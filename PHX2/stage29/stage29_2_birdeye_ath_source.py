"""Stage 29.2 Birdeye ATH source adapter.

Implements the Stage 27.4 ``AthContextSource`` Protocol by
wrapping a Stage 29.2 HTTP transport call to Birdeye's
``/defi/ohlcv`` endpoint. ATH is taken as the maximum
``items[].h`` (intracandle high) over the bounded lookback
window; the corresponding ``items[].unixTime`` becomes the
``ath_observed_at_utc`` timestamp.

Stage 27.4-boundary error mapping (mirror of the price source):

  * HTTP success (200) + ``data.items`` non-empty + at least one
    ``items[].h`` parseable as canonical decimal text ->
    ``AthSourceSnapshot`` with ``ath_value`` populated ->
    Stage 27.4 produces ``ATH_STATUS_PRESENT``.
  * HTTP success (200) + ``data.items`` empty / missing / no
    parseable ``h`` field -> ``AthSourceSnapshot`` with
    ``ath_value=None`` -> Stage 27.4 produces
    ``ATH_STATUS_UNAVAILABLE`` / ``ATH_REASON_NO_OBSERVATIONS``.
  * HTTP non-2xx / timeout / malformed body / upstream
    ``success: false`` -> raises ``Stage27AthSourceError`` ->
    Stage 27.4 produces ``ATH_STATUS_SOURCE_ERROR``.

``window_starts_post_migration`` is ``True`` iff the caller
proved the lookback start lies at or after the upstream
migration evidence timestamp; ``False`` when the caller
explicitly cannot prove it; ``None`` when no migration evidence
was supplied. Stage 29.2 NEVER claims ``True`` without explicit
proof.

This module imports stdlib (``datetime`` / ``decimal`` /
``typing``) plus the Stage 27.4 Protocol surface + Stage 29.2
constants / models / http transport / readiness. It does NOT
import:

  * Stage 21-28 production code beyond the Stage 27.4 Protocol
    surface,
  * any PHX1 / legacy Phoenix-1 source tree module,
  * any third-party HTTP / wallet / trading / Discord / Telegram
    / X library,
  * ``os`` / the process environment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from PHX2.stage27.price_ath_context_contracts import (
    Stage27AthSourceError,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_DEFAULT_OHLCV_TYPE,
    BIRDEYE_OHLCV_SOURCE_LABEL,
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_REPORTING_UNIT_USD,
    DEFAULT_LOOKBACK_HOURS,
    is_allowed_ohlcv_type,
    is_safe_lookback_hours,
    is_safe_mint,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_MISSING,
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_ATH_STATUS_SOURCE_ERROR,
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeAthSnapshot,
    Stage29_2BirdeyeError,
    build_birdeye_ath_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)


# ---------------------------------------------------------------------------
# Pure helpers (snapshot projection)
# ---------------------------------------------------------------------------


def fetch_birdeye_ath_snapshot(
    *,
    base_mint: str,
    transport: Stage29_2BirdeyeHttpTransport,
    endpoint_secret: Stage29_2BirdeyeEndpointSecret,
    timeout_seconds: int,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    ohlcv_type: str = BIRDEYE_DEFAULT_OHLCV_TYPE,
    now_utc: Optional[datetime] = None,
    migration_timestamp_utc: Optional[str] = None,
) -> Stage29_2BirdeyeAthSnapshot:
    """Fetch a Stage 29.2 Birdeye ATH snapshot for ``base_mint``.

    Returns a Stage 29.2 snapshot record carrying the closed-set
    status + the computed ATH value. NEVER raises -- the
    upstream evidence is projected onto closed-set tokens.

    ``window_starts_post_migration`` is set:

      * ``True`` iff ``migration_timestamp_utc`` is supplied AND
        parses cleanly AND the bounded lookback ``time_from``
        is >= the migration moment,
      * ``False`` iff ``migration_timestamp_utc`` is supplied
        AND parses cleanly AND ``time_from`` precedes the
        migration moment,
      * ``None`` iff ``migration_timestamp_utc`` is not supplied
        (the caller cannot promise post-migration semantics).
    """
    if not is_safe_mint(base_mint):
        return _build_error_ath_snapshot(
            lookback_hours=(
                lookback_hours
                if is_safe_lookback_hours(lookback_hours)
                else 0
            ),
        )
    if not is_safe_timeout_seconds(timeout_seconds):
        return _build_error_ath_snapshot(
            lookback_hours=(
                lookback_hours
                if is_safe_lookback_hours(lookback_hours)
                else 0
            ),
        )
    if not is_safe_lookback_hours(lookback_hours):
        return _build_error_ath_snapshot(lookback_hours=0)
    if not is_allowed_ohlcv_type(ohlcv_type):
        return _build_error_ath_snapshot(
            lookback_hours=lookback_hours,
        )

    resolved_now = now_utc if now_utc is not None else (
        datetime.now(timezone.utc)
    )
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)
    time_to = int(resolved_now.timestamp())
    time_from = time_to - lookback_hours * 3600

    http_result: Stage29_2BirdeyeHttpResult = transport.get(
        endpoint_secret=endpoint_secret,
        path=BIRDEYE_PATH_OHLCV,
        query_params={
            "address": base_mint,
            "type": ohlcv_type,
            "time_from": str(time_from),
            "time_to": str(time_to),
        },
        timeout_seconds=timeout_seconds,
    )

    if http_result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
        return _build_error_ath_snapshot(
            lookback_hours=lookback_hours,
            fetched_at_utc=http_result.fetched_at_utc,
        )

    body = http_result.body
    if body is None:
        return _build_error_ath_snapshot(
            lookback_hours=lookback_hours,
            fetched_at_utc=http_result.fetched_at_utc,
        )

    data = body.get("data")
    if not isinstance(data, dict):
        return _build_missing_ath_snapshot(
            lookback_hours=lookback_hours,
            items_count=0,
        )

    items_raw = data.get("items")
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        return _build_missing_ath_snapshot(
            lookback_hours=lookback_hours,
            items_count=(
                len(items_raw)
                if isinstance(items_raw, list)
                else 0
            ),
        )

    best = _select_best_high_candle(items_raw)
    if best is None:
        return _build_missing_ath_snapshot(
            lookback_hours=lookback_hours,
            items_count=len(items_raw),
        )
    ath_value_text, candle_unix = best
    ath_observed_at_utc = _iso_utc_from_unix(candle_unix)

    window_flag = _window_starts_post_migration(
        time_from_unix=time_from,
        migration_timestamp_utc=migration_timestamp_utc,
    )

    return build_birdeye_ath_snapshot(
        ath_value=ath_value_text,
        ath_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_OHLCV_SOURCE_LABEL,
        ath_observed_at_utc=ath_observed_at_utc,
        window_starts_post_migration=window_flag,
        lookback_hours=lookback_hours,
        items_count=len(items_raw),
        birdeye_ath_status=BIRDEYE_ATH_STATUS_PRESENT,
        birdeye_freshness_status=BIRDEYE_FRESHNESS_STATUS_FRESH,
    )


def _build_error_ath_snapshot(
    *,
    lookback_hours: int,
    fetched_at_utc: Optional[str] = None,
) -> Stage29_2BirdeyeAthSnapshot:
    # ``fetched_at_utc`` is not echoed on the ATH snapshot (the
    # Stage 27.4 AthSourceSnapshot does not carry a fetched-at
    # axis), but the parameter is accepted so the helper can be
    # extended later without an interface change.
    _ = fetched_at_utc
    return build_birdeye_ath_snapshot(
        ath_value=None,
        ath_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_OHLCV_SOURCE_LABEL,
        ath_observed_at_utc=None,
        window_starts_post_migration=None,
        lookback_hours=lookback_hours,
        items_count=0,
        birdeye_ath_status=BIRDEYE_ATH_STATUS_SOURCE_ERROR,
        birdeye_freshness_status=(
            BIRDEYE_FRESHNESS_STATUS_UNKNOWN
        ),
    )


def _build_missing_ath_snapshot(
    *,
    lookback_hours: int,
    items_count: int,
) -> Stage29_2BirdeyeAthSnapshot:
    return build_birdeye_ath_snapshot(
        ath_value=None,
        ath_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_OHLCV_SOURCE_LABEL,
        ath_observed_at_utc=None,
        window_starts_post_migration=None,
        lookback_hours=lookback_hours,
        items_count=items_count,
        birdeye_ath_status=BIRDEYE_ATH_STATUS_MISSING,
        birdeye_freshness_status=(
            BIRDEYE_FRESHNESS_STATUS_UNKNOWN
        ),
    )


def _select_best_high_candle(
    items_raw: list,
) -> Optional[tuple[str, int]]:
    """Iterate the Birdeye OHLCV items and return the
    ``(canonical-decimal-text high, unix_time)`` pair for the
    candle with the maximum parseable ``h`` value. Returns
    ``None`` if no candle has a parseable non-negative ``h``.
    """
    best_dec: Optional[Decimal] = None
    best_text: Optional[str] = None
    best_unix: Optional[int] = None
    for entry in items_raw:
        if not isinstance(entry, dict):
            continue
        h_raw = entry.get("h")
        h_text = _coerce_high_value(h_raw)
        if h_text is None:
            continue
        try:
            h_dec = Decimal(h_text)
        except (InvalidOperation, ValueError):
            continue
        unix_raw = entry.get("unixTime")
        unix_int = _coerce_unix_time(unix_raw)
        if unix_int is None:
            continue
        if best_dec is None or h_dec > best_dec:
            best_dec = h_dec
            best_text = h_text
            best_unix = unix_int
    if best_text is None or best_unix is None:
        return None
    return best_text, best_unix


def _coerce_high_value(raw: object) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (
            raw != raw
            or raw == float("inf")
            or raw == float("-inf")
        ):
            return None
        if raw < 0:
            return None
        return _format_decimal(raw)
    if isinstance(raw, str):
        candidate = raw.strip()
        if candidate == "":
            return None
        try:
            parsed = float(candidate)
        except ValueError:
            return None
        if parsed != parsed:
            return None
        if parsed == float("inf") or parsed == float("-inf"):
            return None
        if parsed < 0:
            return None
        return candidate
    return None


def _format_decimal(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0")
            if text.endswith("."):
                text = text + "0"
        return text
    return str(value)


def _coerce_unix_time(raw: object) -> Optional[int]:
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


def _iso_utc_from_unix(unix_seconds: int) -> str:
    return datetime.fromtimestamp(
        unix_seconds, tz=timezone.utc
    ).isoformat()


def _parse_iso_utc(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 UTC timestamp; return ``None`` on
    failure. Stage 29.2 NEVER raises on a malformed migration
    timestamp; it falls back to ``window_starts_post_migration =
    None`` instead.
    """
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _window_starts_post_migration(
    *,
    time_from_unix: int,
    migration_timestamp_utc: Optional[str],
) -> Optional[bool]:
    if migration_timestamp_utc is None:
        return None
    if not isinstance(migration_timestamp_utc, str):
        return None
    parsed = _parse_iso_utc(migration_timestamp_utc)
    if parsed is None:
        return None
    migration_unix = int(parsed.timestamp())
    return time_from_unix >= migration_unix


