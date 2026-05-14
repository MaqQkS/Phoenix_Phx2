"""Reads one alert_decisions row plus its filter_evaluations rows from the PHX2 SQLite DB and builds a Stage 16A DecisionContext; read-only, never writes."""

from __future__ import annotations

from typing import Optional

from PHX2.stage16a.models import DecisionContext, FilterEvaluationSnapshot


class DecisionContextAssembler:
    """Pure read-only assembler.

    Takes a sqlite-compatible connection (sqlite3.Connection or
    PHX2.db.connection.PHX2Connection) and exposes a single method,
    ``assemble``, that turns one ``alert_decision_id`` into the Stage 16A
    ``DecisionContext`` that the Stage 16A evaluator consumes.

    Uses narrow raw SELECT-only SQL -- it does NOT delegate to the
    concrete ``AlertDecisionRepository`` or ``FilterEvaluationRepository``,
    because those repositories live in the alert-flow service stack and
    importing them would re-introduce Stage 16B's coupling to the live
    decision path that the sidecar architecture is designed to avoid.

    Performs no writes: only SELECT statements. The "no write" invariant
    is verified by hashing the relevant tables before and after an
    assemble call (see ``test_assembler_does_not_write_anywhere``).

    Passes ``tier_name`` and every ``filter_evaluations`` column through
    verbatim -- no ``.lower()``, ``.upper()``, ``.strip()``, no
    normalization, no fallback, no dedupe. The assembler is a passive
    projection of existing DB rows into Stage 16A's input dataclasses.
    """

    def __init__(self, connection) -> None:
        self._connection = connection

    def assemble(self, alert_decision_id: int) -> Optional[DecisionContext]:
        """Return the ``DecisionContext`` for ``alert_decision_id`` or ``None`` if absent.

        Reads only the columns the Stage 16A evaluator depends on:

          * ``alert_decisions.id, tier_name``
          * ``filter_evaluations.filter_name, filter_version, label,
            threshold_version``

        Filter evaluations are ordered by ``id ASC`` for deterministic
        match ordering. An alert_decision with zero filter evaluations
        yields a ``DecisionContext`` whose ``filter_evaluations`` is the
        empty tuple.

        ``evaluated_at_utc`` on the returned DecisionContext is left at
        its Stage 16A default (``None``): the assembler is read-only and
        does not stamp a clock. The Stage 16B observer pipeline stamps
        ``evaluated_at_utc`` separately at row-build time.
        """

        decision_row = self._connection.execute(
            """
            SELECT id, tier_name
              FROM alert_decisions
             WHERE id = ?
            """,
            (alert_decision_id,),
        ).fetchone()
        if decision_row is None:
            return None

        filter_rows = self._connection.execute(
            """
            SELECT filter_name, filter_version, label, threshold_version
              FROM filter_evaluations
             WHERE alert_decision_id = ?
             ORDER BY id ASC
            """,
            (alert_decision_id,),
        ).fetchall()

        filter_evaluations = tuple(
            FilterEvaluationSnapshot(
                filter_name=row["filter_name"],
                filter_version=row["filter_version"],
                label=row["label"],
                threshold_version=row["threshold_version"],
            )
            for row in filter_rows
        )

        return DecisionContext(
            alert_decision_id=int(decision_row["id"]),
            tier_name=decision_row["tier_name"],
            filter_evaluations=filter_evaluations,
        )
