"""Field feature model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class FieldFeatures(SerializableDataclass):
    """Environment and participation-quality features.

    Raw feature capture is modeled before any scoring formulas are implemented.
    """

    token_address: str
    id: Optional[int] = None
    as_of_time: Optional[datetime] = None
    fee_window_60s_id: Optional[int] = None
    fee_window_300s_id: Optional[int] = None
    fee_window_900s_id: Optional[int] = None
    fee_window_1800s_id: Optional[int] = None
    fee_window_3600s_id: Optional[int] = None
    liquidity_usd: Optional[float] = None
    lp_floor_label: str = "unknown"
    lp_fragility_score: Optional[float] = None
    fee_gate_label: str = "unknown"
    fee_gate_score: Optional[float] = None
    ante_label_5m: str = "unknown"
    ante_label_20sw: str = "unknown"
    ghost_label: str = "unknown"
    holder_label: str = "unknown"
    event_pace_5m: Optional[float] = None
    fee_pace_5m_sol: Optional[float] = None
    creator_fee_share_5m: Optional[float] = None
    lp_fee_share_5m: Optional[float] = None
    protocol_fee_share_5m: Optional[float] = None
    buy_sell_ratio_5m: Optional[float] = None
    event_count_5m: Optional[int] = None
    raw_snapshot: Dict[str, Any] = field(default_factory=dict)
    feature_version: str = "field_v0_placeholder"
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
