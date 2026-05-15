"""Synthetic Stage 18 output fixtures for Stage 20 tests.

These helpers hand-write minimal contract-valid Stage 18 run
directories used by Stage 20.1.B+ tests. They:

  * Do NOT import PHX2.stage18 -- the import-boundary policy
    applies to fixtures too.
  * Do NOT import PHX2.stage20.constants -- the column tuple and
    schema-version literals are duplicated locally so a typo in
    PHX2.stage20.constants is caught by these tests rather than
    silently mirrored.

A second independent source-of-truth for the same column tuple
lives in PHX2/tests/stage19/fixtures/stage18_outputs.py.
Duplication is intentional.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


_STAGE18_MANIFEST_SCHEMA_VERSION: str = "stage18_run_manifest_v0"


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


_DEFAULT_RUN_ID: str = "deadbeefcafebabe"
_DEFAULT_POLICY_HASH: str = "abc123def456"
_DEFAULT_RULE_ID: str = "rule_minimal"
_DEFAULT_WINDOW_SECONDS: str = "3600"
_DEFAULT_WINDOW_LABEL: str = "1h"


def write_minimal_stage18_dir(
    target_dir: Path,
    *,
    run_id: str = _DEFAULT_RUN_ID,
    extra_review_rows: Sequence[Sequence[str]] = (),
) -> Path:
    """Write a minimal contract-valid Stage 18 output directory.

    Produces:
      * ``manifest.json``     -- Stage 18 manifest with locked
                                  schema_version + flat run_id.
      * ``review_matrix.csv`` -- locked 17-column header plus one
                                  ``PROMISING_REVIEW`` default row
                                  plus ``extra_review_rows``.

    Returns ``target_dir`` for chaining convenience.
    """

    target_dir.mkdir(parents=True, exist_ok=True)
    write_stage18_manifest(target_dir / "manifest.json", run_id=run_id)
    rows: list[Sequence[str]] = [make_review_row()]
    rows.extend(extra_review_rows)
    write_review_matrix(target_dir / "review_matrix.csv", rows)
    return target_dir


def write_stage18_manifest(
    path: Path,
    *,
    run_id: str = _DEFAULT_RUN_ID,
    schema_version: str = _STAGE18_MANIFEST_SCHEMA_VERSION,
    extra: Mapping[str, object] = {},
) -> None:
    """Write a Stage 18-shaped manifest.json at ``path``."""

    payload: dict[str, object] = {
        "schema_version": schema_version,
        "stage18_version": "stage18_review_v0_observe_only",
        "run_id": run_id,
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
    if extra:
        payload.update(extra)
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
    """Write a Stage 18 review_matrix.csv at ``path``.

    ``columns`` defaults to the locked 17-column tuple but accepts
    a caller-supplied alternative for E2008 header-shape negative
    tests.
    """

    parts = [",".join(columns)]
    for row in rows:
        parts.append(",".join(row))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def make_review_row(
    *,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    rule_id: str = _DEFAULT_RULE_ID,
    window_seconds: str = _DEFAULT_WINDOW_SECONDS,
    window_label: str = _DEFAULT_WINDOW_LABEL,
    classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
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
    """Build one review_matrix row matching the locked 17-column schema."""

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


__all__ = [
    "make_review_row",
    "write_minimal_stage18_dir",
    "write_review_matrix",
    "write_stage18_manifest",
]
