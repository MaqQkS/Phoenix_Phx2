"""production_live_runner.py — production private-live forward-watch engine (NO total send cap).

OUT-OF-REPO operator glue. Pure-ish orchestrator: stdlib + the injected callables only. Imports the
Axiom fee gate (pure) for the pre-reserve decision; the send lineage is NOT reimplemented here — the
caller injects the committed/proven ``run_cap1_candidates`` engine plus the real (or fake) ledger,
guard, transport, sidecar, and clocks.

DIFFERENCE FROM BUILD 30/31 (intentional):
  * NO fixed total send cap. The loop does NOT stop because N pings were sent. It runs until a
    runtime/operator boundary or a safety circuit breaker. Quality control is the Axiom fee gate +
    the committed downstream eligibility filters, NOT an arbitrary proof cap.
  * PERIODIC RE-SEED. Unlike Build 31 (seed-once -> drain -> WATCHLIST_EMPTY), this re-seeds the
    watchlist on a cadence so it keeps discovering through a long session.
  * AXIOM FEE GATE FIRST. Each active candidate is evaluated by the Axiom fee gate BEFORE it can
    reach the send engine. Only Axiom-PASSED candidates are passed to ``run_cap1_candidates`` (where
    the dedupe RESERVE + guarded send live), so an Axiom-failed candidate can neither reserve a
    durable ledger line nor send Discord.

Rate limiting WITHOUT a count cap: the committed engine sends at most ONE ping per invocation (the
first eligible candidate), and a per-send cooldown (``min_seconds_between_sends``) spaces sends.
These are production rate limits / backpressure, NOT proof caps.

Circuit breakers (all are production safety stops, not proof caps): max runtime boundary, market
read budget, queue (watchlist) pressure, source (discovery) failure, sustained API/Discord throttle
with backoff, unknown ledger state, ledger mismatch (delta outside {0,1} per cycle),
artifact/ledger inconsistency, sustained explicit delivery failure (each single failure keeps the
candidate ACTIVE under bounded retry backoff; the durable dedupe row is committed ONLY after
confirmed delivery), ambiguous delivery outcome (DELIVERY_UNKNOWN -> operator reconciliation),
incomplete post-receipt ledger commit, secret-scan failure, and any unexpected exception. On ANY
stop the loop exits once and NEVER auto-reruns.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_SELF = str(Path(__file__).resolve().parent)
if _SELF not in sys.path:
    sys.path.insert(0, _SELF)

from production_live_axiom_gate import (  # noqa: E402
    AXIOM_GATE_PASSED, AXIOM_GATE_THROTTLED, AxiomFeeGateConfig, axiom_eligibility_source,
    build_axiom_send_summary, evaluate_axiom_fee_gate, is_strict_axiom_config,
)
from PHX2.free_tier_producer.scam_policy import (  # noqa: E402
    DeliverySafetyDecision,
    delivery_block_reason,
    validate_delivery_decision,
)
from PHX2.free_tier_producer.checkpoint_envelope import (  # noqa: E402
    CheckpointWriteError,
)
from PHX2.free_tier_producer.phx1_parity_policy import (  # noqa: E402
    ALERT_POLICY_LEGACY,
    LEGACY_WATCH_TTL_SECONDS,
    Phx1ParityCounters,
    is_phx1_parity,
    resolve_policy,
    watch_ttl_seconds,
)
from PHX2.models.artifact_source_labels import (  # noqa: E402
    SOURCE_ROLE_PAID_MARKET_PRIMARY as _SOURCE_ROLE_PAID_MARKET_PRIMARY,
)


# --------------------------------------------------------------------------- PHX2 liquidity floor

# Hard minimum on-chain liquidity (USD) a candidate must show BEFORE it may reserve a durable ledger
# line or reach the private Discord transport. PHX2 market/liquidity eligibility — NOT an Axiom gate,
# independent of Axiom observe-only. Enforced pre-reserve via the committed engine's generic
# ``pre_reserve_gate_fn`` hook (wired in production_live_session).
#
# Codex P1 (2026-06-22): parsing is STRICT Decimal — NEVER binary float — so a value that float() would
# round UP to the threshold (e.g. "4499.999999999999999999") or that float()/str.replace would silently
# normalize (commas, underscores, exponent, sign) can NEVER fail OPEN. Only a strict plain-decimal
# string (or an already-finite Decimal) is honored; everything else fails CLOSED (blocks).
MIN_LIQUIDITY_USD = Decimal("4500")
LIQUIDITY_USD_BELOW_MIN_REASON = "LIQUIDITY_USD_BELOW_MIN"

# Strict plain-decimal grammar: digits with an OPTIONAL single '.' fractional part. NO sign, NO comma,
# NO underscore, NO exponent, NO NaN/Infinity, NO empty. Surrounding whitespace is stripped first.
_STRICT_DECIMAL_RE = re.compile(r"\A[0-9]+(?:\.[0-9]+)?\Z")
# Conservative charset for echoing the OBSERVED raw value back into the (redaction-scanned) reason:
# short decimal-ish tokens only (surfaces the malformed inputs we reject — "4,500", "4_500", "4.5e3",
# "+4500", "NaN" — none of which can contain a URL/secret needle like "://").
_SAFE_OBSERVED_RE = re.compile(r"\A[0-9A-Za-z.,+\-_ ]{1,40}\Z")


def _parse_liquidity_usd(value: Any) -> Optional[Decimal]:
    """STRICT parse of a market-context ``liquidity_usd`` to a FINITE ``Decimal``, or ``None`` (block).

    Codex P1 fail-closed contract — NO binary float anywhere:
      * ``bool`` -> None (a bool is never a liquidity value).
      * ``Decimal`` -> the value iff finite (NaN/Infinity -> None).
      * ``str`` -> ``Decimal(s)`` ONLY when ``s`` (after stripping surrounding whitespace) matches the
        strict plain-decimal grammar. Commas, underscores, exponent notation, signs, ``NaN``/
        ``Infinity`` and the empty string are REJECTED.
      * ``int`` / ``float`` / anything else -> None. Float is rejected outright (the real sidecar emits
        DECIMAL TEXT, so there is no live float path) to remove ALL binary-rounding fail-open risk.
    No rounding ever occurs: the Decimal preserves the exact written precision."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, str):
        s = value.strip()
        if not _STRICT_DECIMAL_RE.match(s):
            return None
        try:
            dec = Decimal(s)
        except InvalidOperation:
            return None
        return dec if dec.is_finite() else None
    return None


def _safe_observed_liquidity(raw: Any) -> Optional[str]:
    """A short, redaction-safe rendering of the OBSERVED raw liquidity for the rejection reason, or
    ``None`` to omit. Decimal text is public market data (never a secret); we still bound length +
    charset so a malformed/garbage value can never inject a URL/secret needle into the scanned artifact."""
    if raw is None:
        return None
    if isinstance(raw, (bool, int, float, Decimal)):
        return str(raw)[:40]
    if isinstance(raw, str):
        s = raw.strip()
        if s and _SAFE_OBSERVED_RE.match(s):
            return s
        return None
    return None


def liquidity_floor_block_reason(mint: str, ctx: Any,
                                 *, min_liquidity_usd: Decimal = MIN_LIQUIDITY_USD) -> Optional[str]:
    """PHX2 pre-reserve liquidity floor (NOT an Axiom gate). Return a STABLE, detailed block reason
    string if the candidate's resolved ``liquidity_usd`` is missing / invalid / malformed / zero /
    negative / NaN / Infinity / non-strict-decimal / float / or strictly below ``min_liquidity_usd``;
    else ``None`` (allowed). Fail-closed: anything not provably a FINITE Decimal >= the floor blocks. The
    reason ALWAYS starts with ``LIQUIDITY_USD_BELOW_MIN`` (the normalized artifact reason) and carries
    ``min_liquidity_usd``, the safe observed raw value, and the parsed value WHEN the parse succeeded."""
    floor = min_liquidity_usd if isinstance(min_liquidity_usd, Decimal) else Decimal(str(min_liquidity_usd))
    raw = ctx.get("liquidity_usd") if isinstance(ctx, dict) else None
    parsed = _parse_liquidity_usd(raw)
    if parsed is not None and parsed >= floor:
        return None
    parts = [f"min_liquidity_usd={floor}"]
    obs = _safe_observed_liquidity(raw)
    if obs is not None:
        parts.append(f"observed={obs}")
    if parsed is not None:
        parts.append(f"parsed={parsed}")
    return f"{LIQUIDITY_USD_BELOW_MIN_REASON} ({'; '.join(parts)})"


# --------------------------------------------------------------------------- closed-set stop reasons

# Clean operator-boundary stops (exit 0 when the ledger is consistent).
STOP_MAX_RUNTIME = "MAX_RUNTIME"
STOP_MARKET_BUDGET = "MARKET_BUDGET"
STOP_WATCHLIST_EMPTY = "WATCHLIST_EMPTY"      # only when no discovery_fn (cannot re-seed)
STOP_TICK_BUDGET = "TICK_BUDGET"              # anti-runaway safety bound (NOT a send cap)
# Absolute wall-clock ceiling. Only reachable when an acceptance clock is in
# use and its phase never activated (e.g. a pre-soak recovery that could not
# complete): the run ends on the operator's outer boundary instead of hanging.
# Deliberately NOT a clean stop -- an unactivated soak is never a PASS.
STOP_WALL_CLOCK_CEILING = "WALL_CLOCK_CEILING"

