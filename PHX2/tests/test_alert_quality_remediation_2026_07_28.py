"""2026-07-28 alert-quality remediation: presentation, metadata, volume, LP.

Locks the four remediation contracts proven against the
paid_primary_live_24x7_20260728T055833Z acceptance evidence:

1. Telegram is a clean operator decision surface; internal reason codes stay
   in artifacts and unavailable canonical fields render as ``—``.
2. One canonical per-mint token metadata state, fed from already-owned
   responses, with a bounded pre-dispatch deferral (the 335Sdx… UNKNOWN TOKEN
   defect).
3. Canonical 5m volume stays authenticated fail-closed (the 38K55aqS…/Appa
   zero-sample case is the correct outcome of a missing sealed live migration
   proof) and the shared purge window resists future-skewed event timestamps.
4. Exact-pair actual reserves reach the compose/delivery context (the
   dropped-mapping defect that made every alert render LP as unavailable).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from PHX2.delivery.telegram_adapter import (
    LIQUIDITY_DATA_UNAVAILABLE_REASON,
    TOKEN_METADATA_CANONICAL_LIVE,
    TOKEN_METADATA_UNAVAILABLE,
    UNKNOWN_TOKEN_DISPLAY,
    _actual_liquidity_display,
    _metadata_identity,
    _sanitize_metadata,
    build_ping_data,
    resolve_token_identity,
)
from PHX2.delivery.telegram_composer import compose_telegram_ping
from PHX2.free_tier_producer.canonical_volume import (
    CanonicalSwapVolumeTracker,
    VOLUME_INSUFFICIENT_DATA,
    VOLUME_VALID,
)
from PHX2.free_tier_producer.compat import production_live_artifacts
from PHX2.free_tier_producer.market_scheduler import ScheduledMarketSidecar
from PHX2.free_tier_producer.paid_market_readiness import (
    PaidMarketReadinessConfig,
    PaidMarketReadinessTracker,
)
from PHX2.free_tier_producer.ping_quality_review import (
    CANONICAL_VOLUME_MISSING_REQUIREMENT_BACKFILL,
    CANONICAL_VOLUME_MISSING_REQUIREMENT_LIVE,
    build_ping_quality_record,
    ping_quality_record_is_redaction_safe,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveArtifact,
    PumpSwapReserveIndex,
)
from PHX2.free_tier_producer.token_metadata import (
    METADATA_DEFER_REASON,
    METADATA_STATUS_PENDING,
    METADATA_STATUS_RESOLVED,
    METADATA_STATUS_UNAVAILABLE,
    TokenMetadataResolver,
    sanitize_token_name,
    sanitize_token_symbol,
)


APPA_MINT = "38K55aqSCMrahqPBTZLLa9DvKygaSG4NqhxXvGE4pump"
APPA_PAIR = "A6p5CJUFGdzkSPVMT7rsRFCwizfBoj8BEsoMLqPygvBN"
LIVE_MINT = "335SdxzgdttfbNyKWzkdphiCWKTZduK7XJE8rL6Spump"
LIVE_PAIR = "3EVqNTpj9CUhD2AAPTKLaEzorKAo3zyvkdJMbHDJE2Ns"
WSOL = "So11111111111111111111111111111111111111112"

NOW = "2026-07-28T06:05:37Z"
NOW_EPOCH = datetime(2026, 7, 28, 6, 5, 37, tzinfo=timezone.utc).timestamp()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# =========================================================================
# 1. Canonical token metadata state
# =========================================================================


class _Clock:
    def __init__(self, start: float = NOW_EPOCH) -> None:
        self.epoch = start

    def now_iso(self) -> str:
        return _iso(self.epoch)


def test_metadata_merge_both_name_only_symbol_only_and_neither():
    resolver = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    assert resolver.merge(
        LIVE_MINT, token_name="Live Named", token_symbol="LIVE",
        source="TEST") is True
    snap = resolver.snapshot(LIVE_MINT)
    assert snap["token_name"] == "Live Named"
    assert snap["token_symbol"] == "LIVE"
    assert snap["metadata_status"] == METADATA_STATUS_RESOLVED
    assert snap["validated"] is True
    assert snap["metadata_source"] == "TEST"
    assert snap["metadata_resolved_at"] is not None

    name_only = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    name_only.merge("A" * 40 + "pump", token_name="Only Name", source="TEST")
    assert name_only.snapshot("A" * 40 + "pump")["token_symbol"] is None
    assert name_only.snapshot("A" * 40 + "pump")["validated"] is True

    symbol_only = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    symbol_only.merge("B" * 40 + "pump", token_symbol="TICK", source="TEST")
    assert symbol_only.snapshot("B" * 40 + "pump")["token_name"] is None
    assert symbol_only.snapshot("B" * 40 + "pump")["validated"] is True

    neither = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    assert neither.merge("C" * 40 + "pump", source="TEST") is False
    empty = neither.snapshot("C" * 40 + "pump")
    assert empty["validated"] is False
    assert empty["metadata_failure_reason"] == "SOURCE_FIELDS_EMPTY_OR_INVALID"


def test_metadata_merge_only_improves_and_stale_source_cannot_overwrite():
    resolver = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    resolver.merge(LIVE_MINT, token_name="First Name", source="FIRST")
    # A later source fills the missing symbol but can never replace the name.
    resolver.merge(
        LIVE_MINT, token_name="Imposter", token_symbol="SYM", source="SECOND")
    snap = resolver.snapshot(LIVE_MINT)
    assert snap["token_name"] == "First Name"
    assert snap["token_symbol"] == "SYM"
    assert snap["metadata_source"] == "FIRST"
    assert snap["metadata_sources_attempted"] == ["FIRST", "SECOND"]
    # Null-like refresh payloads never erase resolved state.
    resolver.merge(LIVE_MINT, token_name="???", token_symbol="", source="JUNK")
    assert resolver.snapshot(LIVE_MINT)["token_name"] == "First Name"
    assert resolver.snapshot(LIVE_MINT)["metadata_failure_reason"] is None


def test_metadata_sanitizers_match_the_delivery_layer_exactly():
    cases = (
        "Appa", " padded  name ", "???", "unknown", "N/A", "NULL", "",
        "$$WAN", "multi\nline\tname", "<b>html</b>", "x" * 200, None, 42,
        "น้องวัน",
    )
    for value in cases:
        assert sanitize_token_name(value) == _sanitize_metadata(
            value, limit=64), value
    # Symbol adds the single-$ normalization on top of the shared sanitizer.
    assert sanitize_token_symbol("$$WAN") == "WAN"
    assert sanitize_token_symbol("$") is None
    assert sanitize_token_symbol("WAN") == "WAN"
    assert sanitize_token_symbol("x" * 200) == "x" * 16


def test_metadata_identity_uses_explicit_symbol_and_single_dollar_prefix():
    identity, source = _metadata_identity(
        {"token_name": "Appa", "token_symbol": "$APPA"}, source="TEST")
    assert identity == "Appa ($APPA)".replace("$$", "$")
    assert identity == "Appa ($APPA)"
    assert source == "TEST"


def test_bounded_pre_dispatch_deferral_caps_ticks_and_wall_clock():
    clock = _Clock()
    resolver = TokenMetadataResolver(
        now_iso_fn=clock.now_iso,
        max_pre_dispatch_deferrals=2,
        max_pre_dispatch_wait_seconds=120.0,
    )
    # Two bounded deferrals, then compose must proceed.
    assert resolver.pre_dispatch_defer_reason(LIVE_MINT) == (
        METADATA_DEFER_REASON)
    clock.epoch += 51
    assert resolver.pre_dispatch_defer_reason(LIVE_MINT) == (
        METADATA_DEFER_REASON)
    clock.epoch += 51
    assert resolver.pre_dispatch_defer_reason(LIVE_MINT) is None
    assert resolver.snapshot(LIVE_MINT)["metadata_status"] == (
        METADATA_STATUS_UNAVAILABLE)

    # Wall-clock expiry alone also ends the wait even with budget left.
    late_clock = _Clock()
    late = TokenMetadataResolver(
        now_iso_fn=late_clock.now_iso, max_pre_dispatch_wait_seconds=120.0)
    late.note_request(LIVE_MINT)
    late_clock.epoch += 121
    assert late.pre_dispatch_defer_reason(LIVE_MINT) is None

    # A resolved mint never defers.
    resolved = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    resolved.merge(LIVE_MINT, token_name="Named", source="TEST")
    assert resolved.pre_dispatch_defer_reason(LIVE_MINT) is None


def test_metadata_arriving_during_deferral_resolves_before_compose():
    clock = _Clock()
    resolver = TokenMetadataResolver(now_iso_fn=clock.now_iso)
    assert resolver.pre_dispatch_defer_reason(LIVE_MINT) == (
        METADATA_DEFER_REASON)
    assert resolver.snapshot(LIVE_MINT)["metadata_status"] == (
        METADATA_STATUS_PENDING)
    # The overview plane lands between recheck ticks.
    resolver.merge(
        LIVE_MINT, token_name="Live Named", token_symbol="LIVE",
        source="PAID_MARKET_PRIMARY_OVERVIEW")
    assert resolver.pre_dispatch_defer_reason(LIVE_MINT) is None
    snapshot = resolver.snapshot(LIVE_MINT)
    assert snapshot["metadata_status"] == METADATA_STATUS_RESOLVED
    identity, source = resolve_token_identity(
        mint=LIVE_MINT,
        candidate={
            "token_mint": LIVE_MINT,
            "discovery_provenance": "LIVE_YELLOWSTONE",
            "token_name": None,
            "symbol_or_name": None,
            "canonical_token_metadata": snapshot,
        },
        delivery_context={},
    )
    assert (identity, source) == (
        "Live Named ($LIVE)", TOKEN_METADATA_CANONICAL_LIVE)


def test_live_path_overview_harvest_matches_session_wiring():
    """The paid overview plane now carries name/symbol; merging its values is
    exactly what ``_scheduler_apply_observation`` does for live candidates."""

    resolver = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    overview_values = {
        "mint": LIVE_MINT,
        "current_market_cap_usd": "25737",
        "liquidity_usd": "9748",
        "token_name": "Three Three Five",
        "token_symbol": "TTF",
    }
    resolver.merge(
        LIVE_MINT,
        token_name=overview_values.get("token_name"),
        token_symbol=overview_values.get("token_symbol"),
        source="PAID_MARKET_PRIMARY_OVERVIEW")
    snap = resolver.snapshot(LIVE_MINT)
    assert snap["validated"] is True
    assert snap["metadata_source"] == "PAID_MARKET_PRIMARY_OVERVIEW"


def test_restart_backfill_admission_harvest_never_uses_name_as_ticker():
    resolver = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    # build_backfill_candidate shape: symbol_or_name falls back to the name.
    candidate = {
        "token_mint": APPA_MINT,
        "token_name": "Appa",
        "token_symbol": "",
        "symbol_or_name": "Appa",
    }
    fallback_symbol = candidate.get("symbol_or_name")
    if fallback_symbol == candidate.get("token_name"):
        fallback_symbol = None
    resolver.merge(
        APPA_MINT,
        token_name=candidate.get("token_name"),
        token_symbol=candidate.get("token_symbol") or fallback_symbol,
        source="DEXSCREENER_RESTART_BACKFILL")
    snap = resolver.snapshot(APPA_MINT)
    assert snap["token_name"] == "Appa"
    assert snap["token_symbol"] is None


# =========================================================================
# 2. Canonical volume: authenticated fail-closed window behavior
# =========================================================================


def _swap_payload(**overrides):
    payload = {
        "mint": LIVE_MINT,
        "pool_address": LIVE_PAIR,
        "transaction_signature": "sig-1",
        "event_index": 0,
        "event_side": "BUY",
        "transaction_succeeded": True,
        "source_event_proven": True,
        "reserve_trusted_for_routing": True,
        "quote_decimals": 9,
        "quote_amount_raw": 500_000_000,
        "source_timestamp": _iso(NOW_EPOCH - 30),
        "quote_price_observed_at_utc": _iso(NOW_EPOCH - 29),
        "quote_price_usd": "100",
        "quote_amount_basis": "QUOTE_AMOUNT_IN",
    }
    payload.update(overrides)
    return payload


def _tracker(clock: _Clock) -> CanonicalSwapVolumeTracker:
    return CanonicalSwapVolumeTracker(now_fn=lambda: clock.epoch)


def test_valid_trailing_five_minute_gross_and_net_calculation():
    clock = _Clock()
    tracker = _tracker(clock)
    assert tracker.observe(_swap_payload()) is True                 # +$50
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-2", event_side="SELL",
        quote_amount_raw=250_000_000,
        quote_amount_basis="QUOTE_AMOUNT_OUT")) is True             # -$25
    snapshot = tracker.snapshot(LIVE_MINT)
    assert snapshot["status"] == VOLUME_VALID
    assert Decimal(snapshot["gross_volume_usd"]) == Decimal("75")
    assert Decimal(snapshot["net_quote_flow_usd"]) == Decimal("25")
    assert snapshot["sample_count"] == 2
    assert snapshot["buy_count"] == 1 and snapshot["sell_count"] == 1


def test_duplicate_wrong_mint_missing_decimals_and_untrusted_are_rejected():
    clock = _Clock()
    tracker = _tracker(clock)
    assert tracker.observe(_swap_payload()) is True
    # Exact duplicate (same signature + event index) never double-counts.
    assert tracker.observe(_swap_payload()) is False
    assert tracker.stats()["canonical_volume_events_duplicate_total"] == 1
    # Another mint's swaps never appear in this mint's snapshot.
    assert tracker.observe(_swap_payload(
        mint="Other111111111111111111111111111111111pump",
        transaction_signature="sig-other")) is True
    assert tracker.snapshot(LIVE_MINT)["sample_count"] == 1
    # Missing decimals, missing pool identity, and untrusted routing reject.
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-3", quote_decimals=None)) is False
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-4", pool_address="")) is False
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-5",
        reserve_trusted_for_routing=False)) is False
    assert tracker.stats()["canonical_volume_events_rejected_total"] == 3


def test_window_expiry_and_later_valid_samples_resolve_insufficient_state():
    clock = _Clock()
    tracker = _tracker(clock)
    assert tracker.snapshot(LIVE_MINT)["status"] == VOLUME_INSUFFICIENT_DATA
    assert tracker.observe(_swap_payload()) is True
    assert tracker.snapshot(LIVE_MINT)["status"] == VOLUME_VALID
    # The same evidence expires out of the trailing window.
    clock.epoch += 400
    assert tracker.snapshot(LIVE_MINT)["status"] == VOLUME_INSUFFICIENT_DATA
    # Later valid samples resolve the unavailable state again.
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-later",
        source_timestamp=_iso(clock.epoch - 5),
        quote_price_observed_at_utc=_iso(clock.epoch - 5))) is True
    assert tracker.snapshot(LIVE_MINT)["status"] == VOLUME_VALID


def test_future_skewed_event_is_rejected_and_cannot_evict_the_window():
    """Regression: ``observe`` purged with ``max(now, event_epoch)``, so one
    future-timestamped event could evict every mint's legitimate in-window
    evidence.  The tracker now rejects evidence beyond the small tolerance."""

    clock = _Clock()
    tracker = _tracker(clock)
    assert tracker.observe(_swap_payload()) is True
    skewed = _swap_payload(
        transaction_signature="sig-future",
        source_timestamp=_iso(clock.epoch + 600),
        quote_price_observed_at_utc=_iso(clock.epoch + 600))
    assert tracker.observe(skewed) is False
    assert tracker.stats()["canonical_volume_events_rejected_total"] == 1
    snapshot = tracker.snapshot(LIVE_MINT)
    assert snapshot["status"] == VOLUME_VALID
    assert snapshot["sample_count"] == 1
    # Small (≤2s) skew stays accepted: on-chain clocks jitter.
    assert tracker.observe(_swap_payload(
        transaction_signature="sig-jitter",
        source_timestamp=_iso(clock.epoch + 1),
        quote_price_observed_at_utc=_iso(clock.epoch + 1))) is True


# =========================================================================
# 3. Exact-pair actual reserves reach the compose context
# =========================================================================


def _reserve_index_with_artifact(
    *, observed_epoch: float = NOW_EPOCH - 20,
    pool: str = LIVE_PAIR, mint: str = LIVE_MINT,
) -> PumpSwapReserveIndex:
    index = PumpSwapReserveIndex()
    artifact = PumpSwapReserveArtifact(
        raw_quote_reserves=50_000_000_000,
        virtual_quote_reserves=25_000_000_000,
        effective_quote_reserves=75_000_000_000,
        base_reserves=200_000_000_000,
        reserve_source="BUY_EVENT",
        observation_timestamp=_iso(observed_epoch),
        decoder_layout_version="TEST_FIXTURE",
        pool_address=pool,
        base_mint=mint,
        quote_mint=WSOL,
        base_decimals=6,
        quote_decimals=9,
        base_supply=1_000_000_000_000_000,
    )
    index.record(base_mint=mint, artifact=artifact)
    index.cache_quote_price(WSOL, "100", observed_at=_iso(observed_epoch + 1))
    return index


def test_real_compare_market_output_passes_the_delivery_verification():
    """End-to-end: a genuine ``compare_market`` mapping priced with the same
    context price must satisfy the delivery layer's exact-recompute checks and
    render actual LP — the exact chain that was broken by the dropped key."""

    index = _reserve_index_with_artifact()
    telemetry = index.compare_market(LIVE_MINT, birdeye_price_usd="0.0001")
    assert telemetry["reserve_validation_status"] == "VALID"
    assert telemetry["actual_pool_tvl_usd"] is not None
    market = {
        "current_price": "0.0001",
        "pumpswap_reserve": telemetry,
    }
    total, quote, basis, value, reason = _actual_liquidity_display(
        mint=LIVE_MINT,
        candidate={"pair_address": LIVE_PAIR},
        market=market,
        now_utc=NOW,
    )
    assert reason is None
    assert basis == "TOTAL_ACTUAL_POOL_TVL"
    # raw quote 50 SOL * $100 = $5000; base 200k tokens * $0.0001 = $20.
    assert value == Decimal("5000") + Decimal("20")
    assert total == "$5k"
    assert quote == "$5k"


def test_stale_reserves_and_wrong_pair_stay_unavailable():
    stale_index = _reserve_index_with_artifact(
        observed_epoch=NOW_EPOCH - 360)
    stale = stale_index.compare_market(LIVE_MINT, birdeye_price_usd="0.0001")
    total, _quote, basis, value, reason = _actual_liquidity_display(
        mint=LIVE_MINT,
        candidate={"pair_address": LIVE_PAIR},
        market={"current_price": "0.0001", "pumpswap_reserve": stale},
        now_utc=NOW,
    )
    assert (total, basis, value) == ("—", "UNAVAILABLE", None)
    assert reason == LIQUIDITY_DATA_UNAVAILABLE_REASON

    wrong_pool = _reserve_index_with_artifact(pool="WrongPool111")
    telemetry = wrong_pool.compare_market(
        LIVE_MINT, birdeye_price_usd="0.0001")
    total, _quote, _basis, _value, reason = _actual_liquidity_display(
        mint=LIVE_MINT,
        candidate={"pair_address": LIVE_PAIR},
        market={"current_price": "0.0001", "pumpswap_reserve": telemetry},
        now_utc=NOW,
    )
    assert total == "—"
    assert reason == LIQUIDITY_DATA_UNAVAILABLE_REASON


def test_virtual_reserves_can_never_be_presented_as_actual_liquidity():
    index = _reserve_index_with_artifact()
    telemetry = dict(index.compare_market(
        LIVE_MINT, birdeye_price_usd="0.0001"))
    # Tamper: claim the effective (raw+virtual) quote value as actual.
    telemetry["actual_quote_liquidity_usd"] = "7500"
    telemetry["actual_pool_tvl_usd"] = "7520"
    total, _quote, _basis, _value, reason = _actual_liquidity_display(
        mint=LIVE_MINT,
        candidate={"pair_address": LIVE_PAIR},
        market={"current_price": "0.0001", "pumpswap_reserve": telemetry},
        now_utc=NOW,
    )
    assert total == "—"
    assert reason == LIQUIDITY_DATA_UNAVAILABLE_REASON


def test_scheduled_sidecar_attaches_reserve_telemetry_to_the_resolve_context():
    """Regression for the systemic dropped mapping: the production sidecar's
    resolve() context must carry ``compare_market`` output whenever a reserve
    observation exists — including one recorded before candidate admission —
    and must reflect the newest observation after a post-admission update."""

    index = _reserve_index_with_artifact()
    scheduler = SimpleNamespace(snapshot=lambda mint: {
        "token_mint": mint,
        "current_price": "0.0001",
        "current_market_cap_usd": "25737",
        "liquidity_usd": "9748",
        "all_present": True,
        "market_state": "MARKET_READY",
        "pumpswap_reserve": {},
    })
    sidecar = ScheduledMarketSidecar(
        scheduler, central_ath_snapshot_fn=None, reserve_index=index)
    ctx = sidecar.resolve(
        LIVE_MINT, migration_time_utc=None,
        now_iso_fn=lambda: NOW, sleep_fn=lambda _s: None)
    reserve = ctx["pumpswap_reserve"]
    assert reserve["reserve_validation_status"] == "VALID"
    assert reserve["actual_pool_tvl_usd"] is not None
    assert reserve["reserve_artifact"]["pool_address"] == LIVE_PAIR

    # Post-admission update: a newer artifact replaces the context payload.
    newer = PumpSwapReserveArtifact(
        raw_quote_reserves=60_000_000_000,
        virtual_quote_reserves=25_000_000_000,
        effective_quote_reserves=85_000_000_000,
        base_reserves=210_000_000_000,
        reserve_source="SELL_EVENT",
        observation_timestamp=_iso(NOW_EPOCH - 3),
        decoder_layout_version="TEST_FIXTURE",
        pool_address=LIVE_PAIR,
        base_mint=LIVE_MINT,
        quote_mint=WSOL,
        base_decimals=6,
        quote_decimals=9,
    )
    index.record(base_mint=LIVE_MINT, artifact=newer)
    refreshed = sidecar.resolve(
        LIVE_MINT, migration_time_utc=None,
        now_iso_fn=lambda: NOW, sleep_fn=lambda _s: None)
    assert refreshed["pumpswap_reserve"]["reserve_artifact"][
        "raw_quote_reserves"] == "60000000000"

    # No observation for the mint leaves the scheduler default untouched.
    missing = sidecar.resolve(
        "Missing111111111111111111111111111111111pump",
        migration_time_utc=None,
        now_iso_fn=lambda: NOW, sleep_fn=lambda _s: None)
    assert missing["pumpswap_reserve"] == {}


def test_readiness_tracker_result_preserves_the_reserve_mapping():
    """Regression: ``PaidMarketReadinessTracker._result`` rebuilt the resolved
    context and silently dropped the selected attempt's reserve telemetry."""

    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig())
    reserve_payload = {"reserve_validation_status": "VALID",
                       "actual_pool_tvl_usd": "5020"}

    def fetch_attempt(now_iso: str):
        return {
            "attempt_at_utc": now_iso,
            "price_value": "0.0001",
            "mc_value": "25737",
            "lp_value": "9748",
            "all_present": True,
            "basis": "REAL_MARKET_PRESENT",
            "provider_market_state": None,
            "provider_reason_code": None,
            "provider_timestamp_utc": now_iso,
            "endpoint_attempts": {},
            "pumpswap_reserve": dict(reserve_payload),
        }

    resolved = tracker.resolve(
        LIVE_MINT,
        migration_time_utc=_iso(NOW_EPOCH - 540),
        now_iso_fn=lambda: NOW,
        fetch_attempt_fn=fetch_attempt,
    )
    assert resolved["all_present"] is True
    assert resolved["pumpswap_reserve"] == reserve_payload


