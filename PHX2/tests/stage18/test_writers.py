"""Phase 18.3 writers tests.

Each test constructs synthetic ``ClassifiedRow`` inputs (no disk
fixture needed) and asserts on the writer's output bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from PHX2.stage18.classifier import ClassificationResult
from PHX2.stage18.constants import (
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
    TIER_COVERAGE_MULTI_TIER,
    TIER_COVERAGE_SINGLE_TIER_ONLY,
)
from PHX2.stage18.writers import (
    CLASSIFICATION_SUMMARY_COLUMNS,
    ClassifiedRow,
    DATA_QUALITY_BLOCKERS_COLUMNS,
    REVIEW_MATRIX_COLUMNS,
    SEVERITY_ORDER,
    make_log_event,
    write_classification_summary,
    write_data_quality_blockers,
    write_log,
    write_readme,
    write_review_matrix,
    write_rule_review_cards,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _coarse(
    *,
    policy_hash: str = "ph_a",
    rule_id: str = "rule_x",
    window_seconds: int = 3600,
    window_label: str = "1h",
    n_in_scope: int = 100,
    n_matched: int = 40,
    n_not_matched: int = 60,
    n_with_complete_outcome: int = 100,
    delta_hit_2x_rate: str = "0.100000",
    hit_2x_rate_matched: str = "0.200000",
    hit_2x_rate_not_matched: str = "0.100000",
    descriptive_label: str = "PROMISING",
) -> dict:
    return {
        "policy_hash": policy_hash,
        "rule_id": rule_id,
        "window_seconds": str(window_seconds),
        "window_label": window_label,
        "n_in_scope": str(n_in_scope),
        "n_matched": str(n_matched),
        "n_not_matched": str(n_not_matched),
        "n_with_complete_outcome": str(n_with_complete_outcome),
        "hit_2x_rate_matched": hit_2x_rate_matched,
        "hit_2x_rate_not_matched": hit_2x_rate_not_matched,
        "delta_hit_2x_rate": delta_hit_2x_rate,
        "descriptive_label": descriptive_label,
    }


def _result(
    *,
    classification: str = REVIEW_LABEL_PROMISING,
    stage17_label_preserved: str = "PROMISING",
    insufficient_sample_reason: str = "",
    data_block_reason: str = "",
    gate_trips_all: str = "",
    tier_coverage: str = TIER_COVERAGE_SINGLE_TIER_ONLY,
    unevaluable_rate: Optional[float] = None,
    incomplete_outcome_ratio: Optional[float] = None,
) -> ClassificationResult:
    return ClassificationResult(
        classification=classification,
        stage17_label_preserved=stage17_label_preserved,
        insufficient_sample_reason=insufficient_sample_reason,
        data_block_reason=data_block_reason,
        gate_trips_all=gate_trips_all,
        tier_coverage=tier_coverage,
        unevaluable_rate=unevaluable_rate,
        incomplete_outcome_ratio=incomplete_outcome_ratio,
    )


def _row(
    coarse: dict,
    result: ClassificationResult,
    *,
    headlines: tuple = (),
    unevaluable: tuple = (),
) -> ClassifiedRow:
    return ClassifiedRow(
        coarse_row=coarse,
        classification=result,
        headline_rows_for_slice=headlines,
        unevaluable_breakdown_for_rule=unevaluable,
    )


# ---------------------------------------------------------------------------
# classification_summary.csv
# ---------------------------------------------------------------------------


def test_classification_summary_emits_six_rows_in_severity_order(
    tmp_path: Path,
) -> None:
    """All six buckets always emit, in severity order, even with
    zero rows in every bucket."""

    out_path = tmp_path / "classification_summary.csv"
    n = write_classification_summary([], out_path)
    assert n == 6

    content = out_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == ",".join(CLASSIFICATION_SUMMARY_COLUMNS)
    actual_labels = [line.split(",")[0] for line in lines[1:]]
    assert actual_labels == list(SEVERITY_ORDER)

    for line in lines[1:]:
        cells = line.split(",")
        assert cells[1] == "0"
        assert cells[2] == "0"
        assert cells[3] == "0"


def test_classification_summary_counts_unique_rules_within_a_bucket(
    tmp_path: Path,
) -> None:
    """One rule across two windows in the same bucket:
    n_review_rows=2, n_unique_rules=1, n_policy_hashes=1."""

    rows = [
        _row(
            _coarse(policy_hash="ph_a", rule_id="rule_1", window_seconds=300),
            _result(classification=REVIEW_LABEL_PROMISING),
        ),
        _row(
            _coarse(policy_hash="ph_a", rule_id="rule_1", window_seconds=3600),
            _result(classification=REVIEW_LABEL_PROMISING),
        ),
    ]
    out_path = tmp_path / "classification_summary.csv"
    write_classification_summary(rows, out_path)

    lines = out_path.read_text(encoding="utf-8").splitlines()
    promising_line = next(
        line for line in lines[1:] if line.startswith(REVIEW_LABEL_PROMISING)
    )
    cells = promising_line.split(",")
    assert cells[1] == "2"
    assert cells[2] == "1"
    assert cells[3] == "1"


def test_classification_summary_counts_distinct_policy_hashes(
    tmp_path: Path,
) -> None:
    """Same rule on two policy_hashes, same bucket: n_policy_hashes=2."""

    rows = [
        _row(
            _coarse(policy_hash="ph_a", rule_id="rule_1"),
            _result(
                classification=REVIEW_LABEL_HARMFUL,
                stage17_label_preserved="HARMFUL",
            ),
        ),
        _row(
            _coarse(policy_hash="ph_b", rule_id="rule_1"),
            _result(
                classification=REVIEW_LABEL_HARMFUL,
                stage17_label_preserved="HARMFUL",
            ),
        ),
    ]
    out_path = tmp_path / "classification_summary.csv"
    write_classification_summary(rows, out_path)

    lines = out_path.read_text(encoding="utf-8").splitlines()
    harmful_line = next(
        line for line in lines[1:] if line.startswith(REVIEW_LABEL_HARMFUL)
    )
    cells = harmful_line.split(",")
    assert cells[1] == "2"
    assert cells[2] == "1"
    assert cells[3] == "2"


# ---------------------------------------------------------------------------
# review_matrix.csv
# ---------------------------------------------------------------------------


def test_review_matrix_emits_one_row_per_classified_input(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            _coarse(rule_id="rule_2", window_seconds=3600),
            _result(),
        ),
        _row(
            _coarse(rule_id="rule_1", window_seconds=300),
            _result(),
        ),
    ]
    out_path = tmp_path / "review_matrix.csv"
    n = write_review_matrix(rows, out_path)
    assert n == 2

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(REVIEW_MATRIX_COLUMNS)
    # Sort: rule_1 < rule_2.
    assert "rule_1" in lines[1]
    assert "rule_2" in lines[2]


def test_review_matrix_float_formatting_and_empty_for_none(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            _coarse(delta_hit_2x_rate="0.100000"),
            _result(
                unevaluable_rate=0.25,
                incomplete_outcome_ratio=None,
            ),
        ),
    ]
    out_path = tmp_path / "review_matrix.csv"
    write_review_matrix(rows, out_path)

    lines = out_path.read_text(encoding="utf-8").splitlines()
    columns = list(REVIEW_MATRIX_COLUMNS)
    cells = lines[1].split(",")
    uneval_idx = columns.index("unevaluable_rate")
    incomp_idx = columns.index("incomplete_outcome_ratio")
    delta_idx = columns.index("delta_hit_2x_rate")

    assert cells[uneval_idx] == "0.250000"
    assert cells[incomp_idx] == ""
    assert cells[delta_idx] == "0.100000"


def test_review_matrix_sort_uses_numeric_window_seconds(
    tmp_path: Path,
) -> None:
    """``window_seconds`` is a CSV string ('300', '3600', '14400');
    the sort must be numeric, not lexicographic."""

    rows = [
        _row(_coarse(window_seconds=14400), _result()),
        _row(_coarse(window_seconds=3600), _result()),
        _row(_coarse(window_seconds=300), _result()),
    ]
    write_review_matrix(rows, tmp_path / "review_matrix.csv")

    lines = (
        (tmp_path / "review_matrix.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    columns = list(REVIEW_MATRIX_COLUMNS)
    ws_idx = columns.index("window_seconds")
    assert lines[1].split(",")[ws_idx] == "300"
    assert lines[2].split(",")[ws_idx] == "3600"
    assert lines[3].split(",")[ws_idx] == "14400"


def test_review_matrix_header_only_on_empty_input(tmp_path: Path) -> None:
    out_path = tmp_path / "review_matrix.csv"
    n = write_review_matrix([], out_path)
    assert n == 0
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert lines[0] == ",".join(REVIEW_MATRIX_COLUMNS)


# ---------------------------------------------------------------------------
# data_quality_blockers.csv
# ---------------------------------------------------------------------------


def test_data_quality_blockers_excludes_sample_gate_rows(
    tmp_path: Path,
) -> None:
    """G1/G2/G3 rows are INSUFFICIENT_SAMPLE_REVIEW even when a
    data-quality gate also tripped (sample-gate precedence). They
    must not appear in data_quality_blockers."""

    rows = [
        _row(
            _coarse(rule_id="rule_a"),
            _result(
                classification=REVIEW_LABEL_INSUFFICIENT_SAMPLE,
                insufficient_sample_reason="G1",
                gate_trips_all="G1;G4",  # both fired
            ),
        ),
        _row(
            _coarse(rule_id="rule_b"),
            _result(
                classification=REVIEW_LABEL_DATA_BLOCKED,
                data_block_reason="G4",
                gate_trips_all="G4",
            ),
        ),
    ]
    out_path = tmp_path / "data_quality_blockers.csv"
    n = write_data_quality_blockers(rows, out_path)
    assert n == 1

    content = out_path.read_text(encoding="utf-8")
    assert "rule_b" in content
    assert "rule_a" not in content


def test_data_quality_blockers_header_only_when_no_blocks(
    tmp_path: Path,
) -> None:
    rows = [_row(_coarse(), _result(classification=REVIEW_LABEL_PROMISING))]
    out_path = tmp_path / "data_quality_blockers.csv"
    n = write_data_quality_blockers(rows, out_path)
    assert n == 0
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert lines[0] == ",".join(DATA_QUALITY_BLOCKERS_COLUMNS)


def test_data_quality_blockers_carries_subreason_for_g5(
    tmp_path: Path,
) -> None:
    """``data_block_reason`` may carry a colon-suffixed sub-reason
    such as ``G5:complete_outcome_zero``; the writer must propagate
    it verbatim."""

    rows = [
        _row(
            _coarse(),
            _result(
                classification=REVIEW_LABEL_DATA_BLOCKED,
                data_block_reason="G5:complete_outcome_zero",
                gate_trips_all="G5",
            ),
        ),
    ]
    out_path = tmp_path / "data_quality_blockers.csv"
    write_data_quality_blockers(rows, out_path)

    content = out_path.read_text(encoding="utf-8")
    assert "G5:complete_outcome_zero" in content


# ---------------------------------------------------------------------------
# rule_review_cards.md
# ---------------------------------------------------------------------------


def test_rule_review_cards_section_order_matches_severity(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards([], out_path, stage17_run_id="abc")

    content = out_path.read_text(encoding="utf-8")
    positions = []
    for label in SEVERITY_ORDER:
        header = f"## {label}"
        idx = content.find(header)
        assert idx >= 0, f"section {label!r} missing"
        positions.append(idx)
    assert positions == sorted(positions), (
        f"sections out of severity order: {positions}"
    )


def test_rule_review_cards_emits_placeholder_for_empty_buckets(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards([], out_path, stage17_run_id="r1")
    content = out_path.read_text(encoding="utf-8")
    assert content.count("(no rules in this bucket)") == 6


def test_rule_review_cards_renders_card_fields(tmp_path: Path) -> None:
    rows = [
        _row(
            _coarse(
                policy_hash="abcdef1234567890",
                rule_id="rule_x",
                window_label="1h",
                n_matched=40,
                descriptive_label="HARMFUL",
            ),
            _result(
                classification=REVIEW_LABEL_HARMFUL,
                stage17_label_preserved="HARMFUL",
                unevaluable_rate=0.05,
                tier_coverage=TIER_COVERAGE_SINGLE_TIER_ONLY,
            ),
        ),
    ]
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="run_id_xyz")

    content = out_path.read_text(encoding="utf-8")
    assert "### rule_x @ 1h (abcdef123456)" in content
    assert f"Classification: {REVIEW_LABEL_HARMFUL}" in content
    assert "Stage 17 original label: HARMFUL" in content
    assert "n_matched: 40" in content
    assert "unevaluable_rate: 0.050000" in content
    assert "Tier coverage: single_tier_only" in content
    assert "Source: Stage 17 run_id=run_id_xyz" in content


def test_rule_review_cards_multi_tier_renders_per_tier_table(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            _coarse(descriptive_label="MIXED_BY_TIER"),
            _result(
                classification=REVIEW_LABEL_MIXED_BY_TIER,
                stage17_label_preserved="MIXED_BY_TIER",
                tier_coverage=TIER_COVERAGE_MULTI_TIER,
            ),
            headlines=(
                {
                    "tier_name_snapshot": "T1",
                    "n_matched": "20",
                    "n_not_matched": "30",
                    "hit_2x_rate_matched": "0.200000",
                    "hit_2x_rate_not_matched": "0.100000",
                    "delta_hit_2x_rate": "0.100000",
                },
                {
                    "tier_name_snapshot": "T2",
                    "n_matched": "20",
                    "n_not_matched": "30",
                    "hit_2x_rate_matched": "0.100000",
                    "hit_2x_rate_not_matched": "0.150000",
                    "delta_hit_2x_rate": "-0.050000",
                },
            ),
        ),
    ]
    write_rule_review_cards(
        rows, tmp_path / "rule_review_cards.md", stage17_run_id="r1"
    )
    content = (tmp_path / "rule_review_cards.md").read_text(encoding="utf-8")
    assert "Per-tier evidence:" in content
    assert "| T1 |" in content
    assert "| T2 |" in content


def test_rule_review_cards_renders_data_block_reason_line(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            _coarse(),
            _result(
                classification=REVIEW_LABEL_DATA_BLOCKED,
                stage17_label_preserved="PROMISING",
                data_block_reason="G4",
                gate_trips_all="G4",
            ),
        ),
    ]
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="r1")
    content = out_path.read_text(encoding="utf-8")
    assert "data_block_reason: G4" in content


def test_rule_review_cards_renders_insufficient_sample_reason_line(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            _coarse(),
            _result(
                classification=REVIEW_LABEL_INSUFFICIENT_SAMPLE,
                stage17_label_preserved="PROMISING",
                insufficient_sample_reason="G1",
                gate_trips_all="G1",
            ),
        ),
    ]
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="r1")
    content = out_path.read_text(encoding="utf-8")
    assert "insufficient_sample_reason: G1" in content


def test_rule_review_cards_omits_insufficient_reason_for_stage17_label_path(
    tmp_path: Path,
) -> None:
    """When INSUFFICIENT_SAMPLE_REVIEW comes from the Stage 17
    label (no Stage 18 sample gate fired), no reason line is
    rendered."""

    rows = [
        _row(
            _coarse(descriptive_label="INSUFFICIENT_SAMPLE"),
            _result(
                classification=REVIEW_LABEL_INSUFFICIENT_SAMPLE,
                stage17_label_preserved="INSUFFICIENT_SAMPLE",
                insufficient_sample_reason="",
                gate_trips_all="",
            ),
        ),
    ]
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="r1")
    content = out_path.read_text(encoding="utf-8")
    assert "insufficient_sample_reason:" not in content


def test_rule_review_cards_file_ends_with_exactly_one_newline(
    tmp_path: Path,
) -> None:
    rows = [_row(_coarse(), _result())]
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="r1")
    content = out_path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert not content.endswith("\n\n")


# ---------------------------------------------------------------------------
# stage18_run.log
# ---------------------------------------------------------------------------


def test_log_writer_emits_step_lines_in_order(tmp_path: Path) -> None:
    events = [
        make_log_event("start"),
        make_log_event("classification_complete", harmful=2, promising=1),
        make_log_event("done"),
    ]
    out_path = tmp_path / "stage18_run.log"
    write_log(events, out_path)

    content = out_path.read_text(encoding="utf-8")
    assert content == (
        "step=start\n"
        "step=classification_complete harmful=2 promising=1\n"
        "step=done\n"
    )


def test_log_writer_empty_events_writes_empty_file(tmp_path: Path) -> None:
    out_path = tmp_path / "stage18_run.log"
    write_log([], out_path)
    content = out_path.read_text(encoding="utf-8")
    assert content == ""


def test_log_writer_contains_no_timestamps_or_floats(tmp_path: Path) -> None:
    """The log discipline forbids floats and ISO timestamps in
    field values. This test checks that a typical event sequence
    composed via ``make_log_event`` does not introduce either."""

    import re

    events = [
        make_log_event("inputs_loaded", headline=1, coarse=1),
        make_log_event("gates_evaluated", n_insufficient=0, n_blocked=0),
        make_log_event("review_matrix_written", rows=5),
    ]
    out_path = tmp_path / "stage18_run.log"
    write_log(events, out_path)
    content = out_path.read_text(encoding="utf-8")

    assert not re.search(r"\d{4}-\d{2}-\d{2}", content)
    # No floating-point numbers in the typical sequence.
    assert not re.search(r"\d+\.\d+", content)


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------


def test_readme_writer_is_byte_identical_across_two_runs(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a" / "README.md"
    b = tmp_path / "b" / "README.md"
    a.parent.mkdir()
    b.parent.mkdir()
    write_readme(a)
    write_readme(b)
    assert a.read_bytes() == b.read_bytes()


def test_readme_content_includes_required_sections(tmp_path: Path) -> None:
    out_path = tmp_path / "README.md"
    write_readme(out_path)
    content = out_path.read_text(encoding="utf-8")
    assert "What Stage 18 is" in content
    assert "Artifacts in this directory" in content
    assert "What each classification means" in content
    assert "What Stage 18 does NOT do" in content
    assert "Where the numbers come from" in content
    assert "Operator workflow" in content
    assert "observe-only" in content.lower()


def test_readme_content_has_no_run_specific_data(tmp_path: Path) -> None:
    """README is a static template; no run_id, no timestamp, no
    absolute path should appear."""

    import re

    out_path = tmp_path / "README.md"
    write_readme(out_path)
    content = out_path.read_text(encoding="utf-8")
    # No ISO timestamps.
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", content)
    # No 16-hex run ids embedded in body (very rough check).
    assert not re.search(r"run_id=[0-9a-f]{16}", content)


# ---------------------------------------------------------------------------
# Forbidden-language scan (audit remediation: Stage 18 artifacts
# must not surface action-oriented vocabulary)
# ---------------------------------------------------------------------------


# Case-insensitive regex patterns derived from the locked
# forbidden-terms list in the Stage 18 spec. Word-boundary anchors
# (``\b``) keep ``promote`` from matching e.g. ``promising`` while
# still catching exact-word occurrences in any case.
_FORBIDDEN_LANGUAGE_PATTERNS: tuple[str, ...] = (
    r"\bpromote\b",
    r"\bpromotion\b",
    r"\benforce\b",
    r"\benforcement\b",
    r"\bshould block\b",
    r"\bshould allow\b",
    r"\bcorrect block\b",
    r"\bcorrect allow\b",
    r"\btune to\b",
    r"\bready for production\b",
    r"\bapproved\b",
    r"\brejected\b",
)


def _assert_no_forbidden_language(content: str, source: str) -> None:
    """Assert that none of the locked forbidden audit patterns
    appear in ``content`` (case-insensitive)."""

    import re

    lower = content.lower()
    matched: list[str] = []
    for pattern in _FORBIDDEN_LANGUAGE_PATTERNS:
        if re.search(pattern, lower):
            matched.append(pattern)
    assert not matched, (
        f"{source} contains forbidden audit pattern(s): {matched!r}"
    )


def test_classification_explanations_contain_no_forbidden_language() -> None:
    """Every value in the in-memory bucket-explanation table must
    be free of forbidden audit vocabulary."""

    from PHX2.stage18.writers import _CLASSIFICATION_EXPLANATIONS

    for label, text in _CLASSIFICATION_EXPLANATIONS.items():
        _assert_no_forbidden_language(text, f"explanation[{label}]")


def test_readme_artifact_contains_no_forbidden_language(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "README.md"
    write_readme(out_path)
    _assert_no_forbidden_language(
        out_path.read_text(encoding="utf-8"), "README.md"
    )


def test_rule_review_cards_artifact_contains_no_forbidden_language(
    tmp_path: Path,
) -> None:
    """Build a card for every bucket so every explanation string is
    emitted into the rendered markdown, then scan the file."""

    rows = []
    bucket_setups = [
        (REVIEW_LABEL_PROMISING, "PROMISING", "", ""),
        (REVIEW_LABEL_WEAK, "WEAK", "", ""),
        (REVIEW_LABEL_HARMFUL, "HARMFUL", "", ""),
        (
            REVIEW_LABEL_MIXED_BY_TIER, "MIXED_BY_TIER", "", "",
        ),
        (
            REVIEW_LABEL_INSUFFICIENT_SAMPLE, "PROMISING",
            "G1", "",
        ),
        (
            REVIEW_LABEL_DATA_BLOCKED, "PROMISING",
            "", "G4",
        ),
    ]
    for idx, (cls, s17, isr, dbr) in enumerate(bucket_setups):
        rows.append(_row(
            _coarse(
                policy_hash=f"ph_{idx}aaaaaaaaaaaa",
                rule_id=f"rule_{idx}",
                descriptive_label=s17,
            ),
            _result(
                classification=cls,
                stage17_label_preserved=s17,
                insufficient_sample_reason=isr,
                data_block_reason=dbr,
                gate_trips_all=(isr or dbr),
            ),
        ))
    out_path = tmp_path / "rule_review_cards.md"
    write_rule_review_cards(rows, out_path, stage17_run_id="r1")
    _assert_no_forbidden_language(
        out_path.read_text(encoding="utf-8"), "rule_review_cards.md"
    )


def test_log_artifact_contains_no_forbidden_language(tmp_path: Path) -> None:
    """A realistic log event sequence must not contain forbidden
    audit vocabulary in any step name or field value."""

    events = [
        make_log_event("start"),
        make_log_event(
            "inputs_loaded",
            headline=1, coarse=1, unevaluable=0, data_quality=4,
        ),
        make_log_event(
            "classification_complete",
            harmful=1, promising=0, blocked=0,
            mixed=0, weak=0, insufficient=0,
        ),
        make_log_event("done"),
    ]
    out_path = tmp_path / "stage18_run.log"
    write_log(events, out_path)
    _assert_no_forbidden_language(
        out_path.read_text(encoding="utf-8"), "stage18_run.log"
    )
