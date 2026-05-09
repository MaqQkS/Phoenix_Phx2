"""Price observation model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class PriceObservation(SerializableDataclass):
    """A single observed price or market-cap point."""

    token_address: str
    id: Optional[int] = None
    observed_at: Optional[datetime] = None
    source: Optional[str] = None
    price: Optional[float] = None
    mcap: Optional[float] = None
    liquidity_usd: Optional[float] = None
    source_timestamp: Optional[datetime] = None
    age_seconds: Optional[float] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)

    @property
    def price_usd(self) -> Optional[float]:
        """Backward-compatible alias for earlier scaffold tests."""

        return self.price

    @property
    def market_cap_usd(self) -> Optional[float]:
        """Backward-compatible alias for earlier scaffold tests."""

        return self.mcap
