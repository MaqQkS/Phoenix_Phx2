"""Stage 30.11.17 operator-curated compose session models.

Stage 30.11.17 ships the passive, pure, stdlib-only MODEL layer for the
committed OFFLINE operator-curated compose session -- the smallest bounded
session wrapper over the already-proven single-candidate no-send path
(``compose_no_send_dispatch_deduped``). It ships only the carriers + closed-set
vocabularies + pure safe-shape predicates the session composes:

  * the operator-curated CANDIDATE (a thin carrier of ONE already-revalidated
    Stage 30.11.13 request -- read duck-typed as ``request`` -- plus an optional
    safe-shape curated label; it embeds NO committed request type so the models
    stay a pure leaf);
  * the bounded session CONFIG (the per-run candidate + composition caps + a
    caller-injected timestamp);
  * the per-entry session EVENT (a redaction-safe record carrying ONLY closed-set
    tokens + safe-echo ids + safe flags -- never a body, a url, an exception
    string, or any secret);
  * the rolled-up session RESULT (the ordered events + the non-negative counts +
    the closed-set stop reason + the redaction status + a caller-injected
    timestamp);
  * the closed-set per-entry outcome / stop-reason vocabularies + the redaction
    status tokens;
  * the pure safe-shape predicates + the cap validator + the default config
    builder the session composes.

This module is the MODEL layer ONLY. It implements NO session (that is
``stage30_11_17_operator_curated_compose_session``), runs NO compose, drives NO
ledger, calls NO transport, sends NO message, reads NO process environment, opens
NO network connection, opens NO database, writes NO file, reserves NO dispatch,
signs nothing, trades nothing, and edits NO composer / dedupe / ledger /
ATH-anchoring / market-freshness / Stage 30.12 renderer / tier-band file. Stage
30.11.17 is fake / offline / no-send only: the real private compact dispatch /
Discord send remains a SEPARATE, explicitly operator-authorized step this slice
does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.16 / 30.11.15 /
    30.11.3 model modules). The single-candidate request is carried duck-typed as
    ``Any`` -- the committed Stage 30.11.13 request type is NEVER imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, url, host, or request-metadata
    reference; no wallet / signing / trading surface; no public / subscriber
    routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_17_MINOR_VERSION: str = "30.11.17"


# The Stage 30.11.17 compose-session schema version. Names the candidate / config
# / event / result shapes; distinct from every earlier Stage 30.11 schema
# version. Mirrored BY VALUE by the Stage 30.11 manifest section; this module
# imports no Stage 30.11 manifest.
STAGE30_11_17_SESSION_SCHEMA_VERSION: str = (
    "stage30_11_17_v0_operator_curated_compose_session"
)


# The safe-shape source-stage provenance token (names the slice; never a secret
# / host / transport destination).
STAGE30_11_17_SOURCE_STAGE: str = "30.11.17"


# ---------------------------------------------------------------------------
# Bounded caps
# ---------------------------------------------------------------------------
#
# The session pulls AT MOST ``max_candidates`` curated entries (a single BOUNDED
# for-loop; no ``while`` loop, no daemon) and composes AT MOST ``max_compositions``
# of them. The hard candidate cap mirrors the committed Stage 30.11.5
# ``max_candidates <= 10`` ceiling so the curated session can never evaluate more
# than the bounded runner is allowed to. ``max_compositions`` must be within
# ``1..max_candidates``; a config outside the caps fails closed BEFORE the loop.


STAGE30_11_17_MAX_CANDIDATES_HARD_CAP: int = 10
STAGE30_11_17_DEFAULT_MAX_CANDIDATES: int = 10


# ---------------------------------------------------------------------------
# Closed-set: per-entry outcome
# ---------------------------------------------------------------------------
#
# Exactly one outcome per composed curated entry. ``DISPATCHED`` is the only
# outcome on which the committed composer recorded a would-send through the
# injected FAKE transport (a RECORDED would-send, NEVER a real send);
# ``DEDUPE_BLOCKED`` is a clean cross-/within-run duplicate suppression;
# ``REJECTED`` is any other fail-closed composer rejection; ``ERROR`` is a
# fail-closed dedupe-unavailable / missing compose result / unexpected exception.
# Mirrored BY VALUE by the Stage 30.11 manifest.


ENTRY_OUTCOME_DISPATCHED: str = "DISPATCHED"
ENTRY_OUTCOME_REJECTED: str = "REJECTED"
ENTRY_OUTCOME_DEDUPE_BLOCKED: str = "DEDUPE_BLOCKED"
ENTRY_OUTCOME_ERROR: str = "ERROR"


STAGE30_11_17_ENTRY_OUTCOMES: Tuple[str, ...] = (
    ENTRY_OUTCOME_DISPATCHED,
    ENTRY_OUTCOME_REJECTED,
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_ERROR,
)


def is_entry_outcome(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set per-entry outcome.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_17_ENTRY_OUTCOMES


# ---------------------------------------------------------------------------
# Closed-set: session stop reason
# ---------------------------------------------------------------------------
#
# Exactly one stop reason per session. ``COMPLETED_ALL_CANDIDATES`` means the
# curated list was exhausted within both caps; ``STOPPED_BY_CANDIDATE_CAP`` /
# ``STOPPED_BY_COMPOSITION_CAP`` name the bounding cap. Mirrored BY VALUE by the
# Stage 30.11 manifest.


STOP_REASON_COMPLETED: str = "COMPLETED_ALL_CANDIDATES"
STOP_REASON_CANDIDATE_CAP: str = "STOPPED_BY_CANDIDATE_CAP"
STOP_REASON_COMPOSITION_CAP: str = "STOPPED_BY_COMPOSITION_CAP"


STAGE30_11_17_STOP_REASONS: Tuple[str, ...] = (
    STOP_REASON_COMPLETED,
    STOP_REASON_CANDIDATE_CAP,
    STOP_REASON_COMPOSITION_CAP,
)


def is_stop_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set session stop reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_17_STOP_REASONS


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The session self-scans its own event string fields and stamps the result's
# ``redaction_status``: ``REDACTED`` when every field is safe (the normal path --
# the session builds only closed-set tokens + safe-echo ids), else
# ``REDACTION_VIOLATION``. A consumed-result id / curated label that is not a
# safe-echo token is replaced by ``REDACTED_UNSAFE_ID`` rather than echoed raw, so
# a forged id / label can never smuggle injected text into the result.


STAGE30_11_17_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_17_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_17_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_17_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STAGE30_11_17_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.16 / 30.11.15 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint, an underscore
    candidate id, and an underscore curated label all pass; any newline / control
    char / whitespace / path / url / quote character (or an over-long value)
    fails. It gates the consumed-result ids + the curated label the session echoes
    into its redaction-safe events -- an unsafe value is replaced by
    ``STAGE30_11_17_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the Stage
    30.11.16 ``is_safe_echo_id`` BY VALUE. Pure / total; never raises.
    """
    if not isinstance(value, str):
        return False
    if value == "" or len(value) > 128:
        return False
    for ch in value:
        if "A" <= ch <= "Z":
            continue
        if "a" <= ch <= "z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_" or ch == "-":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Immutable model: one operator-curated candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_17OperatorCuratedCandidate:
    """Immutable carrier of ONE operator-curated compose-session entry.

    A thin wrapper around exactly one already-revalidated committed Stage 30.11.13
    revalidation request (carried duck-typed as ``request`` so this model imports
    no committed request type and stays a pure leaf) plus an optional safe-shape
    curated label. The operator OWNS the revalidation: the request is the same
    object ``compose_no_send_dispatch`` / ``compose_no_send_dispatch_deduped``
    already validate, so a malformed / non-request ``request`` simply yields a
    fail-closed ``REJECTED`` outcome at the composer -- never a crash here.

      * ``request``       -- ONE revalidation request (duck-typed). A non-request
                             value composes to a clean ``REJECTED`` entry.
      * ``curated_label`` -- an optional safe-shape provenance label (echoed onto
                             the entry only when it is a safe-echo token; an unsafe
                             label is redacted, never echoed raw). ``None`` / blank
                             is allowed.
    """

    request: Any
    curated_label: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable model: bounded session config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_17SessionConfig:
    """Immutable bounded compose-session config.

    Carries only the per-run caps + a caller-injected timestamp; no secret, no
    transport reference. A valid config requires ``max_candidates`` within
    ``1..STAGE30_11_17_MAX_CANDIDATES_HARD_CAP`` and ``max_compositions`` within
    ``1..max_candidates`` (see ``is_within_session_caps``).

      * ``max_candidates``   -- the bounded list-pull cap (1..10).
      * ``max_compositions`` -- the bounded compose-call cap (1..max_candidates).
      * ``created_at_utc``   -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                wall-clock read.
    """

    max_candidates: int
    max_compositions: int
    created_at_utc: str


