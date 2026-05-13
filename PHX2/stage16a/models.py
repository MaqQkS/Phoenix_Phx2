"""Stage 16A frozen dataclasses for loaded policies, decision contexts, rule matches, and observe-only evaluation results.

All dataclasses are ``frozen=True`` so the evaluator pipeline cannot mutate
shared state. ``Literal`` defaults on safety-critical fields
(``intended_action``, ``hard_block_allowed``, ``enforcement_effect``,
``dispatch_allowed``, ``live_decision_mutated``) make the type-checker
itself enforce that no Stage 16A result ever claims a hard-blocking
posture.

Stdlib-only: ``dataclasses`` + ``typing``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Optional


# ---------------------------------------------------------------------------
# Loaded policy (output of ObserveOnlyPolicyLoader)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedRule:
    """One rule from a loaded observe-only runtime policy.

    Carries the 5-key predicate tuple plus the operator-review metadata
    and the source Stage 14 rule hash. ``intended_action`` and
    ``hard_block_allowed`` are Literal-typed defaults so any construction
    that tries to override them with a non-observe value would fail
    type-checking (and the loader's R06 check would reject the artifact
    in any case).
    """

    rule_id: str
    tier_scope: str
    filter_name: str
    filter_version: str
    filter_label: str
    threshold_version: str
    intended_action: Literal["LOG_WOULD_BLOCK"] = "LOG_WOULD_BLOCK"
    hard_block_allowed: Literal[False] = False
    source_stage14_rule_hash: str = ""
    operator_reason: str = ""
    reviewed_at_utc: str = ""


@dataclass(frozen=True)
class LoadedObserveOnlyPolicy:
    """The parsed, validated observe-only runtime policy ready for evaluation.

    ``policy_hash`` mirrors the value stored in the runtime artifact; the
    loader has already verified it matches the computed canonical hash of
    the body. ``lineage`` is a frozen mapping carrying Stage 15 / 14 / 13 /
    12 hashes plus operator-review identity, used for audit trails.
    """

    schema_version: Literal["observe_only_runtime_policy_v0"]
    policy_hash: str
    generated_at_utc: str
    git_commit: str
    rules: tuple[LoadedRule, ...]
    lineage: Mapping[str, str]


# ---------------------------------------------------------------------------
# Decision-side inputs (consumed by the evaluator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterEvaluationSnapshot:
    """A single decision's per-filter snapshot used as evaluator input.

    Mirrors the live ``filter_evaluations`` row identity used by the
    UNIQUE(alert_decision_id, filter_name, filter_version, threshold_version)
    constraint plus the per-row ``label``.
    """

    filter_name: str
    filter_version: str
    label: str
    threshold_version: str


@dataclass(frozen=True)
class DecisionContext:
    """The decision-side context passed into ``evaluate_for_decision``.

    Stage 16A's evaluator is read-only over this structure -- it never
    mutates ``filter_evaluations`` or any other field. ``tier_name`` is
    ``None`` for decisions whose tier could not be assigned; the
    evaluator records all rules as ``RuleUnevaluable`` in that case
    (per Phase 7 matching rule 1).
    """

    alert_decision_id: int
    tier_name: Optional[str]
    filter_evaluations: tuple[FilterEvaluationSnapshot, ...]
    evaluated_at_utc: Optional[str] = None


# ---------------------------------------------------------------------------
# Evaluator outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleMatch:
    """A single matched rule from one evaluator call.

    ``matched_filter_evaluation_index`` points back into the originating
    ``DecisionContext.filter_evaluations`` tuple. ``predicate_snapshot``
    is a frozen mapping of the matched 5-tuple keys, for forensic logging.
    """

    rule_id: str
    matched_filter_evaluation_index: int
    predicate_snapshot: Mapping[str, str]


@dataclass(frozen=True)
class RuleUnevaluable:
    """A rule that could not be evaluated for structural reasons.

    Phase 7 currently records this only when ``DecisionContext.tier_name``
    is ``None`` (reason: ``"tier_name_missing_on_decision"``). Future
    structural unevaluability reasons would surface here without expanding
    ``RuleMatch``.
    """

    rule_id: str
    reason: str


@dataclass(frozen=True)
class ObserveOnlyEvaluationResult:
    """The full result of one ``evaluate_for_decision`` call.

    ``enforcement_effect``, ``dispatch_allowed``, and
    ``live_decision_mutated`` are Literal-typed constants. The evaluator
    has no path that produces any other value; these fields are part of
    the type signature so any downstream consumer that branches on them
    is guaranteed by the type system to see the observe-only invariants
    hold.
    """

    alert_decision_id: int
    policy_hash: str
    matched_rules: tuple[RuleMatch, ...]
    unevaluable_rules: tuple[RuleUnevaluable, ...]
    enforcement_effect: Literal["NONE"] = "NONE"
    dispatch_allowed: Literal[True] = True
    live_decision_mutated: Literal[False] = False
