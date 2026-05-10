"""PHX2 SQLite schema migrations.

Stage 4 creates PHX2 dry-run tables only. It does not import Phoenix1 database
modules, mutate Phoenix1 tables, implement strategy logic, or send messages.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Union

from PHX2.config.settings import PHX2DryRunDbSettings, PHX2Settings
from PHX2.db.connection import get_phx2_connection


STAGE_4A_VERSION = "stage_4a_core_telemetry"
STAGE_4B_VERSION = "stage_4b_field_score_clock"
STAGE_5A_VERSION = "stage_5a_raw_pumpswap_events"
STAGE_5C1_VERSION = "stage_5c1_price_curve_points"
STAGE_9A_VERSION = "stage_9a_alert_decision_current_price"
STAGE_9B_VERSION = "stage_9b_outcome_windows_recreate"


CORE_TELEMETRY_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    description TEXT NOT NULL,
    script_name TEXT,
    checksum TEXT,
    applied_at TEXT NOT NULL,
    success INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS token_sequence_state (
    token_address TEXT PRIMARY KEY,
    symbol TEXT,
    pool_address TEXT,
    migration_time TEXT,
    migration_source TEXT,
    migration_price REAL,
    migration_mcap REAL,
    current_price REAL,
    current_mcap REAL,
    last_price_update TEXT,
    sequence_phase TEXT NOT NULL DEFAULT 'unknown',
    current_status TEXT NOT NULL DEFAULT 'unknown',
    last_alerted_tier INTEGER,
    last_migration_event_id INTEGER,
    last_price_observation_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS migration_events (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    pool_address TEXT,
    migration_time TEXT,
    migration_source TEXT,
    signature TEXT,
    slot INTEGER,
    block_time TEXT,
    migration_price REAL,
    migration_mcap REAL,
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    price REAL,
    mcap REAL,
    liquidity_usd REAL,
    source_timestamp TEXT,
    age_seconds REAL,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS ath_state (
    token_address TEXT PRIMARY KEY,
    ath_price REAL,
    ath_mcap REAL,
    ath_time TEXT,
    ath_status TEXT NOT NULL,
    ath_confidence TEXT NOT NULL,
    ath_source TEXT,
    ath_source_priority INTEGER,
    last_event_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS ath_events (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    event_time TEXT NOT NULL,
    price_observation_id INTEGER,
    candidate_price REAL,
    candidate_mcap REAL,
    candidate_source TEXT,
    candidate_source_priority INTEGER,
    prior_ath_price REAL,
    prior_ath_mcap REAL,
    new_ath_price REAL,
    new_ath_mcap REAL,
    status_before TEXT NOT NULL,
    status_after TEXT NOT NULL,
    confidence_before TEXT NOT NULL,
    confidence_after TEXT NOT NULL,
    mutation_type TEXT NOT NULL,
    reason TEXT,
    accepted INTEGER NOT NULL,
    data_limited INTEGER NOT NULL,
    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS alert_decisions (
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

CREATE TABLE IF NOT EXISTS filter_evaluations (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    alert_decision_id INTEGER,
    filter_name TEXT NOT NULL,
    filter_version TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    would_block INTEGER NOT NULL,
    policy_action TEXT NOT NULL,
    reason TEXT,
    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS dispatch_events (
    id TEXT PRIMARY KEY,
    alert_decision_id INTEGER NOT NULL,
    dispatch_run_id TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    tier_label TEXT,
    attempted_at TEXT NOT NULL,
    completed_at TEXT,
    payload_ref TEXT,
    error_message TEXT,
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
);
"""


RESEARCH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fee_windows (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    pool_address TEXT,
    as_of_time TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    first_event_time TEXT,
    last_event_time TEXT,
    event_count INTEGER,
    buy_count INTEGER,
    sell_count INTEGER,
    total_fee_sol REAL,
    lp_fee_sol REAL,
    protocol_fee_sol REAL,
    creator_fee_sol REAL,
    creator_fee_share REAL,
    lp_fee_share REAL,
    protocol_fee_share REAL,
    avg_fee_per_event_sol REAL,
    median_fee_per_event_sol REAL,
    max_fee_event_sol REAL,
    events_per_min REAL,
    fees_per_min_sol REAL,
    buy_sell_count_ratio REAL,
    buy_sell_fee_ratio REAL,
    source_min_id INTEGER,
    source_max_id INTEGER,
    source_row_count INTEGER,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(token_address, as_of_time, window_seconds)
);

