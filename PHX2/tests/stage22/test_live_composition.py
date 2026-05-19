"""Stage 22.5 live composition tests (offline, deterministic).

Covers the live-composition helpers and adapter without any
network call, env read, or real Stage 21.3C transport. Stage 21
exception classes are imported directly so the decode
classifier mapping can be pinned end-to-end.

The Stage 21.3C ``DiscordPrivateTransport`` is exercised via a
constructed instance with a fake injected webhook client; the
adapter wraps that transport and the test asserts:

  * the locked safe-field projection (no URL / API / RPC /
    webhook / raw payload / secret substring);
  * the body length cap;
  * the private-only marker (``safe_for_public_dispatch=False``,
    ``private_preview_marker_present=True``).
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage21.allowlist import OperatorAllowlist
from PHX2.stage21.discord_private_transport import (
    DiscordPostOutcome,
    DiscordPrivateTransport,
)
from PHX2.stage21.live_secrets_boundary import (
    ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
    ENV_VAR_LIVE_SMOKE_MODE,
    ENV_VAR_PROVIDER_ID,
    ENV_VAR_SAFE_FOR_LIVE_DISPATCH,
    HELIUS_PROVIDER_ID,
    LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    LIVE_SMOKE_MODE_TOKEN,
    Stage21LiveReadinessConfig,
    load_live_readiness_config_from_env,
)
from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadFieldTypeError,
    ProviderPayloadFieldValueError,
    ProviderPayloadShapeError,
    ProviderPayloadSuspiciousContentError,
    ProviderPayloadUnsupportedInstructionError,
)
from PHX2.stage21.secret_redaction import SecretRef

from PHX2.stage22.constants import (
    MALFORMED_REASON_FIELD_TYPE_ERROR,
    MALFORMED_REASON_FIELD_VALUE_ERROR,
    MALFORMED_REASON_SHAPE_ERROR,
    MALFORMED_REASON_SUSPICIOUS_CONTENT,
    MALFORMED_REASON_UNEXPECTED_ERROR,
    MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
    STAGE22_PRIVATE_PING_BODY_MAX_LEN,
)
from PHX2.stage22.errors import Stage22RunnerError
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    IngestEventKey,
    NormalizedLiveEvent,
    Stage22DispatchOutcome,
)
from PHX2.stage22.live_composition import (
    Stage22DiscordPrivateTransportAdapter,
    build_private_ping_body,
    classify_stage21_decode_exception,
    get_stage21_decode_fn,
)


_CHAIN: str = "solana_mainnet"


def _make_envelope(
    *,
    event_id: str = "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
    provider_event_id: str = "prov-123",
    raw_event_hash: str = "0" * 64,
    mint: str = "mint_AbCdEf",
    slot: int = 1234,
    event_type: str = "fake_swap",
) -> IngestEventEnvelope:
    event = NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain=_CHAIN,
        mint=mint,
        event_type=event_type,
        observed_at_utc="2026-05-19T00:00:00Z",
        slot=slot,
        signature="sig_xyz",
        raw_event_hash=raw_event_hash,
        normalized_schema_version="stage21_v0_normalized_event",
        payload_summary={},
    )
    key = IngestEventKey(
        provider_id=HELIUS_PROVIDER_ID,
        chain=_CHAIN,
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )
    return IngestEventEnvelope(
        event=event,
        ingest_key=key,
        received_at_utc="2026-05-19T00:00:01Z",
        provider_attempt_index=0,
    )


# ---------------------------------------------------------------------------
# classify_stage21_decode_exception mapping
# ---------------------------------------------------------------------------


def test_classify_stage21_decode_shape_error():
    assert classify_stage21_decode_exception(
        ProviderPayloadShapeError("x")
    ) == MALFORMED_REASON_SHAPE_ERROR


def test_classify_stage21_decode_field_type_error():
    assert classify_stage21_decode_exception(
        ProviderPayloadFieldTypeError("x")
    ) == MALFORMED_REASON_FIELD_TYPE_ERROR


def test_classify_stage21_decode_field_value_error():
    assert classify_stage21_decode_exception(
        ProviderPayloadFieldValueError("x")
    ) == MALFORMED_REASON_FIELD_VALUE_ERROR


def test_classify_stage21_decode_unsupported_instruction():
    assert classify_stage21_decode_exception(
        ProviderPayloadUnsupportedInstructionError("x")
    ) == MALFORMED_REASON_UNSUPPORTED_INSTRUCTION


def test_classify_stage21_decode_suspicious_content():
    assert classify_stage21_decode_exception(
        ProviderPayloadSuspiciousContentError("x")
    ) == MALFORMED_REASON_SUSPICIOUS_CONTENT


def test_classify_stage21_decode_unknown_exception_falls_back():
    class _Other(Exception):
        pass

    assert classify_stage21_decode_exception(
        _Other("x")
    ) == MALFORMED_REASON_UNEXPECTED_ERROR


# ---------------------------------------------------------------------------
# build_private_ping_body
# ---------------------------------------------------------------------------


def test_private_ping_body_includes_only_approved_fields():
    envelope = _make_envelope(
        event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa",
        provider_event_id="prov-xyz-001",
        mint="mint_AbCd",
        slot=4242,
        event_type="fake_swap",
    )
    body = build_private_ping_body(envelope=envelope)
    # Approved fields appear.
    assert "provider=" + HELIUS_PROVIDER_ID in body
    assert "chain=" + _CHAIN in body
    assert "event_type=fake_swap" in body
    assert "mint=mint_AbCd" in body
    assert "slot=4242" in body
    assert "event_id=evt_aaaaaaaaaaaaaaaaaaaaaaaa" in body
    # The forbidden fields MUST NOT appear in the body.
    assert "prov-xyz-001" not in body
    assert "sig_xyz" not in body
    assert "raw_event_hash" not in body
    assert "payload_summary" not in body
    assert "observed_at_utc" not in body


def test_private_ping_body_has_no_url_or_secret_substring():
    envelope = _make_envelope()
    body = build_private_ping_body(envelope=envelope)
    # Defense-in-depth: the body must not contain forbidden URL
    # / webhook / secret substrings.
    forbidden = (
        "http" + ":" + "//",
        "https" + ":" + "//",
        "ws" + ":" + "//",
        "wss" + ":" + "//",
        "discord" + "." + "com",
        "discordapp" + "." + "com",
        "hooks" + ".slack" + "." + "com",
        "api_key",
        "webhook",
        "rpc_url",
        "secret",
        "credential",
        "password",
        "bearer",
        "authorization",
    )
    lower = body.lower()
    for needle in forbidden:
        assert needle not in lower, (
            f"private ping body contains forbidden substring {needle!r}"
        )


def test_private_ping_body_length_cap_enforced():
    """A pathological mint/event_type that pushes the body over
    the locked cap must raise Stage22RunnerError.
    """
    # 600 chars of `m` is well over the 384-char cap.
    long_mint = "m" * 600
    envelope = _make_envelope(mint=long_mint)
    with pytest.raises(Stage22RunnerError):
        build_private_ping_body(envelope=envelope)


def test_private_ping_body_unsafe_substring_raises_runner_error():
    """A mint that injects a webhook host substring must be
    rejected -- the renderer never silently truncates unsafe
    bodies.
    """
    envelope = _make_envelope(mint="webhook_evil")
    with pytest.raises(Stage22RunnerError):
        build_private_ping_body(envelope=envelope)


def test_private_ping_body_url_substring_raises_runner_error():
    envelope = _make_envelope(
        event_type="fake_swap_" + "ht" + "tp" + ":" + "//evil"
    )
    with pytest.raises(Stage22RunnerError):
        build_private_ping_body(envelope=envelope)


def test_private_ping_body_under_max_len():
    envelope = _make_envelope()
    body = build_private_ping_body(envelope=envelope)
    assert len(body) <= STAGE22_PRIVATE_PING_BODY_MAX_LEN


def test_private_ping_body_rejects_none_envelope():
    with pytest.raises(Stage22RunnerError):
        build_private_ping_body(envelope=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stage22DiscordPrivateTransportAdapter
# ---------------------------------------------------------------------------


def _readiness_ready() -> Stage21LiveReadinessConfig:
    """Build a Stage21LiveReadinessConfig that passes
    evaluate_live_readiness in offline tests.

    The Stage 21.1 ``Stage21Config`` requires its own positive
    fields. The simplest path: feed an env mapping that turns
    every gate True, then run the Stage 21 loader.
    """
    env = {
        "PHX2_STAGE21_PROVIDER_MODE": "live",
        "PHX2_STAGE21_SINK_MODE": "private_preview",
        "PHX2_STAGE21_LIVE_PRIVATE": "true",
        "PHX2_STAGE21_DRY_RUN": "false",
        "PHX2_STAGE21_PROVIDER_API_KEY": "test-api-key-xxxxxxxxxxxxxxxx",
        "PHX2_STAGE21_PROVIDER_RPC_URL": "test-rpc-url-xxxxxxxxxxxxxxxx",
        "PHX2_STAGE21_DISCORD_WEBHOOK_URL": "test-webhook-xxxxxxxxxxxxxxxx",
        "PHX2_STAGE21_ALLOWLIST_OPERATOR_IDS": "op1,op2",
        "PHX2_STAGE21_MAX_EVENTS_PER_RUN": "1",
        ENV_VAR_LIVE_SMOKE_MODE: LIVE_SMOKE_MODE_TOKEN,
        ENV_VAR_PROVIDER_ID: HELIUS_PROVIDER_ID,
        ENV_VAR_SAFE_FOR_LIVE_DISPATCH: "true",
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: (
            LIVE_SAFETY_ACKNOWLEDGEMENT_V1
        ),
    }
    return load_live_readiness_config_from_env(env)


class _AcceptingWebhookClient:
    """Stage 21.3C webhook client fake that accepts every post."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        self.calls.append((body_text, idempotency_token))
        return DiscordPostOutcome(
            accepted=True,
            status_class="2xx",
            upstream_error_type="",
        )


