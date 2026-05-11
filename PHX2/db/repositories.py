"""Thin SQLite repositories for PHX2 dry-run persistence.

Repositories accept an already-open PHX2 SQLite connection. They do not open
Phoenix1 connections, run migrations automatically, import Phoenix1 modules, or
perform business logic.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence

from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    AlertDecision,
    ClockFeatures,
    DataStatus,
    DecisionReason,
    DecisionScoreFeatures,
    DecisionType,
    DispatchEvent,
    FeeWindow,
    FieldFeatures,
    FilterLabel,
    FilterResult,
    MigrationEvent,
    OutcomeWindow,
    OutcomeWindowStatus,
    PriceCurvePoint,
    PriceObservation,
    RawPumpSwapEvent,
    ScoreFeatures,
    TokenState,
)
from PHX2.models.outcome_window import PERSISTABLE_OUTCOME_WINDOW_STATUSES
from PHX2.models.serialization import to_json_safe


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_db_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _enum_value(enum_class: type[Enum], value: Optional[str], default: Enum) -> Enum:
    if value is None:
        return default
    return enum_class(value)


def _bool_value(value: Optional[int]) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _json_text(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(to_json_safe(value), separators=(",", ":"), sort_keys=True)


def _json_list(value: Any) -> str:
    return _json_text(value, [])


def _json_dict(value: Any) -> str:
    return _json_text(value, {})


def _load_json(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _limit(limit: int) -> int:
    return max(0, int(limit))


def _payload(model: Any) -> Dict[str, Any]:
    if hasattr(model, "to_dict") and callable(model.to_dict):
        return model.to_dict()
    raise TypeError(f"Expected PHX2 model with to_dict(), got {type(model)!r}")


class RepositoryContract:
    """Base class for PHX2 SQLite repositories."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _commit_if_top_level(self) -> None:
        if not self.connection.in_transaction:
            self.connection.commit()

    def _insert(self, table: str, values: Dict[str, Any]) -> int:
        columns = list(values)
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        cursor = self.connection.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
            [_to_db_value(values[column]) for column in columns],
        )
        self._commit_if_top_level()
        return int(cursor.lastrowid)

    def _fetchone(self, sql: str, params: Sequence[Any]) -> Optional[sqlite3.Row]:
        return self.connection.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: Sequence[Any]) -> List[sqlite3.Row]:
        return list(self.connection.execute(sql, params))


class TokenSequenceRepository(RepositoryContract):
    """Persistence for token_sequence_state."""

    def upsert(self, token_state: TokenState) -> str:
        payload = _payload(token_state)
        now = _now_iso()
        values = {
            "token_address": payload["token_address"],
            "symbol": payload["symbol"],
            "pool_address": payload["pool_address"],
            "migration_time": payload["migration_time"],
            "migration_source": payload["migration_source"],
            "migration_price": payload["migration_price"],
            "migration_mcap": payload["migration_mcap"],
            "current_price": payload["current_price"],
            "current_mcap": payload["current_mcap"],
            "last_price_update": payload["last_price_update"],
            "sequence_phase": payload["sequence_phase"],
            "current_status": payload["current_status"],
            "last_alerted_tier": payload["last_alerted_tier"],
            "last_migration_event_id": payload["last_migration_event_id"],
            "last_price_observation_id": payload["last_price_observation_id"],
            "created_at": now,
            "updated_at": now,
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
        }
        self.connection.execute(
            """
            INSERT INTO token_sequence_state (
                token_address, symbol, pool_address, migration_time,
                migration_source, migration_price, migration_mcap, current_price,
                current_mcap, last_price_update, sequence_phase, current_status,
                last_alerted_tier, last_migration_event_id,
                last_price_observation_id, created_at, updated_at, data_status,
                missing_reasons_json
            )
            VALUES (
                :token_address, :symbol, :pool_address, :migration_time,
                :migration_source, :migration_price, :migration_mcap,
                :current_price, :current_mcap, :last_price_update,
                :sequence_phase, :current_status, :last_alerted_tier,
                :last_migration_event_id, :last_price_observation_id,
                :created_at, :updated_at, :data_status, :missing_reasons_json
            )
            ON CONFLICT(token_address) DO UPDATE SET
                symbol = excluded.symbol,
                pool_address = excluded.pool_address,
                migration_time = excluded.migration_time,
                migration_source = excluded.migration_source,
                migration_price = excluded.migration_price,
                migration_mcap = excluded.migration_mcap,
                current_price = excluded.current_price,
                current_mcap = excluded.current_mcap,
                last_price_update = excluded.last_price_update,
                sequence_phase = excluded.sequence_phase,
                current_status = excluded.current_status,
                last_alerted_tier = excluded.last_alerted_tier,
                last_migration_event_id = excluded.last_migration_event_id,
                last_price_observation_id = excluded.last_price_observation_id,
                updated_at = excluded.updated_at,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json
            """,
            values,
        )
        self._commit_if_top_level()
        return str(payload["token_address"])

    def get(self, token_address: str) -> Optional[TokenState]:
        row = self._fetchone(
            "SELECT * FROM token_sequence_state WHERE token_address = ?",
            (token_address,),
        )
        return _token_state_from_row(row) if row else None

    def list_recent(self, limit: int = 100) -> List[TokenState]:
        rows = self._fetchall(
            """
            SELECT * FROM token_sequence_state
            ORDER BY updated_at DESC, token_address DESC
            LIMIT ?
            """,
            (_limit(limit),),
        )
        return [_token_state_from_row(row) for row in rows]


