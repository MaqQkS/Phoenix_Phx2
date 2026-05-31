"""Stage 30.8.4 controlled compact session artifact proof models.

Stage 30.8.4 is the FINAL planned Stage 30.8 substage: a controlled,
fake / offline proof that the Stage 30.8 storage chain already built
(Stage 30.8.1 models / validators -> Stage 30.8.2 temp-dir writer ->
Stage 30.8.3 manifest-backed reader + session index / dedupe builder)
COMPOSES correctly end-to-end. It is NOT a runtime integration, NOT a
live provider run, NOT a Discord send, NOT a real bot storage proof, and
NOT a new dedupe implementation (dedupe / index already landed in Stage
30.8.3). It is an offline proof that the pieces compose.

This module is the model layer: passive frozen records + closed-set
status / reason tokens + the deterministic fake proof scenario. It
implements NO runner (that is ``stage30_8_controlled_artifact_proof``);
it reads no filesystem, opens no database, reaches no network, reads no
environment, and constructs no artifact bundle (the runner does that).

Records:

  * ``Stage30_8_4ProofPingSpec``                  -- one fake compact ping
    in the proof scenario (pure input description; no artifact yet).
  * ``Stage30_8_4ProofScenario``                  -- the deterministic
    fake scenario (its ping specs + the author-verified expected counts).
  * ``Stage30_8_4ControlledArtifactProofSummary`` -- the passive proof
    verdict (status / reason / counts / flags / safety invariants).

The default scenario (``default_proof_scenario``) proves meaningful
behaviour with two fake sessions and six fake pings:

  * Session A: ping A1 (dedupe K1), ping A2 (dedupe K2), duplicate ping
    A3 (dedupe K1, same session).
  * Session B: ping B1 (dedupe K3), cross-session duplicate ping B2
    (dedupe K2), and a mismatched ping B3 whose OWN ``session_id`` does
    NOT equal its bundle session id (a valid artifact the Stage 30.8.2
    writer accepts, that the Stage 30.8.3 index then suppresses as
    ``INVALID_SUPPRESSED`` / ``SESSION_ID_MISMATCH``).

So the scenario proves, through the real pieces and WITHOUT weakening the
writer: 3 retained (A1 / A2 / B1), 2 duplicate-suppressed (A3 same
session, B2 cross session), 1 invalid-suppressed (B3 mismatch). The
duplicate pings carry DIFFERENT ``ping_id`` values but the SAME
``dedupe_key`` as their first occurrence, so the proof shows dedupe is
driven by ``dedupe_key`` (spec Section 9), never by ``ping_id``.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.8.1 / 30.8.3 models
    modules); the runner sibling owns every PHX2 composition import.
  * No filesystem / env / network / database / compression access. No
    ``open`` / ``pathlib`` / ``os`` / ``json`` / ``sqlite3``. No top-level
    Call (no implicit I/O at import time; the ``@dataclass(frozen=True)``
    decorators are decorator-list Calls, not body-statement Calls -- the
    default scenario is built by ``default_proof_scenario`` at call time,
    never as a module-level constructed constant).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + proof schema identity
# ---------------------------------------------------------------------------


STAGE30_8_4_MINOR_VERSION: str = "30.8.4"


# The Stage 30.8.4 proof summary schema version. Distinct from the
# per-artifact schema version (``stage30_8_v0_compact_artifact``), the
# bundle envelope schema version (``stage30_8_v0_compact_session_bundle``),
# and the session-index schema version
# (``stage30_8_v0_compact_session_index``): this names the offline
# controlled-proof summary shape.
STAGE30_8_4_PROOF_SCHEMA_VERSION: str = (
    "stage30_8_v0_compact_session_proof"
)


# ---------------------------------------------------------------------------
# Proof status (closed set)
# ---------------------------------------------------------------------------


PROOF_STATUS_PROVED: str = "PROVED"
PROOF_STATUS_FAILED: str = "FAILED"


STAGE30_8_4_PROOF_STATUS_VALUES: Tuple[str, ...] = (
    PROOF_STATUS_PROVED,
    PROOF_STATUS_FAILED,
)


def is_proof_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set proof status."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_4_PROOF_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Proof reason (closed set; proof-runner-owned)
# ---------------------------------------------------------------------------
#
# ``OK`` accompanies a ``PROVED`` summary; every other token accompanies a
# fail-closed ``FAILED`` summary. The runner fails closed on the FIRST
# failing step (a bad scenario / output dir, a writer / reader / index
# failure, an unexpected count, or a violated safety invariant).


PROOF_REASON_OK: str = "OK"
PROOF_REASON_INVALID_OUTPUT_DIR: str = "INVALID_OUTPUT_DIR"
PROOF_REASON_INVALID_SCENARIO: str = "INVALID_SCENARIO"
PROOF_REASON_WRITE_FAILED: str = "WRITE_FAILED"
PROOF_REASON_READ_FAILED: str = "READ_FAILED"
PROOF_REASON_INDEX_FAILED: str = "INDEX_FAILED"
PROOF_REASON_COUNT_MISMATCH: str = "COUNT_MISMATCH"
PROOF_REASON_INVARIANT_FAILED: str = "INVARIANT_FAILED"


STAGE30_8_4_PROOF_REASONS: Tuple[str, ...] = (
    PROOF_REASON_OK,
    PROOF_REASON_INVALID_OUTPUT_DIR,
    PROOF_REASON_INVALID_SCENARIO,
    PROOF_REASON_WRITE_FAILED,
    PROOF_REASON_READ_FAILED,
    PROOF_REASON_INDEX_FAILED,
    PROOF_REASON_COUNT_MISMATCH,
    PROOF_REASON_INVARIANT_FAILED,
)


def is_proof_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set proof reason."""
    return (
        isinstance(value, str)
        and value in STAGE30_8_4_PROOF_REASONS
    )


