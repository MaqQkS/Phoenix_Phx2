"""Stage 21 errors tests (covers sanitize_detail per AUDIT-003)."""

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
    sanitize_detail,
    warning_name_for,
)


# ---------------------------------------------------------------------------
# Code-family acceptance and rejection
# ---------------------------------------------------------------------------


def test_base_error_accepts_any_known_code():
    err = Stage21Error(Stage21ErrorCode.E2100, detail="something")
    assert err.code == "E2100"
    # "something" is a safe identifier shape and passes through.
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


# ---------------------------------------------------------------------------
# sanitize_detail (AUDIT-003)
# ---------------------------------------------------------------------------


def test_sanitize_detail_preserves_short_safe_text():
    out = sanitize_detail("raw secret should never appear here")
    # Each word is shorter than the candidate threshold (8) so
    # nothing is touched.
    assert out == "raw secret should never appear here"


def test_sanitize_detail_preserves_screaming_snake_case():
    out = sanitize_detail("env var PHX2_STAGE21_PROVIDER_API_KEY missing")
    assert "PHX2_STAGE21_PROVIDER_API_KEY" in out
    assert "missing" in out


def test_sanitize_detail_preserves_snake_case_identifier():
    out = sanitize_detail("compute_fingerprint expected Optional[str] got int")
    assert "compute_fingerprint" in out
    assert "Optional" in out


def test_sanitize_detail_preserves_pascal_case():
    out = sanitize_detail("attestation_from_secret_ref got NoneType")
    assert "NoneType" in out
    assert "attestation_from_secret_ref" in out


def test_sanitize_detail_redacts_url():
    out = sanitize_detail("webhook=https://example.invalid/abc?secret=xyz")
    assert "https://" not in out
    assert "example.invalid" not in out
    assert "<redacted-url>" in out


def test_sanitize_detail_redacts_mixed_case_secret_like_token():
    secret = "PHX2_TEST_FAKE_API_KEY_zz0011aaBBccDDee"
    out = sanitize_detail(f"slot value={secret}")
    assert secret not in out
    assert "<redacted-token>" in out


def test_sanitize_detail_redacts_short_marker_in_mixed_case_token():
    marker = "zz0011aaBBccDDee"  # 16 chars, mixed case + digits
    out = sanitize_detail(f"marker is {marker} here")
    assert marker not in out
    assert "<redacted-token>" in out


def test_sanitize_detail_redacts_pure_hex_token():
    digest = "0123456789abcdef0123456789abcdef"  # 32 hex chars
    out = sanitize_detail(f"digest={digest}")
    assert digest not in out
    assert "<redacted-token>" in out


def test_sanitize_detail_redacts_uppercase_hex_token():
    digest = "DEADBEEFCAFEBABEDEADBEEFCAFEBABE"
    out = sanitize_detail(f"hash={digest}")
    assert digest not in out
    assert "<redacted-token>" in out


def test_sanitize_detail_redacts_base64_like_token():
    token = "aB1234567890abcdefghijKLMNOP+/=xyz"
    out = sanitize_detail(f"k={token}")
    assert token not in out
    assert "<redacted-token>" in out


def test_sanitize_detail_drops_newlines_and_control_chars():
    out = sanitize_detail("line one\nline two\r\nline three\ttab")
    assert "\n" not in out
    assert "\r" not in out
    assert "\t" not in out


def test_sanitize_detail_truncates_overlong_input():
    long = "x" * 500
    out = sanitize_detail(long, max_length=64)
    assert out.endswith("...")
    assert len(out) <= 64 + 3


def test_sanitize_detail_coerces_non_string_input():
    out = sanitize_detail(None)
    # None coerces to "None" -- below the candidate threshold, no
    # redaction.
    assert "None" in out


def test_sanitize_detail_does_not_leak_through_exception_str():
    secret = "PHX2_TEST_FAKE_BOT_TOKEN_zz0011aaBBccDDee"
    err = Stage21SecretError(
        Stage21ErrorCode.E2103,
        detail=f"slot value={secret}",
    )
    assert secret not in str(err)
    assert "<redacted-token>" in str(err)
    # The stored detail is the sanitized form.
    assert secret not in err.detail


def test_sanitize_detail_handles_hyphenated_lowercase_phrases():
    out = sanitize_detail("round-trip well-known should survive")
    assert "round-trip" in out
    assert "well-known" in out


def test_sanitize_detail_empty_string_returns_empty():
    assert sanitize_detail("") == ""


def test_error_message_format_omits_detail_section_when_empty():
    err = Stage21Error(Stage21ErrorCode.E2100)
    name = STAGE21_ERROR_CODE_NAMES["E2100"]
    assert str(err) == f"[E2100] {name}"
