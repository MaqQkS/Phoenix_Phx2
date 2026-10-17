from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_session as session
from PHX2.free_tier_producer import paid_provider as provider_module
from PHX2.free_tier_producer.compat.build30_watchlist import Watchlist
from PHX2.free_tier_producer.compat.production_live_runner import (
    ProductionBounds,
    seed_discovered_candidates,
)
from PHX2.free_tier_producer.paid_provider import (
    PROVIDER_MODE_FREE_TIER,
    PROVIDER_MODE_PAID_PRIMARY,
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)


MINT = "ABCDEFGH1234567890pump"


def event(*, mint=MINT, event_id="event-1", observed="2026-07-16T06:42:00Z"):
    return SimpleNamespace(
        base_mint=mint,
        mint=mint,
        pool_account="pool",
        pool_program_id="program",
        quote_mint="quote",
        event_id=event_id,
        provider_event_id=event_id,
        observed_at_utc=observed,
        raw_event_hash="hash",
    )


def discovery(events=None, now=None):
    records = events if events is not None else []
    clock = now if now is not None else {"value": 100.0}
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: None,
        dedupe=ProviderCandidateDedupe(),
        now_fn=lambda: clock["value"],
        event_sink=records.append,
    )
    return owner, records, clock


def test_decoded_accepted_candidate_enters_provider_queue_once():
    owner, records, _ = discovery()
    owner._handle_event(event())
    snapshot = owner.snapshot()
    assert snapshot["candidates_decoded"] == 1
    assert snapshot["candidates_accepted"] == 1
    assert snapshot["queue_depth"] == 1
    assert [row["event"] for row in records].count("CANDIDATE_ENQUEUED") == 1


def test_production_consumer_drains_exact_queue_instance():
    owner, _, _ = discovery()
    queue_identity = id(owner._queue)
    owner._handle_event(event())
    drained = owner.drain()
    assert id(owner._queue) == queue_identity
    assert [candidate["token_mint"] for candidate in drained] == [MINT]


def test_dequeue_occurs_once_and_queue_depth_decreases():
    owner, records, clock = discovery()
    owner._handle_event(event())
    clock["value"] = 100.8
    assert len(owner.drain()) == 1
    assert owner.drain() == []
    assert owner.snapshot()["queue_depth"] == 0
    dequeues = [row for row in records if row["event"] == "CANDIDATE_DEQUEUED"]
    assert len(dequeues) == 1
    assert dequeues[0]["queue_age_seconds"] == 0.8


def test_runner_records_received_and_watchlist_acknowledgment():
    watchlist = Watchlist(max_size=4)
    events = []
    seed_discovered_candidates(
        watchlist=watchlist,
        candidates=[{"token_mint": MINT, "candidate_id": "candidate", "migration_time_utc": "2026-07-16T06:42:00Z", "source_ref": "grpc"}],
        seeded_at_utc="2026-07-16T06:42:01Z",
        on_handoff_event=events.append,
    )
    assert [row["event"] for row in events] == ["RUNNER_RECEIVED", "WATCHLIST_ACKNOWLEDGED"]
    assert events[-1]["admission"] == "ADDED"
    assert len(watchlist.active_entries()) == 1


def test_watchlist_rejection_is_explicit():
    watchlist = Watchlist(max_size=1)
    watchlist.seed({"token_mint": MINT}, seeded_at_utc="2026-07-16T06:42:00Z")
    other = "ZYXWVUTS9876543210pump"
    events = []
    seed_discovered_candidates(
        watchlist=watchlist,
        candidates=[{"token_mint": other, "candidate_id": "other"}],
        seeded_at_utc="2026-07-16T06:42:01Z",
        on_handoff_event=events.append,
    )
    assert events[-1]["event"] == "WATCHLIST_REJECTED"
    # PHX2-E2E-002: a full ACTIVE watchlist rejects with the explicit
    # capacity reason plus the counts an operator needs to see it.
    assert events[-1]["reason"] == "ACTIVE_WATCH_CAPACITY_REACHED"
    assert events[-1]["active_count"] == 1
    assert events[-1]["active_capacity"] == 1


def test_duplicate_candidate_is_suppressed_without_second_enqueue():
    owner, records, _ = discovery()
    owner._handle_event(event())
    owner._handle_event(event())
    assert owner.snapshot()["queue_depth"] == 1
    assert [row["event"] for row in records].count("CANDIDATE_ENQUEUED") == 1
    assert any(row["event"] == "DUPLICATE_EVENT" for row in records)


