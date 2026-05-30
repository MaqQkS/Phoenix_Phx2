"""Stage 30.8.2 temp-dir compact session artifact writer.

The FIRST Stage 30.8 storage writer slice: a small, fail-closed,
stdlib-only writer that persists a caller-assembled bundle of validated
Stage 30.8.1 compact artifacts to a caller-PROVIDED output directory (a
temporary / out-of-repo directory in the Stage 30.8.2 tests). It uses the
Stage 30.8.1 models + validators and writes deterministic JSON only.

Stage 30.8.2 deliberately stays a temp-dir writer with fake / offline
tests only. It does NOT integrate with live runtime, the compact ping
renderer, a real bot artifact directory, a database, SQLite, zstd /
compression, a dedupe / session index, live providers, the process
environment, enforcement, trading, wallet, or social systems. Those are
later, separately-authorized Stage 30.8.3+ slices.

Atomic, fail-closed bundle semantics (the whole-directory invariant):

  The writer NEVER edits a live final session directory in place. It
  builds the COMPLETE new bundle in a fresh, unique, hidden staging
  directory under ``output_dir``, verifies the staged bundle is complete
  (every member file present and the manifest references exactly those
  files), and only then promotes it into place by directory rename:

    a. validate every member BEFORE writing anything;
    b. create a unique staging dir ``output_dir/.<session>.staging.<n>``;
    c. write all artifact JSON into staging, then
       ``validation_result.json``, then ``manifest.json`` LAST;
    d. verify the staged dir contains exactly the expected files and the
       manifest references exactly the staged member files;
    e. if a final dir already exists, rename it aside to a unique
       ``output_dir/.<session>.previous.<n>`` directory;
    f. rename the staging dir onto the final dir (a whole-directory swap,
       so NO stale member file from a prior, larger bundle can survive);
    g. remove the previous dir only after the promotion succeeds.

  On any failure the writer fails closed: a pre-promotion failure leaves
  the prior final dir untouched and cleans the staging dir; a failure
  during the staging->final rename rolls the previous dir back into
  place; an unrecoverable failure returns ``WRITE_FAILED`` and never
  pretends the bundle was persisted. The result NEVER reports a final dir
  whose ``manifest.json`` references missing or partially-replaced files.

Discipline / non-goals (Stage 30.8.2):

  * stdlib only (``json`` / ``pathlib`` / ``re`` / ``dataclasses`` /
    ``typing``) plus the Stage 30.8.1 models + validators siblings. The
    writer imports NO ``os`` module (so it performs NO ``os.environ`` /
    ``os.getenv`` env read), NO ``sqlite3``, NO ``zstd`` / compression,
    NO network surface, and NO messaging / provider client.
  * caller-supplied ``output_dir`` ONLY: no default storage root, no
    repo-relative implicit output, no env-var lookup, no global path
    config, no home-directory expansion.
  * exact-type inputs: every accepted / serialized artifact member must
    be the EXACT Stage 30.8.1 model type (``type(x) is Model``), never a
    subclass -- so a subclass carrying an extra field is rejected, and
    serialization projects ONLY the canonical model fields (enumerated
    from the base model class), so no extra attribute can ever leak into
    a persisted artifact.
  * fail closed: every present member is validated BEFORE any byte is
    written; an INVALID member aborts the whole bundle and writes nothing.
  * deterministic: stable filenames, sorted JSON keys, UTF-8, a trailing
    newline. The persisted JSON carries NO absolute path and NO
    wall-clock timestamp (the writer reads no clock); the staging /
    previous directory names are transient and never persisted into any
    artifact.
  * path-contained: the session subdirectory name is sanitized to a
    single safe path component and the resolved path is asserted to stay
    strictly under ``output_dir`` (no ``..`` escape, no separator, no
    drive / colon, no NUL, no whitespace-only id).
  * no side effects at import time (no directory creation, no file write,
    no clock call, no env read).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID,
    VALIDATION_STATUS_VALID,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
    Stage30_8CompactStorageBudgetSnapshotArtifact,
)
from PHX2.stage30.stage30_8_artifact_validators import (
    VALIDATION_REASON_OK,
    validate_compact_dispatch_attempt_artifact,
    validate_compact_error_artifact,
    validate_compact_ping_artifact,
    validate_compact_session_summary_artifact,
    validate_compact_storage_budget_snapshot_artifact,
)


# ---------------------------------------------------------------------------
# Minor version + bundle schema identity
# ---------------------------------------------------------------------------


STAGE30_8_2_MINOR_VERSION: str = "30.8.2"


# The bundle manifest schema version. Distinct from the per-artifact
# schema version ``STAGE30_8_ARTIFACT_SCHEMA_VERSION`` (which the Stage
# 30.8.1 artifact records carry): this names the small Stage 30.8.2
# session-bundle manifest envelope, not the artifacts inside it.
STAGE30_8_2_BUNDLE_SCHEMA_VERSION: str = (
    "stage30_8_v0_compact_session_bundle"
)


# ---------------------------------------------------------------------------
# Write outcome status (closed set)
# ---------------------------------------------------------------------------


WRITE_STATUS_WRITTEN: str = "WRITTEN"
WRITE_STATUS_INVALID: str = "INVALID"
WRITE_STATUS_WRITE_FAILED: str = "WRITE_FAILED"


STAGE30_8_2_WRITE_STATUS_VALUES: Tuple[str, ...] = (
    WRITE_STATUS_WRITTEN,
    WRITE_STATUS_INVALID,
    WRITE_STATUS_WRITE_FAILED,
)


# ---------------------------------------------------------------------------
# Write reason (closed set; writer-owned)
# ---------------------------------------------------------------------------
#
# The ``reason`` on a write result is always one of these writer-owned
# tokens. When a bundle member fails Stage 30.8.1 validation the writer
# sets ``reason = WRITE_REASON_INVALID_ARTIFACT`` and carries the
# underlying Stage 30.8.1 validator reason on the separate
# ``validation_reason`` field, so the two closed sets never blur.


WRITE_REASON_OK: str = "OK"
WRITE_REASON_INVALID_OUTPUT_DIR: str = "INVALID_OUTPUT_DIR"
WRITE_REASON_INVALID_BUNDLE_TYPE: str = "INVALID_BUNDLE_TYPE"
WRITE_REASON_INVALID_SESSION_ID: str = "INVALID_SESSION_ID"
WRITE_REASON_EMPTY_BUNDLE: str = "EMPTY_BUNDLE"
WRITE_REASON_INVALID_ARTIFACT_TYPE: str = "INVALID_ARTIFACT_TYPE"
WRITE_REASON_INVALID_ARTIFACT: str = "INVALID_ARTIFACT"
WRITE_REASON_PATH_ESCAPE: str = "PATH_ESCAPE"
WRITE_REASON_WRITE_FAILED: str = "WRITE_FAILED"


STAGE30_8_2_WRITE_REASONS: Tuple[str, ...] = (
    WRITE_REASON_OK,
    WRITE_REASON_INVALID_OUTPUT_DIR,
    WRITE_REASON_INVALID_BUNDLE_TYPE,
    WRITE_REASON_INVALID_SESSION_ID,
    WRITE_REASON_EMPTY_BUNDLE,
    WRITE_REASON_INVALID_ARTIFACT_TYPE,
    WRITE_REASON_INVALID_ARTIFACT,
    WRITE_REASON_PATH_ESCAPE,
    WRITE_REASON_WRITE_FAILED,
)


# ---------------------------------------------------------------------------
# Deterministic bundle filenames
# ---------------------------------------------------------------------------
#
# Stable, lower-snake filenames. The bundle metadata files (manifest +
# validation result) are fixed; the multi-member kinds use a zero-padded
# numeric suffix so a lexical sort matches insertion order.


MANIFEST_FILENAME: str = "manifest.json"
VALIDATION_RESULT_FILENAME: str = "validation_result.json"
SESSION_SUMMARY_FILENAME: str = "session_summary.json"
STORAGE_BUDGET_FILENAME: str = "storage_budget_snapshot.json"
PING_ARTIFACT_FILENAME_PREFIX: str = "ping_artifact_"
DISPATCH_ATTEMPT_FILENAME_PREFIX: str = "dispatch_attempt_"
ERROR_ARTIFACT_FILENAME_PREFIX: str = "error_artifact_"
ARTIFACT_FILENAME_SUFFIX: str = ".json"
TEMP_FILENAME_SUFFIX: str = ".tmp"


# Hidden transient sub-directory infixes (under output_dir) used for the
# two-phase staging / promote. They are never persisted into an artifact.
STAGING_DIR_INFIX: str = ".staging"
PREVIOUS_DIR_INFIX: str = ".previous"


# A bounded retry count when probing a free transient directory name.
_MAX_TRANSIENT_PROBE: int = 4096


# Safe session-id path component: starts with an alphanumeric, then up to
# 127 more of ``[A-Za-z0-9._-]``. The explicit ``..`` / separator / NUL /
# colon / whitespace guards in ``_is_safe_path_component`` run first; this
# anchored pattern is the positive allowlist (no implicit substring match).
_SAFE_COMPONENT_PATTERN: str = r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z"


# ---------------------------------------------------------------------------
# Immutable input: compact session artifact bundle (writer input wrapper)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactSessionArtifactBundle:
    """Caller-assembled, in-memory bundle of Stage 30.8.1 compact
    artifacts for ONE private-soak session.

    A LENIENT, passive carrier: it does NOT validate its members at
    construction. The writer validates every present member with its
    matching Stage 30.8.1 validator before persisting, and fails closed
    on any invalid member. ``session_id`` names the per-session
    subdirectory under the caller-provided output directory (it is
    sanitized to a safe single path component before use).

    Fields (all artifact members optional; at least one must be present):

      * ``session_id``                 -- the private-soak session id;
                                          also the session subdir name.
      * ``session_summary``            -- the rolled-up session summary
                                          artifact, when available.
      * ``ping_artifacts``             -- terminal compact ping artifacts.
      * ``dispatch_attempt_artifacts`` -- dispatch / send attempt records.
      * ``error_artifacts``            -- closed-set error reason records.
      * ``storage_budget_snapshot``    -- the per-run storage-budget
                                          snapshot, when available.
    """

    session_id: str
    session_summary: Optional[Stage30_8CompactSessionSummaryArtifact] = None
    ping_artifacts: Tuple[Stage30_8CompactPingArtifact, ...] = ()
    dispatch_attempt_artifacts: Tuple[
        Stage30_8CompactDispatchAttemptArtifact, ...
    ] = ()
    error_artifacts: Tuple[Stage30_8CompactErrorArtifact, ...] = ()
    storage_budget_snapshot: Optional[
        Stage30_8CompactStorageBudgetSnapshotArtifact
    ] = None


# ---------------------------------------------------------------------------
# Immutable output: write result (passive verdict record)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_8CompactArtifactWriteResult:
    """Immutable Stage 30.8.2 write result (passive verdict record).

    Carries the writer outcome and (only when safely written) the
    artifact paths. It holds no secret and no value beyond what the
    sanitized Stage 30.8.1 models already carry.

      * ``status``            -- ``WRITTEN`` / ``INVALID`` /
                                 ``WRITE_FAILED``.
      * ``reason``            -- a writer-owned ``WRITE_REASON_*`` token.
      * ``validation_status`` -- ``VALID`` only when every member passed
                                 Stage 30.8.1 validation; ``INVALID``
                                 otherwise.
      * ``validation_reason`` -- the underlying Stage 30.8.1 validator
                                 reason when a member failed validation;
                                 ``OK`` for a fully valid bundle; ``None``
                                 for a pre-validation reject.
      * ``blocked_field``     -- the failing field / member label, or
                                 ``None``.
      * ``safe_to_persist``   -- ``True`` ONLY when ``status`` is
                                 ``WRITTEN`` (the bundle is durably on
                                 disk); ``False`` otherwise.
      * ``session_dir``       -- the session directory path, only when
                                 ``WRITTEN``; else ``None``.
      * ``written_paths``     -- the artifact paths, only when
                                 ``WRITTEN``; else empty.
      * ``artifact_count``    -- the number of artifact members written
                                 (0 unless ``WRITTEN``).
    """

    status: str
    reason: str
    validation_status: str
    validation_reason: Optional[str]
    blocked_field: Optional[str]
    safe_to_persist: bool
    session_dir: Optional[str]
    written_paths: Tuple[str, ...]
    artifact_count: int


# ---------------------------------------------------------------------------
# Internal: bundle-rejected signal (pre-write, fail closed)
# ---------------------------------------------------------------------------


class _BundleRejected(Exception):
    """Internal control-flow signal: a member has a non-exact-model type,
    or the bundle is empty. Carries a writer reason + blocked field. Never
    escapes the module (the public entry point converts it to an
    ``INVALID`` result).
    """

    def __init__(self, reason: str, blocked_field: Optional[str]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.blocked_field = blocked_field


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _invalid_result(
    reason: str,
    blocked_field: Optional[str],
    validation_reason: Optional[str] = None,
) -> Stage30_8CompactArtifactWriteResult:
    """Build an INVALID / not-safe-to-persist result (fail closed)."""
    return Stage30_8CompactArtifactWriteResult(
        status=WRITE_STATUS_INVALID,
        reason=reason,
        validation_status="INVALID",
        validation_reason=validation_reason,
        blocked_field=blocked_field,
        safe_to_persist=False,
        session_dir=None,
        written_paths=(),
        artifact_count=0,
    )


def _write_failed_result() -> Stage30_8CompactArtifactWriteResult:
    """Build a WRITE_FAILED result. The bundle passed validation, but a
    filesystem operation failed; nothing safely-persisted is reported.
    """
    return Stage30_8CompactArtifactWriteResult(
        status=WRITE_STATUS_WRITE_FAILED,
        reason=WRITE_REASON_WRITE_FAILED,
        validation_status=VALIDATION_STATUS_VALID,
        validation_reason=VALIDATION_REASON_OK,
        blocked_field=None,
        safe_to_persist=False,
        session_dir=None,
        written_paths=(),
        artifact_count=0,
    )


# ---------------------------------------------------------------------------
# Pure helpers: input gates + path containment
# ---------------------------------------------------------------------------


def _coerce_output_dir(output_dir: object) -> Optional[Path]:
    """Return a ``Path`` for an explicit caller-provided ``output_dir``,
    or ``None`` when it is not an explicit path.

    Accepts only a ``str`` or ``Path``. Rejects ``None`` / other types,
    the empty string, and the bare current-directory ``.`` (the caller
    MUST pass an explicit output directory; the writer never defaults to
    a repo-relative or implicit location). Pure; never raises.
    """
    if isinstance(output_dir, Path):
        candidate = output_dir
    elif isinstance(output_dir, str):
        if output_dir == "":
            return None
        candidate = Path(output_dir)
    else:
        return None
    if str(candidate) in ("", "."):
        return None
    return candidate


def _is_safe_path_component(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe single path component.

    Fail-closed: rejects non-strings, the empty / whitespace-only string,
    ``.`` / ``..``, any value containing ``..``, a forward or back slash,
    a NUL, or a colon (drive marker), then requires a match against the
    anchored safe pattern. Pure / deterministic; never raises.
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
    return re.match(_SAFE_COMPONENT_PATTERN, value) is not None


def _resolve_within(output_dir: Path, component: str) -> bool:
    """Return ``True`` iff ``output_dir/component`` resolves to a path
    strictly under ``output_dir``.

    The second containment layer (after ``_is_safe_path_component``):
    resolves both paths and asserts the candidate is a strict descendant
    of the resolved root. Pure (no writes); never raises.
    """
    try:
        root = output_dir.resolve()
        candidate = (output_dir / component).resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    if candidate == root:
        return False
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Strict, field-projected serialization (no asdict; no subclass leakage)
# ---------------------------------------------------------------------------
#
# Serialization NEVER uses ``dataclasses.asdict`` (which would serialize
# whatever fields an instance happens to carry, including a subclass's
# extra fields). Instead it projects ONLY the canonical fields enumerated
# from the BASE model class -- so an extra attribute on a subclass /
# duck-typed object can never leak into a persisted artifact.


def _leaf(value: object) -> object:
    """Return a JSON-safe projection of a scalar / string-sequence leaf.

    Accepts ``None`` / ``str`` / ``int`` / ``float`` / ``bool`` and a
    tuple / list of such (codes become a JSON array). Any other type
    (a nested object in a non-nested field, a ``bytes`` blob, ...) raises
    ``TypeError`` so the write fails closed rather than persisting an
    unexpected value.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_leaf(element) for element in value]
    raise TypeError(f"non-leaf value of type {type(value)!r}")


