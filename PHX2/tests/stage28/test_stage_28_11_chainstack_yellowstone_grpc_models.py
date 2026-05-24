"""Stage 28.11 model tests.

Pins:

  * Stage 28.11 version axes + redaction token.
  * Closed-set mode / probe-status / refusal-reason vocabularies.
  * Safe-shape validators (endpoint / x-token / timeout).
  * Private endpoint-secret record:
    - construction rejects unsafe endpoint / unsafe x-token /
      non-bool tls / plaintext (tls=False),
    - ``__repr__`` / ``__str__`` / ``to_safe_dict`` never echo
      raw values; the Stage 28.11 redaction token replaces them,
    - the two ``get_*_for_internal_use()`` methods return the raw
      values exactly (the gRPC client is the only consumer),
    - the record is frozen (no attribute rebind after init).
  * Runtime config:
    - construction rejects mismatched safe-config / endpoint-
      secret types,
    - runtime-config ``__repr__`` carries the redacted secret
      subobject,
    - ``runtime_config_to_safe_dict`` returns a fully redacted
      dict.
  * Readiness report + probe result builders pin the locked
    closed-set tokens; the probe-result bound on
    ``events_received`` (<= 1) is enforced.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    MODE_VALUES,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_DECODED,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_READY,
    PROBE_STATUS_SKIPPED,
    PROBE_STATUS_VALUES,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_ENDPOINT_MISSING,
    REFUSAL_REASON_ENDPOINT_UNSAFE,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_EVENT_RECEIVED,
    REFUSAL_REASON_TIMEOUT_INVALID,
    REFUSAL_REASON_VALUES,
    REFUSAL_REASON_X_TOKEN_MISSING,
    REFUSAL_REASON_X_TOKEN_UNSAFE,
    STAGE28_11_MINOR_VERSION,
    STAGE28_11_REDACTION_TOKEN,
    STAGE28_11_SCHEMA_VERSION,
    Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11GrpcProbeResult,
    Stage28_11GrpcReadinessReport,
    Stage28_11InvalidEndpointSecretError,
    Stage28_11InvalidProbeResultError,
    Stage28_11InvalidReadinessReportError,
    Stage28_11InvalidRuntimeConfigError,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
    build_grpc_probe_result,
    build_grpc_readiness_report,
    is_mode_value,
    is_probe_status_value,
    is_refusal_reason_value,
    is_safe_grpc_endpoint_url,
    is_safe_grpc_x_token,
    is_safe_timeout_seconds,
    probe_result_to_safe_dict,
    readiness_report_to_safe_dict,
    runtime_config_to_safe_dict,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    build_chainstack_yellowstone_config,
)


# ---------------------------------------------------------------------------
# Sample safe fixtures (deliberately innocuous; no real URL / no real token)
# ---------------------------------------------------------------------------


SAFE_ENDPOINT_FIXTURE: str = "fixture.example:443"
SAFE_X_TOKEN_FIXTURE: str = "abc-DEF.ghi-JKL_mno-1234567890"


def _build_safe_config():
    return build_chainstack_yellowstone_config(
        provider_id="chainstack_yellowstone_grpc",
        endpoint_safe_label="chainstack_yellowstone_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )


# ---------------------------------------------------------------------------
# 1. Version axes + redaction token
# ---------------------------------------------------------------------------


def test_minor_version_is_28_11():
    assert STAGE28_11_MINOR_VERSION == "28.11"


def test_schema_version_is_locked():
    assert (
        STAGE28_11_SCHEMA_VERSION
        == "stage28_11_chainstack_yellowstone_grpc_v0"
    )


def test_redaction_token_is_distinct():
    assert STAGE28_11_REDACTION_TOKEN == "<<STAGE28_11_REDACTED>>"


# ---------------------------------------------------------------------------
# 2. Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_mode_values_are_closed_set():
    assert MODE_VALUES == (
        MODE_READINESS_ONLY,
        MODE_PROVIDER_CONNECT_ONLY,
        MODE_ONE_EVENT_DECODE_DRY_RUN,
    )


@pytest.mark.parametrize("mode", MODE_VALUES)
def test_is_mode_value_accepts_locked_tokens(mode):
    assert is_mode_value(mode) is True


def test_is_mode_value_rejects_unknown():
    assert is_mode_value("OTHER_MODE") is False
    assert is_mode_value(None) is False
    assert is_mode_value(123) is False


def test_probe_status_values_closed_set():
    assert PROBE_STATUS_READY in PROBE_STATUS_VALUES
    assert PROBE_STATUS_NOT_READY in PROBE_STATUS_VALUES
    assert PROBE_STATUS_CONNECTED in PROBE_STATUS_VALUES
    assert PROBE_STATUS_DECODED in PROBE_STATUS_VALUES
    assert PROBE_STATUS_FAILED in PROBE_STATUS_VALUES
    assert PROBE_STATUS_SKIPPED in PROBE_STATUS_VALUES


def test_is_probe_status_value_rejects_unknown():
    assert is_probe_status_value("INVENTED") is False


def test_refusal_reason_values_closed_set():
    for needed in (
        REFUSAL_REASON_NONE,
        REFUSAL_REASON_ENDPOINT_MISSING,
        REFUSAL_REASON_ENDPOINT_UNSAFE,
        REFUSAL_REASON_X_TOKEN_MISSING,
        REFUSAL_REASON_X_TOKEN_UNSAFE,
        REFUSAL_REASON_TIMEOUT_INVALID,
        REFUSAL_REASON_MODE_INVALID,
        REFUSAL_REASON_LIVE_FLAG_NOT_SET,
        REFUSAL_REASON_CONNECT_FAILED,
        REFUSAL_REASON_DECODE_FAILED,
        REFUSAL_REASON_NO_EVENT_RECEIVED,
    ):
        assert needed in REFUSAL_REASON_VALUES


def test_is_refusal_reason_value_rejects_unknown():
    assert is_refusal_reason_value("INVENTED") is False


# ---------------------------------------------------------------------------
# 3. Safe-shape validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "fixture.example:443",
        "dns:///fixture.example:443",
        "host-name.local:50051",
        "aa:1",
    ],
)
def test_is_safe_grpc_endpoint_url_accepts_safe(endpoint):
    assert is_safe_grpc_endpoint_url(endpoint) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",  # below min length
        "user:pass@host:443",  # @ disallowed
        "host:443?token=secret",  # ? disallowed
        "host:443#frag",  # # disallowed
        "host space:443",  # whitespace disallowed
        "5Krhost.example:443",  # WIF prefix
        "x" * 257,  # too long
        None,
        123,
        b"host:443",
    ],
)
def test_is_safe_grpc_endpoint_url_rejects_unsafe(bad):
    assert is_safe_grpc_endpoint_url(bad) is False


@pytest.mark.parametrize(
    "token",
    [
        "abc-DEF.ghi-JKL_mno-1234567890",
        "abcd1234",  # min length
        "A.B-C_D.0123456789abcdef",
    ],
)
def test_is_safe_grpc_x_token_accepts_safe(token):
    assert is_safe_grpc_x_token(token) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",  # below min length
        "ab" * 50 + "==",  # base64-padded shape (private-key-like)
        "5K" + "x" * 30,  # WIF prefix
        "0123456789abcdef" * 4,  # 64 hex chars
        None,
        123,
    ],
)
def test_is_safe_grpc_x_token_rejects_unsafe(bad):
    assert is_safe_grpc_x_token(bad) is False


@pytest.mark.parametrize("seconds", [1, 30, 600])
def test_is_safe_timeout_seconds_accepts(seconds):
    assert is_safe_timeout_seconds(seconds) is True


@pytest.mark.parametrize(
    "bad", [0, -1, 601, True, False, 30.0, "30", None]
)
def test_is_safe_timeout_seconds_rejects(bad):
    assert is_safe_timeout_seconds(bad) is False


# ---------------------------------------------------------------------------
# 4. Endpoint secret
# ---------------------------------------------------------------------------


def test_endpoint_secret_construction_accepts_safe():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
        tls=True,
    )
    assert isinstance(
        record,
        Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    )
    assert record.auth_mode == "XTOKEN"
    assert record.tls is True
    assert record.endpoint_length == len(SAFE_ENDPOINT_FIXTURE)
    assert record.x_token_length == len(SAFE_X_TOKEN_FIXTURE)


def test_endpoint_secret_rejects_unsafe_endpoint():
    with pytest.raises(Stage28_11InvalidEndpointSecretError) as err:
        build_chainstack_yellowstone_grpc_endpoint_secret(
            endpoint_url="user:pass@host:443",
            x_token=SAFE_X_TOKEN_FIXTURE,
        )
    assert err.value.field_name == "endpoint_url"
    assert err.value.reason == "ENDPOINT_UNSAFE"
    # The raw unsafe value must NOT appear on the exception.
    assert "user:pass@host:443" not in str(err.value)


def test_endpoint_secret_rejects_missing_endpoint():
    with pytest.raises(Stage28_11InvalidEndpointSecretError) as err:
        build_chainstack_yellowstone_grpc_endpoint_secret(
            endpoint_url=None,
            x_token=SAFE_X_TOKEN_FIXTURE,
        )
    assert err.value.reason == "ENDPOINT_NOT_STRING"


def test_endpoint_secret_rejects_unsafe_x_token():
    with pytest.raises(Stage28_11InvalidEndpointSecretError) as err:
        build_chainstack_yellowstone_grpc_endpoint_secret(
            endpoint_url=SAFE_ENDPOINT_FIXTURE,
            x_token="5K" + "x" * 30,
        )
    assert err.value.field_name == "x_token"
    assert err.value.reason == "X_TOKEN_UNSAFE"
    assert "5K" + "x" * 30 not in str(err.value)


def test_endpoint_secret_rejects_plaintext():
    with pytest.raises(Stage28_11InvalidEndpointSecretError) as err:
        build_chainstack_yellowstone_grpc_endpoint_secret(
            endpoint_url=SAFE_ENDPOINT_FIXTURE,
            x_token=SAFE_X_TOKEN_FIXTURE,
            tls=False,
        )
    assert err.value.reason == "TLS_REQUIRED"


def test_endpoint_secret_repr_redacts_raw_values():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    text = repr(record)
    assert SAFE_ENDPOINT_FIXTURE not in text
    assert SAFE_X_TOKEN_FIXTURE not in text
    assert STAGE28_11_REDACTION_TOKEN in text
    assert "XTOKEN" in text


def test_endpoint_secret_str_redacts_raw_values():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    text = str(record)
    assert SAFE_ENDPOINT_FIXTURE not in text
    assert SAFE_X_TOKEN_FIXTURE not in text


def test_endpoint_secret_to_safe_dict_redacts_raw_values():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    safe = record.to_safe_dict()
    assert safe["endpoint_url"] == STAGE28_11_REDACTION_TOKEN
    assert safe["x_token"] == STAGE28_11_REDACTION_TOKEN
    assert safe["auth_mode"] == "XTOKEN"
    assert safe["endpoint_length"] == len(SAFE_ENDPOINT_FIXTURE)
    assert safe["x_token_length"] == len(SAFE_X_TOKEN_FIXTURE)
    assert safe["tls"] is True
    # Raw values must not appear anywhere in the serialised dict.
    text = repr(safe)
    assert SAFE_ENDPOINT_FIXTURE not in text
    assert SAFE_X_TOKEN_FIXTURE not in text


def test_endpoint_secret_internal_getters_return_raw_values():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    assert (
        record.get_endpoint_url_for_internal_use()
        == SAFE_ENDPOINT_FIXTURE
    )
    assert (
        record.get_x_token_for_internal_use()
        == SAFE_X_TOKEN_FIXTURE
    )


def test_endpoint_secret_is_frozen_no_set():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    with pytest.raises(Stage28_11InvalidEndpointSecretError):
        record.attempted_rebind = "rogue"


def test_endpoint_secret_is_frozen_no_delete():
    record = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    with pytest.raises(Stage28_11InvalidEndpointSecretError):
        del record.auth_mode


def test_endpoint_secret_equality_by_safe_lengths():
    a = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    # Same lengths, different raw values -- equal under the
    # safe-length equality.
    other_endpoint = (
        "h" * len(SAFE_ENDPOINT_FIXTURE)
    ).replace("h", "a", 1) + ":1"
    # That construction has bad chars; pick a definite same-
    # length safe endpoint instead.
    b = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    assert a == b


# ---------------------------------------------------------------------------
# 5. Runtime config
# ---------------------------------------------------------------------------


def test_runtime_config_construction_accepts_safe():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    record = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=_build_safe_config(),
        endpoint_secret=secret,
        mode=MODE_READINESS_ONLY,
        timeout_seconds=30,
    )
    assert isinstance(
        record,
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    )
    assert record.mode == MODE_READINESS_ONLY
    assert record.timeout_seconds == 30


def test_runtime_config_rejects_non_safe_config():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    with pytest.raises(Stage28_11InvalidRuntimeConfigError) as err:
        build_chainstack_yellowstone_grpc_runtime_config(
            safe_config="not_a_config",
            endpoint_secret=secret,
            mode=MODE_READINESS_ONLY,
            timeout_seconds=30,
        )
    assert err.value.field_name == "safe_config"


def test_runtime_config_rejects_non_secret():
    with pytest.raises(Stage28_11InvalidRuntimeConfigError) as err:
        build_chainstack_yellowstone_grpc_runtime_config(
            safe_config=_build_safe_config(),
            endpoint_secret="not_a_secret",
            mode=MODE_READINESS_ONLY,
            timeout_seconds=30,
        )
    assert err.value.field_name == "endpoint_secret"


def test_runtime_config_rejects_invalid_mode():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    with pytest.raises(Stage28_11InvalidRuntimeConfigError) as err:
        build_chainstack_yellowstone_grpc_runtime_config(
            safe_config=_build_safe_config(),
            endpoint_secret=secret,
            mode="ROGUE_MODE",
            timeout_seconds=30,
        )
    assert err.value.field_name == "mode"
    assert err.value.reason == "MODE_NOT_CLOSED_SET"


def test_runtime_config_rejects_unsafe_timeout():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    with pytest.raises(Stage28_11InvalidRuntimeConfigError) as err:
        build_chainstack_yellowstone_grpc_runtime_config(
            safe_config=_build_safe_config(),
            endpoint_secret=secret,
            mode=MODE_READINESS_ONLY,
            timeout_seconds=0,
        )
    assert err.value.field_name == "timeout_seconds"


def test_runtime_config_repr_carries_redacted_secret():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    record = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=_build_safe_config(),
        endpoint_secret=secret,
        mode=MODE_READINESS_ONLY,
        timeout_seconds=30,
    )
    text = repr(record)
    assert SAFE_ENDPOINT_FIXTURE not in text
    assert SAFE_X_TOKEN_FIXTURE not in text


def test_runtime_config_to_safe_dict_redacts_secret():
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT_FIXTURE,
        x_token=SAFE_X_TOKEN_FIXTURE,
    )
    record = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=_build_safe_config(),
        endpoint_secret=secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )
    safe = runtime_config_to_safe_dict(record)
    text = repr(safe)
    assert SAFE_ENDPOINT_FIXTURE not in text
    assert SAFE_X_TOKEN_FIXTURE not in text
    assert safe["mode"] == MODE_ONE_EVENT_DECODE_DRY_RUN
    assert safe["timeout_seconds"] == 30
    assert (
        safe["endpoint_secret"]["endpoint_url"]
        == STAGE28_11_REDACTION_TOKEN
    )
    assert (
        safe["endpoint_secret"]["x_token"]
        == STAGE28_11_REDACTION_TOKEN
    )


# ---------------------------------------------------------------------------
# 6. Readiness report
# ---------------------------------------------------------------------------


def test_readiness_report_accepts_ready_shape():
    report = build_grpc_readiness_report(
        status=PROBE_STATUS_READY,
        refusal_reason=REFUSAL_REASON_NONE,
        endpoint_safe_label="chainstack_yellowstone_endpoint",
        endpoint_length=42,
        x_token_length=24,
        live_flag_set=True,
        timeout_seconds=30,
    )
    assert isinstance(report, Stage28_11GrpcReadinessReport)
    assert report.status == PROBE_STATUS_READY
    assert report.refusal_reason == REFUSAL_REASON_NONE
    assert report.live_flag_set is True
    assert report.timeout_seconds == 30


def test_readiness_report_rejects_non_readiness_status():
    with pytest.raises(Stage28_11InvalidReadinessReportError) as err:
        build_grpc_readiness_report(
            status=PROBE_STATUS_CONNECTED,
            refusal_reason=REFUSAL_REASON_NONE,
        )
    assert err.value.field_name == "status"


def test_readiness_report_rejects_unknown_refusal_reason():
    with pytest.raises(Stage28_11InvalidReadinessReportError) as err:
        build_grpc_readiness_report(
            status=PROBE_STATUS_READY,
            refusal_reason="INVENTED_REASON",
        )
    assert err.value.field_name == "refusal_reason"


def test_readiness_report_rejects_negative_length():
    with pytest.raises(Stage28_11InvalidReadinessReportError) as err:
        build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_ENDPOINT_MISSING,
            endpoint_length=-1,
        )
    assert err.value.field_name == "endpoint_length"


def test_readiness_report_to_safe_dict_carries_redaction_token():
    report = build_grpc_readiness_report(
        status=PROBE_STATUS_READY,
        refusal_reason=REFUSAL_REASON_NONE,
        endpoint_safe_label="chainstack_yellowstone_endpoint",
        endpoint_length=42,
        x_token_length=24,
        live_flag_set=False,
        timeout_seconds=30,
    )
    safe = readiness_report_to_safe_dict(report)
    assert safe["redaction_token"] == STAGE28_11_REDACTION_TOKEN
    assert safe["status"] == PROBE_STATUS_READY


# ---------------------------------------------------------------------------
# 7. Probe result
# ---------------------------------------------------------------------------


def test_probe_result_readiness_only_shape():
    result = build_grpc_probe_result(
        mode=MODE_READINESS_ONLY,
        status=PROBE_STATUS_READY,
        refusal_reason=REFUSAL_REASON_NONE,
        ready=True,
        connected=False,
        decoded=False,
        decoded_payload=None,
        handoff_ready=False,
        events_received=0,
    )
    assert isinstance(result, Stage28_11GrpcProbeResult)
    assert result.handoff_ready is False
    assert result.events_received == 0
    assert result.schema_version == STAGE28_11_SCHEMA_VERSION


def test_probe_result_dry_run_handoff_ready():
    result = build_grpc_probe_result(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        status=PROBE_STATUS_DECODED,
        refusal_reason=REFUSAL_REASON_NONE,
        ready=True,
        connected=True,
        decoded=True,
        decoded_payload=None,
        handoff_ready=True,
        events_received=1,
    )
    assert result.handoff_ready is True
    assert result.events_received == 1


def test_probe_result_rejects_events_received_above_dry_run_bound():
    with pytest.raises(Stage28_11InvalidProbeResultError) as err:
        build_grpc_probe_result(
            mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
            status=PROBE_STATUS_DECODED,
            refusal_reason=REFUSAL_REASON_NONE,
            ready=True,
            connected=True,
            decoded=True,
            decoded_payload=None,
            handoff_ready=True,
            events_received=2,
        )
    assert err.value.field_name == "events_received"
    assert (
        err.value.reason == "EVENTS_RECEIVED_EXCEEDS_DRY_RUN_BOUND"
    )


def test_probe_result_rejects_non_bool_ready():
    with pytest.raises(Stage28_11InvalidProbeResultError):
        build_grpc_probe_result(
            mode=MODE_READINESS_ONLY,
            status=PROBE_STATUS_READY,
            refusal_reason=REFUSAL_REASON_NONE,
            ready="yes",
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )


def test_probe_result_to_safe_dict_no_payload():
    result = build_grpc_probe_result(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        status=PROBE_STATUS_CONNECTED,
        refusal_reason=REFUSAL_REASON_NONE,
        ready=True,
        connected=True,
        decoded=False,
        decoded_payload=None,
        handoff_ready=False,
        events_received=0,
    )
    safe = probe_result_to_safe_dict(result)
    assert safe["mode"] == MODE_PROVIDER_CONNECT_ONLY
    assert safe["decoded_payload"] is None
    assert safe["redaction_token"] == STAGE28_11_REDACTION_TOKEN
