"""Stage 30.8.3 offline compact session index / dedupe models.

Stage 30.8.3 is the FIRST Stage 30.8 dedupe / session index slice. It
ships the pure, passive, stdlib-only model layer for an OFFLINE session
index / dedupe projection over the Stage 30.8.2 manifest-backed compact
session bundles. Stage 30.8.3 is NOT a database, NOT SQLite, NOT zstd /
compression, NOT live runtime, NOT live Discord, NOT real bot storage --
it is offline temp-dir index logic only.

This module is the model layer: passive frozen records + closed-set
status tokens + the deterministic dedupe-identity resolution policy. It
implements NO reader (that is ``stage30_8_session_bundle_reader``) and NO
builder (that is ``stage30_8_session_index_builder``); it reads no
filesystem, opens no database, reaches no network, and reads no
environment.

The index answers, for a set of Stage 30.8.2 session bundles:

  1. Which session bundles exist?            -> ``sessions`` /
     ``session_count`` on the build result.
  2. Which compact ping artifacts belong to  -> ``pings`` on each
     each session?                              ``Stage30_8SessionIndexRecord``.
  3. Which ping artifacts are duplicate       -> ``duplicate_pings`` on
     identities?                                 the build result.
  4. Which unique ping artifacts are          -> ``retained_pings`` on the
     retained for later collection / replay?     build result.
  5. Which duplicates are suppressed?         -> ``duplicate_pings`` (each
                                                 carries its
                                                 ``duplicate_of_*``
                                                 provenance).

Dedupe identity (the locked contract).
``STAGE_30_8_0_COMPACT_SESSION_STORAGE_SPEC_LOCK.md`` Section 9 pins the
dedupe identity for a ``compact_ping_artifact`` as its ``dedupe_key`` (the
Stage 30.6 dedupe key / ``dedupe_fingerprint``: mint + alert / tier /
state class + policy-version / session-scope axis), with exactly one
terminal ping artifact per dedupe identity. The Stage 30.8.1 ping
validator already REQUIRES a non-empty ``session_id`` / ``ping_id`` /
``dedupe_key`` on every valid (and therefore every Stage 30.8.2-written)
ping artifact, so a ping read back from a real bundle always carries a
``dedupe_key``. ``dedupe_key`` is therefore the ONLY retained dedupe
identity: ``resolve_ping_dedupe_identity`` resolves to the ``dedupe_key``
identity when (and only when) a non-empty ``dedupe_key`` string is
present, else to the ``none`` identity -- an identity-less ping that is
NEVER retained (the builder classifies it ``INVALID_SUPPRESSED``). There
is deliberately NO ``ping_id`` fallback: a missing-``dedupe_key`` ping is
never retained by ``ping_id``. ``ping_id`` is used only as provenance /
display / a deterministic ordering tiebreak. Absolute paths and
timestamps are NEVER used as dedupe identity.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.8.1 models module).
  * No filesystem / env / network / database / compression access. No
    ``open`` / ``pathlib`` / ``os`` / ``json`` / ``sqlite3``. No top-level
    Call (no implicit I/O at import time; the ``@dataclass(frozen=True)``
    decorators are decorator-list Calls, not body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + index schema identity
# ---------------------------------------------------------------------------


STAGE30_8_3_MINOR_VERSION: str = "30.8.3"


# The offline session-index schema version. Distinct from the per-artifact
# schema version (``stage30_8_v0_compact_artifact``) and the bundle
# envelope schema version (``stage30_8_v0_compact_session_bundle``): this
# names the Stage 30.8.3 in-memory index projection.
STAGE30_8_3_INDEX_SCHEMA_VERSION: str = "stage30_8_v0_compact_session_index"


# ---------------------------------------------------------------------------
# Index build status (closed set)
# ---------------------------------------------------------------------------


INDEX_BUILD_STATUS_BUILT: str = "BUILT"
INDEX_BUILD_STATUS_EMPTY: str = "EMPTY"
INDEX_BUILD_STATUS_INVALID_INPUT: str = "INVALID_INPUT"
INDEX_BUILD_STATUS_READ_FAILED: str = "READ_FAILED"
INDEX_BUILD_STATUS_INDEX_FAILED: str = "INDEX_FAILED"


STAGE30_8_3_INDEX_BUILD_STATUS_VALUES: Tuple[str, ...] = (
    INDEX_BUILD_STATUS_BUILT,
    INDEX_BUILD_STATUS_EMPTY,
    INDEX_BUILD_STATUS_INVALID_INPUT,
    INDEX_BUILD_STATUS_READ_FAILED,
    INDEX_BUILD_STATUS_INDEX_FAILED,
)


def is_index_build_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set build status."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_3_INDEX_BUILD_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Index build reason (closed set; index-builder-owned)
# ---------------------------------------------------------------------------


INDEX_BUILD_REASON_OK: str = "OK"
INDEX_BUILD_REASON_EMPTY: str = "EMPTY"
INDEX_BUILD_REASON_NO_SOURCE: str = "NO_SOURCE"
INDEX_BUILD_REASON_AMBIGUOUS_SOURCE: str = "AMBIGUOUS_SOURCE"
INDEX_BUILD_REASON_INVALID_SESSION_DIRS: str = "INVALID_SESSION_DIRS"
INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT: str = "INVALID_OUTPUT_ROOT"
INDEX_BUILD_REASON_BUNDLE_READ_FAILED: str = "BUNDLE_READ_FAILED"
INDEX_BUILD_REASON_INTERNAL_ERROR: str = "INTERNAL_ERROR"


STAGE30_8_3_INDEX_BUILD_REASONS: Tuple[str, ...] = (
    INDEX_BUILD_REASON_OK,
    INDEX_BUILD_REASON_EMPTY,
    INDEX_BUILD_REASON_NO_SOURCE,
    INDEX_BUILD_REASON_AMBIGUOUS_SOURCE,
    INDEX_BUILD_REASON_INVALID_SESSION_DIRS,
    INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT,
    INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
    INDEX_BUILD_REASON_INTERNAL_ERROR,
)


# ---------------------------------------------------------------------------
# Ping dedupe status (closed set)
# ---------------------------------------------------------------------------


PING_DEDUPE_STATUS_RETAINED: str = "RETAINED"
PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED: str = "DUPLICATE_SUPPRESSED"
PING_DEDUPE_STATUS_INVALID_SUPPRESSED: str = "INVALID_SUPPRESSED"


STAGE30_8_3_PING_DEDUPE_STATUS_VALUES: Tuple[str, ...] = (
    PING_DEDUPE_STATUS_RETAINED,
    PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
)


def is_ping_dedupe_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set ping dedupe status."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_3_PING_DEDUPE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Ping suppress reason (closed set)
# ---------------------------------------------------------------------------


PING_SUPPRESS_REASON_NONE: str = "NONE"
PING_SUPPRESS_REASON_DUPLICATE_IDENTITY: str = "DUPLICATE_IDENTITY"
PING_SUPPRESS_REASON_MISSING_IDENTITY: str = "MISSING_IDENTITY"
PING_SUPPRESS_REASON_SESSION_ID_MISMATCH: str = "SESSION_ID_MISMATCH"


STAGE30_8_3_PING_SUPPRESS_REASONS: Tuple[str, ...] = (
    PING_SUPPRESS_REASON_NONE,
    PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
    PING_SUPPRESS_REASON_MISSING_IDENTITY,
    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
)


# ---------------------------------------------------------------------------
# Dedupe identity kind (closed set)
# ---------------------------------------------------------------------------
#
# Which axis a ping's dedupe identity resolved from. ``dedupe_key`` is the
# ONLY retained dedupe identity (spec Section 9); ``none`` marks an
# identity-less ping (never retained). There is deliberately NO ``ping_id``
# kind -- ``ping_id`` is provenance / a tiebreak only, never a dedupe
# identity.


DEDUPE_IDENTITY_KIND_DEDUPE_KEY: str = "dedupe_key"
DEDUPE_IDENTITY_KIND_NONE: str = "none"


STAGE30_8_3_DEDUPE_IDENTITY_KINDS: Tuple[str, ...] = (
    DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
    DEDUPE_IDENTITY_KIND_NONE,
)


# ---------------------------------------------------------------------------
# Immutable record: dedupe identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8DedupeIdentity:
    """Immutable, hashable dedupe identity for a compact ping artifact.

    ``kind`` is one of the closed-set ``DEDUPE_IDENTITY_KIND_*`` tokens and
    ``value`` is the resolved identity string (``None`` only for the
    ``none`` kind). Two ping artifacts are duplicates iff their dedupe
    identities are equal. The ``kind`` namespace prevents a cross-axis
    collision (a ``dedupe_key`` of ``"K"`` never collides with a
    ``ping_id`` of ``"K"``). Frozen, so it is hashable and usable as a
    deterministic dict key.
    """

    kind: str
    value: Optional[str]


def resolve_ping_dedupe_identity(
    dedupe_key: object,
) -> Stage30_8DedupeIdentity:
    """Resolve a compact ping artifact's dedupe identity from its
    ``dedupe_key`` ALONE (the spec-locked dedupe identity, Section 9).

    Returns the ``dedupe_key`` identity when ``dedupe_key`` is a non-empty
    string, else the ``none`` identity. There is NO ``ping_id`` fallback:
    a ping that lacks a usable ``dedupe_key`` resolves to ``none`` and is
    never retained (the builder classifies it ``INVALID_SUPPRESSED``).
    ``ping_id`` is provenance / a tiebreak only. Never uses an absolute
    path or a timestamp as identity. Pure / total; never raises.
    """
    if isinstance(dedupe_key, str) and dedupe_key != "":
        return Stage30_8DedupeIdentity(
            DEDUPE_IDENTITY_KIND_DEDUPE_KEY, dedupe_key
        )
    return Stage30_8DedupeIdentity(DEDUPE_IDENTITY_KIND_NONE, None)


def has_dedupe_identity(identity: object) -> bool:
    """Return ``True`` iff ``identity`` is a usable (non-``none``) dedupe
    identity. Pure / total; never raises.
    """
    return (
        isinstance(identity, Stage30_8DedupeIdentity)
        and identity.kind != DEDUPE_IDENTITY_KIND_NONE
        and isinstance(identity.value, str)
        and identity.value != ""
    )


# ---------------------------------------------------------------------------
# Immutable record: indexed ping artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8IndexedPingArtifact:
    """Immutable index record for ONE compact ping artifact.

    Carries the dedupe verdict plus enough provenance to debug:

      * ``session_id``                    -- the bundle (manifest) session
                                             id this ping belongs to.
      * ``session_dir``                   -- the bundle directory path
                                             (provenance).
      * ``artifact_filename``             -- the member filename (ordering +
                                             provenance).
      * ``member_kind``                   -- the artifact kind read from the
                                             JSON identity.
      * ``ping_id``                       -- the ping id from the artifact
                                             identity (when present).
      * ``dedupe_key``                    -- the dedupe key from the
                                             artifact identity (when
                                             present).
      * ``identity_kind``                 -- which axis the dedupe identity
                                             resolved from (closed set).
      * ``identity_value``                -- the resolved dedupe identity
                                             value (``None`` only for the
                                             ``none`` kind).
      * ``dedupe_status``                 -- ``RETAINED`` /
                                             ``DUPLICATE_SUPPRESSED`` /
                                             ``INVALID_SUPPRESSED``.
      * ``suppress_reason``               -- ``NONE`` /
                                             ``DUPLICATE_IDENTITY`` /
                                             ``MISSING_IDENTITY``.
      * ``duplicate_of_session_id``       -- the first-occurrence session
                                             id (only for a duplicate).
      * ``duplicate_of_artifact_filename``-- the first-occurrence filename
                                             (only for a duplicate).

    A passive carrier (no validation at construction); every field is a
    safe scalar or ``None``, so the record is serializable.
    """

    session_id: Optional[str]
    session_dir: str
    artifact_filename: str
    member_kind: Optional[str]
    ping_id: Optional[str]
    dedupe_key: Optional[str]
    identity_kind: str
    identity_value: Optional[str]
    dedupe_status: str
    suppress_reason: str
    duplicate_of_session_id: Optional[str] = None
    duplicate_of_artifact_filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: per-session index record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8SessionIndexRecord:
    """Immutable index record for ONE compact session bundle.

      * ``session_id``                      -- the bundle (manifest) session
                                               id.
      * ``session_dir``                     -- the bundle directory path.
      * ``bundle_schema_version``           -- the bundle envelope schema
                                               version read from the
                                               manifest.
      * ``ping_artifact_count``             -- total ping artifacts in this
                                               session.
      * ``retained_ping_count``             -- retained (unique) pings.
      * ``duplicate_suppressed_ping_count`` -- pings suppressed as duplicate
                                               identities.
      * ``invalid_suppressed_ping_count``   -- pings suppressed for a
                                               missing dedupe identity.
      * ``pings``                           -- the per-ping index records,
                                               in deterministic filename
                                               order.

    A passive carrier; serializable. ``session_id`` is ``Optional`` only
    to stay honest about the lenient reader (a manifest whose
    ``session_id`` is absent / non-string reads back as ``None``); a real
    Stage 30.8.2 bundle always carries a non-empty string session id.
    """

    session_id: Optional[str]
    session_dir: str
    bundle_schema_version: Optional[str]
    ping_artifact_count: int
    retained_ping_count: int
    duplicate_suppressed_ping_count: int
    invalid_suppressed_ping_count: int
    pings: Tuple[Stage30_8IndexedPingArtifact, ...] = ()


# ---------------------------------------------------------------------------
# Immutable record: index build result (top-level output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8SessionIndexBuildResult:
    """Immutable Stage 30.8.3 session index build result.

      * ``status``                     -- ``BUILT`` / ``EMPTY`` /
                                          ``INVALID_INPUT`` / ``READ_FAILED``
                                          / ``INDEX_FAILED``.
      * ``reason``                     -- a closed-set
                                          ``INDEX_BUILD_REASON_*`` token.
      * ``index_schema_version``       -- the Stage 30.8.3 index schema
                                          version.
      * ``session_count``              -- number of session bundles indexed.
      * ``total_ping_count``           -- total ping artifacts across all
                                          sessions.
      * ``retained_count``             -- unique retained pings.
      * ``duplicate_suppressed_count`` -- duplicate-suppressed pings.
      * ``invalid_suppressed_count``   -- identity-less suppressed pings.
      * ``sessions``                   -- per-session records, ordered by
                                          (session_id, session_dir).
      * ``retained_pings``             -- the flat retained set, in
                                          deterministic order (the set to
                                          consider for later collection /
                                          replay).
      * ``duplicate_pings``            -- the flat duplicate-suppressed set,
                                          deterministic order.
      * ``invalid_pings``              -- the flat identity-less set,
                                          deterministic order.
      * ``blocked_session_dir``        -- the offending session dir, only on
                                          ``READ_FAILED`` / some
                                          ``INVALID_INPUT`` cases.
      * ``read_failure_reason``        -- the underlying reader reason, only
                                          on ``READ_FAILED``.

    A passive verdict record; serializable. The builder NEVER raises and
    NEVER writes any file -- the result is a pure in-memory projection.
    """

    status: str
    reason: str
    index_schema_version: str
    session_count: int
    total_ping_count: int
    retained_count: int
    duplicate_suppressed_count: int
    invalid_suppressed_count: int
    sessions: Tuple[Stage30_8SessionIndexRecord, ...] = ()
    retained_pings: Tuple[Stage30_8IndexedPingArtifact, ...] = ()
    duplicate_pings: Tuple[Stage30_8IndexedPingArtifact, ...] = ()
    invalid_pings: Tuple[Stage30_8IndexedPingArtifact, ...] = ()
    blocked_session_dir: Optional[str] = None
    read_failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def indexed_ping_artifact_field_names() -> Tuple[str, ...]:
    """Return the indexed ping record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8IndexedPingArtifact))


