"""Stage 29.5.5 counter-invariant pins.

Pins that the Stage 29.3 mode-3 chain run with the Stage
29.5.5 recorder + writer wired (or omitted) preserves the
locked counter bounds:

  * ``events_seen <= 1`` (max_events=1 lock).
  * ``candidates_dispatched <= 1`` (max_dispatches=1 lock).
  * ``dispatch_success <= 1`` (single-dispatch terminal-record
    invariant).
  * ``filter_enforcement_status == NOT_ACTIVE_STAGE_29_PENDING``
    (Stage 29.5.5 must NOT activate enforcement).
  * Recorder ``recorded_entries`` length <= 1 (Stage 28.9 only
    builds one candidate per ceremony).
  * Side-channel artifact ``entry_count`` <= 1 when written.
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
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
_TEST_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_TEST_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"


# (Fakes duplicated minimal subset)


class _FakeStreamCallable:
    def __init__(self, responses):
        self._responses = responses

    def __call__(self, request_iterator, **kwargs):
        for _ in request_iterator:
            pass
        return _FakeResponseIter(self._responses)


class _FakeResponseIter:
    def __init__(self, responses):
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
    def __init__(self, method):
        self._method = method

    def __call__(self, *args, **kwargs):
        raise AssertionError(self._method)


class _FakeChannel:
    def __init__(self, responses):
        self._responses = responses
        self.close_called = False

    def stream_stream(self, method, **kwargs):
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
    def factory(target, credentials):
        return _FakeChannel(responses)
    return factory


def _make_pumpswap_tx_update():
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
    def __init__(self, *, bodies_by_path):
        self._bodies_by_path = dict(bodies_by_path)

    def get(
        self,
        *,
        endpoint_secret,
        path,
        query_params,
        timeout_seconds,
    ):
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
    def __init__(self):
        self.calls = []

    def send_one_audited_post(
        self,
        *,
        webhook_url,
        webhook_identity,
        payload,
    ):
        self.calls.append({"payload": payload})
        return _build_sent_ok_result()

    @property
    def call_count(self):
        return len(self.calls)


def _build_test_runtime_configs() -> Stage29_3RuntimeConfigBundle:
    cs_safe = build_chainstack_yellowstone_config(
        provider_id="chainstack_yellowstone_test",
        endpoint_safe_label="yellowstone_test_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    cs_secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url="yellowstone.test.local:443",
        x_token="test_x_token_abc1234567890",
        tls=True,
    )
    cs_config = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=cs_safe,
        endpoint_secret=cs_secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )
    birdeye_secret = Stage29_2BirdeyeEndpointSecret(
        _api_key="test_birdeye_api_key_abc1234567890",
        _base_url="https://public-api.test.local",
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
        tempfile.mkdtemp(
            prefix="phx2_stage29_5_5_counter_test_",
        ),
    )


def _build_birdeye_bodies():
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


def _evidence_for(token_mint: str):
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


def _ath_context_for(token_mint: str):
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


# ---------------------------------------------------------------------------
# Counter invariants when recorder + writer are wired
# ---------------------------------------------------------------------------


def test_recorder_plus_writer_preserves_counter_caps() -> None:
    out = _outside_repo_tmpdir()
    factory = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = Stage29_5_5MigrationContextRecorder(
        evidence_provider=_evidence_for,
        ath_context_provider=_ath_context_for,
        clock=lambda: _TEST_OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_FakeBirdeyeHttpTransport(
            bodies_by_path=_build_birdeye_bodies(),
        ),
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        migration_context_renderer=writer,
    )
    assert result.events_seen <= 1
    assert result.candidates_dispatched <= 1
    assert result.dispatch_success <= 1
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert len(recorder.recorded_entries) <= 1


def test_artifact_entry_count_capped_at_one_per_ceremony() -> None:
    out = _outside_repo_tmpdir()
    factory = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = Stage29_5_5MigrationContextRecorder(
        evidence_provider=_evidence_for,
        ath_context_provider=_ath_context_for,
        clock=lambda: _TEST_OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_FakeBirdeyeHttpTransport(
            bodies_by_path=_build_birdeye_bodies(),
        ),
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        migration_context_renderer=writer,
    )
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    if artifact_path.exists():
        bundle = json.loads(
            artifact_path.read_text(encoding="utf-8"),
        )
        assert bundle["entry_count"] <= 1


# ---------------------------------------------------------------------------
# Counter invariants when only recorder is wired (no writer)
# ---------------------------------------------------------------------------


def test_recorder_only_preserves_counter_caps() -> None:
    out = _outside_repo_tmpdir()
    factory = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = Stage29_5_5MigrationContextRecorder(
        evidence_provider=_evidence_for,
        ath_context_provider=_ath_context_for,
        clock=lambda: _TEST_OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_FakeBirdeyeHttpTransport(
            bodies_by_path=_build_birdeye_bodies(),
        ),
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        # no writer
    )
    assert result.events_seen <= 1
    assert result.candidates_dispatched <= 1
    assert result.dispatch_success <= 1
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# Counter invariants when neither is wired (regression guard)
# ---------------------------------------------------------------------------


def test_no_kwargs_preserves_counter_caps() -> None:
    out = _outside_repo_tmpdir()
    factory = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    fake_discord = _FakeAuditedDiscordTransport()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_FakeBirdeyeHttpTransport(
            bodies_by_path=_build_birdeye_bodies(),
        ),
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
    )
    assert result.events_seen <= 1
    assert result.candidates_dispatched <= 1
    assert result.dispatch_success <= 1
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
