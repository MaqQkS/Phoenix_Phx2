"""Stage 26.2 eligibility-classifier tests.

Pins the deterministic behavior of the Stage 26.2 classifier:

  * pure / read-only against Stage 26.1 records;
  * preserves truth-class strings verbatim;
  * rejects unknown truth classes with a typed Stage 26 error;
  * never labels a row as a bad / failure outcome;
  * preserves input order;
  * never joins / dedupes / groups rows;
  * summary counts match rows;
  * Stage 25 manifest hash is carried through to every row / result.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.constants import (
    CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
    CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
    MEASUREMENT_TRUTH_CLASSES,
    STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS,
)
from PHX2.stage26.eligibility_classifier import (
    build_eligibility_result,
    build_eligibility_row,
    classify_measurement_truth_class,
    summarize_eligibility,
)
from PHX2.stage26.eligibility_constants import (
    DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR,
    DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
    DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR,
    DENOMINATOR_STATUS_REJECTION_DENOMINATOR,
    DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
    ELIGIBILITY_DECISION_BY_TRUTH_CLASS,
    OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE,
    PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH,
    STAGE26_ELIGIBILITY_VERSION,
)
from PHX2.stage26.eligibility_models import (
    Stage26EligibilityDecision,
    Stage26EligibilityResult,
    Stage26EligibilityRow,
)
from PHX2.stage26.errors import Stage26EligibilityError
from PHX2.stage26.models import (
    ATHMeasurementInput,
    MigrationMeasurementInput,
    Stage25ArtifactReference,
    Stage25ArtifactSet,
    Stage25ManifestInput,
    Stage25SummaryInput,
    Stage26CalibrationInputSet,
    Stage26ReaderResult,
    ArtifactValidationReport,
)


# ---------------------------------------------------------------------------
# Synthetic Stage 26.1 input rows (handcrafted; no live artifacts)
# ---------------------------------------------------------------------------


_SAMPLE_MINT_A: str = "MintAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_SAMPLE_MINT_B: str = "MintBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_SAMPLE_MINT_C: str = "MintCcccccccccccccccccccccccccccccccccccccc"
_SAMPLE_HASH_A: str = "a" * 64
_SAMPLE_HASH_B: str = "b" * 64
_SAMPLE_HASH_C: str = "c" * 64
_SAMPLE_HASH_D: str = "d" * 64
_SAMPLE_HASH_E: str = "e" * 64
_SAMPLE_MANIFEST_HASH: str = "f" * 64
_SAMPLE_OBS_AT: str = "2026-01-01T00:00:00Z"


def _measured_migration(
    *,
    token_mint: str = _SAMPLE_MINT_A,
    measurement_hash: str = _SAMPLE_HASH_A,
) -> MigrationMeasurementInput:
    return MigrationMeasurementInput(
        measurement_family="MIGRATION",
        measurement_status="MEASURED",
        confidence_level="HIGH",
        reconciliation_status="AGREED",
        token_mint=token_mint,
        schema_version="phx2_stage25_schema_v0",
        threshold_version="phx2_stage25_threshold_v0",
        measurer_name="stage25_migration_measurer",
        measurer_version="stage25_migration_measurer_v0",
        consolidated_slot=251_000_000,
        consolidated_block_time=1_750_000_000,
        reconciled_signature="sig_synth_001",
        selected_source_family="BIRDEYE",
        contributing_source_count=2,
        reason_codes=("MIGRATION_SOURCES_AGREED",),
        numeric_features={},
        evidence={},
        input_missing_fields=(),
        measurement_hash=measurement_hash,
    )


def _migration_with_status(
    *,
    status: str,
    token_mint: str = _SAMPLE_MINT_B,
    measurement_hash: str = _SAMPLE_HASH_B,
) -> MigrationMeasurementInput:
    return MigrationMeasurementInput(
        measurement_family="MIGRATION",
        measurement_status=status,
        confidence_level="NONE",
        reconciliation_status="NO_SOURCES",
        token_mint=token_mint,
        schema_version="phx2_stage25_schema_v0",
        threshold_version="phx2_stage25_threshold_v0",
        measurer_name="stage25_migration_measurer",
        measurer_version="stage25_migration_measurer_v0",
        consolidated_slot=-1,
        consolidated_block_time=-1,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
        reason_codes=(),
        numeric_features={},
        evidence={},
        input_missing_fields=(),
        measurement_hash=measurement_hash,
    )


def _measured_ath(
    *,
    token_mint: str = _SAMPLE_MINT_C,
    measurement_hash: str = _SAMPLE_HASH_C,
) -> ATHMeasurementInput:
    return ATHMeasurementInput(
        measurement_family="ATH",
        measurement_status="MEASURED",
        confidence_level="HIGH",
        reconciliation_status="AGREED",
        token_mint=token_mint,
        schema_version="phx2_stage25_schema_v0",
        threshold_version="phx2_stage25_threshold_v0",
        measurer_name="stage25_ath_measurer",
        measurer_version="stage25_ath_measurement_v0",
        consolidated_peak_slot=251_000_500,
        consolidated_peak_block_time=1_750_001_000,
        consolidated_peak_price=1_500_000,
        quote_denomination="USD_MICRO",
        peak_source_family="BIRDEYE",
        reconciled_peak_observed_at_utc=_SAMPLE_OBS_AT,
        time_to_peak_seconds=None,
        contributing_source_count=2,
        reason_codes=(),
        numeric_features={},
        evidence={},
        input_missing_fields=(),
        measurement_hash=measurement_hash,
    )


def _ath_with_status(
    *,
    status: str,
    token_mint: str = _SAMPLE_MINT_B,
    measurement_hash: str = _SAMPLE_HASH_D,
) -> ATHMeasurementInput:
    return ATHMeasurementInput(
        measurement_family="ATH",
        measurement_status=status,
        confidence_level="NONE",
        reconciliation_status="NO_SOURCES",
        token_mint=token_mint,
        schema_version="phx2_stage25_schema_v0",
        threshold_version="phx2_stage25_threshold_v0",
        measurer_name="stage25_ath_measurer",
        measurer_version="stage25_ath_measurement_v0",
        consolidated_peak_slot=-1,
        consolidated_peak_block_time=-1,
        consolidated_peak_price=None,
        quote_denomination="USD_MICRO",
        peak_source_family="",
        reconciled_peak_observed_at_utc="",
        time_to_peak_seconds=None,
        contributing_source_count=0,
        reason_codes=(),
        numeric_features={},
        evidence={},
        input_missing_fields=(),
        measurement_hash=measurement_hash,
    )


def _empty_summary() -> Stage25SummaryInput:
    empty: dict[str, int] = {}
    return Stage25SummaryInput(
        stage_name="phx2.stage25",
        stage_version="phx2_stage25_v0",
        schema_version="phx2_stage25_schema_v0",
        summary_version="phx2_stage25_summary_v0",
        observe_only_mode="phx2_observe_only_mode",
        created_at_utc=_SAMPLE_OBS_AT,
        observed_token_count=0,
        row_counts=empty,
        migration_observation_source_family_counts=empty,
        migration_observation_source_status_counts=empty,
        migration_measurement_status_counts=empty,
        migration_measurement_confidence_counts=empty,
        migration_measurement_reconciliation_counts=empty,
        price_window_kind_counts=empty,
        price_window_source_status_counts=empty,
        ath_candidate_kind_counts=empty,
        ath_candidate_confidence_counts=empty,
        ath_candidate_source_family_counts=empty,
        ath_candidate_source_status_counts=empty,
        source_reconciliation_status_counts=empty,
        source_reconciliation_confidence_counts=empty,
        ath_measurement_status_counts=empty,
        ath_measurement_confidence_counts=empty,
        ath_measurement_reconciliation_counts=empty,
        rejection_reason_counts=empty,
    )


def _empty_manifest() -> Stage25ManifestInput:
    return Stage25ManifestInput(
        stage_name="phx2.stage25",
        stage_version="phx2_stage25_v0",
        schema_version="phx2_stage25_manifest_schema_v0",
        observe_only_mode="phx2_observe_only_mode",
        redaction_confirmed="",
        manifest_kind="artifact",
        files=(),
        upstream_stage24_pin=None,
        created_at_utc=_SAMPLE_OBS_AT,
        runner_name="stage25_runner",
        runner_version="stage25_runner_v0",
        writer_name="stage25_writer",
        writer_version="stage25_writer_v0",
    )


def _build_input_set(
    *,
    migration_rows: tuple[MigrationMeasurementInput, ...],
    ath_rows: tuple[ATHMeasurementInput, ...],
    manifest_hash: str = _SAMPLE_MANIFEST_HASH,
) -> Stage26CalibrationInputSet:
    pin = Stage25ArtifactReference(
        artifact_basename="stage25_manifest.json",
        artifact_sha256=manifest_hash,
    )
    artifact_set = Stage25ArtifactSet(
        manifest=_empty_manifest(),
        summary=_empty_summary(),
        migration_observations=(),
        migration_measurements=migration_rows,
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=ath_rows,
        measurement_rejections=(),
        stage25_manifest_pin=pin,
        per_artifact_pins=(),
    )
    reader_result = Stage26ReaderResult(
        artifact_set=artifact_set,
        validation_report=ArtifactValidationReport(entries=(), ok=True),
    )
    return Stage26CalibrationInputSet(
        stage26_calibration_input_version="stage26_calibration_input_v0",
        stage25_manifest_pin=pin,
        reader_result=reader_result,
    )


# ---------------------------------------------------------------------------
# classify_measurement_truth_class
# ---------------------------------------------------------------------------


def test_classify_returns_eligibility_decision_named_tuple():
    decision = classify_measurement_truth_class("MEASURED")
    assert isinstance(decision, Stage26EligibilityDecision)


def test_classify_every_locked_truth_class_returns_a_decision():
    """High-value test #2: every Stage 26.1 MEASUREMENT_TRUTH_CLASS
    has an explicit eligibility mapping.
    """
    for truth_class in MEASUREMENT_TRUTH_CLASSES:
        decision = classify_measurement_truth_class(truth_class)
        assert isinstance(decision, Stage26EligibilityDecision)


def test_classify_measured_returns_primary_threshold_eligible():
    decision = classify_measurement_truth_class("MEASURED")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR
    )
    assert decision.outcome_eligibility_status == (
        OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE
    )
    assert decision.primary_denominator_reason == (
        PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH
    )
    assert decision.eligible_for_threshold_calibration is True
    assert decision.eligible_for_primary_metrics is True
    assert decision.eligible_for_observability_metrics is True


def test_classify_partial_returns_observability_only():
    decision = classify_measurement_truth_class("PARTIAL")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR
    )
    assert decision.outcome_eligibility_status == (
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY
    )
    assert decision.eligible_for_threshold_calibration is False
    assert decision.eligible_for_primary_metrics is False
    assert decision.eligible_for_observability_metrics is True


def test_classify_source_conflict_returns_observability_only():
    decision = classify_measurement_truth_class("SOURCE_CONFLICT")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR
    )
    assert decision.outcome_eligibility_status == (
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY
    )
    assert decision.eligible_for_threshold_calibration is False


def test_classify_ambiguous_returns_observability_only():
    decision = classify_measurement_truth_class("AMBIGUOUS")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR
    )
    assert decision.eligible_for_threshold_calibration is False
    assert decision.eligible_for_observability_metrics is True


def test_classify_missing_returns_coverage_gap_only():
    decision = classify_measurement_truth_class("MISSING")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR
    )
    assert decision.eligible_for_threshold_calibration is False
    assert decision.eligible_for_observability_metrics is False


def test_classify_unsupported_returns_scope_gap_only():
    decision = classify_measurement_truth_class("UNSUPPORTED")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR
    )
    assert decision.eligible_for_threshold_calibration is False
    assert decision.eligible_for_observability_metrics is False


def test_classify_rejected_returns_rejection_only():
    decision = classify_measurement_truth_class("REJECTED")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_REJECTION_DENOMINATOR
    )
    assert decision.eligible_for_threshold_calibration is False
    assert decision.eligible_for_observability_metrics is False


def test_classify_not_applicable_returns_scope_gap_only():
    decision = classify_measurement_truth_class("NOT_APPLICABLE")
    assert decision.denominator_status == (
        DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR
    )
    assert decision.eligible_for_threshold_calibration is False


def test_classify_unknown_string_raises_stage26_eligibility_error():
    with pytest.raises(Stage26EligibilityError) as excinfo:
        classify_measurement_truth_class("NOT_A_REAL_TRUTH_CLASS")
    assert excinfo.value.error_code == (
        STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS
    )


def test_classify_non_string_raises_stage26_eligibility_error():
    with pytest.raises(Stage26EligibilityError) as excinfo:
        classify_measurement_truth_class(42)   # type: ignore[arg-type]
    assert excinfo.value.error_code == (
        STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS
    )


def test_classify_is_deterministic_across_repeated_calls():
    """High-value test #15: classifier is deterministic across repeated runs."""
    for truth_class in MEASUREMENT_TRUTH_CLASSES:
        first = classify_measurement_truth_class(truth_class)
        second = classify_measurement_truth_class(truth_class)
        third = classify_measurement_truth_class(truth_class)
        assert first == second == third