# =========================================================================
# 4. Regression fixtures: the two real alerts
# =========================================================================


def _appa_delivery_inputs():
    migration = datetime(2026, 7, 28, 5, 24, 37, tzinfo=timezone.utc)
    now = migration + timedelta(minutes=41)
    fee = SimpleNamespace(
        candidate_mint=APPA_MINT, proof_digest="fee-proof",
        total_fees=Decimal("3.41"), lp_fees=Decimal("0.59"),
        protocol_fees=Decimal("0.15"), creator_fees=Decimal("2.67"),
        event_pace_per_minute=Decimal("64"), event_count=396,
        fee_gate_label="SCAM Likely", fee_gate_score=6,
        fee_gate_reasons=("sticky_lock",), balanced_fees=False,
        bribe_share_pct=Decimal("0.8"), creator_share=Decimal("0.784"),
        bribes_per_transaction=Decimal("0.00007102"),
        first_observed_at_utc=(migration.isoformat()
                               .replace("+00:00", "Z")),
        last_observed_at_utc=(now.isoformat().replace("+00:00", "Z")),
        ante_last20_median=Decimal("0.000058"),
        ante_last20_p25=Decimal("0.000028"),
        ante_last20_p75=Decimal("0.000551"),
        ante_last20_sample_count=20,
        ante_5m_median=Decimal("0.000029"),
        ante_5m_p25=Decimal("0.000018"),
        ante_5m_p75=Decimal("0.0000594"),
        ante_5m_sample_count=322,
        ante_5m_base_fee_coverage=Decimal("1"),
        priority_fee_median_lamports=11574,
        priority_fee_sample_count=20,
        ante_5m_shape=None, ante_5m_shape_rule=None,
        ante_last20_shape=None, ante_last20_shape_rule=None,
    )
    security = SimpleNamespace(
        fee_snapshot=fee, lp_snapshot=None,
        lp_integrity_mode="DISABLED_SINGLE_STREAM",
        verdict="ALLOW", proof_digest="security-proof",
        phx1_structural_policy="SHADOW",
        original_phx1_structural_verdict="HARD_BLOCK",
        effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
        shadow_warning_reason_tokens=(
            "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK",
            "PHX1_FEE_GATE_SCAM_LIKELY",
        ),
        organicity_status="UNVERIFIED",
        manual_review_required=True,
        phx1_policy_digest="policy-digest",
    )
    delivery_context = {
        "candidate": {
            "token_mint": APPA_MINT,
            "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
            "token_name": "Appa",
            "symbol_or_name": "Appa",
            "pair_address": APPA_PAIR,
            "migration_time_utc": (migration.isoformat()
                                   .replace("+00:00", "Z")),
            "canonical_volume_5m": {
                "schema_version": "phx2_canonical_swap_volume_v1",
                "status": "INSUFFICIENT_DATA",
                "mint": APPA_MINT,
                "window_seconds": 300,
                "gross_volume_usd": None,
                "net_quote_flow_usd": None,
                "sample_count": 0,
                "observe_only": True,
            },
            "fee_gate_lifecycle": {
                "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
                "lifecycle_state": "DURABLE_SCAM_LOCKED",
                "evidence_proof_digest": "fee-proof",
            },
        },
        "market_context": {
            "current_market_cap_usd": "86400",
            "liquidity_usd": "24407",
            "central_ath": {"ath_market_cap": "179400"},
            "risk_assessment": {
                "risk_label": "RISK_MEDIUM",
                "risk_reasons": [
                    "EARLY_VOLATILITY", "MARKET_INCOMPLETE_REPEATED"],
            },
        },
        "activation": {"migration_market_cap_usd": "30020"},
        "security_decision": security,
    }
    snapshot = SimpleNamespace(
        token_mint=APPA_MINT, tier_token="Tier 1",
        current_market_cap_usd="86400")
    return snapshot, delivery_context, now.isoformat().replace("+00:00", "Z")


