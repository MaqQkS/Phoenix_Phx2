"""Scheduler degradation must describe the PRESENT, not the run's history.

The 2026-07-29 acceptance run ended reporting ``SCHEDULER_DEGRADED`` with
``['MARKET_LATENCY_SLO_BREACHED', 'MARKET_OBSERVATION_STARVED']`` and an oldest
deadline age of 2,909 s -- while its queue was empty, nothing was in flight and
16 workers were alive.  Two independent defects produced that:

* ``_degraded_reasons`` was an append-only set.  One transient breach anywhere
  in the run pinned SCHEDULER_DEGRADED for the whole process lifetime, so the
  state could never clear and a current problem was indistinguishable from an
  old one.
* the oldest-deadline metric counted every due field group, including
  candidates the planner deliberately DEFERS (a recovery backoff whose next
  probe is not yet due).  That run had 8 candidates legitimately backing off,
  so "starved" and "waiting on purpose" reported identically.
"""

from __future__ import annotations

import time

from PHX2.free_tier_producer.market_scheduler import (
    CandidateScheduleView,
    DEGRADED_REASON_TTL_SECONDS,
    MARKET_LATENCY_SLO_BREACHED,
    MARKET_OBSERVATION_STARVED,
    MarketScheduler,
    MarketSchedulerConfig,
    SCHEDULER_DEGRADED,
    SCHEDULER_READY,
)

NOW = 1_700_000_000.0


class _Clock:
    def __init__(self, start: float = NOW) -> None:
        self.value = float(start)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


def _scheduler(clock, config=None):
    return MarketScheduler(
        price_fetch_fn=None,
        overview_fetch_fn=None,
        batch_price_fetch_fn=None,
        config=config or MarketSchedulerConfig(),
        now_fn=clock,
        monotonic_fn=time.monotonic,
    )


def _view(index, *, clock, status="PENDING_1_20X", age=1.0,
          next_recovery=None, market_state=None, quarantined=False,
          terminal_history=False):
    return CandidateScheduleView(
        mint=f"mint-{index:03d}-pump",
        candidate_id=f"candidate-{index:03d}",
        generation=index + 1,
        status=status,
        seeded_at_epoch=clock() - age,
        market_state=market_state,
        last_observed_epoch=None,
        next_recovery_epoch=next_recovery,
        activation_target_market_cap_usd="120",
        last_activation_market_cap_usd="20",
        delivery_retry_due=False,
        quarantined=quarantined,
        terminal_history=terminal_history,
    )


# ---------------------------------------------------------------------------
# 1. degraded reasons are observations with an age, not a lifetime latch
# ---------------------------------------------------------------------------


def test_a_single_transient_breach_does_not_pin_degraded_forever():
    clock = _Clock()
    scheduler = _scheduler(clock)
    assert scheduler.scheduler_state() == SCHEDULER_READY

    scheduler._note_degraded(MARKET_LATENCY_SLO_BREACHED)
    assert scheduler.scheduler_state() == SCHEDULER_DEGRADED

    # Nothing re-observes it; the scheduler recovered.
    clock.advance(DEGRADED_REASON_TTL_SECONDS + 1.0)
    assert scheduler.scheduler_state() == SCHEDULER_READY
    assert scheduler.stats()["market_scheduler_degraded_reasons"] == []


def test_a_recurring_breach_stays_degraded():
    clock = _Clock()
    scheduler = _scheduler(clock)
    for _ in range(5):
        scheduler._note_degraded(MARKET_OBSERVATION_STARVED)
        clock.advance(DEGRADED_REASON_TTL_SECONDS / 2.0)
        assert scheduler.scheduler_state() == SCHEDULER_DEGRADED


def test_lifetime_history_is_preserved_after_the_reported_set_clears():
    """Ageing the reported set must not destroy evidence."""

    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler._note_degraded(MARKET_LATENCY_SLO_BREACHED)
    scheduler._note_degraded(MARKET_LATENCY_SLO_BREACHED)
    scheduler._note_degraded(MARKET_OBSERVATION_STARVED)
    clock.advance(DEGRADED_REASON_TTL_SECONDS + 1.0)

    stats = scheduler.stats()
    assert stats["market_scheduler_degraded_reasons"] == []
    assert stats["market_scheduler_slo_breached"] is False
    lifetime = stats["market_scheduler_degraded_reasons_lifetime"]
    assert lifetime[MARKET_LATENCY_SLO_BREACHED] == 2
    assert lifetime[MARKET_OBSERVATION_STARVED] == 1


