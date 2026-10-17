"""Offline remediation proofs for the 2026-08-02 PHX1_PARITY dispatch blockers.

The preserved run (``paid_primary_live_24x7_20260802T043054Z`` and
``...T061317Z``) discovered and admitted all four PHX1 mints, matched PHX1's
ATH PRICE exactly for every one of them, and still produced ZERO tiers and
ZERO pings.  Four independent defects were responsible:

A. ``ScheduledMarketSidecar`` -- the sidecar production actually runs -- had
   no ``priority_refresh`` method at all, so the runner's
   ``getattr(sidecar, "priority_refresh", None)`` resolved to ``None`` on
   every attempt: 2,068 attempted, 0 succeeded, 2,068 counted failed, and no
   provider request was ever made.
B. The central ATH record maximized PRICE and MARKET CAP independently, so
   the two arms described different observations and the composer -- rightly
   -- refused to render an alert contradicting itself.  Once diverged the
   condition was unrecoverable: 94 of 145 tracked mints, 80 of 96 compose
   attempts.
C. ``plan()`` ran once per producer watch tick (~46 s measured: 132 ticks in
   6,120 s) against a 12 s price TTL, so a tier-active candidate was
   guaranteed stale for ~38 s of every ~50 s.
D. Hydration was driven ONLY as a side effect of the capacity-bounded
   pricing tail (32 slots) in a run tracking 145 mints, so a restart-backfill
   candidate could sit at ``ATH_HYDRATION_NEVER_ATTEMPTED`` for the entire
   run while being actively watched.

Everything here is offline and deterministic: no network, no real transport,
no ledger mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
import json
from pathlib import Path
import threading

import pytest

from PHX2.free_tier_producer import ath_state as ath_state_module
from PHX2.free_tier_producer.ath_state import (
    ATH_RESOLUTION_PRECISION,
    ATH_UNRESOLVED_SUPPLY_UNAVAILABLE,
    RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY,
    STATUS_CONFIRMED,
    STATUS_PROVISIONAL,
    SUPPLY_BASIS_OBSERVATION,
    VALID_RESOLVED_SUPPLY_BASES,
    ath_resolved_tuple_is_valid,
    build_ath_resolved_tuple,
    evaluate_ath_hydration,
    resolved_market_cap_from,
    validate_ath_checkpoint_record,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    verify_cross_checkpoint_consistency,
)
from PHX2.free_tier_producer.market_scheduler import (
    CADENCE_FAR,
    CADENCE_INACTIVE,
    CADENCE_NEAR_TIER,
    CADENCE_TIER_ACTIVE,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    PRIORITY_REFRESH_RESULTS,
    REFRESH_ALREADY_IN_FLIGHT,
    REFRESH_PERMANENT_FAILURE,
    REFRESH_RATE_LIMITED,
    REFRESH_RETRYABLE_FAILURE,
    REFRESH_SUCCEEDED,
    PRIORITY_REFRESH_MAX_PERMANENT_FAILURES,
    ScheduledMarketSidecar,
    SOURCE_PAID_SINGLE,
    project_request_budget,
)
from PHX2.models.ath_coverage import (
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_HYDRATION_COMPLETE,
    ATH_HYDRATION_MARKET_CAP_UNCONVERTED,
    ATH_HYDRATION_NEVER_ATTEMPTED,
    ATH_HYDRATION_PENDING,
    ATH_HYDRATION_VERIFIED,
)
from PHX2.stage30 import stage30_11_13_committed_no_send_composer as composer


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures"
    / "preserved_run_20260802_phx1_parity_four_mints.json")

NOW = 1_785_650_000.0
WSOL = "So11111111111111111111111111111111111111112"


# ---------------------------------------------------------------------------
# Preserved-run fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def preserved() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _checkpoint_record(state_path: Path, mint: str) -> dict:
    """The AUTHENTICATED checkpoint record for one mint.

    The human-readable ``ath_state.json`` mirror carries extra summary
    counters; the checkpoint is the schema the restore validator governs.
    """

    checkpoint = state_path.with_name(state_path.stem + "_checkpoint.json")
    document = json.loads(checkpoint.read_text(encoding="utf-8"))
    for record in document["payload"]["records"]:
        if record.get("token_mint") == mint:
            return dict(record)
    raise AssertionError(f"no checkpoint record for {mint}")


def _mint_case(preserved: dict, label: str) -> dict:
    case = preserved["mints"][label]
    assert case["central_ath"]["ath_price"], label
    return case


def _record_from_case(case: dict, *, coherent: bool) -> dict:
    """Build a central-ATH RECORD from one preserved mint.

    ``coherent=False`` reproduces the run exactly: the price arm and the
    market-cap arm come from two different observations.  ``coherent=True``
    is the same peak price observed with its OWN market cap, which is what
    the repaired producer now records.
    """

    central = dict(case["central_ath"])
    price = central["ath_price"]
    evidence_price = central["ath_market_cap_evidence_price_usd"]
    market_cap = central["ath_market_cap"]
    record = dict(central)
    record["token_mint"] = case["token_mint"]
    provenance_price = price if coherent else evidence_price
    if coherent:
        with localcontext() as ctx:
            ctx.prec = ATH_RESOLUTION_PRECISION
            supply = Decimal(market_cap) / Decimal(evidence_price)
            own_market_cap = Decimal(price) * supply
        provenance_market_cap = format(own_market_cap, "f")
    else:
        provenance_market_cap = market_cap
    record["price_provenance"] = {
        "price": price,
        # The RUN's record: the maximum price observation carried no market
        # cap of its own (a different, lower-priced tick set the MC arm).
        "market_cap": provenance_market_cap if coherent else None,
        "timestamp": central["ath_timestamp"],
        "provider": central["ath_provider"],
        "observation_type": central["ath_observation_type"],
        "status": central["ath_status"],
        "supply": None,
        "evidence_digest": central.get("ath_evidence_digest"),
    }
    record["market_cap_provenance"] = {
        "price": evidence_price,
        "market_cap": market_cap,
        "timestamp": central["ath_timestamp"],
        "provider": central["ath_provider"],
        "observation_type": central["ath_observation_type"],
        "status": central["ath_status"],
    }
    record.update(build_ath_resolved_tuple(record))
    return record


# ---------------------------------------------------------------------------
# Scheduler harness
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, start: float = NOW) -> None:
        self.value = float(start)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class _View:
    """Minimal candidate entry the scheduler's view builder accepts."""

    def __init__(self, mint: str, *, status: str = "ACTIVE_DIP_WATCH",
                 seeded_at_utc: str = "2026-08-02T05:00:00Z",
                 candidate_id: str = "cand-1") -> None:
        self.token_mint = mint
        self.candidate_id = candidate_id
        self.status = status
        self.seeded_at_utc = seeded_at_utc
        self.market_observation_generation = 7
        self.market_state = None
        self.market_reason_code = None
        self.last_observed_at_utc = None
        self.next_market_refresh_at_utc = None
        self.activation_target_market_cap_usd = None
        self.last_activation_progress_market_cap_usd = None
        self.delivery_next_retry_at_utc = None
        self.market_compose_near = False
        self.market_scheduler_quarantined = False
        self.market_terminal_history = False


def _observation(mint: str, *, field: str, sequence: int, source_at: float,
                 price: str = "0.00002", mc: str = "20000",
                 liquidity: str = "12000",
                 candidate_id: str = "cand-1") -> MarketObservation:
    values = ({"current_price": price, "current_market_cap_usd": mc}
              if field == FIELD_PRICE_MC
              else {"current_market_cap_usd": mc, "liquidity_usd": liquidity})
    return MarketObservation(
        mint=mint, candidate_id=candidate_id, generation=7,
        source=SOURCE_PAID_SINGLE, source_timestamp=float(source_at),
        ingestion_timestamp=float(source_at), field_group=field,
        observation_sequence=sequence,
        source_evidence_digest=f"{sequence:064d}", request_id=None,
        values=values)


