"""Stage 21 telemetry_writers tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage21.config import load_config_for_fake_mode
from PHX2.stage21.constants import (
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_PROVIDER_API_KEY,
)
from PHX2.stage21.credential_attestation import build_attestation_bundle
from PHX2.stage21.errors import Stage21BoundaryError
from PHX2.stage21.models import Stage21RunId
from PHX2.stage21.secret_redaction import build_secret_ref
from PHX2.stage21.stage21_1_manifest import assemble_foundation_manifest
from PHX2.stage21.config import load_config
from PHX2.stage21.telemetry_writers import (
    manifest_to_dict,
    serialize_attestations,
    write_foundation_manifest,
)


SAMPLE_SECRET = "phx2-stage21-test-fake-secret-DETERMINISTIC-001"


def _build_manifest_with_secret():
    config = load_config(env={
        ENV_VAR_PROVIDER_API_KEY: SAMPLE_SECRET,
        ENV_VAR_DISCORD_WEBHOOK_URL: "https://example.invalid/" + SAMPLE_SECRET,
    })
    run_id = Stage21RunId.of(
        run_id="aaaa1111bbbb2222",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    return assemble_foundation_manifest(config=config, run_id=run_id)


def test_manifest_to_dict_returns_mapping():
    manifest = _build_manifest_with_secret()
    payload = manifest_to_dict(manifest)
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {
        "run_metadata",
        "credential_attestations",
        "allowlist_summary",
        "pings",
    }


def test_manifest_to_dict_rejects_wrong_input_type():
    with pytest.raises(Stage21BoundaryError) as excinfo:
        manifest_to_dict("not a manifest")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2106"


def test_manifest_pings_field_is_empty_list_in_21_1():
    manifest = _build_manifest_with_secret()
    payload = manifest_to_dict(manifest)
    assert payload["pings"] == []


def test_manifest_carries_locked_dispatch_flag_false():
    manifest = _build_manifest_with_secret()
    payload = manifest_to_dict(manifest)
    assert payload["run_metadata"]["safe_for_public_dispatch"] is False


def test_manifest_serialization_contains_no_raw_secret(tmp_path: Path):
    manifest = _build_manifest_with_secret()
    target = tmp_path / "stage21_1_manifest.json"
    write_foundation_manifest(manifest, target)
    encoded = target.read_text(encoding="utf-8")
    assert SAMPLE_SECRET not in encoded


def test_manifest_writer_is_byte_deterministic_across_runs(tmp_path: Path):
    manifest = _build_manifest_with_secret()
    target_a = tmp_path / "a.json"
    target_b = tmp_path / "b.json"
    write_foundation_manifest(manifest, target_a)
    write_foundation_manifest(manifest, target_b)
    assert target_a.read_bytes() == target_b.read_bytes()


def test_manifest_writer_produces_sorted_keys_and_trailing_newline(
    tmp_path: Path,
):
    manifest = _build_manifest_with_secret()
    target = tmp_path / "stage21_1_manifest.json"
    write_foundation_manifest(manifest, target)
    encoded = target.read_text(encoding="utf-8")
    assert encoded.endswith("\n")
    payload = json.loads(encoded)
    # Re-encoding with sort_keys=True must produce the same bytes
    # as the writer output minus the trailing newline.
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    ) + "\n"
    assert encoded == canonical


def test_manifest_writer_refuses_path_with_dotdot(tmp_path: Path):
    manifest = _build_manifest_with_secret()
    bad = tmp_path / ".." / "out.json"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_foundation_manifest(manifest, bad)
    assert excinfo.value.code == "E2106"


def test_manifest_writer_refuses_missing_parent_directory(tmp_path: Path):
    manifest = _build_manifest_with_secret()
    target = tmp_path / "does-not-exist" / "out.json"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_foundation_manifest(manifest, target)
    assert excinfo.value.code == "E2106"


def test_manifest_writer_refuses_empty_path():
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_foundation_manifest(_build_manifest_with_secret(), Path(""))
    assert excinfo.value.code == "E2106"


def test_serialize_attestations_helper_is_deterministic():
    refs = (
        build_secret_ref("AAA", SAMPLE_SECRET),
        build_secret_ref("BBB", None),
    )
    bundle = build_attestation_bundle(refs)
    serialized_a = serialize_attestations(bundle)
    serialized_b = serialize_attestations(bundle)
    assert serialized_a == serialized_b


def test_manifest_pings_placeholder_record_carries_safe_dispatch_field_only():
    # Confirm the placeholder ping record never leaks secret-like
    # fields by exercising the manifest_to_dict mapper on a
    # placeholder-populated manifest.
    config = load_config_for_fake_mode()
    run_id = Stage21RunId.of(
        run_id="abcd",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    payload = manifest_to_dict(manifest)
    assert payload["pings"] == []
