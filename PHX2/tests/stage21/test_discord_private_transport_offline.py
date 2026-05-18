"""Stage 21.3C private Discord transport offline tests.

These tests exercise ``DiscordPrivateTransport`` with deterministic
in-memory fake clients. No live network call happens. No
``stage21_live`` marker is used. No real HTTP client is imported.

The Stage 21.3C transport gates ``send`` through four checks in a
fixed order: dispatch-safety, live-readiness, SecretRef presence,
operator allowlist. The tests below cover the happy path and one
distinct refusal path per gate plus the two upstream-failure
paths (client raises / upstream non-2xx) and the deterministic
idempotency-token derivation. The transport NEVER passes the
webhook URL into the client method (per locked operator decision
Q1) and NEVER surfaces the raw client exception (per locked
operator decision Q3).
"""

from __future__ import annotations

import re

import pytest

from PHX2.stage21.allowlist import (
    OperatorAllowlist,
    build_allowlist_from_sequence,
)
from PHX2.stage21.constants import (
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_LIVE_PRIVATE,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_MODE,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_SINK_MODE,
    ProviderModeName,
    SinkModeName,
)
from PHX2.stage21.discord_private_transport import (
    DiscordPostOutcome,
    DiscordPrivateTransport,
    DiscordTransportClientError,
    DiscordTransportError,
    DiscordWebhookClientProtocol,
    REJECTION_REASON_CLIENT_POST_FAILED,
    REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
    REJECTION_REASON_READINESS_NOT_READY,
    REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
    REJECTION_REASON_UPSTREAM_NON_2XX,
    REJECTION_REASON_WEBHOOK_NOT_PRESENT,
    STAGE21_3C_REJECTION_REASONS,
)
from PHX2.stage21.live_secrets_boundary import (
    ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
    ENV_VAR_LIVE_SMOKE_MODE,
    ENV_VAR_PROVIDER_ID,
    ENV_VAR_SAFE_FOR_LIVE_DISPATCH,
    LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    LIVE_SMOKE_MODE_TOKEN,
    PLACEHOLDER_PROVIDER_ID_21_3B,
    Stage21LiveReadinessConfig,
    load_live_readiness_config_from_env,
)
from PHX2.stage21.secret_redaction import SecretRef, build_secret_ref
from PHX2.stage21.transport_contracts import (
    Stage21Transport,
    TransportPayload,
    TransportResult,
)


# Operator-typed non-secret slot values that the live-readiness
# loader treats as "present". The strings are short, look like
# safe identifier shapes, and never appear in any operator-real
# vault.
_FAKE_PROVIDER_API_KEY_VALUE: str = "fake-provider-api-key-for-tests"
_FAKE_PROVIDER_RPC_URL_VALUE: str = "fake-provider-rpc-url-for-tests"
_FAKE_DISCORD_WEBHOOK_URL_VALUE: str = "fake-private-webhook-for-tests"


_ALLOWED_RECIPIENT: str = "alice-operator"
_OTHER_ALLOWED_RECIPIENT: str = "bob-operator"


def _fully_ready_env() -> dict[str, str]:
    """Build an env mapping that satisfies every readiness precondition."""
    return {
        ENV_VAR_PROVIDER_MODE: ProviderModeName.LIVE.value,
        ENV_VAR_SINK_MODE: SinkModeName.PRIVATE_PREVIEW.value,
        ENV_VAR_LIVE_PRIVATE: "true",
        ENV_VAR_PROVIDER_API_KEY: _FAKE_PROVIDER_API_KEY_VALUE,
        ENV_VAR_PROVIDER_RPC_URL: _FAKE_PROVIDER_RPC_URL_VALUE,
        ENV_VAR_DISCORD_WEBHOOK_URL: _FAKE_DISCORD_WEBHOOK_URL_VALUE,
        ENV_VAR_LIVE_SMOKE_MODE: LIVE_SMOKE_MODE_TOKEN,
        ENV_VAR_PROVIDER_ID: PLACEHOLDER_PROVIDER_ID_21_3B,
        ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "true",
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    }


