"""Tests for Stage 20 typed model shapes (20.1.A).

Covers the NamedTuple field sets and required-field behavior
for PreviewCandidate, DecisionStep, FilterResult, and RunManifest.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.models import (
    DecisionStep,
    FilterResult,
    PreviewCandidate,
    RunManifest,
)


def test_preview_candidate_construction_requires_all_fields():
    with pytest.raises(TypeError):
        PreviewCandidate()  # type: ignore[call-arg]


def test_preview_candidate_field_set():
    # Stage 20.2 extends PreviewCandidate additively (operator
    # decision: additive extension, no rename of 20.1 fields). The
    # expected set therefore covers BOTH the original 16 fields and
    # the 7 fields appended at 20.2.
    expected_stage20_1 = {
        "candidate_id",
        "stage18_run_id",
        "stage19_run_id",
        "policy_hash",
        "rule_id",
        "window_seconds",
        "operator_id",
        "review_sequence",
        "review_label",
        "review_timestamp_utc",
        "eligibility_state",
        "stage18_classification",
        "stage17_label_preserved",
        "safe_for_live_dispatch",
        "tier_hint",
        "reason_code",
    }
    expected_stage20_2_additive = {
        "stage20_run_id",
        "source_ledger_row_id",
        "mapping_version",
        "review_age_days",
        "review_stale",
        "multiple_operators_for_slice",
        "notes",
        # Phase B alias field (operator constraint #2): mirrors
        # ``eligibility_state`` so the 20.1 legacy field and the
        # 20.2-named CSV column field both exist on the model.
        "preview_state",
    }
    expected = expected_stage20_1 | expected_stage20_2_additive
    actual = set(PreviewCandidate._fields)
    # Original 20.1 fields must still be present (no rename).
    assert expected_stage20_1.issubset(actual), (
        f"20.1 fields lost: {expected_stage20_1 - actual}"
    )
    # Full 20.2 expected shape is the strict equality.
    assert actual == expected


def test_decision_step_field_set():
    # Stage 20.2 extends DecisionStep additively (operator decision:
    # additive extension, no rename of 20.1 fields). The CSV column
    # names (decision_step_index, decision_step_name, etc.) intentionally
    # differ from the 20.1 model field names (step_index, step_name,
    # ...); the locked column tuple performs the translation at write
    # time so the 20.1 model fields remain unchanged.
    expected_stage20_1 = {
        "candidate_id",
        "step_index",
        "step_name",
        "input_state",
        "output_state",
        "is_terminating",
        "reason_code",
    }
    expected_stage20_2_additive = {
        "decision_id",
        "stage20_run_id",
        "decision_step_state",
        "decision_outcome",
        "evidence_code",
        "evidence_detail",
        # Phase B alias fields (operator constraint #3): each pairs
        # with its 20.1 counterpart and ``build_decision_sequence``
        # populates them with identical values.
        "decision_step_index",
        "decision_step_name",
        "decision_step_terminating",
    }
    expected = expected_stage20_1 | expected_stage20_2_additive
    actual = set(DecisionStep._fields)
    assert expected_stage20_1.issubset(actual), (
        f"20.1 fields lost: {expected_stage20_1 - actual}"
    )
    assert actual == expected


def test_filter_result_field_set():
    expected = {
        "candidate_id",
        "filter_name",
        "filter_version",
        "filter_mode",
        "ordering_index",
        "pass_through",
        "reason_code",
    }
    assert set(FilterResult._fields) == expected


def test_run_manifest_field_set():
    expected = {
        "stage20_run_id",
        "stage20_version",
        "consumer_contract_version",
        "mapping_version",
        "run_timestamp_utc",
        "stage18_input_dir",
        "stage18_run_id",
        "stage18_manifest_sha256",
        "stage18_review_matrix_sha256",
        "stage19_input_dir",
        "stage19_run_id",
        "stage19_ledger_sha256",
        "candidate_count",
        "preview_eligible_count",
        "safe_for_live_dispatch",
        "git_commit",
    }
    assert set(RunManifest._fields) == expected