def _project(
    instance: object,
    model_cls: type,
    nested: Optional[Dict[str, Callable[[object], dict]]] = None,
) -> dict:
    """Project ``instance`` onto the canonical fields of ``model_cls``.

    Enumerates the field names from the BASE ``model_cls`` (never from
    ``type(instance)``), so a subclass's extra field is never read. A
    field named in ``nested`` is recursed through its nested serializer
    (when present); every other field is a JSON-safe leaf.
    """
    nested = nested or {}
    out: dict = {}
    for field in fields(model_cls):
        name = field.name
        value = getattr(instance, name, None)
        if name in nested:
            out[name] = None if value is None else nested[name](value)
        else:
            out[name] = _leaf(value)
    return out


def _serialize_identity(identity: object) -> dict:
    return _project(identity, Stage30_8CompactArtifactIdentity)


def _serialize_content(content: object) -> dict:
    return _project(content, Stage30_8CompactContentSnapshot)


def _serialize_budget(budget: object) -> dict:
    return _project(
        budget,
        Stage30_8CompactStorageBudgetSnapshotArtifact,
        {"identity": _serialize_identity},
    )


def _serialize_ping(ping: object) -> dict:
    return _project(
        ping,
        Stage30_8CompactPingArtifact,
        {"identity": _serialize_identity, "content": _serialize_content},
    )


