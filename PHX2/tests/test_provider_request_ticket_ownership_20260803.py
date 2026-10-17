from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json
import threading
import time

import pytest

from PHX2.free_tier_producer.market_budget import (
    ORIGIN_ATH_HYDRATION_OHLCV,
    ORIGIN_PRIORITY_REFRESH_OVERVIEW,
    ORIGIN_PRIORITY_REFRESH_PRICE,
    ORIGIN_SCHEDULED_OVERVIEW,
    ORIGIN_SCHEDULED_PRICE,
    MarketPhysicalRequestMeter,
    reconcile,
)
from PHX2.free_tier_producer.market_scheduler import (
    CandidateScheduleView,
    MarketScheduler,
    MarketSchedulerConfig,
)
from PHX2.free_tier_producer.free_tier_market_transport import (
    FreeTierMarketTransport,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_NONE,
)


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _OverlappingProvider:
    """Deterministic provider with a 16-call overlap gate and named retries."""

    def __init__(self) -> None:
        self._overlap_ready = threading.Event()
        self._release_overlap = threading.Event()
        self._barrier = threading.Barrier(
            16, action=self._overlap_ready.set)
        self._lock = threading.Lock()
        self._calls = 0
        self._per_key: dict[tuple[str, str], int] = {}

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def wait_for_overlap(self) -> bool:
        return self._overlap_ready.wait(timeout=10)

    def release_overlap(self) -> None:
        self._release_overlap.set()

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        del endpoint_secret, timeout_seconds
        mint = str(query_params.get("address") or "")
        key = (str(path), mint)
        with self._lock:
            self._calls += 1
            ordinal = self._calls
            attempt = self._per_key.get(key, 0)
            self._per_key[key] = attempt + 1
        if ordinal <= 16:
            self._barrier.wait(timeout=10)
            if not self._release_overlap.wait(timeout=10):
                raise TimeoutError("overlap checkpoint was not released")

        # Every 23rd candidate fails its first request on each plane.  The
        # paid transport retries it, producing a second ticket with index 1.
        index = int(mint.removeprefix("Mint") or "0") if mint.startswith("Mint") else 0
        if mint and index % 23 == 0 and attempt == 0:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
                http_status_code=500,
                body=None,
                fetched_at_utc=_iso_now(),
            )

        now_epoch = int(time.time())
        if path == BIRDEYE_PATH_PRICE:
            data = {
                "address": mint,
                "value": "1.25",
                "updateUnixTime": now_epoch,
            }
        elif path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            data = {
                "address": mint,
                "marketCap": "125000",
                "liquidity": "9000",
                "updateUnixTime": now_epoch,
            }
        else:
            data = {"items": [{"h": "1.5", "unixTime": now_epoch}]}
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"success": True, "data": data},
            fetched_at_utc=_iso_now(),
        )


def _view(index: int) -> CandidateScheduleView:
    return CandidateScheduleView(
        mint=f"Mint{index:04d}",
        candidate_id=f"candidate-{index:04d}",
        generation=7,
        status="PENDING_BASELINE",
        seeded_at_epoch=time.time() - 10.0,
    )


def _wait_for_settled(scheduler: MarketScheduler, target: int) -> None:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if scheduler.stats()["market_scheduler_jobs_settled"] >= target:
            return
        time.sleep(0.01)
    pytest.fail(f"scheduler did not settle {target} jobs")


def _assert_exact_checkpoint(
    scheduler: MarketScheduler, meter: MarketPhysicalRequestMeter,
) -> None:
    stats = scheduler.stats()
    result = reconcile(
        scheduler_physical_requests_total=stats[
            "scheduler_physical_requests_total"],
        meter=meter,
    )
    assert result["unreconciled_delta"] == 0
    assert result["scheduler_charge_delta"] == 0
    assert result["reconciled"] is True


