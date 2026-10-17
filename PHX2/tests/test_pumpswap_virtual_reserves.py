"""Offline compatibility and fail-closed proofs for PumpSwap virtual reserves."""

from __future__ import annotations

import base64
from decimal import Decimal
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer.compat.production_live_artifacts import art
from PHX2.free_tier_producer.paid_grpc_source import (
    _base58_decode,
    extract_create_pool_quartet,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    BUY_LAYOUT_BOOST,
    BUY_LAYOUT_LEGACY,
    BUY_LAYOUT_VIRTUAL,
    I128_MAX,
    POOL_LAYOUT_LEGACY,
    POOL_LAYOUT_VIRTUAL,
    PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR,
    RESERVE_COMPARISON_DISCREPANCY,
    SELL_LAYOUT_BOOST,
    SELL_LAYOUT_LEGACY,
    SELL_LAYOUT_VIRTUAL,
    U64_MAX,
    PumpSwapReserveArtifact,
    PumpSwapReserveError,
    PumpSwapReserveIndex,
    buy_quote_input_raw,
    decode_buy_event,
    decode_pool_account,
    decode_sell_event,
    effective_quote_reserves,
    ingest_reserve_events_from_update,
    _program_data_payloads_with_context,
    reserve_liquidity_usd,
    reserve_market_cap_usd,
    reserve_price_usd,
    sell_quote_output_raw,
)
from PHX2.paper_trading.pricing import normalize_record
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_PROGRAM_ID,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    WRAPPED_SOL_MINT,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "D" * 44
OBSERVED = "2026-07-15T12:00:00Z"
CREATE_POOL_DISCRIMINATOR = bytes((233, 146, 209, 142, 207, 104, 64, 188))


def _u64(value: int) -> bytes:
    return value.to_bytes(8, "little", signed=False)


def _i64(value: int) -> bytes:
    return value.to_bytes(8, "little", signed=True)


def _i128(value: int) -> bytes:
    return value.to_bytes(16, "little", signed=True)


def _pubkey(seed: int) -> bytes:
    return bytes((seed,)) * 32


def _pool_account(*, virtual: int | None) -> bytes:
    body = bytearray(PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR)
    body.extend(b"\x01")
    body.extend((7).to_bytes(2, "little"))
    for seed in range(1, 7):
        body.extend(_pubkey(seed))
    body.extend(_u64(123))
    body.extend(_pubkey(7))
    body.extend(b"\x00\x01")
    if virtual is not None:
        body.extend(_i128(virtual))
    return bytes(body)


def _event_tail(kind: str, virtual: int) -> bytes:
    if kind == "legacy":
        return b""
    if kind == "virtual":
        return _i128(virtual)
    if kind == "boost":
        return _u64(3) + _u64(4) + _i128(virtual) + b"\x01" + _u64(1_000_000)
    raise AssertionError(kind)


def _buy_event(*, raw_quote: int = 100, base: int = 200,
               virtual: int = 0, kind: str = "legacy") -> bytes:
    body = bytearray(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES)
    body.extend(_i64(1_752_580_800))
    values = [10, 20, 30, 40, base, raw_quote] + [1] * 7
    for value in values:
        body.extend(_u64(value))
    for seed in range(8, 15):
        body.extend(_pubkey(seed))
    body.extend(_u64(1) + _u64(2))
    body.extend(b"\x01")
    body.extend(_u64(1) + _u64(2) + _u64(3) + _i64(4) + _u64(5))
    name = b"buy"
    body.extend(len(name).to_bytes(4, "little") + name)
    body.extend(_u64(6) + _u64(7))
    body.extend(_event_tail(kind, virtual))
    return bytes(body)


