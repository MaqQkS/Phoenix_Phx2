"""PHX2 SQLite schema migrations.

Stage 4 creates PHX2 dry-run tables only. It does not import Phoenix1 database
modules, mutate Phoenix1 tables, implement strategy logic, or send messages.
"""

import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Union

# PHX2.config.settings and PHX2.db.connection are deferred to inside
# ``migrate_phx2_schema`` so that importing this module does NOT
# transitively load PHX2.config.settings (which imports
# PHX2.models.enums) at module load time. Stage 16B's sidecar boundary
# re-exports the Stage 16B apply functions from this module, so this
# deferral is required to keep ``import PHX2.stage16b.*`` free of the
# forbidden PHX2.config / PHX2.models surface.
if TYPE_CHECKING:  # type-checker-only resolution of the function annotation
    from PHX2.config.settings import PHX2DryRunDbSettings, PHX2Settings


STAGE_4A_VERSION = "stage_4a_core_telemetry"
STAGE_4B_VERSION = "stage_4b_field_score_clock"
STAGE_5A_VERSION = "stage_5a_raw_pumpswap_events"
STAGE_5C1_VERSION = "stage_5c1_price_curve_points"
STAGE_9A_VERSION = "stage_9a_alert_decision_current_price"
STAGE_9B_VERSION = "stage_9b_outcome_windows_recreate"
STAGE_10A_VERSION = "stage_10a_field_features_event_count_5m"
STAGE_10B_VERSION = "stage_10b_filter_evaluations_extension"
STAGE_11A_VERSION = "stage_11a_decision_score_features"
STAGE_16B_VERSION = "stage_16b_observe_only_policy_evaluations"


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
    -- current_price / current_mcap: written by AlertEligibilityEngine starting Stage 9.
    -- Included in CORE_TELEMETRY_SQL so fresh-DB test fixtures match production DBs after
    -- Stage 9A's ALTER TABLE migration. Stage 9A (apply_stage9_alert_decision_extension)
    -- remains authoritative for upgrading pre-Stage-9 production databases.
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
    -- alert_decision_id:
    --   NULL permitted at schema level for future free-standing filter
    --   evaluations. Stage 10 v0 service requires non-NULL. The composite
    --   UNIQUE constraint below treats NULL as distinct in SQLite; v0
    --   relies on application-layer rejection of NULL.
    --   FK declared but inert in Stage 10: PRAGMA foreign_keys is OFF
    --   globally; a future stage owns enabling enforcement.
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
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    CHECK (label IN ('NORMAL', 'ELEVATED', 'SUSPICIOUS', 'SCAM_LIKELY', 'UNKNOWN')),
    CHECK (score IS NULL OR (score >= 0.0 AND score <= 1.0)),
    UNIQUE(alert_decision_id, filter_name, filter_version, threshold_version),
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
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
    event_count_5m INTEGER,
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
CREATE INDEX IF NOT EXISTS idx_filter_evaluations_filter_version ON filter_evaluations(filter_name, filter_version, threshold_version);

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

