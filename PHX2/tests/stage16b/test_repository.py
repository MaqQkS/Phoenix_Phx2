"""Phase 4 tests: Stage 16B ObserveOnlyEvaluationRepository.

Locks tested here:

  * Subclasses ``PHX2.db.repositories.RepositoryContract``.
  * No public method name starts with ``update``, ``delete``, ``mutate``,
    ``mark``, ``save``, ``upsert``, ``set_``, or ``clear``.
  * ``insert_evaluation_rows`` uses ``INSERT OR IGNORE`` on the UNIQUE
    constraint; duplicates are silently dropped and the returned count
    excludes them.
  * Repository stamps ``created_at_utc`` at insert time.
  * ``list_alert_decision_ids_missing_policy_eval`` filters strictly to
    ``decision_type='would_alert' AND would_alert=1``, anti-joins the
    Stage 16B table on ``policy_hash``, orders by ``ad.id`` ASC, respects
    ``limit`` (incl. ``limit=0``), and is per-policy_hash.
  * ``count_evaluations_for_policy`` is per-``policy_hash`` and returns
    zero for unknown hashes.
  * FK runtime rejection is conditional on ``PRAGMA foreign_keys = ON``
    (global PHX2 posture is OFF).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

import pytest

from PHX2.stage16b.models import ObserveOnlyEvaluationRow
from PHX2.stage16b.repository import (
    WOULD_ALERT_DECISION_TYPE,
    WOULD_ALERT_FLAG,
    ObserveOnlyEvaluationRepository,
)
from PHX2.tests.fixtures.analysis_fixture_builder import insert_alert_decision
from PHX2.tests.stage16b.fixtures.builders import (
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


# ---------------------------------------------------------------------------
# Constants + row factory
# ---------------------------------------------------------------------------


POLICY_A = "sha256:" + "a" * 64
POLICY_B = "sha256:" + "b" * 64
EVALUATED_AT = "2026-05-13T12:00:00+00:00"
DECISION_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)


def _make_row(
    *,
    alert_decision_id: int = 1,
    tier_name_snapshot: Optional[str] = "T1",
    policy_hash: str = POLICY_A,
    rule_id: str = "rule_a",
    evaluation_status: str = "NOT_MATCHED",
    matched: int = 0,
    would_have_blocked: int = 0,
    unevaluable_reason: Optional[str] = None,
    predicate_snapshot_json: str = "{}",
    evaluated_at_utc: str = EVALUATED_AT,
) -> ObserveOnlyEvaluationRow:
    return ObserveOnlyEvaluationRow(
        alert_decision_id=alert_decision_id,
        tier_name_snapshot=tier_name_snapshot,
        policy_hash=policy_hash,
        rule_id=rule_id,
        evaluation_status=evaluation_status,
        matched=matched,
        would_have_blocked=would_have_blocked,
        unevaluable_reason=unevaluable_reason,
        predicate_snapshot_json=predicate_snapshot_json,
        evaluated_at_utc=evaluated_at_utc,
    )


def _insert_would_alert(connection, *, decision_id: int, token_address: str = "tok",
                        tier_name: Optional[str] = "T1") -> None:
    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=DECISION_TIME,
        decision_type="would_alert",
        would_alert=True,
        tier_name=tier_name,
    )


# ---------------------------------------------------------------------------
# Insert behavior
# ---------------------------------------------------------------------------


def test_insert_single_row(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        inserted = repo.insert_evaluation_rows([_make_row(alert_decision_id=1)])

        assert inserted == 1
        row = connection.execute(
            "SELECT * FROM observe_only_policy_evaluations"
        ).fetchone()
        assert row is not None
        assert row["alert_decision_id"] == 1
        assert row["policy_hash"] == POLICY_A
        assert row["rule_id"] == "rule_a"
        assert row["evaluation_status"] == "NOT_MATCHED"


def test_insert_batch(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        rows = [
            _make_row(alert_decision_id=1, rule_id=f"rule_{i}")
            for i in range(5)
        ]
        inserted = repo.insert_evaluation_rows(rows)

        assert inserted == 5
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]
        assert count == 5


def test_insert_empty_sequence_returns_zero(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        repo = ObserveOnlyEvaluationRepository(connection)
        assert repo.insert_evaluation_rows([]) == 0
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]
        assert count == 0


def test_duplicate_insert_silently_ignored(tmp_path) -> None:
    """Re-inserting the same (decision, policy, rule) tuple does not raise."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        row = _make_row(alert_decision_id=1, rule_id="rule_a")
        first = repo.insert_evaluation_rows([row])
        # Second call must not raise.
        second = repo.insert_evaluation_rows([row])

        assert first == 1
        assert second == 0


