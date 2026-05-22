"""Stage 27.5 dry-run artifact writer.

Deterministic offline writer that persists a Stage 27.5
``PrivatePingPayloadRecord`` and the matching Stage 27.5
``PingProvenanceArtifactRecord`` to JSON files under a caller-
supplied output root. Stage 27.5 NEVER opens a network connection,
NEVER calls Discord / Telegram / X-social, NEVER reads the process
environment, NEVER runs a continuous loop, NEVER deduplicates
events, NEVER enforces Stage 26 policy candidates.

Safety guarantees:

  * the output root must already exist (the writer NEVER creates
    arbitrary parent directories outside the caller-supplied root),
  * every filename is validated: it must be a non-empty string, no
    path separator, no ``..``, no leading dot, no NUL byte,
  * the resolved output path must remain under the resolved output
    root (path-traversal escapes are rejected before any file write),
  * default behavior is fail-closed when the target file already
    exists (callers must pass ``overwrite=True`` explicitly),
  * encoding is UTF-8; key ordering is stable (``sort_keys=True``);
  * bytes are written via ``Path.write_bytes`` exactly once (no
    incremental writes, no partial-write surface).

This module imports only stdlib (``json`` / ``pathlib`` / ``typing``)
plus Stage 27.5 production modules. It does NOT import Stage 21-26
production code, does NOT import Stage 27.1 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PHX2.stage27.private_ping_models import (
    PingProvenanceArtifactRecord,
    PrivatePingPayloadRecord,
)
from PHX2.stage27.private_ping_provenance import (
    canonical_artifact_json,
    canonical_payload_json,
)


# ---------------------------------------------------------------------------
# Module-local exceptions
# ---------------------------------------------------------------------------


class Stage27_5ArtifactWriteError(Exception):
    """Base error for Stage 27.5 dry-run artifact writes."""


class Stage27_5OutputRootError(Stage27_5ArtifactWriteError):
    """The caller-supplied output root is invalid (missing /
    non-directory / unsafe).
    """


class Stage27_5FilenameError(Stage27_5ArtifactWriteError):
    """The caller-supplied filename is unsafe (path separator, ``..``,
    leading dot, NUL byte, empty string, non-string).
    """


class Stage27_5PathEscapeError(Stage27_5ArtifactWriteError):
    """The resolved target path escapes the resolved output root."""


class Stage27_5ArtifactExistsError(Stage27_5ArtifactWriteError):
    """The target file already exists and ``overwrite`` was not
    requested.
    """


# ---------------------------------------------------------------------------
# Safe filename + output-root resolution
# ---------------------------------------------------------------------------
#
# Stage 27.5 deliberately accepts only "leaf" filenames (no directory
# components). The writer never creates subdirectories; the caller
# must pre-create the output root and pass a leaf filename.


_FORBIDDEN_FILENAME_LITERALS: frozenset[str] = frozenset(
    {"", ".", ".."}
)


def _validate_filename(filename: object) -> str:
    if not isinstance(filename, str):
        raise Stage27_5FilenameError(
            f"filename must be a string, got {type(filename)!r}"
        )
    if filename in _FORBIDDEN_FILENAME_LITERALS:
        raise Stage27_5FilenameError(
            f"filename {filename!r} is not a valid Stage 27.5 "
            "artifact filename"
        )
    if "\x00" in filename:
        raise Stage27_5FilenameError(
            "filename must not contain a NUL byte"
        )
    if "/" in filename or "\\" in filename:
        raise Stage27_5FilenameError(
            f"filename {filename!r} must not contain a path "
            "separator"
        )
    if filename.startswith("."):
        raise Stage27_5FilenameError(
            f"filename {filename!r} must not start with '.'"
        )
    return filename


def _resolve_under_root(
    output_root: Path, filename: str
) -> Path:
    """Return the resolved target path under the resolved output root.

    Pure / deterministic. Rejects any caller who passes a filename
    that escapes the supplied output root. Stage 27.5 NEVER creates
    parents of the output root; the caller must pre-create it.
    """
    if not isinstance(output_root, Path):
        raise Stage27_5OutputRootError(
            "output_root must be a pathlib.Path instance"
        )
    if not output_root.exists():
        raise Stage27_5OutputRootError(
            f"output_root does not exist: {output_root!r}"
        )
    if not output_root.is_dir():
        raise Stage27_5OutputRootError(
            f"output_root is not a directory: {output_root!r}"
        )

    safe_name = _validate_filename(filename)
    resolved_root = output_root.resolve()
    candidate = (resolved_root / safe_name).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise Stage27_5PathEscapeError(
            f"resolved target {candidate!r} escapes output_root "
            f"{resolved_root!r}"
        ) from exc
    if candidate == resolved_root:
        raise Stage27_5PathEscapeError(
            f"resolved target equals output_root: {candidate!r}"
        )
    return candidate


# ---------------------------------------------------------------------------
# Single deterministic JSON write
# ---------------------------------------------------------------------------


def _write_json_bytes(
    target: Path, encoded: str, *, overwrite: bool
) -> Path:
    if target.exists() and not overwrite:
        raise Stage27_5ArtifactExistsError(
            f"Stage 27.5 artifact target already exists: {target!r}"
        )
    # Append a single newline so the artifact ends with a stable
    # terminator (POSIX text-file convention). ``Path.write_bytes``
    # truncates + writes once; there is no partial-write surface.
    target.write_bytes((encoded + "\n").encode("utf-8"))
    return target


# ---------------------------------------------------------------------------
# Public writers
# ---------------------------------------------------------------------------


def write_ping_payload_artifact(
    payload: PrivatePingPayloadRecord,
    output_root: Path,
    filename: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the canonical JSON encoding of a Stage 27.5 ping payload.

    Returns the resolved target ``Path``. Raises a Stage 27.5
    ``Stage27_5ArtifactWriteError`` subclass on any safety failure.

    Pure / deterministic except for the single ``Path.write_bytes``.
    Two identical payloads always produce identical bytes.
    """
    if not isinstance(payload, PrivatePingPayloadRecord):
        raise TypeError(
            "write_ping_payload_artifact requires a "
            "PrivatePingPayloadRecord"
        )
    target = _resolve_under_root(output_root, filename)
    encoded = canonical_payload_json(payload)
    return _write_json_bytes(
        target, encoded, overwrite=overwrite
    )


