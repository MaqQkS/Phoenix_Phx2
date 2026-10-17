"""2026-07-31 restart-state remediation — offline proof.

Three proven defects, one integrated remediation:

1. A small Birdeye 429 burst (7 vs ``max_429_total=5``) latched
   ``BUDGET_RATE_LIMIT_429`` and stopped a producer whose Helius discovery was
   healthy.
2. The durable watch checkpoint was written into the per-run ``--out-dir``
   (which the operator rotates every run), so the restart reported
   ``CHECKPOINT_NOT_FOUND`` and started with an EMPTY watchlist. A LIVE_HELIUS
   mint at 1.20x / 29,719-of-35,663 came back minutes later as a DEX backfill
   candidate at 1.39x / 4,571-of-41,506 with coverage PARTIAL_SINCE_ADMISSION.
3. ``provider_handoff.jsonl`` used the raw per-record appender and tore a line.

Every fixture here is deterministic and offline: no live run, no provider
connection, no transport, no ledger write, no Telegram.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer import provider_backoff as pb
from PHX2.free_tier_producer.free_tier_credit_budget import (
    BUDGET_STOP_RATE_LIMIT_429,
    FreeTierCreditBudget,
    FreeTierCreditBudgetCaps,
)
from PHX2.free_tier_producer.serialized_jsonl import SerializedJsonlAppender
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    build_backfill_evidence_digest,
    validate_backfill_candidate_evidence,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_HELIUS,
    SEED_OUTCOME_CHECKPOINT_QUARANTINED,
    SEED_OUTCOME_EXISTING,
    WATCH_PENDING_1_20X,
    WatchEntry,
    Watchlist,
    build_migration_baseline_digest,
)
from PHX2.models.market_credential import (
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    is_fatal_market_credential_status,
    is_permanent_market_auth_status,
)
from PHX2.watchdog import operational_health as OH

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = json.loads(
    (FIXTURES / "restart_state_remediation_20260731.json").read_text(
        encoding="utf-8"))

ELON_MINT = FIXTURE["token_mint"]
LIVE_RECORD = FIXTURE["live_before_restart"]
DEX_RECORD = FIXTURE["dex_after_restart"]

#: The exact pre-restart economics the invariant must preserve.
ELON_MULTIPLIER = "1.20"
ELON_TARGET = "35663.34541050143760"
ELON_PROGRESS = "29719.454508751198"
ELON_EPOCH = "epoch_d1843c31591e40028876"

#: A second, genuinely-DEX candidate so every checkpoint under test is MIXED.
DEX_MINT = "RestartStateDexBackfill000000000000000pump"

RESTART_EPOCH = "epoch_restart000000000000"
NOW = "2026-08-01T00:00:00Z"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _live_entry(**overrides) -> WatchEntry:
    payload = dict(LIVE_RECORD)
    payload.update(overrides)
    return WatchEntry(**payload)


def _dex_entry(**overrides) -> WatchEntry:
    """A second, genuinely-DEX candidate bound to its OWN mint.

    Both the backfill evidence digest and the immutable migration baseline
    digest bind (mint, candidate_id), so re-binding the fixture to a distinct
    mint means recomputing BOTH through the real builders. That is deliberate:
    it proves the mixed checkpoint carries fully valid backfill and baseline
    proofs rather than hand-waved ones.
    """

    payload = dict(DEX_RECORD)
    payload["token_mint"] = DEX_MINT
    payload["dedupe_identity"] = "mint:" + DEX_MINT
    payload["candidate_id"] = "dex_restart_secondcandidate00"
    payload.update(overrides)
    payload["backfill_evidence_digest"] = build_backfill_evidence_digest(
        payload)
    payload["migration_baseline_digest"] = build_migration_baseline_digest(
        token_mint=payload["token_mint"],
        candidate_id=payload["candidate_id"],
        market_cap_usd=payload.get("migration_market_cap_usd"),
        observed_at_utc=payload.get("migration_market_cap_observed_at_utc"),
        source=payload.get("migration_market_cap_source"),
        price=payload.get("migration_market_cap_price"),
        supply=payload.get("migration_supply_at_observation"),
    )
    return WatchEntry(**payload)


def _write_mixed_checkpoint(path: Path, *, mirror: Path = None) -> Watchlist:
    """REQUIRED TEST 1 — a checkpoint holding LIVE_HELIUS *and* DEX candidates."""

    wl = Watchlist(max_size=64,
                   terminal_history_path=path.parent / "watch_terminal_history.jsonl")
    if mirror is not None:
        wl.set_mirror_path(mirror)
    live = _live_entry()
    dex = _dex_entry()
    wl._entries[live.token_mint] = live
    wl._entries[dex.token_mint] = dex
    wl.persist(path)
    return wl


def _restart(path: Path, *, mirror: Path = None) -> Watchlist:
    """Simulate the producer restart: a brand-new Watchlist from disk only."""

    return Watchlist.load(
        path, max_size=64,
        terminal_history_path=path.parent / "watch_terminal_history.jsonl",
        mirror_path=mirror, now_utc=NOW)


def _budget(**caps) -> FreeTierCreditBudget:
    return FreeTierCreditBudget(FreeTierCreditBudgetCaps(**caps))


def _session_module():
    """Import the producer session the way the operator launcher does.

    It is a top-level script module (not a package member), so its own
    directory and the ``compat`` seam must be importable first.
    """

    import importlib
    import sys

    root = Path(__file__).resolve().parents[1] / "free_tier_producer"
    for extra in (root, root / "compat"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    return importlib.import_module("free_tier_session")


# --------------------------------------------------------------------------
# 1-2. mixed checkpoint restores completely, before discovery
# --------------------------------------------------------------------------


def test_mixed_live_and_dex_checkpoint_restores_every_candidate(tmp_path):
    """REQUIRED 1 + 2 — write mixed state, restart, restore ALL of it."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)

    restored = _restart(path)

    assert restored.checkpoint.checkpoint_status in (
        cpe.CHECKPOINT_PRIMARY_OK, cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK)
    assert not restored.checkpoint_quarantined
    assert set(restored._entries) == {ELON_MINT, DEX_MINT}
    # Restored BEFORE anything is discovered: the restored set is already whole
    # at load time, with nothing merged into it yet.
    summary = restored.checkpoint_summary()
    assert summary["checkpoint_records_validated"] == 2
    assert summary["checkpoint_restored_active"] == 2
    # Compatibility census: the old live row is identified, but production
    # consumes all restored rows through begin_live_only_epoch().
    assert restored.restored_live_pending_mints() == [ELON_MINT]


