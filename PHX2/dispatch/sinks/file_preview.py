"""File-backed preview sink: append one JSON line per dispatch.

The output is bucketed by the UTC date of ``context.attempted_at``. Each line
is a self-contained JSON object so the file is valid JSONL. The sink writes
the full line in one ``write()`` call followed by ``fsync`` so a crash
mid-write cannot leave a partial line that breaks JSONL readers.
"""

import json
import os
from dataclasses import is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult
from PHX2.renderers.adapters.plain_text import PlainTextAdapter
from PHX2.renderers.rendered_alert import RenderedAlert


class FileSink:
    """Append one JSONL line per dispatch under ``{root_dir}/{YYYY-MM-DD}/``."""

    name = "file_preview"

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._adapter = PlainTextAdapter()

    def deliver(
        self,
        rendered: RenderedAlert,
        context: DeliveryContext,
    ) -> DeliveryResult:
        try:
            date_bucket = context.attempted_at.strftime("%Y-%m-%d")
            day_dir = self._root_dir / date_bucket
            day_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = day_dir / "decisions.jsonl"

            payload = self._build_payload(rendered, context)
            line = json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"

            # Atomic append: build the full line, then issue one write() call
            # plus fsync. SQLite-style durability for JSONL — a crash during
            # write leaves either nothing or a complete line.
            fd = os.open(
                str(jsonl_path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                os.write(fd, line.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception as exc:
            return DeliveryResult(
                success=False,
                payload_ref=None,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        return DeliveryResult(
            success=True,
            payload_ref=str(jsonl_path),
            error_message=None,
        )

    def _build_payload(
        self,
        rendered: RenderedAlert,
        context: DeliveryContext,
    ) -> Dict[str, Any]:
        token_address = rendered.token_section.get("address", "")
        formatted_text = self._adapter.format(rendered)
        dispatched_at = context.attempted_at.isoformat().replace("+00:00", "Z")
        return {
            "dispatch_event_id": context.dispatch_event_id,
            "alert_decision_id": rendered.alert_decision_id,
            "dispatch_run_id": context.dispatch_run_id,
            "decision_type": rendered.decision_type,
            "severity": rendered.severity.name,
            "tier_label": rendered.tier_label,
            "token_address": token_address,
            "dispatched_at": dispatched_at,
            "rendered_alert": _structural_dict(rendered),
            "formatted_text": formatted_text,
        }


def _structural_dict(value: Any) -> Any:
    """Convert a RenderedAlert (and any nested enums/dataclasses) to plain JSON.

    Enums are rendered via ``.name`` so the JSONL line uses the same casing
    (``"PARTIAL"``) as the top-level ``severity`` field.
    """

    if isinstance(value, Enum):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        # asdict() recurses but does not convert enums or datetimes — walk the
        # __dataclass_fields__ ourselves to keep the recursion under our control.
        return {
            field_name: _structural_dict(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): _structural_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_structural_dict(item) for item in value]
    return value
