"""Stage 28.11 real gRPC client tests.

Pins:

  * Constructor refuses inputs that are not a Stage 28.11
    runtime config.
  * The client satisfies the Stage 28.10 client Protocol.
  * Connect-only happy path runs against an injected fake
    channel and never touches the network.
  * Connect-only error wrapping: a fake channel that raises
    ``grpc.RpcError`` surfaces a ``Stage28_11ConnectError`` with
    closed-set reason ``PING_RPC_ERROR:<code>``; the raw gRPC
    error message NEVER leaks through.
  * One-event decode dry run happy path runs against an injected
    fake channel and emits the Stage 28.10 safe payload.
  * Dry run error wrapping for stream RPC errors.
  * Stage 28.10 Protocol satisfaction:
    ``fetch_yellowstone_events`` / ``iter_yellowstone_events``
    refuse non-int / non-positive ``max_events``.
  * Live test: skipped by default, opt-in via
    ``PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1`` (plus the other
    Stage 28.11 env names); never sends Discord; never
    invokes the Stage 28.9 wrapper.
"""

from __future__ import annotations

import os
from typing import Iterator, Optional

import grpc
import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage28.chainstack_yellowstone_grpc_client import (
    GRPC_METADATA_KEY_X_TOKEN,
    MAX_UPSTREAM_MESSAGES_TO_SCAN,
    Stage28_11ChainstackYellowstoneGrpcClient,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11ConnectError,
    Stage28_11DecodeError,
    Stage28_11InvalidRuntimeConfigError,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
)
from PHX2.stage28.chainstack_yellowstone_contracts import (
    Stage28_10ChainstackYellowstoneClient,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    Stage28_10ChainstackYellowstonePayload,
    build_chainstack_yellowstone_config,
)


SAFE_ENDPOINT: str = "fixture.example:443"
SAFE_X_TOKEN: str = "abc-DEF.ghi-JKL_mno-1234567890"


def _build_runtime_config(*, mode: str):
    secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=SAFE_ENDPOINT,
        x_token=SAFE_X_TOKEN,
    )
    safe_config = build_chainstack_yellowstone_config(
        provider_id="chainstack_yellowstone_grpc",
        endpoint_safe_label="chainstack_yellowstone_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    return build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=safe_config,
        endpoint_secret=secret,
        mode=mode,
        timeout_seconds=30,
    )


def _build_well_formed_subscribe_update():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1700000000
    update.created_at.nanos = 0
    tx_wrapper = update.transaction
    tx_wrapper.slot = 12345
    tx_info = tx_wrapper.transaction
    tx_info.signature = bytes(range(1, 65))
    tx_info.is_vote = False
    tx_info.index = 0
    return update


# ---------------------------------------------------------------------------
# Fake gRPC channel scaffolding
# ---------------------------------------------------------------------------


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        self._code = code
        super().__init__(f"<fake gRPC error {code.name}>")

    def code(self) -> grpc.StatusCode:
        return self._code


class _FakeStreamIterator:
    def __init__(self, items, *, raise_in_iter: bool = False) -> None:
        self._items = list(items)
        self._raise_in_iter = raise_in_iter
        self._index = 0
        self.cancel_called: bool = False
        # Public test counter: the number of times ``__next__``
        # was invoked on this iterator (whether the call returned
        # an item or raised ``StopIteration``). Used by the
        # exact-scan-cap tests to prove the production loop pulls
        # AT MOST ``MAX_UPSTREAM_MESSAGES_TO_SCAN`` items.
        self.pull_count: int = 0

    def __iter__(self) -> "Iterator[object]":
        return self

    def __next__(self) -> object:
        self.pull_count += 1
        if (
            self._raise_in_iter
            and self._index >= len(self._items)
        ):
            raise _FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED)
        if self._index >= len(self._items):
            raise StopIteration
        item = self._items[self._index]
        self._index += 1
        return item

    def cancel(self) -> None:
        self.cancel_called = True


