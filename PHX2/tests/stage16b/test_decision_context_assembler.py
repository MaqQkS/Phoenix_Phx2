"""Phase 5 tests: Stage 16B DecisionContextAssembler.

Locks tested here:

  * Returns a DecisionContext for an existing alert_decision_id.
  * Returns None for a missing alert_decision_id.
  * Filter evaluations are ordered by id ASC.
  * Filter evaluations are scoped to the target alert_decision_id.
  * Label casing is preserved verbatim (no .lower / .upper / .strip).
  * tier_name passes through verbatim, including None.
  * T1/T2/T3 tier names pass through verbatim.
  * Empty filter_evaluations yields a DecisionContext with empty tuple.
  * Assembler performs no writes (hash relevant tables before/after).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Mapping

from PHX2.stage16a.models import DecisionContext, FilterEvaluationSnapshot
from PHX2.stage16b.decision_context_assembler import DecisionContextAssembler
from PHX2.tests.fixtures.analysis_fixture_builder import (
    insert_alert_decision,
    insert_filter_evaluation,
)
from PHX2.tests.stage16b.fixtures.builders import (
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


# ---------------------------------------------------------------------------
# Constants + helpers
# ---------------------------------------------------------------------------


DECISION_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
AS_OF_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)


def _insert_would_alert(
    connection,
    *,
    decision_id: int,
    tier_name="T1",
    token_address: str = "tok",
) -> None:
    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=DECISION_TIME,
        decision_type="would_alert",
        would_alert=True,
        tier_name=tier_name,
    )


def _insert_fe(
    connection,
    *,
    filter_evaluation_id: int,
    alert_decision_id: int,
    filter_name: str = "fee_gate",
    filter_version: str = "fee_gate_v1_no_bribes",
    threshold_version: str = "thresholds_v0_observe_only",
    label: str = "NORMAL",
) -> None:
    insert_filter_evaluation(
        connection,
        filter_evaluation_id=filter_evaluation_id,
        alert_decision_id=alert_decision_id,
        token_address="tok",
        as_of_time=AS_OF_TIME,
        filter_name=filter_name,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
    )


def _hash_relevant_tables(connection) -> Mapping[str, str]:
    """SHA-256 over canonical dumps of the three tables the assembler touches.

    Returned mapping is used to assert no side effects across an
    assemble() call.
    """

    result: dict[str, str] = {}
    for table in (
        "alert_decisions",
        "filter_evaluations",
        "observe_only_policy_evaluations",
    ):
        rows = connection.execute(
            f"SELECT * FROM {table} ORDER BY id"
        ).fetchall()
        if rows:
            keys = rows[0].keys()
            canonical = "\n".join(
                "|".join(repr(row[k]) for k in keys) for row in rows
            )
        else:
            canonical = ""
        result[table] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


# ---------------------------------------------------------------------------
# Existence + None
# ---------------------------------------------------------------------------


def test_returns_context_for_existing_decision(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1, tier_name="T1")
        _insert_fe(connection, filter_evaluation_id=1, alert_decision_id=1)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert isinstance(context, DecisionContext)
    assert context.alert_decision_id == 1
    assert context.tier_name == "T1"
    assert len(context.filter_evaluations) == 1


def test_returns_none_for_missing_decision(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        context = DecisionContextAssembler(connection).assemble(99999)

    assert context is None


def test_returns_none_for_missing_decision_when_others_exist(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_would_alert(connection, decision_id=2)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(999)

    assert context is None


# ---------------------------------------------------------------------------
# Filter-evaluations ordering and scoping
# ---------------------------------------------------------------------------


def test_filter_evaluations_ordered_by_id_asc(tmp_path) -> None:
    """Out-of-order insertion still yields id-ASC retrieval."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        # Insert with non-monotonic id; vary filter_name so the UNIQUE
        # constraint is not violated.
        _insert_fe(
            connection, filter_evaluation_id=5, alert_decision_id=1,
            filter_name="filter_b",
        )
        _insert_fe(
            connection, filter_evaluation_id=2, alert_decision_id=1,
            filter_name="filter_a",
        )
        _insert_fe(
            connection, filter_evaluation_id=8, alert_decision_id=1,
            filter_name="filter_c",
        )
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert [fe.filter_name for fe in context.filter_evaluations] == [
        "filter_a",
        "filter_b",
        "filter_c",
    ]


