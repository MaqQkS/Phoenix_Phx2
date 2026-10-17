"""Sequential, no-send connectivity diagnostics for shadow parity sources.

The probes instantiate the same source adapters and subscription contracts as
the parity runner. They emit only neutral closed-set fields, numeric counters,
and booleans. Raw exceptions, endpoints, URLs, credentials, response bodies,
and provider product names never enter the result or artifact.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import inspect
import json
from pathlib import Path
import socket
import ssl
import threading
import time
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlsplit

import grpc

from PHX2.free_tier_producer.helius_source import (
    ERROR_AUTH,
    HeliusEnhancedWssSource,
    HeliusSourceConfig,
    STREAM_AUTH_FAILED,
    STREAM_CONNECTED,
    STREAM_FAILED,
)
from PHX2.free_tier_producer.migration_admission import MigrationProofStore
from PHX2.free_tier_producer.paid_provider import build_live_source_factory
from PHX2.scripts.helius_shadow_parity_config import (
    ShadowParityConfiguration,
    load_shadow_parity_configuration,
)
from PHX2.scripts.helius_shadow_parity_preflight import run_preflight
from PHX2.shadow_probes.helius_developer import DEFAULT_MAX_RAW_BYTES


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPOSITORY_ROOT / ".env"
DIAGNOSTIC_ROOT = (
    REPOSITORY_ROOT / "artifacts" / "helius_shadow_parity" / "diagnostics"
)
MAX_PROBE_SECONDS = 180

STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_NOT_OBSERVED = "NOT_OBSERVED"
STATUS_NOT_REQUIRED = "NOT_REQUIRED_TRAFFIC_ACTIVE"

AUTH_ACCEPTED = "ACCEPTED"
AUTH_REJECTED = "REJECTED"
AUTH_UNKNOWN = "UNKNOWN"

RESULT_PASSED = "PASSED"
RESULT_FAILED = "FAILED"


@dataclass(frozen=True)
class NetworkPreflight:
    resolution_status: str
    tcp_status: str
    tls_status: str


@dataclass(frozen=True)
class ShadowConnectivityResult:
    source_role: str
    resolution_status: str
    tcp_status: str
    tls_status: str
    secure_stream_handshake_status: str
    authentication_classification: str
    subscribe_request_transmitted: bool
    subscription_acknowledged: bool
    first_notification_received: bool
    keepalive_status: str
    reconnect_attempts: int
    close_code_class: str
    unsubscribe_transmitted: bool
    unsubscribe_acknowledged: bool
    clean_close: bool
    stable_subscribed_window: bool
    elapsed_seconds: float
    notification_count: int
    byte_count: int
    result_status: str
    failure_stage: str


@dataclass(frozen=True)
class ControlConnectivityResult:
    source_role: str
    resolution_status: str
    channel_readiness_status: str
    authentication_classification: str
    subscription_request_started: bool
    subscription_accepted: bool
    first_update_received: bool
    update_count: int
    last_slot: Optional[int]
    rpc_status_class: str
    reconnect_attempts: int
    elapsed_seconds: float
    result_status: str
    failure_stage: str


class _StreamObserver:
    def __init__(self) -> None:
        self.handshake_succeeded = False
        self.handshake_auth_rejected = False
        self.subscribe_request_id: Optional[int] = None
        self.subscribe_transmitted = False
        self.subscription_acknowledged = False
        self.unsubscribe_request_id: Optional[int] = None
        self.unsubscribe_transmitted = False
        self.unsubscribe_acknowledged = False
        self.keepalive_succeeded = False
        self.close_code: Optional[int] = None


def _safe_http_status(exc: BaseException) -> Optional[int]:
    candidates = (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    )
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


class _ObservedWebSocket:
    def __init__(self, websocket: Any, observer: _StreamObserver) -> None:
        self._websocket = websocket
        self._observer = observer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._websocket, name)

    async def send(self, raw: object) -> None:
        parsed: Mapping[str, object] = {}
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, Mapping):
                parsed = candidate
        except (TypeError, ValueError):
            pass
        await self._websocket.send(raw)
        method = parsed.get("method")
        request_id = parsed.get("id")
        if method == "transactionSubscribe":
            self._observer.subscribe_transmitted = True
            if isinstance(request_id, int) and not isinstance(request_id, bool):
                self._observer.subscribe_request_id = request_id
        elif method == "transactionUnsubscribe":
            self._observer.unsubscribe_transmitted = True
            if isinstance(request_id, int) and not isinstance(request_id, bool):
                self._observer.unsubscribe_request_id = request_id

    async def recv(self) -> object:
        raw = await self._websocket.recv()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return raw
        if not isinstance(parsed, Mapping):
            return raw
        request_id = parsed.get("id")
        result = parsed.get("result")
        if request_id == self._observer.subscribe_request_id:
            if (
                isinstance(result, (int, float))
                and not isinstance(result, bool)
                and (not isinstance(result, float) or result.is_integer())
                and "error" not in parsed
            ):
                self._observer.subscription_acknowledged = True
        if request_id == self._observer.unsubscribe_request_id:
            if result is True and "error" not in parsed:
                self._observer.unsubscribe_acknowledged = True
        return raw

    async def ping(self) -> object:
        pong = await self._websocket.ping()

        async def observe_pong() -> None:
            if inspect.isawaitable(pong):
                await pong
            self._observer.keepalive_succeeded = True

        return observe_pong()

    async def close(self) -> None:
        await self._websocket.close()


class _ObservedConnector:
    def __init__(self, connector: Any, observer: _StreamObserver) -> None:
        self._connector = connector
        self._observer = observer
        self._websocket: Any = None

    async def __aenter__(self) -> _ObservedWebSocket:
        try:
            self._websocket = await self._connector.__aenter__()
        except BaseException as exc:
            self._observer.handshake_auth_rejected = (
                _safe_http_status(exc) in (401, 403)
            )
            raise
        self._observer.handshake_succeeded = True
        return _ObservedWebSocket(self._websocket, self._observer)

    async def __aexit__(self, *args: object) -> object:
        result = await self._connector.__aexit__(*args)
        code = getattr(self._websocket, "close_code", None)
        if isinstance(code, int) and not isinstance(code, bool):
            self._observer.close_code = code
        return result


def _observed_connect(
    observer: _StreamObserver,
    base_connect: Optional[Callable[..., Any]],
) -> Callable[..., Any]:
    if base_connect is None:
        import websockets

        base_connect = websockets.connect

    def connect(url: str, **kwargs: Any) -> _ObservedConnector:
        return _ObservedConnector(base_connect(url, **kwargs), observer)

    return connect


def _host_port(value: str, *, default_port: int = 443) -> tuple[str, int]:
    parsed = urlsplit(value if "://" in value else "//" + value)
    host = parsed.hostname
    if not host:
        raise ValueError("host unavailable")
    return host, int(parsed.port or default_port)


def _network_preflight(host: str, port: int) -> NetworkPreflight:
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception:
        return NetworkPreflight(STATUS_FAILED, STATUS_NOT_OBSERVED, STATUS_NOT_OBSERVED)
    try:
        with socket.create_connection((host, port), timeout=10):
            pass
    except Exception:
        return NetworkPreflight(STATUS_PASSED, STATUS_FAILED, STATUS_NOT_OBSERVED)
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=host):
                pass
    except Exception:
        return NetworkPreflight(STATUS_PASSED, STATUS_PASSED, STATUS_FAILED)
    return NetworkPreflight(STATUS_PASSED, STATUS_PASSED, STATUS_PASSED)


def _close_code_class(code: Optional[int]) -> str:
    if code in (1000, 1001):
        return "NORMAL"
    if code in (1002, 1003, 1007, 1008, 1009, 1010):
        return "POLICY_OR_PROTOCOL"
    if code in (1011, 1012, 1013, 1014):
        return "REMOTE_FAILURE"
    if code is None:
        return "NOT_OBSERVED"
    return "ABNORMAL"


def _shadow_failure_stage(
    *,
    network: NetworkPreflight,
    observer: _StreamObserver,
    source: HeliusEnhancedWssSource,
    stable_window: bool,
) -> str:
    if network.resolution_status != STATUS_PASSED:
        return "DNS_RESOLUTION"
    if network.tcp_status != STATUS_PASSED:
        return "TCP_CONNECT"
    if network.tls_status != STATUS_PASSED:
        return "TLS_HANDSHAKE"
    if not observer.handshake_succeeded:
        return (
            "AUTHENTICATION"
            if observer.handshake_auth_rejected
            else "SECURE_STREAM_HANDSHAKE"
        )
    if not observer.subscribe_transmitted:
        return "SUBSCRIBE_TRANSMIT"
    if not observer.subscription_acknowledged:
        return "SUBSCRIBE_ACKNOWLEDGEMENT"
    if not (
        source.metrics.notifications_received > 0 or stable_window
    ):
        return "NOTIFICATION_OR_STABILITY"
    if not observer.unsubscribe_transmitted:
        return "UNSUBSCRIBE_TRANSMIT"
    if not observer.unsubscribe_acknowledged:
        return "UNSUBSCRIBE_ACKNOWLEDGEMENT"
    if _close_code_class(observer.close_code) != "NORMAL":
        return "CLOSE_HANDSHAKE"
    return "NONE"


async def run_shadow_connectivity_probe(
    *,
    config: HeliusSourceConfig,
    duration_seconds: int,
    base_connect: Optional[Callable[..., Any]] = None,
    network_preflight: Callable[[str, int], NetworkPreflight] = (
        _network_preflight
    ),
) -> ShadowConnectivityResult:
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or not 1 <= duration_seconds <= MAX_PROBE_SECONDS
    ):
        raise ValueError("duration_seconds is out of range")
    started = time.monotonic()
    host, port = _host_port(config.ws_base_url.reveal())
    network = await asyncio.to_thread(network_preflight, host, port)
    observer = _StreamObserver()
    source = HeliusEnhancedWssSource(
        config=config,
        connect_fn=_observed_connect(observer, base_connect),
    )
    resume_after_observation = asyncio.Event()

    async def consume() -> None:
        async for _event in source.iter_events_async(max_events=10_000):
            # Hold the generator at the delivered-event boundary until the
            # probe requests its cooperative unsubscribe. Without this small
            # barrier a high-throughput fake or provider can consume the next
            # frame before the supervising task observes the first one.
            await resume_after_observation.wait()

    task = asyncio.create_task(consume())
    # Preserve enough time inside the hard bound for a provider unsubscribe
    # acknowledgement when the no-notification stability path is exercised.
    active_deadline = started + max(1.0, duration_seconds - 22.0)
    stable_window = False
    while time.monotonic() < active_deadline:
        if task.done():
            break
        if source.metrics.notifications_received > 0:
            break
        await asyncio.sleep(0.05)
    else:
        stable_window = (
            source.status == STREAM_CONNECTED
            and source.metrics.subscriptions > 0
        )

    source.request_graceful_close()
    resume_after_observation.set()
    remaining = max(0.1, started + duration_seconds - time.monotonic())
    try:
        await asyncio.wait_for(task, timeout=remaining)
    except asyncio.TimeoutError:
        source.close()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    failure_stage = _shadow_failure_stage(
        network=network,
        observer=observer,
        source=source,
        stable_window=stable_window,
    )
    authentication = (
        AUTH_ACCEPTED
        if observer.subscription_acknowledged
        else AUTH_REJECTED
        if (
            observer.handshake_auth_rejected
            or source.status == STREAM_AUTH_FAILED
            or source.last_refusal_reason == ERROR_AUTH
        )
        else AUTH_UNKNOWN
    )
    keepalive = (
        STATUS_PASSED
        if observer.keepalive_succeeded
        else STATUS_NOT_REQUIRED
        if source.metrics.notifications_received > 0
        else STATUS_NOT_OBSERVED
    )
    close_class = _close_code_class(observer.close_code)
    return ShadowConnectivityResult(
        source_role="SHADOW_SOURCE",
        resolution_status=network.resolution_status,
        tcp_status=network.tcp_status,
        tls_status=network.tls_status,
        secure_stream_handshake_status=(
            STATUS_PASSED
            if observer.handshake_succeeded
            else STATUS_FAILED
        ),
        authentication_classification=authentication,
        subscribe_request_transmitted=observer.subscribe_transmitted,
        subscription_acknowledged=observer.subscription_acknowledged,
        first_notification_received=(
            source.metrics.notifications_received > 0
        ),
        keepalive_status=keepalive,
        reconnect_attempts=int(source.metrics.reconnects),
        close_code_class=close_class,
        unsubscribe_transmitted=observer.unsubscribe_transmitted,
        unsubscribe_acknowledged=observer.unsubscribe_acknowledged,
        clean_close=(close_class == "NORMAL"),
        stable_subscribed_window=stable_window,
        elapsed_seconds=round(max(0.0, time.monotonic() - started), 3),
        notification_count=int(source.metrics.notifications_received),
        byte_count=int(source.metrics.notification_bytes),
        result_status=(
            RESULT_PASSED if failure_stage == "NONE" else RESULT_FAILED
        ),
        failure_stage=failure_stage,
    )


class _ReadyChannelFactory:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.ready = False

    def __call__(self, target: str, credentials: object) -> object:
        channel = grpc.secure_channel(target, credentials)
        try:
            grpc.channel_ready_future(channel).result(
                timeout=self.timeout_seconds
            )
        except Exception:
            return channel
        self.ready = True
        return channel


def _control_failure_stage(
    *,
    resolution_status: str,
    channel_ready: bool,
    source: object,
) -> str:
    if resolution_status != STATUS_PASSED:
        return "ENDPOINT_RESOLUTION"
    if not channel_ready:
        return "CHANNEL_READINESS"
    status = str(getattr(source, "grpc_status_code", "") or "")
    if status in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
        return "AUTHENTICATION"
    updates = int(getattr(source, "events_scanned", 0) or 0)
    last_slot = (
        getattr(source, "last_slot_observed", None)
        if isinstance(getattr(source, "last_slot_observed", None), int)
        else getattr(source, "latest_confirmed_slot", None)
        if isinstance(getattr(source, "latest_confirmed_slot", None), int)
        else None
    )
    if last_slot is None:
        if str(getattr(source, "iterator_end_kind", "")) == "GRPC_ERROR":
            return "SUBSCRIPTION_REJECTED"
        return (
            "ZERO_UPDATE_TIMEOUT"
            if updates <= 0
            else "REAL_UPDATE_TIMEOUT"
        )
    return "NONE"


def run_control_connectivity_probe(
    *,
    configuration: ShadowParityConfiguration,
    duration_seconds: int,
    channel_factory: Optional[Callable[..., Any]] = None,
    resolver: Callable[..., object] = socket.getaddrinfo,
    source_factory: Optional[Callable[[], Any]] = None,
) -> ControlConnectivityResult:
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or not 1 <= duration_seconds <= MAX_PROBE_SECONDS
    ):
        raise ValueError("duration_seconds is out of range")
    started = time.monotonic()
    target = (
        configuration.chainstack.endpoint_secret
        .get_endpoint_url_for_internal_use()
    )
    host, port = _host_port(target)
    try:
        resolver(host, port, type=socket.SOCK_STREAM)
    except Exception:
        resolution_status = STATUS_FAILED
    else:
        resolution_status = STATUS_PASSED
    ready_factory = (
        _ReadyChannelFactory()
        if channel_factory is None
        else channel_factory
    )
    if source_factory is None:
        proof_store = MigrationProofStore()
        source = build_live_source_factory(
            proof_store=proof_store,
            runtime_config=configuration.chainstack,
        )()
    else:
        source = source_factory()
    if channel_factory is None:
        source._channel_factory = ready_factory
    else:
        source._channel_factory = channel_factory

    def consume() -> None:
        for _event in source.iter_events(max_events=10_000):
            pass

    thread = threading.Thread(
        target=consume,
        name="phx2-control-connectivity-probe",
        daemon=True,
    )
    thread.start()
    deadline = started + duration_seconds
    while time.monotonic() < deadline and thread.is_alive():
        if (
            isinstance(source.last_slot_observed, int)
            or isinstance(source.latest_confirmed_slot, int)
        ):
            break
        time.sleep(0.05)
    source.close()
    thread.join(timeout=max(0.1, deadline - time.monotonic()))
    channel_ready = bool(getattr(ready_factory, "ready", False))
    failure_stage = _control_failure_stage(
        resolution_status=resolution_status,
        channel_ready=channel_ready,
        source=source,
    )
    status = str(source.grpc_status_code or "")
    accepted = (
        isinstance(source.last_slot_observed, int)
        or isinstance(source.latest_confirmed_slot, int)
    )
    authentication = (
        AUTH_REJECTED
        if status in ("UNAUTHENTICATED", "PERMISSION_DENIED")
        else AUTH_ACCEPTED
        if accepted
        else AUTH_UNKNOWN
    )
    last_slot = (
        source.last_slot_observed
        if isinstance(source.last_slot_observed, int)
        else source.latest_confirmed_slot
        if isinstance(source.latest_confirmed_slot, int)
        else None
    )
    return ControlConnectivityResult(
        source_role="CONTROL_SOURCE",
        resolution_status=resolution_status,
        channel_readiness_status=(
            STATUS_PASSED if channel_ready else STATUS_FAILED
        ),
        authentication_classification=authentication,
        subscription_request_started=(
            source.stream_phase
            not in ("NOT_STARTED", "CHANNEL_OPEN", "SUBSCRIBE_CALL")
        ),
        subscription_accepted=accepted,
        first_update_received=accepted,
        update_count=int(source.events_scanned),
        last_slot=last_slot,
        rpc_status_class=status or "NONE",
        reconnect_attempts=0,
        elapsed_seconds=round(max(0.0, time.monotonic() - started), 3),
        result_status=(
            RESULT_PASSED if failure_stage == "NONE" else RESULT_FAILED
        ),
        failure_stage=failure_stage,
    )


def _write_result(path: Path, result: object) -> None:
    resolved = path.resolve()
    allowed = DIAGNOSTIC_ROOT.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError("diagnostic output is outside the allowed root")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(asdict(result), sort_keys=True, indent=2) + "\n"
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequential scanner-safe provider connectivity diagnosis"
    )
    parser.add_argument("source", choices=("shadow", "control"))
    parser.add_argument("--seconds", type=int, default=MAX_PROBE_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    try:
        run_preflight()
        configuration = load_shadow_parity_configuration(
            env_path=args.env_file,
            max_helius_raw_bytes=DEFAULT_MAX_RAW_BYTES,
        )
        if args.source == "shadow":
            result = asyncio.run(
                run_shadow_connectivity_probe(
                    config=configuration.helius,
                    duration_seconds=args.seconds,
                )
            )
        else:
            result = run_control_connectivity_probe(
                configuration=configuration,
                duration_seconds=args.seconds,
            )
        _write_result(args.output, result)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "result_status": RESULT_FAILED,
                    "failure_stage": "DIAGNOSTIC_REFUSED",
                    "safe_error_class": type(exc).__name__,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    print(json.dumps(asdict(result), sort_keys=True, indent=2), flush=True)
    return 0 if result.result_status == RESULT_PASSED else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "AUTH_ACCEPTED",
    "AUTH_REJECTED",
    "AUTH_UNKNOWN",
    "ControlConnectivityResult",
    "NetworkPreflight",
    "RESULT_FAILED",
    "RESULT_PASSED",
    "ShadowConnectivityResult",
    "run_control_connectivity_probe",
    "run_shadow_connectivity_probe",
)