CREATE INDEX IF NOT EXISTS idx_outcome_windows_token_window ON outcome_windows(token_address, window_seconds);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_2x ON outcome_windows(hit_2x);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_3x ON outcome_windows(hit_3x);
CREATE INDEX IF NOT EXISTS idx_outcome_windows_hit_5x ON outcome_windows(hit_5x);
"""


# Outcome-windows indexes that depend on the Stage 4B scaffold-only columns
# ``decision_id``, ``baseline_alert_id``, and ``death_label``. Stage 9B's
# recreate drops these columns (and the indexes along with the table); after
# Stage 9B the DDL below cannot run because the referenced columns no
# longer exist. The conditional creation in
# ``_apply_outcome_windows_scaffold_indexes`` keeps the migration chain
# re-runnable: apply_stage10_schema -> apply_stage4_schema can be called
# again on a post-Stage-9 DB without raising. On a fresh DB the scaffold
# still has the columns, so all three indexes are created exactly as
# before; ``test_critical_indexes_are_present`` continues to observe them
# at Stage 4.
_OUTCOME_WINDOWS_SCAFFOLD_INDEXES = (
    (
        "decision_id",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_windows_decision_window "
        "ON outcome_windows(decision_id, window_seconds) "
        "WHERE decision_id IS NOT NULL",
    ),
    (
        "baseline_alert_id",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_windows_baseline_window "
        "ON outcome_windows(baseline_alert_id, window_seconds) "
        "WHERE baseline_alert_id IS NOT NULL",
    ),
    (
        "death_label",
        "CREATE INDEX IF NOT EXISTS idx_outcome_windows_death_label "
        "ON outcome_windows(death_label)",
    ),
)


def _apply_outcome_windows_scaffold_indexes(
    connection: sqlite3.Connection,
) -> None:
    """Create scaffold-only outcome_windows indexes when columns are present.

    Called once from ``apply_stage4_schema`` immediately after INDEX_SQL.
    Each DDL is skipped if its referenced column no longer exists, which
    is the post-Stage-9B state. This is the rerun-safety hinge: it lets
    ``apply_stage10_schema`` (which delegates to ``apply_stage9_schema``
    which delegates back through ``apply_stage4_schema``) be called twice
    on the same DB without ``sqlite3.OperationalError`` from these stale
    DDLs.
    """

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(outcome_windows)")
    }
    for required_column, ddl in _OUTCOME_WINDOWS_SCAFFOLD_INDEXES:
        if required_column in columns:
            connection.execute(ddl)


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
    _apply_outcome_windows_scaffold_indexes(connection)
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

    Operationally idempotent. Four cases:

    1. Table does not exist → create with Stage 9 schema.
    2. Table already has the Stage 9 shape (``alert_decision_id`` column
       present) → no-op. Existing Stage 9 rows are preserved untouched. The
       version row is re-recorded via INSERT OR IGNORE.
    3. Table has the Stage 4B scaffold shape and is empty → drop and recreate
       with Stage 9 schema.
    4. Table has the Stage 4B scaffold shape and is non-empty → refuse with
       RuntimeError. The new schema is incompatible with the scaffolding
       shape and any real outcome data must be preserved through a
       separately-authored backfill.

    The Stage 9 vs Stage 4B discrimination is by column signature:
    ``alert_decision_id`` exists only in the Stage 9 schema; ``decision_id``
    exists only in the Stage 4B scaffold.
    """

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(outcome_windows)")
    }

    if not columns:
        # Case 1: table absent. First-run from a state that has only the
        # earlier-stage tables, but somehow not the scaffold. Create directly.
        connection.executescript(STAGE_9_OUTCOME_WINDOWS_SQL)
        _record_migration(
            connection,
            version=STAGE_9B_VERSION,
            stage="9B",
            description="Recreate outcome_windows with Stage 9 schema",
        )
        return

    if "alert_decision_id" in columns:
        # Case 2: table is already the Stage 9 shape. No-op — preserve any
        # existing rows. _record_migration uses INSERT OR IGNORE so a repeat
        # call leaves schema_migrations unchanged.
        _record_migration(
            connection,
            version=STAGE_9B_VERSION,
            stage="9B",
            description="Recreate outcome_windows with Stage 9 schema",
        )
        return

    # Case 3 / 4: scaffold shape. Refuse if rows exist; otherwise drop and
    # recreate. The row-count check is the safety net the original migration
    # was built around.
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


STAGE_10_FILTER_EVALUATIONS_SQL = """
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
    missing_reasons_json TEXT NOT NULL DEFAULT '[]',
    CHECK (label IN ('NORMAL', 'ELEVATED', 'SUSPICIOUS', 'SCAM_LIKELY', 'UNKNOWN')),
    CHECK (score IS NULL OR (score >= 0.0 AND score <= 1.0)),
    UNIQUE(alert_decision_id, filter_name, filter_version, threshold_version),
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
);

CREATE INDEX idx_filter_evaluations_token_time ON filter_evaluations(token_address, as_of_time);
CREATE INDEX idx_filter_evaluations_filter_label ON filter_evaluations(filter_name, label);
CREATE INDEX idx_filter_evaluations_alert_decision_id ON filter_evaluations(alert_decision_id);
CREATE INDEX idx_filter_evaluations_would_block ON filter_evaluations(would_block);
CREATE INDEX idx_filter_evaluations_filter_version ON filter_evaluations(filter_name, filter_version, threshold_version);
"""


