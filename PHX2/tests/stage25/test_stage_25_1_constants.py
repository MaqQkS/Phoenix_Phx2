"""Stage 25.1 constants tests.

Pins every Stage 25 closed-set tuple, version axis, tolerance
literal, and boundary-scanner input. Any drift in a token, an
ordering, or the size of a set fails here.
"""

from __future__ import annotations

import pytest

from PHX2.stage25 import constants as c


# ---------------------------------------------------------------------------
# Version / stage axes
# ---------------------------------------------------------------------------


def test_stage_name_token_is_locked():
    assert c.STAGE_NAME == "stage25"


def test_stage_version_axis_is_locked():
    assert c.STAGE_VERSION == "25.1"
    assert c.STAGE25_MINOR_VERSION == "25.1"


def test_stage25_version_full_string_is_locked():
    assert c.STAGE25_VERSION == "stage25_v0_measurement_foundation"


def test_default_schema_version_is_locked():
    assert c.DEFAULT_SCHEMA_VERSION == "stage25_v0_measurement"


def test_manifest_schema_version_is_locked():
    assert c.STAGE25_MANIFEST_SCHEMA_VERSION == "stage25_v0_manifest"


def test_observe_only_mode_token_is_locked():
    assert c.OBSERVE_ONLY_MODE == "observe_only"


def test_default_threshold_version_is_locked():
    assert c.DEFAULT_THRESHOLD_VERSION == "thresholds_v0_observe_only"


def test_redaction_confirmed_token_is_locked():
    assert c.REDACTION_CONFIRMED_TOKEN == "stage25_redaction_confirmed"


# ---------------------------------------------------------------------------
# MEASUREMENT_FAMILIES closed-set
# ---------------------------------------------------------------------------


def test_measurement_families_match_locked_two_token_set():
    assert c.MEASUREMENT_FAMILIES == ("MIGRATION", "ATH")


def test_measurement_families_have_no_duplicates():
    assert len(c.MEASUREMENT_FAMILIES) == len(set(c.MEASUREMENT_FAMILIES))


def test_each_measurement_family_constant_appears_in_tuple():
    expected = {
        c.MEASUREMENT_FAMILY_MIGRATION,
        c.MEASUREMENT_FAMILY_ATH,
    }
    assert expected == set(c.MEASUREMENT_FAMILIES)


# ---------------------------------------------------------------------------
# SOURCE_FAMILIES closed-set
# ---------------------------------------------------------------------------


def test_source_families_match_locked_five_token_set():
    assert c.SOURCE_FAMILIES == (
        "BIRDEYE",
        "DEXSCREENER",
        "ON_CHAIN_SWAP_REPLAY",
        "WEBSOCKET_CAPTURE",
        "UNKNOWN_SOURCE",
    )


def test_source_families_have_no_duplicates():
    assert len(c.SOURCE_FAMILIES) == len(set(c.SOURCE_FAMILIES))


# ---------------------------------------------------------------------------
# SOURCE_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_source_statuses_match_locked_seven_token_set():
    assert c.SOURCE_STATUSES == (
        "PRESENT",
        "ABSENT",
        "PARTIAL",
        "UNSUPPORTED",
        "AMBIGUOUS",
        "MALFORMED",
        "DECODE_FAILED",
    )


def test_source_statuses_have_no_duplicates():
    assert len(c.SOURCE_STATUSES) == len(set(c.SOURCE_STATUSES))


# ---------------------------------------------------------------------------
# MEASUREMENT_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_measurement_statuses_match_locked_eight_token_set():
    assert c.MEASUREMENT_STATUSES == (
        "MEASURED",
        "PARTIAL",
        "UNSUPPORTED",
        "AMBIGUOUS",
        "SOURCE_CONFLICT",
        "MISSING",
        "REJECTED",
        "NOT_APPLICABLE",
    )


def test_measurement_statuses_have_no_duplicates():
    assert len(c.MEASUREMENT_STATUSES) == len(set(c.MEASUREMENT_STATUSES))


# ---------------------------------------------------------------------------
# CONFIDENCE_LEVELS closed-set
# ---------------------------------------------------------------------------


def test_confidence_levels_match_locked_four_token_set():
    assert c.CONFIDENCE_LEVELS == ("HIGH", "MEDIUM", "LOW", "NONE")


def test_confidence_levels_have_no_duplicates():
    assert len(c.CONFIDENCE_LEVELS) == len(set(c.CONFIDENCE_LEVELS))


