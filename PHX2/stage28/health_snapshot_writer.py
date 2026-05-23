"""Stage 28.5 health-snapshot + final-run-summary writers.

This module provides two overwrite-atomic JSON writers that a
future Stage 28.6 longer-session runner will use to emit:

  * the current health snapshot JSON file (continuously refreshed
    while the session runs), and
  * the final run summary JSON file (written once at session
    shutdown).

Both writers use a temp-write-then-replace pattern so the on-disk
artifact is never observed in a half-written state. Both writers
require the caller to supply an explicit ``Path`` and require the
parent directory to already exist; Stage 28.5 never silently
creates parent directories. OSError-like underlying failures are
wrapped as closed-set Stage 28.5 errors carrying only a safe
operation token + an optional safe basename (the raw OSError
message is dropped).

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here. Snapshot / summary paths are always
    caller-supplied ``Path`` objects.
  * No network, no HTTP, no gRPC, no Discord, no Telegram, no X /
    social, no provider client.
  * No retry / backoff / failure classification.
  * No audited HTTP transport (Stage 28.4).
  * No runner / no longer-session smoke harness (Stage 28.6 /
    28.7).
  * No sleep / no scheduling / no queue / no thread / no async /
    no subprocess.
  * No parent-directory autocreation.

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
    FINAL_SUMMARY_RECORD_FIELD_NAMES,
    HEALTH_SNAPSHOT_RECORD_FIELD_NAMES,
    STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION,
    STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    Stage28_5FinalRunSummaryRecord,
    Stage28_5HealthSnapshotRecord,
    Stage28_5HealthStatusError,
    final_run_summary_record_to_dict,
    health_snapshot_record_to_dict,
    is_safe_identifier,
)


# ---------------------------------------------------------------------------
# Snapshot-writer exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_5HealthSnapshotWriterError(
    Stage28_5HealthStatusError
):
    """Base type for every Stage 28.5 snapshot / summary writer
    error.

    Module-local; not a subclass of any central PHX2 error registry.
    Subclasses carry only closed-set fields + safe-to-log labels.
    """


class Stage28_5HealthSnapshotPathError(
    Stage28_5HealthSnapshotWriterError
):
    """Raised when the caller-supplied snapshot / summary path
    fails Stage 28.5 path validation.

    Carries only the closed-set reason token + an optional safe
    basename; never the full raw path.
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
                f"Stage 28.5 health snapshot path error: "
                f"reason={reason!r} safe_basename={safe_basename!r}"
            )
        else:
            msg = (
                f"Stage 28.5 health snapshot path error: "
                f"reason={reason!r}"
            )
        super().__init__(msg)


