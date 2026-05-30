"""Stage 30.8.1 compact session artifact models.

Stage 30.8.1 ships the pure, passive, stdlib-only model layer for the
Stage 30.8 compact session artifact family. These are the safe,
in-memory records a FUTURE writer (Stage 30.8.2+) would persist; Stage
30.8.1 implements NO writer, NO database, NO filesystem access, NO
compression. Every record here is a frozen dataclass that carries only
safe scalars: opaque ids, closed-set tokens, already-rendered display
strings, ISO-8601 UTC timestamps, version strings, and integer / float
counters.

The records are LENIENT carriers: they do NOT validate their fields at
construction. Validation is the job of the separate Stage 30.8.1
validator layer (``stage30_8_artifact_validators``), which classifies a
record into a ``Stage30_8ValidationResult`` (``VALID`` / ``INVALID``)
and NEVER raises. This mirrors the Stage 30.6.1 split between lenient
carriers and a deterministic policy brain.

Closed-set vocabularies pinned here:

  * artifact kinds -- ``compact_session_summary`` /
    ``compact_ping_artifact`` / ``compact_dispatch_attempt_artifact`` /
    ``compact_error_artifact`` / ``compact_storage_budget_snapshot``.
  * the artifact schema version -- ``stage30_8_v0_compact_artifact``.
  * the artifact stage id -- ``stage30_8`` (the value the artifact
    identity ``stage_id`` field must carry; distinct from the Stage
    30.8 family dotted id ``30.8``).
  * the validation status closed set -- ``VALID`` / ``INVALID``.
  * the compact storage-budget status closed set -- ``OK`` /
    ``SOFT_ALARM`` / ``HARD_STOP`` / ``INVALID_INPUT`` (the short Stage
    30.8 budget-snapshot form, not the long Stage 30.6.1 token form).

Immutable records:

  * ``Stage30_8CompactArtifactIdentity``              -- the stable
    identity axes every persisted artifact carries.
  * ``Stage30_8CompactContentSnapshot``               -- the
    already-rendered, redaction-safe compact display fields.
  * ``Stage30_8CompactPingArtifact``                  -- one terminal
    compact private ping record (identity + content snapshot).
  * ``Stage30_8CompactSessionSummaryArtifact``        -- one rolled-up
    per-session summary (identity + safe counters + optional budget
    snapshot).
  * ``Stage30_8CompactDispatchAttemptArtifact``       -- one dispatch /
    send attempt record (sanitized transport status + attempt index).
  * ``Stage30_8CompactErrorArtifact``                 -- one closed-set
    error reason-code record (a reason code only).
  * ``Stage30_8CompactStorageBudgetSnapshotArtifact`` -- one per-run
    Stage 30.6-style storage-budget snapshot.
  * ``Stage30_8ValidationResult``                     -- the validator
    output shape (status / reason / blocked_field / safe_to_persist).

These records are PASSIVE:

  * no filesystem, no ``open`` / ``pathlib`` / ``os`` / ``shutil`` /
    ``sqlite3`` access,
  * no process environment read,
  * no network / provider / Discord surface,
  * no runtime / orchestrator / renderer import,
  * no writer methods (no ``to_file`` / ``from_file`` / ``save`` /
    ``flush`` / append-style method on any record),
  * no compression dependency.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.6.1 models module).
  * No network / env / filesystem / disk I/O at import time. No
    top-level Call (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls,
    not body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version
# ---------------------------------------------------------------------------


STAGE30_8_1_MINOR_VERSION: str = "30.8.1"


# ---------------------------------------------------------------------------
# Artifact schema identity (closed values)
# ---------------------------------------------------------------------------
#
# ``STAGE30_8_ARTIFACT_STAGE_ID`` is the value the artifact identity
# ``stage_id`` field must carry. It is intentionally the underscore form
# ``stage30_8`` (NOT the Stage 30.8 family dotted id ``30.8`` that the
# manifest pins as ``STAGE30_8_STAGE_ID``): the artifact stage id is part
# of the persisted artifact schema, the dotted id is the family label.


STAGE30_8_ARTIFACT_STAGE_ID: str = "stage30_8"
STAGE30_8_ARTIFACT_SCHEMA_VERSION: str = "stage30_8_v0_compact_artifact"


# ---------------------------------------------------------------------------
# Artifact kinds (closed set of five)
# ---------------------------------------------------------------------------


ARTIFACT_KIND_COMPACT_SESSION_SUMMARY: str = "compact_session_summary"
ARTIFACT_KIND_COMPACT_PING_ARTIFACT: str = "compact_ping_artifact"
ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT: str = (
    "compact_dispatch_attempt_artifact"
)
ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT: str = "compact_error_artifact"
ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT: str = (
    "compact_storage_budget_snapshot"
)


STAGE30_8_ARTIFACT_KINDS: Tuple[str, ...] = (
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
)


def is_artifact_kind(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set artifact kind."""
    return isinstance(value, str) and value in STAGE30_8_ARTIFACT_KINDS


