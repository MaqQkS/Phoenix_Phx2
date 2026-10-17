from __future__ import annotations

import inspect
import json
import threading
import time
from types import SimpleNamespace

import grpc

from PHX2.free_tier_producer import paid_grpc_source as source_module
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.free_tier_session import paid_provider_safety_error
from PHX2.free_tier_producer.paid_grpc_source import PaidCreatePoolYellowstoneSource
from PHX2.free_tier_producer.paid_provider import (
    STREAM_STATUS_AUTH_FAILED,
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "ExVW9Wxpr4TnMchukxGwMYM4XYTr3yTKwpqDE35E9seW"
QUOTE = "So11111111111111111111111111111111111111112"


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details


def _patch_response(monkeypatch, response) -> None:
    class Context:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    class Stub:
        def __init__(self, _channel):
            pass

        def Subscribe(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(source_module, "_open_channel", lambda *_a, **_kw: Context())
    monkeypatch.setattr(source_module.geyser_pb2_grpc, "GeyserStub", Stub)
    monkeypatch.setattr(source_module, "_build_metadata", lambda _cfg: ())


def _runtime():
    return SimpleNamespace(safe_config=SimpleNamespace(provider_id="TEST_PROVIDER"))


def test_resource_exhausted_diagnostic_is_exact_and_cannot_persist_raw_details(monkeypatch):
    secret = "SUPER_SECRET_X_TOKEN_VALUE"
    endpoint = "https://private-provider.example:443"

    class Response:
        def __next__(self):
            raise _FakeRpcError(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                f"too many concurrent subscriptions at {endpoint}; x-token={secret}",
            )

        def cancel(self):
            return None

    _patch_response(monkeypatch, Response())
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(), max_messages_to_scan=None)
    assert list(source.iter_events(max_events=1)) == []
    assert source.last_refusal_reason == "STREAM_ERROR:RESOURCE_EXHAUSTED"
    diagnostic = source.diagnostic_snapshot()
    assert diagnostic == {
        "error_class": "_FakeRpcError",
        "grpc_status_code": "RESOURCE_EXHAUSTED",
        "sanitized_error_category": "PROVIDER_CONCURRENT_STREAM_LIMIT",
        "sanitized_details": (
            "Provider rejected the stream because its concurrent subscription limit was reached."),
        "stream_phase": "ITERATE",
        "iterator_end_kind": "GRPC_ERROR",
        "cancellation_requested": False,
    }
    serialized = json.dumps(diagnostic, sort_keys=True)
    assert secret not in serialized
    assert endpoint not in serialized
    assert "x-token" not in serialized.lower()
    unavailable = _FakeRpcError(
        grpc.StatusCode.UNAVAILABLE,
        f"failed to connect to all addresses at {endpoint}; x-token={secret}",
    )
    category, safe_detail = source_module._safe_grpc_detail(unavailable, "UNAVAILABLE")
    assert category == "NETWORK_CONNECT_FAILURE"
    assert safe_detail == "The transport could not establish a connection."
    assert secret not in safe_detail
    assert endpoint not in safe_detail


def test_local_iterator_exception_records_only_fixed_safe_text(monkeypatch):
    secret = "DO_NOT_PERSIST_THIS_SECRET"

    class Response:
        def __next__(self):
            raise ValueError(f"decoder failed near {secret} at https://private.example")

        def cancel(self):
            return None

    _patch_response(monkeypatch, Response())
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(), max_messages_to_scan=None)
    assert list(source.iter_events(max_events=1)) == []
    diagnostic = source.diagnostic_snapshot()
    assert diagnostic["error_class"] == "ValueError"
    assert diagnostic["grpc_status_code"] is None
    assert diagnostic["sanitized_error_category"] == "LOCAL_SOURCE_EXCEPTION"
    assert diagnostic["stream_phase"] == "ITERATE"
    assert diagnostic["iterator_end_kind"] == "LOCAL_ERROR"
    serialized = json.dumps(diagnostic, sort_keys=True)
    assert secret not in serialized
    assert "private.example" not in serialized