def _ready_config() -> Stage21LiveReadinessConfig:
    return load_live_readiness_config_from_env(_fully_ready_env())


def _present_webhook_ref() -> SecretRef:
    return build_secret_ref(
        ENV_VAR_DISCORD_WEBHOOK_URL,
        _FAKE_DISCORD_WEBHOOK_URL_VALUE,
    )


def _absent_webhook_ref() -> SecretRef:
    return build_secret_ref(ENV_VAR_DISCORD_WEBHOOK_URL, "")


def _populated_allowlist() -> OperatorAllowlist:
    return build_allowlist_from_sequence(
        [_ALLOWED_RECIPIENT, _OTHER_ALLOWED_RECIPIENT]
    )


def _empty_allowlist() -> OperatorAllowlist:
    return build_allowlist_from_sequence([])


def _safe_payload(
    *,
    recipient: str = _ALLOWED_RECIPIENT,
    body_text: str = (
        "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- "
        "DO NOT FORWARD AS PUBLIC SIGNAL"
    ),
    private_preview_marker_present: bool = True,
    safe_for_public_dispatch: bool = False,
) -> TransportPayload:
    return TransportPayload(
        recipient=recipient,
        body_text=body_text,
        private_preview_marker_present=private_preview_marker_present,
        safe_for_public_dispatch=safe_for_public_dispatch,
    )


# ---------------------------------------------------------------------------
# Offline fake clients (Stage 21.3C test scaffold, NOT production)
# ---------------------------------------------------------------------------


class RecordingFakeDiscordClient:
    """Deterministic in-memory fake. Records every post_webhook call."""

    def __init__(
        self,
        *,
        accepted: bool = True,
        status_class: str = "2xx",
        upstream_error_type: str = "",
    ) -> None:
        self._outcome: DiscordPostOutcome = DiscordPostOutcome(
            accepted=accepted,
            status_class=status_class,
            upstream_error_type=upstream_error_type,
        )
        self.calls: list[dict[str, str]] = []

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        self.calls.append(
            {
                "body_text": body_text,
                "idempotency_token": idempotency_token,
            }
        )
        return self._outcome


class RaisingFakeDiscordClient:
    """Fake client whose ``post_webhook`` raises a leaky RuntimeError."""

    SECRET_TOKEN_IN_ARGS: str = "SECRET_BODY_LEAK_AAA111BBB222"

    def __init__(self) -> None:
        self.call_count: int = 0

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        self.call_count += 1
        raise RuntimeError(self.SECRET_TOKEN_IN_ARGS)


class RejectingFakeDiscordClient:
    """Fake client returning ``accepted=False`` with a 5xx bucket."""

    def __init__(self) -> None:
        self.call_count: int = 0

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        self.call_count += 1
        return DiscordPostOutcome(
            accepted=False,
            status_class="5xx",
            upstream_error_type="upstream_failure_bucket",
        )


# ---------------------------------------------------------------------------
# Helper builder
# ---------------------------------------------------------------------------


def _build_transport(
    *,
    client: object,
    readiness: Stage21LiveReadinessConfig | None = None,
    webhook_ref: SecretRef | None = None,
    allowlist: OperatorAllowlist | None = None,
) -> DiscordPrivateTransport:
    return DiscordPrivateTransport(
        client=client,  # type: ignore[arg-type]
        readiness=readiness if readiness is not None else _ready_config(),
        webhook_ref=(
            webhook_ref if webhook_ref is not None else _present_webhook_ref()
        ),
        allowlist=(
            allowlist if allowlist is not None else _populated_allowlist()
        ),
    )


# ---------------------------------------------------------------------------
# Locked closed-set vocabulary
# ---------------------------------------------------------------------------


def test_rejection_reason_set_is_locked_to_exact_six_tokens():
    assert set(STAGE21_3C_REJECTION_REASONS) == {
        "readiness_not_ready",
        "recipient_not_in_allowlist",
        "dispatch_safety_rejected",
        "webhook_not_present",
        "client_post_failed",
        "upstream_non_2xx",
    }
    assert len(STAGE21_3C_REJECTION_REASONS) == 6
    assert len(set(STAGE21_3C_REJECTION_REASONS)) == 6


