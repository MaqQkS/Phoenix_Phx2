"""Synthetic Stage 18 + Stage 19 fixture factory for Stage 20.2 tests.

Produces on-disk synthetic files (manifests + CSVs) that satisfy
``validate_inputs``' expectations under the locked Stage 18 / Stage
19 schemas. NO real Stage 18/19 production data is used here and
NO Stage 18/19 imports are made -- the upstream column tuples and
key names are pulled exclusively from ``PHX2.stage20.constants``
(the hand-duplicated source of truth for Stage 20).

The factory exposes three convenience builders:

  * ``make_review_matrix_row(...)``  -- one Stage 18
    review_matrix.csv row dict with every locked column filled.
  * ``make_ledger_row(...)``         -- one Stage 19 ledger row.
  * ``make_minimal_valid_inputs(base_dir, ...)`` -- writes a full
    Stage 18 + Stage 19 file set under ``base_dir`` and returns
    the four resulting paths.

All bytes are deterministic for a given parameter set: CSVs use
QUOTE_MINIMAL, "\\n" line endings, no BOM; JSON manifests use
sort_keys=True, compact separators, UTF-8 no BOM.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from PHX2.stage20.constants import (
    STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION,
    STAGE18_MANIFEST_FILENAME,
    STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
    STAGE18_REVIEW_MATRIX_FILENAME,
    STAGE19_EXPECTED_MANIFEST_SCHEMA_VERSION,
    STAGE19_LEDGER_EXPECTED_COLUMNS,
    STAGE19_LEDGER_FILENAME,
    STAGE19_MANIFEST_FILENAME,
)


_HASH_CHUNK_SIZE = 65536


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _write_csv(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        writer.writerow(list(header))
        for row in rows:
            writer.writerow([str(row.get(col, "")) for col in header])


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    payload = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ) + "\n"
    path.write_bytes(payload.encode("utf-8"))


def make_review_matrix_row(
    *,
    policy_hash: str = "ph_a",
    rule_id: str = "rule_a",
    window_seconds: str = "30",
    window_label: str = "WIN_30S",
    classification: str = "CLASS_A",
    stage17_label_preserved: str = "LABEL_A",
    insufficient_sample_reason: str = "",
    data_block_reason: str = "",
    gate_trips_all: str = "false",
    n_in_scope: str = "10",
    n_matched: str = "5",
    n_not_matched: str = "5",
    n_with_complete_outcome: str = "5",
    delta_hit_2x_rate: str = "0.10",
    unevaluable_rate: str = "0.00",
    incomplete_outcome_ratio: str = "0.00",
    tier_coverage: str = "1.0",
) -> dict[str, str]:
    return {
        "policy_hash": policy_hash,
        "rule_id": rule_id,
        "window_seconds": window_seconds,
        "window_label": window_label,
        "classification": classification,
        "stage17_label_preserved": stage17_label_preserved,
        "insufficient_sample_reason": insufficient_sample_reason,
        "data_block_reason": data_block_reason,
        "gate_trips_all": gate_trips_all,
        "n_in_scope": n_in_scope,
        "n_matched": n_matched,
        "n_not_matched": n_not_matched,
        "n_with_complete_outcome": n_with_complete_outcome,
        "delta_hit_2x_rate": delta_hit_2x_rate,
        "unevaluable_rate": unevaluable_rate,
        "incomplete_outcome_ratio": incomplete_outcome_ratio,
        "tier_coverage": tier_coverage,
    }


def make_ledger_row(
    *,
    stage19_run_id: str = "s19_run_a",
    ledger_row_id: str = "lrid_a",
    stage18_run_id: str = "s18_run_a",
    policy_hash: str = "ph_a",
    rule_id: str = "rule_a",
    window_seconds: str = "30",
    operator_id: str = "op_a",
    review_sequence: str = "1",
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "",
    review_timestamp_utc: str = "2026-05-15T00:00:00Z",
    stage18_classification: str = "CLASS_A",
    stage17_label_preserved: str = "LABEL_A",
) -> dict[str, str]:
    return {
        "stage19_run_id": stage19_run_id,
        "ledger_row_id": ledger_row_id,
        "stage18_run_id": stage18_run_id,
        "policy_hash": policy_hash,
        "rule_id": rule_id,
        "window_seconds": window_seconds,
        "operator_id": operator_id,
        "review_sequence": review_sequence,
        "review_label": review_label,
        "review_notes": review_notes,
        "review_timestamp_utc": review_timestamp_utc,
        "stage18_classification": stage18_classification,
        "stage17_label_preserved": stage17_label_preserved,
    }


def make_stage18_files(
    stage18_dir: Path,
    review_matrix_rows: Sequence[Mapping[str, str]],
    *,
    run_id: str = "s18_run_a",
) -> tuple[Path, Path]:
    """Write Stage 18 manifest.json + review_matrix.csv to ``stage18_dir``.

    Returns (manifest_path, review_matrix_path).
    """

    stage18_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = stage18_dir / STAGE18_MANIFEST_FILENAME
    rm_path = stage18_dir / STAGE18_REVIEW_MATRIX_FILENAME
    _write_csv(
        rm_path,
        STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
        review_matrix_rows,
    )
    # Stage 18 manifest stores its run id under the un-namespaced
    # "run_id" key per Stage 18's published convention.
    _write_json(manifest_path, {
        "schema_version": STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION,
        "stage18_version": "test",
        "run_id": run_id,
        "run_started_utc": "2026-05-15T00:00:00Z",
        "run_finished_utc": "2026-05-15T00:00:00Z",
        "git_commit": "0" * 40,
    })
    return manifest_path, rm_path


def make_stage19_files(
    stage19_dir: Path,
    ledger_rows: Sequence[Mapping[str, str]],
    stage18_manifest_path: Path,
    stage18_review_matrix_path: Path,
    *,
    stage18_run_id: str = "s18_run_a",
    stage19_run_id: str = "s19_run_a",
    override_stage18_manifest_sha256: str | None = None,
    override_stage18_review_matrix_sha256: str | None = None,
) -> tuple[Path, Path]:
    """Write Stage 19 manifest.json + operator_review_ledger.csv.

    By default the manifest's recorded SHA-256s are computed from
    the freshly written Stage 18 files (clean run). Override the
    declared SHA-256s to synthesize an E2003 condition.

    Returns (manifest_path, ledger_path).
    """

    stage19_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = stage19_dir / STAGE19_LEDGER_FILENAME
    manifest_path = stage19_dir / STAGE19_MANIFEST_FILENAME
    _write_csv(ledger_path, STAGE19_LEDGER_EXPECTED_COLUMNS, ledger_rows)

    s18_manifest_sha = (
        override_stage18_manifest_sha256
        if override_stage18_manifest_sha256 is not None
        else _file_sha256(stage18_manifest_path)
    )
    s18_rm_sha = (
        override_stage18_review_matrix_sha256
        if override_stage18_review_matrix_sha256 is not None
        else _file_sha256(stage18_review_matrix_path)
    )

    _write_json(manifest_path, {
        "schema_version": STAGE19_EXPECTED_MANIFEST_SCHEMA_VERSION,
        "stage19_version": "test",
        "stage19_run_id": stage19_run_id,
        "stage18_run_id": stage18_run_id,
        "stage18_manifest_sha256": s18_manifest_sha,
        "stage18_review_matrix_sha256": s18_rm_sha,
        "git_commit": "0" * 40,
    })
    return manifest_path, ledger_path


def make_minimal_valid_inputs(
    base_dir: Path,
    *,
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_timestamp_utc: str = "2026-05-15T00:00:00Z",
    stage18_run_id: str = "s18_run_a",
    stage19_run_id: str = "s19_run_a",
) -> dict[str, Path]:
    """Build the smallest validate_inputs-clean fixture.

    1 review_matrix row + 1 ledger row whose slice key joins to it.

    Returns a dict with the 4 input paths under keys:
      stage18_manifest_path, stage18_review_matrix_path,
      stage19_manifest_path, stage19_ledger_path.
    """

    stage18_dir = base_dir / "stage18"
    stage19_dir = base_dir / "stage19"

    rm_rows = [make_review_matrix_row()]
    s18_manifest, s18_rm = make_stage18_files(
        stage18_dir, rm_rows, run_id=stage18_run_id,
    )

    ledger_rows = [make_ledger_row(
        stage18_run_id=stage18_run_id,
        stage19_run_id=stage19_run_id,
        review_label=review_label,
        review_timestamp_utc=review_timestamp_utc,
    )]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
        stage18_run_id=stage18_run_id,
        stage19_run_id=stage19_run_id,
    )

    return {
        "stage18_manifest_path": s18_manifest,
        "stage18_review_matrix_path": s18_rm,
        "stage19_manifest_path": s19_manifest,
        "stage19_ledger_path": s19_ledger,
    }


__all__ = [
    "make_ledger_row",
    "make_minimal_valid_inputs",
    "make_review_matrix_row",
    "make_stage18_files",
    "make_stage19_files",
]
