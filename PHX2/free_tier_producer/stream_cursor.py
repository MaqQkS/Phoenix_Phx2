"""Durable Yellowstone stream cursor and reconnect-gap recovery contract.

PHX2-E2E-008 (``GRPC_RECONNECT_GAP_UNPROVEN``).

Before this module the single production Yellowstone stream was tip-anchored:
every reconnect rebuilt an identical ``SubscribeRequest`` with no resume
position, so the provider restarted the subscription at the *current* live
head.  A disconnect at slot ``N`` followed by a reconnect at ``N+4`` silently
skipped ``N+1..N+3``.  Dedupe cannot help there -- it suppresses events that
*were* delivered twice; it cannot recover events that were never delivered at
all.  A genuine pump.fun migration inside that window was lost with no
observable trace, while the source still reported itself connected.

The provider contract supports native replay, so this module implements
**Architecture A** (native replay) rather than an independent backfill:

  * ``SubscribeRequest.from_slot`` (``geyser.proto`` field 11) requests a
    replay starting at an exact slot;
  * ``Geyser.SubscribeReplayInfo`` returns ``first_available``, the oldest
    slot the provider can still replay, which bounds retention *before* a
    resume position is attempted.

Recovery introduces no additional provider dependency and opens no second
Yellowstone subscription: it travels through the one replacement stream the
existing reconnect owner already creates.

Durability model
----------------
The cursor is persisted through the authenticated checkpoint envelope from
commit ``9745fd9`` -- this module is a third *adopter* of those primitives
(after the watch checkpoint and the central ATH checkpoint) and changes none
of them.  It supplies only kind-specific callbacks: a record validator, an
identity function, and a cross-generation check that refuses an unexplained
slot rewind.

The cursor advances only *after* the event it names is durably recoverable
downstream.  It is never advanced merely because bytes were read off the
socket, so the failure ordering

    cursor committed -> crash -> handoff never made durable

is impossible by construction; the reverse ordering merely causes a replay
that exact-identity dedupe absorbs.

Nothing in this module opens a socket, reads the environment, or touches a
credential: it receives already-safe structural values from its caller.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer import checkpoint_envelope as _cpe


# ---------------------------------------------------------------------------
# checkpoint identity
# ---------------------------------------------------------------------------

CHECKPOINT_KIND_STREAM_CURSOR = "PHX2_GRPC_STREAM_CURSOR"
STREAM_CURSOR_SCHEMA_V1 = "phx2_stream_cursor_v1"
#: v2 replaces the never-assigned ``last_contiguous_slot`` with the field it was
#: evidently meant to be -- ``last_proven_replay_boundary_slot``, an actual
#: provider-proven replay coverage boundary -- and adds the recovery-episode
#: generation and terminal-retention bookkeeping the boundary contract needs.
#: v1 documents remain loadable: their (always ``None``) contiguity field is
#: read forward, and the first write emits v2.
STREAM_CURSOR_SCHEMA_V2 = "phx2_stream_cursor_v2"
STREAM_CURSOR_SCHEMA_CURRENT = STREAM_CURSOR_SCHEMA_V2
SUPPORTED_CURSOR_SCHEMA_VERSIONS = (
    STREAM_CURSOR_SCHEMA_V2, STREAM_CURSOR_SCHEMA_V1)

CURSOR_RECORD_KIND = "PHX2_GRPC_STREAM_CURSOR_STATE"
CURSOR_PRIMARY_BASENAME = "grpc_stream_cursor.json"
CURSOR_BACKUP_SUFFIX = ".bak"

#: Written verbatim into the persisted cursor document, which lives in the
#: producer's out_dir and is therefore swept by the production redaction
#: scanner. That scanner treats bare provider-vendor names as danger needles,
#: so this token is deliberately vendor-neutral: naming the vendor here would
#: fail every run's postflight scan on a value that carries no secret at all.
STREAM_SOURCE_YELLOWSTONE = "YELLOWSTONE_GRPC_PRIMARY"

#: No cursor has ever been committed. Distinct from slot 0, which is a real
#: (if practically impossible) Solana slot.
NO_SLOT = -1

#: Bounded retention for cross-restart replay dedupe. The rewind window is one
#: boundary slot plus provider-side replay overlap, so a few hundred exact
#: identities cover it with a wide margin while keeping the cursor document
#: small and canonically serializable.
DEFAULT_RECENT_IDENTITY_LIMIT = 512
DEFAULT_BOUNDARY_IDENTITY_LIMIT = 256


# ---------------------------------------------------------------------------
# reconnect / recovery state machine
# ---------------------------------------------------------------------------

STATE_STARTING = "STARTING"
STATE_CURSOR_LOADING = "CURSOR_LOADING"
STATE_REPLAY_REQUIRED = "REPLAY_REQUIRED"
STATE_REPLAYING = "REPLAYING"
STATE_CATCHING_UP = "CATCHING_UP"
STATE_LIVE_HEALTHY = "LIVE_HEALTHY"
STATE_DISCONNECTED = "DISCONNECTED"
STATE_GAP_DETECTED = "GAP_DETECTED"
STATE_RECONNECTING = "RECONNECTING"
STATE_STOPPED = "STOPPED"

STATE_CURSOR_QUARANTINED = "CURSOR_QUARANTINED"
STATE_REPLAY_UNSUPPORTED = "REPLAY_UNSUPPORTED"
STATE_REPLAY_RETENTION_EXCEEDED = "REPLAY_RETENTION_EXCEEDED"
STATE_BACKFILL_UNAVAILABLE = "BACKFILL_UNAVAILABLE"
STATE_BACKFILL_PARTIAL = "BACKFILL_PARTIAL"
STATE_BACKFILL_FAILED = "BACKFILL_FAILED"
STATE_GAP_UNRESOLVED = "GAP_UNRESOLVED"
STATE_SUBSCRIPTION_IDENTITY_MISMATCH = "SUBSCRIPTION_IDENTITY_MISMATCH"
STATE_CURSOR_WRITE_FAILED = "CURSOR_WRITE_FAILED"
STATE_CURSOR_READBACK_FAILED = "CURSOR_READBACK_FAILED"

STREAM_STATES = (
    STATE_STARTING, STATE_CURSOR_LOADING, STATE_REPLAY_REQUIRED,
    STATE_REPLAYING, STATE_CATCHING_UP, STATE_LIVE_HEALTHY,
    STATE_DISCONNECTED, STATE_GAP_DETECTED, STATE_RECONNECTING, STATE_STOPPED,
    STATE_CURSOR_QUARANTINED, STATE_REPLAY_UNSUPPORTED,
    STATE_REPLAY_RETENTION_EXCEEDED, STATE_BACKFILL_UNAVAILABLE,
    STATE_BACKFILL_PARTIAL, STATE_BACKFILL_FAILED, STATE_GAP_UNRESOLVED,
    STATE_SUBSCRIPTION_IDENTITY_MISMATCH, STATE_CURSOR_WRITE_FAILED,
    STATE_CURSOR_READBACK_FAILED,
)

#: States in which the source is doing safe recovery work but MUST NOT be
#: displayed as healthy.
DEGRADED_STATES = (
    STATE_STARTING, STATE_CURSOR_LOADING, STATE_REPLAY_REQUIRED,
    STATE_REPLAYING, STATE_CATCHING_UP, STATE_DISCONNECTED,
    STATE_GAP_DETECTED, STATE_RECONNECTING,
)

RECOVERY_NOT_REQUIRED = "RECOVERY_NOT_REQUIRED"
RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
RECOVERY_IN_PROGRESS = "RECOVERY_IN_PROGRESS"
RECOVERY_CLOSED = "RECOVERY_CLOSED"
RECOVERY_FAILED = "RECOVERY_FAILED"

RECOVERY_STATUSES = (
    RECOVERY_NOT_REQUIRED, RECOVERY_REQUIRED, RECOVERY_IN_PROGRESS,
    RECOVERY_CLOSED, RECOVERY_FAILED,
)

# Closed-set recovery reasons. No raw provider payload ever reaches an
# artifact; these tokens are the entire vocabulary.
REASON_NONE = "NONE"
REASON_BOOTSTRAP_NEW_STATE_DIR = "BOOTSTRAP_NEW_STATE_DIR"
REASON_PROVIDER_DISCONNECT = "PROVIDER_DISCONNECT"
REASON_PROCESS_RESTART = "PROCESS_RESTART"
REASON_REPLAY_POSITION_TOO_OLD = "GRPC_REPLAY_POSITION_TOO_OLD"
REASON_REPLAY_UNAVAILABLE = "GRPC_REPLAY_UNAVAILABLE"
REASON_BACKFILL_REQUIRED = "GRPC_BACKFILL_REQUIRED"
REASON_BACKFILL_PARTIAL = "GRPC_BACKFILL_PARTIAL"
REASON_GAP_UNRECOVERABLE = "GRPC_GAP_UNRECOVERABLE"
REASON_SUBSCRIPTION_IDENTITY_MISMATCH = "SUBSCRIPTION_IDENTITY_MISMATCH"
REASON_CURSOR_QUARANTINED = "CURSOR_QUARANTINED"
REASON_CURSOR_WRITE_FAILED = "CURSOR_WRITE_FAILED"
REASON_CURSOR_READBACK_FAILED = "CURSOR_READBACK_FAILED"

REASON_SOURCE_NOT_LIVE_HEALTHY = "GRPC_SOURCE_NOT_LIVE_HEALTHY"

RECOVERY_REASONS = (
    REASON_NONE, REASON_BOOTSTRAP_NEW_STATE_DIR, REASON_PROVIDER_DISCONNECT,
    REASON_PROCESS_RESTART, REASON_REPLAY_POSITION_TOO_OLD,
    REASON_REPLAY_UNAVAILABLE, REASON_BACKFILL_REQUIRED,
    REASON_BACKFILL_PARTIAL, REASON_GAP_UNRECOVERABLE,
    REASON_SUBSCRIPTION_IDENTITY_MISMATCH, REASON_CURSOR_QUARANTINED,
    REASON_CURSOR_WRITE_FAILED, REASON_CURSOR_READBACK_FAILED,
    REASON_SOURCE_NOT_LIVE_HEALTHY,
)

# Operator-console display tokens.
DISPLAY_CONNECTED_LIVE_HEALTHY = "CONNECTED_LIVE_HEALTHY"
DISPLAY_CONNECTED_REPLAYING = "CONNECTED_REPLAYING"
DISPLAY_CONNECTED_BACKFILLING = "CONNECTED_BACKFILLING"
DISPLAY_DISCONNECTED_RETRYING = "DISCONNECTED_RETRYING"
DISPLAY_GAP_UNRESOLVED = "GAP_UNRESOLVED"
DISPLAY_CURSOR_QUARANTINED = "CURSOR_QUARANTINED"
DISPLAY_REPLAY_UNAVAILABLE = "REPLAY_UNAVAILABLE"
DISPLAY_RECOVERY_FAILED = "RECOVERY_FAILED"
DISPLAY_STOPPED = "STOPPED"

# Bootstrap policy for a state directory that has never held a cursor.
BOOTSTRAP_LIVE_HEAD = "BOOTSTRAP_LIVE_HEAD"
BOOTSTRAP_REFUSE = "BOOTSTRAP_REFUSE"
BOOTSTRAP_POLICIES = (BOOTSTRAP_LIVE_HEAD, BOOTSTRAP_REFUSE)


class StreamCursorWriteError(RuntimeError):
    """The cursor could not be persisted; the previous generation stands."""


# ---------------------------------------------------------------------------
# deterministic event identity
# ---------------------------------------------------------------------------

_IDENTITY_ABSENT = "-"


def _identity_part(value: object) -> str:
    """One identity component, rendered so no two distinct values collide."""

    if value is None:
        return _IDENTITY_ABSENT
    if isinstance(value, bool):
        raise ValueError("STREAM_EVENT_IDENTITY_BOOL_FORBIDDEN")
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text or any(char in text for char in "|\r\n"):
        raise ValueError("STREAM_EVENT_IDENTITY_COMPONENT_INVALID")
    return text


def build_stream_event_identity(
    *,
    slot: object,
    signature: object,
    transaction_index: object = None,
    outer_instruction_index: object = None,
    inner_instruction_index: object = None,
    flattened_instruction_index: object = None,
    migration_version: object = None,
    mint: object = None,
    pool: object = None,
) -> str:
    """Return the exact, deterministic identity of one stream event.

    The identity carries enough structure to distinguish every case the
    reconnect contract must separate:

      * separate transactions inside one slot (``signature``);
      * separate instruction sites inside one transaction (outer / inner /
        flattened instruction indices);
      * ``migrate`` from ``migrate_v2`` (``migration_version``);
      * multiple create-pool sites (mint + pool, which differ per site).

    Slot and signature alone are deliberately *not* sufficient: a slot may
    contain several qualifying transactions and a transaction may contain
    several qualifying instruction sites.
    """

    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("STREAM_EVENT_IDENTITY_SLOT_INVALID")
    signature_text = _identity_part(signature)
    if signature_text == _IDENTITY_ABSENT:
        raise ValueError("STREAM_EVENT_IDENTITY_SIGNATURE_REQUIRED")
    return "|".join((
        str(slot),
        signature_text,
        _identity_part(transaction_index),
        _identity_part(outer_instruction_index),
        _identity_part(inner_instruction_index),
        _identity_part(flattened_instruction_index),
        _identity_part(migration_version),
        _identity_part(mint),
        _identity_part(pool),
    ))


def slot_of_identity(identity: object) -> Optional[int]:
    """Recover the slot component of an identity, or ``None`` if unparseable."""

    if not isinstance(identity, str) or "|" not in identity:
        return None
    head = identity.split("|", 1)[0]
    try:
        value = int(head)
    except ValueError:
        return None
    return value if value >= 0 else None


# ---------------------------------------------------------------------------
# subscription identity binding
# ---------------------------------------------------------------------------

def compute_subscription_identity_digest(
    *,
    source_kind: str,
    commitment: str,
    transaction_filter_name: str,
    account_include: Sequence[str],
    account_exclude: Sequence[str] = (),
    account_required: Sequence[str] = (),
    vote: object = False,
    failed: object = False,
    program_id: str = "",
    migration_versions_supported: Sequence[str] = (),
    decoder_schema_version: str = "",
) -> str:
    """Digest the *meaning* of the subscription, never its credentials.

    A cursor is only reusable while the subscription still means the same
    thing.  Widening or narrowing the filter, changing commitment, or adding a
    migration discriminator version all change which events the stream would
    have delivered, so the old resume position no longer describes covered
    ground and must not be reused blindly.

    Endpoint locations and authentication values are deliberately excluded:
    they are secrets, and rotating one does not change what the subscription
    means.
    """

    body = {
        "domain": "phx2_stream_subscription_identity_v1",
        "source_kind": str(source_kind),
        "commitment": str(commitment),
        "transaction_filter_name": str(transaction_filter_name),
        "account_include": sorted(str(v) for v in account_include),
        "account_exclude": sorted(str(v) for v in account_exclude),
        "account_required": sorted(str(v) for v in account_required),
        "vote": bool(vote),
        "failed": bool(failed),
        "program_id": str(program_id),
        "migration_versions_supported": sorted(
            str(v) for v in migration_versions_supported),
        "decoder_schema_version": str(decoder_schema_version),
    }
    return _cpe.sha256_hex_text(_cpe.canonical_json(body))


# ---------------------------------------------------------------------------
# resume decision
# ---------------------------------------------------------------------------

#: Resume an existing position: the replacement stream carries ``from_slot``.
RESUME_ACTION_SUBSCRIBE_FROM_SLOT = "SUBSCRIBE_FROM_SLOT"
#: A genuinely new subscription with no prior durable position. This is the
#: ONLY state that may legitimately begin at the provider's live head.
RESUME_ACTION_BOOTSTRAP_LIVE_HEAD = "BOOTSTRAP_LIVE_HEAD"
#: The position is dead, quarantined or identity-mismatched. No source, no
#: channel and no subscription may be constructed; an operator must intervene.
RESUME_ACTION_REFUSE_TERMINAL = "REFUSE_TERMINAL"

RESUME_ACTIONS = (
    RESUME_ACTION_SUBSCRIBE_FROM_SLOT,
    RESUME_ACTION_BOOTSTRAP_LIVE_HEAD,
    RESUME_ACTION_REFUSE_TERMINAL,
)


@dataclass(frozen=True)
class ResumeDecision:
    """What the owner must do next, stated unambiguously.

    ``resume_from_slot()`` answers ``None`` for two completely different
    situations -- "there is no prior position, start at the live head" and "this
    position is dead, do not start anything".  The 2026-07-20 re-audit recorded
    a terminal replay-retention cursor silently becoming a live-head
    subscription on restart precisely because ordinary code cannot tell those
    two ``None`` answers apart.

    This type removes the ambiguity: :attr:`builds_source` is the single
    question the owner asks, and a terminal decision answers ``False`` while
    carrying the preserved boundary as evidence rather than as an instruction.
    """

    action: str
    from_slot: Optional[int] = None
    reason: str = REASON_NONE
    #: Preserved for observability only. NEVER used as a subscribe position
    #: when :attr:`builds_source` is ``False``.
    preserved_safe_slot: Optional[int] = None

    @property
    def builds_source(self) -> bool:
        """May the caller construct a source/channel/subscription at all?"""

        return self.action in (RESUME_ACTION_SUBSCRIBE_FROM_SLOT,
                               RESUME_ACTION_BOOTSTRAP_LIVE_HEAD)


@dataclass(frozen=True)
class StreamAttemptRecord:
    """The durably recorded intent of ONE resumable subscription attempt.

    Written before the stream is constructed, so the position that was safe
    *before* the attempt survives whatever the attempt does to the high-water
    mark -- including a provider that ignores ``from_slot``, a mid-attempt
    crash, an operator shutdown and a process restart.
    """

    subscription_identity_digest: str
    recovery_generation: int
    attempt_generation: int
    requested_from_slot: Optional[int]
    pinned_boundary_slot: Optional[int]
    expected_overlap_slot: Optional[int]
    recovery_status: str
    recorded_at_utc: Optional[str]


# ---------------------------------------------------------------------------
# cursor state
# ---------------------------------------------------------------------------

@dataclass
class StreamCursorState:
    """The durable resume position plus its recovery bookkeeping.

    Three *different* positions live here and must never be conflated:

    ``last_durable_slot``
        The **high-water mark**: the newest slot whose event was authoritatively
        handled.  It says nothing about whether every earlier slot was ever
        delivered.

    ``recovery_from_slot``
        The **earliest unresolved recovery boundary**: the safe position that
        was authoritative when the current recovery episode opened.  It is
        pinned for the whole episode; later disconnects never replace it.

    ``last_proven_replay_boundary_slot``
        The **provider-proven replay coverage boundary**: the last position a
        provider actually demonstrated it could replay from, by redelivering
        the boundary event that position names.

    Only the last of the three is evidence of coverage.  The pre-repair cursor
    resumed from the high-water mark, so a provider that ignored ``from_slot``
    and began beyond the boundary silently moved the authoritative position
    across a range that was never observed.

    Note that ordinary numeric slot continuity is deliberately NOT inferred:
    the subscription is transaction-filtered, so most slots legitimately carry
    no matching event.  Coverage is proven only by provider replay behaviour.
    """

    stream_source: str = STREAM_SOURCE_YELLOWSTONE
    subscription_identity_digest: str = ""
    commitment: str = "CONFIRMED"
    last_durable_slot: int = NO_SLOT
    last_durable_event_identity: Optional[str] = None
    last_durable_signature: Optional[str] = None
    processed_event_ids_in_boundary_slot: List[str] = field(default_factory=list)
    last_proven_replay_boundary_slot: Optional[int] = None
    stream_generation: int = 0
    recent_event_identities: List[str] = field(default_factory=list)
    updated_at_utc: Optional[str] = None
    last_disconnect_at_utc: Optional[str] = None
    recovery_required: bool = False
    recovery_from_slot: Optional[int] = None
    recovery_target_slot: Optional[int] = None
    recovery_generation: int = 0
    overlap_proven_generation: Optional[int] = None
    recovery_terminal: bool = False
    replay_first_available_slot: Optional[int] = None
    recovery_status: str = RECOVERY_NOT_REQUIRED
    recovery_reason: str = REASON_NONE
    # -- pre-attempt boundary record (R1) --------------------------------
    # Written BEFORE a stream attempt constructs anything, so the position
    # that was safe before the attempt cannot be lost by the attempt itself.
    attempt_generation: int = 0
    attempt_open: bool = False
    attempt_requested_from_slot: Optional[int] = None
    attempt_pinned_boundary_slot: Optional[int] = None
    replayed_event_count: int = 0
    duplicate_replay_count: int = 0
    backfilled_event_count: int = 0
    gap_detected_total: int = 0
    gap_closed_total: int = 0

    def has_position(self) -> bool:
        return isinstance(self.last_durable_slot, int) and self.last_durable_slot >= 0

    def clone(self) -> "StreamCursorState":
        """A detached copy, so a proposed mutation cannot leak on write failure."""

        return StreamCursorState.from_record(self.to_record())

    def safe_resume_slot(self) -> Optional[int]:
        """The authoritative position a replacement subscription must request.

        While a recovery episode is unresolved this is the preserved episode
        boundary, NOT the high-water mark: everything above the boundary may
        already have been processed idempotently, but nothing has proven the
        range in between was ever delivered.

        The pre-attempt pinned boundary participates on equal terms.  Before
        this repair an unresolved episode that carried no boundary silently
        substituted the high-water mark -- the exact state produced when a
        provider ignored ``from_slot`` on the first attempt after a restart --
        so the answer moved across a range nothing had ever observed.  The
        earliest unproven position always wins.
        """

        if not self.has_position():
            return None
        candidates = [int(self.last_durable_slot)]
        if self.recovery_required or self.attempt_open:
            for value in (self.recovery_from_slot,
                          self.attempt_pinned_boundary_slot):
                if isinstance(value, int) and not isinstance(value, bool) \
                        and value >= 0:
                    candidates.append(int(value))
        return min(candidates)

    def to_record(self) -> Dict[str, Any]:
        """Canonical, float-free record body (the digest is added by the store)."""

        return {
            "record_kind": CURSOR_RECORD_KIND,
            "stream_source": str(self.stream_source),
            "subscription_identity_digest": str(self.subscription_identity_digest),
            "commitment": str(self.commitment),
            "last_durable_slot": int(self.last_durable_slot),
            "last_durable_event_identity": self.last_durable_event_identity,
            "last_durable_signature": self.last_durable_signature,
            "processed_event_ids_in_boundary_slot": list(
                self.processed_event_ids_in_boundary_slot),
            "last_proven_replay_boundary_slot": (
                None if self.last_proven_replay_boundary_slot is None
                else int(self.last_proven_replay_boundary_slot)),
            "stream_generation": int(self.stream_generation),
            "recent_event_identities": list(self.recent_event_identities),
            "updated_at_utc": self.updated_at_utc,
            "last_disconnect_at_utc": self.last_disconnect_at_utc,
            "recovery_required": bool(self.recovery_required),
            "recovery_from_slot": (
                None if self.recovery_from_slot is None
                else int(self.recovery_from_slot)),
            "recovery_target_slot": (
                None if self.recovery_target_slot is None
                else int(self.recovery_target_slot)),
            "recovery_generation": int(self.recovery_generation),
            "overlap_proven_generation": (
                None if self.overlap_proven_generation is None
                else int(self.overlap_proven_generation)),
            "recovery_terminal": bool(self.recovery_terminal),
            "replay_first_available_slot": (
                None if self.replay_first_available_slot is None
                else int(self.replay_first_available_slot)),
            "recovery_status": str(self.recovery_status),
            "recovery_reason": str(self.recovery_reason),
            "attempt_generation": int(self.attempt_generation),
            "attempt_open": bool(self.attempt_open),
            "attempt_requested_from_slot": (
                None if self.attempt_requested_from_slot is None
                else int(self.attempt_requested_from_slot)),
            "attempt_pinned_boundary_slot": (
                None if self.attempt_pinned_boundary_slot is None
                else int(self.attempt_pinned_boundary_slot)),
            "replayed_event_count": int(self.replayed_event_count),
            "duplicate_replay_count": int(self.duplicate_replay_count),
            "backfilled_event_count": int(self.backfilled_event_count),
            "gap_detected_total": int(self.gap_detected_total),
            "gap_closed_total": int(self.gap_closed_total),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "StreamCursorState":
        return cls(
            stream_source=str(record.get("stream_source") or STREAM_SOURCE_YELLOWSTONE),
            subscription_identity_digest=str(
                record.get("subscription_identity_digest") or ""),
            commitment=str(record.get("commitment") or "CONFIRMED"),
            last_durable_slot=int(record.get("last_durable_slot", NO_SLOT)),
            last_durable_event_identity=record.get("last_durable_event_identity"),
            last_durable_signature=record.get("last_durable_signature"),
            processed_event_ids_in_boundary_slot=[
                str(v) for v in (
                    record.get("processed_event_ids_in_boundary_slot") or [])],
            # v2 field; a v1 document carries the never-assigned (always
            # ``None``) contiguity field, which is read forward unchanged.
            last_proven_replay_boundary_slot=(
                record.get("last_proven_replay_boundary_slot")
                if "last_proven_replay_boundary_slot" in record
                else record.get("last_contiguous_slot")),
            stream_generation=int(record.get("stream_generation", 0)),
            recent_event_identities=[
                str(v) for v in (record.get("recent_event_identities") or [])],
            updated_at_utc=record.get("updated_at_utc"),
            last_disconnect_at_utc=record.get("last_disconnect_at_utc"),
            recovery_required=bool(record.get("recovery_required", False)),
            recovery_from_slot=record.get("recovery_from_slot"),
            recovery_target_slot=record.get("recovery_target_slot"),
            recovery_generation=int(record.get("recovery_generation", 0)),
            overlap_proven_generation=record.get("overlap_proven_generation"),
            recovery_terminal=bool(record.get("recovery_terminal", False)),
            replay_first_available_slot=record.get("replay_first_available_slot"),
            recovery_status=str(record.get("recovery_status") or RECOVERY_NOT_REQUIRED),
            recovery_reason=str(record.get("recovery_reason") or REASON_NONE),
            # Absent in every pre-repair generation: an older document simply
            # carries no attempt record, which reads forward as "no attempt in
            # flight" and leaves the existing episode fields authoritative.
            attempt_generation=int(record.get("attempt_generation", 0)),
            attempt_open=bool(record.get("attempt_open", False)),
            attempt_requested_from_slot=record.get("attempt_requested_from_slot"),
            attempt_pinned_boundary_slot=record.get("attempt_pinned_boundary_slot"),
            replayed_event_count=int(record.get("replayed_event_count", 0)),
            duplicate_replay_count=int(record.get("duplicate_replay_count", 0)),
            backfilled_event_count=int(record.get("backfilled_event_count", 0)),
            gap_detected_total=int(record.get("gap_detected_total", 0)),
            gap_closed_total=int(record.get("gap_closed_total", 0)),
        )


# ---------------------------------------------------------------------------
# checkpoint-envelope adoption callbacks
# ---------------------------------------------------------------------------

_REQUIRED_INT_FIELDS = (
    "last_durable_slot", "stream_generation", "replayed_event_count",
    "duplicate_replay_count", "backfilled_event_count", "gap_detected_total",
    "gap_closed_total",
)

#: Present in every generation; absent in v1, so validated only when present.
_OPTIONAL_INT_FIELDS = (
    "last_contiguous_slot", "last_proven_replay_boundary_slot",
    "recovery_from_slot", "recovery_target_slot",
    "overlap_proven_generation", "replay_first_available_slot",
    "recovery_generation",
    "attempt_generation", "attempt_requested_from_slot",
    "attempt_pinned_boundary_slot",
)


def _usable_slot(record: Mapping[str, Any], name: str) -> Optional[int]:
    """The field's value only when it is a usable, nonnegative slot."""

    value = record.get(name)
    if value is None or isinstance(value, bool) or not isinstance(value, int) \
            or value < 0:
        return None
    return int(value)


