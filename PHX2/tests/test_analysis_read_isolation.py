"""Stage 12 TEST 10 -- read-isolation enforcement.

Two complementary checks:

  * Architectural: ``SubstrateReaders`` is a frozen dataclass whose
    fields are typed to exactly the five permitted reader classes.
    A "forbidden" reader pointing at field_features / clock_features /
    fee_windows / etc. cannot be wired in via the dataclass signature.

  * Runtime: a ``sqlite3.set_trace_callback`` records every SQL
    statement issued during a pipeline run. Every table reference
    must fall in the allowed set
      {alert_decisions, filter_evaluations, decision_score_features,
       outcome_windows, token_sequence_state}
    plus the SQLite metadata namespaces (sqlite_master, sqlite_temp_*)
    used by PRAGMA introspection. Any reference to a forbidden table
    (field_features, clock_features, fee_windows, ath_state, ath_events,
    price_observations, raw_pumpswap_events, migration_events,
    price_curve_points, dispatch_events, schema_migrations) fails the
    test.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, get_type_hints

from PHX2.analysis.decision_outcome_analysis import (
    RunParams,
    SubstrateReaders,
    run,
)
from PHX2.analysis.readers import (
    AlertDecisionsReader,
    DecisionScoreFeaturesReader,
    FilterEvaluationsReader,
    OutcomeWindowsReader,
    TokenIdentityReader,
)
from PHX2.tests.fixtures.analysis_fixture_builder import (
    build_canonical_fixture,
    open_readonly_connection,
)


ALLOWED_TABLES: frozenset[str] = frozenset({
    "alert_decisions",
    "filter_evaluations",
    "decision_score_features",
    "outcome_windows",
    "token_sequence_state",
})


FORBIDDEN_TABLES: frozenset[str] = frozenset({
    "field_features",
    "clock_features",
    "fee_windows",
    "ath_state",
    "ath_events",
    "price_observations",
    "raw_pumpswap_events",
    "migration_events",
    "price_curve_points",
    "dispatch_events",
    "schema_migrations",
})


# ---------------------------------------------------------------------------
# Architectural test
# ---------------------------------------------------------------------------


def test_test10_substrate_readers_dataclass_field_types() -> None:
    """L4: SubstrateReaders' field type-hints reference exactly the
    five permitted reader classes.

    If a future change wired a forbidden reader (e.g.
    ``field_features: FieldFeaturesReader``) into the dataclass, this
    test fails.
    """

    hints = get_type_hints(SubstrateReaders)
    expected = {
        "alert_decisions": AlertDecisionsReader,
        "filter_evaluations": FilterEvaluationsReader,
        "decision_score_features": DecisionScoreFeaturesReader,
        "outcome_windows": OutcomeWindowsReader,
    }
    # token_identity is Optional[TokenIdentityReader].
    assert hints["token_identity"] == Optional[TokenIdentityReader]

    for field_name, expected_type in expected.items():
        assert field_name in hints, f"missing field {field_name}"
        assert hints[field_name] is expected_type, (
            f"{field_name} type-hint is {hints[field_name]!r}, "
            f"expected {expected_type!r}"
        )


def test_test10_substrate_readers_is_frozen() -> None:
    """SubstrateReaders is a frozen dataclass -- field assignments are
    rejected at runtime. This makes ``readers.alert_decisions =
    <something_forbidden>`` impossible after construction."""

    assert dataclasses.is_dataclass(SubstrateReaders)
    params = dataclasses.fields(SubstrateReaders)
    assert {f.name for f in params} == {
        "alert_decisions",
        "filter_evaluations",
        "decision_score_features",
        "outcome_windows",
        "token_identity",
    }

    # Frozen check: attempt mutation.
    import sqlite3 as _sqlite3
    connection = _sqlite3.connect(":memory:")
    try:
        readers = SubstrateReaders(
            alert_decisions=AlertDecisionsReader(connection),
            filter_evaluations=FilterEvaluationsReader(connection),
            decision_score_features=DecisionScoreFeaturesReader(connection),
            outcome_windows=OutcomeWindowsReader(connection),
            token_identity=TokenIdentityReader(connection),
        )
        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            readers.alert_decisions = AlertDecisionsReader(connection)  # type: ignore[misc]
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Runtime trace test
# ---------------------------------------------------------------------------


_TABLE_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TABLE_REFERENCE_RE = re.compile(
    r"\b(?:from|join|into|update|table)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_PRAGMA_TABLE_RE = re.compile(
    r"pragma\s+table_info\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    re.IGNORECASE,
)


def _extract_table_references(sql: str) -> set[str]:
    """Heuristic table-name extraction from a SQL statement.

    Looks for tokens after FROM / JOIN / INTO / UPDATE / TABLE and
    inside PRAGMA table_info(...). Returns lowercase table names.
    Does NOT attempt to handle subqueries with table aliases, schema
    prefixes, or quoted identifiers -- Stage 12's SQL is plain enough
    that this works.
    """

    refs: set[str] = set()
    for match in _TABLE_REFERENCE_RE.findall(sql):
        refs.add(match.lower())
    for match in _PRAGMA_TABLE_RE.findall(sql):
        refs.add(match.lower())
    return refs


def test_test10_runtime_trace_only_touches_allowed_tables(tmp_path: Path) -> None:
    """Trace every SQL statement issued during a pipeline run and
    verify each table reference is in ALLOWED_TABLES (or in the
    sqlite_master / sqlite_temp_* introspection namespace).
    """

    fixture = build_canonical_fixture(tmp_path / "iso.db")
    traced_sql: list[str] = []

    connection = open_readonly_connection(fixture)
    connection.set_trace_callback(traced_sql.append)
    try:
        readers = SubstrateReaders(
            alert_decisions=AlertDecisionsReader(connection),
            filter_evaluations=FilterEvaluationsReader(connection),
            decision_score_features=DecisionScoreFeaturesReader(connection),
            outcome_windows=OutcomeWindowsReader(connection),
            token_identity=TokenIdentityReader(connection),
        )
        params = RunParams(
            output_root=tmp_path / "out",
            run_id="20260101T000000Z_iso___",
            created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            as_of_time=datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc),
        )
        run(readers, params)
    finally:
        connection.close()

    assert traced_sql, "expected at least one traced SQL statement"

    all_table_refs: set[str] = set()
    for stmt in traced_sql:
        all_table_refs.update(_extract_table_references(stmt))

    # Filter out SQLite metadata namespaces.
    refs_to_check = {
        ref
        for ref in all_table_refs
        if not ref.startswith("sqlite_")
    }

    forbidden_observed = refs_to_check & FORBIDDEN_TABLES
    assert not forbidden_observed, (
        f"L4 violation: pipeline touched forbidden tables {forbidden_observed!r}\n"
        f"Full traced refs: {sorted(refs_to_check)}\n"
        f"Statements containing forbidden refs: "
        + "\n".join(
            stmt for stmt in traced_sql
            if any(t in stmt.lower() for t in forbidden_observed)
        )
    )

    # Positive assertion: every referenced table is allowed.
    unknown = refs_to_check - ALLOWED_TABLES
    assert not unknown, (
        f"unknown table references (not in ALLOWED_TABLES, not "
        f"SQLite metadata): {unknown!r}\n"
        f"Traced SQL: {traced_sql!r}"
    )
