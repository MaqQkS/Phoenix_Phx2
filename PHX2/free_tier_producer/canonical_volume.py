"""Observe-only canonical rolling volume from authenticated decoded swaps.

The accumulator consumes the already-owned PumpSwap trusted-routing stream.  It
opens no provider connection, makes no eligibility decision, and has no durable
side effect.  Each event is deduped by transaction signature + decoded event
index and valued from the event's actual quote amount with the accepted
timestamped quote/USD observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from PHX2.free_tier_producer.migration_admission import is_supported_mint_identity


VOLUME_SCHEMA_VERSION = "phx2_canonical_swap_volume_v1"
VOLUME_WINDOW_SECONDS = 300
VOLUME_VALID = "VALID"
VOLUME_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
VOLUME_QUOTE_PRICE_MAX_SKEW_SECONDS = 30
#: An event whose on-chain timestamp runs further than this ahead of the wall
#: clock is invalid evidence: ``snapshot`` would exclude it anyway, and before
#: this guard existed its skewed epoch advanced the shared purge cutoff and
#: could evict legitimate in-window events for EVERY mint.
VOLUME_EVENT_MAX_FUTURE_SKEW_SECONDS = 2.0


def _epoch(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).timestamp()


def _decimal(value: object) -> Optional[Decimal]:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


@dataclass(frozen=True)
class CanonicalSwap:
    mint: str
    pool_address: str
    transaction_signature: str
    event_index: int
    side: str
    event_epoch: float
    quote_amount_usd: Decimal

    @property
    def key(self) -> Tuple[str, int]:
        return self.transaction_signature, self.event_index


class CanonicalSwapVolumeTracker:
    """Thread-safe exact 5-minute gross and signed/net quote-flow tracker."""

    def __init__(
        self,
        *,
        now_fn: Callable[[], float] = time.time,
        window_seconds: int = VOLUME_WINDOW_SECONDS,
        quote_price_max_skew_seconds: int = (
            VOLUME_QUOTE_PRICE_MAX_SKEW_SECONDS),
    ) -> None:
        self._now = now_fn
        self._window = max(1, int(window_seconds))
        self._quote_skew = max(0, int(quote_price_max_skew_seconds))
        self._lock = threading.Lock()
        self._events: Dict[Tuple[str, int], CanonicalSwap] = {}
        self._accepted_total = 0
        self._duplicate_total = 0
        self._rejected_total = 0

    def observe(self, payload: Mapping[str, Any]) -> bool:
        """Accept one trusted swap payload; malformed/non-swap input is ignored."""

        if not isinstance(payload, Mapping):
            return self._reject()
        mint = payload.get("mint")
        pool = payload.get("pool_address")
        signature = payload.get("transaction_signature")
        event_index = payload.get("event_index")
        side = payload.get("event_side")
        quote_raw_value = payload.get("quote_amount_raw")
        quote_decimals = payload.get("quote_decimals")
        quote_price = _decimal(payload.get("quote_price_usd"))
        event_epoch = _epoch(payload.get("source_timestamp"))
        quote_epoch = _epoch(payload.get("quote_price_observed_at_utc"))
        if not (
            is_supported_mint_identity(mint)
            and isinstance(pool, str) and pool
            and isinstance(signature, str) and signature
            and isinstance(event_index, int) and not isinstance(event_index, bool)
            and event_index >= 0
            and side in ("BUY", "SELL")
            and payload.get("transaction_succeeded") is True
            and payload.get("source_event_proven") is True
            and payload.get("reserve_trusted_for_routing") is True
            and isinstance(quote_decimals, int)
            and not isinstance(quote_decimals, bool)
            and 0 <= quote_decimals <= 255
            and event_epoch is not None
            and quote_epoch is not None
            and abs(event_epoch - quote_epoch) <= self._quote_skew
            and quote_price is not None and quote_price > 0
        ):
            return self._reject()
        try:
            quote_raw = int(str(quote_raw_value))
        except (TypeError, ValueError):
            return self._reject()
        if quote_raw <= 0:
            return self._reject()
        expected_basis = (
            "QUOTE_AMOUNT_IN" if side == "BUY" else "QUOTE_AMOUNT_OUT")
        if payload.get("quote_amount_basis") != expected_basis:
            return self._reject()
        if event_epoch > float(self._now()) + VOLUME_EVENT_MAX_FUTURE_SKEW_SECONDS:
            return self._reject()
        quote_units = Decimal(quote_raw) / (Decimal(10) ** quote_decimals)
        event = CanonicalSwap(
            mint=mint,
            pool_address=pool,
            transaction_signature=signature,
            event_index=event_index,
            side=side,
            event_epoch=event_epoch,
            quote_amount_usd=quote_units * quote_price,
        )
        with self._lock:
            # The future-skew guard above bounds event_epoch, so a bogus
            # on-chain timestamp can no longer drag the shared cutoff forward.
            self._purge_locked(max(float(self._now()), event_epoch))
            if event.key in self._events:
                self._duplicate_total += 1
                return False
            self._events[event.key] = event
            self._accepted_total += 1
        return True

    def _reject(self) -> bool:
        with self._lock:
            self._rejected_total += 1
        return False

    def _purge_locked(self, now_epoch: float) -> None:
        cutoff = now_epoch - self._window
        stale = [
            key for key, event in self._events.items()
            if event.event_epoch < cutoff]
        for key in stale:
            self._events.pop(key, None)

    def snapshot(
        self, mint: object, *, now_epoch: Optional[float] = None
    ) -> Dict[str, Any]:
        now = float(self._now() if now_epoch is None else now_epoch)
        if not isinstance(mint, str) or not mint:
            return self._empty(mint)
        with self._lock:
            self._purge_locked(now)
            events = sorted(
                (
                    event for event in self._events.values()
                    if event.mint == mint
                    and now - self._window <= event.event_epoch <= now + 2.0
                ),
                key=lambda event: (
                    event.event_epoch,
                    event.transaction_signature,
                    event.event_index,
                ),
            )
        if not events:
            return self._empty(mint)
        gross = sum(
            (event.quote_amount_usd for event in events), Decimal(0))
        net = sum(
            (
                event.quote_amount_usd
                if event.side == "BUY" else -event.quote_amount_usd
                for event in events
            ),
            Decimal(0),
        )
        buys = sum(1 for event in events if event.side == "BUY")
        sells = len(events) - buys
        earliest = events[0].event_epoch
        return {
            "schema_version": VOLUME_SCHEMA_VERSION,
            "status": VOLUME_VALID,
            "mint": mint,
            "window_seconds": self._window,
            "gross_volume_usd": format(gross, "f"),
            "net_quote_flow_usd": format(net, "f"),
            "sample_count": len(events),
            "buy_count": buys,
            "sell_count": sells,
            "coverage_seconds": format(
                Decimal(str(min(self._window, max(0.0, now - earliest)))),
                "f",
            ),
            "signed_flow_convention": "BUY_POSITIVE_SELL_NEGATIVE",
            "quote_amount_basis": "ACTUAL_DECODED_SWAP_QUOTE_AMOUNT",
            "observe_only": True,
        }

    def _empty(self, mint: object) -> Dict[str, Any]:
        return {
            "schema_version": VOLUME_SCHEMA_VERSION,
            "status": VOLUME_INSUFFICIENT_DATA,
            "mint": mint if isinstance(mint, str) else None,
            "window_seconds": self._window,
            "gross_volume_usd": None,
            "net_quote_flow_usd": None,
            "sample_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "coverage_seconds": "0",
            "signed_flow_convention": "BUY_POSITIVE_SELL_NEGATIVE",
            "quote_amount_basis": "ACTUAL_DECODED_SWAP_QUOTE_AMOUNT",
            "observe_only": True,
        }

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "canonical_volume_events_active": len(self._events),
                "canonical_volume_events_accepted_total": self._accepted_total,
                "canonical_volume_events_duplicate_total": self._duplicate_total,
                "canonical_volume_events_rejected_total": self._rejected_total,
            }


__all__ = (
    "VOLUME_SCHEMA_VERSION",
    "VOLUME_WINDOW_SECONDS",
    "VOLUME_VALID",
    "VOLUME_INSUFFICIENT_DATA",
    "VOLUME_QUOTE_PRICE_MAX_SKEW_SECONDS",
    "VOLUME_EVENT_MAX_FUTURE_SKEW_SECONDS",
    "CanonicalSwap",
    "CanonicalSwapVolumeTracker",
)
