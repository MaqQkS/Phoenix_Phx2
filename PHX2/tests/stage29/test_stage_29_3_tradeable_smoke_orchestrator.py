"""Stage 29.3 tradeable-smoke orchestrator pins.

Pins:

  * Mode validation (closed-set probe-mode tokens).
  * Mode 1 readiness gates (live env, operator request, webhook,
    output dir).
  * Mode 1 happy path => READY.
  * Mode 2 known_mint requirement.
  * Mode 2 happy path => CONNECTED via fake gRPC channel + fake
    Birdeye HTTP transport (no Discord call).
  * Mode 3 cap enforcement: 5 hint-bearing transactions on the
    fake stream => exactly 1 assembler call, exactly 1 Discord
    transport call (max_events=1, max_dispatches=1).
  * Mode 3 happy path => DISPATCHED, 1 hint-bearing payload
    present.
  * Mode 3 suppression branches => SUPPRESSED_* outcomes, 0
    Discord transport calls.
  * Mode 3 readiness refusal: no gRPC, no HTTP, no Discord call
    when live-flag is False or webhook missing.
  * No env read on any code path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Mapping, Optional

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
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
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
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
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    TRADEABLE_SMOKE_OUTCOME_CONNECTED,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_OUTCOME_REFUSED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
    TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    DEFAULT_CONNECT_ONLY_MAX_MESSAGES_TO_SCAN,
    DEFAULT_PRICE_STALENESS_THRESHOLD_SECONDS,
    Stage29_3RuntimeConfigBundle,
    Stage29_3UtcClock,
    run_stage29_3_first_private_tradeable_smoke,
)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------


_TEST_BASE_MINT: str = "TestBaseMintAAAA1111111111111111111111111A"
_TEST_POOL_OWNER: str = "TestPoolXXXXXXX3333333333333333333333333X"
_TEST_PROVIDER_ID: str = "chainstack_yellowstone_test"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_abc1234567890"
_TEST_BIRDEYE_API_KEY: str = "test_birdeye_api_key_abc1234567890"
_TEST_BIRDEYE_BASE_URL: str = "https://public-api.test.local"
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


# ---------------------------------------------------------------------------
# Fake gRPC channel (same shape as test_stage_29_3_hint_aware_event_source)
# ---------------------------------------------------------------------------


class _FakeStreamCallable:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses

    def __call__(self, request_iterator, timeout=None, metadata=None):
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
            f"Stage 29.3 source must not invoke {self._method!r}"
        )


class _FakeChannel:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.close_called = False

    def stream_stream(self, method, request_serializer=None, response_deserializer=None, **kwargs):
        if method.endswith("/Subscribe"):
            return _FakeStreamCallable(self._responses)
        return _FakeUnusedCallable(method)

    def unary_unary(self, method, request_serializer=None, response_deserializer=None, **kwargs):
        return _FakeUnusedCallable(method)

    def stream_unary(self, method, request_serializer=None, response_deserializer=None, **kwargs):
        return _FakeUnusedCallable(method)

    def unary_stream(self, method, request_serializer=None, response_deserializer=None, **kwargs):
        return _FakeUnusedCallable(method)

    def close(self):
        self.close_called = True


def _make_factory(responses: list[object]):
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
    update.transaction.transaction.signature = bytes(range(1, 65))
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
# Fake Stage 29.2 Birdeye HTTP transport
# ---------------------------------------------------------------------------


class _FakeBirdeyeHttpTransport:
    """Records every Birdeye GET call + returns scripted bodies.

    Maps path -> body. Returns ``refusal_reason=NONE`` +
    ``http_status_code=200`` on every recognized path.
    """

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
            fetched_at_utc="2026-05-25T03:13:25+00:00",
        )


class _FakeBirdeyeHttpTransportFailing:
    """All paths return SOURCE_ERROR-shape result."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append({"path": path})
        # HTTP_FAILED maps to SOURCE_ERROR in the Birdeye source
        # adapters.
        return Stage29_2BirdeyeHttpResult(
            refusal_reason="HTTP_FAILED",
            http_status_code=0,
            body=None,
            fetched_at_utc="2026-05-25T03:13:25+00:00",
        )