# ---------------------------------------------------------------------------
# Validation status (closed set)
# ---------------------------------------------------------------------------


VALIDATION_STATUS_VALID: str = "VALID"
VALIDATION_STATUS_INVALID: str = "INVALID"


STAGE30_8_VALIDATION_STATUS_VALUES: Tuple[str, ...] = (
    VALIDATION_STATUS_VALID,
    VALIDATION_STATUS_INVALID,
)


def is_validation_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set validation status."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_VALIDATION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Compact storage-budget status (closed set; short Stage 30.8 form)
# ---------------------------------------------------------------------------
#
# The ``compact_storage_budget_snapshot`` artifact carries the short
# Stage 30.8 budget status token. This is the operator-facing short form
# (``OK`` / ``SOFT_ALARM`` / ``HARD_STOP`` / ``INVALID_INPUT``); it maps
# onto the long Stage 30.6.1 ``STORAGE_BUDGET_*`` tokens but Stage 30.8.1
# imports no Stage 30.6 module and re-defines the short closed set here.


STORAGE_BUDGET_STATUS_OK: str = "OK"
STORAGE_BUDGET_STATUS_SOFT_ALARM: str = "SOFT_ALARM"
STORAGE_BUDGET_STATUS_HARD_STOP: str = "HARD_STOP"
STORAGE_BUDGET_STATUS_INVALID_INPUT: str = "INVALID_INPUT"


STAGE30_8_STORAGE_BUDGET_STATUS_VALUES: Tuple[str, ...] = (
    STORAGE_BUDGET_STATUS_OK,
    STORAGE_BUDGET_STATUS_SOFT_ALARM,
    STORAGE_BUDGET_STATUS_HARD_STOP,
    STORAGE_BUDGET_STATUS_INVALID_INPUT,
)


def is_storage_budget_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set budget status."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_STORAGE_BUDGET_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Redaction substitution tokens (closed set)
# ---------------------------------------------------------------------------
#
# A persisted string is safe when it passes the validator scan or is one
# of these closed-set safe placeholders. Mirrors the Stage 30.8.0 spec
# lock redaction-token set.


STAGE30_8_REDACTION_SUBSTITUTION_TOKENS: Tuple[str, ...] = (
    "SAFE",
    "REDACTED",
    "Unknown",
)


