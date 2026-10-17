"""Deterministic startup and scanner-safety tests for isolated probes."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import threading

from PHX2.free_tier_producer.compat.build26_capture_artifacts import scan_text
from PHX2.scripts import provider_connectivity_diagnostics as diagnostics
from PHX2.tests.test_helius_shadow_parity_config import _dotenv, _load
from PHX2.tests.test_helius_shadow_source import (
    _config,
    _Connection,
    _ConnectSequence,
    _FakeWebSocket,
    _notification,
)


PASSED_NETWORK = diagnostics.NetworkPreflight(
    diagnostics.STATUS_PASSED,
    diagnostics.STATUS_PASSED,
    diagnostics.STATUS_PASSED,
)


def _network_pass(_host: str, _port: int) -> diagnostics.NetworkPreflight:
    return PASSED_NETWORK


def _websocket(*responses: object) -> _FakeWebSocket:
    websocket = _FakeWebSocket(responses)
    websocket.close_code = 1000
    return websocket


def test_successful_shadow_isolated_startup() -> None:
    websocket = _websocket(
        {"jsonrpc": "2.0", "id": 1, "result": 77},
        _notification(subscription_id=77),
        {"jsonrpc": "2.0", "id": 2, "result": True},
    )
    result = asyncio.run(
        diagnostics.run_shadow_connectivity_probe(
            config=_config(max_reconnects=0),
            duration_seconds=1,
            base_connect=_ConnectSequence(_Connection(websocket)),
            network_preflight=_network_pass,
        )
    )
    assert result.result_status == diagnostics.RESULT_PASSED
    assert result.secure_stream_handshake_status == diagnostics.STATUS_PASSED
    assert result.subscription_acknowledged is True
    assert result.first_notification_received is True
    assert result.unsubscribe_transmitted is True
    assert result.unsubscribe_acknowledged is True
    assert result.clean_close is True


def test_shadow_handshake_failure_is_stage_specific() -> None:
    result = asyncio.run(
        diagnostics.run_shadow_connectivity_probe(
            config=_config(max_reconnects=0),
            duration_seconds=1,
            base_connect=_ConnectSequence(
                _Connection(error=OSError("secret-bearing-url"))
            ),
            network_preflight=_network_pass,
        )
    )
    assert result.result_status == diagnostics.RESULT_FAILED
    assert result.failure_stage == "SECURE_STREAM_HANDSHAKE"
    assert result.subscribe_request_transmitted is False
    assert "secret-bearing-url" not in json.dumps(asdict(result))


def test_shadow_subscribe_rejection_is_not_a_connection_success() -> None:
    websocket = _websocket(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "synthetic secret"},
        }
    )
    result = asyncio.run(
        diagnostics.run_shadow_connectivity_probe(
            config=_config(max_reconnects=0),
            duration_seconds=1,
            base_connect=_ConnectSequence(_Connection(websocket)),
            network_preflight=_network_pass,
        )
    )
    assert result.secure_stream_handshake_status == diagnostics.STATUS_PASSED
    assert result.subscribe_request_transmitted is True
    assert result.subscription_acknowledged is False
    assert result.failure_stage == "SUBSCRIBE_ACKNOWLEDGEMENT"
    assert "synthetic secret" not in json.dumps(asdict(result))


def test_shadow_reconnect_exhaustion_is_counted() -> None:
    result = asyncio.run(
        diagnostics.run_shadow_connectivity_probe(
            config=_config(max_reconnects=1),
            duration_seconds=1,
            base_connect=_ConnectSequence(
                _Connection(error=OSError("first secret")),
                _Connection(error=OSError("second secret")),
            ),
            network_preflight=_network_pass,
        )
    )
    assert result.result_status == diagnostics.RESULT_FAILED
    assert result.reconnect_attempts == 1
    rendered = json.dumps(asdict(result))
    assert "first secret" not in rendered
    assert "second secret" not in rendered


class _ReadyFactory:
    ready = True

    def __call__(self, *_args, **_kwargs):
        raise AssertionError("fake source does not open a channel")


class _FakeControlSource:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.events_scanned = 0
        self.transactions_scanned = 0
        self.stream_phase = "NOT_STARTED"
        self.iterator_end_kind = "NOT_STARTED"
        self.grpc_status_code = None
        self.last_slot_observed = None
        self.latest_confirmed_slot = None
        self._closed = threading.Event()
        self._channel_factory = None

    def iter_events(self, *, max_events: int):
        assert max_events > 0
        self.stream_phase = "ITERATE"
        if self.outcome == "success":
            self.events_scanned = 1
            self.transactions_scanned = 1
            self.last_slot_observed = 444
            yield object()
            return
        if self.outcome == "rejected":
            self.iterator_end_kind = "GRPC_ERROR"
            self.grpc_status_code = "PERMISSION_DENIED"
            return
        if self.outcome == "frame":
            self.events_scanned = 1
        self._closed.wait(timeout=2)
        self.iterator_end_kind = "CANCELLED"
        return
        yield  # pragma: no cover

    def close(self) -> None:
        self._closed.set()


def _configuration(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    return _load(path)


def test_successful_control_subscription_requires_a_real_update(
    tmp_path: Path,
) -> None:
    source = _FakeControlSource("success")
    result = diagnostics.run_control_connectivity_probe(
        configuration=_configuration(tmp_path),
        duration_seconds=1,
        channel_factory=_ReadyFactory(),
        resolver=lambda *_args, **_kwargs: [object()],
        source_factory=lambda: source,
    )
    assert result.result_status == diagnostics.RESULT_PASSED
    assert result.subscription_accepted is True
    assert result.first_update_received is True
    assert result.update_count == 1
    assert result.last_slot == 444


def test_control_channel_ready_but_subscription_rejected(
    tmp_path: Path,
) -> None:
    source = _FakeControlSource("rejected")
    result = diagnostics.run_control_connectivity_probe(
        configuration=_configuration(tmp_path),
        duration_seconds=1,
        channel_factory=_ReadyFactory(),
        resolver=lambda *_args, **_kwargs: [object()],
        source_factory=lambda: source,
    )
    assert result.channel_readiness_status == diagnostics.STATUS_PASSED
    assert result.subscription_accepted is False
    assert result.authentication_classification == diagnostics.AUTH_REJECTED
    assert result.failure_stage == "AUTHENTICATION"


def test_control_channel_ready_with_zero_updates_times_out(
    tmp_path: Path,
) -> None:
    source = _FakeControlSource("zero")
    result = diagnostics.run_control_connectivity_probe(
        configuration=_configuration(tmp_path),
        duration_seconds=1,
        channel_factory=_ReadyFactory(),
        resolver=lambda *_args, **_kwargs: [object()],
        source_factory=lambda: source,
    )
    assert result.channel_readiness_status == diagnostics.STATUS_PASSED
    assert result.subscription_accepted is False
    assert result.update_count == 0
    assert result.failure_stage == "ZERO_UPDATE_TIMEOUT"


def test_control_non_slot_frame_is_not_a_real_update(
    tmp_path: Path,
) -> None:
    source = _FakeControlSource("frame")
    result = diagnostics.run_control_connectivity_probe(
        configuration=_configuration(tmp_path),
        duration_seconds=1,
        channel_factory=_ReadyFactory(),
        resolver=lambda *_args, **_kwargs: [object()],
        source_factory=lambda: source,
    )
    assert result.subscription_accepted is False
    assert result.update_count == 1
    assert result.last_slot is None
    assert result.failure_stage == "REAL_UPDATE_TIMEOUT"


def test_probe_results_and_readiness_fields_are_scanner_safe(
    tmp_path: Path,
) -> None:
    configuration = _configuration(tmp_path)
    result = diagnostics.ShadowConnectivityResult(
        source_role="SHADOW_SOURCE",
        resolution_status="PASSED",
        tcp_status="PASSED",
        tls_status="PASSED",
        secure_stream_handshake_status="PASSED",
        authentication_classification="ACCEPTED",
        subscribe_request_transmitted=True,
        subscription_acknowledged=True,
        first_notification_received=True,
        keepalive_status="NOT_REQUIRED_TRAFFIC_ACTIVE",
        reconnect_attempts=0,
        close_code_class="NORMAL",
        unsubscribe_transmitted=True,
        unsubscribe_acknowledged=True,
        clean_close=True,
        stable_subscribed_window=False,
        elapsed_seconds=1.0,
        notification_count=1,
        byte_count=100,
        result_status="PASSED",
        failure_stage="NONE",
    )
    rendered = json.dumps(
        {
            "readiness": configuration.sanitized_readiness(),
            "result": asdict(result),
        },
        sort_keys=True,
    )
    assert scan_text(rendered) == []