CREATE TABLE IF NOT EXISTS field_features (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    fee_window_60s_id INTEGER,
    fee_window_300s_id INTEGER,
    fee_window_900s_id INTEGER,
    fee_window_1800s_id INTEGER,
    fee_window_3600s_id INTEGER,
    liquidity_usd REAL,
    lp_floor_label TEXT,
    lp_fragility_score REAL,
    fee_gate_label TEXT,
    fee_gate_score REAL,
    ante_label_5m TEXT,
    ante_label_20sw TEXT,
    ghost_label TEXT,
    holder_label TEXT,
    event_pace_5m REAL,
    fee_pace_5m_sol REAL,
    creator_fee_share_5m REAL,
    lp_fee_share_5m REAL,
    protocol_fee_share_5m REAL,
    buy_sell_ratio_5m REAL,
    raw_snapshot_json TEXT NOT NULL DEFAULT '{}',
    feature_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(token_address, as_of_time, feature_version)
);

CREATE TABLE IF NOT EXISTS score_features (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    score_version TEXT NOT NULL,
    field_score REAL,
    setup_score REAL,
    clock_score REAL,
    risk_score REAL,
    composite_score REAL,
    pump_multiple REAL,
    drawdown_from_ath REAL,
    ath_quality_score REAL,
    price_freshness_score REAL,
    liquidity_quality_score REAL,
    fee_quality_score REAL,
    participation_quality_score REAL,
    organic_risk_score REAL,
    scam_risk_score REAL,
    dip_speed_score REAL,
    support_reclaim_quality_score REAL,
    components_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(token_address, as_of_time, score_version)
);

CREATE TABLE IF NOT EXISTS clock_features (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    migration_time TEXT,
    age_since_migration_s REAL,
    ath_time TEXT,
    time_to_ath_s REAL,
    time_since_ath_s REAL,
    tier_1_time TEXT,
    tier_2_time TEXT,
    tier_3_time TEXT,
    time_ath_to_t1_s REAL,
    time_ath_to_t2_s REAL,
    time_ath_to_t3_s REAL,
    time_t1_to_t2_s REAL,
    time_t2_to_t3_s REAL,
    dip_velocity_pct_per_min REAL,
    recovery_velocity_pct_per_min REAL,
    last_fee_event_time TEXT,
    last_buy_time TEXT,
    last_sell_time TEXT,
    time_since_last_fee_event_s REAL,
    time_since_last_buy_s REAL,
    time_since_last_sell_s REAL,
    sequence_phase TEXT NOT NULL DEFAULT 'unknown',
    phase_reason TEXT,
    feature_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(token_address, as_of_time, feature_version)
);

CREATE TABLE IF NOT EXISTS outcome_windows (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER,
    baseline_alert_id INTEGER,
    token_address TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    window_start_time TEXT NOT NULL,
    window_end_time TEXT NOT NULL,
    field_features_id INTEGER,
    score_features_id INTEGER,
    clock_features_id INTEGER,
    entry_price REAL,
    entry_mcap REAL,
    max_price REAL,
    max_mcap REAL,
    max_return_multiple REAL,
    time_to_max_return_s REAL,
    min_price REAL,
    min_mcap REAL,
    max_drawdown_pct REAL,
    time_to_max_drawdown_s REAL,
    hit_2x INTEGER,
    hit_3x INTEGER,
    hit_5x INTEGER,
    time_to_2x_s REAL,
    time_to_3x_s REAL,
    time_to_5x_s REAL,
    last_observed_price REAL,
    last_observed_mcap REAL,
    last_observed_time TEXT,
    activity_status TEXT NOT NULL DEFAULT 'unknown',
    death_label TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);
