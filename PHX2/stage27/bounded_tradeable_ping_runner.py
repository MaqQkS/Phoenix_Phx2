"""Stage 27.6 bounded dry-run runner.

Stage 27.6 ships a deterministic, bounded, operator-controlled
runner that chains the Stage 27.3 -> 27.4 -> 27.5 pipeline through
the Stage 27.6 live-candidate assembler over a caller-supplied list
of fake provider events and emits a single immutable run summary.

The runner is DRY_RUN ONLY:

  * it NEVER opens a network connection,
  * it NEVER imports a Discord / Telegram / X-social / messaging
    library,
  * it NEVER imports a network / RPC / DB / scheduler library,
  * it NEVER reads the process environment,
  * it NEVER persists a dedupe ledger across runs,
  * it NEVER enforces a Stage 26 candidate policy,
  * it NEVER decides a trading verdict,
  * it NEVER promotes UNKNOWN / DISAGREE / USDC into the existing
    SOL calibration lane,
  * it NEVER widens the closed-set vocabularies emitted by Stage
    27.2 / 27.3 / 27.4 / 27.5 / 27.6.

Two-factor LIVE authorization (mirrored from Stage 27.1):

  * if the caller passes ``live_mode_authority="LIVE_ALLOWED"`` the
    runner fail-closes by refusing to start. Stage 27.6 is a dry-
    run-only substage; the LIVE dispatch path lives in a later
    substage. The refusal is reported as a typed
    ``Stage27_6LiveModeRefusedError`` plus a run summary with
    ``mode=LIVE_REFUSED``.
  * any other ``live_mode_authority`` value (``DRY_RUN`` /
    ``LIVE_REFUSED``) runs as a dry-run runner.

Bounds:

  * the runner refuses to start unless at least one of
    ``max_events`` / ``max_pings`` is a positive integer. ``None``
    on both bounds is a typed configuration error.
  * the runner stops as soon as ``events_seen`` >= ``max_events``
    (when set) OR ``pings_rendered`` >= ``max_pings`` (when set).
    Either bound can be set independently.

Determinism:

  * the run summary is produced from caller-supplied identifiers
    plus the injected clocks; identical inputs always produce an
    identical summary (apart from the wall-clock fields, which come
    from the injected clock).
  * the optional run-summary artifact (when ``output_root`` is set
    and ``write_summary_artifact=True``) is written through the
    Stage 27.5 path-safety helpers so traversal escapes are
    rejected before any file write.

This module imports only stdlib (``json`` / ``pathlib`` / ``typing``)
plus Stage 27.5 / Stage 27.6 production modules. It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, NamedTuple, Optional, Protocol

from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_ERROR,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
    assemble_live_candidate,
)
from PHX2.stage27.live_dedupe import Stage27_6RunLocalDedupe
from PHX2.stage27.private_ping_artifact_writer import (
    Stage27_5ArtifactExistsError,
    Stage27_5ArtifactWriteError,
    Stage27_5FilenameError,
    Stage27_5OutputRootError,
    Stage27_5PathEscapeError,
)
from PHX2.stage27.provider_ingest_models import (
    ProviderIngestInputRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.6 path-safety helpers (mirror Stage 27.5 discipline)
# ---------------------------------------------------------------------------
#
# Stage 27.6 re-uses the Stage 27.5 typed error hierarchy but ships
# its own small safety helpers so the runner does not depend on
# module-private Stage 27.5 symbols. The shape of the checks mirrors
# the Stage 27.5 writer exactly so two artifacts that fail safety
# at Stage 27.5 also fail safety at Stage 27.6.


_FORBIDDEN_FILENAME_LITERALS: frozenset[str] = frozenset(
    {"", ".", ".."}
)


def _validate_summary_filename(filename: object) -> str:
    if not isinstance(filename, str):
        raise Stage27_5FilenameError(
            f"filename must be a string, got {type(filename)!r}"
        )
    if filename in _FORBIDDEN_FILENAME_LITERALS:
        raise Stage27_5FilenameError(
            f"filename {filename!r} is not a valid Stage 27.6 "
            "run-summary filename"
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


def _resolve_under_summary_root(
    output_root: Path, filename: str
) -> Path:
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

    safe_name = _validate_summary_filename(filename)
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
# Stage 27.6 run-mode + summary version axes
# ---------------------------------------------------------------------------


STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION: str = (
    "stage27_v0_run_summary"
)


RUN_MODE_DRY_RUN: str = "DRY_RUN"
RUN_MODE_LIVE_REFUSED: str = "LIVE_REFUSED"

RUN_MODE_VALUES: tuple[str, ...] = (
    RUN_MODE_DRY_RUN,
    RUN_MODE_LIVE_REFUSED,
)


# Stage 27.6 mirrors the Stage 27.1 closed-set authority tokens but
# does NOT import them; importing Stage 27.1 production code would
# widen the Stage 27 cross-substage boundary. Tests and real callers
# pass whichever string they like; only the literal ``"LIVE_ALLOWED"``
# triggers the fail-closed refusal.
LIVE_AUTHORITY_DRY_RUN: str = "DRY_RUN"
LIVE_AUTHORITY_LIVE_REFUSED: str = "LIVE_REFUSED"
LIVE_AUTHORITY_LIVE_ALLOWED: str = "LIVE_ALLOWED"


# ---------------------------------------------------------------------------
# Stage 27.6 typed runner errors
# ---------------------------------------------------------------------------


class Stage27_6RunnerError(Exception):
    """Base class for Stage 27.6 bounded-runner errors."""


class Stage27_6RunnerBoundsError(Stage27_6RunnerError):
    """The runner was configured with no usable bound.

    Stage 27.6 refuses to start when both ``max_events`` and
    ``max_pings`` are ``None`` / non-positive.
    """


class Stage27_6LiveModeRefusedError(Stage27_6RunnerError):
    """The runner was asked to dispatch LIVE but Stage 27.6 is DRY-RUN only.

    The Stage 27 LIVE dispatch surface lives in a later substage.
    Stage 27.6 fail-closes here so an operator cannot accidentally
    enable a LIVE send during the dry-run bounded runner pass.
    """


# ---------------------------------------------------------------------------
# Stage 27.6 clock Protocol (wall-time for run summary)
# ---------------------------------------------------------------------------


class Stage27_6Clock(Protocol):
    """Injectable wall-clock for Stage 27.6 run summaries.

    Returns an ISO-8601 UTC string. The runner reads the clock
    exactly twice: once at run start, once at run finish. Tests can
    pin the wall-clock fields by injecting a deterministic fake.
    """

    def now_utc_iso(self) -> str: ...


# ---------------------------------------------------------------------------
# Stage 27.6 run summary record
# ---------------------------------------------------------------------------


class Stage27_6RunSummaryRecord(NamedTuple):
    """Immutable Stage 27.6 bounded dry-run summary.

    Fields:

      * ``run_id``                  -- caller-supplied; ``None`` when
                                       not attached yet.
      * ``session_id``              -- caller-supplied; ``None`` when
                                       not attached yet.
      * ``mode``                    -- closed-set ``RUN_MODE`` token.
                                       ``LIVE_REFUSED`` iff the
                                       runner fail-closed before
                                       processing any event.
      * ``events_seen``             -- count of events drained from
                                       the input iterable.
      * ``events_composed``         -- count of events whose
                                       Stage 27.3 composition
                                       returned ``COMPOSED``.
      * ``candidates_assembled``    -- count of candidates whose
                                       final status is ``ASSEMBLED``
                                       (assembled without writing an
                                       artifact).
      * ``pings_rendered``          -- count of candidates whose
                                       final status is
                                       ``RENDERED_DRY_RUN``.
      * ``artifacts_written``       -- count of dry-run artifact
                                       files persisted (two per
                                       successfully-written candidate
                                       -- payload + provenance).
                                       Counts SUPPRESSED_* artifacts
                                       as well as RENDERED_DRY_RUN
                                       artifacts so the operator
                                       review surface sees every
                                       persisted file.
      * ``duplicates_skipped``      -- count of
                                       ``SKIPPED_DUPLICATE`` outputs.
      * ``unknown_suppressed``      -- count of
                                       ``SUPPRESSED_UNKNOWN_PAIR``.
      * ``disagree_suppressed``     -- count of
                                       ``SUPPRESSED_DISAGREE_PAIR``.
      * ``unsupported_skipped``     -- count of
                                       ``SKIPPED_UNSUPPORTED_EVENT``
                                       plus ``SKIPPED_MISSING_TOKEN``.
      * ``artifact_write_failures`` -- count of
                                       ``ARTIFACT_WRITE_FAILED``.
      * ``errors``                  -- count of ``ERROR``.
      * ``started_at_utc``          -- ISO-8601 UTC wall-time at run
                                       start.
      * ``finished_at_utc``         -- ISO-8601 UTC wall-time at run
                                       finish.
      * ``schema_version``          -- locked Stage 27.6 run-summary
                                       schema version string.
      * ``candidate_schema_version`` -- locked Stage 27.6 candidate
                                       schema version string (so a
                                       reader can pin both axes).
      * ``stop_reason``             -- short closed-set token
                                       describing why the runner
                                       stopped: ``INPUT_EXHAUSTED``,
                                       ``MAX_EVENTS_REACHED``,
                                       ``MAX_PINGS_REACHED``, or
                                       ``LIVE_MODE_REFUSED``.
    """

    run_id: Optional[str]
    session_id: Optional[str]
    mode: str
    events_seen: int
    events_composed: int
    candidates_assembled: int
    pings_rendered: int
    artifacts_written: int
    duplicates_skipped: int
    unknown_suppressed: int
    disagree_suppressed: int
    unsupported_skipped: int
    artifact_write_failures: int
    errors: int
    started_at_utc: str
    finished_at_utc: str
    schema_version: str
    candidate_schema_version: str
    stop_reason: str


# Stop-reason closed set.

STOP_REASON_INPUT_EXHAUSTED: str = "INPUT_EXHAUSTED"
STOP_REASON_MAX_EVENTS_REACHED: str = "MAX_EVENTS_REACHED"
STOP_REASON_MAX_PINGS_REACHED: str = "MAX_PINGS_REACHED"
STOP_REASON_LIVE_MODE_REFUSED: str = "LIVE_MODE_REFUSED"

STOP_REASON_VALUES: tuple[str, ...] = (
    STOP_REASON_INPUT_EXHAUSTED,
    STOP_REASON_MAX_EVENTS_REACHED,
    STOP_REASON_MAX_PINGS_REACHED,
    STOP_REASON_LIVE_MODE_REFUSED,
)


# ---------------------------------------------------------------------------
# Bounds + mode validation helpers
# ---------------------------------------------------------------------------


def _validate_bounds(
    max_events: Optional[int], max_pings: Optional[int]
) -> None:
    """Refuse the run if no usable bound was supplied.

    Stage 27.6 refuses to start when both bounds are ``None`` or
    when the only supplied bound is non-positive. A defensive guard
    so an operator never accidentally launches an unbounded run.
    """
    if max_events is None and max_pings is None:
        raise Stage27_6RunnerBoundsError(
            "Stage 27.6 bounded runner requires at least one of "
            "max_events / max_pings to be set"
        )
    if max_events is not None and (
        not isinstance(max_events, int)
        or isinstance(max_events, bool)
        or max_events <= 0
    ):
        raise Stage27_6RunnerBoundsError(
            f"max_events must be a positive int when set; got "
            f"{max_events!r}"
        )
    if max_pings is not None and (
        not isinstance(max_pings, int)
        or isinstance(max_pings, bool)
        or max_pings <= 0
    ):
        raise Stage27_6RunnerBoundsError(
            f"max_pings must be a positive int when set; got "
            f"{max_pings!r}"
        )


# ---------------------------------------------------------------------------
# Run summary canonical JSON + writer
# ---------------------------------------------------------------------------


def canonical_run_summary_json(
    summary: Stage27_6RunSummaryRecord,
) -> str:
    """Return the canonical JSON encoding of a run summary.

    Stable across runs: ``sort_keys=True``,
    ``separators=(",", ":")``, ``ensure_ascii=False``.

    Pure / deterministic.
    """
    if not isinstance(summary, Stage27_6RunSummaryRecord):
        raise TypeError(
            "canonical_run_summary_json requires a "
            "Stage27_6RunSummaryRecord"
        )
    mapping = {
        "run_id": summary.run_id,
        "session_id": summary.session_id,
        "mode": summary.mode,
        "events_seen": summary.events_seen,
        "events_composed": summary.events_composed,
        "candidates_assembled": summary.candidates_assembled,
        "pings_rendered": summary.pings_rendered,
        "artifacts_written": summary.artifacts_written,
        "duplicates_skipped": summary.duplicates_skipped,
        "unknown_suppressed": summary.unknown_suppressed,
        "disagree_suppressed": summary.disagree_suppressed,
        "unsupported_skipped": summary.unsupported_skipped,
        "artifact_write_failures": (
            summary.artifact_write_failures
        ),
        "errors": summary.errors,
        "started_at_utc": summary.started_at_utc,
        "finished_at_utc": summary.finished_at_utc,
        "schema_version": summary.schema_version,
        "candidate_schema_version": (
            summary.candidate_schema_version
        ),
        "stop_reason": summary.stop_reason,
    }
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


DEFAULT_RUN_SUMMARY_FILENAME_PREFIX: str = "run_"
DEFAULT_RUN_SUMMARY_FILENAME_SUFFIX: str = "_summary.json"


def default_run_summary_filename(run_id: Optional[str]) -> str:
    """Return ``run_<run_id>_summary.json``.

    When ``run_id`` is ``None`` / empty the filename falls back to
    ``run_unknown_summary.json`` so the dry-run summary still lands
    inside the output root.
    """
    chosen = (
        run_id
        if isinstance(run_id, str) and run_id != ""
        else "unknown"
    )
    candidate = (
        DEFAULT_RUN_SUMMARY_FILENAME_PREFIX
        + chosen
        + DEFAULT_RUN_SUMMARY_FILENAME_SUFFIX
    )
    return _validate_summary_filename(candidate)


def write_run_summary_artifact(
    summary: Stage27_6RunSummaryRecord,
    output_root: Path,
    filename: Optional[str] = None,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the canonical JSON encoding of a Stage 27.6 run summary.

    Returns the resolved target ``Path``. Raises a Stage 27.5
    ``Stage27_5ArtifactWriteError`` subclass on any safety failure
    (the Stage 27.5 path-safety helpers are reused so traversal
    escapes / unsafe filenames are refused the same way the
    Stage 27.5 dry-run writer refuses them).

    Pure / deterministic except for the single ``Path.write_bytes``.
    """
    if not isinstance(summary, Stage27_6RunSummaryRecord):
        raise TypeError(
            "write_run_summary_artifact requires a "
            "Stage27_6RunSummaryRecord"
        )
    chosen_filename = (
        filename
        if filename is not None
        else default_run_summary_filename(summary.run_id)
    )
    target = _resolve_under_summary_root(
        output_root, chosen_filename
    )
    if target.exists() and not overwrite:
        raise Stage27_5ArtifactExistsError(
            f"Stage 27.6 run-summary target already exists: "
            f"{target!r}"
        )
    encoded = canonical_run_summary_json(summary)
    target.write_bytes((encoded + "\n").encode("utf-8"))
    return target


