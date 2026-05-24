"""Stage 28.11 readiness boundary tests.

Pins:

  * Locked Stage 28.11 env-name surface (four names).
  * Readiness rejects missing / unsafe endpoint and missing /
    unsafe x-token with the matching closed-set refusal-reason
    tokens; raw values NEVER appear in the report dict or any
    exception message.
  * Readiness reports the live-gate flag bool without leaking
    the raw env value.
  * Readiness defaults to ``DEFAULT_GRPC_TIMEOUT_SECONDS`` when
    the optional override env is missing; refuses an out-of-
    range / non-int override.
  * ``build_endpoint_secret_from_env`` raises
    ``Stage28_11ReadinessEnvError`` (closed-set reason) when
    readiness refuses, and returns a redaction-safe secret
    record when readiness passes.
  * ``build_runtime_config_from_env`` returns a runtime-config
    whose redacted dict never echoes the raw env values.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_READY,
    REFUSAL_REASON_ENDPOINT_MISSING,
    REFUSAL_REASON_ENDPOINT_UNSAFE,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_TIMEOUT_INVALID,
    REFUSAL_REASON_X_TOKEN_MISSING,
    REFUSAL_REASON_X_TOKEN_UNSAFE,
    STAGE28_11_REDACTION_TOKEN,
    Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    readiness_report_to_safe_dict,
    runtime_config_to_safe_dict,
)
from PHX2.stage28 import (
    chainstack_yellowstone_grpc_readiness as readiness_module,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    DEFAULT_GRPC_TIMEOUT_SECONDS,
    ENV_NAME_ALLOW_LIVE_GRPC,
    ENV_NAME_GRPC_ENDPOINT,
    ENV_NAME_GRPC_TIMEOUT_SECONDS,
    ENV_NAME_X_TOKEN,
    STAGE28_11_READ_ENV_NAMES,
    TIMEOUT_STATUS_DEFAULT,
    TIMEOUT_STATUS_INVALID,
    TIMEOUT_STATUS_OVERRIDE,
    TIMEOUT_STATUS_VALUES,
    Stage28_11ReadinessEnvError,
    Stage28_11SafeEnvProjection,
    build_endpoint_secret_from_env,
    build_runtime_config_from_env,
    detect_stage28_11_grpc_readiness,
    project_stage28_11_env_safe,
)


SAFE_ENDPOINT: str = "fixture.example:443"
SAFE_X_TOKEN: str = "abc-DEF.ghi-JKL_mno-1234567890"
UNSAFE_ENDPOINT_WITH_USERPASS: str = "user:pw@host:443"
UNSAFE_X_TOKEN_WIF: str = "5K" + "x" * 30


def _safe_env() -> dict:
    return {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }


# ---------------------------------------------------------------------------
# 1. Locked env-name surface
# ---------------------------------------------------------------------------


def test_locked_env_names_match():
    assert STAGE28_11_READ_ENV_NAMES == (
        ENV_NAME_GRPC_ENDPOINT,
        ENV_NAME_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC,
        ENV_NAME_GRPC_TIMEOUT_SECONDS,
    )


def test_env_name_grpc_endpoint_constant():
    assert (
        ENV_NAME_GRPC_ENDPOINT
        == "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT"
    )


def test_env_name_x_token_constant():
    assert (
        ENV_NAME_X_TOKEN
        == "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN"
    )


def test_env_name_allow_live_grpc_constant():
    assert (
        ENV_NAME_ALLOW_LIVE_GRPC
        == "PHX2_STAGE28_11_ALLOW_LIVE_GRPC"
    )


def test_env_name_timeout_constant():
    assert (
        ENV_NAME_GRPC_TIMEOUT_SECONDS
        == "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS"
    )


# ---------------------------------------------------------------------------
# 2. Redaction discipline: no public raw env projection
# ---------------------------------------------------------------------------


def test_public_api_does_not_export_raw_env_projection():
    """The Stage 28.11 redaction contract requires that no public
    helper returns the raw endpoint URL or raw x-token in a
    public dict. The previous ``project_stage28_11_env`` helper
    that did so MUST be absent from the module's public surface.
    """
    public_api = set(readiness_module.__all__)
    assert "project_stage28_11_env" not in public_api, (
        "Stage 28.11 redaction: ``project_stage28_11_env`` must "
        "NOT appear in __all__; the raw-value variant is private "
        "(``_read_stage28_11_env_raw``)."
    )
    assert "_read_stage28_11_env_raw" not in public_api, (
        "Stage 28.11 redaction: the private raw env reader must "
        "NOT be re-exported."
    )


def test_public_api_exports_only_safe_env_projection():
    """The replacement public helper is
    ``project_stage28_11_env_safe`` returning a
    ``Stage28_11SafeEnvProjection`` record with no raw values."""
    public_api = set(readiness_module.__all__)
    assert "project_stage28_11_env_safe" in public_api
    assert "Stage28_11SafeEnvProjection" in public_api


def test_module_no_longer_defines_raw_env_projection_callable():
    """The module's top-level namespace must NOT bind
    ``project_stage28_11_env`` (removing the symbol entirely
    prevents downstream callers from sneaking the raw-value
    helper back through ``getattr``)."""
    assert not hasattr(
        readiness_module, "project_stage28_11_env",
    ), (
        "Stage 28.11 redaction: the public raw env reader was "
        "removed; the private replacement is "
        "``_read_stage28_11_env_raw``."
    )


def test_private_raw_reader_still_available_to_module_internals():
    """The private raw reader stays callable inside the module so
    the readiness validator and the endpoint-secret builder can
    project the env once and refuse / wrap immediately. It is
    NOT exported via __all__ (pinned above)."""
    raw_reader = getattr(
        readiness_module, "_read_stage28_11_env_raw", None,
    )
    assert raw_reader is not None
    assert callable(raw_reader)
    # The private reader still functions: it returns the raw
    # values, but its existence outside __all__ keeps it off the
    # public surface and out of import-* propagation.
    out = raw_reader(env=_safe_env())
    assert out == {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }


# ---------------------------------------------------------------------------
# 2b. project_stage28_11_env_safe public helper
# ---------------------------------------------------------------------------


def test_project_safe_returns_safe_projection_record():
    projection = project_stage28_11_env_safe(env=_safe_env())
    assert isinstance(projection, Stage28_11SafeEnvProjection)
    assert projection.endpoint_present is True
    assert projection.x_token_present is True
    assert projection.live_flag_present is False
    assert projection.timeout_present is False
    assert projection.endpoint_length == len(SAFE_ENDPOINT)
    assert projection.x_token_length == len(SAFE_X_TOKEN)
    assert projection.live_flag_value_is_allow is False
    assert projection.timeout_status == TIMEOUT_STATUS_DEFAULT


def test_project_safe_for_empty_env():
    projection = project_stage28_11_env_safe(env={})
    assert projection.endpoint_present is False
    assert projection.x_token_present is False
    assert projection.live_flag_present is False
    assert projection.timeout_present is False
    assert projection.endpoint_length == 0
    assert projection.x_token_length == 0
    assert projection.live_flag_value_is_allow is False
    assert projection.timeout_status == TIMEOUT_STATUS_DEFAULT


def test_project_safe_live_flag_truthy_only_when_one():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC: "1",
    }
    projection = project_stage28_11_env_safe(env=env)
    assert projection.live_flag_present is True
    assert projection.live_flag_value_is_allow is True


def test_project_safe_live_flag_zero_is_not_allow():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC: "0",
    }
    projection = project_stage28_11_env_safe(env=env)
    assert projection.live_flag_present is True
    assert projection.live_flag_value_is_allow is False


def test_project_safe_timeout_override_status():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "120",
    }
    projection = project_stage28_11_env_safe(env=env)
    assert projection.timeout_present is True
    assert projection.timeout_status == TIMEOUT_STATUS_OVERRIDE


def test_project_safe_timeout_invalid_status():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "0",
    }
    projection = project_stage28_11_env_safe(env=env)
    assert projection.timeout_present is True
    assert projection.timeout_status == TIMEOUT_STATUS_INVALID


def test_project_safe_never_echoes_raw_endpoint_or_x_token():
    """End-to-end: a leak-shaped env value never appears in any
    field, repr, str, asdict, or string projection of the safe
    public helper's output."""
    import dataclasses

    raw_endpoint = "leak-detector-endpoint.example:443"
    raw_token = "leak-detector-token-abcdef1234567890"
    env = {
        ENV_NAME_GRPC_ENDPOINT: raw_endpoint,
        ENV_NAME_X_TOKEN: raw_token,
        ENV_NAME_ALLOW_LIVE_GRPC: "1",
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "120",
    }
    projection = project_stage28_11_env_safe(env=env)
    text_blob = (
        repr(projection)
        + str(projection)
        + repr(dataclasses.asdict(projection))
    )
    assert raw_endpoint not in text_blob
    assert raw_token not in text_blob


