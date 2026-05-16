"""Stage 20.2 artifact writer tests (Phase C).

Covers each writer in isolation -- no full run pipeline. Byte-level
assertions where the spec locks the on-disk shape.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from PHX2.stage20.artifact_writers import (
    write_alert_eligibility_decisions_csv,
    write_preview_candidates_csv,
    write_readme_md,
    write_stage20_run_log,
)
from PHX2.stage20.constants import (
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    MAPPING_VERSION,
    PREVIEW_CANDIDATES_CSV_COLUMNS,
)
from PHX2.stage20.models import DecisionStep, PreviewCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(
    *,
    candidate_id: str = "cand_0000000000000001",
    review_timestamp_utc: str = "2026-05-15T00:00:00Z",
    preview_state: str = "PREVIEW_ELIGIBLE",
    review_age_days: int = 0,
    review_stale: bool = False,
    multiple_operators_for_slice: bool = False,
) -> PreviewCandidate:
    return PreviewCandidate(
        candidate_id=candidate_id,
        stage18_run_id="s18_a",
        stage19_run_id="s19_a",
        policy_hash="ph_a",
        rule_id="rule_a",
        window_seconds=30,
        operator_id="op_a",
        review_sequence=1,
        review_label="REVIEW_PROMISING_CONFIRMED",
        review_timestamp_utc=review_timestamp_utc,
        eligibility_state=preview_state,
        stage18_classification="CLASS_A",
        stage17_label_preserved="LABEL_A",
        safe_for_live_dispatch=False,
        tier_hint="",
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        stage20_run_id="stage20_test_run",
        source_ledger_row_id="lrid_a",
        mapping_version=MAPPING_VERSION,
        review_age_days=review_age_days,
        review_stale=review_stale,
        multiple_operators_for_slice=multiple_operators_for_slice,
        notes="",
        preview_state=preview_state,
    )


def _decision(
    candidate_id: str = "cand_0000000000000001",
    step_index: int = 0,
    step_name: str = "slice_resolved",
    is_terminating: bool = False,
    decision_step_state: str = "passed",
    decision_outcome: str = "",
) -> DecisionStep:
    return DecisionStep(
        candidate_id=candidate_id,
        step_index=step_index,
        step_name=step_name,
        input_state="",
        output_state=decision_step_state,
        is_terminating=is_terminating,
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        decision_id=f"dec_{candidate_id}_{step_index}",
        stage20_run_id="stage20_test_run",
        decision_step_state=decision_step_state,
        decision_outcome=decision_outcome,
        evidence_code="",
        evidence_detail="",
        decision_step_index=step_index,
        decision_step_name=step_name,
        decision_step_terminating=is_terminating,
    )


# ---------------------------------------------------------------------------
# preview_candidates.csv -- header byte-exact
# ---------------------------------------------------------------------------


def test_preview_csv_header_byte_exact(tmp_path):
    path = tmp_path / "preview_candidates.csv"
    write_preview_candidates_csv(path, [])
    text = path.read_text(encoding="utf-8")
    expected_header = ",".join(PREVIEW_CANDIDATES_CSV_COLUMNS) + "\n"
    assert text == expected_header
    # No BOM.
    assert path.read_bytes()[:3] != b"\xef\xbb\xbf"


def test_preview_csv_writes_header_even_for_empty_data(tmp_path):
    path = tmp_path / "preview_candidates.csv"
    write_preview_candidates_csv(path, [])
    raw = path.read_bytes()
    # Exactly one header line + "\n", no data.
    assert raw.count(b"\n") == 1


def test_preview_csv_sort_order_review_timestamp_asc_then_candidate_id_asc(
    tmp_path,
):
    c1 = _candidate(candidate_id="cand_zzz",
                    review_timestamp_utc="2026-01-01T00:00:00Z")
    c2 = _candidate(candidate_id="cand_aaa",
                    review_timestamp_utc="2026-01-01T00:00:00Z")
    c3 = _candidate(candidate_id="cand_aaa",
                    review_timestamp_utc="2026-02-01T00:00:00Z")
    path = tmp_path / "preview_candidates.csv"
    write_preview_candidates_csv(path, [c1, c2, c3])
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # Sort: ts ASC, candidate_id ASC
    assert [r["candidate_id"] for r in rows] == [
        "cand_aaa", "cand_zzz", "cand_aaa",
    ]
    assert rows[0]["review_timestamp_utc"] == "2026-01-01T00:00:00Z"
    assert rows[2]["review_timestamp_utc"] == "2026-02-01T00:00:00Z"


def test_preview_csv_bool_cells_serialize_true_false(tmp_path):
    c = _candidate(review_stale=True, multiple_operators_for_slice=False)
    path = tmp_path / "preview_candidates.csv"
    write_preview_candidates_csv(path, [c])
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["review_stale"] == "true"
    assert rows[0]["multiple_operators_for_slice"] == "false"


def test_preview_csv_uses_minimal_quoting_and_lf_line_terminator(tmp_path):
    c = _candidate()
    path = tmp_path / "preview_candidates.csv"
    write_preview_candidates_csv(path, [c])
    raw = path.read_bytes()
    # Only "\n" line endings (no "\r\n").
    assert b"\r\n" not in raw
    # No quoted cells expected -- our test data has no commas/quotes.
    assert b'"' not in raw


# ---------------------------------------------------------------------------
# alert_eligibility_decisions.csv -- header byte-exact
# ---------------------------------------------------------------------------


def test_decisions_csv_header_byte_exact(tmp_path):
    path = tmp_path / "alert_eligibility_decisions.csv"
    write_alert_eligibility_decisions_csv(path, [])
    text = path.read_text(encoding="utf-8")
    expected = ",".join(ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS) + "\n"
    assert text == expected


def test_decisions_csv_sort_candidate_id_asc_then_step_index_asc(tmp_path):
    d1 = _decision(candidate_id="cand_zz", step_index=0)
    d2 = _decision(candidate_id="cand_aa", step_index=3,
                   is_terminating=True, decision_step_state="terminal",
                   decision_outcome="PREVIEW_ELIGIBLE")
    d3 = _decision(candidate_id="cand_aa", step_index=0)
    path = tmp_path / "alert_eligibility_decisions.csv"
    write_alert_eligibility_decisions_csv(path, [d1, d2, d3])
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["candidate_id"], r["decision_step_index"]) for r in rows] == [
        ("cand_aa", "0"),
        ("cand_aa", "3"),
        ("cand_zz", "0"),
    ]


def test_decisions_csv_terminating_serializes_true_false(tmp_path):
    d_term = _decision(step_index=3, is_terminating=True,
                       decision_step_state="terminal",
                       decision_outcome="PREVIEW_ELIGIBLE")
    d_not = _decision(step_index=0, is_terminating=False)
    path = tmp_path / "alert_eligibility_decisions.csv"
    write_alert_eligibility_decisions_csv(path, [d_term, d_not])
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_idx = {r["decision_step_index"]: r for r in rows}
    assert by_idx["3"]["decision_step_terminating"] == "true"
    assert by_idx["0"]["decision_step_terminating"] == "false"


# ---------------------------------------------------------------------------
# README.md -- structural locks (operator constraint A: NO output hashes)
# ---------------------------------------------------------------------------


def _example_manifest_dict_for_readme(*, warnings_active: bool = False) -> dict:
    warnings = {
        "W2001_run_median_staleness_exceeded": False,
        "W2002_preview_eligible_count_zero": False,
        "W2003_tier_hint_missing_count": 0,
        "W2004_multiple_operators_per_review_slice_count": 0,
        "W2005_stage18_evidence_missing_for_review_count": 0,
        "W2006_candidate_review_stale_count": 0,
        "W2007_eligibility_mapping_drift_detected": False,
    }
    if warnings_active:
        warnings["W2001_run_median_staleness_exceeded"] = True
        warnings["W2004_multiple_operators_per_review_slice_count"] = 2
    return {
        "stage20_run_id": "stage20_test_run",
        "stage18_run_id": "s18_run_a",
        "stage19_run_id": "s19_run_a",
        "generated_at_utc": "2026-05-15T00:00:00Z",
        "stage20_version": "stage20_v0_observe_only",
        "stage20_minor_version": "20.2",
        "mapping_version": "v0",
        "consumer_contract_version": "stage20_to_stage21_v0",
        "input_hashes": {
            "stage18_manifest_sha256": "a" * 64,
            "stage18_review_matrix_sha256": "b" * 64,
            "stage19_ledger_sha256": "c" * 64,
            "stage19_manifest_sha256": "d" * 64,
        },
        "preview_candidates_row_count": 1,
        "alert_eligibility_decisions_row_count": 4,
        "preview_state_counts": {
            "PREVIEW_ELIGIBLE": 1,
            "PREVIEW_OBSERVE_ONLY": 0,
            "PREVIEW_NEEDS_MORE_DATA": 0,
            "PREVIEW_EXCLUDED": 0,
        },
        "warnings": warnings,
    }


def test_readme_contains_safety_callout_verbatim(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    assert (
        "safe_for_live_dispatch: false. Stage 20 outputs are operator-"
        "historical and offline; Stage 21 owns live dispatch checks."
    ) in text


def test_readme_contains_stage21_boundary_footer_verbatim(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    assert (
        "Stage 21 boundary: live freshness, duplicate suppression, "
        "and dispatch readiness are not promised by Stage 20."
    ) in text


def test_readme_lists_four_artifact_names(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    for name in (
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "README.md",
        "stage20_run.log",
    ):
        assert name in text


def test_readme_contains_output_hashes_disclaimer_verbatim(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    assert "Output SHA-256 hashes are recorded in manifest.json." in text


def test_readme_does_not_contain_any_output_sha256_values(tmp_path):
    """Operator constraint A: README must not contain output hashes."""

    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    # Synthesize the output hashes that would exist in a real run
    # and assert none of them appear in README.
    for output_sha in ("0" * 64, "1" * 64, "deadbeef" * 8, "f" * 64):
        assert output_sha not in text


def test_readme_active_warnings_none_when_empty(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    assert "Active warnings: none" in text


def test_readme_active_warnings_lists_active_keys_and_values(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(
        path,
        _example_manifest_dict_for_readme(warnings_active=True),
    )
    text = path.read_text(encoding="utf-8")
    assert "Active warnings:" in text
    assert "W2001_run_median_staleness_exceeded: true" in text
    assert "W2004_multiple_operators_per_review_slice_count: 2" in text
    # The full "Active warnings: none" line must NOT appear when there
    # are active warnings.
    assert "Active warnings: none" not in text


def test_readme_includes_stage20_minor_version_line(tmp_path):
    """Operator decision B2-c: minor version axis shown on README."""

    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    text = path.read_text(encoding="utf-8")
    assert "stage20_minor_version: 20.2" in text
    assert "stage20_version: stage20_v0_observe_only" in text


def test_readme_uses_lf_line_endings_no_bom(tmp_path):
    path = tmp_path / "README.md"
    write_readme_md(path, _example_manifest_dict_for_readme())
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw[:3] != b"\xef\xbb\xbf"


# ---------------------------------------------------------------------------
# stage20_run.log -- JSON Lines structure
# ---------------------------------------------------------------------------


def _example_events() -> list[dict]:
    base = {"ts_utc": "2026-05-15T00:00:00Z",
            "stage20_run_id": "stage20_test_run"}
    return [
        {**base, "event": "run_started",         "detail": {}},
        {**base, "event": "inputs_validated",    "detail": {"input_hashes": {}}},
        {**base, "event": "slices_resolved",     "detail": {"slice_count": 1,
                                                            "ledger_row_count_considered": 1}},
        {**base, "event": "candidates_built",    "detail": {"count": 1}},
        {**base, "event": "decisions_built",     "detail": {"count": 4}},
        {**base, "event": "warnings_emitted",    "detail": {"warnings": []}},
        {**base, "event": "artifacts_written",   "detail": {"artifacts": []}},
        {**base, "event": "manifest_written",
                 "detail": {"path": "manifest.json", "planned": True}},
        {**base, "event": "run_completed",       "detail": {}},
    ]


def test_log_every_line_is_valid_json(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, _example_events())
    text = path.read_text(encoding="utf-8")
    lines = text.rstrip("\n").split("\n")
    for line in lines:
        json.loads(line)  # raises on invalid JSON


def test_log_trailing_newline_after_last_line(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, _example_events())
    raw = path.read_bytes()
    assert raw.endswith(b"\n")


def test_log_final_line_is_run_completed(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, _example_events())
    text = path.read_text(encoding="utf-8")
    last = text.rstrip("\n").split("\n")[-1]
    final = json.loads(last)
    assert final["event"] == "run_completed"


def test_log_manifest_written_detail_is_locked_literal(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, _example_events())
    text = path.read_text(encoding="utf-8")
    line_dict = next(
        json.loads(L) for L in text.rstrip("\n").split("\n")
        if json.loads(L)["event"] == "manifest_written"
    )
    # Operator constraint C: detail is exactly the literal locked dict.
    assert line_dict["detail"] == {
        "path": "manifest.json", "planned": True,
    }
    # No extra fields beyond path + planned.
    assert set(line_dict["detail"].keys()) == {"path", "planned"}


def test_log_byte_stable_across_two_writes(tmp_path):
    path1 = tmp_path / "log1.log"
    path2 = tmp_path / "log2.log"
    write_stage20_run_log(path1, _example_events())
    write_stage20_run_log(path2, _example_events())
    assert path1.read_bytes() == path2.read_bytes()


def test_log_uses_compact_json_separators(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, _example_events())
    text = path.read_text(encoding="utf-8")
    # Compact form: no ', ' or ': ' spacing around separators.
    assert ", " not in text
    assert ": " not in text


def test_log_writer_handles_empty_event_list(tmp_path):
    path = tmp_path / "stage20_run.log"
    write_stage20_run_log(path, [])
    assert path.read_bytes() == b""
