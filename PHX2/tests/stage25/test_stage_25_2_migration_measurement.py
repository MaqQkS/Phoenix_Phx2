"""Stage 25.2 migration measurement reconciler tests.

Pins:

  * The reconciler emits ``MISSING / NO_SOURCES / NONE`` when no
    observations are supplied for the requested token.
  * ``ABSENT`` / ``UNSUPPORTED`` observations alone never become
    ``MEASURED``.
  * One valid contributing source yields
    ``MEASURED / SINGLE_SOURCE / LOW``.
  * Two valid contributing sources within the
    ``MIGRATION_TIMESTAMP_TOLERANCE_SECONDS`` tolerance yield
    ``MEASURED / AGREED / HIGH`` with a deterministic consolidated
    timestamp / signature.
  * Two valid contributing sources beyond the tolerance yield
    ``AMBIGUOUS / DISAGREED_MAJOR`` with no consolidated value.
  * A same source family supplying conflicting observations yields
    ``AMBIGUOUS / AMBIGUOUS``.
  * Missing block_time alone does not become ``MEASURED``; the valid
    source still contributes if it has block_time, and the partial
    reason code is recorded.
  * Token mismatch is rejected via the reason code, not silently
    accepted.
  * The deterministic chosen contributor obeys the
    ``(block_time, source_family, migration_signature, slot)`` sort.
  * ``measurement_hash`` is deterministic across two equivalent
    invocations.
  * ``bool`` is NOT accepted as an int for slot / block_time when
    constructing a measurement.
  * ``AMBIGUOUS`` migration status blocks any future ATH measurement
    from being ``MEASURED`` via the
    ``migration_measurement_blocks_measured_ath`` predicate (the
    predicate is the canonical downstream check; this test does NOT
    exercise any ATH logic).
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_UNSUPPORTED,
    MIGRATION_TIMESTAMP_TOLERANCE_SECONDS,
    REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_MIGRATION_BLOCK_TIME_MISSING,
    REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED,
    REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
    REASON_CODE_MIGRATION_NO_OBSERVATIONS,
    REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT,
    REASON_CODE_MIGRATION_SINGLE_SOURCE,
    REASON_CODE_MIGRATION_SOURCES_AGREED,
    REASON_CODE_MIGRATION_SOURCES_DISAGREED,
    REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED,
    REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_MIGRATION_MEASURER_NAME,
    STAGE25_MIGRATION_MEASURER_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.migration_measurement import (
    measure_migration_for_token,
    measure_migrations,
    migration_measurement_blocks_measured_ath,
)
from PHX2.stage25.models import (
    Stage25MigrationMeasurement,
    build_migration_measurement_record,
)
from PHX2.tests.stage25.fixtures.builders import (
    SAMPLE_MIGRATION_SIG,
    SAMPLE_MIGRATION_SIG_ALT,
    SAMPLE_MIGRATION_SIG_THIRD,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    SAMPLE_TOKEN_MINT_C,
    make_migration_observation,
)


# ---------------------------------------------------------------------------
# Rule A: no observations -> MISSING
# ---------------------------------------------------------------------------


def test_no_observations_yields_missing():
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, ())
    assert measurement.measurement_family == MEASUREMENT_FAMILY_MIGRATION
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert measurement.confidence_level == CONFIDENCE_LEVEL_NONE
    assert measurement.consolidated_slot == -1
    assert measurement.consolidated_block_time == -1
    assert measurement.contributing_source_count == 0
    assert REASON_CODE_MIGRATION_NO_OBSERVATIONS in measurement.reason_codes
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )


def test_no_observations_emits_empty_signature_and_source():
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, ())
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


# ---------------------------------------------------------------------------
# Rule B: only non-contributing observations
# ---------------------------------------------------------------------------


def test_all_absent_yields_missing():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert measurement.confidence_level == CONFIDENCE_LEVEL_NONE
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )


def test_all_unsupported_yields_unsupported():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_UNSUPPORTED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_UNSUPPORTED
    assert measurement.confidence_level == CONFIDENCE_LEVEL_NONE
    assert REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS in (
        measurement.reason_codes
    )


def test_any_malformed_yields_rejected():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_MALFORMED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_REJECTED


def test_any_decode_failed_yields_rejected():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_DECODE_FAILED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_REJECTED


def test_all_partial_yields_partial():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL


# ---------------------------------------------------------------------------
# Rule C: single valid source -> MEASURED / SINGLE_SOURCE / LOW
# ---------------------------------------------------------------------------


def test_single_valid_source_yields_measured_low():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.confidence_level == CONFIDENCE_LEVEL_LOW
    assert measurement.consolidated_slot == obs.slot
    assert measurement.consolidated_block_time == obs.block_time
    assert measurement.contributing_source_count == 1
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert measurement.reconciled_signature == obs.migration_signature
    assert measurement.selected_source_family == obs.source_family
    assert REASON_CODE_MIGRATION_SINGLE_SOURCE in measurement.reason_codes


# ---------------------------------------------------------------------------
# Rule D: two valid sources agree within tolerance
# ---------------------------------------------------------------------------


def test_two_sources_agree_within_tolerance_yields_measured_high():
    obs_birdeye = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_dex = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_010,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_dex, obs_birdeye)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert measurement.consolidated_block_time == 1_750_000_000
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )
    assert measurement.contributing_source_count == 2
    assert REASON_CODE_MIGRATION_SOURCES_AGREED in measurement.reason_codes


def test_agreement_picks_minimum_block_time():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_005,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.consolidated_block_time == 1_750_000_000
    assert measurement.selected_source_family == (
        SOURCE_FAMILY_DEXSCREENER
    )
    assert measurement.reconciled_signature == (
        SAMPLE_MIGRATION_SIG_ALT
    )


def test_agreement_tiebreaks_on_source_family_signature_slot():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
        slot=251_000_010,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
        slot=251_000_005,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.selected_source_family == (
        SOURCE_FAMILY_BIRDEYE
    )
    assert measurement.reconciled_signature == (
        SAMPLE_MIGRATION_SIG
    )
    assert measurement.consolidated_slot == 251_000_005


def test_agreement_within_tolerance_at_exact_boundary():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000 + MIGRATION_TIMESTAMP_TOLERANCE_SECONDS,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )


# ---------------------------------------------------------------------------
# Rule E: disagreement beyond tolerance
# ---------------------------------------------------------------------------


def test_two_sources_disagree_yields_ambiguous_disagreed_major():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000
        + MIGRATION_TIMESTAMP_TOLERANCE_SECONDS
        + 1,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    assert measurement.consolidated_block_time == -1
    assert measurement.consolidated_slot == -1
    assert REASON_CODE_MIGRATION_SOURCES_DISAGREED in (
        measurement.reason_codes
    )


# ---------------------------------------------------------------------------
# Rule F: same-source conflict
# ---------------------------------------------------------------------------


def test_same_source_conflict_yields_ambiguous():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG,
        block_time=1_750_000_000,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
        block_time=1_750_000_500,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT in (
        measurement.reason_codes
    )


def test_ambiguous_source_status_yields_ambiguous():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS in (
        measurement.reason_codes
    )


# ---------------------------------------------------------------------------
# Rule G: missing block_time handling
# ---------------------------------------------------------------------------


def test_present_with_missing_block_time_alone_is_not_measured():
    obs = make_migration_observation(block_time=-1)
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status != MEASUREMENT_STATUS_MEASURED


def test_missing_block_time_plus_valid_source_measures_from_valid_source():
    obs_partial = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=-1,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_full = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_partial, obs_full)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_block_time == 1_750_000_000
    assert REASON_CODE_MIGRATION_BLOCK_TIME_MISSING in (
        measurement.reason_codes
    )
    assert measurement.selected_source_family == (
        SOURCE_FAMILY_DEXSCREENER
    )


# ---------------------------------------------------------------------------
# Rule H: token mismatch rejected
# ---------------------------------------------------------------------------


def test_observations_for_other_token_are_rejected_with_reason_code():
    obs_mismatch = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_mismatch,)
    )
    assert measurement.token_mint == SAMPLE_TOKEN_MINT_A
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED in (
        measurement.reason_codes
    )


def test_observations_mixed_token_mints_use_only_matching_observations():
    obs_match = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_mismatch = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_match, obs_mismatch)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_block_time == obs_match.block_time
    assert REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED in (
        measurement.reason_codes
    )


def test_empty_token_raises_contract_error():
    with pytest.raises(Stage25ContractError):
        measure_migration_for_token("", ())


def test_non_tuple_observations_raises_contract_error():
    with pytest.raises(Stage25ContractError):
        measure_migration_for_token(
            SAMPLE_TOKEN_MINT_A,
            [make_migration_observation()],  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Duplicate collapse
# ---------------------------------------------------------------------------


def test_exact_duplicates_collapse_and_record_reason_code():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs, obs, obs)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.contributing_source_count == 1
    assert REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED in (
        measurement.reason_codes
    )
    assert measurement.evidence["duplicate_collapsed_count"] == 2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_measurement_hash_is_deterministic():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    first = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs_a, obs_b))
    second = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs_b, obs_a))
    assert first.measurement_hash == second.measurement_hash


def test_measurement_hash_changes_with_token():
    obs_a = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_b = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    measurement_a = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a,)
    )
    measurement_b = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_B, (obs_b,)
    )
    assert measurement_a.measurement_hash != measurement_b.measurement_hash


def test_measure_migrations_groups_by_token_in_sorted_order():
    obs_a = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_b = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    obs_c = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_C)
    measurements = measure_migrations((obs_c, obs_b, obs_a))
    assert tuple(m.token_mint for m in measurements) == (
        SAMPLE_TOKEN_MINT_A,
        SAMPLE_TOKEN_MINT_B,
        SAMPLE_TOKEN_MINT_C,
    )


def test_measure_migrations_returns_empty_tuple_on_empty_input():
    assert measure_migrations(()) == ()


# ---------------------------------------------------------------------------
# Model-level rejection: bool-as-int / invalid sentinels
# ---------------------------------------------------------------------------


def _measured_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "measurement_status": MEASUREMENT_STATUS_MEASURED,
        "confidence_level": CONFIDENCE_LEVEL_LOW,
        "reconciliation_status": RECONCILIATION_STATUS_SINGLE_SOURCE,
        "token_mint": SAMPLE_TOKEN_MINT_A,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "threshold_version": DEFAULT_THRESHOLD_VERSION,
        "measurer_name": STAGE25_MIGRATION_MEASURER_NAME,
        "measurer_version": STAGE25_MIGRATION_MEASURER_VERSION,
        "consolidated_slot": 251_000_000,
        "consolidated_block_time": 1_750_000_000,
        "reconciled_signature": "sig_record_validator_001",
        "selected_source_family": SOURCE_FAMILY_BIRDEYE,
        "contributing_source_count": 1,
        "reason_codes": (),
        "numeric_features": {},
        "evidence": {},
        "input_missing_fields": (),
    }
    base.update(overrides)
    return base


def test_build_migration_measurement_record_rejects_bool_as_slot():
    with pytest.raises(Stage25ContractError):
        build_migration_measurement_record(
            **_measured_kwargs(consolidated_slot=True)  # type: ignore[arg-type]
        )


def test_build_migration_measurement_record_rejects_bool_as_block_time():
    with pytest.raises(Stage25ContractError):
        build_migration_measurement_record(
            **_measured_kwargs(consolidated_block_time=False)  # type: ignore[arg-type]
        )


def test_build_migration_measurement_record_rejects_negative_sentinel():
    with pytest.raises(Stage25ContractError):
        build_migration_measurement_record(
            **_measured_kwargs(consolidated_slot=-2)
        )


def test_build_migration_measurement_record_rejects_unknown_status_token():
    with pytest.raises(Stage25ContractError):
        build_migration_measurement_record(
            **_measured_kwargs(
                measurement_status="DEFINITELY_NOT_A_VALID_STATUS",
                reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
                consolidated_slot=-1,
                consolidated_block_time=-1,
                reconciled_signature="",
                selected_source_family="",
                contributing_source_count=0,
            )
        )


def test_build_migration_measurement_record_assigns_migration_family():
    record = build_migration_measurement_record(
        **_measured_kwargs()
    )
    assert isinstance(record, Stage25MigrationMeasurement)
    assert record.measurement_family == MEASUREMENT_FAMILY_MIGRATION
    assert record.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert record.reconciled_signature == "sig_record_validator_001"
    assert record.selected_source_family == SOURCE_FAMILY_BIRDEYE


# ---------------------------------------------------------------------------
# Downstream-blocking predicate (no ATH logic implemented yet)
# ---------------------------------------------------------------------------


def test_ambiguous_migration_blocks_measured_ath():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert migration_measurement_blocks_measured_ath(measurement)


def test_missing_migration_blocks_measured_ath():
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, ())
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert migration_measurement_blocks_measured_ath(measurement)


def test_unsupported_migration_blocks_measured_ath():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_UNSUPPORTED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_UNSUPPORTED
    assert migration_measurement_blocks_measured_ath(measurement)


def test_rejected_migration_blocks_measured_ath():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_MALFORMED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_REJECTED
    assert migration_measurement_blocks_measured_ath(measurement)


def test_measured_migration_does_not_block_measured_ath():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert not migration_measurement_blocks_measured_ath(measurement)


# ---------------------------------------------------------------------------
# Identity of measurer name / version
# ---------------------------------------------------------------------------


def test_measurement_records_measurer_name_and_version():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.measurer_name == STAGE25_MIGRATION_MEASURER_NAME
    assert measurement.measurer_version == STAGE25_MIGRATION_MEASURER_VERSION
    assert measurement.schema_version == DEFAULT_SCHEMA_VERSION
    assert measurement.threshold_version == DEFAULT_THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Multi-token reconciliation determinism
# ---------------------------------------------------------------------------


def test_measure_migrations_per_token_measurement_status_correctness():
    obs_a = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_b_partial = make_migration_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PARTIAL,
        block_time=-1,
    )
    obs_c_absent = make_migration_observation(
        token_mint=SAMPLE_TOKEN_MINT_C,
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurements = measure_migrations(
        (obs_a, obs_b_partial, obs_c_absent)
    )
    by_token = {m.token_mint: m for m in measurements}
    assert by_token[SAMPLE_TOKEN_MINT_A].measurement_status == (
        MEASUREMENT_STATUS_MEASURED
    )
    assert by_token[SAMPLE_TOKEN_MINT_B].measurement_status == (
        MEASUREMENT_STATUS_PARTIAL
    )
    assert by_token[SAMPLE_TOKEN_MINT_C].measurement_status == (
        MEASUREMENT_STATUS_MISSING
    )


def test_measure_migrations_returns_immutable_measurements():
    obs = make_migration_observation()
    measurements = measure_migrations((obs,))
    record = measurements[0]
    with pytest.raises(AttributeError):
        record.token_mint = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Three-source agreement: contributing_source_count semantics
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# First-class field promotion (Stage 25.2 audit remediation)
# ---------------------------------------------------------------------------


def test_disagreement_emits_empty_reconciled_signature_and_source_family():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_000
        + MIGRATION_TIMESTAMP_TOLERANCE_SECONDS
        + 1,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_same_source_conflict_emits_empty_reconciled_signature_and_source_family():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG,
        block_time=1_750_000_000,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
        block_time=1_750_000_500,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b)
    )
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_all_absent_emits_no_sources_reconciliation_status():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_all_unsupported_emits_no_sources_reconciliation_status():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_UNSUPPORTED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_partial_emits_no_sources_reconciliation_status():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        block_time=-1,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_ambiguous_status_emits_ambiguous_reconciliation_status():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert measurement.reconciled_signature == ""
    assert measurement.selected_source_family == ""


def test_consolidated_block_time_is_the_first_class_reconciled_block_time():
    """The audit confirmed Stage 25.2 must NOT add a duplicate
    ``reconciled_block_time_unix`` field. ``consolidated_block_time``
    is the first-class equivalent.
    """
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.consolidated_block_time == obs.block_time
    assert not hasattr(measurement, "reconciled_block_time_unix")


def test_consolidated_slot_is_the_first_class_selected_slot():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert measurement.consolidated_slot == obs.slot
    assert not hasattr(measurement, "reconciled_slot")


def test_evidence_no_longer_carries_promoted_fields():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert "reconciliation_status" not in measurement.evidence
    assert "reconciled_signature" not in measurement.evidence
    assert "selected_source_family" not in measurement.evidence
    assert "reconciled_block_time_unix" not in measurement.evidence


def test_evidence_still_carries_observation_diagnostics():
    obs = make_migration_observation()
    measurement = measure_migration_for_token(SAMPLE_TOKEN_MINT_A, (obs,))
    assert "observed_source_families" in measurement.evidence
    assert "contributing_source_families" in measurement.evidence
    assert "observation_count" in measurement.evidence
    assert "duplicate_collapsed_count" in measurement.evidence


def test_three_sources_agree_yields_three_contributors():
    obs_a = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        block_time=1_750_000_000,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        block_time=1_750_000_002,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    obs_c = make_migration_observation(
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
        block_time=1_750_000_005,
        migration_signature=SAMPLE_MIGRATION_SIG_THIRD,
    )
    measurement = measure_migration_for_token(
        SAMPLE_TOKEN_MINT_A, (obs_a, obs_b, obs_c)
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.contributing_source_count == 3
    assert measurement.consolidated_block_time == 1_750_000_000