def test_confirmed_slot_advances_transport_watermark_not_event_cursor(monkeypatch):
    class Response:
        def __init__(self):
            self._updates = iter([
                source_module.geyser_pb2.SubscribeUpdate(
                    slot=source_module.geyser_pb2.SubscribeUpdateSlot(
                        slot=987654,
                        parent=987653,
                        status=source_module.geyser_pb2.SLOT_CONFIRMED,
                    )
                )
            ])

        def __next__(self):
            return next(self._updates)

        def cancel(self):
            return None

    class Cursor:
        def __init__(self):
            self.commits = []

        def commit_event(self, **kwargs):
            self.commits.append(kwargs)

    cursor = Cursor()
    observed = []
    _patch_response(monkeypatch, Response())
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(),
        max_messages_to_scan=None,
        cursor=cursor,
        transport_slot_observer=(
            lambda slot, observed_at: observed.append(
                (slot, observed_at)
            )
            or True
        ),
    )
    assert list(source.iter_events(max_events=1)) == []
    assert [slot for slot, _ in observed] == [987654]
    assert source.first_confirmed_slot == 987654
    assert source.latest_confirmed_slot == 987654
    assert source.confirmed_slot_updates == 1
    assert cursor.commits == []

def test_attempt_history_proves_sequential_cleanup_backoff_and_ath_survival(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b"frozen-ledger\n")
    ledger_before = ledger.read_bytes()
    ath_dir = tmp_path / "ath"
    store = CentralAthStateStore(ath_dir)
    assert store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="2026-07-16T00:00:00Z")
    assert store.observe_provider_current(
        mint=MINT, price_usd="10", market_cap_usd="10000",
        observed_at="2026-07-16T00:00:01Z")
    made = []

    class Source:
        events_scanned = 0
        transactions_scanned = 0
        create_pool_yielded = 0
        reserve_events_decoded = 0
        first_update_epoch = None
        last_update_epoch = None
        last_decoded_event_epoch = None

        def __init__(self, number):
            self.number = number
            self.closed = threading.Event()
            self.cancellation_requested = False
            self.stream_started_epoch = time.time()
            self.last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            assert max_events == 256
            if self.number == 1:
                self.last_refusal_reason = "STREAM_ERROR:RESOURCE_EXHAUSTED"
                if False:
                    yield None
                return
            assert made[0].closed.is_set()
            assert not store.observe_provider_current(
                mint=MINT, price_usd="8", market_cap_usd="8000",
                observed_at="2026-07-16T00:00:02Z")
            self.closed.wait(timeout=2.0)
            if False:
                yield None

        def close(self):
            self.cancellation_requested = True
            self.closed.set()

        def diagnostic_snapshot(self):
            if self.number == 1:
                return {
                    "error_class": "_FakeRpcError",
                    "grpc_status_code": "RESOURCE_EXHAUSTED",
                    "sanitized_error_category": "RESOURCE_EXHAUSTED_UNSPECIFIED",
                    "sanitized_details": (
                        "Provider reported resource exhaustion without a safely classifiable detail."),
                    "stream_phase": "ITERATE",
                    "iterator_end_kind": "GRPC_ERROR",
                    "cancellation_requested": self.cancellation_requested,
                }
            return {
                "error_class": None,
                "grpc_status_code": None,
                "sanitized_error_category": None,
                "sanitized_details": None,
                "stream_phase": "ITERATE",
                "iterator_end_kind": "CANCELLED",
                "cancellation_requested": self.cancellation_requested,
            }

    def factory():
        source = Source(len(made) + 1)
        made.append(source)
        return source

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=factory, dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.02, reconnect_jitter_fraction=0,
        stale_after_seconds=30,
    )
    owner.start()
    deadline = time.time() + 2.0
    while owner.snapshot()["connect_attempts"] < 2 and time.time() < deadline:
        time.sleep(0.005)
    owner.stop(timeout_seconds=1.0)
    snapshot = owner.snapshot()
    assert snapshot["connect_attempts"] == 2
    assert snapshot["reconnects"] == 1
    assert snapshot["stream_errors"] == 1
    assert snapshot["provider_disconnects"] == 1
    assert snapshot["max_active_streams"] == 1
    assert snapshot["active_streams"] == 0
    first, second = snapshot["stream_attempts"]
    assert first["attempt_number"] == 1
    assert first["reconnect_reason"] == "PROVIDER_ERROR"
    assert first["reconnect_scheduled"] is True
    assert first["reconnect_delay_seconds"] == 0.02
    assert first["active_streams_before_cleanup"] == 1
    assert first["active_streams_after_cleanup"] == 0
    assert second["attempt_number"] == 2
    assert second["reconnect_reason"] == "OPERATOR_SHUTDOWN"
    assert second["reconnect_scheduled"] is False
    assert second["cancellation_requested"] is True
    assert ledger.read_bytes() == ledger_before
    restored = CentralAthStateStore(ath_dir)
    assert restored.snapshot(MINT)["ath_price"] == "10"
    assert (ath_dir / "ath_state_checkpoint.json").is_file()
    assert paid_provider_safety_error(snapshot, max_reconnects=0) == (
        "PAID_PROVIDER_RECONNECT_STORM")
    owner_source = inspect.getsource(SingleGrpcPumpSwapDiscovery).lower()
    assert "discord" not in owner_source
    assert "webhook" not in owner_source
    assert "ledger" not in owner_source


