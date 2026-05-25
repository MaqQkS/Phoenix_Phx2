"""Stage 29.2 Birdeye price source adapter.

Implements the Stage 27.4 ``PriceContextSource`` Protocol by
wrapping a Stage 29.2 HTTP transport call to Birdeye's
``/defi/price`` endpoint. Returns a Stage 27.4
``PriceSourceSnapshot`` so the existing Stage 27.4 reader can
consume Stage 29.2 evidence without any Stage 27 production
change.

Stage 27.4-boundary error mapping:

  * HTTP success (200) + ``data.value`` is a parseable
    canonical decimal-text price -> ``PriceSourceSnapshot``
    with ``price_value`` populated -> Stage 27.4 produces
    ``PRICE_STATUS_PRESENT`` / ``PRICE_REASON_OK``.
  * HTTP success (200) + ``data.value`` is missing / null /
    non-numeric -> ``PriceSourceSnapshot`` with
    ``price_value=None`` -> Stage 27.4 produces
    ``PRICE_STATUS_UNAVAILABLE`` /
    ``PRICE_REASON_SOURCE_RETURNED_NONE``.
  * HTTP non-2xx / timeout / failed-connect / malformed body /
    upstream ``success: false`` -> raises
    ``Stage27PriceSourceError`` -> Stage 27.4 produces
    ``PRICE_STATUS_SOURCE_ERROR`` / ``PRICE_REASON_SOURCE_FAILED``.

Stage 29.2 NEVER fabricates a price. The
``Stage29_2BirdeyePriceSnapshot`` carries the upstream
evidence in Stage 29.2's own closed-set vocabulary for the
probe artifact; the Stage 27.4 ``PriceSourceSnapshot``
projection is the narrow view the Stage 27.4 chain consumes.

This module imports stdlib (``typing``) plus the Stage 27.4
Protocol surface + Stage 29.2 constants / models / http
transport / readiness. It does NOT import:

  * Stage 21-28 production code beyond the Stage 27.4 Protocol
    surface,
  * any PHX1 / legacy Phoenix-1 source tree module,
  * any third-party HTTP / wallet / trading / Discord / Telegram
    / X library,
  * ``os`` / the process environment.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.price_ath_context_contracts import (
    Stage27PriceSourceError,
)
from PHX2.stage27.price_ath_context_reader import (
    PriceSourceSnapshot,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PRICE_SOURCE_LABEL,
    BIRDEYE_REPORTING_UNIT_USD,
    is_safe_mint,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
    BIRDEYE_PRICE_STATUS_MISSING,
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_SOURCE_ERROR,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeError,
    Stage29_2BirdeyePriceSnapshot,
    build_birdeye_price_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)


# ---------------------------------------------------------------------------
# Pure helpers (snapshot projection)
# ---------------------------------------------------------------------------


def fetch_birdeye_price_snapshot(
    *,
    base_mint: str,
    transport: Stage29_2BirdeyeHttpTransport,
    endpoint_secret: Stage29_2BirdeyeEndpointSecret,
    timeout_seconds: int,
) -> Stage29_2BirdeyePriceSnapshot:
    """Fetch a Stage 29.2 Birdeye price snapshot for ``base_mint``.

    Returns a Stage 29.2 snapshot record carrying the closed-set
    status + the (decoded) price value. NEVER raises -- the
    upstream evidence is projected onto closed-set tokens. The
    Stage 27.4 ``PriceContextSource`` adapter wraps this helper
    and raises ``Stage27PriceSourceError`` for the ``SOURCE_ERROR``
    case.
    """
    if not is_safe_mint(base_mint):
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=None,
            upstream_update_unix_time=None,
            birdeye_price_status=(
                BIRDEYE_PRICE_STATUS_SOURCE_ERROR
            ),
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )
    if not is_safe_timeout_seconds(timeout_seconds):
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=None,
            upstream_update_unix_time=None,
            birdeye_price_status=(
                BIRDEYE_PRICE_STATUS_SOURCE_ERROR
            ),
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )

    http_result: Stage29_2BirdeyeHttpResult = transport.get(
        endpoint_secret=endpoint_secret,
        path=BIRDEYE_PATH_PRICE,
        query_params={"address": base_mint},
        timeout_seconds=timeout_seconds,
    )

    if http_result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=http_result.fetched_at_utc,
            upstream_update_unix_time=None,
            birdeye_price_status=(
                BIRDEYE_PRICE_STATUS_SOURCE_ERROR
            ),
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )

    body = http_result.body
    if body is None:
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=http_result.fetched_at_utc,
            upstream_update_unix_time=None,
            birdeye_price_status=(
                BIRDEYE_PRICE_STATUS_SOURCE_ERROR
            ),
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )

    data = body.get("data")
    if not isinstance(data, dict):
        # Stage 29.2 maps "data is missing / non-dict" to MISSING,
        # not SOURCE_ERROR -- the HTTP layer succeeded but the
        # response had no usable data axis.
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=http_result.fetched_at_utc,
            upstream_update_unix_time=None,
            birdeye_price_status=BIRDEYE_PRICE_STATUS_MISSING,
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )

    value_raw = data.get("value")
    price_value = _coerce_price_value(value_raw)

    update_unix_raw = data.get("updateUnixTime")
    upstream_update_unix_time = _coerce_unix_time(
        update_unix_raw
    )

    if price_value is None:
        return build_birdeye_price_snapshot(
            price_value=None,
            price_unit=BIRDEYE_REPORTING_UNIT_USD,
            source_label=BIRDEYE_PRICE_SOURCE_LABEL,
            fetched_at_utc=http_result.fetched_at_utc,
            upstream_update_unix_time=upstream_update_unix_time,
            birdeye_price_status=BIRDEYE_PRICE_STATUS_MISSING,
            birdeye_freshness_status=(
                BIRDEYE_FRESHNESS_STATUS_UNKNOWN
            ),
        )

    return build_birdeye_price_snapshot(
        price_value=price_value,
        price_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_PRICE_SOURCE_LABEL,
        fetched_at_utc=http_result.fetched_at_utc,
        upstream_update_unix_time=upstream_update_unix_time,
        birdeye_price_status=BIRDEYE_PRICE_STATUS_PRESENT,
        birdeye_freshness_status=BIRDEYE_FRESHNESS_STATUS_FRESH,
    )


def _coerce_price_value(raw: object) -> Optional[str]:
    """Return canonical decimal text from a Birdeye ``data.value``
    field, or ``None`` when the value is missing / non-numeric.

    Stage 29.2 NEVER returns ``"0"`` / ``"0.0"`` for a missing
    upstream value: a true ``0`` reading from Birdeye is
    preserved as ``"0"`` (the Stage 27.4 reader will then
    surface ``PRICE_STATUS_PRESENT`` with the literal zero, which
    is semantically a valid present price).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        # JSON booleans must never project to a numeric price.
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (
            raw != raw  # NaN check
            or raw == float("inf")
            or raw == float("-inf")
        ):
            return None
        if raw < 0:
            # Negative prices are nonsense; treat as missing.
            return None
        # Render as canonical decimal text via repr-style format.
        return _format_decimal(raw)
    if isinstance(raw, str):
        # Some upstream APIs return numeric strings; accept iff
        # the string parses to a non-negative finite number.
        candidate = raw.strip()
        if candidate == "":
            return None
        try:
            parsed = float(candidate)
        except ValueError:
            return None
        if parsed != parsed:  # NaN
            return None
        if parsed == float("inf") or parsed == float("-inf"):
            return None
        if parsed < 0:
            return None
        return candidate
    return None


