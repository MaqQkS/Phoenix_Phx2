"""Stage 30.4.3 Birdeye token-overview market-context source bridge.

Stage 30.4.3 ships ONE offline-shaped source bridge that implements
the Stage 30.4.1 ``Stage30_4MarketContextSourceProtocol`` surface
(``read(token_mint) -> Optional[Stage30_4MarketContextSourceReading]``)
by mapping a Birdeye ``/defi/token_overview`` snapshot onto the
Stage 30.4 compact market-context reading.

Placement split (locked by the Stage 30.4.3 plan):

  * Stage 29.2 owns the safe Birdeye HTTP transport and the allowed
    endpoint-path surface (``birdeye_constants.BIRDEYE_ALLOWED_PATHS``
    now carries ``/defi/token_overview``).
  * Stage 30.4.3 (this module) owns ONLY the mapping bridge: it asks
    the injected Stage 29.2 transport for one token-overview snapshot
    and projects the current market-cap + liquidity fields onto a
    Stage 30.4.1 reading. It opens no connection itself, reads no
    process environment, and constructs no transport.

Field policy:

  * Current MC is read defensively from ``mc`` / ``marketCap`` /
    ``market_cap`` (first spelling that yields a usable value wins).
  * Liquidity is read defensively from ``liquidity`` /
    ``liquidityUsd`` / ``liquidity_usd``.
  * Accepted numeric values are canonicalized to decimal text.
    ``0`` is a valid reading and is preserved as ``"0"``.
  * A present-but-bad provider value (boolean, ``NaN``, infinity,
    negative, or otherwise malformed) becomes ``None`` -- the
    Stage 30.4.1 adapter resolves ``None`` to Unknown, NEVER to an
    ERROR status and NEVER to ``0``. A missing field is likewise
    Unknown, never ``0``.
  * Net flow stays deferred at Stage 30.4.3: ``net_flow_usd_value``
    is ``None`` and ``net_flow_basis`` is ``UNKNOWN`` so the compact
    ping renders ``Net: Unknown``.

The reading carries NO raw response body, NO resolved request URL,
NO endpoint credential, and NO request-header text. Only canonical
decimal text (or ``None``), the closed-set net-flow-basis token, the
safe-shape source label, the transport's client-clock observed-at
timestamp, the ``stale`` flag, and an optional source-reason token
are ever populated.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports ONLY the four approved Stage 29.2 modules
    (``birdeye_constants`` / ``stage29_2_birdeye_http_transport`` /
    ``stage29_2_birdeye_models`` / ``stage29_2_birdeye_readiness``)
    plus the Stage 30.4.1 source-protocol + models siblings.
  * No process-env read, no live secret access (the endpoint secret
    is injected and only ever forwarded to the injected transport).
  * No network surface in this module (no ``urllib`` / ``requests`` /
    ``httpx`` / ``aiohttp`` / ``socket`` / ``grpc`` / ``os`` import).
  * No Discord / webhook / Telegram / X / social / wallet / trading
    / public-routing surface.
  * No PHX1 import. No Stage 21-28 import. No Stage 29 import beyond
    the approved four.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_TOKEN_OVERVIEW,
    is_safe_mint,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_UNKNOWN,
)
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)


# ---------------------------------------------------------------------------
# Stage 30.4.3 source label + defensive field-spelling order
# ---------------------------------------------------------------------------


# Safe-shape source label echoed on every reading. Passes the Stage
# 30.4.1 adapter's source-label gate (``[A-Za-z0-9_-]{1,64}``). NEVER
# a URL, host, or credential.
STAGE30_4_3_BIRDEYE_SOURCE_LABEL: str = "birdeye_token_overview"


# Current-market-cap field spellings, in preference order. The bridge
# uses the first spelling that yields a usable canonical value.
_MARKET_CAP_KEYS: tuple = ("mc", "marketCap", "market_cap")


# Liquidity field spellings, in preference order.
_LIQUIDITY_KEYS: tuple = ("liquidity", "liquidityUsd", "liquidity_usd")


# ---------------------------------------------------------------------------
# Canonicalization helpers
# ---------------------------------------------------------------------------


def _format_canonical(parsed: Decimal) -> str:
    """Render a non-negative finite ``Decimal`` as canonical decimal
    text matching the Stage 30.4.1 adapter's unsigned pattern
    (``(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?``).

    Uses fixed-point formatting (never scientific notation), strips a
    redundant fractional part, and renders zero as exactly ``"0"``.
    """
    text = format(parsed, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
        if text == "":
            text = "0"
    return text


def _canonicalize_nonneg_usd(raw: object) -> Optional[str]:
    """Return canonical non-negative decimal text for ``raw``, or
    ``None``.

    Returns ``None`` for a missing value (``None``) AND for every
    present-but-bad value: a boolean, ``NaN``, positive / negative
    infinity, a negative magnitude, an empty string, or any
    otherwise-unparseable input. Per Stage 30.4.3 policy both missing
    and present-but-bad collapse to ``None`` so the adapter resolves
    the slot to Unknown (never ERROR, never ``0``).

    A genuine zero (``0`` / ``0.0`` / ``"0"``) is valid and is
    preserved as ``"0"``.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        # A boolean is a provider type-confusion; reject it (Unknown).
        return None
    if isinstance(raw, int):
        candidate = str(raw)
    elif isinstance(raw, float):
        # Reject the non-finite floats before handing to Decimal so a
        # provider ``NaN`` / ``Infinity`` cannot slip through.
        if raw != raw:
            return None
        if raw == float("inf") or raw == float("-inf"):
            return None
        candidate = repr(raw)
    elif isinstance(raw, str):
        candidate = raw.strip()
        if candidate == "":
            return None
    else:
        return None
    try:
        parsed = Decimal(candidate)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    if parsed < 0:
        return None
    return _format_canonical(parsed)


def _extract_first_valid(
    data: dict, keys: tuple
) -> Optional[str]:
    """Return the canonical decimal text for the first spelling in
    ``keys`` that is present on ``data`` AND yields a usable value.

    Returns ``None`` when no spelling is present or every present
    spelling canonicalizes to ``None`` (missing / present-but-bad).
    """
    for key in keys:
        if key not in data:
            continue
        canonical = _canonicalize_nonneg_usd(data[key])
        if canonical is not None:
            return canonical
    return None


# ---------------------------------------------------------------------------
# Stage 30.4.3 Birdeye token-overview source
# ---------------------------------------------------------------------------


class Stage30_4_3BirdeyeMarketContextSource:
    """Stage 30.4.1 ``Stage30_4MarketContextSourceProtocol`` source
    backed by the Stage 29.2 Birdeye ``/defi/token_overview`` call.

    Constructed with the injected Stage 29.2 transport, the private
    endpoint-secret, and the bounded timeout. Tests inject a fake
    transport plus a canned ``Stage29_2BirdeyeHttpResult``. The
    bridge forwards the endpoint-secret to the transport unchanged
    and NEVER reveals it itself.
    """

    def __init__(
        self,
        *,
        transport: Stage29_2BirdeyeHttpTransport,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        timeout_seconds: int,
    ) -> None:
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout_seconds = timeout_seconds

    def read(
        self, token_mint: str
    ) -> Optional[Stage30_4MarketContextSourceReading]:
        """Return a Stage 30.4.1 market-context reading for
        ``token_mint``, or ``None`` when the source had nothing
        usable to report.

        Returns ``None`` (the adapter resolves to Unknown /
        UNAVAILABLE) for: an unsafe-shape mint, an unsafe timeout, a
        transport refusal, a missing body, or a missing / non-dict
        ``data`` object. A present body with a usable / absent MC or
        LP yields a reading; a present-but-bad MC or LP is mapped to
        ``None`` on the reading (Unknown), never to an ERROR value.
        """
        if not is_safe_mint(token_mint):
            return None
        if not is_safe_timeout_seconds(self._timeout_seconds):
            return None

        http_result: Stage29_2BirdeyeHttpResult = self._transport.get(
            endpoint_secret=self._endpoint_secret,
            path=BIRDEYE_PATH_TOKEN_OVERVIEW,
            query_params={"address": token_mint},
            timeout_seconds=self._timeout_seconds,
        )

        if http_result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            return None

        body = http_result.body
        if body is None:
            return None

        data = body.get("data")
        if not isinstance(data, dict):
            return None

        market_cap_value = _extract_first_valid(
            data, _MARKET_CAP_KEYS
        )
        liquidity_value = _extract_first_valid(
            data, _LIQUIDITY_KEYS
        )

        return Stage30_4MarketContextSourceReading(
            market_cap_usd_value=market_cap_value,
            liquidity_usd_value=liquidity_value,
            # Net flow stays deferred at Stage 30.4.3.
            net_flow_usd_value=None,
            net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
            source_label=STAGE30_4_3_BIRDEYE_SOURCE_LABEL,
            observed_at_utc=http_result.fetched_at_utc,
            stale=False,
            source_reason=None,
        )


__all__ = (
    "STAGE30_4_3_BIRDEYE_SOURCE_LABEL",
    "Stage30_4_3BirdeyeMarketContextSource",
)
