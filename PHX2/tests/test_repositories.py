"""Tests for PHX2 repository construction contracts."""

import sqlite3

from PHX2.db.repositories import (
    ATHRepository,
    AlertDecisionRepository,
    ClockFeatureRepository,
    DispatchEventRepository,
    FeeWindowRepository,
    FieldFeatureRepository,
    FilterEvaluationRepository,
    MigrationEventRepository,
    OutcomeWindowRepository,
    PriceCurvePointRepository,
    PriceObservationRepository,
    RawPumpSwapEventRepository,
    RepositoryRegistry,
    ScoreFeatureRepository,
    TokenSequenceRepository,
    repository_registry,
)


REPOSITORY_CLASSES = [
    TokenSequenceRepository,
    MigrationEventRepository,
    PriceObservationRepository,
    RawPumpSwapEventRepository,
    PriceCurvePointRepository,
    ATHRepository,
    AlertDecisionRepository,
    FilterEvaluationRepository,
    FeeWindowRepository,
    FieldFeatureRepository,
    ScoreFeatureRepository,
    ClockFeatureRepository,
    OutcomeWindowRepository,
    DispatchEventRepository,
]


def test_repository_classes_accept_existing_connection():
    connection = sqlite3.connect(":memory:")
    try:
        for repository_class in REPOSITORY_CLASSES:
            repository = repository_class(connection)
            assert repository.connection is connection
    finally:
        connection.close()


def test_repository_registry_is_empty_by_default():
    registry = RepositoryRegistry()

    assert registry.token_sequence is None
    assert registry.migration_events is None
    assert registry.price_observations is None
    assert registry.raw_pumpswap_events is None
    assert registry.price_curve_points is None
    assert registry.ath is None
    assert registry.alert_decisions is None
    assert registry.filter_evaluations is None
    assert registry.fee_windows is None
    assert registry.field_features is None
    assert registry.score_features is None
    assert registry.clock_features is None
    assert registry.outcome_windows is None
    assert registry.dispatch_events is None


def test_repository_registry_factory_binds_all_repositories():
    connection = sqlite3.connect(":memory:")
    try:
        registry = repository_registry(connection)

        assert isinstance(registry.token_sequence, TokenSequenceRepository)
        assert isinstance(registry.migration_events, MigrationEventRepository)
        assert isinstance(registry.price_observations, PriceObservationRepository)
        assert isinstance(registry.raw_pumpswap_events, RawPumpSwapEventRepository)
        assert isinstance(registry.price_curve_points, PriceCurvePointRepository)
        assert isinstance(registry.ath, ATHRepository)
        assert isinstance(registry.alert_decisions, AlertDecisionRepository)
        assert isinstance(registry.filter_evaluations, FilterEvaluationRepository)
        assert isinstance(registry.fee_windows, FeeWindowRepository)
        assert isinstance(registry.field_features, FieldFeatureRepository)
        assert isinstance(registry.score_features, ScoreFeatureRepository)
        assert isinstance(registry.clock_features, ClockFeatureRepository)
        assert isinstance(registry.outcome_windows, OutcomeWindowRepository)
        assert isinstance(registry.dispatch_events, DispatchEventRepository)
    finally:
        connection.close()