def is_within_session_caps(config: object) -> bool:
    """Return ``True`` iff ``config`` is a structurally-valid session config whose
    caps are within the HARD session caps (``1 <= max_candidates <= 10`` and
    ``1 <= max_compositions <= max_candidates``) with a non-blank timestamp.

    Pure / TOTAL; never raises. A non-config, a ``bool`` cap, a non-int cap, a
    cap outside its range, or a blank timestamp fails closed to ``False`` -- so a
    curated session can never be parameterized to pull / compose more than the
    committed ceilings allow.
    """
    if not isinstance(config, Stage30_11_17SessionConfig):
        return False
    max_candidates = config.max_candidates
    max_compositions = config.max_compositions
    if isinstance(max_candidates, bool) or isinstance(max_compositions, bool):
        return False
    if not isinstance(max_candidates, int) or not isinstance(
        max_compositions, int
    ):
        return False
    if not is_nonblank_str(config.created_at_utc):
        return False
    if not (1 <= max_candidates <= STAGE30_11_17_MAX_CANDIDATES_HARD_CAP):
        return False
    if not (1 <= max_compositions <= max_candidates):
        return False
    return True


def default_session_config(*, created_at_utc: str) -> Stage30_11_17SessionConfig:
    """Build the default bounded session config: the 10-candidate cap + a
    10-composition cap (compose every pulled candidate), the HARD ceilings the
    controlled curated session requires. Pure; no I/O, no clock.
    """
    return Stage30_11_17SessionConfig(
        max_candidates=STAGE30_11_17_DEFAULT_MAX_CANDIDATES,
        max_compositions=STAGE30_11_17_DEFAULT_MAX_CANDIDATES,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Immutable model: per-entry session event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_17SessionEvent:
    """Immutable per-entry Stage 30.11.17 compose-session event.

    The session emits exactly one of these per composed curated entry. It echoes
    the safe-shape candidate identity + curated label, pins the closed-set
    ``outcome`` plus the mirrored composer decision / reason + dedupe verdict /
    reason (all closed-set safe tokens), records the recorded would-send count
    (``transport_attempts`` -- a FAKE-client tally, 0 or 1) and whether a body was
    built, and stamps a caller-injected timestamp. It carries ONLY safe scalars +
    closed-set tokens: NO body, NO url, NO exception text, NO secret.

      * ``index``               -- the zero-based position in the composed order.
      * ``token_mint`` / ``candidate_id`` -- echoed safe-shape ids (``""`` when
                                  unreadable; ``REDACTED_UNSAFE_ID`` when present
                                  but not a safe-echo token).
      * ``curated_label``       -- the echoed safe curated label (``""`` when
                                  absent; ``REDACTED_UNSAFE_ID`` when unsafe).
      * ``outcome``             -- one of ``STAGE30_11_17_ENTRY_OUTCOMES``.
      * ``compose_decision``    -- the mirrored composer decision token (``""``
                                  when no compose result).
      * ``compose_reason``      -- the mirrored composer reason token (``""``).
      * ``dedupe_verdict``      -- the mirrored dedupe verdict token (``""`` when
                                  the dedupe guard never ran).
      * ``dedupe_reason``       -- the mirrored dedupe reason token (``""``).
      * ``transport_attempts``  -- the recorded would-send count (FAKE client; 0
                                  or 1) -- NEVER a real send.
      * ``body_present``        -- ``True`` iff a (no-send) operator body was
                                  built; the body text itself is NEVER carried.
      * ``created_at_utc``      -- caller-injected ISO-8601 UTC timestamp.
    """

    index: int
    candidate_id: str
    token_mint: str
    curated_label: str
    outcome: str
    compose_decision: str
    compose_reason: str
    dedupe_verdict: str
    dedupe_reason: str
    transport_attempts: int
    body_present: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: rolled-up session result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_17SessionResult:
    """Immutable rolled-up Stage 30.11.17 compose-session result.

    A passive summary of one bounded curated session. It carries the ordered
    per-entry events, the non-negative outcome counts, the recorded would-send
    tally, the closed-set stop reason, the redaction status, and a caller-injected
    timestamp. Carries ONLY safe scalars + the embedded events; no secret, no
    body, no url, no transport destination.

      * ``events``                -- the ordered per-entry events.
      * ``candidates_seen``       -- curated entries pulled + processed (<= the
                                     candidate cap).
      * ``compositions_attempted``-- ``compose_no_send_dispatch_deduped`` calls
                                     made (<= the composition cap).
      * ``dispatched`` / ``rejected`` / ``dedupe_blocked`` / ``errors`` -- the
                                     per-outcome counts (they sum to
                                     ``compositions_attempted``).
      * ``would_send_recorded``   -- the total recorded would-send count across
                                     entries (FAKE client; equals ``dispatched``).
      * ``stop_reason``           -- one of ``STAGE30_11_17_STOP_REASONS``.
      * ``redaction_status``      -- one of ``STAGE30_11_17_REDACTION_STATUSES``.
      * ``created_at_utc``        -- caller-injected ISO-8601 UTC timestamp.
    """

    events: Tuple[Stage30_11_17SessionEvent, ...]
    candidates_seen: int
    compositions_attempted: int
    dispatched: int
    rejected: int
    dedupe_blocked: int
    errors: int
    would_send_recorded: int
    stop_reason: str
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def operator_curated_candidate_field_names() -> Tuple[str, ...]:
    """Return the operator-curated candidate field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_17OperatorCuratedCandidate))


def session_config_field_names() -> Tuple[str, ...]:
    """Return the session config field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_17SessionConfig))