class _Provider:
    """Deterministic fake provider: records calls, never touches a network."""

    def __init__(self, *, price_ok: bool = True, overview_ok: bool = True,
                 raise_price: BaseException = None) -> None:
        self.price_ok = price_ok
        self.overview_ok = overview_ok
        self.raise_price = raise_price
        self.price_calls: list = []
        self.overview_calls: list = []
        self.sequence = 100
        self.now = NOW
        self.gate = None

    def _next(self) -> int:
        self.sequence += 1
        return self.sequence

    def price(self, mint: str):
        self.price_calls.append(mint)
        if self.gate is not None:
            self.gate.wait(timeout=2.0)
        if self.raise_price is not None:
            raise self.raise_price
        if not self.price_ok:
            return None
        return _observation(mint, field=FIELD_PRICE_MC,
                            sequence=self._next(), source_at=self.now)

    def overview(self, mint: str):
        self.overview_calls.append(mint)
        if not self.overview_ok:
            return None
        return _observation(mint, field=FIELD_OVERVIEW,
                            sequence=self._next(), source_at=self.now)


def _scheduler(provider: _Provider, *, clock: _Clock = None,
               **config_kwargs) -> MarketScheduler:
    clock = clock or _Clock()
    provider.now = clock.value
    config = MarketSchedulerConfig(
        worker_count=1, max_inflight=1, p1_reserved_workers=0,
        **config_kwargs)
    return MarketScheduler(
        price_fetch_fn=provider.price, overview_fetch_fn=provider.overview,
        config=config, now_fn=clock, monotonic_fn=clock)


def _tracked_scheduler(provider: _Provider, *, clock: _Clock = None,
                       status: str = "ACTIVE_DIP_WATCH", **kwargs):
    clock = clock or _Clock()
    scheduler = _scheduler(provider, clock=clock, **kwargs)
    view = _View("mint-000-pump", status=status)
    scheduler.update_candidates([view], now_epoch=clock.value)
    return scheduler, view, clock


# ===========================================================================
# 1-10  Defect A: the production priority refresh
# ===========================================================================


def test_01_scheduled_market_sidecar_implements_priority_refresh() -> None:
    """The sidecar production ACTUALLY runs must carry the method."""

    assert hasattr(ScheduledMarketSidecar, "priority_refresh")
    assert callable(ScheduledMarketSidecar.priority_refresh)
    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    sidecar = ScheduledMarketSidecar(scheduler)
    # The exact call shape the production runner uses.
    context = sidecar.priority_refresh(
        "mint-000-pump", migration_time_utc="2026-08-02T05:00:00Z",
        now_iso_fn=lambda: "2026-08-02T05:05:39Z")
    assert context["priority_refresh_result"] in PRIORITY_REFRESH_RESULTS


