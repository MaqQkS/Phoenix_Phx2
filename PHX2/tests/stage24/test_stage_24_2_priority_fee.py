"""Stage 24.2 priority-fee decoder tests.

Pins:

  * No compute-unit price observed -> ``ABSENT`` /
    ``amount_lamports = None``. Never 0 as a stand-in.
  * Price present but ``compute_units_consumed`` missing ->
    ``PARTIAL`` / ``amount_lamports = None``.
  * Both price and consumed present -> ``DECODED`` with
    ``amount_lamports = ceil(price * consumed / 1_000_000)``;
    the estimated value is labeled in numeric features and
    reason codes.
  * Rounding is locked to ceiling (matches Solana runtime).
  * ComputeBudget ``DECODE_FAILED`` propagates to the priority-
    fee result as ``DECODE_FAILED`` / ``amount_lamports = None``;
    no fake zero / no fee inferred from meta.
  * ComputeBudget ``DECODE_UNCONFIRMED`` (multiple-price
    ambiguity) propagates as ``DECODE_UNCONFIRMED`` /
    ``amount_lamports = None``.
  * Observed vs estimated fields are not conflated:
    ``priority_fee_observed_lamports`` stays ``None`` even
    when the estimate is computed; only
    ``priority_fee_estimated_lamports`` carries the value.
  * The priority-fee decoder imports / reuses the ComputeBudget
    decoder rather than re-parsing instruction bytes.
  * Every emitted decoder_status / data_status / confidence_level
    / fee_source / route_family / instruction_location is a
    member of the Stage 24 closed sets.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType

from PHX2.stage24 import priority_fee as priority_fee_module
from PHX2.stage24.compute_budget import COMPUTE_BUDGET_DECODER_NAME
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
from PHX2.stage24.models import Stage24PriorityFeeResult
from PHX2.stage24.priority_fee import (
    MICROLAMPORTS_PER_LAMPORT,
    PRIORITY_FEE_DECODER_NAME,
    PRIORITY_FEE_DECODER_VERSION,
    REASON_PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE,
    REASON_PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED,
    REASON_PRIORITY_FEE_CONSUMED_UNITS_MISSING,
    REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS,
    REASON_PRIORITY_FEE_PRICE_ABSENT,
    REASON_PRIORITY_FEE_PRICE_PRESENT,
    decode_priority_fee,
)
from PHX2.tests.stage24.fixtures.builders import (
    encode_compute_budget_unknown_tag_data,
    make_compute_budget_set_unit_limit_instruction,
    make_compute_budget_set_unit_price_instruction,
    make_execution_input,
    make_non_compute_budget_instruction,
    make_top_level_instruction,
)


def _assert_closed_set_result(result: Stage24PriorityFeeResult) -> None:
    assert result.primitive_family == "PRIORITY_FEE"
    assert result.decoder_status in DECODER_STATUSES
    assert result.data_status in DATA_STATUSES
    assert result.confidence_level in CONFIDENCE_LEVELS
    assert result.fee_source in FEE_SOURCES
    assert result.route_family in ROUTE_FAMILIES
    assert result.instruction_location in INSTRUCTION_LOCATIONS
    assert result.decoder_name == PRIORITY_FEE_DECODER_NAME
    assert result.decoder_version == PRIORITY_FEE_DECODER_VERSION
    assert result.threshold_version == DEFAULT_THRESHOLD_VERSION
    assert isinstance(result.result_hash, str) and result.result_hash != ""


# ---------------------------------------------------------------------------
# Absent price
# ---------------------------------------------------------------------------


def test_no_compute_unit_price_yields_absent_and_none_amount():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(make_non_compute_budget_instruction()),
        ),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "ABSENT"
    assert result.data_status == "MISSING"
    assert result.confidence_level == "NONE"
    assert result.fee_source == "UNKNOWN"
    assert result.amount_lamports is None
    assert result.unit_price_microlamports is None
    # Critical: NEVER emit 0 for unknown.
    assert result.amount_lamports != 0
    assert REASON_PRIORITY_FEE_PRICE_ABSENT in result.reason_codes


def test_compute_budget_decoded_without_price_yields_absent():
    # SetComputeUnitLimit present, but no SetComputeUnitPrice.
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=300_000)
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 50_000, "fee": 5000}),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "ABSENT"
    assert result.amount_lamports is None
    assert result.unit_limit == 300_000
    assert result.unit_price_microlamports is None
    assert REASON_PRIORITY_FEE_PRICE_ABSENT in result.reason_codes


# ---------------------------------------------------------------------------
# Partial: price present, consumed missing
# ---------------------------------------------------------------------------


def test_price_present_but_consumed_missing_yields_partial():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=10_000
                )
            ),
        ),
        meta=MappingProxyType({"fee": 5000}),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "PARTIAL"
    assert result.data_status == "PARTIAL"
    assert result.confidence_level == "MEDIUM"
    assert result.fee_source == "PRIORITY_FEE"
    assert result.unit_price_microlamports == 10_000
    assert result.amount_lamports is None
    assert REASON_PRIORITY_FEE_PRICE_PRESENT in result.reason_codes
    assert (
        REASON_PRIORITY_FEE_CONSUMED_UNITS_MISSING in result.reason_codes
    )


def test_price_present_consumed_missing_does_not_synthesize_amount_from_meta_fee():
    """``meta.fee`` is the upstream total fee, not the priority
    fee. Stage 24 MUST NOT synthesize a priority fee from
    ``meta.fee`` when ``compute_units_consumed`` is missing.
    """
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=5_000
                )
            ),
        ),
        meta=MappingProxyType({"fee": 9_999}),
    )
    result = decode_priority_fee(execution_input)
    assert result.amount_lamports is None
    assert result.numeric_features["priority_fee_estimated_lamports"] is None
    assert result.numeric_features["priority_fee_observed_lamports"] is None
    assert result.numeric_features["meta_fee_lamports"] == 9_999


# ---------------------------------------------------------------------------
# Decoded
# ---------------------------------------------------------------------------


def test_price_and_consumed_present_yield_decoded_estimated_amount():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_limit_instruction(units=400_000)
            ),
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=10_000
                )
            ),
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 200_000, "fee": 7_000}
        ),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODED"
    assert result.data_status == "COMPLETE"
    assert result.confidence_level == "HIGH"
    assert result.fee_source == "PRIORITY_FEE"
    assert result.instruction_location == "TOP_LEVEL"
    assert result.program_id == COMPUTE_BUDGET_PROGRAM_ID
    assert result.unit_limit == 400_000
    assert result.unit_price_microlamports == 10_000
    # 10_000 * 200_000 / 1_000_000 = 2_000_000_000 / 1_000_000 = 2_000.
    assert result.amount_lamports == 2_000
    assert (
        result.numeric_features["priority_fee_estimated_lamports"] == 2_000
    )
    assert (
        REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS
        in result.reason_codes
    )


def test_rounding_is_ceiling_not_floor():
    # price * consumed = 1_000_001 micro-lamports -> ceil to 2 lamports
    # (floor would be 1, which would underclaim).
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_000_001
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 1}),
    )
    result = decode_priority_fee(execution_input)
    assert result.decoder_status == "DECODED"
    assert result.amount_lamports == 2
    assert result.numeric_features["priority_fee_microlamports_total"] == 1_000_001


def test_rounding_exact_lamport_boundary_is_exact():
    # price * consumed = 1_000_000 micro-lamports -> exactly 1 lamport.
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_000_000
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 1}),
    )
    result = decode_priority_fee(execution_input)
    assert result.decoder_status == "DECODED"
    assert result.amount_lamports == 1


def test_rounding_zero_consumed_yields_zero_estimated_amount():
    # price > 0 but consumed = 0 -> total = 0 -> ceil(0 / 1_000_000) = 0.
    # This is a real decoded zero (the runtime would also charge 0).
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=10_000
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 0}),
    )
    result = decode_priority_fee(execution_input)
    assert result.decoder_status == "DECODED"
    # Real decoded zero is permitted by the contract; only
    # None-as-zero stand-in is forbidden.
    assert result.amount_lamports == 0


def test_rounding_uses_locked_divisor():
    # The divisor MUST be exactly 1_000_000 microlamports / lamport.
    assert MICROLAMPORTS_PER_LAMPORT == 1_000_000


# ---------------------------------------------------------------------------
# Compute budget decode-failed propagation
# ---------------------------------------------------------------------------


def test_malformed_compute_budget_propagates_as_decode_failed_without_zero():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_top_level_instruction(
                    program_id=COMPUTE_BUDGET_PROGRAM_ID,
                    accounts=(),
                    data=encode_compute_budget_unknown_tag_data(
                        tag=200, body=b""
                    ),
                )
            ),
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 100_000, "fee": 12_345}
        ),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_FAILED"
    assert result.data_status == "MALFORMED"
    assert result.amount_lamports is None
    # Neither the meta-fee nor the consumed_units may be used to
    # synthesize a value when the compute-budget surface is
    # malformed.
    assert result.amount_lamports != 0
    assert (
        REASON_PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED
        in result.reason_codes
    )


def test_ambiguous_compute_budget_price_propagates_as_decode_unconfirmed():
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
        meta=MappingProxyType({"compute_units_consumed": 100_000}),
    )
    result = decode_priority_fee(execution_input)
    _assert_closed_set_result(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert result.data_status == "PARTIAL"
    assert result.confidence_level == "LOW"
    assert result.fee_source == "PRIORITY_FEE"
    assert result.unit_price_microlamports is None
    assert result.amount_lamports is None
    assert (
        REASON_PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE
        in result.reason_codes
    )


# ---------------------------------------------------------------------------
# Observed vs estimated distinction
# ---------------------------------------------------------------------------


def test_observed_lamports_never_set_in_24_2():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=2_500
                )
            ),
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 80_000, "fee": 4_000}
        ),
    )
    result = decode_priority_fee(execution_input)
    assert result.decoder_status == "DECODED"
    assert result.numeric_features["priority_fee_estimated_lamports"] == 200
    # Observed remains None: Stage 24.2 has no safe path to
    # derive a realized priority fee separate from base fee.
    assert result.numeric_features["priority_fee_observed_lamports"] is None


def test_estimated_amount_recorded_with_explicit_estimated_label():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=10_000
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 200_000}),
    )
    result = decode_priority_fee(execution_input)
    assert result.amount_lamports == 2_000
    # The "estimated" label is explicit in numeric_features
    # and in reason codes.
    assert (
        result.numeric_features["priority_fee_estimated_lamports"] == 2_000
    )
    assert (
        REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS
        in result.reason_codes
    )
    assert (
        result.evidence["priority_fee_estimation_rounding"] == "ceiling"
    )
    assert (
        result.evidence["priority_fee_estimation_divisor_microlamports"]
        == 1_000_000
    )


# ---------------------------------------------------------------------------
# Reuse contract
# ---------------------------------------------------------------------------


def test_priority_fee_module_imports_compute_budget():
    """The priority-fee decoder MUST reuse the compute-budget
    decoder by importing it, not duplicate the instruction-byte
    parsing. We verify the import statically by parsing
    ``priority_fee.py`` and checking for the ``from
    PHX2.stage24.compute_budget import ...`` statement.
    """
    source_path = Path(priority_fee_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    seen_compute_budget_import = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "PHX2.stage24.compute_budget"
        ):
            seen_compute_budget_import = True
            break
    assert seen_compute_budget_import, (
        "priority_fee.py must import from PHX2.stage24.compute_budget"
    )


def test_priority_fee_module_does_not_import_base64_directly():
    """The priority-fee decoder must not re-parse instruction
    bytes; it should rely entirely on the compute-budget
    decoder for that. So ``base64`` must NOT appear as a
    top-level import of ``priority_fee.py``.
    """
    source_path = Path(priority_fee_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "base64", (
                    "priority_fee.py must not import base64 directly; "
                    "reuse the compute_budget decoder instead"
                )
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top != "base64", (
                "priority_fee.py must not import from base64 directly; "
                "reuse the compute_budget decoder instead"
            )


def test_priority_fee_reuses_compute_budget_result_hash_in_evidence():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=1_000
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 100_000}),
    )
    result = decode_priority_fee(execution_input)
    # The evidence carries the compute-budget result hash so a
    # downstream consumer can correlate the two records.
    assert isinstance(result.evidence["compute_budget_result_hash"], str)
    assert result.evidence["compute_budget_result_hash"] != ""
    assert (
        result.evidence["upstream_decoder_name"] == COMPUTE_BUDGET_DECODER_NAME
    )


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


def test_priority_fee_decode_is_deterministic():
    execution_input = make_execution_input(
        top_level_instructions=(
            MappingProxyType(
                make_compute_budget_set_unit_price_instruction(
                    micro_lamports_per_compute_unit=4_321
                )
            ),
        ),
        meta=MappingProxyType({"compute_units_consumed": 12_345}),
    )
    a = decode_priority_fee(execution_input)
    b = decode_priority_fee(execution_input)
    assert a == b
    assert a.result_hash == b.result_hash
