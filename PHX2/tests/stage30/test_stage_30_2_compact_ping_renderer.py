"""Stage 30.2 compact ping renderer tests.

Pure read-only tests over the Stage 30.2 renderer's body shape,
display fallback rules, warning emission rules, caller-shape
errors, determinism, and body-length / forbidden-substring
invariants.

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

from typing import Optional

import pytest

from PHX2.stage30.compact_ping_models import (
    CompactPingInputRecord,
    CompactPingSnapshotRecord,
    DISPLAY_UNKNOWN,
    STAGE30_2_BODY_CHAR_HARD_CAP,
    STAGE30_2_BODY_CHAR_TARGET,
    STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
    Stage30_2CompactPingError,
)
from PHX2.stage30.compact_ping_renderer import render_compact_ping
from PHX2.stage30.tier_decision_models import (
    BASIS_MC,
    BASIS_PRICE,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    TIER_REASON_NA_MIGRATION_MISSING,
    TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
    TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
    TIER_REASON_NA_MIGRATION_UNTRUSTED,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
    TIER_REASON_UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
    TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
    TIER_REASON_UNKNOWN_GRAVEYARD,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN,
    TierDecisionRecord,
)


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------
#
# ``_SAFE_MINT`` is a FAKE, valid-shape, non-WSOL Solana base58
# token / base mint. The renderer must echo it verbatim; it must
# NEVER substitute the WSOL / quote mint (which is what a buggy
# Stage 30.3+ wiring could conceivably do if it grabbed the
# quote_mint slot instead of the token_mint slot).
#
# ``_WSOL_MINT`` is the real wrapped-SOL quote mint and is used by
# the regression tests below to confirm the renderer never injects
# it on its own.


_SAFE_MINT: str = (
    "PHXTestM1ntFakeBase58NotWSL12345678912345678"
)
_WSOL_MINT: str = (
    "So11111111111111111111111111111111111111112"
)
_SAFE_MINT_SHORT: str = "PHXT…5678"


_SAFE_CREATED_AT: str = "2026-05-27T12:00:00Z"


def _make_tier_decision(**overrides: object) -> TierDecisionRecord:
    defaults: dict = {
        "schema_version": STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        "session_id": None,
        "ping_id": None,
        "candidate_id": None,
        "mint": _SAFE_MINT,
        "basis": BASIS_PRICE,
        "drawdown_from_ath_raw": "0.55",
        "drop_positive": "0.55",
        "ath_status": "PRESENT",
        "ath_since_migration_status": "POST_MIGRATION_ONLY",
        "migration_status": "PRESENT",
        "tier_token": TIER_TOKEN_TIER_1,
        "tier_reason": TIER_REASON_TIER_1_IN_BAND,
        "created_at_utc": _SAFE_CREATED_AT,
    }
    defaults.update(overrides)
    return TierDecisionRecord(**defaults)


def _make_input(
    tier_decision: Optional[TierDecisionRecord] = None,
    **overrides: object,
) -> CompactPingInputRecord:
    defaults: dict = {
        "tier_decision": (
            tier_decision
            if tier_decision is not None
            else _make_tier_decision()
        ),
        "mint": _SAFE_MINT,
        "symbol": None,
        "current_mc_text": None,
        "ath_mc_text": None,
        "migration_mc_text": None,
        "lp_text": None,
        "net_flow_text": None,
        "age_since_migration_seconds": 59760,
        "price_status": "PRESENT",
        "session_id": "sess-001",
        "ping_id": "ping-001",
        "candidate_id": "cand-001",
        "created_at_utc": _SAFE_CREATED_AT,
    }
    defaults.update(overrides)
    return CompactPingInputRecord(**defaults)


# ---------------------------------------------------------------------------
# Golden body: Tier 1 (in-band, all display text None)
# ---------------------------------------------------------------------------


_GOLDEN_TIER_1_BODY: str = (
    "\U0001f525 PHOENIX — PHXT…5678 [Tier 1]\n"
    "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
    "\n"
    "\U0001f9e0 State\n"
    "• MC: Unknown | ATH: Unknown | Mig: Unknown\n"
    "• Drop: -55% | Age: 16.6h | Net: Unknown\n"
    "• LP: Unknown\n"
    "• Basis: price-basis"
)


def test_tier_1_golden_body() -> None:
    snapshot = render_compact_ping(_make_input())
    assert snapshot.body_text == _GOLDEN_TIER_1_BODY
    assert snapshot.tier_token == TIER_TOKEN_TIER_1
    assert snapshot.tier_reason == TIER_REASON_TIER_1_IN_BAND
    assert snapshot.basis == BASIS_PRICE
    assert snapshot.warnings == ()
    assert snapshot.body_length_chars == len(_GOLDEN_TIER_1_BODY)
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_TARGET


# ---------------------------------------------------------------------------
# Golden body: Tier 2 (in-band, with display text)
# ---------------------------------------------------------------------------


_GOLDEN_TIER_2_BODY: str = (
    "\U0001f525 PHOENIX — PUMP [Tier 2]\n"
    "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
    "\n"
    "\U0001f9e0 State\n"
    "• MC: $83k | ATH: $460k | Mig: $36k\n"
    "• Drop: -62% | Age: 16.6h | Net: Unknown\n"
    "• LP: $27k\n"
    "• Basis: price-basis"
)


def test_tier_2_golden_body() -> None:
    # Stage 30.2 has no net-flow source yet, so callers pass
    # ``net_flow_text=None`` and the renderer emits ``Net: Unknown``
    # even when every other display field is supplied. The eventual
    # Net language ("+$12k buys" / "-$8k sells") is intentionally
    # deferred until a net-flow source ships, because the literal
    # substrings ``BUY`` / ``SELL`` are on the Stage 30.2 forbidden
    # trading-verdict needle set (the future net-flow source either
    # picks alternative phrasing or the discipline is amended via a
    # separately authorized spec-lock change).
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_2,
        tier_reason=TIER_REASON_TIER_2_IN_BAND,
        drawdown_from_ath_raw="0.62",
        drop_positive="0.62",
    )
    snapshot = render_compact_ping(
        _make_input(
            tier_decision=td,
            symbol="PUMP",
            current_mc_text="$83k",
            ath_mc_text="$460k",
            migration_mc_text="$36k",
            lp_text="$27k",
            net_flow_text=None,
        )
    )
    assert snapshot.body_text == _GOLDEN_TIER_2_BODY
    assert snapshot.tier_token == TIER_TOKEN_TIER_2
    assert snapshot.tier_reason == TIER_REASON_TIER_2_IN_BAND
    assert snapshot.warnings == ()
    assert snapshot.symbol == "PUMP"
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_TARGET


# ---------------------------------------------------------------------------
# Golden body: Tier 3 (in-band, with symbol, no display text)
# ---------------------------------------------------------------------------


_GOLDEN_TIER_3_BODY: str = (
    "\U0001f525 PHOENIX — DOG [Tier 3]\n"
    "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
    "\n"
    "\U0001f9e0 State\n"
    "• MC: Unknown | ATH: Unknown | Mig: Unknown\n"
    "• Drop: -95% | Age: 16.6h | Net: Unknown\n"
    "• LP: Unknown\n"
    "• Basis: price-basis"
)


def test_tier_3_golden_body() -> None:
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_3,
        tier_reason=TIER_REASON_TIER_3_IN_BAND,
        drawdown_from_ath_raw="0.95",
        drop_positive="0.95",
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, symbol="DOG")
    )
    assert snapshot.body_text == _GOLDEN_TIER_3_BODY
    assert snapshot.tier_token == TIER_TOKEN_TIER_3
    assert snapshot.warnings == ()
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_TARGET


# ---------------------------------------------------------------------------
# Golden body: Tier Unknown (in-gap T1-T2, warning fires)
# ---------------------------------------------------------------------------


_GOLDEN_TIER_UNKNOWN_BODY: str = (
    "\U0001f525 PHOENIX — PHXT…5678 [Tier Unknown]\n"
    "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
    "\n"
    "\U0001f9e0 State\n"
    "• MC: Unknown | ATH: Unknown | Mig: Unknown\n"
    "• Drop: -61% | Age: 16.6h | Net: Unknown\n"
    "• LP: Unknown\n"
    "• Basis: price-basis\n"
    "\n"
    "⚠ Notes\n"
    "• Tier Unknown: in gap (T1-T2)"
)


def test_tier_unknown_golden_body() -> None:
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_UNKNOWN,
        tier_reason=TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
        drawdown_from_ath_raw="0.61",
        drop_positive="0.61",
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status=None)
    )
    assert snapshot.body_text == _GOLDEN_TIER_UNKNOWN_BODY
    assert snapshot.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert snapshot.warnings == (
        "Tier Unknown: in gap (T1-T2)",
    )
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_TARGET


# ---------------------------------------------------------------------------
# Golden body: Tier Not Applicable (migration missing, warning fires)
# ---------------------------------------------------------------------------


_GOLDEN_TIER_NA_BODY: str = (
    "\U0001f525 PHOENIX — PHXT…5678 "
    "[Tier Not Applicable]\n"
    "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
    "\n"
    "\U0001f9e0 State\n"
    "• MC: Unknown | ATH: Unknown | Mig: Unknown\n"
    "• Drop: Unknown | Age: 16.6h | Net: Unknown\n"
    "• LP: Unknown\n"
    "• Basis: price-basis\n"
    "\n"
    "⚠ Notes\n"
    "• Tier Not Applicable: migration missing"
)


def test_tier_not_applicable_golden_body() -> None:
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_NOT_APPLICABLE,
        tier_reason=TIER_REASON_NA_MIGRATION_MISSING,
        drawdown_from_ath_raw=None,
        drop_positive=None,
        ath_status="UNAVAILABLE",
        ath_since_migration_status="UNKNOWN",
        migration_status="MISSING",
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status=None)
    )
    assert snapshot.body_text == _GOLDEN_TIER_NA_BODY
    assert snapshot.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert snapshot.warnings == (
        "Tier Not Applicable: migration missing",
    )
    assert snapshot.drop_percent_display == DISPLAY_UNKNOWN
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_TARGET


# ---------------------------------------------------------------------------
# Regression: renderer echoes the supplied token / base mint and
# NEVER substitutes the WSOL / quote mint.
# ---------------------------------------------------------------------------


def test_renderer_echoes_supplied_token_base_mint_verbatim() -> None:
    """The Stage 30.2 renderer must echo the supplied token / base
    mint verbatim. It must NEVER substitute the WSOL / quote mint.
    """
    assert _SAFE_MINT != _WSOL_MINT
    snapshot = render_compact_ping(_make_input(mint=_SAFE_MINT))
    assert snapshot.mint == _SAFE_MINT
    # The supplied mint appears on the mint line.
    lines = snapshot.body_text.split("\n")
    assert lines[1] == _SAFE_MINT
    # The renderer NEVER swaps in WSOL or any other quote mint.
    assert _WSOL_MINT not in snapshot.body_text


def test_renderer_does_not_inject_wsol_when_mint_missing() -> None:
    """When the caller passes no mint, the body shows Unknown -- the
    renderer must NEVER fall back to WSOL or any other quote mint.
    """
    td = _make_tier_decision(mint=None)
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, mint=None)
    )
    assert snapshot.mint is None
    assert _WSOL_MINT not in snapshot.body_text
    lines = snapshot.body_text.split("\n")
    assert lines[1] == "Unknown"


def test_renderer_does_not_inject_wsol_when_mint_unsafe() -> None:
    """When the caller passes an unsafe-shape mint, the body shows
    Unknown -- the renderer must NEVER fall back to WSOL.
    """
    # "0" * 44 is shape-rejected (zero not in base58 alphabet).
    snapshot = render_compact_ping(_make_input(mint="0" * 44))
    assert snapshot.mint is None
    assert _WSOL_MINT not in snapshot.body_text
    lines = snapshot.body_text.split("\n")
    assert lines[1] == "Unknown"


def test_wsol_passed_in_renders_wsol_not_substituted() -> None:
    """Defensive: the renderer must not have a hardcoded mint
    substitution. If a (misguided) caller passes WSOL as the input
    mint, the renderer echoes it verbatim -- the renderer does NOT
    have logic that detects + rewrites WSOL. The caller is the
    contract owner for token-vs-quote mint distinction.
    """
    snapshot = render_compact_ping(_make_input(mint=_WSOL_MINT))
    assert snapshot.mint == _WSOL_MINT
    lines = snapshot.body_text.split("\n")
    assert lines[1] == _WSOL_MINT


# ---------------------------------------------------------------------------
# Missing display text: MC / ATH / Mig / LP / Net render Unknown
# ---------------------------------------------------------------------------


def test_missing_mc_renders_unknown() -> None:
    snapshot = render_compact_ping(
        _make_input(current_mc_text=None)
    )
    assert snapshot.current_mc_display == DISPLAY_UNKNOWN
    assert "MC: Unknown" in snapshot.body_text


def test_missing_ath_mc_renders_unknown() -> None:
    snapshot = render_compact_ping(_make_input(ath_mc_text=None))
    assert snapshot.ath_mc_display == DISPLAY_UNKNOWN
    assert "ATH: Unknown" in snapshot.body_text


def test_missing_migration_mc_renders_unknown() -> None:
    snapshot = render_compact_ping(
        _make_input(migration_mc_text=None)
    )
    assert snapshot.migration_mc_display == DISPLAY_UNKNOWN
    assert "Mig: Unknown" in snapshot.body_text


def test_missing_lp_renders_unknown() -> None:
    snapshot = render_compact_ping(_make_input(lp_text=None))
    assert snapshot.lp_display == DISPLAY_UNKNOWN
    assert "LP: Unknown" in snapshot.body_text


def test_missing_net_flow_renders_unknown() -> None:
    snapshot = render_compact_ping(
        _make_input(net_flow_text=None)
    )
    assert snapshot.net_flow_display == DISPLAY_UNKNOWN
    assert "Net: Unknown" in snapshot.body_text


def test_empty_string_mc_renders_unknown() -> None:
    snapshot = render_compact_ping(
        _make_input(current_mc_text="")
    )
    assert snapshot.current_mc_display == DISPLAY_UNKNOWN
    assert "MC: Unknown" in snapshot.body_text


def test_empty_string_net_flow_renders_unknown() -> None:
    snapshot = render_compact_ping(_make_input(net_flow_text=""))
    assert snapshot.net_flow_display == DISPLAY_UNKNOWN
    assert "Net: Unknown" in snapshot.body_text


def test_missing_values_never_render_zero() -> None:
    snapshot = render_compact_ping(_make_input())
    # No "MC: 0", "ATH: 0", "Mig: 0", "LP: 0", "Net: 0" anywhere.
    assert " MC: 0" not in snapshot.body_text
    assert " ATH: 0" not in snapshot.body_text
    assert " Mig: 0" not in snapshot.body_text
    assert " LP: 0" not in snapshot.body_text
    assert " Net: 0" not in snapshot.body_text
    # Also confirm "Drop: 0%" never appears for a missing drop.
    td = _make_tier_decision(drop_positive=None)
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert "Drop: 0%" not in snapshot.body_text
    assert "Drop: Unknown" in snapshot.body_text


def test_floor_label_never_emitted() -> None:
    """Regression: ``Floor`` is the OLD label. The Stage 30.2 body
    must never carry it; the new label is ``Drop``.
    """
    for body in _every_body_in_corpus():
        assert "Floor:" not in body
        assert "Floor " not in body


def test_vol_label_never_emitted() -> None:
    """Regression: ``Vol`` is the OLD label. The Stage 30.2 body
    must never carry it; the new label is ``Net``.
    """
    for body in _every_body_in_corpus():
        assert "Vol:" not in body
        assert "Vol " not in body


# ---------------------------------------------------------------------------
# Basis line always appears (both basis tokens)
# ---------------------------------------------------------------------------


def test_basis_line_price_basis_always_present() -> None:
    snapshot = render_compact_ping(_make_input())
    assert "• Basis: price-basis" in snapshot.body_text


def test_basis_line_mc_basis_always_present() -> None:
    td = _make_tier_decision(basis=BASIS_MC)
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert "• Basis: mc-basis" in snapshot.body_text


# ---------------------------------------------------------------------------
# Drop (drawdown-from-ATH) formatting (ROUND_DOWN)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("drop_positive", "expected"),
    [
        ("0.50", "-50%"),
        ("0.55", "-55%"),
        ("0.555", "-55%"),
        ("0.5999", "-59%"),
        ("0.62", "-62%"),
        ("0.82", "-82%"),
        ("0.95", "-95%"),
        ("0.99", "-99%"),
        ("1.00", "-100%"),
        ("0.00", "-0%"),
        ("0", "-0%"),
    ],
)
def test_drop_formatting_round_down(
    drop_positive: str, expected: str
) -> None:
    td = _make_tier_decision(drop_positive=drop_positive)
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert snapshot.drop_percent_display == expected
    assert f"Drop: {expected}" in snapshot.body_text


@pytest.mark.parametrize(
    "bad",
    [None, "", "abc", "  ", "+0.55", ".5", "5.", "NaN", "0e0"],
)
def test_drop_formatting_unknown_on_missing_or_malformed(
    bad: object,
) -> None:
    td = _make_tier_decision(drop_positive=bad)  # type: ignore[arg-type]
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert snapshot.drop_percent_display == DISPLAY_UNKNOWN
    assert "Drop: Unknown" in snapshot.body_text


# ---------------------------------------------------------------------------
# Age formatting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, "0s"),
        (1, "1s"),
        (30, "30s"),
        (59, "59s"),
        (60, "1m"),
        (90, "1m"),
        (3599, "59m"),
        (3600, "1.0h"),
        (3700, "1.0h"),
        (59760, "16.6h"),
        (86400, "24.0h"),
        (172800, "2.0d"),
        (432000, "5.0d"),
    ],
)
def test_age_formatting(age: int, expected: str) -> None:
    snapshot = render_compact_ping(
        _make_input(age_since_migration_seconds=age)
    )
    assert snapshot.age_display == expected
    assert f"Age: {expected}" in snapshot.body_text


def test_age_none_renders_unknown() -> None:
    snapshot = render_compact_ping(
        _make_input(age_since_migration_seconds=None)
    )
    assert snapshot.age_display == DISPLAY_UNKNOWN
    assert "Age: Unknown" in snapshot.body_text


def test_age_negative_raises() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(age_since_migration_seconds=-1)
        )
    assert exc_info.value.reason == "AGE_SECONDS_NEGATIVE"


def test_age_bool_rejected() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                age_since_migration_seconds=True,  # type: ignore[arg-type]
            )
        )
    assert exc_info.value.reason == "AGE_SECONDS_INVALID_TYPE"


def test_age_non_int_type_rejected() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                age_since_migration_seconds="60",  # type: ignore[arg-type]
            )
        )
    assert exc_info.value.reason == "AGE_SECONDS_INVALID_TYPE"


# ---------------------------------------------------------------------------
# Symbol fallback chain
# ---------------------------------------------------------------------------


def test_symbol_valid_uses_symbol() -> None:
    snapshot = render_compact_ping(_make_input(symbol="DOG"))
    assert snapshot.symbol == "DOG"
    assert (
        "\U0001f525 PHOENIX — DOG [Tier 1]"
        in snapshot.body_text
    )


def test_symbol_invalid_shape_falls_back_to_mint_short() -> None:
    # Symbol with a space is outside the allowlist; renderer must
    # NOT raise. Falls back to mint short.
    snapshot = render_compact_ping(_make_input(symbol="bad symbol"))
    assert snapshot.symbol is None  # sanitization redacted to None
    assert _SAFE_MINT_SHORT in snapshot.body_text


def test_symbol_too_long_falls_back_to_mint_short() -> None:
    snapshot = render_compact_ping(
        _make_input(symbol="A" * 17)
    )
    assert snapshot.symbol is None
    assert _SAFE_MINT_SHORT in snapshot.body_text


def test_symbol_empty_string_falls_back_to_mint_short() -> None:
    snapshot = render_compact_ping(_make_input(symbol=""))
    assert snapshot.symbol is None
    assert _SAFE_MINT_SHORT in snapshot.body_text


def test_symbol_invalid_and_no_mint_falls_back_to_unknown() -> None:
    td = _make_tier_decision(mint=None)
    snapshot = render_compact_ping(
        _make_input(
            tier_decision=td,
            mint=None,
            symbol="bad symbol",
        )
    )
    assert snapshot.symbol is None
    assert snapshot.mint is None
    assert (
        "\U0001f525 PHOENIX — Unknown [Tier 1]"
        in snapshot.body_text
    )


def test_no_symbol_no_mint_renders_unknown_header_and_mint_line() -> None:
    snapshot = render_compact_ping(
        _make_input(mint=None, symbol=None)
    )
    assert snapshot.mint is None
    assert snapshot.symbol is None
    assert (
        "\U0001f525 PHOENIX — Unknown [Tier 1]"
        in snapshot.body_text
    )
    # Mint line renders as "Unknown" too.
    lines = snapshot.body_text.split("\n")
    assert lines[1] == "Unknown"


def test_unsafe_mint_falls_back_to_unknown() -> None:
    # A mint outside the base58 alphabet (contains a forbidden "0")
    # redacts to None and the mint line renders as Unknown.
    unsafe = "0" * 44
    snapshot = render_compact_ping(_make_input(mint=unsafe))
    assert snapshot.mint is None
    lines = snapshot.body_text.split("\n")
    assert lines[1] == "Unknown"


# ---------------------------------------------------------------------------
# Renderer trusts TierDecisionRecord verbatim (no tier re-computation)
# ---------------------------------------------------------------------------


def test_renderer_trusts_tier_token_verbatim_even_against_drop() -> None:
    # Contradictory: tier_token says Tier 1 but drop_positive is in
    # the graveyard band (> 0.95). The renderer MUST emit [Tier 1]
    # (and Drop -99%) verbatim. This proves the renderer does not
    # re-classify the drop against the Stage 30.1 bands.
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_1,
        tier_reason=TIER_REASON_TIER_1_IN_BAND,
        drawdown_from_ath_raw="0.99",
        drop_positive="0.99",
    )
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert "[Tier 1]" in snapshot.body_text
    assert "Drop: -99%" in snapshot.body_text


def test_renderer_trusts_tier_reason_verbatim() -> None:
    # Contradictory: tier_token says Tier 1 but tier_reason says the
    # graveyard band. The renderer echoes both verbatim to the
    # snapshot; the body still shows [Tier 1] in the header. The
    # renderer derives its warning from tier_reason, so the body
    # carries the graveyard warning.
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_1,
        tier_reason=TIER_REASON_UNKNOWN_GRAVEYARD,
        drawdown_from_ath_raw="0.99",
        drop_positive="0.99",
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status=None)
    )
    assert snapshot.tier_token == TIER_TOKEN_TIER_1
    assert snapshot.tier_reason == TIER_REASON_UNKNOWN_GRAVEYARD
    assert "[Tier 1]" in snapshot.body_text
    assert snapshot.warnings == (
        "Tier Unknown: graveyard (drop > 0.95)",
    )


# ---------------------------------------------------------------------------
# Warning emission: tier_reason table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tier_reason", "expected_warning"),
    [
        (
            TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
            "Tier Unknown: drawdown missing",
        ),
        (
            TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
            "Tier Unknown: drawdown malformed",
        ),
        (
            TIER_REASON_UNKNOWN_BELOW_TIER_1,
            "Tier Unknown: below tier 1",
        ),
        (
            TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
            "Tier Unknown: in gap (T1-T2)",
        ),
        (
            TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
            "Tier Unknown: in gap (T2-T3)",
        ),
        (
            TIER_REASON_UNKNOWN_GRAVEYARD,
            "Tier Unknown: graveyard (drop > 0.95)",
        ),
        (
            TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
            "Tier Unknown: ATH not present",
        ),
        (
            TIER_REASON_NA_MIGRATION_MISSING,
            "Tier Not Applicable: migration missing",
        ),
        (
            TIER_REASON_NA_MIGRATION_UNTRUSTED,
            "Tier Not Applicable: migration untrusted",
        ),
        (
            TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
            "Tier Not Applicable: unsupported pair",
        ),
        (
            TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
            "Tier Not Applicable: migration source error",
        ),
        (
            TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
            "Tier Not Applicable: ATH may include pre-migration",
        ),
    ],
)
def test_tier_reason_warning_emission(
    tier_reason: str, expected_warning: str
) -> None:
    td = _make_tier_decision(
        tier_reason=tier_reason,
        tier_token=TIER_TOKEN_TIER_UNKNOWN,
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status=None)
    )
    assert snapshot.warnings == (expected_warning,)
    assert expected_warning in snapshot.body_text
    assert "⚠ Notes" in snapshot.body_text


@pytest.mark.parametrize(
    "in_band_reason",
    [
        TIER_REASON_TIER_1_IN_BAND,
        TIER_REASON_TIER_2_IN_BAND,
        TIER_REASON_TIER_3_IN_BAND,
    ],
)
def test_in_band_tier_reason_emits_no_warning(
    in_band_reason: str,
) -> None:
    td = _make_tier_decision(tier_reason=in_band_reason)
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status="PRESENT")
    )
    assert snapshot.warnings == ()
    assert "⚠ Notes" not in snapshot.body_text


# ---------------------------------------------------------------------------
# Warning emission: price_status table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price_status", "expected_warning"),
    [
        ("STALE", "Price degraded: stale"),
        ("SOURCE_ERROR", "Price degraded: source error"),
        ("UNAVAILABLE", "Price degraded: unavailable"),
    ],
)
def test_price_status_warning_emission(
    price_status: str, expected_warning: str
) -> None:
    snapshot = render_compact_ping(
        _make_input(price_status=price_status)
    )
    assert snapshot.warnings == (expected_warning,)
    assert expected_warning in snapshot.body_text


@pytest.mark.parametrize(
    "price_status",
    ["PRESENT", "UNSUPPORTED_PAIR", None],
)
def test_price_status_no_warning_for_clean(
    price_status: Optional[str],
) -> None:
    snapshot = render_compact_ping(
        _make_input(price_status=price_status)
    )
    assert snapshot.warnings == ()


def test_two_warnings_tier_reason_first_then_price_status() -> None:
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_NOT_APPLICABLE,
        tier_reason=TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status="SOURCE_ERROR")
    )
    assert snapshot.warnings == (
        "Tier Not Applicable: ATH may include pre-migration",
        "Price degraded: source error",
    )
    assert len(snapshot.warnings) == 2


def test_max_two_warning_lines() -> None:
    td = _make_tier_decision(
        tier_reason=TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
        tier_token=TIER_TOKEN_TIER_UNKNOWN,
    )
    snapshot = render_compact_ping(
        _make_input(tier_decision=td, price_status="STALE")
    )
    assert len(snapshot.warnings) <= 2


# ---------------------------------------------------------------------------
# Forbidden trading-verdict / URL-auth substring absence
# ---------------------------------------------------------------------------


_FORBIDDEN_TRADING_VERDICT_SUBSTRINGS: tuple = (
    "B" + "UY",
    "S" + "ELL",
    "A" + "PPROVED",
    "G" + "ATE",
    "B" + "LOCK",
    "E" + "NFORCEMENT",
    "E" + "XECUTE",
    "P" + "OSITION",
    "A" + "UTO-TRADE",
)


_FORBIDDEN_URL_AUTH_SUBSTRINGS: tuple = (
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _every_body_in_corpus() -> list:
    bodies: list = []
    # Tier 1 / 2 / 3 / Unknown / Not Applicable.
    bodies.append(_GOLDEN_TIER_1_BODY)
    bodies.append(_GOLDEN_TIER_2_BODY)
    bodies.append(_GOLDEN_TIER_3_BODY)
    bodies.append(_GOLDEN_TIER_UNKNOWN_BODY)
    bodies.append(_GOLDEN_TIER_NA_BODY)
    # Every tier_reason warning variant.
    for reason in (
        TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
        TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
        TIER_REASON_UNKNOWN_BELOW_TIER_1,
        TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
        TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
        TIER_REASON_UNKNOWN_GRAVEYARD,
        TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
        TIER_REASON_NA_MIGRATION_MISSING,
        TIER_REASON_NA_MIGRATION_UNTRUSTED,
        TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
        TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
        TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    ):
        td = _make_tier_decision(
            tier_reason=reason,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
        )
        snapshot = render_compact_ping(
            _make_input(tier_decision=td, price_status="STALE")
        )
        bodies.append(snapshot.body_text)
    return bodies


def test_no_body_contains_forbidden_trading_verdict_substring() -> None:
    for body in _every_body_in_corpus():
        lower = body.lower()
        for needle in _FORBIDDEN_TRADING_VERDICT_SUBSTRINGS:
            assert needle.lower() not in lower, (
                f"body carries forbidden trading-verdict "
                f"substring {needle!r}: {body!r}"
            )


def test_no_body_contains_forbidden_url_auth_substring() -> None:
    for body in _every_body_in_corpus():
        lower = body.lower()
        for needle in _FORBIDDEN_URL_AUTH_SUBSTRINGS:
            assert needle.lower() not in lower, (
                f"body carries forbidden URL/auth substring "
                f"{needle!r}: {body!r}"
            )


# ---------------------------------------------------------------------------
# Body length invariants
# ---------------------------------------------------------------------------


def test_in_band_body_length_under_target() -> None:
    for body in (
        _GOLDEN_TIER_1_BODY,
        _GOLDEN_TIER_2_BODY,
        _GOLDEN_TIER_3_BODY,
    ):
        assert len(body) <= STAGE30_2_BODY_CHAR_TARGET


def test_every_corpus_body_under_hard_cap() -> None:
    for body in _every_body_in_corpus():
        assert len(body) <= STAGE30_2_BODY_CHAR_HARD_CAP


def test_worst_case_body_under_hard_cap() -> None:
    # Worst case: longest tier_reason warning + degraded price +
    # maximum-shape symbol + every display text at a reasonable
    # operator length. Net-flow text uses neutral language that
    # does not collide with the Stage 30.2 forbidden trading-
    # verdict substring set.
    td = _make_tier_decision(
        tier_token=TIER_TOKEN_TIER_NOT_APPLICABLE,
        tier_reason=TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
        drop_positive="0.82",
        drawdown_from_ath_raw="0.82",
    )
    snapshot = render_compact_ping(
        _make_input(
            tier_decision=td,
            symbol="A" * 16,
            current_mc_text="$999.99M",
            ath_mc_text="$1.23B",
            migration_mc_text="$36k",
            lp_text="$27k (tradable-pool)",
            net_flow_text=None,
            age_since_migration_seconds=432000,
            price_status="SOURCE_ERROR",
        )
    )
    assert snapshot.body_length_chars <= STAGE30_2_BODY_CHAR_HARD_CAP


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_render_compact_ping_is_deterministic() -> None:
    input_record = _make_input()
    first = render_compact_ping(input_record)
    second = render_compact_ping(input_record)
    assert first == second
    assert first.body_text == second.body_text


# ---------------------------------------------------------------------------
# Snapshot record carries echoed fields verbatim
# ---------------------------------------------------------------------------


def test_snapshot_record_echoes_tier_decision_fields() -> None:
    td = _make_tier_decision(
        basis=BASIS_MC,
        drawdown_from_ath_raw="0.72",
        drop_positive="0.72",
        ath_status="STALE",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        migration_status="UNTRUSTED",
        tier_token=TIER_TOKEN_TIER_2,
        tier_reason=TIER_REASON_TIER_2_IN_BAND,
    )
    snapshot = render_compact_ping(_make_input(tier_decision=td))
    assert snapshot.basis == BASIS_MC
    assert snapshot.drawdown_from_ath_raw == "0.72"
    assert snapshot.drop_positive == "0.72"
    assert snapshot.ath_status == "STALE"
    assert snapshot.ath_since_migration_status == (
        "POST_MIGRATION_ONLY"
    )
    assert snapshot.migration_status == "UNTRUSTED"
    assert snapshot.tier_token == TIER_TOKEN_TIER_2
    assert snapshot.tier_reason == TIER_REASON_TIER_2_IN_BAND


def test_snapshot_record_carries_schema_version_and_basename() -> None:
    snapshot = render_compact_ping(_make_input())
    assert (
        snapshot.schema_version
        == STAGE30_2_COMPACT_PING_SCHEMA_VERSION
    )


def test_snapshot_record_carries_created_at_verbatim() -> None:
    snapshot = render_compact_ping(
        _make_input(created_at_utc="2026-05-27T18:30:45.123Z")
    )
    assert snapshot.created_at_utc == "2026-05-27T18:30:45.123Z"


def test_snapshot_record_identifier_echoes_sanitized() -> None:
    snapshot = render_compact_ping(
        _make_input(
            session_id="sess-123",
            ping_id="ping-abc.def",
            candidate_id="cand_x",
        )
    )
    assert snapshot.session_id == "sess-123"
    assert snapshot.ping_id == "ping-abc.def"
    assert snapshot.candidate_id == "cand_x"


def test_snapshot_record_identifier_unsafe_shape_redacts() -> None:
    snapshot = render_compact_ping(
        _make_input(
            session_id="bad id with space",
            ping_id="ping/with/slashes",
            candidate_id=None,
        )
    )
    assert snapshot.session_id is None
    assert snapshot.ping_id is None
    assert snapshot.candidate_id is None


def test_snapshot_carries_drop_percent_display_field() -> None:
    snapshot = render_compact_ping(_make_input())
    # Field name on the snapshot is ``drop_percent_display`` -- NOT
    # ``floor_percent_display``. Defensive pin against future
    # accidental rename.
    assert hasattr(snapshot, "drop_percent_display")
    assert not hasattr(snapshot, "floor_percent_display")


def test_snapshot_carries_net_flow_display_field() -> None:
    snapshot = render_compact_ping(_make_input())
    # Field name on the snapshot is ``net_flow_display`` -- NOT
    # ``volume_display``. Defensive pin against future accidental
    # rename.
    assert hasattr(snapshot, "net_flow_display")
    assert not hasattr(snapshot, "volume_display")


# ---------------------------------------------------------------------------
# Caller-shape errors
# ---------------------------------------------------------------------------


def test_input_invalid_type_raises() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping("not an input record")  # type: ignore[arg-type]
    assert exc_info.value.reason == "INPUT_INVALID_TYPE"


def test_tier_decision_invalid_type_raises() -> None:
    bad = _make_input()._replace(
        tier_decision="not a tier decision",  # type: ignore[arg-type]
    )
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(bad)
    assert exc_info.value.reason == "TIER_DECISION_INVALID_TYPE"


@pytest.mark.parametrize(
    "bad_created_at",
    [
        "",
        "2026-05-27",
        "2026/05/27T12:00:00Z",
        "2026-05-27T12:00:00",
        "2026-05-27T12:00:00+00:00",
        "not a timestamp",
    ],
)
def test_created_at_unsafe_shape_raises(
    bad_created_at: object,
) -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(created_at_utc=bad_created_at)
        )
    assert exc_info.value.reason == (
        "CREATED_AT_UTC_NOT_SAFE_ISO8601"
    )


def test_display_text_with_trading_verdict_substring_raises() -> None:
    # "BUY" inside a text field should raise.
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(net_flow_text="this is a B" + "UY signal")
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


def test_display_text_with_url_substring_raises() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(lp_text="visit " + "h" + "ttps://x.com")
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


def test_display_text_with_bearer_substring_raises() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                current_mc_text="B" + "earer abc123"
            )
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


def test_symbol_with_trading_verdict_substring_raises() -> None:
    # Symbol "BUY" passes shape (3 chars, alphanumeric) but the
    # forbidden-substring scan rejects it before fallback can occur.
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(_make_input(symbol="B" + "UY"))
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


def test_safe_substring_alone_is_not_forbidden() -> None:
    # Stage 30.2 intentionally drops "SAFE" from the forbidden
    # trading-verdict needle set; a display text mentioning a
    # standalone "SAFE" (here as a hyphenated qualifier) must NOT
    # raise. The Stage 30 redaction scan uses ``SAFE`` as a closed-
    # set status token, so the renderer must not collide with that
    # usage.
    snapshot = render_compact_ping(
        _make_input(net_flow_text="SAFE-cooling")
    )
    assert snapshot.net_flow_display == "SAFE-cooling"


def test_safe_substring_in_redaction_context_is_not_forbidden() -> None:
    # ``redaction SAFE`` is the natural human-readable label for a
    # passing redaction scan. The renderer must accept it as a
    # standalone display text -- it carries no forbidden trading-
    # verdict substring on its own.
    snapshot = render_compact_ping(
        _make_input(lp_text="redaction SAFE")
    )
    assert snapshot.lp_display == "redaction SAFE"
    assert "redaction SAFE" in snapshot.body_text


def test_safe_buy_compound_substring_is_rejected() -> None:
    # The ``SAFE`` carve-out applies ONLY when ``SAFE`` appears
    # WITHOUT a paired forbidden trading-verdict substring. A
    # compound phrase such as ``SAFE BUY`` is still rejected
    # because ``BUY`` remains a forbidden substring.
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                net_flow_text="SAFE B" + "UY",
            )
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


def test_safe_sell_compound_substring_is_rejected() -> None:
    # Mirror of the SAFE BUY case for SELL.
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                net_flow_text="SAFE S" + "ELL",
            )
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


@pytest.mark.parametrize(
    "needle_paired_with_safe",
    [
        "B" + "UY",
        "S" + "ELL",
        "A" + "PPROVED",
        "G" + "ATE",
        "B" + "LOCK",
        "E" + "NFORCEMENT",
        "E" + "XECUTE",
        "P" + "OSITION",
        "A" + "UTO-TRADE",
    ],
)
def test_safe_paired_with_any_forbidden_verdict_is_rejected(
    needle_paired_with_safe: str,
) -> None:
    # Each forbidden trading-verdict substring still fires even when
    # the caller has also included ``SAFE`` in the text.
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        render_compact_ping(
            _make_input(
                net_flow_text=f"SAFE {needle_paired_with_safe}",
            )
        )
    assert exc_info.value.reason == (
        "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )


# ---------------------------------------------------------------------------
# Basis line always appears (negative assertion: never omitted)
# ---------------------------------------------------------------------------


def test_basis_line_present_in_every_corpus_body() -> None:
    for body in _every_body_in_corpus():
        assert (
            "• Basis: price-basis" in body
            or "• Basis: mc-basis" in body
        )