def test_insert_count_excludes_ignored_duplicates(tmp_path) -> None:
    """A mixed batch of new + duplicate rows reports only newly-inserted count."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        existing = _make_row(alert_decision_id=1, rule_id="rule_a")
        repo.insert_evaluation_rows([existing])

        batch = [
            _make_row(alert_decision_id=1, rule_id="rule_a"),  # duplicate
            _make_row(alert_decision_id=1, rule_id="rule_b"),  # new
            _make_row(alert_decision_id=1, rule_id="rule_c"),  # new
        ]
        inserted = repo.insert_evaluation_rows(batch)

        assert inserted == 2
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]
        assert count == 3


def test_created_at_utc_set_on_insert(tmp_path) -> None:
    """``created_at_utc`` is stamped at insert time and is a valid recent UTC ISO."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        before = datetime.now(timezone.utc)
        repo.insert_evaluation_rows([_make_row(alert_decision_id=1)])
        after = datetime.now(timezone.utc)

        row = connection.execute(
            "SELECT created_at_utc FROM observe_only_policy_evaluations"
        ).fetchone()
        created_at = datetime.fromisoformat(row["created_at_utc"])
        # Allow microsecond skew in either direction.
        assert before.replace(microsecond=0) <= created_at.replace(microsecond=0) <= after.replace(microsecond=0)
        # Sanity-check tzinfo.
        assert created_at.tzinfo is not None


def test_evaluated_at_utc_distinct_from_created_at_utc(tmp_path) -> None:
    """The dataclass-supplied evaluated_at_utc is preserved verbatim; the
    repository stamps created_at_utc independently."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        repo.insert_evaluation_rows([_make_row(
            alert_decision_id=1,
            evaluated_at_utc="2020-01-01T00:00:00+00:00",
        )])

        row = connection.execute(
            "SELECT evaluated_at_utc, created_at_utc FROM observe_only_policy_evaluations"
        ).fetchone()
        assert row["evaluated_at_utc"] == "2020-01-01T00:00:00+00:00"
        # created_at_utc was just stamped, so its year is current.
        assert row["created_at_utc"] != "2020-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# list_alert_decision_ids_missing_policy_eval
# ---------------------------------------------------------------------------


def test_list_missing_returns_only_unevaluated_decisions(tmp_path) -> None:
    """Decisions with telemetry for the same policy_hash are excluded."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_would_alert(connection, decision_id=2)
        _insert_would_alert(connection, decision_id=3)
        repo = ObserveOnlyEvaluationRepository(connection)

        # Decision 2 has telemetry; 1 and 3 do not.
        repo.insert_evaluation_rows([_make_row(alert_decision_id=2)])

        ids = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10)

        assert ids == (1, 3)


def test_list_missing_respects_limit(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        for i in range(1, 6):
            _insert_would_alert(connection, decision_id=i)
        repo = ObserveOnlyEvaluationRepository(connection)

        ids = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=2)

        assert ids == (1, 2)


def test_list_missing_orders_by_id_asc(tmp_path) -> None:
    """Out-of-order insertion still yields id-ASC retrieval."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        # Insert decisions in non-monotonic id order.
        _insert_would_alert(connection, decision_id=5)
        _insert_would_alert(connection, decision_id=2)
        _insert_would_alert(connection, decision_id=8)
        repo = ObserveOnlyEvaluationRepository(connection)

        ids = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10)

        assert ids == (2, 5, 8)


def test_list_missing_filters_by_policy_hash(tmp_path) -> None:
    """Telemetry for policy A does not satisfy the anti-join for policy B."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_would_alert(connection, decision_id=2)
        repo = ObserveOnlyEvaluationRepository(connection)

        # Decision 1 has telemetry for policy A only.
        repo.insert_evaluation_rows([
            _make_row(alert_decision_id=1, policy_hash=POLICY_A),
        ])

        # Policy A: only decision 2 is missing.
        ids_a = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10)
        # Policy B: both are missing because decision 1's row is for A.
        ids_b = repo.list_alert_decision_ids_missing_policy_eval(POLICY_B, limit=10)

        assert ids_a == (2,)
        assert ids_b == (1, 2)


def test_list_missing_filters_to_would_alert_only(tmp_path) -> None:
    """Only ``decision_type='would_alert' AND would_alert=1`` rows surface."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        # SKIP decision -- decision_type is not 'would_alert', would_alert=0.
        insert_alert_decision(
            connection,
            decision_id=2,
            token_address="tok",
            evaluated_at=DECISION_TIME,
            decision_type="skip",
            would_alert=False,
            tier_name=None,
        )
        # BLOCK decision.
        insert_alert_decision(
            connection,
            decision_id=3,
            token_address="tok",
            evaluated_at=DECISION_TIME,
            decision_type="block",
            would_alert=False,
            tier_name="T1",
        )
        _insert_would_alert(connection, decision_id=4)
        repo = ObserveOnlyEvaluationRepository(connection)

        ids = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10)

        assert ids == (1, 4)


def test_list_missing_excludes_would_alert_zero(tmp_path) -> None:
    """Belt-and-suspenders: a row with decision_type='would_alert' but
    would_alert=0 must NOT surface. In practice the engine never produces
    that combination, but the filter must reject it anyway."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_alert_decision(
            connection,
            decision_id=1,
            token_address="tok",
            evaluated_at=DECISION_TIME,
            decision_type="would_alert",
            would_alert=False,  # contradicts decision_type
            tier_name="T1",
        )
        repo = ObserveOnlyEvaluationRepository(connection)

        ids = repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10)

        assert ids == ()