def _sell_event(*, raw_quote: int = 100, base: int = 200,
                virtual: int = 0, kind: str = "legacy") -> bytes:
    body = bytearray(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES)
    body.extend(_i64(1_752_580_800))
    values = [10, 20, 30, 40, base, raw_quote] + [1] * 7
    for value in values:
        body.extend(_u64(value))
    for seed in range(8, 15):
        body.extend(_pubkey(seed))
    for value in (1, 2, 3, 4):
        body.extend(_u64(value))
    body.extend(_event_tail(kind, virtual))
    return bytes(body)


def _artifact(*, raw: int, virtual: int, base: int = 100,
              supply: int | None = 1_000) -> PumpSwapReserveArtifact:
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw,
        virtual_quote_reserves=virtual,
        effective_quote_reserves=effective_quote_reserves(raw, virtual),
        base_reserves=base,
        reserve_source="TEST_EVENT",
        observation_timestamp=OBSERVED,
        decoder_layout_version="TEST_LAYOUT",
        pool_address=POOL,
        base_mint=MINT,
        quote_mint=WRAPPED_SOL_MINT,
        base_decimals=0,
        quote_decimals=0,
        base_supply=supply,
    )


def test_virtual_zero_preserves_price_market_cap_liquidity_and_quotes_exactly():
    artifact = _artifact(raw=100, virtual=0, base=200, supply=1_000)
    assert artifact.effective_quote_reserves == 100
    assert reserve_price_usd(artifact, quote_price_usd="2") == Decimal("1.0")
    assert reserve_market_cap_usd(artifact, quote_price_usd="2") == Decimal("1000.0")
    assert reserve_liquidity_usd(artifact, quote_price_usd="2") == Decimal("400")
    assert buy_quote_input_raw(artifact, base_amount_out_raw=20) == Decimal(100) / Decimal(9)
    assert sell_quote_output_raw(artifact, base_amount_in_raw=20) == Decimal(100) / Decimal(11)


def test_positive_virtual_reserves_raise_every_effective_metric():
    raw_only_equivalent = _artifact(raw=100, virtual=0)
    boosted = _artifact(raw=100, virtual=100)
    assert boosted.effective_quote_reserves == 200
    assert reserve_price_usd(boosted, quote_price_usd=1) == (
        reserve_price_usd(raw_only_equivalent, quote_price_usd=1) * 2)
    assert reserve_market_cap_usd(boosted, quote_price_usd=1) == (
        reserve_market_cap_usd(raw_only_equivalent, quote_price_usd=1) * 2)
    assert reserve_liquidity_usd(boosted, quote_price_usd=1) == (
        reserve_liquidity_usd(raw_only_equivalent, quote_price_usd=1) * 2)


def test_old_and_new_pool_layouts_are_exact_and_preserve_raw_virtual_effective():
    old = decode_pool_account(
        _pool_account(virtual=None), raw_quote_vault_balance=100,
        raw_base_vault_balance=200, observation_timestamp=OBSERVED)
    assert old.decoder_layout_version == POOL_LAYOUT_LEGACY
    assert (old.raw_quote_reserves, old.virtual_quote_reserves,
            old.effective_quote_reserves) == (100, 0, 100)

    new = decode_pool_account(
        _pool_account(virtual=-25), raw_quote_vault_balance=100,
        raw_base_vault_balance=200, observation_timestamp=OBSERVED)
    assert new.decoder_layout_version == POOL_LAYOUT_VIRTUAL
    assert (new.raw_quote_reserves, new.virtual_quote_reserves,
            new.effective_quote_reserves) == (100, -25, 75)