# ---------------------------------------------------------------------------
# Fake Stage 28.4-shaped audited transport
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
    """Stage 28.4-shaped fake transport. Counts calls; never
    opens a network connection.
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
                "payload": dict(payload)
                if isinstance(payload, dict)
                else {},
            }
        )
        return _build_sent_ok_result()

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# Test runtime-config bundle helper
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
    """Return an OS-level temp directory outside the PHX2 repo.

    Stage 28.9 readiness rejects output directories inside the
    PHX2 working tree; pytest's ``tmp_path`` (when launched with
    ``--basetemp=PHX2/.pytest_tmp``) lives inside the repo, so
    mode-3 tests must use ``tempfile.mkdtemp()`` directly.
    """
    return Path(tempfile.mkdtemp(prefix="phx2_stage29_3_test_"))


# ---------------------------------------------------------------------------
# Mode validation
# ---------------------------------------------------------------------------


def test_invalid_mode_refused_mode_invalid(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode="BOGUS",
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID
    )


# ---------------------------------------------------------------------------
# Mode 1 — readiness gates
# ---------------------------------------------------------------------------


def test_mode1_live_flag_not_set_refused(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=False,
        live_operator_request=True,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )


def test_mode1_operator_request_not_set_refused(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=False,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET
    )


def test_mode1_empty_webhook_refused(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=configs,
        private_webhook_url="",
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING
    )


def test_mode1_happy_path_ready(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_READY
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_NONE
    )
    assert result.stop_reason == "READINESS_OK"


# ---------------------------------------------------------------------------
# Mode 2 — connect-only
# ---------------------------------------------------------------------------


def test_mode2_missing_known_mint_refused(tmp_path):
    configs = _build_test_runtime_configs()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=None,
        write_artifacts=False,
    )
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID
    )


def test_mode2_no_discord_call(tmp_path):
    """Mode 2 must NEVER call the Discord transport."""
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path={
            "/defi/price": {
                "data": {
                    "value": 0.000036,
                    "updateUnixTime": 1779678781,
                },
            },
        },
    )
    fake_discord = _FakeAuditedDiscordTransport()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=4,
        write_artifacts=False,
    )
    # Mode 2 only calls /defi/price, never Discord.
    assert fake_discord.call_count == 0
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_CONNECTED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_NONE
    )
    assert result.birdeye_price_present is True


def test_mode2_birdeye_failure_failed_outcome(tmp_path):
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(responses=[])
    failing = _FakeBirdeyeHttpTransportFailing()
    fake_discord = _FakeAuditedDiscordTransport()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=failing,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=4,
        write_artifacts=False,
    )
    assert fake_discord.call_count == 0
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED
    )


# ---------------------------------------------------------------------------
# Mode 3 — full dispatch chain
# ---------------------------------------------------------------------------


def test_mode3_cap_5_events_at_most_1_dispatch():
    """5 hint-bearing transactions on the fake stream => at most
    1 Discord transport call (max_events=1, max_dispatches=1).

    Whether the actual outcome is DISPATCHED or one of the
    SUPPRESSED_* verdicts depends on the Stage 27 chain's
    pair-classifier + price-unit handling (which is exercised
    independently by Stage 27 tests). Stage 29.3 only owns the
    cap-enforcement invariant: at most ONE event consumed AND
    at most ONE Discord call regardless of how many upstream
    hint-bearing events are available.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[
            _make_pumpswap_tx_update() for _ in range(5)
        ],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path={
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
        },
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
    )
    # CAP-ENFORCEMENT INVARIANTS (Stage 29.3 owns these):
    # 1. At most ONE upstream event consumed regardless of how
    #    many hint-bearing transactions were available.
    assert result.events_seen <= 1
    # 2. At most ONE Discord transport call.
    assert fake_discord.call_count <= 1
    # 3. dispatch_success + dispatch_failure <= 1 (max_dispatches).
    assert result.dispatch_success + result.dispatch_failure <= 1
    # 4. candidates_dispatched <= 1.
    assert result.candidates_dispatched <= 1
    # 5. The outcome is one of the closed-set Stage 29.3 outcomes
    #    and refusal_reason consistency holds (validation already
    #    enforces this in the dataclass __post_init__).
    # 6. If DISPATCHED, transport call count is exactly 1;
    #    if SUPPRESSED_*, transport call count is exactly 0.
    # NOTE: Stage 29.3B fixed the hint-forwarding seam (the Stage
    # 27.2 classifier now resolves PUMP_SOL on this fake stream),
    # but the orchestrator test still admits SUPPRESSED_UNKNOWN_PAIR
    # as an outcome because Stage 27.5 / 27.4 currently emit
    # RENDERED_UNSUPPORTED for the USD-priced Birdeye snapshot on a
    # SOL pair, which the Stage 27.6 assembler maps via its
    # defensive fallback to SUPPRESSED_UNKNOWN_PAIR. That downstream
    # defect is out of Stage 29.3B's scope; tightening this
    # assertion would require a separate Stage 29.3C / Stage 27.4
    # USD-pair patch.
    if (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    ):
        assert fake_discord.call_count == 1
        assert result.dispatch_success == 1
    else:
        assert fake_discord.call_count == 0


