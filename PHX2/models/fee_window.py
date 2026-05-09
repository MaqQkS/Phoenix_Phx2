"""Fee window model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class FeeWindow(SerializableDataclass):
    """Materialized PumpSwap fee/event window."""

    token_address: str
    id: Optional[int] = None
    as_of_time: Optional[datetime] = None
    window_seconds: int = 60
    pool_address: Optional[str] = None
    first_event_time: Optional[datetime] = None
    last_event_time: Optional[datetime] = None
    event_count: Optional[int] = None
    buy_count: Optional[int] = None
    sell_count: Optional[int] = None
    total_fee_sol: Optional[float] = None
    lp_fee_sol: Optional[float] = None
    protocol_fee_sol: Optional[float] = None
    creator_fee_sol: Optional[float] = None
    creator_fee_share: Optional[float] = None
    lp_fee_share: Optional[float] = None
    protocol_fee_share: Optional[float] = None
    avg_fee_per_event_sol: Optional[float] = None
    median_fee_per_event_sol: Optional[float] = None
    max_fee_event_sol: Optional[float] = None
    events_per_min: Optional[float] = None
    fees_per_min_sol: Optional[float] = None
    buy_sell_count_ratio: Optional[float] = None
    buy_sell_fee_ratio: Optional[float] = None
    source_min_id: Optional[int] = None
    source_max_id: Optional[int] = None
    source_row_count: Optional[int] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
