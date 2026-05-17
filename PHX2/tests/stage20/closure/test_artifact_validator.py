"""Stage 20.4 artifact validator tests.

Cover:

  * Public surface: outcome NamedTuple, error / warning shapes,
    helper exports.
  * Clean fixture passes (zero errors, zero warnings).
  * Stage 20.2: missing required artifacts -> E2034; optional
    README missing -> W2021; manifest malformed -> E2032;
    safe_for_live_dispatch != False -> E2041; per-artifact hashes
    captured.
  * Stage 20.3: missing required artifacts -> E2035; optional
    README missing -> W2022; manifest malformed -> E2033;
    live_dispatch_ready != False -> E2042; safe_for_live_dispatch
    (if present) != False -> E2041; registry not header-only ->
    E2047; results not header-only -> E2048.
  * No-mutation: scanning the fixture does not change any byte
    of any Stage 20.2 / Stage 20.3 file.
  * Read-only access: the validator only opens prior-stage files
    in mode ``"r"`` / ``"rb"``.
  * ``check_csv_header_only`` covers empty file, blank line file,
    header-only, header + data row.
  * AST self-audit of artifact_validator.py.

Lineage crosscheck is in test_artifact_lineage_crosscheck.py.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from PHX2.stage20.closure import artifact_validator as av
from PHX2.stage20.closure.models import (
    ArtifactHash,
    ArtifactValidationResult,
)


# ---------------------------------------------------------------------------
# Fixture roots
# ---------------------------------------------------------------------------


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"


def _copy_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the clean Stage 20.2 + Stage 20.3 fixtures into tmp_path.

    Returns (stage20_2_dir, stage20_3_dir). Tests freely modify these
    copies for negative scenarios; the source fixtures are never
    mutated.
    """

    s2 = tmp_path / "stage20_2"
    s3 = tmp_path / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    return s2, s3


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_artifact_validation_error_fields_locked():
    assert av.ArtifactValidationError._fields == ("code", "detail")


def test_artifact_validation_warning_fields_locked():
    assert av.ArtifactValidationWarning._fields == ("code", "detail")


def test_artifact_validation_outcome_fields_locked():
    assert av.ArtifactValidationOutcome._fields == (
        "result", "errors", "warnings",
    )


def test_public_helpers_exported():
    assert callable(av.compute_file_sha256)
    assert callable(av.check_csv_header_only)
    assert callable(av.validate_stage20_2)
    assert callable(av.validate_stage20_3)
    assert callable(av.crosscheck_stage20_2_lineage)
    assert callable(av.validate_artifacts)


# ---------------------------------------------------------------------------
# Clean fixture passes
# ---------------------------------------------------------------------------