def test_restore_becomes_diagnostic_before_any_candidate_is_merged(tmp_path):
    """Restore precedes discovery, then current eligibility is emptied."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)

    # Load preserves durable evidence first; epoch B then retires every
    # restored record without changing the original live epoch or slot.
    assert restored.get(ELON_MINT) is not None
    assert restored.rebind_restored_live_entries(
        RESTART_EPOCH, rebound_at_utc=NOW) == 0
    assert restored.get(ELON_MINT).live_epoch_id == ELON_EPOCH
    assert restored.get(ELON_MINT).migration_slot \
        == LIVE_RECORD["migration_slot"]
    assert restored.begin_live_only_epoch(
        RESTART_EPOCH, first_eligible_slot=436_887_781,
        opened_at_utc=NOW) == 2
    assert restored.active_count() == 0
    assert restored.restored_live_pending_mints() == []
    assert restored.summary()["historical_candidates_eligible"] == 0


def test_epoch_rollover_never_reactivates_restored_live_candidates(tmp_path):
    """The first boundary tick cannot reactivate prior-epoch state."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)
    assert restored.begin_live_only_epoch(
        RESTART_EPOCH, first_eligible_slot=436_887_781,
        opened_at_utc=NOW) == 2
    assert restored.close_live_epochs_except(
        RESTART_EPOCH, closed_at_utc=NOW) == 0
    assert restored.get(ELON_MINT) is None
    assert restored.active_count() == 0


# --------------------------------------------------------------------------
# 3-7. what exactly must survive
# --------------------------------------------------------------------------


def test_live_helius_provenance_is_preserved(tmp_path):
    """REQUIRED 3."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    entry = _restart(path).get(ELON_MINT)

    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_HELIUS
    assert entry.migration_evidence_class == "CANONICAL_LIVE_MIGRATION"
    assert entry.migration_slot == LIVE_RECORD["migration_slot"]
    assert entry.source_confidence == "CANONICAL_LIVE"
    assert entry.candidate_id == LIVE_RECORD["candidate_id"]
    assert entry.dedupe_identity == "mint:" + ELON_MINT


def test_activation_target_and_progress_are_preserved(tmp_path):
    """REQUIRED 4 + 9 — the ELON fixture keeps its ORIGINAL 1.20x target."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    entry = _restart(path).get(ELON_MINT)

    assert entry.activation_multiplier == ELON_MULTIPLIER
    assert entry.activation_target_market_cap_usd == ELON_TARGET
    assert entry.last_activation_progress_market_cap_usd == ELON_PROGRESS
    # The immutable baseline the target is derived from survives byte-exactly.
    assert entry.migration_market_cap_usd == "29719.454508751198"
    assert entry.migration_baseline_status == "CAPTURED"
    assert entry.migration_baseline_digest \
        == LIVE_RECORD["migration_baseline_digest"]
    assert entry._migration_baseline_digest_is_valid()
    # Explicitly NOT the post-restart backfill economics.
    assert entry.activation_multiplier != "1.39"
    assert entry.activation_target_market_cap_usd != "41505.817"