def _serialize_dispatch(dispatch: object) -> dict:
    return _project(
        dispatch,
        Stage30_8CompactDispatchAttemptArtifact,
        {"identity": _serialize_identity},
    )


def _serialize_error(error: object) -> dict:
    return _project(
        error,
        Stage30_8CompactErrorArtifact,
        {"identity": _serialize_identity},
    )


def _serialize_summary(summary: object) -> dict:
    return _project(
        summary,
        Stage30_8CompactSessionSummaryArtifact,
        {
            "identity": _serialize_identity,
            "storage_budget": _serialize_budget,
        },
    )


# ---------------------------------------------------------------------------
# Pure helpers: member collection (EXACT type gates) + JSON serialization
# ---------------------------------------------------------------------------


def _collect_members(
    bundle: Stage30_8CompactSessionArtifactBundle,
) -> List[Tuple[str, str, object, Callable, Callable]]:
    """Return the ordered ``(filename, kind, artifact, validator,
    serializer)`` tuples for the bundle's present members.

    Enforces, fail-closed, that each present member is the EXACT Stage
    30.8.1 model type (``type(x) is Model``) -- a subclass (which could
    carry an extra field) is rejected. Raises ``_BundleRejected`` on a
    non-exact-model member type or an empty bundle. Pure; raises only the
    internal signal.
    """
    members: List[Tuple[str, str, object, Callable, Callable]] = []

    summary = bundle.session_summary
    if summary is not None:
        if type(summary) is not Stage30_8CompactSessionSummaryArtifact:
            raise _BundleRejected(
                WRITE_REASON_INVALID_ARTIFACT_TYPE, "session_summary"
            )
        members.append(
            (
                SESSION_SUMMARY_FILENAME,
                ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
                summary,
                validate_compact_session_summary_artifact,
                _serialize_summary,
            )
        )

    budget = bundle.storage_budget_snapshot
    if budget is not None:
        if (
            type(budget)
            is not Stage30_8CompactStorageBudgetSnapshotArtifact
        ):
            raise _BundleRejected(
                WRITE_REASON_INVALID_ARTIFACT_TYPE,
                "storage_budget_snapshot",
            )
        members.append(
            (
                STORAGE_BUDGET_FILENAME,
                ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
                budget,
                validate_compact_storage_budget_snapshot_artifact,
                _serialize_budget,
            )
        )

    members.extend(
        _collect_sequence_members(
            bundle.ping_artifacts,
            "ping_artifacts",
            Stage30_8CompactPingArtifact,
            PING_ARTIFACT_FILENAME_PREFIX,
            ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            validate_compact_ping_artifact,
            _serialize_ping,
        )
    )
    members.extend(
        _collect_sequence_members(
            bundle.dispatch_attempt_artifacts,
            "dispatch_attempt_artifacts",
            Stage30_8CompactDispatchAttemptArtifact,
            DISPATCH_ATTEMPT_FILENAME_PREFIX,
            ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
            validate_compact_dispatch_attempt_artifact,
            _serialize_dispatch,
        )
    )
    members.extend(
        _collect_sequence_members(
            bundle.error_artifacts,
            "error_artifacts",
            Stage30_8CompactErrorArtifact,
            ERROR_ARTIFACT_FILENAME_PREFIX,
            ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
            validate_compact_error_artifact,
            _serialize_error,
        )
    )

    if not members:
        raise _BundleRejected(WRITE_REASON_EMPTY_BUNDLE, "bundle")
    return members


