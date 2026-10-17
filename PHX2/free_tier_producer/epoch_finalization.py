"""Authenticated operator finalization of an already-stopped live epoch.

Epoch closure normally happens **inside** the producer process: the stream loop
calls :meth:`LiveEpochManager.close` on its way out.  That is the only writer,
and it is the right one -- while a producer is alive nothing else may touch the
durable document.

It leaves one hole.  If the producer never reaches that line -- it is force
terminated after the watchdog's bounded cooperative-stop window expires -- the
durable document keeps saying ``EPOCH_HEALTHY`` forever.  The runtime is gone,
the process tree is empty, and yet the next deployment can never be authorized,
because :func:`validate_closed_epoch_deployment_handoff` requires the prior
epoch to be *definitively closed* and no surviving component is allowed to close
it.  Proven live 2026-08-02: epoch ``epoch_478d5a2ae49f452b9f8a`` armed at
06:13:22Z, operator stop marker at 06:24:26Z, cooperative stop requested at
06:24:34Z, ``FORCE_TERMINATION_AFTER_COOPERATIVE_TIMEOUT`` at 06:29:38Z, and the
document still open at generation 134.

This module is the missing writer, and it is deliberately the *narrowest* one
that can exist:

* it never runs while anything owns the runtime -- every owner count must be
  exactly zero;
* it refuses without an explicit operator acknowledgment;
* it authenticates the prior run against evidence the run itself wrote: the
  durable ``run_instance_identity`` names a runtime nonce and a startup-manifest
  sha256, and the preserved launch manifest must hash to exactly that value and
  name the same nonce, repository head and launcher;
* the close time and the close reason are **derived from preserved shutdown
  evidence**, never invented, and ambiguous or contradictory evidence refuses;
* it invents no end slot: the epoch's own start slot and boundary are carried
  through untouched, and no new slot is claimed;
* it never arms, starts or restarts anything, and never opens the paid ledger.

What it writes is one status transition plus one history record, to primary and
backup identically, preserving every field of the original open document.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.live_epoch import (
    EPOCH_CLOSED,
    EPOCH_CONTINUITY_BROKEN,
    EPOCH_HEALTHY,
    EPOCH_STARTING,
    LIVE_EPOCH_BACKUP_SUFFIX,
    LIVE_EPOCH_POLICY_IDENTITY_SCHEMA,
    LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
    classify_live_epoch_document_set,
    closed_epoch_archive_path,
)


STOPPED_EPOCH_FINALIZATION_SCHEMA = "phx2_stopped_epoch_finalization_v1"

#: The marker every finalized close record carries, so a reader can always tell
#: an operator finalization apart from a close the producer wrote itself.
STOPPED_EPOCH_FINALIZATION_EVENT = "OPERATOR_STOPPED_EPOCH_FINALIZATION"

#: Statuses a still-open epoch may legitimately hold.  An integrity failure is
#: deliberately absent: a document that failed its own integrity check is not
#: evidence of anything and must not be laundered into a closed state.
OPEN_EPOCH_STATUSES = (
    EPOCH_STARTING,
    EPOCH_HEALTHY,
    EPOCH_CONTINUITY_BROKEN,
)

#: Close reasons this path may write, and nothing else.  Each names exactly how
#: the producer stopped, as proven by the watchdog's own preserved evidence.
FINALIZED_FORCED = "OPERATOR_STOP_FORCED_TERMINATION"
FINALIZED_COOPERATIVE = "OPERATOR_STOP_COOPERATIVE_EXIT"
FINALIZATION_CLOSE_REASONS = (FINALIZED_FORCED, FINALIZED_COOPERATIVE)

FINALIZE_ACK_MISSING = "FINALIZE_OPERATOR_ACKNOWLEDGMENT_MISSING"
FINALIZE_DOCUMENT_INVALID = "FINALIZE_EPOCH_DOCUMENT_INVALID"
FINALIZE_NOT_PRIMARY = "FINALIZE_EPOCH_NOT_AUTHENTICATED_PRIMARY"
FINALIZE_EPOCH_NOT_OPEN = "FINALIZE_EPOCH_NOT_OPEN"
FINALIZE_RUN_IDENTITY_INVALID = "FINALIZE_PRIOR_RUN_IDENTITY_INVALID"
FINALIZE_POLICY_IDENTITY_INVALID = "FINALIZE_PRIOR_POLICY_IDENTITY_INVALID"
FINALIZE_MANIFEST_UNAVAILABLE = "FINALIZE_STARTUP_MANIFEST_UNAVAILABLE"
FINALIZE_MANIFEST_MISMATCH = "FINALIZE_STARTUP_MANIFEST_DIGEST_MISMATCH"
FINALIZE_NONCE_MISMATCH = "FINALIZE_PRIOR_RUNTIME_NONCE_MISMATCH"
FINALIZE_HEAD_MISMATCH = "FINALIZE_PRIOR_REPOSITORY_HEAD_MISMATCH"
FINALIZE_LAUNCHER_MISMATCH = "FINALIZE_PRIOR_LAUNCHER_MISMATCH"
FINALIZE_EVIDENCE_MISSING = "FINALIZE_SHUTDOWN_EVIDENCE_MISSING"
FINALIZE_EVIDENCE_CONFLICT = "FINALIZE_SHUTDOWN_EVIDENCE_CONFLICT"
FINALIZE_LATER_REARM = "FINALIZE_LATER_REARM_OBSERVED"
FINALIZE_ACTIVE_WATCHDOG = "FINALIZE_ACTIVE_WATCHDOG"
FINALIZE_ACTIVE_PRODUCER = "FINALIZE_ACTIVE_PRODUCER"
FINALIZE_ACTIVE_YELLOWSTONE_OWNER = "FINALIZE_ACTIVE_YELLOWSTONE_OWNER"
FINALIZE_ACTIVE_TELEGRAM_OWNER = "FINALIZE_ACTIVE_TELEGRAM_DELIVERY_OWNER"
FINALIZE_ACTIVE_LEDGER_WRITER = "FINALIZE_ACTIVE_CANONICAL_LEDGER_WRITER"
FINALIZE_LIVE_OR_AMBIGUOUS_LOCK = "FINALIZE_LIVE_OR_AMBIGUOUS_LOCK"
FINALIZE_WRITE_READBACK_FAILED = "FINALIZE_WRITE_READBACK_FAILED"

#: Watchdog event kinds this module reads.  Anything else is ignored.
EVENT_OPERATOR_STOP_MARKER = "OPERATOR_STOP_MARKER_CREATED"
EVENT_COOPERATIVE_STOP_REQUESTED = "COOPERATIVE_STOP_REQUESTED"
EVENT_COOPERATIVE_STOP_COMPLETED = "COOPERATIVE_STOP_COMPLETED"
EVENT_FORCE_TERMINATION = "FORCE_TERMINATION"
EVENT_WATCHDOG_STOP = "WATCHDOG_STOP"

#: Any of these appearing AFTER the terminal watchdog stop means the runtime was
#: armed again, so evidence describing the earlier stop is stale.  These are the
#: watchdog's own launch/adopt/restart event kinds, verbatim.
REARM_EVENT_KINDS = (
    "WATCHDOG_START",
    "PRODUCER_LAUNCHED",
    "PRODUCER_ADOPTED",
    "RESTART_REQUESTED",
    "RESTART_COMPLETED",
)

OPERATOR_STOP_OUTCOME = "OPERATOR_STOP"


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _valid_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == int(length)
        and all(char in "0123456789abcdef" for char in value)
    )


def _parse_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _valid_utc(value: object) -> bool:
    return _parse_utc(value) is not None


def _positive_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return int(value)


@dataclass(frozen=True)
class StoppedRuntimeShutdownEvidence:
    """Preserved, read-only facts about how one run actually stopped.

    Every field is copied from an artifact the stopped run (or its watchdog)
    wrote at the time.  Nothing here is derived from "no process is alive now":
    an empty process table proves the runtime is not running, never that it shut
    down in a state safe to record as a definitive close.
    """

    #: The run this evidence describes; must equal the durable runtime nonce.
    runtime_nonce: str = ""
    #: sha256 of the preserved startup manifest file, as read from disk.
    startup_manifest_sha256: str = ""
    #: Identity the manifest itself asserts for that run.
    manifest_run_id: str = ""
    manifest_repository_head: str = ""
    manifest_launcher_sha256: str = ""
    manifest_watchdog_pid: Optional[int] = None
    manifest_started_at_utc: str = ""
    #: Producer named by the watchdog's ``current_child`` record, if present.
    current_child_producer_pid: Optional[int] = None
    #: Shutdown timeline, each straight from the watchdog's own artifacts.
    operator_stop_requested_at_utc: str = ""
    cooperative_stop_requested_at_utc: str = ""
    cooperative_stop_completed_at_utc: str = ""
    forced_termination_at_utc: str = ""
    watchdog_stop_at_utc: str = ""
    watchdog_stop_outcome: str = ""
    #: True when any evidence of a later arm was observed.
    later_rearm_observed: bool = False
    #: Non-fatal facts recorded for the audit payload.
    evidence_sources: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StoppedEpochFinalizationContext:
    """Live-ownership facts and the operator's explicit acknowledgment.

    Process and lock inspection stay outside this module exactly as they do for
    the deployment handoff, so the policy is deterministic under test.
    """

    operator_acknowledged: bool = False
    watchdog_count: int = 0
    producer_count: int = 0
    yellowstone_owner_count: int = 0
    telegram_delivery_owner_count: int = 0
    canonical_ledger_writer_count: int = 0
    live_or_ambiguous_lock_count: int = 0


@dataclass
class StoppedEpochFinalizationVerdict:
    allowed: bool = False
    refusals: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)
    #: The exact close record this finalization would append (or did append).
    close_record: Dict[str, Any] = field(default_factory=dict)
    #: True when the epoch was ALREADY finalized to this exact close record.
    already_final: bool = False
    #: True only when this call performed the durable write.
    written: bool = False


def _read_json(path: object) -> Tuple[bool, Dict[str, Any]]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False, {}
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return False, {}
    if not isinstance(document, dict):
        return False, {}
    return True, document


def _file_sha256(path: object) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _parse_marker_timestamp(text: object) -> str:
    """``requested_at_utc=<iso>`` -- the operator stop marker's only content."""

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "requested_at_utc" and _valid_utc(value.strip()):
            return value.strip()
    return ""


