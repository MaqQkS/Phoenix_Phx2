"""Stage 26.1 per-row Stage 25 artifact reader tests."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    MEASUREMENT_STATUS_UNSUPPORTED,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
)
from PHX2.stage26.errors import (
    Stage26ManifestError,
    Stage26ReaderError,
    Stage26SchemaError,
)
from PHX2.stage26.stage25_artifact_reader import (
    read_ath_candidates,
    read_ath_measurements,
    read_measurement_rejections,
    read_migration_measurements,
    read_migration_observations,
    read_price_window_observations,
    read_source_reconciliations,
    read_stage25_manifest,
    read_stage25_summary,
)
from PHX2.tests.stage26.fixtures.builders import (
    FAKE_HASH_64,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    make_ath_candidate_dict,
    make_ath_measurement_measured_dict,
    make_ath_measurement_missing_dict,
    make_migration_measurement_measured_dict,
    make_migration_measurement_missing_dict,
    make_migration_observation_dict,
    write_default_valid_stage25_dir,
    write_empty_stage25_dir,
    write_stage25_dir,
)


# ---------------------------------------------------------------------------
# Manifest reader
# ---------------------------------------------------------------------------


def test_read_manifest_returns_typed_input(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    manifest = read_stage25_manifest(stage25_dir)
    assert manifest.stage_name == "stage25"
    assert manifest.observe_only_mode == "observe_only"
    assert manifest.manifest_kind == "artifact"
    # 7 jsonl artifacts + summary + manifest self-entry = 9 entries.
    assert len(manifest.files) == 9


def test_read_manifest_missing_raises(tmp_path):
    stage25_dir = tmp_path / "stage25"
    stage25_dir.mkdir()
    with pytest.raises(Stage26ManifestError) as exc_info:
        read_stage25_manifest(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_MANIFEST_NOT_FOUND"


def test_read_manifest_invalid_self_entry_raises(tmp_path):
    """Self-entry must carry the locked sentinel sha256 / -1 byte / -1 row.

    Tampering the self-entry's sha256 to a real-looking hex digest
    causes the manifest projection to reject the manifest.
    """
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=_default_payloads(),
        self_entry_override={
            "file_basename": STAGE25_MANIFEST_FILENAME,
            "sha256": "a" * 64,
            "byte_count": -1,
            "row_count": -1,
        },
    )
    with pytest.raises(Stage26ManifestError) as exc_info:
        read_stage25_manifest(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_MANIFEST_HASH_SELF_INVALID"


def test_read_manifest_missing_required_field_raises(tmp_path):
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=_default_payloads(),
        manifest_overrides={"runner_name": None},
    )
    with pytest.raises(Stage26ManifestError) as exc_info:
        read_stage25_manifest(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_MANIFEST_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# Summary reader
# ---------------------------------------------------------------------------


def test_read_summary_returns_typed_input(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    summary = read_stage25_summary(stage25_dir)
    assert summary.stage_name == "stage25"
    assert summary.summary_version == "stage25_summary_v0"
    # row_counts maps are read-only MappingProxyType.
    assert isinstance(summary.row_counts, MappingProxyType)
    with pytest.raises(TypeError):
        summary.row_counts["migration_observations"] = 9  # type: ignore[index]


def test_read_summary_missing_required_field_raises(tmp_path):
    payloads = _default_payloads()
    bad_summary = {
        "stage_name": "stage25",
        # missing many required keys
    }
    payloads[STAGE25_SUMMARY_FILENAME] = canonical_json_bytes(bad_summary)
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError):
        read_stage25_summary(stage25_dir)


# ---------------------------------------------------------------------------
# Per-artifact JSONL readers
# ---------------------------------------------------------------------------


def test_read_migration_observations_returns_typed_records(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    observations = read_migration_observations(stage25_dir)
    assert len(observations) == 2
    assert observations[0].token_mint == SAMPLE_TOKEN_MINT_A
    assert isinstance(observations[0].reason_codes, tuple)
    assert isinstance(observations[0].evidence, MappingProxyType)


def test_read_migration_measurements_preserves_truth_classes(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    measurements = read_migration_measurements(stage25_dir)
    statuses = {m.measurement_status for m in measurements}
    # The default fixture emits one MEASURED and one MISSING row.
    assert MEASUREMENT_STATUS_MEASURED in statuses
    assert MEASUREMENT_STATUS_MISSING in statuses


def test_read_migration_measurement_unknown_status_token_raises(tmp_path):
    bad = make_migration_measurement_measured_dict()
    bad["measurement_status"] = "TOTALLY_BOGUS_STATUS"
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_MEASUREMENTS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_measurements(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_RECORD_TRUTH_CLASS_INVALID"


def test_read_migration_measurement_missing_with_peak_fields_raises(tmp_path):
    """A non-MEASURED migration row that carries a synthesized
    reconciled_signature must be rejected (null-as-zero violation).
    """
    bad = make_migration_measurement_missing_dict()
    bad["reconciled_signature"] = "synthetic_signature"
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_MEASUREMENTS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_measurements(stage25_dir)
    assert exc_info.value.error_code == (
        "STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION"
    )


def test_read_migration_measurement_measured_without_peak_fields_raises(tmp_path):
    bad = make_migration_measurement_measured_dict()
    bad["reconciled_signature"] = ""
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_MEASUREMENTS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_measurements(stage25_dir)
    assert exc_info.value.error_code == (
        "STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION"
    )


def test_read_price_window_observations_preserves_null_price(tmp_path):
    """price=None must NOT be coerced to 0; reader preserves the null."""
    from PHX2.tests.stage26.fixtures.builders import (
        make_price_window_observation_dict,
    )
    from PHX2.stage25.constants import (
        SOURCE_STATUS_ABSENT,
    )

    null_price_row = make_price_window_observation_dict(
        price=None,
        source_status=SOURCE_STATUS_ABSENT,
    )
    payloads = _default_payloads()
    payloads[STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME] = (
        canonical_jsonl_bytes((null_price_row,))
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    observations = read_price_window_observations(stage25_dir)
    assert observations[0].price is None


def test_read_ath_candidates_preserves_insufficient_data_null_price(tmp_path):
    """INSUFFICIENT_DATA candidate must carry null peak_price; reader
    must NOT coerce to 0."""
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    candidates = read_ath_candidates(stage25_dir)
    insufficient = [
        c
        for c in candidates
        if c.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    ]
    assert insufficient != []
    for cand in insufficient:
        assert cand.peak_price is None
        assert cand.peak_observed_at_utc == ""
        assert cand.peak_slot == -1
        assert cand.peak_block_time == -1


def test_read_ath_measurements_preserves_truth_classes(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    measurements = read_ath_measurements(stage25_dir)
    statuses = {m.measurement_status for m in measurements}
    assert MEASUREMENT_STATUS_MEASURED in statuses
    assert MEASUREMENT_STATUS_MISSING in statuses
    measured = [
        m for m in measurements
        if m.measurement_status == MEASUREMENT_STATUS_MEASURED
    ]
    missing = [
        m for m in measurements
        if m.measurement_status == MEASUREMENT_STATUS_MISSING
    ]
    for m in measured:
        assert m.consolidated_peak_price is not None
        assert m.peak_source_family != ""
        assert m.consolidated_peak_slot >= 0
    for m in missing:
        assert m.consolidated_peak_price is None
        assert m.peak_source_family == ""
        assert m.consolidated_peak_slot == -1


def test_reader_does_not_upgrade_non_measured_truth_class(tmp_path):
    """Reader must NEVER upgrade PARTIAL / SOURCE_CONFLICT / AMBIGUOUS /
    MISSING / UNSUPPORTED / REJECTED into MEASURED."""
    from PHX2.stage25.constants import (
        CONFIDENCE_LEVEL_NONE,
        MEASUREMENT_STATUS_PARTIAL,
        RECONCILIATION_STATUS_SINGLE_SOURCE,
    )

    partial_row = make_ath_measurement_missing_dict(
        measurement_status=MEASUREMENT_STATUS_PARTIAL,
        reconciliation_status=RECONCILIATION_STATUS_SINGLE_SOURCE,
        confidence_level=CONFIDENCE_LEVEL_NONE,
    )
    payloads = _default_payloads()
    payloads[STAGE25_ATH_MEASUREMENTS_FILENAME] = canonical_jsonl_bytes(
        (partial_row,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    measurements = read_ath_measurements(stage25_dir)
    assert measurements[0].measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurements[0].measurement_status != MEASUREMENT_STATUS_MEASURED


def test_reader_rejects_unknown_source_family(tmp_path):
    bad = make_migration_observation_dict()
    bad["source_family"] = "TOTALLY_UNKNOWN_SOURCE_FAMILY"
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_OBSERVATIONS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_observations(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_RECORD_SCHEMA_INVALID"


def test_reader_rejects_extra_field_in_row(tmp_path):
    bad = make_migration_observation_dict()
    bad["surprise_extra_field"] = "leak"
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_OBSERVATIONS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_observations(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_RECORD_SCHEMA_INVALID"


def test_reader_rejects_missing_required_field_in_row(tmp_path):
    bad = make_migration_observation_dict()
    del bad["observation_hash"]
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_OBSERVATIONS_FILENAME] = canonical_jsonl_bytes(
        (bad,)
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_observations(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_RECORD_SCHEMA_INVALID"


def test_reader_rejects_invalid_json_row(tmp_path):
    payloads = _default_payloads()
    payloads[STAGE25_MIGRATION_OBSERVATIONS_FILENAME] = (
        b"{not valid json}\n"
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    with pytest.raises(Stage26SchemaError) as exc_info:
        read_migration_observations(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_ARTIFACT_SCHEMA_INVALID"


def test_reader_missing_artifact_raises(tmp_path):
    payloads = _default_payloads()
    del payloads[STAGE25_ATH_CANDIDATES_FILENAME]
    # Don't include in manifest either.
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
        omit_manifest_entry_basenames=(STAGE25_ATH_CANDIDATES_FILENAME,),
    )
    with pytest.raises(Stage26ReaderError) as exc_info:
        read_ath_candidates(stage25_dir)
    assert exc_info.value.error_code == "STG26_CAL_ARTIFACT_MISSING_REQUIRED"


def test_reader_handles_empty_jsonl_with_zero_rows(tmp_path):
    stage25_dir = write_empty_stage25_dir(tmp_path)
    obs = read_migration_observations(stage25_dir)
    assert obs == ()
    cand = read_ath_candidates(stage25_dir)
    assert cand == ()


def test_reader_leaves_artifact_mtimes_unchanged(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    mtimes_before = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    read_stage25_manifest(stage25_dir)
    read_stage25_summary(stage25_dir)
    read_migration_observations(stage25_dir)
    read_migration_measurements(stage25_dir)
    read_price_window_observations(stage25_dir)
    read_ath_candidates(stage25_dir)
    read_source_reconciliations(stage25_dir)
    read_ath_measurements(stage25_dir)
    read_measurement_rejections(stage25_dir)
    mtimes_after = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    assert mtimes_before == mtimes_after, (
        "Stage 26.1 reader must NEVER touch Stage 25 artifact mtimes"
    )


def test_read_measurement_rejections_supports_empty_source_family(tmp_path):
    from PHX2.tests.stage26.fixtures.builders import (
        make_measurement_rejection_dict,
    )

    empty_source = make_measurement_rejection_dict(source_family="")
    payloads = _default_payloads()
    payloads[STAGE25_MEASUREMENT_REJECTIONS_FILENAME] = (
        canonical_jsonl_bytes((empty_source,))
    )
    stage25_dir = write_stage25_dir(
        base_dir=tmp_path,
        artifact_bytes_by_basename=payloads,
    )
    rejections = read_measurement_rejections(stage25_dir)
    assert rejections[0].source_family == ""


# ---------------------------------------------------------------------------
# Shared default-payload helper (used by negative tests)
# ---------------------------------------------------------------------------


def _default_payloads() -> dict[str, bytes]:
    """Return the default valid artifact payloads (mirrors the
    ``write_default_valid_stage25_dir`` set).

    Negative tests overwrite individual entries before calling
    ``write_stage25_dir`` to compose a controlled invalid scenario.
    """
    from PHX2.tests.stage26.fixtures.builders import (
        _default_artifact_payloads,
    )

    return _default_artifact_payloads()
