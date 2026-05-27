"""Stage 29.6 bounded private single-shot live proof — fake
end-to-end acceptance tests.

These tests prove that the Stage 29.6 ceremony composition works
end-to-end through the already-committed Stage 29.3 mode-3
entrypoint with the already-committed Stage 29.5.5 recorder +
Stage 29.5.5 side-channel writer + Stage 29.5.6 injector wired
through the optional kwargs. Stage 29.6 adds ZERO production .py
file, ZERO orchestrator, ZERO wrapper module; these tests
exercise the existing surfaces verbatim through fakes.

Pins:

  * Stage 29.6 ceremony composition dispatches EXACTLY ONE
    private Discord ping through the fake Stage 28.4 audited
    transport when wired with recorder + writer + injector.
  * The dispatched body carries the Stage 29.5.5 migration
    context (full block when it fits, deterministic compact
    fallback otherwise) as evidenced by the three cross-path
    safety pin lines.
  * The Stage 28.9 / Stage 29.3 / Stage 29.5.5 expected artifact
    inventory exists under the test's scratch output_dir after
    the ceremony.
  * Omitting the Stage 29.5.5 recorder + side-channel writer
    degrades the dispatched body gracefully: dispatch still
    happens, no Stage 29.5.5 block in body, no Stage 29.5.5
    artifact written. The Stage 28.9 dispatch counter remains
    exactly one.
  * Stage 28.9 dispatch cap honored: max_dispatches=1 hardcoded
    by Stage 29.3 mode 3 — even when the fake provider yields
    multiple hint-bearing events, exactly one Discord dispatch
    occurs.
  * No outbound network call: tests use a fake Chainstack
    channel factory, a fake Birdeye HTTP transport, and a fake
    Stage 28.4 audited Discord transport. The Stage 29.6 ceremony
    is wired without instantiating any real gRPC channel, any
    real HTTP client, or any real WebSocket connection.

All test composition mirrors the existing Stage 29.5.6 integration
tests but renamed and re-asserted for Stage 29.6 ceremony scope.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage28.audited_http_transport_models import (
    REDACTION_STATUS_REDACTED as _ST28_4_REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportResult,
    TRANSPORT_STATUS_SENT_OK,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)
from PHX2.stage28.audited_http_transport_models import (
    derive_safe_reason_code as _st28_4_derive_safe_reason_code,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    build_chainstack_yellowstone_config,
)
from PHX2.stage29.pumpswap_program_constants import (
    SPL_TOKEN_PROGRAM_ID,
    WRAPPED_SOL_MINT,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
    Stage29_2BirdeyeRuntimeConfig,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME,
    Stage29_5_5SideChannelArtifactWriter,
)
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    STAGE29_5_6_CONTENT_MAX_CHARS,
    Stage29_5_6PrivateDiscordBodyInjector,
)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------


_TEST_BASE_MINT: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_POOL_OWNER: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_POOL_PROGRAM_ID: str = (
    "PoolProgramIDDDDDDD22222222222222222222222D"
)
_TEST_QUOTE_MINT: str = (
    "QuoteMintEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
)
_TEST_PROVIDER_ID: str = "stage29_6_test_provider"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_stage29_6"
_TEST_BIRDEYE_API_KEY: str = "test_birdeye_key_stage29_6"
_TEST_BIRDEYE_BASE_URL: str = "https://public-api.test.local"
# The webhook URL is a synthetic test value matching the shape of
# a Discord webhook URL the Stage 28.4 shape validator accepts.
# The fake Stage 28.4 audited Discord transport never opens a
# network connection.
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://" + "discord" + ".com/api/webhooks/"
    "123456789012345678/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
_TEST_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_TEST_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fake transports + channel infrastructure (mirrors Stage 29.5.6
# integration test patterns)
# ---------------------------------------------------------------------------


class _FakeStreamCallable:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses

    def __call__(
        self, request_iterator, timeout=None, metadata=None,
    ):
        for _ in request_iterator:
            pass
        return _FakeResponseIter(self._responses)


class _FakeResponseIter:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.cancel_called = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._idx >= len(self._responses):
            raise StopIteration
        item = self._responses[self._idx]
        self._idx += 1
        return item

    def cancel(self):
        self.cancel_called = True


class _FakeUnusedCallable:
    def __init__(self, method: str) -> None:
        self._method = method

    def __call__(self, *args, **kwargs):
        raise AssertionError(
            f"Stage 29.6 ceremony fake must not invoke "
            f"{self._method!r}"
        )


class _FakeChannel:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.close_called = False

    def stream_stream(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ):
        if method.endswith("/Subscribe"):
            return _FakeStreamCallable(self._responses)
        return _FakeUnusedCallable(method)

    def unary_unary(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def stream_unary(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def unary_stream(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def close(self):
        self.close_called = True


def _make_factory(responses):
    captured: dict = {}

    def factory(target, credentials):
        captured["target"] = target
        captured["credentials"] = credentials
        ch = _FakeChannel(responses)
        captured["channel"] = ch
        return ch

    return factory, captured


def _make_pumpswap_tx_update() -> "_geyser_pb2.SubscribeUpdate":
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(
        range(1, 65),
    )
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000

    def _add(account_index, mint, owner):
        meta = update.transaction.transaction.meta
        pre = meta.pre_token_balances.add()
        pre.account_index = account_index
        pre.mint = mint
        pre.owner = owner
        pre.program_id = SPL_TOKEN_PROGRAM_ID
        post = meta.post_token_balances.add()
        post.account_index = account_index
        post.mint = mint
        post.owner = owner
        post.program_id = SPL_TOKEN_PROGRAM_ID

    _add(0, WRAPPED_SOL_MINT, _TEST_POOL_OWNER)
    _add(1, _TEST_BASE_MINT, _TEST_POOL_OWNER)
    return update


class _FakeBirdeyeHttpTransport:
    def __init__(
        self,
        *,
        bodies_by_path: Mapping[str, Optional[dict]],
    ) -> None:
        self._bodies_by_path = dict(bodies_by_path)
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            {
                "path": path,
                "query_params": dict(query_params),
                "timeout_seconds": timeout_seconds,
            }
        )
        body = self._bodies_by_path.get(path)
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body if body is not None else None,
            fetched_at_utc=datetime.now(
                timezone.utc,
            ).isoformat(),
        )


def _build_sent_ok_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_SENT_OK,
        ok=True,
        http_status_code=204,
        retry_after_seconds=None,
        send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        redaction_status=_ST28_4_REDACTION_STATUS_REDACTED,
        safe_reason_code=_st28_4_derive_safe_reason_code(
            TRANSPORT_STATUS_SENT_OK,
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


class _FakeAuditedDiscordTransport:
    """Stage 28.4-shaped fake audited HTTP transport.

    Captures every send_one_audited_post call in memory; never
    opens a network connection. Returns a scripted Stage 28.4
    SENT_OK result. Used as the ``audited_discord_transport``
    kwarg on the Stage 29.3 entrypoint so the realistic Stage
    28.9 transport stack runs against this fake instead of
    Stage 28.4's real urllib-based transport.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_one_audited_post(
        self,
        *,
        webhook_url: str,
        webhook_identity: str,
        payload,
    ) -> Stage28_4TransportResult:
        self.calls.append(
            {
                "webhook_url": webhook_url,
                "webhook_identity": webhook_identity,
                "payload": (
                    dict(payload)
                    if isinstance(payload, dict)
                    else {}
                ),
            }
        )
        return _build_sent_ok_result()

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _build_test_runtime_configs() -> Stage29_3RuntimeConfigBundle:
    cs_safe = build_chainstack_yellowstone_config(
        provider_id=_TEST_PROVIDER_ID,
        endpoint_safe_label="yellowstone_stage29_6_test",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    cs_secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=_TEST_ENDPOINT,
        x_token=_TEST_X_TOKEN,
        tls=True,
    )
    cs_config = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=cs_safe,
        endpoint_secret=cs_secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )
    birdeye_secret = Stage29_2BirdeyeEndpointSecret(
        _api_key=_TEST_BIRDEYE_API_KEY,
        _base_url=_TEST_BIRDEYE_BASE_URL,
    )
    birdeye_config = Stage29_2BirdeyeRuntimeConfig(
        endpoint_secret=birdeye_secret,
        timeout_seconds=10,
        live_flag_set=True,
    )
    return Stage29_3RuntimeConfigBundle(
        chainstack=cs_config, birdeye=birdeye_config,
    )


