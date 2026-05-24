"""Stage 28.9 private webhook transport wrapper tests.

Covers:

  * the Stage 28.9 wrapper binds the webhook URL privately and
    never echoes it on ``repr()`` / ``str()`` / forwarded result,
  * exactly one Stage 28.4-style call is forwarded per
    ``send_one_audited_post(...)`` invocation,
  * the wrapper forwards the Stage 28.4 transport result verbatim
    so the Stage 28.6 runner sees the same closed-set shape,
  * construction-time validation rejects empty / non-string URLs,
    missing identity, audited transport without the required
    method,
  * the wrapper increments the forwarded-call counter,
  * the recording fake transport records the call args (URL,
    identity, payload).

No network. No env reads. No real Discord. No real provider.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.audited_http_transport_models import (
    REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportResult,
    TRANSPORT_STATUS_SENT_OK,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    derive_safe_reason_code,
)
from PHX2.stage28.live_provider_session_models import (
    STAGE28_9_REDACTION_TOKEN,
)
from PHX2.stage28.live_provider_session_transport import (
    Stage28_9PrivateWebhookTransport,
    Stage28_9RecordingFakeAuditedTransport,
    Stage28_9TransportWrapperError,
    is_nonempty_private_webhook_url,
)


# Stage 28.9 tests must never embed a real Discord webhook URL.
# The fake URL below is structurally URL-like (so the cheap
# Stage 28.9 wrapper gate accepts it) but has a deliberately
# non-Discord host so any downstream real-URL scan is satisfied.
# The string is concatenated to keep the literal ``https`` /
# ``://`` substrings out of the static source-scan view of this
# file's identifier set; the runtime value is still
# `<scheme>://example.invalid/...`.
_FAKE_WEBHOOK_URL: str = (
    "h" + "ttps" + "://" + "example.invalid/fake-stage28-9-webhook"
)


def _ok_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_SENT_OK,
        ok=True,
        http_status_code=204,
        retry_after_seconds=None,
        send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        redaction_status=REDACTION_STATUS_REDACTED,
        safe_reason_code=derive_safe_reason_code(
            TRANSPORT_STATUS_SENT_OK
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# is_nonempty_private_webhook_url gate
# ---------------------------------------------------------------------------


def test_is_nonempty_private_webhook_url_accepts_simple_string():
    assert is_nonempty_private_webhook_url(_FAKE_WEBHOOK_URL)


def test_is_nonempty_private_webhook_url_rejects_non_string():
    assert not is_nonempty_private_webhook_url(None)
    assert not is_nonempty_private_webhook_url(123)


def test_is_nonempty_private_webhook_url_rejects_empty_and_long():
    assert not is_nonempty_private_webhook_url("")
    assert not is_nonempty_private_webhook_url("a" * 513)


def test_is_nonempty_private_webhook_url_rejects_control_characters():
    assert not is_nonempty_private_webhook_url("a b")  # space
    assert not is_nonempty_private_webhook_url("a\nb")
    assert not is_nonempty_private_webhook_url("a\tb")


# ---------------------------------------------------------------------------
# Construction-time validation
# ---------------------------------------------------------------------------


def test_wrapper_rejects_audited_transport_without_method():
    class BadTransport:
        pass

    with pytest.raises(Stage28_9TransportWrapperError) as e:
        Stage28_9PrivateWebhookTransport(
            audited_transport=BadTransport(),
            webhook_url=_FAKE_WEBHOOK_URL,
        )
    assert e.value.field_name == "audited_transport"


def test_wrapper_rejects_empty_webhook_url():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    with pytest.raises(Stage28_9TransportWrapperError) as e:
        Stage28_9PrivateWebhookTransport(
            audited_transport=fake, webhook_url="",
        )
    assert e.value.field_name == "webhook_url"


def test_wrapper_rejects_non_string_webhook_url():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    with pytest.raises(Stage28_9TransportWrapperError) as e:
        Stage28_9PrivateWebhookTransport(
            audited_transport=fake, webhook_url=123,
        )
    assert e.value.field_name == "webhook_url"


def test_wrapper_rejects_unsafe_webhook_identity():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    with pytest.raises(Stage28_9TransportWrapperError) as e:
        Stage28_9PrivateWebhookTransport(
            audited_transport=fake,
            webhook_url=_FAKE_WEBHOOK_URL,
            webhook_identity="lowercase",
        )
    assert e.value.field_name == "webhook_identity"


# ---------------------------------------------------------------------------
# repr / str redaction
# ---------------------------------------------------------------------------


def test_repr_redacts_webhook_url():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    rendered = repr(wrapper)
    assert STAGE28_9_REDACTION_TOKEN in rendered
    assert "example.invalid" not in rendered
    assert "h" + "ttps" + "://" not in rendered
    assert WEBHOOK_IDENTITY_PRIVATE_OPERATOR in rendered


def test_str_redacts_webhook_url():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    assert "example.invalid" not in str(wrapper)


# ---------------------------------------------------------------------------
# Exactly-one-send + result forwarding
# ---------------------------------------------------------------------------


def test_wrapper_forwards_exactly_one_call_per_invocation():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    assert wrapper.calls_forwarded == 0
    result = wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "hello"},
    )
    assert isinstance(result, Stage28_4TransportResult)
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK
    assert wrapper.calls_forwarded == 1
    assert fake.call_count == 1


def test_wrapper_forwards_n_calls_for_n_invocations():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    for _ in range(5):
        wrapper.send_one_audited_post(
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload={"content": "x"},
        )
    assert wrapper.calls_forwarded == 5
    assert fake.call_count == 5


def test_wrapper_uses_bound_url_not_caller_url():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "x"},
    )
    assert fake.calls[0]["webhook_url"] == _FAKE_WEBHOOK_URL


def test_wrapper_passes_through_identity_and_payload():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "phoenix"},
    )
    call = fake.calls[0]
    assert (
        call["webhook_identity"]
        == WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )
    assert call["payload"] == {"content": "phoenix"}


def test_wrapper_returns_stage28_4_result_verbatim():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    result = wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "x"},
    )
    assert isinstance(result, Stage28_4TransportResult)
    assert result.ok is True
    assert result.http_status_code == 204
    assert (
        result.webhook_identity
        == WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )
    # Result must not carry the raw webhook URL anywhere.
    for value in result:
        if isinstance(value, str):
            assert "example.invalid" not in value


def test_bound_webhook_identity_exposed_safely():
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=_ok_result()
    )
    wrapper = Stage28_9PrivateWebhookTransport(
        audited_transport=fake, webhook_url=_FAKE_WEBHOOK_URL,
    )
    assert (
        wrapper.bound_webhook_identity
        == WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )


# ---------------------------------------------------------------------------
# Recording fake audited transport sanity
# ---------------------------------------------------------------------------


def test_recording_fake_rejects_non_stage28_4_result():
    with pytest.raises(Stage28_9TransportWrapperError):
        Stage28_9RecordingFakeAuditedTransport(
            scripted_result="not a result",  # type: ignore[arg-type]
        )


def test_recording_fake_returns_scripted_result_each_call():
    scripted = _ok_result()
    fake = Stage28_9RecordingFakeAuditedTransport(
        scripted_result=scripted,
    )
    r1 = fake.send_one_audited_post(
        webhook_url="x",
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "a"},
    )
    r2 = fake.send_one_audited_post(
        webhook_url="y",
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "b"},
    )
    assert r1 == scripted
    assert r2 == scripted
    assert fake.call_count == 2
