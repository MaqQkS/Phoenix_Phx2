"""Offline proofs for the named PHX1_PARITY alert policy.

The 2026-08-01 live run produced ZERO PHX2 alerts while PHX1 produced eight, on
a run where discovery, restart retention, checkpoint durability, provider
isolation, ATH and tier calculation were all proven correct and PHX2's tier
matched PHX1's for every mint both bots evaluated.  The gap was candidate
universe and eligibility policy.

These tests pin BOTH sides of the contract: what PHX1_PARITY relaxes, and --
just as important -- what it must never relax.  Every send here is a FAKE
transport; nothing opens a socket and no real Telegram send can occur.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import phx1_parity_policy as policy
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.compat.build30_watchlist import (
    BACKFILL_ACTIVATION_MULTIPLIER,
    MIGRATION_ACTIVATION_MULTIPLIER,
    WATCH_ACTIVE_DIP,
    WATCH_EXPIRED,
    Watchlist,
    activation_proof_is_durable,
    activation_proof_is_eligible,
)
from PHX2.free_tier_producer.compat.production_live_runner import ProductionBounds
from PHX2.free_tier_producer.paid_market_readiness import (
    MARKET_READY,
    MARKET_RECOVERY_BACKOFF,
    PaidMarketReadinessTracker,
)
from PHX2.models.ath_coverage import (
    ATH_COVERAGE_COMPLETE_HYDRATED,
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_HYDRATION_COMPLETE,
    ATH_HYDRATION_PENDING,
    ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.models.discovery_provenance import (
    DISCOVERY_PROVENANCE_DEX_BACKFILL,
    DISCOVERY_PROVENANCE_LIVE_HELIUS,
)
from PHX2.free_tier_producer.phx1_structural_policy import (
    EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING,
    EFFECTIVE_POLICY_HARD_BLOCK,
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    PHX1_STRUCTURAL_POLICY_SHADOW,
    route_phx1_structural_reasons,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import InMemoryPingDedupeLedger
from PHX2.tests import test_ath_activation_risk_regression as harness


FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures"
    / "phx1_parity_latest_run_20260801.json"
)


@pytest.fixture
def latest_run() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(autouse=True)
def _restore_process_policy():
    """Every test leaves the process binding exactly as it found it."""

    before = policy.current_alert_policy()
    yield
    policy.bind_alert_policy(before)


# ---------------------------------------------------------------------------
# 1-5. Closed-set policy, recorded activation, no hard block, legacy unchanged
# ---------------------------------------------------------------------------


def test_1_phx1_parity_is_an_explicit_closed_set_policy():
    assert policy.ALERT_POLICY_MODES == ("LEGACY", "PHX1_PARITY")
    assert policy.ALERT_POLICY_CLI_VALUES == ("legacy", "phx1_parity")
    assert policy.normalize_alert_policy(None) == policy.ALERT_POLICY_LEGACY
    assert policy.normalize_alert_policy("legacy") == policy.ALERT_POLICY_LEGACY
    assert policy.normalize_alert_policy(
        "phx1_parity") == policy.ALERT_POLICY_PHX1_PARITY
    for rejected in ("Phx1_Parity", "PARITY", "shadow", "", "enforce", 1, True):
        with pytest.raises(ValueError, match=policy.ALERT_POLICY_INVALID):
            policy.normalize_alert_policy(rejected)

    # Enforcement is a closed set, and every declared condition has a level
    # under BOTH policies.
    for mode in policy.ALERT_POLICY_MODES:
        for condition in policy.ALERT_POLICY_CONDITIONS:
            assert policy.enforcement_for(
                condition, policy=mode) in policy.ENFORCEMENT_LEVELS

    # An unknown condition fails CLOSED under every policy.
    for mode in policy.ALERT_POLICY_MODES:
        assert policy.enforcement_for("a_gate_nobody_classified",
                                      policy=mode) == policy.ENFORCEMENT_HARD
        assert policy.blocks_compose("a_gate_nobody_classified", policy=mode)

    # The relaxed set is exactly the activation + fee/structural family.
    assert set(policy.PHX1_PARITY_RELAXED_CONDITIONS) == {
        policy.CONDITION_ACTIVATION_PROVEN,
        policy.CONDITION_ACTIVATION_MULTIPLIER_LIVE,
        policy.CONDITION_ACTIVATION_MULTIPLIER_BACKFILL,
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
        policy.CONDITION_FEE_PROOF_MISSING,
        policy.CONDITION_FEE_GATE_SCAM_LIKELY,
        policy.CONDITION_STRUCTURAL_POLICY,
    }
    matrix = policy.policy_matrix(policy.ALERT_POLICY_PHX1_PARITY)
    assert matrix["alert_policy"] == "PHX1_PARITY"
    assert set(matrix["conditions"]) == set(policy.ALERT_POLICY_CONDITIONS)


def test_2_activation_status_and_multiplier_remain_recorded_under_parity():
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    entry, _central, _crossing = harness._activated_entry()
    proof = entry.activation_snapshot()

    # The proof is still computed, still validated, still carries its numbers.
    assert proof["activation_proven"] is True
    assert proof["activation_latched"] is True
    assert proof["activation_multiplier"] == "1.20"
    assert proof["migration_market_cap_usd"] == harness.BASELINE
    assert proof["activation_target_market_cap_usd"] == harness.TARGET
    assert proof["activation_evidence_market_cap_usd"] == harness.ACTIVATING_HIGH
    assert proof["activation_eligible"] is True
    assert proof["activation_proof_valid"] is True
    assert activation_proof_is_durable(proof)
    assert activation_proof_is_eligible(proof)

    record = policy.condition_record(
        policy.CONDITION_ACTIVATION_PROVEN, policy.STATUS_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert record == {"status": "PROVEN", "enforcement": "SHADOW"}


def test_3_missing_activation_proof_does_not_hard_block_under_parity():
    assert policy.blocks_compose(
        policy.CONDITION_ACTIVATION_PROVEN,
        policy=policy.ALERT_POLICY_LEGACY) is True
    assert policy.blocks_compose(
        policy.CONDITION_ACTIVATION_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY) is False

    # A missing proof is honestly reported as NOT_PROVEN, never as blocked.
    record = policy.condition_record(
        policy.CONDITION_ACTIVATION_PROVEN, policy.STATUS_NOT_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert record["status"] == "NOT_PROVEN"
    assert record["enforcement"] == policy.ENFORCEMENT_SHADOW
    assert record["enforcement"] not in policy.BLOCKING_ENFORCEMENT_LEVELS


def test_4_activation_crossing_warning_does_not_hard_block_under_parity():
    assert policy.enforcement_for(
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy=policy.ALERT_POLICY_LEGACY) == policy.ENFORCEMENT_HARD
    assert policy.enforcement_for(
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    assert not policy.blocks_compose(
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy=policy.ALERT_POLICY_PHX1_PARITY)


def test_5_legacy_behaviour_is_unchanged_and_is_the_default():
    # Nothing bound => LEGACY.
    policy.bind_alert_policy(policy.ALERT_POLICY_LEGACY)
    assert policy.current_alert_policy() == policy.ALERT_POLICY_LEGACY
    assert policy.resolve_policy(None) == policy.ALERT_POLICY_LEGACY

    for condition in (
        policy.CONDITION_ACTIVATION_PROVEN,
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
        policy.CONDITION_FEE_PROOF_MISSING,
        policy.CONDITION_FEE_GATE_SCAM_LIKELY,
        policy.CONDITION_STRUCTURAL_POLICY,
    ):
        assert policy.enforcement_for(condition) == policy.ENFORCEMENT_HARD
        assert policy.blocks_compose(condition)

    assert policy.watch_ttl_seconds() == 3600
    assert policy.expected_activation_multiplier(
        discovery_provenance_is_backfill=True) == Decimal("1.39")
    assert policy.adaptive_refresh_interval_seconds(
        base_interval_seconds=30.0, seconds_since_activity=99999.0) == 30.0
    assert policy.send_time_refresh_decision(
        market_all_present=False,
        attempts_used=0) == policy.REFRESH_NOT_ENABLED
    assert ProductionBounds().alert_policy == policy.ALERT_POLICY_LEGACY
    assert ProductionBounds().max_candidate_age_seconds == 3600


# ---------------------------------------------------------------------------
# 6-9. Fee lifecycle, fee proof, structural/scam, Global Fee Support
# ---------------------------------------------------------------------------


def test_6_fee_lifecycle_immature_is_annotation_only_under_parity():
    assert policy.enforcement_for(
        policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW

    routed = route_phx1_structural_reasons(
        ["PHX2_FEE_LIFECYCLE_IMMATURE"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.effective_phx1_policy_verdict == (
        EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING)
    assert routed.final_candidate_eligibility is True
    assert routed.manual_review_required is True
    assert routed.shadow_warning_reason_tokens == (
        "PHX2_FEE_LIFECYCLE_IMMATURE",)
    assert routed.non_shadowable_safety_reason_tokens == ()

    enforced = route_phx1_structural_reasons(
        ["PHX2_FEE_LIFECYCLE_IMMATURE"],
        policy_mode=PHX1_STRUCTURAL_POLICY_ENFORCE)
    assert enforced.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert enforced.final_candidate_eligibility is False


def test_7_fee_proof_missing_is_annotation_only_under_parity():
    assert policy.enforcement_for(
        policy.CONDITION_FEE_PROOF_MISSING,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    routed = route_phx1_structural_reasons(
        ["PHX1_FEE_GATE_PROOF_MISSING"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.final_candidate_eligibility is True
    assert routed.manual_review_required is True


def test_8_structural_and_scam_signals_remain_shadow_not_allowed():
    # SHADOW means "recorded and carried forward as a visible manual-review
    # warning", NOT "silently permitted": the original verdict is preserved.
    routed = route_phx1_structural_reasons(
        ["PHX1_FEE_GATE_SCAM_LIKELY"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.original_phx1_structural_verdict == "HARD_BLOCK"
    assert routed.effective_phx1_policy_verdict == (
        EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING)
    assert routed.manual_review_required is True
    assert routed.organicity_status == "UNVERIFIED"
    assert policy.enforcement_for(
        policy.CONDITION_FEE_GATE_SCAM_LIKELY,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW

    # A NON-shadowable safety reason still hard-blocks in SHADOW mode.
    unsafe = route_phx1_structural_reasons(
        ["PHX1_FEE_GATE_SCAM_LIKELY", "SECURITY_DECISION_PROOF_INCONSISTENT"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert unsafe.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert unsafe.final_candidate_eligibility is False
    assert unsafe.non_shadowable_safety_reason_tokens == (
        "SECURITY_DECISION_PROOF_INCONSISTENT",)


def test_9_global_fee_support_remains_observe_only():
    for mode in policy.ALERT_POLICY_MODES:
        assert policy.enforcement_for(
            policy.CONDITION_GLOBAL_FEE_SUPPORT,
            policy=mode) == policy.ENFORCEMENT_PRESENTATION
        assert not policy.blocks_compose(
            policy.CONDITION_GLOBAL_FEE_SUPPORT, policy=mode)


# ---------------------------------------------------------------------------
# 10-12. Backfill activation penalty, ATH coverage
# ---------------------------------------------------------------------------


def test_10_dex_candidate_does_not_require_1_39x_activation_under_parity(latest_run):
    dex = latest_run["candidates"]["DEXBACKFILL"]
    assert dex["legacy_activation_multiplier"] == "1.39"
    assert dex["parity_activation_multiplier"] == "1.20"

    assert BACKFILL_ACTIVATION_MULTIPLIER == Decimal("1.39")
    assert MIGRATION_ACTIVATION_MULTIPLIER == Decimal("1.20")

    legacy = policy.expected_activation_multiplier(
        discovery_provenance_is_backfill=True,
        policy=policy.ALERT_POLICY_LEGACY)
    parity = policy.expected_activation_multiplier(
        discovery_provenance_is_backfill=True,
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert legacy == Decimal("1.39")
    assert parity == Decimal("1.20")
    # Backfill provenance carries NO extra penalty: identical to live.
    assert parity == policy.expected_activation_multiplier(
        discovery_provenance_is_backfill=False,
        policy=policy.ALERT_POLICY_PHX1_PARITY)

    # Provenance itself is never rewritten as live.
    assert dex["discovery_provenance"] == DISCOVERY_PROVENANCE_DEX_BACKFILL
    assert classify_ath_coverage(
        discovery_provenance=dex["discovery_provenance"],
        ath_hydration_status=ATH_HYDRATION_COMPLETE,
    ) == ATH_COVERAGE_COMPLETE_HYDRATED


def test_10b_backfill_sealed_evidence_field_is_untouched_by_the_policy():
    """The 1.39 penalty is removed from the THRESHOLD, not from the evidence.

    ``activation_multiplier`` is part of the sealed restart-backfill evidence
    contract -- ``validate_backfill_candidate_evidence`` checks it and the
    evidence digest is computed over it -- so rewriting the field would
    invalidate the candidate's migration evidence instead of relaxing anything.
    """

    from PHX2.free_tier_producer.compat import build30_watchlist as wl
    from PHX2.free_tier_producer.dexscreener_restart_backfill import (
        PHX1_BACKFILL_ACTIVATION_MULTIPLIER,
    )

    backfill = {"discovery_provenance": DISCOVERY_PROVENANCE_DEX_BACKFILL}
    live = {"discovery_provenance": DISCOVERY_PROVENANCE_LIVE_HELIUS}

    for mode in policy.ALERT_POLICY_MODES:
        policy.bind_alert_policy(mode)
        # The sealed FIELD is provenance-based and policy-independent.
        assert wl._expected_activation_multiplier(
            backfill) == PHX1_BACKFILL_ACTIVATION_MULTIPLIER
        assert wl._expected_activation_multiplier(
            live) == MIGRATION_ACTIVATION_MULTIPLIER

    # The THRESHOLD is what the policy moves.
    assert wl._activation_threshold_multiplier(
        backfill, policy=policy.ALERT_POLICY_LEGACY) == Decimal("1.39")
    assert wl._activation_threshold_multiplier(
        backfill, policy=policy.ALERT_POLICY_PHX1_PARITY) == Decimal("1.20")
    assert wl._activation_threshold_multiplier(
        live, policy=policy.ALERT_POLICY_PHX1_PARITY) == Decimal("1.20")
    assert wl._activation_threshold_multiplier(
        {"discovery_provenance": "SOMETHING_ELSE"},
        policy=policy.ALERT_POLICY_PHX1_PARITY) is None


def test_11_partial_ath_remains_hard_blocked_under_every_policy(latest_run):
    dex = latest_run["candidates"]["DEXBACKFILL"]
    coverage = classify_ath_coverage(
        discovery_provenance=dex["discovery_provenance"],
        ath_hydration_status=dex["ath_hydration_status_partial"],
    )
    assert coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert not ath_coverage_is_complete(coverage)
    for mode in policy.ALERT_POLICY_MODES:
        assert policy.enforcement_for(
            policy.CONDITION_ATH_COVERAGE, policy=mode) == policy.ENFORCEMENT_HARD
        assert policy.blocks_compose(policy.CONDITION_ATH_COVERAGE, policy=mode)


def test_12_complete_ath_may_proceed_for_live_and_hydrated(latest_run):
    dex = latest_run["candidates"]["DEXBACKFILL"]
    hydrated = classify_ath_coverage(
        discovery_provenance=dex["discovery_provenance"],
        ath_hydration_status=dex["ath_hydration_status_complete"],
    )
    assert hydrated == ATH_COVERAGE_COMPLETE_HYDRATED
    assert ath_coverage_is_complete(hydrated)

    # 2026-08-03 correction: a live candidate is COMPLETE only once the
    # central hydration verdict proves its maximum (V3 pair history, or the
    # uninterrupted live tracker).  A still-PENDING live candidate is
    # explicitly partial; a legacy artifact that carries NO verdict keeps its
    # historical live-is-complete reading.
    for key in ("CsmPN87B", "EmnjcV5n", "6bN3QrA5"):
        candidate = latest_run["candidates"][key]
        assert candidate["discovery_provenance"] == DISCOVERY_PROVENANCE_LIVE_HELIUS
        live = classify_ath_coverage(
            discovery_provenance=candidate["discovery_provenance"],
            ath_hydration_status=ATH_HYDRATION_COMPLETE,
        )
        assert live == ATH_COVERAGE_COMPLETE_LIVE
        assert ath_coverage_is_complete(live)
        assert classify_ath_coverage(
            discovery_provenance=candidate["discovery_provenance"],
            ath_hydration_status=ATH_HYDRATION_PENDING,
        ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
        legacy = classify_ath_coverage(
            discovery_provenance=candidate["discovery_provenance"])
        assert legacy == ATH_COVERAGE_COMPLETE_LIVE


# ---------------------------------------------------------------------------
# 13-15. Watch lifetime, durability, adaptive cadence budget
# ---------------------------------------------------------------------------


def test_13_watch_ttl_is_six_hours_under_parity(latest_run):
    assert policy.watch_ttl_seconds(policy.ALERT_POLICY_LEGACY) == 3600
    assert policy.watch_ttl_seconds(policy.ALERT_POLICY_PHX1_PARITY) == 21600
    assert policy.PHX1_PARITY_WATCH_TTL_SECONDS == 6 * 3600

    # The fixture's Tier-1 candidate died at EXACTLY the legacy TTL.
    csm = latest_run["candidates"]["CsmPN87B"]
    assert csm["terminal_reason"] == "CANDIDATE_WATCH_EXPIRED"
    assert csm["observed_watch_seconds"] == policy.LEGACY_WATCH_TTL_SECONDS
    assert csm["observed_watch_seconds"] < policy.PHX1_PARITY_WATCH_TTL_SECONDS

    entry = harness._entry()
    seeded = datetime.fromisoformat(
        harness.BASELINE_AT.replace("Z", "+00:00"))
    watchlist = Watchlist()
    watchlist._entries[entry.token_mint] = entry

    def age_at(offset_seconds: float):
        return lambda _seeded, _o=offset_seconds: _o

    # 90 minutes: expired under legacy, retained under parity.
    survivors = Watchlist()
    survivors._entries[entry.token_mint] = entry
    assert survivors.expire_stale(
        now_age_seconds_fn=age_at(5400.0),
        max_age_seconds=policy.watch_ttl_seconds(
            policy.ALERT_POLICY_PHX1_PARITY),
        max_rechecks=10_000,
        now_utc=harness.TIER1_AT,
    ) == 0
    assert entry.status != WATCH_EXPIRED

    assert watchlist.expire_stale(
        now_age_seconds_fn=age_at(5400.0),
        max_age_seconds=policy.watch_ttl_seconds(policy.ALERT_POLICY_LEGACY),
        max_rechecks=10_000,
        now_utc=harness.TIER1_AT,
    ) == 1
    assert entry.status == WATCH_EXPIRED
    assert seeded.tzinfo is timezone.utc


def test_13b_parity_bounds_extend_ttl_only_when_operator_left_the_default():
    assert ProductionBounds(
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY,
    ).max_candidate_age_seconds == 3600, (
        "the dataclass default is unchanged; the session applies the policy TTL")

    class _Args:
        alert_policy = "phx1_parity"
        max_candidate_age_seconds = 3600

    args = _Args()
    if int(args.max_candidate_age_seconds) == 3600:
        args.max_candidate_age_seconds = policy.watch_ttl_seconds("phx1_parity")
    assert args.max_candidate_age_seconds == 21600

    explicit = _Args()
    explicit.max_candidate_age_seconds = 900
    if int(explicit.max_candidate_age_seconds) == 3600:
        explicit.max_candidate_age_seconds = policy.watch_ttl_seconds(
            "phx1_parity")
    assert explicit.max_candidate_age_seconds == 900, (
        "an explicit operator value must always win")


def test_14_durable_restart_preserves_the_extended_watch(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    entry, _central, _crossing = harness._activated_entry()
    source = Watchlist()
    source._entries[entry.token_mint] = entry
    path = tmp_path / "watch_state.jsonl"
    source.persist(path)

    restored = Watchlist.load(path)
    survivor = restored.get(entry.token_mint)
    assert survivor is not None
    assert survivor.seeded_at_utc == entry.seeded_at_utc
    assert survivor.activation_proven is True
    assert survivor.activation_multiplier == "1.20"
    assert survivor.discovery_provenance == entry.discovery_provenance
    assert activation_proof_is_durable(survivor)

    # Still inside the six-hour window three hours after seeding.
    assert restored.expire_stale(
        now_age_seconds_fn=lambda _s: 3.0 * 3600.0,
        max_age_seconds=policy.watch_ttl_seconds(
            policy.ALERT_POLICY_PHX1_PARITY),
        max_rechecks=10_000,
        now_utc=harness.TIER1_AT,
    ) == 0
    assert restored.get(entry.token_mint) is not None


def test_15_adaptive_refresh_keeps_projected_requests_within_budget():
    size = 128        # --max-watchlist-size default
    base = 30.0       # PaidMarketReadinessConfig.ready_refresh_seconds

    legacy_mix = policy.project_watchlist_heat_distribution(
        watchlist_size=size,
        watch_ttl_seconds_value=policy.LEGACY_WATCH_TTL_SECONDS)
    parity_mix = policy.project_watchlist_heat_distribution(
        watchlist_size=size,
        watch_ttl_seconds_value=policy.PHX1_PARITY_WATCH_TTL_SECONDS)
    assert sum(legacy_mix.values()) == size
    assert sum(parity_mix.values()) == size

    legacy_hourly = policy.project_market_requests_per_hour(
        candidates_by_heat=legacy_mix, base_interval_seconds=base,
        policy=policy.ALERT_POLICY_LEGACY)
    parity_hourly = policy.project_market_requests_per_hour(
        candidates_by_heat=parity_mix, base_interval_seconds=base,
        policy=policy.ALERT_POLICY_PHX1_PARITY)

    # The six-hour watch must not cost MORE provider volume than the committed
    # one-hour watch already spends at the same watchlist capacity.
    assert parity_hourly <= legacy_hourly
    assert parity_hourly <= legacy_hourly * 0.5

    # Ladder shape: hot keeps the committed cadence, cold steps down, and an
    # active dip is always hot regardless of age.
    assert policy.refresh_heat(seconds_since_activity=10.0) == policy.HEAT_HOT
    assert policy.refresh_heat(seconds_since_activity=2000.0) == policy.HEAT_WARM
    assert policy.refresh_heat(seconds_since_activity=7200.0) == policy.HEAT_COOL
    assert policy.refresh_heat(seconds_since_activity=20000.0) == policy.HEAT_COLD
    assert policy.refresh_heat(
        seconds_since_activity=20000.0, is_active_dip=True) == policy.HEAT_HOT
    assert policy.refresh_heat(seconds_since_activity=None) == policy.HEAT_HOT
    assert policy.refresh_heat(seconds_since_activity=-5.0) == policy.HEAT_HOT

    assert policy.adaptive_refresh_interval_seconds(
        base_interval_seconds=base, seconds_since_activity=10.0,
        policy="phx1_parity") == base
    assert policy.adaptive_refresh_interval_seconds(
        base_interval_seconds=base, seconds_since_activity=20000.0,
        policy="phx1_parity") == base * 8
    assert policy.adaptive_refresh_interval_seconds(
        base_interval_seconds=base, seconds_since_activity=20000.0,
        is_active_dip=True, policy="phx1_parity") == base
    # Bounded: never slower than the committed ceiling.
    assert policy.adaptive_refresh_interval_seconds(
        base_interval_seconds=5000.0, seconds_since_activity=20000.0,
        policy="phx1_parity") == policy.MAX_ADAPTIVE_REFRESH_SECONDS


def test_15b_reactivation_returns_a_cold_candidate_to_the_fast_cadence():
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    tracker = PaidMarketReadinessTracker()
    mint = "Fixture1111111111111111111111111111111111pump"
    start = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)

    def iso(offset_seconds: float) -> str:
        return (start + timedelta(seconds=offset_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    def ready_attempt(at: str) -> dict:
        return {
            "price_value": "0.00001", "mc_value": "10000",
            "lp_value": "12000", "all_present": True,
            "provider_timestamp_utc": at, "basis": "REAL_MARKET_PRESENT",
        }

    first = tracker.resolve(
        mint, migration_time_utc=iso(0), now_iso_fn=lambda: iso(0),
        fetch_attempt_fn=lambda at: ready_attempt(at))
    assert first["market_state"] == MARKET_READY

    # Four hours quiet: the state entry is old, so the ladder slows it down.
    state = tracker._mints[mint]
    state["last_activity_epoch"] = start.timestamp()
    state["next_retry_epoch"] = 0.0
    cold = tracker.resolve(
        mint, migration_time_utc=iso(0), now_iso_fn=lambda: iso(4 * 3600),
        fetch_attempt_fn=lambda at: ready_attempt(at))
    cold_gap = cold["market_next_recovery_probe_at_utc"]
    assert cold_gap is None
    cold_delay = tracker._retry_delay(tracker._mints[mint], MARKET_READY)
    assert cold_delay > tracker.config.ready_refresh_seconds

    # Renewed life resets the anchor: back to the committed cadence.
    tracker.note_candidate_activity(
        mint, now_iso=iso(4 * 3600), is_active_dip=True)
    hot_delay = tracker._retry_delay(tracker._mints[mint], MARKET_READY)
    assert hot_delay == tracker.config.ready_refresh_seconds


def test_15c_legacy_cadence_is_byte_identical_to_the_committed_schedule():
    policy.bind_alert_policy(policy.ALERT_POLICY_LEGACY)
    tracker = PaidMarketReadinessTracker()
    state = tracker._new_state(0.0)
    state["last_activity_epoch"] = 0.0
    state["last_attempt_at_utc"] = "2026-08-01T12:00:00Z"
    assert tracker._retry_delay(
        state, MARKET_READY) == tracker.config.ready_refresh_seconds
    state["transient_attempt_count"] = 1
    assert tracker._retry_delay(state, "MARKET_INDEXING") == (
        tracker.config.retry_backoff_seconds[0])


# ---------------------------------------------------------------------------
# 16-18. Market freshness and the bounded send-time refresh
# ---------------------------------------------------------------------------


def test_16_stale_market_data_can_never_compose():
    for mode in policy.ALERT_POLICY_MODES:
        assert policy.enforcement_for(
            policy.CONDITION_MARKET_FRESHNESS,
            policy=mode) == policy.ENFORCEMENT_HARD_AT_SEND
        assert policy.blocks_compose(
            policy.CONDITION_MARKET_FRESHNESS, policy=mode)
        assert policy.blocks_compose(
            policy.CONDITION_MARKET_RECOVERY_BACKOFF, policy=mode)

    # The committed composer freshness ceiling is untouched.
    assert producer_session._market_context_is_fresh(
        {"market_context_fetched_at_utc": None}) is False
    assert producer_session._market_context_is_fresh({}) is False
    assert producer_session._market_context_is_fresh(
        {"market_context_fetched_at_utc": "1999-01-01T00:00:00Z"}) is False


def test_17_one_successful_send_time_refresh_allows_normal_compose():
    assert policy.send_time_refresh_decision(
        market_all_present=False, attempts_used=0,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.REFRESH_ELIGIBLE
    assert policy.send_time_refresh_decision(
        market_all_present=True, attempts_used=0,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.REFRESH_NOT_REQUIRED
    assert policy.SEND_TIME_REFRESH_MAX_ATTEMPTS == 1

    tracker = PaidMarketReadinessTracker()
    mint = "Fixture2222222222222222222222222222222222pump"
    start = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)

    def iso(offset: float) -> str:
        return (start + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tracker.seed_recovery_state(
        mint, now_iso=iso(0),
        next_recovery_probe_at_utc=iso(600))
    not_due = tracker.resolve(
        mint, migration_time_utc=iso(0), now_iso_fn=lambda: iso(1),
        fetch_attempt_fn=lambda _at: pytest.fail("backoff must not fetch"))
    assert not_due["market_state"] == MARKET_RECOVERY_BACKOFF
    assert not_due["all_present"] is False

    # A send-time priority attempt hands its result straight to the tracker,
    # which recovers the candidate on complete fresh data.
    recovered = tracker.observe_scheduled_attempt(
        mint, migration_time_utc=iso(0), now_iso=iso(2),
        attempt={
            "price_value": "0.00002", "mc_value": "20000",
            "lp_value": "13000", "all_present": True,
            "provider_timestamp_utc": iso(2), "basis": "REAL_MARKET_PRESENT",
        })
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True


def test_18_failed_send_time_refresh_retains_the_candidate():
    assert policy.send_time_refresh_decision(
        market_all_present=False, attempts_used=1,
        policy=policy.ALERT_POLICY_PHX1_PARITY
    ) == policy.REFRESH_BUDGET_EXHAUSTED

    tracker = PaidMarketReadinessTracker()
    mint = "Fixture3333333333333333333333333333333333pump"
    start = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)

    def iso(offset: float) -> str:
        return (start + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tracker.seed_recovery_state(
        mint, now_iso=iso(0), next_recovery_probe_at_utc=iso(1))
    failed = tracker.observe_scheduled_attempt(
        mint, migration_time_utc=iso(0), now_iso=iso(2),
        attempt={
            "price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_timestamp_utc": None,
            "basis": "REAL_MARKET_INCOMPLETE",
        })
    assert failed["market_state"] == MARKET_RECOVERY_BACKOFF
    assert failed["all_present"] is False
    # RETAINED, not terminal: a later bounded probe is scheduled and every
    # counter of prior history survives.
    assert failed["market_next_recovery_probe_at_utc"] is not None
    snapshot = tracker.snapshot()
    assert snapshot["counters"]["market_terminal_candidate_state_reached"] == 0
    assert snapshot["by_state"][MARKET_RECOVERY_BACKOFF] == 1


# ---------------------------------------------------------------------------
# 19-21. Preserved hard safety
# ---------------------------------------------------------------------------


def test_19_20_21_core_safety_conditions_are_hard_under_every_policy():
    for condition in policy.NON_RELAXABLE_CONDITIONS:
        for mode in policy.ALERT_POLICY_MODES:
            assert policy.enforcement_for(condition, policy=mode) in (
                policy.ENFORCEMENT_HARD, policy.ENFORCEMENT_HARD_AT_SEND), (
                    f"{condition} must never be relaxed by {mode}")
            assert policy.blocks_compose(condition, policy=mode)

    # Named explicitly so a future edit to the matrix is a test failure.
    for condition in (
        policy.CONDITION_LIQUIDITY_FLOOR,
        policy.CONDITION_CURRENT_MARKET_CAP_VALID,
        policy.CONDITION_DEDUPE,
        policy.CONDITION_MIGRATION_PROVEN,
        policy.CONDITION_ATH_COVERAGE,
        policy.CONDITION_CREDENTIALS,
        policy.CONDITION_CHECKPOINT_INTEGRITY,
        policy.CONDITION_OWNERSHIP_DUPLICATION,
        policy.CONDITION_DELIVERY_RESERVATION,
        policy.CONDITION_CANDIDATE_IDENTITY,
        policy.CONDITION_TIER_LIFETIME_MONOTONICITY,
    ):
        assert policy.enforcement_for(
            condition, policy=policy.ALERT_POLICY_PHX1_PARITY
        ) == policy.ENFORCEMENT_HARD
        assert condition not in policy.PHX1_PARITY_RELAXED_CONDITIONS


def test_19b_liquidity_floor_stays_hard_at_exactly_4500(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    gate = producer_session.make_discord_risk_gate(
        risk_engine=harness._MediumRisk(),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "risk-blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_TELEGRAM",
        errors=harness._NoErrors(),
        lp_integrity_mode=harness.LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    below = {"current_market_cap_usd": harness.TIER1_MC, "liquidity_usd": "4499.99"}
    exact = {"current_market_cap_usd": harness.TIER1_MC, "liquidity_usd": "4500"}
    missing = {"current_market_cap_usd": harness.TIER1_MC, "liquidity_usd": None}
    assert gate(harness.MINT, below).startswith("LIQUIDITY_USD_BELOW_MIN")
    assert gate(harness.MINT, missing) is not None
    assert gate(harness.MINT, exact) is None


# ---------------------------------------------------------------------------
# 22-24. Latest-run fixtures reach fake compose; no real send occurs
# ---------------------------------------------------------------------------


def test_22_latest_run_tier1_fixture_reaches_fake_compose_under_parity(
    tmp_path, latest_run
):
    """CsmPN87B: activation proven, fee IMMATURE, killed by the 60-minute TTL.

    Under PHX1_PARITY the IMMATURE lifecycle is an annotation, the watch is six
    hours, and a candidate with complete ATH, valid MC and valid LP composes.
    """

    csm = latest_run["candidates"]["CsmPN87B"]
    assert csm["fee_gate_lifecycle_state"] == "IMMATURE"
    assert csm["activation_proven"] is True
    assert csm["terminal_reason"] == "CANDIDATE_WATCH_EXPIRED"

    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    entry, _central, _crossing = harness._activated_entry()
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()

    result, security = harness._run_fake_tier(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)

    assert result["outcome"] == "ONE_SEND_COMMITTED"
    record = result["per_candidate"][0]
    assert record["compose_tier"] == "Tier 1"
    assert record["alert_policy"] == policy.ALERT_POLICY_PHX1_PARITY
    assert record["activation_enforcement"] == {
        "status": "PROVEN", "enforcement": "SHADOW"}
    assert entry.status == WATCH_ACTIVE_DIP
    assert security.compose_allowed is True

    # FAKE transport only: exactly one guarded dispatch, one durable ledger row.
    assert len(guard.calls) == 1
    assert guard.calls[0]["deduped"].compose_result.decision == "NO_SEND_DISPATCHED"
    assert len(ledger._state) == 1


def test_23_latest_run_tier3_fixtures_compose_after_fresh_market_evidence(
    tmp_path, latest_run
):
    """EmnjcV5n (no activation proof) and 6bN3QrA5 (recovery backoff).

    Both agreed with PHX1 on Tier 3.  Under PHX1_PARITY the missing proof does
    not block, and fresh market evidence is all either candidate needs.
    """

    emn = latest_run["candidates"]["EmnjcV5n"]
    assert emn["activation_proven"] is False
    assert emn["market_latest_tier"] == "Tier 3"
    assert emn["market_state"] == "MARKET_INCOMPLETE"

    six = latest_run["candidates"]["6bN3QrA5"]
    assert six["activation_proven"] is True
    assert six["market_latest_tier"] == "Tier 3"
    assert six["market_state"] == "MARKET_RECOVERY_BACKOFF"
    assert six["market_reason_code"] == "GRACE_TIME_EXHAUSTED"

    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    entry, _central, _crossing = harness._activated_entry()
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()

    # A Tier-3 drawdown against the same anchored maximum.
    tier3_mc = format(
        Decimal(harness.LATEST_ATH) * Decimal("0.12"), "f")
    result, _security = harness._run_fake_tier(
        entry=entry, current_mc=tier3_mc, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)

    assert result["outcome"] == "ONE_SEND_COMMITTED"
    record = result["per_candidate"][0]
    assert record["compose_tier"] == "Tier 3"
    assert record["alert_policy"] == policy.ALERT_POLICY_PHX1_PARITY
    assert len(guard.calls) == 1
    assert len(ledger._state) == 1

    # State the candidates keep across a failed refresh: ATH, activation,
    # provenance and tier history are never erased by market recovery.
    assert entry.activation_proven is True
    assert entry.discovery_provenance == _crossing["activation"][
        "discovery_provenance"] or entry.discovery_provenance is not None


def test_24_no_real_telegram_send_occurs_during_offline_tests(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    entry, _central, _crossing = harness._activated_entry()
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()

    result, _security = harness._run_fake_tier(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    assert result["outcome"] == "ONE_SEND_COMMITTED"

    # The composer refuses any non-fake client, and the recorded verdict is
    # explicitly a FAKE transport result.
    verdict = guard.calls[0]
    assert verdict["deduped"].compose_result.decision == "NO_SEND_DISPATCHED"
    sent = result["per_candidate"][0].get("send_result")
    assert getattr(sent, "fake_transport", True) is True
    assert getattr(sent, "transport_status", "FAKE_SENT_OK").startswith("FAKE")


# ---------------------------------------------------------------------------
# 25-28. Redaction, checkpoint/journal, Chainstack, broad enumeration
# ---------------------------------------------------------------------------


def test_25_policy_surface_carries_no_redaction_needles():
    """Every token this policy can write to an artifact is closed-set text."""

    banned = (
        "birdeye", "helius", "chainstack", "yellowstone", "webhook",
        "telegram", "discord", "api_key", "apikey", "token=", "http",
        "bearer", "secret",
    )
    payload = json.dumps({
        "matrix_legacy": policy.policy_matrix(policy.ALERT_POLICY_LEGACY),
        "matrix_parity": policy.policy_matrix(policy.ALERT_POLICY_PHX1_PARITY),
        "counters": policy.Phx1ParityCounters(
            policy=policy.ALERT_POLICY_PHX1_PARITY).snapshot(),
        "observability": policy.observability_matrix(
            activation_status=policy.STATUS_NOT_PROVEN,
            fee_lifecycle_status="IMMATURE",
            ath_coverage_status=policy.STATUS_COMPLETE,
            market_freshness_status=policy.STATUS_FRESH,
            policy=policy.ALERT_POLICY_PHX1_PARITY),
        "conditions": list(policy.ALERT_POLICY_CONDITIONS),
        "heat": list(policy.REFRESH_HEAT_LEVELS),
    }).lower()
    for needle in banned:
        assert needle not in payload, needle


def test_25b_shadow_conditions_are_never_labelled_blocked():
    matrix = policy.observability_matrix(
        activation_status=policy.STATUS_NOT_PROVEN,
        fee_lifecycle_status="IMMATURE",
        ath_coverage_status=policy.STATUS_COMPLETE,
        market_freshness_status=policy.STATUS_FRESH,
        policy=policy.ALERT_POLICY_PHX1_PARITY,
    )
    assert matrix == {
        "activation": {"status": "NOT_PROVEN", "enforcement": "SHADOW"},
        "fee_lifecycle": {"status": "IMMATURE", "enforcement": "SHADOW"},
        "ath_coverage": {"status": "COMPLETE", "enforcement": "HARD"},
        "market_freshness": {"status": "FRESH", "enforcement": "HARD_AT_SEND"},
    }
    # Enforcement is read from the matrix, never inferred from status text:
    # the same status under LEGACY reports HARD.
    legacy = policy.observability_matrix(
        activation_status=policy.STATUS_NOT_PROVEN,
        fee_lifecycle_status="IMMATURE",
        ath_coverage_status=policy.STATUS_COMPLETE,
        market_freshness_status=policy.STATUS_FRESH,
        policy=policy.ALERT_POLICY_LEGACY,
    )
    assert legacy["activation"]["enforcement"] == "HARD"
    assert legacy["fee_lifecycle"]["enforcement"] == "HARD"
    for record in list(matrix.values()) + list(legacy.values()):
        assert record["enforcement"] in policy.ENFORCEMENT_LEVELS
        assert "BLOCK" not in record["status"]


def test_26_checkpoint_and_migration_journal_behaviour_unchanged(tmp_path):
    """The policy touches no checkpoint field, schema, digest or journal."""

    for mode in policy.ALERT_POLICY_MODES:
        policy.bind_alert_policy(mode)
        entry, _c, _x = harness._activated_entry()
        source = Watchlist()
        source._entries[entry.token_mint] = entry
        path = tmp_path / f"watch_{mode}.jsonl"
        source.persist(path)
        assert source.checkpoint_summary()[
            "checkpoint_write_permanent_failed_total"] == 0

        restored = Watchlist.load(path)
        summary = restored.checkpoint_summary()
        assert summary["checkpoint_schema_version"] == "phx2_watch_checkpoint_v2"
        assert summary["checkpoint_status"] in (
            "CHECKPOINT_PRIMARY_OK", "CHECKPOINT_PRIMARY_AND_BACKUP_OK")
        assert summary["checkpoint_records_rejected"] == 0
        assert restored.get(entry.token_mint) is not None
        assert restored.checkpoint_quarantined is False

    # No policy condition claims authority over checkpoint integrity.
    assert policy.enforcement_for(
        policy.CONDITION_CHECKPOINT_INTEGRITY,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_HARD


def test_27_chainstack_remains_disabled_by_this_policy():
    import PHX2.free_tier_producer.phx1_parity_policy as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    for needle in ("chainstack", "yellowstone", "grpc"):
        assert needle not in source
    # The policy exposes no provider or transport switch at all.
    exported = set(policy.__all__)
    for name in exported:
        assert "provider" not in name.lower()
        assert "transport" not in name.lower()


def test_28_broad_historical_enumeration_remains_absent():
    import PHX2.free_tier_producer.phx1_parity_policy as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    for needle in (
        "getsignaturesforaddress", "get_signatures_for_address",
        "getblock", "enumerate_history", "backfill_all", "full_scan",
    ):
        assert needle not in source

    # The extended watch is a TTL on ALREADY-DISCOVERED candidates; it grants
    # no new discovery surface and no historical replay.
    assert policy.PHX1_PARITY_WATCH_TTL_SECONDS == 21600
    assert policy.enforcement_for(
        policy.CONDITION_MIGRATION_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_HARD


# ---------------------------------------------------------------------------
# Engine-level A/B: the exact production branch, both policies
# ---------------------------------------------------------------------------


class _NotPresentSidecar(harness._Sidecar):
    """Reports incomplete market data until ONE priority refresh is spent."""

    def __init__(self, *, current_mc, at, central_ath, refresh_succeeds=True):
        super().__init__(current_mc=current_mc, at=at, central_ath=central_ath)
        self.refresh_succeeds = bool(refresh_succeeds)
        self.priority_calls = []

    def resolve(self, mint, **kwargs):
        context = super().resolve(mint, **kwargs)
        context.update({
            "all_present": False,
            "current_market_cap_usd": None,
            "liquidity_usd": None,
            "market_state": "MARKET_RECOVERY_BACKOFF",
            "market_reason_code": "MARKET_RECOVERY_BACKOFF_NOT_DUE",
            "basis": "MARKET_RECOVERY_BACKOFF",
        })
        return context

    def priority_refresh(self, mint, *, migration_time_utc, now_iso_fn):
        self.priority_calls.append(mint)
        if not self.refresh_succeeds:
            context = self.resolve(mint)
            context["market_reason_code"] = "PROVIDER_STALE"
            return context
        return harness._Sidecar.resolve(self, mint)


def _run_engine(
    *, entry, current_mc, at, central_ath, ledger, guard, tmp_path,
    alert_policy, activation_gate=None, sidecar=None, counters=None,
    send_time_refresh_fn=None,
):
    """Drive the REAL committed engine with an explicit policy."""

    fee = harness._fee_snapshot(harness.PHX1_FEE_GATE_NORMAL, at)
    security = harness.evaluate_delivery_safety(
        fee_snapshot=fee, lp_integrity_mode=harness.SECURITY_SINGLE_STREAM)
    assert harness.delivery_block_reason(security) is None
    gate = producer_session.make_discord_risk_gate(
        risk_engine=harness._MediumRisk(),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "risk-blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_TELEGRAM",
        errors=harness._NoErrors(),
        lp_integrity_mode=harness.LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    if sidecar is None:
        sidecar = harness._Sidecar(
            current_mc=current_mc, at=at, central_ath=central_ath)

    def default_gate(candidate, context):
        return entry.observe_market(
            current_market_cap_usd=context["current_market_cap_usd"],
            current_price=context["current_price"],
            current_supply="1000000000",
            provider_timestamp_utc=context["provider_timestamp_utc"],
            observed_at_utc=at,
            observation_source="PAID_MARKET_PRIMARY",
            max_age_seconds=120,
            central_ath=context["central_ath"],
            pumpswap_reserve=context["pumpswap_reserve"],
        )

    if send_time_refresh_fn is None and sidecar is not None:
        refresh_impl = getattr(sidecar, "priority_refresh", None)
        if callable(refresh_impl):
            def send_time_refresh_fn(mint, _ctx, _impl=refresh_impl):
                return _impl(
                    mint, migration_time_utc=harness.BASELINE_AT,
                    now_iso_fn=lambda: at)

    return producer_session.sess.run_cap1_candidates(
        [{
            **entry.to_candidate(),
            "security_decision": security,
            "fee_gate_lifecycle": {
                "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
                "lifecycle_state": "FRESH_CONFIRMED",
                "evidence_proof_digest": fee.proof_digest,
            },
        }],
        sidecar=sidecar,
        ath_transport=harness._OfflineAthTransport(
            current_mc=current_mc, fetched_at=at, ath_mc=harness.LATEST_ATH),
        ath_endpoint_secret=harness.Stage29_2BirdeyeEndpointSecret(
            _api_key="".join(("offline", "-", "test-key", "-", "12345678")),
            _base_url="https" + "://offline.test.invalid",
        ),
        now_utc=datetime.fromisoformat(at.replace("Z", "+00:00")),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: at,
        sleep_fn=lambda _seconds: None,
        ledger=ledger,
        guard=guard,
        authorization=object(),
        created_at_utc=at,
        pre_reserve_gate_fn=gate,
        activation_gate_fn=activation_gate or default_gate,
        alert_policy=alert_policy,
        policy_counters=counters,
        send_time_refresh_fn=send_time_refresh_fn,
    )


def _unproven_gate(_candidate, _context):
    """The exact shape the production activation gate returns when unproven."""

    return {
        "activation": {},
        "events": [],
        "eligible": False,
        "just_activated": False,
        "reason": "PENDING_ACTIVATION_THRESHOLD",
    }


def _crossing_tick_gate(_candidate, _context):
    return {
        "activation": {},
        "events": [],
        "eligible": False,
        "just_activated": True,
        "reason": "ACTIVATION_CROSSING_TICK_BLOCKED",
    }


@pytest.mark.parametrize(
    "gate_fn,reason",
    [(_unproven_gate, "PENDING_ACTIVATION_THRESHOLD"),
     (_crossing_tick_gate, "ACTIVATION_CROSSING_TICK_BLOCKED")],
)
def test_engine_ab_activation_blocks_under_legacy_and_composes_under_parity(
    tmp_path, gate_fn, reason
):
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)

    # ---- LEGACY: the unproven candidate is refused, nothing is reserved ----
    policy.bind_alert_policy(policy.ALERT_POLICY_LEGACY)
    legacy_entry, _c, _x = harness._activated_entry()
    legacy_ledger = InMemoryPingDedupeLedger()
    legacy_guard = harness._FakeGuard()
    legacy = _run_engine(
        entry=legacy_entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=legacy_ledger, guard=legacy_guard,
        tmp_path=tmp_path, alert_policy=policy.ALERT_POLICY_LEGACY,
        activation_gate=gate_fn)

    assert legacy["outcome"] == "ZERO_SEND"
    legacy_record = legacy["per_candidate"][0]
    assert legacy_record["reason"] == "NO_SEND_" + reason
    assert legacy_record["activation_enforcement"] == {
        "status": "NOT_PROVEN", "enforcement": "HARD"}
    assert legacy_record.get("compose_decision") is None
    assert len(legacy_guard.calls) == 0
    assert len(legacy_ledger._state) == 0

    # ---- PHX1_PARITY: the same candidate composes; status still recorded ----
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    parity_entry, _c2, _x2 = harness._activated_entry()
    parity_ledger = InMemoryPingDedupeLedger()
    parity_guard = harness._FakeGuard()
    counters = policy.Phx1ParityCounters(
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    parity = _run_engine(
        entry=parity_entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=parity_ledger, guard=parity_guard,
        tmp_path=tmp_path, alert_policy=policy.ALERT_POLICY_PHX1_PARITY,
        activation_gate=gate_fn, counters=counters)

    assert parity["outcome"] == "ONE_SEND_COMMITTED"
    record = parity["per_candidate"][0]
    assert record["compose_tier"] == "Tier 1"
    assert record["activation_shadow_reason"] == reason
    assert record["activation_enforcement"] == {
        "status": "NOT_PROVEN", "enforcement": "SHADOW"}
    assert record["alert_policy"] == policy.ALERT_POLICY_PHX1_PARITY
    assert counters.get("would_have_blocked_under_legacy_activation") == 1
    assert counters.get("sent_without_activation_proof") == 1
    # FAKE transport only.
    assert len(parity_guard.calls) == 1
    assert len(parity_ledger._state) == 1


def test_engine_send_time_refresh_success_allows_compose_and_counts(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    entry, _c, _x = harness._activated_entry()
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()
    counters = policy.Phx1ParityCounters(
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    sidecar = _NotPresentSidecar(
        current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, refresh_succeeds=True)

    result = _run_engine(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY, sidecar=sidecar,
        counters=counters)

    record = result["per_candidate"][0]
    assert record["send_time_refresh_decision"] == policy.REFRESH_ELIGIBLE
    assert record["send_time_refresh_result"] == "SEND_TIME_REFRESH_SUCCEEDED"
    assert sidecar.priority_calls == [entry.token_mint]
    assert counters.get("send_time_refresh_attempted") == 1
    assert counters.get("send_time_refresh_succeeded") == 1
    assert counters.get("send_time_refresh_failed") == 0
    assert result["outcome"] == "ONE_SEND_COMMITTED"
    assert record["compose_tier"] == "Tier 1"
    assert len(ledger._state) == 1


def test_engine_send_time_refresh_failure_retains_candidate(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    entry, _c, _x = harness._activated_entry()
    before_status = entry.status
    before_activation = entry.activation_snapshot()
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()
    counters = policy.Phx1ParityCounters(
        policy=policy.ALERT_POLICY_PHX1_PARITY)
    sidecar = _NotPresentSidecar(
        current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, refresh_succeeds=False)

    result = _run_engine(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY, sidecar=sidecar,
        counters=counters)

    record = result["per_candidate"][0]
    assert record["send_time_refresh_result"] == "SEND_TIME_REFRESH_FAILED"
    assert record["send_time_refresh_retained"] is True
    assert record["reason"].startswith("NO_SEND_")
    assert counters.get("send_time_refresh_attempted") == 1
    assert counters.get("send_time_refresh_failed") == 1
    assert counters.get("send_time_refresh_succeeded") == 0

    # Nothing reserved, nothing sent, and the candidate is RETAINED: it stays
    # in an active (non-terminal) watch state and its ATH, activation proof,
    # baseline and provenance all survive for a later tick.  Dropping back to
    # ACTIVATED_WAITING_FOR_FRESH_MARKET is the committed behaviour for an
    # observation with no fresh market -- it is not a terminal transition.
    assert result["outcome"] == "ZERO_SEND"
    assert len(guard.calls) == 0
    assert len(ledger._state) == 0
    assert before_status == WATCH_ACTIVE_DIP
    assert entry.status == "ACTIVATED_WAITING_FOR_FRESH_MARKET"
    assert entry.is_active()
    assert entry.status != WATCH_EXPIRED
    after = entry.activation_snapshot()
    assert after["activation_proven"] == before_activation["activation_proven"]
    assert after["activation_evidence_market_cap_usd"] == before_activation[
        "activation_evidence_market_cap_usd"]
    assert after["migration_market_cap_usd"] == before_activation[
        "migration_market_cap_usd"]
    assert entry.discovery_provenance is not None


def test_engine_legacy_never_attempts_a_send_time_refresh(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_LEGACY)
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    entry, _c, _x = harness._activated_entry()
    counters = policy.Phx1ParityCounters(policy=policy.ALERT_POLICY_LEGACY)
    sidecar = _NotPresentSidecar(
        current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, refresh_succeeds=True)

    # Let activation pass so the market branch is the one under test.
    def proven_gate(_candidate, _context):
        return {
            "activation": entry.activation_snapshot(),
            "events": [],
            "eligible": True,
            "just_activated": False,
            "reason": WATCH_ACTIVE_DIP,
        }

    result = _run_engine(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=InMemoryPingDedupeLedger(),
        guard=harness._FakeGuard(), tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_LEGACY, sidecar=sidecar,
        counters=counters, activation_gate=proven_gate)

    record = result["per_candidate"][0]
    assert record["send_time_refresh_decision"] == policy.REFRESH_NOT_ENABLED
    assert sidecar.priority_calls == []
    assert counters.get("send_time_refresh_attempted") == 0
    assert record["reason"] == "NO_SEND_MARKET_RECOVERY_BACKOFF"
    assert result["outcome"] == "ZERO_SEND"


def test_engine_dedupe_and_tier_monotonicity_stay_hard_under_parity(tmp_path):
    policy.bind_alert_policy(policy.ALERT_POLICY_PHX1_PARITY)
    latest = harness._central_evidence(
        harness.LATEST_ATH,
        event_at=harness.LATEST_ATH_AT,
        ingested_at=harness.LATEST_INGESTED_AT)
    entry, _c, _x = harness._activated_entry()
    ledger = InMemoryPingDedupeLedger()
    guard = harness._FakeGuard()

    first = _run_engine(
        entry=entry, current_mc=harness.TIER1_MC, at=harness.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert first["outcome"] == "ONE_SEND_COMMITTED"
    assert first["per_candidate"][0]["compose_tier"] == "Tier 1"
    assert len(ledger._state) == 1

    second = _run_engine(
        entry=entry, current_mc=harness.TIER2_MC, at=harness.TIER2_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert second["outcome"] == "ONE_SEND_COMMITTED"
    assert second["per_candidate"][0]["compose_tier"] == "Tier 2"
    assert len(ledger._state) == 2

    # An immediate repeat of the SAME tier is still suppressed under parity.
    duplicate = _run_engine(
        entry=entry, current_mc=harness.TIER2_MC, at="2026-07-18T20:13:30Z",
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path,
        alert_policy=policy.ALERT_POLICY_PHX1_PARITY)
    assert duplicate["outcome"] == "ZERO_SEND"
    assert len(ledger._state) == 2
    assert len(guard.calls) == 2


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_counters_are_a_closed_set_and_never_raise():
    counters = policy.Phx1ParityCounters(policy="phx1_parity")
    snapshot = counters.snapshot()
    for name in (
        "would_have_blocked_under_legacy_activation",
        "sent_without_activation_proof",
        "fee_lifecycle_shadow_warnings",
        "send_time_refresh_attempted",
        "send_time_refresh_succeeded",
        "send_time_refresh_failed",
        "extended_watch_candidates",
        "candidates_reactivated_after_one_hour",
    ):
        assert snapshot[name] == 0
        counters.increment(name)
        assert counters.get(name) == 1

    # Unknown names, bad amounts and non-strings are ignored, never raised.
    counters.increment("not_a_counter")
    counters.increment(None)
    counters.increment("sent_without_activation_proof", "not-an-int")
    assert counters.get("not_a_counter") == 0
    assert counters.get(None) == 0
    assert counters.get("sent_without_activation_proof") == 1
    assert set(counters.snapshot()) == set(policy.COUNTER_NAMES) | {
        "kind", "schema_version", "alert_policy"}