# Safety / error stops (exit nonzero — operator must investigate; never auto-rerun).
STOP_QUEUE_PRESSURE = "QUEUE_PRESSURE"
STOP_SOURCE_FAILURE = "SOURCE_FAILURE"
STOP_THROTTLED = "THROTTLED"
STOP_UNKNOWN_LEDGER_STATE = "UNKNOWN_LEDGER_STATE"
STOP_LEDGER_MISMATCH = "LEDGER_MISMATCH"
STOP_ARTIFACT_LEDGER_INCONSISTENCY = "ARTIFACT_LEDGER_INCONSISTENCY"
STOP_TRANSPORT_ERROR = "TRANSPORT_ERROR"
# Delivery transaction stops (PHX2-E2E-001): an ambiguous delivery outcome
# needs explicit operator reconciliation (never silent success / silent retry);
# a confirmed delivery whose ledger commit could not complete must finish the
# commit via restart reconciliation before anything else sends.
STOP_DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
STOP_DELIVERY_COMMIT_INCOMPLETE = "DELIVERY_COMMIT_INCOMPLETE"
STOP_SECRET_SCAN_FAILURE = "SECRET_SCAN_FAILURE"
STOP_UNEXPECTED_EXCEPTION = "UNEXPECTED_EXCEPTION"
STOP_EXCEPTION_AFTER_RESERVE = "EXCEPTION_AFTER_RESERVE"     # +1 ledger delta, attributed artifact
STOP_EXCEPTION_BEFORE_RESERVE = "EXCEPTION_BEFORE_RESERVE"   # 0 delta, no fake artifact
STOP_LEDGER_RECHECK_FAILED = "LEDGER_RECHECK_FAILED"         # post-engine ledger read raised
STOP_ARTIFACT_WRITE_FAILED = "ARTIFACT_WRITE_FAILED"         # +1 reserved but durable artifact write failed
STOP_LAX_AXIOM_CONFIG_REFUSED = "LAX_AXIOM_CONFIG_REFUSED"   # injected Axiom config not strict (pre-work refusal)
STOP_UNKNOWN_RESERVED_CANDIDATE = "UNKNOWN_RESERVED_CANDIDATE"  # +1 observed but exact reserved mint unprovable
# Operator Ctrl+C / KeyboardInterrupt / SystemExit caught gracefully so the runner returns its accumulated
# result and the session writes interrupted_* postflight. Deliberately NOT a clean stop: an interrupted run
# is never a full PASS (postflight_ok stays False) even when its ledger delta is consistent.
STOP_OPERATOR_INTERRUPTED = "OPERATOR_INTERRUPTED"
STOP_OPERATOR_REQUESTED = "OPERATOR_REQUESTED"

_CLEAN_STOPS = frozenset({STOP_MAX_RUNTIME, STOP_MARKET_BUDGET, STOP_WATCHLIST_EMPTY,
                          STOP_TICK_BUDGET, STOP_OPERATOR_REQUESTED})


class ProductionThrottleSignal(Exception):
    """A discovery/source callable may raise this to signal upstream rate-limiting; the runner
    applies backoff and stops (THROTTLED) if it is sustained."""


#: How many CONSECUTIVE per-tick redaction scans may fail for read errors ONLY
#: (zero needle hits; e.g. a checkpoint file atomically replaced mid-walk)
#: before the run still stops closed with SECRET_SCAN_FAILURE.  A single
#: transient unreadable file killed a whole live run on 2026-07-27 (final scan
#: artifact: 0 hits).  A scan with ANY actual needle hit still stops the run
#: IMMEDIATELY -- this debounce never applies to real exposure evidence.
MAX_CONSECUTIVE_SCAN_READ_FAILURES = 3

SCAN_VERDICT_CLEAN = "CLEAN"
SCAN_VERDICT_READ_ERROR_ONLY = "READ_ERROR_ONLY"
SCAN_VERDICT_UNSAFE = "UNSAFE"


def classify_redaction_scan(scan: object) -> str:
    """Closed-set per-tick scan classification.

    ``UNSAFE`` = any needle hit, or a non-REDACTED status not fully explained
    by recorded read errors (fail closed for scanners that do not report
    ``read_errors``).  ``READ_ERROR_ONLY`` = zero hits, non-REDACTED status,
    and at least one recorded read error -- the transient-unreadable-file
    class the caller debounces.  A needle hit is NEVER downgraded to
    READ_ERROR_ONLY: the hit test runs first, unconditionally.  Pure / total;
    never raises.
    """
    result = scan if isinstance(scan, dict) else {}
    try:
        hits = int(result.get("total_unsafe_hits", 0) or 0)
    except (TypeError, ValueError):
        hits = 1
    if hits != 0:
        return SCAN_VERDICT_UNSAFE
    if result.get("redaction_status") == "REDACTED":
        return SCAN_VERDICT_CLEAN
    read_errors = result.get("read_errors")
    if isinstance(read_errors, dict) and read_errors:
        return SCAN_VERDICT_READ_ERROR_ONLY
    return SCAN_VERDICT_UNSAFE


class ScanFailureDebounce:
    """The per-run secret-scan stop decision, isolated for deterministic tests.

    ``observe(verdict)`` returns ``True`` when the run must stop closed:
    immediately for ``UNSAFE`` (a real needle hit, or an unexplained
    non-REDACTED status), and after ``MAX_CONSECUTIVE_SCAN_READ_FAILURES``
    CONSECUTIVE ``READ_ERROR_ONLY`` scans.  A CLEAN scan resets the streak --
    which is safe because the scanner can only report REDACTED when EVERY
    file was successfully read and needle-scanned (``redacted = total == 0
    and not read_errors``): a persistently unreadable file therefore can
    never produce the CLEAN that would reset its own streak, so it always
    reaches the fail-closed stop.
    """

    def __init__(
        self, *, max_consecutive_read_failures: int = (
            MAX_CONSECUTIVE_SCAN_READ_FAILURES),
    ) -> None:
        self._limit = int(max_consecutive_read_failures)
        self.consecutive_read_failures = 0

    def observe(self, verdict: str) -> bool:
        if verdict == SCAN_VERDICT_UNSAFE:
            return True
        if verdict == SCAN_VERDICT_READ_ERROR_ONLY:
            self.consecutive_read_failures += 1
            return self.consecutive_read_failures >= self._limit
        self.consecutive_read_failures = 0
        return False


#: ``max_runtime_seconds`` sentinel meaning "no runtime boundary at all".
#: Stage 10 needs a producer that runs until an operator (or the watchdog's
#: cooperative stop request) ends it, because a supervised 24/7 service may not
#: be faked with a very large timeout: a timeout still ends the process at an
#: arbitrary instant and would make the watchdog restart a perfectly healthy
#: producer on a schedule.  The sentinel follows the existing ``max_reseeds`` /
#: ``max_total_ticks`` idiom in this same dataclass (``0 => unbounded``), so no
#: positive bound changes meaning.  Every OTHER breaker -- queue pressure,
#: source failures, throttles, market budget, secret scan, ledger ambiguity --
#: is untouched and still ends the run, so "unbounded" is only ever about the
#: clock.
UNBOUNDED_RUNTIME_SECONDS = 0.0


def runtime_bound_is_unbounded(max_runtime_seconds: object) -> bool:
    """Is this ``max_runtime_seconds`` value the explicit no-clock sentinel?

    A non-numeric value is treated as bounded so a malformed configuration can
    never accidentally produce an endless run.
    """

    try:
        return float(max_runtime_seconds) <= UNBOUNDED_RUNTIME_SECONDS
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ProductionBounds:
    """Operator-tunable bounds. NOTE: there is deliberately NO total send cap field — sends are not
    capped by count. Every field below is a runtime/rate/backpressure/safety bound."""

    recheck_interval_seconds: float = 90.0
    max_candidate_age_seconds: int = 3600
    max_rechecks_per_candidate: int = 240           # high; expiry hygiene, NOT a send cap
    max_runtime_seconds: float = 28800.0            # 8h operator boundary; 0 => unbounded
    max_watchlist_size: int = 256
    queue_pressure_max: int = 256                   # backpressure breaker
    max_market_calls_total: int = 200000            # lifetime read budget, NOT a send cap
    reseed_interval_seconds: float = 300.0          # periodic re-seed cadence
    max_reseeds: int = 0                            # 0 => unlimited within the runtime boundary
    min_seconds_between_sends: float = 300.0        # send cooldown (rate limit, NOT a cap)
    max_consecutive_source_failures: int = 3        # discovery failure breaker
    max_consecutive_throttles: int = 5              # sustained-throttle breaker
    max_consecutive_transport_failures: int = 5     # explicit-delivery-failure breaker
    throttle_backoff_base_seconds: float = 5.0
    throttle_backoff_max_seconds: float = 120.0
    max_total_ticks: int = 0                        # 0 => unbounded (runtime is the real bound)
    #: Named alert policy. LEGACY keeps every committed gate exactly as-is;
    #: PHX1_PARITY relaxes the closed set declared in phx1_parity_policy.
    alert_policy: str = ALERT_POLICY_LEGACY

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _iso_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(now_dt: datetime, seeded_at: str) -> Optional[float]:
    try:
        s = datetime.fromisoformat(str(seeded_at).replace("Z", "+00:00")).astimezone(timezone.utc)
        return (now_dt - s).total_seconds()
    except Exception:
        return None


def sent_ok(send_result: Any) -> bool:
    return bool(
        send_result is not None
        and getattr(send_result, "dispatch_forwarded", False)
        and getattr(send_result, "transport_ok", None) is True
    )


def _refused_result(stop_reason: str) -> Dict[str, Any]:
    """A pre-work refusal (e.g. lax Axiom config). Nothing was touched: no source, no discovery, no
    ledger read/reserve, no transport, no send. Shaped like the normal return so the session reporter
    handles it uniformly; the non-clean stop makes postflight exit nonzero."""
    return {
        "outcome": "REFUSED", "stop_reason": stop_reason, "exception_type": None,
        "ticks": 0, "sends": 0, "reseeds": 0, "market_calls": 0,
        "axiom_pass_count": 0, "axiom_fail_count": 0, "total_ledger_delta": 0,
        "reserve_count": 0, "sent_ok_count": 0, "ledger_state_known": True,
        "artifact_state_known": True, "ledger_consistent": True, "redaction_ok": True,
        "send_records": [], "watchlist_summary": {},
    }