# ---------------------------------------------------------------------------
# Immutable record: compact artifact identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactArtifactIdentity:
    """Immutable Stage 30.8 compact artifact identity (lenient carrier).

    The stable identity axes every persisted compact artifact carries.
    Each is a safe-shape opaque id, a closed-set token, an ISO-8601 UTC
    timestamp, or a version string. NONE is a secret, a raw payload, a
    host, or a transport destination.

    A LENIENT carrier: it does NOT validate its fields at construction.
    The Stage 30.8.1 validator
    (``validate_compact_artifact_identity``) enforces the required /
    closed-set rules and fails closed to an ``INVALID``
    ``Stage30_8ValidationResult`` rather than raising.

    Fields:

      * ``stage_id``                    -- artifact stage id; must carry
                                           ``stage30_8`` to validate.
      * ``run_id``                      -- runtime-context run id.
      * ``session_id``                  -- private-soak session id.
      * ``ping_id``                     -- compact ping id.
      * ``candidate_id``                -- candidate id (when available).
      * ``token_mint``                  -- safe-shape mint (when
                                           available).
      * ``provider_event_id``           -- sanitized opaque event id
                                           (when available).
      * ``normalized_event_id``         -- sanitized normalized event id
                                           (when available).
      * ``observed_at_utc``             -- observation timestamp
                                           (ISO-8601 UTC, when present).
      * ``artifact_created_at_utc``     -- artifact creation timestamp
                                           (ISO-8601 UTC, caller clock).
      * ``artifact_schema_version``     -- Stage 30.8 artifact schema
                                           version; defaults to the
                                           locked value.
      * ``artifact_kind``               -- one of the closed-set kinds.
      * ``dedupe_key``                  -- the dedupe key /
                                           dedupe_fingerprint.
      * ``compact_ping_schema_version`` -- compact-ping schema version
                                           echo (when available).
    """

    stage_id: str = STAGE30_8_ARTIFACT_STAGE_ID
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    ping_id: Optional[str] = None
    candidate_id: Optional[str] = None
    token_mint: Optional[str] = None
    provider_event_id: Optional[str] = None
    normalized_event_id: Optional[str] = None
    observed_at_utc: Optional[str] = None
    artifact_created_at_utc: Optional[str] = None
    artifact_schema_version: str = STAGE30_8_ARTIFACT_SCHEMA_VERSION
    artifact_kind: Optional[str] = None
    dedupe_key: Optional[str] = None
    compact_ping_schema_version: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: compact content snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactContentSnapshot:
    """Immutable Stage 30.8 compact content snapshot (lenient carrier).

    The already-rendered, redaction-safe compact display fields a
    compact artifact may carry. These mirror the Stage 30.2 compact
    display strings plus closed-set status / code tokens. They are the
    sanitized projection of a rendered compact ping, never raw provider
    data.

    A LENIENT carrier (no construction-time validation). The Stage
    30.8.1 validator (``validate_compact_content_snapshot``) enforces:
    display fields are strings (when present); ``warning_codes`` /
    ``reason_codes`` are tuples / lists of strings only; no nested raw
    dict / list payload; no forbidden field name / value pattern.

    Fields:

      * ``compact_body_text``         -- the rendered compact body
                                         string (required non-empty for
                                         a ping artifact).
      * ``mc_display``                -- the ``MC`` display string.
      * ``lp_display``                -- the ``LP`` display string.
      * ``net_display``               -- the ``Net`` display string.
      * ``ath_display``               -- the ``ATH`` display string.
      * ``migration_display``         -- the ``Mig`` display string.
      * ``decision_status``           -- closed-set decision status
                                         token (when present).
      * ``eligibility_status``        -- closed-set eligibility status
                                         token (when present).
      * ``warning_codes``             -- tuple of closed-set warning
                                         code strings.
      * ``reason_codes``              -- tuple of closed-set reason code
                                         strings.
      * ``terminal_outcome_code``     -- terminal outcome code (when
                                         present).
      * ``sanitized_transport_status``-- sanitized transport status
                                         code (when present).
    """

    compact_body_text: Optional[str] = None
    mc_display: Optional[str] = None
    lp_display: Optional[str] = None
    net_display: Optional[str] = None
    ath_display: Optional[str] = None
    migration_display: Optional[str] = None
    decision_status: Optional[str] = None
    eligibility_status: Optional[str] = None
    warning_codes: Tuple[str, ...] = ()
    reason_codes: Tuple[str, ...] = ()
    terminal_outcome_code: Optional[str] = None
    sanitized_transport_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: compact ping artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactPingArtifact:
    """Immutable Stage 30.8 terminal compact ping artifact.

    One durable record per terminal compact private ping: the artifact
    identity plus the sanitized compact content snapshot. A LENIENT
    carrier; ``validate_compact_ping_artifact`` enforces the identity /
    content rules (including a non-empty ``compact_body_text``).
    """

    identity: Optional[Stage30_8CompactArtifactIdentity] = None
    content: Optional[Stage30_8CompactContentSnapshot] = None