def test_classify_mapping_matches_locked_constants_table():
    """The classifier's output for each truth class equals the locked
    ``ELIGIBILITY_DECISION_BY_TRUTH_CLASS`` row for that truth class.
    """
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        truth_class = entry[0]
        decision = classify_measurement_truth_class(truth_class)
        assert decision.denominator_status == entry[1]
        assert decision.outcome_eligibility_status == entry[2]
        assert decision.primary_denominator_reason == entry[3]
        assert decision.calibration_eligibility_kind == entry[4]
        assert decision.eligible_for_threshold_calibration == entry[5]
        assert decision.eligible_for_primary_metrics == entry[6]
        assert decision.eligible_for_observability_metrics == entry[7]


# ---------------------------------------------------------------------------
# build_eligibility_row
# ---------------------------------------------------------------------------


def test_build_row_preserves_truth_class_verbatim():
    """High-value test #12: truth class string is preserved exactly on output."""
    for status in MEASUREMENT_TRUTH_CLASSES:
        if status == "MEASURED":
            input_row = _measured_migration()
        else:
            input_row = _migration_with_status(status=status)
        out = build_eligibility_row(
            input_row=input_row,
            source_artifact_kind=CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
            row_index=0,
            stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
        )
        assert out.measurement_truth_class == status


