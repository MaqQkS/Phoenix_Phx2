"""Stage 26.1 Stage 25 artifact validator tests."""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
)
from PHX2.stage26.constants import (
    ARTIFACT_VALIDATION_STATUS_FILE_MISSING,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
    ARTIFACT_VALIDATION_STATUS_VALIDATED,
)
from PHX2.stage26.errors import Stage26ManifestError
from PHX2.stage26.stage25_artifact_validation import (
    validate_stage25_artifact_set,
)
from PHX2.tests.stage26.fixtures.builders import (
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    canonical_json_bytes,
    write_default_valid_stage25_dir,
    write_empty_stage25_dir,
    write_stage25_dir,
)


def _default_payloads() -> dict[str, bytes]:
    from PHX2.tests.stage26.fixtures.builders import (
        _default_artifact_payloads,
    )

    return _default_artifact_payloads()


def test_validate_default_directory_reports_all_validated(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    report = validate_stage25_artifact_set(stage25_dir)
    assert report.ok is True
    for entry in report.entries:
        assert entry.status == ARTIFACT_VALIDATION_STATUS_VALIDATED, (
            f"{entry.artifact_basename}: {entry.detail!r}"
        )


def test_validate_empty_directory_with_zero_row_counts_is_valid(tmp_path):
    stage25_dir = write_empty_stage25_dir(tmp_path)
    report = validate_stage25_artifact_set(stage25_dir)
    assert report.ok is True


def test_validate_missing_manifest_raises(tmp_path):
    stage25_dir = tmp_path / "stage25"
    stage25_dir.mkdir()
    with pytest.raises(Stage26ManifestError):
        validate_stage25_artifact_set(stage25_dir)


def test_validate_missing_required_artifact_records_entry(tmp_path):
    payloads = _default_payloads()
    del payloads[STAGE25_ATH_CANDIDATES_FILENAME]
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
        omit_manifest_entry_basenames=(STAGE25_ATH_CANDIDATES_FILENAME,),
    )
    report = validate_stage25_artifact_set(stage25_dir)
    assert report.ok is False
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_ATH_CANDIDATES_FILENAME
    ]
    assert matches != []
    assert matches[0].status == ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID


def test_validate_manifest_declared_but_file_missing_records_entry(tmp_path):
    """Manifest declares a JSONL artifact, but the file is removed before
    validation. The validator records FILE_MISSING for that entry.
    """
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    (stage25_dir / STAGE25_ATH_CANDIDATES_FILENAME).unlink()
    report = validate_stage25_artifact_set(stage25_dir)
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_ATH_CANDIDATES_FILENAME
    ]
    assert matches != []
    assert matches[0].status == ARTIFACT_VALIDATION_STATUS_FILE_MISSING
    assert matches[0].error_code == "STG26_CAL_ARTIFACT_MISSING_REQUIRED"


def test_validate_detects_hash_mismatch(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    target = stage25_dir / STAGE25_ATH_CANDIDATES_FILENAME
    original_bytes = target.read_bytes()
    # Append a comment-style blank line; original bytes ended with '\n'.
    target.write_bytes(original_bytes + b" \n")
    report = validate_stage25_artifact_set(stage25_dir)
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_ATH_CANDIDATES_FILENAME
    ]
    assert matches != []
    # The first mismatch detected is byte_count (or hash). Either way the
    # report must NOT mark the entry validated.
    assert matches[0].status != ARTIFACT_VALIDATION_STATUS_VALIDATED


def test_validate_detects_byte_count_mismatch(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    target = stage25_dir / STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    report = validate_stage25_artifact_set(stage25_dir)
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    ]
    assert matches[0].status in (
        ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
        ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
    )


