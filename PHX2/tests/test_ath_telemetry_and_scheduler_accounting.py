"""Regression suite for the 2026-07-31 telemetry / scheduler remediation.

Two independent defects, both proven from the preserved run
``paid_primary_live_24x7_20260731T093544Z``:

A. ``free_tier_pricing_tail`` built the PERSISTED record from the resolved
   ``central_ath`` snapshot but wrote its IN-MEMORY telemetry state from the raw
   ``market`` payload.  A market quote never carries ATH -- ATH lives in the
   central store -- so heartbeat/dashboard telemetry reported ``ath_price_usd =
   null`` for all 17 watch rows while the real eligibility path held valid
   central ATH and had already committed five tiers.  The null was read as a
   pipeline failure it never was.

B. ``MarketScheduler._apply_values_locked`` collapsed "no usable value at all"
   and "valid values that are simply not NEWER" into one ``False``.  The second
   case is the normal answer for a token that has not traded since the last poll
   (the provider timestamp does not advance, so ``_newer`` is False).  326
   successful polls were therefore counted
   ``market_malformed_results_rejected``, never cleared the failure streak and
   never counted as completed work.

NOTHING here relaxes eligibility: no timestamp is written for an UNCHANGED
result, so freshness, ``all_present``, ``market_state`` and every tier /
activation decision derived from them are byte-identical to before.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PHX2.free_tier_producer.market_scheduler import (
    APPLY_OUTCOME_APPLIED,
    APPLY_OUTCOME_MALFORMED,
    APPLY_OUTCOME_UNCHANGED,
    APPLY_OUTCOMES,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    SOURCE_PAID_SINGLE,
)
from PHX2.tests.test_market_scheduler import (  # reuse the audited harness
    NOW,
    _observation,
    _scheduler,
    _view,
)

import sys

_PRODUCER = Path(__file__).resolve().parents[1] / "free_tier_producer"
if str(_PRODUCER) not in sys.path:
    sys.path.insert(0, str(_PRODUCER))

from free_tier_pricing_tail import (  # noqa: E402
    TAIL_ORIGIN_WATCHLIST,
    FreeTierPricingTail,
)


# --------------------------------------------------------------------------
# Defect A -- ATH telemetry projection
# --------------------------------------------------------------------------

CENTRAL_ATH = {
    "ath_price": "0.00015601574133061676",
    "ath_price_usd": "0.00015601574133061676",
    "ath_market_cap": "150041.14415541352",
    "ath_market_cap_usd": "150041.14415541352",
    "ath_timestamp": "2026-07-31T09:38:13Z",
    "ath_observed_at_utc": "2026-07-31T09:38:13Z",
    "ath_provider": "PAID_CURRENT_PRICE",
    "ath_observation_type": "PAID_CURRENT_PRICE",
    "ath_status": "PROVISIONAL",
    "ath_confirmed": False,
    "ath_hydration_status": "ATH_HYDRATION_PENDING",
    "ath_post_migration_complete": False,
    "ath_supply_basis": None,
}


class _Store:
    """Minimal central ATH store stand-in."""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self, mint):  # noqa: D401 - store protocol
        return dict(self._snapshot) if self._snapshot else {}


def _tail(tmp_path, snapshot, *, market=None):
    """A tail whose MARKET payload deliberately carries NO ATH fields."""

    payload = dict(market or {
        "current_price": "0.00001",
        "current_market_cap_usd": "9615",
        "liquidity_usd": "4200",
        "market_provider": "PAID_MARKET_PRIMARY",
        "market_state": "MARKET_READY",
        "market_reason_code": "REQUIRED_FIELDS_FRESH",
    })
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    clock = {"now": 1_000_000.0}
    tail = FreeTierPricingTail(
        out_dir=str(tmp_path),
        fetch_market_fn=lambda _m: dict(payload),
        now_epoch_fn=lambda: clock["now"],
        min_poll_interval_seconds=0.0,
        ath_store=_Store(snapshot),
    )
    tail._test_clock = clock  # type: ignore[attr-defined]
    return tail


def _records(tmp_path):
    path = Path(tmp_path) / "pricing_tail.jsonl"
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_central_ath_appears_identically_in_record_and_state(tmp_path):
    tail = _tail(tmp_path, CENTRAL_ATH)
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    assert tail.poll("2026-07-31T09:40:00Z") == 1

    record = _records(tmp_path)[-1]
    per_mint = tail.market_freshness()["per_mint"][0]

    for field in ("ath_price_usd", "ath_market_cap_usd",
                  "ath_observed_at_utc", "ath_observation_type"):
        assert record[field] == per_mint[field], field
        assert per_mint[field] is not None, field


def test_missing_raw_market_ath_does_not_erase_central_ath_telemetry(tmp_path):
    """The exact 2026-07-31 defect: market carries no ATH, telemetry went null."""

    tail = _tail(tmp_path, CENTRAL_ATH)
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    tail.poll("2026-07-31T09:40:00Z")

    per_mint = tail.market_freshness()["per_mint"][0]
    assert per_mint["ath_price_usd"] == CENTRAL_ATH["ath_price"]
    assert per_mint["ath_market_cap_usd"] == CENTRAL_ATH["ath_market_cap"]
    assert per_mint["ath_observation_type"] == "PAID_CURRENT_PRICE"


def test_newer_central_ath_replaces_the_older_telemetry_value(tmp_path):
    tail = _tail(tmp_path, CENTRAL_ATH)
    store = tail._ath_store
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    tail.poll("2026-07-31T09:40:00Z")
    assert tail.market_freshness()["per_mint"][0]["ath_market_cap_usd"] == (
        "150041.14415541352")

    advanced = dict(CENTRAL_ATH)
    advanced["ath_market_cap"] = "275000.5"
    advanced["ath_market_cap_usd"] = "275000.5"
    advanced["ath_timestamp"] = "2026-07-31T09:45:00Z"
    store._snapshot = advanced
    tail.poll("2026-07-31T09:45:30Z")

    per_mint = tail.market_freshness()["per_mint"][0]
    assert per_mint["ath_market_cap_usd"] == "275000.5"
    assert per_mint["ath_observed_at_utc"] == "2026-07-31T09:45:00Z"


def test_pending_ath_remains_explicitly_pending(tmp_path):
    tail = _tail(tmp_path, CENTRAL_ATH)
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    tail.poll("2026-07-31T09:40:00Z")
    per_mint = tail.market_freshness()["per_mint"][0]
    assert per_mint["ath_hydration_status"] == "ATH_HYDRATION_PENDING"
    assert per_mint["ath_post_migration_complete"] is False


def test_confirmed_and_provisional_remain_distinguishable(tmp_path):
    confirmed = dict(CENTRAL_ATH)
    confirmed.update({
        "ath_status": "CONFIRMED",
        "ath_confirmed": True,
        "ath_hydration_status": "ATH_HYDRATION_COMPLETE",
        "ath_post_migration_complete": True,
    })

    provisional_tail = _tail(tmp_path / "p", CENTRAL_ATH)
    provisional_tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    provisional_tail.poll("2026-07-31T09:40:00Z")
    provisional = provisional_tail.market_freshness()["per_mint"][0]

    confirmed_tail = _tail(tmp_path / "c", confirmed)
    confirmed_tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    confirmed_tail.poll("2026-07-31T09:40:00Z")
    resolved = confirmed_tail.market_freshness()["per_mint"][0]

    assert provisional["ath_status"] == "PROVISIONAL"
    assert provisional["ath_confirmed"] is False
    assert resolved["ath_status"] == "CONFIRMED"
    assert resolved["ath_confirmed"] is True
    assert provisional["ath_status"] != resolved["ath_status"]


def test_tracked_but_unpolled_mint_reports_explicit_nulls(tmp_path):
    tail = _tail(tmp_path, CENTRAL_ATH)
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    per_mint = tail.market_freshness()["per_mint"][0]
    for field in ("ath_price_usd", "ath_status", "ath_hydration_status"):
        assert field in per_mint, field
        assert per_mint[field] is None, field


def test_absent_central_ath_reports_null_without_crashing(tmp_path):
    tail = _tail(tmp_path, {})
    tail.track("mint-a", origin=TAIL_ORIGIN_WATCHLIST)
    assert tail.poll("2026-07-31T09:40:00Z") == 1
    per_mint = tail.market_freshness()["per_mint"][0]
    assert per_mint["ath_price_usd"] is None
    assert per_mint["ath_status"] is None


# --------------------------------------------------------------------------
# Defect B -- scheduler UNCHANGED vs MALFORMED accounting
# --------------------------------------------------------------------------

def _apply(scheduler, view, **kwargs):
    return scheduler.apply_observation(_observation(view, **kwargs))


def test_apply_outcome_vocabulary_is_closed():
    assert APPLY_OUTCOMES == (
        APPLY_OUTCOME_APPLIED, APPLY_OUTCOME_UNCHANGED, APPLY_OUTCOME_MALFORMED)


def test_unchanged_result_is_not_counted_malformed():
    """The exact defect: a quiet token's repeat answer was 'malformed'."""

    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)

    assert _apply(scheduler, view, sequence=1, price="1", mc="100") is True
    before = scheduler.stats()["market_malformed_results_rejected"]

    # Same provider timestamp, same values -- the token has not traded.
    assert _apply(scheduler, view, sequence=2, price="1", mc="100") is False

    stats = scheduler.stats()
    assert stats["market_malformed_results_rejected"] == before
    assert stats["market_results_unchanged"] >= 1


