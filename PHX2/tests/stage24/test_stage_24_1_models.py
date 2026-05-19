"""Stage 24.1 model tests.

Pins:

  * Immutability of Stage 24 NamedTuple records.
  * Closed-set validation on per-decoder-result builders.
  * Deterministic canonical-JSON hashing (sorted keys, no
    whitespace separators, ASCII-safe).
  * ``payload_hash`` is stable across two builds of the same
    logical input.
  * ``payload_hash`` is stable under dict key reordering on the
    ``meta`` mapping.
  * None preservation: ``None`` amounts NEVER coerce to ``0``.
  * Negative amount rejection.
  * Boolean values are NOT accepted as int amounts.
  * Canonical-JSON rejects NaN / Infinity.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage24.constants import (
    CONFIDENCE_LEVEL_HIGH,
    DATA_STATUS_COMPLETE,
    DECODER_STATUS_DECODED,
    DEFAULT_THRESHOLD_VERSION,
    FEE_SOURCE_PRIORITY_FEE,
    INSTRUCTION_LOCATION_TOP_LEVEL,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
)
from PHX2.stage24.errors import Stage24ContractError
from PHX2.stage24.models import (
    Stage24ComputeBudgetResult,
    Stage24ExecutionInput,
    Stage24ExecutionPrimitive,
    Stage24ExecutionQualityResult,
    Stage24JitoTipResult,
    Stage24PriorityFeeResult,
    Stage24RouterFeeResult,
    Stage24RunnerResult,
    assert_data_status_in_closed_set,
    assert_decoder_status_in_closed_set,
    assert_fee_source_in_closed_set,
    assert_optional_non_negative_int,
    assert_primitive_family_in_closed_set,
    build_compute_budget_result,
    canonical_json,
    compute_execution_input_hash,
    stage24_hash,
)
from PHX2.tests.stage24.fixtures.builders import (
    FIXED_CLOCK_UTC,
    make_execution_input,
)


# ---------------------------------------------------------------------------
# NamedTuple immutability
# ---------------------------------------------------------------------------


def test_stage24_execution_input_is_immutable():
    record = make_execution_input()
    with pytest.raises(AttributeError):
        record.signature = "different"  # type: ignore[misc]


def test_stage24_execution_input_is_a_namedtuple():
    assert issubclass(Stage24ExecutionInput, tuple)


def test_stage24_compute_budget_result_is_a_namedtuple():
    assert issubclass(Stage24ComputeBudgetResult, tuple)


def test_stage24_priority_fee_result_is_a_namedtuple():
    assert issubclass(Stage24PriorityFeeResult, tuple)


def test_stage24_jito_tip_result_is_a_namedtuple():
    assert issubclass(Stage24JitoTipResult, tuple)


def test_stage24_router_fee_result_is_a_namedtuple():
    assert issubclass(Stage24RouterFeeResult, tuple)


def test_stage24_execution_quality_result_is_a_namedtuple():
    assert issubclass(Stage24ExecutionQualityResult, tuple)


def test_stage24_execution_primitive_is_a_namedtuple():
    assert issubclass(Stage24ExecutionPrimitive, tuple)


def test_stage24_runner_result_is_a_namedtuple():
    assert issubclass(Stage24RunnerResult, tuple)


def test_compute_budget_result_is_immutable():
    result = build_compute_budget_result(
        decoder_name="fixture_decoder",
        decoder_version="fixture_v1",
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODED,
        data_status=DATA_STATUS_COMPLETE,
        confidence_level=CONFIDENCE_LEVEL_HIGH,
        fee_source=FEE_SOURCE_PRIORITY_FEE,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id="ComputeBudget111111111111111111111111111111",
        unit_limit=200_000,
        unit_price_microlamports=1_000,
        reason_codes=("decoded_unit_price",),
        numeric_features=MappingProxyType({"unit_limit": 200_000}),
        evidence=MappingProxyType({"source": "fixture"}),
        input_missing_fields=(),
    )
    with pytest.raises(AttributeError):
        result.decoder_status = "PARTIAL"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Canonical-JSON
# ---------------------------------------------------------------------------


def test_canonical_json_sorts_dict_keys():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1}'


def test_canonical_json_supports_tuple_and_list():
    a = canonical_json(("x", "y"))
    b = canonical_json(["x", "y"])
    assert a == b
    assert a == '["x","y"]'


def test_canonical_json_rejects_nan():
    with pytest.raises(Stage24ContractError):
        canonical_json(float("nan"))


def test_canonical_json_rejects_infinity():
    with pytest.raises(Stage24ContractError):
        canonical_json(float("inf"))


def test_canonical_json_rejects_non_string_dict_key():
    with pytest.raises(Stage24ContractError):
        canonical_json({1: "value"})


def test_canonical_json_rejects_unsupported_type():
    class Custom:
        pass

    with pytest.raises(Stage24ContractError):
        canonical_json(Custom())


# ---------------------------------------------------------------------------
# stage24_hash determinism
# ---------------------------------------------------------------------------


def test_stage24_hash_is_deterministic():
    body = {"a": 1, "b": [1, 2, 3], "c": "x"}
    assert stage24_hash(body) == stage24_hash(body)


def test_stage24_hash_is_dict_order_independent():
    a = stage24_hash({"a": 1, "b": 2})
    b = stage24_hash({"b": 2, "a": 1})
    assert a == b


def test_stage24_hash_differs_when_value_differs():
    a = stage24_hash({"a": 1})
    b = stage24_hash({"a": 2})
    assert a != b


# ---------------------------------------------------------------------------
# Stage 24 execution-input hashing
# ---------------------------------------------------------------------------


def test_compute_execution_input_hash_matches_record_payload_hash():
    record = make_execution_input()
    assert compute_execution_input_hash(record) == record.payload_hash


def test_two_identical_execution_inputs_produce_identical_payload_hash():
    a = make_execution_input(signature="sig_same_001")
    b = make_execution_input(signature="sig_same_001")
    assert a.payload_hash == b.payload_hash


def test_changed_signature_changes_payload_hash():
    a = make_execution_input(signature="sig_alpha_001")
    b = make_execution_input(signature="sig_beta_001")
    assert a.payload_hash != b.payload_hash


def test_meta_key_reordering_does_not_change_payload_hash():
    a = make_execution_input(
        meta=MappingProxyType({"fee": 5000, "compute_units_consumed": 1234}),
    )
    b = make_execution_input(
        meta=MappingProxyType({"compute_units_consumed": 1234, "fee": 5000}),
    )
    assert a.payload_hash == b.payload_hash


# ---------------------------------------------------------------------------
# None / amount semantics
# ---------------------------------------------------------------------------


def test_optional_non_negative_int_accepts_none():
    assert_optional_non_negative_int(field_name="unit_limit", value=None)


def test_optional_non_negative_int_accepts_zero():
    # A real decoded zero is permitted; the contract bans None
    # coercion to 0, not the legitimate zero value itself.
    assert_optional_non_negative_int(field_name="unit_limit", value=0)


def test_optional_non_negative_int_accepts_positive_int():
    assert_optional_non_negative_int(
        field_name="unit_limit", value=1_000_000
    )


def test_optional_non_negative_int_rejects_negative():
    with pytest.raises(Stage24ContractError):
        assert_optional_non_negative_int(
            field_name="unit_limit", value=-1
        )


def test_optional_non_negative_int_rejects_bool():
    with pytest.raises(Stage24ContractError):
        assert_optional_non_negative_int(
            field_name="unit_limit", value=True
        )


def test_optional_non_negative_int_rejects_string():
    with pytest.raises(Stage24ContractError):
        assert_optional_non_negative_int(
            field_name="unit_limit", value="0"
        )


def test_optional_non_negative_int_rejects_float():
    with pytest.raises(Stage24ContractError):
        assert_optional_non_negative_int(
            field_name="unit_limit", value=1.0
        )


def test_compute_budget_builder_preserves_none_amounts():
    result = build_compute_budget_result(
        decoder_name="fixture_decoder",
        decoder_version="fixture_v1",
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status="ABSENT",
        data_status="MISSING",
        confidence_level="NONE",
        fee_source="UNKNOWN",
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location="UNKNOWN",
        program_id="",
        unit_limit=None,
        unit_price_microlamports=None,
        reason_codes=("absent_compute_budget_instruction",),
        numeric_features=MappingProxyType({}),
        evidence=MappingProxyType({}),
        input_missing_fields=("top_level_instructions",),
    )
    assert result.unit_limit is None
    assert result.unit_price_microlamports is None
    # None must NOT be coerced to 0 in any downstream surface.
    assert result.unit_limit != 0
    assert result.unit_price_microlamports != 0


# ---------------------------------------------------------------------------
# Closed-set assertions
# ---------------------------------------------------------------------------


def test_assert_primitive_family_rejects_unknown():
    with pytest.raises(Stage24ContractError):
        assert_primitive_family_in_closed_set("BOGUS_FAMILY")


def test_assert_decoder_status_rejects_unknown():
    with pytest.raises(Stage24ContractError):
        assert_decoder_status_in_closed_set("BOGUS_STATUS")


def test_assert_decoder_status_rejects_router_fee_candidate():
    # ROUTER_FEE_CANDIDATE belongs in FEE_SOURCES, not
    # DECODER_STATUSES. The assertion helper must reject it as
    # a decoder_status value.
    with pytest.raises(Stage24ContractError):
        assert_decoder_status_in_closed_set("ROUTER_FEE_CANDIDATE")


def test_assert_data_status_rejects_unknown():
    with pytest.raises(Stage24ContractError):
        assert_data_status_in_closed_set("BOGUS")


def test_assert_fee_source_accepts_router_fee_candidate():
    # ROUTER_FEE_CANDIDATE is a fee_source axis member.
    assert_fee_source_in_closed_set("ROUTER_FEE_CANDIDATE")


def test_assert_fee_source_rejects_unknown_token():
    with pytest.raises(Stage24ContractError):
        assert_fee_source_in_closed_set("BOGUS_FEE")


def test_build_compute_budget_result_rejects_invalid_decoder_status():
    with pytest.raises(Stage24ContractError):
        build_compute_budget_result(
            decoder_name="fixture_decoder",
            decoder_version="fixture_v1",
            threshold_version=DEFAULT_THRESHOLD_VERSION,
            decoder_status="ROUTER_FEE_CANDIDATE",
            data_status=DATA_STATUS_COMPLETE,
            confidence_level=CONFIDENCE_LEVEL_HIGH,
            fee_source=FEE_SOURCE_PRIORITY_FEE,
            route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
            instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
            program_id="ComputeBudget111111111111111111111111111111",
            unit_limit=200_000,
            unit_price_microlamports=1_000,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            evidence=MappingProxyType({}),
            input_missing_fields=(),
        )


# ---------------------------------------------------------------------------
# Tuple shape preservation
# ---------------------------------------------------------------------------


def test_execution_input_account_keys_is_tuple():
    record = make_execution_input()
    assert isinstance(record.account_keys, tuple)


def test_execution_input_top_level_instructions_is_tuple():
    record = make_execution_input()
    assert isinstance(record.top_level_instructions, tuple)


def test_execution_input_pre_balances_is_tuple():
    record = make_execution_input()
    assert isinstance(record.pre_balances, tuple)


def test_execution_input_log_messages_is_tuple():
    record = make_execution_input()
    assert isinstance(record.log_messages, tuple)


def test_execution_input_meta_is_mapping():
    from typing import Mapping

    record = make_execution_input()
    assert isinstance(record.meta, Mapping)


def test_fixed_clock_utc_is_set():
    assert FIXED_CLOCK_UTC == "2026-01-01T00:00:00Z"
