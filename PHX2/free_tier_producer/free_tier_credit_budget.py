"""free_tier_credit_budget.py — cumulative per-run credit/rate budget for the free-tier producer.

OUT-OF-REPO operator glue. One pure, stdlib-only tracker that bounds what a single producer run may
spend across EVERY seed window (the committed capture caps are per-window only):

  * discovery spend: seed windows opened, RAW WS notifications seen, getTransaction fetches,
    accepted candidates (all cumulative across windows; a window's caps are SHRUNK to the
    remaining cumulative allowance before the WS is even opened),
  * polling spend (POLLING/HYBRID discovery): poll cycles, pool listings, signature pages,
    polled getTransaction fetches (folded into the SAME cumulative getTransaction budget),
  * send budget: total send attempts per run (would-pings in no-send mode, real private pings in
    armed mode) — the proven production runner deliberately has NO send-cap field, so it lives here,
  * rate-limit tripwires: market-transport + polling HTTP 429 count, consecutive WS-fault windows
    (a 429'd WS handshake surfaces as the closed-set WS_CONNECT_FAILED), cumulative RPC errors,
  * market read budget: total market-transport HTTP requests.

RAW WS SEMANTICS (2026-07-10 fix): ``ws_notifications_seen`` counts RAW logsSubscribe messages
delivered over the socket — an INTERNAL firehose counter. It is NOT the Helius dashboard credit
meter (observed 2026-07-09: 120k raw messages while the Helius dashboard showed only ~14k/1M
credits used across ALL runs). The cap exists purely as a runaway-socket safety bound; it must be
sized from the observed raw message rate (~40k raw msgs per 90s window ≈ 450/s), never from plan
credits. ``RAW_WS_CAP_NOTE`` carries this warning into every snapshot artifact.

STOP MECHANISM: crossing any ceiling only sets ``stop_requested`` (first reason wins). The session
raises ``FreeTierBudgetExhausted`` from its ``on_cycle`` hook — a TICK BOUNDARY, after the tick's
artifacts/ledger work is complete — which the proven runner catches as its fail-closed unexpected-
exception stop. ``rewrite_result_for_budget_stop`` + ``verdict_for_budget_stop`` then relabel that
one specific, deliberately-raised stop as a clean ``BUDGET_<reason>`` operator boundary (exit 0)
IFF every ledger/artifact/redaction invariant still holds. Nothing else is ever relabeled.

HTTP 429 IS NOT A STOP (2026-07-31 restart-state remediation). A provider answering "slow down"
says nothing about the OTHER providers, about the durable migration journal, or about the
candidates already being watched. The 2026-07-31 retest proved the cost of conflating them: 7
Birdeye 429s crossed ``max_429_total=5``, latched ``BUDGET_RATE_LIMIT_429``, and stopped a producer
whose Helius discovery was entirely healthy — and the forced restart is what destroyed the tracked
candidate state. 429s are therefore routed to PROVIDER-SCOPED bounded, jittered backoff
(:mod:`provider_backoff`) which suppresses that one provider's requests until the throttle abates.
``max_429_total`` is retained with its name and artifact key intact, but its MEANING is now the
sustained-degradation threshold: crossing it reports ``PROVIDER_RATE_LIMIT_DEGRADED`` in
health/status and never terminates the run or erases candidate state. Real spend stays bounded by
``max_market_requests_total`` / ``max_polls_total`` / ``max_gettransaction_total``, which are
unchanged and still latch. 401/403 are NOT throttles: they remain permanent, fail-closed and fatal
at their own pre-startup credential gate.

Closed-set reasons/counters only; no URL, no key, no payload, no secret anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Mapping, Optional, Tuple

from PHX2.free_tier_producer import provider_backoff as _pb
from PHX2.free_tier_producer.market_budget import (
    MARKET_REQUEST_CAP_UNBOUNDED,
    market_budget_status,
)

# Closed-set budget stop reasons (rendered as stop_reason "BUDGET_<reason>").
# NOTE: "WS_NOTIFICATIONS" means the RAW WS message safety cap (not Helius credits); the token is
# kept stable so historical artifacts/dashboards keep parsing.
BUDGET_STOP_SEND_CAP = "SEND_CAP"
BUDGET_STOP_WS_NOTIFICATIONS = "WS_NOTIFICATIONS"
BUDGET_STOP_SEED_WINDOWS = "SEED_WINDOWS"
BUDGET_STOP_CANDIDATES = "CANDIDATES"
BUDGET_STOP_GETTRANSACTION = "GETTRANSACTION"
BUDGET_STOP_MARKET_REQUESTS = "MARKET_REQUESTS"
#: Sustained market blindness past its bounded grace. NOT a spend ceiling --
#: this is the fail-closed action for a producer that can no longer observe the
#: market at all. The 2026-08-02 run had no such stop and stayed nominally
#: healthy for 4h38m while every candidate was refused for MARKET_INCOMPLETE.
BUDGET_STOP_MARKET_PLANE_BLIND = "MARKET_PLANE_BLIND"
#: RETIRED AS A STOP (2026-07-31). Kept exported so historical artifacts and
#: dashboards that parse the ``BUDGET_RATE_LIMIT_429`` token keep resolving it.
#: Nothing latches it any more — see the module docstring.
BUDGET_STOP_RATE_LIMIT_429 = "RATE_LIMIT_429"
BUDGET_STOP_WS_SOURCE_DEGRADED = "WS_SOURCE_DEGRADED"
BUDGET_STOP_RPC_SOURCE_DEGRADED = "RPC_SOURCE_DEGRADED"
BUDGET_STOP_POLLS = "POLLS"

BUDGET_STOP_PREFIX = "BUDGET_"

# Redaction-safe warning carried into every snapshot artifact + operator report line.
RAW_WS_CAP_NOTE = "raw WS notifications are not Helius dashboard credits"

# The runner-side labels this module relabels (kept as literals so this module never imports the
# frozen production runner).
_RUNNER_STOP_UNEXPECTED_EXCEPTION = "UNEXPECTED_EXCEPTION"


class FreeTierBudgetExhausted(Exception):
    """Deliberate tick-boundary stop signal raised by the session's on_cycle hook."""

    def __init__(self, reason: str):
        self.reason = str(reason)
        super().__init__(self.reason)


