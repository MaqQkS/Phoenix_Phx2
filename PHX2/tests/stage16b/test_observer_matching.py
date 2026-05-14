"""Phase 6 tests: observer matching, status discrimination, and report counters.

Locks tested here:

  * MATCHED rule emits a MATCHED row.
  * Tier-mismatched rule emits a NOT_MATCHED row (Stage 16A silent skip).
  * tier_name=None emits UNEVALUABLE rows for every rule.
  * Mixed matched + unevaluable in a single decision.
  * Multiple decisions evaluated in id ASC order.
  * limit caps the number of decisions processed.
  * Empty policy returns a clean ObserverRunReport and writes zero rows.
  * Missing decision (e.g., id removed between list_missing and assemble)
    increments decisions_skipped_not_found without crashing.
  * Report counters match emitted-row arithmetic.
  * policy_hash mismatch between loaded policy and evaluator result raises
    RuntimeError.
"""

from __future__ import annotations

import pytest

from PHX2.stage16a.models import ObserveOnlyEvaluationResult
from PHX2.stage16b.models import ObserverRunReport
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


# ---------------------------------------------------------------------------
# Single-decision matching shapes
# ---------------------------------------------------------------------------


def test_observer_writes_matched_row_for_matching_rule(tmp_path) -> None:
    """Decision tier=T1 + FE label=NORMAL satisfies DEFAULT_RULE_T1_NORMAL."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

        rows = list(connection.execute(
            "SELECT * FROM observe_only_policy_evaluations ORDER BY id"
        ))

    assert len(rows) == 1
    assert rows[0]["evaluation_status"] == "MATCHED"
    assert rows[0]["matched"] == 1
    assert rows[0]["would_have_blocked"] == 1
    assert rows[0]["unevaluable_reason"] is None
    assert rows[0]["alert_decision_id"] == 1
    assert rows[0]["rule_id"] == DEFAULT_RULE_T1_NORMAL.rule_id
    assert report.matched_count == 1


def test_observer_writes_not_matched_for_tier_mismatch(tmp_path) -> None:
    """Decision tier=T3 + DEFAULT_RULE_T2_SCAM (tier T2) -> tier mismatch -> NOT_MATCHED."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T3")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="SCAM_LIKELY",
        )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T2_SCAM))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

        rows = list(connection.execute(
            "SELECT * FROM observe_only_policy_evaluations"
        ))

    assert len(rows) == 1
    assert rows[0]["evaluation_status"] == "NOT_MATCHED"
    assert rows[0]["matched"] == 0
    assert rows[0]["would_have_blocked"] == 0
    assert rows[0]["unevaluable_reason"] is None
    assert report.not_matched_count == 1


def test_observer_writes_unevaluable_when_tier_name_none(tmp_path) -> None:
    """Decision tier_name=None -> every rule is UNEVALUABLE with reason
    'tier_name_missing_on_decision'."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name=None)
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, DEFAULT_RULE_T2_SCAM,
        ))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

        rows = list(connection.execute(
            "SELECT evaluation_status, unevaluable_reason "
            "FROM observe_only_policy_evaluations ORDER BY id"
        ))

    assert len(rows) == 2
    assert all(r["evaluation_status"] == "UNEVALUABLE" for r in rows)
    assert all(r["unevaluable_reason"] == "tier_name_missing_on_decision" for r in rows)
    assert report.unevaluable_count == 2
    assert report.matched_count == 0
    assert report.not_matched_count == 0


def test_observer_handles_mixed_matched_and_unevaluable(tmp_path) -> None:
    """Two decisions: one tier=T1 (rule matches), one tier_name=None (rule unevaluable)."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        insert_would_alert_decision(connection, decision_id=2, tier_name=None)
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    assert report.matched_count == 1
    assert report.unevaluable_count == 1
    assert report.not_matched_count == 0


# ---------------------------------------------------------------------------
# Multi-decision + limit
# ---------------------------------------------------------------------------


def test_observer_evaluates_multiple_decisions(tmp_path) -> None:
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

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    assert report.alert_decisions_evaluated == 3
    assert report.rows_inserted == 3
    assert report.matched_count == 3


def test_observer_respects_limit(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        for decision_id in range(1, 6):  # 1..5
            insert_would_alert_decision(
                connection, decision_id=decision_id, tier_name="T1",
            )
            insert_canonical_filter_evaluation(
                connection, fe_id=decision_id,
                alert_decision_id=decision_id, label="NORMAL",
            )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=2)

        # The 2 lowest ids (1, 2) get telemetry; 3-5 do not.
        rows = list(connection.execute(
            "SELECT DISTINCT alert_decision_id "
            "FROM observe_only_policy_evaluations ORDER BY alert_decision_id"
        ))
        evaluated_ids = [r["alert_decision_id"] for r in rows]

    assert report.alert_decisions_evaluated == 2
    assert evaluated_ids == [1, 2]


