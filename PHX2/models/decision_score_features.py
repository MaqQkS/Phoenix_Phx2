"""DecisionScoreFeatures model.

Stage 11. Decision-time typed snapshot of upstream feature state for one
WOULD_ALERT alert decision under one feature_version. Persisted to
``decision_score_features`` by ``DecisionFeatureSnapshotService``.

Stores measurement primitives only -- never composite scores, risk
aggregates, filter labels, or policy verdicts. See Stage 11 Locked
Design Spec L1, L9, L10, L11.

Naming distinction: this is *not* the legacy Stage 4B ``score_features``
table. ``decision_score_features`` is a measurement-primitive snapshot
keyed on (alert_decision_id, feature_version); ``score_features`` is a
forward-looking scoring-output table reserved for a future scoring
service. Stage 11 imports neither ``ScoreFeatures`` nor
``ScoreFeatureRepository``.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class DecisionScoreFeatures(SerializableDataclass):
    """Decision-time feature snapshot row.

    Field grouping mirrors ``decision_score_features`` table column
    layout. ``source_snapshot`` is the in-memory dict form of the row's
    ``source_snapshot_json`` column; the repository serializes via the
    standard ``_json_dict`` helper. ``missing_reasons`` is a tuple at
    the model layer (immutable) and serialized as a JSON list at the
    row layer (matching the existing ``_json_list`` pattern, which
    accepts tuples through ``to_json_safe``).
    """

    # Identity
    id: Optional[int] = None
    alert_decision_id: int = 0
    feature_version: str = ""
    schema_version: str = ""

    # Decision context (denormalized from alert_decisions for
    # self-contained reads). ``token_symbol`` is frozen at decision time
    # so the snapshot is decoupled from later token-state mutations.
    token_address: str = ""
    token_symbol: Optional[str] = None
    decision_time: Optional[datetime] = None
    as_of_time: Optional[datetime] = None

    tier_index: Optional[int] = None
    tier_name: Optional[str] = None
    alert_price: Optional[float] = None
    alert_market_cap: Optional[float] = None

    # Lifecycle state (ATH / migration)
    ath_price: Optional[float] = None
    ath_market_cap: Optional[float] = None
    ath_time: Optional[datetime] = None
    migration_price: Optional[float] = None
    migration_market_cap: Optional[float] = None
    migration_time: Optional[datetime] = None

    # Neutral derived measurements (consumed from upstream Stage 7
    # computation; not recomputed here)
    drop_from_ath: Optional[float] = None
    multiple_from_migration: Optional[float] = None

    # Clock primitives
    time_since_migration_seconds: Optional[float] = None
    time_since_ath_seconds: Optional[float] = None
    time_from_migration_to_ath_seconds: Optional[float] = None

    # Field primitives, 5m typed only (other windows go in
    # source_snapshot.aux_windows)
    liquidity_usd: Optional[float] = None
    event_count_5m: Optional[int] = None
    total_fee_5m: Optional[float] = None
    lp_fee_5m: Optional[float] = None
    protocol_fee_5m: Optional[float] = None
    creator_fee_5m: Optional[float] = None
    creator_fee_share_5m: Optional[float] = None
    lp_fee_share_5m: Optional[float] = None
    protocol_fee_share_5m: Optional[float] = None
    fee_per_event_5m: Optional[float] = None
    events_per_minute_5m: Optional[float] = None
    fees_per_minute_5m: Optional[float] = None

    # Consolidated provenance + non-5m windows + extras
    source_snapshot: Dict[str, Any] = field(default_factory=dict)

    # Audit
    created_at: Optional[datetime] = None
    data_status: DataStatus = DataStatus.OK
    missing_reasons: Tuple[str, ...] = ()


def _coerce_missing_reasons(
    raw: Optional[List[str]],
) -> Tuple[str, ...]:
    """Normalize repository-loaded missing_reasons (list) to model tuple."""

    if raw is None:
        return ()
    return tuple(raw)