def test_activation_proven_status_is_preserved(tmp_path):
    """REQUIRED 5 — both directions: proven stays proven, unproven stays so."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    entry = _restart(path).get(ELON_MINT)

    # The fixture is a real pre-activation candidate: it must NOT come back
    # claiming an activation it never had.
    assert entry.activation_proven is False
    assert entry.activation_latched is False
    assert entry.status == WATCH_PENDING_1_20X

    # ...and the genuinely-DEX candidate's own proven status round-trips too,
    # independently of the live one.
    dex = _restart(path).get(DEX_MINT)
    assert dex.activation_proven is DEX_RECORD.get("activation_proven", False)
    assert dex.migration_baseline_status == "CAPTURED"
    valid, reason = validate_backfill_candidate_evidence(asdict(dex))
    assert valid is True, reason


def test_ath_binding_and_coverage_state_are_preserved(tmp_path):
    """REQUIRED 6."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)

    live = restored.get(ELON_MINT)
    dex = restored.get(DEX_MINT)
    # The live candidate keeps its CENTRAL_ATH binding; it must never come back
    # as the post-restart CENTRAL_ATH_PENDING / ATH_HYDRATION_PENDING shape.
    assert live.ath_source == "CENTRAL_ATH"
    assert live.last_reason == "NO_SEND_PENDING_ACTIVATION_THRESHOLD"
    assert live.liquidity_source == "CANONICAL_PUMPSWAP_RESERVES"
    assert live.current_data_source == LIVE_RECORD["current_data_source"]
    # The genuinely-DEX candidate keeps ITS honest partial coverage.
    assert dex.ath_source == "CENTRAL_ATH_PENDING"
    assert dex.backfill_evidence_digest == _dex_entry().backfill_evidence_digest
    assert validate_backfill_candidate_evidence(asdict(dex))[0] is True
    assert dex.backfill_lookback_seconds == 21600


def test_tracker_market_and_lifetime_tier_state_are_preserved(tmp_path):
    """REQUIRED 7 — tracker/scheduler/tier fields survive byte-exactly."""

    path = tmp_path / "state" / "watch_state.jsonl"
    seeded = _write_mixed_checkpoint(path)
    seeded.get(ELON_MINT).set_market_tier_projection(
        tier="TIER_2", drawdown_pct="0")
    seeded.persist(path)

    entry = _restart(path).get(ELON_MINT)
    assert entry.market_latest_tier == "TIER_2"
    assert entry.market_latest_drawdown_pct == "0"
    assert entry.recheck_count == LIVE_RECORD["recheck_count"]
    assert entry.market_attempt_count == LIVE_RECORD["market_attempt_count"]
    assert entry.market_state == "MARKET_INCOMPLETE"
    assert entry.next_market_refresh_at_utc \
        == LIVE_RECORD["next_market_refresh_at_utc"]
    assert entry.market_price_observed_at_utc \
        == LIVE_RECORD["market_price_observed_at_utc"]
    assert entry.last_observed_at_utc == LIVE_RECORD["last_observed_at_utc"]


# --------------------------------------------------------------------------
# 8. DEX rediscovery merges, never downgrades
# --------------------------------------------------------------------------


def test_dex_rediscovery_merges_into_restored_live_candidate(tmp_path):
    """REQUIRED 8 — the exact 2026-07-31 downgrade, refused."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)
    restored.rebind_restored_live_entries(RESTART_EPOCH, rebound_at_utc=NOW)

    # The backfill sweep re-offers the same mint, exactly as it did live.
    candidate = dict(DEX_RECORD)
    candidate["current_price_usd"] = candidate.pop(
        "backfill_initial_price_usd", None)
    candidate["current_market_cap_usd"] = candidate.pop(
        "backfill_initial_market_cap_usd", None)
    candidate["liquidity_usd"] = candidate.pop(
        "backfill_initial_liquidity_usd", None)
    candidate["volume_fields_present"] = True

    entry, outcome = restored.seed_with_outcome(candidate, seeded_at_utc=NOW)

    assert outcome == SEED_OUTCOME_EXISTING
    assert entry is restored.get(ELON_MINT)
    # Merged, not replaced: provenance and economics are still the live ones.
    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_HELIUS
    assert entry.activation_multiplier == ELON_MULTIPLIER
    assert entry.activation_target_market_cap_usd == ELON_TARGET
    assert entry.last_activation_progress_market_cap_usd == ELON_PROGRESS
    assert entry.ath_source == "CENTRAL_ATH"
    assert entry.candidate_id == LIVE_RECORD["candidate_id"]
    # The DEX sighting is recorded as CORROBORATION.
    assert DISCOVERY_PROVENANCE_DEX in entry.corroborating_sources
    assert len(restored._entries) == 2


def test_restored_records_stay_diagnostic_across_persist_restore_cycles(tmp_path):
    """The live-only invariant holds across repeated restarts."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    retired = []
    for epoch in ("epoch_second00000000000", "epoch_third000000000000"):
        wl = _restart(path)
        retired.append(wl.begin_live_only_epoch(
            epoch, first_eligible_slot=436_887_781, opened_at_utc=NOW))
        wl.close_live_epochs_except(epoch, closed_at_utc=NOW)
        wl.persist(path)
        assert wl.active_count() == 0
        assert wl.summary()["historical_candidates_eligible"] == 0
    assert retired == [2, 0]
    assert _restart(path).active_count() == 0


# --------------------------------------------------------------------------
# 10-14. provider-isolated 429 handling
# --------------------------------------------------------------------------


def test_transient_429_burst_enters_backoff_without_stopping_the_producer():
    """REQUIRED 10 — the exact live burst: 7 x 429 against a cap of 5."""

    budget = _budget(max_429_total=5)
    backoff = budget.market_backoff

    for observed in range(1, 8):
        budget.observe_market({"http_calls_total": 50, "http_429": observed})
        backoff.record_throttle()

    assert budget.stop_requested is False
    assert budget.stop_reason is None
    budget.check_and_raise()          # must not raise
    assert backoff.should_skip() is True
    assert 0.0 < backoff.remaining_seconds() <= backoff.backoff_ceiling_seconds
    assert backoff.throttles_total == 7


