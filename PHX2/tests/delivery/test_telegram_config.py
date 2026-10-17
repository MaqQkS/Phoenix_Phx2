from __future__ import annotations

import pytest

from PHX2.delivery.telegram_config import (
    ENV_DELIVERY_TRANSPORT,
    ENV_DISCORD_ENABLED,
    ENV_TELEGRAM_BOT_TOKEN,
    ENV_TELEGRAM_CHAT_ID,
    ENV_TELEGRAM_DISABLE_LINK_PREVIEW,
    ENV_TELEGRAM_ENABLED,
    ENV_TELEGRAM_PARSE_MODE,
    TelegramConfig,
    TelegramConfigError,
)


TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd"
CHAT = "-1001234567890"


def _values(**overrides: str) -> dict[str, str]:
    values = {
        ENV_DELIVERY_TRANSPORT: "telegram",
        ENV_TELEGRAM_ENABLED: "true",
        ENV_TELEGRAM_BOT_TOKEN: TOKEN,
        ENV_TELEGRAM_CHAT_ID: CHAT,
        ENV_TELEGRAM_PARSE_MODE: "HTML",
        ENV_TELEGRAM_DISABLE_LINK_PREVIEW: "true",
        ENV_DISCORD_ENABLED: "false",
    }
    values.update(overrides)
    return values


def test_exact_telegram_contract_accepts_numeric_chat_as_string():
    config = TelegramConfig.from_mapping(_values())
    assert config.transport == "telegram"
    assert config.telegram_enabled is True
    assert config.chat_id == CHAT and isinstance(config.chat_id, str)
    assert config.parse_mode == "HTML"
    assert config.disable_link_preview is True
    assert config.discord_enabled is False


def test_channel_username_is_accepted():
    assert TelegramConfig.from_mapping(
        _values(**{ENV_TELEGRAM_CHAT_ID: "@PHXBOTSCANS"})
    ).chat_id == "@PHXBOTSCANS"


@pytest.mark.parametrize(
    ("name", "reason"),
    (
        (ENV_TELEGRAM_BOT_TOKEN, "TELEGRAM_TOKEN_MISSING"),
        (ENV_TELEGRAM_CHAT_ID, "TELEGRAM_CHAT_ID_MISSING"),
    ),
)
def test_required_secret_or_destination_fails_closed(name, reason):
    with pytest.raises(TelegramConfigError, match=f"^{reason}$"):
        TelegramConfig.from_mapping(_values(**{name: ""}))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({ENV_DELIVERY_TRANSPORT: "discord"}, "DELIVERY_TRANSPORT_NOT_TELEGRAM"),
        ({ENV_DELIVERY_TRANSPORT: "TELEGRAM"}, "DELIVERY_TRANSPORT_NOT_TELEGRAM"),
        ({ENV_TELEGRAM_ENABLED: "false"}, "TELEGRAM_DISABLED"),
        ({ENV_TELEGRAM_ENABLED: "1"}, "TELEGRAM_ENABLED_MALFORMED"),
        ({ENV_DISCORD_ENABLED: "true"}, "DUAL_TRANSPORT_FORBIDDEN"),
        ({ENV_TELEGRAM_BOT_TOKEN: "not-a-token"}, "TELEGRAM_TOKEN_MALFORMED"),
        ({ENV_TELEGRAM_CHAT_ID: "channel with spaces"}, "TELEGRAM_CHAT_ID_MALFORMED"),
        ({ENV_TELEGRAM_PARSE_MODE: "MarkdownV2"}, "TELEGRAM_PARSE_MODE_NOT_HTML"),
        ({ENV_TELEGRAM_DISABLE_LINK_PREVIEW: "false"},
         "TELEGRAM_LINK_PREVIEW_MUST_BE_DISABLED"),
    ),
)
def test_malformed_or_dual_transport_configuration_fails_closed(overrides, reason):
    with pytest.raises(TelegramConfigError, match=f"^{reason}$"):
        TelegramConfig.from_mapping(_values(**overrides))


def test_config_repr_status_and_errors_never_expose_token_or_chat():
    config = TelegramConfig.from_mapping(_values())
    combined = repr(config) + repr(config.redacted_status())
    assert TOKEN not in combined and CHAT not in combined
    assert config.redacted_status() == {
        "transport": "TELEGRAM",
        "telegram_enabled": True,
        "telegram_token_configured": True,
        "telegram_chat_configured": True,
        "discord_enabled": False,
    }
    with pytest.raises(TelegramConfigError) as caught:
        TelegramConfig.from_mapping(_values(**{ENV_TELEGRAM_BOT_TOKEN: TOKEN + "!"}))
    assert TOKEN not in str(caught.value) and TOKEN not in repr(caught.value)
