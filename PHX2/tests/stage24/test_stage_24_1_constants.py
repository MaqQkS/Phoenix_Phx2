"""Stage 24.1 constants tests.

Pins every Stage 24 closed-set tuple, version axis, Solana
program ID literal, and boundary-scanner input. Any drift in a
token, an ordering, or the size of a set fails here.
"""

from __future__ import annotations

from PHX2.stage24 import constants as c


# ---------------------------------------------------------------------------
# Version / stage axes
# ---------------------------------------------------------------------------


def test_stage_name_token_is_locked():
    assert c.STAGE_NAME == "stage24"


def test_stage_version_axis_is_locked():
    assert c.STAGE_VERSION == "24.1"
    assert c.STAGE24_MINOR_VERSION == "24.1"


def test_stage24_version_full_string_is_locked():
    assert (
        c.STAGE24_VERSION
        == "stage24_v0_execution_primitives_foundation"
    )


def test_default_schema_version_is_locked():
    assert c.DEFAULT_SCHEMA_VERSION == "stage24_v0_execution_primitive"


def test_manifest_schema_version_is_locked():
    assert c.STAGE24_MANIFEST_SCHEMA_VERSION == "stage24_v0_manifest"


def test_observe_only_mode_token_is_locked():
    assert c.OBSERVE_ONLY_MODE == "observe_only"


def test_default_threshold_version_is_locked():
    assert c.DEFAULT_THRESHOLD_VERSION == "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# PRIMITIVE_FAMILIES closed-set
# ---------------------------------------------------------------------------


def test_primitive_families_match_locked_five_token_set():
    assert c.PRIMITIVE_FAMILIES == (
        "COMPUTE_BUDGET",
        "PRIORITY_FEE",
        "JITO_TIP",
        "ROUTER_FEE",
        "EXECUTION_QUALITY",
    )


def test_primitive_families_have_no_duplicates():
    assert len(c.PRIMITIVE_FAMILIES) == len(set(c.PRIMITIVE_FAMILIES))


def test_each_primitive_family_constant_appears_in_tuple():
    expected = {
        c.PRIMITIVE_FAMILY_COMPUTE_BUDGET,
        c.PRIMITIVE_FAMILY_PRIORITY_FEE,
        c.PRIMITIVE_FAMILY_JITO_TIP,
        c.PRIMITIVE_FAMILY_ROUTER_FEE,
        c.PRIMITIVE_FAMILY_EXECUTION_QUALITY,
    }
    assert expected == set(c.PRIMITIVE_FAMILIES)


# ---------------------------------------------------------------------------
# DECODER_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_decoder_statuses_match_locked_eight_token_set():
    assert c.DECODER_STATUSES == (
        "DECODED",
        "PARTIAL",
        "DECODE_UNCONFIRMED",
        "UNSUPPORTED",
        "ABSENT",
        "NOT_APPLICABLE",
        "DECODE_FAILED",
        "INPUT_REJECTED",
    )


def test_decoder_statuses_have_no_duplicates():
    assert len(c.DECODER_STATUSES) == len(set(c.DECODER_STATUSES))


def test_router_fee_candidate_is_not_a_decoder_status():
    # ROUTER_FEE_CANDIDATE is a fee_source axis value, NOT a
    # decoder_status. Stage 24.0 design and the Stage 24
    # honesty rules require this separation.
    assert "ROUTER_FEE_CANDIDATE" not in c.DECODER_STATUSES


def test_axiom_global_fee_candidate_is_not_a_decoder_status():
    assert "AXIOM_GLOBAL_FEE_CANDIDATE" not in c.DECODER_STATUSES


# ---------------------------------------------------------------------------
# DATA_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_data_statuses_match_locked_six_token_set():
    assert c.DATA_STATUSES == (
        "COMPLETE",
        "PARTIAL",
        "MISSING",
        "UNSUPPORTED",
        "NOT_APPLICABLE",
        "MALFORMED",
    )


def test_data_statuses_have_no_duplicates():
    assert len(c.DATA_STATUSES) == len(set(c.DATA_STATUSES))


