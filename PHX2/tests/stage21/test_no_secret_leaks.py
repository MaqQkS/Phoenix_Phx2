"""Stage 21 secret-leak tests (AUDIT-005 leak-matrix expansion).

The Stage 21 contract is that no secret value ever appears in
``repr`` / ``str`` / logs / manifests / telemetry / errors /
exception messages / snapshots / fixtures / committed artifacts.

The original Stage 21.1 leak test seeded a single fake-secret
value. AUDIT-005 broadens the matrix to a parametrized panel
covering:

  * URL-shaped webhook / token
  * long base64-like token
  * long hex-like token (lowercase and uppercase)
  * short token
  * empty string
  * missing / None

For each non-empty shape, the seeded value is set into the secret
env-vars and every Stage 21 leak-prone surface is walked:

  * ``Stage21Config.public_summary``
  * credential attestation bundle
  * ``Stage21FoundationManifest.run_metadata`` / etc.
  * foundation manifest's written JSON
  * ``Stage21Error.__str__`` / ``.detail`` when the seeded value
    is passed through the detail field (AUDIT-003 coverage)

Empty / missing shapes produce ``present=False`` refs and so the
leak walk is trivially clean; the matrix still exercises those
shapes to ensure no spurious output appears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from PHX2.stage21.config import load_config
from PHX2.stage21.constants import (
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_TELEGRAM_BOT_TOKEN,
    ENV_VAR_TELEGRAM_CHAT_ID,
    Stage21ErrorCode,
)
from PHX2.stage21.errors import (
    Stage21BoundaryError,
    Stage21ConfigError,
    Stage21SecretError,
)
from PHX2.stage21.models import Stage21RunId
from PHX2.stage21.stage21_1_manifest import assemble_foundation_manifest
from PHX2.stage21.telemetry_writers import (
    manifest_to_dict,
    write_foundation_manifest,
)


# Locked seeded values per shape. Each ``substrings`` entry is a
# tuple of strings that must NOT appear anywhere on any Stage 21
# leak-prone surface. ``primary`` is the value the test sets into
# the env-var slot; ``substrings`` may include the primary value
# plus a stable partial marker so a partial leak is still caught.

SHAPE_URL = (
    "https://example.invalid/PHX2_LEAK_TEST_WEBHOOK_zZ0011aBcDeF",
    ("https://example.invalid/PHX2_LEAK_TEST_WEBHOOK_zZ0011aBcDeF",
     "example.invalid", "zZ0011aBcDeF"),
)
SHAPE_BASE64 = (
    "aB1234567890abcdefghijKLMNOPqrstuvwxyz+/=zZAaBb01XX",
    ("aB1234567890abcdefghijKLMNOPqrstuvwxyz+/=zZAaBb01XX",
     "KLMNOPqrstuvwxyz+/="),
)
SHAPE_HEX_LOWER = (
    "0123456789abcdef0123456789abcdef0123456789abcdef",
    ("0123456789abcdef0123456789abcdef0123456789abcdef",
     "abcdef0123456789abcdef"),
)
SHAPE_HEX_UPPER = (
    "DEADBEEFCAFEBABEDEADBEEFCAFEBABEDEADBEEFCAFEBABE",
    ("DEADBEEFCAFEBABEDEADBEEFCAFEBABEDEADBEEFCAFEBABE",
     "CAFEBABEDEADBEEF"),
)
SHAPE_SHORT = ("aBcD", ("aBcD",))
SHAPE_EMPTY = ("", ())
SHAPE_NONE = (None, ())


_NON_NONE_SHAPES = [
    pytest.param(SHAPE_URL, id="url-webhook"),
    pytest.param(SHAPE_BASE64, id="base64-token"),
    pytest.param(SHAPE_HEX_LOWER, id="hex-lower-token"),
    pytest.param(SHAPE_HEX_UPPER, id="hex-upper-token"),
    pytest.param(SHAPE_SHORT, id="short-token"),
    pytest.param(SHAPE_EMPTY, id="empty-token"),
]
_ALL_SHAPES = _NON_NONE_SHAPES + [pytest.param(SHAPE_NONE, id="none-token")]

# Stage21Error.sanitize_detail intentionally does NOT redact short
# tokens (< 8 chars) because that surface cannot distinguish a
# short secret from a real English/identifier word without
# excessive false positives. The error-detail leak tests skip the
# short-token shape and the empty-string shape (which has no
# substring to leak). Test
# ``test_short_token_in_error_detail_is_known_limitation`` below
# pins this behavior explicitly so future contributors don't expect
# the sanitizer to cover it.
_ERROR_DETAIL_LEAK_SHAPES = [
    pytest.param(SHAPE_URL, id="url-webhook"),
    pytest.param(SHAPE_BASE64, id="base64-token"),
    pytest.param(SHAPE_HEX_LOWER, id="hex-lower-token"),
    pytest.param(SHAPE_HEX_UPPER, id="hex-upper-token"),
]


def _build_env(value: Optional[str]) -> dict[str, str]:
    """Build an env mapping that puts ``value`` into every secret slot.

    When ``value`` is ``None`` the env mapping is empty (the
    config loader treats absence and empty-string identically as
    "missing").
    """
    if value is None:
        return {}
    return {
        ENV_VAR_PROVIDER_API_KEY: value,
        ENV_VAR_PROVIDER_RPC_URL: value,
        ENV_VAR_DISCORD_WEBHOOK_URL: value,
        ENV_VAR_TELEGRAM_BOT_TOKEN: value,
        ENV_VAR_TELEGRAM_CHAT_ID: value,
    }


def _walk_for_substring(value: object, needle: str) -> bool:
    """Return True iff ``needle`` appears anywhere inside ``value``."""
    if needle == "":
        return False
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        for v in value.values():
            if _walk_for_substring(v, needle):
                return True
        return False
    if isinstance(value, (list, tuple)):
        for v in value:
            if _walk_for_substring(v, needle):
                return True
        return False
    return False


def _build_manifest_for_value(value: Optional[str]):
    env = _build_env(value)
    config = load_config(env=env)
    run_id = Stage21RunId.of(
        run_id="leak-matrix-run-id",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    return config, manifest


# ---------------------------------------------------------------------------
# Parametrized public-summary / manifest leak checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_public_summary(shape):
    value, forbidden_substrings = shape
    config, _ = _build_manifest_for_value(value)
    summary = config.public_summary()
    for needle in forbidden_substrings:
        assert not _walk_for_substring(summary, needle), (
            f"public_summary leaked substring {needle!r} for shape value "
            f"of length {len(value) if value else 0}"
        )


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_manifest_dict(shape):
    value, forbidden_substrings = shape
    _, manifest = _build_manifest_for_value(value)
    payload = manifest_to_dict(manifest)
    for needle in forbidden_substrings:
        assert not _walk_for_substring(payload, needle), (
            f"manifest_to_dict leaked substring {needle!r}"
        )


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_written_manifest_json(shape, tmp_path: Path):
    value, forbidden_substrings = shape
    _, manifest = _build_manifest_for_value(value)
    target = tmp_path / "stage21_1_manifest.json"
    write_foundation_manifest(manifest, target)
    encoded = target.read_text(encoding="utf-8")
    for needle in forbidden_substrings:
        assert needle not in encoded, (
            f"manifest writer leaked substring {needle!r}"
        )


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_config_repr_and_str(shape):
    value, forbidden_substrings = shape
    config, _ = _build_manifest_for_value(value)
    r = repr(config)
    s = str(config)
    for needle in forbidden_substrings:
        assert needle not in r, (
            f"repr(Stage21Config) leaked substring {needle!r}"
        )
        assert needle not in s, (
            f"str(Stage21Config) leaked substring {needle!r}"
        )


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_secret_ref_repr_and_str(shape):
    value, forbidden_substrings = shape
    config, _ = _build_manifest_for_value(value)
    for ref in config.secret_refs():
        r = repr(ref)
        s = str(ref)
        for needle in forbidden_substrings:
            assert needle not in r, (
                f"repr({ref.name}) leaked substring {needle!r}"
            )
            assert needle not in s, (
                f"str({ref.name}) leaked substring {needle!r}"
            )


@pytest.mark.parametrize("shape", _ALL_SHAPES)
def test_no_leak_in_credential_attestations(shape):
    value, forbidden_substrings = shape
    config, _ = _build_manifest_for_value(value)
    for attestation in config.credential_attestations():
        summary = attestation.public_summary()
        for needle in forbidden_substrings:
            assert not _walk_for_substring(summary, needle), (
                f"attestation summary leaked substring {needle!r}"
            )


# ---------------------------------------------------------------------------
# AUDIT-003 + AUDIT-005: leak via Stage21Error.detail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", _ERROR_DETAIL_LEAK_SHAPES)
def test_no_leak_when_secret_passed_through_config_error_detail(shape):
    value, forbidden_substrings = shape
    err = Stage21ConfigError(
        Stage21ErrorCode.E2101,
        detail=f"env var carried bad value: {value}",
    )
    s = str(err)
    for needle in forbidden_substrings:
        assert needle not in s, (
            f"Stage21ConfigError leaked substring {needle!r}"
        )
        assert needle not in err.detail, (
            f"Stage21ConfigError.detail leaked substring {needle!r}"
        )


@pytest.mark.parametrize("shape", _ERROR_DETAIL_LEAK_SHAPES)
def test_no_leak_when_secret_passed_through_secret_error_detail(shape):
    value, forbidden_substrings = shape
    err = Stage21SecretError(
        Stage21ErrorCode.E2103,
        detail=f"compute_fingerprint got: {value}",
    )
    s = str(err)
    for needle in forbidden_substrings:
        assert needle not in s
        assert needle not in err.detail


@pytest.mark.parametrize("shape", _ERROR_DETAIL_LEAK_SHAPES)
def test_no_leak_when_secret_passed_through_boundary_error_detail(shape):
    value, forbidden_substrings = shape
    err = Stage21BoundaryError(
        Stage21ErrorCode.E2106,
        detail=f"target path: {value}",
    )
    s = str(err)
    for needle in forbidden_substrings:
        assert needle not in s
        assert needle not in err.detail


def test_short_token_in_error_detail_is_known_limitation():
    """Pin the limitation: sanitize_detail does NOT redact short tokens.

    Short tokens (below the candidate threshold) cannot be
    distinguished from English / identifier words without
    excessive false positives. The Stage 21 dispatch path never
    routes raw secret values into error detail strings; the
    config / manifest / repr surfaces still protect against
    short-token leaks via the SecretRef boundary, which holds the
    raw value only inside ``config.py`` and never elsewhere.

    If future Stage 21.x callers need stronger guarantees, they
    should pass typed slot identifiers rather than raw values
    into error detail.
    """
    short = "aBcD"
    err = Stage21SecretError(
        Stage21ErrorCode.E2103,
        detail=f"slot got: {short}",
    )
    # Short tokens are intentionally preserved.
    assert short in str(err)
    assert short in err.detail


def test_short_token_in_secret_ref_does_not_leak_into_public_surface():
    # The SecretRef boundary protects short tokens regardless of
    # the sanitizer behavior above: short tokens never appear in
    # repr / str / public_summary.
    config, _ = _build_manifest_for_value("aBcD")
    for ref in config.secret_refs():
        assert "aBcD" not in repr(ref)
        assert "aBcD" not in str(ref)
        assert "aBcD" not in str(ref.public_summary())


# ---------------------------------------------------------------------------
# AUDIT-005: missing / None env-var slot produces clean public surface
# ---------------------------------------------------------------------------


def test_none_token_results_in_empty_fingerprint():
    config, _ = _build_manifest_for_value(None)
    for ref in config.secret_refs():
        assert ref.present is False
        assert ref.length == 0
        assert ref.fingerprint == ""


def test_empty_token_results_in_empty_fingerprint():
    config, _ = _build_manifest_for_value("")
    for ref in config.secret_refs():
        assert ref.present is False
        assert ref.length == 0
        assert ref.fingerprint == ""


def test_short_token_produces_fingerprint_but_no_value_leak():
    config, _ = _build_manifest_for_value("aBcD")
    for ref in config.secret_refs():
        assert ref.present is True
        assert ref.length == 4
        assert ref.fingerprint  # 12 hex chars
        # Even a 4-char raw secret never appears in the public summary.
        assert "aBcD" not in repr(ref)
        assert "aBcD" not in str(ref)
