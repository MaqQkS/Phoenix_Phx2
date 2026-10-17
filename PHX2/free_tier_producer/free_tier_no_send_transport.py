"""free_tier_no_send_transport.py — NO-SEND recording transport for the committed 30.11.16 guard.

OUT-OF-REPO operator glue. Implements the committed ``Stage30_11_16PrivateTransport`` Protocol
(``send_one_audited_post(webhook_identity=..., payload=...)``) by RECORDING the would-ping instead
of sending anything. ``ok=True`` from this transport means exactly "the would-ping was durably
recorded" — NO socket is opened, NO webhook exists in this object, NO Discord/network surface is
reachable from it. This is the free-tier producer's DEFAULT transport; enabling real private
Discord later is a pure transport swap (this recorder -> the proven Stage28_4 -> Stage28_9 seam),
the exact upgrade path proven by Build #27.

Returning a success verdict here is honest by construction (the same contract as the committed
``Stage30_11_5RecordingFakeTransportClient`` at the compose seam): the transport's one job is to
record, and it reports failure (``ok=False`` is unreachable — a record failure raises, which the
committed guard maps to a fail-closed TRANSPORT_EXCEPTION refusal, never a fabricated success).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


NO_SEND_TRANSPORT_STATUS = "NO_SEND_RECORDED"
NO_SEND_TRANSPORT_KIND = "FREE_TIER_NO_SEND_RECORDING"


@dataclass(frozen=True)
class NoSendRecordingResult:
    """Duck-typed verdict the committed guard reads (``ok`` + ``transport_status``)."""

    ok: bool
    transport_status: str
    recorded_count: int


class FreeTierRecordingNoSendTransport:
    """Records one would-ping per forwarded call. Send-incapable by construction."""

    fake_only = True
    real_send_capable = False
    transport_kind = NO_SEND_TRANSPORT_KIND

    def __init__(
        self,
        *,
        on_record: Callable[[Dict[str, Any]], None],
        now_iso_fn: Callable[[], str],
    ) -> None:
        self._on_record = on_record
        self._now_iso_fn = now_iso_fn
        self._recorded_count = 0

    @property
    def recorded_count(self) -> int:
        return self._recorded_count

    def send_one_audited_post(
        self, *, webhook_identity: Optional[str], payload: Any
    ) -> NoSendRecordingResult:
        """Record the would-ping body. Raises on an unrecordable payload / failed record append —
        the committed guard then fails CLOSED (TRANSPORT_EXCEPTION); success is never fabricated."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("payload.content must be a non-empty string")
        record = {
            "kind": "FREE_TIER_WOULD_PING_BODY",
            "recorded_at_utc": self._now_iso_fn(),
            "webhook_identity_echo": (str(webhook_identity)
                                      if isinstance(webhook_identity, str) else None),
            "transport_kind": NO_SEND_TRANSPORT_KIND,
            "real_send": False,
            "content_length": len(content),
            "content_text": content,
        }
        self._on_record(record)  # a failed append raises -> guard fail-closed
        self._recorded_count += 1
        return NoSendRecordingResult(
            ok=True,
            transport_status=NO_SEND_TRANSPORT_STATUS,
            recorded_count=self._recorded_count,
        )


__all__ = (
    "NO_SEND_TRANSPORT_STATUS",
    "NO_SEND_TRANSPORT_KIND",
    "NoSendRecordingResult",
    "FreeTierRecordingNoSendTransport",
)