def apply_stage10_field_features_extension(connection: sqlite3.Connection) -> None:
    """Add nullable event_count_5m column to field_features.

    Idempotent: re-running on a DB that already has the column is a no-op.
    Stage 10's Fee Gate filter consumes ``field_features.event_count_5m``
    as a proxy for Phoenix1's ``tx_count`` primitive; FieldFeatureService
    populates it from the 300s fee window's ``event_count``.
    """

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(field_features)")
    }
    if "event_count_5m" not in columns:
        connection.execute(
            "ALTER TABLE field_features ADD COLUMN event_count_5m INTEGER"
        )
    _record_migration(
        connection,
        version=STAGE_10A_VERSION,
        stage="10A",
        description="Add event_count_5m to field_features",
    )


def apply_stage10_filter_evaluations_recreate(connection: sqlite3.Connection) -> None:
    """Recreate the filter_evaluations table with the Stage 10 schema.

    Operationally idempotent. Four cases:

    1. Table does not exist (unexpected — apply_stage9_schema should have
       created the Stage 4 shape first) → create with Stage 10 schema.
    2. Table already has the Stage 10 shape (``threshold_version`` column
       present) → no-op. Existing rows are preserved untouched. The
       version row is re-recorded via INSERT OR IGNORE.
    3. Table has the Stage 4 scaffold shape and is empty → drop and
       recreate with Stage 10 schema (plus indexes).
    4. Table has the Stage 4 scaffold shape and is non-empty → refuse
       with RuntimeError. The new schema is incompatible with the
       scaffolding shape and any real evaluation data must be preserved
       through a separately-authored backfill.

    The Stage 10 vs Stage 4 discrimination is by column signature:
    ``threshold_version`` exists only in the Stage 10 schema.
    """

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(filter_evaluations)")
    }

    if not columns:
        connection.executescript(STAGE_10_FILTER_EVALUATIONS_SQL)
        _record_migration(
            connection,
            version=STAGE_10B_VERSION,
            stage="10B",
            description="Recreate filter_evaluations with Stage 10 schema",
        )
        return

    if "threshold_version" in columns:
        _record_migration(
            connection,
            version=STAGE_10B_VERSION,
            stage="10B",
            description="Recreate filter_evaluations with Stage 10 schema",
        )
        return

    count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM filter_evaluations"
    ).fetchone()
    existing_rows = int(count_row["count"]) if count_row is not None else 0
    if existing_rows > 0:
        raise RuntimeError(
            "Stage 10 migration safety check refused to drop filter_evaluations: "
            f"table has {existing_rows} row(s). Stage 10 expects an empty "
            "scaffolded table (Stage 7 engine writes none). Backfill or "
            "archive existing rows before re-running this migration."
        )

    connection.execute("DROP TABLE filter_evaluations")
    connection.executescript(STAGE_10_FILTER_EVALUATIONS_SQL)
    _record_migration(
        connection,
        version=STAGE_10B_VERSION,
        stage="10B",
        description="Recreate filter_evaluations with Stage 10 schema",
    )


