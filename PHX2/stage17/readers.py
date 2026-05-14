"""Stage 17 read-only SQLite query layer.

Every connection opened here uses the SQLite URI form with
``?mode=ro`` so the underlying file is opened read-only. The module
issues SELECT queries against three tables only:

  * observe_only_policy_evaluations
  * alert_decisions       (used for the scope filter; tier comes
                            from the evaluation row, not this one)
  * outcome_windows

Every public function in this module returns immutable tuples; no
function mutates any input or any database state.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Tuple

from PHX2.stage17.errors import Stage17Error
from PHX2.stage17.models import EvaluationRow, OutcomeRow


# ---------------------------------------------------------------------------
# Locked source-table scope filter
# ---------------------------------------------------------------------------
#
# Both clauses are required by spec. ``decision_type = 'would_alert'``
# narrows to alert decisions that intended to fire; ``would_alert = 1``
# excludes the rare case where the decision_type label disagrees with
# the boolean column. The filter is repeated everywhere a join to
# alert_decisions appears so the scope cannot drift between callers.
_SCOPE_PREDICATE = (
    "ad.decision_type = 'would_alert' AND ad.would_alert = 1"
)


REQUIRED_TABLES: Tuple[str, ...] = (
    "observe_only_policy_evaluations",
    "alert_decisions",
    "outcome_windows",
)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def open_db_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the PHX2 SQLite DB in read-only mode.

    Uses ``file:<path>?mode=ro`` with ``uri=True`` so writes raise
    ``sqlite3.OperationalError("attempt to write a readonly database")``
    instead of mutating the file. Sets ``row_factory = sqlite3.Row``
    so callers can index returned rows by column name.
    """

    try:
        resolved = db_path.expanduser().resolve()
        if not resolved.is_file():
            raise Stage17Error("A01", f"db_path is not a file: {db_path}")
        uri = f"file:{resolved}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise Stage17Error("A01", f"sqlite3 open failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Table presence
# ---------------------------------------------------------------------------


def verify_required_tables(connection: sqlite3.Connection) -> None:
    """Confirm every Stage 17 source table exists via sqlite_master.

    Raises ``Stage17Error("A02", detail=<table_name>)`` on the first
    missing table. Callers map this onto exit-code 3 (load tier).
    """

    for table in REQUIRED_TABLES:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if row is None:
            raise Stage17Error("A02", table)


# ---------------------------------------------------------------------------
# Distinct policy_hashes
# ---------------------------------------------------------------------------


def list_distinct_policy_hashes(connection: sqlite3.Connection) -> Tuple[str, ...]:
    """Return distinct policy_hash values with at least one in-scope evaluation.

    "In scope" applies the same locked WOULD_ALERT predicate every
    other Stage 17 reader uses
    (``ad.decision_type = 'would_alert' AND ad.would_alert = 1``).
    Without this join the CLI's auto-discovery path could surface
    policy_hashes whose evaluations all point at out-of-scope
    decisions, polluting the manifest, summary line, and run_id
    inputs even though every downstream metric row would correctly
    drop them.

    Sorted ascending. Used by the CLI when ``--policy-hash`` is not
    passed.
    """

    query = (
        "SELECT DISTINCT e.policy_hash AS policy_hash "
        "FROM observe_only_policy_evaluations AS e "
        "JOIN alert_decisions AS ad ON ad.id = e.alert_decision_id "
        f"WHERE {_SCOPE_PREDICATE} "
        "ORDER BY e.policy_hash ASC"
    )
    try:
        rows = connection.execute(query).fetchall()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"list_distinct_policy_hashes: {exc}") from exc
    return tuple(row["policy_hash"] for row in rows)


# ---------------------------------------------------------------------------
# Evaluations (joined to in-scope alert_decisions)
# ---------------------------------------------------------------------------


_EVAL_SELECT_COLUMNS = (
    "e.id AS id, "
    "e.alert_decision_id AS alert_decision_id, "
    "e.tier_name_snapshot AS tier_name_snapshot, "
    "e.policy_hash AS policy_hash, "
    "e.rule_id AS rule_id, "
    "e.evaluation_status AS evaluation_status, "
    "e.matched AS matched, "
    "e.would_have_blocked AS would_have_blocked, "
    "e.unevaluable_reason AS unevaluable_reason, "
    "e.evaluated_at_utc AS evaluated_at_utc"
)


def fetch_evaluation_rows(
    connection: sqlite3.Connection,
    policy_hash: str,
) -> Tuple[EvaluationRow, ...]:
    """Return evaluation rows for ``policy_hash`` joined to in-scope alert_decisions.

    The join restricts to rows where the matching ``alert_decisions``
    record passes the locked scope predicate (decision_type =
    'would_alert' AND would_alert = 1). Rows are ordered by
    ``e.id ASC`` for deterministic downstream grouping.
    """

    query = (
        f"SELECT {_EVAL_SELECT_COLUMNS} "
        "FROM observe_only_policy_evaluations AS e "
        "JOIN alert_decisions AS ad ON ad.id = e.alert_decision_id "
        f"WHERE e.policy_hash = ? AND {_SCOPE_PREDICATE} "
        "ORDER BY e.id ASC"
    )
    try:
        rows = connection.execute(query, (policy_hash,)).fetchall()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"fetch_evaluation_rows: {exc}") from exc

    return tuple(
        EvaluationRow(
            id=row["id"],
            alert_decision_id=row["alert_decision_id"],
            tier_name_snapshot=row["tier_name_snapshot"],
            policy_hash=row["policy_hash"],
            rule_id=row["rule_id"],
            evaluation_status=row["evaluation_status"],
            matched=row["matched"],
            would_have_blocked=row["would_have_blocked"],
            unevaluable_reason=row["unevaluable_reason"],
            evaluated_at_utc=row["evaluated_at_utc"],
        )
        for row in rows
    )


