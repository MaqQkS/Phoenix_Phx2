"""Stage 24.2 ComputeBudget decoder tests.

Pins:

  * ``decode_compute_budget`` emits a closed-set
    ``Stage24ComputeBudgetResult`` for every supported case.
  * No ComputeBudget instruction -> ``ABSENT`` /
    ``MISSING`` / ``unit_limit`` and ``unit_price_microlamports``
    are ``None`` (never coerced to 0).
  * ``SetComputeUnitLimit`` and ``SetComputeUnitPrice`` are
    decoded against the little-endian byte layout, with the
    expected reason codes added.
  * ``RequestHeapFrame`` and the legacy
    ``RequestUnitsDeprecated`` decode without changing the
    priority-fee surface and are labeled with the right reason
    codes.
  * An unknown tag or malformed body fails closed as
    ``DECODE_FAILED`` / ``MALFORMED``.
  * Multiple ``SetComputeUnitLimit`` -> last-write-wins with the
    documented reason code.
  * Multiple ``SetComputeUnitPrice`` -> ``DECODE_UNCONFIRMED`` /
    ``PARTIAL`` / price ``None``, with the documented reason
    code; every observed price is surfaced in evidence.
  * Non-ComputeBudget instructions are ignored.
  * Inner-CPI ComputeBudget instructions are NOT decoded but
    are surfaced as ignored evidence (``inner_..._count`` +
    reason code).
  * The ``Stage24ComputeBudgetResult`` record never carries an
    ``amount_lamports`` field (priority-fee axis lives on the
    priority-fee result, not the compute-budget result).
"""

from __future__ import annotations

from types import MappingProxyType

from PHX2.stage24.compute_budget import (
    COMPUTE_BUDGET_DECODER_NAME,
    COMPUTE_BUDGET_DECODER_VERSION,
    DATA_ENCODING_BASE64,
    REASON_COMPUTE_BUDGET_ABSENT,
    REASON_COMPUTE_BUDGET_DECODED,
    REASON_COMPUTE_BUDGET_HEAP_FRAME_DECODED,
    REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT,
    REASON_COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED,
    REASON_COMPUTE_BUDGET_MALFORMED_DATA,
    REASON_COMPUTE_BUDGET_UNKNOWN_TAG,
    REASON_COMPUTE_UNIT_LIMIT_DECODED,
    REASON_COMPUTE_UNIT_PRICE_DECODED,
    REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS,
    REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS,
    TAG_REQUEST_HEAP_FRAME,
    TAG_REQUEST_UNITS_DEPRECATED,
    TAG_SET_COMPUTE_UNIT_LIMIT,
    TAG_SET_COMPUTE_UNIT_PRICE,
    decode_compute_budget,
)
from PHX2.stage24.constants import (
    COMPUTE_BUDGET_PROGRAM_ID,
    CONFIDENCE_LEVELS,
    DATA_STATUSES,
    DECODER_STATUSES,
    DEFAULT_THRESHOLD_VERSION,
    FEE_SOURCES,
    INSTRUCTION_LOCATIONS,
    ROUTE_FAMILIES,
)
from PHX2.stage24.models import Stage24ComputeBudgetResult
from PHX2.tests.stage24.fixtures.builders import (
    encode_compute_budget_empty_data,
    encode_compute_budget_malformed_short_body_data,
    encode_compute_budget_set_unit_limit_data,
    encode_compute_budget_unknown_tag_data,
    make_compute_budget_request_heap_frame_instruction,
    make_compute_budget_request_units_deprecated_instruction,
    make_compute_budget_set_unit_limit_instruction,
    make_compute_budget_set_unit_price_instruction,
    make_execution_input,
    make_inner_instruction,
    make_non_compute_budget_instruction,
    make_top_level_instruction,
)


# ---------------------------------------------------------------------------
# Closed-set / shape invariants
# ---------------------------------------------------------------------------