def validate_cursor_cross_field_state(
    record: Mapping[str, Any]
) -> Tuple[bool, str]:
    """Refuse an authenticated document whose field groups contradict each other.

    BL-1 (2026-07-20 re-audit).  Every *writer* was repaired: an episode is
    opened only through :meth:`GrpcStreamCursorStore._open_episode_locked`,
    which always pins a boundary, and an attempt is opened only through
    :meth:`GrpcStreamCursorStore.begin_stream_attempt`, which always records
    what it asked for.  The *reader* checked field types and digests but never
    the relationships between the recovery, attempt and overlap-proof groups, so
    a hand-authored document could carry ``recovery_required=true`` with no
    boundary at all and still validate.

    That combination is not inert.  :meth:`StreamCursorState.safe_resume_slot`
    takes the minimum of the candidate positions, and with no boundary to
    contribute the only candidate left is ``last_durable_slot`` -- the
    high-water mark.  The document silently resolves to the self-certifying
    position the boundary contract exists to forbid.

    The rules below are deliberately derived from what the writers actually
    guarantee, not from what a complete document *could* contain:

      * a rule fires only when the fields it judges are PRESENT, so a v1
        document is never rejected for omitting a v2 field;
      * a rule is scoped to the writer that produces the state, so a legitimate
        shape -- a terminal retention cursor pinned by the pre-attempt record
        rather than by an episode, for instance -- still loads.
    """

    invalid = (False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID)

    has_position = int(record.get("last_durable_slot", NO_SLOT)) >= 0
    recovery_required = bool(record.get("recovery_required", False))
    recovery_from = _usable_slot(record, "recovery_from_slot")
    attempt_pinned = _usable_slot(record, "attempt_pinned_boundary_slot")
    attempt_requested = _usable_slot(record, "attempt_requested_from_slot")
    proven_boundary = _usable_slot(record, "last_proven_replay_boundary_slot")

    attempt_open = bool(record.get("attempt_open", False))
    attempt_generation = record.get("attempt_generation")
    has_recovery_generation = "recovery_generation" in record
    recovery_generation = int(record.get("recovery_generation", 0))
    overlap_generation = record.get("overlap_proven_generation")

    # 1. A claimed recovery must name somewhere to recover FROM.
    #    Either boundary counts: an episode pin, or the pre-attempt pin written
    #    before the stream existed. Scoped to documents that hold a position --
    #    ``mark_recovery_failed`` legitimately raises the flag on a cursor that
    #    never committed one, and there is no covered ground to protect there.
    if recovery_required and has_position:
        if recovery_from is None and attempt_pinned is None:
            return invalid

    # 2. ``_open_episode_locked`` is the only writer of ``recovery_from_slot``.
    #    It allocates a NEW episode generation when it opens one, so a boundary
    #    normally implies generation >= 1.
    #
    #    There is exactly one other shape, and it is legitimate.
    #    ``mark_recovery_failed`` may raise ``recovery_required`` on a cursor
    #    that never opened an episode -- generation still 0, no boundary yet.
    #    When the recovery path later records the boundary that failure owes,
    #    ``_open_episode_locked`` takes its continuation branch and pins
    #    ``recovery_from_slot`` WITHOUT allocating a generation, because
    #    allocating one would re-bind the episode identity in the middle of a
    #    recovery and orphan the durable recovery episode that already
    #    references generation 0.  The result is a boundary at generation 0.
    #
    #    That shape was rejected, and because the boundary is re-proposed on
    #    every commit the cursor became permanently unwritable: 94,959
    #    checkpoint attempts, 0 successes, STRUCTURAL_CHECKPOINT_FAILURE, with
    #    the durable document frozen (2026-07-26 Stage-9 run).  Permit exactly
    #    the bootstrap continuation and nothing else: it must still CLAIM the
    #    recovery, and it must never have proven an overlap -- a proof is what
    #    retires an episode, and an episode that proved something had to have
    #    been allocated.
    if recovery_from is not None and has_recovery_generation \
            and recovery_generation < 1:
        bootstrap_continuation = (
            recovery_required
            and record.get("overlap_proven_generation") is None)
        if not bootstrap_continuation:
            return invalid

    # 3. An open attempt is fully recorded, or it is not an attempt.
    if attempt_open:
        if attempt_requested is None or attempt_pinned is None:
            return invalid
        if attempt_generation is None or isinstance(attempt_generation, bool) \
                or not isinstance(attempt_generation, int) \
                or attempt_generation < 1:
            return invalid
        # The pin is ``min(pre_attempt_safe, requested)``: it can never sit
        # above the position the attempt asked the provider for.
        if attempt_pinned > attempt_requested:
            return invalid

    # 4. An overlap proof binds to a boundary and to an attempt that happened.
    if overlap_generation is not None:
        if proven_boundary is None:
            return invalid
        if isinstance(overlap_generation, bool) \
                or not isinstance(overlap_generation, int) \
                or overlap_generation < 0:
            return invalid
        if has_recovery_generation and overlap_generation > recovery_generation:
            return invalid
        # A proof must descend from something that actually requested a
        # position -- a recovery episode OR a recorded stream attempt.
        # ``mark_overlap_proven`` refuses outright unless one of the two is
        # open, so a proof with neither behind it cannot have been written.
        # Note that the attempt group alone proves nothing about which path
        # ran: ``to_record`` emits ``attempt_open`` in every v2 document,
        # including ones whose coverage was driven purely by the episode.
        attempt_recorded = (isinstance(attempt_generation, int)
                            and not isinstance(attempt_generation, bool)
                            and attempt_generation >= 1)
        if recovery_generation < 1 and not attempt_recorded:
            return invalid
        # ``mark_overlap_proven`` clears ``recovery_required`` in the same
        # breath as it records the proof: one episode cannot be both.
        if recovery_required and has_recovery_generation \
                and overlap_generation == recovery_generation:
            return invalid

    # 5. Terminal recovery must say why, and must remain a recovery. A terminal
    #    state that reads as "no recovery needed" is exactly the shape that
    #    becomes a live-head bootstrap on the next restart.
    if bool(record.get("recovery_terminal", False)):
        if str(record.get("recovery_reason") or REASON_NONE) == REASON_NONE:
            return invalid
        if not recovery_required:
            return invalid
        if str(record.get("recovery_status") or "") != RECOVERY_FAILED:
            return invalid

    return True, ""


