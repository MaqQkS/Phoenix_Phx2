"""Pure function that turns one ObserveOnlyEvaluationResult plus its source LoadedObserveOnlyPolicy into one row per policy rule (MATCHED, NOT_MATCHED, or UNEVALUABLE); no I/O."""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage16a.hashing import canonical_json_dumps
from PHX2.stage16a.models import (
    LoadedObserveOnlyPolicy,
    LoadedRule,
    ObserveOnlyEvaluationResult,
)
from PHX2.stage16b.models import ObserveOnlyEvaluationRow


# The 5-key predicate is the canonical shape of any predicate_snapshot in
# Stage 16B telemetry. LoadedRule carries audit metadata
# (source_stage14_rule_hash, operator_reason, reviewed_at_utc) that
# MUST NEVER leak into telemetry rows -- those belong on the runtime
# artifact's lineage block, not on per-decision evaluation rows.
_PREDICATE_KEYS: tuple[str, ...] = (
    "tier_scope",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
)


def _predicate_from_rule(rule: LoadedRule) -> dict[str, str]:
    """Project a ``LoadedRule`` down to its 5-key predicate.

    Explicitly enumerates the 5 keys so any future LoadedRule field
    addition cannot accidentally widen the telemetry surface.
    """

    return {
        "tier_scope": rule.tier_scope,
        "filter_name": rule.filter_name,
        "filter_version": rule.filter_version,
        "filter_label": rule.filter_label,
        "threshold_version": rule.threshold_version,
    }


def _predicate_from_match(snapshot: Mapping[str, str]) -> dict[str, str]:
    """Project a Stage 16A RuleMatch.predicate_snapshot to the 5 keys.

    Stage 16A's evaluator constructs the snapshot with exactly the 5 keys
    today, so this is in practice an identity projection. The explicit
    enumeration defends Stage 16B against a future Stage 16A change that
    widens the snapshot -- Stage 16B's telemetry surface never grows
    without an explicit edit to ``_PREDICATE_KEYS`` (which is policed by
    ``test_row_builder_predicate_snapshot_excludes_loaded_rule_extras``).
    """

    return {k: snapshot[k] for k in _PREDICATE_KEYS}


def build_rows_for_decision(
    alert_decision_id: int,
    tier_name: Optional[str],
    policy: LoadedObserveOnlyPolicy,
    result: ObserveOnlyEvaluationResult,
    evaluated_at_utc: str,
) -> tuple[ObserveOnlyEvaluationRow, ...]:
    """Convert one Stage 16A evaluation result into one telemetry row per policy rule.

    Pure: no I/O, deterministic given the same inputs.

    Precedence (per spec):

      * ``rule_id`` appears in ``result.matched_rules``  -> MATCHED row
          predicate_snapshot from ``RuleMatch.predicate_snapshot``
          (projected to the 5 keys).
      * else ``rule_id`` appears in ``result.unevaluable_rules`` -> UNEVALUABLE
        row with ``unevaluable_reason`` carried through verbatim, and
        predicate_snapshot from the rule's own 5-key predicate.
      * else -> NOT_MATCHED row, predicate_snapshot from the rule's own
        5-key predicate.

    Output row count is ALWAYS ``len(policy.rules)``: every policy rule
    produces exactly one row.

    ``predicate_snapshot_json`` is the canonical JSON
    (``sort_keys=True``, compact separators, ``ensure_ascii=False``) of
    EXACTLY the 5 predicate keys; LoadedRule audit metadata
    (``source_stage14_rule_hash``, ``operator_reason``,
    ``reviewed_at_utc``) is never copied in.
    """

    matched_by_id = {m.rule_id: m for m in result.matched_rules}
    unevaluable_by_id = {u.rule_id: u for u in result.unevaluable_rules}

    rows: list[ObserveOnlyEvaluationRow] = []
    for rule in policy.rules:
        if rule.rule_id in matched_by_id:
            match = matched_by_id[rule.rule_id]
            predicate = _predicate_from_match(match.predicate_snapshot)
            rows.append(ObserveOnlyEvaluationRow(
                alert_decision_id=alert_decision_id,
                tier_name_snapshot=tier_name,
                policy_hash=policy.policy_hash,
                rule_id=rule.rule_id,
                evaluation_status="MATCHED",
                matched=1,
                would_have_blocked=1,
                unevaluable_reason=None,
                predicate_snapshot_json=canonical_json_dumps(predicate),
                evaluated_at_utc=evaluated_at_utc,
            ))
        elif rule.rule_id in unevaluable_by_id:
            ue = unevaluable_by_id[rule.rule_id]
            predicate = _predicate_from_rule(rule)
            rows.append(ObserveOnlyEvaluationRow(
                alert_decision_id=alert_decision_id,
                tier_name_snapshot=tier_name,
                policy_hash=policy.policy_hash,
                rule_id=rule.rule_id,
                evaluation_status="UNEVALUABLE",
                matched=0,
                would_have_blocked=0,
                unevaluable_reason=ue.reason,
                predicate_snapshot_json=canonical_json_dumps(predicate),
                evaluated_at_utc=evaluated_at_utc,
            ))
        else:
            predicate = _predicate_from_rule(rule)
            rows.append(ObserveOnlyEvaluationRow(
                alert_decision_id=alert_decision_id,
                tier_name_snapshot=tier_name,
                policy_hash=policy.policy_hash,
                rule_id=rule.rule_id,
                evaluation_status="NOT_MATCHED",
                matched=0,
                would_have_blocked=0,
                unevaluable_reason=None,
                predicate_snapshot_json=canonical_json_dumps(predicate),
                evaluated_at_utc=evaluated_at_utc,
            ))

    return tuple(rows)
