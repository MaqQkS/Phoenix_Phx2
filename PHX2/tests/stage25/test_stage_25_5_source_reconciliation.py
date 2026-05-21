"""Stage 25.5 source reconciliation + confidence labeling tests.

Pins:

  * A candidate contributes to a reconciled ATH iff it carries a
    contributing source_status (PRESENT / PARTIAL), a contributing
    confidence_level (MEDIUM / LOW), a non-NULL peak_price, a
    non-empty peak_observed_at_utc, a candidate_kind that is NOT
    ``INSUFFICIENT_DATA``, and a known source_family (not
    ``UNKNOWN_SOURCE``).
  * Candidates are grouped by token deterministically; the input
    tuple is never mutated.
  * No candidates -> reconciliation ``NO_SOURCES`` / measurement
    ``MISSING`` / confidence ``NONE`` / no reconciled peak.
  * Only non-contributing candidates -> reconciliation
    ``NO_SOURCES`` (or ``AMBIGUOUS`` when an AMBIGUOUS source_status
    appears) / measurement ``MISSING`` / ``UNSUPPORTED`` /
    ``AMBIGUOUS`` / confidence ``NONE``.
  * One contributing candidate -> reconciliation ``SINGLE_SOURCE``
    / measurement ``PARTIAL`` / confidence ``LOW`` / no reconciled
    peak.
  * Two-or-more contributing candidates within tolerance ->
    reconciliation ``AGREED`` / measurement ``MEASURED`` /
    confidence ``HIGH`` (or ``MEDIUM`` when any contributor is
    PARTIAL/LOW); deterministic peak selection.
  * Outside the minor tolerance but inside the major threshold ->
    reconciliation ``DISAGREED_MINOR`` / measurement ``PARTIAL`` /
    confidence ``LOW`` / no reconciled peak.
  * Outside the major threshold -> reconciliation
    ``DISAGREED_MAJOR`` / measurement ``SOURCE_CONFLICT`` /
    confidence ``NONE`` / no reconciled peak.
  * Any AMBIGUOUS source_status candidate forces reconciliation
    ``AMBIGUOUS`` / measurement ``AMBIGUOUS`` / no reconciled peak.
  * Disagreement metric uses integer parts-per-million and
    integer second-spread; deterministic across two builds.
  * Reconciliation hash changes when status / confidence / metric
    changes; ATH measurement hash changes when status / confidence /
    peak / source family / contributing source count changes.
  * ``Stage25SourceReconciliation`` and ``Stage25ATHMeasurement``
    first-class field sets include the promoted Stage 25.5 fields.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    MEASUREMENT_STATUS_UNSUPPORTED,
    PEAK_TIME_MAJOR_TOLERANCE_SECONDS,
    PEAK_TIME_TOLERANCE_SECONDS,
    PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM,
    PRICE_DISAGREEMENT_TOLERANCE_PPM,
    QUOTE_DENOMINATION_USD_MICRO,
    REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE,
    REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_DISAGREED_MINOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_FAMILY_UNKNOWN_SOURCE,
    SOURCE_FAMILY_WEBSOCKET_CAPTURE,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_ATH_MEASUREMENT_VERSION,
    STAGE25_SOURCE_RECONCILIATION_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHMeasurement,
    Stage25SourceReconciliation,
    build_ath_measurement_record,
    build_source_reconciliation_record,
)
from PHX2.stage25.source_reconciliation import (
    build_ath_measurement_for_token,
    build_source_reconciliation_for_token,
    candidate_can_contribute_to_reconciled_ath,
    classify_candidate_set_reconciliation_status,
    group_ath_candidates_by_token,
    reconcile_ath_candidates,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_ath_candidate,
)


SAMPLE_BLOCK_TIME: int = 1_750_000_010
SAMPLE_SLOT: int = 251_000_010


def _present_candidate(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    peak_price: int = 1_000_000,
    peak_block_time: int = SAMPLE_BLOCK_TIME,
    peak_observed_at_utc: str = FIXED_CLOCK_UTC,
    confidence_level: str = CONFIDENCE_LEVEL_MEDIUM,
):
    return make_ath_candidate(
        token_mint=token_mint,
        source_family=source_family,
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=confidence_level,
        peak_observed_at_utc=peak_observed_at_utc,
        peak_slot=SAMPLE_SLOT,
        peak_block_time=peak_block_time,
        peak_price=peak_price,
    )


def _insufficient_candidate(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_DEXSCREENER,
    source_status: str = SOURCE_STATUS_ABSENT,
):
    return make_ath_candidate(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        peak_observed_at_utc="",
        peak_slot=-1,
        peak_block_time=-1,
        peak_price=None,
    )


# ---------------------------------------------------------------------------
# Candidate contribution predicate
# ---------------------------------------------------------------------------


def test_present_medium_candidate_with_peak_contributes():
    candidate = _present_candidate()
    assert candidate_can_contribute_to_reconciled_ath(candidate) is True


def test_partial_low_candidate_with_peak_contributes():
    candidate = make_ath_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PARTIAL,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_LOW,
    )
    assert candidate_can_contribute_to_reconciled_ath(candidate) is True


def test_insufficient_data_candidate_does_not_contribute():
    candidate = _insufficient_candidate()
    assert candidate_can_contribute_to_reconciled_ath(candidate) is False


@pytest.mark.parametrize(
    "status",
    [
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_UNSUPPORTED,
        SOURCE_STATUS_AMBIGUOUS,
    ],
)
def test_non_contributing_source_status_does_not_contribute(status):
    candidate = make_ath_candidate(
        candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
        source_status=status,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        peak_observed_at_utc="",
        peak_slot=-1,
        peak_block_time=-1,
        peak_price=None,
    )
    assert candidate_can_contribute_to_reconciled_ath(candidate) is False


def test_unknown_source_family_does_not_contribute():
    candidate = make_ath_candidate(
        source_family=SOURCE_FAMILY_UNKNOWN_SOURCE,
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
    )
    assert candidate_can_contribute_to_reconciled_ath(candidate) is False


def test_predicate_rejects_non_candidate_input():
    with pytest.raises(Stage25ContractError):
        candidate_can_contribute_to_reconciled_ath(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_group_candidates_by_token_buckets_deterministically():
    a = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    b = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    c = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    grouped = group_ath_candidates_by_token((a, b, c))
    keys = list(grouped.keys())
    assert keys == sorted(keys)
    assert set(keys) == {SAMPLE_TOKEN_MINT_A, SAMPLE_TOKEN_MINT_B}


def test_group_candidates_does_not_mutate_input_tuple():
    a = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    b = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_B)
    candidates = (a, b)
    snapshot = tuple(candidates)
    _ = group_ath_candidates_by_token(candidates)
    assert candidates == snapshot


def test_group_candidates_rejects_non_tuple_input():
    with pytest.raises(Stage25ContractError):
        group_ath_candidates_by_token([_present_candidate()])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# No candidates
# ---------------------------------------------------------------------------


def test_no_candidates_reconciliation_is_no_sources():
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, ()
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_NONE
    assert reconciliation.contributing_source_count == 0
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES
        in reconciliation.reason_codes
    )


def test_no_candidates_measurement_is_missing_with_no_peak():
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, ()
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (), reconciliation
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert measurement.confidence_level == CONFIDENCE_LEVEL_NONE
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""
    assert measurement.reconciled_peak_observed_at_utc == ""


# ---------------------------------------------------------------------------
# Only non-contributing candidates
# ---------------------------------------------------------------------------


def test_only_absent_candidates_reconciliation_is_no_sources_missing():
    candidates = (
        _insufficient_candidate(source_family=SOURCE_FAMILY_DEXSCREENER),
        _insufficient_candidate(source_family=SOURCE_FAMILY_BIRDEYE),
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_NO_SOURCES
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MISSING
    assert measurement.consolidated_peak_price is None
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES
        in reconciliation.reason_codes
    )


def test_only_unsupported_candidates_measurement_is_unsupported():
    candidates = (
        _insufficient_candidate(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            source_status=SOURCE_STATUS_UNSUPPORTED,
        ),
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_UNSUPPORTED
    assert measurement.consolidated_peak_price is None


# ---------------------------------------------------------------------------
# Single source
# ---------------------------------------------------------------------------


def test_single_contributor_reconciliation_is_single_source():
    candidates = (_present_candidate(),)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_LOW
    assert reconciliation.contributing_source_count == 1
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL
        in reconciliation.reason_codes
    )


def test_single_contributor_measurement_is_partial_without_peak():
    candidates = (_present_candidate(),)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurement.confidence_level == CONFIDENCE_LEVEL_LOW
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""
    assert measurement.reconciled_peak_observed_at_utc == ""
    assert (
        REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE
        in measurement.reason_codes
    )


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def test_two_present_sources_within_tolerance_agree():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 30,
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert reconciliation.contributing_source_count == 2
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert measurement.consolidated_peak_price == 1_010_000
    assert measurement.peak_source_family == SOURCE_FAMILY_DEXSCREENER
    assert measurement.reconciled_peak_observed_at_utc == FIXED_CLOCK_UTC
    assert (
        REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES
        in measurement.reason_codes
    )
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED
        in reconciliation.reason_codes
    )


def test_agreement_with_partial_contributor_yields_medium_confidence():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = make_ath_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PARTIAL,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_LOW,
        peak_block_time=SAMPLE_BLOCK_TIME + 10,
        peak_price=1_005_000,
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_MEDIUM
    assert measurement.confidence_level == CONFIDENCE_LEVEL_MEDIUM
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_peak_price == 1_005_000


def test_agreement_peak_selection_prefers_earliest_observed_at_on_price_tie():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
        peak_observed_at_utc="2026-01-01T00:00:00Z",
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 30,
        peak_observed_at_utc="2026-01-01T00:01:00Z",
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.peak_source_family == SOURCE_FAMILY_BIRDEYE
    assert (
        measurement.reconciled_peak_observed_at_utc
        == "2026-01-01T00:00:00Z"
    )


def test_agreement_three_sources_high_confidence():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_002_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 20,
    )
    c = _present_candidate(
        source_family=SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 40,
    )
    candidates = (a, b, c)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.contributing_source_count == 3
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert measurement.contributing_source_count == 3
    assert measurement.consolidated_peak_price == 1_005_000
    assert measurement.peak_source_family == SOURCE_FAMILY_WEBSOCKET_CAPTURE


# ---------------------------------------------------------------------------
# Minor disagreement
# ---------------------------------------------------------------------------


def test_minor_price_disagreement_yields_partial_low_no_peak():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    # 10% above => 100_000 ppm, above MINOR (50_000 ppm) and below
    # MAJOR (250_000 ppm).
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_100_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 10,
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MINOR
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_LOW
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurement.confidence_level == CONFIDENCE_LEVEL_LOW
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR
        in reconciliation.reason_codes
    )
    assert (
        REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR
        in measurement.reason_codes
    )


def test_minor_time_disagreement_yields_partial_low_no_peak():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_000_000,
        peak_block_time=(
            SAMPLE_BLOCK_TIME + PEAK_TIME_TOLERANCE_SECONDS + 5
        ),
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MINOR
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurement.consolidated_peak_price is None


# ---------------------------------------------------------------------------
# Major disagreement
# ---------------------------------------------------------------------------


def test_major_price_disagreement_yields_source_conflict_none_confidence():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    # 50% above => 500_000 ppm, above MAJOR threshold (250_000 ppm).
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_500_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_NONE
    assert (
        measurement.measurement_status
        == MEASUREMENT_STATUS_SOURCE_CONFLICT
    )
    assert measurement.confidence_level == CONFIDENCE_LEVEL_NONE
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""
    assert (
        REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR
        in reconciliation.reason_codes
    )
    assert (
        REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT
        in measurement.reason_codes
    )


def test_major_time_disagreement_yields_source_conflict():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_000_000,
        peak_block_time=(
            SAMPLE_BLOCK_TIME + PEAK_TIME_MAJOR_TOLERANCE_SECONDS + 1
        ),
    )
    candidates = (a, b)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    assert (
        measurement.measurement_status
        == MEASUREMENT_STATUS_SOURCE_CONFLICT
    )
    assert measurement.consolidated_peak_price is None


# ---------------------------------------------------------------------------
# Ambiguous
# ---------------------------------------------------------------------------


def test_ambiguous_source_status_among_candidates_yields_ambiguous():
    ambiguous = _insufficient_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    candidates = (ambiguous,)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert measurement.consolidated_peak_price is None


def test_non_positive_peak_price_yields_ambiguous():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    zero = make_ath_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
        peak_price=0,
        reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,),
    )
    candidates = (a, zero)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert measurement.measurement_status == MEASUREMENT_STATUS_AMBIGUOUS
    assert measurement.consolidated_peak_price is None


# ---------------------------------------------------------------------------
# classify_candidate_set_reconciliation_status
# ---------------------------------------------------------------------------


def test_classify_returns_no_sources_for_empty_input():
    status = classify_candidate_set_reconciliation_status(())
    assert status == RECONCILIATION_STATUS_NO_SOURCES


def test_classify_returns_single_source_for_one_contributor():
    status = classify_candidate_set_reconciliation_status(
        (_present_candidate(),)
    )
    assert status == RECONCILIATION_STATUS_SINGLE_SOURCE


def test_classify_returns_agreed_for_close_pair():
    status = classify_candidate_set_reconciliation_status(
        (
            _present_candidate(
                source_family=SOURCE_FAMILY_BIRDEYE,
                peak_price=1_000_000,
                peak_block_time=SAMPLE_BLOCK_TIME,
            ),
            _present_candidate(
                source_family=SOURCE_FAMILY_DEXSCREENER,
                peak_price=1_010_000,
                peak_block_time=SAMPLE_BLOCK_TIME + 5,
            ),
        )
    )
    assert status == RECONCILIATION_STATUS_AGREED


def test_classify_returns_disagreed_major_for_huge_spread():
    status = classify_candidate_set_reconciliation_status(
        (
            _present_candidate(
                source_family=SOURCE_FAMILY_BIRDEYE,
                peak_price=1_000_000,
                peak_block_time=SAMPLE_BLOCK_TIME,
            ),
            _present_candidate(
                source_family=SOURCE_FAMILY_DEXSCREENER,
                peak_price=10_000_000,
                peak_block_time=SAMPLE_BLOCK_TIME + 5,
            ),
        )
    )
    assert status == RECONCILIATION_STATUS_DISAGREED_MAJOR


# ---------------------------------------------------------------------------
# Disagreement metric determinism
# ---------------------------------------------------------------------------


def test_price_disagreement_metric_is_integer_and_deterministic():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_100_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 10,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    metric = reconciliation.disagreement_metric
    assert isinstance(metric["price_disagreement_ppm"], int)
    assert isinstance(metric["peak_time_disagreement_seconds"], int)
    assert metric["price_disagreement_ppm"] == 100_000
    assert metric["peak_time_disagreement_seconds"] == 10
    # Determinism: rebuild and confirm bytes-identical metric.
    other = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    assert other.disagreement_metric == metric
    assert other.reconciliation_hash == reconciliation.reconciliation_hash


def test_disagreement_metric_carries_no_float_values():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_002_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 2,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    for value in reconciliation.disagreement_metric.values():
        assert not isinstance(value, float)


# ---------------------------------------------------------------------------
# Hash sensitivity
# ---------------------------------------------------------------------------


def test_reconciliation_hash_changes_with_status():
    agreed_candidates = (
        _present_candidate(
            source_family=SOURCE_FAMILY_BIRDEYE,
            peak_price=1_000_000,
            peak_block_time=SAMPLE_BLOCK_TIME,
        ),
        _present_candidate(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            peak_price=1_005_000,
            peak_block_time=SAMPLE_BLOCK_TIME + 5,
        ),
    )
    minor_candidates = (
        agreed_candidates[0],
        _present_candidate(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            peak_price=1_100_000,
            peak_block_time=SAMPLE_BLOCK_TIME + 5,
        ),
    )
    agreed = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, agreed_candidates
    )
    minor = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, minor_candidates
    )
    assert agreed.reconciliation_status == RECONCILIATION_STATUS_AGREED
    assert minor.reconciliation_status == (
        RECONCILIATION_STATUS_DISAGREED_MINOR
    )
    assert agreed.reconciliation_hash != minor.reconciliation_hash


def test_reconciliation_hash_changes_with_confidence_level():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b_present = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    b_partial = make_ath_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_PARTIAL,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_LOW,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
        peak_price=1_005_000,
    )
    high = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_present)
    )
    medium = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_partial)
    )
    assert high.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert medium.confidence_level == CONFIDENCE_LEVEL_MEDIUM
    assert high.reconciliation_hash != medium.reconciliation_hash


def test_ath_measurement_hash_changes_with_peak_price():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b_low = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    b_high = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_020_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    rec_low = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_low)
    )
    rec_high = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_high)
    )
    m_low = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_low), rec_low
    )
    m_high = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b_high), rec_high
    )
    assert m_low.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert m_high.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert m_low.consolidated_peak_price != m_high.consolidated_peak_price
    assert m_low.measurement_hash != m_high.measurement_hash


def test_ath_measurement_hash_changes_with_peak_source_family():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    rec_ab = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    m_ab = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b), rec_ab
    )
    a_alt = _present_candidate(
        source_family=SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    rec_alt = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a_alt, b)
    )
    m_alt = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a_alt, b), rec_alt
    )
    assert m_ab.peak_source_family != m_alt.peak_source_family
    assert m_ab.measurement_hash != m_alt.measurement_hash


def test_ath_measurement_hash_changes_with_contributing_source_count():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    c = _present_candidate(
        source_family=SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        peak_price=1_002_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 10,
    )
    rec2 = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    rec3 = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b, c)
    )
    m2 = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b), rec2
    )
    m3 = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b, c), rec3
    )
    assert m2.contributing_source_count == 2
    assert m3.contributing_source_count == 3
    assert m2.measurement_hash != m3.measurement_hash


# ---------------------------------------------------------------------------
# First-class field set assertions
# ---------------------------------------------------------------------------


def test_source_reconciliation_fields_include_first_class_promotions():
    expected = {
        "measurement_family",
        "reconciliation_status",
        "confidence_level",
        "token_mint",
        "source_families",
        "contributing_source_count",
        "disagreeing_source_count",
        "disagreement_metric",
        "reason_codes",
        "evidence",
        "reconciliation_hash",
    }
    assert expected.issubset(set(Stage25SourceReconciliation._fields))


def test_ath_measurement_fields_include_first_class_promotions():
    expected = {
        "measurement_family",
        "measurement_status",
        "confidence_level",
        "reconciliation_status",
        "token_mint",
        "consolidated_peak_slot",
        "consolidated_peak_block_time",
        "consolidated_peak_price",
        "peak_source_family",
        "reconciled_peak_observed_at_utc",
        "time_to_peak_seconds",
        "contributing_source_count",
        "reason_codes",
        "measurement_hash",
    }
    assert expected.issubset(set(Stage25ATHMeasurement._fields))


# ---------------------------------------------------------------------------
# Token mismatch
# ---------------------------------------------------------------------------


def test_token_mismatch_observed_attaches_reason_code():
    a = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    other = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, other)
    )
    # Only A's candidate matters; mismatch should be flagged.
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert reconciliation.contributing_source_count == 1
    assert any(
        "TOKEN_MISMATCH" in code for code in reconciliation.reason_codes
    )


def test_token_mismatch_reconciliation_into_measurement_propagates():
    a = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    other = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, other)
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, other), reconciliation
    )
    assert any(
        "TOKEN_MISMATCH" in code for code in measurement.reason_codes
    )


def test_build_ath_measurement_rejects_token_mint_mismatch_on_reconciliation():
    a = _present_candidate(token_mint=SAMPLE_TOKEN_MINT_A)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a,)
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_for_token(
            SAMPLE_TOKEN_MINT_B, (a,), reconciliation
        )


# ---------------------------------------------------------------------------
# Batch reconciler
# ---------------------------------------------------------------------------


def test_reconcile_ath_candidates_emits_one_pair_per_token():
    a1 = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    a2 = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    b1 = _present_candidate(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=500_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    reconciliations, measurements = reconcile_ath_candidates(
        (a1, a2, b1)
    )
    assert len(reconciliations) == 2
    assert len(measurements) == 2
    assert reconciliations[0].token_mint == SAMPLE_TOKEN_MINT_A
    assert reconciliations[1].token_mint == SAMPLE_TOKEN_MINT_B
    assert (
        reconciliations[0].reconciliation_status
        == RECONCILIATION_STATUS_AGREED
    )
    assert (
        reconciliations[1].reconciliation_status
        == RECONCILIATION_STATUS_SINGLE_SOURCE
    )


def test_reconcile_ath_candidates_empty_input_returns_empty_tuples():
    reconciliations, measurements = reconcile_ath_candidates(())
    assert reconciliations == ()
    assert measurements == ()


def test_reconcile_ath_candidates_does_not_mutate_input():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    candidates = (a, b)
    snapshot = tuple(candidates)
    _ = reconcile_ath_candidates(candidates)
    assert candidates == snapshot


def test_reconcile_ath_candidates_is_deterministic_across_runs():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    rec_1, m_1 = reconcile_ath_candidates((a, b))
    rec_2, m_2 = reconcile_ath_candidates((b, a))  # reversed input
    assert rec_1[0].reconciliation_hash == rec_2[0].reconciliation_hash
    assert m_1[0].measurement_hash == m_2[0].measurement_hash


# ---------------------------------------------------------------------------
# Reconciliation metadata constants
# ---------------------------------------------------------------------------


def test_reconciliation_evidence_carries_reconciliation_version():
    a = _present_candidate()
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a,)
    )
    assert (
        reconciliation.evidence["reconciliation_version"]
        == STAGE25_SOURCE_RECONCILIATION_VERSION
    )


def test_ath_measurement_carries_measurement_version_axis():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_002_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 2,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b), reconciliation
    )
    assert measurement.measurer_version == STAGE25_ATH_MEASUREMENT_VERSION
    assert measurement.measurement_family == MEASUREMENT_FAMILY_ATH


# ---------------------------------------------------------------------------
# Honesty: measured peak only when MEASURED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidates",
    [
        (),
        (_insufficient_candidate(),),
        (_present_candidate(),),
        (
            _present_candidate(
                source_family=SOURCE_FAMILY_BIRDEYE,
                peak_price=1_000_000,
                peak_block_time=SAMPLE_BLOCK_TIME,
            ),
            _present_candidate(
                source_family=SOURCE_FAMILY_DEXSCREENER,
                peak_price=10_000_000,
                peak_block_time=SAMPLE_BLOCK_TIME + 5,
            ),
        ),
    ],
)
def test_non_measured_outcomes_have_none_reconciled_peak_price(candidates):
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    if measurement.measurement_status != MEASUREMENT_STATUS_MEASURED:
        assert measurement.consolidated_peak_price is None
        assert measurement.peak_source_family == ""
        assert measurement.reconciled_peak_observed_at_utc == ""


# ---------------------------------------------------------------------------
# Remediation: Ambiguous candidate poisoning
# ---------------------------------------------------------------------------


def test_ambiguous_candidate_poisons_two_agreeing_contributors():
    """Two PRESENT/MEDIUM contributors that would otherwise AGREE, plus
    one AMBIGUOUS candidate, must yield AMBIGUOUS / not MEASURED.

    Ambiguity on a single source is itself evidence the token's ATH
    cannot be measured honestly. The reconciler must NOT silently
    ignore the AMBIGUOUS candidate just because two other sources
    happen to agree.
    """
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    ambiguous = _insufficient_candidate(
        source_family=SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    candidates = (a, b, ambiguous)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert reconciliation.confidence_level == CONFIDENCE_LEVEL_NONE
    assert measurement.measurement_status != MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""
    assert measurement.reconciled_peak_observed_at_utc == ""


def test_ambiguous_candidate_poisons_single_valid_contributor():
    """One AMBIGUOUS candidate plus one valid contributor must yield
    AMBIGUOUS, NOT ``SINGLE_SOURCE``. The ambiguous source is part of
    the audit trail and forces an ambiguous outcome.
    """
    valid = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    ambiguous = _insufficient_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    candidates = (valid, ambiguous)
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, candidates
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, candidates, reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert reconciliation.reconciliation_status != (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert measurement.measurement_status != MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_peak_price is None


def test_ambiguous_only_candidate_yields_ambiguous_no_peak():
    ambiguous = _insufficient_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (ambiguous,)
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (ambiguous,), reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AMBIGUOUS
    )
    assert measurement.measurement_status != MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_peak_price is None
    assert measurement.peak_source_family == ""


def test_classifier_treats_ambiguous_as_poisoning():
    """The classifier alone must surface AMBIGUOUS even when two
    contributing candidates from distinct sources could otherwise
    AGREE.
    """
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    ambiguous = _insufficient_candidate(
        source_family=SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    status = classify_candidate_set_reconciliation_status(
        (a, b, ambiguous)
    )
    assert status == RECONCILIATION_STATUS_AMBIGUOUS


# ---------------------------------------------------------------------------
# Remediation: Distinct source-family contribution rule
# ---------------------------------------------------------------------------


def test_two_same_source_contributors_yield_single_source():
    """Two contributing candidates from the SAME source family must
    NOT produce AGREED / MEASURED. Cross-source agreement requires
    distinct ``source_family`` values; two same-source rows collapse
    to one contributor.
    """
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
        peak_observed_at_utc="2026-01-01T00:00:00Z",
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
        peak_observed_at_utc="2026-01-01T00:01:00Z",
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b), reconciliation
    )
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    assert reconciliation.contributing_source_count == 1
    assert measurement.measurement_status != MEASUREMENT_STATUS_MEASURED
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurement.consolidated_peak_price is None


def test_same_source_dedup_distinct_count_with_other_source():
    """Two BIRDEYE candidates plus one DEXSCREENER candidate must yield
    a contributing_source_count of 2 (distinct sources) after the
    deterministic per-source selection collapses the BIRDEYE pair.
    """
    a1 = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
        peak_observed_at_utc="2026-01-01T00:00:00Z",
    )
    a2 = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
        peak_observed_at_utc="2026-01-01T00:01:00Z",
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_005_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a1, a2, b)
    )
    measurement = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A, (a1, a2, b), reconciliation
    )
    assert reconciliation.contributing_source_count == 2
    assert measurement.contributing_source_count == 2
    assert reconciliation.reconciliation_status == (
        RECONCILIATION_STATUS_AGREED
    )


def test_same_source_selection_is_deterministic_highest_price_wins():
    """Among same-source candidates the deterministic selection is:
    highest peak_price, then earliest peak_observed_at_utc, then
    candidate_hash. The chosen peak must reflect the highest-price
    candidate's source-family selection.
    """
    a_low = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
        peak_observed_at_utc="2026-01-01T00:00:00Z",
    )
    a_high = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_020_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
        peak_observed_at_utc="2026-01-01T00:01:00Z",
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 10,
    )
    reconciliation_1 = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a_low, a_high, b)
    )
    measurement_1 = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A,
        (a_low, a_high, b),
        reconciliation_1,
    )
    # Permute input order; result must be byte-identical.
    reconciliation_2 = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (b, a_high, a_low)
    )
    measurement_2 = build_ath_measurement_for_token(
        SAMPLE_TOKEN_MINT_A,
        (b, a_high, a_low),
        reconciliation_2,
    )
    assert measurement_1.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement_2.measurement_status == MEASUREMENT_STATUS_MEASURED
    # The peak should reflect the same-source selection: a_high (price
    # 1_020_000) beats a_low and is the cross-source peak.
    assert measurement_1.consolidated_peak_price == 1_020_000
    assert measurement_2.consolidated_peak_price == 1_020_000
    assert measurement_1.peak_source_family == SOURCE_FAMILY_BIRDEYE
    assert measurement_2.peak_source_family == SOURCE_FAMILY_BIRDEYE
    assert (
        measurement_1.measurement_hash
        == measurement_2.measurement_hash
    )
    assert (
        reconciliation_1.reconciliation_hash
        == reconciliation_2.reconciliation_hash
    )


def test_two_same_source_only_contributing_source_count_is_one():
    a = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_000_000,
        peak_block_time=SAMPLE_BLOCK_TIME,
    )
    b = _present_candidate(
        source_family=SOURCE_FAMILY_BIRDEYE,
        peak_price=1_010_000,
        peak_block_time=SAMPLE_BLOCK_TIME + 5,
    )
    reconciliation = build_source_reconciliation_for_token(
        SAMPLE_TOKEN_MINT_A, (a, b)
    )
    assert reconciliation.contributing_source_count == 1


# ---------------------------------------------------------------------------
# Remediation: build_ath_measurement_record contract
# ---------------------------------------------------------------------------


def _measured_record_kwargs(
    *,
    reconciliation_status: str = RECONCILIATION_STATUS_AGREED,
    contributing_source_count: int = 2,
):
    """Return a kwargs dict that, by default, builds a valid MEASURED
    ATH measurement record. Tests mutate one field at a time to
    exercise the strengthened invariants.
    """
    from types import MappingProxyType

    return {
        "measurement_status": MEASUREMENT_STATUS_MEASURED,
        "confidence_level": CONFIDENCE_LEVEL_HIGH,
        "reconciliation_status": reconciliation_status,
        "token_mint": SAMPLE_TOKEN_MINT_A,
        "schema_version": "stage25_v0_measurement",
        "threshold_version": "thresholds_v0_observe_only",
        "measurer_name": "stage25_ath_measurer",
        "measurer_version": STAGE25_ATH_MEASUREMENT_VERSION,
        "consolidated_peak_slot": SAMPLE_SLOT,
        "consolidated_peak_block_time": SAMPLE_BLOCK_TIME,
        "consolidated_peak_price": 1_000_000,
        "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        "peak_source_family": SOURCE_FAMILY_BIRDEYE,
        "reconciled_peak_observed_at_utc": FIXED_CLOCK_UTC,
        "time_to_peak_seconds": None,
        "contributing_source_count": contributing_source_count,
        "reason_codes": (
            REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES,
        ),
        "numeric_features": MappingProxyType({}),
        "evidence": MappingProxyType({}),
        "input_missing_fields": (),
    }


def test_build_ath_measurement_record_rejects_measured_with_single_source():
    kwargs = _measured_record_kwargs(
        reconciliation_status=RECONCILIATION_STATUS_SINGLE_SOURCE
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_disagreed_minor():
    kwargs = _measured_record_kwargs(
        reconciliation_status=RECONCILIATION_STATUS_DISAGREED_MINOR
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_disagreed_major():
    kwargs = _measured_record_kwargs(
        reconciliation_status=RECONCILIATION_STATUS_DISAGREED_MAJOR
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_ambiguous():
    kwargs = _measured_record_kwargs(
        reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_no_sources():
    kwargs = _measured_record_kwargs(
        reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES
    )
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_count_one():
    kwargs = _measured_record_kwargs(contributing_source_count=1)
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_count_zero():
    kwargs = _measured_record_kwargs(contributing_source_count=0)
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_accepts_measured_with_agreed_and_two_sources():
    kwargs = _measured_record_kwargs()
    measurement = build_ath_measurement_record(**kwargs)
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.contributing_source_count == 2
    assert (
        measurement.reconciliation_status == RECONCILIATION_STATUS_AGREED
    )


def test_build_ath_measurement_record_rejects_non_measured_with_peak_price():
    from types import MappingProxyType

    kwargs = _measured_record_kwargs()
    kwargs["measurement_status"] = MEASUREMENT_STATUS_PARTIAL
    kwargs["reconciliation_status"] = RECONCILIATION_STATUS_SINGLE_SOURCE
    kwargs["confidence_level"] = CONFIDENCE_LEVEL_LOW
    kwargs["contributing_source_count"] = 1
    kwargs["reason_codes"] = ()
    kwargs["numeric_features"] = MappingProxyType({})
    kwargs["evidence"] = MappingProxyType({})
    # consolidated_peak_price still set -> must raise.
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_non_measured_with_peak_source_family():
    from types import MappingProxyType

    kwargs = _measured_record_kwargs()
    kwargs["measurement_status"] = MEASUREMENT_STATUS_PARTIAL
    kwargs["reconciliation_status"] = RECONCILIATION_STATUS_SINGLE_SOURCE
    kwargs["confidence_level"] = CONFIDENCE_LEVEL_LOW
    kwargs["contributing_source_count"] = 1
    kwargs["reason_codes"] = ()
    kwargs["numeric_features"] = MappingProxyType({})
    kwargs["evidence"] = MappingProxyType({})
    kwargs["consolidated_peak_price"] = None
    kwargs["reconciled_peak_observed_at_utc"] = ""
    # peak_source_family still set -> must raise.
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_non_measured_with_observed_at():
    from types import MappingProxyType

    kwargs = _measured_record_kwargs()
    kwargs["measurement_status"] = MEASUREMENT_STATUS_PARTIAL
    kwargs["reconciliation_status"] = RECONCILIATION_STATUS_SINGLE_SOURCE
    kwargs["confidence_level"] = CONFIDENCE_LEVEL_LOW
    kwargs["contributing_source_count"] = 1
    kwargs["reason_codes"] = ()
    kwargs["numeric_features"] = MappingProxyType({})
    kwargs["evidence"] = MappingProxyType({})
    kwargs["consolidated_peak_price"] = None
    kwargs["peak_source_family"] = ""
    # reconciled_peak_observed_at_utc still set -> must raise.
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


# ---------------------------------------------------------------------------
# Remediation: build_source_reconciliation_record contract
# ---------------------------------------------------------------------------


_UNSET_DISAGREEMENT_METRIC: object = object()


def _reconciliation_record_kwargs(
    *,
    source_families: tuple[str, ...] = (
        SOURCE_FAMILY_BIRDEYE,
        SOURCE_FAMILY_DEXSCREENER,
    ),
    disagreement_metric: object = _UNSET_DISAGREEMENT_METRIC,
):
    """Return a kwargs dict that builds a valid AGREED reconciliation
    record by default. Tests mutate one field at a time to exercise
    the strengthened invariants.

    ``disagreement_metric`` uses a private sentinel for "argument
    omitted" so an explicit ``None`` passed by a test is preserved
    verbatim (and exercises the Stage 25.5 None-allowed contract)
    rather than being silently replaced with the default mapping.
    """
    from types import MappingProxyType

    if disagreement_metric is _UNSET_DISAGREEMENT_METRIC:
        disagreement_metric = MappingProxyType(
            {
                "price_disagreement_ppm": 5_000,
                "peak_time_disagreement_seconds": 30,
                "contributor_count": 2,
            }
        )
    return {
        "measurement_family": MEASUREMENT_FAMILY_ATH,
        "reconciliation_status": RECONCILIATION_STATUS_AGREED,
        "confidence_level": CONFIDENCE_LEVEL_HIGH,
        "token_mint": SAMPLE_TOKEN_MINT_A,
        "source_families": source_families,
        "contributing_source_count": 2,
        "disagreeing_source_count": 0,
        "disagreement_metric": disagreement_metric,
        "reason_codes": (),
        "evidence": MappingProxyType({}),
    }


def test_build_source_reconciliation_record_rejects_float_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": 5_000.0}
        )
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_rejects_bool_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": True}
        )
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_rejects_non_string_metric_key():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType({0: 5_000})
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_rejects_arbitrary_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": "5000"}
        )
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_rejects_list_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": [5_000]}
        )
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_accepts_int_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": 5_000}
        )
    )
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert reconciliation.disagreement_metric[
        "price_disagreement_ppm"
    ] == 5_000


def test_build_source_reconciliation_record_accepts_none_metric_value():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": None}
        )
    )
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert (
        reconciliation.disagreement_metric["price_disagreement_ppm"]
        is None
    )


def test_build_source_reconciliation_record_rejects_unsorted_source_families():
    kwargs = _reconciliation_record_kwargs(
        source_families=(
            SOURCE_FAMILY_DEXSCREENER,
            SOURCE_FAMILY_BIRDEYE,
        ),
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_rejects_duplicate_source_families():
    kwargs = _reconciliation_record_kwargs(
        source_families=(
            SOURCE_FAMILY_BIRDEYE,
            SOURCE_FAMILY_BIRDEYE,
        ),
    )
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)


def test_build_source_reconciliation_record_accepts_sorted_unique_source_families():
    kwargs = _reconciliation_record_kwargs(
        source_families=(
            SOURCE_FAMILY_BIRDEYE,
            SOURCE_FAMILY_DEXSCREENER,
            SOURCE_FAMILY_WEBSOCKET_CAPTURE,
        ),
    )
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert reconciliation.source_families == (
        SOURCE_FAMILY_BIRDEYE,
        SOURCE_FAMILY_DEXSCREENER,
        SOURCE_FAMILY_WEBSOCKET_CAPTURE,
    )


def test_reconciliation_hash_changes_with_disagreement_metric():
    from types import MappingProxyType

    base_kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": 5_000}
        )
    )
    a = build_source_reconciliation_record(**base_kwargs)
    other_kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": 10_000}
        )
    )
    b = build_source_reconciliation_record(**other_kwargs)
    assert a.reconciliation_hash != b.reconciliation_hash


# ---------------------------------------------------------------------------
# Remediation: contribution predicate ignores non-contributing status even
# when peak fields look valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_UNSUPPORTED,
        SOURCE_STATUS_AMBIGUOUS,
    ],
)
def test_non_contributing_status_with_non_null_peak_still_ineligible(status):
    """Even when a candidate carries a non-null ``peak_price`` and a
    non-empty ``peak_observed_at_utc``, a non-contributing
    ``source_status`` MUST keep it out of the contributors pool.
    Contribution is gated on closed-set status / confidence, NOT
    only on price presence.

    The Stage 25.4 ``build_ath_candidate_record`` validator forbids
    constructing such a row via the normal builder (a non-INSUFFICIENT
    candidate must carry PRESENT/PARTIAL), so the test constructs the
    candidate via ``Stage25ATHCandidate._replace`` on a valid record
    to exercise the predicate in isolation.
    """
    valid = _present_candidate()
    poisoned = valid._replace(source_status=status)
    assert candidate_can_contribute_to_reconciled_ath(poisoned) is False


@pytest.mark.parametrize(
    "confidence",
    [CONFIDENCE_LEVEL_NONE, CONFIDENCE_LEVEL_HIGH],
)
def test_non_contributing_confidence_with_non_null_peak_still_ineligible(
    confidence,
):
    """``CONFIDENCE_LEVEL_NONE`` and ``CONFIDENCE_LEVEL_HIGH`` are not
    contributing levels in Stage 25.5: NONE because the candidate has
    no real evidence, HIGH because Stage 25.4 NEVER emits HIGH (HIGH
    is reserved for Stage 25.5+ cross-source agreement). A
    hand-constructed candidate carrying either level with a non-null
    peak must remain ineligible.
    """
    valid = _present_candidate()
    poisoned = valid._replace(confidence_level=confidence)
    assert candidate_can_contribute_to_reconciled_ath(poisoned) is False


def test_unknown_source_with_non_null_peak_still_ineligible():
    valid = _present_candidate()
    poisoned = valid._replace(source_family=SOURCE_FAMILY_UNKNOWN_SOURCE)
    assert candidate_can_contribute_to_reconciled_ath(poisoned) is False


# ---------------------------------------------------------------------------
# Remediation: build_ath_measurement_record slot / block-time contract
# ---------------------------------------------------------------------------


def test_build_ath_measurement_record_rejects_measured_with_sentinel_peak_slot():
    kwargs = _measured_record_kwargs()
    kwargs["consolidated_peak_slot"] = -1
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_measured_with_sentinel_block_time():
    kwargs = _measured_record_kwargs()
    kwargs["consolidated_peak_block_time"] = -1
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_accepts_measured_with_non_negative_slot_and_block_time():
    kwargs = _measured_record_kwargs()
    kwargs["consolidated_peak_slot"] = 0
    kwargs["consolidated_peak_block_time"] = 0
    measurement = build_ath_measurement_record(**kwargs)
    assert measurement.measurement_status == MEASUREMENT_STATUS_MEASURED
    assert measurement.consolidated_peak_slot == 0
    assert measurement.consolidated_peak_block_time == 0


def _unmeasured_partial_kwargs():
    from types import MappingProxyType

    kwargs = _measured_record_kwargs()
    kwargs["measurement_status"] = MEASUREMENT_STATUS_PARTIAL
    kwargs["reconciliation_status"] = RECONCILIATION_STATUS_SINGLE_SOURCE
    kwargs["confidence_level"] = CONFIDENCE_LEVEL_LOW
    kwargs["contributing_source_count"] = 1
    kwargs["consolidated_peak_slot"] = -1
    kwargs["consolidated_peak_block_time"] = -1
    kwargs["consolidated_peak_price"] = None
    kwargs["peak_source_family"] = ""
    kwargs["reconciled_peak_observed_at_utc"] = ""
    kwargs["reason_codes"] = ()
    kwargs["numeric_features"] = MappingProxyType({})
    kwargs["evidence"] = MappingProxyType({})
    return kwargs


def test_build_ath_measurement_record_rejects_non_measured_with_real_peak_slot():
    kwargs = _unmeasured_partial_kwargs()
    kwargs["consolidated_peak_slot"] = SAMPLE_SLOT
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_non_measured_with_real_block_time():
    kwargs = _unmeasured_partial_kwargs()
    kwargs["consolidated_peak_block_time"] = SAMPLE_BLOCK_TIME
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_accepts_non_measured_with_sentinel_slot_and_block_time():
    kwargs = _unmeasured_partial_kwargs()
    measurement = build_ath_measurement_record(**kwargs)
    assert measurement.measurement_status == MEASUREMENT_STATUS_PARTIAL
    assert measurement.consolidated_peak_slot == -1
    assert measurement.consolidated_peak_block_time == -1


def test_build_ath_measurement_record_rejects_bool_consolidated_peak_slot():
    kwargs = _measured_record_kwargs()
    kwargs["consolidated_peak_slot"] = True
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


def test_build_ath_measurement_record_rejects_bool_consolidated_peak_block_time():
    kwargs = _measured_record_kwargs()
    kwargs["consolidated_peak_block_time"] = False
    with pytest.raises(Stage25ContractError):
        build_ath_measurement_record(**kwargs)


# ---------------------------------------------------------------------------
# Remediation: build_source_reconciliation_record accepts disagreement_metric=None
# ---------------------------------------------------------------------------


def test_build_source_reconciliation_record_accepts_none_disagreement_metric():
    kwargs = _reconciliation_record_kwargs(disagreement_metric=None)
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert reconciliation.disagreement_metric is None


def test_reconciliation_hash_differs_between_none_metric_and_mapping_metric():
    from types import MappingProxyType

    kwargs_none = _reconciliation_record_kwargs(disagreement_metric=None)
    kwargs_mapping = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {"price_disagreement_ppm": 0}
        )
    )
    a = build_source_reconciliation_record(**kwargs_none)
    b = build_source_reconciliation_record(**kwargs_mapping)
    assert a.disagreement_metric is None
    assert b.disagreement_metric is not None
    assert a.reconciliation_hash != b.reconciliation_hash


def test_reconciliation_hash_differs_between_none_metric_and_empty_mapping():
    from types import MappingProxyType

    kwargs_none = _reconciliation_record_kwargs(disagreement_metric=None)
    kwargs_empty = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType({})
    )
    a = build_source_reconciliation_record(**kwargs_none)
    b = build_source_reconciliation_record(**kwargs_empty)
    assert a.reconciliation_hash != b.reconciliation_hash


def test_build_source_reconciliation_record_accepts_mapping_with_int_values():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {
                "price_disagreement_ppm": 1_234,
                "peak_time_disagreement_seconds": 56,
            }
        )
    )
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert reconciliation.disagreement_metric[
        "price_disagreement_ppm"
    ] == 1_234


def test_build_source_reconciliation_record_accepts_mapping_with_none_values():
    from types import MappingProxyType

    kwargs = _reconciliation_record_kwargs(
        disagreement_metric=MappingProxyType(
            {
                "price_disagreement_ppm": None,
                "peak_time_disagreement_seconds": None,
            }
        )
    )
    reconciliation = build_source_reconciliation_record(**kwargs)
    assert (
        reconciliation.disagreement_metric["price_disagreement_ppm"]
        is None
    )
    assert (
        reconciliation.disagreement_metric[
            "peak_time_disagreement_seconds"
        ]
        is None
    )


def test_build_source_reconciliation_record_rejects_non_mapping_non_none_metric():
    """Sanity: only None and mappings are accepted; e.g. a list value
    must still raise."""
    kwargs = _reconciliation_record_kwargs(disagreement_metric=[1, 2, 3])
    with pytest.raises(Stage25ContractError):
        build_source_reconciliation_record(**kwargs)