def test_real_16_worker_scheduler_has_exact_ticket_ownership_under_overlap(tmp_path):
    artifact = tmp_path / "provider_request_tickets.jsonl"
    meter = MarketPhysicalRequestMeter(
        ticket_artifact=artifact,
        producer_generation=7,
        epoch_id="epoch_ticket_stress",
    )
    provider = _OverlappingProvider()
    transport = PaidBirdeyeMarketTransport(
        inner_transport=provider,
        endpoint_secret=object(),
        min_interval_seconds=0,
        cache_ttl_seconds=120,
        ohlcv_cache_ttl_seconds=120,
        max_attempts=2,
        max_calls_total=None,
        backoff_seconds=(0,),
        sleep_fn=lambda _seconds: None,
        max_concurrency=16,
        physical_request_meter=meter,
    )
    scheduler = MarketScheduler(
        price_fetch_fn=transport.fetch_price_plane,
        overview_fetch_fn=transport.fetch_overview_plane,
        config=MarketSchedulerConfig(
            worker_count=16,
            max_inflight=16,
            max_queue_size=4096,
            provider_request_budget=0,
            provider_min_interval_seconds=0,
            max_active_candidates=4096,
            p1_reserved_workers=0,
        ),
        physical_request_meter=meter,
    )
    scheduler.start()

    views: list[CandidateScheduleView] = []
    logical_jobs = 0
    expected_settled = 0
    for wave in range(5):
        views.extend(_view(index) for index in range(wave * 100, (wave + 1) * 100))
        scheduler.update_candidates(views)
        jobs = scheduler.plan(enqueue=True)
        logical_jobs += len(jobs)
        expected_settled += len(jobs)
        if wave == 0:
            assert provider.wait_for_overlap()
            # This checkpoint is taken while all 16 physical calls are still
            # in flight. Exact ownership already exists at dispatch, so it is
            # reconciled without waiting for global counter intervals to end.
            _assert_exact_checkpoint(scheduler, meter)
            assert meter.snapshot()["pending_physical_request_tickets"] == 16
            provider.release_overlap()
        _wait_for_settled(scheduler, expected_settled)
        _assert_exact_checkpoint(scheduler, meter)

    assert logical_jobs >= 1000
    assert provider.calls >= 1000
    assert meter.snapshot()["physical_retries"] > 0

    # Real priority-refresh path: first call is cache-only (zero tickets),
    # second mint is forced physical and owns two priority-origin tickets.
    before = meter.total
    cached_refresh = scheduler.priority_refresh(views[1].mint)
    assert cached_refresh["priority_refresh_provider_requests"] == 2
    assert meter.total == before
    with transport._lock:
        transport._cache.clear()
    physical_refresh = scheduler.priority_refresh(views[2].mint)
    assert physical_refresh["priority_refresh_provider_requests"] == 2
    assert meter.total == before + 2
    _assert_exact_checkpoint(scheduler, meter)

    # OHLCV is explicit non-scheduler work, never a hidden adjustment.  Its
    # second identical call is a cache hit and therefore creates no ticket.
    with meter.ownership(
        origin=ORIGIN_ATH_HYDRATION_OHLCV,
        mint=views[3].mint,
        scheduler_owner="ATH_HYDRATION",
    ):
        first = transport.get(
            endpoint_secret=object(),
            path=BIRDEYE_PATH_OHLCV,
            query_params={
                "address": views[3].mint,
                "time_from": "1",
                "time_to": str(int(time.time())),
                "type": "1m",
            },
            timeout_seconds=1,
        )
        physical_after_first = meter.total
        second = transport.get(
            endpoint_secret=object(),
            path=BIRDEYE_PATH_OHLCV,
            query_params={
                "address": views[3].mint,
                "time_from": "1",
                "time_to": str(int(time.time())),
                "type": "1m",
            },
            timeout_seconds=1,
        )
    assert first.http_status_code == second.http_status_code == 200
    assert meter.total == physical_after_first
    _assert_exact_checkpoint(scheduler, meter)

    # Queue work and stop immediately. At least some jobs are cancelled before
    # dispatch and therefore have no ticket at all.
    views.extend(_view(index) for index in range(500, 700))
    scheduler.update_candidates(views)
    cancellation_jobs = scheduler.plan(enqueue=True)
    logical_jobs += len(cancellation_jobs)
    assert scheduler.stop(timeout_seconds=10)
    assert scheduler.stats()["market_scheduler_jobs_cancelled"] > 0
    assert any(
        meter.ticket_count_for_job(job.request_id, include_pending=True) == 0
        for job in cancellation_jobs)
    _assert_exact_checkpoint(scheduler, meter)

    snapshot = meter.snapshot()
    by_origin = snapshot["physical_by_origin"]
    assert by_origin[ORIGIN_SCHEDULED_PRICE] > 0
    assert by_origin[ORIGIN_SCHEDULED_OVERVIEW] > 0
    assert by_origin[ORIGIN_PRIORITY_REFRESH_PRICE] == 1
    assert by_origin[ORIGIN_PRIORITY_REFRESH_OVERVIEW] == 1
    assert by_origin[ORIGIN_ATH_HYDRATION_OHLCV] == 1
    assert snapshot["transport_physical_requests_total"] == provider.calls
    assert snapshot["pending_physical_request_tickets"] == 0
    assert snapshot["non_physical_by_reason"]["CACHE_HIT"] >= 3

    rows = [json.loads(line) for line in artifact.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == provider.calls
    assert len({row["request_id"] for row in rows}) == len(rows)
    assert all(row["physical_dispatch"] is True for row in rows)
    assert all(row["epoch_id"] == "epoch_ticket_stress" for row in rows)
    assert all(row["producer_generation"] == 7 for row in rows)
    assert all("http_status_class" in row for row in rows)
    assert logical_jobs >= 1000


def test_ticket_is_frozen_and_retry_indexes_are_per_physical_attempt():
    meter = MarketPhysicalRequestMeter(producer_generation=3, epoch_id="epoch-a")
    with meter.ownership(
        origin=ORIGIN_SCHEDULED_PRICE,
        scheduler_job_id="job-a",
        mint="MintA",
        priority="P1_ACTIVATED",
        scheduler_owner="MARKET_SCHEDULER",
    ):
        first_id = meter.begin_physical(BIRDEYE_PATH_PRICE, retry_index=0)
        first = meter.complete_physical(
            first_id,
            http_status_class="5XX",
            provider_outcome="HTTP_500",
            observation_accepted=False,
            rejection_reason="PROVIDER_5XX",
        )
        second_id = meter.begin_physical(BIRDEYE_PATH_PRICE, retry_index=1)
        second = meter.complete_physical(
            second_id,
            http_status_class="2XX",
            provider_outcome="SUCCESS",
            observation_accepted=True,
        )
    assert (first.retry_index, second.retry_index) == (0, 1)
    assert meter.ticket_count_for_job("job-a") == 2
    with pytest.raises(FrozenInstanceError):
        first.origin = "MUTATED"  # type: ignore[misc]


def test_paid_failure_and_keyless_fallback_are_separate_exact_tickets():
    meter = MarketPhysicalRequestMeter(producer_generation=9, epoch_id="epoch-f")

    class _PrimaryFailure:
        def get(self, **_kwargs):
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
                http_status_code=500,
                body=None,
                fetched_at_utc=_iso_now(),
            )

    pair_body = json.dumps({
        "pairs": [{
            "chainId": "solana",
            "priceUsd": "2.5",
            "marketCap": 250000,
            "liquidity": {"usd": 10000},
        }],
    }).encode("utf-8")
    fallback = FreeTierMarketTransport(
        urlopen_fn=lambda _url, _timeout: (200, pair_body),
        pairs_min_interval_seconds=0,
        physical_request_meter=meter,
    )
    transport = PaidBirdeyeMarketTransport(
        inner_transport=_PrimaryFailure(),
        endpoint_secret=object(),
        fallback_transport=fallback,
        min_interval_seconds=0,
        max_attempts=1,
        max_calls_total=None,
        physical_request_meter=meter,
    )
    with meter.ownership(
        origin=ORIGIN_SCHEDULED_PRICE,
        scheduler_job_id="fallback-job",
        mint="FallbackMint",
        priority="P1_ACTIVATED",
        scheduler_owner="MARKET_SCHEDULER",
    ):
        result = transport.fetch_price_plane("FallbackMint")
    assert result is not None and result["current_price"] == "2.5"
    tickets = meter.tickets_for_job("fallback-job")
    assert [ticket.origin for ticket in tickets] == [
        ORIGIN_SCHEDULED_PRICE, "FALLBACK"]
    reconciliation = reconcile(
        scheduler_physical_requests_total=2, meter=meter)
    assert reconciliation["reconciliation_reasons"]["SCHEDULER_OWNED"] == 1
    assert reconciliation["reconciliation_reasons"]["FALLBACK"] == 1
    assert reconciliation["unreconciled_delta"] == 0
    assert reconciliation["scheduler_charge_delta"] == 0
