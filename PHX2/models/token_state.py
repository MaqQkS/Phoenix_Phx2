"""Token state model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class TokenState(SerializableDataclass):
    """Current PHX2 view of a token sequence."""

    token_address: str
    symbol: Optional[str] = None
    pool_address: Optional[str] = None
    migration_time: Optional[datetime] = None
    migration_source: Optional[str] = None
    migration_price: Optional[float] = None
    migration_mcap: Optional[float] = None
    current_price: Optional[float] = None
    current_mcap: Optional[float] = None
    last_price_update: Optional[datetime] = None
    sequence_phase: str = "unknown"
    current_status: str = "unknown"
    last_alerted_tier: Optional[int] = None
    last_migration_event_id: Optional[int] = None
    last_price_observation_id: Optional[int] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)


TokenSequenceState = TokenState