#: ``max_sends_per_run`` sentinel meaning "no per-run send ceiling".  Reserved
#: for the canonical managed 24/7 launcher (which must never terminate merely
#: because N alerts were sent -- the 2026-07-27 run 094120Z ended on its 3rd
#: send via BUDGET_SEND_CAP, wiping candidate state on the forced restart).
#: Bounded acceptance/ceremony runs keep their explicit positive caps and stop
#: exactly at them; the default remains the bounded 3.  Per-send safety is
#: unchanged either way: dedupe, tier monotonicity, risk gate, market
#: completeness, crossing-tick block and the inter-send cooldown all still
#: gate every individual dispatch.
SEND_CAP_UNBOUNDED = 0

#: ``max_market_requests_total`` sentinel meaning "no lifetime market-request
#: ceiling", re-exported from :mod:`PHX2.free_tier_producer.market_budget` so
#: the two UNBOUNDED sentinels read identically at every call site.  The
#: 2026-08-02 five-hour run proved why this had to exist: the managed launcher
#: stated the send sentinel and stayed silent about the market cap, inheriting
#: the bounded default of 5,000 and going market-blind 22 minutes in.  Bounded
#: acceptance/ceremony runs keep their explicit positive caps unchanged.
MARKET_CAP_UNBOUNDED = MARKET_REQUEST_CAP_UNBOUNDED