class _RefusingWebhookClient:
    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome:
        return DiscordPostOutcome(
            accepted=False,
            status_class="5xx",
            upstream_error_type="server_error",
        )


def _build_discord_transport(
    *,
    client,
) -> DiscordPrivateTransport:
    readiness = _readiness_ready()
    webhook_ref = SecretRef(
        name="PHX2_STAGE21_DISCORD_WEBHOOK_URL",
        present=True,
        length=29,
        fingerprint="aaaaaaaaaaaa",
    )
    allowlist = OperatorAllowlist(
        recipients=("op1", "op2"),
        fail_closed=False,
    )
    return DiscordPrivateTransport(
        client=client,
        readiness=readiness,
        webhook_ref=webhook_ref,
        allowlist=allowlist,
    )


def test_adapter_dispatched_outcome_on_accepting_client():
    client = _AcceptingWebhookClient()
    transport = _build_discord_transport(client=client)
    adapter = Stage22DiscordPrivateTransportAdapter(
        transport=transport,
        recipient="op1",
    )
    envelope = _make_envelope()
    outcome = adapter.dispatch(envelope=envelope)
    assert outcome.dispatched is True
    assert outcome.rejection_reason == ""
    # The accepting client recorded exactly one call.
    assert len(client.calls) == 1
    body_text, _ = client.calls[0]
    assert body_text.startswith("[Stage 22.5 private-preview ingest]")