# ---------------------------------------------------------------------------
# Default fake scenario building blocks (plain literal constants)
# ---------------------------------------------------------------------------
#
# Every value below is a plain string / int literal (no Call), so this
# module carries no top-level Call. ``default_proof_scenario`` assembles
# them into the scenario record at call time. The session ids are safe
# single path components (the Stage 30.8.2 writer uses them as the
# per-session subdirectory name); the dedupe keys / ping ids / body text
# are safe opaque strings carrying none of the forbidden secret / URL /
# transport needles. The created-at timestamp is a FIXED ISO-8601 UTC
# constant (the proof never reads the wall clock).


STAGE30_8_4_DEFAULT_SCENARIO_NAME: str = (
    "stage30_8_4_default_dedupe_mismatch"
)


STAGE30_8_4_PROOF_RUN_ID: str = "stage30-8-4-proof-run"
STAGE30_8_4_PROOF_CREATED_AT_UTC: str = "2026-01-01T00:00:00Z"


# The two bundle (manifest) session ids -- also the per-session subdir
# names the writer creates under the caller-provided output dir.
STAGE30_8_4_PROOF_SESSION_A_ID: str = "stage30-8-4-proof-session-a"
STAGE30_8_4_PROOF_SESSION_B_ID: str = "stage30-8-4-proof-session-b"


# A ping's OWN claimed session id that deliberately does NOT match its
# bundle session id (drives the SESSION_ID_MISMATCH invalid case through
# the writer without weakening writer validation).
STAGE30_8_4_PROOF_MISMATCH_SESSION_ID: str = (
    "stage30-8-4-proof-session-x"
)


# The fake dedupe keys. K1 repeats within session A (same-session
# duplicate); K2 repeats across sessions A -> B (cross-session duplicate);
# K3 is unique; K4 belongs to the mismatched ping (never retained).
STAGE30_8_4_PROOF_DEDUPE_KEY_1: str = "stage30-8-4-proof-dedupe-k1"
STAGE30_8_4_PROOF_DEDUPE_KEY_2: str = "stage30-8-4-proof-dedupe-k2"
STAGE30_8_4_PROOF_DEDUPE_KEY_3: str = "stage30-8-4-proof-dedupe-k3"
STAGE30_8_4_PROOF_DEDUPE_KEY_4: str = "stage30-8-4-proof-dedupe-k4"


