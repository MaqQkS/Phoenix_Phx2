"""Stage 27.1 operator-config orchestrator tests.

Covers the two-factor LIVE-mode matrix:

  +--------------+-------------+----------------------+---------------+
  | env_flag_set | cli_request | live_secrets_present | resolved      |
  +==============+=============+======================+===============+
  | False        | False       | *                    | DRY_RUN       |
  | True         | False       | *                    | LIVE_REFUSED  |
  | False        | True        | *                    | LIVE_REFUSED  |
  | True         | True        | False                | LIVE_REFUSED  |
  | True         | True        | True                 | LIVE_ALLOWED  |
  +--------------+-------------+----------------------+---------------+

Plus determinism, redaction discipline, and the explicit invariant
that the orchestrator never reads the wall clock (the clock is
injected and frozen across every test).
"""

from __future__ import annotations

import pytest

from PHX2.stage27.live_config_models import (
    LIVE_MODE_AUTHORITY_DRY_RUN,
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
    LIVE_MODE_AUTHORITY_LIVE_REFUSED,
    LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK,
    LIVE_MODE_REASON_DEFAULT_DRY_RUN,
    LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED,
    LIVE_MODE_REASON_LIVE_SECRETS_MISSING,
    LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY,
    LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY,
    STAGE27_BIRDEYE_API_KEY_NAME,
    STAGE27_HELIUS_API_KEY_NAME,
    STAGE27_HELIUS_GRPC_ENDPOINT_NAME,
    STAGE27_HELIUS_RPC_URL_NAME,
    STAGE27_LIVE_MODE_ALLOWED_NAME,
    STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME,
    STAGE27_PROVIDER_ID_NAME,
    STAGE27_REDACTION_TOKEN,
    STAGE27_RUNNER_MAX_EVENTS_NAME,
    STAGE27_RUNNER_MAX_SECONDS_NAME,
    STAGE27_SCRATCH_DIR_NAME,
    Stage27OperatorConfig,
)
from PHX2.stage27.live_operator_config import resolve_operator_config
from PHX2.stage27.live_run_identity import FrozenStage27Clock


# ---------------------------------------------------------------------------
# Canary fake-secret fixtures
# ---------------------------------------------------------------------------


CANARY_HELIUS_API_KEY: str = "CANARY_FAKE_HELIUS_API_KEY_zzzz1111"
CANARY_HELIUS_RPC_URL: str = "https://canary.fake.test/helius/rpc"
CANARY_HELIUS_GRPC_ENDPOINT: str = "canary.fake.test:4243"
CANARY_BIRDEYE_API_KEY: str = "CANARY_FAKE_BIRDEYE_API_KEY_yyyy2222"
CANARY_DISCORD_WEBHOOK_URL: str = (
    "https://canary.fake.test/webhooks/777/CANARY_FAKE_TOKEN_xxxx3333"
)


def _live_ready_env() -> dict[str, str]:
    """Return an env mapping with every LIVE-required field present
    and well-formed, and the LIVE flag truthy.
    """
    return {
        STAGE27_HELIUS_API_KEY_NAME: CANARY_HELIUS_API_KEY,
        STAGE27_HELIUS_RPC_URL_NAME: CANARY_HELIUS_RPC_URL,
        STAGE27_HELIUS_GRPC_ENDPOINT_NAME: CANARY_HELIUS_GRPC_ENDPOINT,
        STAGE27_BIRDEYE_API_KEY_NAME: CANARY_BIRDEYE_API_KEY,
        STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME: CANARY_DISCORD_WEBHOOK_URL,
        STAGE27_PROVIDER_ID_NAME: "canary-helius-test",
        STAGE27_LIVE_MODE_ALLOWED_NAME: "1",
        STAGE27_SCRATCH_DIR_NAME: "/tmp/canary-stage27-scratch",
        STAGE27_RUNNER_MAX_EVENTS_NAME: "50",
        STAGE27_RUNNER_MAX_SECONDS_NAME: "120",
    }


_CANARY_SECRET_VALUES: tuple[str, ...] = (
    CANARY_HELIUS_API_KEY,
    CANARY_HELIUS_RPC_URL,
    CANARY_HELIUS_GRPC_ENDPOINT,
    CANARY_BIRDEYE_API_KEY,
    CANARY_DISCORD_WEBHOOK_URL,
)


def _assert_no_canary_leaks(text: str) -> None:
    for needle in _CANARY_SECRET_VALUES:
        assert needle not in text, (
            f"canary leak: {needle!r} appeared in a redaction-protected "
            f"surface"
        )


def _frozen_clock() -> FrozenStage27Clock:
    return FrozenStage27Clock("2026-05-21T12:00:00+00:00")


# ---------------------------------------------------------------------------
# Two-factor LIVE matrix
# ---------------------------------------------------------------------------


def test_default_neither_factor_resolves_dry_run():
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
        cli_live_requested=False,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_DRY_RUN
    assert cfg.authority.reason_code == LIVE_MODE_REASON_DEFAULT_DRY_RUN
    assert cfg.authority.env_flag_set is False
    assert cfg.authority.cli_live_requested is False


def test_one_factor_env_only_fails_closed_to_live_refused():
    env = {STAGE27_LIVE_MODE_ALLOWED_NAME: "1"}
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=False,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED
    assert cfg.authority.reason_code == LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY
    assert cfg.authority.env_flag_set is True
    assert cfg.authority.cli_live_requested is False


