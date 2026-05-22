"""Stage 27.1 secrets-readiness tests.

Every test uses obvious fake canary secret values; no real keys
are read from ``os.environ``. Each canary value is asserted not to
appear in any redacted readiness summary, repr, or error message.

Pins:

  * ``detect_field_presence`` correctly classifies PRESENT /
    MISSING / MALFORMED for each Stage 27 expected field.
  * ``detect_field_presence`` never stores a raw secret value on
    a SECRET-kind field record.
  * Format validation honors the closed-set malformed reasons.
  * Bulk readiness aggregation correctly partitions
    required-LIVE missing vs malformed.
  * Redacted summary lines never contain any canary secret value.
  * Empty values are classified MALFORMED with reason EMPTY_VALUE.
"""

from __future__ import annotations

import pytest

from PHX2.stage27.live_config_models import (
    CONFIG_FIELD_KIND_CONFIG,
    CONFIG_FIELD_KIND_SECRET,
    MALFORMED_REASON_EMPTY,
    MALFORMED_REASON_NOT_BOOL_LITERAL,
    MALFORMED_REASON_NOT_HTTPS_URL,
    MALFORMED_REASON_NOT_INT,
    MALFORMED_REASON_NOT_POSITIVE_INT,
    MALFORMED_REASON_NO_HOST_PORT,
    SECRET_PRESENCE_MALFORMED,
    SECRET_PRESENCE_MISSING,
    SECRET_PRESENCE_PRESENT,
    STAGE27_ALL_FIELD_NAMES,
    STAGE27_BIRDEYE_API_KEY_NAME,
    STAGE27_HELIUS_API_KEY_NAME,
    STAGE27_HELIUS_GRPC_ENDPOINT_NAME,
    STAGE27_HELIUS_RPC_URL_NAME,
    STAGE27_LIVE_MODE_ALLOWED_NAME,
    STAGE27_LIVE_REQUIRED_FIELD_NAMES,
    STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME,
    STAGE27_PROVIDER_ID_NAME,
    STAGE27_REDACTION_TOKEN,
    STAGE27_RUNNER_MAX_EVENTS_NAME,
    STAGE27_RUNNER_MAX_SECONDS_NAME,
    STAGE27_SCRATCH_DIR_NAME,
    Stage27LiveModeAuthority,
    Stage27RunIdentity,
)
from PHX2.stage27.live_secrets_readiness import (
    build_redacted_readiness_summary,
    detect_all_stage27_field_presence,
    detect_field_presence,
    env_flag_is_truthy_from_record,
)


# ---------------------------------------------------------------------------
# Canary fake-secret fixtures
# ---------------------------------------------------------------------------


# Distinctive, obviously fake canary values. The Stage 27 redaction
# discipline asserts no readiness summary, repr, or error ever
# carries these substrings.
CANARY_HELIUS_API_KEY: str = "CANARY_FAKE_HELIUS_API_KEY_aaaaaa1111"
CANARY_HELIUS_RPC_URL: str = "https://canary.fake.test/helius/rpc?aaa=111"
CANARY_HELIUS_GRPC_ENDPOINT: str = "canary.fake.test:1234"
CANARY_BIRDEYE_API_KEY: str = "CANARY_FAKE_BIRDEYE_API_KEY_bbbbbb2222"
CANARY_DISCORD_WEBHOOK_URL: str = (
    "https://canary.fake.test/webhooks/777/CANARY_FAKE_WEBHOOK_TOKEN_cccccc3333"
)
CANARY_SCRATCH_DIR: str = "/tmp/canary-stage27-scratch"
CANARY_LIVE_MODE_ALLOWED: str = "1"
CANARY_PROVIDER_ID: str = "canary-helius-test"
CANARY_RUNNER_MAX_EVENTS: str = "50"
CANARY_RUNNER_MAX_SECONDS: str = "120"