def test_only_currently_observed_reasons_reach_the_slo_flag():
    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler._note_degraded(MARKET_OBSERVATION_STARVED)
    assert scheduler.stats()["market_scheduler_slo_breached"] is True
    clock.advance(DEGRADED_REASON_TTL_SECONDS + 1.0)
    assert scheduler.stats()["market_scheduler_slo_breached"] is False


# ---------------------------------------------------------------------------
# 2. deliberately deferred work is not starvation
# ---------------------------------------------------------------------------


def test_recovery_backoff_not_yet_due_is_deferred_not_starved():
    """The exact preserved shape: candidates backing off, queue empty."""

    clock = _Clock()
    scheduler = _scheduler(clock)
    backing_off = [
        _view(i, clock=clock, status="MARKET_RECOVERY_BACKOFF",
              market_state="MARKET_RECOVERY_BACKOFF",
              next_recovery=clock() + 600.0, age=3000.0)
        for i in range(8)]
    scheduler.update_candidates(backing_off)

    stats = scheduler.stats()
    # The raw metric still discloses the full age ...
    assert stats["market_scheduler_oldest_deadline_age_seconds"] > 0.0
    assert stats["market_scheduler_deferred_age_seconds"] > 0.0
    # ... but nothing the planner would act on is waiting.
    assert stats["market_scheduler_starved_age_seconds"] == 0.0


def test_genuinely_schedulable_overdue_work_is_reported_as_starved():
    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler.update_candidates([_view(1, clock=clock, age=3000.0)])

    stats = scheduler.stats()
    assert stats["market_scheduler_starved_age_seconds"] > 0.0
    assert stats["market_scheduler_deferred_age_seconds"] == 0.0


def test_quarantined_and_terminal_views_are_never_counted_as_starved():
    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler.update_candidates([
        _view(1, clock=clock, age=3000.0, quarantined=True),
        _view(2, clock=clock, age=3000.0, terminal_history=True),
    ])
    assert scheduler.stats()["market_scheduler_starved_age_seconds"] == 0.0


def test_backoff_that_comes_due_becomes_starved_again():
    """Deferral is temporary; a probe that is due and unserved IS starvation."""

    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler.update_candidates([
        _view(1, clock=clock, status="MARKET_RECOVERY_BACKOFF",
              market_state="MARKET_RECOVERY_BACKOFF",
              next_recovery=clock() + 60.0, age=3000.0)])
    assert scheduler.stats()["market_scheduler_starved_age_seconds"] == 0.0

    clock.advance(120.0)
    assert scheduler.stats()["market_scheduler_starved_age_seconds"] > 0.0


# ---------------------------------------------------------------------------
# 3. job accounting reconciles
# ---------------------------------------------------------------------------


def test_job_accounting_identity_holds_on_an_idle_scheduler():
    clock = _Clock()
    stats = _scheduler(clock).stats()
    assert stats["market_scheduler_jobs_submitted"] == 0
    assert stats["market_scheduler_jobs_settled"] == 0
    assert stats["market_scheduler_jobs_unaccounted"] == 0
    assert stats["market_scheduler_jobs_settled_without_completion"] == 0


def test_settled_without_completion_is_reported_not_hidden():
    """A job answered and rejected is settled, never silently missing."""

    clock = _Clock()
    scheduler = _scheduler(clock)
    scheduler._counters["market_scheduler_jobs_submitted"] = 1131
    scheduler._counters["market_scheduler_jobs_settled"] = 1131
    scheduler._counters["market_scheduler_jobs_completed"] = 838

    stats = scheduler.stats()
    # The 293 that looked lost in the preserved run are accounted for.
    assert stats["market_scheduler_jobs_settled_without_completion"] == 293
    assert stats["market_scheduler_jobs_unaccounted"] == 0