def test_one_factor_cli_only_fails_closed_to_live_refused():
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED
    assert cfg.authority.reason_code == LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY
    assert cfg.authority.env_flag_set is False
    assert cfg.authority.cli_live_requested is True


def test_both_factors_but_secrets_missing_fails_closed():
    env = {STAGE27_LIVE_MODE_ALLOWED_NAME: "1"}  # no LIVE secrets
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED
    assert (
        cfg.authority.reason_code == LIVE_MODE_REASON_LIVE_SECRETS_MISSING
    )


def test_both_factors_but_secrets_malformed_fails_closed():
    env = _live_ready_env()
    env[STAGE27_HELIUS_RPC_URL_NAME] = "ftp://bad/rpc"
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED
    assert (
        cfg.authority.reason_code == LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED
    )


def test_both_factors_and_secrets_present_resolves_live_allowed():
    env = _live_ready_env()
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_ALLOWED
    assert (
        cfg.authority.reason_code
        == LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK
    )
    assert cfg.authority.required_live_secrets_present is True


# ---------------------------------------------------------------------------
# Run identity wiring
# ---------------------------------------------------------------------------


def test_identity_uses_injected_clock_timestamp():
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
        session_id="deadbeef",
    )
    assert cfg.identity.created_at_utc == "2026-05-21T12:00:00+00:00"


def test_identity_mode_mirrors_resolved_authority():
    env = _live_ready_env()
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert cfg.identity.mode == cfg.authority.resolved == "LIVE_ALLOWED"


def test_resolve_operator_config_is_deterministic_given_all_inputs():
    env = _live_ready_env()
    a = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    b = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="deadbeef",
    )
    assert a == b


def test_resolve_operator_config_generates_session_id_when_omitted():
    a = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
    )
    b = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
    )
    assert a.identity.session_id != b.identity.session_id


def test_returned_value_is_immutable_namedtuple():
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
        session_id="deadbeef",
    )
    assert isinstance(cfg, Stage27OperatorConfig)
    assert isinstance(cfg, tuple)
    with pytest.raises(AttributeError):
        cfg.authority = cfg.authority  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DRY_RUN does not require LIVE secrets
# ---------------------------------------------------------------------------


def test_dry_run_does_not_require_live_secrets():
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env={},
        cli_live_requested=False,
        session_id="deadbeef",
    )
    # No LIVE secrets present, but DRY_RUN is still the resolved mode.
    assert cfg.authority.resolved == "DRY_RUN"
    assert cfg.authority.required_live_secrets_present is False


def test_dry_run_with_some_secrets_still_dry_run():
    env = {
        STAGE27_HELIUS_API_KEY_NAME: CANARY_HELIUS_API_KEY,
        STAGE27_PROVIDER_ID_NAME: "canary-helius-test",
    }
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=False,
        session_id="deadbeef",
    )
    assert cfg.authority.resolved == "DRY_RUN"


# ---------------------------------------------------------------------------
# Redaction discipline at the operator-config level
# ---------------------------------------------------------------------------


def test_operator_config_repr_does_not_leak_canary_secrets():
    env = _live_ready_env()
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="canary-session",
    )
    _assert_no_canary_leaks(repr(cfg))
    _assert_no_canary_leaks(str(cfg))


def test_redacted_summary_does_not_leak_canary_secrets():
    env = _live_ready_env()
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="canary-session",
    )
    combined = "\n".join(cfg.redacted_summary.lines)
    _assert_no_canary_leaks(combined)
    # The redaction token must appear (proves redaction ran).
    assert STAGE27_REDACTION_TOKEN in combined


def test_redacted_summary_handles_malformed_value_without_leaking():
    env = _live_ready_env()
    env[STAGE27_HELIUS_RPC_URL_NAME] = (
        "ftp://canary.fake.test/CANARY_FAKE_LEAKY_VALUE_aaaa"
    )
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="canary-session",
    )
    combined = "\n".join(cfg.redacted_summary.lines)
    # The malformed value itself must not leak; only its closed-set
    # reason token.
    assert "CANARY_FAKE_LEAKY_VALUE_aaaa" not in combined
    assert "<malformed:NOT_HTTPS_URL>" in combined


def test_redacted_summary_handles_missing_value_without_leaking():
    env = _live_ready_env()
    del env[STAGE27_BIRDEYE_API_KEY_NAME]
    cfg = resolve_operator_config(
        clock=_frozen_clock(),
        env=env,
        cli_live_requested=True,
        session_id="canary-session",
    )
    combined = "\n".join(cfg.redacted_summary.lines)
    _assert_no_canary_leaks(combined)
    assert "<missing>" in combined


# ---------------------------------------------------------------------------
# Truthy bool literals do not bypass two-factor
# ---------------------------------------------------------------------------


def test_truthy_env_flag_alone_still_refused():
    for literal in ("1", "true", "TRUE", "yes"):
        cfg = resolve_operator_config(
            clock=_frozen_clock(),
            env={STAGE27_LIVE_MODE_ALLOWED_NAME: literal},
            cli_live_requested=False,
            session_id="deadbeef",
        )
        assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED


def test_falsy_env_flag_with_cli_request_still_refused():
    for literal in ("0", "false", "no", ""):
        cfg = resolve_operator_config(
            clock=_frozen_clock(),
            env={STAGE27_LIVE_MODE_ALLOWED_NAME: literal},
            cli_live_requested=True,
            session_id="deadbeef",
        )
        assert cfg.authority.resolved == LIVE_MODE_AUTHORITY_LIVE_REFUSED