def test_project_safe_record_is_frozen():
    """The safe projection is a frozen dataclass so callers
    cannot stuff a raw value back onto it post-construction."""
    projection = project_stage28_11_env_safe(env=_safe_env())
    with pytest.raises(Exception):
        projection.endpoint_present = False  # type: ignore[misc]


def test_timeout_status_values_are_locked_closed_set():
    assert TIMEOUT_STATUS_VALUES == (
        TIMEOUT_STATUS_DEFAULT,
        TIMEOUT_STATUS_OVERRIDE,
        TIMEOUT_STATUS_INVALID,
    )


# ---------------------------------------------------------------------------
# 3. detect_stage28_11_grpc_readiness
# ---------------------------------------------------------------------------


def test_detect_ready_for_safe_env():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC: "1",
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_READY
    assert report.refusal_reason == REFUSAL_REASON_NONE
    assert report.live_flag_set is True
    assert report.endpoint_length == len(SAFE_ENDPOINT)
    assert report.x_token_length == len(SAFE_X_TOKEN)
    assert report.timeout_seconds == DEFAULT_GRPC_TIMEOUT_SECONDS


def test_detect_ready_without_live_flag_still_ready():
    """Readiness alone does not require the live-gate flag."""
    report = detect_stage28_11_grpc_readiness(env=_safe_env())
    assert report.status == PROBE_STATUS_READY
    assert report.live_flag_set is False