def read_stopped_runtime_shutdown_evidence(
    *,
    runtime_nonce: object,
    startup_manifest_binding: object,
    watchdog_state_root: object,
    launch_manifest_dir: object,
    operator_stop_marker_path: object,
    events_path: object,
    current_child_path: Optional[object] = None,
) -> StoppedRuntimeShutdownEvidence:
    """Collect the preserved shutdown evidence for one runtime nonce.

    Pure reads.  Nothing is written, moved or deleted, and an absent or
    unreadable artifact simply leaves its field empty so the classifier can
    refuse for missing evidence rather than guess.
    """

    nonce = str(runtime_nonce or "")
    binding = str(startup_manifest_binding or "").strip().lower()
    sources: List[str] = []

    manifest_sha = ""
    manifest_run_id = ""
    manifest_head = ""
    manifest_launcher = ""
    manifest_watchdog_pid: Optional[int] = None
    manifest_started_at = ""
    child_producer_pid: Optional[int] = None
    manifest_dir = Path(launch_manifest_dir)
    try:
        candidates = sorted(manifest_dir.glob("*.json"))
    except OSError:
        candidates = []
    for candidate in candidates:
        digest = _file_sha256(candidate)
        # The manifest is selected by CONTENT, never by name or mtime: the
        # durable epoch already committed to this exact sha256, so only the file
        # that reproduces it can describe the run being finalized.
        if digest is None or not binding or digest != binding:
            continue
        parsed, document = _read_json(candidate)
        if not parsed:
            continue
        manifest_sha = digest
        manifest_run_id = str(document.get("run_id") or "")
        manifest_head = str(document.get("pinned_repo_head") or "").lower()
        manifest_launcher = str(document.get("launcher_sha256") or "").lower()
        manifest_watchdog_pid = _positive_int(
            document.get("watchdog_parent_pid"))
        manifest_started_at = (
            str(document.get("started_at_utc"))
            if _valid_utc(document.get("started_at_utc")) else "")
        sources.append("startup_manifest")
        break

    marker_at = ""
    try:
        marker_at = _parse_marker_timestamp(
            Path(operator_stop_marker_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        marker_at = ""
    if marker_at:
        sources.append("operator_stop_marker")

    cooperative_requested = ""
    cooperative_completed = ""
    forced_at = ""
    watchdog_stop_at = ""
    watchdog_stop_outcome = ""
    rearm = False
    try:
        event_lines = Path(events_path).read_text(
            encoding="utf-8", errors="replace").splitlines()
    except (OSError, UnicodeError):
        event_lines = []
    # The event log is append-only ACROSS runs, and every earlier run also ended
    # in WATCHDOG_STOP followed by the next run's launch events.  Scoping to the
    # window that opens at this run's own manifest timestamp is what keeps an
    # ordinary restart history from reading as a re-arm of THIS run.  Without an
    # authenticated manifest there is no window, so no timeline is derived and
    # the classifier refuses for missing evidence.
    run_started = _parse_utc(manifest_started_at)
    saw_terminal_stop = False
    for raw in event_lines:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A torn tail line is not evidence of a re-arm and is not fatal on
            # its own; the classifier still requires a complete timeline.
            continue
        if not isinstance(event, dict):
            continue
        at_utc = str(event.get("at_utc") or "")
        observed = _parse_utc(at_utc)
        if run_started is None or observed is None or observed < run_started:
            continue
        kind = str(event.get("kind") or "")
        if saw_terminal_stop:
            if kind in REARM_EVENT_KINDS:
                rearm = True
            continue
        if kind == EVENT_COOPERATIVE_STOP_REQUESTED:
            cooperative_requested = at_utc
        elif kind == EVENT_COOPERATIVE_STOP_COMPLETED:
            cooperative_completed = at_utc
        elif kind == EVENT_FORCE_TERMINATION:
            forced_at = at_utc
        elif kind == EVENT_WATCHDOG_STOP:
            watchdog_stop_at = at_utc
            watchdog_stop_outcome = str(event.get("outcome") or "")
            saw_terminal_stop = True
    if watchdog_stop_at:
        sources.append("watchdog_events")

    if current_child_path is not None:
        parsed, child = _read_json(current_child_path)
        if parsed:
            child_producer_pid = _positive_int(child.get("producer_pid"))
            child_stamp = str(child.get("run_stamp") or "")
            # ``current_child`` is rewritten on every launch.  If it names a run
            # stamp this nonce does not end with, a later child was started.
            if child_stamp and nonce and not nonce.endswith(child_stamp):
                rearm = True
            sources.append("current_child")

    # A launch manifest newer than the one this run committed to is a launch
    # that happened after it -- proof of a re-arm regardless of event ordering.
    if manifest_sha:
        for candidate in candidates:
            if _file_sha256(candidate) == manifest_sha:
                continue
            parsed, document = _read_json(candidate)
            if not parsed:
                continue
            started = _parse_utc(document.get("started_at_utc"))
            terminal = _parse_utc(watchdog_stop_at)
            if started is not None and terminal is not None \
                    and started > terminal:
                rearm = True

    return StoppedRuntimeShutdownEvidence(
        runtime_nonce=nonce,
        startup_manifest_sha256=manifest_sha,
        manifest_run_id=manifest_run_id,
        manifest_repository_head=manifest_head,
        manifest_launcher_sha256=manifest_launcher,
        manifest_watchdog_pid=manifest_watchdog_pid,
        manifest_started_at_utc=manifest_started_at,
        current_child_producer_pid=child_producer_pid,
        operator_stop_requested_at_utc=marker_at,
        cooperative_stop_requested_at_utc=cooperative_requested,
        cooperative_stop_completed_at_utc=cooperative_completed,
        forced_termination_at_utc=forced_at,
        watchdog_stop_at_utc=watchdog_stop_at,
        watchdog_stop_outcome=watchdog_stop_outcome,
        later_rearm_observed=rearm,
        evidence_sources=tuple(sources),
    )


def derive_close_from_shutdown_evidence(
    evidence: StoppedRuntimeShutdownEvidence,
    *,
    epoch_started_at_utc: object,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """``(closed_at_utc, reason, refusals)`` derived strictly from evidence.

    The close time is a timestamp the watchdog actually recorded for the
    producer's termination -- never "now", never the epoch's own clock.  The
    reason names which of the two sanctioned terminations happened.  If the
    evidence does not state one unambiguously, both come back ``None``.
    """

    refusals: List[str] = []
    started = _parse_utc(epoch_started_at_utc)
    marker = _parse_utc(evidence.operator_stop_requested_at_utc)
    requested = _parse_utc(evidence.cooperative_stop_requested_at_utc)
    completed = _parse_utc(evidence.cooperative_stop_completed_at_utc)
    forced = _parse_utc(evidence.forced_termination_at_utc)
    terminal = _parse_utc(evidence.watchdog_stop_at_utc)

    if marker is None or terminal is None or requested is None:
        refusals.append(FINALIZE_EVIDENCE_MISSING)
        return None, None, refusals
    if evidence.watchdog_stop_outcome != OPERATOR_STOP_OUTCOME:
        # A watchdog that stopped for any other outcome did not observe an
        # operator shutdown of this producer, so it cannot attest to one.
        refusals.append(FINALIZE_EVIDENCE_MISSING)
        return None, None, refusals
    if completed is None and forced is None:
        refusals.append(FINALIZE_EVIDENCE_MISSING)
        return None, None, refusals
    if completed is not None and forced is not None:
        # Both terminations recorded for one stop: the watchdog cannot have
        # observed a cooperative exit AND had to force the same producer.
        refusals.append(FINALIZE_EVIDENCE_CONFLICT)
        return None, None, refusals

    closed_at_dt = completed if completed is not None else forced
    reason = (
        FINALIZED_COOPERATIVE if completed is not None else FINALIZED_FORCED)

    ordered = [marker, requested, closed_at_dt, terminal]
    if any(later < earlier
           for earlier, later in zip(ordered, ordered[1:])):
        refusals.append(FINALIZE_EVIDENCE_CONFLICT)
        return None, None, refusals
    if started is not None and marker < started:
        # The stop was requested before this epoch even opened, so it describes
        # some earlier runtime and must not be used to close this one.
        refusals.append(FINALIZE_EVIDENCE_CONFLICT)
        return None, None, refusals

    closed_at = (
        evidence.cooperative_stop_completed_at_utc
        if completed is not None else evidence.forced_termination_at_utc)
    return closed_at, reason, refusals


def _finalization_attestation(
    *,
    epoch: Mapping[str, Any],
    evidence: StoppedRuntimeShutdownEvidence,
) -> Dict[str, Any]:
    run_identity = epoch.get("run_instance_identity")
    run_identity = run_identity if isinstance(run_identity, Mapping) else {}
    policy_identity = epoch.get("durable_policy_identity")
    policy_identity = (
        policy_identity if isinstance(policy_identity, Mapping) else {})
    return {
        "schema_version": STOPPED_EPOCH_FINALIZATION_SCHEMA,
        "event_type": STOPPED_EPOCH_FINALIZATION_EVENT,
        "prior_runtime_nonce": str(run_identity.get("runtime_nonce") or ""),
        "prior_producer_pid": run_identity.get("producer_pid"),
        "prior_watchdog_pid": run_identity.get("watchdog_pid"),
        "prior_repository_head": str(
            policy_identity.get("repo_head_binding") or ""),
        "prior_launcher_sha256": str(
            policy_identity.get("launcher_sha256_binding") or ""),
        "startup_manifest_sha256": str(evidence.startup_manifest_sha256 or ""),
        "operator_stop_requested_at_utc": str(
            evidence.operator_stop_requested_at_utc or ""),
        "cooperative_stop_requested_at_utc": str(
            evidence.cooperative_stop_requested_at_utc or ""),
        "watchdog_stop_at_utc": str(evidence.watchdog_stop_at_utc or ""),
        "watchdog_stop_outcome": str(evidence.watchdog_stop_outcome or ""),
    }


def validate_stopped_epoch_finalization(
    *,
    epoch_path: object,
    evidence: StoppedRuntimeShutdownEvidence,
    context: StoppedEpochFinalizationContext,
) -> StoppedEpochFinalizationVerdict:
    """Decide whether one stopped epoch may be definitively closed.

    Never mutates anything.  Produces the exact close record a subsequent
    :func:`finalize_stopped_epoch` would write, so the operator can be shown the
    derived time and reason before any durable state changes.
    """

    refusals: List[str] = []
    checks: Dict[str, Any] = {}

    if not context.operator_acknowledged:
        refusals.append(FINALIZE_ACK_MISSING)

    for count, reason in (
        (context.watchdog_count, FINALIZE_ACTIVE_WATCHDOG),
        (context.producer_count, FINALIZE_ACTIVE_PRODUCER),
        (context.yellowstone_owner_count, FINALIZE_ACTIVE_YELLOWSTONE_OWNER),
        (context.telegram_delivery_owner_count,
         FINALIZE_ACTIVE_TELEGRAM_OWNER),
        (context.canonical_ledger_writer_count, FINALIZE_ACTIVE_LEDGER_WRITER),
        (context.live_or_ambiguous_lock_count, FINALIZE_LIVE_OR_AMBIGUOUS_LOCK),
    ):
        if isinstance(count, bool) or not isinstance(count, int) or count != 0:
            refusals.append(reason)
    checks.update({
        "watchdog_count": context.watchdog_count,
        "producer_count": context.producer_count,
        "yellowstone_owner_count": context.yellowstone_owner_count,
        "telegram_delivery_owner_count":
            context.telegram_delivery_owner_count,
        "canonical_ledger_writer_count":
            context.canonical_ledger_writer_count,
        "live_or_ambiguous_lock_count": context.live_or_ambiguous_lock_count,
        "operator_acknowledged": bool(context.operator_acknowledged),
    })

    state, epoch, facts = classify_live_epoch_document_set(epoch_path)
    checks["epoch_document_state"] = state
    checks["epoch_selected"] = facts.get("selected")
    if state != "VALID_CURRENT":
        refusals.append(FINALIZE_DOCUMENT_INVALID)
        return StoppedEpochFinalizationVerdict(
            allowed=False, refusals=_ordered(refusals), checks=checks)
    if facts.get("selected") != "primary":
        refusals.append(FINALIZE_NOT_PRIMARY)

    epoch_status = epoch.get("epoch_status")
    epoch_id = epoch.get("live_epoch_id")
    checks["epoch_id"] = epoch_id if isinstance(epoch_id, str) else None
    checks["epoch_status"] = epoch_status
    checks["epoch_generation"] = epoch.get("generation")

    run_identity = epoch.get("run_instance_identity")
    if not isinstance(run_identity, Mapping) \
            or run_identity.get("identity_schema") \
            != LIVE_EPOCH_RUN_IDENTITY_SCHEMA:
        refusals.append(FINALIZE_RUN_IDENTITY_INVALID)
        run_identity = {}
    durable_nonce = str(run_identity.get("runtime_nonce") or "")
    manifest_binding = str(
        run_identity.get("startup_manifest_binding") or "").lower()
    if not durable_nonce or _positive_int(
            run_identity.get("producer_pid")) is None \
            or not _valid_lower_hex(manifest_binding, 64):
        refusals.append(FINALIZE_RUN_IDENTITY_INVALID)
    checks["prior_runtime_nonce"] = durable_nonce or None

    policy_identity = epoch.get("durable_policy_identity")
    if not isinstance(policy_identity, Mapping) \
            or policy_identity.get("identity_schema") \
            != LIVE_EPOCH_POLICY_IDENTITY_SCHEMA:
        refusals.append(FINALIZE_POLICY_IDENTITY_INVALID)
        policy_identity = {}
    prior_head = str(policy_identity.get("repo_head_binding") or "").lower()
    prior_launcher = str(
        policy_identity.get("launcher_sha256_binding") or "").lower()
    if not _valid_lower_hex(prior_head, 40) \
            or not _valid_lower_hex(prior_launcher, 64):
        refusals.append(FINALIZE_POLICY_IDENTITY_INVALID)
    checks["prior_repository_head"] = prior_head or None
    checks["prior_launcher_sha256"] = prior_launcher or None

    # -- authenticate the prior run against its own preserved manifest ------- #
    if not _valid_lower_hex(evidence.startup_manifest_sha256, 64):
        refusals.append(FINALIZE_MANIFEST_UNAVAILABLE)
    elif manifest_binding and evidence.startup_manifest_sha256 \
            != manifest_binding:
        refusals.append(FINALIZE_MANIFEST_MISMATCH)
    else:
        if not evidence.manifest_run_id \
                or evidence.manifest_run_id != durable_nonce \
                or (evidence.runtime_nonce
                    and evidence.runtime_nonce != durable_nonce):
            refusals.append(FINALIZE_NONCE_MISMATCH)
        if evidence.manifest_repository_head != prior_head:
            refusals.append(FINALIZE_HEAD_MISMATCH)
        if evidence.manifest_launcher_sha256 != prior_launcher:
            refusals.append(FINALIZE_LAUNCHER_MISMATCH)
        durable_watchdog_pid = _positive_int(run_identity.get("watchdog_pid"))
        if durable_watchdog_pid is not None \
                and evidence.manifest_watchdog_pid is not None \
                and durable_watchdog_pid != evidence.manifest_watchdog_pid:
            refusals.append(FINALIZE_NONCE_MISMATCH)
        durable_producer_pid = _positive_int(run_identity.get("producer_pid"))
        if durable_producer_pid is not None \
                and evidence.current_child_producer_pid is not None \
                and durable_producer_pid != evidence.current_child_producer_pid:
            # ``current_child`` names a different producer than the durable
            # document: some other child ran after this one.
            refusals.append(FINALIZE_LATER_REARM)
    checks["startup_manifest_sha256"] = (
        evidence.startup_manifest_sha256 or None)
    checks["manifest_run_id"] = evidence.manifest_run_id or None
    # Which preserved artifacts were actually readable, so a refusal for missing
    # evidence names what was absent rather than just that something was.
    checks["evidence_sources"] = list(evidence.evidence_sources)

    if evidence.later_rearm_observed:
        refusals.append(FINALIZE_LATER_REARM)
    checks["later_rearm_observed"] = bool(evidence.later_rearm_observed)

    closed_at, reason, evidence_refusals = (
        derive_close_from_shutdown_evidence(
            evidence, epoch_started_at_utc=epoch.get("epoch_started_at_utc")))
    refusals.extend(evidence_refusals)
    checks["derived_closed_at_utc"] = closed_at
    checks["derived_close_reason"] = reason

    close_record: Dict[str, Any] = {}
    if closed_at and reason and isinstance(epoch_id, str) and epoch_id:
        close_record = {
            "live_epoch_id": epoch_id,
            "epoch_status": EPOCH_CLOSED,
            "reason": reason,
            "closed_at_utc": closed_at,
            # Carried through, never invented.  A never-armed epoch keeps its
            # ``None`` start slot and no end slot is claimed for anything.
            "epoch_start_slot": epoch.get("epoch_start_slot"),
            "finalization": _finalization_attestation(
                epoch=epoch, evidence=evidence),
        }

    # -- idempotence -------------------------------------------------------- #
    # An epoch already finalized to EXACTLY this record is a success, not a
    # refusal, and performs no write.  A closed epoch whose record disagrees is
    # neither: it is left exactly as it is.
    history = epoch.get("epoch_history")
    history = list(history) if isinstance(history, list) else []
    existing = history[-1] if history and isinstance(
        history[-1], Mapping) else {}
    already_final = bool(
        epoch_status == EPOCH_CLOSED
        and close_record
        and dict(existing) == close_record)
    checks["already_final"] = already_final
    if already_final:
        # Returned BEFORE the still-open requirement is applied, so a completed
        # close reports success instead of "not open".  Ownership, acknowledgment
        # and every authentication refusal above still gate the answer.
        return StoppedEpochFinalizationVerdict(
            allowed=not refusals,
            refusals=_ordered(refusals),
            checks=checks,
            close_record=dict(close_record),
            already_final=True,
        )
    if epoch_status not in OPEN_EPOCH_STATUSES:
        refusals.append(FINALIZE_EPOCH_NOT_OPEN)

    ordered = _ordered(refusals)
    return StoppedEpochFinalizationVerdict(
        allowed=not ordered and bool(close_record),
        refusals=ordered,
        checks=checks,
        close_record=dict(close_record),
        already_final=False,
    )


def _ordered(refusals: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for reason in refusals:
        if reason not in seen:
            seen.append(reason)
    return seen


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".finalize.tmp")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def finalize_stopped_epoch(
    *,
    epoch_path: object,
    evidence: StoppedRuntimeShutdownEvidence,
    context: StoppedEpochFinalizationContext,
) -> StoppedEpochFinalizationVerdict:
    """Write the authenticated definitive close to primary AND backup.

    Every field of the open document survives untouched except ``epoch_status``,
    the appended history record, ``generation`` and ``updated_at_utc``.  Primary
    and backup receive byte-identical documents, so the pair authenticates as
    one agreeing generation rather than the usual write-ahead skew.
    """

    verdict = validate_stopped_epoch_finalization(
        epoch_path=epoch_path, evidence=evidence, context=context)
    if not verdict.allowed or verdict.already_final:
        return verdict

    primary = Path(epoch_path)
    backup = primary.with_name(primary.name + LIVE_EPOCH_BACKUP_SUFFIX)
    state, epoch, _facts = classify_live_epoch_document_set(primary)
    if state != "VALID_CURRENT":
        verdict.allowed = False
        verdict.refusals = _ordered(
            list(verdict.refusals) + [FINALIZE_DOCUMENT_INVALID])
        return verdict

    # Preserve the EXACT open document before changing it.  The durable history
    # is a bounded 32-record window, so a finalization that appends could push
    # the oldest transition out of the live document; the archive keeps the
    # pre-finalization bytes verbatim, keyed by their own sha256.  This runs
    # before any mutation, and a failure to preserve refuses the finalization.
    try:
        prior_bytes = primary.read_bytes()
    except OSError:
        verdict.allowed = False
        verdict.refusals = _ordered(
            list(verdict.refusals) + [FINALIZE_DOCUMENT_INVALID])
        return verdict
    prior_file_sha256 = hashlib.sha256(prior_bytes).hexdigest()
    archive = closed_epoch_archive_path(primary, prior_file_sha256)
    if _file_sha256(archive) != prior_file_sha256:
        try:
            _write_atomic(archive, prior_bytes)
        except OSError:
            verdict.allowed = False
            verdict.refusals = _ordered(
                list(verdict.refusals) + [FINALIZE_WRITE_READBACK_FAILED])
            return verdict
    if _file_sha256(archive) != prior_file_sha256:
        verdict.allowed = False
        verdict.refusals = _ordered(
            list(verdict.refusals) + [FINALIZE_WRITE_READBACK_FAILED])
        return verdict
    verdict.checks["preserved_prior_document_sha256"] = prior_file_sha256

    history = list(epoch.get("epoch_history") or [])
    history.append(dict(verdict.close_record))
    payload = dict(epoch)
    payload["epoch_status"] = EPOCH_CLOSED
    payload["epoch_history"] = history[-32:]
    payload["generation"] = int(epoch.get("generation") or 0) + 1
    # The document's own clock advances (this write happened now); the CLOSE
    # timestamp inside the history record stays the evidence-derived one.
    payload["updated_at_utc"] = datetime.now(
        tz=timezone.utc).isoformat().replace("+00:00", "Z")
    document = {**payload, "document_digest": _digest(payload)}
    data = _canonical(document) + b"\n"

    try:
        _write_atomic(backup, data)
        _write_atomic(primary, data)
    except OSError:
        verdict.allowed = False
        verdict.refusals = _ordered(
            list(verdict.refusals) + [FINALIZE_WRITE_READBACK_FAILED])
        return verdict

    readback_state, readback, readback_facts = (
        classify_live_epoch_document_set(primary))
    backup_sha = _file_sha256(backup)
    primary_sha = _file_sha256(primary)
    if readback_state != "VALID_CURRENT" \
            or readback_facts.get("selected") != "primary" \
            or readback.get("epoch_status") != EPOCH_CLOSED \
            or int(readback.get("generation") or 0) != payload["generation"] \
            or primary_sha is None or primary_sha != backup_sha:
        verdict.allowed = False
        verdict.refusals = _ordered(
            list(verdict.refusals) + [FINALIZE_WRITE_READBACK_FAILED])
        return verdict

    verdict.written = True
    verdict.checks["finalized_generation"] = int(readback["generation"])
    verdict.checks["primary_backup_identical"] = True
    return verdict


__all__ = (
    "STOPPED_EPOCH_FINALIZATION_SCHEMA",
    "STOPPED_EPOCH_FINALIZATION_EVENT",
    "OPEN_EPOCH_STATUSES",
    "FINALIZATION_CLOSE_REASONS",
    "FINALIZED_FORCED",
    "FINALIZED_COOPERATIVE",
    "FINALIZE_ACK_MISSING",
    "FINALIZE_DOCUMENT_INVALID",
    "FINALIZE_NOT_PRIMARY",
    "FINALIZE_EPOCH_NOT_OPEN",
    "FINALIZE_RUN_IDENTITY_INVALID",
    "FINALIZE_POLICY_IDENTITY_INVALID",
    "FINALIZE_MANIFEST_UNAVAILABLE",
    "FINALIZE_MANIFEST_MISMATCH",
    "FINALIZE_NONCE_MISMATCH",
    "FINALIZE_HEAD_MISMATCH",
    "FINALIZE_LAUNCHER_MISMATCH",
    "FINALIZE_EVIDENCE_MISSING",
    "FINALIZE_EVIDENCE_CONFLICT",
    "FINALIZE_LATER_REARM",
    "FINALIZE_ACTIVE_WATCHDOG",
    "FINALIZE_ACTIVE_PRODUCER",
    "FINALIZE_ACTIVE_YELLOWSTONE_OWNER",
    "FINALIZE_ACTIVE_TELEGRAM_OWNER",
    "FINALIZE_ACTIVE_LEDGER_WRITER",
    "FINALIZE_LIVE_OR_AMBIGUOUS_LOCK",
    "FINALIZE_WRITE_READBACK_FAILED",
    "StoppedRuntimeShutdownEvidence",
    "StoppedEpochFinalizationContext",
    "StoppedEpochFinalizationVerdict",
    "read_stopped_runtime_shutdown_evidence",
    "derive_close_from_shutdown_evidence",
    "validate_stopped_epoch_finalization",
    "finalize_stopped_epoch",
)
