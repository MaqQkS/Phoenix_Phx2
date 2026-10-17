from __future__ import annotations

from dataclasses import replace

import pytest

from PHX2.delivery.telegram_adapter import (
    TOKEN_METADATA_CANONICAL_LIVE,
    TOKEN_METADATA_DEX_BACKFILL,
    TOKEN_METADATA_UNAVAILABLE,
    TOKEN_METADATA_VALIDATED_CACHE,
    UNKNOWN_TOKEN_DISPLAY,
    format_age_minutes,
    resolve_token_identity,
)
from PHX2.delivery.telegram_composer import (
    FIELD_AVAILABLE,
    FIELD_HIDDEN_INTERNAL,
    TELEGRAM_INTERNAL_MAX_CHARACTERS,
    BuilderReadStatement,
    TelegramMessageTooLong,
    TelegramPingData,
    compose_telegram_ping,
)


MINT = "DC4sure5XanGz2Te2UNPAKR2iAkshzYqvsv3coH4pump"


def _sample() -> TelegramPingData:
    return TelegramPingData(
        token_mint=MINT,
        token_identity="Phoenix Test ($PHX)",
        token_metadata_source="TEST_FIXTURE",
        age_minutes=22,
        age_display="22m",
        tier=3,
        market_cap="$10k",
        post_migration_ath="$57k",
        migration_market_cap="$32k",
        floor="-82%",
        volume="$2.7k gross | -$843 net (n=48)",
        liquidity="$7k",
        quote_side_liquidity="$3.5k",
        liquidity_basis="TOTAL_ACTUAL_POOL_TVL",
        liquidity_quality="Low",
        fee_gate_label="Elevated",
        fee_gate_score="1",
        lp_integrity="PASS",
        composite_verdict="PASS",
        bribes_amm_pct="5.21%",
        creator_pct="52.2%",
        bribes_per_tx_lamports="278,478",
        structure_read="sticky lock",
        ante_last20_median="0.000005",
        ante_last20_p25="0.000005",
        ante_last20_p75="0.000167",
        ante_5m_median="0.000046",
        ante_5m_sample_count="134",
        base_fee_coverage="100%",
        ante_last20_width="32.1",
        ante_5m_width="58.1",
        priority_fee_median_lamports="7,074",
        priority_fee_sample_count="20",
        shape_5m="ORGANIC",
        shape_5m_rule="5",
        shape_last20="AMBIGUOUS",
        shape_last20_rule="6",
        risk_warning="Medium — LP falling",
        builder_read=(
            BuilderReadStatement(
                "Late-sequence stress state", ("FEE_GATE_STICKY_LOCK",)),
            BuilderReadStatement(
                "Attention present, structure requires caution",
                ("EVENT_PACE_ATTENTION_PRESENT", "FEE_GATE_ELEVATED"),
            ),
            BuilderReadStatement(
                "Pool is highly fragile, collapse risk is severe",
                ("LIQUIDITY_BELOW_10000", "ATH_DRAWDOWN_AT_LEAST_70_PERCENT"),
            ),
        ),
    )


GOLDEN = """<b>🔥 PHOENIX — Phoenix Test ($PHX) [Tier 3]</b>
<code>DC4sure5XanGz2Te2UNPAKR2iAkshzYqvsv3coH4pump</code>

<b>🧠 State</b>
• MC: $10k | Post-mig ATH: $57k | Mig: $32k
• Floor: -82% | Age: 22m | Vol 5m: $2.7k gross | -$843 net (n=48)
• LP: $7k

<b>🛑 Structure</b>
• Fee Gate: Elevated (1)
• Risk: Medium — LP falling
• Bribes/AMM: 5.21% | Creator: 52.2% | Bribes/tx: 278,478 lamports
• Read: sticky lock

<b>🎲 Ante (observe-only)</b>
• Median last-20sw: 0.000005 SOL | p25/p75: 0.000005 / 0.000167
• Median 5m: 0.000046 SOL (n=134) | base-fee cov: 100%
• Width: last20 32.1× | 5m 58.1×
⛽️ Priority Fee: 7,074 lam (n=20)
• Shape (5m): ORGANIC (rule 5)
• Shape (20sw): AMBIGUOUS (rule 6)

<b>🏗️ Builder Read</b>
• Late-sequence stress state
• Attention present, structure requires caution
• Pool is highly fragile, collapse risk is severe"""