def apply_stage10_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 through Stage 10 schema in order.

    Stage 10A: idempotently add ``field_features.event_count_5m``.
    Stage 10B: drop + recreate ``filter_evaluations`` with the Stage 10
    schema (new columns, CHECKs, UNIQUE, FK declaration). The recreate
    refuses if pre-existing rows are present.
    """

    apply_stage9_schema(connection)
    apply_stage10_field_features_extension(connection)
    apply_stage10_filter_evaluations_recreate(connection)
    connection.commit()


# ---------------------------------------------------------------------------
# Stage 11 -- decision_score_features (DecisionFeatureSnapshotService)
# ---------------------------------------------------------------------------
#
# Stage 11 adds one new table: ``decision_score_features``. It records a
# decision-time typed snapshot of upstream feature state for every
# WOULD_ALERT decision. The service that writes it
# (``DecisionFeatureSnapshotService``) is the substrate for Stage 12's
# ``alert_decisions x filter_evaluations x decision_score_features x
# outcome_windows`` outcome-correlation join.
#
# Schema notes (see Stage 11 Locked Design Spec for rationale):
#
# * ``feature_version`` (semantic) and ``schema_version`` (payload shape) are
#   stored together but identity is ``UNIQUE(alert_decision_id,
#   feature_version)``. Any ``schema_version`` bump must couple to a
#   ``feature_version`` bump (machine-enforced via the UNIQUE constraint:
#   two rows with the same (decision, feature_version) but different
#   schema_version still violate UNIQUE).
# * Every measurement column is nullable so the row can be written with
#   ``data_status='partial'`` or ``data_status='missing'`` when an upstream
#   is absent. Only identity / versioning / audit columns are NOT NULL.
# * ``token_symbol`` is denormalized from ``token_sequence_state.symbol`` at
#   decision time and frozen on the row. This decouples the snapshot from
#   subsequent token-state mutations (rebrands, symbol corrections) and
#   matches the Stage 7 ``key_feature_snapshot`` freeze convention.
# * ``liquidity_usd`` is reserved despite being NULL on every row today --
#   the upstream column shape (``field_features.liquidity_usd``) is known
#   and stable, so the snapshot table can absorb the value automatically
#   when the LP price reader is wired without a schema change.
# * The FK declaration to ``alert_decisions(id)`` is inert in Stage 11
#   (PRAGMA foreign_keys is OFF globally; same as ``filter_evaluations``)
#   but it documents the relationship and would activate cleanly if FK
#   enforcement is later enabled.
# * ``decision_score_features`` is a *measurement primitive snapshot*, NOT
#   a scoring output. It is intentionally distinct from the legacy
#   ``score_features`` table (Stage 4B scaffolded) which is reserved for
#   a future scoring service. Do not confuse the two: Stage 11 stores no
#   composite_score / risk_score / setup_score / participation_quality_score
#   (per L9, L10, L11 in the locked design spec).
STAGE_11_DECISION_SCORE_FEATURES_SQL = """
CREATE TABLE decision_score_features (
    id                                  INTEGER PRIMARY KEY,

    -- Identity and versioning
    alert_decision_id                   INTEGER NOT NULL,
    feature_version                     TEXT    NOT NULL,
    schema_version                      TEXT    NOT NULL,

    -- Decision context (denormalized from alert_decisions for
    -- self-contained reads)
    token_address                       TEXT    NOT NULL,
    token_symbol                        TEXT,
    decision_time                       TEXT    NOT NULL,
    as_of_time                          TEXT    NOT NULL,

    tier_index                          INTEGER,
    tier_name                           TEXT,
    alert_price                         REAL,
    alert_market_cap                    REAL,

    -- Lifecycle state (ATH / migration)
    ath_price                           REAL,
    ath_market_cap                      REAL,
    ath_time                            TEXT,
    migration_price                     REAL,
    migration_market_cap                REAL,
    migration_time                      TEXT,

    -- Neutral derived measurements (consumed from upstream Stage 7
    -- computation; Stage 11 does not recompute them)
    drop_from_ath                       REAL,
    multiple_from_migration             REAL,

    -- Clock primitives (consumed from clock_features)
    time_since_migration_seconds        REAL,
    time_since_ath_seconds              REAL,
    time_from_migration_to_ath_seconds  REAL,

    -- Field primitives, 5m typed only (other windows go in
    -- source_snapshot_json.aux_windows)
    liquidity_usd                       REAL,
    event_count_5m                      INTEGER,
    total_fee_5m                        REAL,
    lp_fee_5m                           REAL,
    protocol_fee_5m                     REAL,
    creator_fee_5m                      REAL,
    creator_fee_share_5m                REAL,
    lp_fee_share_5m                     REAL,
    protocol_fee_share_5m               REAL,
    fee_per_event_5m                    REAL,
    events_per_minute_5m                REAL,
    fees_per_minute_5m                  REAL,

    -- Consolidated provenance + non-5m windows + extras
    source_snapshot_json                TEXT    NOT NULL DEFAULT '{}',

    -- Audit
    created_at                          TEXT    NOT NULL,
    data_status                         TEXT    NOT NULL,
    missing_reasons_json                TEXT    NOT NULL DEFAULT '[]',

    UNIQUE (alert_decision_id, feature_version),
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
);