def seed_discovered_candidates(
    *,
    watchlist: Any,
    candidates: Any,
    seeded_at_utc: str,
    on_handoff_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_activation_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """Perform and evidence the exact provider-consumer watchlist handoff.

    Admission outcomes are the watchlist's closed set (PHX2-E2E-002): a full
    active watchlist rejects a NEW mint with the explicit observable reason
    ``ACTIVE_WATCH_CAPACITY_REACHED`` (plus active count / configured
    capacity), never a silent drop; terminal history is never resurrected."""
    # Pending durable receipts lead each bounded reseed pass. Queue loss and
    # capacity rejection retain ownership in the inbox until persist() verifies
    # a checkpoint containing the watch or its terminal history.
    pending_fn = getattr(watchlist, "pending_admission_candidates", None)
    pending = pending_fn() if callable(pending_fn) else []
    batch = list(pending) + list(candidates or [])
    seen = set()
    for cand in batch:
        mint = cand.get("token_mint") if isinstance(cand, dict) else None
        candidate_id = cand.get("candidate_id") if isinstance(cand, dict) else None
        identity = (mint, candidate_id)
        if identity in seen:
            continue
        seen.add(identity)
        if on_handoff_event is not None:
            on_handoff_event({
                "kind": "PHX2_PROVIDER_HANDOFF",
                "event": "RUNNER_RECEIVED",
                "observed_at_utc": seeded_at_utc,
                "token_mint": mint,
                "candidate_id": candidate_id,
                "downstream_handoff": "WATCHLIST_SEED",
            })
        if hasattr(watchlist, "seed_with_outcome"):
            entry, outcome = watchlist.seed_with_outcome(
                cand, seeded_at_utc=seeded_at_utc)
        else:  # legacy watchlist objects without explicit outcomes
            before_entry_total = len(watchlist.all_entries())
            entry = watchlist.seed(cand, seeded_at_utc=seeded_at_utc)
            after_entry_total = len(watchlist.all_entries())
            if entry is None:
                outcome = "INVALID_OR_WATCHLIST_CAPACITY"
            elif after_entry_total > before_entry_total:
                outcome = "ADMITTED"
            else:
                outcome = "EXISTING"
        if (entry is not None and outcome in ("ADMITTED", "DROPPED_NON_PUMP")
                and on_activation_event is not None):
            for activation_event in entry.initial_activation_events():
                on_activation_event(activation_event)
        if on_handoff_event is None:
            continue
        if outcome in ("ACTIVE_WATCH_CAPACITY_REACHED",
                       "INVALID_CANDIDATE", "INVALID_OR_WATCHLIST_CAPACITY",
                       "PRE_BOUNDARY_NOT_ELIGIBLE", "DIAGNOSTIC_ONLY"):
            rejection: Dict[str, Any] = {
                "kind": "PHX2_PROVIDER_HANDOFF",
                "event": "WATCHLIST_REJECTED",
                "observed_at_utc": seeded_at_utc,
                "token_mint": mint,
                "candidate_id": candidate_id,
                "reason": outcome,
            }
            if outcome == "ACTIVE_WATCH_CAPACITY_REACHED":
                try:
                    rejection["active_count"] = int(watchlist.active_count())
                    rejection["active_capacity"] = int(watchlist.active_capacity)
                except Exception:
                    pass
            on_handoff_event(rejection)
        elif outcome == "TERMINAL_HISTORY_DUPLICATE":
            on_handoff_event({
                "kind": "PHX2_PROVIDER_HANDOFF",
                "event": "WATCHLIST_ACKNOWLEDGED",
                "observed_at_utc": seeded_at_utc,
                "token_mint": mint,
                "candidate_id": candidate_id,
                "state": getattr(entry, "status", "TERMINAL_HISTORY"),
                "admission": "TERMINAL_HISTORY_DUPLICATE",
            })
        else:
            on_handoff_event({
                "kind": "PHX2_PROVIDER_HANDOFF",
                "event": "WATCHLIST_ACKNOWLEDGED",
                "observed_at_utc": seeded_at_utc,
                "token_mint": mint,
                "candidate_id": candidate_id,
                "state": getattr(entry, "status", "UNKNOWN"),
                "admission": (
                    "ADDED" if outcome == "ADMITTED"
                    else "DROPPED_NON_PUMP" if outcome == "DROPPED_NON_PUMP"
                    else "DEDUPE_SUPPRESSED"
                ),
            })


def run_production_live_watch(
    *,
    watchlist: Any,
    axiom_source: Any,
    axiom_config: AxiomFeeGateConfig,
    sidecar_factory: Callable[[int], Any],
    ath_transport: Any,
    ath_endpoint_secret: Any,
    ledger: Any,
    guard_factory: Callable[[], Any],
    authorization: Any,
    now_dt_fn: Callable[[], datetime],
    now_iso_fn: Callable[[], str],
    now_seconds: Any,
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
    bounds: ProductionBounds,
    run_cap1_candidates_fn: Callable[..., Dict[str, Any]],
    ledger_line_count_fn: Callable[[], int],
    discovery_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    on_axiom_record: Optional[Callable[..., None]] = None,
    on_axiom_results: Optional[Callable[..., None]] = None,
    on_candidate_record: Optional[Callable[..., None]] = None,
    on_send_record: Optional[Callable[..., Dict[str, Any]]] = None,
    on_cycle: Optional[Callable[..., None]] = None,
    redaction_scan_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    watch_state_path: Optional[str] = None,
    on_heartbeat: Optional[Callable[[Dict[str, Any]], None]] = None,
    partial_flush_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
    heartbeat_every_ticks: int = 1,
    partial_flush_every_ticks: int = 1,
    require_axiom_pass: bool = False,
    stop_requested_fn: Optional[Callable[[], bool]] = None,
    # ---- acceptance-phase clock (optional; absent => unchanged behaviour) ----
    #: Evaluated once per tick, before the runtime bound, so the tick that
    #: activates the soak is already inside it.
    phase_tick_fn: Optional[Callable[[], Any]] = None,
    #: Seconds that count toward ``bounds.max_runtime_seconds``. When supplied
    #: this is the ACCEPTANCE clock (active-soak seconds), not wall clock.
    active_seconds_fn: Optional[Callable[[], float]] = None,
    #: Absolute wall-clock ceiling, independent of the acceptance clock.
    max_wall_clock_seconds: Optional[float] = None,
    on_handoff_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_activation_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    activation_market_max_age_seconds: float = 120.0,
    # Role-based, artifact-safe (2026-07-31 redaction cleanup).  The previous
    # default was the provider PRODUCT name, which is a scanner danger needle:
    # any caller that omitted this argument wrote it into watch_state.jsonl and
    # failed the run's redaction scan closed.
    activation_observation_source: str = _SOURCE_ROLE_PAID_MARKET_PRIMARY,
    security_decision_fn: Optional[Callable[[Any], Any]] = None,
    on_security_record: Optional[Callable[..., None]] = None,
    market_scheduler: Any = None,
    tick_wait_fn: Optional[Callable[[float], None]] = None,
    policy_counters: Any = None,
) -> Dict[str, Any]:
    """Run the production private-live forward-watch. Returns a result dict (see bottom). Mutates the
    durable ledger ONLY through the injected ``run_cap1_candidates_fn`` reserve-before-send path.

    AXIOM MODE (2026-06-22): ``require_axiom_pass`` defaults False -> Axiom is OBSERVE-ONLY. The Axiom
    gate still runs BEFORE reserve/send and its verdict + decoded fee are recorded as telemetry and
    attached to the candidate/send artifacts, but it does NOT decide eligibility — PHX2 baseline
    eligibility (the committed ``run_cap1_candidates`` engine: pump gate -> market -> dip/ATH -> dedupe)
    decides. An Axiom FAIL / SOURCE_ERROR / METRICS_INCOMPLETE / THROTTLED never blocks a send and never
    stops the runner. Set ``require_axiom_pass=True`` to opt into the legacy HARD GATE where ONLY
    Axiom-PASSED candidates advance (and a sustained Axiom throttle trips the throttle breaker)."""
    # ---- Codex Blocker 2: enforce a STRICT Axiom gate config internally, BEFORE any source / discovery
    # / ledger / transport work. A direct caller cannot supply a lax config (require_success=False,
    # require_fee_metrics=False, recency disabled, or candidate-mint association disabled) to make a
    # failed/feeless/stale/unassociated tx reserve and send. We REFUSE (fail closed) for clarity rather
    # than silently normalizing.
    if not is_strict_axiom_config(axiom_config):
        return _refused_result(STOP_LAX_AXIOM_CONFIG_REFUSED)

    ticks = 0
    artifact_state_known = True   # Blocker 4: False if a durable send-artifact write fails after a +1
    sends = 0
    reseeds = 0
    market_calls = 0
    checkpoint_write_tolerated_total = 0   # transient watch-checkpoint write failures tolerated (not fatal)
    axiom_pass_count = 0
    axiom_fail_count = 0
    security_allowed_count = 0
    security_blocked_count = 0
    consecutive_source_failures = 0
    consecutive_throttles = 0
    scan_debounce = ScanFailureDebounce()
    consecutive_transport_failures = 0
    last_send_monotonic: Optional[float] = None
    total_ledger_delta = 0
    ledger_state_known = True
    redaction_ok = True
    stop_reason: Optional[str] = None
    exc_type: Optional[str] = None
    interrupted = False
    send_records: List[Dict[str, Any]] = []
    security_results_by_mint: Dict[str, DeliverySafetyDecision] = {}

    # ---- named alert policy ------------------------------------------------
    # The bounds carry the operator's selection; the process binding is the
    # fallback so a direct caller that never set either behaves as LEGACY.
    _alert_policy = resolve_policy(getattr(bounds, "alert_policy", None))
    _parity_enabled = is_phx1_parity(_alert_policy)
    # An explicitly configured candidate age always wins; the policy default
    # applies only when the operator left it at the committed 3600.
    _watch_ttl = int(bounds.max_candidate_age_seconds)
    if _parity_enabled and _watch_ttl == LEGACY_WATCH_TTL_SECONDS:
        _watch_ttl = watch_ttl_seconds(_alert_policy)
    _policy_counters = (
        policy_counters if policy_counters is not None
        else Phx1ParityCounters(policy=_alert_policy))
    _extended_watch_seen: set = set()
    _reactivated_after_hour_seen: set = set()

    def _policy_count(name: str, amount: int = 1) -> None:
        try:
            _policy_counters.increment(name, amount)
        except Exception:
            # Telemetry can never affect eligibility, reserve, or send.
            pass

    def _emit_send_artifact(*, token_mint, candidate_id, cycle_delta_val, send_result,
                            market_context, exception_type=None, reserved_candidate_known=True,
                            axiom_result=None, security_decision=None,
                            ledger_reserved=True, delivery_state=None) -> bool:
        """Codex Blocker 4: attribute a +1 reservation to a send artifact. Guarantees an in-memory
        attempt record (so reserve_count reflects the +1 even if everything downstream fails), then
        attempts the durable artifact write via ``on_send_record``. Returns False iff the durable
        artifact write itself FAILED — the caller then fails closed (ARTIFACT_WRITE_FAILED) and does NOT
        claim coverage. No raw exception text is ever stored (TYPE only).

        Codex Blocker 2: ``reserved_candidate_known`` is recorded on the in-memory record so an
        unknown-attribution +1 (token_mint not provable from the engine result) is never mistaken for a
        correctly-attributed one. ``token_mint`` is the EXACT reserved candidate (from the engine's
        sent_attempt) or None when unknown — it is NEVER inferred from the input candidate order."""
        # OBSERVE-ONLY Axiom telemetry for the EXACT reserved candidate (or the unknown-attribution
        # placeholder when axiom_result is None). A reserved/sent candidate was ALLOWED, so the summary
        # always carries axiom_blocked_candidate=False.
        axiom_summary = build_axiom_send_summary(axiom_result, require_axiom_pass=require_axiom_pass)
        provisional = {"kind": "PRODUCTION_LIVE_SEND_ATTEMPT", "token_mint": token_mint,
                       "tick": ticks, "ledger_reserved": bool(ledger_reserved),
                       "cycle_ledger_delta": cycle_delta_val,
                       "sent_ok": bool(sent_ok(send_result)), "exception_type": exception_type,
                       "delivery_state": delivery_state,
                       "reserved_candidate_known": bool(reserved_candidate_known),
                       "axiom": axiom_summary,
                       "security": (security_decision.to_dict()
                                    if isinstance(security_decision, DeliverySafetyDecision) else None)}
        if on_send_record is None:
            send_records.append(provisional)
            return True
        try:
            record_kwargs = {
                "token_mint": token_mint, "candidate_id": candidate_id, "tick": ticks,
                "observed_at_utc": now_iso_fn(), "ledger_reserved": bool(ledger_reserved),
                "cycle_delta": cycle_delta_val, "send_result": send_result,
                "market_context": market_context, "exception_type": exception_type,
                "delivery_state": delivery_state,
                "axiom": axiom_summary,
            }
            if isinstance(security_decision, DeliverySafetyDecision):
                record_kwargs["security"] = security_decision.to_dict()
            record = on_send_record(**record_kwargs)
        except Exception:
            provisional["artifact_write_failed"] = True
            send_records.append(provisional)        # in-memory +1 attribution still stands
            return False
        if isinstance(record, dict) and "reserved_candidate_known" not in record:
            record = {**record, "reserved_candidate_known": bool(reserved_candidate_known)}
        send_records.append(record if record is not None else provisional)
        return True

    def _build_result_dict(interrupted_flag: bool) -> Dict[str, Any]:
        """Build the result dict from the CURRENT counters. Used both for the final return AND for the
        periodic partial-flush snapshot (so a partial summary has the same shape as the final one). Pure
        read of the enclosing counters/send_records/watchlist; mutates nothing."""
        reserve_count = sum(1 for s in send_records if s.get("ledger_reserved"))
        sent_ok_count = sum(1 for s in send_records if s.get("sent_ok"))
        ledger_consistent = (
            ledger_state_known and artifact_state_known
            and total_ledger_delta >= 0 and reserve_count == total_ledger_delta)
        outcome = ("INTERRUPTED" if interrupted_flag
                   else ("SENDS_PERFORMED" if sends > 0 else "ZERO_SEND"))
        scheduler_stats: Dict[str, Any] = {}
        if market_scheduler is not None:
            try:
                scheduler_stats = dict(market_scheduler.stats())
            except Exception:
                scheduler_stats = {}
        return {
            "outcome": outcome, "stop_reason": stop_reason, "exception_type": exc_type,
            "interrupted": bool(interrupted_flag),
            "ticks": ticks, "sends": sends, "reseeds": reseeds, "market_calls": market_calls,
            "checkpoint_write_tolerated_total": checkpoint_write_tolerated_total,
            "axiom_pass_count": axiom_pass_count, "axiom_fail_count": axiom_fail_count,
            "security_allowed_count": security_allowed_count,
            "security_blocked_count": security_blocked_count,
            "total_ledger_delta": total_ledger_delta, "reserve_count": reserve_count,
            "sent_ok_count": sent_ok_count, "ledger_state_known": ledger_state_known,
            "artifact_state_known": artifact_state_known, "ledger_consistent": ledger_consistent,
            "redaction_ok": redaction_ok, "send_records": send_records,
            "watchlist_summary": watchlist.summary(),
            "require_axiom_pass": bool(require_axiom_pass),
            "axiom_observe_only": (not require_axiom_pass),
            "final_send_eligibility_source": axiom_eligibility_source(require_axiom_pass),
            "market_scheduler": scheduler_stats,
        }

    def _build_heartbeat(obs: Dict[str, Any]) -> Dict[str, Any]:
        """One redaction-safe per-tick heartbeat record: cumulative counters + watchlist status counts +
        this tick's diagnostic observations (``obs``). Only counts / booleans / closed-set reasons /
        timestamps — never a URL / token / payload / secret."""
        summ = watchlist.summary() if hasattr(watchlist, "summary") else {}
        by = summ.get("by_status", {}) if isinstance(summ, dict) else {}
        try:
            active_n = len(watchlist.active_dip_entries())
        except Exception:
            active_n = summ.get("active_dip_watch")
            if active_n is None:
                try:
                    active_n = len(watchlist.active_entries())
                except Exception:
                    active_n = None
        since_send = None
        if last_send_monotonic is not None:
            try:
                since_send = round(monotonic_fn() - last_send_monotonic, 3)
            except Exception:
                since_send = None
        hb = {
            "kind": "PRODUCTION_LIVE_HEARTBEAT",
            "tick": ticks, "ts_utc": now_iso_fn(),
            "watchlist_total": (summ.get("total") if isinstance(summ, dict) else None),
            "watchlist_active": active_n,
            "watchlist_tracked": summ.get("tracked", 0),
            # WATCHLIST_COUNT is the active/tracked count — terminal history
            # is reported separately and never displayed as tracked work.
            "watchlist_count": summ.get("watchlist_count", summ.get("tracked", 0)),
            "watchlist_active_capacity": summ.get("active_capacity"),
            "watchlist_active_capacity_remaining": summ.get("active_capacity_remaining"),
            "watchlist_terminal_history_total": summ.get("terminal_history", 0),
            "watchlist_terminal_pending_archive": summ.get("terminal_pending_archive", 0),
            "watchlist_capacity_rejections": summ.get("capacity_rejections", 0),
            "watchlist_terminal_archive_succeeded": summ.get("terminal_archive_succeeded", 0),
            "watchlist_terminal_archive_failed": summ.get("terminal_archive_failed", 0),
            "watchlist_legacy_terminal_migrated": summ.get("legacy_terminal_migrated", 0),
            "watchlist_terminal_evicted_from_active": summ.get(
                "terminal_evicted_from_active", 0),
            "pending_baseline": summ.get("pending_baseline", 0),
            "pending_1_20x": summ.get("pending_1_20x", 0),
            "activated": summ.get("activated", 0),
            "active_dip_watch": summ.get("active_dip_watch", 0),
            "watchlist_by_status": dict(by),
            "dropped_non_pump_total": by.get("DROPPED_NON_PUMP", 0),
            "expired_total": by.get("EXPIRED", 0),
            "dedupe_suppressed_total": by.get("DEDUPE_SUPPRESSED", 0),
            "send_attempted_total": by.get("SEND_ATTEMPTED", 0),
            "sent_committed_total": by.get("SENT_OK_COMMITTED", 0),
            "delivery_unknown_total": by.get("DELIVERY_UNKNOWN", 0),
            "delivery_retryable_total": (
                summ.get("delivery_retryable", 0) if isinstance(summ, dict) else 0),
            "consecutive_transport_failures": consecutive_transport_failures,
            "reseeds_total": reseeds, "market_calls_total": market_calls,
            "checkpoint_write_tolerated_total": checkpoint_write_tolerated_total,
            # The FULL watch-checkpoint durability surface, not a three-field
            # excerpt. The 2026-07-29 run failed 61 of 63 writes with only
            # ``checkpoint_durability_status`` reaching this artifact, so the
            # watchdog -- which reads the CURSOR durability keys, a different
            # owner that stayed healthy throughout -- had no field that could
            # have shown it, and the run reported HEALTHY to the end.
            **({
                key: summ.get(key) for key in (
                    "checkpoint_durability_status",
                    "checkpoint_write_attempted_total",
                    "checkpoint_write_succeeded_total",
                    "checkpoint_write_retried_total",
                    "checkpoint_write_retryable_failed_total",
                    "checkpoint_write_permanent_failed_total",
                    "checkpoint_consecutive_failures",
                    "checkpoint_structural_failed_total",
                    "checkpoint_last_failure_category",
                    "checkpoint_last_failure_detail",
                    "checkpoint_last_success_utc",
                    "checkpoint_last_verified_generation",
                    "checkpoint_durable_candidate_count",
                    "checkpoint_quarantined",
                    "checkpoint_status",
                )} if isinstance(summ, dict) else {}),
            "axiom_pass_total": axiom_pass_count, "axiom_fail_total": axiom_fail_count,
            "consecutive_source_failures": consecutive_source_failures,
            "consecutive_throttles": consecutive_throttles,
            "max_consecutive_source_failures": bounds.max_consecutive_source_failures,
            "max_consecutive_throttles": bounds.max_consecutive_throttles,
            "breaker_source_failure_active": consecutive_source_failures > 0,
            "breaker_throttle_active": consecutive_throttles > 0,
            "seconds_since_last_send": since_send,
            "sends_total": sends, "sent_this_tick": int(obs.get("sent_this_tick", 0)),
            "stop_reason": stop_reason,
            "interrupted": (stop_reason == STOP_OPERATOR_INTERRUPTED),
        }
        # Merge this tick's diagnostic observations (reseed/no-send/cooldown/etc.).
        for k, v in (obs or {}).items():
            if not k.startswith("_"):
                hb.setdefault(k, v)
        if market_scheduler is not None:
            try:
                scheduler_stats = dict(market_scheduler.stats())
            except Exception:
                scheduler_stats = {}
            if scheduler_stats:
                hb.update(scheduler_stats)
                hb["market_scheduler"] = {
                    "queue": scheduler_stats.get("market_scheduler_queue_depth"),
                    "in_flight": scheduler_stats.get("market_scheduler_inflight"),
                    "workers": scheduler_stats.get("market_scheduler_worker_count"),
                    "oldest_deadline_age_seconds": scheduler_stats.get(
                        "market_scheduler_oldest_deadline_age_seconds"),
                    "slo_breached": scheduler_stats.get(
                        "market_scheduler_slo_breached"),
                    "price_batches": scheduler_stats.get(
                        "market_price_batch_requests"),
                    "overview_calls": scheduler_stats.get(
                        "market_overview_requests"),
                    "requests_avoided_by_grpc": scheduler_stats.get(
                        "market_requests_avoided_by_grpc"),
                    "late_results_rejected": scheduler_stats.get(
                        "market_scheduler_late_results_rejected"),
                    # ---- PHX2-E2E-006 P1 lane (closed-set/numeric only) ----
                    "scheduler_state": scheduler_stats.get("scheduler_state"),
                    "p1_deadline_seconds": scheduler_stats.get(
                        "configured_p1_deadline_seconds"),
                    "capacity_proof_result": scheduler_stats.get(
                        "capacity_proof_result"),
                    "capacity_bound_seconds": scheduler_stats.get(
                        "calculated_capacity_bound_seconds"),
                    "configured_concurrency": scheduler_stats.get(
                        "configured_concurrency"),
                    "p1_queue_depth": scheduler_stats.get("p1_queue_depth"),
                    "p2_queue_depth": scheduler_stats.get("p2_queue_depth"),
                    "p3_queue_depth": scheduler_stats.get("p3_queue_depth"),
                    "p1_open_windows": scheduler_stats.get("p1_open_windows"),
                    "oldest_p1_age_seconds": scheduler_stats.get(
                        "oldest_p1_age_seconds"),
                    "p1_enqueued_total": scheduler_stats.get("p1_enqueued_total"),
                    "p1_completed_total": scheduler_stats.get(
                        "p1_completed_total"),
                    "p1_deadline_met_total": scheduler_stats.get(
                        "p1_deadline_met_total"),
                    "p1_deadline_missed_total": scheduler_stats.get(
                        "p1_deadline_missed_total"),
                    "p1_temporary_failures_total": scheduler_stats.get(
                        "p1_temporary_failures_total"),
                    "p1_permanent_blocks_total": scheduler_stats.get(
                        "p1_permanent_blocks_total"),
                    "scheduler_p50_seconds": scheduler_stats.get(
                        "scheduler_p50_seconds"),
                    "scheduler_p95_seconds": scheduler_stats.get(
                        "scheduler_p95_seconds"),
                    "scheduler_p99_seconds": scheduler_stats.get(
                        "scheduler_p99_seconds"),
                    "scheduler_max_seconds": scheduler_stats.get(
                        "scheduler_max_seconds"),
                }
        return hb

    start = monotonic_fn()
    # Startup replay is independent of a healthy provider/discovery callback.
    # The watch's bound inbox validates receipts; ordinary candidates cannot
    # opt into this path through a label or a replay boolean.
    seed_discovered_candidates(watchlist=watchlist, candidates=[],
        seeded_at_utc=now_iso_fn(), on_handoff_event=on_handoff_event,
        on_activation_event=on_activation_event)
    # Re-seed schedule. If a discovery_fn is supplied, the FIRST tick re-seeds immediately.
    next_reseed_at = start

    while True:
        tick_obs: Dict[str, Any] = {}
        try:
            ticks += 1
            if stop_requested_fn is not None and bool(stop_requested_fn()):
                stop_reason = STOP_OPERATOR_REQUESTED
                break
            if bounds.max_total_ticks and ticks > bounds.max_total_ticks:
                stop_reason = STOP_TICK_BUDGET
                break
            # Phase evaluation happens BEFORE the runtime bound so the very
            # tick that activates the soak already counts toward it.
            if phase_tick_fn is not None:
                try:
                    phase_tick_fn()
                except Exception:
                    # A phase-clock failure must never end a live run; the
                    # clock stays where it was, which keeps delivery blocked.
                    pass
            # MAX_RUNTIME measures the ACCEPTANCE clock when one is supplied.
            # With a phase clock that is active-soak seconds only, so an
            # inherited pre-soak recovery cannot consume the soak.
            elapsed_for_bound = (
                float(active_seconds_fn()) if active_seconds_fn is not None
                else monotonic_fn() - start)
            # 0 => run until an operator/watchdog stop request or another
            # breaker ends the run. Never a "very large timeout".
            if not runtime_bound_is_unbounded(bounds.max_runtime_seconds) \
                    and elapsed_for_bound >= bounds.max_runtime_seconds:
                stop_reason = STOP_MAX_RUNTIME
                break
            # Independent wall-clock ceiling: a phase that never activates must
            # still end the process rather than run unbounded.
            if max_wall_clock_seconds is not None \
                    and (monotonic_fn() - start) >= float(
                        max_wall_clock_seconds):
                stop_reason = STOP_WALL_CLOCK_CEILING
                break
            if market_calls >= bounds.max_market_calls_total:
                stop_reason = STOP_MARKET_BUDGET
                break

            # ---- secret-scan circuit breaker (artifacts written so far) ----
            if redaction_scan_fn is not None:
                scan = redaction_scan_fn()
                if scan_debounce.observe(classify_redaction_scan(scan)):
                    redaction_ok = False
                    stop_reason = STOP_SECRET_SCAN_FAILURE
                    break

            # ---- periodic re-seed (discovery) ----
            now_mono = monotonic_fn()
            if (
                discovery_fn is not None
                and now_mono >= next_reseed_at
                and (bounds.max_reseeds == 0 or reseeds < bounds.max_reseeds)
            ):
                try:
                    new_cands = discovery_fn()
                    consecutive_source_failures = 0
                except ProductionThrottleSignal:
                    consecutive_throttles += 1
                    if consecutive_throttles >= bounds.max_consecutive_throttles:
                        stop_reason = STOP_THROTTLED
                        break
                    _backoff_sleep(sleep_fn, bounds, consecutive_throttles)
                    if watch_state_path:
                        try:
                            watchlist.persist(watch_state_path)
                        except (CheckpointWriteError, OSError):
                            checkpoint_write_tolerated_total += 1
                    continue
                except Exception:
                    consecutive_source_failures += 1
                    if consecutive_source_failures >= bounds.max_consecutive_source_failures:
                        stop_reason = STOP_SOURCE_FAILURE
                        break
                    _backoff_sleep(sleep_fn, bounds, consecutive_source_failures)
                    continue
                seeded_at = now_iso_fn()
                _s0 = watchlist.summary()
                _by0 = _s0.get("by_status", {}) if isinstance(_s0, dict) else {}
                _tot0 = _s0.get("total", 0) if isinstance(_s0, dict) else 0
                seed_discovered_candidates(
                    watchlist=watchlist,
                    candidates=new_cands,
                    seeded_at_utc=seeded_at,
                    on_handoff_event=on_handoff_event,
                    on_activation_event=on_activation_event,
                )
                _s1 = watchlist.summary()
                _by1 = _s1.get("by_status", {}) if isinstance(_s1, dict) else {}
                _tot1 = _s1.get("total", 0) if isinstance(_s1, dict) else 0
                _disc = len(new_cands or [])
                _added = _tot1 - _tot0
                _drop_added = _by1.get("DROPPED_NON_PUMP", 0) - _by0.get("DROPPED_NON_PUMP", 0)
                tick_obs.update({
                    "reseed_attempted": True, "reseed_discovered": _disc,
                    "reseed_total_added": _added,
                    "reseed_active_added": _added - _drop_added,
                    "reseed_dropped_non_pump_added": _drop_added,
                    "reseed_duplicates": max(0, _disc - _added)})
                reseeds += 1
                next_reseed_at = now_mono + bounds.reseed_interval_seconds

            # ---- queue pressure breaker ----
            tracked = (watchlist.tracked_entries()
                       if hasattr(watchlist, "tracked_entries")
                       else watchlist.active_entries())
            if len(tracked) > bounds.queue_pressure_max:
                stop_reason = STOP_QUEUE_PRESSURE
                break

            # PHX2-E2E-006: provider work is planned by explicit deadline and
            # priority, then executed by bounded workers. This call only
            # enqueues due work; it never waits for provider I/O and therefore
            # cannot delay heartbeat, handoff, or checkpoint persistence.
            if market_scheduler is not None:
                try:
                    market_scheduler.update_candidates(tracked)
                    market_scheduler.plan()
                    tick_obs.update({
                        "market_scheduler_planned": True,
                        "market_scheduler_queue_depth": market_scheduler.stats().get(
                            "market_scheduler_queue_depth"),
                    })
                except Exception:
                    tick_obs["market_scheduler_planned"] = False

            if not tracked:
                tick_obs["idle_no_active_candidates"] = True
                if discovery_fn is None:
                    stop_reason = STOP_WATCHLIST_EMPTY      # cannot re-seed -> drained
                    break
                # else: wait for the next re-seed window.  PHX2-E2E-006: the
                # wait is wakeable — a handoff arrival or P1-due event ends
                # it immediately; the configured interval is the MAXIMUM.
                checkpoint_write_tolerated_total += _finish_tick(watchlist, watch_state_path, on_cycle, ticks, sends, reseeds, stop_reason)
                (tick_wait_fn or sleep_fn)(bounds.recheck_interval_seconds)
                continue

            # ---- PHX1 fee + LP-integrity policy (mandatory, before tier/compose) ----
            security_eligible: List[Any] = []
            for entry in tracked:
                if security_decision_fn is None:
                    # Backward-compatible pure runner seam.  The production
                    # session always injects the mandatory policy; legacy unit
                    # harnesses that exercise unrelated runner behavior do not.
                    security_eligible.append(entry)
                    continue
                try:
                    decision = security_decision_fn(entry)
                except Exception:
                    decision = None
                valid, invalid_reason = validate_delivery_decision(decision)
                reason = (invalid_reason if not valid else delivery_block_reason(decision))
                if on_security_record is not None:
                    on_security_record(entry=entry, decision=decision, reason=reason, tick=ticks)
                if reason:
                    security_blocked_count += 1
                    if on_candidate_record is not None:
                        on_candidate_record(
                            rec={"token_mint": entry.token_mint,
                                 "reason": reason,
                                 "security": (decision.to_dict()
                                              if isinstance(decision, DeliverySafetyDecision) else None),
                                 "compose_attempted": False,
                                 "reservation_attempted": False,
                                 "active_ledger_mutated": False,
                                 "delivery_transport_attempted": False,
                                 "telegram_transport_attempted": False,
                                 "discord_transport_attempted": False},
                            entry=entry, cycle=ticks, observed_at_utc=now_iso_fn(),
                            ledger_touched=False, transport_attempted=False,
                            axiom=None, security=decision)
                    continue
                security_allowed_count += 1
                security_results_by_mint[entry.token_mint] = decision
                security_eligible.append(entry)

            tick_obs.update({
                "security_allowed_this_tick": len(security_eligible),
                "security_blocked_total": security_blocked_count,
            })

            # ---- AXIOM enrichment (observe-only by DEFAULT; opt-in hard gate) ----
            # Runs BEFORE any reserve/send. In observe-only mode the Axiom verdict + decoded fee is
            # recorded as TELEMETRY (attached to the candidate/send artifacts) but does NOT decide
            # eligibility — every active candidate is handed to the committed PHX2 engine, which applies
            # the real eligibility (pump gate -> market -> dip/ATH -> dedupe). In hard-gate mode
            # (require_axiom_pass) ONLY Axiom-PASSED candidates advance.
            axiom_results_by_mint: Dict[str, Any] = {}
            candidates_for_engine: List[Any] = []
            tick_axiom_throttled = False
            for entry in security_eligible:
                mint = entry.token_mint
                result = evaluate_axiom_fee_gate(
                    mint, source=axiom_source, config=axiom_config, now_iso_fn=now_iso_fn,
                )
                axiom_results_by_mint[mint] = result
                if on_axiom_record is not None:
                    on_axiom_record(mint=mint, result=result)
                passed = (result.status == AXIOM_GATE_PASSED and result.passed)
                if passed:
                    axiom_pass_count += 1
                else:
                    axiom_fail_count += 1   # telemetry count only; in observe-only this NEVER blocks
                if result.status == AXIOM_GATE_THROTTLED:
                    tick_axiom_throttled = True
                if require_axiom_pass:
                    if passed:
                        candidates_for_engine.append(entry)   # hard gate: only Axiom-PASSED advance
                else:
                    candidates_for_engine.append(entry)       # observe-only: Axiom NEVER blocks

            # The Axiom-throttle circuit breaker applies ONLY in hard-gate mode. In observe-only mode an
            # Axiom RPC throttle is telemetry and must NEVER stop the runner or skip a send (req #7/#9);
            # the candidate proceeds and the committed engine's own eligibility decides.
            if require_axiom_pass and tick_axiom_throttled:
                consecutive_throttles += 1
                if consecutive_throttles >= bounds.max_consecutive_throttles:
                    stop_reason = STOP_THROTTLED
                    break
                _backoff_sleep(sleep_fn, bounds, consecutive_throttles)
                checkpoint_write_tolerated_total += _finish_tick(watchlist, watch_state_path, on_cycle, ticks, sends, reseeds, stop_reason)
                continue
            consecutive_throttles = 0
            _tick_summary = watchlist.summary()
            _dip_active = _tick_summary.get("active_dip_watch")
            if _dip_active is None:
                _dip_active = len(tracked)
            tick_obs.update({"candidates_tracked": len(tracked),
                             "candidates_active": _dip_active,
                             "candidates_for_engine": len(candidates_for_engine),
                             "axiom_throttled_this_tick": bool(tick_axiom_throttled)})

            # OBSERVE-ONLY display arming: hand this tick's per-mint Axiom verdicts to the (optional)
            # Discord fee-append seam so a sent ping can carry the mint-bound Axiom Fees line. Pure
            # callback over a COPY of the verdicts; does NOT affect eligibility / reserve / send and never
            # stops the runner (a callback error is swallowed — display must never break the send path).
            if on_axiom_results is not None:
                try:
                    on_axiom_results(dict(axiom_results_by_mint))
                except Exception:
                    pass

            # ---- send engine (cooldown-gated) ----
            # observe-only: ALL active candidates (Axiom never filtered them); hard-gate: only Axiom-PASSED.
            cooldown_ok = (
                last_send_monotonic is None
                or (monotonic_fn() - last_send_monotonic) >= bounds.min_seconds_between_sends
            )
            tick_obs["cooldown_active"] = not cooldown_ok
            # PHX2-E2E-006: while the send cooldown blocks the engine, open
            # P1 windows close as an EXPLICIT temporary cooldown result and
            # re-arm when the cooldown releases — never a silent pending
            # state, never a spurious deadline-miss count.
            if market_scheduler is not None:
                try:
                    market_scheduler.note_send_cooldown(not cooldown_ok)
                except Exception:
                    pass
            if candidates_for_engine and cooldown_ok:
                try:
                    lc_before = ledger_line_count_fn()
                except Exception:
                    ledger_state_known = False
                    stop_reason = STOP_UNKNOWN_LEDGER_STATE
                    break

                sidecar = sidecar_factory(ticks)
                guard = guard_factory()
                cand_dicts = []
                for entry in candidates_for_engine:
                    candidate = entry.to_candidate()
                    decision = security_results_by_mint.get(entry.token_mint)
                    candidate["security_decision"] = decision
                    if isinstance(decision, DeliverySafetyDecision):
                        candidate["fee_gate"] = decision.fee_snapshot.to_dict()
                        # Single-stream mode carries no LP snapshot; display
                        # DISABLED (never a fabricated PASS).
                        candidate["lp_integrity"] = (
                            decision.lp_snapshot.to_dict()
                            if decision.lp_snapshot is not None
                            else {"lp_integrity": "DISABLED",
                                  "lp_integrity_mode": decision.lp_integrity_mode})
                        candidate["scam_policy"] = decision.to_dict()
                    cand_dicts.append(candidate)

                def _activation_gate(cand: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
                    entry = watchlist.get(cand.get("token_mint", ""))
                    if entry is None:
                        return {"activation": {}, "events": [], "eligible": False,
                                "just_activated": False,
                                "reason": "ACTIVATION_ENTRY_MISSING"}
                    provider_ts = (ctx.get("provider_timestamp_utc")
                                   or ctx.get("market_context_fetched_at_utc"))
                    observed = entry.observe_market(
                        current_market_cap_usd=ctx.get("current_market_cap_usd"),
                        current_price=ctx.get("current_price"),
                        current_supply=ctx.get("supply_at_observation"),
                        provider_timestamp_utc=provider_ts,
                        observed_at_utc=now_iso_fn(),
                        observation_source=activation_observation_source,
                        max_age_seconds=activation_market_max_age_seconds,
                        central_ath=ctx.get("central_ath"),
                        pumpswap_reserve=ctx.get("pumpswap_reserve"),
                    )
                    if on_activation_event is not None:
                        for event in observed.get("events", []):
                            on_activation_event(event)
                    return observed

                def _send_time_refresh(
                    mint: str, ctx: Dict[str, Any]
                ) -> Optional[Dict[str, Any]]:
                    """ONE bounded priority market refresh for a send-ready candidate.

                    Only reached under a policy whose send-time refresh is
                    enabled; the sidecar owns the per-mint call budget and the
                    readiness tracker still owns every state transition, so a
                    failure simply leaves the candidate retained under its
                    existing bounded backoff.
                    """

                    del ctx
                    refresh_fn = getattr(sidecar, "priority_refresh", None)
                    if not callable(refresh_fn):
                        return None
                    entry = watchlist.get(mint)
                    return refresh_fn(
                        mint,
                        migration_time_utc=getattr(
                            entry, "migration_time_utc", None),
                        now_iso_fn=now_iso_fn,
                    )
                # Wrap the reserve/send boundary so a POST-reservation exception is attributed to a
                # send artifact (Blocker 6): every observed +1 ledger delta must be explained.
                engine_exc = None
                out = None
                try:
                    out = run_cap1_candidates_fn(
                        cand_dicts,
                        sidecar=sidecar,
                        ath_transport=ath_transport,
                        ath_endpoint_secret=ath_endpoint_secret,
                        now_utc=now_dt_fn(),
                        now_seconds=now_seconds,
                        now_iso_fn=now_iso_fn,
                        sleep_fn=sleep_fn,
                        ledger=ledger,
                        guard=guard,
                        authorization=authorization,
                        created_at_utc=now_iso_fn(),
                        pump_required=True,
                        alert_policy=_alert_policy,
                        policy_counters=_policy_counters,
                        send_time_refresh_fn=_send_time_refresh,
                        activation_gate_fn=_activation_gate,
                    )
                    # A SHADOW send-time fee recheck may replace the tick-bound
                    # decision on the mutable engine candidate.  Refresh the
                    # runner index before any send/candidate artifact is built.
                    for candidate in cand_dicts:
                        refreshed = candidate.get("security_decision")
                        refreshed_mint = candidate.get("token_mint")
                        if isinstance(refreshed, DeliverySafetyDecision) \
                                and isinstance(refreshed_mint, str):
                            security_results_by_mint[refreshed_mint] = refreshed
                except Exception as exc:
                    engine_exc = exc

                try:
                    lc_after = ledger_line_count_fn()
                except Exception:
                    # ledger recheck raised after a POSSIBLE reserve -> unknown; do NOT claim coverage.
                    ledger_state_known = False
                    if engine_exc is not None:
                        exc_type = type(engine_exc).__name__
                    stop_reason = STOP_LEDGER_RECHECK_FAILED
                    break

                cycle_delta = lc_after - lc_before

                if engine_exc is not None:
                    exc_type = type(engine_exc).__name__
                    if cycle_delta == 1:
                        # Codex Blocker 2: the engine raised BEFORE returning a sent_attempt, so the EXACT
                        # reserved candidate is NOT known. NEVER guess it from cand_dicts[0] (the engine
                        # may have skipped earlier candidates and reserved a later one). Record an explicit
                        # UNKNOWN-attribution artifact, fail closed, and do NOT claim coverage.
                        total_ledger_delta += 1
                        ok = _emit_send_artifact(
                            token_mint=None, candidate_id=None, cycle_delta_val=1, send_result=None,
                            market_context=None, exception_type=exc_type, reserved_candidate_known=False,
                            security_decision=None)
                        artifact_state_known = False     # attribution unverified -> coverage NOT claimed
                        stop_reason = (STOP_UNKNOWN_RESERVED_CANDIDATE if ok
                                       else STOP_ARTIFACT_WRITE_FAILED)
                        break
                    if cycle_delta == 0:
                        stop_reason = STOP_EXCEPTION_BEFORE_RESERVE
                        break
                    stop_reason = STOP_LEDGER_MISMATCH      # impossible delta after exception
                    break

                if cycle_delta not in (0, 1):
                    stop_reason = STOP_LEDGER_MISMATCH
                    break
                total_ledger_delta += cycle_delta
                try:
                    _mc = int(sidecar.stats().get("market_attempts_total", 0))
                    if market_scheduler is None:
                        market_calls += _mc
                    else:
                        # The persistent scheduler exposes cumulative counters;
                        # do not add that cumulative value once per watch tick.
                        market_calls = _mc
                    tick_obs["market_attempts_this_tick"] = _mc
                except Exception:
                    pass

                outcome = out.get("outcome") if isinstance(out, dict) else None
                per_cands = out.get("per_candidate", []) if isinstance(out, dict) else []
                # Per-tick no-send diagnostics (normalized reason token -> count) + below-LP-floor count.
                _reasons: Dict[str, int] = {}
                _below = 0
                for _rc in per_cands:
                    _r = str(_rc.get("reason", "")) if isinstance(_rc, dict) else ""
                    _key = _r.split(" ", 1)[0] if _r else "UNKNOWN"
                    _reasons[_key] = _reasons.get(_key, 0) + 1
                    if _r.startswith(LIQUIDITY_USD_BELOW_MIN_REASON):
                        _below += 1
                tick_obs["no_send_reasons"] = _reasons
                tick_obs["below_lp_floor_this_tick"] = _below
                # Pure read of engine results (NO external callbacks yet): the attempted candidate's
                # market context, used to enrich the send artifact.
                _ATTEMPT_REASONS = ("SENT_OK_COMMITTED", "SENT_OK_COMMIT_PENDING",
                                    "DELIVERY_FAILED_RETRYABLE", "DELIVERY_UNKNOWN")
                _ATTEMPT_OUTCOMES = ("ONE_SEND_COMMITTED", "ONE_SEND_COMMIT_PENDING",
                                     "ONE_SEND_FAILED_RETRYABLE", "ONE_SEND_UNKNOWN")
                sent_market_context: Optional[Dict[str, Any]] = None
                for rec in per_cands:
                    if rec.get("reason") in _ATTEMPT_REASONS:
                        sent_market_context = rec.get("market_context")

                send_result = None
                if outcome in _ATTEMPT_OUTCOMES:
                    # Ledger invariant under the delivery transaction: exactly one
                    # successful-send row for a COMMITTED delivery, zero rows for an
                    # explicit failure / ambiguous outcome / commit-pending receipt.
                    expected_delta = 1 if outcome == "ONE_SEND_COMMITTED" else 0
                    if cycle_delta != expected_delta:
                        stop_reason = STOP_ARTIFACT_LEDGER_INCONSISTENCY
                        break
                    sent_attempt = out.get("sent_attempt") or {}
                    send_result = sent_attempt.get("send_result")
                    delivery_info = sent_attempt.get("delivery") or {}
                    eligible = out.get("eligible_candidate") or {}
                    # Codex Blocker 2: attribute the attempt to the EXACT candidate the engine
                    # processed (from its sent_attempt / eligible_candidate) — NEVER the input
                    # order. If the engine reported an attempt but did not expose which
                    # candidate, fail closed with unknown attribution rather than guessing.
                    eligible_mint = eligible.get("token_mint")
                    if not (isinstance(eligible_mint, str) and eligible_mint):
                        total_ledger_delta_attribution_unknown = True  # noqa: F841 (documentary)
                        _emit_send_artifact(
                            token_mint=None, candidate_id=eligible.get("candidate_id"),
                            cycle_delta_val=cycle_delta, send_result=send_result,
                            market_context=sent_market_context, reserved_candidate_known=False,
                            security_decision=None, ledger_reserved=(cycle_delta == 1),
                            delivery_state=delivery_info.get("delivery_state"))
                        artifact_state_known = False
                        stop_reason = STOP_UNKNOWN_RESERVED_CANDIDATE
                        break
                    # Blocker 4: emit the attempt-bearing artifact BEFORE any fallible
                    # per-candidate callback / post-processing, so a +1 can never be orphaned.
                    ok = _emit_send_artifact(
                        token_mint=eligible_mint,
                        candidate_id=eligible.get("candidate_id"), cycle_delta_val=cycle_delta,
                        send_result=send_result, market_context=sent_market_context,
                        axiom_result=axiom_results_by_mint.get(eligible_mint),
                        security_decision=security_results_by_mint.get(eligible_mint),
                        ledger_reserved=(cycle_delta == 1),
                        delivery_state=delivery_info.get("delivery_state"))
                    if not ok:
                        artifact_state_known = False
                        stop_reason = STOP_ARTIFACT_WRITE_FAILED
                        break
                    if outcome == "ONE_SEND_COMMITTED":
                        sends += 1
                        last_send_monotonic = monotonic_fn()
                        tick_obs["sent_this_tick"] = 1
                        consecutive_transport_failures = 0
                    elif outcome == "ONE_SEND_FAILED_RETRYABLE":
                        consecutive_transport_failures += 1
                        tick_obs["delivery_failed_retryable_this_tick"] = 1
                else:
                    # ZERO_SEND: a +1 delta with no committed send would be unexplained
                    if cycle_delta != 0:
                        stop_reason = STOP_ARTIFACT_LEDGER_INCONSISTENCY
                        break

                # per-candidate recheck records + watchlist state update (FALLIBLE — wrapped so a +1 that
                # was already attributed above is never orphaned by a failing callback; TYPE only, no retry).
                try:
                    for rec in per_cands:
                        m = rec.get("token_mint", "")
                        reason = rec.get("reason", "")
                        entry = watchlist.get(m)
                        watchlist.record_recheck(
                            mint=m,
                            reason=reason,
                            observed_at_utc=now_iso_fn(),
                            market_state=rec.get("market_state"),
                            market_reason_code=rec.get("market_reason_code"),
                            next_market_refresh_at_utc=rec.get("next_market_refresh_at_utc"),
                            market_attempt_count=rec.get("market_attempt_count"),
                            delivery_state=rec.get("delivery_state"),
                            delivery_failure_reason=rec.get("delivery_failure_reason"),
                            delivery_next_retry_at_utc=rec.get("delivery_next_retry_at_utc"),
                            delivery_retry_count=rec.get("delivery_retry_count"),
                            delivery_attempt_id=rec.get("delivery_attempt_id"),
                            delivery_receipt_message_id=rec.get(
                                "delivery_receipt_message_id"),
                        )
                        sent = reason == "SENT_OK_COMMITTED"
                        attempted = reason in _ATTEMPT_REASONS
                        if on_candidate_record is not None:
                            # OBSERVE-ONLY: thread this candidate's Axiom verdict (decoded BEFORE the
                            # engine) so the per-candidate recheck artifact can carry the fee telemetry.
                            # Pure read of axiom_results_by_mint; does NOT affect eligibility/reserve/send.
                            candidate_kwargs = {
                                "rec": rec, "entry": entry, "cycle": ticks,
                                "observed_at_utc": now_iso_fn(),
                                "ledger_touched": bool(sent),
                                "transport_attempted": bool(attempted),
                                "axiom": axiom_results_by_mint.get(m),
                            }
                            security_decision = security_results_by_mint.get(m)
                            if isinstance(security_decision, DeliverySafetyDecision):
                                candidate_kwargs["security"] = security_decision
                            on_candidate_record(**candidate_kwargs)
                except Exception as exc:
                    exc_type = type(exc).__name__
                    stop_reason = (STOP_EXCEPTION_AFTER_RESERVE if cycle_delta == 1
                                   else STOP_EXCEPTION_BEFORE_RESERVE)
                    break

                if outcome in _ATTEMPT_OUTCOMES:
                    # secret-scan immediately after writing the send artifacts
                    if redaction_scan_fn is not None:
                        scan = redaction_scan_fn()
                        if scan_debounce.observe(
                                classify_redaction_scan(scan)):
                            redaction_ok = False
                            stop_reason = STOP_SECRET_SCAN_FAILURE
                            break

                    if outcome == "ONE_SEND_COMMIT_PENDING":
                        # Delivery confirmed (durable receipt) but the ledger
                        # commit did not complete: stop; restart reconciliation
                        # finishes the commit WITHOUT another transport call.
                        stop_reason = STOP_DELIVERY_COMMIT_INCOMPLETE
                        break
                    if outcome == "ONE_SEND_UNKNOWN":
                        # Ambiguous outcome: observable DELIVERY_UNKNOWN state;
                        # never silent success, never an uncontrolled duplicate.
                        # Operator reconciliation policy resolves it.
                        stop_reason = STOP_DELIVERY_UNKNOWN
                        break
                    if outcome == "ONE_SEND_FAILED_RETRYABLE" and (
                            consecutive_transport_failures
                            >= bounds.max_consecutive_transport_failures):
                        # Explicit failures retry under bounded per-candidate
                        # backoff; a SUSTAINED failure streak still stops.
                        stop_reason = STOP_TRANSPORT_ERROR
                        break
                    # ONE_SEND_COMMITTED (or a below-bound explicit failure):
                    # the run continues; a failed candidate stays active with
                    # its retry timestamp and is retried on a later tick.

            # expire stale entries (age / recheck hygiene; not a send cap)
            now_dt = now_dt_fn()
            # PHX1_PARITY extends the watch to six hours: PHX1 alerted on mints
            # PHX2 had already expired at 60 minutes.  A candidate is never
            # discarded merely because activation was not proven -- only age and
            # recheck hygiene terminate a watch, exactly as before.
            expired_entries = watchlist.expire_stale_entries(
                now_age_seconds_fn=lambda s, _n=now_dt: _age_seconds(_n, s),
                max_age_seconds=_watch_ttl,
                max_rechecks=bounds.max_rechecks_per_candidate,
                now_utc=now_iso_fn(),
            )
            if _parity_enabled:
                for _entry in watchlist.active_entries():
                    _entry_age = _age_seconds(now_dt, _entry.seeded_at_utc)
                    if _entry_age is None or _entry_age < LEGACY_WATCH_TTL_SECONDS:
                        continue
                    _mint = _entry.token_mint
                    if _mint not in _extended_watch_seen:
                        _extended_watch_seen.add(_mint)
                        _policy_count("extended_watch_candidates")
                    if (_entry.is_dip_active()
                            and _mint not in _reactivated_after_hour_seen):
                        _reactivated_after_hour_seen.add(_mint)
                        _policy_count("candidates_reactivated_after_one_hour")
            if on_activation_event is not None:
                for expired in expired_entries:
                    on_activation_event({
                        "kind": "PHX2_WATCHLIST_EVENT",
                        "event": "EXPIRED",
                        "token_mint": expired.token_mint,
                        "candidate_id": expired.candidate_id,
                        "observed_at_utc": now_iso_fn(),
                        "state": "EXPIRED",
                        "reason": expired.last_reason,
                    })
            checkpoint_write_tolerated_total += _finish_tick(watchlist, watch_state_path, on_cycle, ticks, sends, reseeds, stop_reason)
            if stop_requested_fn is not None and bool(stop_requested_fn()):
                stop_reason = STOP_OPERATOR_REQUESTED
                break
            # PHX2-E2E-006: wakeable inter-tick wait.  The configured
            # recheck interval is the MAXIMUM idle wait; a P1-relevant
            # scheduler event (tier entry, completed overview, handoff
            # arrival) ends it immediately so alert-time evaluation is not
            # quantized to the maintenance cadence.
            (tick_wait_fn or sleep_fn)(bounds.recheck_interval_seconds)

        except ProductionThrottleSignal:
            consecutive_throttles += 1
            if consecutive_throttles >= bounds.max_consecutive_throttles:
                stop_reason = STOP_THROTTLED
                break
            _backoff_sleep(sleep_fn, bounds, consecutive_throttles)
            continue
        except (KeyboardInterrupt, SystemExit):
            # Operator Ctrl+C (or a host SystemExit). NOT caught by ``except Exception`` (these are
            # BaseException). Stop GRACEFULLY so the accumulated result is returned and the session writes
            # the interrupted_* postflight. The ``finally`` below still fires this tick's heartbeat.
            interrupted = True
            stop_reason = STOP_OPERATOR_INTERRUPTED
            break
        except Exception as exc:  # any unexpected error -> safe stop (record TYPE only)
            exc_type = type(exc).__name__
            stop_reason = STOP_UNEXPECTED_EXCEPTION
            break
        finally:
            # ALWAYS emit this tick's heartbeat (every path: send / idle / throttle / break / interrupt)
            # and, on the flush cadence, a partial postflight snapshot. Pure observability: any error here
            # is swallowed so telemetry can NEVER break or alter the send path.
            if (on_heartbeat is not None and heartbeat_every_ticks
                    and ticks % heartbeat_every_ticks == 0):
                try:
                    on_heartbeat(_build_heartbeat(tick_obs))
                except Exception:
                    pass
            if (partial_flush_fn is not None and partial_flush_every_ticks
                    and ticks % partial_flush_every_ticks == 0):
                try:
                    partial_flush_fn(_build_result_dict(False))
                except Exception:
                    pass

    # Axiom mode facts (2026-06-22): observe-only by default; Axiom did NOT gate sends unless
    # require_axiom_pass. axiom_pass_count/axiom_fail_count are TELEMETRY counts only. An OPERATOR_
    # INTERRUPTED stop sets interrupted=True and outcome=INTERRUPTED (never a clean PASS).
    return _build_result_dict(interrupted)


def _backoff_sleep(sleep_fn: Callable[[float], None], bounds: ProductionBounds, n: int) -> None:
    delay = min(bounds.throttle_backoff_max_seconds,
                bounds.throttle_backoff_base_seconds * float(max(1, n)))
    sleep_fn(delay)


def _finish_tick(watchlist, watch_state_path, on_cycle, ticks, sends, reseeds, stop_reason) -> int:
    """Persist the watch checkpoint and emit the cycle callback.

    Returns the number of TOLERATED checkpoint-write failures (0 or 1). A
    transient Windows sharing-violation on the atomic replace under sustained
    live load is retried inside ``watchlist.persist`` and, if still unresolved,
    is tolerated here (counted, not propagated) so the tick loop never stops
    with UNEXPECTED_EXCEPTION. This mirrors the stream-cursor persist tolerance;
    the durable generation is preserved and the in-memory state is retried on
    the next tick (its unresolved status is surfaced via the watch checkpoint
    durability metrics). A genuinely permanent failure is likewise surfaced
    there rather than crashing the producer."""
    tolerated = 0
    if watch_state_path:
        try:
            watchlist.persist(watch_state_path)
        except (CheckpointWriteError, OSError):
            tolerated = 1
    if on_cycle is not None:
        on_cycle(tick=ticks, sends=sends, reseeds=reseeds, stop_reason=stop_reason,
                 summary=watchlist.summary())
    return tolerated


def production_postflight_verdict(result: Dict[str, Any]) -> Dict[str, Any]:
    """Pure verdict: a clean operator-boundary stop with a known, consistent, fully-explained ledger
    delta and no redaction violation -> exit 0. Every error/safety breaker -> nonzero. Mirrors the
    Build 31 postflight discipline (no auto-rerun; unknown ledger never invariant-safe)."""
    stop = result.get("stop_reason")
    ledger_known = bool(result.get("ledger_state_known"))
    artifact_known = bool(result.get("artifact_state_known", True))
    ledger_consistent = bool(result.get("ledger_consistent"))
    redaction_ok = bool(result.get("redaction_ok"))
    clean = stop in _CLEAN_STOPS
    ok = clean and ledger_known and artifact_known and ledger_consistent and redaction_ok
    return {
        "postflight_ok": bool(ok),
        "exit_code": 0 if ok else 3,
        "stop_reason": stop,
        "clean_stop": clean,
        "ledger_state_known": ledger_known,
        "artifact_state_known": artifact_known,
        "ledger_consistent": ledger_consistent,
        "redaction_ok": redaction_ok,
        "total_ledger_delta": result.get("total_ledger_delta"),
        "reserve_count": result.get("reserve_count"),
        "sent_ok_count": result.get("sent_ok_count"),
    }


__all__ = (
    "UNBOUNDED_RUNTIME_SECONDS", "runtime_bound_is_unbounded",
    "STOP_MAX_RUNTIME", "STOP_MARKET_BUDGET", "STOP_WATCHLIST_EMPTY", "STOP_TICK_BUDGET",
    "STOP_QUEUE_PRESSURE", "STOP_SOURCE_FAILURE", "STOP_THROTTLED", "STOP_UNKNOWN_LEDGER_STATE",
    "STOP_LEDGER_MISMATCH", "STOP_ARTIFACT_LEDGER_INCONSISTENCY", "STOP_TRANSPORT_ERROR",
    "STOP_DELIVERY_UNKNOWN", "STOP_DELIVERY_COMMIT_INCOMPLETE",
    "STOP_SECRET_SCAN_FAILURE", "STOP_UNEXPECTED_EXCEPTION", "STOP_EXCEPTION_AFTER_RESERVE",
    "STOP_EXCEPTION_BEFORE_RESERVE", "STOP_LEDGER_RECHECK_FAILED", "STOP_ARTIFACT_WRITE_FAILED",
    "STOP_LAX_AXIOM_CONFIG_REFUSED", "STOP_UNKNOWN_RESERVED_CANDIDATE",
    "STOP_OPERATOR_INTERRUPTED", "STOP_OPERATOR_REQUESTED",
    "ProductionThrottleSignal", "ProductionBounds", "sent_ok",
    "run_production_live_watch", "production_postflight_verdict",
    "MIN_LIQUIDITY_USD", "LIQUIDITY_USD_BELOW_MIN_REASON", "liquidity_floor_block_reason",
    "MAX_CONSECUTIVE_SCAN_READ_FAILURES", "SCAN_VERDICT_CLEAN",
    "SCAN_VERDICT_READ_ERROR_ONLY", "SCAN_VERDICT_UNSAFE",
    "classify_redaction_scan", "ScanFailureDebounce",
)
