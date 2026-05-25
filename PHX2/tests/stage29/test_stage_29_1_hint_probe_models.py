"""Stage 29.1 hint-probe models pins.

Pins:

  * Closed-set probe-mode / probe-status / refusal-reason
    vocabularies have the exact membership the runbook
    promises.
  * Each ``is_*_value`` predicate accepts every token in its
    closed set and rejects out-of-set values.
  * ``Stage29_1HintProbeError`` carries a closed-set reason.
  * ``Stage29_1HintProbeResult`` is a frozen dataclass; direct
    construction runs the field-validator in ``__post_init__``.
  * Internal-consistency rules (DECODED_WITH_HINTS requires
    payload + extraction + refusal=NONE; NO_HINT_EVIDENCE
    requires payload=None + refusal!=NONE; FAILED/SKIPPED
    require payload=None + refusal!=NONE).
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstonePayload,
    build_chainstack_yellowstone_payload,
    CHAIN_SOLANA,
    EVENT_TYPE_SWAP,
    INSTRUCTION_KIND_UNKNOWN,
    SOURCE_KIND_FAKE,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
    POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
    QUOTE_MINT_EVIDENCE_SOURCE_NONE,
    Stage29_1PumpSwapHintExtractionResult,
)
from PHX2.stage29.stage29_1_hint_probe_models import (
    PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
    PROBE_MODE_VALUES,
    PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
    PROBE_STATUS_DECODED_WITH_HINTS,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_SKIPPED,
    PROBE_STATUS_VALUES,
    REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED,
    REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
    REFUSAL_REASON_STREAM_ERROR,
    REFUSAL_REASON_SUBSCRIBE_FAILED,
    REFUSAL_REASON_VALUES,
    Stage29_1HintProbeError,
    Stage29_1HintProbeResult,
    build_hint_probe_result,
    is_probe_mode_value,
    is_probe_status_value,
    is_refusal_reason_value,
)


# ---------------------------------------------------------------------------
# Closed-set memberships
# ---------------------------------------------------------------------------


def test_probe_mode_closed_set():
    assert PROBE_MODE_VALUES == (
        PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
    )


def test_probe_status_closed_set():
    assert PROBE_STATUS_VALUES == (
        PROBE_STATUS_DECODED_WITH_HINTS,
        PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
        PROBE_STATUS_FAILED,
        PROBE_STATUS_SKIPPED,
    )


def test_refusal_reason_closed_set():
    assert REFUSAL_REASON_VALUES == (
        REFUSAL_REASON_NONE,
        REFUSAL_REASON_MODE_INVALID,
        REFUSAL_REASON_LIVE_FLAG_NOT_SET,
        REFUSAL_REASON_CONNECT_FAILED,
        REFUSAL_REASON_SUBSCRIBE_FAILED,
        REFUSAL_REASON_STREAM_ERROR,
        REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
        (
            REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
        ),
        REFUSAL_REASON_DECODE_FAILED,
        REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
        REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    )


# ---------------------------------------------------------------------------
# Predicate behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", PROBE_MODE_VALUES)
def test_is_probe_mode_value_accepts_each(value):
    assert is_probe_mode_value(value)


def test_is_probe_mode_value_rejects_outside():
    for bad in ("", "OTHER", None, 1, b"X"):
        assert not is_probe_mode_value(bad)


@pytest.mark.parametrize("value", PROBE_STATUS_VALUES)
def test_is_probe_status_value_accepts_each(value):
    assert is_probe_status_value(value)


def test_is_probe_status_value_rejects_outside():
    for bad in ("", "OTHER", None, 1):
        assert not is_probe_status_value(bad)


@pytest.mark.parametrize("value", REFUSAL_REASON_VALUES)
def test_is_refusal_reason_value_accepts_each(value):
    assert is_refusal_reason_value(value)


def test_is_refusal_reason_value_rejects_outside():
    for bad in ("", "OTHER", None, 1):
        assert not is_refusal_reason_value(bad)


# ---------------------------------------------------------------------------
# Exception carries closed-set reason
# ---------------------------------------------------------------------------


def test_probe_error_carries_reason_and_str():
    err = Stage29_1HintProbeError("EXAMPLE")
    assert err.reason == "EXAMPLE"
    assert "EXAMPLE" in str(err)
    assert "Stage 29.1 hint-probe error" in str(err)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload() -> Stage28_10ChainstackYellowstonePayload:
    return build_chainstack_yellowstone_payload(
        provider_event_id="yellowstone_test_event_1",
        provider_name="chainstack_yellowstone_test",
        source_kind=SOURCE_KIND_FAKE,
        mint="TestBaseMintAAAA1111111111111111111111111A",
        event_type=EVENT_TYPE_SWAP,
        observed_at_utc="2026-05-24T12:00:00+00:00",
        slot=100,
        signature=(
            "TestSignatureAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1"
        ),
        instruction_kind=INSTRUCTION_KIND_UNKNOWN,
        decoded_fields={},
        chain=CHAIN_SOLANA,
        quote_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        pool_account=(
            "TestPoolXXXXXXX3333333333333333333333333X"
        ),
        pool_program_id=(
            "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        ),
        base_mint="TestBaseMintAAAA1111111111111111111111111A",
        bonding_curve_version_hint=None,
        provider_quote_asset_hint="SOL",
        provider_pair_type_hint="PUMP_SOL",
        provider_bonding_curve_version_hint=None,
    )


def _make_no_evidence_extraction() -> (
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


# ---------------------------------------------------------------------------
# Result-record construction + invariants
# ---------------------------------------------------------------------------


def test_decoded_with_hints_result_constructible():
    payload = _make_payload()
    extraction = Stage29_1PumpSwapHintExtractionResult(
        outcome=(
            "HINTS_EXTRACTED"
        ),
        base_mint="TestBaseMintAAAA1111111111111111111111111A",
        pool_account=(
            "TestPoolXXXXXXX3333333333333333333333333X"
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
        no_evidence_reason="NONE",
        pool_account_evidence_source=(
            "TOKEN_BALANCE_OWNER_GROUPING"
        ),
        quote_mint_evidence_source=(
            "POOL_OWNER_TOKEN_BALANCE"
        ),
        spl_token_balance_count=2,
        pool_owner_candidate_count=1,
    )
    record = build_hint_probe_result(
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        status=PROBE_STATUS_DECODED_WITH_HINTS,
        refusal_reason=REFUSAL_REASON_NONE,
        hint_bearing_payload=payload,
        extraction_result=extraction,
        events_scanned=5,
        transactions_scanned=2,
        handoff_ready=True,
    )
    assert record.status == PROBE_STATUS_DECODED_WITH_HINTS
    assert record.refusal_reason == REFUSAL_REASON_NONE
    assert record.handoff_ready is True


def test_decoded_with_hints_without_payload_rejected():
    with pytest.raises(Stage29_1HintProbeError):
        build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_DECODED_WITH_HINTS,
            refusal_reason=REFUSAL_REASON_NONE,
            hint_bearing_payload=None,
            extraction_result=None,
            events_scanned=1,
            transactions_scanned=1,
            handoff_ready=True,
        )


def test_decoded_no_hint_evidence_with_payload_rejected():
    payload = _make_payload()
    with pytest.raises(Stage29_1HintProbeError):
        build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
            refusal_reason=(
                REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
            ),
            hint_bearing_payload=payload,
        )


def test_failed_with_refusal_none_rejected():
    with pytest.raises(Stage29_1HintProbeError):
        build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_NONE,
        )


def test_skipped_with_payload_rejected():
    payload = _make_payload()
    with pytest.raises(Stage29_1HintProbeError):
        build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_LIVE_FLAG_NOT_SET,
            hint_bearing_payload=payload,
        )


def test_no_hint_evidence_result_constructible_without_extraction():
    record = build_hint_probe_result(
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        status=PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
        refusal_reason=REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
        events_scanned=64,
        transactions_scanned=0,
    )
    assert (
        record.refusal_reason
        == REFUSAL_REASON_NO_TRANSACTION_RECEIVED
    )
    assert record.hint_bearing_payload is None


def test_no_hint_evidence_result_with_extraction():
    extraction = _make_no_evidence_extraction()
    record = build_hint_probe_result(
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        status=PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
        refusal_reason=(
            REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
        ),
        extraction_result=extraction,
        events_scanned=5,
        transactions_scanned=3,
    )
    assert record.extraction_result is extraction


def test_skipped_with_live_flag_not_set_constructible():
    record = build_hint_probe_result(
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        status=PROBE_STATUS_SKIPPED,
        refusal_reason=REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    )
    assert record.status == PROBE_STATUS_SKIPPED


def test_probe_result_is_frozen():
    record = build_hint_probe_result(
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        status=PROBE_STATUS_SKIPPED,
        refusal_reason=REFUSAL_REASON_MODE_INVALID,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.status = "MUTATED"  # type: ignore[misc]


def test_negative_events_scanned_rejected():
    with pytest.raises(Stage29_1HintProbeError):
        build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
            events_scanned=-1,
        )


def test_handoff_ready_not_bool_rejected():
    with pytest.raises(Stage29_1HintProbeError):
        Stage29_1HintProbeResult(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
            hint_bearing_payload=None,
            extraction_result=None,
            events_scanned=0,
            transactions_scanned=0,
            handoff_ready="True",  # type: ignore[arg-type]
        )


def test_payload_wrong_type_rejected():
    with pytest.raises(Stage29_1HintProbeError):
        Stage29_1HintProbeResult(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_DECODED_WITH_HINTS,
            refusal_reason=REFUSAL_REASON_NONE,
            hint_bearing_payload="not-a-payload",  # type: ignore[arg-type]
            extraction_result=_make_no_evidence_extraction(),
            events_scanned=1,
            transactions_scanned=1,
            handoff_ready=True,
        )