def test_appa_backfill_alert_renders_the_clean_operator_body():
    snapshot, delivery_context, now_utc = _appa_delivery_inputs()
    data = build_ping_data(
        mint=APPA_MINT,
        composed_snapshot=snapshot,
        delivery_context=delivery_context,
        now_utc=now_utc,
    )
    body = compose_telegram_ping(data).text
    lines = body.splitlines()

    assert lines[0] == "<b>🔥 PHOENIX — Appa [Tier 1]</b>"
    assert lines[1] == f"<code>{APPA_MINT}</code>"
    assert "• MC: $86.4k | Obs ATH: $179.4k | Mig: $30k" in lines
    assert "• Floor: -52% | Age: 41m | Vol 5m: —" in lines
    assert "• LP: —" in lines
    assert "• Coverage: Partial (restart backfill)" in lines
    assert "• Fee Gate: Scam Likely (6)" in lines
    assert ("• Bribes/AMM: 0.8% | Creator: 78.4% | "
            "Bribes/tx: 71,020 lamports") in lines
    assert "• Read: sticky lock" in lines
    assert "• Policy: SHADOW BLOCK — durable scam lock" in lines
    assert "• Risk: Medium — early volatility" in lines
    assert "• Median last-20sw: 0.000058 SOL | p25/p75: 0.000028 / 0.000551" \
        in lines
    assert "• Median 5m: 0.000029 SOL (n=322) | base-fee cov: 100%" in lines
    assert "⛽️ Priority Fee: 11,574 lam (n=20)" in lines
    assert "• Late-sequence stress state" in lines

    # Internal implementation strings must never reach the operator body.
    for banned in (
        "PARTIAL_SINCE_ADMISSION",
        "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",
        "NO APPROVED LIQUIDITY QUALITY RULE",
        "NO APPROVED SHAPE RULE",
        "MARKET_INCOMPLETE_REPEATED",
        "market data incomplete",
        "ORGANICITY",
        "MANUAL REVIEW REQUIRED",
        "LP Integrity",
        "Quote-side",
        "DATA UNAVAILABLE",
        "INSUFFICIENT DATA",
        "DEXSCREENER",
        "rule N/A",
        "PHX1 STRUCTURAL POLICY",
        # 2026-07-29 final cleanup: Participation renders nowhere and raw
        # enum identifiers never render.
        "Participation",
        "SOL/min",
        "Events:",
        "RISK_MEDIUM",
        "sticky_lock",
        "SCAM Likely",
    ):
        assert banned not in body, banned

    # The diagnostics stay intact on the artifact surface.
    assert data.field_reason_codes["volume"] == (
        "CANONICAL_SWAP_SAMPLE_INSUFFICIENT",)
    assert data.field_reason_codes["liquidity"] == (
        "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",)
    assert data.field_reason_codes["post_migration_ath"] == (
        "ATH_COVERAGE_PARTIAL_SINCE_ADMISSION",)
    assert data.field_reason_codes["shape_5m"] == (
        "NO_APPROVED_ANTE_SHAPE_RULE",)
    assert data.ath_coverage == "PARTIAL_SINCE_ADMISSION"
    assert data.policy_reason_display == "durable scam lock"

    # The rendered body passes the runtime redaction scanner.
    assert production_live_artifacts.scan_text(body) == []