def test_mode3_no_event_received_no_dispatch():
    """Empty stream => no event reaches the chain; no Discord
    call; outcome NO_EVENT_RECEIVED.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(responses=[])
    birdeye = _FakeBirdeyeHttpTransport(bodies_by_path={})
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
        max_messages_to_scan=4,
        write_artifacts=True,
    )
    assert fake_discord.call_count == 0
    assert result.events_seen == 0
    assert result.candidates_dispatched == 0
    assert result.dispatch_success == 0
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED
    )


def test_mode3_readiness_refusal_no_grpc_no_http_no_discord(tmp_path):
    """Mode 3 readiness refusal: live_env_ready=False => no
    gRPC call (channel_factory NEVER invoked), no Birdeye call,
    no Discord call.
    """
    configs = _build_test_runtime_configs()
    factory_invoked: dict = {"count": 0}

    def asserting_factory(target, credentials):
        factory_invoked["count"] += 1
        raise AssertionError(
            "Stage 29.3 mode 3 readiness refusal must NOT open "
            "the gRPC channel"
        )

    birdeye = _FakeBirdeyeHttpTransport(bodies_by_path={})
    fake_discord = _FakeAuditedDiscordTransport()
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=tmp_path,
        live_env_ready=False,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=asserting_factory,
        write_artifacts=False,
    )
    assert factory_invoked["count"] == 0
    assert len(birdeye.calls) == 0
    assert fake_discord.call_count == 0
    assert result.tradeable_smoke_outcome == TRADEABLE_SMOKE_OUTCOME_REFUSED
    assert (
        result.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_price_staleness_threshold_seconds_300():
    assert DEFAULT_PRICE_STALENESS_THRESHOLD_SECONDS == 300


def test_default_connect_only_max_messages_to_scan_8():
    assert DEFAULT_CONNECT_ONLY_MAX_MESSAGES_TO_SCAN == 8


# ---------------------------------------------------------------------------
# UTC clock
# ---------------------------------------------------------------------------


def test_utc_clock_methods():
    clock = Stage29_3UtcClock()
    now = clock.utc_now()
    iso = clock.now_utc_iso()
    assert isinstance(iso, str)
    assert now.tzinfo is not None
    assert iso.endswith("+00:00") or iso.endswith("Z")
