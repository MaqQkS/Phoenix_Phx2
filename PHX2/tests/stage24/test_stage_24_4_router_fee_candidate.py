"""Stage 24.4 router-fee candidate decoder tests.

Pins the Stage 24.4 router-fee candidate-only contract:

  * No router program present                 -> ABSENT / NOT_APPLICABLE.
  * Active Axiom Trading Program 1 present    -> AXIOM_TRADING_PROGRAM_1
                                                 candidate.
  * Active Axiom FLASHX8 present              -> AXIOM_FLASHX8 candidate.
  * Deprecated Axiom router present           -> DEPRECATED_AXIOM,
                                                 UNSUPPORTED.
  * Multiple active routers                   -> ambiguity surfaced,
                                                 no decoded fee.
  * Wrapped-swap evidence                     -> surfaced as candidate
                                                 numeric features /
                                                 reason codes.
  * Inner System transfer / Token transfer    -> counted as
                                                 candidate-only.
  * Top-level System transfer after router    -> counted as
                                                 candidate-only.
  * ``decoder_status`` is NEVER ``DECODED`` in Stage 24.4.
  * ``amount_lamports`` is ALWAYS ``None`` in Stage 24.4.
  * ``fee_source`` is in
    {``ROUTER_FEE_CANDIDATE``, ``AXIOM_GLOBAL_FEE_CANDIDATE``,
    ``UNKNOWN``} -- never ``AXIOM_GLOBAL_FEE`` or ``ROUTER_FEE``.
  * Candidate numeric features are explicitly named candidate-only
    (no ``router_fee_amount_*`` or ``axiom_global_fee_*`` keys).
  * Reason ordering is deterministic across runs.
  * ``ROUTER_FEE_CANDIDATE`` / ``AXIOM_GLOBAL_FEE_CANDIDATE`` are
    fee_source axis members, NOT decoder_status members.
"""

from __future__ import annotations

from PHX2.stage24.constants import (
    ACTIVE_AXIOM_ROUTER_PROGRAM_IDS,
    CONFIDENCE_LEVELS,
    DATA_STATUSES,
    DECODER_STATUSES,
    DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS,
    FEE_SOURCES,
    INSTRUCTION_LOCATIONS,
    PRIMITIVE_FAMILIES,
    ROUTE_FAMILIES,
)
from PHX2.stage24.router_fee import (
    REASON_AXIOM_FLASHX8_DETECTED,
    REASON_AXIOM_TRADING_PROGRAM_1_DETECTED,
    REASON_DEPRECATED_AXIOM_ROUTER_DETECTED,
    REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT,
    REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT,
    REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED,
    REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4,
    REASON_ROUTER_FEE_CANDIDATE_ONLY,
    REASON_ROUTER_FEE_DECODE_UNCONFIRMED,
    REASON_ROUTER_FEE_NO_ROUTER_DETECTED,
    REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT,
    REASON_WRAPPED_SWAP_CANDIDATE_DETECTED,
    ROUTER_FEE_DECODER_NAME,
    ROUTER_FEE_DECODER_VERSION,
    decode_router_fee_candidate,
)
from PHX2.tests.stage24.fixtures.builders import (
    make_axiom_flashx8_instruction,
    make_axiom_trading_program_1_instruction,
    make_compute_budget_set_unit_limit_instruction,
    make_deprecated_axiom_instruction,
    make_execution_input,
    make_inner_system_transfer_under_router,
    make_inner_token_transfer_under_router,
    make_jito_tip_instruction,
    make_non_compute_budget_instruction,
    make_router_like_execution_input,
    make_system_transfer_instruction,
    make_wrapped_swap_candidate_execution_input,
)


# ---------------------------------------------------------------------------
# Local stage-24.4 allowed-status / candidate-only subsets
# ---------------------------------------------------------------------------


_STAGE_24_4_ALLOWED_DECODER_STATUSES: frozenset[str] = frozenset(
    {
        "DECODE_UNCONFIRMED",
        "PARTIAL",
        "UNSUPPORTED",
        "ABSENT",
        "NOT_APPLICABLE",
    }
)