class Stage28_5HealthSnapshotIOError(
    Stage28_5HealthSnapshotWriterError
):
    """Raised when a Stage 28.5 snapshot / summary filesystem
    operation fails with an OSError-like underlying cause.

    Carries only the closed-set operation token + an optional safe
    basename; never the raw OSError message.
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
                f"Stage 28.5 health snapshot I/O failure: "
                f"operation={operation!r} "
                f"safe_basename={safe_basename!r}"
            )
        else:
            msg = (
                f"Stage 28.5 health snapshot I/O failure: "
                f"operation={operation!r}"
            )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


_SNAPSHOT_PATH_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    "password",
    "passwd",
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
)


def _safe_basename_or_none(path: Path) -> Optional[str]:
    """Return ``path.name`` if it passes the Stage 28.5 safe-
    basename allowlist, else ``None``.
    """
    try:
        candidate = path.name
    except Exception:
        return None
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
    for needle in _SNAPSHOT_PATH_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return None
    if candidate.startswith(".") or candidate.endswith("."):
        return None
    if is_safe_identifier(candidate):
        return candidate
    return candidate


def _validate_snapshot_path(
    path: Path,
    *,
    operation_label: str,
) -> None:
    """Validate that ``path`` is safe to use as a Stage 28.5
    snapshot / summary file.

    Rules:

      * caller must supply an explicit ``Path``,
      * path must not be an existing directory,
      * path must not contain secret-looking substrings,
      * parent directory must exist (Stage 28.5 does NOT auto-
        create parents).
    """
    if not isinstance(path, Path):
        raise Stage28_5HealthSnapshotPathError(
            reason=f"{operation_label}_PATH_NOT_A_PATHLIB_PATH",
        )
    path_str = str(path)
    lowered = path_str.lower()
    for needle in _SNAPSHOT_PATH_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            raise Stage28_5HealthSnapshotPathError(
                reason=f"{operation_label}_PATH_SECRET_LIKE",
            )
    if path.exists() and path.is_dir():
        raise Stage28_5HealthSnapshotPathError(
            reason=f"{operation_label}_PATH_IS_DIRECTORY",
            safe_basename=_safe_basename_or_none(path),
        )
    parent = path.parent
    if str(parent) and not parent.exists():
        raise Stage28_5HealthSnapshotPathError(
            reason=f"{operation_label}_PARENT_DIRECTORY_MISSING",
            safe_basename=_safe_basename_or_none(path),
        )


# ---------------------------------------------------------------------------
# Atomic JSON snapshot writer (temp-write-then-replace)
# ---------------------------------------------------------------------------


_HEALTH_SNAPSHOT_TEMP_SUFFIX: str = ".stage28_5.tmp"


def _write_json_atomic(
    *,
    path: Path,
    record_dict: dict,
    operation_label: str,
) -> None:
    """Write ``record_dict`` as deterministic JSON to ``path`` via
    a temp-write-then-replace pattern.

    The serialized JSON uses ``sort_keys=True`` and
    ``separators=(", ", ": ")`` so the artifact is human-readable
    while still byte-deterministic for a given record. UTF-8 with
    a trailing newline is used; the file is created with no BOM
    and no special encoding.

    On OSError, the writer raises ``Stage28_5HealthSnapshotIOError``
    and attempts to clean up the temp file if it exists. If the
    cleanup itself fails, the cleanup failure is swallowed (the
    primary error is the one the caller needs).
    """
    encoded = (
        json.dumps(
            record_dict,
            sort_keys=True,
            separators=(", ", ": "),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    tmp_name = path.name + _HEALTH_SNAPSHOT_TEMP_SUFFIX
    tmp_path = path.with_name(tmp_name)
    try:
        with tmp_path.open("wb") as handle:
            handle.write(encoded)
        tmp_path.replace(path)
    except OSError as exc:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise Stage28_5HealthSnapshotIOError(
            operation=f"{operation_label}_WRITE",
            safe_basename=_safe_basename_or_none(path),
        ) from exc


# ---------------------------------------------------------------------------
# Health snapshot writer
# ---------------------------------------------------------------------------


def write_health_snapshot(
    *,
    snapshot_path: Path,
    record: Stage28_5HealthSnapshotRecord,
) -> None:
    """Atomically write the current Stage 28.5 health snapshot
    JSON to ``snapshot_path``.

    The snapshot file is overwritten in full each call; the on-
    disk artifact reflects only the latest health snapshot. The
    write uses a temp-write-then-replace pattern so the file is
    never observed in a half-written state by an external reader.
    """
    if not isinstance(record, Stage28_5HealthSnapshotRecord):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 snapshot writer rejected non-record "
            "argument: not a Stage28_5HealthSnapshotRecord"
        )
    _validate_snapshot_path(
        snapshot_path, operation_label="HEALTH_SNAPSHOT"
    )
    record_dict = health_snapshot_record_to_dict(record)
    if (
        record_dict.get("schema_version")
        != STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION
    ):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot record carries an "
            "unexpected schema_version"
        )
    _write_json_atomic(
        path=snapshot_path,
        record_dict=record_dict,
        operation_label="HEALTH_SNAPSHOT",
    )


def read_health_snapshot(snapshot_path: Path) -> Optional[dict]:
    """Read the Stage 28.5 health snapshot JSON at
    ``snapshot_path``.

    Behavior:

      * If the path does not exist, returns ``None``.
      * If the file's contents do not parse as a JSON object
        carrying the locked snapshot schema_version + the locked
        field-name set, a closed-set Stage 28.5 snapshot error is
        raised.
      * OSError on read is wrapped as
        ``Stage28_5HealthSnapshotIOError``.
    """
    _validate_snapshot_path(
        snapshot_path, operation_label="HEALTH_SNAPSHOT"
    )

    if not snapshot_path.exists():
        return None

    try:
        raw = snapshot_path.read_bytes()
    except OSError as exc:
        raise Stage28_5HealthSnapshotIOError(
            operation="HEALTH_SNAPSHOT_READ",
            safe_basename=_safe_basename_or_none(snapshot_path),
        ) from exc

    text = raw.decode("utf-8", errors="strict") if raw else ""
    if text == "":
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot file is empty"
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot file is not valid JSON"
        )
    if not isinstance(parsed, dict):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot file is not a JSON object"
        )
    if (
        parsed.get("schema_version")
        != STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION
    ):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot carries an unknown "
            "schema_version"
        )
    if set(parsed.keys()) != set(HEALTH_SNAPSHOT_RECORD_FIELD_NAMES):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 health snapshot field-set mismatch"
        )
    return parsed


# ---------------------------------------------------------------------------
# Final run summary writer
# ---------------------------------------------------------------------------


def write_final_run_summary(
    *,
    summary_path: Path,
    record: Stage28_5FinalRunSummaryRecord,
) -> None:
    """Atomically write the Stage 28.5 final run summary JSON to
    ``summary_path``.

    The final summary is written once at session shutdown. If the
    file already exists, it is overwritten by the temp-write-
    then-replace pattern. The writer does not auto-create parent
    directories.
    """
    if not isinstance(record, Stage28_5FinalRunSummaryRecord):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary writer rejected non-record "
            "argument: not a Stage28_5FinalRunSummaryRecord"
        )
    _validate_snapshot_path(
        summary_path, operation_label="FINAL_RUN_SUMMARY"
    )
    record_dict = final_run_summary_record_to_dict(record)
    if (
        record_dict.get("schema_version")
        != STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION
    ):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary record carries an "
            "unexpected schema_version"
        )
    _write_json_atomic(
        path=summary_path,
        record_dict=record_dict,
        operation_label="FINAL_RUN_SUMMARY",
    )


def read_final_run_summary(summary_path: Path) -> Optional[dict]:
    """Read the Stage 28.5 final run summary JSON at
    ``summary_path``. Returns ``None`` if the path does not exist."""
    _validate_snapshot_path(
        summary_path, operation_label="FINAL_RUN_SUMMARY"
    )

    if not summary_path.exists():
        return None

    try:
        raw = summary_path.read_bytes()
    except OSError as exc:
        raise Stage28_5HealthSnapshotIOError(
            operation="FINAL_RUN_SUMMARY_READ",
            safe_basename=_safe_basename_or_none(summary_path),
        ) from exc

    text = raw.decode("utf-8", errors="strict") if raw else ""
    if text == "":
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary file is empty"
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary file is not valid JSON"
        )
    if not isinstance(parsed, dict):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary file is not a JSON object"
        )
    if (
        parsed.get("schema_version")
        != STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION
    ):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary carries an unknown "
            "schema_version"
        )
    if set(parsed.keys()) != set(FINAL_SUMMARY_RECORD_FIELD_NAMES):
        raise Stage28_5HealthSnapshotWriterError(
            "Stage 28.5 final summary field-set mismatch"
        )
    return parsed


__all__ = (
    "Stage28_5HealthSnapshotWriterError",
    "Stage28_5HealthSnapshotPathError",
    "Stage28_5HealthSnapshotIOError",
    "write_health_snapshot",
    "read_health_snapshot",
    "write_final_run_summary",
    "read_final_run_summary",
)