def test_live_unknown_metadata_alert_resolves_once_canonical_state_exists():
    """335Sdx… regression: identical candidate, with and without the stamped
    canonical metadata state."""

    bare = {
        "token_mint": LIVE_MINT,
        "discovery_provenance": "LIVE_YELLOWSTONE",
        "token_name": None,
        "symbol_or_name": None,
        "pair_address": LIVE_PAIR,
    }
    identity, source = resolve_token_identity(
        mint=LIVE_MINT, candidate=bare, delivery_context={})
    assert (identity, source) == (
        UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE)

    resolver = TokenMetadataResolver(now_iso_fn=_Clock().now_iso)
    resolver.merge(
        LIVE_MINT, token_name="Three Three Five", token_symbol="TTF",
        source="PAID_MARKET_PRIMARY_OVERVIEW")
    stamped = dict(bare)
    stamped["canonical_token_metadata"] = resolver.snapshot(LIVE_MINT)
    identity, source = resolve_token_identity(
        mint=LIVE_MINT, candidate=stamped, delivery_context={})
    assert (identity, source) == (
        "Three Three Five ($TTF)", TOKEN_METADATA_CANONICAL_LIVE)


# =========================================================================
# 5. Quality-review artifacts explain the exact missing requirement
# =========================================================================


def _quality_record(candidate_overrides=None, market_overrides=None):
    candidate = {
        "candidate_id": "cand-1",
        "token_mint": APPA_MINT,
        "token_name": "Appa",
        "symbol_or_name": "Appa",
        "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
        "pair_address": APPA_PAIR,
        "migration_time_utc": "2026-07-28T05:24:37Z",
        "canonical_volume_5m": {
            "status": "INSUFFICIENT_DATA",
            "mint": APPA_MINT,
            "sample_count": 0,
            "coverage_seconds": "0",
        },
        "canonical_token_metadata": {
            "token_mint": APPA_MINT,
            "token_name": "Appa",
            "token_symbol": None,
            "metadata_status": "RESOLVED",
            "metadata_source": "DEXSCREENER_RESTART_BACKFILL",
            "metadata_first_requested_at": "2026-07-28T05:59:20Z",
            "metadata_resolved_at": "2026-07-28T05:59:20Z",
            "metadata_attempt_count": 1,
            "metadata_failure_reason": None,
        },
    }
    candidate.update(candidate_overrides or {})
    market = {
        "current_market_cap_usd": "86400",
        "liquidity_usd": "24407",
        "pumpswap_reserve": {
            "reserve_validation_status": "VALID",
            "actual_pool_tvl_usd": "5020",
            "actual_quote_liquidity_usd": "5000",
            "quote_price_observed_at_utc": "2026-07-28T06:05:20Z",
        },
    }
    market.update(market_overrides or {})
    return build_ping_quality_record(
        candidate=candidate,
        recheck={"reason": "SENT_OK_COMMITTED", "market_context": market},
        security=None,
        observed_at_utc=NOW,
    )


