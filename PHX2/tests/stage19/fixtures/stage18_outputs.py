"""Helpers that write Stage 18 output directories used by Stage 19 tests.

The helpers in this module write byte-faithful Stage 18 output
files into a caller-supplied directory. They are used by Stage 19
reader, validator, and contract tests (Phase 19.2 onward) to
construct a minimal valid Stage 18 packet and to mutate specific
files for negative-path tests.

These helpers do **not** import ``PHX2.stage18`` and they
intentionally do not import from ``PHX2.stage19.constants``
either: the column tuples and key names are duplicated locally so
a typo in ``PHX2.stage19.constants`` is caught by these tests
rather than silently mirrored. Test fixtures are an independent
source of truth for the Stage 18 contract Stage 19 must accept.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Locked Stage 18 contract values (independently duplicated here so
# this module is a second source of truth)
# ---------------------------------------------------------------------------


_STAGE18_MANIFEST_SCHEMA_VERSION: str = "stage18_run_manifest_v0"
_STAGE18_MANIFEST_RUN_ID_KEY: str = "run_id"


_STAGE18_REVIEW_MATRIX_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "window_label",
    "classification",
    "stage17_label_preserved",
    "insufficient_sample_reason",
    "data_block_reason",
    "gate_trips_all",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_with_complete_outcome",
    "delta_hit_2x_rate",
    "unevaluable_rate",
    "incomplete_outcome_ratio",
    "tier_coverage",
)


_DEFAULT_RUN_ID: str = "0123456789abcdef"
_DEFAULT_POLICY_HASH: str = "abc123def456"
_DEFAULT_RULE_ID: str = "rule_minimal"
_DEFAULT_WINDOW_SECONDS: str = "3600"
_DEFAULT_WINDOW_LABEL: str = "1h"


# ---------------------------------------------------------------------------
# Public helpers -- valid packets
# ---------------------------------------------------------------------------


def write_minimal_valid_stage18_output(
    target_dir: Path,
    *,
    run_id: str = _DEFAULT_RUN_ID,
    extra_review_rows: Sequence[Sequence[str]] = (),
) -> Path:
    """Write a minimal but contract-valid Stage 18 output directory.

    Produces:
      * ``manifest.json``      -- valid Stage 18 manifest (schema
                                  version + flat ``run_id`` field).
      * ``review_matrix.csv``  -- locked 17-column header plus one
                                  ``HARMFUL_REVIEW`` data row, plus
                                  any rows passed via
                                  ``extra_review_rows``.

    Returns ``target_dir`` for chaining convenience.
    """

    target_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(target_dir / "manifest.json", run_id=run_id)
    rows: list[Sequence[str]] = [_minimal_review_row()]
    rows.extend(extra_review_rows)
    write_review_matrix(target_dir / "review_matrix.csv", rows)
    return target_dir


def write_manifest(
    path: Path,
    *,
    run_id: str = _DEFAULT_RUN_ID,
    schema_version: str = _STAGE18_MANIFEST_SCHEMA_VERSION,
    extra_fields: Mapping[str, object] = {},
    omit_run_id: bool = False,
    raw_text: str | None = None,
) -> None:
    """Write a Stage 18-shaped manifest.

    ``schema_version`` defaults to the current accepted version;
    callers exercising E05 (schema mismatch) override it.
    ``omit_run_id`` produces a manifest with no ``run_id`` field
    (E04 trigger -- malformed/missing required key).
    ``raw_text`` short-circuits all serialization and writes the
    supplied bytes verbatim (E04 trigger for invalid-JSON cases).
    """

    if raw_text is not None:
        path.write_text(raw_text, encoding="utf-8", newline="")
        return

    payload: dict[str, object] = {
        "schema_version": schema_version,
        "stage18_version": "stage18_review_v0_observe_only",
        "run_started_utc": "2026-05-13T00:00:00+00:00",
        "run_finished_utc": "2026-05-13T00:00:01+00:00",
        "stage17_input_dir": "/tmp/stage17_run",
        "output_dir": "/tmp/stage18_run",
        "gates": {},
        "stage17_manifest": {},
        "input_row_counts": {},
        "output_row_counts": {},
        "classification_counts": {},
        "policy_hash_filter": [],
        "git_commit": "unknown",
    }
    if not omit_run_id:
        payload[_STAGE18_MANIFEST_RUN_ID_KEY] = run_id
    payload.update(extra_fields)
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    path.write_text(text, encoding="utf-8", newline="")


def write_review_matrix(
    path: Path,
    rows: Sequence[Sequence[str]],
    *,
    columns: Sequence[str] = _STAGE18_REVIEW_MATRIX_COLUMNS,
) -> None:
    """Write a Stage 18 review_matrix.csv with the locked 17-column
    header (or a caller-supplied alternative for E20 header
    negatives) and the supplied data rows (which may be malformed
    to trigger E21 row negatives)."""

    _write_csv(path, columns, rows)


def write_review_matrix_with_header(
    path: Path, header: Sequence[str]
) -> None:
    """Write a header-only review_matrix.csv (used for E20
    header-shape negatives)."""

    line = ",".join(header) + "\n"
    path.write_text(line, encoding="utf-8", newline="")


def make_review_row(
    *,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    rule_id: str = _DEFAULT_RULE_ID,
    window_seconds: str = _DEFAULT_WINDOW_SECONDS,
    window_label: str = _DEFAULT_WINDOW_LABEL,
    classification: str = "HARMFUL_REVIEW",
    stage17_label_preserved: str = "HARMFUL",
    insufficient_sample_reason: str = "",
    data_block_reason: str = "",
    gate_trips_all: str = "",
    n_in_scope: str = "100",
    n_matched: str = "40",
    n_not_matched: str = "60",
    n_with_complete_outcome: str = "100",
    delta_hit_2x_rate: str = "0.100000",
    unevaluable_rate: str = "0.000000",
    incomplete_outcome_ratio: str = "0.000000",
    tier_coverage: str = "single_tier_only",
) -> tuple[str, ...]:
    """Build a single review_matrix row matching the locked 17-column
    schema. Each kwarg defaults to a value that produces a
    contract-valid HARMFUL_REVIEW slice; tests override specific
    cells to trigger negative paths."""

    return (
        policy_hash,
        rule_id,
        window_seconds,
        window_label,
        classification,
        stage17_label_preserved,
        insufficient_sample_reason,
        data_block_reason,
        gate_trips_all,
        n_in_scope,
        n_matched,
        n_not_matched,
        n_with_complete_outcome,
        delta_hit_2x_rate,
        unevaluable_rate,
        incomplete_outcome_ratio,
        tier_coverage,
    )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _minimal_review_row() -> tuple[str, ...]:
    return make_review_row()


def _write_csv(
    path: Path, columns: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    """Hand-write a CSV using Stage 18's conventions (LF, trailing LF)."""

    parts = [",".join(columns)]
    for row in rows:
        parts.append(",".join(row))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


__all__ = [
    "make_review_row",
    "write_manifest",
    "write_minimal_valid_stage18_output",
    "write_review_matrix",
    "write_review_matrix_with_header",
]