# The six fake ping ids (each unique; the duplicate pings carry a
# DIFFERENT ping id from their first occurrence but the SAME dedupe key, so
# the proof shows dedupe is driven by dedupe_key, never ping_id).
STAGE30_8_4_PROOF_PING_A1_ID: str = "stage30-8-4-proof-ping-a1"
STAGE30_8_4_PROOF_PING_A2_ID: str = "stage30-8-4-proof-ping-a2"
STAGE30_8_4_PROOF_PING_A3_ID: str = "stage30-8-4-proof-ping-a3"
STAGE30_8_4_PROOF_PING_B1_ID: str = "stage30-8-4-proof-ping-b1"
STAGE30_8_4_PROOF_PING_B2_ID: str = "stage30-8-4-proof-ping-b2"
STAGE30_8_4_PROOF_PING_B3_ID: str = "stage30-8-4-proof-ping-b3"


# The safe compact body prefix; the scenario appends the ping id.
STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX: str = (
    "stage30-8-4 proof compact body "
)


# The author-verified expected counts for the default scenario. The runner
# cross-checks the live Stage 30.8.3 index against these (a mismatch fails
# the proof closed with ``COUNT_MISMATCH``); it never recomputes the dedupe
# verdict, so these constants are the proof oracle, not a reimplementation.
STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN: int = 2
STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN: int = 6
STAGE30_8_4_EXPECTED_RETAINED: int = 3
STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED: int = 2
STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED: int = 1


# ---------------------------------------------------------------------------
# Immutable record: proof ping spec (pure scenario input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8_4ProofPingSpec:
    """Immutable description of ONE fake compact ping in the proof
    scenario (a pure input record; it is NOT an artifact).

      * ``bundle_session_id``    -- the bundle (manifest) session id this
                                    ping is written into; also the
                                    per-session subdir name.
      * ``identity_session_id``  -- the ping's OWN claimed session id. When
                                    it differs from ``bundle_session_id``
                                    the Stage 30.8.3 index suppresses the
                                    ping (SESSION_ID_MISMATCH); the Stage
                                    30.8.2 writer still accepts it (the
                                    writer does not cross-check the two).
      * ``ping_id``              -- the unique ping id (provenance / a
                                    dedupe tiebreak only, never identity).
      * ``dedupe_key``           -- the dedupe identity (spec Section 9):
                                    the ONLY axis dedupe is driven by.
      * ``body_text``            -- the safe, non-empty compact body text.
    """

    bundle_session_id: str
    identity_session_id: str
    ping_id: str
    dedupe_key: str
    body_text: str


# ---------------------------------------------------------------------------
# Immutable record: proof scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8_4ProofScenario:
    """Immutable, deterministic fake proof scenario.

    Carries the ordered ping specs plus the author-verified expected
    aggregate counts the runner cross-checks the live index against. A
    passive carrier; it performs no I/O and constructs no artifact.

      * ``name``                          -- the scenario name.
      * ``pings``                         -- the ordered ping specs (the
                                             tuple order fixes the
                                             per-bundle write / filename
                                             order).
      * ``expected_sessions_written``     -- expected distinct bundles.
      * ``expected_ping_artifacts_seen``  -- expected ping members read.
      * ``expected_retained``             -- expected unique retained pings.
      * ``expected_duplicate_suppressed`` -- expected duplicate-suppressed.
      * ``expected_invalid_suppressed``   -- expected identity-less /
                                             mismatched suppressed pings.
    """

    name: str
    pings: Tuple[Stage30_8_4ProofPingSpec, ...]
    expected_sessions_written: int
    expected_ping_artifacts_seen: int
    expected_retained: int
    expected_duplicate_suppressed: int
    expected_invalid_suppressed: int