_STAGE_24_4_ALLOWED_FEE_SOURCES: frozenset[str] = frozenset(
    {
        "ROUTER_FEE_CANDIDATE",
        "AXIOM_GLOBAL_FEE_CANDIDATE",
        "UNKNOWN",
    }
)


_STAGE_24_4_FORBIDDEN_FEE_SOURCES: frozenset[str] = frozenset(
    {
        "ROUTER_FEE",
        "AXIOM_GLOBAL_FEE",
    }
)


def _assert_closed_set_membership(result) -> None:
    assert result.primitive_family == "ROUTER_FEE"
    assert result.primitive_family in PRIMITIVE_FAMILIES
    assert result.decoder_status in DECODER_STATUSES
    assert result.data_status in DATA_STATUSES
    assert result.confidence_level in CONFIDENCE_LEVELS
    assert result.fee_source in FEE_SOURCES
    assert result.route_family in ROUTE_FAMILIES
    assert result.instruction_location in INSTRUCTION_LOCATIONS


def _assert_amount_is_none(result) -> None:
    assert result.amount_lamports is None
    assert result.amount_token is None
    assert result.mint == ""


# ---------------------------------------------------------------------------
# No-router cases
# ---------------------------------------------------------------------------


def test_default_input_with_only_compute_budget_yields_no_router():
    execution_input = make_execution_input()
    result = decode_router_fee_candidate(execution_input)
    _assert_closed_set_membership(result)
    assert result.decoder_status in {"ABSENT", "NOT_APPLICABLE"}
    assert result.data_status in {"MISSING", "NOT_APPLICABLE"}
    assert result.route_family == "NO_ROUTER_DETECTED"
    assert result.fee_source == "UNKNOWN"
    assert result.program_id == ""
    _assert_amount_is_none(result)
    assert REASON_ROUTER_FEE_NO_ROUTER_DETECTED in result.reason_codes
    assert (
        REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4
        in result.reason_codes
    )


