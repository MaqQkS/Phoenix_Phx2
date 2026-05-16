"""Stage 20.3 artifact writers.

Five artifacts in one module (locked):
  * filter_interface_registry.csv   -- headers + N FilterDefinition rows
                                       (N = 0 in v0)
  * filter_interface_results.csv    -- headers + N FilterEvaluationRow rows
                                       (N = 0 in v0)
  * stage20_3_run.log               -- JSON Lines (matches 20.2)
  * README.md                       -- static template w/ deterministic
                                       lineage substitution
  * stage20_3_manifest.json         -- locked JSON serialization
                                       (sort_keys=True,
                                        separators=(",", ":"),
                                        ensure_ascii=False, "\\n")

Encoding contract (locked, mirrors Stage 20.2):
  * UTF-8 only. No BOM. Line endings "\\n" everywhere.
  * CSV: csv.writer(f, quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\\n"). Header always written
    even with zero data rows.
  * Log: full event list written via one path.write_bytes call,
    then hashed. No post-hash appends (mirrors 20.2 -- STEP 0
    CHECK 5B).

INFO-1: an inlined private sha256 helper lives in this module.
Stage 20.3 production code must NOT import compute_file_sha256
from PHX2.stage20.manifest_assembler; the duplication keeps the
20.3 boundary clean.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PHX2.stage20.constants import (
    FILTER_INTERFACE_REGISTRY_COLUMNS,
    FILTER_INTERFACE_RESULTS_COLUMNS,
)
from PHX2.stage20.filter_interface_models import (
    FilterDefinition,
    FilterEvaluationRow,
)


# ---------------------------------------------------------------------------
# README template (≤ 30 substantive lines)
# ---------------------------------------------------------------------------


STAGE20_3_README_TEMPLATE: str = """\
# Stage 20.3 — Run

This directory holds Stage 20.3 output. Stage 20.3 is the empty
filter interface scaffolding layer for PHX2 preview candidates.

## What this run did
- Read Stage 20.2 lineage from the parent run dir.
- Initialized an empty filter registry.
- Registered 0 filters.
- Evaluated 0 filters.
- Mutated 0 candidates.
- Wrote 5 deterministic artifacts.

## What this run did NOT do
- No real filters were registered or executed.
- No candidate was blocked, suppressed, demoted, or elevated.
- No live dispatch readiness was granted. safe_for_live_dispatch
  and live_dispatch_ready are both false.
- No network calls. No provider wiring. No Phoenix1 imports.

## Lineage
- Stage 20.2 run id: {stage20_run_id}
- Stage 20.2 source manifest sha256: {stage20_2_manifest_json_sha256}
- Stage 20.3 run id: {stage20_3_run_id}

## Schema versions
- filter_interface_version: filter_interface_v0_empty
- filter_registry_contract_version: filter_registry_contract_v0
- filter_result_contract_version: filter_result_contract_v0

## Notes
v0 interface is intentionally empty. Real filters arrive in a
later stage with their own design lock and audit.
"""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_file_sha256(path: Path) -> str:
    """Streamed SHA-256 hex digest (64 KiB chunks; lowercase hex).

    INFO-1: Stage 20.3-local copy of the helper. Stage 20.3
    production must not import compute_file_sha256 from the 20.2
    manifest assembler module.
    """

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def write_filter_interface_registry_csv(
    path: Path,
    registry: tuple[FilterDefinition, ...],
) -> str:
    """Write the filter-interface registry CSV; return its sha256.

    Header always written (locked column tuple). In v0 the registry
    is an empty tuple so the file contains exactly one line (the
    header) terminated by "\\n".
    """

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        writer.writerow(list(FILTER_INTERFACE_REGISTRY_COLUMNS))
        for fdef in registry:
            writer.writerow([
                getattr(fdef, col)
                for col in FILTER_INTERFACE_REGISTRY_COLUMNS
            ])
    return _compute_file_sha256(path)


def write_filter_interface_results_csv(
    path: Path,
    rows: tuple[FilterEvaluationRow, ...],
) -> str:
    """Write the filter-interface results CSV; return its sha256.

    Header always written. In v0 rows is empty so the file contains
    exactly one line (the header) terminated by "\\n".
    """

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        writer.writerow(list(FILTER_INTERFACE_RESULTS_COLUMNS))
        for row in rows:
            writer.writerow([
                getattr(row, col)
                for col in FILTER_INTERFACE_RESULTS_COLUMNS
            ])
    return _compute_file_sha256(path)


# ---------------------------------------------------------------------------
# Run log (JSON Lines; mirrors 20.2 artifact_writers.write_stage20_run_log)
# ---------------------------------------------------------------------------


def write_stage20_3_run_log(
    path: Path,
    events: list[dict[str, Any]],
) -> str:
    """Write the Stage 20.3 run log as JSON Lines; return its sha256.

    Each line: json.dumps(event, sort_keys=True,
    separators=(",", ":"), ensure_ascii=False) followed by "\\n".
    UTF-8 encoded, no BOM. The full event list is written in a
    single path.write_bytes call; the file is then hashed. No
    post-hash appends (mirrors 20.2 -- STEP 0 CHECK 5B).
    """

    rendered = []
    for event in events:
        rendered.append(json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ))
    text = "\n".join(rendered) + ("\n" if rendered else "")
    path.write_bytes(text.encode("utf-8"))
    return _compute_file_sha256(path)


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


def write_stage20_3_readme(
    path: Path,
    stage20_run_id: str,
    stage20_2_manifest_json_sha256: str,
    stage20_3_run_id: str,
) -> str:
    """Render STAGE20_3_README_TEMPLATE; return its sha256.

    The template carries three substitution fields (stage20_run_id,
    stage20_2_manifest_json_sha256, stage20_3_run_id). All other
    content is locked literal text.
    """

    rendered = STAGE20_3_README_TEMPLATE.format(
        stage20_run_id=stage20_run_id,
        stage20_2_manifest_json_sha256=stage20_2_manifest_json_sha256,
        stage20_3_run_id=stage20_3_run_id,
    )
    path.write_bytes(rendered.encode("utf-8"))
    return _compute_file_sha256(path)


# ---------------------------------------------------------------------------
# Manifest JSON
# ---------------------------------------------------------------------------


def write_stage20_3_manifest_json(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    """Serialize the Stage 20.3 manifest dict to ``path``.

    Locked serialization (matches 20.2):
        json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False) + "\\n"
    UTF-8, no BOM.

    Does NOT return a hash. The runner is the canonical site for
    computing the manifest's own sha256 from the closed file (the
    manifest does not reference its own hash, so the file is
    final once written).
    """

    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    path.write_bytes(canonical.encode("utf-8"))


__all__ = [
    "STAGE20_3_README_TEMPLATE",
    "write_filter_interface_registry_csv",
    "write_filter_interface_results_csv",
    "write_stage20_3_manifest_json",
    "write_stage20_3_readme",
    "write_stage20_3_run_log",
]
