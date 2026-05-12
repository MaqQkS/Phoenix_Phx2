"""Stage 12 substrate readers.

Each reader wraps a ``sqlite3.Connection`` (opened read-only via
``sqlite3.connect(..., uri=True)`` with ``mode=ro``) and issues SELECT
statements against ONE allowed substrate table:

  * AlertDecisionsReader     -> alert_decisions
  * FilterEvaluationsReader  -> filter_evaluations
  * DecisionScoreFeaturesReader -> decision_score_features
  * OutcomeWindowsReader     -> outcome_windows
  * TokenIdentityReader      -> token_sequence_state (display-only,
                                 symbol column only)

L4 (substrate-read narrowing) is enforced architecturally:
``SubstrateReaders`` (in decision_outcome_analysis.py) is a frozen
dataclass whose fields are typed to these reader classes only. No
forbidden-table reader can be wired in by mistake.

Readers issue ONLY SELECT statements. They never INSERT, UPDATE,
DELETE, ALTER, DROP, CREATE, REPLACE, or run a PRAGMA that mutates
state. The DB connection should additionally be opened with
``mode=ro`` so any rogue write attempt fails at the driver layer.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Sequence

import pandas as pd


# ---------------------------------------------------------------------------
# Column inventories
# ---------------------------------------------------------------------------

# Book-keeping / non-primitive columns excluded from the dynamically
# discovered DSF primitive list. Combined STEP 0 S0-3 list plus
# refinement A (identity, tier, and timestamp columns are not numeric
# measurements -- bucketing them would be meaningless).
_DSF_NON_PRIMITIVE_COLUMNS: frozenset[str] = frozenset({
    "id",
    "alert_decision_id",
    "feature_version",
    "schema_version",
    "token_address",
    "token_symbol",
    "decision_time",
    "as_of_time",
    "tier_index",
    "tier_name",
    "ath_time",
    "migration_time",
    "source_snapshot_json",
    "created_at",
    "data_status",
    "missing_reasons_json",
})


# Columns the long CSV reads from alert_decisions. Excludes JSON / audit
# fields the analysis does not consume.
_ALERT_DECISIONS_COLUMNS: tuple[str, ...] = (
    "id",
    "token_address",
    "evaluated_at",
    "decision_type",
    "tier_index",
    "tier_name",
    "primary_reason",
    "would_alert",
    "policy_version",
    "ath_status",
    "ath_confidence",
    "current_price",
    "current_mcap",
    "data_status",
)


_FILTER_EVALUATIONS_COLUMNS: tuple[str, ...] = (
    "id",
    "alert_decision_id",
    "token_address",
    "as_of_time",
    "filter_name",
    "filter_version",
    "threshold_version",
    "label",
    "score",
    "would_block",
    "policy_action",
    "reason",
    "data_status",
)


_OUTCOME_WINDOWS_COLUMNS: tuple[str, ...] = (
    "id",
    "alert_decision_id",
    "window_seconds",
    "window_start_time",
    "window_end_time",
    "alert_price",
    "alert_mcap",
    "max_price",
    "max_mcap",
    "max_observation_time",
    "min_price",
    "min_mcap",
    "min_observation_time",
    "max_return_multiple",
    "max_return_pct",
    "min_return_multiple",
    "min_return_pct",
    "max_drawdown_from_peak_pct",
    "time_to_max_return_seconds",
    "hit_2x",
    "hit_3x",
    "hit_5x",
    "observations_count",
    "first_observation_time",
    "last_observation_time",
    "data_status",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _placeholders(n: int) -> str:
    if n <= 0:
        raise ValueError("placeholders requires n >= 1")
    return ",".join("?" for _ in range(n))


def _read_sql(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> pd.DataFrame:
    cursor = connection.execute(sql, tuple(params))
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat()
    return value.isoformat()


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


class AlertDecisionsReader:
    """Read-only access to alert_decisions."""

    SOURCE_TABLE = "alert_decisions"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def read_all(
        self,
        *,
        included_decision_types: Sequence[str],
        decision_time_range_start: datetime | None = None,
        decision_time_range_end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return alert_decisions filtered by status and time range.

        Time-range comparisons are lexicographic on ISO 8601 TEXT, which
        is correct for the canonical format used throughout PHX2 (UTC
        offset present, fixed-width fields).
        """

        if not included_decision_types:
            raise ValueError("included_decision_types must be non-empty")

        cols = ", ".join(_ALERT_DECISIONS_COLUMNS)
        sql_parts: list[str] = [
            f"SELECT {cols} FROM alert_decisions",
            f"WHERE decision_type IN ({_placeholders(len(included_decision_types))})",
        ]
        params: list[object] = list(included_decision_types)

        if decision_time_range_start is not None:
            sql_parts.append("AND evaluated_at >= ?")
            params.append(_iso(decision_time_range_start))
        if decision_time_range_end is not None:
            sql_parts.append("AND evaluated_at <= ?")
            params.append(_iso(decision_time_range_end))

        sql_parts.append("ORDER BY id ASC")
        return _read_sql(self.connection, " ".join(sql_parts), params)

    def count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM alert_decisions"
        ).fetchone()
        return int(row[0]) if row is not None else 0