@dataclass(frozen=True)
class FreeTierCreditBudgetCaps:
    """Per-RUN cumulative ceilings. Every field must be a positive int (fail-closed on nonsense);
    the ONE exception is ``max_sends_per_run``, which additionally admits the explicit
    ``SEND_CAP_UNBOUNDED`` (0) sentinel for the managed 24/7 posture.
    Defaults are deliberately bounded — the default run is capped, never a 24h free-for-all.

    ``max_raw_ws_notifications_total`` is the RAW WS MESSAGE safety cap (renamed 2026-07-10 from
    ``max_ws_notifications_total``): it bounds raw logsSubscribe messages seen on the socket, which
    are NOT Helius dashboard credits. Size it from the observed raw rate (~450 msg/s while a window
    is open), never from plan credits.

    ``max_429_total`` is NO LONGER A STOP CEILING (2026-07-31). It is the sustained-throttle
    DEGRADATION threshold: crossing it marks the throttled provider
    ``PROVIDER_RATE_LIMIT_DEGRADED`` in health/status while the producer keeps running on its
    healthy sources. Provider-scoped bounded/jittered backoff does the actual throttle management."""

    max_sends_per_run: int = 3
    max_raw_ws_notifications_total: int = 120000
    max_seed_windows: int = 120
    max_candidates_total: int = 400
    max_gettransaction_total: int = 1024
    max_market_requests_total: int = 5000
    max_429_total: int = 5
    max_consecutive_ws_errors: int = 2
    max_rpc_errors_total: int = 12
    max_polls_total: int = 5000

    def __post_init__(self) -> None:
        unbounded_capable = {
            "max_sends_per_run": SEND_CAP_UNBOUNDED,
            "max_market_requests_total": MARKET_CAP_UNBOUNDED,
        }
        for name, v in asdict(self).items():
            floor = unbounded_capable.get(name, 1)
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= floor):
                raise ValueError(f"{name} must be a positive int")

    @property
    def sends_unbounded(self) -> bool:
        """True iff this run has NO per-run send ceiling (managed 24/7 posture)."""
        return self.max_sends_per_run == SEND_CAP_UNBOUNDED

    @property
    def market_requests_unbounded(self) -> bool:
        """True iff this run has NO lifetime market-request ceiling.

        Required for ``--run-forever``: a deployment with no clock boundary
        must not carry a non-refilling lifetime spend boundary.
        """
        return self.max_market_requests_total == MARKET_CAP_UNBOUNDED

    @property
    def max_ws_notifications_total(self) -> int:
        """Legacy read alias for the renamed raw WS message cap."""
        return self.max_raw_ws_notifications_total

    def to_dict(self) -> Dict[str, int]:
        d = asdict(self)
        # Legacy artifact/dashboard key kept as an alias of the canonical raw-cap name.
        d["max_ws_notifications_total"] = d["max_raw_ws_notifications_total"]
        return d


def _nonneg_int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