def test_build_row_carries_manifest_hash():
    """High-value test #19: manifest hash is carried through to every row."""
    input_row = _measured_migration()
    out = build_eligibility_row(
        input_row=input_row,
        source_artifact_kind=CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
        row_index=0,
        stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
    )
    assert out.stage25_manifest_hash == _SAMPLE_MANIFEST_HASH


def test_build_row_assigns_deterministic_row_id():
    out = build_eligibility_row(
        input_row=_measured_migration(),
        source_artifact_kind=CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
        row_index=7,
        stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
    )
    assert out.row_id == "MIGRATION_MEASUREMENT#7"


def test_build_row_carries_source_row_id_and_mint_verbatim():
    out = build_eligibility_row(
        input_row=_measured_migration(),
        source_artifact_kind=CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
        row_index=0,
        stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
    )
    assert out.source_row_id == _SAMPLE_HASH_A
    assert out.mint == _SAMPLE_MINT_A


def test_build_row_does_not_upgrade_non_measured_to_measured():
    """High-value test: no non-MEASURED row gets threshold-calibration eligibility."""
    for status in ("PARTIAL", "SOURCE_CONFLICT", "AMBIGUOUS", "MISSING",
                   "UNSUPPORTED", "REJECTED", "NOT_APPLICABLE"):
        input_row = _migration_with_status(status=status)
        out = build_eligibility_row(
            input_row=input_row,
            source_artifact_kind=CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
            row_index=0,
            stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
        )
        assert out.measurement_truth_class == status
        assert out.eligible_for_threshold_calibration is False, (
            f"non-MEASURED status {status!r} must not be threshold eligible"
        )