def default_proof_scenario() -> Stage30_8_4ProofScenario:
    """Build and return the deterministic default proof scenario.

    Two fake sessions, six fake pings (see the module docstring). Pure /
    total; takes no argument, reads nothing, and returns the same value on
    every call (no clock, no randomness, no filesystem). The dataclass is
    constructed HERE (inside a function), never as a module-level constant,
    so the module carries no top-level Call.
    """
    pings = (
        # Session A.
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            identity_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            ping_id=STAGE30_8_4_PROOF_PING_A1_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_1,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_A1_ID
            ),
        ),
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            identity_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            ping_id=STAGE30_8_4_PROOF_PING_A2_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_2,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_A2_ID
            ),
        ),
        # A3 repeats K1 within session A -> same-session duplicate.
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            identity_session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            ping_id=STAGE30_8_4_PROOF_PING_A3_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_1,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_A3_ID
            ),
        ),
        # Session B.
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            identity_session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            ping_id=STAGE30_8_4_PROOF_PING_B1_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_3,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_B1_ID
            ),
        ),
        # B2 repeats K2 (first seen in session A) -> cross-session
        # duplicate.
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            identity_session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            ping_id=STAGE30_8_4_PROOF_PING_B2_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_2,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_B2_ID
            ),
        ),
        # B3 claims a session id that does NOT match its bundle -> the
        # writer accepts it; the index suppresses it (SESSION_ID_MISMATCH).
        Stage30_8_4ProofPingSpec(
            bundle_session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            identity_session_id=STAGE30_8_4_PROOF_MISMATCH_SESSION_ID,
            ping_id=STAGE30_8_4_PROOF_PING_B3_ID,
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_4,
            body_text=(
                STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX
                + STAGE30_8_4_PROOF_PING_B3_ID
            ),
        ),
    )
    return Stage30_8_4ProofScenario(
        name=STAGE30_8_4_DEFAULT_SCENARIO_NAME,
        pings=pings,
        expected_sessions_written=STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN,
        expected_ping_artifacts_seen=(
            STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN
        ),
        expected_retained=STAGE30_8_4_EXPECTED_RETAINED,
        expected_duplicate_suppressed=(
            STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED
        ),
        expected_invalid_suppressed=(
            STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED
        ),
    )


# ---------------------------------------------------------------------------
# Immutable record: controlled artifact proof summary (passive verdict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8_4ControlledArtifactProofSummary:
    """Immutable Stage 30.8.4 controlled artifact proof summary.

    A passive verdict record. It records counts + capability flags +
    safety invariants and carries NO secret, NO raw provider payload, and
    NO absolute path (only the relative, safe scenario session ids). The
    same input yields the same summary on every run, in any temp dir.

      * ``status``                    -- ``PROVED`` / ``FAILED``.
      * ``reason``                    -- a closed-set ``PROOF_REASON_*``
                                         token.
      * ``proof_schema_version``      -- the Stage 30.8.4 proof schema id.
      * ``scenario_name``             -- the proof scenario name.
      * ``sessions_written_count``    -- bundles the writer persisted.
      * ``sessions_read_count``       -- bundles the reader read back.
      * ``ping_artifacts_seen``       -- ping members the reader returned.
      * ``retained_ping_count``       -- unique retained pings (index).
      * ``duplicate_suppressed_count``-- duplicate-suppressed pings (index).
      * ``invalid_suppressed_count``  -- identity-less / mismatched
                                         suppressed pings (index).
      * ``read_failure_count``        -- bundles that failed to read.
      * ``proof_session_ids``         -- the relative scenario session ids
                                         (safe; never an absolute path).
      * ``writer_used`` / ``reader_used`` / ``index_builder_used``
                                      -- which composed Stage 30.8.x pieces
                                         the run actually invoked.
      * ``live_provider_used`` / ``discord_send_used`` / ``env_read_used``
        / ``db_used`` / ``zstd_used`` / ``runtime_integration_used``
                                      -- forbidden-surface flags; ALWAYS
                                         ``False`` (the proof structurally
                                         cannot reach them).
      * ``manifest_backed_reads``     -- the reads went through the Stage
                                         30.8.3 manifest-backed reader.
      * ``dedupe_key_only``           -- every retained ping resolved its
                                         dedupe identity from ``dedupe_key``
                                         (spec Section 9), never ``ping_id``.
      * ``no_default_storage_root``   -- only the caller-provided output dir
                                         was used; ALWAYS ``True``.
      * ``no_runtime_integration``    -- no runtime / orchestrator path was
                                         touched; ALWAYS ``True``.
    """

    status: str
    reason: str
    proof_schema_version: str
    scenario_name: str
    sessions_written_count: int
    sessions_read_count: int
    ping_artifacts_seen: int
    retained_ping_count: int
    duplicate_suppressed_count: int
    invalid_suppressed_count: int
    read_failure_count: int
    proof_session_ids: Tuple[str, ...]
    writer_used: bool
    reader_used: bool
    index_builder_used: bool
    live_provider_used: bool
    discord_send_used: bool
    env_read_used: bool
    db_used: bool
    zstd_used: bool
    runtime_integration_used: bool
    manifest_backed_reads: bool
    dedupe_key_only: bool
    no_default_storage_root: bool
    no_runtime_integration: bool


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def proof_ping_spec_field_names() -> Tuple[str, ...]:
    """Return the proof ping spec field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8_4ProofPingSpec))


def proof_scenario_field_names() -> Tuple[str, ...]:
    """Return the proof scenario field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_8_4ProofScenario))


