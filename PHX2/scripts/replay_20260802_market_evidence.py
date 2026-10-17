"""Offline replay of the preserved 2026-08-02 five-hour run evidence.

Runs the PRESERVED production evidence back through the REAL production
classes -- :class:`MarketScheduler`, :class:`MarketPhysicalRequestMeter`,
:class:`MarketPlaneWatch`, the migration-proof admission predicate and the
credit budget -- with no live provider, no Telegram, no ledger write and no
production state directory touched.

The replay is an A/B: the same evidence, the same candidates and the same
recorded provider responses are driven twice, once under the configuration
that actually ran (a finite 5,000 lifetime market budget charged at DEQUEUE)
and once under the remediated configuration (UNBOUNDED, charged at PHYSICAL
dispatch).  That is what makes the result a proof rather than an assertion.

HONESTY CONTRACT.  The provider stand-in serves ONLY observations that exist
in the preserved artifacts.  For a mint with no recorded observation it
returns an explicit ``NO_RECORDED_PROVIDER_OBSERVATION`` refusal -- never a
synthesized price, market cap or liquidity value.  That matters here more than
usual, because the defect under repair is precisely the one that stopped those
observations from ever being captured: 15 of the 16 in-window parity mints
carry zero market values across 1,891 recorded evaluations.  Manufacturing
them would make the replay pass by erasing the evidence of the bug.

Usage (offline, read-only):

    python -m PHX2.scripts.replay_20260802_market_evidence [--run-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer.market_budget import (
    MARKET_REQUEST_CAP_UNBOUNDED,
    MarketPhysicalRequestMeter,
)
from PHX2.free_tier_producer.market_plane_health import (
    MARKET_PLANE_BLIND,
    MarketPlaneConfig,
    MarketPlaneWatch,
    classify as classify_market_plane,
)
from PHX2.free_tier_producer.market_scheduler import (
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    MARKET_PROVIDER_BUDGET_EXHAUSTED,
    CandidateScheduleView,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    SOURCE_PAID_SINGLE,
)
from PHX2.watchdog.operational_health import (
    SCHEDULER_STARVATION_BOUND_SECONDS,
)

DEFAULT_RUN_DIR = (
    r"C:\Users\BalaC\phx2_paid_primary_runtime\runs"
    r"\paid_primary_live_24x7_20260802T160009Z")

#: The market budget was exhausted here, ~22 minutes after launch.
BUDGET_EXHAUSTED_UTC = "2026-08-02T16:22:56Z"

#: In-window PHX1 parity mints that alerted before PHX2 was stopped.
IN_WINDOW_PARITY_MINTS: Tuple[Tuple[str, str], ...] = (
    ("vrsz", "Ar9yvmE83HH29cfA4aVUA5ijPFmGeBjZSY5gxAyHpump"),
    ("interlocution", "7F85i7PjD8etYPhzphcnmbd3J38voA13y1qm48vhpump"),
    ("cwg", "9S2RuYGv5vcKBYmaRFiCteg3YxBdCEejZytt1RdHpump"),
    ("Hitler", "9pPYeCgueHKoESoLi1pgcZ8dUy9TwD5zQUeCLLCDpump"),
    ("SPIDERCAT", "FApJRRBFdzgQrJYKxmA29ufcDMzsPSajxMGXcDSkpump"),
    ("PT", "GfyVVfTSm1YTiuBH6EDAstGY3u9eoBF2HDQoRJaspump"),
    ("Beanos", "6iUD5CMY3fx2hrsHtAGrdpyF3N9Jx2G8tdwjb19Mpump"),
    ("JAMES", "4CnFLDYxD2ZYH8GcXiNGtT5NYRo2qhvX1Cgg89Cjpump"),
    ("GOONER", "J92DV8wqCUALdU36at4TZW4Gb49ea17hHRxmWB9apump"),
    ("ZUCC", "4dK65AHdS2rmqgS6svPRg8NnEZ9iq5YjXwRkgCAjpump"),
    ("Aura", "CXb71YBmVkWF9FLUkis4BrMboraywEya9sKJECAspump"),
    ("AURACAT", "6wfbCEwBDE8D75QaQCSgawiNfKwJDCyAYA32F768pump"),
    ("Greyson", "6HeVncC64XUFVSFzG1mDtZYXxEePx5gQj34oS7JDpump"),
    ("AUSTIN", "ETXSe9qbMbsWqrWTgLxCGoHxacMcwxBigYbsFrnBpump"),
    ("SHIBA", "55pPZ7b6FHFWprkmaJNK6qDgxipYdfD8rkMgqkxfpump"),
    ("RAYS", "uUSQ3e65NPaLMjeBbdPZdDabvRPLBfSmVDThL6ypump"),
)

#: Alerted in PHX1 six seconds AFTER the PHX2 stop marker. Replayable as a
#: discovery/processing case; explicitly NOT an in-window live parity miss.
OUT_OF_WINDOW_LABEL = "BROKER"

NO_RECORDED_OBSERVATION = "NO_RECORDED_PROVIDER_OBSERVATION"

NOW = 1_785_690_000.0


# --------------------------------------------------------------------------- #
# evidence loading (read-only)
# --------------------------------------------------------------------------- #

def _iter_jsonl(path: str):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue


def load_evidence(run_dir: str) -> Dict[str, Dict[str, Any]]:
    """Collect every preserved fact this replay is allowed to use."""

    wanted = {mint: label for label, mint in IN_WINDOW_PARITY_MINTS}
    evidence: Dict[str, Dict[str, Any]] = {
        label: {"mint": mint, "proof": None, "watch": None,
                "market": None, "ath": None, "parity": []}
        for label, mint in IN_WINDOW_PARITY_MINTS
    }

    for record in _iter_jsonl(os.path.join(run_dir, "migration_proofs.jsonl")):
        label = wanted.get(str(record.get("candidate_mint") or ""))
        if label and evidence[label]["proof"] is None:
            evidence[label]["proof"] = record

    for record in _iter_jsonl(os.path.join(run_dir, "watch_state.jsonl")):
        label = wanted.get(str(record.get("token_mint") or ""))
        if label:
            evidence[label]["watch"] = record

    for record in _iter_jsonl(
            os.path.join(run_dir, "phx2_ping_quality_review.jsonl")):
        label = wanted.get(str(record.get("mint") or ""))
        if not label:
            continue
        # The FIRST row that actually carries provider values is the only
        # thing this replay may serve as a market observation.
        if evidence[label]["market"] is None \
                and record.get("current_price_usd") is not None \
                and record.get("current_market_cap_usd") is not None:
            evidence[label]["market"] = record

    for record in _iter_jsonl(
            os.path.join(run_dir, "phx1_shadow_candidates.jsonl")):
        label = wanted.get(str(record.get("token_mint") or ""))
        if label:
            evidence[label]["parity"].append(record)

    ath_path = os.path.join(run_dir, "ath_state.json")
    if os.path.exists(ath_path):
        try:
            with open(ath_path, encoding="utf-8") as handle:
                mints = (json.load(handle) or {}).get("mints") or {}
        except (ValueError, OSError):
            mints = {}
        for label, mint in IN_WINDOW_PARITY_MINTS:
            evidence[label]["ath"] = mints.get(mint)

    return evidence


# --------------------------------------------------------------------------- #
# recorded-evidence provider (never fabricates)
# --------------------------------------------------------------------------- #

class RecordedEvidenceProvider:
    """Serves ONLY market values preserved in the run artifacts.

    Every call that reaches this object is a real physical dispatch and is
    recorded on the shared meter, exactly as the live transport would.  A mint
    with no recorded observation yields an explicit refusal; nothing is
    invented to make a candidate progress.
    """

    def __init__(self, evidence: Mapping[str, Dict[str, Any]],
                 meter: MarketPhysicalRequestMeter) -> None:
        self._by_mint: Dict[str, Optional[Dict[str, Any]]] = {}
        for label, row in evidence.items():
            self._by_mint[str(row["mint"])] = row.get("market")
        self._meter = meter
        self._binding: Dict[str, Tuple[str, int]] = {}
        self.price_calls: List[str] = []
        self.overview_calls: List[str] = []
        self.refusals: Dict[str, int] = {}

    def bind(self, mint: str, candidate_id: str, generation: int) -> None:
        """Bind the scheduler's candidate identity so replayed observations
        carry the SAME mint/candidate/generation triple the real path
        enforces. A mismatch is rejected by apply_observation, exactly as it
        would be live."""

        self._binding[mint] = (candidate_id, int(generation))

    def _observation(self, mint: str, field_group: str, sequence: int,
                     values: Mapping[str, Any]) -> MarketObservation:
        candidate_id, generation = self._binding.get(mint, (mint, 1))
        return MarketObservation(
            mint=mint,
            candidate_id=candidate_id,
            generation=generation,
            source=SOURCE_PAID_SINGLE,
            source_timestamp=NOW,
            ingestion_timestamp=NOW,
            field_group=field_group,
            observation_sequence=sequence,
            source_evidence_digest=hashlib.sha256(
                f"{mint}:{field_group}:{sequence}".encode()).hexdigest(),
            request_id=f"replay-{field_group}-{sequence}",
            values=values,
        )

    def _refuse(self, mint: str) -> Dict[str, Any]:
        self.refusals[mint] = self.refusals.get(mint, 0) + 1
        return {"_market_failure_reason": NO_RECORDED_OBSERVATION}

    def fetch_price(self, mint: str, **_kwargs: Any) -> Any:
        self._meter.record_physical("/defi/price")
        self.price_calls.append(mint)
        row = self._by_mint.get(mint)
        if not row:
            return self._refuse(mint)
        return self._observation(
            mint, FIELD_PRICE_MC, 1,
            {"current_price": str(row.get("current_price_usd")),
             "current_market_cap_usd": str(row.get("current_market_cap_usd"))})

    def fetch_overview(self, mint: str, **_kwargs: Any) -> Any:
        self._meter.record_physical("/defi/token_overview")
        self.overview_calls.append(mint)
        row = self._by_mint.get(mint)
        if not row or row.get("liquidity_usd") is None:
            return self._refuse(mint)
        return self._observation(
            mint, FIELD_OVERVIEW, 2,
            {"current_market_cap_usd": str(row.get("current_market_cap_usd")),
             "liquidity_usd": str(row.get("liquidity_usd"))})


class FakeDelivery:
    """In-memory delivery. Reserves, 'sends' and records -- touches nothing."""

    def __init__(self) -> None:
        self.reservations: List[str] = []
        self.sent: List[str] = []

    def reserve(self, mint: str) -> str:
        key = f"fake-reservation:{mint}"
        self.reservations.append(key)
        return key

    def send(self, mint: str) -> str:
        self.sent.append(mint)
        return "SENT_OK_COMMITTED"


# --------------------------------------------------------------------------- #
# replay stages
# --------------------------------------------------------------------------- #

def _view_for(label: str, row: Mapping[str, Any]) -> CandidateScheduleView:
    watch = row.get("watch") or {}
    proof = row.get("proof") or {}
    return CandidateScheduleView(
        mint=str(row["mint"]),
        candidate_id=str(watch.get("candidate_id")
                         or proof.get("migration_signature") or label),
        generation=1,
        status=str(watch.get("status") or "PENDING_BASELINE"),
        seeded_at_epoch=NOW - 60.0,
        market_state=None,
        last_observed_epoch=None,
        next_recovery_epoch=None,
        activation_target_market_cap_usd=(
            str(watch.get("activation_target_market_cap_usd"))
            if watch.get("activation_target_market_cap_usd") else None),
        last_activation_market_cap_usd=None,
        delivery_retry_due=False,
        quarantined=False,
        terminal_history=False,
    )


def _drain(scheduler: MarketScheduler, provider: RecordedEvidenceProvider,
           jobs) -> None:
    """Dispatch each planned job exactly as the worker loop would."""

    for job in jobs:
        with scheduler._ticket_ownership(job):
            if job.field_group == FIELD_PRICE_MC:
                result = provider.fetch_price(job.mints[0])
            else:
                result = provider.fetch_overview(job.mints[0])
        scheduler._charge_job_tickets(job)
        scheduler._consume_result(job, result, None)


def replay_scheduler(evidence: Mapping[str, Dict[str, Any]], *,
                     unbounded: bool) -> Dict[str, Any]:
    """One full pass of the 16 candidates through the REAL scheduler."""

    meter = MarketPhysicalRequestMeter()
    provider = RecordedEvidenceProvider(evidence, meter)
    budget = (MARKET_REQUEST_CAP_UNBOUNDED if unbounded else 5000)
    scheduler = MarketScheduler(
        price_fetch_fn=provider.fetch_price,
        overview_fetch_fn=provider.fetch_overview,
        config=MarketSchedulerConfig(provider_request_budget=budget),
        now_fn=lambda: NOW,
        monotonic_fn=time.monotonic,
        physical_request_meter=meter,
    )
    if not unbounded:
        # Reproduce the live state at 16:22:56Z: the lifetime budget is gone,
        # and under the old accounting it can never come back.
        scheduler._scheduler_physical_requests = 5000
        scheduler._provider_requests_started = 5000

    views = [_view_for(label, row) for label, row in evidence.items()]
    for view in views:
        provider.bind(view.mint, view.candidate_id, view.generation)
    scheduler.update_candidates(views)
    planned = scheduler.plan(enqueue=True)
    _drain(scheduler, provider, planned)

    stats = scheduler.stats()
    per_mint: Dict[str, Dict[str, Any]] = {}
    for label, row in evidence.items():
        mint = str(row["mint"])
        snapshot = scheduler.snapshot(mint) or {}
        has_evidence = row.get("market") is not None
        per_mint[label] = {
            "mint": mint,
            "migration_proof_admitted": bool(row.get("proof")),
            "recorded_market_observation": has_evidence,
            "price_requests_issued": provider.price_calls.count(mint),
            "overview_requests_issued": provider.overview_calls.count(mint),
            "provider_refusals": provider.refusals.get(mint, 0),
            "current_price": snapshot.get("current_price"),
            "current_market_cap_usd": snapshot.get("current_market_cap_usd"),
            "liquidity_usd": snapshot.get("liquidity_usd"),
            "all_present": bool(snapshot.get("all_present")),
            "projected_tier": snapshot.get("projected_tier"),
        }
    return {
        "mode": "UNBOUNDED" if unbounded else "BOUNDED_5000_EXHAUSTED",
        "planned_jobs": len(planned),
        "budget_exhausted_degraded": (
            MARKET_PROVIDER_BUDGET_EXHAUSTED
            in stats["market_scheduler_degraded_reasons"]),
        "scheduler_physical_requests_total": stats[
            "scheduler_physical_requests_total"],
        "transport_physical_requests_total": stats[
            "transport_physical_requests_total"],
        "unreconciled_delta": stats["unreconciled_delta"],
        "market_budget_mode": stats["market_budget_mode"],
        "per_mint": per_mint,
    }


def replay_market_plane() -> Dict[str, Any]:
    """Replay the run's real timeline through the bounded-grace watch."""

    watch = MarketPlaneWatch(MarketPlaneConfig())
    first_blind_at: Optional[float] = None
    verdict = None
    # 16:00:09Z launch, exhaustion at ~T+22m, operator stop at ~T+5h.  One
    # sample per minute.  Before exhaustion the plane is healthy and every
    # priority refresh is served; after it, refreshes keep being attempted at
    # the run's real rate (~51/min) and NONE are served -- which is exactly
    # what the 15,523 rejections over 4h38m look like.
    refreshes_served = 0
    refresh_attempts = 0
    for minute in range(0, 300):
        exhausted = minute >= 22
        refresh_attempts += 51
        if not exhausted:
            refreshes_served += 51
        verdict = watch.observe(
            now_monotonic=float(minute * 60),
            active_candidates=12,
            budget_exhausted=exhausted,
            starved_age_seconds=(float((minute - 22) * 60) if exhausted else 1.0),
            starvation_bound_seconds=SCHEDULER_STARVATION_BOUND_SECONDS,
            successful_refresh_total=refreshes_served,
            priority_refresh_attempts_total=refresh_attempts,
            priority_refresh_served_total=refreshes_served,
            max_observation_age_seconds=(
                float((minute - 22) * 60) if exhausted else 5.0),
        )
        if verdict.status == MARKET_PLANE_BLIND and first_blind_at is None:
            first_blind_at = float(minute)
    should_stop, reason = classify_market_plane(verdict)
    return {
        "first_blind_at_minutes_after_launch": first_blind_at,
        "final_status": verdict.status,
        "final_reasons": list(verdict.reasons),
        "fail_closed_requested": should_stop,
        "fail_closed_reason": reason,
        "silent_minutes_before": 278,   # exhaustion at T+22m, stop at T+300m
        "silent_minutes_after": (
            None if first_blind_at is None else int(first_blind_at - 22)),
    }


