"""Stage 23.1 constants tests.

Pins every Stage 23 closed-set tuple, version axis, and
boundary-scanner input. Any drift in a token, an ordering, or
the size of a set fails here.
"""

from __future__ import annotations

from PHX2.stage23 import constants as c


# ---------------------------------------------------------------------------
# Version / stage axes
# ---------------------------------------------------------------------------


def test_stage_name_token_is_locked():
    assert c.STAGE_NAME == "stage23"


def test_stage_version_axis_is_locked():
    assert c.STAGE_VERSION == "23.1"
    assert c.STAGE23_MINOR_VERSION == "23.1"


def test_stage23_version_full_string_is_locked():
    assert c.STAGE23_VERSION == "stage23_v0_observe_only_filter_foundation"


def test_default_schema_version_is_locked():
    assert c.DEFAULT_SCHEMA_VERSION == "stage23_v0_filter_eval"


def test_manifest_schema_version_is_locked():
    assert (
        c.STAGE23_MANIFEST_SCHEMA_VERSION == "stage23_v0_manifest"
    )


def test_observe_only_mode_token_is_locked():
    assert c.OBSERVE_ONLY_MODE == "observe_only"


# ---------------------------------------------------------------------------
# LABELS closed-set
# ---------------------------------------------------------------------------


def test_labels_match_locked_seven_token_set():
    assert c.LABELS == (
        "NORMAL",
        "ELEVATED",
        "SUSPICIOUS",
        "SCAM_LIKELY",
        "UNKNOWN",
        "INSUFFICIENT_DATA",
        "MISSING_INPUT",
    )


def test_labels_have_no_duplicates():
    assert len(c.LABELS) == len(set(c.LABELS))


def test_each_label_constant_appears_in_tuple():
    expected = {
        c.LABEL_NORMAL,
        c.LABEL_ELEVATED,
        c.LABEL_SUSPICIOUS,
        c.LABEL_SCAM_LIKELY,
        c.LABEL_UNKNOWN,
        c.LABEL_INSUFFICIENT_DATA,
        c.LABEL_MISSING_INPUT,
    }
    assert expected == set(c.LABELS)


# ---------------------------------------------------------------------------
# DATA_STATUSES closed-set
# ---------------------------------------------------------------------------


def test_data_statuses_match_locked_four_token_set():
    assert c.DATA_STATUSES == (
        "COMPLETE",
        "PARTIAL",
        "MISSING",
        "UNSUPPORTED",
    )


def test_data_statuses_have_no_duplicates():
    assert len(c.DATA_STATUSES) == len(set(c.DATA_STATUSES))


def test_each_data_status_constant_appears_in_tuple():
    expected = {
        c.DATA_STATUS_COMPLETE,
        c.DATA_STATUS_PARTIAL,
        c.DATA_STATUS_MISSING,
        c.DATA_STATUS_UNSUPPORTED,
    }
    assert expected == set(c.DATA_STATUSES)


# ---------------------------------------------------------------------------
# FILTER_FAMILIES closed-set
# ---------------------------------------------------------------------------


def test_filter_families_match_locked_three_token_set():
    assert c.FILTER_FAMILIES == (
        "HOLDER_CONCENTRATION",
        "LAUNCH_STRUCTURE",
        "WALLET_SOURCE_QUALITY",
    )


def test_filter_families_have_no_duplicates():
    assert len(c.FILTER_FAMILIES) == len(set(c.FILTER_FAMILIES))


def test_each_filter_family_constant_appears_in_tuple():
    expected = {
        c.FILTER_FAMILY_HOLDER_CONCENTRATION,
        c.FILTER_FAMILY_LAUNCH_STRUCTURE,
        c.FILTER_FAMILY_WALLET_SOURCE_QUALITY,
    }
    assert expected == set(c.FILTER_FAMILIES)


# ---------------------------------------------------------------------------
# INPUT_KINDS closed-set
# ---------------------------------------------------------------------------


def test_input_kinds_match_locked_three_token_set():
    assert c.INPUT_KINDS == (
        "raw_capture",
        "dedupe",
        "synthetic",
    )


def test_input_kinds_have_no_duplicates():
    assert len(c.INPUT_KINDS) == len(set(c.INPUT_KINDS))


# ---------------------------------------------------------------------------
# Preserved input fields
# ---------------------------------------------------------------------------


def test_input_preserved_fields_contain_required_concepts():
    required = {
        "provider_id",
        "event_id",
        "captured_event_id",
        "token_mint",
        "slot",
        "signature",
        "observed_at_utc",
        "payload_summary",
    }
    assert required.issubset(set(c.INPUT_PRESERVED_FIELDS))


# ---------------------------------------------------------------------------
# Forbidden vocabulary / routing
# ---------------------------------------------------------------------------


def test_forbidden_routing_tokens_have_no_duplicates():
    assert len(c.STAGE23_FORBIDDEN_ROUTING_TOKENS) == len(
        set(c.STAGE23_FORBIDDEN_ROUTING_TOKENS)
    )


def test_forbidden_vocabulary_has_no_duplicates():
    assert len(c.STAGE23_FORBIDDEN_VOCABULARY) == len(
        set(c.STAGE23_FORBIDDEN_VOCABULARY)
    )


def test_forbidden_input_field_substrings_cover_known_secret_keys():
    required = {
        "api_key",
        "webhook_url",
        "rpc_url",
        "authorization",
        "secret",
        "private_key",
    }
    assert required.issubset(set(c.STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS))


def test_forbidden_input_value_substrings_cover_known_url_shapes():
    # Construct the URL prefixes at runtime so the literal strings
    # never appear in this test file's source.
    colon_slash_slash = ":" + "//"
    https_prefix = "https" + colon_slash_slash
    http_prefix = "http" + colon_slash_slash
    wss_prefix = "wss" + colon_slash_slash
    ws_prefix = "ws" + colon_slash_slash
    discord_host = "discord" + "." + "com"
    discordapp_host = "discordapp" + "." + "com"
    hooks_slack_host = "hooks" + ".slack" + "." + "com"

    required = {
        https_prefix,
        http_prefix,
        wss_prefix,
        ws_prefix,
        colon_slash_slash,
        discord_host,
        discordapp_host,
        hooks_slack_host,
    }
    assert required.issubset(set(c.STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS))


# ---------------------------------------------------------------------------
# Cross-closed-set independence
# ---------------------------------------------------------------------------


def test_labels_and_data_statuses_disjoint():
    assert set(c.LABELS).isdisjoint(set(c.DATA_STATUSES))


def test_labels_and_filter_families_disjoint():
    assert set(c.LABELS).isdisjoint(set(c.FILTER_FAMILIES))


def test_data_statuses_and_filter_families_disjoint():
    assert set(c.DATA_STATUSES).isdisjoint(set(c.FILTER_FAMILIES))


# ---------------------------------------------------------------------------
# Long-token thresholds
# ---------------------------------------------------------------------------


def test_long_token_thresholds_are_locked():
    assert c.STAGE23_LONG_HEX_RUN_MIN_LEN == 40
    assert c.STAGE23_LONG_TOKENISH_MIN_LEN == 32