def test_rejection_reason_constants_match_locked_string_values():
    assert REJECTION_REASON_READINESS_NOT_READY == "readiness_not_ready"
    assert REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST == (
        "recipient_not_in_allowlist"
    )
    assert REJECTION_REASON_DISPATCH_SAFETY_REJECTED == (
        "dispatch_safety_rejected"
    )
    assert REJECTION_REASON_WEBHOOK_NOT_PRESENT == "webhook_not_present"
    assert REJECTION_REASON_CLIENT_POST_FAILED == "client_post_failed"
    assert REJECTION_REASON_UPSTREAM_NON_2XX == "upstream_non_2xx"


# ---------------------------------------------------------------------------
# Constructor rejection
# ---------------------------------------------------------------------------


def test_constructor_rejects_none_client():
    with pytest.raises(DiscordTransportError):
        DiscordPrivateTransport(
            client=None,  # type: ignore[arg-type]
            readiness=_ready_config(),
            webhook_ref=_present_webhook_ref(),
            allowlist=_populated_allowlist(),
        )


def test_constructor_rejects_none_readiness():
    with pytest.raises(DiscordTransportError):
        DiscordPrivateTransport(
            client=RecordingFakeDiscordClient(),
            readiness=None,  # type: ignore[arg-type]
            webhook_ref=_present_webhook_ref(),
            allowlist=_populated_allowlist(),
        )


def test_constructor_rejects_none_webhook_ref():
    with pytest.raises(DiscordTransportError):
        DiscordPrivateTransport(
            client=RecordingFakeDiscordClient(),
            readiness=_ready_config(),
            webhook_ref=None,  # type: ignore[arg-type]
            allowlist=_populated_allowlist(),
        )


def test_constructor_rejects_none_allowlist():
    with pytest.raises(DiscordTransportError):
        DiscordPrivateTransport(
            client=RecordingFakeDiscordClient(),
            readiness=_ready_config(),
            webhook_ref=_present_webhook_ref(),
            allowlist=None,  # type: ignore[arg-type]
        )


def test_module_local_error_hierarchy_is_rooted_at_exception():
    assert issubclass(DiscordTransportError, Exception)
    assert issubclass(DiscordTransportClientError, DiscordTransportError)


# ---------------------------------------------------------------------------
# Repr redaction
# ---------------------------------------------------------------------------


def test_repr_does_not_leak_webhook_or_fingerprint_or_recipient_or_secrets():
    transport = _build_transport(client=RecordingFakeDiscordClient())
    rendered = repr(transport)
    # The webhook fingerprint is non-empty for a present SecretRef;
    # it must not leak into the repr.
    webhook_ref = _present_webhook_ref()
    assert webhook_ref.fingerprint not in rendered
    # The recipient list must not leak.
    assert _ALLOWED_RECIPIENT not in rendered
    assert _OTHER_ALLOWED_RECIPIENT not in rendered
    # The raw fake webhook value must not leak.
    assert _FAKE_DISCORD_WEBHOOK_URL_VALUE not in rendered
    assert _FAKE_PROVIDER_API_KEY_VALUE not in rendered
    assert _FAKE_PROVIDER_RPC_URL_VALUE not in rendered
    # Only the transport class name and client type name appear.
    assert "DiscordPrivateTransport" in rendered
    assert "RecordingFakeDiscordClient" in rendered