# ---------------------------------------------------------------------------
# Immutable record: compact dispatch attempt artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactDispatchAttemptArtifact:
    """Immutable Stage 30.8 dispatch attempt artifact.

    One record per dispatch / send attempt (including provider retry
    attempts): a sanitized transport status code plus an optional
    attempt index. The attempt's dedupe key lives on ``identity``.
    Multiple attempt artifacts may exist for a single terminal ping.
    A LENIENT carrier; ``validate_compact_dispatch_attempt_artifact``
    enforces the rules.
    """

    identity: Optional[Stage30_8CompactArtifactIdentity] = None
    sanitized_transport_status: Optional[str] = None
    attempt_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Immutable record: compact error artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactErrorArtifact:
    """Immutable Stage 30.8 error artifact.

    One record per closed-set error reason token encountered during
    capture: a reason code ONLY -- never a raw exception message, a raw
    response payload, or a raw provider payload. A LENIENT carrier;
    ``validate_compact_error_artifact`` enforces the rules.
    """

    identity: Optional[Stage30_8CompactArtifactIdentity] = None
    error_reason_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: compact storage budget snapshot artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactStorageBudgetSnapshotArtifact:
    """Immutable Stage 30.8 storage-budget snapshot artifact.

    One record of the Stage 30.6-style per-run storage-budget state:
    the short closed-set ``budget_status`` plus safe integer counters /
    float percentages. Counters / byte counts / percentages only; no raw
    payload, no credential, no transport destination. A LENIENT carrier;
    ``validate_compact_storage_budget_snapshot_artifact`` enforces the
    rules.

    Fields mirror the Stage 30.6 per-run storage summary axes.
    """

    identity: Optional[Stage30_8CompactArtifactIdentity] = None
    budget_status: Optional[str] = None
    raw_bytes_written: Optional[int] = None
    durable_rows_written: Optional[int] = None
    archived_compressed_bytes: Optional[int] = None
    dropped_count: Optional[int] = None
    pruned_count: Optional[int] = None
    sealed_count: Optional[int] = None
    dedupe_suppressed_count: Optional[int] = None
    disk_usage_percent_before: Optional[float] = None
    disk_usage_percent_after: Optional[float] = None


# ---------------------------------------------------------------------------
# Immutable record: compact session summary artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactSessionSummaryArtifact:
    """Immutable Stage 30.8 session summary artifact.

    One rolled-up summary per private soak session: safe counters
    (pings emitted, dispatch attempts, dedupe suppressed, errors), the
    session / run identity, and an optional embedded Stage 30.6-style
    storage-budget snapshot. Carries no raw provider payloads. A LENIENT
    carrier; ``validate_compact_session_summary_artifact`` enforces the
    rules.
    """

    identity: Optional[Stage30_8CompactArtifactIdentity] = None
    pings_emitted: Optional[int] = None
    dispatch_attempts: Optional[int] = None
    dedupe_suppressed: Optional[int] = None
    errors: Optional[int] = None
    storage_budget: Optional[
        Stage30_8CompactStorageBudgetSnapshotArtifact
    ] = None