def test_unchanged_result_counts_as_a_completed_job():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1)
    completed = scheduler.stats()["market_scheduler_jobs_completed"]

    _apply(scheduler, view, sequence=2)
    assert scheduler.stats()["market_scheduler_jobs_completed"] == completed + 1


def test_unchanged_result_clears_the_failure_streak():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1)

    scheduler._record_failure(view.mint, FIELD_PRICE_MC, "PROVIDER_STALE")
    assert scheduler._state[view.mint].failure_count == 1

    _apply(scheduler, view, sequence=2)
    state = scheduler._state[view.mint]
    assert state.failure_count == 0
    assert state.last_request_error is None


def test_unchanged_result_does_not_mutate_stored_values_or_freshness():
    """Eligibility must be byte-identical: no timestamp is written."""

    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, price="1", mc="100")
    _apply(scheduler, view, field=FIELD_OVERVIEW, sequence=2, mc="100",
           liquidity="5000")
    before = scheduler.snapshot(view.mint)

    _apply(scheduler, view, sequence=3, price="1", mc="100")
    after = scheduler.snapshot(view.mint)

    for field in ("current_price", "current_market_cap_usd", "liquidity_usd",
                  "price_observed_at_utc", "market_cap_observed_at_utc",
                  "liquidity_observed_at_utc", "price_fresh", "market_cap_fresh",
                  "liquidity_fresh", "all_present", "market_state",
                  "market_reason_code"):
        assert before[field] == after[field], field