# ---------------------------------------------------------------------------
# CONFIDENCE_LEVELS closed-set
# ---------------------------------------------------------------------------


def test_confidence_levels_match_locked_four_token_set():
    assert c.CONFIDENCE_LEVELS == ("HIGH", "MEDIUM", "LOW", "NONE")


def test_confidence_levels_have_no_duplicates():
    assert len(c.CONFIDENCE_LEVELS) == len(set(c.CONFIDENCE_LEVELS))


# ---------------------------------------------------------------------------
# FEE_SOURCES closed-set
# ---------------------------------------------------------------------------


def test_fee_sources_match_locked_ten_token_set():
    assert c.FEE_SOURCES == (
        "BASE_FEE",
        "PRIORITY_FEE",
        "JITO_TIP",
        "JITO_TIP_CANDIDATE",
        "ROUTER_FEE",
        "ROUTER_FEE_CANDIDATE",
        "AXIOM_GLOBAL_FEE",
        "AXIOM_GLOBAL_FEE_CANDIDATE",
        "PUMPFUN_FEE",
        "UNKNOWN",
    )


def test_fee_sources_have_no_duplicates():
    assert len(c.FEE_SOURCES) == len(set(c.FEE_SOURCES))


def test_router_fee_candidate_is_in_fee_sources():
    assert "ROUTER_FEE_CANDIDATE" in c.FEE_SOURCES


def test_axiom_global_fee_candidate_is_in_fee_sources():
    assert "AXIOM_GLOBAL_FEE_CANDIDATE" in c.FEE_SOURCES


def test_jito_tip_candidate_is_in_fee_sources():
    assert "JITO_TIP_CANDIDATE" in c.FEE_SOURCES


# ---------------------------------------------------------------------------
# ROUTE_FAMILIES closed-set
# ---------------------------------------------------------------------------


def test_route_families_match_locked_eight_token_set():
    assert c.ROUTE_FAMILIES == (
        "NO_ROUTER_DETECTED",
        "AXIOM_TRADING_PROGRAM_1",
        "AXIOM_FLASHX8",
        "DEPRECATED_AXIOM",
        "PUMPFUN_DIRECT",
        "PUMPSWAP_DIRECT",
        "UNKNOWN_ROUTER",
        "UNSUPPORTED_ROUTER",
    )


def test_route_families_have_no_duplicates():
    assert len(c.ROUTE_FAMILIES) == len(set(c.ROUTE_FAMILIES))


# ---------------------------------------------------------------------------
# INSTRUCTION_LOCATIONS closed-set
# ---------------------------------------------------------------------------


def test_instruction_locations_match_locked_six_token_set():
    assert c.INSTRUCTION_LOCATIONS == (
        "TOP_LEVEL",
        "INNER",
        "BALANCE_DELTA",
        "TOKEN_BALANCE_DELTA",
        "LOG_ONLY",
        "UNKNOWN",
    )


def test_instruction_locations_have_no_duplicates():
    assert len(c.INSTRUCTION_LOCATIONS) == len(set(c.INSTRUCTION_LOCATIONS))


# ---------------------------------------------------------------------------
# INPUT_KINDS closed-set
# ---------------------------------------------------------------------------


def test_input_kinds_match_locked_three_token_set():
    assert c.INPUT_KINDS == (
        "decoded_tx_jsonl",
        "synthetic_decoded_tx_jsonl",
        "sanitized_real_decoded_tx_jsonl",
    )


def test_input_kinds_have_no_duplicates():
    assert len(c.INPUT_KINDS) == len(set(c.INPUT_KINDS))


# ---------------------------------------------------------------------------
# Solana program ID literals
# ---------------------------------------------------------------------------


def test_compute_budget_program_id_is_locked():
    assert (
        c.COMPUTE_BUDGET_PROGRAM_ID
        == "ComputeBudget111111111111111111111111111111"
    )


def test_system_program_id_is_locked():
    assert c.SYSTEM_PROGRAM_ID == "11111111111111111111111111111111"


def test_token_program_id_is_locked():
    assert (
        c.TOKEN_PROGRAM_ID
        == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    )


