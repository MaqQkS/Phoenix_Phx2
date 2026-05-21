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
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    QUOTE_DENOMINATION_USD_MICRO,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    REJECTION_REASON_INPUT_MALFORMED,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    STAGE25_MIGRATION_MEASURER_NAME,
    STAGE25_MIGRATION_MEASURER_VERSION,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_PARTIAL,
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
    build_migration_measurement_record,
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


def test_price_window_observation_fields_include_source_status():
    """``source_status`` must be a first-class field on the window
    observation so non-PRESENT statuses (``PARTIAL``, ``AMBIGUOUS``,
    ``ABSENT``, ...) survive projection from
    ``Stage25PriceObservation`` verbatim.
    """
    assert "source_status" in Stage25PriceWindowObservation._fields


def test_price_window_observation_fields_match_locked_order():
    """Lock the field order of ``Stage25PriceWindowObservation``.

    The hash projection relies on the canonical body shape, but
    downstream consumers also pin field positions (positional
    construction, ``namedtuple._asdict`` ordering). This test pins
    the exact order so a future reorder is caught explicitly.
    """
    assert Stage25PriceWindowObservation._fields == (
        "token_mint",
        "source_family",
        "source_status",
        "window_kind",
        "observed_at_utc",
        "slot",
        "block_time",
        "price",
        "quote_denomination",
        "reason_codes",
        "evidence",
        "observation_hash",
    )


def test_price_observation_is_immutable():
    record = make_price_observation()
    with pytest.raises(AttributeError):
        record.price = 999  # type: ignore[misc]


def test_price_window_record_helper_rejects_unknown_source_status():
    """``build_price_window_observation_record`` must validate
    ``source_status`` against the Stage 25 closed set.
    """
    from PHX2.stage25.constants import (
        PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        QUOTE_DENOMINATION_USD_MICRO,
        SOURCE_FAMILY_BIRDEYE,
    )
    from PHX2.stage25.models import build_price_window_observation_record
    from PHX2.tests.stage25.fixtures.builders import (
        FIXED_CLOCK_UTC,
        SAMPLE_TOKEN_MINT_A,
    )

    with pytest.raises(Stage25ContractError):
        build_price_window_observation_record(
            token_mint=SAMPLE_TOKEN_MINT_A,
            source_family=SOURCE_FAMILY_BIRDEYE,
            source_status="NOT_A_REAL_STATUS",
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            observed_at_utc=FIXED_CLOCK_UTC,
            slot=1,
            block_time=2,
            price=1,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            reason_codes=(),
            evidence={},
        )


def test_price_window_record_hash_changes_when_only_source_status_changes():
    """Two window records identical on every field except
    ``source_status`` must hash differently. Pins the binding of
    ``source_status`` into the canonical hash body.
    """
    from PHX2.stage25.constants import (
        PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        QUOTE_DENOMINATION_USD_MICRO,
        SOURCE_FAMILY_BIRDEYE,
        SOURCE_STATUS_PARTIAL,
        SOURCE_STATUS_PRESENT,
    )
    from PHX2.stage25.models import build_price_window_observation_record
    from PHX2.tests.stage25.fixtures.builders import (
        FIXED_CLOCK_UTC,
        SAMPLE_TOKEN_MINT_A,
    )

    kwargs = dict(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        observed_at_utc=FIXED_CLOCK_UTC,
        slot=1,
        block_time=2,
        price=1,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        reason_codes=(),
        evidence={},
    )
    record_present = build_price_window_observation_record(
        source_status=SOURCE_STATUS_PRESENT, **kwargs
    )
    record_partial = build_price_window_observation_record(
        source_status=SOURCE_STATUS_PARTIAL, **kwargs
    )
    assert record_present.source_status != record_partial.source_status
    assert (
        record_present.observation_hash
        != record_partial.observation_hash
    )


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
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
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
        source_status=candidate.source_status,
        candidate_kind=candidate.candidate_kind,
        confidence_level=candidate.confidence_level,
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
            source_status=SOURCE_STATUS_PRESENT,
            candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
            confidence_level=CONFIDENCE_LEVEL_MEDIUM,
            peak_observed_at_utc=FIXED_CLOCK_UTC,
            peak_slot=251_000_500,
            peak_block_time=1_750_001_000,
            peak_price=0,
            quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
            reason_codes=(),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


# ---------------------------------------------------------------------------
# Stage 25.4 first-class field promotion on Stage25ATHCandidate
# ---------------------------------------------------------------------------


def test_ath_candidate_fields_include_source_status_and_confidence_level():
    """Pin the Stage25ATHCandidate ``_fields`` tuple in its intended order.

    Stage 25.4 promotes ``source_status`` and ``confidence_level`` to
    first-class fields so Stage 25.5+ source reconciliation can read
    them directly without parsing the opaque ``evidence`` mapping. The
    field order is pinned here so downstream readers (and the
    canonical hash projection) cannot drift silently.
    """
    assert Stage25ATHCandidate._fields == (
        "token_mint",
        "source_family",
        "source_status",
        "candidate_kind",
        "confidence_level",
        "peak_observed_at_utc",
        "peak_slot",
        "peak_block_time",
        "peak_price",
        "quote_denomination",
        "reason_codes",
        "evidence",
        "input_missing_fields",
        "candidate_hash",
    )


