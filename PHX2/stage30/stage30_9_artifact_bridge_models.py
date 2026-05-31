"""Stage 30.9.1 compact session artifact bridge models.

Stage 30.9.1 ships the passive, pure, stdlib-only model layer for the
Stage 30.9 offline artifact bridge: the records the bridge passes between
its three pieces (a thin innermost capture transport, a post-session
projector, and an offline write -> read -> index proof helper) plus the
closed-set status / reason vocabularies they all share.

The bridge persists Stage 30.8-format compact session artifacts AFTER a
bounded private live-shaped session ends:

    Stage 30.9.1 capture transport (records what was sent)
      -> Stage 30.9.1 post-session projector
         (capture records + dispatch-ledger context -> a Stage 30.8 bundle)
      -> Stage 30.8.2 temp-dir writer  (ONE bundle, post-session only)
      -> Stage 30.8.3 manifest-backed reader
      -> Stage 30.8.3 session index / dedupe builder
      -> Stage 30.9.1 bridge proof summary

This module is the model layer ONLY. It implements NO capture transport
(that is ``stage30_9_capture_transport``), NO projector (that is
``stage30_9_artifact_projector``), and NO proof helper (that is
``stage30_9_artifact_bridge_proof``). It reads no filesystem, opens no
network, reads no environment, opens no database, and constructs no
Stage 30.8 artifact bundle.

Every record here is a frozen dataclass carrying only safe scalars:
opaque ids, closed-set tokens, already-rendered display strings,
ISO-8601 UTC timestamps, and integer counters. The records are PASSIVE
carriers; the projector / proof helper enforce the bridge contract and
fail closed.

Closed-set vocabularies pinned here:

  * bridge status -- ``CAPTURED`` / ``PROJECTED`` / ``WRITTEN_AND_INDEXED``
    / ``INVALID_INPUT`` / ``PROJECT_FAILED`` / ``WRITE_FAILED`` /
    ``READ_FAILED`` / ``INDEX_FAILED``.
  * bridge reason -- ``NONE`` / ``MISSING_RUN_ID`` / ``MISSING_SESSION_ID``
    / ``MISSING_DEDUPE_KEY`` / ``MISSING_COMPACT_BODY`` / ``COUNT_MISMATCH``
    / ``AMBIGUOUS_JOIN`` / ``NON_PRIVATE_WEBHOOK`` / ``WRITER_REJECTED`` /
    ``READER_REJECTED`` / ``INDEX_REJECTED``.
  * the safe private webhook identity label allowlist (mirrors the Stage
    28.4 ``PRIVATE_OPERATOR_WEBHOOK`` value BY VALUE; this module imports
    no Stage 28 module).
  * the bridge proof summary schema version.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.8.1 / 30.8.3 / 30.8.4
    models modules). The projector-result ``bundle`` field is typed
    ``Optional[object]`` so this module need not import the Stage 30.8
    bundle type; the projector constructs the real
    ``Stage30_8CompactSessionArtifactBundle`` there.
  * No filesystem / env / network / database / compression access. No
    ``open`` / ``pathlib`` / ``os`` / ``json`` / ``sqlite3``. No top-level
    Call (no implicit I/O at import time; the ``@dataclass(frozen=True)``
    decorators are decorator-list Calls, not body-statement Calls; the
    deterministic scenarios are built by their builder functions at call
    time, never as module-level constructed constants).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + bridge proof schema identity
# ---------------------------------------------------------------------------


STAGE30_9_1_MINOR_VERSION: str = "30.9.1"


# The Stage 30.9.1 bridge proof summary schema version. Distinct from the
# Stage 30.8 per-artifact / bundle-envelope / session-index / proof schema
# versions: this names the offline artifact-bridge proof summary shape.
STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION: str = (
    "stage30_9_v0_compact_artifact_bridge_proof"
)


# ---------------------------------------------------------------------------
# Closed-set: bridge status
# ---------------------------------------------------------------------------
#
# The phases / outcomes a bridge step may report. The capture transport
# reports ``CAPTURED``; the projector reports ``PROJECTED`` (success) or a
# fail-closed status; the proof helper reports ``WRITTEN_AND_INDEXED``
# (full success) or the fail-closed status of the FIRST failing pipeline
# stage.


BRIDGE_STATUS_CAPTURED: str = "CAPTURED"
BRIDGE_STATUS_PROJECTED: str = "PROJECTED"
BRIDGE_STATUS_WRITTEN_AND_INDEXED: str = "WRITTEN_AND_INDEXED"
BRIDGE_STATUS_INVALID_INPUT: str = "INVALID_INPUT"
BRIDGE_STATUS_PROJECT_FAILED: str = "PROJECT_FAILED"
BRIDGE_STATUS_WRITE_FAILED: str = "WRITE_FAILED"
BRIDGE_STATUS_READ_FAILED: str = "READ_FAILED"
BRIDGE_STATUS_INDEX_FAILED: str = "INDEX_FAILED"


STAGE30_9_1_BRIDGE_STATUS_VALUES: Tuple[str, ...] = (
    BRIDGE_STATUS_CAPTURED,
    BRIDGE_STATUS_PROJECTED,
    BRIDGE_STATUS_WRITTEN_AND_INDEXED,
    BRIDGE_STATUS_INVALID_INPUT,
    BRIDGE_STATUS_PROJECT_FAILED,
    BRIDGE_STATUS_WRITE_FAILED,
    BRIDGE_STATUS_READ_FAILED,
    BRIDGE_STATUS_INDEX_FAILED,
)


def is_bridge_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set bridge status."""
    return (
        isinstance(value, str)
        and value in STAGE30_9_1_BRIDGE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: bridge reason
# ---------------------------------------------------------------------------
#
# ``NONE`` accompanies a success status; every other token accompanies a
# fail-closed status. The projector owns the ``MISSING_* / COUNT_MISMATCH /
# AMBIGUOUS_JOIN / NON_PRIVATE_WEBHOOK`` reasons (surfaced via
# ``INVALID_INPUT``); the proof helper owns ``WRITER_REJECTED`` /
# ``READER_REJECTED`` / ``INDEX_REJECTED`` (surfaced via ``WRITE_FAILED`` /
# ``READ_FAILED`` / ``INDEX_FAILED``).


BRIDGE_REASON_NONE: str = "NONE"
BRIDGE_REASON_MISSING_RUN_ID: str = "MISSING_RUN_ID"
BRIDGE_REASON_MISSING_SESSION_ID: str = "MISSING_SESSION_ID"
BRIDGE_REASON_MISSING_PING_ID: str = "MISSING_PING_ID"
BRIDGE_REASON_MISSING_CANDIDATE_ID: str = "MISSING_CANDIDATE_ID"
BRIDGE_REASON_MISSING_TOKEN_MINT: str = "MISSING_TOKEN_MINT"
BRIDGE_REASON_MISSING_DEDUPE_KEY: str = "MISSING_DEDUPE_KEY"
BRIDGE_REASON_MISSING_COMPACT_BODY: str = "MISSING_COMPACT_BODY"
BRIDGE_REASON_MISSING_CAPTURE_INDEX: str = "MISSING_CAPTURE_INDEX"
BRIDGE_REASON_COUNT_MISMATCH: str = "COUNT_MISMATCH"
BRIDGE_REASON_AMBIGUOUS_JOIN: str = "AMBIGUOUS_JOIN"
BRIDGE_REASON_NON_PRIVATE_WEBHOOK: str = "NON_PRIVATE_WEBHOOK"
BRIDGE_REASON_WRITER_REJECTED: str = "WRITER_REJECTED"
BRIDGE_REASON_READER_REJECTED: str = "READER_REJECTED"
BRIDGE_REASON_INDEX_REJECTED: str = "INDEX_REJECTED"


STAGE30_9_1_BRIDGE_REASON_VALUES: Tuple[str, ...] = (
    BRIDGE_REASON_NONE,
    BRIDGE_REASON_MISSING_RUN_ID,
    BRIDGE_REASON_MISSING_SESSION_ID,
    BRIDGE_REASON_MISSING_PING_ID,
    BRIDGE_REASON_MISSING_CANDIDATE_ID,
    BRIDGE_REASON_MISSING_TOKEN_MINT,
    BRIDGE_REASON_MISSING_DEDUPE_KEY,
    BRIDGE_REASON_MISSING_COMPACT_BODY,
    BRIDGE_REASON_MISSING_CAPTURE_INDEX,
    BRIDGE_REASON_COUNT_MISMATCH,
    BRIDGE_REASON_AMBIGUOUS_JOIN,
    BRIDGE_REASON_NON_PRIVATE_WEBHOOK,
    BRIDGE_REASON_WRITER_REJECTED,
    BRIDGE_REASON_READER_REJECTED,
    BRIDGE_REASON_INDEX_REJECTED,
)


def is_bridge_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set bridge reason."""
    return (
        isinstance(value, str)
        and value in STAGE30_9_1_BRIDGE_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Safe private webhook identity allowlist
# ---------------------------------------------------------------------------
#
# The capture transport records a safe-to-display ``webhook_identity``
# LABEL (never a destination). The projector fails closed
# (``NON_PRIVATE_WEBHOOK``) on any capture whose identity is not one of
# these private labels, so a non-private routing identity can never be
# projected into a persisted artifact. The canonical private-operator
# label mirrors the Stage 28.4 ``WEBHOOK_IDENTITY_PRIVATE_OPERATOR`` value
# BY VALUE; this module imports no Stage 28 module.


PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR: str = "PRIVATE_OPERATOR_WEBHOOK"


STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES: Tuple[str, ...] = (
    PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)


def is_private_webhook_identity(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set private webhook
    identity label. Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES
    )


# ---------------------------------------------------------------------------
# Sanitized transport status (closed set)
# ---------------------------------------------------------------------------
#
# The capture transport stores ONLY one of these closed-set sanitized
# transport status tokens (never a raw inner-result string). The recognized
# tokens mirror the Stage 28.4 transport-status vocabulary BY VALUE (this
# module imports no Stage 28 module), so a legitimate live status is
# preserved faithfully; any unrecognized / non-string / empty status
# normalizes to the closed ``UNKNOWN_TRANSPORT_STATUS`` fallback so an
# unexpected inner-result string can never reach a capture record / artifact.


SANITIZED_TRANSPORT_STATUS_SENT_OK: str = "SENT_OK"
SANITIZED_TRANSPORT_STATUS_RATE_LIMITED: str = "RATE_LIMITED"
SANITIZED_TRANSPORT_STATUS_SERVER_ERROR: str = "SERVER_ERROR"
SANITIZED_TRANSPORT_STATUS_NETWORK_ERROR: str = "NETWORK_ERROR"
SANITIZED_TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED: str = (
    "AUTH_OR_WEBHOOK_REFUSED"
)
SANITIZED_TRANSPORT_STATUS_VALIDATION_FAILED: str = "VALIDATION_FAILED"
SANITIZED_TRANSPORT_STATUS_PAYLOAD_REFUSED: str = "PAYLOAD_REFUSED"
SANITIZED_TRANSPORT_STATUS_UNKNOWN: str = "UNKNOWN_TRANSPORT_STATUS"


STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES: Tuple[str, ...] = (
    SANITIZED_TRANSPORT_STATUS_SENT_OK,
    SANITIZED_TRANSPORT_STATUS_RATE_LIMITED,
    SANITIZED_TRANSPORT_STATUS_SERVER_ERROR,
    SANITIZED_TRANSPORT_STATUS_NETWORK_ERROR,
    SANITIZED_TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    SANITIZED_TRANSPORT_STATUS_VALIDATION_FAILED,
    SANITIZED_TRANSPORT_STATUS_PAYLOAD_REFUSED,
    SANITIZED_TRANSPORT_STATUS_UNKNOWN,
)


def is_sanitized_transport_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set sanitized transport
    status token. Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES
    )


def normalize_transport_status(value: object) -> str:
    """Return the closed-set sanitized transport status for ``value``.

    A recognized non-empty token (one of
    ``STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES``) is returned verbatim;
    anything else -- an unrecognized non-empty string, an empty string, a
    non-string, or ``None`` -- normalizes to ``UNKNOWN_TRANSPORT_STATUS``.
    Pure / total; never raises. Never inspects any attribute of an object
    (callers pass the already-extracted status string), so no secret-bearing
    field can leak through.
    """
    if (
        isinstance(value, str)
        and value in STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES
    ):
        return value
    return SANITIZED_TRANSPORT_STATUS_UNKNOWN


# ---------------------------------------------------------------------------
# Immutable record: capture record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9CaptureRecord:
    """Immutable record of ONE compact private send, as observed by the
    Stage 30.9.1 capture transport (a passive carrier).

      * ``capture_index``              -- the 0-based send-order index the
                                          capture transport assigns (the
                                          stable join key to the dispatch
                                          context).
      * ``webhook_identity``           -- the safe-to-display webhook
                                          identity label forwarded to the
                                          inner transport (never a
                                          destination).
      * ``payload_body_text``          -- the enriched compact body string
                                          exactly as sent (the payload's
                                          ``content``; an immutable string
                                          snapshot, so a later mutation of
                                          the caller's payload dict can
                                          never retroactively change it).
      * ``payload_keys``               -- the sorted tuple of payload
                                          mapping keys (provenance; helps
                                          prove the body was the
                                          ``content`` slot).
      * ``sanitized_transport_status`` -- the inner transport result's
                                          closed-set status token, read
                                          defensively (never the raw
                                          result object, never a secret).
      * ``candidate_id``               -- candidate id IF present in the
                                          payload metadata, else ``None``
                                          (the authoritative candidate id
                                          comes from the dispatch context).
      * ``ping_id``                    -- ping id IF present in the payload
                                          metadata, else ``None`` (the
                                          authoritative ping id comes from
                                          the dispatch context).
    """

    capture_index: int
    webhook_identity: Optional[str]
    payload_body_text: Optional[str]
    payload_keys: Tuple[str, ...] = ()
    sanitized_transport_status: Optional[str] = None
    candidate_id: Optional[str] = None
    ping_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: capture batch summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9CaptureBatchSummary:
    """Immutable passive summary of a capture transport's recorded batch.

    Returned by the capture transport's ``batch_summary()`` for offline
    tests / proof composition. ``status`` is always ``CAPTURED`` (the
    capture transport only records; it never projects or persists).

      * ``status``         -- the closed-set ``CAPTURED`` token.
      * ``capture_count``  -- number of capture records recorded.
      * ``records``        -- the capture records, in send order.
    """

    status: str
    capture_count: int
    records: Tuple[Stage30_9CaptureRecord, ...] = ()


# ---------------------------------------------------------------------------
# Immutable record: dispatch context record (passive ledger-shaped carrier)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9DispatchContextRecord:
    """Immutable passive carrier for the runtime dispatch-ledger context of
    ONE compact private send (a duck-typed mirror of the Stage 28.2 /
    Stage 28.9 dispatch-ledger / runtime-context shape; this module imports
    no Stage 28 module).

    The ``dedupe_key`` is the ALREADY-SERIALIZED runtime dispatch-ledger
    dedupe key string (the projector carries it into the Stage 30.8 ping
    artifact verbatim; it NEVER recomputes a dedupe key).

      * ``capture_index``    -- the stable join key to the capture record.
      * ``dedupe_key``       -- the runtime dispatch-ledger dedupe key
                                (already serialized; carried verbatim).
      * ``candidate_id``     -- the candidate id from the live candidate /
                                adapter path.
      * ``ping_id``          -- the compact ping id from the live candidate
                                / adapter path.
      * ``token_mint``       -- the safe-shape token mint (when available).
      * ``ping_session_id``  -- OPTIONAL per-ping recorded session scope.
                                ``None`` (the default) means the ping
                                artifact's identity session id is the run's
                                config session id (Section 7 provenance:
                                session id from the live config). A context
                                that records a DIFFERENT session scope
                                yields a ping the post-run Stage 30.8.3
                                index suppresses as ``SESSION_ID_MISMATCH``
                                -- the offline invalid-artifact path,
                                proven without weakening the writer or the
                                runtime dedupe.
      * ``dedupe_state``     -- OPTIONAL closed-set runtime dedupe-state
                                echo (provenance only; never recomputed).
    """

    capture_index: int
    dedupe_key: Optional[str]
    candidate_id: Optional[str] = None
    ping_id: Optional[str] = None
    token_mint: Optional[str] = None
    ping_session_id: Optional[str] = None
    dedupe_state: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: session summary counters (projector input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9SessionSummaryCounters:
    """Immutable OPTIONAL per-session counters the projector embeds in the
    emitted Stage 30.8 session summary artifact. Each is a non-negative
    integer (the projector validates). When the projector is given no
    counters it derives them from the projected artifacts.

      * ``pings_emitted``     -- compact pings emitted in the session.
      * ``dispatch_attempts`` -- dispatch / send attempts.
      * ``dedupe_suppressed`` -- candidates the RUNTIME dedupe suppressed
                                 before send (recorded by the runtime, NOT
                                 recomputed by the bridge).
      * ``errors``            -- closed-set transport / capture errors.
    """

    pings_emitted: Optional[int] = None
    dispatch_attempts: Optional[int] = None
    dedupe_suppressed: Optional[int] = None
    errors: Optional[int] = None


# ---------------------------------------------------------------------------
# Immutable record: projector result (passive verdict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9ProjectorResult:
    """Immutable Stage 30.9.1 projector result (a passive verdict record).

      * ``status``                  -- ``PROJECTED`` (a bundle was built)
                                       / ``INVALID_INPUT`` (a normal
                                       fail-closed input) / ``PROJECT_FAILED``
                                       (an unexpected internal error).
      * ``reason``                  -- a closed-set bridge reason
                                       (``NONE`` on success).
      * ``blocked_field``           -- the offending field / record label,
                                       or ``None``.
      * ``bundle``                  -- the emitted Stage 30.8 compact
                                       session artifact bundle on success,
                                       else ``None``. Typed ``object`` so
                                       this models module imports no Stage
                                       30.8 module; the projector
                                       constructs the real
                                       ``Stage30_8CompactSessionArtifactBundle``.
      * ``ping_artifact_count``     -- compact ping artifacts emitted.
      * ``dispatch_attempt_count``  -- dispatch attempt artifacts emitted.
      * ``error_artifact_count``    -- error artifacts emitted.
    """

    status: str
    reason: str
    blocked_field: Optional[str]
    bundle: Optional[object]
    ping_artifact_count: int
    dispatch_attempt_count: int
    error_artifact_count: int


# ---------------------------------------------------------------------------
# Immutable record: bridge scenario (deterministic fake input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9BridgeScenario:
    """Immutable, deterministic fake bridge scenario.

    Carries one private-soak session's worth of capture records + the
    matching dispatch-ledger context records, plus the author-verified
    expected post-run index counts the bridge proof reports (the tests
    cross-check the live counts against these). A passive carrier; it
    performs no I/O and constructs no artifact. All ids / bodies are safe
    opaque strings; the created-at timestamp is a fixed ISO-8601 UTC
    constant (the bridge reads no wall clock).

      * ``name``                          -- the scenario name.
      * ``run_id`` / ``session_id``       -- the run / session identity
                                             (from the live config).
      * ``artifact_created_at_utc``       -- the fixed artifact timestamp.
      * ``capture_records``               -- the recorded sends, in order.
      * ``dispatch_context_records``      -- the dispatch-ledger context,
                                             one per capture (joined by
                                             ``capture_index``).
      * ``session_summary_counters``      -- optional summary counters.
      * ``expected_ping_count``           -- expected ping members read.
      * ``expected_retained``             -- expected unique retained pings.
      * ``expected_duplicate_suppressed`` -- expected duplicate-suppressed.
      * ``expected_invalid_suppressed``   -- expected session-mismatched /
                                             identity-less suppressed pings.
    """

    name: str
    run_id: str
    session_id: str
    artifact_created_at_utc: str
    capture_records: Tuple[Stage30_9CaptureRecord, ...]
    dispatch_context_records: Tuple[Stage30_9DispatchContextRecord, ...]
    session_summary_counters: Optional[Stage30_9SessionSummaryCounters]
    expected_ping_count: int
    expected_retained: int
    expected_duplicate_suppressed: int
    expected_invalid_suppressed: int


# ---------------------------------------------------------------------------
# Immutable record: bridge proof summary (passive verdict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9BridgeProofSummary:
    """Immutable Stage 30.9.1 bridge proof summary (a passive verdict).

    Records the pipeline outcome + counts + capability flags. Carries NO
    secret, NO raw provider payload, and NO absolute path (only the
    relative, safe scenario session id). The same input yields the same
    summary on every run, in any temp dir.

      * ``status``                    -- a closed-set bridge status
                                         (``WRITTEN_AND_INDEXED`` on full
                                         success; else the fail-closed
                                         status of the first failing stage).
      * ``reason``                    -- a closed-set bridge reason.
      * ``bridge_proof_schema_version``-- the Stage 30.9.1 bridge proof
                                         schema id.
      * ``scenario_name``             -- the scenario name.
      * ``proof_session_id``          -- the relative, safe session id
                                         (never an absolute path).
      * ``capture_record_count``      -- capture records the proof
                                         projected from.
      * ``ping_artifacts_projected``  -- ping artifacts the projector
                                         emitted.
      * ``dispatch_attempts_projected``-- dispatch attempt artifacts
                                         emitted.
      * ``error_artifacts_projected`` -- error artifacts emitted.
      * ``bundles_written_count``     -- bundles the writer persisted (0 or
                                         1; the bridge writes ONE bundle).
      * ``bundles_read_count``        -- bundles the reader read back (0/1).
      * ``ping_artifacts_seen``       -- ping members the reader returned.
      * ``retained_count``            -- unique retained pings (index).
      * ``duplicate_suppressed_count``-- duplicate-suppressed pings (index).
      * ``invalid_suppressed_count``  -- session-mismatched / identity-less
                                         suppressed pings (index).
      * ``capture_transport_used`` / ``projector_used`` / ``writer_used`` /
        ``reader_used`` / ``index_builder_used``
                                      -- which composed pieces the proof
                                         actually invoked.
      * ``live_provider_used`` / ``discord_send_used`` / ``env_read_used``
        / ``db_used`` / ``zstd_used``
                                      -- forbidden-surface flags; ALWAYS
                                         ``False`` (the proof structurally
                                         cannot reach them).
      * ``single_bundle_write``       -- exactly one Stage 30.8 bundle write
                                         (never a per-ping write); ALWAYS
                                         ``True``.
      * ``no_default_storage_root``   -- only the caller-provided output dir
                                         was used; ALWAYS ``True``.
      * ``dedupe_key_from_dispatch_context`` -- every retained ping's dedupe
                                         identity came from the dispatch
                                         context (never recomputed).
    """

    status: str
    reason: str
    bridge_proof_schema_version: str
    scenario_name: str
    proof_session_id: Optional[str]
    capture_record_count: int
    ping_artifacts_projected: int
    dispatch_attempts_projected: int
    error_artifacts_projected: int
    bundles_written_count: int
    bundles_read_count: int
    ping_artifacts_seen: int
    retained_count: int
    duplicate_suppressed_count: int
    invalid_suppressed_count: int
    capture_transport_used: bool
    projector_used: bool
    writer_used: bool
    reader_used: bool
    index_builder_used: bool
    live_provider_used: bool
    discord_send_used: bool
    env_read_used: bool
    db_used: bool
    zstd_used: bool
    single_bundle_write: bool
    no_default_storage_root: bool
    dedupe_key_from_dispatch_context: bool


# ---------------------------------------------------------------------------
# Deterministic fake bridge scenario building blocks (plain literals)
# ---------------------------------------------------------------------------
#
# Every value below is a plain string / int literal (no Call), so this
# module carries no top-level Call. The scenario builders assemble them
# into ``Stage30_9BridgeScenario`` records at call time. The session id is
# a safe single path component (the Stage 30.8.2 writer uses it as the
# per-session subdir name); the mismatch session id deliberately differs
# from it (drives the post-run ``SESSION_ID_MISMATCH`` invalid case through
# the writer, exactly as the Stage 30.8.4 proof does). The dedupe keys /
# ping ids / candidate ids / mints / bodies are safe opaque strings; the
# created-at timestamp is a FIXED ISO-8601 UTC constant (the bridge reads
# no wall clock). The transport statuses mirror the Stage 28.4 closed-set
# tokens BY VALUE (this module imports no Stage 28 module).


STAGE30_9_1_DEFAULT_SCENARIO_NAME: str = (
    "stage30_9_1_default_dedupe_bridge"
)
STAGE30_9_1_MISMATCH_SCENARIO_NAME: str = (
    "stage30_9_1_mismatch_dedupe_bridge"
)


STAGE30_9_1_SCENARIO_RUN_ID: str = "stage30-9-1-bridge-run"
STAGE30_9_1_SCENARIO_SESSION_ID: str = "stage30-9-1-bridge-session"
STAGE30_9_1_SCENARIO_CREATED_AT_UTC: str = "2026-01-01T00:00:00Z"


# A ping's recorded session scope that deliberately does NOT match the
# bundle (config) session id -> the writer accepts the artifact; the
# Stage 30.8.3 index suppresses it (SESSION_ID_MISMATCH).
STAGE30_9_1_SCENARIO_MISMATCH_SESSION_ID: str = (
    "stage30-9-1-bridge-session-x"
)


# The fake dedupe keys (already-serialized runtime dispatch-ledger keys).
# K1 repeats (a duplicate-by-dedupe-key send carrying a DIFFERENT ping id);
# K2 is unique; K3 belongs to the mismatched ping (never retained).
STAGE30_9_1_SCENARIO_DEDUPE_KEY_1: str = "stage30-9-1-bridge-dedupe-k1"
STAGE30_9_1_SCENARIO_DEDUPE_KEY_2: str = "stage30-9-1-bridge-dedupe-k2"
STAGE30_9_1_SCENARIO_DEDUPE_KEY_3: str = "stage30-9-1-bridge-dedupe-k3"


# The fake ping / candidate / mint ids (each unique; the duplicate send
# carries a DIFFERENT ping id from its first occurrence but the SAME dedupe
# key, so the bridge proves dedupe is driven by dedupe_key, never ping_id).
STAGE30_9_1_SCENARIO_PING_1_ID: str = "stage30-9-1-bridge-ping-p1"
STAGE30_9_1_SCENARIO_PING_2_ID: str = "stage30-9-1-bridge-ping-p2"
STAGE30_9_1_SCENARIO_PING_3_ID: str = "stage30-9-1-bridge-ping-p3"
STAGE30_9_1_SCENARIO_PING_4_ID: str = "stage30-9-1-bridge-ping-p4"
STAGE30_9_1_SCENARIO_CANDIDATE_1_ID: str = "stage30-9-1-bridge-cand-c1"
STAGE30_9_1_SCENARIO_CANDIDATE_2_ID: str = "stage30-9-1-bridge-cand-c2"
STAGE30_9_1_SCENARIO_CANDIDATE_3_ID: str = "stage30-9-1-bridge-cand-c3"
STAGE30_9_1_SCENARIO_MINT_1: str = "stage30-9-1-bridge-mint-m1"
STAGE30_9_1_SCENARIO_MINT_2: str = "stage30-9-1-bridge-mint-m2"
STAGE30_9_1_SCENARIO_MINT_3: str = "stage30-9-1-bridge-mint-m3"


# The safe compact body prefix; the scenario appends the ping id.
STAGE30_9_1_SCENARIO_COMPACT_BODY_PREFIX: str = (
    "stage30-9-1 bridge compact body "
)


# The transport status tokens (mirror the Stage 28.4 closed-set values).
STAGE30_9_1_SCENARIO_STATUS_SENT_OK: str = "SENT_OK"
STAGE30_9_1_SCENARIO_STATUS_RATE_LIMITED: str = "RATE_LIMITED"


# Author-verified expected post-run index counts. The default scenario:
# 3 ping artifacts / 2 retained (K1, K2) / 1 duplicate-suppressed (the
# second K1, a different ping id) / 0 invalid-suppressed. The mismatch
# scenario adds a 4th ping whose recorded session scope diverges -> 4 ping
# artifacts / 2 retained / 1 duplicate / 1 invalid-suppressed.
STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT: int = 3
STAGE30_9_1_DEFAULT_EXPECTED_RETAINED: int = 2
STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED: int = 1
STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED: int = 0

STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT: int = 4
STAGE30_9_1_MISMATCH_EXPECTED_RETAINED: int = 2
STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED: int = 1
STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED: int = 1


def _scenario_body(ping_id: str) -> str:
    """Return the safe compact body text for ``ping_id``. Pure."""
    return STAGE30_9_1_SCENARIO_COMPACT_BODY_PREFIX + ping_id


def _default_capture_records() -> Tuple[Stage30_9CaptureRecord, ...]:
    """Build the three default-scenario capture records (in send order).

    Two SENT_OK sends carrying the SAME dedupe key with DIFFERENT ping ids
    (a duplicate-by-dedupe-key pair), then a RATE_LIMITED send with a unique
    dedupe key (a non-success status -> an error artifact). The bodies are
    immutable string snapshots; every webhook identity is the private
    operator label. Pure.
    """
    return (
        Stage30_9CaptureRecord(
            capture_index=0,
            webhook_identity=PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload_body_text=_scenario_body(STAGE30_9_1_SCENARIO_PING_1_ID),
            payload_keys=("content",),
            sanitized_transport_status=(
                STAGE30_9_1_SCENARIO_STATUS_SENT_OK
            ),
        ),
        Stage30_9CaptureRecord(
            capture_index=1,
            webhook_identity=PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload_body_text=_scenario_body(STAGE30_9_1_SCENARIO_PING_2_ID),
            payload_keys=("content",),
            sanitized_transport_status=(
                STAGE30_9_1_SCENARIO_STATUS_SENT_OK
            ),
        ),
        Stage30_9CaptureRecord(
            capture_index=2,
            webhook_identity=PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload_body_text=_scenario_body(STAGE30_9_1_SCENARIO_PING_3_ID),
            payload_keys=("content",),
            sanitized_transport_status=(
                STAGE30_9_1_SCENARIO_STATUS_RATE_LIMITED
            ),
        ),
    )


def _default_dispatch_context_records() -> Tuple[
    Stage30_9DispatchContextRecord, ...
]:
    """Build the three default-scenario dispatch context records.

    Each references its capture by ``capture_index`` and carries the
    runtime dispatch-ledger dedupe key VERBATIM. Contexts 0 and 1 share the
    SAME dedupe key (K1) with different ping ids; context 2 is unique (K2).
    None records a divergent session scope (all retain at the config
    session). Pure.
    """
    return (
        Stage30_9DispatchContextRecord(
            capture_index=0,
            dedupe_key=STAGE30_9_1_SCENARIO_DEDUPE_KEY_1,
            candidate_id=STAGE30_9_1_SCENARIO_CANDIDATE_1_ID,
            ping_id=STAGE30_9_1_SCENARIO_PING_1_ID,
            token_mint=STAGE30_9_1_SCENARIO_MINT_1,
        ),
        Stage30_9DispatchContextRecord(
            capture_index=1,
            dedupe_key=STAGE30_9_1_SCENARIO_DEDUPE_KEY_1,
            candidate_id=STAGE30_9_1_SCENARIO_CANDIDATE_1_ID,
            ping_id=STAGE30_9_1_SCENARIO_PING_2_ID,
            token_mint=STAGE30_9_1_SCENARIO_MINT_1,
        ),
        Stage30_9DispatchContextRecord(
            capture_index=2,
            dedupe_key=STAGE30_9_1_SCENARIO_DEDUPE_KEY_2,
            candidate_id=STAGE30_9_1_SCENARIO_CANDIDATE_2_ID,
            ping_id=STAGE30_9_1_SCENARIO_PING_3_ID,
            token_mint=STAGE30_9_1_SCENARIO_MINT_2,
        ),
    )


def default_bridge_scenario() -> Stage30_9BridgeScenario:
    """Build and return the deterministic default bridge scenario.

    One session, three captured sends (two share a dedupe key with
    different ping ids; one is rate-limited). Expected post-run index:
    2 retained, 1 duplicate-suppressed, 0 invalid-suppressed. Pure / total;
    reads nothing and returns the same value on every call (no clock, no
    randomness, no filesystem). The dataclass is constructed HERE (inside a
    function), never as a module-level constant, so the module carries no
    top-level Call.
    """
    return Stage30_9BridgeScenario(
        name=STAGE30_9_1_DEFAULT_SCENARIO_NAME,
        run_id=STAGE30_9_1_SCENARIO_RUN_ID,
        session_id=STAGE30_9_1_SCENARIO_SESSION_ID,
        artifact_created_at_utc=STAGE30_9_1_SCENARIO_CREATED_AT_UTC,
        capture_records=_default_capture_records(),
        dispatch_context_records=_default_dispatch_context_records(),
        session_summary_counters=Stage30_9SessionSummaryCounters(
            pings_emitted=3,
            dispatch_attempts=3,
            dedupe_suppressed=2,
            errors=1,
        ),
        expected_ping_count=STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT,
        expected_retained=STAGE30_9_1_DEFAULT_EXPECTED_RETAINED,
        expected_duplicate_suppressed=(
            STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED
        ),
        expected_invalid_suppressed=(
            STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED
        ),
    )


def mismatch_bridge_scenario() -> Stage30_9BridgeScenario:
    """Build and return the deterministic mismatch bridge scenario.

    The default three sends plus a fourth send whose dispatch context
    records a session scope (``ping_session_id``) that does NOT match the
    bundle (config) session id, so the post-run Stage 30.8.3 index
    suppresses that ping (``SESSION_ID_MISMATCH``). Expected post-run index:
    2 retained, 1 duplicate-suppressed, 1 invalid-suppressed. Pure / total.
    """
    captures = _default_capture_records() + (
        Stage30_9CaptureRecord(
            capture_index=3,
            webhook_identity=PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload_body_text=_scenario_body(STAGE30_9_1_SCENARIO_PING_4_ID),
            payload_keys=("content",),
            sanitized_transport_status=(
                STAGE30_9_1_SCENARIO_STATUS_SENT_OK
            ),
        ),
    )
    contexts = _default_dispatch_context_records() + (
        Stage30_9DispatchContextRecord(
            capture_index=3,
            dedupe_key=STAGE30_9_1_SCENARIO_DEDUPE_KEY_3,
            candidate_id=STAGE30_9_1_SCENARIO_CANDIDATE_3_ID,
            ping_id=STAGE30_9_1_SCENARIO_PING_4_ID,
            token_mint=STAGE30_9_1_SCENARIO_MINT_3,
            ping_session_id=STAGE30_9_1_SCENARIO_MISMATCH_SESSION_ID,
        ),
    )
    return Stage30_9BridgeScenario(
        name=STAGE30_9_1_MISMATCH_SCENARIO_NAME,
        run_id=STAGE30_9_1_SCENARIO_RUN_ID,
        session_id=STAGE30_9_1_SCENARIO_SESSION_ID,
        artifact_created_at_utc=STAGE30_9_1_SCENARIO_CREATED_AT_UTC,
        capture_records=captures,
        dispatch_context_records=contexts,
        session_summary_counters=None,
        expected_ping_count=STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT,
        expected_retained=STAGE30_9_1_MISMATCH_EXPECTED_RETAINED,
        expected_duplicate_suppressed=(
            STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED
        ),
        expected_invalid_suppressed=(
            STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED
        ),
    )


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def capture_record_field_names() -> Tuple[str, ...]:
    """Return the capture record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9CaptureRecord))