def _assert_closed_set_result(result: Stage24ComputeBudgetResult) -> None:
    assert result.primitive_family == "COMPUTE_BUDGET"
    assert result.decoder_status in DECODER_STATUSES
    assert result.data_status in DATA_STATUSES
    assert result.confidence_level in CONFIDENCE_LEVELS
    assert result.fee_source in FEE_SOURCES
    assert result.route_family in ROUTE_FAMILIES
    assert result.instruction_location in INSTRUCTION_LOCATIONS
    assert result.decoder_name == COMPUTE_BUDGET_DECODER_NAME
    assert result.decoder_version == COMPUTE_BUDGET_DECODER_VERSION
    assert result.threshold_version == DEFAULT_THRESHOLD_VERSION
    assert isinstance(result.result_hash, str) and result.result_hash != ""


def test_compute_budget_result_has_no_amount_lamports_field():
    """``amount_lamports`` is a priority-fee axis; the compute-budget
    result does NOT expose it. The Stage 24 priority-fee result is
    the place to surface the lamport amount.
    """
    assert "amount_lamports" not in Stage24ComputeBudgetResult._fields


# ---------------------------------------------------------------------------
# ABSENT
# ---------------------------------------------------------------------------


def test_decode_absent_when_no_compute_budget_instructions():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(make_non_compute_budget_instruction()),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "ABSENT"
    assert result.data_status == "MISSING"
    assert result.confidence_level == "NONE"
    assert result.fee_source == "UNKNOWN"
    assert result.route_family == "NO_ROUTER_DETECTED"
    assert result.instruction_location == "UNKNOWN"
    assert result.program_id == ""
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None
    assert REASON_COMPUTE_BUDGET_ABSENT in result.reason_codes


def test_decode_absent_when_top_level_instructions_empty():
    execution_input = make_execution_input(top_level_instructions=())
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "ABSENT"
    assert REASON_COMPUTE_BUDGET_ABSENT in result.reason_codes
    assert result.numeric_features["compute_budget_instruction_count"] == 0


# ---------------------------------------------------------------------------
# Single-tag decoded paths
# ---------------------------------------------------------------------------


def test_decode_set_compute_unit_limit_only():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=200_000)
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.data_status == "COMPLETE"
    assert result.confidence_level == "HIGH"
    assert result.fee_source == "UNKNOWN"
    assert result.instruction_location == "TOP_LEVEL"
    assert result.program_id == COMPUTE_BUDGET_PROGRAM_ID
    assert result.unit_limit == 200_000
    assert result.unit_price_microlamports is None
    assert REASON_COMPUTE_UNIT_LIMIT_DECODED in result.reason_codes
    assert REASON_COMPUTE_UNIT_PRICE_DECODED not in result.reason_codes
    assert result.numeric_features["compute_unit_limit"] == 200_000
    assert result.numeric_features["compute_unit_limit_instruction_count"] == 1
    assert result.numeric_features["compute_unit_price_instruction_count"] == 0
    assert (
        result.evidence["data_encoding"] == DATA_ENCODING_BASE64
    )
    assert TAG_SET_COMPUTE_UNIT_LIMIT in result.evidence["tags_seen"]


def test_decode_set_compute_unit_price_only():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=7_500,
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.confidence_level == "HIGH"
    assert result.fee_source == "PRIORITY_FEE"
    assert result.unit_limit is None
    assert result.unit_price_microlamports == 7_500
    assert REASON_COMPUTE_UNIT_PRICE_DECODED in result.reason_codes
    assert REASON_COMPUTE_UNIT_LIMIT_DECODED not in result.reason_codes
    assert (
        result.numeric_features["micro_lamports_per_compute_unit"]
        == 7_500
    )
    assert result.numeric_features["compute_unit_price_instruction_count"] == 1