def test_filter_evaluations_scoped_to_target_decision(tmp_path) -> None:
    """An assemble call returns only filter rows tied to the target id."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_would_alert(connection, decision_id=2)
        _insert_fe(
            connection, filter_evaluation_id=1, alert_decision_id=1,
            filter_name="filter_for_1",
        )
        _insert_fe(
            connection, filter_evaluation_id=2, alert_decision_id=2,
            filter_name="filter_for_2",
        )
        connection.commit()

        context_1 = DecisionContextAssembler(connection).assemble(1)
        context_2 = DecisionContextAssembler(connection).assemble(2)

    assert context_1 is not None and context_2 is not None
    assert [fe.filter_name for fe in context_1.filter_evaluations] == ["filter_for_1"]
    assert [fe.filter_name for fe in context_2.filter_evaluations] == ["filter_for_2"]


def test_empty_filter_evaluations_returns_empty_tuple(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert context.filter_evaluations == ()
    assert isinstance(context.filter_evaluations, tuple)


# ---------------------------------------------------------------------------
# Label casing -- preserved verbatim across the 5 CHECK-allowed values
# ---------------------------------------------------------------------------


def test_label_casing_preserved_for_normal(tmp_path) -> None:
    _assert_label_passthrough(tmp_path, "NORMAL")


def test_label_casing_preserved_for_elevated(tmp_path) -> None:
    _assert_label_passthrough(tmp_path, "ELEVATED")


def test_label_casing_preserved_for_suspicious(tmp_path) -> None:
    _assert_label_passthrough(tmp_path, "SUSPICIOUS")


def test_label_casing_preserved_for_scam_likely(tmp_path) -> None:
    _assert_label_passthrough(tmp_path, "SCAM_LIKELY")


def test_label_casing_preserved_for_unknown(tmp_path) -> None:
    _assert_label_passthrough(tmp_path, "UNKNOWN")


def _assert_label_passthrough(tmp_path, label: str) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_fe(
            connection, filter_evaluation_id=1, alert_decision_id=1,
            label=label,
        )
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert context.filter_evaluations[0].label == label


# ---------------------------------------------------------------------------
# tier_name passthrough (None + T1/T2/T3)
# ---------------------------------------------------------------------------


def test_tier_name_none_preserved(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1, tier_name=None)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert context.tier_name is None


def test_tier_name_t1_preserved(tmp_path) -> None:
    _assert_tier_passthrough(tmp_path, "T1")


def test_tier_name_t2_preserved(tmp_path) -> None:
    _assert_tier_passthrough(tmp_path, "T2")


def test_tier_name_t3_preserved(tmp_path) -> None:
    _assert_tier_passthrough(tmp_path, "T3")


def _assert_tier_passthrough(tmp_path, tier_name: str) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1, tier_name=tier_name)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert context.tier_name == tier_name


# ---------------------------------------------------------------------------
# FilterEvaluationSnapshot field passthrough
# ---------------------------------------------------------------------------


def test_filter_evaluation_snapshot_fields_passthrough(tmp_path) -> None:
    """All four FE columns flow through to FilterEvaluationSnapshot verbatim."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_fe(
            connection,
            filter_evaluation_id=1,
            alert_decision_id=1,
            filter_name="fee_gate",
            filter_version="fee_gate_v1_no_bribes",
            threshold_version="thresholds_v0_observe_only",
            label="SCAM_LIKELY",
        )
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert len(context.filter_evaluations) == 1
    fe = context.filter_evaluations[0]
    assert isinstance(fe, FilterEvaluationSnapshot)
    assert fe.filter_name == "fee_gate"
    assert fe.filter_version == "fee_gate_v1_no_bribes"
    assert fe.threshold_version == "thresholds_v0_observe_only"
    assert fe.label == "SCAM_LIKELY"


def test_alert_decision_id_passthrough(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=42, tier_name="T2")
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(42)

    assert context is not None
    assert context.alert_decision_id == 42


def test_evaluated_at_utc_left_at_default(tmp_path) -> None:
    """Assembler is read-only; it does not stamp a clock. The Stage 16A
    DecisionContext default for ``evaluated_at_utc`` is ``None``."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        connection.commit()

        context = DecisionContextAssembler(connection).assemble(1)

    assert context is not None
    assert context.evaluated_at_utc is None


# ---------------------------------------------------------------------------
# No-write contract
# ---------------------------------------------------------------------------


def test_assembler_does_not_write_anywhere(tmp_path) -> None:
    """Hash relevant tables before + after assemble(); state must be byte-identical.

    Covers: target decision present, target decision absent, multiple
    re-calls. Hashes ``alert_decisions``, ``filter_evaluations``, and
    ``observe_only_policy_evaluations`` -- every table that the
    assembler reads or could theoretically write.
    """

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1, tier_name="T1")
        _insert_would_alert(connection, decision_id=2, tier_name="T2")
        _insert_fe(
            connection, filter_evaluation_id=1, alert_decision_id=1,
            filter_name="filter_a",
        )
        _insert_fe(
            connection, filter_evaluation_id=2, alert_decision_id=1,
            filter_name="filter_b",
        )
        _insert_fe(
            connection, filter_evaluation_id=3, alert_decision_id=2,
            filter_name="filter_a",
        )
        connection.commit()

        before = _hash_relevant_tables(connection)

        assembler = DecisionContextAssembler(connection)
        for _ in range(3):
            assembler.assemble(1)      # existing
            assembler.assemble(2)      # existing
            assembler.assemble(99999)  # missing

        after = _hash_relevant_tables(connection)

    assert before == after