def test_detect_endpoint_missing():
    env = {ENV_NAME_X_TOKEN: SAFE_X_TOKEN}
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_ENDPOINT_MISSING
    assert report.endpoint_safe_label is None


def test_detect_endpoint_empty_string_is_missing():
    env = {
        ENV_NAME_GRPC_ENDPOINT: "",
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_ENDPOINT_MISSING


def test_detect_endpoint_unsafe_no_leak():
    env = {
        ENV_NAME_GRPC_ENDPOINT: UNSAFE_ENDPOINT_WITH_USERPASS,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_ENDPOINT_UNSAFE
    safe = readiness_report_to_safe_dict(report)
    text = repr(safe)
    assert UNSAFE_ENDPOINT_WITH_USERPASS not in text


def test_detect_x_token_missing():
    env = {ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT}
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_X_TOKEN_MISSING


def test_detect_x_token_unsafe_no_leak():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: UNSAFE_X_TOKEN_WIF,
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_X_TOKEN_UNSAFE
    safe = readiness_report_to_safe_dict(report)
    text = repr(safe)
    assert UNSAFE_X_TOKEN_WIF not in text


def test_detect_timeout_invalid_rejected():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "0",
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_TIMEOUT_INVALID


def test_detect_timeout_non_numeric_rejected():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "abc",
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_TIMEOUT_INVALID


def test_detect_timeout_out_of_range_rejected():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "601",
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_NOT_READY
    assert report.refusal_reason == REFUSAL_REASON_TIMEOUT_INVALID


def test_detect_timeout_override_applied_when_safe():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "120",
    }
    report = detect_stage28_11_grpc_readiness(env=env)
    assert report.status == PROBE_STATUS_READY
    assert report.timeout_seconds == 120


def test_detect_live_flag_only_truthy_when_exactly_one():
    for value, expected in (
        ("1", True),
        ("true", False),
        ("yes", False),
        ("on", False),
        ("0", False),
        ("", False),
    ):
        env = {
            ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
            ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
            ENV_NAME_ALLOW_LIVE_GRPC: value,
        }
        report = detect_stage28_11_grpc_readiness(env=env)
        assert report.live_flag_set is expected, (
            f"live-gate value {value!r} -> live_flag_set "
            f"expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# 4. build_endpoint_secret_from_env
# ---------------------------------------------------------------------------


def test_build_secret_from_env_returns_safe_record():
    record = build_endpoint_secret_from_env(env=_safe_env())
    assert isinstance(
        record,
        Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    )
    # The raw env values are accessible only via the explicit
    # internal-use getters.
    assert (
        record.get_endpoint_url_for_internal_use()
        == SAFE_ENDPOINT
    )
    assert (
        record.get_x_token_for_internal_use() == SAFE_X_TOKEN
    )


def test_build_secret_from_env_raises_on_unsafe_endpoint():
    env = {
        ENV_NAME_GRPC_ENDPOINT: UNSAFE_ENDPOINT_WITH_USERPASS,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }
    with pytest.raises(Stage28_11ReadinessEnvError) as err:
        build_endpoint_secret_from_env(env=env)
    assert err.value.refusal_reason == REFUSAL_REASON_ENDPOINT_UNSAFE
    assert UNSAFE_ENDPOINT_WITH_USERPASS not in str(err.value)


def test_build_secret_from_env_raises_on_missing_x_token():
    env = {ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT}
    with pytest.raises(Stage28_11ReadinessEnvError) as err:
        build_endpoint_secret_from_env(env=env)
    assert err.value.refusal_reason == REFUSAL_REASON_X_TOKEN_MISSING


# ---------------------------------------------------------------------------
# 5. build_runtime_config_from_env
# ---------------------------------------------------------------------------


def test_build_runtime_config_from_env_redacts_secret():
    record = build_runtime_config_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        env=_safe_env(),
    )
    assert isinstance(
        record,
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    )
    safe = runtime_config_to_safe_dict(record)
    text = repr(safe)
    assert SAFE_ENDPOINT not in text
    assert SAFE_X_TOKEN not in text
    assert (
        safe["endpoint_secret"]["endpoint_url"]
        == STAGE28_11_REDACTION_TOKEN
    )
    assert (
        safe["endpoint_secret"]["x_token"]
        == STAGE28_11_REDACTION_TOKEN
    )


def test_build_runtime_config_from_env_carries_timeout_override():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_GRPC_TIMEOUT_SECONDS: "120",
    }
    record = build_runtime_config_from_env(
        mode=MODE_READINESS_ONLY,
        env=env,
    )
    assert record.timeout_seconds == 120


