"""Fail-closed Telegram production configuration.

Only redacted presence/status data may leave this module.  The bot token is
excluded from dataclass representations and configuration errors carry one
closed-set reason token, never an offending value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Mapping


ENV_DELIVERY_TRANSPORT = "PHX2_DELIVERY_TRANSPORT"
ENV_TELEGRAM_ENABLED = "PHX2_TELEGRAM_ENABLED"
ENV_TELEGRAM_BOT_TOKEN = "PHX2_TELEGRAM_BOT_TOKEN"
ENV_TELEGRAM_CHAT_ID = "PHX2_TELEGRAM_CHAT_ID"
ENV_TELEGRAM_PARSE_MODE = "PHX2_TELEGRAM_PARSE_MODE"
ENV_TELEGRAM_DISABLE_LINK_PREVIEW = "PHX2_TELEGRAM_DISABLE_LINK_PREVIEW"
ENV_DISCORD_ENABLED = "PHX2_DISCORD_ENABLED"
ENV_TELEGRAM_COIN_IMAGES_ENABLED = "PHX2_TELEGRAM_COIN_IMAGES_ENABLED"

TELEGRAM_ENV_NAMES = (
    ENV_DELIVERY_TRANSPORT,
    ENV_TELEGRAM_ENABLED,
    ENV_TELEGRAM_BOT_TOKEN,
    ENV_TELEGRAM_CHAT_ID,
    ENV_TELEGRAM_PARSE_MODE,
    ENV_TELEGRAM_DISABLE_LINK_PREVIEW,
    ENV_DISCORD_ENABLED,
    ENV_TELEGRAM_COIN_IMAGES_ENABLED,
)

TELEGRAM_DESTINATION_ALIAS = "PHOENIX_CHANNEL"
TELEGRAM_PARSE_MODE_HTML = "HTML"

_TOKEN_RE = re.compile(r"^[0-9]{5,}:[A-Za-z0-9_-]{20,}$")
_NUMERIC_CHAT_RE = re.compile(r"^-?[0-9]+$")
_USERNAME_CHAT_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$")


class TelegramConfigError(ValueError):
    """Closed-set configuration refusal with no secret-bearing detail."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _required(values: Mapping[str, str], name: str, reason: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise TelegramConfigError(reason)
    return value.strip()


def _strict_bool(values: Mapping[str, str], name: str, reason: str) -> bool:
    value = _required(values, name, reason).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise TelegramConfigError(reason)


@dataclass(frozen=True)
class TelegramConfig:
    transport: str
    telegram_enabled: bool
    bot_token: str = field(repr=False)
    chat_id: str = field(repr=False)
    parse_mode: str = TELEGRAM_PARSE_MODE_HTML
    disable_link_preview: bool = True
    discord_enabled: bool = False
    destination_alias: str = TELEGRAM_DESTINATION_ALIAS
    coin_images_enabled: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "TelegramConfig":
        transport = _required(
            values, ENV_DELIVERY_TRANSPORT, "DELIVERY_TRANSPORT_REQUIRED")
        if transport != "telegram":
            raise TelegramConfigError("DELIVERY_TRANSPORT_NOT_TELEGRAM")

        telegram_enabled = _strict_bool(
            values, ENV_TELEGRAM_ENABLED, "TELEGRAM_ENABLED_MALFORMED")
        discord_enabled = _strict_bool(
            values, ENV_DISCORD_ENABLED, "DISCORD_ENABLED_MALFORMED")
        if discord_enabled:
            raise TelegramConfigError("DUAL_TRANSPORT_FORBIDDEN")
        if not telegram_enabled:
            raise TelegramConfigError("TELEGRAM_DISABLED")

        token = _required(values, ENV_TELEGRAM_BOT_TOKEN, "TELEGRAM_TOKEN_MISSING")
        if not _TOKEN_RE.fullmatch(token):
            raise TelegramConfigError("TELEGRAM_TOKEN_MALFORMED")

        chat_id = _required(values, ENV_TELEGRAM_CHAT_ID, "TELEGRAM_CHAT_ID_MISSING")
        if not (_NUMERIC_CHAT_RE.fullmatch(chat_id)
                or _USERNAME_CHAT_RE.fullmatch(chat_id)):
            raise TelegramConfigError("TELEGRAM_CHAT_ID_MALFORMED")

        parse_mode = _required(
            values, ENV_TELEGRAM_PARSE_MODE, "TELEGRAM_PARSE_MODE_MISSING")
        if parse_mode != TELEGRAM_PARSE_MODE_HTML:
            raise TelegramConfigError("TELEGRAM_PARSE_MODE_NOT_HTML")

        disable_preview = _strict_bool(
            values,
            ENV_TELEGRAM_DISABLE_LINK_PREVIEW,
            "TELEGRAM_LINK_PREVIEW_SETTING_MALFORMED",
        )
        if not disable_preview:
            raise TelegramConfigError("TELEGRAM_LINK_PREVIEW_MUST_BE_DISABLED")

        image_flag = values.get(ENV_TELEGRAM_COIN_IMAGES_ENABLED, "false")
        if not isinstance(image_flag, str) or image_flag.strip().lower() not in ("true", "false"):
            raise TelegramConfigError("TELEGRAM_COIN_IMAGES_SETTING_MALFORMED")
        return cls(
            transport=transport,
            telegram_enabled=True,
            bot_token=token,
            chat_id=str(chat_id),
            parse_mode=parse_mode,
            disable_link_preview=True,
            discord_enabled=False,
            coin_images_enabled=image_flag.strip().lower() == "true",
        )

    def redacted_status(self) -> dict[str, bool | str]:
        return {
            "transport": "TELEGRAM",
            "telegram_enabled": True,
            "telegram_token_configured": True,
            "telegram_chat_configured": True,
            "discord_enabled": False,
        }


__all__ = (
    "ENV_DELIVERY_TRANSPORT",
    "ENV_TELEGRAM_ENABLED",
    "ENV_TELEGRAM_BOT_TOKEN",
    "ENV_TELEGRAM_CHAT_ID",
    "ENV_TELEGRAM_PARSE_MODE",
    "ENV_TELEGRAM_DISABLE_LINK_PREVIEW",
    "ENV_DISCORD_ENABLED",
    "ENV_TELEGRAM_COIN_IMAGES_ENABLED",
    "TELEGRAM_ENV_NAMES",
    "TELEGRAM_DESTINATION_ALIAS",
    "TELEGRAM_PARSE_MODE_HTML",
    "TelegramConfig",
    "TelegramConfigError",
)
