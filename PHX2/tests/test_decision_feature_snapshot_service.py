"""Service tests for DecisionFeatureSnapshotService (Stage 11).

Layer-2 integration tests: per-test temp DB, real
``repository_registry``, real DDL via ``apply_stage11_schema``. Mirrors
the Stage 9 / Stage 10 service test pattern.

Test groups (per Stage 11 Locked Design Spec section 12.3):

* Happy path
* Validation failures (three sentinels)
* Partial upstream (per-upstream isolation)
* Mixed-basis validation
* Idempotency (re-invocation + UNIQUE race)
* As-of-time defaulting (incl. the critical far-future-clock test)
* Read isolation (only decision_score_features changes)
* Versioning (v0 / v1 coexist; constants match section 2.1)
* Source snapshot JSON shape
* Decision-context denormalization freeze

Plus module-level tests for ``derive_data_status`` per spec section 12.4.
"""

import json
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Tuple

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage11_schema
from PHX2.db.repositories import (
    DecisionScoreFeatureRepository,
    repository_registry,
)
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    AlertDecision,
    ClockFeatures,
    DataStatus,
    DecisionFeatureSnapshotResult,
    DecisionReason,
    DecisionType,
    FeeWindow,
    FieldFeatures,
    TokenState,
)
from PHX2.services.decision_feature_snapshot_service import (
    DecisionFeatureSnapshotService,
    ERROR_ALERT_DECISION_NOT_FOUND,
    ERROR_DECISION_TIME_MISSING,
    ERROR_DECISION_TYPE_NOT_WOULD_ALERT,
    derive_data_status,
)


_DECISION_TIME = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
_MIGRATION_TIME = _DECISION_TIME - timedelta(minutes=10)
_ATH_TIME = _DECISION_TIME - timedelta(minutes=2)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"stage11_svc_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _registry_connection() -> Iterator[Tuple[sqlite3.Connection, object]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage11_schema(connection)
        registry = repository_registry(connection)
        yield connection, registry
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _build_service(
    registry,
    *,
    current_time_provider=None,
) -> DecisionFeatureSnapshotService:
    return DecisionFeatureSnapshotService(
        alert_decisions=registry.alert_decisions,
        token_sequence=registry.token_sequence,
        ath=registry.ath,
        field_features=registry.field_features,
        clock_features=registry.clock_features,
        fee_windows=registry.fee_windows,
        decision_score_features=registry.decision_score_features,
        current_time_provider=current_time_provider,
    )


def _seed_token_state(registry, *, symbol="TOK") -> None:
    registry.token_sequence.upsert(
        TokenState(
            token_address="token-aaa",
            symbol=symbol,
            pool_address="pool-aaa",
            migration_time=_MIGRATION_TIME,
            migration_source="grpc",
            migration_price=0.001,
            migration_mcap=1000.0,
            current_price=0.012,
            current_mcap=12000.0,
            last_price_update=_DECISION_TIME,
            sequence_phase="pump",
            current_status="tracking",
            data_status=DataStatus.OK,
        )
    )


def _seed_ath_event(registry) -> int:
    """Seed an ATH_RAISED event so ``get_state_at_or_before`` can
    reconstruct an ATHState. Returns the event id."""

    return registry.ath.insert_event(
        ATHEvent(
            token_address="token-aaa",
            event_time=_ATH_TIME,
            price_observation_id=None,
            candidate_price=0.05,
            candidate_mcap=50000.0,
            candidate_source="dexscreener",
            prior_ath_price=None,
            prior_ath_mcap=None,
            new_ath_price=0.05,
            new_ath_mcap=50000.0,
            status_before=ATHStatus.UNKNOWN,
            status_after=ATHStatus.CONFIRMED,
            confidence_before=ATHConfidence.UNKNOWN,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            reason=None,
            accepted=True,
            data_limited=False,
            input_snapshot={},
            data_status=DataStatus.OK,
            missing_reasons=[],
        )
    )