def test_exact_golden_html_format_and_reason_mapping():
    result = compose_telegram_ping(_sample())
    assert result.text == GOLDEN
    assert result.text.splitlines()[1] == f"<code>{MINT}</code>"
    assert result.rendered_character_count < TELEGRAM_INTERNAL_MAX_CHARACTERS
    assert result.builder_reason_map == {
        "Late-sequence stress state": ("FEE_GATE_STICKY_LOCK",),
        "Attention present, structure requires caution": (
            "EVENT_PACE_ATTENTION_PRESENT", "FEE_GATE_ELEVATED"),
        "Pool is highly fragile, collapse risk is severe": (
            "LIQUIDITY_BELOW_10000", "ATH_DRAWDOWN_AT_LEAST_70_PERCENT"),
    }
    # Participation renders nowhere (2026-07-29 final cleanup).
    assert "Participation" not in result.text
    assert "SOL/min" not in result.text
    assert "Events:" not in result.text
    assert result.field_presentation["fee_gate"] == FIELD_AVAILABLE
    assert result.field_presentation["fee_breakdown"] == FIELD_AVAILABLE


def test_dynamic_values_are_html_escaped():
    value = "$2.7k <gross> & 'net'"
    result = compose_telegram_ping(replace(
        _sample(), volume=value,
        builder_read=(BuilderReadStatement(
            "Attention & <focus> present", ("EXPLICIT_REASON",)),),
        field_reason_codes={"volume": ("EXPLICIT_REASON",)},
    ))
    assert value not in result.text
    assert "$2.7k &lt;gross&gt; &amp; &#x27;net&#x27;" in result.text
    assert "Attention &amp; &lt;focus&gt; present" in result.text
    assert result.field_reason_codes == {"volume": ("EXPLICIT_REASON",)}


def test_internal_fallback_value_is_suppressed_not_rendered():
    """The presentation boundary: an ``UNKNOWN (...)`` fallback nested in a
    field value never renders — the line keeps the unavailable marker and the
    classification is recorded."""

    result = compose_telegram_ping(replace(
        _sample(),
        volume="UNKNOWN (CANONICAL_SWAP_SAMPLE_INSUFFICIENT)",
    ))
    assert "UNKNOWN" not in result.text
    assert "CANONICAL_SWAP_SAMPLE_INSUFFICIENT" not in result.text
    assert "Vol 5m: —" in result.text
    assert result.field_presentation["volume"] == FIELD_HIDDEN_INTERNAL


def test_over_limit_message_fails_in_composer_before_transport():
    with pytest.raises(TelegramMessageTooLong, match="^MESSAGE_TOO_LONG$"):
        compose_telegram_ping(replace(
            _sample(),
            builder_read=(BuilderReadStatement("x" * 3900, ("TEST_LONG",)),),
        ))


# ---------------------------------------------------------------------------
# 2026-07-28 alert-quality remediation: clean operator presentation contract.
# ---------------------------------------------------------------------------


def test_unavailable_volume_and_lp_render_as_dash_without_internal_reasons():
    result = compose_telegram_ping(replace(
        _sample(),
        volume="—",
        liquidity="—",
        quote_side_liquidity="—",
        liquidity_basis="UNAVAILABLE",
        field_reason_codes={
            "volume": ("CANONICAL_SWAP_SAMPLE_INSUFFICIENT",),
            "liquidity": ("FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",),
            "quote_side_liquidity": (
                "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",),
        },
    ))
    assert "Vol 5m: —" in result.text.splitlines()[5]
    assert "• LP: —" in result.text
    # Internal reason strings and diagnostic duplication stay artifact-only.
    assert "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE" not in result.text
    assert "CANONICAL_SWAP_SAMPLE_INSUFFICIENT" not in result.text
    assert "DATA UNAVAILABLE" not in result.text
    assert "INSUFFICIENT DATA" not in result.text
    assert "Quote-side" not in result.text
    assert "LP Quality" not in result.text
    assert "TOTAL_ACTUAL_POOL_TVL" not in result.text
    assert "[UNAVAILABLE]" not in result.text
    # The reason codes survive on the artifact surface.
    assert result.field_reason_codes["liquidity"] == (
        "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",)


