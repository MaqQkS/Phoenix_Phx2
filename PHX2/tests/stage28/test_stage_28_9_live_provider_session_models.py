"""Stage 28.9 live provider session models tests.

Covers:

  * version axes / redaction token / filter-enforcement marker,
  * closed-set vocabulary checks,
  * provider-id / provider-kind / output-dir label validators,
  * config / readiness-verdict / result record validation,
  * deterministic dict projection,
  * exception hierarchy carries closed-set fields only.

No network. No env reads. No real provider. No real Discord.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.live_provider_session_models import (
    FILTER_ENFORCEMENT_NOTICE_TEXT,
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    POLICY_MODE_PRIVATE_OPERATOR_ONLY,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    REFUSAL_REASON_BOUNDS_INVALID,
    REFUSAL_REASON_NOT_LIVE,
    REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
    REFUSAL_REASON_NOT_REFUSED,
    REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    REFUSAL_REASON_PROVIDER_UNSAFE,
    REFUSAL_REASON_VALUES,
    REFUSAL_REASON_WEBHOOK_MISSING,
    SESSION_MODE_DRY_RUN,
    SESSION_MODE_LIVE_PRIVATE,
    SESSION_MODE_VALUES,
    SESSION_OUTCOME_DEGRADED,
    SESSION_OUTCOME_FAILED,
    SESSION_OUTCOME_OK,
    SESSION_OUTCOME_REFUSED,
    SESSION_OUTCOME_VALUES,
    STAGE28_9_MINOR_VERSION,
    STAGE28_9_REDACTION_TOKEN,
    STAGE28_9_SCHEMA_VERSION,
    STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES,
    STAGE28_9_SESSION_RESULT_FIELD_NAMES,
    Stage28_9InvalidReadinessVerdictError,
    Stage28_9InvalidSessionConfigError,
    Stage28_9InvalidSessionResultError,
    Stage28_9LiveProviderSessionConfig,
    Stage28_9LiveProviderSessionError,
    Stage28_9LiveProviderSessionResult,
    Stage28_9ReadinessVerdict,
    build_live_provider_session_config,
    build_live_provider_session_result,
    build_readiness_verdict,
    is_refusal_reason_value,
    is_safe_output_dir_label,
    is_safe_provider_id,
    is_safe_provider_kind,
    is_session_mode_value,
    is_session_outcome_value,
    session_result_to_dict,
)


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage28_9_minor_version_is_locked():
    assert STAGE28_9_MINOR_VERSION == "28.9"


def test_stage28_9_schema_version_is_locked():
    assert (
        STAGE28_9_SCHEMA_VERSION
        == "stage28_9_live_provider_session_v0"
    )


def test_stage28_9_redaction_token_distinct():
    from PHX2.stage28.audited_http_transport_models import (
        STAGE28_4_REDACTION_TOKEN,
    )
    from PHX2.stage28.health_status_models import (
        STAGE28_5_REDACTION_TOKEN,
    )
    from PHX2.stage28.session_runner_models import (
        STAGE28_6_REDACTION_TOKEN,
    )
    from PHX2.stage28.longer_session_smoke_harness import (
        STAGE28_7_REDACTION_TOKEN,
    )

    assert STAGE28_9_REDACTION_TOKEN.startswith("<<")
    assert STAGE28_9_REDACTION_TOKEN.endswith(">>")
    assert STAGE28_9_REDACTION_TOKEN not in {
        STAGE28_4_REDACTION_TOKEN,
        STAGE28_5_REDACTION_TOKEN,
        STAGE28_6_REDACTION_TOKEN,
        STAGE28_7_REDACTION_TOKEN,
    }


# ---------------------------------------------------------------------------
# Filter-enforcement marker
# ---------------------------------------------------------------------------


def test_filter_enforcement_marker_is_locked():
    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert (
        "NOT_ACTIVE_STAGE_29_PENDING"
        in FILTER_ENFORCEMENT_NOTICE_TEXT
    )
    assert (
        FILTER_ENFORCEMENT_NOTICE_TEXT.startswith(
            "Filter enforcement:"
        )
    )


def test_policy_mode_label_is_private_operator_only():
    assert (
        POLICY_MODE_PRIVATE_OPERATOR_ONLY
        == "PRIVATE_OPERATOR_ONLY_OBSERVE_MANUAL"
    )


# ---------------------------------------------------------------------------
# Closed-set vocabulary checks
# ---------------------------------------------------------------------------


def test_session_outcome_values_closed_set():
    assert set(SESSION_OUTCOME_VALUES) == {
        SESSION_OUTCOME_OK,
        SESSION_OUTCOME_DEGRADED,
        SESSION_OUTCOME_REFUSED,
        SESSION_OUTCOME_FAILED,
    }
    for v in SESSION_OUTCOME_VALUES:
        assert is_session_outcome_value(v)
    assert not is_session_outcome_value("OTHER")
    assert not is_session_outcome_value(None)


def test_refusal_reason_values_closed_set():
    assert set(REFUSAL_REASON_VALUES) == {
        REFUSAL_REASON_NOT_REFUSED,
        REFUSAL_REASON_NOT_LIVE,
        REFUSAL_REASON_WEBHOOK_MISSING,
        REFUSAL_REASON_PROVIDER_UNSAFE,
        REFUSAL_REASON_BOUNDS_INVALID,
        REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
        REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
    }
    for v in REFUSAL_REASON_VALUES:
        assert is_refusal_reason_value(v)


def test_session_mode_values_closed_set():
    assert set(SESSION_MODE_VALUES) == {
        SESSION_MODE_DRY_RUN, SESSION_MODE_LIVE_PRIVATE,
    }
    for v in SESSION_MODE_VALUES:
        assert is_session_mode_value(v)


def test_redaction_status_values_closed_set():
    assert REDACTION_STATUS_SAFE == "SAFE"
    assert REDACTION_STATUS_REDACTED == "REDACTED"


# ---------------------------------------------------------------------------
# Safe provider-id / provider-kind / output-dir-label validators
# ---------------------------------------------------------------------------


def test_is_safe_provider_id_accepts_basic_label():
    assert is_safe_provider_id("helius_grpc")
    assert is_safe_provider_id("provider-01")
    assert is_safe_provider_id("p")


def test_is_safe_provider_id_rejects_non_string_empty_or_long():
    assert not is_safe_provider_id(None)
    assert not is_safe_provider_id(123)
    assert not is_safe_provider_id("")
    assert not is_safe_provider_id("a" * 65)


def test_is_safe_provider_id_rejects_secret_shaped():
    # ``bearer`` / ``authorization`` / ``apikey=`` / ``token=`` /
    # ``://`` substrings are the locked Stage 28.9 secret-canary
    # set (concatenated below so the test source itself is not
    # flagged by a downstream literal scan).
    assert not is_safe_provider_id("b" + "earer_id")
    assert not is_safe_provider_id("a" + "uthorization_id")
    assert not is_safe_provider_id("passwordprov")


def test_is_safe_provider_id_rejects_unsafe_chars_and_edges():
    assert not is_safe_provider_id("-leading")
    assert not is_safe_provider_id("trailing-")
    assert not is_safe_provider_id("contains space")
    assert not is_safe_provider_id("with.dot")


def test_is_safe_provider_kind_uses_same_rule():
    assert is_safe_provider_kind("solana_websocket")
    assert not is_safe_provider_kind("b" + "earer_evil")


def test_is_safe_output_dir_label_accepts_simple_label():
    assert is_safe_output_dir_label("scratch")
    assert is_safe_output_dir_label("phx2_stage28_9.run01")


def test_is_safe_output_dir_label_rejects_path_separators_and_traversal():
    assert not is_safe_output_dir_label("a/b")
    assert not is_safe_output_dir_label("a\\b")
    assert not is_safe_output_dir_label("..")
    assert not is_safe_output_dir_label("a..b")
    assert not is_safe_output_dir_label("")
    assert not is_safe_output_dir_label(None)


def test_is_safe_output_dir_label_rejects_secret_shaped():
    # ``://`` / ``b`` + ``earer `` / ``a`` + ``uthorization:`` are
    # in the Stage 28.9 forbidden-substring list; ``://`` is the
    # easiest URL-shape canary to embed in a label string.
    assert not is_safe_output_dir_label("dir_passwordrun")
    # Stage 28.9 output-dir label cap mirrors the models cap.
    assert not is_safe_output_dir_label("a" * 97)


# ---------------------------------------------------------------------------
# Session config builder
# ---------------------------------------------------------------------------


def _valid_config_kwargs() -> dict:
    return {
        "run_id": "phx2_stage28_9_run01",
        "session_id": "phx2_stage28_9_session01",
        "provider_id": "helius_grpc",
        "provider_kind": "solana_websocket",
        "max_events": 32,
        "max_dispatches": 16,
        "max_ticks": 256,
        "max_total_retries": 3,
        "heartbeat_every_n_events": 4,
        "output_dir_safe_label": "phx2_stage28_9_run01",
        "session_mode": SESSION_MODE_LIVE_PRIVATE,
    }


def test_build_config_happy_path():
    config = build_live_provider_session_config(
        **_valid_config_kwargs()
    )
    assert isinstance(config, Stage28_9LiveProviderSessionConfig)
    assert config.max_events == 32
    assert config.max_dispatches == 16
    assert config.session_mode == SESSION_MODE_LIVE_PRIVATE


def test_build_config_rejects_unsafe_run_id():
    kwargs = _valid_config_kwargs()
    kwargs["run_id"] = "h" + "ttps://evil"
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "run_id"


def test_build_config_rejects_unsafe_session_id():
    kwargs = _valid_config_kwargs()
    kwargs["session_id"] = ""
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "session_id"


def test_build_config_rejects_unsafe_provider_id():
    kwargs = _valid_config_kwargs()
    kwargs["provider_id"] = "bearer_token"
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "provider_id"


def test_build_config_rejects_zero_max_events():
    kwargs = _valid_config_kwargs()
    kwargs["max_events"] = 0
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "max_events"


def test_build_config_rejects_negative_max_total_retries():
    kwargs = _valid_config_kwargs()
    kwargs["max_total_retries"] = -1
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "max_total_retries"


def test_build_config_rejects_bool_for_int_fields():
    kwargs = _valid_config_kwargs()
    kwargs["max_events"] = True
    with pytest.raises(Stage28_9InvalidSessionConfigError):
        build_live_provider_session_config(**kwargs)


def test_build_config_rejects_unsafe_output_dir_label():
    kwargs = _valid_config_kwargs()
    kwargs["output_dir_safe_label"] = "a/b"
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "output_dir_safe_label"


def test_build_config_rejects_unknown_session_mode():
    kwargs = _valid_config_kwargs()
    kwargs["session_mode"] = "EXECUTE"
    with pytest.raises(Stage28_9InvalidSessionConfigError) as e:
        build_live_provider_session_config(**kwargs)
    assert e.value.field_name == "session_mode"


# ---------------------------------------------------------------------------
# Readiness verdict builder
# ---------------------------------------------------------------------------


def test_build_readiness_verdict_ready_requires_not_refused():
    verdict = build_readiness_verdict(
        ready=True, refusal_reason=REFUSAL_REASON_NOT_REFUSED,
    )
    assert isinstance(verdict, Stage28_9ReadinessVerdict)
    assert verdict.ready is True


def test_build_readiness_verdict_ready_with_refusal_reason_rejected():
    with pytest.raises(Stage28_9InvalidReadinessVerdictError):
        build_readiness_verdict(
            ready=True,
            refusal_reason=REFUSAL_REASON_NOT_LIVE,
        )


def test_build_readiness_verdict_not_ready_with_not_refused_rejected():
    with pytest.raises(Stage28_9InvalidReadinessVerdictError):
        build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_NOT_REFUSED,
        )


def test_build_readiness_verdict_rejects_non_bool_ready():
    with pytest.raises(Stage28_9InvalidReadinessVerdictError):
        build_readiness_verdict(
            ready="True",
            refusal_reason=REFUSAL_REASON_NOT_REFUSED,
        )


def test_build_readiness_verdict_rejects_unknown_refusal_reason():
    with pytest.raises(Stage28_9InvalidReadinessVerdictError):
        build_readiness_verdict(
            ready=False, refusal_reason="OTHER",
        )


# ---------------------------------------------------------------------------
# Session result builder + dict projection
# ---------------------------------------------------------------------------


def _zero_counter_kwargs() -> dict:
    return {
        name: 0
        for name in STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES
    }


def _valid_ok_result_kwargs() -> dict:
    kwargs = {
        "session_outcome": SESSION_OUTCOME_OK,
        "refusal_reason": REFUSAL_REASON_NOT_REFUSED,
        "run_id": "phx2_run01",
        "session_id": "phx2_session01",
        "provider_id": "helius_grpc",
        "provider_kind": "solana_websocket",
        "output_dir_safe_label": "scratch_run01",
        "session_mode": SESSION_MODE_LIVE_PRIVATE,
        "stop_reason": "MAX_EVENTS",
    }
    kwargs.update(_zero_counter_kwargs())
    return kwargs


def test_build_result_happy_path():
    result = build_live_provider_session_result(
        **_valid_ok_result_kwargs()
    )
    assert isinstance(result, Stage28_9LiveProviderSessionResult)
    assert (
        result.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert result.redaction_status == REDACTION_STATUS_SAFE
    assert result.schema_version == STAGE28_9_SCHEMA_VERSION


def test_build_result_refused_requires_refusal_reason():
    kwargs = _valid_ok_result_kwargs()
    kwargs["session_outcome"] = SESSION_OUTCOME_REFUSED
    # refusal_reason left as NOT_REFUSED -> must reject
    with pytest.raises(Stage28_9InvalidSessionResultError):
        build_live_provider_session_result(**kwargs)


def test_build_result_non_refused_with_refusal_reason_rejected():
    kwargs = _valid_ok_result_kwargs()
    kwargs["refusal_reason"] = REFUSAL_REASON_NOT_LIVE
    with pytest.raises(Stage28_9InvalidSessionResultError):
        build_live_provider_session_result(**kwargs)


def test_build_result_rejects_unsafe_provider_id():
    kwargs = _valid_ok_result_kwargs()
    kwargs["provider_id"] = "bearer_evil"
    with pytest.raises(Stage28_9InvalidSessionResultError) as e:
        build_live_provider_session_result(**kwargs)
    assert e.value.field_name == "provider_id"


def test_build_result_rejects_negative_counter():
    kwargs = _valid_ok_result_kwargs()
    kwargs["dispatch_success"] = -1
    with pytest.raises(Stage28_9InvalidSessionResultError) as e:
        build_live_provider_session_result(**kwargs)
    assert e.value.field_name == "dispatch_success"


def test_build_result_rejects_unsafe_webhook_identity():
    kwargs = _valid_ok_result_kwargs()
    kwargs["webhook_identity"] = "lower_case_label"
    with pytest.raises(Stage28_9InvalidSessionResultError) as e:
        build_live_provider_session_result(**kwargs)
    assert e.value.field_name == "webhook_identity"


def test_session_result_to_dict_deterministic_order():
    result = build_live_provider_session_result(
        **_valid_ok_result_kwargs()
    )
    projected = session_result_to_dict(result)
    assert list(projected.keys()) == list(
        STAGE28_9_SESSION_RESULT_FIELD_NAMES
    )
    assert (
        projected["filter_enforcement_status"]
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


def test_session_result_to_dict_rejects_non_record():
    with pytest.raises(Stage28_9InvalidSessionResultError):
        session_result_to_dict({"not": "a record"})


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_config_error_subclasses_base():
    err = Stage28_9InvalidSessionConfigError(
        field_name="x", reason="Y",
    )
    assert isinstance(err, Stage28_9LiveProviderSessionError)
    assert err.field_name == "x"
    assert err.reason == "Y"
    # repr must not contain raw secrets / URLs.
    msg = str(err)
    assert "h" + "ttps://" not in msg
    assert "bearer" not in msg.lower()


def test_invalid_result_error_subclasses_base():
    err = Stage28_9InvalidSessionResultError(
        field_name="x", reason="Y",
    )
    assert isinstance(err, Stage28_9LiveProviderSessionError)


def test_invalid_readiness_error_subclasses_base():
    err = Stage28_9InvalidReadinessVerdictError(
        field_name="x", reason="Y",
    )
    assert isinstance(err, Stage28_9LiveProviderSessionError)


# ---------------------------------------------------------------------------
# Redaction canary scan on locked constants
# ---------------------------------------------------------------------------


def test_locked_constants_carry_no_url_or_secret_substring():
    canaries = (
        "h" + "ttps://",
        "h" + "ttp://",
        "discord" + ".com",
        "discord" + "app.com",
        "hooks" + ".slack.com",
        "/webhooks/",
        "b" + "earer ",
        "a" + "uthorization:",
        "s" + "k-",
        "p" + "k-",
    )
    for value in (
        STAGE28_9_MINOR_VERSION,
        STAGE28_9_SCHEMA_VERSION,
        STAGE28_9_REDACTION_TOKEN,
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
        FILTER_ENFORCEMENT_NOTICE_TEXT,
        POLICY_MODE_PRIVATE_OPERATOR_ONLY,
    ):
        lower = value.lower()
        for needle in canaries:
            assert needle.lower() not in lower
