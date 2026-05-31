"""Stage 30.9.1 artifact bridge proof tests.

Proves, end-to-end and offline, that the Stage 30.9.1 bridge composes: the
proof helper PROJECTS the scenario's capture records + dispatch context
into ONE Stage 30.8 bundle, WRITES it through the real Stage 30.8.2 writer
(one bundle write only), READS it through the real Stage 30.8.3 reader,
INDEXES it through the real Stage 30.8.3 builder, and returns a passive
``WRITTEN_AND_INDEXED`` summary whose retained / duplicate / invalid counts
match the scenario oracle. Covers the happy default scenario, the
session-mismatch scenario (an invalid-suppressed ping), an end-to-end run
whose captures come from the real capture transport, determinism, no
absolute paths, the single-bundle-write invariant, and the fail-closed
cases (projector reject, write / read / index failure, invalid output dir).

Fake / offline only. Runs against pytest ``tmp_path``; no live call, no
Discord, no env, no database, no default storage root.
"""

from __future__ import annotations

import PHX2.stage30.stage30_9_artifact_bridge_proof as proof_mod
from PHX2.stage30.stage30_9_artifact_bridge_proof import (
    run_stage30_9_1_artifact_bridge_proof,
)
from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_REASON_INDEX_REJECTED,
    BRIDGE_REASON_MISSING_DEDUPE_KEY,
    BRIDGE_REASON_NONE,
    BRIDGE_REASON_READER_REJECTED,
    BRIDGE_REASON_WRITER_REJECTED,
    BRIDGE_STATUS_INDEX_FAILED,
    BRIDGE_STATUS_INVALID_INPUT,
    BRIDGE_STATUS_READ_FAILED,
    BRIDGE_STATUS_WRITE_FAILED,
    BRIDGE_STATUS_WRITTEN_AND_INDEXED,
    STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
    STAGE30_9_1_SCENARIO_CREATED_AT_UTC,
    STAGE30_9_1_SCENARIO_DEDUPE_KEY_1,
    STAGE30_9_1_SCENARIO_RUN_ID,
    STAGE30_9_1_SCENARIO_SESSION_ID,
    Stage30_9BridgeScenario,
    Stage30_9CaptureRecord,
    Stage30_9DispatchContextRecord,
    default_bridge_scenario,
    mismatch_bridge_scenario,
)
from PHX2.stage30.stage30_9_capture_transport import (
    Stage30_9CaptureTransport,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    MANIFEST_FILENAME,
    WRITE_REASON_WRITE_FAILED,
    WRITE_STATUS_WRITE_FAILED,
    Stage30_8CompactArtifactWriteResult,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    BUNDLE_READ_REASON_MISSING_MANIFEST,
    BUNDLE_READ_STATUS_INVALID,
    Stage30_8BundleReadResult,
)
from PHX2.stage30.stage30_8_session_index_models import (
    INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
    INDEX_BUILD_STATUS_READ_FAILED,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
    Stage30_8SessionIndexBuildResult,
)


_PRIVATE = "PRIVATE_OPERATOR_WEBHOOK"


# ---------------------------------------------------------------------------
# Fakes (offline only)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, transport_status: str) -> None:
        self.transport_status = transport_status


class _FakeInnerTransport:
    def __init__(self, scripted_statuses) -> None:
        self._statuses = list(scripted_statuses)
        self.calls = []

    def send_one_audited_post(self, *, webhook_identity, payload):
        index = len(self.calls)
        self.calls.append((webhook_identity, dict(payload)))
        status = (
            self._statuses[index]
            if index < len(self._statuses)
            else "SENT_OK"
        )
        return _FakeResult(status)


# ---------------------------------------------------------------------------
# 1. Happy default scenario
# ---------------------------------------------------------------------------