class FilterEvaluationsReader:
    """Read-only access to filter_evaluations."""

    SOURCE_TABLE = "filter_evaluations"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def read_for_decisions(self, ids: Sequence[int]) -> pd.DataFrame:
        if not ids:
            return pd.DataFrame(columns=_FILTER_EVALUATIONS_COLUMNS)
        cols = ", ".join(_FILTER_EVALUATIONS_COLUMNS)
        sql = (
            f"SELECT {cols} FROM filter_evaluations "
            f"WHERE alert_decision_id IN ({_placeholders(len(ids))}) "
            f"ORDER BY id ASC"
        )
        return _read_sql(self.connection, sql, list(ids))

    def count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM filter_evaluations"
        ).fetchone()
        return int(row[0]) if row is not None else 0


class DecisionScoreFeaturesReader:
    """Read-only access to decision_score_features."""

    SOURCE_TABLE = "decision_score_features"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def discover_primitive_columns(self) -> list[str]:
        """Return the dynamically discovered list of typed numeric primitive
        columns in decision_score_features, sorted alphabetically.

        Implements FC-1 (Stage 11 feature_version bumps auto-propagate
        without requiring a Stage 12 code edit). Excludes the
        book-keeping/non-primitive set documented in
        ``_DSF_NON_PRIMITIVE_COLUMNS``. Filters by declared SQLite type
        (REAL or INTEGER) so TEXT columns added in future revisions are
        excluded automatically.
        """

        cursor = self.connection.execute(
            "PRAGMA table_info(decision_score_features)"
        )
        primitives: list[str] = []
        for row in cursor.fetchall():
            name = row[1]
            declared_type = (row[2] or "").upper()
            if name in _DSF_NON_PRIMITIVE_COLUMNS:
                continue
            if declared_type not in ("REAL", "INTEGER"):
                continue
            primitives.append(name)
        return sorted(primitives)

    def read_for_decisions(self, ids: Sequence[int]) -> pd.DataFrame:
        if not ids:
            return self._empty_frame()
        cols = self._select_columns()
        sql = (
            f"SELECT {cols} FROM decision_score_features "
            f"WHERE alert_decision_id IN ({_placeholders(len(ids))}) "
            f"ORDER BY id ASC"
        )
        return _read_sql(self.connection, sql, list(ids))

    def _select_columns(self) -> str:
        # All columns; the orchestrator picks token_symbol + primitives
        # from the result. Including all columns keeps the read narrow
        # in row count while letting the orchestrator avoid a follow-up
        # introspection round-trip.
        cursor = self.connection.execute(
            "PRAGMA table_info(decision_score_features)"
        )
        cols = [row[1] for row in cursor.fetchall()]
        return ", ".join(cols)

    def _empty_frame(self) -> pd.DataFrame:
        cursor = self.connection.execute(
            "PRAGMA table_info(decision_score_features)"
        )
        cols = [row[1] for row in cursor.fetchall()]
        return pd.DataFrame(columns=cols)

    def count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM decision_score_features"
        ).fetchone()
        return int(row[0]) if row is not None else 0


class OutcomeWindowsReader:
    """Read-only access to outcome_windows."""

    SOURCE_TABLE = "outcome_windows"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def read_for_decisions(self, ids: Sequence[int]) -> pd.DataFrame:
        if not ids:
            return pd.DataFrame(columns=_OUTCOME_WINDOWS_COLUMNS)
        cols = ", ".join(_OUTCOME_WINDOWS_COLUMNS)
        sql = (
            f"SELECT {cols} FROM outcome_windows "
            f"WHERE alert_decision_id IN ({_placeholders(len(ids))}) "
            f"ORDER BY alert_decision_id ASC, window_seconds ASC, id ASC"
        )
        return _read_sql(self.connection, sql, list(ids))

    def count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM outcome_windows"
        ).fetchone()
        return int(row[0]) if row is not None else 0


class TokenIdentityReader:
    """Read-only display-only join into token_sequence_state.symbol.

    Symbol values populate the long CSV's ``symbol`` column for display
    purposes only. They are explicitly forbidden from entering any
    cohort calculation, denominator, screening, or bucket logic
    (L4 hard rule).
    """

    SOURCE_TABLE = "token_sequence_state"

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def read_symbols(self, addresses: Iterable[str]) -> dict[str, str | None]:
        unique = sorted({a for a in addresses if a})
        if not unique:
            return {}
        sql = (
            "SELECT token_address, symbol FROM token_sequence_state "
            f"WHERE token_address IN ({_placeholders(len(unique))})"
        )
        cursor = self.connection.execute(sql, tuple(unique))
        out: dict[str, str | None] = {}
        for row in cursor.fetchall():
            address = row[0]
            symbol = row[1]
            out[address] = symbol
        return out


# L1 substrate-write enforcement is operational, not introspective: the
# CLI opens the DB with sqlite3 URI mode=ro and that connection is the
# only one ever passed to the readers. There is intentionally NO
# in-package probe helper -- a "probe" that issues CREATE TABLE / DROP
# TABLE statements to test read-onlyness would itself be analysis-
# package write SQL (a latent L1 violation), even if rolled back.
#
# End-to-end coverage of the read-only guarantee lives in the test
# suite:
#   * test_test1_readonly_uri_rejects_writes (PHX2/tests/test_analysis_pipeline.py)
#     -- confirms the CLI's mode=ro URI rejects writes at the driver layer.
#   * test_test10_runtime_trace_only_touches_allowed_tables
#     (PHX2/tests/test_analysis_read_isolation.py)
#     -- confirms the pipeline's SQL trace contains only allowed tables.
