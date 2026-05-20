"""Stage 24.6 execution-quality evaluator tests.

Pins the observe-only behavior of ``evaluate_execution_quality``:

  * Success / failure / unknown landing semantics.
  * Realized priority-fee / Jito-tip pass-through (DECODED only).
  * Router-fee remains unknown / candidate; the Stage 24.5 Path B
    lock means ``realized_router_fee_lamports`` is always None.
  * Compute-unit utilization basis-points derivation requires
    both ``compute_units_consumed`` and the decoded
    ``unit_limit``.
  * Outputs are members of the Stage 24 closed sets.
"""

from __future__ import annotations

from types import MappingProxyType

from PHX2.stage24.constants import (
    CONFIDENCE_LEVELS,
    DATA_STATUSES,
    DECODER_STATUSES,
    FEE_SOURCES,
    PRIMITIVE_FAMILY_EXECUTION_QUALITY,
    ROUTE_FAMILIES,
    STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER,
)
from PHX2.stage24.compute_budget import decode_compute_budget
from PHX2.stage24.execution_quality import (
    REASON_COMPUTE_UNIT_UTILIZATION_DERIVED,
    REASON_COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE,
    REASON_EXECUTION_QUALITY_FAILED,
    REASON_EXECUTION_QUALITY_LANDED,
    REASON_EXECUTION_QUALITY_LANDING_UNKNOWN,
    REASON_EXECUTION_QUALITY_OBSERVE_ONLY,
    REASON_JITO_TIP_NOT_CONFIRMED,
    REASON_PRIORITY_FEE_NOT_CONFIRMED,
    REASON_ROUTER_FEE_NOT_CONFIRMED,
    evaluate_execution_quality,
)
from PHX2.stage24.jito_tip import decode_jito_tip
from PHX2.stage24.priority_fee import decode_priority_fee
from PHX2.stage24.router_fee import decode_router_fee_candidate
from PHX2.tests.stage24.fixtures.builders import (
    make_axiom_flashx8_instruction,
    make_compute_budget_set_unit_limit_instruction,
    make_compute_budget_set_unit_price_instruction,
    make_execution_input,
    make_jito_tip_instruction,
    make_router_like_execution_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_full_priority_fee_input(
    *,
    transaction_status: str = "success",
    compute_units_consumed: int = 50_000,
    meta_extra: dict | None = None,
):
    """Build an input that yields a fully decoded priority-fee surface."""
    meta = {
        "compute_units_consumed": compute_units_consumed,
        "fee": 5000,
    }
    if meta_extra:
        meta.update(meta_extra)
    return make_execution_input(
        transaction_status=transaction_status,
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(
                units=200_000,
            ),
            make_compute_budget_set_unit_price_instruction(
                micro_lamports_per_compute_unit=1_000,
            ),
        ),
        meta=MappingProxyType(meta),
    )


def _run_pipeline(execution_input):
    """Run the four upstream decoders and the quality evaluator."""
    cb = decode_compute_budget(execution_input)
    pf = decode_priority_fee(execution_input)
    jt = decode_jito_tip(execution_input)
    rf = decode_router_fee_candidate(execution_input)
    eq = evaluate_execution_quality(
        execution_input=execution_input,
        compute_budget_result=cb,
        priority_fee_result=pf,
        jito_tip_result=jt,
        router_fee_result=rf,
    )
    return cb, pf, jt, rf, eq


# ---------------------------------------------------------------------------
# Success tx produces landed evidence
# ---------------------------------------------------------------------------


def test_success_tx_produces_landed_true():
    execution_input = _build_full_priority_fee_input()
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.landed is True
    assert REASON_EXECUTION_QUALITY_LANDED in result.reason_codes
    assert REASON_EXECUTION_QUALITY_FAILED not in result.reason_codes
    assert REASON_EXECUTION_QUALITY_OBSERVE_ONLY in result.reason_codes


def test_success_tx_primitive_family_is_execution_quality():
    execution_input = _build_full_priority_fee_input()
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.primitive_family == PRIMITIVE_FAMILY_EXECUTION_QUALITY


# ---------------------------------------------------------------------------
# Failed tx does not claim landed quality
# ---------------------------------------------------------------------------


def test_failed_tx_lands_false_and_realized_fees_remain_none():
    execution_input = _build_full_priority_fee_input(
        transaction_status="err"
    )
    cb, pf, jt, rf, result = _run_pipeline(execution_input)
    assert result.landed is False
    assert REASON_EXECUTION_QUALITY_FAILED in result.reason_codes
    # Jito tip wasn't present so realized stays None either way.
    assert result.realized_jito_tip_lamports is None
    # Priority fee was decoded upstream BUT this run does not
    # claim a HIGH-confidence quality decode for a failed tx.
    assert result.decoder_status != "DECODED"
    assert result.confidence_level != "HIGH"