def _format_decimal(value: object) -> str:
    """Render a non-negative numeric value as canonical decimal
    text. Used only for Birdeye numeric (int/float) responses;
    string responses are passed through unchanged after
    validation.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # ``repr`` on a float gives the shortest round-tripping
        # decimal representation; Stage 29.2 prefers this over
        # ``str`` because ``str`` may emit scientific notation
        # for tiny values.
        text = format(value, "f")
        # Trim trailing zeros after a decimal point, but keep at
        # least one digit after the point if a point exists.
        if "." in text:
            text = text.rstrip("0")
            if text.endswith("."):
                text = text + "0"
        return text
    return str(value)


def _coerce_unix_time(raw: object) -> Optional[int]:
    """Return a non-negative int for a Birdeye unix-time-like
    field, or ``None`` when missing / out-of-range.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        if raw < 0:
            return None
        return raw
    if isinstance(raw, float):
        if raw != raw or raw == float("inf") or raw < 0:
            return None
        return int(raw)
    if isinstance(raw, str):
        candidate = raw.strip()
        if candidate == "":
            return None
        try:
            parsed = int(candidate)
        except ValueError:
            return None
        if parsed < 0:
            return None
        return parsed
    return None


# ---------------------------------------------------------------------------
# Stage 27.4 PriceContextSource Protocol implementation
# ---------------------------------------------------------------------------


