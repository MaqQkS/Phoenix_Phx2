"""free_tier_pricing_tail.py — bounded market-refresh tail for the paper engine.

OUT-OF-REPO operator glue. The committed paper engine opens positions from candidate recheck
records and then needs CONTINUED pricing, or the position degrades to DATA_LOST (committed
default: 1800s without a fresh sample -> haircut close). Producer rechecks alone cannot provide
that continuity: SEND_ATTEMPTED is terminal in the committed watchlist, entries EXPIRE on age,
and a run stop ends rechecks entirely.

2026-07-10 fix: the tail now tracks EVERY guard-accepted watchlist mint (origin WATCHLIST) from
the moment it is seeded — not only would-pinged mints (origin WOULD_PING) — so the paper engine
keeps receiving `pricing_tail.jsonl` samples for the whole tail window. Each tracked mint is
fetched at most once per ``min_poll_interval_seconds`` (default 60s), so the added market spend is
bounded and predictable: ceil(runtime/interval) × tracked mints, on top of the transport's own
pacing + TTL cache + total-call cap.

The tail also OWNS the run's market-freshness telemetry (surfaced via ``summary()`` into the
producer heartbeat + dashboard): per-mint last successful refresh, fresh/stale/unavailable
counts, last-successful-refresh timestamp, and a closed-set last-error token.

Purely additive observation: it never touches the watchlist, the dedupe ledger, the compose path,
or any transport internals. Bounded: max tracked mints + max tail age + per-mint poll interval +
one cached lookup per mint per poll. No URL / key / host / secret in any record.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from PHX2.paper_trading.models import parse_utc, parse_number

PRICING_TAIL_BASENAME = "pricing_tail.jsonl"

TAIL_ORIGIN_WOULD_PING = "WOULD_PING"
TAIL_ORIGIN_WATCHLIST = "WATCHLIST"

# Closed-set last-error tokens (artifact-safe).
TAIL_ERROR_FETCH_MISS = "FETCH_MISS"

# A mint whose last successful refresh is older than this counts as STALE in the freshness block
# (mirrors the committed composer's 300s market-freshness ceiling).
DEFAULT_FRESH_WITHIN_SECONDS = 300.0


class FreeTierPricingTail:
    """Tracks watchlist + would-pinged mints and appends bounded price-tail records."""

    def __init__(
        self,
        *,
        out_dir: Any,
        fetch_market_fn: Callable[[str], Optional[Dict[str, Any]]],
        now_epoch_fn: Callable[[], float],
        max_tracked: int = 32,
        max_tail_age_seconds: float = 21600.0,
        min_poll_interval_seconds: float = 60.0,
        fresh_within_seconds: float = DEFAULT_FRESH_WITHIN_SECONDS,
        ath_store: Any = None,
        context_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        paper_state_file: Any = None,
        paper_feedback_max_age_seconds: float = 120.0,
        unavailable_retention_seconds: float = 300.0,
    ) -> None:
        self._path = Path(out_dir) / PRICING_TAIL_BASENAME
        self._fetch = fetch_market_fn
        self._now_epoch = now_epoch_fn
        self._max_tracked = int(max_tracked)
        self._max_age = float(max_tail_age_seconds)
        self._min_poll_interval = float(min_poll_interval_seconds)
        self._fresh_within = float(fresh_within_seconds)
        self._ath_store = ath_store
        self._context_fn = context_fn
        self._paper_state_file = Path(paper_state_file) if paper_state_file else None
        self._feedback_max_age = float(paper_feedback_max_age_seconds)
        self._unavailable_retention = float(unavailable_retention_seconds)
        if (self._max_tracked <= 0 or not math.isfinite(self._min_poll_interval)
                or self._min_poll_interval < 0 or any(not math.isfinite(v) or v <= 0 for v in (
                self._max_age, self._fresh_within,
                self._feedback_max_age, self._unavailable_retention))):
            raise ValueError("PRICING_TAIL_BOUNDS_INVALID")
        self._pinned: Dict[str, Dict[str, Any]] = {}
        self._feedback_ready = False
        self._feedback_reason = "PAPER_FEEDBACK_NOT_CONFIGURED"
        self._admission_failures = 0
        self._expired_total = 0
        # mint -> {"tracked_at_epoch", "origin", "ath_market_cap_usd", "tier_at_ping",
        #          "records", "misses", "last_polled_epoch", "last_success_epoch",
        #          "last_success_iso"}
        self._tracked: Dict[str, Dict[str, Any]] = {}
        self._appended_total = 0
        self._success_total = 0
        self._miss_total = 0
        self._last_success_iso: Optional[str] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------ tracking

    def _status(self, mint: str, reason: str) -> None:
        self._last_error = reason
        path = self._path.parent / "pricing_tail_status.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": "PAPER_PRICING_COVERAGE", "token_mint": mint,
                "reason": reason, "observed_at_utc": utc_epoch_to_iso(self._now_epoch())}) + "\n")

    def _prune(self) -> None:
        now = float(self._now_epoch())
        for mint, state in list(self._tracked.items()):
            if mint in self._pinned or now < state.get("lease_until_epoch", 0):
                continue
            expired = now - state["tracked_at_epoch"] >= self._max_age
            unavailable = (state["last_success_epoch"] is None and
                           now - state["tracked_at_epoch"] >= self._unavailable_retention)
            if expired or unavailable:
                del self._tracked[mint]
                self._expired_total += 1
                self._status(mint, "TAIL_EXPIRED" if expired else "UNAVAILABLE_SLOT_RECLAIMED")

    def sync_paper_positions(self) -> None:
        """Read only the atomic paper feedback. Lost feedback never releases pins."""
        if self._paper_state_file is None:
            return
        try:
            if self._paper_state_file.stat().st_size > 32 * 1024 * 1024:
                raise ValueError()
            payload = json.loads(self._paper_state_file.read_text(encoding="utf-8"))
            rows = payload["open_mints"]
            stamp = parse_utc(payload.get("heartbeat_utc"))
            now = float(self._now_epoch())
            if not isinstance(rows, list):
                raise ValueError()
            fresh = stamp is not None and 0 <= now - stamp <= self._feedback_max_age
            pins = {}
            for item in rows:
                if not isinstance(item, dict) or not isinstance(item.get("mint"), str) or not item["mint"]:
                    raise ValueError()
                pin = pins.setdefault(item["mint"], {"mint": item["mint"],
                    "candidate_id": item.get("candidate_id"), "paper_position_contexts": []})
                context = item.get("paper_position_context")
                if isinstance(context, dict) and context not in pin["paper_position_contexts"]:
                    pin["paper_position_contexts"].append(context)
            if len(pins) > self._max_tracked:
                self._feedback_ready = False
                self._feedback_reason = "PAPER_OPEN_MINTS_EXCEED_CAPACITY"
                self._status("", self._feedback_reason)
                return
            if not fresh:
                pins = {**self._pinned, **pins}
            if len(pins) > self._max_tracked:
                raise ValueError()
            self._pinned = pins
            self._prune()
            # Paper positions take priority over unused admission slots.
            for mint in pins:
                if mint not in self._tracked and len(self._tracked) >= self._max_tracked:
                    victims = [key for key, value in self._tracked.items()
                               if key not in pins and now >= value.get("lease_until_epoch", 0)]
                    if victims:
                        victim = min(victims, key=lambda key: self._tracked[key]["tracked_at_epoch"])
                        del self._tracked[victim]
                        self._status(victim, "SLOT_RESERVED_FOR_OPEN_PAPER_POSITION")
                if not self.track(mint, origin="PAPER_POSITION"):
                    self._feedback_ready = False
                    self._feedback_reason = "OPEN_PAPER_COVERAGE_UNAVAILABLE"
                    return
            self._feedback_ready = fresh
            self._feedback_reason = ("PAPER_FEEDBACK_READY" if fresh
                                     else "PAPER_FEEDBACK_STALE_OR_UNAVAILABLE")
        except (OSError, ValueError, KeyError, TypeError):
            self._feedback_ready = False
            self._feedback_reason = "PAPER_FEEDBACK_STALE_OR_UNAVAILABLE"

    def tracked_mints(self) -> tuple[str, ...]:
        return tuple(self._tracked)

    def paper_positions(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._pinned)

    def coverage(self, mint: str) -> Dict[str, Any]:
        state = self._tracked.get(mint)
        now = float(self._now_epoch())
        if state is not None and self._feedback_ready:
            # Reserve the slot long enough for a fresh paper snapshot to be
            # consumed and its resulting position to appear in atomic feedback.
            lifetime = (self._max_age if state["last_success_epoch"] is not None
                        else min(self._max_age, self._unavailable_retention))
            limit = now + 600 if mint in self._pinned else state["tracked_at_epoch"] + lifetime
            state["lease_until_epoch"] = max(state.get("lease_until_epoch", 0), min(now + 600, limit))
        return {"admitted": state is not None, "paper_feedback_ready": self._feedback_ready,
                "reason": self._feedback_reason if state else "TAIL_CAPACITY_UNAVAILABLE",
                "lease_until_utc": (utc_epoch_to_iso(state.get("lease_until_epoch", now))
                                    if state else None)}

    def track(self, mint: str, *, ath_market_cap_display: Optional[str] = None,
              tier_at_ping: Optional[str] = None,
              origin: str = TAIL_ORIGIN_WOULD_PING) -> bool:
        """Start tailing ``mint`` (idempotent). False when the tracked set is full.
        A WATCHLIST-tracked mint that later would-pings is upgraded in place (origin +
        ATH/tier context) without losing its refresh history."""
        if not isinstance(mint, str) or not mint:
            return False
        self._prune()
        existing = self._tracked.get(mint)
        if existing is not None:
            if origin == TAIL_ORIGIN_WOULD_PING:
                existing["origin"] = TAIL_ORIGIN_WOULD_PING
                if self._ath_store is None and isinstance(ath_market_cap_display, str):
                    existing["ath_market_cap_usd"] = ath_market_cap_display
                if isinstance(tier_at_ping, str):
                    existing["tier_at_ping"] = tier_at_ping
            return True
        if len(self._tracked) >= self._max_tracked:
            self._admission_failures += 1
            self._status(mint, "TAIL_CAPACITY_UNAVAILABLE")
            return False
        self._tracked[mint] = {
            "tracked_at_epoch": float(self._now_epoch()),
            "origin": (origin if origin in (TAIL_ORIGIN_WOULD_PING, TAIL_ORIGIN_WATCHLIST, "PAPER_POSITION")
                       else TAIL_ORIGIN_WOULD_PING),
            "ath_market_cap_usd": (
                ath_market_cap_display
                if self._ath_store is None and isinstance(ath_market_cap_display, str)
                else None),
            "tier_at_ping": tier_at_ping if isinstance(tier_at_ping, str) else None,
            "records": 0,
            "misses": 0,
            "last_polled_epoch": None,
            "last_success_epoch": None,
            "last_success_iso": None,
            # Declared up front so a tracked-but-not-yet-polled mint reports an
            # explicit "nothing resolved yet" telemetry shape instead of a set of
            # absent keys that read identically to a resolved null.
            "ath_price_usd": None,
            "ath_observed_at_utc": None,
            "ath_observation_type": None,
            "ath_provider": None,
            "ath_status": None,
            "ath_confirmed": None,
            "ath_hydration_status": None,
            "ath_post_migration_complete": None,
            "ath_supply_basis": None,
        }
        return True

    # ------------------------------------------------------------------ per-tick poll

    def poll(self, now_iso: str) -> int:
        """One bounded pass: expire stale mints, fetch each DUE mint once (per-mint
        ``min_poll_interval_seconds`` gate), append records. Returns the number of records
        appended this pass. Never raises."""
        appended = 0
        now = float(self._now_epoch())
        self.sync_paper_positions()
        self._prune()
        for mint in list(self._tracked.keys()):
            state = self._tracked[mint]
            last_polled = state.get("last_polled_epoch")
            if last_polled is not None and (now - last_polled) < self._min_poll_interval:
                continue
            state["last_polled_epoch"] = now
            try:
                market = self._fetch(mint)
            except Exception:
                market = None
            now = float(self._now_epoch())
            market = market if isinstance(market, dict) else {}
            price = parse_number(market.get("current_price"))
            quote_epoch = parse_utc(market.get("price_observed_at_utc")
                                    or market.get("provider_timestamp_utc")
                                    or market.get("fetched_at_utc"))
            quote_ok = bool(price is not None and price > 0 and quote_epoch is not None
                            and 0 <= now - quote_epoch <= self._fresh_within
                            and market.get("price_fresh") is not False
                            and (market.get("market_state") == "MARKET_READY"
                                 or market.get("price_fresh") is True))
            if not quote_ok:
                state["misses"] += 1
                self._miss_total += 1
                self._last_error = TAIL_ERROR_FETCH_MISS
            record = {
                "kind": "FREE_TIER_PRICING_TAIL",
                "token_mint": mint,
                "observed_at_utc": now_iso,
                "current_price": market.get("current_price"),
                "current_market_cap_usd": market.get("current_market_cap_usd"),
                "liquidity_usd": market.get("liquidity_usd"),
                "market_context_fetched_at_utc": market.get("fetched_at_utc"),
                "tail_source": "FREE_TIER_MARKET",
                "tail_origin": state.get("origin"),
                "pricing_coverage": self.coverage(mint),
                "quote_status": "FRESH" if quote_ok else "STALE_OR_UNAVAILABLE",
            }
            if self._context_fn is not None:
                record.update(self._context_fn(mint))
            central_ath: Dict[str, Any] = {}
            snapshot_fn = getattr(self._ath_store, "snapshot", None)
            if callable(snapshot_fn):
                try:
                    central_ath = dict(snapshot_fn(mint) or {})
                except Exception:
                    central_ath = {}
            if central_ath:
                record["central_ath"] = central_ath
                record["ath_price_usd"] = central_ath.get("ath_price")
                record["ath_market_cap_usd"] = central_ath.get("ath_market_cap")
                record["ath_observed_at_utc"] = central_ath.get("ath_timestamp")
                record["ath_provider"] = central_ath.get("ath_provider")
                record["ath_observation_type"] = central_ath.get(
                    "ath_observation_type")
            for key in (
                "market_provider", "price_observation_type", "price_observed_at_utc",
                "ath_price_usd", "ath_observed_at_utc", "ath_provider",
                "ath_observation_type", "ath_sample_count", "ath_provisional_ready",
                "ath_discord_eligible", "market_state", "market_reason_code",
                "provider_timestamp_utc", "endpoint_attempts",
                "pumpswap_reserve", "price_fresh", "market_price_ttl_seconds",
                "market_cap_observed_at_utc", "liquidity_observed_at_utc",
                "market_cap_fresh", "liquidity_fresh", "market_overview_ttl_seconds",
            ):
                if market.get(key) is not None:
                    record[key] = market.get(key)
            if state["ath_market_cap_usd"] and not central_ath:
                record["ath_market_cap_usd"] = state["ath_market_cap_usd"]
            if state["tier_at_ping"]:
                record["tier_at_ping"] = state["tier_at_ping"]
            # Stamp after assembling quote, risk, security and ATH evidence.
            # A slow fetch must not make its own context appear from the future.
            record["observed_at_utc"] = utc_epoch_to_iso(self._now_epoch())
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, sort_keys=True) + "\n")
            except Exception:
                continue
            state["records"] += 1
            if quote_ok:
                state["last_success_epoch"] = quote_epoch
                state["last_success_iso"] = utc_epoch_to_iso(quote_epoch)
            state["market_provider"] = market.get("market_provider")
            # The persisted record and the in-memory telemetry state MUST expose
            # the SAME resolved ATH snapshot.  Reading these back from ``market``
            # reported a null ATH for every mint whenever the raw payload omitted
            # them -- which it always does, because ATH lives in the central
            # store, not in a market quote.  The 2026-07-31 canary therefore
            # showed ath_price_usd=null on all 17 watch rows while the real
            # eligibility path held valid central ATH and had already committed
            # five tiers; the null was read as a pipeline failure it never was.
            # ``record`` is the merged, authoritative view (central_ath first,
            # then any non-None market override applied above).
            state["ath_price_usd"] = record.get("ath_price_usd")
            state["ath_market_cap_usd"] = record.get("ath_market_cap_usd")
            state["ath_observed_at_utc"] = record.get("ath_observed_at_utc")
            state["ath_observation_type"] = record.get("ath_observation_type")
            state["ath_provider"] = record.get("ath_provider")
            # Provisional/confirmed, coverage and supply basis come only from the
            # central store; a market quote can never establish them.
            state["ath_status"] = central_ath.get("ath_status")
            state["ath_confirmed"] = central_ath.get("ath_confirmed")
            state["ath_hydration_status"] = central_ath.get("ath_hydration_status")
            state["ath_post_migration_complete"] = central_ath.get(
                "ath_post_migration_complete")
            state["ath_supply_basis"] = central_ath.get("ath_supply_basis")
            state["market_state"] = market.get("market_state")
            state["market_reason_code"] = market.get("market_reason_code")
            self._appended_total += 1
            if quote_ok:
                self._success_total += 1
                self._last_success_iso = utc_epoch_to_iso(quote_epoch)
            appended += 1
        return appended

    # ------------------------------------------------------------------ stats

    def market_freshness(self) -> Dict[str, Any]:
        """Redaction-safe market-freshness block for heartbeat/summary + dashboard: counts,
        last successful refresh, closed-set last error, bounded per-mint detail."""
        now = float(self._now_epoch())
        fresh = stale = unavailable = 0
        per_mint: List[Dict[str, Any]] = []
        for mint, state in self._tracked.items():
            success = state.get("last_success_epoch")
            if success is None:
                status = "UNAVAILABLE"
                unavailable += 1
                age_s: Optional[float] = None
            else:
                age_s = round(max(0.0, now - float(success)), 1)
                if age_s <= self._fresh_within:
                    status = "FRESH"
                    fresh += 1
                else:
                    status = "STALE"
                    stale += 1
            per_mint.append({
                "token_mint": mint,
                "origin": state.get("origin"),
                "status": status,
                "last_success_age_s": age_s,
                "records": state.get("records"),
                "misses": state.get("misses"),
                "market_provider": state.get("market_provider"),
                "ath_price_usd": state.get("ath_price_usd"),
                "ath_market_cap_usd": state.get("ath_market_cap_usd"),
                "ath_observed_at_utc": state.get("ath_observed_at_utc"),
                "ath_observation_type": state.get("ath_observation_type"),
                "ath_provider": state.get("ath_provider"),
                "ath_status": state.get("ath_status"),
                "ath_confirmed": state.get("ath_confirmed"),
                "ath_hydration_status": state.get("ath_hydration_status"),
                "ath_post_migration_complete": state.get(
                    "ath_post_migration_complete"),
                "ath_supply_basis": state.get("ath_supply_basis"),
                "market_state": state.get("market_state"),
                "market_reason_code": state.get("market_reason_code"),
            })
        return {
            "market_data_fresh_count": fresh,
            "market_data_stale_count": stale,
            "market_unavailable_count": unavailable,
            "last_successful_market_refresh_at": self._last_success_iso,
            "last_market_error": self._last_error,
            "refresh_success_total": self._success_total,
            "refresh_miss_total": self._miss_total,
            "fresh_within_seconds": self._fresh_within,
            "per_mint": per_mint[:32],
        }

    def summary(self) -> Dict[str, Any]:
        by_origin: Dict[str, int] = {}
        for state in self._tracked.values():
            key = str(state.get("origin"))
            by_origin[key] = by_origin.get(key, 0) + 1
        return {
            "tracked": len(self._tracked),
            "tracked_by_origin": by_origin,
            "max_tracked": self._max_tracked,
            "max_tail_age_seconds": self._max_age,
            "min_poll_interval_seconds": self._min_poll_interval,
            "appended_total": self._appended_total,
            "refresh_success_total": self._success_total,
            "refresh_miss_total": self._miss_total,
            "last_successful_market_refresh_at": self._last_success_iso,
            "last_market_error": self._last_error,
            "admission_failures": self._admission_failures,
            "expired_total": self._expired_total,
            "open_paper_pins": len(self._pinned),
            "paper_feedback_ready": self._feedback_ready,
            "paper_feedback_reason": self._feedback_reason,
        }


def utc_epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = (
    "PRICING_TAIL_BASENAME", "TAIL_ORIGIN_WOULD_PING", "TAIL_ORIGIN_WATCHLIST",
    "TAIL_ERROR_FETCH_MISS", "DEFAULT_FRESH_WITHIN_SECONDS", "FreeTierPricingTail",
    "utc_epoch_to_iso",
)
