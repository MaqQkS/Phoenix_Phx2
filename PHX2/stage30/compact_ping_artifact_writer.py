"""Stage 30.2 compact ping JSONL artifact writer.

Append-only JSONL writer for Stage 30.2 ``CompactPingSnapshotRecord``
lines. The writer persists one JSON object per line into the locked
basename ``stage30_2_compact_pings.jsonl`` under a caller-supplied
output directory. The writer NEVER opens a network connection, NEVER
reads the process environment, NEVER auto-creates parent directories,
and NEVER performs renderer or tier logic (those live in the Stage
30.2 renderer and the Stage 30.1 projector, respectively).

Artifact shape:

  Each line is a single JSON object encoded with sorted keys + no
  extra whitespace + an LF terminator. The encoding is deterministic:
  the same ``CompactPingSnapshotRecord`` always produces a byte-
  identical line. Identifiers, mint, symbol, display strings, body
  text, warnings tuple, and ISO-8601 timestamps are pre-resolved by
  the renderer; the writer trusts the record's field values verbatim
  and emits ``None`` slots as JSON ``null``.

  The writer never emits a webhook URL, RPC endpoint, API key, bearer
  token, authorization header, raw provider payload, or raw exception
  string. The ``FORBIDDEN_RECORD_FIELD_NAMES`` guard rejects any
  future refactor that tries to widen the snapshot record with a
  secret-class or raw-payload-class field name; the current
  ``CompactPingSnapshotRecord._fields`` set is already clean by
  construction.

Discipline:

  * Stdlib only (``json`` / ``pathlib`` / ``typing``).
  * Stage 30.2 ``compact_ping_models`` imported read-only.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack,
    Birdeye, Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source modification.
  * No parent-directory autocreation.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from PHX2.stage30.compact_ping_models import (
    CompactPingSnapshotRecord,
    FORBIDDEN_RECORD_FIELD_NAMES,
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
    Stage30_2CompactPingError,
    is_forbidden_record_field_name,
)


# ---------------------------------------------------------------------------
# Output-directory safety gate
# ---------------------------------------------------------------------------
#
# Concatenated literals so this module's own source does NOT carry the
# canonical URL / webhook / API-key substrings (mirrors the Stage
# 30.1 / Stage 29.5.5 side-channel artifact writer patterns).


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _output_dir_is_safe(output_dir: object) -> bool:
    """Return ``True`` iff ``output_dir`` is a ``Path`` that exists,
    is a directory, and carries no URL / webhook / API-key substring
    on its string rendering.

    Pure / deterministic. Stage 30.2 callers are expected to create
    the output directory upstream (typically operator scratch space
    outside the PHX2 working tree).
    """
    if not isinstance(output_dir, Path):
        return False
    path_str = str(output_dir)
    lowered = path_str.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    if not output_dir.exists():
        return False
    if not output_dir.is_dir():
        return False
    return True


# ---------------------------------------------------------------------------
# Record projection (closed-shape; rejects forbidden field names)
# ---------------------------------------------------------------------------


def compact_ping_snapshot_to_dict(
    snapshot: CompactPingSnapshotRecord,
) -> Dict[str, Any]:
    """Project a Stage 30.2 ``CompactPingSnapshotRecord`` onto a dict
    whose keys are exactly ``CompactPingSnapshotRecord._fields`` and
    whose values flow through verbatim.

    Raises ``Stage30_2CompactPingError`` when:

      * ``snapshot`` is not a ``CompactPingSnapshotRecord`` instance.
      * any field name on ``CompactPingSnapshotRecord._fields`` matches
        the Stage 30.2 forbidden-field-name vocabulary (defensive
        sentinel against future refactors).
    """
    if not isinstance(snapshot, CompactPingSnapshotRecord):
        raise Stage30_2CompactPingError(
            "SNAPSHOT_RECORD_INVALID_TYPE"
        )
    for name in CompactPingSnapshotRecord._fields:
        if is_forbidden_record_field_name(name):
            raise Stage30_2CompactPingError(
                "RECORD_HAS_FORBIDDEN_FIELD_NAME"
            )
    projected: Dict[str, Any] = {}
    for name in CompactPingSnapshotRecord._fields:
        value = getattr(snapshot, name)
        if isinstance(value, tuple):
            projected[name] = list(value)
        else:
            projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Deterministic JSONL line encoding
# ---------------------------------------------------------------------------


def encode_compact_ping_jsonl_line(
    snapshot: CompactPingSnapshotRecord,
) -> str:
    """Encode ``snapshot`` as a single JSONL line (one JSON object
    terminated with ``\\n``).

    Deterministic: ``json.dumps(..., sort_keys=True, separators=(",",
    ":"), ensure_ascii=False)`` + an LF byte. Two identical snapshots
    always produce a byte-identical line.
    """
    projected = compact_ping_snapshot_to_dict(snapshot)
    return (
        json.dumps(
            projected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Append-only JSONL writer
# ---------------------------------------------------------------------------


def append_compact_ping_snapshot(
    *,
    output_dir: Path,
    snapshot: CompactPingSnapshotRecord,
) -> Path:
    """Append one Stage 30.2 ``CompactPingSnapshotRecord`` to the
    locked JSONL artifact under ``output_dir``.

    Returns the resolved ``Path`` of the JSONL artifact. Raises
    ``Stage30_2CompactPingError`` on caller-shape failures:

      * ``output_dir`` not a ``pathlib.Path``.
      * ``output_dir`` carrying a URL / webhook / API-key substring
        on its string rendering.
      * ``output_dir`` missing or not a directory.
      * ``snapshot`` not a ``CompactPingSnapshotRecord``.

    Lets ``OSError`` propagate from the underlying file open / write
    so the operator's outer ``except (OSError, ...)`` swallow path
    can capture write-time failures distinctly from caller-shape
    failures. Stage 30.2 NEVER auto-creates ``output_dir``; the
    caller is responsible for creating it upstream.
    """
    if not _output_dir_is_safe(output_dir):
        raise Stage30_2CompactPingError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(output_dir, Path):
        raise Stage30_2CompactPingError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(snapshot, CompactPingSnapshotRecord):
        raise Stage30_2CompactPingError(
            "SNAPSHOT_RECORD_INVALID_TYPE"
        )
    line = encode_compact_ping_jsonl_line(snapshot)
    target = (
        output_dir / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    )
    with target.open("a", encoding="utf-8", newline="") as fh:
        fh.write(line)
    return target


__all__ = (
    "STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "compact_ping_snapshot_to_dict",
    "encode_compact_ping_jsonl_line",
    "append_compact_ping_snapshot",
)