class MigrationEventRepository(RepositoryContract):
    """Persistence for migration_events."""

    def insert(self, event: MigrationEvent) -> int:
        payload = _payload(event)
        return self._insert(
            "migration_events",
            {
                "token_address": payload["token_address"],
                "pool_address": payload["pool_address"],
                "migration_time": payload["migration_time"],
                "migration_source": payload["migration_source"],
                "signature": payload["signature"],
                "slot": payload["slot"],
                "block_time": payload["block_time"],
                "migration_price": payload["migration_price"],
                "migration_mcap": payload["migration_mcap"],
                "raw_payload_json": _json_dict(payload["raw_payload_json"]),
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def list_by_token(self, token_address: str) -> List[MigrationEvent]:
        rows = self._fetchall(
            """
            SELECT * FROM migration_events
            WHERE token_address = ?
            ORDER BY migration_time DESC, id DESC
            """,
            (token_address,),
        )
        return [_migration_event_from_row(row) for row in rows]


class PriceObservationRepository(RepositoryContract):
    """Persistence for price_observations."""

    def insert(self, observation: PriceObservation) -> int:
        payload = _payload(observation)
        return self._insert(
            "price_observations",
            {
                "token_address": payload["token_address"],
                "observed_at": payload["observed_at"],
                "source": payload["source"],
                "price": payload["price"],
                "mcap": payload["mcap"],
                "liquidity_usd": payload["liquidity_usd"],
                "source_timestamp": payload["source_timestamp"],
                "age_seconds": payload["age_seconds"],
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get_by_id(self, observation_id: int) -> Optional[PriceObservation]:
        row = self._fetchone(
            "SELECT * FROM price_observations WHERE id = ?",
            (observation_id,),
        )
        return _price_observation_from_row(row) if row else None

    def get_latest(self, token_address: str) -> Optional[PriceObservation]:
        row = self._fetchone(
            """
            SELECT * FROM price_observations
            WHERE token_address = ?
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
            """,
            (token_address,),
        )
        return _price_observation_from_row(row) if row else None

    def get_latest_at_or_before(
        self,
        token_address: str,
        as_of_time: Any,
    ) -> Optional[PriceObservation]:
        row = self._fetchone(
            """
            SELECT * FROM price_observations
            WHERE token_address = ? AND observed_at <= ?
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
            """,
            (token_address, _to_db_value(as_of_time)),
        )
        return _price_observation_from_row(row) if row else None

    def list_by_token(self, token_address: str, limit: int = 100) -> List[PriceObservation]:
        rows = self._fetchall(
            """
            SELECT * FROM price_observations
            WHERE token_address = ?
            ORDER BY observed_at DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_price_observation_from_row(row) for row in rows]

    def list_by_token_chronological(
        self,
        token_address: str,
        limit: Optional[int] = None,
    ) -> List[PriceObservation]:
        sql = """
            SELECT * FROM price_observations
            WHERE token_address = ?
            ORDER BY observed_at ASC, id ASC
            """
        params: List[Any] = [token_address]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(_limit(limit))
        rows = self._fetchall(sql, params)
        return [_price_observation_from_row(row) for row in rows]

    def get_observations_in_range(
        self,
        token_address: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[PriceObservation]:
        """Return observations with start_time <= observed_at <= end_time, ASC.

        Closed interval on both ends. Used by OutcomeTrackingService to gather
        observations for a single forward-return window. Empty result is valid.
        """

        rows = self._fetchall(
            """
            SELECT * FROM price_observations
            WHERE token_address = ?
              AND observed_at >= ?
              AND observed_at <= ?
            ORDER BY observed_at ASC, id ASC
            """,
            (token_address, _to_db_value(start_time), _to_db_value(end_time)),
        )
        return [_price_observation_from_row(row) for row in rows]


class ATHRepository(RepositoryContract):
    """Persistence for ATH current state and event log."""

    def upsert_state(self, ath_state: ATHState) -> str:
        payload = _payload(ath_state)
        now = _now_iso()
        values = {
            "token_address": payload["token_address"],
            "ath_price": payload["ath_price"],
            "ath_mcap": payload["ath_mcap"],
            "ath_time": payload["ath_time"],
            "ath_status": payload["ath_status"],
            "ath_confidence": payload["ath_confidence"],
            "ath_source": payload["ath_source"],
            "ath_source_priority": None,
            "last_event_id": payload["last_event_id"],
            "created_at": now,
            "updated_at": now,
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
        }
        self.connection.execute(
            """
            INSERT INTO ath_state (
                token_address, ath_price, ath_mcap, ath_time, ath_status,
                ath_confidence, ath_source, ath_source_priority, last_event_id,
                created_at, updated_at, data_status, missing_reasons_json
            )
            VALUES (
                :token_address, :ath_price, :ath_mcap, :ath_time, :ath_status,
                :ath_confidence, :ath_source, :ath_source_priority,
                :last_event_id, :created_at, :updated_at, :data_status,
                :missing_reasons_json
            )
            ON CONFLICT(token_address) DO UPDATE SET
                ath_price = excluded.ath_price,
                ath_mcap = excluded.ath_mcap,
                ath_time = excluded.ath_time,
                ath_status = excluded.ath_status,
                ath_confidence = excluded.ath_confidence,
                ath_source = excluded.ath_source,
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json
            """,
            values,
        )
        self._commit_if_top_level()
        return str(payload["token_address"])

    def get_state(self, token_address: str) -> Optional[ATHState]:
        row = self._fetchone(
            "SELECT * FROM ath_state WHERE token_address = ?",
            (token_address,),
        )
        return _ath_state_from_row(row) if row else None

    def get_state_at_or_before(
        self,
        token_address: str,
        as_of_time: datetime,
    ) -> Optional[ATHState]:
        """Reconstruct the ATHState that was in effect at ``as_of_time``.

        Reads from the append-only ``ath_events`` log instead of the mutable
        ``ath_state`` row, so a future ATH raise does not leak into a
        historical or replay evaluation. Returns ``None`` when no event has
        been recorded for the token at or before ``as_of_time``.

        Reconstruction rules (mirroring ATHService.write semantics):

        * Currently the only state-mutating ``mutation_type`` is
          ``ATH_RAISED``. Other event types (``ATH_NO_CHANGE``,
          ``ATH_REJECTED_LOWER``, ``ATH_REJECTED_INVALID``,
          ``ATH_DATA_LIMITED``) preserve the prior state's ATH-related
          fields and only advance ``last_event_id``.
        * If a state-mutating event exists at or before ``as_of_time``, its
          post-event fields define the ATH numerics, status, confidence,
          source, ``data_status`` and ``missing_reasons``.
        * Otherwise the FIRST event at or before ``as_of_time`` defines
          ``data_status`` and ``missing_reasons`` (matching ATHService's
          "first rejection sets state, subsequent rejections preserve"
          behavior); ATH numerics stay None and status/confidence stay
          UNKNOWN.
        * ``last_event_id`` is always the id of the latest event at or
          before ``as_of_time`` (any type).

        ``as_of_time`` must be provided. ``None`` raises ``ValueError`` —
        callers wanting current state should use ``get_state``.
        """

        if as_of_time is None:
            raise ValueError(
                "get_state_at_or_before requires an explicit as_of_time; "
                "use get_state(token_address) for the current state."
            )

        as_of_db = _to_db_value(as_of_time)

        latest_row = self._fetchone(
            """
            SELECT * FROM ath_events
            WHERE token_address = ? AND event_time <= ?
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """,
            (token_address, as_of_db),
        )
        if latest_row is None:
            return None
        latest_event = _ath_event_from_row(latest_row)

        raise_row = self._fetchone(
            """
            SELECT * FROM ath_events
            WHERE token_address = ? AND event_time <= ?
              AND mutation_type = ?
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """,
            (token_address, as_of_db, ATHEventType.ATH_RAISED.value),
        )

        if raise_row is not None:
            raise_event = _ath_event_from_row(raise_row)
            ath_price = raise_event.new_ath_price
            ath_mcap = raise_event.new_ath_mcap
            ath_time = raise_event.event_time
            ath_status = raise_event.status_after
            ath_confidence = raise_event.confidence_after
            ath_source = raise_event.candidate_source
            data_status = raise_event.data_status
            missing_reasons = list(raise_event.missing_reasons)
        else:
            first_row = self._fetchone(
                """
                SELECT * FROM ath_events
                WHERE token_address = ? AND event_time <= ?
                ORDER BY event_time ASC, id ASC
                LIMIT 1
                """,
                (token_address, as_of_db),
            )
            first_event = _ath_event_from_row(first_row)
            ath_price = None
            ath_mcap = None
            ath_time = None
            ath_status = ATHStatus.UNKNOWN
            ath_confidence = ATHConfidence.UNKNOWN
            ath_source = None
            data_status = first_event.data_status
            missing_reasons = list(first_event.missing_reasons)

        return ATHState(
            token_address=token_address,
            ath_price=ath_price,
            ath_mcap=ath_mcap,
            ath_time=ath_time,
            ath_status=ath_status,
            ath_confidence=ath_confidence,
            ath_source=ath_source,
            last_event_id=latest_event.id,
            updated_at=None,
            data_status=data_status,
            missing_reasons=missing_reasons,
        )

    def insert_event(self, ath_event: ATHEvent) -> int:
        payload = _payload(ath_event)
        return self._insert(
            "ath_events",
            {
                "token_address": payload["token_address"],
                "event_time": payload["event_time"],
                "price_observation_id": payload["price_observation_id"],
                "candidate_price": payload["candidate_price"],
                "candidate_mcap": payload["candidate_mcap"],
                "candidate_source": payload["candidate_source"],
                "candidate_source_priority": None,
                "prior_ath_price": payload["prior_ath_price"],
                "prior_ath_mcap": payload["prior_ath_mcap"],
                "new_ath_price": payload["new_ath_price"],
                "new_ath_mcap": payload["new_ath_mcap"],
                "status_before": payload["status_before"],
                "status_after": payload["status_after"],
                "confidence_before": payload["confidence_before"],
                "confidence_after": payload["confidence_after"],
                "mutation_type": payload["mutation_type"],
                "reason": payload["reason"],
                "accepted": payload["accepted"],
                "data_limited": payload["data_limited"],
                "input_snapshot_json": _json_dict(payload["input_snapshot"]),
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get_event_by_id(self, event_id: int) -> Optional[ATHEvent]:
        row = self._fetchone(
            "SELECT * FROM ath_events WHERE id = ?",
            (event_id,),
        )
        return _ath_event_from_row(row) if row else None

    def list_events(self, token_address: str, limit: int = 100) -> List[ATHEvent]:
        rows = self._fetchall(
            """
            SELECT * FROM ath_events
            WHERE token_address = ?
            ORDER BY event_time DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_ath_event_from_row(row) for row in rows]

    def list_events_chronological(
        self,
        token_address: str,
        limit: int = 100,
    ) -> List[ATHEvent]:
        rows = self._fetchall(
            """
            SELECT * FROM ath_events
            WHERE token_address = ?
            ORDER BY event_time ASC, id ASC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_ath_event_from_row(row) for row in rows]


class AlertDecisionRepository(RepositoryContract):
    """Persistence for alert_decisions."""

    def insert(self, decision: AlertDecision) -> int:
        payload = _payload(decision)
        return self._insert(
            "alert_decisions",
            {
                "token_address": payload["token_address"],
                "evaluated_at": payload["evaluated_at"],
                "decision_type": payload["decision_type"],
                "tier_index": payload["tier_index"],
                "tier_name": payload["tier_name"],
                "primary_reason": payload["primary_reason"],
                "reasons_json": _json_list(payload["reasons"]),
                "would_alert": payload["would_alert"],
                "blocked": payload["blocked"],
                "skipped": payload["skipped"],
                "price_observation_id": payload["price_observation_id"],
                "ath_event_id": payload["ath_event_id"],
                "field_features_id": payload["field_features_id"],
                "score_features_id": payload["score_features_id"],
                "clock_features_id": payload["clock_features_id"],
                "field_score": payload["field_score"],
                "setup_score": payload["setup_score"],
                "clock_score": payload["clock_score"],
                "risk_score": payload["risk_score"],
                "composite_score": payload["composite_score"],
                "ath_price": payload["ath_price"],
                "ath_status": payload["ath_status"],
                "ath_confidence": payload["ath_confidence"],
                "ath_source": payload["ath_source"],
                "price_age_seconds": payload["price_age_seconds"],
                "pump_multiple": payload["pump_multiple"],
                "drawdown_from_ath": payload["drawdown_from_ath"],
                "current_price": payload["current_price"],
                "current_mcap": payload["current_mcap"],
                "filter_labels_json": _json_dict(payload["filter_labels"]),
                "tier_context_json": _json_dict(payload["tier_context"]),
                "key_feature_snapshot_json": _json_dict(payload["key_feature_snapshot"]),
                "policy_version": payload["policy_version"],
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get(self, decision_id: int) -> Optional[AlertDecision]:
        row = self._fetchone(
            "SELECT * FROM alert_decisions WHERE id = ?",
            (decision_id,),
        )
        return _alert_decision_from_row(row) if row else None

    def list_by_token(self, token_address: str, limit: int = 100) -> List[AlertDecision]:
        rows = self._fetchall(
            """
            SELECT * FROM alert_decisions
            WHERE token_address = ?
            ORDER BY evaluated_at DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_alert_decision_from_row(row) for row in rows]

    def list_recent(self, limit: int = 100) -> List[AlertDecision]:
        rows = self._fetchall(
            """
            SELECT * FROM alert_decisions
            ORDER BY evaluated_at DESC, id DESC
            LIMIT ?
            """,
            (_limit(limit),),
        )
        return [_alert_decision_from_row(row) for row in rows]

    def list_would_alert(
        self,
        limit: int = 100,
        offset: int = 0,
        order: Literal["asc", "desc"] = "desc",
    ) -> List[AlertDecision]:
        """Return WOULD_ALERT decisions, newest-first by default.

        ``order="asc"`` returns oldest-first, used by OutcomeTrackingService for
        deterministic backfill progression. ``offset`` enables paging through
        large historical sets without re-reading processed rows.
        """

        if order not in ("asc", "desc"):
            raise ValueError(f"order must be 'asc' or 'desc', got {order!r}")
        direction = "ASC" if order == "asc" else "DESC"
        rows = self._fetchall(
            f"""
            SELECT * FROM alert_decisions
            WHERE would_alert = 1
            ORDER BY evaluated_at {direction}, id {direction}
            LIMIT ? OFFSET ?
            """,
            (_limit(limit), max(0, int(offset))),
        )
        return [_alert_decision_from_row(row) for row in rows]

    def list_pending_would_alert_with_ids(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[tuple]:
        """Return (id, AlertDecision) pairs for WOULD_ALERT decisions, oldest-first.

        Stage 9 OutcomeTrackingService needs the row id to write outcome_windows
        rows, but the AlertDecision dataclass does not currently expose its
        primary key. This method returns the id alongside the hydrated row so
        the service does not need to re-query by composite key.

        Both ``decision_type = 'would_alert'`` and ``would_alert = 1`` are
        filtered: layered defense paired with the service-side decision_type
        re-check. Either filter alone is sufficient in practice today, but
        keeping both means a regression in either layer cannot leak SKIP/
        BLOCK/ERROR rows into outcome_windows.
        """

        rows = self._fetchall(
            """
            SELECT * FROM alert_decisions
            WHERE decision_type = 'would_alert' AND would_alert = 1
            ORDER BY evaluated_at ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (_limit(limit), max(0, int(offset))),
        )
        return [(int(row["id"]), _alert_decision_from_row(row)) for row in rows]

    def list_would_alerts_for_token(
        self,
        token_address: str,
        as_of_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[AlertDecision]:
        """Return prior WOULD_ALERT decisions for one token, oldest first.

        Used by AlertEligibilityEngine to detect duplicate-tier and
        tier-progression conditions. When ``as_of_time`` is provided, only
        rows with ``evaluated_at <= as_of_time`` are returned (inclusive),
        which prevents future WOULD_ALERTs from leaking into a historical or
        replay evaluation.
        """

        if as_of_time is None:
            rows = self._fetchall(
                """
                SELECT * FROM alert_decisions
                WHERE token_address = ? AND would_alert = 1
                ORDER BY evaluated_at ASC, id ASC
                LIMIT ?
                """,
                (token_address, _limit(limit)),
            )
        else:
            rows = self._fetchall(
                """
                SELECT * FROM alert_decisions
                WHERE token_address = ? AND would_alert = 1
                  AND evaluated_at <= ?
                ORDER BY evaluated_at ASC, id ASC
                LIMIT ?
                """,
                (token_address, _to_db_value(as_of_time), _limit(limit)),
            )
        return [_alert_decision_from_row(row) for row in rows]


class FilterEvaluationRepository(RepositoryContract):
    """Persistence for filter_evaluations."""

    def insert(self, result: FilterResult) -> int:
        payload = _payload(result)
        output_reason = payload["output_reason"]
        return self._insert(
            "filter_evaluations",
            {
                "token_address": payload["token_address"],
                "as_of_time": payload["as_of_time"],
                "alert_decision_id": payload["alert_decision_id"],
                "filter_name": payload["filter_name"],
                "filter_version": payload["filter_version"],
                "threshold_version": payload["threshold_version"],
                "label": payload["label"],
                "score": payload["score"],
                "would_block": payload["would_block"],
                "policy_action": payload["policy_action"],
                "reason": payload["reason"],
                "input_snapshot_json": _json_dict(payload["input_snapshot"]),
                "output_reason_json": (
                    _json_dict(output_reason) if output_reason is not None else None
                ),
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def list_by_token(self, token_address: str, limit: int = 100) -> List[FilterResult]:
        rows = self._fetchall(
            """
            SELECT * FROM filter_evaluations
            WHERE token_address = ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_filter_result_from_row(row) for row in rows]

    def get_by_decision(self, alert_decision_id: int) -> List[FilterResult]:
        rows = self._fetchall(
            """
            SELECT * FROM filter_evaluations
            WHERE alert_decision_id = ?
            ORDER BY id ASC
            """,
            (alert_decision_id,),
        )
        return [_filter_result_from_row(row) for row in rows]

    def exists_for_decision(
        self,
        alert_decision_id: int,
        filter_name: str,
        filter_version: str,
        threshold_version: str,
    ) -> bool:
        row = self._fetchone(
            """
            SELECT 1 FROM filter_evaluations
            WHERE alert_decision_id = ?
              AND filter_name = ?
              AND filter_version = ?
              AND threshold_version = ?
            LIMIT 1
            """,
            (alert_decision_id, filter_name, filter_version, threshold_version),
        )
        return row is not None


class FeeWindowRepository(RepositoryContract):
    """Persistence for fee_windows."""

    def insert(self, window: FeeWindow) -> int:
        return self.upsert(window)

    def upsert(self, window: FeeWindow) -> int:
        payload = _payload(window)
        values = {
            "token_address": payload["token_address"],
            "pool_address": payload["pool_address"],
            "as_of_time": payload["as_of_time"],
            "window_seconds": payload["window_seconds"],
            "first_event_time": payload["first_event_time"],
            "last_event_time": payload["last_event_time"],
            "event_count": payload["event_count"],
            "buy_count": payload["buy_count"],
            "sell_count": payload["sell_count"],
            "total_fee_sol": payload["total_fee_sol"],
            "lp_fee_sol": payload["lp_fee_sol"],
            "protocol_fee_sol": payload["protocol_fee_sol"],
            "creator_fee_sol": payload["creator_fee_sol"],
            "creator_fee_share": payload["creator_fee_share"],
            "lp_fee_share": payload["lp_fee_share"],
            "protocol_fee_share": payload["protocol_fee_share"],
            "avg_fee_per_event_sol": payload["avg_fee_per_event_sol"],
            "median_fee_per_event_sol": payload["median_fee_per_event_sol"],
            "max_fee_event_sol": payload["max_fee_event_sol"],
            "events_per_min": payload["events_per_min"],
            "fees_per_min_sol": payload["fees_per_min_sol"],
            "buy_sell_count_ratio": payload["buy_sell_count_ratio"],
            "buy_sell_fee_ratio": payload["buy_sell_fee_ratio"],
            "source_min_id": payload["source_min_id"],
            "source_max_id": payload["source_max_id"],
            "source_row_count": payload["source_row_count"],
            "created_at": _now_iso(),
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
        }
        self.connection.execute(
            """
            INSERT INTO fee_windows (
                token_address, pool_address, as_of_time, window_seconds,
                first_event_time, last_event_time, event_count, buy_count,
                sell_count, total_fee_sol, lp_fee_sol, protocol_fee_sol,
                creator_fee_sol, creator_fee_share, lp_fee_share,
                protocol_fee_share, avg_fee_per_event_sol,
                median_fee_per_event_sol, max_fee_event_sol, events_per_min,
                fees_per_min_sol, buy_sell_count_ratio, buy_sell_fee_ratio,
                source_min_id, source_max_id, source_row_count, created_at,
                data_status, missing_reasons_json
            )
            VALUES (
                :token_address, :pool_address, :as_of_time, :window_seconds,
                :first_event_time, :last_event_time, :event_count, :buy_count,
                :sell_count, :total_fee_sol, :lp_fee_sol, :protocol_fee_sol,
                :creator_fee_sol, :creator_fee_share, :lp_fee_share,
                :protocol_fee_share, :avg_fee_per_event_sol,
                :median_fee_per_event_sol, :max_fee_event_sol, :events_per_min,
                :fees_per_min_sol, :buy_sell_count_ratio, :buy_sell_fee_ratio,
                :source_min_id, :source_max_id, :source_row_count, :created_at,
                :data_status, :missing_reasons_json
            )
            ON CONFLICT(token_address, as_of_time, window_seconds) DO UPDATE SET
                pool_address = excluded.pool_address,
                first_event_time = excluded.first_event_time,
                last_event_time = excluded.last_event_time,
                event_count = excluded.event_count,
                buy_count = excluded.buy_count,
                sell_count = excluded.sell_count,
                total_fee_sol = excluded.total_fee_sol,
                lp_fee_sol = excluded.lp_fee_sol,
                protocol_fee_sol = excluded.protocol_fee_sol,
                creator_fee_sol = excluded.creator_fee_sol,
                creator_fee_share = excluded.creator_fee_share,
                lp_fee_share = excluded.lp_fee_share,
                protocol_fee_share = excluded.protocol_fee_share,
                avg_fee_per_event_sol = excluded.avg_fee_per_event_sol,
                median_fee_per_event_sol = excluded.median_fee_per_event_sol,
                max_fee_event_sol = excluded.max_fee_event_sol,
                events_per_min = excluded.events_per_min,
                fees_per_min_sol = excluded.fees_per_min_sol,
                buy_sell_count_ratio = excluded.buy_sell_count_ratio,
                buy_sell_fee_ratio = excluded.buy_sell_fee_ratio,
                source_min_id = excluded.source_min_id,
                source_max_id = excluded.source_max_id,
                source_row_count = excluded.source_row_count,
                created_at = excluded.created_at,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json
            """,
            {key: _to_db_value(value) for key, value in values.items()},
        )
        self._commit_if_top_level()
        row = self._fetchone(
            """
            SELECT id FROM fee_windows
            WHERE token_address = ? AND as_of_time = ? AND window_seconds = ?
            """,
            (
                payload["token_address"],
                _to_db_value(payload["as_of_time"]),
                payload["window_seconds"],
            ),
        )
        return int(row["id"])

    def get(
        self,
        token_address: str,
        as_of_time: Any,
        window_seconds: int,
    ) -> Optional[FeeWindow]:
        row = self._fetchone(
            """
            SELECT * FROM fee_windows
            WHERE token_address = ? AND as_of_time = ? AND window_seconds = ?
            """,
            (token_address, _to_db_value(as_of_time), window_seconds),
        )
        return _fee_window_from_row(row) if row else None

    def get_by_id(self, fee_window_id: int) -> Optional[FeeWindow]:
        """Load fee_window row by primary key.

        Stage 11 navigates ``field_features.fee_window_300s_id`` (and the
        peer 60s/900s/1800s/3600s FKs) to load typed 5m amounts and the
        non-5m aux-window snapshots. FK navigation by id is the cleaner
        read than ``get(token, as_of, 300)``: it does not depend on the
        invariant that field_features and fee_windows share the same
        as_of_time. Mirrors ``AlertDecisionRepository.get`` and
        ``FieldFeatureRepository.get_by_id`` shape.
        """

        row = self._fetchone(
            "SELECT * FROM fee_windows WHERE id = ?",
            (fee_window_id,),
        )
        return _fee_window_from_row(row) if row else None

    def list_by_token(self, token_address: str, limit: int = 100) -> List[FeeWindow]:
        rows = self._fetchall(
            """
            SELECT * FROM fee_windows
            WHERE token_address = ?
            ORDER BY as_of_time DESC, window_seconds ASC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_fee_window_from_row(row) for row in rows]


class RawPumpSwapEventRepository(RepositoryContract):
    """Persistence for raw_pumpswap_events."""

    def insert(self, event: RawPumpSwapEvent) -> int:
        payload = _payload(event)
        return self._insert(
            "raw_pumpswap_events",
            {
                "observed_at": payload["observed_at"],
                "source": payload["source"],
                "subscription": payload["subscription"],
                "signature": payload["signature"],
                "slot": payload["slot"],
                "block_time": payload["block_time"],
                "transaction_index": payload["transaction_index"],
                "instruction_index": payload["instruction_index"],
                "inner_instruction_index": payload["inner_instruction_index"],
                "event_index": payload["event_index"],
                "dedupe_key": payload["dedupe_key"],
                "pool_address": payload["pool_address"],
                "token_address": payload["token_address"],
                "base_mint": payload["base_mint"],
                "quote_mint": payload["quote_mint"],
                "user_address": payload["user_address"],
                "event_type": payload["event_type"],
                "base_amount_raw": payload["base_amount_raw"],
                "quote_amount_raw": payload["quote_amount_raw"],
                "base_amount_token": payload["base_amount_token"],
                "quote_amount_sol": payload["quote_amount_sol"],
                "price_sol": payload["price_sol"],
                "price_usd": payload["price_usd"],
                "mcap": payload["mcap"],
                "lp_fee_sol": payload["lp_fee_sol"],
                "protocol_fee_sol": payload["protocol_fee_sol"],
                "creator_fee_sol": payload["creator_fee_sol"],
                "total_fee_sol": payload["total_fee_sol"],
                "fee_unit": payload["fee_unit"],
                "fee_invariant_ok": payload["fee_invariant_ok"],
                "decoder_name": payload["decoder_name"],
                "decoder_version": payload["decoder_version"],
                "raw_payload_json": _json_dict(payload["raw_payload"]),
                "created_at": payload["created_at"] or _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get_by_dedupe_key(self, dedupe_key: str) -> Optional[RawPumpSwapEvent]:
        row = self._fetchone(
            "SELECT * FROM raw_pumpswap_events WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        return _raw_pumpswap_event_from_row(row) if row else None

    def list_by_token(
        self,
        token_address: str,
        limit: int = 100,
    ) -> List[RawPumpSwapEvent]:
        rows = self._fetchall(
            """
            SELECT * FROM raw_pumpswap_events
            WHERE token_address = ?
            ORDER BY block_time DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_raw_pumpswap_event_from_row(row) for row in rows]

    def list_window(
        self,
        token_address: str,
        start_time: Any,
        end_time: Any,
        limit: Optional[int] = None,
    ) -> List[RawPumpSwapEvent]:
        params: List[Any] = [
            token_address,
            _to_db_value(start_time),
            _to_db_value(end_time),
        ]
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(_limit(limit))

        rows = self._fetchall(
            f"""
            SELECT * FROM raw_pumpswap_events
            WHERE token_address = ?
                AND COALESCE(block_time, observed_at) >= ?
                AND COALESCE(block_time, observed_at) <= ?
            ORDER BY COALESCE(block_time, observed_at) ASC, id ASC
            {limit_sql}
            """,
            params,
        )
        return [_raw_pumpswap_event_from_row(row) for row in rows]

    def count_by_token(self, token_address: str) -> int:
        row = self._fetchone(
            """
            SELECT COUNT(*) AS count
            FROM raw_pumpswap_events
            WHERE token_address = ?
            """,
            (token_address,),
        )
        return int(row["count"])


class PriceCurvePointRepository(RepositoryContract):
    """Persistence for observe-only price_curve_points."""

    def insert(self, point: PriceCurvePoint) -> int:
        return self.upsert(point)

    def upsert(self, point: PriceCurvePoint) -> int:
        payload = _payload(point)
        values = {
            "token_address": payload["token_address"],
            "anchor_type": payload["anchor_type"],
            "anchor_key": payload["anchor_key"],
            "anchor_time": payload["anchor_time"],
            "anchor_ref_id": payload["anchor_ref_id"],
            "bucket_seconds": payload["bucket_seconds"],
            "bucket_start_time": payload["bucket_start_time"],
            "bucket_end_time": payload["bucket_end_time"],
            "observed_at": payload["observed_at"],
            "price_observation_id": payload["price_observation_id"],
            "price": payload["price"],
            "mcap": payload["mcap"],
            "liquidity_usd": payload["liquidity_usd"],
            "normalized_price": payload["normalized_price"],
            "normalized_mcap": payload["normalized_mcap"],
            "return_from_anchor": payload["return_from_anchor"],
            "return_from_migration": payload["return_from_migration"],
            "drawdown_from_ath": payload["drawdown_from_ath"],
            "age_since_migration_s": payload["age_since_migration_s"],
            "time_since_ath_s": payload["time_since_ath_s"],
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
            "created_at": payload["created_at"] or _now_iso(),
        }
        self.connection.execute(
            """
            INSERT INTO price_curve_points (
                token_address, anchor_type, anchor_key, anchor_time,
                anchor_ref_id, bucket_seconds, bucket_start_time,
                bucket_end_time, observed_at, price_observation_id, price,
                mcap, liquidity_usd, normalized_price, normalized_mcap,
                return_from_anchor, return_from_migration, drawdown_from_ath,
                age_since_migration_s, time_since_ath_s, data_status,
                missing_reasons_json, created_at
            )
            VALUES (
                :token_address, :anchor_type, :anchor_key, :anchor_time,
                :anchor_ref_id, :bucket_seconds, :bucket_start_time,
                :bucket_end_time, :observed_at, :price_observation_id, :price,
                :mcap, :liquidity_usd, :normalized_price, :normalized_mcap,
                :return_from_anchor, :return_from_migration, :drawdown_from_ath,
                :age_since_migration_s, :time_since_ath_s, :data_status,
                :missing_reasons_json, :created_at
            )
            ON CONFLICT(token_address, anchor_key, bucket_seconds) DO UPDATE SET
                anchor_type = excluded.anchor_type,
                anchor_time = excluded.anchor_time,
                anchor_ref_id = excluded.anchor_ref_id,
                bucket_start_time = excluded.bucket_start_time,
                bucket_end_time = excluded.bucket_end_time,
                observed_at = excluded.observed_at,
                price_observation_id = excluded.price_observation_id,
                price = excluded.price,
                mcap = excluded.mcap,
                liquidity_usd = excluded.liquidity_usd,
                normalized_price = excluded.normalized_price,
                normalized_mcap = excluded.normalized_mcap,
                return_from_anchor = excluded.return_from_anchor,
                return_from_migration = excluded.return_from_migration,
                drawdown_from_ath = excluded.drawdown_from_ath,
                age_since_migration_s = excluded.age_since_migration_s,
                time_since_ath_s = excluded.time_since_ath_s,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json,
                created_at = excluded.created_at
            """,
            {key: _to_db_value(value) for key, value in values.items()},
        )
        self._commit_if_top_level()
        row = self._fetchone(
            """
            SELECT id FROM price_curve_points
            WHERE token_address = ? AND anchor_key = ? AND bucket_seconds = ?
            """,
            (
                payload["token_address"],
                payload["anchor_key"],
                payload["bucket_seconds"],
            ),
        )
        return int(row["id"])

    def get(
        self,
        token_address: str,
        anchor_key: str,
        bucket_seconds: int,
    ) -> Optional[PriceCurvePoint]:
        row = self._fetchone(
            """
            SELECT * FROM price_curve_points
            WHERE token_address = ?
                AND anchor_key = ?
                AND bucket_seconds = ?
            """,
            (token_address, anchor_key, bucket_seconds),
        )
        return _price_curve_point_from_row(row) if row else None

    def list_by_token(
        self,
        token_address: str,
        limit: int = 100,
    ) -> List[PriceCurvePoint]:
        rows = self._fetchall(
            """
            SELECT * FROM price_curve_points
            WHERE token_address = ?
            ORDER BY anchor_time DESC, bucket_seconds ASC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_price_curve_point_from_row(row) for row in rows]

    def list_by_anchor(
        self,
        token_address: str,
        anchor_type: str,
        limit: int = 100,
    ) -> List[PriceCurvePoint]:
        rows = self._fetchall(
            """
            SELECT * FROM price_curve_points
            WHERE token_address = ? AND anchor_type = ?
            ORDER BY bucket_seconds ASC, anchor_time DESC, id DESC
            LIMIT ?
            """,
            (token_address, anchor_type, _limit(limit)),
        )
        return [_price_curve_point_from_row(row) for row in rows]

    def list_bucket(
        self,
        anchor_type: str,
        bucket_seconds: int,
        limit: int = 100,
    ) -> List[PriceCurvePoint]:
        rows = self._fetchall(
            """
            SELECT * FROM price_curve_points
            WHERE anchor_type = ? AND bucket_seconds = ?
            ORDER BY anchor_time DESC, id DESC
            LIMIT ?
            """,
            (anchor_type, bucket_seconds, _limit(limit)),
        )
        return [_price_curve_point_from_row(row) for row in rows]


class FieldFeatureRepository(RepositoryContract):
    """Persistence for field_features."""

    def insert(self, features: FieldFeatures) -> int:
        return self.upsert(features)

    def upsert(self, features: FieldFeatures) -> int:
        payload = _payload(features)
        values = {
            "token_address": payload["token_address"],
            "as_of_time": payload["as_of_time"],
            "fee_window_60s_id": payload["fee_window_60s_id"],
            "fee_window_300s_id": payload["fee_window_300s_id"],
            "fee_window_900s_id": payload["fee_window_900s_id"],
            "fee_window_1800s_id": payload["fee_window_1800s_id"],
            "fee_window_3600s_id": payload["fee_window_3600s_id"],
            "liquidity_usd": payload["liquidity_usd"],
            "lp_floor_label": payload["lp_floor_label"],
            "lp_fragility_score": payload["lp_fragility_score"],
            "fee_gate_label": payload["fee_gate_label"],
            "fee_gate_score": payload["fee_gate_score"],
            "ante_label_5m": payload["ante_label_5m"],
            "ante_label_20sw": payload["ante_label_20sw"],
            "ghost_label": payload["ghost_label"],
            "holder_label": payload["holder_label"],
            "event_pace_5m": payload["event_pace_5m"],
            "fee_pace_5m_sol": payload["fee_pace_5m_sol"],
            "creator_fee_share_5m": payload["creator_fee_share_5m"],
            "lp_fee_share_5m": payload["lp_fee_share_5m"],
            "protocol_fee_share_5m": payload["protocol_fee_share_5m"],
            "buy_sell_ratio_5m": payload["buy_sell_ratio_5m"],
            "event_count_5m": payload["event_count_5m"],
            "raw_snapshot_json": _json_dict(payload["raw_snapshot"]),
            "feature_version": payload["feature_version"],
            "created_at": _now_iso(),
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
        }
        self.connection.execute(
            """
            INSERT INTO field_features (
                token_address, as_of_time, fee_window_60s_id,
                fee_window_300s_id, fee_window_900s_id, fee_window_1800s_id,
                fee_window_3600s_id, liquidity_usd, lp_floor_label,
                lp_fragility_score, fee_gate_label, fee_gate_score,
                ante_label_5m, ante_label_20sw, ghost_label, holder_label,
                event_pace_5m, fee_pace_5m_sol, creator_fee_share_5m,
                lp_fee_share_5m, protocol_fee_share_5m, buy_sell_ratio_5m,
                event_count_5m, raw_snapshot_json, feature_version,
                created_at, data_status, missing_reasons_json
            )
            VALUES (
                :token_address, :as_of_time, :fee_window_60s_id,
                :fee_window_300s_id, :fee_window_900s_id,
                :fee_window_1800s_id, :fee_window_3600s_id, :liquidity_usd,
                :lp_floor_label, :lp_fragility_score, :fee_gate_label,
                :fee_gate_score, :ante_label_5m, :ante_label_20sw,
                :ghost_label, :holder_label, :event_pace_5m,
                :fee_pace_5m_sol, :creator_fee_share_5m, :lp_fee_share_5m,
                :protocol_fee_share_5m, :buy_sell_ratio_5m,
                :event_count_5m, :raw_snapshot_json, :feature_version,
                :created_at, :data_status, :missing_reasons_json
            )
            ON CONFLICT(token_address, as_of_time, feature_version) DO UPDATE SET
                fee_window_60s_id = excluded.fee_window_60s_id,
                fee_window_300s_id = excluded.fee_window_300s_id,
                fee_window_900s_id = excluded.fee_window_900s_id,
                fee_window_1800s_id = excluded.fee_window_1800s_id,
                fee_window_3600s_id = excluded.fee_window_3600s_id,
                liquidity_usd = excluded.liquidity_usd,
                lp_floor_label = excluded.lp_floor_label,
                lp_fragility_score = excluded.lp_fragility_score,
                fee_gate_label = excluded.fee_gate_label,
                fee_gate_score = excluded.fee_gate_score,
                ante_label_5m = excluded.ante_label_5m,
                ante_label_20sw = excluded.ante_label_20sw,
                ghost_label = excluded.ghost_label,
                holder_label = excluded.holder_label,
                event_pace_5m = excluded.event_pace_5m,
                fee_pace_5m_sol = excluded.fee_pace_5m_sol,
                creator_fee_share_5m = excluded.creator_fee_share_5m,
                lp_fee_share_5m = excluded.lp_fee_share_5m,
                protocol_fee_share_5m = excluded.protocol_fee_share_5m,
                buy_sell_ratio_5m = excluded.buy_sell_ratio_5m,
                event_count_5m = excluded.event_count_5m,
                raw_snapshot_json = excluded.raw_snapshot_json,
                created_at = excluded.created_at,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json
            """,
            {key: _to_db_value(value) for key, value in values.items()},
        )
        self._commit_if_top_level()
        row = self._fetchone(
            """
            SELECT id FROM field_features
            WHERE token_address = ? AND as_of_time = ? AND feature_version = ?
            """,
            (
                payload["token_address"],
                _to_db_value(payload["as_of_time"]),
                payload["feature_version"],
            ),
        )
        return int(row["id"])

    def get_by_id(self, features_id: int) -> Optional[FieldFeatures]:
        row = self._fetchone(
            "SELECT * FROM field_features WHERE id = ?",
            (features_id,),
        )
        return _field_features_from_row(row) if row else None

    def get_latest(self, token_address: str) -> Optional[FieldFeatures]:
        row = self._fetchone(
            """
            SELECT * FROM field_features
            WHERE token_address = ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT 1
            """,
            (token_address,),
        )
        return _field_features_from_row(row) if row else None

    def get_latest_at_or_before(
        self,
        token_address: str,
        as_of_time: Any,
    ) -> Optional[FieldFeatures]:
        row = self._fetchone(
            """
            SELECT * FROM field_features
            WHERE token_address = ? AND as_of_time <= ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT 1
            """,
            (token_address, _to_db_value(as_of_time)),
        )
        return _field_features_from_row(row) if row else None


class ScoreFeatureRepository(RepositoryContract):
    """Persistence for score_features."""

    def insert(self, features: ScoreFeatures) -> int:
        payload = _payload(features)
        return self._insert(
            "score_features",
            {
                "token_address": payload["token_address"],
                "as_of_time": payload["as_of_time"],
                "score_version": payload["score_version"],
                "field_score": payload["field_score"],
                "setup_score": payload["setup_score"],
                "clock_score": payload["clock_score"],
                "risk_score": payload["risk_score"],
                "composite_score": payload["composite_score"],
                "pump_multiple": payload["pump_multiple"],
                "drawdown_from_ath": payload["drawdown_from_ath"],
                "ath_quality_score": payload["ath_quality_score"],
                "price_freshness_score": payload["price_freshness_score"],
                "liquidity_quality_score": payload["liquidity_quality_score"],
                "fee_quality_score": payload["fee_quality_score"],
                "participation_quality_score": payload["participation_quality_score"],
                "organic_risk_score": payload["organic_risk_score"],
                "scam_risk_score": payload["scam_risk_score"],
                "dip_speed_score": payload["dip_speed_score"],
                "support_reclaim_quality_score": payload[
                    "support_reclaim_quality_score"
                ],
                "components_json": _json_dict(payload["components"]),
                "created_at": _now_iso(),
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get_latest(
        self,
        token_address: str,
        score_version: Optional[str] = None,
    ) -> Optional[ScoreFeatures]:
        if score_version is None:
            row = self._fetchone(
                """
                SELECT * FROM score_features
                WHERE token_address = ?
                ORDER BY as_of_time DESC, id DESC
                LIMIT 1
                """,
                (token_address,),
            )
        else:
            row = self._fetchone(
                """
                SELECT * FROM score_features
                WHERE token_address = ? AND score_version = ?
                ORDER BY as_of_time DESC, id DESC
                LIMIT 1
                """,
                (token_address, score_version),
            )
        return _score_features_from_row(row) if row else None

    def get_latest_at_or_before(
        self,
        token_address: str,
        as_of_time: Any,
    ) -> Optional[ScoreFeatures]:
        row = self._fetchone(
            """
            SELECT * FROM score_features
            WHERE token_address = ? AND as_of_time <= ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT 1
            """,
            (token_address, _to_db_value(as_of_time)),
        )
        return _score_features_from_row(row) if row else None


class ClockFeatureRepository(RepositoryContract):
    """Persistence for clock_features."""

    def insert(self, features: ClockFeatures) -> int:
        return self.upsert(features)

    def upsert(self, features: ClockFeatures) -> int:
        payload = _payload(features)
        values = {
            "token_address": payload["token_address"],
            "as_of_time": payload["as_of_time"],
            "migration_time": payload["migration_time"],
            "age_since_migration_s": payload["age_since_migration_s"],
            "ath_time": payload["ath_time"],
            "time_to_ath_s": payload["time_to_ath_s"],
            "time_since_ath_s": payload["time_since_ath_s"],
            "tier_1_time": payload["tier_1_time"],
            "tier_2_time": payload["tier_2_time"],
            "tier_3_time": payload["tier_3_time"],
            "time_ath_to_t1_s": payload["time_ath_to_t1_s"],
            "time_ath_to_t2_s": payload["time_ath_to_t2_s"],
            "time_ath_to_t3_s": payload["time_ath_to_t3_s"],
            "time_t1_to_t2_s": payload["time_t1_to_t2_s"],
            "time_t2_to_t3_s": payload["time_t2_to_t3_s"],
            "dip_velocity_pct_per_min": payload["dip_velocity_pct_per_min"],
            "recovery_velocity_pct_per_min": payload[
                "recovery_velocity_pct_per_min"
            ],
            "last_fee_event_time": payload["last_fee_event_time"],
            "last_buy_time": payload["last_buy_time"],
            "last_sell_time": payload["last_sell_time"],
            "time_since_last_fee_event_s": payload["time_since_last_fee_event_s"],
            "time_since_last_buy_s": payload["time_since_last_buy_s"],
            "time_since_last_sell_s": payload["time_since_last_sell_s"],
            "sequence_phase": payload["sequence_phase"],
            "phase_reason": payload["phase_reason"],
            "feature_version": payload["feature_version"],
            "created_at": _now_iso(),
            "data_status": payload["data_status"],
            "missing_reasons_json": _json_list(payload["missing_reasons"]),
        }
        self.connection.execute(
            """
            INSERT INTO clock_features (
                token_address, as_of_time, migration_time,
                age_since_migration_s, ath_time, time_to_ath_s,
                time_since_ath_s, tier_1_time, tier_2_time, tier_3_time,
                time_ath_to_t1_s, time_ath_to_t2_s, time_ath_to_t3_s,
                time_t1_to_t2_s, time_t2_to_t3_s, dip_velocity_pct_per_min,
                recovery_velocity_pct_per_min, last_fee_event_time,
                last_buy_time, last_sell_time, time_since_last_fee_event_s,
                time_since_last_buy_s, time_since_last_sell_s, sequence_phase,
                phase_reason, feature_version, created_at, data_status,
                missing_reasons_json
            )
            VALUES (
                :token_address, :as_of_time, :migration_time,
                :age_since_migration_s, :ath_time, :time_to_ath_s,
                :time_since_ath_s, :tier_1_time, :tier_2_time, :tier_3_time,
                :time_ath_to_t1_s, :time_ath_to_t2_s, :time_ath_to_t3_s,
                :time_t1_to_t2_s, :time_t2_to_t3_s, :dip_velocity_pct_per_min,
                :recovery_velocity_pct_per_min, :last_fee_event_time,
                :last_buy_time, :last_sell_time, :time_since_last_fee_event_s,
                :time_since_last_buy_s, :time_since_last_sell_s,
                :sequence_phase, :phase_reason, :feature_version, :created_at,
                :data_status, :missing_reasons_json
            )
            ON CONFLICT(token_address, as_of_time, feature_version) DO UPDATE SET
                migration_time = excluded.migration_time,
                age_since_migration_s = excluded.age_since_migration_s,
                ath_time = excluded.ath_time,
                time_to_ath_s = excluded.time_to_ath_s,
                time_since_ath_s = excluded.time_since_ath_s,
                tier_1_time = excluded.tier_1_time,
                tier_2_time = excluded.tier_2_time,
                tier_3_time = excluded.tier_3_time,
                time_ath_to_t1_s = excluded.time_ath_to_t1_s,
                time_ath_to_t2_s = excluded.time_ath_to_t2_s,
                time_ath_to_t3_s = excluded.time_ath_to_t3_s,
                time_t1_to_t2_s = excluded.time_t1_to_t2_s,
                time_t2_to_t3_s = excluded.time_t2_to_t3_s,
                dip_velocity_pct_per_min = excluded.dip_velocity_pct_per_min,
                recovery_velocity_pct_per_min = excluded.recovery_velocity_pct_per_min,
                last_fee_event_time = excluded.last_fee_event_time,
                last_buy_time = excluded.last_buy_time,
                last_sell_time = excluded.last_sell_time,
                time_since_last_fee_event_s = excluded.time_since_last_fee_event_s,
                time_since_last_buy_s = excluded.time_since_last_buy_s,
                time_since_last_sell_s = excluded.time_since_last_sell_s,
                sequence_phase = excluded.sequence_phase,
                phase_reason = excluded.phase_reason,
                created_at = excluded.created_at,
                data_status = excluded.data_status,
                missing_reasons_json = excluded.missing_reasons_json
            """,
            {key: _to_db_value(value) for key, value in values.items()},
        )
        self._commit_if_top_level()
        row = self._fetchone(
            """
            SELECT id FROM clock_features
            WHERE token_address = ? AND as_of_time = ? AND feature_version = ?
            """,
            (
                payload["token_address"],
                _to_db_value(payload["as_of_time"]),
                payload["feature_version"],
            ),
        )
        return int(row["id"])

    def get_by_id(self, features_id: int) -> Optional[ClockFeatures]:
        row = self._fetchone(
            "SELECT * FROM clock_features WHERE id = ?",
            (features_id,),
        )
        return _clock_features_from_row(row) if row else None

    def get_latest(self, token_address: str) -> Optional[ClockFeatures]:
        row = self._fetchone(
            """
            SELECT * FROM clock_features
            WHERE token_address = ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT 1
            """,
            (token_address,),
        )
        return _clock_features_from_row(row) if row else None

    def get_latest_at_or_before(
        self,
        token_address: str,
        as_of_time: Any,
    ) -> Optional[ClockFeatures]:
        row = self._fetchone(
            """
            SELECT * FROM clock_features
            WHERE token_address = ? AND as_of_time <= ?
            ORDER BY as_of_time DESC, id DESC
            LIMIT 1
            """,
            (token_address, _to_db_value(as_of_time)),
        )
        return _clock_features_from_row(row) if row else None


class OutcomeWindowRepository(RepositoryContract):
    """Persistence for outcome_windows.

    Stage 9 schema: insert-only. There is no update, delete, or recompute path
    in v0; once a row is written for a (alert_decision_id, window_seconds)
    pair it is terminal. Service-only statuses (PARTIAL, WINDOW_NOT_ELAPSED,
    ALREADY_RECORDED) are rejected before the DB call as defense in depth
    against the schema-level CHECK constraint.
    """

    def insert(self, outcome: OutcomeWindow) -> int:
        if outcome.data_status not in PERSISTABLE_OUTCOME_WINDOW_STATUSES:
            raise ValueError(
                "OutcomeWindow.data_status must be one of "
                f"{sorted(s.value for s in PERSISTABLE_OUTCOME_WINDOW_STATUSES)}; "
                f"got {outcome.data_status.value!r}. Service-only statuses are "
                "never persisted."
            )
        payload = _payload(outcome)
        return self._insert(
            "outcome_windows",
            {
                "alert_decision_id": payload["alert_decision_id"],
                "token_address": payload["token_address"],
                "window_seconds": payload["window_seconds"],
                "window_start_time": payload["window_start_time"],
                "window_end_time": payload["window_end_time"],
                "alert_price": payload["alert_price"],
                "alert_mcap": payload["alert_mcap"],
                "max_price": payload["max_price"],
                "max_mcap": payload["max_mcap"],
                "max_observation_time": payload["max_observation_time"],
                "min_price": payload["min_price"],
                "min_mcap": payload["min_mcap"],
                "min_observation_time": payload["min_observation_time"],
                "max_return_multiple": payload["max_return_multiple"],
                "max_return_pct": payload["max_return_pct"],
                "min_return_multiple": payload["min_return_multiple"],
                "min_return_pct": payload["min_return_pct"],
                "max_drawdown_from_peak_pct": payload["max_drawdown_from_peak_pct"],
                "time_to_max_return_seconds": payload["time_to_max_return_seconds"],
                "hit_2x": payload["hit_2x"],
                "hit_3x": payload["hit_3x"],
                "hit_5x": payload["hit_5x"],
                "observations_count": payload["observations_count"],
                "first_observation_time": payload["first_observation_time"],
                "last_observation_time": payload["last_observation_time"],
                "data_status": payload["data_status"],
                "created_at": _now_iso(),
            },
        )

    def get_by_decision_and_window(
        self,
        alert_decision_id: int,
        window_seconds: int,
    ) -> Optional[OutcomeWindow]:
        row = self._fetchone(
            """
            SELECT * FROM outcome_windows
            WHERE alert_decision_id = ? AND window_seconds = ?
            """,
            (alert_decision_id, window_seconds),
        )
        return _outcome_window_from_row(row) if row else None

    def get_all_for_decision(self, alert_decision_id: int) -> List[OutcomeWindow]:
        rows = self._fetchall(
            """
            SELECT * FROM outcome_windows
            WHERE alert_decision_id = ?
            ORDER BY window_seconds ASC, id ASC
            """,
            (alert_decision_id,),
        )
        return [_outcome_window_from_row(row) for row in rows]


class DispatchEventRepository(RepositoryContract):
    """Persistence for dispatch_events (Stage 8B audit log).

    Two-phase write: the dispatcher calls ``create`` with a pending row, then
    invokes the sink, then calls ``update_status`` to record the terminal
    outcome. ``exists_non_failed`` enforces the idempotency contract.
    """

    def create(self, event: DispatchEvent) -> None:
        self.connection.execute(
            """
            INSERT INTO dispatch_events (
                id,
                alert_decision_id,
                dispatch_run_id,
                target,
                status,
                decision_type,
                severity,
                tier_label,
                attempted_at,
                completed_at,
                payload_ref,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.alert_decision_id,
                event.dispatch_run_id,
                event.target,
                event.status,
                event.decision_type,
                event.severity,
                event.tier_label,
                _to_db_value(event.attempted_at),
                _to_db_value(event.completed_at),
                event.payload_ref,
                event.error_message,
            ),
        )
        self._commit_if_top_level()

    def get_by_id(self, event_id: str) -> Optional[DispatchEvent]:
        row = self._fetchone(
            "SELECT * FROM dispatch_events WHERE id = ?",
            (event_id,),
        )
        return _dispatch_event_from_row(row) if row else None

    def update_status(
        self,
        event_id: str,
        status: str,
        completed_at: datetime,
        payload_ref: Optional[str],
        error_message: Optional[str],
    ) -> None:
        self.connection.execute(
            """
            UPDATE dispatch_events
            SET status = ?,
                completed_at = ?,
                payload_ref = ?,
                error_message = ?
            WHERE id = ?
            """,
            (
                status,
                _to_db_value(completed_at),
                payload_ref,
                error_message,
                event_id,
            ),
        )
        self._commit_if_top_level()

    def exists_non_failed(self, alert_decision_id: int, target: str) -> bool:
        row = self._fetchone(
            """
            SELECT 1 FROM dispatch_events
            WHERE alert_decision_id = ?
              AND target = ?
              AND status != 'failed'
            LIMIT 1
            """,
            (alert_decision_id, target),
        )
        return row is not None

    def list_by_decision(self, alert_decision_id: int) -> List[DispatchEvent]:
        rows = self._fetchall(
            """
            SELECT * FROM dispatch_events
            WHERE alert_decision_id = ?
            ORDER BY attempted_at ASC, id ASC
            """,
            (alert_decision_id,),
        )
        return [_dispatch_event_from_row(row) for row in rows]


class DecisionScoreFeatureRepository(RepositoryContract):
    """Persistence for decision_score_features (Stage 11).

    Insert-only audit-log shape, matching ``OutcomeWindowRepository``
    and ``FilterEvaluationRepository``. Idempotency is probed via
    ``get_by_decision_and_version`` before insert; UNIQUE-constraint
    races during insert are caught by the service layer
    (``DecisionFeatureSnapshotService``) and resolved by re-probing.
    No upsert path exists -- a snapshot row, once written, is
    terminal under its (alert_decision_id, feature_version) identity.

    Stage 11 writes only to ``decision_score_features``. This class
    therefore exposes no methods that touch any other table.
    """

    def insert(self, snapshot: DecisionScoreFeatures) -> int:
        """Insert one row. Returns the new id.

        Raises ``sqlite3.IntegrityError`` on
        ``UNIQUE(alert_decision_id, feature_version)`` violation. The
        caller (``DecisionFeatureSnapshotService``) catches this case
        and treats it as a UNIQUE-race after re-probing.
        """

        payload = _payload(snapshot)
        return self._insert(
            "decision_score_features",
            {
                "alert_decision_id": payload["alert_decision_id"],
                "feature_version": payload["feature_version"],
                "schema_version": payload["schema_version"],
                "token_address": payload["token_address"],
                "token_symbol": payload["token_symbol"],
                "decision_time": payload["decision_time"],
                "as_of_time": payload["as_of_time"],
                "tier_index": payload["tier_index"],
                "tier_name": payload["tier_name"],
                "alert_price": payload["alert_price"],
                "alert_market_cap": payload["alert_market_cap"],
                "ath_price": payload["ath_price"],
                "ath_market_cap": payload["ath_market_cap"],
                "ath_time": payload["ath_time"],
                "migration_price": payload["migration_price"],
                "migration_market_cap": payload["migration_market_cap"],
                "migration_time": payload["migration_time"],
                "drop_from_ath": payload["drop_from_ath"],
                "multiple_from_migration": payload["multiple_from_migration"],
                "time_since_migration_seconds": payload[
                    "time_since_migration_seconds"
                ],
                "time_since_ath_seconds": payload["time_since_ath_seconds"],
                "time_from_migration_to_ath_seconds": payload[
                    "time_from_migration_to_ath_seconds"
                ],
                "liquidity_usd": payload["liquidity_usd"],
                "event_count_5m": payload["event_count_5m"],
                "total_fee_5m": payload["total_fee_5m"],
                "lp_fee_5m": payload["lp_fee_5m"],
                "protocol_fee_5m": payload["protocol_fee_5m"],
                "creator_fee_5m": payload["creator_fee_5m"],
                "creator_fee_share_5m": payload["creator_fee_share_5m"],
                "lp_fee_share_5m": payload["lp_fee_share_5m"],
                "protocol_fee_share_5m": payload["protocol_fee_share_5m"],
                "fee_per_event_5m": payload["fee_per_event_5m"],
                "events_per_minute_5m": payload["events_per_minute_5m"],
                "fees_per_minute_5m": payload["fees_per_minute_5m"],
                "source_snapshot_json": _json_dict(payload["source_snapshot"]),
                "created_at": payload["created_at"],
                "data_status": payload["data_status"],
                "missing_reasons_json": _json_list(payload["missing_reasons"]),
            },
        )

    def get_by_id(self, snapshot_id: int) -> Optional[DecisionScoreFeatures]:
        row = self._fetchone(
            "SELECT * FROM decision_score_features WHERE id = ?",
            (snapshot_id,),
        )
        return _decision_score_features_from_row(row) if row else None

    def get_by_decision_and_version(
        self,
        alert_decision_id: int,
        feature_version: str,
    ) -> Optional[DecisionScoreFeatures]:
        """Idempotency probe matching UNIQUE(alert_decision_id, feature_version).

        Returns the existing row if present (Already-recorded branch in
        the service), else None (proceed to insert).
        """

        row = self._fetchone(
            """
            SELECT * FROM decision_score_features
            WHERE alert_decision_id = ? AND feature_version = ?
            """,
            (alert_decision_id, feature_version),
        )
        return _decision_score_features_from_row(row) if row else None

    def get_all_for_decision(
        self,
        alert_decision_id: int,
    ) -> List[DecisionScoreFeatures]:
        """All snapshots across feature_versions for one decision.

        Ordered by id ASC (insertion order). Stage 12 typically filters
        the result down to one feature_version for cross-row
        comparability.
        """

        rows = self._fetchall(
            """
            SELECT * FROM decision_score_features
            WHERE alert_decision_id = ?
            ORDER BY id ASC
            """,
            (alert_decision_id,),
        )
        return [_decision_score_features_from_row(row) for row in rows]

    def list_by_token(
        self,
        token_address: str,
        limit: int = 100,
    ) -> List[DecisionScoreFeatures]:
        """Chronological list (decision_time DESC) for one token."""

        rows = self._fetchall(
            """
            SELECT * FROM decision_score_features
            WHERE token_address = ?
            ORDER BY decision_time DESC, id DESC
            LIMIT ?
            """,
            (token_address, _limit(limit)),
        )
        return [_decision_score_features_from_row(row) for row in rows]


@dataclass(frozen=True)
class RepositoryRegistry:
    """Container for PHX2 repositories bound to one SQLite connection."""

    token_sequence: Optional[TokenSequenceRepository] = None
    migration_events: Optional[MigrationEventRepository] = None
    price_observations: Optional[PriceObservationRepository] = None
    ath: Optional[ATHRepository] = None
    alert_decisions: Optional[AlertDecisionRepository] = None
    filter_evaluations: Optional[FilterEvaluationRepository] = None
    fee_windows: Optional[FeeWindowRepository] = None
    field_features: Optional[FieldFeatureRepository] = None
    score_features: Optional[ScoreFeatureRepository] = None
    clock_features: Optional[ClockFeatureRepository] = None
    outcome_windows: Optional[OutcomeWindowRepository] = None
    dispatch_events: Optional[DispatchEventRepository] = None
    raw_pumpswap_events: Optional[RawPumpSwapEventRepository] = None
    price_curve_points: Optional[PriceCurvePointRepository] = None
    decision_score_features: Optional[DecisionScoreFeatureRepository] = None


def repository_registry(connection: sqlite3.Connection) -> RepositoryRegistry:
    """Build repositories for a supplied PHX2 connection."""

    return RepositoryRegistry(
        token_sequence=TokenSequenceRepository(connection),
        migration_events=MigrationEventRepository(connection),
        price_observations=PriceObservationRepository(connection),
        ath=ATHRepository(connection),
        alert_decisions=AlertDecisionRepository(connection),
        filter_evaluations=FilterEvaluationRepository(connection),
        fee_windows=FeeWindowRepository(connection),
        field_features=FieldFeatureRepository(connection),
        score_features=ScoreFeatureRepository(connection),
        clock_features=ClockFeatureRepository(connection),
        outcome_windows=OutcomeWindowRepository(connection),
        dispatch_events=DispatchEventRepository(connection),
        raw_pumpswap_events=RawPumpSwapEventRepository(connection),
        price_curve_points=PriceCurvePointRepository(connection),
        decision_score_features=DecisionScoreFeatureRepository(connection),
    )


def _token_state_from_row(row: sqlite3.Row) -> TokenState:
    return TokenState(
        token_address=row["token_address"],
        symbol=row["symbol"],
        pool_address=row["pool_address"],
        migration_time=_parse_datetime(row["migration_time"]),
        migration_source=row["migration_source"],
        migration_price=row["migration_price"],
        migration_mcap=row["migration_mcap"],
        current_price=row["current_price"],
        current_mcap=row["current_mcap"],
        last_price_update=_parse_datetime(row["last_price_update"]),
        sequence_phase=row["sequence_phase"],
        current_status=row["current_status"],
        last_alerted_tier=row["last_alerted_tier"],
        last_migration_event_id=row["last_migration_event_id"],
        last_price_observation_id=row["last_price_observation_id"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _migration_event_from_row(row: sqlite3.Row) -> MigrationEvent:
    return MigrationEvent(
        token_address=row["token_address"],
        pool_address=row["pool_address"],
        migration_time=_parse_datetime(row["migration_time"]),
        migration_source=row["migration_source"],
        signature=row["signature"],
        slot=row["slot"],
        block_time=_parse_datetime(row["block_time"]),
        migration_price=row["migration_price"],
        migration_mcap=row["migration_mcap"],
        raw_payload_json=_load_json(row["raw_payload_json"], {}),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _price_observation_from_row(row: sqlite3.Row) -> PriceObservation:
    return PriceObservation(
        id=row["id"],
        token_address=row["token_address"],
        observed_at=_parse_datetime(row["observed_at"]),
        source=row["source"],
        price=row["price"],
        mcap=row["mcap"],
        liquidity_usd=row["liquidity_usd"],
        source_timestamp=_parse_datetime(row["source_timestamp"]),
        age_seconds=row["age_seconds"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _ath_state_from_row(row: sqlite3.Row) -> ATHState:
    return ATHState(
        token_address=row["token_address"],
        ath_price=row["ath_price"],
        ath_mcap=row["ath_mcap"],
        ath_time=_parse_datetime(row["ath_time"]),
        ath_status=_enum_value(ATHStatus, row["ath_status"], ATHStatus.UNKNOWN),
        ath_confidence=_enum_value(
            ATHConfidence,
            row["ath_confidence"],
            ATHConfidence.UNKNOWN,
        ),
        ath_source=row["ath_source"],
        last_event_id=row["last_event_id"],
        updated_at=_parse_datetime(row["updated_at"]),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _ath_event_from_row(row: sqlite3.Row) -> ATHEvent:
    return ATHEvent(
        token_address=row["token_address"],
        id=row["id"],
        event_time=_parse_datetime(row["event_time"]),
        price_observation_id=row["price_observation_id"],
        candidate_price=row["candidate_price"],
        candidate_mcap=row["candidate_mcap"],
        candidate_source=row["candidate_source"],
        prior_ath_price=row["prior_ath_price"],
        prior_ath_mcap=row["prior_ath_mcap"],
        new_ath_price=row["new_ath_price"],
        new_ath_mcap=row["new_ath_mcap"],
        status_before=_enum_value(ATHStatus, row["status_before"], ATHStatus.UNKNOWN),
        status_after=_enum_value(ATHStatus, row["status_after"], ATHStatus.UNKNOWN),
        confidence_before=_enum_value(
            ATHConfidence,
            row["confidence_before"],
            ATHConfidence.UNKNOWN,
        ),
        confidence_after=_enum_value(
            ATHConfidence,
            row["confidence_after"],
            ATHConfidence.UNKNOWN,
        ),
        mutation_type=_enum_value(
            ATHEventType,
            row["mutation_type"],
            ATHEventType.ATH_NO_CHANGE,
        ),
        reason=row["reason"],
        accepted=bool(row["accepted"]),
        data_limited=bool(row["data_limited"]),
        input_snapshot=_load_json(row["input_snapshot_json"], {}),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _alert_decision_from_row(row: sqlite3.Row) -> AlertDecision:
    reasons = [
        _enum_value(DecisionReason, reason, DecisionReason.ERROR)
        for reason in _load_json(row["reasons_json"], [])
    ]
    return AlertDecision(
        token_address=row["token_address"],
        evaluated_at=_parse_datetime(row["evaluated_at"]),
        decision_type=_enum_value(DecisionType, row["decision_type"], DecisionType.ERROR),
        tier_index=row["tier_index"],
        tier_name=row["tier_name"],
        primary_reason=_enum_value(
            DecisionReason,
            row["primary_reason"],
            DecisionReason.ERROR,
        ),
        reasons=reasons,
        would_alert=bool(row["would_alert"]),
        blocked=bool(row["blocked"]),
        skipped=bool(row["skipped"]),
        price_observation_id=row["price_observation_id"],
        ath_event_id=row["ath_event_id"],
        field_features_id=row["field_features_id"],
        score_features_id=row["score_features_id"],
        clock_features_id=row["clock_features_id"],
        field_score=row["field_score"],
        setup_score=row["setup_score"],
        clock_score=row["clock_score"],
        risk_score=row["risk_score"],
        composite_score=row["composite_score"],
        ath_price=row["ath_price"],
        ath_status=_enum_value(ATHStatus, row["ath_status"], ATHStatus.UNKNOWN),
        ath_confidence=_enum_value(
            ATHConfidence,
            row["ath_confidence"],
            ATHConfidence.UNKNOWN,
        ),
        ath_source=row["ath_source"],
        price_age_seconds=row["price_age_seconds"],
        pump_multiple=row["pump_multiple"],
        drawdown_from_ath=row["drawdown_from_ath"],
        current_price=row["current_price"],
        current_mcap=row["current_mcap"],
        filter_labels=_load_json(row["filter_labels_json"], {}),
        tier_context=_load_json(row["tier_context_json"], {}),
        key_feature_snapshot=_load_json(row["key_feature_snapshot_json"], {}),
        policy_version=row["policy_version"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _filter_result_from_row(row: sqlite3.Row) -> FilterResult:
    output_reason_json = row["output_reason_json"]
    return FilterResult(
        token_address=row["token_address"],
        as_of_time=_parse_datetime(row["as_of_time"]),
        filter_name=row["filter_name"],
        filter_version=row["filter_version"],
        threshold_version=row["threshold_version"],
        label=_enum_value(FilterLabel, row["label"], FilterLabel.UNKNOWN),
        score=row["score"],
        would_block=bool(row["would_block"]),
        policy_action=row["policy_action"],
        reason=row["reason"],
        input_snapshot=_load_json(row["input_snapshot_json"], {}),
        output_reason=(
            _load_json(output_reason_json, None) if output_reason_json is not None else None
        ),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
        alert_decision_id=row["alert_decision_id"],
    )


def _fee_window_from_row(row: sqlite3.Row) -> FeeWindow:
    return FeeWindow(
        id=row["id"],
        token_address=row["token_address"],
        as_of_time=_parse_datetime(row["as_of_time"]),
        window_seconds=row["window_seconds"],
        pool_address=row["pool_address"],
        first_event_time=_parse_datetime(row["first_event_time"]),
        last_event_time=_parse_datetime(row["last_event_time"]),
        event_count=row["event_count"],
        buy_count=row["buy_count"],
        sell_count=row["sell_count"],
        total_fee_sol=row["total_fee_sol"],
        lp_fee_sol=row["lp_fee_sol"],
        protocol_fee_sol=row["protocol_fee_sol"],
        creator_fee_sol=row["creator_fee_sol"],
        creator_fee_share=row["creator_fee_share"],
        lp_fee_share=row["lp_fee_share"],
        protocol_fee_share=row["protocol_fee_share"],
        avg_fee_per_event_sol=row["avg_fee_per_event_sol"],
        median_fee_per_event_sol=row["median_fee_per_event_sol"],
        max_fee_event_sol=row["max_fee_event_sol"],
        events_per_min=row["events_per_min"],
        fees_per_min_sol=row["fees_per_min_sol"],
        buy_sell_count_ratio=row["buy_sell_count_ratio"],
        buy_sell_fee_ratio=row["buy_sell_fee_ratio"],
        source_min_id=row["source_min_id"],
        source_max_id=row["source_max_id"],
        source_row_count=row["source_row_count"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _field_features_from_row(row: sqlite3.Row) -> FieldFeatures:
    return FieldFeatures(
        id=row["id"],
        token_address=row["token_address"],
        as_of_time=_parse_datetime(row["as_of_time"]),
        fee_window_60s_id=row["fee_window_60s_id"],
        fee_window_300s_id=row["fee_window_300s_id"],
        fee_window_900s_id=row["fee_window_900s_id"],
        fee_window_1800s_id=row["fee_window_1800s_id"],
        fee_window_3600s_id=row["fee_window_3600s_id"],
        liquidity_usd=row["liquidity_usd"],
        lp_floor_label=row["lp_floor_label"],
        lp_fragility_score=row["lp_fragility_score"],
        fee_gate_label=row["fee_gate_label"],
        fee_gate_score=row["fee_gate_score"],
        ante_label_5m=row["ante_label_5m"],
        ante_label_20sw=row["ante_label_20sw"],
        ghost_label=row["ghost_label"],
        holder_label=row["holder_label"],
        event_pace_5m=row["event_pace_5m"],
        fee_pace_5m_sol=row["fee_pace_5m_sol"],
        creator_fee_share_5m=row["creator_fee_share_5m"],
        lp_fee_share_5m=row["lp_fee_share_5m"],
        protocol_fee_share_5m=row["protocol_fee_share_5m"],
        buy_sell_ratio_5m=row["buy_sell_ratio_5m"],
        event_count_5m=row["event_count_5m"],
        raw_snapshot=_load_json(row["raw_snapshot_json"], {}),
        feature_version=row["feature_version"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _raw_pumpswap_event_from_row(row: sqlite3.Row) -> RawPumpSwapEvent:
    return RawPumpSwapEvent(
        id=row["id"],
        observed_at=_parse_datetime(row["observed_at"]),
        source=row["source"],
        subscription=row["subscription"],
        signature=row["signature"],
        slot=row["slot"],
        block_time=_parse_datetime(row["block_time"]),
        transaction_index=row["transaction_index"],
        instruction_index=row["instruction_index"],
        inner_instruction_index=row["inner_instruction_index"],
        event_index=row["event_index"],
        dedupe_key=row["dedupe_key"],
        pool_address=row["pool_address"],
        token_address=row["token_address"],
        base_mint=row["base_mint"],
        quote_mint=row["quote_mint"],
        user_address=row["user_address"],
        event_type=row["event_type"],
        base_amount_raw=row["base_amount_raw"],
        quote_amount_raw=row["quote_amount_raw"],
        base_amount_token=row["base_amount_token"],
        quote_amount_sol=row["quote_amount_sol"],
        price_sol=row["price_sol"],
        price_usd=row["price_usd"],
        mcap=row["mcap"],
        lp_fee_sol=row["lp_fee_sol"],
        protocol_fee_sol=row["protocol_fee_sol"],
        creator_fee_sol=row["creator_fee_sol"],
        total_fee_sol=row["total_fee_sol"],
        fee_unit=row["fee_unit"],
        fee_invariant_ok=_bool_value(row["fee_invariant_ok"]),
        decoder_name=row["decoder_name"],
        decoder_version=row["decoder_version"],
        raw_payload=_load_json(row["raw_payload_json"], {}),
        created_at=_parse_datetime(row["created_at"]),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _price_curve_point_from_row(row: sqlite3.Row) -> PriceCurvePoint:
    return PriceCurvePoint(
        id=row["id"],
        token_address=row["token_address"],
        anchor_type=row["anchor_type"],
        anchor_key=row["anchor_key"],
        anchor_time=_parse_datetime(row["anchor_time"]),
        anchor_ref_id=row["anchor_ref_id"],
        bucket_seconds=row["bucket_seconds"],
        bucket_start_time=_parse_datetime(row["bucket_start_time"]),
        bucket_end_time=_parse_datetime(row["bucket_end_time"]),
        observed_at=_parse_datetime(row["observed_at"]),
        price_observation_id=row["price_observation_id"],
        price=row["price"],
        mcap=row["mcap"],
        liquidity_usd=row["liquidity_usd"],
        normalized_price=row["normalized_price"],
        normalized_mcap=row["normalized_mcap"],
        return_from_anchor=row["return_from_anchor"],
        return_from_migration=row["return_from_migration"],
        drawdown_from_ath=row["drawdown_from_ath"],
        age_since_migration_s=row["age_since_migration_s"],
        time_since_ath_s=row["time_since_ath_s"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
        created_at=_parse_datetime(row["created_at"]),
    )


def _score_features_from_row(row: sqlite3.Row) -> ScoreFeatures:
    return ScoreFeatures(
        token_address=row["token_address"],
        as_of_time=_parse_datetime(row["as_of_time"]),
        score_version=row["score_version"],
        field_score=row["field_score"],
        setup_score=row["setup_score"],
        clock_score=row["clock_score"],
        risk_score=row["risk_score"],
        composite_score=row["composite_score"],
        pump_multiple=row["pump_multiple"],
        drawdown_from_ath=row["drawdown_from_ath"],
        ath_quality_score=row["ath_quality_score"],
        price_freshness_score=row["price_freshness_score"],
        liquidity_quality_score=row["liquidity_quality_score"],
        fee_quality_score=row["fee_quality_score"],
        participation_quality_score=row["participation_quality_score"],
        organic_risk_score=row["organic_risk_score"],
        scam_risk_score=row["scam_risk_score"],
        dip_speed_score=row["dip_speed_score"],
        support_reclaim_quality_score=row["support_reclaim_quality_score"],
        components=_load_json(row["components_json"], {}),
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _clock_features_from_row(row: sqlite3.Row) -> ClockFeatures:
    return ClockFeatures(
        id=row["id"],
        token_address=row["token_address"],
        as_of_time=_parse_datetime(row["as_of_time"]),
        migration_time=_parse_datetime(row["migration_time"]),
        age_since_migration_s=row["age_since_migration_s"],
        ath_time=_parse_datetime(row["ath_time"]),
        time_to_ath_s=row["time_to_ath_s"],
        time_since_ath_s=row["time_since_ath_s"],
        tier_1_time=_parse_datetime(row["tier_1_time"]),
        tier_2_time=_parse_datetime(row["tier_2_time"]),
        tier_3_time=_parse_datetime(row["tier_3_time"]),
        time_ath_to_t1_s=row["time_ath_to_t1_s"],
        time_ath_to_t2_s=row["time_ath_to_t2_s"],
        time_ath_to_t3_s=row["time_ath_to_t3_s"],
        time_t1_to_t2_s=row["time_t1_to_t2_s"],
        time_t2_to_t3_s=row["time_t2_to_t3_s"],
        dip_velocity_pct_per_min=row["dip_velocity_pct_per_min"],
        recovery_velocity_pct_per_min=row["recovery_velocity_pct_per_min"],
        last_fee_event_time=_parse_datetime(row["last_fee_event_time"]),
        last_buy_time=_parse_datetime(row["last_buy_time"]),
        last_sell_time=_parse_datetime(row["last_sell_time"]),
        time_since_last_fee_event_s=row["time_since_last_fee_event_s"],
        time_since_last_buy_s=row["time_since_last_buy_s"],
        time_since_last_sell_s=row["time_since_last_sell_s"],
        sequence_phase=row["sequence_phase"],
        phase_reason=row["phase_reason"],
        feature_version=row["feature_version"],
        data_status=_enum_value(DataStatus, row["data_status"], DataStatus.MISSING),
        missing_reasons=_load_json(row["missing_reasons_json"], []),
    )


def _outcome_window_from_row(row: sqlite3.Row) -> OutcomeWindow:
    return OutcomeWindow(
        id=row["id"],
        alert_decision_id=row["alert_decision_id"],
        token_address=row["token_address"],
        window_seconds=row["window_seconds"],
        window_start_time=_parse_datetime(row["window_start_time"]),
        window_end_time=_parse_datetime(row["window_end_time"]),
        alert_price=row["alert_price"],
        alert_mcap=row["alert_mcap"],
        max_price=row["max_price"],
        max_mcap=row["max_mcap"],
        max_observation_time=_parse_datetime(row["max_observation_time"]),
        min_price=row["min_price"],
        min_mcap=row["min_mcap"],
        min_observation_time=_parse_datetime(row["min_observation_time"]),
        max_return_multiple=row["max_return_multiple"],
        max_return_pct=row["max_return_pct"],
        min_return_multiple=row["min_return_multiple"],
        min_return_pct=row["min_return_pct"],
        max_drawdown_from_peak_pct=row["max_drawdown_from_peak_pct"],
        time_to_max_return_seconds=row["time_to_max_return_seconds"],
        hit_2x=_bool_value(row["hit_2x"]),
        hit_3x=_bool_value(row["hit_3x"]),
        hit_5x=_bool_value(row["hit_5x"]),
        observations_count=row["observations_count"],
        first_observation_time=_parse_datetime(row["first_observation_time"]),
        last_observation_time=_parse_datetime(row["last_observation_time"]),
        data_status=_enum_value(
            OutcomeWindowStatus,
            row["data_status"],
            OutcomeWindowStatus.NO_PRICE_DATA,
        ),
    )


def _dispatch_event_from_row(row: sqlite3.Row) -> DispatchEvent:
    attempted_at = _parse_datetime(row["attempted_at"])
    assert attempted_at is not None  # NOT NULL in schema
    return DispatchEvent(
        id=row["id"],
        alert_decision_id=row["alert_decision_id"],
        dispatch_run_id=row["dispatch_run_id"],
        target=row["target"],
        status=row["status"],
        decision_type=row["decision_type"],
        severity=row["severity"],
        tier_label=row["tier_label"],
        attempted_at=attempted_at,
        completed_at=_parse_datetime(row["completed_at"]),
        payload_ref=row["payload_ref"],
        error_message=row["error_message"],
    )


def _decision_score_features_from_row(
    row: sqlite3.Row,
) -> DecisionScoreFeatures:
    return DecisionScoreFeatures(
        id=row["id"],
        alert_decision_id=row["alert_decision_id"],
        feature_version=row["feature_version"],
        schema_version=row["schema_version"],
        token_address=row["token_address"],
        token_symbol=row["token_symbol"],
        decision_time=_parse_datetime(row["decision_time"]),
        as_of_time=_parse_datetime(row["as_of_time"]),
        tier_index=row["tier_index"],
        tier_name=row["tier_name"],
        alert_price=row["alert_price"],
        alert_market_cap=row["alert_market_cap"],
        ath_price=row["ath_price"],
        ath_market_cap=row["ath_market_cap"],
        ath_time=_parse_datetime(row["ath_time"]),
        migration_price=row["migration_price"],
        migration_market_cap=row["migration_market_cap"],
        migration_time=_parse_datetime(row["migration_time"]),
        drop_from_ath=row["drop_from_ath"],
        multiple_from_migration=row["multiple_from_migration"],
        time_since_migration_seconds=row["time_since_migration_seconds"],
        time_since_ath_seconds=row["time_since_ath_seconds"],
        time_from_migration_to_ath_seconds=row[
            "time_from_migration_to_ath_seconds"
        ],
        liquidity_usd=row["liquidity_usd"],
        event_count_5m=row["event_count_5m"],
        total_fee_5m=row["total_fee_5m"],
        lp_fee_5m=row["lp_fee_5m"],
        protocol_fee_5m=row["protocol_fee_5m"],
        creator_fee_5m=row["creator_fee_5m"],
        creator_fee_share_5m=row["creator_fee_share_5m"],
        lp_fee_share_5m=row["lp_fee_share_5m"],
        protocol_fee_share_5m=row["protocol_fee_share_5m"],
        fee_per_event_5m=row["fee_per_event_5m"],
        events_per_minute_5m=row["events_per_minute_5m"],
        fees_per_minute_5m=row["fees_per_minute_5m"],
        source_snapshot=_load_json(row["source_snapshot_json"], {}),
        created_at=_parse_datetime(row["created_at"]),
        data_status=_enum_value(
            DataStatus, row["data_status"], DataStatus.MISSING
        ),
        missing_reasons=tuple(_load_json(row["missing_reasons_json"], [])),
    )
