"""Operational health matrix: a connected socket never launders a defect.

Pins the exact combination the 2026-07-29 run reported as HEALTHY.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import source_continuity as SC
from PHX2.watchdog import operational_health as OH


def _telemetry(state=SC.NO_GAP, connected=True, **kw):
    base = {
        "transport_connected": connected,
        "status": "CONNECTED" if connected else "DISCONNECTED",
        "source_continuity_state": state,
        "grpc_gap_from_slot": None,
        "grpc_gap_to_slot": None,
        "grpc_gap_size_slots": None,
        "grpc_gap_unresolved_slot_total": 0,
        "recovery_status": state,
        "cursor_durability_status": "CHECKPOINT_DURABILITY_HEALTHY",
    }
    base.update(kw)
    return base


def _watchlist(successes=10, structural=0, consecutive=0,
               durable=17, tracked=17, **kw):
    base = {
        "checkpoint_write_attempted_total": successes + structural,
        "checkpoint_write_succeeded_total": successes,
        "checkpoint_write_retryable_failed_total": 0,
        "checkpoint_structural_failed_total": structural,
        "checkpoint_consecutive_failures": consecutive,
        "checkpoint_last_success_utc": "2026-07-29T06:13:24Z",
        "checkpoint_last_failure_detail": None,
        "checkpoint_durable_candidate_count": durable,
        "checkpoint_last_verified_generation": successes,
        "watchlist_count": tracked,
    }
    base.update(kw)
    return base


def _evaluate(**kw):
    params = dict(telemetry=_telemetry(), watchlist_summary=_watchlist())
    params.update(kw)
    return OH.evaluate_operational_health(**params)


# ---------------------------------------------------------------------------


def test_all_dimensions_healthy_is_healthy():
    v = _evaluate()
    assert v.status == OH.HEALTHY
    assert v.healthy is True
    assert v.primary_cause is None


def test_connected_with_unresolved_gap_is_unhealthy():
    v = _evaluate(telemetry=_telemetry(state=SC.UNRESOLVED,
                                       grpc_gap_size_slots=2184))
    assert v.status == OH.UNHEALTHY_GAP_UNRESOLVED
    assert v.primary_cause == OH.CAUSE_SOURCE_GAP_UNRESOLVED
    assert v.dimension("transport_connection").verdict == OH.DIM_HEALTHY


def test_connected_with_recovering_gap_is_degraded():
    v = _evaluate(telemetry=_telemetry(state=SC.RECOVERING))
    assert v.status == OH.DEGRADED_RECOVERING
    assert v.primary_cause == OH.CAUSE_SOURCE_GAP_RECOVERING


@pytest.mark.parametrize("state", list(SC.UNPROVEN_STATES))
def test_no_unproven_continuity_state_can_report_healthy(state):
    v = _evaluate(telemetry=_telemetry(state=state))
    assert v.status != OH.HEALTHY


def test_missing_continuity_evidence_is_not_proof_of_continuity():
    telemetry = _telemetry()
    telemetry.pop("source_continuity_state")
    v = _evaluate(telemetry=telemetry)
    assert v.status == OH.UNHEALTHY_GAP_UNRESOLVED


def test_structural_checkpoint_failure_is_immediately_unhealthy():
    v = _evaluate(watchlist_summary=_watchlist(structural=1, consecutive=1))
    assert v.status == OH.UNHEALTHY_CHECKPOINT_DURABILITY
    assert OH.CAUSE_CHECKPOINT_STRUCTURAL in (
        [v.primary_cause] + v.secondary_causes)


def test_single_transient_checkpoint_failure_is_only_degraded():
    v = _evaluate(watchlist_summary=_watchlist(consecutive=1))
    assert v.status == OH.DEGRADED_TRANSIENT_DURABILITY
    assert v.primary_cause == OH.CAUSE_CHECKPOINT_RETRYING
    assert OH.circuit_should_open(v)[0] is False


def test_successful_retry_returns_to_healthy():
    v = _evaluate(watchlist_summary=_watchlist(consecutive=0))
    assert v.status == OH.HEALTHY


def test_consecutive_transient_failures_reach_unhealthy():
    v = _evaluate(watchlist_summary=_watchlist(
        consecutive=OH.CONSECUTIVE_CHECKPOINT_FAILURE_LIMIT))
    assert v.status == OH.UNHEALTHY_CHECKPOINT_DURABILITY
    assert OH.CAUSE_CHECKPOINT_CONSECUTIVE in (
        [v.primary_cause] + v.secondary_causes)


def test_tracked_state_never_checkpointed_is_unhealthy():
    v = _evaluate(watchlist_summary=_watchlist(
        successes=0, durable=0, tracked=17))
    assert v.status == OH.UNHEALTHY_CHECKPOINT_DURABILITY
    assert OH.CAUSE_STATE_NOT_DURABLE in (
        [v.primary_cause] + v.secondary_causes)


def test_both_defects_together_report_multiple_causes():
    """The exact 2026-07-29 combination."""

    v = _evaluate(
        telemetry=_telemetry(state=SC.UNRESOLVED, grpc_gap_size_slots=2184),
        watchlist_summary=_watchlist(
            successes=2, structural=61, consecutive=61,
            durable=11, tracked=17))
    assert v.status == OH.UNHEALTHY_MULTIPLE_CAUSES
    causes = [v.primary_cause] + v.secondary_causes
    assert OH.CAUSE_SOURCE_GAP_UNRESOLVED in causes
    assert OH.CAUSE_CHECKPOINT_STRUCTURAL in causes
    assert v.healthy is False


def test_checkpoint_lag_is_reported():
    v = _evaluate(watchlist_summary=_watchlist(durable=11, tracked=17))
    detail = v.dimension("watch_checkpoint_durability").detail
    assert detail["checkpoint_lag_candidates"] == 6
    assert detail["durable_candidate_count"] == 11
    assert detail["current_candidate_count"] == 17


def test_disconnected_transport_is_unhealthy():
    v = _evaluate(telemetry=_telemetry(connected=False))
    assert v.status == OH.UNHEALTHY_TRANSPORT_DISCONNECTED


def test_credential_or_integrity_failure_vetoes_healthy():
    v = _evaluate(
        credentials_integrity_ok=False,
        credentials_integrity_status="INVALID_CREDENTIAL")
    assert v.status == OH.UNHEALTHY_CREDENTIALS_OR_INTEGRITY
    assert v.dimension("credentials_integrity").verdict == OH.DIM_UNHEALTHY


def test_scheduler_ticket_charge_delta_vetoes_healthy():
    v = _evaluate(telemetry=_telemetry(
        unreconciled_delta=0,
        scheduler_charge_delta=1,
        scheduler_physical_requests_total=9,
        transport_physical_requests_total=10,
        reconciled_total=10,
    ))
    assert v.status == OH.UNHEALTHY_REQUEST_ACCOUNTING
    assert v.dimension("request_accounting").detail[
        "scheduler_charge_delta"] == 1


def test_circuit_opens_only_on_durability_loss():
    gap_only = _evaluate(telemetry=_telemetry(state=SC.UNRESOLVED))
    assert OH.circuit_should_open(gap_only)[0] is False

    durability = _evaluate(watchlist_summary=_watchlist(structural=1))
    should_open, reason = OH.circuit_should_open(durability)
    assert should_open is True
    assert reason == OH.CAUSE_CHECKPOINT_STRUCTURAL


def test_open_circuit_and_ownership_are_dimensions():
    v = _evaluate(circuit_closed=False, process_ownership_ok=False)
    assert v.status == OH.UNHEALTHY_MULTIPLE_CAUSES
    causes = [v.primary_cause] + v.secondary_causes
    assert OH.CAUSE_CIRCUIT_OPEN in causes
    assert OH.CAUSE_OWNERSHIP_AMBIGUOUS in causes


def test_stopped_short_circuits_every_dimension():
    v = _evaluate(stopped=True)
    assert v.status == OH.STOPPED
    assert v.primary_cause is None


def test_scheduler_degraded_does_not_alone_make_unhealthy():
    v = _evaluate(scheduler_state="SCHEDULER_DEGRADED")
    assert v.status == OH.DEGRADED_TRANSIENT_DURABILITY or v.status in \
        OH.DEGRADED_STATUSES
    assert v.status not in OH.UNHEALTHY_STATUSES


def test_record_is_serializable_and_carries_causes():
    v = _evaluate(telemetry=_telemetry(state=SC.UNRESOLVED))
    record = v.to_record()
    assert record["operational_status"] == OH.UNHEALTHY_GAP_UNRESOLVED
    assert record["primary_cause"] == OH.CAUSE_SOURCE_GAP_UNRESOLVED
    assert any(d["name"] == "source_continuity" for d in record["dimensions"])
    assert all(s in OH.OPERATIONAL_STATUSES
               for s in [record["operational_status"]])