def _seed_fee_window_300s(
    registry,
    *,
    as_of: datetime = _DECISION_TIME,
    window_seconds: int = 300,
    pool: str = "pool-aaa",
) -> int:
    return registry.fee_windows.insert(
        FeeWindow(
            token_address="token-aaa",
            as_of_time=as_of,
            window_seconds=window_seconds,
            pool_address=pool,
            event_count=20,
            buy_count=12,
            sell_count=8,
            total_fee_sol=0.4,
            lp_fee_sol=0.10,
            protocol_fee_sol=0.10,
            creator_fee_sol=0.20,
            creator_fee_share=0.50,
            lp_fee_share=0.25,
            protocol_fee_share=0.25,
            avg_fee_per_event_sol=0.02,
            median_fee_per_event_sol=0.018,
            max_fee_event_sol=0.05,
            events_per_min=4.0,
            fees_per_min_sol=0.08,
            buy_sell_count_ratio=1.5,
            buy_sell_fee_ratio=1.4,
            data_status=DataStatus.OK,
        )
    )


def _seed_field_features(
    registry,
    *,
    fee_window_300s_id: int,
    fee_window_60s_id=None,
    fee_window_900s_id=None,
    fee_window_1800s_id=None,
    fee_window_3600s_id=None,
    liquidity_usd=None,
) -> int:
    return registry.field_features.insert(
        FieldFeatures(
            token_address="token-aaa",
            as_of_time=_DECISION_TIME,
            fee_window_60s_id=fee_window_60s_id,
            fee_window_300s_id=fee_window_300s_id,
            fee_window_900s_id=fee_window_900s_id,
            fee_window_1800s_id=fee_window_1800s_id,
            fee_window_3600s_id=fee_window_3600s_id,
            liquidity_usd=liquidity_usd,
            event_pace_5m=4.0,
            fee_pace_5m_sol=0.08,
            creator_fee_share_5m=0.50,
            lp_fee_share_5m=0.25,
            protocol_fee_share_5m=0.25,
            buy_sell_ratio_5m=1.5,
            event_count_5m=20,
            raw_snapshot={"source": "test_seed"},
            feature_version="field_v0_placeholder",
            data_status=DataStatus.OK,
        )
    )


def _seed_clock_features(registry) -> int:
    return registry.clock_features.insert(
        ClockFeatures(
            token_address="token-aaa",
            as_of_time=_DECISION_TIME,
            migration_time=_MIGRATION_TIME,
            age_since_migration_s=600.0,
            ath_time=_ATH_TIME,
            time_to_ath_s=480.0,
            time_since_ath_s=120.0,
            last_fee_event_time=_DECISION_TIME - timedelta(seconds=15),
            time_since_last_fee_event_s=15.0,
            sequence_phase="pump",
            phase_reason="seeded for test",
            data_status=DataStatus.OK,
        )
    )


def _decision(
    *,
    token: str = "token-aaa",
    decision_type: DecisionType = DecisionType.WOULD_ALERT,
    evaluated_at=_DECISION_TIME,
    current_price: float = 0.012,
    current_mcap: float = 12000.0,
    drawdown_from_ath: float = -0.76,
    pump_multiple: float = 12.0,
    tier_index: int = 2,
    tier_name: str = "tier_2",
    price_observation_id=None,
    ath_event_id=None,
) -> AlertDecision:
    is_would_alert = decision_type == DecisionType.WOULD_ALERT
    is_skip = decision_type == DecisionType.SKIP
    is_block = decision_type == DecisionType.BLOCK
    return AlertDecision(
        token_address=token,
        evaluated_at=evaluated_at,
        decision_type=decision_type,
        tier_index=tier_index,
        tier_name=tier_name,
        primary_reason=DecisionReason.WOULD_ALERT
        if is_would_alert
        else DecisionReason.TIER_GAP,
        reasons=[],
        would_alert=is_would_alert,
        blocked=is_block,
        skipped=is_skip,
        price_observation_id=price_observation_id,
        ath_event_id=ath_event_id,
        ath_price=0.05,
        ath_status=ATHStatus.CONFIRMED,
        ath_confidence=ATHConfidence.HIGH,
        ath_source="dexscreener",
        price_age_seconds=2.0,
        pump_multiple=pump_multiple,
        drawdown_from_ath=drawdown_from_ath,
        current_price=current_price,
        current_mcap=current_mcap,
        policy_version="policy_v0_placeholder",
        data_status=DataStatus.OK,
    )


def _seed_full_happy_path(registry) -> int:
    """Seed all upstreams for the happy-path test. Returns the inserted
    alert_decision id."""

    _seed_token_state(registry)
    ath_event_id = _seed_ath_event(registry)
    fee300_id = _seed_fee_window_300s(registry)
    fee60_id = _seed_fee_window_300s(
        registry, as_of=_DECISION_TIME, window_seconds=60
    )
    fee900_id = _seed_fee_window_300s(
        registry, as_of=_DECISION_TIME, window_seconds=900
    )
    _seed_field_features(
        registry,
        fee_window_300s_id=fee300_id,
        fee_window_60s_id=fee60_id,
        fee_window_900s_id=fee900_id,
    )
    _seed_clock_features(registry)
    return registry.alert_decisions.insert(
        _decision(ath_event_id=ath_event_id)
    )


