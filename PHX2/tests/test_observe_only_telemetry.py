"""Offline acceptance for truthful observe-only Telegram telemetry."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

from PHX2.delivery.telegram_adapter import (
    ANTE_SHAPE_NO_RULE_REASON,
    BUILDER_NO_RULE_REASON,
    LIQUIDITY_DATA_UNAVAILABLE_REASON,
    LIQUIDITY_QUALITY_NOT_SCORED_REASON,
    _actual_liquidity_display,
    _builder_read,
    build_ping_data,
)
from PHX2.delivery.telegram_composer import compose_telegram_ping
from PHX2.free_tier_producer.canonical_volume import (
    CanonicalSwapVolumeTracker,
    VOLUME_INSUFFICIENT_DATA,
    VOLUME_VALID,
)
from PHX2.free_tier_producer.compat.production_live_artifacts import art
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveArtifact,
    actual_pool_tvl_usd,
    actual_quote_liquidity_usd,
    actual_token_liquidity_usd,
    reserve_liquidity_usd,
)
from PHX2.tests.delivery.test_telegram_delivery import (
    CREATED,
    MINT,
    _delivery_context,
    _snapshot,
)


PAIR = "2YnSLW6SzsQteerTm6Q7ygWQJnizrrcJkEUcGBrSwQLd"
QUOTE = "So11111111111111111111111111111111111111112"
NOW_EPOCH = datetime.fromisoformat(
    CREATED.replace("Z", "+00:00")).timestamp()


def _swap(
    *,
    signature: str,
    event_index: int,
    side: str,
    quote_raw: int,
    source_timestamp: str = CREATED,
    quote_timestamp: str = CREATED,
):
    return {
        "mint": MINT,
        "pool_address": PAIR,
        "transaction_signature": signature,
        "event_index": event_index,
        "event_side": side,
        "quote_amount_raw": str(quote_raw),
        "quote_amount_basis": (
            "QUOTE_AMOUNT_IN" if side == "BUY" else "QUOTE_AMOUNT_OUT"),
        "quote_decimals": 9,
        "quote_price_usd": "100",
        "source_timestamp": source_timestamp,
        "quote_price_observed_at_utc": quote_timestamp,
        "transaction_succeeded": True,
        "source_event_proven": True,
        "reserve_trusted_for_routing": True,
    }


def _reserve(
    *,
    observed_at: str = CREATED,
    pool: str = PAIR,
) -> tuple[PumpSwapReserveArtifact, dict]:
    artifact = PumpSwapReserveArtifact(
        raw_quote_reserves=100_000_000_000,
        virtual_quote_reserves=50_000_000_000,
        effective_quote_reserves=150_000_000_000,
        base_reserves=200_000_000_000_000,
        reserve_source="PUMPSWAP_BUY_EVENT",
        observation_timestamp=observed_at,
        decoder_layout_version="TEST",
        pool_address=pool,
        base_mint=MINT,
        quote_mint=QUOTE,
        base_decimals=6,
        quote_decimals=9,
        event_side="BUY",
        quote_amount_raw=1_000_000_000,
        quote_amount_basis="QUOTE_AMOUNT_IN",
    )
    quote = actual_quote_liquidity_usd(
        artifact, quote_price_usd="50")
    token = actual_token_liquidity_usd(
        artifact, base_price_usd="0.0001")
    total = actual_pool_tvl_usd(
        artifact, quote_price_usd="50", base_price_usd="0.0001")
    telemetry = {
        "reserve_validation_status": "VALID",
        "reserve_artifact": artifact.to_dict(),
        "actual_quote_liquidity_usd": format(quote, "f"),
        "actual_token_liquidity_usd": format(token, "f"),
        "actual_pool_tvl_usd": format(total, "f"),
        "actual_liquidity_definition": (
            "REAL_QUOTE_VAULT_PLUS_REAL_BASE_VAULT_AT_ACCEPTED_CURRENT_PRICE"),
        "quote_side_liquidity_definition": "REAL_QUOTE_VAULT_ONLY",
        "quote_price_usd": "50",
        "quote_price_observed_at_utc": observed_at,
        "effective_reserve_liquidity_usd": format(
            reserve_liquidity_usd(artifact, quote_price_usd="50"), "f"),
    }
    return artifact, telemetry


def test_valid_swaps_produce_exact_gross_signed_net_and_coverage():
    tracker = CanonicalSwapVolumeTracker(now_fn=lambda: NOW_EPOCH)
    assert tracker.observe(_swap(
        signature="buy", event_index=0, side="BUY",
        quote_raw=1_000_000_000))
    assert tracker.observe(_swap(
        signature="sell", event_index=1, side="SELL",
        quote_raw=250_000_000))

    snapshot = tracker.snapshot(MINT)

    assert snapshot["status"] == VOLUME_VALID
    assert snapshot["gross_volume_usd"] == "125.00"
    assert snapshot["net_quote_flow_usd"] == "75.00"
    assert snapshot["sample_count"] == 2
    assert snapshot["buy_count"] == snapshot["sell_count"] == 1
    assert snapshot["window_seconds"] == 300
    assert snapshot["observe_only"] is True


def test_duplicate_non_swap_and_stale_price_events_are_excluded():
    tracker = CanonicalSwapVolumeTracker(now_fn=lambda: NOW_EPOCH)
    event = _swap(
        signature="one", event_index=0, side="BUY",
        quote_raw=1_000_000_000)
    assert tracker.observe(event)
    assert tracker.observe(event) is False
    non_swap = {**event, "transaction_signature": "migration",
                "event_side": "MIGRATION_INITIALIZATION"}
    assert tracker.observe(non_swap) is False
    stale_quote = _swap(
        signature="stale", event_index=2, side="SELL",
        quote_raw=1_000_000_000,
        quote_timestamp="2026-07-16T11:59:00Z",
    )
    assert tracker.observe(stale_quote) is False
    snapshot = tracker.snapshot(MINT)
    assert snapshot["sample_count"] == 1
    assert snapshot["gross_volume_usd"] == "100"
    assert tracker.stats() == {
        "canonical_volume_events_active": 1,
        "canonical_volume_events_accepted_total": 1,
        "canonical_volume_events_duplicate_total": 1,
        "canonical_volume_events_rejected_total": 2,
    }


def test_no_authenticated_swaps_is_explicit_insufficient_data():
    snapshot = CanonicalSwapVolumeTracker(
        now_fn=lambda: NOW_EPOCH).snapshot(MINT)
    assert snapshot["status"] == VOLUME_INSUFFICIENT_DATA
    assert snapshot["sample_count"] == 0
    assert snapshot["coverage_seconds"] == "0"


def test_production_constructs_and_registers_canonical_volume_once():
    source = (
        Path(__file__).resolve().parents[1]
        / "free_tier_producer" / "free_tier_session.py"
    ).read_text(encoding="utf-8")
    assert source.count("canonical_volume = CanonicalSwapVolumeTracker()") == 1
    assert source.count(
        "reserve_index.add_routing_observer(canonical_volume.observe)") == 1
    assert source.count('cand["canonical_volume_5m"] = canonical_volume.snapshot(') == 1


def test_actual_liquidity_excludes_virtual_and_keeps_effective_pricing():
    artifact, telemetry = _reserve()

    assert actual_quote_liquidity_usd(
        artifact, quote_price_usd="50") == Decimal("5000")
    assert actual_token_liquidity_usd(
        artifact, base_price_usd="0.0001") == Decimal("20000.0000")
    assert actual_pool_tvl_usd(
        artifact, quote_price_usd="50",
        base_price_usd="0.0001") == Decimal("25000.0000")
    # Effective pricing liquidity deliberately includes the 50 virtual SOL and
    # doubles that effective side.  It remains internal and separately labeled.
    assert reserve_liquidity_usd(
        artifact, quote_price_usd="50") == Decimal("15000")
    assert telemetry["actual_quote_liquidity_usd"] == "5000"
    assert telemetry["actual_pool_tvl_usd"] == "25000.0000"


def test_matching_fresh_actual_liquidity_reaches_telegram_truthfully():
    _artifact, reserve = _reserve()
    context = _delivery_context()
    context["candidate"].update({
        "pair_address": PAIR,
        "canonical_volume_5m": {
            "status": "VALID",
            "mint": MINT,
            "window_seconds": 300,
            "gross_volume_usd": "125",
            "net_quote_flow_usd": "75",
            "sample_count": 2,
            "observe_only": True,
        },
    })
    context["market_context"].update({
        "current_price": "0.0001",
        "pumpswap_reserve": reserve,
    })
    data = build_ping_data(
        mint=MINT,
        composed_snapshot=_snapshot(),
        delivery_context=context,
        now_utc=CREATED,
    )
    text = compose_telegram_ping(data).text

    assert data.tier == 3
    assert data.liquidity == "$25k"
    assert data.quote_side_liquidity == "$5k"
    assert data.liquidity_basis == "TOTAL_ACTUAL_POOL_TVL"
    assert data.volume == "$125 gross | +$75 net (n=2)"
    assert data.liquidity_quality == (
        "NOT SCORED (NO APPROVED LIQUIDITY QUALITY RULE)")
    assert "Vol 5m: $125 gross | +$75 net (n=2)" in text
    # 2026-07-28 remediation: the operator body shows the clean value only;
    # basis, quote-side duplication and the unscored-quality placeholder stay
    # artifact-only.
    assert "• LP: $25k" in text
    assert "TOTAL_ACTUAL_POOL_TVL" not in text
    assert "Quote-side" not in text
    assert "LP Quality" not in text
    assert "NO APPROVED LIQUIDITY QUALITY RULE" not in text
    assert "CENTRAL_VOLUME_CLASSIFIER_UNAVAILABLE" not in text
    assert "CENTRAL_LIQUIDITY_QUALITY_UNAVAILABLE" not in text


def test_stale_or_mismatched_pair_data_is_rejected_for_display():
    _artifact, reserve = _reserve(pool="WrongPair")
    candidate = {"pair_address": PAIR}
    market = {"current_price": "0.0001", "pumpswap_reserve": reserve}
    total, quote, basis, value, reason = _actual_liquidity_display(
        mint=MINT,
        candidate=candidate,
        market=market,
        now_utc=CREATED,
    )
    # The internal reason code stays artifact-only; the display is the
    # unavailable marker (2026-07-28 remediation).
    assert total == quote == "—"
    assert basis == "UNAVAILABLE" and value is None
    assert reason == LIQUIDITY_DATA_UNAVAILABLE_REASON

    _artifact, stale = _reserve(observed_at="2026-07-16T11:54:00Z")
    assert _actual_liquidity_display(
        mint=MINT,
        candidate={"pair_address": PAIR},
        market={"current_price": "0.0001", "pumpswap_reserve": stale},
        now_utc=CREATED,
    )[2] == "UNAVAILABLE"


def test_absent_approved_shape_rules_and_builder_no_match_are_distinct():
    context = _delivery_context()
    fee = context["security_decision"].fee_snapshot
    del fee.ante_5m_shape
    del fee.ante_5m_shape_rule
    del fee.ante_last20_shape
    del fee.ante_last20_shape_rule
    data = build_ping_data(
        mint=MINT,
        composed_snapshot=_snapshot(),
        delivery_context=context,
        now_utc=CREATED,
    )
    assert data.shape_5m == data.shape_last20 == "NO APPROVED SHAPE RULE"
    assert data.shape_5m_rule == data.shape_last20_rule == "N/A"
    assert data.field_reason_codes["shape_5m"] == (
        ANTE_SHAPE_NO_RULE_REASON,)
    assert data.field_reason_codes["shape_last20"] == (
        ANTE_SHAPE_NO_RULE_REASON,)

    builder = _builder_read(
        fee=SimpleNamespace(
            fee_gate_reasons=(), event_pace_per_minute=Decimal("2"),
            fee_gate_label="Normal", balanced_fees=False),
        lp=SimpleNamespace(lp_integrity_reasons=()),
        liquidity=Decimal("25000"),
        floor=Decimal("-10"),
        shape_5m="NO APPROVED SHAPE RULE",
    )
    # 2026-07-29 final cleanup: no placeholder sentence exists — the section
    # is omitted and the no-match reason travels through field_reason_codes
    # (BUILDER_NO_RULE_REASON) on the artifact surface.
    assert builder == ()
    assert BUILDER_NO_RULE_REASON == "NO_APPROVED_BUILDER_READ_RULE_MATCHED"


def test_telemetry_is_display_only_redaction_safe_and_not_a_dedupe_axis():
    from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
        ping_dedupe_key_field_names,
    )

    fields = ping_dedupe_key_field_names()
    assert "canonical_volume_5m" not in fields
    assert "actual_pool_tvl_usd" not in fields
    assert "liquidity_quality" not in fields
    proof = {
        "canonical_volume_5m": CanonicalSwapVolumeTracker(
            now_fn=lambda: NOW_EPOCH).snapshot(MINT),
        "liquidity_quality_reason": LIQUIDITY_QUALITY_NOT_SCORED_REASON,
    }
    serialized = json.dumps(proof, sort_keys=True)
    assert art.scan_text(serialized) == []
    assert "http" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_captured_target_actual_tvl_and_effective_reserves_are_exact():
    """Recalculate the failed-run mint from its preserved pricing-tail values."""

    artifact = PumpSwapReserveArtifact(
        raw_quote_reserves=205_830_369_195,
        virtual_quote_reserves=17_584_505_372,
        effective_quote_reserves=223_414_874_567,
        base_reserves=95_538_553_292_815,
        reserve_source="PUMPSWAP_BUY_EVENT",
        observation_timestamp="2026-07-27T06:27:44Z",
        decoder_layout_version="PUMPSWAP_BUY_EVENT_BOOST_V3",
        pool_address=PAIR,
        base_mint="Dh5GKcPQFBJXw74yP4u7BCHYQzHoG6JX8dXQaNwvpump",
        quote_mint=QUOTE,
        base_decimals=6,
        quote_decimals=9,
    )
    sol_usd = Decimal(
        "76.62396096829567905571206497")
    accepted_price = Decimal("0.00015528628073180863")
    quote = actual_quote_liquidity_usd(
        artifact, quote_price_usd=sol_usd)
    token = actual_token_liquidity_usd(
        artifact, base_price_usd=accepted_price)
    total = actual_pool_tvl_usd(
        artifact,
        quote_price_usd=sol_usd,
        base_price_usd=accepted_price,
    )
    effective = reserve_liquidity_usd(
        artifact, quote_price_usd=sol_usd)
    assert quote == Decimal(
        "15771.53817528756930996044331")
    assert token == Decimal(
        "14835.82660733892987559693399")
    assert total == Decimal(
        "30607.36478262649918555737730")
    assert effective == Decimal(
        "34237.86525711696600000000000")
    assert total != Decimal("43129.82205625301")
