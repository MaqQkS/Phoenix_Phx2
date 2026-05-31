"""Stage 30.8.3 offline manifest-backed bundle reader tests.

Pure offline unit tests for the Stage 30.8.3 reader. Every test reads ONLY
from the pytest ``tmp_path`` temporary directory (out-of-repo); no live
calls, no env reads, no Discord, no provider, no database / SQLite / zstd.
Happy-path bundles are produced by the real Stage 30.8.2 writer; the
fail-closed cases hand-craft / mutate raw bundle directories.

Pinned contract: the reader is manifest-backed and fail-closed -- it
requires ``manifest.json`` (the commit marker), reads only the manifest's
listed member files, and refuses a missing / malformed / wrong-schema
manifest, a malformed ``member_files`` list, an unsafe / escaping member
filename, a missing member file, an incomplete bundle, a loose / non-file
entry, and malformed member JSON. It returns a passive result and never
raises; it writes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
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
    BUNDLE_READ_REASON_INCOMPLETE_BUNDLE,
    BUNDLE_READ_REASON_INVALID_SESSION_DIR,
    BUNDLE_READ_REASON_LOOSE_FILE,
    BUNDLE_READ_REASON_MALFORMED_MANIFEST,
    BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON,
    BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE,
    BUNDLE_READ_REASON_MEMBER_FILES_INVALID,
    BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE,
    BUNDLE_READ_REASON_MISSING_MANIFEST,
    BUNDLE_READ_REASON_MISSING_MEMBER_FILE,
    BUNDLE_READ_REASON_OK,
    BUNDLE_READ_REASON_SYMLINK_REJECTED,
    BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA,
    BUNDLE_READ_STATUS_INVALID,
    BUNDLE_READ_STATUS_READ,
    EXPECTED_BUNDLE_SCHEMA_VERSION,
    MANIFEST_FILENAME,
    VALIDATION_RESULT_FILENAME,
    read_compact_session_bundle,
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


def _write_valid_bundle(
    out_dir: Path, session_id: str = "sess-1", n_pings: int = 2
) -> Path:
    """Write a valid bundle via the real Stage 30.8.2 writer; return the
    session directory.
    """
    pings = tuple(
        _ping(session_id, f"ping-{i}", f"dk-{i}") for i in range(n_pings)
    )
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id=session_id, ping_artifacts=pings
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_WRITTEN
    return out_dir / session_id


def _raw_bundle(
    session_dir: Path,
    manifest: object,
    members: dict,
    *,
    write_validation: bool = True,
) -> None:
    """Hand-write a raw bundle dir: ``manifest.json`` (``manifest`` dumped),
    optionally ``validation_result.json``, and each ``members`` entry
    (name -> raw text). Full control for the fail-closed cases.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    if write_validation:
        (session_dir / VALIDATION_RESULT_FILENAME).write_text(
            json.dumps({"validation_status": "VALID"}), encoding="utf-8"
        )
    for name, text in members.items():
        (session_dir / name).write_text(text, encoding="utf-8")


