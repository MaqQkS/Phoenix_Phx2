"""Stage 30.8.4 controlled compact session artifact proof tests.

Proves, end-to-end and offline, that the Stage 30.8 storage chain
composes: the Stage 30.8.4 runner WRITES fake compact session bundles
through the real Stage 30.8.2 writer, READS them back through the real
Stage 30.8.3 reader, INDEXES them through the real Stage 30.8.3 builder,
and returns a deterministic ``PROVED`` summary. Covers the happy proof
(counts + flags + invariants), the duplicate proof (same-session +
cross-session duplicates, dedupe driven by ``dedupe_key`` not ``ping_id``),
real reader/index composition, determinism across temp dirs, and the
fail-closed cases (invalid output dir, write / read / index failure, count
mismatch, invariant failure).

Fake / offline only. The proof runs against pytest ``tmp_path`` temp dirs;
it makes no live call, sends no Discord, reads no environment, opens no
database, and uses no default storage root.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_8_controlled_artifact_proof as proof_mod
from PHX2.stage30.stage30_8_controlled_artifact_proof import (
    proof_scenario_bundles,
    run_stage30_8_4_controlled_artifact_proof,
)
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
    STAGE30_8_4_DEFAULT_SCENARIO_NAME,
    STAGE30_8_4_PROOF_DEDUPE_KEY_1,
    STAGE30_8_4_PROOF_DEDUPE_KEY_2,
    STAGE30_8_4_PROOF_DEDUPE_KEY_3,
    STAGE30_8_4_PROOF_DEDUPE_KEY_4,
    STAGE30_8_4_PROOF_SCHEMA_VERSION,
    STAGE30_8_4_PROOF_SESSION_A_ID,
    STAGE30_8_4_PROOF_SESSION_B_ID,
    Stage30_8_4ProofScenario,
    default_proof_scenario,
)
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    MANIFEST_FILENAME,
    WRITE_REASON_WRITE_FAILED,
    WRITE_STATUS_WRITTEN,
    WRITE_STATUS_WRITE_FAILED,
    Stage30_8CompactArtifactWriteResult,
    write_compact_session_artifact_bundle,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    BUNDLE_READ_REASON_MISSING_MANIFEST,
    BUNDLE_READ_STATUS_INVALID,
    BUNDLE_READ_STATUS_READ,
    Stage30_8BundleReadResult,
    read_compact_session_bundle,
)
from PHX2.stage30.stage30_8_session_index_builder import (
    build_compact_session_index,
)
from PHX2.stage30.stage30_8_session_index_models import (
    DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
    DEDUPE_IDENTITY_KIND_NONE,
    INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
    INDEX_BUILD_REASON_OK,
    INDEX_BUILD_STATUS_BUILT,
    INDEX_BUILD_STATUS_READ_FAILED,
    PING_DEDUPE_STATUS_RETAINED,
    PING_SUPPRESS_REASON_NONE,
    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
    Stage30_8IndexedPingArtifact,
    Stage30_8SessionIndexBuildResult,
)


# ---------------------------------------------------------------------------
# 1. Happy proof
# ---------------------------------------------------------------------------


def test_happy_proof_is_proved_with_expected_counts(tmp_path) -> None:
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))

    assert summary.status == PROOF_STATUS_PROVED
    assert summary.reason == PROOF_REASON_OK
    assert summary.proof_schema_version == STAGE30_8_4_PROOF_SCHEMA_VERSION
    assert summary.scenario_name == STAGE30_8_4_DEFAULT_SCENARIO_NAME

    # Counts (the scenario oracle: 2 sessions / 6 pings / 3 retained / 2
    # duplicate-suppressed / 1 invalid-suppressed).
    assert summary.sessions_written_count == 2
    assert summary.sessions_read_count == 2
    assert summary.ping_artifacts_seen == 6
    assert summary.retained_ping_count == 3
    assert summary.duplicate_suppressed_count == 2
    assert summary.invalid_suppressed_count == 1
    assert summary.read_failure_count == 0


def test_happy_proof_flags_and_invariants(tmp_path) -> None:
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))

    # The composed Stage 30.8.x pieces were actually invoked.
    assert summary.writer_used is True
    assert summary.reader_used is True
    assert summary.index_builder_used is True

    # The forbidden surfaces were never reached (structurally impossible).
    assert summary.live_provider_used is False
    assert summary.discord_send_used is False
    assert summary.env_read_used is False
    assert summary.db_used is False
    assert summary.zstd_used is False
    assert summary.runtime_integration_used is False

    # Safety invariants.
    assert summary.manifest_backed_reads is True
    assert summary.dedupe_key_only is True
    assert summary.no_default_storage_root is True
    assert summary.no_runtime_integration is True


def test_happy_proof_accepts_path_object_output_dir(tmp_path) -> None:
    # A Path (not only a str) output dir is accepted by the writer.
    summary = run_stage30_8_4_controlled_artifact_proof(tmp_path)
    assert summary.status == PROOF_STATUS_PROVED


def test_happy_proof_summary_carries_no_absolute_path(tmp_path) -> None:
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    # Only the relative scenario session ids are exposed -- never an
    # absolute temp path.
    assert summary.proof_session_ids == (
        STAGE30_8_4_PROOF_SESSION_A_ID,
        STAGE30_8_4_PROOF_SESSION_B_ID,
    )
    base = str(tmp_path)
    for session_id in summary.proof_session_ids:
        assert base not in session_id
        assert ":" not in session_id
        assert "/" not in session_id and "\\" not in session_id


def test_happy_proof_really_wrote_manifest_backed_bundles(tmp_path) -> None:
    # Real composition: the writer truly persisted a manifest-backed bundle
    # per session under the caller-provided dir (not a mocked result).
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_PROVED
    for session_id in summary.proof_session_ids:
        session_dir = tmp_path / session_id
        assert session_dir.is_dir()
        assert (session_dir / MANIFEST_FILENAME).is_file()


# ---------------------------------------------------------------------------
# 2. Duplicate proof (same-session + cross-session; dedupe_key not ping_id)
# ---------------------------------------------------------------------------


def _write_default_scenario(tmp_path) -> list:
    """Write the default scenario bundles through the real writer; return
    the written session dirs.
    """
    scenario = default_proof_scenario()
    bundles = proof_scenario_bundles(scenario)
    dirs = []
    for bundle in bundles:
        result = write_compact_session_artifact_bundle(str(tmp_path), bundle)
        assert result.status == WRITE_STATUS_WRITTEN
        dirs.append(result.session_dir)
    return dirs


def test_same_and_cross_session_duplicates_suppressed(tmp_path) -> None:
    dirs = _write_default_scenario(tmp_path)
    index = build_compact_session_index(session_dirs=tuple(dirs))
    assert index.status == INDEX_BUILD_STATUS_BUILT

    retained_by_key = {p.dedupe_key: p for p in index.retained_pings}
    duplicates_by_key = {p.dedupe_key: p for p in index.duplicate_pings}

    # K1 / K2 / K3 are the three retained (unique) dedupe identities.
    assert set(retained_by_key) == {
        STAGE30_8_4_PROOF_DEDUPE_KEY_1,
        STAGE30_8_4_PROOF_DEDUPE_KEY_2,
        STAGE30_8_4_PROOF_DEDUPE_KEY_3,
    }

    # Same-session duplicate: A3 (K1) duplicates A1, both in session A.
    a1 = retained_by_key[STAGE30_8_4_PROOF_DEDUPE_KEY_1]
    a3 = duplicates_by_key[STAGE30_8_4_PROOF_DEDUPE_KEY_1]
    assert a1.session_id == STAGE30_8_4_PROOF_SESSION_A_ID
    assert a3.session_id == STAGE30_8_4_PROOF_SESSION_A_ID
    assert a3.duplicate_of_session_id == STAGE30_8_4_PROOF_SESSION_A_ID
    assert a3.duplicate_of_artifact_filename == a1.artifact_filename

    # Cross-session duplicate: B2 (K2) duplicates A2 -- across sessions.
    a2 = retained_by_key[STAGE30_8_4_PROOF_DEDUPE_KEY_2]
    b2 = duplicates_by_key[STAGE30_8_4_PROOF_DEDUPE_KEY_2]
    assert a2.session_id == STAGE30_8_4_PROOF_SESSION_A_ID
    assert b2.session_id == STAGE30_8_4_PROOF_SESSION_B_ID
    assert b2.duplicate_of_session_id == STAGE30_8_4_PROOF_SESSION_A_ID
    assert b2.session_id != b2.duplicate_of_session_id


def test_dedupe_driven_by_dedupe_key_not_ping_id(tmp_path) -> None:
    dirs = _write_default_scenario(tmp_path)
    index = build_compact_session_index(session_dirs=tuple(dirs))

    a1 = next(
        p
        for p in index.retained_pings
        if p.dedupe_key == STAGE30_8_4_PROOF_DEDUPE_KEY_1
    )
    a3 = next(
        p
        for p in index.duplicate_pings
        if p.dedupe_key == STAGE30_8_4_PROOF_DEDUPE_KEY_1
    )
    # A1 and A3 carry DIFFERENT ping ids but the SAME dedupe key, yet A3 is
    # still suppressed as a duplicate -> dedupe is driven by dedupe_key.
    assert a1.ping_id != a3.ping_id
    assert a1.dedupe_key == a3.dedupe_key == STAGE30_8_4_PROOF_DEDUPE_KEY_1
    # Every retained ping resolved its identity from dedupe_key (Section 9).
    for ping in index.retained_pings:
        assert ping.identity_kind == DEDUPE_IDENTITY_KIND_DEDUPE_KEY
        assert ping.identity_value == ping.dedupe_key


def test_mismatched_ping_invalid_suppressed_via_session_mismatch(
    tmp_path,
) -> None:
    dirs = _write_default_scenario(tmp_path)
    index = build_compact_session_index(session_dirs=tuple(dirs))

    assert len(index.invalid_pings) == 1
    invalid = index.invalid_pings[0]
    # B3 was a VALID artifact the writer accepted (its own session id is a
    # non-empty string) but its session id does not match the bundle, so
    # the index suppresses it.
    assert invalid.dedupe_key == STAGE30_8_4_PROOF_DEDUPE_KEY_4
    assert invalid.suppress_reason == PING_SUPPRESS_REASON_SESSION_ID_MISMATCH


# ---------------------------------------------------------------------------
# 3. Reader / index composition (the runner uses the real Stage 30.8.3
#    pieces; it does not reimplement the read / dedupe logic)
# ---------------------------------------------------------------------------


def test_runner_uses_real_reader_and_builder(monkeypatch, tmp_path) -> None:
    calls = {"read": 0, "build": 0}
    real_read = proof_mod.read_compact_session_bundle
    real_build = proof_mod.build_compact_session_index

    def counting_read(session_dir):
        calls["read"] += 1
        return real_read(session_dir)

    def counting_build(session_dirs=None, output_root=None):
        calls["build"] += 1
        return real_build(session_dirs=session_dirs, output_root=output_root)

    monkeypatch.setattr(proof_mod, "read_compact_session_bundle", counting_read)
    monkeypatch.setattr(
        proof_mod, "build_compact_session_index", counting_build
    )

    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_PROVED
    # The reader was invoked once per session and the builder exactly once.
    assert calls["read"] == 2
    assert calls["build"] == 1


# ---------------------------------------------------------------------------
# 4. Determinism (two runs in separate temp dirs give an identical summary)
# ---------------------------------------------------------------------------


def test_two_runs_in_separate_temp_dirs_are_identical(tmp_path) -> None:
    summary_1 = run_stage30_8_4_controlled_artifact_proof(
        str(tmp_path / "run1")
    )
    summary_2 = run_stage30_8_4_controlled_artifact_proof(
        str(tmp_path / "run2")
    )
    # The summary carries no absolute path / timestamp / random value, so
    # the two runs are byte-for-byte identical (frozen dataclass equality).
    assert summary_1 == summary_2
    assert summary_1.status == PROOF_STATUS_PROVED


def test_scenario_bundles_are_deterministic() -> None:
    scenario = default_proof_scenario()
    bundles_1 = proof_scenario_bundles(scenario)
    bundles_2 = proof_scenario_bundles(scenario)
    assert bundles_1 == bundles_2
    # Two sessions, three pings each (A1/A2/A3 and B1/B2/B3).
    assert len(bundles_1) == 2
    assert [b.session_id for b in bundles_1] == [
        STAGE30_8_4_PROOF_SESSION_A_ID,
        STAGE30_8_4_PROOF_SESSION_B_ID,
    ]
    assert all(len(b.ping_artifacts) == 3 for b in bundles_1)


# ---------------------------------------------------------------------------
# 5. Fail-closed cases
# ---------------------------------------------------------------------------


def test_invalid_output_dir_fails_closed() -> None:
    for bad in (None, "", "."):
        summary = run_stage30_8_4_controlled_artifact_proof(bad)
        assert summary.status == PROOF_STATUS_FAILED
        assert summary.reason == PROOF_REASON_INVALID_OUTPUT_DIR
        # Nothing safely written / read / indexed.
        assert summary.sessions_written_count == 0
        assert summary.sessions_read_count == 0


def test_invalid_scenario_fails_closed(tmp_path) -> None:
    # A non-scenario object fails closed (and never raises).
    for bad_scenario in (object(), "not-a-scenario", 123, {"pings": []}):
        summary = run_stage30_8_4_controlled_artifact_proof(
            str(tmp_path), bad_scenario
        )
        assert summary.status == PROOF_STATUS_FAILED
        assert summary.reason == PROOF_REASON_INVALID_SCENARIO


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
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_FAILED
    assert summary.reason == PROOF_REASON_WRITE_FAILED
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

    monkeypatch.setattr(proof_mod, "read_compact_session_bundle", fake_read)
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_FAILED
    assert summary.reason == PROOF_REASON_READ_FAILED
    assert summary.writer_used is True
    assert summary.reader_used is True
    assert summary.read_failure_count == 1


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
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_FAILED
    assert summary.reason == PROOF_REASON_INDEX_FAILED
    assert summary.index_builder_used is True


def test_count_mismatch_fails_closed(monkeypatch, tmp_path) -> None:
    def fake_build(session_dirs=None, output_root=None):
        # BUILT, but the retained count does not match the scenario oracle.
        return Stage30_8SessionIndexBuildResult(
            status=INDEX_BUILD_STATUS_BUILT,
            reason=INDEX_BUILD_REASON_OK,
            index_schema_version=STAGE30_8_3_INDEX_SCHEMA_VERSION,
            session_count=2,
            total_ping_count=6,
            retained_count=99,
            duplicate_suppressed_count=2,
            invalid_suppressed_count=1,
        )

    monkeypatch.setattr(
        proof_mod, "build_compact_session_index", fake_build
    )
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_FAILED
    assert summary.reason == PROOF_REASON_COUNT_MISMATCH


def test_invariant_failure_fails_closed(monkeypatch, tmp_path) -> None:
    # Counts match the oracle, but one "retained" ping resolved no
    # dedupe_key identity -> the dedupe_key_only invariant fails closed.
    bad_retained = (
        Stage30_8IndexedPingArtifact(
            session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            session_dir="session-a",
            artifact_filename="ping_artifact_0001.json",
            member_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            ping_id="p1",
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_1,
            identity_kind=DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
            identity_value=STAGE30_8_4_PROOF_DEDUPE_KEY_1,
            dedupe_status=PING_DEDUPE_STATUS_RETAINED,
            suppress_reason=PING_SUPPRESS_REASON_NONE,
        ),
        Stage30_8IndexedPingArtifact(
            session_id=STAGE30_8_4_PROOF_SESSION_A_ID,
            session_dir="session-a",
            artifact_filename="ping_artifact_0002.json",
            member_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            ping_id="p2",
            dedupe_key=STAGE30_8_4_PROOF_DEDUPE_KEY_2,
            identity_kind=DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
            identity_value=STAGE30_8_4_PROOF_DEDUPE_KEY_2,
            dedupe_status=PING_DEDUPE_STATUS_RETAINED,
            suppress_reason=PING_SUPPRESS_REASON_NONE,
        ),
        Stage30_8IndexedPingArtifact(
            session_id=STAGE30_8_4_PROOF_SESSION_B_ID,
            session_dir="session-b",
            artifact_filename="ping_artifact_0001.json",
            member_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            ping_id="p3",
            dedupe_key=None,
            identity_kind=DEDUPE_IDENTITY_KIND_NONE,
            identity_value=None,
            dedupe_status=PING_DEDUPE_STATUS_RETAINED,
            suppress_reason=PING_SUPPRESS_REASON_NONE,
        ),
    )

    def fake_build(session_dirs=None, output_root=None):
        return Stage30_8SessionIndexBuildResult(
            status=INDEX_BUILD_STATUS_BUILT,
            reason=INDEX_BUILD_REASON_OK,
            index_schema_version=STAGE30_8_3_INDEX_SCHEMA_VERSION,
            session_count=2,
            total_ping_count=6,
            retained_count=3,
            duplicate_suppressed_count=2,
            invalid_suppressed_count=1,
            retained_pings=bad_retained,
        )

    monkeypatch.setattr(
        proof_mod, "build_compact_session_index", fake_build
    )
    summary = run_stage30_8_4_controlled_artifact_proof(str(tmp_path))
    assert summary.status == PROOF_STATUS_FAILED
    assert summary.reason == PROOF_REASON_INVARIANT_FAILED
    assert summary.dedupe_key_only is False


def test_real_corrupted_bundle_fails_index_closed(tmp_path) -> None:
    # Corrupt a real manifest-backed bundle (remove its manifest.json) and
    # confirm the real reader + builder fail the whole index closed -- no
    # monkeypatching; the genuine Stage 30.8.3 pieces.
    dirs = _write_default_scenario(tmp_path)
    manifest = Path(dirs[0]) / MANIFEST_FILENAME
    assert manifest.is_file()
    manifest.unlink()

    read = read_compact_session_bundle(dirs[0])
    assert read.status == BUNDLE_READ_STATUS_INVALID

    index = build_compact_session_index(session_dirs=tuple(dirs))
    assert index.status == INDEX_BUILD_STATUS_READ_FAILED


def test_runner_never_raises_on_bad_inputs(tmp_path) -> None:
    # Total fail-closed: every odd input yields a summary, never an
    # exception.
    for output_dir in (None, "", ".", 123, object(), str(tmp_path)):
        summary = run_stage30_8_4_controlled_artifact_proof(output_dir)
        assert summary.status in (PROOF_STATUS_PROVED, PROOF_STATUS_FAILED)


def test_proof_scenario_bundles_only_holds_ping_artifacts() -> None:
    # The proof scenario writes ONLY compact ping artifacts (no summary /
    # dispatch / error / budget members), so every read member is a ping.
    bundles = proof_scenario_bundles(default_proof_scenario())
    for bundle in bundles:
        assert bundle.session_summary is None
        assert bundle.dispatch_attempt_artifacts == ()
        assert bundle.error_artifacts == ()
        assert bundle.storage_budget_snapshot is None
        assert len(bundle.ping_artifacts) == 3