def test_shape_placeholder_lines_are_hidden_but_reasons_survive():
    result = compose_telegram_ping(replace(
        _sample(),
        shape_5m="NO APPROVED SHAPE RULE",
        shape_5m_rule="N/A",
        shape_last20="INSUFFICIENT SAMPLE",
        shape_last20_rule="N/A",
        field_reason_codes={
            "shape_5m": ("NO_APPROVED_ANTE_SHAPE_RULE",),
            "shape_last20": ("ANTE_SHAPE_SAMPLE_INSUFFICIENT",),
        },
    ))
    assert "Shape" not in result.text
    assert "NO APPROVED SHAPE RULE" not in result.text
    assert "rule N/A" not in result.text
    assert result.field_reason_codes["shape_5m"] == (
        "NO_APPROVED_ANTE_SHAPE_RULE",)


def test_lp_integrity_and_composite_are_artifact_only():
    """2026-07-29 final cleanup: internal subsystem status lines never render
    in Structure; the values stay on the data/artifact surface."""

    for lp_integrity, composite in (
        ("DISABLED", "PASS"),
        ("PASS", "PASS"),
        ("DISABLED", "BLOCKED"),
    ):
        data = replace(
            _sample(), lp_integrity=lp_integrity,
            composite_verdict=composite)
        result = compose_telegram_ping(data)
        assert "LP Integrity" not in result.text
        assert "Composite" not in result.text
        assert data.lp_integrity == lp_integrity
        assert data.composite_verdict == composite


def test_empty_risk_display_omits_the_risk_line():
    result = compose_telegram_ping(replace(_sample(), risk_warning=""))
    assert "• Risk:" not in result.text


def test_raw_risk_enum_never_renders():
    result = compose_telegram_ping(replace(
        _sample(), risk_warning="RISK_MEDIUM — LP falling"))
    assert "RISK_MEDIUM" not in result.text
    assert "• Risk:" not in result.text
    assert result.field_presentation["risk"] == FIELD_HIDDEN_INTERNAL


def test_shadow_block_renders_one_compact_policy_line_inside_structure():
    result = compose_telegram_ping(replace(
        _sample(),
        risk_warning="",
        phx1_structural_policy_mode="SHADOW",
        original_phx1_structural_verdict="HARD_BLOCK",
        effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
        shadow_warning_reasons=(
            "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK",
            "PHX1_FEE_GATE_SCAM_LIKELY",
        ),
        organicity_status="UNVERIFIED",
        manual_review_required=True,
        policy_reason_display="durable scam lock",
    ))
    lines = result.text.splitlines()
    assert "• Policy: SHADOW BLOCK — durable scam lock" in lines
    policy_index = lines.index("• Policy: SHADOW BLOCK — durable scam lock")
    read_index = lines.index("• Read: sticky lock")
    assert policy_index == read_index + 1
    # The old multi-line internal block never renders.
    assert "PHX1 STRUCTURAL POLICY" not in result.text
    assert "ORIGINAL STRUCTURAL VERDICT" not in result.text
    assert "SHADOW REASONS" not in result.text
    assert "ORGANICITY" not in result.text
    assert "MANUAL REVIEW REQUIRED" not in result.text
    assert "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK" not in result.text


def test_pass_result_has_no_policy_footer_at_all():
    result = compose_telegram_ping(_sample())
    assert "Policy:" not in result.text
    assert "PHX1 STRUCTURAL POLICY" not in result.text


def test_partial_coverage_renders_compact_coverage_line_and_obs_ath_label():
    result = compose_telegram_ping(replace(
        _sample(),
        discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
        ath_coverage="PARTIAL_SINCE_ADMISSION",
    ))
    lines = result.text.splitlines()
    assert "• Coverage: Partial (restart backfill)" in lines
    assert "Obs ATH: $57k" in result.text
    assert "Post-mig ATH" not in result.text
    # The internal enum/schema tokens and provider name stay artifact-only.
    assert "PARTIAL_SINCE_ADMISSION" not in result.text
    assert "DEXSCREENER" not in result.text
    assert "RESTART_BACKFILL" not in result.text
    assert "ATH coverage" not in result.text
    assert "true post-mig drawdown" not in result.text


def test_complete_live_coverage_has_no_coverage_line():
    result = compose_telegram_ping(_sample())
    assert "Coverage:" not in result.text
    assert "Post-mig ATH: $57k" in result.text


