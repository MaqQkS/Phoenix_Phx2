"""End-to-end test: assemble -> render -> format on a real AlertDecision."""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import repository_registry
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    DataStatus,
    PriceObservation,
    TokenSequenceState,
)
from PHX2.renderers import (
    DRY_RUN_BANNER,
    AlertRenderer,
    RenderingContextAssembler,
)
from PHX2.renderers.adapters import PlainTextAdapter
from PHX2.services.alert_eligibility_engine import (
    AlertEligibilityEngine,
    DEFAULT_ALERT_POLICY,
)


TOKEN = "tokenE2E"
EVAL_TIME = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)
MIG_TIME = EVAL_TIME - timedelta(hours=1)
ATH_TIME = MIG_TIME + timedelta(minutes=10)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"e2e_pipeline_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _engine_context() -> Iterator[tuple]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        registry = repository_registry(connection)
        yield connection, registry
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def test_full_pipeline_assemble_render_format_real_decision():
    with _engine_context() as (_, registry):
        registry.token_sequence.upsert(
            TokenSequenceState(
                token_address=TOKEN,
                symbol="E2E",
                migration_time=MIG_TIME,
                migration_price=0.0001,
                migration_mcap=100_000.0,
                current_price=0.0003,
                current_mcap=300_000.0,
                last_price_update=EVAL_TIME,
                data_status=DataStatus.OK,
            )
        )
        price_id = registry.price_observations.insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=EVAL_TIME - timedelta(seconds=30),
                source="pumpswap_event",
                price=0.0003,
                mcap=300_000.0,
                liquidity_usd=80_000.0,
                age_seconds=30.0,
                data_status=DataStatus.OK,
            )
        )
        ath_event_id = registry.ath.insert_event(
            ATHEvent(
                token_address=TOKEN,
                event_time=ATH_TIME,
                price_observation_id=price_id,
                candidate_price=0.0010,
                candidate_mcap=1_000_000.0,
                candidate_source="pumpswap_event",
                new_ath_price=0.0010,
                new_ath_mcap=1_000_000.0,
                status_after=ATHStatus.CONFIRMED,
                confidence_after=ATHConfidence.HIGH,
                mutation_type=ATHEventType.ATH_RAISED,
                accepted=True,
                data_status=DataStatus.OK,
            )
        )
        registry.ath.upsert_state(
            ATHState(
                token_address=TOKEN,
                ath_price=0.0010,
                ath_mcap=1_000_000.0,
                ath_time=ATH_TIME,
                ath_status=ATHStatus.CONFIRMED,
                ath_confidence=ATHConfidence.HIGH,
                ath_source="pumpswap_event",
                last_event_id=ath_event_id,
                data_status=DataStatus.OK,
            )
        )

        engine = AlertEligibilityEngine(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            alert_decisions=registry.alert_decisions,
            policy=DEFAULT_ALERT_POLICY,
            current_time_provider=lambda: EVAL_TIME,
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        context = assembler.assemble(decision, EVAL_TIME)
        rendered = AlertRenderer().render(context)
        preview = PlainTextAdapter().format(rendered)

        # The banner appears exactly twice: top and bottom.
        assert preview.count(DRY_RUN_BANNER) == 2
        # Token identity always present.
        assert TOKEN in preview
        # The decision_type's headline survives the round-trip.
        assert decision.decision_type.value.upper() in preview


def test_full_pipeline_runs_for_skip_decision():
    """A SKIP decision (token not found) still renders a preview with two banners."""

    with _engine_context() as (_, registry):
        engine = AlertEligibilityEngine(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            alert_decisions=registry.alert_decisions,
            current_time_provider=lambda: EVAL_TIME,
        )
        decision = engine.evaluate_token("never-seen-token", as_of_time=EVAL_TIME)

        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        context = assembler.assemble(decision, EVAL_TIME)
        rendered = AlertRenderer().render(context)
        preview = PlainTextAdapter().format(rendered)

        assert preview.count(DRY_RUN_BANNER) == 2
        assert "SKIP" in preview