def test_happy_default_scenario_written_and_indexed(tmp_path) -> None:
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))

    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED
    assert summary.reason == BRIDGE_REASON_NONE
    assert summary.bridge_proof_schema_version == (
        STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION
    )

    # Projected artifact counts (3 pings / 3 dispatch attempts / 1 error).
    assert summary.capture_record_count == 3
    assert summary.ping_artifacts_projected == 3
    assert summary.dispatch_attempts_projected == 3
    assert summary.error_artifacts_projected == 1

    # One bundle written + read; three ping members seen.
    assert summary.bundles_written_count == 1
    assert summary.bundles_read_count == 1
    assert summary.ping_artifacts_seen == 3

    # Post-run index counts match the scenario oracle.
    scenario = default_bridge_scenario()
    assert summary.retained_count == scenario.expected_retained == 2
    assert (
        summary.duplicate_suppressed_count
        == scenario.expected_duplicate_suppressed
        == 1
    )
    assert (
        summary.invalid_suppressed_count
        == scenario.expected_invalid_suppressed
        == 0
    )


def test_happy_flags_and_invariants(tmp_path) -> None:
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    # The composed pieces were actually invoked.
    assert summary.projector_used is True
    assert summary.writer_used is True
    assert summary.reader_used is True
    assert summary.index_builder_used is True
    # The forbidden surfaces were never reached.
    assert summary.live_provider_used is False
    assert summary.discord_send_used is False
    assert summary.env_read_used is False
    assert summary.db_used is False
    assert summary.zstd_used is False
    # Invariants.
    assert summary.single_bundle_write is True
    assert summary.no_default_storage_root is True
    assert summary.dedupe_key_from_dispatch_context is True


def test_happy_accepts_path_object_output_dir(tmp_path) -> None:
    summary = run_stage30_9_1_artifact_bridge_proof(tmp_path)
    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED


def test_happy_summary_carries_no_absolute_path(tmp_path) -> None:
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    # Only the relative scenario session id is exposed.
    assert summary.proof_session_id == STAGE30_9_1_SCENARIO_SESSION_ID
    base = str(tmp_path)
    assert base not in (summary.proof_session_id or "")
    assert ":" not in (summary.proof_session_id or "")
    assert "/" not in (summary.proof_session_id or "")
    assert "\\" not in (summary.proof_session_id or "")


def test_happy_really_wrote_one_manifest_backed_bundle(tmp_path) -> None:
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED
    # Exactly one session bundle dir under the caller-provided dir, with a
    # manifest.json (the real writer truly persisted it).
    session_dir = tmp_path / STAGE30_9_1_SCENARIO_SESSION_ID
    assert session_dir.is_dir()
    assert (session_dir / MANIFEST_FILENAME).is_file()
    non_hidden = [
        p for p in tmp_path.iterdir() if not p.name.startswith(".")
    ]
    assert non_hidden == [session_dir]


# ---------------------------------------------------------------------------
# 2. Mismatch scenario -> one invalid-suppressed ping
# ---------------------------------------------------------------------------


def test_mismatch_scenario_invalid_suppressed(tmp_path) -> None:
    scenario = mismatch_bridge_scenario()
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path), scenario)

    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED
    assert summary.ping_artifacts_seen == 4
    # 2 retained, 1 duplicate, 1 invalid-suppressed (the session-mismatched
    # ping the post-run index rejects).
    assert summary.retained_count == scenario.expected_retained == 2
    assert (
        summary.duplicate_suppressed_count
        == scenario.expected_duplicate_suppressed
        == 1
    )
    assert (
        summary.invalid_suppressed_count
        == scenario.expected_invalid_suppressed
        == 1
    )


# ---------------------------------------------------------------------------
# 3. The proof uses the real Stage 30.8 writer / reader / builder (one write)
# ---------------------------------------------------------------------------


def test_proof_uses_real_pieces_with_single_bundle_write(
    monkeypatch, tmp_path
) -> None:
    calls = {"write": 0, "read": 0, "build": 0}
    real_write = proof_mod.write_compact_session_artifact_bundle
    real_read = proof_mod.read_compact_session_bundle
    real_build = proof_mod.build_compact_session_index

    def counting_write(output_dir, bundle):
        calls["write"] += 1
        return real_write(output_dir, bundle)

    def counting_read(session_dir):
        calls["read"] += 1
        return real_read(session_dir)

    def counting_build(session_dirs=None, output_root=None):
        calls["build"] += 1
        return real_build(session_dirs=session_dirs, output_root=output_root)

    monkeypatch.setattr(
        proof_mod, "write_compact_session_artifact_bundle", counting_write
    )
    monkeypatch.setattr(
        proof_mod, "read_compact_session_bundle", counting_read
    )
    monkeypatch.setattr(
        proof_mod, "build_compact_session_index", counting_build
    )

    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED
    # EXACTLY one bundle write (never per ping), one read, one index build.
    assert calls["write"] == 1
    assert calls["read"] == 1
    assert calls["build"] == 1


