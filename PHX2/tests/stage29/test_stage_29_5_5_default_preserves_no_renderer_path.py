"""Stage 29.5.5 default-preserves-no-renderer-path pins.

The Stage 29.5.5 opt-in seam adds one optional kwarg
``migration_context_renderer: Optional[object] = None`` to the
Stage 29.3 public entrypoint. When the kwarg is omitted (or
explicitly None), the Stage 29.3 mode-3 path MUST behave
BYTE-EQUIVALENTLY to the pre-Stage-29.5.5 code path: no
side-channel artifact write happens; no Stage 29.5.5 hook is
called; no Stage 29.5.5 module is imported by Stage 29.3
production source.

These tests pin that invariant at four levels:

  * Signature-level: the public entrypoint accepts the new
    kwarg with a default of None and KEYWORD_ONLY kind.
  * AST-level: the Stage 29.3 source contains the conditional
    ``if migration_context_renderer is not None`` guard.
  * Import-level: Stage 29.3 source imports ZERO ``stage29_5_5*``
    module.
  * Behavior-level: calling the entrypoint without the kwarg
    OR with kwarg=None DOES NOT write a side-channel artifact
    file (because no writer is wired); the dispatched-Discord
    count remains 1; the smoke result is DISPATCHED.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

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
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME,
)


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_3_SOURCE: Path = (
    PHX2_ROOT / "stage29" / "stage29_3_tradeable_smoke.py"
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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Signature-level pins
# ---------------------------------------------------------------------------


def test_public_entrypoint_accepts_migration_context_renderer_kwarg() -> None:
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    assert "migration_context_renderer" in sig.parameters, (
        "run_stage29_3_first_private_tradeable_smoke must "
        "expose the 'migration_context_renderer' kwarg at "
        "Stage 29.5.5"
    )
    param = sig.parameters["migration_context_renderer"]
    assert param.default is None, (
        "'migration_context_renderer' kwarg must default to "
        "None so default Stage 29.3 behavior remains byte-"
        "equivalent"
    )
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "'migration_context_renderer' must be keyword-only to "
        "prevent positional-shift breakage of existing callers"
    )


def test_default_value_for_renderer_is_strict_none() -> None:
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    param = sig.parameters["migration_context_renderer"]
    assert param.default is None


# ---------------------------------------------------------------------------
# AST-level pins
# ---------------------------------------------------------------------------


def test_stage_29_3_source_contains_conditional_renderer_guard() -> None:
    """Stage 29.3 must guard the side-channel artifact call
    with BOTH a mode-3 mode check AND a renderer-non-None
    check. Modes 1 (READINESS_ONLY) and 2
    (CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY) MUST NOT call the
    Stage 29.5.5 writer regardless of whether the kwarg is
    supplied.
    """
    src = _read(STAGE29_3_SOURCE)
    assert (
        "migration_context_renderer is not None" in src
    ), (
        "Stage 29.3 mode-3 must guard the Stage 29.5.5 side-"
        "channel artifact call with the renderer-non-None "
        "conditional"
    )
    assert (
        "PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN"
        in src
    ), (
        "Stage 29.3 mode-3 guard must reference "
        "PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN "
        "so the writer is mode-3-only"
    )
    # Find the LAST writer call (the docstring's prose mention
    # appears earlier and is not the guarded site we want).
    call_idx = src.rfind(
        "migration_context_renderer.write_side_channel_artifact(",
    )
    assert call_idx >= 0
    # Search backwards from the call site for the nearest
    # ``if (`` block opener; the guard MUST contain both the
    # mode-3 token AND the renderer-non-None token.
    guard_window_start = src.rfind("if (", 0, call_idx)
    assert guard_window_start >= 0
    guard_window = src[guard_window_start:call_idx]
    assert (
        "PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN"
        in guard_window
    ), (
        "the writer's nearest if-guard must reference the "
        "mode-3 probe-mode token (mode-3-only writer hook)"
    )
    assert (
        "migration_context_renderer is not None" in guard_window
    ), (
        "the writer's nearest if-guard must also gate on "
        "renderer-non-None"
    )


def test_stage_29_3_source_calls_write_side_channel_artifact() -> None:
    src = _read(STAGE29_3_SOURCE)
    assert (
        "write_side_channel_artifact"
        in src
    ), (
        "Stage 29.3 mode-3 must invoke the side-channel "
        "writer's write_side_channel_artifact method"
    )


def test_stage_29_3_source_guards_renderer_call_in_try_except() -> None:
    """The Stage 29.5.5 side-channel write call MUST be inside
    a ``try`` / ``except Exception: pass`` guard so a side-
    channel write failure never affects the dispatch outcome.
    """
    src = _read(STAGE29_3_SOURCE)
    # We can't trivially assert AST structure, but we CAN
    # assert that the textual pattern is present.
    assert (
        "migration_context_renderer.write_side_channel_artifact"
        in src
    )
    # The except clause swallowing Exception must appear after
    # the renderer call (we check the order of substrings).
    call_idx = src.find(
        "migration_context_renderer.write_side_channel_artifact",
    )
    except_idx = src.find(
        "except Exception:", call_idx,
    )
    pass_idx = src.find("pass", except_idx)
    assert (
        call_idx >= 0
        and except_idx > call_idx
        and pass_idx > except_idx
    ), (
        "Stage 29.3 mode-3 must wrap the Stage 29.5.5 side-"
        "channel call in 'try / except Exception: pass'"
    )


# ---------------------------------------------------------------------------
# Import-level pins
# ---------------------------------------------------------------------------


def test_stage_29_3_source_does_not_import_any_stage29_5_5_module() -> None:
    """Stage 29.3 production must remain decoupled from the
    Stage 29.5.5 sub-tree. The writer is supplied to Stage
    29.3 via the opt-in kwarg whose static type is ``object``
    (not a Stage 29.5.5 Protocol), so Stage 29.3 production
    carries ZERO ``stage29_5_5*`` import.
    """
    src = _read(STAGE29_3_SOURCE)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "stage29_5_5" not in mod, (
                f"Stage 29.3 production must not import any "
                f"stage29_5_5* module; offender import: "
                f"{mod!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "stage29_5_5" not in alias.name, (
                    f"Stage 29.3 production must not import "
                    f"any stage29_5_5* module; offender "
                    f"import: {alias.name!r}"
                )


def test_stage_29_3_source_still_does_not_import_any_stage29_5_module() -> None:
    """Stage 29.3 production carried ZERO ``stage29_5*`` import
    at Stage 29.5.4; the Stage 29.5.5 patch must preserve that
    pin (it adds only the renderer kwarg with type ``object``).
    """
    src = _read(STAGE29_3_SOURCE)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "stage29_5" not in mod, (
                f"Stage 29.3 production must not import any "
                f"stage29_5* module; offender import: {mod!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert (
                    "stage29_5" not in alias.name
                ), (
                    f"Stage 29.3 production must not import "
                    f"any stage29_5* module; offender "
                    f"import: {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# Behavior-level pins
# ---------------------------------------------------------------------------
#
# We reuse a minimal subset of the integration-test fakes to
# drive Stage 29.3 mode-3 without the Stage 29.5.5 kwargs and
# verify that:
#   * no side-channel artifact file is written;
#   * the dispatched-Discord count remains 1;
#   * the smoke result is DISPATCHED.


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
            prefix="phx2_stage29_5_5_default_test_",
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


def test_default_kwarg_omitted_writes_no_side_channel_artifact() -> None:
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
        # migration_context_renderer omitted -> None
    )
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert not artifact_path.exists(), (
        "Default Stage 29.3 mode-3 path must NOT write a "
        "Stage 29.5.5 side-channel artifact when the renderer "
        "kwarg is omitted"
    )
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


def test_explicit_none_kwarg_writes_no_side_channel_artifact() -> None:
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
        migration_context_renderer=None,
    )
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert not artifact_path.exists()
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1


# ---------------------------------------------------------------------------
# Mode-3-only side-channel hook pins
# ---------------------------------------------------------------------------
#
# The Stage 29.5.5 side-channel artifact write is wired ONLY for
# mode-3 (PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN).
# Modes 1 (READINESS_ONLY) and 2
# (CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY) do NOT drive Stage 27.6
# candidate assembly, so a Stage 29.5.5 recorder wired into
# those modes has nothing to record; the side-channel writer
# must be skipped entirely for those modes regardless of
# whether the operator passed a writer through the kwarg.


class _CallTrackingWriter:
    """Tiny writer-shaped object used to assert whether the
    Stage 29.3 side-channel hook fired.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def write_side_channel_artifact(
        self,
        *,
        output_dir,
        migration_source,
    ):
        self.calls.append(
            {
                "output_dir": output_dir,
                "migration_source": migration_source,
            }
        )
        return None


