"""Phase 6 tests: observer rerun idempotency.

Locks tested here:

  * Rerunning the same policy after a complete run writes zero new rows.
  * A rerun after additional WOULD_ALERT decisions land processes only
    the new ones (the existing decisions' telemetry stays put).
  * A second policy with a different policy_hash writes a separate row
    set for the same decision; the original rows are untouched.
  * INSERT OR IGNORE silently drops conflicting duplicates (verified
    through the observer pipeline, not just at repository level).
"""

from __future__ import annotations

from PHX2.tests.stage16b.fixtures.builders import (
    ALT_POLICY_HASH,
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


def test_observer_rerun_same_policy_writes_zero_new_rows(tmp_path) -> None:
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

        first = observer.run_once(tmp_path / "any.json", limit=100)
        second = observer.run_once(tmp_path / "any.json", limit=100)

        total = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]

    assert first.rows_inserted == 3
    assert first.alert_decisions_evaluated == 3
    # Second run sees nothing missing -> evaluates no decisions, writes
    # no rows.
    assert second.rows_inserted == 0
    assert second.alert_decisions_evaluated == 0
    assert total == 3


def test_observer_rerun_after_new_decisions_only_evaluates_new(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)

        first = observer.run_once(tmp_path / "any.json", limit=100)
        assert first.alert_decisions_evaluated == 1

        # Add two more WOULD_ALERT decisions between runs.
        insert_would_alert_decision(connection, decision_id=2, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=2, alert_decision_id=2, label="NORMAL",
        )
        insert_would_alert_decision(connection, decision_id=3, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=3, alert_decision_id=3, label="NORMAL",
        )
        connection.commit()

        second = observer.run_once(tmp_path / "any.json", limit=100)

        # Verify which decisions have telemetry.
        rows = list(connection.execute(
            "SELECT DISTINCT alert_decision_id "
            "FROM observe_only_policy_evaluations "
            "ORDER BY alert_decision_id"
        ))

    assert second.alert_decisions_evaluated == 2  # only decisions 2 and 3
    assert second.rows_inserted == 2
    assert [r["alert_decision_id"] for r in rows] == [1, 2, 3]


def test_observer_different_policy_hash_writes_separate_rows(tmp_path) -> None:
    """Two policies (same rule, different policy_hash) each produce their
    own telemetry rows for the same decision."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        # Policy A
        loader_a = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, policy_hash=DEFAULT_POLICY_HASH,
        ))
        observer_a = make_observer(connection, policy_loader=loader_a)
        report_a = observer_a.run_once(tmp_path / "a.json", limit=10)

        # Policy B -- same rule, different policy_hash
        loader_b = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, policy_hash=ALT_POLICY_HASH,
        ))
        observer_b = make_observer(connection, policy_loader=loader_b)
        report_b = observer_b.run_once(tmp_path / "b.json", limit=10)

        rows = list(connection.execute(
            "SELECT policy_hash FROM observe_only_policy_evaluations "
            "ORDER BY policy_hash"
        ))

    assert report_a.rows_inserted == 1
    assert report_b.rows_inserted == 1
    assert {r["policy_hash"] for r in rows} == {DEFAULT_POLICY_HASH, ALT_POLICY_HASH}
    assert len(rows) == 2


def test_observer_duplicate_inserts_handled(tmp_path) -> None:
    """Even if the observer somehow re-inserts the same (decision,
    policy, rule) tuple, INSERT OR IGNORE silently drops the dup and the
    row count remains stable.

    Triggered here by forcing list_missing to return the same decision
    twice via a wrapper -- exercises the in-pipeline dedupe path."""

    from PHX2.stage16b.repository import ObserveOnlyEvaluationRepository

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        real_repo = ObserveOnlyEvaluationRepository(connection)

        class _DoubleListingRepo:
            """Returns the same decision twice from list_missing; insert
            delegates to the real repository."""

            def __init__(self, wrapped) -> None:
                self._wrapped = wrapped

            def list_alert_decision_ids_missing_policy_eval(
                self, policy_hash, limit,
            ):
                ids = self._wrapped.list_alert_decision_ids_missing_policy_eval(
                    policy_hash=policy_hash, limit=limit,
                )
                # Duplicate the ids tuple to simulate a buggy list_missing.
                return ids + ids

            def insert_evaluation_rows(self, rows):
                return self._wrapped.insert_evaluation_rows(rows)

            def count_evaluations_for_policy(self, policy_hash):
                return self._wrapped.count_evaluations_for_policy(policy_hash)

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(
            connection,
            policy_loader=loader,
            repository=_DoubleListingRepo(real_repo),
        )

        report = observer.run_once(tmp_path / "any.json", limit=10)

        total = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]

    # 2 listings * 1 decision * 1 rule = 2 emitted rows; 1 inserted
    # (first), 1 ignored (second on the UNIQUE conflict).
    assert report.alert_decisions_evaluated == 2
    assert report.rows_inserted == 1
    assert report.rows_ignored_duplicates == 1
    assert total == 1


def test_observer_rerun_after_more_rules_added_to_policy(tmp_path) -> None:
    """A larger policy (more rules) writes additional rows for already-
    evaluated decisions because the (decision, policy_hash, rule_id)
    tuple is now distinct.

    Note: changing a rule changes the policy_hash via Stage 16A's
    canonical hash. This test mirrors that contract by using a different
    policy_hash for the second run."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        # First policy: just DEFAULT_RULE_T1_NORMAL.
        loader_a = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, policy_hash=DEFAULT_POLICY_HASH,
        ))
        observer_a = make_observer(connection, policy_loader=loader_a)
        observer_a.run_once(tmp_path / "a.json", limit=10)

        # Second policy: same rule plus DEFAULT_RULE_T2_SCAM; different hash.
        loader_b = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, DEFAULT_RULE_T2_SCAM,
            policy_hash=ALT_POLICY_HASH,
        ))
        observer_b = make_observer(connection, policy_loader=loader_b)
        observer_b.run_once(tmp_path / "b.json", limit=10)

        # First policy: 1 row (rule_t1_normal).
        # Second policy: 2 rows (rule_t1_normal matched, rule_t2_scam tier-mismatch NOT_MATCHED).
        total = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]

    assert total == 3
