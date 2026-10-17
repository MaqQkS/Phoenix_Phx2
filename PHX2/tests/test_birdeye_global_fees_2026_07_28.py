"""2026-07-28 Birdeye Global Fees observe-only telemetry.

Locks the capability-probe-proven contract:

1. ``global_fees_paid`` is a top-level JSON number on the Token Overview
   ``data`` object PHX2 ALREADY fetches during market enrichment; it equals
   the dedicated single-token fee endpoint's ``alltime``
   ``sum_global_fee_paid_amount_sol`` exactly (unit therefore contract-proven
   SOL, interval contract-proven all-time), so production adds ZERO provider
   requests.
2. The canonical per-mint tracker is observe-only: exact-mint merge, survives
   snapshot replacement / recreation / scheduler handoff, discloses provider
   regressions, and never gates eligibility, tiering, risk, structure, or
   dispatch.
3. Telegram renders one clean ``💸 Global Fees: <amount> SOL`` line directly
   below the State section ONLY for a valid, display-fresh value; every other
   state omits the line entirely while the closed-set reason stays on the
   artifact surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import json

import pytest

from PHX2.delivery.telegram_adapter import (
    GLOBAL_FEES_DISPLAY_MAX_AGE_SECONDS,
    _compact_sol,
    _global_fees_display,
    build_ping_data,
)
from PHX2.delivery.telegram_composer import (
    TELEGRAM_INTERNAL_MAX_CHARACTERS,
    TelegramMessageTooLong,
    TelegramPingData,
    compose_telegram_ping,
)
from PHX2.free_tier_producer.compat import production_live_artifacts
from PHX2.free_tier_producer.compat.build29_cap1_artifacts import (
    run_redaction_scan,
)
from PHX2.free_tier_producer.global_fees import (
    GLOBAL_FEES_ACCESS_AUTH_FAILURE,
    GLOBAL_FEES_ACCESS_AVAILABLE,
    GLOBAL_FEES_ACCESS_PLAN_FORBIDDEN,
    GLOBAL_FEES_ACCESS_RATE_LIMITED,
    GLOBAL_FEES_ACCESS_RESPONSE_INVALID,
    GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW,
    GLOBAL_FEES_INTERVAL_ALLTIME,
    GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY,
    GLOBAL_FEES_STATUS_FIELD_MISSING,
    GLOBAL_FEES_STATUS_NOT_REQUESTED,
    GLOBAL_FEES_STATUS_PROVIDER_ERROR,
    GLOBAL_FEES_STATUS_RATE_LIMITED,
    GLOBAL_FEES_STATUS_STALE,
    GLOBAL_FEES_STATUS_VALID,
    GLOBAL_FEES_STATUS_VALUE_INVALID,
    GLOBAL_FEES_STATUS_VALUE_NEGATIVE,
    GLOBAL_FEES_STATUS_VALUE_NONFINITE,
    GLOBAL_FEES_STATUS_VALUE_NULL,
    GlobalFeesTracker,
    build_overview_global_fees_observation,
    classify_dedicated_fee_access,
    classify_global_fees_value,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.free_tier_producer.ping_quality_review import (
    build_ping_quality_record,
    ping_quality_record_is_redaction_safe,
)
from PHX2.stage29.birdeye_constants import BIRDEYE_ALLOWED_PATHS
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)


APPA_MINT = "38K55aqSCMrahqPBTZLLa9DvKygaSG4NqhxXvGE4pump"
APPA_PAIR = "A6p5CJUFGdzkSPVMT7rsRFCwizfBoj8BEsoMLqPygvBN"
LIVE_MINT = "335SdxzgdttfbNyKWzkdphiCWKTZduK7XJE8rL6Spump"
LIVE_PAIR = "3EVqNTpj9CUhD2AAPTKLaEzorKAo3zyvkdJMbHDJE2Ns"

NOW = "2026-07-28T06:05:37Z"
NOW_EPOCH = datetime(2026, 7, 28, 6, 5, 37, tzinfo=timezone.utc).timestamp()

#: Probe-preserved values (2026-07-28 capability probe): Token Overview
#: ``global_fees_paid`` equals the dedicated endpoint's alltime
#: ``sum_global_fee_paid_amount_sol`` for both probe mints.
APPA_GLOBAL_FEES = 1.498774236
LIVE_GLOBAL_FEES = 3.750421734


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class _Clock:
    def __init__(self, start: float = NOW_EPOCH) -> None:
        self.epoch = start

    def now_iso(self) -> str:
        return _iso(self.epoch)


def _valid_snapshot(
    mint: str = LIVE_MINT,
    *,
    value: str = "14.8",
    observed_at: str = NOW,
    status: str = GLOBAL_FEES_STATUS_VALID,
    **overrides,
):
    snapshot = {
        "schema_version": "phx2_global_fees_v1",
        "token_mint": mint,
        "global_fees_paid_sol": value,
        "global_fees_interval": GLOBAL_FEES_INTERVAL_ALLTIME,
        "global_fees_source": GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY,
        "global_fees_endpoint_source": GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW,
        "global_fees_status": status,
        "global_fees_observed_at_utc": observed_at,
        "global_fees_age_seconds": 0.0,
        "global_fees_http_status_class": "2XX",
        "global_fees_failure_reason": None,
        "global_fees_raw_type": "number",
        "global_fees_request_reused": True,
        "global_fees_display_fresh_seconds": 300.0,
        "global_fees_provider_coverage_note": (
            "ALL_TIME_GLOBAL_FEES_SOL_FROM_EXISTING_OVERVIEW_SNAPSHOT"),
        "global_fees_regression_detected": False,
        "global_fees_regression_prior_value_sol": None,
        "global_fees_regression_prior_observed_at_utc": None,
        "global_fees_regression_observed_at_utc": None,
        "global_fees_observation_count": 1,
        "observe_only": True,
    }
    snapshot.update(overrides)
    return snapshot


# =========================================================================
# 1. Raw-value classification (contract-proven: JSON number, SOL, alltime)
# =========================================================================


@pytest.mark.parametrize(("raw", "expected_status", "expected_text"), (
    (APPA_GLOBAL_FEES, GLOBAL_FEES_STATUS_VALID, "1.498774236"),
    (LIVE_GLOBAL_FEES, GLOBAL_FEES_STATUS_VALID, "3.750421734"),
    (0, GLOBAL_FEES_STATUS_VALID, "0"),
    (125, GLOBAL_FEES_STATUS_VALID, "125"),
    (None, GLOBAL_FEES_STATUS_VALUE_NULL, None),
    (True, GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    (False, GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    (-1.5, GLOBAL_FEES_STATUS_VALUE_NEGATIVE, None),
    (float("nan"), GLOBAL_FEES_STATUS_VALUE_NONFINITE, None),
    (float("inf"), GLOBAL_FEES_STATUS_VALUE_NONFINITE, None),
    (float("-inf"), GLOBAL_FEES_STATUS_VALUE_NONFINITE, None),
    # The 2026-07-28 probe proved a JSON number; strings are NOT
    # contract-proven and must be rejected, never coerced.
    ("14.8", GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    ("", GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    ("14.8 SOL", GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    ({"value": 14.8}, GLOBAL_FEES_STATUS_VALUE_INVALID, None),
    ([14.8], GLOBAL_FEES_STATUS_VALUE_INVALID, None),
))
def test_raw_value_classification_closed_set(raw, expected_status, expected_text):
    status, text, _raw_type = classify_global_fees_value(
        raw, field_present=True)
    assert status == expected_status
    assert text == expected_text


def test_missing_field_classifies_field_missing():
    status, text, raw_type = classify_global_fees_value(
        None, field_present=False)
    assert status == GLOBAL_FEES_STATUS_FIELD_MISSING
    assert text is None
    assert raw_type == "missing"


def test_value_is_sol_passthrough_never_lamports_converted():
    # 1.498774236 must stay 1.498774236 SOL — any lamports interpretation
    # would multiply or divide by 1e9.
    status, text, _ = classify_global_fees_value(
        APPA_GLOBAL_FEES, field_present=True)
    assert status == GLOBAL_FEES_STATUS_VALID
    assert Decimal(text) == Decimal("1.498774236")


@pytest.mark.parametrize(("status_code", "verdict"), (
    (200, GLOBAL_FEES_ACCESS_AVAILABLE),
    (403, GLOBAL_FEES_ACCESS_PLAN_FORBIDDEN),
    (401, GLOBAL_FEES_ACCESS_AUTH_FAILURE),
    (429, GLOBAL_FEES_ACCESS_RATE_LIMITED),
    (500, GLOBAL_FEES_ACCESS_RESPONSE_INVALID),
    (None, GLOBAL_FEES_ACCESS_RESPONSE_INVALID),
    (True, GLOBAL_FEES_ACCESS_RESPONSE_INVALID),
))
def test_dedicated_endpoint_access_classification(status_code, verdict):
    assert classify_dedicated_fee_access(status_code) == verdict


# =========================================================================
# 2. Overview transport: fees ride the existing response, zero extra calls
# =========================================================================


def _result(body=None, *, refusal=BIRDEYE_REFUSAL_REASON_NONE, status=200):
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=refusal,
        http_status_code=status,
        body=body,
        fetched_at_utc="1970-01-01T00:16:40Z",
    )


class _SequenceTransport:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


def test_overview_plane_populates_global_fees_with_zero_extra_requests():
    inner = _SequenceTransport([
        _result({"success": True, "data": {
            "address": LIVE_MINT, "mc": "50010", "liquidity": "9000",
            "global_fees_paid": LIVE_GLOBAL_FEES,
        }}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 1000,
    )
    overview = transport.fetch_overview_plane(LIVE_MINT, timeout_seconds=1)
    assert overview["current_market_cap_usd"] == "50010"
    fees = overview["global_fees"]
    assert fees["token_mint"] == LIVE_MINT
    assert fees["global_fees_status"] == GLOBAL_FEES_STATUS_VALID
    assert fees["global_fees_paid_sol"] == "3.750421734"
    assert fees["global_fees_interval"] == GLOBAL_FEES_INTERVAL_ALLTIME
    assert fees["global_fees_source"] == GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY
    assert fees["global_fees_endpoint_source"] == (
        GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW)
    assert fees["global_fees_request_reused"] is True
    assert fees["global_fees_http_status_class"] == "2XX"
    # THE reuse proof: exactly one HTTP call, to the overview path only.
    assert [call["path"] for call in inner.calls] == ["/defi/token_overview"]


def test_overview_plane_missing_field_is_disclosed_not_fabricated():
    inner = _SequenceTransport([
        _result({"success": True, "data": {
            "address": LIVE_MINT, "mc": "50010", "liquidity": "9000",
        }}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 1000,
    )
    fees = transport.fetch_overview_plane(
        LIVE_MINT, timeout_seconds=1)["global_fees"]
    assert fees["global_fees_status"] == GLOBAL_FEES_STATUS_FIELD_MISSING
    assert fees["global_fees_paid_sol"] is None
    assert fees["global_fees_raw_type"] == "missing"
    assert len(inner.calls) == 1


def test_wrong_mint_overview_response_never_yields_fees():
    inner = _SequenceTransport([
        _result({"success": True, "data": {
            "address": APPA_MINT, "mc": "50010", "liquidity": "9000",
            "global_fees_paid": 99.0,
        }}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 1000,
    )
    assert transport.fetch_overview_plane(LIVE_MINT, timeout_seconds=1) == {
        "mint": LIVE_MINT, "_market_failure_reason": "PROVIDER_WRONG_MINT"}


def test_dedicated_fee_endpoint_is_not_in_the_allowed_path_surface():
    # Production request surface stays locked at exactly the five sanctioned
    # paths (three legacy + the two 2026-08-03 V3 candle paths): the
    # dedicated fee endpoint (and any multi-token business endpoint) is
    # NEVER requested while the overview field is available.
    assert BIRDEYE_ALLOWED_PATHS == (
        "/defi/price", "/defi/ohlcv", "/defi/token_overview",
        "/defi/v3/ohlcv/pair", "/defi/v3/ohlcv")
    assert not any("fee" in path for path in BIRDEYE_ALLOWED_PATHS)
    assert not any("multi" in path for path in BIRDEYE_ALLOWED_PATHS)


# =========================================================================
# 3. Canonical tracker: exact-mint merge, lifecycle survival, regression
# =========================================================================


def _observation(mint=LIVE_MINT, *, value=LIVE_GLOBAL_FEES, observed_at=NOW,
                 status=None):
    data = {"global_fees_paid": value} if value is not ... else {}
    observation = build_overview_global_fees_observation(
        mint=mint, data=data, observed_at_utc=observed_at)
    if status is not None:
        observation["global_fees_status"] = status
    return observation


def test_tracker_exact_mint_merge_and_snapshot_projection():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    assert tracker.observe_overview(LIVE_MINT, _observation()) is True
    snap = tracker.snapshot(LIVE_MINT)
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_VALID
    assert snap["global_fees_paid_sol"] == "3.750421734"
    assert snap["global_fees_interval"] == "alltime"
    assert snap["global_fees_observed_at_utc"] == NOW
    assert snap["global_fees_age_seconds"] == 0.0
    assert snap["global_fees_request_reused"] is True
    assert snap["observe_only"] is True


def test_tracker_rejects_wrong_mint_observations():
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    assert tracker.observe_overview(
        APPA_MINT, _observation(mint=LIVE_MINT)) is False
    assert tracker.snapshot(APPA_MINT)["global_fees_status"] == (
        GLOBAL_FEES_STATUS_NOT_REQUESTED)
    assert tracker.stats()["global_fees_wrong_mint_rejected"] == 1


def test_tracker_unknown_mint_reports_not_requested_without_mutation():
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    for _ in range(3):
        snap = tracker.snapshot(LIVE_MINT)
        assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_NOT_REQUESTED
        assert snap["global_fees_paid_sol"] is None
    # Reading state never creates attempts, retries, or entries.
    assert tracker.stats()["global_fees_observations_total"] == 0


def test_tracker_survives_candidate_snapshot_replacement_and_handoff():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    tracker.observe_overview(LIVE_MINT, _observation())
    # Candidate dict replaced / recreated / handed off between schedulers:
    # each new stamping reads the canonical tracker, so the value survives
    # every transient-dict lifecycle event.
    first_candidate = {"token_mint": LIVE_MINT,
                       "global_fees": tracker.snapshot(LIVE_MINT)}
    replacement_candidate = {"token_mint": LIVE_MINT}
    replacement_candidate["global_fees"] = tracker.snapshot(LIVE_MINT)
    assert (replacement_candidate["global_fees"]["global_fees_paid_sol"]
            == first_candidate["global_fees"]["global_fees_paid_sol"]
            == "3.750421734")


def test_tracker_invalid_observation_never_erases_prior_valid_value():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    tracker.observe_overview(LIVE_MINT, _observation())
    later = _iso(NOW_EPOCH + 30)
    tracker.observe_overview(
        LIVE_MINT, _observation(value=None, observed_at=later))
    snap = tracker.snapshot(LIVE_MINT)
    assert snap["global_fees_paid_sol"] == "3.750421734"
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_VALID
    assert snap["global_fees_failure_reason"] == (
        GLOBAL_FEES_STATUS_VALUE_NULL)


def test_tracker_scheduler_failures_map_closed_and_preserve_value():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    tracker.observe_scheduler_failure(
        APPA_MINT, failure_reason="PROVIDER_RATE_LIMIT")
    assert tracker.snapshot(APPA_MINT)["global_fees_status"] == (
        GLOBAL_FEES_STATUS_RATE_LIMITED)
    tracker.observe_scheduler_failure(
        APPA_MINT, failure_reason="PROVIDER_5XX")
    snap = tracker.snapshot(APPA_MINT)
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_PROVIDER_ERROR
    assert snap["global_fees_failure_reason"] == "PROVIDER_5XX"
    # A failure after a valid value keeps the value; only telemetry moves.
    tracker.observe_overview(LIVE_MINT, _observation())
    tracker.observe_scheduler_failure(
        LIVE_MINT, failure_reason="PROVIDER_TIMEOUT")
    snap = tracker.snapshot(LIVE_MINT)
    assert snap["global_fees_paid_sol"] == "3.750421734"
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_VALID
    assert snap["global_fees_failure_reason"] == "PROVIDER_TIMEOUT"


def test_tracker_stale_projection_and_later_valid_refresh():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    tracker.observe_overview(LIVE_MINT, _observation())
    clock.epoch = NOW_EPOCH + 301
    snap = tracker.snapshot(LIVE_MINT)
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_STALE
    assert snap["global_fees_paid_sol"] == "3.750421734"
    assert snap["global_fees_age_seconds"] == 301.0
    refreshed_at = _iso(NOW_EPOCH + 290)
    tracker.observe_overview(
        LIVE_MINT, _observation(value=3.9, observed_at=refreshed_at))
    snap = tracker.snapshot(LIVE_MINT)
    assert snap["global_fees_status"] == GLOBAL_FEES_STATUS_VALID
    assert snap["global_fees_paid_sol"] == "3.9"
    assert snap["global_fees_age_seconds"] == 11.0


def test_tracker_provider_regression_is_disclosed_never_silently_maxed():
    clock = _Clock()
    tracker = GlobalFeesTracker(now_iso_fn=clock.now_iso)
    tracker.observe_overview(LIVE_MINT, _observation(value=3.750421734))
    later = _iso(NOW_EPOCH + 60)
    clock.epoch = NOW_EPOCH + 60
    tracker.observe_overview(
        LIVE_MINT, _observation(value=1.2, observed_at=later))
    snap = tracker.snapshot(LIVE_MINT)
    # Documented rule: the latest contract-valid observation is adopted and
    # BOTH observations stay disclosed; the value is never re-maxed.
    assert snap["global_fees_paid_sol"] == "1.2"
    assert snap["global_fees_regression_detected"] is True
    assert snap["global_fees_regression_prior_value_sol"] == "3.750421734"
    assert snap["global_fees_regression_prior_observed_at_utc"] == NOW
    assert snap["global_fees_regression_observed_at_utc"] == later
    assert tracker.stats()["global_fees_regressions_detected"] == 1


def test_tracker_merge_matches_live_session_apply_wiring():
    """Merging ``observation.values['global_fees']`` is exactly what
    ``_scheduler_apply_observation`` does for enriched candidates."""

    overview_values = {
        "mint": LIVE_MINT,
        "current_market_cap_usd": "25737",
        "liquidity_usd": "9748",
        "token_name": "Three Three Five",
        "token_symbol": "TTF",
        "global_fees": _observation(),
    }
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    fees_observation = overview_values.get("global_fees")
    assert isinstance(fees_observation, dict)
    tracker.observe_overview(LIVE_MINT, fees_observation)
    assert tracker.snapshot(LIVE_MINT)["global_fees_paid_sol"] == (
        "3.750421734")


# =========================================================================
# 4. Compact SOL formatter
# =========================================================================


@pytest.mark.parametrize(("value", "expected"), (
    ("0.004", "0.004"),
    ("0.12", "0.12"),
    ("1.8", "1.8"),
    ("14.8", "14.8"),
    ("125", "125"),
    ("1240", "1,240"),
    ("0", "0"),
    ("2.0", "2"),
    ("1.498774236", "1.5"),
    ("3.750421734", "3.8"),
    ("0.000073889", "0.000074"),
    ("0.999", "1"),
    ("99.96", "100"),
    ("999999", "999,999"),
))
def test_compact_sol_formatter(value, expected):
    rendered = _compact_sol(Decimal(value))
    assert rendered == expected
    assert "E" not in rendered and "e" not in rendered


# =========================================================================
# 5. Compose-side display gate
# =========================================================================


def test_display_gate_renders_only_valid_fresh_exact_mint_state():
    candidate = {"global_fees": _valid_snapshot()}
    display, snapshot, reason = _global_fees_display(
        candidate, LIVE_MINT, NOW)
    assert display == "14.8 SOL"
    assert reason is None
    assert snapshot is candidate["global_fees"]


@pytest.mark.parametrize(("mutation", "expected_reason"), (
    ({"global_fees_status": "FIELD_MISSING"}, "GLOBAL_FEES_FIELD_MISSING"),
    ({"global_fees_status": "VALUE_NULL"}, "GLOBAL_FEES_VALUE_NULL"),
    ({"global_fees_status": "VALUE_INVALID"}, "GLOBAL_FEES_VALUE_INVALID"),
    ({"global_fees_status": "VALUE_NEGATIVE"}, "GLOBAL_FEES_VALUE_NEGATIVE"),
    ({"global_fees_status": "VALUE_NONFINITE"},
     "GLOBAL_FEES_VALUE_NONFINITE"),
    ({"global_fees_status": "STALE"}, "GLOBAL_FEES_STALE"),
    ({"global_fees_status": "PLAN_FORBIDDEN"}, "GLOBAL_FEES_PLAN_FORBIDDEN"),
    ({"global_fees_status": "RATE_LIMITED"}, "GLOBAL_FEES_RATE_LIMITED"),
    ({"global_fees_status": "PROVIDER_ERROR"}, "GLOBAL_FEES_PROVIDER_ERROR"),
    ({"global_fees_status": "NOT_REQUESTED"}, "GLOBAL_FEES_NOT_REQUESTED"),
    ({"global_fees_paid_sol": None}, "GLOBAL_FEES_VALUE_INVALID"),
    ({"global_fees_paid_sol": "-3"}, "GLOBAL_FEES_VALUE_INVALID"),
    ({"global_fees_paid_sol": "not-a-number"}, "GLOBAL_FEES_VALUE_INVALID"),
    ({"global_fees_interval": "24h"}, "GLOBAL_FEES_VALUE_INVALID"),
    ({"global_fees_observed_at_utc": None}, "GLOBAL_FEES_STALE"),
))
def test_display_gate_fails_closed_per_state(mutation, expected_reason):
    candidate = {"global_fees": _valid_snapshot(**mutation)}
    display, _snapshot, reason = _global_fees_display(
        candidate, LIVE_MINT, NOW)
    assert display == ""
    assert reason == expected_reason


def test_display_gate_compose_time_staleness_recheck():
    # Snapshot stamped VALID earlier, but compose happens later than the
    # display bound: the compose-time re-check omits the line.
    stale_now = _iso(NOW_EPOCH + GLOBAL_FEES_DISPLAY_MAX_AGE_SECONDS + 1)
    candidate = {"global_fees": _valid_snapshot()}
    display, _snapshot, reason = _global_fees_display(
        candidate, LIVE_MINT, stale_now)
    assert display == ""
    assert reason == "GLOBAL_FEES_STALE"
    # Future-skewed observation is equally refused.
    skewed = {"global_fees": _valid_snapshot(
        observed_at=_iso(NOW_EPOCH + 120))}
    display, _snapshot, reason = _global_fees_display(skewed, LIVE_MINT, NOW)
    assert display == ""
    assert reason == "GLOBAL_FEES_STALE"


def test_display_gate_rejects_wrong_mint_and_missing_snapshot():
    display, snapshot, reason = _global_fees_display({}, LIVE_MINT, NOW)
    assert (display, snapshot, reason) == (
        "", None, "GLOBAL_FEES_NOT_REQUESTED")
    candidate = {"global_fees": _valid_snapshot(mint=APPA_MINT)}
    display, snapshot, reason = _global_fees_display(
        candidate, LIVE_MINT, NOW)
    assert (display, snapshot, reason) == (
        "", None, "GLOBAL_FEES_NOT_REQUESTED")


# =========================================================================
# 6. Telegram body contract
# =========================================================================


def _delivery_inputs(*, provenance="LIVE_YELLOWSTONE", shadow=False,
                     global_fees=None, migration_offset_minutes=41):
    migration = datetime(2026, 7, 28, 5, 24, 37, tzinfo=timezone.utc)
    now = migration + timedelta(minutes=migration_offset_minutes)
    fee = SimpleNamespace(
        candidate_mint=LIVE_MINT, proof_digest="fee-proof",
        total_fees=Decimal("8.39"), lp_fees=Decimal("5.55"),
        protocol_fees=Decimal("2.84"), creator_fees=Decimal("0.00"),
        event_pace_per_minute=Decimal("22"), event_count=5633,
        fee_gate_label="PASS" if not shadow else "SCAM Likely",
        fee_gate_score=2 if not shadow else 6,
        fee_gate_reasons=("balanced",) if not shadow else ("sticky_lock",),
        balanced_fees=not shadow,
        bribe_share_pct=Decimal("0.8"), creator_share=Decimal("0.01"),
        bribes_per_transaction=Decimal("0.00007102"),
        first_observed_at_utc=(migration.isoformat().replace("+00:00", "Z")),
        last_observed_at_utc=(now.isoformat().replace("+00:00", "Z")),
        ante_last20_median=Decimal("0.000058"),
        ante_last20_p25=Decimal("0.000028"),
        ante_last20_p75=Decimal("0.000551"),
        ante_last20_sample_count=20,
        ante_5m_median=Decimal("0.000029"),
        ante_5m_p25=Decimal("0.000018"),
        ante_5m_p75=Decimal("0.0000594"),
        ante_5m_sample_count=322,
        ante_5m_base_fee_coverage=Decimal("1"),
        priority_fee_median_lamports=11574,
        priority_fee_sample_count=20,
        ante_5m_shape=None, ante_5m_shape_rule=None,
        ante_last20_shape=None, ante_last20_shape_rule=None,
    )
    if shadow:
        security = SimpleNamespace(
            fee_snapshot=fee, lp_snapshot=None,
            lp_integrity_mode="DISABLED_SINGLE_STREAM",
            verdict="ALLOW", proof_digest="security-proof",
            phx1_structural_policy="SHADOW",
            original_phx1_structural_verdict="HARD_BLOCK",
            effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
            shadow_warning_reason_tokens=("PHX1_FEE_GATE_SCAM_LIKELY",),
            organicity_status="UNVERIFIED",
            manual_review_required=True,
            phx1_policy_digest="policy-digest",
        )
    else:
        security = SimpleNamespace(
            fee_snapshot=fee, lp_snapshot=None,
            lp_integrity_mode="DISABLED_SINGLE_STREAM",
            verdict="ALLOW", proof_digest="security-proof",
            phx1_structural_policy="SHADOW",
            original_phx1_structural_verdict="PASS",
            effective_phx1_policy_verdict="PASS",
            shadow_warning_reason_tokens=(),
            organicity_status="UNVERIFIED",
            manual_review_required=False,
            phx1_policy_digest="policy-digest",
        )
    candidate = {
        "token_mint": LIVE_MINT,
        "discovery_provenance": provenance,
        "token_name": "Three Three Five",
        "token_symbol": "TTF",
        "symbol_or_name": "TTF",
        "pair_address": LIVE_PAIR,
        "migration_time_utc": migration.isoformat().replace("+00:00", "Z"),
        "canonical_volume_5m": {
            "schema_version": "phx2_canonical_swap_volume_v1",
            "status": "INSUFFICIENT_DATA",
            "mint": LIVE_MINT,
            "window_seconds": 300,
            "gross_volume_usd": None,
            "net_quote_flow_usd": None,
            "sample_count": 0,
            "observe_only": True,
        },
        "fee_gate_lifecycle": {
            "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
            "lifecycle_state": ("DURABLE_SCAM_LOCKED" if shadow
                                else "FRESH_CONFIRMED"),
            "evidence_proof_digest": "fee-proof",
        },
    }
    if global_fees is not None:
        candidate["global_fees"] = global_fees
    delivery_context = {
        "candidate": candidate,
        "market_context": {
            "current_market_cap_usd": "86400",
            "liquidity_usd": "24407",
            "central_ath": {"ath_market_cap": "179400"},
            "risk_assessment": {"risk_label": "RISK_LOW",
                                "risk_reasons": []},
        },
        "activation": {"migration_market_cap_usd": "30020"},
        "security_decision": security,
    }
    snapshot = SimpleNamespace(
        token_mint=LIVE_MINT, tier_token="Tier 1",
        current_market_cap_usd="86400")
    return snapshot, delivery_context, now.isoformat().replace("+00:00", "Z")


def test_valid_value_renders_directly_below_state():
    snapshot, delivery_context, now_utc = _delivery_inputs(
        global_fees=_valid_snapshot(observed_at="2026-07-28T06:05:00Z"))
    data = build_ping_data(
        mint=LIVE_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    assert data.global_fees_display == "14.8 SOL"
    body = compose_telegram_ping(data).text
    lines = body.splitlines()
    # 2026-07-29 final cleanup: Global Fees renders immediately after the
    # State section (Participation renders nowhere).
    lp_index = next(
        index for index, line in enumerate(lines) if line.startswith("• LP:"))
    assert lines[lp_index + 1] == ""
    assert lines[lp_index + 2] == "💸 Global Fees: 14.8 SOL"
    assert lines[lp_index + 3] == ""
    assert lines[lp_index + 4] == "<b>🛑 Structure</b>"
    assert "Participation" not in body
    assert "global_fees" not in data.field_reason_codes
    assert production_live_artifacts.scan_text(body) == []


def test_unavailable_value_omits_the_line_and_spacing_entirely():
    for fees in (
        None,
        _valid_snapshot(status="FIELD_MISSING", value=None),
        _valid_snapshot(status="STALE"),
        _valid_snapshot(value="not-a-number"),
        _valid_snapshot(mint=APPA_MINT),
    ):
        snapshot, delivery_context, now_utc = _delivery_inputs(
            global_fees=fees)
        data = build_ping_data(
            mint=LIVE_MINT, composed_snapshot=snapshot,
            delivery_context=delivery_context, now_utc=now_utc)
        assert data.global_fees_display == ""
        body = compose_telegram_ping(data).text
        assert "Global Fees" not in body
        assert "💸" not in body
        assert "\n\n\n" not in body
        lines = body.splitlines()
        lp_index = next(
            index for index, line in enumerate(lines)
            if line.startswith("• LP:"))
        assert lines[lp_index + 1] == ""
        assert lines[lp_index + 2] == "<b>🛑 Structure</b>"
        assert data.field_reason_codes["global_fees"][0].startswith(
            "GLOBAL_FEES_")


def test_restart_backfill_alert_carries_global_fees_identically():
    snapshot, delivery_context, now_utc = _delivery_inputs(
        provenance="DEXSCREENER_RESTART_BACKFILL",
        global_fees=_valid_snapshot(observed_at="2026-07-28T06:05:00Z"))
    data = build_ping_data(
        mint=LIVE_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    body = compose_telegram_ping(data).text
    assert "💸 Global Fees: 14.8 SOL" in body.splitlines()
    assert "• Coverage: Partial (restart backfill)" in body.splitlines()


def test_scam_shadow_alert_carries_global_fees_and_policy_line():
    snapshot, delivery_context, now_utc = _delivery_inputs(
        shadow=True,
        global_fees=_valid_snapshot(
            value="0.004", observed_at="2026-07-28T06:05:00Z"))
    data = build_ping_data(
        mint=LIVE_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    body = compose_telegram_ping(data).text
    lines = body.splitlines()
    assert "💸 Global Fees: 0.004 SOL" in lines
    assert "• Policy: SHADOW BLOCK — fee gate scam likely" in lines


def test_structural_pass_alert_body_stays_clean_of_internal_text():
    snapshot, delivery_context, now_utc = _delivery_inputs(
        global_fees=_valid_snapshot(observed_at="2026-07-28T06:05:00Z"))
    data = build_ping_data(
        mint=LIVE_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    body = compose_telegram_ping(data).text
    # Surrounding sections follow the 2026-07-29 final cleanup contract:
    # Participation renders nowhere (it stays artifact-only telemetry).
    lines = body.splitlines()
    assert "Participation" not in body
    assert "SOL/min" not in body
    assert "Events:" not in body
    assert "• Floor: -52% | Age: 41m | Vol 5m: —" in lines
    assert "• LP: —" in lines
    # No provider/internal implementation text may reach the operator body.
    for banned in (
        "TOKEN_OVERVIEW",
        "TOKEN_FEE_SINGLE",
        "PAID_MARKET_PRIMARY",
        "alltime",
        "GLOBAL_FEES_",
        "NOT_REQUESTED",
        "PLAN_FORBIDDEN",
        "RATE_LIMITED",
        "FIELD_MISSING",
        "REQUEST_REUSED",
        "ALL_TIME_GLOBAL_FEES_SOL_FROM_EXISTING_OVERVIEW_SNAPSHOT",
        "2XX",
        "CU",
        "birdeye",
        "Birdeye",
        "BIRDEYE",
    ):
        assert banned not in body, banned
    assert production_live_artifacts.scan_text(body) == []


def test_message_length_contract_and_fail_closed_overlength():
    snapshot, delivery_context, now_utc = _delivery_inputs(
        global_fees=_valid_snapshot(
            value="999999", observed_at="2026-07-28T06:05:00Z"))
    data = build_ping_data(
        mint=LIVE_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    composed = compose_telegram_ping(data)
    assert "💸 Global Fees: 999,999 SOL" in composed.text.splitlines()
    assert composed.rendered_character_count <= (
        TELEGRAM_INTERNAL_MAX_CHARACTERS)
    # The existing overlength contract is unchanged and stays fail-closed:
    # no degradation ladder exists, so an overlong body refuses compose
    # entirely (Global Fees receives no special retention).
    overlong = TelegramPingData(
        **{**_ping_data_kwargs(data), "structure_read": "x" * 4200})
    with pytest.raises(TelegramMessageTooLong):
        compose_telegram_ping(overlong)


def _ping_data_kwargs(data: TelegramPingData) -> dict:
    from dataclasses import fields as dataclass_fields
    return {f.name: getattr(data, f.name) for f in dataclass_fields(
        TelegramPingData)}


# =========================================================================
# 7. Artifact contracts
# =========================================================================


def test_quality_record_preserves_global_fees_diagnostics():
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    tracker.observe_overview(LIVE_MINT, _observation())
    candidate = {
        "candidate_id": "cand-1",
        "token_mint": LIVE_MINT,
        "discovery_provenance": "LIVE_YELLOWSTONE",
        "global_fees": tracker.snapshot(LIVE_MINT),
        "canonical_volume_5m": {"status": "VALID", "mint": LIVE_MINT,
                                "sample_count": 4,
                                "coverage_seconds": 300,
                                "gross_volume_usd": "100",
                                "net_quote_flow_usd": "10"},
    }
    record = build_ping_quality_record(
        candidate=candidate, recheck={"reason": "SENT_OK_COMMITTED"},
        security=None, observed_at_utc=NOW)
    review = record["global_fees_review"]
    assert review["status"] == GLOBAL_FEES_STATUS_VALID
    assert review["global_fees_paid_sol"] == "3.750421734"
    assert review["interval"] == "alltime"
    assert review["source"] == GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY
    assert review["endpoint_source"] == GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW
    assert review["observed_at_utc"] == NOW
    assert review["request_reused"] is True
    assert review["regression_detected"] is False
    assert ping_quality_record_is_redaction_safe(record) is True


def test_quality_record_preserves_unavailable_reason():
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    tracker.observe_overview(
        LIVE_MINT, _observation(value=None))
    candidate = {"token_mint": LIVE_MINT,
                 "global_fees": tracker.snapshot(LIVE_MINT)}
    review = build_ping_quality_record(
        candidate=candidate, recheck={}, security=None,
        observed_at_utc=NOW)["global_fees_review"]
    assert review["status"] == GLOBAL_FEES_STATUS_VALUE_NULL
    assert review["global_fees_paid_sol"] is None
    assert review["failure_reason"] == GLOBAL_FEES_STATUS_VALUE_NULL
    assert review["raw_type"] == "null"


def test_runtime_artifact_scanner_accepts_every_new_field(tmp_path):
    tracker = GlobalFeesTracker(now_iso_fn=_Clock().now_iso)
    tracker.observe_overview(LIVE_MINT, _observation())
    tracker.observe_overview(
        LIVE_MINT, _observation(value=1.2, observed_at=_iso(NOW_EPOCH + 60)))
    snapshot = tracker.snapshot(LIVE_MINT)
    compose_artifact_telemetry = {
        "global_fees": snapshot,
        "global_fees_rendered": True,
    }
    quality_record = build_ping_quality_record(
        candidate={"token_mint": LIVE_MINT, "global_fees": snapshot},
        recheck={}, security=None, observed_at_utc=NOW)
    (tmp_path / "phx2_ping_quality_review.jsonl").write_text(
        json.dumps(quality_record), encoding="utf-8")
    (tmp_path / "telegram_compose.json").write_text(
        json.dumps(compose_artifact_telemetry), encoding="utf-8")
    scan = run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    assert scan["total_unsafe_hits"] == 0
    assert scan["positive_control_ok"] is True


def test_no_secret_material_exists_in_any_new_surface():
    observation = _observation()
    snapshot_text = json.dumps(observation).lower()
    for needle in ("api-key", "api_key", "x-api-key", "bearer",
                   "authorization", "://"):
        assert needle not in snapshot_text
