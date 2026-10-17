"""Rate-aware Birdeye-primary market transport for paid PHX2 modes.

This wraps the existing redaction-safe Stage 29.2 GET boundary. Calls are
serialized, paced, cached, and retried with a finite backoff. Every valid
price or OHLCV high is also fed into a monotonic per-mint ATH observation
record; malformed/stale observations are ignored, never fabricated.

PROVIDER-SCOPED RATE-LIMIT BACKOFF (2026-07-31). An HTTP 429 opens a bounded,
jittered backoff window owned by :mod:`provider_backoff` and scoped to THIS
provider alone. While the window is open the transport short-circuits: no
socket is opened, no retry is burned, and the caller receives an ordinary
recoverable refusal that the per-mint readiness layer already knows how to
carry as ``MARKET_RECOVERY_BACKOFF``. Helius discovery, the durable migration
journal and the watch checkpoint are untouched by a market throttle. A single
success closes the window. 401/403 keep their existing permanent-rejection
path (no retry, no backoff) and remain fatal at the pre-startup credential
gate — a rejected key is never treated as "wait and try again".
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
    BIRDEYE_PATH_V3_PAIR_OHLCV,
    BIRDEYE_PATH_V3_TOKEN_OHLCV,
    BIRDEYE_V3_MODE_RANGE,
    BIRDEYE_V3_OUTLIER_MODE_PROVIDER_DEFAULT,
    BIRDEYE_V3_PADDING_DISABLED,
    is_allowed_v3_ohlcv_type,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeHttpResult
from PHX2.models.market_credential import (
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    classify_market_credential_status,
    is_permanent_market_auth_status,
)
from PHX2.free_tier_producer.market_budget import (
    NON_PHYSICAL_CACHE_HIT,
    NON_PHYSICAL_CAP_REACHED,
    NON_PHYSICAL_DEADLINE_EXHAUSTED,
    NON_PHYSICAL_RATE_LIMIT_BACKOFF,
    ORIGIN_ATH_V3_PAIR_COARSE,
    ORIGIN_ATH_V3_PAIR_INCREMENTAL,
    ORIGIN_ATH_V3_PAIR_REFINE,
    ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC,
    ORIGIN_FALLBACK,
    MarketPhysicalRequestMeter,
)
from PHX2.models.ath_coverage import (
    ATH_V3_AUTH_FAILED,
    ATH_V3_CANDLE_GAP,
    ATH_V3_HISTORY_INCOMPLETE,
    ATH_V3_INVERSION_UNRESOLVED,
    ATH_V3_PAIR_UNAVAILABLE,
    ATH_V3_RATE_LIMITED,
    ATH_V3_USD_CONVERSION_UNRESOLVED,
)
from PHX2.free_tier_producer.ath_state import (
    ATH_V3_COARSE_INTERVAL,
    ATH_V3_COARSE_INTERVAL_SECONDS,
    ATH_V3_REFINE_INTERVAL,
)
from PHX2.free_tier_producer.paid_market_readiness import (
    MARKET_INCOMPLETE,
    MARKET_INDEXING,
    MARKET_INVALID,
    MARKET_READY,
    MARKET_STALE,
)
from PHX2.free_tier_producer.global_fees import (
    build_overview_global_fees_observation,
)
from PHX2.free_tier_producer.provider_backoff import (
    PROVIDER_MARKET_PRIMARY,
    ProviderRateLimitBackoff,
)


def _positive_decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_epoch(value: object, fallback: float) -> float:
    if not isinstance(value, str) or not value:
        return float(fallback)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return float(fallback)
    if parsed.tzinfo is None:
        return float(fallback)
    return parsed.astimezone(timezone.utc).timestamp()


def _http_status_class(result: object) -> str:
    try:
        status = int(getattr(result, "http_status_code", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    return f"{status // 100}XX" if 100 <= status <= 599 else "NO_STATUS"


def _provider_ticket_outcome(result: object) -> Tuple[str, bool, Optional[str]]:
    refusal = str(getattr(result, "refusal_reason", "") or "")
    accepted = refusal == BIRDEYE_REFUSAL_REASON_NONE
    if accepted:
        return "SUCCESS", True, None
    status_class = _http_status_class(result)
    outcome = status_class if status_class != "NO_STATUS" else (refusal or "ERROR")
    return outcome, False, refusal or "PROVIDER_REFUSED"


class PaidBirdeyeMarketTransport:
    """Committed Birdeye transport Protocol plus producer market helper."""

    def __init__(
        self,
        *,
        inner_transport: Any,
        endpoint_secret: Any,
        fallback_transport: Any = None,
        fallback_endpoint_secret: Any = None,
        min_interval_seconds: float = 1.05,
        cache_ttl_seconds: float = 8.0,
        ohlcv_cache_ttl_seconds: float = 25.0,
        max_attempts: int = 3,
        max_calls_total: Optional[int] = 200000,
        backoff_seconds: Tuple[float, ...] = (0.5, 1.0),
        max_data_age_seconds: float = 300.0,
        now_fn: Callable[[], float] = time.time,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        ath_store: Any = None,
        ohlcv_interval: str = "1m",
        ohlcv_page_candles: int = 900,
        ohlcv_max_pages: int = 128,
        v3_page_candles: int = 900,
        max_concurrency: int = 4,
        background_yield_fn: Optional[Callable[[], bool]] = None,
        rate_limit_backoff: Optional[ProviderRateLimitBackoff] = None,
        physical_request_meter: Optional[MarketPhysicalRequestMeter] = None,
    ) -> None:
        self._inner = inner_transport
        # The ONE authoritative physical-request counter, shared with the
        # market scheduler.  Every path below that returns WITHOUT dialling
        # records a non-physical reason instead; that is what makes a cache
        # hit cost zero budget rather than a full unit.
        self._physical_meter = physical_request_meter
        # Shared with the run's credit budget so ONE object is the truth for
        # both the request-suppression decision and the health surface.
        self._rate_limit = rate_limit_backoff or ProviderRateLimitBackoff(
            PROVIDER_MARKET_PRIMARY, monotonic_fn=monotonic_fn)
        self._secret = endpoint_secret
        self._fallback = fallback_transport
        self._fallback_secret = fallback_endpoint_secret
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._cache_ttl = max(0.0, float(cache_ttl_seconds))
        self._ohlcv_ttl = max(0.0, float(ohlcv_cache_ttl_seconds))
        self._max_attempts = max(1, min(5, int(max_attempts)))
        # ``None`` means UNBOUNDED (the RUN_FOREVER market-budget posture):
        # the cap check is skipped, NOT clamped by ``max(1, ...)`` -- which
        # would have turned "no ceiling" into a one-request ceiling and
        # blinded the market plane instantly.  Any int keeps its old meaning.
        self._max_calls_total = (
            None if max_calls_total is None else max(1, int(max_calls_total)))
        self._backoff = tuple(max(0.0, float(v)) for v in backoff_seconds)
        self._max_data_age = max(1.0, float(max_data_age_seconds))
        self._now = now_fn
        self._mono = monotonic_fn
        self._sleep = sleep_fn
        self._ath_store = ath_store
        self._ohlcv_interval = "1m" if ohlcv_interval != "1m" else ohlcv_interval
        self._ohlcv_page_candles = max(1, min(5000, int(ohlcv_page_candles)))
        self._ohlcv_max_pages = max(1, min(512, int(ohlcv_max_pages)))
        # V3 pair-history pager: 900 fifteen-second candles per request is a
        # 3h45m span, far below the provider's 5,000-record response limit,
        # and a six-hour candidate window closes in two deterministic chunks.
        self._v3_page_candles = max(1, min(4500, int(v3_page_candles)))
        # Exact ticket-id capture for the V3 evidence trail (thread-local so
        # concurrent hydrations of different mints never mix tickets).
        self._ticket_sink = threading.local()
        if not (1 <= int(max_concurrency) <= 64):
            raise ValueError("paid_birdeye_max_concurrency_invalid")
        # PHX2-E2E-006: pacing gates request STARTS only; the HTTP call runs
        # outside the state lock behind a bounded concurrency gate, so one
        # slow or retrying mint can no longer serialize every other mint.
        self._max_concurrency = int(max_concurrency)
        self._http_gate = threading.BoundedSemaphore(self._max_concurrency)
        self._background_yield = background_yield_fn
        self._lock = threading.RLock()
        self._last_call_mono: Optional[float] = None
        self._next_start_mono: Optional[float] = None
        self._cache: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Tuple[float, Any]] = {}
        self._ath: Dict[str, Dict[str, Any]] = {}
        self._diagnostics: Dict[str, Dict[str, Any]] = {}
        self._last_ohlcv_refresh: Dict[str, float] = {}
        self._first_live_epoch: Dict[str, float] = {}
        self._inflight = 0
        #: Sanitized closed-set credential class of the most recent auth
        #: rejection (never a key, header, or URL).  Rides ``stats()`` so the
        #: failure is explainable from artifacts alone.
        self._last_auth_status_class: Optional[str] = None
        self._counters: Dict[str, int] = {
            "http_calls_total": 0,
            "pairs_calls": 0,
            "price_calls": 0,
            "overview_calls": 0,
            "ohlcv_calls": 0,
            "cache_hits": 0,
            "http_errors": 0,
            "http_429": 0,
            "http_auth_failures": 0,
            "auth_retries_skipped": 0,
            "malformed_bodies": 0,
            "capped": 0,
            "fallback_used": 0,
            "retries": 0,
            "stale_refusals": 0,
            "max_inflight": 0,
            "ath_observations": 0,
            "ath_provisional_mints": 0,
            "ath_confirmed_mints": 0,
            "ohlcv_indexing": 0,
            "deadline_exhausted": 0,
            "background_yields": 0,
            # ---- V3 pair-history plane (2026-08-03) ----------------------
            "v3_pair_coarse_calls": 0,
            "v3_pair_refine_calls": 0,
            "v3_pair_incremental_calls": 0,
            "v3_diagnostic_calls": 0,
            "v3_candles_coarse": 0,
            "v3_candles_refined": 0,
            "v3_candles_incremental": 0,
            "v3_pair_auth_failures": 0,
            "v3_pair_rate_limited": 0,
            "v3_pair_5xx": 0,
            "v3_refine_fallback_coarse": 0,
            "v3_valuation_unresolved": 0,
            # Requests NOT dialled because this provider's bounded backoff
            # window was open. This is the counter that proves the throttle was
            # respected rather than hammered.
            "rate_limit_backoff_skipped": 0,
            "rate_limit_retries_skipped": 0,
        }

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            central_stats = getattr(self._ath_store, "stats", lambda: {})()
            stale_evidence = []
            for mint, diagnostic in self._diagnostics.items():
                endpoints = diagnostic.get("endpoints") or {}
                for endpoint in endpoints.values():
                    for stale in endpoint.get("stale_responses") or ():
                        if isinstance(stale, Mapping):
                            stale_evidence.append({"mint": mint, **dict(stale)})
            # Status remains bounded while retaining the latest exact
            # redaction-safe classifications that explain current behavior.
            stale_evidence = stale_evidence[-256:]
            return {
                **self._counters,
                "provider": "PAID_MARKET_PRIMARY",
                "last_auth_status_class": self._last_auth_status_class,
                "request_concurrency": self._max_concurrency,
                "request_start_spacing_seconds": self._min_interval,
                # The committed paid-provider contract represented in this
                # repository exposes only single-address price and overview
                # GET shapes.  The scheduler must not invent a multi-mint URL.
                "price_batch_supported": False,
                "price_batch_size": 0,
                "cached_entries": len(self._cache),
                "ath_mints": int(central_stats.get("ath_mints", len(self._ath))),
                "ath_event_dedupe_keys": int(central_stats.get("ath_event_dedupe_keys", 0)),
                "rate_limit_status": self._rate_limit.status,
                "rate_limit_degraded": self._rate_limit.degraded,
                "provider_backoff": self._rate_limit.snapshot(),
                "stale_provider_responses": stale_evidence,
                "stale_provider_responses_retained": len(stale_evidence),
                **(self._physical_meter.snapshot()
                   if self._physical_meter is not None else {}),
            }

    def _record_non_physical(self, reason: str) -> None:
        """A call that returned without crossing the dispatch boundary."""

        if self._physical_meter is not None:
            self._physical_meter.record_non_physical(reason)

    @property
    def physical_request_meter(self) -> Optional[MarketPhysicalRequestMeter]:
        """The shared authoritative physical-request counter, if installed."""

        return self._physical_meter

    @property
    def rate_limit_backoff(self) -> ProviderRateLimitBackoff:
        """The provider-scoped throttle object (shared with the run budget)."""

        return self._rate_limit

    def market_diagnostic(self, mint: str) -> Dict[str, Any]:
        """Return only redaction-safe per-mint endpoint/field diagnostics."""
        with self._lock:
            row = self._diagnostics.get(mint) or {}
            endpoints = {
                path: dict(value) for path, value in (row.get("endpoints") or {}).items()
            }
            price = endpoints.get(BIRDEYE_PATH_PRICE) or {}
            overview = endpoints.get(BIRDEYE_PATH_TOKEN_OVERVIEW) or {}
            states = (price.get("state"), overview.get("state"))
            if MARKET_INVALID in states:
                state = MARKET_INVALID
            elif MARKET_STALE in states:
                state = MARKET_STALE
            elif MARKET_INDEXING in states:
                state = MARKET_INDEXING
            elif MARKET_INCOMPLETE in states or not all(states):
                state = MARKET_INCOMPLETE
            else:
                state = MARKET_READY
            reason = next((
                str(item.get("reason_code")) for item in (price, overview)
                if item.get("state") == state and item.get("reason_code")
            ), state)
            return {
                "market_state": state,
                "market_reason_code": reason,
                "provider_timestamp_utc": price.get("provider_timestamp_utc"),
                "endpoints": endpoints,
            }

    def get(
        self,
        *,
        endpoint_secret: Any,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
        deadline_monotonic: Optional[float] = None,
        max_attempts: Optional[int] = None,
    ) -> Stage29_2BirdeyeHttpResult:
        """Paced, cached, bounded-concurrency GET.

        PHX2-E2E-006 restructure: the state lock covers only cache reads,
        counter/diagnostic updates and start-slot allocation.  Pacing waits,
        the HTTP call, and retry backoffs run OUTSIDE the lock, behind a
        bounded concurrency gate, so independent mints overlap and one
        failing mint's retries never head-of-line block the rest.

        ``deadline_monotonic`` is the candidate's remaining P1 budget: no
        attempt may START at or after it, and a retry that cannot fit is
        abandoned as an explicit timeout-shaped refusal (never silence,
        never a stale send authorization).
        """

        _ = endpoint_secret
        key = (str(path), tuple(sorted((str(k), str(v)) for k, v in query_params.items())))
        with self._lock:
            cached = self._cache.get(key)
            ttl = (self._ohlcv_ttl
                   if path in (BIRDEYE_PATH_OHLCV, BIRDEYE_PATH_V3_PAIR_OHLCV,
                               BIRDEYE_PATH_V3_TOKEN_OHLCV)
                   else self._cache_ttl)
            if cached is not None and (float(self._mono()) - cached[0]) <= ttl:
                self._counters["cache_hits"] += 1
                self._record_non_physical(NON_PHYSICAL_CACHE_HIT)
                return cached[1]

        attempts_allowed = (self._max_attempts if max_attempts is None
                            else max(1, min(5, int(max_attempts))))
        result: Optional[Stage29_2BirdeyeHttpResult] = None
        for attempt in range(attempts_allowed):
            # Provider-scoped throttle gate, checked BEFORE the call is paced
            # or dialled: an open backoff window means this provider asked us
            # to stop, so we stop -- for this provider only. Breaking (rather
            # than returning) leaves the existing fallback path reachable: a
            # keyless fallback is a DIFFERENT provider and is not throttled, so
            # market coverage degrades rather than stopping. With no fallback
            # the caller gets the ordinary recoverable refusal the readiness
            # layer already carries as MARKET_RECOVERY_BACKOFF; nothing is
            # fabricated and no candidate state dies.
            if self._rate_limit.should_skip():
                with self._lock:
                    self._counters["rate_limit_backoff_skipped"] += 1
                self._record_non_physical(NON_PHYSICAL_RATE_LIMIT_BACKOFF)
                result = self._rate_limited_result()
                break
            with self._lock:
                if self._max_calls_total is not None \
                        and self._counters["http_calls_total"] >= self._max_calls_total:
                    self._counters["capped"] += 1
                    self._record_non_physical(NON_PHYSICAL_CAP_REACHED)
                    return self._error_result()
            start_at = self._reserve_start_slot()
            if deadline_monotonic is not None and start_at >= float(deadline_monotonic):
                with self._lock:
                    self._counters["deadline_exhausted"] += 1
                self._record_non_physical(NON_PHYSICAL_DEADLINE_EXHAUSTED)
                return self._timeout_result()
            wait = start_at - float(self._mono())
            if wait > 0:
                self._sleep(wait)
            physical_ticket_id: Optional[str] = None
            dispatch_exception = False
            with self._http_gate:
                with self._lock:
                    self._inflight += 1
                    self._counters["max_inflight"] = max(
                        self._counters["max_inflight"], self._inflight
                    )
                try:
                    # Allocate the immutable ownership identity at the exact
                    # physical boundary, immediately before the provider call.
                    if self._physical_meter is not None:
                        physical_ticket_id = self._physical_meter.begin_physical(
                            path, retry_index=attempt)
                    result = self._inner.get(
                        endpoint_secret=self._secret,
                        path=path,
                        query_params=query_params,
                        timeout_seconds=timeout_seconds,
                    )
                except Exception:
                    dispatch_exception = True
                    result = self._error_result()
                finally:
                    with self._lock:
                        self._inflight -= 1
            with self._lock:
                self._counters["http_calls_total"] += 1
                if path == BIRDEYE_PATH_PRICE:
                    self._counters["price_calls"] += 1
                    self._counters["pairs_calls"] += 1
                elif path == BIRDEYE_PATH_TOKEN_OVERVIEW:
                    self._counters["overview_calls"] += 1
                elif path == BIRDEYE_PATH_OHLCV:
                    self._counters["ohlcv_calls"] += 1
                elif path == BIRDEYE_PATH_V3_TOKEN_OHLCV:
                    self._counters["v3_diagnostic_calls"] += 1
                if path == BIRDEYE_PATH_V3_PAIR_OHLCV:
                    status_now = int(
                        getattr(result, "http_status_code", 0) or 0)
                    if status_now in (401, 403):
                        self._counters["v3_pair_auth_failures"] += 1
                    elif status_now == 429:
                        self._counters["v3_pair_rate_limited"] += 1
                    elif status_now >= 500:
                        self._counters["v3_pair_5xx"] += 1
                sink = getattr(self._ticket_sink, "ids", None)
                if sink is not None and physical_ticket_id is not None:
                    sink.append(physical_ticket_id)
                stale = self._record_diagnostic_locked(
                    path, query_params, result,
                    request_ticket_id=physical_ticket_id)
                throttled = getattr(result, "http_status_code", 0) == 429
                if throttled:
                    self._counters["http_429"] += 1
                    self._counters["rate_limit_retries_skipped"] += (
                        attempts_allowed - attempt - 1)
                provider_result = result
                if stale:
                    self._counters["stale_refusals"] += 1
                    result = self._error_result()
                if result.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE:
                    self._observe_locked(path, query_params, result)
                    self._cache[key] = (float(self._mono()), result)
                    succeeded = True
                else:
                    succeeded = False
                    self._counters["http_errors"] += 1
                if physical_ticket_id is not None:
                    if stale:
                        provider_outcome = "STALE_PROVIDER_TIMESTAMP"
                        observation_accepted = False
                        rejection = "PRICE_PROVIDER_TIMESTAMP_STALE"
                    else:
                        provider_outcome, observation_accepted, rejection = (
                            _provider_ticket_outcome(provider_result))
                    if dispatch_exception:
                        provider_outcome = "DISPATCH_EXCEPTION"
                        rejection = "DISPATCH_EXCEPTION"
                    self._physical_meter.complete_physical(
                        physical_ticket_id,
                        http_status_class=_http_status_class(result),
                        provider_outcome=provider_outcome,
                        observation_accepted=observation_accepted,
                        rejection_reason=rejection,
                    )
                if succeeded:
                    # Observable recovery: a served response closes any open
                    # backoff window for this provider.
                    self._rate_limit.record_success()
                    return result
                if throttled:
                    # Open/extend the bounded jittered window and STOP retrying
                    # this request. Retrying into a throttle is what turns a
                    # transient burst into a sustained one.
                    self._rate_limit.record_throttle()
                    break
                status_code = int(getattr(result, "http_status_code", 0) or 0)
                if is_permanent_market_auth_status(status_code):
                    # Permanent credential rejection: the same key will be
                    # refused identically on every retry (the 2026-07-30 canary
                    # burned 32 retries against a constant 401).  Record the
                    # sanitized class and stop immediately.
                    self._counters["http_auth_failures"] += 1
                    self._counters["auth_retries_skipped"] += (
                        attempts_allowed - attempt - 1)
                    self._last_auth_status_class = (
                        classify_market_credential_status(status_code))
                    # Counted in its OWN class: a rejected credential is not a
                    # throttle and must never enter backoff-and-retry.
                    self._rate_limit.record_auth_failure()
                    permanent_auth_failure = True
                else:
                    permanent_auth_failure = False
            if permanent_auth_failure:
                break
            if attempt + 1 < attempts_allowed:
                delay = (self._backoff[min(attempt, len(self._backoff) - 1)]
                         if self._backoff else 0)
                if deadline_monotonic is not None and (
                        float(self._mono()) + float(delay)
                        >= float(deadline_monotonic)):
                    with self._lock:
                        self._counters["deadline_exhausted"] += 1
                    return self._timeout_result()
                with self._lock:
                    self._counters["retries"] += 1
                self._sleep(delay)

        assert result is not None
        if self._fallback is not None:
            with self._lock:
                self._counters["fallback_used"] += 1
            try:
                if self._physical_meter is None:
                    return self._fallback.get(
                        endpoint_secret=(self._fallback_secret
                                         if self._fallback_secret is not None else endpoint_secret),
                        path=path,
                        query_params=query_params,
                        timeout_seconds=timeout_seconds,
                    )
                with self._physical_meter.ownership(origin=ORIGIN_FALLBACK):
                    return self._fallback.get(
                        endpoint_secret=(self._fallback_secret
                                         if self._fallback_secret is not None else endpoint_secret),
                        path=path,
                        query_params=query_params,
                        timeout_seconds=timeout_seconds,
                    )
            except Exception:
                pass
        return result

    def fetch_price_plane(
        self, mint: str, timeout_seconds: int = 10,
        deadline_monotonic: Optional[float] = None,
        max_attempts: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch only the fast current-price plane for one exactly-bound mint.

        Market cap is intentionally not fabricated from price.  It is returned
        only when a documented response supplies it; otherwise the independent
        overview plane remains due.  This method never performs an overview or
        OHLCV request.
        """

        if not isinstance(mint, str) or not mint:
            return None
        result = self.get(
            endpoint_secret=self._secret,
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": mint},
            timeout_seconds=timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            max_attempts=max_attempts,
        )
        if result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            return self._scheduler_failure_result(mint, result)
        data = (result.body or {}).get("data")
        if not isinstance(data, dict):
            return {"mint": mint, "_market_failure_reason": "PROVIDER_MALFORMED"}
        response_mint = data.get("address") or data.get("mint")
        if response_mint is not None and response_mint != mint:
            return {"mint": mint, "_market_failure_reason": "PROVIDER_WRONG_MINT"}
        price = _positive_decimal(data.get("value"))
        if price is None:
            return {"mint": mint, "_market_failure_reason": "PROVIDER_MALFORMED"}
        out: Dict[str, Any] = {
            "mint": mint,
            "current_price": _decimal_text(price),
            "fetched_at_utc": result.fetched_at_utc,
            "provider_timestamp_utc": self._price_observed_iso(
                data, result.fetched_at_utc),
            "market_provider": "PAID_MARKET_PRIMARY",
            "price_observation_type": "CURRENT_PRICE",
        }
        # Accept a market-cap field only if this exact documented response
        # happens to provide one. Missing stays missing and cannot be freshened
        # by the price timestamp.
        mc = next((_positive_decimal(data.get(key)) for key in (
            "mc", "marketCap", "market_cap")
            if _positive_decimal(data.get(key)) is not None), None)
        if mc is not None:
            out["current_market_cap_usd"] = _decimal_text(mc)
        return out

    def fetch_overview_plane(
        self, mint: str, timeout_seconds: int = 10,
        deadline_monotonic: Optional[float] = None,
        max_attempts: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch slow market-cap/liquidity enrichment for one bound mint.

        The overview timestamp never freshens current price.  Call cadence and
        independent freshness are owned by :mod:`market_scheduler`.
        """

        if not isinstance(mint, str) or not mint:
            return None
        result = self.get(
            endpoint_secret=self._secret,
            path=BIRDEYE_PATH_TOKEN_OVERVIEW,
            query_params={"address": mint},
            timeout_seconds=timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            max_attempts=max_attempts,
        )
        if result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            return self._scheduler_failure_result(mint, result)
        data = (result.body or {}).get("data")
        if not isinstance(data, dict):
            return {"mint": mint, "_market_failure_reason": "PROVIDER_MALFORMED"}
        response_mint = data.get("address") or data.get("mint")
        if response_mint is not None and response_mint != mint:
            return {"mint": mint, "_market_failure_reason": "PROVIDER_WRONG_MINT"}
        mc = next((_positive_decimal(data.get(key)) for key in (
            "mc", "marketCap", "market_cap")
            if _positive_decimal(data.get(key)) is not None), None)
        liquidity = next((_positive_decimal(data.get(key)) for key in (
            "liquidity", "liquidityUsd", "liquidity_usd")
            if _positive_decimal(data.get(key)) is not None), None)
        if mc is None and liquidity is None:
            return {"mint": mint, "_market_failure_reason": "PROVIDER_MALFORMED"}
        provider_epoch = next((
            _positive_decimal(data.get(key)) for key in (
                "updateUnixTime", "updatedUnixTime", "lastUpdatedUnixTime")
            if _positive_decimal(data.get(key)) is not None
        ), None)
        observed_at = (
            _iso(float(provider_epoch)) if provider_epoch is not None
            else result.fetched_at_utc)
        out = {
            "mint": mint,
            "fetched_at_utc": result.fetched_at_utc,
            "provider_timestamp_utc": observed_at,
            "market_provider": "PAID_MARKET_PRIMARY",
        }
        if mc is not None:
            out["current_market_cap_usd"] = _decimal_text(mc)
        if liquidity is not None:
            out["liquidity_usd"] = _decimal_text(liquidity)
        # Token identity riding on a response the run already paid for
        # (2026-07-28 metadata remediation).  The scheduler ignores these keys;
        # the session's apply callback merges them into the canonical
        # per-mint metadata state.  Missing stays missing.
        name = data.get("name")
        symbol = data.get("symbol")
        if isinstance(name, str) and name.strip():
            out["token_name"] = name
        if isinstance(symbol, str) and symbol.strip():
            out["token_symbol"] = symbol
        # Presentation only; rides the existing exact-mint overview request.
        from PHX2.delivery.telegram_media import validate_logo_url
        logo = validate_logo_url(data.get("logoURI"))
        if logo is not None:
            out["token_logo_url"] = logo
        # Observe-only all-time Global Fees riding the same identity-checked
        # response (2026-07-28 capability probe).  Classification happens here
        # at the response boundary; the session merges it into the canonical
        # per-mint tracker.  Never a market-readiness or eligibility input.
        out["global_fees"] = build_overview_global_fees_observation(
            mint=mint,
            data=data,
            observed_at_utc=observed_at,
            http_status_code=int(result.http_status_code or 0),
        )
        return out

    def _scheduler_failure_result(
        self, mint: str, result: Stage29_2BirdeyeHttpResult
    ) -> Dict[str, Any]:
        """Project provider failures to a redaction-safe closed scheduler reason."""

        status = int(result.http_status_code or 0)
        diagnostic = self.market_diagnostic(mint)
        credential_status = classify_market_credential_status(status)
        if credential_status is not None:
            # Surfaced ahead of the malformed/stale branches: a rejected key
            # must never be reported downstream as PROVIDER_MALFORMED.
            reason = "PROVIDER_" + credential_status
        elif status == 429:
            reason = "PROVIDER_RATE_LIMIT"
        elif status >= 500:
            reason = "PROVIDER_5XX"
        elif result.refusal_reason == BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT:
            reason = "PROVIDER_TIMEOUT"
        elif (result.refusal_reason == BIRDEYE_REFUSAL_REASON_BODY_MALFORMED
              or diagnostic.get("market_state") == MARKET_INVALID):
            reason = "PROVIDER_MALFORMED"
        elif diagnostic.get("market_state") == MARKET_STALE:
            reason = "PROVIDER_STALE"
        else:
            reason = "PROVIDER_HTTP_FAILED"
        out = {"mint": mint, "_market_failure_reason": reason}
        if reason == "PROVIDER_STALE":
            out["_market_failure_evidence"] = diagnostic
        return out

    def fetch_simple_market(self, mint: str, timeout_seconds: int = 10) -> Optional[Dict[str, Any]]:
        price = self.get(
            endpoint_secret=self._secret,
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": mint},
            timeout_seconds=timeout_seconds,
        )
        overview = self.get(
            endpoint_secret=self._secret,
            path=BIRDEYE_PATH_TOKEN_OVERVIEW,
            query_params={"address": mint},
            timeout_seconds=timeout_seconds,
        )
        if price.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            return None
        p_data = (price.body or {}).get("data")
        o_data = (overview.body or {}).get("data")
        if not isinstance(p_data, dict):
            return None
        current = _positive_decimal(p_data.get("value"))
        if current is None:
            return None
        observed_at = self._price_observed_iso(p_data, price.fetched_at_utc)
        out: Dict[str, Any] = {
            "current_price": _decimal_text(current),
            "fetched_at_utc": price.fetched_at_utc,
            "market_provider": "PAID_MARKET_PRIMARY",
            "price_observation_type": "CURRENT_PRICE",
            "price_observed_at_utc": observed_at,
        }
        if isinstance(o_data, dict) and overview.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE:
            mc = next((_positive_decimal(o_data.get(k)) for k in ("mc", "marketCap", "market_cap")
                       if _positive_decimal(o_data.get(k)) is not None), None)
            lp = next((_positive_decimal(o_data.get(k)) for k in ("liquidity", "liquidityUsd", "liquidity_usd")
                       if _positive_decimal(o_data.get(k)) is not None), None)
            if mc is not None:
                out["current_market_cap_usd"] = _decimal_text(mc)
            if lp is not None:
                out["liquidity_usd"] = _decimal_text(lp)
        observe_current = getattr(self._ath_store, "observe_provider_current", None)
        if callable(observe_current):
            try:
                observe_current(
                    mint=mint,
                    price_usd=current,
                    market_cap_usd=out.get("current_market_cap_usd"),
                    observed_at=observed_at,
                    confirmed=False,
                )
            except Exception:
                pass
        # Probe historical observations independently of compose.  Missing newborn
        # OHLCV leaves the live-observed ATH intact and is retried after the bounded TTL.
        self.refresh_ath_history(mint, timeout_seconds=timeout_seconds)
        diagnostic = self.market_diagnostic(mint)
        out.update({
            "market_state": diagnostic["market_state"],
            "market_reason_code": diagnostic["market_reason_code"],
            "provider_timestamp_utc": diagnostic.get("provider_timestamp_utc"),
            "endpoint_attempts": diagnostic.get("endpoints") or {},
        })
        ath = self.ath_snapshot(mint)
        if ath:
            out.update({
                "ath_price_usd": ath["ath_price_usd"],
                "ath_market_cap_usd": ath.get("ath_market_cap_usd"),
                "ath_observed_at_utc": ath["observed_at_utc"],
                "ath_provider": ath["provider"],
                "ath_observation_type": ath["observation_type"],
                "ath_sample_count": ath.get("sample_count"),
                "ath_provisional_ready": ath.get("provisional_ready"),
                "ath_discord_eligible": ath.get("discord_eligible", False),
            })
        return out

    # ---- canonical V3 pair-history hydration (2026-08-03) -----------------

    @contextmanager
    def _collect_tickets(self, sink: List[str]) -> Iterator[None]:
        prior = getattr(self._ticket_sink, "ids", None)
        self._ticket_sink.ids = sink
        try:
            yield
        finally:
            self._ticket_sink.ids = prior

    def _v3_ownership(self, origin: str, mint: str):
        if self._physical_meter is None:
            return nullcontext()
        return self._physical_meter.ownership(
            origin=origin, mint=mint, scheduler_owner="ATH_V3_PAIR")

    @staticmethod
    def _v3_failure_reason(result: Stage29_2BirdeyeHttpResult) -> str:
        status = int(getattr(result, "http_status_code", 0) or 0)
        if status in (401, 403):
            return ATH_V3_AUTH_FAILED
        if status == 429:
            return ATH_V3_RATE_LIMITED
        return ATH_V3_HISTORY_INCOMPLETE

    @staticmethod
    def _v3_item_time(item: Mapping[str, Any]) -> Optional[int]:
        raw = item.get("unix_time", item.get("unixTime"))
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        value = int(raw)
        return value if value >= 0 else None

    def _v3_valid_candles(
        self,
        result: Stage29_2BirdeyeHttpResult,
        *,
        expected_address: str,
        window_from: int,
        window_to: int,
        interval_seconds: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """Validated candle list, or ``None`` when the page is unusable.

        Every candle must belong to the expected address, sit inside the
        requested window (one interval of provider-boundary slack), and carry
        a finite positive high.  ``padding=false`` means an absent bucket is
        "no trades", so an EMPTY list is a valid page; a page whose candles
        are malformed or belong to another address is not.
        """

        data = (result.body or {}).get("data")
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return None
        accepted: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                return None
            address = item.get("address")
            if address is not None and address != expected_address:
                return None
            when = self._v3_item_time(item)
            if when is None:
                return None
            if when < window_from or when > window_to + interval_seconds:
                # A candle outside the exact requested range is rejected --
                # never silently admitted into a migration-anchored window.
                # The LEFT edge is exact on purpose: the request window
                # already starts at the interval floor of the migration
                # anchor, so anything earlier would be a pre-migration
                # candle, which must never contribute a maximum.  The right
                # edge keeps one interval of provider boundary slack for the
                # in-progress candle.
                return None
            high = _positive_decimal(item.get("h"))
            if high is None:
                return None
            accepted.append({
                "unix_time": when,
                "h": high,
                "v": _positive_decimal(item.get("v")),
                "v_usd": _positive_decimal(item.get("v_usd")),
            })
        return accepted

    def _v3_pair_page(
        self, *, pair: str, interval: str, time_from: int, time_to: int,
        origin: str, mint: str, timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        assert is_allowed_v3_ohlcv_type(interval), interval
        with self._v3_ownership(origin, mint):
            return self.get(
                endpoint_secret=self._secret,
                path=BIRDEYE_PATH_V3_PAIR_OHLCV,
                query_params={
                    "address": pair,
                    "type": interval,
                    "time_from": str(int(time_from)),
                    "time_to": str(int(time_to)),
                    "mode": BIRDEYE_V3_MODE_RANGE,
                    "padding": BIRDEYE_V3_PADDING_DISABLED,
                },
                timeout_seconds=timeout_seconds,
            )

    def _v3_token_page(
        self, *, mint: str, interval: str, time_from: int, time_to: int,
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        with self._v3_ownership(ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC, mint):
            return self.get(
                endpoint_secret=self._secret,
                path=BIRDEYE_PATH_V3_TOKEN_OHLCV,
                query_params={
                    "address": mint,
                    "type": interval,
                    "time_from": str(int(time_from)),
                    "time_to": str(int(time_to)),
                    "mode": BIRDEYE_V3_MODE_RANGE,
                    "padding": BIRDEYE_V3_PADDING_DISABLED,
                    "currency": "usd",
                },
                timeout_seconds=timeout_seconds,
            )

    def refresh_ath_history(
        self, mint: str, timeout_seconds: int = 10,
    ) -> Dict[str, Any]:
        """Canonical V3 PAIR post-migration ATH hydration for one mint.

        Two-stage adaptive algorithm against the authenticated migration
        pool, driven from the central store's registered pair identity:

        1. **Coarse full-window scan** -- 15-second pair candles from
           ``floor(migration anchor, 15s)`` (so the partial first candle can
           never be dropped -- the exact 2026-08-03 defect) through now, in
           deterministic contiguous chunks below the 5,000-record response
           limit.  After initial completion, requests continue only PAST the
           durable cursor (incremental; the proven prefix is never
           re-downloaded).
        2. **Peak refinement** -- 1-second pair candles across the highest
           coarse candle.  When 1-second data is unavailable the valid
           15-second high is retained with explicit provenance instead of
           inventing precision.

        The pair endpoint prices this pool in its QUOTE asset (probe-proven),
        so the refined peak is valued in USD from the provider's own token
        USD series at the SAME candle timestamps, cross-validated per candle
        (identical trade volumes, coherent USD/native ratio).  Divergence is
        recorded as a diagnostic; an unresolvable valuation pends THIS
        candidate with a specific named reason and blocks nothing else.

        Returns a small JSON-safe outcome; a TTL-suppressed no-op reports
        ``attempted=False`` so the store's bounded backoff never inflates.
        """

        store = self._ath_store
        if store is None:
            return {"attempted": False, "reason": "OHLCV_ANCHOR_MISSING",
                    "complete": False, "pages": 0}
        with self._lock:
            now_mono = float(self._mono())
            last = self._last_ohlcv_refresh.get(mint)
            if last is not None and (now_mono - last) < self._ohlcv_ttl:
                return {"attempted": False, "reason": "OHLCV_REFRESH_TTL_ACTIVE",
                        "complete": False, "pages": 0}
        identity = getattr(store, "pool_identity", lambda _m: None)(mint)
        if not isinstance(identity, Mapping) \
                or not identity.get("pool_address"):
            note = getattr(store, "note_v3_pending", None)
            if callable(note):
                try:
                    note(mint, ATH_V3_PAIR_UNAVAILABLE,
                         pending_detail="MIGRATION_PAIR_NOT_REGISTERED")
                except Exception:
                    pass
            with self._lock:
                self._last_ohlcv_refresh[mint] = now_mono
            return {"attempted": False, "reason": ATH_V3_PAIR_UNAVAILABLE,
                    "complete": False, "pages": 0}
        pair = str(identity["pool_address"])
        quote_mint = identity.get("quote_mint")
        created_at = identity.get("pool_created_at") or getattr(
            store, "pool_created_at", lambda _m: None)(mint)
        anchor_epoch = _parse_iso_epoch(created_at, -1.0) \
            if created_at is not None else -1.0
        if anchor_epoch < 0:
            return {"attempted": False, "reason": "OHLCV_ANCHOR_MISSING",
                    "complete": False, "pages": 0}
        span = ATH_V3_COARSE_INTERVAL_SECONDS
        anchor_aligned = (int(anchor_epoch) // span) * span
        now = int(float(self._now()))
        v3_prior = getattr(store, "v3_pair_state", lambda _m: None)(mint) or {}
        prior_complete = v3_prior.get("history_complete") is True
        prior_cursor = v3_prior.get("cursor_unix")
        prior_from = v3_prior.get("window_from_unix")
        incremental = bool(
            prior_complete
            and isinstance(prior_cursor, int)
            and not isinstance(prior_cursor, bool)
            and isinstance(prior_from, int)
            and not isinstance(prior_from, bool)
            and prior_from <= anchor_aligned)
        fetch_from = (prior_cursor + span) if incremental else anchor_aligned
        stage_origin = (ORIGIN_ATH_V3_PAIR_INCREMENTAL if incremental
                        else ORIGIN_ATH_V3_PAIR_COARSE)
        stage_counter = ("v3_pair_incremental_calls" if incremental
                        else "v3_pair_coarse_calls")
        candle_counter = ("v3_candles_incremental" if incremental
                          else "v3_candles_coarse")
        tickets: List[str] = []
        pages = 0
        candles_received = 0
        covered_to: Optional[int] = None
        best_native: Optional[Tuple[Decimal, int]] = None
        failure: Optional[Tuple[str, str]] = None

        def _finish(reason: str, complete: bool) -> Dict[str, Any]:
            with self._lock:
                self._last_ohlcv_refresh[mint] = now_mono
            return {
                "attempted": True,
                "reason": reason,
                "complete": bool(complete),
                "pages": int(pages),
                "time_from_unix": int(fetch_from),
                "time_to_unix": int(covered_to if covered_to is not None
                                    else fetch_from),
                "interval": ATH_V3_COARSE_INTERVAL,
            }

        page_span = self._v3_page_candles * span
        cursor = fetch_from
        with self._collect_tickets(tickets):
            while cursor <= now and pages < self._ohlcv_max_pages:
                if self._background_yield is not None and pages > 0:
                    try:
                        should_yield = bool(self._background_yield())
                    except Exception:
                        should_yield = False
                    if should_yield:
                        with self._lock:
                            self._counters["background_yields"] += 1
                        failure = (ATH_V3_CANDLE_GAP, "BACKGROUND_YIELD")
                        break
                page_to = min(now, cursor + page_span - 1)
                result = self._v3_pair_page(
                    pair=pair, interval=ATH_V3_COARSE_INTERVAL,
                    time_from=cursor, time_to=page_to,
                    origin=stage_origin, mint=mint,
                    timeout_seconds=timeout_seconds)
                pages += 1
                with self._lock:
                    self._counters[stage_counter] += 1
                if result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
                    failure = (self._v3_failure_reason(result),
                               "PAIR_PAGE_" + _http_status_class(result))
                    break
                accepted = self._v3_valid_candles(
                    result, expected_address=pair,
                    window_from=cursor, window_to=page_to,
                    interval_seconds=span)
                if accepted is None:
                    failure = (ATH_V3_HISTORY_INCOMPLETE,
                               "PAIR_PAGE_MALFORMED")
                    break
                candles_received += len(accepted)
                for row in accepted:
                    if best_native is None or row["h"] > best_native[0]:
                        best_native = (row["h"], row["unix_time"])
                covered_to = page_to
                cursor = page_to + 1
        with self._lock:
            self._counters[candle_counter] += candles_received
        if covered_to is None:
            # Nothing new was covered at all.
            if failure is None:
                failure = (ATH_V3_HISTORY_INCOMPLETE, "NO_RANGE_COVERED")
            note = getattr(store, "note_v3_pending", None)
            if callable(note):
                try:
                    note(mint, failure[0], pending_detail=failure[1],
                         request_ticket_ids=tickets)
                except Exception:
                    pass
            return _finish(failure[0], False)
        total_candles = candles_received + max(
            0, int(v3_prior.get("candle_count") or 0))
        # A fully-covered window with ZERO candles ever accepted is a newborn
        # pair the provider has not indexed yet (or one with no trades at
        # all); claiming completeness would freeze an empty maximum, so the
        # attempt stays incomplete and the bounded retry re-scans from the
        # anchor.
        scan_complete = (failure is None and cursor > now
                         and total_candles > 0)
        if failure is not None and failure[0] == ATH_V3_HISTORY_INCOMPLETE:
            # SOME range was covered before the failure: the attempt left a
            # temporal hole between accepted coverage and now, resumed from
            # the durable cursor next attempt.  Auth/throttle failures keep
            # their more specific names.
            failure = (ATH_V3_CANDLE_GAP, failure[1])
        cursor_closed = min(covered_to, now - span)
        cursor_closed = (cursor_closed // span) * span
        if cursor_closed < anchor_aligned:
            cursor_closed = anchor_aligned

        # ---- global coarse peak (prior evidence + this scan) --------------
        prior_peak = v3_prior.get("coarse_peak")
        prior_peak_value = (
            _positive_decimal(prior_peak.get("native_high"))
            if isinstance(prior_peak, Mapping) else None)
        prior_peak_unix = (prior_peak or {}).get("unix_time") \
            if isinstance(prior_peak, Mapping) else None
        global_peak: Optional[Tuple[Decimal, Optional[int]]] = None
        if prior_peak_value is not None:
            global_peak = (prior_peak_value, prior_peak_unix)
        if best_native is not None and (
                global_peak is None or best_native[0] > global_peak[0]):
            global_peak = best_native
        peak_is_new = bool(
            best_native is not None
            and (prior_peak_value is None
                 or best_native[0] > prior_peak_value))

        # ---- Stage 2: 1s refinement of a NEW peak candle ------------------
        refined_value: Optional[Decimal] = None
        refined_unix: Optional[int] = None
        refine_interval_used: Optional[str] = None
        refined_flag = False
        refine_candles: List[Dict[str, Any]] = []
        prior_refined = v3_prior.get("refined_peak")
        needs_refine = bool(
            global_peak is not None
            and global_peak[1] is not None
            and (peak_is_new or not isinstance(prior_refined, Mapping)))
        if needs_refine:
            peak_t = int(global_peak[1])
            with self._collect_tickets(tickets):
                refine_result = self._v3_pair_page(
                    pair=pair, interval=ATH_V3_REFINE_INTERVAL,
                    time_from=peak_t, time_to=peak_t + span - 1,
                    origin=ORIGIN_ATH_V3_PAIR_REFINE, mint=mint,
                    timeout_seconds=timeout_seconds)
            with self._lock:
                self._counters["v3_pair_refine_calls"] += 1
            refine_ok = (
                refine_result.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE)
            accepted = self._v3_valid_candles(
                refine_result, expected_address=pair,
                window_from=peak_t, window_to=peak_t + span - 1,
                interval_seconds=1) if refine_ok else None
            if accepted:
                refine_candles = accepted
                with self._lock:
                    self._counters["v3_candles_refined"] += len(accepted)
                for row in accepted:
                    if refined_value is None or row["h"] > refined_value:
                        refined_value = row["h"]
                        refined_unix = row["unix_time"]
                refine_interval_used = ATH_V3_REFINE_INTERVAL
                refined_flag = True
            else:
                # 1-second data unavailable: retain the valid coarse high
                # with explicit provenance rather than inventing precision.
                with self._lock:
                    self._counters["v3_refine_fallback_coarse"] += 1
                refined_value = global_peak[0]
                refined_unix = peak_t
                refine_interval_used = ATH_V3_COARSE_INTERVAL
                refined_flag = False
        elif isinstance(prior_refined, Mapping):
            refined_value = _positive_decimal(prior_refined.get("native_high"))
            refined_unix = prior_refined.get("unix_time")
            refine_interval_used = prior_refined.get("interval")
            refined_flag = bool(prior_refined.get("refined"))

        # ---- USD valuation of the (possibly new) refined peak -------------
        usd_price: Optional[Decimal] = None
        usd_unix: Optional[int] = None
        usd_interval: Optional[str] = None
        usd_method: Optional[str] = None
        implied_ratio: Optional[Decimal] = None
        divergence: Optional[Dict[str, Any]] = None
        valuation_failure: Optional[Tuple[str, str]] = None
        prior_usd = v3_prior.get("usd_peak")
        needs_valuation = bool(
            refined_value is not None and refined_unix is not None
            and (peak_is_new or not isinstance(prior_usd, Mapping)))
        if needs_valuation:
            if refined_flag and refine_candles:
                native_series = {row["unix_time"]: row
                                 for row in refine_candles}
                val_interval = ATH_V3_REFINE_INTERVAL
                val_from = min(native_series)
                val_to = max(native_series)
                val_seconds = 1
            else:
                peak_t = int(refined_unix)
                native_series = {
                    peak_t: {"unix_time": peak_t, "h": refined_value,
                             "v": None, "v_usd": None}}
                val_interval = ATH_V3_COARSE_INTERVAL
                val_from = peak_t
                val_to = peak_t + span - 1
                val_seconds = span
            with self._collect_tickets(tickets):
                token_result = self._v3_token_page(
                    mint=mint, interval=val_interval,
                    time_from=val_from, time_to=val_to,
                    timeout_seconds=timeout_seconds)
            if token_result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
                valuation_failure = (
                    self._v3_failure_reason(token_result),
                    "VALUATION_" + _http_status_class(token_result))
            else:
                token_candles = self._v3_valid_candles(
                    token_result, expected_address=mint,
                    window_from=val_from, window_to=val_to,
                    interval_seconds=val_seconds)
                if not token_candles:
                    valuation_failure = (
                        ATH_V3_USD_CONVERSION_UNRESOLVED,
                        "VALUATION_SERIES_EMPTY")
                else:
                    outcome = self._v3_value_peak(
                        native_series=native_series,
                        token_candles=token_candles,
                        peak_unix=int(refined_unix),
                        peak_native=refined_value,
                    )
                    (usd_price, usd_unix, usd_method, implied_ratio,
                     divergence, valuation_failure) = outcome
                    if usd_price is not None:
                        usd_interval = val_interval

        # ---- atomic commit -------------------------------------------------
        observe = getattr(store, "observe_v3_pair_ath", None)
        if callable(observe):
            try:
                observe(
                    mint=mint,
                    pair_address=pair,
                    quote_mint=quote_mint,
                    anchor_unix=anchor_aligned,
                    window_from_unix=(anchor_aligned if not incremental
                                      else prior_from),
                    window_to_unix=covered_to,
                    cursor_unix=cursor_closed,
                    history_complete=bool(scan_complete or prior_complete),
                    candles_received=candles_received,
                    coarse_peak_native=(best_native[0]
                                        if best_native is not None else None),
                    coarse_peak_unix=(best_native[1]
                                      if best_native is not None else None),
                    refined_peak_native=refined_value,
                    refined_peak_unix=refined_unix,
                    refine_interval=refine_interval_used,
                    refined=refined_flag,
                    usd_peak_price=usd_price,
                    usd_peak_unix=usd_unix,
                    usd_valuation_interval=usd_interval,
                    usd_valuation_method=usd_method,
                    implied_quote_usd=implied_ratio,
                    outlier_mode=BIRDEYE_V3_OUTLIER_MODE_PROVIDER_DEFAULT,
                    divergence=divergence,
                    request_ticket_ids=tickets,
                )
            except Exception:
                pass
        pending: Optional[Tuple[str, str]] = None
        if failure is not None:
            pending = failure
        elif valuation_failure is not None:
            pending = valuation_failure
            with self._lock:
                self._counters["v3_valuation_unresolved"] += 1
        if pending is not None:
            note = getattr(store, "note_v3_pending", None)
            if callable(note):
                try:
                    note(mint, pending[0], pending_detail=pending[1],
                         request_ticket_ids=())
                except Exception:
                    pass
            return _finish(pending[0], False)
        return _finish(
            "ATH_V3_HISTORY_COMPLETE" if (scan_complete or prior_complete)
            else ATH_V3_HISTORY_INCOMPLETE,
            bool(scan_complete or prior_complete))

    #: USD/native peak-ratio coherence band: every same-second ratio in the
    #: refinement window must sit within this factor of the window median.
    _V3_RATIO_BAND = Decimal("1.5")
    #: Absolute sanity band for the implied QUOTE-asset USD rate.  The pool
    #: identity is proof-derived (migrate_v2 admits only WSOL quotes), so the
    #: implied rate is a major-asset USD price.  The band spans eight orders
    #: of magnitude -- it encodes no market opinion -- while a CONSISTENTLY
    #: inverted series is wrong by ~10^12 and lands far outside it.  This is
    #: how orientation is VALIDATED structurally rather than guessed from
    #: whichever number looks plausible.
    _V3_RATIO_ABS_MIN = Decimal("0.01")
    _V3_RATIO_ABS_MAX = Decimal("1000000")
    #: Relative tolerance for the identical-trades volume check between the
    #: pair series and the token USD series at the same second.
    _V3_VOLUME_REL_TOLERANCE = Decimal("0.001")

    def _v3_value_peak(
        self,
        *,
        native_series: Mapping[int, Mapping[str, Any]],
        token_candles: List[Dict[str, Any]],
        peak_unix: int,
        peak_native: Decimal,
    ) -> Tuple[Optional[Decimal], Optional[int], Optional[str],
               Optional[Decimal], Optional[Dict[str, Any]],
               Optional[Tuple[str, str]]]:
        """Value ONE refined pair peak in USD from same-timestamp candles.

        Primary path: the token USD candle at the exact peak second whose
        trade volumes match the pair candle (same trades, provider-converted
        to USD).  Fallback within the same responses: the median USD/native
        ratio over volume-matched seconds applied to the native peak, with an
        explicit method label.  No matched second at all, or an incoherent
        ratio (orientation flip), returns a named failure instead of a value.
        """

        token_by_time = {row["unix_time"]: row for row in token_candles}
        ratios: List[Decimal] = []
        matched: List[int] = []
        volume_matched: List[int] = []
        volume_mismatched: List[int] = []
        with localcontext() as ctx:
            ctx.prec = 60
            for when, native_row in native_series.items():
                token_row = token_by_time.get(when)
                if token_row is None:
                    continue
                native_high = native_row.get("h")
                token_high = token_row.get("h")
                if native_high is None or token_high is None:
                    continue
                matched.append(when)
                ratios.append(token_high / native_high)
                native_volume = native_row.get("v")
                token_volume = token_row.get("v")
                if native_volume is None or token_volume is None:
                    continue
                scale = max(abs(native_volume), abs(token_volume))
                if scale == 0 or abs(native_volume - token_volume) <= (
                        self._V3_VOLUME_REL_TOLERANCE * scale):
                    volume_matched.append(when)
                else:
                    volume_mismatched.append(when)
            if not matched:
                return (None, None, None, None, None,
                        (ATH_V3_USD_CONVERSION_UNRESOLVED,
                         "NO_MATCHED_TIMESTAMPS"))
            ordered = sorted(ratios)
            median = ordered[len(ordered) // 2]
            if median <= 0:
                return (None, None, None, None, None,
                        (ATH_V3_INVERSION_UNRESOLVED, "RATIO_NON_POSITIVE"))
            if not (self._V3_RATIO_ABS_MIN <= median
                    <= self._V3_RATIO_ABS_MAX):
                return (None, None, None, None, None,
                        (ATH_V3_INVERSION_UNRESOLVED,
                         "RATIO_OUTSIDE_ABSOLUTE_BAND"))
            divergence: Optional[Dict[str, Any]] = None
            if volume_mismatched:
                divergence = {
                    "kind": "ATH_TOKEN_PAIR_DIVERGENCE",
                    "volume_matched_candles": len(volume_matched),
                    "volume_mismatched_candles": len(volume_mismatched),
                    "matched_candles": len(matched),
                }
            token_peak_row = token_by_time.get(peak_unix)
            if token_peak_row is not None:
                peak_ratio = token_peak_row["h"] / peak_native
                if not (median / self._V3_RATIO_BAND <= peak_ratio
                        <= median * self._V3_RATIO_BAND):
                    return (None, None, None, None, divergence,
                            (ATH_V3_INVERSION_UNRESOLVED,
                             "PEAK_RATIO_OUTSIDE_BAND"))
                peak_volume_ok = (
                    peak_unix in volume_matched
                    or (native_series.get(peak_unix, {}).get("v") is None))
                if peak_volume_ok:
                    return (token_peak_row["h"], peak_unix,
                            "SAME_SECOND_PROVIDER_USD", peak_ratio,
                            divergence, None)
            # Fallback: median ratio over volume-matched candles only.
            fallback_pool = [
                token_by_time[when]["h"] / native_series[when]["h"]
                for when in volume_matched]
            if not fallback_pool:
                return (None, None, None, None, divergence,
                        (ATH_V3_USD_CONVERSION_UNRESOLVED,
                         "NO_VOLUME_MATCHED_CANDLES"))
            fallback_sorted = sorted(fallback_pool)
            fallback_median = fallback_sorted[len(fallback_sorted) // 2]
            if not (median / self._V3_RATIO_BAND <= fallback_median
                    <= median * self._V3_RATIO_BAND):
                return (None, None, None, None, divergence,
                        (ATH_V3_INVERSION_UNRESOLVED,
                         "FALLBACK_RATIO_OUTSIDE_BAND"))
            return (peak_native * fallback_median, peak_unix,
                    "MEDIAN_RATIO_CONVERSION", fallback_median,
                    divergence, None)

    def ath_snapshot(self, mint: str) -> Optional[Dict[str, Any]]:
        central_snapshot = getattr(self._ath_store, "snapshot", None)
        if callable(central_snapshot):
            try:
                record = central_snapshot(mint)
            except Exception:
                record = None
            if isinstance(record, dict):
                return {
                    "ath_price_usd": record.get("ath_price"),
                    "ath_market_cap_usd": record.get("ath_market_cap"),
                    "observed_at_utc": record.get("ath_timestamp"),
                    "provider": record.get("ath_provider"),
                    "observation_type": record.get("ath_observation_type"),
                    "sample_count": None,
                    "provisional_ready": record.get("ath_status") == "CONFIRMED",
                    "discord_eligible": record.get("ath_market_cap") is not None,
                    "central_ath": record,
                }
        with self._lock:
            record = self._ath.get(mint)
            return dict(record) if record is not None else None

    def _reserve_start_slot(self) -> float:
        """Allocate the next request-START instant under the shared pacing gate.

        Spacing is enforced on request starts across every worker; the
        allocation itself is O(1) under the lock, and the actual wait
        happens outside the lock so paced callers never serialize each
        other's response time or retries.
        """

        with self._lock:
            now = float(self._mono())
            base = now if self._next_start_mono is None else max(
                now, self._next_start_mono)
            self._next_start_mono = base + self._min_interval
            self._last_call_mono = base
            return base

    def _timeout_result(self) -> Stage29_2BirdeyeHttpResult:
        """Deadline-exhaustion refusal: timeout-shaped, never a success."""

        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=_iso(self._now()),
        )

    def _is_stale_price(self, path: str, result: Stage29_2BirdeyeHttpResult) -> bool:
        if path != BIRDEYE_PATH_PRICE or result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            return False
        data = (result.body or {}).get("data")
        if not isinstance(data, dict):
            return False
        raw = data.get("updateUnixTime")
        if raw is None:
            return False
        try:
            age = float(self._now()) - float(raw)
        except (TypeError, ValueError):
            return True
        return age < -5.0 or age > self._max_data_age

    def _record_diagnostic_locked(
        self, path: str, params: Mapping[str, str], result: Stage29_2BirdeyeHttpResult,
        *, request_ticket_id: Optional[str] = None,
    ) -> bool:
        mint = str(params.get("address") or "")
        if not mint:
            return False
        prior = self._diagnostics.setdefault(mint, {"endpoints": {}})
        endpoints = prior["endpoints"]
        previous = endpoints.get(path) or {}
        state, reason, fields, provider_ts, stale = self._classify_endpoint(path, result)
        first_success = previous.get("first_success_at_utc")
        if first_success is None and state == MARKET_READY:
            first_success = result.fetched_at_utc
        provider_age_seconds: Optional[float] = None
        if provider_ts is not None:
            provider_epoch = _parse_iso_epoch(provider_ts, float("nan"))
            if provider_epoch == provider_epoch:
                provider_age_seconds = float(self._now()) - provider_epoch
        stale_history = list(previous.get("stale_responses") or ())
        if stale:
            stale_history.append({
                "provider_timestamp_utc": provider_ts,
                "fetched_at_utc": result.fetched_at_utc,
                "provider_age_seconds": provider_age_seconds,
                "configured_freshness_ttl_seconds": self._max_data_age,
                "endpoint": path,
                "request_ticket_id": request_ticket_id,
                "rejection_reason": reason,
            })
            del stale_history[:-32]
        endpoints[path] = {
            "request_count": int(previous.get("request_count") or 0) + 1,
            "state": state,
            "reason_code": reason,
            "fetched_at_utc": result.fetched_at_utc,
            "first_success_at_utc": first_success,
            "provider_timestamp_utc": provider_ts,
            # Transport receipt time and provider event time are independent
            # evidence.  In particular, fetched_at_utc is never substituted
            # for a stale provider timestamp to manufacture freshness.
            "provider_age_seconds": provider_age_seconds,
            "configured_freshness_ttl_seconds": self._max_data_age,
            "endpoint": path,
            "request_ticket_id": request_ticket_id,
            "rejection_reason": reason if stale else None,
            "stale_responses": stale_history,
            "fields": fields,
        }
        return stale

    def _classify_endpoint(
        self, path: str, result: Stage29_2BirdeyeHttpResult
    ) -> Tuple[str, str, Dict[str, bool], Optional[str], bool]:
        fields: Dict[str, bool] = {}
        if result.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE:
            status = int(getattr(result, "http_status_code", 0) or 0)
            if status == 404:
                return MARKET_INDEXING, "PROVIDER_NOT_INDEXED", fields, None, False
            # A credential failure is NOT a malformed request/payload.  Keeping
            # 401/403 distinct from 400 is what lets the operator see "the key
            # is rejected" instead of "the provider sent garbage".
            if status == 401:
                return (MARKET_INVALID, "PROVIDER_" + MARKET_CREDENTIAL_INVALID,
                        fields, None, False)
            if status == 403:
                return (MARKET_INVALID,
                        "PROVIDER_" + MARKET_CREDENTIAL_UNAUTHORIZED,
                        fields, None, False)
            if status == 400:
                return MARKET_INVALID, "PROVIDER_REQUEST_REJECTED", fields, None, False
            return MARKET_INCOMPLETE, "PROVIDER_READ_FAILED", fields, None, False
        body = result.body
        if not isinstance(body, dict):
            return MARKET_INVALID, "PROVIDER_BODY_INVALID", fields, None, False
        data = body.get("data")
        if data is None:
            return MARKET_INDEXING, "PROVIDER_NOT_INDEXED", fields, None, False
        if not isinstance(data, dict):
            return MARKET_INVALID, "PROVIDER_DATA_INVALID", fields, None, False
        if path == BIRDEYE_PATH_PRICE:
            raw_price = data.get("value")
            fields["price"] = raw_price is not None
            if raw_price is None:
                return MARKET_INCOMPLETE, "PRICE_MISSING", fields, None, False
            if _positive_decimal(raw_price) is None:
                return MARKET_INVALID, "PRICE_INVALID", fields, None, False
            raw_ts = data.get("updateUnixTime")
            fields["provider_timestamp"] = raw_ts is not None
            if raw_ts is None:
                return MARKET_INCOMPLETE, "PROVIDER_TIMESTAMP_MISSING", fields, None, False
            try:
                epoch = float(raw_ts)
                provider_ts = _iso(epoch)
                age = float(self._now()) - epoch
            except (TypeError, ValueError, OSError):
                return MARKET_INVALID, "PROVIDER_TIMESTAMP_INVALID", fields, None, False
            if age < -5.0 or age > self._max_data_age:
                return MARKET_STALE, "PRICE_PROVIDER_TIMESTAMP_STALE", fields, provider_ts, True
            return MARKET_READY, "PRICE_FRESH", fields, provider_ts, False
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            mc_keys = ("mc", "marketCap", "market_cap")
            lp_keys = ("liquidity", "liquidityUsd", "liquidity_usd")
            raw_mc = next((data.get(k) for k in mc_keys if k in data), None)
            raw_lp = next((data.get(k) for k in lp_keys if k in data), None)
            fields.update({"market_cap": raw_mc is not None, "liquidity": raw_lp is not None})
            if raw_mc is not None and _positive_decimal(raw_mc) is None:
                return MARKET_INVALID, "MARKET_CAP_INVALID", fields, None, False
            if raw_lp is not None and _positive_decimal(raw_lp) is None:
                return MARKET_INVALID, "LIQUIDITY_INVALID", fields, None, False
            missing = []
            if raw_mc is None:
                missing.append("MARKET_CAP")
            if raw_lp is None:
                missing.append("LIQUIDITY")
            if missing:
                return MARKET_INCOMPLETE, "MISSING_" + "_".join(missing), fields, None, False
            return MARKET_READY, "OVERVIEW_COMPLETE", fields, None, False
        if path == BIRDEYE_PATH_OHLCV:
            items = data.get("items")
            fields["ohlcv"] = isinstance(items, list) and bool(items)
            if not isinstance(items, list) or not items:
                self._counters["ohlcv_indexing"] += 1
                return MARKET_INDEXING, "OHLCV_NOT_INDEXED", fields, None, False
            if not any(isinstance(item, dict) and _positive_decimal(item.get("h")) is not None
                       for item in items):
                return MARKET_INVALID, "OHLCV_INVALID", fields, None, False
            return MARKET_READY, "OHLCV_PRESENT", fields, None, False
        return MARKET_INVALID, "ENDPOINT_UNEXPECTED", fields, None, False

    def _observe_locked(
        self, path: str, params: Mapping[str, str], result: Stage29_2BirdeyeHttpResult
    ) -> None:
        mint = str(params.get("address") or "")
        if not mint:
            return
        data = (result.body or {}).get("data")
        if not isinstance(data, dict):
            self._counters["malformed_bodies"] += 1
            return
        if path == BIRDEYE_PATH_PRICE:
            value = _positive_decimal(data.get("value"))
            if value is None:
                return
            observed = self._price_observed_iso(data, result.fetched_at_utc)
            observed_epoch = _parse_iso_epoch(observed, float(self._now()))
            self._first_live_epoch.setdefault(mint, observed_epoch)
            prior = self._ath.get(mint)
            if prior is None or value > Decimal(prior["ath_price_usd"]):
                self._ath[mint] = {
                    "ath_price_usd": _decimal_text(value),
                    "observed_at_utc": observed,
                    "provider": "PAID_MARKET_PRIMARY",
                    "observation_type": "ATH_PROVISIONAL_LIVE_OBSERVED",
                    "sample_count": int((prior or {}).get("sample_count") or 0) + 1,
                    "first_live_observed_at_utc": (prior or {}).get(
                        "first_live_observed_at_utc", observed),
                    "last_live_observed_at_utc": observed,
                    "provisional_ready": False,
                    "discord_eligible": False,
                }
            else:
                prior["sample_count"] = int(prior.get("sample_count") or 0) + 1
                prior["last_live_observed_at_utc"] = observed
            current = self._ath[mint]
            first_epoch = _parse_iso_epoch(
                current.get("first_live_observed_at_utc"), observed_epoch)
            current["provisional_ready"] = (
                int(current.get("sample_count") or 0) >= 3
                and observed_epoch - first_epoch >= 60.0
            )
            self._counters["ath_observations"] += 1
            observe_current = getattr(self._ath_store, "observe_provider_current", None)
            if callable(observe_current):
                try:
                    observe_current(
                        mint=mint,
                        price_usd=value,
                        observed_at=observed,
                        confirmed=False,
                    )
                except Exception:
                    pass
        elif path == BIRDEYE_PATH_OHLCV:
            best: Optional[Tuple[Decimal, str]] = None
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                value = _positive_decimal(item.get("h"))
                if value is None:
                    continue
                try:
                    observed = _iso(float(item.get("unixTime")))
                except (TypeError, ValueError, OSError):
                    observed = result.fetched_at_utc
                if best is None or value > best[0]:
                    best = (value, observed)
                self._counters["ath_observations"] += 1
            if best is None:
                return
            value, observed = best
            try:
                range_from = int(params.get("time_from"))
                range_to = int(params.get("time_to"))
            except (TypeError, ValueError):
                range_from = range_to = -1
            prior = self._ath.get(mint)
            if prior is None or value >= Decimal(prior["ath_price_usd"]):
                self._ath[mint] = {
                    "ath_price_usd": _decimal_text(value),
                    "observed_at_utc": observed,
                    "provider": "PAID_MARKET_PRIMARY",
                    # One valid page is not proof that every page from pool
                    # creation through now was present.  refresh_ath_history
                    # performs the only complete-window promotion.
                    "observation_type": "ATH_PAID_OHLCV_INCOMPLETE",
                    "sample_count": int((prior or {}).get("sample_count") or 0),
                    "first_live_observed_at_utc": (prior or {}).get(
                        "first_live_observed_at_utc"),
                    "last_live_observed_at_utc": (prior or {}).get(
                        "last_live_observed_at_utc"),
                    "provisional_ready": bool((prior or {}).get("provisional_ready")),
                    "discord_eligible": False,
                }
            observe_ohlcv = getattr(self._ath_store, "observe_ohlcv_high", None)
            if callable(observe_ohlcv) and range_from >= 0:
                try:
                    observe_ohlcv(
                        mint=mint,
                        high_price_usd=value,
                        candle_timestamp=observed,
                        history_complete=False,
                        interval=params.get("type") or "1m",
                        time_from_unix=range_from,
                        time_to_unix=range_to,
                    )
                except Exception:
                    pass

        provisional = confirmed = 0
        for record in self._ath.values():
            if record.get("observation_type") == "ATH_PAID_OHLCV_CONFIRMED":
                confirmed += 1
            else:
                provisional += 1
        self._counters["ath_provisional_mints"] = provisional
        self._counters["ath_confirmed_mints"] = confirmed

    @staticmethod
    def _price_observed_iso(data: Mapping[str, Any], fallback: str) -> str:
        try:
            return _iso(float(data.get("updateUnixTime")))
        except (TypeError, ValueError, OSError):
            return fallback

    def _error_result(self) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
            http_status_code=0,
            body=None,
            fetched_at_utc=_iso(self._now()),
        )

    def _rate_limited_result(self) -> Stage29_2BirdeyeHttpResult:
        """Refusal for a request suppressed by the open backoff window.

        Carries the 429 status so ``_scheduler_failure_result`` projects the
        already-existing closed-set ``PROVIDER_RATE_LIMIT`` reason: the
        operator sees "throttled", not a generic HTTP failure. No request was
        made, so no counter in the HTTP-call family moves.
        """

        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
            http_status_code=429,
            body=None,
            fetched_at_utc=_iso(self._now()),
        )


__all__ = ("PaidBirdeyeMarketTransport",)