# ---------------------------------------------------------------------------
# Live-mode-refused short-circuit summary
# ---------------------------------------------------------------------------


def _build_live_refused_summary(
    *,
    run_id: Optional[str],
    session_id: Optional[str],
    started_at_utc: str,
    finished_at_utc: str,
) -> Stage27_6RunSummaryRecord:
    return Stage27_6RunSummaryRecord(
        run_id=run_id,
        session_id=session_id,
        mode=RUN_MODE_LIVE_REFUSED,
        events_seen=0,
        events_composed=0,
        candidates_assembled=0,
        pings_rendered=0,
        artifacts_written=0,
        duplicates_skipped=0,
        unknown_suppressed=0,
        disagree_suppressed=0,
        unsupported_skipped=0,
        artifact_write_failures=0,
        errors=0,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        schema_version=STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        stop_reason=STOP_REASON_LIVE_MODE_REFUSED,
    )


# ---------------------------------------------------------------------------
# Bounded dry-run runner
# ---------------------------------------------------------------------------


class Stage27_6BoundedDryRunRunResult(NamedTuple):
    """Immutable bounded dry-run runner result.

    Bundles the run summary with the per-event candidate records
    so tests can pin both axes deterministically. The candidate
    tuple is in input-order.
    """

    summary: Stage27_6RunSummaryRecord
    candidates: tuple[Stage27_6LiveCandidateRecord, ...]