def _collect_sequence_members(
    sequence: object,
    field_name: str,
    model_type: type,
    filename_prefix: str,
    kind: str,
    validator: Callable,
    serializer: Callable,
) -> List[Tuple[str, str, object, Callable, Callable]]:
    """Return member tuples for one tuple/list-valued bundle field.

    Enforces, fail-closed, that the field is a tuple / list and every
    element is the EXACT ``model_type`` (``type(x) is model_type``; a
    subclass is rejected). Raises ``_BundleRejected`` otherwise. Filenames
    are ``<prefix><1-based zero-padded index>.json`` so a lexical sort
    matches order. Pure; raises only the signal.
    """
    if not isinstance(sequence, (tuple, list)):
        raise _BundleRejected(
            WRITE_REASON_INVALID_ARTIFACT_TYPE, field_name
        )
    members: List[Tuple[str, str, object, Callable, Callable]] = []
    for index, element in enumerate(sequence):
        if type(element) is not model_type:
            raise _BundleRejected(
                WRITE_REASON_INVALID_ARTIFACT_TYPE, field_name
            )
        filename = (
            filename_prefix
            + format(index + 1, "04d")
            + ARTIFACT_FILENAME_SUFFIX
        )
        members.append((filename, kind, element, validator, serializer))
    return members


