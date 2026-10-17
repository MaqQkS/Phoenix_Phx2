"""free_tier_risk.py — LIGHTWEIGHT scam/bundle risk layer for the free-tier producer.

OUT-OF-REPO operator glue. Classifies every guard-accepted candidate mint as
RISK_LOW / RISK_MEDIUM / RISK_HIGH / RISK_UNKNOWN from signals the free tier ALREADY pays for:

  * LP level + LP trend over the samples the pricing tail / market sidecar already fetch
    (LP critically low, thin, falling, collapsed),
  * market data quality (missing LP on priced samples, stale refresh, consecutive refresh
    misses, repeated MARKET_UNAVAILABLE rechecks, persistent unavailability),
  * launch weirdness (creation-pool signature-page count observed by polling discovery —
    a bundled launch blasts hundreds of buys into the first minutes),
  * early price behavior (spike-then-dump, extreme drawdown / violent wick inside the first
    minutes after first observation).

HONESTY CONTRACT: holder / top-wallet / bundle-wallet distribution data is NOT available on
the free tier without an expensive account scan, so those signals are ALWAYS reported as
UNKNOWN signals — they never push a label to HIGH, and NO holder scan exists in this module
(``HOLDER_SCAN_ENABLED`` is a module constant ``False``; there is nothing to turn on). This is
a cheap risk tagger, not a rug detector: RISK_LOW means "no cheap red flag observed", never
"safe".

Spend contract: the engine only CONSUMES observations the producer already made (tail fetches,
sidecar market context, polling stats). It performs NO HTTP/RPC/WS call of its own, adds zero
Helius credits, and is bounded in memory (max tracked mints, max samples per mint).

Also provides ``FreeTierRiskLineTransport`` — a private-transport wrapper (same one-shot
``bind_body`` contract as the proven production Axiom fee appender) that appends a single
"Risk: <LABEL> — <reasons>" display line to the outgoing ping body. WARN-ONLY: it never blocks,
never originates, and never re-routes a send; the committed compose/dedupe/guard gate chain is
unchanged. Closed-set tokens and counts only; no URL, key, host, or secret anywhere.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# Closed-set labels + reason tokens (the producer -> paper -> dashboard contract)
# ---------------------------------------------------------------------------

RISK_LOW = "RISK_LOW"
RISK_MEDIUM = "RISK_MEDIUM"
RISK_HIGH = "RISK_HIGH"
RISK_UNKNOWN = "RISK_UNKNOWN"
RISK_LABELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_UNKNOWN)

# HIGH reasons
REASON_LIQUIDITY_COLLAPSE = "LIQUIDITY_COLLAPSE"
REASON_LP_CRITICALLY_LOW = "LP_CRITICALLY_LOW"
REASON_PRICE_SPIKE_DUMP = "PRICE_SPIKE_DUMP"
REASON_EARLY_EXTREME_DRAWDOWN = "EARLY_EXTREME_DRAWDOWN"
REASON_MARKET_UNAVAILABLE_PERSISTENT = "MARKET_UNAVAILABLE_PERSISTENT"
REASON_POOL_TOO_HOT = "POOL_TOO_HOT"

# MEDIUM reasons
REASON_LP_THIN = "LP_THIN"
REASON_LP_FALLING = "LP_FALLING"
REASON_LP_MISSING = "LP_MISSING"
REASON_MARKET_STALE = "MARKET_STALE"
REASON_MARKET_REFRESH_FAILING = "MARKET_REFRESH_FAILING"
REASON_MARKET_INCOMPLETE_REPEATED = "MARKET_INCOMPLETE_REPEATED"
REASON_EARLY_VOLATILITY = "EARLY_VOLATILITY"
REASON_POOL_HOT_EARLY = "POOL_HOT_EARLY_ACTIVITY"

# UNKNOWN-label reason (only when there is nothing to classify from)
REASON_NO_MARKET_DATA = "NO_MARKET_DATA"

HIGH_REASONS = (
    REASON_LIQUIDITY_COLLAPSE, REASON_LP_CRITICALLY_LOW, REASON_PRICE_SPIKE_DUMP,
    REASON_EARLY_EXTREME_DRAWDOWN, REASON_MARKET_UNAVAILABLE_PERSISTENT, REASON_POOL_TOO_HOT,
)
MEDIUM_REASONS = (
    REASON_LP_THIN, REASON_LP_FALLING, REASON_LP_MISSING, REASON_MARKET_STALE,
    REASON_MARKET_REFRESH_FAILING, REASON_MARKET_INCOMPLETE_REPEATED, REASON_EARLY_VOLATILITY,
    REASON_POOL_HOT_EARLY,
)

# Signals the free tier CANNOT observe cheaply — always reported UNKNOWN, never scanned.
UNKNOWN_SIGNAL_HOLDER = "HOLDER_DATA_UNAVAILABLE_FREE_TIER"
UNKNOWN_SIGNAL_BUNDLE_WALLETS = "BUNDLE_WALLET_DATA_UNAVAILABLE_FREE_TIER"
UNKNOWN_SIGNALS_ALWAYS = (UNKNOWN_SIGNAL_HOLDER, UNKNOWN_SIGNAL_BUNDLE_WALLETS)

# There is no holder/top-wallet scan in this bundle AT ALL (not even off-by-default code):
# adding one later must be a deliberate, capped, reviewed change. Tests pin this constant.
HOLDER_SCAN_ENABLED = False

RISK_NOTE = ("cheap free-tier heuristic; holder/bundle-wallet data UNKNOWN by design; "
             "RISK_LOW means no cheap red flag observed, not safe")

# Short display phrases for the Discord line + dashboard (closed set; artifact-safe).
_REASON_DISPLAY = {
    REASON_LIQUIDITY_COLLAPSE: "liquidity collapse",
    REASON_LP_CRITICALLY_LOW: "LP critically low",
    REASON_PRICE_SPIKE_DUMP: "spike-dump",
    REASON_EARLY_EXTREME_DRAWDOWN: "early extreme drawdown",
    REASON_MARKET_UNAVAILABLE_PERSISTENT: "market unavailable",
    REASON_POOL_TOO_HOT: "too-hot pool",
    REASON_LP_THIN: "thin LP",
    REASON_LP_FALLING: "LP falling",
    REASON_LP_MISSING: "LP missing",
    REASON_MARKET_STALE: "market stale",
    REASON_MARKET_REFRESH_FAILING: "market refresh failing",
    REASON_MARKET_INCOMPLETE_REPEATED: "market data incomplete",
    REASON_EARLY_VOLATILITY: "early volatility",
    REASON_POOL_HOT_EARLY: "hot early activity",
    REASON_NO_MARKET_DATA: "insufficient free-tier data",
}

_LABEL_DISPLAY = {
    RISK_LOW: "LOW",
    RISK_MEDIUM: "MEDIUM",
    RISK_HIGH: "HIGH",
    RISK_UNKNOWN: "UNKNOWN",
}


def format_risk_line(label: str, reasons: List[str], max_reasons: int = 3) -> str:
    """One human display line: ``Risk: HIGH — liquidity collapse / market stale``.
    LOW carries no reason tail; UNKNOWN always explains the free-tier holder/bundle gap."""
    short = _LABEL_DISPLAY.get(label, "UNKNOWN")
    if label == RISK_LOW:
        return "Risk: LOW"
    if label == RISK_UNKNOWN:
        # UNKNOWN means the cheap free-tier signals could not classify AND holder/bundle
        # distribution is never observable here — say so explicitly (never auto-blocks).
        return "Risk: UNKNOWN — insufficient free-tier holder/bundle data"
    shown = [_REASON_DISPLAY.get(r, r.replace("_", " ").lower())
             for r in (reasons or [])[:max_reasons]]
    tail = " / ".join(shown)
    return f"Risk: {short} — {tail}" if tail else f"Risk: {short}"


# ---------------------------------------------------------------------------
# Thresholds (documented heuristics; every value is a plain-constant knob)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreeTierRiskThresholds:
    """Heuristic knobs. Deliberately coarse: the layer tags obvious wreckage, it does not
    pretend precision the free-tier data cannot support."""

    lp_critical_usd: float = 1000.0        # LP below this => HIGH (nobody can exit)
    lp_thin_usd: float = 6000.0            # LP below this => MEDIUM (thin)
    lp_collapse_drop: float = 0.60         # latest LP <= 40% of peak LP => HIGH
    lp_falling_drop: float = 0.30          # latest LP <= 70% of peak LP => MEDIUM
    lp_min_peak_usd: float = 3000.0        # trend rules need a real peak to compare against
    spike_multiple: float = 3.0            # peak >= 3x first observed price ...
    spike_dump_retention: float = 0.40     # ... and latest <= 40% of peak => HIGH spike-dump
    early_window_seconds: float = 900.0    # "early" = first 15 min after first observation
    early_extreme_retention: float = 0.30  # latest <= 30% of peak inside early window => HIGH
    early_volatility_drop: float = 0.50    # >=50% peak-to-trough inside early window => MEDIUM
    stale_after_seconds: float = 300.0     # mirrors the committed composer freshness ceiling
    refresh_fail_consecutive: int = 3      # consecutive misses (some data exists) => MEDIUM
    unavailable_consecutive: int = 5       # consecutive misses with ZERO successes => HIGH
    market_incomplete_rechecks: int = 3    # NO_SEND_MARKET_UNAVAILABLE rechecks => MEDIUM
    hot_sig_count_high: int = 450          # creation-page signatures at discovery => HIGH
    hot_sig_count_medium: int = 250        # creation-page signatures at discovery => MEDIUM
    min_samples_for_price_rules: int = 2
    max_samples_per_mint: int = 48
    max_tracked_mints: int = 512


def _f(value: Any) -> Optional[float]:
    """Tolerant finite-float parse of PHX2 decimal-text / numeric fields."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(str(value).strip().replace(",", "")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _iso_now(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _MintRiskState:
    __slots__ = ("first_epoch", "migration_epoch", "discovery_source", "sig_count",
                 "samples", "consecutive_misses", "miss_total", "success_total",
                 "last_success_epoch", "market_unavailable_rechecks", "last_assessment")

    def __init__(self, now_epoch: float, max_samples: int) -> None:
        self.first_epoch = float(now_epoch)
        self.migration_epoch: Optional[float] = None
        self.discovery_source: Optional[str] = None
        self.sig_count: Optional[int] = None
        self.samples: deque = deque(maxlen=max_samples)   # (epoch, price, lp, mc)
        self.consecutive_misses = 0
        self.miss_total = 0
        self.success_total = 0
        self.last_success_epoch: Optional[float] = None
        self.market_unavailable_rechecks = 0
        self.last_assessment: Optional[Dict[str, Any]] = None


