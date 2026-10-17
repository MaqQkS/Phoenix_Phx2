"""Build 30 cap-1 forward-watch — bounded recheck-loop engine.

OUT-OF-REPO. The engine wraps the committed, audited ``run_cap1_candidates`` (one cap-1 pass:
pump gate -> market resolve -> compose [dedupe RESERVE-before-send] -> ONE guarded send of the
first eligible candidate, stop-after-one) in a bounded, interval-driven loop over a persistent
``Watchlist``. The send lineage is NOT reimplemented here; the engine only schedules rechecks and
records outcomes.

Safety invariants enforced by construction:
  * The ONLY ledger-mutating call is the injected ``run_cap1_candidates_fn`` reaching the committed
    compose reserve — which happens ONLY on the dispatch path. Rechecking an ineligible candidate
    composes to a non-dispatch decision and reserves nothing (ledger delta 0).
  * Stop-after-one: the loop breaks immediately on the first cycle that reports ONE_SEND_ATTEMPT,
    so at most one send attempt per ceremony (delta in {0, +1}).
  * No retry: a transport failure after reserve is surfaced (cap burned) and the loop still stops.
  * Fully injectable (sidecar/guard factories, clocks, ledger, transport) so the offline selftest
    drives it with fakes + a TEMP ledger and never touches the durable ledger / a socket / Discord.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class WatchBounds:
    recheck_interval_seconds: float = 90.0
    max_candidate_age_seconds: int = 3600
    max_rechecks_per_candidate: int = 30
    max_runtime_seconds: float = 7200.0
    max_watchlist_size: int = 64
    max_market_calls_total: int = 4096
    max_real_sends: int = 1


def _iso_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(now_dt: datetime, seeded_at: str) -> Optional[float]:
    try:
        s = datetime.fromisoformat(seeded_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        return (now_dt - s).total_seconds()
    except Exception:
        return None


def run_forward_watch(
    *,
    watchlist: Any,
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
    bounds: WatchBounds,
    run_cap1_candidates_fn: Callable[..., Dict[str, Any]],
    ledger_line_count_fn: Optional[Callable[[], int]] = None,
    on_candidate_record: Optional[Callable[..., None]] = None,
    on_cycle: Optional[Callable[..., None]] = None,
    watch_state_path: Optional[str] = None,
) -> Dict[str, Any]:
    sends = 0
    market_calls = 0
    cycles = 0
    start = monotonic_fn()
    stop_reason: Optional[str] = None
    sent_attempt: Optional[Dict[str, Any]] = None
    eligible_candidate: Optional[Dict[str, Any]] = None
    cycle_deltas: List[Optional[int]] = []

    while True:
        if monotonic_fn() - start >= bounds.max_runtime_seconds:
            stop_reason = "MAX_RUNTIME"
            break
        if sends >= bounds.max_real_sends:
            stop_reason = "MAX_SENDS"
            break
        if market_calls >= bounds.max_market_calls_total:
            stop_reason = "MARKET_BUDGET"
            break
        active = watchlist.active_entries()
        if not active:
            stop_reason = "WATCHLIST_EMPTY"
            break

        cycles += 1
        now_dt = now_dt_fn()
        created_at = _iso_dt(now_dt)
        sidecar = sidecar_factory(cycles)
        guard = guard_factory()
        lc_before = ledger_line_count_fn() if ledger_line_count_fn else None

        cand_dicts = [e.to_candidate() for e in active]
        out = run_cap1_candidates_fn(
            cand_dicts,
            sidecar=sidecar,
            ath_transport=ath_transport,
            ath_endpoint_secret=ath_endpoint_secret,
            now_utc=now_dt,
            now_seconds=now_seconds,
            now_iso_fn=now_iso_fn,
            sleep_fn=sleep_fn,
            ledger=ledger,
            guard=guard,
            authorization=authorization,
            created_at_utc=created_at,
            pump_required=True,
        )

        lc_after = ledger_line_count_fn() if ledger_line_count_fn else None
        cycle_delta = (lc_after - lc_before) if (lc_before is not None and lc_after is not None) else None
        cycle_deltas.append(cycle_delta)

        for rec in out.get("per_candidate", []):
            mint = rec.get("token_mint", "")
            reason = rec.get("reason", "")
            entry = watchlist.get(mint)
            watchlist.record_recheck(mint=mint, reason=reason, observed_at_utc=created_at)
            sent = reason in ("SEND_ATTEMPTED", "SENT_OK_COMMITTED")
            # Per-candidate ledger_touched reflects the dispatch path (reserve-before-send ⇒ a send
            # attempt implies the key was reserved). The AUTHORITATIVE ledger movement is the
            # ceremony-level baseline delta (computed by the caller after the run).
            if on_candidate_record is not None:
                on_candidate_record(
                    rec=rec, entry=entry, cycle=cycles, observed_at_utc=created_at,
                    ledger_touched=bool(sent), transport_attempted=bool(sent),
                )

        try:
            market_calls += int(sidecar.stats().get("market_attempts_total", 0))
        except Exception:
            pass

        if out.get("outcome") in ("ONE_SEND_ATTEMPT", "ONE_SEND_COMMITTED",
                                  "ONE_SEND_COMMIT_PENDING",
                                  "ONE_SEND_FAILED_RETRYABLE", "ONE_SEND_UNKNOWN"):
            sends += 1
            sent_attempt = out.get("sent_attempt")
            eligible_candidate = out.get("eligible_candidate")
            stop_reason = "SEND_ATTEMPTED"
            if on_cycle is not None:
                on_cycle(cycle=cycles, outcome=out.get("outcome"),
                         cycle_delta=cycle_delta, summary=watchlist.summary())
            break  # stop-after-one (ceremony level)

        watchlist.expire_stale(
            now_age_seconds_fn=lambda s, _n=now_dt: _age_seconds(_n, s),
            max_age_seconds=bounds.max_candidate_age_seconds,
            max_rechecks=bounds.max_rechecks_per_candidate,
        )
        if on_cycle is not None:
            on_cycle(cycle=cycles, outcome=out.get("outcome"),
                     cycle_delta=cycle_delta, summary=watchlist.summary())
        if watch_state_path:
            watchlist.persist(watch_state_path)
        sleep_fn(bounds.recheck_interval_seconds)

    return {
        "sends": sends,
        "cycles": cycles,
        "market_calls": market_calls,
        "stop_reason": stop_reason,
        "sent_attempt": sent_attempt,
        "eligible_candidate": eligible_candidate,
        "cycle_deltas": cycle_deltas,
        "watchlist_summary": watchlist.summary(),
    }


__all__ = ("WatchBounds", "run_forward_watch")
