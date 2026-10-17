"""Authenticated same-connection Yellowstone transport-slot watermark.

This state is deliberately independent from the transaction event cursor.
Confirmed slot updates may advance it while no PumpSwap transaction matches;
they never imply that any transaction side effect was applied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer.durable_state import AuthenticatedSingletonStore


CHECKPOINT_KIND_TRANSPORT_WATERMARK = "PHX2_TRANSPORT_SLOT_WATERMARK"
TRANSPORT_WATERMARK_SCHEMA_V1 = "phx2_transport_slot_watermark_v1"
TRANSPORT_WATERMARK_RECORD_KIND = "PHX2_TRANSPORT_SLOT_WATERMARK_STATE"
TRANSPORT_WATERMARK_BASENAME = "transport_slot_watermark.json"
TRANSPORT_SOURCE_YELLOWSTONE_CONFIRMED_SLOT = "YELLOWSTONE_CONFIRMED_SLOT"


@dataclass
class TransportWatermarkState:
    record_kind: str = TRANSPORT_WATERMARK_RECORD_KIND
    source: str = TRANSPORT_SOURCE_YELLOWSTONE_CONFIRMED_SLOT
    first_confirmed_slot: Optional[int] = None
    latest_confirmed_slot: Optional[int] = None
    observed_updates: int = 0
    duplicate_or_regressive_updates: int = 0
    last_observed_at_utc: Optional[str] = None

    def to_record(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(
        cls, record: Mapping[str, Any]
    ) -> "TransportWatermarkState":
        return cls(
            record_kind=str(record.get("record_kind") or ""),
            source=str(record.get("source") or ""),
            first_confirmed_slot=record.get("first_confirmed_slot"),
            latest_confirmed_slot=record.get("latest_confirmed_slot"),
            observed_updates=int(record.get("observed_updates") or 0),
            duplicate_or_regressive_updates=int(
                record.get("duplicate_or_regressive_updates") or 0
            ),
            last_observed_at_utc=record.get("last_observed_at_utc"),
        )


def validate_transport_watermark_record(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    if record.get("record_kind") != TRANSPORT_WATERMARK_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    if record.get("source") != TRANSPORT_SOURCE_YELLOWSTONE_CONFIRMED_SLOT:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    for name in ("first_confirmed_slot", "latest_confirmed_slot"):
        value = record.get(name)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    first = record.get("first_confirmed_slot")
    latest = record.get("latest_confirmed_slot")
    if (first is None) != (latest is None):
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    if first is not None and latest < first:
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    for name in ("observed_updates", "duplicate_or_regressive_updates"):
        value = record.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if not _cpe.record_digest_is_valid(
        CHECKPOINT_KIND_TRANSPORT_WATERMARK, record
    ):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    return True, ""


def transport_watermark_identity(record: Mapping[str, Any]) -> Tuple[str]:
    if record.get("record_kind") != TRANSPORT_WATERMARK_RECORD_KIND:
        raise ValueError("TRANSPORT_WATERMARK_RECORD_KIND_INVALID")
    return (TRANSPORT_WATERMARK_RECORD_KIND,)


class TransportWatermarkStore(AuthenticatedSingletonStore):
    checkpoint_kind = CHECKPOINT_KIND_TRANSPORT_WATERMARK
    schema_version = TRANSPORT_WATERMARK_SCHEMA_V1
    record_kind = TRANSPORT_WATERMARK_RECORD_KIND

    def __init__(
        self,
        *,
        state_dir: object,
        basename: str = TRANSPORT_WATERMARK_BASENAME,
    ) -> None:
        super().__init__(primary_path=Path(state_dir) / basename)
        self.state = TransportWatermarkState()

    def classify(self, path: object) -> _cpe.FileClassification:
        return _cpe.classify_checkpoint_file(
            path,
            kind=self.checkpoint_kind,
            supported_schema_versions=(self.schema_version,),
            record_validator=validate_transport_watermark_record,
            identity_fn=transport_watermark_identity,
        )

    def restore_record(self, record: Mapping[str, Any]) -> None:
        self.state = TransportWatermarkState.from_record(record)

    def current_record(self) -> Dict[str, Any]:
        return self.state.to_record()

    def observe_confirmed_slot(
        self, slot: object, *, observed_at_utc: Optional[str] = None
    ) -> bool:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            return False
        with self._lock:
            state = TransportWatermarkState.from_record(
                self.state.to_record()
            )
            state.observed_updates += 1
            if state.first_confirmed_slot is None:
                state.first_confirmed_slot = int(slot)
                state.latest_confirmed_slot = int(slot)
            elif int(slot) > int(state.latest_confirmed_slot or -1):
                state.latest_confirmed_slot = int(slot)
            else:
                state.duplicate_or_regressive_updates += 1
            state.last_observed_at_utc = (
                observed_at_utc or _cpe.utc_now_iso()
            )
            self._persist_record_locked(state.to_record())
            self.state = state
        return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self.state.to_record(),
                "checkpoint_generation": self.generation,
                "checkpoint_quarantined": self.quarantined,
                "checkpoint_quarantine_reason": self.quarantine_reason,
            }


__all__ = (
    "CHECKPOINT_KIND_TRANSPORT_WATERMARK",
    "TRANSPORT_WATERMARK_SCHEMA_V1",
    "TRANSPORT_WATERMARK_RECORD_KIND",
    "TRANSPORT_WATERMARK_BASENAME",
    "TRANSPORT_SOURCE_YELLOWSTONE_CONFIRMED_SLOT",
    "TransportWatermarkState",
    "TransportWatermarkStore",
    "validate_transport_watermark_record",
)
