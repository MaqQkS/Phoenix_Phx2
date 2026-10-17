"""2026-07-27 live-quality audit remediation — deterministic regressions.

Every fixture below reproduces a defect PROVEN from the preserved
``paid_primary_live_24x7_*`` run evidence of 2026-07-26/27 (sanitized values
only; no live file is read, no provider/transport is constructed):

  1. cqDX3…pump duplicate/state regression: Tier 2 (ATH $116,943.16,
     DD_BAND_60) sent 10:20:46Z from run 094120Z; the run was then killed
     (BUDGET_SEND_CAP), the per-run ATH store started empty, and the SAME mint
     re-sent Tier 1 (ATH $50,272.48, DD_BAND_50) at 11:09:44Z.
  2. Watchlist starvation: all 38 live-decoded migrations were rejected
     ``EPOCH_EVENT_PRE_ARM_REJECTED`` with ``migration_slot: null`` because the
     frozen normalized event carries no ``slot`` attribute.
  3. SECRET_SCAN_FAILURE with zero needle hits: one transiently unreadable
     file (atomic checkpoint replace mid-walk) killed run 083623Z at 09:41:05Z.
  4. PAID_PROVIDER_RECONNECT_STORM latched by a LIFETIME reconnect count
     (6 provider resets spread over 2.9 h) against a healthy stream.
  5. Watchdog EPOCH_NOT_DURABLE integrity circuit opened at 13:13:43Z against
     a producer mid-clean-shutdown (disk epoch CLOSED, heartbeat 3 s stale),
     then ``main.py status`` served the stale owner count (owners=1) after a
     verified full stop.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

import PHX2.operator_cli as cli
from PHX2.delivery.telegram_composer import (
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_COVERAGE_UNKNOWN,
    BuilderReadStatement,
    TelegramPingData,
    compose_telegram_ping,
)
from PHX2.free_tier_producer.ath_state import (
    CentralAthStateStore,
    DURABLE_RESTORE_HEAVY_STATE_RETENTION_SECONDS,
)
from PHX2.free_tier_producer.compat import production_live_artifacts
from PHX2.free_tier_producer.compat.production_live_runner import (
    MAX_CONSECUTIVE_SCAN_READ_FAILURES,
    SCAN_VERDICT_CLEAN,
    SCAN_VERDICT_READ_ERROR_ONLY,
    SCAN_VERDICT_UNSAFE,
    classify_redaction_scan,
)
from PHX2.free_tier_producer.free_tier_session import (
    ReconnectStormWindow,
    paid_provider_safety_error,
)
from PHX2.free_tier_producer.live_epoch import (
    EPOCH_EVENT_ADMITTED,
    EPOCH_EVENT_PRE_ARM_REJECTED,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    STAGE30_11_15_POLICY_VERSION,
    Stage30_11_15PingDedupeKey,
)
from PHX2.watchdog.health import (
    NONRESTARTABLE_INTEGRITY_FAILURE,
    REASON_EPOCH_NOT_DURABLE,
    HealthInputs,
    evaluate_health,
)


CQDX_MINT = "cqDX3mDQGcjqbTLXqzKnsi1ZPcRUQowdqf8fszkpump"
TTL = 21_600


def _key(*, mint: str = CQDX_MINT, tier: str = "Tier 2",
         band: str = "DD_BAND_60", verified: bool = True,
         source: str = "central_ath_v1",
         policy: str = STAGE30_11_15_POLICY_VERSION,
         signal: str = STAGE30_11_15_OPERATOR_SIGNAL_KIND,
         ) -> Stage30_11_15PingDedupeKey:
    return Stage30_11_15PingDedupeKey(
        token_mint=mint, operator_signal_kind=signal, tier_token=tier,
        drawdown_band=band, post_migration_ath_verified=verified,
        ath_source_stage=source, policy_version=policy)


# =========================================================================
# 1. Monotonic sent-tier dedupe (invariants 5-7, 22, 23)
# =========================================================================

@pytest.mark.parametrize("make_ledger", [
    lambda tmp: InMemoryPingDedupeLedger(),
    lambda tmp: JsonlPingDedupeLedger(path=tmp / "ping_dedupe.jsonl"),
], ids=["memory", "jsonl"])
class TestSentTierMonotonicity:
    def test_lower_tier_after_higher_tier_is_suppressed_within_ttl(
            self, tmp_path, make_ledger):
        """The exact cqDX3…pump regression: Tier 2 sent, state lost, Tier 1
        re-attempted 49 minutes later with EVERY other key axis different."""
        ledger = make_ledger(tmp_path)
        first = ledger.check_and_reserve(
            key=_key(tier="Tier 2", band="DD_BAND_60"),
            now_utc="2026-07-27T10:20:46Z", ttl_seconds=TTL)
        assert first.allowed
        regression = ledger.check_and_reserve(
            key=_key(tier="Tier 1", band="DD_BAND_50", verified=False,
                     source="stage30_11_11"),
            now_utc="2026-07-27T11:09:44Z", ttl_seconds=TTL)
        assert regression.suppressed
        assert regression.reason == DEDUPE_REASON_DUPLICATE_WITHIN_TTL

    def test_higher_tier_escalation_still_alerts(self, tmp_path, make_ledger):
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T10:20:46Z",
            ttl_seconds=TTL).allowed
        escalation = ledger.check_and_reserve(
            key=_key(tier="Tier 3", band="DD_BAND_80"),
            now_utc="2026-07-27T11:09:44Z", ttl_seconds=TTL)
        assert escalation.allowed

    def test_lower_tier_suppressed_even_after_ttl_expiry(
            self, tmp_path, make_ledger):
        """Lifetime monotonicity: "Tier 2 sent => no later Tier 1" holds for
        the whole ledger lifecycle, not just inside the 6h TTL window."""
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T00:00:00Z",
            ttl_seconds=TTL).allowed
        aged = ledger.check_and_reserve(
            key=_key(tier="Tier 1", band="DD_BAND_50"),
            now_utc="2026-07-28T12:00:00Z", ttl_seconds=TTL)
        assert aged.suppressed
        assert aged.reason == DEDUPE_REASON_DUPLICATE_WITHIN_TTL
        escalation = ledger.check_and_reserve(
            key=_key(tier="Tier 3", band="DD_BAND_80"),
            now_utc="2026-07-28T12:00:00Z", ttl_seconds=TTL)
        assert escalation.allowed

    def test_equal_tier_realerts_keep_ttl_semantics(
            self, tmp_path, make_ledger):
        """The TTL still governs SAME-tier re-alerts: an unchanged key ages
        out and may alert again; a crossed band re-alerts immediately."""
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2", band="DD_BAND_60"),
            now_utc="2026-07-27T00:00:00Z", ttl_seconds=TTL).allowed
        crossed_band = ledger.check_and_reserve(
            key=_key(tier="Tier 2", band="DD_BAND_70"),
            now_utc="2026-07-27T00:30:00Z", ttl_seconds=TTL)
        assert crossed_band.allowed
        aged_same_key = ledger.check_and_reserve(
            key=_key(tier="Tier 2", band="DD_BAND_60"),
            now_utc="2026-07-27T06:00:01Z", ttl_seconds=TTL)
        assert aged_same_key.allowed

    def test_policy_version_bump_reopens_alerting(
            self, tmp_path, make_ledger):
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T00:00:00Z",
            ttl_seconds=TTL).allowed
        bumped = ledger.check_and_reserve(
            key=_key(tier="Tier 1", band="DD_BAND_50",
                     policy="stage30_11_15_v1"),
            now_utc="2026-07-27T01:00:00Z", ttl_seconds=TTL)
        assert bumped.allowed

    def test_exact_duplicate_still_suppressed(self, tmp_path, make_ledger):
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(), now_utc="2026-07-27T10:20:46Z",
            ttl_seconds=TTL).allowed
        again = ledger.check_and_reserve(
            key=_key(), now_utc="2026-07-27T10:30:00Z", ttl_seconds=TTL)
        assert again.suppressed

    def test_other_mints_are_unaffected(self, tmp_path, make_ledger):
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T10:20:46Z",
            ttl_seconds=TTL).allowed
        other = ledger.check_and_reserve(
            key=_key(mint="K16JV4YxuyVdvBqxq4CSDhGpSX2r1TwRKeYd7G3pump",
                     tier="Tier 1", band="DD_BAND_50"),
            now_utc="2026-07-27T11:45:50Z", ttl_seconds=TTL)
        assert other.allowed

    def test_commit_of_the_reserved_higher_tier_stays_idempotent(
            self, tmp_path, make_ledger):
        """The commit-after-delivery replay path must keep tolerating the row
        it just reserved (equal rank never triggers the regression guard)."""
        ledger = make_ledger(tmp_path)
        assert ledger.check_and_reserve(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T10:20:46Z",
            ttl_seconds=TTL).allowed
        commit = ledger.commit_confirmed_send(
            key=_key(tier="Tier 2"), now_utc="2026-07-27T10:20:49Z",
            ttl_seconds=TTL)
        assert commit.suppressed          # row already written: idempotent


def test_jsonl_replay_suppresses_lower_tier_across_restart(tmp_path):
    """Cross-run durability: a fresh ledger instance replaying the file still
    holds the sent-tier monotonicity (candidate-instance boundaries crossed)."""
    path = tmp_path / "ping_dedupe.jsonl"
    first = JsonlPingDedupeLedger(path=path)
    assert first.check_and_reserve(
        key=_key(tier="Tier 2"), now_utc="2026-07-27T10:20:46Z",
        ttl_seconds=TTL).allowed
    replayed = JsonlPingDedupeLedger(path=path)
    regression = replayed.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50", source="stage30_11_11"),
        now_utc="2026-07-27T11:09:44Z", ttl_seconds=TTL)
    assert regression.suppressed


def test_full_lifecycle_tier2_restart_ttl_expiry_readmission_tier1(tmp_path):
    """The operator-mandated lifecycle sequence: Tier 2 send -> process
    restart (ledger replay) -> dedupe TTL expiry -> same mint re-admitted
    under a different provenance's key axes -> attempted Tier 1 send.  The
    Tier 1 must stay suppressed; a Tier 3 escalation must stay allowed."""
    path = tmp_path / "ping_dedupe.jsonl"
    run1 = JsonlPingDedupeLedger(path=path)
    assert run1.check_and_reserve(
        key=_key(tier="Tier 2", band="DD_BAND_60", source="central_ath_v1"),
        now_utc="2026-07-27T10:20:46Z", ttl_seconds=TTL).allowed

    # Process restart: a new ledger instance replays the durable file.
    run2 = JsonlPingDedupeLedger(path=path)
    # 26h later -- far beyond the 6h TTL -- the mint re-enters via
    # restart-backfill provenance: every non-mint key axis differs.
    late_regression = run2.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50", verified=False,
                 source="stage30_11_11"),
        now_utc="2026-07-28T12:30:00Z", ttl_seconds=TTL)
    assert late_regression.suppressed
    escalation = run2.check_and_reserve(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-28T12:31:00Z", ttl_seconds=TTL)
    assert escalation.allowed
    # And the escalation now guards Tier 2 as well, forever.
    run3 = JsonlPingDedupeLedger(path=path)
    tier2_after_tier3 = run3.check_and_reserve(
        key=_key(tier="Tier 2", band="DD_BAND_60"),
        now_utc="2026-07-30T00:00:00Z", ttl_seconds=TTL)
    assert tier2_after_tier3.suppressed


class _NoIterationDict(dict):
    """A dict that PROVES no caller iterates it: point lookups and writes
    work; any full-collection walk raises."""

    def _refuse(self, *args, **kwargs):
        raise AssertionError(
            "full-state iteration after initialization is forbidden")

    __iter__ = _refuse
    keys = _refuse
    values = _refuse
    items = _refuse


def _freeze_iteration(ledger) -> None:
    ledger._state = _NoIterationDict(ledger._state)
    ledger._highest_tier_by_scope = _NoIterationDict(
        ledger._highest_tier_by_scope)


def test_index_is_reconstructed_from_replay_and_duplicates_are_idempotent(
        tmp_path):
    path = tmp_path / "ping_dedupe.jsonl"
    first = JsonlPingDedupeLedger(path=path)
    assert first.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50"),
        now_utc="2026-07-27T00:00:00Z", ttl_seconds=TTL).allowed
    assert first.check_and_reserve(
        key=_key(tier="Tier 2", band="DD_BAND_60"),
        now_utc="2026-07-27T01:00:00Z", ttl_seconds=TTL).allowed
    assert first.check_and_reserve(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T02:00:00Z", ttl_seconds=TTL).allowed
    # Idempotent commit replay of an existing row changes nothing.
    assert first.commit_confirmed_send(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T02:00:01Z", ttl_seconds=TTL).suppressed

    replayed = JsonlPingDedupeLedger(path=path)
    scope = (CQDX_MINT, STAGE30_11_15_OPERATOR_SIGNAL_KIND,
             STAGE30_11_15_POLICY_VERSION)
    assert replayed._highest_tier_by_scope[scope] == 3
    assert replayed._highest_tier_by_scope == first._highest_tier_by_scope
    # Tier 3 now guards both lower tiers, from the replayed index alone.
    _freeze_iteration(replayed)
    for tier, band in (("Tier 1", "DD_BAND_51"), ("Tier 2", "DD_BAND_61")):
        outcome = replayed.check_and_reserve(
            key=_key(tier=tier, band=band),
            now_utc="2026-07-30T00:00:00Z", ttl_seconds=TTL)
        assert outcome.suppressed


def test_failed_append_never_raises_the_tier_index(tmp_path, monkeypatch):
    """A reservation that never became durable must not advance the index
    (nor the replayed state)."""
    path = tmp_path / "ping_dedupe.jsonl"
    ledger = JsonlPingDedupeLedger(path=path)

    def refuse_append(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "_append_record", refuse_append)
    failed = ledger.check_and_reserve(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T00:00:00Z", ttl_seconds=TTL)
    assert failed.unavailable
    assert ledger._highest_tier_by_scope == {}
    assert ledger._state == {}
    monkeypatch.undo()
    # With the write path healthy again, a LOWER tier is still allowed --
    # the failed Tier 3 reservation never became authoritative.
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50"),
        now_utc="2026-07-27T00:01:00Z", ttl_seconds=TTL).allowed


def test_check_only_never_raises_the_tier_index(tmp_path):
    path = tmp_path / "ping_dedupe.jsonl"
    ledger = JsonlPingDedupeLedger(path=path)
    assert ledger.check_only(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T00:00:00Z", ttl_seconds=TTL).allowed
    assert ledger._highest_tier_by_scope == {}
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50"),
        now_utc="2026-07-27T00:01:00Z", ttl_seconds=TTL).allowed


def test_signal_kind_isolation_in_the_lifetime_guard(tmp_path):
    ledger = JsonlPingDedupeLedger(path=tmp_path / "ping_dedupe.jsonl")
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 2"), now_utc="2026-07-27T00:00:00Z",
        ttl_seconds=TTL).allowed
    other_signal = ledger.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50",
                 signal="PHOENIX_OPERATOR_OTHER_SIGNAL"),
        now_utc="2026-07-27T01:00:00Z", ttl_seconds=TTL)
    assert other_signal.allowed


@pytest.mark.parametrize("make_ledger", [
    lambda tmp: InMemoryPingDedupeLedger(),
    lambda tmp: JsonlPingDedupeLedger(path=tmp / "ping_dedupe.jsonl"),
], ids=["memory", "jsonl"])
def test_classification_is_index_based_after_initialization(
        tmp_path, make_ledger):
    """Post-init classification must never walk the full replayed state:
    both collections are made iteration-hostile and every classify /
    reserve / commit path still works via point lookups."""
    ledger = make_ledger(tmp_path)
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 2"), now_utc="2026-07-27T00:00:00Z",
        ttl_seconds=TTL).allowed
    _freeze_iteration(ledger)
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 1", band="DD_BAND_50"),
        now_utc="2026-07-27T01:00:00Z", ttl_seconds=TTL).suppressed
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T01:00:00Z", ttl_seconds=TTL).allowed
    assert ledger.check_and_reserve(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T01:30:00Z", ttl_seconds=TTL).suppressed
    assert ledger.commit_confirmed_send(
        key=_key(tier="Tier 3", band="DD_BAND_80"),
        now_utc="2026-07-27T01:31:00Z", ttl_seconds=TTL).suppressed
    check_only = getattr(ledger, "check_only", None)
    if callable(check_only):
        assert check_only(
            key=_key(tier="Tier 2", band="DD_BAND_61"),
            now_utc="2026-07-30T00:00:00Z", ttl_seconds=TTL).suppressed


def test_memory_and_jsonl_indexes_stay_behaviorally_equivalent(tmp_path):
    memory = InMemoryPingDedupeLedger()
    jsonl = JsonlPingDedupeLedger(path=tmp_path / "ping_dedupe.jsonl")
    script = (
        ("Tier 1", "DD_BAND_50", "2026-07-27T00:00:00Z"),
        ("Tier 3", "DD_BAND_80", "2026-07-27T01:00:00Z"),
        ("Tier 2", "DD_BAND_60", "2026-07-27T02:00:00Z"),   # regression
        ("Tier 3", "DD_BAND_80", "2026-07-28T00:00:00Z"),   # TTL re-alert
    )
    for tier, band, now in script:
        left = memory.check_and_reserve(
            key=_key(tier=tier, band=band), now_utc=now, ttl_seconds=TTL)
        right = jsonl.check_and_reserve(
            key=_key(tier=tier, band=band), now_utc=now, ttl_seconds=TTL)
        assert (left.verdict, left.reason) == (right.verdict, right.reason)
    assert memory._highest_tier_by_scope == jsonl._highest_tier_by_scope


def test_large_ledger_replay_and_lookup_performance_sanity(tmp_path):
    """Bounded synthetic scaling fixture (never production ledger contents):
    50,000 records replay once; 10,000 post-replay classifications run
    against iteration-hostile collections, proving index-based O(1) reads."""
    import io
    import time as _time

    from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
        _serialize_record,
    )

    path = tmp_path / "big_ping_dedupe.jsonl"
    tiers = ("Tier 1", "Tier 2", "Tier 3")
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        for index in range(50_000):
            key = _key(
                mint=f"SyntheticMint{index:027d}pump",
                tier=tiers[index % 3],
                band=f"DD_BAND_{50 + 10 * (index % 3)}")
            handle.write(_serialize_record(
                key=key, reserved_at_utc="2026-07-27T00:00:00Z") + "\n")

    replay_start = _time.perf_counter()
    ledger = JsonlPingDedupeLedger(path=path)
    replay_seconds = _time.perf_counter() - replay_start
    assert ledger._available
    assert len(ledger._state) == 50_000
    assert len(ledger._highest_tier_by_scope) == 50_000

    _freeze_iteration(ledger)
    lookup_start = _time.perf_counter()
    suppressed = 0
    for index in range(0, 30_000, 3):
        probe = _key(
            mint=f"SyntheticMint{index + 2:027d}pump",   # a Tier 3 scope
            tier="Tier 1", band="DD_BAND_55")
        if ledger.check_only(
                key=probe, now_utc="2026-07-30T00:00:00Z",
                ttl_seconds=TTL).suppressed:
            suppressed += 1
    lookup_seconds = _time.perf_counter() - lookup_start
    assert suppressed == 10_000            # every probe hit its Tier 3 scope
    # Generous ceilings: a replay is linear once; each lookup is O(1).
    assert replay_seconds < 30.0
    assert lookup_seconds < 5.0
    globals()["_PERF_SANITY_REPORT"] = {
        "records": 50_000,
        "replay_seconds": round(replay_seconds, 3),
        "lookups": 10_000,
        "lookup_seconds": round(lookup_seconds, 3),
    }


# =========================================================================
# 1b. Send budget: bounded acceptance runs vs unbounded managed 24/7
# =========================================================================

def _budget_caps(**overrides):
    from PHX2.free_tier_producer.free_tier_credit_budget import (
        FreeTierCreditBudgetCaps,
    )

    base = dict(
        max_sends_per_run=3, max_raw_ws_notifications_total=120000,
        max_seed_windows=120, max_candidates_total=400,
        max_gettransaction_total=1024, max_market_requests_total=5000,
        max_429_total=5, max_consecutive_ws_errors=2,
        max_rpc_errors_total=12, max_polls_total=5000)
    base.update(overrides)
    return FreeTierCreditBudgetCaps(**base)


def test_bounded_run_still_stops_exactly_at_its_send_budget():
    """Run 094120Z semantics preserved for bounded acceptance runs: the 3rd
    send latches BUDGET_SEND_CAP and the next tick boundary raises."""
    from PHX2.free_tier_producer.free_tier_credit_budget import (
        BUDGET_STOP_SEND_CAP,
        FreeTierBudgetExhausted,
        FreeTierCreditBudget,
    )

    budget = FreeTierCreditBudget(_budget_caps(max_sends_per_run=3),
                                  delivery_enabled=True)
    for _ in range(2):
        budget.record_send_attempt(sent_ok=True)
        budget.check_and_raise()          # under budget: no stop
    budget.record_send_attempt(sent_ok=True)
    assert budget.stop_requested and budget.stop_reason == BUDGET_STOP_SEND_CAP
    with pytest.raises(FreeTierBudgetExhausted):
        budget.check_and_raise()


def test_unbounded_managed_run_never_terminates_on_send_count():
    """The canonical 24/7 posture (max_sends_per_run=0) must not end the
    producer merely because N alerts were sent; every OTHER budget ceiling
    still latches normally."""
    from PHX2.free_tier_producer.free_tier_credit_budget import (
        BUDGET_STOP_CANDIDATES,
        FreeTierCreditBudget,
        SEND_CAP_UNBOUNDED,
    )

    budget = FreeTierCreditBudget(
        _budget_caps(max_sends_per_run=SEND_CAP_UNBOUNDED),
        delivery_enabled=True)
    assert budget.caps.sends_unbounded
    for _ in range(50):
        budget.record_send_attempt(sent_ok=True)
        budget.check_and_raise()          # never raises for send count
    assert not budget.stop_requested
    assert budget.sent_ok_count == 50
    budget.record_provider_candidates(400)   # other safety ceilings intact
    assert budget.stop_requested
    assert budget.stop_reason == BUDGET_STOP_CANDIDATES


def test_send_cap_zero_is_the_only_relaxed_field():
    with pytest.raises(ValueError):
        _budget_caps(max_candidates_total=0)
    with pytest.raises(ValueError):
        _budget_caps(max_sends_per_run=-1)
    assert _budget_caps(max_sends_per_run=0).sends_unbounded
    assert not _budget_caps(max_sends_per_run=3).sends_unbounded


def test_canonical_launcher_carries_the_unbounded_send_budget():
    from PHX2.watchdog.launcher_template import (
        REFUSAL_SEND_CAP_NOT_UNBOUNDED,
        render_live_launcher,
        validate_live_launcher_text,
    )

    head = "e" * 40
    baseline = ("3f6de122a289a211705a944926e54dd5913f0cfa0a24f460a04df9a9"
                "fa0217eb:3662:10")
    text = render_live_launcher(expected_head=head, ledger_baseline=baseline)
    assert '"--max-sends-per-run", "0"' in text
    assert '"--run-forever"' in text
    refusals = validate_live_launcher_text(
        text, expected_head=head, ledger_baseline=baseline)
    assert refusals == []
    # A bounded cap can never silently creep into the 24/7 launcher.
    bounded = text.replace('"--max-sends-per-run", "0"',
                           '"--max-sends-per-run", "3"')
    assert REFUSAL_SEND_CAP_NOT_UNBOUNDED in validate_live_launcher_text(
        bounded, expected_head=head, ledger_baseline=baseline)
    absent = text.replace('  "--max-sends-per-run", "0",\n', "")
    assert REFUSAL_SEND_CAP_NOT_UNBOUNDED in validate_live_launcher_text(
        absent, expected_head=head, ledger_baseline=baseline)
    # The managed launcher still introduces no other transport or authority
    # (its manifest DECLARES wallet_signing_enabled=false; no arm flag exists).
    assert "--enable-private-discord" not in text
    assert "--enable-wallet" not in text
    assert "--enable-trading" not in text and "--enable-signing" not in text
    assert "wallet_signing_enabled  = $false" in text


# =========================================================================
# 2. Durable ATH checkpoint across run-dir rotation (invariants 1-4, 8-10)
# =========================================================================

def _observe(store: CentralAthStateStore, mint: str, market_cap: str,
             at: str, *, confirmed: bool = True) -> bool:
    price = format(int(market_cap) / 10**9, "f")
    return store.observe_provider_current(
        mint=mint, price_usd=price, market_cap_usd=market_cap,
        observed_at=at, confirmed=confirmed)


def test_ath_survives_run_dir_rotation_with_durable_checkpoint_dir(tmp_path):
    """The cqDX3 fixture: canonical ATH must survive the run rollover instead
    of restarting from the re-admission spot price."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    first = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    assert _observe(first, CQDX_MINT, "49961", "2026-07-27T10:18:55Z")
    assert _observe(first, CQDX_MINT, "116943", "2026-07-27T09:55:16Z")

    run2 = tmp_path / "run2"           # fresh out dir: the watchdog restart
    run2.mkdir()
    second = CentralAthStateStore(run2, checkpoint_dir=state_dir)
    restored = second.snapshot(CQDX_MINT)
    assert restored is not None
    assert restored["ath_market_cap"] == "116943"
    # A lower post-restart observation may be recorded but can never lower
    # the canonical ATH (monotonicity across tracker recreation).
    _observe(second, CQDX_MINT, "50272", "2026-07-27T10:57:14Z")
    assert second.snapshot(CQDX_MINT)["ath_market_cap"] == "116943"


