"""Stage 28.11 probe orchestrator tests.

Pins:

  * ``mode=READINESS_ONLY`` returns READY without touching the
    network and without setting ``handoff_ready``.
  * ``mode=PROVIDER_CONNECT_ONLY`` and
    ``mode=ONE_EVENT_DECODE_DRY_RUN`` both refuse to run when
    the live-gate flag is not set; the closed-set refusal
    reason is ``LIVE_FLAG_NOT_SET``.
  * ``mode=PROVIDER_CONNECT_ONLY`` happy path returns
    ``CONNECTED`` against an injected fake channel; the probe
    NEVER sends Discord and NEVER calls the Stage 28.9 wrapper.
  * ``mode=ONE_EVENT_DECODE_DRY_RUN`` happy path returns
    ``DECODED`` with ``decoded_payload`` populated and
    ``handoff_ready=True`` only when all three sub-steps
    succeed.
  * Mode dispatch errors:
    - rogue mode -> ``MODE_INVALID``,
    - connect failure -> ``CONNECT_FAILED``,
    - decode no-event -> ``NO_EVENT_RECEIVED``,
    - decode other refusal -> ``DECODE_FAILED``.
  * ``run_stage28_11_probe_from_env``:
    - rejects when env did not pass readiness,
    - happy path drives readiness + probe with injected fake
      channel,
    - the live-gate flag from env passes through into the
      probe.
"""

from __future__ import annotations

from typing import Iterator, Optional

import grpc
import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_DECODED,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_READY,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_ENDPOINT_MISSING,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_EVENT_RECEIVED,
    REFUSAL_REASON_X_TOKEN_MISSING,
    Stage28_10ChainstackYellowstonePayload,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
)
from PHX2.stage28.chainstack_yellowstone_grpc_probe import (
    run_stage28_11_probe,
    run_stage28_11_probe_from_env,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    ENV_NAME_ALLOW_LIVE_GRPC,
    ENV_NAME_GRPC_ENDPOINT,
    ENV_NAME_X_TOKEN,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
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
# Reusable fake channel scaffolding (shared shape with the
# client test).
# ---------------------------------------------------------------------------


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        self._code = code
        super().__init__(f"<fake gRPC error {code.name}>")

    def code(self) -> grpc.StatusCode:
        return self._code


class _FakeStreamIterator:
    def __init__(self, items) -> None:
        self._items = list(items)
        self._index = 0
        self.cancel_called = False

    def __iter__(self):
        return self

    def __next__(self):
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
        subscribe_responses: tuple = (),
        raise_on_ping_code: Optional[grpc.StatusCode] = None,
        raise_on_subscribe_code: Optional[grpc.StatusCode] = None,
    ) -> None:
        self._subscribe_responses = subscribe_responses
        self._raise_on_ping_code = raise_on_ping_code
        self._raise_on_subscribe_code = raise_on_subscribe_code
        self.close_called = False

    def unary_unary(self, method, **kwargs):
        def call(request, *, timeout=None, metadata=None):
            if method.endswith("/Ping"):
                if self._raise_on_ping_code is not None:
                    raise _FakeRpcError(self._raise_on_ping_code)
                return _geyser_pb2.PongResponse(count=1)
            return None
        return call

    def stream_stream(self, method, **kwargs):
        def call(request_iter, *, timeout=None, metadata=None):
            if method.endswith("/Subscribe"):
                for _ in request_iter:
                    pass
                if self._raise_on_subscribe_code is not None:
                    raise _FakeRpcError(
                        self._raise_on_subscribe_code,
                    )
                return _FakeStreamIterator(
                    self._subscribe_responses,
                )
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

    def close(self):
        self.close_called = True


def _factory(channel):
    def f(target, credentials):
        return channel
    return f


# ---------------------------------------------------------------------------
# 1. readiness-only
# ---------------------------------------------------------------------------


def test_readiness_only_returns_ready_without_network():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_READINESS_ONLY,
        live_flag_set=False,
    )
    assert result.status == PROBE_STATUS_READY
    assert result.refusal_reason == REFUSAL_REASON_NONE
    assert result.ready is True
    assert result.connected is False
    assert result.decoded is False
    assert result.handoff_ready is False
    assert result.events_received == 0


def test_readiness_only_ignores_live_flag():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_READINESS_ONLY,
        live_flag_set=True,
    )
    assert result.status == PROBE_STATUS_READY
    # ``handoff_ready`` stays False for readiness-only even when
    # the live flag is set; the operator must escalate to
    # connect-only / dry-run modes to advance.
    assert result.handoff_ready is False


# ---------------------------------------------------------------------------
# 2. rogue mode
# ---------------------------------------------------------------------------


def test_rogue_mode_returns_failed_with_mode_invalid():
    rc = _build_runtime_config(mode=MODE_READINESS_ONLY)
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode="ROGUE_MODE",
        live_flag_set=True,
    )
    assert result.status == PROBE_STATUS_FAILED
    assert result.refusal_reason == REFUSAL_REASON_MODE_INVALID
    assert result.handoff_ready is False


# ---------------------------------------------------------------------------
# 3. provider-connect-only
# ---------------------------------------------------------------------------


def test_connect_only_without_live_flag_returns_failed():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_PROVIDER_CONNECT_ONLY,
        live_flag_set=False,
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )
    assert result.ready is True
    assert result.connected is False
    assert result.handoff_ready is False


def test_connect_only_happy_path_with_fake_channel():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    channel = _FakeChannel()
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_PROVIDER_CONNECT_ONLY,
        live_flag_set=True,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_CONNECTED
    assert result.refusal_reason == REFUSAL_REASON_NONE
    assert result.ready is True
    assert result.connected is True
    assert result.decoded is False
    assert result.handoff_ready is False
    assert channel.close_called is True