def test_build_row_for_ath_measurement_uses_ath_artifact_kind():
    out = build_eligibility_row(
        input_row=_measured_ath(),
        source_artifact_kind=CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
        row_index=3,
        stage25_manifest_hash=_SAMPLE_MANIFEST_HASH,
    )
    assert out.source_artifact_kind == CALIBRATION_INPUT_KIND_ATH_MEASUREMENT
    assert out.row_id == "ATH_MEASUREMENT#3"


# ---------------------------------------------------------------------------
# build_eligibility_result
# ---------------------------------------------------------------------------


def test_build_result_empty_input_returns_empty_rows():
    input_set = _build_input_set(migration_rows=(), ath_rows=())
    result = build_eligibility_result(input_set)
    assert isinstance(result, Stage26EligibilityResult)
    assert result.rows == ()
    assert result.summary.row_count == 0


def test_build_result_preserves_input_order():
    """High-value test #16: classifier preserves input order."""
    migration_rows = (
        _measured_migration(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_A
        ),
        _migration_with_status(
            status="MISSING",
            token_mint=_SAMPLE_MINT_B,
            measurement_hash=_SAMPLE_HASH_B,
        ),
        _migration_with_status(
            status="PARTIAL",
            token_mint=_SAMPLE_MINT_C,
            measurement_hash=_SAMPLE_HASH_C,
        ),
    )
    ath_rows = (
        _measured_ath(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_D
        ),
        _ath_with_status(
            status="MISSING",
            token_mint=_SAMPLE_MINT_B,
            measurement_hash=_SAMPLE_HASH_E,
        ),
    )
    input_set = _build_input_set(
        migration_rows=migration_rows,
        ath_rows=ath_rows,
    )
    result = build_eligibility_result(input_set)
    assert len(result.rows) == 5
    # Migration first (preserved order), then ATH (preserved order).
    assert result.rows[0].source_row_id == _SAMPLE_HASH_A
    assert result.rows[1].source_row_id == _SAMPLE_HASH_B
    assert result.rows[2].source_row_id == _SAMPLE_HASH_C
    assert result.rows[3].source_row_id == _SAMPLE_HASH_D
    assert result.rows[4].source_row_id == _SAMPLE_HASH_E


