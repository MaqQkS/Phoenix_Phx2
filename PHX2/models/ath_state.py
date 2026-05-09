"""ATH state and event models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import ATHConfidence, ATHEventType, ATHStatus, DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class ATHState(SerializableDataclass):
    """Current ATH state owned by ATHService."""

    token_address: str
    ath_price: Optional[float] = None
    ath_mcap: Optional[float] = None
    ath_time: Optional[datetime] = None
    ath_status: ATHStatus = ATHStatus.UNKNOWN
    ath_confidence: ATHConfidence = ATHConfidence.UNKNOWN
    ath_source: Optional[str] = None
    last_event_id: Optional[int] = None
    updated_at: Optional[datetime] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)

    @property
    def status(self) -> ATHStatus:
        return self.ath_status

    @property
    def confidence(self) -> ATHConfidence:
        return self.ath_confidence

    @property
    def source(self) -> Optional[str]:
        return self.ath_source

    @property
    def price_usd(self) -> Optional[float]:
        return self.ath_price

    @property
    def market_cap_usd(self) -> Optional[float]:
        return self.ath_mcap


@dataclass(frozen=True)
class ATHEvent(SerializableDataclass):
    """Future audit record for an ATH candidate or mutation."""

    token_address: str
    id: Optional[int] = field(default=None, compare=False)
    event_time: Optional[datetime] = None
    price_observation_id: Optional[int] = None
    candidate_price: Optional[float] = None
    candidate_mcap: Optional[float] = None
    candidate_source: Optional[str] = None
    prior_ath_price: Optional[float] = None
    prior_ath_mcap: Optional[float] = None                              
    new_ath_price: Optional[float] = None
    new_ath_mcap: Optional[float] = None                      
    status_before: ATHStatus = ATHStatus.UNKNOWN
    status_after: ATHStatus = ATHStatus.UNKNOWN
    confidence_before: ATHConfidence = ATHConfidence.UNKNOWN
    confidence_after: ATHConfidence = ATHConfidence.UNKNOWN
    mutation_type: ATHEventType = ATHEventType.ATH_NO_CHANGE
    reason: Optional[str] = None
    accepted: bool = False
    data_limited: bool = False
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    data_status: DataStatus = DataStatus.PARTIAL
    missing_reasons: List[str] = field(default_factory=list)
