"""Stage 27.7b private Discord sender tests.

Pins:

  * Fake transport: happy path -> SENT, exactly one transport
    call, transport_status_code preserved on the dispatch result.
  * Fake transport: non-200 -> TRANSPORT_ERROR /
    TRANSPORT_NON_SUCCESS.
  * Fake transport: raised Stage27_7bTransportError ->
    TRANSPORT_ERROR / TRANSPORT_EXCEPTION.
  * Sender refuses on missing webhook URL / identity.
  * Sender NEVER stores raw webhook URL on the dispatch result.
  * Sender NEVER includes raw webhook URL in any raised exception
    string.
  * Stage27_7bRealHttpDiscordTransport raises NotImplementedError.
  * Sender argument-error type carries only NAME + closed reason
    + optional length.
  * Provenance IDs are preserved from the Stage 27.5 payload.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import private_discord_models as m
from PHX2.stage27.private_discord_sender import (
    FrozenStage27_7bDispatchClock,
    Stage27_7bFakeDiscordTransport,
    Stage27_7bRealHttpDiscordTransport,
    Stage27_7bSenderArgumentError,
    Stage27_7bTransportError,
    Stage27_7bTransportResult,
    send_one_private_ping,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
    STAGE27_5_PING_SCHEMA_VERSION,
)


# A deliberately-distinctive fake webhook URL canary. If the
# sender ever leaks the URL into a dispatch result, repr, or error
# string, this canary substring will be detectable.
FAKE_WEBHOOK_URL_CANARY: str = (
    "FAKE-CANARY-WEBHOOK-URL-DO-NOT-LEAK-zzz-9b3a"
)
FAKE_FROZEN_UTC: str = "2026-05-22T12:00:30+00:00"


def _frozen_clock() -> FrozenStage27_7bDispatchClock:
    return FrozenStage27_7bDispatchClock(frozen_iso=FAKE_FROZEN_UTC)


def _sol_payload(ping_id: str = "ping-sol-1") -> PrivatePingPayloadRecord:
    return PrivatePingPayloadRecord(
        ping_id=ping_id,
        run_id="run-1",
        session_id="sess-1",
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        provider_id="fake-provider",
        provider_event_id="fake-evt-sol-1",
        normalized_event_id="fake-norm-sol-1",
        raw_capture_ref="fake-rcap-sol-1",
        token_mint="SmokeMintSol1",
        quote_mint="So11111111111111111111111111111111111111112",
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        bonding_curve_version="SOL_LEGACY",
        pair_detection_status="CONFIRMED",
        pair_detection_confidence="HIGH",
        pair_detection_reason="CONFIRMED_AGREEMENT",
        pair_live_policy="LIVE_ALLOWED",
        calibration_lane="EXISTING_SOL_LANE",
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
        render_status="RENDERED",
        render_note="LIVE_OK",
        body_text="PHX2 STAGE 27.5 PRIVATE DRY-RUN PING\nping_id: ping-sol-1\n",
    )


# ---------------------------------------------------------------------------
# Happy path: fake transport, status 200
# ---------------------------------------------------------------------------


def test_send_one_private_ping_happy_path_returns_sent():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        run_id="run-1",
        session_id="sess-1",
    )
    assert result.dispatch_status == m.DISPATCH_STATUS_SENT
    assert result.dispatch_reason == m.DISPATCH_REASON_LIVE_SEND_OK
    assert result.dispatch_mode == m.DISPATCH_MODE_LIVE_SEND
    assert result.webhook_identity == (
        m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )
    assert result.ping_id == "ping-sol-1"
    assert result.run_id == "run-1"
    assert result.session_id == "sess-1"
    assert result.sent_at_utc == FAKE_FROZEN_UTC
    assert result.transport_status_code == 200
    assert result.redaction_status == m.REDACTION_STATUS_REDACTED
    assert result.schema_version == (
        m.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION
    )
    assert result.pair_quote_asset == "SOL"
    assert result.render_status == "RENDERED"


def test_send_one_private_ping_calls_transport_exactly_once():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    assert transport.call_count == 1
    assert len(transport.calls) == 1
    assert transport.calls[0].webhook_url == FAKE_WEBHOOK_URL_CANARY
    assert transport.calls[0].body_text == payload.body_text


def test_send_one_private_ping_passes_payload_body_text_only():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    # The sender hands the transport the safe rendered body, not
    # a raw payload blob.
    call = transport.calls[0]
    assert call.body_text == payload.body_text
    # Defensive: body_text contains the deterministic header.
    assert "PHX2 STAGE 27.5 PRIVATE DRY-RUN PING" in call.body_text


# ---------------------------------------------------------------------------
# Non-200 transport status -> TRANSPORT_ERROR
# ---------------------------------------------------------------------------


def test_send_one_private_ping_non_200_status_returns_transport_error():
    transport = Stage27_7bFakeDiscordTransport(
        configured_status_code=500
    )
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    assert result.dispatch_status == m.DISPATCH_STATUS_TRANSPORT_ERROR
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_TRANSPORT_NON_SUCCESS
    )
    assert result.transport_status_code == 500


def test_send_one_private_ping_transport_exception_returns_transport_error():
    transport = Stage27_7bFakeDiscordTransport(
        raise_exception_kind="NETWORK_ERROR"
    )
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    assert result.dispatch_status == m.DISPATCH_STATUS_TRANSPORT_ERROR
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_TRANSPORT_EXCEPTION
    )
    # Status code is None when the transport raises (no status was
    # returned).
    assert result.transport_status_code is None


# ---------------------------------------------------------------------------
# Refusal: missing webhook
# ---------------------------------------------------------------------------


def test_send_one_private_ping_refuses_empty_webhook_url():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url="",
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_WEBHOOK_URL_MISSING
    )
    assert transport.call_count == 0


def test_send_one_private_ping_refuses_empty_webhook_identity():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity="",
        transport=transport,
        clock=_frozen_clock(),
    )
    assert result.dispatch_status == (
        m.DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
    )
    assert result.dispatch_reason == (
        m.DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING
    )
    assert transport.call_count == 0
    # The webhook URL canary is NOT echoed even though we passed
    # a valid URL.
    assert FAKE_WEBHOOK_URL_CANARY not in repr(result)


# ---------------------------------------------------------------------------
# Redaction: webhook URL never appears in result / repr / str / errors
# ---------------------------------------------------------------------------


def test_dispatch_result_repr_does_not_contain_webhook_url():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    assert FAKE_WEBHOOK_URL_CANARY not in repr(result)
    assert FAKE_WEBHOOK_URL_CANARY not in str(result)


def test_dispatch_result_fields_do_not_contain_webhook_url():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    for field_name in result._fields:
        value = getattr(result, field_name)
        if isinstance(value, str):
            assert FAKE_WEBHOOK_URL_CANARY not in value, (
                f"webhook URL canary leaked into result.{field_name}"
            )


def test_transport_error_does_not_carry_webhook_url():
    err = Stage27_7bTransportError(
        kind="NETWORK_ERROR", status_code=502
    )
    assert FAKE_WEBHOOK_URL_CANARY not in str(err)
    assert FAKE_WEBHOOK_URL_CANARY not in repr(err)
    assert err.kind == "NETWORK_ERROR"
    assert err.status_code == 502


def test_sender_argument_error_does_not_carry_value():
    err = Stage27_7bSenderArgumentError(
        argument_name="webhook_url",
        reason="NOT_STRING",
        value_length=len(FAKE_WEBHOOK_URL_CANARY),
    )
    assert FAKE_WEBHOOK_URL_CANARY not in str(err)
    assert FAKE_WEBHOOK_URL_CANARY not in repr(err)
    # The error carries only the closed-set NAME + REASON + length.
    assert "webhook_url" in str(err)
    assert "NOT_STRING" in str(err)
    assert str(len(FAKE_WEBHOOK_URL_CANARY)) in str(err)


def test_transport_result_does_not_carry_webhook_url():
    result = Stage27_7bTransportResult(
        status_code=200,
        ok=True,
        transport_error_kind=None,
    )
    assert FAKE_WEBHOOK_URL_CANARY not in repr(result)


def test_fake_transport_carries_url_internally_but_not_on_dispatch_result():
    """The fake transport stores the URL on its _FakeCallRecord
    (tests need to assert the right URL was passed), but the Stage
    27.7b dispatch result NEVER carries the URL.
    """
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
    )
    # Fake transport intentionally captures the URL on its call
    # record so tests can pin "the sender called transport with
    # exactly this URL". This is a TEST-fixture concern only.
    assert transport.calls[0].webhook_url == FAKE_WEBHOOK_URL_CANARY
    # The dispatch result never carries the URL.
    assert FAKE_WEBHOOK_URL_CANARY not in repr(result)


# ---------------------------------------------------------------------------
# Argument-type guards
# ---------------------------------------------------------------------------


def test_send_one_private_ping_rejects_non_payload_object():
    transport = Stage27_7bFakeDiscordTransport()
    with pytest.raises(Stage27_7bSenderArgumentError) as exc_info:
        send_one_private_ping(
            "not-a-payload",  # type: ignore[arg-type]
            webhook_url=FAKE_WEBHOOK_URL_CANARY,
            webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            transport=transport,
            clock=_frozen_clock(),
        )
    err = exc_info.value
    assert err.argument_name == "payload"
    assert err.reason == "NOT_PRIVATE_PING_PAYLOAD_RECORD"
    assert FAKE_WEBHOOK_URL_CANARY not in str(err)


# ---------------------------------------------------------------------------
# Real HTTP transport is isolated + raises
# ---------------------------------------------------------------------------


def test_real_http_transport_raises_not_implemented():
    transport = Stage27_7bRealHttpDiscordTransport()
    with pytest.raises(NotImplementedError) as exc_info:
        transport.send_one_payload(
            FAKE_WEBHOOK_URL_CANARY, "body"
        )
    # The placeholder does NOT echo the URL into the error.
    assert FAKE_WEBHOOK_URL_CANARY not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Provenance preservation
# ---------------------------------------------------------------------------


def test_send_preserves_payload_provenance_ids_on_result():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload(ping_id="ping-prov-7")
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        run_id="run-prov-7",
        session_id="sess-prov-7",
    )
    assert result.ping_id == "ping-prov-7"
    assert result.run_id == "run-prov-7"
    assert result.session_id == "sess-prov-7"
    assert result.pair_quote_asset == "SOL"
    assert result.render_status == "RENDERED"


def test_send_handles_none_run_session_ids():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=_frozen_clock(),
        run_id=None,
        session_id=None,
    )
    assert result.run_id is None
    assert result.session_id is None


# ---------------------------------------------------------------------------
# Sender does not read env / does not open network at module load
# ---------------------------------------------------------------------------


def test_sender_module_does_not_read_environ_via_ast():
    """Defensive companion to the Stage 27.7b boundary scan: the
    sender module does NOT touch ``os.environ`` at the AST level.
    The boundary scan in ``test_stage_27_7b_boundaries.py`` is the
    source of truth; this is a small redundancy.

    Uses an AST scan (not a substring scan) so legitimate
    docstring mentions of ``os.environ`` (in language like "the
    sender does NOT read ``os.environ``") do not cause a false
    positive.
    """
    import ast
    import inspect

    from PHX2.stage27 import private_discord_sender as sender_mod

    source = inspect.getsource(sender_mod)
    tree = ast.parse(source)

    os_aliases: set[str] = set()
    env_attr_names = {"environ", "getenv", "environb"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    assert alias.name not in env_attr_names, (
                        f"forbidden env-read import "
                        f"{alias.name!r}"
                    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
            ):
                assert node.attr not in env_attr_names, (
                    f"forbidden env-read pattern "
                    f"os.{node.attr}"
                )


def test_clock_is_injected_and_used_for_sent_at_utc():
    transport = Stage27_7bFakeDiscordTransport()
    payload = _sol_payload()
    clock = FrozenStage27_7bDispatchClock(
        frozen_iso="2026-05-22T13:00:00+00:00"
    )
    result = send_one_private_ping(
        payload,
        webhook_url=FAKE_WEBHOOK_URL_CANARY,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        transport=transport,
        clock=clock,
    )
    assert result.sent_at_utc == "2026-05-22T13:00:00+00:00"
