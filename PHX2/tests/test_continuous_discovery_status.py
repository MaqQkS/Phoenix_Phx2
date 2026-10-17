"""Continuous-discovery status vocabulary, exposure contract, credit budget.

Two things are pinned here.

STATUS.  The closed-set states the discovery policy names by hand must all
exist, the eight required facts must each be exposed SEPARATELY (so nobody has
to infer one from another), and no status value may be readable as a claim of
exhaustive six-hour completeness.

CREDIT BUDGET.  The rejected broad-enumeration design projected ~78.9M
credits/month -- 788.7% of the 10M Developer allowance.  The replacement has to
fit with real headroom, computed from MEASURED production telemetry rather than
asserted, and the model must contain no term that could express a broad
historical scan.
"""

from __future__ import annotations

import json

import pytest

from PHX2.free_tier_producer import discovery_status as DS
from PHX2.free_tier_producer import helius_credit_projection as CP
from PHX2.free_tier_producer.compat import production_live_artifacts as pla


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------


def test_every_required_state_exists_and_is_in_the_closed_set() -> None:
    required = {
        "LIVE_CONNECTED", "LIVE_RECONNECTING",
        "GAP_RECOVERY_ACTIVE", "GAP_RECOVERY_DEGRADED",
        "DEX_SAFETY_NET_HEALTHY", "DEX_SAFETY_NET_PARTIAL_COVERAGE",
        "DEX_SAFETY_NET_DEGRADED", "DEX_SAFETY_NET_DISABLED",
    }
    assert set(DS.REQUIRED_DISCOVERY_STATES) == required
    # Subset membership, never exact equality: narrower states (idle, stopped,
    # auth-failed) are allowed additions, dropping a required one is not.
    assert required.issubset(set(DS.DISCOVERY_STATES))
    assert len(set(DS.DISCOVERY_STATES)) == len(DS.DISCOVERY_STATES)


def test_no_state_token_can_be_read_as_exhaustive_completeness() -> None:
    for token in DS.DISCOVERY_STATES:
        upper = token.upper()
        assert "COMPLETE" not in upper
        assert "EXHAUSTIVE" not in upper
        assert "FULL_COVERAGE" not in upper


def test_live_source_states_are_decided_failure_first() -> None:
    assert DS.live_source_state(
        transport_connected=True, reconnecting=False) == DS.LIVE_CONNECTED
    assert DS.live_source_state(
        transport_connected=False, reconnecting=True) == DS.LIVE_RECONNECTING
    # A connected socket during a reconnect attempt is still RECONNECTING.
    assert DS.live_source_state(
        transport_connected=True, reconnecting=True) == DS.LIVE_RECONNECTING
    assert DS.live_source_state(
        transport_connected=True, reconnecting=False,
        authentication_failed=True) == DS.LIVE_AUTHENTICATION_FAILED
    assert DS.live_source_state(
        transport_connected=True, reconnecting=False,
        stopped=True) == DS.LIVE_STOPPED


def test_gap_recovery_states_prefer_the_worst_unresolved_fact() -> None:
    assert DS.gap_recovery_state(open_gap_count=0) == DS.GAP_RECOVERY_IDLE
    assert DS.gap_recovery_state(open_gap_count=2) == DS.GAP_RECOVERY_ACTIVE
    assert DS.gap_recovery_state(
        open_gap_count=2, terminal_gap_count=1) == DS.GAP_RECOVERY_DEGRADED
    assert DS.gap_recovery_state(
        open_gap_count=1, terminal_gap_count=1) == DS.GAP_RECOVERY_DEGRADED


def test_curated_observation_never_says_did_not_migrate() -> None:
    assert DS.curated_observation_status(
        observed=True,
        curated_source_answered=True) == DS.OBSERVED_BY_CURATED_SOURCE
    assert DS.curated_observation_status(
        observed=False,
        curated_source_answered=True) == DS.NOT_OBSERVED_BY_CURATED_SOURCE
    assert DS.curated_observation_status(
        observed=False,
        curated_source_answered=False) == DS.CURATED_SOURCE_UNAVAILABLE
    for verdict in DS.CURATED_OBSERVATION_VERDICTS:
        assert "NO_MIGRATION" not in verdict
        assert "DID_NOT" not in verdict