def test_build_result_does_not_join_rows_by_mint():
    """High-value test #17: classifier does not join/dedupe/group rows."""
    # Two rows with the same mint; the classifier MUST keep both, in order.
    migration_rows = (
        _measured_migration(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_A
        ),
    )
    ath_rows = (
        _measured_ath(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_D
        ),
    )
    input_set = _build_input_set(
        migration_rows=migration_rows,
        ath_rows=ath_rows,
    )
    result = build_eligibility_result(input_set)
    assert len(result.rows) == 2
    assert {row.mint for row in result.rows} == {_SAMPLE_MINT_A}
    assert result.rows[0].source_artifact_kind == (
        CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT
    )
    assert result.rows[1].source_artifact_kind == (
        CALIBRATION_INPUT_KIND_ATH_MEASUREMENT
    )


def test_build_result_does_not_dedupe_identical_rows():
    """High-value test: identical rows must NOT be collapsed."""
    migration_rows = (
        _measured_migration(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_A
        ),
        _measured_migration(
            token_mint=_SAMPLE_MINT_A, measurement_hash=_SAMPLE_HASH_A
        ),
    )
    input_set = _build_input_set(
        migration_rows=migration_rows, ath_rows=()
    )
    result = build_eligibility_result(input_set)
    assert len(result.rows) == 2
    assert result.rows[0].row_id == "MIGRATION_MEASUREMENT#0"
    assert result.rows[1].row_id == "MIGRATION_MEASUREMENT#1"


