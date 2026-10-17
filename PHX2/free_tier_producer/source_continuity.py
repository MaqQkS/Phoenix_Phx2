"""Canonical Yellowstone source-continuity state machine and durable gap document.

This is the ONE authoritative definition of "did the single owned stream cover
every slot it claims to have covered".  Before this module existed there were
two independent notions of coverage:

* the durable stream cursor (:mod:`PHX2.free_tier_producer.stream_cursor`),
  whose disconnect/recovery bookkeeping was reachable ONLY when live-epoch mode
  was off; and
* the live-epoch manager, which on reconnect simply closed the old epoch and
  armed a fresh one at whatever slot arrived next -- the provider's live head.

Production runs live-epoch mode, so the cursor half never executed and the
live-epoch half performed no slot comparison at all.  A reconnect could
therefore skip an arbitrary range with every gap counter reading zero while the
display status still read ``CONNECTED_LIVE_HEALTHY``.  The 2026-07-29
acceptance run lost slots 435896378..435898561 (2,184 slots) exactly this way.

The invariant this module enforces is deliberately narrow and arithmetic::

    expected_next_slot = last_fully_processed_slot + 1
    gap when first_post_reconnect_slot > expected_next_slot

A gap is EVIDENCE, not a verdict.  Recording one never terminal-locks the
stream: live-epoch policy keeps observing forward.  What a gap does do is make
it impossible for any layer to report healthy continuous coverage while the
range is unproven, and it survives epoch rollover so the re-arm can never erase
the record of what was skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "phx2_source_continuity_v1"
DOCUMENT_KIND = "PHX2_SOURCE_CONTINUITY_STATE"

# -- continuity states (closed set) ----------------------------------------
NO_GAP = "NO_GAP"
GAP_DETECTED = "GAP_DETECTED"
RECOVERY_REQUESTED = "RECOVERY_REQUESTED"
RECOVERING = "RECOVERING"
PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
RECOVERED = "RECOVERED"
UNRESOLVED = "UNRESOLVED"
RECOVERY_UNAVAILABLE = "RECOVERY_UNAVAILABLE"
RECOVERY_FAILED = "RECOVERY_FAILED"

CONTINUITY_STATES = (
    NO_GAP, GAP_DETECTED, RECOVERY_REQUESTED, RECOVERING,
    PARTIALLY_RECOVERED, RECOVERED, UNRESOLVED, RECOVERY_UNAVAILABLE,
    RECOVERY_FAILED,
)

#: States in which coverage is NOT proven continuous. Any layer that wants to
#: claim healthy ingestion must find the current state outside this set.
UNPROVEN_STATES = (
    GAP_DETECTED, RECOVERY_REQUESTED, RECOVERING, PARTIALLY_RECOVERED,
    UNRESOLVED, RECOVERY_UNAVAILABLE, RECOVERY_FAILED,
)

#: States that are terminal for THIS gap: recovery will not progress further
#: without operator action. They are unhealthy but never stop the stream.
TERMINAL_GAP_STATES = (UNRESOLVED, RECOVERY_UNAVAILABLE, RECOVERY_FAILED)

# -- disconnect reason classes (closed set; never provider exception text) ---
REASON_PROVIDER_ERROR = "PROVIDER_ERROR"
REASON_PROVIDER_DISCONNECT = "PROVIDER_DISCONNECT"
REASON_WATCHDOG_STALE = "WATCHDOG_STALE"
REASON_AUTH_FAILURE = "AUTH_FAILURE"
REASON_OWNER_ERROR = "OWNER_ERROR"
REASON_OPERATOR_SHUTDOWN = "OPERATOR_SHUTDOWN"
REASON_UNKNOWN = "UNKNOWN"

DISCONNECT_REASON_CLASSES = (
    REASON_PROVIDER_ERROR, REASON_PROVIDER_DISCONNECT, REASON_WATCHDOG_STALE,
    REASON_AUTH_FAILURE, REASON_OWNER_ERROR, REASON_OPERATOR_SHUTDOWN,
    REASON_UNKNOWN,
)

# -- recovery failure reasons (closed set) ----------------------------------
FAILURE_NONE = "NONE"
FAILURE_REPLAY_UNSUPPORTED = "REPLAY_UNSUPPORTED"
FAILURE_REPLAY_REFUSED = "REPLAY_REFUSED"
FAILURE_REPLAY_POSITION_TOO_OLD = "REPLAY_POSITION_TOO_OLD"
FAILURE_REPLAY_INCOMPLETE = "REPLAY_INCOMPLETE"
FAILURE_ATTEMPTS_EXHAUSTED = "RECOVERY_ATTEMPTS_EXHAUSTED"
FAILURE_HTTP_PARTIAL = "HELIUS_HTTP_PARTIAL"
FAILURE_HTTP_PROVIDER = "HELIUS_HTTP_PROVIDER_ERROR"
FAILURE_HTTP_CEILING = "HELIUS_HTTP_CEILING"

RECOVERY_FAILURE_REASONS = (
    FAILURE_NONE, FAILURE_REPLAY_UNSUPPORTED, FAILURE_REPLAY_REFUSED,
    FAILURE_REPLAY_POSITION_TOO_OLD, FAILURE_REPLAY_INCOMPLETE,
    FAILURE_ATTEMPTS_EXHAUSTED, FAILURE_HTTP_PARTIAL,
    FAILURE_HTTP_PROVIDER, FAILURE_HTTP_CEILING,
)

#: A forward jump larger than this is disclosed as physically implausible for
#: the observed reconnect wall-clock. Solana produces well under 10 slots/s;
#: the bound is deliberately loose so only genuinely impossible rates trip it.
IMPLAUSIBLE_SLOTS_PER_SECOND = 10.0

#: Bounded same-session recovery attempts before the gap is declared failed.
DEFAULT_MAX_RECOVERY_ATTEMPTS = 3

# -- provider-query coverage proof (orthogonal to recovery lifecycle) -------
#
# A gap can contain zero matching transactions.  ``COMPLETE`` therefore means
# the bounded provider query proved the entire inclusive slot range was
# exhausted; it never means merely "some rows were returned".
COVERAGE_NOT_REQUESTED = "NOT_REQUESTED"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_COMPLETE = "COMPLETE"
COVERAGE_FAILED = "FAILED"
RECOVERY_COVERAGE_STATUSES = (
    COVERAGE_NOT_REQUESTED,
    COVERAGE_PARTIAL,
    COVERAGE_COMPLETE,
    COVERAGE_FAILED,
)
MAX_RECOVERY_EVIDENCE = 4096


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _is_slot(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0)


def normalize_ranges(
    ranges: Sequence[Sequence[int]],
) -> List[Tuple[int, int]]:
    """Merge overlapping/adjacent inclusive ranges into a canonical list.

    This is what makes duplicate and out-of-order slot delivery idempotent: the
    same slot applied twice, or applied late, collapses into the identical
    canonical coverage set.
    """

    clean: List[Tuple[int, int]] = []
    for item in ranges or ():
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        lo, hi = item[0], item[1]
        if not _is_slot(lo) or not _is_slot(hi) or hi < lo:
            continue
        clean.append((int(lo), int(hi)))
    if not clean:
        return []
    clean.sort()
    merged: List[Tuple[int, int]] = [clean[0]]
    for lo, hi in clean[1:]:
        plo, phi = merged[-1]
        if lo <= phi + 1:
            merged[-1] = (plo, max(phi, hi))
        else:
            merged.append((lo, hi))
    return merged


def subtract_ranges(
    span: Tuple[int, int], covered: Sequence[Sequence[int]],
) -> List[Tuple[int, int]]:
    """Inclusive ``span`` minus ``covered``; the still-unproven remainder."""

    lo, hi = int(span[0]), int(span[1])
    if hi < lo:
        return []
    out: List[Tuple[int, int]] = []
    cursor = lo
    for clo, chi in normalize_ranges(covered):
        if chi < cursor:
            continue
        if clo > hi:
            break
        if clo > cursor:
            out.append((cursor, min(hi, clo - 1)))
        cursor = max(cursor, chi + 1)
        if cursor > hi:
            break
    if cursor <= hi:
        out.append((cursor, hi))
    return out


@dataclass
class SourceGap:
    """One durable, authenticated record of a proven coverage discontinuity."""

    gap_id: str
    detected_at_utc: str
    disconnect_reason_class: str
    last_received_slot: Optional[int]
    last_processed_slot: Optional[int]
    last_durable_slot: Optional[int]
    expected_next_slot: int
    first_post_reconnect_slot: int
    gap_from_slot: int
    gap_to_slot: int
    gap_size_slots: int
    requested_recovery_from_slot: Optional[int] = None
    recovery_status: str = GAP_DETECTED
    covered_ranges: List[List[int]] = field(default_factory=list)
    unresolved_ranges: List[List[int]] = field(default_factory=list)
    recovery_attempts: int = 0
    last_failure_reason: str = FAILURE_NONE
    epoch_before: Optional[str] = None
    epoch_after: Optional[str] = None
    epoch_boundary_before: Optional[int] = None
    epoch_boundary_after: Optional[int] = None
    candidates_closed_by_gap: int = 0
    implausible_jump: bool = False
    observed_jump_slots_per_second: Optional[float] = None
    resolved_at_utc: Optional[str] = None
    recovery_coverage_status: str = COVERAGE_NOT_REQUESTED
    recovered_signatures: List[str] = field(default_factory=list)
    recovered_slots: List[int] = field(default_factory=list)

    def to_record(self) -> Dict[str, Any]:
        record = asdict(self)
        record["covered_ranges"] = [list(r) for r in
                                    normalize_ranges(self.covered_ranges)]
        record["unresolved_ranges"] = [list(r) for r in
                                       normalize_ranges(self.unresolved_ranges)]
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "SourceGap":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in dict(record).items() if k in known})

    def recompute_unresolved(self) -> None:
        self.covered_ranges = [list(r) for r in
                               normalize_ranges(self.covered_ranges)]
        self.unresolved_ranges = [
            list(r) for r in
            subtract_ranges((self.gap_from_slot, self.gap_to_slot),
                            self.covered_ranges)]

    @property
    def unresolved_slot_count(self) -> int:
        return sum(hi - lo + 1 for lo, hi in
                   normalize_ranges(self.unresolved_ranges))

    @property
    def is_proven_continuous(self) -> bool:
        return self.recovery_status == RECOVERED and not self.unresolved_ranges


class SourceContinuityTracker:
    """Thread-safe canonical continuity tracker with a durable gap document.

    Slot bookkeeping is monotonic and duplicate-tolerant.  ``note_slot`` may be
    called with the same slot repeatedly or with a slot below the high-water
    mark (out-of-order delivery) without corrupting the record: the high-water
    marks only ever advance, and replayed slots inside an open gap contribute
    to its covered ranges regardless of arrival order.
    """

    def __init__(
        self,
        *,
        state_path: object = None,
        now_fn=None,
        max_recovery_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    ) -> None:
        self._lock = threading.RLock()
        self._path = Path(str(state_path)) if state_path is not None else None
        self._now_fn = now_fn
        self._max_recovery_attempts = max(1, int(max_recovery_attempts))
        self._last_received_slot: Optional[int] = None
        self._last_processed_slot: Optional[int] = None
        self._last_durable_slot: Optional[int] = None
        self._gaps: List[SourceGap] = []
        self._generation = 0
        self._previous_digest: Optional[str] = None
        self._awaiting_first_slot = False
        self._pending_reason = REASON_UNKNOWN
        self._pending_disconnect_at: Optional[float] = None
        self._gap_detected_total = 0
        self._gap_closed_total = 0
        self._write_failures = 0

    # -- clock -------------------------------------------------------------

    def _now_iso(self) -> str:
        if self._now_fn is not None:
            return str(self._now_fn())
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _monotonic(self) -> float:
        import time
        return time.monotonic()

    # -- slot bookkeeping --------------------------------------------------

    def note_slot(self, slot: object, *, processed: bool = False,
                  durable: bool = False) -> Optional[SourceGap]:
        """Record one observed slot; returns a gap if this slot opened one.

        The FIRST slot seen after a disconnect is the continuity checkpoint.
        Everything else only advances high-water marks and, when a gap is open,
        contributes coverage.
        """

        if not _is_slot(slot):
            return None
        value = int(slot)
        with self._lock:
            opened: Optional[SourceGap] = None
            if self._awaiting_first_slot:
                opened = self._evaluate_reconnect_locked(value)
                self._awaiting_first_slot = False
            if self._last_received_slot is None \
                    or value > self._last_received_slot:
                self._last_received_slot = value
            if processed and (self._last_processed_slot is None
                              or value > self._last_processed_slot):
                self._last_processed_slot = value
            if durable and (self._last_durable_slot is None
                            or value > self._last_durable_slot):
                self._last_durable_slot = value
            if processed:
                self._apply_coverage_locked(value, value)
            if opened is not None:
                self._persist_locked()
            return opened

    def note_durable_slot(self, slot: object) -> None:
        if not _is_slot(slot):
            return
        with self._lock:
            value = int(slot)
            if self._last_durable_slot is None \
                    or value > self._last_durable_slot:
                self._last_durable_slot = value

    def _apply_coverage_locked(self, lo: int, hi: int) -> None:
        for gap in self._gaps:
            if gap.recovery_status in (RECOVERED,):
                continue
            if hi < gap.gap_from_slot or lo > gap.gap_to_slot:
                continue
            clipped = (max(lo, gap.gap_from_slot), min(hi, gap.gap_to_slot))
            gap.covered_ranges = [list(r) for r in normalize_ranges(
                list(gap.covered_ranges) + [list(clipped)])]
            gap.recompute_unresolved()
            if not gap.unresolved_ranges:
                gap.recovery_status = RECOVERED
                gap.resolved_at_utc = self._now_iso()
                self._gap_closed_total += 1
            elif gap.recovery_status in (RECOVERY_REQUESTED, RECOVERING):
                gap.recovery_status = RECOVERING

    def apply_recovered_range(self, lo: object, hi: object) -> None:
        """Credit a proven-processed inclusive range to any open gap."""

        if not _is_slot(lo) or not _is_slot(hi) or int(hi) < int(lo):
            return
        with self._lock:
            self._apply_coverage_locked(int(lo), int(hi))
            self._persist_locked()

    def record_recovery_evidence(
        self,
        *,
        gap_id: str,
        signatures: Sequence[object] = (),
        slots: Sequence[object] = (),
        coverage_status: str = COVERAGE_PARTIAL,
    ) -> None:
        """Persist bounded exact recovery identities without closing the gap.

        Coverage and returned rows are distinct evidence.  A valid empty-range
        proof records ``COMPLETE`` with empty identity lists; partial pages may
        record rows while the unresolved range remains open.
        """

        safe_status = (
            coverage_status
            if coverage_status in RECOVERY_COVERAGE_STATUSES
            else COVERAGE_FAILED
        )
        safe_signatures = [
            value for value in signatures
            if isinstance(value, str) and 1 <= len(value) <= 128
        ][:MAX_RECOVERY_EVIDENCE]
        safe_slots = [
            int(value) for value in slots if _is_slot(value)
        ][:MAX_RECOVERY_EVIDENCE]
        with self._lock:
            for gap in self._gaps:
                if gap.gap_id != gap_id:
                    continue
                merged_signatures = list(dict.fromkeys(
                    list(gap.recovered_signatures) + safe_signatures
                ))
                gap.recovered_signatures = merged_signatures[
                    -MAX_RECOVERY_EVIDENCE:
                ]
                gap.recovered_slots = sorted(set(
                    list(gap.recovered_slots) + [
                        value for value in safe_slots
                        if gap.gap_from_slot <= value <= gap.gap_to_slot
                    ]
                ))[-MAX_RECOVERY_EVIDENCE:]
                gap.recovery_coverage_status = safe_status
            self._persist_locked()

    # -- reconnect lifecycle ----------------------------------------------

    def note_disconnect(self, *, reason_class: str = REASON_UNKNOWN) -> None:
        """Arm the continuity check for the next stream attempt."""

        with self._lock:
            safe = (reason_class if reason_class in DISCONNECT_REASON_CLASSES
                    else REASON_UNKNOWN)
            self._awaiting_first_slot = True
            self._pending_reason = safe
            self._pending_disconnect_at = self._monotonic()

    def _evaluate_reconnect_locked(self, first_slot: int) -> Optional[SourceGap]:
        anchor = self._last_processed_slot
        if anchor is None:
            anchor = self._last_durable_slot
        if anchor is None:
            # Nothing was ever proven covered: a fresh subscription claims no
            # prior ground, so there is no discontinuity to report.
            return None
        expected_next = int(anchor) + 1
        if first_slot <= expected_next:
            # Exact continuation, or a duplicate/replayed slot at or below the
            # anchor. Neither is a gap.
            return None
        gap_from = expected_next
        gap_to = first_slot - 1
        size = gap_to - gap_from + 1
        elapsed = None
        if self._pending_disconnect_at is not None:
            elapsed = max(0.0, self._monotonic() - self._pending_disconnect_at)
        rate = (float(size) / elapsed) if elapsed and elapsed > 0 else None
        seed = {
            "from": gap_from, "to": gap_to,
            "reason": self._pending_reason,
            "generation": self._generation + 1,
        }
        gap = SourceGap(
            gap_id="gap_" + _digest(seed)[:20],
            detected_at_utc=self._now_iso(),
            disconnect_reason_class=self._pending_reason,
            last_received_slot=self._last_received_slot,
            last_processed_slot=self._last_processed_slot,
            last_durable_slot=self._last_durable_slot,
            expected_next_slot=expected_next,
            first_post_reconnect_slot=first_slot,
            gap_from_slot=gap_from,
            gap_to_slot=gap_to,
            gap_size_slots=size,
            recovery_status=GAP_DETECTED,
            implausible_jump=bool(
                rate is not None and rate > IMPLAUSIBLE_SLOTS_PER_SECOND),
            observed_jump_slots_per_second=(
                round(rate, 3) if rate is not None else None),
        )
        gap.recompute_unresolved()
        self._gaps.append(gap)
        self._gap_detected_total += 1
        return gap

    # -- recovery ----------------------------------------------------------

    def open_gaps(self) -> List[SourceGap]:
        with self._lock:
            return [g for g in self._gaps if g.recovery_status != RECOVERED]

    def safe_recovery_slot(self) -> Optional[int]:
        """Earliest slot still owed across every open gap."""

        with self._lock:
            starts = [min(r[0] for r in normalize_ranges(g.unresolved_ranges))
                      for g in self._gaps
                      if g.recovery_status != RECOVERED and g.unresolved_ranges]
            return min(starts) if starts else None

    def replay_request(self) -> Optional[Tuple[str, int]]:
        """The next ``(gap_id, from_slot)`` a same-session replay should ask for.

        Returns ``None`` when there is nothing to request: no open gap, every
        open gap already declared unavailable/failed, or the bounded attempt
        budget for each remaining gap is spent.  The slot is the EARLIEST
        still-unproven slot of that gap, so a partially recovered range asks
        only for the remainder and a refused attempt never re-requests ground
        that was already proven.

        A ``None`` answer is what keeps the live-only startup policy intact:
        with no open gap the owner still bootstraps at the provider's live
        head exactly as before.
        """

        with self._lock:
            for gap in self._gaps:
                if gap.recovery_status in (
                        RECOVERED, RECOVERY_UNAVAILABLE, RECOVERY_FAILED):
                    continue
                if gap.recovery_attempts >= self._max_recovery_attempts:
                    continue
                ranges = normalize_ranges(gap.unresolved_ranges)
                if not ranges:
                    continue
                return gap.gap_id, int(ranges[0][0])
            return None

    def mark_recovery_requested(self, gap_id: str, from_slot: object) -> None:
        with self._lock:
            for gap in self._gaps:
                if gap.gap_id != gap_id:
                    continue
                gap.requested_recovery_from_slot = (
                    int(from_slot) if _is_slot(from_slot) else None)
                gap.recovery_attempts += 1
                gap.recovery_status = RECOVERY_REQUESTED
            self._persist_locked()

    def mark_recovery_failed(self, gap_id: str, *,
                             reason: str = FAILURE_NONE,
                             unavailable: bool = False) -> None:
        with self._lock:
            safe = reason if reason in RECOVERY_FAILURE_REASONS else FAILURE_NONE
            for gap in self._gaps:
                if gap.gap_id != gap_id or gap.recovery_status == RECOVERED:
                    continue
                gap.last_failure_reason = safe
                if unavailable:
                    gap.recovery_status = RECOVERY_UNAVAILABLE
                elif gap.recovery_attempts >= self._max_recovery_attempts:
                    gap.recovery_status = RECOVERY_FAILED
                elif gap.covered_ranges:
                    gap.recovery_status = PARTIALLY_RECOVERED
                else:
                    gap.recovery_status = UNRESOLVED
            self._persist_locked()

    def note_epoch_rollover(self, *, epoch_before: Optional[str],
                            epoch_after: Optional[str],
                            boundary_before: object = None,
                            boundary_after: object = None) -> None:
        """Bind epoch identity to every open gap.

        Rollover NEVER clears a gap. The re-arm is recorded as context on the
        existing evidence so a later reader can see exactly which epoch
        boundary jumped over which unproven range.
        """

        with self._lock:
            for gap in self._gaps:
                if gap.recovery_status == RECOVERED:
                    continue
                if gap.epoch_before is None:
                    gap.epoch_before = epoch_before
                gap.epoch_after = epoch_after
                if gap.epoch_boundary_before is None and _is_slot(boundary_before):
                    gap.epoch_boundary_before = int(boundary_before)
                if _is_slot(boundary_after):
                    gap.epoch_boundary_after = int(boundary_after)
            self._persist_locked()

    def note_candidates_closed_by_gap(self, count: object) -> None:
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return
        with self._lock:
            open_gaps = [g for g in self._gaps
                         if g.recovery_status != RECOVERED]
            if not open_gaps:
                return
            open_gaps[-1].candidates_closed_by_gap += int(count)
            self._persist_locked()

    # -- aggregate state ---------------------------------------------------

    def continuity_state(self) -> str:
        with self._lock:
            open_gaps = [g for g in self._gaps
                         if g.recovery_status != RECOVERED]
            if not open_gaps:
                return NO_GAP
            order = (RECOVERY_FAILED, RECOVERY_UNAVAILABLE, UNRESOLVED,
                     PARTIALLY_RECOVERED, RECOVERING, RECOVERY_REQUESTED,
                     GAP_DETECTED)
            for state in order:
                if any(g.recovery_status == state for g in open_gaps):
                    return state
            return GAP_DETECTED

    def coverage_is_proven_continuous(self) -> bool:
        return self.continuity_state() == NO_GAP

    def recovered_ranges(self) -> List[Tuple[int, int]]:
        """Every inclusive range this tracker has PROVEN covered after a gap.

        Exposed separately from the gap list so a status surface can state what
        was actually recovered without a reader having to reconstruct it from
        per-gap records.
        """

        with self._lock:
            spans: List[List[int]] = []
            for gap in self._gaps:
                spans.extend(list(item) for item in
                             normalize_ranges(gap.covered_ranges))
            return normalize_ranges(spans)

    def unresolved_ranges(self) -> List[Tuple[int, int]]:
        """Every inclusive range still owed across all open gaps."""

        with self._lock:
            spans: List[List[int]] = []
            for gap in self._gaps:
                if gap.recovery_status == RECOVERED:
                    continue
                spans.extend(list(item) for item in
                             normalize_ranges(gap.unresolved_ranges))
            return normalize_ranges(spans)

    def snapshot(self) -> Dict[str, Any]:
        recovered = self.recovered_ranges()
        unresolved = self.unresolved_ranges()
        with self._lock:
            open_gaps = [g for g in self._gaps
                         if g.recovery_status != RECOVERED]
            unresolved_slots = sum(g.unresolved_slot_count for g in open_gaps)
            return {
                "recovered_ranges": [list(item) for item in recovered],
                "unresolved_ranges": [list(item) for item in unresolved],
                "schema_version": SCHEMA_VERSION,
                "continuity_state": self.continuity_state(),
                "coverage_proven_continuous":
                    self.coverage_is_proven_continuous(),
                "last_received_slot": self._last_received_slot,
                "last_processed_slot": self._last_processed_slot,
                "last_durable_slot": self._last_durable_slot,
                "gap_detected_total": self._gap_detected_total,
                "gap_closed_total": self._gap_closed_total,
                "open_gap_count": len(open_gaps),
                "unresolved_slot_total": unresolved_slots,
                "gap_from_slot": (open_gaps[0].gap_from_slot
                                  if open_gaps else None),
                "gap_to_slot": open_gaps[0].gap_to_slot if open_gaps else None,
                "gap_size_slots": (open_gaps[0].gap_size_slots
                                   if open_gaps else None),
                "gap_id": open_gaps[0].gap_id if open_gaps else None,
                "implausible_jump": any(g.implausible_jump for g in open_gaps),
                "generation": self._generation,
                "document_write_failures": self._write_failures,
                "gaps": [g.to_record() for g in self._gaps[-16:]],
            }

    # -- durability --------------------------------------------------------

    def _document_locked(self) -> Dict[str, Any]:
        payload = {
            "kind": DOCUMENT_KIND,
            "schema_version": SCHEMA_VERSION,
            "generation": self._generation + 1,
            "previous_generation_digest": self._previous_digest,
            "updated_at_utc": self._now_iso(),
            "last_received_slot": self._last_received_slot,
            "last_processed_slot": self._last_processed_slot,
            "last_durable_slot": self._last_durable_slot,
            "gap_detected_total": self._gap_detected_total,
            "gap_closed_total": self._gap_closed_total,
            "gaps": [g.to_record() for g in self._gaps],
        }
        payload["document_digest"] = _digest(payload)
        return payload

    def _persist_locked(self) -> None:
        if self._path is None:
            self._generation += 1
            return
        payload = self._document_locked()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".next.tmp")
            data = _canonical_bytes(payload)
            with tmp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self._path.exists():
                backup = self._path.with_name(self._path.name + ".bak")
                try:
                    os.replace(self._path, backup)
                except OSError:
                    pass
            os.replace(tmp, self._path)
        except OSError:
            # Durability failure never interferes with ingestion; the
            # in-memory gap stays authoritative and the counter is surfaced.
            self._write_failures += 1
            return
        self._generation = int(payload["generation"])
        self._previous_digest = str(payload["document_digest"])

    def persist(self) -> None:
        with self._lock:
            self._persist_locked()

    def load(self) -> bool:
        """Restore a previously persisted document; False when unavailable."""

        if self._path is None or not self._path.exists():
            return False
        for candidate in (self._path,
                          self._path.with_name(self._path.name + ".bak")):
            try:
                raw = candidate.read_bytes().decode("utf-8")
                payload = json.loads(raw)
            except (OSError, ValueError, UnicodeError):
                continue
            if not isinstance(payload, dict) \
                    or payload.get("kind") != DOCUMENT_KIND:
                continue
            supplied = payload.get("document_digest")
            check = {k: v for k, v in payload.items() if k != "document_digest"}
            if not isinstance(supplied, str) or _digest(check) != supplied:
                continue
            with self._lock:
                self._last_received_slot = payload.get("last_received_slot")
                self._last_processed_slot = payload.get("last_processed_slot")
                self._last_durable_slot = payload.get("last_durable_slot")
                self._gap_detected_total = int(
                    payload.get("gap_detected_total") or 0)
                self._gap_closed_total = int(
                    payload.get("gap_closed_total") or 0)
                self._gaps = [SourceGap.from_record(r)
                              for r in payload.get("gaps") or []
                              if isinstance(r, Mapping)]
                self._generation = int(payload.get("generation") or 0)
                self._previous_digest = supplied
            return True
        return False


def display_status_for(
    *, transport_connected: bool, continuity_state: str,
) -> str:
    """Stream display status that can never launder a gap into 'healthy'."""

    if not transport_connected:
        return "DISCONNECTED"
    if continuity_state == NO_GAP:
        return "CONNECTED_LIVE_HEALTHY"
    if continuity_state in TERMINAL_GAP_STATES:
        return "CONNECTED_COVERAGE_UNRESOLVED"
    return "CONNECTED_COVERAGE_RECOVERING"