@pytest.mark.parametrize("decoder,builder,layouts", [
    (decode_buy_event, _buy_event,
     (BUY_LAYOUT_LEGACY, BUY_LAYOUT_VIRTUAL, BUY_LAYOUT_BOOST)),
    (decode_sell_event, _sell_event,
     (SELL_LAYOUT_LEGACY, SELL_LAYOUT_VIRTUAL, SELL_LAYOUT_BOOST)),
])
def test_old_virtual_and_current_event_layouts_never_shift_existing_fields(
    decoder, builder, layouts
):
    artifacts = [
        decoder(builder(kind="legacy", raw_quote=100, base=200)),
        decoder(builder(kind="virtual", virtual=25, raw_quote=100, base=200)),
        decoder(builder(kind="boost", virtual=25, raw_quote=100, base=200)),
    ]
    assert [artifact.decoder_layout_version for artifact in artifacts] == list(layouts)
    assert [artifact.raw_quote_reserves for artifact in artifacts] == [100, 100, 100]
    assert [artifact.base_reserves for artifact in artifacts] == [200, 200, 200]
    assert [artifact.virtual_quote_reserves for artifact in artifacts] == [0, 25, 25]
    assert artifacts[2].base_supply == 1_000_000


def test_malformed_lengths_negative_effective_and_overflow_fail_closed():
    with pytest.raises(PumpSwapReserveError, match="length_unknown"):
        decode_pool_account(
            _pool_account(virtual=None) + b"\x00", raw_quote_vault_balance=1,
            raw_base_vault_balance=1, observation_timestamp=OBSERVED)
    with pytest.raises(PumpSwapReserveError, match="suffix_length_unknown"):
        decode_buy_event(_buy_event(kind="legacy") + b"\x00")
    with pytest.raises(PumpSwapReserveError, match="not_positive"):
        effective_quote_reserves(10, -10)
    with pytest.raises(PumpSwapReserveError, match="overflow"):
        effective_quote_reserves(U64_MAX, I128_MAX)
    with pytest.raises(PumpSwapReserveError, match="not_positive"):
        decode_sell_event(_sell_event(raw_quote=10, virtual=-11, kind="virtual"))


def test_raw_only_artifacts_cannot_be_used_for_price_or_paper_fallback():
    with pytest.raises(PumpSwapReserveError, match="validated_reserve_artifact_required"):
        reserve_price_usd({"raw_quote_reserves": 100}, quote_price_usd=1)  # type: ignore[arg-type]
    raw_only_record = {
        "token_mint": MINT,
        "observed_at_utc": OBSERVED,
        "raw_quote_reserves": "100",
        "base_reserves": "200",
    }
    assert normalize_record(raw_only_record).price_usd is None


def test_paper_fallback_accepts_only_central_effective_metrics_and_primary_wins():
    artifact = _artifact(raw=100, virtual=100)
    telemetry = {
        "reserve_validation_status": "VALID",
        "reserve_artifact": artifact.to_dict(),
        "effective_reserve_price_usd": "2",
        "effective_reserve_market_cap_usd": "2000",
        "effective_reserve_liquidity_usd": "400",
        "effective_reserve_ath_market_cap_usd": "2500",
        "effective_reserve_drawdown_pct": "20",
    }
    reserve_only = normalize_record({
        "token_mint": MINT, "observed_at_utc": OBSERVED,
        "pumpswap_reserve": telemetry,
    })
    assert reserve_only.price_usd == 2
    assert reserve_only.market_cap_usd == 2000
    assert reserve_only.liquidity_usd == 400
    assert reserve_only.drawdown_pct == 20
    assert reserve_only.extra["price_provenance"] == "EFFECTIVE_PUMPSWAP_RESERVES"

    primary = normalize_record({
        "token_mint": MINT, "observed_at_utc": OBSERVED,
        "current_price": "3", "pumpswap_reserve": telemetry,
    })
    assert primary.price_usd == 3
    assert primary.extra["price_provenance"] == "PRIMARY_MARKET"