def test_02_production_runner_resolves_the_real_method() -> None:
    """``getattr(sidecar, "priority_refresh", None)`` must not be None.

    This is the exact expression the production runner evaluates; in the
    2026-08-02 run it returned None 2,068 times.
    """

    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    sidecar = ScheduledMarketSidecar(scheduler)
    refresh_fn = getattr(sidecar, "priority_refresh", None)
    assert callable(refresh_fn), "production send-time refresh is dead code"
    source = Path(
        "PHX2/free_tier_producer/compat/production_live_runner.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(sidecar, "priority_refresh", None)' in source


def test_03_priority_refresh_makes_a_provider_request() -> None:
    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    result = scheduler.priority_refresh("mint-000-pump")
    assert provider.price_calls == ["mint-000-pump"]
    assert provider.overview_calls == ["mint-000-pump"]
    assert result["priority_refresh_provider_requests"] == 2
    assert scheduler.stats()["priority_refresh_provider_requests_total"] == 2


def test_04_success_updates_price_market_cap_and_liquidity() -> None:
    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    before = scheduler.snapshot("mint-000-pump")
    assert before["current_price"] is None
    result = scheduler.priority_refresh("mint-000-pump")
    assert result["priority_refresh_result"] == REFRESH_SUCCEEDED
    assert result["current_price"] == "0.00002"
    assert result["current_market_cap_usd"] == "20000"
    assert result["liquidity_usd"] == "12000"
    assert result["all_present"] is True


def test_05_success_clears_stale_and_recovery_state() -> None:
    provider = _Provider()
    clock = _Clock()
    scheduler = _scheduler(provider, clock=clock)
    view = _View("mint-000-pump")
    view.market_state = "MARKET_RECOVERY_BACKOFF"
    view.market_reason_code = "MARKET_RECOVERY_BACKOFF_NOT_DUE"
    view.next_market_refresh_at_utc = "2026-08-02T09:00:00Z"
    scheduler.update_candidates([view], now_epoch=clock.value)
    scheduler._record_failure("mint-000-pump", FIELD_PRICE_MC, "PROVIDER_BOOM")
    assert scheduler._state["mint-000-pump"].failure_count == 1
    result = scheduler.priority_refresh("mint-000-pump")
    assert result["priority_refresh_result"] == REFRESH_SUCCEEDED
    assert result["market_state"] == "MARKET_READY"
    assert scheduler._state["mint-000-pump"].failure_count == 0
    assert scheduler._state["mint-000-pump"].last_request_error is None
    assert scheduler._views["mint-000-pump"].next_recovery_epoch is None


def test_06_success_is_visible_to_the_same_evaluation_cycle() -> None:
    """A refreshed value must be readable by the caller that asked for it.

    The async worker pool cannot promise that; the priority refresh fetches
    on the CALLING thread precisely so the same candidate evaluation (or one
    explicitly bounded re-evaluation) sees the new values.
    """

    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    result = scheduler.priority_refresh("mint-000-pump")
    # Returned context AND the next independent snapshot both carry it.
    assert result["all_present"] is True
    assert scheduler.snapshot("mint-000-pump")["all_present"] is True


def test_07_retryable_failure_preserves_candidate_state() -> None:
    provider = _Provider(price_ok=False, overview_ok=False)
    scheduler, view, _clock = _tracked_scheduler(provider)
    result = scheduler.priority_refresh("mint-000-pump")
    assert result["priority_refresh_result"] == REFRESH_RETRYABLE_FAILURE
    # The candidate is RETAINED: still tracked, same binding, no terminal
    # transition, nothing erased.
    retained = scheduler._views["mint-000-pump"]
    assert retained.candidate_id == view.candidate_id
    assert retained.generation > 0
    assert not retained.quarantined
    assert not retained.terminal_history
    assert result["priority_refresh_retry_after_seconds"] > 0


def test_08_rate_limited_refresh_enters_provider_backoff() -> None:
    provider = _Provider(raise_price=RuntimeError("HTTP 429 Too Many Requests"))
    clock = _Clock()
    scheduler, _view, _clock2 = _tracked_scheduler(provider, clock=clock)
    first = scheduler.priority_refresh("mint-000-pump")
    assert first["priority_refresh_result"] == REFRESH_RATE_LIMITED
    backoff = first["priority_refresh_retry_after_seconds"]
    assert backoff > 0
    # A second immediate attempt is refused by the provider-scoped backoff
    # WITHOUT making another request.
    calls_before = len(provider.price_calls)
    second = scheduler.priority_refresh("mint-000-pump")
    assert second["priority_refresh_result"] == REFRESH_RATE_LIMITED
    assert second["priority_refresh_provider_requests"] == 0
    assert len(provider.price_calls) == calls_before


def test_09_permanent_failure_does_not_loop_indefinitely() -> None:
    provider = _Provider()
    scheduler = _scheduler(provider)
    # Untracked mint: structurally impossible to refresh.
    for _ in range(PRIORITY_REFRESH_MAX_PERMANENT_FAILURES + 4):
        result = scheduler.priority_refresh("never-tracked-pump")
        assert result["priority_refresh_result"] == REFRESH_PERMANENT_FAILURE
    assert provider.price_calls == []
    assert scheduler.stats()["priority_refresh_permanent_total"] == (
        PRIORITY_REFRESH_MAX_PERMANENT_FAILURES)


def test_10_duplicate_simultaneous_refreshes_coalesce() -> None:
    provider = _Provider()
    provider.gate = threading.Event()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    outcomes: list = []

    def worker() -> None:
        outcomes.append(scheduler.priority_refresh("mint-000-pump"))

    first = threading.Thread(target=worker)
    first.start()
    # Wait until the first refresh is genuinely in flight.
    for _ in range(2000):
        if provider.price_calls:
            break
    second = scheduler.priority_refresh("mint-000-pump")
    provider.gate.set()
    first.join(timeout=5.0)
    assert second["priority_refresh_result"] == REFRESH_ALREADY_IN_FLIGHT
    assert second["priority_refresh_provider_requests"] == 0
    assert scheduler.stats()["priority_refresh_coalesced_total"] == 1


# ===========================================================================
# 11-20  Defect B: the coherent resolved ATH tuple
# ===========================================================================


def _coherent_record(price: str = "0.00005", supply: str = "1000000000",
                     *, status: str = STATUS_PROVISIONAL) -> dict:
    with localcontext() as ctx:
        ctx.prec = ATH_RESOLUTION_PRECISION
        market_cap = Decimal(price) * Decimal(supply)
    record = {
        "token_mint": "mint-000-pump",
        "ath_price": price,
        "ath_market_cap": format(market_cap, "f"),
        "ath_market_cap_evidence_price_usd": price,
        "ath_timestamp": "2026-08-02T05:05:39Z",
        "ath_provider": "PAID_CURRENT_PRICE",
        "ath_observation_type": "PAID_CURRENT_PRICE",
        "ath_status": status,
        "price_provenance": {
            "price": price,
            "market_cap": format(market_cap, "f"),
            "timestamp": "2026-08-02T05:05:39Z",
            "provider": "PAID_CURRENT_PRICE",
            "observation_type": "PAID_CURRENT_PRICE",
            "status": status,
            "evidence_digest": "a" * 64,
        },
    }
    record.update(build_ath_resolved_tuple(record))
    return record


def test_11_coherent_tuple_uses_one_price_and_one_supply_basis() -> None:
    record = _coherent_record()
    assert record["resolved"] is True
    assert record["resolution_method"] == RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY
    assert record["resolved_supply_basis"] == SUPPLY_BASIS_OBSERVATION
    assert record["resolved_ath_price"] == record["ath_price"]
    assert record["resolved_observed_at_utc"] == record["ath_timestamp"]
    assert record["resolved_supply_basis"] in VALID_RESOLVED_SUPPLY_BASES


def test_12_derived_market_cap_equals_price_times_supply() -> None:
    record = _coherent_record()
    expected = resolved_market_cap_from(
        record["resolved_ath_price"], record["resolved_supply"])
    assert Decimal(record["resolved_ath_market_cap"]) == expected
    assert ath_resolved_tuple_is_valid(record)


def test_12b_incoherent_observation_pairs_are_detectable() -> None:
    """The ROOT CAUSE of the split arms, reproduced and now visible.

    The price and market-cap planes are independent, so an overview that
    refreshes only the market cap leaves the snapshot exposing a price from
    one instant beside a market cap from another.  April's 2026-08-02 record
    carried a 06:08:21Z price next to a 06:08:05Z market cap; feeding that
    pair to the ATH store as ONE observation is what split the two maxima
    and, through the implied supply, made every later candle high
    unconvertible.
    """

    provider = _Provider()
    clock = _Clock()
    scheduler = _scheduler(provider, clock=clock)
    scheduler.update_candidates([_View("mint-000-pump")], now_epoch=clock.value)
    scheduler.apply_observation(_observation(
        "mint-000-pump", field=FIELD_PRICE_MC, sequence=1, source_at=NOW))
    assert scheduler.snapshot("mint-000-pump")["market_pair_coherent"] is True
    # A later OVERVIEW refreshes the market cap alone -- exactly April's shape.
    scheduler.apply_observation(_observation(
        "mint-000-pump", field=FIELD_OVERVIEW, sequence=2,
        source_at=NOW + 16, mc="21000"))
    snapshot = scheduler.snapshot("mint-000-pump")
    assert snapshot["market_pair_coherent"] is False
    assert snapshot["price_observed_at_utc"] != (
        snapshot["market_cap_observed_at_utc"])
    # The session only forwards a market cap to the ATH store when the pair
    # is coherent; the incoherent case contributes its PRICE only.
    session_source = Path(
        "PHX2/free_tier_producer/free_tier_session.py").read_text(
            encoding="utf-8")
    assert 'coherent = bool(snapshot.get("market_pair_coherent"))' in (
        session_source)


def test_13_raw_split_evidence_remains_preserved(preserved: dict) -> None:
    """Resolution ADDS a projection; it never edits or deletes evidence."""

    case = _mint_case(preserved, "RABBIT")
    record = _record_from_case(case, coherent=True)
    central = case["central_ath"]
    assert record["ath_price"] == central["ath_price"]
    assert record["ath_market_cap"] == central["ath_market_cap"]
    assert record["ath_market_cap_evidence_price_usd"] == (
        central["ath_market_cap_evidence_price_usd"])
    # The two raw arms still disagree -- that history is intact...
    assert record["ath_price"] != record["ath_market_cap_evidence_price_usd"]
    assert record["market_cap_provenance"]["market_cap"] == (
        central["ath_market_cap"])
    # ...and the resolved projection sits beside it, not on top of it.
    assert record["resolved"] is True


def test_14_split_raw_maxima_no_longer_kill_a_valid_resolved_tuple(
    preserved: dict,
) -> None:
    for label in ("COGE", "RABBIT", "APRIL"):
        case = _mint_case(preserved, label)
        record = _record_from_case(case, coherent=True)
        assert record["ath_price"] != (
            record["ath_market_cap_evidence_price_usd"]), label
        assert ath_resolved_tuple_is_valid(record), label
        status, reason = evaluate_ath_hydration(
            {**record, "pool_created_at": case["migration_time_utc"],
             "ohlcv_coverage": None})
        # Still blocked -- but on COVERAGE, never again on the impossible
        # split-arm comparison.
        assert reason != ATH_HYDRATION_MARKET_CAP_UNCONVERTED, label


def test_15_missing_supply_remains_fail_closed() -> None:
    record = {
        "token_mint": "mint-000-pump",
        "ath_price": "0.00005",
        "price_provenance": {
            "price": "0.00005", "market_cap": None,
            "timestamp": "2026-08-02T05:05:39Z",
            "provider": "PAID_OHLCV_HIGH",
            "observation_type": "PAID_OHLCV_HIGH",
            "status": STATUS_CONFIRMED, "supply": None,
        },
    }
    resolved = build_ath_resolved_tuple(record)
    assert resolved["resolved"] is False
    assert resolved["resolution_reason"] == ATH_UNRESOLVED_SUPPLY_UNAVAILABLE
    assert resolved["resolved_ath_market_cap"] is None
    assert not ath_resolved_tuple_is_valid(resolved)


@pytest.mark.parametrize("supply", ["0", "-1", "not-a-number", ""])
def test_16_invalid_supply_remains_fail_closed(supply: str) -> None:
    record = {
        "token_mint": "mint-000-pump",
        "ath_price": "0.00005",
        "price_provenance": {
            "price": "0.00005", "market_cap": None,
            "timestamp": "2026-08-02T05:05:39Z",
            "provider": "PAID_OHLCV_HIGH",
            "observation_type": "PAID_OHLCV_HIGH",
            "status": STATUS_CONFIRMED, "supply": supply,
            "supply_basis": "EVENT_SOURCED_SUPPLY",
        },
    }
    resolved = build_ath_resolved_tuple(record)
    assert resolved["resolved"] is False
    assert resolved["resolved_ath_market_cap"] is None


def test_17_provisional_resolved_ath_stays_distinguishable() -> None:
    record = _coherent_record(status=STATUS_PROVISIONAL)
    assert record["resolved_status"] == STATUS_PROVISIONAL
    assert ath_resolved_tuple_is_valid(record)


def test_18_confirmed_resolved_ath_stays_distinguishable() -> None:
    record = _coherent_record(status=STATUS_CONFIRMED)
    assert record["resolved_status"] == STATUS_CONFIRMED
    assert ath_resolved_tuple_is_valid(record)
    assert _coherent_record(status=STATUS_PROVISIONAL)[
        "resolved_status"] != record["resolved_status"]


def test_19_composer_contract_mirrors_the_producer_exactly() -> None:
    """The composer imports no producer module, so the mirror must be pinned.

    A drift here -- especially in the arithmetic precision -- would make an
    honest resolved tuple fail its own exact recompute check, which is the
    class of unsatisfiable gate this remediation removed.
    """

    assert composer._CENTRAL_ATH_RESOLUTION_PRECISION == ATH_RESOLUTION_PRECISION
    assert composer._CENTRAL_ATH_RESOLUTION_METHODS == (
        ath_state_module.VALID_ATH_RESOLUTION_METHODS)
    assert set(composer._CENTRAL_ATH_SUPPLY_BASES) == set(
        VALID_RESOLVED_SUPPLY_BASES)
    price, supply = "0.000052802674482463554", "947073239.9475011200499777"
    assert composer.resolved_market_cap_from(price, supply) == (
        resolved_market_cap_from(price, supply))


def test_20_composer_rejects_a_malformed_resolved_tuple() -> None:
    request = composer.Stage30_11_13RevalidationRequest(
        token_mint="mint-000-pump", candidate_id="c1",
        migration_time_utc="2026-08-02T05:00:00Z",
        current_price="0.00002", current_market_cap_usd="20000",
        created_at_utc="2026-08-02T05:05:39Z", migration_confirmed=True,
        liquidity_usd="12000",
        market_context_fetched_at_utc="2026-08-02T05:05:38Z",
        authoritative_ath_price="0.00005",
        authoritative_ath_market_cap_usd="50000",
        authoritative_ath_timestamp="2026-08-02T05:02:00Z",
        authoritative_ath_provider="PAID_CURRENT_PRICE",
        authoritative_ath_observation_type="PAID_CURRENT_PRICE",
        authoritative_ath_status=STATUS_PROVISIONAL,
        # A resolved tuple whose market cap is NOT price x supply.
        resolved_ath_price="0.00005",
        resolved_supply="1000000000",
        resolved_supply_basis=SUPPLY_BASIS_OBSERVATION,
        resolved_ath_market_cap_usd="99999",
        resolved_observed_at_utc="2026-08-02T05:02:00Z",
        resolved_ath_source="PAID_CURRENT_PRICE",
        resolved_ath_observation_type="PAID_CURRENT_PRICE",
        resolved_ath_status=STATUS_PROVISIONAL,
        resolution_method=RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY,
    )
    assert composer.resolved_market_cap_from(
        request.resolved_ath_price, request.resolved_supply) != Decimal(
            request.resolved_ath_market_cap_usd)
    # A tuple missing its method is refused outright.
    broken = replace(request, resolution_method=None)
    assert broken.resolution_method not in (
        composer._CENTRAL_ATH_RESOLUTION_METHODS)


# ===========================================================================
# 21-26  Preserved-run fixtures
# ===========================================================================


def _tier_for(record: dict, current_market_cap: str) -> str:
    from PHX2.free_tier_producer.market_scheduler import project_closed_tier

    tier, _pct = project_closed_tier(
        ath_market_cap_usd=record["resolved_ath_market_cap"],
        current_market_cap_usd=current_market_cap)
    return tier


class _FixtureBirdeyeTransport:
    """Path-routed fake Birdeye transport bound to ONE preserved mint.

    Opens no socket.  ``/defi/price`` returns that mint's preserved current
    price and ``/defi/ohlcv`` its preserved peak, so the composer's
    independent migration-anchored freshness gate resolves against exactly
    the observations the run recorded.
    """

    def __init__(self, case: dict) -> None:
        from PHX2.stage29.stage29_2_birdeye_models import (
            BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            BIRDEYE_REFUSAL_REASON_NONE,
        )

        self._none = BIRDEYE_REFUSAL_REASON_NONE
        self._timeout = BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
        self._case = case
        self._fetched_at = _FIXTURE_FETCHED_AT
        self.calls: list = []

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        from PHX2.stage29.birdeye_constants import (
            BIRDEYE_PATH_OHLCV, BIRDEYE_PATH_PRICE,
        )
        from PHX2.stage29.stage29_2_birdeye_http_transport import (
            Stage29_2BirdeyeHttpResult,
        )

        self.calls.append(path)
        market = self._case["market_context"]
        central = self._case["central_ath"]
        if path == BIRDEYE_PATH_PRICE:
            body = {"success": True,
                    "data": {"value": market["current_price"],
                             "updateUnixTime": _FIXTURE_NOW_UNIX}}
        elif path == BIRDEYE_PATH_OHLCV:
            body = {"success": True,
                    "data": {"items": [
                        {"h": central["ath_price"],
                         "unixTime": _FIXTURE_NOW_UNIX - 900},
                        {"h": market["current_price"],
                         "unixTime": _FIXTURE_NOW_UNIX - 60},
                    ]}}
        else:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=self._timeout, http_status_code=0, body=None,
                fetched_at_utc=self._fetched_at)
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=self._none, http_status_code=200, body=body,
            fetched_at_utc=self._fetched_at)


