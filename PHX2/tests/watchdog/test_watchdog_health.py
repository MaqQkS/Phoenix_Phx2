"""Health classification: restartable vs integrity, and every fail-closed edge.

Covers required offline tests 9-12, 15-20 and 33-34.

``evaluate_health`` is a pure function, so each case states exactly one wrong
fact and asserts exactly one classification.  Nothing is mocked because nothing
has a side effect.
"""

from __future__ import annotations

import pytest

from PHX2.watchdog.health import (
    CIRCUIT_OPEN,
    HEALTH_CLASSES,
    HEALTHY,
    INTEGRITY_CLASSES,
    NONRESTARTABLE_DUPLICATE_OWNER,
    NONRESTARTABLE_INTEGRITY_FAILURE,
    NONRESTARTABLE_LEDGER_FAILURE,
    REASON_CIRCUIT_OPEN,
    REASON_CURSOR_COUNTERS_INCOHERENT,
    REASON_CURSOR_DOCUMENT_INVALID,
    REASON_CURSOR_IDENTITY_MISMATCH,
    REASON_CURSOR_QUARANTINE,
    REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE,
    REASON_DELIVERY_AMBIGUITY,
    REASON_DUPLICATE_DELIVERY_OWNER,
    REASON_DUPLICATE_PRODUCER,
    REASON_DUPLICATE_YELLOWSTONE_OWNER,
    REASON_HEARTBEAT_ABSENT,
    REASON_HEARTBEAT_REGRESSED,
    REASON_HEARTBEAT_STALE,
    REASON_LEDGER_CONCURRENT_WRITER,
    REASON_LEDGER_TRUNCATED_LINE,
    REASON_LEDGER_UNPARSEABLE,
    REASON_OPERATOR_STOP,
    REASON_PRODUCER_EXITED,
    REASON_RECOVERY_FALSE_ADVANCEMENT,
    REASON_RECOVERY_STALLED,
    REASON_RECOVERY_TERMINAL,
    REASON_REDACTION_EXPOSURE,
    REASON_REPO_HEAD_MISMATCH,
    REASON_UNRESOLVED_WORK_CROSSED,
    RECOVERING_WITH_PROGRESS,
    RESTARTABLE_PROCESS_FAILURE,
    RESTARTABLE_STALE_HEARTBEAT,
    STARTING,
    STOPPED_BY_OPERATOR,
    STRUCTURAL_CHECKPOINT_FAILURE,
    HealthInputs,
    evaluate_health,
    restart_is_permitted,
)


def live(**overrides) -> HealthInputs:
    """A fully healthy, long-running producer, with named fields overridden."""

    base = dict(
        producer_expected=True, producer_pid=4242, producer_alive=True,
        producer_identity_ok=True, logical_producer_count=1,
        producer_uptime_seconds=3600.0,
        heartbeat_present=True, heartbeat_parse_ok=True,
        heartbeat_age_seconds=12.0,
        yellowstone_owner_count=1, max_active_streams_observed=1,
        recovery_state="IDLE", telegram_enabled=True, discord_enabled=False,
        send_capable_transport_count=1,
    )
    base.update(overrides)
    return HealthInputs(**base)


# --- 9. healthy stays healthy -------------------------------------------- #

def test_healthy_producer_is_healthy():
    verdict = evaluate_health(live())
    assert verdict.health_class == HEALTHY
    assert verdict.stable
    assert not verdict.restartable
    assert not verdict.integrity_failure


def test_every_health_class_is_declared():
    for name in HEALTH_CLASSES:
        assert isinstance(name, str) and name


# --- 10. startup grace prevents a premature restart ---------------------- #

def test_missing_heartbeat_inside_startup_grace_is_starting():
    verdict = evaluate_health(live(
        heartbeat_present=False, producer_uptime_seconds=20.0,
        startup_grace_seconds=300.0))
    assert verdict.health_class == STARTING
    assert not restart_is_permitted(verdict)


def test_stale_heartbeat_inside_startup_grace_is_starting():
    verdict = evaluate_health(live(
        heartbeat_age_seconds=5_000.0, producer_uptime_seconds=30.0,
        startup_grace_seconds=300.0))
    assert verdict.health_class == STARTING
    assert not restart_is_permitted(verdict)


def test_unparseable_first_heartbeat_inside_grace_is_starting():
    verdict = evaluate_health(live(
        heartbeat_parse_ok=False, producer_uptime_seconds=10.0,
        startup_grace_seconds=300.0))
    assert verdict.health_class == STARTING