def test_connect_only_connect_failure_returns_failed():
    rc = _build_runtime_config(
        mode=MODE_PROVIDER_CONNECT_ONLY,
    )
    channel = _FakeChannel(
        raise_on_ping_code=grpc.StatusCode.UNAVAILABLE,
    )
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_PROVIDER_CONNECT_ONLY,
        live_flag_set=True,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_CONNECT_FAILED
    )


# ---------------------------------------------------------------------------
# 4. one-event decode dry run
# ---------------------------------------------------------------------------


def test_dry_run_without_live_flag_returns_failed():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        live_flag_set=False,
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )


def test_dry_run_happy_path_with_fake_channel():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    channel = _FakeChannel(
        subscribe_responses=(
            _build_well_formed_subscribe_update(),
        ),
    )
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        live_flag_set=True,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_DECODED
    assert result.refusal_reason == REFUSAL_REASON_NONE
    assert result.ready is True
    assert result.connected is True
    assert result.decoded is True
    assert result.handoff_ready is True
    assert result.events_received == 1
    assert isinstance(
        result.decoded_payload,
        Stage28_10ChainstackYellowstonePayload,
    )
    assert result.decoded_payload.slot == 12345


def test_dry_run_no_event_returns_no_event_received():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    channel = _FakeChannel(subscribe_responses=())
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        live_flag_set=True,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_NO_EVENT_RECEIVED
    )
    assert result.connected is True
    assert result.decoded is False
    assert result.handoff_ready is False


def test_dry_run_subscribe_failure_returns_connect_failed():
    rc = _build_runtime_config(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
    )
    channel = _FakeChannel(
        raise_on_subscribe_code=grpc.StatusCode.UNAUTHENTICATED,
    )
    result = run_stage28_11_probe(
        runtime_config=rc,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        live_flag_set=True,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_FAILED
    # A subscribe stream open failure surfaces as a Stage
    # 28.11 ConnectError -> CONNECT_FAILED at the probe layer.
    assert (
        result.refusal_reason == REFUSAL_REASON_CONNECT_FAILED
    )


# ---------------------------------------------------------------------------
# 5. run_stage28_11_probe_from_env
# ---------------------------------------------------------------------------


def test_probe_from_env_returns_failed_when_readiness_refuses():
    env = {ENV_NAME_X_TOKEN: SAFE_X_TOKEN}  # endpoint missing
    result = run_stage28_11_probe_from_env(
        mode=MODE_READINESS_ONLY,
        env=env,
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_ENDPOINT_MISSING
    )
    assert result.handoff_ready is False


def test_probe_from_env_readiness_only_passes_when_env_ready():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
    }
    result = run_stage28_11_probe_from_env(
        mode=MODE_READINESS_ONLY,
        env=env,
    )
    assert result.status == PROBE_STATUS_READY


def test_probe_from_env_connect_only_with_fake_channel():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC: "1",
    }
    channel = _FakeChannel()
    result = run_stage28_11_probe_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        env=env,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_CONNECTED
    assert channel.close_called is True


def test_probe_from_env_connect_only_without_live_flag_fails():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        # ALLOW_LIVE_GRPC not set
    }
    channel = _FakeChannel()
    result = run_stage28_11_probe_from_env(
        mode=MODE_PROVIDER_CONNECT_ONLY,
        env=env,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_FAILED
    assert (
        result.refusal_reason == REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )


def test_probe_from_env_dry_run_handoff_ready():
    env = {
        ENV_NAME_GRPC_ENDPOINT: SAFE_ENDPOINT,
        ENV_NAME_X_TOKEN: SAFE_X_TOKEN,
        ENV_NAME_ALLOW_LIVE_GRPC: "1",
    }
    channel = _FakeChannel(
        subscribe_responses=(
            _build_well_formed_subscribe_update(),
        ),
    )
    result = run_stage28_11_probe_from_env(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        env=env,
        channel_factory=_factory(channel),
    )
    assert result.status == PROBE_STATUS_DECODED
    assert result.handoff_ready is True
    assert result.events_received == 1
    assert isinstance(
        result.decoded_payload,
        Stage28_10ChainstackYellowstonePayload,
    )


def test_probe_from_env_rogue_mode_fails():
    result = run_stage28_11_probe_from_env(
        mode="ROGUE_MODE",
        env={},
    )
    assert result.status == PROBE_STATUS_FAILED
    assert result.refusal_reason == REFUSAL_REASON_MODE_INVALID


# ---------------------------------------------------------------------------
# 6. Stage 28.11 probe NEVER imports / wires the Stage 28.9
#    wrapper
# ---------------------------------------------------------------------------


def test_probe_module_does_not_import_stage_28_9_adapter():
    """The Stage 28.11 probe module must NOT import the Stage
    28.9 adapter / transport modules. Stage 28.11 is bounded to
    readiness / connect / decode; the Stage 28.9 wrapper is
    Stage 28.12 territory."""
    import ast
    import pathlib

    src = pathlib.Path(
        __file__,
    ).resolve().parent.parent.parent / "stage28" / (
        "chainstack_yellowstone_grpc_probe.py"
    )
    tree = ast.parse(src.read_text(encoding="utf-8"))
    forbidden = (
        "PHX2.stage28.live_provider_session_adapter",
        "PHX2.stage28.live_provider_session_transport",
        "PHX2.stage28.live_provider_session_models",
        "PHX2.stage28.bounded_private_session_runner",
        "PHX2.stage28.audited_http_transport",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden, (
                f"Stage 28.11 probe imports forbidden Stage 28.9 "
                f"surface: {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, (
                    f"Stage 28.11 probe imports forbidden Stage "
                    f"28.9 surface: {alias.name!r}"
                )
