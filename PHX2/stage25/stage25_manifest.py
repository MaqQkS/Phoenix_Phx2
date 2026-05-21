"""Stage 25 manifest scaffolding (foundation only at 25.1).

This module ships the typed ``NamedTuple`` records and pure
builders for the Stage 25 input + artifact manifest surface.
The manifest is the provenance trail a Stage 25.5+ runner will
emit alongside every artifact run; Stage 25.1 ships the
contract surface and the deterministic serializer only -- no
runner uses it yet.

Records:

  * ``Stage25ManifestFileEntry``  -- one row per input / artifact
                                     file with its identity
                                     (basename), SHA-256, and row
                                     count.
  * ``Stage25Stage24ManifestPin`` -- optional pin recording an
                                     upstream Stage 24 manifest by
                                     basename and SHA-256 only. The
                                     Stage 25 module does NOT import
                                     Stage 24 production code; the
                                     pin is plain strings.
  * ``Stage25InputManifest``      -- the locked Stage 25 input
                                     manifest: file entries, the
                                     redaction-confirmation token,
                                     stage name / version / schema
                                     version, the observe-only
                                     posture marker, an optional
                                     upstream-Stage-24 pin, and a
                                     caller-injected
                                     ``created_at_utc``.
  * ``Stage25ArtifactManifest``   -- the locked Stage 25 artifact
                                     manifest: artifact file entries
                                     plus the same metadata fields
                                     as the input manifest.

Pure builders / helpers:

  * ``hash_file_sha256``                -- deterministic SHA-256 hex
                                           of a file's bytes.
  * ``build_manifest_file_entry``       -- build a file-entry record
                                           with safe basename +
                                           row-count + hash.
  * ``build_stage24_manifest_pin``      -- build the optional Stage
                                           24 upstream pin record
                                           with basename / sha256
                                           safety checks.
  * ``build_input_manifest``            -- assemble a complete
                                           ``Stage25InputManifest``.
  * ``build_artifact_manifest``         -- assemble a complete
                                           ``Stage25ArtifactManifest``.
  * ``serialize_input_manifest``        -- deterministic canonical
                                           JSON for an input manifest.
  * ``serialize_artifact_manifest``     -- deterministic canonical
                                           JSON for an artifact
                                           manifest.

Design notes:

  * Manifest identity is the BASENAME of the input / artifact file,
    NOT the absolute path. Absolute paths leak filesystem layout /
    user identity / scratch-directory naming; Stage 25 is
    observe-only and the manifest is allowed to leak no operator
    context.
  * The optional Stage 24 manifest pin records ONLY the upstream
    manifest's basename and SHA-256. It is supplied by the caller;
    Stage 25 never reads a Stage 24 manifest file itself.
  * Serialization is canonical-JSON (sorted keys, no whitespace,
    ASCII-safe). Identical manifests produce byte-identical
    serializations.
  * ``created_at_utc`` is caller-supplied / injectable. The
    builders never invoke the clock themselves.

This module imports only stdlib (``hashlib`` / ``pathlib``)
plus the Stage 25 constants / errors / models. It does NOT
import Stage 21 / Stage 22 / Stage 23 / Stage 24 production
modules, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple, Optional

from PHX2.stage25.constants import (
    OBSERVE_ONLY_MODE,
    REDACTION_CONFIRMED_TOKEN,
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    STAGE_NAME,
    STAGE_VERSION,
    STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE25_MANIFEST_SCHEMA_VERSION,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
    STAGE25_WRITER_NAME,
    STAGE25_WRITER_VERSION,
)
from PHX2.stage25.errors import Stage25ManifestError
from PHX2.stage25.models import canonical_json


# ---------------------------------------------------------------------------
# Self-referential manifest sentinels
# ---------------------------------------------------------------------------
#
# The Stage 25 artifact manifest includes ``stage25_manifest.json`` as
# one of its own file entries (see ``build_artifact_manifest``). The
# manifest's recorded ``sha256`` cannot be the real hash of its bytes
# because writing the recorded hash back into the manifest changes
# the bytes (the classic self-referential hash problem). The Stage
# 25.6 convention: the self-entry carries the locked sentinel string
# ``SELF_REFERENTIAL_MANIFEST_SHA256`` in the ``sha256`` field and
# ``-1`` in both the ``byte_count`` and ``row_count`` fields;
# downstream readers detect the sentinel and skip the bytes-equal
# verification for the manifest self-entry. The sentinel is
# intentionally a non-hex string so it can never be confused with a
# real digest.
#
# The three sentinel constants are defined in
# ``PHX2/stage25/constants.py`` (the canonical Stage 25 schema /
# vocabulary surface) and re-exported verbatim here for backward
# compatibility with existing Stage 25.6 callers that import them
# from this module.


# ---------------------------------------------------------------------------
# Stage25ManifestFileEntry
# ---------------------------------------------------------------------------


class Stage25ManifestFileEntry(NamedTuple):
    """Per-file entry in a Stage 25 manifest.

    Fields:

      * ``file_basename`` -- the file's basename (not the absolute
                             path). Required non-empty.
      * ``sha256``        -- SHA-256 hex of the file's bytes at
                             manifest-build time. Required non-empty.
                             The locked
                             ``SELF_REFERENTIAL_MANIFEST_SHA256``
                             sentinel is reserved for the manifest's
                             own self-entry.
      * ``row_count``     -- count of non-blank JSONL lines the
                             reader projected from the file. ``-1``
                             is reserved for "not applicable" (e.g.
                             an artifact file whose row count is not
                             meaningful at manifest-build time).
      * ``byte_count``    -- byte count of the file's bytes at
                             manifest-build time. ``-1`` is reserved
                             for "not applicable" -- specifically
                             the manifest's own self-entry, whose
                             byte_count cannot be recorded inside
                             the manifest itself without breaking the
                             self-referential hash chain.
    """

    file_basename: str
    sha256: str
    row_count: int
    byte_count: int = -1


# ---------------------------------------------------------------------------
# Stage25Stage24ManifestPin
# ---------------------------------------------------------------------------


class Stage25Stage24ManifestPin(NamedTuple):
    """Optional pin recording an upstream Stage 24 manifest.

    Stage 25 records the upstream Stage 24 manifest by basename
    and SHA-256 only. The Stage 25 module does NOT import Stage 24
    production code; this pin is plain strings supplied by the
    caller.

    Fields:

      * ``upstream_manifest_basename`` -- the upstream Stage 24
                                         manifest file's basename.
                                         Required non-empty.
      * ``upstream_manifest_sha256``   -- SHA-256 hex of the upstream
                                         Stage 24 manifest's bytes.
                                         Required non-empty.
    """

    upstream_manifest_basename: str
    upstream_manifest_sha256: str


# ---------------------------------------------------------------------------
# Stage25InputManifest
# ---------------------------------------------------------------------------


class Stage25InputManifest(NamedTuple):
    """Stage 25 input manifest.

    Provenance record for the input files a Stage 25 run consumed.
    Stage 25.1 ships the record + serializer only; no runner
    constructs instances of it.

    Fields:

      * ``stage_name``               -- locked ``STAGE_NAME`` token
                                        (``"stage25"``).
      * ``stage_version``            -- locked ``STAGE_VERSION``.
      * ``schema_version``           -- locked
                                        ``STAGE25_MANIFEST_SCHEMA_VERSION``.
      * ``observe_only_mode``        -- locked ``OBSERVE_ONLY_MODE``
                                        token.
      * ``redaction_confirmed``      -- locked ``REDACTION_CONFIRMED_TOKEN``
                                        when set; empty string when
                                        not yet confirmed.
      * ``files``                    -- tuple of
                                        ``Stage25ManifestFileEntry``
                                        for each input file the run
                                        consumed. Deterministic
                                        order: sorted by
                                        ``file_basename``.
      * ``upstream_stage24_pin``     -- optional
                                        ``Stage25Stage24ManifestPin``
                                        recording the upstream Stage
                                        24 manifest. ``None`` when
                                        no upstream pin is recorded.
      * ``created_at_utc``           -- ISO-8601 UTC string,
                                        caller-supplied / injected
                                        clock.
    """

    stage_name: str
    stage_version: str
    schema_version: str
    observe_only_mode: str
    redaction_confirmed: str
    files: tuple[Stage25ManifestFileEntry, ...]
    upstream_stage24_pin: Optional[Stage25Stage24ManifestPin]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Stage25ArtifactManifest
# ---------------------------------------------------------------------------


class Stage25ArtifactManifest(NamedTuple):
    """Stage 25 artifact manifest.

    Provenance record for the artifact files a Stage 25 run wrote.
    Stage 25.6 promotes the runner / writer identity tokens to
    first-class manifest fields so downstream readers can pin the
    exact runner / writer that produced a manifest without parsing
    serialized JSON or inferring from filenames.

    Fields mirror ``Stage25InputManifest`` plus:

      * ``runner_name``    -- locked ``STAGE25_RUNNER_NAME``.
      * ``runner_version`` -- locked ``STAGE25_RUNNER_VERSION``.
      * ``writer_name``    -- locked ``STAGE25_WRITER_NAME`` /
                              ``STAGE25_ARTIFACT_WRITER_NAME``.
      * ``writer_version`` -- locked ``STAGE25_WRITER_VERSION`` /
                              ``STAGE25_ARTIFACT_WRITER_VERSION``.

    ``files`` lists OUTPUT artifact files (including the manifest
    file itself; see ``SELF_REFERENTIAL_MANIFEST_SHA256``).
    """

    stage_name: str
    stage_version: str
    schema_version: str
    observe_only_mode: str
    redaction_confirmed: str
    files: tuple[Stage25ManifestFileEntry, ...]
    upstream_stage24_pin: Optional[Stage25Stage24ManifestPin]
    created_at_utc: str
    runner_name: str = STAGE25_RUNNER_NAME
    runner_version: str = STAGE25_RUNNER_VERSION
    writer_name: str = STAGE25_WRITER_NAME
    writer_version: str = STAGE25_WRITER_VERSION


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------


def _require_safe_basename(file_basename: str) -> None:
    """Raise ``Stage25ManifestError`` if ``file_basename`` is unsafe.

    A safe basename:

      * is a non-empty string;
      * does not contain any forbidden secret-bearing substring;
      * does not contain any forbidden URL / webhook-host
        substring;
      * does not contain a path separator (``/`` or ``\\``) --
        manifests carry basenames, not paths.
    """
    if not isinstance(file_basename, str) or file_basename == "":
        raise Stage25ManifestError(
            "manifest file_basename must be a non-empty string"
        )
    if "/" in file_basename or "\\" in file_basename:
        raise Stage25ManifestError(
            "manifest file_basename must not contain a path separator"
        )
    lower = file_basename.lower()
    for needle in STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if needle in lower:
            raise Stage25ManifestError(
                "manifest file_basename carries a forbidden "
                "secret-bearing substring"
            )
    for needle in STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if needle in lower:
            raise Stage25ManifestError(
                "manifest file_basename carries a forbidden URL-shape "
                "substring"
            )


def _require_safe_sha256(sha256: str) -> None:
    if not isinstance(sha256, str) or sha256 == "":
        raise Stage25ManifestError(
            "manifest sha256 must be a non-empty string"
        )


def _require_redaction_confirmation(redaction_confirmed: str) -> None:
    """Raise ``Stage25ManifestError`` if ``redaction_confirmed`` is not
    the locked token or the empty string.
    """
    if redaction_confirmed == "":
        return
    if redaction_confirmed != REDACTION_CONFIRMED_TOKEN:
        raise Stage25ManifestError(
            "redaction_confirmed must be the locked Stage 25 confirmation "
            "token or the empty string"
        )


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------


def hash_file_sha256(*, path: Path) -> str:
    """Return the SHA-256 hex digest of the bytes at ``path``.

    Reads the file in chunks; never imports any third-party
    library. Raises ``Stage25ManifestError`` if the path does not
    exist, is a directory, or is otherwise not a regular file.
    """
    if not path.exists():
        raise Stage25ManifestError(
            f"hash_file_sha256: path does not exist: {path.name!r}"
        )
    if path.is_dir():
        raise Stage25ManifestError(
            f"hash_file_sha256: path is a directory: {path.name!r}"
        )
    if not path.is_file():
        raise Stage25ManifestError(
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
    byte_count: int = -1,
) -> Stage25ManifestFileEntry:
    """Build a ``Stage25ManifestFileEntry`` with safety validation.

    ``byte_count`` defaults to ``-1`` (the "not applicable" sentinel
    reserved for the manifest's own self-entry); every caller writing
    a real artifact file MUST supply the file's actual byte length.
    """
    _require_safe_basename(file_basename)
    _require_safe_sha256(sha256)
    if not isinstance(row_count, int) or isinstance(row_count, bool):
        raise Stage25ManifestError(
            "manifest row_count must be a strict int"
        )
    if row_count < -1:
        raise Stage25ManifestError(
            "manifest row_count must be -1 (not applicable) or >= 0"
        )
    if not isinstance(byte_count, int) or isinstance(byte_count, bool):
        raise Stage25ManifestError(
            "manifest byte_count must be a strict int"
        )
    if byte_count < -1:
        raise Stage25ManifestError(
            "manifest byte_count must be -1 (not applicable) or >= 0"
        )
    return Stage25ManifestFileEntry(
        file_basename=file_basename,
        sha256=sha256,
        row_count=row_count,
        byte_count=byte_count,
    )


def build_stage24_manifest_pin(
    *,
    upstream_manifest_basename: str,
    upstream_manifest_sha256: str,
) -> Stage25Stage24ManifestPin:
    """Build a ``Stage25Stage24ManifestPin`` with safety validation.

    Stage 25 never imports Stage 24 production code; the upstream
    manifest pin is captured as plain strings supplied by the
    caller. The basename safety check matches the
    ``Stage25ManifestFileEntry`` discipline (no path separators,
    no secret-bearing / URL-shape substrings).
    """
    _require_safe_basename(upstream_manifest_basename)
    _require_safe_sha256(upstream_manifest_sha256)
    return Stage25Stage24ManifestPin(
        upstream_manifest_basename=upstream_manifest_basename,
        upstream_manifest_sha256=upstream_manifest_sha256,
    )


def _sort_file_entries(
    entries: tuple[Stage25ManifestFileEntry, ...],
) -> tuple[Stage25ManifestFileEntry, ...]:
    return tuple(
        sorted(entries, key=lambda entry: entry.file_basename)
    )


def _validate_pin_partial(
    *,
    upstream_manifest_basename: Optional[str],
    upstream_manifest_sha256: Optional[str],
) -> None:
    """Raise if exactly one of basename / sha256 is supplied."""
    basename_set = (
        upstream_manifest_basename is not None
        and upstream_manifest_basename != ""
    )
    sha_set = (
        upstream_manifest_sha256 is not None
        and upstream_manifest_sha256 != ""
    )
    if basename_set != sha_set:
        raise Stage25ManifestError(
            "Stage 24 manifest pin requires both basename and sha256 or "
            "neither"
        )


def _resolve_upstream_pin(
    *,
    upstream_manifest_basename: Optional[str],
    upstream_manifest_sha256: Optional[str],
) -> Optional[Stage25Stage24ManifestPin]:
    _validate_pin_partial(
        upstream_manifest_basename=upstream_manifest_basename,
        upstream_manifest_sha256=upstream_manifest_sha256,
    )
    if (
        upstream_manifest_basename is None
        or upstream_manifest_basename == ""
    ):
        return None
    assert upstream_manifest_sha256 is not None
    return build_stage24_manifest_pin(
        upstream_manifest_basename=upstream_manifest_basename,
        upstream_manifest_sha256=upstream_manifest_sha256,
    )


def build_input_manifest(
    *,
    files: tuple[Stage25ManifestFileEntry, ...],
    created_at_utc: str,
    redaction_confirmed: str = "",
    upstream_manifest_basename: Optional[str] = None,
    upstream_manifest_sha256: Optional[str] = None,
) -> Stage25InputManifest:
    """Assemble a ``Stage25InputManifest`` with deterministic file order.

    If exactly one of ``upstream_manifest_basename`` /
    ``upstream_manifest_sha256`` is supplied, ``Stage25ManifestError``
    is raised. Supplying both records the optional upstream Stage
    24 manifest pin; supplying neither leaves the pin as ``None``.
    """
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage25ManifestError(
            "manifest created_at_utc must be a non-empty string"
        )
    _require_redaction_confirmation(redaction_confirmed)
    if not isinstance(files, tuple):
        raise Stage25ManifestError(
            "manifest files must be a tuple"
        )
    for entry in files:
        if not isinstance(entry, Stage25ManifestFileEntry):
            raise Stage25ManifestError(
                "manifest files must contain only "
                "Stage25ManifestFileEntry records"
            )
    sorted_entries = _sort_file_entries(files)
    upstream_pin = _resolve_upstream_pin(
        upstream_manifest_basename=upstream_manifest_basename,
        upstream_manifest_sha256=upstream_manifest_sha256,
    )
    return Stage25InputManifest(
        stage_name=STAGE_NAME,
        stage_version=STAGE_VERSION,
        schema_version=STAGE25_MANIFEST_SCHEMA_VERSION,
        observe_only_mode=OBSERVE_ONLY_MODE,
        redaction_confirmed=redaction_confirmed,
        files=sorted_entries,
        upstream_stage24_pin=upstream_pin,
        created_at_utc=created_at_utc,
    )


def build_artifact_manifest(
    *,
    files: tuple[Stage25ManifestFileEntry, ...],
    created_at_utc: str,
    redaction_confirmed: str = "",
    upstream_manifest_basename: Optional[str] = None,
    upstream_manifest_sha256: Optional[str] = None,
    runner_name: str = STAGE25_RUNNER_NAME,
    runner_version: str = STAGE25_RUNNER_VERSION,
    writer_name: str = STAGE25_WRITER_NAME,
    writer_version: str = STAGE25_WRITER_VERSION,
) -> Stage25ArtifactManifest:
    """Assemble a ``Stage25ArtifactManifest`` with deterministic file order.

    Stage 25.6 promotes ``runner_name`` / ``runner_version`` /
    ``writer_name`` / ``writer_version`` to first-class manifest fields
    so downstream readers can pin the exact runner / writer pair that
    produced a manifest. Defaults are the locked Stage 25 axes.
    """
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage25ManifestError(
            "manifest created_at_utc must be a non-empty string"
        )
    _require_redaction_confirmation(redaction_confirmed)
    if not isinstance(files, tuple):
        raise Stage25ManifestError(
            "manifest files must be a tuple"
        )
    for entry in files:
        if not isinstance(entry, Stage25ManifestFileEntry):
            raise Stage25ManifestError(
                "manifest files must contain only "
                "Stage25ManifestFileEntry records"
            )
    if not isinstance(runner_name, str) or runner_name == "":
        raise Stage25ManifestError(
            "manifest runner_name must be a non-empty string"
        )
    if not isinstance(runner_version, str) or runner_version == "":
        raise Stage25ManifestError(
            "manifest runner_version must be a non-empty string"
        )
    if not isinstance(writer_name, str) or writer_name == "":
        raise Stage25ManifestError(
            "manifest writer_name must be a non-empty string"
        )
    if not isinstance(writer_version, str) or writer_version == "":
        raise Stage25ManifestError(
            "manifest writer_version must be a non-empty string"
        )
    sorted_entries = _sort_file_entries(files)
    upstream_pin = _resolve_upstream_pin(
        upstream_manifest_basename=upstream_manifest_basename,
        upstream_manifest_sha256=upstream_manifest_sha256,
    )
    return Stage25ArtifactManifest(
        stage_name=STAGE_NAME,
        stage_version=STAGE_VERSION,
        schema_version=STAGE25_MANIFEST_SCHEMA_VERSION,
        observe_only_mode=OBSERVE_ONLY_MODE,
        redaction_confirmed=redaction_confirmed,
        files=sorted_entries,
        upstream_stage24_pin=upstream_pin,
        created_at_utc=created_at_utc,
        runner_name=runner_name,
        runner_version=runner_version,
        writer_name=writer_name,
        writer_version=writer_version,
    )


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------


def _serialize_files(
    files: tuple[Stage25ManifestFileEntry, ...],
) -> list[dict[str, object]]:
    return [
        {
            "file_basename": entry.file_basename,
            "sha256": entry.sha256,
            "row_count": entry.row_count,
            "byte_count": entry.byte_count,
        }
        for entry in files
    ]


def _serialize_pin(
    pin: Optional[Stage25Stage24ManifestPin],
) -> Optional[dict[str, object]]:
    if pin is None:
        return None
    return {
        "upstream_manifest_basename": pin.upstream_manifest_basename,
        "upstream_manifest_sha256": pin.upstream_manifest_sha256,
    }


def serialize_input_manifest(manifest: Stage25InputManifest) -> str:
    """Return the canonical JSON serialization of ``manifest``."""
    body: dict[str, object] = {
        "stage_name": manifest.stage_name,
        "stage_version": manifest.stage_version,
        "schema_version": manifest.schema_version,
        "observe_only_mode": manifest.observe_only_mode,
        "redaction_confirmed": manifest.redaction_confirmed,
        "files": _serialize_files(manifest.files),
        "upstream_stage24_pin": _serialize_pin(
            manifest.upstream_stage24_pin
        ),
        "created_at_utc": manifest.created_at_utc,
        "manifest_kind": "input",
    }
    return canonical_json(body)


def serialize_artifact_manifest(manifest: Stage25ArtifactManifest) -> str:
    """Return the canonical JSON serialization of ``manifest``.

    The artifact manifest body includes the Stage 25.6 runner /
    writer identity tokens so downstream readers can pin the exact
    code that produced the manifest.
    """
    body: dict[str, object] = {
        "stage_name": manifest.stage_name,
        "stage_version": manifest.stage_version,
        "schema_version": manifest.schema_version,
        "observe_only_mode": manifest.observe_only_mode,
        "redaction_confirmed": manifest.redaction_confirmed,
        "files": _serialize_files(manifest.files),
        "upstream_stage24_pin": _serialize_pin(
            manifest.upstream_stage24_pin
        ),
        "created_at_utc": manifest.created_at_utc,
        "manifest_kind": "artifact",
        "runner_name": manifest.runner_name,
        "runner_version": manifest.runner_version,
        "writer_name": manifest.writer_name,
        "writer_version": manifest.writer_version,
    }
    return canonical_json(body)


def artifact_manifest_to_canonical_body(
    manifest: Stage25ArtifactManifest,
) -> dict[str, object]:
    """Return the canonical mapping body of an artifact manifest.

    Convenience for callers that want to run a redaction sweep over
    the canonical body without first round-tripping through JSON.
    """
    return {
        "stage_name": manifest.stage_name,
        "stage_version": manifest.stage_version,
        "schema_version": manifest.schema_version,
        "observe_only_mode": manifest.observe_only_mode,
        "redaction_confirmed": manifest.redaction_confirmed,
        "files": _serialize_files(manifest.files),
        "upstream_stage24_pin": _serialize_pin(
            manifest.upstream_stage24_pin
        ),
        "created_at_utc": manifest.created_at_utc,
        "manifest_kind": "artifact",
        "runner_name": manifest.runner_name,
        "runner_version": manifest.runner_version,
        "writer_name": manifest.writer_name,
        "writer_version": manifest.writer_version,
    }


__all__ = [
    "SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
    "SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    "SELF_REFERENTIAL_MANIFEST_SHA256",
    "Stage25ArtifactManifest",
    "Stage25InputManifest",
    "Stage25ManifestFileEntry",
    "Stage25Stage24ManifestPin",
    "artifact_manifest_to_canonical_body",
    "build_artifact_manifest",
    "build_input_manifest",
    "build_manifest_file_entry",
    "build_stage24_manifest_pin",
    "hash_file_sha256",
    "serialize_artifact_manifest",
    "serialize_input_manifest",
]