def test_repr_does_not_leak_client_repr_when_client_has_sensitive_repr():
    class _LeakyClient:
        def __repr__(self) -> str:
            return "<LeakyClient webhook='SECRET_LEAK_VALUE_98765'>"

        def post_webhook(
            self,
            *,
            body_text: str,
            idempotency_token: str,
        ) -> DiscordPostOutcome:
            return DiscordPostOutcome(
                accepted=True,
                status_class="2xx",
                upstream_error_type="",
            )

    transport = _build_transport(client=_LeakyClient())
    rendered = repr(transport)
    assert "SECRET_LEAK_VALUE_98765" not in rendered
    assert "webhook='" not in rendered
    assert "_LeakyClient" in rendered


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_dispatches_through_fake_client():
    client = RecordingFakeDiscordClient(accepted=True, status_class="2xx")
    transport = _build_transport(client=client)
    result = transport.send(_safe_payload())
    assert result.dispatched is True
    assert result.rejection_reason == ""
    assert result.recipient == _ALLOWED_RECIPIENT
    assert len(client.calls) == 1


def test_happy_path_passes_body_text_to_client_unchanged():
    body = (
        "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- "
        "DO NOT FORWARD AS PUBLIC SIGNAL"
    )
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload(body_text=body))
    assert client.calls[0]["body_text"] == body


def test_happy_path_returns_transport_result_namedtuple():
    transport = _build_transport(client=RecordingFakeDiscordClient())
    result = transport.send(_safe_payload())
    assert isinstance(result, TransportResult)


def test_transport_satisfies_stage21_transport_protocol():
    transport = _build_transport(client=RecordingFakeDiscordClient())
    typed: Stage21Transport = transport
    result = typed.send(_safe_payload())
    assert result.dispatched is True


# ---------------------------------------------------------------------------
# Dispatch-safety refusal
# ---------------------------------------------------------------------------


def test_dispatch_safety_failure_safe_for_public_dispatch_true_refuses():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    payload = _safe_payload()._replace(safe_for_public_dispatch=True)
    result = transport.send(payload)
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_DISPATCH_SAFETY_REJECTED
    assert client.calls == []


def test_dispatch_safety_failure_marker_missing_refuses():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    payload = _safe_payload()._replace(private_preview_marker_present=False)
    result = transport.send(payload)
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_DISPATCH_SAFETY_REJECTED
    assert client.calls == []


# ---------------------------------------------------------------------------
# Readiness refusals
# ---------------------------------------------------------------------------


def test_disabled_readiness_mode_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_LIVE_SMOKE_MODE] = ""
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


def test_provider_mode_not_live_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_MODE] = ProviderModeName.FAKE.value
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


def test_sink_mode_not_private_preview_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_SINK_MODE] = SinkModeName.FAKE.value
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


def test_live_private_not_true_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_LIVE_PRIVATE] = "false"
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


def test_safe_for_live_dispatch_not_true_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_SAFE_FOR_LIVE_DISPATCH] = "false"
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


def test_safety_acknowledgement_mismatch_refuses_with_readiness_not_ready():
    env = _fully_ready_env()
    env[ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT] = "ack-wrong-value"
    readiness = load_live_readiness_config_from_env(env)
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, readiness=readiness)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_READINESS_NOT_READY
    assert client.calls == []


# ---------------------------------------------------------------------------
# Webhook-presence refusal
# ---------------------------------------------------------------------------


def test_missing_webhook_refuses_with_webhook_not_present():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(
        client=client,
        webhook_ref=_absent_webhook_ref(),
    )
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_WEBHOOK_NOT_PRESENT
    assert client.calls == []


# ---------------------------------------------------------------------------
# Allowlist refusals
# ---------------------------------------------------------------------------


def test_recipient_not_in_allowlist_refuses():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    payload = _safe_payload(recipient="charlie-unknown")
    result = transport.send(payload)
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST
    assert client.calls == []


def test_fail_closed_empty_allowlist_refuses():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, allowlist=_empty_allowlist())
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST
    assert client.calls == []


# ---------------------------------------------------------------------------
# Client-failure refusals (sanitization invariants)
# ---------------------------------------------------------------------------


def test_client_raising_runtime_error_refuses_with_client_post_failed():
    client = RaisingFakeDiscordClient()
    transport = _build_transport(client=client)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_CLIENT_POST_FAILED