def test_empty_top_level_instructions_yields_no_router():
    execution_input = make_router_like_execution_input(
        top_level_instructions=(),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.decoder_status in {"ABSENT", "NOT_APPLICABLE"}
    assert result.route_family == "NO_ROUTER_DETECTED"
    _assert_amount_is_none(result)


def test_unrelated_program_id_yields_no_router():
    instr = make_non_compute_budget_instruction(
        program_id="Random111111111111111111111111111111111111",
        data="",
    )
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.route_family == "NO_ROUTER_DETECTED"
    _assert_amount_is_none(result)


# ---------------------------------------------------------------------------
# Active Axiom router cases
# ---------------------------------------------------------------------------


def test_flashx8_router_yields_axiom_flashx8_candidate():
    instr = make_axiom_flashx8_instruction()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_closed_set_membership(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert result.data_status == "PARTIAL"
    assert result.confidence_level == "LOW"
    assert result.route_family == "AXIOM_FLASHX8"
    assert result.fee_source == "AXIOM_GLOBAL_FEE_CANDIDATE"
    assert result.instruction_location == "TOP_LEVEL"
    assert result.program_id == ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[1]
    _assert_amount_is_none(result)
    assert REASON_AXIOM_FLASHX8_DETECTED in result.reason_codes
    assert REASON_ROUTER_FEE_DECODE_UNCONFIRMED in result.reason_codes
    assert REASON_ROUTER_FEE_CANDIDATE_ONLY in result.reason_codes
    assert (
        REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4
        in result.reason_codes
    )
    assert result.numeric_features["active_router_instruction_count"] == 1
    assert result.numeric_features["deprecated_router_instruction_count"] == 0


def test_axiom_trading_program_1_router_yields_candidate():
    instr = make_axiom_trading_program_1_instruction()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_closed_set_membership(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert result.route_family == "AXIOM_TRADING_PROGRAM_1"
    assert result.fee_source == "AXIOM_GLOBAL_FEE_CANDIDATE"
    assert result.program_id == ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[0]
    _assert_amount_is_none(result)
    assert REASON_AXIOM_TRADING_PROGRAM_1_DETECTED in result.reason_codes


def test_decoder_name_and_version_are_stage_24_4():
    result = decode_router_fee_candidate(
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        )
    )
    assert result.decoder_name == ROUTER_FEE_DECODER_NAME
    assert result.decoder_version == ROUTER_FEE_DECODER_VERSION
    assert "router_fee" in result.decoder_version


# ---------------------------------------------------------------------------
# Deprecated Axiom router cases
# ---------------------------------------------------------------------------


def test_deprecated_axiom_router_yields_unsupported():
    instr = make_deprecated_axiom_instruction(deprecated_index=0)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_closed_set_membership(result)
    assert result.decoder_status == "UNSUPPORTED"
    assert result.data_status == "UNSUPPORTED"
    assert result.confidence_level == "NONE"
    assert result.route_family == "DEPRECATED_AXIOM"
    assert result.fee_source == "ROUTER_FEE_CANDIDATE"
    assert result.program_id == DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS[0]
    _assert_amount_is_none(result)
    assert (
        REASON_DEPRECATED_AXIOM_ROUTER_DETECTED in result.reason_codes
    )
    assert REASON_ROUTER_FEE_CANDIDATE_ONLY in result.reason_codes
    assert (
        REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4
        in result.reason_codes
    )


def test_second_deprecated_axiom_router_also_unsupported():
    instr = make_deprecated_axiom_instruction(deprecated_index=1)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.decoder_status == "UNSUPPORTED"
    assert result.route_family == "DEPRECATED_AXIOM"
    assert result.fee_source == "ROUTER_FEE_CANDIDATE"
    assert result.program_id == DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS[1]
    _assert_amount_is_none(result)


# ---------------------------------------------------------------------------
# Multiple active routers
# ---------------------------------------------------------------------------


def test_multiple_active_router_families_surface_ambiguity():
    a = make_axiom_flashx8_instruction()
    b = make_axiom_trading_program_1_instruction()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(a, b),
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_closed_set_membership(result)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    _assert_amount_is_none(result)
    assert (
        REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED in result.reason_codes
    )
    assert REASON_AXIOM_FLASHX8_DETECTED in result.reason_codes
    assert (
        REASON_AXIOM_TRADING_PROGRAM_1_DETECTED in result.reason_codes
    )
    assert result.numeric_features["active_router_instruction_count"] == 2


def test_multiple_flashx8_instructions_flagged_as_multiple_routers():
    a = make_axiom_flashx8_instruction()
    b = make_axiom_flashx8_instruction()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(a, b),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert REASON_AXIOM_FLASHX8_DETECTED in result.reason_codes
    assert (
        REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED in result.reason_codes
    )
    _assert_amount_is_none(result)


def test_active_plus_deprecated_router_surfaces_both():
    a = make_axiom_flashx8_instruction()
    d = make_deprecated_axiom_instruction(deprecated_index=0)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(a, d),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.decoder_status == "DECODE_UNCONFIRMED"
    assert result.route_family == "AXIOM_FLASHX8"
    assert REASON_AXIOM_FLASHX8_DETECTED in result.reason_codes
    assert (
        REASON_DEPRECATED_AXIOM_ROUTER_DETECTED in result.reason_codes
    )
    _assert_amount_is_none(result)


# ---------------------------------------------------------------------------
# Wrapped swap evidence
# ---------------------------------------------------------------------------


def test_wrapped_swap_inner_system_transfer_surfaces_candidate():
    execution_input = make_wrapped_swap_candidate_execution_input(
        route_family_index=1,
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_amount_is_none(result)
    assert result.numeric_features["wrapped_swap_candidate"] is True
    assert (
        REASON_WRAPPED_SWAP_CANDIDATE_DETECTED in result.reason_codes
    )
    assert (
        REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT
        in result.reason_codes
    )


def test_wrapped_swap_inner_token_transfer_surfaces_candidate():
    execution_input = make_wrapped_swap_candidate_execution_input(
        route_family_index=0,
        extra_inner_token_transfer=True,
    )
    result = decode_router_fee_candidate(execution_input)
    _assert_amount_is_none(result)
    assert result.numeric_features["wrapped_swap_candidate"] is True
    assert (
        REASON_WRAPPED_SWAP_CANDIDATE_DETECTED in result.reason_codes
    )
    assert (
        REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT
        in result.reason_codes
    )


def test_inner_system_transfer_counted_but_never_decoded():
    router_instr = make_axiom_flashx8_instruction()
    inner_a = make_inner_system_transfer_under_router(lamports=12_345)
    inner_b = make_inner_system_transfer_under_router(lamports=67_890)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(router_instr,),
        inner_instructions=(inner_a, inner_b),
    )
    result = decode_router_fee_candidate(execution_input)
    assert (
        result.numeric_features["inner_system_transfer_candidate_count"]
        == 2
    )
    _assert_amount_is_none(result)
    assert result.decoder_status != "DECODED"


def test_inner_token_transfer_counted_but_never_decoded():
    router_instr = make_axiom_trading_program_1_instruction()
    inner_token = make_inner_token_transfer_under_router()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(router_instr,),
        inner_instructions=(inner_token,),
    )
    result = decode_router_fee_candidate(execution_input)
    assert (
        result.numeric_features["inner_token_transfer_candidate_count"]
        == 1
    )
    _assert_amount_is_none(result)
    assert (
        REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT
        in result.reason_codes
    )


def test_top_level_system_transfer_after_router_counted_as_candidate():
    router_instr = make_axiom_flashx8_instruction()
    sys_after = make_system_transfer_instruction(
        lamports=99,
        destination="DestAfter1111111111111111111111111111111",
    )
    execution_input = make_router_like_execution_input(
        top_level_instructions=(router_instr, sys_after),
    )
    result = decode_router_fee_candidate(execution_input)
    assert (
        result.numeric_features[
            "top_level_system_transfer_after_router_candidate_count"
        ]
        == 1
    )
    _assert_amount_is_none(result)
    assert (
        REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT
        in result.reason_codes
    )


def test_top_level_system_transfer_before_router_does_not_count_as_after():
    sys_before = make_system_transfer_instruction(
        lamports=1,
        destination="Dest1111111111111111111111111111111111111",
    )
    router_instr = make_axiom_flashx8_instruction()
    execution_input = make_router_like_execution_input(
        top_level_instructions=(sys_before, router_instr),
    )
    result = decode_router_fee_candidate(execution_input)
    assert (
        result.numeric_features[
            "top_level_system_transfer_after_router_candidate_count"
        ]
        == 0
    )


# ---------------------------------------------------------------------------
# Cross-cutting Stage 24.4 invariants
# ---------------------------------------------------------------------------


def _all_stage_24_4_router_cases() -> tuple:
    return (
        make_router_like_execution_input(top_level_instructions=()),
        make_execution_input(),
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_trading_program_1_instruction(),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_deprecated_axiom_instruction(deprecated_index=0),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_deprecated_axiom_instruction(deprecated_index=1),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_flashx8_instruction(),
                make_axiom_trading_program_1_instruction(),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_flashx8_instruction(),
            ),
            inner_instructions=(
                make_inner_system_transfer_under_router(),
                make_inner_token_transfer_under_router(),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_flashx8_instruction(),
                make_system_transfer_instruction(
                    lamports=10,
                    destination=(
                        "DestAfter1111111111111111111111111111111"
                    ),
                ),
            ),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_flashx8_instruction(),
                make_deprecated_axiom_instruction(deprecated_index=0),
            ),
        ),
    )


