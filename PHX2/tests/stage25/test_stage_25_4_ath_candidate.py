"""Stage 25.4 ATH candidate builder tests.

Pins:

  * POST_MIGRATION_PRIMARY / POST_MIGRATION_EXTENDED observations
    with PRESENT price are ATH-eligible.
  * PRE_MIGRATION_EXCLUDED / UNKNOWN_WINDOW observations are
    ineligible regardless of source_status or price.
  * ``price = None`` observations are ineligible.
  * ABSENT / MALFORMED / DECODE_FAILED / UNSUPPORTED / AMBIGUOUS
    source statuses are ineligible.
  * PARTIAL with a valid price is eligible but the candidate
    carries ``CONFIDENCE_LEVEL_LOW`` and a partial-source reason
    code.
  * Highest price wins within one (token, source) group.
  * Tie on price prefers earliest ``observed_at_utc``; secondary
    tie uses the deterministic ``observation_hash``.
  * ON_CHAIN_SWAP_REPLAY -> ``SWAP_REPLAY_PEAK``;
    BIRDEYE / DEXSCREENER / WEBSOCKET_CAPTURE ->
    ``SOURCE_REPORTED_PEAK``.
  * No eligible windows -> ``INSUFFICIENT_DATA`` with
    ``peak_price=None`` and confidence ``NONE``.
  * Pre-migration-only group -> ``INSUFFICIENT_DATA`` with the
    pre-migration reason code.
  * Unknown-window-only group -> ``INSUFFICIENT_DATA`` with the
    unknown-window reason code.
  * Token / source mismatch on ``build_ath_candidate_for_token_source``
    raises ``Stage25ContractError``.
  * ``build_ath_candidates`` groups by (token, source) and emits
    candidates in deterministic order.
  * ``candidate_hash`` is deterministic across two equivalent
    builds and changes when price / time / status / kind /
    confidence / reason-codes change.
  * Input tuples are not mutated.
  * No cross-source comparison is performed: peaks are local to
    each (token, source) group.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.ath_candidate import (
    build_ath_candidate_for_token_source,
    build_ath_candidates,
    group_price_window_observations_by_token_and_source,
    price_window_observation_is_ath_eligible,
    select_source_peak_window_observation,
)
from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_THRESHOLD_VERSION,
    PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    QUOTE_DENOMINATION_USD_MICRO,
    REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA,
    REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS,
    REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK,
    REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED,
    REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_FAMILY_WEBSOCKET_CAPTURE,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_ATH_CANDIDATE_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    build_ath_candidate_record,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_price_window_observation,
)


# ---------------------------------------------------------------------------
# Eligibility predicate
# ---------------------------------------------------------------------------


def test_post_migration_primary_with_present_price_is_eligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        source_status=SOURCE_STATUS_PRESENT,
        price=100,
    )
    assert price_window_observation_is_ath_eligible(observation) is True


def test_post_migration_extended_with_present_price_is_eligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
        source_status=SOURCE_STATUS_PRESENT,
        price=200,
    )
    assert price_window_observation_is_ath_eligible(observation) is True


def test_pre_migration_excluded_is_ineligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
        source_status=SOURCE_STATUS_PRESENT,
        price=999,
    )
    assert price_window_observation_is_ath_eligible(observation) is False


def test_unknown_window_is_ineligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
        source_status=SOURCE_STATUS_AMBIGUOUS,
        price=None,
    )
    assert price_window_observation_is_ath_eligible(observation) is False


def test_missing_migration_unknown_window_is_ineligible():
    """A window observation that was projected against a missing
    migration measurement carries ``UNKNOWN_WINDOW``; it must not
    become ATH-eligible even when the source still claims PRESENT.
    """
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
        source_status=SOURCE_STATUS_PRESENT,
        price=123,
    )
    assert price_window_observation_is_ath_eligible(observation) is False


def test_price_none_is_ineligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        source_status=SOURCE_STATUS_PARTIAL,
        price=None,
    )
    assert price_window_observation_is_ath_eligible(observation) is False


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
def test_non_contributing_status_is_ineligible(status):
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        source_status=status,
        price=None,
    )
    assert price_window_observation_is_ath_eligible(observation) is False


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
def test_non_contributing_status_with_non_null_price_stays_ineligible(status):
    """Minor-finding remediation: a non-contributing source status must
    not produce a peak even when the upstream window observation
    carries a non-null positive price. Eligibility is gated on the
    source_status closed set, NOT on the presence of a price field.
    """
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        source_status=status,
        price=10_000_000,
    )
    assert price_window_observation_is_ath_eligible(observation) is False
    # And confirm through the full builder path: the resulting
    # candidate cannot be a peak record -- it is INSUFFICIENT_DATA
    # with NULL peak price and a non-contributing-status reason code.
    candidate = build_ath_candidate_for_token_source(
        observation.token_mint, observation.source_family, (observation,)
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert candidate.peak_price is None
    assert candidate.confidence_level == CONFIDENCE_LEVEL_NONE


def test_partial_with_valid_price_is_eligible():
    observation = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        source_status=SOURCE_STATUS_PARTIAL,
        price=42,
    )
    assert price_window_observation_is_ath_eligible(observation) is True


# ---------------------------------------------------------------------------
# Peak selection
# ---------------------------------------------------------------------------


def test_select_peak_picks_highest_price():
    low = make_price_window_observation(price=100, block_time=1_750_000_001)
    high = make_price_window_observation(
        price=500,
        block_time=1_750_000_002,
        observed_at_utc="2026-01-01T00:00:01Z",
    )
    mid = make_price_window_observation(
        price=200,
        block_time=1_750_000_003,
        observed_at_utc="2026-01-01T00:00:02Z",
    )
    peak = select_source_peak_window_observation((low, high, mid))
    assert peak is high


def test_select_peak_tie_chooses_earliest_observed_at_utc():
    later = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:10Z",
        block_time=1_750_000_010,
    )
    earlier = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:05Z",
        block_time=1_750_000_005,
    )
    peak = select_source_peak_window_observation((later, earlier))
    assert peak is earlier


def test_select_peak_tie_on_price_and_time_uses_hash_disambiguator():
    a = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:00Z",
        block_time=1_750_000_000,
        slot=1,
    )
    b = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:00Z",
        block_time=1_750_000_000,
        slot=2,
    )
    assert a.observation_hash != b.observation_hash
    peak = select_source_peak_window_observation((a, b))
    # The chosen peak is the one with the lower observation_hash
    # under deterministic ordering (sort_key tuple negates price so
    # ``min`` returns the highest-priced entry with the lowest
    # downstream tie-break).
    expected = a if a.observation_hash < b.observation_hash else b
    assert peak is expected


def test_select_peak_returns_none_when_no_eligible():
    pre_migration = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
        price=100,
    )
    unknown = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
        price=200,
    )
    assert (
        select_source_peak_window_observation((pre_migration, unknown))
        is None
    )


# ---------------------------------------------------------------------------
# Candidate kind mapping
# ---------------------------------------------------------------------------


def test_swap_replay_source_maps_to_swap_replay_peak():
    obs = make_price_window_observation(
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
        price=999,
    )
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint,
        SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
        (obs,),
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK
    assert (
        REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK
        in candidate.reason_codes
    )


@pytest.mark.parametrize(
    "source_family",
    [
        SOURCE_FAMILY_BIRDEYE,
        SOURCE_FAMILY_DEXSCREENER,
        SOURCE_FAMILY_WEBSOCKET_CAPTURE,
    ],
)
def test_reportable_source_maps_to_source_reported_peak(source_family):
    obs = make_price_window_observation(
        source_family=source_family,
        price=500,
    )
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint,
        source_family,
        (obs,),
    )
    assert candidate.candidate_kind == (
        ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK
    )
    assert (
        REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK
        in candidate.reason_codes
    )


# ---------------------------------------------------------------------------
# Confidence + partial source status
# ---------------------------------------------------------------------------


def test_present_source_yields_first_class_medium_confidence():
    obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PRESENT, price=400
    )
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    assert candidate.source_status == SOURCE_STATUS_PRESENT
    assert candidate.confidence_level == CONFIDENCE_LEVEL_MEDIUM


def test_partial_source_yields_first_class_low_confidence_and_reason_code():
    obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=400
    )
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    assert candidate.source_status == SOURCE_STATUS_PARTIAL
    assert candidate.confidence_level == CONFIDENCE_LEVEL_LOW
    assert (
        REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS
        in candidate.reason_codes
    )


def test_partial_loses_to_present_on_higher_price():
    present_high = make_price_window_observation(
        source_status=SOURCE_STATUS_PRESENT,
        price=1_000,
        observed_at_utc="2026-01-01T00:00:01Z",
        block_time=1_750_000_001,
    )
    partial_low = make_price_window_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        price=500,
        observed_at_utc="2026-01-01T00:00:02Z",
        block_time=1_750_000_002,
    )
    candidate = build_ath_candidate_for_token_source(
        present_high.token_mint,
        present_high.source_family,
        (present_high, partial_low),
    )
    assert candidate.peak_price == 1_000
    assert candidate.source_status == SOURCE_STATUS_PRESENT
    assert candidate.confidence_level == CONFIDENCE_LEVEL_MEDIUM
    assert (
        REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS
        not in candidate.reason_codes
    )


# ---------------------------------------------------------------------------
# Tie-break reason code
# ---------------------------------------------------------------------------


def test_price_tie_attaches_tie_break_reason_code():
    a = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:00Z",
        block_time=1_750_000_000,
    )
    b = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:05Z",
        block_time=1_750_000_005,
    )
    candidate = build_ath_candidate_for_token_source(
        a.token_mint, a.source_family, (a, b)
    )
    assert (
        REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED
        in candidate.reason_codes
    )


def test_no_tie_break_reason_code_when_unique_max():
    high = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:00Z",
        block_time=1_750_000_000,
    )
    low = make_price_window_observation(
        price=100,
        observed_at_utc="2026-01-01T00:00:05Z",
        block_time=1_750_000_005,
    )
    candidate = build_ath_candidate_for_token_source(
        high.token_mint, high.source_family, (high, low)
    )
    assert (
        REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED
        not in candidate.reason_codes
    )


# ---------------------------------------------------------------------------
# Insufficient-data cases
# ---------------------------------------------------------------------------


def test_no_observations_yields_insufficient_data_candidate():
    candidate = build_ath_candidate_for_token_source(
        SAMPLE_TOKEN_MINT_A,
        SOURCE_FAMILY_BIRDEYE,
        (),
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert candidate.peak_price is None
    assert candidate.peak_observed_at_utc == ""
    assert candidate.peak_slot == -1
    assert candidate.peak_block_time == -1
    assert candidate.confidence_level == CONFIDENCE_LEVEL_NONE
    assert candidate.source_status == SOURCE_STATUS_ABSENT
    assert (
        REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA
        in candidate.reason_codes
    )
    assert (
        REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS
        in candidate.reason_codes
    )


def test_pre_migration_only_group_yields_insufficient_with_reason_code():
    pre = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
        price=999,
    )
    candidate = build_ath_candidate_for_token_source(
        pre.token_mint, pre.source_family, (pre,)
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert (
        REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED
        in candidate.reason_codes
    )
    assert candidate.peak_price is None


def test_unknown_window_only_group_yields_insufficient_with_reason_code():
    unk = make_price_window_observation(
        window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
        source_status=SOURCE_STATUS_AMBIGUOUS,
        price=None,
    )
    candidate = build_ath_candidate_for_token_source(
        unk.token_mint, unk.source_family, (unk,)
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert (
        REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED
        in candidate.reason_codes
    )
    assert candidate.peak_price is None


def test_all_non_contributing_status_yields_insufficient():
    absent = make_price_window_observation(
        source_status=SOURCE_STATUS_ABSENT,
        price=None,
    )
    candidate = build_ath_candidate_for_token_source(
        absent.token_mint, absent.source_family, (absent,)
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert (
        REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS
        in candidate.reason_codes
    )


def test_null_price_only_group_yields_insufficient_with_null_price_code():
    null_price = make_price_window_observation(
        source_status=SOURCE_STATUS_PARTIAL,
        price=None,
    )
    candidate = build_ath_candidate_for_token_source(
        null_price.token_mint, null_price.source_family, (null_price,)
    )
    assert candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    assert (
        REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED
        in candidate.reason_codes
    )


# ---------------------------------------------------------------------------
# Token / source-family mismatch
# ---------------------------------------------------------------------------


def test_token_mismatch_in_per_group_builder_raises():
    obs = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
    )
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source(
            SAMPLE_TOKEN_MINT_B,
            SOURCE_FAMILY_BIRDEYE,
            (obs,),
        )


def test_source_family_mismatch_in_per_group_builder_raises():
    obs = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
    )
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source(
            SAMPLE_TOKEN_MINT_A,
            SOURCE_FAMILY_DEXSCREENER,
            (obs,),
        )


def test_non_namedtuple_entry_raises():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source(
            SAMPLE_TOKEN_MINT_A,
            SOURCE_FAMILY_BIRDEYE,
            ("not a record",),  # type: ignore[arg-type]
        )


def test_empty_token_raises():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source("", SOURCE_FAMILY_BIRDEYE, ())


def test_empty_source_family_raises():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source(SAMPLE_TOKEN_MINT_A, "", ())


def test_non_tuple_observations_raises():
    with pytest.raises(Stage25ContractError):
        build_ath_candidate_for_token_source(
            SAMPLE_TOKEN_MINT_A,
            SOURCE_FAMILY_BIRDEYE,
            [make_price_window_observation()],  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------


def test_build_ath_candidates_groups_by_token_and_source():
    a_birdeye = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        price=100,
    )
    a_dex = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        price=300,
    )
    b_birdeye = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_BIRDEYE,
        price=200,
    )
    candidates = build_ath_candidates((a_dex, b_birdeye, a_birdeye))
    keys = [
        (candidate.token_mint, candidate.source_family)
        for candidate in candidates
    ]
    assert keys == sorted(keys)
    assert len(candidates) == 3


def test_build_ath_candidates_is_deterministic_across_input_order():
    a = make_price_window_observation(
        price=100,
        observed_at_utc="2026-01-01T00:00:01Z",
        block_time=1_750_000_001,
    )
    b = make_price_window_observation(
        price=500,
        observed_at_utc="2026-01-01T00:00:02Z",
        block_time=1_750_000_002,
    )
    c = make_price_window_observation(
        price=200,
        observed_at_utc="2026-01-01T00:00:03Z",
        block_time=1_750_000_003,
    )
    first = build_ath_candidates((a, b, c))
    second = build_ath_candidates((c, b, a))
    assert first == second


def test_build_ath_candidates_empty_input_returns_empty_tuple():
    assert build_ath_candidates(()) == ()


def test_build_ath_candidates_returns_only_namedtuple_records():
    obs = make_price_window_observation()
    candidates = build_ath_candidates((obs,))
    for candidate in candidates:
        assert isinstance(candidate, Stage25ATHCandidate)


# ---------------------------------------------------------------------------
# Cross-source independence
# ---------------------------------------------------------------------------


def test_no_cross_source_comparison_one_token_two_sources():
    """Two sources of one token must produce two independent candidates.

    The peak chosen for source A must reflect only source-A
    observations, even when source B has a higher price.
    """
    a_low_birdeye = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        price=100,
        observed_at_utc="2026-01-01T00:00:01Z",
        block_time=1_750_000_001,
    )
    a_high_dex = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        price=999_999,
        observed_at_utc="2026-01-01T00:00:02Z",
        block_time=1_750_000_002,
    )
    candidates = build_ath_candidates((a_low_birdeye, a_high_dex))
    by_source = {
        (candidate.token_mint, candidate.source_family): candidate
        for candidate in candidates
    }
    assert by_source[
        (SAMPLE_TOKEN_MINT_A, SOURCE_FAMILY_BIRDEYE)
    ].peak_price == 100
    assert by_source[
        (SAMPLE_TOKEN_MINT_A, SOURCE_FAMILY_DEXSCREENER)
    ].peak_price == 999_999


def test_group_helper_does_not_mutate_input_tuple():
    obs1 = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        price=100,
    )
    obs2 = make_price_window_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
        price=200,
    )
    original = (obs1, obs2)
    original_snapshot = tuple(original)
    grouped = group_price_window_observations_by_token_and_source(original)
    assert original == original_snapshot
    assert len(grouped) == 2


def test_per_group_builder_does_not_mutate_input_tuple():
    obs1 = make_price_window_observation(price=100)
    obs2 = make_price_window_observation(price=500)
    original = (obs1, obs2)
    snapshot = tuple(original)
    build_ath_candidate_for_token_source(
        obs1.token_mint, obs1.source_family, original
    )
    assert original == snapshot


# ---------------------------------------------------------------------------
# Hash determinism + sensitivity
# ---------------------------------------------------------------------------


def _baseline_record(**overrides) -> Stage25ATHCandidate:
    """Helper that constructs a baseline Stage25ATHCandidate via the
    record-validator helper, applying overrides.

    The default kwargs match the production builder's contract: a
    contributing candidate carries ``source_status=PRESENT`` and
    ``confidence_level=MEDIUM`` -- both now first-class fields on the
    record rather than evidence-mapping keys.
    """
    defaults = dict(
        token_mint=SAMPLE_TOKEN_MINT_A,
        source_family=SOURCE_FAMILY_BIRDEYE,
        source_status=SOURCE_STATUS_PRESENT,
        candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
        peak_observed_at_utc=FIXED_CLOCK_UTC,
        peak_slot=251_000_010,
        peak_block_time=1_750_000_010,
        peak_price=1_234_567,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
        reason_codes=(REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,),
        evidence={
            "candidate_version": STAGE25_ATH_CANDIDATE_VERSION,
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
        },
        input_missing_fields=(),
    )
    defaults.update(overrides)
    return build_ath_candidate_record(**defaults)


def test_candidate_hash_is_deterministic_across_equivalent_builds():
    a = _baseline_record()
    b = _baseline_record()
    assert a.candidate_hash == b.candidate_hash


def test_candidate_hash_changes_when_peak_price_changes():
    a = _baseline_record(peak_price=1_234_567)
    b = _baseline_record(peak_price=2_000_000)
    assert a.candidate_hash != b.candidate_hash


def test_candidate_hash_changes_when_peak_observed_at_utc_changes():
    a = _baseline_record(peak_observed_at_utc="2026-01-01T00:00:00Z")
    b = _baseline_record(peak_observed_at_utc="2026-01-01T00:00:01Z")
    assert a.candidate_hash != b.candidate_hash


def test_candidate_hash_changes_when_candidate_kind_changes():
    a = _baseline_record(candidate_kind=ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK)
    b = _baseline_record(candidate_kind=ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK)
    assert a.candidate_hash != b.candidate_hash


def test_candidate_hash_changes_when_first_class_source_status_changes():
    """``source_status`` is now a first-class field bound directly into
    the canonical hash projection. A change to that field alone (with
    no other field change) must change the candidate_hash so a
    Stage 25.5+ source reconciler can detect status drift without
    inspecting evidence.
    """
    a = _baseline_record(
        source_status=SOURCE_STATUS_PRESENT,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
    )
    b = _baseline_record(
        source_status=SOURCE_STATUS_PARTIAL,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
    )
    assert a.candidate_hash != b.candidate_hash


def test_candidate_hash_changes_when_first_class_confidence_level_changes():
    """``confidence_level`` is now a first-class field bound directly
    into the canonical hash projection.
    """
    a = _baseline_record(confidence_level=CONFIDENCE_LEVEL_MEDIUM)
    b = _baseline_record(confidence_level=CONFIDENCE_LEVEL_LOW)
    assert a.candidate_hash != b.candidate_hash


def test_candidate_hash_changes_when_reason_codes_change():
    a = _baseline_record(
        reason_codes=(REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,)
    )
    b = _baseline_record(
        reason_codes=(
            REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,
            REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS,
        )
    )
    assert a.candidate_hash != b.candidate_hash


def test_full_pipeline_candidate_hash_is_deterministic():
    obs = make_price_window_observation(price=900)
    first = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    second = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    assert first.candidate_hash == second.candidate_hash


def test_builder_path_hash_changes_when_source_status_changes():
    """Hash sensitivity via the production builder path.

    Two candidates that differ only in the upstream window
    observation's ``source_status`` produce different candidate
    hashes because the first-class fields are bound into the
    canonical hash projection.
    """
    present_obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PRESENT, price=500
    )
    partial_obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=500
    )
    present_candidate = build_ath_candidate_for_token_source(
        present_obs.token_mint, present_obs.source_family, (present_obs,)
    )
    partial_candidate = build_ath_candidate_for_token_source(
        partial_obs.token_mint, partial_obs.source_family, (partial_obs,)
    )
    assert (
        present_candidate.candidate_hash
        != partial_candidate.candidate_hash
    )


def test_builder_path_hash_changes_when_confidence_level_changes():
    """Through the production builder, ``source_status=PRESENT`` maps to
    ``CONFIDENCE_LEVEL_MEDIUM`` and ``SOURCE_STATUS_PARTIAL`` maps to
    ``CONFIDENCE_LEVEL_LOW``. The two confidence values are bound into
    the canonical hash so changing the upstream status alone (which
    drives the confidence change) produces distinct candidate hashes.
    """
    present_obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PRESENT, price=500
    )
    partial_obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=500
    )
    present_candidate = build_ath_candidate_for_token_source(
        present_obs.token_mint, present_obs.source_family, (present_obs,)
    )
    partial_candidate = build_ath_candidate_for_token_source(
        partial_obs.token_mint, partial_obs.source_family, (partial_obs,)
    )
    assert (
        present_candidate.confidence_level == CONFIDENCE_LEVEL_MEDIUM
    )
    assert partial_candidate.confidence_level == CONFIDENCE_LEVEL_LOW
    assert (
        present_candidate.candidate_hash
        != partial_candidate.candidate_hash
    )


# ---------------------------------------------------------------------------
# Evidence/first-class separation
# ---------------------------------------------------------------------------


def test_evidence_does_not_carry_source_status_or_confidence_level_keys():
    """Stage 25.4 audit remediation: the production builder writes
    ``source_status`` and ``confidence_level`` only to the first-class
    record fields. Evidence must NOT carry them so a downstream reader
    cannot encounter divergent first-class vs. evidence values.
    """
    obs = make_price_window_observation(
        source_status=SOURCE_STATUS_PRESENT, price=500
    )
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    assert "source_status" not in candidate.evidence
    assert "selected_source_status" not in candidate.evidence
    assert "confidence_level" not in candidate.evidence


def test_insufficient_candidate_evidence_does_not_carry_status_or_confidence():
    candidate = build_ath_candidate_for_token_source(
        SAMPLE_TOKEN_MINT_A,
        SOURCE_FAMILY_BIRDEYE,
        (),
    )
    assert "source_status" not in candidate.evidence
    assert "selected_source_status" not in candidate.evidence
    assert "confidence_level" not in candidate.evidence


# ---------------------------------------------------------------------------
# Zero-price peak preserves PRICE_OBSERVED_ZERO invariant
# ---------------------------------------------------------------------------


def test_zero_price_peak_preserves_price_observed_zero_reason():
    """A zero-price observation can only be selected when it is the
    only eligible entry. The resulting candidate must carry the
    upstream ``PRICE_OBSERVED_ZERO`` reason code so the model
    validator accepts the zero peak.
    """
    zero_obs = make_price_window_observation(
        price=0,
        reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,),
    )
    candidate = build_ath_candidate_for_token_source(
        zero_obs.token_mint, zero_obs.source_family, (zero_obs,)
    )
    assert candidate.peak_price == 0
    assert REASON_CODE_PRICE_OBSERVED_ZERO in candidate.reason_codes
    assert candidate.candidate_kind == (
        ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK
    )


# ---------------------------------------------------------------------------
# Version axis pinning
# ---------------------------------------------------------------------------


def test_candidate_evidence_records_candidate_version_axis():
    obs = make_price_window_observation(price=500)
    candidate = build_ath_candidate_for_token_source(
        obs.token_mint, obs.source_family, (obs,)
    )
    assert (
        candidate.evidence["candidate_version"]
        == STAGE25_ATH_CANDIDATE_VERSION
    )
    assert (
        candidate.evidence["threshold_version"] == DEFAULT_THRESHOLD_VERSION
    )
