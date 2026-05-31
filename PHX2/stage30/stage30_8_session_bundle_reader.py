"""Stage 30.8.3 offline manifest-backed compact session bundle reader.

A small, fail-closed, stdlib-only reader for the Stage 30.8.2 compact
session bundles. It reads a caller-PROVIDED session bundle directory (a
temporary / out-of-repo directory in the Stage 30.8.3 tests), treats
``manifest.json`` as the commit marker, and returns a passive read result
of the bundle's members. It is the read companion to the Stage 30.8.2
writer; Stage 30.8.3 stays OFFLINE temp-dir logic only.

Fail-closed, manifest-backed read semantics. The reader:

  * accepts only an explicit ``str`` / ``Path`` session directory (no
    default storage root, no env lookup, no repo scan);
  * REQUIRES ``manifest.json`` and treats it as the commit marker;
  * reads ONLY the files the manifest's ``member_files`` lists (plus the
    two bundle metadata files, ``manifest.json`` +
    ``validation_result.json``);
  * REFUSES a missing manifest, a malformed manifest, a wrong
    bundle-schema version, a malformed ``member_files`` list, a member
    filename that is not a safe single path component, a member path that
    escapes the session dir, a manifest reference to a missing file, an
    incomplete bundle (missing ``validation_result.json``), a loose
    artifact file not listed by the manifest, a non-file entry, and a
    member file whose JSON is malformed;
  * REJECTS every symlink BEFORE dereferencing it -- a symlinked session
    dir (checked before ``is_dir``), a symlinked ``manifest.json`` (checked
    before ``is_file`` / read), and a symlinked metadata / member entry
    (checked during enumeration and again immediately before each read) --
    and asserts every resolved path stays strictly under the session dir,
    so no symlink target outside the bundle is ever read;
  * returns a passive ``Stage30_8BundleReadResult`` (``READ`` /
    ``INVALID``) for normal invalid input rather than raising.

Discipline / non-goals:

  * stdlib only (``json`` / ``pathlib`` / ``dataclasses`` / ``typing``).
    The reader imports NO ``os`` (so NO ``os.environ`` / ``os.getenv``
    env read), NO ``sqlite3``, NO ``zstd`` / compression, NO network
    surface, and NO PHX2 module. Its bundle-format constants
    (``MANIFEST_FILENAME`` / ``VALIDATION_RESULT_FILENAME`` /
    ``EXPECTED_BUNDLE_SCHEMA_VERSION``) mirror the Stage 30.8.2 writer and
    are cross-checked against it by the Stage 30.8.3 manifest test.
  * READ-ONLY: the reader opens files for reading only -- it writes no
    file, creates no directory, and mutates no bundle.
  * deterministic: members are read in the manifest's sorted
    ``member_files`` order, never in filesystem-iteration order.
  * no side effects at import time (no directory read, no clock, no env).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + mirrored Stage 30.8.2 bundle-format constants
# ---------------------------------------------------------------------------


STAGE30_8_3_MINOR_VERSION: str = "30.8.3"


# The two fixed bundle metadata filenames + the bundle envelope schema
# version. These MIRROR the Stage 30.8.2 writer
# (``stage30_8_temp_artifact_writer``); the Stage 30.8.3 manifest test
# cross-checks them against the writer's exported constants so the reader
# can never silently drift from the format the writer produces. They are
# re-declared here (not imported) so the reader stays free of any PHX2
# import.
MANIFEST_FILENAME: str = "manifest.json"
VALIDATION_RESULT_FILENAME: str = "validation_result.json"
EXPECTED_BUNDLE_SCHEMA_VERSION: str = "stage30_8_v0_compact_session_bundle"


# The manifest key naming the bundle envelope schema version + the key
# naming the listed member files.
_MANIFEST_SCHEMA_VERSION_KEY: str = "bundle_schema_version"
_MANIFEST_MEMBER_FILES_KEY: str = "member_files"
_MANIFEST_SESSION_ID_KEY: str = "session_id"


# ---------------------------------------------------------------------------
# Read status (closed set)
# ---------------------------------------------------------------------------


BUNDLE_READ_STATUS_READ: str = "READ"
BUNDLE_READ_STATUS_INVALID: str = "INVALID"


STAGE30_8_3_BUNDLE_READ_STATUS_VALUES: Tuple[str, ...] = (
    BUNDLE_READ_STATUS_READ,
    BUNDLE_READ_STATUS_INVALID,
)


# ---------------------------------------------------------------------------
# Read reason (closed set; reader-owned)
# ---------------------------------------------------------------------------


BUNDLE_READ_REASON_OK: str = "OK"
BUNDLE_READ_REASON_INVALID_SESSION_DIR: str = "INVALID_SESSION_DIR"
BUNDLE_READ_REASON_SYMLINK_REJECTED: str = "SYMLINK_REJECTED"
BUNDLE_READ_REASON_MISSING_MANIFEST: str = "MISSING_MANIFEST"
BUNDLE_READ_REASON_MALFORMED_MANIFEST: str = "MALFORMED_MANIFEST"
BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA: str = "WRONG_BUNDLE_SCHEMA"
BUNDLE_READ_REASON_MEMBER_FILES_INVALID: str = "MEMBER_FILES_INVALID"
BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE: str = "MEMBER_FILENAME_UNSAFE"
BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE: str = "MEMBER_PATH_ESCAPE"
BUNDLE_READ_REASON_MISSING_MEMBER_FILE: str = "MISSING_MEMBER_FILE"
BUNDLE_READ_REASON_INCOMPLETE_BUNDLE: str = "INCOMPLETE_BUNDLE"
BUNDLE_READ_REASON_LOOSE_FILE: str = "LOOSE_FILE"
BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON: str = "MALFORMED_MEMBER_JSON"
BUNDLE_READ_REASON_READ_FAILED: str = "READ_FAILED"


STAGE30_8_3_BUNDLE_READ_REASONS: Tuple[str, ...] = (
    BUNDLE_READ_REASON_OK,
    BUNDLE_READ_REASON_INVALID_SESSION_DIR,
    BUNDLE_READ_REASON_SYMLINK_REJECTED,
    BUNDLE_READ_REASON_MISSING_MANIFEST,
    BUNDLE_READ_REASON_MALFORMED_MANIFEST,
    BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA,
    BUNDLE_READ_REASON_MEMBER_FILES_INVALID,
    BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE,
    BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE,
    BUNDLE_READ_REASON_MISSING_MEMBER_FILE,
    BUNDLE_READ_REASON_INCOMPLETE_BUNDLE,
    BUNDLE_READ_REASON_LOOSE_FILE,
    BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON,
    BUNDLE_READ_REASON_READ_FAILED,
)


# ---------------------------------------------------------------------------
# Immutable records: read member + read result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8ReadBundleMember:
    """One member file read from a manifest-backed bundle (passive).

      * ``filename``    -- the member filename (a safe single path
                           component listed by the manifest).
      * ``member_kind`` -- the ``identity.artifact_kind`` read from the
                           parsed JSON (``None`` when absent / not a dict).
      * ``payload``     -- the parsed JSON object (the ``json.loads``
                           result; a dict for a well-formed artifact).
    """

    filename: str
    member_kind: Optional[str]
    payload: object


@dataclass(frozen=True)
class Stage30_8BundleReadResult:
    """Immutable Stage 30.8.3 bundle read result (passive verdict).

      * ``status``                -- ``READ`` / ``INVALID``.
      * ``reason``                -- a closed-set ``BUNDLE_READ_REASON_*``
                                     token.
      * ``session_dir``           -- the session directory path
                                     (provenance).
      * ``session_id``            -- the manifest ``session_id`` (only when
                                     read far enough to parse it).
      * ``bundle_schema_version`` -- the manifest bundle schema version
                                     (only when read).
      * ``members``               -- the read members, in the manifest's
                                     sorted ``member_files`` order (empty
                                     unless ``READ``).
      * ``member_count``          -- number of members read.
      * ``blocked_file``          -- the offending filename, when a member
                                     / loose-file rule failed; else
                                     ``None``.
    """

    status: str
    reason: str
    session_dir: str
    session_id: Optional[str]
    bundle_schema_version: Optional[str]
    members: Tuple[Stage30_8ReadBundleMember, ...]
    member_count: int
    blocked_file: Optional[str]


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _invalid(
    session_dir: str,
    reason: str,
    blocked_file: Optional[str] = None,
    session_id: Optional[str] = None,
    bundle_schema_version: Optional[str] = None,
) -> Stage30_8BundleReadResult:
    """Build an INVALID read result (fail closed; no members)."""
    return Stage30_8BundleReadResult(
        status=BUNDLE_READ_STATUS_INVALID,
        reason=reason,
        session_dir=session_dir,
        session_id=session_id,
        bundle_schema_version=bundle_schema_version,
        members=(),
        member_count=0,
        blocked_file=blocked_file,
    )


# ---------------------------------------------------------------------------
# Pure helpers: input gate + path containment
# ---------------------------------------------------------------------------


def _coerce_session_dir(session_dir: object) -> Optional[Path]:
    """Return a ``Path`` for an explicit caller-provided ``session_dir``,
    or ``None`` when it is not an explicit path. Accepts only a non-empty
    ``str`` or a ``Path``; rejects ``None`` / other types, the empty
    string, and the bare current dir ``.``. Pure; never raises.
    """
    if isinstance(session_dir, Path):
        candidate = session_dir
    elif isinstance(session_dir, str):
        if session_dir == "":
            return None
        candidate = Path(session_dir)
    else:
        return None
    if str(candidate) in ("", "."):
        return None
    return candidate


def _is_safe_member_filename(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe single path component.

    Fail-closed: rejects non-strings, the empty / whitespace-only string,
    ``.`` / ``..``, any value containing ``..``, a forward or back slash, a
    NUL, or a colon (drive marker). Pure / deterministic; never raises.
    """
    if not isinstance(value, str):
        return False
    if value.strip() == "":
        return False
    if value in (".", ".."):
        return False
    if ".." in value:
        return False
    if "/" in value or "\\" in value:
        return False
    if "\x00" in value:
        return False
    if ":" in value:
        return False
    return True