def test_without_durable_dir_checkpoint_stays_in_run_dir(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    store = CentralAthStateStore(run_dir)
    assert _observe(store, CQDX_MINT, "1000", "2026-07-27T10:00:00Z")
    assert (run_dir / "ath_state_checkpoint.json").exists()


def test_durable_dir_holds_checkpoint_and_run_dir_holds_public_mirror(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    store = CentralAthStateStore(run_dir, checkpoint_dir=state_dir)
    assert _observe(store, CQDX_MINT, "1000", "2026-07-27T10:00:00Z")
    assert (state_dir / "ath_state_checkpoint.json").exists()
    assert (run_dir / "ath_state.json").exists()
    assert not (run_dir / "ath_state_checkpoint.json").exists()


def test_restore_compacts_only_stale_heavy_maps_and_keeps_ath_core(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    stale_mint = "StaleMint0000000000000000000000000000pump"
    fresh_mint = "FreshMint0000000000000000000000000000pump"
    assert _observe(store, stale_mint, "77000", "2026-07-27T01:00:00Z")
    assert _observe(store, fresh_mint, "88000", "2026-07-27T09:59:00Z")
    with store._lock:
        store._mints[stale_mint]["seen_event_keys"] = {
            f"evt:{i}": "2026-07-27T01:00:00Z" for i in range(64)}
        store._mints[stale_mint]["last_updated_at"] = "2026-07-27T01:00:00Z"
        store._mints[stale_mint]["ath_timestamp"] = "2026-07-27T01:00:00Z"
        store._mints[fresh_mint]["seen_event_keys"] = {
            f"evt:{i}": "2026-07-27T09:59:00Z" for i in range(64)}
        store._persist_generation_locked()

    anchor = "2026-07-27T10:21:23Z"     # > 6h after the stale mint's activity
    assert DURABLE_RESTORE_HEAVY_STATE_RETENTION_SECONDS == 21_600
    run2 = tmp_path / "run2"
    run2.mkdir()
    restored = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc=anchor)
    stale = restored.snapshot(stale_mint)
    fresh = restored.snapshot(fresh_mint)
    assert stale["ath_market_cap"] == "77000"      # ATH core retained
    assert fresh["ath_market_cap"] == "88000"
    with restored._lock:
        assert restored._mints[stale_mint]["seen_event_keys"] == {}
        assert restored._mints[stale_mint]["pending_events"] == []
        assert len(restored._mints[fresh_mint]["seen_event_keys"]) == 64


def test_records_quiet_beyond_retention_are_retired_at_restore(tmp_path):
    """Whole-record lifecycle boundary: >72h-quiet mints are retired at
    restore (bounded durable growth); fresh mints and their values survive."""
    from PHX2.free_tier_producer.ath_state import (
        DURABLE_ATH_RECORD_RETENTION_SECONDS,
    )

    assert DURABLE_ATH_RECORD_RETENTION_SECONDS == 259_200
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    old_mint = "OldMint000000000000000000000000000000pump"
    live_mint = "LiveMint00000000000000000000000000000pump"
    assert _observe(store, old_mint, "55000", "2026-07-20T00:00:00Z")
    assert _observe(store, live_mint, "66000", "2026-07-27T09:00:00Z")
    with store._lock:
        store._mints[old_mint]["last_updated_at"] = "2026-07-20T00:00:00Z"
        store._mints[old_mint]["ath_timestamp"] = "2026-07-20T00:00:00Z"
        store._persist_generation_locked()

    run2 = tmp_path / "run2"
    run2.mkdir()
    restored = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-07-27T10:00:00Z")
    assert restored.snapshot(old_mint) is None          # retired
    assert restored.snapshot(live_mint)["ath_market_cap"] == "66000"
    assert restored.checkpoint_summary()["checkpoint_records_retired"] == 1
    assert not restored.checkpoint_quarantined


def test_retired_absence_across_generation_pair_does_not_quarantine(tmp_path):
    """After retirement the pruned primary is one generation ahead of a
    backup that still carries the retired record; the pair must load clean."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    old_mint = "OldMint000000000000000000000000000000pump"
    live_mint = "LiveMint00000000000000000000000000000pump"
    assert _observe(store, old_mint, "55000", "2026-07-20T00:00:00Z")
    assert _observe(store, live_mint, "66000", "2026-07-27T09:00:00Z")
    with store._lock:
        store._mints[old_mint]["last_updated_at"] = "2026-07-20T00:00:00Z"
        store._mints[old_mint]["ath_timestamp"] = "2026-07-20T00:00:00Z"
        store._persist_generation_locked()

    run2 = tmp_path / "run2"
    run2.mkdir()
    pruned = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-07-27T10:00:00Z")
    assert pruned.snapshot(old_mint) is None
    # First post-retirement persist: primary = pruned gen N+1, backup = gen N
    # (still carrying the retired record).
    assert _observe(pruned, live_mint, "67000", "2026-07-27T10:01:00Z")

    run3 = tmp_path / "run3"
    run3.mkdir()
    reopened = CentralAthStateStore(
        run3, checkpoint_dir=state_dir, now_utc="2026-07-27T10:02:00Z")
    assert not reopened.checkpoint_quarantined
    assert reopened.checkpoint.checkpoint_ath_regression_rejected == 0
    assert reopened.snapshot(live_mint)["ath_market_cap"] == "67000"


def test_missing_fresh_record_is_a_regression_and_self_heals_from_backup(
        tmp_path):
    """Accidental loss of a FRESH mint is NOT tolerated as retirement: the
    absence reads as a regression, the pair decision rejects the pruned
    generation and restores the higher authenticated evidence from the
    backup (fail-safe recovery; quarantine remains for the case where no
    clean side exists, covered by the both-corrupted test)."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    kept = "KeptMint00000000000000000000000000000pump"
    lost = "LostMint00000000000000000000000000000pump"
    assert _observe(store, kept, "50000", "2026-07-27T09:00:00Z")
    assert _observe(store, lost, "60000", "2026-07-27T09:01:00Z")
    with store._lock:
        store._mints.pop(lost)          # simulate accidental record loss
        store._persist_generation_locked()

    run2 = tmp_path / "run2"
    run2.mkdir()
    reopened = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-07-27T09:05:00Z")
    assert not reopened.checkpoint_quarantined
    assert reopened.checkpoint.checkpoint_recovered_from_backup
    assert reopened.checkpoint.checkpoint_ath_regression_rejected >= 1
    assert reopened.snapshot(lost)["ath_market_cap"] == "60000"
    assert reopened.snapshot(kept)["ath_market_cap"] == "50000"


def test_durable_corrupted_primary_recovers_from_backup(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    assert _observe(store, CQDX_MINT, "50000", "2026-07-27T09:00:00Z")
    assert _observe(store, CQDX_MINT, "51000", "2026-07-27T09:01:00Z")
    (state_dir / "ath_state_checkpoint.json").write_text(
        "{corrupt", encoding="utf-8")

    run2 = tmp_path / "run2"
    run2.mkdir()
    recovered = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-07-27T09:02:00Z")
    assert not recovered.checkpoint_quarantined
    assert recovered.checkpoint.checkpoint_recovered_from_backup
    assert recovered.snapshot(CQDX_MINT)["ath_market_cap"] == "50000"


def test_durable_both_corrupted_fails_closed(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    assert _observe(store, CQDX_MINT, "50000", "2026-07-27T09:00:00Z")
    assert _observe(store, CQDX_MINT, "51000", "2026-07-27T09:01:00Z")
    (state_dir / "ath_state_checkpoint.json").write_text(
        "{corrupt", encoding="utf-8")
    (state_dir / "ath_state_checkpoint.json.bak").write_text(
        "{also-corrupt", encoding="utf-8")

    run2 = tmp_path / "run2"
    run2.mkdir()
    quarantined = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-07-27T09:02:00Z")
    assert quarantined.checkpoint_quarantined
    assert quarantined.snapshot(CQDX_MINT) is None
    # A quarantined store never rewrites the corrupt evidence.
    assert (state_dir / "ath_state_checkpoint.json").read_text(
        encoding="utf-8") == "{corrupt"


def test_per_run_checkpoint_never_retires_or_compacts_records(tmp_path):
    """Retention applies ONLY to the durable cross-run checkpoint: a per-run
    store (no checkpoint_dir) reloads its own state verbatim regardless of
    wall-clock age -- legacy fixtures and same-dir reopens stay intact."""
    store = CentralAthStateStore(tmp_path)
    ancient = "AncientMint00000000000000000000000000pump"
    assert _observe(store, ancient, "90776", "2026-01-01T00:00:00Z")
    with store._lock:
        store._mints[ancient]["last_updated_at"] = "2026-01-01T00:00:00Z"
        store._mints[ancient]["ath_timestamp"] = "2026-01-01T00:00:00Z"
        store._mints[ancient]["seen_event_keys"] = {"evt:1": "t"}
        store._persist_generation_locked()
    reopened = CentralAthStateStore(tmp_path)      # real wall clock anchor
    snapshot = reopened.snapshot(ancient)
    assert snapshot is not None
    assert snapshot["ath_market_cap"] == "90776"
    with reopened._lock:
        assert reopened._mints[ancient]["seen_event_keys"] == {"evt:1": "t"}
    assert reopened.checkpoint_summary()["checkpoint_records_retired"] == 0


def test_long_downtime_retires_everything_and_starts_clean(tmp_path):
    """Downtime beyond the retention horizon: every record retires, the store
    starts empty and healthy, and re-admissions begin as fresh evidence."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run1 = tmp_path / "run1"
    run1.mkdir()
    store = CentralAthStateStore(run1, checkpoint_dir=state_dir)
    assert _observe(store, CQDX_MINT, "116943", "2026-07-27T09:55:16Z")

    run2 = tmp_path / "run2"
    run2.mkdir()
    later = CentralAthStateStore(
        run2, checkpoint_dir=state_dir, now_utc="2026-08-10T00:00:00Z")
    assert not later.checkpoint_quarantined
    assert later.snapshot(CQDX_MINT) is None
    assert _observe(later, CQDX_MINT, "40000", "2026-08-10T00:01:00Z")
    assert later.snapshot(CQDX_MINT)["ath_market_cap"] == "40000"


# =========================================================================
# 3. Live-path candidate continuity: the slot side-channel (starvation fix)
# =========================================================================

class _FakeLiveEpoch:
    integrity_failure = False

    def __init__(self) -> None:
        self.admitted_slots: list = []

    def admit_event(self, slot):
        self.admitted_slots.append(slot)
        if not isinstance(slot, int) or isinstance(slot, bool):
            return False, EPOCH_EVENT_PRE_ARM_REJECTED, "epoch-test"
        return True, EPOCH_EVENT_ADMITTED, "epoch-test"


def _provider_handle_event(monkeypatch, *, event_slot: Optional[int]):
    """Drive the REAL PaidProviderDiscovery._handle_event with fakes."""
    from PHX2.free_tier_producer import paid_provider as pp

    provider = object.__new__(pp.SingleGrpcPumpSwapDiscovery)
    provider._lock = __import__("threading").RLock()
    provider._events_received = 0
    provider._last_message_epoch = 0.0
    provider._last_handoff_durable = False
    provider._now = lambda: 0.0
    provider._live_epoch = _FakeLiveEpoch()
    handoffs = []
    provider._emit_handoff = (
        lambda kind, *args, **kw: handoffs.append((kind, kw)))
    provider._mark_handoff_durable = lambda value: None
    admitted = []
    provider._admit_candidate = (
        lambda candidate: admitted.append(candidate) or True)

    event = SimpleNamespace(          # the frozen normalized event: NO slot
        base_mint=CQDX_MINT, mint=CQDX_MINT,
        pool_account="PoolAccount111111111111111111111111111111111",
        pool_program_id="ProgramId1111111111111111111111111111111111",
        quote_mint="So11111111111111111111111111111111111111112",
        event_id="evt-1", provider_event_id="prov-evt-1",
        observed_at_utc="2026-07-27T10:21:50Z",
        raw_event_hash="hash-1",
    )
    assert not hasattr(event, "slot")
    provider._handle_event(event, event_slot=event_slot)
    return provider, handoffs, admitted


def test_live_migration_with_side_channel_slot_is_admitted(monkeypatch):
    """The 2026-07-27 starvation bug: 38/38 live migrations were rejected
    EPOCH_EVENT_PRE_ARM_REJECTED with migration_slot null.  With the slot
    side-channel the same event is admitted and carries its real slot."""
    provider, handoffs, admitted = _provider_handle_event(
        monkeypatch, event_slot=435_519_912)
    assert provider._live_epoch.admitted_slots == [435_519_912]
    assert not [h for h in handoffs if h[0] == "EPOCH_EVENT_REJECTED"]
    assert len(admitted) == 1
    assert admitted[0]["migration_slot"] == 435_519_912
    assert admitted[0]["live_epoch_id"] == "epoch-test"


def test_live_migration_without_any_slot_still_fails_closed(monkeypatch):
    provider, handoffs, admitted = _provider_handle_event(
        monkeypatch, event_slot=None)
    rejected = [h for h in handoffs if h[0] == "EPOCH_EVENT_REJECTED"]
    assert len(rejected) == 1
    assert rejected[0][1]["reason"] == EPOCH_EVENT_PRE_ARM_REJECTED
    assert admitted == []


POOL = "PoolAccount111111111111111111111111111111111"
PROGRAM = "ProgramId1111111111111111111111111111111111"
QUOTE = "So11111111111111111111111111111111111111112"


def _norm_event(*, mint: str = CQDX_MINT, base_mint: Optional[str] = None,
                event_id: str = "evt-1") -> SimpleNamespace:
    return SimpleNamespace(
        base_mint=mint if base_mint is None else base_mint,
        mint=mint, pool_account=POOL, pool_program_id=PROGRAM,
        quote_mint=QUOTE, event_id=event_id,
        provider_event_id="sig-" + event_id,
        observed_at_utc="2026-07-27T10:21:50Z",
        raw_event_hash="hash-" + event_id)


class _RecordingLiveEpoch:
    """Admits any int slot; records every admission call verbatim."""

    integrity_failure = False

    def __init__(self) -> None:
        self.admitted_slots: list = []
        self.rollovers: list = []

    def admit_event(self, slot):
        self.admitted_slots.append(slot)
        if not isinstance(slot, int) or isinstance(slot, bool):
            return False, EPOCH_EVENT_PRE_ARM_REJECTED, "epoch-test"
        return True, EPOCH_EVENT_ADMITTED, "epoch-test"

    def rollover(self, reason):
        self.rollovers.append(reason)
        return f"epoch-test-{len(self.rollovers) + 1}"

    def close(self, reason):
        return None

    def snapshot(self):
        return {"live_epoch_id": "epoch-test",
                "epoch_status": "EPOCH_HEALTHY"}


def _drive_owner(source_factory, *, settle):
    """Run the REAL SingleGrpcPumpSwapDiscovery pump loop over fake sources."""
    import time as _time

    from PHX2.free_tier_producer.paid_provider import (
        ProviderCandidateDedupe,
        SingleGrpcPumpSwapDiscovery,
    )

    epoch = _RecordingLiveEpoch()
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=source_factory,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.002,
        stale_after_seconds=30,
        live_epoch_manager=epoch,
    )
    owner.start()
    deadline = _time.time() + 2.0
    while not settle(owner, epoch) and _time.time() < deadline:
        _time.sleep(0.005)
    owner.stop(timeout_seconds=1.0)
    return owner, epoch


MINT_B = "SecondMint000000000000000000000000000pump"
MINT_C = "ThirdMint0000000000000000000000000000pump"


def test_consecutive_events_carry_their_own_slots_and_none_never_reuses():
    """Two migrations with different slots + a malformed event between them
    + a slot-less event after: each admission sees ITS OWN slot; the
    slot-less event fails closed instead of reusing the previous slot."""
    calls = {"n": 0}

    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            calls["n"] += 1
            if calls["n"] != 1:
                return
            self.last_event_slot = 100
            yield _norm_event(event_id="evt-a")
            # Malformed between valid events: base mint mismatch -> the
            # handler classifies MALFORMED_EVENT after the epoch gate.
            self.last_event_slot = 101
            yield _norm_event(mint=MINT_B, base_mint="M" * 43 + "x",
                              event_id="evt-bad")
            self.last_event_slot = 102
            yield _norm_event(mint=MINT_B, event_id="evt-b")
            # Slot-less event: the side-channel is None for THIS event.
            self.last_event_slot = None
            yield _norm_event(mint=MINT_C, event_id="evt-c")

    owner, epoch = _drive_owner(
        Source, settle=lambda o, e: len(e.admitted_slots) >= 4)
    queued = owner.drain(10)
    assert epoch.admitted_slots == [100, 101, 102, None]
    assert [(row["token_mint"], row["migration_slot"]) for row in queued] == [
        (CQDX_MINT, 100), (MINT_B, 102)]


def test_reconnect_then_first_event_uses_the_new_streams_slot():
    calls = {"n": 0}

    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            calls["n"] += 1
            if calls["n"] == 1:
                self.last_event_slot = 100
                yield _norm_event(event_id="evt-a")
                # Session ends -> reconnect; the NEXT session's first event
                # publishes ITS slot before anything is admitted.
            elif calls["n"] == 2:
                self.last_event_slot = 435_544_321
                yield _norm_event(mint=MINT_B, event_id="evt-b")

    owner, epoch = _drive_owner(
        Source, settle=lambda o, e: len(e.admitted_slots) >= 2)
    queued = owner.drain(10)
    assert epoch.admitted_slots[:2] == [100, 435_544_321]
    assert [(row["token_mint"], row["migration_slot"]) for row in queued] == [
        (CQDX_MINT, 100), (MINT_B, 435_544_321)]


def test_handler_exception_never_corrupts_the_next_events_slot(monkeypatch):
    """An exception inside event handling ends the stream session; the
    reconnect's next event still binds its own slot exactly."""
    from PHX2.free_tier_producer import paid_provider as pp

    real = pp.event_to_candidate
    blown = {"done": False}

    def exploding(event, **kwargs):
        if getattr(event, "event_id", "") == "evt-a" and not blown["done"]:
            blown["done"] = True
            raise RuntimeError("HANDLER_EXPLODED_FOR_TEST")
        return real(event, **kwargs)

    monkeypatch.setattr(pp, "event_to_candidate", exploding)

    calls = {"n": 0}

    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            calls["n"] += 1
            if calls["n"] == 1:
                self.last_event_slot = 100
                yield _norm_event(event_id="evt-a")
            elif calls["n"] == 2:
                self.last_event_slot = 200
                yield _norm_event(mint=MINT_B, event_id="evt-b")

    owner, epoch = _drive_owner(
        Source, settle=lambda o, e: len(e.admitted_slots) >= 2)
    queued = owner.drain(10)
    assert [(row["token_mint"], row["migration_slot"]) for row in queued] == [
        (MINT_B, 200)]


def test_drained_buffer_candidates_keep_their_buffered_slot():
    """Buffered (quarantined) candidates re-enter admission carrying the
    exact slot the buffer recorded for them."""
    from PHX2.free_tier_producer import paid_provider as pp

    provider = object.__new__(pp.SingleGrpcPumpSwapDiscovery)
    provider._lock = __import__("threading").RLock()
    provider._admit_lock = __import__("threading").RLock()
    provider._events_received = 0
    provider._last_message_epoch = 0.0
    provider._last_handoff_durable = False
    provider._now = lambda: 0.0
    provider._live_epoch = None
    admitted: list = []
    provider._admit_candidate = (
        lambda candidate: admitted.append(candidate) or True)

    class Coordinator:
        def drain_plan(self):
            return {"candidates": [
                {"candidate": {"token_mint": CQDX_MINT,
                               "migration_slot": 435_519_912}},
                {"candidate": {"token_mint": MINT_B,
                               "migration_slot": 435_519_950}},
            ]}

        def mark_drained(self, *, applied, suppressed):
            self.result = (applied, suppressed)

    provider._gap_recovery = Coordinator()
    provider._drain_recovered_buffer()
    assert [(c["token_mint"], c["migration_slot"]) for c in admitted] == [
        (CQDX_MINT, 435_519_912), (MINT_B, 435_519_950)]


def test_quarantine_buffer_stamps_the_source_transaction_slot():
    import inspect

    from PHX2.free_tier_producer import paid_provider as pp

    text = inspect.getsource(pp.SingleGrpcPumpSwapDiscovery)
    stamp = text.index('candidate["migration_slot"] = slot')
    buffer_call = text.index("coordinator.buffer_admitted_candidate(")
    assert stamp < buffer_call


def test_source_publishes_the_slot_side_channel_before_yield():
    import inspect

    from PHX2.free_tier_producer import paid_grpc_source as src

    source_text = inspect.getsource(src.PaidCreatePoolYellowstoneSource)
    assert "self.last_event_slot" in source_text
    publish = source_text.index("self.last_event_slot = (")
    yield_site = source_text.index("yield event")
    assert publish < yield_site


def test_owner_call_sites_thread_the_slot_side_channel():
    import inspect

    from PHX2.free_tier_producer import paid_provider as pp

    text = inspect.getsource(pp.SingleGrpcPumpSwapDiscovery)
    assert text.count('event_slot=getattr(') >= 2


def test_session_wires_durable_ath_dir_and_windowed_reconnect_breaker():
    import inspect

    from PHX2.free_tier_producer import free_tier_session as session

    text = inspect.getsource(session)
    assert "checkpoint_dir=str(durable_ath_dir) if durable_ath_dir" in text
    assert "reconnects_in_window=reconnect_storm_window.observe(" in text


# =========================================================================
# 4. Secret-scan: transient read errors vs real needle hits
# =========================================================================

def test_classify_scan_clean():
    assert classify_redaction_scan({
        "redaction_status": "REDACTED", "total_unsafe_hits": 0,
        "read_errors": {}}) == SCAN_VERDICT_CLEAN


def test_classify_scan_needle_hit_is_unsafe_immediately():
    assert classify_redaction_scan({
        "redaction_status": "REDACTION_VIOLATION", "total_unsafe_hits": 2,
        "read_errors": {}}) == SCAN_VERDICT_UNSAFE


def test_classify_scan_read_error_only_is_debounceable():
    assert classify_redaction_scan({
        "redaction_status": "REDACTION_VIOLATION", "total_unsafe_hits": 0,
        "read_errors": {"x.json": "PermissionError"},
    }) == SCAN_VERDICT_READ_ERROR_ONLY
    assert MAX_CONSECUTIVE_SCAN_READ_FAILURES == 3


def test_classify_scan_without_read_error_detail_fails_closed():
    assert classify_redaction_scan({
        "redaction_status": "REDACTION_VIOLATION", "total_unsafe_hits": 0,
    }) == SCAN_VERDICT_UNSAFE
    assert classify_redaction_scan(None) == SCAN_VERDICT_UNSAFE


def test_scan_vanished_file_is_disclosed_not_a_violation(
        tmp_path, monkeypatch):
    """A file that disappears between rglob and read (atomic checkpoint
    replacement) must not flip a clean run to SECRET_SCAN_FAILURE."""
    (tmp_path / "steady.json").write_text("{}", encoding="utf-8")
    ghost = tmp_path / "ath_state_checkpoint.json.next.tmp"
    ghost.write_text("{}", encoding="utf-8")

    real_read_bytes = Path.read_bytes

    def racing_read_bytes(self):
        if self.name == ghost.name:
            if self.exists():
                self.unlink()          # the atomic replace wins the race
            raise FileNotFoundError(str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", racing_read_bytes)
    monkeypatch.setattr(production_live_artifacts.time, "sleep",
                        lambda seconds: None)
    scan = production_live_artifacts.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    assert scan["total_unsafe_hits"] == 0
    assert scan["vanished_files"] == [ghost.name]
    assert scan["read_errors"] == {}


def test_scan_persistently_unreadable_file_still_fails_closed(
        tmp_path, monkeypatch):
    (tmp_path / "steady.json").write_text("{}", encoding="utf-8")
    locked = tmp_path / "locked.json"
    locked.write_text("{}", encoding="utf-8")

    real_read_bytes = Path.read_bytes

    def locked_read_bytes(self):
        if self.name == locked.name:
            raise PermissionError(str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", locked_read_bytes)
    monkeypatch.setattr(production_live_artifacts.time, "sleep",
                        lambda seconds: None)
    scan = production_live_artifacts.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTION_VIOLATION"
    assert scan["read_errors"] == {"locked.json": "PermissionError"}


def _planted_needle_text() -> str:
    # Assembled from sub-needle atoms so THIS test source never carries a
    # scannable needle; only the runtime-assembled value trips the scanner.
    return ("wss" + ":" + "/" + "/" + "atlas" + "-" + "mainnet" + ".heli"
            + "us-rpc.com/?api" + "-" + "key" + "=PLANTED-TEST-VALUE")


def test_scan_real_needle_in_stable_file_stops_immediately(tmp_path):
    (tmp_path / "steady.json").write_text("{}", encoding="utf-8")
    (tmp_path / "leak.txt").write_text(
        _planted_needle_text(), encoding="utf-8")
    scan = production_live_artifacts.run_redaction_scan(tmp_path)
    assert scan["total_unsafe_hits"] >= 1
    assert scan["redaction_status"] == "REDACTION_VIOLATION"
    assert classify_redaction_scan(scan) == SCAN_VERDICT_UNSAFE
    from PHX2.free_tier_producer.compat.production_live_runner import (
        ScanFailureDebounce,
    )

    assert ScanFailureDebounce().observe(
        classify_redaction_scan(scan)) is True     # first tick, no debounce


def test_scan_needle_in_replaced_destination_is_detected_despite_vanish(
        tmp_path, monkeypatch):
    """The atomic-replace tolerance never hides content: the tmp file may
    vanish, but its REPLACEMENT TARGET is scanned on the same walk and a
    needle there is an immediate violation."""
    target = tmp_path / "ath_state_checkpoint.json"
    target.write_text(
        json.dumps({"note": _planted_needle_text()}), encoding="utf-8")
    ghost = tmp_path / "ath_state_checkpoint.json.next.tmp"
    ghost.write_text("{}", encoding="utf-8")

    real_read_bytes = Path.read_bytes

    def racing_read_bytes(self):
        if self.name == ghost.name:
            if self.exists():
                self.unlink()
            raise FileNotFoundError(str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", racing_read_bytes)
    monkeypatch.setattr(production_live_artifacts.time, "sleep",
                        lambda seconds: None)
    scan = production_live_artifacts.run_redaction_scan(tmp_path)
    assert scan["vanished_files"] == [ghost.name]
    assert scan["total_unsafe_hits"] >= 1
    assert classify_redaction_scan(scan) == SCAN_VERDICT_UNSAFE


def test_needle_hits_are_never_downgraded_to_read_error_only():
    """A scan carrying BOTH a needle hit and read errors is UNSAFE."""
    assert classify_redaction_scan({
        "redaction_status": "REDACTION_VIOLATION",
        "total_unsafe_hits": 1,
        "read_errors": {"x.json": "PermissionError"},
    }) == SCAN_VERDICT_UNSAFE


def test_scan_debounce_three_consecutive_read_errors_stop():
    from PHX2.free_tier_producer.compat.production_live_runner import (
        ScanFailureDebounce,
    )

    debounce = ScanFailureDebounce()
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is False
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is False
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is True


def test_scan_debounce_resets_after_clean_and_still_fails_closed_eventually():
    """A CLEAN scan resets the streak (safe: REDACTED requires every file to
    have been read), one transient race never stops production, and a file
    that STAYS unreadable can never produce the CLEAN that would reset its
    own streak -- so intermittent persistence still reaches the stop."""
    from PHX2.free_tier_producer.compat.production_live_runner import (
        ScanFailureDebounce,
    )

    debounce = ScanFailureDebounce()
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is False  # transient
    assert debounce.observe(SCAN_VERDICT_CLEAN) is False            # resolved
    assert debounce.consecutive_read_failures == 0
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is False
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is False
    assert debounce.observe(SCAN_VERDICT_READ_ERROR_ONLY) is True   # 3rd in a row
    # UNSAFE stops regardless of any prior streak state.
    fresh = ScanFailureDebounce()
    assert fresh.observe(SCAN_VERDICT_CLEAN) is False
    assert fresh.observe(SCAN_VERDICT_UNSAFE) is True


def test_clean_scan_is_impossible_while_any_file_is_unreadable(
        tmp_path, monkeypatch):
    """The invariant the debounce reset relies on: REDACTED requires every
    file read -- an unreadable file always yields READ_ERROR_ONLY, never
    CLEAN, so it cannot reset its own streak."""
    (tmp_path / "steady.json").write_text("{}", encoding="utf-8")
    locked = tmp_path / "locked.json"
    locked.write_text("{}", encoding="utf-8")

    real_read_bytes = Path.read_bytes

    def locked_read_bytes(self):
        if self.name == locked.name:
            raise PermissionError(str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", locked_read_bytes)
    monkeypatch.setattr(production_live_artifacts.time, "sleep",
                        lambda seconds: None)
    verdicts = [
        classify_redaction_scan(
            production_live_artifacts.run_redaction_scan(tmp_path))
        for _ in range(3)
    ]
    assert verdicts == [SCAN_VERDICT_READ_ERROR_ONLY] * 3
    from PHX2.free_tier_producer.compat.production_live_runner import (
        ScanFailureDebounce,
    )

    debounce = ScanFailureDebounce()
    assert [debounce.observe(v) for v in verdicts] == [False, False, True]


def test_runner_loop_sites_route_through_the_debounce():
    import inspect

    from PHX2.free_tier_producer.compat import production_live_runner as runner

    text = inspect.getsource(runner.run_production_live_watch)
    assert text.count("scan_debounce.observe(") == 2
    assert "classify_redaction_scan(scan)" in text


# =========================================================================
# 11. Migration decode-latency observability (acceptance-review metric only)
# =========================================================================

def test_ken_class_decode_latency_measures_extreme():
    """KEN's proven shape: chain migration 11:00:07Z, live decode
    11:10:59.16Z (~652s), seeded by the 11:39:53Z sweep, ATH before
    admission — every number the acceptance report needs, from fields the
    pipeline already persists."""
    from PHX2.free_tier_producer.ping_quality_review import (
        LATENCY_REVIEW_EXTREME,
        build_migration_latency_observability,
    )

    block = build_migration_latency_observability(
        candidate={
            "migration_time_utc": "2026-07-27T11:00:07Z",
            "local_observed_at_utc": "2026-07-27T11:10:59.160595Z",
            "discovery_utc": "2026-07-27T11:39:53Z",
            "migration_slot": 435525387,
            "migration_time_source": "PROVIDER_EVENT_TIME",
            "migration_time_authoritative": True,
            "discovery_provenance": "LIVE_YELLOWSTONE",
        },
        activation={
            "activated_at_utc": None,
            "activation_evidence_ingested_at_utc": None,
        },
        central_ath={"ath_timestamp": "2026-07-27T11:07:54Z"},
    )
    assert block["migration_slot"] == 435525387
    assert block["migration_to_decode_seconds"] == pytest.approx(
        652.161, abs=0.01)
    assert block["decode_to_admission_seconds"] == pytest.approx(
        1733.839, abs=0.01)
    assert block["migration_to_admission_seconds"] == pytest.approx(
        2386.0, abs=0.01)
    assert block["ath_before_admission"] is True
    assert block["decode_latency_review"] == LATENCY_REVIEW_EXTREME
    assert block["review_semantics"] == (
        "OBSERVABILITY_ACCEPTANCE_REVIEW_ONLY")


def test_decode_latency_review_class_boundaries():
    from PHX2.free_tier_producer.ping_quality_review import (
        LATENCY_REVIEW_EXTREME,
        LATENCY_REVIEW_OK,
        LATENCY_REVIEW_REVIEW,
        LATENCY_REVIEW_UNAVAILABLE,
        MIGRATION_DECODE_LATENCY_EXTREME_SECONDS,
        MIGRATION_DECODE_LATENCY_REVIEW_SECONDS,
        classify_decode_latency,
    )

    assert MIGRATION_DECODE_LATENCY_REVIEW_SECONDS == 90.0
    assert MIGRATION_DECODE_LATENCY_EXTREME_SECONDS == 600.0
    assert classify_decode_latency(0.5) == LATENCY_REVIEW_OK
    assert classify_decode_latency(89.999) == LATENCY_REVIEW_OK
    assert classify_decode_latency(90.0) == LATENCY_REVIEW_REVIEW
    assert classify_decode_latency(599.999) == LATENCY_REVIEW_REVIEW
    assert classify_decode_latency(600.0) == LATENCY_REVIEW_EXTREME
    assert classify_decode_latency(None) == LATENCY_REVIEW_UNAVAILABLE
    assert classify_decode_latency("652") == LATENCY_REVIEW_UNAVAILABLE
    assert classify_decode_latency(True) == LATENCY_REVIEW_UNAVAILABLE


def test_backfill_candidate_latency_is_unavailable_not_fabricated():
    """A restart-backfill candidate has no live decode: latencies stay None
    and the review class says UNAVAILABLE instead of inventing a number."""
    from PHX2.free_tier_producer.ping_quality_review import (
        LATENCY_REVIEW_UNAVAILABLE,
        build_migration_latency_observability,
    )

    block = build_migration_latency_observability(
        candidate={
            "migration_time_utc": "2026-07-27T06:49:41Z",
            "discovery_utc": "2026-07-27T07:38:07Z",
            "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
        },
        activation={},
        central_ath={},
    )
    assert block["migration_to_decode_seconds"] is None
    assert block["decode_latency_review"] == LATENCY_REVIEW_UNAVAILABLE
    assert block["migration_to_admission_seconds"] == pytest.approx(2906.0)
    assert block["ath_before_admission"] is None
    assert block["provenance"] == "DEXSCREENER_RESTART_BACKFILL"


def test_malformed_timestamps_yield_none_not_errors():
    from PHX2.free_tier_producer.ping_quality_review import (
        build_migration_latency_observability,
    )

    block = build_migration_latency_observability(
        candidate={"migration_time_utc": "not-a-time",
                   "local_observed_at_utc": 12345},
        activation={"activated_at_utc": ""},
        central_ath={"ath_timestamp": None},
    )
    assert block["migration_to_decode_seconds"] is None
    assert block["admission_to_activation_seconds"] is None
    assert block["ath_before_admission"] is None


def test_quality_record_carries_the_latency_block_and_stays_redaction_safe():
    from PHX2.free_tier_producer.ping_quality_review import (
        build_ping_quality_record,
        ping_quality_record_is_redaction_safe,
    )

    record = build_ping_quality_record(
        candidate={
            "candidate_id": "cand-1", "token_mint": CQDX_MINT,
            "discovery_provenance": "LIVE_YELLOWSTONE",
            "migration_time_utc": "2026-07-27T09:44:23Z",
            "local_observed_at_utc": "2026-07-27T09:44:23.657939Z",
            "discovery_utc": "2026-07-27T09:44:24Z",
            "migration_slot": 435514577,
        },
        recheck={
            "reason": "NO_SEND_PENDING_ACTIVATION_THRESHOLD",
            "market_context": {"current_market_cap_usd": "43800",
                               "central_ath": {
                                   "ath_market_cap": "116943",
                                   "ath_timestamp": "2026-07-27T09:55:16Z"}},
            "activation": {"activated_at_utc": "2026-07-27T10:18:55Z",
                           "migration_market_cap_usd": "31328"},
        },
        security=None,
        observed_at_utc="2026-07-27T10:20:00Z",
    )
    block = record["latency_observability"]
    assert block["latency_schema"] == (
        "phx2_migration_latency_observability_v1")
    assert block["migration_to_decode_seconds"] == pytest.approx(0.658, abs=0.01)
    assert block["decode_latency_review"] == "OK"
    assert block["ath_before_admission"] is False
    assert ping_quality_record_is_redaction_safe(record)


# =========================================================================
# 5. Windowed reconnect-storm breaker
# =========================================================================

def test_slow_reconnects_over_hours_never_trip_the_storm_breaker():
    """The 2026-07-27 run: 6 provider resets at 11:38, 12:09, 12:59, 13:04,
    13:09 and 13:12 UTC crossed the LIFETIME cap of 5 and killed a healthy
    run.  Under the 30-minute window the same series never reads as a storm."""
    clock = {"now": 0.0}
    window = ReconnectStormWindow(now_fn=lambda: clock["now"])
    resets = [0.0, 4635.0, 6470.0, 9475.0, 9771.0, 10049.0, 10272.0]
    worst = 0
    for cumulative, at in enumerate(resets):
        clock["now"] = at
        worst = max(worst, window.observe(cumulative))
    assert worst <= 5
    assert paid_provider_safety_error(
        {"reconnects": 6}, max_reconnects=5,
        reconnects_in_window=worst) is None


def test_rapid_reconnect_churn_still_trips_the_storm_breaker():
    clock = {"now": 0.0}
    window = ReconnectStormWindow(now_fn=lambda: clock["now"])
    verdicts = []
    for count in range(7):             # 6 reconnects inside 6 minutes
        clock["now"] = count * 60.0
        observed = window.observe(count)
        verdicts.append(paid_provider_safety_error(
            {"reconnects": count}, max_reconnects=5,
            reconnects_in_window=observed))
    assert verdicts[-1] == "PAID_PROVIDER_RECONNECT_STORM"


def test_cumulative_semantics_preserved_when_no_window_supplied():
    assert paid_provider_safety_error(
        {"reconnects": 6}, max_reconnects=5) == (
        "PAID_PROVIDER_RECONNECT_STORM")


def test_reconnect_window_resets_on_fresh_provider_counter():
    clock = {"now": 0.0}
    window = ReconnectStormWindow(now_fn=lambda: clock["now"])
    clock["now"] = 10.0
    assert window.observe(6) == 0      # first sighting: baseline, no storm
    clock["now"] = 20.0
    assert window.observe(0) == 0      # counter regressed: new provider
    clock["now"] = 30.0
    assert window.observe(2) == 2


def test_other_safety_refusals_are_untouched():
    assert paid_provider_safety_error(
        {"max_active_streams": 2}, max_reconnects=5,
        reconnects_in_window=0) == "PAID_PROVIDER_STREAM_OVERLAP"


# =========================================================================
# 6. Watchdog: epoch durability race is not an integrity failure
# =========================================================================

def _epoch_inputs(**overrides) -> HealthInputs:
    base = dict(
        producer_expected=True, producer_pid=24568, producer_alive=True,
        producer_identity_ok=True, logical_producer_count=1,
        producer_uptime_seconds=10_351.0,
        heartbeat_present=True, heartbeat_parse_ok=True,
        heartbeat_age_seconds=3.0,
        yellowstone_owner_count=1, max_active_streams_observed=1,
        recovery_document_state="RETIRED_AUDIT_ONLY",
        recovery_state="HISTORICAL_BLOCK_REPLAY_RETIRED_FROM_PRODUCTION",
        live_epoch_required=True,
        epoch_document_state="VALID_CURRENT",
        telegram_enabled=True, discord_enabled=False,
        send_capable_transport_count=1,
    )
    base.update(overrides)
    return HealthInputs(**base)


def test_fresh_epoch_rollover_within_grace_is_not_integrity_failure():
    """The 13:12:44Z rollover observed 59 s later must not open the circuit."""
    verdict = evaluate_health(_epoch_inputs(
        epoch_status="EPOCH_STARTING", epoch_durable=False,
        epoch_age_seconds=58.8))
    assert verdict.health_class != NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_NOT_DURABLE not in verdict.reasons


def test_starting_epoch_non_durable_past_grace_still_opens_circuit():
    verdict = evaluate_health(_epoch_inputs(
        epoch_status="EPOCH_STARTING", epoch_durable=False,
        epoch_age_seconds=301.0))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_NOT_DURABLE in verdict.reasons


def test_healthy_epoch_non_durable_is_still_an_integrity_failure():
    verdict = evaluate_health(_epoch_inputs(
        epoch_status="EPOCH_HEALTHY", epoch_durable=False,
        epoch_age_seconds=3600.0))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_NOT_DURABLE in verdict.reasons


def test_closed_valid_epoch_observation_reports_durable(tmp_path):
    """The 13:13:43Z incident inputs: producer alive mid-shutdown, disk epoch
    already CLOSED and authenticated, heartbeat one tick behind.  The
    observation must report durable instead of opening an integrity circuit."""
    import PHX2.watchdog.observe as obs

    resolution = obs.ProductionPolicyResolution(
        state=obs.PRODUCTION_POLICY_VALID,
        source=obs.PRODUCTION_POLICY_SOURCE_HEARTBEAT,
        production_mode="LIVE_EPOCH_WITH_DEX_BACKFILL",
        live_epoch_required=True,
        reason="CURRENT_HEARTBEAT_POLICY_VALID",
    )
    # Mirror of build_observation's epoch_durable computation with the CLOSED
    # carve-out applied (the pure decision, isolated from file plumbing).
    policy_valid = resolution.state == obs.PRODUCTION_POLICY_VALID
    epoch_disk_state = "VALID_CURRENT"
    epoch_identity_matches = True
    epoch_status = "EPOCH_CLOSED"
    heartbeat_epoch = {"epoch_durable": True,
                       "epoch_status": "EPOCH_STARTING"}
    epoch_durable = bool(
        policy_valid and epoch_disk_state == "VALID_CURRENT"
        and epoch_identity_matches
        and (heartbeat_epoch.get("epoch_durable") is True
             and heartbeat_epoch.get("epoch_status") == epoch_status))
    assert epoch_durable is False       # the pre-fix inputs really disagree
    if not epoch_durable and policy_valid \
            and epoch_disk_state == "VALID_CURRENT" \
            and epoch_identity_matches and epoch_status == "EPOCH_CLOSED":
        epoch_durable = True
    verdict = evaluate_health(_epoch_inputs(
        epoch_status="EPOCH_CLOSED", epoch_durable=epoch_durable,
        epoch_age_seconds=58.8))
    assert verdict.health_class != NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_NOT_DURABLE not in verdict.reasons


def test_observe_source_carries_the_closed_epoch_carve_out():
    import inspect

    import PHX2.watchdog.observe as obs

    text = inspect.getsource(obs.build_observation)
    assert 'epoch_status == "EPOCH_CLOSED"' in text


# =========================================================================
# 7. Operator status/stop: stale heartbeat ownership and stop invariants
# =========================================================================

class _StoppedBackend:
    """The exact post-stop world of 2026-07-27: no live process, no live
    lock, a persisted watchdog status claiming yellowstone_owner_count=1 and
    an OPEN integrity circuit, a durable CLOSED epoch on disk."""

    def __init__(self, *, owners_claim: int = 1):
        self.repo_root = Path(".")
        self.actions: list = []
        self.owners_claim = owners_claim

    def task_status(self):
        return {"task_present": True, "managed_schema_ok": True,
                "task_state": "Disabled"}

    def task_action(self, action):
        self.actions.append(action)
        return {"_ok": True, "task_state": "Disabled"}

    def watchdog_snapshot(self):
        return {
            "status": {"observation": {
                "yellowstone_owner_count": self.owners_claim,
                "heartbeat_age_seconds": 3.0,
                "epoch_status": "EPOCH_CLOSED",
                "epoch_durable": False,
                "epoch_identity_matches": True,
            }},
            "circuit_status": "OPEN",
            "circuit_open_reason": "EPOCH_NOT_DURABLE",
            "circuit_integrity_locked": True,
            "watchdog_lock_holder_pid": None,
            "producer_lock_holder_pid": None,
        }

    def process_table(self):
        return []

    def latest_heartbeat(self):
        return {
            "provider_telemetry": {
                "primary_source_state": "CONNECTED",
                "shadow_state": "CONNECTED",
            },
        }

    def request_watchdog_stop(self):
        return True

    def runtime_locks_absent(self):
        return True

    def monotonic(self):
        return 0.0

    def sleep(self, seconds):
        pass


@pytest.fixture
def stopped_world(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli, "resolve_repo_head", lambda root: "e" * 40)
    monkeypatch.setattr(
        cli, "default_production_config",
        lambda expected_head: SimpleNamespace(
            live_epoch_primary_path=tmp_path / "live_epoch_state.json"))
    monkeypatch.setattr(
        cli, "classify_live_epoch_document_set",
        lambda path: ("VALID_CURRENT", {
            "live_epoch_id": "epoch_d478578be0a9428eb34d",
            "epoch_status": "EPOCH_CLOSED",
            "epoch_start_slot": 435544303,
        }, {}))
    monkeypatch.setattr(
        cli, "ledger_identity",
        lambda path: {"parse_ok": True, "lines": 17, "sha256": "5" * 64,
                      "bytes": 6228})
    monkeypatch.setattr(
        cli, "_last_ledger_timestamp", lambda path: "2026-07-27T11:45:50Z")


def test_stopped_status_reports_zero_owners_and_discloses_stale_claim(
        stopped_world, capsys):
    status = cli.collect_status(_StoppedBackend())
    assert status.state == "STOPPED"
    assert status.yellowstone_owners == 0
    assert status.stale_yellowstone_owners == 1
    assert status.epoch_durable is True
    assert status.epoch_identity_matches is True
    assert status.epoch_document_state == "VALID_CURRENT"
    assert status.primary_source_state == "STOPPED"
    assert status.shadow_state == "DISABLED"
    # The durable circuit latch is surfaced verbatim -- never hidden.
    assert status.circuit == "OPEN"
    assert status.circuit_reason == "EPOCH_NOT_DURABLE"
    cli.print_status(status)
    out = capsys.readouterr().out
    assert "Yellowstone owners: 0 (stale heartbeat claimed 1" in out
    assert "Epoch durable: True" in out


def test_stopped_status_is_stable_and_idempotent(stopped_world):
    backend = _StoppedBackend()
    first = cli.collect_status(backend)
    second = cli.collect_status(backend)
    assert first == second


def test_running_status_keeps_live_owner_count(stopped_world, monkeypatch):
    backend = _StoppedBackend()
    live_pid = __import__("os").getpid()
    snapshot = backend.watchdog_snapshot()
    snapshot["watchdog_lock_holder_pid"] = live_pid
    snapshot["producer_lock_holder_pid"] = live_pid
    monkeypatch.setattr(backend, "watchdog_snapshot", lambda: snapshot)
    status = cli.collect_status(backend)
    assert status.state == "RUNNING"
    assert status.yellowstone_owners == 1
    assert status.stale_yellowstone_owners is None


def test_stop_prints_cleanly_only_after_final_invariants_agree(
        stopped_world, capsys):
    backend = _StoppedBackend()
    assert cli.stop(backend) == 0
    out = capsys.readouterr().out
    assert "PHX2 STOPPED CLEANLY" in out
    assert "disable" in backend.actions


def test_stop_refuses_clean_claim_when_epoch_document_is_invalid(
        stopped_world, monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "classify_live_epoch_document_set",
        lambda path: ("INVALID_CORRUPT", {}, {}))
    backend = _StoppedBackend()
    assert cli.stop(backend) == 2
    out = capsys.readouterr().out
    assert "PHX2 STOPPED CLEANLY" not in out
    assert "final status invariants disagree" in out


# =========================================================================
# 8. Backfill provenance / ATH coverage rendering (invariants 12, 13)
# =========================================================================

def _ping_data(**overrides) -> TelegramPingData:
    base = dict(
        token_mint=CQDX_MINT,
        token_identity="Double Dih Dog ($Willy)",
        token_metadata_source="DEXSCREENER_RESTART_BACKFILL",
        age_minutes=85, age_display="1h 25m", tier=2,
        market_cap="$43.8k", post_migration_ath="$116.9k",
        migration_market_cap="$31.3k", floor="-62%",
        # Display fields carry the 2026-07-28 adapter outputs: unavailable
        # canonical evidence renders the marker; the reason codes live in
        # field_reason_codes / artifacts only.
        volume="—",
        liquidity="—",
        quote_side_liquidity="—",
        liquidity_basis="UNAVAILABLE",
        liquidity_quality="NOT SCORED (NO APPROVED LIQUIDITY QUALITY RULE)",
        fee_gate_label="Normal", fee_gate_score="0",
        lp_integrity="DISABLED", composite_verdict="PASS",
        bribes_amm_pct="4.4%", creator_pct="52.2%",
        bribes_per_tx_lamports="278,478",
        structure_read="balanced fees",
        ante_last20_median="0.000005", ante_last20_p25="0.000005",
        ante_last20_p75="0.000161", ante_5m_median="0.000046",
        ante_5m_sample_count="127", base_fee_coverage="100%",
        ante_last20_width="32.1", ante_5m_width="58.1",
        priority_fee_median_lamports="7,074",
        priority_fee_sample_count="20",
        shape_5m="NO APPROVED SHAPE RULE", shape_5m_rule="N/A",
        shape_last20="NO APPROVED SHAPE RULE", shape_last20_rule="N/A",
        builder_read=(BuilderReadStatement(
            "Attention is weak",
            ("EVENT_PACE_ATTENTION_WEAK",)),),
    )
    base.update(overrides)
    return TelegramPingData(**base)


def test_live_complete_body_is_unchanged_and_has_no_disclosure_line():
    body = compose_telegram_ping(_ping_data(
        discovery_provenance="LIVE",
        ath_coverage=ATH_COVERAGE_COMPLETE_LIVE)).text
    assert "Post-mig ATH: $116.9k" in body
    assert "Source:" not in body
    assert "ATH coverage" not in body


def test_backfill_body_discloses_partial_coverage_and_never_claims_post_mig():
    body = compose_telegram_ping(_ping_data(
        discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
        ath_coverage=ATH_COVERAGE_PARTIAL_SINCE_ADMISSION)).text
    assert "Obs ATH: $116.9k" in body
    assert "Post-mig ATH" not in body
    # One compact provider-neutral coverage line (2026-07-28 remediation):
    # the internal enum and provider name stay artifact-only, and the body
    # never carries the provider-name needle the runtime scanner bans.
    assert "• Coverage: Partial (restart backfill)" in body
    assert "PARTIAL_SINCE_ADMISSION" not in body
    assert "ATH coverage" not in body
    assert "true post-mig drawdown" not in body
    assert "DEXSCREENER" not in body


def test_backfill_body_passes_the_runtime_redaction_scanner():
    """The disclosure line must never trip the per-tick artifact scanner or
    force the send-result body preview to WITHHELD_UNSAFE."""
    body = compose_telegram_ping(_ping_data(
        discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
        ath_coverage=ATH_COVERAGE_PARTIAL_SINCE_ADMISSION)).text
    assert production_live_artifacts.scan_text(body) == []


def test_unknown_provenance_also_discloses():
    body = compose_telegram_ping(_ping_data(
        discovery_provenance="UNKNOWN",
        ath_coverage=ATH_COVERAGE_UNKNOWN)).text
    assert "Obs ATH" in body
    assert "Post-mig ATH" not in body
    assert "• Coverage: Unknown" in body


def test_backfill_candidate_cannot_claim_complete_live_coverage():
    with pytest.raises(ValueError, match="ATH_COVERAGE_PROOF_INCONSISTENT"):
        _ping_data(
            discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
            ath_coverage=ATH_COVERAGE_COMPLETE_LIVE)


def test_invalid_coverage_token_is_rejected():
    with pytest.raises(ValueError, match="ATH_COVERAGE_INVALID"):
        _ping_data(ath_coverage="TOTAL")
    with pytest.raises(ValueError, match="DISCOVERY_PROVENANCE_INVALID"):
        _ping_data(discovery_provenance="GUESSED")


def test_adapter_derives_coverage_from_candidate_provenance():
    from PHX2.delivery.telegram_adapter import build_ping_data

    def _context(provenance):
        fee = SimpleNamespace(
            candidate_mint=CQDX_MINT, total_fees=Decimal("7.63"),
            lp_fees=Decimal("0.71"), protocol_fees=Decimal("2.94"),
            creator_fees=Decimal("3.98"),
            event_pace_per_minute=Decimal("59"), event_count=5000,
            fee_gate_label="Normal", fee_gate_score=0,
            fee_gate_reasons=(), balanced_fees=True,
            bribe_share_pct=Decimal("4.4"), creator_share=Decimal("0.52"),
            bribes_per_transaction=Decimal("0.000278478"),
            first_observed_at_utc="2026-07-27T09:44:23Z",
            last_observed_at_utc="2026-07-27T10:20:46Z",
            ante_last20_median=Decimal("0.000005"),
            ante_last20_p25=Decimal("0.000005"),
            ante_last20_p75=Decimal("0.000161"),
            ante_last20_sample_count=20,
            ante_5m_median=Decimal("0.000046"),
            ante_5m_p25=Decimal("0.0000008"),
            ante_5m_p75=Decimal("0.0000459"),
            ante_5m_sample_count=127,
            ante_5m_base_fee_coverage=Decimal("1"),
            priority_fee_median_lamports=7074,
            priority_fee_sample_count=20,
            ante_5m_shape=None, ante_5m_shape_rule=None,
            ante_last20_shape=None, ante_last20_shape_rule=None,
        )
        security = SimpleNamespace(
            fee_snapshot=fee, lp_snapshot=None,
            lp_integrity_mode="DISABLED_SINGLE_STREAM",
            verdict="ALLOW",
        )
        candidate = {
            "token_mint": CQDX_MINT,
            "token_name": "Double Dih Dog",
            "symbol_or_name": "Willy",
            "migration_time_utc": "2026-07-27T09:44:23Z",
        }
        if provenance is not None:
            candidate["discovery_provenance"] = provenance
        snapshot = SimpleNamespace(
            token_mint=CQDX_MINT, tier_token="Tier 2",
            current_market_cap_usd=Decimal("43800"))
        return snapshot, {
            "candidate": candidate,
            "market_context": {
                "current_market_cap_usd": "43800",
                "central_ath": {"ath_market_cap": "116943"},
            },
            "activation": {"migration_market_cap_usd": "31300"},
            "security_decision": security,
        }

    snapshot, context = _context("DEXSCREENER_RESTART_BACKFILL")
    data = build_ping_data(
        mint=CQDX_MINT, composed_snapshot=snapshot,
        delivery_context=context, now_utc="2026-07-27T11:09:44Z")
    assert data.discovery_provenance == "DEXSCREENER_RESTART_BACKFILL"
    assert data.ath_coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert data.field_reason_codes["post_migration_ath"] == (
        "ATH_COVERAGE_PARTIAL_SINCE_ADMISSION",)

    snapshot, context = _context("LIVE_YELLOWSTONE")
    data = build_ping_data(
        mint=CQDX_MINT, composed_snapshot=snapshot,
        delivery_context=context, now_utc="2026-07-27T11:09:44Z")
    assert data.discovery_provenance == "LIVE"
    assert data.ath_coverage == ATH_COVERAGE_COMPLETE_LIVE

    snapshot, context = _context(None)
    data = build_ping_data(
        mint=CQDX_MINT, composed_snapshot=snapshot,
        delivery_context=context, now_utc="2026-07-27T11:09:44Z")
    assert data.discovery_provenance == "UNKNOWN"
    assert data.ath_coverage == ATH_COVERAGE_UNKNOWN


# =========================================================================
# 9. Ante samples never imply canonical volume (invariants 19, 20)
# =========================================================================

def test_ante_samples_do_not_backfill_missing_canonical_volume():
    """4FnZD…pump: 127 five-minute ante samples while canonical volume had
    zero accepted swap samples.  The two evidence streams stay independent."""
    from PHX2.delivery.telegram_adapter import _canonical_volume_display

    display, snapshot, reason = _canonical_volume_display(
        {"canonical_volume_5m": {
            "mint": CQDX_MINT, "status": "INSUFFICIENT_DATA"}}, CQDX_MINT)
    assert display == "—"
    assert reason == "CANONICAL_SWAP_SAMPLE_INSUFFICIENT"

    body = compose_telegram_ping(_ping_data(
        volume="—", ante_5m_sample_count="127")).text
    assert "Vol 5m: —" in body
    assert "INSUFFICIENT" not in body
    assert "(n=127)" in body


def test_valid_canonical_volume_renders_with_samples():
    from PHX2.delivery.telegram_adapter import _canonical_volume_display

    display, snapshot, reason = _canonical_volume_display(
        {"canonical_volume_5m": {
            "mint": CQDX_MINT, "status": "VALID", "observe_only": True,
            "window_seconds": 300, "gross_volume_usd": "1904.81",
            "net_quote_flow_usd": "-350", "sample_count": 51,
        }}, CQDX_MINT)
    assert reason is None
    assert "gross" in display and "(n=51)" in display


# =========================================================================
# 10. Exact-pair actual-reserve display stays fail-closed and exact
# =========================================================================

def _reserve_market(*, pool="PoolAccount111111111111111111111111111111111",
                    observed="2026-07-27T11:09:40Z",
                    quote_observed="2026-07-27T11:09:41Z"):
    return {
        "current_price": "0.0000438",
        "pumpswap_reserve": {
            "reserve_validation_status": "VALID",
            "quote_price_usd": "100",
            "quote_price_observed_at_utc": quote_observed,
            "actual_liquidity_definition": (
                "REAL_QUOTE_VAULT_PLUS_REAL_BASE_VAULT_AT_ACCEPTED_"
                "CURRENT_PRICE"),
            "quote_side_liquidity_definition": "REAL_QUOTE_VAULT_ONLY",
            "actual_quote_liquidity_usd": "5000",
            "actual_token_liquidity_usd": "4380",
            "actual_pool_tvl_usd": "9380",
            "reserve_artifact": {
                "pool_address": pool,
                "base_mint": CQDX_MINT,
                "observation_timestamp": observed,
                "raw_quote_reserves": "50000000000",
                "virtual_quote_reserves": "25000000000",
                "effective_quote_reserves": "75000000000",
                "base_reserves": "100000000000000000",
                "quote_decimals": 9,
                "base_decimals": 9,
            },
        },
    }


def _liquidity(candidate_pair, market, now="2026-07-27T11:09:44Z"):
    from PHX2.delivery.telegram_adapter import _actual_liquidity_display

    return _actual_liquidity_display(
        mint=CQDX_MINT,
        candidate={"pair_address": candidate_pair},
        market=market, now_utc=now)


def test_fresh_matching_reserves_display_actual_tvl_from_raw_vaults():
    display, quote_display, basis, value, reason = _liquidity(
        "PoolAccount111111111111111111111111111111111", _reserve_market())
    assert reason is None
    assert basis == "TOTAL_ACTUAL_POOL_TVL"
    assert display == "$9.4k" and quote_display == "$5k"
    assert value == Decimal("9380")


def test_wrong_pair_reserves_are_rejected():
    display, _, basis, value, reason = _liquidity(
        "OtherPool11111111111111111111111111111111111", _reserve_market())
    assert reason == "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE"
    assert basis == "UNAVAILABLE" and value is None


def test_stale_reserves_are_rejected_and_fresh_recovers():
    stale = _liquidity(
        "PoolAccount111111111111111111111111111111111",
        _reserve_market(observed="2026-07-27T11:03:40Z",
                        quote_observed="2026-07-27T11:03:41Z"))
    assert stale[4] == "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE"
    fresh = _liquidity(
        "PoolAccount111111111111111111111111111111111", _reserve_market())
    assert fresh[4] is None


def test_effective_virtual_reserves_never_substitute_for_actual_vaults():
    market = _reserve_market()
    artifact = market["pumpswap_reserve"]["reserve_artifact"]
    # Claim the EFFECTIVE (virtual-inclusive) quote as the actual quote-side
    # liquidity: the cross-check must refuse the display.
    market["pumpswap_reserve"]["actual_quote_liquidity_usd"] = "7500"
    market["pumpswap_reserve"]["actual_pool_tvl_usd"] = "11880"
    assert artifact["virtual_quote_reserves"] != "0"
    display, _, basis, value, reason = _liquidity(
        "PoolAccount111111111111111111111111111111111", market)
    assert reason == "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE"
    assert value is None
