"""Migration event model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class MigrationEvent(SerializableDataclass):
    """Pump.fun to PumpSwap migration event boundary."""

    token_address: str
    pool_address: Optional[str] = None
    migration_time: Optional[datetime] = None
    migration_source: Optional[str] = None
    signature: Optional[str] = None
    slot: Optional[int] = None
    block_time: Optional[datetime] = None
    migration_price: Optional[float] = None
    migration_mcap: Optional[float] = None
    raw_payload_json: Dict[str, Any] = field(default_factory=dict)
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
