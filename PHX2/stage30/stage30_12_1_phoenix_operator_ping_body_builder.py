"""Stage 30.12.1 PHOENIX operator ping body-builder factory.

A pure, offline FACTORY that lets a controlled ceremony feed the committed Stage
30.12 PHOENIX renderer through the EXISTING Stage 30.11.5 ``compact_body_builder``
seam WITHOUT monkey-patching and WITHOUT editing the Stage 30.11 runner / sink /
gate. It is the committed home for the body-builder glue the first no-send
ceremony improvised out-of-repo.

    a ceremony-assembled ``PhoenixOperatorPingContext`` (the rich renderer-only
    fields the committed Stage 30.9.3 gate input lacks: LP / current price / ATH
    price / fractional drop / migration timestamp / provenance ref / age / ...)
      -> ``make_phoenix_operator_ping_body_builder(context)``
          -> renders the committed Stage 30.12 body ONCE, at construction time
             (a renderer fail-closed surfaces HERE, before the runner starts)
          -> returns a ``Callable[[Any], str]`` that, per dispatched candidate,
             verifies the gate input's token mint matches the context and returns
             the PRE-RENDERED body (it NEVER renders again, NEVER fetches, NEVER
             opens a socket, NEVER reads the process environment or a clock)

Why render at construction, not per call. The committed Stage 30.11.3 private
sink calls ``compact_body_builder(gate_input)`` with NO try / except, so a
renderer validation error raised inside that call would propagate UNHANDLED
through the seam and the bounded runner mid-dispatch. Rendering ONCE at
construction moves every Stage 30.12 fail-closed (a missing / quote-mint /
non-base58 token mint, a missing tier token, a forbidden URL / credential /
secret-bearing display field, an over-cap body) to the ceremony, BEFORE the
runner is composed -- so the runner only ever receives a total, already-validated
builder that returns a constant string. The ONLY per-call failure is the
token-mint-mismatch guard below: a deliberate, should-never-happen fail-closed
that refuses to emit one candidate's body for a different dispatched candidate.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the two committed Stage 30.12 siblings (the input record + the
    closed-set error from the models, and the renderer). It imports NO Stage
    30.9.3 / Stage 30.10 / Stage 30.11 type -- the per-candidate gate input is
    read DUCK-TYPED (``getattr``) so the slice stays a clean LEAF and adds no
    coupling between Stage 30.11 and Stage 30.12.
  * No ``os`` import; no environment read; no ``getenv`` / environ access.
  * No network, no socket; no Discord / webhook / transport surface.
  * No clock / time import; no filesystem write; no while loop / daemon / thread.
  * No wallet / trading surface.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, Optional

from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    PhoenixOperatorPingInput,
    Stage30_12PhoenixOperatorPingError,
)
from PHX2.stage30.stage30_12_phoenix_operator_ping_renderer import (
    render_phoenix_operator_ping,
)


STAGE30_12_1_MINOR_VERSION: str = "30.12.1"


# Closed-set Stage 30.12.1 fail-closed reason tokens (carried on the committed
# Stage 30.12 error). Distinct from the renderer's own reason tokens.
STAGE30_12_1_CONTEXT_INVALID_TYPE_REASON: str = (
    "STAGE30_12_1_CONTEXT_INVALID_TYPE"
)
STAGE30_12_1_TOKEN_MINT_MISMATCH_REASON: str = (
    "STAGE30_12_1_TOKEN_MINT_MISMATCH"
)


# ---------------------------------------------------------------------------
# Immutable Stage 30.12.1 renderer context
# ---------------------------------------------------------------------------


class PhoenixOperatorPingContext(NamedTuple):
    """Immutable Stage 30.12.1 PHOENIX renderer context.

    A passive carrier of the rich renderer-only fields a ceremony has honestly
    revalidated -- the fields the committed Stage 30.9.3 gate input does NOT
    carry at the body-builder boundary (LP / current price / ATH price / ATH MC
    display / fractional drop / migration timestamp / provenance ref / age /
    symbol), plus
    the two required identity fields. It maps one-to-one onto the committed Stage
    30.12 ``PhoenixOperatorPingInput`` (the renderer owns all formatting,
    safe-shape validation, and fail-closed behavior). It carries no secret, no
    raw payload, no host, and no transport destination; a forbidden / secret
    display value is rejected by the renderer at build time, never rendered.

    ``token_mint`` and ``tier_token`` are REQUIRED; every other field is OPTIONAL
    and defaults to ``None`` (the renderer renders a missing optional as the
    literal ``Unknown`` -- never a fabricated value).
    """

    token_mint: str
    tier_token: str
    symbol_or_name: Optional[str] = None
    migration_confirmed: Optional[bool] = None
    migration_time_utc: Optional[str] = None
    market_cap_display: Optional[str] = None
    liquidity_display: Optional[str] = None
    current_price: Optional[str] = None
    ath_price: Optional[str] = None
    absolute_drawdown: Optional[str] = None
    fractional_drop_pct: Optional[str] = None
    tier_band_display: Optional[str] = None
    basis_display: Optional[str] = None
    source_ref: Optional[str] = None
    age_display: Optional[str] = None
    ath_market_cap_display: Optional[str] = None


# The Stage 30.11.5-seam-compatible compact body builder type: a callable that,
# given a duck-typed dispatched gate input / payload, returns the operator body.
PhoenixOperatorPingBodyBuilder = Callable[[Any], str]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def context_to_input(
    context: PhoenixOperatorPingContext,
) -> PhoenixOperatorPingInput:
    """Map a ``PhoenixOperatorPingContext`` one-to-one onto a committed Stage
    30.12 ``PhoenixOperatorPingInput``.

    Pure / deterministic. Raises ``Stage30_12PhoenixOperatorPingError`` (reason
    ``STAGE30_12_1_CONTEXT_INVALID_TYPE``) when handed a non-context record; it
    NEVER fabricates a field.
    """
    if not isinstance(context, PhoenixOperatorPingContext):
        raise Stage30_12PhoenixOperatorPingError(
            STAGE30_12_1_CONTEXT_INVALID_TYPE_REASON
        )
    return PhoenixOperatorPingInput(
        token_mint=context.token_mint,
        tier_token=context.tier_token,
        symbol_or_name=context.symbol_or_name,
        migration_confirmed=context.migration_confirmed,
        migration_time_utc=context.migration_time_utc,
        market_cap_display=context.market_cap_display,
        liquidity_display=context.liquidity_display,
        current_price=context.current_price,
        ath_price=context.ath_price,
        absolute_drawdown=context.absolute_drawdown,
        fractional_drop_pct=context.fractional_drop_pct,
        tier_band_display=context.tier_band_display,
        basis_display=context.basis_display,
        source_ref=context.source_ref,
        age_display=context.age_display,
        ath_market_cap_display=context.ath_market_cap_display,
    )


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def make_phoenix_operator_ping_body_builder(
    context: PhoenixOperatorPingContext,
) -> PhoenixOperatorPingBodyBuilder:
    """Build a Stage 30.11.5-seam-compatible compact body builder that renders
    the committed Stage 30.12 PHOENIX body for ``context``.

    Renders ONCE here, at construction. Every committed Stage 30.12 fail-closed
    therefore surfaces NOW (it raises ``Stage30_12PhoenixOperatorPingError``
    BEFORE the runner is composed), never inside the no-try/except Stage 30.11.3
    sink call mid-dispatch:

      * ``STAGE30_12_1_CONTEXT_INVALID_TYPE``  -- ``context`` is not a
                                                  ``PhoenixOperatorPingContext``.
      * a renderer reason (``TOKEN_MINT_MISSING`` / ``TOKEN_MINT_IS_WSOL_QUOTE``
        / ``TOKEN_MINT_NOT_BASE58`` / ``TIER_TOKEN_MISSING`` /
        ``DISPLAY_TEXT_FORBIDDEN_SUBSTRING`` / ``BODY_EXCEEDS_HARD_CAP``) -- the
        committed renderer rejected the context-derived input.

    The returned callable is total and pure: given a duck-typed dispatched gate
    input, it verifies ``gate_input.token_mint`` equals the context token mint
    and returns the PRE-RENDERED body verbatim. It NEVER re-renders, NEVER
    fetches, NEVER opens a socket, NEVER reads the environment or a clock. A
    mismatch (a different candidate than the one the body was rendered for) is a
    deliberate fail-closed: it raises ``Stage30_12PhoenixOperatorPingError``
    (reason ``STAGE30_12_1_TOKEN_MINT_MISMATCH``) rather than emit one
    candidate's body for another. The builder reads ONLY the gate input's
    ``token_mint`` (duck-typed); it imports / references no Stage 30.9.3 / 30.11
    type, so the slice stays a clean leaf.
    """
    # Render ONCE, at construction. A Stage 30.12 fail-closed raises HERE.
    pre_rendered_body = render_phoenix_operator_ping(context_to_input(context))
    expected_token_mint = context.token_mint

    def _body_builder(gate_input: Any) -> str:
        actual_token_mint = getattr(gate_input, "token_mint", None)
        if actual_token_mint != expected_token_mint:
            raise Stage30_12PhoenixOperatorPingError(
                STAGE30_12_1_TOKEN_MINT_MISMATCH_REASON
            )
        return pre_rendered_body

    return _body_builder


__all__ = (
    "STAGE30_12_1_MINOR_VERSION",
    "STAGE30_12_1_CONTEXT_INVALID_TYPE_REASON",
    "STAGE30_12_1_TOKEN_MINT_MISMATCH_REASON",
    "PhoenixOperatorPingContext",
    "PhoenixOperatorPingBodyBuilder",
    "context_to_input",
    "make_phoenix_operator_ping_body_builder",
)
