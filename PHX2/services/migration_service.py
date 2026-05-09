"""PHX2 migration intake service.

This service accepts already-normalized MigrationEvent models and persists only
PHX2 migration/token state. It does not open live sockets, fetch prices, seed
ATH, write raw PumpSwap events, evaluate alerts, or send messages.
"""

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, List, Optional

from PHX2.db.repositories import MigrationEventRepository, TokenSequenceRepository
from PHX2.models import DataStatus, MigrationEvent, TokenState


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: List[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


class MigrationService:
    """Owns PHX2 migration event intake and token sequence initialization."""

    def __init__(
        self,
        migration_events: MigrationEventRepository,
        token_sequence: TokenSequenceRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.migration_events = migration_events
        self.token_sequence = token_sequence
        self.current_time_provider = current_time_provider or _default_current_time

    def ingest_migration(self, event: MigrationEvent) -> TokenState:
        """Persist a normalized migration and initialize token sequence state.

        Duplicate token intake is deterministic: the existing token row is
        preserved and returned with a duplicate reason recorded on state.
        Duplicate signature insertions that reach SQLite are caught and mapped
        to the same duplicate-state behavior.
        """

        token_address = event.token_address.strip() if event.token_address else ""
        if not token_address:
            raise ValueError("MigrationEvent.token_address is required")

        existing = self.token_sequence.get(token_address)
        if existing is not None:
            with self.migration_events.connection.transaction():
                return self._record_duplicate(existing, "duplicate_token_migration")

        normalized_event = self._normalized_event(event, token_address)
        with self.migration_events.connection.transaction():
            try:
                migration_event_id = self.migration_events.insert(normalized_event)
            except sqlite3.IntegrityError:
                existing_after_error = self.token_sequence.get(token_address)
                if existing_after_error is not None:
                    return self._record_duplicate(
                        existing_after_error,
                        "duplicate_migration_signature",
                    )
                duplicate_state = self._token_state_from_event(
                    normalized_event,
                    migration_event_id=None,
                    extra_missing_reasons=["duplicate_migration_signature"],
                )
                self.token_sequence.upsert(duplicate_state)
                return duplicate_state

            token_state = self._token_state_from_event(normalized_event, migration_event_id)
            self.token_sequence.upsert(token_state)
            return token_state

    def _normalized_event(
        self,
        event: MigrationEvent,
        token_address: str,
    ) -> MigrationEvent:
        migration_time = event.migration_time or event.block_time
        missing_reasons = list(event.missing_reasons)
        if event.migration_time is None:
            missing_reasons.append("migration_time_missing")
        if migration_time is None:
            migration_time = self.current_time_provider()

        return replace(
            event,
            token_address=token_address,
            migration_time=migration_time,
            missing_reasons=_dedupe_reasons(missing_reasons),
        )

    def _token_state_from_event(
        self,
        event: MigrationEvent,
        migration_event_id: Optional[int],
        extra_missing_reasons: Optional[List[str]] = None,
    ) -> TokenState:
        missing_reasons = list(event.missing_reasons)
        if event.migration_price is None:
            missing_reasons.append("migration_price_missing")
        if event.migration_mcap is None:
            missing_reasons.append("migration_mcap_missing")
        if extra_missing_reasons:
            missing_reasons.extend(extra_missing_reasons)

        missing_reasons = _dedupe_reasons(missing_reasons)
        data_status = self._data_status_for_event(event, missing_reasons)

        return TokenState(
            token_address=event.token_address,
            pool_address=event.pool_address,
            migration_time=event.migration_time,
            migration_source=event.migration_source or "unknown",
            migration_price=event.migration_price,
            migration_mcap=event.migration_mcap,
            sequence_phase="post_migration",
            current_status="tracking",
            last_migration_event_id=migration_event_id,
            data_status=data_status,
            missing_reasons=missing_reasons,
        )

    def _data_status_for_event(
        self,
        event: MigrationEvent,
        missing_reasons: List[str],
    ) -> DataStatus:
        if not missing_reasons and event.data_status == DataStatus.OK:
            return DataStatus.OK
        if (
            event.migration_price is None
            and event.migration_mcap is None
            and "migration_time_missing" in missing_reasons
        ):
            return DataStatus.MISSING
        return DataStatus.PARTIAL

    def _record_duplicate(self, existing: TokenState, reason: str) -> TokenState:
        missing_reasons = _dedupe_reasons([*existing.missing_reasons, reason])
        duplicate_state = replace(
            existing,
            data_status=DataStatus.PARTIAL,
            missing_reasons=missing_reasons,
        )
        self.token_sequence.upsert(duplicate_state)
        return duplicate_state
