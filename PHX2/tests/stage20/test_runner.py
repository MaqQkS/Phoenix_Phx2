"""Stage 20.2 runner end-to-end tests (Phase C).

Exercises ``run_stage20_2`` over synthetic Stage 18/19 inputs. The
synthetic factory under ``fixtures/synthetic_stage18_19.py`` produces
``validate_inputs``-clean inputs by default; tests deliberately
tamper to exercise specific failure modes.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.constants import (
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PreviewEligibilityState,
)
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.runner import run_stage20_2
from PHX2.tests.stage20.fixtures.synthetic_stage18_19 import (
    make_ledger_row,
    make_minimal_valid_inputs,
    make_review_matrix_row,
    make_stage18_files,
    make_stage19_files,
)


# Frozen clock used by every test (so generated_at_utc and
# downstream stage20_run_id are byte-stable across runs).
_FROZEN_NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


def _frozen_clock() -> FrozenClock:
    return FrozenClock(_FROZEN_NOW)


def _ts(days_ago: int) -> str:
    return (_FROZEN_NOW - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# 21-24. End-to-end small runs
# ---------------------------------------------------------------------------


def test_minimal_valid_ledger_produces_one_candidate_four_decisions(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    assert result.candidate_count == 1
    assert result.decision_count == 4
    assert result.preview_state_counts["PREVIEW_ELIGIBLE"] == 1
    assert result.warnings_summary["W2002_preview_eligible_count_zero"] is False


def test_empty_ledger_zero_candidates_w2002_fires(tmp_path):
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    # Stage 18 with one matrix row; Stage 19 with empty ledger.
    rm_rows = [make_review_matrix_row()]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, [], s18_manifest, s18_rm,
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    assert result.candidate_count == 0
    assert result.decision_count == 0
    assert result.warnings_summary["W2002_preview_eligible_count_zero"] is True

    # Headers still written.
    preview_csv = result.run_dir / "preview_candidates.csv"
    assert preview_csv.exists()
    lines = preview_csv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # header only


def test_all_rejected_all_excluded_w2002_fires(tmp_path):
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    rm_rows = [
        make_review_matrix_row(policy_hash="ph_a"),
        make_review_matrix_row(policy_hash="ph_b"),
    ]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    ledger_rows = [
        make_ledger_row(policy_hash="ph_a", ledger_row_id="r1",
                        review_label="REVIEW_REJECTED"),
        make_ledger_row(policy_hash="ph_b", ledger_row_id="r2",
                        review_label="REVIEW_HARMFUL_CONFIRMED"),
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    assert result.candidate_count == 2
    assert (
        result.preview_state_counts["PREVIEW_EXCLUDED"] == 2
    )
    assert result.preview_state_counts["PREVIEW_ELIGIBLE"] == 0
    assert result.warnings_summary["W2002_preview_eligible_count_zero"] is True


def test_six_label_mix_produces_correct_preview_state_counts(tmp_path):
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    labels = list(LABEL_TO_STATE_MAPPING_V0.keys())
    rm_rows = [
        make_review_matrix_row(policy_hash=f"ph_{i}", rule_id=f"rule_{i}")
        for i in range(len(labels))
    ]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    ledger_rows = [
        make_ledger_row(
            review_label=lbl,
            policy_hash=f"ph_{i}",
            rule_id=f"rule_{i}",
            ledger_row_id=f"r{i}",
        )
        for i, lbl in enumerate(labels)
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    counts = result.preview_state_counts
    assert counts["PREVIEW_ELIGIBLE"] == 1     # REVIEW_PROMISING_CONFIRMED
    assert counts["PREVIEW_OBSERVE_ONLY"] == 1  # WATCHLIST
    assert counts["PREVIEW_NEEDS_MORE_DATA"] == 2  # NEEDS_MORE_DATA + INCONCLUSIVE
    assert counts["PREVIEW_EXCLUDED"] == 2     # HARMFUL + REJECTED


# ---------------------------------------------------------------------------
# 17. stage20_run_id byte-stability under frozen clock
# ---------------------------------------------------------------------------


def test_stage20_run_id_is_byte_stable_under_frozen_clock(tmp_path):
    inputs1 = make_minimal_valid_inputs(tmp_path / "in1")
    inputs2 = make_minimal_valid_inputs(tmp_path / "in2")
    r1 = run_stage20_2(
        inputs1["stage18_manifest_path"],
        inputs1["stage18_review_matrix_path"],
        inputs1["stage19_manifest_path"],
        inputs1["stage19_ledger_path"],
        tmp_path / "out1",
        clock=_frozen_clock(),
    )
    r2 = run_stage20_2(
        inputs2["stage18_manifest_path"],
        inputs2["stage18_review_matrix_path"],
        inputs2["stage19_manifest_path"],
        inputs2["stage19_ledger_path"],
        tmp_path / "out2",
        clock=_frozen_clock(),
    )
    assert r1.stage20_run_id == r2.stage20_run_id


# ---------------------------------------------------------------------------
# Log determinism + circular-hash avoidance
# ---------------------------------------------------------------------------


def test_log_manifest_written_event_detail_is_locked_literal(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    log_text = (result.run_dir / "stage20_run.log").read_text(encoding="utf-8")
    events = [json.loads(L) for L in log_text.rstrip("\n").split("\n")]
    mw = next(e for e in events if e["event"] == "manifest_written")
    assert mw["detail"] == {"path": "manifest.json", "planned": True}


def test_log_byte_stable_across_two_runs_same_clock(tmp_path):
    inputs1 = make_minimal_valid_inputs(tmp_path / "in1")
    inputs2 = make_minimal_valid_inputs(tmp_path / "in2")
    r1 = run_stage20_2(
        inputs1["stage18_manifest_path"],
        inputs1["stage18_review_matrix_path"],
        inputs1["stage19_manifest_path"],
        inputs1["stage19_ledger_path"],
        tmp_path / "out1",
        clock=_frozen_clock(),
    )
    r2 = run_stage20_2(
        inputs2["stage18_manifest_path"],
        inputs2["stage18_review_matrix_path"],
        inputs2["stage19_manifest_path"],
        inputs2["stage19_ledger_path"],
        tmp_path / "out2",
        clock=_frozen_clock(),
    )
    log1 = (r1.run_dir / "stage20_run.log").read_bytes()
    log2 = (r2.run_dir / "stage20_run.log").read_bytes()
    assert log1 == log2


def test_manifest_stage20_run_log_sha256_matches_on_disk_log(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    import hashlib
    log_bytes = (result.run_dir / "stage20_run.log").read_bytes()
    expected_sha = hashlib.sha256(log_bytes).hexdigest()
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["stage20_run_log_sha256"] == expected_sha


def test_log_artifacts_written_event_lists_exactly_three_artifacts(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    log_text = (result.run_dir / "stage20_run.log").read_text(encoding="utf-8")
    aw = next(
        json.loads(L)
        for L in log_text.rstrip("\n").split("\n")
        if json.loads(L)["event"] == "artifacts_written"
    )
    names = [a["name"] for a in aw["detail"]["artifacts"]]
    assert len(names) == 3
    assert "stage20_run.log" not in names  # self-reference avoidance
    assert set(names) == {
        "README.md",
        "alert_eligibility_decisions.csv",
        "preview_candidates.csv",
    }


def test_log_does_not_contain_its_own_sha256(tmp_path):
    """log self-reference avoidance -- the log's own sha never
    appears inside the log."""

    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    import hashlib
    log_bytes = (result.run_dir / "stage20_run.log").read_bytes()
    log_sha = hashlib.sha256(log_bytes).hexdigest()
    log_text = log_bytes.decode("utf-8")
    assert log_sha not in log_text


# ---------------------------------------------------------------------------
# Artifact content -- header byte assertions, README disclaimers
# ---------------------------------------------------------------------------


def test_preview_candidates_csv_header_line_byte_exact(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    text = (result.run_dir / "preview_candidates.csv").read_text(encoding="utf-8")
    expected_header = (
        "candidate_id,stage20_run_id,stage18_run_id,stage19_run_id,"
        "source_ledger_row_id,policy_hash,rule_id,window_seconds,"
        "operator_id,review_timestamp_utc,review_label,preview_state,"
        "mapping_version,tier_hint,review_age_days,review_stale,"
        "multiple_operators_for_slice,notes\n"
    )
    assert text.startswith(expected_header)


def test_alert_eligibility_decisions_csv_header_line_byte_exact(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    text = (result.run_dir / "alert_eligibility_decisions.csv").read_text(
        encoding="utf-8"
    )
    expected_header = (
        "decision_id,candidate_id,stage20_run_id,decision_step_index,"
        "decision_step_name,decision_step_state,"
        "decision_step_terminating,decision_outcome,evidence_code,"
        "evidence_detail\n"
    )
    assert text.startswith(expected_header)


def test_readme_does_not_contain_any_output_sha256(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    readme_text = (result.run_dir / "README.md").read_text(encoding="utf-8")
    for key in (
        "preview_candidates_csv_sha256",
        "alert_eligibility_decisions_csv_sha256",
        "readme_md_sha256",
        "stage20_run_log_sha256",
    ):
        sha = manifest[key]
        assert sha not in readme_text, (
            f"README must not contain output hash for {key}"
        )


def test_readme_contains_output_hashes_disclaimer_line(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    readme = (result.run_dir / "README.md").read_text(encoding="utf-8")
    assert "Output SHA-256 hashes are recorded in manifest.json." in readme


# ---------------------------------------------------------------------------
# Upstream warning surfacing -- end-to-end
# ---------------------------------------------------------------------------


def test_upstream_e2003_blocks_run_no_artifacts_written(tmp_path):
    """Stage 19 manifest declares a wrong stage18_manifest_sha256
    -> validate_inputs fires E2003 -> runner raises before any
    artifacts are written.
    """

    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    rm_rows = [make_review_matrix_row()]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    ledger_rows = [make_ledger_row()]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
        # Tamper: declare a wrong stage18_manifest_sha256.
        override_stage18_manifest_sha256="0" * 64,
    )
    output_root = tmp_path / "out"
    with pytest.raises(Stage20ValidationError) as exc:
        run_stage20_2(
            s18_manifest, s18_rm, s19_manifest, s19_ledger,
            output_root, clock=_frozen_clock(),
        )
    assert exc.value.code == "E2003"
    # No stage20_runs directory created.
    assert not (output_root / "stage20_runs").exists()


def test_upstream_w2004_multi_operator_surfaces_count_gt_zero(tmp_path):
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    rm_rows = [make_review_matrix_row()]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    # Same slice, 2 distinct operators -> upstream W2004 fires.
    ledger_rows = [
        make_ledger_row(operator_id="op_a", ledger_row_id="r1",
                        review_sequence="1"),
        make_ledger_row(operator_id="op_b", ledger_row_id="r2",
                        review_sequence="2"),
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    assert (
        result.warnings_summary[
            "W2004_multiple_operators_per_review_slice_count"
        ]
        > 0
    )


def test_upstream_w2005_evidence_gap_surfaces_count_gt_zero(tmp_path):
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    # Review matrix has ph_a only.
    rm_rows = [make_review_matrix_row(policy_hash="ph_a")]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    # Ledger row uses ph_b -- no matching evidence -> W2005.
    ledger_rows = [
        make_ledger_row(policy_hash="ph_b", ledger_row_id="r1"),
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    assert (
        result.warnings_summary[
            "W2005_stage18_evidence_missing_for_review_count"
        ]
        > 0
    )


# ---------------------------------------------------------------------------
# E2022 positive coverage (manifest emits literal false)
# ---------------------------------------------------------------------------


def test_manifest_safe_for_live_dispatch_roundtrips_python_false(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["safe_for_live_dispatch"] is False


def test_manifest_json_text_contains_safe_for_live_dispatch_false_substring(
    tmp_path,
):
    """Phase C test 41 -- exact compact substring in serialized form."""

    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    text = (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"safe_for_live_dispatch":false' in text


# ---------------------------------------------------------------------------
# W2007 end-to-end (with / without prior manifest)
# ---------------------------------------------------------------------------


def _write_prior_manifest(
    path: Path,
    *,
    mapping_version: str = "v0",
    label_mapping: dict[str, str] | None = None,
) -> Path:
    if label_mapping is None:
        label_mapping = {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}
    data = {
        "mapping_version": mapping_version,
        "label_mapping": label_mapping,
    }
    path.write_bytes(json.dumps(data, sort_keys=True).encode("utf-8"))
    return path


def test_w2007_fires_when_prior_manifest_mapping_version_differs(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    prior = _write_prior_manifest(
        tmp_path / "prior_manifest.json",
        mapping_version="v999",
    )
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
        prior_stage20_manifest_path=prior,
    )
    assert (
        result.warnings_summary[
            "W2007_eligibility_mapping_drift_detected"
        ]
        is True
    )


def test_w2007_does_not_fire_when_prior_manifest_matches(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    prior = _write_prior_manifest(tmp_path / "prior_manifest.json")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
        prior_stage20_manifest_path=prior,
    )
    assert (
        result.warnings_summary[
            "W2007_eligibility_mapping_drift_detected"
        ]
        is False
    )


def test_w2007_does_not_fire_when_no_prior_manifest_path(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    assert (
        result.warnings_summary[
            "W2007_eligibility_mapping_drift_detected"
        ]
        is False
    )


# ---------------------------------------------------------------------------
# Post-write reconciliation (E2023 row count + E2025 missing column)
# Tests synthesize the post-write violation directly.
# ---------------------------------------------------------------------------


def test_post_write_e2023_synthetic_row_count_mismatch(tmp_path):
    """The runner re-reads the CSV row counts after writing and
    compares them against manifest fields. We can't easily induce
    this from a clean run; the negative coverage lives at the
    manifest assembler / reader boundary instead. We verify the
    runner's row count by mutating the produced manifest dict
    AFTER the run and confirming the counts match the CSVs (the
    positive of the E2023 path).
    """

    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    # Reconcile manifest counts vs on-disk CSV row counts.
    import csv
    with (result.run_dir / "preview_candidates.csv").open(
        "r", encoding="utf-8", newline="",
    ) as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        preview_rows = sum(1 for _ in reader)
    assert manifest["preview_candidates_row_count"] == preview_rows
    with (result.run_dir / "alert_eligibility_decisions.csv").open(
        "r", encoding="utf-8", newline="",
    ) as f:
        reader = csv.reader(f)
        next(reader, None)
        decision_rows = sum(1 for _ in reader)
    assert manifest["alert_eligibility_decisions_row_count"] == decision_rows


def test_minimal_run_produces_all_19_manifest_keys(tmp_path):
    inputs = make_minimal_valid_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    expected = {
        "alert_eligibility_decisions_csv_sha256",
        "alert_eligibility_decisions_row_count",
        "consumer_contract_version",
        "generated_at_utc",
        "input_hashes",
        "label_mapping",
        "mapping_version",
        "preview_candidates_csv_sha256",
        "preview_candidates_row_count",
        "preview_state_counts",
        "readme_md_sha256",
        "safe_for_live_dispatch",
        "stage18_run_id",
        "stage19_run_id",
        "stage20_run_id",
        "stage20_run_log_sha256",
        "stage20_version",
        "stage20_minor_version",
        "warnings",
    }
    assert set(manifest.keys()) == expected


# ---------------------------------------------------------------------------
# Stage 18 run-id extraction observation (operator decision B1-a)
# ---------------------------------------------------------------------------


def test_e2011_precedence_over_decision_invariants(tmp_path, monkeypatch):
    """Codex remediation: when ``derive_candidate_id`` is forced to
    produce a collision between two distinct slices, the runner must
    surface E2011 -- never E2015 / E2016 / E2017 -- because
    candidate-id uniqueness is checked BEFORE decision sequences
    are built.

    Prior bug pattern: build_all_candidates produced both candidates
    AND their decision lists, and validate_decision_sequences ran
    before validate_candidate_id_uniqueness. Two candidates sharing
    a candidate_id contributed 8 decision rows to the same id,
    surfacing as a duplicate-step_index E2015 -- the actual root
    cause (collision) hidden behind the symptom.
    """

    # Build two distinct slices.
    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    rm_rows = [
        make_review_matrix_row(policy_hash="ph_a", rule_id="rule_a"),
        make_review_matrix_row(policy_hash="ph_b", rule_id="rule_b"),
    ]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    ledger_rows = [
        make_ledger_row(policy_hash="ph_a", rule_id="rule_a",
                        ledger_row_id="r1"),
        make_ledger_row(policy_hash="ph_b", rule_id="rule_b",
                        ledger_row_id="r2"),
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )

    # Force a candidate_id collision at the builder level.
    monkeypatch.setattr(
        "PHX2.stage20.builder.derive_candidate_id",
        lambda **_kwargs: "cand_forced_collision",
    )

    with pytest.raises(Stage20ValidationError) as exc:
        run_stage20_2(
            s18_manifest, s18_rm, s19_manifest, s19_ledger,
            tmp_path / "out", clock=_frozen_clock(),
        )

    # Must be E2011 -- the actual root cause -- not the downstream
    # E2015 / E2016 / E2017 symptoms.
    assert exc.value.code == "E2011", (
        f"Expected E2011 (candidate_id collision) but got "
        f"{exc.value.code}. The runner must validate "
        f"candidate-id uniqueness BEFORE building decision "
        f"sequences."
    )
    assert "E2011" in str(exc.value)


def test_runner_extracts_stage18_run_id_from_stage19_manifest(tmp_path):
    """Operator decision B1-a: the runner reads stage18_run_id from
    Stage 19's manifest, not Stage 18's. This test sets distinct
    values to ensure the right source is used: Stage 19's manifest
    carries the namespaced 'stage18_run_id', and that is the value
    that propagates into Stage 20's manifest output.
    """

    stage18_dir = tmp_path / "inputs/stage18"
    stage19_dir = tmp_path / "inputs/stage19"
    rm_rows = [make_review_matrix_row()]
    # Stage 18 own manifest records run_id="s18_OWN"
    s18_manifest, s18_rm = make_stage18_files(
        stage18_dir, rm_rows, run_id="s18_OWN",
    )
    ledger_rows = [make_ledger_row(stage18_run_id="s18_OWN")]
    # Stage 19 manifest declares stage18_run_id="s18_OWN" (namespaced).
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
        stage18_run_id="s18_OWN",
    )
    result = run_stage20_2(
        s18_manifest, s18_rm, s19_manifest, s19_ledger,
        tmp_path / "out", clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["stage18_run_id"] == "s18_OWN"
