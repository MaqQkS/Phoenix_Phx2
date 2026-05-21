"""Stage 25.6 in-memory runner tests.

Pins:

  * Happy path: a single token with one migration observation and
    two agreeing price observations produces one ``MEASURED``
    migration measurement, one ``AGREED`` source reconciliation, and
    one ``MEASURED`` ATH measurement.
  * No migration observation -> ``UNKNOWN_WINDOW`` price windows and
    no measured ATH.
  * Ambiguous migration -> no measured ATH for that token.
  * Pre-migration price observation -> ``PRE_MIGRATION_EXCLUDED`` and
    no ATH candidate peak from that observation.
  * Two agreeing source candidates -> ``MEASURED`` ATH.
  * Single source -> ``PARTIAL`` (not ``MEASURED``).
  * Source conflict -> ``SOURCE_CONFLICT`` (not ``MEASURED``).
  * Deterministic output: identical inputs + identical injected
    ``created_at_utc`` produce byte-identical canonical summary
    bodies and identical runner-result tuples.
  * Input tuples are never mutated.
  * Runner does not perform any file I/O.
  * Stage25RunnerResult field set is locked.
"""

from __future__ import annotations

import os

import pytest

from PHX2.stage25.constants import (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_PRESENT,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25RunnerResult,
)
from PHX2.stage25.runner import run_stage25_measurement
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_MIGRATION_BLOCK_TIME,
    SAMPLE_MIGRATION_SIG,
    SAMPLE_MIGRATION_SLOT,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_migration_observation,
    make_price_observation,
)


def _migration_obs(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    block_time: int = SAMPLE_MIGRATION_BLOCK_TIME,
    slot: int = SAMPLE_MIGRATION_SLOT,
    migration_signature: str = SAMPLE_MIGRATION_SIG,
    source_status: str = SOURCE_STATUS_PRESENT,
):
    return make_migration_observation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        block_time=block_time,
        slot=slot,
        migration_signature=migration_signature,
    )


def _price_obs(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_DEXSCREENER,
    block_time: int,
    price: int,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_010,
    source_status: str = SOURCE_STATUS_PRESENT,
):
    return make_price_observation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        block_time=block_time,
        slot=slot,
        price=price,
    )


# ---------------------------------------------------------------------------
# Runner result shape
# ---------------------------------------------------------------------------


def test_runner_result_field_set_is_locked():
    """Stage 25.6 locks the runner-result field set; pin it explicitly."""
    assert Stage25RunnerResult._fields == (
        "migration_observations",
        "migration_measurements",
        "price_window_observations",
        "ath_candidates",
        "source_reconciliations",
        "ath_measurements",
        "rejections",
        "summary",
        "created_at_utc",
        "runner_name",
        "runner_version",
        "threshold_version",
        "schema_version",
        "input_token_count",
        "input_rejection_count",
    )


def test_runner_result_carries_locked_version_axes():
    result = run_stage25_measurement(
        migration_observations=(),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.runner_name == STAGE25_RUNNER_NAME
    assert result.runner_version == STAGE25_RUNNER_VERSION
    assert result.threshold_version == DEFAULT_THRESHOLD_VERSION
    assert result.schema_version == DEFAULT_SCHEMA_VERSION
    assert result.created_at_utc == FIXED_CLOCK_UTC


def test_empty_inputs_produce_empty_tuples_and_zero_counts():
    result = run_stage25_measurement(
        migration_observations=(),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.migration_observations == ()
    assert result.migration_measurements == ()
    assert result.price_window_observations == ()
    assert result.ath_candidates == ()
    assert result.source_reconciliations == ()
    assert result.ath_measurements == ()
    assert result.rejections == ()
    assert result.input_token_count == 0
    assert result.input_rejection_count == 0


# ---------------------------------------------------------------------------
# Happy path: full pipeline
# ---------------------------------------------------------------------------


def test_happy_path_two_sources_measured_ath():
    migration_observations = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
        ),
    )
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_010_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert len(result.migration_measurements) == 1
    migration = result.migration_measurements[0]
    assert migration.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert migration.confidence_level == CONFIDENCE_LEVEL_HIGH

    assert len(result.price_window_observations) == 2
    for window in result.price_window_observations:
        assert window.window_kind == (
            PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
        )

    assert len(result.ath_candidates) == 2
    assert len(result.source_reconciliations) == 1
    reconciliation = result.source_reconciliations[0]
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )

    assert len(result.ath_measurements) == 1
    ath = result.ath_measurements[0]
    assert ath.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert ath.peak_source_family in {
        SOURCE_FAMILY_BIRDEYE,
        SOURCE_FAMILY_DEXSCREENER,
    }


