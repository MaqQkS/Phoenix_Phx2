"""Stage 21 secret-leak tests.

The Stage 21 contract is that no secret value ever appears in
``repr`` / ``str`` / logs / manifests / telemetry / errors /
exception messages / snapshots / fixtures / committed artifacts.

These tests use a known seeded fake secret and exercise every
21.1 surface that could plausibly echo it:

  * ``Stage21Config.public_summary`` and nested structures
  * The credential-attestation bundle
  * The foundation manifest writer's JSON output
  * The repr / str of every typed record that holds a SecretRef
  * The exception messages for the config / secret / boundary
    families
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage21.config import load_config
from PHX2.stage21.constants import (
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_TELEGRAM_BOT_TOKEN,
    ENV_VAR_TELEGRAM_CHAT_ID,
)
from PHX2.stage21.errors import Stage21ConfigError, Stage21SecretError
from PHX2.stage21.models import Stage21RunId
from PHX2.stage21.stage21_1_manifest import assemble_foundation_manifest
from PHX2.stage21.telemetry_writers import (
    manifest_to_dict,
    write_foundation_manifest,
)


SAMPLE_SECRETS: dict[str, str] = {
    ENV_VAR_PROVIDER_API_KEY:
        "PHX2_TEST_FAKE_API_KEY_zz0011aaBBccDDee",
    ENV_VAR_PROVIDER_RPC_URL:
        "https://example.invalid/PHX2_TEST_RPC_zz0011aaBBccDDee",
    ENV_VAR_DISCORD_WEBHOOK_URL:
        "https://example.invalid/PHX2_TEST_WEBHOOK_zz0011aaBBccDDee",
    ENV_VAR_TELEGRAM_BOT_TOKEN:
        "PHX2_TEST_FAKE_BOT_TOKEN_zz0011aaBBccDDee",
    ENV_VAR_TELEGRAM_CHAT_ID:
        "PHX2_TEST_FAKE_CHAT_ID_zz0011aaBBccDDee",
}


def _all_secret_substrings() -> list[str]:
    """Return the seeded fake-secret substrings that must never leak.

    Each value is a complete fake secret. We also include a stable
    "marker" substring that appears in every value so a partial
    leak (e.g. only the suffix) is still caught.
    """
    out = list(SAMPLE_SECRETS.values())
    out.append("zz0011aaBBccDDee")
    return out


def _contains_any_secret(text: str) -> tuple[bool, str]:
    for s in _all_secret_substrings():
        if s in text:
            return True, s
    return False, ""


def _walk_for_secret(value: object) -> tuple[bool, str]:
    if isinstance(value, str):
        return _contains_any_secret(value)
    if isinstance(value, dict):
        for v in value.values():
            found, leaked = _walk_for_secret(v)
            if found:
                return True, leaked
        return False, ""
    if isinstance(value, (list, tuple)):
        for v in value:
            found, leaked = _walk_for_secret(v)
            if found:
                return True, leaked
        return False, ""
    return False, ""


def test_public_summary_has_no_seeded_secret():
    config = load_config(env=SAMPLE_SECRETS.copy())
    summary = config.public_summary()
    leaked, value = _walk_for_secret(summary)
    assert not leaked, f"public_summary leaked secret substring: {value!r}"


def test_credential_attestations_have_no_seeded_secret():
    config = load_config(env=SAMPLE_SECRETS.copy())
    attestations = config.credential_attestations()
    for a in attestations:
        for v in a.public_summary().values():
            if isinstance(v, str):
                found, leaked = _contains_any_secret(v)
                assert not found, (
                    f"attestation {a.name!r} leaked substring {leaked!r}"
                )


def test_repr_and_str_of_config_have_no_seeded_secret():
    config = load_config(env=SAMPLE_SECRETS.copy())
    assert not _contains_any_secret(repr(config))[0]
    assert not _contains_any_secret(str(config))[0]
    for ref in config.secret_refs():
        assert not _contains_any_secret(repr(ref))[0]
        assert not _contains_any_secret(str(ref))[0]


def test_manifest_to_dict_has_no_seeded_secret():
    config = load_config(env=SAMPLE_SECRETS.copy())
    run_id = Stage21RunId.of(
        run_id="run-id-1234",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    payload = manifest_to_dict(manifest)
    leaked, value = _walk_for_secret(payload)
    assert not leaked, f"manifest_to_dict leaked secret substring: {value!r}"


def test_manifest_writer_output_has_no_seeded_secret(tmp_path: Path):
    config = load_config(env=SAMPLE_SECRETS.copy())
    run_id = Stage21RunId.of(
        run_id="run-id-1234",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    target = tmp_path / "stage21_1_manifest.json"
    write_foundation_manifest(manifest, target)
    encoded = target.read_text(encoding="utf-8")
    found, leaked = _contains_any_secret(encoded)
    assert not found, (
        f"manifest writer output leaked secret substring: {leaked!r}"
    )


def test_no_seeded_secret_in_exception_messages():
    # Trigger a config error and a secret error, then assert
    # neither message contains a seeded secret value.
    try:
        raise Stage21ConfigError("E2101", detail="bad mode")
    except Stage21ConfigError as exc:
        assert not _contains_any_secret(str(exc))[0]

    try:
        raise Stage21SecretError("E2103", detail="bad input")
    except Stage21SecretError as exc:
        assert not _contains_any_secret(str(exc))[0]
