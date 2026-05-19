"""Stage 23.5 deterministic artifact writer.

The writer serializes a ``Stage23RunnerResult`` produced by
``PHX2.stage23.runner.run_stage23_filters`` into a deterministic
set of files under an operator-supplied output directory. Every
write is pure of side effects beyond the output directory:

  * No network I/O, no env reads, no clock reads.
  * Writes ONLY to the operator-supplied output directory.
  * Writes EXACTLY the locked Stage 23 artifact filenames.
  * Never modifies files the writer did not write itself.

Artifact filenames (locked):

  * ``stage23_filter_evaluations.jsonl``
  * ``stage23_filter_summary.csv``
  * ``stage23_reason_code_counts.csv``
  * ``stage23_data_status_counts.csv``
  * ``stage23_label_counts.csv``
  * ``stage23_manifest.json``

Determinism guarantees:

  * Stable file ordering: the manifest enumerates artifacts in
    sorted-basename order.
  * Stable row ordering: JSONL rows are sorted by
    ``(token_mint, event_id, captured_event_id, filter_name)``;
    CSV rows are sorted by the row's full tuple key in
    declaration order.
  * Stable JSON serialization: canonical JSON (sorted keys, no
    whitespace, ASCII-safe) is used everywhere.
  * Deterministic CSV: explicit ``\\n`` line endings; no quoting
    needed because every value is controlled closed-set
    vocabulary or a non-negative integer.

Safety guarantees:

  * The writer performs a redaction sweep over every artifact's
    rendered text BEFORE writing. URL-shape literals and webhook
    host literals raise ``Stage23ManifestError`` rather than
    landing on disk. Mirrors the Stage 23 input reader's
    redaction discipline.
  * The writer uses ``Stage23ManifestError`` for every contract
    violation (invalid output directory, secret leakage). The
    writer never raises a bare ``OSError`` for an invalid
    directory because the runner's caller is expected to handle
    typed Stage 23 errors.

This module imports only stdlib (``hashlib`` / ``pathlib`` /
``collections`` / ``types`` / ``typing``) plus the Stage 23
constants / errors / models / manifest / runner. It does NOT
import Stage 21 or Stage 22 modules, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple

from PHX2.stage23.constants import (
    OBSERVE_ONLY_MODE,
    STAGE_NAME,
    STAGE_VERSION,
    STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE23_MANIFEST_SCHEMA_VERSION,
)
from PHX2.stage23.errors import Stage23ManifestError
from PHX2.stage23.models import (
    Stage23FilterEvaluation,
    canonical_json,
)
from PHX2.stage23.runner import Stage23RunnerResult
from PHX2.stage23.stage23_manifest import REDACTION_CONFIRMED_TOKEN


# ---------------------------------------------------------------------------
# Locked artifact filenames
# ---------------------------------------------------------------------------


ARTIFACT_FILENAME_EVALUATIONS: str = "stage23_filter_evaluations.jsonl"
ARTIFACT_FILENAME_FILTER_SUMMARY: str = "stage23_filter_summary.csv"
ARTIFACT_FILENAME_REASON_CODE_COUNTS: str = (
    "stage23_reason_code_counts.csv"
)
ARTIFACT_FILENAME_DATA_STATUS_COUNTS: str = (
    "stage23_data_status_counts.csv"
)
ARTIFACT_FILENAME_LABEL_COUNTS: str = "stage23_label_counts.csv"
ARTIFACT_FILENAME_MANIFEST: str = "stage23_manifest.json"


# The five non-manifest artifacts in canonical sorted-basename
# order. The manifest enumerates these in this same order so
# every run's manifest carries the same artifact ordering.
NON_MANIFEST_ARTIFACT_FILENAMES: tuple[str, ...] = (
    ARTIFACT_FILENAME_DATA_STATUS_COUNTS,
    ARTIFACT_FILENAME_EVALUATIONS,
    ARTIFACT_FILENAME_FILTER_SUMMARY,
    ARTIFACT_FILENAME_LABEL_COUNTS,
    ARTIFACT_FILENAME_REASON_CODE_COUNTS,
)


ALL_ARTIFACT_FILENAMES: tuple[str, ...] = (
    ARTIFACT_FILENAME_DATA_STATUS_COUNTS,
    ARTIFACT_FILENAME_EVALUATIONS,
    ARTIFACT_FILENAME_FILTER_SUMMARY,
    ARTIFACT_FILENAME_LABEL_COUNTS,
    ARTIFACT_FILENAME_MANIFEST,
    ARTIFACT_FILENAME_REASON_CODE_COUNTS,
)


# Schema version for the Stage 23 runner-artifact manifest body.
# Distinct from the input/artifact manifests in
# ``stage23_manifest.py`` because the runner artifact manifest
# carries additional fields (counts / filter versions).
STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND: str = "stage23_runner_artifact"


# ---------------------------------------------------------------------------
# Public result shape
# ---------------------------------------------------------------------------


class Stage23ArtifactSet(NamedTuple):
    """Result of one ``write_stage23_artifacts`` invocation.

    Fields:

      * ``output_dir``               -- the operator-supplied
                                        directory the writer
                                        wrote into.
      * ``artifact_paths``           -- frozen mapping
                                        ``basename -> Path`` for
                                        every artifact written.
      * ``artifact_hashes``          -- frozen mapping
                                        ``basename -> sha256 hex``
                                        for every artifact
                                        (including the manifest).
      * ``artifact_row_counts``      -- frozen mapping
                                        ``basename -> row_count``.
                                        ``-1`` for files where row
                                        count is not meaningful
                                        (the manifest itself).
      * ``manifest_path``            -- the manifest file path.
      * ``redaction_confirmed``      -- the redaction confirmation
                                        token the writer set on
                                        the manifest after running
                                        its redaction sweep.
    """

    output_dir: Path
    artifact_paths: Mapping[str, Path]
    artifact_hashes: Mapping[str, str]
    artifact_row_counts: Mapping[str, int]
    manifest_path: Path
    redaction_confirmed: str


# ---------------------------------------------------------------------------
# Output-directory validation
# ---------------------------------------------------------------------------


def _require_output_dir(output_dir: Path) -> None:
    if not isinstance(output_dir, Path):
        raise Stage23ManifestError(
            "write_stage23_artifacts: output_dir must be a pathlib.Path"
        )
    if not output_dir.exists():
        raise Stage23ManifestError(
            "write_stage23_artifacts: output_dir does not exist"
        )
    if not output_dir.is_dir():
        raise Stage23ManifestError(
            "write_stage23_artifacts: output_dir is not a directory"
        )


def _require_created_at_utc(created_at_utc: str) -> None:
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage23ManifestError(
            "write_stage23_artifacts: created_at_utc must be a non-empty "
            "string"
        )


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def _scan_for_redaction(*, text: str, artifact_basename: str) -> None:
    """Raise ``Stage23ManifestError`` if ``text`` carries a forbidden
    URL / webhook-host substring.

    The sweep is a defensive backstop: the Stage 23 input reader
    already rejects forbidden value substrings at ingest, and
    every filter's projection layer constrains its output to
    closed-set numeric values plus controlled identifier strings.
    """
    lower = text.lower()
    for needle in STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if needle in lower:
            raise Stage23ManifestError(
                f"write_stage23_artifacts: artifact "
                f"{artifact_basename!r} carries a forbidden "
                "URL-shape / webhook-host substring"
            )


# ---------------------------------------------------------------------------
# Evaluation -> JSONL row body
# ---------------------------------------------------------------------------


def _evaluation_jsonl_body(
    evaluation: Stage23FilterEvaluation,
) -> dict[str, object]:
    """Build the canonical JSONL row body for one evaluation."""
    filter_input = evaluation.filter_input
    filter_result = evaluation.filter_result
    return {
        "token_mint": filter_input.token_mint,
        "provider_id": filter_input.provider_id,
        "event_id": filter_input.event_id,
        "captured_event_id": filter_input.captured_event_id,
        "observed_at_utc": filter_input.observed_at_utc,
        "slot": filter_input.slot,
        "signature": filter_input.signature,
        "filter_name": filter_result.filter_name,
        "filter_family": filter_result.filter_family,
        "filter_version": filter_result.filter_version,
        "threshold_version": filter_result.threshold_version,
        "label": filter_result.label,
        "data_status": filter_result.data_status,
        "reason_codes": list(filter_result.reason_codes),
        "numeric_features": dict(filter_result.numeric_features),
        "missing_features": list(filter_result.missing_features),
        "input_hash": evaluation.input_hash,
        "evaluation_hash": evaluation.evaluation_hash,
        "created_at_utc": evaluation.created_at_utc,
    }


def _render_evaluations_jsonl(
    runner_result: Stage23RunnerResult,
) -> str:
    """Render the JSONL artifact text.

    The runner's ``evaluations`` is already sorted
    deterministically; we render in that order. An empty input
    set yields the empty string (zero lines).
    """
    lines: list[str] = []
    for evaluation in runner_result.evaluations:
        lines.append(canonical_json(_evaluation_jsonl_body(evaluation)))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Counter helpers
# ---------------------------------------------------------------------------


def _filter_summary_counter(
    runner_result: Stage23RunnerResult,
) -> Counter[tuple[str, str, str, str]]:
    counter: Counter[tuple[str, str, str, str]] = Counter()
    for evaluation in runner_result.evaluations:
        r = evaluation.filter_result
        counter[(r.filter_family, r.filter_name, r.label, r.data_status)] += 1
    return counter


def _reason_code_counter(
    runner_result: Stage23RunnerResult,
) -> Counter[tuple[str, str, str]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for evaluation in runner_result.evaluations:
        r = evaluation.filter_result
        for code in r.reason_codes:
            counter[(r.filter_family, r.filter_name, code)] += 1
    return counter


def _label_counter_per_filter(
    runner_result: Stage23RunnerResult,
) -> Counter[tuple[str, str, str]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for evaluation in runner_result.evaluations:
        r = evaluation.filter_result
        counter[(r.filter_family, r.filter_name, r.label)] += 1
    return counter


def _data_status_counter_per_filter(
    runner_result: Stage23RunnerResult,
) -> Counter[tuple[str, str, str]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for evaluation in runner_result.evaluations:
        r = evaluation.filter_result
        counter[(r.filter_family, r.filter_name, r.data_status)] += 1
    return counter


# ---------------------------------------------------------------------------
# CSV rendering
# ---------------------------------------------------------------------------


# CSV values are restricted to closed-set vocabulary (filter
# families, filter names, labels, data statuses, reason codes)
# plus non-negative integers. None of these vocabularies contains
# a comma, double quote, or newline, so manual rendering is safe
# and avoids the ``csv`` stdlib (which is on the Stage 23
# file-persistence-forbidden allowlist).


def _csv_row(values: tuple[object, ...]) -> str:
    rendered = [str(value) for value in values]
    for value in rendered:
        if "," in value or '"' in value or "\n" in value or "\r" in value:
            raise Stage23ManifestError(
                "write_stage23_artifacts: CSV value carries a delimiter / "
                "quote / newline; vocabulary discipline violated"
            )
    return ",".join(rendered)


def _render_filter_summary_csv(
    runner_result: Stage23RunnerResult,
) -> str:
    counter = _filter_summary_counter(runner_result)
    header = _csv_row(
        ("filter_family", "filter_name", "label", "data_status", "count")
    )
    rows: list[str] = []
    for key in sorted(counter.keys()):
        filter_family, filter_name, label, data_status = key
        rows.append(
            _csv_row(
                (
                    filter_family,
                    filter_name,
                    label,
                    data_status,
                    counter[key],
                )
            )
        )
    body = "\n".join([header, *rows])
    return body + "\n"


def _render_reason_code_counts_csv(
    runner_result: Stage23RunnerResult,
) -> str:
    counter = _reason_code_counter(runner_result)
    header = _csv_row(
        ("filter_family", "filter_name", "reason_code", "count")
    )
    rows: list[str] = []
    for key in sorted(counter.keys()):
        filter_family, filter_name, reason_code = key
        rows.append(
            _csv_row(
                (
                    filter_family,
                    filter_name,
                    reason_code,
                    counter[key],
                )
            )
        )
    body = "\n".join([header, *rows])
    return body + "\n"


def _render_label_counts_csv(
    runner_result: Stage23RunnerResult,
) -> str:
    counter = _label_counter_per_filter(runner_result)
    header = _csv_row(("filter_family", "filter_name", "label", "count"))
    rows: list[str] = []
    for key in sorted(counter.keys()):
        filter_family, filter_name, label = key
        rows.append(
            _csv_row(
                (filter_family, filter_name, label, counter[key])
            )
        )
    body = "\n".join([header, *rows])
    return body + "\n"


def _render_data_status_counts_csv(
    runner_result: Stage23RunnerResult,
) -> str:
    counter = _data_status_counter_per_filter(runner_result)
    header = _csv_row(
        ("filter_family", "filter_name", "data_status", "count")
    )
    rows: list[str] = []
    for key in sorted(counter.keys()):
        filter_family, filter_name, data_status = key
        rows.append(
            _csv_row(
                (filter_family, filter_name, data_status, counter[key])
            )
        )
    body = "\n".join([header, *rows])
    return body + "\n"


# ---------------------------------------------------------------------------
# Manifest body
# ---------------------------------------------------------------------------


def _collect_filter_versions(
    runner_result: Stage23RunnerResult,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (filter_name -> filter_version, filter_name -> threshold_version)
    derived from the runner output.
    """
    filter_versions: dict[str, str] = {}
    threshold_versions: dict[str, str] = {}
    for evaluation in runner_result.evaluations:
        r = evaluation.filter_result
        filter_versions[r.filter_name] = r.filter_version
        threshold_versions[r.filter_name] = r.threshold_version
    return filter_versions, threshold_versions