# ---------------------------------------------------------------------------
# 4. End-to-end: captures come from the real capture transport
# ---------------------------------------------------------------------------


def test_end_to_end_through_real_capture_transport(tmp_path) -> None:
    # Drive a fake inner transport through the REAL capture transport to
    # produce real capture records, then bridge-proof over them: capture ->
    # project -> write -> read -> index.
    inner = _FakeInnerTransport(["SENT_OK", "SENT_OK", "SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    bodies = ("body-A", "body-B", "body-C")
    for body in bodies:
        transport.send_one_audited_post(
            webhook_identity=_PRIVATE, payload={"content": body}
        )
    captures = transport.records
    assert len(captures) == 3

    contexts = (
        Stage30_9DispatchContextRecord(
            capture_index=0,
            dedupe_key="k1",
            ping_id="p1",
            candidate_id="c1",
            token_mint="m1",
        ),
        Stage30_9DispatchContextRecord(
            capture_index=1,
            dedupe_key="k1",
            ping_id="p2",
            candidate_id="c1",
            token_mint="m1",
        ),
        Stage30_9DispatchContextRecord(
            capture_index=2,
            dedupe_key="k2",
            ping_id="p3",
            candidate_id="c2",
            token_mint="m2",
        ),
    )
    scenario = Stage30_9BridgeScenario(
        name="end-to-end",
        run_id=STAGE30_9_1_SCENARIO_RUN_ID,
        session_id=STAGE30_9_1_SCENARIO_SESSION_ID,
        artifact_created_at_utc=STAGE30_9_1_SCENARIO_CREATED_AT_UTC,
        capture_records=captures,
        dispatch_context_records=contexts,
        session_summary_counters=None,
        expected_ping_count=3,
        expected_retained=2,
        expected_duplicate_suppressed=1,
        expected_invalid_suppressed=0,
    )
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path), scenario)
    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED
    assert summary.ping_artifacts_seen == 3
    assert summary.retained_count == 2
    assert summary.duplicate_suppressed_count == 1
    assert summary.invalid_suppressed_count == 0


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def test_two_runs_in_separate_temp_dirs_are_identical(tmp_path) -> None:
    s1 = run_stage30_9_1_artifact_bridge_proof(str(tmp_path / "run1"))
    s2 = run_stage30_9_1_artifact_bridge_proof(str(tmp_path / "run2"))
    # No absolute path / timestamp / random on the summary -> identical.
    assert s1 == s2
    assert s1.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED


# ---------------------------------------------------------------------------
# 6. Fail-closed: projector reject (missing dedupe context)
# ---------------------------------------------------------------------------


def test_projector_reject_surfaces_invalid_input(tmp_path) -> None:
    # A dispatch context with no dedupe_key -> the projector fails closed;
    # the bridge surfaces INVALID_INPUT / MISSING_DEDUPE_KEY and writes
    # nothing.
    captures = (
        Stage30_9CaptureRecord(
            capture_index=0,
            webhook_identity=_PRIVATE,
            payload_body_text="body",
            payload_keys=("content",),
            sanitized_transport_status="SENT_OK",
        ),
    )
    contexts = (
        Stage30_9DispatchContextRecord(capture_index=0, dedupe_key=None),
    )
    scenario = Stage30_9BridgeScenario(
        name="missing-dedupe",
        run_id=STAGE30_9_1_SCENARIO_RUN_ID,
        session_id=STAGE30_9_1_SCENARIO_SESSION_ID,
        artifact_created_at_utc=STAGE30_9_1_SCENARIO_CREATED_AT_UTC,
        capture_records=captures,
        dispatch_context_records=contexts,
        session_summary_counters=None,
        expected_ping_count=0,
        expected_retained=0,
        expected_duplicate_suppressed=0,
        expected_invalid_suppressed=0,
    )
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path), scenario)
    assert summary.status == BRIDGE_STATUS_INVALID_INPUT
    assert summary.reason == BRIDGE_REASON_MISSING_DEDUPE_KEY
    assert summary.bundles_written_count == 0
    assert summary.writer_used is False
    # Nothing was written under the output dir.
    non_hidden = [
        p for p in tmp_path.iterdir() if not p.name.startswith(".")
    ]
    assert non_hidden == []