# ---------------------------------------------------------------------------
# REJECTION_REASONS closed-set
# ---------------------------------------------------------------------------


def test_rejection_reasons_carry_required_members():
    required = {
        "INPUT_MALFORMED",
        "FORBIDDEN_FIELD_SUBSTRING",
        "FORBIDDEN_VALUE_SUBSTRING",
        "LONG_HEX_RUN_DETECTED",
        "UNKNOWN_INPUT_KIND",
        "UNKNOWN_SOURCE_FAMILY",
        "SOURCE_BUILDER_TYPED_ERROR",
        "MIGRATION_AMBIGUOUS_BLOCKS_ATH",
        "PRE_MIGRATION_OBSERVATION_USED_FOR_ATH",
        "ZERO_PRICE_WITHOUT_EXPLICIT_OBSERVED_ZERO",
        "NEGATIVE_PRICE",
        "NON_FINITE_PRICE",
        "DUPLICATE_OBSERVATION",
        "NULL_REQUIRES_EXPLICIT_STATUS",
    }
    assert required.issubset(set(c.REJECTION_REASONS))


def test_rejection_reasons_have_no_duplicates():
    assert len(c.REJECTION_REASONS) == len(set(c.REJECTION_REASONS))


# ---------------------------------------------------------------------------
# PRICE_WINDOW_KINDS closed-set
# ---------------------------------------------------------------------------


def test_price_window_kinds_match_locked_four_token_set():
    assert c.PRICE_WINDOW_KINDS == (
        "POST_MIGRATION_PRIMARY",
        "POST_MIGRATION_EXTENDED",
        "PRE_MIGRATION_EXCLUDED",
        "UNKNOWN_WINDOW",
    )


# ---------------------------------------------------------------------------
# ATH_CANDIDATE_KINDS closed-set
# ---------------------------------------------------------------------------


def test_ath_candidate_kinds_match_locked_four_token_set():
    assert c.ATH_CANDIDATE_KINDS == (
        "SOURCE_REPORTED_PEAK",
        "SWAP_REPLAY_PEAK",
        "COMBINED_PEAK",
        "INSUFFICIENT_DATA",
    )


# ---------------------------------------------------------------------------
# RECONCILIATION_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_reconciliation_statuses_match_locked_six_token_set():
    assert c.RECONCILIATION_STATUSES == (
        "AGREED",
        "DISAGREED_MINOR",
        "DISAGREED_MAJOR",
        "SINGLE_SOURCE",
        "NO_SOURCES",
        "AMBIGUOUS",
    )


def test_reconciliation_statuses_have_no_duplicates():
    assert len(c.RECONCILIATION_STATUSES) == len(
        set(c.RECONCILIATION_STATUSES)
    )


# ---------------------------------------------------------------------------
# QUOTE_DENOMINATIONS closed-set
# ---------------------------------------------------------------------------


def test_quote_denominations_match_locked_three_token_set():
    assert c.QUOTE_DENOMINATIONS == (
        "USD_MICRO",
        "SOL_LAMPORTS",
        "UNKNOWN_QUOTE",
    )


# ---------------------------------------------------------------------------
# INPUT_KINDS closed-set
# ---------------------------------------------------------------------------


def test_input_kinds_match_locked_six_token_set():
    assert c.INPUT_KINDS == (
        "migration_observations_jsonl",
        "price_observations_jsonl",
        "synthetic_migration_observations_jsonl",
        "synthetic_price_observations_jsonl",
        "sanitized_real_migration_observations_jsonl",
        "sanitized_real_price_observations_jsonl",
    )


def test_input_kinds_have_no_duplicates():
    assert len(c.INPUT_KINDS) == len(set(c.INPUT_KINDS))


def test_migration_input_kind_partition_complements_price_partition():
    union = set(c.MIGRATION_OBSERVATION_INPUT_KINDS) | set(
        c.PRICE_OBSERVATION_INPUT_KINDS
    )
    assert union == set(c.INPUT_KINDS)
    intersection = set(c.MIGRATION_OBSERVATION_INPUT_KINDS) & set(
        c.PRICE_OBSERVATION_INPUT_KINDS
    )
    assert intersection == set()


# ---------------------------------------------------------------------------
# Tolerances / sentinels
# ---------------------------------------------------------------------------


def test_migration_timestamp_tolerance_seconds_is_60():
    assert c.MIGRATION_TIMESTAMP_TOLERANCE_SECONDS == 60


