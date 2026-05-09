"""Dispatch event model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus, DispatchMode
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class DispatchEvent(SerializableDataclass):
    """Verification or send-attempt record.

    Stage 4 stores dispatch intent/audit rows only. It implements no sending.
    """

    token_address: str
    dispatch_mode: DispatchMode = DispatchMode.DISABLED
    alert_decision_id: Optional[int] = None
    destination: Optional[str] = None
    renderer_version: Optional[str] = None
    rendered_text: Optional[str] = None
    preview_file_path: Optional[str] = None
    status: str = "pending"
    dry_run: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
