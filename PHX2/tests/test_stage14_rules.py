"""Stage 14 rule translation tests.

Covers:
  * Eligibility gate routes each non-eligible row to the right
    locked exclusion reason.
  * Eligible rows mint content-stable rule IDs that survive
    insertion of new candidates and row reordering.
  * Duplicate eligible rows collapse to one rule with both source
    cohort_ids preserved.
  * Every input row is accounted for (rules' source_row_count sum +
    excluded count == input row count).
"""

from __future__ import annotations

import pytest

from PHX2.stage14.rules import (
    compute_rule_id,
    translate_recommendations,
)
from PHX2.stage14.types import (
    EXCLUSION_MISSING_FILTER_IDENTITY,
    EXCLUSION_NOT_ADVANCE_CANDIDATE,
    EXCLUSION_NOT_FILTER_LABEL_SURFACE,
    EXCLUSION_NOT_TIGHTEN,
    EXCLUSION_TIER_SCOPE_OVERALL,
)


def _row(**overrides: object) -> dict[str, str]:
    """Helper to build a candidate-row dict.

    Defaults to a v0-eligible row; tests flip specific fields.
    """

    base: dict[str, str] = {
        "policy_surface": "filter_label_blocking",
        "cohort_id": "fee_gate_v1@v1[threshold=v1]:scam_likely",
        "filter_name": "fee_gate_v1",
        "filter_version": "v1",
        "filter_label": "scam_likely",
        "threshold_version": "v1",
        "tier_scope": "T1",
        "action_class": "ADVANCE_AS_CANDIDATE",
        "direction": "tighten",
        "evidence_class": "strong",
        "policy_severity": "unknown",
        "review_priority": "urgent",
        "n_complete": "50",
        "n_censored": "5",
        "cohort_rate": "0.050",
        "baseline_rate": "0.200",
        "lift_absolute": "-0.150",
        "lift_relative": "-0.750",
        "wilson_ci_low": "0.020",
        "wilson_ci_high": "0.100",
        "ci_excludes_baseline": "true",
        "censoring_rate": "0.100",
        "censoring_warning_flag": "false",
        "watchlist_flag": "true",
        "tier_evidence_support": "",
        "cross_tier_disagreement": "false",
        "loosen_capped_flag": "false",
        "confidence_ceiling_applied": "false",
        "notes": "",
    }
    for k, v in overrides.items():
        base[k] = str(v) if not isinstance(v, str) else v
    return base


def test_eligible_row_becomes_one_rule() -> None:
    rules, excluded = translate_recommendations([_row()])
    assert len(rules) == 1
    assert len(excluded) == 0
    rule = rules[0]
    assert rule.simulated_action == "SIMULATED_BLOCK"
    assert rule.direction == "tighten"
    assert rule.policy_surface == "filter_label_blocking"
    assert rule.tier_scope == "T1"
    assert rule.filter_name == "fee_gate_v1"
    assert rule.source_row_count == 1


def test_rule_id_is_content_stable() -> None:
    rules1, _ = translate_recommendations([_row()])
    rules2, _ = translate_recommendations([_row()])
    assert rules1[0].rule_id == rules2[0].rule_id


def test_rule_id_survives_insertion_of_other_candidates() -> None:
    """Inserting a different eligible candidate before an existing one
    must not change the existing rule's ID."""

    other = _row(
        cohort_id="filter_b@v1[threshold=v1]:other",
        filter_name="filter_b",
        filter_label="other",
        tier_scope="T2",
    )

    rules_alone, _ = translate_recommendations([_row()])
    rules_with_other, _ = translate_recommendations([other, _row()])

    by_id = {r.tier_scope: r.rule_id for r in rules_with_other}
    assert by_id["T1"] == rules_alone[0].rule_id


def test_rule_id_distinguishes_tiers() -> None:
    rules, _ = translate_recommendations(
        [_row(tier_scope="T1"), _row(tier_scope="T2")]
    )
    assert len({r.rule_id for r in rules}) == 2


def test_rule_id_distinguishes_filter_versions() -> None:
    rules, _ = translate_recommendations(
        [
            _row(filter_version="v1"),
            _row(filter_version="v2"),
        ]
    )
    assert len({r.rule_id for r in rules}) == 2


def test_duplicate_eligible_rows_collapse_to_one_rule() -> None:
    """Two Stage 13 rows with the same content identity must collapse
    to one rule, with both source cohort_ids preserved."""

    duplicate = _row(cohort_id="alternate_cohort_id_label")
    rules, excluded = translate_recommendations([_row(), duplicate])
    assert len(rules) == 1
    assert len(excluded) == 0
    rule = rules[0]
    assert rule.source_row_count == 2
    cohort_ids = [s.cohort_id for s in rule.source_recommendations]
    assert sorted(cohort_ids) == cohort_ids
    assert "alternate_cohort_id_label" in cohort_ids


def test_excludes_non_filter_label_surface() -> None:
    _, excluded = translate_recommendations(
        [_row(policy_surface="primitive_bucket_cohort")]
    )
    assert [e.exclusion_reason for e in excluded] == [
        EXCLUSION_NOT_FILTER_LABEL_SURFACE
    ]


