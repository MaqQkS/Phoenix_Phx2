"""Stage 20.4 handoff writer + closure writer tests.

Covers ``handoff_writer`` and ``closure_writer`` together:

  * Handoff template loads + renders without leaving unfilled
    ``{{placeholder}}`` markers.
  * Every required section header is present (A through H).
  * Section C uses the locked dry-run / private-preview marker
    text (verbatim) without locking an exact ping phrase.
  * Section D uses the locked Phoenix1 isolation text verbatim.
  * Section H carries the manual tag recommendation verbatim.
  * Handoff contract version is embedded.
  * README template loads + renders cleanly.

Closure writer determinism:

  * Writing the same closure packet twice (different tmp output
    dirs) produces byte-identical files across all 8 artifacts.
  * Locked write order matches CLOSURE_OUTPUT_ARTIFACT_FILENAMES.
  * JSON files use sort_keys=True + indent=2 + trailing newline.
  * CSV uses lineterminator="\\n".
  * Run log is JSON Lines with sort_keys=True.

AST self-audit:

  * Neither handoff_writer.py nor closure_writer.py imports
    forbidden network/Phoenix1/cross-stage modules.
  * Neither reads ``os.environ`` or calls ``os.getenv``.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import pytest

from PHX2.stage20.closure import closure_writer as cw
from PHX2.stage20.closure import handoff_writer as hw
from PHX2.stage20.closure.constants import (
    CLOSURE_CHECKLIST_FILENAME,
    CLOSURE_MANIFEST_FILENAME,
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    CLOSURE_README_FILENAME,
    CLOSURE_RUN_LOG_FILENAME,
    CODEBASE_AUDIT_REPORT_FILENAME,
    HANDOFF_CONTRACT_VERSION,
    STAGE20_2_LINEAGE_FILENAME,
    STAGE20_3_LINEAGE_FILENAME,
    STAGE21_HANDOFF_FILENAME,
)
from PHX2.stage20.closure.checklist_builder import build_checklist
from PHX2.stage20.closure.models import (
    ArtifactValidationResult,
    ClosureInputConfig,
    ClosurePacket,
    CodebaseAuditResult,
    OperatorTestResults,
)


# ---------------------------------------------------------------------------
# Locked text strings (must appear verbatim in the rendered doc)
# ---------------------------------------------------------------------------


_SECTION_C_HEADER = "## Section C -- Private preview boundary"
_SECTION_D_HEADER = "## Section D -- Hard rules Stage 21 inherits"
_SECTION_H_HEADER = (
    "## Section H -- Closure attestations + manual tag recommendation"
)


# Verbatim text fragments from C.13 in the locked spec.
_SECTION_C_LOCKED_TEXT = (
    "All Stage 21 outputs route to private operator-controlled "
    "channel(s)\nonly. No subscriber routing, no public channel "
    "routing, no paid-signal\nrouting."
)

_SECTION_C_MARKER_REQUIREMENT = (
    "Every Stage 21 preview ping must carry an explicit, visible "
    "dry-run /\nprivate-preview marker"
)

_SECTION_C_NO_LOCKED_PING_TEXT = (
    "Stage 20.4 does not lock the exact text"
)

_SECTION_D_PHOENIX1_ISOLATION_HEADER = "Phoenix1 isolation (locked)."

_SECTION_D_LOCKED_TEXT = (
    "Stage 21 must not import Phoenix1 code, and must not depend "
    "on Phoenix1\nruntime state as its live provider path. Any "
    "Phoenix1 comparison/replay\nmust remain offline and separately "
    "scoped (see Stage 16 for the\nreplay/comparison stage, when "
    "implemented)."
)

_SECTION_H_MANUAL_TAG_LINE = (
    "git tag -a stage-20-closed -m \"PHX2 Stage 20 closed after "
    "20.4 audit\""
)

_SECTION_H_NO_AUTO_CREATION_LINE = (
    "Stage 20.4 will not create this tag."
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_inputs(tmp_path: Path) -> ClosureInputConfig:
    op = OperatorTestResults(
        test_command="pytest PHX2/tests/stage20/ -q",
        run1_passed=42, run1_failed=0, run1_errors=0,
        run2_passed=42, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    return ClosureInputConfig(
        stage20_1_commit_sha="c" * 40,
        stage20_2_commit_sha="d" * 40,
        stage20_3_commit_sha="e" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T12:34:56Z",
    )


def _make_audit() -> CodebaseAuditResult:
    return CodebaseAuditResult(
        inner_files_scanned=("PHX2/stage20/closure/x.py",),
        outer_files_scanned=("PHX2/stage20/y.py",),
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


def _make_artifacts() -> ArtifactValidationResult:
    return ArtifactValidationResult(
        stage20_2_manifest_valid=True,
        stage20_2_artifacts_present={
            "manifest.json": True,
            "preview_candidates.csv": True,
            "alert_eligibility_decisions.csv": True,
            "stage20_run.log": True,
            "README.md": True,
        },
        stage20_2_artifact_hashes=(),
        stage20_2_safe_for_live_dispatch_false=True,
        stage20_3_manifest_valid=True,
        stage20_3_artifacts_present={
            "stage20_3_manifest.json": True,
            "filter_interface_registry.csv": True,
            "filter_interface_results.csv": True,
            "stage20_3_run.log": True,
            "README.md": True,
        },
        stage20_3_artifact_hashes=(),
        stage20_3_safe_for_live_dispatch_false=True,
        stage20_3_live_dispatch_ready_false=True,
        stage20_3_filter_registry_empty=True,
        stage20_3_filter_results_empty=True,
        lineage_crosscheck_passed=True,
        passed=True,
    )


def _make_packet(tmp_path: Path) -> ClosurePacket:
    inputs = _make_inputs(tmp_path)
    audit = _make_audit()
    artifacts = _make_artifacts()
    checklist = build_checklist(
        inputs=inputs,
        input_validation_errors=(),
        audit=audit,
        artifacts=artifacts,
        artifact_warnings=(),
        run_dir_was_fresh=True,
        prior_closure_run_detected=False,
    )
    return ClosurePacket(
        inputs=inputs,
        codebase_audit=audit,
        artifact_validation=artifacts,
        checklist=checklist,
        warnings=(),
        errors=(),
        safe_for_live_dispatch=False,
        live_dispatch_ready=False,
        handoff_contract_version=HANDOFF_CONTRACT_VERSION,
        closure_status="closed_pending_operator_review",
        run_id="stage20_4_20260516T123456Z_deadbeef",
    )


def _make_log_events() -> tuple:
    ts = "2026-05-16T12:34:56Z"
    return (
        {"event": "input_loaded", "ts": ts},
        {"event": "codebase_audit_inner_started", "ts": ts},
        {"event": "codebase_audit_inner_completed", "ts": ts,
         "inner_files": 1},
        {"event": "codebase_audit_outer_started", "ts": ts},
        {"event": "codebase_audit_outer_completed", "ts": ts,
         "outer_files": 1},
        {"event": "forbidden_token_scan_started", "ts": ts},
        {"event": "forbidden_token_scan_completed", "ts": ts,
         "blocking_hits": 0, "warning_hits": 0},
        {"event": "artifact_validation_stage20_2_started", "ts": ts},
        {"event": "artifact_validation_stage20_2_completed", "ts": ts},
        {"event": "artifact_validation_stage20_3_started", "ts": ts},
        {"event": "artifact_validation_stage20_3_completed", "ts": ts},
        {"event": "lineage_crosscheck_started", "ts": ts},
        {"event": "lineage_crosscheck_completed", "ts": ts,
         "passed": True},
        {"event": "operator_test_results_validated", "ts": ts},
        {"event": "checklist_built", "ts": ts, "total": 28},
        {"event": "closure_status_decided", "ts": ts,
         "status": "closed_pending_operator_review"},
        {"event": "artifacts_written", "ts": ts, "artifact_count": 8},
    )


# ---------------------------------------------------------------------------
# Handoff writer: render returns string, no unfilled placeholders
# ---------------------------------------------------------------------------


def test_render_handoff_returns_nonempty_string(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert isinstance(text, str)
    assert len(text) > 100


def test_render_handoff_has_no_unfilled_placeholders(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert hw.find_unfilled_placeholders(text) == ()


def test_render_handoff_embeds_contract_version(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert HANDOFF_CONTRACT_VERSION in text
    assert (
        "stage20_to_stage21_private_preview_handoff_v0" in text
    )


def test_render_handoff_embeds_run_id_and_commit_shas(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_xyz")
    assert "run_xyz" in text
    assert inputs.stage20_1_commit_sha in text
    assert inputs.stage20_2_commit_sha in text
    assert inputs.stage20_3_commit_sha in text


def test_render_handoff_embeds_operator_pytest_baseline(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert inputs.operator_test_results.test_command in text
    assert str(inputs.operator_test_results.run1_passed) in text
    assert str(inputs.operator_test_results.run2_passed) in text


def test_render_handoff_is_deterministic_for_same_input(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    a = hw.render_handoff(inputs=inputs, run_id="r")
    b = hw.render_handoff(inputs=inputs, run_id="r")
    assert a == b


def test_render_readme_has_no_unfilled_placeholders(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_readme(
        inputs=inputs, run_id="r",
        closure_status="closed_pending_operator_review",
    )
    assert hw.find_unfilled_placeholders(text) == ()
    assert "r" in text  # run_id
    assert "closed_pending_operator_review" in text


def test_find_unfilled_placeholders_detects_unfilled():
    """find_unfilled_placeholders returns leftover {{x}} substrings."""
    text = "## Header\n{{unfilled_thing}} and {{another_one}}\nbody"
    leftover = hw.find_unfilled_placeholders(text)
    assert "{{unfilled_thing}}" in leftover
    assert "{{another_one}}" in leftover


def test_render_handoff_raises_on_unsupplied_placeholder(tmp_path: Path,
                                                         monkeypatch):
    """If the template has an unsupported placeholder, the renderer
    raises RuntimeError post-substitution."""
    bad_template = "Hello {{unknown_field}}\n"
    monkeypatch.setattr(
        hw, "_load_template", lambda path: bad_template,
    )
    inputs = _make_inputs(tmp_path)
    with pytest.raises(RuntimeError, match="unfilled placeholders"):
        hw.render_handoff(inputs=inputs, run_id="r")


# ---------------------------------------------------------------------------
# Required-section presence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section_header", [
    "## Section A -- What Stage 21 may consume from Stage 20",
    "## Section B -- What Stage 21 must build fresh",
    "## Section C -- Private preview boundary",
    "## Section D -- Hard rules Stage 21 inherits",
    "## Section E -- Stage 21 starting line",
    "## Section F -- Stage 21 must explicitly define separately",
    "## Section G -- Forbidden in Stage 21 v0",
    "## Section H -- Closure attestations + manual tag recommendation",
])
def test_render_handoff_has_required_section_header(
    tmp_path: Path, section_header,
):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert section_header in text


# ---------------------------------------------------------------------------
# Section C: exact locked text + dry-run/private-preview marker
# ---------------------------------------------------------------------------


def test_section_c_contains_locked_routing_text(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_C_LOCKED_TEXT in text


def test_section_c_contains_marker_requirement(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_C_MARKER_REQUIREMENT in text


def test_section_c_does_not_lock_exact_ping_text(tmp_path: Path):
    """Section C must say Stage 20.4 doesn't lock the exact ping
    phrase (Stage 21 design call)."""
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_C_NO_LOCKED_PING_TEXT in text


# ---------------------------------------------------------------------------
# Section D: exact locked Phoenix1 isolation text
# ---------------------------------------------------------------------------


def test_section_d_contains_phoenix1_isolation_header(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_D_PHOENIX1_ISOLATION_HEADER in text


def test_section_d_contains_locked_phoenix1_isolation_paragraph(
    tmp_path: Path,
):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_D_LOCKED_TEXT in text


def test_section_d_contains_locked_bullet_list(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert (
        "No `import phoenix1` or any submodule thereof in Stage 21 "
        "modules." in text
    )
    assert (
        "No reads from a live Phoenix1 database connection in "
        "Stage 21 runtime." in text
    )


# ---------------------------------------------------------------------------
# Section H: manual tag recommendation + no auto-creation
# ---------------------------------------------------------------------------


def test_section_h_contains_manual_tag_command_verbatim(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_H_MANUAL_TAG_LINE in text


def test_section_h_states_stage20_4_will_not_create_tag(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert _SECTION_H_NO_AUTO_CREATION_LINE in text


def test_section_h_lists_path_stage_block(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    for path_line in (
        "PHX2/stage20/closure/",
        "PHX2/tests/stage20/closure/",
        "PHX2/stage20/closure/templates/",
        ".gitignore",
    ):
        assert path_line in text


def test_section_h_warns_no_git_add_dot(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="r")
    assert "no `git add .`" in text


# ---------------------------------------------------------------------------
# Closure writer: writes all 8 artifacts
# ---------------------------------------------------------------------------


def _write_packet(tmp_path: Path) -> Path:
    """Build a minimal closure packet and write it. Returns the run_dir."""
    run_dir = tmp_path / "closure_run"
    run_dir.mkdir()
    packet = _make_packet(tmp_path)
    audit = _make_audit()
    artifacts = _make_artifacts()
    handoff_md = hw.render_handoff(inputs=packet.inputs, run_id=packet.run_id)
    readme_md = hw.render_readme(
        inputs=packet.inputs, run_id=packet.run_id,
        closure_status=packet.closure_status,
    )
    cw.write_closure_packet(
        run_dir=run_dir,
        packet=packet,
        audit=audit,
        artifact_validation=artifacts,
        stage20_3_recorded_stage20_2_lineage={
            "manifest_json_sha256": "0" * 64,
            "preview_candidates_csv_sha256": "1" * 64,
            "alert_eligibility_decisions_csv_sha256": "2" * 64,
            "readme_md_sha256": "3" * 64,
            "stage20_run_log_sha256": "4" * 64,
        },
        log_events=_make_log_events(),
        handoff_md=handoff_md,
        readme_md=readme_md,
    )
    return run_dir


def test_closure_writer_writes_all_8_artifacts(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    files = sorted(p.name for p in run_dir.iterdir())
    expected = sorted(CLOSURE_OUTPUT_ARTIFACT_FILENAMES)
    assert files == expected


def test_closure_writer_returns_paths_in_locked_order(tmp_path: Path):
    run_dir = tmp_path / "closure_run"
    run_dir.mkdir()
    packet = _make_packet(tmp_path)
    audit = _make_audit()
    artifacts = _make_artifacts()
    handoff_md = hw.render_handoff(inputs=packet.inputs, run_id=packet.run_id)
    readme_md = hw.render_readme(
        inputs=packet.inputs, run_id=packet.run_id,
        closure_status=packet.closure_status,
    )
    paths = cw.write_closure_packet(
        run_dir=run_dir,
        packet=packet,
        audit=audit,
        artifact_validation=artifacts,
        stage20_3_recorded_stage20_2_lineage={
            "manifest_json_sha256": "0" * 64,
            "preview_candidates_csv_sha256": "1" * 64,
            "alert_eligibility_decisions_csv_sha256": "2" * 64,
            "readme_md_sha256": "3" * 64,
            "stage20_run_log_sha256": "4" * 64,
        },
        log_events=_make_log_events(),
        handoff_md=handoff_md,
        readme_md=readme_md,
    )
    names = tuple(p.name for p in paths)
    assert names == CLOSURE_OUTPUT_ARTIFACT_FILENAMES


# ---------------------------------------------------------------------------
# Closure writer: determinism for the 8 artifacts
# ---------------------------------------------------------------------------


def _snapshot(d: Path) -> dict:
    out = {}
    for p in sorted(d.iterdir()):
        if p.is_file():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_closure_writer_is_deterministic_for_same_inputs(tmp_path: Path):
    """Writing the same closure packet twice (different output dirs)
    must produce byte-identical files across all 8 artifacts."""
    run_a = tmp_path / "a"
    run_a.mkdir()
    run_b = tmp_path / "b"
    run_b.mkdir()

    packet = _make_packet(tmp_path)
    audit = _make_audit()
    artifacts = _make_artifacts()
    handoff_md = hw.render_handoff(inputs=packet.inputs, run_id=packet.run_id)
    readme_md = hw.render_readme(
        inputs=packet.inputs, run_id=packet.run_id,
        closure_status=packet.closure_status,
    )
    recorded_lineage = {
        "manifest_json_sha256": "0" * 64,
        "preview_candidates_csv_sha256": "1" * 64,
        "alert_eligibility_decisions_csv_sha256": "2" * 64,
        "readme_md_sha256": "3" * 64,
        "stage20_run_log_sha256": "4" * 64,
    }
    events = _make_log_events()

    for target in (run_a, run_b):
        cw.write_closure_packet(
            run_dir=target,
            packet=packet,
            audit=audit,
            artifact_validation=artifacts,
            stage20_3_recorded_stage20_2_lineage=recorded_lineage,
            log_events=events,
            handoff_md=handoff_md,
            readme_md=readme_md,
        )

    snap_a = _snapshot(run_a)
    snap_b = _snapshot(run_b)
    assert snap_a == snap_b
    assert len(snap_a) == 8


# ---------------------------------------------------------------------------
# Closure writer: serialization format spot-checks
# ---------------------------------------------------------------------------


def test_manifest_json_is_sort_keys_indent_2_with_trailing_newline(
    tmp_path: Path,
):
    run_dir = _write_packet(tmp_path)
    raw = (run_dir / CLOSURE_MANIFEST_FILENAME).read_bytes()
    assert raw.endswith(b"\n")
    decoded = raw.decode("utf-8")
    # sort_keys=True + indent=2: keys appear in sorted order.
    # The first top-level key alphabetically is "artifact_validation_summary"
    # but the prefix to check is the literal "{\n  \"".
    assert decoded.startswith("{\n  \"")
    # Round-trip parse + compare canonical re-serialization.
    parsed = json.loads(decoded)
    re_serialized = json.dumps(
        parsed, sort_keys=True, indent=2, ensure_ascii=False,
    ) + "\n"
    assert decoded == re_serialized


def test_checklist_csv_uses_lf_lineterminator(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    raw = (run_dir / CLOSURE_CHECKLIST_FILENAME).read_bytes()
    # No CRLF endings.
    assert b"\r\n" not in raw
    # Header + 28 data rows = 29 lines (each ending with \n).
    assert raw.count(b"\n") == 29


def test_checklist_csv_column_order_matches_lock(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    with (run_dir / CLOSURE_CHECKLIST_FILENAME).open(
        "r", encoding="utf-8", newline="",
    ) as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "code", "description", "status", "severity", "detail",
    ]


def test_run_log_is_json_lines_with_sort_keys(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    raw = (run_dir / CLOSURE_RUN_LOG_FILENAME).read_bytes()
    lines = raw.decode("utf-8").splitlines()
    # 17 events written, so 17 lines.
    assert len(lines) == 17
    # Each line is parseable JSON.
    for line in lines:
        parsed = json.loads(line)
        # Keys must be sorted.
        re_serialized = json.dumps(
            parsed, sort_keys=True, ensure_ascii=False,
        )
        assert line == re_serialized


def test_handoff_md_in_run_dir_contains_locked_section_text(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    text = (run_dir / STAGE21_HANDOFF_FILENAME).read_text(encoding="utf-8")
    assert _SECTION_C_LOCKED_TEXT in text
    assert _SECTION_D_LOCKED_TEXT in text
    assert _SECTION_H_MANUAL_TAG_LINE in text


def test_readme_md_in_run_dir_includes_contract_version(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    text = (run_dir / CLOSURE_README_FILENAME).read_text(encoding="utf-8")
    assert HANDOFF_CONTRACT_VERSION in text


def test_lineage_json_carries_recorded_lineage_block(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    data = json.loads(
        (run_dir / STAGE20_3_LINEAGE_FILENAME).read_text(encoding="utf-8")
    )
    assert "stage20_3_recorded_stage20_2_lineage" in data
    recorded = data["stage20_3_recorded_stage20_2_lineage"]
    assert recorded["manifest_json_sha256"] == "0" * 64


def test_audit_report_json_has_locked_top_level_keys(tmp_path: Path):
    run_dir = _write_packet(tmp_path)
    data = json.loads(
        (run_dir / CODEBASE_AUDIT_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    for key in (
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
    ):
        assert key in data, key


# ---------------------------------------------------------------------------
# Run dir non-mutation: closure_writer only writes to the supplied run_dir
# ---------------------------------------------------------------------------


def test_closure_writer_does_not_touch_input_run_dirs(tmp_path: Path):
    """Build synthetic Stage 20.2 / Stage 20.3 input run dirs with a
    sentinel file each. After closure_writer runs, those files must
    be unchanged."""
    s2 = tmp_path / "s2_in"
    s2.mkdir()
    (s2 / "sentinel.txt").write_text("don't touch me", encoding="utf-8")
    s3 = tmp_path / "s3_in"
    s3.mkdir()
    (s3 / "sentinel.txt").write_text("don't touch me", encoding="utf-8")

    run_dir = tmp_path / "closure_run"
    run_dir.mkdir()

    # Build a packet pointing inputs at our synthetic dirs.
    inputs = _make_inputs(tmp_path)
    inputs = inputs._replace(stage20_2_run_dir=s2, stage20_3_run_dir=s3)
    audit = _make_audit()
    artifacts = _make_artifacts()
    checklist = build_checklist(
        inputs=inputs, input_validation_errors=(), audit=audit,
        artifacts=artifacts, artifact_warnings=(),
        run_dir_was_fresh=True, prior_closure_run_detected=False,
    )
    packet = ClosurePacket(
        inputs=inputs, codebase_audit=audit,
        artifact_validation=artifacts, checklist=checklist,
        warnings=(), errors=(),
        safe_for_live_dispatch=False, live_dispatch_ready=False,
        handoff_contract_version=HANDOFF_CONTRACT_VERSION,
        closure_status="closed_pending_operator_review",
        run_id="r",
    )
    handoff_md = hw.render_handoff(inputs=inputs, run_id="r")
    readme_md = hw.render_readme(
        inputs=inputs, run_id="r",
        closure_status="closed_pending_operator_review",
    )

    pre_s2 = (s2 / "sentinel.txt").read_text(encoding="utf-8")
    pre_s3 = (s3 / "sentinel.txt").read_text(encoding="utf-8")

    cw.write_closure_packet(
        run_dir=run_dir,
        packet=packet, audit=audit, artifact_validation=artifacts,
        stage20_3_recorded_stage20_2_lineage=None,
        log_events=_make_log_events(),
        handoff_md=handoff_md, readme_md=readme_md,
    )

    assert (s2 / "sentinel.txt").read_text(encoding="utf-8") == pre_s2
    assert (s3 / "sentinel.txt").read_text(encoding="utf-8") == pre_s3


# ---------------------------------------------------------------------------
# AST self-audit: handoff_writer.py + closure_writer.py
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


@pytest.mark.parametrize("module", [hw, cw])
def test_module_has_no_forbidden_imports(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        for bad in _FORBIDDEN:
            assert name != bad and not name.startswith(bad + "."), (
                f"{module.__name__} imports forbidden module "
                f"{name!r} at line {lineno}"
            )


@pytest.mark.parametrize("module", [hw, cw])
def test_module_does_not_import_phx2_stage20_outside_closure(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if name.startswith("PHX2.stage20") and not name.startswith(
            "PHX2.stage20.closure"
        ):
            pytest.fail(
                f"{module.__name__} imports {name!r} at line {lineno}"
            )


@pytest.mark.parametrize("module", [hw, cw])
def test_module_has_no_env_reads_or_getenv_calls(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                pytest.fail(
                    f"{module.__name__} reads os.environ at "
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
                        f"{module.__name__} calls os.getenv at "
                        f"line {node.lineno}"
                    )