def test_no_migration_observation_yields_unknown_window_and_unmeasured_ath():
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_005_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=(),
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert len(result.migration_measurements) == 0
    assert all(
        window.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
        for window in result.price_window_observations
    )
    assert len(result.ath_measurements) == 1
    assert result.ath_measurements[0].measurement_status != (
        MEASUREMENT_STATUS_MEASURED
    )


def test_ambiguous_migration_blocks_measured_ath():
    migration_observations = (
        _migration_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            source_status=SOURCE_STATUS_AMBIGUOUS,
        ),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_AMBIGUOUS,
        ),
    )
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_005_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert len(result.migration_measurements) == 1
    migration = result.migration_measurements[0]
    assert migration.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    # Migration not MEASURED -> windows are UNKNOWN_WINDOW.
    assert all(
        window.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
        for window in result.price_window_observations
    )
    # Without eligible windows the candidates fail; no measured ATH.
    assert all(
        ath.measurement_status != MEASUREMENT_STATUS_MEASURED
        for ath in result.ath_measurements
    )


def test_pre_migration_price_observation_excluded():
    migration_observations = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
        ),
    )
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME - 60,
            price=900_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    pre_window = result.price_window_observations[0]
    assert pre_window.window_kind == PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    # No eligible windows -> no measured ATH.
    assert all(
        ath.measurement_status != MEASUREMENT_STATUS_MEASURED
        for ath in result.ath_measurements
    )


def test_single_source_yields_partial_ath():
    migration_observations = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
    )
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    reconciliation = result.source_reconciliations[0]
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    ath = result.ath_measurements[0]
    assert ath.measurement_status == MEASUREMENT_STATUS_PARTIAL


def test_source_conflict_yields_source_conflict_ath():
    migration_observations = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
        ),
    )
    # Two sources with prices an order of magnitude apart: the
    # ppm spread exceeds the MAJOR threshold so the reconciliation
    # records ``DISAGREED_MAJOR``.
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=1_000_000,
        ),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=10_000_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    reconciliation = result.source_reconciliations[0]
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    ath = result.ath_measurements[0]
    assert ath.measurement_status == MEASUREMENT_STATUS_SOURCE_CONFLICT


# ---------------------------------------------------------------------------
# Determinism / no I/O / no mutation
# ---------------------------------------------------------------------------


def test_runner_output_is_deterministic_for_identical_inputs():
    migration_observations = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
        ),
    )
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_BIRDEYE,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_010_000,
        ),
    )
    result_a = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    result_b = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result_a.migration_measurements == result_b.migration_measurements
    assert result_a.price_window_observations == (
        result_b.price_window_observations
    )
    assert result_a.ath_candidates == result_b.ath_candidates
    assert result_a.source_reconciliations == (
        result_b.source_reconciliations
    )
    assert result_a.ath_measurements == result_b.ath_measurements


def test_runner_does_not_mutate_input_tuples():
    migration_observations = (_migration_obs(),)
    price_observations = (
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=2_000_000,
        ),
    )
    migration_snapshot = tuple(migration_observations)
    price_snapshot = tuple(price_observations)
    _ = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert migration_observations == migration_snapshot
    assert price_observations == price_snapshot


def test_runner_does_not_write_files(tmp_path):
    """Stage 25.6 runner is pure: no writer surface is invoked."""
    before = sorted(os.listdir(tmp_path))
    _ = run_stage25_measurement(
        migration_observations=(_migration_obs(),),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    after = sorted(os.listdir(tmp_path))
    assert before == after


def test_runner_rejects_empty_created_at_utc():
    with pytest.raises(Stage25ContractError):
        run_stage25_measurement(
            migration_observations=(),
            price_observations=(),
            created_at_utc="",
        )


def test_runner_rejects_non_tuple_inputs():
    with pytest.raises(Stage25ContractError):
        run_stage25_measurement(
            migration_observations=[_migration_obs()],  # type: ignore[arg-type]
            price_observations=(),
            created_at_utc=FIXED_CLOCK_UTC,
        )
    with pytest.raises(Stage25ContractError):
        run_stage25_measurement(
            migration_observations=(),
            price_observations=[_price_obs(block_time=1, price=1)],  # type: ignore[arg-type]
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_runner_input_token_count_counts_distinct_tokens():
    migration_observations = (
        _migration_obs(token_mint=SAMPLE_TOKEN_MINT_A),
        _migration_obs(
            token_mint=SAMPLE_TOKEN_MINT_B,
            source_family=SOURCE_FAMILY_DEXSCREENER,
        ),
    )
    price_observations = (
        _price_obs(
            token_mint=SAMPLE_TOKEN_MINT_A,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
            price=1_000_000,
        ),
    )
    result = run_stage25_measurement(
        migration_observations=migration_observations,
        price_observations=price_observations,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.input_token_count == 2
