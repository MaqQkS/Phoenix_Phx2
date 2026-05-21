"""Stage 25.3 price-observation helper tests.

Pins:

  * Exact duplicate price observations collapse deterministically.
  * Conflicting same-source observations at the same
    ``observed_at_utc`` but a different price / source_status do NOT
    collapse.
  * Observations group by token deterministically.
  * Observations group by (token, source_family) deterministically.
  * Non-PRESENT source statuses are preserved, not silently dropped.
  * ``PRESENT`` with a valid price contributes to a window.
  * ``PARTIAL`` with a valid price contributes with the partial
    status preserved.
  * ``ABSENT`` / ``MALFORMED`` / ``DECODE_FAILED`` / ``UNSUPPORTED``
    / ``AMBIGUOUS`` cannot contribute.
  * ``price = None`` with a non-PRESENT status is preserved.
  * ``price = 0`` with the explicit ``PRICE_OBSERVED_ZERO`` reason
    code is preserved.
  * Output ordering is deterministic across two equivalent inputs.
  * Input tuples are not mutated by any helper.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    QUOTE_DENOMINATION_USD_MICRO,
    REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS,
    REASON_CODE_PRICE_OBSERVATION_NO_PRICE,
    REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.price_observation import (
    classify_price_observation,
    dedupe_price_observations,
    group_price_observations_by_token,
    group_price_observations_by_token_and_source,
    normalize_price_observations,
    price_observation_can_contribute_to_window,
    price_observation_source_status_is_non_contributing,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_price_observation,
)


# ---------------------------------------------------------------------------
# Normalize / deterministic ordering
# ---------------------------------------------------------------------------


def test_normalize_returns_deterministic_order():
    a = make_price_observation(
        source_family=SOURCE_FAMILY_BIRDEYE, price=1_000
    )
    b = make_price_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER, price=2_000
    )
    c = make_price_observation(
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY, price=3_000
    )
    first = normalize_price_observations((c, a, b))
    second = normalize_price_observations((b, c, a))
    assert first == second


def test_normalize_rejects_non_tuple_input():
    a = make_price_observation()
    with pytest.raises(Stage25ContractError):
        normalize_price_observations([a])  # type: ignore[arg-type]


def test_normalize_does_not_mutate_input():
    a = make_price_observation(price=1)
    b = make_price_observation(price=2)
    original = (b, a)
    snapshot = tuple(original)
    normalize_price_observations(original)
    assert original == snapshot


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


def test_dedupe_collapses_exact_duplicates():
    a = make_price_observation(price=1_000)
    b = make_price_observation(price=1_000)
    assert a == b
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 1


def test_dedupe_preserves_same_source_conflicts_on_price():
    a = make_price_observation(price=1_000)
    b = make_price_observation(price=2_000)
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_preserves_same_source_conflicts_on_source_status():
    a = make_price_observation(
        source_status=SOURCE_STATUS_PRESENT, price=1_000
    )
    b = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=1_000
    )
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_rejects_non_tuple_input():
    a = make_price_observation()
    with pytest.raises(Stage25ContractError):
        dedupe_price_observations([a, a])  # type: ignore[arg-type]


def test_dedupe_does_not_mutate_input():
    a = make_price_observation(price=1)
    b = make_price_observation(price=1)
    original = (a, b)
    snapshot = tuple(original)
    dedupe_price_observations(original)
    assert original == snapshot


def test_dedupe_output_ordering_is_deterministic():
    a = make_price_observation(
        source_family=SOURCE_FAMILY_BIRDEYE, price=1_000
    )
    b = make_price_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER, price=2_000
    )
    first = dedupe_price_observations((a, b))
    second = dedupe_price_observations((b, a))
    assert first == second


# ---------------------------------------------------------------------------
# Dedupe exact-collapse / non-collapse coverage
# ---------------------------------------------------------------------------


def test_dedupe_collapses_byte_identical_observations():
    a = make_price_observation(price=1_000, block_time=1_750_000_000)
    b = make_price_observation(price=1_000, block_time=1_750_000_000)
    assert a == b
    assert a.observation_hash == b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert deduped == (a,)


def test_dedupe_does_not_collapse_differing_block_time():
    """Two observations with same token/source/observed_at/price/status
    but different block_time straddle the migration boundary; they
    must remain distinct so window classification stays honest.
    """
    a = make_price_observation(
        price=1_000, block_time=1_750_000_000 - 60
    )
    b = make_price_observation(
        price=1_000, block_time=1_750_000_000 + 60
    )
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_does_not_collapse_differing_slot():
    a = make_price_observation(price=1_000, slot=251_000_000)
    b = make_price_observation(price=1_000, slot=251_000_100)
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_does_not_collapse_differing_evidence():
    a = make_price_observation(
        price=1_000, evidence={"window_label": "post_migration_primary"}
    )
    b = make_price_observation(
        price=1_000, evidence={"window_label": "post_migration_extended"}
    )
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_does_not_collapse_differing_reason_codes():
    a = make_price_observation(price=1_000)
    b = make_price_observation(
        price=1_000, reason_codes=("PRICE_OBSERVATION_NO_PRICE",)
    )
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_does_not_collapse_differing_input_missing_fields():
    a = make_price_observation(price=1_000)
    b = make_price_observation(
        price=1_000, input_missing_fields=("evidence",)
    )
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_does_not_collapse_differing_provider_id():
    a = make_price_observation(price=1_000, provider_id="provider_one")
    b = make_price_observation(price=1_000, provider_id="provider_two")
    assert a.observation_hash != b.observation_hash
    deduped = dedupe_price_observations((a, b))
    assert len(deduped) == 2


def test_dedupe_key_includes_observation_hash():
    """Sanity probe: the dedupe key uses observation_hash as its
    trailing axis so any field bound into the canonical hash
    discriminates duplicates.
    """
    from PHX2.stage25.price_observation import _dedupe_key

    a = make_price_observation(price=1_000)
    b = make_price_observation(
        price=1_000, evidence={"window_label": "different"}
    )
    assert _dedupe_key(a)[-1] == a.observation_hash
    assert _dedupe_key(b)[-1] == b.observation_hash
    assert _dedupe_key(a) != _dedupe_key(b)


def test_dedupe_output_remains_deterministic_under_hash_distinct_inputs():
    """Two equivalent inputs (different ordering) emit byte-identical
    deduped tuples even when several distinct-hash observations
    survive.
    """
    a = make_price_observation(price=1_000, block_time=1_750_000_000)
    b = make_price_observation(price=1_000, block_time=1_750_000_100)
    c = make_price_observation(price=1_000, block_time=1_750_000_200)
    first = dedupe_price_observations((c, a, b))
    second = dedupe_price_observations((b, c, a))
    assert first == second
    assert len(first) == 3


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_group_by_token_returns_deterministic_groups():
    a1 = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_A, price=1)
    a2 = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_A, price=2)
    b1 = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_B, price=3)
    grouped = group_price_observations_by_token((b1, a2, a1))
    assert list(grouped.keys()) == sorted(
        (SAMPLE_TOKEN_MINT_A, SAMPLE_TOKEN_MINT_B)
    )
    a_group = grouped[SAMPLE_TOKEN_MINT_A]
    assert len(a_group) == 2
    assert a1 in a_group
    assert a2 in a_group
    assert grouped[SAMPLE_TOKEN_MINT_B] == (b1,)


def test_group_by_token_is_stable_across_input_permutations():
    a = make_price_observation(price=1)
    b = make_price_observation(price=2)
    c = make_price_observation(token_mint=SAMPLE_TOKEN_MINT_B, price=3)
    first = group_price_observations_by_token((a, b, c))
    second = group_price_observations_by_token((c, b, a))
    assert first == second


def test_group_by_token_empty_input_returns_empty_dict():
    assert group_price_observations_by_token(()) == {}


def test_group_by_token_rejects_non_tuple_input():
    with pytest.raises(Stage25ContractError):
        group_price_observations_by_token(
            [make_price_observation()]  # type: ignore[arg-type]
        )


def test_group_by_token_and_source_returns_deterministic_groups():
    a_be = make_price_observation(
        source_family=SOURCE_FAMILY_BIRDEYE, price=1
    )
    a_ds = make_price_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER, price=2
    )
    b_be = make_price_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_BIRDEYE,
        price=3,
    )
    grouped = group_price_observations_by_token_and_source(
        (b_be, a_ds, a_be)
    )
    keys = list(grouped.keys())
    assert keys == sorted(keys)
    assert grouped[(SAMPLE_TOKEN_MINT_A, SOURCE_FAMILY_BIRDEYE)] == (
        a_be,
    )
    assert grouped[
        (SAMPLE_TOKEN_MINT_A, SOURCE_FAMILY_DEXSCREENER)
    ] == (a_ds,)
    assert grouped[(SAMPLE_TOKEN_MINT_B, SOURCE_FAMILY_BIRDEYE)] == (
        b_be,
    )


def test_group_by_token_and_source_rejects_non_tuple_input():
    with pytest.raises(Stage25ContractError):
        group_price_observations_by_token_and_source(
            [make_price_observation()]  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Source-status preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        SOURCE_STATUS_PARTIAL,
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_UNSUPPORTED,
        SOURCE_STATUS_AMBIGUOUS,
    ],
)
def test_non_present_source_statuses_are_preserved_through_normalize(status):
    observation = make_price_observation(source_status=status, price=None)
    normalized = normalize_price_observations((observation,))
    assert normalized == (observation,)
    assert normalized[0].source_status == status


def test_non_present_status_with_price_none_preserved():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=None
    )
    assert observation.price is None
    assert observation.source_status == SOURCE_STATUS_PARTIAL


def test_zero_price_with_explicit_observed_zero_preserved():
    observation = make_price_observation(
        price=0, reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,)
    )
    assert observation.price == 0
    assert REASON_CODE_PRICE_OBSERVED_ZERO in observation.reason_codes


# ---------------------------------------------------------------------------
# Contribution predicate
# ---------------------------------------------------------------------------


def test_present_with_price_can_contribute():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PRESENT, price=1_234
    )
    assert price_observation_can_contribute_to_window(observation) is True


def test_partial_with_price_can_contribute():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=42
    )
    assert price_observation_can_contribute_to_window(observation) is True


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
def test_non_contributing_statuses_cannot_contribute(status):
    observation = make_price_observation(
        source_status=status, price=None
    )
    assert (
        price_observation_can_contribute_to_window(observation) is False
    )
    assert (
        price_observation_source_status_is_non_contributing(observation)
        is True
    )


def test_partial_with_price_none_cannot_contribute():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PARTIAL, price=None
    )
    assert (
        price_observation_can_contribute_to_window(observation) is False
    )


def test_present_with_explicit_zero_can_contribute():
    observation = make_price_observation(
        price=0, reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,)
    )
    assert price_observation_can_contribute_to_window(observation) is True


# ---------------------------------------------------------------------------
# Classification helper
# ---------------------------------------------------------------------------


def test_classify_present_with_valid_price_returns_original():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_PRESENT, price=99
    )
    classified = classify_price_observation(observation)
    assert classified == observation


def test_classify_non_contributing_status_annotates_observation():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_ABSENT,
        price=None,
        quote_denomination=QUOTE_DENOMINATION_USD_MICRO,
    )
    classified = classify_price_observation(observation)
    assert (
        REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS
        in classified.reason_codes
    )
    assert REASON_CODE_PRICE_OBSERVATION_NO_PRICE in classified.reason_codes
    assert classified.observation_hash != observation.observation_hash


def test_classify_zero_price_with_explicit_reason_adds_marker():
    observation = make_price_observation(
        price=0, reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,)
    )
    classified = classify_price_observation(observation)
    assert (
        REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT
        in classified.reason_codes
    )


def test_classify_does_not_duplicate_existing_codes():
    observation = make_price_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
        price=None,
        reason_codes=(
            REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS,
            REASON_CODE_PRICE_OBSERVATION_NO_PRICE,
        ),
    )
    classified = classify_price_observation(observation)
    assert classified.reason_codes == observation.reason_codes
    # Reason-code set is unchanged so the rebuilt record carries the
    # same observation_hash.
    assert classified.observation_hash == observation.observation_hash


# ---------------------------------------------------------------------------
# Fixed clock smoke
# ---------------------------------------------------------------------------


def test_fixtures_carry_fixed_clock():
    a = make_price_observation()
    b = make_price_observation()
    assert a.observed_at_utc == FIXED_CLOCK_UTC
    assert a == b
