"""Observe-only price curve point model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class PriceCurvePoint(SerializableDataclass):
    """One normalized price path bucket for curve research."""

    token_address: str
    anchor_type: str
    anchor_key: str
    anchor_time: datetime
    bucket_seconds: int
    bucket_start_time: datetime
    bucket_end_time: datetime
    id: Optional[int] = None
    anchor_ref_id: Optional[int] = None
    observed_at: Optional[datetime] = None
    price_observation_id: Optional[int] = None
    price: Optional[float] = None
    mcap: Optional[float] = None
    liquidity_usd: Optional[float] = None
    normalized_price: Optional[float] = None
    normalized_mcap: Optional[float] = None
    return_from_anchor: Optional[float] = None
    return_from_migration: Optional[float] = None
    drawdown_from_ath: Optional[float] = None
    age_since_migration_s: Optional[float] = None
    time_since_ath_s: Optional[float] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_key, str) or not self.anchor_key.strip():
            raise ValueError("anchor_key is required")