def test_backoff_is_bounded_and_jittered():
    """REQUIRED 10 — bounded ladder, jitter inside its declared fraction."""

    clock = {"t": 0.0}
    high = pb.ProviderRateLimitBackoff(
        pb.PROVIDER_MARKET_PRIMARY, monotonic_fn=lambda: clock["t"],
        jitter_fn=lambda: 0.999999)
    low = pb.ProviderRateLimitBackoff(
        pb.PROVIDER_MARKET_PRIMARY, monotonic_fn=lambda: clock["t"],
        jitter_fn=lambda: 0.0)

    delays_high = [high.record_throttle() for _ in range(40)]
    delays_low = [low.record_throttle() for _ in range(40)]

    ladder = pb.DEFAULT_BACKOFF_LADDER_SECONDS
    assert delays_low[:len(ladder)] == list(ladder)          # rung floor
    assert max(delays_high) <= ladder[-1] * (1 + pb.DEFAULT_JITTER_FRACTION)
    assert all(d <= high.backoff_ceiling_seconds for d in delays_high)
    # Saturates: 40 consecutive throttles never exceed the last rung.
    assert delays_low[-1] == ladder[-1]
    # Jitter genuinely separates two otherwise identical callers.
    assert delays_high[-1] > delays_low[-1]


def test_backoff_suppresses_the_throttled_provider_not_the_fallback():
    """A throttle degrades ONE provider; a different one still serves."""

    from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
    from PHX2.stage29.stage29_2_birdeye_models import (
        BIRDEYE_REFUSAL_REASON_NONE,
    )
    from PHX2.stage29.stage29_2_birdeye_http_transport import (
        Stage29_2BirdeyeHttpResult,
    )

    clock = {"t": 0.0}
    calls = {"primary": 0, "fallback": 0}

    class _Throttling:
        def get(self, **_kwargs):
            calls["primary"] += 1
            return Stage29_2BirdeyeHttpResult(
                refusal_reason="HTTP_STATUS_REJECTED", http_status_code=429,
                body=None, fetched_at_utc="2026-08-01T00:00:00Z")

    class _Fallback:
        def get(self, **_kwargs):
            calls["fallback"] += 1
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body={"success": True,
                      "data": {"value": "1.5", "updateUnixTime": 1000}},
                fetched_at_utc="2026-08-01T00:00:00Z")

    transport = PaidBirdeyeMarketTransport(
        inner_transport=_Throttling(), endpoint_secret=object(),
        fallback_transport=_Fallback(), min_interval_seconds=0,
        cache_ttl_seconds=0, max_attempts=3, backoff_seconds=(0,),
        now_fn=lambda: 1000, monotonic_fn=lambda: clock["t"])
    kwargs = dict(endpoint_secret=object(), path="/defi/price",
                  query_params={"address": ELON_MINT}, timeout_seconds=1)

    first = transport.get(**kwargs)
    assert first.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE   # via fallback
    assert calls == {"primary": 1, "fallback": 1}
    assert transport.rate_limit_backoff.should_skip() is True

    # Inside the window the throttled provider is not dialled AT ALL, while the
    # fallback keeps serving: market coverage degrades, it does not stop.
    second = transport.get(**kwargs)
    assert second.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE
    assert calls == {"primary": 1, "fallback": 2}
    stats = transport.stats()
    assert stats["rate_limit_backoff_skipped"] == 1
    assert stats["http_429"] == 1
    # Only ONE 429 was ever paid for: retries were not burned into the throttle.
    assert stats["rate_limit_retries_skipped"] == 2


def test_helius_discovery_and_journal_keep_running_during_market_backoff():
    """REQUIRED 11 — one provider's throttle never touches the other."""

    budget = _budget(max_429_total=5)
    for _ in range(7):
        budget.market_backoff.record_throttle()
    budget.observe_market({"http_calls_total": 60, "http_429": 7})

    assert budget.market_backoff.should_skip() is True
    # The discovery/polling surface is untouched and keeps admitting work.
    assert budget.polling_backoff.should_skip() is False
    assert budget.polling_backoff.status == pb.PROVIDER_RATE_LIMIT_OK
    assert budget.polling_allowance(per_poll_gettransaction=8) is not None
    budget.record_poll(
        {"pools_listed": 4, "signatures_seen": 9, "transactions_fetched": 2},
        accepted=1, guard_dropped=0)
    assert budget.stop_requested is False
    # Migrations still admit against the shared candidate budget.
    budget.record_provider_candidates(1)
    assert budget.candidates_accepted == 2
    assert budget.stop_requested is False


def test_401_and_403_are_not_throttles_and_stay_fatal():
    """REQUIRED 12 — auth rejection is permanent and pre-startup fatal."""

    backoff = pb.ProviderRateLimitBackoff(pb.PROVIDER_MARKET_PRIMARY)
    backoff.record_auth_failure()
    backoff.record_auth_failure()

    # Counted in its own class; NEVER converted into wait-and-retry.
    assert backoff.auth_failures_total == 2
    assert backoff.throttles_total == 0
    assert backoff.should_skip() is False
    assert backoff.status == pb.PROVIDER_RATE_LIMIT_OK

    # And the startup gate still refuses 401/403 outright while 429 carries no
    # credential verdict at all.
    assert is_permanent_market_auth_status(401) is True
    assert is_permanent_market_auth_status(403) is True
    assert is_permanent_market_auth_status(429) is False
    assert is_fatal_market_credential_status(MARKET_CREDENTIAL_INVALID) is True
    assert is_fatal_market_credential_status(
        MARKET_CREDENTIAL_UNAUTHORIZED) is True