class FreeTierCreditBudget:
    """Cumulative per-run budget/counter state. Pure in-memory; the session persists snapshots."""

    def __init__(
        self,
        caps: FreeTierCreditBudgetCaps,
        *,
        delivery_enabled: Optional[bool] = None,
        discord_enabled: Optional[bool] = None,
        ws_exhaustion_latches: bool = True,
        market_backoff: Optional["_pb.ProviderRateLimitBackoff"] = None,
        polling_backoff: Optional["_pb.ProviderRateLimitBackoff"] = None,
    ) -> None:
        self.caps = caps
        # Provider-SCOPED throttle state. One market-primary object is shared
        # with the market transport (which records each individual 429 and each
        # recovery); the polling object is driven from this module's per-cycle
        # stats. A throttle on one never touches the other, and neither can
        # stop the run.
        self.market_backoff = market_backoff or _pb.ProviderRateLimitBackoff(
            _pb.PROVIDER_MARKET_PRIMARY,
            degraded_after_consecutive=caps.max_429_total)
        self.polling_backoff = polling_backoff or _pb.ProviderRateLimitBackoff(
            _pb.PROVIDER_DISCOVERY_POLLING,
            degraded_after_consecutive=caps.max_429_total)
        #: Latched-visible (never fatal) sustained-throttle marker.
        self.rate_limit_degraded = False
        # ``discord_enabled`` is a constructor-only compatibility alias for
        # older offline callers. Runtime state is transport-neutral.
        if delivery_enabled is None:
            delivery_enabled = bool(discord_enabled)
        elif discord_enabled is not None:
            raise ValueError("select delivery_enabled or legacy discord_enabled, not both")
        self.delivery_enabled = bool(delivery_enabled)
        # ws mode (default True): an exhausted raw-WS/seed-window budget latches a clean run stop
        # (the legacy protective behavior). HYBRID sets False: WS exhaustion only stops FURTHER
        # WS windows (downgrade to polling-only); real-spend ceilings still latch normally.
        self.ws_exhaustion_latches = bool(ws_exhaustion_latches)
        self.seed_windows = 0
        self.windows_blocked_by_budget = 0
        self.ws_notifications_seen = 0          # RAW WS messages (not Helius credits)
        self.gettransaction_fetches = 0         # cumulative across WS windows AND polling
        self.candidates_accepted = 0
        self.rpc_errors_total = 0
        self.ws_error_windows = 0
        self.consecutive_ws_errors = 0
        self.send_attempts = 0
        self.sent_ok_count = 0
        self.market_requests = 0
        self.count_429 = 0                      # market-transport 429s (absolute mirror)
        # Polling-discovery counters (POLLING/HYBRID modes; all cumulative for the run).
        self.poll_count = 0
        self.polls_blocked_by_budget = 0
        self.polling_pools_listed = 0
        self.polling_pools_new = 0
        self.polling_signatures_seen = 0
        self.polling_signatures_new = 0
        self.polling_transactions_fetched = 0
        self.polling_create_pool_candidates = 0
        self.polling_pump_suffix_accepted = 0
        self.polling_non_pump_guard_dropped = 0
        self.polling_pools_skipped_too_hot = 0
        self.polling_errors = 0
        self.polling_429 = 0                    # polling-side HTTP 429s (cumulative)
        self.stop_requested = False
        self.stop_reason: Optional[str] = None

    # ------------------------------------------------------------------ stops

    def request_stop(self, reason: str) -> None:
        """Latch the FIRST budget stop reason; later crossings never overwrite it."""
        if not self.stop_requested:
            self.stop_requested = True
            self.stop_reason = str(reason)

    def check_and_raise(self) -> None:
        """Session on_cycle hook body: raise the deliberate tick-boundary stop when latched."""
        if self.stop_requested:
            raise FreeTierBudgetExhausted(self.stop_reason or "UNKNOWN")

    # ------------------------------------------------------------------ discovery windows

    def raw_ws_remaining(self) -> int:
        """Remaining RAW WS message allowance (0 when exhausted). Pure read; never latches —
        HYBRID mode uses it to silently skip further WS windows and continue polling."""
        return max(0, self.caps.max_raw_ws_notifications_total - self.ws_notifications_seen)

    def window_allowance(self, *, per_window_notifications: int,
                         per_window_gettransaction: int) -> Optional[Dict[str, int]]:
        """Pre-window gate. Returns the SHRUNK per-window caps for the next seed window, or None
        when the discovery budget is exhausted (which also latches the stop — strict budgeting:
        an exhausted discovery budget ends the run at the next tick boundary rather than idling).
        When None is returned the caller must NOT open a WS / make any RPC."""
        if self.stop_requested:
            self.windows_blocked_by_budget += 1
            return None
        reason: Optional[str] = None
        if self.seed_windows >= self.caps.max_seed_windows:
            reason = BUDGET_STOP_SEED_WINDOWS
        elif self.ws_notifications_seen >= self.caps.max_raw_ws_notifications_total:
            reason = BUDGET_STOP_WS_NOTIFICATIONS
        elif self.gettransaction_fetches >= self.caps.max_gettransaction_total:
            reason = BUDGET_STOP_GETTRANSACTION
        elif self.candidates_accepted >= self.caps.max_candidates_total:
            reason = BUDGET_STOP_CANDIDATES
        if reason is not None:
            self.windows_blocked_by_budget += 1
            if (reason in (BUDGET_STOP_WS_NOTIFICATIONS, BUDGET_STOP_SEED_WINDOWS)
                    and not self.ws_exhaustion_latches):
                return None     # HYBRID downgrade: no more WS windows, but the run continues
            self.request_stop(reason)
            return None
        return {
            "max_notifications": max(1, min(
                _nonneg_int(per_window_notifications),
                self.caps.max_raw_ws_notifications_total - self.ws_notifications_seen)),
            "max_gettransaction": max(1, min(
                _nonneg_int(per_window_gettransaction),
                self.caps.max_gettransaction_total - self.gettransaction_fetches)),
        }

    def record_window(self, stats: Mapping[str, Any], *, accepted: int) -> None:
        """Fold one completed capture window's stats into the cumulative counters and latch any
        ceiling crossing. ``stats`` is the committed capture's closed-set stats dict."""
        self.seed_windows += 1
        self.ws_notifications_seen += _nonneg_int(stats.get("notifications_seen"))
        self.gettransaction_fetches += _nonneg_int(stats.get("gettransaction_fetches"))
        self.rpc_errors_total += _nonneg_int(stats.get("rpc_errors"))
        self.candidates_accepted += _nonneg_int(accepted)
        if bool(stats.get("ws_error")):
            self.ws_error_windows += 1
            self.consecutive_ws_errors += 1
        else:
            self.consecutive_ws_errors = 0
        # Tripwires first (repeated throttle/degradation), then plain budget ceilings.
        if self.consecutive_ws_errors >= self.caps.max_consecutive_ws_errors:
            self.request_stop(BUDGET_STOP_WS_SOURCE_DEGRADED)
        if self.rpc_errors_total >= self.caps.max_rpc_errors_total:
            self.request_stop(BUDGET_STOP_RPC_SOURCE_DEGRADED)
        if self.ws_exhaustion_latches:
            if self.ws_notifications_seen >= self.caps.max_raw_ws_notifications_total:
                self.request_stop(BUDGET_STOP_WS_NOTIFICATIONS)
            if self.seed_windows >= self.caps.max_seed_windows:
                self.request_stop(BUDGET_STOP_SEED_WINDOWS)
        if self.gettransaction_fetches >= self.caps.max_gettransaction_total:
            self.request_stop(BUDGET_STOP_GETTRANSACTION)
        if self.candidates_accepted >= self.caps.max_candidates_total:
            self.request_stop(BUDGET_STOP_CANDIDATES)

    # ------------------------------------------------------------------ polling discovery

    def polling_allowance(self, *, per_poll_gettransaction: int) -> Optional[Dict[str, int]]:
        """Pre-poll gate for POLLING/HYBRID discovery. Returns the SHRUNK per-poll getTransaction
        allowance, or None when the polling budget is exhausted (latches the stop like
        ``window_allowance``). Deliberately does NOT consult the raw-WS cap: an exhausted WS
        budget must never kill a polling run."""
        if self.stop_requested:
            self.polls_blocked_by_budget += 1
            return None
        reason: Optional[str] = None
        if self.poll_count >= self.caps.max_polls_total:
            reason = BUDGET_STOP_POLLS
        elif self.gettransaction_fetches >= self.caps.max_gettransaction_total:
            reason = BUDGET_STOP_GETTRANSACTION
        elif self.candidates_accepted >= self.caps.max_candidates_total:
            reason = BUDGET_STOP_CANDIDATES
        if reason is not None:
            self.polls_blocked_by_budget += 1
            self.request_stop(reason)
            return None
        return {
            "max_gettransaction": max(1, min(
                _nonneg_int(per_poll_gettransaction),
                self.caps.max_gettransaction_total - self.gettransaction_fetches)),
        }

    def record_poll(self, stats: Mapping[str, Any], *, accepted: int, guard_dropped: int) -> None:
        """Fold one completed polling cycle's closed-set stats into the cumulative counters and
        latch any ceiling crossing. Polled getTransaction fetches consume the SAME cumulative
        getTransaction budget as WS-window fetches."""
        self.poll_count += 1
        cycle_429 = _nonneg_int(stats.get("polling_429"))
        if cycle_429:
            # Provider-scoped bounded/jittered backoff, one rung per throttled
            # cycle. The polling surface keeps running; only its next probe is
            # deferred.
            for _ in range(cycle_429):
                self.polling_backoff.record_throttle()
        elif _nonneg_int(stats.get("pools_listed")) \
                or _nonneg_int(stats.get("signatures_seen")):
            # A cycle that actually reached the provider and was not throttled
            # is observable recovery evidence.
            self.polling_backoff.record_success()
        self.polling_pools_listed += _nonneg_int(stats.get("pools_listed"))
        self.polling_pools_new += _nonneg_int(stats.get("pools_new"))
        self.polling_signatures_seen += _nonneg_int(stats.get("signatures_seen"))
        self.polling_signatures_new += _nonneg_int(stats.get("signatures_new"))
        tx = _nonneg_int(stats.get("transactions_fetched"))
        self.polling_transactions_fetched += tx
        self.gettransaction_fetches += tx
        self.polling_create_pool_candidates += _nonneg_int(stats.get("create_pool_candidates"))
        self.polling_pools_skipped_too_hot += _nonneg_int(stats.get("pools_skipped_too_hot"))
        self.polling_errors += _nonneg_int(stats.get("polling_errors"))
        self.polling_429 += _nonneg_int(stats.get("polling_429"))
        self.rpc_errors_total += _nonneg_int(stats.get("rpc_errors"))
        self.candidates_accepted += _nonneg_int(accepted)
        self.polling_pump_suffix_accepted += _nonneg_int(accepted)
        self.polling_non_pump_guard_dropped += _nonneg_int(guard_dropped)
        # Tripwires first, then plain ceilings (mirrors record_window).
        self._check_429_degradation()
        if self.rpc_errors_total >= self.caps.max_rpc_errors_total:
            self.request_stop(BUDGET_STOP_RPC_SOURCE_DEGRADED)
        if self.gettransaction_fetches >= self.caps.max_gettransaction_total:
            self.request_stop(BUDGET_STOP_GETTRANSACTION)
        if self.candidates_accepted >= self.caps.max_candidates_total:
            self.request_stop(BUDGET_STOP_CANDIDATES)
        if self.poll_count >= self.caps.max_polls_total:
            self.request_stop(BUDGET_STOP_POLLS)

    def record_provider_candidates(self, accepted: int) -> None:
        """Count candidates drained from a paid primary stream against the shared run cap."""
        self.candidates_accepted += _nonneg_int(accepted)
        if self.candidates_accepted >= self.caps.max_candidates_total:
            self.request_stop(BUDGET_STOP_CANDIDATES)

    def _check_429_degradation(self) -> None:
        """Sustained-throttle DEGRADATION marker across both HTTP surfaces.

        Deliberately does NOT call ``request_stop``: a throttled provider is a
        recoverable, provider-local condition (see the module docstring). The
        marker rides ``snapshot()`` into the heartbeat / producer_summary and
        from there into the operator health matrix.
        """

        if (self.count_429 + self.polling_429) >= self.caps.max_429_total:
            self.rate_limit_degraded = True

    @property
    def rate_limit_status(self) -> str:
        """Worst provider status across the isolated throttle scopes."""

        statuses = (self.market_backoff.status, self.polling_backoff.status)
        if self.rate_limit_degraded \
                or _pb.PROVIDER_RATE_LIMIT_DEGRADED in statuses:
            return _pb.PROVIDER_RATE_LIMIT_DEGRADED
        if _pb.PROVIDER_RATE_LIMIT_BACKOFF in statuses:
            return _pb.PROVIDER_RATE_LIMIT_BACKOFF
        return _pb.PROVIDER_RATE_LIMIT_OK

    # ------------------------------------------------------------------ sends / market

    def record_send_attempt(self, *, sent_ok: bool) -> None:
        """One engine send attempt reached the guard transport (would-ping or real ping)."""
        self.send_attempts += 1
        if sent_ok:
            self.sent_ok_count += 1
        if not self.caps.sends_unbounded \
                and self.send_attempts >= self.caps.max_sends_per_run:
            self.request_stop(BUDGET_STOP_SEND_CAP)

    def observe_market(self, stats: Mapping[str, Any]) -> None:
        """Mirror the market transport's cumulative counters (idempotent absolute reads).

        ``http_calls_total`` is already the PHYSICAL count -- requests that
        actually reached the wire -- so this ceiling was never the one that
        killed the 2026-08-02 run.  Under the UNBOUNDED sentinel it is not a
        ceiling at all: the run stays observable through the counter without
        being stopped by it.
        """
        self.market_requests = _nonneg_int(stats.get("http_calls_total"))
        self.count_429 = _nonneg_int(stats.get("http_429"))
        self._check_429_degradation()
        if self.caps.market_requests_unbounded:
            return
        if self.market_requests >= self.caps.max_market_requests_total:
            self.request_stop(BUDGET_STOP_MARKET_REQUESTS)

    def market_budget_block(self) -> Dict[str, Any]:
        """Operator-facing market-budget mode/limit/consumption block."""

        return market_budget_status(
            self.caps.max_market_requests_total, self.market_requests)

    # ------------------------------------------------------------------ reporting

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe counters block for heartbeat + producer_summary (counts/bools/closed-set
        tokens only). Carries the operator-requested keys verbatim."""
        return {
            "kind": "FREE_TIER_CREDIT_BUDGET",
            "ws_notifications_seen": self.ws_notifications_seen,
            "raw_ws_notifications_seen": self.ws_notifications_seen,
            "raw_ws_notifications_are_not_helius_credits": True,
            "raw_ws_cap_note": RAW_WS_CAP_NOTE,
            "seed_windows": self.seed_windows,
            "windows_blocked_by_budget": self.windows_blocked_by_budget,
            "candidate_count": self.candidates_accepted,
            "gettransaction_fetches": self.gettransaction_fetches,
            "send_attempts": self.send_attempts,
            "sent_ok_count": self.sent_ok_count,
            "would_ping_count": (0 if self.delivery_enabled else self.send_attempts),
            "private_ping_count": (self.sent_ok_count if self.delivery_enabled else 0),
            "market_requests": self.market_requests,
            **self.market_budget_block(),
            "429_count": self.count_429,
            "rpc_errors_total": self.rpc_errors_total,
            "ws_error_windows": self.ws_error_windows,
            "consecutive_ws_errors": self.consecutive_ws_errors,
            "polling": {
                "poll_count": self.poll_count,
                "polls_blocked_by_budget": self.polls_blocked_by_budget,
                "pools_listed": self.polling_pools_listed,
                "pools_new": self.polling_pools_new,
                "signatures_seen": self.polling_signatures_seen,
                "signatures_new": self.polling_signatures_new,
                "transactions_fetched": self.polling_transactions_fetched,
                "create_pool_candidates": self.polling_create_pool_candidates,
                "pump_suffix_accepted": self.polling_pump_suffix_accepted,
                "non_pump_guard_dropped": self.polling_non_pump_guard_dropped,
                "pools_skipped_too_hot": self.polling_pools_skipped_too_hot,
                "polling_errors": self.polling_errors,
                "polling_429": self.polling_429,
            },
            # Provider-isolated throttle state. A throttled provider is
            # visible here and in the health matrix; it never appears as a stop.
            "rate_limit": {
                "status": self.rate_limit_status,
                "degraded": (
                    self.rate_limit_degraded
                    or self.rate_limit_status
                    == _pb.PROVIDER_RATE_LIMIT_DEGRADED),
                "degradation_threshold": self.caps.max_429_total,
                "observed_429_total": self.count_429 + self.polling_429,
                "market_primary": self.market_backoff.snapshot(),
                "discovery_polling": self.polling_backoff.snapshot(),
            },
            "budget_stop_requested": self.stop_requested,
            "budget_stop_reason": self.stop_reason,
            "caps": self.caps.to_dict(),
        }


# --------------------------------------------------------------------------- result relabeling


def rewrite_result_for_budget_stop(result: Dict[str, Any],
                                   budget: FreeTierCreditBudget) -> Tuple[Dict[str, Any], bool]:
    """Relabel EXACTLY the runner stop our own on_cycle raise produced (UNEXPECTED_EXCEPTION with
    exception_type FreeTierBudgetExhausted while a budget stop was latched) as the clean operator
    boundary ``BUDGET_<reason>``. Any other stop — including a REAL unexpected exception that
    happens to race a latched budget — passes through untouched."""
    tripped = (
        budget.stop_requested
        and result.get("stop_reason") == _RUNNER_STOP_UNEXPECTED_EXCEPTION
        and result.get("exception_type") == FreeTierBudgetExhausted.__name__
    )
    if not tripped:
        return result, False
    rewritten = {
        **result,
        "stop_reason": BUDGET_STOP_PREFIX + (budget.stop_reason or "UNKNOWN"),
        "exception_type": None,
        "budget_stop": True,
        "budget_stop_mechanism": FreeTierBudgetExhausted.__name__,
    }
    return rewritten, True


def verdict_for_budget_stop(verdict: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade the postflight verdict to a clean exit-0 boundary for a relabeled budget stop IFF
    every safety invariant held (known+consistent ledger, known artifacts, clean redaction scan).
    A budget stop with ANY violated invariant stays a nonzero investigate-me exit."""
    if not result.get("budget_stop"):
        return verdict
    invariants_ok = (
        bool(result.get("ledger_state_known"))
        and bool(result.get("artifact_state_known", True))
        and bool(result.get("ledger_consistent"))
        and bool(result.get("redaction_ok"))
    )
    if not invariants_ok:
        return {**verdict, "budget_stop": True}
    return {**verdict, "postflight_ok": True, "exit_code": 0, "clean_stop": True,
            "budget_stop": True}


__all__ = (
    "BUDGET_STOP_SEND_CAP", "BUDGET_STOP_WS_NOTIFICATIONS", "BUDGET_STOP_SEED_WINDOWS",
    "BUDGET_STOP_CANDIDATES", "BUDGET_STOP_GETTRANSACTION", "BUDGET_STOP_MARKET_REQUESTS",
    "BUDGET_STOP_MARKET_PLANE_BLIND", "MARKET_CAP_UNBOUNDED",
    "BUDGET_STOP_RATE_LIMIT_429", "BUDGET_STOP_WS_SOURCE_DEGRADED",
    "BUDGET_STOP_RPC_SOURCE_DEGRADED", "BUDGET_STOP_POLLS", "BUDGET_STOP_PREFIX",
    "RAW_WS_CAP_NOTE", "SEND_CAP_UNBOUNDED",
    "FreeTierBudgetExhausted", "FreeTierCreditBudgetCaps", "FreeTierCreditBudget",
    "rewrite_result_for_budget_stop", "verdict_for_budget_stop",
)