# ---------------------------------------------------------------------------
# exposure contract
# ---------------------------------------------------------------------------


def _status():
    return DS.build_discovery_status(
        transport_connected=True,
        reconnecting=False,
        continuity_snapshot={
            "continuity_state": "GAP_DETECTED",
            "coverage_proven_continuous": False,
            "last_durable_slot": 436_237_503,
            "gap_detected_total": 3,
            "open_gap_count": 1,
            "recovered_ranges": [[100, 110], [200, 205]],
            "unresolved_ranges": [[300, 310]],
        },
        journal_snapshot={
            "record_count": 42,
            "last_confirmed_slot": 436_237_500,
            "last_journal_commit_utc": "2026-07-31T00:00:00Z",
        },
        backfill_snapshot={
            "consecutive_failed_sweeps": 0,
            "sweeps_completed_total": 3,
            "any_required_source_failed": False,
            "last_sweep_answered": True,
            "curated_rows_examined": 57,
            "candidates_admitted": 8,
        },
        backfill_enabled=True,
        reconnect_snapshot={"consecutive_failures": 0},
    )


def test_each_required_fact_is_exposed_separately() -> None:
    status = _status()
    record = status.to_record()
    # live-source continuity
    assert record["live_source_state"] == DS.LIVE_CONNECTED
    assert record["live_source_continuity_state"] == "GAP_DETECTED"
    assert record["coverage_proven_continuous"] is False
    # durable cursor slot
    assert record["durable_cursor_slot"] == 436_237_503
    # last migration-journal commit
    assert record["last_migration_journal_commit_utc"] == (
        "2026-07-31T00:00:00Z")
    assert record["migration_journal_record_count"] == 42
    assert record["migration_journal_last_confirmed_slot"] == 436_237_500
    # detected gaps
    assert record["detected_gap_total"] == 3
    assert record["open_gap_count"] == 1
    # recovered ranges
    assert record["recovered_ranges"] == [[100, 110], [200, 205]]
    assert record["unresolved_ranges"] == [[300, 310]]
    # curated rows examined / candidates admitted
    assert record["curated_rows_examined"] == 57
    assert record["curated_candidates_admitted"] == 8
    # known coverage limitations
    assert set(record["known_coverage_limitations"]) == set(
        DS.KNOWN_COVERAGE_LIMITATIONS)


def test_the_three_subsystems_are_projected_independently() -> None:
    status = _status()
    assert status.live_source_state == DS.LIVE_CONNECTED
    assert status.gap_recovery_state == DS.GAP_RECOVERY_ACTIVE
    assert status.dex_safety_net_state == DS.DEX_SAFETY_NET_HEALTHY
    # A healthy MECHANISM still only claims PARTIAL coverage.
    assert status.dex_safety_net_coverage == DS.DEX_SAFETY_NET_PARTIAL_COVERAGE
    assert status.curated_coverage_claim == DS.CURATED_COVERAGE_CLAIM


def test_a_disabled_safety_net_makes_no_coverage_claim() -> None:
    status = DS.build_discovery_status(
        transport_connected=True, reconnecting=False, backfill_enabled=False)
    assert status.dex_safety_net_state == DS.DEX_SAFETY_NET_DISABLED
    assert status.dex_safety_net_coverage == DS.DEX_SAFETY_NET_DISABLED
    assert status.curated_coverage_claim == DS.DEX_SAFETY_NET_DISABLED


def test_missing_inputs_degrade_rather_than_fabricate() -> None:
    status = DS.build_discovery_status(
        transport_connected=False, reconnecting=True)
    record = status.to_record()
    assert record["live_source_state"] == DS.LIVE_RECONNECTING
    assert record["durable_cursor_slot"] is None
    assert record["last_migration_journal_commit_utc"] is None
    assert record["migration_journal_record_count"] == 0
    assert record["recovered_ranges"] == []
    assert record["coverage_proven_continuous"] is False


def test_malformed_range_input_is_dropped_not_trusted() -> None:
    status = DS.build_discovery_status(
        transport_connected=True, reconnecting=False,
        continuity_snapshot={
            "recovered_ranges": [[10, 20], [30], "x", [50, 40], [-1, 5],
                                 [True, 5]],
        })
    assert status.recovered_ranges == ((10, 20),)