def test_candidate_artifact_preserves_complete_reserve_contract():
    compat_dir = Path(__file__).resolve().parents[1] / "free_tier_producer" / "compat"
    sys.path.insert(0, str(compat_dir))
    try:
        import build30_artifacts
    finally:
        sys.path.remove(str(compat_dir))
    reserve = {
        "reserve_validation_status": "VALID",
        "reserve_artifact": _artifact(raw=100, virtual=25).to_dict(),
        "effective_reserve_price_usd": "1.25",
    }
    record = build30_artifacts.build_candidate_recheck_record(
        rec={
            "token_mint": MINT,
            "market_context": {
                "current_price": "1",
                "current_market_cap_usd": "1000",
                "liquidity_usd": "500",
                "pumpswap_reserve": reserve,
            },
        },
        entry=SimpleNamespace(candidate_id="c1", migration_time_utc=OBSERVED,
                              source_ref="test"),
        cycle=1,
        observed_at_utc=OBSERVED,
        ledger_touched=False,
        transport_attempted=False,
    )
    emitted = record["market_attempt_summary"]["pumpswap_reserve"]
    assert emitted["reserve_artifact"]["raw_quote_reserves"] == "100"
    assert emitted["reserve_artifact"]["virtual_quote_reserves"] == "25"
    assert emitted["reserve_artifact"]["effective_quote_reserves"] == "125"


def test_index_telemetry_price_mc_liquidity_ath_and_drawdown_use_effective():
    index = PumpSwapReserveIndex()
    first = _artifact(raw=100, virtual=100, base=100, supply=1000)
    assert index.record(base_mint=MINT, artifact=first)
    t1 = index.compare_market(
        MINT, birdeye_price_usd="1", quote_price_usd="1",
        discrepancy_warn_pct="20")
    assert t1["comparison_status"] == RESERVE_COMPARISON_DISCREPANCY
    assert t1["effective_reserve_price_usd"] == "2"
    assert t1["effective_reserve_market_cap_usd"] == "2000"
    assert t1["effective_reserve_liquidity_usd"] == "400"
    assert t1["effective_reserve_drawdown_pct"] == "0"
    assert t1["reserve_trusted_for_routing"] is False
    assert t1["reference_price_usd"] == "1"
    assert art.scan_text(json.dumps(t1)) == []

    second = _artifact(raw=50, virtual=50, base=100, supply=1000)
    assert index.record(base_mint=MINT, artifact=second)
    t2 = index.compare_market(MINT, birdeye_price_usd="1", quote_price_usd="1")
    assert t2["effective_reserve_price_usd"] == "1"
    assert t2["effective_reserve_ath_price_usd"] == "2"
    assert t2["effective_reserve_drawdown_pct"] == "50.0"


def test_same_grpc_update_ingestion_keeps_pump_suffix_before_reserve_indexing():
    payload = _buy_event(kind="virtual", virtual=25)
    log = "Program data: " + base64.b64encode(payload).decode("ascii")

    def update_for(base_mint: str):
        balances = [
            SimpleNamespace(
                mint=base_mint, ui_token_amount=SimpleNamespace(decimals=6)),
            SimpleNamespace(
                mint=WRAPPED_SOL_MINT, ui_token_amount=SimpleNamespace(decimals=9)),
        ]
        meta = SimpleNamespace(
            pre_token_balances=balances, post_token_balances=balances,
            log_messages=[log])
        return SimpleNamespace(
            transaction=SimpleNamespace(transaction=SimpleNamespace(meta=meta)))

    rejected = PumpSwapReserveIndex()
    assert ingest_reserve_events_from_update(
        update_for("A" * 44), reserve_index=rejected) == 0
    assert rejected.stats()["reserve_mints_indexed"] == 0

    accepted = PumpSwapReserveIndex()
    assert ingest_reserve_events_from_update(
        update_for(MINT), reserve_index=accepted) == 1
    assert accepted.latest(MINT).effective_quote_reserves == 125