def test_build_runtime_config_from_env_raises_when_readiness_fails():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        # x_token missing
    }
    with pytest.raises(Stage28_11ReadinessEnvError) as err:
        build_runtime_config_from_env(
            mode=MODE_READINESS_ONLY,
            env=env,
        )
    assert err.value.refusal_reason == REFUSAL_REASON_X_TOKEN_MISSING


# ---------------------------------------------------------------------------
# 6. End-to-end redaction discipline (safe values still never leak)
# ---------------------------------------------------------------------------


def test_readiness_report_with_safe_env_never_echoes_raw_values():
    """The readiness report stores only length counters + a
    safe-shape provider-id label; it MUST NOT echo the raw
    endpoint URL or raw x-token even when the env passed
    readiness."""
    import dataclasses

    report = detect_stage28_11_grpc_readiness(env=_safe_env())
    safe = readiness_report_to_safe_dict(report)
    blob = (
        repr(report)
        + str(report)
        + repr(dataclasses.asdict(report))
        + repr(safe)
    )
    assert SAFE_ENDPOINT not in blob
    assert SAFE_X_TOKEN not in blob


def test_readiness_env_error_carries_only_closed_set_reason():
    """Stage28_11ReadinessEnvError must never echo the raw
    endpoint URL or raw x-token in its str / repr / args."""
    env = {
        ENV_NAME_GRPC_ENDPOINT: UNSAFE_ENDPOINT_WITH_USERPASS,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }
    with pytest.raises(Stage28_11ReadinessEnvError) as err:
        build_endpoint_secret_from_env(env=env)
    blob = (
        str(err.value)
        + repr(err.value)
        + repr(getattr(err.value, "args", ()))
    )
    assert UNSAFE_ENDPOINT_WITH_USERPASS not in blob
    assert SAFE_X_TOKEN not in blob


def test_runtime_config_built_from_env_redacts_in_safe_dict():
    """End-to-end: building the runtime config from env and
    projecting to its safe dict never leaks the raw env
    values."""
    record = build_runtime_config_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        env=_safe_env(),
    )
    safe = runtime_config_to_safe_dict(record)
    text = repr(safe) + repr(record)
    assert SAFE_ENDPOINT not in text
    assert SAFE_X_TOKEN not in text
