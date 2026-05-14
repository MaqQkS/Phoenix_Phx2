"""Phase 6 tests: observer never mutates alert_decisions, filter_evaluations,
or any other existing table.

Locks tested here:

  * alert_decisions rows are byte-identical before and after the observer
    runs (SHA-256 of canonical row dump).
  * filter_evaluations rows are byte-identical before and after.
  * Other Stage-16B-irrelevant tables retain their row counts
    (decision_score_features, outcome_windows, dispatch_events, etc.) --
    the observer never touches them.

The before/after hash captures every column on every row in
``alert_decisions`` and ``filter_evaluations`` (incl. ``id``,
``created_at``, ``filter_labels_json``, ``key_feature_snapshot_json``,
etc.), so a single byte change would surface.
"""

from __future__ import annotations

import hashlib
from typing import Mapping

from PHX2.tests.stage16b.fixtures.builders import (
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


def _hash_table(connection, table: str) -> str:
    # ORDER BY rowid: not every PHX2 table has an ``id`` column
    # (``token_sequence_state`` is keyed on ``token_address``; ``ath_state``
    # on ``token_address``; etc.). rowid is the sqlite-built-in stable
    # ordering that exists for every non-WITHOUT-ROWID table, and is the
    # safest universal sort key for snapshot hashing.
    rows = connection.execute(
        f"SELECT * FROM {table} ORDER BY rowid"
    ).fetchall()
    if not rows:
        return "<empty>"
    keys = rows[0].keys()
    canonical = "\n".join(
        "|".join(repr(row[k]) for k in keys) for row in rows
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_count(connection, table: str) -> int:
    return connection.execute(
        f"SELECT COUNT(*) AS c FROM {table}"
    ).fetchone()["c"]


_UPSTREAM_TABLES_NEVER_MUTATED = (
    "alert_decisions",
    "filter_evaluations",
    "decision_score_features",
    "outcome_windows",
    "dispatch_events",
    "token_sequence_state",
    "migration_events",
    "price_observations",
    "ath_state",
    "ath_events",
    "field_features",
    "score_features",
    "clock_features",
    "fee_windows",
    "raw_pumpswap_events",
    "price_curve_points",
)


def _hash_all_upstream(connection) -> Mapping[str, str]:
    return {table: _hash_table(connection, table) for table in _UPSTREAM_TABLES_NEVER_MUTATED}


def test_alert_decisions_unchanged_after_observer(tmp_path) -> None:
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

        before = _hash_table(connection, "alert_decisions")

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        observer.run_once(tmp_path / "any.json", limit=10)

        after = _hash_table(connection, "alert_decisions")

    assert before == after


def test_filter_evaluations_unchanged_after_observer(tmp_path) -> None:
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

        before = _hash_table(connection, "filter_evaluations")

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        observer.run_once(tmp_path / "any.json", limit=10)

        after = _hash_table(connection, "filter_evaluations")

    assert before == after


def test_every_upstream_table_unchanged_after_observer(tmp_path) -> None:
    """Hash every existing PHX2 table before and after; only
    observe_only_policy_evaluations should change."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        insert_would_alert_decision(connection, decision_id=2, tier_name="T2")
        insert_canonical_filter_evaluation(
            connection, fe_id=2, alert_decision_id=2, label="SCAM_LIKELY",
        )
        connection.commit()

        before = _hash_all_upstream(connection)
        before_telemetry = _row_count(connection, "observe_only_policy_evaluations")

        loader = StubPolicyLoader(make_loaded_policy(
            DEFAULT_RULE_T1_NORMAL, DEFAULT_RULE_T2_SCAM,
        ))
        observer = make_observer(connection, policy_loader=loader)
        observer.run_once(tmp_path / "any.json", limit=10)

        after = _hash_all_upstream(connection)
        after_telemetry = _row_count(connection, "observe_only_policy_evaluations")

    # Every upstream table is byte-identical.
    assert before == after
    # observe_only_policy_evaluations is the only table that grew.
    assert before_telemetry == 0
    assert after_telemetry > 0


def test_no_upstream_mutation_across_multiple_observer_runs(tmp_path) -> None:
    """Running the observer multiple times still leaves every upstream
    table byte-identical to the pre-first-run state."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )
        connection.commit()

        before = _hash_all_upstream(connection)

        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(connection, policy_loader=loader)
        for _ in range(3):
            observer.run_once(tmp_path / "any.json", limit=10)

        after = _hash_all_upstream(connection)

    assert before == after
