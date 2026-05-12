"""Programmatic substrate-DB builder for Stage 12 tests.

Each helper is an *imperative INSERT*. The functions accept explicit
primary keys (alert_decision_id, etc.) so tests can wire up
deterministic foreign-key relationships without round-tripping
``lastrowid``.

The fixture builder uses the Stage 11 migration to set up the schema.
After construction, callers should close the writable connection and
re-open the DB with ``sqlite3.connect(uri=...mode=ro)`` for read-only
analysis. This is the Stage 12 contract -- the DB is read-only during
a run.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PHX2.db.migrations import apply_stage11_schema


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _bool_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def build_empty_fixture_db(path: Path) -> Path:
    """Create a fresh SQLite DB at ``path`` with Stage 11 schema applied.

    Returns the path. The connection is closed before return.
    """

    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refuses to overwrite existing fixture: {path}")
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage11_schema(connection)
    finally:
        connection.commit()
        connection.close()
    return path


def open_writable_connection(path: Path) -> sqlite3.Connection:
    """Open a writable connection on a fixture DB (for test set-up)."""

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def open_readonly_connection(path: Path) -> sqlite3.Connection:
    """Open the fixture DB read-only, mirroring the Stage 12 CLI."""

    uri = f"file:{Path(path).as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def insert_token_sequence(
    connection: sqlite3.Connection,
    *,
    token_address: str,
    symbol: str | None = None,
    pool_address: str | None = None,
    migration_time: datetime | None = None,
    sequence_phase: str = "post_migration",
    current_status: str = "active",
    data_status: str = "ok",
) -> None:
    now = _utc_iso(datetime.now(timezone.utc))
    connection.execute(
        """
        INSERT INTO token_sequence_state (
            token_address, symbol, pool_address, migration_time,
            sequence_phase, current_status,
            created_at, updated_at,
            data_status, missing_reasons_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')
        """,
        (
            token_address,
            symbol,
            pool_address,
            _utc_iso(migration_time) if migration_time else None,
            sequence_phase,
            current_status,
            now,
            now,
            data_status,
        ),
    )


def insert_alert_decision(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str,
    evaluated_at: datetime,
    decision_type: str = "would_alert",
    tier_index: int | None = 1,
    tier_name: str | None = "T1",
    primary_reason: str = "would_alert",
    would_alert: bool = True,
    blocked: bool = False,
    skipped: bool = False,
    current_price: float | None = 1.0,
    current_mcap: float | None = 100_000.0,
    pump_multiple: float | None = 2.5,
    drawdown_from_ath: float | None = -0.30,
    ath_status: str = "confirmed",
    ath_confidence: str = "high",
    policy_version: str = "phx2-fixture",
    data_status: str = "ok",
    extra: Mapping[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "id": decision_id,
        "token_address": token_address,
        "evaluated_at": _utc_iso(evaluated_at),
        "decision_type": decision_type,
        "tier_index": tier_index,
        "tier_name": tier_name,
        "primary_reason": primary_reason,
        "reasons_json": "[]",
        "would_alert": _bool_int(would_alert),
        "blocked": _bool_int(blocked),
        "skipped": _bool_int(skipped),
        "price_observation_id": None,
        "ath_event_id": None,
        "field_features_id": None,
        "score_features_id": None,
        "clock_features_id": None,
        "field_score": None,
        "setup_score": None,
        "clock_score": None,
        "risk_score": None,
        "composite_score": None,
        "ath_price": None,
        "ath_status": ath_status,
        "ath_confidence": ath_confidence,
        "ath_source": None,
        "price_age_seconds": None,
        "pump_multiple": pump_multiple,
        "drawdown_from_ath": drawdown_from_ath,
        "current_price": current_price,
        "current_mcap": current_mcap,
        "filter_labels_json": "{}",
        "tier_context_json": "{}",
        "key_feature_snapshot_json": "{}",
        "policy_version": policy_version,
        "created_at": _utc_iso(datetime.now(timezone.utc)),
        "data_status": data_status,
        "missing_reasons_json": "[]",
    }
    if extra:
        payload.update(extra)

    columns = list(payload.keys())
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO alert_decisions ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(payload[c] for c in columns),
    )


def insert_filter_evaluation(
    connection: sqlite3.Connection,
    *,
    filter_evaluation_id: int,
    alert_decision_id: int | None,
    token_address: str,
    as_of_time: datetime,
    filter_name: str = "fee_gate",
    filter_version: str = "v1",
    threshold_version: str = "v1",
    label: str = "NORMAL",
    score: float | None = 0.5,
    would_block: bool = False,
    policy_action: str = "allow",
    reason: str | None = None,
    data_status: str = "ok",
) -> None:
    payload: dict[str, Any] = {
        "id": filter_evaluation_id,
        "token_address": token_address,
        "as_of_time": _utc_iso(as_of_time),
        "alert_decision_id": alert_decision_id,
        "filter_name": filter_name,
        "filter_version": filter_version,
        "threshold_version": threshold_version,
        "label": label,
        "score": score,
        "would_block": _bool_int(would_block),
        "policy_action": policy_action,
        "reason": reason,
        "input_snapshot_json": "{}",
        "output_reason_json": None,
        "created_at": _utc_iso(datetime.now(timezone.utc)),
        "data_status": data_status,
        "missing_reasons_json": "[]",
    }
    columns = list(payload.keys())
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO filter_evaluations ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(payload[c] for c in columns),
    )


# Default primitive values used by ``insert_decision_score_features``. A
# fixture caller can override any subset via ``primitive_overrides``.
DEFAULT_DSF_PRIMITIVES: dict[str, Any] = {
    "alert_price": 1.0,
    "alert_market_cap": 100_000.0,
    "ath_price": 1.5,
    "ath_market_cap": 150_000.0,
    "migration_price": 0.5,
    "migration_market_cap": 50_000.0,
    "drop_from_ath": -0.33,
    "multiple_from_migration": 2.0,
    "time_since_migration_seconds": 3600.0,
    "time_since_ath_seconds": 600.0,
    "time_from_migration_to_ath_seconds": 3000.0,
    "liquidity_usd": 10_000.0,
    "event_count_5m": 25,
    "total_fee_5m": 1.5,
    "lp_fee_5m": 1.0,
    "protocol_fee_5m": 0.3,
    "creator_fee_5m": 0.2,
    "creator_fee_share_5m": 0.133,
    "lp_fee_share_5m": 0.667,
    "protocol_fee_share_5m": 0.2,
    "fee_per_event_5m": 0.06,
    "events_per_minute_5m": 5.0,
    "fees_per_minute_5m": 0.3,
}


def insert_decision_score_features(
    connection: sqlite3.Connection,
    *,
    snapshot_id: int,
    alert_decision_id: int,
    token_address: str,
    decision_time: datetime,
    as_of_time: datetime | None = None,
    feature_version: str = "v1",
    schema_version: str = "1",
    token_symbol: str | None = "TOK",
    tier_index: int | None = 1,
    tier_name: str | None = "T1",
    data_status: str = "ok",
    ath_time: datetime | None = None,
    migration_time: datetime | None = None,
    source_snapshot: Mapping[str, Any] | None = None,
    primitive_overrides: Mapping[str, Any] | None = None,
) -> None:
    primitives = dict(DEFAULT_DSF_PRIMITIVES)
    if primitive_overrides:
        primitives.update(primitive_overrides)
    as_of = as_of_time or decision_time
    payload: dict[str, Any] = {
        "id": snapshot_id,
        "alert_decision_id": alert_decision_id,
        "feature_version": feature_version,
        "schema_version": schema_version,
        "token_address": token_address,
        "token_symbol": token_symbol,
        "decision_time": _utc_iso(decision_time),
        "as_of_time": _utc_iso(as_of),
        "tier_index": tier_index,
        "tier_name": tier_name,
        **{
            k: primitives.get(k)
            for k in DEFAULT_DSF_PRIMITIVES.keys()
        },
        "ath_time": _utc_iso(ath_time) if ath_time else None,
        "migration_time": _utc_iso(migration_time) if migration_time else None,
        "source_snapshot_json": json.dumps(source_snapshot or {}),
        "created_at": _utc_iso(datetime.now(timezone.utc)),
        "data_status": data_status,
        "missing_reasons_json": "[]",
    }
    columns = list(payload.keys())
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO decision_score_features ({', '.join(columns)}) "
        f"VALUES ({placeholders})",
        tuple(payload[c] for c in columns),
    )


def insert_outcome_window(
    connection: sqlite3.Connection,
    *,
    outcome_id: int | None = None,
    alert_decision_id: int,
    token_address: str,
    window_seconds: int,
    window_start_time: datetime,
    window_end_time: datetime,
    alert_price: float | None = 1.0,
    alert_mcap: float | None = 100_000.0,
    max_price: float | None = 2.0,
    max_mcap: float | None = 200_000.0,
    max_observation_time: datetime | None = None,
    min_price: float | None = 0.8,
    min_mcap: float | None = 80_000.0,
    min_observation_time: datetime | None = None,
    max_return_multiple: float | None = 2.0,
    max_return_pct: float | None = 100.0,
    min_return_multiple: float | None = 0.8,
    min_return_pct: float | None = -20.0,
    max_drawdown_from_peak_pct: float | None = -10.0,
    time_to_max_return_seconds: float | None = 600.0,
    hit_2x: bool | None = True,
    hit_3x: bool | None = False,
    hit_5x: bool | None = False,
    observations_count: int | None = 30,
    first_observation_time: datetime | None = None,
    last_observation_time: datetime | None = None,
    data_status: str = "COMPLETE",
) -> None:
    payload: dict[str, Any] = {
        "alert_decision_id": alert_decision_id,
        "token_address": token_address,
        "window_seconds": window_seconds,
        "window_start_time": _utc_iso(window_start_time),
        "window_end_time": _utc_iso(window_end_time),
        "alert_price": alert_price,
        "alert_mcap": alert_mcap,
        "max_price": max_price,
        "max_mcap": max_mcap,
        "max_observation_time": _utc_iso(max_observation_time) if max_observation_time else None,
        "min_price": min_price,
        "min_mcap": min_mcap,
        "min_observation_time": _utc_iso(min_observation_time) if min_observation_time else None,
        "max_return_multiple": max_return_multiple,
        "max_return_pct": max_return_pct,
        "min_return_multiple": min_return_multiple,
        "min_return_pct": min_return_pct,
        "max_drawdown_from_peak_pct": max_drawdown_from_peak_pct,
        "time_to_max_return_seconds": time_to_max_return_seconds,
        "hit_2x": _bool_int(hit_2x),
        "hit_3x": _bool_int(hit_3x),
        "hit_5x": _bool_int(hit_5x),
        "observations_count": observations_count,
        "first_observation_time": _utc_iso(first_observation_time) if first_observation_time else None,
        "last_observation_time": _utc_iso(last_observation_time) if last_observation_time else None,
        "data_status": data_status,
        "created_at": _utc_iso(datetime.now(timezone.utc)),
    }
    if outcome_id is not None:
        payload = {"id": outcome_id, **payload}
    columns = list(payload.keys())
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO outcome_windows ({', '.join(columns)}) "
        f"VALUES ({placeholders})",
        tuple(payload[c] for c in columns),
    )


# ---------------------------------------------------------------------------
# Smoke fixture (Phase 2): two decisions, one with filter eval + outcome,
# one bare. Sufficient for the Phase 2 smoke test. Phase 4 builds richer
# fixtures (44-decision canonical) on top of these helpers.
# ---------------------------------------------------------------------------


def build_smoke_fixture(path: Path) -> Path:
    """Two-decision smoke fixture for Phase 2.

    Decision 1001:
      tier T1, has 1 filter evaluation, has DSF row, has 24h outcome
      row with data_status=COMPLETE, hit_2x=True.
    Decision 1002:
      tier T2, NO filter evaluation, NO DSF row, NO outcome row.
    """

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        eval_time_1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        eval_time_2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        insert_token_sequence(
            connection,
            token_address="TOKEN_A",
            symbol="A_SYM",
            migration_time=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        )
        insert_token_sequence(
            connection,
            token_address="TOKEN_B",
            symbol="B_SYM",
            migration_time=datetime(2026, 1, 2, 11, 0, 0, tzinfo=timezone.utc),
        )

        insert_alert_decision(
            connection,
            decision_id=1001,
            token_address="TOKEN_A",
            evaluated_at=eval_time_1,
            tier_index=1,
            tier_name="T1",
        )
        insert_filter_evaluation(
            connection,
            filter_evaluation_id=5001,
            alert_decision_id=1001,
            token_address="TOKEN_A",
            as_of_time=eval_time_1,
            filter_name="fee_gate",
            filter_version="v1",
            threshold_version="v1",
            label="NORMAL",
            score=0.4,
            would_block=False,
        )
        insert_decision_score_features(
            connection,
            snapshot_id=9001,
            alert_decision_id=1001,
            token_address="TOKEN_A",
            decision_time=eval_time_1,
            token_symbol="A_SYM",
            tier_index=1,
            tier_name="T1",
            ath_time=datetime(2026, 1, 1, 11, 50, 0, tzinfo=timezone.utc),
            migration_time=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        )
        insert_outcome_window(
            connection,
            alert_decision_id=1001,
            token_address="TOKEN_A",
            window_seconds=86400,
            window_start_time=eval_time_1,
            window_end_time=eval_time_1.replace(day=2),
            data_status="COMPLETE",
            hit_2x=True,
            hit_3x=False,
            hit_5x=False,
            max_return_multiple=2.3,
            max_drawdown_from_peak_pct=-12.0,
        )

        insert_alert_decision(
            connection,
            decision_id=1002,
            token_address="TOKEN_B",
            evaluated_at=eval_time_2,
            tier_index=2,
            tier_name="T2",
        )

        connection.commit()
    finally:
        connection.close()
    return path


# ---------------------------------------------------------------------------
# Phase 4 composable scenario helpers + 44-decision canonical fixture
# ---------------------------------------------------------------------------


# Each ``add_*`` helper writes one self-contained scenario through a
# writable connection. Helpers compose: a test can call exactly the
# scenarios it needs, and ``build_canonical_fixture`` calls them in
# sequence to assemble the full 44-decision corpus.


def add_decision_complete_outcome(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str,
    evaluated_at: datetime,
    tier_index: int,
    tier_name: str,
    snapshot_id: int,
    outcome_max_return_multiple: float = 2.3,
    outcome_max_drawdown_from_peak_pct: float = -12.0,
    hit_2x: bool = True,
    hit_3x: bool = False,
    hit_5x: bool = False,
    token_symbol: str | None = None,
    primitive_overrides: Mapping[str, Any] | None = None,
) -> None:
    """One WOULD_ALERT decision with DSF + COMPLETE 24h outcome."""

    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=evaluated_at,
        tier_index=tier_index,
        tier_name=tier_name,
    )
    insert_decision_score_features(
        connection,
        snapshot_id=snapshot_id,
        alert_decision_id=decision_id,
        token_address=token_address,
        decision_time=evaluated_at,
        token_symbol=token_symbol,
        tier_index=tier_index,
        tier_name=tier_name,
        primitive_overrides=primitive_overrides,
    )
    insert_outcome_window(
        connection,
        alert_decision_id=decision_id,
        token_address=token_address,
        window_seconds=86400,
        window_start_time=evaluated_at,
        window_end_time=evaluated_at + timedelta(seconds=86400),
        data_status="COMPLETE",
        hit_2x=hit_2x,
        hit_3x=hit_3x,
        hit_5x=hit_5x,
        max_return_multiple=outcome_max_return_multiple,
        max_drawdown_from_peak_pct=outcome_max_drawdown_from_peak_pct,
    )


def add_decision_censored_outcome(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str,
    evaluated_at: datetime,
    tier_index: int,
    tier_name: str,
    snapshot_id: int,
    censor_status: str = "NO_PRICE_DATA",
    token_symbol: str | None = None,
    primitive_overrides: Mapping[str, Any] | None = None,
) -> None:
    """One WOULD_ALERT decision with a 24h row whose data_status is not
    COMPLETE (i.e., the window elapsed but was unmeasurable). Includes
    a DSF row."""

    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=evaluated_at,
        tier_index=tier_index,
        tier_name=tier_name,
    )
    insert_decision_score_features(
        connection,
        snapshot_id=snapshot_id,
        alert_decision_id=decision_id,
        token_address=token_address,
        decision_time=evaluated_at,
        token_symbol=token_symbol,
        tier_index=tier_index,
        tier_name=tier_name,
        primitive_overrides=primitive_overrides,
    )
    insert_outcome_window(
        connection,
        alert_decision_id=decision_id,
        token_address=token_address,
        window_seconds=86400,
        window_start_time=evaluated_at,
        window_end_time=evaluated_at + timedelta(seconds=86400),
        data_status=censor_status,
        # All outcome metrics NULL for non-COMPLETE rows.
        max_price=None,
        max_mcap=None,
        min_price=None,
        min_mcap=None,
        max_return_multiple=None,
        max_return_pct=None,
        min_return_multiple=None,
        min_return_pct=None,
        max_drawdown_from_peak_pct=None,
        time_to_max_return_seconds=None,
        hit_2x=None,
        hit_3x=None,
        hit_5x=None,
        observations_count=0,
    )


def add_decision_no_outcome(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str,
    evaluated_at: datetime,
    tier_index: int,
    tier_name: str,
    snapshot_id: int | None = None,
    token_symbol: str | None = None,
    primitive_overrides: Mapping[str, Any] | None = None,
) -> None:
    """One WOULD_ALERT decision with NO outcome_windows row.

    DSF is included by default (pass ``snapshot_id=None`` to skip).
    """

    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=evaluated_at,
        tier_index=tier_index,
        tier_name=tier_name,
    )
    if snapshot_id is not None:
        insert_decision_score_features(
            connection,
            snapshot_id=snapshot_id,
            alert_decision_id=decision_id,
            token_address=token_address,
            decision_time=evaluated_at,
            token_symbol=token_symbol,
            tier_index=tier_index,
            tier_name=tier_name,
            primitive_overrides=primitive_overrides,
        )


def add_filter_eval(
    connection: sqlite3.Connection,
    *,
    filter_evaluation_id: int,
    alert_decision_id: int,
    token_address: str,
    as_of_time: datetime,
    filter_name: str = "fee_gate",
    filter_version: str = "v1",
    threshold_version: str = "v1",
    label: str = "NORMAL",
    score: float | None = 0.4,
    would_block: bool = False,
) -> None:
    """Attach a filter evaluation to an existing decision."""

    insert_filter_evaluation(
        connection,
        filter_evaluation_id=filter_evaluation_id,
        alert_decision_id=alert_decision_id,
        token_address=token_address,
        as_of_time=as_of_time,
        filter_name=filter_name,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
        score=score,
        would_block=would_block,
    )


def add_non_would_alert_decision(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str,
    evaluated_at: datetime,
    decision_type: str = "skip",
    tier_index: int | None = None,
    tier_name: str | None = None,
    primary_reason: str = "policy_disabled",
) -> None:
    """A SKIP or BLOCK decision (not WOULD_ALERT). Used by TEST 8 and
    TEST 12 to verify the decision_type filter behavior."""

    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=evaluated_at,
        decision_type=decision_type,
        tier_index=tier_index,
        tier_name=tier_name,
        primary_reason=primary_reason,
        would_alert=False,
    )


# ---------------------------------------------------------------------------
# Canonical 44-decision fixture
# ---------------------------------------------------------------------------


CANONICAL_BASE_TIME = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)


# Tier composition (totals 44):
#   T1: 18 decisions  (deterministic id range 2001..2018)
#   T2: 16 decisions  (2019..2034)
#   T3: 10 decisions  (2035..2044)
# Each tier mixes complete / censored / no_outcome and with/without DSF
# and with/without filter evaluations to satisfy the §8 test corpus.


def _spread_decision_minute(idx: int) -> datetime:
    """Deterministic decision-time spread: 5 minutes per decision."""

    return CANONICAL_BASE_TIME + timedelta(minutes=5 * idx)


def _varied_primitives(global_idx: int, tier: int) -> dict[str, Any]:
    """Build a uniformly-varied DSF primitive override dict.

    Every numeric primitive declared in ``DEFAULT_DSF_PRIMITIVES`` is
    given an idx-dependent value so the canonical fixture exercises
    quartile bucketing on EVERY Stage 11 primitive (per Phase 5
    inspection requirement). Each tier gets a different multiplier
    to ensure pooled-population variance + within-tier variance.

    Deterministic: same (global_idx, tier) -> same dict.
    """

    g = float(global_idx)
    t = float(tier)
    # The two domain-bucketed primitives use the same domain bucket
    # ranges across tiers; keep them in [0h..72h+] / [0m..24h+].
    return {
        "alert_price":                       0.5 + 0.05 * g,
        "alert_market_cap":              30_000.0 + 2_000.0 * g,
        "ath_price":                         0.8 + 0.04 * g,
        "ath_market_cap":                80_000.0 + 3_000.0 * g,
        "migration_price":                   0.3 + 0.02 * g,
        "migration_market_cap":          30_000.0 + 1_500.0 * g,
        "drop_from_ath":                   -0.20 - 0.015 * g,
        "multiple_from_migration":           1.5 + 0.1 * g,
        "time_since_migration_seconds":  600.0 + 1_000.0 * g + 20_000.0 * t,
        "time_since_ath_seconds":         60.0 + 80.0 * g + 200.0 * t,
        "time_from_migration_to_ath_seconds": 100.0 + 50.0 * g,
        "liquidity_usd":                  5_000.0 + 500.0 * g,
        "event_count_5m":                       5 + global_idx,
        "total_fee_5m":                      0.5 + 0.05 * g,
        "lp_fee_5m":                         0.3 + 0.03 * g,
        "protocol_fee_5m":                   0.1 + 0.012 * g,
        "creator_fee_5m":                   0.05 + 0.005 * g,
        "creator_fee_share_5m":             0.05 + 0.005 * g,
        "lp_fee_share_5m":                   0.5 + 0.01 * g,
        "protocol_fee_share_5m":            0.15 + 0.005 * g,
        "fee_per_event_5m":                 0.03 + 0.002 * g,
        "events_per_minute_5m":              2.0 + 0.2 * g,
        "fees_per_minute_5m":                0.1 + 0.01 * g,
    }


def _t1_block(connection: sqlite3.Connection) -> None:
    """Tier 1: 18 decisions.

    Composition:
      ids 2001..2010 -- COMPLETE outcome, varied DSF primitive values
                        (used by TEST 6 quartile bucketing). 8 of these
                        attach a filter eval; 2 do not.
      ids 2011..2014 -- CENSORED outcome (NO_PRICE_DATA / INVALID_ALERT_PRICE)
                        2 each. With filter eval, with DSF.
      ids 2015..2018 -- NO_OUTCOME (no 24h row). 2 with DSF, 2 without DSF.
                        Each pair: one with filter, one without.
    """

    base_snap = 7000
    base_filter = 8000

    # 2001..2010: complete outcomes, varied primitive values across
    # quartiles. Every Stage 11 numeric primitive is varied via
    # _varied_primitives so the canonical fixture exercises quartile
    # bucketing across the full primitive set (Phase 5 sample-run
    # requirement).
    for i in range(10):
        decision_id = 2001 + i
        evaluated_at = _spread_decision_minute(i)
        primitives = _varied_primitives(global_idx=i, tier=1)
        add_decision_complete_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T1_{i:03d}",
            evaluated_at=evaluated_at,
            tier_index=1,
            tier_name="T1",
            snapshot_id=base_snap + i,
            outcome_max_return_multiple=2.0 + 0.3 * i,
            outcome_max_drawdown_from_peak_pct=-10.0 - i,
            hit_2x=(i % 2 == 0),  # half hit, half miss
            hit_3x=(i == 0),
            hit_5x=False,
            token_symbol=f"SYM_T1_{i}",
            primitive_overrides=primitives,
        )
        if i < 8:  # 8 of 10 get a filter eval
            label = "NORMAL" if i % 2 == 0 else "ELEVATED"
            add_filter_eval(
                connection,
                filter_evaluation_id=base_filter + i,
                alert_decision_id=decision_id,
                token_address=f"TKN_T1_{i:03d}",
                as_of_time=evaluated_at,
                label=label,
            )

    # 2011..2014: censored outcomes (2 NO_PRICE_DATA + 2 INVALID_ALERT_PRICE)
    for i, status in enumerate(
        ["NO_PRICE_DATA", "NO_PRICE_DATA", "INVALID_ALERT_PRICE", "INVALID_ALERT_PRICE"]
    ):
        decision_id = 2011 + i
        evaluated_at = _spread_decision_minute(10 + i)
        add_decision_censored_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T1_C{i:02d}",
            evaluated_at=evaluated_at,
            tier_index=1,
            tier_name="T1",
            snapshot_id=base_snap + 10 + i,
            censor_status=status,
            token_symbol=f"SYM_T1_C{i}",
            primitive_overrides=_varied_primitives(global_idx=10 + i, tier=1),
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=base_filter + 10 + i,
            alert_decision_id=decision_id,
            token_address=f"TKN_T1_C{i:02d}",
            as_of_time=evaluated_at,
            label="ELEVATED",
        )

    # 2015..2018: no-outcome (no 24h row). Half have DSF, half do not.
    for i in range(4):
        decision_id = 2015 + i
        evaluated_at = _spread_decision_minute(14 + i)
        token_address = f"TKN_T1_N{i:02d}"
        with_dsf = i < 2
        add_decision_no_outcome(
            connection,
            decision_id=decision_id,
            token_address=token_address,
            evaluated_at=evaluated_at,
            tier_index=1,
            tier_name="T1",
            snapshot_id=(base_snap + 14 + i) if with_dsf else None,
            token_symbol=f"SYM_T1_N{i}" if with_dsf else None,
            primitive_overrides=(
                _varied_primitives(global_idx=14 + i, tier=1) if with_dsf else None
            ),
        )
        if i % 2 == 0:
            add_filter_eval(
                connection,
                filter_evaluation_id=base_filter + 14 + i,
                alert_decision_id=decision_id,
                token_address=token_address,
                as_of_time=evaluated_at,
                label="NORMAL",
            )


def _t2_block(connection: sqlite3.Connection) -> None:
    """Tier 2: 16 decisions, similar mix shifted to T2 with different
    primitive ranges."""

    base_snap = 7100
    base_filter = 8100
    base_idx = 18  # T1 used minutes 0..17

    # 2019..2030: COMPLETE outcomes. 12 of them with varied primitives.
    for i in range(12):
        decision_id = 2019 + i
        evaluated_at = _spread_decision_minute(base_idx + i)
        primitives = _varied_primitives(global_idx=base_idx + i, tier=2)
        add_decision_complete_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T2_{i:03d}",
            evaluated_at=evaluated_at,
            tier_index=2,
            tier_name="T2",
            snapshot_id=base_snap + i,
            outcome_max_return_multiple=1.5 + 0.2 * i,
            outcome_max_drawdown_from_peak_pct=-15.0 - 0.5 * i,
            hit_2x=(i < 4),  # 4 of 12 hit
            hit_3x=False,
            hit_5x=False,
            token_symbol=f"SYM_T2_{i}",
            primitive_overrides=primitives,
        )
        if i < 9:  # 9 of 12 have a filter eval
            if i % 3 == 0:
                label = "NORMAL"
            elif i % 3 == 1:
                label = "ELEVATED"
            else:
                label = "SUSPICIOUS"
            # M-1 remediation: decisions 2022 and 2025 (i == 3 and i == 6,
            # both NORMAL) get threshold_version="v2" so the canonical
            # fixture exercises the threshold_version partition in the
            # filter cohort tables. All other filter evals stay on the
            # default "v1" threshold.
            threshold_version = "v2" if i in (3, 6) else "v1"
            add_filter_eval(
                connection,
                filter_evaluation_id=base_filter + i,
                alert_decision_id=decision_id,
                token_address=f"TKN_T2_{i:03d}",
                as_of_time=evaluated_at,
                label=label,
                threshold_version=threshold_version,
            )

    # 2031..2032: censored
    for i in range(2):
        decision_id = 2031 + i
        evaluated_at = _spread_decision_minute(base_idx + 12 + i)
        add_decision_censored_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T2_C{i:02d}",
            evaluated_at=evaluated_at,
            tier_index=2,
            tier_name="T2",
            snapshot_id=base_snap + 12 + i,
            censor_status="NO_PRICE_DATA",
            primitive_overrides=_varied_primitives(
                global_idx=base_idx + 12 + i, tier=2
            ),
        )

    # 2033..2034: no outcome
    for i in range(2):
        decision_id = 2033 + i
        evaluated_at = _spread_decision_minute(base_idx + 14 + i)
        add_decision_no_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T2_N{i:02d}",
            evaluated_at=evaluated_at,
            tier_index=2,
            tier_name="T2",
            snapshot_id=base_snap + 14 + i,
            primitive_overrides=_varied_primitives(
                global_idx=base_idx + 14 + i, tier=2
            ),
        )


def _t3_block(connection: sqlite3.Connection) -> None:
    """Tier 3: 10 decisions."""

    base_snap = 7200
    base_filter = 8200
    base_idx = 18 + 16  # T1 used 18 indices, T2 used 16

    # 2035..2042: COMPLETE outcomes, 8 decisions
    for i in range(8):
        decision_id = 2035 + i
        evaluated_at = _spread_decision_minute(base_idx + i)
        primitives = _varied_primitives(global_idx=base_idx + i, tier=3)
        add_decision_complete_outcome(
            connection,
            decision_id=decision_id,
            token_address=f"TKN_T3_{i:03d}",
            evaluated_at=evaluated_at,
            tier_index=3,
            tier_name="T3",
            snapshot_id=base_snap + i,
            outcome_max_return_multiple=2.5 + 0.15 * i,
            outcome_max_drawdown_from_peak_pct=-20.0 - 0.2 * i,
            hit_2x=(i % 2 == 1),
            hit_3x=(i == 1),
            hit_5x=False,
            token_symbol=f"SYM_T3_{i}",
            primitive_overrides=primitives,
        )
        if i < 5:
            add_filter_eval(
                connection,
                filter_evaluation_id=base_filter + i,
                alert_decision_id=decision_id,
                token_address=f"TKN_T3_{i:03d}",
                as_of_time=evaluated_at,
                label="NORMAL" if i % 2 == 0 else "SUSPICIOUS",
            )

    # 2043: censored
    decision_id = 2043
    evaluated_at = _spread_decision_minute(base_idx + 8)
    add_decision_censored_outcome(
        connection,
        decision_id=decision_id,
        token_address="TKN_T3_C00",
        evaluated_at=evaluated_at,
        tier_index=3,
        tier_name="T3",
        snapshot_id=base_snap + 8,
        censor_status="NO_PRICE_DATA",
        primitive_overrides=_varied_primitives(global_idx=base_idx + 8, tier=3),
    )

    # 2044: no outcome, no DSF
    decision_id = 2044
    evaluated_at = _spread_decision_minute(base_idx + 9)
    add_decision_no_outcome(
        connection,
        decision_id=decision_id,
        token_address="TKN_T3_N00",
        evaluated_at=evaluated_at,
        tier_index=3,
        tier_name="T3",
        snapshot_id=None,
    )


def build_canonical_fixture(path: Path) -> Path:
    """Build the 44-decision canonical Stage 12 fixture.

    Composition (totals 44):
      T1: 18 decisions (10 COMPLETE, 4 CENSORED, 4 NO_OUTCOME)
      T2: 16 decisions (12 COMPLETE, 2 CENSORED, 2 NO_OUTCOME)
      T3: 10 decisions (8  COMPLETE, 1 CENSORED, 1 NO_OUTCOME)

    Filter evaluations attached to 22 of 44 decisions across the three
    label values NORMAL / ELEVATED / SUSPICIOUS.

    DSF rows attached to 41 of 44 (two T1 no-outcome decisions and one
    T3 no-outcome decision deliberately have no DSF).

    Primitive values vary across each tier, giving enough distinct
    values for quartile bucketing on a population pooled across tiers
    (>= 4 distinct values per primitive).
    """

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        # token_sequence_state rows: the canonical fixture uses DSF's
        # frozen token_symbol; token_sequence_state.symbol is reserved
        # for the no-DSF decisions (for symbol-fallback test coverage).
        for tier_letter, count in (("T1", 18), ("T2", 16), ("T3", 10)):
            # Token addresses written by the block helpers above.
            # For the no-DSF cases, the long CSV looks up
            # token_sequence_state.symbol; populate it.
            pass  # populated per-decision below if needed

        _t1_block(connection)
        _t2_block(connection)
        _t3_block(connection)

        # Token-sequence symbols for the no-DSF decisions. The two T1
        # no-DSF decisions are 2017 and 2018 (token addresses
        # TKN_T1_N02 / TKN_T1_N03); the one T3 no-DSF decision is 2044
        # (token address TKN_T3_N00).
        insert_token_sequence(
            connection,
            token_address="TKN_T1_N02",
            symbol="TS_FALLBACK_T1A",
        )
        insert_token_sequence(
            connection,
            token_address="TKN_T1_N03",
            symbol="TS_FALLBACK_T1B",
        )
        insert_token_sequence(
            connection,
            token_address="TKN_T3_N00",
            symbol="TS_FALLBACK_T3",
        )

        connection.commit()
    finally:
        connection.close()
    return path


# ---------------------------------------------------------------------------
# Narrow fixtures for single-behavior regression tests
# ---------------------------------------------------------------------------


def build_join_cardinality_fixture(path: Path) -> Path:
    """TEST 2 fixture: A (1 filter eval), B (2 filter evals), C (0)."""

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        eval_a = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        eval_b = datetime(2026, 4, 1, 0, 5, 0, tzinfo=timezone.utc)
        eval_c = datetime(2026, 4, 1, 0, 10, 0, tzinfo=timezone.utc)

        add_decision_complete_outcome(
            connection,
            decision_id=3001,  # A
            token_address="TKN_A",
            evaluated_at=eval_a,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4001,
            token_symbol="A_SYM",
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5001,
            alert_decision_id=3001,
            token_address="TKN_A",
            as_of_time=eval_a,
            filter_name="fee_gate",
            filter_version="v1",
        )

        add_decision_complete_outcome(
            connection,
            decision_id=3002,  # B (2 filter evals)
            token_address="TKN_B",
            evaluated_at=eval_b,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4002,
            token_symbol="B_SYM",
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5002,
            alert_decision_id=3002,
            token_address="TKN_B",
            as_of_time=eval_b,
            filter_name="fee_gate",
            filter_version="v1",
            label="ELEVATED",
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5003,
            alert_decision_id=3002,
            token_address="TKN_B",
            as_of_time=eval_b,
            filter_name="creator_share_gate",
            filter_version="v1",
            label="SUSPICIOUS",
        )

        add_decision_complete_outcome(
            connection,
            decision_id=3003,  # C (no filter eval)
            token_address="TKN_C",
            evaluated_at=eval_c,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4003,
            token_symbol="C_SYM",
        )

        connection.commit()
    finally:
        connection.close()
    return path


def build_censoring_fixture(path: Path) -> Path:
    """TEST 3 fixture: A (COMPLETE, hit_2x=True), B (censored)."""

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        eval_a = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)
        eval_b = datetime(2026, 4, 2, 0, 5, 0, tzinfo=timezone.utc)
        add_decision_complete_outcome(
            connection,
            decision_id=3101,
            token_address="TKN_A",
            evaluated_at=eval_a,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4101,
            hit_2x=True,
            outcome_max_return_multiple=2.5,
            outcome_max_drawdown_from_peak_pct=-10.0,
            token_symbol="A_SYM",
        )
        add_decision_censored_outcome(
            connection,
            decision_id=3102,
            token_address="TKN_B",
            evaluated_at=eval_b,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4102,
            censor_status="NO_PRICE_DATA",
            token_symbol="B_SYM",
        )
        connection.commit()
    finally:
        connection.close()
    return path


def build_missing_data_fixture(path: Path) -> Path:
    """TEST 4 fixture: decisions with various missing-data shapes."""

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        base = datetime(2026, 4, 3, 0, 0, 0, tzinfo=timezone.utc)
        # 3201: full row (filter + DSF + COMPLETE outcome)
        add_decision_complete_outcome(
            connection,
            decision_id=3201,
            token_address="TKN_FULL",
            evaluated_at=base,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4201,
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5201,
            alert_decision_id=3201,
            token_address="TKN_FULL",
            as_of_time=base,
        )
        # 3202: NO DSF row, but has filter eval and COMPLETE outcome
        add_decision_no_outcome(  # use no_outcome helper then add manual outcome
            connection,
            decision_id=3202,
            token_address="TKN_NO_DSF",
            evaluated_at=base + timedelta(minutes=5),
            tier_index=1,
            tier_name="T1",
            snapshot_id=None,
        )
        insert_outcome_window(
            connection,
            alert_decision_id=3202,
            token_address="TKN_NO_DSF",
            window_seconds=86400,
            window_start_time=base + timedelta(minutes=5),
            window_end_time=base + timedelta(minutes=5, seconds=86400),
            data_status="COMPLETE",
            hit_2x=False,
            max_return_multiple=1.5,
            max_drawdown_from_peak_pct=-25.0,
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5202,
            alert_decision_id=3202,
            token_address="TKN_NO_DSF",
            as_of_time=base + timedelta(minutes=5),
        )
        insert_token_sequence(
            connection, token_address="TKN_NO_DSF", symbol="NO_DSF_TS"
        )

        # 3203: DSF + no filter + COMPLETE outcome
        add_decision_complete_outcome(
            connection,
            decision_id=3203,
            token_address="TKN_NO_FILTER",
            evaluated_at=base + timedelta(minutes=10),
            tier_index=1,
            tier_name="T1",
            snapshot_id=4203,
        )
        # No filter eval inserted.

        # 3204: DSF + filter + no outcome row
        add_decision_no_outcome(
            connection,
            decision_id=3204,
            token_address="TKN_NO_OUT",
            evaluated_at=base + timedelta(minutes=15),
            tier_index=1,
            tier_name="T1",
            snapshot_id=4204,
        )
        add_filter_eval(
            connection,
            filter_evaluation_id=5204,
            alert_decision_id=3204,
            token_address="TKN_NO_OUT",
            as_of_time=base + timedelta(minutes=15),
        )

        connection.commit()
    finally:
        connection.close()
    return path


def build_empty_substrate_fixture(path: Path) -> Path:
    """TEST 8 fixture: only non-WOULD_ALERT decisions (SKIP / BLOCK).

    Verifies the status filter screens these out and the pipeline emits
    empty CSVs with headers only.
    """

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        base = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        for i, dtype in enumerate(("skip", "block", "skip")):
            add_non_would_alert_decision(
                connection,
                decision_id=3301 + i,
                token_address=f"TKN_X{i}",
                evaluated_at=base + timedelta(minutes=i),
                decision_type=dtype,
                tier_index=1,
                tier_name="T1",
                primary_reason="policy_disabled" if dtype == "skip" else "filter_blocked",
            )
        connection.commit()
    finally:
        connection.close()
    return path


def build_time_range_fixture(path: Path) -> Path:
    """TEST 12 fixture: decisions at t1, t2, t3."""

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        t1 = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 1, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        for idx, (decision_id, eval_at) in enumerate(
            [(3401, t1), (3402, t2), (3403, t3)], start=1
        ):
            add_decision_complete_outcome(
                connection,
                decision_id=decision_id,
                token_address=f"TKN_TR_{idx}",
                evaluated_at=eval_at,
                tier_index=1,
                tier_name="T1",
                snapshot_id=4400 + idx,
            )
        connection.commit()
    finally:
        connection.close()
    return path


def build_null_symbol_fixture(path: Path) -> Path:
    """NULL-symbol regression fixture.

    Decision A: DSF row exists with token_symbol=NULL;
                token_sequence_state.symbol exists = "TESTSYM".
                Expected long-CSV symbol: NULL (not "TESTSYM").
    Decision B: NO DSF row; token_sequence_state.symbol = "FALLBACK".
                Expected long-CSV symbol: "FALLBACK".
    """

    build_empty_fixture_db(path)
    connection = open_writable_connection(path)
    try:
        eval_a = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        eval_b = datetime(2026, 6, 1, 0, 5, 0, tzinfo=timezone.utc)

        # Case A: token_sequence_state has TESTSYM, but DSF token_symbol
        # is explicitly NULL.
        insert_token_sequence(
            connection,
            token_address="TKN_NULLA",
            symbol="TESTSYM",
        )
        add_decision_complete_outcome(
            connection,
            decision_id=3501,
            token_address="TKN_NULLA",
            evaluated_at=eval_a,
            tier_index=1,
            tier_name="T1",
            snapshot_id=4501,
            token_symbol=None,  # <-- explicitly NULL in DSF
        )

        # Case B: token_sequence_state has FALLBACK, no DSF row.
        insert_token_sequence(
            connection,
            token_address="TKN_NULLB",
            symbol="FALLBACK",
        )
        add_decision_no_outcome(
            connection,
            decision_id=3502,
            token_address="TKN_NULLB",
            evaluated_at=eval_b,
            tier_index=1,
            tier_name="T1",
            snapshot_id=None,  # <-- no DSF
        )

        connection.commit()
    finally:
        connection.close()
    return path
