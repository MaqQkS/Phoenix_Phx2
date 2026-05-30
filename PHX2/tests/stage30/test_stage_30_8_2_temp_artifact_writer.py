"""Stage 30.8.2 temp-dir compact session artifact writer tests.

Pure offline unit tests for the Stage 30.8.2 writer. Every test writes
ONLY into the pytest ``tmp_path`` temporary directory (out-of-repo); no
live calls, no env reads, no real bot artifact directory, no Discord, no
provider, no database / SQLite / zstd.

Pinned contract:

  * a valid bundle writes its artifact JSON + validation_result.json +
    manifest.json under ``output_dir/<session_id>/`` and reports WRITTEN
    / safe_to_persist with the written paths under ``output_dir``;
  * an invalid / non-model member is NOT persisted (fail closed) and
    nothing is written;
  * a malicious / unsafe ``session_id`` fails closed and nothing escapes
    ``output_dir``;
  * the persisted JSON is deterministic (same input -> identical bytes,
    no absolute path / wall-clock leakage);
  * rewriting the same bundle leaves valid (not partial) JSON and no
    leftover temp file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import PHX2.stage30.stage30_8_temp_artifact_writer as writer_module
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
    content_snapshot_field_names,
    identity_field_names,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
    Stage30_8CompactStorageBudgetSnapshotArtifact,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    ARTIFACT_FILENAME_SUFFIX,
    MANIFEST_FILENAME,
    PREVIOUS_DIR_INFIX,
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
    STAGING_DIR_INFIX,
    VALIDATION_RESULT_FILENAME,
    WRITE_REASON_EMPTY_BUNDLE,
    WRITE_REASON_INVALID_ARTIFACT,
    WRITE_REASON_INVALID_ARTIFACT_TYPE,
    WRITE_REASON_INVALID_BUNDLE_TYPE,
    WRITE_REASON_INVALID_OUTPUT_DIR,
    WRITE_REASON_INVALID_SESSION_ID,
    WRITE_REASON_OK,
    WRITE_STATUS_INVALID,
    WRITE_STATUS_WRITE_FAILED,
    WRITE_STATUS_WRITTEN,
    Stage30_8CompactSessionArtifactBundle,
    write_compact_session_artifact_bundle,
)


# ---------------------------------------------------------------------------
# Builders (valid records; fixed values -> deterministic)
# ---------------------------------------------------------------------------


def _identity(**overrides: object) -> Stage30_8CompactArtifactIdentity:
    kwargs = dict(
        run_id="run-001",
        session_id="sess-001",
        ping_id="ping-001",
        candidate_id="cand-001",
        token_mint="So11111111111111111111111111111111111111112",
        provider_event_id="evt-001",
        normalized_event_id="norm-001",
        observed_at_utc="2026-05-29T00:00:00Z",
        artifact_created_at_utc="2026-05-29T00:00:01Z",
        artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
        dedupe_key="dedupe-abc",
        compact_ping_schema_version="stage30_2_v0_compact_ping",
    )
    kwargs.update(overrides)
    return Stage30_8CompactArtifactIdentity(**kwargs)  # type: ignore[arg-type]


def _content(**overrides: object) -> Stage30_8CompactContentSnapshot:
    kwargs = dict(
        compact_body_text="PHOENIX compact | MC: $83k | ATH: $120k",
        mc_display="$83k",
        lp_display="$12k",
        net_display="+$4k buys",
        ath_display="$120k",
        migration_display="Known",
        decision_status="ELIGIBLE",
        eligibility_status="ELIGIBLE",
        warning_codes=("PRICE_DEGRADED_NONE",),
        reason_codes=("TIER_3_IN_BAND",),
        terminal_outcome_code="DISPATCHED",
        sanitized_transport_status="OK_200",
    )
    kwargs.update(overrides)
    return Stage30_8CompactContentSnapshot(**kwargs)  # type: ignore[arg-type]


def _ping(**overrides: object) -> Stage30_8CompactPingArtifact:
    identity = overrides.pop(
        "identity",
        _identity(artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT),
    )
    content = overrides.pop("content", _content())
    return Stage30_8CompactPingArtifact(
        identity=identity, content=content  # type: ignore[arg-type]
    )


def _budget(**overrides: object) -> (
    Stage30_8CompactStorageBudgetSnapshotArtifact
):
    kwargs = dict(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
            ping_id=None,
        ),
        budget_status="OK",
        raw_bytes_written=1024,
        durable_rows_written=10,
        archived_compressed_bytes=128,
        dropped_count=0,
        pruned_count=0,
        sealed_count=1,
        dedupe_suppressed_count=2,
        disk_usage_percent_before=40.0,
        disk_usage_percent_after=41.0,
    )
    kwargs.update(overrides)
    return Stage30_8CompactStorageBudgetSnapshotArtifact(
        **kwargs  # type: ignore[arg-type]
    )


def _session_summary(**overrides: object) -> (
    Stage30_8CompactSessionSummaryArtifact
):
    kwargs = dict(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
            ping_id=None,
        ),
        pings_emitted=2,
        dispatch_attempts=3,
        dedupe_suppressed=1,
        errors=0,
        storage_budget=_budget(),
    )
    kwargs.update(overrides)
    return Stage30_8CompactSessionSummaryArtifact(
        **kwargs  # type: ignore[arg-type]
    )


def _dispatch(**overrides: object) -> (
    Stage30_8CompactDispatchAttemptArtifact
):
    kwargs = dict(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
        ),
        sanitized_transport_status="OK_200",
        attempt_index=0,
    )
    kwargs.update(overrides)
    return Stage30_8CompactDispatchAttemptArtifact(
        **kwargs  # type: ignore[arg-type]
    )


def _error(**overrides: object) -> Stage30_8CompactErrorArtifact:
    kwargs = dict(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
        ),
        error_reason_code="ADAPTER_CALLER_SHAPE_ERROR",
    )
    kwargs.update(overrides)
    return Stage30_8CompactErrorArtifact(**kwargs)  # type: ignore[arg-type]


def _full_bundle(session_id: str = "sess-001") -> (
    Stage30_8CompactSessionArtifactBundle
):
    """A bundle exercising every member kind (2 pings)."""
    return Stage30_8CompactSessionArtifactBundle(
        session_id=session_id,
        session_summary=_session_summary(),
        ping_artifacts=(_ping(), _ping()),
        dispatch_attempt_artifacts=(_dispatch(),),
        error_artifacts=(_error(),),
        storage_budget_snapshot=_budget(),
    )


def _files_under(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# 1. Happy path -> WRITTEN bundle under output_dir
# ---------------------------------------------------------------------------


def test_happy_path_single_ping_writes_bundle(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-001", ping_artifacts=(_ping(),)
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)

    assert result.status == WRITE_STATUS_WRITTEN
    assert result.reason == WRITE_REASON_OK
    assert result.validation_status == "VALID"
    assert result.safe_to_persist is True
    assert result.artifact_count == 1

    session_dir = Path(result.session_dir)
    assert session_dir == (out_dir / "sess-001")
    names = {p.name for p in session_dir.iterdir() if p.is_file()}
    assert names == {
        "ping_artifact_0001.json",
        VALIDATION_RESULT_FILENAME,
        MANIFEST_FILENAME,
    }
    # Every file parses as JSON.
    for path in session_dir.iterdir():
        json.loads(path.read_text(encoding="utf-8"))
    # The written paths are reported and live strictly under output_dir.
    assert result.written_paths
    for path_str in result.written_paths:
        assert Path(path_str).resolve().is_relative_to(out_dir.resolve())
    assert session_dir.resolve().is_relative_to(out_dir.resolve())


def test_happy_path_full_bundle_writes_every_member(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = _full_bundle()
    result = write_compact_session_artifact_bundle(out_dir, bundle)

    assert result.status == WRITE_STATUS_WRITTEN
    assert result.artifact_count == 6  # summary + 2 pings + dispatch + error + budget

    session_dir = Path(result.session_dir)
    names = {p.name for p in session_dir.iterdir() if p.is_file()}
    assert names == {
        "session_summary.json",
        "ping_artifact_0001.json",
        "ping_artifact_0002.json",
        "dispatch_attempt_0001.json",
        "error_artifact_0001.json",
        "storage_budget_snapshot.json",
        VALIDATION_RESULT_FILENAME,
        MANIFEST_FILENAME,
    }


def test_written_ping_artifact_json_roundtrips_identity(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-001", ping_artifacts=(_ping(),)
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    session_dir = Path(result.session_dir)

    payload = json.loads(
        (session_dir / "ping_artifact_0001.json").read_text(encoding="utf-8")
    )
    assert payload["identity"]["session_id"] == "sess-001"
    assert payload["identity"]["stage_id"] == "stage30_8"
    assert payload["content"]["mc_display"] == "$83k"
    # codes tuples become JSON arrays.
    assert payload["content"]["warning_codes"] == ["PRICE_DEGRADED_NONE"]


def test_manifest_and_validation_result_payloads(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = _full_bundle()
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    session_dir = Path(result.session_dir)

    manifest = json.loads(
        (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert manifest["bundle_schema_version"] == STAGE30_8_2_BUNDLE_SCHEMA_VERSION
    assert manifest["session_id"] == "sess-001"
    assert manifest["artifact_stage_id"] == "stage30_8"
    assert manifest["counts"] == {
        "session_summary": 1,
        "ping_artifacts": 2,
        "dispatch_attempt_artifacts": 1,
        "error_artifacts": 1,
        "storage_budget_snapshot": 1,
    }
    # member_files lists the 6 artifact files (not the manifest / validation).
    assert MANIFEST_FILENAME not in manifest["member_files"]
    assert VALIDATION_RESULT_FILENAME not in manifest["member_files"]
    assert len(manifest["member_files"]) == 6

    validation = json.loads(
        (session_dir / VALIDATION_RESULT_FILENAME).read_text(encoding="utf-8")
    )
    assert validation["validation_status"] == "VALID"
    assert validation["safe_to_persist"] is True
    assert len(validation["members"]) == 6
    for member in validation["members"]:
        assert member["validation_status"] == "VALID"


# ---------------------------------------------------------------------------
# 2. Invalid content / member does not persist (fail closed)
# ---------------------------------------------------------------------------


_MALFORMED_MEMBERS = (
    None,
    object(),
    123,
    "a string",
    [1, 2, 3],
    {},
    {"mc_display": 123},
)


def test_malformed_ping_member_type_not_persisted(tmp_path: Path) -> None:
    # A non-model element in ping_artifacts fails the writer's type gate;
    # nothing is written. (``None`` is skipped here -- it means "absent"
    # only at the top-level optional fields, never inside a sequence.)
    for index, bad in enumerate(_MALFORMED_MEMBERS):
        out_dir = tmp_path / f"out-{index}"
        bundle = Stage30_8CompactSessionArtifactBundle(
            session_id="sess-bad", ping_artifacts=(bad,)
        )
        result = write_compact_session_artifact_bundle(out_dir, bundle)
        assert result.status == WRITE_STATUS_INVALID, bad
        assert result.safe_to_persist is False
        assert result.reason == WRITE_REASON_INVALID_ARTIFACT_TYPE
        assert _files_under(out_dir) == []


def test_malformed_top_level_member_type_not_persisted(tmp_path: Path) -> None:
    # ``None`` at a top-level optional field means "absent", so it is
    # excluded here (a None-only bundle is an EMPTY_BUNDLE, covered
    # separately). Every other non-model value fails the writer type gate.
    for index, bad in enumerate(m for m in _MALFORMED_MEMBERS if m is not None):
        out_dir = tmp_path / f"out-summary-{index}"
        bundle = Stage30_8CompactSessionArtifactBundle(
            session_id="sess-bad", session_summary=bad
        )
        result = write_compact_session_artifact_bundle(out_dir, bundle)
        assert result.status == WRITE_STATUS_INVALID, bad
        assert result.safe_to_persist is False
        assert result.reason == WRITE_REASON_INVALID_ARTIFACT_TYPE
        assert result.blocked_field == "session_summary"
        assert _files_under(out_dir) == []


def test_ping_with_bad_content_value_not_persisted(tmp_path: Path) -> None:
    # A real ping artifact whose content carries a non-string display
    # field fails Stage 30.8.1 validation; nothing is written.
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-bad",
        ping_artifacts=(_ping(content=_content(mc_display=123)),),
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_INVALID
    assert result.safe_to_persist is False
    assert result.reason == WRITE_REASON_INVALID_ARTIFACT
    assert result.validation_reason == "DISPLAY_FIELD_NOT_STRING"
    assert result.blocked_field == "mc_display"
    assert _files_under(out_dir) == []


def test_ping_with_dict_content_not_persisted(tmp_path: Path) -> None:
    # A bare dict is NOT an accepted content snapshot input.
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-bad",
        ping_artifacts=(
            Stage30_8CompactPingArtifact(
                identity=_identity(
                    artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT
                ),
                content={"mc_display": 123},  # type: ignore[arg-type]
            ),
        ),
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_INVALID
    assert result.safe_to_persist is False
    assert result.reason == WRITE_REASON_INVALID_ARTIFACT
    # A bare dict in the ping's ``content`` field is caught by the
    # ping-level field scan as a nested raw payload (fail closed).
    assert result.validation_reason == "NESTED_RAW_PAYLOAD"
    assert result.blocked_field == "content"
    assert _files_under(out_dir) == []


def test_invalid_ping_identity_not_persisted(tmp_path: Path) -> None:
    # Missing required identity axis -> INVALID, nothing written.
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-bad",
        ping_artifacts=(_ping(identity=_identity(run_id="")),),
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_INVALID
    assert result.reason == WRITE_REASON_INVALID_ARTIFACT
    assert result.validation_reason == "MISSING_REQUIRED_IDENTITY"
    assert _files_under(out_dir) == []


# ---------------------------------------------------------------------------
# 3. Invalid bundle / output dir / empty bundle
# ---------------------------------------------------------------------------


def test_non_bundle_input_is_invalid(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    for bad in (None, object(), 123, "a string", [1, 2, 3], {}):
        result = write_compact_session_artifact_bundle(out_dir, bad)
        assert result.status == WRITE_STATUS_INVALID
        assert result.reason == WRITE_REASON_INVALID_BUNDLE_TYPE
        assert result.safe_to_persist is False
    assert _files_under(out_dir) == []


def test_invalid_output_dir_is_invalid(tmp_path: Path) -> None:
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-001", ping_artifacts=(_ping(),)
    )
    for bad_dir in (None, 123, b"bytes", "", "."):
        result = write_compact_session_artifact_bundle(bad_dir, bundle)
        assert result.status == WRITE_STATUS_INVALID
        assert result.reason == WRITE_REASON_INVALID_OUTPUT_DIR
        assert result.safe_to_persist is False


def test_empty_bundle_is_invalid(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = Stage30_8CompactSessionArtifactBundle(session_id="sess-001")
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_INVALID
    assert result.reason == WRITE_REASON_EMPTY_BUNDLE
    assert _files_under(out_dir) == []


# ---------------------------------------------------------------------------
# 4. Path containment: malicious session_id never escapes output_dir
# ---------------------------------------------------------------------------


_UNSAFE_SESSION_IDS = (
    "../evil",
    "..",
    ".",
    "",
    "   ",
    "\t\n",
    "a b",
    "a/b",
    "a\\b",
    "/abs/evil",
    "C:evil",
    "with:colon",
    "with\x00nul",
    "....//x",
)


def test_unsafe_session_id_fails_closed(tmp_path: Path) -> None:
    base = tmp_path / "containment"
    out_dir = base / "out"
    out_dir.mkdir(parents=True)
    for bad_sid in _UNSAFE_SESSION_IDS:
        bundle = Stage30_8CompactSessionArtifactBundle(
            session_id=bad_sid, ping_artifacts=(_ping(),)
        )
        result = write_compact_session_artifact_bundle(out_dir, bundle)
        assert result.status == WRITE_STATUS_INVALID, repr(bad_sid)
        assert result.reason == WRITE_REASON_INVALID_SESSION_ID, repr(bad_sid)
        assert result.safe_to_persist is False
    # Nothing was written inside output_dir, and nothing escaped to the
    # parent (no sibling "evil" directory was created).
    assert _files_under(out_dir) == []
    assert not (base / "evil").exists()
    assert _files_under(base) == []


# ---------------------------------------------------------------------------
# 5. Deterministic output (no absolute-path / clock leakage)
# ---------------------------------------------------------------------------


def test_same_bundle_two_dirs_produces_identical_bytes(tmp_path: Path) -> None:
    bundle = _full_bundle()
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    result_a = write_compact_session_artifact_bundle(out_a, bundle)
    result_b = write_compact_session_artifact_bundle(out_b, bundle)
    assert result_a.status == WRITE_STATUS_WRITTEN
    assert result_b.status == WRITE_STATUS_WRITTEN

    session_a = Path(result_a.session_dir)
    session_b = Path(result_b.session_dir)
    member_names = sorted(p.name for p in session_a.iterdir() if p.is_file())
    assert member_names == sorted(
        p.name for p in session_b.iterdir() if p.is_file()
    )
    for name in member_names:
        assert (session_a / name).read_bytes() == (
            session_b / name
        ).read_bytes(), name


def test_persisted_json_carries_no_absolute_path(tmp_path: Path) -> None:
    out_dir = tmp_path / "deep" / "nested" / "out"
    bundle = _full_bundle()
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    session_dir = Path(result.session_dir)
    needle = str(out_dir)
    for path in session_dir.iterdir():
        assert needle not in path.read_text(encoding="utf-8"), path.name


# ---------------------------------------------------------------------------
# 6. Atomic-ish rewrite: rewriting leaves valid (not partial) JSON
# ---------------------------------------------------------------------------


def test_rewrite_same_bundle_leaves_valid_json(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    bundle = _full_bundle()

    first = write_compact_session_artifact_bundle(out_dir, bundle)
    assert first.status == WRITE_STATUS_WRITTEN
    session_dir = Path(first.session_dir)
    first_manifest = (session_dir / MANIFEST_FILENAME).read_bytes()

    second = write_compact_session_artifact_bundle(out_dir, bundle)
    assert second.status == WRITE_STATUS_WRITTEN
    second_manifest = (session_dir / MANIFEST_FILENAME).read_bytes()

    assert first_manifest == second_manifest
    # Every file still parses (no partial / corrupt content).
    for path in session_dir.iterdir():
        if path.suffix == ARTIFACT_FILENAME_SUFFIX:
            json.loads(path.read_text(encoding="utf-8"))
    # No leftover temp files.
    assert not [p for p in session_dir.iterdir() if p.name.endswith(".tmp")]


# ---------------------------------------------------------------------------
# 7. Result is deterministic for a fixed input
# ---------------------------------------------------------------------------


def test_writer_result_is_deterministic(tmp_path: Path) -> None:
    bundle = _full_bundle()
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    result_a = write_compact_session_artifact_bundle(out_a, bundle)
    result_b = write_compact_session_artifact_bundle(out_b, bundle)
    # Path-independent fields match.
    assert result_a.status == result_b.status
    assert result_a.reason == result_b.reason
    assert result_a.validation_status == result_b.validation_status
    assert result_a.artifact_count == result_b.artifact_count


def _single_ping_bundle(session_id: str = "sess-001") -> (
    Stage30_8CompactSessionArtifactBundle
):
    return Stage30_8CompactSessionArtifactBundle(
        session_id=session_id, ping_artifacts=(_ping(),)
    )


def _hidden_transient_dirs(out_dir: Path) -> List[str]:
    if not out_dir.exists():
        return []
    return [
        entry.name
        for entry in out_dir.iterdir()
        if entry.is_dir()
        and (
            STAGING_DIR_INFIX in entry.name
            or PREVIOUS_DIR_INFIX in entry.name
        )
    ]


# ---------------------------------------------------------------------------
# 8. Exact-type gate: a subclass with an extra field cannot leak
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _EvilPingArtifact(Stage30_8CompactPingArtifact):
    extra_path: str = "C:/tmp/leaked_abs_path"


@dataclass(frozen=True)
class _EvilIdentity(Stage30_8CompactArtifactIdentity):
    extra_path: str = "C:/tmp/leaked_nested_abs_path"


def test_subclass_member_with_extra_field_is_rejected(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    evil = _EvilPingArtifact(
        identity=_identity(artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT),
        content=_content(),
    )
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-001", ping_artifacts=(evil,)
    )
    result = write_compact_session_artifact_bundle(out_dir, bundle)
    assert result.status == WRITE_STATUS_INVALID
    assert result.reason == WRITE_REASON_INVALID_ARTIFACT_TYPE
    assert result.safe_to_persist is False
    assert result.blocked_field == "ping_artifacts"
    # Nothing written, and the extra field is nowhere on disk.
    assert _files_under(out_dir) == []
    for path in _files_under(out_dir):
        assert "leaked_abs_path" not in path.read_text(encoding="utf-8")


def test_nested_subclass_extra_field_never_persisted(tmp_path: Path) -> None:
    # An exact ping whose nested identity is a subclass with an extra
    # field: serialization projects only the canonical identity fields, so
    # the extra value can never reach disk -- regardless of outcome.
    out_dir = tmp_path / "out"
    ping = Stage30_8CompactPingArtifact(
        identity=_EvilIdentity(
            run_id="run-001",
            session_id="sess-001",
            ping_id="ping-001",
            artifact_created_at_utc="2026-05-29T00:00:01Z",
            artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            dedupe_key="dedupe-abc",
        ),
        content=_content(),
    )
    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id="sess-001", ping_artifacts=(ping,)
    )
    write_compact_session_artifact_bundle(out_dir, bundle)
    for path in _files_under(out_dir):
        assert "leaked_nested_abs_path" not in path.read_text(
            encoding="utf-8"
        )
        # No stray "extra_path" key leaked into the canonical schema.
        assert "extra_path" not in path.read_text(encoding="utf-8")


def test_projection_keys_match_model_field_names() -> None:
    # Regression guard: serialization projects exactly the canonical model
    # fields (no drift, no extras), keyed off the models' own helpers.
    identity_dict = writer_module._serialize_identity(_identity())
    assert sorted(identity_dict.keys()) == sorted(identity_field_names())
    content_dict = writer_module._serialize_content(_content())
    assert sorted(content_dict.keys()) == sorted(
        content_snapshot_field_names()
    )


# ---------------------------------------------------------------------------
# 9. Whitespace-only / unsafe session IDs are rejected
# ---------------------------------------------------------------------------


def test_whitespace_only_session_id_rejected(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    for bad_sid in ("", " ", "   ", "\t", "\n", "\t\n ", "  \r\n  "):
        bundle = Stage30_8CompactSessionArtifactBundle(
            session_id=bad_sid, ping_artifacts=(_ping(),)
        )
        result = write_compact_session_artifact_bundle(out_dir, bundle)
        assert result.status == WRITE_STATUS_INVALID, repr(bad_sid)
        assert result.reason == WRITE_REASON_INVALID_SESSION_ID, repr(
            bad_sid
        )
        assert result.safe_to_persist is False
    assert _files_under(out_dir) == []


# ---------------------------------------------------------------------------
# 10. Shrinking rewrite removes stale old member files
# ---------------------------------------------------------------------------


def test_shrinking_rewrite_removes_stale_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    # First write: the full 6-member bundle (8 files).
    first = write_compact_session_artifact_bundle(out_dir, _full_bundle())
    assert first.status == WRITE_STATUS_WRITTEN
    session_dir = Path(first.session_dir)
    assert (session_dir / "session_summary.json").exists()
    assert (session_dir / "ping_artifact_0002.json").exists()

    # Second write: a single-ping bundle (3 files) to the same session.
    second = write_compact_session_artifact_bundle(
        out_dir, _single_ping_bundle()
    )
    assert second.status == WRITE_STATUS_WRITTEN

    # The session dir now holds EXACTLY the new bundle's files; every
    # stale old member file is gone.
    names = {p.name for p in session_dir.iterdir() if p.is_file()}
    assert names == {
        "ping_artifact_0001.json",
        VALIDATION_RESULT_FILENAME,
        MANIFEST_FILENAME,
    }
    assert not (session_dir / "session_summary.json").exists()
    assert not (session_dir / "ping_artifact_0002.json").exists()
    assert not (session_dir / "storage_budget_snapshot.json").exists()

    # The new manifest references only files that are actually present.
    manifest = json.loads(
        (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert manifest["member_files"] == ["ping_artifact_0001.json"]
    for name in manifest["member_files"]:
        assert (session_dir / name).exists()

    # No leftover hidden staging / previous directories.
    assert _hidden_transient_dirs(out_dir) == []
    assert {p.name for p in out_dir.iterdir()} == {"sess-001"}


def test_success_leaves_no_transient_dirs(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    result = write_compact_session_artifact_bundle(out_dir, _full_bundle())
    assert result.status == WRITE_STATUS_WRITTEN
    assert {p.name for p in out_dir.iterdir()} == {"sess-001"}
    assert _hidden_transient_dirs(out_dir) == []


# ---------------------------------------------------------------------------
# 11. Mid-write failure: fail closed, never a committed-looking bundle
# ---------------------------------------------------------------------------


def test_failure_on_manifest_write_no_committed_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    out_dir = tmp_path / "out"
    original = writer_module._atomic_write

    def failing(final_path: Path, data: bytes) -> None:
        if final_path.name == MANIFEST_FILENAME:
            raise OSError("simulated manifest write failure")
        return original(final_path, data)

    monkeypatch.setattr(writer_module, "_atomic_write", failing)
    result = write_compact_session_artifact_bundle(out_dir, _full_bundle())

    assert result.status == WRITE_STATUS_WRITE_FAILED
    assert result.safe_to_persist is False
    # No final session dir, no manifest anywhere, no leftover staging dir.
    assert not (out_dir / "sess-001").exists()
    assert list(out_dir.rglob("manifest.json")) == []
    assert _hidden_transient_dirs(out_dir) == []


def test_failure_mid_artifacts_no_partial_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    out_dir = tmp_path / "out"
    original = writer_module._atomic_write
    state = {"count": 0}

    def failing(final_path: Path, data: bytes) -> None:
        state["count"] += 1
        if state["count"] == 2:  # fail after the first artifact file
            raise OSError("simulated mid-artifact write failure")
        return original(final_path, data)

    monkeypatch.setattr(writer_module, "_atomic_write", failing)
    result = write_compact_session_artifact_bundle(out_dir, _full_bundle())

    assert result.status == WRITE_STATUS_WRITE_FAILED
    assert result.safe_to_persist is False
    assert not (out_dir / "sess-001").exists()
    assert list(out_dir.rglob("manifest.json")) == []
    assert _hidden_transient_dirs(out_dir) == []


def test_failure_during_rewrite_keeps_old_bundle_intact(
    tmp_path: Path, monkeypatch
) -> None:
    out_dir = tmp_path / "out"
    # First write succeeds -> a valid full bundle on disk.
    first = write_compact_session_artifact_bundle(out_dir, _full_bundle())
    assert first.status == WRITE_STATUS_WRITTEN
    session_dir = Path(first.session_dir)

    # Second write fails on the manifest while staging the new bundle.
    original = writer_module._atomic_write

    def failing(final_path: Path, data: bytes) -> None:
        if final_path.name == MANIFEST_FILENAME:
            raise OSError("simulated rewrite manifest failure")
        return original(final_path, data)

    monkeypatch.setattr(writer_module, "_atomic_write", failing)
    second = write_compact_session_artifact_bundle(
        out_dir, _single_ping_bundle()
    )
    assert second.status == WRITE_STATUS_WRITE_FAILED
    assert second.safe_to_persist is False

    # The prior valid bundle is completely intact (manifest references all
    # 6 members and every one is present).
    manifest = json.loads(
        (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert len(manifest["member_files"]) == 6
    for name in manifest["member_files"]:
        assert (session_dir / name).exists()
    assert (session_dir / "session_summary.json").exists()
    assert _hidden_transient_dirs(out_dir) == []


def test_promotion_rename_failure_rolls_back_old_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    out_dir = tmp_path / "out"
    first = write_compact_session_artifact_bundle(out_dir, _full_bundle())
    assert first.status == WRITE_STATUS_WRITTEN
    session_dir = Path(first.session_dir)

    # Inject a failure on the staging->final promotion rename only; the
    # final->previous rename-aside and the previous->final rollback both
    # succeed, so the prior bundle must be restored.
    original = writer_module._rename_dir

    def failing(src: Path, dst: Path) -> None:
        if STAGING_DIR_INFIX in src.name:
            raise OSError("simulated promotion rename failure")
        return original(src, dst)

    monkeypatch.setattr(writer_module, "_rename_dir", failing)
    second = write_compact_session_artifact_bundle(
        out_dir, _single_ping_bundle()
    )
    assert second.status == WRITE_STATUS_WRITE_FAILED
    assert second.safe_to_persist is False

    # The old full bundle was rolled back into place intact.
    manifest = json.loads(
        (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert len(manifest["member_files"]) == 6
    assert (session_dir / "session_summary.json").exists()
    assert (session_dir / "ping_artifact_0002.json").exists()
    assert _hidden_transient_dirs(out_dir) == []


# ---------------------------------------------------------------------------
# 12. Manifest is written LAST (commit-marker ordering)
# ---------------------------------------------------------------------------


def test_manifest_is_written_last(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "out"
    original = writer_module._atomic_write
    order: List[str] = []

    def recording(final_path: Path, data: bytes) -> None:
        order.append(final_path.name)
        return original(final_path, data)

    monkeypatch.setattr(writer_module, "_atomic_write", recording)
    result = write_compact_session_artifact_bundle(out_dir, _full_bundle())

    assert result.status == WRITE_STATUS_WRITTEN
    assert order[-1] == MANIFEST_FILENAME
    assert order[-2] == VALIDATION_RESULT_FILENAME
    # Every earlier write is an artifact member file (manifest is never
    # written before an artifact).
    assert MANIFEST_FILENAME not in order[:-1]
    # On success, every file the manifest references exists on disk.
    session_dir = Path(result.session_dir)
    manifest = json.loads(
        (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    for name in manifest["member_files"]:
        assert (session_dir / name).exists()