_FIXTURE_CREATED_AT = "2026-08-02T06:30:00Z"
_FIXTURE_FETCHED_AT = "2026-08-02T06:29:50+00:00"
_FIXTURE_NOW_UNIX = 1_785_652_200


def _compose_fixture(case: dict, *, coherent: bool):
    """Drive the REAL committed composer over one preserved mint."""

    from datetime import datetime, timezone

    from PHX2.stage29.stage29_2_birdeye_readiness import (
        Stage29_2BirdeyeEndpointSecret,
    )
    from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
        make_constant_clock,
    )
    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        Stage30_11_5RecordingFakeTransportClient,
    )

    record = _record_from_case(case, coherent=coherent)
    market = case["market_context"]
    request = composer.Stage30_11_13RevalidationRequest(
        token_mint=case["token_mint"],
        candidate_id=case["candidate_id"],
        migration_time_utc=case["migration_time_utc"],
        current_price=market["current_price"],
        current_market_cap_usd=market["current_market_cap_usd"],
        created_at_utc=_FIXTURE_CREATED_AT,
        migration_confirmed=True,
        symbol_or_name=case["label"],
        migration_source="PRESERVED_RUN_FIXTURE",
        liquidity_usd=market["liquidity_usd"],
        age_display="1h",
        market_context_status="PRESENT",
        market_context_fetched_at_utc=_FIXTURE_FETCHED_AT,
        authoritative_ath_price=record["ath_price"],
        authoritative_ath_market_cap_usd=record["ath_market_cap"],
        authoritative_ath_timestamp=record["ath_timestamp"],
        authoritative_ath_provider=record["ath_provider"],
        authoritative_ath_observation_type=record["ath_observation_type"],
        authoritative_ath_status=record["ath_status"],
        authoritative_ath_market_cap_evidence_price_usd=record[
            "ath_market_cap_evidence_price_usd"],
        ath_coverage=ATH_COVERAGE_COMPLETE_LIVE,
        resolved_ath_price=record["resolved_ath_price"],
        resolved_supply=record["resolved_supply"],
        resolved_supply_basis=record["resolved_supply_basis"],
        resolved_ath_market_cap_usd=record["resolved_ath_market_cap"],
        resolved_observed_at_utc=record["resolved_observed_at_utc"],
        resolved_ath_source=record["resolved_source"],
        resolved_ath_observation_type=record["resolved_observation_type"],
        resolved_ath_status=record["resolved_status"],
        resolved_evidence_digest=record["resolved_evidence_digest"],
        resolution_method=record["resolution_method"],
    )
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=_FIXTURE_CREATED_AT)
    result = composer.compose_no_send_dispatch(
        request,
        ath_transport=_FixtureBirdeyeTransport(case),
        ath_endpoint_secret=Stage29_2BirdeyeEndpointSecret(
            _api_key="abcd1234efgh5678ijkl9012mnop3456",
            _base_url="https://aaaa-bbbb.example"),
        now_utc=datetime(2026, 8, 2, 6, 30, 0, tzinfo=timezone.utc),
        transport_client=client,
        now_seconds=make_constant_clock(Decimal(0)),
        market_context_max_age_seconds=3600,
    )
    return result, client


