"""Stage 29.5.4 counter-invariant pins.

Pins that the Stage 29.3 mode-3 chain run with the Stage 29.5.4
adapter wired (or omitted) preserves the locked counter bounds:

  * ``events_seen <= 1`` (max_events=1 lock).
  * ``candidates_dispatched <= 1`` (max_dispatches=1 lock).
  * ``dispatch_success <= 1`` (single-dispatch terminal-record
    invariant).
  * ``filter_enforcement_status == NOT_ACTIVE_STAGE_29_PENDING``
    (Stage 29.5.4 must NOT activate enforcement).

These pins are the Stage 29.5.4 layer of the broader Stage 29.3
cap-enforcement contract; the no_duplicate_dispatch test file
exercises the cap from the dispatch-count angle, and this file
exercises it from the result-record counter angle.
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


class _RecordingSource:
    def __init__(self):
        self._d = Stage29_3NoMigrationEvidenceSource()
        self.calls: list[str] = []

    def read_migration_snapshot(self, token_mint: str):
        self.calls.append(token_mint)
        return self._d.read_migration_snapshot(token_mint)


class _FakeStream:
    def __init__(self, responses):
        self._responses = responses

    def __call__(
        self, request_iterator, timeout=None, metadata=None,
    ):
        for _ in request_iterator:
            pass
        return _FakeIter(self._responses)


class _FakeIter:
    def __init__(self, responses):
        self._r = list(responses)
        self._i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._i >= len(self._r):
            raise StopIteration
        v = self._r[self._i]
        self._i += 1
        return v

    def cancel(self):
        return None


class _FakeUnused:
    def __init__(self, m):
        self._m = m

    def __call__(self, *a, **k):
        raise AssertionError(self._m)


class _FakeChannel:
    def __init__(self, responses):
        self._r = responses

    def stream_stream(self, method, **kw):
        if method.endswith("/Subscribe"):
            return _FakeStream(self._r)
        return _FakeUnused(method)

    def unary_unary(self, method, **kw):
        return _FakeUnused(method)

    def stream_unary(self, method, **kw):
        return _FakeUnused(method)

    def unary_stream(self, method, **kw):
        return _FakeUnused(method)

    def close(self):
        return None


def _factory(responses):
    def f(target, credentials):
        return _FakeChannel(responses)
    return f


def _tx():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(
        range(1, 65),
    )
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000
    meta = update.transaction.transaction.meta
    for idx, (mint, owner) in enumerate((
        (WRAPPED_SOL_MINT, _TEST_POOL_OWNER),
        (_TEST_BASE_MINT, _TEST_POOL_OWNER),
    )):
        pre = meta.pre_token_balances.add()
        pre.account_index = idx
        pre.mint = mint
        pre.owner = owner
        pre.program_id = SPL_TOKEN_PROGRAM_ID
        post = meta.post_token_balances.add()
        post.account_index = idx
        post.mint = mint
        post.owner = owner
        post.program_id = SPL_TOKEN_PROGRAM_ID
    return update


class _BeTransport:
    def __init__(self, bodies):
        self._bodies = dict(bodies)

    def get(
        self,
        *,
        endpoint_secret,
        path,
        query_params,
        timeout_seconds,
    ):
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=self._bodies.get(path),
            fetched_at_utc=datetime.now(
                timezone.utc,
            ).isoformat(),
        )


def _ok():
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


class _Discord:
    def __init__(self):
        self.calls = []

    def send_one_audited_post(
        self,
        *,
        webhook_url,
        webhook_identity,
        payload,
    ):
        self.calls.append({})
        return _ok()


def _cfgs():
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


def _tmp():
    return Path(
        tempfile.mkdtemp(
            prefix="phx2_stage29_5_4_counter_test_",
        ),
    )


# ---------------------------------------------------------------------------
# 1. With adapter wired: events_seen / candidates_dispatched /
# dispatch_success <= 1
# ---------------------------------------------------------------------------


def test_counter_invariants_with_adapter_wired() -> None:
    recording = _RecordingSource()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_cfgs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=_tmp(),
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_BeTransport(_bodies()),
        audited_discord_transport=_Discord(),  # type: ignore[arg-type]
        channel_factory=_factory([_tx() for _ in range(3)]),
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recording,  # type: ignore[arg-type]
    )
    assert result.events_seen <= 1
    assert result.candidates_dispatched <= 1
    assert result.dispatch_success <= 1


# ---------------------------------------------------------------------------
# 2. Without adapter: same invariants
# ---------------------------------------------------------------------------


def test_counter_invariants_without_adapter() -> None:
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_cfgs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=_tmp(),
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_BeTransport(_bodies()),
        audited_discord_transport=_Discord(),  # type: ignore[arg-type]
        channel_factory=_factory([_tx() for _ in range(3)]),
        max_messages_to_scan=8,
        write_artifacts=True,
    )
    assert result.events_seen <= 1
    assert result.candidates_dispatched <= 1
    assert result.dispatch_success <= 1


# ---------------------------------------------------------------------------
# 3. filter_enforcement_status preserved with adapter wired
# ---------------------------------------------------------------------------


def test_filter_enforcement_status_not_active_with_adapter() -> None:
    recording = _RecordingSource()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_cfgs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=_tmp(),
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_BeTransport(_bodies()),
        audited_discord_transport=_Discord(),  # type: ignore[arg-type]
        channel_factory=_factory([_tx()]),
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recording,  # type: ignore[arg-type]
    )
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# 4. filter_enforcement_status preserved without adapter
# ---------------------------------------------------------------------------


def test_filter_enforcement_status_not_active_without_adapter() -> None:
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_cfgs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=_tmp(),
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_BeTransport(_bodies()),
        audited_discord_transport=_Discord(),  # type: ignore[arg-type]
        channel_factory=_factory([_tx()]),
        max_messages_to_scan=8,
        write_artifacts=True,
    )
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# 5. dispatch_success + dispatch_failure <= 1 (single-dispatch invariant)
# ---------------------------------------------------------------------------


def test_dispatch_total_at_most_one_with_adapter() -> None:
    recording = _RecordingSource()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=_cfgs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=_tmp(),
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_BeTransport(_bodies()),
        audited_discord_transport=_Discord(),  # type: ignore[arg-type]
        channel_factory=_factory([_tx() for _ in range(2)]),
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recording,  # type: ignore[arg-type]
    )
    assert (
        result.dispatch_success + result.dispatch_failure
        <= 1
    )