def session_event_field_names() -> Tuple[str, ...]:
    """Return the session event field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_17SessionEvent))


def session_result_field_names() -> Tuple[str, ...]:
    """Return the session result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_17SessionResult))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_17_MINOR_VERSION",
    "STAGE30_11_17_SESSION_SCHEMA_VERSION",
    "STAGE30_11_17_SOURCE_STAGE",
    # Bounded caps.
    "STAGE30_11_17_MAX_CANDIDATES_HARD_CAP",
    "STAGE30_11_17_DEFAULT_MAX_CANDIDATES",
    # Per-entry outcomes.
    "ENTRY_OUTCOME_DISPATCHED",
    "ENTRY_OUTCOME_REJECTED",
    "ENTRY_OUTCOME_DEDUPE_BLOCKED",
    "ENTRY_OUTCOME_ERROR",
    "STAGE30_11_17_ENTRY_OUTCOMES",
    "is_entry_outcome",
    # Stop reasons.
    "STOP_REASON_COMPLETED",
    "STOP_REASON_CANDIDATE_CAP",
    "STOP_REASON_COMPOSITION_CAP",
    "STAGE30_11_17_STOP_REASONS",
    "is_stop_reason",
    # Redaction.
    "STAGE30_11_17_REDACTION_STATUS_REDACTED",
    "STAGE30_11_17_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_17_REDACTED_UNSAFE_ID",
    "STAGE30_11_17_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_17OperatorCuratedCandidate",
    "Stage30_11_17SessionConfig",
    "is_within_session_caps",
    "default_session_config",
    "Stage30_11_17SessionEvent",
    "Stage30_11_17SessionResult",
    # Field-name helpers.
    "operator_curated_candidate_field_names",
    "session_config_field_names",
    "session_event_field_names",
    "session_result_field_names",
)