# ----------------------------------------------------------------------
# Constant lock check (spec section 2.1)
# ----------------------------------------------------------------------


def test_class_level_constants_match_spec_section_2_1():
    assert (
        DecisionFeatureSnapshotService.FEATURE_VERSION
        == "decision_features_v0_observe_only"
    )
    assert DecisionFeatureSnapshotService.SCHEMA_VERSION == "schema_v0"


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


def test_happy_path_writes_one_row_with_data_status_ok():
    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    assert result.error is None
    assert result.already_recorded is False
    assert result.decision_score_features_id is not None
    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.alert_decision_id == decision_id
    assert snapshot.feature_version == "decision_features_v0_observe_only"
    assert snapshot.schema_version == "schema_v0"
    assert snapshot.token_address == "token-aaa"
    assert snapshot.token_symbol == "TOK"
    assert snapshot.tier_index == 2
    assert snapshot.tier_name == "tier_2"
    assert snapshot.alert_price == 0.012
    assert snapshot.alert_market_cap == 12000.0
    assert snapshot.ath_price == 0.05
    assert snapshot.ath_market_cap == 50000.0
    assert snapshot.ath_time == _ATH_TIME
    assert snapshot.migration_price == 0.001
    assert snapshot.migration_market_cap == 1000.0
    assert snapshot.migration_time == _MIGRATION_TIME
    assert snapshot.drop_from_ath == -0.76
    assert snapshot.multiple_from_migration == 12.0
    assert snapshot.time_since_migration_seconds == 600.0
    assert snapshot.time_since_ath_seconds == 120.0
    assert snapshot.time_from_migration_to_ath_seconds == 480.0
    assert snapshot.event_count_5m == 20
    assert snapshot.total_fee_5m == 0.4
    assert snapshot.lp_fee_5m == 0.10
    assert snapshot.protocol_fee_5m == 0.10
    assert snapshot.creator_fee_5m == 0.20
    assert snapshot.creator_fee_share_5m == 0.50
    assert snapshot.lp_fee_share_5m == 0.25
    assert snapshot.protocol_fee_share_5m == 0.25
    assert snapshot.fee_per_event_5m == 0.02
    assert snapshot.events_per_minute_5m == 4.0
    assert snapshot.fees_per_minute_5m == 0.08
    assert snapshot.data_status == DataStatus.OK


def test_happy_path_source_snapshot_has_all_six_sections():
    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    sections = snapshot.source_snapshot
    assert set(sections.keys()) == {
        "envelope",
        "upstream_refs",
        "ath_provenance",
        "basis_flags",
        "aux_windows",
        "clock_aux",
    }
    envelope = sections["envelope"]
    assert envelope["service_name"] == "DecisionFeatureSnapshotService"
    assert envelope["feature_version"] == "decision_features_v0_observe_only"
    assert envelope["schema_version"] == "schema_v0"
    assert envelope["decision_time"] == _DECISION_TIME.isoformat()
    assert envelope["as_of_time"] == _DECISION_TIME.isoformat()
    upstream_refs = sections["upstream_refs"]
    assert upstream_refs["alert_decision_id"] == result.alert_decision_id
    assert upstream_refs["fee_window_300s_id"] is not None
    assert upstream_refs["fee_window_60s_id"] is not None
    assert upstream_refs["fee_window_900s_id"] is not None
    # Aux windows whose FK was present.
    assert set(sections["aux_windows"].keys()) == {"60s", "900s"}
    assert sections["clock_aux"]["sequence_phase"] == "pump"
    assert sections["ath_provenance"]["ath_status"] == "confirmed"


# ----------------------------------------------------------------------
# Validation failures
# ----------------------------------------------------------------------


def test_unknown_decision_returns_alert_decision_not_found_no_db_write():
    with _registry_connection() as (connection, registry):
        service = _build_service(registry)
        result = service.snapshot_for_decision(424242)
        row_count = connection.execute(
            "SELECT COUNT(*) AS n FROM decision_score_features"
        ).fetchone()["n"]

    assert result.error == ERROR_ALERT_DECISION_NOT_FOUND
    assert result.snapshot is None
    assert result.decision_score_features_id is None
    assert result.already_recorded is False
    assert row_count == 0


