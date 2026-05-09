"""Tests for PHX2 typed settings defaults."""

from PHX2.config.settings import DispatchMode, PHX2Settings, RuntimeMode


def test_settings_load_with_expected_defaults():
    settings = PHX2Settings()

    assert settings.runtime_mode == RuntimeMode.DRY_RUN
    assert settings.dry_run is True
    assert settings.phoenix1_db.path == "data/bot.db"
    assert settings.phx2_db.path == "data/phx2_dryrun.db"
    assert settings.score.score_version == "score_v0_observe_only"


def test_dispatch_mode_default_is_disabled():
    settings = PHX2Settings()

    assert settings.dispatch.dispatch_mode == DispatchMode.DISABLED
    assert settings.dispatch.dispatch_mode.value == "disabled"


def test_configured_fee_windows_match_stage2_plan():
    settings = PHX2Settings()

    assert list(settings.feature_windows.fee_windows_seconds) == [
        60,
        300,
        900,
        1800,
        3600,
    ]


def test_configured_outcome_windows_match_stage2_plan():
    settings = PHX2Settings()

    assert list(settings.outcome_windows.outcome_windows_seconds) == [
        300,
        900,
        1800,
        3600,
        14400,
        86400,
    ]


def test_allowed_dispatch_modes_are_explicit():
    assert [mode.value for mode in DispatchMode] == [
        "disabled",
        "file_preview",
        "console",
        "telegram_private",
        "discord_private",
        "telegram_live",
        "discord_live",
        "multi",
    ]