def test_failed_tx_never_marks_landed_true():
    execution_input = _build_full_priority_fee_input(
        transaction_status="failed"
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.landed is False


# ---------------------------------------------------------------------------
# Unknown landing
# ---------------------------------------------------------------------------


def test_unknown_transaction_status_lands_none():
    execution_input = _build_full_priority_fee_input(
        transaction_status=""
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.landed is None
    assert REASON_EXECUTION_QUALITY_LANDING_UNKNOWN in result.reason_codes
    assert result.decoder_status == "ABSENT"
    assert result.data_status == "MISSING"
    assert result.confidence_level == "NONE"


def test_garbage_transaction_status_lands_none():
    execution_input = _build_full_priority_fee_input(
        transaction_status="unknown_status_token"
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.landed is None
    assert REASON_EXECUTION_QUALITY_LANDING_UNKNOWN in result.reason_codes


# ---------------------------------------------------------------------------
# Compute utilization basis points
# ---------------------------------------------------------------------------


def test_compute_unit_utilization_derived_when_both_present():
    execution_input = _build_full_priority_fee_input(
        compute_units_consumed=100_000,
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    # 100_000 / 200_000 = 50% = 5000 basis points
    assert (
        result.numeric_features["compute_unit_utilization_basis_points"]
        == 5_000
    )
    assert (
        REASON_COMPUTE_UNIT_UTILIZATION_DERIVED in result.reason_codes
    )


def test_compute_unit_utilization_none_when_units_consumed_missing():
    # No compute_units_consumed in meta
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(
                units=200_000,
            ),
            make_compute_budget_set_unit_price_instruction(
                micro_lamports_per_compute_unit=1_000,
            ),
        ),
        meta=MappingProxyType({"fee": 5000}),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert (
        result.numeric_features["compute_unit_utilization_basis_points"]
        is None
    )
    assert (
        REASON_COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE
        in result.reason_codes
    )


def test_compute_unit_utilization_none_when_limit_missing():
    # No compute-budget instructions at all
    execution_input = make_execution_input(
        top_level_instructions=(),
        meta=MappingProxyType({"compute_units_consumed": 50_000}),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert (
        result.numeric_features["compute_unit_utilization_basis_points"]
        is None
    )


# ---------------------------------------------------------------------------
# Priority fee estimate is carried but realized observed fee stays None
# ---------------------------------------------------------------------------


def test_priority_fee_estimate_carried_when_decoded():
    execution_input = _build_full_priority_fee_input()
    cb, pf, _, _, result = _run_pipeline(execution_input)
    assert pf.decoder_status == "DECODED"
    assert (
        result.realized_priority_fee_lamports == pf.amount_lamports
    )
    assert REASON_PRIORITY_FEE_NOT_CONFIRMED not in result.reason_codes


def test_priority_fee_not_confirmed_when_compute_budget_absent():
    execution_input = make_execution_input(
        top_level_instructions=(),
        meta=MappingProxyType({"fee": 5000}),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.realized_priority_fee_lamports is None
    assert REASON_PRIORITY_FEE_NOT_CONFIRMED in result.reason_codes


# ---------------------------------------------------------------------------
# Jito tip carried when decoded
# ---------------------------------------------------------------------------


def test_jito_tip_carried_when_decoded():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
            make_compute_budget_set_unit_price_instruction(
                micro_lamports_per_compute_unit=1_000,
            ),
            make_jito_tip_instruction(lamports=10_000),
        ),
        account_keys=(
            "AccountA1111111111111111111111111111111111",
            "AccountB2222222222222222222222222222222222",
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 50_000, "fee": 5000}
        ),
    )
    _, _, jt, _, result = _run_pipeline(execution_input)
    assert jt.decoder_status == "DECODED"
    assert result.realized_jito_tip_lamports == 10_000
    assert REASON_JITO_TIP_NOT_CONFIRMED not in result.reason_codes


def test_jito_tip_not_confirmed_when_absent():
    execution_input = _build_full_priority_fee_input()
    _, _, jt, _, result = _run_pipeline(execution_input)
    assert jt.decoder_status == "ABSENT"
    assert result.realized_jito_tip_lamports is None
    assert REASON_JITO_TIP_NOT_CONFIRMED in result.reason_codes


# ---------------------------------------------------------------------------
# Router fee remains unknown/candidate (Path B lock)
# ---------------------------------------------------------------------------


def test_router_fee_realized_amount_is_always_none():
    # Even with an active router candidate, the realized amount
    # is None at Stage 24.6.
    execution_input = make_router_like_execution_input(
        top_level_instructions=(make_axiom_flashx8_instruction(),),
    )
    _, _, _, rf, result = _run_pipeline(execution_input)
    assert rf.decoder_status == "DECODE_UNCONFIRMED"
    assert rf.amount_lamports is None
    assert result.realized_router_fee_lamports is None
    assert REASON_ROUTER_FEE_NOT_CONFIRMED in result.reason_codes


def test_no_router_input_does_not_emit_router_not_confirmed():
    # When the router-fee surface saw ABSENT, the
    # ROUTER_FEE_NOT_CONFIRMED reason is not added.
    execution_input = _build_full_priority_fee_input()
    _, _, _, rf, result = _run_pipeline(execution_input)
    assert rf.decoder_status == "ABSENT"
    assert REASON_ROUTER_FEE_NOT_CONFIRMED not in result.reason_codes


def test_router_fee_confirmed_decoder_evidence_marker_is_false():
    execution_input = make_router_like_execution_input(
        top_level_instructions=(make_axiom_flashx8_instruction(),),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert (
        result.evidence["router_fee_confirmed_decoder"]
        == STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER
    )
    assert (
        result.evidence["router_fee_confirmed_decoder"] is False
    )


# ---------------------------------------------------------------------------
# None preservation: unknowns stay None, not 0
# ---------------------------------------------------------------------------


def test_realized_amounts_default_to_none_not_zero():
    execution_input = make_execution_input(
        top_level_instructions=(),
        meta=MappingProxyType({}),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.realized_priority_fee_lamports is None
    assert result.realized_jito_tip_lamports is None
    assert result.realized_router_fee_lamports is None


# ---------------------------------------------------------------------------
# Closed-set output values
# ---------------------------------------------------------------------------


def test_output_values_are_members_of_closed_sets():
    cases = (
        _build_full_priority_fee_input(),
        _build_full_priority_fee_input(transaction_status="err"),
        _build_full_priority_fee_input(transaction_status=""),
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        ),
    )
    for execution_input in cases:
        _, _, _, _, result = _run_pipeline(execution_input)
        assert result.decoder_status in DECODER_STATUSES
        assert result.data_status in DATA_STATUSES
        assert result.confidence_level in CONFIDENCE_LEVELS
        assert result.fee_source in FEE_SOURCES
        assert result.route_family in ROUTE_FAMILIES


# ---------------------------------------------------------------------------
# Slot delta arithmetic
# ---------------------------------------------------------------------------


def test_slot_delta_computed_when_submitted_slot_present():
    execution_input = make_execution_input(
        slot=250_000_010,
        meta=MappingProxyType(
            {"submitted_slot": 250_000_000, "fee": 5000}
        ),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.slot_delta == 10


def test_slot_delta_none_when_submitted_slot_absent():
    execution_input = _build_full_priority_fee_input()
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.slot_delta is None


# ---------------------------------------------------------------------------
# Error code surfacing (short non-secret only)
# ---------------------------------------------------------------------------


def test_short_error_code_is_carried_verbatim():
    execution_input = make_execution_input(
        transaction_status="err",
        meta=MappingProxyType(
            {"error_code": "InstructionError", "fee": 5000}
        ),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.error_code == "InstructionError"


def test_oversize_error_code_is_dropped():
    execution_input = make_execution_input(
        transaction_status="err",
        meta=MappingProxyType(
            {"error_code": "x" * 200, "fee": 5000}
        ),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.error_code == ""


def test_missing_error_code_is_empty_string():
    execution_input = _build_full_priority_fee_input()
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.error_code == ""


# ---------------------------------------------------------------------------
# Builder validation rejects negative amounts
# ---------------------------------------------------------------------------


def test_execution_quality_result_carries_input_missing_fields():
    execution_input = _build_full_priority_fee_input()
    _, _, _, _, result = _run_pipeline(execution_input)
    assert result.input_missing_fields == execution_input.missing_fields


# ---------------------------------------------------------------------------
# Execution-fee component counters
# ---------------------------------------------------------------------------


def test_execution_fee_components_counts_full_picture():
    execution_input = make_execution_input(
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
            make_compute_budget_set_unit_price_instruction(
                micro_lamports_per_compute_unit=1_000,
            ),
            make_jito_tip_instruction(lamports=10_000),
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 50_000, "fee": 5000}
        ),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    assert (
        result.numeric_features["execution_fee_components_known_count"]
        == 2
    )
    # Router-fee absent (no active candidate), priority+jito known,
    # so unknown count = 0.
    assert (
        result.numeric_features["execution_fee_components_unknown_count"]
        == 0
    )


def test_execution_fee_components_counts_router_candidate():
    execution_input = make_router_like_execution_input(
        top_level_instructions=(make_axiom_flashx8_instruction(),),
    )
    _, _, _, _, result = _run_pipeline(execution_input)
    # priority unknown + jito unknown + router_active = 3 unknown
    assert (
        result.numeric_features["execution_fee_components_unknown_count"]
        == 3
    )
    assert (
        result.numeric_features["execution_fee_components_known_count"]
        == 0
    )