def test_sustained_429_reports_degraded_and_keeps_candidate_state(tmp_path):
    """REQUIRED 13 — DEGRADED in health/status; candidate history intact."""

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)

    budget = _budget(max_429_total=5)
    for observed in range(1, 13):
        budget.observe_market({"http_calls_total": 90, "http_429": observed})
        budget.market_backoff.record_throttle()

    snapshot = budget.snapshot()
    assert snapshot["rate_limit"]["status"] == pb.PROVIDER_RATE_LIMIT_DEGRADED
    assert snapshot["rate_limit"]["degraded"] is True
    assert snapshot["rate_limit"]["observed_429_total"] == 12
    assert snapshot["budget_stop_requested"] is False
    assert snapshot["budget_stop_reason"] is None

    verdict = OH.evaluate_provider_rate_limit({}, {"credit_budget": snapshot})
    assert verdict.verdict == OH.DIM_DEGRADED
    assert OH.CAUSE_PROVIDER_RATE_LIMITED in verdict.causes
    # DEGRADED, never UNHEALTHY, and never a reason to open the circuit.
    assert verdict.verdict != OH.DIM_UNHEALTHY

    # The throttle deleted nothing.
    assert set(restored._entries) == {ELON_MINT, DEX_MINT}
    assert restored.get(ELON_MINT).activation_target_market_cap_usd \
        == ELON_TARGET


def test_sustained_429_never_opens_the_circuit_or_reads_unhealthy():
    """REQUIRED 13 — the whole point: a throttle must not restart anything."""

    budget = _budget(max_429_total=5)
    for observed in range(1, 10):
        budget.observe_market({"http_calls_total": 90, "http_429": observed})
        budget.market_backoff.record_throttle()

    verdict = OH.evaluate_operational_health(
        telemetry={
            "transport_connected": True,
            "source_continuity_state": "NO_GAP",
            "rate_limit": budget.snapshot()["rate_limit"],
        },
        watchlist_summary={"watchlist_count": 2,
                           "checkpoint_durable_candidate_count": 2,
                           "checkpoint_write_succeeded_total": 3},
        scheduler_state=None,
    )
    assert verdict.status == OH.DEGRADED_PROVIDER_RATE_LIMITED
    assert verdict.status in OH.DEGRADED_STATUSES
    assert verdict.status not in OH.UNHEALTHY_STATUSES
    assert OH.circuit_should_open(verdict)[0] is False


def test_degradation_reaches_the_operator_through_the_real_heartbeat_shape():
    """REQUIRED 13 — the production wiring, not just the evaluator.

    The producer writes ``budget.snapshot()`` under ``credit_budget`` on the
    heartbeat; the watchdog passes that heartbeat to the single operational
    evaluation, whose verdict ``main.py status`` and the operator CLI print
    verbatim. Assert that whole chain, so a throttle cannot be invisible.
    """

    budget = _budget(max_429_total=5)
    for observed in range(1, 8):
        budget.observe_market({"http_calls_total": 70, "http_429": observed})
        budget.market_backoff.record_throttle()

    heartbeat = {
        "kind": "PHX2_PRODUCER_HEARTBEAT",
        "credit_budget": budget.snapshot(),
        "watchlist_count": 2,
        "checkpoint_durable_candidate_count": 2,
        "checkpoint_write_succeeded_total": 5,
    }
    verdict = OH.evaluate_operational_health(
        telemetry={"transport_connected": True,
                   "source_continuity_state": "NO_GAP"},
        watchlist_summary=heartbeat,
        scheduler_state=None,
    )

    assert verdict.status == OH.DEGRADED_PROVIDER_RATE_LIMITED
    assert verdict.primary_cause == OH.CAUSE_PROVIDER_RATE_LIMITED
    dimension = verdict.dimension("market_provider")
    assert dimension is not None and dimension.verdict == OH.DIM_DEGRADED
    assert dimension.detail["market_primary"]["consecutive_throttles"] == 7
    assert dimension.detail["observed_429_total"] == 7
    # Serializable and redaction-safe all the way into the observation record.
    record = verdict.to_record()
    assert record["operational_status"] == OH.DEGRADED_PROVIDER_RATE_LIMITED
    assert "://" not in json.dumps(record)
    # The watch checkpoint is still healthy: a throttle is not a durability
    # problem, and it must not be reported as one.
    checkpoint = verdict.dimension("watch_checkpoint_durability")
    assert checkpoint is not None and checkpoint.verdict == OH.DIM_HEALTHY