def test_decoder_status_is_never_decoded_for_stage_24_4_router_fee():
    for execution_input in _all_stage_24_4_router_cases():
        result = decode_router_fee_candidate(execution_input)
        assert result.decoder_status != "DECODED"


def test_decoder_status_is_in_stage_24_4_allowed_subset():
    for execution_input in _all_stage_24_4_router_cases():
        result = decode_router_fee_candidate(execution_input)
        assert (
            result.decoder_status in _STAGE_24_4_ALLOWED_DECODER_STATUSES
        )


def test_amount_lamports_is_none_for_every_stage_24_4_router_fee_path():
    for execution_input in _all_stage_24_4_router_cases():
        result = decode_router_fee_candidate(execution_input)
        assert result.amount_lamports is None
        assert result.amount_token is None
        assert result.mint == ""


def test_fee_source_is_only_candidate_in_stage_24_4():
    for execution_input in _all_stage_24_4_router_cases():
        result = decode_router_fee_candidate(execution_input)
        assert result.fee_source in _STAGE_24_4_ALLOWED_FEE_SOURCES
        assert (
            result.fee_source not in _STAGE_24_4_FORBIDDEN_FEE_SOURCES
        )


def test_route_family_is_in_closed_set_for_every_case():
    for execution_input in _all_stage_24_4_router_cases():
        result = decode_router_fee_candidate(execution_input)
        assert result.route_family in ROUTE_FAMILIES