def validate_cursor_record(record: Mapping[str, Any]) -> Tuple[bool, str]:
    """Kind-specific record validation for the checkpoint envelope."""

    if record.get("record_kind") != CURSOR_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    for name in _REQUIRED_INT_FIELDS:
        value = record.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if int(record.get("last_durable_slot", NO_SLOT)) < NO_SLOT:
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for name in ("replayed_event_count", "duplicate_replay_count",
                 "backfilled_event_count", "gap_detected_total",
                 "gap_closed_total", "stream_generation"):
        if int(record.get(name, 0)) < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for name in _OPTIONAL_INT_FIELDS:
        value = record.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if not isinstance(record.get("subscription_identity_digest"), str):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    if not _cpe.is_sha256_digest(record.get("subscription_identity_digest")):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    if record.get("recovery_status") not in RECOVERY_STATUSES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if record.get("recovery_reason") not in RECOVERY_REASONS:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if not isinstance(record.get("recovery_required"), bool):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    # v2 only; a v1 document simply omits it.
    if "recovery_terminal" in record and not isinstance(
            record.get("recovery_terminal"), bool):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    # Post-repair only; every earlier generation simply omits it.
    if "attempt_open" in record and not isinstance(
            record.get("attempt_open"), bool):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    for name in ("processed_event_ids_in_boundary_slot",
                 "recent_event_identities"):
        value = record.get(name)
        if not isinstance(value, list) or any(
                not isinstance(item, str) or not item for item in value):
            return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    identity = record.get("last_durable_event_identity")
    if identity is not None and (not isinstance(identity, str) or not identity):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    # A committed position must name the event that justified it.
    if int(record.get("last_durable_slot", NO_SLOT)) >= 0 and identity is None:
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    if identity is not None:
        identity_slot = slot_of_identity(identity)
        if identity_slot is None:
            return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
        if identity_slot != int(record.get("last_durable_slot", NO_SLOT)):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    if record.get("updated_at_utc") is not None and _cpe.parse_utc_timestamp(
            record.get("updated_at_utc")) is None:
        return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    if record.get("last_disconnect_at_utc") is not None and _cpe.parse_utc_timestamp(
            record.get("last_disconnect_at_utc")) is None:
        return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    if not _cpe.record_digest_is_valid(CHECKPOINT_KIND_STREAM_CURSOR, record):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    # Authenticity is established above; only now is it meaningful to ask
    # whether what was authenticated is internally consistent (BL-1).
    return validate_cursor_cross_field_state(record)


