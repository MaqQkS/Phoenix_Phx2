"""Stage 27.7b controlled live smoke dispatch tests.

Pins:

  * DRY_RUN mode never calls transport; returns DRY_RUN_NOT_SENT.
  * Three-factor LIVE auth: every missing factor returns a
    closed-set refusal (LIVE_AUTHORITY_NOT_ALLOWED /
    OPERATOR_LIVE_REQUEST_MISSING /
    SMOKE_DISPATCH_REQUEST_MISSING).
  * Missing webhook URL / identity in LIVE_SEND mode ->
    REFUSED_MISSING_WEBHOOK.
  * UNKNOWN pair refuses (any mode).
  * DISAGREE pair refuses (any mode).
  * USDC pair refuses live send unless RENDERED_OBSERVE_ONLY warning.
  * USDC pair WITH OBSERVE_ONLY can send.
  * SOL pair on EXISTING_SOL_LANE in LIVE_SEND -> SENT.
  * Multi-payload dispatch -> REFUSED_MULTIPLE_PAYLOADS.
  * Empty payload list -> REFUSED_MULTIPLE_PAYLOADS / NO_PAYLOAD_PROVIDED.
  * Unknown dispatch_mode -> REFUSED_UNAUTHORIZED_MODE /
    UNKNOWN_DISPATCH_MODE.
  * Webhook URL canary never appears in any dispatch result.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import private_discord_models as m
from PHX2.stage27.live_smoke_dispatch import (
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
    STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH,
    dispatch_one_private_ping_smoke,
)
from PHX2.stage27.private_discord_sender import (
    FrozenStage27_7bDispatchClock,
    Stage27_7bFakeDiscordTransport,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
    STAGE27_5_PING_SCHEMA_VERSION,
)


FAKE_WEBHOOK_URL_CANARY: str = (
    "FAKE-CANARY-WEBHOOK-URL-DO-NOT-LEAK-dispatch-7f1c"
)
FAKE_FROZEN_UTC: str = "2026-05-22T12:00:30+00:00"


def _frozen_clock() -> FrozenStage27_7bDispatchClock:
    return FrozenStage27_7bDispatchClock(frozen_iso=FAKE_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _payload(
    *,
    ping_id: str = "ping-1",
    quote_asset: str = "SOL",
    pair_detection_status: str = "CONFIRMED",
    calibration_lane: str = "EXISTING_SOL_LANE",
    render_status: str = "RENDERED",
    pair_type: str = "PUMP_SOL",
    pair_live_policy: str = "LIVE_ALLOWED",
    bonding_curve_version: str = "SOL_LEGACY",
) -> PrivatePingPayloadRecord:
    return PrivatePingPayloadRecord(
        ping_id=ping_id,
        run_id="run-1",
        session_id="sess-1",
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        provider_id="fake-provider",
        provider_event_id="fake-evt-1",
        normalized_event_id="fake-norm-1",
        raw_capture_ref="fake-rcap-1",
        token_mint="SmokeMint1",
        quote_mint=None,
        pair_type=pair_type,
        quote_asset=quote_asset,
        bonding_curve_version=bonding_curve_version,
        pair_detection_status=pair_detection_status,
        pair_detection_confidence="HIGH",
        pair_detection_reason="CONFIRMED_AGREEMENT",
        pair_live_policy=pair_live_policy,
        calibration_lane=calibration_lane,
        measurement_status="COMPLETE",
        measurement_warnings=(),
        price_status="PRESENT",
        price_value_display="0.001",
        price_unit_display="SOL",
        price_source_display="fake-birdeye",
        price_staleness_seconds_display="10",
        ath_status="PRESENT",
        ath_value_display="0.005",
        ath_unit_display="SOL",
        ath_since_migration_status_display="STARTS_POST_MIGRATION",
        drawdown_display="0.80",
        drawdown_basis_display="ATH_AFTER_MIGRATION",
        migration_status="PRESENT",
        migration_timestamp_display="2026-05-22T11:00:00+00:00",
        migration_age_seconds_display="3630",
        migration_source_display="ON_CHAIN_MIGRATION_EVENT",
        render_status=render_status,
        render_note="LIVE_OK",
        body_text=(
            "PHX2 STAGE 27.5 PRIVATE DRY-RUN PING\n"
            f"ping_id: {ping_id}\n"
        ),
    )


def _sol_payload() -> PrivatePingPayloadRecord:
    return _payload()


def _usdc_payload_observe_only() -> PrivatePingPayloadRecord:
    return _payload(
        ping_id="ping-usdc-1",
        quote_asset="USDC",
        pair_type="PUMP_USDC",
        bonding_curve_version="USDC_FIXED",
        calibration_lane="USDC_OBSERVE_ONLY",
        render_status="RENDERED_OBSERVE_ONLY",
        pair_live_policy="LIVE_ALLOWED",
    )


def _usdc_payload_no_observe_only() -> PrivatePingPayloadRecord:
    """USDC payload without the OBSERVE_ONLY render warning.

    Stage 27.5 normally tags every USDC payload
    RENDERED_OBSERVE_ONLY; this fixture exists to assert the
    dispatch refuses defensively if upstream ever fails to tag it.
    """
    return _payload(
        ping_id="ping-usdc-2",
        quote_asset="USDC",
        pair_type="PUMP_USDC",
        bonding_curve_version="USDC_FIXED",
        calibration_lane="USDC_OBSERVE_ONLY",
        render_status="RENDERED",  # missing OBSERVE_ONLY warning
        pair_live_policy="LIVE_ALLOWED",
    )


def _unknown_payload() -> PrivatePingPayloadRecord:
    return _payload(
        ping_id="ping-unk-1",
        quote_asset="UNKNOWN",
        pair_type="UNKNOWN",
        bonding_curve_version="UNKNOWN",
        pair_detection_status="UNRESOLVED",
        calibration_lane="UNKNOWN_PAIR_OBSERVE_ONLY",
        render_status="RENDERED_SUPPRESSED",
        pair_live_policy="LIVE_SUPPRESS_UNKNOWN",
    )


def _disagree_payload() -> PrivatePingPayloadRecord:
    return _payload(
        ping_id="ping-dis-1",
        quote_asset="SOL",
        pair_type="PUMP_SOL",
        bonding_curve_version="SOL_LEGACY",
        pair_detection_status="DISAGREE",
        calibration_lane="DISAGREE_PAIR_OBSERVE_ONLY",
        render_status="RENDERED_SUPPRESSED",
        pair_live_policy="LIVE_SUPPRESS_DISAGREE",
    )


def _sol_payload_off_lane() -> PrivatePingPayloadRecord:
    """Defensive: SOL pair but calibration lane is NOT
    EXISTING_SOL_LANE. Stage 27.5 should never produce this, but
    Stage 27.7b dispatch refuses defensively.
    """
    return _payload(
        ping_id="ping-sol-off-lane",
        quote_asset="SOL",
        pair_type="PUMP_SOL",
        bonding_curve_version="SOL_LEGACY",
        pair_detection_status="CONFIRMED",
        calibration_lane="USDC_OBSERVE_ONLY",  # wrong lane
        render_status="RENDERED",
    )


# ---------------------------------------------------------------------------
# DRY_RUN default mode
# ---------------------------------------------------------------------------


def test_default_dispatch_mode_is_dry_run_and_does_not_call_transport():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_DRY_RUN_NOT_SENT
    )
    assert result.dispatch_reason == m.DISPATCH_REASON_DRY_RUN_MODE
    assert result.dispatch_mode == m.DISPATCH_MODE_DRY_RUN
    assert result.transport_status_code is None
    assert transport.call_count == 0


def test_explicit_dry_run_mode_does_not_call_transport_even_with_full_auth():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_DRY_RUN,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_DRY_RUN_NOT_SENT
    )
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Three-factor LIVE authorization
# ---------------------------------------------------------------------------


def test_live_send_with_non_live_allowed_authority_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority="LIVE_REFUSED",
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_NOT_LIVE
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_LIVE_AUTHORITY_NOT_ALLOWED
    )
    assert transport.call_count == 0


def test_live_send_with_dry_run_authority_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority="DRY_RUN",
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_NOT_LIVE
    )
    assert transport.call_count == 0


def test_live_send_with_operator_live_request_false_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=False,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_OPERATOR_LIVE_REQUEST_MISSING
    )
    assert transport.call_count == 0


def test_live_send_with_smoke_dispatch_request_false_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=False,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_SMOKE_DISPATCH_REQUEST_MISSING
    )
    assert transport.call_count == 0


def test_live_send_with_unknown_dispatch_mode_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode="ENABLED",
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_UNKNOWN_DISPATCH_MODE
    )
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Missing webhook (LIVE_SEND only; DRY_RUN short-circuits earlier)
# ---------------------------------------------------------------------------


def test_live_send_with_empty_webhook_url_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url="",
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_WEBHOOK_URL_MISSING
    )
    assert transport.call_count == 0


def test_live_send_with_empty_webhook_identity_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity="",
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING
    )
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Pair-aware refusals (apply in BOTH DRY_RUN and LIVE_SEND)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dispatch_mode",
    [m.DISPATCH_MODE_DRY_RUN, m.DISPATCH_MODE_LIVE_SEND],
)
def test_unknown_pair_refuses_in_any_mode(dispatch_mode):
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_unknown_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=dispatch_mode,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN
    )
    assert result.pair_quote_asset == "UNKNOWN"
    assert transport.call_count == 0


@pytest.mark.parametrize(
    "dispatch_mode",
    [m.DISPATCH_MODE_DRY_RUN, m.DISPATCH_MODE_LIVE_SEND],
)
def test_disagree_pair_refuses_in_any_mode(dispatch_mode):
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_disagree_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=dispatch_mode,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_PAIR_SUPPRESS_DISAGREE
    )
    assert transport.call_count == 0


def test_usdc_pair_without_observe_only_refuses_live_send():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_usdc_payload_no_observe_only()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY
    )
    assert transport.call_count == 0


def test_usdc_pair_with_observe_only_sends_in_live_mode():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_usdc_payload_observe_only()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == m.DISPATCH_STATUS_SENT
    assert result.dispatch_mode == m.DISPATCH_MODE_LIVE_SEND
    assert result.pair_quote_asset == "USDC"
    assert result.render_status == "RENDERED_OBSERVE_ONLY"
    assert transport.call_count == 1


def test_sol_pair_off_existing_lane_refuses_live_send():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload_off_lane()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_PAIR_SOL_NOT_ON_EXISTING_LANE
    )
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# SOL happy path
# ---------------------------------------------------------------------------


def test_sol_pair_live_send_happy_path():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
        run_id="run-smoke-1",
        session_id="sess-smoke-1",
    )
    assert result.dispatch_status == m.DISPATCH_STATUS_SENT
    assert result.dispatch_reason == m.DISPATCH_REASON_LIVE_SEND_OK
    assert result.dispatch_mode == m.DISPATCH_MODE_LIVE_SEND
    assert result.pair_quote_asset == "SOL"
    assert result.transport_status_code == 200
    assert result.run_id == "run-smoke-1"
    assert result.session_id == "sess-smoke-1"
    assert transport.call_count == 1


# ---------------------------------------------------------------------------
# One-ping bound
# ---------------------------------------------------------------------------


def test_one_ping_bound_locked_to_one():
    assert STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH == 1


def test_multi_payload_dispatch_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload(), _sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED
    )
    assert transport.call_count == 0
    # Refusal-before-payload sentinels:
    assert result.ping_id == m.NO_PAYLOAD_SENTINEL
    assert result.pair_quote_asset == m.NO_PAYLOAD_SENTINEL


def test_empty_payload_list_refuses_with_no_payload_reason():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_NO_PAYLOAD_PROVIDED
    )
    assert transport.call_count == 0


def test_scalar_payload_argument_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        "not-a-sequence",  # type: ignore[arg-type]
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
    )
    assert transport.call_count == 0


def test_three_payload_dispatch_refuses():
    transport = Stage27_7bFakeDiscordTransport()
    payloads = [
        _payload(ping_id="ping-a"),
        _payload(ping_id="ping-b"),
        _payload(ping_id="ping-c"),
    ]
    result = dispatch_one_private_ping_smoke(
        payloads,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
    )
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Webhook URL redaction across dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "auth_kwargs",
    [
        {  # successful LIVE_SEND
            "live_mode_authority": LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
            "operator_live_request": True,
            "smoke_dispatch_request": True,
            "dispatch_mode": m.DISPATCH_MODE_LIVE_SEND,
        },
        {  # DRY_RUN
            "live_mode_authority": LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
            "operator_live_request": True,
            "smoke_dispatch_request": True,
            "dispatch_mode": m.DISPATCH_MODE_DRY_RUN,
        },
        {  # REFUSED_NOT_LIVE
            "live_mode_authority": "DRY_RUN",
            "operator_live_request": True,
            "smoke_dispatch_request": True,
            "dispatch_mode": m.DISPATCH_MODE_LIVE_SEND,
        },
        {  # REFUSED_UNAUTHORIZED_MODE
            "live_mode_authority": LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
            "operator_live_request": False,
            "smoke_dispatch_request": True,
            "dispatch_mode": m.DISPATCH_MODE_LIVE_SEND,
        },
    ],
)
def test_webhook_url_canary_never_in_dispatch_result(auth_kwargs):
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_sol_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        **auth_kwargs,
    )
    assert FAKE_WEBHOOK_URL_CANARY not in repr(result)
    assert FAKE_WEBHOOK_URL_CANARY not in str(result)
    for field_name in result._fields:
        value = getattr(result, field_name)
        if isinstance(value, str):
            assert FAKE_WEBHOOK_URL_CANARY not in value


# ---------------------------------------------------------------------------
# Schema version preserved on every dispatch result
# ---------------------------------------------------------------------------


def test_every_refusal_result_carries_schema_version():
    transport = Stage27_7bFakeDiscordTransport()
    result = dispatch_one_private_ping_smoke(
        [_unknown_payload()],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.schema_version == (
        m.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION
    )
    assert result.redaction_status == m.REDACTION_STATUS_REDACTED


def test_sent_at_utc_stamped_on_every_dispatch_result():
    transport = Stage27_7bFakeDiscordTransport()
    clock = FrozenStage27_7bDispatchClock(
        frozen_iso="2026-05-22T15:30:00+00:00"
    )
    # Refusal still stamps the clock.
    result = dispatch_one_private_ping_smoke(
        [],
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=clock,
        live_mode_authority=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        operator_live_request=True,
        smoke_dispatch_request=True,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
    )
    assert result.sent_at_utc == "2026-05-22T15:30:00+00:00"
