"""Pure function. Returns matches against the loaded observe-only policy. NEVER returns a blocking decision. NEVER writes. NEVER calls into alert flow.

The evaluator takes a ``LoadedObserveOnlyPolicy`` at construction time and
exposes a single method, ``evaluate_for_decision``, that compares an inbound
``DecisionContext`` to every rule in the loaded policy and returns a
``ObserveOnlyEvaluationResult``. ``enforcement_effect``, ``dispatch_allowed``,
and ``live_decision_mutated`` are Literal-typed constants -- the evaluator
has no code path that produces any other value.

Matching is exact-string: no case normalization, no whitespace trimming, no
type coercion. The matching loop is total (it never raises) because every
input is a frozen dataclass whose construction has already validated its
own invariants.
"""

from __future__ import annotations

from types import MappingProxyType

from PHX2.stage16a.models import (
    DecisionContext,
    LoadedObserveOnlyPolicy,
    ObserveOnlyEvaluationResult,
    RuleMatch,
    RuleUnevaluable,
)


_TIER_MISSING_REASON = "tier_name_missing_on_decision"


class ObserveOnlyPolicyEvaluator:
    """Pure evaluator that matches a DecisionContext against a LoadedObserveOnlyPolicy and returns observe-only matches only.

    The constructor binds a single ``LoadedObserveOnlyPolicy`` to the
    instance; ``evaluate_for_decision`` is read-only over that policy.
    """

    def __init__(self, policy: LoadedObserveOnlyPolicy) -> None:
        self._policy = policy

    def evaluate_for_decision(
        self, context: DecisionContext
    ) -> ObserveOnlyEvaluationResult:
        """Match ``context`` against every rule in the bound policy.

        Per Phase 7 matching algorithm:

          1. ``context.tier_name is None`` -> every rule is
             ``RuleUnevaluable(tier_name_missing_on_decision)``.
          2. Tier mismatch -> silent skip.
          3. Otherwise, scan ``context.filter_evaluations`` for an exact
             match on (filter_name, filter_version, label, threshold_version).
             At most one match per rule.
          4. No match and not unevaluable -> silent skip (rule simply
             didn't fire).

        Returns ``ObserveOnlyEvaluationResult`` with the locked
        observe-only invariants. Total: never raises.
        """

        matched: list[RuleMatch] = []
        unevaluable: list[RuleUnevaluable] = []

        for rule in self._policy.rules:
            if context.tier_name is None:
                unevaluable.append(RuleUnevaluable(
                    rule_id=rule.rule_id,
                    reason=_TIER_MISSING_REASON,
                ))
                continue

            if context.tier_name != rule.tier_scope:
                continue

            for index, fe in enumerate(context.filter_evaluations):
                if (
                    fe.filter_name == rule.filter_name
                    and fe.filter_version == rule.filter_version
                    and fe.label == rule.filter_label
                    and fe.threshold_version == rule.threshold_version
                ):
                    matched.append(RuleMatch(
                        rule_id=rule.rule_id,
                        matched_filter_evaluation_index=index,
                        predicate_snapshot=MappingProxyType({
                            "tier_scope": rule.tier_scope,
                            "filter_name": rule.filter_name,
                            "filter_version": rule.filter_version,
                            "filter_label": rule.filter_label,
                            "threshold_version": rule.threshold_version,
                        }),
                    ))
                    break  # at most one match per rule per decision

        return ObserveOnlyEvaluationResult(
            alert_decision_id=context.alert_decision_id,
            policy_hash=self._policy.policy_hash,
            matched_rules=tuple(matched),
            unevaluable_rules=tuple(unevaluable),
        )