def test_auth_failure_has_one_attempt_and_no_reconnect():
    class Source:
        last_refusal_reason = "STREAM_ERROR:UNAUTHENTICATED"
        stream_started_epoch = None
        first_update_epoch = None
        last_update_epoch = None
        last_decoded_event_epoch = None

        def iter_events(self, *, max_events):
            if False:
                yield None

        def close(self):
            pass

        def diagnostic_snapshot(self):
            return {
                "error_class": "_FakeRpcError",
                "grpc_status_code": "UNAUTHENTICATED",
                "sanitized_error_category": "AUTHENTICATION_OR_PERMISSION_FAILURE",
                "sanitized_details": "The provider rejected authentication or permission.",
                "stream_phase": "ITERATE",
                "iterator_end_kind": "GRPC_ERROR",
                "cancellation_requested": False,
            }

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source, dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0)
    owner.start()
    deadline = time.time() + 1.0
    while owner.snapshot()["status"] != STREAM_STATUS_AUTH_FAILED and time.time() < deadline:
        time.sleep(0.005)
    snapshot = owner.snapshot()
    assert snapshot["status"] == STREAM_STATUS_AUTH_FAILED
    assert snapshot["connect_attempts"] == 1
    assert snapshot["reconnects"] == 0
    assert snapshot["stream_errors"] == 1
    assert snapshot["authentication_failures"] == 1
    assert snapshot["provider_disconnects"] == 0
    assert snapshot["stream_attempts"][0]["reconnect_scheduled"] is False


def test_watchdog_attempt_is_distinct_from_stream_error_and_never_overlaps():
    made = []

    class Source:
        last_refusal_reason = "NONE"
        last_update_epoch = None
        first_update_epoch = None
        last_decoded_event_epoch = None
        stream_started_epoch = None

        def __init__(self):
            self.closed = threading.Event()
            self.cancellation_requested = False
            made.append(self)

        def iter_events(self, *, max_events):
            self.closed.wait(timeout=2.0)
            if False:
                yield None

        def close(self):
            self.cancellation_requested = True
            self.closed.set()

        def diagnostic_snapshot(self):
            return {
                "error_class": None,
                "grpc_status_code": None,
                "sanitized_error_category": None,
                "sanitized_details": None,
                "stream_phase": "ITERATE",
                "iterator_end_kind": "CANCELLED",
                "cancellation_requested": self.cancellation_requested,
            }

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source, dedupe=ProviderCandidateDedupe(),
        stale_after_seconds=0.05, reconnect_backoff_seconds=0,
        reconnect_jitter_fraction=0)
    owner.start()
    deadline = time.time() + 1.0
    while owner.snapshot()["connect_attempts"] < 2 and time.time() < deadline:
        time.sleep(0.005)
    owner.stop(timeout_seconds=1.0)
    snapshot = owner.snapshot()
    assert snapshot["max_active_streams"] == 1
    assert snapshot["watchdog_reconnects"] == 1
    assert snapshot["stream_errors"] == 0
    first = snapshot["stream_attempts"][0]
    assert first["watchdog_trigger_kind"] == "LAST_MESSAGE_STALE"
    assert first["reconnect_reason"] == "WATCHDOG_STALE"
    assert first["cancellation_requested"] is True
    assert first["active_streams_after_cleanup"] == 0
    assert made[0].closed.is_set()