def _full_canary_env() -> dict[str, str]:
    """Return a complete, well-formed canary env mapping.

    Every Stage 27 expected name is populated. None of these
    values are real secrets.
    """
    return {
        STAGE27_HELIUS_API_KEY_NAME: CANARY_HELIUS_API_KEY,
        STAGE27_HELIUS_RPC_URL_NAME: CANARY_HELIUS_RPC_URL,
        STAGE27_HELIUS_GRPC_ENDPOINT_NAME: CANARY_HELIUS_GRPC_ENDPOINT,
        STAGE27_BIRDEYE_API_KEY_NAME: CANARY_BIRDEYE_API_KEY,
        STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME: CANARY_DISCORD_WEBHOOK_URL,
        STAGE27_SCRATCH_DIR_NAME: CANARY_SCRATCH_DIR,
        STAGE27_LIVE_MODE_ALLOWED_NAME: CANARY_LIVE_MODE_ALLOWED,
        STAGE27_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        STAGE27_RUNNER_MAX_EVENTS_NAME: CANARY_RUNNER_MAX_EVENTS,
        STAGE27_RUNNER_MAX_SECONDS_NAME: CANARY_RUNNER_MAX_SECONDS,
    }


_ALL_CANARY_SECRET_VALUES: tuple[str, ...] = (
    CANARY_HELIUS_API_KEY,
    CANARY_HELIUS_RPC_URL,
    CANARY_HELIUS_GRPC_ENDPOINT,
    CANARY_BIRDEYE_API_KEY,
    CANARY_DISCORD_WEBHOOK_URL,
)


def _assert_no_canary_secret_appears(text: str) -> None:
    for needle in _ALL_CANARY_SECRET_VALUES:
        assert needle not in text, (
            f"canary secret value leaked into a redaction-protected "
            f"surface: {needle!r}"
        )


# ---------------------------------------------------------------------------
# Per-field detection: PRESENT happy paths
# ---------------------------------------------------------------------------


def test_detect_field_presence_secret_happy_path():
    env = _full_canary_env()
    record = detect_field_presence(STAGE27_HELIUS_API_KEY_NAME, env=env)
    assert record.name == STAGE27_HELIUS_API_KEY_NAME
    assert record.kind == CONFIG_FIELD_KIND_SECRET
    assert record.presence_status == SECRET_PRESENCE_PRESENT
    # Raw secret value is never stored on a SECRET record.
    assert record.safe_value is None
    assert record.value_length == len(CANARY_HELIUS_API_KEY)
    _assert_no_canary_secret_appears(repr(record))


def test_detect_field_presence_config_happy_path():
    env = _full_canary_env()
    record = detect_field_presence(STAGE27_PROVIDER_ID_NAME, env=env)
    assert record.name == STAGE27_PROVIDER_ID_NAME
    assert record.kind == CONFIG_FIELD_KIND_CONFIG
    assert record.presence_status == SECRET_PRESENCE_PRESENT
    # CONFIG kind: the safe value IS stored because it is intentionally non-secret.
    assert record.safe_value == CANARY_PROVIDER_ID
    assert record.value_length == len(CANARY_PROVIDER_ID)


# ---------------------------------------------------------------------------
# Per-field detection: MISSING
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", STAGE27_ALL_FIELD_NAMES)
def test_detect_field_presence_missing_when_env_omits(name):
    record = detect_field_presence(name, env={})
    assert record.presence_status == SECRET_PRESENCE_MISSING
    assert record.safe_value is None
    assert record.value_length is None


def test_detect_field_presence_unknown_name_raises():
    with pytest.raises(ValueError):
        detect_field_presence("NOT_A_REAL_NAME", env={})


# ---------------------------------------------------------------------------
# Per-field detection: MALFORMED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", STAGE27_ALL_FIELD_NAMES)
def test_empty_value_is_malformed_empty(name):
    record = detect_field_presence(name, env={name: ""})
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_EMPTY
    assert record.safe_value is None


def test_helius_rpc_url_requires_http_or_https():
    env = _full_canary_env()
    env[STAGE27_HELIUS_RPC_URL_NAME] = "ftp://example.test/rpc"
    record = detect_field_presence(STAGE27_HELIUS_RPC_URL_NAME, env=env)
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_HTTPS_URL