def _ath_candidate_kwargs(**overrides):
    """Helper: minimal valid kwargs for ``build_ath_candidate_record``."""
    defaults = dict(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
        peak_observed_at_utc=FIXED_CLOCK_UTC,
        peak_slot=251_000_500,
        peak_block_time=1_750_001_000,
        peak_price=1_000,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        reason_codes=(),
        evidence=MappingProxyType({}),
        input_missing_fields=(),
    )
    defaults.update(overrides)
    return defaults


def test_build_ath_candidate_record_rejects_unknown_source_status():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            **_ath_candidate_kwargs(source_status="NOT_A_REAL_STATUS")
        )


def test_build_ath_candidate_record_rejects_unknown_confidence_level():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            **_ath_candidate_kwargs(confidence_level="NOT_A_REAL_LEVEL")
        )


def test_build_ath_candidate_record_rejects_contributing_with_absent_source():
    """A contributing candidate (kind != INSUFFICIENT_DATA) must carry a
    contributing source_status. ABSENT is forbidden here.
    """
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            **_ath_candidate_kwargs(source_status=SOURCE_STATUS_ABSENT)
        )


def test_build_ath_candidate_record_rejects_contributing_with_ambiguous_source():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            **_ath_candidate_kwargs(source_status=SOURCE_STATUS_AMBIGUOUS)
        )


def test_build_ath_candidate_record_rejects_contributing_with_none_confidence():
    """A contributing candidate must not carry ``confidence_level=NONE``.

    ``NONE`` is reserved for ``INSUFFICIENT_DATA`` candidates.
    """
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_record(
            **_ath_candidate_kwargs(confidence_level=CONFIDENCE_LEVEL_NONE)
        )


def test_build_ath_candidate_record_accepts_insufficient_with_none_confidence():
    """INSUFFICIENT_DATA candidates may carry ``confidence_level=NONE``
    AND a non-contributing source_status that explains the gap.
    """
    candidate = build_ath_candidate_record(
        **_ath_candidate_kwargs(
            source_status=SOURCE_STATUS_ABSENT,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_price=None,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
        )
    )
    assert candidate.source_status == SOURCE_STATUS_ABSENT
    assert candidate.confidence_level == CONFIDENCE_LEVEL_NONE
    assert candidate.peak_price is None


def test_candidate_hash_changes_when_source_status_changes_only():
    """Hash sensitivity: changing only ``source_status`` (with no other
    field change) must change the candidate hash.

    Uses ``INSUFFICIENT_DATA`` so two different non-contributing
    statuses are both contractually valid.
    """
    insufficient_a = build_ath_candidate_record(
        **_ath_candidate_kwargs(
            source_status=SOURCE_STATUS_ABSENT,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_price=None,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
        )
    )
    insufficient_b = build_ath_candidate_record(
        **_ath_candidate_kwargs(
            source_status=SOURCE_STATUS_AMBIGUOUS,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_price=None,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
        )
    )
    assert insufficient_a.candidate_hash != insufficient_b.candidate_hash


def test_candidate_hash_changes_when_confidence_level_changes_only():
    """Hash sensitivity: changing only ``confidence_level`` (with no
    other field change) must change the candidate hash.
    """
    medium = build_ath_candidate_record(
        **_ath_candidate_kwargs(confidence_level=CONFIDENCE_LEVEL_MEDIUM)
    )
    low = build_ath_candidate_record(
        **_ath_candidate_kwargs(confidence_level=CONFIDENCE_LEVEL_LOW)
    )
    assert medium.candidate_hash != low.candidate_hash


def test_candidate_source_status_and_confidence_are_first_class_attributes():
    """Stage 25.5+ source reconciliation must be able to read
    ``source_status`` and ``confidence_level`` directly off the record
    without parsing ``evidence``.
    """
    candidate = build_ath_candidate_record(
        **_ath_candidate_kwargs(
            source_status=SOURCE_STATUS_PARTIAL,
            confidence_level=CONFIDENCE_LEVEL_LOW,
        )
    )
    assert candidate.source_status == SOURCE_STATUS_PARTIAL
    assert candidate.confidence_level == CONFIDENCE_LEVEL_LOW
    # The evidence mapping should NOT need to carry these fields for
    # downstream readers; the test does not assert what the mapping
    # contains, only that the first-class read path works without
    # touching it.
    _ = candidate.evidence  # access does not raise


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


# ---------------------------------------------------------------------------
# Stage 25.2 first-class fields on Stage25MigrationMeasurement
# ---------------------------------------------------------------------------