def test_list_missing_limit_zero_returns_empty(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        assert repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=0) == ()


def test_list_missing_negative_limit_clamped_to_zero(tmp_path) -> None:
    """``limit < 0`` is clamped, not raised; mirrors AlertDecisionRepository._limit."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        assert repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=-5) == ()


def test_list_missing_empty_alert_decisions(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        repo = ObserveOnlyEvaluationRepository(connection)
        assert repo.list_alert_decision_ids_missing_policy_eval(POLICY_A, limit=10) == ()


# ---------------------------------------------------------------------------
# count_evaluations_for_policy
# ---------------------------------------------------------------------------


def test_count_evaluations_for_policy(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        _insert_would_alert(connection, decision_id=2)
        repo = ObserveOnlyEvaluationRepository(connection)

        repo.insert_evaluation_rows([
            _make_row(alert_decision_id=1, rule_id="rule_a"),
            _make_row(alert_decision_id=2, rule_id="rule_a"),
            _make_row(alert_decision_id=2, rule_id="rule_b"),
        ])

        assert repo.count_evaluations_for_policy(POLICY_A) == 3


def test_count_zero_for_unknown_policy_hash(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        repo.insert_evaluation_rows([_make_row(alert_decision_id=1, policy_hash=POLICY_A)])

        assert repo.count_evaluations_for_policy(POLICY_B) == 0


def test_count_filters_by_policy_hash(tmp_path) -> None:
    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        _insert_would_alert(connection, decision_id=1)
        repo = ObserveOnlyEvaluationRepository(connection)

        repo.insert_evaluation_rows([
            _make_row(alert_decision_id=1, rule_id="rule_a", policy_hash=POLICY_A),
            _make_row(alert_decision_id=1, rule_id="rule_a", policy_hash=POLICY_B),
            _make_row(alert_decision_id=1, rule_id="rule_b", policy_hash=POLICY_A),
        ])

        assert repo.count_evaluations_for_policy(POLICY_A) == 2
        assert repo.count_evaluations_for_policy(POLICY_B) == 1


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_repository_does_not_subclass_concrete_repository_module() -> None:
    """Audit-required: Stage 16B's repository must NOT inherit from
    ``PHX2.db.repositories.RepositoryContract`` because importing
    ``PHX2.db.repositories`` transitively loads ``PHX2.models`` and
    ``PHX2.config.settings``, widening Stage 16B's sidecar import
    boundary. The repository is a top-level class instead.
    """

    bases = ObserveOnlyEvaluationRepository.__mro__
    base_names = [
        f"{b.__module__}.{b.__qualname__}" for b in bases
    ]
    # Only object should be in the MRO besides the class itself.
    assert ObserveOnlyEvaluationRepository in bases
    assert object in bases
    forbidden_bases = [
        n for n in base_names
        if n.startswith("PHX2.db.repositories.")
        or n.startswith("PHX2.config.")
        or n.startswith("PHX2.models.")
    ]
    assert not forbidden_bases, (
        f"ObserveOnlyEvaluationRepository inherits from a forbidden module: "
        f"{forbidden_bases!r}"
    )


def test_repository_class_has_no_mutation_methods() -> None:
    forbidden_prefixes = (
        "update", "delete", "mutate", "mark", "save", "upsert", "set_", "clear",
    )
    public_method_names = [
        name
        for name in dir(ObserveOnlyEvaluationRepository)
        if not name.startswith("_")
        and callable(getattr(ObserveOnlyEvaluationRepository, name, None))
    ]
    violations: list[tuple[str, str]] = []
    for name in public_method_names:
        for prefix in forbidden_prefixes:
            if name.startswith(prefix):
                violations.append((name, prefix))
    assert not violations, (
        f"ObserveOnlyEvaluationRepository exposes forbidden mutation methods: "
        f"{violations!r}"
    )


def test_repository_module_constants_locked() -> None:
    """The WOULD_ALERT magic-string and flag constants are locked to the
    Step 0 V6 values."""

    assert WOULD_ALERT_DECISION_TYPE == "would_alert"
    assert WOULD_ALERT_FLAG == 1


# ---------------------------------------------------------------------------
# FK runtime rejection -- conditional on PRAGMA foreign_keys ON
# ---------------------------------------------------------------------------


def test_repository_insert_fk_rejection_when_enforcement_enabled(tmp_path) -> None:
    """Inserting a telemetry row whose alert_decision_id does not exist
    in alert_decisions must fail with sqlite3.IntegrityError when
    PRAGMA foreign_keys = ON.

    The global PHX2 posture is foreign_keys = OFF (V5 finding); this
    test toggles ON for the assertion only. If the SQLite build refuses
    to enable enforcement, the test skips.
    """

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        pragma = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if not pragma:
            pytest.skip(
                "PRAGMA foreign_keys could not be enabled in this SQLite build"
            )

        repo = ObserveOnlyEvaluationRepository(connection)
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert_evaluation_rows([_make_row(alert_decision_id=99999)])