def test_quality_review_explains_backfill_and_live_volume_requirements():
    backfill = _quality_record()
    review = backfill["canonical_volume_review"]
    assert review["status"] == "INSUFFICIENT_DATA"
    assert review["missing_requirement"] == (
        CANONICAL_VOLUME_MISSING_REQUIREMENT_BACKFILL)

    live = _quality_record(candidate_overrides={
        "discovery_provenance": "LIVE_YELLOWSTONE"})
    assert live["canonical_volume_review"]["missing_requirement"] == (
        CANONICAL_VOLUME_MISSING_REQUIREMENT_LIVE)

    valid = _quality_record(candidate_overrides={
        "canonical_volume_5m": {
            "status": "VALID", "mint": APPA_MINT, "sample_count": 48,
            "coverage_seconds": "299", "gross_volume_usd": "2732",
            "net_quote_flow_usd": "-843"},
    })
    assert valid["canonical_volume_review"]["missing_requirement"] is None
    assert valid["canonical_volume_review"]["sample_count"] == 48


def test_quality_review_carries_metadata_and_reserve_diagnostics():
    record = _quality_record()
    assert record["token_metadata"]["metadata_status"] == "RESOLVED"
    assert record["token_metadata"]["metadata_source"] == (
        "DEXSCREENER_RESTART_BACKFILL")
    assert record["actual_reserve_review"]["reserve_validation_status"] == (
        "VALID")
    assert record["actual_reserve_review"]["actual_pool_tvl_usd"] == "5020"
    assert ping_quality_record_is_redaction_safe(record) is True