def test_discord_webhook_requires_https():
    env = _full_canary_env()
    env[STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME] = "http://example.test/hook"
    record = detect_field_presence(
        STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_HTTPS_URL


def test_grpc_endpoint_requires_host_port_or_url():
    env = _full_canary_env()
    env[STAGE27_HELIUS_GRPC_ENDPOINT_NAME] = "no-colon-here"
    record = detect_field_presence(
        STAGE27_HELIUS_GRPC_ENDPOINT_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NO_HOST_PORT


def test_grpc_endpoint_with_url_scheme_is_present():
    env = _full_canary_env()
    env[STAGE27_HELIUS_GRPC_ENDPOINT_NAME] = "https://canary.test/grpc"
    record = detect_field_presence(
        STAGE27_HELIUS_GRPC_ENDPOINT_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_PRESENT


def test_live_mode_allowed_requires_bool_literal():
    env = _full_canary_env()
    env[STAGE27_LIVE_MODE_ALLOWED_NAME] = "maybe"
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_BOOL_LITERAL


@pytest.mark.parametrize("literal", [
    "1", "0", "true", "false", "TRUE", "FALSE", "yes", "no",
])
def test_live_mode_allowed_accepts_bool_literals(literal):
    env = _full_canary_env()
    env[STAGE27_LIVE_MODE_ALLOWED_NAME] = literal
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_PRESENT


def test_runner_max_events_must_be_int():
    env = _full_canary_env()
    env[STAGE27_RUNNER_MAX_EVENTS_NAME] = "many"
    record = detect_field_presence(
        STAGE27_RUNNER_MAX_EVENTS_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_INT


def test_runner_max_events_must_be_positive():
    env = _full_canary_env()
    env[STAGE27_RUNNER_MAX_EVENTS_NAME] = "0"
    record = detect_field_presence(
        STAGE27_RUNNER_MAX_EVENTS_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_POSITIVE_INT


def test_runner_max_seconds_must_be_positive():
    env = _full_canary_env()
    env[STAGE27_RUNNER_MAX_SECONDS_NAME] = "-3"
    record = detect_field_presence(
        STAGE27_RUNNER_MAX_SECONDS_NAME, env=env
    )
    assert record.presence_status == SECRET_PRESENCE_MALFORMED
    assert record.malformed_reason == MALFORMED_REASON_NOT_POSITIVE_INT


# ---------------------------------------------------------------------------
# Bulk readiness aggregation
# ---------------------------------------------------------------------------


def test_bulk_readiness_all_present_aggregates_to_live_ready():
    env = _full_canary_env()
    report = detect_all_stage27_field_presence(env=env)
    assert len(report.fields) == len(STAGE27_ALL_FIELD_NAMES)
    assert report.required_live_missing == ()
    assert report.required_live_malformed == ()
    assert report.all_required_live_present is True


def test_bulk_readiness_missing_live_required_blocks_live():
    env = _full_canary_env()
    del env[STAGE27_HELIUS_API_KEY_NAME]
    del env[STAGE27_PROVIDER_ID_NAME]
    report = detect_all_stage27_field_presence(env=env)
    assert STAGE27_HELIUS_API_KEY_NAME in report.required_live_missing
    assert STAGE27_PROVIDER_ID_NAME in report.required_live_missing
    assert report.all_required_live_present is False


def test_bulk_readiness_malformed_live_required_blocks_live():
    env = _full_canary_env()
    env[STAGE27_HELIUS_RPC_URL_NAME] = "ftp://bad/rpc"
    report = detect_all_stage27_field_presence(env=env)
    assert STAGE27_HELIUS_RPC_URL_NAME in report.required_live_malformed
    assert report.all_required_live_present is False


def test_bulk_readiness_missing_optional_does_not_block_live():
    env = _full_canary_env()
    del env[STAGE27_SCRATCH_DIR_NAME]
    del env[STAGE27_RUNNER_MAX_EVENTS_NAME]
    report = detect_all_stage27_field_presence(env=env)
    # Optional CONFIG fields are not required for LIVE; their
    # absence is recorded but does not move the aggregate flag.
    assert report.all_required_live_present is True


def test_bulk_readiness_completely_empty_env():
    report = detect_all_stage27_field_presence(env={})
    assert set(report.required_live_missing) == set(
        STAGE27_LIVE_REQUIRED_FIELD_NAMES
    )
    assert report.required_live_malformed == ()
    assert report.all_required_live_present is False


# ---------------------------------------------------------------------------
# env_flag_is_truthy_from_record
# ---------------------------------------------------------------------------


def test_env_flag_truthy_when_present_and_truthy_literal():
    env = _full_canary_env()
    env[STAGE27_LIVE_MODE_ALLOWED_NAME] = "true"
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME, env=env
    )
    assert env_flag_is_truthy_from_record(record) is True


def test_env_flag_falsy_when_value_is_falsy_literal():
    env = _full_canary_env()
    env[STAGE27_LIVE_MODE_ALLOWED_NAME] = "false"
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME, env=env
    )
    assert env_flag_is_truthy_from_record(record) is False


def test_env_flag_falsy_when_missing():
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME, env={}
    )
    assert env_flag_is_truthy_from_record(record) is False


def test_env_flag_falsy_when_malformed():
    record = detect_field_presence(
        STAGE27_LIVE_MODE_ALLOWED_NAME,
        env={STAGE27_LIVE_MODE_ALLOWED_NAME: "maybe"},
    )
    # MALFORMED is conservative fail-closed: env_flag treated as falsy.
    assert env_flag_is_truthy_from_record(record) is False


def test_env_flag_helper_rejects_wrong_record_name():
    record = detect_field_presence(STAGE27_HELIUS_API_KEY_NAME, env={})
    with pytest.raises(ValueError):
        env_flag_is_truthy_from_record(record)


# ---------------------------------------------------------------------------
# Redacted readiness summary
# ---------------------------------------------------------------------------


def _build_authority(resolved: str = "LIVE_ALLOWED") -> Stage27LiveModeAuthority:
    return Stage27LiveModeAuthority(
        resolved=resolved,
        env_flag_set=True,
        cli_live_requested=True,
        required_live_secrets_present=(resolved == "LIVE_ALLOWED"),
        reason_code="BOTH_FACTORS_AND_SECRETS_OK"
        if resolved == "LIVE_ALLOWED"
        else "ONE_FACTOR_ENV_ONLY",
    )


def _build_identity(mode: str = "LIVE_ALLOWED") -> Stage27RunIdentity:
    return Stage27RunIdentity(
        session_id="canary-session",
        run_id="canary-run-1234",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=mode,
        stage="stage27",
        substage="27.1",
        schema_version="stage27_v0_operator_config",
    )


def test_redacted_summary_emits_redaction_token_for_secret_present():
    env = _full_canary_env()
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_ALLOWED"),
        identity=_build_identity("LIVE_ALLOWED"),
    )
    combined = "\n".join(summary.lines)
    assert STAGE27_REDACTION_TOKEN in combined
    _assert_no_canary_secret_appears(combined)


def test_redacted_summary_carries_safe_config_value():
    env = _full_canary_env()
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_ALLOWED"),
        identity=_build_identity("LIVE_ALLOWED"),
    )
    combined = "\n".join(summary.lines)
    # CONFIG safe values are allowed to appear because they are
    # not secrets.
    assert CANARY_PROVIDER_ID in combined
    assert CANARY_SCRATCH_DIR in combined


