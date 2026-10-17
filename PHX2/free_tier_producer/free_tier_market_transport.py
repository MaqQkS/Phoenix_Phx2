"""free_tier_market_transport.py — FREE-TIER market data behind the committed Birdeye transport seam.

OUT-OF-REPO operator glue for the PHX2 live free-tier producer. Implements the committed
``Stage29_2BirdeyeHttpTransport`` Protocol (``get(endpoint_secret=..., path=..., query_params=...,
timeout_seconds=...) -> Stage29_2BirdeyeHttpResult``) so the ENTIRE committed market/ATH/dip-gate
lineage (Stage 29.2 price source, Stage 30.4.3 market-context source, Stage 30.11.11 anchored-ATH
fetch, Stage 30.11.13 composer) runs UNCHANGED over free, keyless public market data:

  * ``/defi/price``          -> free public token-pairs lookup (price of the deepest solana pool)
  * ``/defi/token_overview`` -> same lookup (marketCap, with FDV fallback; liquidity.usd)
  * ``/defi/ohlcv``          -> free public pool OHLCV candles (minute/hour), filtered to the
                                requested ``[time_from, time_to]`` window, projected to the
                                committed ``{"h": <high>, "unixTime": <ts>}`` item shape

This mirrors the proven Build #27/#28 pattern (a path-routed transport returning Birdeye-shaped
bodies) with REAL free-tier data instead of canned constants. The committed sources keep doing ALL
parsing/validation; a missing/invalid upstream value stays missing (fail-closed at the composer).

NO API key is required. NO paid provider is used. An OPTIONAL fallback transport (e.g. the real
Stage 29.2 urllib transport, if the operator's env has a key) may be injected; when present it is
consulted ONLY after the free path produced no usable body. Default: no fallback.

REDACTION DISCIPLINE: provider host names exist ONLY inside this module's code and in-memory URLs.
No URL, no host substring, and no provider name is ever placed in a return body, an exception
message, a stat, or an artifact (the danger-needle scanner bans "://", provider names, etc.).
Closed-set basis/status tokens only. The endpoint secret argument is IGNORED by the free path
(never dialed, never read beyond identity) and is never serialized.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PHX2.stage29.birdeye_constants import (  # committed, read-only  # noqa: E402
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (  # noqa: E402
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (  # noqa: E402
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (  # noqa: E402
    Stage29_2BirdeyeEndpointSecret,
)

# Shape-valid FAKE creds for the committed source constructors (same pattern as the proven Build 29
# fakes). The free transport NEVER dials them and NEVER serializes them into any artifact.
_PLACEHOLDER_KEY = "ft00free11tier22market33data44xx"
_PLACEHOLDER_HOST = "free-tier-market.invalid"  # host only; never dialed

# Free provider endpoints (in-memory only; NEVER echoed into artifacts/errors/stats).
_PAIRS_URL_FMT = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
_OHLCV_URL_FMT = (
    "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}"
    "/ohlcv/{timeframe}?aggregate={aggregate}&before_timestamp={before}"
    "&limit={limit}&currency=usd"
)
_HTTP_HEADERS = {"accept": "application/json", "User-Agent": "phx2-free-tier/1"}

# Closed-set source stat labels (redaction-safe; no provider name).
SOURCE_LABEL_PAIRS = "FREE_PAIRS_LOOKUP"
SOURCE_LABEL_OHLCV = "FREE_OHLCV_LOOKUP"

# Sentinel distinguishing "the pairs lookup FAILED" (-> refusal, fallback eligible) from
# "the lookup worked but the token has no usable pool" (-> honest no-data body).
_LOOKUP_FAILED = object()


def build_free_tier_endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    """Shape-valid placeholder secret the committed source constructors require. The free
    transport ignores it entirely; it is never dialed, printed, or persisted."""
    return Stage29_2BirdeyeEndpointSecret(
        _api_key=_PLACEHOLDER_KEY, _base_url="https://" + _PLACEHOLDER_HOST
    )


def _default_urlopen(url: str, timeout_seconds: float) -> Tuple[int, bytes]:
    """Real read-only GET. Returns (status_code, raw_bytes) — an HTTP error status (429, 5xx, …)
    is RETURNED as a status, not raised, so the caller can count rate-limit pressure precisely.
    Raises only on transport-level failure (DNS/TLS/timeout)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=dict(_HTTP_HEADERS), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return int(getattr(resp, "status", 200) or 200), resp.read()
    except urllib.error.HTTPError as err:
        return int(err.code), b""