def test_adapter_refused_outcome_on_refusing_upstream():
    client = _RefusingWebhookClient()
    transport = _build_discord_transport(client=client)
    adapter = Stage22DiscordPrivateTransportAdapter(
        transport=transport,
        recipient="op1",
    )
    envelope = _make_envelope()
    outcome = adapter.dispatch(envelope=envelope)
    assert outcome.dispatched is False
    assert outcome.rejection_reason == "upstream_non_2xx"


def test_adapter_refused_when_recipient_not_in_allowlist():
    client = _AcceptingWebhookClient()
    transport = _build_discord_transport(client=client)
    adapter = Stage22DiscordPrivateTransportAdapter(
        transport=transport,
        recipient="op-not-allowed",
    )
    envelope = _make_envelope()
    outcome = adapter.dispatch(envelope=envelope)
    assert outcome.dispatched is False
    assert outcome.rejection_reason == "recipient_not_in_allowlist"


def test_adapter_rejects_none_transport():
    with pytest.raises(Stage22RunnerError):
        Stage22DiscordPrivateTransportAdapter(
            transport=None,  # type: ignore[arg-type]
            recipient="op1",
        )


def test_adapter_rejects_empty_recipient():
    client = _AcceptingWebhookClient()
    transport = _build_discord_transport(client=client)
    with pytest.raises(Stage22RunnerError):
        Stage22DiscordPrivateTransportAdapter(
            transport=transport,
            recipient="",
        )


# ---------------------------------------------------------------------------
# get_stage21_decode_fn passthrough
# ---------------------------------------------------------------------------


def test_get_stage21_decode_fn_returns_stage21_decoder():
    from PHX2.stage21.provider_event_decoder import decode_provider_event

    assert get_stage21_decode_fn() is decode_provider_event
