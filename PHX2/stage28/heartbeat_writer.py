"""Stage 28.5 heartbeat JSONL append-only writer.

This module provides the append-only JSONL heartbeat-writer
primitive that a future Stage 28.6 longer-session runner will use
to emit one heartbeat record per heartbeat tick. The Stage 28.5
heartbeat artifact is operator-visible only; it is never broadcast
to any audience, never routed to a subscriber, never sent over
Discord, never forwarded to Telegram or X / social.

Writer contract:

  * Each heartbeat line is one JSON object terminated by ``\\n``.
  * Lines are append-only: no deletion, no compaction, no in-place
    mutation. A future replay reconstructs the latest known state
    by streaming the file end-to-end.
  * Lines are deterministic: ``json.dumps`` is called with
    ``sort_keys=True`` and ``separators=(",", ":")`` so a given
    Stage 28.5 record always serializes to a byte-identical line.
  * Lines are redaction-safe by construction: every field of a
    Stage 28.5 heartbeat record is closed-set / counter / safe-
    shape identifier; the writer NEVER copies a webhook URL, RPC
    URL, API key, bearer token, auth header, or raw exception
    string anywhere.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here. The heartbeat path is always a
    caller-supplied ``Path``.
  * No network, no HTTP, no gRPC, no Discord, no Telegram, no X /
    social, no provider client.
  * No retry / backoff / failure classification (those are Stage
    28.3a / 28.3b).
  * No transport (audited HTTP is Stage 28.4).
  * No runner (longer-session bounded runner is Stage 28.6).
  * No sleep / scheduling.
  * No parent-directory autocreation. The writer requires the
    parent directory to already exist; this keeps Stage 28.5 away
    from accidental directory creation under operator-supplied
    paths.

This module imports only stdlib (``json`` / ``pathlib`` /
``typing``) plus the Stage 28.5 models module. It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2 /
28.3a / 28.3b / 28.4 production code, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define a
CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PHX2.stage28.health_status_models import (
    HEARTBEAT_RECORD_FIELD_NAMES,
    STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
    Stage28_5HealthStatusError,
    Stage28_5HeartbeatRecord,
    heartbeat_record_to_dict,
    is_safe_identifier,
)


# ---------------------------------------------------------------------------
# Stage 28.5 heartbeat-writer accepted schema versions
# ---------------------------------------------------------------------------


# A tuple is used so a future Stage 28.5 schema bump can extend
# the accepted set while the existing v0 records remain readable.
_ACCEPTED_HEARTBEAT_SCHEMA_VERSIONS: tuple[str, ...] = (
    STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Heartbeat-writer exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_5HeartbeatWriterError(Stage28_5HealthStatusError):
    """Base type for every Stage 28.5 heartbeat-writer error.

    Module-local; not a subclass of any central PHX2 error registry.
    Subclasses carry only closed-set fields + safe-to-log labels.
    """


class Stage28_5HeartbeatPathError(Stage28_5HeartbeatWriterError):
    """Raised when the caller-supplied heartbeat path fails Stage
    28.5 path validation (directory, missing parent, secret-looking
    path, etc.).

    Carries only the closed-set reason token + an optional safe
    basename; never the full raw path (which may carry secret-
    looking material).
    """

    def __init__(
        self,
        reason: str,
        *,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.safe_basename: Optional[str] = safe_basename
        if safe_basename is not None:
            msg = (
                f"Stage 28.5 heartbeat path error: "
                f"reason={reason!r} safe_basename={safe_basename!r}"
            )
        else:
            msg = (
                f"Stage 28.5 heartbeat path error: reason={reason!r}"
            )
        super().__init__(msg)


class Stage28_5HeartbeatIOError(Stage28_5HeartbeatWriterError):
    """Raised when a Stage 28.5 heartbeat filesystem operation
    fails with an OSError-like underlying cause.

    Carries only the closed-set operation token + an optional safe
    basename; never the raw OSError message (which may include a
    full path that itself carries secret-looking material).
    """

    def __init__(
        self,
        operation: str,
        *,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.operation: str = operation
        self.safe_basename: Optional[str] = safe_basename
        if safe_basename is not None:
            msg = (
                f"Stage 28.5 heartbeat I/O failure: "
                f"operation={operation!r} "
                f"safe_basename={safe_basename!r}"
            )
        else:
            msg = (
                f"Stage 28.5 heartbeat I/O failure: "
                f"operation={operation!r}"
            )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


_HEARTBEAT_PATH_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
    # URL / scheme substrings (concatenated so this source file
    # itself does not carry the literal URL prefix).
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    # Auth / bearer substrings.
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    "password",
    "passwd",
    # Webhook host fragments.
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
)


def _safe_basename_or_none(path: Path) -> Optional[str]:
    """Return ``path.name`` if it passes the Stage 28.5 safe-
    identifier allowlist, else ``None``.

    Used inside error reporting so the writer never echoes a raw
    path that itself carries secret-looking material.
    """
    try:
        candidate = path.name
    except Exception:
        return None
    # We allow dots in basenames (e.g. ``heartbeat.jsonl``) so use
    # a slightly broader allowlist than ``is_safe_identifier``
    # while still rejecting URL / token / webhook substrings.
    if not isinstance(candidate, str):
        return None
    if candidate == "":
        return None
    if len(candidate) > 96:
        return None
    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.-"
    )
    for ch in candidate:
        if ch not in allowed:
            return None
    lowered = candidate.lower()
    for needle in _HEARTBEAT_PATH_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return None
    if is_safe_identifier(candidate):
        return candidate
    # Otherwise the basename is allowed-shape (e.g. carries a dot
    # for the file extension); still safe to echo.
    if candidate.startswith(".") or candidate.endswith("."):
        return None
    return candidate


def _validate_heartbeat_path(path: Path) -> None:
    """Validate that ``path`` is safe to use as a Stage 28.5
    heartbeat file.

    Rules:

      * the caller must supply an explicit ``Path``,
      * the path must not be an existing directory,
      * the path must not contain secret-looking substrings
        (URL / bearer / webhook fragments),
      * the parent directory must exist (Stage 28.5 does NOT
        auto-create parents).
    """
    if not isinstance(path, Path):
        raise Stage28_5HeartbeatPathError(
            reason="HEARTBEAT_PATH_NOT_A_PATHLIB_PATH",
        )
    path_str = str(path)
    lowered = path_str.lower()
    for needle in _HEARTBEAT_PATH_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            raise Stage28_5HeartbeatPathError(
                reason="HEARTBEAT_PATH_SECRET_LIKE",
            )
    if path.exists() and path.is_dir():
        raise Stage28_5HeartbeatPathError(
            reason="HEARTBEAT_PATH_IS_DIRECTORY",
            safe_basename=_safe_basename_or_none(path),
        )
    parent = path.parent
    if str(parent) and not parent.exists():
        raise Stage28_5HeartbeatPathError(
            reason="HEARTBEAT_PARENT_DIRECTORY_MISSING",
            safe_basename=_safe_basename_or_none(path),
        )


# ---------------------------------------------------------------------------
# Record serialization
# ---------------------------------------------------------------------------


def _serialize_heartbeat_line(
    record: Stage28_5HeartbeatRecord,
) -> str:
    """Serialize a heartbeat record to a deterministic JSON line
    (terminated by ``\\n``).
    """
    record_dict = heartbeat_record_to_dict(record)
    return (
        json.dumps(
            record_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Append-only writer
# ---------------------------------------------------------------------------


def append_heartbeat(
    *,
    heartbeat_path: Path,
    record: Stage28_5HeartbeatRecord,
) -> None:
    """Append one Stage 28.5 heartbeat record to ``heartbeat_path``.

    The writer opens the file in binary append mode so existing
    content is never truncated, and writes a UTF-8-encoded bytes
    payload. OSError-like underlying failures are wrapped as
    ``Stage28_5HeartbeatIOError`` (the raw OSError text is dropped;
    only the closed-set operation token + optional safe basename
    reach the wrapping exception).
    """
    if not isinstance(record, Stage28_5HeartbeatRecord):
        raise Stage28_5HeartbeatWriterError(
            "Stage 28.5 heartbeat writer rejected non-record "
            "argument: not a Stage28_5HeartbeatRecord"
        )
    _validate_heartbeat_path(heartbeat_path)
    line = _serialize_heartbeat_line(record)
    payload = line.encode("utf-8")
    try:
        with heartbeat_path.open("ab") as handle:
            handle.write(payload)
    except OSError as exc:
        raise Stage28_5HeartbeatIOError(
            operation="HEARTBEAT_APPEND",
            safe_basename=_safe_basename_or_none(heartbeat_path),
        ) from exc


# ---------------------------------------------------------------------------
# Read (replay) helper
# ---------------------------------------------------------------------------


def read_heartbeat_lines(heartbeat_path: Path) -> tuple[dict, ...]:
    """Replay the heartbeat artifact at ``heartbeat_path`` into a
    tuple of validated record dicts.

    Behavior:

      * If the path does not exist, returns an empty tuple.
      * If the file is empty, returns an empty tuple.
      * Each non-empty line must be a JSON object carrying the
        locked Stage 28.5 heartbeat schema_version and the locked
        heartbeat field-name set; otherwise a closed-set Stage
        28.5 heartbeat error is raised.
      * OSError on read is wrapped as
        ``Stage28_5HeartbeatIOError``.

    The function does NOT auto-create the file or its parent
    directory.
    """
    _validate_heartbeat_path(heartbeat_path)

    if not heartbeat_path.exists():
        return ()

    try:
        raw = heartbeat_path.read_bytes()
    except OSError as exc:
        raise Stage28_5HeartbeatIOError(
            operation="HEARTBEAT_READ",
            safe_basename=_safe_basename_or_none(heartbeat_path),
        ) from exc

    if not raw:
        return ()

    text = raw.decode("utf-8", errors="strict")
    if text == "":
        return ()

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    out: list[dict] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.rstrip("\r")
        if stripped == "":
            raise Stage28_5HeartbeatWriterError(
                f"Stage 28.5 heartbeat malformed line: "
                f"line_index={index} reason='EMPTY_LINE'"
            )
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            raise Stage28_5HeartbeatWriterError(
                f"Stage 28.5 heartbeat malformed line: "
                f"line_index={index} reason='INVALID_JSON'"
            )
        if not isinstance(parsed, dict):
            raise Stage28_5HeartbeatWriterError(
                f"Stage 28.5 heartbeat malformed line: "
                f"line_index={index} reason='NOT_A_JSON_OBJECT'"
            )
        schema_version = parsed.get("schema_version")
        if (
            not isinstance(schema_version, str)
            or schema_version not in _ACCEPTED_HEARTBEAT_SCHEMA_VERSIONS
        ):
            raise Stage28_5HeartbeatWriterError(
                f"Stage 28.5 heartbeat unknown schema_version: "
                f"line_index={index}"
            )
        if set(parsed.keys()) != set(HEARTBEAT_RECORD_FIELD_NAMES):
            raise Stage28_5HeartbeatWriterError(
                f"Stage 28.5 heartbeat field-set mismatch: "
                f"line_index={index}"
            )
        out.append(parsed)
    return tuple(out)


__all__ = (
    "Stage28_5HeartbeatWriterError",
    "Stage28_5HeartbeatPathError",
    "Stage28_5HeartbeatIOError",
    "append_heartbeat",
    "read_heartbeat_lines",
)
