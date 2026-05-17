"""Stage 20.4 checklist builder.

Builds the locked 28-row ``stage20_closure_checklist`` record from
the validated input config, the codebase audit result, the artifact
validation result, the input-loader's accumulated E20xx errors,
the artifact-validator's W20xx warnings, and the orchestrator's
per-run state (``run_dir_was_fresh``, ``prior_closure_run_detected``).

Row order is locked at
``PHX2.stage20.closure.constants.CHECKLIST_ROW_ORDER``. Each row's
status is a pure function of its inputs; this module does not
read files, make network calls, or invoke git/subprocess.

Status semantics:

  * ``"pass"``    -- the row's underlying condition is verified True.
  * ``"fail"``    -- the row's severity is ``"error"`` and the
                     underlying condition is False or unverified.
  * ``"warning"`` -- the row's severity is ``"warning"`` and the
                     underlying warning condition fired.
  * ``"n/a"``     -- reserved for v0; currently unused. v0 rows
                     map to pass / fail / warning only.

Phoenix1 departure note: this module imports no Phoenix1 code.

Boundary discipline: imports only stdlib + closure subtree.

What Stage 20.4 checklist_builder will NOT do:
  * No file I/O.
  * No git / subprocess / env reads / network.
  * No template rendering (handoff_writer owns markdown).

Known limitations
-----------------
  * Checklist row order is hardcoded in
    ``PHX2.stage20.closure.constants.CHECKLIST_ROW_ORDER``;
    adding a row requires updating the locked row/code definitions
    (constant tuple + checklist builder branch + tests) together.
  * Checklist statuses are derived from fixed Stage 20.4 inputs
    (input validation errors, audit result, artifact validation
    result, two orchestrator-supplied flags). There is no
    operator-supplied custom status override layer.
"""

from __future__ import annotations

from typing import Mapping

from PHX2.stage20.closure.constants import (
    CHECKLIST_ROW_ORDER,
    HANDOFF_CONTRACT_VERSION,
    LIVE_DISPATCH_READY,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE20_2_README_FILENAME,
    STAGE20_2_REQUIRED_ARTIFACT_FILENAMES,
    STAGE20_3_README_FILENAME,
    STAGE20_3_REQUIRED_ARTIFACT_FILENAMES,
)
from PHX2.stage20.closure.models import (
    ArtifactValidationResult,
    ChecklistItem,
    ClosureInputConfig,
    CodebaseAuditResult,
)


# Build {code -> (description, severity)} from the locked tuple.
_ROW_METADATA: Mapping[str, tuple[str, str]] = {
    code: (desc, severity)
    for code, desc, severity in CHECKLIST_ROW_ORDER
}


def _row(code: str, status: str, detail: str) -> ChecklistItem:
    desc, severity = _ROW_METADATA[code]
    return ChecklistItem(
        code=code,
        description=desc,
        status=status,
        detail=detail,
        severity=severity,
    )


def _find_input_error(
    errors,
    code: str,
    contains: str = "",
):
    """Return the first matching InputValidationError or None."""
    for e in errors:
        if e.code == code and (not contains or contains in e.detail):
            return e
    return None


