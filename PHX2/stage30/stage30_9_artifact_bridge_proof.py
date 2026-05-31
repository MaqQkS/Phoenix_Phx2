"""Stage 30.9.1 offline compact artifact bridge proof helper.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.9.1
artifact bridge composes end-to-end using fakes / offline temp dirs:

    Stage 30.9.1 capture records + dispatch-ledger context
      -> Stage 30.9.1 post-session projector  (ONE Stage 30.8 bundle)
      -> Stage 30.8.2 temp-dir writer          (ONE bundle write only)
      -> Stage 30.8.3 manifest-backed reader
      -> Stage 30.8.3 session index / dedupe builder
      -> Stage 30.9.1 bridge proof summary

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT
a new readiness gate, and NOT a new dedupe implementation. It CONSTRUCTS
no filesystem I/O of its own: every write goes through the Stage 30.8.2
writer and every read through the Stage 30.8.3 reader / builder, so the
proof exercises the real pieces rather than reimplementing them. It writes
EXACTLY ONE Stage 30.8 bundle (post-session); it NEVER writes per ping.

What the helper does (``run_stage30_9_1_artifact_bridge_proof``):

  1. Take an EXPLICIT, caller-provided ``output_dir`` (a temporary /
     out-of-repo directory in the tests). The helper never infers a
     storage root, reads no environment, and uses no default path; it
     hands ``output_dir`` straight to the Stage 30.8.2 writer (which fails
     closed on a non-explicit dir).
  2. Resolve the scenario (the deterministic default when ``None``).
  3. PROJECT the scenario's capture records + dispatch context into ONE
     Stage 30.8 bundle (the projector carries the dedupe key from the
     dispatch context; it never recomputes one).
  4. WRITE the single bundle with the Stage 30.8.2 writer.
  5. READ the written bundle back with the Stage 30.8.3 reader.
  6. INDEX the written bundle with the Stage 30.8.3 builder for the
     post-session retained / duplicate / invalid proof.
  7. Return a passive ``Stage30_9BridgeProofSummary``.

Fail-closed: a projector failure surfaces the projector's status / reason
(``INVALID_INPUT`` / ``PROJECT_FAILED``); a writer / reader / index failure
-> ``WRITE_FAILED`` / ``READ_FAILED`` / ``INDEX_FAILED`` (with
``WRITER_REJECTED`` / ``READER_REJECTED`` / ``INDEX_REJECTED``). An invalid
``output_dir`` fails closed through the writer (``WRITE_FAILED``). The
helper NEVER raises.

Discipline:

  * Stdlib only (``typing``); the JSON / pathlib I/O all lives behind the
    composed Stage 30.8.2 writer + Stage 30.8.3 reader / builder.
  * PHX2 imports: the Stage 30.9.1 bridge-models + projector siblings +
    the Stage 30.8.1 artifact-models (for the ping kind) + the Stage 30.8.2
    writer + the Stage 30.8.3 reader / index-builder / index-models
    siblings. It imports NO Stage 28 module, NO Stage 21-29 / runtime /
    orchestrator / renderer / Discord / provider module.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_REASON_INDEX_REJECTED,
    BRIDGE_REASON_NONE,
    BRIDGE_REASON_READER_REJECTED,
    BRIDGE_REASON_WRITER_REJECTED,
    BRIDGE_STATUS_INDEX_FAILED,
    BRIDGE_STATUS_PROJECT_FAILED,
    BRIDGE_STATUS_PROJECTED,
    BRIDGE_STATUS_READ_FAILED,
    BRIDGE_STATUS_WRITE_FAILED,
    BRIDGE_STATUS_WRITTEN_AND_INDEXED,
    STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
    Stage30_9BridgeProofSummary,
    default_bridge_scenario,
)
from PHX2.stage30.stage30_9_artifact_projector import (
    project_compact_session_artifact_bundle,
)
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    WRITE_STATUS_WRITTEN,
    write_compact_session_artifact_bundle,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    BUNDLE_READ_STATUS_READ,
    read_compact_session_bundle,
)
from PHX2.stage30.stage30_8_session_index_builder import (
    build_compact_session_index,
)
from PHX2.stage30.stage30_8_session_index_models import (
    DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
    INDEX_BUILD_STATUS_BUILT,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _opt_str(value: object) -> Optional[str]:
    """Return ``value`` when it is a non-empty string, else ``None``."""
    return value if isinstance(value, str) and value != "" else None


def _summary(
    *,
    status: str,
    reason: str,
    scenario_name: str,
    proof_session_id: Optional[str],
    capture_record_count: int = 0,
    ping_artifacts_projected: int = 0,
    dispatch_attempts_projected: int = 0,
    error_artifacts_projected: int = 0,
    bundles_written_count: int = 0,
    bundles_read_count: int = 0,
    ping_artifacts_seen: int = 0,
    retained_count: int = 0,
    duplicate_suppressed_count: int = 0,
    invalid_suppressed_count: int = 0,
    capture_transport_used: bool = False,
    projector_used: bool = False,
    writer_used: bool = False,
    reader_used: bool = False,
    index_builder_used: bool = False,
    dedupe_key_from_dispatch_context: bool = False,
) -> Stage30_9BridgeProofSummary:
    """Assemble a bridge proof summary. The forbidden-surface flags are
    ALWAYS ``False`` and the single-bundle-write / no-default-storage-root
    invariants ALWAYS ``True`` (the proof structurally cannot reach those
    surfaces and writes exactly one bundle). Pure.
    """
    return Stage30_9BridgeProofSummary(
        status=status,
        reason=reason,
        bridge_proof_schema_version=STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
        scenario_name=scenario_name,
        proof_session_id=proof_session_id,
        capture_record_count=capture_record_count,
        ping_artifacts_projected=ping_artifacts_projected,
        dispatch_attempts_projected=dispatch_attempts_projected,
        error_artifacts_projected=error_artifacts_projected,
        bundles_written_count=bundles_written_count,
        bundles_read_count=bundles_read_count,
        ping_artifacts_seen=ping_artifacts_seen,
        retained_count=retained_count,
        duplicate_suppressed_count=duplicate_suppressed_count,
        invalid_suppressed_count=invalid_suppressed_count,
        capture_transport_used=capture_transport_used,
        projector_used=projector_used,
        writer_used=writer_used,
        reader_used=reader_used,
        index_builder_used=index_builder_used,
        live_provider_used=False,
        discord_send_used=False,
        env_read_used=False,
        db_used=False,
        zstd_used=False,
        single_bundle_write=True,
        no_default_storage_root=True,
        dedupe_key_from_dispatch_context=(
            dedupe_key_from_dispatch_context
        ),
    )


def _sequence_len(value: object) -> int:
    """Return ``len(value)`` when it is a tuple / list, else 0. Pure."""
    if isinstance(value, (tuple, list)):
        return len(value)
    return 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_stage30_9_1_artifact_bridge_proof(
    output_dir: object,
    scenario: object = None,
) -> Stage30_9BridgeProofSummary:
    """Run the offline compact artifact bridge proof into a caller-provided
    ``output_dir`` (a temporary / out-of-repo directory).

    With ``scenario=None`` the deterministic default bridge scenario is
    used. The proof projects -> writes ONE bundle -> reads -> indexes
    through the real Stage 30.9.1 projector + Stage 30.8.2 / 30.8.3 pieces
    and returns a passive ``Stage30_9BridgeProofSummary``
    (``WRITTEN_AND_INDEXED`` on success; a fail-closed status otherwise).
    Pure relative to the caller-provided dir; reads no clock, no env, no
    random; never raises.
    """
    try:
        return _run_bridge_proof(output_dir, scenario)
    except Exception:  # pragma: no cover - total fail-closed backstop
        return _summary(
            status=BRIDGE_STATUS_PROJECT_FAILED,
            reason=BRIDGE_REASON_NONE,
            scenario_name="",
            proof_session_id=None,
        )


def _run_bridge_proof(
    output_dir: object, scenario: object
) -> Stage30_9BridgeProofSummary:
    """Bridge proof body (see ``run_stage30_9_1_artifact_bridge_proof``)."""
    if scenario is None:
        scenario = default_bridge_scenario()

    scenario_name = _opt_str(getattr(scenario, "name", None)) or ""
    proof_session_id = _opt_str(getattr(scenario, "session_id", None))
    captures = getattr(scenario, "capture_records", None)
    contexts = getattr(scenario, "dispatch_context_records", None)
    capture_count = _sequence_len(captures)

    # 1. Project the capture records + dispatch context into ONE bundle.
    projection = project_compact_session_artifact_bundle(
        run_id=getattr(scenario, "run_id", None),
        session_id=getattr(scenario, "session_id", None),
        artifact_created_at_utc=getattr(
            scenario, "artifact_created_at_utc", None
        ),
        capture_records=captures,
        dispatch_context_records=contexts,
        session_summary_counters=getattr(
            scenario, "session_summary_counters", None
        ),
    )
    if projection.status != BRIDGE_STATUS_PROJECTED:
        # Surface the projector's fail-closed status / reason verbatim
        # (INVALID_INPUT / PROJECT_FAILED).
        return _summary(
            status=projection.status,
            reason=projection.reason,
            scenario_name=scenario_name,
            proof_session_id=proof_session_id,
            capture_record_count=capture_count,
            projector_used=True,
        )

    ping_projected = projection.ping_artifact_count
    dispatch_projected = projection.dispatch_attempt_count
    error_projected = projection.error_artifact_count

    # 2. Write the single bundle through the Stage 30.8.2 writer.
    write_result = write_compact_session_artifact_bundle(
        output_dir, projection.bundle
    )
    if write_result.status != WRITE_STATUS_WRITTEN:
        return _summary(
            status=BRIDGE_STATUS_WRITE_FAILED,
            reason=BRIDGE_REASON_WRITER_REJECTED,
            scenario_name=scenario_name,
            proof_session_id=proof_session_id,
            capture_record_count=capture_count,
            ping_artifacts_projected=ping_projected,
            dispatch_attempts_projected=dispatch_projected,
            error_artifacts_projected=error_projected,
            projector_used=True,
            writer_used=True,
        )
    session_dir = write_result.session_dir

    # 3. Read the written bundle back through the Stage 30.8.3 reader.
    read_result = read_compact_session_bundle(session_dir)
    if read_result.status != BUNDLE_READ_STATUS_READ:
        return _summary(
            status=BRIDGE_STATUS_READ_FAILED,
            reason=BRIDGE_REASON_READER_REJECTED,
            scenario_name=scenario_name,
            proof_session_id=proof_session_id,
            capture_record_count=capture_count,
            ping_artifacts_projected=ping_projected,
            dispatch_attempts_projected=dispatch_projected,
            error_artifacts_projected=error_projected,
            bundles_written_count=1,
            projector_used=True,
            writer_used=True,
            reader_used=True,
        )
    ping_artifacts_seen = sum(
        1
        for member in read_result.members
        if member.member_kind == ARTIFACT_KIND_COMPACT_PING_ARTIFACT
    )

    # 4. Index the written bundle through the Stage 30.8.3 builder.
    index = build_compact_session_index(session_dirs=(session_dir,))
    if index.status != INDEX_BUILD_STATUS_BUILT:
        return _summary(
            status=BRIDGE_STATUS_INDEX_FAILED,
            reason=BRIDGE_REASON_INDEX_REJECTED,
            scenario_name=scenario_name,
            proof_session_id=proof_session_id,
            capture_record_count=capture_count,
            ping_artifacts_projected=ping_projected,
            dispatch_attempts_projected=dispatch_projected,
            error_artifacts_projected=error_projected,
            bundles_written_count=1,
            bundles_read_count=1,
            ping_artifacts_seen=ping_artifacts_seen,
            projector_used=True,
            writer_used=True,
            reader_used=True,
            index_builder_used=True,
        )

    # 5. Invariant: every retained ping resolved its dedupe identity from
    #    the dedupe_key carried from the dispatch context (never ping_id /
    #    none). Vacuously true when nothing is retained.
    dedupe_key_from_context = all(
        ping.identity_kind == DEDUPE_IDENTITY_KIND_DEDUPE_KEY
        for ping in index.retained_pings
    )

    # 6. WRITTEN_AND_INDEXED.
    return _summary(
        status=BRIDGE_STATUS_WRITTEN_AND_INDEXED,
        reason=BRIDGE_REASON_NONE,
        scenario_name=scenario_name,
        proof_session_id=proof_session_id,
        capture_record_count=capture_count,
        ping_artifacts_projected=ping_projected,
        dispatch_attempts_projected=dispatch_projected,
        error_artifacts_projected=error_projected,
        bundles_written_count=1,
        bundles_read_count=1,
        ping_artifacts_seen=ping_artifacts_seen,
        retained_count=index.retained_count,
        duplicate_suppressed_count=index.duplicate_suppressed_count,
        invalid_suppressed_count=index.invalid_suppressed_count,
        projector_used=True,
        writer_used=True,
        reader_used=True,
        index_builder_used=True,
        dedupe_key_from_dispatch_context=dedupe_key_from_context,
    )


__all__ = (
    "run_stage30_9_1_artifact_bridge_proof",
)