CREATE INDEX idx_decision_score_features_token_time
    ON decision_score_features(token_address, decision_time);

CREATE INDEX idx_decision_score_features_alert_decision_id
    ON decision_score_features(alert_decision_id);

CREATE INDEX idx_decision_score_features_feature_version
    ON decision_score_features(feature_version);

CREATE INDEX idx_decision_score_features_data_status
    ON decision_score_features(data_status);
"""


def apply_stage11_decision_score_features(
    connection: sqlite3.Connection,
) -> None:
    """Create ``decision_score_features`` on first run; no-op on re-run.

    Stage 11 has no prior scaffold (no Stage 4B placeholder for this
    table), so the four-case recreate guard used in Stages 9B and 10B is
    not needed. A simple existence check via ``PRAGMA table_info`` is
    sufficient: empty result means the table is absent and we run the
    full DDL; non-empty result means an earlier Stage 11 application
    already created it and we skip.

    The version row is recorded via ``_record_migration``'s INSERT OR
    IGNORE, so re-runs leave ``schema_migrations`` with exactly one
    Stage 11A row regardless of how many times the migration is applied.
    """

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(decision_score_features)"
        )
    }
    if not columns:
        connection.executescript(STAGE_11_DECISION_SCORE_FEATURES_SQL)
    _record_migration(
        connection,
        version=STAGE_11A_VERSION,
        stage="11A",
        description="Decision-time feature snapshot table",
    )


def apply_stage11_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 through Stage 11 schema in order.

    Stage 11A: idempotently create ``decision_score_features`` (typed
    snapshot of upstream feature state per alert decision).
    """

    apply_stage10_schema(connection)
    apply_stage11_decision_score_features(connection)
    connection.commit()


# ---------------------------------------------------------------------------
# Stage 16B -- observe_only_policy_evaluations (sidecar telemetry)
# ---------------------------------------------------------------------------
#
# Stage 16B adds one new table: ``observe_only_policy_evaluations``. It is
# the append-only telemetry sink for the Stage 16B sidecar observer, which
# evaluates already-committed WOULD_ALERT alert decisions against a Stage
# 16A observe-only runtime policy via Stage 16A's pure evaluator. Stage
# 16B never participates in alert eligibility or dispatch -- this table is
# read by analysis tooling only.
#
# Schema notes:
#
# * Identity is ``UNIQUE(alert_decision_id, policy_hash, rule_id)``: one
#   row per (decision, policy, rule). Re-running the observer on the same
#   policy is idempotent via ``INSERT OR IGNORE``.
# * Three columns (``matched``, ``would_have_blocked``, ``evaluation_status``)
#   are constrained by a single compound CHECK to the three valid postures:
#     MATCHED      -> matched=1, would_have_blocked=1, reason IS NULL
#     NOT_MATCHED  -> matched=0, would_have_blocked=0, reason IS NULL
#     UNEVALUABLE  -> matched=0, would_have_blocked=0, reason IS NOT NULL
#   The compound CHECK is what makes the row's posture self-consistent on
#   disk; Stage 16B's row builder produces only these three shapes.
# * ``would_have_blocked`` mirrors ``matched`` today (1 iff the matched
#   rule's ``intended_action`` would have fired). Because Stage 16A
#   policies are ``LOG_WOULD_BLOCK`` for every rule
#   (``hard_block_allowed=False``), a MATCHED rule always implies
#   ``would_have_blocked=1``; the column is kept distinct so the schema
#   accommodates future intended-action shapes without an ALTER.
# * The FK declaration to ``alert_decisions(id)`` is inert at runtime
#   (``PRAGMA foreign_keys`` is OFF globally; same posture as
#   ``filter_evaluations`` and ``decision_score_features``) but documents
#   the relationship and would activate cleanly if FK enforcement is later
#   enabled.
STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL = """
CREATE TABLE IF NOT EXISTS observe_only_policy_evaluations (
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
    UNIQUE(alert_decision_id, policy_hash, rule_id),
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_decision
    ON observe_only_policy_evaluations(alert_decision_id);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_policy_rule_time
    ON observe_only_policy_evaluations(policy_hash, rule_id, evaluated_at_utc);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_status
    ON observe_only_policy_evaluations(evaluation_status);
"""


