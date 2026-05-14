"""Stage 17 manifest assembly + atomic write.

The manifest is the only run-level summary written by Stage 17 that
captures enough state to reproduce the run later: it pins the git
commit, the DB-side row counts, the MIN_N value, the analyzed
policy_hashes, and the per-CSV output row counts.

Determinism contract: two runs against an unchanged DB produce
identical manifests AFTER zeroing the run-specific fields
``run_id``, ``run_started_utc``, ``run_finished_utc``, ``db_path``,
``output_dir`` (the determinism test asserts this exact set).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from PHX2.stage17.errors import Stage17Error


SCHEMA_VERSION = "stage17_run_manifest_v0"


def compute_run_id(
    *,
    db_basename: str,
    min_n: int,
    policy_hashes: Sequence[str],
    source_table_row_counts: Mapping[str, int],
) -> str:
    """Derive a 16-hex-char run id from the canonical input set.

    Uses path basename only (not absolute path) so two checkouts of
    the same DB on different machines produce the same run_id.
    """

    canonical = json.dumps(
        {
            "db_basename": db_basename,
            "min_n": int(min_n),
            "policy_hashes": list(policy_hashes),
            "source_table_row_counts": dict(source_table_row_counts),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def build_manifest(
    *,
    run_id: str,
    run_started_utc: str,
    run_finished_utc: str,
    db_path: str,
    output_dir: str,
    min_n_active: int,
    policy_hashes_analyzed: Sequence[str],
    git_commit: str,
    source_table_row_counts: Mapping[str, int],
    output_row_counts: Mapping[str, int],
    schema_migrations_seen: Sequence[str],
    orphan_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Build the manifest dictionary (does not write it)."""

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_started_utc": run_started_utc,
        "run_finished_utc": run_finished_utc,
        "db_path": db_path,
        "output_dir": output_dir,
        "min_n_active": int(min_n_active),
        "policy_hashes_analyzed": list(policy_hashes_analyzed),
        "git_commit": git_commit,
        "source_table_row_counts": dict(source_table_row_counts),
        "output_row_counts": dict(output_row_counts),
        "schema_migrations_seen": list(schema_migrations_seen),
        "orphan_counts": dict(orphan_counts),
    }


def write_manifest(manifest: Mapping[str, Any], output_path: Path) -> None:
    """Atomically write the manifest JSON.

    The serialization is ``sort_keys=True``, compact, UTF-8 without
    ASCII escaping so the byte sequence is independent of dict
    insertion order. The atomic-write pattern mirrors the CSV / log
    writers (``.tmp`` sibling + ``os.replace``).
    """

    payload = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    tmp = output_path.with_name(output_path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8", newline="")
        os.replace(tmp, output_path)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise Stage17Error(
            "A05", f"{output_path.name}: {exc}"
        ) from exc


__all__ = [
    "SCHEMA_VERSION",
    "build_manifest",
    "compute_run_id",
    "write_manifest",
]