def write_ping_provenance_artifact(
    artifact: PingProvenanceArtifactRecord,
    output_root: Path,
    filename: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the canonical JSON encoding of a Stage 27.5 provenance
    artifact.

    Returns the resolved target ``Path``. Raises a Stage 27.5
    ``Stage27_5ArtifactWriteError`` subclass on any safety failure.

    Pure / deterministic except for the single ``Path.write_bytes``.
    Two artifacts that differ only in ``artifact_created_at_utc``
    will differ on disk; every other field is byte-identical for
    identical inputs.
    """
    if not isinstance(artifact, PingProvenanceArtifactRecord):
        raise TypeError(
            "write_ping_provenance_artifact requires a "
            "PingProvenanceArtifactRecord"
        )
    target = _resolve_under_root(output_root, filename)
    encoded = canonical_artifact_json(artifact)
    return _write_json_bytes(
        target, encoded, overwrite=overwrite
    )


# ---------------------------------------------------------------------------
# Deterministic default filename helpers
# ---------------------------------------------------------------------------
#
# The Stage 27.5 dry-run artifact filename convention pins the ping
# identifier (caller-supplied, opaque) inside the basename so two
# artifacts for the same ping always collide on disk. The leading
# ``ping_`` prefix prevents an unexpectedly empty / dot-only ping_id
# from becoming a hidden file.


DEFAULT_PAYLOAD_FILENAME_PREFIX: str = "ping_"
DEFAULT_PAYLOAD_FILENAME_SUFFIX: str = "_payload.json"
DEFAULT_PROVENANCE_FILENAME_PREFIX: str = "ping_"
DEFAULT_PROVENANCE_FILENAME_SUFFIX: str = "_provenance.json"


def default_payload_filename(ping_id: str) -> str:
    """Return ``ping_<ping_id>_payload.json``.

    The ``ping_id`` must be a non-empty string that survives the
    filename safety check.
    """
    if not isinstance(ping_id, str) or ping_id == "":
        raise Stage27_5FilenameError(
            "default_payload_filename requires a non-empty ping_id"
        )
    candidate = (
        DEFAULT_PAYLOAD_FILENAME_PREFIX
        + ping_id
        + DEFAULT_PAYLOAD_FILENAME_SUFFIX
    )
    return _validate_filename(candidate)


def default_provenance_filename(ping_id: str) -> str:
    """Return ``ping_<ping_id>_provenance.json``.

    The ``ping_id`` must be a non-empty string that survives the
    filename safety check.
    """
    if not isinstance(ping_id, str) or ping_id == "":
        raise Stage27_5FilenameError(
            "default_provenance_filename requires a non-empty "
            "ping_id"
        )
    candidate = (
        DEFAULT_PROVENANCE_FILENAME_PREFIX
        + ping_id
        + DEFAULT_PROVENANCE_FILENAME_SUFFIX
    )
    return _validate_filename(candidate)


# ---------------------------------------------------------------------------
# Optional one-shot pair writer
# ---------------------------------------------------------------------------


def write_dry_run_artifact_pair(
    payload: PrivatePingPayloadRecord,
    artifact: PingProvenanceArtifactRecord,
    output_root: Path,
    *,
    payload_filename: Optional[str] = None,
    provenance_filename: Optional[str] = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write both Stage 27.5 dry-run artifacts and return their paths.

    Convenience helper for tests that want a single call site. Filenames
    default to the deterministic ``ping_<ping_id>_*.json`` convention.
    """
    chosen_payload = (
        payload_filename
        if payload_filename is not None
        else default_payload_filename(payload.ping_id)
    )
    chosen_provenance = (
        provenance_filename
        if provenance_filename is not None
        else default_provenance_filename(artifact.ping_id)
    )
    payload_path = write_ping_payload_artifact(
        payload, output_root, chosen_payload, overwrite=overwrite
    )
    provenance_path = write_ping_provenance_artifact(
        artifact,
        output_root,
        chosen_provenance,
        overwrite=overwrite,
    )
    return payload_path, provenance_path