def test_validate_detects_row_count_mismatch(tmp_path):
    """Lie about row_count in the manifest; bytes and hash match but
    row_count != non-blank-line count."""
    payloads = _default_payloads()
    # Take the (valid) measurement_rejections file and inject a wrong
    # row count for it in the manifest. We override the manifest entry
    # via extra_manifest_entries + omit_manifest_entry_basenames.
    real_bytes = payloads[STAGE25_MEASUREMENT_REJECTIONS_FILENAME]
    real_sha = __import__("hashlib").sha256(real_bytes).hexdigest()
    real_byte_count = len(real_bytes)
    lie_row_count = 999  # actual is 1
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
        omit_manifest_entry_basenames=(
            STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
        ),
        extra_manifest_entries=(
            {
                "file_basename": STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
                "sha256": real_sha,
                "row_count": lie_row_count,
                "byte_count": real_byte_count,
            },
        ),
    )
    report = validate_stage25_artifact_set(stage25_dir)
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_MEASUREMENT_REJECTIONS_FILENAME
    ]
    assert matches != []
    assert matches[0].status == (
        ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH
    )


def test_validate_rejects_wrong_observe_only_mode(tmp_path):
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=_default_payloads(),
        manifest_overrides={"observe_only_mode": "live_enforcement"},
    )
    report = validate_stage25_artifact_set(stage25_dir)
    manifest_entry = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_MANIFEST_FILENAME
    ][0]
    assert manifest_entry.status != ARTIFACT_VALIDATION_STATUS_VALIDATED


def test_validate_rejects_wrong_redaction_token(tmp_path):
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=_default_payloads(),
        manifest_overrides={"redaction_confirmed": "not_the_locked_token"},
    )
    report = validate_stage25_artifact_set(stage25_dir)
    manifest_entry = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_MANIFEST_FILENAME
    ][0]
    assert manifest_entry.status != ARTIFACT_VALIDATION_STATUS_VALIDATED


def test_validate_respects_self_referential_manifest_sentinel(tmp_path):
    """Self-entry MUST carry the locked sentinel sha256 + -1 byte/row counts.

    Direct verification that the default fixture uses the sentinel and
    that the validator accepts it without computing a real digest.
    """
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    from PHX2.stage26.stage25_artifact_reader import read_stage25_manifest

    manifest = read_stage25_manifest(stage25_dir)
    self_entries = [
        e
        for e in manifest.files
        if e.file_basename == STAGE25_MANIFEST_FILENAME
    ]
    assert len(self_entries) == 1
    self_entry = self_entries[0]
    assert self_entry.sha256 == SELF_REFERENTIAL_MANIFEST_SHA256
    assert self_entry.byte_count == SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
    assert self_entry.row_count == SELF_REFERENTIAL_MANIFEST_ROW_COUNT
    report = validate_stage25_artifact_set(stage25_dir)
    assert report.ok is True


def test_validate_rejects_truth_class_drift_as_row_level_entry(tmp_path):
    """A row whose measurement_status is not in the locked closed set
    is surfaced as a record-level validation entry."""
    payloads = _default_payloads()
    from PHX2.tests.stage26.fixtures.builders import (
        canonical_jsonl_bytes,
        make_migration_measurement_measured_dict,
    )

    bad_row = make_migration_measurement_measured_dict()
    bad_row["measurement_status"] = "FAKE_STATUS_TOKEN"
    payloads[STAGE25_MIGRATION_MEASUREMENTS_FILENAME] = (
        canonical_jsonl_bytes((bad_row,))
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    report = validate_stage25_artifact_set(stage25_dir)
    matches = [
        e
        for e in report.entries
        if e.artifact_basename == STAGE25_MIGRATION_MEASUREMENTS_FILENAME
    ]
    assert matches[0].error_code == "STG26_CAL_RECORD_TRUTH_CLASS_INVALID"


def test_validate_report_ok_true_iff_every_entry_validated(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    report = validate_stage25_artifact_set(stage25_dir)
    assert report.ok == all(
        e.status == ARTIFACT_VALIDATION_STATUS_VALIDATED
        for e in report.entries
    )


def test_validate_does_not_mutate_artifact_mtimes(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    mtimes_before = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    validate_stage25_artifact_set(stage25_dir)
    mtimes_after = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    assert mtimes_before == mtimes_after
