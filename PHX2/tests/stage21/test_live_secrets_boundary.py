"""Stage 21.3A live-readiness boundary tests."""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage21.config import Stage21Config
from PHX2.stage21.constants import (
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_LIVE_PRIVATE,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_MODE,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_SINK_MODE,
    ProviderModeName,
    SinkModeName,
)
from PHX2.stage21.live_secrets_boundary import (
    ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
    ENV_VAR_LIVE_SMOKE_MODE,
    ENV_VAR_PROVIDER_ID,
    ENV_VAR_SAFE_FOR_LIVE_DISPATCH,
    LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    LIVE_SMOKE_MODE_TOKEN,
    PLACEHOLDER_PROVIDER_ID_21_3B,
    REASON_BASE_PUBLIC_FLAG_NOT_FALSE,
    REASON_DISCORD_WEBHOOK_URL_MISSING,
    REASON_LIVE_PRIVATE_NOT_TRUE,
    REASON_MISSING_PROVIDER_ID,
    REASON_MODE_DISABLED,
    REASON_PROVIDER_API_KEY_MISSING,
    REASON_PROVIDER_MODE_NOT_LIVE,
    REASON_PROVIDER_RPC_URL_MISSING,
    REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE,
    REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH,
    REASON_SINK_MODE_NOT_PRIVATE_PREVIEW,
    REASON_UNSUPPORTED_PROVIDER_ID,
    ReadinessResult,
    STAGE21_3A_NEW_ENV_VAR_NAMES,
    STAGE21_3A_READINESS_REASON_TOKENS,
    Stage21LiveReadinessConfig,
    evaluate_live_readiness,
    load_live_readiness_config_from_env,
)


def _fully_ready_env() -> dict[str, str]:
    """Build an env mapping that satisfies every readiness precondition."""
    return {
        ENV_VAR_PROVIDER_MODE: ProviderModeName.LIVE.value,
        ENV_VAR_SINK_MODE: SinkModeName.PRIVATE_PREVIEW.value,
        ENV_VAR_LIVE_PRIVATE: "true",
        ENV_VAR_PROVIDER_API_KEY: "fake-secret-token-for-tests-only",
        ENV_VAR_PROVIDER_RPC_URL: "fake-rpc-url-for-tests-only",
        ENV_VAR_DISCORD_WEBHOOK_URL: "fake-discord-url-for-tests-only",
        ENV_VAR_LIVE_SMOKE_MODE: LIVE_SMOKE_MODE_TOKEN,
        ENV_VAR_PROVIDER_ID: PLACEHOLDER_PROVIDER_ID_21_3B,
        ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "true",
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    }


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


def test_live_smoke_mode_token_is_live_smoke():
    assert LIVE_SMOKE_MODE_TOKEN == "live_smoke"


def test_live_safety_acknowledgement_v1_carries_v1_suffix():
    # The acknowledgement token is locked at V1; future revisions
    # require an explicit operator decision to introduce a V2 token.
    assert LIVE_SAFETY_ACKNOWLEDGEMENT_V1.endswith("-v1")
    assert "stage21" in LIVE_SAFETY_ACKNOWLEDGEMENT_V1
    assert "ack" in LIVE_SAFETY_ACKNOWLEDGEMENT_V1


def test_new_env_var_names_use_phx2_stage21_prefix():
    for name in STAGE21_3A_NEW_ENV_VAR_NAMES:
        assert name.startswith("PHX2_STAGE21_"), name
    assert ENV_VAR_LIVE_SMOKE_MODE == "PHX2_STAGE21_LIVE_SMOKE_MODE"
    assert ENV_VAR_PROVIDER_ID == "PHX2_STAGE21_PROVIDER_ID"
    assert ENV_VAR_SAFE_FOR_LIVE_DISPATCH == "PHX2_STAGE21_SAFE_FOR_LIVE_DISPATCH"
    assert (
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT
        == "PHX2_STAGE21_LIVE_SAFETY_ACKNOWLEDGEMENT"
    )


def test_new_env_var_set_size_is_exactly_four():
    assert len(STAGE21_3A_NEW_ENV_VAR_NAMES) == 4
    assert len(set(STAGE21_3A_NEW_ENV_VAR_NAMES)) == 4


