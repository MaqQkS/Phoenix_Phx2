"""Outcome window model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class OutcomeWindow(SerializableDataclass):
    """Post-decision outcome measurement placeholder."""

    window_seconds: int
    decision_id: Optional[int] = None
    baseline_alert_id: Optional[int] = None
    token_address: Optional[str] = None
    window_start_time: Optional[datetime] = None
    window_end_time: Optional[datetime] = None
    entry_price: Optional[float] = None
    entry_mcap: Optional[float] = None
    max_price: Optional[float] = None
    max_mcap: Optional[float] = None
    max_return_multiple: Optional[float] = None
    time_to_max_return_s: Optional[float] = None
    min_price: Optional[float] = None
    min_mcap: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    time_to_max_drawdown_s: Optional[float] = None
    hit_2x: Optional[bool] = None
    hit_3x: Optional[bool] = None
    hit_5x: Optional[bool] = None
    time_to_2x_s: Optional[float] = None
    time_to_3x_s: Optional[float] = None
    time_to_5x_s: Optional[float] = None
    last_observed_price: Optional[float] = None
    last_observed_mcap: Optional[float] = None
    last_observed_time: Optional[datetime] = None
    activity_status: str = "unknown"
    death_label: str = "unknown"
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