def _backfill_candidate(**updates):
    candidate = {
        "token_mint": MINT,
        "pair_address": "Pair111",
        "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
        "token_name": "NOngWAn",
        "symbol_or_name": "WAN",
    }
    candidate.update(updates)
    return candidate


def test_nongwan_title_and_111_minute_age_are_exact():
    rendered = compose_telegram_ping(replace(
        _sample(),
        token_identity="NOngWAn ($WAN)",
        token_metadata_source=TOKEN_METADATA_DEX_BACKFILL,
        age_minutes=111,
        age_display=format_age_minutes(111),
        tier=1,
    )).text
    assert rendered.splitlines()[0] == (
        "<b>🔥 PHOENIX — NOngWAn ($WAN) [Tier 1]</b>")
    assert "Age: 1h 51m" in rendered
    assert "111M" not in rendered
    assert rendered.splitlines()[1] == f"<code>{MINT}</code>"


@pytest.mark.parametrize(
    "minutes,expected",
    [(7, "7m"), (59, "59m"), (111, "1h 51m"), (120, "2h"),
     (1620, "1d 3h")],
)
def test_age_format_is_unambiguous(minutes, expected):
    assert format_age_minutes(minutes) == expected
    assert "M" not in expected


def test_metadata_precedence_and_exact_mint_binding():
    candidate = _backfill_candidate()
    identity, source = resolve_token_identity(
        mint=MINT,
        candidate=candidate,
        delivery_context={
            "canonical_token_metadata": {
                "token_mint": MINT,
                "token_name": "Canonical",
                "symbol": "CAN",
                "authenticated": True,
            },
            "validated_metadata_cache": {
                MINT: {
                    "token_mint": MINT,
                    "name": "Cached",
                    "ticker": "CCH",
                    "validated": True,
                },
            },
        },
    )
    assert (identity, source) == (
        "Canonical ($CAN)", TOKEN_METADATA_CANONICAL_LIVE)

    identity, source = resolve_token_identity(
        mint=MINT,
        candidate=candidate,
        delivery_context={},
    )
    assert (identity, source) == (
        "NOngWAn ($WAN)", TOKEN_METADATA_DEX_BACKFILL)

    other_mint = "Other111111111111111111111111111111111111111"
    identity, source = resolve_token_identity(
        mint=MINT,
        candidate=_backfill_candidate(token_mint=other_mint),
        delivery_context={
            "canonical_token_metadata": {
                "token_mint": other_mint,
                "token_name": "Wrong",
                "symbol": "BAD",
                "authenticated": True,
            },
        },
    )
    assert (identity, source) == (
        UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE)


def test_candidate_level_canonical_metadata_resolves_for_live_provenance():
    """The producer stamps ``canonical_token_metadata`` on the candidate; the
    adapter must consume it at highest precedence even when the raw candidate
    fields are empty (the exact 335Sdx… failure shape)."""

    candidate = {
        "token_mint": MINT,
        "discovery_provenance": "LIVE_YELLOWSTONE",
        "symbol_or_name": None,
        "token_name": None,
        "canonical_token_metadata": {
            "token_mint": MINT,
            "token_name": "Live Named",
            "token_symbol": "LIVE",
            "metadata_status": "RESOLVED",
            "validated": True,
        },
    }
    identity, source = resolve_token_identity(
        mint=MINT, candidate=candidate, delivery_context={})
    assert (identity, source) == (
        "Live Named ($LIVE)", TOKEN_METADATA_CANONICAL_LIVE)


def test_stale_candidate_snapshot_cannot_override_enriched_canonical_state():
    candidate = _backfill_candidate(
        token_name="Stale Old Name",
        symbol_or_name="OLD",
        canonical_token_metadata={
            "token_mint": MINT,
            "token_name": "Enriched",
            "token_symbol": "NEW",
            "validated": True,
        },
    )
    identity, source = resolve_token_identity(
        mint=MINT, candidate=candidate, delivery_context={})
    assert (identity, source) == (
        "Enriched ($NEW)", TOKEN_METADATA_CANONICAL_LIVE)


