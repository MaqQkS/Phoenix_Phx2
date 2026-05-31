"""Stage 30.8.3 offline compact session index / dedupe builder.

A pure, deterministic, fail-closed builder that consumes one or more
manifest-backed Stage 30.8.2 compact session bundle directories (read
through ``stage30_8_session_bundle_reader``) and returns an in-memory
``Stage30_8SessionIndexBuildResult``. Stage 30.8.3 is OFFLINE temp-dir
index logic only: it is NOT a database, NOT SQLite, NOT zstd /
compression, NOT live runtime, NOT live Discord, NOT real bot storage,
and it WRITES NOTHING -- the index is a pure in-memory projection.

The builder answers, for the supplied bundles, the five Stage 30.8.3
index questions (see ``stage30_8_session_index_models``): which session
bundles exist, which compact ping artifacts belong to each, which are
duplicate identities, which unique pings are retained for later
collection / replay, and which duplicates are suppressed.

Dedupe + provenance (deterministic, global across sessions):

  * a compact ping artifact whose OWN ``session_id`` is missing,
    non-string, or does not equal its bundle (manifest) session id is
    suppressed (INVALID_SUPPRESSED / SESSION_ID_MISMATCH); its provenance
    is never normalized and it is never retained or counted as a duplicate;
  * the dedupe identity of a compact ping artifact is its ``dedupe_key``
    ALONE (spec Section 9), resolved by ``resolve_ping_dedupe_identity``;
    ``ping_id`` is provenance / a tiebreak only, never a dedupe identity;
  * a ping carrying no usable ``dedupe_key`` is INVALID_SUPPRESSED /
    MISSING_IDENTITY and is never retained (there is NO ``ping_id``
    fallback);
  * the FIRST occurrence of each dedupe identity -- by the deterministic
    order (session_id ascending, then session_dir, then member filename /
    manifest order, then ping_id) -- is RETAINED; every later occurrence
    is DUPLICATE_SUPPRESSED and records the first occurrence's provenance;
  * ordering never depends on filesystem iteration order (the reader
    returns members in sorted manifest order; the builder sorts
    enumerated session dirs and the flat ping list).

Fail-closed: any session directory that does not read as a valid
manifest-backed bundle fails the WHOLE build closed (``READ_FAILED`` with
the offending dir + the underlying reader reason). Bad arguments yield
``INVALID_INPUT``; an unexpected internal error yields ``INDEX_FAILED``.
The builder NEVER raises.

Discipline / non-goals:

  * stdlib only (``pathlib`` / ``typing``); the JSON reading lives in the
    reader sibling, so the builder needs NO ``json``. It imports NO
    ``os`` (NO env read), NO ``sqlite3``, NO ``zstd`` / compression, NO
    network surface.
  * PHX2 imports: the Stage 30.8.3 reader + index-models siblings plus the
    Stage 30.8.1 artifact-models sibling (only for the closed-set ping
    artifact kind). NO Stage 21-29 / Stage 29.5 import, NO runtime /
    orchestrator / renderer import, NO Discord / provider import.
  * READ-ONLY: enumerates directories (``iterdir``) and resolves paths;
    it writes no file and creates no directory.
  * no side effects at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
)
from PHX2.stage30.stage30_8_session_bundle_reader import (
    BUNDLE_READ_STATUS_READ,
    Stage30_8BundleReadResult,
    read_compact_session_bundle,
)
from PHX2.stage30.stage30_8_session_index_models import (
    INDEX_BUILD_REASON_AMBIGUOUS_SOURCE,
    INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
    INDEX_BUILD_REASON_EMPTY,
    INDEX_BUILD_REASON_INTERNAL_ERROR,
    INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT,
    INDEX_BUILD_REASON_INVALID_SESSION_DIRS,
    INDEX_BUILD_REASON_NO_SOURCE,
    INDEX_BUILD_REASON_OK,
    INDEX_BUILD_STATUS_BUILT,
    INDEX_BUILD_STATUS_EMPTY,
    INDEX_BUILD_STATUS_INDEX_FAILED,
    INDEX_BUILD_STATUS_INVALID_INPUT,
    INDEX_BUILD_STATUS_READ_FAILED,
    PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
    PING_DEDUPE_STATUS_RETAINED,
    PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
    PING_SUPPRESS_REASON_MISSING_IDENTITY,
    PING_SUPPRESS_REASON_NONE,
    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
    Stage30_8DedupeIdentity,
    Stage30_8IndexedPingArtifact,
    Stage30_8SessionIndexBuildResult,
    Stage30_8SessionIndexRecord,
    has_dedupe_identity,
    resolve_ping_dedupe_identity,
)


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _result(
    status: str,
    reason: str,
    sessions: Tuple[Stage30_8SessionIndexRecord, ...] = (),
    retained: Tuple[Stage30_8IndexedPingArtifact, ...] = (),
    duplicates: Tuple[Stage30_8IndexedPingArtifact, ...] = (),
    invalid: Tuple[Stage30_8IndexedPingArtifact, ...] = (),
    blocked_session_dir: Optional[str] = None,
    read_failure_reason: Optional[str] = None,
) -> Stage30_8SessionIndexBuildResult:
    """Assemble a build result with derived counts (pure)."""
    total = len(retained) + len(duplicates) + len(invalid)
    return Stage30_8SessionIndexBuildResult(
        status=status,
        reason=reason,
        index_schema_version=STAGE30_8_3_INDEX_SCHEMA_VERSION,
        session_count=len(sessions),
        total_ping_count=total,
        retained_count=len(retained),
        duplicate_suppressed_count=len(duplicates),
        invalid_suppressed_count=len(invalid),
        sessions=sessions,
        retained_pings=retained,
        duplicate_pings=duplicates,
        invalid_pings=invalid,
        blocked_session_dir=blocked_session_dir,
        read_failure_reason=read_failure_reason,
    )


def _invalid_input(
    reason: str, blocked_session_dir: Optional[str] = None
) -> Stage30_8SessionIndexBuildResult:
    return _result(
        INDEX_BUILD_STATUS_INVALID_INPUT,
        reason,
        blocked_session_dir=blocked_session_dir,
    )


# ---------------------------------------------------------------------------
# Pure helpers: candidate session dir resolution
# ---------------------------------------------------------------------------


def _coerce_dir(value: object) -> Optional[Path]:
    """Return a ``Path`` for an explicit ``str`` / ``Path``, else ``None``.
    Rejects the empty string and the bare ``.``. Pure; never raises.
    """
    if isinstance(value, Path):
        candidate = value
    elif isinstance(value, str):
        if value == "":
            return None
        candidate = Path(value)
    else:
        return None
    if str(candidate) in ("", "."):
        return None
    return candidate


def _candidate_dirs_from_root(output_root: Path) -> List[Path]:
    """Return the sorted, non-hidden, non-symlink immediate subdirectories
    of ``output_root`` (the candidate session dirs). Hidden ``.<...>`` dirs
    -- the writer's transient ``.staging`` / ``.previous`` dirs -- are
    skipped. Sorted by name so enumeration is deterministic, never
    filesystem-iteration-order. May raise ``OSError`` (the caller wraps).
    """
    subdirs = [
        entry
        for entry in output_root.iterdir()
        if entry.is_dir()
        and not entry.is_symlink()
        and not entry.name.startswith(".")
    ]
    return sorted(subdirs, key=lambda p: p.name)


# ---------------------------------------------------------------------------
# Internal: provisional ping view (pre-dedupe)
# ---------------------------------------------------------------------------


def _opt_str(value: object) -> Optional[str]:
    """Return ``value`` when it is a non-empty string, else ``None``."""
    return value if isinstance(value, str) and value != "" else None


def _collect_ping_views(
    reads: List[Stage30_8BundleReadResult],
) -> List[dict]:
    """Flatten the compact ping members of every read bundle into
    provisional ping views (plain dicts; pure / never raises).

    A member is a ping iff its ``member_kind`` is the closed-set
    ``compact_ping_artifact`` kind. Identity axes are read defensively
    from the parsed payload's ``identity`` mapping.
    """
    views: List[dict] = []
    for read in reads:
        for member in read.members:
            if member.member_kind != ARTIFACT_KIND_COMPACT_PING_ARTIFACT:
                continue
            payload = member.payload
            identity = (
                payload.get("identity")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(identity, dict):
                identity = {}
            views.append(
                {
                    # The bundle (manifest) session id this ping belongs
                    # to -- the authoritative session for the index.
                    "session_id": read.session_id,
                    # The ping's OWN claimed session id (provenance gate):
                    # it must match the bundle session id (Major 3).
                    "member_session_id": _opt_str(
                        identity.get("session_id")
                    ),
                    "session_dir": read.session_dir,
                    "filename": member.filename,
                    "member_kind": member.member_kind,
                    "ping_id": _opt_str(identity.get("ping_id")),
                    "dedupe_key": _opt_str(identity.get("dedupe_key")),
                }
            )
    return views


def _ping_sort_key(view: dict) -> Tuple[str, str, str, str]:
    """Deterministic order: session_id asc, then session_dir, then member
    filename (== manifest order), then ping_id. ``None`` sorts as the empty
    string so it is stable / comparable.
    """
    return (
        view["session_id"] or "",
        view["session_dir"] or "",
        view["filename"] or "",
        view["ping_id"] or "",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_compact_session_index(
    session_dirs: object = None,
    output_root: object = None,
) -> Stage30_8SessionIndexBuildResult:
    """Build an offline compact session index over Stage 30.8.2 bundles.

    Provide EXACTLY ONE source:

      * ``session_dirs`` -- an explicit list / tuple of session bundle
        directories (each a ``str`` / ``Path``), or
      * ``output_root``  -- a directory whose non-hidden immediate
        subdirectories are the session bundles.

    Every candidate directory must read as a valid manifest-backed Stage
    30.8.2 bundle; any directory that does not fails the whole build closed
    (``READ_FAILED``). Returns a ``Stage30_8SessionIndexBuildResult`` (pure
    in-memory; the builder writes nothing and never raises).
    """
    try:
        return _build(session_dirs, output_root)
    except Exception:  # pragma: no cover - total fail-closed backstop
        return _result(
            INDEX_BUILD_STATUS_INDEX_FAILED,
            INDEX_BUILD_REASON_INTERNAL_ERROR,
        )


def _build(
    session_dirs: object, output_root: object
) -> Stage30_8SessionIndexBuildResult:
    """Index build body (see ``build_compact_session_index``)."""
    # 1. Exactly one source.
    if session_dirs is not None and output_root is not None:
        return _invalid_input(INDEX_BUILD_REASON_AMBIGUOUS_SOURCE)
    if session_dirs is None and output_root is None:
        return _invalid_input(INDEX_BUILD_REASON_NO_SOURCE)

    # 2. Resolve the ordered candidate session dirs.
    if output_root is not None:
        root = _coerce_dir(output_root)
        if root is None or not root.is_dir():
            return _invalid_input(
                INDEX_BUILD_REASON_INVALID_OUTPUT_ROOT,
                blocked_session_dir=str(output_root),
            )
        candidates = _candidate_dirs_from_root(root)
    else:
        if isinstance(session_dirs, (str, bytes)) or not isinstance(
            session_dirs, (list, tuple)
        ):
            return _invalid_input(INDEX_BUILD_REASON_INVALID_SESSION_DIRS)
        candidates = []
        for entry in session_dirs:
            coerced = _coerce_dir(entry)
            if coerced is None:
                return _invalid_input(
                    INDEX_BUILD_REASON_INVALID_SESSION_DIRS,
                    blocked_session_dir=str(entry),
                )
            candidates.append(coerced)

    # 3. No candidates -> EMPTY (a well-formed but empty source).
    if not candidates:
        return _result(INDEX_BUILD_STATUS_EMPTY, INDEX_BUILD_REASON_EMPTY)

    # 4. Read every candidate; fail the whole build closed on any invalid
    #    bundle.
    reads: List[Stage30_8BundleReadResult] = []
    for candidate in candidates:
        read = read_compact_session_bundle(candidate)
        if read.status != BUNDLE_READ_STATUS_READ:
            return _result(
                INDEX_BUILD_STATUS_READ_FAILED,
                INDEX_BUILD_REASON_BUNDLE_READ_FAILED,
                blocked_session_dir=read.session_dir,
                read_failure_reason=read.reason,
            )
        reads.append(read)

    # 5. Dedupe the flat ping set deterministically (global across
    #    sessions); first occurrence wins.
    views = sorted(_collect_ping_views(reads), key=_ping_sort_key)
    seen: Dict[Stage30_8DedupeIdentity, Stage30_8IndexedPingArtifact] = {}
    retained: List[Stage30_8IndexedPingArtifact] = []
    duplicates: List[Stage30_8IndexedPingArtifact] = []
    invalid: List[Stage30_8IndexedPingArtifact] = []

    for view in views:
        # Provenance gate (Major 3): the ping's own session id must be a
        # non-empty string equal to the bundle (manifest) session id. A
        # missing / non-string / mismatched member session id is suppressed
        # (never normalized, never retained, never counted as a duplicate).
        if (
            view["member_session_id"] is None
            or view["member_session_id"] != view["session_id"]
        ):
            invalid.append(
                _indexed_ping(
                    view,
                    resolve_ping_dedupe_identity(view["dedupe_key"]),
                    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
                    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
                )
            )
            continue
        # Dedupe identity is the dedupe_key ALONE (spec Section 9); a ping
        # lacking a usable dedupe_key is identity-less and never retained.
        identity = resolve_ping_dedupe_identity(view["dedupe_key"])
        if not has_dedupe_identity(identity):
            invalid.append(
                _indexed_ping(
                    view,
                    identity,
                    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
                    PING_SUPPRESS_REASON_MISSING_IDENTITY,
                )
            )
            continue
        first = seen.get(identity)
        if first is None:
            record = _indexed_ping(
                view,
                identity,
                PING_DEDUPE_STATUS_RETAINED,
                PING_SUPPRESS_REASON_NONE,
            )
            seen[identity] = record
            retained.append(record)
        else:
            duplicates.append(
                _indexed_ping(
                    view,
                    identity,
                    PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
                    PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
                    duplicate_of_session_id=first.session_id,
                    duplicate_of_artifact_filename=first.artifact_filename,
                )
            )

    # 6. Group the indexed pings back into per-session records (one per
    #    read bundle directory), ordered by (session_id, session_dir).
    sessions = _build_session_records(reads, retained + duplicates + invalid)

    return _result(
        INDEX_BUILD_STATUS_BUILT,
        INDEX_BUILD_REASON_OK,
        sessions=sessions,
        retained=tuple(retained),
        duplicates=tuple(duplicates),
        invalid=tuple(invalid),
    )


def _indexed_ping(
    view: dict,
    identity: Stage30_8DedupeIdentity,
    dedupe_status: str,
    suppress_reason: str,
    duplicate_of_session_id: Optional[str] = None,
    duplicate_of_artifact_filename: Optional[str] = None,
) -> Stage30_8IndexedPingArtifact:
    """Build one indexed ping record from a provisional view + verdict."""
    return Stage30_8IndexedPingArtifact(
        session_id=view["session_id"],
        session_dir=view["session_dir"],
        artifact_filename=view["filename"],
        member_kind=view["member_kind"],
        ping_id=view["ping_id"],
        dedupe_key=view["dedupe_key"],
        identity_kind=identity.kind,
        identity_value=identity.value,
        dedupe_status=dedupe_status,
        suppress_reason=suppress_reason,
        duplicate_of_session_id=duplicate_of_session_id,
        duplicate_of_artifact_filename=duplicate_of_artifact_filename,
    )


def _build_session_records(
    reads: List[Stage30_8BundleReadResult],
    indexed: List[Stage30_8IndexedPingArtifact],
) -> Tuple[Stage30_8SessionIndexRecord, ...]:
    """Group indexed pings by session dir into per-session records.

    One record per read bundle directory (so two bundles that happen to
    share a manifest session id stay distinct). Pings within a session are
    ordered by member filename; sessions are ordered by (session_id,
    session_dir). Pure.
    """
    by_dir: Dict[str, List[Stage30_8IndexedPingArtifact]] = {}
    for record in indexed:
        by_dir.setdefault(record.session_dir, []).append(record)

    records: List[Stage30_8SessionIndexRecord] = []
    for read in reads:
        pings = sorted(
            by_dir.get(read.session_dir, []),
            key=lambda r: r.artifact_filename,
        )
        retained_n = sum(
            1
            for p in pings
            if p.dedupe_status == PING_DEDUPE_STATUS_RETAINED
        )
        duplicate_n = sum(
            1
            for p in pings
            if p.dedupe_status == PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED
        )
        invalid_n = sum(
            1
            for p in pings
            if p.dedupe_status == PING_DEDUPE_STATUS_INVALID_SUPPRESSED
        )
        records.append(
            Stage30_8SessionIndexRecord(
                session_id=read.session_id,
                session_dir=read.session_dir,
                bundle_schema_version=read.bundle_schema_version,
                ping_artifact_count=len(pings),
                retained_ping_count=retained_n,
                duplicate_suppressed_ping_count=duplicate_n,
                invalid_suppressed_ping_count=invalid_n,
                pings=tuple(pings),
            )
        )

    return tuple(
        sorted(
            records, key=lambda r: (r.session_id or "", r.session_dir)
        )
    )


__all__ = (
    "build_compact_session_index",
)