def test_decode_both_limit_and_price():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=300_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=12_345,
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.fee_source == "PRIORITY_FEE"
    assert result.unit_limit == 300_000
    assert result.unit_price_microlamports == 12_345
    assert REASON_COMPUTE_BUDGET_DECODED in result.reason_codes
    assert REASON_COMPUTE_UNIT_LIMIT_DECODED in result.reason_codes
    assert REASON_COMPUTE_UNIT_PRICE_DECODED in result.reason_codes
    assert result.numeric_features["compute_budget_instruction_count"] == 2


def test_decode_request_heap_frame_only():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_request_heap_frame_instruction(
                    heap_frame_bytes=131_072,
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.fee_source == "UNKNOWN"
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None
    assert REASON_COMPUTE_BUDGET_HEAP_FRAME_DECODED in result.reason_codes
    assert REASON_COMPUTE_UNIT_LIMIT_DECODED not in result.reason_codes
    assert REASON_COMPUTE_UNIT_PRICE_DECODED not in result.reason_codes
    assert result.numeric_features["heap_frame_bytes"] == 131_072
    assert TAG_REQUEST_HEAP_FRAME in result.evidence["tags_seen"]


def test_decode_request_units_deprecated_marks_as_legacy():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_request_units_deprecated_instruction(
                    requested_units=400_000,
                    additional_fee_lamports=10_000,
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None
    assert (
        REASON_COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED
        in result.reason_codes
    )
    # Critical: must NOT be silently promoted to the modern
    # SetComputeUnitLimit / SetComputeUnitPrice surface.
    assert REASON_COMPUTE_UNIT_LIMIT_DECODED not in result.reason_codes
    assert REASON_COMPUTE_UNIT_PRICE_DECODED not in result.reason_codes
    assert (
        result.numeric_features["deprecated_requested_units"] == 400_000
    )
    assert (
        result.numeric_features["deprecated_additional_fee_lamports"]
        == 10_000
    )
    assert TAG_REQUEST_UNITS_DEPRECATED in result.evidence["tags_seen"]


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_decode_unknown_tag_fails_closed():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data=encode_compute_budget_unknown_tag_data(
                        tag=99, body=bytes(8)
                    ),
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert result.data_status == "MALFORMED"
    assert result.confidence_level == "NONE"
    assert result.fee_source == "UNKNOWN"
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None
    assert REASON_COMPUTE_BUDGET_UNKNOWN_TAG in result.reason_codes


def test_decode_malformed_short_body_fails_closed():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data=encode_compute_budget_malformed_short_body_data(),
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert result.data_status == "MALFORMED"
    assert REASON_COMPUTE_BUDGET_MALFORMED_DATA in result.reason_codes
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None


def test_decode_empty_data_fails_closed():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data=encode_compute_budget_empty_data(),
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert REASON_COMPUTE_BUDGET_MALFORMED_DATA in result.reason_codes


def test_decode_invalid_base64_data_fails_closed():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data="not_valid_base64_$$",
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert result.data_status == "MALFORMED"
    assert REASON_COMPUTE_BUDGET_MALFORMED_DATA in result.reason_codes


def test_decode_failure_does_not_expose_unit_limit_or_price_from_other_instructions():
    """Even when one valid SetComputeUnitLimit succeeds, an
    unknown tag elsewhere in the same transaction forces
    DECODE_FAILED and the decoder MUST NOT expose any
    successfully-parsed unit_limit / unit_price -- the overall
    observation is suspect.
    """
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=200_000)
            ),
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data=encode_compute_budget_unknown_tag_data(
                        tag=77, body=b""
                    ),
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None


# ---------------------------------------------------------------------------
# Multi-instruction policies
# ---------------------------------------------------------------------------


def test_multiple_set_compute_unit_limit_is_last_write_wins():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=100_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=400_000)
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.unit_limit == 400_000
    assert (
        REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS
        in result.reason_codes
    )
    # Every observed limit is recorded in evidence so a downstream
    # consumer can detect the rewrite.
    assert result.evidence["compute_unit_limit_values_observed"] == [
        100_000,
        400_000,
    ]
    assert (
        result.numeric_features["compute_unit_limit_instruction_count"] == 2
    )


