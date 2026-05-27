"""Stage 29.5.4 no-duplicate-dispatch pins.

The Stage 29.3 mode-3 ceremony locks ``max_events=1`` /
``max_dispatches=1`` internally; the Stage 29.5.4 opt-in
migration_source adapter MUST NOT introduce duplicate dispatch
on any branch.

Pins:

  * With an explicit Stage 29.5.4-style migration_source wired
    AND 5 hint-bearing PumpSwap transactions on the fake stream,
    the Discord transport receives AT MOST 1 call.
  * Without the kwarg AND 5 hint-bearing PumpSwap transactions
    on the fake stream, the Discord transport receives AT MOST
    1 call (regression guard).
  * candidates_dispatched + dispatch_success + dispatch_failure
    invariants survive.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
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
from PHX2.stage29.stage29_3_no_migration_evidence_source import (
    Stage29_3NoMigrationEvidenceSource,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    run_stage29_3_first_private_tradeable_smoke,
)


_TEST_BASE_MINT: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_POOL_OWNER: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


class _RecordingMigrationContextSource:
    def __init__(self) -> None:
        self._default = Stage29_3NoMigrationEvidenceSource()
        self.calls: list[str] = []

    def read_migration_snapshot(
        self, token_mint: str,
    ) -> MigrationSourceSnapshot:
        self.calls.append(token_mint)
        return self._default.read_migration_snapshot(
            token_mint,
        )


# -- Fake gRPC plumbing ------------------------------------


class _FakeStreamCallable:
    def __init__(self, responses):
        self._responses = responses

    def __call__(
        self, request_iterator, timeout=None, metadata=None,
    ):
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
        raise AssertionError(
            f"unexpected gRPC method {self._method!r}"
        )


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


# -- Fake Birdeye + Discord ---------------------------------


class _FakeBirdeyeHttpTransport:
    def __init__(self, *, bodies_by_path):
        self._bodies_by_path = dict(bodies_by_path)
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret,
        path,
        query_params,
        timeout_seconds,
    ):
        self.calls.append({"path": path})
        body = self._bodies_by_path.get(path)
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body if body is not None else None,
            fetched_at_utc=datetime.now(
                timezone.utc,
            ).isoformat(),
        )


def _sent_ok():
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
        self.calls: list[dict] = []

    def send_one_audited_post(
        self,
        *,
        webhook_url,
        webhook_identity,
        payload,
    ):
        self.calls.append({})
        return _sent_ok()

    @property
    def call_count(self):
        return len(self.calls)


def _build_test_runtime_configs():
    cs_safe = build_chainstack_yellowstone_config(
        provider_id="test_provider",
        endpoint_safe_label="yellowstone_test_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    cs_secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url="yellowstone.test.local:443",
        x_token="test_x_token_1234567890",
        tls=True,
    )
    cs_config = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=cs_safe,
        endpoint_secret=cs_secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )
    birdeye_secret = Stage29_2BirdeyeEndpointSecret(
        _api_key="test_api_key_1234567890",
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


def _bodies():
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


def _tmpdir():
    return Path(
        tempfile.mkdtemp(
            prefix="phx2_stage29_5_4_nodup_test_",
        ),
    )


# ---------------------------------------------------------------------------
# 1. With adapter wired + 5 hint-bearing events -> <= 1 dispatch
# ---------------------------------------------------------------------------


def test_with_adapter_5_hint_events_at_most_1_dispatch() -> None:
    out = _tmpdir()
    configs = _build_test_runtime_configs()
    factory = _make_factory(
        responses=[
            _make_pumpswap_tx_update() for _ in range(5)
        ],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recording = _RecordingMigrationContextSource()
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
        max_messages_to_scan=64,
        write_artifacts=True,
        migration_source=recording,  # type: ignore[arg-type]
    )
    assert result.events_seen <= 1
    assert fake_discord.call_count <= 1
    assert (
        result.dispatch_success + result.dispatch_failure
        <= 1
    )
    assert result.candidates_dispatched <= 1


# ---------------------------------------------------------------------------
# 2. Without adapter + 5 hint-bearing events -> <= 1 dispatch
# (regression guard: Stage 29.5.4 must NOT regress the cap)
# ---------------------------------------------------------------------------


def test_without_adapter_5_hint_events_at_most_1_dispatch() -> None:
    out = _tmpdir()
    configs = _build_test_runtime_configs()
    factory = _make_factory(
        responses=[
            _make_pumpswap_tx_update() for _ in range(5)
        ],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_bodies(),
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
        max_messages_to_scan=64,
        write_artifacts=True,
        # migration_source omitted
    )
    assert result.events_seen <= 1
    assert fake_discord.call_count <= 1
    assert (
        result.dispatch_success + result.dispatch_failure
        <= 1
    )
    assert result.candidates_dispatched <= 1


# ---------------------------------------------------------------------------
# 3. With adapter wired + empty stream -> zero dispatch
# ---------------------------------------------------------------------------


def test_with_adapter_empty_stream_zero_dispatch() -> None:
    out = _tmpdir()
    configs = _build_test_runtime_configs()
    factory = _make_factory(responses=[])
    birdeye = _FakeBirdeyeHttpTransport(bodies_by_path={})
    fake_discord = _FakeAuditedDiscordTransport()
    recording = _RecordingMigrationContextSource()
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
        max_messages_to_scan=4,
        write_artifacts=True,
        migration_source=recording,  # type: ignore[arg-type]
    )
    assert result.events_seen == 0
    assert fake_discord.call_count == 0
    assert result.dispatch_success == 0
    assert result.candidates_dispatched == 0
    # The migration source must not have been consulted in this
    # branch -- no candidate was assembled.
    assert recording.calls == []
