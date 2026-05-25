"""Stage 29.1 PumpSwap hint live probe pins.

Pins via a channel-factory-injected fake (no network):

  * Live-gate False yields SKIPPED + LIVE_FLAG_NOT_SET.
  * Invalid runtime-config yields SKIPPED + MODE_INVALID.
  * Invalid mode yields SKIPPED + MODE_INVALID.
  * Invalid max_messages_to_scan yields SKIPPED +
    MAX_MESSAGES_TO_SCAN_INVALID.
  * Non-callable channel_factory yields SKIPPED +
    CHANNEL_FACTORY_NOT_CALLABLE.
  * Empty stream yields DECODED_NO_HINT_EVIDENCE +
    NO_TRANSACTION_RECEIVED.
  * Stream with only non-transaction variants (ping / pong /
    slot / etc.) yields DECODED_NO_HINT_EVIDENCE +
    NO_TRANSACTION_RECEIVED.
  * Stream with transaction-variant messages that do NOT
    contain a PumpSwap pool yields DECODED_NO_HINT_EVIDENCE +
    NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED.
  * Stream with a PumpSwap-shaped transaction yields
    DECODED_WITH_HINTS + payload + extraction.
  * Bounded scan: the probe stops at max_messages_to_scan
    even when the upstream keeps yielding non-matching events.
  * No env read on any code path (the probe uses the
    pre-built runtime-config).
"""

from __future__ import annotations

from typing import Optional

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
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
from PHX2.stage29.stage29_1_hint_probe_models import (
    PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
    PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
    PROBE_STATUS_DECODED_WITH_HINTS,
    PROBE_STATUS_SKIPPED,
    REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED,
    REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
)
from PHX2.stage29.stage29_1_pumpswap_hint_probe import (
    DEFAULT_MAX_MESSAGES_TO_SCAN,
    STAGE29_1_TRANSACTION_FILTER_NAME,
    build_pumpswap_subscribe_request,
    run_stage29_1_pumpswap_hint_probe,
)


_TEST_BASE_MINT: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_POOL_OWNER: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_PROVIDER_ID: str = "chainstack_yellowstone_test"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_abc1234567890"


# ---------------------------------------------------------------------------
# Fake gRPC channel
# ---------------------------------------------------------------------------


class _FakeStreamCallable:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses

    def __call__(
        self,
        request_iterator: object,
        timeout: Optional[float] = None,
        metadata: Optional[tuple] = None,
    ) -> "_FakeResponseIter":
        # Drain the request iterator to mirror real-stub
        # semantics. The Stage 29.1 probe constructs the request
        # via build_pumpswap_subscribe_request() and wraps it in
        # iter([request]); the fake doesn't validate the request
        # contents.
        for _ in request_iterator:
            pass
        return _FakeResponseIter(self._responses)


class _FakeResponseIter:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.cancel_called = False

    def __iter__(self) -> "_FakeResponseIter":
        return self

    def __next__(self) -> object:
        if self._idx >= len(self._responses):
            raise StopIteration
        item = self._responses[self._idx]
        self._idx += 1
        return item

    def cancel(self) -> None:
        self.cancel_called = True


class _FakeUnusedCallable:
    """No-op callable returned for channel methods the Stage
    29.1 probe is not allowed to invoke at call time. The
    generated ``GeyserStub.__init__`` constructs these
    bindings for every method on the service; the Stage 29.1
    probe only calls ``Subscribe``, but the bindings must
    exist at construction time. Calling the returned object
    raises a clear assertion so a regression that triggers
    Ping / GetSlot / etc. from the Stage 29.1 probe is
    caught.
    """

    def __init__(self, method: str) -> None:
        self._method = method

    def __call__(self, *args, **kwargs) -> object:
        raise AssertionError(
            f"Stage 29.1 probe must not invoke {self._method!r}"
        )


class _FakeChannel:
    """Stand-in for ``grpc.Channel`` that supports the subset of
    the gRPC API the generated ``GeyserStub`` exercises. The
    ``stream_stream`` binding returns a real fake for
    ``Subscribe``; every other binding returns a no-op
    callable so the GeyserStub constructor succeeds.
    """

    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.close_called = False

    def stream_stream(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ) -> object:
        if method.endswith("/Subscribe"):
            return _FakeStreamCallable(self._responses)
        return _FakeUnusedCallable(method)

    def unary_unary(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ) -> object:
        return _FakeUnusedCallable(method)

    def stream_unary(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ) -> object:
        return _FakeUnusedCallable(method)

    def unary_stream(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ) -> object:
        return _FakeUnusedCallable(method)

    def close(self) -> None:
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


