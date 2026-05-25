"""Stage 29.1 PumpSwap hint-aware decoder pins.

Pins:

  * On HINTS_EXTRACTED -> rebuilt payload has all hint slots
    populated and ``mint`` overridden from the Stage 28.11
    placeholder to the extracted base mint and
    ``instruction_kind`` set to ``PUMP_SWAP``.
  * On NO_EVIDENCE -> baseline Stage 28.11 payload returned
    verbatim (mint == placeholder, every hint slot None).
  * Stage 28.11 baseline decode errors propagate (e.g. vote
    transactions raise inside the baseline decoder; the
    hint-aware decoder must surface that error).
  * ``is_hint_bearing_payload`` correctly distinguishes
    rebuilt payloads from baseline payloads.
  * The rebuilt payload passes Stage 28.10 payload validation
    (``build_chainstack_yellowstone_payload`` accepts it).
"""

from __future__ import annotations

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    STAGE28_11_PLACEHOLDER_MINT,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11DecodeError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    INSTRUCTION_KIND_PUMP_SWAP,
    INSTRUCTION_KIND_UNKNOWN,
    Stage28_10ChainstackYellowstonePayload,
)
from PHX2.stage29.pumpswap_hint_aware_decoder import (
    decode_subscribe_update_with_pumpswap_hints,
    is_hint_bearing_payload,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_ID,
    USDC_MINT,
    WRAPPED_SOL_MINT,
)


_TEST_BASE_MINT_A: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_POOL_OWNER_X: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_PROVIDER_NAME: str = "chainstack_yellowstone_test"


def _add_token_balance_pair(
    update: object,
    *,
    account_index: int,
    mint: str,
    owner: str,
    program_id: str = SPL_TOKEN_PROGRAM_ID,
) -> None:
    meta = update.transaction.transaction.meta
    pre = meta.pre_token_balances.add()
    pre.account_index = account_index
    pre.mint = mint
    pre.owner = owner
    pre.program_id = program_id
    post = meta.post_token_balances.add()
    post.account_index = account_index
    post.mint = mint
    post.owner = owner
    post.program_id = program_id


def _build_tx_update(
    *,
    with_pool: bool,
    is_vote: bool = False,
) -> "_geyser_pb2.SubscribeUpdate":
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(range(1, 65))
    update.transaction.transaction.is_vote = is_vote
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000
    if with_pool:
        _add_token_balance_pair(
            update,
            account_index=0,
            mint=WRAPPED_SOL_MINT,
            owner=_TEST_POOL_OWNER_X,
        )
        _add_token_balance_pair(
            update,
            account_index=1,
            mint=_TEST_BASE_MINT_A,
            owner=_TEST_POOL_OWNER_X,
        )
    return update


# ---------------------------------------------------------------------------
# HINTS_EXTRACTED path: payload is rebuilt with hint slots populated.
# ---------------------------------------------------------------------------


