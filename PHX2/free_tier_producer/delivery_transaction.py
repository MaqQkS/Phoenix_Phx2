"""PHX2 delivery transaction state machine (PHX2-E2E-001 correction).

Production previously appended the durable successful-send dedupe row at
compose time (reserve-before-send), so a failed / interrupted Telegram attempt
permanently suppressed the alert. This module makes the delivery a real
transaction with explicit states:

    ATTEMPT_RESERVED          bounded lease; NOT a successful-send record
    TRANSPORT_IN_PROGRESS     a transport call began; NOT terminal success
    DELIVERY_FAILED_RETRYABLE transport explicitly reported no delivery;
                              lease released; candidate stays retryable
    DELIVERY_UNKNOWN          ambiguous outcome after dispatch; observable,
                              never silently converted to success or retried
    SENT_OK_COMMITTED         confirmed transport_ok=True + durable receipt +
                              exactly one successful-send ledger row

The durable successful-send ledger (Stage 30.11.15) now represents confirmed
SENT_OK only: the row is appended by ``commit_confirmed_send`` AFTER the
transport confirms delivery, or during restart reconciliation from a durable
confirmed-success receipt. Attempt/outbox state lives in a SEPARATE journal
(``DeliveryAttemptJournal``) with its own schema and lease semantics.

Every record in the journal carries a sha256 self-digest; a tampered record
fails the journal closed (no new lease, no receipt-driven commit). All
timestamps are caller-injected ISO-8601 -- this module never reads a wall
clock, opens no network connection, and never touches the real production
ledgers itself (the caller injects the ledger instance).

Journal authority (PHX2-E2E-001 / PHX2-E2E-009 correction)
----------------------------------------------------------
The journal owns the legal-transition contract; presence of a field is never
evidence of a transition. Two invariants are enforced structurally:

1. NO DURABLE TRANSPORT-START RECORD -> NO TRANSPORT INVOCATION.
   ``record_transport_started`` returns a ``JournalWriteResult`` whose
   ``dispatch_authorized`` flag is the ONLY authority permitting a transport
   call. A false return, write exception, fsync failure, read-back mismatch,
   binding mismatch or unavailable journal leaves the transport UNCALLED --
   otherwise a delivery could happen with no durable evidence and a later
   restart would dispatch it a SECOND time.

2. A receipt is valid only with a durable, binding-consistent
   TRANSPORT_IN_PROGRESS predecessor. ``LEASED -> RECEIPT`` is refused and,
   if such a sequence is already durable on disk, it is quarantined as
   ``DELIVERY_RECEIPT_SEQUENCE_INVALID`` -- never SENT_OK, never a
   successful-send ledger row.

Only a LEASED attempt WITHOUT a transport-start record may be released by
normal lease expiry. An attempt that reached TRANSPORT_IN_PROGRESS without a
recognized receipt stays DELIVERY_UNKNOWN and is operator-held: automatically
releasing it would recreate duplicate risk after a real remote success whose
response was lost.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DELIVERY_OUTBOX_SCHEMA_VERSION = "phx2_delivery_outbox_v1"

# Delivery transaction states (closed set).
DELIVERY_STATE_ATTEMPT_RESERVED = "ATTEMPT_RESERVED"
DELIVERY_STATE_TRANSPORT_IN_PROGRESS = "TRANSPORT_IN_PROGRESS"
DELIVERY_STATE_FAILED_RETRYABLE = "DELIVERY_FAILED_RETRYABLE"
DELIVERY_STATE_UNKNOWN = "DELIVERY_UNKNOWN"
DELIVERY_STATE_SENT_OK_COMMITTED = "SENT_OK_COMMITTED"
DELIVERY_STATE_COMMIT_PENDING = "SENT_OK_COMMIT_PENDING"
DELIVERY_STATE_ABORTED_BEFORE_TRANSPORT = "ATTEMPT_ABORTED_BEFORE_TRANSPORT"
DELIVERY_STATE_LEASE_HELD = "ATTEMPT_LEASE_HELD"
DELIVERY_STATE_RELEASED = "ATTEMPT_RELEASED"
# The durable transport-start record could not be written, so NO transport call
# was made. Distinct from every transport-failure state: nothing reached the
# wire, so this must never render as a Telegram failure or as a sent state.
DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL = "DELIVERY_DISPATCH_BLOCKED_JOURNAL_FAILURE"
# A durable receipt exists with no legal TRANSPORT_IN_PROGRESS predecessor (or
# with a conflicting second receipt): quarantined, never committable.
DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID = "DELIVERY_RECEIPT_SEQUENCE_INVALID"

# Closed-set refusal reasons emitted before any transport call (PHX2-E2E-001).
REFUSAL_TRANSPORT_START_PERSIST_FAILED = "DELIVERY_TRANSPORT_START_PERSIST_FAILED"
REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH = (
    "DELIVERY_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH")
# Closed-set receipt refusals (PHX2-E2E-009).
REFUSAL_RECEIPT_PREDECESSOR_INVALID = "DELIVERY_RECEIPT_PREDECESSOR_INVALID"
REFUSAL_RECEIPT_BINDING_MISMATCH = "DELIVERY_RECEIPT_BINDING_MISMATCH"
REFUSAL_RECEIPT_CONFLICT = "DELIVERY_RECEIPT_CONFLICT"
# Confirmed delivery whose receipt could not be persisted: operator-held.
REFUSAL_RECEIPT_PERSIST_FAILED = "DELIVERY_RECEIPT_PERSIST_FAILED"

# Journal mutation result statuses (closed set).
WRITE_PERSISTED = "PERSISTED"
WRITE_ALREADY_PERSISTED = "ALREADY_PERSISTED"
WRITE_ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
WRITE_BINDING_MISMATCH = "BINDING_MISMATCH"
WRITE_JOURNAL_UNAVAILABLE = "JOURNAL_UNAVAILABLE"
WRITE_FAILED = "WRITE_FAILED"
WRITE_READBACK_FAILED = "READBACK_FAILED"
WRITE_CONFLICT = "CONFLICT"

_DURABLE_WRITE_STATUSES = frozenset((WRITE_PERSISTED, WRITE_ALREADY_PERSISTED))

# Safe observability counters (no payloads, no credentials, no raw journal).
COUNTER_START_ATTEMPTED = "delivery_transport_start_persist_attempted_total"
COUNTER_START_PERSISTED = "delivery_transport_start_persisted_total"
COUNTER_START_FAILED = "delivery_transport_start_persist_failed_total"
COUNTER_DISPATCH_BLOCKED = "delivery_dispatch_blocked_journal_failure_total"
COUNTER_RECEIPT_PREDECESSOR_INVALID = "delivery_receipt_predecessor_invalid_total"
COUNTER_RECEIPT_BINDING_MISMATCH = "delivery_receipt_binding_mismatch_total"
COUNTER_RECEIPT_CONFLICT = "delivery_receipt_conflict_total"
COUNTER_RESTART_UNKNOWN_TRANSPORT = "delivery_restart_unknown_transport_total"
COUNTER_RESTART_INVALID_SEQUENCE = "delivery_restart_invalid_sequence_total"
COUNTER_SUCCESS_COMMIT_RECONCILED = "delivery_success_commit_reconciled_total"

_COUNTER_NAMES = (
    COUNTER_START_ATTEMPTED,
    COUNTER_START_PERSISTED,
    COUNTER_START_FAILED,
    COUNTER_DISPATCH_BLOCKED,
    COUNTER_RECEIPT_PREDECESSOR_INVALID,
    COUNTER_RECEIPT_BINDING_MISMATCH,
    COUNTER_RECEIPT_CONFLICT,
    COUNTER_RESTART_UNKNOWN_TRANSPORT,
    COUNTER_RESTART_INVALID_SEQUENCE,
    COUNTER_SUCCESS_COMMIT_RECONCILED,
)


@dataclass(frozen=True)
class JournalWriteResult:
    """Typed outcome of ONE journal mutation (closed ``status`` set).

    ``bool(result)`` is True only for a durably persisted record (or a
    byte-identical record already durable), preserving the previous boolean
    call contract. ``dispatch_authorized`` is deliberately NARROWER: it is True
    only for a freshly persisted, read-back-verified transport-start record, so
    an idempotent replay can never re-authorize a second transport call."""

    status: str
    detail: str = ""
    dispatch_authorized: bool = False

    def __bool__(self) -> bool:
        return self.status in _DURABLE_WRITE_STATUSES

    @property
    def persisted(self) -> bool:
        return self.status in _DURABLE_WRITE_STATUSES

# Journal event tokens (closed set).
EVENT_ATTEMPT_RESERVED = "ATTEMPT_RESERVED"
EVENT_TRANSPORT_IN_PROGRESS = "TRANSPORT_IN_PROGRESS"
EVENT_DELIVERY_FAILED_RETRYABLE = "DELIVERY_FAILED_RETRYABLE"
EVENT_DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
EVENT_DELIVERY_RECEIPT = "DELIVERY_RECEIPT"
EVENT_SENT_OK_COMMITTED = "SENT_OK_COMMITTED"
EVENT_LEASE_RELEASED = "LEASE_RELEASED"

_JOURNAL_EVENTS = frozenset((
    EVENT_ATTEMPT_RESERVED,
    EVENT_TRANSPORT_IN_PROGRESS,
    EVENT_DELIVERY_FAILED_RETRYABLE,
    EVENT_DELIVERY_UNKNOWN,
    EVENT_DELIVERY_RECEIPT,
    EVENT_SENT_OK_COMMITTED,
    EVENT_LEASE_RELEASED,
))

# Transport classification (closed set).
CLASSIFY_CONFIRMED_OK = "CONFIRMED_OK"
CLASSIFY_FAILED_RETRYABLE = "FAILED_RETRYABLE"
CLASSIFY_UNKNOWN = "UNKNOWN"
CLASSIFY_NOT_ATTEMPTED = "NOT_ATTEMPTED"

# A transport verdict with one of these statuses may mean "delivered but the
# response/confirmation was lost" -- it must NEVER be treated as a proven
# no-delivery, so it maps to DELIVERY_UNKNOWN rather than a silent retry.
AMBIGUOUS_TRANSPORT_STATUSES = frozenset((
    "TIMEOUT",
    "NETWORK_ERROR",
    "MALFORMED_RESPONSE",
    "UNKNOWN_FAILURE",
))

# Lease / retry policy defaults (deterministic; injected clocks only).
DEFAULT_ATTEMPT_LEASE_SECONDS = 900
DEFAULT_RETRY_BACKOFF_BASE_SECONDS = 60
DEFAULT_RETRY_BACKOFF_MAX_SECONDS = 3600

RELEASE_REASON_EXPLICIT_FAILURE = "EXPLICIT_TRANSPORT_FAILURE"
RELEASE_REASON_GUARD_REFUSED = "GUARD_REFUSED_BEFORE_TRANSPORT"
RELEASE_REASON_LEASE_EXPIRED_STALE = "LEASE_EXPIRED_STALE"
RELEASE_REASON_OPERATOR_NOT_DELIVERED = "OPERATOR_RESOLVED_NOT_DELIVERED"

RECONCILE_INTERRUPTED_TRANSPORT = "RECONCILED_INTERRUPTED_TRANSPORT"

_DEDUPE_KEY_FIELDS = (
    "token_mint", "operator_signal_kind", "tier_token", "drawdown_band",
    "post_migration_ath_verified", "ath_source_stage", "policy_version",
)


def _parse_iso_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def dedupe_key_to_dict(key: Any) -> Optional[Dict[str, Any]]:
    """Project a Stage 30.11.15 dedupe key onto a plain field map (duck-typed);
    ``None`` on any missing field. Pure / total."""
    out: Dict[str, Any] = {}
    for name in _DEDUPE_KEY_FIELDS:
        value = getattr(key, name, None)
        if name == "post_migration_ath_verified":
            if not isinstance(value, bool):
                return None
        elif not isinstance(value, str) or not value.strip():
            return None
        out[name] = value
    return out


def _canonical_digest(record: Dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def snapshot_body_digest(body: object) -> Optional[str]:
    if not isinstance(body, str) or not body:
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _coerce_generation(value: object) -> int:
    """Delivery generation as a non-negative int; anything malformed folds to
    0 so a corrupt field can never silently match a different generation."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value >= 0 else 0