# ---------------------------------------------------------------------------
# 7. Fail-closed: invalid output dir
# ---------------------------------------------------------------------------


def test_invalid_output_dir_fails_closed() -> None:
    for bad in (None, "", "."):
        summary = run_stage30_9_1_artifact_bridge_proof(bad)
        # The projection succeeds (it does not need the output dir), then the
        # writer rejects the non-explicit dir -> WRITE_FAILED.
        assert summary.status == BRIDGE_STATUS_WRITE_FAILED
        assert summary.reason == BRIDGE_REASON_WRITER_REJECTED
        assert summary.bundles_written_count == 0
        assert summary.bundles_read_count == 0


# ---------------------------------------------------------------------------
# 8. Fail-closed: writer / reader / index failure (monkeypatched)
# ---------------------------------------------------------------------------


def test_write_failure_fails_closed(monkeypatch, tmp_path) -> None:
    def fake_write(output_dir, bundle):
        return Stage30_8CompactArtifactWriteResult(
            status=WRITE_STATUS_WRITE_FAILED,
            reason=WRITE_REASON_WRITE_FAILED,
            validation_status="VALID",
            validation_reason="OK",
            blocked_field=None,
            safe_to_persist=False,
            session_dir=None,
            written_paths=(),
            artifact_count=0,
        )

    monkeypatch.setattr(
        proof_mod, "write_compact_session_artifact_bundle", fake_write
    )
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    assert summary.status == BRIDGE_STATUS_WRITE_FAILED
    assert summary.reason == BRIDGE_REASON_WRITER_REJECTED
    assert summary.writer_used is True
    assert summary.reader_used is False
    assert summary.index_builder_used is False


def test_read_failure_fails_closed(monkeypatch, tmp_path) -> None:
    def fake_read(session_dir):
        return Stage30_8BundleReadResult(
            status=BUNDLE_READ_STATUS_INVALID,
            reason=BUNDLE_READ_REASON_MISSING_MANIFEST,
            session_dir=str(session_dir),
            session_id=None,
            bundle_schema_version=None,
            members=(),
            member_count=0,
            blocked_file=None,
        )

    monkeypatch.setattr(
        proof_mod, "read_compact_session_bundle", fake_read
    )
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    assert summary.status == BRIDGE_STATUS_READ_FAILED
    assert summary.reason == BRIDGE_REASON_READER_REJECTED
    assert summary.writer_used is True
    assert summary.reader_used is True
    assert summary.bundles_written_count == 1


def test_index_failure_fails_closed(monkeypatch, tmp_path) -> None:
    def fake_build(session_dirs=None, output_root=None):
        return Stage30_8SessionIndexBuildResult(
            status=INDEX_BUILD_STATUS_READ_FAILED,
            reason=INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
            index_schema_version=STAGE30_8_3_INDEX_SCHEMA_VERSION,
            session_count=0,
            total_ping_count=0,
            retained_count=0,
            duplicate_suppressed_count=0,
            invalid_suppressed_count=0,
        )

    monkeypatch.setattr(
        proof_mod, "build_compact_session_index", fake_build
    )
    summary = run_stage30_9_1_artifact_bridge_proof(str(tmp_path))
    assert summary.status == BRIDGE_STATUS_INDEX_FAILED
    assert summary.reason == BRIDGE_REASON_INDEX_REJECTED
    assert summary.index_builder_used is True


# ---------------------------------------------------------------------------
# 9. Total fail-closed: never raises
# ---------------------------------------------------------------------------


def test_bridge_proof_never_raises(tmp_path) -> None:
    for output_dir in (None, "", ".", 123, object(), str(tmp_path)):
        summary = run_stage30_9_1_artifact_bridge_proof(output_dir)
        assert summary.status in (
            BRIDGE_STATUS_WRITTEN_AND_INDEXED,
            BRIDGE_STATUS_WRITE_FAILED,
            BRIDGE_STATUS_READ_FAILED,
            BRIDGE_STATUS_INDEX_FAILED,
            BRIDGE_STATUS_INVALID_INPUT,
            "PROJECT_FAILED",
        )
