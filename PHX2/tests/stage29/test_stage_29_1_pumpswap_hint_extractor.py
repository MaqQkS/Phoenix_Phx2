"""Stage 29.1 PumpSwap hint extractor pins.

Pins via constructed Yellowstone ``SubscribeUpdate`` protobuf
fixtures (no network):

  * Positive WSOL pool: owner X holds WSOL + base mint -->
    HINTS_EXTRACTED with the exact quartet + PUMP_SOL hint.
  * Positive USDC pool: owner Y holds USDC + base mint -->
    HINTS_EXTRACTED with the exact quartet + PUMP_USDC hint.
  * Vote tx -> NO_EVIDENCE with TRANSACTION_IS_VOTE_SKIPPED.
  * Failed tx (meta.err set) -> NO_EVIDENCE with
    TRANSACTION_FAILED_PER_META_ERR.
  * No token balances at all -> NO_EVIDENCE with
    NO_TOKEN_BALANCES.
  * Non-SPL-Token program_id on balances -> NO_EVIDENCE with
    NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES.
  * Owner with only WSOL (no non-WSOL co-owned) -> NO_EVIDENCE
    with NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE.
  * Two owners satisfy heuristic (ambiguous multi-pool) ->
    NO_EVIDENCE with POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES.
  * Owner holds WSOL + two distinct non-quote mints ->
    NO_EVIDENCE with POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS.
  * No-SOL-invention guard: only base + an unknown quote
    mint (not WSOL/USDC) -> hint slots None.
  * No-USDC-invention guard: symmetric.
  * Determinism: same fixture twice -> identical result.
  * Order-independence of token-balance list.
  * SPL Token-2022 program is accepted equivalently.
  * Non-string / empty owner / mint entries are silently
    skipped (not crashing).
"""

from __future__ import annotations

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
    solana_storage_pb2 as _solana_storage_pb2,
)
from PHX2.stage29.pumpswap_hint_extractor import (
    extract_pumpswap_hints,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    NO_EVIDENCE_REASON_META_MISSING,
    NO_EVIDENCE_REASON_NONE,
    NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
    NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES,
    NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS,
    NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
    NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
    NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    SPL_TOKEN_2022_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_ID,
    USDC_MINT,
    WRAPPED_SOL_MINT,
)


# ---------------------------------------------------------------------------
# Safe test fixtures (constructed protobuf shapes)
# ---------------------------------------------------------------------------


_TEST_BASE_MINT_A: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_BASE_MINT_B: str = (
    "TestBaseMintBBBB2222222222222222222222222B"
)
_TEST_POOL_OWNER_X: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_POOL_OWNER_Y: str = (
    "TestPoolYYYYYYY4444444444444444444444444Y"
)
_TEST_UNKNOWN_QUOTE_MINT: str = (
    "TestUnknownQuoteMINTAAAAAAAAAAAAAAAAAAAAAAQ"
)
_TEST_USER_OWNER: str = (
    "TestUserOwnerUUU5555555555555555555555555U"
)


def _build_token_balance(
    *,
    account_index: int,
    mint: str,
    owner: str,
    program_id: str,
) -> "_solana_storage_pb2.TokenBalance":
    tb = _solana_storage_pb2.TokenBalance()
    tb.account_index = account_index
    tb.mint = mint
    tb.owner = owner
    tb.program_id = program_id
    return tb


def _empty_subscribe_update_with_transaction() -> (
    "_geyser_pb2.SubscribeUpdate"
):
    """Build a SubscribeUpdate with an empty (but well-shaped)
    transaction variant — no token balances, no meta.err, not a
    vote. The extractor's pre-checks should fall through to the
    token-balance walk.
    """
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(range(1, 65))
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    # Touch meta so HasField("meta") returns True; leave fields
    # at defaults.
    update.transaction.transaction.meta.fee = 5000
    return update