_MEASURED_BUILDER_DEFAULTS: dict[str, object] = {
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
    "reconciled_signature": "sig_first_class_001",
    "selected_source_family": SOURCE_FAMILY_BIRDEYE,
    "contributing_source_count": 1,
    "reason_codes": (),
    "numeric_features": MappingProxyType({}),
    "evidence": MappingProxyType({}),
    "input_missing_fields": (),
}


def _build_measured(**overrides: object) -> Stage25MigrationMeasurement:
    kwargs: dict[str, object] = dict(_MEASURED_BUILDER_DEFAULTS)
    kwargs.update(overrides)
    return build_migration_measurement_record(**kwargs)  # type: ignore[arg-type]


def test_migration_measurement_named_tuple_field_set():
    expected = (
        "measurement_family",
        "measurement_status",
        "confidence_level",
        "reconciliation_status",
        "token_mint",
        "schema_version",
        "threshold_version",
        "measurer_name",
        "measurer_version",
        "consolidated_slot",
        "consolidated_block_time",
        "reconciled_signature",
        "selected_source_family",
        "contributing_source_count",
        "reason_codes",
        "numeric_features",
        "evidence",
        "input_missing_fields",
        "measurement_hash",
    )
    assert Stage25MigrationMeasurement._fields == expected


def test_migration_measurement_does_not_have_duplicate_reconciled_block_time_field():
    assert (
        "reconciled_block_time_unix"
        not in Stage25MigrationMeasurement._fields
    )
    assert (
        "consolidated_block_time"
        in Stage25MigrationMeasurement._fields
    )


def test_build_migration_measurement_record_assigns_first_class_fields():
    record = _build_measured()
    assert record.measurement_family == MEASUREMENT_FAMILY_MIGRATION
    assert record.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert record.reconciled_signature == "sig_first_class_001"
    assert record.selected_source_family == SOURCE_FAMILY_BIRDEYE


def test_build_migration_measurement_record_rejects_unknown_reconciliation_status():
    with pytest.raises(Stage25ContractError):
        _build_measured(reconciliation_status="NOT_A_STATUS")


def test_build_migration_measurement_record_rejects_invalid_selected_source_family():
    with pytest.raises(Stage25ContractError):
        _build_measured(selected_source_family="NOT_A_SOURCE")


def test_build_migration_measurement_record_allows_empty_selected_source_family_when_not_measured():
    record = _build_measured(
        measurement_status=MEASUREMENT_STATUS_MISSING,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
        consolidated_slot=-1,
        consolidated_block_time=-1,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
    )
    assert record.measurement_status == MEASUREMENT_STATUS_MISSING
    assert record.reconciled_signature == ""
    assert record.selected_source_family == ""


def test_build_migration_measurement_record_rejects_non_string_reconciled_signature():
    with pytest.raises(Stage25ContractError):
        _build_measured(reconciled_signature=42)  # type: ignore[arg-type]


def test_build_migration_measurement_record_rejects_non_string_selected_source_family():
    with pytest.raises(Stage25ContractError):
        _build_measured(selected_source_family=7)  # type: ignore[arg-type]


def test_measured_migration_requires_non_empty_reconciled_signature():
    with pytest.raises(Stage25ContractError):
        _build_measured(reconciled_signature="")


def test_measured_migration_requires_non_empty_selected_source_family():
    with pytest.raises(Stage25ContractError):
        _build_measured(selected_source_family="")


def test_measurement_hash_changes_when_reconciliation_status_changes():
    record_a = _build_measured(
        reconciliation_status=RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    record_b = _build_measured(
        reconciliation_status=RECONCILIATION_STATUS_AGREED,
        contributing_source_count=2,
    )
    assert record_a.measurement_hash != record_b.measurement_hash


def test_measurement_hash_changes_when_reconciled_signature_changes():
    record_a = _build_measured(reconciled_signature="sig_one")
    record_b = _build_measured(reconciled_signature="sig_two")
    assert record_a.measurement_hash != record_b.measurement_hash


def test_measurement_hash_changes_when_selected_source_family_changes():
    record_a = _build_measured(
        selected_source_family=SOURCE_FAMILY_BIRDEYE
    )
    record_b = _build_measured(
        selected_source_family=SOURCE_FAMILY_DEXSCREENER
    )
    assert record_a.measurement_hash != record_b.measurement_hash


def test_measurement_hash_is_stable_across_two_identical_invocations():
    record_a = _build_measured()
    record_b = _build_measured()
    assert record_a.measurement_hash == record_b.measurement_hash


def test_measurement_hash_changes_when_only_reconciliation_status_axis_changes():
    record_a = _build_measured(
        measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS,
        consolidated_slot=-1,
        consolidated_block_time=-1,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
    )
    record_b = _build_measured(
        measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        reconciliation_status=RECONCILIATION_STATUS_DISAGREED_MAJOR,
        consolidated_slot=-1,
        consolidated_block_time=-1,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
    )
    assert record_a.measurement_hash != record_b.measurement_hash