def run_bounded_dry_run(
    events: Iterable[ProviderIngestInputRecord],
    sources: Stage27_6Sources,
    *,
    clock: Stage27_6Clock,
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    max_events: Optional[int] = None,
    max_pings: Optional[int] = None,
    live_mode_authority: str = LIVE_AUTHORITY_DRY_RUN,
    write_artifacts: bool = True,
    write_summary_artifact: bool = False,
    candidate_id_prefix: str = "cand_",
    ping_id_prefix: str = "ping_",
    raise_on_live_refused: bool = False,
) -> Stage27_6BoundedDryRunRunResult:
    """Drive the Stage 27.6 bounded dry-run runner.

    Returns a ``Stage27_6BoundedDryRunRunResult`` with the run
    summary plus the per-event candidate tuple. The runner never
    raises a Stage 27.3 / 27.4 / 27.5 typed error to the caller --
    every typed failure resolves to a ``CANDIDATE_STATUS_ERROR`` /
    ``CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED`` candidate and is
    counted in the run summary.

    Argument discipline:

      * ``events``                    -- iterable of
                                         ``ProviderIngestInputRecord``.
                                         The runner drains the
                                         iterable lazily and stops as
                                         soon as a bound is hit.
      * ``sources``                   -- injected Stage 27.4 / 27.5
                                         source + clock bundle.
      * ``clock``                     -- Stage 27.6 wall clock for
                                         run summary timestamps.
      * ``output_root``               -- pre-existing directory.
                                         Required when
                                         ``write_artifacts=True`` or
                                         ``write_summary_artifact=True``.
      * ``run_id`` / ``session_id``   -- caller-supplied identity
                                         strings. Stage 27.6 does
                                         NOT import Stage 27.1.
      * ``max_events`` / ``max_pings`` -- bounds. At least one MUST
                                         be set (and positive).
      * ``live_mode_authority``       -- if equal to
                                         ``"LIVE_ALLOWED"`` the
                                         runner fail-closes; any
                                         other value runs dry.
      * ``write_artifacts``           -- forwarded to
                                         ``assemble_live_candidate``.
      * ``write_summary_artifact``    -- ``True`` to persist the run
                                         summary as a Stage 27.6
                                         run-summary artifact.
      * ``candidate_id_prefix`` /
        ``ping_id_prefix``            -- short prefixes used to
                                         derive deterministic ids
                                         from the event index.
      * ``raise_on_live_refused``     -- ``True`` to raise
                                         ``Stage27_6LiveModeRefusedError``
                                         in addition to returning a
                                         LIVE_REFUSED summary;
                                         defaults to ``False`` so
                                         tests can inspect the
                                         summary without a try /
                                         except.
    """
    _validate_bounds(max_events, max_pings)

    started_at_utc = clock.now_utc_iso()

    if live_mode_authority == LIVE_AUTHORITY_LIVE_ALLOWED:
        finished_at_utc = clock.now_utc_iso()
        summary = _build_live_refused_summary(
            run_id=run_id,
            session_id=session_id,
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
        )
        if write_summary_artifact and output_root is not None:
            try:
                write_run_summary_artifact(summary, output_root)
            except Stage27_5ArtifactWriteError:
                # The LIVE_REFUSED summary is observable in-process
                # even if its on-disk artifact cannot be written.
                pass
        if raise_on_live_refused:
            raise Stage27_6LiveModeRefusedError(
                "Stage 27.6 is DRY-RUN only; LIVE_ALLOWED refused"
            )
        return Stage27_6BoundedDryRunRunResult(
            summary=summary, candidates=()
        )

    if write_artifacts and output_root is None:
        raise Stage27_6RunnerBoundsError(
            "Stage 27.6 runner requires output_root when "
            "write_artifacts=True"
        )

    dedupe = Stage27_6RunLocalDedupe()

    events_seen = 0
    events_composed = 0
    candidates_assembled = 0
    pings_rendered = 0
    artifacts_written = 0
    duplicates_skipped = 0
    unknown_suppressed = 0
    disagree_suppressed = 0
    unsupported_skipped = 0
    artifact_write_failures = 0
    errors = 0

    candidates: list[Stage27_6LiveCandidateRecord] = []
    stop_reason = STOP_REASON_INPUT_EXHAUSTED

    for index, ingest_input in enumerate(events):
        if max_events is not None and events_seen >= max_events:
            stop_reason = STOP_REASON_MAX_EVENTS_REACHED
            break
        if max_pings is not None and pings_rendered >= max_pings:
            stop_reason = STOP_REASON_MAX_PINGS_REACHED
            break
        events_seen += 1
        candidate_id = f"{candidate_id_prefix}{index:04d}"
        ping_id = f"{ping_id_prefix}{index:04d}"
        try:
            candidate = assemble_live_candidate(
                ingest_input,
                sources,
                dedupe,
                candidate_id=candidate_id,
                output_root=output_root,
                run_id=run_id,
                session_id=session_id,
                ping_id=ping_id,
                write_artifacts=write_artifacts,
            )
        except Exception:
            errors += 1
            continue
        candidates.append(candidate)

        if (
            candidate.ingest_output.composition_status
            == "COMPOSED"
        ):
            events_composed += 1

        status = candidate.candidate_status
        # Count artifacts whenever the writer actually persisted both
        # files (SUPPRESSED_* candidates also persist a dry-run
        # artifact for operator review).
        if (
            candidate.write_attempted
            and candidate.payload_artifact_path is not None
            and candidate.provenance_artifact_path is not None
        ):
            artifacts_written += 2
        if status == CANDIDATE_STATUS_RENDERED_DRY_RUN:
            pings_rendered += 1
        elif status == CANDIDATE_STATUS_ASSEMBLED:
            candidates_assembled += 1
        elif status == CANDIDATE_STATUS_SKIPPED_DUPLICATE:
            duplicates_skipped += 1
        elif status == CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR:
            unknown_suppressed += 1
        elif status == CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR:
            disagree_suppressed += 1
        elif status in (
            CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
            CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
        ):
            unsupported_skipped += 1
        elif status == CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED:
            artifact_write_failures += 1
        elif status == CANDIDATE_STATUS_ERROR:
            errors += 1

        # Re-check bounds after counters are updated so a max_pings
        # bound fires immediately after the bound-hitting event.
        if max_events is not None and events_seen >= max_events:
            stop_reason = STOP_REASON_MAX_EVENTS_REACHED
            break
        if max_pings is not None and pings_rendered >= max_pings:
            stop_reason = STOP_REASON_MAX_PINGS_REACHED
            break

    finished_at_utc = clock.now_utc_iso()

    summary = Stage27_6RunSummaryRecord(
        run_id=run_id,
        session_id=session_id,
        mode=RUN_MODE_DRY_RUN,
        events_seen=events_seen,
        events_composed=events_composed,
        candidates_assembled=candidates_assembled,
        pings_rendered=pings_rendered,
        artifacts_written=artifacts_written,
        duplicates_skipped=duplicates_skipped,
        unknown_suppressed=unknown_suppressed,
        disagree_suppressed=disagree_suppressed,
        unsupported_skipped=unsupported_skipped,
        artifact_write_failures=artifact_write_failures,
        errors=errors,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        schema_version=STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        stop_reason=stop_reason,
    )

    if write_summary_artifact and output_root is not None:
        try:
            write_run_summary_artifact(summary, output_root)
        except Stage27_5ArtifactWriteError:
            # The runner result still surfaces the summary in-process
            # so a writer failure here does not invalidate the run.
            pass

    return Stage27_6BoundedDryRunRunResult(
        summary=summary, candidates=tuple(candidates)
    )


# Re-exported for downstream identifier scans / closure audits.
__all__ = (
    "STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION",
    "RUN_MODE_DRY_RUN",
    "RUN_MODE_LIVE_REFUSED",
    "RUN_MODE_VALUES",
    "LIVE_AUTHORITY_DRY_RUN",
    "LIVE_AUTHORITY_LIVE_REFUSED",
    "LIVE_AUTHORITY_LIVE_ALLOWED",
    "STOP_REASON_INPUT_EXHAUSTED",
    "STOP_REASON_MAX_EVENTS_REACHED",
    "STOP_REASON_MAX_PINGS_REACHED",
    "STOP_REASON_LIVE_MODE_REFUSED",
    "STOP_REASON_VALUES",
    "Stage27_6RunnerError",
    "Stage27_6RunnerBoundsError",
    "Stage27_6LiveModeRefusedError",
    "Stage27_6Clock",
    "Stage27_6RunSummaryRecord",
    "Stage27_6BoundedDryRunRunResult",
    "canonical_run_summary_json",
    "default_run_summary_filename",
    "write_run_summary_artifact",
    "run_bounded_dry_run",
)