"""


INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_token_sequence_pool_address ON token_sequence_state(pool_address);
CREATE INDEX IF NOT EXISTS idx_token_sequence_migration_time ON token_sequence_state(migration_time);
CREATE INDEX IF NOT EXISTS idx_token_sequence_current_status ON token_sequence_state(current_status);
CREATE INDEX IF NOT EXISTS idx_token_sequence_sequence_phase ON token_sequence_state(sequence_phase);

CREATE UNIQUE INDEX IF NOT EXISTS ux_migration_events_signature ON migration_events(signature) WHERE signature IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_migration_events_token_time ON migration_events(token_address, migration_time);
CREATE INDEX IF NOT EXISTS idx_migration_events_pool_address ON migration_events(pool_address);
CREATE INDEX IF NOT EXISTS idx_migration_events_slot ON migration_events(slot);

CREATE INDEX IF NOT EXISTS idx_price_observations_token_observed ON price_observations(token_address, observed_at);
CREATE INDEX IF NOT EXISTS idx_price_observations_token_source_timestamp ON price_observations(token_address, source_timestamp);
CREATE INDEX IF NOT EXISTS idx_price_observations_source ON price_observations(source);

CREATE INDEX IF NOT EXISTS idx_ath_state_status ON ath_state(ath_status);
CREATE INDEX IF NOT EXISTS idx_ath_state_confidence ON ath_state(ath_confidence);
CREATE INDEX IF NOT EXISTS idx_ath_state_source ON ath_state(ath_source);
CREATE INDEX IF NOT EXISTS idx_ath_state_updated_at ON ath_state(updated_at);

CREATE INDEX IF NOT EXISTS idx_ath_events_token_time ON ath_events(token_address, event_time);
CREATE INDEX IF NOT EXISTS idx_ath_events_mutation_type ON ath_events(mutation_type);
CREATE INDEX IF NOT EXISTS idx_ath_events_accepted ON ath_events(accepted);
CREATE INDEX IF NOT EXISTS idx_ath_events_candidate_source ON ath_events(candidate_source);
CREATE INDEX IF NOT EXISTS idx_ath_events_data_limited ON ath_events(data_limited);

CREATE INDEX IF NOT EXISTS idx_alert_decisions_token_eval ON alert_decisions(token_address, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_alert_decisions_decision_type ON alert_decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_alert_decisions_primary_reason ON alert_decisions(primary_reason);
CREATE INDEX IF NOT EXISTS idx_alert_decisions_would_alert ON alert_decisions(would_alert);
CREATE INDEX IF NOT EXISTS idx_alert_decisions_tier_index ON alert_decisions(tier_index);
CREATE INDEX IF NOT EXISTS idx_alert_decisions_policy_version ON alert_decisions(policy_version);

CREATE INDEX IF NOT EXISTS idx_filter_evaluations_token_time ON filter_evaluations(token_address, as_of_time);
CREATE INDEX IF NOT EXISTS idx_filter_evaluations_filter_label ON filter_evaluations(filter_name, label);
CREATE INDEX IF NOT EXISTS idx_filter_evaluations_alert_decision_id ON filter_evaluations(alert_decision_id);
CREATE INDEX IF NOT EXISTS idx_filter_evaluations_would_block ON filter_evaluations(would_block);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dispatch_events_idempotency
    ON dispatch_events(alert_decision_id, target)
    WHERE status != 'failed';
CREATE INDEX IF NOT EXISTS idx_dispatch_events_query
    ON dispatch_events(decision_type, severity, attempted_at);
CREATE INDEX IF NOT EXISTS idx_dispatch_events_run
    ON dispatch_events(dispatch_run_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_events_alert_decision_id
    ON dispatch_events(alert_decision_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_events_status
    ON dispatch_events(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_events_target_status_time
    ON dispatch_events(target, status, attempted_at);

CREATE INDEX IF NOT EXISTS idx_fee_windows_token_window_time ON fee_windows(token_address, window_seconds, as_of_time);
CREATE INDEX IF NOT EXISTS idx_fee_windows_last_event_time ON fee_windows(last_event_time);
CREATE INDEX IF NOT EXISTS idx_fee_windows_pool_address ON fee_windows(pool_address);

CREATE INDEX IF NOT EXISTS idx_field_features_token_time ON field_features(token_address, as_of_time);
CREATE INDEX IF NOT EXISTS idx_field_features_fee_gate_label ON field_features(fee_gate_label);
CREATE INDEX IF NOT EXISTS idx_field_features_lp_floor_label ON field_features(lp_floor_label);

CREATE INDEX IF NOT EXISTS idx_score_features_token_time ON score_features(token_address, as_of_time);
CREATE INDEX IF NOT EXISTS idx_score_features_score_version ON score_features(score_version);
CREATE INDEX IF NOT EXISTS idx_score_features_composite_score ON score_features(composite_score);
CREATE INDEX IF NOT EXISTS idx_score_features_risk_score ON score_features(risk_score);

CREATE INDEX IF NOT EXISTS idx_clock_features_token_time ON clock_features(token_address, as_of_time);
CREATE INDEX IF NOT EXISTS idx_clock_features_sequence_phase ON clock_features(sequence_phase);

CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_windows_decision_window ON outcome_windows(decision_id, window_seconds) WHERE decision_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_windows_baseline_window ON outcome_windows(baseline_alert_id, window_seconds) WHERE baseline_alert_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outcome_windows_token_window ON outcome_windows(token_address, window_seconds);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_2x ON outcome_windows(hit_2x);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_3x ON outcome_windows(hit_3x);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_5x ON outcome_windows(hit_5x);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_death_label ON outcome_windows(death_label);
"""