def test_clean_fixture_passes(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    outcome = av.validate_artifacts(s2, s3)
    assert isinstance(outcome.result, ArtifactValidationResult)
    assert outcome.result.passed is True
    assert outcome.errors == ()
    assert outcome.warnings == ()


def test_clean_fixture_records_all_substates_true(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    r = av.validate_artifacts(s2, s3).result
    assert r.stage20_2_manifest_valid is True
    assert r.stage20_2_safe_for_live_dispatch_false is True
    assert r.stage20_3_manifest_valid is True
    assert r.stage20_3_safe_for_live_dispatch_false is True
    assert r.stage20_3_live_dispatch_ready_false is True
    assert r.stage20_3_filter_registry_empty is True
    assert r.stage20_3_filter_results_empty is True
    assert r.lineage_crosscheck_passed is True


def test_clean_fixture_records_all_required_artifacts_present(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    r = av.validate_artifacts(s2, s3).result
    for name in (
        "manifest.json",
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "stage20_run.log",
        "README.md",
    ):
        assert r.stage20_2_artifacts_present.get(name) is True, name
    for name in (
        "stage20_3_manifest.json",
        "filter_interface_registry.csv",
        "filter_interface_results.csv",
        "stage20_3_run.log",
        "README.md",
    ):
        assert r.stage20_3_artifacts_present.get(name) is True, name


def test_clean_fixture_records_artifact_hashes_with_bytes(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    r = av.validate_artifacts(s2, s3).result
    # 4 required + 1 optional README each
    assert len(r.stage20_2_artifact_hashes) == 5
    assert len(r.stage20_3_artifact_hashes) == 5
    for h in r.stage20_2_artifact_hashes + r.stage20_3_artifact_hashes:
        assert isinstance(h, ArtifactHash)
        assert len(h.sha256) == 64
        assert all(ch in "0123456789abcdef" for ch in h.sha256)
        assert h.bytes > 0


def test_artifact_hashes_match_freshly_computed_hashes(tmp_path: Path):
    """Every recorded ArtifactHash.sha256 must equal the SHA-256 we
    compute outside the validator. This is a sanity check that the
    streaming hasher behaves correctly."""
    s2, s3 = _copy_pair(tmp_path)
    r = av.validate_artifacts(s2, s3).result
    for h in r.stage20_2_artifact_hashes:
        path = s2 / h.relative_path
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        assert h.sha256 == expected, h.relative_path
    for h in r.stage20_3_artifact_hashes:
        path = s3 / h.relative_path
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        assert h.sha256 == expected, h.relative_path


# ---------------------------------------------------------------------------
# Stage 20.2 negative cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", [
    "manifest.json",
    "preview_candidates.csv",
    "alert_eligibility_decisions.csv",
    "stage20_run.log",
])
def test_stage20_2_missing_required_artifact_triggers_e2034(
    tmp_path: Path, filename,
):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / filename).unlink()
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2034" in codes
    # Detail mentions the specific filename.
    e2034 = [e for e in outcome.errors if e.code == "E2034"]
    assert any(filename in e.detail for e in e2034)
    assert outcome.result.passed is False


def test_stage20_2_missing_readme_triggers_w2021(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "README.md").unlink()
    outcome = av.validate_artifacts(s2, s3)
    codes_w = [w.code for w in outcome.warnings]
    codes_e = [e.code for e in outcome.errors]
    assert "W2021" in codes_w
    # Missing README is warning, not error.
    assert "E2034" not in codes_e or all(
        "README.md" not in e.detail
        for e in outcome.errors if e.code == "E2034"
    )
    # README is also missing from the lineage check; that's a
    # separate E2036 path covered in test_artifact_lineage_crosscheck.


def test_stage20_2_malformed_manifest_triggers_e2032(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "manifest.json").write_text("{not valid json", encoding="utf-8")
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2032" in codes
    assert outcome.result.stage20_2_manifest_valid is False


def test_stage20_2_manifest_root_not_object_triggers_e2032(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "manifest.json").write_text("[1,2,3]", encoding="utf-8")
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2032" in codes


def test_stage20_2_safe_flag_true_triggers_e2041(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "manifest.json").write_text(
        '{"safe_for_live_dispatch":true}\n', encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2041" in codes
    assert outcome.result.stage20_2_safe_for_live_dispatch_false is False


def test_stage20_2_safe_flag_missing_triggers_e2041(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "manifest.json").write_text("{}\n", encoding="utf-8")
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2041" in codes


def test_stage20_2_safe_flag_string_false_still_triggers_e2041(
    tmp_path: Path,
):
    """``"false"`` (string) is not the literal Python False; must
    trip E2041 because the locked check uses ``is False``."""
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "manifest.json").write_text(
        '{"safe_for_live_dispatch":"false"}\n', encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2041" in codes


# ---------------------------------------------------------------------------
# Stage 20.3 negative cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", [
    "stage20_3_manifest.json",
    "filter_interface_registry.csv",
    "filter_interface_results.csv",
    "stage20_3_run.log",
])
def test_stage20_3_missing_required_artifact_triggers_e2035(
    tmp_path: Path, filename,
):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / filename).unlink()
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2035" in codes
    e2035 = [e for e in outcome.errors if e.code == "E2035"]
    assert any(filename in e.detail for e in e2035)
    assert outcome.result.passed is False


