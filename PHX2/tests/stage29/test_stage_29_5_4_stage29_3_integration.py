"""Stage 29.5.4 Stage 29.3 mode-3 integration pins.

End-to-end controlled offline test that:

  * Wires a recording fake ``migration_source`` (a subclass of
    ``Stage29_3NoMigrationEvidenceSource`` that records every
    ``read_migration_snapshot`` call) into
    ``run_stage29_3_first_private_tradeable_smoke``.
  * Drives the Stage 29.3 mode-3 ceremony through fake Chainstack
    gRPC + fake Birdeye HTTP + fake audited Discord transports.
  * Asserts the recording fake was called at least once when
    explicitly supplied, AND was NOT called when the operator
    omits the kwarg (because the default
    ``Stage29_3NoMigrationEvidenceSource`` is constructed
    independently).
  * Asserts the Stage 29.3 mode-3 outcome remains DISPATCHED
    regardless of whether the adapter is wired (the adapter is
    observational; it does NOT block dispatch on UNKNOWN
    snapshots).

No live network. No real WebSocket / gRPC / HTTP. No real
Discord webhook.
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
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    run_stage29_3_first_private_tradeable_smoke,
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


# ---------------------------------------------------------------------------
# Recording fake migration source
# ---------------------------------------------------------------------------


class _RecordingMigrationContextSource:
    """Records every read_migration_snapshot call; returns the
    deterministic Stage 29.3 default UNKNOWN snapshot (so the
    Stage 27.6 / Stage 27.4 / Stage 28.9 chain behaves
    byte-equivalently to the default Stage 29.3 mode-3 path).

    The recording fake is the smallest possible observation
    harness: it lets the test verify the Stage 29.5.4 opt-in
    seam wired the supplied instance into the Stage 27.6
    Sources bundle.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._default = Stage29_3NoMigrationEvidenceSource()

    def read_migration_snapshot(
        self, token_mint: str,
    ) -> MigrationSourceSnapshot:
        self.calls.append(token_mint)
        return self._default.read_migration_snapshot(
            token_mint,
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# Fake gRPC channel
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
        tempfile.mkdtemp(prefix="phx2_stage29_5_4_test_"),
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
# 1. Explicit migration_source kwarg is consulted on every assembled
# candidate (Stage 27.4 read_migration_context is called at least once)
# ---------------------------------------------------------------------------


def test_explicit_migration_source_is_consulted_at_least_once_in_mode3() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recording_source = _RecordingMigrationContextSource()

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
        migration_source=recording_source,  # type: ignore[arg-type]
    )

    # The supplied migration source MUST have been consulted at
    # least once during the Stage 27.6 candidate assembly.
    assert recording_source.call_count >= 1, (
        "Stage 29.5.4 opt-in seam: the supplied migration_source "
        "must be consulted at least once during Stage 29.3 "
        "mode-3 candidate assembly"
    )

    # Stage 29.3 mode-3 reached the DISPATCHED branch (the
    # recording fake returns UNKNOWN snapshots, identical to the
    # default Stage29_3NoMigrationEvidenceSource).
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# 2. Default kwarg (omitted) does NOT consult the recording source
# ---------------------------------------------------------------------------


def test_default_kwarg_does_not_consult_explicit_recording_source() -> None:
    """When the operator omits the migration_source kwarg, the
    Stage 29.3 mode-3 path constructs its own
    Stage29_3NoMigrationEvidenceSource() (the default fallback)
    and uses THAT instance -- the externally-constructed
    recording fake is never consulted because the operator did
    not wire it in.
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
    recording_source = _RecordingMigrationContextSource()

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
        # migration_source omitted -> Stage 29.3 default fallback
    )

    # The externally-constructed recording fake is NOT the same
    # instance the Stage 29.3 mode-3 path constructed internally,
    # so its call counter must remain zero.
    assert recording_source.call_count == 0, (
        "Default Stage 29.3 mode-3 path must NOT consult an "
        "externally-constructed migration_source instance when "
        "the kwarg is omitted"
    )

    # Behavior is byte-equivalent: still DISPATCHED, still one
    # Discord call.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# 3. Explicit None kwarg behaves identically to omission
# ---------------------------------------------------------------------------


def test_explicit_none_kwarg_uses_default_fallback() -> None:
    """Passing ``migration_source=None`` explicitly is identical
    to omitting the kwarg: the Stage 29.3 mode-3 path constructs
    Stage29_3NoMigrationEvidenceSource() internally.
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
    recording_source = _RecordingMigrationContextSource()

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
        migration_source=None,
    )

    assert recording_source.call_count == 0
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# 4. filter_enforcement_status preserved when adapter is wired
# ---------------------------------------------------------------------------


def test_filter_enforcement_status_preserved_when_adapter_wired() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recording_source = _RecordingMigrationContextSource()

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
        migration_source=recording_source,  # type: ignore[arg-type]
    )

    # The Stage 29.3 result's filter_enforcement_status is locked
    # at the Stage 28.9 wrapper / Stage 29.3 layer; the Stage
    # 29.5.4 adapter does NOT mutate it.
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# 5. Adapter wired -> chain produces DISPATCHED, observable
# counters survive
# ---------------------------------------------------------------------------


def test_adapter_wired_chain_dispatches_with_known_counters() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recording_source = _RecordingMigrationContextSource()

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
        migration_source=recording_source,  # type: ignore[arg-type]
    )

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert result.events_seen == 1
    assert result.candidates_dispatched == 1
    assert result.dispatch_success == 1
    assert result.dispatch_failure == 0
    assert fake_discord.call_count == 1
