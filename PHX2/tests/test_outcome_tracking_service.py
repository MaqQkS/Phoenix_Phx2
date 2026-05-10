"""Integration tests for OutcomeTrackingService.

These tests use the real SQLite repositories against a temp DB. They cover
the service's contract end-to-end: maturation, idempotency, status semantics,
boundary correctness, and the safety guards on the repository write path.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage9_schema
from PHX2.db.repositories import (
    AlertDecisionRepository,
    OutcomeWindowRepository,
    PriceObservationRepository,
    repository_registry,
)
from PHX2.models import (
    ATHConfidence,
    ATHStatus,
    AlertDecision,
    DataStatus,
    DecisionReason,
    DecisionType,
    OutcomeWindow,
    OutcomeWindowStatus,
    PriceObservation,
)
from PHX2.services.outcome_tracking_service import OutcomeTrackingService


TOKEN = "tokenA"
EVAL_TIME = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"outcome_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context(
    *,
    clock_value: Optional[datetime] = None,
    window_seconds: Optional[Tuple[int, ...]] = None,
) -> Iterator[Tuple[PHX2Connection, OutcomeTrackingService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage9_schema(connection)
        registry = repository_registry(connection)
        clock = (lambda: clock_value) if clock_value is not None else None
        kwargs = {}
        if clock is not None:
            kwargs["clock"] = clock
        if window_seconds is not None:
            kwargs["window_seconds"] = window_seconds
        service = OutcomeTrackingService(
            alert_decision_repository=registry.alert_decisions,
            price_observation_repository=registry.price_observations,
            outcome_window_repository=registry.outcome_windows,
            **kwargs,
        )
        yield connection, service
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _insert_would_alert_decision(
    connection: PHX2Connection,
    *,
    token_address: str = TOKEN,
    evaluated_at: datetime = EVAL_TIME,
    current_price: Optional[float] = 1.0,
    current_mcap: Optional[float] = 100.0,
    decision_type: DecisionType = DecisionType.WOULD_ALERT,
    would_alert: bool = True,
) -> int:
    """Insert a minimal alert_decisions row matching the Stage 9 contract.

    Bypasses AlertEligibilityEngine to keep this fixture independent of Stage 7.
    Returns the row id.
    """

    repo = AlertDecisionRepository(connection)
    decision = AlertDecision(
        token_address=token_address,
        evaluated_at=evaluated_at,
        decision_type=decision_type,
        primary_reason=(
            DecisionReason.WOULD_ALERT
            if decision_type == DecisionType.WOULD_ALERT
            else DecisionReason.MIN_PUMP_NOT_MET
        ),
        reasons=[
            DecisionReason.WOULD_ALERT
            if decision_type == DecisionType.WOULD_ALERT
            else DecisionReason.MIN_PUMP_NOT_MET
        ],
        would_alert=would_alert,
        skipped=not would_alert,
        ath_status=ATHStatus.CONFIRMED,
        ath_confidence=ATHConfidence.HIGH,
        current_price=current_price,
        current_mcap=current_mcap,
        policy_version="policy_v0_test",
        data_status=DataStatus.OK,
    )
    return repo.insert(decision)


def _insert_price_observation(
    connection: PHX2Connection,
    *,
    token_address: str,
    observed_at: datetime,
    price: float,
    mcap: Optional[float] = None,
) -> int:
    repo = PriceObservationRepository(connection)
    return repo.insert(
        PriceObservation(
            token_address=token_address,
            observed_at=observed_at,
            source="test",
            price=price,
            mcap=mcap,
            data_status=DataStatus.OK,
        )
    )


# --------------------------------------------------------------------------
# Decision-level coverage
# --------------------------------------------------------------------------


def test_decision_with_rich_data_writes_six_complete_rows():
    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        # A few observations spread across 24 hours so all six windows have
        # data.
        for offset_seconds, price in [
            (60, 1.5),
            (600, 2.5),
            (1500, 3.0),
            (3000, 4.0),
            (10_000, 5.5),
            (40_000, 2.0),
            (80_000, 1.2),
        ]:
            _insert_price_observation(
                connection,
                token_address=TOKEN,
                observed_at=EVAL_TIME + timedelta(seconds=offset_seconds),
                price=price,
                mcap=price * 100.0,
            )

        result = service.track_for_decision(decision_id)
        assert result.error is None
        assert len(result.window_results) == 6

        outcomes = service.outcome_windows.get_all_for_decision(decision_id)
        assert len(outcomes) == 6
        for outcome in outcomes:
            assert outcome.data_status == OutcomeWindowStatus.COMPLETE
            assert outcome.alert_price == 1.0
            assert outcome.observations_count is not None
            assert outcome.observations_count > 0
            assert outcome.max_price is not None
            assert outcome.max_return_multiple is not None
            assert outcome.hit_2x is not None


def test_decision_with_no_price_observations_writes_six_no_price_data_rows():
    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert len(outcomes) == 6
        for outcome in outcomes:
            assert outcome.data_status == OutcomeWindowStatus.NO_PRICE_DATA
            assert outcome.observations_count == 0
            assert outcome.max_price is None
            assert outcome.min_price is None
            assert outcome.max_return_multiple is None
            assert outcome.hit_2x is None
            assert outcome.first_observation_time is None
            assert outcome.last_observation_time is None


@pytest.mark.parametrize("invalid_price", [None, 0.0, -1.0])
def test_decision_with_invalid_current_price_writes_six_invalid_rows(invalid_price):
    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        decision_id = _insert_would_alert_decision(
            connection, current_price=invalid_price
        )
        # Drop a price observation in the window — it must be ignored because
        # the alert price itself is invalid.
        _insert_price_observation(
            connection,
            token_address=TOKEN,
            observed_at=EVAL_TIME + timedelta(seconds=120),
            price=2.0,
        )

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert len(outcomes) == 6
        for outcome in outcomes:
            assert outcome.data_status == OutcomeWindowStatus.INVALID_ALERT_PRICE
            assert outcome.observations_count is None  # NULL by spec
            assert outcome.max_price is None
            assert outcome.max_return_multiple is None


def test_observations_in_early_windows_remain_in_later_cumulative_windows():
    # Stage 9 windows are cumulative [evaluated_at, evaluated_at + window_seconds]
    # ranges, NOT disjoint slices. An observation at +1500s is inside every
    # window whose end is >= 1500s — i.e. 30m, 1h, 4h, 24h. So a token whose
    # only observations land in the first 30 minutes still produces COMPLETE
    # rows for all six windows: the 1h/4h/24h windows simply contain those
    # same observations. There is no observation pattern that yields a
    # short-windows-complete / long-windows-empty split under cumulative
    # closed-interval semantics.
    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        for offset_seconds, price in [(60, 1.2), (600, 1.5), (1500, 2.1)]:
            _insert_price_observation(
                connection,
                token_address=TOKEN,
                observed_at=EVAL_TIME + timedelta(seconds=offset_seconds),
                price=price,
            )

        service.track_for_decision(decision_id)
        outcomes = {
            outcome.window_seconds: outcome
            for outcome in service.outcome_windows.get_all_for_decision(decision_id)
        }

        # All six windows COMPLETE because every observation at +60s/+600s/
        # +1500s falls inside the cumulative [start, end] range of every
        # window.
        for window_seconds in (300, 900, 1800, 3600, 14400, 86400):
            assert outcomes[window_seconds].data_status == OutcomeWindowStatus.COMPLETE
            assert outcomes[window_seconds].observations_count is not None
            assert outcomes[window_seconds].observations_count > 0


# --------------------------------------------------------------------------
# Maturation
# --------------------------------------------------------------------------


def test_maturation_t_plus_4m_no_rows_written():
    as_of = EVAL_TIME + timedelta(minutes=4)
    with _service_context(clock_value=as_of) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        result = service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert outcomes == []
        for window_result in result.window_results:
            assert window_result.status == OutcomeWindowStatus.WINDOW_NOT_ELAPSED


def test_maturation_t_plus_5m_exactly_writes_only_5m_row():
    as_of = EVAL_TIME + timedelta(seconds=300)  # exactly the 5m boundary
    with _service_context(clock_value=as_of) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert [o.window_seconds for o in outcomes] == [300]


def test_maturation_t_plus_16m_writes_5m_and_15m_only():
    as_of = EVAL_TIME + timedelta(minutes=16)
    with _service_context(clock_value=as_of) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert sorted(o.window_seconds for o in outcomes) == [300, 900]


def test_backfill_decision_25h_ago_writes_all_six_rows_in_one_call():
    as_of = EVAL_TIME + timedelta(hours=25)
    with _service_context(clock_value=as_of) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)

        assert sorted(o.window_seconds for o in outcomes) == [
            300,
            900,
            1800,
            3600,
            14400,
            86400,
        ]


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


def test_idempotency_run_twice_zero_new_rows_second_pass_all_already_recorded():
    as_of = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=as_of) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)

        service.track_for_decision(decision_id)
        first_pass = service.outcome_windows.get_all_for_decision(decision_id)
        first_ids = sorted(o.id for o in first_pass)

        result = service.track_for_decision(decision_id)
        second_pass = service.outcome_windows.get_all_for_decision(decision_id)
        second_ids = sorted(o.id for o in second_pass)

        assert first_ids == second_ids
        assert len(second_pass) == 6
        for window_result in result.window_results:
            assert window_result.status == OutcomeWindowStatus.ALREADY_RECORDED


# --------------------------------------------------------------------------
# track_pending
# --------------------------------------------------------------------------


def test_track_pending_skips_skip_block_and_error_decisions():
    as_of = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=as_of) as (connection, service):
        # Three decisions: one WOULD_ALERT, one SKIP, one BLOCK.
        wa_id = _insert_would_alert_decision(connection, current_price=1.0)
        skip_id = _insert_would_alert_decision(
            connection,
            evaluated_at=EVAL_TIME + timedelta(seconds=1),
            decision_type=DecisionType.SKIP,
            would_alert=False,
            current_price=1.0,
        )
        block_id = _insert_would_alert_decision(
            connection,
            evaluated_at=EVAL_TIME + timedelta(seconds=2),
            decision_type=DecisionType.BLOCK,
            would_alert=False,
            current_price=1.0,
        )

        result = service.track_pending()

        assert result.decisions_processed == 1  # only the WOULD_ALERT
        assert len(service.outcome_windows.get_all_for_decision(wa_id)) == 6
        assert service.outcome_windows.get_all_for_decision(skip_id) == []
        assert service.outcome_windows.get_all_for_decision(block_id) == []


def test_track_pending_skips_error_decisions():
    # Regression: Stage 9 must never produce outcome_windows rows for
    # decision_type='error' rows, even though the existing SKIP/BLOCK test
    # names the case in passing. Layered: SQL filter excludes them at read,
    # service-side decision_type guard rejects them at write.
    as_of = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=as_of) as (connection, service):
        wa_id = _insert_would_alert_decision(connection, current_price=1.0)
        error_id = _insert_would_alert_decision(
            connection,
            evaluated_at=EVAL_TIME + timedelta(seconds=1),
            decision_type=DecisionType.ERROR,
            would_alert=False,
            current_price=1.0,
        )

        result = service.track_pending()

        assert result.decisions_processed == 1  # only the WOULD_ALERT
        assert len(service.outcome_windows.get_all_for_decision(wa_id)) == 6
        assert service.outcome_windows.get_all_for_decision(error_id) == []


def test_track_pending_processes_decisions_oldest_first():
    as_of = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=as_of) as (connection, service):
        # Three WOULD_ALERTs across two tokens, evaluated at different times.
        first = _insert_would_alert_decision(
            connection,
            token_address="t1",
            evaluated_at=EVAL_TIME,
            current_price=1.0,
        )
        second = _insert_would_alert_decision(
            connection,
            token_address="t2",
            evaluated_at=EVAL_TIME + timedelta(minutes=10),
            current_price=1.0,
        )
        third = _insert_would_alert_decision(
            connection,
            token_address="t3",
            evaluated_at=EVAL_TIME + timedelta(minutes=20),
            current_price=1.0,
        )

        result = service.track_pending()

        assert result.decisions_processed == 3
        ids_in_order = [r.alert_decision_id for r in result.decision_results]
        assert ids_in_order == [first, second, third]


# --------------------------------------------------------------------------
# Boundary semantics — closed interval [start, end]
# --------------------------------------------------------------------------


def test_observation_at_window_start_included():
    as_of = EVAL_TIME + timedelta(seconds=300)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        _insert_price_observation(
            connection,
            token_address=TOKEN,
            observed_at=EVAL_TIME,  # exactly at window_start_time
            price=2.0,
        )

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)
        assert outcomes[0].data_status == OutcomeWindowStatus.COMPLETE
        assert outcomes[0].observations_count == 1


def test_observation_at_window_end_included():
    as_of = EVAL_TIME + timedelta(seconds=305)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        _insert_price_observation(
            connection,
            token_address=TOKEN,
            observed_at=EVAL_TIME + timedelta(seconds=300),  # exactly at end
            price=2.0,
        )

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)
        assert outcomes[0].observations_count == 1


def test_observation_at_start_minus_1us_excluded():
    as_of = EVAL_TIME + timedelta(seconds=305)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        _insert_price_observation(
            connection,
            token_address=TOKEN,
            observed_at=EVAL_TIME - timedelta(microseconds=1),
            price=2.0,
        )

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)
        assert outcomes[0].data_status == OutcomeWindowStatus.NO_PRICE_DATA
        assert outcomes[0].observations_count == 0


def test_observation_at_end_plus_1us_excluded():
    as_of = EVAL_TIME + timedelta(seconds=305)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        _insert_price_observation(
            connection,
            token_address=TOKEN,
            observed_at=EVAL_TIME + timedelta(seconds=300, microseconds=1),
            price=2.0,
        )

        service.track_for_decision(decision_id)
        outcomes = service.outcome_windows.get_all_for_decision(decision_id)
        assert outcomes[0].data_status == OutcomeWindowStatus.NO_PRICE_DATA


# --------------------------------------------------------------------------
# Repository write-path guards
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "service_only_status",
    [
        OutcomeWindowStatus.PARTIAL,
        OutcomeWindowStatus.WINDOW_NOT_ELAPSED,
        OutcomeWindowStatus.ALREADY_RECORDED,
        OutcomeWindowStatus.ERROR,
    ],
)
def test_repository_rejects_non_persistable_status(service_only_status):
    with _service_context() as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        repo = service.outcome_windows
        row = OutcomeWindow(
            alert_decision_id=decision_id,
            token_address=TOKEN,
            window_seconds=300,
            window_start_time=EVAL_TIME,
            window_end_time=EVAL_TIME + timedelta(seconds=300),
            data_status=service_only_status,
        )
        with pytest.raises(ValueError, match="data_status"):
            repo.insert(row)


def test_db_check_constraint_rejects_invalid_status_via_raw_sql():
    with _service_context() as (connection, service):
        _insert_would_alert_decision(connection, current_price=1.0)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO outcome_windows (
                    alert_decision_id, token_address, window_seconds,
                    window_start_time, window_end_time, data_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    TOKEN,
                    300,
                    EVAL_TIME.isoformat(),
                    (EVAL_TIME + timedelta(seconds=300)).isoformat(),
                    "PARTIAL",  # rejected by CHECK constraint
                    EVAL_TIME.isoformat(),
                ),
            )


def test_db_check_constraint_rejects_invalid_window_seconds_via_raw_sql():
    with _service_context() as (connection, service):
        _insert_would_alert_decision(connection, current_price=1.0)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO outcome_windows (
                    alert_decision_id, token_address, window_seconds,
                    window_start_time, window_end_time, data_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    TOKEN,
                    7,  # not in canonical set; rejected by CHECK
                    EVAL_TIME.isoformat(),
                    (EVAL_TIME + timedelta(seconds=7)).isoformat(),
                    "COMPLETE",
                    EVAL_TIME.isoformat(),
                ),
            )


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------


def test_track_for_decision_skips_non_would_alert_with_explicit_error():
    as_of = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=as_of) as (connection, service):
        skip_id = _insert_would_alert_decision(
            connection,
            decision_type=DecisionType.SKIP,
            would_alert=False,
            current_price=1.0,
        )

        result = service.track_for_decision(skip_id)
        assert result.error == "not a would_alert decision"
        assert result.window_results == ()
        assert service.outcome_windows.get_all_for_decision(skip_id) == []


def test_track_for_decision_returns_error_when_decision_id_unknown():
    with _service_context() as (_connection, service):
        result = service.track_for_decision(99999)
        assert result.error == "alert_decision_not_found"
        assert result.window_results == ()


def test_engine_produces_would_alert_then_stage9_runs_end_to_end():
    """E2E: AlertEligibilityEngine produces a WOULD_ALERT, the clock advances,
    OutcomeTrackingService runs, outcome_windows is populated. dispatch_events
    must not be touched by Stage 9.
    """

    from PHX2.services.alert_eligibility_engine import AlertEligibilityEngine
    from PHX2.models import (
        ATHEvent,
        ATHEventType,
        PriceObservation,
        TokenState,
    )
    from PHX2.db.repositories import (
        ATHRepository,
        PriceObservationRepository,
        TokenSequenceRepository,
    )

    eval_time = EVAL_TIME
    advanced = eval_time + timedelta(seconds=305)
    obs_time = eval_time - timedelta(seconds=60)

    with _service_context(
        clock_value=advanced, window_seconds=(300,)
    ) as (connection, service):
        # Build a token state that would produce a WOULD_ALERT.
        TokenSequenceRepository(connection).upsert(
            TokenState(
                token_address=TOKEN,
                migration_time=eval_time - timedelta(hours=1),
                migration_source="test",
                migration_price=10.0,
                migration_mcap=10_000.0,
                current_price=40.0,
                current_mcap=40_000.0,
                last_price_update=obs_time,
                data_status=DataStatus.OK,
            )
        )
        PriceObservationRepository(connection).insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=obs_time,
                source="test",
                price=40.0,
                mcap=40_000.0,
                data_status=DataStatus.OK,
            )
        )
        ath_repo = ATHRepository(connection)
        ath_repo.insert_event(
            ATHEvent(
                token_address=TOKEN,
                event_time=eval_time - timedelta(minutes=30),
                candidate_price=100.0,
                candidate_mcap=100_000.0,
                candidate_source="test",
                new_ath_price=100.0,
                new_ath_mcap=100_000.0,
                status_before=ATHStatus.UNKNOWN,
                status_after=ATHStatus.CONFIRMED,
                confidence_before=ATHConfidence.UNKNOWN,
                confidence_after=ATHConfidence.HIGH,
                mutation_type=ATHEventType.ATH_RAISED,
                accepted=True,
                data_status=DataStatus.OK,
            )
        )

        from PHX2.db.repositories import (
            ClockFeatureRepository,
            FieldFeatureRepository,
        )

        engine = AlertEligibilityEngine(
            token_sequence=TokenSequenceRepository(connection),
            price_observations=PriceObservationRepository(connection),
            ath=ath_repo,
            field_features=FieldFeatureRepository(connection),
            clock_features=ClockFeatureRepository(connection),
            alert_decisions=AlertDecisionRepository(connection),
            current_time_provider=lambda: eval_time,
        )
        decision = engine.evaluate_token(TOKEN, as_of_time=eval_time)
        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.current_price == 40.0

        # Stage 9 picks up the engine's row via track_pending.
        # Snapshot full dispatch_events row content (not just count) so we
        # catch in-place modifications in addition to inserts/deletes.
        before_dispatch = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM dispatch_events ORDER BY id"
            ).fetchall()
        ]

        result = service.track_pending()
        assert result.decisions_processed == 1
        assert result.rows_inserted == 1

        outcomes = connection.execute(
            "SELECT * FROM outcome_windows"
        ).fetchall()
        assert len(outcomes) == 1
        assert outcomes[0]["data_status"] == "NO_PRICE_DATA"
        assert outcomes[0]["window_seconds"] == 300

        # dispatch_events must remain untouched — Stage 9 has no business
        # writing to it. Deep equality on every column catches both row-count
        # changes and in-place mutations.
        after_dispatch = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM dispatch_events ORDER BY id"
            ).fetchall()
        ]
        assert after_dispatch == before_dispatch


def test_unique_constraint_race_treated_as_already_recorded():
    """When insert hits the unique constraint (because a concurrent caller
    inserted the same row in between get-by-decision and insert), the
    service must surface ALREADY_RECORDED and not raise.
    """

    as_of = EVAL_TIME + timedelta(seconds=305)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        # Simulate the race: pre-insert a row directly via the repository so
        # the unique index fires when the service attempts its insert. We do
        # this by patching get_by_decision_and_window to lie about absence,
        # forcing the service to try inserting.
        repo = service.outcome_windows
        repo.insert(
            OutcomeWindow(
                alert_decision_id=decision_id,
                token_address=TOKEN,
                window_seconds=300,
                window_start_time=EVAL_TIME,
                window_end_time=EVAL_TIME + timedelta(seconds=300),
                alert_price=1.0,
                observations_count=0,
                data_status=OutcomeWindowStatus.NO_PRICE_DATA,
            )
        )
        original_get = repo.get_by_decision_and_window

        call_count = {"n": 0}

        def lying_get(alert_decision_id_, window_seconds_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # first call: pretend the row does not exist
            return original_get(alert_decision_id_, window_seconds_)

        repo.get_by_decision_and_window = lying_get  # type: ignore[assignment]
        try:
            result = service.track_for_decision(decision_id)
        finally:
            repo.get_by_decision_and_window = original_get  # type: ignore[assignment]

        assert len(result.window_results) == 1
        assert result.window_results[0].status == OutcomeWindowStatus.ALREADY_RECORDED
        assert result.window_results[0].outcome_window_id is not None


# --------------------------------------------------------------------------
# Per-window exception handling
# --------------------------------------------------------------------------


def test_non_integrity_error_in_one_window_yields_error_status_others_continue():
    """A non-IntegrityError raised by insert (e.g. a stub RuntimeError
    standing in for an unexpected DB error or logic bug) must not be
    silently turned into WINDOW_NOT_ELAPSED. The failed window surfaces as
    ERROR (service-only, never persisted) and the remaining windows in the
    same decision continue processing.
    """

    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        repo = service.outcome_windows
        original_insert = repo.insert

        def insert_raising_on_900(row):
            if row.window_seconds == 900:
                raise RuntimeError("simulated unexpected failure")
            return original_insert(row)

        repo.insert = insert_raising_on_900  # type: ignore[assignment]
        try:
            result = service.track_for_decision(decision_id)
        finally:
            repo.insert = original_insert  # type: ignore[assignment]

        statuses = {wr.window_seconds: wr.status for wr in result.window_results}
        assert statuses[900] == OutcomeWindowStatus.ERROR
        # The 900s window was not retried and produced no DB row.
        rows_900 = [
            outcome
            for outcome in service.outcome_windows.get_all_for_decision(decision_id)
            if outcome.window_seconds == 900
        ]
        assert rows_900 == []
        # The other five windows succeeded and persisted.
        for window_seconds in (300, 1800, 3600, 14400, 86400):
            assert statuses[window_seconds] == OutcomeWindowStatus.NO_PRICE_DATA
        persisted = service.outcome_windows.get_all_for_decision(decision_id)
        assert len(persisted) == 5

        # The ERROR result carries the exception class name and message in
        # ``reason`` so operators can distinguish real failures from skips.
        error_result = next(
            wr for wr in result.window_results if wr.status == OutcomeWindowStatus.ERROR
        )
        assert error_result.reason is not None
        assert "RuntimeError" in error_result.reason
        assert "simulated unexpected failure" in error_result.reason


def test_integrity_error_race_still_resolves_to_already_recorded_after_narrowing():
    """Regression: narrowing the per-window exception mapping must not break
    the unique-constraint race path. The inner ``_insert_or_already_recorded``
    handler still catches ``sqlite3.IntegrityError`` and resolves the race
    to ALREADY_RECORDED before the outer handler ever sees the exception.
    """

    as_of = EVAL_TIME + timedelta(seconds=305)
    with _service_context(
        clock_value=as_of, window_seconds=(300,)
    ) as (connection, service):
        decision_id = _insert_would_alert_decision(connection, current_price=1.0)
        repo = service.outcome_windows
        repo.insert(
            OutcomeWindow(
                alert_decision_id=decision_id,
                token_address=TOKEN,
                window_seconds=300,
                window_start_time=EVAL_TIME,
                window_end_time=EVAL_TIME + timedelta(seconds=300),
                alert_price=1.0,
                observations_count=0,
                data_status=OutcomeWindowStatus.NO_PRICE_DATA,
            )
        )
        original_get = repo.get_by_decision_and_window
        call_count = {"n": 0}

        def lying_get(alert_decision_id_, window_seconds_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return original_get(alert_decision_id_, window_seconds_)

        repo.get_by_decision_and_window = lying_get  # type: ignore[assignment]
        try:
            result = service.track_for_decision(decision_id)
        finally:
            repo.get_by_decision_and_window = original_get  # type: ignore[assignment]

        # Race resolves cleanly via the inner handler — never propagates to
        # the outer ERROR mapping.
        assert len(result.window_results) == 1
        assert result.window_results[0].status == OutcomeWindowStatus.ALREADY_RECORDED
        assert result.window_results[0].status != OutcomeWindowStatus.ERROR


def test_track_pending_continues_batch_when_one_decision_has_an_errored_window():
    """An exception during one window of one decision must not abort the
    batch. Other decisions in the same ``track_pending`` call continue, and
    the per-window failure is reflected in ``rows_errored`` rather than
    silently absorbed into ``rows_skipped_window_not_elapsed``.
    """

    far_future = EVAL_TIME + timedelta(days=2)
    with _service_context(clock_value=far_future) as (connection, service):
        first_id = _insert_would_alert_decision(
            connection,
            token_address="t1",
            evaluated_at=EVAL_TIME,
            current_price=1.0,
        )
        second_id = _insert_would_alert_decision(
            connection,
            token_address="t2",
            evaluated_at=EVAL_TIME + timedelta(seconds=1),
            current_price=1.0,
        )

        repo = service.outcome_windows
        original_insert = repo.insert
        triggered = {"done": False}

        def insert_raising_once_on_first_decision(row):
            # Fail exactly once, on the first decision's 900s window. Every
            # other call (including subsequent windows on the first decision
            # and all windows on the second decision) goes through normally.
            if (
                not triggered["done"]
                and row.alert_decision_id == first_id
                and row.window_seconds == 900
            ):
                triggered["done"] = True
                raise RuntimeError("simulated unexpected failure")
            return original_insert(row)

        repo.insert = insert_raising_once_on_first_decision  # type: ignore[assignment]
        try:
            result = service.track_pending()
        finally:
            repo.insert = original_insert  # type: ignore[assignment]

        # Both decisions ran to completion.
        assert result.decisions_processed == 2
        # 6 windows × 2 decisions = 12 attempts; one window errored, eleven
        # NO_PRICE_DATA rows persisted.
        assert result.rows_inserted == 11
        assert result.rows_errored == 1
        assert result.rows_skipped_window_not_elapsed == 0

        # Per-decision view: first decision has one errored window and five
        # persisted; second decision has all six persisted.
        first_persisted = service.outcome_windows.get_all_for_decision(first_id)
        second_persisted = service.outcome_windows.get_all_for_decision(second_id)
        assert len(first_persisted) == 5
        assert len(second_persisted) == 6
        assert all(o.window_seconds != 900 for o in first_persisted)