def _build_manifest_body(
    *,
    runner_result: Stage23RunnerResult,
    created_at_utc: str,
    artifact_hashes: Mapping[str, str],
    artifact_row_counts: Mapping[str, int],
) -> dict[str, object]:
    filter_versions, threshold_versions = _collect_filter_versions(
        runner_result
    )
    artifact_entries: list[dict[str, object]] = []
    for basename in sorted(NON_MANIFEST_ARTIFACT_FILENAMES):
        artifact_entries.append(
            {
                "file_basename": basename,
                "sha256": artifact_hashes[basename],
                "row_count": artifact_row_counts[basename],
            }
        )
    return {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": STAGE23_MANIFEST_SCHEMA_VERSION,
        "manifest_kind": STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "redaction_confirmed": REDACTION_CONFIRMED_TOKEN,
        "created_at_utc": created_at_utc,
        "input_count": runner_result.input_count,
        "evaluation_count": runner_result.evaluation_count,
        "filter_count": runner_result.filter_count,
        "filter_versions": dict(sorted(filter_versions.items())),
        "threshold_versions": dict(sorted(threshold_versions.items())),
        "artifacts": artifact_entries,
        "label_counts": dict(sorted(runner_result.label_counts.items())),
        "data_status_counts": dict(
            sorted(runner_result.data_status_counts.items())
        ),
        "reason_code_counts": dict(
            sorted(runner_result.reason_code_counts.items())
        ),
    }


