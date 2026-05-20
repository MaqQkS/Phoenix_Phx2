"""Stage 24.3 Jito-tip decoder tests.

Pins:

  * ``decode_jito_tip`` emits a closed-set
    ``Stage24JitoTipResult`` for every supported case.
  * One top-level System Program transfer to a known Jito tip
    account decodes as ``DECODED`` / ``COMPLETE`` / ``HIGH`` /
    ``JITO_TIP`` with the exact lamport amount.
  * No System Program transfer to a known tip account ->
    ``ABSENT`` / ``MISSING`` (or ``NOT_APPLICABLE`` when there
    are no top-level instructions), ``amount_lamports`` is
    ``None`` (never coerced to 0).
  * A System Program transfer to a non-tip account is ignored
    and surfaced as evidence; it never headline-decodes.
  * A malformed Transfer body fails closed as ``DECODE_FAILED``
    / ``MALFORMED`` with the documented reason.
  * A non-Transfer System Program instruction (e.g.
    ``CreateAccount``, ``Assign``) does not fake a tip.
  * Multiple top-level tip transfers surface
    ``MULTIPLE_JITO_TIP_CANDIDATES`` and never silently sum.
  * Inner-CPI tip transfers are surfaced as
    ``JITO_TIP_INNER_CANDIDATE_PRESENT`` evidence but never
    headline-decode.
  * Failed transactions never claim a paid tip.
  * ``amount_lamports`` is ``None`` for every missing /
    unsupported / ambiguous case.
  * The locked Jito tip account tuple matches the eight standard
    Jito tip wallets.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

import pytest

from PHX2.stage24.constants import (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    CONFIDENCE_LEVELS,
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MALFORMED,
    DATA_STATUS_MISSING,
    DATA_STATUS_NOT_APPLICABLE,
    DATA_STATUS_PARTIAL,
    DATA_STATUSES,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODED,
    DECODER_STATUS_DECODE_FAILED,
    DECODER_STATUS_DECODE_UNCONFIRMED,
    DECODER_STATUS_NOT_APPLICABLE,
    DECODER_STATUS_PARTIAL,
    DECODER_STATUSES,
    DEFAULT_THRESHOLD_VERSION,
    FEE_SOURCE_JITO_TIP,
    FEE_SOURCE_JITO_TIP_CANDIDATE,
    FEE_SOURCE_UNKNOWN,
    FEE_SOURCES,
    INSTRUCTION_LOCATION_INNER,
    INSTRUCTION_LOCATION_TOP_LEVEL,
    INSTRUCTION_LOCATION_UNKNOWN,
    INSTRUCTION_LOCATIONS,
    KNOWN_JITO_TIP_ACCOUNTS,
    ROUTE_FAMILIES,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
    SYSTEM_PROGRAM_ID,
)
from PHX2.stage24.jito_tip import (
    DATA_ENCODING_BASE64,
    JITO_TIP_DECODER_NAME,
    JITO_TIP_DECODER_VERSION,
    REASON_JITO_TIP_ABSENT,
    REASON_JITO_TIP_ACCOUNTS_UNCONFIGURED,
    REASON_JITO_TIP_DECODED,
    REASON_JITO_TIP_INNER_CANDIDATE_PRESENT,
    REASON_JITO_TIP_MALFORMED_TRANSFER,
    REASON_JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS,
    REASON_JITO_TIP_TX_FAILED,
    REASON_MULTIPLE_JITO_TIP_CANDIDATES,
    REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED,
    SYSTEM_PROGRAM_TRANSFER_TAG,
    SYSTEM_PROGRAM_TRANSFER_TOTAL_BYTE_WIDTH,
    decode_jito_tip,
)
from PHX2.stage24.models import Stage24JitoTipResult, build_jito_tip_result
from PHX2.tests.stage24.fixtures.builders import (
    make_compute_budget_set_unit_limit_instruction,
    make_execution_input,
    make_inner_jito_tip_instruction,
    make_inner_non_tip_system_transfer_instruction,
    make_jito_tip_instruction,
    make_malformed_system_transfer_instruction,
    make_non_tip_system_transfer_instruction,
    make_system_program_non_transfer_instruction,
    make_system_transfer_instruction,
    make_system_transfer_instruction_data,
)


# ---------------------------------------------------------------------------
# Closed-set / shape invariants
# ---------------------------------------------------------------------------


def _assert_closed_set_result(result: Stage24JitoTipResult) -> None:
    assert result.primitive_family == "JITO_TIP"
    assert result.decoder_status in DECODER_STATUSES
    assert result.data_status in DATA_STATUSES
    assert result.confidence_level in CONFIDENCE_LEVELS
    assert result.fee_source in FEE_SOURCES
    assert result.route_family in ROUTE_FAMILIES
    assert result.instruction_location in INSTRUCTION_LOCATIONS
    assert result.decoder_name == JITO_TIP_DECODER_NAME
    assert result.decoder_version == JITO_TIP_DECODER_VERSION
    assert result.threshold_version == DEFAULT_THRESHOLD_VERSION


def _no_fake_zero(result: Stage24JitoTipResult) -> None:
    """A Stage 24 honesty axis: a missing tip is ``None``, never ``0``.

    If amount_lamports is 0, it must be paired with a DECODED
    status (a documented zero-amount transfer would be exotic but
    not forbidden). All non-DECODED cases must carry
    ``amount_lamports is None``.
    """
    if result.amount_lamports is not None:
        assert result.decoder_status == DECODER_STATUS_DECODED, (
            "non-None amount_lamports must come from a DECODED record; got "
            f"{result.decoder_status}"
        )


# ---------------------------------------------------------------------------
# Jito tip account list lockdown
# ---------------------------------------------------------------------------


def test_known_jito_tip_accounts_carries_eight_locked_pubkeys():
    assert KNOWN_JITO_TIP_ACCOUNTS == (
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
        "ADuUkR4vqLUMWXxW9gh6D6L8pivKeVrtfXEMnEnyGuTk",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
        "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    )


def test_known_jito_tip_accounts_has_no_duplicates():
    assert len(KNOWN_JITO_TIP_ACCOUNTS) == len(set(KNOWN_JITO_TIP_ACCOUNTS))


def test_known_jito_tip_accounts_is_a_tuple():
    assert isinstance(KNOWN_JITO_TIP_ACCOUNTS, tuple)


# ---------------------------------------------------------------------------
# Top-level happy path
# ---------------------------------------------------------------------------


def test_single_top_level_tip_transfer_decodes_to_high_confidence():
    tip_account = KNOWN_JITO_TIP_ACCOUNTS[0]
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=12_345, tip_account=tip_account
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_DECODED
    assert result.data_status == DATA_STATUS_COMPLETE
    assert result.confidence_level == CONFIDENCE_LEVEL_HIGH
    assert result.fee_source == FEE_SOURCE_JITO_TIP
    assert result.amount_lamports == 12_345
    assert result.tip_account == tip_account
    assert result.program_id == SYSTEM_PROGRAM_ID
    assert result.instruction_location == INSTRUCTION_LOCATION_TOP_LEVEL
    assert result.route_family == ROUTE_FAMILY_NO_ROUTER_DETECTED
    assert REASON_JITO_TIP_DECODED in result.reason_codes
    assert REASON_JITO_TIP_ABSENT not in result.reason_codes


def test_decoded_tip_records_destination_account_index():
    tip_account = KNOWN_JITO_TIP_ACCOUNTS[3]
    source = "SourceAccount11111111111111111111111111111"
    execution_input = make_execution_input(
        account_keys=(source, tip_account),
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=5_000, tip_account=tip_account, source=source
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.numeric_features["tip_destination_account_index"] == 1
    assert result.numeric_features["tip_source_account_index"] == 0


def test_decoded_tip_carries_data_encoding_evidence():
    tip_account = KNOWN_JITO_TIP_ACCOUNTS[2]
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=7_777, tip_account=tip_account
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.evidence["data_encoding"] == DATA_ENCODING_BASE64
    assert result.evidence["program_id"] == SYSTEM_PROGRAM_ID
    assert result.evidence["tip_account"] == tip_account


def test_each_locked_tip_account_decodes_individually():
    for tip in KNOWN_JITO_TIP_ACCOUNTS:
        execution_input = make_execution_input(
            top_level_instructions=(
                make_jito_tip_instruction(lamports=1_000, tip_account=tip),
            ),
        )
        result = decode_jito_tip(execution_input)
        assert result.decoder_status == DECODER_STATUS_DECODED, tip
        assert result.tip_account == tip
        assert result.amount_lamports == 1_000


# ---------------------------------------------------------------------------
# Absent / no-tip cases
# ---------------------------------------------------------------------------


def test_no_system_transfer_at_all_returns_absent_with_no_amount():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.data_status == DATA_STATUS_MISSING
    assert result.confidence_level == CONFIDENCE_LEVEL_NONE
    assert result.fee_source == FEE_SOURCE_UNKNOWN
    assert result.amount_lamports is None
    assert result.tip_account == ""
    assert REASON_JITO_TIP_ABSENT in result.reason_codes


def test_empty_top_level_instructions_returns_absent_not_applicable():
    execution_input = make_execution_input(top_level_instructions=())
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.data_status == DATA_STATUS_NOT_APPLICABLE
    assert result.amount_lamports is None
    assert REASON_JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS in result.reason_codes


def test_system_transfer_to_non_tip_account_is_ignored_for_headline():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_non_tip_system_transfer_instruction(
                lamports=500,
                destination="DefinitelyNotATipAccount11111111111111111",
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None
    assert result.tip_account == ""
    assert (
        REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED in result.reason_codes
    )
    assert REASON_JITO_TIP_ABSENT in result.reason_codes


def test_non_transfer_system_program_instruction_does_not_fake_a_tip():
    # Tag=0 (CreateAccount) is a System Program instruction but is
    # NOT a Transfer. The decoder must ignore it cleanly.
    execution_input = make_execution_input(
        top_level_instructions=(
            make_system_program_non_transfer_instruction(tag=0, body=b""),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None
    assert REASON_JITO_TIP_MALFORMED_TRANSFER not in result.reason_codes


def test_unknown_system_program_tag_does_not_fake_a_tip():
    # Tag value outside the documented System Program tag set. The
    # decoder must NOT promote it to a DECODE_FAILED Transfer.
    execution_input = make_execution_input(
        top_level_instructions=(
            make_system_program_non_transfer_instruction(
                tag=99, body=b"\x00" * 8
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None


# ---------------------------------------------------------------------------
# Malformed cases
# ---------------------------------------------------------------------------


def test_malformed_transfer_body_fails_closed():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_malformed_system_transfer_instruction(),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_DECODE_FAILED
    assert result.data_status == DATA_STATUS_MALFORMED
    assert result.confidence_level == CONFIDENCE_LEVEL_NONE
    assert result.amount_lamports is None
    assert result.tip_account == ""
    assert REASON_JITO_TIP_MALFORMED_TRANSFER in result.reason_codes
    assert result.numeric_features[
        "malformed_transfer_instruction_count"
    ] == 1


def test_invalid_base64_data_is_ignored_as_non_transfer():
    # Non-base64 data on a System Program instruction is treated
    # as "not a Transfer" rather than "malformed Transfer". The
    # decoder must not claim a tip.
    execution_input = make_execution_input(
        top_level_instructions=(
            {
                "program_id": SYSTEM_PROGRAM_ID,
                "accounts": [
                    "SourceAccount11111111111111111111111111111",
                    KNOWN_JITO_TIP_ACCOUNTS[0],
                ],
                "data": "@@@",
            },
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None


# ---------------------------------------------------------------------------
# Multiple tip candidates
# ---------------------------------------------------------------------------


def test_multiple_top_level_tip_candidates_surfaces_ambiguity():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=10_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
            make_jito_tip_instruction(
                lamports=20_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[1]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_DECODE_UNCONFIRMED
    assert result.data_status == DATA_STATUS_PARTIAL
    assert result.confidence_level == CONFIDENCE_LEVEL_LOW
    assert result.fee_source == FEE_SOURCE_JITO_TIP_CANDIDATE
    assert result.amount_lamports is None
    assert result.tip_account == ""
    assert REASON_MULTIPLE_JITO_TIP_CANDIDATES in result.reason_codes
    assert REASON_JITO_TIP_DECODED not in result.reason_codes
    assert result.numeric_features[
        "top_level_jito_tip_candidate_count"
    ] == 2


def test_multiple_tip_candidates_records_per_candidate_evidence():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=10_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
            make_jito_tip_instruction(
                lamports=20_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[1]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    candidate_lamports = result.evidence["candidate_lamports_per_index"]
    assert isinstance(candidate_lamports, list)
    assert [0, 10_000] in candidate_lamports
    assert [1, 20_000] in candidate_lamports
    assert result.numeric_features["jito_tip_candidate_lamports_min"] == (
        10_000
    )
    assert result.numeric_features["jito_tip_candidate_lamports_max"] == (
        20_000
    )


def test_multiple_tip_candidates_do_not_sum_silently():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=10_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
            make_jito_tip_instruction(
                lamports=20_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.amount_lamports is None
    assert result.amount_lamports != 30_000


# ---------------------------------------------------------------------------
# Inner tip candidate evidence-only behavior
# ---------------------------------------------------------------------------


def test_inner_tip_candidate_only_does_not_headline_decode():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
        ),
        inner_instructions=(
            make_inner_jito_tip_instruction(
                lamports=4_321,
                tip_account=KNOWN_JITO_TIP_ACCOUNTS[2],
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None
    assert result.tip_account == ""
    assert (
        REASON_JITO_TIP_INNER_CANDIDATE_PRESENT in result.reason_codes
    )
    assert REASON_JITO_TIP_DECODED not in result.reason_codes
    assert result.instruction_location == INSTRUCTION_LOCATION_INNER
    assert result.fee_source == FEE_SOURCE_JITO_TIP_CANDIDATE
    assert result.numeric_features["inner_jito_tip_candidate_count"] == 1
    assert (
        result.numeric_features["top_level_jito_tip_candidate_count"] == 0
    )


def test_inner_non_tip_transfer_does_not_flag_inner_candidate():
    execution_input = make_execution_input(
        inner_instructions=(
            make_inner_non_tip_system_transfer_instruction(
                lamports=500,
                destination="InnerStranger1111111111111111111111111111",
            ),
        ),
        top_level_instructions=(),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert (
        REASON_JITO_TIP_INNER_CANDIDATE_PRESENT not in result.reason_codes
    )


def test_top_level_tip_with_inner_candidate_still_decodes_top_level():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=11_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
        inner_instructions=(
            make_inner_jito_tip_instruction(
                lamports=999, tip_account=KNOWN_JITO_TIP_ACCOUNTS[1]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODED
    assert result.amount_lamports == 11_000
    # Both the decoded reason and the inner-candidate reason are
    # recorded, but the headline amount comes from the top-level
    # tip.
    assert REASON_JITO_TIP_DECODED in result.reason_codes
    assert (
        REASON_JITO_TIP_INNER_CANDIDATE_PRESENT in result.reason_codes
    )


# ---------------------------------------------------------------------------
# Failed transaction behavior
# ---------------------------------------------------------------------------


def test_failed_tx_with_tip_candidate_returns_partial_with_no_amount():
    execution_input = make_execution_input(
        transaction_status="err",
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=8_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_PARTIAL
    assert result.data_status == DATA_STATUS_PARTIAL
    assert result.confidence_level == CONFIDENCE_LEVEL_LOW
    assert result.fee_source == FEE_SOURCE_JITO_TIP_CANDIDATE
    assert result.amount_lamports is None
    assert REASON_JITO_TIP_TX_FAILED in result.reason_codes
    assert REASON_JITO_TIP_DECODED not in result.reason_codes


def test_failed_tx_with_no_tip_candidate_returns_not_applicable():
    execution_input = make_execution_input(
        transaction_status="err",
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_NOT_APPLICABLE
    assert result.data_status == DATA_STATUS_NOT_APPLICABLE
    assert result.confidence_level == CONFIDENCE_LEVEL_NONE
    assert result.fee_source == FEE_SOURCE_UNKNOWN
    assert result.amount_lamports is None
    assert REASON_JITO_TIP_TX_FAILED in result.reason_codes


def test_failed_tx_status_token_normalized_case_insensitively():
    execution_input = make_execution_input(
        transaction_status="ERR",
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=8_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_PARTIAL
    assert result.amount_lamports is None


def test_success_status_does_not_trigger_failed_tx_path():
    execution_input = make_execution_input(
        transaction_status="success",
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=4_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODED
    assert REASON_JITO_TIP_TX_FAILED not in result.reason_codes


# ---------------------------------------------------------------------------
# Numeric feature / evidence invariants
# ---------------------------------------------------------------------------


def test_decoder_result_numeric_features_carry_required_keys():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=2_000, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    nf = result.numeric_features
    for required in (
        "jito_tip_lamports",
        "jito_tip_candidate_count",
        "top_level_jito_tip_candidate_count",
        "inner_jito_tip_candidate_count",
        "system_transfer_instruction_count",
        "tip_destination_account_index",
        "tip_source_account_index",
    ):
        assert required in nf, required


def test_decoder_result_evidence_has_program_id_and_data_encoding():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.evidence["program_id"] == SYSTEM_PROGRAM_ID
    assert result.evidence["data_encoding"] == DATA_ENCODING_BASE64


def test_decoder_result_is_immutable_namedtuple():
    result = decode_jito_tip(make_execution_input())
    with pytest.raises(AttributeError):
        result.amount_lamports = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# No-fake-zero invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "execution_input_factory",
    [
        lambda: make_execution_input(top_level_instructions=()),
        lambda: make_execution_input(
            top_level_instructions=(
                make_compute_budget_set_unit_limit_instruction(units=1),
            )
        ),
        lambda: make_execution_input(
            top_level_instructions=(
                make_non_tip_system_transfer_instruction(lamports=1),
            )
        ),
        lambda: make_execution_input(
            top_level_instructions=(
                make_malformed_system_transfer_instruction(),
            )
        ),
        lambda: make_execution_input(
            top_level_instructions=(
                make_jito_tip_instruction(
                    lamports=10, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
                ),
                make_jito_tip_instruction(
                    lamports=20, tip_account=KNOWN_JITO_TIP_ACCOUNTS[1]
                ),
            )
        ),
        lambda: make_execution_input(
            transaction_status="err",
            top_level_instructions=(
                make_jito_tip_instruction(
                    lamports=10, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
                ),
            ),
        ),
    ],
)
def test_amount_lamports_is_none_for_missing_or_unsupported_cases(
    execution_input_factory,
):
    result = decode_jito_tip(execution_input_factory())
    _assert_closed_set_result(result)
    _no_fake_zero(result)
    assert result.amount_lamports is None


# ---------------------------------------------------------------------------
# Account index resolution
# ---------------------------------------------------------------------------


def test_decoder_resolves_int_account_index_into_account_keys():
    tip_account = KNOWN_JITO_TIP_ACCOUNTS[4]
    account_keys = (
        "AccountA111111111111111111111111111111111",
        tip_account,
        "AccountC111111111111111111111111111111111",
    )
    execution_input = make_execution_input(
        account_keys=account_keys,
        top_level_instructions=(
            {
                "program_id": SYSTEM_PROGRAM_ID,
                "accounts": [0, 1],
                "data": make_system_transfer_instruction_data(
                    lamports=2_222
                ),
            },
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODED
    assert result.tip_account == tip_account
    assert result.amount_lamports == 2_222
    assert result.numeric_features["tip_destination_account_index"] == 1
    assert result.numeric_features["tip_source_account_index"] == 0


def test_decoder_handles_missing_destination_account_gracefully():
    # Only one account in the accounts list -> no destination at
    # position 1 -> decoder cannot resolve -> ABSENT (not a fake
    # decode).
    execution_input = make_execution_input(
        top_level_instructions=(
            {
                "program_id": SYSTEM_PROGRAM_ID,
                "accounts": [
                    "OnlySourceAccount11111111111111111111111111",
                ],
                "data": make_system_transfer_instruction_data(
                    lamports=3_333
                ),
            },
        ),
    )
    result = decode_jito_tip(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.amount_lamports is None
    assert result.tip_account == ""


# ---------------------------------------------------------------------------
# Deterministic reason ordering
# ---------------------------------------------------------------------------


def test_decoded_reason_appears_first_in_reason_codes():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_non_tip_system_transfer_instruction(lamports=900),
            make_jito_tip_instruction(
                lamports=5_555, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODED
    assert result.reason_codes[0] == REASON_JITO_TIP_DECODED


def test_absent_reason_appears_first_for_absent_path():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_non_tip_system_transfer_instruction(lamports=900),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_ABSENT
    assert result.reason_codes[0] == REASON_JITO_TIP_ABSENT


def test_malformed_reason_appears_first_for_malformed_path():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_malformed_system_transfer_instruction(),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODE_FAILED
    assert result.reason_codes[0] == REASON_JITO_TIP_MALFORMED_TRANSFER


def test_multiple_candidate_reason_appears_first_for_ambiguous_path():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=10, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
            make_jito_tip_instruction(
                lamports=20, tip_account=KNOWN_JITO_TIP_ACCOUNTS[1]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.decoder_status == DECODER_STATUS_DECODE_UNCONFIRMED
    assert result.reason_codes[0] == REASON_MULTIPLE_JITO_TIP_CANDIDATES


def test_failed_tx_reason_appears_first_for_failed_path():
    execution_input = make_execution_input(
        transaction_status="err",
        top_level_instructions=(
            make_jito_tip_instruction(
                lamports=10, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
            ),
        ),
    )
    result = decode_jito_tip(execution_input)
    assert result.reason_codes[0] == REASON_JITO_TIP_TX_FAILED


# ---------------------------------------------------------------------------
# Builder closed-set guard
# ---------------------------------------------------------------------------


def test_build_jito_tip_result_rejects_invalid_decoder_status():
    with pytest.raises(Exception):
        build_jito_tip_result(
            decoder_name=JITO_TIP_DECODER_NAME,
            decoder_version=JITO_TIP_DECODER_VERSION,
            threshold_version=DEFAULT_THRESHOLD_VERSION,
            decoder_status="BOGUS_STATUS",
            data_status=DATA_STATUS_COMPLETE,
            confidence_level=CONFIDENCE_LEVEL_HIGH,
            fee_source=FEE_SOURCE_JITO_TIP,
            route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
            instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
            program_id=SYSTEM_PROGRAM_ID,
            tip_account=KNOWN_JITO_TIP_ACCOUNTS[0],
            amount_lamports=1_000,
            reason_codes=(REASON_JITO_TIP_DECODED,),
            numeric_features=MappingProxyType({}),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


def test_build_jito_tip_result_rejects_router_fee_candidate_status():
    with pytest.raises(Exception):
        build_jito_tip_result(
            decoder_name=JITO_TIP_DECODER_NAME,
            decoder_version=JITO_TIP_DECODER_VERSION,
            threshold_version=DEFAULT_THRESHOLD_VERSION,
            decoder_status="ROUTER_FEE_CANDIDATE",
            data_status=DATA_STATUS_COMPLETE,
            confidence_level=CONFIDENCE_LEVEL_HIGH,
            fee_source=FEE_SOURCE_JITO_TIP,
            route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
            instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
            program_id=SYSTEM_PROGRAM_ID,
            tip_account=KNOWN_JITO_TIP_ACCOUNTS[0],
            amount_lamports=1_000,
            reason_codes=(REASON_JITO_TIP_DECODED,),
            numeric_features=MappingProxyType({}),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


# ---------------------------------------------------------------------------
# System Program Transfer layout sanity
# ---------------------------------------------------------------------------


def test_system_program_transfer_layout_constants_are_locked():
    assert SYSTEM_PROGRAM_TRANSFER_TAG == 2
    assert SYSTEM_PROGRAM_TRANSFER_TOTAL_BYTE_WIDTH == 12


def test_fixture_builder_produces_expected_byte_layout():
    data = make_system_transfer_instruction_data(lamports=1_234_567)
    import base64

    raw = base64.b64decode(data)
    assert len(raw) == SYSTEM_PROGRAM_TRANSFER_TOTAL_BYTE_WIDTH
    tag = int.from_bytes(raw[:4], "little")
    lamports = int.from_bytes(raw[4:12], "little")
    assert tag == SYSTEM_PROGRAM_TRANSFER_TAG
    assert lamports == 1_234_567


def test_decoder_result_returns_namedtuple_with_jito_tip_family():
    result = decode_jito_tip(make_execution_input())
    assert isinstance(result, Stage24JitoTipResult)
    assert result.primitive_family == "JITO_TIP"


# ---------------------------------------------------------------------------
# Numeric / evidence type guarantees
# ---------------------------------------------------------------------------


def test_numeric_features_and_evidence_are_mappings():
    result = decode_jito_tip(
        make_execution_input(
            top_level_instructions=(
                make_jito_tip_instruction(
                    lamports=42, tip_account=KNOWN_JITO_TIP_ACCOUNTS[0]
                ),
            ),
        )
    )
    assert isinstance(result.numeric_features, Mapping)
    assert isinstance(result.evidence, Mapping)


def test_reason_codes_is_tuple_of_strings():
    result = decode_jito_tip(make_execution_input())
    assert isinstance(result.reason_codes, tuple)
    for code in result.reason_codes:
        assert isinstance(code, str)
        assert code != ""
