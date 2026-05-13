"""Phase 7: structural purity tests on ObserveOnlyPolicyEvaluator.

Two angles:

* Random-context fuzz: run the evaluator 1000 times with random inputs
  and verify the working directory is untouched, no exceptions escape,
  and result invariants always hold.

* Method-name shape: the evaluator class must NOT expose any method whose
  name contains write / insert / update / delete / send / dispatch /
  block / enforce / commit / save. If a future regression added such a
  method (even harmlessly) this test would catch the structural drift.
"""

from __future__ import annotations

import random
from pathlib import Path
from types import MappingProxyType

import pytest

from PHX2.stage16a.models import (
    DecisionContext,
    FilterEvaluationSnapshot,
    LoadedObserveOnlyPolicy,
    LoadedRule,
)
from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator


TIERS = ("T1", "T2", "T3")
LABELS = ("NORMAL", "ELEVATED", "SUSPICIOUS", "SCAM_LIKELY", "UNKNOWN")
FILTER_NAMES = ("fee_gate", "ghost_filter", "ante_filter")
FILTER_VERSIONS = ("v1", "v2_no_bribes", "v3_strict")
THRESHOLDS = ("thresholds_v0", "thresholds_v1")


def _random_rule(rng: random.Random) -> LoadedRule:
    return LoadedRule(
        rule_id=f"rule_{rng.randrange(10_000):05d}",
        tier_scope=rng.choice(TIERS),
        filter_name=rng.choice(FILTER_NAMES),
        filter_version=rng.choice(FILTER_VERSIONS),
        filter_label=rng.choice(LABELS),
        threshold_version=rng.choice(THRESHOLDS),
    )


def _random_snapshot(rng: random.Random) -> FilterEvaluationSnapshot:
    return FilterEvaluationSnapshot(
        filter_name=rng.choice(FILTER_NAMES),
        filter_version=rng.choice(FILTER_VERSIONS),
        label=rng.choice(LABELS),
        threshold_version=rng.choice(THRESHOLDS),
    )


def _random_context(rng: random.Random, decision_id: int) -> DecisionContext:
    n = rng.randrange(0, 6)
    return DecisionContext(
        alert_decision_id=decision_id,
        tier_name=rng.choice(TIERS + (None,)),
        filter_evaluations=tuple(_random_snapshot(rng) for _ in range(n)),
    )


def _random_policy(rng: random.Random, rule_count: int) -> LoadedObserveOnlyPolicy:
    # Generate unique rules so the policy is well-formed at the loader's
    # R08 level even though the evaluator itself doesn't enforce that.
    seen: set[tuple] = set()
    rules: list[LoadedRule] = []
    seen_rule_ids: set[str] = set()
    while len(rules) < rule_count:
        r = _random_rule(rng)
        key = (r.tier_scope, r.filter_name, r.filter_version, r.filter_label, r.threshold_version)
        if key in seen or r.rule_id in seen_rule_ids:
            continue
        seen.add(key)
        seen_rule_ids.add(r.rule_id)
        rules.append(r)
    return LoadedObserveOnlyPolicy(
        schema_version="observe_only_runtime_policy_v0",
        policy_hash="sha256:" + "8" * 64,
        generated_at_utc="2026-05-13T12:00:00+00:00",
        git_commit="0" * 40,
        rules=tuple(rules),
        lineage=MappingProxyType({}),
    )


def test_evaluator_1000_random_contexts_leave_tmp_path_untouched(
    tmp_path: Path,
) -> None:
    """Run the evaluator 1000 times with random contexts and assert
    nothing was written under ``tmp_path``."""

    rng = random.Random(42)
    policy = _random_policy(rng, rule_count=20)
    evaluator = ObserveOnlyPolicyEvaluator(policy)

    for i in range(1000):
        context = _random_context(rng, decision_id=i)
        result = evaluator.evaluate_for_decision(context)
        # Hard invariants on every result.
        assert result.enforcement_effect == "NONE"
        assert result.dispatch_allowed is True
        assert result.live_decision_mutated is False
        assert result.policy_hash == policy.policy_hash
        assert result.alert_decision_id == i
        # Matched/unevaluable always tuples.
        assert isinstance(result.matched_rules, tuple)
        assert isinstance(result.unevaluable_rules, tuple)

    # tmp_path is the test's own scratch dir. The evaluator should never
    # write anything anywhere; we assert no entries appeared under
    # tmp_path during the loop. (pytest's tmp_path is pre-created and
    # empty when the test starts.)
    assert list(tmp_path.iterdir()) == [], (
        f"tmp_path is not empty: {list(tmp_path.iterdir())!r}"
    )


def test_evaluator_class_exposes_no_mutation_named_methods() -> None:
    """No method (public or private) on the evaluator class may carry a
    name containing any of these tokens. The list is conservative -- if
    a future change really does need such a method, this test must be
    updated AND the change reviewed for observe-only safety."""

    forbidden_tokens = (
        "write",
        "insert",
        "update",
        "delete",
        "send",
        "dispatch",
        "block",
        "enforce",
        "commit",
        "save",
    )
    for attr_name in dir(ObserveOnlyPolicyEvaluator):
        if attr_name.startswith("__") and attr_name.endswith("__"):
            continue
        lowered = attr_name.lower()
        for token in forbidden_tokens:
            assert token not in lowered, (
                f"ObserveOnlyPolicyEvaluator.{attr_name} contains forbidden "
                f"token {token!r}"
            )


def test_evaluator_module_exposes_no_forbidden_top_level_names() -> None:
    """Same check at the module level (no helper functions named
    ``write_*`` / ``dispatch_*`` / etc.)."""

    import PHX2.stage16a.observe_only_policy_evaluator as evaluator_module

    forbidden_tokens = (
        "write",
        "insert",
        "update",
        "delete",
        "send",
        "dispatch",
        "block",
        "enforce",
        "commit",
        "save",
    )
    for name in dir(evaluator_module):
        if name.startswith("__") and name.endswith("__"):
            continue
        lowered = name.lower()
        for token in forbidden_tokens:
            assert token not in lowered, (
                f"observe_only_policy_evaluator module exposes name "
                f"{name!r} containing forbidden token {token!r}"
            )


def test_evaluator_does_not_mutate_input_context() -> None:
    """``DecisionContext`` is a frozen dataclass, so mutation would raise
    FrozenInstanceError already. This test additionally checks that the
    evaluator never even attempts to reassign or replace context fields,
    by comparing identity before/after."""

    rng = random.Random(7)
    policy = _random_policy(rng, rule_count=5)
    context = _random_context(rng, decision_id=42)
    original_tuple = context.filter_evaluations  # identity check anchor

    evaluator = ObserveOnlyPolicyEvaluator(policy)
    evaluator.evaluate_for_decision(context)

    assert context.filter_evaluations is original_tuple
    assert context.alert_decision_id == 42


def test_evaluator_does_not_mutate_policy_rules_tuple() -> None:
    rng = random.Random(123)
    policy = _random_policy(rng, rule_count=10)
    original_rules = policy.rules

    evaluator = ObserveOnlyPolicyEvaluator(policy)
    for i in range(50):
        evaluator.evaluate_for_decision(_random_context(rng, decision_id=i))

    assert policy.rules is original_rules
