"""Stage 29.3 smoke-models pins.

Pins the Stage 29.3 closed-set vocabularies, the
``Stage29_3TradeableSmokeResult`` validation contract, the
builder error path, and the ``smoke_result_to_dict`` projection.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_3_smoke_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_VALUES,
    REDACTION_STATUS_SAFE,
    STAGE29_3_REDACTION_TOKEN,
    STAGE29_3_SCHEMA_VERSION,
    STAGE29_3_SMOKE_RESULT_COUNTER_FIELD_NAMES,
    STAGE29_3_SMOKE_RESULT_FIELD_NAMES,
    TRADEABLE_SMOKE_OUTCOME_CONNECTED,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_FAILED,
    TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES,
    TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_OUTCOME_REFUSED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
    TRADEABLE_SMOKE_OUTCOME_VALUES,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
    TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED,
    TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_VALUES,
    TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING,
    Stage29_3InvalidSmokeResultError,
    Stage29_3TradeableSmokeError,
    build_tradeable_smoke_result,
    is_probe_mode_value,
    is_redaction_status_value,
    is_tradeable_smoke_outcome_value,
    is_tradeable_smoke_refusal_reason_value,
    smoke_result_to_dict,
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_probe_mode_values_closed_set():
    assert PROBE_MODE_VALUES == (
        PROBE_MODE_READINESS_ONLY,
        PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    )
    for mode in PROBE_MODE_VALUES:
        assert is_probe_mode_value(mode)
    for bogus in ("", "READINESS", "MODE3", None, 0, True, [], {}):
        assert not is_probe_mode_value(bogus)


def test_outcome_values_membership():
    assert TRADEABLE_SMOKE_OUTCOME_DISPATCHED in TRADEABLE_SMOKE_OUTCOME_VALUES
    assert TRADEABLE_SMOKE_OUTCOME_REFUSED in TRADEABLE_SMOKE_OUTCOME_VALUES
    assert TRADEABLE_SMOKE_OUTCOME_FAILED in TRADEABLE_SMOKE_OUTCOME_VALUES
    assert TRADEABLE_SMOKE_OUTCOME_READY in TRADEABLE_SMOKE_OUTCOME_VALUES
    assert TRADEABLE_SMOKE_OUTCOME_CONNECTED in TRADEABLE_SMOKE_OUTCOME_VALUES
    assert TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED in TRADEABLE_SMOKE_OUTCOME_VALUES
    for suppressed in (
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
    ):
        assert suppressed in TRADEABLE_SMOKE_OUTCOME_VALUES
        assert is_tradeable_smoke_outcome_value(suppressed)


def test_outcome_non_error_subset_excludes_refused_and_failed():
    assert (
        TRADEABLE_SMOKE_OUTCOME_REFUSED
        not in TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES
    )
    assert (
        TRADEABLE_SMOKE_OUTCOME_FAILED
        not in TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES
    )
    for value in TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES:
        assert value in TRADEABLE_SMOKE_OUTCOME_VALUES


def test_refusal_reason_values_membership():
    for reason in (
        TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
        TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID,
        TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED,
        TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED,
        TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING,
        TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
        TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
        TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED,
        TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED,
        TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED,
    ):
        assert reason in TRADEABLE_SMOKE_REFUSAL_REASON_VALUES
        assert is_tradeable_smoke_refusal_reason_value(reason)


def test_redaction_status_closed_set():
    assert is_redaction_status_value(REDACTION_STATUS_SAFE)
    assert is_redaction_status_value("REDACTED")
    assert not is_redaction_status_value("ok")
    assert not is_redaction_status_value(None)


def test_redaction_token_is_unique_stage_marker():
    assert STAGE29_3_REDACTION_TOKEN.startswith("<<STAGE29_3")
    assert STAGE29_3_REDACTION_TOKEN.endswith(">>")


# ---------------------------------------------------------------------------
# Stage29_3TradeableSmokeResult validation
# ---------------------------------------------------------------------------


def _build_ok_dispatched() -> object:
    return build_tradeable_smoke_result(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
        tradeable_smoke_refusal_reason=(
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE
        ),
        events_seen=1,
        candidates_assembled=1,
        candidates_dispatched=1,
        dispatch_success=1,
        hint_bearing_payload_present=True,
        birdeye_price_present=True,
        birdeye_ath_present=True,
        stop_reason="DISPATCHED",
    )


def test_well_formed_dispatched_result_validates():
    result = _build_ok_dispatched()
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    assert result.schema_version == STAGE29_3_SCHEMA_VERSION
    assert result.redaction_status == REDACTION_STATUS_SAFE
    assert (
        result.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


def test_well_formed_refused_result_validates():
    result = build_tradeable_smoke_result(
        mode=PROBE_MODE_READINESS_ONLY,
        tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_REFUSED,
        tradeable_smoke_refusal_reason=(
            TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING
        ),
        stop_reason="WEBHOOK_MISSING",
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING
    )


def test_invalid_mode_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode="BOGUS_MODE",
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_DISPATCHED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            events_seen=1, candidates_assembled=1,
            candidates_dispatched=1, dispatch_success=1,
            hint_bearing_payload_present=True,
            birdeye_price_present=True,
            birdeye_ath_present=True,
            stop_reason="DISPATCHED",
        )


def test_non_error_outcome_with_refusal_reason_set_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_READY,
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING
            ),
            stop_reason="READY",
        )


def test_error_outcome_with_none_refusal_reason_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_REFUSED,
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            stop_reason="REFUSED",
        )


@pytest.mark.parametrize(
    "field_name",
    list(STAGE29_3_SMOKE_RESULT_COUNTER_FIELD_NAMES),
)
def test_negative_counters_rejected(field_name):
    kwargs = dict(
        mode=PROBE_MODE_READINESS_ONLY,
        tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_READY,
        tradeable_smoke_refusal_reason=(
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE
        ),
        stop_reason="READY",
    )
    kwargs[field_name] = -1
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(**kwargs)


def test_events_seen_exceeds_max_events_1_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
            tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            events_seen=2,
            candidates_assembled=1,
            candidates_dispatched=1,
            dispatch_success=1,
            hint_bearing_payload_present=True,
            birdeye_price_present=True,
            birdeye_ath_present=True,
            stop_reason="DISPATCHED",
        )


def test_dispatch_success_exceeds_max_dispatches_1_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
            tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            events_seen=1,
            candidates_assembled=1,
            candidates_dispatched=1,
            dispatch_success=2,
            hint_bearing_payload_present=True,
            birdeye_price_present=True,
            birdeye_ath_present=True,
            stop_reason="DISPATCHED",
        )


def test_stop_reason_unsafe_rejected():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_READY,
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            stop_reason="contains spaces and / slashes",
        )


def test_smoke_result_to_dict_preserves_field_order():
    result = _build_ok_dispatched()
    projected = smoke_result_to_dict(result)
    assert tuple(projected.keys()) == STAGE29_3_SMOKE_RESULT_FIELD_NAMES


def test_smoke_result_to_dict_rejects_non_record():
    with pytest.raises(Stage29_3InvalidSmokeResultError):
        smoke_result_to_dict("not-a-record")  # type: ignore[arg-type]


def test_stage29_3_error_carries_only_reason_token():
    err = Stage29_3TradeableSmokeError("SOME_REASON")
    assert err.reason == "SOME_REASON"
    # repr / str carry the closed-set reason token, never a raw
    # secret / URL.
    assert "h" + "ttps" not in repr(err)
    assert "SOME_REASON" in str(err)