# ---------------------------------------------------------------------------
# Stage 16B locked schema invariants -- validated by the hardened migration
# when ``observe_only_policy_evaluations`` already exists from a prior run.
# ---------------------------------------------------------------------------


# (column_name, declared_type, notnull) in declaration order.
EXPECTED_STAGE_16B_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("id", "INTEGER", 0),
    ("alert_decision_id", "INTEGER", 1),
    ("tier_name_snapshot", "TEXT", 0),
    ("policy_hash", "TEXT", 1),
    ("rule_id", "TEXT", 1),
    ("evaluation_status", "TEXT", 1),
    ("matched", "INTEGER", 1),
    ("would_have_blocked", "INTEGER", 1),
    ("unevaluable_reason", "TEXT", 0),
    ("predicate_snapshot_json", "TEXT", 1),
    ("evaluated_at_utc", "TEXT", 1),
    ("created_at_utc", "TEXT", 1),
)


EXPECTED_STAGE_16B_UNIQUE_COLUMNS: tuple[str, ...] = (
    "alert_decision_id",
    "policy_hash",
    "rule_id",
)


EXPECTED_STAGE_16B_FOREIGN_KEY: tuple[str, str, str] = (
    "alert_decisions",
    "alert_decision_id",
    "id",
)


EXPECTED_STAGE_16B_INDEXES: dict[str, tuple[str, ...]] = {
    "idx_observe_only_policy_eval_decision": ("alert_decision_id",),
    "idx_observe_only_policy_eval_policy_rule_time": (
        "policy_hash", "rule_id", "evaluated_at_utc",
    ),
    "idx_observe_only_policy_eval_status": ("evaluation_status",),
}


class Stage16BMigrationError(RuntimeError):
    """Raised when an existing ``observe_only_policy_evaluations`` table
    diverges from the locked Stage 16B schema and cannot be repaired
    in-place.

    Drift in column shape, the UNIQUE constraint, or the FK declaration
    is a hard refuse: those are baked into the table at CREATE time and
    cannot be added without a full table recreate, which Stage 16B
    deliberately does not perform (the table is append-only telemetry
    and recreate would silently nuke prior runs' rows).

    Missing indexes are NOT a refuse condition -- they are recreated
    idempotently via ``CREATE INDEX IF NOT EXISTS``.
    """


def _existing_stage_16b_columns(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, int], ...]:
    rows = list(connection.execute(
        "PRAGMA table_info(observe_only_policy_evaluations)"
    ))
    return tuple((row["name"], row["type"], row["notnull"]) for row in rows)


def _existing_stage_16b_unique_constraint_columns(
    connection: sqlite3.Connection,
) -> list[tuple[str, ...]]:
    """Return the column tuple of every UNIQUE constraint (origin='u') on
    the Stage 16B table. PRIMARY KEY (origin='pk') is excluded; named
    CREATE INDEX (origin='c') is excluded."""

    results: list[tuple[str, ...]] = []
    for idx_row in connection.execute(
        "PRAGMA index_list(observe_only_policy_evaluations)"
    ):
        if idx_row["unique"] == 1 and idx_row["origin"] == "u":
            cols = tuple(
                r["name"]
                for r in connection.execute(
                    f"PRAGMA index_info({idx_row['name']})"
                )
            )
            results.append(cols)
    return results