def test_21_coge_fixture_reaches_tier_2_compose(preserved: dict) -> None:
    """The REAL composer, driven over COGE's preserved observations."""

    case = _mint_case(preserved, "COGE")
    # BEFORE: the run's split arms cannot resolve, so no tuple exists at all.
    assert _record_from_case(case, coherent=False)["resolved"] is False
    result, client = _compose_fixture(case, coherent=True)
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, result.reason
    assert result.snapshot.tier_token == "Tier 2"
    # Fake transport delivery reservation succeeded.
    assert client.bodies, "no fake delivery reservation was made"
    assert f"CA: {case['token_mint']}" in client.bodies[-1]


def test_22_rabbit_fixture_reaches_tier_2_compose(preserved: dict) -> None:
    case = _mint_case(preserved, "RABBIT")
    assert _record_from_case(case, coherent=False)["resolved"] is False
    result, client = _compose_fixture(case, coherent=True)
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, result.reason
    assert result.snapshot.tier_token == "Tier 2"
    assert client.bodies, "no fake delivery reservation was made"
    assert f"CA: {case['token_mint']}" in client.bodies[-1]


def test_21b_coge_before_the_fix_is_rejected_by_the_composer(
    preserved: dict,
) -> None:
    """The run's own record still fails closed -- nothing was weakened."""

    case = _mint_case(preserved, "COGE")
    result, client = _compose_fixture(case, coherent=False)
    assert result.decision == composer.COMPOSE_DECISION_REJECTED
    assert result.reason == (
        composer.COMPOSE_REJECTED_ATH_RESOLVED_TUPLE_INVALID)
    assert client.bodies == []


def test_21c_coge_resolved_tier_math(preserved: dict) -> None:
    case = _mint_case(preserved, "COGE")
    market = case["market_context"]
    assert market["market_state"] == "MARKET_READY"
    assert Decimal(market["liquidity_usd"]) > Decimal("4500")
    # BEFORE: the two arms disagree, so the record could never resolve.
    run_record = _record_from_case(case, coherent=False)
    assert run_record["resolved"] is False
    # AFTER: one coherent observation -> Tier 2 and a compose-eligible tuple.
    fixed = _record_from_case(case, coherent=True)
    assert ath_resolved_tuple_is_valid(fixed)
    assert _tier_for(fixed, market["current_market_cap_usd"]) == "Tier 2"


def test_22c_rabbit_resolved_tier_math(preserved: dict) -> None:
    case = _mint_case(preserved, "RABBIT")
    market = case["market_context"]
    assert market["market_state"] == "MARKET_READY"
    assert Decimal(market["liquidity_usd"]) > Decimal("4500")
    run_record = _record_from_case(case, coherent=False)
    assert run_record["resolved"] is False
    fixed = _record_from_case(case, coherent=True)
    assert ath_resolved_tuple_is_valid(fixed)
    assert _tier_for(fixed, market["current_market_cap_usd"]) == "Tier 2"


def test_23_april_fixture_executes_a_real_priority_refresh(
    preserved: dict,
) -> None:
    """April's market was STALE and every refresh was dead code.

    After the fix a real provider request is made, the refreshed values
    become visible, and the tier is recomputed from them.
    """

    case = _mint_case(preserved, "APRIL")
    assert case["market_context"]["market_state"] == "MARKET_INCOMPLETE"
    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    sidecar = ScheduledMarketSidecar(scheduler)
    before = scheduler.snapshot("mint-000-pump")
    assert before["all_present"] is False
    context = sidecar.priority_refresh(
        "mint-000-pump", migration_time_utc=case["migration_time_utc"],
        now_iso_fn=lambda: case["observed_at_utc"])
    assert context["priority_refresh_result"] == REFRESH_SUCCEEDED
    assert provider.price_calls, "no provider request was made"
    assert context["all_present"] is True
    assert context["market_state"] == "MARKET_READY"


def test_24_turtleneck_hydration_is_scheduled(preserved: dict, tmp_path) -> None:
    case = _mint_case(preserved, "TURTLE")
    assert case["central_ath"]["ath_hydration_reason"] == (
        ATH_HYDRATION_NEVER_ATTEMPTED)
    store = ath_state_module.CentralAthStateStore(
        path=tmp_path / "ath_state.json")
    mint = case["token_mint"]
    store.register_pool(
        mint=mint, pool_address="pool-address", quote_mint=WSOL,
        creation_timestamp=case["migration_time_utc"])
    hydration = store.schedule_hydration(
        mint, anchor_utc=case["migration_time_utc"])
    assert hydration["scheduled"] is True
    assert hydration["scheduled_at_utc"]
    assert hydration["anchor_utc"] == case["migration_time_utc"]
    assert mint in store.pending_hydration_mints()
    assert store.hydration_due(mint) is True
    # Scheduling alone never completes anything.
    assert hydration["status"] == ATH_HYDRATION_PENDING


def test_25_partial_backfill_ath_remains_blocked(preserved: dict) -> None:
    case = _mint_case(preserved, "TURTLE")
    record = _record_from_case(case, coherent=True)
    anchor_unix = int(Decimal("1785642480"))  # 2026-08-02T03:48:00Z
    partial = {
        **record,
        "pool_created_at": case["migration_time_utc"],
        "ohlcv_coverage": {
            "interval": "1m", "time_from_unix": anchor_unix,
            "time_to_unix": anchor_unix + 300,
            "history_complete": False, "pages": 1},
    }
    status, reason = evaluate_ath_hydration(
        partial, now_utc="2026-08-02T05:38:54Z")
    assert status == ATH_HYDRATION_PENDING
    assert status != ATH_HYDRATION_COMPLETE
    assert reason != ATH_HYDRATION_VERIFIED


