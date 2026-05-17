"""Stage 21 constants tests."""

from __future__ import annotations

from PHX2.stage21 import constants as c


def test_stage21_version_strings_are_locked():
    assert c.STAGE21_VERSION == "stage21_v0_private_preview_foundation"
    assert c.STAGE21_MINOR_VERSION == "21.1"
    assert c.STAGE21_CONSUMER_CONTRACT_VERSION == "stage21_to_stage22_v0"


def test_safe_for_public_dispatch_is_literal_false():
    # Hardcoded invariant. The literal Python ``False`` value
    # gates any future Stage 21 live dispatch.
    assert c.SAFE_FOR_PUBLIC_DISPATCH is False


def test_default_mode_flags():
    assert c.DEFAULT_DRY_RUN is True
    assert c.DEFAULT_LIVE_PRIVATE is False


def test_private_preview_required_tokens():
    expected = (
        "PHX2 PRIVATE PREVIEW",
        "OPERATOR ONLY",
        "DO NOT FORWARD AS PUBLIC SIGNAL",
    )
    assert c.PRIVATE_PREVIEW_REQUIRED_TOKENS == expected
    assert c.PRIVATE_PREVIEW_BANNER_TEXT == expected[0]
    assert c.PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT == expected[1]
    assert c.PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT == expected[2]


def test_provider_mode_names_closed_set():
    assert {m.value for m in c.ProviderModeName} == {
        "FAKE",
        "REPLAY",
        "LIVE",
    }


def test_sink_mode_names_closed_set():
    assert {m.value for m in c.SinkModeName} == {
        "FAKE",
        "PRIVATE_PREVIEW",
    }


def test_error_code_registry_closed_set_and_named():
    declared = {m.value for m in c.Stage21ErrorCode}
    named = set(c.STAGE21_ERROR_CODE_NAMES.keys())
    assert declared == named, (
        "every Stage 21 error code must appear in "
        "STAGE21_ERROR_CODE_NAMES"
    )
    # All Stage 21 codes are within the E2100..E2199 range.
    for code in declared:
        assert code.startswith("E21"), code
        n = int(code[1:])
        assert 2100 <= n <= 2199, code


def test_warning_code_registry_closed_set_and_named():
    declared = {m.value for m in c.Stage21WarningCode}
    named = set(c.STAGE21_WARNING_CODE_NAMES.keys())
    assert declared == named
    for code in declared:
        assert code.startswith("W21"), code
        n = int(code[1:])
        assert 2100 <= n <= 2199, code


def test_no_duplicate_error_codes():
    seen = set()
    for member in c.Stage21ErrorCode:
        assert member.value not in seen, member.value
        seen.add(member.value)


def test_no_duplicate_warning_codes():
    seen = set()
    for member in c.Stage21WarningCode:
        assert member.value not in seen, member.value
        seen.add(member.value)


def test_active_and_reserved_codes_partition_completely():
    declared = {m.value for m in c.Stage21ErrorCode}
    active = c.CODES_ACTIVE_IN_STAGE_21_1
    reserved = c.CODES_RESERVED_FOR_LATER_STAGE_21
    assert active.isdisjoint(reserved)
    assert active | reserved == declared


def test_active_and_reserved_warnings_partition_completely():
    declared = {m.value for m in c.Stage21WarningCode}
    active = c.WARNINGS_ACTIVE_IN_STAGE_21_1
    reserved = c.WARNINGS_RESERVED_FOR_LATER_STAGE_21
    assert active.isdisjoint(reserved)
    assert active | reserved == declared


def test_no_overlap_with_stage20_codes():
    # Stage 20 codes live at E2001..E20xx and W2001..W20xx.
    # Stage 21 codes must not collide with those.
    for member in c.Stage21ErrorCode:
        assert not member.value.startswith("E20"), member.value
    for member in c.Stage21WarningCode:
        assert not member.value.startswith("W20"), member.value


def test_env_var_name_constants_have_phx2_stage21_prefix():
    all_names = list(c.STAGE21_SECRET_ENV_VARS) + list(
        c.STAGE21_NON_SECRET_ENV_VARS
    )
    assert len(all_names) == len(set(all_names)), (
        "no env var name appears in both the secret and non-secret "
        "tuples"
    )
    for name in all_names:
        assert name.startswith("PHX2_STAGE21_"), name


def test_secret_env_vars_include_webhook_url_and_bot_token():
    # Webhook URLs are secret-class. Bot tokens and chat IDs are
    # secret-class. The constants module is the single source of
    # truth; this test pins the membership so a future drift is
    # caught.
    assert c.ENV_VAR_DISCORD_WEBHOOK_URL in c.STAGE21_SECRET_ENV_VARS
    assert c.ENV_VAR_TELEGRAM_BOT_TOKEN in c.STAGE21_SECRET_ENV_VARS
    assert c.ENV_VAR_TELEGRAM_CHAT_ID in c.STAGE21_SECRET_ENV_VARS
    assert c.ENV_VAR_PROVIDER_API_KEY in c.STAGE21_SECRET_ENV_VARS
    assert c.ENV_VAR_PROVIDER_RPC_URL in c.STAGE21_SECRET_ENV_VARS


def test_non_secret_env_vars_do_not_include_secret_class():
    overlap = set(c.STAGE21_NON_SECRET_ENV_VARS) & set(
        c.STAGE21_SECRET_ENV_VARS
    )
    assert overlap == set()


def test_secret_fingerprint_hex_length_is_twelve():
    assert c.SECRET_FINGERPRINT_HEX_LENGTH == 12


def test_redacted_value_sentinel_present():
    assert c.REDACTED_VALUE_SENTINEL == "<redacted>"


def test_forbidden_routing_tokens_lowercase():
    for token in c.STAGE21_FORBIDDEN_ROUTING_TOKENS:
        assert token == token.lower(), token
        assert "subscriber" in token or "public" in token or "paid" in token


def test_default_max_events_per_run_positive_int():
    assert isinstance(c.DEFAULT_MAX_EVENTS_PER_RUN, int)
    assert c.DEFAULT_MAX_EVENTS_PER_RUN > 0