class _RaisingIfCalledWriter:
    """Writer that raises if invoked. Used to prove modes 1 / 2
    do not call the hook even when an explicit writer is wired.
    """

    def write_side_channel_artifact(
        self,
        *,
        output_dir,
        migration_source,
    ):
        raise AssertionError(
            "Stage 29.5.5 side-channel writer must NOT be "
            "called outside Stage 29.3 mode-3"
        )


def test_mode_1_does_not_call_migration_context_renderer() -> None:
    """Mode 1 (READINESS_ONLY) does not drive Stage 27.6
    candidate assembly. Passing a Stage 29.5.5 writer through
    ``migration_context_renderer`` MUST be a no-op: the writer
    is never called.
    """
    out = _outside_repo_tmpdir()
    writer = _CallTrackingWriter()
    raising_writer = _RaisingIfCalledWriter()
    # 1a -- counting writer.
    result_a = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=True,
        migration_context_renderer=writer,
    )
    assert writer.calls == [], (
        "Mode 1 (READINESS_ONLY) MUST NOT call the Stage 29.5.5 "
        "side-channel writer; got "
        f"{len(writer.calls)} call(s)"
    )
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()
    # 1b -- writer that raises if called. The Stage 29.3 entry
    # point must not invoke this writer, so no exception
    # escapes (even if the writer's call were caught inside the
    # try/except, the AssertionError below would be raised by
    # _RaisingIfCalledWriter, which the try/except swallows.
    # The decisive pin is that the smoke outcome remains
    # unchanged AND no artifact file is created -- proving the
    # writer was either skipped or its raise was caught and
    # ignored. We pair this with the counting writer above to
    # establish that modes 1 / 2 SKIP the hook entirely).
    out2 = _outside_repo_tmpdir()
    result_b = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out2,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=True,
        migration_context_renderer=raising_writer,
    )
    assert not (
        out2 / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()
    # The smoke result is unchanged across writer kinds.
    assert (
        result_a.tradeable_smoke_outcome
        == result_b.tradeable_smoke_outcome
    )


def test_mode_2_does_not_call_migration_context_renderer() -> None:
    """Mode 2 (CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY) does not
    drive Stage 27.6 candidate assembly either. Passing a
    Stage 29.5.5 writer through ``migration_context_renderer``
    MUST be a no-op: the writer is never called.
    """
    out = _outside_repo_tmpdir()
    writer = _CallTrackingWriter()
    factory = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        runtime_configs=_build_test_runtime_configs(),
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=_FakeBirdeyeHttpTransport(
            bodies_by_path=_build_birdeye_bodies(),
        ),
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_context_renderer=writer,
    )
    assert writer.calls == [], (
        "Mode 2 (CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY) MUST NOT "
        "call the Stage 29.5.5 side-channel writer; got "
        f"{len(writer.calls)} call(s)"
    )
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()
    # Mode 2 result is independently produced; we only assert
    # the writer was skipped, not the mode-2 outcome itself.
    assert result is not None


def test_mode_3_still_calls_migration_context_renderer_when_opted_in() -> None:
    """Mode 3 retains the existing opt-in behavior: when an
    operator passes a writer through ``migration_context_renderer``
    AND ``write_artifacts=True``, the writer is invoked exactly
    once after the Stage 28.9 session completes.
    """
    out = _outside_repo_tmpdir()
    writer = _CallTrackingWriter()
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
        migration_context_renderer=writer,
    )
    assert len(writer.calls) == 1, (
        "Mode 3 MUST call the Stage 29.5.5 side-channel writer "
        "exactly once when the kwarg is supplied; got "
        f"{len(writer.calls)} call(s)"
    )
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