def test_the_status_record_is_redaction_safe() -> None:
    body = json.dumps(_status().to_record(), sort_keys=True)
    assert pla.scan_text(body) == []


# ---------------------------------------------------------------------------
# credit budget
# ---------------------------------------------------------------------------


def test_the_measured_stream_rate_is_the_projection_input() -> None:
    assert CP.MEASURED_WSS_BYTES == 9_775_274 - 618_959
    assert CP.MEASURED_WSS_SECONDS == 582.0
    assert CP.MEASURED_WSS_BYTES_PER_SECOND == pytest.approx(15_732.5, abs=0.5)
    # Billing follows the provider's published stream rate, not a guess.
    assert CP.stream_credits_for_bytes(100_000) == pytest.approx(2.0)
    assert CP.stream_credits_for_bytes(0) == 0.0


def test_no_gap_operation_fits_the_developer_allowance() -> None:
    projection = CP.no_gap_projection()
    assert projection.gap_recovery_credits == 0.0
    assert projection.reconnect_credits == 0.0
    assert projection.fits_developer_allowance is True
    assert projection.allowance_fraction < 0.10


def test_ordinary_operation_fits_with_wide_headroom() -> None:
    projection = CP.ordinary_projection()
    assert projection.fits_developer_allowance is True
    assert projection.allowance_fraction < 0.15
    record = projection.to_record()
    assert record["headroom_credits"] > 9_000_000


def test_the_conservative_case_still_fits_with_headroom() -> None:
    projection = CP.conservative_projection()
    assert projection.fits_developer_allowance is True
    # Doubled stream rate, one reconnect a minute for a month, hourly gaps at
    # the FULL bounded recovery ceiling -- still well under a fifth.
    assert projection.allowance_fraction < 0.25
    assert projection.total_credits < CP.DEVELOPER_MONTHLY_CREDITS


def test_the_rejected_broad_enumeration_projection_is_not_reachable() -> None:
    """No parameter in this model can express a broad historical scan."""

    report = CP.projection_report()
    assert report["broad_historical_enumeration_modelled"] is False
    for scenario in report["scenarios"]:
        # 78.9M credits was the rejected design; every scenario is far below.
        assert scenario["total_credits"] < 5_000_000
        assert scenario["fits_developer_allowance"] is True


def test_gap_recovery_credits_are_bounded_by_hard_ceilings() -> None:
    from PHX2.free_tier_producer.helius_gap_recovery import DEFAULT_MAX_CREDITS
    from PHX2.free_tier_producer.source_continuity import (
        DEFAULT_MAX_RECOVERY_ATTEMPTS,
    )

    per_day = CP.gap_recovery_credits_per_month(gaps_per_day=1) / 30
    assert per_day == DEFAULT_MAX_RECOVERY_ATTEMPTS * DEFAULT_MAX_CREDITS
    assert CP.gap_recovery_credits_per_month(gaps_per_day=0) == 0.0
    assert CP.gap_recovery_credits_per_month(gaps_per_day=-5) == 0.0


def test_reconnect_credits_are_negligible_even_at_the_worst_cadence() -> None:
    worst = CP.reconnect_credits_per_month(
        reconnects_per_month=CP.WORST_CASE_RECONNECTS_PER_MONTH)
    assert worst < 5_000
    assert CP.WORST_CASE_RECONNECTS_PER_MONTH == CP.SECONDS_PER_MONTH // 60


def test_curated_dex_requests_are_reported_separately() -> None:
    report = CP.projection_report()
    assert report["curated_dex_consumes_helius_credits"] is False
    assert report["curated_dex_requests_per_month"] == (
        CP.CURATED_DEX_SWEEPS_PER_DAY * CP.CURATED_DEX_REQUESTS_PER_SWEEP * 30)
    # And they are NOT summed into any Helius scenario total.
    for scenario in report["scenarios"]:
        assert "curated" not in json.dumps(scenario).lower()


def test_the_projection_report_is_redaction_safe() -> None:
    assert pla.scan_text(
        json.dumps(CP.projection_report(), sort_keys=True)) == []