def _manifest(session_id: str, member_files: object) -> dict:
    return {
        "bundle_schema_version": EXPECTED_BUNDLE_SCHEMA_VERSION,
        "session_id": session_id,
        "member_files": member_files,
    }


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_reads_valid_bundle(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-1", n_pings=2)
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_READ
    assert result.reason == BUNDLE_READ_REASON_OK
    assert result.session_id == "sess-1"
    assert result.bundle_schema_version == EXPECTED_BUNDLE_SCHEMA_VERSION
    assert result.member_count == 2
    # Members are in sorted manifest order, never filesystem order.
    assert [m.filename for m in result.members] == [
        "ping_artifact_0001.json",
        "ping_artifact_0002.json",
    ]
    for member in result.members:
        assert member.member_kind == ARTIFACT_KIND_COMPACT_PING_ARTIFACT
        assert isinstance(member.payload, dict)
    assert result.blocked_file is None


def test_accepts_str_and_path(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-2", n_pings=1)
    by_path = read_compact_session_bundle(session_dir)
    by_str = read_compact_session_bundle(str(session_dir))
    assert by_path.status == BUNDLE_READ_STATUS_READ
    assert by_str.status == BUNDLE_READ_STATUS_READ
    assert by_path == by_str


# ---------------------------------------------------------------------------
# 2. Invalid session-dir input
# ---------------------------------------------------------------------------


def test_invalid_session_dir_inputs(tmp_path: Path) -> None:
    for bad in (None, "", ".", 123, b"x", object()):
        result = read_compact_session_bundle(bad)
        assert result.status == BUNDLE_READ_STATUS_INVALID
        assert result.reason == BUNDLE_READ_REASON_INVALID_SESSION_DIR


def test_nonexistent_dir_fails_closed(tmp_path: Path) -> None:
    result = read_compact_session_bundle(tmp_path / "nope")
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_INVALID_SESSION_DIR


def test_file_not_dir_fails_closed(tmp_path: Path) -> None:
    a_file = tmp_path / "afile"
    a_file.write_text("x", encoding="utf-8")
    result = read_compact_session_bundle(a_file)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_INVALID_SESSION_DIR


# ---------------------------------------------------------------------------
# 3. Missing / malformed / wrong-schema manifest
# ---------------------------------------------------------------------------


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-3")
    (session_dir / MANIFEST_FILENAME).unlink()
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MISSING_MANIFEST


def test_malformed_manifest_json_fails_closed(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-4")
    (session_dir / MANIFEST_FILENAME).write_text(
        "{ not valid json", encoding="utf-8"
    )
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MALFORMED_MANIFEST


def test_manifest_not_object_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-arr"
    session_dir.mkdir()
    (session_dir / MANIFEST_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MALFORMED_MANIFEST


def test_wrong_bundle_schema_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-5"
    manifest = _manifest("sess-5", [])
    manifest["bundle_schema_version"] = "some_other_schema_v9"
    _raw_bundle(session_dir, manifest, {})
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA


# ---------------------------------------------------------------------------
# 4. Malformed member_files list
# ---------------------------------------------------------------------------


def test_member_files_not_a_list_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-6"
    _raw_bundle(session_dir, _manifest("sess-6", "not-a-list"), {})
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MEMBER_FILES_INVALID


def test_member_files_non_string_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-7"
    _raw_bundle(session_dir, _manifest("sess-7", ["a.json", 7]), {})
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MEMBER_FILES_INVALID


def test_member_files_duplicate_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-dup"
    _raw_bundle(
        session_dir,
        _manifest("sess-dup", ["a.json", "a.json"]),
        {"a.json": json.dumps({"identity": {}})},
    )
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MEMBER_FILES_INVALID


# ---------------------------------------------------------------------------
# 5. Member path safety: missing / unsafe / escaping
# ---------------------------------------------------------------------------


def test_manifest_references_missing_file_fails_closed(
    tmp_path: Path,
) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-8", n_pings=2)
    # Delete a listed member file but leave it referenced by the manifest.
    (session_dir / "ping_artifact_0002.json").unlink()
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MISSING_MEMBER_FILE
    assert result.blocked_file == "ping_artifact_0002.json"


def test_member_filename_unsafe_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-9"
    _raw_bundle(
        session_dir,
        _manifest("sess-9", ["sub/dir.json"]),
        {},
    )
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE
    assert result.blocked_file == "sub/dir.json"


def test_member_path_escape_fails_closed(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-10"
    # An escaping reference: ".." is caught by the safe-component gate.
    _raw_bundle(session_dir, _manifest("sess-10", ["../escape.json"]), {})
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason in (
        BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE,
        BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE,
    )
    assert result.blocked_file == "../escape.json"


# ---------------------------------------------------------------------------
# 6. Loose / incomplete / non-file entries
# ---------------------------------------------------------------------------


def test_loose_unlisted_file_fails_closed(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-11", n_pings=1)
    (session_dir / "loose_extra.json").write_text("{}", encoding="utf-8")
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_LOOSE_FILE
    assert result.blocked_file == "loose_extra.json"


def test_incomplete_bundle_missing_validation_fails_closed(
    tmp_path: Path,
) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-12", n_pings=1)
    (session_dir / VALIDATION_RESULT_FILENAME).unlink()
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_INCOMPLETE_BUNDLE


def test_subdirectory_entry_fails_closed(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-13", n_pings=1)
    (session_dir / "nested_subdir").mkdir()
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_LOOSE_FILE


# ---------------------------------------------------------------------------
# 7. Malformed member JSON
# ---------------------------------------------------------------------------


def test_malformed_member_json_fails_closed(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-14", n_pings=2)
    (session_dir / "ping_artifact_0001.json").write_text(
        "{ broken", encoding="utf-8"
    )
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON
    assert result.blocked_file == "ping_artifact_0001.json"


# ---------------------------------------------------------------------------
# 8. Empty member set is consistent (no member files)
# ---------------------------------------------------------------------------


def test_empty_member_set_reads(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-empty"
    _raw_bundle(session_dir, _manifest("sess-empty", []), {})
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_READ
    assert result.member_count == 0


# ---------------------------------------------------------------------------
# 9. Determinism + read-only
# ---------------------------------------------------------------------------


def test_read_is_deterministic(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-15", n_pings=3)
    first = read_compact_session_bundle(session_dir)
    second = read_compact_session_bundle(session_dir)
    assert first == second


def test_read_mutates_nothing(tmp_path: Path) -> None:
    session_dir = _write_valid_bundle(tmp_path, "sess-16", n_pings=2)
    before = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(session_dir.iterdir())
    }
    read_compact_session_bundle(session_dir)
    after = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(session_dir.iterdir())
    }
    assert before == after


# ---------------------------------------------------------------------------
# 10. Symlink rejection BEFORE any read (Major 2)
# ---------------------------------------------------------------------------


def _symlink_or_skip(
    link: Path, target: Path, *, target_is_directory: bool = False
) -> None:
    """Create a symlink, or skip the test when the platform / privilege
    does not permit symlink creation (e.g. Windows without Developer Mode,
    WinError 1314). The reader's symlink-rejection code is exercised on any
    runner where symlinks can be created.
    """
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"symlinks not supported here: {exc!r}")


def test_symlinked_session_dir_rejected(tmp_path: Path) -> None:
    real = _write_valid_bundle(tmp_path / "real", "sess-sl1", n_pings=1)
    link = tmp_path / "linked_session"
    _symlink_or_skip(link, real, target_is_directory=True)
    result = read_compact_session_bundle(link)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_SYMLINK_REJECTED
    assert result.member_count == 0


def test_symlinked_manifest_rejected_without_following(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "sess-sl2"
    session_dir.mkdir()
    (session_dir / VALIDATION_RESULT_FILENAME).write_text(
        json.dumps({"validation_status": "VALID"}), encoding="utf-8"
    )
    # A VALID manifest placed elsewhere: if the reader FOLLOWED the symlink
    # it would parse it and could proceed -- it must not.
    target = tmp_path / "real_manifest.json"
    target.write_text(
        json.dumps(_manifest("sess-sl2", [])), encoding="utf-8"
    )
    _symlink_or_skip(session_dir / MANIFEST_FILENAME, target)
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_SYMLINK_REJECTED
    # Proof the symlink target was NOT followed: no members were read.
    assert result.member_count == 0


def test_symlinked_member_file_rejected(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess-sl3"
    _raw_bundle(
        session_dir,
        _manifest("sess-sl3", ["ping_artifact_0001.json"]),
        {},
    )
    # The member is a symlink to an in-dir file (resolves under the session
    # dir, so it is caught as a symlink during enumeration, not as escape).
    _symlink_or_skip(
        session_dir / "ping_artifact_0001.json",
        session_dir / VALIDATION_RESULT_FILENAME,
    )
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason == BUNDLE_READ_REASON_SYMLINK_REJECTED


def test_symlink_escape_outside_session_dir_rejected(
    tmp_path: Path,
) -> None:
    # A member symlink whose target is OUTSIDE the session dir is rejected
    # (as a symlink or as a path escape) before the outside target is read.
    outside = tmp_path / "outside_secret.json"
    outside.write_text(
        json.dumps({"identity": {"artifact_kind": "compact_ping_artifact"}}),
        encoding="utf-8",
    )
    session_dir = tmp_path / "sess-sl4"
    _raw_bundle(
        session_dir,
        _manifest("sess-sl4", ["ping_artifact_0001.json"]),
        {},
    )
    _symlink_or_skip(session_dir / "ping_artifact_0001.json", outside)
    result = read_compact_session_bundle(session_dir)
    assert result.status == BUNDLE_READ_STATUS_INVALID
    assert result.reason in (
        BUNDLE_READ_REASON_SYMLINK_REJECTED,
        BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE,
    )
    assert result.member_count == 0
