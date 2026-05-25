"""Stage 29.3 hint-aware Chainstack Yellowstone event source.

The single Stage 29.3 surface that opens a real Chainstack
Yellowstone gRPC channel, narrows the upstream subscription to
the PumpSwap AMM program (the same filter Stage 29.1 uses),
reads at most ``max_events`` ``SubscribeUpdate`` messages,
decodes each transaction-variant message via the Stage 29.1
hint-aware decoder, and yields exactly the hint-bearing
``Stage28_10NormalizedEvent`` records the Stage 28.9 wrapper +
Stage 27 chain need to produce a real tradeable private ping.

The event source structurally satisfies the existing Stage 28.9
``Stage28_9ProviderEventSource`` Protocol via its
``iter_events(max_events)`` method, so the Stage 28.9
``run_stage28_9_live_provider_session`` orchestrator can drive
this source without any Stage 28.9 production edit.

The source NEVER:

  * sends a Discord message,
  * sends a Telegram message,
  * sends an X / social message,
  * touches a wallet / private-key / signer surface,
  * sizes / executes a trade,
  * touches Stage 26 enforcement,
  * starts a daemon / watchdog / autorestart loop,
  * reads any env name (the Stage 28.11 readiness module owns
    the only env-read boundary for the Chainstack chain; the
    Stage 29.3 caller hands this source a pre-built Stage 28.11
    runtime-config record),
  * persists an artifact on its own (the Stage 29.3 artifact
    writer owns persistence),
  * surfaces the upstream Stage 29.1 PumpSwap probe failure
    pattern unchanged — instead, the source surfaces failures as
    an empty iterator + sets a closed-set last-refusal-reason
    attribute so the Stage 29.3 orchestrator can inspect why no
    hint-bearing event was yielded.

This module is the ONLY Stage 29.3 production file allowed to
import ``grpc`` and the generated Yellowstone protobuf stubs.
Every other Stage 29.3 production module stays gRPC-free.

This module imports:

  * stdlib (``contextlib`` / ``typing``),
  * ``grpc`` (the runtime gRPC channel layer),
  * ``PHX2.proto.stage28_11._generated.geyser_pb2`` /
    ``geyser_pb2_grpc`` (the generated Yellowstone stubs),
  * ``PHX2.stage28.chainstack_yellowstone_event_source`` (the
    Stage 28.10 ``project_payload_to_normalized_event`` helper),
  * ``PHX2.stage28.chainstack_yellowstone_grpc_models`` (the
    Stage 28.11 runtime-config + endpoint-secret types),
  * ``PHX2.stage28.chainstack_yellowstone_grpc_decode`` (the
    Stage 28.11 baseline decode-error type, surfaced when the
    upstream message fails the baseline shape contract),
  * ``PHX2.stage28.chainstack_yellowstone_models`` (the Stage
    28.10 payload + normalized-event types),
  * ``PHX2.stage29.pumpswap_hint_aware_decoder`` (the Stage 29.1
    hint-aware decoder + ``is_hint_bearing_payload`` predicate),
  * ``PHX2.stage29.pumpswap_program_constants`` (the PumpSwap
    program id).

It does NOT import:

  * Stage 21-27 production code beyond the indirect Stage 27.3
    ``NormalizedEventLike`` Protocol satisfied structurally by
    ``Stage28_10NormalizedEvent``,
  * Stage 28.0-28.9 dispatch surfaces (the source is upstream of
    Stage 28.9; the Stage 28.9 wrapper consumes the iterator),
  * Stage 29.2 / Stage 29.3 production modules,
  * any Discord / Telegram / X / wallet / trading / dotenv /
    keyring library,
  * ``os`` / the process environment.

Discipline:

  * No env reads. The runtime-config is constructed by the
    unchanged Stage 28.11 readiness layer
    (``build_runtime_config_from_env``) and passed in by the
    Stage 29.3 orchestrator.
  * Every gRPC call carries the runtime-config's finite
    deadline.
  * The channel closes deterministically on every exit path.
  * Raw gRPC error tracebacks NEVER leak; the source catches
    ``grpc.RpcError`` and records a closed-set refusal token.
  * The raw endpoint URL and raw x-token NEVER appear on any
    public attribute, ``__repr__``, exception, log line, or
    artifact; they are read from the runtime-config's private
    secret subobject only at channel-create / metadata-attach
    time.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import grpc

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
    geyser_pb2_grpc as _geyser_pb2_grpc,
)
from PHX2.stage28.chainstack_yellowstone_event_source import (
    project_payload_to_normalized_event,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    Stage28_11DecodeError as _Stage28_11DecodeError,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstonePayload,
    Stage28_10InvalidNormalizedEventError,
    Stage28_10InvalidPayloadError,
    Stage28_10NormalizedEvent,
)
from PHX2.stage29.pumpswap_hint_aware_decoder import (
    decode_subscribe_update_with_pumpswap_hints,
    is_hint_bearing_payload,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
)


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


# gRPC metadata key for the Chainstack Yellowstone x-token.
# Pinned identically to the Stage 28.11 / Stage 29.1 boundary.
GRPC_METADATA_KEY_X_TOKEN: str = "x-token"


# Stage 29.3 filter entry name inside ``SubscribeRequest.transactions``.
# Distinctive from the Stage 28.11 ``stage28_11_dry_run`` and the
# Stage 29.1 ``stage29_1_pumpswap`` names so server-side audit logs
# can attribute each substage's traffic separately.
STAGE29_3_TRANSACTION_FILTER_NAME: str = "stage29_3_pumpswap"


# Default cap on the number of upstream ``SubscribeUpdate``
# messages the hint-aware source scans while searching for the
# first hint-bearing transaction. Mirrors the Stage 29.1 probe
# default; callers may pass a different value via
# ``max_messages_to_scan``.
DEFAULT_MAX_MESSAGES_TO_SCAN: int = 64


# ---------------------------------------------------------------------------
# Closed-set refusal reason (mirrors a subset of the Stage 29.3
# tradeable-smoke refusal reasons; defined here as plain strings so
# the source has no test-cycle import dependency on smoke_models.py)
# ---------------------------------------------------------------------------


REFUSAL_REASON_NONE: str = "NONE"
REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID: str = (
    "MAX_MESSAGES_TO_SCAN_INVALID"
)
REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE: str = (
    "CHANNEL_FACTORY_NOT_CALLABLE"
)
REFUSAL_REASON_SUBSCRIBE_FAILED: str = "SUBSCRIBE_FAILED"
REFUSAL_REASON_STREAM_ERROR: str = "STREAM_ERROR"
REFUSAL_REASON_DECODE_FAILED: str = "DECODE_FAILED"
REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED: str = (
    "NO_HINT_BEARING_TRANSACTION_RECEIVED"
)
REFUSAL_REASON_RUNTIME_CONFIG_INVALID: str = (
    "RUNTIME_CONFIG_INVALID"
)


# ---------------------------------------------------------------------------
# Subscribe request builder
# ---------------------------------------------------------------------------


def build_pumpswap_subscribe_request() -> object:
    """Build a Yellowstone ``SubscribeRequest`` that narrows the
    upstream stream to PumpSwap AMM transactions only.

    Pure / deterministic. The request:

      * names a single transaction filter
        (``STAGE29_3_TRANSACTION_FILTER_NAME``) whose
        ``account_include`` list contains exactly the PumpSwap
        program id,
      * sets ``vote = False``,
      * sets ``failed = False``,
      * sets ``commitment = CONFIRMED``.

    No other filter axes (slots / accounts / blocks / entries)
    are touched.
    """
    request = _geyser_pb2.SubscribeRequest()
    tx_filter = request.transactions[
        STAGE29_3_TRANSACTION_FILTER_NAME
    ]
    tx_filter.account_include.append(PUMPSWAP_PROGRAM_ID)
    tx_filter.vote = False
    tx_filter.failed = False
    request.commitment = _geyser_pb2.CONFIRMED
    return request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@contextmanager
def _open_channel(
    runtime_config: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    channel_factory: Optional[object],
) -> Iterator[object]:
    """Yield a gRPC channel for the source's iteration.

    Default factory builds a real ``grpc.secure_channel`` with
    TLS credentials. Tests pass an explicit ``channel_factory``
    callable that takes ``(target, credentials)`` and returns a
    fake channel; the context manager always closes the channel
    on exit, even when the body raised.
    """
    target = (
        runtime_config.endpoint_secret
        .get_endpoint_url_for_internal_use()
    )
    if channel_factory is None:
        channel = grpc.secure_channel(
            target,
            grpc.ssl_channel_credentials(),
        )
    else:
        channel = channel_factory(
            target,
            grpc.ssl_channel_credentials(),
        )
    try:
        yield channel
    finally:
        close_method = getattr(channel, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                # Cleanup is best-effort; never raise from the
                # context manager exit so the caller's original
                # exception is preserved.
                pass


def _build_metadata(
    runtime_config: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
) -> tuple[tuple[str, str], ...]:
    """Construct the metadata tuple gRPC attaches to the call.

    The x-token is read just-in-time from the runtime-config's
    private secret subobject; the tuple is small (one entry) and
    local to the call -- no copy persists.
    """
    token = (
        runtime_config.endpoint_secret
        .get_x_token_for_internal_use()
    )
    return ((GRPC_METADATA_KEY_X_TOKEN, token),)


# ---------------------------------------------------------------------------
# Stage 29.3 hint-aware event source
# ---------------------------------------------------------------------------


class Stage29_3HintAwareChainstackEventSource:
    """Stage 29.3 hint-aware Chainstack Yellowstone event source.

    Construction:

      * ``runtime_config`` -- a Stage 28.11 runtime-config
        constructed via the unchanged Stage 28.11 readiness layer
        (``build_runtime_config_from_env``). The source never
        builds the runtime-config itself; Stage 29.3 introduces
        no second env-read site.
      * ``max_messages_to_scan`` -- optional positive ``int`` cap
        on how many upstream ``SubscribeUpdate`` messages the
        source consumes per iteration. Defaults to
        ``DEFAULT_MAX_MESSAGES_TO_SCAN`` (64).
      * ``channel_factory`` -- optional ``(target, credentials)
        -> channel`` callable. ``None`` uses the production
        ``grpc.secure_channel``. Non-callable values cause the
        source's iterator to yield nothing and record
        ``CHANNEL_FACTORY_NOT_CALLABLE``.

    The source's ``iter_events(max_events)`` method yields up to
    ``max_events`` hint-bearing ``Stage28_10NormalizedEvent``
    records while scanning at most ``max_messages_to_scan``
    upstream ``SubscribeUpdate`` messages. Non-hint-bearing
    messages (ping / slot / block / non-PumpSwap or
    baseline-shape transactions) do NOT consume the
    ``max_events`` yield budget; they only consume the
    ``max_messages_to_scan`` scan budget. The source NEVER:

      * fabricates a normalized event,
      * yields a baseline (hint-None) payload,
      * raises a ``grpc.RpcError`` at the boundary,
      * leaks the raw endpoint URL / x-token on any record,
        exception, or attribute.

    The source's ``last_refusal_reason`` attribute carries a
    closed-set token describing why iteration ended (``NONE`` when
    a hint-bearing event was yielded, otherwise one of the
    ``REFUSAL_REASON_*`` tokens above).
    """

    def __init__(
        self,
        *,
        runtime_config: (
            Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
        ),
        max_messages_to_scan: int = DEFAULT_MAX_MESSAGES_TO_SCAN,
        channel_factory: Optional[object] = None,
    ) -> None:
        if not isinstance(
            runtime_config,
            Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
        ):
            self._runtime_config: Optional[
                Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
            ] = None
            self._max_messages_to_scan: int = (
                DEFAULT_MAX_MESSAGES_TO_SCAN
            )
            self._channel_factory: Optional[object] = None
            self._init_refusal_reason: Optional[str] = (
                REFUSAL_REASON_RUNTIME_CONFIG_INVALID
            )
            self._last_refusal_reason: str = (
                REFUSAL_REASON_RUNTIME_CONFIG_INVALID
            )
            self._iter_count: int = 0
            self._events_scanned: int = 0
            self._transactions_scanned: int = 0
            self._hint_bearing_yielded: int = 0
            return

        if (
            isinstance(max_messages_to_scan, bool)
            or not isinstance(max_messages_to_scan, int)
            or max_messages_to_scan <= 0
        ):
            self._runtime_config = runtime_config
            self._max_messages_to_scan = (
                DEFAULT_MAX_MESSAGES_TO_SCAN
            )
            self._channel_factory = None
            self._init_refusal_reason = (
                REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
            )
            self._last_refusal_reason = (
                REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
            )
            self._iter_count = 0
            self._events_scanned = 0
            self._transactions_scanned = 0
            self._hint_bearing_yielded = 0
            return

        if channel_factory is not None and not callable(
            channel_factory,
        ):
            self._runtime_config = runtime_config
            self._max_messages_to_scan = max_messages_to_scan
            self._channel_factory = None
            self._init_refusal_reason = (
                REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE
            )
            self._last_refusal_reason = (
                REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE
            )
            self._iter_count = 0
            self._events_scanned = 0
            self._transactions_scanned = 0
            self._hint_bearing_yielded = 0
            return

        self._runtime_config = runtime_config
        self._max_messages_to_scan = max_messages_to_scan
        self._channel_factory = channel_factory
        self._init_refusal_reason = None
        self._last_refusal_reason = REFUSAL_REASON_NONE
        self._iter_count = 0
        self._events_scanned = 0
        self._transactions_scanned = 0
        self._hint_bearing_yielded = 0

    # ------------------------------------------------------------------
    # Public read-only observers
    # ------------------------------------------------------------------

    @property
    def init_refusal_reason(self) -> Optional[str]:
        """Return the construction-time refusal reason, or ``None``
        when construction succeeded. Tests + the orchestrator use
        this to short-circuit when the runtime-config / bound /
        channel-factory triggered an init-time refusal.
        """
        return self._init_refusal_reason

    @property
    def last_refusal_reason(self) -> str:
        """Return the closed-set refusal reason from the most
        recent iteration. ``NONE`` on success; otherwise one of
        the ``REFUSAL_REASON_*`` tokens.
        """
        return self._last_refusal_reason

    @property
    def iter_count(self) -> int:
        return self._iter_count

    @property
    def events_scanned(self) -> int:
        return self._events_scanned

    @property
    def transactions_scanned(self) -> int:
        return self._transactions_scanned

    @property
    def hint_bearing_yielded(self) -> int:
        return self._hint_bearing_yielded

    # ------------------------------------------------------------------
    # Stage 28.9 ProviderEventSource Protocol satisfaction
    # ------------------------------------------------------------------

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[Stage28_10NormalizedEvent]:
        """Yield up to ``max_events`` hint-bearing
        ``Stage28_10NormalizedEvent`` records.

        Bounded discipline:

          * the iterator scans at most ``max_messages_to_scan``
            upstream messages,
          * the iterator yields at most ``max_events``
            hint-bearing events (non-hint-bearing messages do NOT
            consume the yield budget),
          * the iterator returns once ``yielded == max_events``,
          * the iterator stops on the first decode-failure /
            stream-error / RPC error (recording a closed-set
            refusal reason),
          * the iterator yields nothing when the source was
            construction-time refused (the orchestrator inspects
            ``init_refusal_reason``).

        Validation precedence:

          * ``max_events`` must be a positive ``int`` (not bool).
            Invalid values cause the iterator to yield nothing and
            record ``MAX_MESSAGES_TO_SCAN_INVALID``.
        """
        # Construction-time refusal: yield nothing.
        if self._init_refusal_reason is not None:
            return

        # Re-validate the caller-supplied max_events.
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or max_events <= 0
        ):
            self._last_refusal_reason = (
                REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
            )
            return

        assert self._runtime_config is not None  # narrowed by init
        runtime_config = self._runtime_config
        provider_name = runtime_config.safe_config.provider_id
        timeout_seconds = runtime_config.timeout_seconds
        # Stage 29.3A: scan budget is independent of the yield cap.
        # The for-loop below scans up to ``max_messages_to_scan``
        # upstream messages; the yield cap is enforced after each
        # yield via ``yielded >= max_events``. Non-hint-bearing
        # messages do not consume the yield budget.
        effective_bound = self._max_messages_to_scan

        self._iter_count += 1
        # Reset per-iteration refusal to NONE; we set a refusal
        # token below for any non-success path.
        self._last_refusal_reason = REFUSAL_REASON_NONE

        try:
            with _open_channel(
                runtime_config, self._channel_factory,
            ) as channel:
                try:
                    stub = _geyser_pb2_grpc.GeyserStub(channel)
                    metadata = _build_metadata(runtime_config)
                    request_iter = iter(
                        [build_pumpswap_subscribe_request()],
                    )
                    response_iter = stub.Subscribe(
                        request_iter,
                        timeout=timeout_seconds,
                        metadata=metadata,
                    )
                except grpc.RpcError:
                    self._last_refusal_reason = (
                        REFUSAL_REASON_SUBSCRIBE_FAILED
                    )
                    return
                except Exception:
                    self._last_refusal_reason = (
                        REFUSAL_REASON_SUBSCRIBE_FAILED
                    )
                    return

                try:
                    iterator = iter(response_iter)
                except TypeError:
                    self._last_refusal_reason = (
                        REFUSAL_REASON_STREAM_ERROR
                    )
                    return

                yielded = 0
                for _ in range(effective_bound):
                    try:
                        update = next(iterator)
                    except StopIteration:
                        break
                    except grpc.RpcError:
                        self._last_refusal_reason = (
                            REFUSAL_REASON_STREAM_ERROR
                        )
                        return
                    self._events_scanned += 1

                    if not isinstance(
                        update, _geyser_pb2.SubscribeUpdate,
                    ):
                        continue

                    # Only attempt decode on transaction-variant
                    # updates. ping / pong / slot / block / etc.
                    # variants are skipped without consuming the
                    # decode path.
                    try:
                        if not update.HasField("transaction"):
                            continue
                    except (ValueError, TypeError):
                        continue

                    self._transactions_scanned += 1

                    try:
                        payload, _extraction = (
                            decode_subscribe_update_with_pumpswap_hints(
                                update,
                                provider_name=provider_name,
                            )
                        )
                    except _Stage28_11DecodeError:
                        # Baseline decoder refused this update;
                        # keep scanning the rest of the bounded
                        # budget for a hint-bearing transaction.
                        continue
                    except Exception:
                        self._last_refusal_reason = (
                            REFUSAL_REASON_DECODE_FAILED
                        )
                        return

                    if not is_hint_bearing_payload(payload):
                        # Baseline-shape payload (mint =
                        # placeholder OR any hint slot None); keep
                        # scanning for the first hint-bearing
                        # event.
                        continue

                    # Project the hint-bearing payload onto a
                    # Stage 28.10 normalized event. The projection
                    # is pure / deterministic; a typed projection
                    # error is treated as a malformed payload and
                    # the source continues scanning.
                    try:
                        normalized = (
                            project_payload_to_normalized_event(
                                payload,
                            )
                        )
                    except (
                        Stage28_10InvalidPayloadError,
                        Stage28_10InvalidNormalizedEventError,
                    ):
                        continue

                    # Best-effort cancel of the upstream stream so
                    # the server tears down its side promptly.
                    try:
                        response_iter.cancel()
                    except Exception:
                        pass

                    yielded += 1
                    self._hint_bearing_yielded += 1
                    yield normalized

                    if yielded >= max_events:
                        return

                # Loop fell through: no hint-bearing payload
                # surfaced within the bounded budget.
                if yielded == 0:
                    self._last_refusal_reason = (
                        REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED
                    )
                try:
                    response_iter.cancel()
                except Exception:
                    pass
        except Exception:
            # The outer try here exists ONLY so a context-manager
            # failure (the _open_channel raising at __enter__ /
            # __exit__) does not leak. The channel-factory path
            # already validated callability at __init__; production
            # ``grpc.secure_channel`` raises only on internal SSL
            # errors. Either way the closed-set refusal token is
            # safe to surface.
            self._last_refusal_reason = (
                REFUSAL_REASON_SUBSCRIBE_FAILED
            )
            return


# The geyser_pb2_grpc + geyser_pb2 imports above are intentional.
# They pin the Stage 29.3 hint-aware event source to the same
# generated-stub package the Stage 28.11 / Stage 29.1 surfaces use,
# so the boundary scan can assert this module is allowed to depend
# on them.
_GENERATED_STUB_MARKER_UPDATE: object = _geyser_pb2.SubscribeUpdate
_GENERATED_STUB_MARKER_REQUEST: object = (
    _geyser_pb2.SubscribeRequest
)
_GENERATED_STUB_MARKER_GEYSER_STUB: object = (
    _geyser_pb2_grpc.GeyserStub
)
_PAYLOAD_TYPE_MARKER: object = Stage28_10ChainstackYellowstonePayload


__all__ = (
    # Locked constants.
    "GRPC_METADATA_KEY_X_TOKEN",
    "STAGE29_3_TRANSACTION_FILTER_NAME",
    "DEFAULT_MAX_MESSAGES_TO_SCAN",
    # Refusal-reason vocabulary.
    "REFUSAL_REASON_NONE",
    "REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID",
    "REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE",
    "REFUSAL_REASON_SUBSCRIBE_FAILED",
    "REFUSAL_REASON_STREAM_ERROR",
    "REFUSAL_REASON_DECODE_FAILED",
    "REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED",
    "REFUSAL_REASON_RUNTIME_CONFIG_INVALID",
    # Subscribe-request builder.
    "build_pumpswap_subscribe_request",
    # Event source.
    "Stage29_3HintAwareChainstackEventSource",
)
