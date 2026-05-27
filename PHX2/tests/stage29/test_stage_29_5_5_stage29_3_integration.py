"""Stage 29.5.5 Stage 29.3 mode-3 integration pins.

End-to-end controlled offline test that:

  * Wires a Stage 29.5.5 recorder + renderer + side-channel
    writer into ``run_stage29_3_first_private_tradeable_smoke``
    via the new ``migration_context_renderer`` kwarg.
  * Drives the Stage 29.3 mode-3 ceremony through fake
    Chainstack gRPC + fake Birdeye HTTP + fake audited Discord
    transports.
  * Asserts the recorder's ``read_migration_snapshot`` is
    consulted at least once during Stage 27.6 candidate
    assembly when the recorder is wired as ``migration_source``.
  * Asserts the side-channel artifact file is written under
    ``output_dir`` with the canonical filename when the writer
    is wired as ``migration_context_renderer``.
  * Asserts the dispatched-Discord count remains exactly one
    regardless of whether the renderer / writer is wired.
  * Asserts the smoke result's ``filter_enforcement_status``
    remains ``NOT_ACTIVE_STAGE_29_PENDING`` when the renderer
    / writer is wired.

No live network. No real WebSocket / gRPC / HTTP. No real
Discord webhook.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

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
_TEST_PROVIDER_ID: str = "chainstack_yellowstone_test"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_abc1234567890"
_TEST_BIRDEYE_API_KEY: str = (
    "test_birdeye_api_key_abc1234567890"
)
_TEST_BIRDEYE_BASE_URL: str = "https://public-api.test.local"
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
_TEST_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_TEST_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fake gRPC channel (mirrors Stage 29.5.4 integration fakes)
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
            f"Stage 29.3 source must not invoke "
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


# ---------------------------------------------------------------------------
# Fake Birdeye HTTP transport
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fake audited Discord transport
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Runtime-config helper
# ---------------------------------------------------------------------------


def _build_test_runtime_configs() -> Stage29_3RuntimeConfigBundle:
    cs_safe = build_chainstack_yellowstone_config(
        provider_id=_TEST_PROVIDER_ID,
        endpoint_safe_label="yellowstone_test_endpoint",
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
        tempfile.mkdtemp(prefix="phx2_stage29_5_5_test_"),
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


# ---------------------------------------------------------------------------
# Stage 29.5.5 recorder + writer factories
# ---------------------------------------------------------------------------


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
            source_event_ref="evt-001",
        ),
    )


def _ath_context_for(
    token_mint: str,
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
        pair_type="SOL_PAIR",
        quote_asset="SOL",
        ath_value="123.45",
        ath_unit="SOL",
        ath_source="birdeye",
        ath_observed_at_utc=(
            "2026-01-01T00:01:00+00:00"
        ),
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


def _build_writer() -> Stage29_5_5SideChannelArtifactWriter:
    return Stage29_5_5SideChannelArtifactWriter()


# ---------------------------------------------------------------------------
# 1. Recorder + writer wired: side-channel artifact is written, smoke
# result is DISPATCHED, dispatched-Discord count is exactly one.
# ---------------------------------------------------------------------------


def test_recorder_plus_writer_wired_writes_side_channel_artifact() -> None:
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
    writer = _build_writer()

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
    )

    # Side-channel artifact should be written.
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert artifact_path.exists(), (
        "Stage 29.5.5 side-channel artifact must be written "
        "when recorder + writer are wired"
    )
    bundle = json.loads(
        artifact_path.read_text(encoding="utf-8"),
    )
    assert bundle["entry_count"] >= 1
    assert bundle["informational_only"] is True
    assert bundle["not_a_trading_verdict"] is True

    # Recorder consulted at least once during candidate
    # assembly; one recorded entry materialized.
    assert len(recorder.recorded_entries) >= 1

    # Stage 29.3 mode-3 still DISPATCHED exactly once.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


def test_recorder_plus_writer_preserves_filter_enforcement_status() -> None:
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
    writer = _build_writer()

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
    )

    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# 2. Recorder wired but no writer: NO side-channel artifact, recorder
# still records, dispatched count still 1.
# ---------------------------------------------------------------------------


def test_recorder_wired_without_writer_writes_no_artifact() -> None:
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
        # migration_context_renderer omitted (None)
    )

    # No side-channel artifact (because no writer wired).
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert not artifact_path.exists()

    # Recorder still records in memory.
    assert len(recorder.recorded_entries) >= 1

    # Dispatch unchanged.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# 3. Writer wired but no recorder (operator passed default migration
# source = None): writer no-ops because migration_source is None.
# ---------------------------------------------------------------------------


def test_writer_wired_without_recorder_noops_safely() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    writer = _build_writer()

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
        # migration_source omitted (None) -> default fallback
        migration_context_renderer=writer,
    )

    # Writer no-ops because migration_source is None.
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert not artifact_path.exists()

    # Dispatch unchanged.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# 4. Writer raises -> Stage 29.3 mode-3 swallows the failure
# ---------------------------------------------------------------------------


class _RaisingWriter:
    def write_side_channel_artifact(
        self, *, output_dir, migration_source,
    ):
        raise RuntimeError("simulated writer failure")


def test_writer_failure_does_not_affect_smoke_result() -> None:
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
        migration_context_renderer=_RaisingWriter(),
    )

    # Smoke result is unaffected by the writer failure.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
