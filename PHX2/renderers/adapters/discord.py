"""Discord embed adapter for :class:`PHX2.renderers.rendered_alert.RenderedAlert`.

The adapter is a pure function over a :class:`RenderedAlert`. It performs no
I/O, never reads the clock, never reads environment variables, and never
raises. Same input → byte-identical output every time.

Stage 8C uses this adapter inside :class:`PHX2.dispatch.sinks.discord.DiscordSink`
to produce a Discord webhook embed payload. The sink owns the network call;
the adapter owns the shape.

Color palette: blue / amber / gray / red. Green is intentionally avoided so
neither CLEAN nor PARTIAL reads as a "go" signal in a dry-run channel, and
PARTIAL stays visually distinct from CLEAN.
"""

import logging
from typing import Any, Dict, List

from PHX2.renderers.rendered_alert import RenderedAlert, Severity


logger = logging.getLogger(__name__)


COLOR_CLEAN = 0x3B82F6
COLOR_PARTIAL = 0xF59E0B
COLOR_INFO = 0x6B7280
COLOR_ERROR = 0xEF4444

_SEVERITY_COLORS = {
    Severity.CLEAN: COLOR_CLEAN,
    Severity.PARTIAL: COLOR_PARTIAL,
    Severity.INFO: COLOR_INFO,
    Severity.ERROR: COLOR_ERROR,
}

_COMPACT_DECISION_TYPES = frozenset({"skip", "block", "error"})

TITLE_LIMIT = 256
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
FOOTER_TEXT_LIMIT = 2048
DESCRIPTION_LIMIT = 4096
TOTAL_EMBED_LIMIT = 6000
MAX_FIELDS = 25

_ELLIPSIS = "…"
_MIDDLE_DOT = " · "


class DiscordEmbedAdapter:
    """Format a :class:`RenderedAlert` as a Discord webhook embed dict."""

    def format(self, rendered: RenderedAlert) -> Dict[str, Any]:
        severity = rendered.severity
        color = _SEVERITY_COLORS.get(severity, COLOR_INFO)
        timestamp = rendered.footer.get("evaluated_at", "")
        footer_text = _truncate(_build_footer_text(rendered), FOOTER_TEXT_LIMIT, "footer.text")

        if rendered.decision_type.lower() in _COMPACT_DECISION_TYPES:
            title = _truncate(_compact_title(rendered), TITLE_LIMIT, "title")
            fields = _compact_fields(rendered)
        else:
            title = _truncate(_full_title(rendered), TITLE_LIMIT, "title")
            fields = _full_fields(rendered)

        embed: Dict[str, Any] = {
            "author": {"name": rendered.banner},
            "title": title,
            "description": "",
            "color": color,
            "fields": fields,
            "footer": {"text": footer_text},
            "timestamp": timestamp,
        }

        total = _total_embed_length(embed)
        if total > TOTAL_EMBED_LIMIT:
            return {"_payload_too_large": True, "original_length": total}

        return embed


def _full_title(rendered: RenderedAlert) -> str:
    tier_label = rendered.tier_label or "unknown"
    base = f"WOULD_ALERT — {tier_label}"
    if rendered.severity == Severity.PARTIAL:
        return f"{base} [PARTIAL DATA]"
    return base


def _compact_title(rendered: RenderedAlert) -> str:
    decision_type = rendered.decision_type.upper()
    primary_reason = rendered.token_section.get("primary_reason", "unknown")
    return f"{decision_type} — {primary_reason}"


def _full_fields(rendered: RenderedAlert) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    fields.append(_make_field("Token", _section_value(_token_lines(rendered))))
    fields.append(_make_field("Market", _section_value(_market_lines(rendered))))
    fields.append(_make_field("ATH", _section_value(_ath_lines(rendered))))
    fields.append(_make_field("Field", _section_value(_field_lines(rendered))))
    fields.append(_make_field("Clock", _section_value(_clock_lines(rendered))))
    if rendered.missing_section:
        fields.append(_make_field("Missing", _section_value(_missing_lines(rendered))))
    return fields[:MAX_FIELDS]


