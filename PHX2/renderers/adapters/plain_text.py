"""Plain-text adapter for :class:`PHX2.renderers.rendered_alert.RenderedAlert`.

The adapter is a pure function over a :class:`RenderedAlert`. It performs no
I/O, never reads the clock, and never raises. The dry-run banner is rendered
at both the top and bottom of every output.

Layout for ``WOULD_ALERT`` includes Token, Market, ATH, Field, Clock and (when
non-empty) Missing sections. Compact decisions (``SKIP``, ``BLOCK``,
``ERROR``) drop everything except Token, Missing (if any), and Policy/Decision
metadata.
"""

from typing import Iterable, List

from PHX2.renderers.rendered_alert import RenderedAlert


_COMPACT_TYPES = frozenset({"skip", "block", "error"})


class PlainTextAdapter:
    """Format a :class:`RenderedAlert` as a single string."""

    def format(self, rendered: RenderedAlert) -> str:
        lines: List[str] = []
        lines.append(rendered.banner)
        lines.append(rendered.headline)
        lines.append("")

        lines.extend(_format_section("Token", _format_token_lines(rendered)))

        if rendered.decision_type.lower() not in _COMPACT_TYPES:
            lines.extend(_format_section("Market", _format_market_lines(rendered)))
            lines.extend(_format_section("ATH", _format_ath_lines(rendered)))
            lines.extend(_format_section("Field", _format_field_lines(rendered)))
            lines.extend(_format_section("Clock", _format_clock_lines(rendered)))

        if rendered.missing_section:
            lines.extend(
                _format_section(
                    "Missing", [f"- {item}" for item in rendered.missing_section]
                )
            )

        lines.extend(_format_footer(rendered))

        lines.append(rendered.banner)
        return "\n".join(lines)


def _format_section(header: str, body_lines: Iterable[str]) -> List[str]:
    body = list(body_lines)
    if not body:
        return []
    return [f"{header}:", *body, ""]


def _format_token_lines(rendered: RenderedAlert) -> List[str]:
    section = rendered.token_section
    return [
        f"- Symbol: {section.get('symbol', 'unknown')}",
        f"- Address: {section.get('address', 'unknown')}",
        f"- Tier: {section.get('tier', 'unknown')}",
        f"- Reason: {section.get('primary_reason', 'unknown')}",
    ]


def _format_market_lines(rendered: RenderedAlert) -> List[str]:
    section = rendered.market_section
    return [
        f"- Current MC:    {section.get('current_mc', 'unknown')}",
        f"- Migration MC:  {section.get('migration_mc', 'unknown')}",
        f"- ATH MC:        {section.get('ath_mc', 'unknown')}",
        f"- Drawdown:      {section.get('drawdown', 'unknown')}",
        f"- Pump multiple: {section.get('pump_multiple', 'unknown')}",
        f"- Price age:     {section.get('price_age', 'unknown')}",
        f"- Basis:         {section.get('calculation_basis', 'unknown')}",
    ]


def _format_ath_lines(rendered: RenderedAlert) -> List[str]:
    section = rendered.ath_section
    return [
        f"- Status:     {section.get('status', 'unknown')}",
        f"- Confidence: {section.get('confidence', 'unknown')}",
        f"- Source:     {section.get('source', 'unknown')}",
        f"- Event time: {section.get('ath_event_time', 'unknown')}",
    ]


def _format_field_lines(rendered: RenderedAlert) -> List[str]:
    section = rendered.field_section
    if not section:
        return ["- (field features unavailable)"]
    return [f"- {key}: {value}" for key, value in section.items()]


def _format_clock_lines(rendered: RenderedAlert) -> List[str]:
    section = rendered.clock_section
    return [
        f"- Token age:            {section.get('token_age', 'unknown')}",
        f"- Time since migration: {section.get('time_since_migration', 'unknown')}",
        f"- Time since ATH:       {section.get('time_since_ath', 'unknown')}",
    ]


def _format_footer(rendered: RenderedAlert) -> List[str]:
    footer = rendered.footer
    decision_id_str = (
        str(rendered.alert_decision_id)
        if rendered.alert_decision_id is not None
        else "unknown"
    )
    return [
        f"Policy:       {footer.get('policy_version', 'unknown')}",
        f"Decision:     {decision_id_str}",
        f"Evaluated at: {footer.get('evaluated_at', 'unknown')}",
    ]
