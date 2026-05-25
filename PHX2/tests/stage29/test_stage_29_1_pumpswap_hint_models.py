"""Stage 29.1 PumpSwap hint extraction models pins.

Pins:

  * Each closed-set vocabulary has the exact membership the
    Stage 29.0 spec §13 reserved.
  * Each ``is_*_value`` predicate accepts every token in its
    closed set and rejects non-strings, empty strings, and
    out-of-set strings.
  * ``Stage29_1PumpSwapHintExtractorError`` carries a closed-
    set reason and emits a deterministic ``str(...)``.
  * ``Stage29_1PumpSwapHintExtractionResult`` is a frozen
    dataclass; direct construction runs the field-validator
    in ``__post_init__`` so consistency contracts cannot be
    bypassed.
  * The HINTS_EXTRACTED ↔ quartet-populated invariant holds
    in both directions (extracted requires quartet; missing
    quartet rejects).
  * The NO_EVIDENCE ↔ all-None invariant holds.
  * ``bonding_curve_version_hint`` is rejected as non-None at
    Stage 29.1 (deferred axis).
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    HINT_EXTRACTION_OUTCOME_VALUES,
    NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE,
    NO_EVIDENCE_REASON_META_MISSING,
    NO_EVIDENCE_REASON_NONE,
    NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
    NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE,
    NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES,
    NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS,
    NO_EVIDENCE_REASON_QUOTE_MINT_NOT_KNOWN_QUOTE,
    NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
    NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
    NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
    NO_EVIDENCE_REASON_VALUES,
    POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
    POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING,
    POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES,
    QUOTE_MINT_EVIDENCE_SOURCE_NONE,
    QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE,
    QUOTE_MINT_EVIDENCE_SOURCE_VALUES,
    Stage29_1PumpSwapHintExtractionResult,
    Stage29_1PumpSwapHintExtractorError,
    is_hint_extraction_outcome_value,
    is_no_evidence_reason_value,
    is_pool_account_evidence_source_value,
    is_quote_mint_evidence_source_value,
)


# ---------------------------------------------------------------------------
# Closed-set memberships
# ---------------------------------------------------------------------------


def test_hint_extraction_outcome_closed_set_membership():
    assert HINT_EXTRACTION_OUTCOME_VALUES == (
        HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
        HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    )


def test_no_evidence_reason_closed_set_membership():
    expected = (
        NO_EVIDENCE_REASON_NONE,
        NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
        NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
        NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
        NO_EVIDENCE_REASON_META_MISSING,
        NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
        NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES,
        (
            NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE
        ),
        (
            NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES
        ),
        (
            NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS
        ),
        NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE,
        NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE,
        NO_EVIDENCE_REASON_QUOTE_MINT_NOT_KNOWN_QUOTE,
    )
    assert NO_EVIDENCE_REASON_VALUES == expected


def test_pool_account_evidence_source_closed_set_membership():
    assert POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES == (
        POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
        POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING,
    )


def test_quote_mint_evidence_source_closed_set_membership():
    assert QUOTE_MINT_EVIDENCE_SOURCE_VALUES == (
        QUOTE_MINT_EVIDENCE_SOURCE_NONE,
        QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE,
    )


# ---------------------------------------------------------------------------
# Predicate behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", HINT_EXTRACTION_OUTCOME_VALUES
)
def test_is_hint_extraction_outcome_value_accepts_each(value):
    assert is_hint_extraction_outcome_value(value)


def test_is_hint_extraction_outcome_value_rejects_outside():
    for bad in ("", "OTHER", None, 123, b"HINTS_EXTRACTED"):
        assert not is_hint_extraction_outcome_value(bad)


@pytest.mark.parametrize("value", NO_EVIDENCE_REASON_VALUES)
def test_is_no_evidence_reason_value_accepts_each(value):
    assert is_no_evidence_reason_value(value)


def test_is_no_evidence_reason_value_rejects_outside():
    for bad in ("", "OTHER_REASON", None, 0, b"NONE"):
        assert not is_no_evidence_reason_value(bad)


@pytest.mark.parametrize(
    "value", POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES
)
def test_is_pool_account_evidence_source_value_accepts_each(value):
    assert is_pool_account_evidence_source_value(value)


def test_is_pool_account_evidence_source_value_rejects_outside():
    for bad in ("", "OTHER", None, 1):
        assert not is_pool_account_evidence_source_value(bad)


@pytest.mark.parametrize(
    "value", QUOTE_MINT_EVIDENCE_SOURCE_VALUES
)
def test_is_quote_mint_evidence_source_value_accepts_each(value):
    assert is_quote_mint_evidence_source_value(value)


def test_is_quote_mint_evidence_source_value_rejects_outside():
    for bad in ("", "OTHER", None, 1):
        assert not is_quote_mint_evidence_source_value(bad)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


def test_exception_carries_closed_set_reason_and_str():
    err = Stage29_1PumpSwapHintExtractorError("EXAMPLE_REASON")
    assert err.reason == "EXAMPLE_REASON"
    text = str(err)
    assert "EXAMPLE_REASON" in text
    assert "Stage 29.1 PumpSwap hint extractor error" in text


# ---------------------------------------------------------------------------
# Frozen-dataclass enforcement
# ---------------------------------------------------------------------------


def _ok_no_evidence_result() -> (
    Stage29_1PumpSwapHintExtractionResult
):
    return Stage29_1PumpSwapHintExtractionResult(
        outcome=HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
        base_mint=None,
        pool_account=None,
        quote_mint=None,
        pool_program_id=None,
        provider_pair_type_hint=None,
        provider_quote_asset_hint=None,
        bonding_curve_version_hint=None,
        no_evidence_reason=NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
        pool_account_evidence_source=(
            POOL_ACCOUNT_EVIDENCE_SOURCE_NONE
        ),
        quote_mint_evidence_source=(
            QUOTE_MINT_EVIDENCE_SOURCE_NONE
        ),
        spl_token_balance_count=0,
        pool_owner_candidate_count=0,
    )


def _ok_hints_extracted_result() -> (
    Stage29_1PumpSwapHintExtractionResult
):
    return Stage29_1PumpSwapHintExtractionResult(
        outcome=HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
        base_mint="TestBaseMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
        pool_account=(
            "TestPoolAccountAAAAAAAAAAAAAAAAAAAAAAAAAAA1"
        ),
        quote_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        pool_program_id=(
            "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        ),
        provider_pair_type_hint="PUMP_SOL",
        provider_quote_asset_hint="SOL",
        bonding_curve_version_hint=None,
        no_evidence_reason=NO_EVIDENCE_REASON_NONE,
        pool_account_evidence_source=(
            POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
        ),
        quote_mint_evidence_source=(
            QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
        ),
        spl_token_balance_count=2,
        pool_owner_candidate_count=1,
    )


def test_no_evidence_result_constructible():
    record = _ok_no_evidence_result()
    assert (
        record.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )


def test_hints_extracted_result_constructible():
    record = _ok_hints_extracted_result()
    assert (
        record.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )


def test_extraction_result_is_frozen():
    record = _ok_no_evidence_result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.outcome = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Internal consistency rules
# ---------------------------------------------------------------------------


def test_hints_extracted_without_quartet_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=(
                HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
            ),
            base_mint=None,
            pool_account=None,
            quote_mint=None,
            pool_program_id=None,
            provider_pair_type_hint="PUMP_SOL",
            provider_quote_asset_hint="SOL",
            bonding_curve_version_hint=None,
            no_evidence_reason=NO_EVIDENCE_REASON_NONE,
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
            ),
            spl_token_balance_count=2,
            pool_owner_candidate_count=1,
        )


def test_hints_extracted_with_no_evidence_reason_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=(
                HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
            ),
            base_mint="TestBaseMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
            pool_account=(
                "TestPoolAccountAAAAAAAAAAAAAAAAAAAAAAAAAAA1"
            ),
            quote_mint=(
                "So11111111111111111111111111111111111111112"
            ),
            pool_program_id=(
                "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
            ),
            provider_pair_type_hint="PUMP_SOL",
            provider_quote_asset_hint="SOL",
            bonding_curve_version_hint=None,
            # Inconsistent: NO_TOKEN_BALANCES with HINTS_EXTRACTED.
            no_evidence_reason=(
                NO_EVIDENCE_REASON_NO_TOKEN_BALANCES
            ),
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
            ),
            spl_token_balance_count=2,
            pool_owner_candidate_count=1,
        )


def test_hints_extracted_with_unknown_pair_type_hint_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=(
                HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
            ),
            base_mint="TestBaseMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
            pool_account=(
                "TestPoolAccountAAAAAAAAAAAAAAAAAAAAAAAAAAA1"
            ),
            quote_mint=(
                "So11111111111111111111111111111111111111112"
            ),
            pool_program_id=(
                "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
            ),
            provider_pair_type_hint="UNKNOWN",
            provider_quote_asset_hint="SOL",
            bonding_curve_version_hint=None,
            no_evidence_reason=NO_EVIDENCE_REASON_NONE,
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
            ),
            spl_token_balance_count=2,
            pool_owner_candidate_count=1,
        )


def test_no_evidence_with_populated_slot_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
            base_mint="TestBaseMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
            pool_account=None,
            quote_mint=None,
            pool_program_id=None,
            provider_pair_type_hint=None,
            provider_quote_asset_hint=None,
            bonding_curve_version_hint=None,
            no_evidence_reason=(
                NO_EVIDENCE_REASON_NO_TOKEN_BALANCES
            ),
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_NONE
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_NONE
            ),
            spl_token_balance_count=0,
            pool_owner_candidate_count=0,
        )


def test_no_evidence_with_reason_none_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
            base_mint=None,
            pool_account=None,
            quote_mint=None,
            pool_program_id=None,
            provider_pair_type_hint=None,
            provider_quote_asset_hint=None,
            bonding_curve_version_hint=None,
            no_evidence_reason=NO_EVIDENCE_REASON_NONE,
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_NONE
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_NONE
            ),
            spl_token_balance_count=0,
            pool_owner_candidate_count=0,
        )


def test_bonding_curve_version_hint_non_none_rejected_at_29_1():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=(
                HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
            ),
            base_mint="TestBaseMintAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
            pool_account=(
                "TestPoolAccountAAAAAAAAAAAAAAAAAAAAAAAAAAA1"
            ),
            quote_mint=(
                "So11111111111111111111111111111111111111112"
            ),
            pool_program_id=(
                "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
            ),
            provider_pair_type_hint="PUMP_SOL",
            provider_quote_asset_hint="SOL",
            bonding_curve_version_hint="SOL_LEGACY",
            no_evidence_reason=NO_EVIDENCE_REASON_NONE,
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
            ),
            spl_token_balance_count=2,
            pool_owner_candidate_count=1,
        )


def test_negative_counter_rejected():
    with pytest.raises(Stage29_1PumpSwapHintExtractorError):
        Stage29_1PumpSwapHintExtractionResult(
            outcome=HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
            base_mint=None,
            pool_account=None,
            quote_mint=None,
            pool_program_id=None,
            provider_pair_type_hint=None,
            provider_quote_asset_hint=None,
            bonding_curve_version_hint=None,
            no_evidence_reason=(
                NO_EVIDENCE_REASON_NO_TOKEN_BALANCES
            ),
            pool_account_evidence_source=(
                POOL_ACCOUNT_EVIDENCE_SOURCE_NONE
            ),
            quote_mint_evidence_source=(
                QUOTE_MINT_EVIDENCE_SOURCE_NONE
            ),
            spl_token_balance_count=-1,
            pool_owner_candidate_count=0,
        )