def _resolve_within(session_dir: Path, component: str) -> bool:
    """Return ``True`` iff ``session_dir/component`` resolves to a path
    strictly under ``session_dir`` (the second containment layer after
    ``_is_safe_member_filename``). Pure (no writes); never raises.
    """
    try:
        root = session_dir.resolve()
        candidate = (session_dir / component).resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    if candidate == root:
        return False
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _reject_unsafe_read(session_dir: Path, name: str) -> Optional[str]:
    """Return a fail-closed reason if ``session_dir/name`` is unsafe to
    read, else ``None``.

    Checked immediately BEFORE every metadata / member read so no symlink
    target is ever followed: it is unsafe when ``session_dir/name`` is a
    symlink (rejected before any ``is_file`` / ``read_text`` that would
    dereference it) or when it does not resolve strictly under
    ``session_dir``. Pure; never raises.
    """
    path = session_dir / name
    try:
        if path.is_symlink():
            return BUNDLE_READ_REASON_SYMLINK_REJECTED
    except OSError:
        return BUNDLE_READ_REASON_SYMLINK_REJECTED
    if not _resolve_within(session_dir, name):
        return BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE
    return None


def _member_kind_of(payload: object) -> Optional[str]:
    """Return the ``identity.artifact_kind`` from a parsed member payload,
    or ``None`` when it is absent / not a string. Pure; never raises.
    """
    if not isinstance(payload, dict):
        return None
    identity = payload.get("identity")
    if not isinstance(identity, dict):
        return None
    kind = identity.get("artifact_kind")
    return kind if isinstance(kind, str) else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def read_compact_session_bundle(
    session_dir: object,
) -> Stage30_8BundleReadResult:
    """Read a manifest-backed Stage 30.8.2 compact session bundle.

    Fail-closed order: explicit existing directory -> ``manifest.json``
    present -> manifest parses -> bundle schema version matches ->
    ``member_files`` is a list of unique safe single-path-component
    filenames -> every member resolves strictly under the session dir and
    exists -> ``validation_result.json`` is present -> no loose / non-file
    / symlink entry -> every member's JSON parses. Only then does it return
    a ``READ`` result whose ``members`` are the parsed member payloads in
    the manifest's sorted ``member_files`` order. Any normal invalid input
    yields an ``INVALID`` result; the reader NEVER raises and writes
    nothing.
    """
    coerced = _coerce_session_dir(session_dir)
    if coerced is None:
        return _invalid(
            str(session_dir), BUNDLE_READ_REASON_INVALID_SESSION_DIR
        )
    dir_label = str(coerced)
    try:
        return _read_bundle(coerced, dir_label)
    except OSError:
        return _invalid(dir_label, BUNDLE_READ_REASON_READ_FAILED)
    except Exception:  # pragma: no cover - total fail-closed backstop
        return _invalid(dir_label, BUNDLE_READ_REASON_READ_FAILED)