# ---------------------------------------------------------------------------
# Empty policy short-circuit
# ---------------------------------------------------------------------------


def test_observer_empty_policy_returns_clean_report(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy())  # zero rules
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    assert isinstance(report, ObserverRunReport)
    assert report.policy_hash == DEFAULT_POLICY_HASH
    assert report.policy_rule_count == 0
    assert report.alert_decisions_evaluated == 0
    assert report.rows_inserted == 0
    assert report.rows_ignored_duplicates == 0
    assert report.decisions_skipped_not_found == 0
    assert report.matched_count == 0
    assert report.not_matched_count == 0
    assert report.unevaluable_count == 0


def test_observer_empty_policy_writes_zero_rows(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy())  # zero rules
        observer = make_observer(connection, policy_loader=loader)

        observer.run_once(tmp_path / "any.json", limit=10)

        count = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]

    assert count == 0


# ---------------------------------------------------------------------------
# Missing decision (race-window-like behavior)
# ---------------------------------------------------------------------------


class _DropOnAssembleAssembler:
    """Assembler that returns None for one specific id, real assembler otherwise."""

    def __init__(self, wrapped, missing_id: int) -> None:
        self._wrapped = wrapped
        self._missing_id = missing_id

    def assemble(self, alert_decision_id: int):
        if alert_decision_id == self._missing_id:
            return None
        return self._wrapped.assemble(alert_decision_id)


def test_observer_skips_missing_decision(tmp_path) -> None:
    """If the assembler returns None mid-run, the observer counts the
    decision as skipped and continues with the rest."""

    from PHX2.stage16b.decision_context_assembler import DecisionContextAssembler

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

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        assembler = _DropOnAssembleAssembler(
            DecisionContextAssembler(connection), missing_id=2,
        )
        observer = make_observer(
            connection, policy_loader=loader, assembler=assembler,
        )

        report = observer.run_once(tmp_path / "any.json", limit=10)

        # Decisions 1 and 3 should have telemetry; 2 should not.
        cursor = connection.execute(
            "SELECT DISTINCT alert_decision_id "
            "FROM observe_only_policy_evaluations ORDER BY alert_decision_id"
        )
        evaluated_ids = [r["alert_decision_id"] for r in cursor]

    assert report.alert_decisions_evaluated == 2
    assert report.decisions_skipped_not_found == 1
    assert evaluated_ids == [1, 3]


# ---------------------------------------------------------------------------
# Report counter arithmetic
# ---------------------------------------------------------------------------


def test_observer_report_counters_match_emitted_row_arithmetic(tmp_path) -> None:
    """Sum of status counters == alert_decisions_evaluated * policy_rule_count."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        # 3 decisions, 2-rule policy -> 6 emitted rows.
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        insert_would_alert_decision(connection, decision_id=2, tier_name="T2")
        insert_canonical_filter_evaluation(
            connection, fe_id=2, alert_decision_id=2, label="SCAM_LIKELY",
        )
        insert_would_alert_decision(connection, decision_id=3, tier_name="T3")
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, DEFAULT_RULE_T2_SCAM,
        ))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    total_emitted = report.alert_decisions_evaluated * report.policy_rule_count
    bucketed = report.matched_count + report.not_matched_count + report.unevaluable_count
    inserted_plus_ignored = report.rows_inserted + report.rows_ignored_duplicates

    assert total_emitted == 6
    assert bucketed == 6
    assert inserted_plus_ignored == 6
    assert report.rows_inserted == 6
    assert report.rows_ignored_duplicates == 0


def test_observer_report_policy_hash_and_rule_count(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        loader = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, DEFAULT_RULE_T2_SCAM,
        ))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    assert report.policy_hash == DEFAULT_POLICY_HASH
    assert report.policy_rule_count == 2


def test_observer_report_evaluation_duration_is_non_negative(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        report = observer.run_once(tmp_path / "any.json", limit=10)

    assert report.evaluation_duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# policy_hash mismatch raises
# ---------------------------------------------------------------------------


class _PolicyHashLyingEvaluator:
    """Stub evaluator that returns a different policy_hash than the
    policy it was constructed from -- triggers the observer's defensive
    RuntimeError."""

    def __init__(self, policy_hash: str) -> None:
        self._policy_hash = policy_hash

    def evaluate_for_decision(self, context):
        return ObserveOnlyEvaluationResult(
            alert_decision_id=context.alert_decision_id,
            policy_hash=self._policy_hash,
            matched_rules=(),
            unevaluable_rules=(),
        )


def test_observer_policy_hash_mismatch_raises(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        # Factory returns an evaluator that claims a different policy_hash.
        liar_factory = lambda _policy: _PolicyHashLyingEvaluator(
            policy_hash="sha256:" + "0" * 64,
        )
        observer = make_observer(
            connection, policy_loader=loader, evaluator_factory=liar_factory,
        )

        with pytest.raises(RuntimeError, match="policy_hash"):
            observer.run_once(tmp_path / "any.json", limit=10)