def _outside_repo_tmpdir() -> Path:
    return Path(
        tempfile.mkdtemp(prefix="phx2_stage29_6_proof_"),
    )


def _build_birdeye_bodies() -> Mapping[str, dict]:
    return {
        "/defi/price": {
            "data": {
                "value": 0.000036,
                "updateUnixTime": 1779678781,
            },
        },
        "/defi/ohlcv": {
            "data": {
                "items": [
                    {"h": 0.000054, "unixTime": 1779592200},
                ],
            },
        },
    }


def _evidence_for(token_mint: str) -> tuple[
    Stage29_5MigrationEvidenceRecord, ...
]:
    return (
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=token_mint,
            pool_account=_TEST_POOL_OWNER,
            pool_program_id=_TEST_POOL_PROGRAM_ID,
            quote_mint=_TEST_QUOTE_MINT,
            migration_timestamp_utc=_TEST_MIGRATION_TS,
            migration_slot=12345,
            migration_signature="Sig" + "X" * 60,
            observed_at_utc=_TEST_OBSERVED_AT,
            source_event_ref="evt-stage29-6-001",
        ),
    )


def _ath_context_for(token_mint: str) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
        pair_type="SOL_PAIR",
        quote_asset="SOL",
        ath_value="123.45",
        ath_unit="SOL",
        ath_source="birdeye",
        ath_observed_at_utc="2026-01-01T00:01:00+00:00",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        drawdown_from_ath="0.1",
        drawdown_unit="ratio",
        drawdown_basis="last_price",
        ath_status="PRESENT",
        ath_reason="OK",
        schema_version="stage27_4_v0_ath_context",
    )


