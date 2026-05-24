"""Stage 28.11 Chainstack Yellowstone real gRPC client.

This module ships the FIRST Stage 28.11 production class that
opens a real Chainstack Yellowstone gRPC channel. It satisfies
the Stage 28.10 ``Stage28_10ChainstackYellowstoneClient``
Protocol so the existing Stage 28.10 event source / hint-aware
candidate assembler chain can later (in Stage 28.12, under
separate operator authorization) drain real provider-backed
events through the same Protocol the Stage 28.10 fake client
already satisfies.

This module IS allowed to import:

  * ``grpc`` (the runtime gRPC channel layer),
  * the generated ``geyser_pb2`` / ``geyser_pb2_grpc`` modules
    under ``PHX2.proto.stage28_11._generated``,
  * the Stage 28.11 models / decode modules,
  * the Stage 28.10 contracts / models modules.

It does NOT import:

  * Stage 21-27 production code,
  * ``os`` / the process environment (the readiness layer owns
    that surface),
  * any messaging / Discord / Telegram / X / dispatch / trade /
    wallet / private-key library,
  * the Stage 28.9 adapter / Stage 28.9 transport (Stage 28.11
    does NOT wire to the Stage 28.9 wrapper -- that step is
    Stage 28.12).

Discipline:

  * No env reads.
  * No Discord send.
  * No automated trading / wallet / signer / position-sizing /
    trade-execution surface.
  * No public / subscriber / paid-tier / Telegram / X routing.
  * No daemon / watchdog / autorestart loop.
  * Every gRPC call carries a finite deadline.
  * Channels close deterministically (context-managed) at the
    end of every method.
  * Raw gRPC error tracebacks NEVER leak through the public
    boundary; the client catches ``grpc.RpcError`` and re-emits
    ``Stage28_11ConnectError`` / ``Stage28_11DecodeError``
    with closed-set reason tokens.
  * The raw endpoint URL and raw x-token NEVER appear on any
    public attribute, ``__repr__``, exception, log line, or
    artifact; they are read from the private secret subobject
    only at channel-create / metadata-attach time.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Iterator,
    Optional,
    Tuple,
)

import grpc

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
    geyser_pb2_grpc as _geyser_pb2_grpc,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    decode_subscribe_update_to_payload,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11ConnectError,
    Stage28_11DecodeError,
    Stage28_11GrpcError,
    Stage28_11InvalidRuntimeConfigError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstonePayload,
)


# ---------------------------------------------------------------------------
# Metadata key for the Chainstack Yellowstone x-token
# ---------------------------------------------------------------------------


# Chainstack Yellowstone gRPC uses ``x-token`` as the metadata
# header carrying the auth token. The Stage 28.11 boundary scan
# pins this constant; the client always attaches it via the
# explicit ``metadata`` argument on every RPC call.
GRPC_METADATA_KEY_X_TOKEN: str = "x-token"


# Locked cap on the number of upstream ``SubscribeUpdate``
# messages the Stage 28.11 dry-run scans while searching for the
# first transaction variant. Chainstack Yellowstone multiplexes
# transaction updates with ping / pong / slot / block / etc.
# updates; the dry-run skips the latter to find one transaction.
# The cap is finite so a pathological upstream that only emits
# non-transaction noise can NOT keep the dry-run subscribed
# indefinitely (the per-call deadline also bounds wall-clock
# time, but the message cap is the tighter bound on bytes /
# logical work). If the cap is exceeded without a transaction,
# the reader returns ``None`` and the caller surfaces the
# closed-set ``NO_TRANSACTION_UPDATE_RECEIVED`` reason exactly
# like a deadline-expired stream.
MAX_UPSTREAM_MESSAGES_TO_SCAN: int = 64


# ---------------------------------------------------------------------------
# Stage 28.11 gRPC client
# ---------------------------------------------------------------------------


class Stage28_11ChainstackYellowstoneGrpcClient:
    """Stage 28.11 real Chainstack Yellowstone gRPC client.

    Construction:

      * ``runtime_config`` -- a Stage 28.11
                              ``Stage28_11ChainstackYellowstoneGrpcRuntimeConfig``
                              built via the Stage 28.11 readiness
                              helper (which refuses unsafe env
                              shapes); the secret subobject's raw
                              endpoint + x-token are accessed
                              only at channel-create /
                              metadata-attach time.

    Methods:

      * ``validate_readiness()`` -- pure no-network shape check
                                     that pins the runtime config
                                     is well-formed.
      * ``provider_connect_only(channel_factory=None)`` -- opens
                                     the secure channel, calls
                                     ``Ping()``, tears the
                                     channel down. No event
                                     decode. No Discord. No
                                     stream subscription.
      * ``one_event_decode_dry_run(channel_factory=None)`` --
                                     opens the secure channel,
                                     calls ``Subscribe()`` with
                                     a minimal transaction
                                     filter, reads at most one
                                     ``SubscribeUpdate`` and
                                     decodes it via the Stage
                                     28.11 decoder, tears the
                                     channel down. No Discord.
                                     No Stage 28.9 wrapper.
      * ``fetch_yellowstone_events(cursor, max_events)`` --
                                     Stage 28.10 Protocol
                                     satisfaction. Returns a
                                     ``(tuple_of_payloads,
                                     next_cursor)`` pair using
                                     the same one-event subscribe
                                     under the hood (bounded by
                                     ``max_events``).
      * ``iter_yellowstone_events(*, max_events)`` -- Stage
                                     28.10 Protocol satisfaction.
                                     Iterator form of the above.

    The Stage 28.10 ``Stage28_10ChainstackYellowstoneClient``
    Protocol is satisfied by the two ``*_yellowstone_events``
    methods so a later Stage 28.12 substage can wire this client
    into the Stage 28.9 wrapper unchanged. **Stage 28.11 itself
    does NOT invoke that wrapper.**
    """

    def __init__(
        self,
        *,
        runtime_config: (
            Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
        ),
    ) -> None:
        if not isinstance(
            runtime_config,
            Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
        ):
            raise Stage28_11InvalidRuntimeConfigError(
                field_name="runtime_config",
                reason="NOT_A_RUNTIME_CONFIG",
            )
        self._runtime_config: (
            Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
        ) = runtime_config
        self._connect_call_count: int = 0
        self._decode_call_count: int = 0

    # ------------------------------------------------------------------
    # Safe accessors
    # ------------------------------------------------------------------

    @property
    def runtime_config(
        self,
    ) -> Stage28_11ChainstackYellowstoneGrpcRuntimeConfig:
        return self._runtime_config

    @property
    def connect_call_count(self) -> int:
        return self._connect_call_count

    @property
    def decode_call_count(self) -> int:
        return self._decode_call_count

    def __repr__(self) -> str:
        return (
            "Stage28_11ChainstackYellowstoneGrpcClient("
            f"runtime_config={self._runtime_config!r}, "
            f"connect_call_count={self._connect_call_count!r}, "
            f"decode_call_count={self._decode_call_count!r})"
        )

    # ------------------------------------------------------------------
    # Public modes
    # ------------------------------------------------------------------

    def validate_readiness(self) -> None:
        """Pure no-network shape check.

        Re-runs the runtime-config field validation (already run
        at construction) so callers can pin the readiness step
        as a distinct method without having to introspect the
        constructor. Raises
        ``Stage28_11InvalidRuntimeConfigError`` on any locked-
        shape violation; returns ``None`` on success.
        """
        from PHX2.stage28.chainstack_yellowstone_grpc_models import (
            _validate_runtime_config_fields,
        )
        _validate_runtime_config_fields(self._runtime_config)

    def provider_connect_only(
        self,
        *,
        channel_factory: Optional[object] = None,
    ) -> None:
        """Open the secure gRPC channel, call ``Ping()``, tear
        the channel down.

        No event decode. No Stream subscription. No Discord. The
        ``channel_factory`` argument is an injection seam for
        tests so a fake channel that does not touch the network
        can stand in for ``grpc.secure_channel``; tests pass an
        in-process fake. Production callers pass ``None`` to use
        the real ``grpc.secure_channel``.

        Raises ``Stage28_11ConnectError`` (closed-set reason) on
        any gRPC failure. The exception NEVER carries the raw
        endpoint URL, the raw x-token, or the raw gRPC error
        message.
        """
        self._connect_call_count += 1
        with self._open_channel(channel_factory) as channel:
            try:
                stub = _geyser_pb2_grpc.GeyserStub(channel)
                request = _geyser_pb2.PingRequest(count=1)
                metadata = self._build_metadata()
                _response = stub.Ping(
                    request,
                    timeout=self._timeout_seconds(),
                    metadata=metadata,
                )
            except grpc.RpcError as err:
                code_name = self._safe_grpc_code_name(err)
                raise Stage28_11ConnectError(
                    f"PING_RPC_ERROR:{code_name}",
                )
            except Stage28_11GrpcError:
                raise
            except Exception:
                # Defensive: catch any other unexpected
                # exception from the gRPC layer and re-wrap with
                # a closed-set token so the raw traceback never
                # surfaces at the Stage 28.11 boundary.
                raise Stage28_11ConnectError(
                    "PING_UNEXPECTED_ERROR",
                )

    def one_event_decode_dry_run(
        self,
        *,
        channel_factory: Optional[object] = None,
    ) -> Stage28_10ChainstackYellowstonePayload:
        """Open the secure gRPC channel, subscribe with a minimal
        transaction filter, decode at most ONE upstream
        ``SubscribeUpdate`` into the Stage 28.10 safe payload,
        tear the channel down.

        Raises ``Stage28_11ConnectError`` (closed-set reason)
        when the channel / stream fails before any event is
        received. Raises ``Stage28_11DecodeError`` (closed-set
        reason) when the upstream message cannot be decoded.

        No Discord send. No Stage 28.9 wrapper. No dispatch.
        Returns the decoded Stage 28.10 payload on success.
        """
        self._decode_call_count += 1
        with self._open_channel(channel_factory) as channel:
            try:
                stub = _geyser_pb2_grpc.GeyserStub(channel)
                metadata = self._build_metadata()
                request_iter = iter(
                    [self._build_minimal_transaction_request()],
                )
                response_iter = stub.Subscribe(
                    request_iter,
                    timeout=self._timeout_seconds(),
                    metadata=metadata,
                )
            except grpc.RpcError as err:
                code_name = self._safe_grpc_code_name(err)
                raise Stage28_11ConnectError(
                    f"SUBSCRIBE_RPC_ERROR:{code_name}",
                )
            except Stage28_11GrpcError:
                raise
            except Exception:
                raise Stage28_11ConnectError(
                    "SUBSCRIBE_UNEXPECTED_ERROR",
                )

            try:
                update = self._read_first_transaction_update(
                    response_iter,
                )
            except grpc.RpcError as err:
                code_name = self._safe_grpc_code_name(err)
                raise Stage28_11ConnectError(
                    f"SUBSCRIBE_STREAM_ERROR:{code_name}",
                )

            if update is None:
                raise Stage28_11DecodeError(
                    "NO_TRANSACTION_UPDATE_RECEIVED",
                )

            payload = decode_subscribe_update_to_payload(
                update,
                provider_name=(
                    self._runtime_config.safe_config.provider_id
                ),
            )

            # Best-effort: cancel the upstream stream so the
            # server tears down its side promptly. ``cancel()``
            # is safe to call even after the stream has
            # naturally terminated.
            try:
                response_iter.cancel()
            except Exception:
                # Cancellation is best-effort; never fail the
                # probe because of cleanup errors.
                pass

            return payload

    # ------------------------------------------------------------------
    # Stage 28.10 Protocol satisfaction
    # ------------------------------------------------------------------

    def fetch_yellowstone_events(
        self,
        cursor: Optional[str],
        max_events: int,
    ) -> Tuple[
        Tuple[Stage28_10ChainstackYellowstonePayload, ...],
        Optional[str],
    ]:
        """Stage 28.10 Protocol satisfaction.

        Stage 28.11 implements this method by running the
        one-event subscribe under the hood, bounded by
        ``max_events``. The cursor is ignored (Stage 28.11 does
        not implement resumable cursor pagination yet; the next-
        cursor sentinel is always ``None``).

        Raises the same Stage 28.11 errors as
        ``one_event_decode_dry_run``.

        **Stage 28.11 itself does NOT wire this method into the
        Stage 28.9 wrapper.** The Stage 28.10 event source can
        call this in a later Stage 28.12 substage; the Stage
        28.11 probe layer does NOT.
        """
        if isinstance(max_events, bool) or not isinstance(
            max_events, int
        ):
            raise Stage28_11DecodeError("MAX_EVENTS_NOT_INT")
        if max_events <= 0:
            raise Stage28_11DecodeError(
                "MAX_EVENTS_NOT_POSITIVE",
            )
        if cursor is not None and not isinstance(cursor, str):
            raise Stage28_11DecodeError(
                "CURSOR_NOT_STRING_OR_NONE",
            )
        # Stage 28.11 implements the bound by performing one
        # decode then returning the singleton tuple. A future
        # substage may stream more events; Stage 28.11 stays
        # tight.
        payload = self.one_event_decode_dry_run()
        return ((payload,), None)

    def iter_yellowstone_events(
        self,
        *,
        max_events: int,
    ) -> Iterator[Stage28_10ChainstackYellowstonePayload]:
        """Stage 28.10 Protocol satisfaction. Iterator form."""
        if isinstance(max_events, bool) or not isinstance(
            max_events, int
        ):
            raise Stage28_11DecodeError("MAX_EVENTS_NOT_INT")
        if max_events <= 0:
            raise Stage28_11DecodeError(
                "MAX_EVENTS_NOT_POSITIVE",
            )
        payload = self.one_event_decode_dry_run()
        yield payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timeout_seconds(self) -> int:
        return self._runtime_config.timeout_seconds

    def _build_metadata(self) -> tuple[tuple[str, str], ...]:
        """Construct the metadata tuple gRPC attaches to every
        call.

        The x-token is read just-in-time from the private secret
        subobject; the tuple is small (one entry) and local to
        this call -- no copy persists.
        """
        token = (
            self._runtime_config.endpoint_secret
            .get_x_token_for_internal_use()
        )
        return ((GRPC_METADATA_KEY_X_TOKEN, token),)

    def _build_minimal_transaction_request(
        self,
    ) -> object:
        """Build a minimal Yellowstone ``SubscribeRequest`` that
        targets non-vote transactions only.

        The Stage 28.11 dry-run does NOT filter by mint /
        account / program -- the goal is just to confirm the
        upstream stream produces at least one well-formed
        transaction update so the decoder can be exercised. The
        Stage 28.10 candidate assembler downstream applies the
        Stage 27 / Stage 28.6 pair-classification + UNKNOWN /
        DISAGREE / USDC observe-only suppressions; Stage 28.11
        does NOT bypass those.
        """
        request = _geyser_pb2.SubscribeRequest()
        # The map<string, SubscribeRequestFilterTransactions>
        # field is named ``transactions`` on the request. Adding
        # a single filter entry with vote=False keeps vote
        # transactions out of the dry-run stream.
        request.transactions["stage28_11_dry_run"].vote = False
        # ``commitment`` defaults to PROCESSED (0); Stage 28.11
        # dry-run uses CONFIRMED to align with the operator's
        # typical price-context expectations.
        request.commitment = _geyser_pb2.CONFIRMED
        return request

    def _read_first_transaction_update(
        self,
        response_iter: object,
    ) -> Optional[object]:
        """Read the response stream until the first transaction-
        variant ``SubscribeUpdate`` arrives, then return it.

        Returns ``None`` if the stream ends, the per-stream
        message scan cap (``MAX_UPSTREAM_MESSAGES_TO_SCAN``) is
        hit, or no transaction variant appears in the scanned
        prefix. Skips ``ping`` / ``pong`` / ``slot`` / ``block``
        / etc. variants the Yellowstone server multiplexes
        alongside transactions; non-protobuf items in the stream
        are also skipped without consuming additional scan
        budget beyond their own slot.

        The Stage 28.11 dry-run is bounded by BOTH:

          * the per-call deadline (``timeout`` passed to
            ``Subscribe``), which raises ``grpc.RpcError`` and
            is wrapped by the caller, AND
          * the per-stream message scan cap, which consumes AT
            MOST ``MAX_UPSTREAM_MESSAGES_TO_SCAN`` items from
            the upstream iterator (no extra "peek-and-discard"
            pull past the cap). This keeps the dry-run finite
            even when the upstream emits only non-transaction
            noise within the deadline window.
        """
        if not hasattr(response_iter, "__iter__"):
            return None
        # Use an explicit ``next()`` loop instead of ``for ... in
        # response_iter`` so the cap is checked BEFORE each pull;
        # a ``for`` loop would advance the iterator one more time
        # before the in-body cap check ran, consuming
        # ``MAX_UPSTREAM_MESSAGES_TO_SCAN + 1`` items total. The
        # exact contract is "no more than the cap items pulled,
        # ever."
        try:
            iterator = iter(response_iter)
        except TypeError:
            return None
        for _ in range(MAX_UPSTREAM_MESSAGES_TO_SCAN):
            try:
                update = next(iterator)
            except StopIteration:
                return None
            if not isinstance(
                update, _geyser_pb2.SubscribeUpdate,
            ):
                continue
            try:
                if update.HasField("transaction"):
                    return update
            except (ValueError, TypeError):
                continue
        # Cap exhausted without a transaction variant; the
        # iterator was advanced exactly
        # ``MAX_UPSTREAM_MESSAGES_TO_SCAN`` times. The caller
        # maps the ``None`` return to the closed-set
        # ``NO_TRANSACTION_UPDATE_RECEIVED`` reason; no raw
        # upstream content leaks.
        return None

    def _safe_grpc_code_name(
        self,
        err: object,
    ) -> str:
        """Return a closed-set safe label for a gRPC error.

        The Stage 28.11 boundary discipline mandates no raw gRPC
        error message ever surfaces on the public exception (the
        message can echo URL fragments, metadata, hostnames).
        The error code is a closed-set ``grpc.StatusCode``
        ENUM; the name (``UNAVAILABLE``, ``UNAUTHENTICATED``,
        etc.) is safe to forward as a closed-set token.
        """
        code_callable = getattr(err, "code", None)
        if callable(code_callable):
            try:
                code = code_callable()
            except Exception:
                return "UNKNOWN"
            name = getattr(code, "name", None)
            if isinstance(name, str) and name != "":
                return name
        return "UNKNOWN"

    @contextmanager
    def _open_channel(
        self,
        channel_factory: Optional[object],
    ) -> Iterator[object]:
        """Yield a gRPC channel for the run.

        The default factory builds a real ``grpc.secure_channel``
        with TLS credentials. Tests pass an explicit
        ``channel_factory`` callable that takes the target +
        credentials and returns a fake channel (offline). The
        context manager always closes the channel on exit even
        when the body raised.
        """
        target = (
            self._runtime_config.endpoint_secret
            .get_endpoint_url_for_internal_use()
        )
        if channel_factory is None:
            channel = grpc.secure_channel(
                target,
                grpc.ssl_channel_credentials(),
            )
        else:
            if not callable(channel_factory):
                raise Stage28_11ConnectError(
                    "CHANNEL_FACTORY_NOT_CALLABLE",
                )
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
                    # Cleanup is best-effort; do NOT raise from
                    # the context manager exit to avoid masking
                    # the caller's original exception.
                    pass


__all__ = (
    "GRPC_METADATA_KEY_X_TOKEN",
    "MAX_UPSTREAM_MESSAGES_TO_SCAN",
    "Stage28_11ChainstackYellowstoneGrpcClient",
)
