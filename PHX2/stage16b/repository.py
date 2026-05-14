"""Append-only. No update_*, delete_*, mutate_*, mark_*, save_*, upsert_*, set_*, or clear_* methods. Owns exactly one table: observe_only_policy_evaluations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Sequence

from PHX2.stage16b.models import ObserveOnlyEvaluationRow


# Step 0 V6 locked: WOULD_ALERT decisions are
# ``decision_type='would_alert' AND would_alert=1``. Stage 16B mirrors
# the predicate used by
# ``AlertDecisionRepository.list_pending_would_alert_with_ids`` verbatim
# (see PHX2/db/repositories.py:731). The magic strings live here once so
# tests and observer code reference the same source of truth.
WOULD_ALERT_DECISION_TYPE: str = "would_alert"
WOULD_ALERT_FLAG: int = 1


def _now_utc_iso() -> str:
    """Stamp ``created_at_utc`` at INSERT time. Module-level so tests can
    monkeypatch it for deterministic Phase 9 fixtures."""

    return datetime.now(timezone.utc).isoformat()


class ObserveOnlyEvaluationRepository:
    """Append-only repository for ``observe_only_policy_evaluations``.

    Accepts a raw ``sqlite3.Connection``. The repository deliberately
    does NOT subclass ``PHX2.db.repositories.RepositoryContract`` and
    does NOT use ``PHX2.db.connection.PHX2Connection``: importing either
    of those modules would transitively load ``PHX2.config.settings``
    and ``PHX2.models`` / ``PHX2.models.enums``, widening Stage 16B's
    sidecar import boundary beyond the locked surface (the audit
    flagged this as a HIGH finding and required the move to raw
    sqlite3).

    Owns exactly one table. Reads ``alert_decisions`` only via a
    ``NOT EXISTS`` anti-join to enumerate WOULD_ALERT decisions whose
    telemetry for a given policy is missing. Never imports or invokes
    ``AlertDecisionRepository`` or ``FilterEvaluationRepository``.

    No method on this class starts with ``update``, ``delete``,
    ``mutate``, ``mark``, ``save``, ``upsert``, ``set_``, or ``clear``:
    telemetry is append-only and the API surface declares it (locked
    via ``test_repository_class_has_no_mutation_methods``).
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # ---------- transaction helper ----------

    def _commit_if_top_level(self, was_in_transaction: bool) -> None:
        """Equivalent of PHX2's RepositoryContract convention, adapted to
        a raw ``sqlite3.Connection``.

        For ``sqlite3.Connection``, ``in_transaction`` is ``True`` while
        there are uncommitted data-modification statements in flight.
        Callers snapshot the flag BEFORE issuing writes and pass the
        snapshot in: if the connection was at the top level
        (``in_transaction is False``) when the call started, the writes
        this call issued started the implicit transaction and the
        repository owns commit/rollback for those writes; if the
        connection was already inside a transaction (e.g., a future
        Stage 16B caller wrapping a workflow in ``with connection:``),
        commit is left to whoever opened the transaction.

        Stage 16B's observer never composes writes under an outer
        transaction today, so in practice this always commits per call
        -- the durability contract ``test_observer_partial_crash``
        relies on.
        """

        if not was_in_transaction:
            self.connection.commit()

    # ---------- write surface ----------

    def insert_evaluation_rows(
        self,
        rows: Sequence[ObserveOnlyEvaluationRow],
    ) -> int:
        """Insert a batch of telemetry rows; return the count actually inserted.

        Stamps ``created_at_utc`` to the current UTC ISO timestamp at
        insert time. ``INSERT OR IGNORE`` silently drops rows whose
        ``(alert_decision_id, policy_hash, rule_id)`` tuple is already
        present (the UNIQUE constraint); this is the mechanism by which
        observer reruns are idempotent.

        The returned count excludes ignored duplicates. An empty
        sequence is handled without executing any SQL.
        """

        if not rows:
            return 0
        # Snapshot transaction state BEFORE the first execute so we know
        # whether our writes started a new transaction or joined an
        # existing one (see _commit_if_top_level docstring).
        was_in_transaction = bool(
            getattr(self.connection, "in_transaction", False)
        )
        now = _now_utc_iso()
        inserted = 0
        for row in rows:
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO observe_only_policy_evaluations (
                    alert_decision_id,
                    tier_name_snapshot,
                    policy_hash,
                    rule_id,
                    evaluation_status,
                    matched,
                    would_have_blocked,
                    unevaluable_reason,
                    predicate_snapshot_json,
                    evaluated_at_utc,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.alert_decision_id,
                    row.tier_name_snapshot,
                    row.policy_hash,
                    row.rule_id,
                    row.evaluation_status,
                    row.matched,
                    row.would_have_blocked,
                    row.unevaluable_reason,
                    row.predicate_snapshot_json,
                    row.evaluated_at_utc,
                    now,
                ),
            )
            inserted += cursor.rowcount
        self._commit_if_top_level(was_in_transaction)
        return inserted

    # ---------- read surface ----------

    def list_alert_decision_ids_missing_policy_eval(
        self,
        policy_hash: str,
        limit: int,
    ) -> tuple[int, ...]:
        """Return WOULD_ALERT decision ids whose telemetry for ``policy_hash`` is absent.

        Filters strictly to WOULD_ALERT
        (``decision_type='would_alert' AND would_alert=1``); the
        anti-join (``NOT EXISTS``) excludes any decision that already has
        at least one telemetry row for the given ``policy_hash``.
        Ordered by ``id ASC`` for deterministic backfill progression.

        ``limit`` is clamped to ``>= 0``; a ``limit`` of ``0`` returns
        an empty tuple without executing SQL.

        Uses positional column access (``row[0]``) so the method works
        regardless of whether the caller's connection has
        ``row_factory = sqlite3.Row`` set.
        """

        clamped_limit = max(0, int(limit))
        if clamped_limit == 0:
            return ()
        rows = self.connection.execute(
            """
            SELECT ad.id
              FROM alert_decisions ad
             WHERE ad.decision_type = ?
               AND ad.would_alert = ?
               AND NOT EXISTS (
                   SELECT 1
                     FROM observe_only_policy_evaluations oe
                    WHERE oe.alert_decision_id = ad.id
                      AND oe.policy_hash = ?
               )
             ORDER BY ad.id ASC
             LIMIT ?
            """,
            (
                WOULD_ALERT_DECISION_TYPE,
                WOULD_ALERT_FLAG,
                policy_hash,
                clamped_limit,
            ),
        ).fetchall()
        return tuple(int(row[0]) for row in rows)

    def count_evaluations_for_policy(self, policy_hash: str) -> int:
        """Return the number of telemetry rows recorded for ``policy_hash``.

        Returns ``0`` for an unknown ``policy_hash``.
        """

        row = self.connection.execute(
            """
            SELECT COUNT(*)
              FROM observe_only_policy_evaluations
             WHERE policy_hash = ?
            """,
            (policy_hash,),
        ).fetchone()
        return int(row[0]) if row is not None else 0
