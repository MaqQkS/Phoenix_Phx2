"""Phase 9 determinism tests: two consecutive observer runs on identically-
built fresh DBs against the SAME runtime policy artifact, with a frozen
clock, produce byte-identical telemetry rows (excluding ``id`` and
``created_at_utc`` which are insertion-time artifacts).

The runtime artifact must be shared between runs because Stage 16A's
``RuntimePolicyBuilder`` embeds ``source_stage15_run_path`` (the absolute
path to the Stage 15 fixture dir) in the lineage block and therefore
into the canonical ``policy_hash``. Two artifacts built in different tmp
directories carry different paths and hash to different values; the
locked invariant Stage 16B observes is that the SAME artifact applied to
the SAME inputs produces the SAME telemetry.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator
from PHX2.stage16a.observe_only_policy_loader import ObserveOnlyPolicyLoader
from PHX2.stage16b.decision_context_assembler import DecisionContextAssembler
from PHX2.stage16b.observer import ObserveOnlyObserverService
from PHX2.stage16b.repository import ObserveOnlyEvaluationRepository
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    make_runtime_artifact_path,
)
from PHX2.tests.stage16b.fixtures.builders import (
    insert_canonical_filter_evaluation,
    insert_would_alert_decision,
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


_FIXED_EVALUATED_AT = "2026-05-13T12:00:00+00:00"


# Columns that are insertion-time artifacts (autoincrement id; wall-clock
# created_at_utc stamped by the repository at insert time). Excluded
# from determinism comparison.
_NON_DETERMINISTIC_COLUMNS = ("id", "created_at_utc")


def _dump_telemetry_excluding_volatile(connection) -> Sequence[tuple]:
    """Return all telemetry rows sorted by (alert_decision_id, rule_id),
    with ``id`` and ``created_at_utc`` stripped."""

    rows = list(connection.execute(
        "SELECT * FROM observe_only_policy_evaluations "
        "ORDER BY alert_decision_id, rule_id"
    ))
    if not rows:
        return ()
    keys = [k for k in rows[0].keys() if k not in _NON_DETERMINISTIC_COLUMNS]
    return tuple(tuple(row[k] for k in keys) for row in rows)


def _seed_db(work_dir: Path) -> Path:
    """Build a Stage 16B DB seeded with the standard 3-WOULD_ALERT scenario
    (T1+NORMAL, T3+NORMAL, None+NORMAL) covering all three evaluation
    statuses."""

    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = make_stage16b_db_path(work_dir)

    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )

        insert_would_alert_decision(connection, decision_id=2, tier_name="T3")
        insert_canonical_filter_evaluation(
            connection, fe_id=2, alert_decision_id=2, label="NORMAL",
        )

        insert_would_alert_decision(connection, decision_id=3, tier_name=None)
        insert_canonical_filter_evaluation(
            connection, fe_id=3, alert_decision_id=3, label="NORMAL",
        )
        connection.commit()
    return db_path


def _run_observer_once(db_path: Path, artifact_path: Path) -> None:
    """Run the Stage 16B observer once against ``db_path`` and
    ``artifact_path`` with the frozen clock."""

    with stage16b_phx2_connection(db_path) as connection:
        observer = ObserveOnlyObserverService(
            policy_loader=ObserveOnlyPolicyLoader(),
            evaluator_factory=ObserveOnlyPolicyEvaluator,
            assembler=DecisionContextAssembler(connection),
            repository=ObserveOnlyEvaluationRepository(connection),
            clock=lambda: _FIXED_EVALUATED_AT,
        )
        observer.run_once(artifact_path, limit=100)


def _dump_through_fresh_connection(db_path: Path) -> Sequence[tuple]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return _dump_telemetry_excluding_volatile(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Determinism across two fresh runs sharing the same artifact
# ---------------------------------------------------------------------------


def test_observer_two_fresh_runs_produce_identical_telemetry(tmp_path) -> None:
    artifact = make_runtime_artifact_path(
        tmp_path / "shared_artifact",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )

    db_a = _seed_db(tmp_path / "run_a")
    _run_observer_once(db_a, artifact)
    rows_a = _dump_through_fresh_connection(db_a)

    db_b = _seed_db(tmp_path / "run_b")
    _run_observer_once(db_b, artifact)
    rows_b = _dump_through_fresh_connection(db_b)

    assert rows_a == rows_b
    # Sanity: 3 WOULD_ALERT decisions x 2 rules = 6 rows.
    assert len(rows_a) == 6


def test_observer_three_consecutive_fresh_runs_all_match(tmp_path) -> None:
    artifact = make_runtime_artifact_path(
        tmp_path / "shared_artifact",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )

    runs: list[Sequence[tuple]] = []
    for i in range(3):
        db = _seed_db(tmp_path / f"run_{i}")
        _run_observer_once(db, artifact)
        runs.append(_dump_through_fresh_connection(db))

    assert runs[0] == runs[1] == runs[2]


def test_observer_evaluated_at_utc_uses_frozen_clock(tmp_path) -> None:
    """evaluated_at_utc takes the value from the injected clock; the
    frozen-clock fixture pins it to ``_FIXED_EVALUATED_AT``."""

    artifact = make_runtime_artifact_path(
        tmp_path / "shared_artifact",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )

    for sub in ("run_a", "run_b"):
        db = _seed_db(tmp_path / sub)
        _run_observer_once(db, artifact)
        conn = sqlite3.connect(str(db))
        try:
            stamps = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT evaluated_at_utc "
                    "FROM observe_only_policy_evaluations"
                )
            }
        finally:
            conn.close()
        assert stamps == {_FIXED_EVALUATED_AT}


def test_observer_rerun_on_same_db_writes_zero_new_rows(tmp_path) -> None:
    """Idempotency: a second observer run on the same DB writes nothing
    because list_alert_decision_ids_missing_policy_eval returns empty.

    Uses the SAME artifact for both runs so the policy_hash is stable
    and the anti-join in list_missing actually excludes the
    already-evaluated decisions."""

    artifact = make_runtime_artifact_path(
        tmp_path / "shared_artifact",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )
    db_path = _seed_db(tmp_path / "run_x")

    _run_observer_once(db_path, artifact)
    first_rows = _dump_through_fresh_connection(db_path)

    # Rerun on same DB + same artifact.
    with stage16b_phx2_connection(db_path) as connection:
        observer = ObserveOnlyObserverService(
            policy_loader=ObserveOnlyPolicyLoader(),
            evaluator_factory=ObserveOnlyPolicyEvaluator,
            assembler=DecisionContextAssembler(connection),
            repository=ObserveOnlyEvaluationRepository(connection),
            clock=lambda: _FIXED_EVALUATED_AT,
        )
        rerun_report = observer.run_once(artifact, limit=100)

    second_rows = _dump_through_fresh_connection(db_path)

    assert rerun_report.alert_decisions_evaluated == 0
    assert rerun_report.rows_inserted == 0
    assert first_rows == second_rows


def test_observer_policy_hash_is_deterministic_across_runs(tmp_path) -> None:
    """Two fresh DBs evaluated against the SAME artifact yield the same
    policy_hash on every telemetry row."""

    artifact = make_runtime_artifact_path(
        tmp_path / "shared_artifact",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )

    def _policy_hashes(db_path: Path) -> set[str]:
        conn = sqlite3.connect(str(db_path))
        try:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT policy_hash "
                    "FROM observe_only_policy_evaluations"
                )
            }
        finally:
            conn.close()

    db_a = _seed_db(tmp_path / "run_a")
    _run_observer_once(db_a, artifact)
    db_b = _seed_db(tmp_path / "run_b")
    _run_observer_once(db_b, artifact)

    hashes_a = _policy_hashes(db_a)
    hashes_b = _policy_hashes(db_b)

    assert len(hashes_a) == 1
    assert hashes_a == hashes_b


def test_observer_two_artifacts_at_different_paths_have_different_policy_hashes(
    tmp_path,
) -> None:
    """Counterpoint to the determinism contract: Stage 16A's
    RuntimePolicyBuilder embeds the absolute Stage 15 run-dir path into
    the lineage block, so two fixture-built artifacts at different paths
    have different policy_hashes. This test pins that behavior so a
    future change that makes artifact policy_hash path-independent can
    be discovered and the determinism tests above can be relaxed."""

    artifact_a = make_runtime_artifact_path(
        tmp_path / "artifact_a",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )
    artifact_b = make_runtime_artifact_path(
        tmp_path / "artifact_b",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )

    def _hash_of(artifact: Path) -> str:
        db = _seed_db(tmp_path / f"run_for_{artifact.parent.name}")
        _run_observer_once(db, artifact)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT DISTINCT policy_hash "
                "FROM observe_only_policy_evaluations"
            ).fetchone()
        finally:
            conn.close()
        return row[0]

    assert _hash_of(artifact_a) != _hash_of(artifact_b)
