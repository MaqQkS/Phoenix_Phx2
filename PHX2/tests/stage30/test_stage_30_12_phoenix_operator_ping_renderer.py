"""Stage 30.12 PHOENIX private operator ping renderer tests.

Pure read-only tests over the Stage 30.12 renderer's body shape, the golden full
body for the real first-private-send candidate values, the Unknown fallbacks,
the WSOL-as-CA rejection, the redaction / forbidden-substring fail-closed, the
source-ref shortening, the body-length cap, determinism, the tier-band display
map, and the fractional-drop regression (the renderer uses the EXPLICIT
fractional percent, never the absolute drawdown).

Discipline: no env reads, no network, no Discord, no provider calls. Stdlib +
pytest only.
"""

from __future__ import annotations

import pytest

from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    DISPLAY_UNKNOWN,
    PhoenixOperatorPingInput,
    STAGE30_12_BODY_CHAR_HARD_CAP,
    STAGE30_12_OPERATOR_FOOTER,
    Stage30_12PhoenixOperatorPingError,
    TIER_BAND_DISPLAY_TIER_1,
    TIER_BAND_DISPLAY_TIER_2,
    TIER_BAND_DISPLAY_TIER_3,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_UNKNOWN,
    WSOL_QUOTE_MINT,
    tier_band_display_for,
)
from PHX2.stage30.stage30_12_phoenix_operator_ping_renderer import (
    render_phoenix_operator_ping,
)


# A real, valid-shape, non-WSOL Solana base58 token / base mint (the candidate
# whose first real private send improvised the ugly body out-of-repo).
_GOLDEN_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_GOLDEN_SIG: str = (
    "5hMAYVvmcYNxV29b5TAboHuKEXKjURwU484fjHrBeUNU6ebUN2ndako5D1pFW5jxZMBxmRFWVhtJ8oZ7PDaJ9MFV"
)
_GOLDEN_SOURCE_REF: str = f"helius:sig:{_GOLDEN_SIG}:slot:424620715"

_ELLIPSIS: str = "…"