def replay_delivery(evidence: Mapping[str, Dict[str, Any]],
                    unbounded_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Fake reservation + SENT_OK for anything that reaches eligibility."""

    delivery = FakeDelivery()
    outcomes: Dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="phx2_replay_") as tmp:
        ledger = os.path.join(tmp, "fake_ledger.jsonl")
        for label, row in unbounded_result["per_mint"].items():
            if not row["all_present"]:
                outcomes[label] = "NO_FAKE_DELIVERY_MARKET_INCOMPLETE"
                continue
            ath = (evidence[label].get("ath") or {}).get("ath_hydration") or {}
            if ath.get("resolved_ath_market_cap") is None:
                # HARD gate under PHX1_PARITY: no coherent resolved ATH, no
                # tier, no send. Correctly refused, not a defect.
                outcomes[label] = "NO_FAKE_DELIVERY_ATH_COVERAGE_INCOMPLETE"
                continue
            delivery.reserve(row["mint"])
            result = delivery.send(row["mint"])
            with open(ledger, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"mint": row["mint"],
                                         "result": result}) + "\n")
            outcomes[label] = result
    return {
        "fake_reservations": len(delivery.reservations),
        "fake_sent_ok": len(delivery.sent),
        "real_ledger_touched": False,
        "telegram_attempts": 0,
        "outcomes": outcomes,
    }


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def build_report(run_dir: str) -> Dict[str, Any]:
    evidence = load_evidence(run_dir)
    bounded = replay_scheduler(evidence, unbounded=False)
    unbounded = replay_scheduler(evidence, unbounded=True)
    plane = replay_market_plane()
    delivery = replay_delivery(evidence, unbounded)

    with_evidence = [label for label, row in evidence.items()
                     if row.get("market") is not None]
    progressed = [label for label, row in unbounded["per_mint"].items()
                  if row["all_present"]]
    in_scope_ok = (len(progressed) / len(with_evidence)) if with_evidence else 0.0

    return {
        "kind": "PHX2_REPLAY_20260802_MARKET_EVIDENCE",
        "run_dir": run_dir,
        "budget_exhausted_utc": BUDGET_EXHAUSTED_UTC,
        "candidates_replayed": len(evidence),
        "candidates_with_recorded_market_observation": with_evidence,
        "candidates_without_recorded_market_observation": [
            label for label in evidence if label not in with_evidence],
        "bounded_replay": bounded,
        "unbounded_replay": unbounded,
        "market_plane_replay": plane,
        "fake_delivery": delivery,
        "in_scope_progression_rate": in_scope_ok,
        "out_of_window_note": (
            f"{OUT_OF_WINDOW_LABEL} alerted in PHX1 six seconds after the PHX2 "
            "stop marker; replayed as a discovery/processing case only and NOT "
            "counted as an in-window live parity miss."),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.run_dir):
        print(f"[refused] run directory not found: {args.run_dir}")
        return 2

    report = build_report(args.run_dir)
    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 0

    bounded = report["bounded_replay"]
    unbounded = report["unbounded_replay"]
    print("PHX2 OFFLINE REPLAY — preserved 2026-08-02 five-hour evidence")
    print(f"  run dir: {report['run_dir']}")
    print(f"  candidates replayed: {report['candidates_replayed']}")
    print(f"  with recorded market observation: "
          f"{len(report['candidates_with_recorded_market_observation'])}")
    print()
    print("A/B THROUGH THE REAL MarketScheduler")
    for result in (bounded, unbounded):
        print(f"  [{result['mode']}]")
        print(f"    planned jobs                  : {result['planned_jobs']}")
        print(f"    BUDGET_EXHAUSTED degraded     : "
              f"{result['budget_exhausted_degraded']}")
        print(f"    scheduler physical requests   : "
              f"{result['scheduler_physical_requests_total']}")
        print(f"    transport physical requests   : "
              f"{result['transport_physical_requests_total']}")
        print(f"    unreconciled delta            : "
              f"{result['unreconciled_delta']}")
    print()
    print("PER-MINT (UNBOUNDED replay)")
    header = (f"  {'MINT':16}{'proof':>6}{'obs':>5}{'px_req':>7}{'ov_req':>7}"
              f"{'present':>8}  {'tier':<8}outcome")
    print(header)
    for label, row in unbounded["per_mint"].items():
        outcome = report["fake_delivery"]["outcomes"].get(label, "-")
        print(f"  {label:16}{str(row['migration_proof_admitted']):>6}"
              f"{str(row['recorded_market_observation']):>5}"
              f"{row['price_requests_issued']:>7}"
              f"{row['overview_requests_issued']:>7}"
              f"{str(row['all_present']):>8}  "
              f"{str(row['projected_tier'] or '-'):<8}{outcome}")
    print()
    plane = report["market_plane_replay"]
    print("MARKET-PLANE FAIL-CLOSED REPLAY")
    print(f"  first BLIND at T+{plane['first_blind_at_minutes_after_launch']}m "
          f"(budget died at T+22m)")
    print(f"  final status   : {plane['final_status']}")
    print(f"  fail closed    : {plane['fail_closed_requested']} "
          f"({plane['fail_closed_reason']})")
    print(f"  silent minutes : {plane['silent_minutes_before']} before "
          f"-> {plane['silent_minutes_after']} after")
    print()
    delivery = report["fake_delivery"]
    print("FAKE DELIVERY")
    print(f"  reservations={delivery['fake_reservations']} "
          f"sent_ok={delivery['fake_sent_ok']} "
          f"telegram_attempts={delivery['telegram_attempts']} "
          f"real_ledger_touched={delivery['real_ledger_touched']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
