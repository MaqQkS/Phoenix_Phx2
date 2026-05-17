"""Stage 21 secret_redaction tests."""

from __future__ import annotations

import hashlib

import pytest

from PHX2.stage21.constants import (
    REDACTED_VALUE_SENTINEL,
    SECRET_FINGERPRINT_HEX_LENGTH,
)
from PHX2.stage21.errors import Stage21SecretError
from PHX2.stage21.secret_redaction import (
    SecretRef,
    build_secret_ref,
    compute_fingerprint,
    fingerprint_matches,
    redact_for_public,
)


SAMPLE_SECRET = "phx2-stage21-test-fake-secret-A1B2C3D4"


def _expected_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[
        :SECRET_FINGERPRINT_HEX_LENGTH
    ]


def test_compute_fingerprint_deterministic_for_present_value():
    expected = _expected_fingerprint(SAMPLE_SECRET)
    assert compute_fingerprint(SAMPLE_SECRET) == expected
    # Second call returns the same value.
    assert compute_fingerprint(SAMPLE_SECRET) == expected
    # Length is exactly the locked truncation.
    assert len(compute_fingerprint(SAMPLE_SECRET)) == 12


def test_compute_fingerprint_handles_none_and_empty():
    assert compute_fingerprint(None) == ""
    assert compute_fingerprint("") == ""


def test_compute_fingerprint_rejects_non_string():
    with pytest.raises(Stage21SecretError) as excinfo:
        compute_fingerprint(b"raw bytes")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2103"


def test_compute_fingerprint_never_contains_raw_secret():
    fp = compute_fingerprint(SAMPLE_SECRET)
    # The fingerprint is hex; a real secret with non-hex chars
    # cannot be a substring of a hex string.
    assert SAMPLE_SECRET not in fp


def test_build_secret_ref_present():
    ref = build_secret_ref("PHX2_STAGE21_PROVIDER_API_KEY", SAMPLE_SECRET)
    assert isinstance(ref, SecretRef)
    assert ref.name == "PHX2_STAGE21_PROVIDER_API_KEY"
    assert ref.present is True
    assert ref.length == len(SAMPLE_SECRET.encode("utf-8"))
    assert ref.fingerprint == _expected_fingerprint(SAMPLE_SECRET)


def test_build_secret_ref_missing_and_empty():
    ref_missing = build_secret_ref("X", None)
    ref_empty = build_secret_ref("X", "")
    for ref in (ref_missing, ref_empty):
        assert ref.present is False
        assert ref.length == 0
        assert ref.fingerprint == ""


def test_secret_ref_repr_does_not_include_secret_value():
    ref = build_secret_ref("X", SAMPLE_SECRET)
    r = repr(ref)
    s = str(ref)
    assert SAMPLE_SECRET not in r
    assert SAMPLE_SECRET not in s
    # The repr is the standard NamedTuple format, which only
    # includes the four public-safe fields.
    assert "fingerprint" in r
    assert "present" in r


def test_secret_ref_public_summary_has_only_public_fields():
    ref = build_secret_ref("X", SAMPLE_SECRET)
    summary = ref.public_summary()
    assert set(summary.keys()) == {"name", "present", "length", "fingerprint"}
    for value in summary.values():
        if isinstance(value, str):
            assert SAMPLE_SECRET not in value


def test_redact_for_public_returns_sentinel_for_present_value():
    assert redact_for_public(SAMPLE_SECRET) == REDACTED_VALUE_SENTINEL


def test_redact_for_public_returns_empty_for_missing_value():
    assert redact_for_public(None) == ""
    assert redact_for_public("") == ""


def test_fingerprint_matches_round_trip():
    fp = compute_fingerprint(SAMPLE_SECRET)
    assert fingerprint_matches(SAMPLE_SECRET, fp) is True


def test_fingerprint_matches_rejects_mismatch():
    fp = compute_fingerprint(SAMPLE_SECRET)
    assert fingerprint_matches("different-value", fp) is False


def test_fingerprint_matches_handles_empty_inputs():
    assert fingerprint_matches(SAMPLE_SECRET, "") is False
    assert fingerprint_matches(None, "") is False
    assert fingerprint_matches("", "") is False


def test_fingerprint_helper_is_stable_across_unicode_safe_inputs():
    # ASCII secrets are the common case but the helper should be
    # stable for any utf-8 input. The test pins UTF-8 stability.
    value = "phx2-stage21-key-WITH-UNICODE-éö"
    fp1 = compute_fingerprint(value)
    fp2 = compute_fingerprint(value)
    assert fp1 == fp2
    assert len(fp1) == 12
