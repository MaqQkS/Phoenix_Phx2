"""Stage 30.2 compact ping manifest.

Constants-only re-export manifest. Pins the Stage 30.2 inventory,
the closed-set surface (display sentinel, body cap constants, the
forbidden-field-name vocabulary), the locked schema version, the
locked JSONL artifact basename, and the Stage 30.2 forbidden-surface
list inherited from the Stage 30.0 spec lock.

The Stage 30.2 forbidden surface (unchanged from Stage 30.0 except
that Stage 30.2 IS the compact private ping body rendering and so
removes that single surface from the list):

  * Bounded private runtime session wiring (Stage 30.3 scope).
  * Market-cap / liquidity / volume adapter (Stage 30.4 scope).
  * Public routing, subscriber / paid routing, Telegram, X / social.
  * Stage 26 / Stage 29 enforcement activation.
  * Trading / wallet / signing / private key surfaces.
  * Live Discord send, live gRPC / HTTP / WebSocket provider call,
    live secret read.
  * Pump.fun bonding-curve decoder.
  * Stage 27 / Stage 28 / Stage 29 production source modification.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 30.2 sibling modules
    it re-exports,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.compact_ping_artifact_writer import (
    append_compact_ping_snapshot as _APPEND_COMPACT_PING_SNAPSHOT,
    compact_ping_snapshot_to_dict
    as _COMPACT_PING_SNAPSHOT_TO_DICT,
    encode_compact_ping_jsonl_line
    as _ENCODE_COMPACT_PING_JSONL_LINE,
)
from PHX2.stage30.compact_ping_models import (
    CompactPingInputRecord as _CompactPingInputRecord,
    CompactPingSnapshotRecord as _CompactPingSnapshotRecord,
    DISPLAY_UNKNOWN as _DISPLAY_UNKNOWN,
    FORBIDDEN_RECORD_FIELD_NAMES
    as _FORBIDDEN_RECORD_FIELD_NAMES,
    STAGE30_2_BODY_CHAR_HARD_CAP
    as _STAGE30_2_BODY_CHAR_HARD_CAP,
    STAGE30_2_BODY_CHAR_TARGET
    as _STAGE30_2_BODY_CHAR_TARGET,
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    as _STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
    STAGE30_2_COMPACT_PING_SCHEMA_VERSION
    as _STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
    STAGE30_2_MINOR_VERSION as _STAGE30_2_MINOR_VERSION,
    Stage30_2CompactPingError as _Stage30_2CompactPingError,
    is_forbidden_record_field_name
    as _is_forbidden_record_field_name,
)
from PHX2.stage30.compact_ping_renderer import (
    render_compact_ping as _render_compact_ping,
)


# ---------------------------------------------------------------------------
# Stage 30.2 inventory
# ---------------------------------------------------------------------------


STAGE30_2_PRODUCTION_INVENTORY: Tuple[str, ...] = (
    "compact_ping_models.py",
    "compact_ping_renderer.py",
    "compact_ping_artifact_writer.py",
    "stage30_2_manifest.py",
)


STAGE30_2_TEST_INVENTORY: Tuple[str, ...] = (
    "test_stage_30_2_compact_ping_models.py",
    "test_stage_30_2_compact_ping_renderer.py",
    "test_stage_30_2_compact_ping_artifact_writer.py",
)


# ---------------------------------------------------------------------------
# Stage 30.2 forbidden surface (inherited from the Stage 30.0 spec
# lock; Stage 30.2 IS the compact private ping body rendering, so
# that single surface is removed from the inherited list).
# ---------------------------------------------------------------------------


STAGE30_2_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "bounded private runtime session wiring",
    "market-cap liquidity volume adapter",
    "public audience routing",
    "subscriber paid audience routing",
    "Telegram surface",
    "X social surface",
    "Stage 26 enforcement activation",
    "Stage 29 enforcement activation",
    "trading verdict emission",
    "wallet signing surface",
    "private key surface",
    "live Discord send",
    "live gRPC HTTP WebSocket provider call",
    "live secret read",
    "Pump.fun bonding-curve decoder",
    "Stage 27 production source modification",
    "Stage 28 production source modification",
    "Stage 29 production source modification",
)


# ---------------------------------------------------------------------------
# Re-exports (closed-set surface + records + renderer + writer)
# ---------------------------------------------------------------------------


STAGE30_2_MINOR_VERSION: str = _STAGE30_2_MINOR_VERSION
STAGE30_2_COMPACT_PING_SCHEMA_VERSION: str = (
    _STAGE30_2_COMPACT_PING_SCHEMA_VERSION
)
STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME: str = (
    _STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
)
STAGE30_2_BODY_CHAR_TARGET: int = _STAGE30_2_BODY_CHAR_TARGET
STAGE30_2_BODY_CHAR_HARD_CAP: int = _STAGE30_2_BODY_CHAR_HARD_CAP


DISPLAY_UNKNOWN: str = _DISPLAY_UNKNOWN


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    _FORBIDDEN_RECORD_FIELD_NAMES
)


CompactPingInputRecord = _CompactPingInputRecord
CompactPingSnapshotRecord = _CompactPingSnapshotRecord
Stage30_2CompactPingError = _Stage30_2CompactPingError


is_forbidden_record_field_name = _is_forbidden_record_field_name


render_compact_ping = _render_compact_ping


compact_ping_snapshot_to_dict = _COMPACT_PING_SNAPSHOT_TO_DICT
encode_compact_ping_jsonl_line = _ENCODE_COMPACT_PING_JSONL_LINE
append_compact_ping_snapshot = _APPEND_COMPACT_PING_SNAPSHOT


__all__ = (
    # Version + locked artifact basename + caps + sentinel.
    "STAGE30_2_MINOR_VERSION",
    "STAGE30_2_COMPACT_PING_SCHEMA_VERSION",
    "STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME",
    "STAGE30_2_BODY_CHAR_TARGET",
    "STAGE30_2_BODY_CHAR_HARD_CAP",
    "DISPLAY_UNKNOWN",
    # Inventory.
    "STAGE30_2_PRODUCTION_INVENTORY",
    "STAGE30_2_TEST_INVENTORY",
    # Forbidden surface.
    "STAGE30_2_FORBIDDEN_SURFACES",
    # Records + forbidden-field guard + error.
    "CompactPingInputRecord",
    "CompactPingSnapshotRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "Stage30_2CompactPingError",
    # Helpers.
    "is_forbidden_record_field_name",
    # Renderer.
    "render_compact_ping",
    # Writer.
    "compact_ping_snapshot_to_dict",
    "encode_compact_ping_jsonl_line",
    "append_compact_ping_snapshot",
)