def _json_bytes(payload: object) -> bytes:
    """Serialize ``payload`` to deterministic UTF-8 JSON bytes.

    Sorted keys, no ASCII escaping (real UTF-8), two-space indent, and a
    single trailing newline. The persisted bytes carry no absolute path
    and no wall-clock value, so the same input serializes identically
    regardless of where it is written.
    """
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, indent=2
    )
    return (text + "\n").encode("utf-8")


def _bundle_manifest_payload(
    bundle: Stage30_8CompactSessionArtifactBundle,
    member_filenames: List[str],
) -> dict:
    """Build the deterministic, path-free bundle manifest payload."""
    return {
        "bundle_schema_version": STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
        "artifact_schema_version": STAGE30_8_ARTIFACT_SCHEMA_VERSION,
        "artifact_stage_id": STAGE30_8_ARTIFACT_STAGE_ID,
        "stage_minor_version": STAGE30_8_2_MINOR_VERSION,
        "session_id": bundle.session_id,
        "member_files": sorted(member_filenames),
        "counts": {
            "session_summary": (
                1 if bundle.session_summary is not None else 0
            ),
            "ping_artifacts": len(bundle.ping_artifacts),
            "dispatch_attempt_artifacts": len(
                bundle.dispatch_attempt_artifacts
            ),
            "error_artifacts": len(bundle.error_artifacts),
            "storage_budget_snapshot": (
                1 if bundle.storage_budget_snapshot is not None else 0
            ),
        },
    }