@pytest.mark.parametrize(
    "decision_type",
    [DecisionType.SKIP, DecisionType.BLOCK, DecisionType.ERROR],
)
def test_non_would_alert_decision_returns_decision_type_sentinel(
    decision_type,
):
    with _registry_connection() as (connection, registry):
        decision_id = registry.alert_decisions.insert(
            _decision(decision_type=decision_type)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)
        row_count = connection.execute(
            "SELECT COUNT(*) AS n FROM decision_score_features"
        ).fetchone()["n"]

    assert result.error == ERROR_DECISION_TYPE_NOT_WOULD_ALERT
    assert result.snapshot is None
    assert row_count == 0


def test_decision_with_missing_evaluated_at_returns_time_sentinel():
    # alert_decisions.evaluated_at is NOT NULL in schema; we bypass the
    # repository's path by writing a row with evaluated_at as a sentinel
    # value the service can detect. We use a raw insert with a
    # time-string then mutate the row in-memory by re-loading via raw
    # SQL through a custom AlertDecisionRepository wrapper.
    # The pragmatic way to exercise this path: stub the
    # AlertDecisionRepository.get to return a decision with
    # evaluated_at=None.
    class _StubAlertDecisions:
        def get(self, decision_id):
            assert decision_id == 1
            return _decision(evaluated_at=None)

    with _registry_connection() as (connection, registry):
        service = DecisionFeatureSnapshotService(
            alert_decisions=_StubAlertDecisions(),
            token_sequence=registry.token_sequence,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            fee_windows=registry.fee_windows,
            decision_score_features=registry.decision_score_features,
        )
        result = service.snapshot_for_decision(1)
        row_count = connection.execute(
            "SELECT COUNT(*) AS n FROM decision_score_features"
        ).fetchone()["n"]

    assert result.error == ERROR_DECISION_TIME_MISSING
    assert result.snapshot is None
    assert row_count == 0


# ----------------------------------------------------------------------
# Partial upstream
# ----------------------------------------------------------------------


def test_missing_token_sequence_state_marks_partial_and_keeps_other_columns():
    with _registry_connection() as (_connection, registry):
        # Skip _seed_token_state. Seed everything else.
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.token_symbol is None
    assert snapshot.migration_price is None
    assert snapshot.migration_market_cap is None
    assert snapshot.migration_time is None
    assert "token_sequence_state_missing" in snapshot.missing_reasons
    assert "migration_basis_missing" in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.PARTIAL
    # Other typed columns still populated from the present upstreams.
    assert snapshot.alert_price == 0.012
    assert snapshot.ath_price == 0.05
    assert snapshot.event_count_5m == 20


def test_missing_ath_state_marks_partial_keeps_drop_from_ath_from_decision():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        # No _seed_ath_event call.
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(_decision())
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.ath_price is None
    assert snapshot.ath_market_cap is None
    assert snapshot.ath_time is None
    assert "ath_state_missing" in snapshot.missing_reasons
    assert "ath_basis_missing" in snapshot.missing_reasons
    # drop_from_ath comes from the decision row, not ath_state.
    assert snapshot.drop_from_ath == -0.76
    assert snapshot.data_status == DataStatus.PARTIAL


def test_missing_field_features_marks_partial_and_clears_5m_columns():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        # Skip _seed_field_features.
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.event_count_5m is None
    assert snapshot.creator_fee_share_5m is None
    assert snapshot.events_per_minute_5m is None
    assert snapshot.total_fee_5m is None
    assert snapshot.lp_fee_5m is None
    assert "field_features_missing" in snapshot.missing_reasons
    # field_features absent -> fee_window_300s FK is None too.
    assert "fee_window_300s_id_unset" in snapshot.missing_reasons
    assert "fee_window_300s_missing" in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.PARTIAL


def test_missing_clock_features_marks_partial_and_clears_clock_columns():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        # Skip _seed_clock_features.
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.time_since_migration_seconds is None
    assert snapshot.time_since_ath_seconds is None
    assert snapshot.time_from_migration_to_ath_seconds is None
    assert "clock_features_missing" in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.PARTIAL


