"""Stage 19 manifest assembly + atomic write + run_id derivation.

The Stage 19 run id is the first 16 hex chars of SHA-256 over a
canonical JSON dict of seven fields:

    operator_id
    operator_input_sha256
    prior_ledger_sha256 (or null)
    run_timestamp_utc
    stage18_input_basename
    stage18_run_id
    stage19_schema_version

``stage18_input_basename`` (not the absolute path) is the input
to the run-id hash so two checkouts of the repo on different
machines / in different working directories can produce
identical run ids when the upstream Stage 18 run is the same.

Atomic write pattern: write to ``<path>.tmp``, then
``os.replace`` onto the final name. If the OS write fails the
``.tmp`` sibling is removed before the exception propagates.

This module imports ``get_git_commit`` from ``PHX2.stage19._git``
for the manifest's ``git_commit`` field but does not import
``subprocess`` directly.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from PHX2.stage19.constants import (
    LABELS,
    STAGE19_SCHEMA_VERSION,
    STAGE19_VERSION,
)


_HASH_CHUNK_SIZE: int = 65536  # 64 KiB streaming reads for compute_file_sha256


def compute_stage19_run_id(
    *,
    stage18_run_id: str,
    stage18_input_basename: str,
    operator_id: str,
    operator_input_sha256: str,
    prior_ledger_sha256: Optional[str],
    run_timestamp_utc: str,
    stage19_schema_version: str,
) -> str:
    """Derive the 16-hex-char Stage 19 run id from the canonical
    input set.

    Pure function of its keyword arguments. Two invocations with
    identical arguments return the same id; any change to any
    argument changes the id.
    """

    payload = {
        "operator_id": operator_id,
        "operator_input_sha256": operator_input_sha256,
        "prior_ledger_sha256": prior_ledger_sha256,
        "run_timestamp_utc": run_timestamp_utc,
        "stage18_input_basename": stage18_input_basename,
        "stage18_run_id": stage18_run_id,
        "stage19_schema_version": stage19_schema_version,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def compute_file_sha256(path: Path) -> str:
    """Return the 64-hex lowercase SHA-256 digest of the file at
    ``path``.

    Streams the file in 64 KiB chunks rather than loading the
    whole file into memory.
    """

    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    *,
    stage19_run_id: str,
    run_timestamp_utc: str,
    operator_id: str,
    stage18_input_dir: Path,
    stage18_run_id: str,
    stage18_manifest_sha256: str,
    stage18_review_matrix_sha256: str,
    operator_input_path: Path,
    operator_input_sha256: str,
    prior_ledger_dir: Optional[Path],
    prior_ledger_sha256: Optional[str],
    prior_ledger_schema_version: Optional[str],
    new_row_count: int,
    prior_row_count: int,
    total_ledger_row_count: int,
    label_counts: dict[str, int],
    git_commit: str,
) -> dict[str, Any]:
    """Assemble the Stage 19 manifest dict (does not write it).

    ``label_counts`` is reconstructed in LABELS-locked order from
    the caller-supplied per-label counts so the manifest is
    deterministic regardless of how the caller built the dict.
    Missing labels default to 0.

    Path-typed inputs are resolved to absolute strings.
    """

    ordered_label_counts: dict[str, int] = {}
    for label in LABELS:
        ordered_label_counts[label] = int(label_counts.get(label, 0))

    return {
        "stage19_schema_version": STAGE19_SCHEMA_VERSION,
        "stage19_version": STAGE19_VERSION,
        "stage19_run_id": stage19_run_id,
        "run_timestamp_utc": run_timestamp_utc,
        "operator_id": operator_id,
        "stage18_input_dir": str(Path(stage18_input_dir).resolve()),
        "stage18_input_basename": Path(stage18_input_dir).name,
        "stage18_run_id": stage18_run_id,
        "stage18_manifest_sha256": stage18_manifest_sha256,
        "stage18_review_matrix_sha256": stage18_review_matrix_sha256,
        "operator_input_path": str(Path(operator_input_path).resolve()),
        "operator_input_sha256": operator_input_sha256,
        "prior_ledger_dir": (
            str(Path(prior_ledger_dir).resolve())
            if prior_ledger_dir is not None
            else None
        ),
        "prior_ledger_sha256": prior_ledger_sha256,
        "prior_ledger_schema_version": prior_ledger_schema_version,
        "new_row_count": int(new_row_count),
        "prior_row_count": int(prior_row_count),
        "total_ledger_row_count": int(total_ledger_row_count),
        "label_counts": ordered_label_counts,
        "git_commit": git_commit,
    }


def write_manifest_json(path: Path, manifest: dict) -> None:
    """Atomically write the Stage 19 manifest JSON.

    Serialization: ``sort_keys=True``, compact separators, UTF-8
    without ASCII escaping, so the byte sequence is independent
    of dict insertion order.

    Atomic write: write to ``<path>.tmp`` then ``os.replace``
    onto the final name. The temp file is removed on OSError to
    avoid leaving residue at the parent path.
    """

    payload = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8", newline="")
        os.replace(tmp, path)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


__all__ = [
    "build_manifest",
    "compute_file_sha256",
    "compute_stage19_run_id",
    "write_manifest_json",
]
