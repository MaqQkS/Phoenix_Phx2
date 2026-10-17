"""Deterministic tests for the no-send Helius Enhanced WSS source."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import helius_source as source
from PHX2.free_tier_producer import source_continuity as continuity
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_PROGRAM_ID,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.tests.test_helius_developer_shadow_probe import _update_to_helius
from PHX2.tests.test_migration_admission import build_pool_creation_update


def _config(**overrides):
    values = {
        "HELIUS_API_KEY": "unit-test-secret",
        "HELIUS_RPC_URL": "https://mainnet.helius-rpc.com/",
        "HELIUS_WS_URL": "wss://mainnet.helius-rpc.com/",
    }
    return source.load_helius_source_config(
        environ=values,
        reconnect_backoff_seconds=(0.0,),
        **overrides,
    )


def _notification(
    *,
    subscription_id: int = 77,
    slot: int = 123,
    signature_byte: int = 7,
    migrate_v2: bool = False,
    loaded: bool = False,
    failed: bool = False,
) -> dict:
    kwargs = {
        "use_loaded_addresses": loaded,
        "failed": failed,
    }
    if migrate_v2:
        kwargs["migrate_discriminator"] = (
            PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR
        )
    update = build_pool_creation_update(**kwargs)
    update.transaction.slot = slot
    update.transaction.transaction.signature = bytes([signature_byte]) * 64
    return {
        "jsonrpc": "2.0",
        "method": "transactionNotification",
        "params": {
            "subscription": subscription_id,
            "result": _update_to_helius(update),
        },
    }


class _FakeWebSocket:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.sent = []
        self.pings = 0
        self.closed = False

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self):
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)

    async def ping(self):
        self.pings += 1
        future = asyncio.get_running_loop().create_future()
        future.set_result(None)
        return future

    async def close(self) -> None:
        self.closed = True


class _Connection:
    def __init__(self, websocket=None, error=None) -> None:
        self.websocket = websocket
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.websocket

    async def __aexit__(self, *_args):
        return False


class _ConnectSequence:
    def __init__(self, *connections) -> None:
        self.connections = list(connections)
        self.urls = []
        self.kwargs = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        self.kwargs.append(kwargs)
        return self.connections.pop(0)


def _source(
    *,
    tracker=None,
    gap_recoverer=None,
    recovery_observer=None,
    connect_fn=None,
    **config_overrides,
):
    return source.HeliusEnhancedWssSource(
        config=_config(**config_overrides),
        continuity=tracker,
        gap_recoverer=gap_recoverer,
        recovery_observer=recovery_observer,
        connect_fn=connect_fn,
        now_fn=lambda: "2026-07-29T12:00:00Z",
        sleep_fn=lambda _seconds: asyncio.sleep(0),
    )


def test_configuration_loading_redaction_and_query_refusal(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            (
                "HELIUS_API_KEY=unit-test-secret",
                "HELIUS_RPC_URL=https://mainnet.helius-rpc.com/",
                "HELIUS_WS_URL=wss://mainnet.helius-rpc.com/",
                "TELEGRAM_BOT_TOKEN=must-not-be-read",
            )
        ),
        encoding="utf-8",
    )
    config = source.load_helius_source_config(env_path=env, environ={})
    assert "unit-test-secret" not in repr(config)
    assert str(config.api_key) == "<REDACTED>"
    assert config.sanitized_presence() == {
        "HELIUS_API_KEY": "PRESENT",
        "HELIUS_RPC_URL": "PRESENT",
        "HELIUS_WS_URL": "PRESENT",
    }
    with pytest.raises(source.HeliusSourceConfigurationError):
        source.load_helius_source_config(
            environ={
                "HELIUS_API_KEY": "secret",
                "HELIUS_RPC_URL": (
                    "https://mainnet.helius-rpc.com/?api-key=secret"
                ),
                "HELIUS_WS_URL": "wss://mainnet.helius-rpc.com/",
            }
        )


def test_total_byte_ceiling_stops_before_accounting_overflow() -> None:
    instance = _source(max_total_raw_bytes=1)
    result = instance._decode_notification(
        json.dumps(_notification()),
        subscription_id=77,
    )
    assert result is None
    assert instance.metrics.notification_bytes == 0
    assert instance.metrics.byte_ceiling_reached is True
    assert instance.metrics.byte_ceiling_notification_discarded is True
    assert instance._closed.is_set()


def test_source_selection_closed_set_excludes_retired_helius_shadow_mode() -> None:
    with pytest.raises(source.HeliusSourceConfigurationError):
        source.load_source_selection({})
    primary = source.load_source_selection(
        {source.MIGRATION_SOURCE_ENV: source.CHAINSTACK_PRIMARY}
    )
    with pytest.raises(source.HeliusSourceConfigurationError):
        source.load_source_selection(
            {source.MIGRATION_SOURCE_ENV: source.HELIUS_SHADOW}
        )
    future = source.load_source_selection(
        {source.MIGRATION_SOURCE_ENV: source.HELIUS_PRIMARY}
    )
    assert primary.mode == source.CHAINSTACK_PRIMARY
    future.require_launcher_ready()


def test_approved_subscription_is_exact_tight_filter() -> None:
    request = source.approved_tight_subscription_request(41)
    assert request == {
        "jsonrpc": "2.0",
        "id": 41,
        "method": "transactionSubscribe",
        "params": [
            {
                "failed": False,
                "vote": False,
                "accountRequired": [
                    PUMPFUN_PROGRAM_ID,
                    PUMPSWAP_PROGRAM_ID,
                ],
            },
            {
                "commitment": "confirmed",
                "encoding": "jsonParsed",
                "transactionDetails": "full",
                "showRewards": False,
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }


def test_connect_subscribe_numeric_id_decode_and_unsubscribe() -> None:
    websocket = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 77},
            _notification(subscription_id=77),
            {"jsonrpc": "2.0", "id": 2, "result": True},
        )
    )
    connect = _ConnectSequence(_Connection(websocket))
    adapter = _source(connect_fn=connect)
    events = list(adapter.iter_events(max_events=1))
    assert len(events) == 1
    assert events[0].provider_name == source.HELIUS_SOURCE_IDENTITY
    assert events[0].event_type == "migration"
    assert events[0].provider_event_id == adapter.last_event_signature
    assert adapter.last_event_slot == 123
    assert adapter.last_event_context is not None
    assert adapter.last_event_context.source_slot == 123
    assert adapter.last_event_context.source_identity == (
        source.HELIUS_SOURCE_IDENTITY
    )
    assert adapter.last_migration_type == MIGRATION_VERSION_V1
    assert [request["method"] for request in websocket.sent] == [
        "transactionSubscribe",
        "transactionUnsubscribe",
    ]
    assert connect.kwargs[0]["ping_interval"] is None
    assert "unit-test-secret" in connect.urls[0]
    assert "unit-test-secret" not in repr(adapter._config)


def test_unsubscribe_waits_past_interleaved_notification() -> None:
    websocket = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 77},
            _notification(subscription_id=77),
            _notification(
                subscription_id=77,
                slot=124,
                signature_byte=31,
            ),
            {"jsonrpc": "2.0", "id": 2, "result": True},
        )
    )
    adapter = _source(
        connect_fn=_ConnectSequence(_Connection(websocket)),
    )
    assert len(list(adapter.iter_events(max_events=1))) == 1
    assert [request["method"] for request in websocket.sent] == [
        "transactionSubscribe",
        "transactionUnsubscribe",
    ]
    assert websocket.responses == []


def test_bounded_batch_boundary_arms_exact_next_subscription_gap() -> None:
    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-29T12:00:00Z"
    )
    websocket = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 77},
            _notification(subscription_id=77, slot=123),
            {"jsonrpc": "2.0", "id": 2, "result": True},
        )
    )
    adapter = _source(
        tracker=tracker,
        connect_fn=_ConnectSequence(_Connection(websocket)),
    )
    assert len(list(adapter.iter_events(max_events=1))) == 1
    gap = tracker.note_slot(125)
    assert gap is not None
    assert (gap.gap_from_slot, gap.gap_to_slot) == (124, 124)


def test_graceful_operator_close_does_not_claim_downtime_coverage() -> None:
    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-29T12:00:00Z"
    )
    tracker.note_slot(100, processed=True, durable=True)
    adapter = _source(tracker=tracker)
    adapter.request_graceful_close()
    assert list(adapter.iter_events(max_events=1)) == []
    assert tracker.note_slot(200) is None


def test_failure_close_arms_reconnect_gap() -> None:
    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-29T12:00:00Z"
    )
    tracker.note_slot(100, processed=True, durable=True)
    adapter = _source(tracker=tracker)
    adapter.close()
    gap = tracker.note_slot(102)
    assert gap is not None
    assert (gap.gap_from_slot, gap.gap_to_slot) == (101, 101)


def test_loaded_addresses_and_versioned_migrate_v2_are_preserved() -> None:
    adapter = _source()
    raw = json.dumps(
        _notification(
            subscription_id=9,
            slot=222,
            signature_byte=8,
            migrate_v2=True,
            loaded=True,
        )
    )
    event = adapter._decode_notification(raw, subscription_id=9)
    assert event is not None
    assert adapter.last_migration_type == MIGRATION_VERSION_V2
    assert adapter.last_event_context is not None
    assert len(adapter.last_event_context.loaded_addresses) > 0
    assert adapter.metrics.migrate_v2 == 1


def test_failed_transaction_malformed_and_wrong_subscription_fail_closed() -> None:
    adapter = _source()
    failed = adapter._decode_notification(
        json.dumps(
            _notification(
                subscription_id=3,
                signature_byte=10,
                failed=True,
            )
        ),
        subscription_id=3,
    )
    malformed = adapter._decode_notification("{", subscription_id=3)
    wrong = adapter._decode_notification(
        json.dumps(_notification(subscription_id=4, signature_byte=11)),
        subscription_id=3,
    )
    assert failed is None
    assert malformed is None
    assert wrong is None
    assert adapter.metrics.decoder_rejections == 1
    assert adapter.metrics.malformed_notifications == 1
    assert adapter.metrics.wrong_subscription_notifications == 1


def test_non_migration_is_rejected_and_emits_sanitized_decoder_evidence() -> None:
    observed = []
    adapter = source.HeliusEnhancedWssSource(
        config=_config(),
        decoder_observer=observed.append,
        now_fn=lambda: "2026-07-29T12:00:00Z",
    )
    update = build_pool_creation_update()
    update.transaction.slot = 333
    update.transaction.transaction.signature = bytes([19]) * 64
    message = update.transaction.transaction.transaction.message
    meta = update.transaction.transaction.meta
    message.instructions = [
        SimpleNamespace(
            program_id_index=0,
            accounts=b"",
            data=b"ordinary",
        )
    ]
    meta.inner_instructions = []
    raw = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "transactionNotification",
            "params": {
                "subscription": 8,
                "result": _update_to_helius(update),
            },
        }
    )
    assert adapter._decode_notification(raw, subscription_id=8) is None
    assert adapter.metrics.non_migrations_rejected == 1
    assert len(observed) == 1
    assert observed[0]["local_decoder_verdict"] == "REJECTED"
    assert observed[0]["rejection_reason"] == "NOT_MIGRATION"
    assert observed[0]["migration_comparison_scope"] is False
    assert observed[0]["slot"] == 333
    assert "transaction" not in observed[0]
    assert "meta" not in observed[0]
    assert "unit-test-secret" not in repr(observed[0])


def test_signature_dedupe_is_exact_and_idempotent() -> None:
    adapter = _source()
    raw = json.dumps(_notification(subscription_id=5, signature_byte=12))
    assert adapter._decode_notification(raw, subscription_id=5) is not None
    assert adapter._decode_notification(raw, subscription_id=5) is None
    assert adapter.metrics.migrations_yielded == 1
    assert adapter.metrics.duplicate_signatures == 1


def test_reconnect_resubscribes_with_fresh_id_and_opens_one_slot_gap() -> None:
    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-29T12:00:00Z"
    )
    first = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 51},
            _notification(
                subscription_id=51,
                slot=100,
                signature_byte=13,
            ),
            OSError("disconnect"),
        )
    )
    second = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 2, "result": 52},
            _notification(
                subscription_id=52,
                slot=102,
                signature_byte=14,
            ),
            {"jsonrpc": "2.0", "id": 3, "result": True},
        )
    )
    connect = _ConnectSequence(_Connection(first), _Connection(second))
    adapter = _source(
        tracker=tracker,
        connect_fn=connect,
        max_reconnects=1,
    )
    events = list(adapter.iter_events(max_events=2))
    assert len(events) == 2
    assert adapter.metrics.reconnects == 1
    assert first.sent[0]["id"] == 1
    assert second.sent[0]["id"] == 2
    snapshot = tracker.snapshot()
    assert snapshot["continuity_state"] == continuity.GAP_DETECTED
    assert snapshot["gap_from_slot"] == 101
    assert snapshot["gap_to_slot"] == 101
    gap = tracker.open_gaps()[0]
    assert gap.expected_next_slot == 101
    assert gap.first_post_reconnect_slot == 102


def test_reconnect_gap_invokes_separate_http_recoverer() -> None:
    class FakeRecoverer:
        def __init__(self) -> None:
            self.calls = []

        def recover(self, **kwargs):
            self.calls.append(kwargs)
            return type("Outcome", (), {"coverage_status": "PARTIAL"})()

    tracker = continuity.SourceContinuityTracker()
    first = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 71},
            _notification(
                subscription_id=71,
                slot=200,
                signature_byte=17,
            ),
            OSError("disconnect"),
        )
    )
    second = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 2, "result": 72},
            _notification(
                subscription_id=72,
                slot=202,
                signature_byte=18,
            ),
            {"jsonrpc": "2.0", "id": 3, "result": True},
        )
    )
    fake_recoverer = FakeRecoverer()
    observed_recoveries = []
    adapter = _source(
        tracker=tracker,
        gap_recoverer=fake_recoverer,
        recovery_observer=observed_recoveries.append,
        connect_fn=_ConnectSequence(
            _Connection(first),
            _Connection(second),
        ),
        max_reconnects=1,
    )
    assert len(list(adapter.iter_events(max_events=2))) == 2
    assert len(fake_recoverer.calls) == 1
    assert fake_recoverer.calls[0]["gap_from_slot"] == 201
    assert fake_recoverer.calls[0]["gap_to_slot"] == 201
    assert adapter.diagnostic_snapshot()["last_recovery_status"] == "PARTIAL"
    assert observed_recoveries == [adapter.last_recovery_outcome]


def test_keepalive_ping_then_notification() -> None:
    websocket = _FakeWebSocket(
        (
            {"jsonrpc": "2.0", "id": 1, "result": 61},
            asyncio.TimeoutError(),
            _notification(subscription_id=61, signature_byte=15),
            {"jsonrpc": "2.0", "id": 2, "result": True},
        )
    )
    adapter = _source(
        connect_fn=_ConnectSequence(_Connection(websocket)),
    )
    assert len(list(adapter.iter_events(max_events=1))) == 1
    assert websocket.pings == 1
    assert adapter.metrics.keepalive_pings == 1


def test_byte_and_credit_telemetry_are_exposed() -> None:
    adapter = _source()
    raw = json.dumps(_notification(subscription_id=7, signature_byte=16))
    assert adapter._decode_notification(raw, subscription_id=7) is not None
    metrics = adapter.metrics.snapshot()
    assert metrics["notification_bytes"] == len(raw.encode("utf-8"))
    assert metrics["estimated_credits"] > 0
    assert metrics["notifications_received"] == 1


def test_shadow_source_has_no_delivery_or_ledger_ownership_surface() -> None:
    text = inspect.getsource(source).lower()
    forbidden_imports = (
        "import telegram",
        "telegram_transport",
        "telegram_adapter",
        "delivery_transaction",
        "ping_dedupe.jsonl",
        "reserve_delivery",
        "commit_delivery",
    )
    for token in forbidden_imports:
        assert token not in text