def test_field_features_present_but_fee_window_300s_id_unset():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        # Insert field_features with no fee_window_300s_id.
        registry.field_features.insert(
            FieldFeatures(
                token_address="token-aaa",
                as_of_time=_DECISION_TIME,
                fee_window_300s_id=None,  # the test pivot
                liquidity_usd=None,
                event_pace_5m=4.0,
                fee_pace_5m_sol=0.08,
                creator_fee_share_5m=0.5,
                lp_fee_share_5m=0.25,
                protocol_fee_share_5m=0.25,
                event_count_5m=20,
                feature_version="field_v0_placeholder",
                data_status=DataStatus.OK,
            )
        )
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    # Share metrics + event_count come from field_features, populated.
    assert snapshot.event_count_5m == 20
    assert snapshot.creator_fee_share_5m == 0.5
    # SOL-amount columns come from fee_window_300s, NULL because FK unset.
    assert snapshot.total_fee_5m is None
    assert snapshot.lp_fee_5m is None
    assert snapshot.creator_fee_5m is None
    assert snapshot.fee_per_event_5m is None
    assert "fee_window_300s_id_unset" in snapshot.missing_reasons
    assert "fee_window_300s_missing" in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.PARTIAL


def test_liquidity_usd_unpopulated_does_not_degrade_data_status_to_partial():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(
            registry,
            fee_window_300s_id=fee300_id,
            liquidity_usd=None,  # the explicit unpopulated case
        )
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert snapshot.liquidity_usd is None
    assert "liquidity_usd_unpopulated" in snapshot.missing_reasons
    # Status stays OK -- the fine code is informational only.
    assert snapshot.data_status == DataStatus.OK


# ----------------------------------------------------------------------
# Mixed-basis validation
# ----------------------------------------------------------------------


def test_alert_basis_valid_via_price_fallback_keeps_status_ok():
    """alert_market_cap missing but alert_price > 0 -> alert basis valid,
    so OK with only the fine code (alert_market_cap_missing) and NOT
    the coarse code (alert_basis_missing).
    """

    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(
                current_price=0.012, current_mcap=None, ath_event_id=ath_event_id
            )
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert "alert_market_cap_missing" in snapshot.missing_reasons
    assert "alert_basis_missing" not in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.OK


def test_alert_basis_fully_missing_marks_partial_with_both_tiers():
    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry)
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(
                current_price=None, current_mcap=None, ath_event_id=ath_event_id
            )
        )
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    assert "alert_price_missing" in snapshot.missing_reasons
    assert "alert_market_cap_missing" in snapshot.missing_reasons
    assert "alert_basis_missing" in snapshot.missing_reasons
    assert snapshot.data_status == DataStatus.PARTIAL


# ----------------------------------------------------------------------
# Idempotency
# ----------------------------------------------------------------------


