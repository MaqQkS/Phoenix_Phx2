"""The watchdog health model: a pure function from observations to a verdict.

Everything the watchdog decides is decided HERE, on primitives.  No file is
read, no process is inspected and no clock is consulted in this module, so every
classification -- including every integrity refusal -- is reproducible offline
from a literal :class:`HealthInputs`.

The central distinction is restartable-vs-integrity.  A restart is only ever a
remedy for a process that stopped or stopped ticking.  It is NEVER a remedy for
a durable-state problem: restarting a producer whose cursor is quarantined, or
whose recovery episode is not advancing, re-enters exactly the same state and
produces the restart loop Stage 10 forbids.  Those verdicts open the circuit and
wait for an operator instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------- #
# health classes
# --------------------------------------------------------------------------- #

HEALTHY = "HEALTHY"
STARTING = "STARTING"
RECOVERING_WITH_PROGRESS = "RECOVERING_WITH_PROGRESS"
#: The producer is running correctly but can no longer PROVE it covered every
#: slot it claims.  Deliberately neither restartable nor an integrity failure:
#: a restart re-arms at the live head and cannot recover a skipped range, and
#: incomplete coverage is not unsafe -- the send path already refuses to
#: authorize on it.  What this class exists to prevent is the one thing the
#: 2026-07-29 run did: report HEALTHY over a proven discontinuity.
DEGRADED_COVERAGE_UNPROVEN = "DEGRADED_COVERAGE_UNPROVEN"
RESTARTABLE_PROCESS_FAILURE = "RESTARTABLE_PROCESS_FAILURE"
RESTARTABLE_STALE_HEARTBEAT = "RESTARTABLE_STALE_HEARTBEAT"
NONRESTARTABLE_INTEGRITY_FAILURE = "NONRESTARTABLE_INTEGRITY_FAILURE"
NONRESTARTABLE_LEDGER_FAILURE = "NONRESTARTABLE_LEDGER_FAILURE"
NONRESTARTABLE_DUPLICATE_OWNER = "NONRESTARTABLE_DUPLICATE_OWNER"
CIRCUIT_OPEN = "CIRCUIT_OPEN"
STOPPED_BY_OPERATOR = "STOPPED_BY_OPERATOR"

HEALTH_CLASSES = (
    HEALTHY,
    STARTING,
    RECOVERING_WITH_PROGRESS,
    DEGRADED_COVERAGE_UNPROVEN,
    RESTARTABLE_PROCESS_FAILURE,
    RESTARTABLE_STALE_HEARTBEAT,
    NONRESTARTABLE_INTEGRITY_FAILURE,
    NONRESTARTABLE_LEDGER_FAILURE,
    NONRESTARTABLE_DUPLICATE_OWNER,
    CIRCUIT_OPEN,
    STOPPED_BY_OPERATOR,
)

#: Classes that permit exactly one bounded, backed-off restart attempt.
RESTARTABLE_CLASSES = frozenset(
    {RESTARTABLE_PROCESS_FAILURE, RESTARTABLE_STALE_HEARTBEAT})

#: Classes that must never be auto-restarted and must open the circuit.
INTEGRITY_CLASSES = frozenset({
    NONRESTARTABLE_INTEGRITY_FAILURE,
    NONRESTARTABLE_LEDGER_FAILURE,
    NONRESTARTABLE_DUPLICATE_OWNER,
})

#: Classes that count as "the producer is doing its job" for the stable-run
#: interval that resets the restart budget.
STABLE_CLASSES = frozenset({HEALTHY, RECOVERING_WITH_PROGRESS})

# --------------------------------------------------------------------------- #
# closed-set reasons
# --------------------------------------------------------------------------- #

REASON_OPERATOR_STOP = "OPERATOR_STOP_REQUESTED"
REASON_CIRCUIT_OPEN = "CIRCUIT_OPEN"

REASON_REDACTION_EXPOSURE = "REDACTION_EXPOSURE"
REASON_REPO_HEAD_MISMATCH = "REPOSITORY_HEAD_MISMATCH"
REASON_LAUNCHER_IDENTITY_MISMATCH = "LAUNCHER_IDENTITY_MISMATCH"
REASON_AMBIGUOUS_PRODUCER_OWNERSHIP = "AMBIGUOUS_PRODUCER_OWNERSHIP"
REASON_CURSOR_QUARANTINE = "CURSOR_QUARANTINED"
REASON_CURSOR_DOCUMENT_INVALID = "CURSOR_DOCUMENT_INVALID"
REASON_CURSOR_IDENTITY_MISMATCH = "CURSOR_SUBSCRIPTION_IDENTITY_MISMATCH"
REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE = (
    "CURSOR_STRUCTURAL_CHECKPOINT_FAILURE")
REASON_CURSOR_COUNTERS_INCOHERENT = "CURSOR_CHECKPOINT_COUNTERS_INCOHERENT"
REASON_RECOVERY_DOCUMENT_INVALID = "RECOVERY_DOCUMENT_INVALID"
REASON_RECOVERY_TERMINAL = "RECOVERY_TERMINAL"
REASON_RECOVERY_FALSE_ADVANCEMENT = "RECOVERY_FALSE_ADVANCEMENT"
REASON_RECOVERY_STALLED = "RECOVERY_STALLED_NO_PROGRESS"
REASON_SOURCE_GAP_UNRESOLVED = "SOURCE_COVERAGE_GAP_UNRESOLVED"
REASON_WATCH_CHECKPOINT_STRUCTURAL = "WATCH_CHECKPOINT_STRUCTURAL_FAILURE"
REASON_WATCH_CHECKPOINT_NOT_DURABLE = "WATCH_CHECKPOINT_NOT_DURABLE"
REASON_WATCH_CHECKPOINT_QUARANTINED = "WATCH_CHECKPOINT_QUARANTINED"
REASON_EPOCH_DOCUMENT_INVALID = "EPOCH_DOCUMENT_INVALID"
REASON_EPOCH_INTEGRITY_FAILURE = "EPOCH_INTEGRITY_FAILURE"
REASON_EPOCH_NOT_DURABLE = "EPOCH_NOT_DURABLE"
REASON_EPOCH_STARTING = "EPOCH_STARTING"
REASON_EPOCH_NOT_HEALTHY = "EPOCH_NOT_HEALTHY"
REASON_UNRESOLVED_WORK_CROSSED = "UNRESOLVED_WORK_CROSSED"
REASON_UNKNOWN_INTEGRITY = "UNKNOWN_STATE_INTEGRITY_FAILURE"

REASON_LEDGER_UNPARSEABLE = "LEDGER_UNPARSEABLE"
REASON_LEDGER_TRUNCATED_LINE = "LEDGER_TRUNCATED_LINE"
REASON_LEDGER_UNEXPECTED_REWRITE = "LEDGER_UNEXPECTED_REWRITE"
REASON_LEDGER_CONCURRENT_WRITER = "LEDGER_CONCURRENT_WRITER"
REASON_LEDGER_PATH_MISMATCH = "LEDGER_PATH_MISMATCH"
REASON_DELIVERY_AMBIGUITY = "DELIVERY_STATE_AMBIGUITY"

REASON_DUPLICATE_PRODUCER = "DUPLICATE_PRODUCER"
REASON_DUPLICATE_YELLOWSTONE_OWNER = "DUPLICATE_YELLOWSTONE_OWNER"
REASON_DUPLICATE_DELIVERY_OWNER = "DUPLICATE_TELEGRAM_DELIVERY_OWNER"
REASON_UNEXPECTED_CHILD_TOPOLOGY = "UNEXPECTED_CHILD_TOPOLOGY"

REASON_PRODUCER_ABSENT = "PRODUCER_PROCESS_ABSENT"
REASON_PRODUCER_EXITED = "PRODUCER_PROCESS_EXITED"
REASON_HEARTBEAT_ABSENT = "HEARTBEAT_ABSENT_AFTER_GRACE"
REASON_HEARTBEAT_UNPARSEABLE = "HEARTBEAT_UNPARSEABLE"
REASON_HEARTBEAT_STALE = "HEARTBEAT_STALE"
REASON_HEARTBEAT_REGRESSED = "HEARTBEAT_SEQUENCE_REGRESSED"

REASON_STARTING_GRACE = "WITHIN_STARTUP_GRACE"
REASON_RECOVERY_PROGRESSING = "RECOVERY_PROGRESSING"
REASON_ALL_CHECKS_PASSED = "ALL_CHECKS_PASSED"

HEALTH_REASONS = (
    REASON_OPERATOR_STOP, REASON_CIRCUIT_OPEN,
    REASON_REDACTION_EXPOSURE, REASON_REPO_HEAD_MISMATCH,
    REASON_LAUNCHER_IDENTITY_MISMATCH, REASON_AMBIGUOUS_PRODUCER_OWNERSHIP,
    REASON_CURSOR_QUARANTINE, REASON_CURSOR_DOCUMENT_INVALID,
    REASON_CURSOR_IDENTITY_MISMATCH,
    REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE,
    REASON_CURSOR_COUNTERS_INCOHERENT,
    REASON_RECOVERY_DOCUMENT_INVALID, REASON_RECOVERY_TERMINAL,
    REASON_RECOVERY_FALSE_ADVANCEMENT, REASON_RECOVERY_STALLED,
    REASON_SOURCE_GAP_UNRESOLVED, REASON_WATCH_CHECKPOINT_STRUCTURAL,
    REASON_WATCH_CHECKPOINT_NOT_DURABLE, REASON_WATCH_CHECKPOINT_QUARANTINED,
    REASON_EPOCH_DOCUMENT_INVALID, REASON_EPOCH_INTEGRITY_FAILURE,
    REASON_EPOCH_NOT_DURABLE, REASON_EPOCH_STARTING,
    REASON_EPOCH_NOT_HEALTHY,    REASON_UNRESOLVED_WORK_CROSSED, REASON_UNKNOWN_INTEGRITY,
    REASON_LEDGER_UNPARSEABLE, REASON_LEDGER_TRUNCATED_LINE,
    REASON_LEDGER_UNEXPECTED_REWRITE, REASON_LEDGER_CONCURRENT_WRITER,
    REASON_LEDGER_PATH_MISMATCH, REASON_DELIVERY_AMBIGUITY,
    REASON_DUPLICATE_PRODUCER, REASON_DUPLICATE_YELLOWSTONE_OWNER,
    REASON_DUPLICATE_DELIVERY_OWNER, REASON_UNEXPECTED_CHILD_TOPOLOGY,
    REASON_PRODUCER_ABSENT, REASON_PRODUCER_EXITED,
    REASON_HEARTBEAT_ABSENT, REASON_HEARTBEAT_UNPARSEABLE,
    REASON_HEARTBEAT_STALE, REASON_HEARTBEAT_REGRESSED,
    REASON_STARTING_GRACE, REASON_RECOVERY_PROGRESSING,
    REASON_ALL_CHECKS_PASSED,
)

#: Cursor durability vocabulary, IMPORTED from the producer rather than restated.
#:
#: Re-declaring these as literals was a live defect: the real healthy status is
#: ``CHECKPOINT_DURABILITY_HEALTHY``, not ``"HEALTHY"``, so a
#: "status != healthy" test was true on every healthy producer.  And
#: ``STRUCTURAL_CHECKPOINT_FAILURE`` is a failure CATEGORY
#: (``cursor_last_failure_category``), never a durability status, so comparing a
#: status against it could never match.  Importing removes both drift classes.
from PHX2.free_tier_producer.checkpoint_envelope import (  # noqa: E402
    CHECKPOINT_DURABILITY_DEGRADED,
    CHECKPOINT_DURABILITY_HEALTHY,
    CHECKPOINT_FAILURE_STRUCTURAL,
)

CURSOR_DURABILITY_HEALTHY = CHECKPOINT_DURABILITY_HEALTHY
CURSOR_DURABILITY_DEGRADED = CHECKPOINT_DURABILITY_DEGRADED
STRUCTURAL_CHECKPOINT_FAILURE = CHECKPOINT_FAILURE_STRUCTURAL

#: Recovery states that mean an episode is open and being worked.
RECOVERY_ACTIVE_STATES = frozenset({
    "REPLAY_REFUSED",
    "RPC_BACKFILL_PLANNED",
    "RPC_BACKFILL_RUNNING",
    "LIVE_STREAM_QUARANTINED",
    "OVERLAP_PENDING",
    "RECOVERY_PAUSED_RETRYABLE",
})

#: Recovery states that are settled and need no special allowance.
RECOVERY_SETTLED_STATES = frozenset({"IDLE", "RECOVERY_PROVEN"})

#: Recovery states that are terminal integrity failures.
RECOVERY_TERMINAL_STATES = frozenset(
    {"RECOVERY_TERMINAL", "RECOVERY_STATE_QUARANTINED"})

CHECKPOINT_DOCUMENT_OK = frozenset({"VALID_CURRENT", "VALID_LEGACY", "MISSING"})


@dataclass(frozen=True)
class HealthInputs:
    """One complete observation of the supervised system.

    Every field is a primitive so a test can state a failure exactly.  ``None``
    consistently means "not observed", which is never treated as healthy for an
    integrity signal.
    """

    # -- operator / breaker ------------------------------------------------- #
    operator_stop_requested: bool = False
    circuit_open: bool = False

    # -- process health ----------------------------------------------------- #
    producer_expected: bool = True
    producer_pid: Optional[int] = None
    producer_alive: bool = False
    producer_identity_ok: bool = True
    producer_identity_observed: bool = True
    logical_producer_count: int = 0
    unexpected_child_topology: bool = False
    producer_uptime_seconds: Optional[float] = None

    # -- heartbeat health --------------------------------------------------- #
    heartbeat_present: bool = False
    heartbeat_parse_ok: bool = True
    heartbeat_age_seconds: Optional[float] = None
    heartbeat_tick_regressed: bool = False

    # -- source health ------------------------------------------------------ #
    yellowstone_owner_count: Optional[int] = None
    max_active_streams_observed: Optional[int] = None

    # -- source CONTINUITY -------------------------------------------------- #
    #
    # A connected socket is not continuous ingestion.  Before these fields
    # existed the watchdog had no input that could express "the stream is up
    # and 2,184 slots are missing", so the 2026-07-29 run's verdict was
    # HEALTHY throughout a proven discontinuity.  ``None`` means not observed
    # and is never treated as proof of continuity for a producer that is
    # otherwise reporting.
    source_continuity_state: Optional[str] = None
    source_coverage_proven_continuous: Optional[bool] = None
    source_unresolved_slot_total: Optional[int] = None

    # -- WATCH-checkpoint durability ---------------------------------------- #
    #
    # Distinct from the cursor checkpoint above: a different owner, a
    # different file, and healthy in the same run where this one failed 61 of
    # 63 writes.  Reading only the cursor keys is why that was invisible.
    watch_checkpoint_durability_status: Optional[str] = None
    watch_checkpoint_consecutive_failures: Optional[int] = None
    watch_checkpoint_structural_failed_total: Optional[int] = None
    watch_checkpoint_quarantined: bool = False

    # -- cursor health ------------------------------------------------------ #
    cursor_document_state: str = "VALID_CURRENT"
    cursor_quarantined: bool = False
    cursor_identity_match: bool = True
    cursor_durability_status: str = CURSOR_DURABILITY_HEALTHY
    cursor_last_failure_category: Optional[str] = None
    cursor_checkpoint_attempted_total: Optional[int] = None
    cursor_checkpoint_succeeded_total: Optional[int] = None
    cursor_checkpoint_failed_total: Optional[int] = None
    cursor_succeeded_total_advanced: Optional[bool] = None

    # -- recovery health ---------------------------------------------------- #
    recovery_document_state: str = "VALID_CURRENT"
    recovery_state: str = "IDLE"
    recovery_terminal: bool = False
    recovery_progress_units: Optional[int] = None
    recovery_progress_advanced: Optional[bool] = None
    recovery_no_progress_seconds: Optional[float] = None
    recovery_false_advancement: bool = False
    unresolved_work_crossed: bool = False

    # -- live-only epoch health -------------------------------------------- #
    live_epoch_required: bool = False
    epoch_document_state: str = "VALID_CURRENT"
    epoch_status: str = "EPOCH_HEALTHY"
    epoch_durable: bool = True
    epoch_age_seconds: Optional[float] = None

    # -- delivery health ---------------------------------------------------- #
    telegram_enabled: bool = True
    discord_enabled: bool = False
    send_capable_transport_count: int = 1
    delivery_state_ambiguous: bool = False

    # -- ledger health ------------------------------------------------------ #
    ledger_parse_ok: bool = True
    ledger_truncated_line: bool = False
    ledger_unexpected_rewrite: bool = False
    ledger_concurrent_writer: bool = False
    ledger_path_matches: bool = True

    # -- identity / redaction ---------------------------------------------- #
    repo_head_matches: bool = True
    launcher_identity_matches: bool = True
    redaction_exposure: bool = False
    unknown_integrity_failure: bool = False

    # -- thresholds --------------------------------------------------------- #
    #: Consecutive watch-checkpoint write failures that mean tracked state is
    #: genuinely no longer durable.  One transient failure is tolerated: the
    #: prior verified generation always survives.
    watch_checkpoint_failure_limit: int = 5
    startup_grace_seconds: float = 300.0
    heartbeat_max_age_seconds: float = 240.0
    recovery_stall_seconds: float = 1800.0


@dataclass
class HealthVerdict:
    health_class: str
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    # Internal control action carried by the SAME canonical verdict.  It is
    # deliberately not a separately evaluated health opinion.
    control_class: Optional[str] = None

    @property
    def control_health_class(self) -> str:
        return self.control_class or self.health_class

    @property
    def restartable(self) -> bool:
        return self.control_health_class in RESTARTABLE_CLASSES

    @property
    def integrity_failure(self) -> bool:
        return self.control_health_class in INTEGRITY_CLASSES

    @property
    def stable(self) -> bool:
        if self.control_class is not None:
            # A canonical verdict earns stability only when every required
            # operational dimension is healthy now. Recovery/degradation no
            # longer resets the durable restart budget.
            return self.health_class == HEALTHY \
                and self.control_health_class in STABLE_CLASSES
        return self.health_class in STABLE_CLASSES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_class": self.health_class,
            "control_class": self.control_health_class,
            "reasons": list(self.reasons),
            "restartable": self.restartable,
            "integrity_failure": self.integrity_failure,
            "metrics": dict(self.metrics),
        }


def _duplicate_owner_reasons(inputs: HealthInputs) -> List[str]:
    reasons: List[str] = []
    if int(inputs.logical_producer_count or 0) > 1:
        reasons.append(REASON_DUPLICATE_PRODUCER)
    owners = inputs.yellowstone_owner_count
    if owners is not None and int(owners) > 1:
        reasons.append(REASON_DUPLICATE_YELLOWSTONE_OWNER)
    observed_max = inputs.max_active_streams_observed
    if observed_max is not None and int(observed_max) > 1:
        # The producer's own single-stream invariant reports the high-water mark
        # of concurrently active streams; above one it has already overlapped.
        reasons.append(REASON_DUPLICATE_YELLOWSTONE_OWNER)
    if int(inputs.send_capable_transport_count or 0) > 1:
        reasons.append(REASON_DUPLICATE_DELIVERY_OWNER)
    if inputs.discord_enabled:
        reasons.append(REASON_DUPLICATE_DELIVERY_OWNER)
    if inputs.unexpected_child_topology:
        reasons.append(REASON_UNEXPECTED_CHILD_TOPOLOGY)
    # De-duplicate while preserving order.
    seen: set = set()
    ordered: List[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return ordered


def _cursor_integrity_reasons(inputs: HealthInputs) -> List[str]:
    reasons: List[str] = []
    if inputs.cursor_quarantined:
        reasons.append(REASON_CURSOR_QUARANTINE)
    if str(inputs.cursor_document_state) not in CHECKPOINT_DOCUMENT_OK:
        reasons.append(REASON_CURSOR_DOCUMENT_INVALID)
    if not inputs.cursor_identity_match:
        reasons.append(REASON_CURSOR_IDENTITY_MISMATCH)
    # A PERSISTENT structural write failure, evidenced two ways at once: the
    # producer categorised its last failure as structural AND at least one write
    # actually failed. Neither half alone is enough -- a DEGRADED status on its own
    # is a tolerated, non-fatal condition the producer recovers from (Step-6
    # recorded exactly that on the watch checkpoint with zero data loss).
    if str(inputs.cursor_last_failure_category or "") == (
            STRUCTURAL_CHECKPOINT_FAILURE) \
            and int(inputs.cursor_checkpoint_failed_total or 0) > 0:
        reasons.append(REASON_CURSOR_STRUCTURAL_CHECKPOINT_FAILURE)
    attempted = inputs.cursor_checkpoint_attempted_total
    succeeded = inputs.cursor_checkpoint_succeeded_total
    failed = inputs.cursor_checkpoint_failed_total
    if attempted is not None and succeeded is not None:
        if int(succeeded) > int(attempted):
            reasons.append(REASON_CURSOR_COUNTERS_INCOHERENT)
        elif failed is not None and (
                int(succeeded) + int(failed)) > int(attempted):
            reasons.append(REASON_CURSOR_COUNTERS_INCOHERENT)
    # NOTE: a PLATEAU in ``cursor_checkpoint_succeeded_total`` is NOT evidence of
    # anything wrong and must never be treated as one. The cursor batches
    # persistence (32 events / 0.5 s), and while a recovery episode quarantines
    # the live stream there are no new events at all -- observed live with
    # ``events_received_total=0`` and a flat succeeded counter of 432 on a fully
    # healthy producer. An earlier version of this function inferred a structural
    # failure from that plateau and opened the circuit on a healthy run.
    return reasons


#: Continuity states in which coverage is NOT proven, imported in spirit from
#: the producer's closed set.  Restated here would drift; the tuple below is
#: asserted equal to ``source_continuity.UNPROVEN_STATES`` by the health tests.
_CONTINUITY_TERMINAL = ("UNRESOLVED", "RECOVERY_UNAVAILABLE", "RECOVERY_FAILED")
_CONTINUITY_RECOVERING = (
    "GAP_DETECTED", "RECOVERY_REQUESTED", "RECOVERING", "PARTIALLY_RECOVERED")


def _watch_checkpoint_integrity_reasons(inputs: HealthInputs) -> List[str]:
    """Watch-checkpoint durability, a DIFFERENT owner from the cursor.

    In the 2026-07-29 run the cursor checkpoint was healthy for all 16,866 of
    its writes while the watch checkpoint failed 61 of 63.  The watchdog read
    only the cursor keys, so tracked candidate state silently stopped being
    durable with no verdict able to say so.  Losing durability IS an integrity
    failure: a restart would resurrect whatever stale generation survived.
    """

    reasons: List[str] = []
    if inputs.watch_checkpoint_quarantined:
        reasons.append(REASON_WATCH_CHECKPOINT_QUARANTINED)
    structural = inputs.watch_checkpoint_structural_failed_total
    if structural is not None and int(structural) > 0:
        reasons.append(REASON_WATCH_CHECKPOINT_STRUCTURAL)
    consecutive = inputs.watch_checkpoint_consecutive_failures
    if consecutive is not None and int(consecutive) >= int(
            inputs.watch_checkpoint_failure_limit):
        reasons.append(REASON_WATCH_CHECKPOINT_NOT_DURABLE)
    return reasons


def _continuity_reason(inputs: HealthInputs) -> Optional[str]:
    """The gap reason, or None when coverage is proven continuous.

    Absent evidence is NOT a gap: a producer that reports no continuity state
    at all is handled by the ordinary heartbeat/process checks rather than
    being accused of a discontinuity it never claimed.
    """

    state = inputs.source_continuity_state
    if state is None:
        if inputs.source_coverage_proven_continuous is False:
            return REASON_SOURCE_GAP_UNRESOLVED
        return None
    text = str(state)
    if text in _CONTINUITY_TERMINAL or text in _CONTINUITY_RECOVERING:
        return REASON_SOURCE_GAP_UNRESOLVED
    if inputs.source_coverage_proven_continuous is False:
        return REASON_SOURCE_GAP_UNRESOLVED
    return None


def _recovery_integrity_reasons(inputs: HealthInputs) -> List[str]:
    if (str(inputs.recovery_document_state) == "RETIRED_AUDIT_ONLY"
            and str(inputs.recovery_state)
            == "HISTORICAL_BLOCK_REPLAY_RETIRED_FROM_PRODUCTION"):
        return []
    reasons: List[str] = []
    if str(inputs.recovery_document_state) not in CHECKPOINT_DOCUMENT_OK:
        reasons.append(REASON_RECOVERY_DOCUMENT_INVALID)
    state = str(inputs.recovery_state or "")
    if inputs.recovery_terminal or state in RECOVERY_TERMINAL_STATES:
        reasons.append(REASON_RECOVERY_TERMINAL)
    if inputs.recovery_false_advancement:
        reasons.append(REASON_RECOVERY_FALSE_ADVANCEMENT)
    if inputs.unresolved_work_crossed:
        reasons.append(REASON_UNRESOLVED_WORK_CROSSED)
    if state in RECOVERY_ACTIVE_STATES:
        stalled_for = inputs.recovery_no_progress_seconds
        if stalled_for is not None \
                and float(stalled_for) >= float(inputs.recovery_stall_seconds):
            # Deliberately an INTEGRITY verdict, not a restartable one. A restart
            # re-enters the same durable episode, so an auto-restart here would
            # be a loop; the operator decides instead.
            reasons.append(REASON_RECOVERY_STALLED)
    return reasons


def _epoch_integrity_reasons(inputs: HealthInputs) -> List[str]:
    if not inputs.live_epoch_required:
        return []
    reasons: List[str] = []
    if str(inputs.epoch_document_state) != "VALID_CURRENT":
        reasons.append(REASON_EPOCH_DOCUMENT_INVALID)
    if str(inputs.epoch_status) == "EPOCH_INTEGRITY_FAILURE":
        reasons.append(REASON_EPOCH_INTEGRITY_FAILURE)
    if not inputs.epoch_durable:
        # A freshly rolled-over epoch is EPOCH_STARTING and legitimately not
        # yet durable while the producer arms it; inside the same startup
        # grace the process gets, that is a transition, not an integrity
        # failure (the STARTING verdict downstream still reports it).  A
        # STARTING epoch that stays non-durable past the grace window is a
        # genuine stuck state and still opens the circuit.
        age = inputs.epoch_age_seconds
        starting_within_grace = bool(
            str(inputs.epoch_status) == "EPOCH_STARTING"
            and age is not None
            and float(age) < float(inputs.startup_grace_seconds))
        if not starting_within_grace:
            reasons.append(REASON_EPOCH_NOT_DURABLE)
    return reasons


def _ledger_reasons(inputs: HealthInputs) -> List[str]:
    reasons: List[str] = []
    if not inputs.ledger_parse_ok:
        reasons.append(REASON_LEDGER_UNPARSEABLE)
    if inputs.ledger_truncated_line:
        reasons.append(REASON_LEDGER_TRUNCATED_LINE)
    if inputs.ledger_unexpected_rewrite:
        reasons.append(REASON_LEDGER_UNEXPECTED_REWRITE)
    if inputs.ledger_concurrent_writer:
        reasons.append(REASON_LEDGER_CONCURRENT_WRITER)
    if not inputs.ledger_path_matches:
        reasons.append(REASON_LEDGER_PATH_MISMATCH)
    if inputs.delivery_state_ambiguous:
        reasons.append(REASON_DELIVERY_AMBIGUITY)
    return reasons


def _identity_reasons(inputs: HealthInputs) -> List[str]:
    reasons: List[str] = []
    if inputs.redaction_exposure:
        reasons.append(REASON_REDACTION_EXPOSURE)
    if not inputs.repo_head_matches:
        reasons.append(REASON_REPO_HEAD_MISMATCH)
    if not inputs.launcher_identity_matches:
        reasons.append(REASON_LAUNCHER_IDENTITY_MISMATCH)
    if inputs.unknown_integrity_failure:
        reasons.append(REASON_UNKNOWN_INTEGRITY)
    if inputs.producer_alive and not inputs.producer_identity_ok:
        # A live process at the recorded PID that is NOT the canonical producer
        # is ambiguous ownership: the watchdog must never kill it and must never
        # start a second producer beside it.
        reasons.append(REASON_AMBIGUOUS_PRODUCER_OWNERSHIP)
    if inputs.producer_alive and not inputs.producer_identity_observed:
        reasons.append(REASON_AMBIGUOUS_PRODUCER_OWNERSHIP)
    return reasons


def evaluate_health(inputs: HealthInputs) -> HealthVerdict:
    """Classify one observation.  Fail-closed order, most severe first."""

    metrics: Dict[str, Any] = {
        "producer_pid": inputs.producer_pid,
        "producer_alive": bool(inputs.producer_alive),
        "logical_producer_count": int(inputs.logical_producer_count or 0),
        "producer_uptime_seconds": inputs.producer_uptime_seconds,
        "heartbeat_present": bool(inputs.heartbeat_present),
        "heartbeat_age_seconds": inputs.heartbeat_age_seconds,
        "yellowstone_owner_count": inputs.yellowstone_owner_count,
        "cursor_document_state": str(inputs.cursor_document_state),
        "cursor_durability_status": str(inputs.cursor_durability_status),
        "source_continuity_state": inputs.source_continuity_state,
        "source_coverage_proven_continuous": (
            inputs.source_coverage_proven_continuous),
        "source_unresolved_slot_total": inputs.source_unresolved_slot_total,
        "watch_checkpoint_durability_status": (
            inputs.watch_checkpoint_durability_status),
        "watch_checkpoint_consecutive_failures": (
            inputs.watch_checkpoint_consecutive_failures),
        "watch_checkpoint_structural_failed_total": (
            inputs.watch_checkpoint_structural_failed_total),
        "recovery_state": str(inputs.recovery_state),
        "recovery_progress_units": inputs.recovery_progress_units,
        "recovery_no_progress_seconds": inputs.recovery_no_progress_seconds,
        "live_epoch_required": bool(inputs.live_epoch_required),
        "epoch_document_state": str(inputs.epoch_document_state),
        "epoch_status": str(inputs.epoch_status),
        "epoch_durable": bool(inputs.epoch_durable),
        "epoch_age_seconds": inputs.epoch_age_seconds,
        "telegram_enabled": bool(inputs.telegram_enabled),
        "discord_enabled": bool(inputs.discord_enabled),
        "send_capable_transport_count": int(
            inputs.send_capable_transport_count or 0),
    }

    # 1. an explicit operator stop outranks everything: nothing is a failure.
    if inputs.operator_stop_requested:
        return HealthVerdict(STOPPED_BY_OPERATOR, [REASON_OPERATOR_STOP], metrics)

    # 2. an open circuit is already the terminal state; do not re-diagnose.
    if inputs.circuit_open:
        return HealthVerdict(CIRCUIT_OPEN, [REASON_CIRCUIT_OPEN], metrics)

    # 3. duplicate ownership -- the one condition that could produce a second
    #    Yellowstone owner, a second delivery owner or a second ledger writer.
    duplicates = _duplicate_owner_reasons(inputs)
    if duplicates:
        return HealthVerdict(NONRESTARTABLE_DUPLICATE_OWNER, duplicates, metrics)

    # 4. ledger / delivery ambiguity.
    ledger = _ledger_reasons(inputs)
    if ledger:
        return HealthVerdict(NONRESTARTABLE_LEDGER_FAILURE, ledger, metrics)

    # 5. every other integrity class.
    integrity = (_identity_reasons(inputs)
                 + _cursor_integrity_reasons(inputs)
                 + _watch_checkpoint_integrity_reasons(inputs)
                 + _recovery_integrity_reasons(inputs)
                 + _epoch_integrity_reasons(inputs))
    if integrity:
        return HealthVerdict(
            NONRESTARTABLE_INTEGRITY_FAILURE, integrity, metrics)

    # 6. from here the durable state is sound; only the PROCESS can be wrong.
    if not inputs.producer_expected:
        return HealthVerdict(
            STOPPED_BY_OPERATOR, [REASON_OPERATOR_STOP], metrics)
    if not inputs.producer_alive:
        reason = (REASON_PRODUCER_EXITED if inputs.producer_pid is not None
                  else REASON_PRODUCER_ABSENT)
        return HealthVerdict(RESTARTABLE_PROCESS_FAILURE, [reason], metrics)

    uptime = inputs.producer_uptime_seconds
    within_grace = (uptime is not None
                    and float(uptime) < float(inputs.startup_grace_seconds))

    # 7. heartbeat health, with the startup grace applied first.
    if not inputs.heartbeat_present:
        if within_grace:
            return HealthVerdict(STARTING, [REASON_STARTING_GRACE], metrics)
        return HealthVerdict(
            RESTARTABLE_STALE_HEARTBEAT, [REASON_HEARTBEAT_ABSENT], metrics)
    if not inputs.heartbeat_parse_ok:
        if within_grace:
            # A partially written first heartbeat is a normal startup race.
            return HealthVerdict(STARTING, [REASON_STARTING_GRACE], metrics)
        return HealthVerdict(
            RESTARTABLE_STALE_HEARTBEAT, [REASON_HEARTBEAT_UNPARSEABLE],
            metrics)
    if inputs.heartbeat_tick_regressed:
        # A regressing tick/timestamp means the artifact is no longer describing
        # the process the watchdog believes it is supervising.
        return HealthVerdict(
            NONRESTARTABLE_INTEGRITY_FAILURE, [REASON_HEARTBEAT_REGRESSED],
            metrics)
    age = inputs.heartbeat_age_seconds
    if age is not None and float(age) > float(inputs.heartbeat_max_age_seconds):
        if within_grace:
            return HealthVerdict(STARTING, [REASON_STARTING_GRACE], metrics)
        return HealthVerdict(
            RESTARTABLE_STALE_HEARTBEAT, [REASON_HEARTBEAT_STALE], metrics)

    if inputs.live_epoch_required and inputs.epoch_status != "EPOCH_HEALTHY":
        epoch_age = inputs.epoch_age_seconds
        epoch_within_grace = (
            inputs.epoch_status == "EPOCH_STARTING"
            and epoch_age is not None
            and float(epoch_age) < float(inputs.startup_grace_seconds))
        if epoch_within_grace:
            return HealthVerdict(STARTING, [REASON_EPOCH_STARTING], metrics)
        return HealthVerdict(
            RESTARTABLE_PROCESS_FAILURE, [REASON_EPOCH_NOT_HEALTHY], metrics)

    # 8. a live recovery episode that is measurably advancing is healthy work,
    #    not a failure -- and must never be restarted for being slow.
    if str(inputs.recovery_state or "") in RECOVERY_ACTIVE_STATES:
        return HealthVerdict(
            RECOVERING_WITH_PROGRESS, [REASON_RECOVERY_PROGRESSING], metrics)

    # 9. the process is sound and the durable state is sound, but the stream
    #    may not be able to PROVE it covered every slot it claims. Checked
    #    LAST, immediately before HEALTHY, because it is the weakest verdict
    #    that is still not healthy -- and it is the exact verdict the
    #    2026-07-29 run needed and did not have.
    continuity_reason = _continuity_reason(inputs)
    if continuity_reason is not None:
        return HealthVerdict(
            DEGRADED_COVERAGE_UNPROVEN, [continuity_reason], metrics)

    if within_grace and inputs.heartbeat_present:
        # Heart-beating inside the grace window is already HEALTHY; the grace
        # only ever suppresses ABSENCE.
        return HealthVerdict(HEALTHY, [REASON_ALL_CHECKS_PASSED], metrics)

    return HealthVerdict(HEALTHY, [REASON_ALL_CHECKS_PASSED], metrics)


def canonicalize_health(
    base: HealthVerdict, operational_record: Mapping[str, Any],
) -> HealthVerdict:
    """Merge legacy safety primitives and operational dimensions once.

    ``base`` still supplies the proven process/integrity classification.  The
    operational record supplies whether the running producer is actually doing
    its job.  The returned object is the sole status and control verdict: its
    public ``health_class`` is rendered and persisted, while ``control_class``
    selects continue, bounded restart, or circuit from that same evaluation.
    """

    from PHX2.watchdog import operational_health as operational

    status = operational_record.get("operational_status")
    status = str(status) if isinstance(status, str) else None
    dimensions_raw = operational_record.get("dimensions")
    dimensions = [dict(item) for item in dimensions_raw
                  if isinstance(item, Mapping)] \
        if isinstance(dimensions_raw, (list, tuple)) else []
    unhealthy_names = {
        str(item.get("name")) for item in dimensions
        if item.get("verdict") == operational.DIM_UNHEALTHY
    }

    # Startup, operator stop, open circuit, and primitive integrity/process
    # failures remain authoritative. For a live sound process, operational
    # dimensions are allowed to veto HEALTHY and select the bounded remedy.
    base_is_mergeable = base.health_class in {
        HEALTHY, RECOVERING_WITH_PROGRESS, DEGRADED_COVERAGE_UNPROVEN}
    if not base_is_mergeable or status is None:
        canonical_status = base.health_class
        control = base.health_class
    elif status == operational.HEALTHY:
        canonical_status = base.health_class
        control = base.health_class
    elif status in operational.DEGRADED_STATUSES:
        canonical_status = status
        control = DEGRADED_COVERAGE_UNPROVEN
    elif status in operational.UNHEALTHY_STATUSES:
        canonical_status = status
        integrity_dimensions = {
            "process_ownership", "watch_checkpoint_durability",
            "telegram_ownership", "ledger", "epoch", "circuit",
            "credentials_integrity",
        }
        restart_dimensions = {
            "transport_connection", "scheduler", "market_plane",
            "request_accounting", "authoritative_supply",
        }
        if unhealthy_names & integrity_dimensions:
            control = NONRESTARTABLE_INTEGRITY_FAILURE
        elif unhealthy_names & restart_dimensions:
            control = RESTARTABLE_PROCESS_FAILURE
        else:
            # An unresolved coverage gap cannot be repaired by restarting at
            # live head, but it still vetoes HEALTHY and stability.
            control = DEGRADED_COVERAGE_UNPROVEN
    else:
        canonical_status = status
        control = base.health_class

    operational_causes: List[str] = []
    primary = operational_record.get("primary_cause")
    if isinstance(primary, str) and primary:
        operational_causes.append(primary)
    secondary = operational_record.get("secondary_causes")
    if isinstance(secondary, (list, tuple)):
        operational_causes.extend(
            str(item) for item in secondary if isinstance(item, str) and item)
    reasons = (operational_causes
               if canonical_status != base.health_class and operational_causes
               else list(base.reasons))
    metrics = dict(base.metrics)
    metrics.update({
        "canonical_health_status": canonical_status,
        "canonical_control_class": control,
        "operational_dimensions": dimensions,
    })
    return HealthVerdict(
        canonical_status, reasons, metrics, control_class=control)


def restart_is_permitted(verdict: HealthVerdict) -> bool:
    """Only a restartable class may ever lead to a replacement producer."""

    return verdict.restartable


__all__ = (
    "HEALTHY", "STARTING", "RECOVERING_WITH_PROGRESS",
    "DEGRADED_COVERAGE_UNPROVEN",
    "RESTARTABLE_PROCESS_FAILURE", "RESTARTABLE_STALE_HEARTBEAT",
    "NONRESTARTABLE_INTEGRITY_FAILURE", "NONRESTARTABLE_LEDGER_FAILURE",
    "NONRESTARTABLE_DUPLICATE_OWNER", "CIRCUIT_OPEN", "STOPPED_BY_OPERATOR",
    "HEALTH_CLASSES", "HEALTH_REASONS",
    "RESTARTABLE_CLASSES", "INTEGRITY_CLASSES", "STABLE_CLASSES",
    "RECOVERY_ACTIVE_STATES", "RECOVERY_SETTLED_STATES",
    "RECOVERY_TERMINAL_STATES",
    "CURSOR_DURABILITY_HEALTHY", "CURSOR_DURABILITY_DEGRADED",
    "STRUCTURAL_CHECKPOINT_FAILURE",
    "HealthInputs", "HealthVerdict", "evaluate_health", "canonicalize_health",
    "restart_is_permitted",
)
