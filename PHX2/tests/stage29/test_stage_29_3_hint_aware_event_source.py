"""Stage 29.3 hint-aware Chainstack event source pins.

Pins via a channel-factory-injected fake (no network):

  * Invalid runtime-config -> init refusal,
    ``RUNTIME_CONFIG_INVALID``; iter yields nothing.
  * Invalid max_messages_to_scan -> init refusal,
    ``MAX_MESSAGES_TO_SCAN_INVALID``; iter yields nothing.
  * Non-callable channel_factory -> init refusal,
    ``CHANNEL_FACTORY_NOT_CALLABLE``; iter yields nothing.
  * Empty stream -> last refusal
    ``NO_HINT_BEARING_TRANSACTION_RECEIVED``; iter yields
    nothing.
  * Stream with only non-transaction variants (ping etc.) ->
    same refusal as empty.
  * Stream with a hint-bearing PumpSwap transaction -> iter
    yields exactly one Stage 28.10 normalized event carrying the
    extracted hint quartet; cancel is called on the response
    iterator.
  * Bounded scan: source stops at ``max_messages_to_scan`` even
    when the upstream keeps yielding non-matching events.
  * No env read on any code path (the source uses the pre-built
    runtime-config).
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
    Stage28_10NormalizedEvent,
    build_chainstack_yellowstone_config,
)
from PHX2.stage29.pumpswap_program_constants import (
    SPL_TOKEN_PROGRAM_ID,
    WRAPPED_SOL_MINT,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    DEFAULT_MAX_MESSAGES_TO_SCAN,
    REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
    REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_RUNTIME_CONFIG_INVALID,
    STAGE29_3_TRANSACTION_FILTER_NAME,
    Stage29_3HintAwareChainstackEventSource,
    build_pumpswap_subscribe_request,
)


_TEST_BASE_MINT: str = "TestBaseMintAAAA1111111111111111111111111A"
_TEST_POOL_OWNER: str = "TestPoolXXXXXXX3333333333333333333333333X"
_TEST_PROVIDER_ID: str = "chainstack_yellowstone_test"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_abc1234567890"


# ---------------------------------------------------------------------------
# Fake gRPC channel (mirrors the Stage 29.1 probe test pattern)
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
    def __init__(self, method: str) -> None:
        self._method = method

    def __call__(self, *args, **kwargs) -> object:
        raise AssertionError(
            f"Stage 29.3 source must not invoke {self._method!r}"
        )


class _FakeChannel:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.close_called = False

    def stream_stream(
        self, method, request_serializer=None,
        response_deserializer=None, **kwargs,
    ) -> object:
        if method.endswith("/Subscribe"):
            return _FakeStreamCallable(self._responses)
        return _FakeUnusedCallable(method)

    def unary_unary(
        self, method, request_serializer=None,
        response_deserializer=None, **kwargs,
    ) -> object:
        return _FakeUnusedCallable(method)

    def stream_unary(
        self, method, request_serializer=None,
        response_deserializer=None, **kwargs,
    ) -> object:
        return _FakeUnusedCallable(method)

    def unary_stream(
        self, method, request_serializer=None,
        response_deserializer=None, **kwargs,
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
# Test runtime-config + fixture helpers
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


def _make_non_pumpswap_tx_update() -> "_geyser_pb2.SubscribeUpdate":
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
    assert STAGE29_3_TRANSACTION_FILTER_NAME in request.transactions
    tx_filter = request.transactions[
        STAGE29_3_TRANSACTION_FILTER_NAME
    ]
    assert tx_filter.vote is False
    assert tx_filter.failed is False
    assert (
        "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        in list(tx_filter.account_include)
    )
    assert request.commitment == _geyser_pb2.CONFIRMED


# ---------------------------------------------------------------------------
# Construction-time refusals
# ---------------------------------------------------------------------------


def test_invalid_runtime_config_init_refused():
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config="not-a-config",  # type: ignore[arg-type]
    )
    assert source.init_refusal_reason == REFUSAL_REASON_RUNTIME_CONFIG_INVALID
    yielded = list(source.iter_events(max_events=1))
    assert yielded == []


def test_invalid_max_messages_to_scan_init_refused():
    runtime_config = _build_test_runtime_config()
    for bad in (0, -1, True):
        source = Stage29_3HintAwareChainstackEventSource(
            runtime_config=runtime_config,
            max_messages_to_scan=bad,  # type: ignore[arg-type]
        )
        assert (
            source.init_refusal_reason
            == REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
        )
        assert list(source.iter_events(max_events=1)) == []


def test_non_callable_channel_factory_init_refused():
    runtime_config = _build_test_runtime_config()
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        channel_factory="not-callable",  # type: ignore[arg-type]
    )
    assert (
        source.init_refusal_reason
        == REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE
    )
    assert list(source.iter_events(max_events=1)) == []


# ---------------------------------------------------------------------------
# Empty / non-matching streams
# ---------------------------------------------------------------------------


def test_empty_stream_yields_nothing_with_no_hint_refusal():
    runtime_config = _build_test_runtime_config()
    factory, captured = _make_factory(responses=[])
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert list(source.iter_events(max_events=1)) == []
    assert (
        source.last_refusal_reason
        == REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
    )
    assert captured["channel"].close_called is True


def test_ping_only_stream_yields_nothing():
    runtime_config = _build_test_runtime_config()
    factory, _captured = _make_factory(
        responses=[_make_ping_update(), _make_ping_update()],
    )
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    assert list(source.iter_events(max_events=1)) == []
    assert (
        source.last_refusal_reason
        == REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
    )


def test_non_pumpswap_tx_stream_yields_nothing():
    runtime_config = _build_test_runtime_config()
    factory, _captured = _make_factory(
        responses=[_make_non_pumpswap_tx_update()],
    )
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=4,
        channel_factory=factory,
    )
    assert list(source.iter_events(max_events=1)) == []
    assert (
        source.last_refusal_reason
        == REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
    )


# ---------------------------------------------------------------------------
# Happy path: one hint-bearing PumpSwap event
# ---------------------------------------------------------------------------


def test_hint_bearing_tx_yields_one_normalized_event():
    runtime_config = _build_test_runtime_config()
    factory, captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    yielded = list(source.iter_events(max_events=1))
    assert len(yielded) == 1
    event = yielded[0]
    assert isinstance(event, Stage28_10NormalizedEvent)
    assert event.base_mint == _TEST_BASE_MINT
    assert event.pool_account == _TEST_POOL_OWNER
    assert event.quote_mint == WRAPPED_SOL_MINT
    assert (
        event.pool_program_id
        == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    )
    assert event.provider_pair_type_hint == "PUMP_SOL"
    assert event.provider_quote_asset_hint == "SOL"
    assert source.hint_bearing_yielded == 1
    assert source.last_refusal_reason == REFUSAL_REASON_NONE


def test_response_iter_cancelled_on_success():
    runtime_config = _build_test_runtime_config()
    factory, captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    list(source.iter_events(max_events=1))
    assert captured["channel"].close_called is True


# ---------------------------------------------------------------------------
# Bounded scan: max_messages_to_scan honoured
# ---------------------------------------------------------------------------


def test_bounded_scan_stops_at_max_messages():
    runtime_config = _build_test_runtime_config()
    # 10 non-matching transactions; source must stop at the cap
    # without yielding anything and without exhausting the
    # response iterator beyond the cap.
    responses = [
        _make_non_pumpswap_tx_update() for _ in range(10)
    ]
    factory, captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=3,
        channel_factory=factory,
    )
    assert list(source.iter_events(max_events=1)) == []
    # Stage 29.3A: scan budget is now independent of the yield cap.
    # With max_messages_to_scan=3 and 10 non-matching messages
    # available, the source MUST scan exactly 3 messages before
    # surrendering, not 1.
    assert source.events_scanned == 3
    assert source.hint_bearing_yielded == 0
    assert (
        source.last_refusal_reason
        == REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
    )


def test_default_max_messages_to_scan_is_64():
    # The default constant is a pinned 64 to mirror Stage 29.1.
    assert DEFAULT_MAX_MESSAGES_TO_SCAN == 64


# ---------------------------------------------------------------------------
# Stage 29.3A: scan budget decoupled from yield cap
# ---------------------------------------------------------------------------


def test_99_non_hints_then_1_hint_yields_exactly_one_event():
    """With max_events=1 and max_messages_to_scan=100, a stream
    of 99 non-hint-bearing messages followed by 1 hint-bearing
    PumpSwap transaction MUST yield exactly 1 normalized event.
    Non-hint-bearing messages do not consume the yield budget;
    the source keeps scanning until either a hint-bearing payload
    appears or the scan budget is exhausted.
    """
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_non_pumpswap_tx_update() for _ in range(99)
    ] + [_make_pumpswap_tx_update()]
    factory, _captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=100,
        channel_factory=factory,
    )
    yielded = list(source.iter_events(max_events=1))
    assert len(yielded) == 1
    event = yielded[0]
    assert isinstance(event, Stage28_10NormalizedEvent)
    assert event.base_mint == _TEST_BASE_MINT
    assert source.hint_bearing_yielded == 1
    # The source scanned all 100 messages: 99 non-hints + 1 hint.
    assert source.events_scanned == 100
    assert source.last_refusal_reason == REFUSAL_REASON_NONE


def test_100_non_hints_yields_zero_events_cleanly():
    """With max_events=1 and max_messages_to_scan=100, a stream
    of 100 non-hint-bearing messages MUST yield zero events and
    stop with the NO_HINT_BEARING_TRANSACTION_RECEIVED closed-set
    refusal. The source MUST scan exactly the budget (100), not
    short-circuit at 1.
    """
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_non_pumpswap_tx_update() for _ in range(100)
    ]
    factory, captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=100,
        channel_factory=factory,
    )
    yielded = list(source.iter_events(max_events=1))
    assert yielded == []
    assert source.events_scanned == 100
    assert source.hint_bearing_yielded == 0
    assert (
        source.last_refusal_reason
        == REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
    )
    assert captured["channel"].close_called is True


def test_non_hints_do_not_consume_max_events_budget():
    """3 non-hint-bearing messages followed by 1 hint-bearing
    message with max_events=1, max_messages_to_scan=4 MUST yield
    exactly 1 event after scanning all 4 messages. Verifies that
    the 3 non-hints did NOT each "burn" the yield budget.
    """
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_non_pumpswap_tx_update(),
        _make_non_pumpswap_tx_update(),
        _make_non_pumpswap_tx_update(),
        _make_pumpswap_tx_update(),
    ]
    factory, _captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=4,
        channel_factory=factory,
    )
    yielded = list(source.iter_events(max_events=1))
    assert len(yielded) == 1
    assert source.hint_bearing_yielded == 1
    assert source.events_scanned == 4
    assert source.last_refusal_reason == REFUSAL_REASON_NONE


def test_multiple_hints_capped_at_max_events():
    """5 hint-bearing messages on the stream with max_events=2
    and max_messages_to_scan=64 MUST yield exactly 2 events; the
    source returns immediately after ``yielded == max_events``.
    """
    runtime_config = _build_test_runtime_config()
    responses = [_make_pumpswap_tx_update() for _ in range(5)]
    factory, _captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=64,
        channel_factory=factory,
    )
    yielded = list(source.iter_events(max_events=2))
    assert len(yielded) == 2
    assert source.hint_bearing_yielded == 2
    # The source returned right after the 2nd yield; it did not
    # exhaust the remaining 3 hint-bearing messages on the stream.
    assert source.events_scanned == 2
    assert source.last_refusal_reason == REFUSAL_REASON_NONE


def test_scan_budget_independent_of_max_events_equal_one():
    """The bug fixed in Stage 29.3A: with max_events=1 (the Stage
    29.3 orchestrator's hardcoded yield cap) the effective scan
    budget MUST equal max_messages_to_scan, not min(1, N). 50
    non-hint-bearing messages with max_messages_to_scan=50 must
    all be scanned.
    """
    runtime_config = _build_test_runtime_config()
    responses = [
        _make_non_pumpswap_tx_update() for _ in range(50)
    ]
    factory, _captured = _make_factory(responses=responses)
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=50,
        channel_factory=factory,
    )
    list(source.iter_events(max_events=1))
    assert source.events_scanned == 50


# ---------------------------------------------------------------------------
# Invalid runtime max_events
# ---------------------------------------------------------------------------


def test_iter_with_invalid_max_events_yields_nothing():
    runtime_config = _build_test_runtime_config()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=8,
        channel_factory=factory,
    )
    for bad in (0, -1, True):
        yielded = list(source.iter_events(max_events=bad))  # type: ignore[arg-type]
        assert yielded == []
        assert (
            source.last_refusal_reason
            == REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
        )


# ---------------------------------------------------------------------------
# Channel close discipline
# ---------------------------------------------------------------------------


def test_channel_closed_on_no_hint_path():
    runtime_config = _build_test_runtime_config()
    factory, captured = _make_factory(responses=[])
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_config,
        max_messages_to_scan=4,
        channel_factory=factory,
    )
    list(source.iter_events(max_events=1))
    assert captured["channel"].close_called is True