RAW_PUMPSWAP_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS raw_pumpswap_events (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    subscription TEXT,
    signature TEXT NOT NULL,
    slot INTEGER,
    block_time TEXT,
    transaction_index INTEGER,
    instruction_index INTEGER,
    inner_instruction_index INTEGER,
    event_index INTEGER,
    dedupe_key TEXT NOT NULL,
    pool_address TEXT,
    token_address TEXT,
    base_mint TEXT,
    quote_mint TEXT,
    user_address TEXT,
    event_type TEXT NOT NULL,
    base_amount_raw TEXT,
    quote_amount_raw TEXT,
    base_amount_token REAL,
    quote_amount_sol REAL,
    price_sol REAL,
    price_usd REAL,
    mcap REAL,
    lp_fee_sol REAL,
    protocol_fee_sol REAL,
    creator_fee_sol REAL,
    total_fee_sol REAL,
    fee_unit TEXT,
    fee_invariant_ok INTEGER,
    decoder_name TEXT,
    decoder_version TEXT,
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_token_block_time
    ON raw_pumpswap_events(token_address, block_time);
CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_pool_block_time
    ON raw_pumpswap_events(pool_address, block_time);
CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_signature
    ON raw_pumpswap_events(signature);
CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_slot
    ON raw_pumpswap_events(slot);
CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_event_type
    ON raw_pumpswap_events(event_type);
CREATE INDEX IF NOT EXISTS idx_raw_pumpswap_events_created_at
    ON raw_pumpswap_events(created_at);
"""


PRICE_CURVE_POINTS_SQL = """
CREATE TABLE IF NOT EXISTS price_curve_points (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    anchor_type TEXT NOT NULL,
    anchor_key TEXT NOT NULL,
    anchor_time TEXT NOT NULL,
    anchor_ref_id INTEGER,
    bucket_seconds INTEGER NOT NULL,
    bucket_start_time TEXT NOT NULL,
    bucket_end_time TEXT NOT NULL,
    observed_at TEXT,
    price_observation_id INTEGER,
    price REAL,
    mcap REAL,
    liquidity_usd REAL,
    normalized_price REAL,
    normalized_mcap REAL,
    return_from_anchor REAL,
    return_from_migration REAL,
    drawdown_from_ath REAL,
    age_since_migration_s REAL,
    time_since_ath_s REAL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(token_address, anchor_key, bucket_seconds)
);

CREATE INDEX IF NOT EXISTS idx_price_curve_points_token_anchor_bucket
    ON price_curve_points(token_address, anchor_type, bucket_seconds);
CREATE INDEX IF NOT EXISTS idx_price_curve_points_anchor_bucket
    ON price_curve_points(anchor_type, bucket_seconds);
CREATE INDEX IF NOT EXISTS idx_price_curve_points_data_status
    ON price_curve_points(data_status);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_migration(
    connection: sqlite3.Connection,
    *,
    version: str,
    stage: str,
    description: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (
            version,
            stage,
            description,
            script_name,
            checksum,
            applied_at,
            success
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (version, stage, description, "PHX2/db/migrations.py", None, _utc_now()),
    )


def apply_stage4_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4A/4B PHX2 schema to an existing PHX2 connection."""

    connection.executescript(CORE_TELEMETRY_SQL)
    _record_migration(
        connection,
        version=STAGE_4A_VERSION,
        stage="4A",
        description="Core telemetry schema",
    )

    connection.executescript(RESEARCH_SCHEMA_SQL)
    connection.executescript(INDEX_SQL)
    _record_migration(
        connection,
        version=STAGE_4B_VERSION,
        stage="4B",
        description="Field, Score, Clock research schema",
    )
    connection.commit()


def apply_stage5a_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 plus Stage 5A raw PumpSwap event schema."""

    apply_stage4_schema(connection)
    connection.executescript(RAW_PUMPSWAP_EVENTS_SQL)
    _record_migration(
        connection,
        version=STAGE_5A_VERSION,
        stage="5A",
        description="Raw PumpSwap event schema",
    )
    connection.commit()


def apply_stage5c1_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4, Stage 5A, and Stage 5C.1 price curve point schema."""

    apply_stage5a_schema(connection)
    connection.executescript(PRICE_CURVE_POINTS_SQL)
    _record_migration(
        connection,
        version=STAGE_5C1_VERSION,
        stage="5C.1",
        description="Observe-only price curve point schema",
    )
    connection.commit()


STAGE_9_OUTCOME_WINDOWS_SQL = """
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
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id),
    UNIQUE (alert_decision_id, window_seconds),
    CHECK (data_status IN ('COMPLETE', 'NO_PRICE_DATA', 'INVALID_ALERT_PRICE')),
    CHECK (window_seconds IN (300, 900, 1800, 3600, 14400, 86400))
);