def test_readiness_reason_tokens_are_a_closed_set():
    # The locked reason vocabulary. Adding or renaming any token
    # is an explicit operator decision; this test fails on either.
    assert STAGE21_3A_READINESS_REASON_TOKENS == (
        "mode_disabled",
        "provider_mode_not_live",
        "sink_mode_not_private_preview",
        "live_private_not_true",
        "safe_for_public_dispatch_not_false",
        "missing_provider_id",
        "unsupported_provider_id",
        "provider_api_key_missing",
        "provider_rpc_url_missing",
        "discord_webhook_url_missing",
        "safe_for_live_dispatch_not_true",
        "safety_acknowledgement_mismatch",
    )


def test_readiness_reason_token_count_is_twelve():
    assert len(STAGE21_3A_READINESS_REASON_TOKENS) == 12
    assert len(set(STAGE21_3A_READINESS_REASON_TOKENS)) == 12


def test_placeholder_provider_id_constant_locked_to_reserved_for_21_3b():
    # Real provider ids belong in Stage 21.3B+; Stage 21.3A only
    # accepts this exact placeholder. Adding any other accepted
    # value here is an explicit operator decision.
    assert PLACEHOLDER_PROVIDER_ID_21_3B == "reserved_for_21_3b"


# ---------------------------------------------------------------------------
# Loader -- base composition + new fields
# ---------------------------------------------------------------------------


def test_loader_with_empty_env_returns_empty_string_fields_and_false_bool():
    cfg = load_live_readiness_config_from_env({})
    assert isinstance(cfg, Stage21LiveReadinessConfig)
    assert isinstance(cfg.base, Stage21Config)
    assert cfg.live_smoke_mode == ""
    assert cfg.provider_id == ""
    assert cfg.safe_for_live_dispatch is False
    assert cfg.safety_acknowledgement == ""


def test_loader_reads_all_four_new_env_vars_from_supplied_mapping():
    env = {
        ENV_VAR_LIVE_SMOKE_MODE: LIVE_SMOKE_MODE_TOKEN,
        ENV_VAR_PROVIDER_ID: PLACEHOLDER_PROVIDER_ID_21_3B,
        ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "true",
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    }
    cfg = load_live_readiness_config_from_env(env)
    assert cfg.live_smoke_mode == LIVE_SMOKE_MODE_TOKEN
    assert cfg.provider_id == PLACEHOLDER_PROVIDER_ID_21_3B
    assert cfg.safe_for_live_dispatch is True
    assert cfg.safety_acknowledgement == LIVE_SAFETY_ACKNOWLEDGEMENT_V1


def test_loader_delegates_base_to_load_config_unmodified():
    # Stage21Config defaults: FAKE/FAKE, dry_run=True, live_private=False.
    cfg = load_live_readiness_config_from_env({})
    assert cfg.base.provider_mode is ProviderModeName.FAKE
    assert cfg.base.sink_mode is SinkModeName.FAKE
    assert cfg.base.live_private is False
    assert cfg.base.safe_for_public_dispatch is False


def test_loader_safe_for_live_dispatch_parses_truthy_tokens():
    for token in ("1", "true", "yes", "on", "TRUE", "Yes", "On"):
        env = {ENV_VAR_SAFE_FOR_LIVE_DISPATCH: token}
        cfg = load_live_readiness_config_from_env(env)
        assert cfg.safe_for_live_dispatch is True, token


def test_loader_safe_for_live_dispatch_parses_falsy_or_unknown_as_false():
    for token in ("", "0", "false", "no", "off", "anything-else", "DISABLED"):
        env = {ENV_VAR_SAFE_FOR_LIVE_DISPATCH: token}
        cfg = load_live_readiness_config_from_env(env)
        assert cfg.safe_for_live_dispatch is False, token


# ---------------------------------------------------------------------------
# evaluate_live_readiness -- happy path
# ---------------------------------------------------------------------------


def test_fully_ready_env_evaluates_ready_true_with_empty_reasons():
    cfg = load_live_readiness_config_from_env(_fully_ready_env())
    result = evaluate_live_readiness(cfg)
    assert isinstance(result, ReadinessResult)
    assert result.ready is True
    assert result.reasons == ()


# ---------------------------------------------------------------------------
# evaluate_live_readiness -- mode disabled short-circuits to single reason
# ---------------------------------------------------------------------------


def test_empty_env_returns_only_mode_disabled():
    cfg = load_live_readiness_config_from_env({})
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert result.reasons == (REASON_MODE_DISABLED,)


