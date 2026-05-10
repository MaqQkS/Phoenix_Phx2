"""Tests for DiscordEmbedAdapter."""

from dataclasses import replace

import pytest

from PHX2.renderers.adapters.discord import (
    COLOR_CLEAN,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_PARTIAL,
    DiscordEmbedAdapter,
    FIELD_VALUE_LIMIT,
    TOTAL_EMBED_LIMIT,
)
from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.rendered_alert import DRY_RUN_BANNER, RenderedAlert, Severity

from PHX2.tests.dispatch._fixtures import (
    make_rendered_alert,
    make_rendered_block,
    make_rendered_error,
    make_rendered_skip,
)
from PHX2.tests.renderers._fixtures import make_full_context


# ---- shape: WOULD_ALERT --------------------------------------------------


def test_would_alert_clean_returns_full_embed_shape():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)

    assert set(embed.keys()) == {
        "author",
        "title",
        "description",
        "color",
        "fields",
        "footer",
        "timestamp",
    }
    assert embed["author"] == {"name": DRY_RUN_BANNER}
    assert embed["title"] == "WOULD_ALERT — T2"
    assert embed["description"] == ""
    assert embed["color"] == COLOR_CLEAN
    assert isinstance(embed["fields"], list)


def test_would_alert_partial_title_includes_partial_data_marker():
    rendered = make_rendered_alert(severity=Severity.PARTIAL)
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["title"] == "WOULD_ALERT — T2 [PARTIAL DATA]"


def test_would_alert_clean_title_has_no_partial_data_marker():
    rendered = make_rendered_alert(severity=Severity.CLEAN)
    embed = DiscordEmbedAdapter().format(rendered)
    assert "[PARTIAL DATA]" not in embed["title"]
    assert embed["title"] == "WOULD_ALERT — T2"


def test_full_embed_contains_all_section_fields():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    field_names = [f["name"] for f in embed["fields"]]
    assert field_names == ["Token", "Market", "ATH", "Field", "Clock"]


def test_missing_field_appears_when_section_non_empty():
    rendered = make_rendered_alert()
    rendered = replace(rendered, missing_section=["price_stale", "ath_unknown"])
    embed = DiscordEmbedAdapter().format(rendered)
    field_names = [f["name"] for f in embed["fields"]]
    assert field_names[-1] == "Missing"
    missing_field = embed["fields"][-1]
    assert "price_stale" in missing_field["value"]
    assert "ath_unknown" in missing_field["value"]


def test_no_missing_field_when_section_empty():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    field_names = [f["name"] for f in embed["fields"]]
    assert "Missing" not in field_names


def test_token_field_value_contains_section_data():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    token_field = next(f for f in embed["fields"] if f["name"] == "Token")
    assert "Symbol: BONKINU" in token_field["value"]
    assert "Tier: T2" in token_field["value"]
    assert "Reason: would_alert" in token_field["value"]


def test_market_field_value_contains_section_data():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    market_field = next(f for f in embed["fields"] if f["name"] == "Market")
    assert "Current MC: $847k" in market_field["value"]
    assert "Drawdown: 70.2%" in market_field["value"]


def test_all_fields_are_not_inline():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    for field in embed["fields"]:
        assert field["inline"] is False


# ---- shape: SKIP / BLOCK / ERROR ----------------------------------------


def test_skip_emits_compact_embed_with_token_and_missing_fields():
    rendered = make_rendered_skip()
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["title"] == "SKIP — price_stale"
    assert embed["description"] == ""
    assert len(embed["fields"]) == 2
    assert embed["fields"][0]["name"] == "Token"
    assert embed["fields"][1]["name"] == "Missing"
    assert "price_stale" in embed["fields"][1]["value"]


def test_block_emits_compact_embed_with_only_token_field():
    # BLOCK fixture has empty missing_section, so no Missing field is added.
    rendered = make_rendered_block()
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["title"] == "BLOCK — policy_disabled"
    assert len(embed["fields"]) == 1
    assert embed["fields"][0]["name"] == "Token"


def test_error_emits_compact_embed_with_token_and_missing_fields():
    rendered = make_rendered_error()
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["title"] == "ERROR — error"
    assert len(embed["fields"]) == 2
    assert embed["fields"][0]["name"] == "Token"
    assert embed["fields"][1]["name"] == "Missing"
    assert "error" in embed["fields"][1]["value"]


def test_compact_decision_with_empty_missing_section_omits_missing_field():
    """Parity with plain-text adapter: when missing_section is empty,
    compact decisions show only the Token field."""
    rendered = make_rendered_skip(missing_section=[])
    embed = DiscordEmbedAdapter().format(rendered)
    assert len(embed["fields"]) == 1
    assert embed["fields"][0]["name"] == "Token"


# ---- banner placement ---------------------------------------------------


def test_dry_run_banner_appears_in_author_and_footer():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    assert DRY_RUN_BANNER in embed["author"]["name"]
    assert DRY_RUN_BANNER in embed["footer"]["text"]


