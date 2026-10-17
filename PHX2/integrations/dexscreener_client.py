"""Bounded, redaction-safe DexScreener HTTP client.

The client owns no credentials and persists no response body. Its public
methods return validated JSON shapes plus closed-set telemetry; callers decide
candidate semantics.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple


DEX_BACKFILL_SUCCESS = "DEX_BACKFILL_SUCCESS"
DEX_BACKFILL_PARTIAL = "DEX_BACKFILL_PARTIAL"
DEX_BACKFILL_EMPTY = "DEX_BACKFILL_EMPTY"
DEX_BACKFILL_UNAVAILABLE = "DEX_BACKFILL_UNAVAILABLE"
DEX_BACKFILL_INVALID_RESPONSE = "DEX_BACKFILL_INVALID_RESPONSE"
DEX_BACKFILL_STATUSES = (
    DEX_BACKFILL_SUCCESS,
    DEX_BACKFILL_PARTIAL,
    DEX_BACKFILL_EMPTY,
    DEX_BACKFILL_UNAVAILABLE,
    DEX_BACKFILL_INVALID_RESPONSE,
)

DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
SOL_MINT = "So11111111111111111111111111111111111111112"
PUMPSWAP_DEX_ID = "pumpswap"

# The former chain-wide "/latest/dex/pairs/solana" surface is retired: the
# provider documents that path shape only as a pair-specific lookup with a
# required pair identifier, so a chain-wide request is structurally invalid
# (it failed deterministically in every preserved sweep and never returned a
# pair).  See RETIRED_BACKFILL_SOURCES in dexscreener_restart_backfill.
LATEST_TOKEN_PROFILES_PATH = "/token-profiles/latest/v1"
SOLANA_TOKENS_PATH = "/tokens/v1/solana/"


class DexScreenerError(RuntimeError):
    """Closed-set client failure; message never includes URL or body."""


@dataclass(frozen=True)
class DexClientBounds:
    timeout_seconds: float = 15.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_requests: int = 10
    max_retries: int = 1
    request_spacing_seconds: float = 1.0

    def validate(self) -> None:
        if not 0.1 <= float(self.timeout_seconds) <= 30.0:
            raise ValueError("DEX_TIMEOUT_BOUND_INVALID")
        if not 1024 <= int(self.max_response_bytes) <= 8 * 1024 * 1024:
            raise ValueError("DEX_RESPONSE_BYTE_BOUND_INVALID")
        if not 1 <= int(self.max_requests) <= 32:
            raise ValueError("DEX_REQUEST_BOUND_INVALID")
        if not 0 <= int(self.max_retries) <= 2:
            raise ValueError("DEX_RETRY_BOUND_INVALID")
        if not 0.0 <= float(self.request_spacing_seconds) <= 5.0:
            raise ValueError("DEX_RATE_SPACING_BOUND_INVALID")


@dataclass(frozen=True)
class DexHttpResult:
    status_code: int
    body: bytes


def _default_transport(
    url: str, *, timeout_seconds: float, max_response_bytes: int
) -> DexHttpResult:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PHX2-Dex-Restart-Backfill/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(timeout_seconds)
        ) as response:
            status = int(getattr(response, "status", 200))
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    if int(length) > int(max_response_bytes):
                        raise DexScreenerError("DEX_RESPONSE_TOO_LARGE")
                except ValueError:
                    pass
            body = response.read(int(max_response_bytes) + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read(int(max_response_bytes) + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DexScreenerError("DEX_TRANSPORT_UNAVAILABLE") from exc
    if len(body) > int(max_response_bytes):
        raise DexScreenerError("DEX_RESPONSE_TOO_LARGE")
    return DexHttpResult(status_code=status, body=body)


def _safe_error_class(exc: object) -> str:
    name = type(exc).__name__
    if 0 < len(name) <= 64 and all(c.isalnum() or c == "_" for c in name):
        return name
    return "UNSAFE_EXCEPTION_CLASS"


class DexscreenerClient:
    """One bounded request-budget owner, including all retry attempts."""

    def __init__(
        self,
        *,
        bounds: DexClientBounds = DexClientBounds(),
        transport: Callable[..., DexHttpResult] = _default_transport,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        bounds.validate()
        if not callable(transport):
            raise ValueError("DEX_TRANSPORT_INVALID")
        self.bounds = bounds
        self._transport = transport
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._lock = threading.Lock()
        self._last_request_at: Optional[float] = None
        self._stats: Dict[str, Any] = {
            "requests_attempted": 0,
            "requests_succeeded": 0,
            "requests_failed": 0,
            "retry_count": 0,
            "rate_limit_count": 0,
            "invalid_response_count": 0,
            "last_error_class": None,
        }

    def _rate_space(self) -> None:
        with self._lock:
            prior = self._last_request_at
            now = float(self._monotonic())
            wait = 0.0 if prior is None else max(
                0.0,
                float(self.bounds.request_spacing_seconds) - (now - prior),
            )
        if wait > 0:
            self._sleep(wait)
        with self._lock:
            self._last_request_at = float(self._monotonic())

    def _request_json(self, path: str) -> Tuple[Optional[Any], str]:
        last_status = DEX_BACKFILL_UNAVAILABLE
        for attempt in range(int(self.bounds.max_retries) + 1):
            with self._lock:
                if self._stats["requests_attempted"] >= int(
                    self.bounds.max_requests
                ):
                    self._stats["last_error_class"] = (
                        "DEX_REQUEST_BUDGET_EXHAUSTED")
                    return None, DEX_BACKFILL_PARTIAL
                self._stats["requests_attempted"] += 1
                if attempt:
                    self._stats["retry_count"] += 1
            self._rate_space()
            try:
                result = self._transport(
                    DEXSCREENER_BASE_URL + path,
                    timeout_seconds=float(self.bounds.timeout_seconds),
                    max_response_bytes=int(self.bounds.max_response_bytes),
                )
                code = int(result.status_code)
                if code == 429:
                    with self._lock:
                        self._stats["rate_limit_count"] += 1
                        self._stats["requests_failed"] += 1
                        self._stats["last_error_class"] = "HTTP_429"
                    if attempt < int(self.bounds.max_retries):
                        continue
                    return None, DEX_BACKFILL_UNAVAILABLE
                if code < 200 or code >= 300:
                    with self._lock:
                        self._stats["requests_failed"] += 1
                        self._stats["last_error_class"] = "HTTP_STATUS_NON_2XX"
                    if code >= 500 and attempt < int(self.bounds.max_retries):
                        continue
                    return None, DEX_BACKFILL_UNAVAILABLE
                try:
                    value = json.loads(result.body.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    with self._lock:
                        self._stats["requests_failed"] += 1
                        self._stats["invalid_response_count"] += 1
                        self._stats["last_error_class"] = "DEX_JSON_INVALID"
                    return None, DEX_BACKFILL_INVALID_RESPONSE
                with self._lock:
                    self._stats["requests_succeeded"] += 1
                return value, DEX_BACKFILL_SUCCESS
            except DexScreenerError as exc:
                with self._lock:
                    self._stats["requests_failed"] += 1
                    self._stats["last_error_class"] = str(exc)[:64]
                last_status = DEX_BACKFILL_UNAVAILABLE
                if attempt < int(self.bounds.max_retries):
                    continue
                return None, last_status
            except Exception as exc:
                with self._lock:
                    self._stats["requests_failed"] += 1
                    self._stats["last_error_class"] = _safe_error_class(exc)
                return None, DEX_BACKFILL_UNAVAILABLE
        return None, last_status

    def latest_token_profiles(self) -> Tuple[List[Dict[str, Any]], str]:
        value, status = self._request_json(LATEST_TOKEN_PROFILES_PATH)
        if value is None:
            return [], status
        if not isinstance(value, list):
            return [], DEX_BACKFILL_INVALID_RESPONSE
        normalized = [dict(item) for item in value if isinstance(item, Mapping)]
        return normalized, (
            DEX_BACKFILL_SUCCESS if normalized else DEX_BACKFILL_EMPTY)

    def token_pairs(
        self, mints: List[str]
    ) -> Tuple[List[Dict[str, Any]], str]:
        clean = [mint for mint in mints if isinstance(mint, str) and mint]
        if not clean or len(clean) > 30:
            return [], DEX_BACKFILL_INVALID_RESPONSE
        value, status = self._request_json(
            SOLANA_TOKENS_PATH + ",".join(clean))
        if value is None:
            return [], status
        if not isinstance(value, list):
            return [], DEX_BACKFILL_INVALID_RESPONSE
        normalized = [dict(item) for item in value if isinstance(item, Mapping)]
        return normalized, (
            DEX_BACKFILL_SUCCESS if normalized else DEX_BACKFILL_EMPTY)

    def current_sol_price_usd(self) -> Tuple[Optional[float], str]:
        pairs, status = self.token_pairs([SOL_MINT])
        for pair in pairs:
            try:
                price = float(pair.get("priceUsd") or 0)
            except (TypeError, ValueError):
                continue
            if price > 0:
                return price, DEX_BACKFILL_SUCCESS
        return None, status

    def highest_liquidity_pumpswap_pair(
        self, mint: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        pairs, status = self.token_pairs([mint])
        valid = [
            pair for pair in pairs
            if str(pair.get("chainId") or "solana").lower() == "solana"
            and str(pair.get("dexId") or "").lower() == PUMPSWAP_DEX_ID
            and str((pair.get("baseToken") or {}).get("address") or "") == mint
            and isinstance(pair.get("pairAddress"), str)
            and bool(pair.get("pairAddress"))
        ]
        if not valid:
            return None, (
                DEX_BACKFILL_EMPTY if status == DEX_BACKFILL_SUCCESS else status)

        def liquidity(pair: Mapping[str, Any]) -> float:
            try:
                return float((pair.get("liquidity") or {}).get("usd") or 0)
            except (TypeError, ValueError):
                return 0.0

        return max(valid, key=liquidity), DEX_BACKFILL_SUCCESS

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **dict(self._stats),
                "max_requests": int(self.bounds.max_requests),
                "max_retries": int(self.bounds.max_retries),
                "timeout_seconds": float(self.bounds.timeout_seconds),
                "max_response_bytes": int(self.bounds.max_response_bytes),
                "request_spacing_seconds": float(
                    self.bounds.request_spacing_seconds),
            }


__all__ = (
    "DEX_BACKFILL_SUCCESS",
    "DEX_BACKFILL_PARTIAL",
    "DEX_BACKFILL_EMPTY",
    "DEX_BACKFILL_UNAVAILABLE",
    "DEX_BACKFILL_INVALID_RESPONSE",
    "DEX_BACKFILL_STATUSES",
    "DEXSCREENER_BASE_URL",
    "SOL_MINT",
    "PUMPSWAP_DEX_ID",
    "DexScreenerError",
    "DexClientBounds",
    "DexHttpResult",
    "DexscreenerClient",
)