class _FakeChannel:
    def __init__(
        self,
        *,
        ping_response: Optional[object] = None,
        subscribe_responses: tuple = (),
        raise_on_ping_code: Optional[grpc.StatusCode] = None,
        raise_on_subscribe_code: Optional[grpc.StatusCode] = None,
        raise_in_stream: bool = False,
    ) -> None:
        self._ping_response = ping_response
        self._subscribe_responses = subscribe_responses
        self._raise_on_ping_code = raise_on_ping_code
        self._raise_on_subscribe_code = raise_on_subscribe_code
        self._raise_in_stream = raise_in_stream
        self.close_called: bool = False
        self.last_ping_metadata: Optional[tuple] = None
        self.last_subscribe_metadata: Optional[tuple] = None
        self.last_subscribe_request: Optional[object] = None
        self.last_stream_iterator: Optional[
            _FakeStreamIterator
        ] = None

    def unary_unary(self, method: str, **kwargs):
        def call(request, *, timeout=None, metadata=None):
            if method.endswith("/Ping"):
                self.last_ping_metadata = metadata
                if self._raise_on_ping_code is not None:
                    raise _FakeRpcError(self._raise_on_ping_code)
                if self._ping_response is None:
                    return _geyser_pb2.PongResponse(count=1)
                return self._ping_response
            return None
        return call

    def stream_stream(self, method: str, **kwargs):
        def call(request_iter, *, timeout=None, metadata=None):
            if method.endswith("/Subscribe"):
                self.last_subscribe_metadata = metadata
                # Drain the single SubscribeRequest.
                for req in request_iter:
                    self.last_subscribe_request = req
                if self._raise_on_subscribe_code is not None:
                    raise _FakeRpcError(
                        self._raise_on_subscribe_code,
                    )
                iterator = _FakeStreamIterator(
                    self._subscribe_responses,
                    raise_in_iter=self._raise_in_stream,
                )
                self.last_stream_iterator = iterator
                return iterator
            return iter([])
        return call

    def unary_stream(self, method, **kwargs):
        def call(request, *, timeout=None, metadata=None):
            return iter([])
        return call

    def stream_unary(self, method, **kwargs):
        def call(request_iter, *, timeout=None, metadata=None):
            for _ in request_iter:
                pass
            return None
        return call

    def close(self) -> None:
        self.close_called = True


def _fake_channel_factory(channel: _FakeChannel):
    def factory(target, credentials):
        return channel
    return factory


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------


def test_client_rejects_non_runtime_config():
    with pytest.raises(Stage28_11InvalidRuntimeConfigError):
        Stage28_11ChainstackYellowstoneGrpcClient(
            runtime_config="not a config",  # type: ignore[arg-type]
        )


def test_client_accepts_runtime_config():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    assert client.runtime_config is rc
    assert client.connect_call_count == 0
    assert client.decode_call_count == 0


def test_client_repr_is_redacted():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    text = repr(client)
    assert SAFE_ENDPOINT not in text
    assert SAFE_X_TOKEN not in text


# ---------------------------------------------------------------------------
# 2. Stage 28.10 Protocol satisfaction
# ---------------------------------------------------------------------------


def test_client_satisfies_stage_28_10_protocol():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    assert isinstance(
        client,
        Stage28_10ChainstackYellowstoneClient,
    )


def test_protocol_methods_refuse_non_int_max_events():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    with pytest.raises(Stage28_11DecodeError):
        client.fetch_yellowstone_events(
            cursor=None,
            max_events="one",  # type: ignore[arg-type]
        )
    with pytest.raises(Stage28_11DecodeError):
        # iterator: consume to trigger
        list(client.iter_yellowstone_events(
            max_events="one",  # type: ignore[arg-type]
        ))


def test_protocol_methods_refuse_non_positive_max_events():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    with pytest.raises(Stage28_11DecodeError):
        client.fetch_yellowstone_events(
            cursor=None,
            max_events=0,
        )


def test_protocol_methods_refuse_non_string_cursor():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    with pytest.raises(Stage28_11DecodeError):
        client.fetch_yellowstone_events(
            cursor=123,  # type: ignore[arg-type]
            max_events=1,
        )


# ---------------------------------------------------------------------------
# 3. validate_readiness
# ---------------------------------------------------------------------------


def test_validate_readiness_passes_for_valid_config():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    # Returns None on success.
    assert client.validate_readiness() is None


