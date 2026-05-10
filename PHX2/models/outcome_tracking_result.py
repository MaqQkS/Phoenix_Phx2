"""Result dataclasses returned by OutcomeTrackingService.

These are pure return objects. No persistence, no I/O, no rendering.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from PHX2.models.outcome_window import OutcomeWindowStatus


@dataclass(frozen=True)
class WindowProcessingResult:
    """One per configured window per call to track_for_decision."""

    window_seconds: int
    status: OutcomeWindowStatus
    outcome_window_id: Optional[int] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class DecisionTrackingResult:
    """Per-decision result aggregating one WindowProcessingResult per window."""

    alert_decision_id: int
    window_results: Tuple[WindowProcessingResult, ...] = ()
    error: Optional[str] = None


@dataclass(frozen=True)
class BatchTrackingResult:
    """Aggregate result for a single track_pending invocation."""

    decision_results: Tuple[DecisionTrackingResult, ...] = ()
    decisions_processed: int = 0
    decisions_skipped_non_would_alert: int = 0
    rows_inserted: int = 0
    rows_skipped_already_recorded: int = 0
    rows_skipped_window_not_elapsed: int = 0