class Stage29_2BirdeyePriceSource:
    """Stage 27.4 ``PriceContextSource`` Protocol implementation
    backed by the Stage 29.2 Birdeye HTTP transport.

    Constructed with the Stage 29.2 transport + the private
    endpoint-secret + the bounded timeout. Tests inject a fake
    transport to drive every branch deterministically.
    """

    def __init__(
        self,
        *,
        transport: Stage29_2BirdeyeHttpTransport,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        timeout_seconds: int,
    ) -> None:
        if not isinstance(
            endpoint_secret,
            Stage29_2BirdeyeEndpointSecret,
        ):
            raise Stage29_2BirdeyeError(
                "ENDPOINT_SECRET_TYPE_INVALID"
            )
        if not is_safe_timeout_seconds(timeout_seconds):
            raise Stage29_2BirdeyeError(
                "TIMEOUT_SECONDS_UNSAFE"
            )
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout_seconds = timeout_seconds

    def read_price_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> PriceSourceSnapshot:
        """Return a Stage 27.4 ``PriceSourceSnapshot`` for the
        given mint.

        The ``pair_quote_asset`` argument is accepted to satisfy
        the Stage 27.4 Protocol but is NOT used to vary the
        Birdeye call: Stage 29.2 always reports in USD, and the
        Stage 27.4 reader handles unit-mismatch logic.

        Raises ``Stage27PriceSourceError`` when the upstream
        evidence is a SOURCE_ERROR (HTTP failure / timeout /
        malformed body / Birdeye ``success: false``). Returns
        a snapshot with ``price_value=None`` for the MISSING
        case (HTTP success but no usable ``data.value``).
        """
        # ``pair_quote_asset`` is intentionally unused by Stage 29.2;
        # it is part of the Stage 27.4 Protocol signature and
        # consumed by the Stage 27.4 reader's unit-matching logic.
        _ = pair_quote_asset

        snapshot = self.fetch_snapshot(base_mint=token_mint)
        if (
            snapshot.birdeye_price_status
            == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
        ):
            raise Stage27PriceSourceError(
                reason="SOURCE_FAILED",
                source_label=snapshot.source_label,
            )
        return PriceSourceSnapshot(
            price_value=snapshot.price_value,
            price_unit=snapshot.price_unit,
            source_label=snapshot.source_label,
            fetched_at_utc=snapshot.fetched_at_utc,
        )

    def fetch_snapshot(
        self,
        *,
        base_mint: str,
    ) -> Stage29_2BirdeyePriceSnapshot:
        """Return the rich Stage 29.2 snapshot record for the
        probe artifact path. Never raises.
        """
        return fetch_birdeye_price_snapshot(
            base_mint=base_mint,
            transport=self._transport,
            endpoint_secret=self._endpoint_secret,
            timeout_seconds=self._timeout_seconds,
        )


__all__ = (
    "fetch_birdeye_price_snapshot",
    "Stage29_2BirdeyePriceSource",
)