def test_excludes_non_advance_candidate() -> None:
    _, excluded = translate_recommendations(
        [_row(action_class="HOLD_OBSERVE_ONLY")]
    )
    assert [e.exclusion_reason for e in excluded] == [
        EXCLUSION_NOT_ADVANCE_CANDIDATE
    ]


def test_excludes_anomaly_flag() -> None:
    _, excluded = translate_recommendations(
        [_row(action_class="ANOMALY_FLAG")]
    )
    assert excluded[0].exclusion_reason == EXCLUSION_NOT_ADVANCE_CANDIDATE


def test_excludes_no_signal_found() -> None:
    _, excluded = translate_recommendations(
        [_row(action_class="NO_SIGNAL_FOUND")]
    )
    assert excluded[0].exclusion_reason == EXCLUSION_NOT_ADVANCE_CANDIDATE


def test_excludes_insufficient_evidence() -> None:
    """Stage 13's writer normally keeps INSUFFICIENT_EVIDENCE rows
    out of candidate_recommendations.csv (they live in
    insufficient_evidence_cohorts.csv), but if one does leak through
    Stage 14's gate must still reject it with the not-advance reason
    rather than translate a weakly-supported rule.
    """

    _, excluded = translate_recommendations(
        [_row(action_class="INSUFFICIENT_EVIDENCE", evidence_class="insufficient")]
    )
    assert excluded[0].exclusion_reason == EXCLUSION_NOT_ADVANCE_CANDIDATE


def test_excludes_loosen_direction() -> None:
    _, excluded = translate_recommendations([_row(direction="loosen")])
    assert excluded[0].exclusion_reason == EXCLUSION_NOT_TIGHTEN


def test_excludes_overall_tier_scope() -> None:
    _, excluded = translate_recommendations([_row(tier_scope="overall")])
    assert excluded[0].exclusion_reason == EXCLUSION_TIER_SCOPE_OVERALL


def test_excludes_missing_filter_name() -> None:
    _, excluded = translate_recommendations([_row(filter_name="")])
    assert excluded[0].exclusion_reason == EXCLUSION_MISSING_FILTER_IDENTITY


def test_excludes_missing_threshold_version() -> None:
    _, excluded = translate_recommendations([_row(threshold_version="")])
    assert excluded[0].exclusion_reason == EXCLUSION_MISSING_FILTER_IDENTITY


def test_excludes_missing_filter_label() -> None:
    _, excluded = translate_recommendations([_row(filter_label="")])
    assert excluded[0].exclusion_reason == EXCLUSION_MISSING_FILTER_IDENTITY


def test_excludes_missing_filter_version() -> None:
    _, excluded = translate_recommendations([_row(filter_version="")])
    assert excluded[0].exclusion_reason == EXCLUSION_MISSING_FILTER_IDENTITY


def test_gate_order_surface_before_action() -> None:
    """A primitive_bucket_cohort row that ALSO has a non-eligible
    action_class fails on the surface check first (gate order)."""

    _, excluded = translate_recommendations(
        [
            _row(
                policy_surface="primitive_bucket_cohort",
                action_class="HOLD_OBSERVE_ONLY",
            )
        ]
    )
    assert excluded[0].exclusion_reason == EXCLUSION_NOT_FILTER_LABEL_SURFACE


def test_every_input_row_accounted_for() -> None:
    """Sum of rule source_row_counts + excluded rows == input count."""

    rows = [
        _row(),  # eligible
        _row(action_class="HOLD_OBSERVE_ONLY"),  # excluded
        _row(tier_scope="overall"),  # excluded
        _row(direction="loosen"),  # excluded
        _row(filter_name=""),  # excluded
        _row(tier_scope="T2"),  # eligible, distinct rule
        _row(tier_scope="T2"),  # eligible, collapses with prior T2
    ]
    rules, excluded = translate_recommendations(rows)
    source_total = sum(r.source_row_count for r in rules)
    assert source_total + len(excluded) == len(rows)


def test_rules_sorted_by_rule_id() -> None:
    rows = [
        _row(tier_scope="T3"),
        _row(tier_scope="T1"),
        _row(tier_scope="T2"),
    ]
    rules, _ = translate_recommendations(rows)
    assert [r.rule_id for r in rules] == sorted(r.rule_id for r in rules)


def test_compute_rule_id_format() -> None:
    rid = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
    )
    assert rid.startswith("shadow_rule_")
    assert len(rid) == len("shadow_rule_") + 12


def test_compute_rule_id_differs_on_each_input_change() -> None:
    base_kwargs = dict(
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
    )
    base = compute_rule_id(**base_kwargs)
    for change_key in (
        "policy_surface",
        "tier_scope",
        "filter_name",
        "filter_version",
        "filter_label",
        "threshold_version",
        "simulated_action",
    ):
        mutated = dict(base_kwargs)
        mutated[change_key] = mutated[change_key] + "_modified"
        assert compute_rule_id(**mutated) != base, change_key