# --- 11. stale heartbeat after grace is ONE safe restart ----------------- #

def test_absent_heartbeat_after_grace_is_restartable():
    verdict = evaluate_health(live(
        heartbeat_present=False, producer_uptime_seconds=1_000.0,
        startup_grace_seconds=300.0))
    assert verdict.health_class == RESTARTABLE_STALE_HEARTBEAT
    assert verdict.reasons == [REASON_HEARTBEAT_ABSENT]
    assert restart_is_permitted(verdict)


def test_stale_heartbeat_after_grace_is_restartable():
    verdict = evaluate_health(live(
        heartbeat_age_seconds=400.0, heartbeat_max_age_seconds=240.0))
    assert verdict.health_class == RESTARTABLE_STALE_HEARTBEAT
    assert verdict.reasons == [REASON_HEARTBEAT_STALE]


def test_heartbeat_exactly_at_threshold_is_not_stale():
    verdict = evaluate_health(live(
        heartbeat_age_seconds=240.0, heartbeat_max_age_seconds=240.0))
    assert verdict.health_class == HEALTHY


def test_quiet_producer_is_not_stale_merely_for_being_quiet():
    """No qualifying token, no ping, low activity -- still HEALTHY."""

    verdict = evaluate_health(live(heartbeat_age_seconds=30.0))
    assert verdict.health_class == HEALTHY


# --- 12. operator stop never looks like a failure ------------------------ #

def test_operator_stop_outranks_everything():
    verdict = evaluate_health(live(
        operator_stop_requested=True, producer_alive=False,
        cursor_quarantined=True, logical_producer_count=3))
    assert verdict.health_class == STOPPED_BY_OPERATOR
    assert verdict.reasons == [REASON_OPERATOR_STOP]
    assert not restart_is_permitted(verdict)


def test_open_circuit_is_not_re_diagnosed():
    verdict = evaluate_health(live(circuit_open=True, producer_alive=False))
    assert verdict.health_class == CIRCUIT_OPEN
    assert verdict.reasons == [REASON_CIRCUIT_OPEN]
    assert not restart_is_permitted(verdict)


# --- 13 (classification half). unexpected exit is restartable ----------- #

def test_dead_producer_is_restartable_process_failure():
    verdict = evaluate_health(live(producer_alive=False))
    assert verdict.health_class == RESTARTABLE_PROCESS_FAILURE
    assert verdict.reasons == [REASON_PRODUCER_EXITED]
    assert restart_is_permitted(verdict)


# --- 15 / 16. recovery with and without progress ------------------------ #

@pytest.mark.parametrize("state", [
    "REPLAY_REFUSED", "RPC_BACKFILL_PLANNED", "RPC_BACKFILL_RUNNING",
    "LIVE_STREAM_QUARANTINED", "OVERLAP_PENDING",
    "RECOVERY_PAUSED_RETRYABLE",
])
def test_active_recovery_with_progress_never_restarts(state):
    verdict = evaluate_health(live(
        recovery_state=state, recovery_progress_units=2_310,
        recovery_progress_advanced=True, recovery_no_progress_seconds=5.0,
        recovery_stall_seconds=1_800.0))
    assert verdict.health_class == RECOVERING_WITH_PROGRESS
    assert not restart_is_permitted(verdict)
    assert verdict.stable, "progressing recovery must count toward stability"


def test_recovery_without_progress_beyond_threshold_is_integrity_not_restart():
    """A restart re-enters the SAME durable episode, so it must not happen."""

    verdict = evaluate_health(live(
        recovery_state="RPC_BACKFILL_RUNNING", recovery_progress_units=2_310,
        recovery_progress_advanced=False,
        recovery_no_progress_seconds=1_900.0, recovery_stall_seconds=1_800.0))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_RECOVERY_STALLED in verdict.reasons
    assert not restart_is_permitted(verdict)


def test_recovery_stall_just_below_threshold_is_still_progressing_class():
    verdict = evaluate_health(live(
        recovery_state="RPC_BACKFILL_RUNNING",
        recovery_no_progress_seconds=1_799.0, recovery_stall_seconds=1_800.0))
    assert verdict.health_class == RECOVERING_WITH_PROGRESS


def test_settled_recovery_is_plain_healthy():
    for state in ("IDLE", "RECOVERY_PROVEN"):
        assert evaluate_health(
            live(recovery_state=state)).health_class == HEALTHY