def build_checklist(
    *,
    inputs: ClosureInputConfig,
    input_validation_errors: tuple,
    audit: CodebaseAuditResult,
    artifacts: ArtifactValidationResult,
    artifact_warnings: tuple = (),
    run_dir_was_fresh: bool = True,
    prior_closure_run_detected: bool = False,
) -> tuple:
    """Build the locked 28-row checklist.

    Returns a tuple of ``ChecklistItem`` records in the exact
    ``C20_4_01`` .. ``C20_4_28`` order defined by
    ``CHECKLIST_ROW_ORDER``.

    ``input_validation_errors``: tuple of
        ``PHX2.stage20.closure.input_loader.InputValidationError``
        records (commit-SHA + run-dir + repo-root + operator-test
        results consistency checks).
    ``artifact_warnings``: tuple of
        ``PHX2.stage20.closure.artifact_validator.ArtifactValidationWarning``
        records (W20xx).
    ``run_dir_was_fresh``: orchestrator-supplied. True when the
        target run directory did not pre-exist (E2046 did NOT fire).
        Orchestrator only reaches the checklist build step when this
        is True; tests may pass False to verify the failure branch.
    ``prior_closure_run_detected``: True iff one or more existing
        closure run dirs were found under
        ``<output_root>/stage20_closure_runs/`` (W2024).
    """

    items: list[ChecklistItem] = []

    # ----- Commit SHA validation (E2044) -----
    for code, sha_field in (
        ("C20_4_01", "stage20_1_commit_sha"),
        ("C20_4_02", "stage20_2_commit_sha"),
        ("C20_4_03", "stage20_3_commit_sha"),
    ):
        err = _find_input_error(
            input_validation_errors, "E2044", contains=sha_field,
        )
        if err is None:
            items.append(_row(code, "pass", ""))
        else:
            items.append(_row(code, "fail", err.detail))

    # ----- Stage 20.2 / 20.3 run directory existence (E2030 / E2031) -----
    items.append(_pass_or_fail_from_input_error(
        "C20_4_04", input_validation_errors, "E2030",
    ))
    items.append(_pass_or_fail_from_input_error(
        "C20_4_05", input_validation_errors, "E2031",
    ))

    # ----- Manifests valid JSON (E2032 / E2033) -----
    items.append(_row(
        "C20_4_06",
        "pass" if artifacts.stage20_2_manifest_valid else "fail",
        "" if artifacts.stage20_2_manifest_valid
        else "Stage 20.2 manifest.json failed JSON validation (E2032)",
    ))
    items.append(_row(
        "C20_4_07",
        "pass" if artifacts.stage20_3_manifest_valid else "fail",
        "" if artifacts.stage20_3_manifest_valid
        else "Stage 20.3 manifest.json failed JSON validation (E2033)",
    ))

    # ----- Safety flags (E2041 / E2042) -----
    items.append(_row(
        "C20_4_08",
        "pass" if artifacts.stage20_2_safe_for_live_dispatch_false
        else "fail",
        "" if artifacts.stage20_2_safe_for_live_dispatch_false
        else (
            "Stage 20.2 safe_for_live_dispatch is not the literal "
            "False (E2041)"
        ),
    ))
    items.append(_row(
        "C20_4_09",
        "pass" if artifacts.stage20_3_live_dispatch_ready_false
        else "fail",
        "" if artifacts.stage20_3_live_dispatch_ready_false
        else (
            "Stage 20.3 live_dispatch_ready is not the literal "
            "False (E2042)"
        ),
    ))

    # ----- Required artifacts present (E2034 / E2035) -----
    s2_missing = [
        f for f in STAGE20_2_REQUIRED_ARTIFACT_FILENAMES
        if not artifacts.stage20_2_artifacts_present.get(f, False)
    ]
    items.append(_row(
        "C20_4_10",
        "pass" if not s2_missing else "fail",
        "" if not s2_missing
        else "Stage 20.2 missing required artifact(s): "
             + ", ".join(s2_missing),
    ))
    s3_missing = [
        f for f in STAGE20_3_REQUIRED_ARTIFACT_FILENAMES
        if not artifacts.stage20_3_artifacts_present.get(f, False)
    ]
    items.append(_row(
        "C20_4_11",
        "pass" if not s3_missing else "fail",
        "" if not s3_missing
        else "Stage 20.3 missing required artifact(s): "
             + ", ".join(s3_missing),
    ))

    # ----- READMEs (W2021 / W2022) -----
    s2_readme_present = artifacts.stage20_2_artifacts_present.get(
        STAGE20_2_README_FILENAME, False,
    )
    items.append(_row(
        "C20_4_12",
        "pass" if s2_readme_present else "warning",
        "" if s2_readme_present
        else "Stage 20.2 README.md missing (W2021)",
    ))
    s3_readme_present = artifacts.stage20_3_artifacts_present.get(
        STAGE20_3_README_FILENAME, False,
    )
    items.append(_row(
        "C20_4_13",
        "pass" if s3_readme_present else "warning",
        "" if s3_readme_present
        else "Stage 20.3 README.md missing (W2022)",
    ))

    # ----- Filter CSVs header-only (E2047 / E2048) -----
    items.append(_row(
        "C20_4_14",
        "pass" if artifacts.stage20_3_filter_registry_empty else "fail",
        "" if artifacts.stage20_3_filter_registry_empty
        else (
            "Stage 20.3 filter_interface_registry.csv is not "
            "header-only (E2047)"
        ),
    ))
    items.append(_row(
        "C20_4_15",
        "pass" if artifacts.stage20_3_filter_results_empty else "fail",
        "" if artifacts.stage20_3_filter_results_empty
        else (
            "Stage 20.3 filter_interface_results.csv is not "
            "header-only (E2048)"
        ),
    ))

    # ----- Lineage crosscheck (E2036) -----
    items.append(_row(
        "C20_4_16",
        "pass" if artifacts.lineage_crosscheck_passed else "fail",
        "" if artifacts.lineage_crosscheck_passed
        else "Stage 20.3 -> Stage 20.2 lineage hash mismatch (E2036)",
    ))

    # ----- Codebase audit -----
    items.append(_row(
        "C20_4_17",
        "pass" if not audit.forbidden_network_imports else "fail",
        "" if not audit.forbidden_network_imports
        else f"{len(audit.forbidden_network_imports)} forbidden "
             f"network/dispatch import(s) found (E2037)",
    ))
    items.append(_row(
        "C20_4_18",
        "pass" if not audit.forbidden_phoenix1_imports else "fail",
        "" if not audit.forbidden_phoenix1_imports
        else f"{len(audit.forbidden_phoenix1_imports)} Phoenix1 "
             f"import(s) found (E2038)",
    ))
    items.append(_row(
        "C20_4_19",
        "pass" if not audit.cross_stage_violations else "fail",
        "" if not audit.cross_stage_violations
        else f"{len(audit.cross_stage_violations)} cross-stage "
             f"import(s) found (E2039)",
    ))
    inner_only_clean = (
        not audit.subprocess_uses_in_closure
        and not audit.sqlite_imports_in_closure
        and not audit.env_reads_in_closure
    )
    items.append(_row(
        "C20_4_20",
        "pass" if inner_only_clean else "fail",
        "" if inner_only_clean
        else (
            f"closure inner-scope: "
            f"subprocess={len(audit.subprocess_uses_in_closure)} "
            f"sqlite={len(audit.sqlite_imports_in_closure)} "
            f"env_reads={len(audit.env_reads_in_closure)} (E2037)"
        ),
    ))
    items.append(_row(
        "C20_4_21",
        "pass" if not audit.blocking_token_hits else "fail",
        "" if not audit.blocking_token_hits
        else f"{len(audit.blocking_token_hits)} blocking safety-flag "
             f"token hit(s) (E2040)",
    ))
    items.append(_row(
        "C20_4_22",
        "pass" if not audit.warning_token_hits else "warning",
        "" if not audit.warning_token_hits
        else f"{len(audit.warning_token_hits)} warning token(s) found "
             f"(W2025; informational)",
    ))

    # ----- Operator test results (E2043) -----
    has_e2043 = any(
        e.code == "E2043" for e in input_validation_errors
    )
    op_green = inputs.operator_test_results.all_green
    if not has_e2043 and op_green:
        items.append(_row("C20_4_23", "pass", ""))
    else:
        if has_e2043:
            detail = (
                "operator_test_results validation failed (E2043; "
                "see input_validation_errors for specifics)"
            )
        else:
            detail = (
                "operator_test_results.all_green is False "
                "(failures or zero passed-runs)"
            )
        items.append(_row("C20_4_23", "fail", detail))

    # ----- Stage 20.4 run dir is fresh (E2046; pre-run-dir) -----
    items.append(_row(
        "C20_4_24",
        "pass" if run_dir_was_fresh else "fail",
        "" if run_dir_was_fresh
        else (
            "Stage 20.4 target run directory already exists; refusing "
            "to overwrite (E2046)"
        ),
    ))

    # ----- Closure manifest safety flags (hardcoded constants) -----
    items.append(_row(
        "C20_4_25",
        "pass" if SAFE_FOR_LIVE_DISPATCH is False else "fail",
        "" if SAFE_FOR_LIVE_DISPATCH is False
        else "SAFE_FOR_LIVE_DISPATCH is not the literal Python False",
    ))
    items.append(_row(
        "C20_4_26",
        "pass" if LIVE_DISPATCH_READY is False else "fail",
        "" if LIVE_DISPATCH_READY is False
        else "LIVE_DISPATCH_READY is not the literal Python False",
    ))

    # ----- Handoff contract version present -----
    items.append(_row(
        "C20_4_27",
        "pass" if HANDOFF_CONTRACT_VERSION else "fail",
        "" if HANDOFF_CONTRACT_VERSION
        else "HANDOFF_CONTRACT_VERSION is empty",
    ))

    # ----- Prior closure run detected (W2024; informational) -----
    items.append(_row(
        "C20_4_28",
        "warning" if prior_closure_run_detected else "pass",
        "" if not prior_closure_run_detected
        else (
            "one or more prior closure run directories detected "
            "in output_root (W2024)"
        ),
    ))

    return tuple(items)


def _pass_or_fail_from_input_error(
    code: str,
    errors,
    error_code: str,
) -> ChecklistItem:
    err = _find_input_error(errors, error_code)
    if err is None:
        return _row(code, "pass", "")
    return _row(code, "fail", err.detail)


def checklist_counts(checklist: tuple) -> dict:
    """Return a {pass/fail/warning/na} counts dict over a checklist tuple.

    Used by closure_writer for the manifest's ``checklist_counts``
    block and by the operator stdout summary. Pure function over
    ``ChecklistItem.status`` values.
    """

    counts = {"pass": 0, "fail": 0, "warning": 0, "n/a": 0}
    for item in checklist:
        if item.status in counts:
            counts[item.status] += 1
    return {
        "total": len(checklist),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "warnings": counts["warning"],
        "na": counts["n/a"],
    }


__all__ = [
    "build_checklist",
    "checklist_counts",
]