def test_redacted_summary_handles_missing_secret():
    env = _full_canary_env()
    del env[STAGE27_HELIUS_API_KEY_NAME]
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_REFUSED"),
        identity=_build_identity("LIVE_REFUSED"),
    )
    combined = "\n".join(summary.lines)
    assert "<missing>" in combined
    _assert_no_canary_secret_appears(combined)


def test_redacted_summary_handles_malformed_secret():
    env = _full_canary_env()
    env[STAGE27_HELIUS_RPC_URL_NAME] = "ftp://canary.test/rpc"
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_REFUSED"),
        identity=_build_identity("LIVE_REFUSED"),
    )
    combined = "\n".join(summary.lines)
    assert "<malformed:NOT_HTTPS_URL>" in combined
    # The malformed value itself must not leak.
    assert "ftp://canary.test/rpc" not in combined


def test_redacted_summary_mode_label_carries_resolved_authority():
    env = _full_canary_env()
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_ALLOWED"),
        identity=_build_identity("LIVE_ALLOWED"),
    )
    assert summary.mode_label == "LIVE_ALLOWED"


def test_redacted_summary_redaction_token_matches_constant():
    env = _full_canary_env()
    report = detect_all_stage27_field_presence(env=env)
    summary = build_redacted_readiness_summary(
        report=report,
        authority=_build_authority("LIVE_ALLOWED"),
        identity=_build_identity("LIVE_ALLOWED"),
    )
    assert summary.redaction_token == STAGE27_REDACTION_TOKEN