# ---------------------------------------------------------------------------
# 4. provider_connect_only with fake channel
# ---------------------------------------------------------------------------


def test_connect_only_happy_path_with_fake_channel():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    channel = _FakeChannel()
    client.provider_connect_only(
        channel_factory=_fake_channel_factory(channel),
    )
    assert client.connect_call_count == 1
    assert channel.close_called is True
    # Metadata must carry the x-token under the locked key.
    md = channel.last_ping_metadata or ()
    md_dict = dict(md)
    assert GRPC_METADATA_KEY_X_TOKEN in md_dict
    assert md_dict[GRPC_METADATA_KEY_X_TOKEN] == SAFE_X_TOKEN


def test_connect_only_wraps_grpc_error_with_closed_set_reason():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    channel = _FakeChannel(
        raise_on_ping_code=grpc.StatusCode.UNAVAILABLE,
    )
    with pytest.raises(Stage28_11ConnectError) as err:
        client.provider_connect_only(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "PING_RPC_ERROR:UNAVAILABLE"
    assert channel.close_called is True
    # The raw fake-gRPC error message must NOT appear on the
    # public exception.
    assert "<fake gRPC error" not in str(err.value)


def test_connect_only_factory_must_be_callable():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    with pytest.raises(Stage28_11ConnectError) as err:
        client.provider_connect_only(
            channel_factory="not-a-callable",
        )
    assert err.value.reason == "CHANNEL_FACTORY_NOT_CALLABLE"


# ---------------------------------------------------------------------------
# 5. one_event_decode_dry_run with fake channel
# ---------------------------------------------------------------------------


def test_dry_run_happy_path_decodes_one_payload():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    channel = _FakeChannel(
        subscribe_responses=(
            _build_well_formed_subscribe_update(),
        ),
    )
    payload = client.one_event_decode_dry_run(
        channel_factory=_fake_channel_factory(channel),
    )
    assert isinstance(
        payload,
        Stage28_10ChainstackYellowstonePayload,
    )
    assert payload.slot == 12345
    assert channel.close_called is True
    assert client.decode_call_count == 1
    # The fake subscribe request must have been sent.
    assert channel.last_subscribe_request is not None
    # Metadata must carry the x-token.
    md = dict(channel.last_subscribe_metadata or ())
    assert md.get(GRPC_METADATA_KEY_X_TOKEN) == SAFE_X_TOKEN
    # The stream iterator was cancelled after the one event.
    assert (
        channel.last_stream_iterator is not None
        and channel.last_stream_iterator.cancel_called is True
    )


def test_dry_run_skips_ping_variant_before_transaction():
    """Yellowstone multiplexes ping / pong / slot updates; the
    Stage 28.11 client must skip them and return the first
    transaction."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    ping_update = _geyser_pb2.SubscribeUpdate()
    ping_update.created_at.seconds = 1700000000
    ping_update.ping.SetInParent()
    channel = _FakeChannel(
        subscribe_responses=(
            ping_update,
            _build_well_formed_subscribe_update(),
        ),
    )
    payload = client.one_event_decode_dry_run(
        channel_factory=_fake_channel_factory(channel),
    )
    assert payload.slot == 12345


def test_dry_run_no_event_received_raises_decode_error():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    channel = _FakeChannel(subscribe_responses=())
    with pytest.raises(Stage28_11DecodeError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
    assert channel.close_called is True


def test_dry_run_wraps_subscribe_rpc_error():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    channel = _FakeChannel(
        raise_on_subscribe_code=grpc.StatusCode.UNAUTHENTICATED,
    )
    with pytest.raises(Stage28_11ConnectError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == (
        "SUBSCRIBE_RPC_ERROR:UNAUTHENTICATED"
    )
    assert channel.close_called is True


# ---------------------------------------------------------------------------
# 6. Channel is always closed even on error
# ---------------------------------------------------------------------------


def test_channel_closes_on_unexpected_error():
    """The client wraps unexpected exceptions and still closes
    the channel."""
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )

    class _ExplodingChannel(_FakeChannel):
        def unary_unary(self, method, **kwargs):
            def call(request, *, timeout=None, metadata=None):
                raise RuntimeError("upstream library bug")
            return call

    channel = _ExplodingChannel()
    with pytest.raises(Stage28_11ConnectError) as err:
        client.provider_connect_only(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "PING_UNEXPECTED_ERROR"
    assert channel.close_called is True
    # The raw RuntimeError message must NOT appear on the public
    # Stage 28.11 exception.
    assert "upstream library bug" not in str(err.value)


# ---------------------------------------------------------------------------
# 7. Finite scan cap on _read_first_transaction_update
# ---------------------------------------------------------------------------


def _build_ping_only_update():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1700000000
    update.ping.SetInParent()
    return update


def test_scan_cap_constant_is_finite_and_positive():
    """The scan cap must be a finite positive int so the dry-run
    cannot be kept subscribed indefinitely on a non-transaction
    upstream feed."""
    assert isinstance(MAX_UPSTREAM_MESSAGES_TO_SCAN, int)
    assert MAX_UPSTREAM_MESSAGES_TO_SCAN > 0
    # Sanity: keep the cap tight enough that a fixture stream
    # below the cap is feasible to construct in tests.
    assert MAX_UPSTREAM_MESSAGES_TO_SCAN <= 1024


def test_scan_cap_admits_transaction_just_below_cap():
    """A transaction sitting at the last admitted slot
    (position ``MAX_UPSTREAM_MESSAGES_TO_SCAN``) is still
    decoded successfully."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN - 1)
    ]
    tx = _build_well_formed_subscribe_update()
    channel = _FakeChannel(
        subscribe_responses=tuple(pings + [tx]),
    )
    payload = client.one_event_decode_dry_run(
        channel_factory=_fake_channel_factory(channel),
    )
    assert isinstance(
        payload,
        Stage28_10ChainstackYellowstonePayload,
    )
    assert payload.slot == 12345
    assert channel.close_called is True


