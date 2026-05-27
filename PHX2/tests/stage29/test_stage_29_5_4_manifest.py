"""Stage 29.5.4 manifest cross-checks.

Pins:

  * Production inventory tuple (2 .py files).
  * Doc inventory tuple (1 .md file).
  * Test inventory tuple (10 test files).
  * Zero env-read admission.
  * Zero outbound-network admission.
  * Locked schema version constant.
  * Locked enforcement / redaction tokens.
  * Forbidden-surface tuple structure and contents.
  * The Stage 29.5.4 forbidden-surface tuple NO LONGER contains
    "direct Stage 29.3 migration-context injection" -- Stage
    29.5.4 unlocks exactly that surface.
  * Sentinel references for the adapter class + provider
    Protocols exist at import time.
"""

from __future__ import annotations


def test_production_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_PRODUCTION_PY_BASENAMES,
    )
    assert STAGE29_5_4_PRODUCTION_PY_BASENAMES == (
        "stage29_5_4_migration_context_source_adapter.py",
        "stage29_5_4_manifest.py",
    )


def test_doc_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_DOC_BASENAMES,
    )
    assert STAGE29_5_4_DOC_BASENAMES == (
        "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
    )


def test_test_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_TEST_BASENAMES,
    )
    assert STAGE29_5_4_TEST_BASENAMES == (
        "test_stage_29_5_4_migration_context_source_adapter.py",
        "test_stage_29_5_4_stage29_3_integration.py",
        "test_stage_29_5_4_default_preserves_no_migration_path.py",
        "test_stage_29_5_4_no_duplicate_dispatch.py",
        "test_stage_29_5_4_no_live_surface.py",
        "test_stage_29_5_4_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_4_boundaries.py",
        "test_stage_29_5_4_manifest.py",
        "test_stage_29_5_4_spec_lock.py",
        "test_stage_29_5_4_counter_invariants.py",
    )


def test_env_read_admission_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_4_ENV_READ_ADMITTED_BASENAMES == ()


def test_outbound_network_admission_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_4_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )


def test_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION
        == "stage29_5_4_v0_migration_context_source_adapter"
    )


def test_locked_enforcement_token_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_FILTER_ENFORCEMENT_STATUS_LOCKED,
    )
    assert (
        STAGE29_5_4_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_locked_redaction_token_pin() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_REDACTION_STATUS_LOCKED,
    )
    assert STAGE29_5_4_REDACTION_STATUS_LOCKED == "SAFE"


def test_forbidden_surfaces_is_nonempty_tuple() -> None:
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_FORBIDDEN_SURFACES,
    )
    assert isinstance(
        STAGE29_5_4_FORBIDDEN_SURFACES, tuple
    )
    assert len(STAGE29_5_4_FORBIDDEN_SURFACES) > 0
    for entry in STAGE29_5_4_FORBIDDEN_SURFACES:
        assert isinstance(entry, str)
        assert entry.strip() == entry
        assert entry, "forbidden-surface entries must be non-empty"


def test_forbidden_surfaces_contains_core_pins() -> None:
    """The Stage 29.5.4 forbidden-surface tuple MUST continue to
    pin every Stage 29.5.3 forbidden surface that Stage 29.5.4
    does not unlock.
    """
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_FORBIDDEN_SURFACES,
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
        "formatted Discord rendering",
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
        "Stage 29.6+ implementation",
    }
    actual = set(STAGE29_5_4_FORBIDDEN_SURFACES)
    missing = required - actual
    assert not missing, (
        f"Stage 29.5.4 forbidden-surface tuple missing required "
        f"entries: {sorted(missing)!r}"
    )


def test_forbidden_surfaces_does_not_pin_direct_stage29_3_injection() -> None:
    """Stage 29.5.4 unlocks exactly one Stage 29.5.3 forbidden
    surface: ``direct Stage 29.3 migration-context injection``.
    The Stage 29.5.4 forbidden-surface tuple must therefore NOT
    contain that entry (Stage 29.5.4 admits the surface via the
    opt-in ``migration_source`` kwarg).
    """
    from PHX2.stage29.stage29_5_4_manifest import (
        STAGE29_5_4_FORBIDDEN_SURFACES,
    )
    assert (
        "direct Stage 29.3 migration-context injection"
        not in STAGE29_5_4_FORBIDDEN_SURFACES
    )


def test_adapter_class_re_exported_through_manifest_sentinel() -> None:
    """The manifest module imports the adapter class as a sentinel
    so a boundary scan can pin the class exists at import time
    without instantiating it. The sentinel is a private symbol
    (leading underscore) but importing the manifest must not
    raise.
    """
    import PHX2.stage29.stage29_5_4_manifest as manifest
    assert hasattr(manifest, "_ADAPTER_CLASS_REF")
    assert hasattr(manifest, "_EVIDENCE_PROVIDER_PROTOCOL_REF")
    assert hasattr(manifest, "_ATH_CONTEXT_PROVIDER_PROTOCOL_REF")


def test_manifest_all_symbols_importable() -> None:
    """Every symbol named in ``__all__`` is importable from the
    manifest.
    """
    import PHX2.stage29.stage29_5_4_manifest as manifest
    assert hasattr(manifest, "__all__")
    for symbol in manifest.__all__:
        assert hasattr(manifest, symbol), (
            f"Manifest __all__ names {symbol!r} but the symbol "
            f"is not present on the module"
        )
