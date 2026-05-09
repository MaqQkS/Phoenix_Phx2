"""PHX2 raw PumpSwap event intake service.

This service accepts already-normalized RawPumpSwapEvent models and persists
only PHX2 raw_pumpswap_events. It does not open live streams, decode
transactions, materialize fee windows, mutate token state, evaluate alerts, or
send messages.
"""

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, List, Optional

from PHX2.db.repositories import RawPumpSwapEventRepository
from PHX2.models import DataStatus, RawPumpSwapEvent


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: List[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_text(value: Optional[str], field_name: str) -> str:
    stripped = _optional_text(value)
    if stripped is None:
        raise ValueError(f"RawPumpSwapEvent.{field_name} is required")
    return stripped


class PumpSwapEventIngestionService:
    """Owns PHX2 normalized raw PumpSwap event intake."""

    def __init__(
        self,
        raw_pumpswap_events: RawPumpSwapEventRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.raw_pumpswap_events = raw_pumpswap_events
        self.current_time_provider = current_time_provider or _default_current_time

    def ingest_event(self, event: RawPumpSwapEvent) -> int:
        """Persist a normalized raw event and return its PHX2 row id.

        Duplicate dedupe_key replays are deterministic: the existing row id is
        returned so a live ingestion loop can safely see replayed events.
        """

        normalized_event = self._normalized_event(event)
        try:
            return self.raw_pumpswap_events.insert(normalized_event)
        except sqlite3.IntegrityError:
            existing = self.raw_pumpswap_events.get_by_dedupe_key(
                normalized_event.dedupe_key
            )
            if existing is not None and existing.id is not None:
                return existing.id
            raise

    def _normalized_event(self, event: RawPumpSwapEvent) -> RawPumpSwapEvent:
        dedupe_key = _required_text(event.dedupe_key, "dedupe_key")
        signature = _required_text(event.signature, "signature")
        event_type = _required_text(event.event_type, "event_type")

        missing_reasons = list(event.missing_reasons)

        observed_at = event.observed_at
        if observed_at is None:
            observed_at = self.current_time_provider()
            missing_reasons.append("observed_at_missing")

        source = _optional_text(event.source)
        if source is None:
            source = "unknown"
            missing_reasons.append("source_missing")

        token_address = _optional_text(event.token_address)
        if token_address is None:
            missing_reasons.append("token_address_missing")

        pool_address = _optional_text(event.pool_address)
        if pool_address is None:
            missing_reasons.append("pool_address_missing")

        if self._fee_fields_missing(event):
            missing_reasons.append("fee_fields_missing")

        missing_reasons = _dedupe_reasons(missing_reasons)

        return replace(
            event,
            observed_at=observed_at,
            source=source,
            signature=signature,
            dedupe_key=dedupe_key,
            event_type=event_type,
            token_address=token_address,
            pool_address=pool_address,
            data_status=self._data_status_for_event(event, missing_reasons),
            missing_reasons=missing_reasons,
        )

    def _data_status_for_event(
        self,
        event: RawPumpSwapEvent,
        missing_reasons: List[str],
    ) -> DataStatus:
        if missing_reasons:
            return DataStatus.PARTIAL
        if event.data_status == DataStatus.MISSING:
            return DataStatus.OK
        return event.data_status

    def _fee_fields_missing(self, event: RawPumpSwapEvent) -> bool:
        return any(
            value is None
            for value in (
                event.lp_fee_sol,
                event.protocol_fee_sol,
                event.creator_fee_sol,
                event.total_fee_sol,
            )
        )