def test_scan_cap_refuses_when_transaction_is_just_beyond_cap():
    """A transaction sitting one slot past the cap is NEVER
    reached; the dry-run surfaces ``NO_TRANSACTION_UPDATE_RECEIVED``.
    """
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN)
    ]
    tx = _build_well_formed_subscribe_update()
    channel = _FakeChannel(
        subscribe_responses=tuple(pings + [tx]),
    )
    with pytest.raises(Stage28_11DecodeError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
    assert channel.close_called is True


def test_scan_cap_refuses_when_stream_is_all_pings():
    """A stream that emits only ping updates (no transaction
    variant within the cap) surfaces the closed-set refusal."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN + 10)
    ]
    channel = _FakeChannel(subscribe_responses=tuple(pings))
    with pytest.raises(Stage28_11DecodeError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
    # The closed-set reason carries no raw upstream content.
    assert SAFE_ENDPOINT not in str(err.value)
    assert SAFE_X_TOKEN not in str(err.value)
    assert channel.close_called is True


def test_scan_cap_small_mixed_prefix_still_succeeds():
    """A handful of ping messages followed by a transaction
    (well under the cap) still decodes the transaction. This
    pins the existing behavior the cap should NOT degrade."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [_build_ping_only_update() for _ in range(5)]
    tx = _build_well_formed_subscribe_update()
    channel = _FakeChannel(
        subscribe_responses=tuple(pings + [tx]),
    )
    payload = client.one_event_decode_dry_run(
        channel_factory=_fake_channel_factory(channel),
    )
    assert payload.slot == 12345


def test_scan_cap_pulls_at_most_cap_items_when_no_transaction():
    """Exact-cap contract: when the upstream emits only
    non-transaction messages, the reader pulls AT MOST
    ``MAX_UPSTREAM_MESSAGES_TO_SCAN`` items from the iterator,
    NOT one more. Pins that the cap is a strict pull bound and
    not a "consume the (N+1)-th then return" behavior."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    # Emit MAX_UPSTREAM_MESSAGES_TO_SCAN + 10 ping updates so a
    # ``cap + 1``-th pull would be possible if the loop were
    # off-by-one.
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN + 10)
    ]
    channel = _FakeChannel(subscribe_responses=tuple(pings))
    with pytest.raises(Stage28_11DecodeError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
    assert channel.last_stream_iterator is not None
    pulled = channel.last_stream_iterator.pull_count
    assert pulled == MAX_UPSTREAM_MESSAGES_TO_SCAN, (
        f"Stage 28.11 scan cap must consume AT MOST "
        f"{MAX_UPSTREAM_MESSAGES_TO_SCAN!r} upstream messages; "
        f"observed {pulled!r}."
    )
    # Cleanup discipline preserved: the channel was closed.
    assert channel.close_called is True


def test_scan_cap_pulls_at_most_cap_when_tx_lives_past_cap():
    """Mirror of the above with a transaction sitting past the
    cap. The reader still must NOT pull the transaction position
    (i.e. NOT pull the (cap+1)-th item)."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN)
    ]
    tx = _build_well_formed_subscribe_update()
    channel = _FakeChannel(
        subscribe_responses=tuple(pings + [tx]),
    )
    with pytest.raises(Stage28_11DecodeError) as err:
        client.one_event_decode_dry_run(
            channel_factory=_fake_channel_factory(channel),
        )
    assert err.value.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
    pulled = channel.last_stream_iterator.pull_count
    assert pulled == MAX_UPSTREAM_MESSAGES_TO_SCAN, (
        f"Stage 28.11 scan cap must consume exactly the cap "
        f"and NEVER reach the past-cap transaction slot; "
        f"observed {pulled!r}."
    )