def _make_input(**overrides: object) -> PhoenixOperatorPingInput:
    base: dict = {
        "token_mint": _GOLDEN_MINT,
        "tier_token": TIER_TOKEN_TIER_2,
    }
    base.update(overrides)
    return PhoenixOperatorPingInput(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Golden full body
# ---------------------------------------------------------------------------


def _golden_input() -> PhoenixOperatorPingInput:
    return _make_input(
        tier_token=TIER_TOKEN_TIER_2,
        symbol_or_name=None,
        migration_confirmed=True,
        migration_time_utc="2026-06-06T06:14:10Z",
        market_cap_display="$5.1k",
        liquidity_display="$4.8k",
        current_price="0.000005190124582537581",
        ath_price="0.00002109286722553503",
        absolute_drawdown="0.000015902742642997449",
        fractional_drop_pct="-75.39%",
        basis_display="Post-migration ATH",
        source_ref=_GOLDEN_SOURCE_REF,
    )


def test_golden_full_body_contains_every_section_and_field() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    expected_substrings = (
        "🔥 PHOENIX",
        "[Tier 2]",
        f"CA: {_GOLDEN_MINT}",
        "🧠 State",
        "💰 Price",
        "🎯 Dip Gate",
        "🧾 Provenance",
        "MC: $5.1k",
        "LP: $4.8k",
        "Drop: -75.39%",
        "Mig: Confirmed",
        "Now: $0.0000051901",
        "ATH: $0.0000210929",
        f"Band: {TIER_BAND_DISPLAY_TIER_2}",
        "Basis: Post-migration ATH",
        "Migration: 2026-06-06T06:14:10Z",
        "Src: helius:sig:5hMAYVvm" + _ELLIPSIS + "MFV:slot:424620715",
        "PRIVATE OPERATOR ONLY",
    )
    for needle in expected_substrings:
        assert needle in body, f"golden body missing {needle!r}\n{body}"


def test_golden_body_first_line_is_the_phoenix_header_not_ugly_title() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    first_line = body.splitlines()[0]
    assert first_line == "🔥 PHOENIX — Et9km9…VfaNe [Tier 2]"
    # The ugly proof-body title must NOT be present anywhere.
    assert "PHOENIX PRIVATE - OPERATOR ONLY" not in body


def test_golden_body_footer_is_operator_only_wording() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    assert body.splitlines()[-1] == STAGE30_12_OPERATOR_FOOTER
    assert STAGE30_12_OPERATOR_FOOTER == "PRIVATE OPERATOR ONLY · PHX2"


def test_golden_body_does_not_dump_absolute_drawdown() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    assert "0.000015902742642997449" not in body
    assert "abs " not in body


# ---------------------------------------------------------------------------
# 2. Unknown fallbacks
# ---------------------------------------------------------------------------


def test_missing_optionals_render_unknown_not_blank_or_zero() -> None:
    body = render_phoenix_operator_ping(
        _make_input(tier_token=TIER_TOKEN_TIER_2)
    )
    assert "MC: Unknown" in body
    assert "LP: Unknown" in body
    assert "Drop: Unknown" in body
    assert "Mig: Unknown" in body
    assert "Age: Unknown" in body
    assert "Now: Unknown" in body
    assert "ATH: Unknown" in body
    assert "Basis: Unknown" in body
    assert "Migration: Unknown" in body
    assert "Src: Unknown" in body
    # Never a fabricated zero / empty.
    assert "$0 " not in body
    assert "MC:  |" not in body
    assert ": \n" not in body


def test_migration_confirmed_false_renders_unknown_not_confirmed() -> None:
    body = render_phoenix_operator_ping(
        _make_input(migration_confirmed=False)
    )
    assert "Mig: Unknown" in body
    assert "Mig: Confirmed" not in body


def test_non_iso_migration_time_renders_unknown() -> None:
    body = render_phoenix_operator_ping(
        _make_input(migration_time_utc="June 6 2026")
    )
    assert "Migration: Unknown" in body
    assert "June 6 2026" not in body


# ---------------------------------------------------------------------------
# 3. WSOL / quote-mint rejection (and other CA fail-closed shapes)
# ---------------------------------------------------------------------------


def test_wsol_quote_mint_as_token_mint_fails_closed() -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(_make_input(token_mint=WSOL_QUOTE_MINT))
    assert exc.value.reason == "TOKEN_MINT_IS_WSOL_QUOTE"


def test_blank_token_mint_fails_closed() -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(_make_input(token_mint="   "))
    assert exc.value.reason == "TOKEN_MINT_MISSING"


def test_non_base58_token_mint_fails_closed() -> None:
    # Contains '0' / 'O' / 'l' (outside the base58 alphabet).
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(
            _make_input(token_mint="0OIl" + "1" * 40)
        )
    assert exc.value.reason == "TOKEN_MINT_NOT_BASE58"


def test_blank_tier_token_fails_closed() -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(_make_input(tier_token=""))
    assert exc.value.reason == "TIER_TOKEN_MISSING"


def test_non_input_type_fails_closed() -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping({"token_mint": _GOLDEN_MINT})  # type: ignore[arg-type]
    assert exc.value.reason == "INPUT_INVALID_TYPE"


# ---------------------------------------------------------------------------
# 4. Redaction / forbidden-substring fail-closed
# ---------------------------------------------------------------------------


_DANGEROUS_VALUES = (
    "https://discord.com/api/webhooks/123456/AbCdEf",   # full webhook URL
    "wss://example.invalid/socket",                     # ws scheme
    "sk-live-0123456789abcdef",                         # secret-key-looking
    "x-api-key: deadbeef",                              # api-key header
    "Authorization: Bearer eyJabc.def.ghi",             # auth header
    "https://mainnet.helius-rpc.com/?api-key=secret",   # private RPC URL
    "rpc_url=https://node.invalid",                     # rpc_url assignment
)


@pytest.mark.parametrize("bad_value", _DANGEROUS_VALUES)
@pytest.mark.parametrize(
    "field",
    (
        "symbol_or_name",
        "market_cap_display",
        "liquidity_display",
        "source_ref",
        "basis_display",
        "age_display",
    ),
)
def test_forbidden_substring_in_any_display_field_fails_closed(
    field: str, bad_value: str
) -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(_make_input(**{field: bad_value}))
    assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"


def test_control_char_injection_fails_closed() -> None:
    # A newline-bearing field could otherwise spoof a fake body section.
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(
            _make_input(market_cap_display="$5.1k\n🧠 State\nFAKE")
        )
    assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"


def test_clean_golden_body_carries_no_scheme_or_key_material() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    lowered = body.lower()
    assert (":" + "/" + "/") not in body
    assert ("x-" + "api-" + "key") not in lowered
    assert ("api_" + "key") not in lowered


# ---------------------------------------------------------------------------
# 4b. Codex secret-variant regression (hyphen / underscore / spacing variants)
# ---------------------------------------------------------------------------
#
# Codex FAIL: the renderer leaked secret/API-key-looking values in display
# fields (notably source_ref) because the needle list only matched the
# underscore / spaced variants. These probes assert the hyphen / underscore /
# case / URL variants now fail closed BEFORE shortening.


_CODEX_SECRET_SOURCE_REFS = (
    # Codex's three concrete missed probes.
    "helius:sig:api-key=abc123:slot:1",
    "helius:sig:bearer_token=abcdefghi:slot:1",
    "helius:sig:private-key=abc:slot:1",
    # Case + separator variants.
    "helius:sig:API-KEY=abc123:slot:1",
    "helius:sig:Bearer-Token=abcdefghi:slot:1",
    "helius:sig:PRIVATE_KEY=abc:slot:1",
    # URL / webhook / api-key-in-URL variants.
    "https://discord.com/api/webhooks/123/secret",
    "https://example.com/?x-api-key=abc123",
    "https://rpc.example.com/?api-key=abc123",
)


@pytest.mark.parametrize("bad_source_ref", _CODEX_SECRET_SOURCE_REFS)
def test_codex_secret_source_refs_fail_closed(bad_source_ref: str) -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        render_phoenix_operator_ping(_make_input(source_ref=bad_source_ref))
    assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"


@pytest.mark.parametrize(
    "field", ("source_ref", "symbol_or_name", "basis_display", "age_display")
)
def test_hyphen_secret_variants_fail_closed_in_any_field(field: str) -> None:
    for bad in ("api-key=abc", "private-key=abc", "bearer-token=abc"):
        with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
            render_phoenix_operator_ping(_make_input(**{field: bad}))
        assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING", (
            f"{field}={bad!r} must fail closed"
        )


