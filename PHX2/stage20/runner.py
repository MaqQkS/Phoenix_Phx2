"""Stage 20.2 run orchestrator.

Drives the locked pipeline below. The ordering encodes one
non-obvious invariant from the Codex remediation pass:
``validate_candidate_id_uniqueness`` (E2011) runs BEFORE any
decision sequence is constructed, so a forced candidate-id
collision surfaces as the actual root cause E2011 rather than as
a downstream E2015 / E2016 symptom from doubled-up decision
rows.

Pipeline (current implementation):

     1. validate_inputs (E2001..E2010, E2022; W2001/W2004/W2005)
     2. read Stage 19 ledger rows
     3. recompute input hashes; extract Stage 18 / Stage 19 run ids
     4. capture generated_at_utc from the injected clock
     5. derive stage20_run_id
     6. resolve_slices(ledger_rows)
        + build_candidate(...) per slice          (NO decisions yet)
     7. validate_candidate_id_uniqueness          (E2011)
     8. build_decision_sequence(...) per candidate
     8b. validate_decision_sequences              (E2015 / E2016 / E2017)
     9. assemble manifest.warnings dict
        (upstream W2001/W2004/W2005 + local W2002/W2006/W2007
        + W2003 zero-stub)
    10. mkdir run_dir = output_root / "stage20_runs" / stage20_run_id
    11. write preview_candidates.csv             + sha256
    12. write alert_eligibility_decisions.csv    + sha256
    13. write README.md (no output hashes)       + sha256
    14-16. assemble run-log events; 3-artifact artifacts_written
           sorted by name ASC; locked literal manifest_written
           detail ``{"path":"manifest.json","planned":true}``
    17. write stage20_run.log                    + sha256
    18. assemble manifest with all 4 output hashes
    19. validate_manifest_shape                   (E2021 / E2024 / E2022)
    20. write manifest.json
    21. reconcile_output_artifacts               (E2023 / E2025)
    22. return Stage20RunResult

Circular-hash avoidance (locked):
  - manifest_written event detail is the literal
    ``{"path": "manifest.json", "planned": true}`` -- no value
    that depends on manifest.json's bytes.
  - README contains output artifact names only (no hashes); input
    hashes ARE emitted because they are upstream values
    independent of any artifact written during the run.
  - The log is written BEFORE the manifest; the manifest records
    the log's sha256 without a cycle.

This module is the ONLY place that imports ``validate_inputs`` --
keeping the runner the single integration point with the locked
20.1 validator surface.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Mapping, NamedTuple, Optional

from PHX2.stage20.artifact_writers import (
    write_alert_eligibility_decisions_csv,
    write_preview_candidates_csv,
    write_readme_md,
    write_stage20_run_log,
)
from PHX2.stage20.builder import (
    assemble_manifest_warnings_dict,
    build_candidate,
    build_decision_sequence,
    resolve_slices,
    select_winning_row,
    validate_candidate_id_uniqueness,
    validate_decision_sequences,
)
from PHX2.stage20.clock import Clock
from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    MAPPING_VERSION,
    PREVIEW_STATE_COUNT_KEYS,
    STAGE19_LEDGER_EXPECTED_COLUMNS,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
    EligibilityErrorCode,
)
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.ids import derive_stage20_run_id
from PHX2.stage20.input_validators import validate_inputs
from PHX2.stage20.manifest_assembler import (
    assemble_manifest,
    compute_file_sha256,
    extract_stage18_run_id_from_stage19_manifest,
    extract_stage19_run_id,
    reconcile_output_artifacts,
    recompute_input_hashes,
    validate_manifest_shape,
    write_manifest_json,
)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class Stage20RunResult(NamedTuple):
    """Locked return shape of ``run_stage20_2``.

    The runner returns enough to let tests/callers locate the run
    directory and inspect counts + warnings without re-reading
    manifest.json. The full manifest is on disk at
    ``run_dir / "manifest.json"`` for any caller that needs the
    complete dict.
    """

    stage20_run_id: str
    run_dir: Path
    candidate_count: int
    decision_count: int
    preview_state_counts: dict[str, int]
    warnings_summary: dict[str, object]


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _format_iso_z(dt) -> str:
    """Format a tz-aware UTC datetime to ISO-8601 with trailing 'Z'."""

    # Locked format matches STAGE19_LEDGER_TIMESTAMP_FORMAT.
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_ledger_rows(ledger_path: Path) -> list[dict[str, str]]:
    """Read every Stage 19 ledger row into memory.

    Defense-in-depth: re-asserts that the header is a superset of
    the locked column tuple. ``validate_inputs`` already emits
    E2009 if a required column is missing; this runtime guard
    catches the same condition if the run somehow advances past
    validation with a malformed header.
    """

    with ledger_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        missing = set(STAGE19_LEDGER_EXPECTED_COLUMNS) - set(header)
        if missing:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2009,
                detail=(
                    "Stage 19 ledger header missing required "
                    f"columns: {sorted(missing)}"
                ),
            )
        return [dict(row) for row in reader]


def _load_prior_manifest_label_mapping_and_version(
    prior_manifest_path: Optional[Path],
) -> tuple[Optional[Mapping[str, str]], Optional[str]]:
    if prior_manifest_path is None:
        return None, None
    raw = prior_manifest_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None, None
    label_mapping = data.get("label_mapping")
    if not isinstance(label_mapping, dict):
        label_mapping = None
    mapping_version = data.get("mapping_version")
    if not isinstance(mapping_version, str):
        mapping_version = None
    return label_mapping, mapping_version


def _build_log_events(
    *,
    stage20_run_id: str,
    generated_at_utc: str,
    input_hashes: Mapping[str, str],
    slice_count: int,
    ledger_row_count_considered: int,
    candidate_count: int,
    decision_count: int,
    warnings_dict: Mapping[str, object],
    readme_sha: str,
    preview_csv_sha: str,
    decisions_csv_sha: str,
) -> list[dict[str, object]]:
    """Build the locked 9-event run-log sequence.

    The artifacts_written event lists EXACTLY 3 artifacts
    (README.md, alert_eligibility_decisions.csv,
    preview_candidates.csv) sorted by name ASC -- never
    stage20_run.log itself (self-reference avoidance, operator
    constraint B).

    The manifest_written event detail is the locked literal
    ``{"path": "manifest.json", "planned": true}`` -- no manifest
    hash, no manifest bytes, no extra fields (operator constraint
    C; breaks the manifest<->log circular hash dependency).
    """

    # Warnings list (sorted by full key; emitting bare W-code).
    warnings_list = [
        {
            "code": full_key.split("_", 1)[0],
            "value": warnings_dict[full_key],
        }
        for full_key in sorted(warnings_dict.keys())
    ]

    # Artifacts list (sorted by name ASC; byte-comparison order).
    artifacts_list = sorted(
        [
            {"name": "README.md", "sha256": readme_sha},
            {
                "name": "alert_eligibility_decisions.csv",
                "sha256": decisions_csv_sha,
            },
            {"name": "preview_candidates.csv", "sha256": preview_csv_sha},
        ],
        key=lambda a: a["name"],
    )

    def _wrap(event: str, detail: Mapping[str, object]) -> dict[str, object]:
        return {
            "event": event,
            "ts_utc": generated_at_utc,
            "stage20_run_id": stage20_run_id,
            "detail": dict(detail),
        }

    return [
        _wrap("run_started", {}),
        _wrap("inputs_validated", {"input_hashes": dict(input_hashes)}),
        _wrap("slices_resolved", {
            "slice_count": slice_count,
            "ledger_row_count_considered": ledger_row_count_considered,
        }),
        _wrap("candidates_built", {"count": candidate_count}),
        _wrap("decisions_built", {"count": decision_count}),
        _wrap("warnings_emitted", {"warnings": warnings_list}),
        _wrap("artifacts_written", {"artifacts": artifacts_list}),
        # Operator constraint C: literal detail; no manifest-derived fields.
        _wrap("manifest_written", {"path": "manifest.json", "planned": True}),
        _wrap("run_completed", {}),
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_stage20_2(
    stage18_manifest_path: Path,
    stage18_review_matrix_path: Path,
    stage19_manifest_path: Path,
    stage19_ledger_path: Path,
    output_root: Path,
    *,
    clock: Clock,
    stage19_summary_path: Optional[Path] = None,
    prior_stage20_manifest_path: Optional[Path] = None,
) -> Stage20RunResult:
    """Execute the Stage 20.2 run pipeline end-to-end.

    Steps 1..22 from the Phase C spec, in order. Raises a
    ``Stage20ValidationError`` carrying the first error code on
    upstream validation failure or downstream invariant violation;
    no artifacts are written on failed validation.

    Args:
        stage18_manifest_path: Stage 18 manifest.json (consumed
            for hash; stage18_run_id is read from Stage 19's
            manifest per operator B1-a).
        stage18_review_matrix_path: Stage 18 review_matrix.csv.
        stage19_manifest_path: Stage 19 manifest.json (source of
            stage18_run_id, stage19_run_id, and the hashes
            validate_inputs cross-checks).
        stage19_ledger_path: Stage 19 operator_review_ledger.csv.
        output_root: parent directory; the run writes into
            ``output_root / "stage20_runs" / <stage20_run_id>``.
        clock: injected Clock (FrozenClock in tests).
        stage19_summary_path: optional Stage 19
            operator_review_summary.csv; if provided, its sha256
            is added to ``input_hashes.stage19_summary_sha256``.
        prior_stage20_manifest_path: optional prior 20.2 manifest;
            W2007 fires if its label_mapping or mapping_version
            differs from this run's.
    """

    # ----- Step 1: validate_inputs ------------------------------------
    stage18_dir = stage18_manifest_path.parent
    stage19_dir = stage19_manifest_path.parent
    validation_result = validate_inputs(
        stage18_dir, stage19_dir, clock=clock,
    )
    if not validation_result.ok:
        first_code = (
            validation_result.errors[0]
            if validation_result.errors
            else EligibilityErrorCode.E2021.value
        )
        raise Stage20ValidationError(
            first_code,
            detail=(
                f"validate_inputs failed; errors="
                f"{tuple(validation_result.errors)}"
            ),
        )

    # ----- Step 2: read ledger rows -----------------------------------
    ledger_rows = _read_ledger_rows(stage19_ledger_path)

    # ----- Step 3: input hashes + run ids -----------------------------
    input_hashes = recompute_input_hashes(
        stage18_manifest_path,
        stage18_review_matrix_path,
        stage19_manifest_path,
        stage19_ledger_path,
        stage19_summary_path,
    )
    stage18_run_id = extract_stage18_run_id_from_stage19_manifest(
        stage19_manifest_path
    )
    stage19_run_id = extract_stage19_run_id(stage19_manifest_path)

    # ----- Step 4: generated_at_utc -----------------------------------
    generated_at_utc = _format_iso_z(clock.now())

    # ----- Step 5: derive stage20_run_id ------------------------------
    stage20_run_id = derive_stage20_run_id(
        stage18_run_id=stage18_run_id,
        stage18_manifest_sha256=input_hashes["stage18_manifest_sha256"],
        stage18_review_matrix_sha256=input_hashes[
            "stage18_review_matrix_sha256"
        ],
        stage19_run_id=stage19_run_id,
        stage19_ledger_sha256=input_hashes["stage19_ledger_sha256"],
        stage19_manifest_sha256=input_hashes["stage19_manifest_sha256"],
        stage20_version=STAGE20_VERSION,
        stage20_minor_version=STAGE20_MINOR_VERSION,
        mapping_version=MAPPING_VERSION,
        consumer_contract_version=CONSUMER_CONTRACT_VERSION,
        generated_at_utc=generated_at_utc,
    )

    # ----- Step 6: build candidates only (NO decisions yet) -----------
    # Codex remediation: E2011 precedence. Candidate-id uniqueness is
    # validated BEFORE decision sequences are constructed; otherwise
    # a candidate_id collision would surface as a spurious E2015/E2016
    # from the doubled-up decision list rather than the actual E2011.
    slices = resolve_slices(ledger_rows)
    candidates = [
        build_candidate(
            select_winning_row(rows),
            rows,
            clock=clock,
            stage20_run_id=stage20_run_id,
        )
        for rows in slices.values()
    ]

    # ----- Step 7: candidate_id uniqueness (E2011) --------------------
    validate_candidate_id_uniqueness(candidates)

    # ----- Step 8: build decision sequences ---------------------------
    decisions = []
    for candidate in candidates:
        decisions.extend(build_decision_sequence(
            candidate, stage20_run_id=stage20_run_id,
        ))

    # ----- Step 8b: validate decision invariants (E2015/E2016/E2017) --
    validate_decision_sequences(decisions, candidates)

    # ----- Step 9: assemble manifest.warnings dict --------------------
    prior_label_mapping, prior_mapping_version = (
        _load_prior_manifest_label_mapping_and_version(
            prior_stage20_manifest_path
        )
    )
    warnings_dict = assemble_manifest_warnings_dict(
        validation_result,
        candidates,
        prior_manifest_label_mapping=prior_label_mapping,
        prior_manifest_mapping_version=prior_mapping_version,
    )

    # preview_state_counts (all 4 keys, integer >= 0)
    counts = {k: 0 for k in PREVIEW_STATE_COUNT_KEYS}
    for c in candidates:
        if c.preview_state in counts:
            counts[c.preview_state] += 1

    # ----- Step 10: mkdir run_dir -------------------------------------
    run_dir = output_root / "stage20_runs" / stage20_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # ----- Step 11: preview_candidates.csv ----------------------------
    preview_csv_path = run_dir / "preview_candidates.csv"
    write_preview_candidates_csv(preview_csv_path, candidates)
    preview_csv_sha = compute_file_sha256(preview_csv_path)

    # ----- Step 12: alert_eligibility_decisions.csv -------------------
    decisions_csv_path = run_dir / "alert_eligibility_decisions.csv"
    write_alert_eligibility_decisions_csv(decisions_csv_path, decisions)
    decisions_csv_sha = compute_file_sha256(decisions_csv_path)

    # ----- Step 13: README.md (no output hashes) ----------------------
    readme_input_dict: dict[str, object] = {
        "stage20_run_id": stage20_run_id,
        "stage18_run_id": stage18_run_id,
        "stage19_run_id": stage19_run_id,
        "generated_at_utc": generated_at_utc,
        "stage20_version": STAGE20_VERSION,
        "stage20_minor_version": STAGE20_MINOR_VERSION,
        "mapping_version": MAPPING_VERSION,
        "consumer_contract_version": CONSUMER_CONTRACT_VERSION,
        "input_hashes": dict(input_hashes),
        "preview_candidates_row_count": len(candidates),
        "alert_eligibility_decisions_row_count": len(decisions),
        "preview_state_counts": dict(counts),
        "warnings": dict(warnings_dict),
    }
    readme_path = run_dir / "README.md"
    write_readme_md(readme_path, readme_input_dict)
    readme_sha = compute_file_sha256(readme_path)

    # ----- Steps 14-16: assemble run-log event list -------------------
    events = _build_log_events(
        stage20_run_id=stage20_run_id,
        generated_at_utc=generated_at_utc,
        input_hashes=input_hashes,
        slice_count=len(candidates),
        ledger_row_count_considered=len(ledger_rows),
        candidate_count=len(candidates),
        decision_count=len(decisions),
        warnings_dict=warnings_dict,
        readme_sha=readme_sha,
        preview_csv_sha=preview_csv_sha,
        decisions_csv_sha=decisions_csv_sha,
    )

    # ----- Step 17: stage20_run.log -----------------------------------
    log_path = run_dir / "stage20_run.log"
    write_stage20_run_log(log_path, events)
    log_sha = compute_file_sha256(log_path)

    # ----- Step 18: assemble manifest ---------------------------------
    output_hashes = {
        "preview_candidates_csv_sha256": preview_csv_sha,
        "alert_eligibility_decisions_csv_sha256": decisions_csv_sha,
        "readme_md_sha256": readme_sha,
        "stage20_run_log_sha256": log_sha,
    }
    manifest = assemble_manifest(
        stage20_run_id=stage20_run_id,
        stage18_run_id=stage18_run_id,
        stage19_run_id=stage19_run_id,
        generated_at_utc=generated_at_utc,
        input_hashes=input_hashes,
        output_hashes=output_hashes,
        preview_state_counts=counts,
        preview_candidates_row_count=len(candidates),
        alert_eligibility_decisions_row_count=len(decisions),
        warnings_dict=warnings_dict,
    )

    # ----- Step 19: validate_manifest_shape (E2021/E2024/E2022) -------
    validate_manifest_shape(manifest)

    # ----- Step 20: write manifest.json -------------------------------
    manifest_path = run_dir / "manifest.json"
    write_manifest_json(manifest_path, manifest)

    # ----- Step 21: post-write reconciliation (E2023 / E2025) ---------
    reconcile_output_artifacts(manifest, run_dir)

    # ----- Step 22: return Stage20RunResult ---------------------------
    return Stage20RunResult(
        stage20_run_id=stage20_run_id,
        run_dir=run_dir,
        candidate_count=len(candidates),
        decision_count=len(decisions),
        preview_state_counts=dict(counts),
        warnings_summary=dict(warnings_dict),
    )


__all__ = [
    "Stage20RunResult",
    "run_stage20_2",
]