def test_re_invocation_returns_already_recorded_no_second_row():
    with _registry_connection() as (connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        first = service.snapshot_for_decision(decision_id)
        second = service.snapshot_for_decision(decision_id)
        row_count = connection.execute(
            "SELECT COUNT(*) AS n FROM decision_score_features WHERE alert_decision_id = ?",
            (decision_id,),
        ).fetchone()["n"]

    assert first.already_recorded is False
    assert second.already_recorded is True
    assert second.error is None
    assert second.snapshot is not None
    assert second.decision_score_features_id == first.decision_score_features_id
    assert row_count == 1


def test_unique_race_during_insert_resolves_to_already_recorded():
    """Simulate the UNIQUE-race window between probe and insert by
    wrapping the repository so its insert raises IntegrityError on the
    first call. The service catches the error, re-probes, and reports
    already_recorded.
    """

    class _RaceRepo:
        def __init__(self, real_repo: DecisionScoreFeatureRepository):
            self._real = real_repo
            self._winner_inserted = False

        def get_by_decision_and_version(self, alert_decision_id, feature_version):
            return self._real.get_by_decision_and_version(
                alert_decision_id, feature_version
            )

        def insert(self, snapshot):
            # Inject the race winner row, then raise the UNIQUE violation
            # the actual real insert would have hit.
            if not self._winner_inserted:
                self._winner_inserted = True
                self._real.insert(snapshot)
                raise sqlite3.IntegrityError(
                    "UNIQUE constraint failed: "
                    "decision_score_features.alert_decision_id, "
                    "decision_score_features.feature_version"
                )
            return self._real.insert(snapshot)

        def get_by_id(self, snapshot_id):
            return self._real.get_by_id(snapshot_id)

        def get_all_for_decision(self, alert_decision_id):
            return self._real.get_all_for_decision(alert_decision_id)

        def list_by_token(self, token_address, limit=100):
            return self._real.list_by_token(token_address, limit=limit)

    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        race_repo = _RaceRepo(registry.decision_score_features)
        service = DecisionFeatureSnapshotService(
            alert_decisions=registry.alert_decisions,
            token_sequence=registry.token_sequence,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            fee_windows=registry.fee_windows,
            decision_score_features=race_repo,
        )
        result = service.snapshot_for_decision(decision_id)
        rows = registry.decision_score_features.get_all_for_decision(
            decision_id
        )

    assert result.already_recorded is True
    assert result.error is None
    assert result.snapshot is not None
    assert result.decision_score_features_id is not None
    # The service did NOT write a duplicate; the race-winner row is the
    # only row for this decision.
    assert len(rows) == 1


def test_unique_race_with_genuine_duplicate_re_raises_when_no_existing_row():
    """An IntegrityError that is NOT a UNIQUE-race (no row found on
    re-probe) must be re-raised, not swallowed. This guards against
    treating real constraint violations (CHECK / NOT NULL / FK) as
    silent already-recorded returns.
    """

    class _BogusUniqueRepo:
        def __init__(self, real):
            self._real = real

        def get_by_decision_and_version(self, alert_decision_id, feature_version):
            return self._real.get_by_decision_and_version(
                alert_decision_id, feature_version
            )

        def insert(self, snapshot):
            # Pretend a UNIQUE violation but never actually write the row;
            # the service's re-probe will find nothing and must re-raise.
            raise sqlite3.IntegrityError(
                "UNIQUE constraint failed: pretend"
            )

        def get_by_id(self, snapshot_id):
            return self._real.get_by_id(snapshot_id)

        def get_all_for_decision(self, alert_decision_id):
            return self._real.get_all_for_decision(alert_decision_id)

        def list_by_token(self, token_address, limit=100):
            return self._real.list_by_token(token_address, limit=limit)

    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        bogus = _BogusUniqueRepo(registry.decision_score_features)
        service = DecisionFeatureSnapshotService(
            alert_decisions=registry.alert_decisions,
            token_sequence=registry.token_sequence,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            fee_windows=registry.fee_windows,
            decision_score_features=bogus,
        )
        with pytest.raises(sqlite3.IntegrityError):
            service.snapshot_for_decision(decision_id)


# ----------------------------------------------------------------------
# As-of-time defaulting
# ----------------------------------------------------------------------


def test_as_of_time_defaults_to_decision_evaluated_at_when_omitted():
    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    assert result.snapshot is not None
    assert result.snapshot.as_of_time == _DECISION_TIME


def test_as_of_time_uses_caller_value_when_passed():
    explicit = _DECISION_TIME - timedelta(seconds=42)
    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        result = service.snapshot_for_decision(
            decision_id, as_of_time=explicit
        )

    assert result.snapshot is not None
    assert result.snapshot.as_of_time == explicit


def test_as_of_time_default_ignores_far_future_current_time_provider():
    """Spec section 12.3 flag-2 critical test.

    Pin the L8 default-as_of_time policy: when ``as_of_time=None`` and
    ``current_time_provider`` returns a far-future date, the persisted
    ``as_of_time`` must equal ``decision.evaluated_at``, NOT the
    far-future ``current_time_provider`` value. ``current_time_provider``
    only feeds the persisted ``created_at`` audit field.

    This guards against accidental Stage 9 / Stage 10 default-time
    copy-paste regression.
    """

    far_future = datetime(2099, 12, 31, 23, 59, tzinfo=timezone.utc)

    def far_future_clock():
        return far_future

    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(
            registry, current_time_provider=far_future_clock
        )
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    # as_of_time stays at decision.evaluated_at, NOT far_future.
    assert snapshot.as_of_time == _DECISION_TIME
    assert snapshot.as_of_time != far_future
    # created_at IS allowed to come from current_time_provider.
    assert snapshot.created_at == far_future


# ----------------------------------------------------------------------
# Read isolation
# ----------------------------------------------------------------------


def _row_counts_per_table(connection: sqlite3.Connection) -> dict:
    tables = [
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        table: connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}"
        ).fetchone()["n"]
        for table in tables
    }


