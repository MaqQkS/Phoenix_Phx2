"""Stage 29.2 probe-models pin tests."""

from __future__ import annotations

import pytest

from PHX2.stage29 import (
    stage29_2_birdeye_probe_models as PM,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_REFUSAL_REASON_NONE,
    NO_INVENTION_AUDIT_PASSED,
    Stage29_2BirdeyeError,
    build_birdeye_ath_snapshot,
    build_birdeye_evidence_record,
    build_birdeye_price_snapshot,
)


def test_probe_mode_values_set():
    assert PM.PROBE_MODE_VALUES == (
        "READINESS_ONLY",
        "HTTP_CONNECT_ONLY",
        "ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN",
    )


def test_probe_status_values_set():
    assert PM.PROBE_STATUS_VALUES == (
        "READY",
        "NOT_READY",
        "CONNECTED",
        "FETCHED_WITH_PRICE_AND_ATH",
        "FETCHED_PRICE_ONLY",
        "FETCHED_NO_ATH_EVIDENCE",
        "FAILED",
        "SKIPPED",
    )


def test_is_probe_mode_value_rejects_unknown():
    assert not PM.is_probe_mode_value("connect")
    assert not PM.is_probe_mode_value(None)


def test_is_probe_status_value_rejects_unknown():
    assert not PM.is_probe_status_value("ready")
    assert not PM.is_probe_status_value(1)


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeHintProbeResult validation
# ---------------------------------------------------------------------------


def _build_evidence():
    price = build_birdeye_price_snapshot(
        price_value="0.5",
        price_unit="USD",
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-25T12:00:00+00:00",
        upstream_update_unix_time=1716638400,
        birdeye_price_status="PRESENT",
        birdeye_freshness_status="FRESH",
    )
    ath = build_birdeye_ath_snapshot(
        ath_value="0.8",
        ath_unit="USD",
        source_label="birdeye_defi_ohlcv",
        ath_observed_at_utc="2026-05-24T12:00:00+00:00",
        window_starts_post_migration=False,
        lookback_hours=24,
        items_count=10,
        birdeye_ath_status="PRESENT",
        birdeye_freshness_status="FRESH",
    )
    return build_birdeye_evidence_record(
        base_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        price_snapshot=price,
        ath_snapshot=ath,
        drawdown_ratio="-0.375",
        freshness_status=BIRDEYE_FRESHNESS_STATUS_FRESH,
        no_invention_audit=NO_INVENTION_AUDIT_PASSED,
    )


def _good_probe_result_kwargs():
    return dict(
        mode=PM.PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        status=PM.PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH,
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        base_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        evidence=_build_evidence(),
        http_status_code=200,
        api_key_length=32,
        base_url_length=24,
        live_flag_set=True,
        timeout_seconds=30,
        handoff_ready=True,
    )


def test_build_probe_result_ok():
    rec = PM.build_hint_probe_result(
        **_good_probe_result_kwargs()
    )
    assert rec.mode == (
        "ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN"
    )
    assert rec.handoff_ready is True
    assert rec.schema_version == "stage29_2_birdeye_probe_v0"


def test_probe_result_accepts_string_mode_echo():
    # The mode field is a string echo of the operator-supplied
    # mode; the probe orchestrator's dispatch logic is the
    # authoritative closed-set check. The model validator only
    # requires ``isinstance(mode, str)``.
    kw = _good_probe_result_kwargs()
    kw["mode"] = "connect"
    kw["status"] = PM.PROBE_STATUS_FAILED
    kw["refusal_reason"] = "MODE_INVALID"
    rec = PM.build_hint_probe_result(**kw)
    assert rec.mode == "connect"


def test_probe_result_rejects_non_string_mode():
    kw = _good_probe_result_kwargs()
    kw["mode"] = None
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_rejects_unknown_status():
    kw = _good_probe_result_kwargs()
    kw["status"] = "Fetched"
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_rejects_unknown_refusal_reason():
    kw = _good_probe_result_kwargs()
    kw["refusal_reason"] = "weird"
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_rejects_negative_http_status():
    kw = _good_probe_result_kwargs()
    kw["http_status_code"] = -1
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_rejects_bool_http_status():
    kw = _good_probe_result_kwargs()
    kw["http_status_code"] = True
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_rejects_non_bool_handoff():
    kw = _good_probe_result_kwargs()
    kw["handoff_ready"] = "yes"
    with pytest.raises(Stage29_2BirdeyeError):
        PM.build_hint_probe_result(**kw)


def test_probe_result_accepts_none_evidence():
    kw = _good_probe_result_kwargs()
    kw["evidence"] = None
    kw["status"] = PM.PROBE_STATUS_READY
    kw["mode"] = PM.PROBE_MODE_READINESS_ONLY
    rec = PM.build_hint_probe_result(**kw)
    assert rec.evidence is None


def test_probe_result_repr_carries_only_safe_fields():
    rec = PM.build_hint_probe_result(
        **_good_probe_result_kwargs()
    )
    r = repr(rec)
    for needle in (
        "B" + "earer",
        "h" + "ttps://aaaa-bbbb.example",
    ):
        assert needle not in r
