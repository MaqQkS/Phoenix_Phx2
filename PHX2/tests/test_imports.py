"""Smoke tests for the PHX2 Stage 1 scaffold."""

import importlib


PHX2_MODULES = [
    "PHX2",
    "PHX2.main",
    "PHX2.config.settings",
    "PHX2.config",
    "PHX2.db.connection",
    "PHX2.db",
    "PHX2.db.migrations",
    "PHX2.db.repositories",
    "PHX2.models.enums",
    "PHX2.models.serialization",
    "PHX2.models.token_state",
    "PHX2.models.migration_event",
    "PHX2.models.price_observation",
    "PHX2.models.ath_state",
    "PHX2.models.alert_decision",
    "PHX2.models.dispatch_event",
    "PHX2.models.fee_window",
    "PHX2.models.filter_result",
    "PHX2.models.field_features",
    "PHX2.models.score_features",
    "PHX2.models.clock_features",
    "PHX2.models.outcome_window",
    "PHX2.models.raw_pumpswap_event",
    "PHX2.models.price_curve_point",
    "PHX2.services.migration_service",
    "PHX2.services.price_service",
    "PHX2.services.pumpswap_event_ingestion_service",
    "PHX2.services.ath_service",
    "PHX2.services.alert_eligibility_engine",
    "PHX2.services.filter_evaluation_engine",
    "PHX2.services.telemetry_service",
    "PHX2.services.alert_dispatcher",
    "PHX2.services.feature_window_service",
    "PHX2.services.field_feature_service",
    "PHX2.services.score_feature_service",
    "PHX2.services.clock_feature_service",
    "PHX2.services.curve_capture_service",
    "PHX2.services.outcome_tracking_service",
    "PHX2.integrations.dexscreener_client",
    "PHX2.integrations.birdeye_client",
    "PHX2.integrations.helius_client",
    "PHX2.integrations.telegram_client",
    "PHX2.integrations.discord_client",
    "PHX2.renderers.alert_renderer",
    "PHX2.renderers.telegram_renderer",
    "PHX2.scripts.dry_run_compare",
    "PHX2.scripts.backfill_ath_cases",
    "PHX2.scripts.export_decisions",
    "PHX2.scripts.export_research_features",
    "PHX2.scripts.preview_alerts",
]


def test_phx2_modules_import_without_side_effects():
    for module_name in PHX2_MODULES:
        assert importlib.import_module(module_name)


def test_stage1_placeholder_boundaries_are_named():
    from PHX2.config import DispatchMode as ConfigDispatchMode
    from PHX2.models import ClockFeatures, FieldFeatures, ScoreFeatures
    from PHX2.services import (
        AlertEligibilityEngine,
        ATHService,
        CurveCaptureService,
        DispatchMode,
        FeatureWindowService,
        PumpSwapEventIngestionService,
        TelemetryService,
    )
    from PHX2.renderers import AlertRenderer, TelegramRenderer

    assert ATHService.__name__ == "ATHService"
    assert callable(ATHService.evaluate_price_observation)
    assert callable(ATHService.rebuild_from_price_observations)
    assert CurveCaptureService.__name__ == "CurveCaptureService"
    assert AlertEligibilityEngine.__name__ == "AlertEligibilityEngine"
    assert TelemetryService.__name__ == "TelemetryService"
    assert FeatureWindowService.__name__ == "FeatureWindowService"
    assert PumpSwapEventIngestionService.__name__ == "PumpSwapEventIngestionService"
    assert ConfigDispatchMode.DISABLED.value == "disabled"
    assert DispatchMode.DISABLED.value == "disabled"
    assert FieldFeatures.__name__ == "FieldFeatures"
    assert ScoreFeatures.__name__ == "ScoreFeatures"
    assert ClockFeatures.__name__ == "ClockFeatures"
    assert AlertRenderer.__name__ == "AlertRenderer"
    assert TelegramRenderer.__name__ == "TelegramRenderer"