def test_build_result_is_deterministic_across_repeated_calls():
    """High-value test #15: deterministic across runs."""
    migration_rows = (
        _measured_migration(),
        _migration_with_status(status="REJECTED"),
    )
    ath_rows = (
        _measured_ath(),
        _ath_with_status(status="MISSING"),
    )
    input_set = _build_input_set(
        migration_rows=migration_rows, ath_rows=ath_rows
    )
    first = build_eligibility_result(input_set)
    second = build_eligibility_result(input_set)
    third = build_eligibility_result(input_set)
    assert first == second == third


def test_build_result_carries_version_axis_and_manifest_pin():
    input_set = _build_input_set(migration_rows=(), ath_rows=())
    result = build_eligibility_result(input_set)
    assert (
        result.stage26_eligibility_version == STAGE26_ELIGIBILITY_VERSION
    )
    assert (
        result.stage25_manifest_pin.artifact_sha256
        == _SAMPLE_MANIFEST_HASH
    )


def test_build_result_carries_manifest_hash_to_every_row():
    """High-value test #19: manifest hash carried through to every row/result."""
    migration_rows = (
        _measured_migration(),
        _migration_with_status(status="MISSING"),
    )
    ath_rows = (_measured_ath(),)
    input_set = _build_input_set(
        migration_rows=migration_rows, ath_rows=ath_rows
    )
    result = build_eligibility_result(input_set)
    for row in result.rows:
        assert row.stage25_manifest_hash == _SAMPLE_MANIFEST_HASH


def test_build_result_unknown_truth_class_raises_typed_error():
    """High-value test #11: unknown truth class raises typed Stage 26 error."""
    bogus = MigrationMeasurementInput(
        measurement_family="MIGRATION",
        measurement_status="NOT_A_LOCKED_STATUS",
        confidence_level="NONE",
        reconciliation_status="NO_SOURCES",
        token_mint=_SAMPLE_MINT_A,
        schema_version="phx2_stage25_schema_v0",
        threshold_version="phx2_stage25_threshold_v0",
        measurer_name="stage25_migration_measurer",
        measurer_version="stage25_migration_measurer_v0",
        consolidated_slot=-1,
        consolidated_block_time=-1,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
        reason_codes=(),
        numeric_features={},
        evidence={},
        input_missing_fields=(),
        measurement_hash=_SAMPLE_HASH_A,
    )
    input_set = _build_input_set(
        migration_rows=(bogus,), ath_rows=()
    )
    with pytest.raises(Stage26EligibilityError) as excinfo:
        build_eligibility_result(input_set)
    assert excinfo.value.error_code == (
        STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS
    )


# ---------------------------------------------------------------------------
# summarize_eligibility
# ---------------------------------------------------------------------------


def test_summary_row_count_matches_rows_length():
    input_set = _build_input_set(
        migration_rows=(
            _measured_migration(),
            _migration_with_status(status="PARTIAL"),
            _migration_with_status(status="MISSING"),
        ),
        ath_rows=(
            _measured_ath(),
            _ath_with_status(status="REJECTED"),
        ),
    )
    result = build_eligibility_result(input_set)
    assert result.summary.row_count == len(result.rows) == 5


def test_summary_counts_by_denominator_status_sum_to_row_count():
    """High-value test #18: summary counts match rows by denominator."""
    input_set = _build_input_set(
        migration_rows=(
            _measured_migration(),
            _migration_with_status(status="PARTIAL"),
            _migration_with_status(status="MISSING"),
        ),
        ath_rows=(
            _measured_ath(),
            _ath_with_status(status="REJECTED"),
        ),
    )
    result = build_eligibility_result(input_set)
    total = sum(
        count for _key, count in result.summary.counts_by_denominator_status
    )
    assert total == result.summary.row_count


