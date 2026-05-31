"""Stage 30.8.4 controlled compact session artifact proof runner.

A pure, deterministic, fail-closed runner that PROVES the Stage 30.8
storage chain composes end-to-end using fake / offline compact artifacts:

    Stage 30.8.1 models / validators
      -> Stage 30.8.2 temp-dir artifact writer
      -> Stage 30.8.3 manifest-backed bundle reader
      -> Stage 30.8.3 session index / dedupe builder
      -> Stage 30.8.4 controlled proof summary

It is NOT a runtime integration, NOT a live provider run, NOT a Discord
send, NOT a real bot storage proof, and NOT a new dedupe implementation
(dedupe / index already landed in Stage 30.8.3). The runner CONSTRUCTS no
filesystem I/O of its own: every write goes through the Stage 30.8.2
writer and every read through the Stage 30.8.3 reader / builder, so the
proof exercises the real pieces rather than reimplementing them.

What the runner does (``run_stage30_8_4_controlled_artifact_proof``):

  1. Take an EXPLICIT, caller-provided ``output_dir`` (a temporary /
     out-of-repo directory in the tests). The runner never infers a
     storage root, reads no environment, and uses no default path; it
     hands ``output_dir`` straight to the Stage 30.8.2 writer (which
     fails closed on a non-explicit dir).
  2. Build the deterministic fake scenario bundles (in memory).
  3. WRITE each bundle with the Stage 30.8.2 writer.
  4. READ each written bundle back with the Stage 30.8.3 reader.
  5. INDEX the written bundles with the Stage 30.8.3 builder.
  6. Cross-check the live index counts against the scenario's
     author-verified expected counts (the proof oracle; the runner never
     recomputes the dedupe verdict).
  7. Verify the safety invariants (every retained ping keyed by
     ``dedupe_key``; retained dedupe identities unique).
  8. Return a passive ``Stage30_8_4ControlledArtifactProofSummary``.

Fail-closed: a bad scenario -> ``INVALID_SCENARIO``; a non-explicit
output dir -> ``INVALID_OUTPUT_DIR``; a writer / reader / index failure ->
``WRITE_FAILED`` / ``READ_FAILED`` / ``INDEX_FAILED``; an unexpected count
-> ``COUNT_MISMATCH``; a violated invariant -> ``INVARIANT_FAILED``. The
runner NEVER raises.

Discipline / non-goals:

  * stdlib only (``__future__`` / ``typing``); the JSON / pathlib I/O all
    lives behind the composed Stage 30.8.2 writer + Stage 30.8.3 reader /
    builder, so the runner needs NO ``json`` / ``pathlib``. It imports NO
    ``os`` (NO env read), NO ``sqlite3``, NO ``zstd`` / compression, NO
    network surface.
  * PHX2 imports: the Stage 30.8.4 proof-models sibling + the Stage 30.8.1
    artifact-models sibling + the Stage 30.8.2 writer + the Stage 30.8.3
    reader / index-builder / index-models siblings. NO Stage 21-29 / Stage
    29.5 import, NO runtime / orchestrator / renderer import, NO Discord /
    provider import.
  * the runner performs no direct filesystem primitive of its own and
    creates no proof-summary file: every write is delegated to the Stage
    30.8.2 writer and every read to the Stage 30.8.3 reader / builder, and
    the proof summary is a pure in-memory record.
  * no side effects at import time.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PHX2.stage30.stage30_8_controlled_artifact_proof_models import (
    PROOF_REASON_COUNT_MISMATCH,
    PROOF_REASON_INDEX_FAILED,
    PROOF_REASON_INVALID_OUTPUT_DIR,
    PROOF_REASON_INVALID_SCENARIO,
    PROOF_REASON_INVARIANT_FAILED,
    PROOF_REASON_OK,
    PROOF_REASON_READ_FAILED,
    PROOF_REASON_WRITE_FAILED,
    PROOF_STATUS_FAILED,
    PROOF_STATUS_PROVED,
    STAGE30_8_4_PROOF_CREATED_AT_UTC,
    STAGE30_8_4_PROOF_RUN_ID,
    STAGE30_8_4_PROOF_SCHEMA_VERSION,
    Stage30_8_4ControlledArtifactProofSummary,
    Stage30_8_4ProofScenario,
    default_proof_scenario,
)
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactPingArtifact,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    WRITE_REASON_INVALID_OUTPUT_DIR,
    WRITE_STATUS_WRITTEN,
    Stage30_8CompactSessionArtifactBundle,
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
# Pure helper: build the fake scenario bundles (in memory; no I/O)
# ---------------------------------------------------------------------------


def _build_ping(spec: object) -> Stage30_8CompactPingArtifact:
    """Build ONE Stage 30.8.1 compact ping artifact from a proof ping spec.

    The ping carries the scenario's fixed run id + fixed ISO-8601 UTC
    created-at timestamp (the proof reads no clock), the ping's OWN claimed
    session id (which may deliberately differ from its bundle session id),
    its unique ping id, its dedupe key, and a non-empty compact body. Pure.
    """
    identity = Stage30_8CompactArtifactIdentity(
        run_id=STAGE30_8_4_PROOF_RUN_ID,
        session_id=spec.identity_session_id,
        ping_id=spec.ping_id,
        artifact_created_at_utc=STAGE30_8_4_PROOF_CREATED_AT_UTC,
        artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
        dedupe_key=spec.dedupe_key,
    )
    content = Stage30_8CompactContentSnapshot(
        compact_body_text=spec.body_text,
    )
    return Stage30_8CompactPingArtifact(identity=identity, content=content)


def proof_scenario_bundles(
    scenario: Stage30_8_4ProofScenario,
) -> Tuple[Stage30_8CompactSessionArtifactBundle, ...]:
    """Build the in-memory Stage 30.8.2 bundles for a proof scenario.

    Groups the scenario's ping specs by ``bundle_session_id`` (preserving
    first-seen bundle order and per-bundle ping order, so the writer's
    zero-padded filenames match the scenario order) and returns one
    ``Stage30_8CompactSessionArtifactBundle`` per session. Pure; performs
    no I/O.
    """
    order: List[str] = []
    groups: Dict[str, List[Stage30_8CompactPingArtifact]] = {}
    for spec in scenario.pings:
        session_id = spec.bundle_session_id
        if session_id not in groups:
            groups[session_id] = []
            order.append(session_id)
        groups[session_id].append(_build_ping(spec))
    return tuple(
        Stage30_8CompactSessionArtifactBundle(
            session_id=session_id,
            ping_artifacts=tuple(groups[session_id]),
        )
        for session_id in order
    )


# ---------------------------------------------------------------------------
# Pure helpers: scenario session ids + invariant checks
# ---------------------------------------------------------------------------


def _scenario_session_ids(scenario: Stage30_8_4ProofScenario) -> Tuple[str, ...]:
    """Return the ordered, de-duplicated bundle session ids of a scenario
    (relative, safe; never an absolute path). Pure.
    """
    seen: List[str] = []
    for spec in scenario.pings:
        if spec.bundle_session_id not in seen:
            seen.append(spec.bundle_session_id)
    return tuple(seen)


def _all_retained_keyed_by_dedupe_key(index: object) -> bool:
    """Return ``True`` iff every retained ping resolved its dedupe identity
    from a non-empty ``dedupe_key`` (spec Section 9), never ``ping_id`` /
    ``none``. Pure.
    """
    return all(
        ping.identity_kind == DEDUPE_IDENTITY_KIND_DEDUPE_KEY
        and isinstance(ping.identity_value, str)
        and ping.identity_value != ""
        for ping in index.retained_pings
    )


def _retained_identities_unique(index: object) -> bool:
    """Return ``True`` iff the retained pings carry pairwise-distinct dedupe
    identity values (no two retained pings share an identity). Pure.
    """
    values = [ping.identity_value for ping in index.retained_pings]
    return len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Pure summary builder
# ---------------------------------------------------------------------------


def _summary(
    status: str,
    reason: str,
    scenario_name: str,
    session_ids: Tuple[str, ...],
    sessions_written: int = 0,
    sessions_read: int = 0,
    ping_artifacts_seen: int = 0,
    retained: int = 0,
    duplicate: int = 0,
    invalid: int = 0,
    read_failures: int = 0,
    writer_used: bool = False,
    reader_used: bool = False,
    index_builder_used: bool = False,
    manifest_backed_reads: bool = False,
    dedupe_key_only: bool = False,
) -> Stage30_8_4ControlledArtifactProofSummary:
    """Assemble a proof summary. The forbidden-surface flags are ALWAYS
    ``False`` and the no-default-storage-root / no-runtime-integration
    invariants ALWAYS ``True`` (the proof structurally cannot reach those
    surfaces). Pure.
    """
    return Stage30_8_4ControlledArtifactProofSummary(
        status=status,
        reason=reason,
        proof_schema_version=STAGE30_8_4_PROOF_SCHEMA_VERSION,
        scenario_name=scenario_name,
        sessions_written_count=sessions_written,
        sessions_read_count=sessions_read,
        ping_artifacts_seen=ping_artifacts_seen,
        retained_ping_count=retained,
        duplicate_suppressed_count=duplicate,
        invalid_suppressed_count=invalid,
        read_failure_count=read_failures,
        proof_session_ids=session_ids,
        writer_used=writer_used,
        reader_used=reader_used,
        index_builder_used=index_builder_used,
        live_provider_used=False,
        discord_send_used=False,
        env_read_used=False,
        db_used=False,
        zstd_used=False,
        runtime_integration_used=False,
        manifest_backed_reads=manifest_backed_reads,
        dedupe_key_only=dedupe_key_only,
        no_default_storage_root=True,
        no_runtime_integration=True,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_stage30_8_4_controlled_artifact_proof(
    output_dir: object,
    scenario: object = None,
) -> Stage30_8_4ControlledArtifactProofSummary:
    """Run the controlled compact session artifact proof into a
    caller-provided ``output_dir`` (a temporary / out-of-repo directory).

    With ``scenario=None`` the deterministic default scenario is used. The
    proof writes -> reads -> indexes the fake bundles through the real
    Stage 30.8.2 / 30.8.3 pieces, cross-checks the live index against the
    scenario's expected counts, verifies the dedupe-key-only +
    retained-unique invariants, and returns a passive
    ``Stage30_8_4ControlledArtifactProofSummary`` (``PROVED`` / ``FAILED``).
    Pure relative to the caller-provided dir; reads no clock, no env, no
    random; never raises.
    """
    try:
        return _run_proof(output_dir, scenario)
    except Exception:  # pragma: no cover - total fail-closed backstop
        # The composed Stage 30.8.2 / 30.8.3 pieces never raise; the only
        # realistic exception source is a malformed caller-supplied
        # scenario, so the backstop fails closed as INVALID_SCENARIO.
        return _summary(
            PROOF_STATUS_FAILED, PROOF_REASON_INVALID_SCENARIO, "", ()
        )


def _run_proof(
    output_dir: object, scenario: object
) -> Stage30_8_4ControlledArtifactProofSummary:
    """Proof body (see ``run_stage30_8_4_controlled_artifact_proof``)."""
    # 0. Resolve + gate the scenario.
    if scenario is None:
        scenario = default_proof_scenario()
    if type(scenario) is not Stage30_8_4ProofScenario:
        return _summary(
            PROOF_STATUS_FAILED, PROOF_REASON_INVALID_SCENARIO, "", ()
        )

    scenario_name = scenario.name
    session_ids = _scenario_session_ids(scenario)
    bundles = proof_scenario_bundles(scenario)

    # 1. Write each bundle through the Stage 30.8.2 writer.
    written_dirs: List[str] = []
    for bundle in bundles:
        result = write_compact_session_artifact_bundle(output_dir, bundle)
        if result.status != WRITE_STATUS_WRITTEN:
            reason = (
                PROOF_REASON_INVALID_OUTPUT_DIR
                if result.reason == WRITE_REASON_INVALID_OUTPUT_DIR
                else PROOF_REASON_WRITE_FAILED
            )
            return _summary(
                PROOF_STATUS_FAILED,
                reason,
                scenario_name,
                session_ids,
                writer_used=True,
            )
        written_dirs.append(result.session_dir)

    # 2. Read each written bundle back through the Stage 30.8.3 reader.
    ping_artifacts_seen = 0
    for session_dir in written_dirs:
        read = read_compact_session_bundle(session_dir)
        if read.status != BUNDLE_READ_STATUS_READ:
            return _summary(
                PROOF_STATUS_FAILED,
                PROOF_REASON_READ_FAILED,
                scenario_name,
                session_ids,
                sessions_written=len(written_dirs),
                read_failures=1,
                writer_used=True,
                reader_used=True,
            )
        ping_artifacts_seen += sum(
            1
            for member in read.members
            if member.member_kind == ARTIFACT_KIND_COMPACT_PING_ARTIFACT
        )
    sessions_read = len(written_dirs)

    # 3. Build the offline session index through the Stage 30.8.3 builder.
    index = build_compact_session_index(session_dirs=tuple(written_dirs))
    if index.status != INDEX_BUILD_STATUS_BUILT:
        return _summary(
            PROOF_STATUS_FAILED,
            PROOF_REASON_INDEX_FAILED,
            scenario_name,
            session_ids,
            sessions_written=len(written_dirs),
            sessions_read=sessions_read,
            ping_artifacts_seen=ping_artifacts_seen,
            writer_used=True,
            reader_used=True,
            index_builder_used=True,
            manifest_backed_reads=True,
        )

    # 4. Cross-check the live index against the scenario expected counts.
    counts_ok = (
        len(bundles) == scenario.expected_sessions_written
        and index.session_count == scenario.expected_sessions_written
        and ping_artifacts_seen == scenario.expected_ping_artifacts_seen
        and index.total_ping_count == scenario.expected_ping_artifacts_seen
        and index.retained_count == scenario.expected_retained
        and (
            index.duplicate_suppressed_count
            == scenario.expected_duplicate_suppressed
        )
        and (
            index.invalid_suppressed_count
            == scenario.expected_invalid_suppressed
        )
    )
    if not counts_ok:
        return _summary(
            PROOF_STATUS_FAILED,
            PROOF_REASON_COUNT_MISMATCH,
            scenario_name,
            session_ids,
            sessions_written=len(bundles),
            sessions_read=sessions_read,
            ping_artifacts_seen=ping_artifacts_seen,
            retained=index.retained_count,
            duplicate=index.duplicate_suppressed_count,
            invalid=index.invalid_suppressed_count,
            writer_used=True,
            reader_used=True,
            index_builder_used=True,
            manifest_backed_reads=True,
        )

    # 5. Verify the safety invariants.
    dedupe_key_only = _all_retained_keyed_by_dedupe_key(index)
    if not (dedupe_key_only and _retained_identities_unique(index)):
        return _summary(
            PROOF_STATUS_FAILED,
            PROOF_REASON_INVARIANT_FAILED,
            scenario_name,
            session_ids,
            sessions_written=len(bundles),
            sessions_read=sessions_read,
            ping_artifacts_seen=ping_artifacts_seen,
            retained=index.retained_count,
            duplicate=index.duplicate_suppressed_count,
            invalid=index.invalid_suppressed_count,
            writer_used=True,
            reader_used=True,
            index_builder_used=True,
            manifest_backed_reads=True,
            dedupe_key_only=dedupe_key_only,
        )

    # 6. PROVED.
    return _summary(
        PROOF_STATUS_PROVED,
        PROOF_REASON_OK,
        scenario_name,
        session_ids,
        sessions_written=len(bundles),
        sessions_read=sessions_read,
        ping_artifacts_seen=ping_artifacts_seen,
        retained=index.retained_count,
        duplicate=index.duplicate_suppressed_count,
        invalid=index.invalid_suppressed_count,
        writer_used=True,
        reader_used=True,
        index_builder_used=True,
        manifest_backed_reads=True,
        dedupe_key_only=True,
    )


__all__ = (
    "proof_scenario_bundles",
    "run_stage30_8_4_controlled_artifact_proof",
)