CREATE INDEX idx_outcome_windows_token_address ON outcome_windows(token_address);
CREATE INDEX idx_outcome_windows_alert_decision_id ON outcome_windows(alert_decision_id);
CREATE INDEX idx_outcome_windows_window_start_time ON outcome_windows(window_start_time);
"""


def apply_stage9_alert_decision_extension(connection: sqlite3.Connection) -> None:
    """Add nullable current_price / current_mcap columns to alert_decisions.

    Idempotent: re-running on a DB that already has the columns is a no-op.
    Stage 9 reads ``alert_decisions.current_price`` directly as the canonical
    denominator for forward-return measurement; AlertEligibilityEngine writes
    these from the same values it places into ``key_feature_snapshot``.
    """

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(alert_decisions)")
    }
    if "current_price" not in columns:
        connection.execute(
            "ALTER TABLE alert_decisions ADD COLUMN current_price REAL"
        )
    if "current_mcap" not in columns:
        connection.execute(
            "ALTER TABLE alert_decisions ADD COLUMN current_mcap REAL"
        )
    _record_migration(
        connection,
        version=STAGE_9A_VERSION,
        stage="9A",
        description="Add current_price/current_mcap to alert_decisions",
    )


def apply_stage9_outcome_windows_recreate(connection: sqlite3.Connection) -> None:
    """Replace the Stage 4B outcome_windows scaffolding with the Stage 9 schema.

    Refuses to drop the table when it contains rows. The safety check exists
    because the new schema is incompatible with the scaffolding shape and any
    real outcome data must be preserved through a separately-authored backfill.
    """

    count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM outcome_windows"
    ).fetchone()
    existing_rows = int(count_row["count"]) if count_row is not None else 0
    if existing_rows > 0:
        raise RuntimeError(
            "Stage 9 migration safety check refused to drop outcome_windows: "
            f"table has {existing_rows} row(s). Stage 9 expects an empty "
            "scaffolded table. Backfill or archive existing rows before "
            "re-running this migration."
        )

    connection.execute("DROP TABLE outcome_windows")
    connection.executescript(STAGE_9_OUTCOME_WINDOWS_SQL)
    _record_migration(
        connection,
        version=STAGE_9B_VERSION,
        stage="9B",
        description="Recreate outcome_windows with Stage 9 schema",
    )


def apply_stage9_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 through Stage 9 schema in order."""

    apply_stage5c1_schema(connection)
    apply_stage9_alert_decision_extension(connection)
    apply_stage9_outcome_windows_recreate(connection)
    connection.commit()


def migrate_phx2_schema(settings: Union[PHX2Settings, PHX2DryRunDbSettings]) -> None:
    """Open the PHX2 dry-run DB and apply the current PHX2 schema."""

    connection = get_phx2_connection(settings)
    try:
        apply_stage9_schema(connection)
    finally:
        connection.close()
