"""Clock feature model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class ClockFeatures(SerializableDataclass):
    """Sequence timing features."""

    token_address: str
    id: Optional[int] = None
    as_of_time: Optional[datetime] = None
    migration_time: Optional[datetime] = None
    age_since_migration_s: Optional[float] = None
    ath_time: Optional[datetime] = None
    time_to_ath_s: Optional[float] = None
    time_since_ath_s: Optional[float] = None
    tier_1_time: Optional[datetime] = None
    tier_2_time: Optional[datetime] = None
    tier_3_time: Optional[datetime] = None
    time_ath_to_t1_s: Optional[float] = None
    time_ath_to_t2_s: Optional[float] = None
    time_ath_to_t3_s: Optional[float] = None
    time_t1_to_t2_s: Optional[float] = None
    time_t2_to_t3_s: Optional[float] = None
    dip_velocity_pct_per_min: Optional[float] = None
    recovery_velocity_pct_per_min: Optional[float] = None
    last_fee_event_time: Optional[datetime] = None
    last_buy_time: Optional[datetime] = None
    last_sell_time: Optional[datetime] = None
    time_since_last_fee_event_s: Optional[float] = None
    time_since_last_buy_s: Optional[float] = None
    time_since_last_sell_s: Optional[float] = None
    sequence_phase: str = "unknown"
    phase_reason: Optional[str] = None
    feature_version: str = "clock_v0_placeholder"
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
