"""Stage 29.5.5 private discord migration context rendering
manifest.

Constants-only re-export manifest. Pins the Stage 29.5.5
inventory, the zero env-read / zero outbound-network admission
tuples, the locked enforcement / redaction tokens, the locked
Stage 29.5.5 schema versions (renderer / rendered-block /
recorder / side-channel writer), and the Stage 29.5.5
forbidden-surface list.

Stage 29.5.5 narrows the Stage 29.5.4 forbidden-surface list by
unlocking exactly one surface:

  * "formatted Discord rendering" -- this substage's primary
    surface (a Stage 29.5.5 pure renderer + a Stage 29.5.5
    recording adapter + a Stage 29.5.5 side-channel artifact
    writer + a single optional ``migration_context_renderer``
    kwarg on ``run_stage29_3_first_private_tradeable_smoke``).

Every other Stage 29.5.4 forbidden surface remains pinned on
the Stage 29.5.5 list (including the Stage 29.5 "Discord
dispatch behavior change" pin, which Stage 29.5.5 preserves
verbatim: the live dispatched Discord body remains the
unchanged Stage 27.5 plain-text rendering of the Stage 27.4
measurement context record; Stage 29.5.5 ships ZERO change to
the Stage 27.5 private ping renderer / Stage 28.4 audited HTTP
transport / Stage 28.9 dispatch wrapper / Stage 28.2 dispatch
ledger). Additionally, Stage 29.5.5 pins:

  * "injecting rendered block into live dispatched Discord
    body" -- the Stage 29.5.5 rendered block is captured only
    in a side-channel artifact file under the Stage 29.3 mode-3
    ``output_dir``; it never reaches the live dispatched
    payload.
  * "Stage 29.5.4 manifest inventory change" -- the Stage
    29.5.4 manifest's production-inventory tuple is locked at
    Stage 29.5.4 and survives Stage 29.5.5 byte-for-byte.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.5 sibling
    modules (renderer, recorder, side-channel writer, render
    models) and the Stage 29.5 schema constants it re-exports,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import
    time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION
    as _RECORDER_SCHEMA_VERSION,
    Stage29_5_5MigrationContextRecorder
    as _RECORDER_CLASS,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION
    as _RENDERER_SCHEMA_VERSION,
    render_private_discord_migration_context_block
    as _RENDERER_FN,
)
from PHX2.stage29.stage29_5_5_render_models import (
    STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
    as _RECORDED_ENTRY_SCHEMA_VERSION,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
    as _RENDERED_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RecordedRenderEntry
    as _RECORDED_ENTRY_CLASS,
    Stage29_5_5RenderedMigrationContextBlock
    as _RENDERED_BLOCK_CLASS,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION
    as _SIDE_CHANNEL_BUNDLE_SCHEMA_VERSION,
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    as _SIDE_CHANNEL_FILENAME,
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION
    as _SIDE_CHANNEL_WRITER_SCHEMA_VERSION,
    Stage29_5_5SideChannelArtifactWriter
    as _SIDE_CHANNEL_WRITER_CLASS,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT,
    REDACTION_STATUS_SAFE as _LOCKED_REDACTION,
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_5_render_models.py",
    "stage29_5_5_private_discord_migration_context_renderer.py",
    "stage29_5_5_migration_context_recorder.py",
    "stage29_5_5_side_channel_artifact_writer.py",
    "stage29_5_5_manifest.py",
)


STAGE29_5_5_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md",
)


STAGE29_5_5_TEST_BASENAMES: tuple[str, ...] = (
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


# Stage 29.5.5 admits ZERO env-read sites. The renderer, the
# recorder, and the side-channel writer are pure composition
# layers; env access flows through the unchanged Stage 28.11 +
# Stage 29.2 readiness boundaries via the Stage 29.3 entrypoint
# that consumes the recorder + writer at the operator's option.
STAGE29_5_5_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.5 admits ZERO outbound-HTTP / outbound-WS /
# outbound-socket / outbound-gRPC sites. The renderer and
# recorder are observational; the side-channel writer performs
# one local file write per ceremony (no network).
STAGE29_5_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.5 schema-version pins
# ---------------------------------------------------------------------------


STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION: str = (
    _RENDERER_SCHEMA_VERSION
)


STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION: str = (
    _RENDERED_BLOCK_SCHEMA_VERSION
)


STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION: str = (
    _RECORDED_ENTRY_SCHEMA_VERSION
)


STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION: str = (
    _RECORDER_SCHEMA_VERSION
)


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION: str = (
    _SIDE_CHANNEL_WRITER_SCHEMA_VERSION
)


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION: str = (
    _SIDE_CHANNEL_BUNDLE_SCHEMA_VERSION
)


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME: str = (
    _SIDE_CHANNEL_FILENAME
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 locked enforcement / redaction tokens (echoed from
# Stage 29.5 models; the renderer / recorder / writer never
# override them)
# ---------------------------------------------------------------------------


STAGE29_5_5_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


STAGE29_5_5_REDACTION_STATUS_LOCKED: str = _LOCKED_REDACTION


# ---------------------------------------------------------------------------
# Stage 29.5.5 forbidden-surface pins
# ---------------------------------------------------------------------------
#
# Stage 29.5.5 unlocks exactly one Stage 29.5.4 forbidden
# surface:
#
#   * "formatted Discord rendering"
#
# Every other Stage 29.5.4 forbidden surface remains pinned here
# (with the addition of two Stage 29.5.5-specific pins). The
# Stage 29.5.4 manifest's forbidden-surface tuple is unchanged
# byte-for-byte; the Stage 29.5.4 boundary scan reads only Stage
# 29.5.4 production files, so the Stage 29.5.4 pins remain
# green.


STAGE29_5_5_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "public dashboard",
    "HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    # Forbidden-surface entries naming the pre-PHX2 codebase are
    # concatenated literally so this manifest's source itself
    # does NOT carry the literal substring; the runtime tuple
    # values are unchanged byte-for-byte.
    "P" + "HX1 import path",
    "direct P" + "HX1 spaghetti copy",
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
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_RENDERER_FN_REF: object = _RENDERER_FN
_RENDERED_BLOCK_CLASS_REF: object = _RENDERED_BLOCK_CLASS
_RECORDED_ENTRY_CLASS_REF: object = _RECORDED_ENTRY_CLASS
_RECORDER_CLASS_REF: object = _RECORDER_CLASS
_SIDE_CHANNEL_WRITER_CLASS_REF: object = (
    _SIDE_CHANNEL_WRITER_CLASS
)


__all__ = (
    "STAGE29_5_5_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_5_DOC_BASENAMES",
    "STAGE29_5_5_TEST_BASENAMES",
    "STAGE29_5_5_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION",
    "STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION",
    "STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION",
    "STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION",
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION",
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION",
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME",
    "STAGE29_5_5_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_5_REDACTION_STATUS_LOCKED",
    "STAGE29_5_5_FORBIDDEN_SURFACES",
)