def test_client_raising_runtime_error_does_not_leak_raw_exception_message():
    client = RaisingFakeDiscordClient()
    transport = _build_transport(client=client)
    result = transport.send(_safe_payload())
    rendered = repr(result) + str(result) + result.rejection_reason
    assert RaisingFakeDiscordClient.SECRET_TOKEN_IN_ARGS not in rendered
    assert "SECRET_BODY_LEAK" not in rendered


def test_client_raising_runtime_error_is_not_retried():
    client = RaisingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    # The transport invokes the client exactly once even when the
    # client raises. Stage 21.3C does NOT retry; a Stage 22 retry
    # layer would sit between the transport and the runner.
    assert client.call_count == 1


def test_client_raising_runtime_error_does_not_propagate_to_caller():
    class _BroadlyLeakyClient:
        def post_webhook(
            self,
            *,
            body_text: str,
            idempotency_token: str,
        ) -> DiscordPostOutcome:
            raise Exception("CREDENTIAL_LEAK_zZyYxX9988")

    transport = _build_transport(client=_BroadlyLeakyClient())
    # The transport must not raise on a client failure; it returns
    # a TransportResult instead.
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_CLIENT_POST_FAILED
    # No leak into the result.
    rendered_all = (
        repr(result) + str(result) + result.rejection_reason
    )
    assert "CREDENTIAL_LEAK_zZyYxX9988" not in rendered_all


# ---------------------------------------------------------------------------
# Upstream-non-2xx refusal
# ---------------------------------------------------------------------------


def test_accepted_false_refuses_with_upstream_non_2xx():
    client = RejectingFakeDiscordClient()
    transport = _build_transport(client=client)
    result = transport.send(_safe_payload())
    assert result.dispatched is False
    assert result.rejection_reason == REJECTION_REASON_UPSTREAM_NON_2XX
    assert client.call_count == 1


def test_accepted_false_does_not_leak_status_bucket_or_error_type():
    client = RejectingFakeDiscordClient()
    transport = _build_transport(client=client)
    result = transport.send(_safe_payload())
    rendered = repr(result) + str(result) + result.rejection_reason
    # status_class / upstream_error_type are not surfaced into the
    # narrow TransportResult vocabulary (locked Q2 decision).
    assert "5xx" not in rendered
    assert "upstream_failure_bucket" not in rendered


def test_accepted_false_is_not_retried():
    client = RejectingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    assert client.call_count == 1


# ---------------------------------------------------------------------------
# Deterministic idempotency token
# ---------------------------------------------------------------------------


def test_idempotency_token_is_deterministic_for_identical_payload():
    client_a = RecordingFakeDiscordClient()
    transport_a = _build_transport(client=client_a)
    transport_a.send(_safe_payload())

    client_b = RecordingFakeDiscordClient()
    transport_b = _build_transport(client=client_b)
    transport_b.send(_safe_payload())

    token_a = client_a.calls[0]["idempotency_token"]
    token_b = client_b.calls[0]["idempotency_token"]
    assert token_a == token_b


def test_idempotency_token_differs_when_body_changes():
    client_a = RecordingFakeDiscordClient()
    transport_a = _build_transport(client=client_a)
    transport_a.send(
        _safe_payload(
            body_text=(
                "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- "
                "DO NOT FORWARD -- BODY ONE"
            )
        )
    )

    client_b = RecordingFakeDiscordClient()
    transport_b = _build_transport(client=client_b)
    transport_b.send(
        _safe_payload(
            body_text=(
                "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- "
                "DO NOT FORWARD -- BODY TWO"
            )
        )
    )

    token_a = client_a.calls[0]["idempotency_token"]
    token_b = client_b.calls[0]["idempotency_token"]
    assert token_a != token_b


def test_idempotency_token_differs_when_recipient_changes():
    client_a = RecordingFakeDiscordClient()
    transport_a = _build_transport(client=client_a)
    transport_a.send(_safe_payload(recipient=_ALLOWED_RECIPIENT))

    client_b = RecordingFakeDiscordClient()
    transport_b = _build_transport(client=client_b)
    transport_b.send(_safe_payload(recipient=_OTHER_ALLOWED_RECIPIENT))

    token_a = client_a.calls[0]["idempotency_token"]
    token_b = client_b.calls[0]["idempotency_token"]
    assert token_a != token_b


