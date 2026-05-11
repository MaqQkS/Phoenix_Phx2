"""Filter evaluation model.

Stage 10 extends this dataclass with ``threshold_version`` and
``output_reason`` to support FilterEvaluationEngine telemetry, and
swaps ``label`` from a free-form string to the FilterLabel enum so it
matches the new CHECK constraint on filter_evaluations.label.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus, FilterLabel
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class FilterResult(SerializableDataclass):
    """Filter label produced independently from alert blocking policy."""

    token_address: str
    filter_name: str
    as_of_time: Optional[datetime] = None
    filter_version: str = "filter_v0_placeholder"
    threshold_version: str = "thresholds_v0_placeholder"
    label: FilterLabel = FilterLabel.UNKNOWN
    score: Optional[float] = None
    would_block: bool = False
    policy_action: str = "observe"
    reason: Optional[str] = None
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    output_reason: Optional[Dict[str, Any]] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
    alert_decision_id: Optional[int] = None