def _build_recorder() -> Stage29_5_5MigrationContextRecorder:
    return Stage29_5_5MigrationContextRecorder(
        evidence_provider=_evidence_for,
        ath_context_provider=_ath_context_for,
        clock=lambda: _TEST_OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )


# ---------------------------------------------------------------------------
# Expected Stage 29.6 acceptance artifact basenames (pinned)
# ---------------------------------------------------------------------------


_STAGE_28_9_EXPECTED_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage28_9_dispatch_ledger.jsonl",
    "stage28_9_heartbeat.jsonl",
    "stage28_9_health_snapshot.json",
    "stage28_9_final_run_summary.json",
)


_STAGE_29_3_EXPECTED_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage29_3_tradeable_smoke_result.json",
    "stage29_3_extracted_hints.json",
    "stage29_3_birdeye_evidence.json",
    "stage29_3_redaction_scan.json",
)


# ---------------------------------------------------------------------------
# Stage 29.6 ceremony — full wiring with recorder + writer + injector
# ---------------------------------------------------------------------------


def test_stage_29_6_ceremony_dispatches_exactly_once_with_migration_context() -> None:
    """Stage 29.6 fake end-to-end acceptance proof.

    Composes the existing Stage 29.3 mode-3 entrypoint with the
    Stage 29.5.5 recorder + Stage 29.5.5 side-channel writer +
    Stage 29.5.6 injector wired through the three optional
    kwargs. Asserts:

      * Stage 29.3 ``tradeable_smoke_outcome == DISPATCHED``.
      * Exactly one fake-captured Discord dispatch (Stage 28.9
        ``max_dispatches=1`` honored).
      * Stage 28.9 header present in dispatched body.
      * Stage 29.5.5 migration context visible in dispatched
        body via the three cross-path safety pin lines.
      * Dispatched body stays within the 1900-char combined cap.
      * Stage 29.5.5 recorder captured at least one entry.
      * filter_enforcement_status remains NOT_ACTIVE_STAGE_29_PENDING.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    writer = Stage29_5_5SideChannelArtifactWriter()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        migration_context_renderer=writer,
        private_discord_body_injector=injector,
    )

    # Stage 29.3 mode-3 outcome: DISPATCHED.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    ), (
        f"Stage 29.6 ceremony expected DISPATCHED; got "
        f"{result.tradeable_smoke_outcome!r}"
    )

    # Exactly one fake-captured Discord dispatch (Stage 28.9
    # max_dispatches=1 honored end-to-end).
    assert fake_discord.call_count == 1, (
        f"Stage 29.6 ceremony expected exactly 1 Discord "
        f"dispatch; got {fake_discord.call_count}"
    )

    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )

    # Stage 28.9 header preserved.
    assert (
        "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
        in dispatched_content
    )

    # Stage 29.5.5 migration context visible via cross-path
    # safety pin lines (full or compact fallback).
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched_content
    ), (
        "Stage 29.6 ceremony must produce a dispatched body "
        "carrying the Stage 29.5.5 migration context (full or "
        "compact)"
    )
    assert "informational_only: true" in dispatched_content
    assert "not_a_trading_verdict: true" in dispatched_content

    # Dispatched body stays within Stage 29.5.6 combined cap.
    assert len(dispatched_content) <= (
        STAGE29_5_6_CONTENT_MAX_CHARS
    )

    # The Stage 29.5.5 recorder captured at least one entry
    # (Stage 27.6 candidate assembly called the recorder).
    entries = recorder.recorded_entries
    assert len(entries) >= 1, (
        "Stage 29.5.5 recorder must capture at least one entry "
        "during the Stage 29.6 ceremony"
    )

    # filter_enforcement_status pin preserved on the Stage 29.3
    # smoke result.
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# Stage 29.6 expected artifact inventory pin
# ---------------------------------------------------------------------------


def test_stage_29_6_ceremony_writes_expected_artifacts() -> None:
    """After a successful Stage 29.6 ceremony, the expected
    Stage 28.9 + Stage 29.3 + Stage 29.5.5 acceptance artifacts
    exist under the test's scratch ``output_dir``.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    writer = Stage29_5_5SideChannelArtifactWriter()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        migration_context_renderer=writer,
        private_discord_body_injector=injector,
    )

    # Stage 28.9 artifacts (4 expected).
    for basename in _STAGE_28_9_EXPECTED_ARTIFACT_BASENAMES:
        path = out / basename
        assert path.exists(), (
            f"Stage 29.6 ceremony expected Stage 28.9 artifact "
            f"{basename!r} under output_dir"
        )

    # Stage 29.3 artifacts (4 expected).
    for basename in _STAGE_29_3_EXPECTED_ARTIFACT_BASENAMES:
        path = out / basename
        assert path.exists(), (
            f"Stage 29.6 ceremony expected Stage 29.3 artifact "
            f"{basename!r} under output_dir"
        )

    # Stage 29.5.5 side-channel artifact.
    side_channel_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert side_channel_path.exists(), (
        f"Stage 29.6 ceremony expected Stage 29.5.5 side-"
        f"channel artifact "
        f"{STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME!r} "
        f"under output_dir"
    )

    # Side-channel artifact carries at least one entry.
    bundle = json.loads(
        side_channel_path.read_text(encoding="utf-8"),
    )
    assert bundle["entry_count"] >= 1, (
        "Stage 29.5.5 side-channel artifact must carry at "
        "least one entry after a successful Stage 29.6 "
        "ceremony"
    )