def test_hints_extracted_overrides_mint_and_sets_instruction_kind():
    update = _build_tx_update(with_pool=True)
    payload, extraction = (
        decode_subscribe_update_with_pumpswap_hints(
            update, provider_name=_TEST_PROVIDER_NAME,
        )
    )
    assert isinstance(
        payload, Stage28_10ChainstackYellowstonePayload,
    )
    assert (
        extraction.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    # mint slot overridden away from placeholder.
    assert payload.mint == _TEST_BASE_MINT_A
    assert payload.mint != STAGE28_11_PLACEHOLDER_MINT
    # instruction_kind upgraded.
    assert payload.instruction_kind == INSTRUCTION_KIND_PUMP_SWAP
    # Hint quartet populated.
    assert payload.base_mint == _TEST_BASE_MINT_A
    assert payload.pool_account == _TEST_POOL_OWNER_X
    assert payload.quote_mint == WRAPPED_SOL_MINT
    assert payload.pool_program_id == PUMPSWAP_PROGRAM_ID
    # Provider hints populated.
    assert payload.provider_pair_type_hint == "PUMP_SOL"
    assert payload.provider_quote_asset_hint == "SOL"
    # Bonding-curve axis stays None (Stage 29.1 doesn't decode it).
    assert payload.bonding_curve_version_hint is None
    assert payload.provider_bonding_curve_version_hint is None


def test_hint_bearing_payload_predicate_positive():
    update = _build_tx_update(with_pool=True)
    payload, _ = decode_subscribe_update_with_pumpswap_hints(
        update, provider_name=_TEST_PROVIDER_NAME,
    )
    assert is_hint_bearing_payload(payload)


# ---------------------------------------------------------------------------
# NO_EVIDENCE path: baseline payload preserved verbatim.
# ---------------------------------------------------------------------------


def test_no_evidence_returns_baseline_payload_verbatim():
    update = _build_tx_update(with_pool=False)
    payload, extraction = (
        decode_subscribe_update_with_pumpswap_hints(
            update, provider_name=_TEST_PROVIDER_NAME,
        )
    )
    assert (
        extraction.outcome
        == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE
    )
    assert (
        extraction.no_evidence_reason
        == NO_EVIDENCE_REASON_NO_TOKEN_BALANCES
    )
    # Baseline payload preserved.
    assert payload.mint == STAGE28_11_PLACEHOLDER_MINT
    assert payload.instruction_kind == INSTRUCTION_KIND_UNKNOWN
    assert payload.base_mint is None
    assert payload.pool_account is None
    assert payload.quote_mint is None
    assert payload.pool_program_id is None
    assert payload.provider_pair_type_hint is None
    assert payload.provider_quote_asset_hint is None


def test_hint_bearing_payload_predicate_negative_on_baseline():
    update = _build_tx_update(with_pool=False)
    payload, _ = decode_subscribe_update_with_pumpswap_hints(
        update, provider_name=_TEST_PROVIDER_NAME,
    )
    assert not is_hint_bearing_payload(payload)


# ---------------------------------------------------------------------------
# Stage 28.11 baseline decode errors propagate verbatim.
# ---------------------------------------------------------------------------


def test_vote_transaction_raises_baseline_decode_error():
    update = _build_tx_update(with_pool=True, is_vote=True)
    with pytest.raises(Stage28_11DecodeError) as excinfo:
        decode_subscribe_update_with_pumpswap_hints(
            update, provider_name=_TEST_PROVIDER_NAME,
        )
    # Stage 28.11 baseline carries the closed-set reason.
    assert "TRANSACTION_IS_VOTE_SKIPPED" in str(excinfo.value)


def test_non_protobuf_update_raises_baseline_decode_error():
    with pytest.raises(Stage28_11DecodeError):
        decode_subscribe_update_with_pumpswap_hints(
            None, provider_name=_TEST_PROVIDER_NAME,
        )


# ---------------------------------------------------------------------------
# Hint bearing predicate edge cases.
# ---------------------------------------------------------------------------


def test_hint_bearing_payload_predicate_rejects_non_payload():
    assert not is_hint_bearing_payload(None)
    assert not is_hint_bearing_payload("not-a-payload")
    assert not is_hint_bearing_payload({})


def test_usdc_pool_extracted_correctly_through_decoder():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 200
    update.transaction.transaction.signature = bytes(range(1, 65))
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000
    _add_token_balance_pair(
        update,
        account_index=0,
        mint=USDC_MINT,
        owner=_TEST_POOL_OWNER_X,
    )
    _add_token_balance_pair(
        update,
        account_index=1,
        mint=_TEST_BASE_MINT_A,
        owner=_TEST_POOL_OWNER_X,
    )

    payload, extraction = (
        decode_subscribe_update_with_pumpswap_hints(
            update, provider_name=_TEST_PROVIDER_NAME,
        )
    )
    assert (
        extraction.outcome
        == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    )
    assert payload.quote_mint == USDC_MINT
    assert payload.provider_pair_type_hint == "PUMP_USDC"
    assert payload.provider_quote_asset_hint == "USDC"
    assert is_hint_bearing_payload(payload)
