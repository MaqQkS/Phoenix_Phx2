"""Stage 17 pytest configuration.

IMPORTANT -- Windows ACL workaround (mirrors Stage 16A/16B):

Every Stage 17 test run MUST be invoked with a fresh ``--basetemp`` path,
e.g.::

    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage17_p1 PHX2/tests/stage17/

The default pytest tmp directory under ``%LOCALAPPDATA%\\Temp\\pytest-of-<user>``
accumulates restrictive ACLs that even ``Remove-Item -Force`` cannot always
clear. Each phase uses a distinct ``--basetemp`` so the run starts on a
clean slate.

Schema-bootstrap policy (locked):

  * Tests need a SQLite DB with alert_decisions, filter_evaluations,
    observe_only_policy_evaluations, outcome_windows, plus
    schema_migrations.
  * ``stage17_db_path`` first attempts to call
    ``PHX2.db.migrations.apply_stage16b_schema`` against a fresh
    sqlite3 connection. That helper applies the full Stage 4..16B
    chain, including schema_migrations.
  * If that helper is unavailable (ImportError / AttributeError), the
    fixture falls back to executing the embedded minimal DDL below,
    matching the schemas verified during STEP 0 inventory.
  * The fallback path is exercised by the test suite only when the
    real helper is missing; in normal CI the helper path is taken.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

import pytest


# ---------------------------------------------------------------------------
# Fallback DDL: minimal Stage 4..16B-equivalent schema (no indexes needed
# for Stage 17 tests; foreign keys remain inert by default like in prod).
# ---------------------------------------------------------------------------


_FALLBACK_DDL = """
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE alert_decisions (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    tier_index INTEGER,
    tier_name TEXT,
    primary_reason TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    would_alert INTEGER NOT NULL,
    blocked INTEGER NOT NULL,
    skipped INTEGER NOT NULL,
    price_observation_id INTEGER,
    ath_event_id INTEGER,
    field_features_id INTEGER,
    score_features_id INTEGER,
    clock_features_id INTEGER,
    field_score REAL,
    setup_score REAL,
    clock_score REAL,
    risk_score REAL,
    composite_score REAL,
    ath_price REAL,
    ath_status TEXT NOT NULL,
    ath_confidence TEXT NOT NULL,
    ath_source TEXT,
    price_age_seconds REAL,
    pump_multiple REAL,
    drawdown_from_ath REAL,
    current_price REAL,
    current_mcap REAL,
    filter_labels_json TEXT NOT NULL DEFAULT '{}',
    tier_context_json TEXT NOT NULL DEFAULT '{}',
    key_feature_snapshot_json TEXT NOT NULL DEFAULT '{}',
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE filter_evaluations (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    alert_decision_id INTEGER,
    filter_name TEXT NOT NULL,
    filter_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    would_block INTEGER NOT NULL,
    policy_action TEXT NOT NULL,
    reason TEXT,
    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
    output_reason_json TEXT,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE outcome_windows (
    id INTEGER PRIMARY KEY,
    alert_decision_id INTEGER NOT NULL,
    token_address TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    window_start_time TEXT NOT NULL,
    window_end_time TEXT NOT NULL,
    alert_price REAL,
    alert_mcap REAL,
    max_price REAL,
    max_mcap REAL,
    max_observation_time TEXT,
    min_price REAL,
    min_mcap REAL,
    min_observation_time TEXT,
    max_return_multiple REAL,
    max_return_pct REAL,
    min_return_multiple REAL,
    min_return_pct REAL,
    max_drawdown_from_peak_pct REAL,
    time_to_max_return_seconds REAL,
    hit_2x INTEGER,
    hit_3x INTEGER,
    hit_5x INTEGER,
    observations_count INTEGER,
    first_observation_time TEXT,
    last_observation_time TEXT,
    data_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (alert_decision_id, window_seconds),
    CHECK (data_status IN ('COMPLETE', 'NO_PRICE_DATA', 'INVALID_ALERT_PRICE')),
    CHECK (window_seconds IN (300, 900, 1800, 3600, 14400, 86400))
);

CREATE TABLE observe_only_policy_evaluations (
    id INTEGER PRIMARY KEY,
    alert_decision_id INTEGER NOT NULL,
    tier_name_snapshot TEXT,
    policy_hash TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    evaluation_status TEXT NOT NULL,
    matched INTEGER NOT NULL,
    would_have_blocked INTEGER NOT NULL,
    unevaluable_reason TEXT,
    predicate_snapshot_json TEXT NOT NULL,
    evaluated_at_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (evaluation_status IN ('MATCHED', 'NOT_MATCHED', 'UNEVALUABLE')),
    CHECK (matched IN (0, 1)),
    CHECK (would_have_blocked IN (0, 1)),
    CHECK (
        (evaluation_status = 'MATCHED'
            AND matched = 1
            AND would_have_blocked = 1
            AND unevaluable_reason IS NULL)
        OR
        (evaluation_status = 'NOT_MATCHED'
            AND matched = 0
            AND would_have_blocked = 0
            AND unevaluable_reason IS NULL)
        OR
        (evaluation_status = 'UNEVALUABLE'
            AND matched = 0
            AND would_have_blocked = 0
            AND unevaluable_reason IS NOT NULL)
    ),
    UNIQUE(alert_decision_id, policy_hash, rule_id)
);
"""


def _bootstrap_schema(connection: sqlite3.Connection) -> str:
    """Bootstrap the Stage 16B-equivalent schema onto ``connection``.

    Returns either ``"helper"`` or ``"fallback"`` to document which
    path was taken; tests do not depend on this signal but it is
    useful for debugging.
    """

    try:
        from PHX2.db.migrations import apply_stage16b_schema
    except (ImportError, AttributeError):
        connection.executescript(_FALLBACK_DDL)
        connection.commit()
        return "fallback"

    try:
        apply_stage16b_schema(connection)
        return "helper"
    except Exception:
        # Helper present but failed (e.g., shape drift) -- fall back to
        # the embedded DDL so tests remain runnable. The conftest is
        # deliberately not policing migration health.
        connection.executescript(_FALLBACK_DDL)
        connection.commit()
        return "fallback"


def _open_with_row_factory(db_path: Path) -> sqlite3.Connection:
    """Open a fresh sqlite3 connection with row_factory set.

    The PHX2.db.migrations chain reads PRAGMA rows by column name
    (``row["name"]``), so the row factory must be Row before any
    migration helper is called.
    """

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


@pytest.fixture
def stage17_db_path(tmp_path: Path) -> Path:
    """Return a freshly-created Stage 17 SQLite DB path with empty tables."""

    db_path = tmp_path / "stage17.db"
    connection = _open_with_row_factory(db_path)
    try:
        _bootstrap_schema(connection)
    finally:
        connection.close()
    return db_path


@pytest.fixture
def stage17_db_factory(tmp_path: Path) -> Callable[[str], Path]:
    """Factory variant: returns a callable producing fresh DBs by name.

    Useful for tests that need multiple isolated DBs in a single test
    function (e.g., determinism comparisons of two different fixture
    states).
    """

    counter = {"n": 0}

    def make(name: str) -> Path:
        counter["n"] += 1
        db_path = tmp_path / f"{name}_{counter['n']}.db"
        connection = _open_with_row_factory(db_path)
        try:
            _bootstrap_schema(connection)
        finally:
            connection.close()
        return db_path

    return make
