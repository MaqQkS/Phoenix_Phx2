"""Alert decision model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import (
    ATHConfidence,
    ATHStatus,
    DataStatus,
    DecisionReason,
    DecisionType,
)
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class AlertDecision(SerializableDataclass):
    """Decision object produced by AlertEligibilityEngine.

    This object owns no sending side effects and performs no DB writes.
    """

    token_address: str
    evaluated_at: Optional[datetime] = None
    decision_type: DecisionType = DecisionType.SKIP
    tier_index: Optional[int] = None
    tier_name: Optional[str] = None
    primary_reason: DecisionReason = DecisionReason.ERROR
    reasons: List[DecisionReason] = field(default_factory=list)
    would_alert: bool = False
    blocked: bool = False
    skipped: bool = True
    price_observation_id: Optional[int] = None
    ath_event_id: Optional[int] = None
    field_features_id: Optional[int] = None
    score_features_id: Optional[int] = None
    clock_features_id: Optional[int] = None
    field_score: Optional[float] = None
    setup_score: Optional[float] = None
    clock_score: Optional[float] = None
    risk_score: Optional[float] = None
    composite_score: Optional[float] = None
    ath_price: Optional[float] = None
    ath_status: ATHStatus = ATHStatus.UNKNOWN
    ath_confidence: ATHConfidence = ATHConfidence.UNKNOWN
    ath_source: Optional[str] = None
    price_age_seconds: Optional[float] = None
    pump_multiple: Optional[float] = None
    drawdown_from_ath: Optional[float] = None
    filter_labels: Dict[str, str] = field(default_factory=dict)
    tier_context: Dict[str, Any] = field(default_factory=dict)
    key_feature_snapshot: Dict[str, Any] = field(default_factory=dict)
    policy_version: str = "policy_v0_placeholder"
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
