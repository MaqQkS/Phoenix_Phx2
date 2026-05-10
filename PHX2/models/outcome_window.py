"""Outcome window model.

Stage 9 owns this table: one row per (alert_decision_id, window_seconds) pair
for forward-return measurement of WOULD_ALERT decisions. Stage 4B's scaffolding
is fully replaced — no entry_price, baseline_alert_id, feature ids, last_observed
fields, activity_status, death_label, or generic DataStatus references survive.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from PHX2.models.serialization import SerializableDataclass


class OutcomeWindowStatus(str, Enum):
    """Stage-9-specific status for outcome window measurement.

    The persisted ``data_status`` column accepts only the strict 3-value subset
    {COMPLETE, NO_PRICE_DATA, INVALID_ALERT_PRICE}, enforced both by
    ``PERSISTABLE_OUTCOME_WINDOW_STATUSES`` at the repository layer and by the
    schema-level CHECK constraint. The remaining values are service-only
    signals never reaching the DB:

    - PARTIAL: reserved for a future stage; not written in v0.
    - WINDOW_NOT_ELAPSED, ALREADY_RECORDED: skip reasons surfaced through
      ``WindowProcessingResult``.
    - ERROR: unexpected exception during per-window processing. Distinct from
      WINDOW_NOT_ELAPSED so a real failure (DB lock timeout, schema mismatch,
      logic bug) is not silently counted as a normal maturation skip during
      batch backfill.
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NO_PRICE_DATA = "NO_PRICE_DATA"
    INVALID_ALERT_PRICE = "INVALID_ALERT_PRICE"
    WINDOW_NOT_ELAPSED = "WINDOW_NOT_ELAPSED"
    ALREADY_RECORDED = "ALREADY_RECORDED"
    ERROR = "ERROR"


PERSISTABLE_OUTCOME_WINDOW_STATUSES = frozenset(
    {
        OutcomeWindowStatus.COMPLETE,
        OutcomeWindowStatus.NO_PRICE_DATA,
        OutcomeWindowStatus.INVALID_ALERT_PRICE,
    }
)


@dataclass(frozen=True)
class OutcomeWindow(SerializableDataclass):
    """One forward-return measurement window for a WOULD_ALERT decision."""

    window_seconds: int
    id: Optional[int] = None
    alert_decision_id: Optional[int] = None
    token_address: Optional[str] = None
    window_start_time: Optional[datetime] = None
    window_end_time: Optional[datetime] = None
    alert_price: Optional[float] = None
    alert_mcap: Optional[float] = None
    max_price: Optional[float] = None
    max_mcap: Optional[float] = None
    max_observation_time: Optional[datetime] = None
    min_price: Optional[float] = None
    min_mcap: Optional[float] = None
    min_observation_time: Optional[datetime] = None
    max_return_multiple: Optional[float] = None
    max_return_pct: Optional[float] = None
    min_return_multiple: Optional[float] = None
    min_return_pct: Optional[float] = None
    max_drawdown_from_peak_pct: Optional[float] = None
    time_to_max_return_seconds: Optional[float] = None
    hit_2x: Optional[bool] = None
    hit_3x: Optional[bool] = None
    hit_5x: Optional[bool] = None
    observations_count: Optional[int] = None
    first_observation_time: Optional[datetime] = None
    last_observation_time: Optional[datetime] = None
    data_status: OutcomeWindowStatus = OutcomeWindowStatus.NO_PRICE_DATA