def _validation_result_payload(member_verdicts: List[dict]) -> dict:
    """Build the deterministic, path-free validation-result payload (all
    members are VALID, else the writer never reaches this point).
    """
    return {
        "bundle_schema_version": STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
        "validation_status": VALIDATION_STATUS_VALID,
        "reason": WRITE_REASON_OK,
        "safe_to_persist": True,
        "members": member_verdicts,
    }


# ---------------------------------------------------------------------------
# Filesystem seams (monkeypatchable in tests) + transient dir helpers
# ---------------------------------------------------------------------------


def _atomic_write(final_path: Path, data: bytes) -> None:
    """Write ``data`` to a sibling ``.tmp`` file, then atomically replace
    ``final_path``. ``Path.replace`` maps onto the platform atomic rename.
    """
    tmp_path = final_path.with_name(final_path.name + TEMP_FILENAME_SUFFIX)
    tmp_path.write_bytes(data)
    tmp_path.replace(final_path)


def _rename_dir(src: Path, dst: Path) -> None:
    """Rename directory ``src`` to ``dst`` (``dst`` must not exist). Maps
    onto the platform atomic directory rename; a separate seam from
    ``_atomic_write`` so a test can inject a promotion-time failure.
    """
    src.rename(dst)


def _remove_tree(path: Path) -> None:
    """Recursively remove ``path`` (stdlib / pathlib only; no shutil).
    Skips symlinked directories (unlinks the link, never follows it).
    """
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        for child in path.iterdir():
            _remove_tree(child)
        path.rmdir()
    else:
        path.unlink()


def _remove_tree_quiet(path: Optional[Path]) -> None:
    """Best-effort ``_remove_tree`` that swallows filesystem errors (a
    cleanup path that must never mask the real outcome).
    """
    if path is None:
        return
    try:
        _remove_tree(path)
    except OSError:
        pass


def _make_staging_dir(output_dir: Path, session_id: str) -> Path:
    """Create and return a fresh, unique hidden staging directory under
    ``output_dir`` (``.<session>.staging.<n>``). Creates ``output_dir``
    if needed. Raises ``OSError`` on an unrecoverable filesystem error.
    """
    base = "." + session_id + STAGING_DIR_INFIX
    index = 0
    while index < _MAX_TRANSIENT_PROBE:
        candidate = output_dir / (base + "." + str(index))
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            index += 1
            continue
    raise OSError("could not allocate a unique staging directory")


def _free_previous_path(output_dir: Path, session_id: str) -> Path:
    """Return a unique hidden ``.<session>.previous.<n>`` path under
    ``output_dir`` that does NOT yet exist (a rename target for the prior
    final directory). Raises ``OSError`` if none is free.
    """
    base = "." + session_id + PREVIOUS_DIR_INFIX
    index = 0
    while index < _MAX_TRANSIENT_PROBE:
        candidate = output_dir / (base + "." + str(index))
        if not candidate.exists():
            return candidate
        index += 1
    raise OSError("could not allocate a unique previous directory")


