"""Dedicated Yellowstone liquidity-verifier source and single-owner lifecycle.

This is the only owner allowed to open the second PHX2 gRPC subscription.  Its
server filter is PumpSwap-only and its client decoder yields only create-pool,
deposit and withdraw instructions; ordinary swaps and ATH events are ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone
import queue
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

import grpc

from PHX2.free_tier_producer.liquidity_integrity import (
    ADD_LIQUIDITY,
    CREATE_POOL,
    CREATE_POOL_DISCRIMINATOR,
    CREATION_CONTEXT_CPI,
    CREATION_CONTEXT_MIGRATION_CPI,
    CREATION_CONTEXT_TOP_LEVEL,
    REMOVE_LIQUIDITY,
    LiquidityEvent,
    LiquidityIntegrityIndex,
    decode_pumpswap_instruction,
)
from PHX2.free_tier_producer.migration_admission import (
    migration_cpi_ancestry_proven,
)
from PHX2.free_tier_producer.paid_grpc_source import (
    ITERATOR_END_CANCELLED,
    ITERATOR_END_CLEAN_EOF,
    ITERATOR_END_GRPC_ERROR,
    ITERATOR_END_LOCAL_ERROR,
    ITERATOR_END_MAX_EVENTS,
    ITERATOR_END_NOT_STARTED,
    REFUSAL_NONE,
    REFUSAL_STREAM_ERROR,
    _base58_encode,
    _grpc_code,
    _resolve_key,
    _safe_exception_class,
    _safe_grpc_detail,
)
from PHX2.proto.stage28_11._generated import geyser_pb2, geyser_pb2_grpc
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    _build_metadata,
    _open_channel,
    build_pumpswap_subscribe_request,
)


VERIFIER_ROLE = "LIQUIDITY_VERIFIER"
VERIFIER_STATUS_STOPPED = "STOPPED"
VERIFIER_STATUS_CONNECTING = "CONNECTING"
VERIFIER_STATUS_CONNECTED = "CONNECTED"
VERIFIER_STATUS_RECONNECTING = "RECONNECTING"
VERIFIER_STATUS_AUTH_FAILED = "AUTH_FAILED"
VERIFIER_STATUS_STOPPING = "STOPPING"


def _utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _unwrap(update: object) -> Optional[Tuple[Any, Any, Any, Any]]:
    try:
        wrapper = update.transaction
        tx_info = wrapper.transaction
        return wrapper, tx_info, tx_info.transaction.message, tx_info.meta
    except Exception:
        return None


def _all_keys(message: object, meta: object) -> list[bytes]:
    keys = [bytes(value) for value in list(getattr(message, "account_keys", ()) or ())]
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_writable_addresses", ()) or ()))
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_readonly_addresses", ()) or ()))
    return keys


def _raw_token_amount(balance: object) -> Optional[int]:
    try:
        amount = getattr(balance.ui_token_amount, "amount", None)
        if isinstance(amount, str) and amount.isdigit():
            return int(amount)
        value = int(amount)
        return value if value >= 0 else None
    except Exception:
        return None


def _balance_evidence(meta: object, keys: list[bytes]) -> Tuple[Dict[str, str], Dict[str, int]]:
    pre: Dict[int, int] = {}
    post: Dict[int, int] = {}
    owners: Dict[str, str] = {}
    for attr, target in (("pre_token_balances", pre), ("post_token_balances", post)):
        for balance in list(getattr(meta, attr, ()) or ()):
            try:
                index = int(balance.account_index)
                amount = _raw_token_amount(balance)
                address = _resolve_key(keys, index)
                owner = getattr(balance, "owner", None)
                if amount is not None:
                    target[index] = amount
                if address and isinstance(owner, str) and owner:
                    owners[address] = owner
            except Exception:
                continue
    deltas: Dict[str, int] = {}
    for index in set(pre) | set(post):
        address = _resolve_key(keys, index)
        if address:
            deltas[address] = post.get(index, 0) - pre.get(index, 0)
    return owners, deltas


def decode_liquidity_update(update: object, *, observed_at_utc: Optional[str] = None) -> Tuple[LiquidityEvent, ...]:
    """Decode only PumpSwap create/deposit/withdraw instructions from one tx."""

    unwrapped = _unwrap(update)
    if unwrapped is None:
        return ()
    wrapper, tx_info, message, meta = unwrapped
    keys = _all_keys(message, meta)
    if not keys:
        return ()
    try:
        signature = _base58_encode(bytes(tx_info.signature))
        slot = int(wrapper.slot)
    except Exception:
        return ()
    if not signature:
        return ()
    if observed_at_utc is None:
        observed_at_utc = _utc_iso(time.time())
    required = int(getattr(getattr(message, "header", None), "num_required_signatures", 0) or 0)
    signer_keys = {
        _resolve_key(keys, index) for index in range(min(required, len(keys)))
    }
    signer_keys.discard(None)
    fee_payer = _resolve_key(keys, 0)
    owners, deltas = _balance_evidence(meta, keys)
    # Preserve the historical flattening order (top-level first, then inner
    # groups in order) so event_index/dedupe keys stay stable, but carry each
    # instruction's execution context for CPI-aware authority semantics.
    top_instructions: List[Any] = list(getattr(message, "instructions", ()) or ())
    entries: List[Tuple[Any, str, Optional[Tuple[Any, ...]]]] = [
        (instruction, CREATION_CONTEXT_TOP_LEVEL, None)
        for instruction in top_instructions
    ]
    for group in list(getattr(meta, "inner_instructions", ()) or ()):
        group_instructions = tuple(getattr(group, "instructions", ()) or ())
        try:
            group_index = int(getattr(group, "index"))
        except Exception:
            group_index = -1
        if 0 <= group_index < len(top_instructions):
            top = top_instructions[group_index]
            try:
                top_program = _resolve_key(keys, int(top.program_id_index))
                top_data = bytes(top.data)
            except Exception:
                top_program, top_data = None, b""
        else:
            top_program, top_data = None, b""
        for inner_index, instruction in enumerate(group_instructions):
            entries.append((instruction, CREATION_CONTEXT_CPI,
                            (group_instructions, inner_index, top_program, top_data)))
    events = []
    event_index = 0
    for instruction, context_kind, group_context in entries:
        try:
            program = _resolve_key(keys, int(instruction.program_id_index))
            if program != PUMPSWAP_PROGRAM_ID:
                continue
            data = bytes(instruction.data)
            migration_proven = False
            if group_context is not None and data.startswith(CREATE_POOL_DISCRIMINATOR):
                group_instructions, inner_index, top_program, top_data = group_context
                migration_proven = migration_cpi_ancestry_proven(
                    group_instructions=group_instructions,
                    inner_index=inner_index,
                    top_level_program=top_program,
                    top_level_data=top_data,
                    keys=keys,
                )
            account_indices = list(bytes(instruction.accounts))
            accounts = [_resolve_key(keys, index) or "" for index in account_indices]
            event = decode_pumpswap_instruction(
                program_id=program,
                data=data,
                accounts=accounts,
                signer_keys=signer_keys,
                fee_payer=fee_payer,
                transaction_signature=signature,
                event_index=event_index,
                slot=slot,
                timestamp_utc=observed_at_utc,
                vault_owner_by_address=owners,
                reserve_delta_by_address=deltas,
                creation_context=(
                    CREATION_CONTEXT_MIGRATION_CPI if migration_proven else context_kind),
                migration_cpi_proven=migration_proven,
            )
            event_index += 1
            if event.kind in (CREATE_POOL, ADD_LIQUIDITY, REMOVE_LIQUIDITY):
                events.append(event)
        except Exception:
            # A malformed matching instruction is represented by the pure decoder
            # whenever possible; an unrepresentable instruction is dropped rather
            # than guessed from UI text or amount.
            event_index += 1
            continue
    return tuple(events)


class LiquidityYellowstoneSource:
    """One PumpSwap-filtered server stream yielding liquidity instructions only."""

    def __init__(self, *, runtime_config: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
                 max_messages_to_scan: Optional[int] = None,
                 channel_factory: Any = None) -> None:
        self._runtime_config = runtime_config
        self._max_messages = (None if max_messages_to_scan is None
                              else max(1, int(max_messages_to_scan)))
        self._channel_factory = channel_factory
        self._close_event = threading.Event()
        self._response_lock = threading.Lock()
        self._response_iter: Any = None
        self.last_refusal_reason = REFUSAL_NONE
        self.events_scanned = 0
        self.transactions_scanned = 0
        self.liquidity_events_decoded = 0
        self.last_update_epoch: Optional[float] = None
        self.stream_started_epoch: Optional[float] = None
        self.stream_ended_epoch: Optional[float] = None
        self.stream_phase = "NOT_STARTED"
        self.iterator_end_kind = ITERATOR_END_NOT_STARTED
        self.error_class: Optional[str] = None
        self.grpc_status_code: Optional[str] = None
        self.sanitized_error_category: Optional[str] = None
        self.sanitized_details: Optional[str] = None
        self.cancellation_requested = False

    def close(self) -> None:
        self.cancellation_requested = True
        self._close_event.set()
        with self._response_lock:
            response = self._response_iter
        if response is not None:
            try:
                response.cancel()
            except Exception:
                pass

    def diagnostic_snapshot(self) -> Dict[str, Any]:
        return {
            "role": VERIFIER_ROLE,
            "error_class": self.error_class,
            "grpc_status_code": self.grpc_status_code,
            "sanitized_error_category": self.sanitized_error_category,
            "sanitized_details": self.sanitized_details,
            "stream_phase": self.stream_phase,
            "iterator_end_kind": self.iterator_end_kind,
            "cancellation_requested": self.cancellation_requested,
        }

    def iter_events(self, *, max_events: int) -> Iterator[LiquidityEvent]:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events <= 0:
            return
        cfg = self._runtime_config
        response = None
        self.stream_phase = "CHANNEL_OPEN"
        try:
            with _open_channel(cfg, self._channel_factory) as channel:
                stub = geyser_pb2_grpc.GeyserStub(channel)
                self.stream_started_epoch = time.time()
                self.stream_phase = "SUBSCRIBE_CALL"
                response = stub.Subscribe(
                    iter([build_pumpswap_subscribe_request()]),
                    metadata=_build_metadata(cfg),
                )
                with self._response_lock:
                    self._response_iter = response
                self.stream_phase = "ITERATE"
                yielded = 0
                scanned = 0
                while (not self._close_event.is_set()
                       and (self._max_messages is None or scanned < self._max_messages)):
                    try:
                        update = next(response)
                    except StopIteration:
                        self.iterator_end_kind = ITERATOR_END_CLEAN_EOF
                        break
                    except grpc.RpcError as err:
                        if self._close_event.is_set():
                            self.iterator_end_kind = ITERATOR_END_CANCELLED
                            return
                        code = _grpc_code(err)
                        category, details = _safe_grpc_detail(err, code)
                        self.iterator_end_kind = ITERATOR_END_GRPC_ERROR
                        self.error_class = _safe_exception_class(err)
                        self.grpc_status_code = code
                        self.sanitized_error_category = category
                        self.sanitized_details = details
                        self.last_refusal_reason = f"{REFUSAL_STREAM_ERROR}:{code}"
                        return
                    scanned += 1
                    self.events_scanned += 1
                    self.last_update_epoch = time.time()
                    if not isinstance(update, geyser_pb2.SubscribeUpdate):
                        continue
                    try:
                        if not update.HasField("transaction"):
                            continue
                    except (TypeError, ValueError):
                        continue
                    self.transactions_scanned += 1
                    for event in decode_liquidity_update(update):
                        self.liquidity_events_decoded += 1
                        yielded += 1
                        yield event
                        if yielded >= max_events:
                            self.iterator_end_kind = ITERATOR_END_MAX_EVENTS
                            return
                if self._close_event.is_set():
                    self.iterator_end_kind = ITERATOR_END_CANCELLED
        except grpc.RpcError as err:
            if self._close_event.is_set():
                self.iterator_end_kind = ITERATOR_END_CANCELLED
                return
            code = _grpc_code(err)
            category, details = _safe_grpc_detail(err, code)
            self.iterator_end_kind = ITERATOR_END_GRPC_ERROR
            self.error_class = _safe_exception_class(err)
            self.grpc_status_code = code
            self.sanitized_error_category = category
            self.sanitized_details = details
            self.last_refusal_reason = f"{REFUSAL_STREAM_ERROR}:{code}"
        except Exception as err:
            if self._close_event.is_set():
                self.iterator_end_kind = ITERATOR_END_CANCELLED
                return
            self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
            self.error_class = _safe_exception_class(err)
            self.sanitized_error_category = "LOCAL_SOURCE_EXCEPTION"
            self.sanitized_details = "A local verifier exception was withheld."
        finally:
            self.stream_ended_epoch = time.time()
            with self._response_lock:
                if self._response_iter is response:
                    self._response_iter = None
            if response is not None:
                try:
                    response.cancel()
                except Exception:
                    pass


class SingleLiquidityVerifier:
    """Separately owned verifier task with a hard role maximum of one stream."""

    def __init__(self, *, source_factory: Callable[[], Any],
                 integrity_index: LiquidityIntegrityIndex,
                 reconnect_backoff_seconds: float = 1.0,
                 stale_after_seconds: float = 120.0,
                 now_fn: Callable[[], float] = time.time,
                 event_sink: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        if not callable(source_factory):
            raise ValueError("source_factory_required")
        if not isinstance(integrity_index, LiquidityIntegrityIndex):
            raise ValueError("integrity_index_required")
        self._source_factory = source_factory
        self._index = integrity_index
        self._backoff = max(0.0, float(reconnect_backoff_seconds))
        self._stale_after = max(0.05, float(stale_after_seconds))
        self._now = now_fn
        self._event_sink = event_sink
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_source: Any = None
        self._lock = threading.Lock()
        self._status = VERIFIER_STATUS_STOPPED
        self._active_streams = 0
        self._max_active_streams = 0
        self._connect_attempts = 0
        self._reconnects = 0
        self._events_received = 0
        self._stream_errors = 0
        self._authentication_failures = 0
        self._watchdog_reconnects = 0
        self._terminal_auth_failure = False
        self._shutdown_state = "NOT_REQUESTED"
        self._cleanup_state = "CLEAN"
        self._watchdog_state = "IDLE"
        self._attempt_history: List[Dict[str, Any]] = []
        self._last_error_category: Optional[str] = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._shutdown_state = "RUNNING"
            self._thread = threading.Thread(
                target=self._run, name="PHX2-liquidity-verifier", daemon=True)
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 10.0) -> None:
        self._shutdown_state = "REQUESTED"
        self._status = VERIFIER_STATUS_STOPPING
        self._stop.set()
        source = self._active_source
        if source is not None:
            try:
                source.close()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(max(0.0, float(timeout_seconds)))
        with self._lock:
            self._shutdown_state = "COMPLETE" if not (thread and thread.is_alive()) else "TIMEOUT"
            if self._active_streams == 0:
                self._status = VERIFIER_STATUS_STOPPED

    def _emit(self, event: LiquidityEvent) -> None:
        if self._event_sink is None:
            return
        try:
            payload = event.to_dict()
            payload["event_kind"] = payload.pop("kind", event.kind)
            self._event_sink({"kind": "PHX2_LIQUIDITY_EVENT", **payload})
        except Exception:
            pass

    def _run(self) -> None:
        first = True
        while not self._stop.is_set() and not self._terminal_auth_failure:
            source = None
            watchdog_stop = threading.Event()
            watchdog_fired = threading.Event()
            watchdog_thread: Optional[threading.Thread] = None
            started = self._now()
            with self._lock:
                self._connect_attempts += 1
                attempt = self._connect_attempts
                if not first:
                    self._reconnects += 1
                self._status = VERIFIER_STATUS_CONNECTING if first else VERIFIER_STATUS_RECONNECTING
            reason = "CLEAN_EOF"
            diagnostic: Dict[str, Any] = {}
            try:
                source = self._source_factory()
                with self._lock:
                    self._active_source = source
                    self._active_streams += 1
                    self._max_active_streams = max(self._max_active_streams, self._active_streams)
                    self._status = VERIFIER_STATUS_CONNECTED
                    if self._active_streams > 1:
                        raise RuntimeError("verifier_stream_overlap")
                    self._watchdog_state = "WATCHING"
                watchdog_thread = threading.Thread(
                    target=self._watch_source,
                    kwargs={
                        "source": source,
                        "session_started": started,
                        "stop_event": watchdog_stop,
                        "fired_event": watchdog_fired,
                    },
                    name="PHX2-liquidity-verifier-watchdog",
                    daemon=True,
                )
                watchdog_thread.start()
                for event in source.iter_events(max_events=1_000_000_000):
                    if self._stop.is_set():
                        reason = "OPERATOR_SHUTDOWN"
                        break
                    self._events_received += 1
                    if self._index.record(event):
                        self._emit(event)
                refusal = str(getattr(source, "last_refusal_reason", "") or "")
                if watchdog_fired.is_set():
                    reason = "WATCHDOG_STALE"
                    self._watchdog_reconnects += 1
                    self._watchdog_state = "STALE_TRIGGERED"
                elif "UNAUTHENTICATED" in refusal:
                    reason = "AUTH_FAILURE"
                    self._terminal_auth_failure = True
                    self._authentication_failures += 1
                    self._status = VERIFIER_STATUS_AUTH_FAILED
                elif self._stop.is_set():
                    reason = "OPERATOR_SHUTDOWN"
                elif refusal and refusal != REFUSAL_NONE:
                    reason = "STREAM_ERROR"
                    self._stream_errors += 1
            except Exception:
                reason = "OWNER_ERROR"
                self._stream_errors += 1
            finally:
                watchdog_stop.set()
                if source is not None:
                    try:
                        diagnostic = dict(source.diagnostic_snapshot())
                    except Exception:
                        diagnostic = {}
                    try:
                        source.close()
                    except Exception:
                        pass
                if watchdog_thread is not None:
                    watchdog_thread.join(timeout=1.0)
                with self._lock:
                    self._cleanup_state = "IN_PROGRESS"
                    if self._active_streams > 0:
                        self._active_streams -= 1
                    self._active_source = None
                    self._cleanup_state = "CLEAN"
                    self._last_error_category = diagnostic.get("sanitized_error_category")
                    self._attempt_history.append({
                        "attempt": attempt,
                        "started_at_utc": _utc_iso(started),
                        "ended_at_utc": _utc_iso(self._now()),
                        "reason": reason,
                        "active_streams_after_cleanup": self._active_streams,
                        "error_category": self._last_error_category,
                        "authentication_failure": reason == "AUTH_FAILURE",
                        "watchdog_triggered": reason == "WATCHDOG_STALE",
                    })
            first = False
            if self._stop.is_set() or self._terminal_auth_failure:
                break
            if self._backoff:
                self._stop.wait(self._backoff)
        with self._lock:
            if not self._terminal_auth_failure:
                self._status = VERIFIER_STATUS_STOPPED
            if self._active_streams == 0 and self._watchdog_state == "WATCHING":
                self._watchdog_state = "IDLE"

    def _watch_source(self, *, source: Any, session_started: float,
                      stop_event: threading.Event,
                      fired_event: threading.Event) -> None:
        """Cancel one stale verifier source; replacement stays sequential."""
        interval = max(0.05, min(1.0, self._stale_after / 4.0))
        while not self._stop.is_set() and not stop_event.wait(interval):
            last_update = getattr(source, "last_update_epoch", None)
            anchor = float(last_update) if isinstance(last_update, (int, float)) else session_started
            if float(self._now()) - anchor <= self._stale_after:
                continue
            fired_event.set()
            try:
                source.close()
            except Exception:
                pass
            return

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            result = {
                "role": VERIFIER_ROLE,
                "status": self._status,
                "active_streams": self._active_streams,
                "max_active_streams": self._max_active_streams,
                "stream_capacity": 1,
                "connect_attempts": self._connect_attempts,
                "reconnects": self._reconnects,
                "events_received": self._events_received,
                "stream_errors": self._stream_errors,
                "authentication_failures": self._authentication_failures,
                "watchdog_reconnects": self._watchdog_reconnects,
                "terminal_auth_failure": self._terminal_auth_failure,
                "shutdown_state": self._shutdown_state,
                "cleanup_state": self._cleanup_state,
                "watchdog_state": self._watchdog_state,
                "last_error_category": self._last_error_category,
                "attempt_history": list(self._attempt_history),
            }
        result.update(self._index.stats())
        return result


def build_live_liquidity_source_factory() -> Callable[[], LiquidityYellowstoneSource]:
    from PHX2.stage28.chainstack_yellowstone_grpc_models import MODE_PROVIDER_CONNECT_ONLY
    from PHX2.stage28.chainstack_yellowstone_grpc_readiness import build_runtime_config_from_env

    runtime_config = build_runtime_config_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY, max_events=1)

    def factory() -> LiquidityYellowstoneSource:
        return LiquidityYellowstoneSource(
            runtime_config=runtime_config, max_messages_to_scan=None)

    return factory


def combined_stream_snapshot(primary: Mapping[str, Any], verifier: Mapping[str, Any]) -> Dict[str, int]:
    primary_active = int(primary.get("active_streams") or 0)
    verifier_active = int(verifier.get("active_streams") or 0)
    primary_max = int(primary.get("max_active_streams") or 0)
    verifier_max = int(verifier.get("max_active_streams") or 0)
    return {
        "primary_active_streams": primary_active,
        "verifier_active_streams": verifier_active,
        "total_active_streams": primary_active + verifier_active,
        "primary_max_active_streams": primary_max,
        "verifier_max_active_streams": verifier_max,
        "total_max_active_streams": primary_max + verifier_max,
    }


__all__ = (
    "VERIFIER_ROLE", "LiquidityYellowstoneSource", "SingleLiquidityVerifier",
    "decode_liquidity_update", "build_live_liquidity_source_factory",
    "combined_stream_snapshot",
)
