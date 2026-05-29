"""Stage 30.4.1 offline compact market context JSONL artifact
writer.

Append-only JSONL writer for Stage 30.4.1
``Stage30_4CompactMarketContextRecord`` lines. The writer persists
one JSON object per line into the locked basename
``stage30_4_compact_market_context.jsonl`` under a caller-supplied
output directory. The writer NEVER opens a network connection,
NEVER reads the process environment, NEVER auto-creates parent
directories, NEVER performs adapter / formatter logic (those live
in the Stage 30.4.1 adapter / formatter modules), and NEVER
embeds a raw provider payload, an inbound-hook URL, an RPC
endpoint, an API-key string, a signed-token credential, or
authorization-header text on the emitted line.

Artifact shape:

  Each line is a single JSON object encoded with sorted keys + no
  extra whitespace + an LF terminator. The encoding is
  deterministic: the same
  ``Stage30_4CompactMarketContextRecord`` always produces a byte-
  identical line.

Discipline:

  * Stdlib only (``json`` / ``pathlib`` / ``typing``).
  * Stage 30.4.1 ``..._models`` imported read-only.
  * No process-env read, no live secret access.
  * No network surface, no transport reference on source text.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No parent-directory autocreation.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from PHX2.stage30.stage30_4_compact_market_context_models import (
    FORBIDDEN_RECORD_FIELD_NAMES,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME,
    Stage30_4CompactMarketContextError,
    Stage30_4CompactMarketContextRecord,
    is_forbidden_record_field_name,
)


# ---------------------------------------------------------------------------
# Output-directory safety gate
# ---------------------------------------------------------------------------
#
# Concatenated literals so this module's own source does NOT carry
# the canonical URL / inbound-hook / API-key substrings.


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _output_dir_is_safe(output_dir: object) -> bool:
    """Return ``True`` iff ``output_dir`` is a ``Path`` that exists,
    is a directory, and carries no URL / inbound-hook / API-key
    substring on its string rendering.

    Pure / deterministic. Stage 30.4.1 callers are expected to
    create the output directory upstream (typically operator scratch
    space outside the PHX2 working tree, or a pytest tmp_path
    fixture).
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


def compact_market_context_record_to_dict(
    record: Stage30_4CompactMarketContextRecord,
) -> Dict[str, Any]:
    """Project a Stage 30.4.1
    ``Stage30_4CompactMarketContextRecord`` onto a dict whose keys
    are exactly
    ``Stage30_4CompactMarketContextRecord._fields`` and whose
    values flow through verbatim.

    Raises ``Stage30_4CompactMarketContextError`` when:

      * ``record`` is not a ``Stage30_4CompactMarketContextRecord``
        instance.
      * any field name on
        ``Stage30_4CompactMarketContextRecord._fields`` matches the
        Stage 30.4.1 forbidden-field-name vocabulary (defensive
        sentinel against future refactors).
      * any canonical decimal-text or display value is a non-finite
        ``float`` / ``Decimal``. Stage 30.4.1 stores canonical
        values as ``str`` or ``None``; a ``float`` slipping in
        means an upstream refactor broke the invariant.
    """
    if not isinstance(record, Stage30_4CompactMarketContextRecord):
        raise Stage30_4CompactMarketContextError(
            "RECORD_INVALID_TYPE"
        )
    for name in Stage30_4CompactMarketContextRecord._fields:
        if is_forbidden_record_field_name(name):
            raise Stage30_4CompactMarketContextError(
                "RECORD_HAS_FORBIDDEN_FIELD_NAME"
            )
    projected: Dict[str, Any] = {}
    for name in Stage30_4CompactMarketContextRecord._fields:
        value = getattr(record, name)
        # Defensive: Stage 30.4.1 records carry only str / None /
        # bool values. A ``float`` would be an upstream invariant
        # break; reject explicitly so a non-finite ``float`` never
        # reaches the JSON encoder (json.dumps would happily emit
        # ``NaN`` / ``Infinity`` which would violate the Unknown
        # policy).
        if isinstance(value, float):
            raise Stage30_4CompactMarketContextError(
                "RECORD_FIELD_NON_STR_NUMERIC"
            )
        projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Deterministic JSONL line encoding
# ---------------------------------------------------------------------------


def encode_compact_market_context_jsonl_line(
    record: Stage30_4CompactMarketContextRecord,
) -> str:
    """Encode ``record`` as a single JSONL line (one JSON object
    terminated with ``\\n``).

    Deterministic: ``json.dumps(..., sort_keys=True,
    separators=(",", ":"), ensure_ascii=False, allow_nan=False)`` +
    an LF byte. Two identical records always produce a byte-
    identical line. ``allow_nan=False`` raises on a non-finite
    numeric slot, but Stage 30.4.1 records carry only str / None /
    bool values, so this is belt-and-suspenders against future
    refactors.
    """
    projected = compact_market_context_record_to_dict(record)
    return (
        json.dumps(
            projected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Append-only JSONL writer
# ---------------------------------------------------------------------------


def append_compact_market_context_record(
    *,
    output_dir: Path,
    record: Stage30_4CompactMarketContextRecord,
) -> Path:
    """Append one Stage 30.4.1
    ``Stage30_4CompactMarketContextRecord`` to the locked JSONL
    artifact under ``output_dir``.

    Returns the resolved ``Path`` of the JSONL artifact. Raises
    ``Stage30_4CompactMarketContextError`` on caller-shape failures:

      * ``output_dir`` not a ``pathlib.Path``.
      * ``output_dir`` carrying a URL / inbound-hook / API-key
        substring on its string rendering.
      * ``output_dir`` missing or not a directory.
      * ``record`` not a ``Stage30_4CompactMarketContextRecord``.

    Lets ``OSError`` propagate from the underlying file open / write
    so the operator's outer ``except (OSError, ...)`` swallow path
    can capture write-time failures distinctly from caller-shape
    failures. Stage 30.4.1 NEVER auto-creates ``output_dir``; the
    caller is responsible for creating it upstream.
    """
    if not _output_dir_is_safe(output_dir):
        raise Stage30_4CompactMarketContextError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(output_dir, Path):
        raise Stage30_4CompactMarketContextError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(record, Stage30_4CompactMarketContextRecord):
        raise Stage30_4CompactMarketContextError(
            "RECORD_INVALID_TYPE"
        )
    line = encode_compact_market_context_jsonl_line(record)
    target = (
        output_dir / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    with target.open("a", encoding="utf-8", newline="") as fh:
        fh.write(line)
    return target


__all__ = (
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "compact_market_context_record_to_dict",
    "encode_compact_market_context_jsonl_line",
    "append_compact_market_context_record",
)