def _add_pre_post_balance_pair(
    update: "_geyser_pb2.SubscribeUpdate",
    *,
    account_index: int,
    mint: str,
    owner: str,
    program_id: str = SPL_TOKEN_PROGRAM_ID,
) -> None:
    """Add the same (account_index, mint, owner, program_id) tuple
    to both ``pre_token_balances`` and ``post_token_balances``.
    PHX1 production observed that PumpSwap pools surface the same
    pool account on both sides of the swap; the extractor's
    dedup-by-(owner,mint) collapses the pair into one entry.
    """
    meta = update.transaction.transaction.meta
    pre = meta.pre_token_balances.add()
    pre.CopyFrom(
        _build_token_balance(
            account_index=account_index,
            mint=mint,
            owner=owner,
            program_id=program_id,
        ),
    )
    post = meta.post_token_balances.add()
    post.CopyFrom(
        _build_token_balance(
            account_index=account_index,
            mint=mint,
            owner=owner,
            program_id=program_id,
        ),
    )


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_positive_wsol_pool_extracts_full_quartet():
    update = _empty_subscribe_update_with_transaction()
    # Pool owner holds WSOL + base mint A.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )
    # An unrelated user ATA holding only the base token.
    _add_pre_post_balance_pair(
        update,
        account_index=2,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_USER_OWNER,
    )

    result = extract_pumpswap_hints(update)

    assert (
        result.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    assert result.no_evidence_reason == NO_EVIDENCE_REASON_NONE
    assert result.base_mint == _TEST_BASE_MINT_A
    assert result.pool_account == _TEST_POOL_OWNER_X
    assert result.quote_mint == WRAPPED_SOL_MINT
    assert result.pool_program_id == PUMPSWAP_PROGRAM_ID
    assert result.provider_pair_type_hint == "PUMP_SOL"
    assert result.provider_quote_asset_hint == "SOL"
    assert result.bonding_curve_version_hint is None


def test_positive_usdc_pool_extracts_full_quartet():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=USDC_MINT,
        owner=_TEST_POOL_OWNER_Y,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_B,
        owner=_TEST_POOL_OWNER_Y,
    )

    result = extract_pumpswap_hints(update)

    assert (
        result.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    assert result.base_mint == _TEST_BASE_MINT_B
    assert result.pool_account == _TEST_POOL_OWNER_Y
    assert result.quote_mint == USDC_MINT
    assert result.pool_program_id == PUMPSWAP_PROGRAM_ID
    assert result.provider_pair_type_hint == "PUMP_USDC"
    assert result.provider_quote_asset_hint == "USDC"
    assert result.bonding_curve_version_hint is None


def test_positive_token_2022_pool_extracts():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
        program_id=SPL_TOKEN_2022_PROGRAM_ID,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
        program_id=SPL_TOKEN_2022_PROGRAM_ID,
    )

    result = extract_pumpswap_hints(update)

    assert (
        result.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    assert result.quote_mint == WRAPPED_SOL_MINT
    assert result.base_mint == _TEST_BASE_MINT_A


def test_positive_token_balance_list_order_independent():
    """Pool extraction must be order-independent over the
    token-balance list.
    """
    update_a = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update_a,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update_a,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    update_b = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update_b,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update_b,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )

    result_a = extract_pumpswap_hints(update_a)
    result_b = extract_pumpswap_hints(update_b)

    assert result_a.outcome == result_b.outcome
    assert result_a.base_mint == result_b.base_mint
    assert result_a.pool_account == result_b.pool_account
    assert result_a.quote_mint == result_b.quote_mint


def test_positive_extraction_is_deterministic():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    a = extract_pumpswap_hints(update)
    b = extract_pumpswap_hints(update)

    assert a.outcome == b.outcome
    assert a.base_mint == b.base_mint
    assert a.pool_account == b.pool_account
    assert a.quote_mint == b.quote_mint
    assert a.pool_program_id == b.pool_program_id
    assert (
        a.provider_pair_type_hint == b.provider_pair_type_hint
    )
    assert (
        a.provider_quote_asset_hint
        == b.provider_quote_asset_hint
    )
    assert a.no_evidence_reason == b.no_evidence_reason


# ---------------------------------------------------------------------------
# Negative cases — refuse to extract
# ---------------------------------------------------------------------------


def test_update_without_transaction_variant_no_evidence():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    # No transaction variant set.
    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION
    )
    assert result.base_mint is None
    assert result.pool_account is None
    assert result.quote_mint is None
    assert result.pool_program_id is None
    assert result.provider_pair_type_hint is None


def test_non_subscribe_update_input_refused():
    result = extract_pumpswap_hints(None)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION
    )

    result = extract_pumpswap_hints("not-a-protobuf")
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION
    )


def test_vote_transaction_skipped():
    update = _empty_subscribe_update_with_transaction()
    update.transaction.transaction.is_vote = True

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED
    )


def test_failed_transaction_per_meta_err_refused():
    update = _empty_subscribe_update_with_transaction()
    # Set meta.err to a default-shaped TransactionError so
    # HasField("err") becomes True.
    update.transaction.transaction.meta.err.SetInParent()
    # Even with a perfectly-shaped pool, the failed tx is
    # refused.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR
    )
    assert result.base_mint is None


def test_no_token_balances_at_all_refused():
    update = _empty_subscribe_update_with_transaction()
    # meta is present but no token balances added.
    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_TOKEN_BALANCES
    )


