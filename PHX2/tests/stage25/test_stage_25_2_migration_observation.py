"""Stage 25.2 migration observation helper tests.

Pins:

  * Exact-duplicate observations collapse to a single record under
    ``dedupe_migration_observations``.
  * ``group_migration_observations_by_token`` groups by ``token_mint``
    deterministically and preserves intra-group canonical ordering.
  * Observations carrying non-PRESENT source statuses are preserved by
    the helpers, never silently dropped.
  * Same-source observations differing on signature / slot / block_time
    are NOT collapsed; they remain as distinct evidence rows so the
    measurer can flag the same-source conflict.
  * ``normalize_migration_observations`` is deterministic and does not
    mutate its input.
  * ``classify_migration_observation`` annotates observations with
    diagnostic reason codes for missing block_time / slot / signature
    and unsupported / ambiguous source statuses, returns the original
    record when no annotations apply, and never mutates its input.
"""

from __future__ import annotations

from PHX2.stage25.constants import (
    REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_MIGRATION_BLOCK_TIME_MISSING,
    REASON_CODE_MIGRATION_SIGNATURE_MISSING,
    REASON_CODE_MIGRATION_SLOT_MISSING,
    REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
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
from PHX2.stage25.migration_observation import (
    classify_migration_observation,
    dedupe_migration_observations,
    group_migration_observations_by_token,
    normalize_migration_observations,
    observation_is_present_with_full_evidence,
    observation_status_is_ambiguous,
    observation_status_is_unsupported,
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
# dedupe_migration_observations
# ---------------------------------------------------------------------------


def test_dedupe_collapses_exact_duplicates():
    obs_a = make_migration_observation()
    obs_b = make_migration_observation()
    result = dedupe_migration_observations((obs_a, obs_b))
    assert len(result) == 1
    assert result[0] == obs_a


def test_dedupe_preserves_distinct_signatures_from_same_source():
    obs_a = make_migration_observation(
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    obs_b = make_migration_observation(
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    result = dedupe_migration_observations((obs_a, obs_b))
    assert len(result) == 2


def test_dedupe_preserves_distinct_slots_from_same_source():
    obs_a = make_migration_observation(slot=251_000_000)
    obs_b = make_migration_observation(slot=251_000_001)
    result = dedupe_migration_observations((obs_a, obs_b))
    assert len(result) == 2


def test_dedupe_preserves_distinct_block_times_from_same_source():
    obs_a = make_migration_observation(block_time=1_750_000_000)
    obs_b = make_migration_observation(block_time=1_750_000_001)
    result = dedupe_migration_observations((obs_a, obs_b))
    assert len(result) == 2


def test_dedupe_preserves_distinct_source_families_for_same_token():
    obs_a = make_migration_observation(source_family=SOURCE_FAMILY_BIRDEYE)
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    result = dedupe_migration_observations((obs_a, obs_b))
    assert len(result) == 2


def test_dedupe_preserves_non_present_observations():
    obs_present = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        source_status=SOURCE_STATUS_PRESENT,
    )
    obs_absent = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    obs_unsupported = make_migration_observation(
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
        source_status=SOURCE_STATUS_UNSUPPORTED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    result = dedupe_migration_observations(
        (obs_absent, obs_present, obs_unsupported)
    )
    assert len(result) == 3
    statuses = {obs.source_status for obs in result}
    assert statuses == {
        SOURCE_STATUS_PRESENT,
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_UNSUPPORTED,
    }


def test_dedupe_does_not_mutate_input_tuple():
    obs_a = make_migration_observation()
    inputs = (obs_a, obs_a)
    _ = dedupe_migration_observations(inputs)
    assert inputs == (obs_a, obs_a)


def test_dedupe_output_order_is_deterministic():
    obs_a = make_migration_observation(source_family=SOURCE_FAMILY_BIRDEYE)
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    first = dedupe_migration_observations((obs_a, obs_b))
    second = dedupe_migration_observations((obs_b, obs_a))
    assert first == second


def test_dedupe_empty_returns_empty_tuple():
    assert dedupe_migration_observations(()) == ()


# ---------------------------------------------------------------------------
# group_migration_observations_by_token
# ---------------------------------------------------------------------------


def test_group_by_token_separates_tokens():
    obs_a = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_b = make_migration_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    grouped = group_migration_observations_by_token((obs_a, obs_b))
    assert set(grouped.keys()) == {
        SAMPLE_TOKEN_MINT_A,
        SAMPLE_TOKEN_MINT_B,
    }
    assert grouped[SAMPLE_TOKEN_MINT_A] == (obs_a,)
    assert grouped[SAMPLE_TOKEN_MINT_B] == (obs_b,)


def test_group_by_token_key_order_is_deterministic():
    obs_a = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_A)
    obs_b = make_migration_observation(
        token_mint=SAMPLE_TOKEN_MINT_B,
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    obs_c = make_migration_observation(
        token_mint=SAMPLE_TOKEN_MINT_C,
        source_family=SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    )
    grouped = group_migration_observations_by_token((obs_c, obs_a, obs_b))
    assert list(grouped.keys()) == [
        SAMPLE_TOKEN_MINT_A,
        SAMPLE_TOKEN_MINT_B,
        SAMPLE_TOKEN_MINT_C,
    ]


def test_group_by_token_intra_group_order_is_canonical():
    obs_birdeye = make_migration_observation(
        source_family=SOURCE_FAMILY_BIRDEYE,
        migration_signature=SAMPLE_MIGRATION_SIG_ALT,
    )
    obs_dex = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )
    grouped = group_migration_observations_by_token(
        (obs_dex, obs_birdeye)
    )
    group = grouped[SAMPLE_TOKEN_MINT_A]
    assert group[0].source_family == SOURCE_FAMILY_BIRDEYE
    assert group[1].source_family == SOURCE_FAMILY_DEXSCREENER


def test_group_by_token_empty_returns_empty_dict():
    assert group_migration_observations_by_token(()) == {}


def test_group_by_token_does_not_mutate_input():
    obs_a = make_migration_observation()
    obs_b = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    inputs = (obs_a, obs_b)
    _ = group_migration_observations_by_token(inputs)
    assert inputs == (obs_a, obs_b)


# ---------------------------------------------------------------------------
# normalize_migration_observations
# ---------------------------------------------------------------------------


def test_normalize_is_deterministic():
    obs_a = make_migration_observation(source_family=SOURCE_FAMILY_BIRDEYE)
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    first = normalize_migration_observations((obs_a, obs_b))
    second = normalize_migration_observations((obs_b, obs_a))
    assert first == second


def test_normalize_preserves_observation_count():
    obs_a = make_migration_observation(source_family=SOURCE_FAMILY_BIRDEYE)
    obs_b = make_migration_observation(
        source_family=SOURCE_FAMILY_DEXSCREENER,
    )
    normalized = normalize_migration_observations((obs_a, obs_b))
    assert len(normalized) == 2


def test_normalize_does_not_mutate_input():
    obs_a = make_migration_observation()
    obs_b = make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B)
    inputs = (obs_b, obs_a)
    _ = normalize_migration_observations(inputs)
    assert inputs == (obs_b, obs_a)


def test_normalize_empty_returns_empty_tuple():
    assert normalize_migration_observations(()) == ()


# ---------------------------------------------------------------------------
# classify_migration_observation
# ---------------------------------------------------------------------------


def test_classify_complete_present_is_unchanged():
    obs = make_migration_observation()
    result = classify_migration_observation(obs)
    assert result is obs


def test_classify_present_with_missing_block_time_adds_reason_code():
    obs = make_migration_observation(block_time=-1)
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_BLOCK_TIME_MISSING in result.reason_codes


def test_classify_present_with_missing_slot_adds_reason_code():
    obs = make_migration_observation(slot=-1)
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_SLOT_MISSING in result.reason_codes


def test_classify_present_with_missing_signature_adds_reason_code():
    obs = make_migration_observation(migration_signature="")
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_SIGNATURE_MISSING in result.reason_codes


def test_classify_unsupported_status_adds_reason_code():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_UNSUPPORTED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS in (
        result.reason_codes
    )


def test_classify_absent_status_uses_unsupported_reason_code():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS in (
        result.reason_codes
    )


def test_classify_malformed_status_uses_unsupported_reason_code():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_MALFORMED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS in (
        result.reason_codes
    )


def test_classify_decode_failed_status_uses_unsupported_reason_code():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_DECODE_FAILED,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS in (
        result.reason_codes
    )


def test_classify_ambiguous_status_adds_reason_code():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    result = classify_migration_observation(obs)
    assert REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS in (
        result.reason_codes
    )


def test_classify_does_not_duplicate_existing_codes():
    obs = make_migration_observation(
        slot=-1,
        reason_codes=(REASON_CODE_MIGRATION_SLOT_MISSING,),
    )
    result = classify_migration_observation(obs)
    assert result.reason_codes.count(
        REASON_CODE_MIGRATION_SLOT_MISSING
    ) == 1


def test_classify_returns_new_observation_with_updated_hash():
    obs = make_migration_observation(slot=-1)
    classified = classify_migration_observation(obs)
    assert classified.observation_hash != obs.observation_hash


def test_classify_does_not_mutate_input():
    obs = make_migration_observation(slot=-1)
    original_reason_codes = obs.reason_codes
    _ = classify_migration_observation(obs)
    assert obs.reason_codes == original_reason_codes


# ---------------------------------------------------------------------------
# Module-level predicate helpers
# ---------------------------------------------------------------------------


def test_observation_is_present_with_full_evidence_true_for_complete():
    obs = make_migration_observation()
    assert observation_is_present_with_full_evidence(obs)


def test_observation_is_present_with_full_evidence_false_for_partial_block_time():
    obs = make_migration_observation(block_time=-1)
    assert not observation_is_present_with_full_evidence(obs)


def test_observation_is_present_with_full_evidence_false_for_partial_slot():
    obs = make_migration_observation(slot=-1)
    assert not observation_is_present_with_full_evidence(obs)


def test_observation_is_present_with_full_evidence_false_for_empty_signature():
    obs = make_migration_observation(migration_signature="")
    assert not observation_is_present_with_full_evidence(obs)


def test_observation_is_present_with_full_evidence_false_for_partial_status():
    obs = make_migration_observation(source_status=SOURCE_STATUS_PARTIAL)
    assert not observation_is_present_with_full_evidence(obs)


def test_observation_status_is_unsupported_true_for_absent():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_ABSENT,
        migration_signature="",
        slot=-1,
        block_time=-1,
    )
    assert observation_status_is_unsupported(obs)


def test_observation_status_is_unsupported_false_for_present():
    obs = make_migration_observation()
    assert not observation_status_is_unsupported(obs)


def test_observation_status_is_ambiguous_true_for_ambiguous_status():
    obs = make_migration_observation(
        source_status=SOURCE_STATUS_AMBIGUOUS,
    )
    assert observation_status_is_ambiguous(obs)


def test_observation_status_is_ambiguous_false_for_present_status():
    obs = make_migration_observation()
    assert not observation_status_is_ambiguous(obs)
