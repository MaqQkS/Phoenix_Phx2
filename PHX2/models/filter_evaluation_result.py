"""Result dataclass returned by FilterEvaluationEngine.

This is a pure return object. No persistence, no I/O. Mirrors the
Stage 9 ``DecisionTrackingResult`` convention: validation failures
populate the ``error`` field and produce empty ``results`` with all
count fields at zero. The engine does not raise on caller errors.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PHX2.models.filter_result import FilterResult


@dataclass(frozen=True)
class DecisionFilterEvaluationResult:
    """Wrapper returned by FilterEvaluationEngine.evaluate_for_decision.

    Validation failures (unknown decision_id, non-WOULD_ALERT
    decision_type) return a result with ``error`` populated and
    ``results=[]``. ``error`` is None on the happy path. Tests assert
    on the exact error string vocabulary; see
    ``FilterEvaluationEngine`` for the two sentinel values.
    """

    alert_decision_id: int
    evaluated_at: datetime
    results: List[FilterResult] = field(default_factory=list)
    total_filters: int = 0
    completed_count: int = 0
    missing_inputs_count: int = 0
    error_count: int = 0
    already_recorded_count: int = 0
    error: Optional[str] = None