def _read_bundle(
    session_dir: Path, dir_label: str
) -> Stage30_8BundleReadResult:
    """Manifest-backed read body (see ``read_compact_session_bundle``).
    May raise ``OSError`` -- the public entry point converts it to a
    fail-closed ``READ_FAILED`` result.
    """
    # Reject a symlinked session dir BEFORE is_dir() (which follows links).
    if session_dir.is_symlink():
        return _invalid(
            dir_label, BUNDLE_READ_REASON_SYMLINK_REJECTED
        )
    if not session_dir.is_dir():
        return _invalid(
            dir_label, BUNDLE_READ_REASON_INVALID_SESSION_DIR
        )

    manifest_path = session_dir / MANIFEST_FILENAME
    # Reject a symlinked (or escaping) manifest BEFORE is_file() /
    # read_text() (which would dereference it), so no symlink target is read.
    unsafe = _reject_unsafe_read(session_dir, MANIFEST_FILENAME)
    if unsafe is not None:
        return _invalid(
            dir_label, unsafe, blocked_file=MANIFEST_FILENAME
        )
    if not manifest_path.is_file():
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_MISSING_MANIFEST,
            blocked_file=MANIFEST_FILENAME,
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_MALFORMED_MANIFEST,
            blocked_file=MANIFEST_FILENAME,
        )
    if not isinstance(manifest, dict):
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_MALFORMED_MANIFEST,
            blocked_file=MANIFEST_FILENAME,
        )

    schema_version = manifest.get(_MANIFEST_SCHEMA_VERSION_KEY)
    if schema_version != EXPECTED_BUNDLE_SCHEMA_VERSION:
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA,
            blocked_file=MANIFEST_FILENAME,
            bundle_schema_version=(
                schema_version
                if isinstance(schema_version, str)
                else None
            ),
        )

    session_id_raw = manifest.get(_MANIFEST_SESSION_ID_KEY)
    session_id = session_id_raw if isinstance(session_id_raw, str) else None

    member_files = manifest.get(_MANIFEST_MEMBER_FILES_KEY)
    if not isinstance(member_files, list) or not all(
        isinstance(name, str) and name != "" for name in member_files
    ):
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_MEMBER_FILES_INVALID,
            blocked_file=MANIFEST_FILENAME,
            session_id=session_id,
            bundle_schema_version=schema_version,
        )
    if len(member_files) != len(set(member_files)):
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_MEMBER_FILES_INVALID,
            blocked_file=MANIFEST_FILENAME,
            session_id=session_id,
            bundle_schema_version=schema_version,
        )

    # Determine the deterministic read order up-front (sorted member files),
    # never the filesystem iteration order.
    ordered_members = sorted(member_files)

    for name in ordered_members:
        if not _is_safe_member_filename(name):
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE,
                blocked_file=name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        if not _resolve_within(session_dir, name):
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE,
                blocked_file=name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )

    # Enumerate the directory ONCE; reject any non-file / symlink entry and
    # capture the present regular-file names. (A clean Stage 30.8.2 bundle
    # contains only regular files: the metadata pair + the members.)
    present_files: set = set()
    for entry in session_dir.iterdir():
        if entry.is_symlink():
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_SYMLINK_REJECTED,
                blocked_file=entry.name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        if not entry.is_file():
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_LOOSE_FILE,
                blocked_file=entry.name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        present_files.add(entry.name)

    expected_metadata = {MANIFEST_FILENAME, VALIDATION_RESULT_FILENAME}
    expected_all = set(ordered_members) | expected_metadata

    missing = expected_all - present_files
    if missing:
        missing_members = missing - expected_metadata
        if missing_members:
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_MISSING_MEMBER_FILE,
                blocked_file=sorted(missing_members)[0],
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_INCOMPLETE_BUNDLE,
            blocked_file=sorted(missing)[0],
            session_id=session_id,
            bundle_schema_version=schema_version,
        )

    extra = present_files - expected_all
    if extra:
        return _invalid(
            dir_label,
            BUNDLE_READ_REASON_LOOSE_FILE,
            blocked_file=sorted(extra)[0],
            session_id=session_id,
            bundle_schema_version=schema_version,
        )

    members: List[Stage30_8ReadBundleMember] = []
    for name in ordered_members:
        # Reject a symlinked (or escaping) member immediately BEFORE the
        # read, so no symlink target is ever dereferenced.
        unsafe = _reject_unsafe_read(session_dir, name)
        if unsafe is not None:
            return _invalid(
                dir_label,
                unsafe,
                blocked_file=name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        member_path = session_dir / name
        try:
            payload = json.loads(member_path.read_text(encoding="utf-8"))
        except ValueError:
            return _invalid(
                dir_label,
                BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON,
                blocked_file=name,
                session_id=session_id,
                bundle_schema_version=schema_version,
            )
        members.append(
            Stage30_8ReadBundleMember(
                filename=name,
                member_kind=_member_kind_of(payload),
                payload=payload,
            )
        )

    return Stage30_8BundleReadResult(
        status=BUNDLE_READ_STATUS_READ,
        reason=BUNDLE_READ_REASON_OK,
        session_dir=dir_label,
        session_id=session_id,
        bundle_schema_version=schema_version,
        members=tuple(members),
        member_count=len(members),
        blocked_file=None,
    )


__all__ = (
    # Minor version + mirrored bundle-format constants.
    "STAGE30_8_3_MINOR_VERSION",
    "MANIFEST_FILENAME",
    "VALIDATION_RESULT_FILENAME",
    "EXPECTED_BUNDLE_SCHEMA_VERSION",
    # Read status (closed set).
    "BUNDLE_READ_STATUS_READ",
    "BUNDLE_READ_STATUS_INVALID",
    "STAGE30_8_3_BUNDLE_READ_STATUS_VALUES",
    # Read reason (closed set).
    "BUNDLE_READ_REASON_OK",
    "BUNDLE_READ_REASON_INVALID_SESSION_DIR",
    "BUNDLE_READ_REASON_SYMLINK_REJECTED",
    "BUNDLE_READ_REASON_MISSING_MANIFEST",
    "BUNDLE_READ_REASON_MALFORMED_MANIFEST",
    "BUNDLE_READ_REASON_WRONG_BUNDLE_SCHEMA",
    "BUNDLE_READ_REASON_MEMBER_FILES_INVALID",
    "BUNDLE_READ_REASON_MEMBER_FILENAME_UNSAFE",
    "BUNDLE_READ_REASON_MEMBER_PATH_ESCAPE",
    "BUNDLE_READ_REASON_MISSING_MEMBER_FILE",
    "BUNDLE_READ_REASON_INCOMPLETE_BUNDLE",
    "BUNDLE_READ_REASON_LOOSE_FILE",
    "BUNDLE_READ_REASON_MALFORMED_MEMBER_JSON",
    "BUNDLE_READ_REASON_READ_FAILED",
    "STAGE30_8_3_BUNDLE_READ_REASONS",
    # Records.
    "Stage30_8ReadBundleMember",
    "Stage30_8BundleReadResult",
    # Public entry point.
    "read_compact_session_bundle",
)