# ---------------------------------------------------------------------------
# Stage 27.4 AthContextSource Protocol implementation
# ---------------------------------------------------------------------------


class Stage29_2BirdeyeAthSource:
    """Stage 27.4 ``AthContextSource`` Protocol implementation
    backed by the Stage 29.2 Birdeye HTTP transport
    (``/defi/ohlcv``).

    Constructed with the Stage 29.2 transport + the private
    endpoint-secret + the bounded timeout + the bounded
    lookback. Tests inject a fake transport.
    """

    def __init__(
        self,
        *,
        transport: Stage29_2BirdeyeHttpTransport,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        timeout_seconds: int,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        ohlcv_type: str = BIRDEYE_DEFAULT_OHLCV_TYPE,
        migration_timestamp_utc: Optional[str] = None,
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
        if not is_safe_lookback_hours(lookback_hours):
            raise Stage29_2BirdeyeError(
                "LOOKBACK_HOURS_UNSAFE"
            )
        if not is_allowed_ohlcv_type(ohlcv_type):
            raise Stage29_2BirdeyeError(
                "OHLCV_TYPE_NOT_ALLOWED"
            )
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout_seconds = timeout_seconds
        self._lookback_hours = lookback_hours
        self._ohlcv_type = ohlcv_type
        self._migration_timestamp_utc = migration_timestamp_utc

    def read_ath_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> AthSourceSnapshot:
        """Return a Stage 27.4 ``AthSourceSnapshot`` for the
        given mint.

        The ``pair_quote_asset`` argument is accepted to satisfy
        the Stage 27.4 Protocol but is NOT used to vary the
        Birdeye call; Stage 29.2 always reports in USD.

        Raises ``Stage27AthSourceError`` for the SOURCE_ERROR
        case; returns a snapshot with ``ath_value=None`` for the
        MISSING case.
        """
        _ = pair_quote_asset
        snapshot = self.fetch_snapshot(base_mint=token_mint)
        if (
            snapshot.birdeye_ath_status
            == BIRDEYE_ATH_STATUS_SOURCE_ERROR
        ):
            raise Stage27AthSourceError(
                reason="SOURCE_FAILED",
                source_label=snapshot.source_label,
            )
        return AthSourceSnapshot(
            ath_value=snapshot.ath_value,
            ath_unit=snapshot.ath_unit,
            source_label=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            window_starts_post_migration=(
                snapshot.window_starts_post_migration
            ),
        )

    def fetch_snapshot(
        self,
        *,
        base_mint: str,
    ) -> Stage29_2BirdeyeAthSnapshot:
        """Return the rich Stage 29.2 ATH snapshot for the
        probe artifact path. Never raises.
        """
        return fetch_birdeye_ath_snapshot(
            base_mint=base_mint,
            transport=self._transport,
            endpoint_secret=self._endpoint_secret,
            timeout_seconds=self._timeout_seconds,
            lookback_hours=self._lookback_hours,
            ohlcv_type=self._ohlcv_type,
            migration_timestamp_utc=(
                self._migration_timestamp_utc
            ),
        )


__all__ = (
    "fetch_birdeye_ath_snapshot",
    "Stage29_2BirdeyeAthSource",
)