def test_multiple_set_compute_unit_price_surfaces_ambiguity():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_000
                )
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=2_000
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert result.data_status == "PARTIAL"
    assert result.confidence_level == "LOW"
    # Critical: the price is NOT silently chosen.
    assert result.unit_price_microlamports is None
    assert (
        REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS
        in result.reason_codes
    )
    # fee_source still records that priority-fee evidence was
    # observed; the decoder_status surfaces the ambiguity.
    assert result.fee_source == "PRIORITY_FEE"
    assert result.evidence["compute_unit_price_values_observed"] == [
        1_000,
        2_000,
    ]


def test_mixed_multiple_limit_and_multiple_price_keeps_price_ambiguity():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=100_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=200_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=500
                )
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_500
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    # Last-write-wins for limit even when price is ambiguous.
    assert result.unit_limit == 200_000
    assert result.unit_price_microlamports is None
    assert (
        REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS
        in result.reason_codes
    )
    assert (
        REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS
        in result.reason_codes
    )


# ---------------------------------------------------------------------------
# Scope: non-CB and inner-CB are not decoded
# ---------------------------------------------------------------------------


def test_decode_ignores_non_compute_budget_instructions():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(make_non_compute_budget_instruction()),
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=200_000)
            ),
            MappingProxyType(
                make_non_compute_budget_instruction(
                    program_id=(
                        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
                    ),
                )
            ),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.unit_limit == 200_000
    assert (
        result.numeric_features["compute_budget_instruction_count"] == 1
    )


def test_decode_ignores_inner_compute_budget_but_surfaces_evidence():
    inner_compute_budget_instruction = make_inner_instruction(
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        accounts=(),
        data=encode_compute_budget_set_unit_limit_data(units=999_999),
    )
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(make_non_compute_budget_instruction()),
        ),
        inner_instructions=(
            MappingProxyType(inner_compute_budget_instruction),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    # No top-level ComputeBudget -> ABSENT.
    assert result.decoder_status == "ABSENT"
    # But the inner-CPI ComputeBudget instruction is surfaced
    # as ignored evidence.
    assert (
        REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT
        in result.reason_codes
    )
    assert (
        result.numeric_features["inner_compute_budget_instruction_count"]
        == 1
    )
    # The inner instruction's value MUST NOT leak into the
    # decoded unit_limit -- inner CPI ComputeBudget is not
    # honored by the Solana runtime and must not be honored here.
    assert result.unit_limit is None


def test_decode_top_level_compute_budget_with_inner_compute_budget_records_both():
    inner_compute_budget_instruction = make_inner_instruction(
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        accounts=(),
        data=encode_compute_budget_set_unit_limit_data(units=11_111),
    )
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=222_222)
            ),
        ),
        inner_instructions=(
            MappingProxyType(inner_compute_budget_instruction),
        ),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    # Top-level limit wins; inner is recorded but ignored.
    assert result.unit_limit == 222_222
    assert (
        REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT
        in result.reason_codes
    )
    assert (
        result.numeric_features["inner_compute_budget_instruction_count"]
        == 1
    )


# ---------------------------------------------------------------------------
# Output stability
# ---------------------------------------------------------------------------


def test_decode_is_deterministic_across_repeated_calls():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=200_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_234
                )
            ),
        ),
    )
    first = decode_compute_budget(execution_input)
    second = decode_compute_budget(execution_input)
    assert first == second
    assert first.result_hash == second.result_hash


def test_decode_preserves_input_missing_fields():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=100)
            ),
        ),
        missing_fields=("post_token_balances", "pre_token_balances"),
    )
    result = decode_compute_budget(execution_input)
    _assert_closed_set_result(result)
    assert result.input_missing_fields == (
        "post_token_balances",
        "pre_token_balances",
    )