def test_summary_counts_by_outcome_match_rows():
    input_set = _build_input_set(
        migration_rows=(
            _measured_migration(),
            _migration_with_status(status="PARTIAL"),
        ),
        ath_rows=(
            _measured_ath(),
            _ath_with_status(status="REJECTED"),
        ),
    )
    result = build_eligibility_result(input_set)
    pairs = dict(result.summary.counts_by_outcome_eligibility_status)
    assert pairs["PRIMARY_OUTCOME_ELIGIBLE"] == 2
    assert pairs["OBSERVABILITY_ONLY"] == 1
    assert pairs["REJECTION_ONLY"] == 1
    assert pairs.get("COVERAGE_GAP_ONLY", 0) == 0
    assert pairs.get("SCOPE_GAP_ONLY", 0) == 0
    assert pairs.get("INELIGIBLE_INVALID_INPUT", 0) == 0


def test_summary_counts_by_primary_reason_match_rows():
    input_set = _build_input_set(
        migration_rows=(
            _migration_with_status(status="MISSING"),
            _migration_with_status(status="UNSUPPORTED"),
            _migration_with_status(status="NOT_APPLICABLE"),
        ),
        ath_rows=(),
    )
    result = build_eligibility_result(input_set)
    pairs = dict(result.summary.counts_by_primary_denominator_reason)
    assert pairs["MISSING_MEASUREMENT"] == 1
    assert pairs["UNSUPPORTED_MEASUREMENT"] == 1
    assert pairs["NOT_APPLICABLE_MEASUREMENT"] == 1
    assert pairs["MEASURED_TRUTH"] == 0


def test_summary_count_tuples_are_sorted_ascending():
    """The summary's per-bucket count tuples are tuple-of-pairs sorted
    by key ascending. This is the locked deterministic emission shape.
    """
    input_set = _build_input_set(
        migration_rows=(
            _measured_migration(),
            _migration_with_status(status="MISSING"),
        ),
        ath_rows=(),
    )
    result = build_eligibility_result(input_set)
    for count_tuple in (
        result.summary.counts_by_denominator_status,
        result.summary.counts_by_outcome_eligibility_status,
        result.summary.counts_by_primary_denominator_reason,
        result.summary.counts_by_calibration_eligibility_kind,
        result.summary.counts_by_measurement_truth_class,
        result.summary.counts_by_source_artifact_kind,
    ):
        keys = [pair[0] for pair in count_tuple]
        assert keys == sorted(keys), (
            f"summary count tuple is not sorted ascending: {keys!r}"
        )


def test_no_row_gets_a_bad_or_failure_outcome():
    """High-value test #14: no row is labeled as bad/failure outcome.

    Stage 25's non-MEASURED truth classes are first-class outcomes,
    not failures. Stage 26.2's row records carry no ``failed`` /
    ``error`` / ``invalid`` boolean fields on the per-row record.
    """
    input_set = _build_input_set(
        migration_rows=(
            _migration_with_status(status="REJECTED"),
            _migration_with_status(status="MISSING"),
        ),
        ath_rows=(),
    )
    result = build_eligibility_result(input_set)
    forbidden_fields = {
        "failed", "is_failure", "is_bad", "is_invalid",
        "error", "bad_outcome",
    }
    for row in result.rows:
        assert forbidden_fields.isdisjoint(set(row._fields))


# ---------------------------------------------------------------------------
# summarize_eligibility (direct invocation)
# ---------------------------------------------------------------------------


def test_summarize_eligibility_returns_immutable_summary():
    rows: tuple[Stage26EligibilityRow, ...] = ()
    summary = summarize_eligibility(rows)
    assert isinstance(summary, tuple)
    assert summary.row_count == 0