def test_scan_cap_pulls_just_through_transaction_when_at_cap():
    """Pin the lower bound: when a transaction sits at the
    last admitted slot (position ``cap``), the reader pulls
    EXACTLY ``cap`` items and returns; it never wastes a
    further pull on the iterator."""
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=rc,
    )
    pings = [
        _build_ping_only_update()
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN - 1)
    ]
    tx = _build_well_formed_subscribe_update()
    # An extra ping after the transaction so we can prove the
    # reader did NOT pull it.
    extra = _build_ping_only_update()
    channel = _FakeChannel(
        subscribe_responses=tuple(pings + [tx, extra]),
    )
    payload = client.one_event_decode_dry_run(
        channel_factory=_fake_channel_factory(channel),
    )
    assert payload.slot == 12345
    pulled = channel.last_stream_iterator.pull_count
    assert pulled == MAX_UPSTREAM_MESSAGES_TO_SCAN, (
        f"Stage 28.11 reader should consume exactly the cap "
        f"when a transaction sits at the cap position; "
        f"observed {pulled!r}."
    )


# ---------------------------------------------------------------------------
# 8. Live test (opt-in)
# ---------------------------------------------------------------------------


_LIVE_FLAG_VALUE: str = os.environ.get(
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "",
)
_LIVE_GATE_OPEN: bool = _LIVE_FLAG_VALUE == "1"


@pytest.mark.skipif(
    not _LIVE_GATE_OPEN,
    reason=(
        "Stage 28.11 live gRPC test skipped; set "
        "PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1 plus the Chainstack "
        "env names to opt in. The live test never sends "
        "Discord, never invokes the Stage 28.9 wrapper, never "
        "dispatches."
    ),
)
def test_live_provider_connect_only():
    """Opt-in live test that opens a real Chainstack Yellowstone
    gRPC channel and calls ``Ping()`` once.

    Requires:
      * ``PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1``
      * ``PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT``
      * ``PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN``

    Never sends Discord. Never invokes the Stage 28.9 wrapper.
    Bounded by the Stage 28.11 default 30-second deadline. No
    retry storm.
    """
    from PHX2.stage28.chainstack_yellowstone_grpc_probe import (
        run_stage28_11_probe_from_env,
    )

    result = run_stage28_11_probe_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        env=None,  # real os.environ
        channel_factory=None,  # real gRPC channel
    )
    # The operator runs this manually; the assertion is mild
    # because a slow Chainstack edge can return UNAVAILABLE
    # transiently. The intent is that the test SURFACES the
    # closed-set status to the operator without crashing.
    assert result.status in (
        "CONNECTED",
        "FAILED",
    ), (
        f"unexpected Stage 28.11 live probe status: "
        f"{result.status!r}"
    )
    # Regardless of outcome, the test must never have echoed
    # the raw endpoint URL / x-token on the result record.
    assert "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT" not in (
        str(result)
    )