class FreeTierRiskEngine:
    """Per-run, in-memory risk state over mints the producer already observes.

    Every public method is total (never raises): a broken observation degrades to "no new
    signal", never to a crashed producer tick. Bounded: max tracked mints (FIFO eviction) and
    max samples per mint."""

    def __init__(self, *, now_epoch_fn: Callable[[], float] = time.time,
                 thresholds: Optional[FreeTierRiskThresholds] = None) -> None:
        self._now = now_epoch_fn
        self.thresholds = thresholds or FreeTierRiskThresholds()
        self._mints: Dict[str, _MintRiskState] = {}
        self._evicted_total = 0

    # ------------------------------------------------------------------ state plumbing

    def _state(self, mint: str) -> Optional[_MintRiskState]:
        if not isinstance(mint, str) or not mint:
            return None
        state = self._mints.get(mint)
        if state is None:
            while len(self._mints) >= self.thresholds.max_tracked_mints:
                oldest = next(iter(self._mints))
                self._mints.pop(oldest, None)
                self._evicted_total += 1
            state = _MintRiskState(self._now(), self.thresholds.max_samples_per_mint)
            self._mints[mint] = state
        return state

    # ------------------------------------------------------------------ observations

    def observe_seed(self, mint: str, *, migration_time_utc: Any = None,
                     discovery_source: Any = None, discovery_sig_count: Any = None) -> None:
        """Seed-time context from discovery (pump-guard-accepted candidates only)."""
        try:
            state = self._state(mint)
            if state is None:
                return
            if isinstance(discovery_source, str) and discovery_source:
                state.discovery_source = discovery_source[:16]
            sig_count = _f(discovery_sig_count)
            if sig_count is not None and sig_count >= 0:
                state.sig_count = int(sig_count)
            if isinstance(migration_time_utc, str) and migration_time_utc:
                try:
                    state.migration_epoch = datetime.fromisoformat(
                        migration_time_utc.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
        except Exception:
            pass

    def observe_market_sample(self, mint: str, market: Any) -> None:
        """One market observation (tail fetch or sidecar market_context). ``market`` needs a
        positive ``current_price`` to count as a success; anything else is a refresh miss."""
        try:
            state = self._state(mint)
            if state is None:
                return
            now = float(self._now())
            price = _f(market.get("current_price")) if isinstance(market, Mapping) else None
            if price is None or price <= 0:
                state.consecutive_misses += 1
                state.miss_total += 1
                return
            lp = _f(market.get("liquidity_usd"))
            mc = _f(market.get("current_market_cap_usd"))
            state.samples.append((now, price, lp, mc))
            state.consecutive_misses = 0
            state.success_total += 1
            state.last_success_epoch = now
        except Exception:
            pass

    def observe_recheck(self, mint: str, *, reason: Any = None, compose_reason: Any = None,
                        market_context: Any = None) -> None:
        """One engine recheck outcome for a candidate (closed-set reasons only)."""
        try:
            state = self._state(mint)
            if state is None:
                return
            if isinstance(market_context, Mapping) and market_context.get("current_price") is not None:
                self.observe_market_sample(mint, market_context)
            tokens = " ".join(str(t) for t in (reason, compose_reason) if t)
            if any(token in tokens for token in (
                "MARKET_UNAVAILABLE", "MARKET_CAP_UNAVAILABLE", "MARKET_INDEXING",
                "MARKET_INCOMPLETE", "MARKET_STALE", "MARKET_INVALID",
                # PHX2-E2E-004: exhaustion now emits recovery backoff instead of
                # MARKET_UNAVAILABLE; keep the same warning-only telemetry.
                "MARKET_RECOVERY_BACKOFF",
            )):
                state.market_unavailable_rechecks += 1
        except Exception:
            pass

    # ------------------------------------------------------------------ classification

    def assess(self, mint: str) -> Dict[str, Any]:
        """Classify ``mint`` from everything observed so far. Total; always returns a valid
        assessment dict (UNKNOWN when nothing is known)."""
        try:
            return self._assess_inner(mint)
        except Exception:
            return self._assessment(RISK_UNKNOWN, [REASON_NO_MARKET_DATA], mint=mint,
                                    samples=0, misses=0, sig_count=None)

    def _assess_inner(self, mint: str) -> Dict[str, Any]:
        th = self.thresholds
        state = self._mints.get(mint) if isinstance(mint, str) else None
        if state is None:
            return self._assessment(RISK_UNKNOWN, [REASON_NO_MARKET_DATA], mint=mint,
                                    samples=0, misses=0, sig_count=None)
        now = float(self._now())
        high: List[str] = []
        medium: List[str] = []

        samples = [s for s in state.samples if s[1] is not None and s[1] > 0]
        lp_seen_present = False
        if samples:
            latest_epoch, latest_price, latest_lp, _latest_mc = samples[-1]
            lps = [s[2] for s in samples if s[2] is not None and s[2] >= 0]
            lp_seen_present = bool(lps)

            # 1) LP level + trend
            if latest_lp is not None:
                if latest_lp < th.lp_critical_usd:
                    high.append(REASON_LP_CRITICALLY_LOW)
                elif latest_lp < th.lp_thin_usd:
                    medium.append(REASON_LP_THIN)
                peak_lp = max(lps) if lps else None
                if peak_lp is not None and peak_lp >= th.lp_min_peak_usd and peak_lp > 0:
                    if latest_lp <= peak_lp * (1.0 - th.lp_collapse_drop):
                        high.append(REASON_LIQUIDITY_COLLAPSE)
                    elif latest_lp <= peak_lp * (1.0 - th.lp_falling_drop):
                        medium.append(REASON_LP_FALLING)
            else:
                medium.append(REASON_LP_MISSING)

            # 2) early price behavior (windowed on first observation / migration time)
            prices = [s[1] for s in samples]
            first_price, peak_price = prices[0], max(prices)
            anchor = state.migration_epoch if state.migration_epoch is not None else state.first_epoch
            age = max(0.0, now - float(anchor))
            if len(samples) >= th.min_samples_for_price_rules and peak_price > 0:
                if (peak_price >= first_price * th.spike_multiple
                        and latest_price <= peak_price * th.spike_dump_retention):
                    high.append(REASON_PRICE_SPIKE_DUMP)
                elif age <= th.early_window_seconds \
                        and latest_price <= peak_price * th.early_extreme_retention:
                    high.append(REASON_EARLY_EXTREME_DRAWDOWN)
                elif (age <= th.early_window_seconds and len(samples) >= 3
                        and (peak_price - min(prices)) / peak_price >= th.early_volatility_drop):
                    medium.append(REASON_EARLY_VOLATILITY)

            # 3) freshness of the newest successful sample
            if state.last_success_epoch is not None \
                    and (now - state.last_success_epoch) > th.stale_after_seconds:
                medium.append(REASON_MARKET_STALE)

        # 4) refresh reliability
        if state.consecutive_misses >= th.unavailable_consecutive and state.success_total == 0:
            high.append(REASON_MARKET_UNAVAILABLE_PERSISTENT)
        elif state.consecutive_misses >= th.refresh_fail_consecutive:
            medium.append(REASON_MARKET_REFRESH_FAILING)
        if state.market_unavailable_rechecks >= th.market_incomplete_rechecks:
            medium.append(REASON_MARKET_INCOMPLETE_REPEATED)

        # 5) launch weirdness (creation-page signature count, polling discovery only)
        if state.sig_count is not None:
            if state.sig_count >= th.hot_sig_count_high:
                high.append(REASON_POOL_TOO_HOT)
            elif state.sig_count >= th.hot_sig_count_medium:
                medium.append(REASON_POOL_HOT_EARLY)

        if high:
            label, reasons = RISK_HIGH, high + medium
        elif medium:
            label, reasons = RISK_MEDIUM, medium
        elif state.success_total > 0 and lp_seen_present:
            label, reasons = RISK_LOW, []
        else:
            label, reasons = RISK_UNKNOWN, [REASON_NO_MARKET_DATA]

        assessment = self._assessment(
            label, reasons, mint=mint, samples=len(samples),
            misses=state.miss_total, sig_count=state.sig_count)
        state.last_assessment = assessment
        return assessment

    def _assessment(self, label: str, reasons: List[str], *, mint: Any, samples: int,
                    misses: int, sig_count: Optional[int]) -> Dict[str, Any]:
        # de-dupe, preserve order, bound length
        seen: set = set()
        clean: List[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                clean.append(r)
        return {
            "risk_label": label,
            "risk_reasons": clean[:6],
            "risk_unknown_signals": list(UNKNOWN_SIGNALS_ALWAYS),
            "risk_line": format_risk_line(label, clean),
            "risk_assessed_at_utc": _iso_now(self._now()),
            "risk_signal_counts": {
                "samples": int(samples),
                "refresh_misses": int(misses),
                "discovery_sig_count": sig_count,
            },
            "risk_note": RISK_NOTE,
            "holder_scan_enabled": HOLDER_SCAN_ENABLED,
        }

    # ------------------------------------------------------------------ read views

    def last_assessment(self, mint: str) -> Optional[Dict[str, Any]]:
        state = self._mints.get(mint) if isinstance(mint, str) else None
        return dict(state.last_assessment) if state and state.last_assessment else None

    def risk_line(self, mint: str) -> Optional[str]:
        """Fresh display line for the ping body (assesses at call time). Total."""
        try:
            return str(self.assess(mint).get("risk_line") or "") or None
        except Exception:
            return None

    def summary(self) -> Dict[str, Any]:
        """Redaction-safe counters block for heartbeat / producer_summary / dashboard."""
        by_label: Dict[str, int] = {label: 0 for label in RISK_LABELS}
        reason_counts: Dict[str, int] = {}
        high_mints: List[str] = []
        for mint, state in self._mints.items():
            assessment = state.last_assessment
            if not assessment:
                continue
            label = str(assessment.get("risk_label"))
            if label in by_label:
                by_label[label] += 1
            for r in assessment.get("risk_reasons") or []:
                reason_counts[str(r)] = reason_counts.get(str(r), 0) + 1
            if label == RISK_HIGH and len(high_mints) < 16:
                high_mints.append(mint)
        return {
            "kind": "FREE_TIER_RISK_SUMMARY",
            "tracked_mints": len(self._mints),
            "assessed_mints": sum(by_label.values()),
            "by_label": by_label,
            "reason_counts": dict(sorted(reason_counts.items())),
            "high_risk_mints": high_mints,
            "evicted_total": self._evicted_total,
            "holder_scan_enabled": HOLDER_SCAN_ENABLED,
            "unknown_signals_always": list(UNKNOWN_SIGNALS_ALWAYS),
            "note": RISK_NOTE,
        }


# ---------------------------------------------------------------------------
# Private-Discord dispatch risk POLICY (2026-07-12)
#
# Unlike the warn-only display line below, this is an ENFORCING policy: RISK_HIGH is blocked.
# RISK_MEDIUM is warning-only in explicit DISABLED_SINGLE_STREAM PHX1-parity production, while
# the historical structure rule remains available only when that mode is not selected. It is a
# PURE function over an already-computed assessment plus the
# current market structure — it originates nothing, calls nothing, and (by WHERE the producer
# invokes it: the pre-reserve gate) runs BEFORE any dedupe reserve, webhook transport, send-cap
# consume, or private_ping_count increment. Closed-set tokens only.
# ---------------------------------------------------------------------------

# Terminal decisions (recorded as the candidate-artifact reason + the dashboard block split).
SKIPPED_HIGH_RISK_DISCORD = "SKIPPED_HIGH_RISK_DISCORD"
SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE = "SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE"
DISCORD_DISPATCH_ALLOWED = "DISCORD_DISPATCH_ALLOWED"
MEDIUM_RISK_WARNING_ONLY = "MEDIUM_RISK_WARNING_ONLY"
LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM = "DISABLED_SINGLE_STREAM"

# Closed-set mapped HIGH-risk block reasons (dashboard vocabulary).
HIGH_RISK_TOO_HOT = "HIGH_RISK_TOO_HOT"
HIGH_RISK_LIQUIDITY_COLLAPSE = "HIGH_RISK_LIQUIDITY_COLLAPSE"
HIGH_RISK_MARKET_STALE = "HIGH_RISK_MARKET_STALE"
HIGH_RISK_SCAM_BUNDLE = "HIGH_RISK_SCAM_BUNDLE"   # reserved: no free-tier bundle scan emits this yet
HIGH_RISK_PRICE_COLLAPSE = "HIGH_RISK_PRICE_COLLAPSE"
HIGH_RISK_OTHER = "HIGH_RISK_OTHER"
DISCORD_HIGH_RISK_REASONS = (
    HIGH_RISK_TOO_HOT, HIGH_RISK_LIQUIDITY_COLLAPSE, HIGH_RISK_MARKET_STALE,
    HIGH_RISK_SCAM_BUNDLE, HIGH_RISK_PRICE_COLLAPSE, HIGH_RISK_OTHER,
)

# risk-engine HIGH reason -> closed-set discord block reason (first reason in order wins).
_HIGH_REASON_TO_DISCORD = {
    REASON_POOL_TOO_HOT: HIGH_RISK_TOO_HOT,
    REASON_LIQUIDITY_COLLAPSE: HIGH_RISK_LIQUIDITY_COLLAPSE,
    REASON_LP_CRITICALLY_LOW: HIGH_RISK_LIQUIDITY_COLLAPSE,
    REASON_MARKET_UNAVAILABLE_PERSISTENT: HIGH_RISK_MARKET_STALE,
    REASON_PRICE_SPIKE_DUMP: HIGH_RISK_PRICE_COLLAPSE,
    REASON_EARLY_EXTREME_DRAWDOWN: HIGH_RISK_PRICE_COLLAPSE,
}

# Closed-set weak-MEDIUM block reasons (finer detail under the one terminal decision).
MEDIUM_RISK_LP_TOO_LOW = "MEDIUM_RISK_LP_TOO_LOW"
MEDIUM_RISK_MC_TOO_LOW = "MEDIUM_RISK_MC_TOO_LOW"
MEDIUM_RISK_MARKET_NOT_FRESH = "MEDIUM_RISK_MARKET_NOT_FRESH"
MEDIUM_RISK_STRUCTURE_REASON = "MEDIUM_RISK_STRUCTURE_REASON"

# Strong-MEDIUM structure thresholds — ALL must hold for a MEDIUM to reach Discord.
DISCORD_MEDIUM_MIN_LP_USD = 10000.0
DISCORD_MEDIUM_MIN_MC_USD = 30000.0
# MEDIUM reasons that veto a send outright even if LP/MC/freshness pass.
_MEDIUM_STRUCTURE_VETO = (
    REASON_LIQUIDITY_COLLAPSE, REASON_MARKET_INCOMPLETE_REPEATED, REASON_POOL_TOO_HOT,
)


def map_high_risk_reason(reasons: Any) -> str:
    """First mapped closed-set HIGH reason (ordered by the assessment's reason list)."""
    for r in reasons or ():
        mapped = _HIGH_REASON_TO_DISCORD.get(r)
        if mapped:
            return mapped
    return HIGH_RISK_OTHER


@dataclass(frozen=True)
class DiscordRiskDecision:
    """Result of the dispatch policy. ``allowed`` gates the private Discord path."""
    allowed: bool
    terminal_decision: str
    risk_label: Optional[str]
    risk_reasons: Tuple[str, ...]
    mapped_reason: Optional[str] = None
    warning_only: bool = False
    policy_mode: Optional[str] = None

    def to_record(self) -> Dict[str, Any]:
        return {
            "discord_allowed": self.allowed,
            "terminal_decision": self.terminal_decision,
            "risk_label": self.risk_label,
            "risk_reasons": list(self.risk_reasons),
            "mapped_reason": self.mapped_reason,
            "warning_only": self.warning_only,
            "policy_mode": self.policy_mode,
        }


def classify_discord_dispatch(assessment: Any, *, liquidity_usd: Any = None,
                              market_cap_usd: Any = None,
                              market_fresh: Any = None,
                              lp_integrity_mode: Any = None) -> DiscordRiskDecision:
    """Pure private-Discord dispatch policy over a risk assessment + current market structure.

      RISK_HIGH   -> BLOCK (SKIPPED_HIGH_RISK_DISCORD + mapped closed-set reason).
      RISK_MEDIUM -> warning-only when lp_integrity_mode=DISABLED_SINGLE_STREAM; otherwise the
                     historical explicit policy requires LP >= $10k, MC >= $30k, fresh market,
                     and no structure veto.
      RISK_LOW    -> allowed.
      RISK_UNKNOWN-> allowed (NEVER blocked purely because holder/bundle data is unavailable;
                     every downstream market/liquidity/tier/dip/dedupe/safety gate still runs).

    Total: never raises. HIGH always blocks; MEDIUM never independently blocks in explicit
    single-stream mode. Everything else defers
    to the committed downstream gates (this policy never manufactures a send)."""
    label = (assessment or {}).get("risk_label") if isinstance(assessment, Mapping) else None
    raw_reasons = (assessment or {}).get("risk_reasons") if isinstance(assessment, Mapping) else None
    reasons = tuple(raw_reasons or ())
    if label == RISK_HIGH:
        return DiscordRiskDecision(False, SKIPPED_HIGH_RISK_DISCORD, label, reasons,
                                   map_high_risk_reason(reasons), False,
                                   str(lp_integrity_mode) if lp_integrity_mode else None)
    if label == RISK_MEDIUM:
        if lp_integrity_mode == LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM:
            return DiscordRiskDecision(
                True, DISCORD_DISPATCH_ALLOWED, label, reasons,
                MEDIUM_RISK_WARNING_ONLY, True,
                LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
        lp = _f(liquidity_usd)
        mc = _f(market_cap_usd)
        if any(r in _MEDIUM_STRUCTURE_VETO for r in reasons):
            return DiscordRiskDecision(False, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, label,
                                       reasons, MEDIUM_RISK_STRUCTURE_REASON)
        if lp is None or lp < DISCORD_MEDIUM_MIN_LP_USD:
            return DiscordRiskDecision(False, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, label,
                                       reasons, MEDIUM_RISK_LP_TOO_LOW)
        if mc is None or mc < DISCORD_MEDIUM_MIN_MC_USD:
            return DiscordRiskDecision(False, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, label,
                                       reasons, MEDIUM_RISK_MC_TOO_LOW)
        if not market_fresh:
            return DiscordRiskDecision(False, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, label,
                                       reasons, MEDIUM_RISK_MARKET_NOT_FRESH)
        return DiscordRiskDecision(True, DISCORD_DISPATCH_ALLOWED, label, reasons, None)
    # RISK_LOW / RISK_UNKNOWN / anything unrecognized: allowed here; downstream gates remain.
    return DiscordRiskDecision(True, DISCORD_DISPATCH_ALLOWED, label, reasons, None)


# ---------------------------------------------------------------------------
# WARN-ONLY risk display line on the outgoing ping body
# ---------------------------------------------------------------------------

# Discord hard content limit; appending never pushes the body past it (skip instead).
MAX_PING_CONTENT_CHARS = 2000

RISK_LINE_APPENDED = "RISK_LINE_APPENDED"
RISK_LINE_NO_BINDING = "RISK_LINE_NO_BINDING"
RISK_LINE_BODY_MISMATCH = "RISK_LINE_BODY_MISMATCH"
RISK_LINE_UNAVAILABLE = "RISK_LINE_UNAVAILABLE"
RISK_LINE_TOO_LONG = "RISK_LINE_SKIPPED_TOO_LONG"


class FreeTierRiskLineTransport:
    """Wraps any ``send_one_audited_post(*, webhook_identity, payload)`` transport (the no-send
    recorder OR the proven Stage28 private seam) and appends the mint-bound "Risk: ..." line.

    Same safety shape as the proven production ``AxiomFeeAppendingTransport``:
      * the composer arms ``bind_body(body=<exact dispatched body>, mint=...)`` right before the
        guarded send (via the engine's existing ``axiom_fee_appender`` display seam),
      * the binding is ONE-SHOT (consumed on every send; a stale bind can never annotate a
        later send), and the line is appended only on an EXACT body match,
      * display-arming/annotation errors can NEVER affect eligibility, the dedupe reserve, or
        the send — any failure just forwards the payload unmodified,
      * WARN-ONLY by construction: there is no code path in which this wrapper blocks,
        drops, or re-routes a send (RISK_HIGH included).
    """

    def __init__(self, *, inner: Any,
                 risk_line_fn: Callable[[str], Optional[str]],
                 max_content_chars: int = MAX_PING_CONTENT_CHARS) -> None:
        self._inner = inner
        self._risk_line_fn = risk_line_fn
        self._max = int(max_content_chars)
        self._pending_body: Optional[str] = None
        self._pending_mint: Optional[str] = None
        self._appends_count = 0
        self._last_decision: Optional[Dict[str, Any]] = None

    def __getattr__(self, name: str) -> Any:
        """Duck-type passthrough: unknown PUBLIC attributes (``fake_only``,
        ``recorded_count``, ``transport_kind``, ...) resolve from the wrapped transport, so
        wrapping never hides the inner transport's declared capabilities. Private names raise
        immediately (recursion guard for a partially-constructed instance)."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    # -- introspection (session send-record + tests) --

    @property
    def inner(self) -> Any:
        return self._inner

    @property
    def appends_count(self) -> int:
        return self._appends_count

    @property
    def last_decision(self) -> Optional[Dict[str, Any]]:
        return dict(self._last_decision) if self._last_decision else None

    # -- arming (compose seam calls this; same contract as the Axiom appender) --

    def bind_body(self, *, body: Any, mint: Any) -> None:
        if isinstance(body, str) and body and isinstance(mint, str) and mint:
            self._pending_body = body
            self._pending_mint = mint
        else:
            self._pending_body = None
            self._pending_mint = None

    # -- wrapped transport call --

    def send_one_audited_post(self, *, webhook_identity: Optional[str], payload: Any) -> Any:
        new_payload, decision = self._decide(payload)
        self._pending_body = None       # one-shot: consumed regardless of outcome
        self._pending_mint = None
        self._last_decision = decision
        if decision.get("appended"):
            self._appends_count += 1
        return self._inner.send_one_audited_post(
            webhook_identity=webhook_identity, payload=new_payload)

    def _decide(self, payload: Any) -> Tuple[Any, Dict[str, Any]]:
        """Total: any internal failure returns the payload UNMODIFIED with a closed-set
        status. Only ever edits ``payload['content']`` by appending one line."""
        mint = self._pending_mint
        decision: Dict[str, Any] = {"appended": False, "status": RISK_LINE_NO_BINDING,
                                    "mint": mint, "risk_line": None}
        try:
            if self._pending_body is None or mint is None:
                return payload, decision
            content = payload.get("content") if isinstance(payload, Mapping) else None
            if not isinstance(content, str) or content != self._pending_body:
                decision["status"] = RISK_LINE_BODY_MISMATCH
                return payload, decision
            try:
                line = self._risk_line_fn(mint)
            except Exception:
                line = None
            if not isinstance(line, str) or not line.strip():
                decision["status"] = RISK_LINE_UNAVAILABLE
                return payload, decision
            line = line.strip()
            if len(content) + 1 + len(line) > self._max:
                decision["status"] = RISK_LINE_TOO_LONG
                decision["risk_line"] = line
                return payload, decision
            new_payload = dict(payload)
            new_payload["content"] = content + "\n" + line
            decision["appended"] = True
            decision["status"] = RISK_LINE_APPENDED
            decision["risk_line"] = line
            return new_payload, decision
        except Exception:
            decision["status"] = RISK_LINE_UNAVAILABLE
            return payload, decision


__all__ = (
    "RISK_LOW", "RISK_MEDIUM", "RISK_HIGH", "RISK_UNKNOWN", "RISK_LABELS",
    "REASON_LIQUIDITY_COLLAPSE", "REASON_LP_CRITICALLY_LOW", "REASON_PRICE_SPIKE_DUMP",
    "REASON_EARLY_EXTREME_DRAWDOWN", "REASON_MARKET_UNAVAILABLE_PERSISTENT",
    "REASON_POOL_TOO_HOT", "REASON_LP_THIN", "REASON_LP_FALLING", "REASON_LP_MISSING",
    "REASON_MARKET_STALE", "REASON_MARKET_REFRESH_FAILING",
    "REASON_MARKET_INCOMPLETE_REPEATED", "REASON_EARLY_VOLATILITY", "REASON_POOL_HOT_EARLY",
    "REASON_NO_MARKET_DATA", "HIGH_REASONS", "MEDIUM_REASONS",
    "UNKNOWN_SIGNAL_HOLDER", "UNKNOWN_SIGNAL_BUNDLE_WALLETS", "UNKNOWN_SIGNALS_ALWAYS",
    "HOLDER_SCAN_ENABLED", "RISK_NOTE", "MAX_PING_CONTENT_CHARS",
    "RISK_LINE_APPENDED", "RISK_LINE_NO_BINDING", "RISK_LINE_BODY_MISMATCH",
    "RISK_LINE_UNAVAILABLE", "RISK_LINE_TOO_LONG",
    "FreeTierRiskThresholds", "FreeTierRiskEngine", "FreeTierRiskLineTransport",
    "format_risk_line",
    # --- private-Discord dispatch risk policy (enforcing) ---
    "SKIPPED_HIGH_RISK_DISCORD", "SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE",
    "DISCORD_DISPATCH_ALLOWED", "MEDIUM_RISK_WARNING_ONLY",
    "LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM",
    "HIGH_RISK_TOO_HOT", "HIGH_RISK_LIQUIDITY_COLLAPSE", "HIGH_RISK_MARKET_STALE",
    "HIGH_RISK_SCAM_BUNDLE", "HIGH_RISK_PRICE_COLLAPSE", "HIGH_RISK_OTHER",
    "DISCORD_HIGH_RISK_REASONS",
    "MEDIUM_RISK_LP_TOO_LOW", "MEDIUM_RISK_MC_TOO_LOW", "MEDIUM_RISK_MARKET_NOT_FRESH",
    "MEDIUM_RISK_STRUCTURE_REASON",
    "DISCORD_MEDIUM_MIN_LP_USD", "DISCORD_MEDIUM_MIN_MC_USD",
    "map_high_risk_reason", "DiscordRiskDecision", "classify_discord_dispatch",
)