def proof_summary_field_names() -> Tuple[str, ...]:
    """Return the proof summary field names as a tuple."""
    return tuple(
        f.name
        for f in fields(Stage30_8_4ControlledArtifactProofSummary)
    )


__all__ = (
    # Minor version + proof schema identity.
    "STAGE30_8_4_MINOR_VERSION",
    "STAGE30_8_4_PROOF_SCHEMA_VERSION",
    # Proof status.
    "PROOF_STATUS_PROVED",
    "PROOF_STATUS_FAILED",
    "STAGE30_8_4_PROOF_STATUS_VALUES",
    "is_proof_status",
    # Proof reason.
    "PROOF_REASON_OK",
    "PROOF_REASON_INVALID_OUTPUT_DIR",
    "PROOF_REASON_INVALID_SCENARIO",
    "PROOF_REASON_WRITE_FAILED",
    "PROOF_REASON_READ_FAILED",
    "PROOF_REASON_INDEX_FAILED",
    "PROOF_REASON_COUNT_MISMATCH",
    "PROOF_REASON_INVARIANT_FAILED",
    "STAGE30_8_4_PROOF_REASONS",
    "is_proof_reason",
    # Default scenario building blocks.
    "STAGE30_8_4_DEFAULT_SCENARIO_NAME",
    "STAGE30_8_4_PROOF_RUN_ID",
    "STAGE30_8_4_PROOF_CREATED_AT_UTC",
    "STAGE30_8_4_PROOF_SESSION_A_ID",
    "STAGE30_8_4_PROOF_SESSION_B_ID",
    "STAGE30_8_4_PROOF_MISMATCH_SESSION_ID",
    "STAGE30_8_4_PROOF_DEDUPE_KEY_1",
    "STAGE30_8_4_PROOF_DEDUPE_KEY_2",
    "STAGE30_8_4_PROOF_DEDUPE_KEY_3",
    "STAGE30_8_4_PROOF_DEDUPE_KEY_4",
    "STAGE30_8_4_PROOF_PING_A1_ID",
    "STAGE30_8_4_PROOF_PING_A2_ID",
    "STAGE30_8_4_PROOF_PING_A3_ID",
    "STAGE30_8_4_PROOF_PING_B1_ID",
    "STAGE30_8_4_PROOF_PING_B2_ID",
    "STAGE30_8_4_PROOF_PING_B3_ID",
    "STAGE30_8_4_PROOF_COMPACT_BODY_PREFIX",
    "STAGE30_8_4_EXPECTED_SESSIONS_WRITTEN",
    "STAGE30_8_4_EXPECTED_PING_ARTIFACTS_SEEN",
    "STAGE30_8_4_EXPECTED_RETAINED",
    "STAGE30_8_4_EXPECTED_DUPLICATE_SUPPRESSED",
    "STAGE30_8_4_EXPECTED_INVALID_SUPPRESSED",
    # Records + scenario builder.
    "Stage30_8_4ProofPingSpec",
    "Stage30_8_4ProofScenario",
    "Stage30_8_4ControlledArtifactProofSummary",
    "default_proof_scenario",
    # Field-name helpers.
    "proof_ping_spec_field_names",
    "proof_scenario_field_names",
    "proof_summary_field_names",
)