def test_secret_source_ref_never_reaches_shortening(monkeypatch) -> None:
    # Prove the redaction scan fails closed BEFORE source-ref shortening, so a
    # secret can never be hidden inside a middle-elided segment: make shortening
    # blow up if it is ever reached for a secret-bearing input.
    import PHX2.stage30.stage30_12_phoenix_operator_ping_renderer as renderer_mod

    def _must_not_be_called(_value: object) -> str:
        raise AssertionError(
            "source-ref shortening must not be reached for a secret value"
        )

    monkeypatch.setattr(
        renderer_mod, "_shorten_source_ref", _must_not_be_called
    )
    for bad in _CODEX_SECRET_SOURCE_REFS:
        with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
            renderer_mod.render_phoenix_operator_ping(
                _make_input(source_ref=bad)
            )
        assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"


def test_positive_control_long_public_helius_ref_still_renders_shortened() -> None:
    # The normal long public Helius source ref is NOT a secret: it renders,
    # middle-elided, and the full signature never appears.
    body = render_phoenix_operator_ping(
        _make_input(source_ref=_GOLDEN_SOURCE_REF)
    )
    assert _GOLDEN_SIG not in body
    assert (
        "Src: helius:sig:5hMAYVvm" + _ELLIPSIS + "MFV:slot:424620715" in body
    )


# ---------------------------------------------------------------------------
# 5. Source-ref shortening
# ---------------------------------------------------------------------------


def test_long_signature_is_middle_elided() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    # The full 88-char signature must NOT appear; the elided form must.
    assert _GOLDEN_SIG not in body
    assert "Src: helius:sig:5hMAYVvm" + _ELLIPSIS + "MFV:slot:424620715" in body


def test_short_source_ref_segments_are_kept_verbatim() -> None:
    body = render_phoenix_operator_ping(
        _make_input(source_ref="onchain:slot:424620715")
    )
    assert "Src: onchain:slot:424620715" in body


# ---------------------------------------------------------------------------
# 6. Body length cap
# ---------------------------------------------------------------------------


