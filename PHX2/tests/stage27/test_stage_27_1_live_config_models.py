"""Stage 27.1 live-config models tests.

Pins:

  * Closed-set vocabularies (live-mode authority, reason codes,
    secret presence, malformed reasons, config-field kind) are the
    exact locked tuples.
  * Expected Stage 27 env / config variable name partitions
    (SECRET vs CONFIG, live-required vs optional) are the exact
    locked sets.
  * Stage 27 redaction token is a single distinctive literal.
  * Every NamedTuple is immutable (``setattr`` raises).
  * NamedTuple ``repr()`` of a SECRET-kind ``Stage27ConfigFieldRecord``
    never carries a raw secret value (because the field is
    populated with ``safe_value=None`` by construction).
  * Stage 27.1 schema-version + stage/substage axes are pinned.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from PHX2.stage27 import live_config_models as m


# ---------------------------------------------------------------------------
# Live-mode authority closed set
# ---------------------------------------------------------------------------


def test_live_mode_authority_values_are_locked_tuple():
    assert m.LIVE_MODE_AUTHORITY_VALUES == (
        "DRY_RUN",
        "LIVE_REFUSED",
        "LIVE_ALLOWED",
    )


def test_live_mode_authority_token_constants():
    assert m.LIVE_MODE_AUTHORITY_DRY_RUN == "DRY_RUN"
    assert m.LIVE_MODE_AUTHORITY_LIVE_REFUSED == "LIVE_REFUSED"
    assert m.LIVE_MODE_AUTHORITY_LIVE_ALLOWED == "LIVE_ALLOWED"


def test_live_mode_reason_values_are_locked_tuple():
    assert m.LIVE_MODE_REASON_VALUES == (
        "DEFAULT_DRY_RUN",
        "ONE_FACTOR_ENV_ONLY",
        "ONE_FACTOR_CLI_ONLY",
        "LIVE_SECRETS_MISSING",
        "LIVE_SECRETS_MALFORMED",
        "BOTH_FACTORS_AND_SECRETS_OK",
    )


# ---------------------------------------------------------------------------
# Secret-presence closed set
# ---------------------------------------------------------------------------


def test_secret_presence_values_are_locked_tuple():
    assert m.SECRET_PRESENCE_VALUES == (
        "PRESENT",
        "MISSING",
        "MALFORMED",
    )


def test_malformed_reason_values_are_locked_tuple():
    assert m.MALFORMED_REASON_VALUES == (
        "EMPTY_VALUE",
        "NOT_HTTPS_URL",
        "NOT_INT",
        "NOT_POSITIVE_INT",
        "NOT_BOOL_LITERAL",
        "NO_HOST_PORT",
    )


# ---------------------------------------------------------------------------
# Config-field kind closed set
# ---------------------------------------------------------------------------


def test_config_field_kind_values():
    assert m.CONFIG_FIELD_KIND_SECRET == "SECRET"
    assert m.CONFIG_FIELD_KIND_CONFIG == "CONFIG"
    assert m.CONFIG_FIELD_KIND_VALUES == ("SECRET", "CONFIG")


# ---------------------------------------------------------------------------
# Expected env / config variable names
# ---------------------------------------------------------------------------


def test_stage27_secret_names_locked_tuple():
    assert m.STAGE27_SECRET_NAMES == (
        "HELIUS_API_KEY",
        "HELIUS_RPC_URL",
        "HELIUS_GRPC_ENDPOINT",
        "BIRDEYE_API_KEY",
        "PHX2_PRIVATE_DISCORD_WEBHOOK_URL",
    )


def test_stage27_config_names_locked_tuple():
    assert m.STAGE27_CONFIG_NAMES == (
        "PHX2_STAGE27_SCRATCH_DIR",
        "PHX2_LIVE_MODE_ALLOWED",
        "PHX2_PROVIDER_ID",
        "PHX2_RUNNER_MAX_EVENTS",
        "PHX2_RUNNER_MAX_SECONDS",
    )


def test_stage27_all_field_names_is_concat_of_secret_and_config():
    assert m.STAGE27_ALL_FIELD_NAMES == (
        m.STAGE27_SECRET_NAMES + m.STAGE27_CONFIG_NAMES
    )


def test_stage27_live_required_field_names_locked_tuple():
    assert m.STAGE27_LIVE_REQUIRED_FIELD_NAMES == (
        "HELIUS_API_KEY",
        "HELIUS_RPC_URL",
        "HELIUS_GRPC_ENDPOINT",
        "BIRDEYE_API_KEY",
        "PHX2_PRIVATE_DISCORD_WEBHOOK_URL",
        "PHX2_PROVIDER_ID",
    )


def test_stage27_secret_and_config_name_sets_are_disjoint():
    assert (
        set(m.STAGE27_SECRET_NAMES) & set(m.STAGE27_CONFIG_NAMES)
        == set()
    )


@pytest.mark.parametrize("name", [
    "HELIUS_API_KEY",
    "HELIUS_RPC_URL",
    "HELIUS_GRPC_ENDPOINT",
    "BIRDEYE_API_KEY",
    "PHX2_PRIVATE_DISCORD_WEBHOOK_URL",
])
def test_is_secret_name_true_for_each_secret(name):
    assert m.is_secret_name(name) is True
    assert m.is_config_name(name) is False
    assert m.field_kind_for_name(name) == "SECRET"


@pytest.mark.parametrize("name", [
    "PHX2_STAGE27_SCRATCH_DIR",
    "PHX2_LIVE_MODE_ALLOWED",
    "PHX2_PROVIDER_ID",
    "PHX2_RUNNER_MAX_EVENTS",
    "PHX2_RUNNER_MAX_SECONDS",
])
def test_is_config_name_true_for_each_config(name):
    assert m.is_config_name(name) is True
    assert m.is_secret_name(name) is False
    assert m.field_kind_for_name(name) == "CONFIG"


def test_field_kind_for_name_raises_on_unknown():
    with pytest.raises(ValueError):
        m.field_kind_for_name("not_a_real_stage27_name")


# ---------------------------------------------------------------------------
# Stage 27 version axes
# ---------------------------------------------------------------------------


def test_stage_name_and_version_axes():
    assert m.STAGE_NAME == "stage27"
    assert m.STAGE_VERSION == "27.1"
    assert m.STAGE27_MINOR_VERSION == "27.1"
    assert m.STAGE27_DEFAULT_SCHEMA_VERSION == "stage27_v0_operator_config"


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


def test_redaction_token_is_distinctive_literal():
    assert m.STAGE27_REDACTION_TOKEN == "<<STAGE27_REDACTED>>"
    # The token must be distinctive enough that a fake-canary
    # value generated for tests can not collide with it.
    assert "STAGE27_REDACTED" in m.STAGE27_REDACTION_TOKEN
    assert m.STAGE27_REDACTION_TOKEN.startswith("<<")
    assert m.STAGE27_REDACTION_TOKEN.endswith(">>")


# ---------------------------------------------------------------------------
# Record shape immutability and repr safety
# ---------------------------------------------------------------------------


def _build_secret_record_present(name: str, length: int) -> m.Stage27ConfigFieldRecord:
    return m.Stage27ConfigFieldRecord(
        name=name,
        kind=m.CONFIG_FIELD_KIND_SECRET,
        presence_status=m.SECRET_PRESENCE_PRESENT,
        malformed_reason=None,
        safe_value=None,
        value_length=length,
    )


def _build_config_record_present(name: str, value: str) -> m.Stage27ConfigFieldRecord:
    return m.Stage27ConfigFieldRecord(
        name=name,
        kind=m.CONFIG_FIELD_KIND_CONFIG,
        presence_status=m.SECRET_PRESENCE_PRESENT,
        malformed_reason=None,
        safe_value=value,
        value_length=len(value),
    )


def test_config_field_record_is_namedtuple_immutable():
    record = _build_secret_record_present("HELIUS_API_KEY", 24)
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.name = "spoofed"  # type: ignore[misc]


def test_secret_field_record_repr_has_no_raw_value_field():
    # The SECRET record carries ``safe_value=None`` by construction.
    # Its ``repr()`` must therefore say ``safe_value=None`` and
    # carry no raw value substring.
    record = _build_secret_record_present("HELIUS_API_KEY", 24)
    rep = repr(record)
    assert "safe_value=None" in rep
    # The redaction token never appears on the record itself; only
    # the redacted summary surfaces the token.
    assert "<<STAGE27_REDACTED>>" not in rep


def test_config_field_record_repr_exposes_only_safe_value():
    # The CONFIG record is allowed to carry the raw safe value; the
    # value is a label / path / number / bool literal, never a
    # secret.
    record = _build_config_record_present(
        "PHX2_PROVIDER_ID", "helius-test"
    )
    rep = repr(record)
    assert "safe_value='helius-test'" in rep


def test_readiness_report_is_namedtuple_immutable():
    report = m.Stage27SecretsReadinessReport(
        fields=(),
        required_live_missing=(),
        required_live_malformed=(),
        all_required_live_present=True,
    )
    assert isinstance(report, tuple)
    with pytest.raises(AttributeError):
        report.fields = ()  # type: ignore[misc]


def test_live_mode_authority_is_namedtuple_immutable():
    authority = m.Stage27LiveModeAuthority(
        resolved="DRY_RUN",
        env_flag_set=False,
        cli_live_requested=False,
        required_live_secrets_present=False,
        reason_code="DEFAULT_DRY_RUN",
    )
    assert isinstance(authority, tuple)
    with pytest.raises(AttributeError):
        authority.resolved = "LIVE_ALLOWED"  # type: ignore[misc]


def test_run_identity_is_namedtuple_immutable():
    identity = m.Stage27RunIdentity(
        session_id="deadbeef",
        run_id="cafef00d",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode="DRY_RUN",
        stage="stage27",
        substage="27.1",
        schema_version="stage27_v0_operator_config",
    )
    assert isinstance(identity, tuple)
    with pytest.raises(AttributeError):
        identity.run_id = "spoof"  # type: ignore[misc]


def test_operator_config_is_namedtuple_immutable():
    redacted = m.Stage27RedactedReadinessSummary(
        lines=(),
        mode_label="DRY_RUN",
        redaction_token=m.STAGE27_REDACTION_TOKEN,
    )
    authority = m.Stage27LiveModeAuthority(
        resolved="DRY_RUN",
        env_flag_set=False,
        cli_live_requested=False,
        required_live_secrets_present=False,
        reason_code="DEFAULT_DRY_RUN",
    )
    identity = m.Stage27RunIdentity(
        session_id="deadbeef",
        run_id="cafef00d",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode="DRY_RUN",
        stage="stage27",
        substage="27.1",
        schema_version="stage27_v0_operator_config",
    )
    report = m.Stage27SecretsReadinessReport(
        fields=(),
        required_live_missing=(),
        required_live_malformed=(),
        all_required_live_present=True,
    )
    cfg = m.Stage27OperatorConfig(
        readiness=report,
        authority=authority,
        identity=identity,
        redacted_summary=redacted,
    )
    assert isinstance(cfg, tuple)
    with pytest.raises(AttributeError):
        cfg.authority = authority  # type: ignore[misc]
