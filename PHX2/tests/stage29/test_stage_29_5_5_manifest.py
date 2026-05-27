"""Stage 29.5.5 manifest cross-checks.

Pins:

  * Production inventory tuple (5 .py files).
  * Doc inventory tuple (1 .md file).
  * Test inventory tuple (16 test files).
  * Zero env-read admission.
  * Zero outbound-network admission.
  * Locked schema version constants (renderer / rendered-block
    / recorded-entry / recorder / side-channel writer /
    side-channel bundle / side-channel filename).
  * Locked enforcement / redaction tokens.
  * Forbidden-surface tuple structure and contents.
  * The Stage 29.5.5 forbidden-surface tuple NO LONGER contains
    ``"formatted Discord rendering"`` -- Stage 29.5.5 unlocks
    exactly that surface for the OFFLINE side-channel path.
  * The Stage 29.5.5 forbidden-surface tuple DOES still contain
    ``"Discord dispatch behavior change"`` (the live dispatched
    body remains unchanged) AND
    ``"injecting rendered block into live dispatched Discord
    body"`` (the rendered block is side-channel only).
  * The Stage 29.5.5 forbidden-surface tuple ALSO pins
    ``"Stage 29.5.4 manifest inventory change"`` (locked).
  * Sentinel references for the renderer + rendered-block +
    recorded-entry + recorder + side-channel writer classes
    exist at import time.
"""

from __future__ import annotations


def test_production_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_PRODUCTION_PY_BASENAMES,
    )
    assert STAGE29_5_5_PRODUCTION_PY_BASENAMES == (
        "stage29_5_5_render_models.py",
        "stage29_5_5_private_discord_migration_context_renderer.py",
        "stage29_5_5_migration_context_recorder.py",
        "stage29_5_5_side_channel_artifact_writer.py",
        "stage29_5_5_manifest.py",
    )


def test_doc_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_DOC_BASENAMES,
    )
    assert STAGE29_5_5_DOC_BASENAMES == (
        "STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md",
    )


def test_test_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_TEST_BASENAMES,
    )
    assert STAGE29_5_5_TEST_BASENAMES == (
        "test_stage_29_5_5_render_models.py",
        "test_stage_29_5_5_renderer.py",
        "test_stage_29_5_5_status_matrix.py",
        "test_stage_29_5_5_migration_context_recorder.py",
        "test_stage_29_5_5_side_channel_artifact_writer.py",
        "test_stage_29_5_5_redaction.py",
        "test_stage_29_5_5_stage29_3_integration.py",
        "test_stage_29_5_5_default_preserves_no_renderer_path.py",
        "test_stage_29_5_5_no_duplicate_dispatch.py",
        "test_stage_29_5_5_no_live_surface.py",
        "test_stage_29_5_5_no_enforcement_activation.py",
        "test_stage_29_5_5_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_5_boundaries.py",
        "test_stage_29_5_5_manifest.py",
        "test_stage_29_5_5_spec_lock.py",
        "test_stage_29_5_5_counter_invariants.py",
    )


def test_env_read_admission_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_5_ENV_READ_ADMITTED_BASENAMES == ()


def test_outbound_network_admission_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )


def test_renderer_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION
        == "stage29_5_5_v0_private_discord_migration_context_renderer"
    )


def test_rendered_block_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        == "stage29_5_5_v0_rendered_migration_context_block"
    )


def test_recorded_entry_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
        == "stage29_5_5_v0_recorded_render_entry"
    )


def test_recorder_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION
        == "stage29_5_5_v0_migration_context_recorder"
    )


def test_side_channel_writer_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION
        == "stage29_5_5_v0_side_channel_artifact_writer"
    )


def test_side_channel_bundle_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION
        == "stage29_5_5_v0_side_channel_artifact_bundle"
    )


def test_side_channel_artifact_filename_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME,
    )
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
        == "stage29_5_5_side_channel_migration_context_artifact.json"
    )


def test_locked_enforcement_token_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_FILTER_ENFORCEMENT_STATUS_LOCKED,
    )
    assert (
        STAGE29_5_5_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_locked_redaction_token_pin() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_REDACTION_STATUS_LOCKED,
    )
    assert STAGE29_5_5_REDACTION_STATUS_LOCKED == "SAFE"


