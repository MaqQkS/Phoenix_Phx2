"""Every health surface must agree, and none may report the 2026-07-29 shape.

That run reported HEALTHY continuously while:

* the single owned stream had silently skipped 2,184 slots
  (435896378..435898561), and
* 61 of 63 watch-checkpoint writes had failed.

Both facts were in the heartbeat.  Neither reached a verdict:
``HealthInputs`` had no continuity field at all, and its only durability
fields read the CURSOR checkpoint -- a different owner, healthy for all
16,866 of its writes that same run.  ``operational_health`` modelled both
correctly and nothing in production imported it.

These tests pin the repair at the level that matters: a verdict, not a metric.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import market_scheduler as MS
from PHX2.free_tier_producer import source_continuity as SC
from PHX2.watchdog import health as H
from PHX2.watchdog import operational_health as OH

# -- preserved failed-run evidence (slots and counters only) ----------------
GAP_FROM = 435896378
GAP_TO = 435898561
GAP_SIZE = 2184
WATCH_WRITES_FAILED = 61


def _healthy_inputs(**overrides) -> H.HealthInputs:
    """A producer with every process and durable fact sound."""

    base = dict(
        producer_expected=True, producer_pid=4242, producer_alive=True,
        logical_producer_count=1, producer_uptime_seconds=3600.0,
        heartbeat_present=True, heartbeat_parse_ok=True,
        heartbeat_age_seconds=5.0,
        yellowstone_owner_count=1, max_active_streams_observed=1,
        source_continuity_state=SC.NO_GAP,
        source_coverage_proven_continuous=True,
        source_unresolved_slot_total=0,
        watch_checkpoint_durability_status="CHECKPOINT_DURABILITY_HEALTHY",
        watch_checkpoint_consecutive_failures=0,
        watch_checkpoint_structural_failed_total=0,
        live_epoch_required=True, epoch_status="EPOCH_HEALTHY",
        epoch_durable=True, epoch_age_seconds=1200.0,
    )
    base.update(overrides)
    return H.HealthInputs(**base)


# ---------------------------------------------------------------------------
# 1. the control: everything sound really is HEALTHY
# ---------------------------------------------------------------------------


def test_a_sound_producer_is_healthy():
    verdict = H.evaluate_health(_healthy_inputs())
    assert verdict.health_class == H.HEALTHY
    assert verdict.restartable is False
    assert verdict.integrity_failure is False


# ---------------------------------------------------------------------------
# 2. the preserved gap can no longer report healthy
# ---------------------------------------------------------------------------


def test_preserved_2184_slot_gap_is_not_healthy():
    verdict = H.evaluate_health(_healthy_inputs(
        source_continuity_state=SC.GAP_DETECTED,
        source_coverage_proven_continuous=False,
        source_unresolved_slot_total=GAP_SIZE))

    assert verdict.health_class != H.HEALTHY
    assert verdict.health_class == H.DEGRADED_COVERAGE_UNPROVEN
    assert H.REASON_SOURCE_GAP_UNRESOLVED in verdict.reasons
    # A restart re-arms at the live head and cannot recover the range, so it
    # must never be offered as the remedy.
    assert verdict.restartable is False
    # And incomplete coverage is not unsafe: the circuit stays closed.
    assert verdict.integrity_failure is False
    assert verdict.metrics["source_unresolved_slot_total"] == GAP_SIZE


@pytest.mark.parametrize("state", [
    s for s in SC.CONTINUITY_STATES if s != SC.NO_GAP])
def test_no_unproven_continuity_state_can_report_healthy(state):
    verdict = H.evaluate_health(_healthy_inputs(
        source_continuity_state=state,
        source_coverage_proven_continuous=(state == SC.RECOVERED)))
    if state == SC.RECOVERED:
        # RECOVERED with proven coverage is genuinely healthy again.
        assert verdict.health_class == H.HEALTHY
    else:
        assert verdict.health_class != H.HEALTHY


def test_coverage_flag_alone_blocks_healthy_even_without_a_state():
    """Fail closed on the flag when the state token is absent."""

    verdict = H.evaluate_health(_healthy_inputs(
        source_continuity_state=None,
        source_coverage_proven_continuous=False))
    assert verdict.health_class == H.DEGRADED_COVERAGE_UNPROVEN


def test_absent_continuity_evidence_is_not_invented_as_a_gap():
    """A producer that claims nothing is not accused of a discontinuity."""

    verdict = H.evaluate_health(_healthy_inputs(
        source_continuity_state=None,
        source_coverage_proven_continuous=None))
    assert verdict.health_class == H.HEALTHY


# ---------------------------------------------------------------------------
# 3. watch-checkpoint durability is now a verdict, not just a metric
# ---------------------------------------------------------------------------


def test_preserved_watch_checkpoint_failures_open_the_circuit():
    verdict = H.evaluate_health(_healthy_inputs(
        watch_checkpoint_durability_status="CHECKPOINT_DURABILITY_DEGRADED",
        watch_checkpoint_consecutive_failures=WATCH_WRITES_FAILED))

    assert verdict.health_class == H.NONRESTARTABLE_INTEGRITY_FAILURE
    assert H.REASON_WATCH_CHECKPOINT_NOT_DURABLE in verdict.reasons
    assert verdict.integrity_failure is True
    assert verdict.restartable is False


def test_structural_watch_checkpoint_failure_is_immediately_unhealthy():
    verdict = H.evaluate_health(_healthy_inputs(
        watch_checkpoint_structural_failed_total=1))
    assert verdict.health_class == H.NONRESTARTABLE_INTEGRITY_FAILURE
    assert H.REASON_WATCH_CHECKPOINT_STRUCTURAL in verdict.reasons


def test_a_single_transient_watch_checkpoint_failure_is_tolerated():
    """The prior verified generation survives one blip; do not stop the world."""

    verdict = H.evaluate_health(_healthy_inputs(
        watch_checkpoint_consecutive_failures=1))
    assert verdict.health_class == H.HEALTHY


def test_quarantined_watch_checkpoint_is_an_integrity_failure():
    verdict = H.evaluate_health(_healthy_inputs(
        watch_checkpoint_quarantined=True))
    assert verdict.health_class == H.NONRESTARTABLE_INTEGRITY_FAILURE
    assert H.REASON_WATCH_CHECKPOINT_QUARANTINED in verdict.reasons


def test_healthy_cursor_checkpoint_cannot_mask_a_failing_watch_checkpoint():
    """The exact 2026-07-29 combination: cursor fine, watch state lost."""

    verdict = H.evaluate_health(_healthy_inputs(
        cursor_durability_status=H.CURSOR_DURABILITY_HEALTHY,
        cursor_checkpoint_attempted_total=16866,
        cursor_checkpoint_succeeded_total=16866,
        cursor_checkpoint_failed_total=0,
        watch_checkpoint_durability_status="CHECKPOINT_DURABILITY_DEGRADED",
        watch_checkpoint_consecutive_failures=WATCH_WRITES_FAILED))
    assert verdict.health_class != H.HEALTHY


# ---------------------------------------------------------------------------
# 4. the two evaluators agree
# ---------------------------------------------------------------------------


def _telemetry(state=SC.NO_GAP, proven=True, unresolved=0):
    return {
        "transport_connected": True,
        "status": "CONNECTED",
        "source_continuity_state": state,
        "coverage_proven_continuous": proven,
        "grpc_gap_unresolved_slot_total": unresolved,
        "cursor_durability_status": "CHECKPOINT_DURABILITY_HEALTHY",
    }


def _summary(consecutive=0, structural=0):
    return {
        "checkpoint_write_attempted_total": 100,
        "checkpoint_write_succeeded_total": 100 - consecutive,
        "checkpoint_consecutive_failures": consecutive,
        "checkpoint_structural_failed_total": structural,
        "checkpoint_durable_candidate_count": 17,
        "watchlist_count": 17,
    }


def test_both_evaluators_agree_on_a_sound_producer():
    assert H.evaluate_health(_healthy_inputs()).health_class == H.HEALTHY
    verdict = OH.evaluate_operational_health(
        telemetry=_telemetry(), watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_READY, scheduler_starved_age_seconds=0.0,
        epoch_healthy=True)
    assert verdict.status == OH.HEALTHY


def test_both_evaluators_agree_on_the_preserved_gap():
    watchdog = H.evaluate_health(_healthy_inputs(
        source_continuity_state=SC.GAP_DETECTED,
        source_coverage_proven_continuous=False,
        source_unresolved_slot_total=GAP_SIZE))
    operational = OH.evaluate_operational_health(
        telemetry=_telemetry(SC.GAP_DETECTED, False, GAP_SIZE),
        watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_READY, scheduler_starved_age_seconds=0.0,
        epoch_healthy=True)

    assert watchdog.health_class != H.HEALTHY
    assert operational.status != OH.HEALTHY
    assert operational.status == OH.DEGRADED_RECOVERING
    # Neither opens the circuit for a coverage gap.
    assert watchdog.integrity_failure is False
    assert OH.circuit_should_open(operational)[0] is False


def test_both_evaluators_agree_on_the_preserved_checkpoint_failure():
    watchdog = H.evaluate_health(_healthy_inputs(
        watch_checkpoint_consecutive_failures=WATCH_WRITES_FAILED))
    operational = OH.evaluate_operational_health(
        telemetry=_telemetry(),
        watchlist_summary=_summary(consecutive=WATCH_WRITES_FAILED),
        scheduler_state=MS.SCHEDULER_READY, scheduler_starved_age_seconds=0.0,
        epoch_healthy=True)

    assert watchdog.health_class == H.NONRESTARTABLE_INTEGRITY_FAILURE
    assert operational.status == OH.UNHEALTHY_CHECKPOINT_DURABILITY
    # Both agree this one DOES open the circuit.
    assert watchdog.integrity_failure is True
    assert OH.circuit_should_open(operational)[0] is True


# ---------------------------------------------------------------------------
# 5. scheduler starvation cannot report healthy indefinitely
# ---------------------------------------------------------------------------


def test_ready_scheduler_is_healthy_not_degraded():
    """SCHEDULER_HEALTHY never existed; the real token is SCHEDULER_READY."""

    assert not hasattr(MS, "SCHEDULER_HEALTHY")
    verdict = OH.evaluate_operational_health(
        telemetry=_telemetry(), watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_READY, scheduler_starved_age_seconds=0.0)
    assert verdict.dimension("scheduler").verdict == OH.DIM_HEALTHY
    assert verdict.status == OH.HEALTHY


def test_transient_scheduler_degradation_is_degraded_not_unhealthy():
    verdict = OH.evaluate_operational_health(
        telemetry=_telemetry(), watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_DEGRADED,
        scheduler_starved_age_seconds=30.0)
    assert verdict.status in OH.DEGRADED_STATUSES
    assert verdict.status not in OH.UNHEALTHY_STATUSES


def test_starvation_beyond_the_bound_is_unhealthy():
    verdict = OH.evaluate_operational_health(
        telemetry=_telemetry(), watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_DEGRADED,
        scheduler_starved_age_seconds=(
            OH.SCHEDULER_STARVATION_BOUND_SECONDS + 1.0))
    assert verdict.status == OH.UNHEALTHY_SCHEDULER_STARVATION
    assert verdict.primary_cause == OH.CAUSE_SCHEDULER_STARVED


def test_deferred_backoff_age_does_not_starve_the_verdict():
    """The preserved 2,909 s was deferred work, not starvation."""

    verdict = OH.evaluate_operational_health(
        telemetry=_telemetry(), watchlist_summary=_summary(),
        scheduler_state=MS.SCHEDULER_READY,
        scheduler_starved_age_seconds=0.0)
    assert verdict.status == OH.HEALTHY


# ---------------------------------------------------------------------------
# 6. closed sets stay closed
# ---------------------------------------------------------------------------


def test_every_new_reason_is_declared_in_the_closed_set():
    for reason in (H.REASON_SOURCE_GAP_UNRESOLVED,
                   H.REASON_WATCH_CHECKPOINT_STRUCTURAL,
                   H.REASON_WATCH_CHECKPOINT_NOT_DURABLE,
                   H.REASON_WATCH_CHECKPOINT_QUARANTINED):
        assert reason in H.HEALTH_REASONS


def test_every_new_class_and_status_is_declared():
    assert H.DEGRADED_COVERAGE_UNPROVEN in H.HEALTH_CLASSES
    # Deliberately in no action set: not restartable, not integrity, not
    # "stable" for the restart-budget reset.
    assert H.DEGRADED_COVERAGE_UNPROVEN not in H.RESTARTABLE_CLASSES
    assert H.DEGRADED_COVERAGE_UNPROVEN not in H.INTEGRITY_CLASSES
    assert H.DEGRADED_COVERAGE_UNPROVEN not in H.STABLE_CLASSES
    for status in (OH.DEGRADED_RECOVERING, OH.DEGRADED_TRANSIENT_DURABILITY,
                   OH.UNHEALTHY_GAP_UNRESOLVED,
                   OH.UNHEALTHY_CHECKPOINT_DURABILITY,
                   OH.UNHEALTHY_SCHEDULER_STARVATION,
                   OH.UNHEALTHY_DELIVERY_OWNER, OH.UNHEALTHY_LEDGER,
                   OH.UNHEALTHY_MULTIPLE_CAUSES):
        assert status in OH.OPERATIONAL_STATUSES


def test_continuity_vocabulary_has_not_drifted_from_the_producer():
    """health.py restates continuity states; they must match the source."""

    restated = set(H._CONTINUITY_TERMINAL) | set(H._CONTINUITY_RECOVERING)
    assert restated == set(SC.UNPROVEN_STATES)