# --- 17 / 18. cursor integrity never auto-restarts ---------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"cursor_quarantined": True}, REASON_CURSOR_QUARANTINE),
    ({"cursor_document_state": "CORRUPT"}, REASON_CURSOR_DOCUMENT_INVALID),
    ({"cursor_identity_match": False}, REASON_CURSOR_IDENTITY_MISMATCH),
    ({"cursor_last_failure_category": STRUCTURAL_CHECKPOINT_FAILURE,
      "cursor_checkpoint_failed_total": 3},
     REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE),
    ({"cursor_checkpoint_attempted_total": 10,
      "cursor_checkpoint_succeeded_total": 11},
     REASON_CURSOR_COUNTERS_INCOHERENT),
    ({"cursor_checkpoint_attempted_total": 10,
      "cursor_checkpoint_succeeded_total": 6,
      "cursor_checkpoint_failed_total": 6},
     REASON_CURSOR_COUNTERS_INCOHERENT),
])
def test_cursor_integrity_failures_are_nonrestartable(overrides, reason):
    verdict = evaluate_health(live(**overrides))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert reason in verdict.reasons
    assert not restart_is_permitted(verdict)
    assert verdict.integrity_failure


def test_durability_vocabulary_is_the_producers_own():
    """Re-declaring these as literals opened the circuit on a healthy producer.

    The real healthy status is CHECKPOINT_DURABILITY_HEALTHY (not "HEALTHY"), and
    STRUCTURAL_CHECKPOINT_FAILURE is a failure CATEGORY, never a status.
    """

    from PHX2.free_tier_producer.checkpoint_envelope import (
        CHECKPOINT_DURABILITY_DEGRADED,
        CHECKPOINT_DURABILITY_HEALTHY,
        CHECKPOINT_FAILURE_STRUCTURAL,
    )
    from PHX2.watchdog.health import (
        CURSOR_DURABILITY_DEGRADED,
        CURSOR_DURABILITY_HEALTHY,
    )

    assert CURSOR_DURABILITY_HEALTHY == CHECKPOINT_DURABILITY_HEALTHY
    assert CURSOR_DURABILITY_DEGRADED == CHECKPOINT_DURABILITY_DEGRADED
    assert STRUCTURAL_CHECKPOINT_FAILURE == CHECKPOINT_FAILURE_STRUCTURAL
    assert CURSOR_DURABILITY_HEALTHY != "HEALTHY"
    assert HealthInputs().cursor_durability_status == (
        CHECKPOINT_DURABILITY_HEALTHY)


def test_a_healthy_producer_reporting_the_real_status_is_healthy():
    verdict = evaluate_health(live(
        cursor_durability_status="CHECKPOINT_DURABILITY_HEALTHY",
        cursor_checkpoint_attempted_total=432,
        cursor_checkpoint_succeeded_total=432,
        cursor_checkpoint_failed_total=0))
    assert verdict.health_class == HEALTHY


def test_a_flat_checkpoint_counter_is_not_a_structural_failure():
    """Observed live: a quarantined recovery yields zero new events, so the
    succeeded counter legitimately plateaus on a fully healthy producer."""

    verdict = evaluate_health(live(
        cursor_durability_status="CHECKPOINT_DURABILITY_HEALTHY",
        cursor_checkpoint_attempted_total=432,
        cursor_checkpoint_succeeded_total=432,
        cursor_checkpoint_failed_total=0,
        cursor_succeeded_total_advanced=False))
    assert verdict.health_class == HEALTHY
    assert REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE not in verdict.reasons


def test_degraded_durability_alone_is_tolerated():
    """A DEGRADED status the producer recovers from is not an integrity failure."""

    verdict = evaluate_health(live(
        cursor_durability_status="CHECKPOINT_DURABILITY_DEGRADED",
        cursor_succeeded_total_advanced=False,
        cursor_checkpoint_failed_total=0))
    assert verdict.health_class == HEALTHY


def test_structural_category_needs_an_actual_failed_write():
    assert evaluate_health(live(
        cursor_last_failure_category=STRUCTURAL_CHECKPOINT_FAILURE,
        cursor_checkpoint_failed_total=0)).health_class == HEALTHY