def test_active_axiom_router_program_ids_locked_pair():
    assert c.ACTIVE_AXIOM_ROUTER_PROGRAM_IDS == (
        "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzpgbMG6",
        "FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9",
    )


def test_deprecated_axiom_router_program_ids_locked_pair():
    assert c.DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS == (
        "AxiomxSitivYjPjKgJ9XSrdhsydtZssk7TEDam3PxKcC",
        "Axiom3a2w1UbMt2SMgqSvRiuJFTPusDhwKamNgPTeNQ9",
    )


def test_active_and_deprecated_axiom_ids_are_disjoint():
    active = set(c.ACTIVE_AXIOM_ROUTER_PROGRAM_IDS)
    deprecated = set(c.DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS)
    assert active.isdisjoint(deprecated)


def test_known_jito_tip_accounts_is_tuple_of_strings():
    # 24.3 will lock the tip-account literals; 24.1 ships the
    # tuple shape.
    assert isinstance(c.KNOWN_JITO_TIP_ACCOUNTS, tuple)
    for value in c.KNOWN_JITO_TIP_ACCOUNTS:
        assert isinstance(value, str)


# ---------------------------------------------------------------------------
# Forbidden routing / vocabulary tuples
# ---------------------------------------------------------------------------


def test_forbidden_routing_tokens_carry_required_members():
    required = {
        "subscriber",
        "subscriber_channel",
        "public_channel",
        "public_signal",
        "public_dispatch",
        "paid_signal",
        "paid_signals",
        "paid_channel",
        "paid_dispatch",
    }
    assert required.issubset(set(c.STAGE24_FORBIDDEN_ROUTING_TOKENS))


def test_forbidden_vocabulary_includes_next_stage_concepts():
    required = {
        "migration",
        "birdeye",
        "dexscreener",
        "x_api",
        "social",
    }
    assert required.issubset(set(c.STAGE24_FORBIDDEN_VOCABULARY))


def test_forbidden_vocabulary_includes_enforcement_words():
    required = {"enforce", "gate", "block", "blocking"}
    assert required.issubset(set(c.STAGE24_FORBIDDEN_VOCABULARY))


def test_forbidden_vocabulary_does_not_include_stage_24_terms():
    # Stage 24's vocabulary IS axiom / jito / priority_fee /
    # compute_budget / execution_quality. They must NOT be on
    # the forbidden list.
    forbidden = set(c.STAGE24_FORBIDDEN_VOCABULARY)
    assert "axiom" not in forbidden
    assert "jito" not in forbidden
    assert "priority_fee" not in forbidden
    assert "compute_budget" not in forbidden
    assert "execution_quality" not in forbidden


def test_forbidden_vocabulary_words_contains_ath():
    # ``ath`` is a too-short substring for a naive substring
    # scanner (it would also match ``path`` / ``math`` /
    # ``hashlib``). The Stage 24 boundary scanner therefore
    # treats it as a discrete word-level forbidden token.
    assert "ath" in c.STAGE24_FORBIDDEN_VOCABULARY_WORDS


def test_forbidden_vocabulary_has_no_duplicates():
    assert len(c.STAGE24_FORBIDDEN_VOCABULARY) == len(
        set(c.STAGE24_FORBIDDEN_VOCABULARY)
    )


# ---------------------------------------------------------------------------
# Input-reader redaction constants
# ---------------------------------------------------------------------------


def test_forbidden_input_field_substrings_carry_required_members():
    required = {
        "api_key",
        "webhook",
        "rpc_url",
        "password",
        "secret",
        "private_key",
    }
    assert required.issubset(
        set(c.STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS)
    )


def test_forbidden_input_value_substrings_include_url_schemes():
    # URL schemes are constructed via concatenation in constants
    # so the literal substring "h" + "ttp://" does not appear in
    # this source. The test asserts the runtime value carries
    # the scheme.
    for needle in c.STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        assert isinstance(needle, str)
        assert needle != ""
    assert any(
        "ttp://" in needle
        for needle in c.STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS
    )


def test_long_hex_run_min_len_is_40():
    assert c.STAGE24_LONG_HEX_RUN_MIN_LEN == 40
