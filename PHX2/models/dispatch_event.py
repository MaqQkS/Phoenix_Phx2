"""Dispatch event model.

Stage 8B: a row in the dispatch_events table records exactly one attempt by
:class:`PHX2.dispatch.dispatcher.Dispatcher` to route a rendered alert to a
sink. The row goes through ``pending`` → ``sent``/``failed``/``skipped``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class DispatchEvent(SerializableDataclass):
    """Audit record for one dispatch attempt.

    ``id`` is a UUID hex string assigned by the dispatcher. ``alert_decision_id``
    is the integer primary key of the ``alert_decisions`` row this dispatch
    corresponds to. ``dispatch_run_id`` is shared by every row written by one
    Dispatcher instance.
    """

    id: str
    alert_decision_id: int
    dispatch_run_id: str
    target: str
    status: str
    decision_type: str
    severity: str
    attempted_at: datetime
    tier_label: Optional[str] = None
    completed_at: Optional[datetime] = None
    payload_ref: Optional[str] = None
    error_message: Optional[str] = None
