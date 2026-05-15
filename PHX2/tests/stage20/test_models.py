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
    expected = {
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
    assert set(PreviewCandidate._fields) == expected


def test_decision_step_field_set():
    expected = {
        "candidate_id",
        "step_index",
        "step_name",
        "input_state",
        "output_state",
        "is_terminating",
        "reason_code",
    }
    assert set(DecisionStep._fields) == expected


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