def test_snapshot_for_decision_only_changes_decision_score_features_row_count():
    with _registry_connection() as (connection, registry):
        decision_id = _seed_full_happy_path(registry)
        before = _row_counts_per_table(connection)
        service = _build_service(registry)
        service.snapshot_for_decision(decision_id)
        after = _row_counts_per_table(connection)

    # Every existing table that did NOT change.
    delta = {
        table: (before[table], after[table])
        for table in before
        if before[table] != after[table]
    }
    assert delta == {
        "decision_score_features": (before["decision_score_features"], 1)
    }, (
        f"snapshot_for_decision must only change the row count of "
        f"decision_score_features. Observed deltas: {delta}"
    )


def test_constructor_signature_excludes_forbidden_repositories():
    """The service constructor surface enforces L5 read-isolation.

    The seven dependencies are the read/write allowlist; the parameters
    listed here MUST NOT appear in the service's __init__ signature so
    that forbidden reads are caught at construction time as a missing
    dependency rather than at runtime as a coupling escape.
    """

    forbidden = {
        "filter_evaluations",
        "outcome_windows",
        "dispatch_events",
        "score_features",
        "price_observations",
        "raw_pumpswap_events",
        "price_curve_points",
        "migration_events",
    }
    init_params = (
        DecisionFeatureSnapshotService.__init__.__code__.co_varnames[
            : DecisionFeatureSnapshotService.__init__.__code__.co_argcount
        ]
    )
    leak = forbidden.intersection(init_params)
    assert leak == set(), (
        f"Stage 11 service must not accept any of {sorted(forbidden)} as "
        f"a constructor dependency. Found leak: {leak}"
    )


# ----------------------------------------------------------------------
# Versioning
# ----------------------------------------------------------------------


def test_v0_and_v1_feature_versions_coexist_for_one_decision():
    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service_v0 = _build_service(registry)
        v0_result = service_v0.snapshot_for_decision(decision_id)

        # Hand-craft a v1 service by subclassing with overridden constants.
        class _V1Service(DecisionFeatureSnapshotService):
            FEATURE_VERSION = "decision_features_v1_observe_only"

        service_v1 = _V1Service(
            alert_decisions=registry.alert_decisions,
            token_sequence=registry.token_sequence,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            fee_windows=registry.fee_windows,
            decision_score_features=registry.decision_score_features,
        )
        v1_result = service_v1.snapshot_for_decision(decision_id)

        rows = registry.decision_score_features.get_all_for_decision(
            decision_id
        )

    assert v0_result.error is None
    assert v1_result.error is None
    assert v0_result.already_recorded is False
    assert v1_result.already_recorded is False
    assert v0_result.feature_version == "decision_features_v0_observe_only"
    assert v1_result.feature_version == "decision_features_v1_observe_only"
    feature_versions = sorted(row.feature_version for row in rows)
    assert feature_versions == [
        "decision_features_v0_observe_only",
        "decision_features_v1_observe_only",
    ]


# ----------------------------------------------------------------------
# Source-snapshot JSON shape
# ----------------------------------------------------------------------