# ---------------------------------------------------------------------------
# Stage 29.6 missing-context degrades gracefully
# ---------------------------------------------------------------------------


def test_stage_29_6_ceremony_without_migration_context_degrades_safely() -> None:
    """When the operator omits the Stage 29.5.5 recorder + side-
    channel writer + Stage 29.5.6 injector (default Stage 29.3
    mode-3 invocation), the Stage 29.6 ceremony still dispatches
    exactly one private ping; the dispatched body does NOT
    carry the Stage 29.5.5 migration context block (no recorder
    wired); and the Stage 29.5.5 side-channel artifact is NOT
    written (no writer wired).

    This is the graceful-degradation pin: Stage 29.6 ceremony
    composition is non-fatal when the optional migration-context
    surfaces are absent. Stage 28.9 dispatch counter remains
    exactly one.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        # No migration_source / migration_context_renderer /
        # private_discord_body_injector kwargs supplied — the
        # default Stage 29.3 mode-3 path runs without any Stage
        # 29.5.X wiring.
    )

    # Stage 29.3 mode-3 still dispatches.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )

    # Exactly one Discord dispatch.
    assert fake_discord.call_count == 1

    # Dispatched body carries the Stage 28.9 header but NOT the
    # Stage 29.5.5 block (no recorder wired).
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    assert (
        "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
        in dispatched_content
    )
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )
    assert "[MIGRATION CONTEXT]" not in dispatched_content

    # Stage 29.5.5 side-channel artifact is NOT written (no
    # writer wired).
    side_channel_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert not side_channel_path.exists(), (
        "Stage 29.6 graceful-degradation: side-channel "
        "artifact must not be written when no writer is wired"
    )

    # Stage 28.9 + Stage 29.3 base artifacts still present
    # (dispatch path runs to completion regardless of migration-
    # context wiring).
    for basename in _STAGE_28_9_EXPECTED_ARTIFACT_BASENAMES:
        path = out / basename
        assert path.exists(), (
            f"Stage 29.6 graceful-degradation: Stage 28.9 "
            f"artifact {basename!r} must still be written"
        )
    for basename in _STAGE_29_3_EXPECTED_ARTIFACT_BASENAMES:
        path = out / basename
        assert path.exists(), (
            f"Stage 29.6 graceful-degradation: Stage 29.3 "
            f"artifact {basename!r} must still be written"
        )


# ---------------------------------------------------------------------------
# Stage 29.6 bounded dispatch cap (max_dispatches=1 honored)
# ---------------------------------------------------------------------------


def test_stage_29_6_ceremony_honors_bounded_max_dispatches_cap() -> None:
    """Even when the fake provider yields multiple hint-bearing
    transactions, Stage 29.3 mode-3 dispatches EXACTLY ONE
    private Discord ping (the Stage 28.9 ``max_dispatches=1``
    cap is honored end-to-end).
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    # Provider yields THREE hint-bearing transactions. Stage 28.9
    # max_events / max_dispatches caps must throttle dispatch
    # down to exactly one.
    factory, _captured = _make_factory(
        responses=[
            _make_pumpswap_tx_update(),
            _make_pumpswap_tx_update(),
            _make_pumpswap_tx_update(),
        ],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        private_discord_body_injector=injector,
    )

    # Exactly one Discord dispatch even though provider yielded
    # three hint-bearing events.
    assert fake_discord.call_count == 1, (
        f"Stage 29.6 bounded-cap pin: expected exactly 1 "
        f"Discord dispatch from 3 yielded events; got "
        f"{fake_discord.call_count}"
    )
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )


# ---------------------------------------------------------------------------
# Stage 29.6 outbound-network discipline pin
# ---------------------------------------------------------------------------


def test_stage_29_6_test_module_imports_no_network_library() -> None:
    """Stage 29.6 fake tests must not import any outbound-
    network library. We assert this by reading the test
    module's own source.

    Each forbidden token is built from string concatenation so
    this test's source body does not itself carry the literal
    substring (the self-scan would otherwise trip on its own
    declarative tuple).
    """
    this_path = Path(__file__).resolve()
    source = this_path.read_text(encoding="utf-8")
    forbidden_imports: tuple[str, ...] = (
        "import " + "urllib",
        "import " + "http.client",
        "import " + "socket",
        "import " + "websocket",
        "import " + "websockets",
        "import " + "aiohttp",
        "import " + "requests",
        "import " + "httpx",
    )
    for forbidden_import in forbidden_imports:
        assert forbidden_import not in source, (
            f"Stage 29.6 test module must not import outbound "
            f"network library {forbidden_import!r}"
        )


def test_stage_29_6_ceremony_uses_only_fake_transports() -> None:
    """Stage 29.6 ceremony test composes ONLY fake transports.
    Verify the four key fake classes are present in this test
    module's source.
    """
    this_path = Path(__file__).resolve()
    source = this_path.read_text(encoding="utf-8")
    for fake_marker in (
        "_FakeAuditedDiscordTransport",
        "_FakeBirdeyeHttpTransport",
        "_FakeChannel",
        "_FakeStreamCallable",
    ):
        assert fake_marker in source, (
            f"Stage 29.6 test module must define fake "
            f"transport class {fake_marker!r}"
        )


# ---------------------------------------------------------------------------
# Stage 29.6 dispatched-body forbidden-substring pin
# ---------------------------------------------------------------------------


_FORBIDDEN_DISPATCHED_BODY_SUBSTRINGS: tuple[str, ...] = (
    # URL host literals must never appear in the dispatched body.
    "h" + "ttps://api.helius",
    "h" + "ttps://rpc.helius",
    "h" + "ttps://mainnet.helius",
    "h" + "ttps://public-api.birdeye",
    "h" + "ttps://pro-api.birdeye",
    "w" + "ss://yellowstone",
    "w" + "s://yellowstone",
    # Auth header literals.
    "B" + "earer ",
    "A" + "uthorization:",
    "X-API-K" + "EY:",
    # API-key-shape prefixes.
    "s" + "k-live-",
    "s" + "k-test-",
    # Wallet / signer prefixes.
    "p" + "rivate_key",
    "s" + "ecret_key",
    "s" + "eed_phrase",
    "m" + "nemonic",
    # Trading-verdict tokens.
    "buy" + "_signal",
    "sell" + "_signal",
    "auto" + "_trade",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_DISPATCHED_BODY_SUBSTRINGS,
)
def test_stage_29_6_dispatched_body_carries_no_forbidden_substring(
    needle: str,
) -> None:
    """The Stage 29.6 ceremony's dispatched body must carry no
    URL host literal, no auth header literal, no API-key
    prefix, no wallet / signer literal, and no trading-verdict
    token.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        private_discord_body_injector=injector,
    )

    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    assert needle not in dispatched_content, (
        f"Stage 29.6 dispatched body must not carry forbidden "
        f"substring {needle!r}"
    )
