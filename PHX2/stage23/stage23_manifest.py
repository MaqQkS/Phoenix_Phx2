"""Stage 23 manifest scaffolding (foundation only at 23.1).

This module ships the typed ``NamedTuple`` records and pure
builders for the Stage 23 input + artifact manifest surface.
The manifest is the provenance trail a Stage 23.5+ runner will
emit alongside every artifact run; Stage 23.1 ships the
contract surface and the deterministic serializer only -- no
runner uses it yet.

Records:

  * ``Stage23ManifestFileEntry``  -- one row per input file with
                                     its identity (basename),
                                     SHA-256, and row count.
  * ``Stage23InputManifest``      -- the locked Stage 23 input
                                     manifest: file entries, the
                                     redaction-confirmation
                                     token, stage name / version
                                     / schema version, the
                                     observe-only posture marker,
                                     and a caller-injected
                                     ``created_at_utc``.
  * ``Stage23ArtifactManifest``   -- the locked Stage 23 artifact
                                     manifest: artifact file
                                     entries plus the same
                                     metadata fields as the input
                                     manifest.

Pure builders / helpers:

  * ``hash_file_sha256``                -- deterministic SHA-256
                                           hex of a file's bytes.
  * ``build_manifest_file_entry``       -- build a file-entry record
                                           with safe basename
                                           + row-count + hash.
  * ``build_input_manifest``            -- assemble a complete
                                           ``Stage23InputManifest``.
  * ``build_artifact_manifest``         -- assemble a complete
                                           ``Stage23ArtifactManifest``.
  * ``serialize_input_manifest``        -- deterministic canonical
                                           JSON for an input manifest.
  * ``serialize_artifact_manifest``     -- deterministic canonical
                                           JSON for an artifact
                                           manifest.

Design notes:

  * Manifest identity is the BASENAME of the input / artifact
    file, NOT the absolute path. Absolute paths leak filesystem
    layout / user identity / scratch-directory naming; Stage 23
    is observe-only and the manifest is allowed to leak no
    operator context. The redaction-confirmation field is a
    locked short token a future runner sets after running its
    own redaction sweep; 23.1 ships the token vocabulary only.
  * Serialization is canonical-JSON (sorted keys, no whitespace,
    ASCII-safe). Identical manifests produce byte-identical
    serializations.
  * ``created_at_utc`` is caller-supplied / injectable. The
    builders never invoke the clock themselves -- mirroring the
    Stage 21 / Stage 22 injected-clock discipline.

This module imports only stdlib (``hashlib`` / ``pathlib``)
plus the Stage 23 constants / errors / models. It does NOT
import Stage 21 or Stage 22 modules, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple

from PHX2.stage23.constants import (
    OBSERVE_ONLY_MODE,
    STAGE_NAME,
    STAGE_VERSION,
    STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE23_MANIFEST_SCHEMA_VERSION,
)
from PHX2.stage23.errors import Stage23ManifestError
from PHX2.stage23.models import canonical_json


# ---------------------------------------------------------------------------
# Redaction confirmation token
# ---------------------------------------------------------------------------
#
# The Stage 23 manifest carries an explicit redaction-confirmation
# field whose only legal value is the locked token below. A future
# Stage 23.5 runner sets the field after running its own redaction
# sweep; an operator can grep manifests for the absence of this
# token to detect runners that skipped the sweep. Stage 23.1 ships
# the token only; no runner sets it yet.


REDACTION_CONFIRMED_TOKEN: str = "stage23_redaction_confirmed"


# ---------------------------------------------------------------------------
# Stage23ManifestFileEntry
# ---------------------------------------------------------------------------


class Stage23ManifestFileEntry(NamedTuple):
    """Per-file entry in a Stage 23 manifest.

    Fields:

      * ``file_basename`` -- the file's basename (not the absolute
                             path). Required non-empty.
      * ``sha256``        -- SHA-256 hex of the file's bytes at
                             manifest-build time. Required
                             non-empty.
      * ``row_count``     -- count of non-blank JSONL lines the
                             reader projected from the file.
                             ``-1`` is reserved for "not
                             applicable" (e.g. an artifact file
                             whose row count is not meaningful at
                             manifest-build time).
    """

    file_basename: str
    sha256: str
    row_count: int


# ---------------------------------------------------------------------------
# Stage23InputManifest
# ---------------------------------------------------------------------------


class Stage23InputManifest(NamedTuple):
    """Stage 23 input manifest.

    Provenance record for the input files a Stage 23 run consumed.
    Stage 23.1 ships the record + serializer only; no runner
    constructs instances of it.

    Fields:

      * ``stage_name``             -- locked ``STAGE_NAME`` token
                                      (``"stage23"``).
      * ``stage_version``          -- locked ``STAGE_VERSION``
                                      (closing value ``"23.6"``).
      * ``schema_version``         -- locked
                                      ``STAGE23_MANIFEST_SCHEMA_VERSION``.
      * ``observe_only_mode``      -- locked ``OBSERVE_ONLY_MODE``
                                      token.
      * ``redaction_confirmed``    -- locked ``REDACTION_CONFIRMED_TOKEN``
                                      when set; empty string when
                                      not yet confirmed.
      * ``files``                  -- tuple of
                                      ``Stage23ManifestFileEntry``
                                      for each input file the run
                                      consumed. Deterministic
                                      order: sorted by
                                      ``file_basename``.
      * ``created_at_utc``         -- ISO-8601 UTC string,
                                      caller-supplied / injected
                                      clock.
    """

    stage_name: str
    stage_version: str
    schema_version: str
    observe_only_mode: str
    redaction_confirmed: str
    files: tuple[Stage23ManifestFileEntry, ...]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Stage23ArtifactManifest
# ---------------------------------------------------------------------------


class Stage23ArtifactManifest(NamedTuple):
    """Stage 23 artifact manifest.

    Provenance record for the artifact files a Stage 23 run wrote.
    Stage 23.1 ships the record + serializer only; no runner
    constructs instances of it.

    Field shape mirrors ``Stage23InputManifest``; the only
    difference is that ``files`` lists OUTPUT artifact files
    rather than INPUT files.
    """

    stage_name: str
    stage_version: str
    schema_version: str
    observe_only_mode: str
    redaction_confirmed: str
    files: tuple[Stage23ManifestFileEntry, ...]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------


def _require_safe_basename(file_basename: str) -> None:
    """Raise ``Stage23ManifestError`` if ``file_basename`` is unsafe.

    A safe basename:

      * is a non-empty string;
      * does not contain any forbidden secret-bearing substring;
      * does not contain any forbidden URL / webhook-host
        substring;
      * does not contain a path separator (``/`` or ``\\``) --
        manifests carry basenames, not paths.
    """
    if not isinstance(file_basename, str) or file_basename == "":
        raise Stage23ManifestError(
            "manifest file_basename must be a non-empty string"
        )
    if "/" in file_basename or "\\" in file_basename:
        raise Stage23ManifestError(
            "manifest file_basename must not contain a path separator"
        )
    lower = file_basename.lower()
    for needle in STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if needle in lower:
            raise Stage23ManifestError(
                "manifest file_basename carries a forbidden "
                "secret-bearing substring"
            )
    for needle in STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if needle in lower:
            raise Stage23ManifestError(
                "manifest file_basename carries a forbidden URL-shape "
                "substring"
            )


def _require_redaction_confirmation(redaction_confirmed: str) -> None:
    """Raise ``Stage23ManifestError`` if ``redaction_confirmed`` is not
    the locked token or the empty string.
    """
    if redaction_confirmed == "":
        return
    if redaction_confirmed != REDACTION_CONFIRMED_TOKEN:
        raise Stage23ManifestError(
            "redaction_confirmed must be the locked Stage 23 "
            "confirmation token or the empty string"
        )


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------


def hash_file_sha256(*, path: Path) -> str:
    """Return the SHA-256 hex digest of the bytes at ``path``.

    Reads the file in chunks; never imports any third-party
    library. Raises ``Stage23ManifestError`` if the path does not
    exist, is a directory, or is otherwise not a regular file.
    """
    if not path.exists():
        raise Stage23ManifestError(
            f"hash_file_sha256: path does not exist: {path.name!r}"
        )
    if path.is_dir():
        raise Stage23ManifestError(
            f"hash_file_sha256: path is a directory: {path.name!r}"
        )
    if not path.is_file():
        raise Stage23ManifestError(
            f"hash_file_sha256: path is not a regular file: {path.name!r}"
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_manifest_file_entry(
    *,
    file_basename: str,
    sha256: str,
    row_count: int,
) -> Stage23ManifestFileEntry:
    """Build a ``Stage23ManifestFileEntry`` with safety validation."""
    _require_safe_basename(file_basename)
    if not isinstance(sha256, str) or sha256 == "":
        raise Stage23ManifestError(
            "manifest sha256 must be a non-empty string"
        )
    if not isinstance(row_count, int) or isinstance(row_count, bool):
        raise Stage23ManifestError(
            "manifest row_count must be a strict int"
        )
    if row_count < -1:
        raise Stage23ManifestError(
            "manifest row_count must be -1 (not applicable) or >= 0"
        )
    return Stage23ManifestFileEntry(
        file_basename=file_basename,
        sha256=sha256,
        row_count=row_count,
    )


def _sort_file_entries(
    entries: tuple[Stage23ManifestFileEntry, ...],
) -> tuple[Stage23ManifestFileEntry, ...]:
    return tuple(
        sorted(entries, key=lambda entry: entry.file_basename)
    )


def build_input_manifest(
    *,
    files: tuple[Stage23ManifestFileEntry, ...],
    created_at_utc: str,
    redaction_confirmed: str = "",
) -> Stage23InputManifest:
    """Assemble a ``Stage23InputManifest`` with deterministic file order."""
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage23ManifestError(
            "manifest created_at_utc must be a non-empty string"
        )
    _require_redaction_confirmation(redaction_confirmed)
    if not isinstance(files, tuple):
        raise Stage23ManifestError(
            "manifest files must be a tuple"
        )
    for entry in files:
        if not isinstance(entry, Stage23ManifestFileEntry):
            raise Stage23ManifestError(
                "manifest files must contain only "
                "Stage23ManifestFileEntry records"
            )
    sorted_entries = _sort_file_entries(files)
    return Stage23InputManifest(
        stage_name=STAGE_NAME,
        stage_version=STAGE_VERSION,
        schema_version=STAGE23_MANIFEST_SCHEMA_VERSION,
        observe_only_mode=OBSERVE_ONLY_MODE,
        redaction_confirmed=redaction_confirmed,
        files=sorted_entries,
        created_at_utc=created_at_utc,
    )


def build_artifact_manifest(
    *,
    files: tuple[Stage23ManifestFileEntry, ...],
    created_at_utc: str,
    redaction_confirmed: str = "",
) -> Stage23ArtifactManifest:
    """Assemble a ``Stage23ArtifactManifest`` with deterministic file order."""
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage23ManifestError(
            "manifest created_at_utc must be a non-empty string"
        )
    _require_redaction_confirmation(redaction_confirmed)
    if not isinstance(files, tuple):
        raise Stage23ManifestError(
            "manifest files must be a tuple"
        )
    for entry in files:
        if not isinstance(entry, Stage23ManifestFileEntry):
            raise Stage23ManifestError(
                "manifest files must contain only "
                "Stage23ManifestFileEntry records"
            )
    sorted_entries = _sort_file_entries(files)
    return Stage23ArtifactManifest(
        stage_name=STAGE_NAME,
        stage_version=STAGE_VERSION,
        schema_version=STAGE23_MANIFEST_SCHEMA_VERSION,
        observe_only_mode=OBSERVE_ONLY_MODE,
        redaction_confirmed=redaction_confirmed,
        files=sorted_entries,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------


def _serialize_files(
    files: tuple[Stage23ManifestFileEntry, ...],
) -> list[dict[str, object]]:
    return [
        {
            "file_basename": entry.file_basename,
            "sha256": entry.sha256,
            "row_count": entry.row_count,
        }
        for entry in files
    ]


def serialize_input_manifest(manifest: Stage23InputManifest) -> str:
    """Return the canonical JSON serialization of ``manifest``."""
    body: dict[str, object] = {
        "stage_name": manifest.stage_name,
        "stage_version": manifest.stage_version,
        "schema_version": manifest.schema_version,
        "observe_only_mode": manifest.observe_only_mode,
        "redaction_confirmed": manifest.redaction_confirmed,
        "files": _serialize_files(manifest.files),
        "created_at_utc": manifest.created_at_utc,
        "manifest_kind": "input",
    }
    return canonical_json(body)


def serialize_artifact_manifest(manifest: Stage23ArtifactManifest) -> str:
    """Return the canonical JSON serialization of ``manifest``."""
    body: dict[str, object] = {
        "stage_name": manifest.stage_name,
        "stage_version": manifest.stage_version,
        "schema_version": manifest.schema_version,
        "observe_only_mode": manifest.observe_only_mode,
        "redaction_confirmed": manifest.redaction_confirmed,
        "files": _serialize_files(manifest.files),
        "created_at_utc": manifest.created_at_utc,
        "manifest_kind": "artifact",
    }
    return canonical_json(body)


__all__ = [
    "REDACTION_CONFIRMED_TOKEN",
    "Stage23ArtifactManifest",
    "Stage23InputManifest",
    "Stage23ManifestFileEntry",
    "build_artifact_manifest",
    "build_input_manifest",
    "build_manifest_file_entry",
    "hash_file_sha256",
    "serialize_artifact_manifest",
    "serialize_input_manifest",
]