# ---- color mapping ------------------------------------------------------


@pytest.mark.parametrize(
    "severity,expected_color",
    [
        (Severity.CLEAN, COLOR_CLEAN),
        (Severity.PARTIAL, COLOR_PARTIAL),
        (Severity.INFO, COLOR_INFO),
        (Severity.ERROR, COLOR_ERROR),
    ],
)
def test_color_matches_severity(severity, expected_color):
    if severity == Severity.INFO:
        rendered = make_rendered_skip()
    elif severity == Severity.ERROR:
        rendered = make_rendered_error()
    else:
        rendered = make_rendered_alert(severity=severity)
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["color"] == expected_color


# ---- timestamp ----------------------------------------------------------


def test_timestamp_matches_rendered_footer_evaluated_at():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed["timestamp"] == rendered.footer["evaluated_at"]
    # ISO 8601 UTC sanity check
    assert "T" in embed["timestamp"]
    assert "+00:00" in embed["timestamp"] or embed["timestamp"].endswith("Z")


# ---- footer text --------------------------------------------------------


def test_footer_includes_decision_id_when_set():
    rendered = make_rendered_alert(alert_decision_id=42)
    embed = DiscordEmbedAdapter().format(rendered)
    assert "decision 42" in embed["footer"]["text"]


def test_footer_includes_decision_unknown_when_id_none():
    rendered = make_rendered_alert(alert_decision_id=None)
    embed = DiscordEmbedAdapter().format(rendered)
    assert "decision unknown" in embed["footer"]["text"]


def test_footer_uses_middle_dot_separators():
    rendered = make_rendered_alert(alert_decision_id=7)
    embed = DiscordEmbedAdapter().format(rendered)
    # Middle dot (U+00B7) between banner, decision, and policy_version.
    assert " · " in embed["footer"]["text"]
    assert embed["footer"]["text"].count(" · ") == 2


def test_footer_includes_policy_version():
    rendered = make_rendered_alert()
    embed = DiscordEmbedAdapter().format(rendered)
    assert rendered.footer["policy_version"] in embed["footer"]["text"]


# ---- truncation ---------------------------------------------------------


def test_oversized_field_value_is_truncated_to_limit():
    rendered = make_rendered_alert()
    long_symbol = "A" * 2000
    rendered = replace(
        rendered,
        token_section={**rendered.token_section, "symbol": long_symbol},
    )
    embed = DiscordEmbedAdapter().format(rendered)
    token_field = next(f for f in embed["fields"] if f["name"] == "Token")
    assert len(token_field["value"]) == FIELD_VALUE_LIMIT
    assert token_field["value"].endswith("…")


def test_total_embed_exceeding_six_thousand_returns_payload_too_large_marker():
    rendered = make_rendered_alert()
    # Each individual section truncates to FIELD_VALUE_LIMIT (1024 chars).
    # Six fields at the limit gives roughly 6,144 chars in field values
    # alone — past the 6000 total-embed cap.
    huge_value = "X" * (FIELD_VALUE_LIMIT - 20)
    rendered = replace(
        rendered,
        token_section={**rendered.token_section, "address": huge_value},
        market_section={
            **rendered.market_section,
            "current_mc": huge_value,
            "ath_mc": huge_value,
        },
        ath_section={**rendered.ath_section, "source": huge_value},
        field_section={**rendered.field_section, "lp_floor_label": huge_value},
        clock_section={**rendered.clock_section, "token_age": huge_value},
        missing_section=[huge_value],
    )
    embed = DiscordEmbedAdapter().format(rendered)
    assert embed.get("_payload_too_large") is True
    assert isinstance(embed.get("original_length"), int)
    assert embed["original_length"] > TOTAL_EMBED_LIMIT


# ---- determinism --------------------------------------------------------


def test_format_is_deterministic_byte_identical():
    rendered = make_rendered_alert()
    a = DiscordEmbedAdapter().format(rendered)
    b = DiscordEmbedAdapter().format(rendered)
    assert a == b


def test_format_is_deterministic_for_compact_decision():
    rendered = make_rendered_skip()
    a = DiscordEmbedAdapter().format(rendered)
    b = DiscordEmbedAdapter().format(rendered)
    assert a == b


# ---- purity: no clock reads --------------------------------------------


def test_adapter_does_not_call_datetime_now():
    """Static check: the adapter source contains no clock calls."""

    import inspect

    import PHX2.renderers.adapters.discord as module

    source = inspect.getsource(module)
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "time.time" not in source
    assert "time.monotonic" not in source


def test_adapter_does_not_break_when_called_with_renderer_output():
    """Sanity: the adapter accepts what AlertRenderer produces."""

    rendered = AlertRenderer().render(make_full_context())
    embed = DiscordEmbedAdapter().format(rendered)
    assert isinstance(embed, dict)
    # When the rendered alert isn't oversized, we expect a real embed.
    assert "_payload_too_large" not in embed
    assert embed["title"].startswith("WOULD_ALERT")
