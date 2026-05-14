"""Phase 6 test: per-decision durable progress under mid-run crash.

Step 0 V9 locked the repository's transaction convention to
``_commit_if_top_level`` -- per-call (i.e., per-decision) commits.
That gives the observer the durable-partial-progress posture this test
verifies:

  1. Run the observer with a wrapped repository that succeeds for the
     first two ``insert_evaluation_rows`` calls and raises on the third.
  2. The exception propagates out of ``run_once``.
  3. Decisions 1 and 2 have telemetry rows persisted.
  4. Decision 3 (and any later ids) have NO telemetry rows.
  5. Rerun the observer with the real repository.
  6. The rerun's ``list_alert_decision_ids_missing_policy_eval`` returns
     only decisions 3..N; the rerun completes them idempotently.
  7. Total telemetry afterwards equals ``N decisions * rule_count``;
     decisions 1 and 2's original telemetry stays put (no INSERT OR
     IGNORE conflicts because the UNIQUE constraint excludes the
     already-present rows from re-insertion).
"""

from __future__ import annotations

import pytest

from PHX2.stage16b.repository import ObserveOnlyEvaluationRepository
from PHX2.tests.stage16b.fixtures.builders import (
    DEFAULT_POLICY_HASH,
    DEFAULT_RULE_T1_NORMAL,
    StubPolicyLoader,
    insert_canonical_filter_evaluation,
    insert_would_alert_decision,
    make_loaded_policy,
    make_observer,
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


class _FailOnNthInsertRepository:
    """Wrapping repository that fails on the (fail_after + 1)th call to
    ``insert_evaluation_rows``. All other methods pass through verbatim."""

    def __init__(self, wrapped, fail_after: int) -> None:
        self._wrapped = wrapped
        self._fail_after = fail_after
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def insert_evaluation_rows(self, rows):
        self._call_count += 1
        if self._call_count > self._fail_after:
            raise RuntimeError(
                f"simulated mid-run insert failure on call "
                f"{self._call_count}"
            )
        return self._wrapped.insert_evaluation_rows(rows)

    def list_alert_decision_ids_missing_policy_eval(self, policy_hash, limit):
        return self._wrapped.list_alert_decision_ids_missing_policy_eval(
            policy_hash=policy_hash, limit=limit,
        )

    def count_evaluations_for_policy(self, policy_hash):
        return self._wrapped.count_evaluations_for_policy(policy_hash)


def test_observer_partial_crash_preserves_durable_progress(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        # Five WOULD_ALERT decisions, each with a matching FE.
        for decision_id in (1, 2, 3, 4, 5):
            insert_would_alert_decision(
                connection, decision_id=decision_id, tier_name="T1",
            )
            insert_canonical_filter_evaluation(
                connection, fe_id=decision_id,
                alert_decision_id=decision_id, label="NORMAL",
            )
        connection.commit()

        real_repo = ObserveOnlyEvaluationRepository(connection)

        # ----- First run: wrapped repo fails on 3rd insert call. -----
        failing_repo = _FailOnNthInsertRepository(real_repo, fail_after=2)
        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(
            connection, policy_loader=loader, repository=failing_repo,
        )

        with pytest.raises(RuntimeError, match="simulated mid-run insert failure"):
            observer.run_once(tmp_path / "any.json", limit=10)

        # The first two decisions were committed before the third raised.
        committed_after_crash = list(connection.execute(
            "SELECT DISTINCT alert_decision_id "
            "FROM observe_only_policy_evaluations "
            "ORDER BY alert_decision_id"
        ))
        assert [r["alert_decision_id"] for r in committed_after_crash] == [1, 2]

        # ----- Second run: real (un-wrapped) repo finishes the job. -----
        rerun_observer = make_observer(
            connection, policy_loader=loader, repository=real_repo,
        )
        rerun_report = rerun_observer.run_once(tmp_path / "any.json", limit=10)

        # list_missing returned (3, 4, 5); each got 1 telemetry row.
        assert rerun_report.alert_decisions_evaluated == 3
        assert rerun_report.rows_inserted == 3
        assert rerun_report.rows_ignored_duplicates == 0

        # All 5 decisions now have exactly 1 telemetry row each.
        per_decision = list(connection.execute(
            "SELECT alert_decision_id, COUNT(*) AS c "
            "FROM observe_only_policy_evaluations "
            "GROUP BY alert_decision_id "
            "ORDER BY alert_decision_id"
        ))

    assert [(r["alert_decision_id"], r["c"]) for r in per_decision] == [
        (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
    ]


def test_observer_partial_crash_does_not_double_write_decision_one_or_two(
    tmp_path,
) -> None:
    """The rerun's INSERT OR IGNORE must NOT touch decisions 1 and 2 --
    list_missing excludes them up-front. Hash the post-rerun rows for
    decisions 1 and 2 and verify they are byte-identical to their state
    immediately after the partial-crash run."""

    import hashlib

    def _hash_decision_rows(connection, decision_id: int) -> str:
        rows = connection.execute(
            "SELECT * FROM observe_only_policy_evaluations "
            "WHERE alert_decision_id = ? "
            "ORDER BY id",
            (decision_id,),
        ).fetchall()
        if not rows:
            return "<empty>"
        keys = rows[0].keys()
        canonical = "\n".join(
            "|".join(repr(row[k]) for k in keys) for row in rows
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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

        real_repo = ObserveOnlyEvaluationRepository(connection)

        # Run with crash on 3rd insert call.
        failing_repo = _FailOnNthInsertRepository(real_repo, fail_after=2)
        loader = StubPolicyLoader(make_loaded_policy(DEFAULT_RULE_T1_NORMAL))
        observer = make_observer(
            connection, policy_loader=loader, repository=failing_repo,
        )
        with pytest.raises(RuntimeError):
            observer.run_once(tmp_path / "any.json", limit=10)

        hash_1_before_rerun = _hash_decision_rows(connection, 1)
        hash_2_before_rerun = _hash_decision_rows(connection, 2)

        # Rerun with real repo.
        rerun_observer = make_observer(
            connection, policy_loader=loader, repository=real_repo,
        )
        rerun_observer.run_once(tmp_path / "any.json", limit=10)

        hash_1_after_rerun = _hash_decision_rows(connection, 1)
        hash_2_after_rerun = _hash_decision_rows(connection, 2)

    assert hash_1_before_rerun == hash_1_after_rerun
    assert hash_2_before_rerun == hash_2_after_rerun
