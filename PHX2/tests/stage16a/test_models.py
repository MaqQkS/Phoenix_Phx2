"""Phase 3: frozen dataclasses, Literal defaults, and roundtrip construction."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from PHX2.stage16a.models import (
    DecisionContext,
    FilterEvaluationSnapshot,
    LoadedObserveOnlyPolicy,
    LoadedRule,
    ObserveOnlyEvaluationResult,
    RuleMatch,
    RuleUnevaluable,
)


# ---------------------------------------------------------------------------
# Builders for use in tests
# ---------------------------------------------------------------------------


def _rule(**overrides) -> LoadedRule:
    base = dict(
        rule_id="rule_x",
        tier_scope="T1",
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        filter_label="NORMAL",
        threshold_version="thresholds_v0_observe_only",
    )
    base.update(overrides)
    return LoadedRule(**base)


def _policy(**overrides) -> LoadedObserveOnlyPolicy:
    base = dict(
        schema_version="observe_only_runtime_policy_v0",
        policy_hash="sha256:" + "0" * 64,
        generated_at_utc="2026-05-13T00:00:00+00:00",
        git_commit="deadbeefcafef00d",
        rules=(),
        lineage=MappingProxyType({}),
    )
    base.update(overrides)
    return LoadedObserveOnlyPolicy(**base)


def _snapshot(**overrides) -> FilterEvaluationSnapshot:
    base = dict(
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        label="NORMAL",
        threshold_version="thresholds_v0_observe_only",
    )
    base.update(overrides)
    return FilterEvaluationSnapshot(**base)


def _context(**overrides) -> DecisionContext:
    base = dict(
        alert_decision_id=1,
        tier_name="T1",
        filter_evaluations=(),
    )
    base.update(overrides)
    return DecisionContext(**base)


def _match(**overrides) -> RuleMatch:
    base = dict(
        rule_id="rule_x",
        matched_filter_evaluation_index=0,
        predicate_snapshot=MappingProxyType({}),
    )
    base.update(overrides)
    return RuleMatch(**base)


def _unevaluable(**overrides) -> RuleUnevaluable:
    base = dict(
        rule_id="rule_x",
        reason="tier_name_missing_on_decision",
    )
    base.update(overrides)
    return RuleUnevaluable(**base)


def _result(**overrides) -> ObserveOnlyEvaluationResult:
    base = dict(
        alert_decision_id=1,
        policy_hash="sha256:" + "0" * 64,
        matched_rules=(),
        unevaluable_rules=(),
    )
    base.update(overrides)
    return ObserveOnlyEvaluationResult(**base)


# ---------------------------------------------------------------------------
# Frozen behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory,attr,value",
    [
        (_rule, "rule_id", "other"),
        (_rule, "tier_scope", "T2"),
        (_rule, "filter_label", "ELEVATED"),
        (_policy, "policy_hash", "sha256:other"),
        (_snapshot, "label", "ELEVATED"),
        (_context, "alert_decision_id", 999),
        (_match, "matched_filter_evaluation_index", 5),
        (_unevaluable, "reason", "other"),
        (_result, "alert_decision_id", 999),
    ],
)
def test_dataclass_is_frozen(factory, attr, value) -> None:
    instance = factory()
    with pytest.raises(FrozenInstanceError):
        setattr(instance, attr, value)


# ---------------------------------------------------------------------------
# Literal defaults: the safety-critical fields hold the locked constants
# ---------------------------------------------------------------------------


def test_loaded_rule_literal_defaults() -> None:
    r = _rule()
    assert r.intended_action == "LOG_WOULD_BLOCK"
    assert r.hard_block_allowed is False


def test_observe_only_evaluation_result_literal_defaults() -> None:
    result = _result()
    assert result.enforcement_effect == "NONE"
    assert result.dispatch_allowed is True
    assert result.live_decision_mutated is False


def test_loaded_policy_schema_version_default_can_only_be_observe_only() -> None:
    """Constructing with the locked schema_version succeeds; the runtime
    loader's R02 check rejects any other value, but the dataclass itself
    accepts the Literal value at runtime (Python doesn't enforce Literal
    at runtime; the loader does)."""

    p = _policy()
    assert p.schema_version == "observe_only_runtime_policy_v0"


# ---------------------------------------------------------------------------
# Construction roundtrip
# ---------------------------------------------------------------------------


def test_loaded_rule_carries_all_fields_through_construction() -> None:
    r = _rule(
        rule_id="rule_xyz",
        tier_scope="T2",
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        filter_label="SCAM_LIKELY",
        threshold_version="thresholds_v0_observe_only",
        source_stage14_rule_hash="sha256:abcd",
        operator_reason="observe-only review",
        reviewed_at_utc="2026-05-12T12:00:00+00:00",
    )
    assert r.rule_id == "rule_xyz"
    assert r.tier_scope == "T2"
    assert r.filter_label == "SCAM_LIKELY"
    assert r.source_stage14_rule_hash == "sha256:abcd"
    assert r.operator_reason == "observe-only review"
    assert r.reviewed_at_utc == "2026-05-12T12:00:00+00:00"
    assert r.intended_action == "LOG_WOULD_BLOCK"
    assert r.hard_block_allowed is False


def test_loaded_policy_holds_rules_tuple_and_lineage() -> None:
    rules = (_rule(rule_id="a"), _rule(rule_id="b"))
    lineage = MappingProxyType({
        "source_stage15_manifest_hash": "sha256:11",
        "source_stage14_manifest_hash": "sha256:22",
    })
    p = _policy(rules=rules, lineage=lineage)
    assert p.rules == rules
    assert dict(p.lineage) == dict(lineage)
    assert len(p.rules) == 2


def test_decision_context_tier_name_none_is_valid() -> None:
    c = _context(tier_name=None)
    assert c.tier_name is None


def test_decision_context_evaluated_at_utc_default_is_none() -> None:
    c = _context()
    assert c.evaluated_at_utc is None


def test_filter_evaluation_snapshot_fields() -> None:
    s = _snapshot(label="ELEVATED")
    assert s.label == "ELEVATED"
    assert s.filter_name == "fee_gate"


def test_rule_match_carries_index_and_snapshot() -> None:
    snap = MappingProxyType({"tier_scope": "T2"})
    m = _match(matched_filter_evaluation_index=3, predicate_snapshot=snap)
    assert m.matched_filter_evaluation_index == 3
    assert dict(m.predicate_snapshot) == {"tier_scope": "T2"}


def test_rule_unevaluable_carries_reason() -> None:
    u = _unevaluable(reason="tier_name_missing_on_decision")
    assert u.reason == "tier_name_missing_on_decision"


def test_evaluation_result_carries_match_and_unevaluable_tuples() -> None:
    matches = (_match(rule_id="a"), _match(rule_id="b"))
    unevs = (_unevaluable(rule_id="c"),)
    r = _result(matched_rules=matches, unevaluable_rules=unevs)
    assert r.matched_rules == matches
    assert r.unevaluable_rules == unevs
    assert r.enforcement_effect == "NONE"
    assert r.dispatch_allowed is True
    assert r.live_decision_mutated is False


# ---------------------------------------------------------------------------
# Equality / hashability (frozen dataclasses get __hash__ for free)
# ---------------------------------------------------------------------------


def test_loaded_rule_equality_by_value() -> None:
    a = _rule()
    b = _rule()
    assert a == b


def test_filter_evaluation_snapshot_is_hashable() -> None:
    s = _snapshot()
    # Hashable because dataclass(frozen=True) generates __hash__.
    assert isinstance(hash(s), int)
