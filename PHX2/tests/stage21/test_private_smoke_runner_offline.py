"""Stage 21.4 private smoke runner -- offline behaviour tests.

Every test uses in-memory fakes. No real network, no real
provider client, no real Discord client. Two scopes:

  * The bulk of the tests use a minimal ``_FakeProviderAdapter``
    and ``_FakeTransport`` so the runner's gate sequence is
    exercised in isolation.
  * One integration test wires the REAL Stage 21.3C
    ``DiscordPrivateTransport`` against an offline in-memory
    Discord client so the runner / transport composition is
    exercised end-to-end without any network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pytest

from PHX2.stage21.allowlist import build_allowlist_from_sequence
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
    REJECTION_REASON_CLIENT_POST_FAILED,
    REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
    REJECTION_REASON_READINESS_NOT_READY,
    REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
    REJECTION_REASON_UPSTREAM_NON_2XX,
    REJECTION_REASON_WEBHOOK_NOT_PRESENT,
)
from PHX2.stage21.live_secrets_boundary import (
    ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
    ENV_VAR_LIVE_SMOKE_MODE,
    ENV_VAR_PROVIDER_ID,
    ENV_VAR_SAFE_FOR_LIVE_DISPATCH,
    HELIUS_PROVIDER_ID,
    LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    LIVE_SMOKE_MODE_TOKEN,
    PLACEHOLDER_PROVIDER_ID_21_3B,
    load_live_readiness_config_from_env,
)
from PHX2.stage21.normalized_events import (
    NormalizedLiveEvent,
    normalize_fake_event,
)
from PHX2.stage21.ping_payloads import (
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
    STAGE21_FAKE_SOURCE_KIND,
)
from PHX2.stage21.private_smoke_runner import (
    DEFAULT_MAX_EVENTS,
    SKIPPED_REASON_PROVIDER_FETCH_FAILED,
    SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
    SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS,
    SKIPPED_REASON_READINESS_NOT_READY,
    STAGE21_4_SKIPPED_REASONS,
    STAGE21_4_SMOKE_LABEL,
    Stage21PrivateSmokeResult,
    Stage21RunnerError,
    run_one_private_smoke_ping,
)
from PHX2.stage21.secret_redaction import build_secret_ref
from PHX2.stage21.transport_contracts import (
    TransportPayload,
    TransportResult,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _fully_ready_env() -> dict[str, str]:
    """Build an env mapping that satisfies every readiness precondition."""
    return {
        ENV_VAR_PROVIDER_MODE: ProviderModeName.LIVE.value,
        ENV_VAR_SINK_MODE: SinkModeName.PRIVATE_PREVIEW.value,
        ENV_VAR_LIVE_PRIVATE: "true",
        ENV_VAR_PROVIDER_API_KEY: "fake-api-key-for-tests-only",
        ENV_VAR_PROVIDER_RPC_URL: "fake-rpc-url-for-tests-only",
        ENV_VAR_DISCORD_WEBHOOK_URL: "fake-discord-url-for-tests-only",
        ENV_VAR_LIVE_SMOKE_MODE: LIVE_SMOKE_MODE_TOKEN,
        ENV_VAR_PROVIDER_ID: PLACEHOLDER_PROVIDER_ID_21_3B,
        ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "true",
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    }


def _make_event(
    *,
    provider_event_id: str = "evt_for_tests_1",
    mint: str = "MintForTestsOnly1",
    event_type: str = "fake_swap",
    slot: int = 100,
    signature: str = "fake_sig_for_tests_only_abc123",
) -> NormalizedLiveEvent:
    """Build a deterministic fake NormalizedLiveEvent for tests.

    Uses ``normalize_fake_event`` so the resulting record satisfies
    the same Stage 21 invariants the real decoder produces. All
    fixture string values are SHORT_LABEL / SHORT_IDENTIFIER safe
    (alphanumeric + underscores; the ``provider_event_id`` may use
    hyphens because it is validated as SHORT_IDENTIFIER, not
    SHORT_LABEL).
    """
    return normalize_fake_event(
        provider_event_id=provider_event_id,
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind=STAGE21_FAKE_SOURCE_KIND,
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint=mint,
        event_type=event_type,
        observed_at_utc="2026-01-01T00:00:00Z",
        slot=slot,
        signature=signature,
        raw_payload={"k": "v"},
    )


class _FakeProviderAdapter:
    """In-memory provider adapter that returns a fixed event sequence.

    Satisfies the Stage 21.4 ``Stage21ProviderAdapter`` Protocol
    structurally. Records every call for assertion.
    """

    def __init__(
        self,
        events: Sequence[NormalizedLiveEvent] = (),
        *,
        raise_exception: Optional[BaseException] = None,
    ) -> None:
        self._events: tuple[NormalizedLiveEvent, ...] = tuple(events)
        self._raise = raise_exception
        self.calls: list[dict[str, object]] = []

    def fetch_normalized_events(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> tuple[NormalizedLiveEvent, ...]:
        self.calls.append({"cursor": cursor, "max_results": max_results})
        if self._raise is not None:
            raise self._raise
        return self._events


class _TripwireProviderAdapter:
    """Adapter that raises if ``fetch_normalized_events`` is ever called.

    Used to assert the runner short-circuits BEFORE the adapter
    when readiness is disabled.
    """

    def __init__(self) -> None:
        self.invocations: int = 0

    def fetch_normalized_events(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> tuple[NormalizedLiveEvent, ...]:
        self.invocations += 1
        raise AssertionError(
            "tripwire: provider adapter must NOT be called when readiness "
            "is disabled"
        )


class _FakeTransport:
    """In-memory transport with a configurable ``TransportResult``.

    Satisfies the Stage21Transport Protocol structurally. Echoes
    the payload's recipient back through the result.
    """

    def __init__(
        self,
        result: Optional[TransportResult] = None,
    ) -> None:
        self._result: TransportResult = (
            result
            if result is not None
            else TransportResult(
                dispatched=True,
                rejection_reason="",
                recipient="",
            )
        )
        self.calls: list[TransportPayload] = []

    def send(self, payload: TransportPayload) -> TransportResult:
        self.calls.append(payload)
        return TransportResult(
            dispatched=self._result.dispatched,
            rejection_reason=self._result.rejection_reason,
            recipient=payload.recipient,
        )


# ---------------------------------------------------------------------------
# Locked skipped-reason set
# ---------------------------------------------------------------------------


def test_skipped_reason_set_is_locked_to_exactly_four_tokens():
    assert STAGE21_4_SKIPPED_REASONS == (
        SKIPPED_REASON_READINESS_NOT_READY,
        SKIPPED_REASON_PROVIDER_FETCH_FAILED,
        SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS,
        SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
    )
    assert len(STAGE21_4_SKIPPED_REASONS) == 4
    assert len(set(STAGE21_4_SKIPPED_REASONS)) == 4


def test_default_max_events_is_one():
    assert DEFAULT_MAX_EVENTS == 1


def test_smoke_label_is_21_4():
    assert STAGE21_4_SMOKE_LABEL == "21.4"


# ---------------------------------------------------------------------------
# Construction-time validation
# ---------------------------------------------------------------------------


def test_construction_rejects_none_provider_adapter():
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=None,  # type: ignore[arg-type]
            transport=transport,
            readiness=readiness,
            recipient="op-1",
        )


def test_construction_rejects_none_transport():
    provider = _FakeProviderAdapter()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=None,  # type: ignore[arg-type]
            readiness=readiness,
            recipient="op-1",
        )


def test_construction_rejects_none_readiness():
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=None,  # type: ignore[arg-type]
            recipient="op-1",
        )


def test_construction_rejects_empty_recipient():
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=readiness,
            recipient="",
        )


def test_construction_rejects_non_str_recipient():
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=readiness,
            recipient=123,  # type: ignore[arg-type]
        )


def test_construction_rejects_zero_max_events():
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=readiness,
            recipient="op-1",
            max_events=0,
        )


def test_construction_rejects_negative_max_events():
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=readiness,
            recipient="op-1",
            max_events=-1,
        )


def test_construction_rejects_bool_max_events():
    # Python ``bool`` is a subclass of ``int``; the runner rejects
    # it explicitly so a stray ``True`` / ``False`` does not
    # silently coerce to ``1`` / ``0``.
    provider = _FakeProviderAdapter()
    transport = _FakeTransport()
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    with pytest.raises(Stage21RunnerError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=transport,
            readiness=readiness,
            recipient="op-1",
            max_events=True,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Readiness short-circuit
# ---------------------------------------------------------------------------


def test_readiness_not_ready_skips_before_provider_fetch():
    # Empty env -> mode_disabled -> readiness ready=False.
    readiness = load_live_readiness_config_from_env({})
    provider = _TripwireProviderAdapter()
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is False
    assert result.sent is False
    assert result.skipped_reason == SKIPPED_REASON_READINESS_NOT_READY
    assert result.transport_reason == ""
    assert result.provider_event_count == 0
    assert result.normalized_event_id == ""
    assert result.recipient == "op-1"
    # The tripwire would have raised if the adapter were called.
    assert provider.invocations == 0
    # Transport was never called either.
    assert transport.calls == []


def test_readiness_not_ready_with_partial_env_also_short_circuits():
    # safe_for_live_dispatch is False -> readiness ready=False.
    env = _fully_ready_env()
    env[ENV_VAR_SAFE_FOR_LIVE_DISPATCH] = "false"
    readiness = load_live_readiness_config_from_env(env)
    provider = _TripwireProviderAdapter()
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.skipped_reason == SKIPPED_REASON_READINESS_NOT_READY
    assert provider.invocations == 0


# ---------------------------------------------------------------------------
# Provider event-count guards
# ---------------------------------------------------------------------------


def test_provider_returns_zero_events_skips_with_locked_reason():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    provider = _FakeProviderAdapter(events=())
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is False
    assert result.sent is False
    assert result.skipped_reason == (
        SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS
    )
    assert result.provider_event_count == 0
    # Provider called exactly once with the requested cap.
    assert len(provider.calls) == 1
    assert provider.calls[0]["max_results"] == 1
    # Transport never called.
    assert transport.calls == []


def test_provider_returns_two_events_fails_closed_does_not_truncate():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    provider = _FakeProviderAdapter(
        events=(
            _make_event(provider_event_id="evt-1", mint="MintForTestsOnly1"),
            _make_event(provider_event_id="evt-2", mint="MintForTestsOnly2"),
        )
    )
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
        max_events=1,
    )
    assert result.attempted is False
    assert result.sent is False
    assert result.skipped_reason == (
        SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY
    )
    assert result.provider_event_count == 2
    # Transport never called -- fail closed instead of truncating.
    assert transport.calls == []


def test_provider_returns_exactly_max_events_is_accepted():
    # ``max_events == 2`` and the adapter returns 2 -- still
    # single-shot send (only ``events[0]`` is forwarded).
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    e1 = _make_event(provider_event_id="evt-1", mint="MintForTestsOnly1")
    e2 = _make_event(provider_event_id="evt-2", mint="MintForTestsOnly2")
    provider = _FakeProviderAdapter(events=(e1, e2))
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
        max_events=2,
    )
    assert result.attempted is True
    assert result.sent is True
    assert result.provider_event_count == 2
    # Forwarded event is the FIRST one.
    assert result.normalized_event_id == e1.event_id
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# Provider exception sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_class, exc_message",
    [
        (RuntimeError, "upstream https://secret.example/webhook key=AKIA1234567890ABCDEFG"),
        (ValueError, "rpc 0xdeadbeefdeadbeef returned bad json"),
        (ConnectionError, "Bearer token aB1234567890abcdefghijKLMNOPqr+/="),
        (TimeoutError, "https://discord.com/api/webhooks/AAAAAAAAAA/zzzzzzzzzzzzzz"),
    ],
)
def test_provider_fetch_raises_is_sanitized(exc_class, exc_message):
    # The adapter exception carries URL / token / API key shapes;
    # none of them must appear anywhere in the result.
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    provider = _FakeProviderAdapter(raise_exception=exc_class(exc_message))
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is False
    assert result.sent is False
    assert result.skipped_reason == SKIPPED_REASON_PROVIDER_FETCH_FAILED
    assert result.provider_event_count == 0
    # Transport never called.
    assert transport.calls == []
    # No leak via repr or any specific field.
    rendered = repr(result)
    for leak_substring in (
        "https://",
        "http://",
        "discord.com",
        "secret.example",
        "AKIA",
        "Bearer",
        "0xdeadbeef",
        "AAAAAAAAAA",
        exc_class.__name__,
    ):
        assert leak_substring not in rendered, (
            f"leaked {leak_substring!r} into runner result repr"
        )


# ---------------------------------------------------------------------------
# Happy path / payload shape
# ---------------------------------------------------------------------------


def test_happy_path_returns_attempted_and_sent_true():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport(
        TransportResult(dispatched=True, rejection_reason="", recipient="op-1")
    )
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is True
    assert result.skipped_reason == ""
    assert result.transport_reason == ""
    assert result.provider_event_count == 1
    assert result.normalized_event_id == event.event_id
    assert result.recipient == "op-1"
    assert len(provider.calls) == 1
    assert len(transport.calls) == 1


def test_transport_payload_carries_locked_marker_and_dispatch_flag():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    sent_payload = transport.calls[0]
    assert sent_payload.private_preview_marker_present is True
    assert sent_payload.safe_for_public_dispatch is False
    assert sent_payload.recipient == "op-1"


def test_transport_body_text_carries_21_4_label_not_21_2_label():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    body = transport.calls[0].body_text
    # The body carries the locked Stage 21.4 smoke marker token,
    # NOT a Stage 21.2 fake-path label.
    assert "21.4" in body
    assert "21.2" not in body
    assert "fake_private_transport" not in body
    # The body carries the safe non-secret event fields.
    assert event.mint in body
    assert event.event_type in body
    assert event.event_id in body
    assert event.observed_at_utc in body


def test_transport_body_text_does_not_carry_signature_or_decoded_fields():
    # The smoke body is deliberately minimal. It does NOT embed
    # the signature (~88-char base58 string) or any decoded_fields
    # / payload_summary content.
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    body = transport.calls[0].body_text
    assert "fake_sig_for_tests_only_abc123" not in body
    # The raw_payload key/value pair must not appear in the body.
    assert "raw_payload" not in body


def test_runner_is_deterministic_over_identical_inputs():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider_a = _FakeProviderAdapter(events=(event,))
    transport_a = _FakeTransport()
    result_a = run_one_private_smoke_ping(
        provider_adapter=provider_a,
        transport=transport_a,
        readiness=readiness,
        recipient="op-1",
    )
    provider_b = _FakeProviderAdapter(events=(event,))
    transport_b = _FakeTransport()
    result_b = run_one_private_smoke_ping(
        provider_adapter=provider_b,
        transport=transport_b,
        readiness=readiness,
        recipient="op-1",
    )
    assert result_a == result_b
    assert transport_a.calls[0].body_text == transport_b.calls[0].body_text


# ---------------------------------------------------------------------------
# Transport refusal pass-through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rejection_reason",
    [
        REJECTION_REASON_READINESS_NOT_READY,
        REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
        REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
        REJECTION_REASON_WEBHOOK_NOT_PRESENT,
        REJECTION_REASON_CLIENT_POST_FAILED,
        REJECTION_REASON_UPSTREAM_NON_2XX,
    ],
)
def test_transport_refusal_surfaces_locked_reason_verbatim(rejection_reason):
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport(
        TransportResult(
            dispatched=False,
            rejection_reason=rejection_reason,
            recipient="op-1",
        )
    )
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is False
    # The runner reached transport.send, so skipped_reason is empty.
    assert result.skipped_reason == ""
    # The transport reason is echoed verbatim.
    assert result.transport_reason == rejection_reason


def test_transport_exception_is_not_caught_by_runner():
    # The Stage 21.3C transport contract is that ``send`` never
    # raises on a refusal. If a transport DOES raise, that is a
    # contract violation worth surfacing to the operator -- the
    # runner does NOT catch it.

    class _BrokenTransport:
        def send(self, payload: TransportPayload) -> TransportResult:
            raise RuntimeError(
                "transport contract violation: send raised instead of "
                "returning a TransportResult"
            )

    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    with pytest.raises(RuntimeError):
        run_one_private_smoke_ping(
            provider_adapter=provider,
            transport=_BrokenTransport(),
            readiness=readiness,
            recipient="op-1",
        )


# ---------------------------------------------------------------------------
# Helius provider_id integration (Stage 21.4 widening)
# ---------------------------------------------------------------------------


def test_helius_provider_id_satisfies_readiness_after_21_4_widening():
    env = _fully_ready_env()
    env[ENV_VAR_PROVIDER_ID] = HELIUS_PROVIDER_ID
    readiness = load_live_readiness_config_from_env(env)
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is True
    assert result.skipped_reason == ""


# ---------------------------------------------------------------------------
# Real Stage 21.3C DiscordPrivateTransport integration (offline client)
# ---------------------------------------------------------------------------


class _OfflineDiscordClient:
    """In-memory ``DiscordWebhookClientProtocol`` implementation.

    Records every ``post_webhook`` call so the integration test
    can assert the runner / transport composition forwarded
    exactly one body and a deterministic idempotency token.
    """

    def __init__(self, accepted: bool = True) -> None:
        self._accepted = accepted
        self.calls: list[dict[str, str]] = []

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        self.calls.append({
            "body_text": body_text,
            "idempotency_token": idempotency_token,
        })
        return DiscordPostOutcome(
            accepted=self._accepted,
            status_class="2xx" if self._accepted else "5xx",
            upstream_error_type="",
        )


def _build_real_discord_transport(
    *,
    client: _OfflineDiscordClient,
    env: dict[str, str],
    allowlist_items: Sequence[str],
) -> DiscordPrivateTransport:
    readiness = load_live_readiness_config_from_env(env)
    return DiscordPrivateTransport(
        client=client,
        readiness=readiness,
        webhook_ref=build_secret_ref(
            ENV_VAR_DISCORD_WEBHOOK_URL,
            env[ENV_VAR_DISCORD_WEBHOOK_URL],
        ),
        allowlist=build_allowlist_from_sequence(allowlist_items),
    )


def test_real_discord_transport_integration_happy_path():
    env = _fully_ready_env()
    readiness = load_live_readiness_config_from_env(env)
    client = _OfflineDiscordClient(accepted=True)
    transport = _build_real_discord_transport(
        client=client,
        env=env,
        allowlist_items=["op-1"],
    )
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is True
    assert result.transport_reason == ""
    # The client received exactly one call carrying the Stage 21.4
    # smoke body and a deterministic idempotency token.
    assert len(client.calls) == 1
    sent_body = client.calls[0]["body_text"]
    assert "21.4" in sent_body
    assert event.mint in sent_body


def test_real_discord_transport_integration_idempotency_token_is_deterministic():
    env = _fully_ready_env()
    readiness = load_live_readiness_config_from_env(env)
    event = _make_event()

    client_a = _OfflineDiscordClient(accepted=True)
    transport_a = _build_real_discord_transport(
        client=client_a,
        env=env,
        allowlist_items=["op-1"],
    )
    run_one_private_smoke_ping(
        provider_adapter=_FakeProviderAdapter(events=(event,)),
        transport=transport_a,
        readiness=readiness,
        recipient="op-1",
    )

    client_b = _OfflineDiscordClient(accepted=True)
    transport_b = _build_real_discord_transport(
        client=client_b,
        env=env,
        allowlist_items=["op-1"],
    )
    run_one_private_smoke_ping(
        provider_adapter=_FakeProviderAdapter(events=(event,)),
        transport=transport_b,
        readiness=readiness,
        recipient="op-1",
    )
    # Same event + same recipient -> same idempotency token.
    assert (
        client_a.calls[0]["idempotency_token"]
        == client_b.calls[0]["idempotency_token"]
    )


def test_real_discord_transport_integration_recipient_not_in_allowlist():
    env = _fully_ready_env()
    readiness = load_live_readiness_config_from_env(env)
    client = _OfflineDiscordClient(accepted=True)
    # ``op-2`` is in the allowlist; the runner asks for ``op-1``.
    transport = _build_real_discord_transport(
        client=client,
        env=env,
        allowlist_items=["op-2"],
    )
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is False
    assert result.transport_reason == (
        REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST
    )
    # The client was never invoked because the allowlist refused
    # before the client call.
    assert client.calls == []


def test_real_discord_transport_integration_upstream_non_2xx():
    env = _fully_ready_env()
    readiness = load_live_readiness_config_from_env(env)
    client = _OfflineDiscordClient(accepted=False)
    transport = _build_real_discord_transport(
        client=client,
        env=env,
        allowlist_items=["op-1"],
    )
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert result.attempted is True
    assert result.sent is False
    assert result.transport_reason == REJECTION_REASON_UPSTREAM_NON_2XX


# ---------------------------------------------------------------------------
# Persistence / leak hygiene
# ---------------------------------------------------------------------------


def test_runner_does_not_persist_anything_to_tmp_path(tmp_path: Path):
    contents_before = sorted(tmp_path.iterdir())
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    contents_after = sorted(tmp_path.iterdir())
    assert contents_before == contents_after


def test_result_repr_does_not_leak_url_or_secret_substrings():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    event = _make_event()
    provider = _FakeProviderAdapter(events=(event,))
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    rendered = repr(result)
    for needle in (
        "https://",
        "http://",
        "discord.com",
        "discordapp.com",
        "api_key",
        "webhook_url",
        "fingerprint",
        "Bearer",
    ):
        assert needle not in rendered


def test_result_namedtuple_is_immutable():
    readiness = load_live_readiness_config_from_env(_fully_ready_env())
    provider = _FakeProviderAdapter(events=(_make_event(),))
    transport = _FakeTransport()
    result = run_one_private_smoke_ping(
        provider_adapter=provider,
        transport=transport,
        readiness=readiness,
        recipient="op-1",
    )
    assert isinstance(result, Stage21PrivateSmokeResult)
    with pytest.raises(AttributeError):
        result.sent = False  # type: ignore[misc]