def test_body_is_within_hard_cap() -> None:
    body = render_phoenix_operator_ping(_golden_input())
    assert len(body) <= STAGE30_12_BODY_CHAR_HARD_CAP


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------


def test_renderer_is_deterministic() -> None:
    first = render_phoenix_operator_ping(_golden_input())
    second = render_phoenix_operator_ping(_golden_input())
    assert first == second


# ---------------------------------------------------------------------------
# 8. Tier band display
# ---------------------------------------------------------------------------


def test_tier_band_display_helper_maps_the_three_tiers() -> None:
    assert tier_band_display_for(TIER_TOKEN_TIER_1) == TIER_BAND_DISPLAY_TIER_1
    assert tier_band_display_for(TIER_TOKEN_TIER_2) == TIER_BAND_DISPLAY_TIER_2
    assert tier_band_display_for(TIER_TOKEN_TIER_3) == TIER_BAND_DISPLAY_TIER_3
    assert TIER_BAND_DISPLAY_TIER_1 == "50%–60%"
    assert TIER_BAND_DISPLAY_TIER_2 == "62%–80%"
    assert TIER_BAND_DISPLAY_TIER_3 == "82%–95%"


def test_tier_unknown_band_maps_to_unknown() -> None:
    assert tier_band_display_for(TIER_TOKEN_TIER_UNKNOWN) == DISPLAY_UNKNOWN
    assert tier_band_display_for("nonsense") == DISPLAY_UNKNOWN
    body = render_phoenix_operator_ping(
        _make_input(tier_token=TIER_TOKEN_TIER_UNKNOWN)
    )
    assert "Band: Unknown" in body
    assert "[Tier Unknown]" in body


@pytest.mark.parametrize(
    "tier_token,expected_band",
    (
        (TIER_TOKEN_TIER_1, TIER_BAND_DISPLAY_TIER_1),
        (TIER_TOKEN_TIER_2, TIER_BAND_DISPLAY_TIER_2),
        (TIER_TOKEN_TIER_3, TIER_BAND_DISPLAY_TIER_3),
    ),
)
def test_band_derived_from_tier_token_in_body(
    tier_token: str, expected_band: str
) -> None:
    body = render_phoenix_operator_ping(_make_input(tier_token=tier_token))
    assert f"Band: {expected_band}" in body


def test_explicit_tier_band_display_overrides_derivation() -> None:
    body = render_phoenix_operator_ping(
        _make_input(
            tier_token=TIER_TOKEN_TIER_2, tier_band_display="62.0%–79.9%"
        )
    )
    assert "Band: 62.0%–79.9%" in body


# ---------------------------------------------------------------------------
# 9. Fractional-drop regression (explicit percent, never absolute * 100)
# ---------------------------------------------------------------------------


def test_drop_uses_explicit_fractional_pct_not_absolute_drawdown() -> None:
    # absolute_drawdown is tiny; the explicit fractional percent is -75.39%.
    # The renderer MUST echo the explicit percent and MUST NOT derive -0% from
    # the absolute magnitude (the Stage 30.2 drop helper bug after e32b8ce).
    body = render_phoenix_operator_ping(
        _make_input(
            absolute_drawdown="0.000015902742642997449",
            fractional_drop_pct="-75.39%",
        )
    )
    assert "Drop: -75.39%" in body
    assert "-0%" not in body
    assert "Drop: -0%" not in body


def test_missing_fractional_drop_renders_unknown_not_zero() -> None:
    body = render_phoenix_operator_ping(
        _make_input(absolute_drawdown="0.0000159", fractional_drop_pct=None)
    )
    assert "Drop: Unknown" in body
    assert "-0%" not in body


# ---------------------------------------------------------------------------
# 10. Price formatting
# ---------------------------------------------------------------------------


def test_price_formatting_is_clean_and_trims_trailing_zeros() -> None:
    body = render_phoenix_operator_ping(
        _make_input(current_price="1.5000000000", ath_price="0")
    )
    assert "Now: $1.5" in body
    assert "ATH: $0" in body


def test_malformed_price_renders_unknown() -> None:
    body = render_phoenix_operator_ping(
        _make_input(current_price="not-a-number", ath_price="-3")
    )
    # current_price "not-a-number" contains no forbidden needle but is not
    # decimal text; negative ath is rejected by the formatter.
    assert "Now: Unknown" in body
    assert "ATH: Unknown" in body
