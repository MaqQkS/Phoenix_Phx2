"""Stage 21.1 manifest assembler tests."""

from __future__ import annotations

from PHX2.stage21.config import (
    load_config,
    load_config_for_fake_mode,
)
from PHX2.stage21.constants import (
    ENV_VAR_ALLOWLIST_OPERATOR_IDS,
    ENV_VAR_PROVIDER_API_KEY,
)
from PHX2.stage21.credential_attestation import CredentialAttestation
from PHX2.stage21.models import Stage21RunId
from PHX2.stage21.stage21_1_manifest import assemble_foundation_manifest
from PHX2.stage21.telemetry_models import (
    AllowlistSummary,
    PingDispatchPlaceholder,
    RunMetadata,
    Stage21FoundationManifest,
)


def test_assemble_returns_stage21_foundation_manifest():
    config = load_config_for_fake_mode()
    run_id = Stage21RunId.of(
        run_id="aaaa1111",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    assert isinstance(manifest, Stage21FoundationManifest)
    assert isinstance(manifest.run_metadata, RunMetadata)
    assert isinstance(manifest.allowlist_summary, AllowlistSummary)
    assert manifest.pings == ()


def test_assemble_run_metadata_uses_run_id_provenance():
    config = load_config_for_fake_mode()
    run_id = Stage21RunId.of(
        run_id="xyz",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    assert manifest.run_metadata.run_id == "xyz"
    assert manifest.run_metadata.generated_at_utc_iso == "2026-05-17T12:00:00Z"
    assert manifest.run_metadata.safe_for_public_dispatch is False


def test_assemble_credential_attestations_are_typed_and_sorted():
    config = load_config(env={ENV_VAR_PROVIDER_API_KEY: "FAKE-VALUE"})
    run_id = Stage21RunId.of(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    for a in manifest.credential_attestations:
        assert isinstance(a, CredentialAttestation)
    names = [a.name for a in manifest.credential_attestations]
    assert names == sorted(names)


def test_assemble_allowlist_empty_is_fail_closed():
    config = load_config_for_fake_mode()
    run_id = Stage21RunId.of(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    assert manifest.allowlist_summary.recipients == ()
    assert manifest.allowlist_summary.count == 0
    assert manifest.allowlist_summary.fail_closed is True


def test_assemble_allowlist_with_recipients():
    config = load_config(env={ENV_VAR_ALLOWLIST_OPERATOR_IDS: "alice,bob"})
    run_id = Stage21RunId.of(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    manifest = assemble_foundation_manifest(config=config, run_id=run_id)
    assert manifest.allowlist_summary.recipients == ("alice", "bob")
    assert manifest.allowlist_summary.count == 2
    assert manifest.allowlist_summary.fail_closed is False


def test_assemble_is_pure_function_identical_inputs_identical_output():
    config = load_config_for_fake_mode()
    run_id = Stage21RunId.of(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    a = assemble_foundation_manifest(config=config, run_id=run_id)
    b = assemble_foundation_manifest(config=config, run_id=run_id)
    assert a == b


def test_ping_placeholder_record_has_locked_fields():
    assert PingDispatchPlaceholder._fields == (
        "ping_id",
        "candidate_id",
        "safe_for_public_dispatch",
        "private_preview_marker_present",
    )