def test_forbidden_surfaces_is_nonempty_tuple() -> None:
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_FORBIDDEN_SURFACES,
    )
    assert isinstance(
        STAGE29_5_5_FORBIDDEN_SURFACES, tuple
    )
    assert len(STAGE29_5_5_FORBIDDEN_SURFACES) > 0
    for entry in STAGE29_5_5_FORBIDDEN_SURFACES:
        assert isinstance(entry, str)
        assert entry.strip() == entry
        assert entry, "forbidden-surface entries must be non-empty"


def test_forbidden_surfaces_contains_core_pins() -> None:
    """The Stage 29.5.5 forbidden-surface tuple MUST continue
    to pin every Stage 29.5.4 forbidden surface EXCEPT
    ``"formatted Discord rendering"`` (which Stage 29.5.5
    unlocks for the side-channel path).
    """
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_FORBIDDEN_SURFACES,
    )
    required = {
        "production enforcement",
        "public routing",
        "subscriber routing",
        "paid tier routing",
        "Telegram sender",
        "Telegram client",
        "X / social sidecar",
        "automated trading",
        "position sizing",
        "trade execution",
        "wallet / private-key / signer logic",
        "private keys",
        "Discord dispatch behavior change",
        "injecting rendered block into live dispatched Discord body",
        "new env name",
        "new third-party runtime dependency",
        "PHX1 import path",
        "direct PHX1 spaghetti copy",
        "Pump.fun bonding-curve decoder",
        "Dexscreener as a dispatch authority",
        "Helius as a price source",
        "live Helius WebSocket call",
        "live Chainstack gRPC call",
        "live Birdeye HTTP call",
        "live Discord call",
        "Stage 29.4 runtime wiring change",
        "Stage 29.5 manifest inventory change",
        "Stage 29.5.2 manifest inventory change",
        "Stage 29.5.3 manifest inventory change",
        "Stage 29.5.4 manifest inventory change",
        "Stage 29.6+ implementation",
    }
    actual = set(STAGE29_5_5_FORBIDDEN_SURFACES)
    missing = required - actual
    assert not missing, (
        f"Stage 29.5.5 forbidden-surface tuple missing "
        f"required entries: {sorted(missing)!r}"
    )


def test_forbidden_surfaces_does_not_pin_formatted_discord_rendering() -> None:
    """Stage 29.5.5 unlocks exactly one Stage 29.5.4 forbidden
    surface: ``formatted Discord rendering``. The Stage 29.5.5
    forbidden-surface tuple must therefore NOT contain that
    entry.
    """
    from PHX2.stage29.stage29_5_5_manifest import (
        STAGE29_5_5_FORBIDDEN_SURFACES,
    )
    assert (
        "formatted Discord rendering"
        not in STAGE29_5_5_FORBIDDEN_SURFACES
    )


def test_renderer_fn_re_exported_through_manifest_sentinel() -> None:
    """The manifest module imports the renderer fn as a
    sentinel so a boundary scan can pin the symbol exists at
    import time without invoking it. The sentinel is a private
    symbol (leading underscore).
    """
    import PHX2.stage29.stage29_5_5_manifest as manifest
    assert hasattr(manifest, "_RENDERER_FN_REF")
    assert hasattr(manifest, "_RENDERED_BLOCK_CLASS_REF")
    assert hasattr(manifest, "_RECORDED_ENTRY_CLASS_REF")
    assert hasattr(manifest, "_RECORDER_CLASS_REF")
    assert hasattr(
        manifest, "_SIDE_CHANNEL_WRITER_CLASS_REF",
    )


def test_manifest_all_symbols_importable() -> None:
    """Every symbol named in ``__all__`` is importable from
    the manifest.
    """
    import PHX2.stage29.stage29_5_5_manifest as manifest
    assert hasattr(manifest, "__all__")
    for symbol in manifest.__all__:
        assert hasattr(manifest, symbol), (
            f"Manifest __all__ names {symbol!r} but the "
            f"symbol is not present on the module"
        )
