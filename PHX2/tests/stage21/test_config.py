"""Stage 21 config tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.config import (
    Stage21Config,
    known_env_var_names,
    load_config,
    load_config_for_fake_mode,
)
from PHX2.stage21.constants import (
    DEFAULT_DRY_RUN,
    DEFAULT_LIVE_PRIVATE,
    ENV_VAR_ALLOWLIST_OPERATOR_IDS,
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_DRY_RUN,
    ENV_VAR_LIVE_PRIVATE,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_MODE,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_SINK_MODE,
    ENV_VAR_TELEGRAM_BOT_TOKEN,
    ENV_VAR_TELEGRAM_CHAT_ID,
    ProviderModeName,
    SAFE_FOR_PUBLIC_DISPATCH,
    SinkModeName,
    STAGE21_MINOR_VERSION,
    STAGE21_NON_SECRET_ENV_VARS,
    STAGE21_SECRET_ENV_VARS,
    STAGE21_VERSION,
)
from PHX2.stage21.credential_attestation import CredentialAttestation
from PHX2.stage21.errors import Stage21ConfigError
from PHX2.stage21.secret_redaction import SecretRef


SAMPLE_SECRET = "phx2-stage21-test-fake-secret-VALUE-12345"


def test_load_config_for_fake_mode_succeeds_without_real_secrets():
    config = load_config_for_fake_mode()
    assert isinstance(config, Stage21Config)
    assert config.provider_mode == ProviderModeName.FAKE
    assert config.sink_mode == SinkModeName.FAKE
    assert config.dry_run is DEFAULT_DRY_RUN
    assert config.live_private is DEFAULT_LIVE_PRIVATE
    assert config.safe_for_public_dispatch is False
    for ref in config.secret_refs():
        assert ref.present is False
        assert ref.length == 0
        assert ref.fingerprint == ""
    assert config.allowlist.fail_closed is True


def test_load_config_with_empty_env_equivalent_to_fake_mode():
    config_empty = load_config(env={})
    config_fake = load_config_for_fake_mode()
    assert config_empty == config_fake


def test_load_config_does_not_touch_real_environ_when_env_passed(monkeypatch):
    # Set a real env var; if load_config(env={}) is correct it
    # must NOT read this value. We pin the behavior by setting a
    # value and asserting the resulting Stage21Config has no
    # matching present ref.
    monkeypatch.setenv(ENV_VAR_PROVIDER_API_KEY, "should-not-be-read")
    config = load_config(env={})
    assert config.provider_api_key.present is False


def test_load_config_reads_provider_mode_and_sink_mode():
    config = load_config(env={
        ENV_VAR_PROVIDER_MODE: "FAKE",
        ENV_VAR_SINK_MODE: "FAKE",
    })
    assert config.provider_mode == ProviderModeName.FAKE
    assert config.sink_mode == SinkModeName.FAKE


def test_load_config_invalid_provider_mode_raises_e2101():
    with pytest.raises(Stage21ConfigError) as excinfo:
        load_config(env={ENV_VAR_PROVIDER_MODE: "GARBAGE"})
    assert excinfo.value.code == "E2101"


def test_load_config_invalid_sink_mode_raises_e2101():
    with pytest.raises(Stage21ConfigError) as excinfo:
        load_config(env={ENV_VAR_SINK_MODE: "PUBLIC"})
    assert excinfo.value.code == "E2101"


def test_load_config_invalid_dry_run_raises_e2101():
    with pytest.raises(Stage21ConfigError) as excinfo:
        load_config(env={ENV_VAR_DRY_RUN: "maybe"})
    assert excinfo.value.code == "E2101"


def test_load_config_parses_truthy_dry_run_and_live_private():
    config = load_config(env={
        ENV_VAR_DRY_RUN: "no",
        ENV_VAR_LIVE_PRIVATE: "yes",
    })
    assert config.dry_run is False
    assert config.live_private is True


def test_load_config_with_secrets_builds_secret_refs():
    config = load_config(env={
        ENV_VAR_PROVIDER_API_KEY: SAMPLE_SECRET,
        ENV_VAR_DISCORD_WEBHOOK_URL: "https://example.invalid/hook/abc",
    })
    assert config.provider_api_key.present is True
    assert config.provider_api_key.fingerprint != ""
    assert config.discord_webhook_url.present is True
    assert config.discord_webhook_url.fingerprint != ""
    # The other slots stay missing.
    assert config.provider_rpc_url.present is False


def test_load_config_with_allowlist_env():
    config = load_config(env={
        ENV_VAR_ALLOWLIST_OPERATOR_IDS: "alice,bob",
    })
    assert config.allowlist.recipients == ("alice", "bob")
    assert config.allowlist.fail_closed is False


def test_stage21_config_public_summary_has_no_raw_secret():
    config = load_config(env={
        ENV_VAR_PROVIDER_API_KEY: SAMPLE_SECRET,
        ENV_VAR_DISCORD_WEBHOOK_URL: "https://example.invalid/" + SAMPLE_SECRET,
        ENV_VAR_TELEGRAM_BOT_TOKEN: SAMPLE_SECRET + "-bot",
        ENV_VAR_TELEGRAM_CHAT_ID: SAMPLE_SECRET + "-chat",
        ENV_VAR_ALLOWLIST_OPERATOR_IDS: "alice,bob",
    })
    summary = config.public_summary()

    def _has_secret(value: object) -> bool:
        if isinstance(value, str):
            return SAMPLE_SECRET in value
        if isinstance(value, dict):
            return any(_has_secret(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(_has_secret(v) for v in value)
        return False

    assert not _has_secret(summary)


def test_stage21_config_public_summary_carries_locked_dispatch_flag():
    config = load_config(env={})
    summary = config.public_summary()
    assert summary["safe_for_public_dispatch"] is False
    assert summary["safe_for_public_dispatch"] is SAFE_FOR_PUBLIC_DISPATCH
    assert summary["stage21_version"] == STAGE21_VERSION
    assert summary["stage21_minor_version"] == STAGE21_MINOR_VERSION


def test_credential_attestations_are_sorted_by_name_and_typed():
    config = load_config(env={
        ENV_VAR_PROVIDER_API_KEY: SAMPLE_SECRET,
    })
    attestations = config.credential_attestations()
    names = [a.name for a in attestations]
    assert names == sorted(names)
    for a in attestations:
        assert isinstance(a, CredentialAttestation)


def test_secret_refs_typed_and_in_locked_order():
    config = load_config_for_fake_mode()
    refs = config.secret_refs()
    assert len(refs) == 5
    for ref in refs:
        assert isinstance(ref, SecretRef)
    # The order of the tuple is locked by the config module so the
    # attestation bundle and downstream telemetry have a stable
    # iteration order.
    names = [r.name for r in refs]
    assert names == [
        ENV_VAR_PROVIDER_API_KEY,
        ENV_VAR_PROVIDER_RPC_URL,
        ENV_VAR_DISCORD_WEBHOOK_URL,
        ENV_VAR_TELEGRAM_BOT_TOKEN,
        ENV_VAR_TELEGRAM_CHAT_ID,
    ]


def test_known_env_var_names_returns_union_of_secret_and_non_secret():
    names = known_env_var_names()
    assert set(names) == set(STAGE21_SECRET_ENV_VARS) | set(
        STAGE21_NON_SECRET_ENV_VARS
    )
    # Names are sorted for deterministic emission.
    assert list(names) == sorted(names)