# ---------------------------------------------------------------------------
# Test runtime-config helpers
# ---------------------------------------------------------------------------


def _build_test_runtime_config() -> (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
):
    safe_config = build_chainstack_yellowstone_config(
        provider_id=_TEST_PROVIDER_ID,
        endpoint_safe_label="yellowstone_test_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=_TEST_ENDPOINT,
        x_token=_TEST_X_TOKEN,
        tls=True,
    )
    return build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=safe_config,
        endpoint_secret=secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )


# ---------------------------------------------------------------------------
# Constructed SubscribeUpdate fixtures (transaction variant +
# non-transaction variants)
# ---------------------------------------------------------------------------


def _make_pumpswap_tx_update() -> (
    "_geyser_pb2.SubscribeUpdate"
):
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


def _make_non_pumpswap_tx_update() -> (
    "_geyser_pb2.SubscribeUpdate"
):
    """A transaction-variant SubscribeUpdate with no SPL token
    balances -- the Stage 29.1 extractor will report
    NO_EVIDENCE.
    """
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(range(1, 65))
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000
    return update


def _make_ping_update() -> "_geyser_pb2.SubscribeUpdate":
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.ping.SetInParent()
    return update


# ---------------------------------------------------------------------------
# Subscribe request builder
# ---------------------------------------------------------------------------


def test_build_pumpswap_subscribe_request_filter_shape():
    request = build_pumpswap_subscribe_request()
    assert (
        STAGE29_1_TRANSACTION_FILTER_NAME
        in request.transactions
    )
    tx_filter = request.transactions[
        STAGE29_1_TRANSACTION_FILTER_NAME
    ]
    assert tx_filter.vote is False
    assert tx_filter.failed is False
    assert (
        "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        in list(tx_filter.account_include)
    )
    assert request.commitment == _geyser_pb2.CONFIRMED


# ---------------------------------------------------------------------------
# Input validation -> SKIPPED results
# ---------------------------------------------------------------------------


def test_invalid_runtime_config_skipped_mode_invalid():
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config="not-a-runtime-config",  # type: ignore[arg-type]
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
    )
    assert result.status == PROBE_STATUS_SKIPPED
    assert result.refusal_reason == REFUSAL_REASON_MODE_INVALID
    assert result.hint_bearing_payload is None
    assert result.handoff_ready is False


def test_invalid_mode_skipped_mode_invalid():
    runtime_config = _build_test_runtime_config()
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode="OTHER_MODE",
        live_flag_set=True,
    )
    assert result.status == PROBE_STATUS_SKIPPED
    assert result.refusal_reason == REFUSAL_REASON_MODE_INVALID


def test_live_flag_not_set_skipped():
    runtime_config = _build_test_runtime_config()
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=False,
    )
    assert result.status == PROBE_STATUS_SKIPPED
    assert (
        result.refusal_reason
        == REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )


def test_invalid_max_messages_to_scan_skipped():
    runtime_config = _build_test_runtime_config()
    for bad in (0, -1, "10", None, True):
        result = run_stage29_1_pumpswap_hint_probe(
            runtime_config=runtime_config,
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            live_flag_set=True,
            max_messages_to_scan=bad,  # type: ignore[arg-type]
        )
        assert result.status == PROBE_STATUS_SKIPPED
        assert (
            result.refusal_reason
            == REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
        )


def test_non_callable_channel_factory_skipped():
    runtime_config = _build_test_runtime_config()
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        channel_factory="not-a-callable",  # type: ignore[arg-type]
    )
    assert result.status == PROBE_STATUS_SKIPPED
    assert (
        result.refusal_reason
        == REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE
    )


# ---------------------------------------------------------------------------
# Stream behavior with fake channel
# ---------------------------------------------------------------------------


def test_empty_stream_returns_no_transaction_received():
    runtime_config = _build_test_runtime_config()
    factory, captured = _make_factory(responses=[])
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert (
        result.status == PROBE_STATUS_DECODED_NO_HINT_EVIDENCE
    )
    assert (
        result.refusal_reason
        == REFUSAL_REASON_NO_TRANSACTION_RECEIVED
    )
    assert result.events_scanned == 0
    assert result.transactions_scanned == 0
    assert result.hint_bearing_payload is None
    # The factory's target was the runtime-config's endpoint URL.
    assert captured["target"] == _TEST_ENDPOINT
    # The fake channel close was called.
    assert captured["channel"].close_called


def test_only_ping_variants_returns_no_transaction_received():
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_ping_update(),
        _make_ping_update(),
        _make_ping_update(),
    ]
    factory, _captured = _make_factory(responses=responses)
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert (
        result.status == PROBE_STATUS_DECODED_NO_HINT_EVIDENCE
    )
    assert (
        result.refusal_reason
        == REFUSAL_REASON_NO_TRANSACTION_RECEIVED
    )
    assert result.events_scanned == 3
    assert result.transactions_scanned == 0


