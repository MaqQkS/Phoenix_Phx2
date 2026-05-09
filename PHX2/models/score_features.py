"""Score feature model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class ScoreFeatures(SerializableDataclass):
    """Versioned score placeholders.

    Scores are intentionally unset until raw Field and Clock features are
    captured and reviewed.
    """

    token_address: str
    as_of_time: Optional[datetime] = None
    score_version: str = "score_v0_observe_only"
    field_score: Optional[float] = None
    setup_score: Optional[float] = None
    clock_score: Optional[float] = None
    risk_score: Optional[float] = None
    composite_score: Optional[float] = None
    pump_multiple: Optional[float] = None
    drawdown_from_ath: Optional[float] = None
    ath_quality_score: Optional[float] = None
    price_freshness_score: Optional[float] = None
    liquidity_quality_score: Optional[float] = None
    fee_quality_score: Optional[float] = None
    participation_quality_score: Optional[float] = None
    organic_risk_score: Optional[float] = None
    scam_risk_score: Optional[float] = None
    dip_speed_score: Optional[float] = None
    support_reclaim_quality_score: Optional[float] = None
    components: Dict[str, Any] = field(default_factory=dict)
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