def cursor_record_identity(record: Mapping[str, Any]) -> Tuple:
    """The cursor is a singleton document: exactly one record per generation."""

    kind = record.get("record_kind")
    if kind != CURSOR_RECORD_KIND:
        raise ValueError("STREAM_CURSOR_RECORD_KIND_INVALID")
    return (CURSOR_RECORD_KIND,)


def classify_cursor_checkpoint_file(
    path: object, *, validation_now_utc: Optional[str] = None
) -> _cpe.FileClassification:
    """Classify one cursor file without mutating it.

    No ``legacy_classifier`` is supplied: the cursor is introduced *with* the
    authenticated envelope, so there is no pre-envelope encoding to migrate.
    Any non-envelope content in the cursor path is therefore corruption, never
    a legacy generation -- and corruption must never be mistaken for a new
    install.
    """

    return _cpe.classify_checkpoint_file(
        path,
        kind=CHECKPOINT_KIND_STREAM_CURSOR,
        supported_schema_versions=SUPPORTED_CURSOR_SCHEMA_VERSIONS,
        record_validator=validate_cursor_record,
        identity_fn=cursor_record_identity,
        validation_now_utc=validation_now_utc,
    )


def _selected_cursor_record(
    classification: _cpe.FileClassification,
) -> Optional[Mapping[str, Any]]:
    for record in classification.records or []:
        if record.get("record_kind") == CURSOR_RECORD_KIND:
            return record
    return None


def cursor_cross_generation_check(
    selected: _cpe.FileClassification, other: _cpe.FileClassification
) -> Tuple[bool, Optional[str], int]:
    """Refuse an unexplained cursor rewind between two authenticated generations.

    A newer generation that names an *older* slot under the *same* subscription
    identity would silently re-open a window the operator believes was already
    covered.  A rewind under a *changed* subscription identity is legitimate --
    the subscription now means something else and the position is deliberately
    re-anchored -- so identity is compared before the slot is judged.
    """

    selected_record = _selected_cursor_record(selected)
    other_record = _selected_cursor_record(other)
    if selected_record is None or other_record is None:
        return True, None, 0
    selected_gen = selected.generation
    other_gen = other.generation
    if not isinstance(selected_gen, int) or not isinstance(other_gen, int):
        return True, None, 0
    if selected_gen <= other_gen:
        return True, None, 0
    if (selected_record.get("subscription_identity_digest")
            != other_record.get("subscription_identity_digest")):
        return True, None, 0
    selected_slot = int(selected_record.get("last_durable_slot", NO_SLOT))
    other_slot = int(other_record.get("last_durable_slot", NO_SLOT))
    if selected_slot < other_slot:
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID, 1
    return True, None, 0


# ---------------------------------------------------------------------------
# durable cursor store
# ---------------------------------------------------------------------------