def test_peak_time_tolerance_seconds_is_120():
    assert c.PEAK_TIME_TOLERANCE_SECONDS == 120


def test_price_disagreement_tolerance_ppm_is_50000():
    assert c.PRICE_DISAGREEMENT_TOLERANCE_PPM == 50_000


def test_post_migration_primary_window_seconds_is_six_hours():
    assert c.POST_MIGRATION_PRIMARY_WINDOW_SECONDS == 6 * 3600


def test_long_hex_run_min_len_is_40():
    assert c.STAGE25_LONG_HEX_RUN_MIN_LEN == 40


# ---------------------------------------------------------------------------
# Forbidden vocabulary / routing tuples
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
    assert required.issubset(set(c.STAGE25_FORBIDDEN_ROUTING_TOKENS))


def test_forbidden_vocabulary_includes_transport_and_scheduler_tokens():
    required = {
        "dispatch",
        "telegram",
        "scheduler",
        "daemon",
        "worker",
        "run_loop",
        "x_api",
        "social",
    }
    assert required.issubset(set(c.STAGE25_FORBIDDEN_VOCABULARY))


def test_forbidden_vocabulary_does_not_falsely_ban_stage25_terms():
    forbidden = set(c.STAGE25_FORBIDDEN_VOCABULARY)
    for stage25_word in (
        "migration",
        "birdeye",
        "dexscreener",
        "ath",
        "peak",
        "source",
        "reconciliation",
        "candidate",
        "price",
        "window",
        "measurement",
        "observation",
        "swap_replay",
    ):
        assert stage25_word not in forbidden, (
            f"Stage 25 vocabulary word {stage25_word!r} must not be on "
            "the forbidden list"
        )


def test_forbidden_stage24_execution_fee_vocabulary_locked_four_token_set():
    assert c.STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY == (
        "axiom",
        "jito",
        "compute_budget",
        "router_fee",
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
        set(c.STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS)
    )


def test_forbidden_input_value_substrings_include_url_schemes():
    for needle in c.STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        assert isinstance(needle, str)
        assert needle != ""
    assert any(
        "ttp://" in needle
        for needle in c.STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS
    )


# ---------------------------------------------------------------------------
# REASON_CODES closed-set
# ---------------------------------------------------------------------------


def test_reason_codes_carry_price_observed_zero():
    assert c.REASON_CODE_PRICE_OBSERVED_ZERO == "PRICE_OBSERVED_ZERO"
    assert "PRICE_OBSERVED_ZERO" in c.REASON_CODES


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


def test_assert_measurement_family_accepts_each_member():
    for member in c.MEASUREMENT_FAMILIES:
        c.assert_measurement_family_in_closed_set(member)


def test_assert_measurement_family_rejects_unknown():
    with pytest.raises(ValueError):
        c.assert_measurement_family_in_closed_set("BOGUS_FAMILY")


def test_assert_source_status_rejects_unknown():
    with pytest.raises(ValueError):
        c.assert_source_status_in_closed_set("BOGUS")


def test_assert_quote_denomination_rejects_unknown():
    with pytest.raises(ValueError):
        c.assert_quote_denomination_in_closed_set("BOGUS_QUOTE")


def test_assert_optional_non_negative_int_accepts_none_and_zero():
    c.assert_optional_non_negative_int(field_name="price", value=None)
    c.assert_optional_non_negative_int(field_name="price", value=0)
    c.assert_optional_non_negative_int(field_name="price", value=1_000)


def test_assert_optional_non_negative_int_rejects_bool():
    with pytest.raises(ValueError):
        c.assert_optional_non_negative_int(field_name="price", value=True)


def test_assert_optional_non_negative_int_rejects_negative():
    with pytest.raises(ValueError):
        c.assert_optional_non_negative_int(field_name="price", value=-1)


def test_assert_non_negative_int_or_minus_one_sentinel_accepts_sentinel():
    c.assert_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=-1
    )
    c.assert_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=0
    )
    c.assert_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=12345
    )


def test_assert_non_negative_int_or_minus_one_sentinel_rejects_minus_two():
    with pytest.raises(ValueError):
        c.assert_non_negative_int_or_minus_one_sentinel(
            field_name="slot", value=-2
        )


def test_assert_non_negative_int_or_minus_one_sentinel_rejects_bool():
    with pytest.raises(ValueError):
        c.assert_non_negative_int_or_minus_one_sentinel(
            field_name="slot", value=True
        )
