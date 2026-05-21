"""Stage 25.3 price-window projector tests.

Pins:

  * MEASURED migration + observation before
    ``consolidated_block_time`` -> ``PRE_MIGRATION_EXCLUDED``.
  * MEASURED migration + observation exactly at
    ``consolidated_block_time`` -> ``POST_MIGRATION_PRIMARY``.
  * MEASURED migration + observation within the primary window
    -> ``POST_MIGRATION_PRIMARY``.
  * MEASURED migration + observation after the primary window
    -> ``POST_MIGRATION_EXTENDED``.
  * Missing / ambiguous / unsupported / rejected migration
    -> ``UNKNOWN_WINDOW``.
  * Partial migration without a usable ``consolidated_block_time``
    -> ``UNKNOWN_WINDOW``.
  * Missing ``observed_at_utc`` -> ``UNKNOWN_WINDOW``.
  * Token mismatch between price observation and migration measurement
    raises ``Stage25ContractError``.
  * ``source_status = PRESENT`` with ``price = None`` is still rejected
    through the model helper.
  * ``price = 0`` without ``PRICE_OBSERVED_ZERO`` rejected.
  * ``price = 0`` with ``PRICE_OBSERVED_ZERO`` accepted.
  * Non-PRESENT source_status with ``price = None`` produces a window
    observation that preserves the price / status verbatim.
  * ``PRE_MIGRATION_EXCLUDED`` observations preserve their price but
    carry the exclusion reason code.
  * Observation hash is deterministic across two equivalent builds.
  * Observation hash changes when ``window_kind`` changes.
  * Observation hash changes when ``observed_at_utc`` changes.
  * ``build_price_window_observations`` groups migrations by token.
  * A token with no migration measurement gets ``UNKNOWN_WINDOW`` and
    the ``PRICE_WINDOW_MIGRATION_NOT_MEASURED`` reason code.
  * Input observations are never mutated by the projector.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_NOT_APPLICABLE,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_UNSUPPORTED,
    POST_MIGRATION_PRIMARY_WINDOW_SECONDS,
    PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED,
    REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING,
    REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY,
    REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION,
    RECONCILIATION_STATUS_AMBIGUOUS,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    STAGE25_PRICE_WINDOW_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25PriceWindowObservation,
    build_price_window_observation_record,
)
from PHX2.stage25.price_window import (
    build_price_window_observation,
    build_price_window_observations,
    build_price_window_observations_for_token,
    classify_price_window_kind,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_MIGRATION_BLOCK_TIME,
    SAMPLE_MIGRATION_SLOT,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_measured_migration_measurement,
    make_price_observation,
    make_unmeasured_migration_measurement,
)


# ---------------------------------------------------------------------------
# classify_price_window_kind
# ---------------------------------------------------------------------------


def test_classify_pre_migration_returns_excluded():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME - 60,
    )
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    )


def test_classify_exactly_at_consolidated_block_time_is_primary():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME,
    )
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
    )


def test_classify_within_primary_window_is_primary():
    migration = make_measured_migration_measurement()
    inside = (
        SAMPLE_MIGRATION_BLOCK_TIME + POST_MIGRATION_PRIMARY_WINDOW_SECONDS
    )
    observation = make_price_observation(block_time=inside)
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
    )


def test_classify_after_primary_window_is_extended():
    migration = make_measured_migration_measurement()
    outside = (
        SAMPLE_MIGRATION_BLOCK_TIME
        + POST_MIGRATION_PRIMARY_WINDOW_SECONDS
        + 1
    )
    observation = make_price_observation(block_time=outside)
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED
    )


@pytest.mark.parametrize(
    "status",
    [
        MEASUREMENT_STATUS_AMBIGUOUS,
        MEASUREMENT_STATUS_REJECTED,
        MEASUREMENT_STATUS_UNSUPPORTED,
        MEASUREMENT_STATUS_NOT_APPLICABLE,
        MEASUREMENT_STATUS_MISSING,
    ],
)
def test_classify_unmeasured_migration_returns_unknown(status):
    if status == MEASUREMENT_STATUS_AMBIGUOUS:
        migration = make_unmeasured_migration_measurement(
            measurement_status=status,
            reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS,
        )
    else:
        migration = make_unmeasured_migration_measurement(
            measurement_status=status,
        )
    observation = make_price_observation()
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    )


def test_classify_partial_migration_without_usable_block_time_is_unknown():
    migration = make_unmeasured_migration_measurement(
        measurement_status=MEASUREMENT_STATUS_PARTIAL,
    )
    observation = make_price_observation()
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    )


def test_classify_missing_observed_at_utc_is_unknown():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        observed_at_utc="",
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
    )
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    )


def test_classify_observation_block_time_absent_is_unknown():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(block_time=-1)
    assert classify_price_window_kind(observation, migration) == (
        PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    )


# ---------------------------------------------------------------------------
# build_price_window_observation
# ---------------------------------------------------------------------------


def test_build_window_observation_returns_namedtuple():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10
    )
    record = build_price_window_observation(observation, migration)
    assert isinstance(record, Stage25PriceWindowObservation)
    assert record.window_kind == PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
    assert record.price == observation.price
    assert record.source_status == observation.source_status


def test_build_window_observation_token_mismatch_rejected():
    migration = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A
    )
    observation = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    with pytest.raises(Stage25ContractError):
        build_price_window_observation(observation, migration)


def test_build_window_observation_preserves_partial_status_with_reason_code():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        price=42,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
    )
    record = build_price_window_observation(observation, migration)
    assert record.source_status == SOURCE_STATUS_PARTIAL
    assert (
        REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS
        in record.reason_codes
    )


def test_build_window_observation_preserves_ambiguous_status_with_reason_code():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
        price=None,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
    )
    record = build_price_window_observation(observation, migration)
    assert record.source_status == SOURCE_STATUS_AMBIGUOUS
    assert (
        REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS
        in record.reason_codes
    )
    assert record.price is None


def test_build_window_observation_pre_migration_preserves_price():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        price=1_234,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME - 10,
    )
    record = build_price_window_observation(observation, migration)
    assert record.price == 1_234
    assert record.window_kind == PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    assert (
        REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED
        in record.reason_codes
    )


def test_build_window_observation_observed_at_missing_carries_reason_code():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        observed_at_utc="",
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
    )
    record = build_price_window_observation(observation, migration)
    assert record.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    assert (
        REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING
        in record.reason_codes
    )


def test_build_window_observation_unknown_migration_carries_reason_code():
    migration = make_unmeasured_migration_measurement(
        measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
        reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS,
    )
    observation = make_price_observation()
    record = build_price_window_observation(observation, migration)
    assert record.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    assert (
        REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION in record.reason_codes
    )


def test_build_window_observation_missing_migration_carries_not_measured_code():
    migration = make_unmeasured_migration_measurement(
        measurement_status=MEASUREMENT_STATUS_MISSING,
    )
    observation = make_price_observation()
    record = build_price_window_observation(observation, migration)
    assert record.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    assert (
        REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED
        in record.reason_codes
    )


def test_build_window_observation_attaches_post_primary_reason_code():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 30
    )
    record = build_price_window_observation(observation, migration)
    assert (
        REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY
        in record.reason_codes
    )


def test_build_window_observation_attaches_post_extended_reason_code():
    migration = make_measured_migration_measurement()
    block_time = (
        SAMPLE_MIGRATION_BLOCK_TIME
        + POST_MIGRATION_PRIMARY_WINDOW_SECONDS
        + 30
    )
    observation = make_price_observation(block_time=block_time)
    record = build_price_window_observation(observation, migration)
    assert record.window_kind == PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED
    assert (
        REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED
        in record.reason_codes
    )


# ---------------------------------------------------------------------------
# Model helper enforcement
# ---------------------------------------------------------------------------


def test_record_helper_rejects_present_with_none_price():
    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="BIRDEYE",
            source_status=SOURCE_STATUS_PRESENT,
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=None,
            quote_denomination="USD_MICRO",
            reason_codes=(),
            evidence={},
        )


def test_record_helper_rejects_zero_price_without_explicit_reason():
    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="BIRDEYE",
            source_status=SOURCE_STATUS_PRESENT,
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=0,
            quote_denomination="USD_MICRO",
            reason_codes=(),
            evidence={},
        )


def test_record_helper_accepts_zero_price_with_explicit_reason():
    record = build_price_window_observation_record(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family="BIRDEYE",
        source_status=SOURCE_STATUS_PRESENT,
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        observed_at_utc=FIXED_CLOCK_UTC,
        slot=1,
        block_time=2,
        price=0,
        quote_denomination="USD_MICRO",
        reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,),
        evidence={},
    )
    assert record.price == 0


def test_record_helper_rejects_bool_as_price():
    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="BIRDEYE",
            source_status=SOURCE_STATUS_PRESENT,
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=True,  # type: ignore[arg-type]
            quote_denomination="USD_MICRO",
            reason_codes=(),
            evidence={},
        )


def test_record_helper_rejects_negative_price():
    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="BIRDEYE",
            source_status=SOURCE_STATUS_PRESENT,
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=-5,
            quote_denomination="USD_MICRO",
            reason_codes=(),
            evidence={},
        )


def test_record_helper_rejects_unknown_window_kind():
    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="BIRDEYE",
            source_status=SOURCE_STATUS_PRESENT,
            window_kind="NOT_A_REAL_WINDOW",
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=1,
            quote_denomination="USD_MICRO",
            reason_codes=(),
            evidence={},
        )


# ---------------------------------------------------------------------------
# Hash determinism / divergence
# ---------------------------------------------------------------------------


def test_window_observation_hash_is_deterministic():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10
    )
    first = build_price_window_observation(observation, migration)
    second = build_price_window_observation(observation, migration)
    assert first.observation_hash == second.observation_hash


def test_window_observation_hash_changes_with_window_kind():
    migration = make_measured_migration_measurement()
    primary = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10
    )
    extended = make_price_observation(
        block_time=(
            SAMPLE_MIGRATION_BLOCK_TIME
            + POST_MIGRATION_PRIMARY_WINDOW_SECONDS
            + 1
        )
    )
    primary_record = build_price_window_observation(primary, migration)
    extended_record = build_price_window_observation(extended, migration)
    assert primary_record.window_kind != extended_record.window_kind
    assert (
        primary_record.observation_hash
        != extended_record.observation_hash
    )


def test_window_observation_hash_changes_with_observed_at_utc():
    migration = make_measured_migration_measurement()
    obs_a = make_price_observation(
        observed_at_utc="2026-01-01T00:00:00Z",
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
    )
    obs_b = make_price_observation(
        observed_at_utc="2026-01-01T00:01:00Z",
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
    )
    record_a = build_price_window_observation(obs_a, migration)
    record_b = build_price_window_observation(obs_b, migration)
    assert record_a.observation_hash != record_b.observation_hash


def test_window_observation_canonical_body_includes_window_kind():
    # Two records that differ only in their window_kind must hash
    # differently; this guards against forgetting to bind window_kind
    # into the canonical hash body.
    base = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10
    )
    rebuilt = build_price_window_observation_record(
        token_mint=base.token_mint,
        source_family=base.source_family,
        source_status=base.source_status,
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
        observed_at_utc=base.observed_at_utc,
        slot=base.slot,
        block_time=base.block_time,
        price=base.price,
        quote_denomination=base.quote_denomination,
        reason_codes=base.reason_codes,
        evidence={},
    )
    other = build_price_window_observation_record(
        token_mint=base.token_mint,
        source_family=base.source_family,
        source_status=base.source_status,
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        observed_at_utc=base.observed_at_utc,
        slot=base.slot,
        block_time=base.block_time,
        price=base.price,
        quote_denomination=base.quote_denomination,
        reason_codes=base.reason_codes,
        evidence={},
    )
    assert rebuilt.observation_hash != other.observation_hash


# ---------------------------------------------------------------------------
# build_price_window_observations_for_token
# ---------------------------------------------------------------------------


def test_for_token_rejects_mismatched_migration_token():
    migration = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A
    )
    observation = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    with pytest.raises(Stage25ContractError):
        build_price_window_observations_for_token(
            SAMPLE_TOKEN_MINT_B, (observation,), migration
        )


def test_for_token_rejects_observation_with_other_token():
    migration = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A
    )
    observation = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    with pytest.raises(Stage25ContractError):
        build_price_window_observations_for_token(
            SAMPLE_TOKEN_MINT_A, (observation,), migration
        )


def test_for_token_returns_canonical_order():
    migration = make_measured_migration_measurement()
    a = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5, price=1
    )
    b = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5, price=2
    )
    first = build_price_window_observations_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b), migration
    )
    second = build_price_window_observations_for_token(
        SAMPLE_TOKEN_MINT_A, (b, a), migration
    )
    assert first == second


def test_for_token_rejects_non_tuple_inputs():
    migration = make_measured_migration_measurement()
    with pytest.raises(Stage25ContractError):
        build_price_window_observations_for_token(
            SAMPLE_TOKEN_MINT_A,
            [make_price_observation()],  # type: ignore[arg-type]
            migration,
        )


# ---------------------------------------------------------------------------
# build_price_window_observations
# ---------------------------------------------------------------------------


def test_batch_projector_groups_by_token():
    migration_a = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A
    )
    migration_b = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_B,
        consolidated_block_time=SAMPLE_MIGRATION_BLOCK_TIME + 1_000,
        consolidated_slot=SAMPLE_MIGRATION_SLOT + 1,
        reconciled_signature="sig_migration_synthetic_alt",
    )
    obs_a = make_price_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 30,
    )
    obs_b = make_price_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 1_050,
    )
    records = build_price_window_observations(
        (obs_a, obs_b),
        (migration_a, migration_b),
    )
    assert len(records) == 2
    tokens = [r.token_mint for r in records]
    assert tokens == sorted(tokens)


def test_batch_projector_token_with_no_migration_is_unknown():
    obs = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    records = build_price_window_observations((obs,), ())
    assert len(records) == 1
    record = records[0]
    assert record.window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    assert (
        REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED
        in record.reason_codes
    )


def test_batch_projector_rejects_duplicate_migration_for_token():
    migration_a1 = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A
    )
    migration_a2 = make_measured_migration_measurement(
        token_mint=SAMPLE_TOKEN_MINT_A,
        consolidated_block_time=SAMPLE_MIGRATION_BLOCK_TIME + 60,
    )
    obs = make_price_observation()
    with pytest.raises(Stage25ContractError):
        build_price_window_observations(
            (obs,), (migration_a1, migration_a2)
        )


def test_batch_projector_rejects_non_tuple_inputs():
    with pytest.raises(Stage25ContractError):
        build_price_window_observations(
            [make_price_observation()],  # type: ignore[arg-type]
            (),
        )
    with pytest.raises(Stage25ContractError):
        build_price_window_observations(
            (),
            [make_measured_migration_measurement()],  # type: ignore[arg-type]
        )


def test_batch_projector_does_not_mutate_inputs():
    migration = make_measured_migration_measurement()
    obs_a = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10, price=1
    )
    obs_b = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 20, price=2
    )
    observations = (obs_b, obs_a)
    migrations = (migration,)
    snap_obs = tuple(observations)
    snap_mig = tuple(migrations)
    build_price_window_observations(observations, migrations)
    assert observations == snap_obs
    assert migrations == snap_mig


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_window_version_is_locked():
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5
    )
    record = build_price_window_observation(observation, migration)
    assert (
        record.evidence["window_version"] == STAGE25_PRICE_WINDOW_VERSION
    )
    assert (
        record.evidence["threshold_version"] == DEFAULT_THRESHOLD_VERSION
    )


# ---------------------------------------------------------------------------
# source_status survives projection verbatim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,price_kwargs",
    [
        (SOURCE_STATUS_PRESENT, {"price": 1_000}),
        (SOURCE_STATUS_PARTIAL, {"price": 1_000}),
        (SOURCE_STATUS_PARTIAL, {"price": None}),
        (SOURCE_STATUS_AMBIGUOUS, {"price": None}),
    ],
)
def test_source_status_survives_projection_verbatim(status, price_kwargs):
    """The Stage 25.3 projector preserves the upstream
    ``Stage25PriceObservation.source_status`` verbatim on the
    resulting ``Stage25PriceWindowObservation``. Stage 25.4+ ATH
    reconcilers rely on this to exclude non-PRESENT observations
    from a measured ATH.
    """
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        source_status=status,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
        **price_kwargs,
    )
    record = build_price_window_observation(observation, migration)
    assert record.source_status == status
    assert record.price == observation.price


def test_window_observation_hash_changes_with_source_status_only():
    """A window observation whose source_status differs from another
    on every other axis must hash differently. Pins the
    source_status -> hash dependency at the projector level.
    """
    migration = make_measured_migration_measurement()
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PRESENT,
        price=1_000,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
    )
    record_present = build_price_window_observation(observation, migration)

    sibling = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        price=1_000,
        block_time=SAMPLE_MIGRATION_BLOCK_TIME + 5,
    )
    record_partial = build_price_window_observation(sibling, migration)

    assert record_present.source_status != record_partial.source_status
    assert (
        record_present.observation_hash
        != record_partial.observation_hash
    )