def test_recovery_clears_provider_backoff():
    """REQUIRED 14."""

    clock = {"t": 0.0}
    backoff = pb.ProviderRateLimitBackoff(
        pb.PROVIDER_MARKET_PRIMARY, monotonic_fn=lambda: clock["t"],
        jitter_fn=lambda: 0.0, degraded_after_consecutive=5)
    for _ in range(6):
        backoff.record_throttle()
    assert backoff.should_skip() is True
    assert backoff.status == pb.PROVIDER_RATE_LIMIT_DEGRADED

    assert backoff.record_success() is True

    assert backoff.should_skip() is False
    assert backoff.remaining_seconds() == 0.0
    assert backoff.consecutive_throttles == 0
    assert backoff.status == pb.PROVIDER_RATE_LIMIT_OK
    assert backoff.recoveries_total == 1
    # A later throttle starts again from the FIRST rung, not where it left off.
    assert backoff.record_throttle() == pb.DEFAULT_BACKOFF_LADDER_SECONDS[0]


def test_rate_limit_429_is_no_longer_a_latchable_stop_reason():
    """The retired stop token stays exported, but nothing may latch it."""

    budget = _budget(max_429_total=2)
    for observed in range(1, 20):
        budget.observe_market({"http_calls_total": 10, "http_429": observed})
        budget.record_poll({"polling_429": 1}, accepted=0, guard_dropped=0)

    assert BUDGET_STOP_RATE_LIMIT_429 == "RATE_LIMIT_429"
    assert budget.stop_reason != "BUDGET_" + BUDGET_STOP_RATE_LIMIT_429
    assert budget.stop_reason != BUDGET_STOP_RATE_LIMIT_429
    # Real spend ceilings are UNCHANGED and still latch.
    spend = _budget(max_market_requests_total=10)
    spend.observe_market({"http_calls_total": 10, "http_429": 0})
    assert spend.stop_requested is True
    assert spend.stop_reason == "MARKET_REQUESTS"


# --------------------------------------------------------------------------
# 15. provider_handoff serialized appends
# --------------------------------------------------------------------------