# --- recovery integrity -------------------------------------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"recovery_terminal": True}, REASON_RECOVERY_TERMINAL),
    ({"recovery_state": "RECOVERY_TERMINAL"}, REASON_RECOVERY_TERMINAL),
    ({"recovery_state": "RECOVERY_STATE_QUARANTINED"},
     REASON_RECOVERY_TERMINAL),
    ({"recovery_false_advancement": True}, REASON_RECOVERY_FALSE_ADVANCEMENT),
    ({"unresolved_work_crossed": True}, REASON_UNRESOLVED_WORK_CROSSED),
    ({"recovery_document_state": "CORRUPT"},
     "RECOVERY_DOCUMENT_INVALID"),
])
def test_recovery_integrity_failures_are_nonrestartable(overrides, reason):
    verdict = evaluate_health(live(**overrides))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert reason in verdict.reasons
    assert not restart_is_permitted(verdict)


# --- 19. ledger ambiguity never auto-restarts --------------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"ledger_parse_ok": False}, REASON_LEDGER_UNPARSEABLE),
    ({"ledger_truncated_line": True}, REASON_LEDGER_TRUNCATED_LINE),
    ({"ledger_concurrent_writer": True}, REASON_LEDGER_CONCURRENT_WRITER),
    ({"delivery_state_ambiguous": True}, REASON_DELIVERY_AMBIGUITY),
    ({"ledger_path_matches": False}, "LEDGER_PATH_MISMATCH"),
    ({"ledger_unexpected_rewrite": True}, "LEDGER_UNEXPECTED_REWRITE"),
])
def test_ledger_failures_are_nonrestartable(overrides, reason):
    verdict = evaluate_health(live(**overrides))
    assert verdict.health_class == NONRESTARTABLE_LEDGER_FAILURE
    assert reason in verdict.reasons
    assert not restart_is_permitted(verdict)


# --- 20. unknown integrity + identity failures -------------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"redaction_exposure": True}, REASON_REDACTION_EXPOSURE),
    ({"repo_head_matches": False}, REASON_REPO_HEAD_MISMATCH),
    ({"launcher_identity_matches": False}, "LAUNCHER_IDENTITY_MISMATCH"),
    ({"unknown_integrity_failure": True},
     "UNKNOWN_STATE_INTEGRITY_FAILURE"),
    ({"producer_identity_ok": False}, "AMBIGUOUS_PRODUCER_OWNERSHIP"),
])
def test_identity_failures_are_nonrestartable(overrides, reason):
    verdict = evaluate_health(live(**overrides))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert reason in verdict.reasons


def test_regressing_heartbeat_is_integrity_not_restart():
    verdict = evaluate_health(live(heartbeat_tick_regressed=True))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_HEARTBEAT_REGRESSED in verdict.reasons


# --- 33 / 34. sole Telegram owner, sole ledger writer ------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"logical_producer_count": 2}, REASON_DUPLICATE_PRODUCER),
    ({"yellowstone_owner_count": 2}, REASON_DUPLICATE_YELLOWSTONE_OWNER),
    ({"max_active_streams_observed": 2}, REASON_DUPLICATE_YELLOWSTONE_OWNER),
    ({"send_capable_transport_count": 2}, REASON_DUPLICATE_DELIVERY_OWNER),
    ({"discord_enabled": True}, REASON_DUPLICATE_DELIVERY_OWNER),
    ({"unexpected_child_topology": True}, "UNEXPECTED_CHILD_TOPOLOGY"),
])
def test_duplicate_owner_conditions_are_nonrestartable(overrides, reason):
    verdict = evaluate_health(live(**overrides))
    assert verdict.health_class == NONRESTARTABLE_DUPLICATE_OWNER
    assert reason in verdict.reasons
    assert not restart_is_permitted(verdict)
    assert verdict.health_class in INTEGRITY_CLASSES


def test_discord_enabled_is_a_duplicate_delivery_owner_even_alone():
    """Telegram is the sole transport; Discord being enabled at all is a fault."""

    verdict = evaluate_health(live(
        telegram_enabled=False, discord_enabled=True,
        send_capable_transport_count=1))
    assert verdict.health_class == NONRESTARTABLE_DUPLICATE_OWNER
    assert REASON_DUPLICATE_DELIVERY_OWNER in verdict.reasons


def test_duplicate_owner_outranks_a_dead_process():
    verdict = evaluate_health(live(
        producer_alive=False, logical_producer_count=2))
    assert verdict.health_class == NONRESTARTABLE_DUPLICATE_OWNER