_RECEIPT_IDENTITY_FIELDS = (
    "token_mint", "candidate_id", "tier_token", "dedupe_key",
    "snapshot_body_sha256", "delivery_generation", "message_id",
    "transport_status",
)


def _same_receipt(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """Delivery identity equality for idempotence. ``recorded_at_utc`` is
    excluded: a replayed identical receipt is the same delivery even when the
    injected clock advanced."""
    return all(left.get(name) == right.get(name)
               for name in _RECEIPT_IDENTITY_FIELDS)


def classify_transport_result(send_result: Any) -> str:
    """Classify a Stage 30.11.16 guard result into the closed delivery set.

    * no transport attempt reached the wire -> NOT_ATTEMPTED
    * transport_ok is True                  -> CONFIRMED_OK
    * transport_ok is False, status proves an explicit no-delivery
                                            -> FAILED_RETRYABLE
    * transport_ok is False with an ambiguous status, or transport_ok is None
      after an attempt (exception / non-bool verdict) -> UNKNOWN

    Pure / total; never raises. Never fabricates success.
    """
    if send_result is None:
        return CLASSIFY_NOT_ATTEMPTED
    attempted = getattr(send_result, "transport_attempted", None)
    if attempted is not True:
        return CLASSIFY_NOT_ATTEMPTED
    ok = getattr(send_result, "transport_ok", None)
    if ok is True:
        return CLASSIFY_CONFIRMED_OK
    status = getattr(send_result, "transport_status", None)
    if ok is False:
        if isinstance(status, str) and status in AMBIGUOUS_TRANSPORT_STATUSES:
            return CLASSIFY_UNKNOWN
        return CLASSIFY_FAILED_RETRYABLE
    return CLASSIFY_UNKNOWN


def compute_retry_backoff_seconds(
    retry_count: int,
    *,
    base_seconds: int = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: int = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
) -> int:
    """Bounded deterministic exponential backoff: base * 2^retry_count, capped."""
    try:
        n = max(0, int(retry_count))
    except (TypeError, ValueError):
        n = 0
    value = base_seconds * (2 ** min(n, 16))
    return int(min(max_seconds, value))


def next_retry_at_utc(
    *,
    now_utc: str,
    retry_count: int,
    base_seconds: int = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: int = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
) -> Optional[str]:
    now = _parse_iso_utc(now_utc)
    if now is None:
        return None
    from datetime import timedelta
    return _iso(now + timedelta(seconds=compute_retry_backoff_seconds(
        retry_count, base_seconds=base_seconds, max_seconds=max_seconds)))


def retry_due(*, now_utc: str, next_retry_at: object) -> bool:
    """True when no retry timestamp exists or it is <= now. Malformed values
    fail OPEN for retryability (a broken timestamp must not strand a watch)."""
    scheduled = _parse_iso_utc(next_retry_at)
    if scheduled is None:
        return True
    now = _parse_iso_utc(now_utc)
    if now is None:
        return False
    return now >= scheduled


@dataclass
class _AttemptState:
    """Replay-derived state for one attempt_id."""

    attempt_id: str
    token_mint: str = ""
    candidate_id: str = ""
    tier_token: str = ""
    dedupe_key: Dict[str, Any] = field(default_factory=dict)
    snapshot_body_sha256: Optional[str] = None
    delivery_generation: int = 0
    reserved_at_utc: Optional[str] = None
    lease_expires_at_utc: Optional[str] = None
    transport_started: bool = False
    failed_retryable: bool = False
    unknown: bool = False
    receipt: Optional[Dict[str, Any]] = None
    # True only when the durable receipt was folded AFTER a durable
    # TRANSPORT_IN_PROGRESS record for the same attempt. This is replayed from
    # the on-disk ORDER, so a hand-forged LEASED -> RECEIPT journal cannot
    # present itself as a committable success.
    receipt_after_start: bool = False
    receipt_conflict: bool = False
    committed: bool = False
    released: bool = False
    release_reason: Optional[str] = None
    last_transport_status: Optional[str] = None

    def terminal(self) -> bool:
        return self.committed or self.released or self.failed_retryable

    def invalid_sequence(self) -> bool:
        """A durable receipt with no legal predecessor, or two conflicting
        receipts: quarantined, never committable, never auto-retried."""
        return self.receipt is not None and (
            not self.receipt_after_start or self.receipt_conflict)

    def lease_active(self, now_utc: str) -> bool:
        if self.terminal() or self.unknown:
            return False
        expires = _parse_iso_utc(self.lease_expires_at_utc)
        now = _parse_iso_utc(now_utc)
        if expires is None or now is None:
            return False
        return now < expires

    def state(self) -> str:
        if self.committed:
            return DELIVERY_STATE_SENT_OK_COMMITTED
        if self.invalid_sequence():
            return DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID
        if self.receipt is not None:
            return DELIVERY_STATE_COMMIT_PENDING
        if self.unknown:
            return DELIVERY_STATE_UNKNOWN
        if self.failed_retryable:
            return DELIVERY_STATE_FAILED_RETRYABLE
        if self.released:
            return DELIVERY_STATE_RELEASED
        if self.transport_started:
            return DELIVERY_STATE_TRANSPORT_IN_PROGRESS
        return DELIVERY_STATE_ATTEMPT_RESERVED


class DeliveryAttemptJournal:
    """Append-only JSONL attempt/outbox journal with bounded-lease semantics.

    Separate from -- and never a substitute for -- the successful-send dedupe
    ledger. Construction is total: a bad path / missing parent / tampered or
    malformed record leaves the journal UNAVAILABLE and every mutating call
    fails closed (no lease, no receipt, no commit marker). ``path=None`` builds
    an in-memory journal (no I/O; used by legacy offline call sites and unit
    fakes)."""

    def __init__(self, *, path: object = None) -> None:
        self._path: Optional[Path] = path if isinstance(path, Path) else None
        self._memory_only = path is None
        self._attempts: Dict[str, _AttemptState] = {}
        self._order: List[str] = []
        self._available = True
        self._unavailable_reason = ""
        self._counters: Dict[str, int] = {name: 0 for name in _COUNTER_NAMES}
        if path is None:
            return
        try:
            self._init_replay(path)
        except OSError:
            self._mark_unavailable("JOURNAL_UNAVAILABLE")

    # ---- construction / replay -------------------------------------------

    def _mark_unavailable(self, reason: str) -> None:
        self._available = False
        self._unavailable_reason = reason

    @property
    def available(self) -> bool:
        return self._available

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable_reason

    def _init_replay(self, path: object) -> None:
        if not isinstance(path, Path) or ".." in path.parts:
            self._mark_unavailable("JOURNAL_UNAVAILABLE")
            return
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            self._mark_unavailable("JOURNAL_UNAVAILABLE")
            return
        if path.exists() and not path.is_file():
            self._mark_unavailable("JOURNAL_UNAVAILABLE")
            return
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.rstrip("\n")
                if line.strip() == "":
                    self._mark_unavailable("JOURNAL_CORRUPT")
                    return
                if not self._apply_line(line):
                    self._mark_unavailable("JOURNAL_CORRUPT")
                    return

    def _apply_line(self, line: str) -> bool:
        try:
            record = json.loads(line)
        except ValueError:
            return False
        if not isinstance(record, dict):
            return False
        if record.get("schema_version") != DELIVERY_OUTBOX_SCHEMA_VERSION:
            return False
        digest = record.get("record_sha256")
        if not isinstance(digest, str) or digest != _canonical_digest(record):
            return False
        event = record.get("event")
        attempt_id = record.get("attempt_id")
        if event not in _JOURNAL_EVENTS or not isinstance(attempt_id, str) \
                or not attempt_id:
            return False
        self._fold(record)
        return True

    def _fold(self, record: Dict[str, Any]) -> None:
        attempt_id = record["attempt_id"]
        state = self._attempts.get(attempt_id)
        if state is None:
            state = _AttemptState(attempt_id=attempt_id)
            self._attempts[attempt_id] = state
            self._order.append(attempt_id)
        event = record["event"]
        if event == EVENT_ATTEMPT_RESERVED:
            state.token_mint = str(record.get("token_mint") or "")
            state.candidate_id = str(record.get("candidate_id") or "")
            state.tier_token = str(record.get("tier_token") or "")
            key = record.get("dedupe_key")
            state.dedupe_key = dict(key) if isinstance(key, dict) else {}
            digest = record.get("snapshot_body_sha256")
            state.snapshot_body_sha256 = (
                digest if isinstance(digest, str) else None)
            state.delivery_generation = _coerce_generation(
                record.get("delivery_generation"))
            state.reserved_at_utc = record.get("recorded_at_utc")
            state.lease_expires_at_utc = record.get("lease_expires_at_utc")
        elif event == EVENT_TRANSPORT_IN_PROGRESS:
            state.transport_started = True
        elif event == EVENT_DELIVERY_FAILED_RETRYABLE:
            state.failed_retryable = True
            state.last_transport_status = record.get("transport_status")
        elif event == EVENT_DELIVERY_UNKNOWN:
            state.unknown = True
            state.last_transport_status = record.get("transport_status")
        elif event == EVENT_DELIVERY_RECEIPT:
            folded = {
                "token_mint": record.get("token_mint"),
                "candidate_id": record.get("candidate_id"),
                "tier_token": record.get("tier_token"),
                "dedupe_key": (dict(record.get("dedupe_key"))
                               if isinstance(record.get("dedupe_key"), dict)
                               else {}),
                "snapshot_body_sha256": record.get("snapshot_body_sha256"),
                "delivery_generation": _coerce_generation(
                    record.get("delivery_generation")),
                "message_id": record.get("message_id"),
                "transport_status": record.get("transport_status"),
                "recorded_at_utc": record.get("recorded_at_utc"),
            }
            if state.receipt is None:
                # Replayed from the durable ORDER: a receipt folded before any
                # transport-start record can never be a committable success.
                state.receipt = folded
                state.receipt_after_start = state.transport_started
            elif not _same_receipt(state.receipt, folded):
                state.receipt_conflict = True
            state.last_transport_status = record.get("transport_status")
        elif event == EVENT_SENT_OK_COMMITTED:
            state.committed = True
        elif event == EVENT_LEASE_RELEASED:
            state.released = True
            state.release_reason = record.get("release_reason")

    # ---- writes ----------------------------------------------------------

    def note(self, name: str) -> None:
        """Increment a safe closed-set counter (unknown names are ignored)."""
        if name in self._counters:
            self._counters[name] += 1

    def counters(self) -> Dict[str, int]:
        return dict(self._counters)

    def _readback_ok(self, offset: int, line: str) -> bool:
        """Re-read the exact bytes just appended. A short/partial write or a
        truncated flush must NOT be reported as durable -- the transport-start
        authority depends on this being byte-exact."""
        try:
            with self._path.open("rb") as handle:
                handle.seek(offset)
                written = handle.read()
        except (OSError, ValueError):
            return False
        try:
            return written.decode("utf-8").rstrip("\r\n") == line
        except UnicodeDecodeError:
            return False

    def _append_result(self, record: Dict[str, Any]) -> JournalWriteResult:
        """Durably append one record: serialize -> append -> flush -> fsync ->
        read-back -> only THEN fold into memory. The in-memory state is never
        advanced ahead of the persistent write, so a failed append can never
        leave an attempt appearing as TRANSPORT_IN_PROGRESS."""
        record = dict(record)
        record["schema_version"] = DELIVERY_OUTBOX_SCHEMA_VERSION
        record["record_sha256"] = _canonical_digest(record)
        if not self._memory_only:
            line = json.dumps(record, sort_keys=True, separators=(",", ":"))
            try:
                offset = (self._path.stat().st_size
                          if self._path.exists() else 0)
                with self._path.open("a", encoding="utf-8", newline="") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except (OSError, ValueError):
                self._mark_unavailable("JOURNAL_WRITE_FAILED")
                return JournalWriteResult(WRITE_FAILED, "JOURNAL_WRITE_FAILED")
            if not self._readback_ok(offset, line):
                self._mark_unavailable("JOURNAL_READBACK_FAILED")
                return JournalWriteResult(
                    WRITE_READBACK_FAILED, "JOURNAL_READBACK_FAILED")
        self._fold(record)
        return JournalWriteResult(WRITE_PERSISTED)

    def _append(self, record: Dict[str, Any]) -> bool:
        """RAW durable append with no transition validation. Retained for the
        committed corrupt/tampered-journal probes that forge records directly;
        production transitions go through the validating ``record_*`` API."""
        return self._append_result(record).persisted

    # ---- key-level state -------------------------------------------------

    def _key_token(self, key_map: Dict[str, Any]) -> str:
        return json.dumps(key_map, sort_keys=True, separators=(",", ":"))

    def _attempts_for_key(self, key_map: Dict[str, Any]) -> List[_AttemptState]:
        token = self._key_token(key_map)
        return [self._attempts[a] for a in self._order
                if self._key_token(self._attempts[a].dedupe_key) == token]

    def active_lease_for_key(
        self, key_map: Dict[str, Any], *, now_utc: str
    ) -> Optional[_AttemptState]:
        for state in self._attempts_for_key(key_map):
            if state.lease_active(now_utc):
                return state
        return None

    def pending_unknown_for_key(
        self, key_map: Dict[str, Any]
    ) -> Optional[_AttemptState]:
        for state in self._attempts_for_key(key_map):
            if state.unknown and not state.committed and not state.released:
                return state
        return None

    def pending_invalid_sequence_for_key(
        self, key_map: Dict[str, Any]
    ) -> Optional[_AttemptState]:
        """An unresolved quarantined receipt sequence for this key. A new
        transport attempt is refused until an operator resolves it: the durable
        journal claims a delivery that its own ordering cannot substantiate."""
        for state in self._attempts_for_key(key_map):
            if state.invalid_sequence() and not state.committed \
                    and not state.released:
                return state
        return None

    def attempt(self, attempt_id: str) -> Optional[_AttemptState]:
        return self._attempts.get(attempt_id)

    def all_attempts(self) -> List[_AttemptState]:
        return [self._attempts[a] for a in self._order]

    def pending_commits(self) -> List[_AttemptState]:
        """Receipts that are legally committable. A quarantined invalid
        sequence is deliberately excluded: it is never pending a commit."""
        return [s for s in self.all_attempts()
                if s.receipt is not None and not s.committed
                and not s.invalid_sequence()]

    def invalid_sequences(self) -> List[_AttemptState]:
        return [s for s in self.all_attempts() if s.invalid_sequence()]

    def observable_states(self) -> List[Dict[str, Any]]:
        """Redaction-safe attempt states for status artifacts / operators."""
        out = []
        for state in self.all_attempts():
            out.append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "candidate_id": state.candidate_id,
                "tier_token": state.tier_token,
                "delivery_state": state.state(),
                "transport_status": state.last_transport_status,
                "reserved_at_utc": state.reserved_at_utc,
                "lease_expires_at_utc": state.lease_expires_at_utc,
                "release_reason": state.release_reason,
                "message_id": (state.receipt or {}).get("message_id"),
                "delivery_generation": state.delivery_generation,
                # Closed-set booleans an operator/dashboard can trust without
                # re-deriving success from raw journal fields.
                "transport_dispatched": state.transport_started,
                "success_ledger_committed": state.committed,
                "receipt_sequence_valid": (state.receipt is None
                                           or not state.invalid_sequence()),
            })
        return out

    # ---- legal-transition contract ---------------------------------------

    def _transition_refusal(
        self,
        state: _AttemptState,
        event: str,
        *,
        release_reason: Optional[str] = None,
        operator_reconciliation: bool = False,
    ) -> Optional[str]:
        """Validate the EXACT predecessor state for ``event``.

        Returns ``None`` when legal, else a closed-set refusal detail. This
        checks the replayed state machine -- never string ordering, never mere
        field presence."""
        current = state.state()
        if event == EVENT_TRANSPORT_IN_PROGRESS:
            if current != DELIVERY_STATE_ATTEMPT_RESERVED:
                return "REQUIRES_ATTEMPT_RESERVED"
            return None
        if event == EVENT_DELIVERY_RECEIPT:
            if operator_reconciliation:
                # The ONLY legal receipt outside TRANSPORT_IN_PROGRESS is an
                # explicit operator reconciliation of an ambiguous outcome,
                # which by construction already had a durable transport start.
                if current != DELIVERY_STATE_UNKNOWN:
                    return "REQUIRES_DELIVERY_UNKNOWN"
                return None
            if current != DELIVERY_STATE_TRANSPORT_IN_PROGRESS:
                return "REQUIRES_TRANSPORT_IN_PROGRESS"
            return None
        if event in (EVENT_DELIVERY_FAILED_RETRYABLE, EVENT_DELIVERY_UNKNOWN):
            if current != DELIVERY_STATE_TRANSPORT_IN_PROGRESS:
                return "REQUIRES_TRANSPORT_IN_PROGRESS"
            return None
        if event == EVENT_SENT_OK_COMMITTED:
            if current != DELIVERY_STATE_COMMIT_PENDING:
                return "REQUIRES_CONFIRMED_RECEIPT"
            return None
        if event == EVENT_LEASE_RELEASED:
            if current == DELIVERY_STATE_ATTEMPT_RESERVED:
                return None
            if current == DELIVERY_STATE_FAILED_RETRYABLE:
                return None            # paired with the explicit-failure record
            if current == DELIVERY_STATE_TRANSPORT_IN_PROGRESS:
                # A transport-start record exists, so a remote delivery may
                # have begun: releasing is safe ONLY when the guard proved
                # nothing reached the wire. Lease expiry must NEVER release
                # here -- that is precisely the duplicate-delivery window.
                if release_reason == RELEASE_REASON_GUARD_REFUSED:
                    return None
                return "TRANSPORT_IN_PROGRESS_REQUIRES_OPERATOR"
            if current == DELIVERY_STATE_UNKNOWN:
                if release_reason == RELEASE_REASON_OPERATOR_NOT_DELIVERED:
                    return None
                return "UNKNOWN_REQUIRES_OPERATOR_RESOLUTION"
            if current == DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID:
                if release_reason == RELEASE_REASON_OPERATOR_NOT_DELIVERED:
                    return None
                return "INVALID_SEQUENCE_REQUIRES_OPERATOR_RESOLUTION"
            return "TERMINAL_ATTEMPT"
        return "UNSUPPORTED_EVENT"

    def _binding_refusal(
        self,
        state: _AttemptState,
        *,
        token_mint: Optional[str] = None,
        candidate_id: Optional[str] = None,
        tier_token: Optional[str] = None,
        snapshot_body_sha256: Optional[str] = None,
        dedupe_key: Optional[Dict[str, Any]] = None,
        delivery_generation: Optional[int] = None,
    ) -> Optional[str]:
        """Compare caller-supplied immutable bindings against the attempt's
        durable ATTEMPT_RESERVED bindings. ``None`` asserts nothing (legacy
        call sites); any supplied value must match EXACTLY."""
        if token_mint is not None and str(token_mint) != state.token_mint:
            return "MINT_MISMATCH"
        if candidate_id is not None and str(candidate_id) != state.candidate_id:
            return "CANDIDATE_MISMATCH"
        if tier_token is not None and str(tier_token) != state.tier_token:
            return "TIER_MISMATCH"
        if snapshot_body_sha256 is not None \
                and snapshot_body_sha256 != state.snapshot_body_sha256:
            return "SNAPSHOT_DIGEST_MISMATCH"
        if dedupe_key is not None:
            if not isinstance(dedupe_key, dict) \
                    or dict(dedupe_key) != state.dedupe_key:
                return "LEDGER_KEY_MISMATCH"
        if delivery_generation is not None \
                and _coerce_generation(delivery_generation) \
                != state.delivery_generation:
            return "DELIVERY_GENERATION_MISMATCH"
        return None

    def _guarded_append(
        self,
        attempt_id: str,
        *,
        event: str,
        record: Dict[str, Any],
        bindings: Optional[Dict[str, Any]] = None,
        release_reason: Optional[str] = None,
        operator_reconciliation: bool = False,
    ) -> JournalWriteResult:
        """Availability -> attempt exists -> legal transition -> immutable
        bindings -> durable append. Any refusal fails closed WITHOUT writing."""
        if not self._available:
            return JournalWriteResult(
                WRITE_JOURNAL_UNAVAILABLE, self._unavailable_reason)
        if not isinstance(attempt_id, str) or not attempt_id:
            return JournalWriteResult(
                WRITE_ILLEGAL_TRANSITION, "MALFORMED_ATTEMPT_ID")
        state = self._attempts.get(attempt_id)
        if state is None:
            return JournalWriteResult(
                WRITE_ILLEGAL_TRANSITION, "ATTEMPT_NOT_FOUND")
        refusal = self._transition_refusal(
            state, event, release_reason=release_reason,
            operator_reconciliation=operator_reconciliation)
        if refusal is not None:
            return JournalWriteResult(WRITE_ILLEGAL_TRANSITION, refusal)
        if bindings is not None:
            mismatch = self._binding_refusal(state, **bindings)
            if mismatch is not None:
                return JournalWriteResult(WRITE_BINDING_MISMATCH, mismatch)
        return self._append_result(record)

    # ---- transaction steps ----------------------------------------------

    def acquire_lease(
        self,
        *,
        key_map: Dict[str, Any],
        token_mint: str,
        candidate_id: str,
        tier_token: str,
        snapshot_body_sha256: Optional[str],
        now_utc: str,
        lease_seconds: int = DEFAULT_ATTEMPT_LEASE_SECONDS,
        delivery_generation: Optional[int] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Acquire the single temporary attempt lease for a dedupe key.

        Returns ``(attempt_id, None)`` on success, else ``(None, refusal)``.
        Refuses when the journal is unavailable, another un-expired lease is
        active for the key (only one concurrent attempt), an unresolved
        DELIVERY_UNKNOWN outcome is pending for the key (ambiguity is never
        silently retried), or a quarantined receipt sequence is unresolved."""
        if not self._available:
            return None, "JOURNAL_UNAVAILABLE"
        if not isinstance(key_map, dict) or not key_map:
            return None, "MALFORMED_DEDUPE_KEY"
        now = _parse_iso_utc(now_utc)
        if now is None:
            return None, "MALFORMED_NOW"
        if self.active_lease_for_key(key_map, now_utc=now_utc) is not None:
            return None, DELIVERY_STATE_LEASE_HELD
        if self.pending_unknown_for_key(key_map) is not None:
            return None, "DELIVERY_UNKNOWN_PENDING_RECONCILIATION"
        if self.pending_invalid_sequence_for_key(key_map) is not None:
            return None, "DELIVERY_RECEIPT_SEQUENCE_INVALID_PENDING_RECONCILIATION"
        prior = len(self._attempts_for_key(key_map))
        generation = (prior if delivery_generation is None
                      else _coerce_generation(delivery_generation))
        attempt_id = hashlib.sha256(
            f"{self._key_token(key_map)}|{now_utc}|{prior}".encode("utf-8")
        ).hexdigest()[:32]
        if attempt_id in self._attempts:
            return None, "ATTEMPT_ID_CONFLICT"
        from datetime import timedelta
        record = {
            "event": EVENT_ATTEMPT_RESERVED,
            "attempt_id": attempt_id,
            "token_mint": token_mint,
            "candidate_id": candidate_id,
            "tier_token": tier_token,
            "dedupe_key": dict(key_map),
            "snapshot_body_sha256": snapshot_body_sha256,
            "delivery_generation": generation,
            "recorded_at_utc": now_utc,
            "lease_expires_at_utc": _iso(
                now + timedelta(seconds=int(lease_seconds))),
        }
        if not self._append_result(record).persisted:
            return None, "JOURNAL_WRITE_FAILED"
        return attempt_id, None

    def record_transport_started(
        self,
        attempt_id: str,
        *,
        now_utc: str,
        expected_token_mint: Optional[str] = None,
        expected_candidate_id: Optional[str] = None,
        expected_tier_token: Optional[str] = None,
        expected_snapshot_body_sha256: Optional[str] = None,
        expected_dedupe_key: Optional[Dict[str, Any]] = None,
        expected_delivery_generation: Optional[int] = None,
    ) -> JournalWriteResult:
        """Durably authorize EXACTLY ONE transport call for ``attempt_id``.

        The returned result is authoritative (PHX2-E2E-001): a transport may be
        invoked only when ``dispatch_authorized`` is True, which requires a
        freshly persisted, fsynced, read-back-verified
        ``ATTEMPT_RESERVED -> TRANSPORT_IN_PROGRESS`` record whose immutable
        bindings match every supplied expectation. An already-started attempt
        returns ``ALREADY_PERSISTED`` and does NOT re-authorize dispatch: a
        prior transport call may already have reached the wire."""
        self.note(COUNTER_START_ATTEMPTED)
        state = self._attempts.get(attempt_id) if self._available else None
        if state is not None and state.transport_started:
            self.note(COUNTER_START_FAILED)
            mismatch = self._binding_refusal(
                state,
                token_mint=expected_token_mint,
                candidate_id=expected_candidate_id,
                tier_token=expected_tier_token,
                snapshot_body_sha256=expected_snapshot_body_sha256,
                dedupe_key=expected_dedupe_key,
                delivery_generation=expected_delivery_generation,
            )
            if mismatch is not None:
                return JournalWriteResult(WRITE_CONFLICT, mismatch)
            return JournalWriteResult(
                WRITE_ALREADY_PERSISTED, "TRANSPORT_ALREADY_STARTED")
        result = self._guarded_append(
            attempt_id,
            event=EVENT_TRANSPORT_IN_PROGRESS,
            record={
                "event": EVENT_TRANSPORT_IN_PROGRESS,
                "attempt_id": attempt_id,
                "recorded_at_utc": now_utc,
            },
            bindings={
                "token_mint": expected_token_mint,
                "candidate_id": expected_candidate_id,
                "tier_token": expected_tier_token,
                "snapshot_body_sha256": expected_snapshot_body_sha256,
                "dedupe_key": expected_dedupe_key,
                "delivery_generation": expected_delivery_generation,
            },
        )
        if result.status == WRITE_PERSISTED:
            self.note(COUNTER_START_PERSISTED)
            return JournalWriteResult(WRITE_PERSISTED, dispatch_authorized=True)
        self.note(COUNTER_START_FAILED)
        return result

    def record_failed_retryable(
        self, attempt_id: str, *, transport_status: Optional[str], now_utc: str
    ) -> JournalWriteResult:
        result = self._guarded_append(
            attempt_id,
            event=EVENT_DELIVERY_FAILED_RETRYABLE,
            record={
                "event": EVENT_DELIVERY_FAILED_RETRYABLE,
                "attempt_id": attempt_id,
                "transport_status": transport_status,
                "recorded_at_utc": now_utc,
            },
        )
        if not result.persisted:
            return result
        return self._guarded_append(
            attempt_id,
            event=EVENT_LEASE_RELEASED,
            record={
                "event": EVENT_LEASE_RELEASED,
                "attempt_id": attempt_id,
                "release_reason": RELEASE_REASON_EXPLICIT_FAILURE,
                "recorded_at_utc": now_utc,
            },
            release_reason=RELEASE_REASON_EXPLICIT_FAILURE,
        )

    def record_unknown(
        self, attempt_id: str, *, transport_status: Optional[str], now_utc: str
    ) -> JournalWriteResult:
        return self._guarded_append(
            attempt_id,
            event=EVENT_DELIVERY_UNKNOWN,
            record={
                "event": EVENT_DELIVERY_UNKNOWN,
                "attempt_id": attempt_id,
                "transport_status": transport_status,
                "recorded_at_utc": now_utc,
            },
        )

    def record_receipt(
        self,
        attempt_id: str,
        *,
        message_id: Optional[int],
        transport_status: Optional[str],
        now_utc: str,
        expected_token_mint: Optional[str] = None,
        expected_candidate_id: Optional[str] = None,
        expected_tier_token: Optional[str] = None,
        expected_snapshot_body_sha256: Optional[str] = None,
        expected_dedupe_key: Optional[Dict[str, Any]] = None,
        expected_delivery_generation: Optional[int] = None,
        operator_reconciliation: bool = False,
    ) -> JournalWriteResult:
        """Persist the durable confirmed-success receipt BEFORE the ledger
        commit (PHX2-E2E-009).

        A receipt is legal ONLY from a durable TRANSPORT_IN_PROGRESS
        predecessor for the same attempt -- or, via
        ``operator_reconciliation``, from an explicitly resolved
        DELIVERY_UNKNOWN. A second receipt is idempotent when byte-identical
        in delivery identity and a hard CONFLICT otherwise."""
        if not self._available:
            return JournalWriteResult(
                WRITE_JOURNAL_UNAVAILABLE, self._unavailable_reason)
        state = self._attempts.get(attempt_id) if isinstance(attempt_id, str) \
            else None
        if state is None:
            self.note(COUNTER_RECEIPT_PREDECESSOR_INVALID)
            return JournalWriteResult(
                WRITE_ILLEGAL_TRANSITION, "ATTEMPT_NOT_FOUND")
        # Bindings are validated BEFORE idempotence: a caller holding the wrong
        # attempt must never be silently satisfied by an identical receipt.
        mismatch = self._binding_refusal(
            state,
            token_mint=expected_token_mint,
            candidate_id=expected_candidate_id,
            tier_token=expected_tier_token,
            snapshot_body_sha256=expected_snapshot_body_sha256,
            dedupe_key=expected_dedupe_key,
            delivery_generation=expected_delivery_generation,
        )
        if mismatch is not None:
            self.note(COUNTER_RECEIPT_BINDING_MISMATCH)
            return JournalWriteResult(WRITE_BINDING_MISMATCH, mismatch)
        record = {
            "event": EVENT_DELIVERY_RECEIPT,
            "attempt_id": attempt_id,
            "token_mint": state.token_mint,
            "candidate_id": state.candidate_id,
            "tier_token": state.tier_token,
            "dedupe_key": dict(state.dedupe_key),
            "snapshot_body_sha256": state.snapshot_body_sha256,
            "delivery_generation": state.delivery_generation,
            "message_id": message_id,
            "transport_status": transport_status,
            "recorded_at_utc": now_utc,
        }
        if state.receipt is not None:
            # Idempotence is decided BEFORE the transition check: the attempt
            # already advanced past TRANSPORT_IN_PROGRESS by its own receipt.
            if _same_receipt(state.receipt, record):
                return JournalWriteResult(
                    WRITE_ALREADY_PERSISTED, "IDEMPOTENT_RECEIPT")
            self.note(COUNTER_RECEIPT_CONFLICT)
            return JournalWriteResult(WRITE_CONFLICT, "RECEIPT_CONFLICT")
        result = self._guarded_append(
            attempt_id,
            event=EVENT_DELIVERY_RECEIPT,
            record=record,
            bindings={
                "token_mint": expected_token_mint,
                "candidate_id": expected_candidate_id,
                "tier_token": expected_tier_token,
                "snapshot_body_sha256": expected_snapshot_body_sha256,
                "dedupe_key": expected_dedupe_key,
                "delivery_generation": expected_delivery_generation,
            },
            operator_reconciliation=operator_reconciliation,
        )
        if result.status == WRITE_ILLEGAL_TRANSITION:
            self.note(COUNTER_RECEIPT_PREDECESSOR_INVALID)
        elif result.status == WRITE_BINDING_MISMATCH:
            self.note(COUNTER_RECEIPT_BINDING_MISMATCH)
        return result

    def record_committed(
        self, attempt_id: str, *, now_utc: str
    ) -> JournalWriteResult:
        return self._guarded_append(
            attempt_id,
            event=EVENT_SENT_OK_COMMITTED,
            record={
                "event": EVENT_SENT_OK_COMMITTED,
                "attempt_id": attempt_id,
                "recorded_at_utc": now_utc,
            },
        )

    def release_lease(
        self, attempt_id: str, *, release_reason: str, now_utc: str
    ) -> JournalWriteResult:
        return self._guarded_append(
            attempt_id,
            event=EVENT_LEASE_RELEASED,
            record={
                "event": EVENT_LEASE_RELEASED,
                "attempt_id": attempt_id,
                "release_reason": release_reason,
                "recorded_at_utc": now_utc,
            },
            release_reason=release_reason,
        )


def _note(journal: Any, name: str) -> None:
    """Increment a journal counter when the injected journal supports them."""
    note = getattr(journal, "note", None)
    if callable(note):
        note(name)


def _start_failure_reason(result: Any) -> str:
    """Closed-set reason for a blocked dispatch. Never reports a transport
    failure: the transport was NOT called."""
    if getattr(result, "status", "") == WRITE_JOURNAL_UNAVAILABLE:
        return REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH
    return REFUSAL_TRANSPORT_START_PERSIST_FAILED


def _receipt_failure_reason(result: Any) -> str:
    status = getattr(result, "status", "")
    if status == WRITE_ILLEGAL_TRANSITION:
        return REFUSAL_RECEIPT_PREDECESSOR_INVALID
    if status == WRITE_BINDING_MISMATCH:
        return REFUSAL_RECEIPT_BINDING_MISMATCH
    if status == WRITE_CONFLICT:
        return REFUSAL_RECEIPT_CONFLICT
    return REFUSAL_RECEIPT_PERSIST_FAILED


def _receipt_binding_valid(state: _AttemptState) -> Tuple[bool, str]:
    """Fail-closed predecessor + binding check between the reserved attempt and
    its receipt: the receipt must follow a durable TRANSPORT_IN_PROGRESS record
    and reference the SAME mint / candidate / tier / dedupe key / snapshot
    digest / generation the lease bound. Any violation refuses the commit."""
    receipt = state.receipt or {}
    if state.receipt is None:
        return False, REFUSAL_RECEIPT_PREDECESSOR_INVALID
    if not state.receipt_after_start:
        # PHX2-E2E-009: a receipt with no durable transport-start predecessor
        # is never evidence of a delivery, however well-formed it looks.
        return False, REFUSAL_RECEIPT_PREDECESSOR_INVALID
    if state.receipt_conflict:
        return False, REFUSAL_RECEIPT_CONFLICT
    if _coerce_generation(receipt.get("delivery_generation")) \
            != state.delivery_generation:
        return False, "RECEIPT_GENERATION_MISMATCH"
    if str(receipt.get("token_mint") or "") != state.token_mint:
        return False, "RECEIPT_MINT_MISMATCH"
    if str(receipt.get("candidate_id") or "") != state.candidate_id:
        return False, "RECEIPT_CANDIDATE_MISMATCH"
    if str(receipt.get("tier_token") or "") != state.tier_token:
        return False, "RECEIPT_TIER_MISMATCH"
    if receipt.get("dedupe_key") != state.dedupe_key:
        return False, "RECEIPT_KEY_MISMATCH"
    if receipt.get("snapshot_body_sha256") != state.snapshot_body_sha256:
        return False, "RECEIPT_SNAPSHOT_MISMATCH"
    if state.dedupe_key.get("token_mint") != state.token_mint:
        return False, "RECEIPT_KEY_MINT_MISMATCH"
    return True, ""


def _commit_from_receipt(
    *,
    journal: DeliveryAttemptJournal,
    ledger: Any,
    state: _AttemptState,
    ttl_seconds: int,
    now_utc: str,
) -> Tuple[bool, str]:
    """Finish the successful-send commit from a durable receipt: exactly one
    ledger row (idempotent by TTL classification), then the committed marker.
    Never calls a transport. Returns ``(committed, reason)``."""
    ok, reason = _receipt_binding_valid(state)
    if not ok:
        return False, reason
    commit_fn = getattr(ledger, "commit_confirmed_send", None)
    if not callable(commit_fn):
        return False, "LEDGER_COMMIT_UNSUPPORTED"
    receipt_at = (state.receipt or {}).get("recorded_at_utc") or now_utc
    key = _key_from_map(state.dedupe_key)
    if key is None:
        return False, "RECEIPT_KEY_MALFORMED"
    outcome = commit_fn(key=key, now_utc=receipt_at, ttl_seconds=ttl_seconds)
    # allowed => this commit wrote the one row; a suppressed duplicate means
    # the row already exists (idempotent replay). Anything else fails closed.
    allowed = bool(getattr(outcome, "allowed", False))
    already = getattr(outcome, "verdict", "") == "DEDUPE_SUPPRESSED_DUPLICATE"
    if not allowed and not already:
        return False, "LEDGER_COMMIT_UNAVAILABLE"
    if not journal.record_committed(state.attempt_id, now_utc=now_utc):
        return False, "JOURNAL_COMMIT_MARKER_FAILED"
    return True, ""


def _key_from_map(key_map: Dict[str, Any]) -> Optional[Any]:
    try:
        from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
            Stage30_11_15PingDedupeKey,
        )
        return Stage30_11_15PingDedupeKey(
            token_mint=key_map["token_mint"],
            operator_signal_kind=key_map["operator_signal_kind"],
            tier_token=key_map["tier_token"],
            drawdown_band=key_map["drawdown_band"],
            post_migration_ath_verified=key_map["post_migration_ath_verified"],
            ath_source_stage=key_map["ath_source_stage"],
            policy_version=key_map["policy_version"],
        )
    except (KeyError, TypeError):
        return None


def _resolve_message_id(send_result: Any, delivery_evidence: Any) -> Optional[int]:
    """The Telegram success message identifier where available: read off the
    guard result when a fake carries it, else off the delivery adapter's
    ``last_result`` (the committed evidence surface). Pure; never raises."""
    for candidate in (
        getattr(send_result, "message_id", None),
        getattr(getattr(delivery_evidence, "last_result", None),
                "message_id", None),
    ):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return candidate
    return None


def execute_guarded_delivery(
    *,
    deduped: Any,
    guard: Any,
    authorization: Any,
    created_at_utc: str,
    journal: DeliveryAttemptJournal,
    ledger: Any,
    dedupe_key: Any,
    snapshot_body: object,
    ttl_seconds: int,
    lease_seconds: int = DEFAULT_ATTEMPT_LEASE_SECONDS,
    delivery_evidence: Any = None,
) -> Dict[str, Any]:
    """Run ONE delivery transaction in the corrected production order:

        lease (temporary, bounded)
          -> DURABLE transport-start record, confirmed for this exact attempt
             and its immutable bindings          <-- dispatch authority gate
          -> transport -> classify
          -> [receipt -> successful-send ledger row -> commit] |
             [explicit failure -> release lease, stay retryable] |
             [ambiguous -> DELIVERY_UNKNOWN, observable, no auto-retry]

    The transport is NOT invoked unless the start record is durably confirmed
    (PHX2-E2E-001); a failed start persistence returns
    ``DELIVERY_DISPATCH_BLOCKED_JOURNAL_FAILURE`` with a closed-set reason,
    leaves the lease to expire safely, and is never reported as a transport
    failure or a sent state.

    Returns a dict with ``delivery_state``, ``attempt_id``, ``send_result``,
    ``transport_invoked``, ``ledger_committed`` and the transport
    classification. Never appends the successful-send ledger for anything
    except a CONFIRMED transport_ok=True result with a durable, binding-checked
    receipt."""
    key_map = dedupe_key_to_dict(dedupe_key)
    if key_map is None:
        return {"delivery_state": DELIVERY_STATE_ABORTED_BEFORE_TRANSPORT,
                "attempt_id": None, "send_result": None,
                "classification": CLASSIFY_NOT_ATTEMPTED,
                "refusal_reason": "MALFORMED_DEDUPE_KEY"}
    compose_result = getattr(deduped, "compose_result", None)
    token_mint = str(getattr(compose_result, "token_mint", "") or "")
    candidate_id = str(getattr(compose_result, "candidate_id", "") or "")
    snapshot = getattr(compose_result, "snapshot", None)
    tier_token = str(getattr(snapshot, "tier_token", "") or "")
    attempt_id, refusal = journal.acquire_lease(
        key_map=key_map,
        token_mint=token_mint,
        candidate_id=candidate_id,
        tier_token=tier_token,
        snapshot_body_sha256=snapshot_body_digest(snapshot_body),
        now_utc=created_at_utc,
        lease_seconds=lease_seconds,
    )
    if attempt_id is None:
        return {"delivery_state": DELIVERY_STATE_LEASE_HELD,
                "attempt_id": None, "send_result": None,
                "classification": CLASSIFY_NOT_ATTEMPTED,
                "transport_invoked": False, "ledger_committed": False,
                "refusal_reason": refusal}
    leased = journal.attempt(attempt_id)
    generation = getattr(leased, "delivery_generation", None)
    bindings = {
        "expected_token_mint": token_mint,
        "expected_candidate_id": candidate_id,
        "expected_tier_token": tier_token,
        "expected_snapshot_body_sha256": snapshot_body_digest(snapshot_body),
        "expected_dedupe_key": key_map,
        "expected_delivery_generation": generation,
    }
    # PHX2-E2E-001: the durable transport-start record is the ONLY authority
    # that may authorize a transport call. If it cannot be proven durable for
    # THIS exact attempt and bindings, the transport is not invoked at all --
    # otherwise a delivery could occur leaving no durable evidence, and a later
    # restart would release the lease and deliver a SECOND time.
    try:
        start = journal.record_transport_started(
            attempt_id, now_utc=created_at_utc, **bindings)
    except Exception:
        # The transport was never called. Convert to a closed-set reason and
        # never surface the raw exception contents.
        start = JournalWriteResult(WRITE_FAILED, "TRANSPORT_START_RAISED")
    if not getattr(start, "dispatch_authorized", False):
        _note(journal, COUNTER_DISPATCH_BLOCKED)
        # The lease is deliberately NOT released: it holds the key for its
        # bounded remaining life (no busy retry loop) and, carrying no
        # transport-start record, expires safely for a later healthy attempt.
        return {"delivery_state": DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL,
                "attempt_id": attempt_id, "send_result": None,
                "classification": CLASSIFY_NOT_ATTEMPTED,
                "transport_invoked": False, "ledger_committed": False,
                "journal_write_status": getattr(start, "status", WRITE_FAILED),
                "refusal_reason": _start_failure_reason(start)}
    send_result = guard.authorize_and_dispatch(
        deduped, authorization=authorization, created_at_utc=created_at_utc)
    classification = classify_transport_result(send_result)
    if classification == CLASSIFY_CONFIRMED_OK:
        message_id = _resolve_message_id(send_result, delivery_evidence)
        receipt = journal.record_receipt(
            attempt_id,
            message_id=message_id,
            transport_status=getattr(send_result, "transport_status", None),
            now_utc=created_at_utc,
            **bindings,
        )
        if not receipt:
            # The remote delivery IS confirmed but no durable receipt exists.
            # Never commit the successful-send row from volatile state, and
            # never retry: the durable transport-start record makes restart
            # reconciliation park this as operator-held DELIVERY_UNKNOWN.
            journal.record_unknown(
                attempt_id,
                transport_status=RECONCILE_INTERRUPTED_TRANSPORT,
                now_utc=created_at_utc)
            return {"delivery_state": DELIVERY_STATE_UNKNOWN,
                    "attempt_id": attempt_id, "send_result": send_result,
                    "classification": CLASSIFY_UNKNOWN,
                    "transport_invoked": True, "ledger_committed": False,
                    "journal_write_status": getattr(
                        receipt, "status", WRITE_FAILED),
                    "refusal_reason": _receipt_failure_reason(receipt)}
        state = journal.attempt(attempt_id)
        committed, commit_reason = _commit_from_receipt(
            journal=journal, ledger=ledger, state=state,
            ttl_seconds=ttl_seconds, now_utc=created_at_utc)
        return {
            "delivery_state": (DELIVERY_STATE_SENT_OK_COMMITTED if committed
                               else DELIVERY_STATE_COMMIT_PENDING),
            "attempt_id": attempt_id,
            "send_result": send_result,
            "classification": classification,
            "message_id": message_id,
            "commit_reason": commit_reason,
            "transport_invoked": True,
            "ledger_committed": committed,
        }
    if classification == CLASSIFY_FAILED_RETRYABLE:
        journal.record_failed_retryable(
            attempt_id,
            transport_status=getattr(send_result, "transport_status", None),
            now_utc=created_at_utc,
        )
        return {"delivery_state": DELIVERY_STATE_FAILED_RETRYABLE,
                "attempt_id": attempt_id, "send_result": send_result,
                "classification": classification,
                "transport_invoked": True, "ledger_committed": False,
                "failure_reason": getattr(
                    send_result, "transport_status", None)}
    if classification == CLASSIFY_NOT_ATTEMPTED:
        # The guard proved nothing reached the wire, so the lease may be
        # released even though a transport-start record exists.
        journal.release_lease(
            attempt_id,
            release_reason=RELEASE_REASON_GUARD_REFUSED,
            now_utc=created_at_utc,
        )
        return {"delivery_state": DELIVERY_STATE_ABORTED_BEFORE_TRANSPORT,
                "attempt_id": attempt_id, "send_result": send_result,
                "classification": classification,
                "transport_invoked": False, "ledger_committed": False,
                "refusal_reason": getattr(send_result, "reason", None)}
    journal.record_unknown(
        attempt_id,
        transport_status=getattr(send_result, "transport_status", None),
        now_utc=created_at_utc,
    )
    return {"delivery_state": DELIVERY_STATE_UNKNOWN,
            "attempt_id": attempt_id, "send_result": send_result,
            "classification": classification,
            "transport_invoked": True, "ledger_committed": False}


def reconcile_journal_on_restart(
    *,
    journal: DeliveryAttemptJournal,
    ledger: Any,
    now_utc: str,
    ttl_seconds: int,
) -> Dict[str, Any]:
    """Deterministic restart reconciliation over the outbox journal:

    * receipt without commit  -> finish the ledger commit (no transport call)
    * transport began, no outcome -> DELIVERY_UNKNOWN (observable; no resend)
    * stale reserved lease    -> released (retry permitted)

    Never calls any transport. Returns a redaction-safe report."""
    report = {
        "kind": "PHX2_DELIVERY_RECONCILIATION",
        "reconciled_at_utc": now_utc,
        "journal_available": journal.available,
        "commits_completed": 0,
        "commits_failed": 0,
        "unknown_marked": 0,
        "leases_released": 0,
        "pending_unknown": 0,
        "invalid_sequences": 0,
        "details": [],
    }
    if not journal.available:
        report["journal_unavailable_reason"] = journal.unavailable_reason
        return report
    for state in journal.all_attempts():
        if state.invalid_sequence() and not state.committed:
            # PHX2-E2E-009: a durable receipt whose own ordering cannot prove a
            # transport ever started. Quarantined: no commit, no ledger row, no
            # automatic retry -- the key stays blocked until an operator
            # resolves it explicitly.
            _note(journal, COUNTER_RESTART_INVALID_SEQUENCE)
            report["invalid_sequences"] += 1
            report["details"].append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "action": "INVALID_SEQUENCE_QUARANTINED",
                "reason": (REFUSAL_RECEIPT_CONFLICT if state.receipt_conflict
                           else REFUSAL_RECEIPT_PREDECESSOR_INVALID),
            })
            continue
        if state.receipt is not None and not state.committed:
            committed, reason = _commit_from_receipt(
                journal=journal, ledger=ledger, state=state,
                ttl_seconds=ttl_seconds, now_utc=now_utc)
            if committed:
                report["commits_completed"] += 1
                _note(journal, COUNTER_SUCCESS_COMMIT_RECONCILED)
            else:
                report["commits_failed"] += 1
            report["details"].append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "action": ("COMMIT_COMPLETED" if committed
                           else "COMMIT_FAILED"),
                "reason": reason,
            })
            continue
        if state.committed or state.released or state.failed_retryable:
            continue
        if state.unknown:
            report["pending_unknown"] += 1
            report["details"].append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "action": "UNKNOWN_PENDING",
                "reason": state.last_transport_status,
            })
            continue
        if state.transport_started:
            # A transport call was durably authorized and may have reached the
            # wire: never released, never auto-retried -- operator-held.
            journal.record_unknown(
                state.attempt_id,
                transport_status=RECONCILE_INTERRUPTED_TRANSPORT,
                now_utc=now_utc,
            )
            _note(journal, COUNTER_RESTART_UNKNOWN_TRANSPORT)
            report["unknown_marked"] += 1
            report["pending_unknown"] += 1
            report["details"].append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "action": "MARKED_UNKNOWN",
                "reason": RECONCILE_INTERRUPTED_TRANSPORT,
            })
            continue
        if not state.lease_active(now_utc):
            journal.release_lease(
                state.attempt_id,
                release_reason=RELEASE_REASON_LEASE_EXPIRED_STALE,
                now_utc=now_utc,
            )
            report["leases_released"] += 1
            report["details"].append({
                "attempt_id": state.attempt_id,
                "token_mint": state.token_mint,
                "action": "LEASE_RELEASED",
                "reason": RELEASE_REASON_LEASE_EXPIRED_STALE,
            })
    return report


def resolve_unknown_attempt(
    *,
    journal: DeliveryAttemptJournal,
    ledger: Any,
    attempt_id: str,
    resolution: str,
    now_utc: str,
    ttl_seconds: int,
) -> Dict[str, Any]:
    """Explicit operator reconciliation for a DELIVERY_UNKNOWN attempt.

    ``resolution`` is ``CONFIRMED_DELIVERED`` (record a receipt with no message
    id, then commit the successful-send row -- prevents any duplicate) or
    ``CONFIRMED_NOT_DELIVERED`` (release the lease so a later healthy retry is
    permitted). Anything else fails closed.

    This is the ONLY API that may attach a receipt outside
    TRANSPORT_IN_PROGRESS, and it also releases a quarantined invalid receipt
    sequence so the key is not blocked forever."""
    state = journal.attempt(attempt_id)
    quarantined = state is not None and state.invalid_sequence()
    if state is None or state.committed or state.released \
            or not (state.unknown or quarantined):
        return {"resolved": False, "reason": "ATTEMPT_NOT_PENDING_UNKNOWN"}
    if resolution == "CONFIRMED_DELIVERED":
        if quarantined:
            # A quarantined sequence has no trustworthy predecessor; an
            # operator cannot promote it to a success commit.
            return {"resolved": False,
                    "reason": REFUSAL_RECEIPT_PREDECESSOR_INVALID}
        if not journal.record_receipt(
                attempt_id, message_id=None,
                transport_status="OPERATOR_CONFIRMED_DELIVERED",
                now_utc=now_utc, operator_reconciliation=True):
            return {"resolved": False, "reason": "JOURNAL_WRITE_FAILED"}
        committed, reason = _commit_from_receipt(
            journal=journal, ledger=ledger, state=journal.attempt(attempt_id),
            ttl_seconds=ttl_seconds, now_utc=now_utc)
        return {"resolved": committed,
                "reason": reason,
                "delivery_state": (DELIVERY_STATE_SENT_OK_COMMITTED
                                   if committed
                                   else DELIVERY_STATE_COMMIT_PENDING)}
    if resolution == "CONFIRMED_NOT_DELIVERED":
        if not journal.release_lease(
                attempt_id,
                release_reason=RELEASE_REASON_OPERATOR_NOT_DELIVERED,
                now_utc=now_utc):
            return {"resolved": False, "reason": "JOURNAL_WRITE_FAILED"}
        return {"resolved": True, "reason": "",
                "delivery_state": DELIVERY_STATE_RELEASED}
    return {"resolved": False, "reason": "UNSUPPORTED_RESOLUTION"}


def reconcile_watchlist_delivery(
    *,
    watchlist: Any,
    journal: DeliveryAttemptJournal,
    now_utc: str,
) -> List[Dict[str, Any]]:
    """Restart alignment between the outbox journal and restored watch entries:
    a mint whose delivery is already committed terminalizes WITHOUT another
    transport call; a pending-unknown mint surfaces as DELIVERY_UNKNOWN."""
    events: List[Dict[str, Any]] = []
    if not journal.available:
        return events
    for state in journal.all_attempts():
        if not state.token_mint:
            continue
        entry = watchlist.get(state.token_mint)
        if entry is None or not entry.is_active():
            continue
        if state.committed:
            watchlist.record_recheck(
                mint=state.token_mint,
                reason="SENT_OK_COMMITTED",
                observed_at_utc=now_utc,
                delivery_state=DELIVERY_STATE_SENT_OK_COMMITTED,
                delivery_attempt_id=state.attempt_id,
                delivery_receipt_message_id=(
                    (state.receipt or {}).get("message_id")),
            )
            events.append({"token_mint": state.token_mint,
                           "action": "TERMINALIZED_FROM_RECEIPT"})
        elif state.unknown and not state.released:
            watchlist.record_recheck(
                mint=state.token_mint,
                reason="DELIVERY_UNKNOWN",
                observed_at_utc=now_utc,
                delivery_state=DELIVERY_STATE_UNKNOWN,
                delivery_attempt_id=state.attempt_id,
            )
            events.append({"token_mint": state.token_mint,
                           "action": "MARKED_DELIVERY_UNKNOWN"})
    return events


__all__ = (
    "DELIVERY_OUTBOX_SCHEMA_VERSION",
    "DELIVERY_STATE_ATTEMPT_RESERVED",
    "DELIVERY_STATE_TRANSPORT_IN_PROGRESS",
    "DELIVERY_STATE_FAILED_RETRYABLE",
    "DELIVERY_STATE_UNKNOWN",
    "DELIVERY_STATE_SENT_OK_COMMITTED",
    "DELIVERY_STATE_COMMIT_PENDING",
    "DELIVERY_STATE_ABORTED_BEFORE_TRANSPORT",
    "DELIVERY_STATE_LEASE_HELD",
    "DELIVERY_STATE_RELEASED",
    "DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL",
    "DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID",
    "REFUSAL_TRANSPORT_START_PERSIST_FAILED",
    "REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH",
    "REFUSAL_RECEIPT_PREDECESSOR_INVALID",
    "REFUSAL_RECEIPT_BINDING_MISMATCH",
    "REFUSAL_RECEIPT_CONFLICT",
    "REFUSAL_RECEIPT_PERSIST_FAILED",
    "JournalWriteResult",
    "WRITE_PERSISTED",
    "WRITE_ALREADY_PERSISTED",
    "WRITE_ILLEGAL_TRANSITION",
    "WRITE_BINDING_MISMATCH",
    "WRITE_JOURNAL_UNAVAILABLE",
    "WRITE_FAILED",
    "WRITE_READBACK_FAILED",
    "WRITE_CONFLICT",
    "COUNTER_START_ATTEMPTED",
    "COUNTER_START_PERSISTED",
    "COUNTER_START_FAILED",
    "COUNTER_DISPATCH_BLOCKED",
    "COUNTER_RECEIPT_PREDECESSOR_INVALID",
    "COUNTER_RECEIPT_BINDING_MISMATCH",
    "COUNTER_RECEIPT_CONFLICT",
    "COUNTER_RESTART_UNKNOWN_TRANSPORT",
    "COUNTER_RESTART_INVALID_SEQUENCE",
    "COUNTER_SUCCESS_COMMIT_RECONCILED",
    "AMBIGUOUS_TRANSPORT_STATUSES",
    "CLASSIFY_CONFIRMED_OK",
    "CLASSIFY_FAILED_RETRYABLE",
    "CLASSIFY_UNKNOWN",
    "CLASSIFY_NOT_ATTEMPTED",
    "DEFAULT_ATTEMPT_LEASE_SECONDS",
    "DEFAULT_RETRY_BACKOFF_BASE_SECONDS",
    "DEFAULT_RETRY_BACKOFF_MAX_SECONDS",
    "DeliveryAttemptJournal",
    "classify_transport_result",
    "compute_retry_backoff_seconds",
    "next_retry_at_utc",
    "retry_due",
    "dedupe_key_to_dict",
    "snapshot_body_digest",
    "execute_guarded_delivery",
    "reconcile_journal_on_restart",
    "resolve_unknown_attempt",
    "reconcile_watchlist_delivery",
)
