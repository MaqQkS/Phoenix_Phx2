"""Phase 7: ObserveOnlyPolicyEvaluator matching semantics."""

from __future__ import annotations

from types import MappingProxyType

from PHX2.stage16a.models import (
    DecisionContext,
    FilterEvaluationSnapshot,
    LoadedObserveOnlyPolicy,
    LoadedRule,
    ObserveOnlyEvaluationResult,
)
from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator


POLICY_HASH = "sha256:" + "9" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(**overrides) -> LoadedRule:
    base = dict(
        rule_id="rule_t2_fee_gate_scam",
        tier_scope="T2",
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        filter_label="SCAM_LIKELY",
        threshold_version="thresholds_v0_observe_only",
    )
    base.update(overrides)
    return LoadedRule(**base)


def _policy(*rules: LoadedRule) -> LoadedObserveOnlyPolicy:
    return LoadedObserveOnlyPolicy(
        schema_version="observe_only_runtime_policy_v0",
        policy_hash=POLICY_HASH,
        generated_at_utc="2026-05-13T12:00:00+00:00",
        git_commit="cafebabe",
        rules=rules,
        lineage=MappingProxyType({}),
    )


def _snapshot(**overrides) -> FilterEvaluationSnapshot:
    base = dict(
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        label="SCAM_LIKELY",
        threshold_version="thresholds_v0_observe_only",
    )
    base.update(overrides)
    return FilterEvaluationSnapshot(**base)


def _context(
    *snapshots: FilterEvaluationSnapshot,
    alert_decision_id: int = 7,
    tier_name: str | None = "T2",
) -> DecisionContext:
    return DecisionContext(
        alert_decision_id=alert_decision_id,
        tier_name=tier_name,
        filter_evaluations=snapshots,
    )


def _evaluate(policy: LoadedObserveOnlyPolicy, context: DecisionContext) -> ObserveOnlyEvaluationResult:
    return ObserveOnlyPolicyEvaluator(policy).evaluate_for_decision(context)


# ---------------------------------------------------------------------------
# Single-rule matching
# ---------------------------------------------------------------------------


def test_single_rule_exact_match_produces_one_match() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot()))
    assert len(result.matched_rules) == 1
    assert len(result.unevaluable_rules) == 0
    assert result.matched_rules[0].rule_id == "rule_t2_fee_gate_scam"
    assert result.matched_rules[0].matched_filter_evaluation_index == 0


def test_tier_mismatch_produces_no_match() -> None:
    result = _evaluate(
        _policy(_rule(tier_scope="T1")),
        _context(_snapshot(), tier_name="T2"),
    )
    assert result.matched_rules == ()
    assert result.unevaluable_rules == ()


def test_filter_name_mismatch_produces_no_match() -> None:
    result = _evaluate(
        _policy(_rule()),
        _context(_snapshot(filter_name="other_filter")),
    )
    assert result.matched_rules == ()


def test_filter_version_mismatch_produces_no_match() -> None:
    result = _evaluate(
        _policy(_rule()),
        _context(_snapshot(filter_version="fee_gate_v2")),
    )
    assert result.matched_rules == ()


def test_filter_label_mismatch_produces_no_match() -> None:
    result = _evaluate(
        _policy(_rule(filter_label="ELEVATED")),
        _context(_snapshot(label="SCAM_LIKELY")),
    )
    assert result.matched_rules == ()


def test_threshold_version_mismatch_produces_no_match() -> None:
    result = _evaluate(
        _policy(_rule()),
        _context(_snapshot(threshold_version="thresholds_v1")),
    )
    assert result.matched_rules == ()


# ---------------------------------------------------------------------------
# Casing / normalization
# ---------------------------------------------------------------------------


def test_casing_mismatch_produces_no_match() -> None:
    """No case normalization. ``scam_likely`` (lowercase) does NOT match
    ``SCAM_LIKELY`` (uppercase) -- the rule's UPPERCASE_SNAKE label is
    treated as an exact string."""

    result = _evaluate(
        _policy(_rule(filter_label="SCAM_LIKELY")),
        _context(_snapshot(label="scam_likely")),
    )
    assert result.matched_rules == ()


def test_whitespace_not_trimmed() -> None:
    result = _evaluate(
        _policy(_rule(filter_label="SCAM_LIKELY")),
        _context(_snapshot(label=" SCAM_LIKELY ")),
    )
    assert result.matched_rules == ()


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


def test_empty_filter_evaluations_produces_empty_matches() -> None:
    result = _evaluate(_policy(_rule()), _context())
    assert result.matched_rules == ()
    assert result.unevaluable_rules == ()
    assert result.alert_decision_id == 7
    assert result.policy_hash == POLICY_HASH


