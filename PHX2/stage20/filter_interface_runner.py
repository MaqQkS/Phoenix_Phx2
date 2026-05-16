"""Stage 20.3 run orchestrator.

Drives the locked 15-step pipeline below. The only directory
Stage 20.3 creates is
``<stage20_2_run_dir>/stage20_3/<stage20_3_run_id>/``; sibling
Stage 20.2 files are PRE/POST snapshotted and re-verified to
enforce 20.2 immutability (ground rule 12).

Pipeline:
   1. PRE snapshot of Stage 20.2 sibling-file sha256 hashes.
   2. load_and_validate_stage20_2_run (E2027 on contract failure).
   3. build_v0_registry() -> empty tuple in v0.
   4. derive_stage20_3_run_id from the validated lineage.
   5. mkdir stage20_3_run_dir = stage20_2_run_dir / "stage20_3"
      / stage20_3_run_id (refuses to overwrite -- E2027).
   6. Capture generated_at_utc from the injected clock (matches
      Stage 20.2's _format_iso_z so a single value covers all
      log events).
   7-9. Write registry CSV, results CSV, README; collect hashes.
  10. Build the locked 7-event log list (single shared ts_utc).
  11. Write log; collect hash.
  12. assemble_stage20_3_manifest with all 4 published hashes.
  13. Write manifest.json (no return hash; manifest does not
      reference itself).
  14. POST snapshot of Stage 20.2 sibling-file sha256 hashes;
      compare to step 1. Any mismatch raises E2027.
  15. Return Stage20ThreeRunResult.

Event-timestamp pattern: mirrors Stage 20.2's runner --
generated_at_utc is captured once at step 6 and reused across
all 7 events (single shared ``ts_utc`` per the 20.2 pattern).

The 20.2 immutability discipline is defensive only: Stage 20.3
never opens a 20.2 sibling file for write, so the POST snapshot
should always match PRE in correct operation. The check exists
to catch a future regression that accidentally rewrites the
parent run.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PHX2.stage20.clock import Clock
from PHX2.stage20.constants import EligibilityErrorCode
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.filter_interface_input import (
    STAGE20_2_REQUIRED_SIBLING_FILES,
    Stage20TwoInputs,
    _compute_file_sha256_streaming,
    load_and_validate_stage20_2_run,
)
from PHX2.stage20.filter_interface_models import build_v0_registry
from PHX2.stage20.filter_interface_writers import (
    write_filter_interface_registry_csv,
    write_filter_interface_results_csv,
    write_stage20_3_manifest_json,
    write_stage20_3_readme,
    write_stage20_3_run_log,
)
from PHX2.stage20.stage20_3_manifest import (
    STAGE20_3_MANIFEST_ARTIFACT_FILENAME,
    assemble_stage20_3_manifest,
    derive_stage20_3_run_id,
)


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


class Stage20ThreeRunResult(NamedTuple):
    """Locked return shape of run_stage20_3."""

    stage20_3_run_id: str
    stage20_3_run_dir: Path
    stage20_run_id: str
    registered_filter_count: int
    evaluated_filter_count: int
    candidate_mutation_count: int
    blocking_filter_count: int
    safe_for_live_dispatch: bool
    live_dispatch_ready: bool


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _format_iso_z(dt) -> str:
    """Format a tz-aware UTC datetime to ISO-8601 with trailing 'Z'.

    Mirrors Stage 20.2's runner._format_iso_z so the
    generated_at_utc string format is identical across the two
    stages.
    """

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _snapshot_sibling_hashes(
    stage20_2_run_dir: Path,
) -> dict[str, str]:
    """Compute the sha256 of every Stage 20.2 sibling file."""

    return {
        name: _compute_file_sha256_streaming(stage20_2_run_dir / name)
        for name in STAGE20_2_REQUIRED_SIBLING_FILES
    }


def _build_log_events(
    *,
    stage20_3_run_id: str,
    inputs: Stage20TwoInputs,
    generated_at_utc: str,
    registry_csv_sha: str,
    results_csv_sha: str,
    readme_sha: str,
) -> list[dict[str, object]]:
    """Build the locked 7-event Stage 20.3 run-log sequence.

    Mirrors Stage 20.2's runner._build_log_events: a single shared
    ts_utc on every event (captured once from the injected clock),
    with the stage20_3_run_id replacing 20.2's stage20_run_id.
    """

    def _wrap(event_name: str, detail: dict[str, object]) -> dict[str, object]:
        return {
            "event": event_name,
            "ts_utc": generated_at_utc,
            "stage20_3_run_id": stage20_3_run_id,
            "detail": dict(detail),
        }

    return [
        _wrap("run_started", {
            # Symmetric with run_completed.{stage20_3_run_id, ok}; the
            # Stage 20.2 lineage is already preserved by the
            # stage20_2_inputs_loaded event (next) and the manifest's
            # stage20_2_lineage block, so no separate parent-dir field
            # is needed here.
            "stage20_3_run_id": stage20_3_run_id,
        }),
        _wrap("stage20_2_inputs_loaded", {
            "stage20_run_id": inputs.stage20_run_id,
            "manifest_json_sha256": inputs.manifest_json_sha256,
        }),
        _wrap("registry_initialized", {
            "registered_filter_count": 0,
        }),
        _wrap("evaluation_completed", {
            "evaluated_filter_count": 0,
            "candidate_mutation_count": 0,
            "blocking_filter_count": 0,
        }),
        _wrap("artifacts_written", {
            "filter_interface_registry_csv_sha256": registry_csv_sha,
            "filter_interface_results_csv_sha256": results_csv_sha,
            "readme_md_sha256": readme_sha,
        }),
        _wrap("manifest_written", {
            "path": STAGE20_3_MANIFEST_ARTIFACT_FILENAME,
            "planned": True,
        }),
        _wrap("run_completed", {
            "stage20_3_run_id": stage20_3_run_id,
            "ok": True,
        }),
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_stage20_3(
    stage20_2_run_dir: Path,
    *,
    clock: Clock,
) -> Stage20ThreeRunResult:
    """Execute the Stage 20.3 run pipeline end-to-end.

    Stage 20.2 immutability discipline (ground rule 12): the only
    directory Stage 20.3 may create is
    ``<stage20_2_run_dir>/stage20_3/<stage20_3_run_id>/`` and the
    files it places inside that directory. Stage 20.2 sibling
    artifact files are NEVER opened for write; the PRE/POST sha256
    snapshot at steps 1 and 14 is a defensive guard against a
    future regression.

    Args:
        stage20_2_run_dir: a validated Stage 20.2 run directory
            (the one written by run_stage20_2).
        clock: injected Clock (FrozenClock in tests).

    Raises:
        Stage20ValidationError(E2027): for any 20.2 input
            contract violation, pre-existing 20.3 run dir for the
            derived id, or POST-snapshot immutability check
            failure.
    """

    # ----- Step 1: load + validate Stage 20.2 inputs ------------------
    # Validation comes first so a missing / malformed run dir surfaces
    # as a clean E2027 (rather than a FileNotFoundError from the
    # snapshot helper). The PRE snapshot needs to happen BEFORE the
    # 20.3 run dir is created (step 5) but AFTER the parent run dir
    # is known to exist.
    inputs = load_and_validate_stage20_2_run(stage20_2_run_dir)

    # ----- Step 2: PRE snapshot of sibling hashes ---------------------
    pre_sibling_hashes = _snapshot_sibling_hashes(stage20_2_run_dir)

    # ----- Step 3: build empty registry (vacuous validation) ----------
    registry = build_v0_registry()

    # ----- Step 4: derive Stage 20.3 run id ---------------------------
    stage20_3_run_id = derive_stage20_3_run_id(
        inputs.stage20_run_id,
        inputs.manifest_json_sha256,
    )

    # ----- Step 5: mkdir stage20_3_run_dir ----------------------------
    stage20_3_run_dir = (
        stage20_2_run_dir / "stage20_3" / stage20_3_run_id
    )
    try:
        stage20_3_run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2027,
            detail=(
                "stage20_3 run dir already exists for derived id "
                f"{stage20_3_run_id!r}; locked v0 behavior is "
                "refuse-to-overwrite: "
                f"{stage20_3_run_dir!s}"
            ),
        ) from exc

    # ----- Step 6: generated_at_utc -----------------------------------
    generated_at_utc = _format_iso_z(clock.now())

    # ----- Step 7: registry CSV ---------------------------------------
    registry_path = (
        stage20_3_run_dir / "filter_interface_registry.csv"
    )
    registry_csv_sha = write_filter_interface_registry_csv(
        registry_path, registry,
    )

    # ----- Step 8: results CSV ----------------------------------------
    results_path = stage20_3_run_dir / "filter_interface_results.csv"
    results_csv_sha = write_filter_interface_results_csv(
        results_path, (),
    )

    # ----- Step 9: README --------------------------------------------
    readme_path = stage20_3_run_dir / "README.md"
    readme_sha = write_stage20_3_readme(
        readme_path,
        inputs.stage20_run_id,
        inputs.manifest_json_sha256,
        stage20_3_run_id,
    )

    # ----- Step 10: assemble log events ------------------------------
    events = _build_log_events(
        stage20_3_run_id=stage20_3_run_id,
        inputs=inputs,
        generated_at_utc=generated_at_utc,
        registry_csv_sha=registry_csv_sha,
        results_csv_sha=results_csv_sha,
        readme_sha=readme_sha,
    )

    # ----- Step 11: stage20_3_run.log --------------------------------
    log_path = stage20_3_run_dir / "stage20_3_run.log"
    log_sha = write_stage20_3_run_log(log_path, events)

    # ----- Step 12: assemble manifest --------------------------------
    manifest = assemble_stage20_3_manifest(
        inputs=inputs,
        stage20_3_run_id=stage20_3_run_id,
        generated_at_utc=generated_at_utc,
        filter_interface_registry_csv_sha256=registry_csv_sha,
        filter_interface_results_csv_sha256=results_csv_sha,
        stage20_3_run_log_sha256=log_sha,
        readme_md_sha256=readme_sha,
    )

    # ----- Step 13: write manifest.json ------------------------------
    manifest_path = (
        stage20_3_run_dir / STAGE20_3_MANIFEST_ARTIFACT_FILENAME
    )
    write_stage20_3_manifest_json(manifest_path, manifest)

    # ----- Step 14: POST snapshot of sibling hashes ------------------
    post_sibling_hashes = _snapshot_sibling_hashes(stage20_2_run_dir)
    if pre_sibling_hashes != post_sibling_hashes:
        mismatches = [
            name
            for name in pre_sibling_hashes
            if pre_sibling_hashes[name] != post_sibling_hashes.get(name)
        ]
        raise Stage20ValidationError(
            EligibilityErrorCode.E2027,
            detail=(
                "Stage 20.2 sibling-file mutation detected during "
                "Stage 20.3 run; immutability violated for: "
                f"{sorted(mismatches)}"
            ),
        )

    # ----- Step 15: return ------------------------------------------
    return Stage20ThreeRunResult(
        stage20_3_run_id=stage20_3_run_id,
        stage20_3_run_dir=stage20_3_run_dir,
        stage20_run_id=inputs.stage20_run_id,
        registered_filter_count=0,
        evaluated_filter_count=0,
        candidate_mutation_count=0,
        blocking_filter_count=0,
        safe_for_live_dispatch=False,
        live_dispatch_ready=False,
    )


__all__ = [
    "Stage20ThreeRunResult",
    "run_stage20_3",
]