def session_index_record_field_names() -> Tuple[str, ...]:
    """Return the per-session index record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8SessionIndexRecord))


def session_index_build_result_field_names() -> Tuple[str, ...]:
    """Return the build result record field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_8SessionIndexBuildResult)
    )


__all__ = (
    # Minor version + index schema identity.
    "STAGE30_8_3_MINOR_VERSION",
    "STAGE30_8_3_INDEX_SCHEMA_VERSION",
    # Build status.
    "INDEX_BUILD_STATUS_BUILT",
    "INDEX_BUILD_STATUS_EMPTY",
    "INDEX_BUILD_STATUS_INVALID_INPUT",
    "INDEX_BUILD_STATUS_READ_FAILED",
    "INDEX_BUILD_STATUS_INDEX_FAILED",
    "STAGE30_8_3_INDEX_BUILD_STATUS_VALUES",
    "is_index_build_status",
    # Build reason.
    "INDEX_BUILD_REASON_OK",
    "INDEX_BUILD_REASON_EMPTY",
    "INDEX_BUILD_REASON_NO_SOURCE",
    "INDEX_BUILD_REASON_AMBIGUOUS_SOURCE",
    "INDEX_BUILD_REASON_INVALID_SESSION_DIRS",
    "INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT",
    "INDEX_BUILD_REASON_BUNDLE_READ_FAILED",
    "INDEX_BUILD_REASON_INTERNAL_ERROR",
    "STAGE30_8_3_INDEX_BUILD_REASONS",
    # Ping dedupe status.
    "PING_DEDUPE_STATUS_RETAINED",
    "PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED",
    "PING_DEDUPE_STATUS_INVALID_SUPPRESSED",
    "STAGE30_8_3_PING_DEDUPE_STATUS_VALUES",
    "is_ping_dedupe_status",
    # Ping suppress reason.
    "PING_SUPPRESS_REASON_NONE",
    "PING_SUPPRESS_REASON_DUPLICATE_IDENTITY",
    "PING_SUPPRESS_REASON_MISSING_IDENTITY",
    "PING_SUPPRESS_REASON_SESSION_ID_MISMATCH",
    "STAGE30_8_3_PING_SUPPRESS_REASONS",
    # Dedupe identity kind.
    "DEDUPE_IDENTITY_KIND_DEDUPE_KEY",
    "DEDUPE_IDENTITY_KIND_NONE",
    "STAGE30_8_3_DEDUPE_IDENTITY_KINDS",
    # Dedupe identity record + resolution.
    "Stage30_8DedupeIdentity",
    "resolve_ping_dedupe_identity",
    "has_dedupe_identity",
    # Index records.
    "Stage30_8IndexedPingArtifact",
    "Stage30_8SessionIndexRecord",
    "Stage30_8SessionIndexBuildResult",
    # Field-name helpers.
    "indexed_ping_artifact_field_names",
    "session_index_record_field_names",
    "session_index_build_result_field_names",
)