def test_idempotency_token_does_not_contain_raw_body_text():
    body = "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- DO NOT FORWARD"
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload(body_text=body))
    token = client.calls[0]["idempotency_token"]
    assert body not in token
    # The token never contains common body-content substrings.
    assert "OPERATOR" not in token
    assert "PRIVATE" not in token


def test_idempotency_token_does_not_contain_raw_recipient():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload(recipient=_ALLOWED_RECIPIENT))
    token = client.calls[0]["idempotency_token"]
    assert _ALLOWED_RECIPIENT not in token


def test_idempotency_token_does_not_contain_webhook_or_fingerprint_or_secret():
    webhook_ref = _present_webhook_ref()
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client, webhook_ref=webhook_ref)
    transport.send(_safe_payload())
    token = client.calls[0]["idempotency_token"]
    assert _FAKE_DISCORD_WEBHOOK_URL_VALUE not in token
    assert _FAKE_PROVIDER_API_KEY_VALUE not in token
    assert _FAKE_PROVIDER_RPC_URL_VALUE not in token
    assert webhook_ref.fingerprint not in token


def test_idempotency_token_is_lowercase_hex_string():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    token = client.calls[0]["idempotency_token"]
    assert re.fullmatch(r"[0-9a-f]+", token), (
        f"token {token!r} is not lowercase hex"
    )
    # The locked prefix length is 32 hex chars.
    assert len(token) == 32


# ---------------------------------------------------------------------------
# Webhook-URL non-propagation invariant
# ---------------------------------------------------------------------------


def test_client_post_webhook_signature_is_keyword_only_body_and_token():
    """The Protocol's ``post_webhook`` accepts only body_text+idempotency_token.

    Per locked operator decision Q1 the transport does NOT pass the
    webhook URL into the client method. The test pins the call
    surface exactly so a future drift adding a positional
    ``webhook_url`` parameter would fail here.
    """
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    call = client.calls[0]
    assert set(call.keys()) == {"body_text", "idempotency_token"}


def test_client_never_receives_webhook_url_kwarg():
    class _StrictClient:
        def __init__(self) -> None:
            self.seen_kwargs: list[set[str]] = []

        def post_webhook(self, **kwargs: object) -> DiscordPostOutcome:
            self.seen_kwargs.append(set(kwargs.keys()))
            return DiscordPostOutcome(
                accepted=True,
                status_class="2xx",
                upstream_error_type="",
            )

    client = _StrictClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    seen = client.seen_kwargs[0]
    assert "webhook_url" not in seen
    assert "url" not in seen
    assert "secret" not in seen
    assert "fingerprint" not in seen
    assert seen == {"body_text", "idempotency_token"}


# ---------------------------------------------------------------------------
# Repeated invocation is independent (no internal retry state)
# ---------------------------------------------------------------------------


def test_repeated_invocation_calls_client_once_per_send():
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    transport.send(_safe_payload())
    transport.send(_safe_payload())
    assert len(client.calls) == 3


def test_repeated_invocation_with_identical_payload_yields_identical_token():
    # Same payload always produces the same idempotency token, no
    # matter how many times ``send`` is called.
    client = RecordingFakeDiscordClient()
    transport = _build_transport(client=client)
    transport.send(_safe_payload())
    transport.send(_safe_payload())
    transport.send(_safe_payload())
    tokens = {call["idempotency_token"] for call in client.calls}
    assert len(tokens) == 1


# ---------------------------------------------------------------------------
# Protocol typing smoke test
# ---------------------------------------------------------------------------


def test_recording_fake_satisfies_client_protocol_via_static_assignment():
    client: DiscordWebhookClientProtocol = RecordingFakeDiscordClient()
    outcome = client.post_webhook(body_text="x", idempotency_token="t")
    assert isinstance(outcome, DiscordPostOutcome)
    assert outcome.accepted is True