def test_non_enabling_live_smoke_mode_short_circuits_to_mode_disabled():
    # Even when every OTHER precondition holds, an unrecognized
    # live_smoke_mode value returns only ``mode_disabled``.
    env = _fully_ready_env()
    env[ENV_VAR_LIVE_SMOKE_MODE] = "anything-else"
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert result.reasons == (REASON_MODE_DISABLED,)


def test_missing_live_smoke_mode_short_circuits_to_mode_disabled():
    env = _fully_ready_env()
    del env[ENV_VAR_LIVE_SMOKE_MODE]
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert result.reasons == (REASON_MODE_DISABLED,)


def test_uppercase_live_smoke_mode_does_not_match_enabling_token():
    env = _fully_ready_env()
    env[ENV_VAR_LIVE_SMOKE_MODE] = LIVE_SMOKE_MODE_TOKEN.upper()
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert result.reasons == (REASON_MODE_DISABLED,)


# ---------------------------------------------------------------------------
# evaluate_live_readiness -- individual precondition violations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_mutation, expected_reason",
    [
        (
            {ENV_VAR_PROVIDER_MODE: ProviderModeName.FAKE.value},
            REASON_PROVIDER_MODE_NOT_LIVE,
        ),
        (
            {ENV_VAR_PROVIDER_MODE: ProviderModeName.REPLAY.value},
            REASON_PROVIDER_MODE_NOT_LIVE,
        ),
        (
            {ENV_VAR_SINK_MODE: SinkModeName.FAKE.value},
            REASON_SINK_MODE_NOT_PRIVATE_PREVIEW,
        ),
        (
            {ENV_VAR_LIVE_PRIVATE: "false"},
            REASON_LIVE_PRIVATE_NOT_TRUE,
        ),
        (
            {ENV_VAR_PROVIDER_ID: ""},
            REASON_MISSING_PROVIDER_ID,
        ),
        (
            # A real provider name like ``"helius"`` is rejected
            # in Stage 21.3A; the real vocabulary lands in 21.3B+.
            {ENV_VAR_PROVIDER_ID: "helius"},
            REASON_UNSUPPORTED_PROVIDER_ID,
        ),
        (
            {ENV_VAR_PROVIDER_API_KEY: ""},
            REASON_PROVIDER_API_KEY_MISSING,
        ),
        (
            {ENV_VAR_PROVIDER_RPC_URL: ""},
            REASON_PROVIDER_RPC_URL_MISSING,
        ),
        (
            {ENV_VAR_DISCORD_WEBHOOK_URL: ""},
            REASON_DISCORD_WEBHOOK_URL_MISSING,
        ),
        (
            {ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "false"},
            REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE,
        ),
        (
            {ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: "not-the-locked-token"},
            REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH,
        ),
        (
            # Acknowledgement V0 (hypothetical earlier revision) is
            # not accepted -- only the exact V1 token passes.
            {ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: "phx2-stage21-live-smoke-ack-v0"},
            REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH,
        ),
    ],
)
def test_single_precondition_violation_surfaces_locked_reason(
    env_mutation: Mapping[str, str],
    expected_reason: str,
):
    env = _fully_ready_env()
    env.update(env_mutation)
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert expected_reason in result.reasons


# ---------------------------------------------------------------------------
# provider_id gate: placeholder is the only accepted value (Major 1)
# ---------------------------------------------------------------------------


def test_missing_provider_id_via_explicit_unset_yields_missing_reason():
    # ``del`` on a dict mapping is the closest analog to a missing
    # env-var. The loader's env.get(...) defaults to "" so the
    # missing case is equivalent to the empty case.
    env = _fully_ready_env()
    del env[ENV_VAR_PROVIDER_ID]
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert REASON_MISSING_PROVIDER_ID in result.reasons
    assert REASON_UNSUPPORTED_PROVIDER_ID not in result.reasons


def test_empty_provider_id_yields_missing_reason():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = ""
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert REASON_MISSING_PROVIDER_ID in result.reasons
    assert REASON_UNSUPPORTED_PROVIDER_ID not in result.reasons


def test_real_provider_id_helius_yields_unsupported_reason_and_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = "helius"
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert REASON_UNSUPPORTED_PROVIDER_ID in result.reasons
    assert REASON_MISSING_PROVIDER_ID not in result.reasons


