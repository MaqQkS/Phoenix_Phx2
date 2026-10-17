"""Curated DEX safety net: honest coverage semantics, not a completeness claim.

The behaviour under test is deliberately narrow.  The curated surface is a
provider's editorial "latest token profiles" list, not a migration index: it has
no completeness guarantee and no time-ordered pagination.  So a successful poll
proves the REQUESTS worked, and nothing else.

These tests pin exactly that boundary:

* a candidate the curated list DOES carry is recovered and admitted;
* a candidate it does NOT carry is reported NOT_OBSERVED_BY_CURATED_SOURCE,
  never silently treated as covered;
* a successful poll's coverage claim is PARTIAL_COVERAGE;
* a live + DEX duplicate produces ONE watchlist tracker;
* anything older than the hard six-hour lookback is rejected;
* partial ATH coverage cannot compose or send, complete coverage can;
* a DEX failure never disturbs healthy live discovery.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from PHX2.free_tier_producer import discovery_status as DS
from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_LIVE,
    Watchlist,
)
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    BACKFILL_STATE_DEGRADED,
    BACKFILL_STATE_HEALTHY,
    CURATED_COVERAGE_CLAIM,
    KNOWN_COVERAGE_LIMITATIONS,
    PHX1_LOOKBACK_SECONDS,
    DexRestartBackfill,
    build_backfill_candidate,
)
from PHX2.integrations.dexscreener_client import (
    DEX_BACKFILL_SUCCESS,
    DEX_BACKFILL_UNAVAILABLE,
)
from PHX2.models.ath_coverage import (
    ATH_COVERAGE_COMPLETE_HYDRATED,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.models.discovery_provenance import DISCOVERY_PROVENANCE_DEX_BACKFILL


OBSERVED_MINT = "11111111111111111111111111111111pump"
ABSENT_MINT = "22222222222222222222222222222222pump"


def _pair(now: float, *, mint: str = OBSERVED_MINT, age_seconds: float = 60.0,
          pair_address: str = "pair-1"):
    return {
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": pair_address,
        "pairCreatedAt": int((now - age_seconds) * 1000),
        "baseToken": {"address": mint, "symbol": "TEST", "name": "Test Token"},
        "priceUsd": "0.0001",
        "marketCap": "100000",
        "liquidity": {"usd": "5000"},
        "volume": {"m5": "1", "h1": "10", "h6": "20", "h24": "30"},
    }


def _run_sweep(client_factory, *, now: float, epoch: str = "epoch-curated"):
    runner = DexRestartBackfill(client_factory=client_factory,
                                now_fn=lambda: now)
    assert runner.schedule(epoch) is True
    deadline = time.time() + 5
    while runner.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)
    return runner


def _client(*, pairs, profile_status=DEX_BACKFILL_SUCCESS,
            token_status=DEX_BACKFILL_SUCCESS, mints=(OBSERVED_MINT,),
            raise_on_profiles: bool = False):
    class _Client:
        def current_sol_price_usd(self):
            return 150.0, DEX_BACKFILL_SUCCESS

        def latest_token_profiles(self):
            if raise_on_profiles:
                raise RuntimeError("curated surface unavailable")
            return ([{"chainId": "solana", "tokenAddress": mint}
                     for mint in mints], profile_status)

        def token_pairs(self, _mints):
            return list(pairs), token_status

        def stats(self):
            return {
                "requests_attempted": 3, "requests_succeeded": 3,
                "requests_failed": 0, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": None,
            }

    return _Client


# ---------------------------------------------------------------------------
# recovery + observation semantics
# ---------------------------------------------------------------------------


def test_a_known_curated_candidate_is_recovered_and_admitted() -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    snapshot = runner.snapshot()
    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["candidates_admitted"] == 1
    drained = runner.drain()
    assert [item["token_mint"] for item in drained] == [OBSERVED_MINT]
    assert runner.observation_status(OBSERVED_MINT) == (
        DS.OBSERVED_BY_CURATED_SOURCE)


def test_an_absent_candidate_is_not_observed_never_silently_covered() -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    verdict = runner.observation_status(ABSENT_MINT)
    assert verdict == DS.NOT_OBSERVED_BY_CURATED_SOURCE
    # The vocabulary has no way to say "covered" here.
    assert verdict != DS.OBSERVED_BY_CURATED_SOURCE
    assert "COMPLETE" not in verdict


def test_absence_before_any_answer_is_source_unavailable() -> None:
    runner = DexRestartBackfill(client_factory=_client(pairs=[]),
                                now_fn=time.time)
    assert runner.observation_status(ABSENT_MINT) == (
        DS.CURATED_SOURCE_UNAVAILABLE)


def test_poll_success_reports_partial_coverage_never_healthy_coverage(
) -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    status = runner.safety_net_status(enabled=True)
    # Mechanism health and coverage claim are SEPARATE answers.
    assert status["state"] == DS.DEX_SAFETY_NET_HEALTHY
    assert status["coverage"] == DS.DEX_SAFETY_NET_PARTIAL_COVERAGE
    assert status["coverage"] != DS.DEX_SAFETY_NET_HEALTHY
    assert status["curated_coverage_claim"] == CURATED_COVERAGE_CLAIM
    assert "NOT_EXHAUSTIVE" in status["curated_coverage_claim"]
    assert status["curated_rows_examined"] >= 1
    assert status["curated_candidates_admitted"] == 1


def test_coverage_function_can_never_return_healthy() -> None:
    """Structural: a successful poll has no path to a completeness claim."""

    for answered in (True, False):
        assert DS.dex_safety_net_coverage(
            enabled=True,
            last_sweep_answered=answered) != DS.DEX_SAFETY_NET_HEALTHY
    assert DS.dex_safety_net_coverage(
        enabled=True, last_sweep_answered=True
    ) == DS.DEX_SAFETY_NET_PARTIAL_COVERAGE
    assert DS.dex_safety_net_coverage(
        enabled=True, last_sweep_answered=False
    ) == DS.DEX_SAFETY_NET_DEGRADED
    assert DS.dex_safety_net_coverage(
        enabled=False, last_sweep_answered=True
    ) == DS.DEX_SAFETY_NET_DISABLED


def test_known_coverage_limitations_are_always_disclosed() -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    limitations = runner.snapshot()["known_coverage_limitations"]
    assert set(limitations) == set(KNOWN_COVERAGE_LIMITATIONS)
    assert "CURATED_DEX_ABSENCE_IS_NOT_PROOF_OF_NO_MIGRATION" in limitations
    assert "CURATED_DEX_SURFACE_IS_NOT_A_MIGRATION_INDEX" in limitations


# ---------------------------------------------------------------------------
# admission window
# ---------------------------------------------------------------------------


def test_a_candidate_older_than_six_hours_is_rejected() -> None:
    now = time.time()
    assert PHX1_LOOKBACK_SECONDS == 6 * 60 * 60
    candidate, reason = build_backfill_candidate(
        pair=_pair(now, age_seconds=PHX1_LOOKBACK_SECONDS + 1.0),
        sol_price_usd=Decimal("150"), sol_fallback_used=False,
        sweep_id="sweep-1", epoch_id="epoch-1",
        discovery_utc="2026-07-31T00:00:00Z", now_epoch=now)
    assert candidate is None
    assert reason == "OUTSIDE_PHX1_LOOKBACK"

    inside, ok_reason = build_backfill_candidate(
        pair=_pair(now, age_seconds=PHX1_LOOKBACK_SECONDS - 1.0),
        sol_price_usd=Decimal("150"), sol_fallback_used=False,
        sweep_id="sweep-1", epoch_id="epoch-1",
        discovery_utc="2026-07-31T00:00:00Z", now_epoch=now)
    assert ok_reason == "ACCEPTED"
    assert inside is not None
    assert inside["backfill_lookback_seconds"] == PHX1_LOOKBACK_SECONDS


def test_the_six_hour_bound_is_retained_by_the_sweep() -> None:
    now = time.time()
    runner = _run_sweep(
        _client(pairs=[_pair(now, age_seconds=PHX1_LOOKBACK_SECONDS + 60)]),
        now=now)
    snapshot = runner.snapshot()
    assert snapshot["candidates_admitted"] == 0
    assert snapshot["candidates_rejected"] == 1
    assert snapshot["lookback_ceiling_seconds"] == PHX1_LOOKBACK_SECONDS


# ---------------------------------------------------------------------------
# dedupe against live discovery
# ---------------------------------------------------------------------------


def test_live_and_dex_duplicate_creates_one_tracker(tmp_path: Path) -> None:
    watchlist = Watchlist(max_size=8,
                          terminal_history_path=tmp_path / "terminal.jsonl")
    live = watchlist.seed({
        "token_mint": OBSERVED_MINT,
        "candidate_id": "live-1",
        "migration_time_utc": "2026-07-31T00:00:00Z",
        "source_ref": "helius:sig",
        "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
    }, seeded_at_utc="2026-07-31T00:00:01Z")
    assert live is not None
    dex = watchlist.seed({
        "token_mint": OBSERVED_MINT,
        "candidate_id": "dex_restart_1",
        "migration_time_utc": "2026-07-31T00:00:00Z",
        "source_ref": "dex_restart:pair",
        "discovery_provenance": DISCOVERY_PROVENANCE_DEX,
    }, seeded_at_utc="2026-07-31T00:00:02Z")
    assert dex is None                       # the SAME mint, not a second row
    assert len(watchlist.active_entries()) == 1
    assert watchlist.get(OBSERVED_MINT).candidate_id == "live-1"


def test_the_sweep_dedupes_repeated_mints_within_one_pass() -> None:
    now = time.time()
    runner = _run_sweep(
        _client(pairs=[_pair(now, pair_address="pair-1"),
                       _pair(now, pair_address="pair-2")]),
        now=now)
    snapshot = runner.snapshot()
    assert snapshot["candidates_admitted"] == 1
    assert snapshot["duplicate_suppressions"] >= 1


# ---------------------------------------------------------------------------
# ATH coverage gate
# ---------------------------------------------------------------------------


def test_partial_ath_coverage_cannot_compose_or_send() -> None:
    coverage = classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_hydration_status="ATH_HYDRATION_PENDING")
    assert coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert ath_coverage_is_complete(coverage) is False


def test_complete_ath_coverage_may_enter_tier_evaluation() -> None:
    from PHX2.free_tier_producer.ath_state import ATH_HYDRATION_COMPLETE
    from PHX2.free_tier_producer.market_scheduler import project_closed_tier

    coverage = classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_hydration_status=ATH_HYDRATION_COMPLETE)
    assert coverage == ATH_COVERAGE_COMPLETE_HYDRATED
    assert ath_coverage_is_complete(coverage) is True
    tier, drawdown = project_closed_tier(
        ath_market_cap_usd="67087.57", current_market_cap_usd="19900")
    assert tier == "Tier 2"
    assert Decimal("70.2") < Decimal(drawdown) < Decimal("70.5")


def test_a_backfill_candidate_starts_with_pending_central_ath() -> None:
    now = time.time()
    candidate, reason = build_backfill_candidate(
        pair=_pair(now), sol_price_usd=Decimal("150"),
        sol_fallback_used=False, sweep_id="sweep-1", epoch_id="epoch-1",
        discovery_utc="2026-07-31T00:00:00Z", now_epoch=now)
    assert reason == "ACCEPTED"
    assert candidate["ath_source"] == "CENTRAL_ATH_PENDING"
    assert candidate["discovery_provenance"] == DISCOVERY_PROVENANCE_DEX_BACKFILL


# ---------------------------------------------------------------------------
# failure isolation
# ---------------------------------------------------------------------------


def test_dex_failure_reports_degraded_and_never_stops_live_discovery(
) -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[], raise_on_profiles=True), now=now)
    snapshot = runner.snapshot()
    assert snapshot["status"] != DEX_BACKFILL_SUCCESS
    status = runner.safety_net_status(enabled=True)
    assert status["state"] == DS.DEX_SAFETY_NET_DEGRADED
    assert status["coverage"] == DS.DEX_SAFETY_NET_DEGRADED
    # A failing safety net still leaves the LIVE source healthy: the two are
    # projected independently and the DEX answer contributes nothing to the
    # live-source state.
    projected = DS.build_discovery_status(
        transport_connected=True, reconnecting=False,
        continuity_snapshot={"continuity_state": "NO_GAP",
                             "coverage_proven_continuous": True,
                             "open_gap_count": 0},
        backfill_snapshot=snapshot, backfill_enabled=True)
    assert projected.live_source_state == DS.LIVE_CONNECTED
    assert projected.gap_recovery_state == DS.GAP_RECOVERY_IDLE
    assert projected.dex_safety_net_state == DS.DEX_SAFETY_NET_DEGRADED
    assert projected.coverage_proven_continuous is True


def test_a_sweep_thread_exception_never_escapes_to_the_caller() -> None:
    now = time.time()

    class _Exploding:
        def current_sol_price_usd(self):
            raise RuntimeError("boom")

    runner = _run_sweep(_Exploding, now=now)
    assert runner.snapshot()["error_class"] == "RuntimeError"
    assert runner.drain() == []
    assert runner.safety_net_status(
        enabled=True)["state"] == DS.DEX_SAFETY_NET_DEGRADED


def test_backfill_operational_state_still_reports_the_legacy_tokens() -> None:
    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    assert runner.snapshot()["operational_state"] == BACKFILL_STATE_HEALTHY
    failing = _run_sweep(_client(pairs=[], raise_on_profiles=True), now=now,
                         epoch="epoch-failing")
    assert failing.snapshot()["operational_state"] == BACKFILL_STATE_DEGRADED


def test_disabled_safety_net_is_reported_as_disabled() -> None:
    runner = DexRestartBackfill(client_factory=_client(pairs=[]),
                                now_fn=time.time)
    status = runner.safety_net_status(enabled=False)
    assert status["state"] == DS.DEX_SAFETY_NET_DISABLED
    assert status["coverage"] == DS.DEX_SAFETY_NET_DISABLED


def test_curated_status_payloads_are_redaction_safe() -> None:
    from PHX2.free_tier_producer.compat import production_live_artifacts as pla

    now = time.time()
    runner = _run_sweep(_client(pairs=[_pair(now)]), now=now)
    body = json.dumps(runner.safety_net_status(enabled=True), sort_keys=True)
    assert pla.scan_text(body) == []