def dispatch_context_record_field_names() -> Tuple[str, ...]:
    """Return the dispatch context record field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_9DispatchContextRecord)
    )


def projector_result_field_names() -> Tuple[str, ...]:
    """Return the projector result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9ProjectorResult))


def bridge_scenario_field_names() -> Tuple[str, ...]:
    """Return the bridge scenario field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9BridgeScenario))


def bridge_proof_summary_field_names() -> Tuple[str, ...]:
    """Return the bridge proof summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9BridgeProofSummary))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_9_1_MINOR_VERSION",
    "STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION",
    # Bridge status.
    "BRIDGE_STATUS_CAPTURED",
    "BRIDGE_STATUS_PROJECTED",
    "BRIDGE_STATUS_WRITTEN_AND_INDEXED",
    "BRIDGE_STATUS_INVALID_INPUT",
    "BRIDGE_STATUS_PROJECT_FAILED",
    "BRIDGE_STATUS_WRITE_FAILED",
    "BRIDGE_STATUS_READ_FAILED",
    "BRIDGE_STATUS_INDEX_FAILED",
    "STAGE30_9_1_BRIDGE_STATUS_VALUES",
    "is_bridge_status",
    # Bridge reason.
    "BRIDGE_REASON_NONE",
    "BRIDGE_REASON_MISSING_RUN_ID",
    "BRIDGE_REASON_MISSING_SESSION_ID",
    "BRIDGE_REASON_MISSING_PING_ID",
    "BRIDGE_REASON_MISSING_CANDIDATE_ID",
    "BRIDGE_REASON_MISSING_TOKEN_MINT",
    "BRIDGE_REASON_MISSING_DEDUPE_KEY",
    "BRIDGE_REASON_MISSING_COMPACT_BODY",
    "BRIDGE_REASON_MISSING_CAPTURE_INDEX",
    "BRIDGE_REASON_COUNT_MISMATCH",
    "BRIDGE_REASON_AMBIGUOUS_JOIN",
    "BRIDGE_REASON_NON_PRIVATE_WEBHOOK",
    "BRIDGE_REASON_WRITER_REJECTED",
    "BRIDGE_REASON_READER_REJECTED",
    "BRIDGE_REASON_INDEX_REJECTED",
    "STAGE30_9_1_BRIDGE_REASON_VALUES",
    "is_bridge_reason",
    # Private webhook identity allowlist.
    "PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
    "STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES",
    "is_private_webhook_identity",
    # Sanitized transport status (closed set).
    "SANITIZED_TRANSPORT_STATUS_SENT_OK",
    "SANITIZED_TRANSPORT_STATUS_RATE_LIMITED",
    "SANITIZED_TRANSPORT_STATUS_SERVER_ERROR",
    "SANITIZED_TRANSPORT_STATUS_NETWORK_ERROR",
    "SANITIZED_TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED",
    "SANITIZED_TRANSPORT_STATUS_VALIDATION_FAILED",
    "SANITIZED_TRANSPORT_STATUS_PAYLOAD_REFUSED",
    "SANITIZED_TRANSPORT_STATUS_UNKNOWN",
    "STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES",
    "is_sanitized_transport_status",
    "normalize_transport_status",
    # Records.
    "Stage30_9CaptureRecord",
    "Stage30_9CaptureBatchSummary",
    "Stage30_9DispatchContextRecord",
    "Stage30_9SessionSummaryCounters",
    "Stage30_9ProjectorResult",
    "Stage30_9BridgeScenario",
    "Stage30_9BridgeProofSummary",
    # Deterministic fake scenario building blocks + builders.
    "STAGE30_9_1_DEFAULT_SCENARIO_NAME",
    "STAGE30_9_1_MISMATCH_SCENARIO_NAME",
    "STAGE30_9_1_SCENARIO_RUN_ID",
    "STAGE30_9_1_SCENARIO_SESSION_ID",
    "STAGE30_9_1_SCENARIO_CREATED_AT_UTC",
    "STAGE30_9_1_SCENARIO_MISMATCH_SESSION_ID",
    "STAGE30_9_1_SCENARIO_DEDUPE_KEY_1",
    "STAGE30_9_1_SCENARIO_DEDUPE_KEY_2",
    "STAGE30_9_1_SCENARIO_DEDUPE_KEY_3",
    "STAGE30_9_1_SCENARIO_PING_1_ID",
    "STAGE30_9_1_SCENARIO_PING_2_ID",
    "STAGE30_9_1_SCENARIO_PING_3_ID",
    "STAGE30_9_1_SCENARIO_PING_4_ID",
    "STAGE30_9_1_SCENARIO_CANDIDATE_1_ID",
    "STAGE30_9_1_SCENARIO_CANDIDATE_2_ID",
    "STAGE30_9_1_SCENARIO_CANDIDATE_3_ID",
    "STAGE30_9_1_SCENARIO_MINT_1",
    "STAGE30_9_1_SCENARIO_MINT_2",
    "STAGE30_9_1_SCENARIO_MINT_3",
    "STAGE30_9_1_SCENARIO_COMPACT_BODY_PREFIX",
    "STAGE30_9_1_SCENARIO_STATUS_SENT_OK",
    "STAGE30_9_1_SCENARIO_STATUS_RATE_LIMITED",
    "STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT",
    "STAGE30_9_1_DEFAULT_EXPECTED_RETAINED",
    "STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED",
    "STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED",
    "STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT",
    "STAGE30_9_1_MISMATCH_EXPECTED_RETAINED",
    "STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED",
    "STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED",
    "default_bridge_scenario",
    "mismatch_bridge_scenario",
    # Field-name helpers.
    "capture_record_field_names",
    "dispatch_context_record_field_names",
    "projector_result_field_names",
    "bridge_scenario_field_names",
    "bridge_proof_summary_field_names",
)