@pytest.mark.parametrize(
    "candidate_real_provider_id",
    ["helius", "birdeye", "jupiter", "shyft", "quicknode", "rpcmania"],
)
def test_known_real_provider_id_candidates_are_all_rejected_in_21_3a(
    candidate_real_provider_id: str,
):
    # Stage 21.3A locks the gate to the placeholder. Any plausible
    # real provider name is rejected with ``unsupported_provider_id``.
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = candidate_real_provider_id
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert REASON_UNSUPPORTED_PROVIDER_ID in result.reasons


def test_placeholder_provider_id_passes_the_gate():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = PLACEHOLDER_PROVIDER_ID_21_3B
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    # The placeholder satisfies the provider_id gate on its own,
    # and with the rest of the fully-ready env it produces a ready
    # result with empty reasons.
    assert result.ready is True
    assert result.reasons == ()


def test_unsupported_provider_id_reason_does_not_leak_raw_value():
    # The readiness reason set is constructed from locked
    # constants -- it cannot carry the raw provider_id value back
    # to the operator. Pin that property: a malicious or
    # secret-like provider_id input must not appear anywhere in
    # the readiness reasons.
    raw_value = "secret-value-for-error"
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = raw_value
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    for reason in result.reasons:
        assert raw_value not in reason


def test_multiple_violations_surface_exact_full_reason_tuple_alphabetical():
    # Disable two preconditions at once and assert the EXACT full
    # expected reason tuple for the scenario (Minor remediation
    # tightening). The expected tuple is sorted alphabetically so
    # the assertion is order-stable regardless of the underlying
    # iteration order inside ``evaluate_live_readiness``.
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_API_KEY] = ""
    env[ENV_VAR_SAFE_FOR_LIVE_DISPATCH] = "false"
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert tuple(sorted(result.reasons)) == (
        REASON_PROVIDER_API_KEY_MISSING,
        REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE,
    )


def test_every_required_secret_missing_lists_every_secret_reason():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_API_KEY] = ""
    env[ENV_VAR_PROVIDER_RPC_URL] = ""
    env[ENV_VAR_DISCORD_WEBHOOK_URL] = ""
    cfg = load_live_readiness_config_from_env(env)
    result = evaluate_live_readiness(cfg)
    assert result.ready is False
    assert REASON_PROVIDER_API_KEY_MISSING in result.reasons
    assert REASON_PROVIDER_RPC_URL_MISSING in result.reasons
    assert REASON_DISCORD_WEBHOOK_URL_MISSING in result.reasons


def test_safe_for_public_dispatch_invariant_is_always_false_so_reason_never_fires():
    # SAFE_FOR_PUBLIC_DISPATCH is hardcoded to literal Python
    # False; the corresponding reason is wired but cannot fire as
    # long as the constant stays False. This test pins that
    # behavior so a future constant flip surfaces the new reason
    # path immediately.
    cfg = load_live_readiness_config_from_env(_fully_ready_env())
    assert cfg.base.safe_for_public_dispatch is False
    result = evaluate_live_readiness(cfg)
    assert REASON_BASE_PUBLIC_FLAG_NOT_FALSE not in result.reasons


# ---------------------------------------------------------------------------
# Composition wrapper invariants
# ---------------------------------------------------------------------------


def test_wrapper_does_not_modify_or_replace_base_stage21config():
    env = _fully_ready_env()
    cfg = load_live_readiness_config_from_env(env)
    # ``cfg.base`` is a Stage21Config and exposes every Stage 21.1
    # public summary field unchanged.
    summary = cfg.base.public_summary()
    assert summary["provider_mode"] == ProviderModeName.LIVE.value
    assert summary["sink_mode"] == SinkModeName.PRIVATE_PREVIEW.value
    assert summary["live_private"] is True
    assert summary["safe_for_public_dispatch"] is False


def test_wrapper_is_immutable_namedtuple_shape():
    cfg = load_live_readiness_config_from_env({})
    with pytest.raises(AttributeError):
        cfg.live_smoke_mode = "force"  # type: ignore[misc]


def test_readiness_result_is_immutable_namedtuple_shape():
    result = evaluate_live_readiness(
        load_live_readiness_config_from_env({})
    )
    with pytest.raises(AttributeError):
        result.ready = True  # type: ignore[misc]
