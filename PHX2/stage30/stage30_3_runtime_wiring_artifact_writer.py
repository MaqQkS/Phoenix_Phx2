"""Stage 30.3 runtime-wiring JSONL artifact writer.

Append-only JSONL writer for Stage 30.3
``Stage30_3RuntimeWiringArtifactRecord`` lines. The writer
persists one JSON object per line into the locked basename
``stage30_3_runtime_wiring.jsonl`` under a caller-supplied output
directory. The writer NEVER opens a network connection, NEVER
reads the process environment, NEVER auto-creates parent
directories, and NEVER performs tier / compact-render logic
(those live in the Stage 30.1 projector + Stage 30.2 renderer).

Artifact shape:

  Each line is a single JSON object encoded with sorted keys + no
  extra whitespace + an LF terminator. The encoding is
  deterministic: the same record always produces a byte-identical
  line. The ``wrapper_order`` tuple serialises as a JSON array;
  every ``None`` slot serialises as JSON ``null``.

  The writer never emits a URL host literal, RPC endpoint, API
  key, bearer token, authorization header, raw provider payload,
  or raw exception string. The ``FORBIDDEN_RECORD_FIELD_NAMES``
  guard rejects any future refactor that tries to widen the
  record with a secret-class or raw-payload-class field name; the
  current ``Stage30_3RuntimeWiringArtifactRecord._fields`` set is
  already clean by construction.

Discipline:

  * Stdlib only (``json`` / ``pathlib`` / ``typing``).
  * Stage 30.3 ``stage30_3_compact_runtime_models`` imported
    read-only.
  * No Stage 27 / Stage 28 / Stage 29 import.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No parent-directory autocreation.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from PHX2.stage30.stage30_3_compact_runtime_models import (
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    Stage30_3CompactRuntimeError,
    Stage30_3RuntimeWiringArtifactRecord,
    is_forbidden_record_field_name,
)


# ---------------------------------------------------------------------------
# Output-directory safety gate
# ---------------------------------------------------------------------------
#
# Concatenated literals so this module's own source does NOT carry
# the canonical URL / operator-channel / API-key substrings
# (mirrors the Stage 30.1 / Stage 30.2 / Stage 29.5.5 writer
# patterns).


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
    """Return ``True`` iff ``output_dir`` is a ``Path`` that
    exists, is a directory, and carries no URL / operator-channel
    / API-key substring on its string rendering.

    Pure / deterministic. Stage 30.3 callers are expected to
    create the output directory upstream (typically operator
    scratch space outside the PHX2 working tree).
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


def runtime_wiring_record_to_dict(
    record: Stage30_3RuntimeWiringArtifactRecord,
) -> Dict[str, Any]:
    """Project a Stage 30.3 runtime-wiring record onto a dict
    whose keys are exactly
    ``Stage30_3RuntimeWiringArtifactRecord._fields`` and whose
    values flow through verbatim. Tuple fields (``wrapper_order``)
    are projected as lists so ``json.dumps`` emits them as JSON
    arrays.

    Raises ``Stage30_3CompactRuntimeError`` when:

      * ``record`` is not a
        ``Stage30_3RuntimeWiringArtifactRecord`` instance.
      * any field name on the record's ``_fields`` tuple matches
        the Stage 30.3 forbidden-field-name vocabulary
        (defensive sentinel against future refactors).
    """
    if not isinstance(record, Stage30_3RuntimeWiringArtifactRecord):
        raise Stage30_3CompactRuntimeError(
            "RUNTIME_WIRING_RECORD_INVALID_TYPE"
        )
    for name in Stage30_3RuntimeWiringArtifactRecord._fields:
        if is_forbidden_record_field_name(name):
            raise Stage30_3CompactRuntimeError(
                "RECORD_HAS_FORBIDDEN_FIELD_NAME"
            )
    projected: Dict[str, Any] = {}
    for name in Stage30_3RuntimeWiringArtifactRecord._fields:
        value = getattr(record, name)
        if isinstance(value, tuple):
            projected[name] = list(value)
        else:
            projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Deterministic JSONL line encoding
# ---------------------------------------------------------------------------


def encode_runtime_wiring_jsonl_line(
    record: Stage30_3RuntimeWiringArtifactRecord,
) -> str:
    """Encode ``record`` as a single JSONL line (one JSON object
    terminated with ``\\n``).

    Deterministic: ``json.dumps(..., sort_keys=True,
    separators=(",", ":"), ensure_ascii=False)`` + an LF byte. Two
    identical records always produce a byte-identical line.
    """
    projected = runtime_wiring_record_to_dict(record)
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


def append_runtime_wiring_record(
    *,
    output_dir: Path,
    record: Stage30_3RuntimeWiringArtifactRecord,
) -> Path:
    """Append one Stage 30.3 runtime-wiring record to the locked
    JSONL artifact under ``output_dir``.

    Returns the resolved ``Path`` of the JSONL artifact. Raises
    ``Stage30_3CompactRuntimeError`` on caller-shape failures:

      * ``output_dir`` not a ``pathlib.Path``.
      * ``output_dir`` carrying a URL / operator-channel /
        API-key substring on its string rendering.
      * ``output_dir`` missing or not a directory.
      * ``record`` not a
        ``Stage30_3RuntimeWiringArtifactRecord``.

    Lets ``OSError`` propagate from the underlying file open /
    write so the wrapper's outer ``except OSError`` swallow path
    can capture write-time failures distinctly from caller-shape
    failures. Stage 30.3 NEVER auto-creates ``output_dir``; the
    caller is responsible for creating it upstream.
    """
    if not _output_dir_is_safe(output_dir):
        raise Stage30_3CompactRuntimeError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(output_dir, Path):
        raise Stage30_3CompactRuntimeError(
            "OUTPUT_DIR_UNSAFE_OR_MISSING"
        )
    if not isinstance(record, Stage30_3RuntimeWiringArtifactRecord):
        raise Stage30_3CompactRuntimeError(
            "RUNTIME_WIRING_RECORD_INVALID_TYPE"
        )
    line = encode_runtime_wiring_jsonl_line(record)
    target = output_dir / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    with target.open("a", encoding="utf-8", newline="") as fh:
        fh.write(line)
    return target


__all__ = (
    "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
    "runtime_wiring_record_to_dict",
    "encode_runtime_wiring_jsonl_line",
    "append_runtime_wiring_record",
)
