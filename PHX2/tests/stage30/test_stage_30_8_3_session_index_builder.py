"""Stage 30.8.3 offline session index / dedupe builder tests.

Pure offline unit tests for the Stage 30.8.3 builder. Every test reads
ONLY from the pytest ``tmp_path`` temporary directory (out-of-repo); no
live calls, no env reads, no Discord, no provider, no database / SQLite /
zstd. Happy-path / dedupe bundles are produced by the real Stage 30.8.2
writer; the identity-less and session_id-mismatch cases hand-craft raw
bundles (the writer cannot produce a ping that lacks a dedupe_key or that
spoofs its session_id).

Pinned contract: the builder is deterministic and fail-closed. The dedupe
identity is the spec-locked ``dedupe_key`` ALONE (no ``ping_id``
fallback); ``ping_id`` is only a deterministic ordering tiebreak. The
first occurrence by (session_id, session_dir, filename, ping_id) wins and
later occurrences are DUPLICATE_SUPPRESSED (global across sessions); a
ping with no usable ``dedupe_key`` -- or whose own session_id does not
match its bundle -- is INVALID_SUPPRESSED and never retained; an invalid
bundle dir fails the WHOLE build closed (READ_FAILED); bad arguments
yield INVALID_INPUT. The builder writes nothing and never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactPingArtifact,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    WRITE_STATUS_WRITTEN,
    Stage30_8CompactSessionArtifactBundle,
    write_compact_session_artifact_bundle,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    BUNDLE_READ_REASON_MISSING_MANIFEST,
    EXPECTED_BUNDLE_SCHEMA_VERSION,
)
from PHX2.stage30.stage30_8_session_index_builder import (
    build_compact_session_index,
)
from PHX2.stage30.stage30_8_session_index_models import (
    DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
    INDEX_BUILD_REASON_AMBIGUOUS_SOURCE,
    INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
    INDEX_BUILD_REASON_EMPTY,
    INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT,
    INDEX_BUILD_REASON_INVALID_SESSION_DIRS,
    INDEX_BUILD_REASON_NO_SOURCE,
    INDEX_BUILD_REASON_OK,
    INDEX_BUILD_STATUS_BUILT,
    INDEX_BUILD_STATUS_EMPTY,
    INDEX_BUILD_STATUS_INVALID_INPUT,
    INDEX_BUILD_STATUS_READ_FAILED,
    PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
    PING_DEDUPE_STATUS_RETAINED,
    PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
    PING_SUPPRESS_REASON_MISSING_IDENTITY,
    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _ping(session_id: str, ping_id: str, dedupe_key: str) -> (
    Stage30_8CompactPingArtifact
):
    return Stage30_8CompactPingArtifact(
        identity=Stage30_8CompactArtifactIdentity(
            run_id="run-1",
            session_id=session_id,
            ping_id=ping_id,
            artifact_created_at_utc="2026-05-29T00:00:01Z",
            artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            dedupe_key=dedupe_key,
        ),
        content=Stage30_8CompactContentSnapshot(
            compact_body_text="MC: $83k | ATH: $120k | Mig: Known"
        ),
    )


def _write_bundle(
    out_dir: Path, session_id: str, pings: tuple
) -> Path:
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id=session_id, ping_artifacts=pings
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_WRITTEN, result
    return out_dir / session_id


def _raw_ping_bundle(
    session_dir: Path, session_id: str, ping_identities: List[dict]
) -> Path:
    """Hand-write a structurally-valid bundle whose ping artifacts carry
    caller-chosen identity axes (so a ping can deliberately lack a
    ``dedupe_key`` / ``ping_id``). The reader accepts it (manifest-backed,
    complete); the builder applies the dedupe policy.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    member_files: List[str] = []
    for index, axes in enumerate(ping_identities, start=1):
        name = f"ping_artifact_{index:04d}.json"
        member_files.append(name)
        identity = {
            "stage_id": STAGE30_8_ARTIFACT_STAGE_ID,
            "artifact_schema_version": STAGE30_8_ARTIFACT_SCHEMA_VERSION,
            "artifact_kind": ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            "session_id": session_id,
            "run_id": "run-1",
            "artifact_created_at_utc": "2026-05-29T00:00:01Z",
        }
        identity.update(axes)
        payload = {
            "identity": identity,
            "content": {"compact_body_text": "MC: $83k"},
        }
        (session_dir / name).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    manifest = {
        "bundle_schema_version": EXPECTED_BUNDLE_SCHEMA_VERSION,
        "session_id": session_id,
        "member_files": sorted(member_files),
    }
    (session_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (session_dir / "validation_result.json").write_text(
        json.dumps({"validation_status": "VALID"}), encoding="utf-8"
    )
    return session_dir


def _snapshot_tree(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# 1. Happy path (two bundles, real writer)
# ---------------------------------------------------------------------------


def test_happy_path_two_bundles(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        "sess-a",
        (_ping("sess-a", "p1", "dk-1"), _ping("sess-a", "p2", "dk-2")),
    )
    _write_bundle(tmp_path, "sess-b", (_ping("sess-b", "p3", "dk-3"),))

    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.reason == INDEX_BUILD_REASON_OK
    assert result.index_schema_version == STAGE30_8_3_INDEX_SCHEMA_VERSION
    assert result.session_count == 2
    assert result.total_ping_count == 3
    assert result.retained_count == 3
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 0
    # Sessions ordered by session_id ascending.
    assert [s.session_id for s in result.sessions] == ["sess-a", "sess-b"]
    # Each session lists its own pings (GOAL Q2).
    assert result.sessions[0].ping_artifact_count == 2
    assert result.sessions[1].ping_artifact_count == 1
    for ping in result.retained_pings:
        assert ping.dedupe_status == PING_DEDUPE_STATUS_RETAINED
        assert ping.identity_kind == DEDUPE_IDENTITY_KIND_DEDUPE_KEY


# ---------------------------------------------------------------------------
# 2. Duplicate within one session
# ---------------------------------------------------------------------------


def test_duplicate_in_same_session(tmp_path: Path) -> None:
    # Two pings with the SAME dedupe_key (distinct ping_ids) -> the second
    # is suppressed. This also proves the dedupe axis is dedupe_key, not
    # ping_id (distinct ping_ids still dedupe).
    _write_bundle(
        tmp_path,
        "sess-x",
        (_ping("sess-x", "pA", "dup-key"), _ping("sess-x", "pB", "dup-key")),
    )
    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 1
    assert result.duplicate_suppressed_count == 1
    retained = result.retained_pings[0]
    duplicate = result.duplicate_pings[0]
    assert retained.artifact_filename == "ping_artifact_0001.json"
    assert duplicate.artifact_filename == "ping_artifact_0002.json"
    assert duplicate.dedupe_status == PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED
    assert duplicate.suppress_reason == PING_SUPPRESS_REASON_DUPLICATE_IDENTITY
    assert duplicate.duplicate_of_session_id == "sess-x"
    assert (
        duplicate.duplicate_of_artifact_filename
        == "ping_artifact_0001.json"
    )


# ---------------------------------------------------------------------------
# 3. Duplicate across sessions
# ---------------------------------------------------------------------------


def test_duplicate_across_sessions(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "sess-a", (_ping("sess-a", "pA", "shared"),))
    _write_bundle(tmp_path, "sess-b", (_ping("sess-b", "pB", "shared"),))
    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 1
    assert result.duplicate_suppressed_count == 1
    # First occurrence by session_id ascending: sess-a is retained.
    assert result.retained_pings[0].session_id == "sess-a"
    duplicate = result.duplicate_pings[0]
    assert duplicate.session_id == "sess-b"
    assert duplicate.duplicate_of_session_id == "sess-a"


# ---------------------------------------------------------------------------
# 4. Distinct identities are all retained
# ---------------------------------------------------------------------------


def test_distinct_pings_all_retained(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        "sess-z",
        (
            _ping("sess-z", "p1", "dk-1"),
            _ping("sess-z", "p2", "dk-2"),
            _ping("sess-z", "p3", "dk-3"),
        ),
    )
    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 3
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 0


# ---------------------------------------------------------------------------
# 5. Missing ping identity -> INVALID_SUPPRESSED (never retained)
# ---------------------------------------------------------------------------


def test_identity_less_ping_is_invalid_suppressed(tmp_path: Path) -> None:
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-bad-id",
        "sess-bad-id",
        [
            {"ping_id": None, "dedupe_key": None},
            {"ping_id": "", "dedupe_key": ""},
        ],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 0
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 2
    for ping in result.invalid_pings:
        assert ping.dedupe_status == PING_DEDUPE_STATUS_INVALID_SUPPRESSED
        assert ping.suppress_reason == PING_SUPPRESS_REASON_MISSING_IDENTITY
    # An identity-less ping is NEVER retained.
    assert result.retained_pings == ()


# ---------------------------------------------------------------------------
# 6. No ping_id fallback: a missing dedupe_key is never retained (Major 1)
# ---------------------------------------------------------------------------


def test_no_ping_id_fallback_for_missing_dedupe_key(tmp_path: Path) -> None:
    # Pings carrying a ping_id but NO usable dedupe_key must NOT be retained
    # via a ping_id fallback: dedupe_key is the only retained identity.
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-no-dk",
        "sess-no-dk",
        [
            {"ping_id": "only-1", "dedupe_key": None},
            {"ping_id": "only-2", "dedupe_key": ""},
        ],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 0
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 2
    for ping in result.invalid_pings:
        assert ping.dedupe_status == PING_DEDUPE_STATUS_INVALID_SUPPRESSED
        assert ping.suppress_reason == PING_SUPPRESS_REASON_MISSING_IDENTITY
        assert ping.identity_kind != "ping_id"
    assert result.retained_pings == ()


# ---------------------------------------------------------------------------
# 6b. Member / manifest session_id integrity (Major 3)
# ---------------------------------------------------------------------------


def test_member_session_id_mismatch_is_invalid_suppressed(
    tmp_path: Path,
) -> None:
    # A ping whose own identity.session_id differs from the bundle/manifest
    # session_id has spoofed provenance: suppress it, never retain it.
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-real",
        "sess-real",
        [
            {
                "ping_id": "p1",
                "dedupe_key": "dk1",
                "session_id": "sess-OTHER",
            },
            {"ping_id": "p2", "dedupe_key": "dk2"},  # matches "sess-real"
        ],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 1
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 1
    invalid = result.invalid_pings[0]
    assert invalid.dedupe_status == PING_DEDUPE_STATUS_INVALID_SUPPRESSED
    assert invalid.suppress_reason == PING_SUPPRESS_REASON_SESSION_ID_MISMATCH
    # The matching ping is the one retained.
    assert result.retained_pings[0].ping_id == "p2"


def test_missing_member_session_id_is_invalid_suppressed(
    tmp_path: Path,
) -> None:
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-real2",
        "sess-real2",
        [{"ping_id": "p1", "dedupe_key": "dk1", "session_id": None}],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 0
    assert result.invalid_suppressed_count == 1
    assert (
        result.invalid_pings[0].suppress_reason
        == PING_SUPPRESS_REASON_SESSION_ID_MISMATCH
    )


def test_matching_member_session_id_is_retained(tmp_path: Path) -> None:
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-match",
        "sess-match",
        # session_id defaults to the bundle id -> matches.
        [{"ping_id": "p1", "dedupe_key": "dk1"}],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.retained_count == 1
    assert result.invalid_suppressed_count == 0


def test_mismatched_pings_not_counted_as_duplicates(
    tmp_path: Path,
) -> None:
    # Two pings share dedupe_key "dk1" but BOTH have a mismatched
    # session_id: they must be INVALID_SUPPRESSED, never a
    # retained+duplicate pair.
    session_dir = _raw_ping_bundle(
        tmp_path / "sess-real3",
        "sess-real3",
        [
            {"ping_id": "p1", "dedupe_key": "dk1", "session_id": "wrong"},
            {"ping_id": "p2", "dedupe_key": "dk1", "session_id": "wrong"},
        ],
    )
    result = build_compact_session_index(session_dirs=[str(session_dir)])
    assert result.retained_count == 0
    assert result.duplicate_suppressed_count == 0
    assert result.invalid_suppressed_count == 2
    for ping in result.invalid_pings:
        assert (
            ping.suppress_reason == PING_SUPPRESS_REASON_SESSION_ID_MISMATCH
        )


# ---------------------------------------------------------------------------
# 7. Fail closed on an invalid bundle directory
# ---------------------------------------------------------------------------


def test_build_fails_closed_on_missing_manifest(tmp_path: Path) -> None:
    bad_dir = tmp_path / "sess-no-manifest"
    bad_dir.mkdir()
    (bad_dir / "stray.json").write_text("{}", encoding="utf-8")
    result = build_compact_session_index(session_dirs=[str(bad_dir)])
    assert result.status == INDEX_BUILD_STATUS_READ_FAILED
    assert result.reason == INDEX_BUILD_REASON_BUNDLE_READ_FAILED
    assert result.blocked_session_dir == str(bad_dir)
    assert result.read_failure_reason == BUNDLE_READ_REASON_MISSING_MANIFEST
    assert result.sessions == ()
    assert result.retained_pings == ()


def test_one_bad_dir_fails_whole_build(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "sess-good", (_ping("sess-good", "p", "dk"),))
    bad_dir = tmp_path / "sess-bad"
    bad_dir.mkdir()  # no manifest
    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_READ_FAILED
    assert result.blocked_session_dir == str(bad_dir)


# ---------------------------------------------------------------------------
# 8. Determinism (independent of input / filesystem order)
# ---------------------------------------------------------------------------


def test_determinism_independent_of_input_order(tmp_path: Path) -> None:
    a = _write_bundle(
        tmp_path,
        "sess-a",
        (_ping("sess-a", "p1", "shared"), _ping("sess-a", "p2", "dk-a")),
    )
    b = _write_bundle(tmp_path, "sess-b", (_ping("sess-b", "p3", "shared"),))

    forward = build_compact_session_index(
        session_dirs=[str(a), str(b)]
    )
    reverse = build_compact_session_index(
        session_dirs=[str(b), str(a)]
    )
    by_root = build_compact_session_index(output_root=tmp_path)

    assert forward == reverse
    assert forward == by_root
    assert forward.retained_count == 2
    assert forward.duplicate_suppressed_count == 1


# ---------------------------------------------------------------------------
# 9. Input validation
# ---------------------------------------------------------------------------


def test_no_source_is_invalid_input(tmp_path: Path) -> None:
    result = build_compact_session_index()
    assert result.status == INDEX_BUILD_STATUS_INVALID_INPUT
    assert result.reason == INDEX_BUILD_REASON_NO_SOURCE


def test_ambiguous_source_is_invalid_input(tmp_path: Path) -> None:
    result = build_compact_session_index(
        session_dirs=[str(tmp_path)], output_root=str(tmp_path)
    )
    assert result.status == INDEX_BUILD_STATUS_INVALID_INPUT
    assert result.reason == INDEX_BUILD_REASON_AMBIGUOUS_SOURCE


def test_bad_session_dirs_type_is_invalid_input(tmp_path: Path) -> None:
    for bad in ("a-string-not-a-list", 123, {"x": 1}):
        result = build_compact_session_index(session_dirs=bad)
        assert result.status == INDEX_BUILD_STATUS_INVALID_INPUT
        assert result.reason == INDEX_BUILD_REASON_INVALID_SESSION_DIRS


def test_bad_session_dirs_element_is_invalid_input(tmp_path: Path) -> None:
    result = build_compact_session_index(session_dirs=[123, None])
    assert result.status == INDEX_BUILD_STATUS_INVALID_INPUT
    assert result.reason == INDEX_BUILD_REASON_INVALID_SESSION_DIRS


def test_bad_output_root_is_invalid_input(tmp_path: Path) -> None:
    result = build_compact_session_index(
        output_root=str(tmp_path / "does-not-exist")
    )
    assert result.status == INDEX_BUILD_STATUS_INVALID_INPUT
    assert result.reason == INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT


def test_empty_source_is_empty(tmp_path: Path) -> None:
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    by_root = build_compact_session_index(output_root=empty_root)
    assert by_root.status == INDEX_BUILD_STATUS_EMPTY
    assert by_root.reason == INDEX_BUILD_REASON_EMPTY
    by_list = build_compact_session_index(session_dirs=[])
    assert by_list.status == INDEX_BUILD_STATUS_EMPTY


# ---------------------------------------------------------------------------
# 10. output_root skips hidden transient dirs
# ---------------------------------------------------------------------------


def test_output_root_skips_hidden_dirs(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "sess-a", (_ping("sess-a", "p", "dk"),))
    # A leftover hidden transient dir (writer ``.staging`` / ``.previous``
    # style) carrying junk must be ignored, not fail the build.
    hidden = tmp_path / ".sess-a.staging.0"
    hidden.mkdir()
    (hidden / "junk.txt").write_text("junk", encoding="utf-8")
    result = build_compact_session_index(output_root=tmp_path)
    assert result.status == INDEX_BUILD_STATUS_BUILT
    assert result.session_count == 1
    assert result.sessions[0].session_id == "sess-a"


# ---------------------------------------------------------------------------
# 11. Per-session record counts
# ---------------------------------------------------------------------------


def test_per_session_counts(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        "sess-counts",
        (
            _ping("sess-counts", "p1", "k1"),
            _ping("sess-counts", "p2", "k1"),  # dup of p1
            _ping("sess-counts", "p3", "k2"),
        ),
    )
    result = build_compact_session_index(output_root=tmp_path)
    record = result.sessions[0]
    assert record.ping_artifact_count == 3
    assert record.retained_ping_count == 2
    assert record.duplicate_suppressed_ping_count == 1
    assert record.invalid_suppressed_ping_count == 0
    assert len(record.pings) == 3


# ---------------------------------------------------------------------------
# 12. The builder writes nothing
# ---------------------------------------------------------------------------


def test_builder_writes_nothing(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "sess-a", (_ping("sess-a", "p1", "dk-1"),))
    _write_bundle(tmp_path, "sess-b", (_ping("sess-b", "p2", "dk-2"),))
    before = _snapshot_tree(tmp_path)
    build_compact_session_index(output_root=tmp_path)
    after = _snapshot_tree(tmp_path)
    assert before == after