def test_source_snapshot_json_persisted_compact_and_sorted():
    with _registry_connection() as (connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        service.snapshot_for_decision(decision_id)
        raw_json = connection.execute(
            "SELECT source_snapshot_json FROM decision_score_features "
            "WHERE alert_decision_id = ?",
            (decision_id,),
        ).fetchone()["source_snapshot_json"]

    parsed = json.loads(raw_json)
    # Six top-level sections, no extras.
    assert set(parsed.keys()) == {
        "envelope",
        "upstream_refs",
        "ath_provenance",
        "basis_flags",
        "aux_windows",
        "clock_aux",
    }
    # Compact: no whitespace separators.
    assert ", " not in raw_json
    assert ": " not in raw_json
    # Sorted keys: top-level order is strict ASCII alphabetical
    # (so ath_* < aux_* because t < u).
    expected_top_order = [
        "ath_provenance",
        "aux_windows",
        "basis_flags",
        "clock_aux",
        "envelope",
        "upstream_refs",
    ]
    for key in expected_top_order:
        assert f'"{key}"' in raw_json
    indices = [raw_json.index(f'"{key}"') for key in expected_top_order]
    assert indices == sorted(indices), (
        f"source_snapshot_json keys must be persisted in sorted order; "
        f"observed indices for {expected_top_order} = {indices}"
    )


def test_aux_windows_omits_entries_for_missing_fee_window_fks():
    """Per spec section 8.6: each aux_windows entry is omitted when the
    source FK is unset on field_features. The happy-path seed populates
    only 60s and 900s, so 1800s and 3600s entries must be absent.
    """

    with _registry_connection() as (_connection, registry):
        decision_id = _seed_full_happy_path(registry)
        service = _build_service(registry)
        result = service.snapshot_for_decision(decision_id)

    snapshot = result.snapshot
    assert snapshot is not None
    aux = snapshot.source_snapshot["aux_windows"]
    assert set(aux.keys()) == {"60s", "900s"}


# ----------------------------------------------------------------------
# Decision-context denormalization freeze
# ----------------------------------------------------------------------


def test_token_symbol_is_frozen_at_decision_time_after_upstream_mutation():
    """Spec section 12.3 freeze test.

    The snapshot captures ``token_symbol`` from the
    ``token_sequence_state`` row at decision time. A subsequent update
    to that row must NOT propagate to the persisted snapshot.
    """

    with _registry_connection() as (_connection, registry):
        _seed_token_state(registry, symbol="OLD")
        ath_event_id = _seed_ath_event(registry)
        fee300_id = _seed_fee_window_300s(registry)
        _seed_field_features(registry, fee_window_300s_id=fee300_id)
        _seed_clock_features(registry)
        decision_id = registry.alert_decisions.insert(
            _decision(ath_event_id=ath_event_id)
        )
        service = _build_service(registry)
        first_result = service.snapshot_for_decision(decision_id)

        # Mutate the upstream symbol AFTER snapshot.
        registry.token_sequence.upsert(
            TokenState(
                token_address="token-aaa",
                symbol="REBRANDED",
                pool_address="pool-aaa",
                migration_time=_MIGRATION_TIME,
                migration_source="grpc",
                migration_price=0.001,
                migration_mcap=1000.0,
                current_price=0.012,
                current_mcap=12000.0,
                last_price_update=_DECISION_TIME,
                sequence_phase="pump",
                current_status="tracking",
                data_status=DataStatus.OK,
            )
        )

        # Re-load the persisted snapshot row directly via the repository.
        loaded = registry.decision_score_features.get_by_id(
            first_result.decision_score_features_id
        )

    assert first_result.snapshot is not None
    assert first_result.snapshot.token_symbol == "OLD"
    assert loaded is not None
    assert loaded.token_symbol == "OLD"


# ----------------------------------------------------------------------
# Module-level pure-function tests (spec section 12.4)
# ----------------------------------------------------------------------


def test_derive_data_status_ok_when_all_conditions_met():
    assert (
        derive_data_status(
            alert_basis_valid=True,
            ath_basis_valid=True,
            migration_basis_valid=True,
            field_features_present=True,
            clock_features_present=True,
            fee_window_300s_present=True,
            token_sequence_state_present=True,
        )
        == DataStatus.OK
    )


@pytest.mark.parametrize(
    "missing_flag",
    [
        "alert_basis_valid",
        "ath_basis_valid",
        "migration_basis_valid",
        "field_features_present",
        "clock_features_present",
        "fee_window_300s_present",
        "token_sequence_state_present",
    ],
)
def test_derive_data_status_partial_when_one_coarse_input_absent(missing_flag):
    flags = dict(
        alert_basis_valid=True,
        ath_basis_valid=True,
        migration_basis_valid=True,
        field_features_present=True,
        clock_features_present=True,
        fee_window_300s_present=True,
        token_sequence_state_present=True,
    )
    flags[missing_flag] = False
    # Removing field_features OR clock_features alone is PARTIAL; only
    # both together pushes to MISSING.
    assert derive_data_status(**flags) == DataStatus.PARTIAL


def test_derive_data_status_missing_when_all_three_basis_groups_invalid():
    assert (
        derive_data_status(
            alert_basis_valid=False,
            ath_basis_valid=False,
            migration_basis_valid=False,
            field_features_present=True,
            clock_features_present=True,
            fee_window_300s_present=True,
            token_sequence_state_present=True,
        )
        == DataStatus.MISSING
    )


def test_derive_data_status_missing_when_field_and_clock_both_absent():
    assert (
        derive_data_status(
            alert_basis_valid=True,
            ath_basis_valid=True,
            migration_basis_valid=True,
            field_features_present=False,
            clock_features_present=False,
            fee_window_300s_present=True,
            token_sequence_state_present=True,
        )
        == DataStatus.MISSING
    )