def test_empty_policy_rules_produces_empty_result() -> None:
    empty_policy = _policy()
    result = _evaluate(empty_policy, _context(_snapshot()))
    assert result.matched_rules == ()
    assert result.unevaluable_rules == ()


# ---------------------------------------------------------------------------
# tier_name=None
# ---------------------------------------------------------------------------


def test_tier_name_none_marks_every_rule_unevaluable() -> None:
    r1 = _rule(rule_id="r1")
    r2 = _rule(rule_id="r2", tier_scope="T1")
    r3 = _rule(rule_id="r3", tier_scope="T3")
    result = _evaluate(_policy(r1, r2, r3), _context(_snapshot(), tier_name=None))
    assert result.matched_rules == ()
    assert len(result.unevaluable_rules) == 3
    assert {u.rule_id for u in result.unevaluable_rules} == {"r1", "r2", "r3"}
    for u in result.unevaluable_rules:
        assert u.reason == "tier_name_missing_on_decision"


def test_tier_name_none_with_empty_filter_evaluations_still_marks_unevaluable() -> None:
    result = _evaluate(_policy(_rule()), _context(tier_name=None))
    assert len(result.unevaluable_rules) == 1


# ---------------------------------------------------------------------------
# Multi-rule + multi-filter
# ---------------------------------------------------------------------------


def test_multi_rule_multi_filter_evaluation_only_matches_intersections() -> None:
    rules = (
        _rule(rule_id="r_t2_scam", filter_label="SCAM_LIKELY"),
        _rule(rule_id="r_t1_normal", tier_scope="T1", filter_label="NORMAL"),
        _rule(rule_id="r_t2_elevated", filter_label="ELEVATED"),
    )
    snapshots = (
        _snapshot(label="SCAM_LIKELY"),
        _snapshot(label="ELEVATED"),
    )
    result = _evaluate(_policy(*rules), _context(*snapshots, tier_name="T2"))
    matched_ids = {m.rule_id for m in result.matched_rules}
    # T2 + SCAM_LIKELY -> matches snapshot index 0
    # T2 + ELEVATED -> matches snapshot index 1
    # T1 + NORMAL -> tier mismatch, no match
    assert matched_ids == {"r_t2_scam", "r_t2_elevated"}


def test_rule_matches_first_filter_evaluation_only() -> None:
    """At most one match per rule per decision. If filter_evaluations
    contains the same (filter_name, version, label, threshold_version)
    twice, only the first is matched."""

    rule = _rule()
    snap = _snapshot()
    result = _evaluate(_policy(rule), _context(snap, snap))
    assert len(result.matched_rules) == 1
    assert result.matched_rules[0].matched_filter_evaluation_index == 0


def test_each_rule_independently_matches() -> None:
    """Two rules that share the same predicate (legal at the model level
    even though the runtime loader's R08 forbids duplicate tuples) would
    each produce a match. We test with distinct predicates here so the
    loaded policy is well-formed."""

    rule_a = _rule(rule_id="a", filter_label="SCAM_LIKELY")
    rule_b = _rule(rule_id="b", filter_label="ELEVATED")
    snap_a = _snapshot(label="SCAM_LIKELY")
    snap_b = _snapshot(label="ELEVATED")
    result = _evaluate(_policy(rule_a, rule_b), _context(snap_a, snap_b))
    assert {m.rule_id for m in result.matched_rules} == {"a", "b"}


# ---------------------------------------------------------------------------
# Locked result fields (observe-only invariants)
# ---------------------------------------------------------------------------


def test_result_enforcement_effect_is_always_none() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot()))
    assert result.enforcement_effect == "NONE"


def test_result_dispatch_allowed_is_always_true() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot()))
    assert result.dispatch_allowed is True


def test_result_live_decision_mutated_is_always_false() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot()))
    assert result.live_decision_mutated is False


def test_result_policy_hash_matches_loaded_policy() -> None:
    policy = _policy(_rule())
    result = _evaluate(policy, _context(_snapshot()))
    assert result.policy_hash == policy.policy_hash


def test_result_alert_decision_id_passes_through() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot(), alert_decision_id=12345))
    assert result.alert_decision_id == 12345


# ---------------------------------------------------------------------------
# Predicate snapshot in RuleMatch
# ---------------------------------------------------------------------------


def test_rule_match_predicate_snapshot_carries_5_keys() -> None:
    result = _evaluate(_policy(_rule()), _context(_snapshot()))
    snap = result.matched_rules[0].predicate_snapshot
    assert set(snap.keys()) == {
        "tier_scope",
        "filter_name",
        "filter_version",
        "filter_label",
        "threshold_version",
    }
    assert snap["tier_scope"] == "T2"
    assert snap["filter_label"] == "SCAM_LIKELY"