# ---------------------------------------------------------------------------
# Outcomes for a set of decision ids
# ---------------------------------------------------------------------------


_OUTCOME_SELECT_COLUMNS = (
    "alert_decision_id, "
    "window_seconds, "
    "max_return_multiple, "
    "max_drawdown_from_peak_pct, "
    "time_to_max_return_seconds, "
    "hit_2x, "
    "hit_3x, "
    "hit_5x, "
    "data_status"
)


def fetch_outcome_rows_for_decisions(
    connection: sqlite3.Connection,
    alert_decision_ids: Iterable[int],
) -> Tuple[OutcomeRow, ...]:
    """Return outcome_windows rows for the given alert_decision_ids.

    An empty input returns ``()`` without issuing a query (SQLite
    rejects empty ``IN ()`` clauses; the early return keeps callers
    simple). Result rows are ordered by ``(alert_decision_id,
    window_seconds)`` ascending.
    """

    ids = tuple(alert_decision_ids)
    if not ids:
        return ()

    placeholders = ",".join("?" for _ in ids)
    query = (
        f"SELECT {_OUTCOME_SELECT_COLUMNS} "
        "FROM outcome_windows "
        f"WHERE alert_decision_id IN ({placeholders}) "
        "ORDER BY alert_decision_id ASC, window_seconds ASC"
    )
    try:
        rows = connection.execute(query, ids).fetchall()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"fetch_outcome_rows_for_decisions: {exc}") from exc

    return tuple(
        OutcomeRow(
            alert_decision_id=row["alert_decision_id"],
            window_seconds=row["window_seconds"],
            max_return_multiple=row["max_return_multiple"],
            max_drawdown_from_peak_pct=row["max_drawdown_from_peak_pct"],
            time_to_max_return_seconds=row["time_to_max_return_seconds"],
            hit_2x=row["hit_2x"],
            hit_3x=row["hit_3x"],
            hit_5x=row["hit_5x"],
            data_status=row["data_status"],
        )
        for row in rows
    )


# ---------------------------------------------------------------------------
# Orphan diagnostics
# ---------------------------------------------------------------------------


def count_orphan_evaluations(connection: sqlite3.Connection) -> int:
    """Count evaluations whose alert_decision_id is missing or not in scope.

    "Orphan" = either the FK target row does not exist in
    alert_decisions OR the target exists but does not satisfy the
    locked WOULD_ALERT scope predicate. Diagnostic only -- never used
    to filter the main aggregation.
    """

    query = (
        "SELECT COUNT(*) AS n "
        "FROM observe_only_policy_evaluations AS e "
        "LEFT JOIN alert_decisions AS ad ON ad.id = e.alert_decision_id "
        "WHERE ad.id IS NULL "
        "   OR NOT (ad.decision_type = 'would_alert' AND ad.would_alert = 1)"
    )
    try:
        row = connection.execute(query).fetchone()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"count_orphan_evaluations: {exc}") from exc
    return int(row["n"])


def count_orphan_outcomes(connection: sqlite3.Connection) -> int:
    """Count outcomes whose alert_decision_id has no row in alert_decisions.

    Diagnostic only. Outcome rows whose decision exists but is
    out-of-scope are NOT counted as orphans -- Stage 17 only filters
    on the evaluations side; outcomes are joined post-hoc per decision
    id.
    """

    query = (
        "SELECT COUNT(*) AS n "
        "FROM outcome_windows AS o "
        "LEFT JOIN alert_decisions AS ad ON ad.id = o.alert_decision_id "
        "WHERE ad.id IS NULL"
    )
    try:
        row = connection.execute(query).fetchone()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"count_orphan_outcomes: {exc}") from exc
    return int(row["n"])


# ---------------------------------------------------------------------------
# Manifest support: row counts and schema_migrations
# ---------------------------------------------------------------------------


def count_table(connection: sqlite3.Connection, table_name: str) -> int:
    """Return ``COUNT(*)`` for a single table.

    The table name is whitelisted against ``REQUIRED_TABLES`` so this
    helper cannot be coerced into running an arbitrary identifier.
    """

    if table_name not in REQUIRED_TABLES:
        raise Stage17Error("A03", f"count_table refused unknown table: {table_name}")
    try:
        row = connection.execute(
            f"SELECT COUNT(*) AS n FROM {table_name}"
        ).fetchone()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"count_table({table_name}): {exc}") from exc
    return int(row["n"])


def count_alert_decisions_in_scope(connection: sqlite3.Connection) -> int:
    """Return the row count of alert_decisions matching the locked scope predicate."""

    try:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM alert_decisions AS ad "
            f"WHERE {_SCOPE_PREDICATE}"
        ).fetchone()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"count_alert_decisions_in_scope: {exc}") from exc
    return int(row["n"])


def count_outcome_windows_complete(connection: sqlite3.Connection) -> int:
    """Return the row count of outcome_windows where data_status = 'COMPLETE'."""

    try:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM outcome_windows WHERE data_status = 'COMPLETE'"
        ).fetchone()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"count_outcome_windows_complete: {exc}") from exc
    return int(row["n"])


def list_schema_migrations(connection: sqlite3.Connection) -> Tuple[str, ...]:
    """Return the verbatim version list from schema_migrations.

    Returns an empty tuple if the schema_migrations table does not
    exist (older fixture DBs may lack it). Manifest determinism is
    preserved either way.
    """

    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if row is None:
        return ()
    try:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version ASC"
        ).fetchall()
    except sqlite3.Error as exc:
        raise Stage17Error("A03", f"list_schema_migrations: {exc}") from exc
    return tuple(r["version"] for r in rows)