def test_genuinely_malformed_result_is_still_rejected():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    before = scheduler.stats()["market_malformed_results_rejected"]

    # No usable positive value at all.
    assert _apply(scheduler, view, sequence=1, price=None, mc=None) is False
    stats = scheduler.stats()
    assert stats["market_malformed_results_rejected"] == before + 1
    assert stats["market_results_unchanged"] == 0


def test_malformed_and_unchanged_are_separately_attributed():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, price="1", mc="100")
    _apply(scheduler, view, sequence=2, price="1", mc="100")      # unchanged
    _apply(scheduler, view, sequence=3, price=None, mc=None)      # malformed

    stats = scheduler.stats()
    assert stats["market_results_unchanged"] == 1
    assert stats["market_malformed_results_rejected"] == 1


def test_out_of_order_protection_is_preserved():
    """An older result must still not overwrite newer stored data."""

    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, source_at=NOW, price="5", mc="500")

    assert _apply(scheduler, view, sequence=2, source_at=NOW - 60,
                  price="9", mc="900") is False
    snapshot = scheduler.snapshot(view.mint)
    assert (snapshot["current_price"], snapshot["current_market_cap_usd"]) == (
        "5", "500")


def test_a_newer_result_still_applies_normally():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, source_at=NOW - 10, price="1", mc="100")

    assert _apply(scheduler, view, sequence=2, source_at=NOW, price="2",
                  mc="200") is True
    snapshot = scheduler.snapshot(view.mint)
    assert (snapshot["current_price"], snapshot["current_market_cap_usd"]) == (
        "2", "200")


def test_quiet_token_does_not_accumulate_malformed_rejections():
    """Preserved-run shape: many repeat polls of a token that never trades."""

    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, price="1", mc="100")

    for sequence in range(2, 42):
        _apply(scheduler, view, sequence=sequence, price="1", mc="100")

    stats = scheduler.stats()
    assert stats["market_malformed_results_rejected"] == 0
    assert stats["market_results_unchanged"] == 40
    assert scheduler._state[view.mint].failure_count == 0


def test_job_accounting_identity_holds_under_mixed_outcomes():
    """submitted == settled + cancelled + queued + inflight, unaccounted == 0."""

    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply(scheduler, view, sequence=1, price="1", mc="100")
    _apply(scheduler, view, sequence=2, price="1", mc="100")
    _apply(scheduler, view, sequence=3, price=None, mc=None)

    assert scheduler.stats()["market_scheduler_jobs_unaccounted"] == 0
