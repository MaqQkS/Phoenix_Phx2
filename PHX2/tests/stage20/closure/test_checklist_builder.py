"""Stage 20.4 checklist builder tests.

Cover:

  * Locked row order (28 rows, codes C20_4_01..C20_4_28).
  * Each row uses the locked description from CHECKLIST_ROW_ORDER.
  * Severities derive from CHECKLIST_ROW_ORDER (error / warning).
  * All-clean inputs -> every row "pass" (except W2024 row, which
    can be "pass" too when no prior closure run is present).
  * Each error condition flips its row to "fail" with a detail
    string that references the relevant E20xx code.
  * Each warning condition flips its row to "warning".
  * ``checklist_counts`` returns expected aggregates.
  * AST self-audit: no forbidden imports.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import checklist_builder as cb
from PHX2.stage20.closure.constants import CHECKLIST_ROW_ORDER
from PHX2.stage20.closure.input_loader import InputValidationError
from PHX2.stage20.closure.artifact_validator import ArtifactValidationWarning
from PHX2.stage20.closure.models import (
    ArtifactValidationResult,
    ChecklistItem,
    ClosureInputConfig,
    CodebaseAuditResult,
    OperatorTestResults,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _clean_inputs(tmp_path: Path) -> ClosureInputConfig:
    op = OperatorTestResults(
        test_command="pytest -q",
        run1_passed=10, run1_failed=0, run1_errors=0,
        run2_passed=10, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    return ClosureInputConfig(
        stage20_1_commit_sha="a" * 40,
        stage20_2_commit_sha="b" * 40,
        stage20_3_commit_sha="c" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T12:00:00Z",
    )


def _clean_audit() -> CodebaseAuditResult:
    return CodebaseAuditResult(
        inner_files_scanned=("a.py",),
        outer_files_scanned=("b.py",),
        forbidden_network_imports=(),
        forbidden_phoenix1_imports=(),
        cross_stage_violations=(),
        env_reads_in_closure=(),
        subprocess_uses_in_closure=(),
        sqlite_imports_in_closure=(),
        blocking_token_hits=(),
        warning_token_hits=(),
        passed=True,
    )


def _clean_artifacts() -> ArtifactValidationResult:
    s2_present = {
        "manifest.json": True,
        "preview_candidates.csv": True,
        "alert_eligibility_decisions.csv": True,
        "stage20_run.log": True,
        "README.md": True,
    }
    s3_present = {
        "stage20_3_manifest.json": True,
        "filter_interface_registry.csv": True,
        "filter_interface_results.csv": True,
        "stage20_3_run.log": True,
        "README.md": True,
    }
    return ArtifactValidationResult(
        stage20_2_manifest_valid=True,
        stage20_2_artifacts_present=s2_present,
        stage20_2_artifact_hashes=(),
        stage20_2_safe_for_live_dispatch_false=True,
        stage20_3_manifest_valid=True,
        stage20_3_artifacts_present=s3_present,
        stage20_3_artifact_hashes=(),
        stage20_3_safe_for_live_dispatch_false=True,
        stage20_3_live_dispatch_ready_false=True,
        stage20_3_filter_registry_empty=True,
        stage20_3_filter_results_empty=True,
        lineage_crosscheck_passed=True,
        passed=True,
    )


def _build(tmp_path, **overrides):
    """Run build_checklist with clean defaults + per-test overrides."""
    args = {
        "inputs": _clean_inputs(tmp_path),
        "input_validation_errors": (),
        "audit": _clean_audit(),
        "artifacts": _clean_artifacts(),
        "artifact_warnings": (),
        "run_dir_was_fresh": True,
        "prior_closure_run_detected": False,
    }
    args.update(overrides)
    return cb.build_checklist(**args)


def _by_code(checklist, code):
    for item in checklist:
        if item.code == code:
            return item
    raise AssertionError(f"no row {code} in checklist")


# ---------------------------------------------------------------------------
# Row order, count, columns
# ---------------------------------------------------------------------------


def test_checklist_returns_28_rows(tmp_path: Path):
    checklist = _build(tmp_path)
    assert len(checklist) == 28


def test_checklist_returns_tuple_not_list(tmp_path: Path):
    checklist = _build(tmp_path)
    assert isinstance(checklist, tuple)


def test_checklist_row_order_matches_constants(tmp_path: Path):
    checklist = _build(tmp_path)
    codes = [item.code for item in checklist]
    expected_codes = [row[0] for row in CHECKLIST_ROW_ORDER]
    assert codes == expected_codes


def test_checklist_codes_unique(tmp_path: Path):
    checklist = _build(tmp_path)
    codes = [item.code for item in checklist]
    assert len(codes) == len(set(codes))


def test_checklist_descriptions_match_locked_order(tmp_path: Path):
    checklist = _build(tmp_path)
    for item, (_code, desc, _sev) in zip(checklist, CHECKLIST_ROW_ORDER):
        assert item.description == desc


def test_checklist_severities_match_locked_order(tmp_path: Path):
    checklist = _build(tmp_path)
    for item, (_code, _desc, sev) in zip(checklist, CHECKLIST_ROW_ORDER):
        assert item.severity == sev


def test_every_row_is_checklist_item(tmp_path: Path):
    checklist = _build(tmp_path)
    for item in checklist:
        assert isinstance(item, ChecklistItem)


def test_every_row_status_is_in_locked_set(tmp_path: Path):
    checklist = _build(tmp_path)
    for item in checklist:
        assert item.status in {"pass", "fail", "warning", "n/a"}, item


# ---------------------------------------------------------------------------
# All-clean inputs -> every row passes (warning rows = "pass" too)
# ---------------------------------------------------------------------------


def test_all_clean_inputs_yield_all_pass(tmp_path: Path):
    """Clean inputs (no errors, no warnings, fresh run dir, no prior
    closure runs) yield every row status = "pass"."""
    checklist = _build(tmp_path)
    statuses = {item.status for item in checklist}
    assert statuses == {"pass"}


# ---------------------------------------------------------------------------
# Error rows flip to "fail"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code,sha_field", [
    ("C20_4_01", "stage20_1_commit_sha"),
    ("C20_4_02", "stage20_2_commit_sha"),
    ("C20_4_03", "stage20_3_commit_sha"),
])
def test_e2044_flips_commit_sha_row_to_fail(
    tmp_path: Path, code, sha_field,
):
    err = InputValidationError(
        code="E2044",
        detail=f"{sha_field}='bad' is not a 40-char lowercase hex commit SHA",
    )
    checklist = _build(tmp_path, input_validation_errors=(err,))
    row = _by_code(checklist, code)
    assert row.status == "fail"
    assert sha_field in row.detail


def test_e2030_flips_c20_4_04_to_fail(tmp_path: Path):
    err = InputValidationError(
        code="E2030",
        detail="stage20_2_run_dir does not exist or is not a directory",
    )
    checklist = _build(tmp_path, input_validation_errors=(err,))
    row = _by_code(checklist, "C20_4_04")
    assert row.status == "fail"
    assert "stage20_2_run_dir" in row.detail


def test_e2031_flips_c20_4_05_to_fail(tmp_path: Path):
    err = InputValidationError(
        code="E2031",
        detail="stage20_3_run_dir does not exist or is not a directory",
    )
    checklist = _build(tmp_path, input_validation_errors=(err,))
    row = _by_code(checklist, "C20_4_05")
    assert row.status == "fail"


def test_stage20_2_manifest_invalid_flips_c20_4_06(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(stage20_2_manifest_valid=False)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_06")
    assert row.status == "fail"
    assert "E2032" in row.detail


def test_stage20_3_manifest_invalid_flips_c20_4_07(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(stage20_3_manifest_valid=False)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_07")
    assert row.status == "fail"
    assert "E2033" in row.detail


def test_stage20_2_safe_flag_unverified_flips_c20_4_08(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(
        stage20_2_safe_for_live_dispatch_false=False,
    )
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_08")
    assert row.status == "fail"
    assert "E2041" in row.detail


def test_stage20_3_live_dispatch_unverified_flips_c20_4_09(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(
        stage20_3_live_dispatch_ready_false=False,
    )
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_09")
    assert row.status == "fail"
    assert "E2042" in row.detail


def test_stage20_2_required_artifact_missing_flips_c20_4_10(tmp_path: Path):
    base = _clean_artifacts()
    new_present = dict(base.stage20_2_artifacts_present)
    new_present["preview_candidates.csv"] = False
    artifacts = base._replace(stage20_2_artifacts_present=new_present)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_10")
    assert row.status == "fail"
    assert "preview_candidates.csv" in row.detail


def test_stage20_3_required_artifact_missing_flips_c20_4_11(tmp_path: Path):
    base = _clean_artifacts()
    new_present = dict(base.stage20_3_artifacts_present)
    new_present["filter_interface_registry.csv"] = False
    artifacts = base._replace(stage20_3_artifacts_present=new_present)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_11")
    assert row.status == "fail"
    assert "filter_interface_registry.csv" in row.detail


def test_stage20_3_filter_registry_not_empty_flips_c20_4_14(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(
        stage20_3_filter_registry_empty=False,
    )
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_14")
    assert row.status == "fail"
    assert "E2047" in row.detail


def test_stage20_3_filter_results_not_empty_flips_c20_4_15(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(
        stage20_3_filter_results_empty=False,
    )
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_15")
    assert row.status == "fail"
    assert "E2048" in row.detail


def test_lineage_crosscheck_failed_flips_c20_4_16(tmp_path: Path):
    artifacts = _clean_artifacts()._replace(
        lineage_crosscheck_passed=False,
    )
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_16")
    assert row.status == "fail"
    assert "E2036" in row.detail


def test_forbidden_network_imports_flips_c20_4_17(tmp_path: Path):
    from PHX2.stage20.closure.models import ImportHit
    audit = _clean_audit()._replace(
        forbidden_network_imports=(
            ImportHit(file="x.py", line=1, module="requests", reason="net"),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_17")
    assert row.status == "fail"
    assert "E2037" in row.detail


def test_forbidden_phoenix1_imports_flips_c20_4_18(tmp_path: Path):
    from PHX2.stage20.closure.models import ImportHit
    audit = _clean_audit()._replace(
        forbidden_phoenix1_imports=(
            ImportHit(file="x.py", line=1, module="phoenix1", reason="p1"),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_18")
    assert row.status == "fail"
    assert "E2038" in row.detail


def test_cross_stage_violations_flips_c20_4_19(tmp_path: Path):
    from PHX2.stage20.closure.models import ImportHit
    audit = _clean_audit()._replace(
        cross_stage_violations=(
            ImportHit(file="x.py", line=1, module="PHX2.stage17", reason="cs"),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_19")
    assert row.status == "fail"
    assert "E2039" in row.detail


def test_subprocess_or_sqlite_or_env_flips_c20_4_20(tmp_path: Path):
    from PHX2.stage20.closure.models import ImportHit
    audit = _clean_audit()._replace(
        subprocess_uses_in_closure=(
            ImportHit(file="x.py", line=1, module="subprocess", reason="sp"),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_20")
    assert row.status == "fail"
    assert "subprocess=1" in row.detail


def test_blocking_token_hits_flips_c20_4_21(tmp_path: Path):
    from PHX2.stage20.closure.models import TokenHit
    audit = _clean_audit()._replace(
        blocking_token_hits=(
            TokenHit(
                file="x.py", line=1, token="safe_for_live_dispatch = True",
                context="...", severity="error",
            ),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_21")
    assert row.status == "fail"
    assert "E2040" in row.detail


def test_operator_test_e2043_flips_c20_4_23(tmp_path: Path):
    err = InputValidationError(
        code="E2043",
        detail="operator_test_results.run1 is not green",
    )
    checklist = _build(tmp_path, input_validation_errors=(err,))
    row = _by_code(checklist, "C20_4_23")
    assert row.status == "fail"
    assert "E2043" in row.detail


def test_operator_all_green_false_flips_c20_4_23(tmp_path: Path):
    inputs = _clean_inputs(tmp_path)
    op = inputs.operator_test_results._replace(all_green=False)
    inputs = inputs._replace(operator_test_results=op)
    checklist = _build(tmp_path, inputs=inputs)
    row = _by_code(checklist, "C20_4_23")
    assert row.status == "fail"
    assert "all_green" in row.detail


def test_run_dir_not_fresh_flips_c20_4_24(tmp_path: Path):
    checklist = _build(tmp_path, run_dir_was_fresh=False)
    row = _by_code(checklist, "C20_4_24")
    assert row.status == "fail"
    assert "E2046" in row.detail


# ---------------------------------------------------------------------------
# Warning rows flip to "warning"
# ---------------------------------------------------------------------------


def test_missing_stage20_2_readme_warns_c20_4_12(tmp_path: Path):
    base = _clean_artifacts()
    new_present = dict(base.stage20_2_artifacts_present)
    new_present["README.md"] = False
    artifacts = base._replace(stage20_2_artifacts_present=new_present)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_12")
    assert row.status == "warning"
    assert "W2021" in row.detail


def test_missing_stage20_3_readme_warns_c20_4_13(tmp_path: Path):
    base = _clean_artifacts()
    new_present = dict(base.stage20_3_artifacts_present)
    new_present["README.md"] = False
    artifacts = base._replace(stage20_3_artifacts_present=new_present)
    checklist = _build(tmp_path, artifacts=artifacts)
    row = _by_code(checklist, "C20_4_13")
    assert row.status == "warning"
    assert "W2022" in row.detail


def test_warning_token_hits_warn_c20_4_22(tmp_path: Path):
    from PHX2.stage20.closure.models import TokenHit
    audit = _clean_audit()._replace(
        warning_token_hits=(
            TokenHit(
                file="x.py", line=1, token="api_key",
                context="...", severity="warning",
            ),
        ),
    )
    checklist = _build(tmp_path, audit=audit)
    row = _by_code(checklist, "C20_4_22")
    assert row.status == "warning"
    assert "W2025" in row.detail


def test_prior_closure_run_detected_warns_c20_4_28(tmp_path: Path):
    checklist = _build(tmp_path, prior_closure_run_detected=True)
    row = _by_code(checklist, "C20_4_28")
    assert row.status == "warning"
    assert "W2024" in row.detail


# ---------------------------------------------------------------------------
# checklist_counts aggregation
# ---------------------------------------------------------------------------


def test_checklist_counts_total_is_28(tmp_path: Path):
    checklist = _build(tmp_path)
    counts = cb.checklist_counts(checklist)
    assert counts["total"] == 28


def test_checklist_counts_all_pass_on_clean(tmp_path: Path):
    checklist = _build(tmp_path)
    counts = cb.checklist_counts(checklist)
    assert counts["passed"] == 28
    assert counts["failed"] == 0
    assert counts["warnings"] == 0
    assert counts["na"] == 0


def test_checklist_counts_reflects_one_failure(tmp_path: Path):
    err = InputValidationError(code="E2030", detail="missing")
    checklist = _build(tmp_path, input_validation_errors=(err,))
    counts = cb.checklist_counts(checklist)
    assert counts["failed"] == 1
    assert counts["passed"] == 27


def test_checklist_counts_reflects_one_warning(tmp_path: Path):
    checklist = _build(tmp_path, prior_closure_run_detected=True)
    counts = cb.checklist_counts(checklist)
    assert counts["warnings"] == 1
    assert counts["passed"] == 27


# ---------------------------------------------------------------------------
# AST self-audit: checklist_builder has no forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN = frozenset({
    "requests", "httpx", "aiohttp", "urllib3", "websockets",
    "grpc", "grpclib", "discord", "telegram", "telethon", "pyrogram",
    "dotenv", "python_dotenv", "sqlite3", "aiosqlite",
    "subprocess", "git", "pygit2", "dulwich",
    "phoenix1", "Phoenix1", "phx1",
})


def _collect_imports(tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def test_checklist_builder_has_no_forbidden_imports():
    tree = ast.parse(Path(cb.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        for bad in _FORBIDDEN:
            assert name != bad and not name.startswith(bad + "."), (
                f"checklist_builder.py imports forbidden module "
                f"{name!r} at line {lineno}"
            )


def test_checklist_builder_does_not_import_phx2_stage20_outside_closure():
    tree = ast.parse(Path(cb.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if name.startswith("PHX2.stage20") and not name.startswith(
            "PHX2.stage20.closure"
        ):
            pytest.fail(
                f"checklist_builder.py imports {name!r} at line {lineno}"
            )


def test_checklist_builder_has_no_env_reads_or_subprocess_calls():
    tree = ast.parse(Path(cb.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            value = node.value
            if isinstance(value, ast.Name) and value.id == "os":
                if node.attr == "environ":
                    pytest.fail(
                        f"checklist_builder reads os.environ at "
                        f"line {node.lineno}"
                    )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                ):
                    pytest.fail(
                        f"checklist_builder calls os.getenv at "
                        f"line {node.lineno}"
                    )
