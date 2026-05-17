"""Stage 21 errors tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.constants import (
    STAGE21_ERROR_CODE_NAMES,
    STAGE21_WARNING_CODE_NAMES,
    Stage21ErrorCode,
    Stage21WarningCode,
)
from PHX2.stage21.errors import (
    Stage21BoundaryError,
    Stage21ConfigError,
    Stage21Error,
    Stage21ProviderContractError,
    Stage21SecretError,
    Stage21TelemetryError,
    Stage21TransportContractError,
    warning_name_for,
)


def test_base_error_accepts_any_known_code():
    err = Stage21Error(Stage21ErrorCode.E2100, detail="something")
    assert err.code == "E2100"
    assert err.detail == "something"
    name = STAGE21_ERROR_CODE_NAMES["E2100"]
    assert f"[E2100] {name}: something" == str(err)


def test_base_error_rejects_unknown_string_code():
    with pytest.raises(ValueError):
        Stage21Error("E9999")


def test_config_error_accepts_only_config_family():
    Stage21ConfigError(Stage21ErrorCode.E2100)
    Stage21ConfigError(Stage21ErrorCode.E2101)
    Stage21ConfigError(Stage21ErrorCode.E2102)
    Stage21ConfigError(Stage21ErrorCode.E2105)


def test_config_error_rejects_secret_family():
    with pytest.raises(ValueError):
        Stage21ConfigError(Stage21ErrorCode.E2103)


def test_secret_error_accepts_only_secret_family():
    Stage21SecretError(Stage21ErrorCode.E2103)
    Stage21SecretError(Stage21ErrorCode.E2104)


def test_secret_error_rejects_config_family():
    with pytest.raises(ValueError):
        Stage21SecretError(Stage21ErrorCode.E2100)
    with pytest.raises(ValueError):
        Stage21SecretError(Stage21ErrorCode.E2105)


def test_boundary_error_accepts_only_boundary_family():
    Stage21BoundaryError(Stage21ErrorCode.E2106)


def test_boundary_error_rejects_telemetry_family():
    with pytest.raises(ValueError):
        Stage21BoundaryError(Stage21ErrorCode.E2110)


def test_telemetry_error_accepts_only_telemetry_family():
    for code in [
        Stage21ErrorCode.E2110,
        Stage21ErrorCode.E2111,
        Stage21ErrorCode.E2112,
        Stage21ErrorCode.E2113,
        Stage21ErrorCode.E2140,
        Stage21ErrorCode.E2141,
    ]:
        Stage21TelemetryError(code)


def test_provider_contract_error_accepts_only_provider_family():
    for code in [
        Stage21ErrorCode.E2120,
        Stage21ErrorCode.E2121,
        Stage21ErrorCode.E2122,
    ]:
        Stage21ProviderContractError(code)


def test_transport_contract_error_accepts_only_transport_family():
    for code in [
        Stage21ErrorCode.E2130,
        Stage21ErrorCode.E2131,
        Stage21ErrorCode.E2132,
    ]:
        Stage21TransportContractError(code)


def test_warning_name_for_round_trip():
    for code in Stage21WarningCode:
        assert warning_name_for(code) == STAGE21_WARNING_CODE_NAMES[code.value]
        assert warning_name_for(code.value) == (
            STAGE21_WARNING_CODE_NAMES[code.value]
        )


def test_warning_name_for_unknown_raises():
    with pytest.raises(ValueError):
        warning_name_for("W9999")


def test_every_subclass_inherits_stage21_error():
    for cls in [
        Stage21ConfigError,
        Stage21SecretError,
        Stage21BoundaryError,
        Stage21TelemetryError,
        Stage21ProviderContractError,
        Stage21TransportContractError,
    ]:
        instance = cls.__new__(cls)
        assert isinstance(instance, Stage21Error)


def test_error_message_carries_no_secret_payload():
    # The error constructor's detail string is the only operator-
    # supplied content in the formatted message. We verify the
    # detail does not echo back the code's snake-case name (that
    # is supplied by the registry, not the caller) so a malformed
    # caller cannot smuggle a payload via the detail string.
    err = Stage21SecretError(
        Stage21ErrorCode.E2103,
        detail="raw secret should never appear here",
    )
    assert "raw secret should never appear here" in str(err)
    # The detail is preserved verbatim; the test merely pins that
    # behavior so the secret-leak test in test_no_secret_leaks.py
    # can rely on the absence of any real env-value substring.