# ---------------------------------------------------------------------------
# Immutable record: validation result (validator output shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8ValidationResult:
    """Immutable Stage 30.8.1 validation result.

    The output shape of every Stage 30.8.1 validator. A frozen record:

      * ``status``          -- ``VALID`` / ``INVALID``.
      * ``reason``          -- a closed-set reason token (``OK`` for a
                               valid result; an ``INVALID_*`` style
                               token otherwise).
      * ``blocked_field``   -- the field name that failed validation, or
                               ``None`` for a valid result.
      * ``safe_to_persist`` -- ``True`` only when ``status`` is
                               ``VALID`` (a future writer may persist
                               the artifact); ``False`` otherwise. This
                               is a verdict flag, NOT a writer: Stage
                               30.8.1 persists nothing.
    """

    status: str
    reason: str
    blocked_field: Optional[str]
    safe_to_persist: bool


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def identity_field_names() -> Tuple[str, ...]:
    """Return the identity record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8CompactArtifactIdentity))


def content_snapshot_field_names() -> Tuple[str, ...]:
    """Return the content snapshot record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8CompactContentSnapshot))


def ping_artifact_field_names() -> Tuple[str, ...]:
    """Return the ping artifact record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8CompactPingArtifact))


def session_summary_artifact_field_names() -> Tuple[str, ...]:
    """Return the session summary record field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_8CompactSessionSummaryArtifact)
    )


def dispatch_attempt_artifact_field_names() -> Tuple[str, ...]:
    """Return the dispatch attempt record field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_8CompactDispatchAttemptArtifact)
    )


def error_artifact_field_names() -> Tuple[str, ...]:
    """Return the error artifact record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8CompactErrorArtifact))


def storage_budget_snapshot_artifact_field_names() -> Tuple[str, ...]:
    """Return the storage-budget snapshot record field names tuple."""
    return tuple(
        f.name
        for f in fields(Stage30_8CompactStorageBudgetSnapshotArtifact)
    )


def validation_result_field_names() -> Tuple[str, ...]:
    """Return the validation result record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8ValidationResult))


__all__ = (
    # Minor version.
    "STAGE30_8_1_MINOR_VERSION",
    # Artifact schema identity.
    "STAGE30_8_ARTIFACT_STAGE_ID",
    "STAGE30_8_ARTIFACT_SCHEMA_VERSION",
    # Artifact kinds.
    "ARTIFACT_KIND_COMPACT_SESSION_SUMMARY",
    "ARTIFACT_KIND_COMPACT_PING_ARTIFACT",
    "ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT",
    "ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT",
    "ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT",
    "STAGE30_8_ARTIFACT_KINDS",
    "is_artifact_kind",
    # Validation status.
    "VALIDATION_STATUS_VALID",
    "VALIDATION_STATUS_INVALID",
    "STAGE30_8_VALIDATION_STATUS_VALUES",
    "is_validation_status",
    # Storage budget status.
    "STORAGE_BUDGET_STATUS_OK",
    "STORAGE_BUDGET_STATUS_SOFT_ALARM",
    "STORAGE_BUDGET_STATUS_HARD_STOP",
    "STORAGE_BUDGET_STATUS_INVALID_INPUT",
    "STAGE30_8_STORAGE_BUDGET_STATUS_VALUES",
    "is_storage_budget_status",
    # Redaction tokens.
    "STAGE30_8_REDACTION_SUBSTITUTION_TOKENS",
    # Records.
    "Stage30_8CompactArtifactIdentity",
    "Stage30_8CompactContentSnapshot",
    "Stage30_8CompactPingArtifact",
    "Stage30_8CompactDispatchAttemptArtifact",
    "Stage30_8CompactErrorArtifact",
    "Stage30_8CompactStorageBudgetSnapshotArtifact",
    "Stage30_8CompactSessionSummaryArtifact",
    "Stage30_8ValidationResult",
    # Field-name helpers.
    "identity_field_names",
    "content_snapshot_field_names",
    "ping_artifact_field_names",
    "session_summary_artifact_field_names",
    "dispatch_attempt_artifact_field_names",
    "error_artifact_field_names",
    "storage_budget_snapshot_artifact_field_names",
    "validation_result_field_names",
)