def _verify_staged_bundle(
    staging_dir: Path, member_filenames: List[str]
) -> bool:
    """Return ``True`` iff the staged directory is a complete bundle.

    Asserts the staged dir contains EXACTLY the member files plus
    ``validation_result.json`` + ``manifest.json`` (no missing member, no
    stray file, no leftover ``.tmp``), and the staged ``manifest.json``
    references exactly the staged member files. Never raises.
    """
    expected = set(member_filenames) | {
        VALIDATION_RESULT_FILENAME,
        MANIFEST_FILENAME,
    }
    try:
        present = {
            entry.name
            for entry in staging_dir.iterdir()
            if entry.is_file()
        }
    except OSError:
        return False
    if present != expected:
        return False
    try:
        manifest = json.loads(
            (staging_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return False
    listed = manifest.get("member_files")
    if not isinstance(listed, list):
        return False
    return set(listed) == set(member_filenames)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def write_compact_session_artifact_bundle(
    output_dir: object,
    bundle: object,
) -> Stage30_8CompactArtifactWriteResult:
    """Validate and atomically write a compact session artifact bundle
    under a caller-provided ``output_dir``.

    Fail-closed order:

      1. ``output_dir`` must be an explicit ``str`` / ``Path`` (no empty,
         no bare ``.``);
      2. ``bundle`` must be EXACTLY a
         ``Stage30_8CompactSessionArtifactBundle``;
      3. ``bundle.session_id`` must be a safe single path component;
      4. every present member must be the EXACT Stage 30.8.1 model type
         and must pass its matching Stage 30.8.1 validator (the bundle
         must hold at least one member);
      5. the session directory must resolve strictly under ``output_dir``.

    Only after ALL of the above does the writer build the COMPLETE bundle
    in a fresh hidden staging directory, verify it, and promote it onto
    the final session directory by a whole-directory rename (replacing any
    prior bundle entirely, so no stale member file survives). Any
    filesystem failure yields a ``WRITE_FAILED`` result with the prior
    final directory left intact (or rolled back); a successful write
    leaves the final directory containing EXACTLY the new bundle's files.

    Returns a ``Stage30_8CompactArtifactWriteResult``; never raises.
    """
    out_path = _coerce_output_dir(output_dir)
    if out_path is None:
        return _invalid_result(WRITE_REASON_INVALID_OUTPUT_DIR, "output_dir")

    if type(bundle) is not Stage30_8CompactSessionArtifactBundle:
        return _invalid_result(WRITE_REASON_INVALID_BUNDLE_TYPE, "bundle")

    if not _is_safe_path_component(bundle.session_id):
        return _invalid_result(
            WRITE_REASON_INVALID_SESSION_ID, "session_id"
        )

    try:
        members = _collect_members(bundle)
    except _BundleRejected as rejected:
        return _invalid_result(rejected.reason, rejected.blocked_field)

    # Validate every member BEFORE writing or staging anything.
    verdicts: List[dict] = []
    for filename, kind, artifact, validator, _serializer in members:
        result = validator(artifact)
        if result.status != VALIDATION_STATUS_VALID:
            return _invalid_result(
                WRITE_REASON_INVALID_ARTIFACT,
                result.blocked_field,
                validation_reason=result.reason,
            )
        verdicts.append(
            {
                "file": filename,
                "artifact_kind": kind,
                "validation_status": result.status,
            }
        )

    if not _resolve_within(out_path, bundle.session_id):
        return _invalid_result(WRITE_REASON_PATH_ESCAPE, "session_id")

    # Serialize the whole bundle up-front (pure; no I/O). A serialization
    # failure here means nothing is ever written. Members first, then the
    # validation result, then the manifest LAST (the commit marker).
    member_filenames = [filename for filename, _, _, _, _ in members]
    try:
        ordered_files: List[Tuple[str, bytes]] = [
            (filename, _json_bytes(serializer(artifact)))
            for filename, _kind, artifact, _validator, serializer in members
        ]
        ordered_files.append(
            (
                VALIDATION_RESULT_FILENAME,
                _json_bytes(_validation_result_payload(verdicts)),
            )
        )
        ordered_files.append(
            (
                MANIFEST_FILENAME,
                _json_bytes(
                    _bundle_manifest_payload(bundle, member_filenames)
                ),
            )
        )
    except (TypeError, ValueError):
        return _write_failed_result()

    final_dir = out_path / bundle.session_id
    return _stage_and_promote(
        out_path,
        final_dir,
        bundle.session_id,
        ordered_files,
        member_filenames,
        len(members),
    )


def _stage_and_promote(
    out_path: Path,
    final_dir: Path,
    session_id: str,
    ordered_files: List[Tuple[str, bytes]],
    member_filenames: List[str],
    artifact_count: int,
) -> Stage30_8CompactArtifactWriteResult:
    """Write the complete bundle into a staging dir, verify it, and
    promote it onto ``final_dir`` by whole-directory rename. Fail closed
    on every failure (prior final dir untouched or rolled back).
    """
    try:
        staging_dir = _make_staging_dir(out_path, session_id)
    except OSError:
        return _write_failed_result()

    # 1. Write the complete bundle into the staging dir (manifest last).
    try:
        for filename, data in ordered_files:
            _atomic_write(staging_dir / filename, data)
    except (OSError, ValueError, TypeError):
        _remove_tree_quiet(staging_dir)
        return _write_failed_result()

    # 2. Verify the staged bundle is complete + self-consistent.
    if not _verify_staged_bundle(staging_dir, member_filenames):
        _remove_tree_quiet(staging_dir)
        return _write_failed_result()

    # 3. Promote: move any prior final dir aside, then rename staging in.
    previous_path: Optional[Path] = None
    final_existed = final_dir.exists()
    try:
        if final_existed:
            previous_path = _free_previous_path(out_path, session_id)
            _rename_dir(final_dir, previous_path)
    except OSError:
        # Prior final dir is untouched (the rename-aside failed before it
        # moved anything we cannot recover); clean staging, fail closed.
        _remove_tree_quiet(staging_dir)
        return _write_failed_result()

    try:
        _rename_dir(staging_dir, final_dir)
    except OSError:
        # The new bundle could not be promoted. Roll the prior bundle
        # back into place so the existing valid bundle is not lost.
        if previous_path is not None:
            try:
                _rename_dir(previous_path, final_dir)
            except OSError:
                pass
        _remove_tree_quiet(staging_dir)
        return _write_failed_result()

    # 4. Success: drop the prior bundle (best-effort) and report.
    _remove_tree_quiet(previous_path)
    written_paths = tuple(
        str(final_dir / filename) for filename, _ in ordered_files
    )
    return Stage30_8CompactArtifactWriteResult(
        status=WRITE_STATUS_WRITTEN,
        reason=WRITE_REASON_OK,
        validation_status=VALIDATION_STATUS_VALID,
        validation_reason=VALIDATION_REASON_OK,
        blocked_field=None,
        safe_to_persist=True,
        session_dir=str(final_dir),
        written_paths=written_paths,
        artifact_count=artifact_count,
    )


__all__ = (
    # Minor version + bundle schema identity.
    "STAGE30_8_2_MINOR_VERSION",
    "STAGE30_8_2_BUNDLE_SCHEMA_VERSION",
    # Write status (closed set).
    "WRITE_STATUS_WRITTEN",
    "WRITE_STATUS_INVALID",
    "WRITE_STATUS_WRITE_FAILED",
    "STAGE30_8_2_WRITE_STATUS_VALUES",
    # Write reason (closed set).
    "WRITE_REASON_OK",
    "WRITE_REASON_INVALID_OUTPUT_DIR",
    "WRITE_REASON_INVALID_BUNDLE_TYPE",
    "WRITE_REASON_INVALID_SESSION_ID",
    "WRITE_REASON_EMPTY_BUNDLE",
    "WRITE_REASON_INVALID_ARTIFACT_TYPE",
    "WRITE_REASON_INVALID_ARTIFACT",
    "WRITE_REASON_PATH_ESCAPE",
    "WRITE_REASON_WRITE_FAILED",
    "STAGE30_8_2_WRITE_REASONS",
    # Deterministic filenames.
    "MANIFEST_FILENAME",
    "VALIDATION_RESULT_FILENAME",
    "SESSION_SUMMARY_FILENAME",
    "STORAGE_BUDGET_FILENAME",
    "PING_ARTIFACT_FILENAME_PREFIX",
    "DISPATCH_ATTEMPT_FILENAME_PREFIX",
    "ERROR_ARTIFACT_FILENAME_PREFIX",
    "ARTIFACT_FILENAME_SUFFIX",
    "TEMP_FILENAME_SUFFIX",
    # Records.
    "Stage30_8CompactSessionArtifactBundle",
    "Stage30_8CompactArtifactWriteResult",
    # Public entry point.
    "write_compact_session_artifact_bundle",
)
