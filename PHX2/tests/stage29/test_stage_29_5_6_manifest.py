"""Stage 29.5.6 manifest cross-checks.

Pins:

  * Production inventory tuple (2 .py files).
  * Doc inventory tuple (1 .md file).
  * Test inventory tuple (4 test files).
  * Zero env-read admission.
  * Zero outbound-network admission.
  * Locked injector schema version constant.
  * Locked combined-content character cap (1900).
  * Locked enforcement / redaction tokens.
  * Forbidden-surface tuple structure and contents.
  * The Stage 29.5.6 forbidden-surface tuple NO LONGER contains
    ``"injecting rendered block into live dispatched Discord
    body"`` -- Stage 29.5.6 unlocks exactly that surface for the
    mode-3 / opt-in path.
  * The Stage 29.5.6 forbidden-surface tuple DOES pin every
    Stage 29.5.5 production source modification (renderer /
    recorder / side-channel writer / manifest).
  * Sentinel reference for the injector class exists at import
    time.
"""

from __future__ import annotations


def test_production_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_PRODUCTION_PY_BASENAMES,
    )
    assert STAGE29_5_6_PRODUCTION_PY_BASENAMES == (
        "stage29_5_6_private_ping_migration_context_injector.py",
        "stage29_5_6_manifest.py",
    )


def test_doc_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_DOC_BASENAMES,
    )
    assert STAGE29_5_6_DOC_BASENAMES == (
        "STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md",
    )


def test_test_inventory_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_TEST_BASENAMES,
    )
    assert STAGE29_5_6_TEST_BASENAMES == (
        "test_stage_29_5_6_private_ping_migration_context.py",
        "test_stage_29_5_6_boundaries.py",
        "test_stage_29_5_6_manifest.py",
        "test_stage_29_5_6_spec_lock.py",
    )


def test_env_read_admission_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_ENV_READ_ADMITTED_BASENAMES,
    )
    assert STAGE29_5_6_ENV_READ_ADMITTED_BASENAMES == ()


def test_outbound_network_admission_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_OUTBOUND_NETWORK_ADMITTED_BASENAMES,
    )
    assert (
        STAGE29_5_6_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()
    )


def test_injector_schema_version_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION
        == "stage29_5_6_v0_private_discord_body_injector"
    )


def test_content_max_chars_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_CONTENT_MAX_CHARS,
    )
    assert STAGE29_5_6_CONTENT_MAX_CHARS == 1900
    assert isinstance(STAGE29_5_6_CONTENT_MAX_CHARS, int)


def test_locked_enforcement_token_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED,
    )
    assert (
        STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_locked_redaction_token_pin() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_REDACTION_STATUS_LOCKED,
    )
    assert STAGE29_5_6_REDACTION_STATUS_LOCKED == "SAFE"


def test_forbidden_surfaces_is_nonempty_tuple() -> None:
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_FORBIDDEN_SURFACES,
    )
    assert isinstance(
        STAGE29_5_6_FORBIDDEN_SURFACES, tuple
    )
    assert len(STAGE29_5_6_FORBIDDEN_SURFACES) > 0
    for entry in STAGE29_5_6_FORBIDDEN_SURFACES:
        assert isinstance(entry, str)
        assert entry.strip() == entry
        assert entry, "forbidden-surface entries must be non-empty"


def test_forbidden_surfaces_contains_core_pins() -> None:
    """The Stage 29.5.6 forbidden-surface tuple MUST continue to
    pin every Stage 29.5.5 forbidden surface EXCEPT ``"injecting
    rendered block into live dispatched Discord body"`` (which
    Stage 29.5.6 unlocks for the mode-3 / opt-in path), AND must
    add the Stage 29.5.6-specific narrowing pins.
    """
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_FORBIDDEN_SURFACES,
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
        "Stage 27.5 private ping renderer modification",
        "Stage 28.4 audited HTTP transport modification",
        "Stage 28.6 bounded runner modification",
        "Stage 28.9 dispatch wrapper modification",
        "Stage 28.9 dispatch ledger record shape change",
        "Stage 28.9 dispatch counter axes change",
        "live dispatched audience change",
        "raw JSON blob in dispatched body",
        "raw payload bytes in dispatched body",
        "raw URL host in dispatched body",
        "raw API key in dispatched body",
        "raw webhook URL in dispatched body",
        "Stage 29.5.5 renderer source modification",
        "Stage 29.5.5 recorder source modification",
        "Stage 29.5.5 side-channel writer source modification",
        "Stage 29.3 default behavior change",
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
        "Stage 29.5.5 manifest inventory change",
        "Stage 29.6+ implementation",
    }
    actual = set(STAGE29_5_6_FORBIDDEN_SURFACES)
    missing = required - actual
    assert not missing, (
        f"Stage 29.5.6 forbidden-surface tuple missing "
        f"required entries: {sorted(missing)!r}"
    )


def test_forbidden_surfaces_does_not_pin_injecting_rendered_block() -> None:
    """Stage 29.5.6 unlocks exactly one Stage 29.5.5 forbidden
    surface: ``injecting rendered block into live dispatched
    Discord body``. The Stage 29.5.6 forbidden-surface tuple
    must therefore NOT contain that entry.
    """
    from PHX2.stage29.stage29_5_6_manifest import (
        STAGE29_5_6_FORBIDDEN_SURFACES,
    )
    assert (
        "injecting rendered block into live dispatched Discord body"
        not in STAGE29_5_6_FORBIDDEN_SURFACES
    )


def test_injector_class_re_exported_through_manifest_sentinel() -> None:
    """The manifest module imports the injector class as a
    sentinel so a boundary scan can pin the symbol exists at
    import time without invoking it. The sentinel is a private
    symbol (leading underscore).
    """
    import PHX2.stage29.stage29_5_6_manifest as manifest
    assert hasattr(manifest, "_INJECTOR_CLASS_REF")


def test_manifest_all_symbols_importable() -> None:
    """Every symbol named in ``__all__`` is importable from the
    manifest.
    """
    import PHX2.stage29.stage29_5_6_manifest as manifest
    assert hasattr(manifest, "__all__")
    for symbol in manifest.__all__:
        assert hasattr(manifest, symbol), (
            f"Manifest __all__ names {symbol!r} but the symbol "
            f"is not present on the module"
        )
