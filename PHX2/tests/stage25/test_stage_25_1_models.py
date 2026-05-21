"""Stage 25.1 model tests.

Pins:

  * Immutability of Stage 25 NamedTuple records.
  * Closed-set validation on per-record builders.
  * Deterministic canonical-JSON hashing (sorted keys, no
    whitespace separators, ASCII-safe).
  * ``observation_hash`` is stable across two builds of the same
    logical observation.
  * ``observation_hash`` is stable under dict-key reordering on
    the ``evidence`` mapping.
  * None preservation: ``None`` prices NEVER coerce to ``0``.
  * Negative price rejection.
  * Boolean values are NOT accepted as int prices.
  * Canonical-JSON rejects NaN / Infinity.
  * Price=0 requires the explicit ``PRICE_OBSERVED_ZERO`` reason
    code.
  * ATH measurement / candidate / reconciliation / rejection /
    unified records are NamedTuples and immutable.
  * Measurement / candidate / reconciliation hashes are
    deterministic.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    CONFIDENCE_LEVEL_HIGH,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_FAMILY_MIGRATION,
    QUOTE_DENOMINATION_USD_MICRO,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    RECONCILIATION_STATUS_AGREED,
    REJECTION_REASON_INPUT_MALFORMED,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_PRESENT,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    Stage25ATHMeasurement,
    Stage25MeasurementInput,
    Stage25MeasurementRejection,
    Stage25MigrationMeasurement,
    Stage25MigrationObservation,
    Stage25PriceObservation,
    Stage25PriceWindowObservation,
    Stage25RunnerResult,
    Stage25SourceReconciliation,
    Stage25UnifiedMeasurement,
    build_ath_candidate_record,
    build_measurement_input,
    build_measurement_rejection,
    build_migration_observation,
    build_price_observation,
    build_source_reconciliation_record,
    canonical_json,
    compute_candidate_hash,
    compute_measurement_hash,
    compute_observation_hash,
    compute_reconciliation_hash,
    stage25_hash,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_TOKEN_MINT_A,
    make_migration_observation,
    make_price_observation,
)


# ---------------------------------------------------------------------------
# NamedTuple immutability
# ---------------------------------------------------------------------------


def test_migration_observation_is_immutable():
    record = make_migration_observation()
    with pytest.raises(AttributeError):
        record.token_mint = "different"  # type: ignore[misc]


def test_migration_observation_is_a_namedtuple():
    assert issubclass(Stage25MigrationObservation, tuple)


def test_price_observation_is_a_namedtuple():
    assert issubclass(Stage25PriceObservation, tuple)


def test_measurement_input_is_a_namedtuple():
    assert issubclass(Stage25MeasurementInput, tuple)


def test_migration_measurement_is_a_namedtuple():
    assert issubclass(Stage25MigrationMeasurement, tuple)


def test_ath_measurement_is_a_namedtuple():
    assert issubclass(Stage25ATHMeasurement, tuple)


def test_ath_candidate_is_a_namedtuple():
    assert issubclass(Stage25ATHCandidate, tuple)


def test_source_reconciliation_is_a_namedtuple():
    assert issubclass(Stage25SourceReconciliation, tuple)


def test_measurement_rejection_is_a_namedtuple():
    assert issubclass(Stage25MeasurementRejection, tuple)


def test_unified_measurement_is_a_namedtuple():
    assert issubclass(Stage25UnifiedMeasurement, tuple)


def test_runner_result_is_a_namedtuple():
    assert issubclass(Stage25RunnerResult, tuple)


def test_price_window_observation_is_a_namedtuple():
    assert issubclass(Stage25PriceWindowObservation, tuple)


def test_price_observation_is_immutable():
    record = make_price_observation()
    with pytest.raises(AttributeError):
        record.price = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Canonical-JSON
# ---------------------------------------------------------------------------


def test_canonical_json_sorts_dict_keys():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1}'


def test_canonical_json_supports_tuple_and_list():
    a = canonical_json(("x", "y"))
    b = canonical_json(["x", "y"])
    assert a == b
    assert a == '["x","y"]'


def test_canonical_json_rejects_nan():
    with pytest.raises(Stage25ContractError):
        canonical_json(float("nan"))


def test_canonical_json_rejects_infinity():
    with pytest.raises(Stage25ContractError):
        canonical_json(float("inf"))


def test_canonical_json_rejects_non_string_dict_key():
    with pytest.raises(Stage25ContractError):
        canonical_json({1: "value"})


def test_canonical_json_rejects_unsupported_type():
    class Custom:
        pass

    with pytest.raises(Stage25ContractError):
        canonical_json(Custom())


# ---------------------------------------------------------------------------
# stage25_hash determinism
# ---------------------------------------------------------------------------


def test_stage25_hash_is_deterministic():
    body = {"a": 1, "b": [1, 2, 3], "c": "x"}
    assert stage25_hash(body) == stage25_hash(body)


def test_stage25_hash_is_dict_order_independent():
    a = stage25_hash({"a": 1, "b": 2})
    b = stage25_hash({"b": 2, "a": 1})
    assert a == b


def test_stage25_hash_differs_when_value_differs():
    a = stage25_hash({"a": 1})
    b = stage25_hash({"a": 2})
    assert a != b


# ---------------------------------------------------------------------------
# Observation hashing
# ---------------------------------------------------------------------------


def test_compute_observation_hash_matches_migration_record_hash():
    record = make_migration_observation()
    assert compute_observation_hash(record) == record.observation_hash


def test_compute_observation_hash_matches_price_record_hash():
    record = make_price_observation()
    assert compute_observation_hash(record) == record.observation_hash


def test_two_identical_migration_observations_produce_same_hash():
    a = make_migration_observation()
    b = make_migration_observation()
    assert a.observation_hash == b.observation_hash


def test_changed_token_mint_changes_migration_observation_hash():
    a = make_migration_observation(token_mint="MintAlpha111111111111111111111111111111111")
    b = make_migration_observation(token_mint="MintBeta111111111111111111111111111111111x")
    assert a.observation_hash != b.observation_hash


def test_evidence_key_reordering_does_not_change_observation_hash():
    a = make_migration_observation(
        evidence=MappingProxyType({"x": 1, "y": 2}),
    )
    b = make_migration_observation(
        evidence=MappingProxyType({"y": 2, "x": 1}),
    )
    assert a.observation_hash == b.observation_hash


def test_compute_observation_hash_rejects_unknown_type():
    with pytest.raises(Stage25ContractError):
        compute_observation_hash(object())


# ---------------------------------------------------------------------------
# Builder closed-set validation
# ---------------------------------------------------------------------------


def test_build_migration_observation_rejects_unknown_source_family():
    with pytest.raises(Stage25ContractError):
        build_migration_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family="NOT_A_REAL_SOURCE",
            source_status=SOURCE_STATUS_PRESENT,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            migration_signature="sig",
            migration_pool="pool",
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_migration_observation_rejects_unknown_source_status():
    with pytest.raises(Stage25ContractError):
        build_migration_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_BIRDEYE,
            source_status="BOGUS_STATUS",
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            migration_signature="sig",
            migration_pool="pool",
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_migration_observation_rejects_empty_token_mint():
    with pytest.raises(Stage25ContractError):
        build_migration_observation(
            token_mint="",
            source_family=SOURCE_FAMILY_BIRDEYE,
            source_status=SOURCE_STATUS_ABSENT,
            observed_at_utc="",
            slot=-1,
            block_time=-1,
            migration_signature="",
            migration_pool="",
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_migration_observation_rejects_slot_below_minus_one():
    with pytest.raises(Stage25ContractError):
        build_migration_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_BIRDEYE,
            source_status=SOURCE_STATUS_ABSENT,
            observed_at_utc="",
            slot=-2,
            block_time=-1,
            migration_signature="",
            migration_pool="",
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


# ---------------------------------------------------------------------------
# Price None / amount semantics
# ---------------------------------------------------------------------------


def test_build_price_observation_preserves_none_price():
    record = build_price_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_ABSENT,
        observed_at_utc="",
        slot=-1,
        block_time=-1,
        price=None,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        provider_id="provider",
        reason_codes=(),
        evidence=MappingProxyType({}),
        input_missing_fields=(),
    )
    assert record.price is None
    assert record.price != 0


def test_build_price_observation_rejects_negative_price():
    with pytest.raises(Stage25ContractError):
        build_price_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_PRESENT,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            price=-1,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_price_observation_rejects_bool_price():
    with pytest.raises(Stage25ContractError):
        build_price_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_PRESENT,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            price=True,  # type: ignore[arg-type]
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_price_observation_rejects_zero_without_explicit_reason():
    with pytest.raises(Stage25ContractError):
        build_price_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_PRESENT,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            price=0,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_price_observation_accepts_zero_with_explicit_reason():
    record = build_price_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PRESENT,
        observed_at_utc=FIXED_CLOCK_UTC,
        slot=100,
        block_time=200,
        price=0,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        provider_id="provider",
        reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,),
        evidence=MappingProxyType({}),
        input_missing_fields=(),
    )
    assert record.price == 0
    assert REASON_CODE_PRICE_OBSERVED_ZERO in record.reason_codes


def test_build_price_observation_rejects_present_with_none_price():
    """PRESENT means the source claims it observed the price; ``None``
    is reserved for non-PRESENT statuses (ABSENT / PARTIAL /
    AMBIGUOUS / UNSUPPORTED / MALFORMED / DECODE_FAILED).
    """
    with pytest.raises(Stage25ContractError):
        build_price_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_PRESENT,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=100,
            block_time=200,
            price=None,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_price_observation_accepts_each_non_present_status_with_none_price():
    from PHX2.stage25.constants import (
        SOURCE_STATUS_AMBIGUOUS,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_PARTIAL,
        SOURCE_STATUS_UNSUPPORTED,
    )

    for non_present_status in (
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_PARTIAL,
        SOURCE_STATUS_AMBIGUOUS,
        SOURCE_STATUS_UNSUPPORTED,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
    ):
        record = build_price_observation(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=non_present_status,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=-1,
            block_time=-1,
            price=None,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            provider_id="provider",
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )
        assert record.price is None
        assert record.source_status == non_present_status


# ---------------------------------------------------------------------------
# MeasurementInput shape
# ---------------------------------------------------------------------------


def test_build_measurement_input_round_trips_tuples():
    migration = make_migration_observation()
    price = make_price_observation()
    container = build_measurement_input(
        token_mint=SAMPLE_TOKEN_MINT_A,
        schema_version=DEFAULT_SCHEMA_VERSION,
        migration_observations=(migration,),
        price_observations=(price,),
    )
    assert isinstance(container.migration_observations, tuple)
    assert isinstance(container.price_observations, tuple)
    assert container.migration_observations == (migration,)
    assert container.price_observations == (price,)


def test_build_measurement_input_rejects_non_tuple_observations():
    migration = make_migration_observation()
    with pytest.raises(Stage25ContractError):
        build_measurement_input(
            token_mint=SAMPLE_TOKEN_MINT_A,
            schema_version=DEFAULT_SCHEMA_VERSION,
            migration_observations=[migration],  # type: ignore[arg-type]
            price_observations=(),
        )


def test_build_measurement_input_rejects_wrong_observation_type():
    price = make_price_observation()
    with pytest.raises(Stage25ContractError):
        build_measurement_input(
            token_mint=SAMPLE_TOKEN_MINT_A,
            schema_version=DEFAULT_SCHEMA_VERSION,
            migration_observations=(price,),  # type: ignore[arg-type]
            price_observations=(),
        )


# ---------------------------------------------------------------------------
# ATH candidate + reconciliation builders
# ---------------------------------------------------------------------------


def test_build_ath_candidate_record_round_trips_with_hash():
    candidate = build_ath_candidate_record(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        peak_observed_at_utc=FIXED_CLOCK_UTC,
        peak_slot=251_000_500,
        peak_block_time=1_750_001_000,
        peak_price=999_999,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        reason_codes=("source_reported",),
        evidence=MappingProxyType({"k": "v"}),
        input_missing_fields=(),
    )
    assert isinstance(candidate, Stage25ATHCandidate)
    assert candidate.candidate_hash != ""
    # Recomputing the hash from the same projection must match.
    expected = compute_candidate_hash(
        token_mint=candidate.token_mint,
        source_family=candidate.source_family,
        candidate_kind=candidate.candidate_kind,
        peak_observed_at_utc=candidate.peak_observed_at_utc,
        peak_slot=candidate.peak_slot,
        peak_block_time=candidate.peak_block_time,
        peak_price=candidate.peak_price,
        quote_denomination=candidate.quote_denomination,
        reason_codes=candidate.reason_codes,
        evidence=candidate.evidence,
        input_missing_fields=candidate.input_missing_fields,
    )
    assert candidate.candidate_hash == expected


def test_build_ath_candidate_record_rejects_zero_peak_without_explicit_reason():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_BIRDEYE,
            candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
            peak_observed_at_utc=FIXED_CLOCK_UTC,
            peak_slot=251_000_500,
            peak_block_time=1_750_001_000,
            peak_price=0,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_source_reconciliation_record_round_trips_with_hash():
    reconciliation = build_source_reconciliation_record(
        measurement_family=MEASUREMENT_FAMILY_MIGRATION,
        reconciliation_status=RECONCILIATION_STATUS_AGREED,
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_families=(SOURCE_FAMILY_BIRDEYE, SOURCE_FAMILY_DEXSCREENER),
        contributing_source_count=2,
        disagreeing_source_count=0,
        reason_codes=(),
        evidence=MappingProxyType({}),
    )
    assert isinstance(reconciliation, Stage25SourceReconciliation)
    expected = compute_reconciliation_hash(
        measurement_family=reconciliation.measurement_family,
        reconciliation_status=reconciliation.reconciliation_status,
        token_mint=reconciliation.token_mint,
        source_families=reconciliation.source_families,
        contributing_source_count=reconciliation.contributing_source_count,
        disagreeing_source_count=reconciliation.disagreeing_source_count,
        reason_codes=reconciliation.reason_codes,
        evidence=reconciliation.evidence,
    )
    assert reconciliation.reconciliation_hash == expected


def test_build_source_reconciliation_record_rejects_unknown_source_family():
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(
            measurement_family=MEASUREMENT_FAMILY_MIGRATION,
            reconciliation_status=RECONCILIATION_STATUS_AGREED,
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_families=(SOURCE_FAMILY_BIRDEYE, "NOT_REAL"),
            contributing_source_count=2,
            disagreeing_source_count=0,
            reason_codes=(),
            evidence=MappingProxyType({}),
        )


# ---------------------------------------------------------------------------
# Rejection builder
# ---------------------------------------------------------------------------


def test_build_measurement_rejection_round_trips():
    rejection = build_measurement_rejection(
        rejection_reason=REJECTION_REASON_INPUT_MALFORMED,
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        detail="line 1: malformed JSON",
        reason_codes=(),
    )
    assert isinstance(rejection, Stage25MeasurementRejection)
    assert rejection.rejection_reason == REJECTION_REASON_INPUT_MALFORMED


def test_build_measurement_rejection_accepts_empty_source_family():
    rejection = build_measurement_rejection(
        rejection_reason=REJECTION_REASON_INPUT_MALFORMED,
        token_mint="",
        source_family="",
        detail="file-level error",
        reason_codes=(),
    )
    assert rejection.source_family == ""


def test_build_measurement_rejection_rejects_unknown_reason():
    with pytest.raises(Stage25ContractError):
        build_measurement_rejection(
            rejection_reason="NOT_A_REAL_REASON",
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_BIRDEYE,
            detail="x",
            reason_codes=(),
        )


# ---------------------------------------------------------------------------
# Measurement hash determinism (function-level, no constructed record)
# ---------------------------------------------------------------------------


def test_compute_measurement_hash_is_deterministic():
    a = compute_measurement_hash(
        measurement_family=MEASUREMENT_FAMILY_ATH,
        measurement_status="MEASURED",
        confidence_level=CONFIDENCE_LEVEL_HIGH,
        token_mint=SAMPLE_TOKEN_MINT_A,
        schema_version=DEFAULT_SCHEMA_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        measurer_name="ath_measurer_v0",
        measurer_version="0.1",
        extra=MappingProxyType(
            {"consolidated_peak_price": 1_000_000, "contributing_source_count": 2}
        ),
    )
    b = compute_measurement_hash(
        measurement_family=MEASUREMENT_FAMILY_ATH,
        measurement_status="MEASURED",
        confidence_level=CONFIDENCE_LEVEL_HIGH,
        token_mint=SAMPLE_TOKEN_MINT_A,
        schema_version=DEFAULT_SCHEMA_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        measurer_name="ath_measurer_v0",
        measurer_version="0.1",
        extra=MappingProxyType(
            {"contributing_source_count": 2, "consolidated_peak_price": 1_000_000}
        ),
    )
    assert a == b