def test_provider_handoff_concurrent_writes_produce_zero_malformed_lines(
        tmp_path):
    """REQUIRED 15 — the torn-line class, under real thread contention."""

    path = tmp_path / "provider_handoff.jsonl"
    appender = SerializedJsonlAppender(path)
    writers, per_writer = 8, 60
    start = threading.Barrier(writers)
    errors: list = []

    def write(worker: int) -> None:
        start.wait()
        for index in range(per_writer):
            try:
                appender.append({
                    "kind": "PHX2_PROVIDER_HANDOFF",
                    "worker": worker,
                    "index": index,
                    # Wide payload: a torn write is far likelier to be visible.
                    "token_mint": ELON_MINT,
                    "padding": "x" * (128 + worker * 32),
                })
            except Exception as exc:            # pragma: no cover - defensive
                errors.append(repr(exc))

    threads = [threading.Thread(target=write, args=(w,)) for w in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    appender.close()

    assert errors == []
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == writers * per_writer
    decoded = [json.loads(line) for line in lines]      # zero malformed lines
    assert appender.appended_records == writers * per_writer
    assert appender.failed_appends == 0
    seen = {(row["worker"], row["index"]) for row in decoded}
    assert len(seen) == writers * per_writer            # nothing overwritten
    assert path.read_bytes().endswith(b"\n")            # no torn trailing line


def test_torn_trailing_handoff_line_stays_disclosed_and_recoverable(tmp_path):
    """REQUIRED 15 — a pre-existing torn tail is readable, not silently lost."""

    path = tmp_path / "provider_handoff.jsonl"
    path.write_text('{"kind":"A","n":1}\n{"kind":"B","n":2}\n{"kind":"C","n',
                    encoding="utf-8")

    raw = path.read_text(encoding="utf-8").splitlines()
    intact, malformed = [], []
    for line in raw:
        try:
            intact.append(json.loads(line))
        except ValueError:
            malformed.append(line)
    assert len(intact) == 2 and len(malformed) == 1

    # Appending through the hardened path never rewrites, truncates or removes
    # the preserved evidence -- and it does not let the tear SPREAD: one
    # separator newline is emitted so the torn fragment stays exactly one
    # unreadable line and everything after it is parseable.
    appender = SerializedJsonlAppender(path)
    appender.append({"kind": "D", "n": 4})
    appender.append({"kind": "E", "n": 5})
    appender.close()

    assert appender.repaired_torn_tail is True
    text = path.read_text(encoding="utf-8")
    assert '{"kind":"C","n' in text                    # evidence preserved
    assert text.startswith('{"kind":"A","n":1}\n{"kind":"B","n":2}\n')
    assert text.endswith("\n")

    lines = text.splitlines()
    recovered, still_malformed = [], []
    for line in lines:
        try:
            recovered.append(json.loads(line))
        except ValueError:
            still_malformed.append(line)
    # Exactly the ONE original tear remains malformed; the damage did not grow.
    assert still_malformed == ['{"kind":"C","n']
    assert [row["kind"] for row in recovered] == ["A", "B", "D", "E"]


# --------------------------------------------------------------------------
# 16-18. fail-closed, no send, ledger untouched
# --------------------------------------------------------------------------


def test_checkpoint_restoration_stays_fail_closed_for_corrupt_evidence(
        tmp_path):
    """REQUIRED 16 — durability must not have weakened authentication."""

    path = tmp_path / "state" / "watch_state.jsonl"
    wl = _write_mixed_checkpoint(path)
    wl.persist(path)          # second generation, so a .bak now exists
    assert Path(str(path) + ".bak").exists()

    # Tamper with the authoritative primary AND its backup.
    for target in (path, Path(str(path) + ".bak")):
        body = target.read_text(encoding="utf-8")
        target.write_text(
            body.replace(ELON_TARGET, "99999999.00000000000000"),
            encoding="utf-8")

    restored = _restart(path)

    assert restored.checkpoint_quarantined is True
    assert restored.checkpoint.checkpoint_status == cpe.CHECKPOINT_QUARANTINED
    assert restored._entries == {}
    # Quarantine lockdown: no admissions and no overwrite of the evidence.
    assert restored.seed_with_outcome(
        {"token_mint": ELON_MINT}, seeded_at_utc=NOW)[1] \
        == SEED_OUTCOME_CHECKPOINT_QUARANTINED
    before = path.read_bytes()
    restored.persist(path)
    assert path.read_bytes() == before
    assert restored.checkpoint_summary()["checkpoint_persist_refused"] >= 1


def test_missing_checkpoint_is_reported_not_invented(tmp_path):
    """A genuinely absent checkpoint still says so — it never fabricates."""

    fresh = Watchlist.load(tmp_path / "state" / "watch_state.jsonl",
                           max_size=8, now_utc=NOW)
    assert fresh.checkpoint.checkpoint_status == cpe.CHECKPOINT_NOT_FOUND
    assert fresh._entries == {}
    assert fresh.checkpoint_quarantined is False


def test_run_dir_mirror_is_written_and_is_never_the_restore_source(tmp_path):
    """The durability fix itself: authoritative durable pair + run mirror."""

    durable = tmp_path / "state" / "watch_state.jsonl"
    mirror = tmp_path / "runs" / "run_stamp" / "watch_state.jsonl"
    _write_mixed_checkpoint(durable, mirror=mirror)

    assert durable.exists() and mirror.exists()
    assert mirror.read_bytes() == durable.read_bytes()

    # A ROTATED run directory (the live failure) no longer loses anything:
    # the durable pair is what the next producer reads.
    rotated = tmp_path / "runs" / "next_run_stamp" / "watch_state.jsonl"
    restored = _restart(durable, mirror=rotated)
    assert set(restored._entries) == {ELON_MINT, DEX_MINT}
    restored.persist(durable)
    assert rotated.exists()
    assert rotated.read_bytes() == durable.read_bytes()
    assert restored.checkpoint_summary()["checkpoint_mirror_write_failed"] == 0
    assert restored.checkpoint_summary()["checkpoint_mirror_configured"] is True


def test_mirror_failure_never_fails_the_durable_write(tmp_path):
    """The mirror is telemetry: it is disclosed on failure, never fatal."""

    durable = tmp_path / "state" / "watch_state.jsonl"
    # Mirror target whose PARENT is a regular file: mkdir/replace must fail.
    blocked_parent = tmp_path / "runs_blocked"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    mirror = blocked_parent / "run" / "watch_state.jsonl"

    wl = _write_mixed_checkpoint(durable, mirror=mirror)
    wl.persist(durable)

    assert durable.exists()
    assert not mirror.exists()
    summary = wl.checkpoint_summary()
    assert summary["checkpoint_mirror_write_failed"] >= 1
    assert summary["checkpoint_durability_status"] \
        == cpe.CHECKPOINT_DURABILITY_HEALTHY


def test_no_transport_ledger_or_send_object_is_touched_offline(tmp_path):
    """REQUIRED 17 + 18 — nothing here can send or move the ledger."""

    ledger = tmp_path / "ping_dedupe.jsonl"
    ledger.write_text("", encoding="utf-8")
    before = (ledger.read_bytes(), ledger.stat().st_size)

    path = tmp_path / "state" / "watch_state.jsonl"
    _write_mixed_checkpoint(path)
    restored = _restart(path)
    restored.rebind_restored_live_entries(RESTART_EPOCH, rebound_at_utc=NOW)
    budget = _budget(max_429_total=5)
    for _ in range(7):
        budget.market_backoff.record_throttle()

    assert (ledger.read_bytes(), ledger.stat().st_size) == before
    # No delivery ever happened: no receipt, no ledger key, no send attempt.
    entry = restored.get(ELON_MINT)
    assert entry.delivery_state is None
    assert entry.delivery_receipt_digest is None
    assert entry.delivery_ledger_key is None
    assert entry.delivery_attempt_count == 0
    assert budget.send_attempts == 0
    assert budget.sent_ok_count == 0
    assert budget.snapshot()["private_ping_count"] == 0


def test_session_anchors_the_checkpoint_outside_the_rotating_run_dir(tmp_path):
    """The root cause itself: which directory the session writes state into."""

    session = _session_module()
    state_dir = tmp_path / "runtime" / "state"
    run_a = tmp_path / "runtime" / "runs" / "run_20260731T224645Z"
    run_b = tmp_path / "runtime" / "runs" / "run_20260731T231533Z"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    first = session.resolve_watch_state_paths(
        out_dir=str(run_a), cursor_state_dir=str(state_dir))
    second = session.resolve_watch_state_paths(
        out_dir=str(run_b), cursor_state_dir=str(state_dir))

    # The AUTHORITATIVE path is identical across the run-dir rotation that
    # destroyed the state on 2026-07-31.
    assert first["durable"] is True and second["durable"] is True
    assert first["watch_state_path"] == second["watch_state_path"]
    assert first["watch_terminal_history_path"] \
        == second["watch_terminal_history_path"]
    assert Path(first["watch_state_path"]).parent == state_dir
    # The MIRRORS follow the run dir, so run artifacts stay where every reader
    # (dashboard, paper tooling, redaction scan, selftests) expects them.
    assert Path(first["watch_state_mirror_path"]).parent == run_a
    assert Path(second["watch_state_mirror_path"]).parent == run_b

    # A durable checkpoint written under the first run is found by the second.
    _write_mixed_checkpoint(
        Path(first["watch_state_path"]),
        mirror=Path(first["watch_state_mirror_path"]))
    restored = _restart(Path(second["watch_state_path"]))
    assert set(restored._entries) == {ELON_MINT, DEX_MINT}
    assert restored.get(ELON_MINT).activation_target_market_cap_usd \
        == ELON_TARGET


def test_session_without_a_stable_state_dir_keeps_the_previous_layout(tmp_path):
    """Development posture is unchanged: no stable dir, no mirror, no move."""

    session = _session_module()
    run = tmp_path / "run"
    run.mkdir()
    paths = session.resolve_watch_state_paths(
        out_dir=str(run), cursor_state_dir=None)

    assert paths["durable"] is False
    assert Path(paths["watch_state_path"]).parent == run
    assert paths["watch_state_mirror_path"] == paths["watch_state_path"]
    # Adoption is a no-op when there is nothing durable to adopt INTO.
    assert session.adopt_legacy_run_dir_watch_state(paths)["adopted"] is False


def test_pre_remediation_run_dir_state_is_adopted_once_then_never_again(
        tmp_path):
    """Upgrade path: state left in a non-rotating out-dir is not abandoned."""

    session = _session_module()
    state_dir = tmp_path / "state"
    run = tmp_path / "run"
    run.mkdir()
    paths = session.resolve_watch_state_paths(
        out_dir=str(run), cursor_state_dir=str(state_dir))

    # A pre-remediation build left its checkpoint beside the run artifacts.
    legacy = Path(paths["watch_state_mirror_path"])
    wl = _write_mixed_checkpoint(legacy)
    wl.persist(legacy)                     # second generation -> .bak exists
    legacy_bytes = legacy.read_bytes()

    adoption = session.adopt_legacy_run_dir_watch_state(paths)
    assert adoption["adopted"] is True
    assert adoption["errors"] == []
    assert "watch_state" in adoption["copied"]
    # Bytes verbatim: the envelope digest chain still authenticates.
    assert Path(paths["watch_state_path"]).read_bytes() == legacy_bytes
    restored = _restart(Path(paths["watch_state_path"]))
    assert set(restored._entries) == {ELON_MINT, DEX_MINT}

    # Idempotent: once durable state exists it ALWAYS wins, and a stale
    # run-dir copy can never overwrite it.
    legacy.write_bytes(b"{stale garbage from an abandoned run\n")
    again = session.adopt_legacy_run_dir_watch_state(paths)
    assert again["adopted"] is False
    assert Path(paths["watch_state_path"]).read_bytes() == legacy_bytes


def test_no_secret_or_endpoint_leaks_into_backoff_telemetry():
    """Redaction discipline for every new artifact-bound field."""

    budget = _budget(max_429_total=5)
    budget.market_backoff.record_throttle()
    budget.polling_backoff.record_throttle()
    block = budget.snapshot()["rate_limit"]
    # Scoped to the block this remediation ADDS. (The surrounding budget
    # snapshot legitimately carries the committed RAW_WS_CAP_NOTE prose.)
    blob = json.dumps(block, sort_keys=True)

    for needle in ("://", "http", "api_key", "Authorization", "bearer",
                   "birdeye", "helius", "chainstack", "dexscreener", "token"):
        assert needle.lower() not in blob.lower(), needle
    assert block["market_primary"]["provider"] == pb.PROVIDER_MARKET_PRIMARY
    assert block["discovery_polling"]["provider"] == pb.PROVIDER_DISCOVERY_POLLING
    assert block["status"] in pb.PROVIDER_RATE_LIMIT_STATUSES


def test_watch_entry_new_audit_fields_round_trip_through_validation(tmp_path):
    """The two new schema fields must not weaken checkpoint validation."""

    from PHX2.free_tier_producer.compat.build30_watchlist import (
        validate_watch_checkpoint_record,
    )

    record = asdict(_live_entry(
        restored_from_live_epoch_id=ELON_EPOCH,
        epoch_rebound_at_utc=NOW))
    ok, reason = validate_watch_checkpoint_record(record)
    assert ok is True and reason == ""

    # A malformed rebind timestamp still fails closed.
    bad = dict(record, epoch_rebound_at_utc="not-a-timestamp")
    ok, reason = validate_watch_checkpoint_record(bad)
    assert ok is False
    assert reason == cpe.QUARANTINE_TIMESTAMP_INVALID


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
