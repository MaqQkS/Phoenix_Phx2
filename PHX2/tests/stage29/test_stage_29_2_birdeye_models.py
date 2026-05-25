"""Stage 29.2 birdeye models pin tests.

Locks the closed-set vocabularies + snapshot / evidence
dataclasses + ``__post_init__`` validators. Confirms Stage 29.2
NEVER carries a fabricated number when status is non-``PRESENT``.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_OHLCV_SOURCE_LABEL,
    BIRDEYE_PRICE_SOURCE_LABEL,
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29 import stage29_2_birdeye_models as M


# ---------------------------------------------------------------------------
# Closed-set price status
# ---------------------------------------------------------------------------


def test_price_status_values_set():
    assert M.BIRDEYE_PRICE_STATUS_VALUES == (
        "PRESENT",
        "MISSING",
        "STALE",
        "SOURCE_ERROR",
    )


@pytest.mark.parametrize("value", M.BIRDEYE_PRICE_STATUS_VALUES)
def test_is_birdeye_price_status_value_accepts_known(value):
    assert M.is_birdeye_price_status_value(value)


def test_is_birdeye_price_status_value_rejects_unknown():
    assert not M.is_birdeye_price_status_value("present")
    assert not M.is_birdeye_price_status_value(None)
    assert not M.is_birdeye_price_status_value(1)


# ---------------------------------------------------------------------------
# Closed-set ATH status
# ---------------------------------------------------------------------------


def test_ath_status_values_set():
    assert M.BIRDEYE_ATH_STATUS_VALUES == (
        "PRESENT",
        "MISSING",
        "STALE",
        "SOURCE_ERROR",
    )


# ---------------------------------------------------------------------------
# Closed-set freshness status
# ---------------------------------------------------------------------------


def test_freshness_status_values_set():
    assert M.BIRDEYE_FRESHNESS_STATUS_VALUES == (
        "FRESH",
        "STALE",
        "UNKNOWN",
    )


# ---------------------------------------------------------------------------
# Closed-set refusal reason
# ---------------------------------------------------------------------------


def test_refusal_reason_values_minimum_set():
    required = {
        "NONE",
        "ENDPOINT_MISSING",
        "ENDPOINT_UNSAFE",
        "API_KEY_MISSING",
        "API_KEY_UNSAFE",
        "LIVE_FLAG_NOT_SET",
        "TIMEOUT_INVALID",
        "HTTP_FAILED",
        "HTTP_TIMEOUT",
        "HTTP_STATUS_REJECTED",
        "HTTP_SUCCESS_FALSE",
        "BODY_MALFORMED",
        "PRICE_MISSING_IN_BODY",
        "ATH_SERIES_EMPTY",
        "MINT_REJECTED_SAFE_SHAPE",
        "BASE_URL_REJECTED",
        "LOOKBACK_INVALID",
        "OHLCV_TYPE_INVALID",
        "MODE_INVALID",
        "TRANSPORT_FACTORY_NOT_CALLABLE",
    }
    assert required.issubset(set(M.BIRDEYE_REFUSAL_REASON_VALUES))


# ---------------------------------------------------------------------------
# No-invention audit closed set
# ---------------------------------------------------------------------------


def test_no_invention_audit_values_set():
    assert M.NO_INVENTION_AUDIT_VALUES == ("PASSED", "FAILED")


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeError carries closed-set reason only
# ---------------------------------------------------------------------------


def test_error_carries_reason_attribute():
    err = M.Stage29_2BirdeyeError("SOME_REASON")
    assert err.reason == "SOME_REASON"
    assert "SOME_REASON" in str(err)


# ---------------------------------------------------------------------------
# Stage29_2BirdeyePriceSnapshot validation
# ---------------------------------------------------------------------------


def _good_price_snapshot_kwargs():
    return dict(
        price_value="0.00012345",
        price_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_PRICE_SOURCE_LABEL,
        fetched_at_utc="2026-05-25T12:00:00+00:00",
        upstream_update_unix_time=1700000000,
        birdeye_price_status=M.BIRDEYE_PRICE_STATUS_PRESENT,
        birdeye_freshness_status=M.BIRDEYE_FRESHNESS_STATUS_FRESH,
    )


def test_build_price_snapshot_present_ok():
    snap = M.build_birdeye_price_snapshot(
        **_good_price_snapshot_kwargs()
    )
    assert snap.price_value == "0.00012345"
    assert snap.schema_version == (
        "stage29_2_birdeye_snapshot_v0"
    )


def test_price_snapshot_present_requires_value():
    kw = _good_price_snapshot_kwargs()
    kw["price_value"] = None
    with pytest.raises(M.Stage29_2BirdeyeError) as exc:
        M.build_birdeye_price_snapshot(**kw)
    assert "PRESENT_WITHOUT_PRICE_VALUE" in str(exc.value)


def test_price_snapshot_missing_forbids_value():
    kw = _good_price_snapshot_kwargs()
    kw["birdeye_price_status"] = M.BIRDEYE_PRICE_STATUS_MISSING
    # value remains "0.00012345" -> must raise
    with pytest.raises(M.Stage29_2BirdeyeError) as exc:
        M.build_birdeye_price_snapshot(**kw)
    assert "MISSING_OR_ERROR_WITH_PRICE_VALUE" in str(exc.value)


def test_price_snapshot_source_error_forbids_value():
    kw = _good_price_snapshot_kwargs()
    kw["birdeye_price_status"] = (
        M.BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )
    with pytest.raises(M.Stage29_2BirdeyeError) as exc:
        M.build_birdeye_price_snapshot(**kw)
    assert "MISSING_OR_ERROR_WITH_PRICE_VALUE" in str(exc.value)


def test_price_snapshot_missing_with_none_ok():
    kw = _good_price_snapshot_kwargs()
    kw["birdeye_price_status"] = M.BIRDEYE_PRICE_STATUS_MISSING
    kw["price_value"] = None
    snap = M.build_birdeye_price_snapshot(**kw)
    assert snap.price_value is None


def test_price_snapshot_rejects_float_price_value():
    kw = _good_price_snapshot_kwargs()
    kw["price_value"] = 0.00012345  # float, must be str/None
    with pytest.raises(M.Stage29_2BirdeyeError) as exc:
        M.build_birdeye_price_snapshot(**kw)
    assert "PRICE_VALUE_NOT_STR_OR_NONE" in str(exc.value)


def test_price_snapshot_rejects_unknown_status():
    kw = _good_price_snapshot_kwargs()
    kw["birdeye_price_status"] = "present"  # lowercase, unknown
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_price_snapshot(**kw)


def test_price_snapshot_rejects_negative_unix_time():
    kw = _good_price_snapshot_kwargs()
    kw["upstream_update_unix_time"] = -1
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_price_snapshot(**kw)


def test_price_snapshot_rejects_bool_unix_time():
    kw = _good_price_snapshot_kwargs()
    kw["upstream_update_unix_time"] = True
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_price_snapshot(**kw)


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeAthSnapshot validation
# ---------------------------------------------------------------------------


def _good_ath_snapshot_kwargs():
    return dict(
        ath_value="0.0008",
        ath_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label=BIRDEYE_OHLCV_SOURCE_LABEL,
        ath_observed_at_utc="2026-05-24T18:00:00+00:00",
        window_starts_post_migration=False,
        lookback_hours=24,
        items_count=96,
        birdeye_ath_status=M.BIRDEYE_ATH_STATUS_PRESENT,
        birdeye_freshness_status=M.BIRDEYE_FRESHNESS_STATUS_FRESH,
    )


def test_build_ath_snapshot_present_ok():
    snap = M.build_birdeye_ath_snapshot(
        **_good_ath_snapshot_kwargs()
    )
    assert snap.ath_value == "0.0008"
    assert snap.items_count == 96


def test_ath_snapshot_present_requires_value():
    kw = _good_ath_snapshot_kwargs()
    kw["ath_value"] = None
    with pytest.raises(M.Stage29_2BirdeyeError) as exc:
        M.build_birdeye_ath_snapshot(**kw)
    assert "PRESENT_WITHOUT_ATH_VALUE" in str(exc.value)


def test_ath_snapshot_missing_forbids_value():
    kw = _good_ath_snapshot_kwargs()
    kw["birdeye_ath_status"] = M.BIRDEYE_ATH_STATUS_MISSING
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_ath_snapshot(**kw)


def test_ath_snapshot_source_error_forbids_value():
    kw = _good_ath_snapshot_kwargs()
    kw["birdeye_ath_status"] = (
        M.BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_ath_snapshot(**kw)


def test_ath_snapshot_window_flag_accepts_none():
    kw = _good_ath_snapshot_kwargs()
    kw["window_starts_post_migration"] = None
    snap = M.build_birdeye_ath_snapshot(**kw)
    assert snap.window_starts_post_migration is None


def test_ath_snapshot_window_flag_rejects_non_bool_non_none():
    kw = _good_ath_snapshot_kwargs()
    kw["window_starts_post_migration"] = "True"
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_ath_snapshot(**kw)


def test_ath_snapshot_rejects_negative_items_count():
    kw = _good_ath_snapshot_kwargs()
    kw["items_count"] = -1
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_ath_snapshot(**kw)


def test_ath_snapshot_rejects_bool_lookback_hours():
    kw = _good_ath_snapshot_kwargs()
    kw["lookback_hours"] = True
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_ath_snapshot(**kw)


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeEvidenceRecord validation
# ---------------------------------------------------------------------------


def test_build_evidence_record_ok():
    price = M.build_birdeye_price_snapshot(
        **_good_price_snapshot_kwargs()
    )
    ath = M.build_birdeye_ath_snapshot(
        **_good_ath_snapshot_kwargs()
    )
    rec = M.build_birdeye_evidence_record(
        base_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        price_snapshot=price,
        ath_snapshot=ath,
        drawdown_ratio="-0.846",
        freshness_status=M.BIRDEYE_FRESHNESS_STATUS_FRESH,
        no_invention_audit=M.NO_INVENTION_AUDIT_PASSED,
    )
    assert rec.drawdown_ratio == "-0.846"
    assert rec.no_invention_audit == "PASSED"
    assert rec.schema_version == (
        "stage29_2_birdeye_evidence_v0"
    )


def test_evidence_record_rejects_wrong_snapshot_type():
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_evidence_record(
            base_mint="aaaa",
            price_snapshot="not-a-snapshot",  # type: ignore[arg-type]
            ath_snapshot=M.build_birdeye_ath_snapshot(
                **_good_ath_snapshot_kwargs()
            ),
            drawdown_ratio=None,
            freshness_status=M.BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
            no_invention_audit=M.NO_INVENTION_AUDIT_PASSED,
        )


def test_evidence_record_rejects_unknown_audit():
    price = M.build_birdeye_price_snapshot(
        **_good_price_snapshot_kwargs()
    )
    ath = M.build_birdeye_ath_snapshot(
        **_good_ath_snapshot_kwargs()
    )
    with pytest.raises(M.Stage29_2BirdeyeError):
        M.build_birdeye_evidence_record(
            base_mint="aaaa",
            price_snapshot=price,
            ath_snapshot=ath,
            drawdown_ratio=None,
            freshness_status=M.BIRDEYE_FRESHNESS_STATUS_FRESH,
            no_invention_audit="passed",  # lowercase
        )


# ---------------------------------------------------------------------------
# Snapshots / evidence record __repr__ never echoes raw response body
# ---------------------------------------------------------------------------


def test_price_snapshot_repr_carries_only_safe_fields():
    snap = M.build_birdeye_price_snapshot(
        **_good_price_snapshot_kwargs()
    )
    r = repr(snap)
    # Forbidden fragments
    for needle in (
        "B" + "earer",
        "BIRDEYE_API" + "_KEY",
        "h" + "ttps://",
    ):
        assert needle not in r


def test_ath_snapshot_repr_carries_only_safe_fields():
    snap = M.build_birdeye_ath_snapshot(
        **_good_ath_snapshot_kwargs()
    )
    r = repr(snap)
    for needle in (
        "B" + "earer",
        "BIRDEYE_API" + "_KEY",
        "h" + "ttps://",
    ):
        assert needle not in r
