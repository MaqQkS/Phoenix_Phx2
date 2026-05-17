"""Stage 20.4 model shape tests.

Verify every NamedTuple constructs with explicit kwargs, every
field is in the locked position, every collection-typed field
declared as ``tuple`` materializes as a real ``tuple`` (not
``list``), and the closure packet exposes the locked safety flags
as the literal Python ``False``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage20.closure import models as m


# ---------------------------------------------------------------------------
# OperatorTestResults
# ---------------------------------------------------------------------------


def test_operator_test_results_fields_locked():
    assert m.OperatorTestResults._fields == (
        "test_command",
        "run1_passed",
        "run1_failed",
        "run1_errors",
        "run2_passed",
        "run2_failed",
        "run2_errors",
        "both_runs_match",
        "all_green",
    )


def test_operator_test_results_constructs_with_all_fields():
    r = m.OperatorTestResults(
        test_command="pytest PHX2/tests/stage20/ -q",
        run1_passed=10,
        run1_failed=0,
        run1_errors=0,
        run2_passed=10,
        run2_failed=0,
        run2_errors=0,
        both_runs_match=True,
        all_green=True,
    )
    assert r.test_command == "pytest PHX2/tests/stage20/ -q"
    assert r.run1_passed == 10
    assert r.both_runs_match is True
    assert r.all_green is True


def test_operator_test_results_is_immutable():
    r = m.OperatorTestResults(
        test_command="pytest -q",
        run1_passed=1, run1_failed=0, run1_errors=0,
        run2_passed=1, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    with pytest.raises(AttributeError):
        r.run1_passed = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ClosureInputConfig
# ---------------------------------------------------------------------------


def test_closure_input_config_fields_locked():
    assert m.ClosureInputConfig._fields == (
        "stage20_1_commit_sha",
        "stage20_2_commit_sha",
        "stage20_3_commit_sha",
        "stage20_2_run_dir",
        "stage20_3_run_dir",
        "repo_root",
        "output_root",
        "operator_test_results",
        "generated_at_utc",
    )


def test_closure_input_config_constructs(tmp_path: Path):
    op = m.OperatorTestResults(
        test_command="pytest -q",
        run1_passed=5, run1_failed=0, run1_errors=0,
        run2_passed=5, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    cfg = m.ClosureInputConfig(
        stage20_1_commit_sha="0" * 40,
        stage20_2_commit_sha="1" * 40,
        stage20_3_commit_sha="2" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T12:34:56Z",
    )
    assert isinstance(cfg.stage20_2_run_dir, Path)
    assert isinstance(cfg.stage20_3_run_dir, Path)
    assert isinstance(cfg.repo_root, Path)
    assert isinstance(cfg.output_root, Path)
    assert cfg.operator_test_results.all_green is True
    assert cfg.generated_at_utc == "2026-05-16T12:34:56Z"


# ---------------------------------------------------------------------------
# ArtifactHash
# ---------------------------------------------------------------------------


def test_artifact_hash_fields_locked():
    assert m.ArtifactHash._fields == (
        "relative_path", "sha256", "bytes",
    )


def test_artifact_hash_constructs():
    h = m.ArtifactHash(
        relative_path="manifest.json",
        sha256="a" * 64,
        bytes=123,
    )
    assert h.relative_path == "manifest.json"
    assert h.bytes == 123


# ---------------------------------------------------------------------------
# ImportHit
# ---------------------------------------------------------------------------


def test_import_hit_fields_locked():
    assert m.ImportHit._fields == ("file", "line", "module", "reason")


def test_import_hit_constructs():
    hit = m.ImportHit(
        file="PHX2/stage20/foo.py",
        line=12,
        module="requests",
        reason="network_client",
    )
    assert hit.line == 12
    assert hit.module == "requests"


# ---------------------------------------------------------------------------
# TokenHit
# ---------------------------------------------------------------------------


def test_token_hit_fields_locked():
    assert m.TokenHit._fields == (
        "file", "line", "token", "context", "severity",
    )


def test_token_hit_constructs_with_error_severity():
    t = m.TokenHit(
        file="PHX2/stage20/foo.py",
        line=42,
        token="safe_for_live_dispatch = True",
        context="...",
        severity="error",
    )
    assert t.severity == "error"


def test_token_hit_constructs_with_warning_severity():
    t = m.TokenHit(
        file="PHX2/stage20/foo.py",
        line=10,
        token="api_key",
        context="...",
        severity="warning",
    )
    assert t.severity == "warning"


# ---------------------------------------------------------------------------
# CodebaseAuditResult
# ---------------------------------------------------------------------------


def test_codebase_audit_result_fields_locked():
    assert m.CodebaseAuditResult._fields == (
        "inner_files_scanned",
        "outer_files_scanned",
        "forbidden_network_imports",
        "forbidden_phoenix1_imports",
        "cross_stage_violations",
        "env_reads_in_closure",
        "subprocess_uses_in_closure",
        "sqlite_imports_in_closure",
        "blocking_token_hits",
        "warning_token_hits",
        "passed",
    )


def test_codebase_audit_result_collection_fields_are_tuples():
    r = m.CodebaseAuditResult(
        inner_files_scanned=(),
        outer_files_scanned=(),
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
    for field_name in (
        "inner_files_scanned",
        "outer_files_scanned",
        "forbidden_network_imports",
        "forbidden_phoenix1_imports",
        "cross_stage_violations",
        "env_reads_in_closure",
        "subprocess_uses_in_closure",
        "sqlite_imports_in_closure",
        "blocking_token_hits",
        "warning_token_hits",
    ):
        value = getattr(r, field_name)
        assert isinstance(value, tuple), (
            f"{field_name} expected tuple, got {type(value).__name__}"
        )


# ---------------------------------------------------------------------------
# ArtifactValidationResult
# ---------------------------------------------------------------------------


def test_artifact_validation_result_fields_locked():
    assert m.ArtifactValidationResult._fields == (
        "stage20_2_manifest_valid",
        "stage20_2_artifacts_present",
        "stage20_2_artifact_hashes",
        "stage20_2_safe_for_live_dispatch_false",
        "stage20_3_manifest_valid",
        "stage20_3_artifacts_present",
        "stage20_3_artifact_hashes",
        "stage20_3_safe_for_live_dispatch_false",
        "stage20_3_live_dispatch_ready_false",
        "stage20_3_filter_registry_empty",
        "stage20_3_filter_results_empty",
        "lineage_crosscheck_passed",
        "passed",
    )


def test_artifact_validation_result_hash_collections_are_tuples():
    r = m.ArtifactValidationResult(
        stage20_2_manifest_valid=True,
        stage20_2_artifacts_present={"manifest.json": True},
        stage20_2_artifact_hashes=(),
        stage20_2_safe_for_live_dispatch_false=True,
        stage20_3_manifest_valid=True,
        stage20_3_artifacts_present={"stage20_3_manifest.json": True},
        stage20_3_artifact_hashes=(),
        stage20_3_safe_for_live_dispatch_false=True,
        stage20_3_live_dispatch_ready_false=True,
        stage20_3_filter_registry_empty=True,
        stage20_3_filter_results_empty=True,
        lineage_crosscheck_passed=True,
        passed=True,
    )
    assert isinstance(r.stage20_2_artifact_hashes, tuple)
    assert isinstance(r.stage20_3_artifact_hashes, tuple)
    assert isinstance(r.stage20_2_artifacts_present, dict)
    assert isinstance(r.stage20_3_artifacts_present, dict)


# ---------------------------------------------------------------------------
# ChecklistItem
# ---------------------------------------------------------------------------


def test_checklist_item_fields_locked():
    """ChecklistItem fields are (code, description, status, detail,
    severity). The CSV column order is independent (see
    CHECKLIST_CSV_COLUMNS in constants)."""
    assert m.ChecklistItem._fields == (
        "code", "description", "status", "detail", "severity",
    )


def test_checklist_item_constructs():
    item = m.ChecklistItem(
        code="C20_4_01",
        description="Stage 20.1 commit SHA format valid",
        status="pass",
        detail="",
        severity="error",
    )
    assert item.code == "C20_4_01"
    assert item.severity == "error"


# ---------------------------------------------------------------------------
# ClosurePacket
# ---------------------------------------------------------------------------


def test_closure_packet_fields_locked():
    assert m.ClosurePacket._fields == (
        "inputs",
        "codebase_audit",
        "artifact_validation",
        "checklist",
        "warnings",
        "errors",
        "safe_for_live_dispatch",
        "live_dispatch_ready",
        "handoff_contract_version",
        "closure_status",
        "run_id",
    )


def _build_minimal_packet(tmp_path: Path) -> m.ClosurePacket:
    op = m.OperatorTestResults(
        test_command="pytest -q",
        run1_passed=1, run1_failed=0, run1_errors=0,
        run2_passed=1, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    inputs = m.ClosureInputConfig(
        stage20_1_commit_sha="0" * 40,
        stage20_2_commit_sha="1" * 40,
        stage20_3_commit_sha="2" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T00:00:00Z",
    )
    ca = m.CodebaseAuditResult(
        inner_files_scanned=(),
        outer_files_scanned=(),
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
    av = m.ArtifactValidationResult(
        stage20_2_manifest_valid=True,
        stage20_2_artifacts_present={},
        stage20_2_artifact_hashes=(),
        stage20_2_safe_for_live_dispatch_false=True,
        stage20_3_manifest_valid=True,
        stage20_3_artifacts_present={},
        stage20_3_artifact_hashes=(),
        stage20_3_safe_for_live_dispatch_false=True,
        stage20_3_live_dispatch_ready_false=True,
        stage20_3_filter_registry_empty=True,
        stage20_3_filter_results_empty=True,
        lineage_crosscheck_passed=True,
        passed=True,
    )
    return m.ClosurePacket(
        inputs=inputs,
        codebase_audit=ca,
        artifact_validation=av,
        checklist=(),
        warnings=(),
        errors=(),
        safe_for_live_dispatch=False,
        live_dispatch_ready=False,
        handoff_contract_version=(
            "stage20_to_stage21_private_preview_handoff_v0"
        ),
        closure_status="closed_pending_operator_review",
        run_id="stage20_4_20260516T123456Z_deadbeef",
    )


def test_closure_packet_constructs_and_exposes_locked_flags(tmp_path: Path):
    p = _build_minimal_packet(tmp_path)
    assert p.safe_for_live_dispatch is False
    assert p.live_dispatch_ready is False
    assert (
        p.handoff_contract_version
        == "stage20_to_stage21_private_preview_handoff_v0"
    )
    assert p.closure_status == "closed_pending_operator_review"
    assert p.run_id == "stage20_4_20260516T123456Z_deadbeef"


def test_closure_packet_collection_fields_are_tuples(tmp_path: Path):
    p = _build_minimal_packet(tmp_path)
    assert isinstance(p.checklist, tuple)
    assert isinstance(p.warnings, tuple)
    assert isinstance(p.errors, tuple)


def test_closure_packet_blocked_status_is_acceptable(tmp_path: Path):
    """Both closure_status values from the closed set must construct."""
    op = m.OperatorTestResults(
        test_command="pytest -q",
        run1_passed=1, run1_failed=0, run1_errors=0,
        run2_passed=1, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    inputs = m.ClosureInputConfig(
        stage20_1_commit_sha="0" * 40,
        stage20_2_commit_sha="1" * 40,
        stage20_3_commit_sha="2" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T00:00:00Z",
    )
    ca = m.CodebaseAuditResult(
        inner_files_scanned=(),
        outer_files_scanned=(),
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
    av = m.ArtifactValidationResult(
        stage20_2_manifest_valid=True,
        stage20_2_artifacts_present={},
        stage20_2_artifact_hashes=(),
        stage20_2_safe_for_live_dispatch_false=True,
        stage20_3_manifest_valid=True,
        stage20_3_artifacts_present={},
        stage20_3_artifact_hashes=(),
        stage20_3_safe_for_live_dispatch_false=True,
        stage20_3_live_dispatch_ready_false=True,
        stage20_3_filter_registry_empty=True,
        stage20_3_filter_results_empty=True,
        lineage_crosscheck_passed=True,
        passed=True,
    )
    blocked = m.ClosurePacket(
        inputs=inputs,
        codebase_audit=ca,
        artifact_validation=av,
        checklist=(),
        warnings=(),
        errors=("E2036 lineage mismatch",),
        safe_for_live_dispatch=False,
        live_dispatch_ready=False,
        handoff_contract_version=(
            "stage20_to_stage21_private_preview_handoff_v0"
        ),
        closure_status="closure_blocked",
        run_id="stage20_4_20260516T000000Z_cafebabe",
    )
    assert blocked.closure_status == "closure_blocked"
    assert blocked.errors == ("E2036 lineage mismatch",)


# ---------------------------------------------------------------------------
# NamedTuple-ness (every model is a tuple subclass)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [
    m.OperatorTestResults,
    m.ClosureInputConfig,
    m.ArtifactHash,
    m.ImportHit,
    m.TokenHit,
    m.CodebaseAuditResult,
    m.ArtifactValidationResult,
    m.ChecklistItem,
    m.ClosurePacket,
])
def test_named_tuples_are_tuple_subclasses(cls):
    """All Stage 20.4 model classes are NamedTuple subclasses
    (=> instances are tuples)."""
    assert issubclass(cls, tuple), cls.__name__


# ---------------------------------------------------------------------------
# Module imports nothing from PHX2.stage20 outside its own subpackage
# ---------------------------------------------------------------------------


def test_models_module_imports_no_stage20_modules_outside_closure():
    """Boundary discipline: PHX2/stage20/closure/models.py must not
    import from PHX2.stage20.* outside of PHX2.stage20.closure.* .
    Walk the AST of models.py and assert."""
    import ast
    from pathlib import Path

    source_path = Path(m.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("PHX2.stage20") and not mod.startswith(
                "PHX2.stage20.closure"
            ):
                pytest.fail(
                    f"models.py must not import from {mod!r} "
                    f"at line {node.lineno}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("PHX2.stage20") and not name.startswith(
                    "PHX2.stage20.closure"
                ):
                    pytest.fail(
                        f"models.py must not `import {name}` "
                        f"at line {node.lineno}"
                    )
