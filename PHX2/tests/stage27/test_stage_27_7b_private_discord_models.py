"""Stage 27.7b private Discord dispatch model tests.

Pins:

  * Schema-version handles are the locked Stage 27.7b strings.
  * ``DISPATCH_STATUS_VALUES`` is the locked closed set (8 tokens).
  * ``DISPATCH_REASON_VALUES`` carries every closed-set reason
    token referenced by the sender + dispatch layer.
  * ``DISPATCH_MODE_VALUES`` is exactly ``(DRY_RUN, LIVE_SEND)``.
  * ``REDACTION_STATUS_VALUES`` is the locked closed set.
  * ``Stage27_7bDispatchResultRecord`` is an immutable NamedTuple
    with the locked field set; webhook-URL-class field names are
    forbidden.
  * ``is_forbidden_dispatch_result_field_name`` rejects raw-payload
    / secret / webhook / api-key / rpc-url substrings.
  * ``NO_PAYLOAD_SENTINEL`` literal is distinctive and is not in
    the dispatch-status / reason / mode vocabulary.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import private_discord_models as m


# ---------------------------------------------------------------------------
# Version-axis pins
# ---------------------------------------------------------------------------


def test_stage_27_7b_minor_version_handle():
    assert m.STAGE27_7B_MINOR_VERSION == "27.7b"


def test_stage_27_7b_dispatch_result_schema_version_handle():
    assert m.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION == (
        "stage27_v0_private_discord_dispatch_result"
    )


# ---------------------------------------------------------------------------
# Closed-set: dispatch_status
# ---------------------------------------------------------------------------


def test_dispatch_status_values_locked_closed_set():
    assert m.DISPATCH_STATUS_VALUES == (
        "SENT",
        "DRY_RUN_NOT_SENT",
        "REFUSED_NOT_LIVE",
        "REFUSED_MISSING_WEBHOOK",
        "REFUSED_MULTIPLE_PAYLOADS",
        "REFUSED_SUPPRESSED_PAIR",
        "REFUSED_UNAUTHORIZED_MODE",
        "TRANSPORT_ERROR",
    )


def test_dispatch_status_not_sent_values_excludes_sent_and_transport_error():
    not_sent = m.DISPATCH_STATUS_NOT_SENT_VALUES
    assert m.DISPATCH_STATUS_SENT not in not_sent
    assert m.DISPATCH_STATUS_TRANSPORT_ERROR not in not_sent
    # Every refusal + dry-run status is in the not-sent set.
    for token in (
        m.DISPATCH_STATUS_DRY_RUN_NOT_SENT,
        m.DISPATCH_STATUS_REFUSED_NOT_LIVE,
        m.DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
        m.DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS,
        m.DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
        m.DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE,
    ):
        assert token in not_sent


# ---------------------------------------------------------------------------
# Closed-set: dispatch_reason
# ---------------------------------------------------------------------------


def test_dispatch_reason_values_locked_closed_set():
    assert m.DISPATCH_REASON_VALUES == (
        "LIVE_SEND_OK",
        "DRY_RUN_MODE",
        "LIVE_AUTHORITY_NOT_ALLOWED",
        "OPERATOR_LIVE_REQUEST_MISSING",
        "SMOKE_DISPATCH_REQUEST_MISSING",
        "UNKNOWN_DISPATCH_MODE",
        "WEBHOOK_URL_MISSING",
        "WEBHOOK_IDENTITY_MISSING",
        "MULTIPLE_PAYLOADS_REFUSED",
        "NO_PAYLOAD_PROVIDED",
        "PAIR_SUPPRESS_UNKNOWN",
        "PAIR_SUPPRESS_DISAGREE",
        "PAIR_USDC_REQUIRES_OBSERVE_ONLY",
        "PAIR_SOL_NOT_ON_EXISTING_LANE",
        "TRANSPORT_EXCEPTION",
        "TRANSPORT_NON_SUCCESS",
    )


# ---------------------------------------------------------------------------
# Closed-set: dispatch_mode
# ---------------------------------------------------------------------------


def test_dispatch_mode_values_locked_closed_set():
    assert m.DISPATCH_MODE_VALUES == ("DRY_RUN", "LIVE_SEND")


# ---------------------------------------------------------------------------
# Closed-set: redaction_status
# ---------------------------------------------------------------------------


def test_redaction_status_values_locked_closed_set():
    assert m.REDACTION_STATUS_VALUES == (
        "REDACTED",
        "REDACTION_FAILED",
    )


# ---------------------------------------------------------------------------
# Stage27_7bDispatchResultRecord field set
# ---------------------------------------------------------------------------


_EXPECTED_DISPATCH_RESULT_FIELDS: frozenset[str] = frozenset(
    {
        "dispatch_status",
        "dispatch_reason",
        "dispatch_mode",
        "webhook_identity",
        "ping_id",
        "run_id",
        "session_id",
        "sent_at_utc",
        "transport_status_code",
        "redaction_status",
        "schema_version",
        "pair_quote_asset",
        "render_status",
    }
)


def test_dispatch_result_field_set_locked():
    fields = set(m.Stage27_7bDispatchResultRecord._fields)
    assert fields == _EXPECTED_DISPATCH_RESULT_FIELDS


def test_dispatch_result_no_webhook_url_field():
    fields = set(m.Stage27_7bDispatchResultRecord._fields)
    for forbidden in (
        "webhook_url",
        "discord_webhook_url",
        "raw_webhook_url",
        "webhook_endpoint",
    ):
        assert forbidden not in fields


def test_dispatch_result_no_raw_payload_field():
    fields = set(m.Stage27_7bDispatchResultRecord._fields)
    for forbidden in (
        "raw_payload",
        "payload_blob",
        "raw_response",
        "response_body",
        "api_key",
        "apikey",
        "bearer_token",
        "authorization_header",
        "rpc_url",
        "private_key",
    ):
        assert forbidden not in fields


def test_dispatch_result_is_namedtuple_subclass():
    assert issubclass(
        m.Stage27_7bDispatchResultRecord, tuple
    )
    # NamedTuple instances are tuples.
    record = m.Stage27_7bDispatchResultRecord(
        dispatch_status=m.DISPATCH_STATUS_DRY_RUN_NOT_SENT,
        dispatch_reason=m.DISPATCH_REASON_DRY_RUN_MODE,
        dispatch_mode=m.DISPATCH_MODE_DRY_RUN,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        ping_id="ping-1",
        run_id="run-1",
        session_id="sess-1",
        sent_at_utc="2026-05-22T12:00:30+00:00",
        transport_status_code=None,
        redaction_status=m.REDACTION_STATUS_REDACTED,
        schema_version=m.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
        pair_quote_asset="SOL",
        render_status="RENDERED",
    )
    assert isinstance(record, tuple)


def test_dispatch_result_is_immutable():
    record = m.Stage27_7bDispatchResultRecord(
        dispatch_status=m.DISPATCH_STATUS_SENT,
        dispatch_reason=m.DISPATCH_REASON_LIVE_SEND_OK,
        dispatch_mode=m.DISPATCH_MODE_LIVE_SEND,
        webhook_identity=m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        ping_id="ping-2",
        run_id=None,
        session_id=None,
        sent_at_utc="2026-05-22T12:00:30+00:00",
        transport_status_code=200,
        redaction_status=m.REDACTION_STATUS_REDACTED,
        schema_version=m.STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
        pair_quote_asset="SOL",
        render_status="RENDERED",
    )
    with pytest.raises(AttributeError):
        record.dispatch_status = "OTHER"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Forbidden field-name helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "raw_payload",
        "raw_payload_blob",
        "payload_blob",
        "secret",
        "api_key",
        "apikey",
        "token_secret",
        "webhook_url",
        "discord_webhook_url",
        "rpc_url",
        "private_key",
        "credentials",
        "bearer_token",
        "authorization_header",
        # Substring matches must also fire.
        "operator_webhook_url",
        "primary_discord_webhook_url",
        "the_raw_payload_blob",
        "an_api_key_here",
    ],
)
def test_forbidden_field_name_rejected(name):
    assert m.is_forbidden_dispatch_result_field_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "ping_id",
        "run_id",
        "session_id",
        "dispatch_status",
        "dispatch_reason",
        "dispatch_mode",
        "webhook_identity",
        "sent_at_utc",
        "transport_status_code",
        "redaction_status",
        "schema_version",
        "pair_quote_asset",
        "render_status",
    ],
)
def test_safe_field_name_admitted(name):
    assert m.is_forbidden_dispatch_result_field_name(name) is False


def test_forbidden_field_name_non_string_input_returns_false():
    assert m.is_forbidden_dispatch_result_field_name(None) is False
    assert m.is_forbidden_dispatch_result_field_name(123) is False
    assert m.is_forbidden_dispatch_result_field_name(b"webhook_url") is False


def test_forbidden_field_name_vocabulary_includes_webhook_url():
    assert "webhook_url" in m.FORBIDDEN_DISPATCH_RESULT_FIELD_NAMES
    assert "discord_webhook_url" in m.FORBIDDEN_DISPATCH_RESULT_FIELD_NAMES


# ---------------------------------------------------------------------------
# Webhook identity label literal
# ---------------------------------------------------------------------------


def test_webhook_identity_private_operator_label_is_safe_string():
    label = m.WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    assert isinstance(label, str) and label != ""
    # The label must NOT look like a URL.
    assert "://" not in label
    assert "/" not in label
    assert "." not in label


# ---------------------------------------------------------------------------
# NO_PAYLOAD_SENTINEL is distinctive
# ---------------------------------------------------------------------------


def test_no_payload_sentinel_is_distinctive_literal():
    assert m.NO_PAYLOAD_SENTINEL == "<no_payload>"
    # The sentinel must not collide with any closed-set token.
    assert m.NO_PAYLOAD_SENTINEL not in m.DISPATCH_STATUS_VALUES
    assert m.NO_PAYLOAD_SENTINEL not in m.DISPATCH_REASON_VALUES
    assert m.NO_PAYLOAD_SENTINEL not in m.DISPATCH_MODE_VALUES
    assert m.NO_PAYLOAD_SENTINEL not in m.REDACTION_STATUS_VALUES