def test_non_spl_token_program_balances_refused():
    update = _empty_subscribe_update_with_transaction()
    # Construct entries whose program_id is a non-SPL-Token
    # program (e.g. the PumpSwap program id itself, or a random
    # other program id). The extractor must skip them all and
    # surface NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
        program_id=PUMPSWAP_PROGRAM_ID,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
        program_id=PUMPSWAP_PROGRAM_ID,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES
    )


def test_owner_with_only_wsol_no_base_refused():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE
    )


def test_user_with_only_base_no_pool_refused():
    """A user ATA holding ONLY a non-quote base mint, with no
    matched quote-side ATA, is not a pool. The extractor must
    not invent a quote-side hint."""
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_USER_OWNER,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE
    )
    assert result.quote_mint is None
    assert result.provider_pair_type_hint is None
    assert result.provider_quote_asset_hint is None


def test_ambiguous_multi_pool_refused():
    update = _empty_subscribe_update_with_transaction()
    # Two distinct owners each satisfy the heuristic — the
    # extractor must refuse to pick one.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=2,
        mint=USDC_MINT,
        owner=_TEST_POOL_OWNER_Y,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=3,
        mint=_TEST_BASE_MINT_B,
        owner=_TEST_POOL_OWNER_Y,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES
    )
    assert result.pool_owner_candidate_count == 2


def test_owner_with_multi_non_quote_mints_refused():
    update = _empty_subscribe_update_with_transaction()
    # One owner holds WSOL + TWO non-quote mints. The
    # heuristic refuses to pick which is the base.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=2,
        mint=_TEST_BASE_MINT_B,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS
    )
    assert result.base_mint is None


# ---------------------------------------------------------------------------
# Invention guards
# ---------------------------------------------------------------------------


def test_no_sol_invention_from_base_only():
    """A pool whose only non-quote mint is the test base mint
    must NOT have its quote slot silently promoted to WSOL.
    The extractor requires explicit WSOL evidence on the
    token-balance side."""
    update = _empty_subscribe_update_with_transaction()
    # Only a base mint balance, no WSOL anywhere.
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_USER_OWNER,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert result.quote_mint is None
    assert result.provider_quote_asset_hint is None
    assert result.provider_pair_type_hint is None


def test_no_usdc_invention_from_base_only():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=_TEST_BASE_MINT_B,
        owner=_TEST_USER_OWNER,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert result.quote_mint is None
    assert result.provider_quote_asset_hint is None
    assert result.provider_pair_type_hint is None


def test_unknown_quote_mint_does_not_classify_as_pump():
    """A pool-shaped owner whose quote-side mint is NOT one of
    the known quotes must NOT yield a PumpSwap classification.
    The extractor must refuse and never invent SOL/USDC."""
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=_TEST_UNKNOWN_QUOTE_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    # No fabrication: the owner held two non-quote-set mints
    # (from the extractor's point of view), so the
    # multi-non-quote refusal applies.
    assert result.no_evidence_reason in (
        NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS,
        NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
    )
    assert result.quote_mint is None
    assert result.provider_pair_type_hint is None
    assert result.provider_quote_asset_hint is None


# ---------------------------------------------------------------------------
# Empty / malformed TokenBalance entry handling
# ---------------------------------------------------------------------------


def test_empty_owner_field_silently_skipped():
    update = _empty_subscribe_update_with_transaction()
    # First entry has an empty owner -- silently skipped.
    pre = (
        update.transaction.transaction.meta
        .pre_token_balances.add()
    )
    pre.account_index = 0
    pre.mint = WRAPPED_SOL_MINT
    pre.owner = ""
    pre.program_id = SPL_TOKEN_PROGRAM_ID
    # Second entry is well-formed but on its own does not
    # satisfy the heuristic.
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    # Pool owner X only holds WSOL (no base mint co-owned).
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE
    )


def test_empty_mint_field_silently_skipped():
    update = _empty_subscribe_update_with_transaction()
    pre = (
        update.transaction.transaction.meta
        .pre_token_balances.add()
    )
    pre.account_index = 0
    pre.mint = ""
    pre.owner = _TEST_POOL_OWNER_X
    pre.program_id = SPL_TOKEN_PROGRAM_ID

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    # The empty-mint entry was the only TokenBalance and was
    # silently skipped; the spl_balance_count is 0 so the
    # extractor surfaces NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES.
    assert (
        result.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES
    )


# ---------------------------------------------------------------------------
# Stage 29.1 NEVER emits a bonding_curve_version_hint
# ---------------------------------------------------------------------------


def test_bonding_curve_version_hint_stays_none_on_positive():
    update = _empty_subscribe_update_with_transaction()
    _add_pre_post_balance_pair(
        update,
        account_index=0,
        mint=WRAPPED_SOL_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_pre_post_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    result = extract_pumpswap_hints(update)
    assert (
        result.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    assert result.bonding_curve_version_hint is None