def test_non_pumpswap_tx_returns_no_hint_bearing():
    runtime_config = _build_test_runtime_config()
    responses = [_make_non_pumpswap_tx_update()]
    factory, _captured = _make_factory(responses=responses)
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert (
        result.status == PROBE_STATUS_DECODED_NO_HINT_EVIDENCE
    )
    assert (
        result.refusal_reason
        == REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
    )
    assert result.transactions_scanned == 1
    assert result.extraction_result is not None
    assert result.hint_bearing_payload is None


def test_pumpswap_tx_returns_hint_bearing_payload():
    runtime_config = _build_test_runtime_config()
    responses = [_make_pumpswap_tx_update()]
    factory, _captured = _make_factory(responses=responses)
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert result.status == PROBE_STATUS_DECODED_WITH_HINTS
    assert result.refusal_reason == REFUSAL_REASON_NONE
    assert result.handoff_ready is True
    payload = result.hint_bearing_payload
    assert payload is not None
    assert payload.base_mint == _TEST_BASE_MINT
    assert payload.pool_account == _TEST_POOL_OWNER
    assert payload.quote_mint == WRAPPED_SOL_MINT
    assert payload.provider_pair_type_hint == "PUMP_SOL"
    assert payload.provider_quote_asset_hint == "SOL"
    assert (
        payload.pool_program_id
        == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    )
    assert payload.bonding_curve_version_hint is None
    assert result.extraction_result is not None
    assert (
        result.extraction_result.outcome == "HINTS_EXTRACTED"
    )
    assert result.transactions_scanned == 1


def test_pumpswap_found_after_skipping_pings():
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_ping_update(),
        _make_ping_update(),
        _make_non_pumpswap_tx_update(),
        _make_pumpswap_tx_update(),
        # Trailing events should NOT be consumed past the
        # winning event.
        _make_pumpswap_tx_update(),
    ]
    factory, _captured = _make_factory(responses=responses)
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=16,
        channel_factory=factory,
    )
    assert result.status == PROBE_STATUS_DECODED_WITH_HINTS
    # 2 pings + 1 non-pumpswap tx + 1 pumpswap tx = 4 events
    # scanned before returning.
    assert result.events_scanned == 4
    assert result.transactions_scanned == 2


def test_bounded_scan_caps_consumption():
    runtime_config = _build_test_runtime_config()
    # 100 non-PumpSwap updates -- the probe must stop at the
    # cap and surface NO_PUMPSWAP_HINT_BEARING_TRANSACTION.
    responses = [
        _make_non_pumpswap_tx_update() for _ in range(100)
    ]
    factory, _captured = _make_factory(responses=responses)
    result = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert (
        result.status == PROBE_STATUS_DECODED_NO_HINT_EVIDENCE
    )
    assert (
        result.refusal_reason
        == REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
    )
    assert result.events_scanned == 8
    assert result.transactions_scanned == 8


def test_default_max_messages_to_scan_constant():
    assert DEFAULT_MAX_MESSAGES_TO_SCAN == 64


# ---------------------------------------------------------------------------
# No-env-read pin: pytest fixture mutates os.environ to confirm
# the probe does NOT consult it.
# ---------------------------------------------------------------------------


def test_probe_does_not_read_os_environ(monkeypatch):
    """The probe must never reach into ``os.environ``. We
    sentinel-stamp the env and assert the probe still returns
    the same result with or without sentinels.
    """
    runtime_config = _build_test_runtime_config()
    responses = [_make_pumpswap_tx_update()]
    factory_a, _ = _make_factory(responses=responses)
    monkeypatch.setenv(
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
        "do-not-read-this-test-stamp",
    )
    monkeypatch.setenv(
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
        "do-not-read-this-test-stamp",
    )
    result_a = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory_a,
    )
    # The probe should have used the runtime_config's secret
    # (test endpoint), NOT the env sentinel.
    assert result_a.status == PROBE_STATUS_DECODED_WITH_HINTS

    monkeypatch.delenv(
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
        raising=False,
    )
    monkeypatch.delenv(
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN", raising=False,
    )
    factory_b, _ = _make_factory(responses=responses)
    result_b = run_stage29_1_pumpswap_hint_probe(
        runtime_config=runtime_config,
        mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
        live_flag_set=True,
        max_messages_to_scan=8,
        channel_factory=factory_b,
    )
    assert result_b.status == result_a.status
    assert result_b.refusal_reason == result_a.refusal_reason
