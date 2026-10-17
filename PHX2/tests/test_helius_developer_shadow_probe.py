"""Deterministic tests for the bounded Helius Developer no-send/shadow proof."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer.liquidity_integrity import b58encode
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_PROGRAM_ID,
)
from PHX2.scripts.helius_developer_shadow_probe import run_offline_recall
from PHX2.shadow_probes import helius_developer as probe
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.tests.test_migration_admission import build_pool_creation_update


def _instruction_json(instruction) -> dict:
    payload = {
        "programIdIndex": instruction.program_id_index,
        "accounts": list(bytes(instruction.accounts)),
        "data": probe._b58encode(bytes(instruction.data)),
    }
    if hasattr(instruction, "stack_height"):
        payload["stackHeight"] = instruction.stack_height
    return payload


def _update_to_helius(update) -> dict:
    wrapper = update.transaction
    info = wrapper.transaction
    message = info.transaction.message
    meta = info.meta

    def balance_json(balance) -> dict:
        return {
            "accountIndex": balance.account_index,
            "owner": getattr(balance, "owner", None),
            "mint": getattr(balance, "mint", None),
            "uiTokenAmount": {
                "amount": balance.ui_token_amount.amount,
                "decimals": balance.ui_token_amount.decimals,
            },
        }

    signature = probe._b58encode(bytes(info.signature))
    return {
        "slot": int(wrapper.slot),
        "signature": signature,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    b58encode(bytes(value)) for value in message.account_keys
                ],
                "instructions": [
                    _instruction_json(value) for value in message.instructions
                ],
            },
        },
        "meta": {
            "err": (
                None if getattr(meta, "err", None) is None else {"failure": True}
            ),
            "logMessages": list(getattr(meta, "log_messages", ()) or ()),
            "loadedAddresses": {
                "writable": [
                    b58encode(bytes(value))
                    for value in (
                        getattr(meta, "loaded_writable_addresses", ()) or ()
                    )
                ],
                "readonly": [
                    b58encode(bytes(value))
                    for value in (
                        getattr(meta, "loaded_readonly_addresses", ()) or ()
                    )
                ],
            },
            "innerInstructions": [
                {
                    "index": group.index,
                    "instructions": [
                        _instruction_json(value) for value in group.instructions
                    ],
                }
                for group in (getattr(meta, "inner_instructions", ()) or ())
            ],
            "preTokenBalances": [
                balance_json(value)
                for value in (getattr(meta, "pre_token_balances", ()) or ())
            ],
            "postTokenBalances": [
                balance_json(value)
                for value in (getattr(meta, "post_token_balances", ()) or ())
            ],
        },
    }


def test_sanitized_env_loading_and_secret_repr(tmp_path: Path) -> None:
    key = "unit-test-key-never-print"
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            (
                f"HELIUS_API_KEY={key}",
                "HELIUS_RPC_URL=https://mainnet.helius-rpc.com/",
                "HELIUS_WS_URL=wss://mainnet.helius-rpc.com/",
                "HELIUS_GRPC_ENDPOINT=https://legacy.invalid/",
                "TELEGRAM_BOT_TOKEN=must-not-be-read",
            )
        ),
        encoding="utf-8",
    )
    config = probe.load_helius_probe_config(env_path=env, environ={})
    assert config.sanitized_presence() == {
        "HELIUS_API_KEY": "PRESENT",
        "HELIUS_RPC_URL": "PRESENT",
        "HELIUS_WS_URL": "PRESENT",
        "HELIUS_GRPC_ENDPOINT": "PRESENT_LEGACY_IGNORED",
    }
    assert key not in repr(config)
    assert key not in str(config.api_key)
    with pytest.raises(ValueError):
        probe.dataclass_to_sanitized_dict(config)


@pytest.mark.parametrize(
    ("base", "scheme"),
    (
        ("https://mainnet.helius-rpc.com/", "https"),
        ("wss://mainnet.helius-rpc.com/", "wss"),
    ),
)
def test_authenticated_url_construction_and_redaction(base: str, scheme: str) -> None:
    key = "secret-query-value"
    completed = probe.build_authenticated_url(
        base, key, expected_scheme=scheme
    )
    assert completed.endswith("api-key=" + key)
    redacted = probe.redact_url(completed)
    assert key not in redacted
    assert "?" not in redacted
    assert redacted == base
    message = probe.redact_text(
        f"failed at {completed} using {key}", secrets=(key,)
    )
    assert key not in message
    assert "api-key" not in message


@pytest.mark.parametrize(
    "unsafe",
    (
        "https://mainnet.helius-rpc.com/?api-key=embedded",
        "https://user:pass@mainnet.helius-rpc.com/",
        "http://mainnet.helius-rpc.com/",
    ),
)
def test_rpc_base_url_rejects_queries_userinfo_and_wrong_scheme(
    unsafe: str,
) -> None:
    with pytest.raises(probe.ProbeConfigurationError):
        probe.build_authenticated_url(
            unsafe, "key", expected_scheme="https"
        )


def test_transaction_subscribe_request_shapes() -> None:
    control = probe.build_transaction_subscribe_request(
        request_id=1, filter_label=probe.FILTER_CONTROL
    )
    tight = probe.build_transaction_subscribe_request(
        request_id=2, filter_label=probe.FILTER_TIGHT
    )
    assert control["method"] == "transactionSubscribe"
    assert control["params"][0] == {
        "failed": False,
        "vote": False,
        "accountInclude": [PUMPFUN_PROGRAM_ID],
    }
    assert tight["params"][0] == {
        "failed": False,
        "vote": False,
        "accountRequired": [PUMPFUN_PROGRAM_ID, PUMPSWAP_PROGRAM_ID],
    }
    assert control["params"][1] == {
        "commitment": "confirmed",
        "encoding": "jsonParsed",
        "transactionDetails": "full",
        "showRewards": False,
        "maxSupportedTransactionVersion": 0,
    }


def test_numeric_subscription_unsubscribe_and_rejection() -> None:
    assert (
        probe.validate_numeric_subscription_response(
            {"jsonrpc": "2.0", "id": 4, "result": 99}, request_id=4
        )
        == 99
    )
    with pytest.raises(probe.ProbeProtocolError):
        probe.validate_numeric_subscription_response(
            {"jsonrpc": "2.0", "id": 4, "result": True}, request_id=4
        )
    with pytest.raises(probe.ProbeProtocolError):
        probe.validate_numeric_subscription_response(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "error": {"code": -32602, "message": "rejected"},
            },
            request_id=4,
        )
    request = probe.build_transaction_unsubscribe_request(
        request_id=5, subscription_id=99
    )
    assert request["method"] == "transactionUnsubscribe"
    assert request["params"] == [99]
    assert probe.validate_unsubscribe_response(
        {"jsonrpc": "2.0", "id": 5, "result": True}, request_id=5
    )


class _FakeWebSocket:
    def __init__(self, responses=()) -> None:
        self.responses = list(responses)
        self.sent = []
        self.ping_count = 0

    async def send(self, value: str) -> None:
        self.sent.append(json.loads(value))

    async def recv(self) -> str:
        return json.dumps(self.responses.pop(0))

    async def ping(self):
        self.ping_count += 1
        future = asyncio.get_running_loop().create_future()
        future.set_result(None)
        return future


def test_keepalive_ping_and_reconnect_resubscribe_use_fresh_ids() -> None:
    async def exercise() -> None:
        websocket = _FakeWebSocket(
            (
                {"jsonrpc": "2.0", "id": 101, "result": 11},
                {"jsonrpc": "2.0", "id": 102, "result": 12},
                {"jsonrpc": "2.0", "id": 201, "result": 21},
                {"jsonrpc": "2.0", "id": 202, "result": 22},
            )
        )
        await probe.send_keepalive(websocket)
        first, first_pending = await probe._subscribe_pair(
            websocket, generation=1
        )
        second, second_pending = await probe._subscribe_pair(
            websocket, generation=2
        )
        assert websocket.ping_count == 1
        assert first == {11: probe.FILTER_CONTROL, 12: probe.FILTER_TIGHT}
        assert second == {21: probe.FILTER_CONTROL, 22: probe.FILTER_TIGHT}
        assert first_pending == ()
        assert second_pending == ()
        assert set(first).isdisjoint(second)
        assert [item["id"] for item in websocket.sent] == [101, 102, 201, 202]

    asyncio.run(exercise())


def test_keepalive_timeout_fails_closed() -> None:
    class NeverPongWebSocket:
        async def ping(self):
            return asyncio.get_running_loop().create_future()

    async def exercise() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await probe.send_keepalive(
                NeverPongWebSocket(), timeout_seconds=0.001
            )

    asyncio.run(exercise())


def test_subscribe_pair_retains_interleaved_notification() -> None:
    async def exercise() -> None:
        notification = {
            "jsonrpc": "2.0",
            "method": "transactionNotification",
            "params": {"subscription": 11, "result": {}},
        }
        websocket = _FakeWebSocket(
            (
                {"jsonrpc": "2.0", "id": 102, "result": 12},
                notification,
                {"jsonrpc": "2.0", "id": 101, "result": 11},
            )
        )
        mapping, pending = await probe._subscribe_pair(
            websocket, generation=1
        )
        assert mapping == {11: probe.FILTER_CONTROL, 12: probe.FILTER_TIGHT}
        assert len(pending) == 1
        assert json.loads(pending[0]) == notification

    asyncio.run(exercise())


def test_duplicate_migration_notification_is_idempotent_for_recall_set() -> None:
    metrics = probe.FilterMetrics()
    classification = probe.LocalClassification(
        classification=probe.CLASS_MIGRATE_V2,
        reject_reason=None,
        slot=123,
        signature_hash="0123456789abcdef0123",
    )
    metrics.record(raw_bytes=100, classification=classification)
    metrics.record(raw_bytes=100, classification=classification)
    assert metrics.notifications == 2
    assert metrics.migrate_v2 == 2
    assert metrics.migration_signature_hashes == {"0123456789abcdef0123"}


def test_offline_control_and_tight_recall_across_authoritative_matrix() -> None:
    report = run_offline_recall()
    assert report["authoritative_valid_migrations"] == 8
    assert report["control_valid_recall_percent"] == 100
    assert report["tight_valid_recall_percent"] == 100
    assert report["tight_approved_offline"] is True
    rows = {row["source_fixture"]: row for row in report["fixtures"]}
    assert rows["synthetic_migrate_legacy_inner"]["local_decoder_result"] == (
        MIGRATION_VERSION_V1
    )
    assert rows["synthetic_migrate_v2_v0_loaded_addresses"][
        "local_decoder_result"
    ] == MIGRATION_VERSION_V2
    assert rows["failed_migration_excluded"]["control_match"] is False
    assert rows["vote_transaction_excluded"]["tight_match"] is False
    assert rows["direct_pool_creation_not_migration"][
        "local_decoder_result"
    ] == probe.CLASS_DECODE_FAILURE


@pytest.mark.parametrize(
    ("migrate_v2", "loaded", "expected"),
    (
        (False, False, MIGRATION_VERSION_V1),
        (True, False, MIGRATION_VERSION_V2),
        (True, True, MIGRATION_VERSION_V2),
    ),
)
def test_helius_json_adapter_preserves_decoder_parity(
    migrate_v2: bool, loaded: bool, expected: str
) -> None:
    kwargs = {"use_loaded_addresses": loaded}
    if migrate_v2:
        kwargs["migrate_discriminator"] = (
            PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR
        )
    original = build_pool_creation_update(**kwargs)
    original_result = probe.classify_decoder_update(original)
    envelope = _update_to_helius(original)
    adapted = probe.helius_envelope_to_decoder_update(envelope)
    adapted_result = probe.classify_decoder_update(adapted)
    assert original_result.classification == expected
    assert adapted_result.classification == expected
    assert adapted_result.slot == original_result.slot
    assert adapted_result.signature == original_result.signature
    assert adapted_result.signature_hash == original_result.signature_hash


def test_malformed_missing_meta_fails_closed() -> None:
    result = probe.classify_helius_envelope(
        {"slot": 1, "signature": "11111111111111111111111111111111"}
    )
    assert result.classification == probe.CLASS_DECODE_FAILURE
    assert result.reject_reason == "transaction or meta is missing"


def test_uncompressed_byte_accounting_and_credit_calculation() -> None:
    raw = '{"snowman":"☃"}'
    expected = len(raw.encode("utf-8"))
    assert probe.uncompressed_json_bytes(raw) == expected
    assert probe.estimated_stream_credits(100_000) == 2
    assert probe.billing_granule_upper_bound(100_001) == 4
    assert probe.gtfa_full_credits(0) == 10
    assert probe.gtfa_full_credits(100) == 10
    assert probe.gtfa_full_credits(101) == 20
    projection = probe.project_credits(
        byte_count=100_000, elapsed_seconds=60
    )
    assert projection["credits_per_minute"] == 2
    assert projection["projected_credits_per_30_days"] == 86_400


def test_slot_bounded_request_and_pagination_contract() -> None:
    first = probe.build_slot_bounded_gtfa_request(
        request_id=7,
        address=PUMPFUN_PROGRAM_ID,
        slot_gte=100,
        slot_lte=102,
        limit=25,
    )
    options = first["params"][1]
    assert first["method"] == "getTransactionsForAddress"
    assert options["sortOrder"] == "asc"
    assert options["filters"] == {
        "slot": {"gte": 100, "lte": 102},
        "status": "succeeded",
        "tokenAccounts": "none",
    }
    assert options["transactionDetails"] == "full"
    assert options["maxSupportedTransactionVersion"] == 0
    next_page = probe.build_slot_bounded_gtfa_request(
        request_id=8,
        address=PUMPFUN_PROGRAM_ID,
        slot_gte=100,
        slot_lte=102,
        limit=25,
        pagination_token="102:5",
    )
    assert next_page["params"][1]["paginationToken"] == "102:5"


def test_wrong_slot_rejection_empty_range_and_duplicate_idempotence() -> None:
    response = {
        "jsonrpc": "2.0",
        "id": 9,
        "result": {
            "data": [
                {"slot": 100, "signature": "sig-a", "transactionIndex": 1},
                {"slot": 101, "signature": "sig-b", "transactionIndex": 2},
                {"slot": 999, "signature": "sig-out", "transactionIndex": 3},
            ],
            "paginationToken": None,
        },
    }
    accepted, rejected, token = probe.validate_gtfa_page(
        response, request_id=9, slot_gte=100, slot_lte=101
    )
    assert len(accepted) == 2
    assert rejected == 1
    assert token is None
    unique, duplicates = probe.dedupe_recovery_entries(
        [accepted[0], accepted[0], accepted[1]]
    )
    assert [item["signature"] for item in unique] == ["sig-a", "sig-b"]
    assert duplicates == 1
    empty, rejected_empty, token_empty = probe.validate_gtfa_page(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "result": {"data": [], "paginationToken": None},
        },
        request_id=10,
        slot_gte=0,
        slot_lte=0,
    )
    assert empty == []
    assert rejected_empty == 0
    assert token_empty is None


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (401, probe.AUTH_FAILURE),
        (403, probe.PLAN_FORBIDDEN),
        (429, probe.RATE_LIMITED),
    ),
)
def test_http_failure_classification(status: int, expected: str) -> None:
    assert probe._provider_error_classification(status=status) == expected


def test_no_production_transport_or_runtime_evidence_surface() -> None:
    source = inspect.getsource(probe)
    forbidden = (
        "telegram_transport",
        "TelegramTransport",
        "discord_transport",
        "production_entrypoint",
        "production_supervisor",
        "phx2_paid_primary_runtime",
        "ping_dedupe.jsonl",
    )
    for token in forbidden:
        assert token not in source


def test_pure_helpers_do_not_mutate_sentinel_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ping_dedupe.jsonl"
    ledger.write_bytes(b"sentinel-ledger\n")
    before = ledger.read_bytes()
    probe.build_transaction_subscribe_request(
        request_id=1, filter_label=probe.FILTER_CONTROL
    )
    probe.build_slot_bounded_gtfa_request(
        request_id=2,
        address=PUMPFUN_PROGRAM_ID,
        slot_gte=1,
        slot_lte=1,
        limit=1,
    )
    probe.project_credits(byte_count=1_000, elapsed_seconds=10)
    assert ledger.read_bytes() == before