def test_quality_review_redaction_still_bans_credential_shaped_keys():
    record = _quality_record()
    assert ping_quality_record_is_redaction_safe(
        {**record, "telegram_token": "x"}) is False
    assert ping_quality_record_is_redaction_safe(
        {**record, "endpoint_secret": "x"}) is False
    assert ping_quality_record_is_redaction_safe(
        {**record, "nested": {"outbound_body": "x"}}) is False


def test_runtime_artifact_scanner_accepts_the_new_metadata_fields(tmp_path):
    """The per-tick artifact scanner treats unknown provider-name strings as
    danger needles that fail a run closed.  Every metadata source token the
    resolver can persist must therefore stay inside the exact-equality
    allowlist or be provider-neutral."""

    import json as json_module

    quality = _quality_record(candidate_overrides={
        "canonical_token_metadata": {
            "token_mint": APPA_MINT,
            "token_name": "Appa",
            "token_symbol": None,
            "metadata_status": "RESOLVED",
            "metadata_source": "DEXSCREENER_RESTART_BACKFILL",
            "metadata_first_requested_at": "2026-07-28T05:59:20Z",
            "metadata_resolved_at": "2026-07-28T05:59:20Z",
            "metadata_attempt_count": 3,
            "metadata_failure_reason": None,
            "metadata_sources_attempted": [
                "DEXSCREENER_RESTART_BACKFILL",
                "RESTART_BACKFILL_FRESH_MARKET_GATE",
                "PAID_MARKET_PRIMARY_OVERVIEW",
                "CANDIDATE_STATE",
            ],
        },
    })
    (tmp_path / "phx2_ping_quality_review.jsonl").write_text(
        json_module.dumps(quality) + "\n", encoding="utf-8")
    scan = production_live_artifacts.run_redaction_scan(tmp_path)
    assert scan["total_unsafe_hits"] == 0, scan["per_file_hits"]
    assert scan["redaction_status"] == "REDACTED"
    assert scan["positive_control_ok"] is True