# ---------------------------------------------------------------------------
# File-write primitives
# ---------------------------------------------------------------------------


def _sha256_hex(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _row_count_for_artifact(*, basename: str, text: str) -> int:
    if basename == ARTIFACT_FILENAME_EVALUATIONS:
        if text == "":
            return 0
        return text.count("\n")
    # CSV artifacts: header counts; data rows = total lines - 1.
    # The manifest itself is not enumerated here.
    if basename.endswith(".csv"):
        if text == "":
            return 0
        # Every CSV body ends with a trailing "\n" so the
        # line count is text.count("\n"). The header occupies
        # one line; the data rows are the remainder.
        return max(0, text.count("\n") - 1)
    return -1


def _write_artifact_text(*, path: Path, text: str) -> None:
    """Write ``text`` to ``path`` using a UTF-8 binary stream so
    every byte that lands on disk is exactly the byte we
    rendered. Explicit ``newline=""`` would not suffice because
    Python's text-mode write maps ``\\n`` to ``\\r\\n`` on
    Windows; binary mode is the only portable way to guarantee
    byte-identical artifacts across platforms.
    """
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Public writer surface
# ---------------------------------------------------------------------------


def write_stage23_artifacts(
    *,
    runner_result: Stage23RunnerResult,
    output_dir: Path,
    created_at_utc: str,
) -> Stage23ArtifactSet:
    """Write the Stage 23 artifact set into ``output_dir``.

    The writer renders each artifact's text in memory, runs a
    redaction sweep over the rendered text, and writes the
    bytes to disk. Every artifact's SHA-256 is computed BEFORE
    write so the manifest body carries the same hashes the
    operator can reconstruct from the rendered text.

    Raises:

      * ``Stage23ManifestError`` if ``output_dir`` is missing /
        not a directory / not a ``pathlib.Path``.
      * ``Stage23ManifestError`` if ``created_at_utc`` is not a
        non-empty string.
      * ``Stage23ManifestError`` if any artifact text carries a
        forbidden URL / webhook-host substring.
      * ``Stage23ManifestError`` if a CSV value carries a comma
        / quote / newline (vocabulary discipline violation).
    """
    _require_output_dir(output_dir)
    _require_created_at_utc(created_at_utc)

    # Render every non-manifest artifact's text first.
    rendered: dict[str, str] = {
        ARTIFACT_FILENAME_EVALUATIONS: _render_evaluations_jsonl(
            runner_result
        ),
        ARTIFACT_FILENAME_FILTER_SUMMARY: _render_filter_summary_csv(
            runner_result
        ),
        ARTIFACT_FILENAME_REASON_CODE_COUNTS: (
            _render_reason_code_counts_csv(runner_result)
        ),
        ARTIFACT_FILENAME_LABEL_COUNTS: _render_label_counts_csv(
            runner_result
        ),
        ARTIFACT_FILENAME_DATA_STATUS_COUNTS: (
            _render_data_status_counts_csv(runner_result)
        ),
    }

    # Redaction sweep BEFORE write -- secret-shaped text never
    # touches disk.
    for basename, text in rendered.items():
        _scan_for_redaction(text=text, artifact_basename=basename)

    # Compute SHA-256 + row count for each rendered artifact.
    artifact_hashes: dict[str, str] = {}
    artifact_row_counts: dict[str, int] = {}
    for basename, text in rendered.items():
        artifact_hashes[basename] = _sha256_hex(text)
        artifact_row_counts[basename] = _row_count_for_artifact(
            basename=basename, text=text
        )

    # Write the rendered artifacts to disk.
    artifact_paths: dict[str, Path] = {}
    for basename, text in rendered.items():
        path = output_dir / basename
        _write_artifact_text(path=path, text=text)
        artifact_paths[basename] = path

    # Build + redaction-sweep + write the manifest.
    manifest_body = _build_manifest_body(
        runner_result=runner_result,
        created_at_utc=created_at_utc,
        artifact_hashes=artifact_hashes,
        artifact_row_counts=artifact_row_counts,
    )
    manifest_text = canonical_json(manifest_body) + "\n"
    _scan_for_redaction(
        text=manifest_text,
        artifact_basename=ARTIFACT_FILENAME_MANIFEST,
    )
    manifest_path = output_dir / ARTIFACT_FILENAME_MANIFEST
    _write_artifact_text(path=manifest_path, text=manifest_text)
    artifact_paths[ARTIFACT_FILENAME_MANIFEST] = manifest_path
    artifact_hashes[ARTIFACT_FILENAME_MANIFEST] = _sha256_hex(manifest_text)
    artifact_row_counts[ARTIFACT_FILENAME_MANIFEST] = -1

    return Stage23ArtifactSet(
        output_dir=output_dir,
        artifact_paths=MappingProxyType(
            {key: artifact_paths[key] for key in sorted(artifact_paths)}
        ),
        artifact_hashes=MappingProxyType(
            {key: artifact_hashes[key] for key in sorted(artifact_hashes)}
        ),
        artifact_row_counts=MappingProxyType(
            {
                key: artifact_row_counts[key]
                for key in sorted(artifact_row_counts)
            }
        ),
        manifest_path=manifest_path,
        redaction_confirmed=REDACTION_CONFIRMED_TOKEN,
    )


__all__ = [
    "ALL_ARTIFACT_FILENAMES",
    "ARTIFACT_FILENAME_DATA_STATUS_COUNTS",
    "ARTIFACT_FILENAME_EVALUATIONS",
    "ARTIFACT_FILENAME_FILTER_SUMMARY",
    "ARTIFACT_FILENAME_LABEL_COUNTS",
    "ARTIFACT_FILENAME_MANIFEST",
    "ARTIFACT_FILENAME_REASON_CODE_COUNTS",
    "NON_MANIFEST_ARTIFACT_FILENAMES",
    "STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND",
    "Stage23ArtifactSet",
    "write_stage23_artifacts",
]