def test_candidate_numeric_feature_keys_are_explicitly_candidate_only():
    router_instr = make_axiom_flashx8_instruction()
    inner_sys = make_inner_system_transfer_under_router()
    inner_token = make_inner_token_transfer_under_router()
    sys_after = make_system_transfer_instruction(
        lamports=1,
        destination="Dest1111111111111111111111111111111111111",
    )
    execution_input = make_router_like_execution_input(
        top_level_instructions=(router_instr, sys_after),
        inner_instructions=(inner_sys, inner_token),
    )
    result = decode_router_fee_candidate(execution_input)
    forbidden_total_keys = (
        "router_fee_amount_lamports",
        "router_fee_amount",
        "router_fee_lamports",
        "axiom_global_fee_lamports",
        "axiom_global_fee_amount",
    )
    for key in forbidden_total_keys:
        assert key not in result.numeric_features, (
            f"Stage 24.4 must not surface decoded-amount key {key!r}"
        )
    required_candidate_keys = (
        "inner_system_transfer_candidate_count",
        "inner_token_transfer_candidate_count",
        "top_level_system_transfer_after_router_candidate_count",
        "router_fee_candidate_count",
    )
    for key in required_candidate_keys:
        assert key in result.numeric_features


def test_reason_ordering_is_deterministic_across_two_runs():
    def _build():
        return make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_flashx8_instruction(),
                make_axiom_trading_program_1_instruction(),
            ),
            inner_instructions=(
                make_inner_system_transfer_under_router(),
                make_inner_token_transfer_under_router(),
            ),
        )

    a = decode_router_fee_candidate(_build())
    b = decode_router_fee_candidate(_build())
    assert a.reason_codes == b.reason_codes


def test_reason_ordering_places_amount_not_decoded_marker_last():
    result = decode_router_fee_candidate(
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        )
    )
    assert (
        result.reason_codes[-1]
        == REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4
    )


def test_reason_ordering_starts_with_no_router_when_absent():
    result = decode_router_fee_candidate(make_execution_input())
    assert (
        result.reason_codes[0] == REASON_ROUTER_FEE_NO_ROUTER_DETECTED
    )


def test_result_hash_is_stable_across_two_runs_for_same_input():
    def _input():
        return make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
            inner_instructions=(
                make_inner_system_transfer_under_router(),
            ),
        )

    a = decode_router_fee_candidate(_input())
    b = decode_router_fee_candidate(_input())
    assert a.result_hash == b.result_hash


# ---------------------------------------------------------------------------
# Closed-set boundary: candidate tokens are fee_source, not decoder_status
# ---------------------------------------------------------------------------


def test_router_fee_candidate_is_a_fee_source_not_decoder_status():
    assert "ROUTER_FEE_CANDIDATE" in FEE_SOURCES
    assert "AXIOM_GLOBAL_FEE_CANDIDATE" in FEE_SOURCES
    assert "ROUTER_FEE_CANDIDATE" not in DECODER_STATUSES
    assert "AXIOM_GLOBAL_FEE_CANDIDATE" not in DECODER_STATUSES


# ---------------------------------------------------------------------------
# Interaction with non-router primitives (negative sanity checks)
# ---------------------------------------------------------------------------


def test_compute_budget_instruction_alone_is_not_a_router():
    instr = make_compute_budget_set_unit_limit_instruction(units=200_000)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.route_family == "NO_ROUTER_DETECTED"
    assert result.decoder_status in {"ABSENT", "NOT_APPLICABLE"}
    _assert_amount_is_none(result)


def test_jito_tip_instruction_alone_is_not_a_router():
    instr = make_jito_tip_instruction(lamports=10_000)
    execution_input = make_router_like_execution_input(
        top_level_instructions=(instr,),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.route_family == "NO_ROUTER_DETECTED"
    _assert_amount_is_none(result)
