"""Tests for RenderingContext and RenderingContextAssembler."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import repository_registry
from PHX2.models import (
    ATHEvent,
    ATHEventType,
    AlertDecision,
    ATHConfidence,
    ATHState,
    ATHStatus,
    ClockFeatures,
    DataStatus,
    DecisionReason,
    DecisionType,
    FieldFeatures,
    PriceObservation,
    TokenSequenceState,
)
from PHX2.renderers.context import RenderingContext, RenderingContextAssembler


TOKEN = "tokenZ"
EVAL_TIME = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"context_assembler_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _populated_db() -> Iterator[tuple]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        registry = repository_registry(connection)

        token_state = TokenSequenceState(
            token_address=TOKEN,
            symbol="ZZZ",
            migration_time=EVAL_TIME,
            migration_price=0.0001,
            migration_mcap=100_000.0,
            current_price=0.0002,
            current_mcap=200_000.0,
            data_status=DataStatus.OK,
        )
        registry.token_sequence.upsert(token_state)

        price_observation = PriceObservation(
            token_address=TOKEN,
            observed_at=EVAL_TIME,
            source="pumpswap_event",
            price=0.0002,
            mcap=200_000.0,
            data_status=DataStatus.OK,
        )
        price_id = registry.price_observations.insert(price_observation)

        ath_event = ATHEvent(
            token_address=TOKEN,
            event_time=EVAL_TIME,
            candidate_price=0.001,
            candidate_mcap=1_000_000.0,
            candidate_source="pumpswap_event",
            new_ath_price=0.001,
            new_ath_mcap=1_000_000.0,
            status_after=ATHStatus.CONFIRMED,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
        ath_event_id = registry.ath.insert_event(ath_event)

        ath_state = ATHState(
            token_address=TOKEN,
            ath_price=0.001,
            ath_mcap=1_000_000.0,
            ath_time=EVAL_TIME,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="pumpswap_event",
            last_event_id=ath_event_id,
            data_status=DataStatus.OK,
        )
        registry.ath.upsert_state(ath_state)

        field_features = FieldFeatures(
            token_address=TOKEN,
            as_of_time=EVAL_TIME,
            liquidity_usd=125_000.0,
            data_status=DataStatus.OK,
        )
        field_id = registry.field_features.upsert(field_features)

        clock_features = ClockFeatures(
            token_address=TOKEN,
            as_of_time=EVAL_TIME,
            migration_time=EVAL_TIME,
            data_status=DataStatus.OK,
        )
        clock_id = registry.clock_features.upsert(clock_features)

        ids = {
            "price_observation_id": price_id,
            "ath_event_id": ath_event_id,
            "field_features_id": field_id,
            "clock_features_id": clock_id,
        }
        yield connection, registry, ids
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _build_decision(
    *,
    price_observation_id=None,
    ath_event_id=None,
    field_features_id=None,
    clock_features_id=None,
) -> AlertDecision:
    return AlertDecision(
        token_address=TOKEN,
        evaluated_at=EVAL_TIME,
        decision_type=DecisionType.WOULD_ALERT,
        primary_reason=DecisionReason.WOULD_ALERT,
        reasons=[DecisionReason.WOULD_ALERT],
        would_alert=True,
        skipped=False,
        price_observation_id=price_observation_id,
        ath_event_id=ath_event_id,
        field_features_id=field_features_id,
        clock_features_id=clock_features_id,
        data_status=DataStatus.OK,
    )


# ---- Happy path: all source rows present -------------------------------


def test_assemble_with_all_source_ids_returns_full_context():
    with _populated_db() as (_, registry, ids):
        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        decision = _build_decision(**ids)

        context = assembler.assemble(decision, EVAL_TIME)

        assert isinstance(context, RenderingContext)
        assert context.alert_decision is decision
        assert context.as_of_time == EVAL_TIME
        assert context.token_sequence_state is not None
        assert context.token_sequence_state.token_address == TOKEN
        assert context.price_observation is not None
        assert context.price_observation.id == ids["price_observation_id"]
        assert context.ath_event is not None
        assert context.ath_event.id == ids["ath_event_id"]
        assert context.ath_state is not None
        assert context.ath_state.token_address == TOKEN
        assert context.field_features is not None
        assert context.field_features.id == ids["field_features_id"]
        assert context.clock_features is not None
        assert context.clock_features.id == ids["clock_features_id"]


# ---- All source ids are None -------------------------------------------


def test_assemble_with_all_none_ids_returns_none_slots():
    with _populated_db() as (_, registry, _):
        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        decision = _build_decision()  # all ids None

        context = assembler.assemble(decision, EVAL_TIME)

        assert context.price_observation is None
        assert context.ath_event is None
        assert context.field_features is None
        assert context.clock_features is None
        # ATH state and token state are looked up by token_address so they're
        # still populated.
        assert context.ath_state is not None
        assert context.token_sequence_state is not None


# ---- Deleted source row --------------------------------------------------


def test_assemble_with_dangling_price_observation_id_returns_none():
    with _populated_db() as (connection, registry, ids):
        # Delete the price observation row but keep the id reference.
        connection.execute(
            "DELETE FROM price_observations WHERE id = ?",
            (ids["price_observation_id"],),
        )
        connection.commit()

        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        decision = _build_decision(**ids)

        context = assembler.assemble(decision, EVAL_TIME)

        assert context.price_observation is None
        # Other slots still populated.
        assert context.ath_event is not None
        assert context.field_features is not None
        assert context.clock_features is not None


def test_assemble_with_dangling_field_features_id_returns_none():
    with _populated_db() as (connection, registry, ids):
        connection.execute(
            "DELETE FROM field_features WHERE id = ?",
            (ids["field_features_id"],),
        )
        connection.commit()

        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        decision = _build_decision(**ids)
        context = assembler.assemble(decision, EVAL_TIME)
        assert context.field_features is None


# ---- Token without state row -------------------------------------------


def test_assemble_with_unknown_token_returns_none_token_and_ath_state():
    with _populated_db() as (_, registry, _):
        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        decision = AlertDecision(
            token_address="unknown-token",
            evaluated_at=EVAL_TIME,
            decision_type=DecisionType.SKIP,
            primary_reason=DecisionReason.TOKEN_NOT_FOUND,
            data_status=DataStatus.MISSING,
        )

        context = assembler.assemble(decision, EVAL_TIME)

        assert context.token_sequence_state is None
        assert context.ath_state is None