def test_backfill_requires_exact_provenance_and_cache_requires_pair_match():
    wrong_provenance = _backfill_candidate(discovery_provenance="UNTRUSTED")
    identity, source = resolve_token_identity(
        mint=MINT,
        candidate=wrong_provenance,
        delivery_context={},
    )
    assert (identity, source) == (
        UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE)

    identity, source = resolve_token_identity(
        mint=MINT,
        candidate=wrong_provenance,
        delivery_context={
            "validated_metadata_cache": {
                MINT: {
                    "token_mint": MINT,
                    "name": "Cached",
                    "ticker": "CCH",
                    "pair_address": "Pair111",
                    "validated": True,
                },
            },
        },
    )
    assert (identity, source) == (
        "Cached ($CCH)", TOKEN_METADATA_VALIDATED_CACHE)

    mismatch, mismatch_source = resolve_token_identity(
        mint=MINT,
        candidate=wrong_provenance,
        delivery_context={
            "validated_metadata_cache": {
                MINT: {
                    "token_mint": MINT,
                    "name": "Wrong Pool",
                    "ticker": "BAD",
                    "pair_address": "Pair999",
                    "validated": True,
                },
            },
        },
    )
    assert (mismatch, mismatch_source) == (
        UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE)


@pytest.mark.parametrize(
    "name,ticker,expected",
    [
        ("Name Only", None, "Name Only"),
        (None, "TICK", "$TICK"),
        (None, None, UNKNOWN_TOKEN_DISPLAY),
        ("น้องวัน", "WAN", "น้องวัน ($WAN)"),
    ],
)
def test_metadata_fallbacks_and_unicode(name, ticker, expected):
    candidate = _backfill_candidate(token_name=name, symbol_or_name=ticker)
    identity, _source = resolve_token_identity(
        mint=MINT, candidate=candidate, delivery_context={})
    assert identity == expected


def test_unknown_token_title_is_operator_cased():
    rendered = compose_telegram_ping(replace(
        _sample(),
        token_identity=UNKNOWN_TOKEN_DISPLAY,
        token_metadata_source=TOKEN_METADATA_UNAVAILABLE,
    )).text
    assert rendered.splitlines()[0] == (
        f"<b>🔥 PHOENIX — {UNKNOWN_TOKEN_DISPLAY} [Tier 3]</b>")
    assert "UNKNOWN TOKEN" not in rendered


def test_ticker_prefix_is_normalized_to_single_dollar():
    candidate = _backfill_candidate(symbol_or_name="$$WAN")
    identity, _source = resolve_token_identity(
        mint=MINT, candidate=candidate, delivery_context={})
    assert identity == "NOngWAn ($WAN)"


def test_metadata_is_control_stripped_bounded_single_line_and_html_escaped():
    candidate = _backfill_candidate(
        token_name="<b>NO\nng\\u0000WAn</b>" + ("X" * 100),
        symbol_or_name="W\tA\rN&" + ("Y" * 100),
    )
    identity, source = resolve_token_identity(
        mint=MINT, candidate=candidate, delivery_context={})
    assert source == TOKEN_METADATA_DEX_BACKFILL
    assert "\n" not in identity and "\r" not in identity and "\t" not in identity
    name, ticker = identity.rsplit(" ($", 1)
    assert len(name) <= 64
    assert len(ticker.removesuffix(")")) <= 16

    text = compose_telegram_ping(replace(
        _sample(),
        token_identity=identity,
        token_metadata_source=source,
    )).text
    title = text.splitlines()[0]
    assert "&lt;b&gt;" in title and "&amp;" in title
    assert title.count("\n") == 0
    assert "<b>NO" not in title


def test_title_metadata_is_not_a_dedupe_or_ledger_identity_axis():
    from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
        Stage30_11_15PingDedupeKey,
        canonical_ping_dedupe_key_tuple,
        ping_dedupe_key_field_names,
    )

    key = Stage30_11_15PingDedupeKey(
        token_mint=MINT,
        operator_signal_kind="PHOENIX_OPERATOR_DIP_PING",
        tier_token="Tier 1",
        drawdown_band="DD_BAND_50",
        post_migration_ath_verified=True,
        ath_source_stage="central_ath_v1",
        policy_version="stage30_11_15_v0",
    )
    before = canonical_ping_dedupe_key_tuple(key)
    compose_telegram_ping(replace(
        _sample(), token_identity="Changed Display ($NEW)"))
    after = canonical_ping_dedupe_key_tuple(key)
    assert before == after
    assert "token_identity" not in ping_dedupe_key_field_names()
    assert "token_metadata_source" not in ping_dedupe_key_field_names()