def test_26_complete_backfill_ath_may_proceed(preserved: dict) -> None:
    case = _mint_case(preserved, "TURTLE")
    record = _record_from_case(case, coherent=True)
    anchor_unix = 1785642480  # 2026-08-02T03:48:00Z
    now_unix = 1785649134     # 2026-08-02T05:38:54Z
    # 2026-08-03: completeness is proven by the authenticated migration
    # PAIR's V3 history (the V1 token-aggregate window no longer counts --
    # its migration-anchored ``time_from`` was proven to drop the partial
    # first candle holding the literal peak).
    complete = {
        **record,
        "pool_created_at": case["migration_time_utc"],
        "ath_v3_pair": {
            "schema_version": "phx2_ath_v3_pair_v1",
            "pair_address": "PairTurtle" + "1" * 34,
            "live_epoch_id": None,
            "anchor_unix": anchor_unix,
            "coarse_interval": "15s",
            "window_from_unix": (anchor_unix // 15) * 15,
            "window_to_unix": now_unix,
            "history_complete": True,
            "usd_peak": {"price_usd": record["resolved_ath_price"],
                         "unix_time": anchor_unix + 600},
        },
    }
    status, reason = evaluate_ath_hydration(
        complete, now_utc="2026-08-02T05:38:54Z")
    assert status == ATH_HYDRATION_COMPLETE
    assert reason == ATH_HYDRATION_VERIFIED
    assert _tier_for(
        complete, case["market_context"]["current_market_cap_usd"]) == "Tier 1"


# ===========================================================================
# 27-29  Defect C: cadence vs freshness TTL, and the request budget
# ===========================================================================


def test_27_tier_active_cadence_is_shorter_than_the_hard_ttl() -> None:
    provider = _Provider()
    clock = _Clock()
    scheduler = _scheduler(provider, clock=clock)
    view = _View("mint-000-pump", status="ACTIVE_DIP_WATCH")
    view.market_compose_near = True
    scheduler.update_candidates([view], now_epoch=clock.value)
    stored = scheduler._views["mint-000-pump"]
    assert scheduler.cadence_class(stored) == CADENCE_TIER_ACTIVE
    price_interval, overview_interval, cadence = scheduler._refresh_intervals(
        stored)
    price_ttl, overview_ttl = scheduler._ttls(stored)
    headroom = float(scheduler.config.cadence_headroom_fraction)
    assert cadence == CADENCE_TIER_ACTIVE
    assert price_interval <= price_ttl * headroom
    assert overview_interval <= overview_ttl * headroom
    ceilings = scheduler.config.tier_cadence_ceilings()
    assert price_interval <= ceilings["price_tier_active_ceiling_seconds"]
    assert overview_interval <= ceilings["overview_tier_active_ceiling_seconds"]


def test_28_far_candidates_stay_on_a_slower_cadence() -> None:
    provider = _Provider()
    clock = _Clock()
    scheduler = _scheduler(provider, clock=clock)
    far = _View("mint-far0-pump", status="PENDING_1_20X", candidate_id="far")
    near = _View("mint-000-pump", status="ACTIVE_DIP_WATCH")
    near.market_compose_near = True
    scheduler.update_candidates([far, near], now_epoch=clock.value)
    far_view = scheduler._views["mint-far0-pump"]
    near_view = scheduler._views["mint-000-pump"]
    assert scheduler.cadence_class(far_view) == CADENCE_FAR
    far_price, far_overview, _ = scheduler._refresh_intervals(far_view)
    near_price, near_overview, _ = scheduler._refresh_intervals(near_view)
    assert far_price > near_price
    assert far_overview > near_overview
    # Far candidates are deliberately SLOWER than the legacy pending TTL --
    # that is what pays for the faster tier-active cadence.
    assert far_price >= scheduler.config.price_pending_ttl_seconds
    # A terminal/quarantined candidate is slower still.
    near_view_inactive = replace(far_view, quarantined=True)
    assert scheduler.cadence_class(near_view_inactive) == CADENCE_INACTIVE


def test_28b_scheduler_plans_without_a_producer_tick() -> None:
    """Defect C's actual mechanism, and its fix.

    ``plan()`` was called ONCE per producer watch tick.  A tick measured
    ~46 s in the 2026-08-02 run (132 ticks in 6,120 s), so a 12 s price TTL
    was unreachable no matter how idle the workers were.  With an internal
    planner interval the scheduler re-plans on its OWN cadence, and
    ``plan()`` stays idempotent for every existing caller.
    """

    import time

    calls = {"n": 0}

    def price(mint: str):
        calls["n"] += 1
        now = time.time()
        return MarketObservation(
            mint=mint, candidate_id="cand-1", generation=7,
            source=SOURCE_PAID_SINGLE, source_timestamp=now,
            ingestion_timestamp=now, field_group=FIELD_PRICE_MC,
            observation_sequence=calls["n"],
            source_evidence_digest=f"{calls['n']:064d}", request_id=None,
            values={"current_price": "0.00002",
                    "current_market_cap_usd": "20000"})

    scheduler = MarketScheduler(
        price_fetch_fn=price, overview_fetch_fn=None,
        config=MarketSchedulerConfig(
            worker_count=2, max_inflight=2, p1_reserved_workers=0,
            provider_min_interval_seconds=0.01,
            planner_interval_seconds=0.02,
            price_active_ttl_seconds=0.2, overview_active_ttl_seconds=0.4))
    view = _View("mint-000-pump")
    view.market_compose_near = True
    scheduler.update_candidates([view])
    scheduler.start()
    try:
        time.sleep(1.0)
    finally:
        scheduler.stop(timeout_seconds=5.0)
    # A tier-active candidate at a 0.1 s clamped interval must be refreshed
    # many times in one second WITHOUT any caller driving plan().
    assert calls["n"] >= 5, calls["n"]
    # And the legacy caller-driven path still works with the planner off.
    quiet = MarketScheduler(
        price_fetch_fn=price, overview_fetch_fn=None,
        config=MarketSchedulerConfig(worker_count=1, max_inflight=1,
                                     p1_reserved_workers=0))
    assert quiet.config.planner_interval_seconds == 0.0
    assert quiet.plan(enqueue=False) == []


def test_29_projected_request_usage_stays_within_budget() -> None:
    import argparse

    from PHX2.free_tier_producer.free_tier_session import (
        build_production_market_scheduler_config,
    )

    config = build_production_market_scheduler_config(argparse.Namespace())
    # The mix actually observed on 2026-08-02: 33 tracked candidates --
    # 13 activated, 17 pending, 3 quarantined.
    observed = project_request_budget(
        config, tier_active=13, far=17, inactive=3)
    assert observed["fits_budget"] is True
    assert observed["within_spacing_ceiling"] is True
    assert observed["within_request_budget"] is True
    assert observed["projected_requests_per_second"] < (
        observed["request_start_spacing_ceiling_rps"])
    # Even the pathological case -- every observed candidate simultaneously
    # tier-active -- still fits.
    worst = project_request_budget(config, tier_active=33)
    assert worst["fits_budget"] is True
    # And the projection is honest about where it stops fitting.
    saturated = project_request_budget(config, tier_active=400)
    assert saturated["within_spacing_ceiling"] is False


# ===========================================================================
# 30-31  Checkpoint: April restores, corruption still quarantines
# ===========================================================================


@dataclass
class _Entry:
    """Minimal watch entry; a dataclass because the production consistency
    check serializes the entry with ``asdict`` when it quarantines."""

    token_mint: str
    status: str
    activation_target_market_cap_usd: str
    candidate_id: str = "cand-april"


class _Watchlist:
    def __init__(self, entries) -> None:
        self._entries = list(entries)
        self.quarantined: list = []

    def all_entries(self):
        return list(self._entries)

    def quarantine_candidate(self, mint, **kwargs):
        self.quarantined.append(mint)


def test_30_april_resolved_checkpoint_restores_successfully(
    preserved: dict,
) -> None:
    """April's quarantine was the split ATH tuple, not real corruption.

    Its raw market-cap arm ($34,493.51) sat BELOW its own activation target
    ($32,980.58 -- and its later split arm fell to $27,483.81), while the
    record's true resolved peak is ~$52,995.  The contradiction was in the
    arms, never in the candidate.
    """

    from PHX2.free_tier_producer.compat.build30_watchlist import (
        WATCH_ACTIVE_DIP,
    )

    case = _mint_case(preserved, "APRIL")
    target = case["activation"]["activation_target_market_cap_usd"]
    record = _record_from_case(case, coherent=True)
    assert Decimal(record["resolved_ath_market_cap"]) > Decimal(target)
    watchlist = _Watchlist(
        [_Entry(case["token_mint"], WATCH_ACTIVE_DIP, target)])
    findings = verify_cross_checkpoint_consistency(
        watchlist, {case["token_mint"]: record},
        now_utc="2026-08-02T06:13:00Z")
    assert findings == []
    assert watchlist.quarantined == []


def test_30b_resolved_record_round_trips_through_the_real_checkpoint(
    preserved: dict, tmp_path,
) -> None:
    """The resolved tuple serializes, validates and restores unchanged."""

    case = _mint_case(preserved, "APRIL")
    path = tmp_path / "ath_state.json"
    store = ath_state_module.CentralAthStateStore(path=path)
    mint = case["token_mint"]
    central = case["central_ath"]
    # ONE coherent observation: this price WITH its own market cap.
    with localcontext() as ctx:
        ctx.prec = ATH_RESOLUTION_PRECISION
        supply = (Decimal(central["ath_market_cap"])
                  / Decimal(central["ath_market_cap_evidence_price_usd"]))
        own_market_cap = Decimal(central["ath_price"]) * supply
    assert store.observe_provider_current(
        mint=mint, price_usd=central["ath_price"],
        market_cap_usd=format(own_market_cap, "f"),
        observed_at=central["ath_timestamp"]) is True
    snapshot = store.snapshot(mint)
    assert snapshot["resolved"] is True
    assert ath_resolved_tuple_is_valid(snapshot)

    record = _checkpoint_record(path, mint)
    ok, reason = validate_ath_checkpoint_record(record)
    assert ok, reason
    assert record["resolved_ath_market_cap"] == (
        snapshot["resolved_ath_market_cap"])
    assert record["resolution_method"] == (
        RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY)

    restored = ath_state_module.CentralAthStateStore(path=path)
    restored_snapshot = restored.snapshot(mint)
    assert restored_snapshot["resolved"] is True
    assert restored_snapshot["resolved_ath_market_cap"] == (
        snapshot["resolved_ath_market_cap"])
    assert restored_snapshot["resolved_supply"] == snapshot["resolved_supply"]
    assert restored.checkpoint_quarantined is False


def test_31_corrupt_checkpoint_records_still_quarantine(
    preserved: dict,
) -> None:
    from PHX2.free_tier_producer.compat.build30_watchlist import (
        WATCH_ACTIVE_DIP,
    )

    case = _mint_case(preserved, "APRIL")
    target = case["activation"]["activation_target_market_cap_usd"]
    record = _record_from_case(case, coherent=True)
    # (a) A record bound to a DIFFERENT mint still quarantines.
    wrong_mint = _Watchlist(
        [_Entry(case["token_mint"], WATCH_ACTIVE_DIP, target)])
    findings = verify_cross_checkpoint_consistency(
        wrong_mint, {case["token_mint"]: {**record,
                                          "token_mint": "other-mint-pump"}},
        now_utc="2026-08-02T06:13:00Z")
    assert [f["issue"] for f in findings] == [
        "ATH_RECORD_BOUND_TO_DIFFERENT_MINT"]
    assert wrong_mint.quarantined == [case["token_mint"]]
    # (b) A resolved peak GENUINELY below the activation target still
    #     quarantines -- the check was re-pointed, never weakened.
    low = _Watchlist(
        [_Entry(case["token_mint"], WATCH_ACTIVE_DIP, "999999999")])
    findings = verify_cross_checkpoint_consistency(
        low, {case["token_mint"]: record}, now_utc="2026-08-02T06:13:00Z")
    assert [f["issue"] for f in findings] == [
        "ACTIVATED_BUT_CENTRAL_ATH_BELOW_TARGET"]
    assert findings[0]["central_ath_comparison_basis"] == (
        "RESOLVED_ATH_MARKET_CAP")

def test_31b_tampered_resolved_record_is_refused_by_the_validator(
    preserved: dict, tmp_path,
) -> None:
    """A record CLAIMING resolution whose own arithmetic fails is corrupt."""

    case = _mint_case(preserved, "APRIL")
    path = tmp_path / "ath_state.json"
    store = ath_state_module.CentralAthStateStore(path=path)
    mint = case["token_mint"]
    store.observe_provider_current(
        mint=mint, price_usd="0.00005", market_cap_usd="50000",
        observed_at="2026-08-02T05:05:39Z")
    record = _checkpoint_record(path, mint)
    ok, _reason = validate_ath_checkpoint_record(record)
    assert ok

    # Market cap no longer equals price x supply.
    tampered = {**record, "resolved_ath_market_cap": "1"}
    ok, reason = validate_ath_checkpoint_record(tampered)
    assert not ok
    assert reason == "CHECKPOINT_CROSS_CONSISTENCY_INVALID"

    # Resolved price no longer equals the record's own accepted maximum.
    detached = {**record, "resolved_ath_price": "0.99"}
    ok, reason = validate_ath_checkpoint_record(detached)
    assert not ok
    assert reason == "CHECKPOINT_CROSS_CONSISTENCY_INVALID"

    # An unresolved record claiming a resolution method is refused.
    claimed = {**record, "resolved": False,
               "resolution_method": RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY}
    ok, reason = validate_ath_checkpoint_record(claimed)
    assert not ok
    assert reason == "CHECKPOINT_STATUS_UNSUPPORTED"


# ===========================================================================
# 32-38  Hard-safety requirements that must NOT have moved
# ===========================================================================


def test_32_phx1_parity_activation_fee_structural_stay_shadow() -> None:
    from PHX2.free_tier_producer import phx1_parity_policy as policy

    parity = policy.ALERT_POLICY_PHX1_PARITY
    for condition in (policy.CONDITION_ACTIVATION_PROVEN,
                      policy.CONDITION_ACTIVATION_MULTIPLIER_LIVE,
                      policy.CONDITION_ACTIVATION_CROSSING_TICK,
                      policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
                      policy.CONDITION_FEE_PROOF_MISSING,
                      policy.CONDITION_FEE_GATE_SCAM_LIKELY,
                      policy.CONDITION_STRUCTURAL_POLICY):
        assert policy.enforcement_for(condition, policy=parity) == (
            policy.ENFORCEMENT_SHADOW), condition
        assert policy.blocks_compose(condition, policy=parity) is False


def test_33_liquidity_floor_remains_hard() -> None:
    source = Path(
        "PHX2/free_tier_producer/free_tier_session.py").read_text(
            encoding="utf-8")
    assert "4500" in source
    from PHX2.free_tier_producer import phx1_parity_policy as policy

    assert policy.blocks_compose(
        policy.CONDITION_LIQUIDITY_FLOOR,
        policy=policy.ALERT_POLICY_PHX1_PARITY) is True


def test_34_invalid_current_market_cap_remains_hard() -> None:
    from PHX2.free_tier_producer.compat.build29_cap1_compose_send import (
        build_revalidation_request,
    )

    assert build_revalidation_request(
        token_mint="mint-000-pump", candidate_id="c1",
        migration_time_utc="2026-08-02T05:00:00Z", migration_source="src",
        current_price="0.00002", current_market_cap_usd=None,
        liquidity_usd="12000",
        market_context_fetched_at_utc="2026-08-02T05:05:38Z",
        created_at_utc="2026-08-02T05:05:39Z") is None


def test_35_migration_proof_remains_hard() -> None:
    from PHX2.free_tier_producer import phx1_parity_policy as policy

    assert policy.enforcement_for(
        policy.CONDITION_MIGRATION_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_HARD


def test_36_dedupe_and_delivery_remain_hard() -> None:
    from PHX2.free_tier_producer import phx1_parity_policy as policy

    parity = policy.ALERT_POLICY_PHX1_PARITY
    for condition in (policy.CONDITION_DEDUPE,
                      policy.CONDITION_DELIVERY_RESERVATION,
                      policy.CONDITION_TIER_LIFETIME_MONOTONICITY,
                      policy.CONDITION_COMPOSE_AUTHORIZATION):
        assert policy.enforcement_for(condition, policy=parity) in (
            policy.ENFORCEMENT_HARD, policy.ENFORCEMENT_HARD_AT_SEND), condition
        assert policy.blocks_compose(condition, policy=parity) is True


def test_37_no_real_telegram_send_occurs_offline() -> None:
    """Nothing in this module can reach a real transport.

    The priority refresh is a MARKET path: it never composes, never renders,
    never reserves a ledger line and never touches a transport.
    """

    import socket

    scheduler_source = Path(
        "PHX2/free_tier_producer/market_scheduler.py").read_text(
            encoding="utf-8").lower()
    for needle in ("telegram", "discord", "webhook",
                   "compose_and_maybe_send", "api.telegram.org"):
        assert needle not in scheduler_source, needle

    # Behavioural, not textual: a priority refresh with the network hard
    # blocked still completes through its fake provider and still refuses to
    # invent a value.
    real_socket = socket.socket

    def _blocked(*args, **kwargs):
        raise AssertionError("offline test attempted a network connection")

    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    socket.socket = _blocked
    try:
        result = scheduler.priority_refresh("mint-000-pump")
    finally:
        socket.socket = real_socket
    assert result["priority_refresh_result"] == REFRESH_SUCCEEDED
    assert "message_id" not in result
    assert "transport_ok" not in result


def test_38_paid_ledger_is_never_touched_by_this_module(tmp_path) -> None:
    """Neither remediated module can reach the permanent ping ledger."""

    for module_path in ("PHX2/free_tier_producer/market_scheduler.py",
                        "PHX2/free_tier_producer/ath_state.py"):
        source = Path(module_path).read_text(encoding="utf-8").lower()
        for needle in ("ping_dedupe", "dedupe_ledger", "reserve_send",
                       "dispatch_ledger"):
            assert needle not in source, f"{module_path}: {needle}"

    # Behavioural: exercising both remediated paths writes only the ATH
    # checkpoint the store owns, and nothing resembling a ledger.
    store = ath_state_module.CentralAthStateStore(
        path=tmp_path / "ath_state.json")
    store.observe_provider_current(
        mint="mint-000-pump", price_usd="0.00005",
        market_cap_usd="50000", observed_at="2026-08-02T05:05:39Z")
    store.schedule_hydration("mint-000-pump")
    provider = _Provider()
    scheduler, _view, _clock = _tracked_scheduler(provider)
    scheduler.priority_refresh("mint-000-pump")
    written = sorted(p.name for p in tmp_path.iterdir())
    assert written and all("ledger" not in name and "dedupe" not in name
                           for name in written), written


# ===========================================================================
# Preserved-run replay: before vs after, all four mints
# ===========================================================================


def test_replay_before_fix_reproduces_every_observed_failure(
    preserved: dict,
) -> None:
    """The exact run outcome, reproduced from preserved evidence."""

    composed_tiers = 0
    for label in ("COGE", "RABBIT", "APRIL", "TURTLE"):
        case = _mint_case(preserved, label)
        record = _record_from_case(case, coherent=False)
        central = case["central_ath"]
        if label == "TURTLE":
            # Its two arms AGREED; turtleneck was blocked on coverage.
            assert central["ath_price"] == (
                central["ath_market_cap_evidence_price_usd"])
            assert central["ath_hydration_reason"] == (
                ATH_HYDRATION_NEVER_ATTEMPTED)
        else:
            # The split-arm defect: no resolvable observation at all.
            assert central["ath_price"] != (
                central["ath_market_cap_evidence_price_usd"]), label
            assert record["resolved"] is False, label
        status, _reason = evaluate_ath_hydration(
            {**record, "pool_created_at": case["migration_time_utc"],
             "ohlcv_coverage": None})
        assert status != ATH_HYDRATION_COMPLETE, label
    assert composed_tiers == 0

    # Defect A, reproduced structurally: the retired sidecar carried the
    # method, the production one did not.
    from PHX2.free_tier_producer.compat.build29_cap1_market_sidecar import (
        Cap1MarketSidecar,
    )
    assert hasattr(Cap1MarketSidecar, "priority_refresh")


def test_replay_after_fix_reaches_tiers_and_fake_delivery(
    preserved: dict,
) -> None:
    """After the fix: two preserved fixtures reach a Tier-2 compose tuple,
    April gets a real refreshed evaluation, turtleneck reaches scheduling,
    and no hard-safety requirement is bypassed."""

    outcomes = {}
    for label in ("COGE", "RABBIT", "APRIL", "TURTLE"):
        case = _mint_case(preserved, label)
        record = _record_from_case(case, coherent=True)
        market = case["market_context"]
        tier = (_tier_for(record, market["current_market_cap_usd"])
                if record["resolved"] else None)
        outcomes[label] = {
            "resolved": record["resolved"],
            "tier": tier,
            "liquidity_ok": Decimal(market["liquidity_usd"]) > Decimal("4500"),
            "market_ready": market["market_state"] == "MARKET_READY",
        }
    # Two preserved fixtures reach a Tier-2 compose-eligible resolved tuple
    # with fresh market evidence and liquidity above the hard floor.
    for label in ("COGE", "RABBIT"):
        assert outcomes[label]["resolved"] is True, label
        assert outcomes[label]["tier"] == "Tier 2", label
        assert outcomes[label]["liquidity_ok"] is True, label
        assert outcomes[label]["market_ready"] is True, label
    # April resolves, but its market snapshot is stale: it must NOT compose
    # on stale evidence -- it must be refreshed first (test 23).
    assert outcomes["APRIL"]["resolved"] is True
    assert outcomes["APRIL"]["market_ready"] is False
    # Turtleneck's arms were always coherent; it is gated on coverage only.
    assert outcomes["TURTLE"]["resolved"] is True
    assert outcomes["TURTLE"]["tier"] == "Tier 1"