def _existing_stage_16b_foreign_key_present(
    connection: sqlite3.Connection,
) -> bool:
    for fk in connection.execute(
        "PRAGMA foreign_key_list(observe_only_policy_evaluations)"
    ):
        if (
            fk["table"] == EXPECTED_STAGE_16B_FOREIGN_KEY[0]
            and fk["from"] == EXPECTED_STAGE_16B_FOREIGN_KEY[1]
            and fk["to"] == EXPECTED_STAGE_16B_FOREIGN_KEY[2]
        ):
            return True
    return False


def _validate_observe_only_table_shape(
    connection: sqlite3.Connection,
) -> None:
    """Validate the existing table against the locked Stage 16B schema.

    Raises ``Stage16BMigrationError`` on drift in column shape, UNIQUE
    constraint, or FK declaration. Missing indexes are NOT validated
    here -- they are repaired idempotently by
    ``_ensure_observe_only_indexes`` after this check passes.
    """

    actual_columns = _existing_stage_16b_columns(connection)
    if actual_columns != EXPECTED_STAGE_16B_COLUMNS:
        raise Stage16BMigrationError(
            "observe_only_policy_evaluations columns drift from the locked "
            f"Stage 16B shape: expected {EXPECTED_STAGE_16B_COLUMNS!r}, "
            f"got {actual_columns!r}"
        )

    unique_columns = _existing_stage_16b_unique_constraint_columns(connection)
    if EXPECTED_STAGE_16B_UNIQUE_COLUMNS not in unique_columns:
        raise Stage16BMigrationError(
            "observe_only_policy_evaluations is missing the locked UNIQUE "
            f"constraint on {EXPECTED_STAGE_16B_UNIQUE_COLUMNS!r}; "
            f"present UNIQUE constraints: {unique_columns!r}"
        )

    if not _existing_stage_16b_foreign_key_present(connection):
        raise Stage16BMigrationError(
            "observe_only_policy_evaluations is missing the locked FOREIGN "
            f"KEY declaration {EXPECTED_STAGE_16B_FOREIGN_KEY!r}"
        )


def _existing_observe_only_table_indexes(
    connection: sqlite3.Connection,
) -> dict[str, tuple[str, ...]]:
    """Return ``{index_name: (col1, col2, ...)}`` for every named
    ``CREATE INDEX`` (``origin='c'``) on ``observe_only_policy_evaluations``.

    Excludes auto-created indexes for PRIMARY KEY (``origin='pk'``) and
    UNIQUE constraints (``origin='u'``); only Stage 16B's own CREATE
    INDEX entries are returned. Used by index-shape validation.
    """

    indexes: dict[str, tuple[str, ...]] = {}
    for idx_row in connection.execute(
        "PRAGMA index_list(observe_only_policy_evaluations)"
    ):
        if idx_row["origin"] != "c":
            continue
        cols = tuple(
            r["name"]
            for r in connection.execute(
                f"PRAGMA index_info({idx_row['name']})"
            )
        )
        indexes[idx_row["name"]] = cols
    return indexes


def _validate_observe_only_indexes(connection: sqlite3.Connection) -> None:
    """Validate existing Stage 16B indexes match the locked column tuples.

    Audit re-finding MEDIUM: ``CREATE INDEX IF NOT EXISTS`` is a no-op
    when an index of the same name exists -- a same-name index with
    drifted columns would silently survive a "repair" attempt. This
    validation closes the gap: for each locked Stage 16B index name,
    if an index with that name already exists on
    ``observe_only_policy_evaluations``, its indexed-column tuple MUST
    match the locked tuple; otherwise raise ``Stage16BMigrationError``.

    Missing indexes are NOT a refuse condition -- they are repaired
    idempotently by ``_ensure_observe_only_indexes`` (called after this
    validation when the table itself is compatible).
    """

    existing_indexes = _existing_observe_only_table_indexes(connection)
    for index_name, expected_columns in EXPECTED_STAGE_16B_INDEXES.items():
        if index_name not in existing_indexes:
            # Missing -- will be repaired by _ensure_observe_only_indexes.
            continue
        actual_columns = existing_indexes[index_name]
        if actual_columns != expected_columns:
            raise Stage16BMigrationError(
                f"observe_only_policy_evaluations index {index_name!r} has "
                f"drifted columns: expected {expected_columns!r}, got "
                f"{actual_columns!r}"
            )


