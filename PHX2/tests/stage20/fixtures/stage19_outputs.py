"""Synthetic Stage 19 output fixtures for Stage 20 tests.

These helpers hand-write minimal contract-valid Stage 19 run
directories used by Stage 20.1.B+ tests. They:

  * Do NOT import PHX2.stage19 -- the import-boundary policy
    applies to fixtures too.
  * Do NOT import PHX2.stage20.constants -- the column tuple,
    schema_version literal, hash-field key names, and label
    vocabulary are duplicated locally so a typo in
    PHX2.stage20.constants is caught by these tests rather than
    silently mirrored.

The Stage 19 manifest is the authoritative source of Stage 18
input hashes (per the Stage 19 build_manifest contract). These
fixtures compute SHA-256 over the on-disk Stage 18 files and
stamp the resulting hashes into the Stage 19 manifest before
writing it. That mirrors how a real Stage 19 run records the
upstream hashes, so Stage 20's ``verify_input_hashes`` exercise
is end-to-end.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


_STAGE19_SCHEMA_VERSION: str = "stage19_ledger_v1"


_STAGE19_LEDGER_COLUMNS: tuple[str, ...] = (
    "stage19_run_id",
    "ledger_row_id",
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "review_sequence",
    "review_label",
    "review_notes",
    "review_timestamp_utc",
    "stage18_classification",
    "stage17_label_preserved",
)


_DEFAULT_STAGE19_RUN_ID: str = "1234567890abcdef"
_DEFAULT_STAGE18_RUN_ID: str = "deadbeefcafebabe"
_DEFAULT_OPERATOR_ID: str = "operator_alice"
_DEFAULT_RUN_TIMESTAMP: str = "2026-05-13T00:00:00Z"

_ZERO_HASH: str = "0" * 64


def _file_sha256(path: Path) -> str:
    """Return the 64-hex SHA-256 digest of ``path``."""

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_minimal_stage19_dir(
    target_dir: Path,
    *,
    stage18_dir: Path,
    stage19_run_id: str = _DEFAULT_STAGE19_RUN_ID,
    stage18_run_id: str = _DEFAULT_STAGE18_RUN_ID,
    operator_id: str = _DEFAULT_OPERATOR_ID,
    run_timestamp_utc: str = _DEFAULT_RUN_TIMESTAMP,
    extra_ledger_rows: Sequence[Sequence[str]] = (),
) -> Path:
    """Write a minimal contract-valid Stage 19 output directory.

    ``stage18_dir`` is an existing on-disk Stage 18 run dir whose
    manifest.json and review_matrix.csv are hashed and stamped
    into Stage 19's manifest before write. This mirrors how a
    real Stage 19 run captures upstream hashes.
    """

    target_dir.mkdir(parents=True, exist_ok=True)

    stage18_manifest_sha256 = _file_sha256(stage18_dir / "manifest.json")
    stage18_review_matrix_sha256 = _file_sha256(stage18_dir / "review_matrix.csv")

    rows: list[Sequence[str]] = [
        make_ledger_row(
            stage19_run_id=stage19_run_id,
            stage18_run_id=stage18_run_id,
            operator_id=operator_id,
            run_timestamp_utc=run_timestamp_utc,
        )
    ]
    rows.extend(extra_ledger_rows)
    write_ledger(target_dir / "operator_review_ledger.csv", rows)

    write_stage19_manifest(
        target_dir / "manifest.json",
        stage19_run_id=stage19_run_id,
        stage18_run_id=stage18_run_id,
        operator_id=operator_id,
        run_timestamp_utc=run_timestamp_utc,
        stage18_input_dir=str(stage18_dir.resolve()),
        stage18_manifest_sha256=stage18_manifest_sha256,
        stage18_review_matrix_sha256=stage18_review_matrix_sha256,
    )
    return target_dir


def write_stage19_manifest(
    path: Path,
    *,
    stage19_run_id: str = _DEFAULT_STAGE19_RUN_ID,
    stage18_run_id: str = _DEFAULT_STAGE18_RUN_ID,
    operator_id: str = _DEFAULT_OPERATOR_ID,
    run_timestamp_utc: str = _DEFAULT_RUN_TIMESTAMP,
    stage18_input_dir: str = "/tmp/stage18_run",
    stage18_manifest_sha256: str = _ZERO_HASH,
    stage18_review_matrix_sha256: str = _ZERO_HASH,
    schema_version: str = _STAGE19_SCHEMA_VERSION,
    extra: Mapping[str, object] = {},
) -> None:
    """Write a Stage 19-shaped manifest.json at ``path``."""

    payload: dict[str, object] = {
        "stage19_schema_version": schema_version,
        "stage19_version": "0.1.0",
        "stage19_run_id": stage19_run_id,
        "run_timestamp_utc": run_timestamp_utc,
        "operator_id": operator_id,
        "stage18_input_dir": stage18_input_dir,
        "stage18_input_basename": Path(stage18_input_dir).name,
        "stage18_run_id": stage18_run_id,
        "stage18_manifest_sha256": stage18_manifest_sha256,
        "stage18_review_matrix_sha256": stage18_review_matrix_sha256,
        "operator_input_path": "/tmp/operator_review_input.csv",
        "operator_input_sha256": _ZERO_HASH,
        "prior_ledger_dir": None,
        "prior_ledger_sha256": None,
        "prior_ledger_schema_version": None,
        "new_row_count": 1,
        "prior_row_count": 0,
        "total_ledger_row_count": 1,
        "label_counts": {
            "REVIEW_PROMISING_CONFIRMED": 1,
            "REVIEW_HARMFUL_CONFIRMED": 0,
            "REVIEW_REJECTED": 0,
            "WATCHLIST": 0,
            "NEEDS_MORE_DATA": 0,
            "INCONCLUSIVE": 0,
        },
        "git_commit": "unknown",
    }
    if extra:
        payload.update(extra)
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    path.write_text(text, encoding="utf-8", newline="")


def write_ledger(
    path: Path,
    rows: Sequence[Sequence[str]],
    *,
    columns: Sequence[str] = _STAGE19_LEDGER_COLUMNS,
) -> None:
    """Write a Stage 19 operator_review_ledger.csv at ``path``.

    ``columns`` defaults to the locked 13-column tuple but accepts
    a caller-supplied alternative for E2009 header-shape negative
    tests.
    """

    parts = [",".join(columns)]
    for row in rows:
        parts.append(",".join(str(c) for c in row))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def make_ledger_row(
    *,
    stage19_run_id: str = _DEFAULT_STAGE19_RUN_ID,
    ledger_row_id: str = "abcdef0123456789",
    stage18_run_id: str = _DEFAULT_STAGE18_RUN_ID,
    policy_hash: str = "abc123def456",
    rule_id: str = "rule_minimal",
    window_seconds: str = "3600",
    operator_id: str = _DEFAULT_OPERATOR_ID,
    review_sequence: str = "1",
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "",
    run_timestamp_utc: str = _DEFAULT_RUN_TIMESTAMP,
    stage18_classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
) -> tuple[str, ...]:
    """Build one Stage 19 ledger row matching the locked 13-column schema."""

    return (
        stage19_run_id,
        ledger_row_id,
        stage18_run_id,
        policy_hash,
        rule_id,
        window_seconds,
        operator_id,
        review_sequence,
        review_label,
        review_notes,
        run_timestamp_utc,
        stage18_classification,
        stage17_label_preserved,
    )


__all__ = [
    "make_ledger_row",
    "write_ledger",
    "write_minimal_stage19_dir",
    "write_stage19_manifest",
]