def _compact_fields(rendered: RenderedAlert) -> List[Dict[str, Any]]:
    fields = [_make_field("Token", _section_value(_token_lines(rendered)))]
    if rendered.missing_section:
        fields.append(_make_field("Missing", _section_value(_missing_lines(rendered))))
    return fields[:MAX_FIELDS]


def _make_field(name: str, value: str) -> Dict[str, Any]:
    truncated_name = _truncate(name, FIELD_NAME_LIMIT, f"field.name[{name}]")
    truncated_value = _truncate(value, FIELD_VALUE_LIMIT, f"field.value[{name}]")
    return {"name": truncated_name, "value": truncated_value, "inline": False}


def _section_value(pairs: List[tuple]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in pairs)


def _token_lines(rendered: RenderedAlert) -> List[tuple]:
    section = rendered.token_section
    return [
        ("Symbol", section.get("symbol", "unknown")),
        ("Address", section.get("address", "unknown")),
        ("Tier", section.get("tier", "unknown")),
        ("Reason", section.get("primary_reason", "unknown")),
    ]


def _market_lines(rendered: RenderedAlert) -> List[tuple]:
    section = rendered.market_section
    return [
        ("Current MC", section.get("current_mc", "unknown")),
        ("Migration MC", section.get("migration_mc", "unknown")),
        ("ATH MC", section.get("ath_mc", "unknown")),
        ("Drawdown", section.get("drawdown", "unknown")),
        ("Pump multiple", section.get("pump_multiple", "unknown")),
        ("Price age", section.get("price_age", "unknown")),
        ("Basis", section.get("calculation_basis", "unknown")),
    ]


def _ath_lines(rendered: RenderedAlert) -> List[tuple]:
    section = rendered.ath_section
    return [
        ("Status", section.get("status", "unknown")),
        ("Confidence", section.get("confidence", "unknown")),
        ("Source", section.get("source", "unknown")),
        ("Event time", section.get("ath_event_time", "unknown")),
    ]


def _field_lines(rendered: RenderedAlert) -> List[tuple]:
    section = rendered.field_section
    if not section:
        return [("(field features unavailable)", "")]
    return [(key, value) for key, value in section.items()]


def _clock_lines(rendered: RenderedAlert) -> List[tuple]:
    section = rendered.clock_section
    return [
        ("Token age", section.get("token_age", "unknown")),
        ("Time since migration", section.get("time_since_migration", "unknown")),
        ("Time since ATH", section.get("time_since_ath", "unknown")),
    ]


def _missing_lines(rendered: RenderedAlert) -> List[tuple]:
    return [(item, "") for item in rendered.missing_section]


def _build_footer_text(rendered: RenderedAlert) -> str:
    decision_id = (
        str(rendered.alert_decision_id)
        if rendered.alert_decision_id is not None
        else "unknown"
    )
    policy_version = rendered.footer.get("policy_version", "unknown")
    return (
        rendered.banner
        + _MIDDLE_DOT
        + f"decision {decision_id}"
        + _MIDDLE_DOT
        + policy_version
    )


def _truncate(value: str, limit: int, label: str) -> str:
    if len(value) <= limit:
        return value
    logger.info(
        "discord_embed_field_truncated",
        extra={"field": label, "original_length": len(value), "limit": limit},
    )
    return value[: limit - 1] + _ELLIPSIS


def _total_embed_length(embed: Dict[str, Any]) -> int:
    total = 0
    title = embed.get("title", "")
    if isinstance(title, str):
        total += len(title)
    description = embed.get("description", "")
    if isinstance(description, str):
        total += len(description)
    for field in embed.get("fields", []):
        total += len(field.get("name", ""))
        total += len(field.get("value", ""))
    footer = embed.get("footer", {})
    if isinstance(footer, dict):
        total += len(footer.get("text", ""))
    return total