class FreeTierMarketTransport:
    """Path-routed free-tier market transport (committed Birdeye transport Protocol).

    Injectables (all optional; real defaults):
      * ``urlopen_fn(url, timeout_seconds) -> (status, bytes)`` — selftests inject a canned fake.
      * ``now_fn`` / ``monotonic_fn`` / ``sleep_fn`` — clocks + pacing (fakes in selftests).
      * ``fallback_transport`` — an OPTIONAL committed-Protocol transport consulted only when the
        free path yields no usable body (e.g. the real Stage 29.2 urllib transport when the
        operator's env has a key). Default None = pure free tier.
    """

    def __init__(
        self,
        *,
        urlopen_fn: Optional[Callable[[str, float], Tuple[int, bytes]]] = None,
        now_fn: Callable[[], float] = time.time,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        fallback_transport: Any = None,
        fallback_endpoint_secret: Any = None,
        pairs_min_interval_seconds: float = 0.25,
        ohlcv_min_interval_seconds: float = 2.1,
        pair_cache_ttl_seconds: float = 20.0,
        ohlcv_cache_ttl_seconds: float = 45.0,
        max_calls_total: Optional[int] = 200000,
        physical_request_meter: Any = None,
    ) -> None:
        self._urlopen = urlopen_fn or _default_urlopen
        # Optional shared physical-request counter. Installed ONLY when this
        # transport sits behind the paid-primary market scheduler as its
        # keyless fallback, so the scheduler charges the calls it causes here
        # exactly as it charges the paid ones. In pure free-tier mode there is
        # no scheduler to charge them, so no meter is installed and nothing
        # would be left unreconciled.
        self._physical_meter = physical_request_meter
        self._now = now_fn
        self._mono = monotonic_fn
        self._sleep = sleep_fn
        self._fallback = fallback_transport
        self._fallback_secret = fallback_endpoint_secret
        self._pairs_min_interval = float(pairs_min_interval_seconds)
        self._ohlcv_min_interval = float(ohlcv_min_interval_seconds)
        self._pair_ttl = float(pair_cache_ttl_seconds)
        self._ohlcv_ttl = float(ohlcv_cache_ttl_seconds)
        # ``None`` means UNBOUNDED (the RUN_FOREVER market-budget posture).
        # ``0`` keeps its historical meaning of "refuse every call" -- the
        # free-tier bounded-run behaviour and its selftest depend on it, so
        # the sentinel is deliberately NOT overloaded onto zero here.
        self._max_calls_total = (
            None if max_calls_total is None else int(max_calls_total))
        self._lock = threading.Lock()
        self._last_call_mono: Dict[str, float] = {}
        self._pair_cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
        self._ohlcv_cache: Dict[Tuple[str, int, int, str], Tuple[float, List[Dict[str, Any]]]] = {}
        self._counters: Dict[str, int] = {
            "http_calls_total": 0,
            "pairs_calls": 0,
            "ohlcv_calls": 0,
            "cache_hits": 0,
            "http_errors": 0,
            "http_429": 0,
            "malformed_bodies": 0,
            "capped": 0,
            "fallback_used": 0,
        }

    # ------------------------------------------------------------------ stats

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._counters)

    # ------------------------------------------------------------------ committed Protocol

    def get(
        self,
        *,
        endpoint_secret: Any,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        """Committed transport Protocol entry. NEVER raises; failures map to refusal results."""
        _ = endpoint_secret  # ignored by the free path; never dialed/serialized
        try:
            if path == BIRDEYE_PATH_PRICE:
                result = self._get_price(query_params, timeout_seconds)
            elif path == BIRDEYE_PATH_TOKEN_OVERVIEW:
                result = self._get_overview(query_params, timeout_seconds)
            elif path == BIRDEYE_PATH_OHLCV:
                result = self._get_ohlcv(query_params, timeout_seconds)
            else:
                result = self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        except Exception:
            result = self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        if (
            result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE
            and self._fallback is not None
        ):
            try:
                with self._lock:
                    self._counters["fallback_used"] += 1
                return self._fallback.get(
                    endpoint_secret=(self._fallback_secret
                                     if self._fallback_secret is not None else endpoint_secret),
                    path=path,
                    query_params=query_params,
                    timeout_seconds=timeout_seconds,
                )
            except Exception:
                return result
        return result

    # ------------------------------------------------------------------ producer helper

    def fetch_simple_market(self, mint: str, timeout_seconds: int = 10) -> Optional[Dict[str, Any]]:
        """Pricing-tail helper: one cached free lookup -> {"current_price": <decimal-text>,
        "current_market_cap_usd": <decimal-text>, "liquidity_usd": <decimal-text>} (values may be
        missing -> key absent). Returns None when the token has no usable pool. Never raises."""
        try:
            pair = self._best_pair(mint, timeout_seconds)
        except Exception:
            return None
        if pair is _LOOKUP_FAILED or pair is None:
            return None
        out: Dict[str, Any] = {"fetched_at_utc": self._iso_now()}
        price = _decimal_text(pair.get("priceUsd"))
        if price is not None:
            out["current_price"] = price
        mc = _positive_number(pair.get("marketCap"))
        if mc is None:
            mc = _positive_number(pair.get("fdv"))
        if mc is not None:
            out["current_market_cap_usd"] = _decimal_text(mc)
        lp = _positive_number((pair.get("liquidity") or {}).get("usd")
                              if isinstance(pair.get("liquidity"), dict) else None)
        if lp is not None:
            out["liquidity_usd"] = _decimal_text(lp)
        return out

    # ------------------------------------------------------------------ path handlers

    def _get_price(self, params: Mapping[str, str], timeout: int) -> Stage29_2BirdeyeHttpResult:
        mint = str(params.get("address") or "")
        if not mint:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        pair = self._best_pair(mint, timeout)
        if pair is _LOOKUP_FAILED:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        if pair is None:
            # HTTP layer worked but no pool -> "no data" body (committed source maps to MISSING).
            return self._ok({"success": True, "data": None})
        price = _decimal_text(pair.get("priceUsd"))
        if price is None:
            return self._ok({"success": True, "data": {}})
        return self._ok({
            "success": True,
            "data": {"value": price, "updateUnixTime": int(self._now())},
        })

    def _get_overview(self, params: Mapping[str, str], timeout: int) -> Stage29_2BirdeyeHttpResult:
        mint = str(params.get("address") or "")
        if not mint:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        pair = self._best_pair(mint, timeout)
        if pair is _LOOKUP_FAILED:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        if pair is None:
            return self._ok({"success": True, "data": None})
        data: Dict[str, Any] = {}
        mc = _positive_number(pair.get("marketCap"))
        if mc is None:
            mc = _positive_number(pair.get("fdv"))  # pump tokens: fdv == mc in practice
        if mc is not None:
            data["marketCap"] = mc
        lp_raw = pair.get("liquidity")
        lp = _positive_number(lp_raw.get("usd")) if isinstance(lp_raw, dict) else None
        if lp is not None:
            data["liquidity"] = lp
        return self._ok({"success": True, "data": data})

    def _get_ohlcv(self, params: Mapping[str, str], timeout: int) -> Stage29_2BirdeyeHttpResult:
        mint = str(params.get("address") or "")
        if not mint:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        time_from = _coerce_int(params.get("time_from"))
        time_to = _coerce_int(params.get("time_to"))
        if time_from is None or time_to is None or time_to <= time_from:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        pair = self._best_pair(mint, timeout)
        if pair is _LOOKUP_FAILED:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        pool = pair.get("pairAddress") if isinstance(pair, dict) else None
        if not isinstance(pool, str) or not pool:
            return self._ok({"success": True, "data": {"items": []}})
        items = self._ohlcv_items(pool, time_from, time_to, timeout)
        if items is None:
            return self._refusal(BIRDEYE_REFUSAL_REASON_HTTP_FAILED)
        return self._ok({"success": True, "data": {"items": items}})

    # ------------------------------------------------------------------ free lookups

    def _best_pair(self, mint: str, timeout: int) -> Any:
        """Deepest solana pool for ``mint`` from the free pairs lookup, with a short TTL cache.
        Returns the pair dict, None when the token has no usable pool, or ``_LOOKUP_FAILED``
        when the lookup itself failed (failures are NOT cached)."""
        now = self._mono()
        with self._lock:
            hit = self._pair_cache.get(mint)
            if hit is not None and hit[0] > now:
                self._counters["cache_hits"] += 1
                return hit[1]
        body = self._paced_get_json(
            _PAIRS_URL_FMT.format(mint=mint), SOURCE_LABEL_PAIRS,
            self._pairs_min_interval, timeout)
        if not isinstance(body, dict):
            return _LOOKUP_FAILED
        pair: Optional[Dict[str, Any]] = None
        pairs = body.get("pairs")
        if isinstance(pairs, list):
            best_lp = -1.0
            for p in pairs:
                if not isinstance(p, dict) or p.get("chainId") != "solana":
                    continue
                lp_raw = p.get("liquidity")
                lp = _positive_number(lp_raw.get("usd")) if isinstance(lp_raw, dict) else None
                lp_val = float(lp) if lp is not None else 0.0
                if lp_val > best_lp:
                    best_lp = lp_val
                    pair = p
        with self._lock:
            self._pair_cache[mint] = (self._mono() + self._pair_ttl, pair)
        return pair

    def _ohlcv_items(self, pool: str, time_from: int, time_to: int,
                     timeout: int) -> Optional[List[Dict[str, Any]]]:
        """Candle highs over ``[time_from, time_to]`` projected to the committed item shape.
        Uses minute candles when the window fits the provider's page cap, else hour candles.
        None on lookup failure (refusal upstream); [] when the pool has no candles yet."""
        window_seconds = time_to - time_from
        if window_seconds <= 900 * 60:          # fits one minute-candle page
            timeframe, aggregate, unit = "minute", 1, 60
        elif window_seconds <= 900 * 3600:      # fits one hour-candle page
            timeframe, aggregate, unit = "hour", 1, 3600
        else:
            timeframe, aggregate, unit = "day", 1, 86400
        limit = min(1000, max(10, (window_seconds // unit) + 3))
        cache_key = (pool, time_from // unit, time_to // unit, timeframe)
        now = self._mono()
        with self._lock:
            hit = self._ohlcv_cache.get(cache_key)
            if hit is not None and hit[0] > now:
                self._counters["cache_hits"] += 1
                return hit[1]
        body = self._paced_get_json(
            _OHLCV_URL_FMT.format(pool=pool, timeframe=timeframe, aggregate=aggregate,
                                  before=time_to + unit, limit=limit),
            SOURCE_LABEL_OHLCV, self._ohlcv_min_interval, timeout)
        if body is None:
            return None
        items: List[Dict[str, Any]] = []
        data = body.get("data") if isinstance(body, dict) else None
        attrs = data.get("attributes") if isinstance(data, dict) else None
        rows = attrs.get("ohlcv_list") if isinstance(attrs, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 3:
                    continue
                ts = _coerce_int(row[0])
                high = _positive_number(row[2])
                if ts is None or high is None:
                    continue
                if time_from <= ts <= time_to:
                    items.append({"h": high, "unixTime": ts})
        with self._lock:
            self._ohlcv_cache[cache_key] = (self._mono() + self._ohlcv_ttl, items)
        return items

    def _paced_get_json(self, url: str, source_label: str, min_interval: float,
                        timeout: int) -> Optional[Any]:
        """Rate-paced GET -> parsed JSON, or None on any failure. Counts stats; never raises;
        never echoes the URL anywhere."""
        with self._lock:
            if self._max_calls_total is not None \
                    and self._counters["http_calls_total"] >= self._max_calls_total:
                self._counters["capped"] += 1
                if self._physical_meter is not None:
                    self._physical_meter.record_non_physical(
                        "TRANSPORT_CAP_REACHED")
                return None
            last = self._last_call_mono.get(source_label, -1e9)
            wait = min_interval - (self._mono() - last)
        if wait > 0:
            self._sleep(wait)
        with self._lock:
            self._last_call_mono[source_label] = self._mono()
            self._counters["http_calls_total"] += 1
            if source_label == SOURCE_LABEL_PAIRS:
                self._counters["pairs_calls"] += 1
            else:
                self._counters["ohlcv_calls"] += 1
        ticket_id: Optional[str] = None
        # Allocate at the exact physical boundary, immediately before the
        # socket call.  A legacy counter remains supported for isolated tests.
        if self._physical_meter is not None:
            begin = getattr(self._physical_meter, "begin_physical", None)
            if callable(begin):
                ticket_id = begin(source_label)
            else:
                self._physical_meter.record_physical(source_label)
        try:
            status, raw = self._urlopen(url, float(min(int(timeout), 30)))
        except Exception:
            with self._lock:
                self._counters["http_errors"] += 1
            if ticket_id is not None:
                self._physical_meter.complete_physical(
                    ticket_id,
                    http_status_class="NO_STATUS",
                    provider_outcome="DISPATCH_EXCEPTION",
                    observation_accepted=False,
                    rejection_reason="DISPATCH_EXCEPTION",
                )
            return None
        if status != 200:
            with self._lock:
                self._counters["http_errors"] += 1
                if status == 429:
                    self._counters["http_429"] += 1
            if ticket_id is not None:
                self._physical_meter.complete_physical(
                    ticket_id,
                    http_status_class=(
                        f"{int(status) // 100}XX" if 100 <= int(status) <= 599
                        else "NO_STATUS"),
                    provider_outcome=f"HTTP_{int(status)}",
                    observation_accepted=False,
                    rejection_reason="HTTP_FAILED",
                )
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            with self._lock:
                self._counters["malformed_bodies"] += 1
            if ticket_id is not None:
                self._physical_meter.complete_physical(
                    ticket_id,
                    http_status_class="2XX",
                    provider_outcome="BODY_MALFORMED",
                    observation_accepted=False,
                    rejection_reason="BODY_MALFORMED",
                )
            return None
        if ticket_id is not None:
            self._physical_meter.complete_physical(
                ticket_id,
                http_status_class="2XX",
                provider_outcome="SUCCESS",
                observation_accepted=True,
            )
        return body

    # ------------------------------------------------------------------ result builders

    def _iso_now(self) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    def _ok(self, body: Dict[str, Any]) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200, body=body, fetched_at_utc=self._iso_now(),
        )

    def _refusal(self, reason: str) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=reason, http_status_code=0, body=None,
            fetched_at_utc=self._iso_now(),
        )


# --------------------------------------------------------------------------- value coercers


def _positive_number(raw: Any) -> Optional[float]:
    """Finite positive float from a JSON number/numeric-string, else None."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val or val in (float("inf"), float("-inf")) or val <= 0:
        return None
    return val


def _decimal_text(raw: Any) -> Optional[str]:
    """Plain decimal text (never scientific notation) from a positive number/numeric-string."""
    from decimal import Decimal, InvalidOperation
    num = _positive_number(raw)
    if num is None:
        return None
    if isinstance(raw, str) and "e" not in raw.lower():
        return raw.strip()
    try:
        text = format(Decimal(repr(num)), "f")
    except (InvalidOperation, ValueError):
        return None
    if "." in text:
        text = text.rstrip("0")
        if text.endswith("."):
            text += "0"
    return text


def _coerce_int(raw: Any) -> Optional[int]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "FreeTierMarketTransport",
    "build_free_tier_endpoint_secret",
    "SOURCE_LABEL_PAIRS",
    "SOURCE_LABEL_OHLCV",
)
