"""Build #29 cap-1 — real read-only market sidecar (price + MC + LP, delayed refresh).

OUT-OF-REPO operator glue. Produces the decimal-text market context the committed
``Stage30_11_13RevalidationRequest`` requires — ``current_price`` (committed
``Stage29_2BirdeyePriceSource``), ``current_market_cap_usd`` + ``liquidity_usd`` (committed
``Stage30_4_3BirdeyeMarketContextSource`` via the Stage 30.4.1 adapter) — with the B.1-style
escalating delayed refresh (immediate / +10s / +30s / +60s relative to
``migration_event_time_utc``, while ANY of price/MC/LP is Unknown, stop when all three KNOWN).
Never fabricates: a missing value stays ``None`` and the request then fails closed at the
committed composer. Per-candidate blocking-but-bounded (cap-1 processes one candidate, stops
after one send) via an injected ``sleep_fn`` so the selftest advances a fake clock with no real
sleep.

Egress: only read-only Birdeye GETs via the injected transport (real urllib at the armed
ceremony; a deterministic fake in the selftest). REDACTION: emits only decimal-text values +
closed-set status; no ``birdeye`` substring (the runner labels basis ``REAL_MARKET_*``).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PHX2.stage29.stage29_2_birdeye_price_source import (  # committed  # noqa: E402
    Stage29_2BirdeyePriceSource,
)
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (  # committed  # noqa: E402
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_4_compact_market_context_adapter import (  # committed  # noqa: E402
    project_market_context,
)
from PHX2.stage29.pumpswap_program_constants import USDC_MINT  # noqa: E402
from PHX2.free_tier_producer.pumpswap_reserves import (  # noqa: E402
    PumpSwapReserveIndex,
)


REFRESH_OFFSETS_SECONDS: Tuple[int, ...] = (0, 10, 30, 60)


@dataclass(frozen=True)
class Cap1MarketCaps:
    max_calls_per_token: int = 4
    max_calls_total: int = 128
    max_delayed_refresh_seconds: int = 60
    max_failures_total: int = 8
    max_consecutive_failures: int = 3

    def __post_init__(self) -> None:
        bounds = {
            "max_calls_per_token": (1, 16),
            "max_calls_total": (1, 8192),
            "max_delayed_refresh_seconds": (0, 3600),
            "max_failures_total": (1, 8192),
            "max_consecutive_failures": (1, 256),
        }
        for name, (lo, hi) in bounds.items():
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
                raise ValueError(f"{name} must be an int in [{lo}, {hi}]")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class Cap1MarketSidecar:
    """Resolves price + MC + LP for one candidate with the escalating delayed refresh."""

    def __init__(
        self,
        *,
        transport: Any,
        endpoint_secret: Any,
        timeout_seconds: int = 30,
        enabled: bool = True,
        caps: Optional[Cap1MarketCaps] = None,
        readiness_tracker: Any = None,
        reserve_index: Optional[PumpSwapReserveIndex] = None,
        ath_store: Any = None,
    ) -> None:
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout = int(timeout_seconds)
        self._enabled = bool(enabled)
        self._caps = caps or Cap1MarketCaps()
        self._readiness_tracker = readiness_tracker
        self._reserve_index = reserve_index
        self._ath_store = ath_store
        self._counters: Dict[str, int] = {
            "attempts": 0,
            "present": 0,
            "failures": 0,
            "capped": 0,
        }
        self._per_mint_attempts: Dict[str, int] = {}
        # Failure ceilings are per mint.  The former shared counters let one
        # newborn token starve every later candidate in the same watch tick.
        self._per_mint_failures: Dict[str, int] = {}
        self._per_mint_consecutive_failures: Dict[str, int] = {}

    def central_ath_snapshot(self, mint: str) -> Optional[Dict[str, Any]]:
        """Return the current central maximum independently of market-attempt selection."""

        if self._ath_store is None:
            return None
        snapshot_fn = getattr(self._ath_store, "snapshot", None)
        if not callable(snapshot_fn):
            return {}
        try:
            return dict(snapshot_fn(mint) or {})
        except Exception:
            return {}

    def _fetch_one(self, mint: str, attempt_at_utc: str, scheduled_offset_s: int) -> Dict[str, Any]:
        if not self._enabled or self._transport is None or self._endpoint_secret is None:
            return self._unknown_attempt(attempt_at_utc, scheduled_offset_s, "REAL_MARKET_DISABLED")
        if self._counters["attempts"] >= self._caps.max_calls_total:
            self._counters["capped"] += 1
            return self._unknown_attempt(attempt_at_utc, scheduled_offset_s, "REAL_MARKET_CAP")
        if self._per_mint_attempts.get(mint, 0) >= self._caps.max_calls_per_token:
            self._counters["capped"] += 1
            return self._unknown_attempt(attempt_at_utc, scheduled_offset_s, "REAL_MARKET_CAP")
        if (self._per_mint_consecutive_failures.get(mint, 0)
                >= self._caps.max_consecutive_failures):
            self._counters["capped"] += 1
            return self._unknown_attempt(attempt_at_utc, scheduled_offset_s, "REAL_MARKET_CAP")
        if self._per_mint_failures.get(mint, 0) >= self._caps.max_failures_total:
            self._counters["capped"] += 1
            return self._unknown_attempt(attempt_at_utc, scheduled_offset_s, "REAL_MARKET_CAP")

        self._counters["attempts"] += 1
        self._per_mint_attempts[mint] = self._per_mint_attempts.get(mint, 0) + 1

        price_value: Optional[str] = None
        price_source: Any = None
        try:
            price_source = Stage29_2BirdeyePriceSource(
                transport=self._transport,
                endpoint_secret=self._endpoint_secret,
                timeout_seconds=self._timeout,
            )
            snap = price_source.fetch_snapshot(base_mint=mint)  # never raises
            price_value = getattr(snap, "price_value", None)
        except Exception:
            price_value = None

        reserve_telemetry: Dict[str, Any] = {}
        if self._reserve_index is not None:
            artifact = self._reserve_index.latest(mint)
            if artifact is not None:
                quote_price: Optional[str] = "1" if artifact.quote_mint == USDC_MINT else None
                if quote_price is None and artifact.quote_mint:
                    try:
                        quote_source = price_source or Stage29_2BirdeyePriceSource(
                            transport=self._transport,
                            endpoint_secret=self._endpoint_secret,
                            timeout_seconds=self._timeout,
                        )
                        quote_snapshot = quote_source.fetch_snapshot(
                            base_mint=artifact.quote_mint)
                        quote_price = getattr(quote_snapshot, "price_value", None)
                    except Exception:
                        quote_price = None
                reserve_telemetry = self._reserve_index.compare_market(
                    mint,
                    birdeye_price_usd=price_value,
                    quote_price_usd=quote_price,
                )

        mc_value: Optional[str] = None
        lp_value: Optional[str] = None
        try:
            source = Stage30_4_3BirdeyeMarketContextSource(
                transport=self._transport,
                endpoint_secret=self._endpoint_secret,
                timeout_seconds=self._timeout,
            )
            record = project_market_context(
                session_id=None, run_id=None, candidate_id=None,
                token_mint=mint, created_at_utc=attempt_at_utc, source=source,
            )
            mc_value = getattr(record, "market_cap_usd_value", None)
            lp_value = getattr(record, "liquidity_usd_value", None)
        except Exception:
            mc_value = None
            lp_value = None

        diagnostic: Dict[str, Any] = {}
        diagnostic_fn = getattr(self._transport, "market_diagnostic", None)
        if callable(diagnostic_fn):
            try:
                diagnostic = dict(diagnostic_fn(mint) or {})
            except Exception:
                diagnostic = {}

        observe_current = getattr(self._ath_store, "observe_provider_current", None)
        if callable(observe_current) and price_value:
            try:
                observe_current(
                    mint=mint,
                    price_usd=price_value,
                    market_cap_usd=mc_value,
                    observed_at=(diagnostic.get("provider_timestamp_utc")
                                 or attempt_at_utc),
                    confirmed=False,
                )
            except Exception:
                pass
        central_ath = self.central_ath_snapshot(mint) or {}

        all_present = bool(price_value) and bool(mc_value) and bool(lp_value)
        if all_present:
            self._per_mint_consecutive_failures[mint] = 0
            self._counters["present"] += 1
            basis = "REAL_MARKET_PRESENT"
        else:
            self._per_mint_consecutive_failures[mint] = (
                self._per_mint_consecutive_failures.get(mint, 0) + 1
            )
            self._per_mint_failures[mint] = self._per_mint_failures.get(mint, 0) + 1
            self._counters["failures"] += 1
            basis = "REAL_MARKET_INCOMPLETE"
        return {
            "scheduled_offset_s": scheduled_offset_s,
            "attempt_at_utc": attempt_at_utc,
            "price_value": price_value,
            "mc_value": mc_value,
            "lp_value": lp_value,
            "all_present": all_present,
            "basis": basis,
            "provider_market_state": diagnostic.get("market_state"),
            "provider_reason_code": diagnostic.get("market_reason_code"),
            "provider_timestamp_utc": diagnostic.get("provider_timestamp_utc"),
            "endpoint_attempts": diagnostic.get("endpoints") or {},
            "pumpswap_reserve": reserve_telemetry,
            "central_ath": central_ath,
        }

    @staticmethod
    def _unknown_attempt(attempt_at_utc: str, scheduled_offset_s: int, basis: str) -> Dict[str, Any]:
        return {
            "scheduled_offset_s": scheduled_offset_s,
            "attempt_at_utc": attempt_at_utc,
            "price_value": None,
            "mc_value": None,
            "lp_value": None,
            "all_present": False,
            "basis": basis,
        }

    def resolve(
        self,
        mint: str,
        *,
        migration_time_utc: Optional[str],
        now_iso_fn: Callable[[], str],
        sleep_fn: Callable[[float], None],
    ) -> Dict[str, Any]:
        """Resolve market context with the escalating refresh. Returns the first all-present
        attempt's values, else the last attempt's (honest partial/None). Blocking-but-bounded
        by ``max_delayed_refresh_seconds``."""
        if self._readiness_tracker is not None:
            return self._readiness_tracker.resolve(
                mint,
                migration_time_utc=migration_time_utc,
                now_iso_fn=now_iso_fn,
                fetch_attempt_fn=lambda attempt_at_utc: self._fetch_one(
                    mint, attempt_at_utc, 0
                ),
            )
        attempts: List[Dict[str, Any]] = []
        # Immediate attempt (offset 0).
        attempts.append(self._fetch_one(mint, now_iso_fn(), 0))
        idx = 1
        while (
            not attempts[-1]["all_present"]
            and attempts[-1]["basis"] not in ("REAL_MARKET_CAP", "REAL_MARKET_DISABLED")
            and idx < len(REFRESH_OFFSETS_SECONDS)
            and len(attempts) < self._caps.max_calls_per_token
            and REFRESH_OFFSETS_SECONDS[idx] <= self._caps.max_delayed_refresh_seconds
        ):
            offset = REFRESH_OFFSETS_SECONDS[idx]
            # Wait until migration + offset is due (bounded).
            self._sleep_until_due(migration_time_utc, offset, now_iso_fn, sleep_fn)
            attempts.append(self._fetch_one(mint, now_iso_fn(), offset))
            idx += 1

        selected = next((a for a in attempts if a["all_present"]), attempts[-1])
        return {
            "current_price": selected["price_value"],
            "current_market_cap_usd": selected["mc_value"],
            "liquidity_usd": selected["lp_value"],
            "market_context_fetched_at_utc": selected["attempt_at_utc"],
            "all_present": selected["all_present"],
            "basis": selected["basis"],
            "attempts": attempts,
            "market_state": (selected.get("provider_market_state")
                             or ("MARKET_READY" if selected["all_present"]
                                 else "MARKET_INCOMPLETE")),
            "market_reason_code": (selected.get("provider_reason_code")
                                   or ("REQUIRED_FIELDS_FRESH" if selected["all_present"]
                                       else "REQUIRED_FIELDS_MISSING")),
            "provider_timestamp_utc": selected.get("provider_timestamp_utc"),
            "endpoint_attempts": selected.get("endpoint_attempts") or {},
            "pumpswap_reserve": selected.get("pumpswap_reserve") or {},
            # Market values deliberately come from the selected ready attempt;
            # ATH does not.  It is a monotonic shared state and must be read at
            # return time so an older ready attempt cannot pin an older maximum.
            "central_ath": self.central_ath_snapshot(mint),
        }

    def priority_refresh(
        self,
        mint: str,
        *,
        migration_time_utc: Optional[str],
        now_iso_fn: Callable[[], str],
    ) -> Dict[str, Any]:
        """ONE bounded send-time provider attempt for an otherwise-ready candidate.

        The normal ``resolve`` path honours the readiness tracker's backoff and
        returns ``MARKET_RECOVERY_BACKOFF_NOT_DUE`` with zero fetches, which is
        correct for maintenance polling but silently costs an alert when a
        candidate is otherwise fully dispatchable.  This performs exactly one
        direct attempt, hands the result to the readiness tracker (still the
        sole owner of every readiness/recovery transition, so a success
        recovers the candidate and a failure advances the existing bounded
        backoff), and returns a context in the same shape as ``resolve``.

        The per-mint call caps in ``_fetch_one`` bound this by construction: a
        priority refresh consumes one of the candidate's budgeted attempts and
        returns an honest incomplete context once the budget is spent.
        """

        now_iso = now_iso_fn()
        attempt = self._fetch_one(mint, now_iso, 0)
        if self._readiness_tracker is not None:
            try:
                projection = self._readiness_tracker.observe_scheduled_attempt(
                    mint,
                    migration_time_utc=migration_time_utc,
                    now_iso=now_iso,
                    attempt=attempt,
                )
            except Exception:
                projection = None
            if isinstance(projection, dict):
                return projection
        return {
            "current_price": attempt["price_value"],
            "current_market_cap_usd": attempt["mc_value"],
            "liquidity_usd": attempt["lp_value"],
            "market_context_fetched_at_utc": attempt["attempt_at_utc"],
            "all_present": attempt["all_present"],
            "basis": attempt["basis"],
            "attempts": [attempt],
            "market_state": (attempt.get("provider_market_state")
                             or ("MARKET_READY" if attempt["all_present"]
                                 else "MARKET_INCOMPLETE")),
            "market_reason_code": (attempt.get("provider_reason_code")
                                   or ("REQUIRED_FIELDS_FRESH"
                                       if attempt["all_present"]
                                       else "REQUIRED_FIELDS_MISSING")),
            "provider_timestamp_utc": attempt.get("provider_timestamp_utc"),
            "endpoint_attempts": attempt.get("endpoint_attempts") or {},
            "pumpswap_reserve": attempt.get("pumpswap_reserve") or {},
            "central_ath": self.central_ath_snapshot(mint),
        }

    def _sleep_until_due(
        self,
        migration_time_utc: Optional[str],
        offset: int,
        now_iso_fn: Callable[[], str],
        sleep_fn: Callable[[float], None],
    ) -> None:
        # Bounded wait until now >= migration + offset (cap at max_delayed_refresh_seconds of waiting).
        waited = 0
        while waited < self._caps.max_delayed_refresh_seconds:
            try:
                due = _parse_iso(migration_time_utc) + timedelta(seconds=offset)
                now = _parse_iso(now_iso_fn())
            except Exception:
                return
            if now >= due:
                return
            sleep_fn(1.0)
            waited += 1

    def stats(self) -> Dict[str, Any]:
        return {
            "market_enabled": self._enabled,
            "market_attempts_total": self._counters["attempts"],
            "market_present_total": self._counters["present"],
            "market_failures_total": self._counters["failures"],
            "market_capped_total": self._counters["capped"],
        }


__all__ = ("REFRESH_OFFSETS_SECONDS", "Cap1MarketCaps", "Cap1MarketSidecar")