def test_duplicate_mint_with_new_event_is_suppressed():
    owner, records, _ = discovery()
    owner._handle_event(event(event_id="one"))
    owner._handle_event(event(event_id="two"))
    assert owner.snapshot()["queue_depth"] == 1
    assert any(row["event"] == "DUPLICATE_MINT" for row in records)


def test_malformed_candidate_remains_blocked():
    owner, records, _ = discovery()
    malformed = event()
    malformed.base_mint = None
    owner._handle_event(malformed)
    assert owner.snapshot()["queue_depth"] == 0
    assert any(row["event"] == "MALFORMED_EVENT" for row in records)


def test_non_pump_candidate_remains_blocked():
    owner, records, _ = discovery()
    owner._handle_event(event(mint="NotAPumpMint"))
    assert owner.snapshot()["queue_depth"] == 0
    assert any(row["event"] == "NON_PUMP_DROPPED" for row in records)


def test_handoff_artifact_failure_becomes_visible_and_fails_closed():
    def fail(_record):
        raise OSError("withheld")

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: None,
        dedupe=ProviderCandidateDedupe(),
        event_sink=fail,
    )
    owner._handle_event(event())
    snapshot = owner.snapshot()
    assert snapshot["handoff_artifact_errors"] > 0
    assert session.paid_provider_safety_error(snapshot, max_reconnects=5) == "PAID_PROVIDER_HANDOFF_ARTIFACT_FAILURE"


def test_paid_queue_handoff_cadence_is_bounded_to_watch_tick():
    bounds = ProductionBounds(recheck_interval_seconds=45, reseed_interval_seconds=240)
    effective = session._bounds_with_provider_handoff_cadence(bounds, PROVIDER_MODE_PAID_PRIMARY)
    assert effective.reseed_interval_seconds == 45
    assert effective.recheck_interval_seconds == 45


def test_free_tier_reseed_cadence_is_unchanged():
    bounds = ProductionBounds(recheck_interval_seconds=45, reseed_interval_seconds=240)
    assert session._bounds_with_provider_handoff_cadence(bounds, PROVIDER_MODE_FREE_TIER) is bounds


def test_provider_state_is_constructed_once_outside_discovery_callback():
    path = Path(session.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    run_producer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_producer")
    constructions = [
        node for node in ast.walk(run_producer)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "SingleGrpcPumpSwapDiscovery"
    ]
    discovery_fn = next(node for node in ast.walk(run_producer) if isinstance(node, ast.FunctionDef) and node.name == "discovery_fn")
    nested_constructions = [
        node for node in ast.walk(discovery_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "SingleGrpcPumpSwapDiscovery"
    ]
    # One mutually exclusive construction site exists for each authoritative
    # source family (Helius and legacy Chainstack).  Runtime source-mode
    # selection reaches exactly one of them; neither is constructed per
    # discovery callback.
    assert len(constructions) == 2
    assert nested_constructions == []


def test_start_is_idempotent_and_does_not_create_second_owner_thread(monkeypatch):
    threads = []

    class FakeThread:
        def __init__(self, **kwargs):
            self.alive = False
            threads.append(self)

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.alive = False

    monkeypatch.setattr(provider_module.threading, "Thread", FakeThread)
    owner, _, _ = discovery()
    owner.start()
    owner.start()
    assert len(threads) == 1


def test_central_ath_payload_is_not_mutated_during_runner_handoff():
    central = {"ath_market_cap": "42100", "ath_provider": "GRPC_EVENT"}
    candidate = {"token_mint": MINT, "candidate_id": "candidate", "central_ath": central}
    watchlist = Watchlist(max_size=2)
    seed_discovered_candidates(
        watchlist=watchlist,
        candidates=[candidate],
        seeded_at_utc="2026-07-16T06:42:01Z",
    )
    assert candidate["central_ath"] is central
    assert central == {"ath_market_cap": "42100", "ath_provider": "GRPC_EVENT"}


def test_observer_imports_no_provider_and_causes_no_network_request():
    from PHX2.observability import operator_console

    tree = ast.parse(Path(operator_console.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("paid_provider" in name or "paid_grpc" in name for name in imported)
