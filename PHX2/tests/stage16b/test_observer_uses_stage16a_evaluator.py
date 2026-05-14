"""Phase 6 tests: observer delegates predicate matching to Stage 16A's evaluator.

Locks tested here:

  * The observer calls ``ObserveOnlyPolicyEvaluator.evaluate_for_decision``
    exactly once per evaluated decision.
  * The telemetry rows the observer writes reflect the result returned
    by the monkeypatched evaluator (proving the observer does not
    re-derive matching from the policy + context itself).

The tests monkeypatch Stage 16A's evaluator instance method rather than
its class, so other tests in the same session are unaffected.
"""

from __future__ import annotations

import json
from typing import List

from PHX2.stage16a.models import (
    DecisionContext,
    ObserveOnlyEvaluationResult,
    RuleMatch,
    RuleUnevaluable,
)
from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator
from PHX2.tests.stage16b.fixtures.builders import (
    DEFAULT_POLICY_HASH,
    DEFAULT_RULE_T1_NORMAL,
    DEFAULT_RULE_T2_SCAM,
    StubPolicyLoader,
    insert_canonical_filter_evaluation,
    insert_would_alert_decision,
    make_loaded_policy,
    make_observer,
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


def test_observer_calls_stage16a_evaluator_once_per_evaluated_decision(
    tmp_path, monkeypatch,
) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        for decision_id in (1, 2, 3):
            insert_would_alert_decision(
                connection, decision_id=decision_id, tier_name="T1",
            )
            insert_canonical_filter_evaluation(
                connection, fe_id=decision_id,
                alert_decision_id=decision_id, label="NORMAL",
            )
        connection.commit()

        # Monkeypatch the evaluator's instance method by replacing the
        # class method. Count calls + retain real behavior so the
        # observer's pipeline (row builder / repository) sees a real
        # evaluation result.
        original_evaluate = ObserveOnlyPolicyEvaluator.evaluate_for_decision
        call_log: List[int] = []

        def _counting_evaluate(self, context: DecisionContext):
            call_log.append(context.alert_decision_id)
            return original_evaluate(self, context)

        monkeypatch.setattr(
            ObserveOnlyPolicyEvaluator,
            "evaluate_for_decision",
            _counting_evaluate,
        )

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        observer.run_once(tmp_path / "any.json", limit=10)

    assert call_log == [1, 2, 3]


def test_observer_telemetry_reflects_monkeypatched_evaluator_result(
    tmp_path, monkeypatch,
) -> None:
    """Replace the evaluator's behavior to always emit a MATCHED row for
    DEFAULT_RULE_T1_NORMAL, even when the rule's predicate would not
    actually match. The observer must propagate that decision verbatim
    into telemetry, proving it does not re-derive matching from the
    policy + context itself."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        # Decision is tier T3 -- DEFAULT_RULE_T1_NORMAL would tier-mismatch
        # in the real evaluator. The monkeypatched evaluator emits MATCHED.
        insert_would_alert_decision(connection, decision_id=1, tier_name="T3")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="SCAM_LIKELY",
        )
        connection.commit()

        forced_predicate_snapshot = {
            "tier_scope": "T1",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "NORMAL",
            "threshold_version": "thresholds_v0_observe_only",
        }

        def _force_matched(self, context: DecisionContext):
            return ObserveOnlyEvaluationResult(
                alert_decision_id=context.alert_decision_id,
                policy_hash=self._policy.policy_hash,
                matched_rules=(
                    RuleMatch(
                        rule_id=DEFAULT_RULE_T1_NORMAL.rule_id,
                        matched_filter_evaluation_index=0,
                        predicate_snapshot=forced_predicate_snapshot,
                    ),
                ),
                unevaluable_rules=(),
            )

        monkeypatch.setattr(
            ObserveOnlyPolicyEvaluator,
            "evaluate_for_decision",
            _force_matched,
        )

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        report = observer.run_once(tmp_path / "any.json", limit=10)

        rows = list(connection.execute(
            "SELECT * FROM observe_only_policy_evaluations"
        ))

    assert report.matched_count == 1
    assert report.not_matched_count == 0
    assert len(rows) == 1
    assert rows[0]["evaluation_status"] == "MATCHED"
    assert rows[0]["rule_id"] == DEFAULT_RULE_T1_NORMAL.rule_id
    # predicate_snapshot reflects the forced match's snapshot.
    snapshot = json.loads(rows[0]["predicate_snapshot_json"])
    assert snapshot == forced_predicate_snapshot


def test_observer_telemetry_reflects_monkeypatched_unevaluable(
    tmp_path, monkeypatch,
) -> None:
    """Force the evaluator to return all-UNEVALUABLE for a tier=T1
    decision (which would normally produce MATCHED) and verify the
    telemetry reflects the forced UNEVALUABLE outcome."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        def _force_unevaluable(self, context: DecisionContext):
            return ObserveOnlyEvaluationResult(
                alert_decision_id=context.alert_decision_id,
                policy_hash=self._policy.policy_hash,
                matched_rules=(),
                unevaluable_rules=(
                    RuleUnevaluable(
                        rule_id=DEFAULT_RULE_T1_NORMAL.rule_id,
                        reason="forced_for_test",
                    ),
                ),
            )

        monkeypatch.setattr(
            ObserveOnlyPolicyEvaluator,
            "evaluate_for_decision",
            _force_unevaluable,
        )

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        report = observer.run_once(tmp_path / "any.json", limit=10)

        row = connection.execute(
            "SELECT evaluation_status, unevaluable_reason "
            "FROM observe_only_policy_evaluations"
        ).fetchone()

    assert report.unevaluable_count == 1
    assert report.matched_count == 0
    assert row["evaluation_status"] == "UNEVALUABLE"
    assert row["unevaluable_reason"] == "forced_for_test"