def _ensure_observe_only_indexes(connection: sqlite3.Connection) -> None:
    """Idempotently (re-)create the three Stage 16B indexes.

    ``CREATE INDEX IF NOT EXISTS`` is a no-op when an index of the same
    name already exists, so this is safe to call regardless of the
    starting state. ``_validate_observe_only_indexes`` MUST be called
    BEFORE this function on re-runs so that a same-name-but-drifted
    index is rejected up-front; otherwise the IF NOT EXISTS DDL here
    would silently preserve the drifted index instead of repairing it.
    """

    for index_name, columns in EXPECTED_STAGE_16B_INDEXES.items():
        column_list = ", ".join(columns)
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON observe_only_policy_evaluations({column_list})"
        )


def apply_stage16b_observe_only_policy_evaluations(
    connection: sqlite3.Connection,
) -> None:
    """Create ``observe_only_policy_evaluations`` on first run; validate the
    existing table on re-run.

    First run (table absent): execute
    ``STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL`` to create the
    table + three indexes per the locked DDL, then record the migration.

    Re-run (table present): validate the table's column shape, UNIQUE
    constraint, and FK declaration against the locked schema. If any
    drift, raise ``Stage16BMigrationError`` and DO NOT record the
    migration as successful. If the table is compatible, repair any
    missing indexes idempotently via ``CREATE INDEX IF NOT EXISTS`` and
    record the migration via ``INSERT OR IGNORE`` (so re-runs leave
    ``schema_migrations`` with exactly one Stage 16B row).
    """

    actual_columns = _existing_stage_16b_columns(connection)

    if not actual_columns:
        # First run -- create from locked DDL.
        connection.executescript(STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL)
        _record_migration(
            connection,
            version=STAGE_16B_VERSION,
            stage="16B",
            description="Observe-only policy evaluations table",
        )
        return

    # Re-run: validate first. A drift here raises Stage16BMigrationError
    # before _record_migration so a malformed pre-existing table never
    # produces a spurious "16B applied" row in schema_migrations.
    _validate_observe_only_table_shape(connection)

    # Validate index shapes BEFORE the repair pass: a same-name index
    # with drifted columns would otherwise survive
    # ``CREATE INDEX IF NOT EXISTS`` silently. Audit re-finding MEDIUM.
    _validate_observe_only_indexes(connection)

    # Compatible existing table -- repair missing indexes idempotently
    # and record the migration via INSERT OR IGNORE.
    _ensure_observe_only_indexes(connection)
    _record_migration(
        connection,
        version=STAGE_16B_VERSION,
        stage="16B",
        description="Observe-only policy evaluations table",
    )


def apply_stage16b_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 through Stage 16B schema in order.

    Stage 16B: idempotently create ``observe_only_policy_evaluations``,
    the append-only telemetry sink written by the Stage 16B sidecar
    observer. The observer reuses Stage 16A's loader and evaluator and
    never participates in alert eligibility or dispatch.
    """

    apply_stage11_schema(connection)
    apply_stage16b_observe_only_policy_evaluations(connection)
    connection.commit()


def migrate_phx2_schema(
    settings: "Union[PHX2Settings, PHX2DryRunDbSettings]",
) -> None:
    """Open the PHX2 dry-run DB and apply the current PHX2 schema."""

    # Deferred imports: see module-level note about the Stage 16B sidecar
    # boundary.
    from PHX2.db.connection import get_phx2_connection

    connection = get_phx2_connection(settings)
    try:
        apply_stage16b_schema(connection)
    finally:
        connection.close()