def test_program_data_binds_exact_outer_inner_and_flattened_instruction_identity():
    other_program = "11111111111111111111111111111111"
    keys = [_base58_decode(other_program), _base58_decode(PUMPSWAP_PROGRAM_ID)]
    top = [
        SimpleNamespace(program_id_index=0),
        SimpleNamespace(program_id_index=1),
    ]
    inner = SimpleNamespace(index=0, instructions=[
        SimpleNamespace(program_id_index=0),
        SimpleNamespace(program_id_index=1),
    ])
    message = SimpleNamespace(account_keys=keys, instructions=top)
    meta = SimpleNamespace(
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=[inner],
    )
    inner_payload = b"inner-event"
    top_payload = b"top-event"
    logs = [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [2]",
        "Program data: " + base64.b64encode(inner_payload).decode("ascii"),
        f"Program {PUMPSWAP_PROGRAM_ID} success",
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program data: " + base64.b64encode(top_payload).decode("ascii"),
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]
    decoded = list(_program_data_payloads_with_context(
        logs, message=message, meta=meta))
    assert [(payload, proven) for payload, _identity, proven in decoded] == [
        (inner_payload, True), (top_payload, True)]
    inner_identity = decoded[0][1]
    assert (inner_identity.outer_index, inner_identity.inner_index,
            inner_identity.flattened_index) == (0, 1, 3)
    top_identity = decoded[1][1]
    assert (top_identity.outer_index, top_identity.inner_index,
            top_identity.flattened_index) == (1, None, 1)


def test_truncated_instruction_log_mapping_is_comparison_only():
    keys = [_base58_decode(PUMPSWAP_PROGRAM_ID)]
    message = SimpleNamespace(
        account_keys=keys,
        instructions=[SimpleNamespace(program_id_index=0),
                      SimpleNamespace(program_id_index=0)],
    )
    meta = SimpleNamespace(
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=[],
    )
    payload = b"event"
    logs = [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program data: " + base64.b64encode(payload).decode("ascii"),
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]
    assert list(_program_data_payloads_with_context(
        logs, message=message, meta=meta))[0][2] is False


def test_create_pool_base_mint_extraction_is_unchanged():
    keys_text = [POOL, "1" * 32, "2" * 32, MINT, WRAPPED_SOL_MINT, PUMPSWAP_PROGRAM_ID]
    instruction = SimpleNamespace(
        program_id_index=5, accounts=bytes((0, 1, 2, 3, 4)),
        data=CREATE_POOL_DISCRIMINATOR)
    message = SimpleNamespace(
        account_keys=[_base58_decode(value) for value in keys_text],
        instructions=[instruction])
    meta = SimpleNamespace(
        log_messages=["Program log: Instruction: CreatePool"],
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=[])
    update = SimpleNamespace(transaction=SimpleNamespace(transaction=SimpleNamespace(
        transaction=SimpleNamespace(message=message), meta=meta)))
    assert extract_create_pool_quartet(update) == (POOL, MINT, WRAPPED_SOL_MINT)


def test_lp_drain_risk_uses_effective_not_raw_quote_reserves():
    compat_dir = Path(__file__).resolve().parents[1] / "free_tier_producer" / "compat"
    sys.path.insert(0, str(compat_dir))
    try:
        import production_live_lp_verify as lpv
        import production_live_lp_verify_models as models
    finally:
        sys.path.remove(str(compat_dir))

    first = models.LpReserveSnapshot.from_artifact(
        timestamp_s=1.0, artifact=_artifact(raw=100, virtual=100))
    second = models.LpReserveSnapshot.from_artifact(
        timestamp_s=2.0, artifact=_artifact(raw=100, virtual=0))
    result = lpv.verify_lp(
        models.LpVerifyInput(
            candidate_mint=MINT, pool_address=POOL,
            reserve_snapshots=(first, second)),
        models.LpVerifyConfig(min_events=2),
    )
    assert result.lp_verify_status == models.LP_VERIFY_FAIL
    assert result.lp_verify_reason == models.LP_REMOVED_OR_DRAINING
    assert result.pumpswap_reserve["effective_quote_reserves"] == "100"