class GrpcStreamCursorStore:
    """Authenticated, atomically rotated resume position for the one stream.

    Reuses the commit-``9745fd9`` checkpoint primitives verbatim: temp write,
    flush, fsync, full read-back re-validation, backup rotation, atomic
    replace, directory fsync, and a final confirm.  A quarantined cursor is a
    *write lockdown* as well as a status, so corrupt evidence is never
    overwritten by a fresh generation.
    """

    def __init__(
        self,
        *,
        primary_path: object,
        subscription_identity_digest: str,
        commitment: str = "CONFIRMED",
        stream_source: str = STREAM_SOURCE_YELLOWSTONE,
        recent_identity_limit: int = DEFAULT_RECENT_IDENTITY_LIMIT,
        boundary_identity_limit: int = DEFAULT_BOUNDARY_IDENTITY_LIMIT,
        now_iso_fn: Callable[[], str] = _cpe.utc_now_iso,
        persist_batch_max_events: int = 1,
        persist_batch_max_seconds: float = 0.0,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = Path(primary_path)
        self._backup = self._primary.with_name(
            self._primary.name + CURSOR_BACKUP_SUFFIX)
        self._identity_digest = str(subscription_identity_digest)
        self._recent_limit = max(1, int(recent_identity_limit))
        self._boundary_limit = max(1, int(boundary_identity_limit))
        self._now_iso = now_iso_fn
        self._lock = threading.RLock()

        self.state = StreamCursorState(
            stream_source=str(stream_source),
            subscription_identity_digest=self._identity_digest,
            commitment=str(commitment),
        )
        self._generation = 0
        self._envelope_digest: Optional[str] = None
        self._created_at: Optional[str] = None
        self._loaded = False
        self._quarantined = False
        self._quarantine_reason: Optional[str] = None
        self._write_locked = False
        self._identity_mismatch = False
        self._loaded_identity_digest: Optional[str] = None
        # What the CURRENT attempt actually asked the provider for. Tracked
        # separately from the episode boundary so an overlap proof is checked
        # against the boundary it claims to prove, never against itself.
        self._requested_from_slot: Optional[int] = None
        self._requested_generation: Optional[int] = None

        self.load_result = _cpe.CheckpointLoadResult(
            checkpoint_kind=CHECKPOINT_KIND_STREAM_CURSOR)
        self.cursor_write_failed_total = 0
        self.cursor_readback_failed_total = 0

        # -- bounded periodic (batched) persistence --------------------------
        # Throughput remediation. ``commit_event`` advances the IN-MEMORY
        # position on every event (so intra-session reconnect dedupe sees every
        # processed event) but writes the durable checkpoint only on a small
        # bounded trigger: ``persist_batch_max_events`` commits OR
        # ``persist_batch_max_seconds`` elapsed since the oldest pending commit,
        # whichever first.  An admitted migration and every recovery/terminal/
        # shutdown transition force a synchronous flush, so the batch window
        # only ever contains deterministic rejections -- whose reserve/fee
        # re-ingestion after a crash-replay is idempotent.  Defaults (1 / 0.0)
        # reproduce the pre-fix flush-every-event behaviour exactly.
        self._batch_max_events = max(1, int(persist_batch_max_events))
        self._batch_max_seconds = max(0.0, float(persist_batch_max_seconds))
        self._batching_enabled = (
            self._batch_max_events > 1 or self._batch_max_seconds > 0.0)
        self._monotonic = monotonic_fn
        self._pending_commit_events = 0
        self._dirty = False
        self._last_flushed_slot = NO_SLOT
        self._last_flush_monotonic = monotonic_fn()
        self._oldest_pending_monotonic: Optional[float] = None
        # checkpoint observability (mirrors the ATH/watch durability contract)
        self.cursor_checkpoint_attempted_total = 0
        self.cursor_checkpoint_succeeded_total = 0
        self.cursor_checkpoint_failed_total = 0
        self.cursor_checkpoint_deferred_total = 0
        self.cursor_checkpoint_forced_flush_total = 0
        self.cursor_checkpoint_write_retried_total = 0
        self.cursor_checkpoint_transient_failure_total = 0
        self.cursor_checkpoint_last_write_attempts = 0
        self._checkpoint_latencies_ms: List[float] = []
        self._last_checkpoint_bytes = 0
        self.cursor_durability_status = _cpe.CHECKPOINT_DURABILITY_HEALTHY
        self.cursor_last_success_utc: Optional[str] = None
        self.cursor_last_failure_category: Optional[str] = None

    # -- properties ------------------------------------------------------

    @property
    def primary_path(self) -> Path:
        return self._primary

    @property
    def backup_path(self) -> Path:
        return self._backup

    @property
    def quarantined(self) -> bool:
        return self._quarantined

    @property
    def quarantine_reason(self) -> Optional[str]:
        return self._quarantine_reason

    @property
    def subscription_identity_matches(self) -> bool:
        return not self._identity_mismatch

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def pending_commit_events(self) -> int:
        """Commits advanced in memory but not yet written to disk."""

        return self._pending_commit_events

    @property
    def last_flushed_slot(self) -> int:
        """The durably-flushed high-water slot (``NO_SLOT`` if none)."""

        return self._last_flushed_slot

    # -- load ------------------------------------------------------------

    def load(self, *, validation_now_utc: Optional[str] = None) -> _cpe.CheckpointLoadResult:
        """Restore the authenticated cursor through the exact load matrix.

        ``CHECKPOINT_NOT_FOUND`` (both files genuinely absent) is the only
        state that permits the documented bootstrap policy.  Any *existing*
        but invalid pair quarantines and locks writes -- a corrupt cursor is
        never silently treated as a new install.
        """

        with self._lock:
            primary = classify_cursor_checkpoint_file(
                self._primary, validation_now_utc=validation_now_utc)
            backup = classify_cursor_checkpoint_file(
                self._backup, validation_now_utc=validation_now_utc)
            decision = _cpe.resolve_checkpoint_pair(
                primary, backup,
                cross_generation_check=cursor_cross_generation_check)

            result = _cpe.CheckpointLoadResult(
                checkpoint_kind=CHECKPOINT_KIND_STREAM_CURSOR,
                checkpoint_status=decision.status,
                checkpoint_primary_status=primary.state,
                checkpoint_backup_status=backup.state,
                checkpoint_recovered_from_backup=decision.recovered_from_backup,
                checkpoint_quarantined=decision.quarantined,
                checkpoint_quarantine_reason=decision.quarantine_reason,
                checkpoint_files_found=(
                    primary.state != _cpe.FILE_MISSING
                    or backup.state != _cpe.FILE_MISSING),
                checkpoint_source_selected=decision.selected,
                checkpoint_primary_invalid_reason=decision.primary_invalid_reason,
                checkpoint_backup_invalid_reason=decision.backup_invalid_reason,
                checkpoint_generation_conflict_total=(
                    1 if decision.generation_conflict else 0),
                checkpoint_last_validated_at_utc=self._now_iso(),
                checkpoint_notes=list(decision.notes),
            )

            self._loaded = True
            if decision.status == _cpe.CHECKPOINT_NOT_FOUND:
                self.load_result = result
                return result

            if decision.quarantined:
                self._quarantined = True
                self._quarantine_reason = decision.quarantine_reason
                # Write lockdown: never overwrite corrupt evidence.
                self._write_locked = True
                self.load_result = result
                return result

            selected = primary if decision.selected == "primary" else backup
            record = _selected_cursor_record(selected)
            if record is None:
                self._quarantined = True
                self._quarantine_reason = _cpe.QUARANTINE_RECORD_COUNT_MISMATCH
                self._write_locked = True
                result.checkpoint_quarantined = True
                result.checkpoint_status = _cpe.CHECKPOINT_QUARANTINED
                result.checkpoint_quarantine_reason = self._quarantine_reason
                self.load_result = result
                return result

            restored = StreamCursorState.from_record(record)
            self._loaded_identity_digest = restored.subscription_identity_digest
            if restored.subscription_identity_digest != self._identity_digest:
                # The subscription no longer means what it meant when this
                # position was written: refuse a blind resume.
                self._identity_mismatch = True
                restored.recovery_required = True
                restored.recovery_status = RECOVERY_FAILED
                restored.recovery_reason = REASON_SUBSCRIPTION_IDENTITY_MISMATCH

            self.state = restored
            # The restored high-water mark IS the durably flushed position: a
            # batched write only ever lags this in memory, never on disk.
            self._last_flushed_slot = (
                int(restored.last_durable_slot) if restored.has_position()
                else NO_SLOT)
            # An attempt record still marked open means the previous process
            # died, was killed, or was stopped between constructing a stream
            # and proving its coverage. Nothing proved the requested position
            # was honoured, so the episode is reopened at the pinned boundary
            # rather than allowing the high-water mark to become authoritative.
            if restored.attempt_open and restored.has_position():
                self._open_episode_locked(
                    boundary=self._attempt_boundary_locked(),
                    reason=REASON_PROVIDER_DISCONNECT)
                if restored.recovery_status == RECOVERY_NOT_REQUIRED:
                    restored.recovery_status = RECOVERY_REQUIRED
            self._generation = int(selected.header.get("generation") or 0) \
                if selected.header else 0
            self._envelope_digest = (
                selected.envelope_digest if selected.header else None)
            self._created_at = (
                selected.header.get("created_at_utc") if selected.header else None)
            result.checkpoint_generation = self._generation
            result.checkpoint_schema_version = (
                selected.header.get("schema_version") if selected.header else None)
            result.checkpoint_records_validated = 1
            self.load_result = result
            return result

    # -- persist ---------------------------------------------------------

    def _persist_state_locked(self, proposed: "StreamCursorState") -> None:
        """Persist a PROPOSED state, publishing it in memory only on success.

        Ordering is deliberate and load-bearing for the resume contract:

            derive proposed -> canonical serialise -> temp write -> flush/fsync
            -> atomic replace -> read back -> re-validate -> PUBLISH in memory

        A failed persistence therefore leaves both the durable document *and*
        ``self.state`` at the last valid generation.  The pre-repair ordering
        mutated in-memory state first, so a write failure left the in-process
        resume position ahead of anything that had ever been made durable.
        """

        if self._write_locked:
            raise StreamCursorWriteError(REASON_CURSOR_QUARANTINED)
        now = self._now_iso()
        proposed.updated_at_utc = now
        proposed.subscription_identity_digest = self._identity_digest
        record = proposed.to_record()
        record["record_digest"] = _cpe.build_record_digest(
            CHECKPOINT_KIND_STREAM_CURSOR, record)
        header = _cpe.build_envelope_header(
            checkpoint_kind=CHECKPOINT_KIND_STREAM_CURSOR,
            schema_version=STREAM_CURSOR_SCHEMA_CURRENT,
            payload_encoding=_cpe.PAYLOAD_ENCODING_DOCUMENT,
            generation=self._generation + 1,
            record_digests=[record["record_digest"]],
            created_at_utc=self._created_at or now,
            updated_at_utc=now,
            previous_generation_digest=self._envelope_digest,
            source_id=self._primary.name,
        )
        self.cursor_checkpoint_attempted_total += 1
        started = self._monotonic()
        try:
            write_outcome = _cpe.write_checkpoint_generation_resilient(
                primary_path=self._primary,
                backup_path=self._backup,
                header=header,
                records=[record],
                classify=lambda p: classify_cursor_checkpoint_file(p),
            )
            self.cursor_checkpoint_last_write_attempts = int(
                write_outcome.attempts)
            self.cursor_checkpoint_write_retried_total += int(
                write_outcome.retried)
            self.cursor_checkpoint_transient_failure_total += int(
                write_outcome.transient_failures)
        except _cpe.CheckpointWriteError as exc:
            text = str(exc)
            self.cursor_checkpoint_failed_total += 1
            self.cursor_durability_status = _cpe.CHECKPOINT_DURABILITY_DEGRADED
            self.cursor_last_failure_category = (
                _cpe.classify_checkpoint_write_error(exc))
            if "READBACK_INVALID" in text or "CONFIRM_INVALID" in text:
                self.cursor_readback_failed_total += 1
                raise StreamCursorWriteError(REASON_CURSOR_READBACK_FAILED) from exc
            self.cursor_write_failed_total += 1
            raise StreamCursorWriteError(REASON_CURSOR_WRITE_FAILED) from exc
        except OSError as exc:
            self.cursor_checkpoint_failed_total += 1
            self.cursor_durability_status = _cpe.CHECKPOINT_DURABILITY_DEGRADED
            self.cursor_last_failure_category = (
                _cpe.classify_checkpoint_write_error(exc))
            self.cursor_write_failed_total += 1
            raise StreamCursorWriteError(REASON_CURSOR_WRITE_FAILED) from exc
        # Read-back and confirm both succeeded: publish.
        self.state = proposed
        self._generation = int(header["generation"])
        self._envelope_digest = str(header["envelope_digest"])
        self._created_at = self._created_at or now
        # Durable marker + batch bookkeeping advance ONLY on a confirmed write.
        self.cursor_checkpoint_succeeded_total += 1
        self.cursor_durability_status = _cpe.CHECKPOINT_DURABILITY_HEALTHY
        self.cursor_last_success_utc = now
        self.cursor_last_failure_category = None
        self._dirty = False
        self._pending_commit_events = 0
        self._oldest_pending_monotonic = None
        self._last_flush_monotonic = self._monotonic()
        self._last_flushed_slot = (
            int(self.state.last_durable_slot) if self.state.has_position()
            else NO_SLOT)
        elapsed_ms = max(0.0, (self._last_flush_monotonic - started) * 1000.0)
        self._checkpoint_latencies_ms.append(elapsed_ms)
        if len(self._checkpoint_latencies_ms) > 512:
            del self._checkpoint_latencies_ms[:-512]
        try:
            self._last_checkpoint_bytes = int(self._primary.stat().st_size)
        except OSError:
            pass

    def _persist_locked(self) -> None:
        """Persist the CURRENT in-memory state.

        Used by the recovery-claim mutators, where the in-memory claim is
        deliberately authoritative even if it cannot be written: claiming a gap
        that was never persisted is the conservative direction, whereas
        advancing a position that was never persisted is not.
        """

        self._persist_state_locked(self.state)

    def persist(self) -> None:
        with self._lock:
            self._persist_locked()

    # -- bounded periodic (batched) flush --------------------------------

    def _flush_threshold_reached_locked(self) -> bool:
        """Has the pending batch reached its count OR elapsed-time bound?"""

        if self._pending_commit_events >= self._batch_max_events:
            return True
        if self._batch_max_seconds > 0.0 \
                and self._oldest_pending_monotonic is not None:
            age = self._monotonic() - self._oldest_pending_monotonic
            if age >= self._batch_max_seconds:
                return True
        return False

    def _flush_pending_locked(self, *, forced: bool) -> bool:
        """Write the current in-memory state if any commit is unflushed.

        Returns ``True`` when nothing was pending or the pending state was
        flushed successfully; ``False`` when a pending flush was attempted and
        failed.  A failure keeps the in-memory position ahead of disk and the
        pending flag set (the next trigger retries), surfacing the condition
        through the durability status and counters rather than raising: a
        cursor flush must never crash the single consumption thread.
        """

        if not self._dirty:
            return True
        if forced:
            self.cursor_checkpoint_forced_flush_total += 1
        try:
            self._persist_state_locked(self.state)
            return True
        except StreamCursorWriteError:
            return False

    def flush_if_pending(self) -> bool:
        """Force any deferred cursor commits to disk (cooperative flush).

        Called at every stream boundary and on cooperative shutdown so the
        durable resume position is current before the process may exit.  Never
        raises; a failed flush is observable via :attr:`cursor_durability_status`
        and the checkpoint counters.
        """

        with self._lock:
            return self._flush_pending_locked(forced=True)

    # -- cursor advancement ---------------------------------------------

    def is_duplicate(self, identity: str) -> bool:
        """Was this exact event already durably processed?

        Covers replay overlap, reconnect and process restart: the boundary-slot
        identities and the bounded recent-identity ring both survive a restart
        because they live inside the authenticated cursor document.
        """

        with self._lock:
            return (identity in self.state.processed_event_ids_in_boundary_slot
                    or identity in self.state.recent_event_identities)

    def commit_event(
        self,
        *,
        slot: int,
        identity: str,
        signature: Optional[str] = None,
        replayed: bool = False,
        detail_identity: Optional[str] = None,
    ) -> None:
        """Advance the durable position to one authoritatively handled event.

        The caller must only reach this after the event is recoverable
        downstream (an admitted migration whose handoff is durable, or a
        deterministically classified rejection).  Slots never move backwards:
        a replayed event at or below the committed slot updates only the
        duplicate bookkeeping.

        ``identity`` is the *replay-skip key* -- the transaction-scoped
        identity the caller can compute before decoding, so a replayed update
        is recognised without re-running any side effect.  ``detail_identity``
        is the finer instruction-site identity of an admitted migration; it is
        recorded as the named durable event and tracked alongside the skip key
        so multiple sites remain individually distinguishable.
        """

        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise ValueError("STREAM_CURSOR_SLOT_INVALID")
        if not isinstance(identity, str) or not identity:
            raise ValueError("STREAM_CURSOR_IDENTITY_INVALID")
        with self._lock:
            # Mutate a DETACHED copy: an event beyond an unresolved recovery
            # boundary may legitimately advance the high-water mark, but a
            # failed persist must leave the published state exactly where the
            # last durable generation left it.
            state = self.state.clone()
            if replayed:
                state.replayed_event_count += 1
            identities = [identity]
            if detail_identity and detail_identity != identity:
                identities.append(detail_identity)
            if slot > state.last_durable_slot:
                # A new boundary slot: previous boundary identities are now
                # strictly below the committed position and no longer needed
                # to suppress overlap for this slot.
                state.last_durable_slot = slot
                state.processed_event_ids_in_boundary_slot = list(identities)
                state.last_durable_event_identity = detail_identity or identity
                if signature is not None:
                    state.last_durable_signature = str(signature)
            elif slot == state.last_durable_slot:
                for value in identities:
                    if value not in state.processed_event_ids_in_boundary_slot:
                        state.processed_event_ids_in_boundary_slot.append(value)
                while len(state.processed_event_ids_in_boundary_slot) > self._boundary_limit:
                    state.processed_event_ids_in_boundary_slot.pop(0)
                state.last_durable_event_identity = detail_identity or identity
                if signature is not None:
                    state.last_durable_signature = str(signature)
            # A slot strictly below the committed position is replay overlap
            # only: the durable position must never regress.
            for value in identities:
                if value not in state.recent_event_identities:
                    state.recent_event_identities.append(value)
            while len(state.recent_event_identities) > self._recent_limit:
                state.recent_event_identities.pop(0)
            if not self._batching_enabled:
                # Default / pre-fix behaviour: one durable generation per event.
                # ``self.state`` advances only on a confirmed write.
                self._persist_state_locked(state)
                return
            # Batched: publish the position IN MEMORY immediately so a
            # same-process reconnect dedupes every processed event, then flush
            # to disk on a bounded trigger.  An admitted migration
            # (``detail_identity`` present) is effectful and is ALWAYS flushed
            # synchronously, so the batch window only ever holds deterministic
            # rejections.  A deferred flush never advances the durable marker:
            # a crash simply replays the window, which exact-identity dedupe and
            # idempotent reserve/fee re-ingestion absorb.
            self.state = state
            self._pending_commit_events += 1
            self._dirty = True
            if self._oldest_pending_monotonic is None:
                self._oldest_pending_monotonic = self._monotonic()
            # Force a synchronous flush when the event is effectful (an admitted
            # migration carries ``detail_identity``) OR while no durable position
            # exists yet, so a brand-new subscription establishes its first
            # durable resume slot on the very first event instead of leaving a
            # whole batch window with nothing recoverable but a live-head
            # bootstrap.
            forced = detail_identity is not None or self._last_flushed_slot < 0
            if forced or self._flush_threshold_reached_locked():
                self._flush_pending_locked(forced=forced)
            else:
                self.cursor_checkpoint_deferred_total += 1

    def record_duplicate_replay(self, count: int = 1) -> None:
        with self._lock:
            self.state.duplicate_replay_count += max(0, int(count))

    # -- recovery bookkeeping -------------------------------------------

    def _attempt_boundary_locked(
        self, attempted_from_slot: object = None) -> Optional[int]:
        """The boundary this episode owes, taken from the ATTEMPT, not the mark.

        Preference order, most explicit first: the position the caller states it
        actually requested, then the boundary pinned before the current attempt
        started.  ``last_durable_slot`` is deliberately absent -- deriving the
        boundary from the high-water mark is the defect this exists to remove.
        """

        for value in (attempted_from_slot,
                      self.state.attempt_pinned_boundary_slot):
            if isinstance(value, int) and not isinstance(value, bool) \
                    and value >= 0:
                return int(value)
        return None

    def _open_episode_locked(self, *, boundary: Optional[int],
                             reason: str) -> None:
        """Open or continue ONE recovery episode without ever moving it.

        Three branches, and only the first ALLOCATES an episode:

        * no recovery claimed yet -> allocate the next generation and pin the
          boundary;
        * recovery already claimed but no boundary recorded -> this is the
          continuation of a requirement raised by :meth:`mark_recovery_failed`
          before any episode existed.  Pin the boundary the failure owes and
          deliberately do NOT allocate: the durable recovery episode binds
          itself to ``recovery_generation``, so allocating here would re-bind
          the identity mid-recovery and orphan it.  Generation therefore stays
          0 for a bootstrap episode, which
          :func:`validate_cursor_cross_field_state` rule 2 permits explicitly;
        * recovery already claimed with a boundary -> keep the EARLIEST, never
          move it forward.
        """

        state = self.state
        if not state.has_position():
            return
        pinned = boundary if boundary is not None else int(state.last_durable_slot)
        # The episode always owes the EARLIEST unproven position.
        pinned = min(pinned, int(state.last_durable_slot))
        if not state.recovery_required:
            state.recovery_generation += 1
            state.recovery_from_slot = pinned
            state.overlap_proven_generation = None
            state.recovery_reason = reason
        elif state.recovery_from_slot is None:
            # Bootstrap continuation -- generation intentionally unchanged.
            state.recovery_from_slot = pinned
        else:
            state.recovery_from_slot = min(int(state.recovery_from_slot), pinned)
        state.recovery_required = True

    def begin_stream_attempt(
        self, *, requested_from_slot: Optional[int],
        subscription_identity_digest: Optional[str] = None,
    ) -> StreamAttemptRecord:
        """Durably pin the pre-attempt safe boundary BEFORE the stream exists.

        This is the repair for the restart-time half of the reconnect defect.
        The steady-state fix preserved a boundary only while an episode was
        already open; on the first attempt after a restart or a clean shutdown
        nothing was pinned, so a provider that ignored ``from_slot`` advanced
        the high-water mark and the settling ``mark_disconnect`` then adopted
        the moved position as the episode boundary.  The unobserved range was
        abandoned permanently and the wrong state survived another restart.

        Recording the intent first inverts that: whatever the attempt does to
        the high-water mark, the position that was authoritative *before* it
        remains the boundary until an exact replay proof retires it.

        Raises :class:`StreamCursorWriteError` when the record cannot be made
        durable.  The caller MUST NOT process events in that case: an event
        that advances the authoritative position while the position it moved
        away from was never written is exactly the loss this prevents.
        """

        if requested_from_slot is not None and (
                isinstance(requested_from_slot, bool)
                or not isinstance(requested_from_slot, int)
                or requested_from_slot < 0):
            raise ValueError("STREAM_CURSOR_ATTEMPT_SLOT_INVALID")
        with self._lock:
            state = self.state
            pre_attempt_safe = state.safe_resume_slot()
            state.attempt_generation += 1
            state.attempt_requested_from_slot = (
                None if requested_from_slot is None else int(requested_from_slot))
            if requested_from_slot is None:
                # A genuinely new subscription claims no prior coverage, so it
                # has no earlier position to protect.
                state.attempt_open = False
                state.attempt_pinned_boundary_slot = None
            else:
                state.attempt_open = True
                state.attempt_pinned_boundary_slot = (
                    int(requested_from_slot) if pre_attempt_safe is None
                    else int(min(pre_attempt_safe, requested_from_slot)))
            self._requested_from_slot = (
                None if requested_from_slot is None else int(requested_from_slot))
            self._requested_generation = int(state.recovery_generation)
            if state.recovery_required:
                state.recovery_status = RECOVERY_IN_PROGRESS
            # Durable BEFORE the stream is constructed. A write failure
            # propagates: no attempt may run on an unrecorded boundary.
            self._persist_locked()
            return StreamAttemptRecord(
                subscription_identity_digest=str(
                    subscription_identity_digest or self._identity_digest),
                recovery_generation=int(state.recovery_generation),
                attempt_generation=int(state.attempt_generation),
                requested_from_slot=state.attempt_requested_from_slot,
                pinned_boundary_slot=state.attempt_pinned_boundary_slot,
                expected_overlap_slot=state.attempt_requested_from_slot,
                recovery_status=str(state.recovery_status),
                recorded_at_utc=state.updated_at_utc,
            )

    def mark_disconnect(self, *, reason: str = REASON_PROVIDER_DISCONNECT,
                        at_utc: Optional[str] = None,
                        attempted_from_slot: Optional[int] = None) -> None:
        """Open (or continue) a recovery episode without moving its boundary.

        The first disconnect of an episode pins ``recovery_from_slot`` to the
        position that was authoritative at that moment.  Every subsequent
        disconnect while the episode remains unresolved leaves that boundary
        exactly where it is.

        The pre-repair implementation overwrote the boundary with the current
        ``last_durable_slot`` on every disconnect.  Against a provider that
        ignored ``from_slot``, the high-water mark had by then moved beyond the
        unobserved range, so the second disconnect erased the last record of
        the position that still owed coverage -- and the next reconnect
        requested the moved position, which the provider trivially honoured,
        self-certifying a gap that had never been closed.
        """

        with self._lock:
            state = self.state
            state.last_disconnect_at_utc = at_utc or self._now_iso()
            if not state.has_position():
                # Nothing was ever committed: there is no proven covered
                # ground to have lost, so no gap is claimed.
                return
            safe_reason = (
                reason if reason in RECOVERY_REASONS else REASON_PROVIDER_DISCONNECT)
            # The boundary comes from the ATTEMPT, never from the high-water
            # mark the attempt may just have moved. An unresolved episode keeps
            # its ORIGINAL boundary and generation.
            self._open_episode_locked(
                boundary=self._attempt_boundary_locked(attempted_from_slot),
                reason=safe_reason)
            state.recovery_status = RECOVERY_REQUIRED
            state.recovery_target_slot = None
            state.gap_detected_total += 1
            try:
                self._persist_locked()
            except StreamCursorWriteError:
                # The in-memory gap remains authoritative for this process;
                # the persistence failure is surfaced through the counters.
                pass

    def mark_recovery_started(self, *, from_slot: int,
                              recovery_generation: Optional[int] = None) -> None:
        """Record the position actually requested; never move the boundary.

        ``recovery_from_slot`` is the episode's pinned safe boundary and is
        deliberately NOT reassigned here: what was requested is tracked
        separately so an overlap proof can be checked against the boundary it
        claims to prove rather than against itself.
        """

        with self._lock:
            self.state.recovery_status = RECOVERY_IN_PROGRESS
            self._requested_from_slot = int(from_slot)
            self._requested_generation = (
                int(recovery_generation) if recovery_generation is not None
                else int(self.state.recovery_generation))

    def mark_recovery_failed(self, *, reason: str,
                             attempted_from_slot: Optional[int] = None) -> None:
        """Record that THIS attempt failed to prove its coverage.

        Pins the episode boundary from the attempt record.  Before this repair
        the flag was raised with no boundary at all, leaving a valid,
        digest-authenticated document in which ``recovery_required`` was true
        and ``recovery_from_slot`` was null -- a state whose safe resume
        silently degraded to the already-advanced high-water mark.
        """

        with self._lock:
            safe_reason = (
                reason if reason in RECOVERY_REASONS else REASON_GAP_UNRECOVERABLE)
            self._open_episode_locked(
                boundary=self._attempt_boundary_locked(attempted_from_slot),
                reason=safe_reason)
            self.state.recovery_required = True
            self.state.recovery_status = RECOVERY_FAILED
            self.state.recovery_reason = safe_reason
            try:
                self._persist_locked()
            except StreamCursorWriteError:
                pass

    def mark_replay_retention_exceeded(
        self, *, first_available: Optional[int] = None,
        reason: str = REASON_REPLAY_POSITION_TOO_OLD,
    ) -> None:
        """Enter the TERMINAL retention-exceeded state.

        The required boundary is older than anything the provider can still
        replay.  There is no safe automatic remedy: starting at the live head
        would silently abandon the range, and deleting the cursor would destroy
        the evidence of what was abandoned.  The position is therefore retained
        untouched, ``resume_from_slot`` refuses to answer, reconnecting stops,
        delivery stays blocked, and an operator must intervene.
        """

        with self._lock:
            state = self.state
            state.recovery_required = True
            state.recovery_terminal = True
            state.recovery_status = RECOVERY_FAILED
            state.recovery_reason = (
                reason if reason in RECOVERY_REASONS
                else REASON_REPLAY_POSITION_TOO_OLD)
            if first_available is not None and not isinstance(first_available, bool) \
                    and isinstance(first_available, int) and first_available >= 0:
                state.replay_first_available_slot = int(first_available)
            try:
                self._persist_locked()
            except StreamCursorWriteError:
                pass

    def _overlap_binding_is_valid(
        self, *, requested_from_slot: object, proven_boundary_slot: object,
        recovery_generation: object,
        attempt_generation: object = None,
        subscription_identity_digest: object = None,
        require_open_episode: bool = True,
    ) -> bool:
        """Does this proof actually prove THIS attempt's requested boundary?

        Overlap is evidence only when the provider redelivered the EXACT event
        the resume position names.  ``from_slot`` is inclusive and the cursor
        was committed at a slot where a matching transaction was seen, so that
        transaction must come back; observing it at exactly that slot is the
        whole proof.

        Equality is the only admissible test.  A *higher* slot proves the
        provider started beyond the boundary and says nothing about the range in
        between -- the original self-certifying loop.  A *lower* slot proves the
        provider never reached the requested position at all: a lagging or
        rolled-back stream, or an update whose ``slot`` never left the proto3
        default of 0.  The pre-repair guard rejected only the first of those,
        so a slot-0 update closed the episode and opened the send gate with zero
        replay coverage.
        """

        state = self.state
        if self._quarantined or self._identity_mismatch or state.recovery_terminal:
            return False
        for value in (requested_from_slot, proven_boundary_slot,
                      recovery_generation):
            if not isinstance(value, int) or isinstance(value, bool):
                return False
        if requested_from_slot < 0 or proven_boundary_slot < 0:
            return False
        if recovery_generation != int(state.recovery_generation):
            return False            # a later disconnect superseded this attempt
        if attempt_generation is not None:
            if not isinstance(attempt_generation, int) or isinstance(
                    attempt_generation, bool):
                return False
            if attempt_generation != int(state.attempt_generation):
                return False        # proof belongs to a superseded attempt
        if subscription_identity_digest is not None:
            if str(subscription_identity_digest) != str(
                    state.subscription_identity_digest):
                return False        # the subscription no longer means the same
        if require_open_episode:
            if state.recovery_from_slot is None:
                return False
            if requested_from_slot != int(state.recovery_from_slot):
                return False        # it did not request the boundary it owes
        if state.attempt_open and state.attempt_requested_from_slot is not None:
            if requested_from_slot != int(state.attempt_requested_from_slot):
                return False        # not the position this attempt asked for
        # EXACT equality. Not <=, not >=: neither direction is proof.
        if proven_boundary_slot != requested_from_slot:
            return False
        return True

    def mark_overlap_proven(
        self, *, requested_from_slot: int, proven_boundary_slot: int,
        recovery_generation: int,
        attempt_generation: Optional[int] = None,
        subscription_identity_digest: Optional[str] = None,
    ) -> bool:
        """Record positive provider replay proof and retire the pinned boundary.

        Called by the source at the moment a boundary-slot event is redelivered
        AND its identity processing is complete.  Returns ``True`` only when
        the proof genuinely binds to the position this attempt requested.

        An attempt that resumes a position while NO episode is open still has a
        boundary to retire: the pre-attempt pin.  Proving it closes the pin
        without inventing an episode, so an honest provider does not leave a
        healthy stream permanently anchored to its start position.
        """

        with self._lock:
            state = self.state
            episode_open = bool(state.recovery_required)
            if not episode_open and not state.attempt_open:
                return False
            if not self._overlap_binding_is_valid(
                    requested_from_slot=requested_from_slot,
                    proven_boundary_slot=proven_boundary_slot,
                    recovery_generation=recovery_generation,
                    attempt_generation=attempt_generation,
                    subscription_identity_digest=subscription_identity_digest,
                    require_open_episode=episode_open):
                return False
            state.last_proven_replay_boundary_slot = int(requested_from_slot)
            state.overlap_proven_generation = int(recovery_generation)
            # The attempt proved the position it requested: the pre-attempt pin
            # has done its job and must not keep holding the resume position.
            state.attempt_open = False
            state.attempt_pinned_boundary_slot = None
            if episode_open:
                state.recovery_required = False
                state.recovery_status = RECOVERY_CLOSED
                state.recovery_reason = REASON_NONE
                state.recovery_from_slot = None
                state.recovery_target_slot = None
                state.gap_closed_total += 1
            try:
                self._persist_locked()
            except StreamCursorWriteError:
                pass
            return True

    def mark_gap_closed(
        self, *, requested_from_slot: int, proven_boundary_slot: int,
        recovery_generation: int,
        attempt_generation: Optional[int] = None,
        subscription_identity_digest: Optional[str] = None,
    ) -> bool:
        """Confirm an episode closed, refusing anything that is not proof.

        Idempotent with respect to :meth:`mark_overlap_proven`: if the source
        already recorded a binding proof for this same generation and boundary,
        this confirms it rather than double-counting.
        """

        with self._lock:
            state = self.state
            if not state.recovery_required and not state.attempt_open:
                # Already closed -- but only report success if THIS episode is
                # what closed it.
                return bool(
                    state.overlap_proven_generation == recovery_generation
                    and state.last_proven_replay_boundary_slot
                    == requested_from_slot)
        return self.mark_overlap_proven(
            requested_from_slot=requested_from_slot,
            proven_boundary_slot=proven_boundary_slot,
            recovery_generation=recovery_generation,
            attempt_generation=attempt_generation,
            subscription_identity_digest=subscription_identity_digest)

    def resolve_terminal_retention_with_backfill_proof(
        self, *, safe_from_slot: int, proven_target_slot: int,
        overlap_identity: str, recovery_generation: int,
        subscription_identity_digest: str,
    ) -> bool:
        """The ONE exit from the replay-retention terminal state.

        Only production backfill evidence may transition a
        ``REPLAY_RETENTION_EXCEEDED`` cursor back to health: complete
        block-range coverage of ``[safe_from_slot .. proven_target_slot]``
        re-proven through an independent authoritative source, closed by an
        exact cross-source overlap identity at the target slot.  The caller
        (the recovery coordinator) is responsible for having actually proven
        that coverage; this method verifies that the CLAIM binds to this
        cursor's episode exactly, and refuses anything that does not:

          * a quarantined or identity-mismatched cursor is never resolvable --
            corruption is not a retention problem;
          * only the retention terminal reason qualifies; an auth failure or
            an unknown refusal that was terminal stays terminal;
          * the proof must name the episode's own generation, subscription
            identity and immutable safe boundary -- a stale or foreign proof
            is refused;
          * the overlap identity must be a real event identity whose slot IS
            the proven target.

        On success the terminal flag, the episode and the pinned boundary are
        retired ATOMICALLY in one persisted generation.  A persistence failure
        changes nothing and returns ``False`` -- the cursor remains terminal,
        which is the conservative direction.  No operator assertion, manual
        flag or partial proof can reach this transition.
        """

        for value in (safe_from_slot, proven_target_slot, recovery_generation):
            if isinstance(value, bool) or not isinstance(value, int):
                return False
        if safe_from_slot < 0 or proven_target_slot < safe_from_slot:
            return False
        if not isinstance(overlap_identity, str) or not overlap_identity:
            return False
        if slot_of_identity(overlap_identity) != int(proven_target_slot):
            return False
        with self._lock:
            state = self.state
            if self._quarantined or self._identity_mismatch:
                return False
            if not state.recovery_terminal:
                return False
            if state.recovery_reason != REASON_REPLAY_POSITION_TOO_OLD:
                return False
            if str(subscription_identity_digest) != self._identity_digest:
                return False
            if str(subscription_identity_digest) != str(
                    state.subscription_identity_digest):
                return False
            if int(recovery_generation) != int(state.recovery_generation):
                return False
            boundary = state.safe_resume_slot()
            if boundary is None or int(safe_from_slot) != int(boundary):
                return False
            proposed = state.clone()
            proposed.recovery_terminal = False
            proposed.recovery_required = False
            proposed.recovery_status = RECOVERY_CLOSED
            proposed.recovery_reason = REASON_NONE
            proposed.recovery_from_slot = None
            proposed.recovery_target_slot = None
            proposed.attempt_open = False
            proposed.attempt_pinned_boundary_slot = None
            proposed.last_proven_replay_boundary_slot = int(safe_from_slot)
            proposed.overlap_proven_generation = int(recovery_generation)
            proposed.backfilled_event_count += 1
            proposed.gap_closed_total += 1
            try:
                self._persist_state_locked(proposed)
            except StreamCursorWriteError:
                # Nothing was published: the terminal evidence stands.
                return False
            return True

    def is_terminal(self) -> bool:
        """Is recovery in a state no automatic action can leave?"""

        with self._lock:
            return bool(
                self.state.recovery_terminal or self._quarantined
                or self._identity_mismatch)

    def slot_is_inside_recovery_responsibility(self, slot: object) -> bool:
        """Is ``slot`` still owed coverage by the current recovery episode?"""

        with self._lock:
            state = self.state
            if not state.recovery_required or state.recovery_from_slot is None:
                return False
            if isinstance(slot, bool) or not isinstance(slot, int):
                return False
            return int(state.recovery_from_slot) <= slot <= int(
                state.last_durable_slot)

    # -- resume ----------------------------------------------------------

    def safe_resume_slot(self) -> Optional[int]:
        """The authoritative safe resume boundary, ignoring load/identity gates.

        Distinct from :meth:`resume_from_slot`, which additionally refuses to
        answer at all when the cursor may not be trusted.
        """

        with self._lock:
            return self.state.safe_resume_slot()

    def resume_from_slot(self) -> Optional[int]:
        """The inclusive slot the replacement stream must replay from.

        Inclusive by design: the boundary slot may hold further qualifying
        events that were never processed, and re-receiving the events that
        *were* processed is exactly what proves the provider honoured the
        resume position.  The duplicates are suppressed by exact identity.

        While a recovery episode is unresolved this returns the episode's
        pinned boundary rather than the high-water mark, so a provider that
        ignores ``from_slot`` is re-asked for the same unproven position
        instead of being handed a position it has already trivially satisfied.
        """

        with self._lock:
            if self._quarantined or self._identity_mismatch:
                return None
            if self.state.recovery_terminal:
                # A dead position must not drive another subscription attempt.
                return None
            return self.state.safe_resume_slot()

    def resume_decision(self) -> ResumeDecision:
        """What the owner must do next, with no ambiguous ``None``.

        :meth:`resume_from_slot` answers ``None`` both for "no prior position,
        start at the live head" and for "this position is dead, start nothing".
        The owner consulted it before it consulted terminal state, so a
        terminal replay-retention cursor silently became a full live-head
        subscription on restart -- skipping the retention pre-check entirely and
        abandoning the range the terminal state existed to protect.

        Callers must branch on :attr:`ResumeDecision.builds_source`, never on
        ``from_slot is None``.
        """

        with self._lock:
            state = self.state
            preserved = state.safe_resume_slot()
            if self._quarantined:
                return ResumeDecision(
                    action=RESUME_ACTION_REFUSE_TERMINAL, from_slot=None,
                    reason=REASON_CURSOR_QUARANTINED,
                    preserved_safe_slot=preserved)
            if self._identity_mismatch:
                return ResumeDecision(
                    action=RESUME_ACTION_REFUSE_TERMINAL, from_slot=None,
                    reason=REASON_SUBSCRIPTION_IDENTITY_MISMATCH,
                    preserved_safe_slot=preserved)
            if state.recovery_terminal:
                return ResumeDecision(
                    action=RESUME_ACTION_REFUSE_TERMINAL, from_slot=None,
                    reason=(state.recovery_reason if state.recovery_reason
                            in RECOVERY_REASONS
                            else REASON_REPLAY_POSITION_TOO_OLD),
                    preserved_safe_slot=preserved)
            if preserved is None:
                # Genuinely new: no durable position was ever written, so there
                # is no coverage to lose by starting at the live head.
                return ResumeDecision(
                    action=RESUME_ACTION_BOOTSTRAP_LIVE_HEAD, from_slot=None,
                    reason=REASON_NONE, preserved_safe_slot=None)
            return ResumeDecision(
                action=RESUME_ACTION_SUBSCRIBE_FROM_SLOT,
                from_slot=int(preserved), reason=REASON_NONE,
                preserved_safe_slot=int(preserved))

    # -- observability ---------------------------------------------------

    def _latency_percentile_locked(self, fraction: float) -> Optional[float]:
        samples = self._checkpoint_latencies_ms
        if not samples:
            return None
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, max(0, int(fraction * len(ordered))))
        return round(ordered[idx], 3)

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe cursor observability. No paths, secrets or raw errors."""

        with self._lock:
            state = self.state
            processed_slot = (
                int(state.last_durable_slot) if state.has_position() else None)
            flushed_slot = (
                int(self._last_flushed_slot)
                if self._last_flushed_slot is not None
                and self._last_flushed_slot >= 0 else None)
            durability_lag = (
                max(0, processed_slot - flushed_slot)
                if processed_slot is not None and flushed_slot is not None
                else 0)
            oldest_pending_age_ms = (
                round(max(0.0, (self._monotonic()
                                - self._oldest_pending_monotonic)) * 1000.0, 3)
                if self._oldest_pending_monotonic is not None else 0.0)
            return {
                "grpc_cursor_schema_version": STREAM_CURSOR_SCHEMA_CURRENT,
                "grpc_cursor_generation": int(self._generation),
                "grpc_cursor_last_durable_slot": (
                    None if not state.has_position() else int(state.last_durable_slot)),
                # The high-water mark above versus the authoritative boundary
                # below: the whole point of the repair is that these differ
                # while a recovery episode is unresolved.
                "grpc_cursor_safe_resume_slot": state.safe_resume_slot(),
                "grpc_cursor_last_proven_replay_boundary_slot": (
                    state.last_proven_replay_boundary_slot),
                "grpc_cursor_requested_from_slot": self._requested_from_slot,
                # The pre-attempt pin: what the CURRENT attempt is obliged to
                # preserve regardless of where the high-water mark has moved.
                "grpc_attempt_generation": int(state.attempt_generation),
                "grpc_attempt_open": bool(state.attempt_open),
                "grpc_attempt_requested_from_slot": (
                    state.attempt_requested_from_slot),
                "grpc_attempt_pinned_boundary_slot": (
                    state.attempt_pinned_boundary_slot),
                "grpc_recovery_generation": int(state.recovery_generation),
                "grpc_overlap_proven_generation": state.overlap_proven_generation,
                "grpc_recovery_terminal": bool(state.recovery_terminal),
                "grpc_replay_first_available_slot": (
                    state.replay_first_available_slot),
                "grpc_cursor_boundary_event_count": len(
                    state.processed_event_ids_in_boundary_slot),
                "grpc_cursor_recent_identity_count": len(
                    state.recent_event_identities),
                "grpc_cursor_checkpoint_status": self.load_result.checkpoint_status,
                "grpc_cursor_recovered_from_backup": bool(
                    self.load_result.checkpoint_recovered_from_backup),
                "grpc_cursor_quarantined": bool(self._quarantined),
                "grpc_cursor_quarantine_reason": self._quarantine_reason,
                "grpc_cursor_write_locked": bool(self._write_locked),
                "grpc_subscription_identity_match": not self._identity_mismatch,
                "grpc_stream_generation": int(state.stream_generation),
                "grpc_gap_unresolved": bool(state.recovery_required),
                "grpc_gap_from_slot": state.recovery_from_slot,
                "grpc_gap_target_slot": state.recovery_target_slot,
                "grpc_recovery_status": state.recovery_status,
                "grpc_recovery_reason": state.recovery_reason,
                "grpc_replay_event_total": int(state.replayed_event_count),
                "grpc_replay_duplicate_total": int(state.duplicate_replay_count),
                "grpc_backfill_event_total": int(state.backfilled_event_count),
                "grpc_gap_detected_total": int(state.gap_detected_total),
                "grpc_gap_closed_total": int(state.gap_closed_total),
                "grpc_cursor_write_failed_total": int(self.cursor_write_failed_total),
                "grpc_cursor_readback_failed_total": int(
                    self.cursor_readback_failed_total),
                # -- durable-cursor throughput decomposition -----------------
                # ``grpc_cursor_last_durable_slot`` above is the IN-MEMORY
                # processed high-water mark; the on-disk durable position is
                # the flushed slot below.  They are equal unless a batched flush
                # is momentarily pending.
                "grpc_cursor_flushed_durable_slot": flushed_slot,
                "grpc_cursor_durability_lag_slots": int(durability_lag),
                "grpc_cursor_pending_commit_events": int(
                    self._pending_commit_events),
                "grpc_cursor_oldest_pending_age_ms": oldest_pending_age_ms,
                "grpc_cursor_persist_batch_max_events": int(self._batch_max_events),
                "grpc_cursor_persist_batch_max_seconds": float(
                    self._batch_max_seconds),
                "grpc_cursor_checkpoint_attempted_total": int(
                    self.cursor_checkpoint_attempted_total),
                "grpc_cursor_checkpoint_succeeded_total": int(
                    self.cursor_checkpoint_succeeded_total),
                "grpc_cursor_checkpoint_failed_total": int(
                    self.cursor_checkpoint_failed_total),
                "grpc_cursor_checkpoint_deferred_total": int(
                    self.cursor_checkpoint_deferred_total),
                "grpc_cursor_checkpoint_forced_flush_total": int(
                    self.cursor_checkpoint_forced_flush_total),
                "grpc_cursor_checkpoint_write_retried_total": int(
                    self.cursor_checkpoint_write_retried_total),
                "grpc_cursor_checkpoint_transient_failure_total": int(
                    self.cursor_checkpoint_transient_failure_total),
                "grpc_cursor_checkpoint_last_write_attempts": int(
                    self.cursor_checkpoint_last_write_attempts),
                "grpc_cursor_checkpoint_bytes": int(self._last_checkpoint_bytes),
                "grpc_cursor_checkpoint_latency_ms_p50": (
                    self._latency_percentile_locked(0.50)),
                "grpc_cursor_checkpoint_latency_ms_p95": (
                    self._latency_percentile_locked(0.95)),
                "grpc_cursor_checkpoint_latency_ms_p99": (
                    self._latency_percentile_locked(0.99)),
                "grpc_cursor_durability_status": self.cursor_durability_status,
                "grpc_cursor_last_success_utc": self.cursor_last_success_utc,
                "grpc_cursor_last_failure_category": (
                    self.cursor_last_failure_category),
            }


# ---------------------------------------------------------------------------
# replay retention
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplayRetentionVerdict:
    """Whether the provider can still replay from the required boundary."""

    retention_exceeded: bool
    coverage_proven: bool
    reason: str
    first_available_slot: Optional[int] = None
    safe_resume_slot: Optional[int] = None


def evaluate_replay_retention(
    *, safe_resume_slot: Optional[int], first_available_slot: Optional[int],
) -> ReplayRetentionVerdict:
    """Compare the required boundary against the provider's retention floor.

    ``first_available`` comes from the generated ``Geyser.SubscribeReplayInfo``
    unary RPC.  Querying it *before* a replay is attempted turns a reactive,
    reconnect-storming failure into an explicit terminal state.

    An unavailable or malformed answer is never treated as coverage: it yields
    ``coverage_proven=False`` with an explicit reason, so the caller stays
    degraded rather than optimistically declaring health.
    """

    if safe_resume_slot is None:
        # Nothing to replay from: a genuinely new subscription.
        return ReplayRetentionVerdict(
            retention_exceeded=False, coverage_proven=True, reason=REASON_NONE)
    if (first_available_slot is None or isinstance(first_available_slot, bool)
            or not isinstance(first_available_slot, int)
            or first_available_slot < 0):
        return ReplayRetentionVerdict(
            retention_exceeded=False, coverage_proven=False,
            reason=REASON_REPLAY_UNAVAILABLE,
            safe_resume_slot=int(safe_resume_slot))
    if int(first_available_slot) > int(safe_resume_slot):
        return ReplayRetentionVerdict(
            retention_exceeded=True, coverage_proven=False,
            reason=REASON_REPLAY_POSITION_TOO_OLD,
            first_available_slot=int(first_available_slot),
            safe_resume_slot=int(safe_resume_slot))
    return ReplayRetentionVerdict(
        retention_exceeded=False, coverage_proven=True, reason=REASON_NONE,
        first_available_slot=int(first_available_slot),
        safe_resume_slot=int(safe_resume_slot))


# ---------------------------------------------------------------------------
# source health -> outbound authorization
# ---------------------------------------------------------------------------

#: The ONLY source state that may authorize an outbound alert. Everything else
#: -- starting, loading, connecting, replaying, catching up, gap unresolved,
#: quarantined, retention exceeded, recovery failed, retrying, identity
#: mismatch -- blocks the send path.
SEND_AUTHORIZING_STATES = (STATE_LIVE_HEALTHY,)

#: Blocking a send is NOT blocking the producer. Replay ingestion, migration
#: admission, deterministic rejection, candidate restoration, watchlist
#: rebuilding, baseline restoration and replay dedupe must all keep running
#: while degraded, or the recovery this module exists to perform cannot happen.
_STATE_TO_BLOCK_REASON = {
    STATE_GAP_UNRESOLVED: REASON_GAP_UNRECOVERABLE,
    STATE_GAP_DETECTED: REASON_GAP_UNRECOVERABLE,
    STATE_CURSOR_QUARANTINED: REASON_CURSOR_QUARANTINED,
    STATE_REPLAY_RETENTION_EXCEEDED: REASON_REPLAY_POSITION_TOO_OLD,
    STATE_REPLAY_UNSUPPORTED: REASON_REPLAY_UNAVAILABLE,
    STATE_BACKFILL_UNAVAILABLE: REASON_BACKFILL_REQUIRED,
    STATE_BACKFILL_PARTIAL: REASON_BACKFILL_PARTIAL,
    STATE_BACKFILL_FAILED: REASON_GAP_UNRECOVERABLE,
    STATE_SUBSCRIPTION_IDENTITY_MISMATCH: REASON_SUBSCRIPTION_IDENTITY_MISMATCH,
    STATE_CURSOR_WRITE_FAILED: REASON_CURSOR_WRITE_FAILED,
    STATE_CURSOR_READBACK_FAILED: REASON_CURSOR_READBACK_FAILED,
}


def source_health_authorizes_send(snapshot: Mapping[str, Any]) -> Tuple[bool, str]:
    """May the outbound alert path proceed given this source health snapshot?

    Fails CLOSED: an absent, malformed or unrecognised state blocks.  Returns
    ``(authorized, closed_set_reason)``; the reason is ``REASON_NONE`` only
    when authorized.
    """

    if not isinstance(snapshot, Mapping):
        return False, REASON_SOURCE_NOT_LIVE_HEALTHY
    if snapshot.get("grpc_cursor_quarantined") or snapshot.get(
            "grpc_recovery_terminal"):
        reason = snapshot.get("grpc_recovery_reason")
        return False, (reason if reason in RECOVERY_REASONS
                       else REASON_CURSOR_QUARANTINED)
    if snapshot.get("gap_unresolved") or snapshot.get("grpc_gap_unresolved"):
        return False, REASON_GAP_UNRECOVERABLE
    state = snapshot.get("stream_state")
    if state not in SEND_AUTHORIZING_STATES:
        return False, _STATE_TO_BLOCK_REASON.get(
            state, REASON_SOURCE_NOT_LIVE_HEALTHY)
    if not bool(snapshot.get("live_healthy", False)):
        return False, REASON_SOURCE_NOT_LIVE_HEALTHY
    return True, REASON_NONE


def source_health_permits_ingestion(_snapshot: Mapping[str, Any]) -> bool:
    """Degraded discovery keeps ingesting; only the SEND path is gated.

    Present as an explicit, named counterpart to
    :func:`source_health_authorizes_send` so the asymmetry is a stated contract
    rather than an accident of where a check happens to sit.
    """

    return True


def build_cursor_store(
    *,
    state_dir: object,
    subscription_identity_digest: str,
    commitment: str = "CONFIRMED",
    basename: str = CURSOR_PRIMARY_BASENAME,
    **kwargs: Any,
) -> GrpcStreamCursorStore:
    """Construct the cursor store for one producer state directory."""

    return GrpcStreamCursorStore(
        primary_path=Path(state_dir) / basename,
        subscription_identity_digest=subscription_identity_digest,
        commitment=commitment,
        **kwargs,
    )


__all__ = (
    "CHECKPOINT_KIND_STREAM_CURSOR",
    "STREAM_CURSOR_SCHEMA_V1",
    "STREAM_CURSOR_SCHEMA_V2",
    "STREAM_CURSOR_SCHEMA_CURRENT",
    "SUPPORTED_CURSOR_SCHEMA_VERSIONS",
    "CURSOR_RECORD_KIND",
    "CURSOR_PRIMARY_BASENAME",
    "STREAM_SOURCE_YELLOWSTONE",
    "NO_SLOT",
    "STREAM_STATES",
    "DEGRADED_STATES",
    "STATE_STARTING",
    "STATE_CURSOR_LOADING",
    "STATE_REPLAY_REQUIRED",
    "STATE_REPLAYING",
    "STATE_CATCHING_UP",
    "STATE_LIVE_HEALTHY",
    "STATE_DISCONNECTED",
    "STATE_GAP_DETECTED",
    "STATE_RECONNECTING",
    "STATE_STOPPED",
    "STATE_CURSOR_QUARANTINED",
    "STATE_REPLAY_UNSUPPORTED",
    "STATE_REPLAY_RETENTION_EXCEEDED",
    "STATE_BACKFILL_UNAVAILABLE",
    "STATE_BACKFILL_PARTIAL",
    "STATE_BACKFILL_FAILED",
    "STATE_GAP_UNRESOLVED",
    "STATE_SUBSCRIPTION_IDENTITY_MISMATCH",
    "STATE_CURSOR_WRITE_FAILED",
    "STATE_CURSOR_READBACK_FAILED",
    "RECOVERY_STATUSES",
    "RECOVERY_NOT_REQUIRED",
    "RECOVERY_REQUIRED",
    "RECOVERY_IN_PROGRESS",
    "RECOVERY_CLOSED",
    "RECOVERY_FAILED",
    "RECOVERY_REASONS",
    "REASON_NONE",
    "REASON_BOOTSTRAP_NEW_STATE_DIR",
    "REASON_PROVIDER_DISCONNECT",
    "REASON_PROCESS_RESTART",
    "REASON_REPLAY_POSITION_TOO_OLD",
    "REASON_REPLAY_UNAVAILABLE",
    "REASON_BACKFILL_REQUIRED",
    "REASON_BACKFILL_PARTIAL",
    "REASON_GAP_UNRECOVERABLE",
    "REASON_SUBSCRIPTION_IDENTITY_MISMATCH",
    "REASON_CURSOR_QUARANTINED",
    "REASON_CURSOR_WRITE_FAILED",
    "REASON_CURSOR_READBACK_FAILED",
    "REASON_SOURCE_NOT_LIVE_HEALTHY",
    "SEND_AUTHORIZING_STATES",
    "ReplayRetentionVerdict",
    "evaluate_replay_retention",
    "source_health_authorizes_send",
    "source_health_permits_ingestion",
    "DISPLAY_CONNECTED_LIVE_HEALTHY",
    "DISPLAY_CONNECTED_REPLAYING",
    "DISPLAY_CONNECTED_BACKFILLING",
    "DISPLAY_DISCONNECTED_RETRYING",
    "DISPLAY_GAP_UNRESOLVED",
    "DISPLAY_CURSOR_QUARANTINED",
    "DISPLAY_REPLAY_UNAVAILABLE",
    "DISPLAY_RECOVERY_FAILED",
    "DISPLAY_STOPPED",
    "BOOTSTRAP_LIVE_HEAD",
    "BOOTSTRAP_REFUSE",
    "BOOTSTRAP_POLICIES",
    "StreamCursorWriteError",
    "ResumeDecision",
    "StreamAttemptRecord",
    "RESUME_ACTION_SUBSCRIBE_FROM_SLOT",
    "RESUME_ACTION_BOOTSTRAP_LIVE_HEAD",
    "RESUME_ACTION_REFUSE_TERMINAL",
    "RESUME_ACTIONS",
    "StreamCursorState",
    "GrpcStreamCursorStore",
    "build_cursor_store",
    "build_stream_event_identity",
    "slot_of_identity",
    "compute_subscription_identity_digest",
    "classify_cursor_checkpoint_file",
    "validate_cursor_record",
    "validate_cursor_cross_field_state",
    "cursor_record_identity",
    "cursor_cross_generation_check",
)