def test_stage20_3_missing_readme_triggers_w2022(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "README.md").unlink()
    outcome = av.validate_artifacts(s2, s3)
    codes_w = [w.code for w in outcome.warnings]
    assert "W2022" in codes_w


def test_stage20_3_malformed_manifest_triggers_e2033(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "stage20_3_manifest.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2033" in codes
    assert outcome.result.stage20_3_manifest_valid is False


def test_stage20_3_manifest_root_not_object_triggers_e2033(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "stage20_3_manifest.json").write_text(
        "42", encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2033" in codes


def test_stage20_3_live_dispatch_ready_true_triggers_e2042(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    data = json.loads(
        (s3 / "stage20_3_manifest.json").read_text(encoding="utf-8")
    )
    data["live_dispatch_ready"] = True
    (s3 / "stage20_3_manifest.json").write_text(
        json.dumps(data), encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2042" in codes
    assert outcome.result.stage20_3_live_dispatch_ready_false is False


def test_stage20_3_live_dispatch_ready_missing_triggers_e2042(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    data = json.loads(
        (s3 / "stage20_3_manifest.json").read_text(encoding="utf-8")
    )
    data.pop("live_dispatch_ready", None)
    (s3 / "stage20_3_manifest.json").write_text(
        json.dumps(data), encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2042" in codes


def test_stage20_3_safe_flag_true_triggers_e2041(tmp_path: Path):
    """Stage 20.3 unsafe-flag violation reuses E2041 (detail clarifies
    which manifest). Per operator decision, the dedicated checklist
    row for 20.3 unsafe flag is the same E2041 code with a distinct
    detail string."""
    s2, s3 = _copy_pair(tmp_path)
    data = json.loads(
        (s3 / "stage20_3_manifest.json").read_text(encoding="utf-8")
    )
    data["safe_for_live_dispatch"] = True
    (s3 / "stage20_3_manifest.json").write_text(
        json.dumps(data), encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2041" in codes
    # Detail mentions Stage 20.3 specifically.
    assert any(
        "Stage 20.3" in e.detail
        for e in outcome.errors if e.code == "E2041"
    )
    assert outcome.result.stage20_3_safe_for_live_dispatch_false is False


def test_stage20_3_safe_flag_absent_is_acceptable(tmp_path: Path):
    """Per locked Phase 4 behavior: ``safe_for_live_dispatch`` is
    only required to be False IF PRESENT in the Stage 20.3 manifest.
    Absence is treated as vacuously OK and does not raise E2041."""
    s2, s3 = _copy_pair(tmp_path)
    data = json.loads(
        (s3 / "stage20_3_manifest.json").read_text(encoding="utf-8")
    )
    data.pop("safe_for_live_dispatch", None)
    new_text = json.dumps(data) + "\n"
    (s3 / "stage20_3_manifest.json").write_text(new_text, encoding="utf-8")

    # Recompute the 20.3 manifest hash recorded by lineage? No -- the
    # 20.3 manifest hash is not in lineage. Stage 20.2 lineage hashes
    # are unchanged (they reference Stage 20.2 files, not 20.3).
    outcome = av.validate_artifacts(s2, s3)
    e2041 = [e for e in outcome.errors if e.code == "E2041"]
    assert e2041 == []
    assert outcome.result.stage20_3_safe_for_live_dispatch_false is True


def test_stage20_3_filter_registry_empty_file_triggers_e2047(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "filter_interface_registry.csv").write_text(
        "", encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2047" in codes
    assert outcome.result.stage20_3_filter_registry_empty is False


def test_stage20_3_filter_registry_with_data_row_triggers_e2047(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    header = (
        "filter_id,filter_name,filter_version,threshold_version,"
        "mode,contract_version\n"
    )
    data_row = "f_id,f_name,v0,t0,OBSERVE_ONLY,filter_registry_contract_v0\n"
    (s3 / "filter_interface_registry.csv").write_text(
        header + data_row, encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2047" in codes


def test_stage20_3_filter_results_empty_file_triggers_e2048(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "filter_interface_results.csv").write_text(
        "", encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2048" in codes
    assert outcome.result.stage20_3_filter_results_empty is False


def test_stage20_3_filter_results_with_data_row_triggers_e2048(
    tmp_path: Path,
):
    s2, s3 = _copy_pair(tmp_path)
    header = (
        "candidate_id,filter_id,filter_name,filter_version,"
        "threshold_version,mode,evaluation_status,observation_label,"
        "observation_detail_json,contract_version\n"
    )
    data_row = "c_id,f_id,f_name,v0,t0,OBSERVE_ONLY,passed,obs,{},v0\n"
    (s3 / "filter_interface_results.csv").write_text(
        header + data_row, encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2048" in codes


# ---------------------------------------------------------------------------
# check_csv_header_only edge cases
# ---------------------------------------------------------------------------


def test_check_csv_header_only_returns_false_for_missing_file(tmp_path):
    ok, detail = av.check_csv_header_only(tmp_path / "missing.csv")
    assert ok is False
    assert "does not exist" in detail


def test_check_csv_header_only_returns_false_for_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    ok, detail = av.check_csv_header_only(p)
    assert ok is False
    assert "empty" in detail


def test_check_csv_header_only_returns_false_for_blank_line_only(tmp_path):
    p = tmp_path / "blank.csv"
    p.write_text("\n", encoding="utf-8")
    ok, detail = av.check_csv_header_only(p)
    assert ok is False
    assert "no non-empty rows" in detail


def test_check_csv_header_only_returns_true_for_header_only(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("a,b,c\n", encoding="utf-8")
    ok, detail = av.check_csv_header_only(p)
    assert ok is True
    assert detail == ""


def test_check_csv_header_only_tolerates_extra_trailing_newline(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("a,b,c\n\n", encoding="utf-8")
    ok, _ = av.check_csv_header_only(p)
    assert ok is True


def test_check_csv_header_only_rejects_header_plus_data_row(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    ok, detail = av.check_csv_header_only(p)
    assert ok is False
    assert "data row" in detail


def test_check_csv_header_only_rejects_header_plus_multiple_data_rows(
    tmp_path,
):
    p = tmp_path / "h.csv"
    p.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    ok, detail = av.check_csv_header_only(p)
    assert ok is False
    assert "2 data row" in detail


# ---------------------------------------------------------------------------
# No-mutation: validator does not change Stage 20.2 / Stage 20.3 bytes
# ---------------------------------------------------------------------------


def _snapshot_dir(d: Path) -> dict:
    out: dict[str, str] = {}
    for p in sorted(d.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(d))] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
    return out


def test_validator_does_not_mutate_stage20_2_or_stage20_3(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    pre_s2 = _snapshot_dir(s2)
    pre_s3 = _snapshot_dir(s3)
    av.validate_artifacts(s2, s3)
    post_s2 = _snapshot_dir(s2)
    post_s3 = _snapshot_dir(s3)
    assert pre_s2 == post_s2
    assert pre_s3 == post_s3


def test_validator_does_not_create_new_files_in_run_dirs(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    pre_s2_names = sorted(p.name for p in s2.iterdir())
    pre_s3_names = sorted(p.name for p in s3.iterdir())
    av.validate_artifacts(s2, s3)
    post_s2_names = sorted(p.name for p in s2.iterdir())
    post_s3_names = sorted(p.name for p in s3.iterdir())
    assert pre_s2_names == post_s2_names
    assert pre_s3_names == post_s3_names


# ---------------------------------------------------------------------------
# Read-only file access: AST scan of artifact_validator source
# ---------------------------------------------------------------------------


def _collect_open_modes(tree: ast.AST) -> list[tuple[str, int]]:
    """Find every literal-mode argument on ``Path.open(...)`` or
    ``open(...)`` calls. Returns (mode_string, lineno).

    Calls without an explicit ``mode`` argument default to ``"r"``
    so we record ``"r"``.
    """

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `<x>.open(...)` and bare `open(...)`.
        if isinstance(node.func, ast.Attribute):
            if node.func.attr != "open":
                continue
        elif isinstance(node.func, ast.Name):
            if node.func.id != "open":
                continue
        else:
            continue

        # Find the mode arg if any (first positional after self, or
        # kwarg ``mode``). For Path.open, args[0] is the mode; for
        # bare open(), args[0] is path and args[1] is mode.
        mode_str = None
        # Path.open: signature is open(mode="r", buffering=-1, ...)
        # so args[0] is mode if positional.
        if isinstance(node.func, ast.Attribute):
            if node.args and isinstance(node.args[0], ast.Constant):
                mode_str = node.args[0].value
        else:
            if (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                mode_str = node.args[1].value
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode_str = kw.value.value

        if mode_str is None:
            mode_str = "r"
        out.append((str(mode_str), node.lineno))
    return out


def test_artifact_validator_opens_only_read_modes():
    """Every ``open`` call site in artifact_validator must use a
    read-only mode (``"r"``, ``"rb"``, or rt-equivalent). Write,
    append, or exclusive-create modes are forbidden under the
    read-only contract for Stage 20.2 / Stage 20.3 artifacts."""
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for mode, lineno in _collect_open_modes(tree):
        assert mode in ("r", "rb"), (
            f"artifact_validator.py uses non-read open mode "
            f"{mode!r} at line {lineno}"
        )


def test_artifact_validator_uses_read_text_with_utf8(tmp_path: Path):
    """Verify the validator's read_text calls succeed for the fixture
    (UTF-8 round-trip). This is a behavioral guard, not an AST scan."""
    s2, s3 = _copy_pair(tmp_path)
    outcome = av.validate_artifacts(s2, s3)
    assert outcome.result.passed is True


# ---------------------------------------------------------------------------
# AST self-audit: no forbidden imports, no env reads, no subprocess
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK = frozenset({
    "requests", "httpx", "aiohttp", "urllib3", "websockets",
    "grpc", "grpclib",
    "discord", "telegram", "telethon", "pyrogram",
})

_FORBIDDEN_INNER_ONLY = frozenset({
    "dotenv", "python_dotenv",
    "sqlite3", "aiosqlite",
    "subprocess",
    "git", "pygit2", "dulwich",
})

_FORBIDDEN_PHOENIX1 = frozenset({"phoenix1", "Phoenix1", "phx1"})


def _matches_any(name: str, blacklist: frozenset[str]) -> bool:
    if name in blacklist:
        return True
    for b in blacklist:
        if name.startswith(b + "."):
            return True
    return False


def _collect_imports(tree: ast.AST):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def test_artifact_validator_has_no_forbidden_network_imports():
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any(name, _FORBIDDEN_NETWORK), (
            f"artifact_validator.py imports forbidden network "
            f"module {name!r} at line {lineno}"
        )


def test_artifact_validator_has_no_forbidden_inner_only_imports():
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any(name, _FORBIDDEN_INNER_ONLY), (
            f"artifact_validator.py imports forbidden inner-only "
            f"module {name!r} at line {lineno}"
        )


def test_artifact_validator_has_no_phoenix1_imports():
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        assert not _matches_any(name, _FORBIDDEN_PHOENIX1), (
            f"artifact_validator.py imports Phoenix1 module "
            f"{name!r} at line {lineno}"
        )


def test_artifact_validator_does_not_import_phx2_stage20_outside_closure():
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if name.startswith("PHX2.stage20") and not name.startswith(
            "PHX2.stage20.closure"
        ):
            pytest.fail(
                f"artifact_validator.py imports {name!r} at line "
                f"{lineno}"
            )


def test_artifact_validator_has_no_env_reads():
    tree = ast.parse(Path(av.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                pytest.fail(
                    f"artifact_validator.py reads os.environ at "
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
                        f"artifact_validator.py calls os.getenv "
                        f"at line {node.lineno}"
                    )
