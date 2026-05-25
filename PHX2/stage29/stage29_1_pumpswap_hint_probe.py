"""Stage 29.1 PumpSwap hint live probe orchestrator.

The single Stage 29.1 surface that opens a live Chainstack
Yellowstone gRPC channel, narrows the upstream subscription to
the PumpSwap AMM program, reads at most a bounded number of
``SubscribeUpdate`` messages, decodes each transaction-variant
message via the Stage 29.1 hint-aware decoder, and returns on
the first hint-bearing payload (or a closed-set refusal token
when no hint-bearing payload surfaces within the budget).

The probe NEVER:

  * sends a Discord message,
  * sends a Telegram message,
  * sends an X / social message,
  * touches a wallet / private-key / signer surface,
  * sizes / executes a trade,
  * invokes the Stage 28.9 wrapper,
  * invokes the Stage 28.6 bounded runner,
  * touches Stage 26 enforcement,
  * starts a daemon / watchdog / autorestart loop,
  * reads any env name other than the four canonical
    Stage 28.11 names through the unchanged Stage 28.11
    readiness boundary,
  * persists an artifact on its own (the operator's caller
    is responsible for writing the result to an artifact
    directory outside the PHX2 tree).

This module is the ONLY Stage 29.1 production file allowed to
import ``grpc`` and the generated Yellowstone protobuf stubs.
Every other Stage 29.1 production module stays gRPC-free.

This module imports:

  * stdlib (``contextlib`` / ``typing``),
  * ``grpc`` (the runtime gRPC channel layer),
  * ``PHX2.proto.stage28_11._generated.geyser_pb2`` /
    ``geyser_pb2_grpc`` (the generated Yellowstone stubs),
  * ``PHX2.stage28.chainstack_yellowstone_grpc_models`` (the
    Stage 28.11 runtime-config + endpoint-secret types),
  * ``PHX2.stage28.chainstack_yellowstone_grpc_decode`` (the
    Stage 28.11 baseline decode-error type, surfaced verbatim
    when the upstream message fails the baseline shape
    contract),
  * ``PHX2.stage29.pumpswap_hint_aware_decoder`` (the Stage
    29.1 hint-aware decoder),
  * ``PHX2.stage29.pumpswap_program_constants`` (the
    PumpSwap program id),
  * ``PHX2.stage29.stage29_1_hint_probe_models`` (the probe
    result + closed-set vocabularies).

It does NOT import:

  * Stage 21-27 production code,
  * Stage 28.4 audited transport / Stage 28.6 runner / Stage
    28.9 adapter / Stage 28.9 transport,
  * Stage 29.2 / Stage 29.3 surfaces (none exist at Stage
    29.1),
  * any Discord / Telegram / X / wallet / trading / dotenv /
    keyring library,
  * ``os`` / the process environment (the Stage 28.11
    readiness module owns the only env-read boundary; the
    operator hands this probe a pre-built runtime-config
    record).

Discipline:

  * No env reads here. The runtime-config is constructed by
    the unchanged Stage 28.11 readiness layer
    (``build_runtime_config_from_env``) and passed in.
  * Every gRPC call carries the runtime-config's finite
    deadline.
  * The channel closes deterministically on every exit path.
  * Raw gRPC error tracebacks NEVER leak; the probe catches
    ``grpc.RpcError`` and emits closed-set status-code names.
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
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11DecodeError,
    Stage28_11InvalidRuntimeConfigError,
)
from PHX2.stage29.pumpswap_hint_aware_decoder import (
    decode_subscribe_update_with_pumpswap_hints,
    is_hint_bearing_payload,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
)
from PHX2.stage29.stage29_1_hint_probe_models import (
    PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
    PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
    PROBE_STATUS_DECODED_WITH_HINTS,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_SKIPPED,
    REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED,
    REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
    REFUSAL_REASON_STREAM_ERROR,
    REFUSAL_REASON_SUBSCRIBE_FAILED,
    Stage29_1HintProbeResult,
    build_hint_probe_result,
    is_probe_mode_value,
)


# ---------------------------------------------------------------------------
# gRPC metadata key for the Chainstack Yellowstone x-token
# ---------------------------------------------------------------------------


GRPC_METADATA_KEY_X_TOKEN: str = "x-token"


# Stage 29.1 filter entry name used inside the
# ``SubscribeRequest.transactions`` map field. Stage 29.1 uses a
# distinctive name (NOT the Stage 28.11 ``stage28_11_dry_run``
# label) so the Chainstack server-side audit clearly distinguishes
# the Stage 29.1 probe from the Stage 28.11 baseline probe.
STAGE29_1_TRANSACTION_FILTER_NAME: str = "stage29_1_pumpswap"


# Cap on the number of upstream ``SubscribeUpdate`` messages the
# Stage 29.1 probe will pull before giving up. The probe is
# bounded BOTH by the per-call deadline (which comes from the
# Stage 28.11 runtime-config) AND by this message cap. The
# default mirrors the Stage 28.11 dry-run cap; callers may pass
# a different value via ``max_messages_to_scan``.
DEFAULT_MAX_MESSAGES_TO_SCAN: int = 64


# ---------------------------------------------------------------------------
# Subscribe request builder
# ---------------------------------------------------------------------------


def build_pumpswap_subscribe_request() -> object:
    """Build a Yellowstone ``SubscribeRequest`` that narrows the
    upstream stream to PumpSwap AMM transactions only.

    Pure / deterministic. The request:

      * names a single transaction filter
        (``STAGE29_1_TRANSACTION_FILTER_NAME``) whose
        ``account_include`` list contains exactly the PumpSwap
        program id,
      * sets ``vote = False`` (no vote transactions),
      * sets ``failed = False`` (no failed transactions; the
        hint extractor would refuse them anyway, but narrowing
        upstream reduces wasted bandwidth),
      * sets ``commitment = CONFIRMED`` to match the Stage
        28.11 baseline.

    No other filter axes (slots / accounts / blocks / entries)
    are touched.
    """
    request = _geyser_pb2.SubscribeRequest()
    tx_filter = request.transactions[
        STAGE29_1_TRANSACTION_FILTER_NAME
    ]
    tx_filter.account_include.append(PUMPSWAP_PROGRAM_ID)
    tx_filter.vote = False
    tx_filter.failed = False
    request.commitment = _geyser_pb2.CONFIRMED
    return request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_grpc_code_name(err: object) -> str:
    """Return a closed-set safe label for a gRPC error.

    The error code is a closed-set ``grpc.StatusCode`` ENUM; its
    name (``UNAVAILABLE``, ``UNAUTHENTICATED``, etc.) is safe to
    forward as a closed-set token. Raw gRPC error messages can
    echo URL fragments / metadata / hostnames and must never
    leave the boundary.
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
    runtime_config: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    channel_factory: Optional[object],
) -> Iterator[object]:
    """Yield a gRPC channel for the probe run.

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
                # Cleanup is best-effort; do NOT raise from the
                # context manager exit to avoid masking the
                # caller's original exception.
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
# Probe entry point
# ---------------------------------------------------------------------------


def run_stage29_1_pumpswap_hint_probe(
    *,
    runtime_config: (
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
    ),
    mode: str,
    live_flag_set: bool,
    max_messages_to_scan: int = DEFAULT_MAX_MESSAGES_TO_SCAN,
    channel_factory: Optional[object] = None,
) -> Stage29_1HintProbeResult:
    """Run a Stage 29.1 PumpSwap hint probe.

    Arguments:

      * ``runtime_config`` -- a Stage 28.11 runtime-config
        constructed via the unchanged Stage 28.11 readiness
        layer (``build_runtime_config_from_env``); never built
        here so Stage 29.1 introduces no second env-read site.
      * ``mode`` -- must be
        ``PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN``; any
        other value yields a SKIPPED result with
        ``MODE_INVALID``.
      * ``live_flag_set`` -- the caller's projection of the
        Stage 28.11 ``PHX2_STAGE28_11_ALLOW_LIVE_GRPC`` env
        flag. Must be ``True`` for the probe to open a real
        channel; ``False`` yields a SKIPPED result with
        ``LIVE_FLAG_NOT_SET``.
      * ``max_messages_to_scan`` -- positive int cap on how
        many upstream ``SubscribeUpdate`` messages the probe
        consumes. Defaults to
        ``DEFAULT_MAX_MESSAGES_TO_SCAN`` (64). Invalid values
        yield a SKIPPED result with
        ``MAX_MESSAGES_TO_SCAN_INVALID``.
      * ``channel_factory`` -- optional ``(target, credentials)
        -> channel`` callable. ``None`` uses the production
        ``grpc.secure_channel``. Non-callable values yield a
        SKIPPED result with
        ``CHANNEL_FACTORY_NOT_CALLABLE``.

    Returns a single ``Stage29_1HintProbeResult`` carrying the
    probe outcome. Never raises; every failure is projected to a
    closed-set refusal reason on the result so the operator's
    artifact discipline is preserved.
    """
    # 1. Validate runtime config (must be a Stage 28.11
    #    runtime-config record; any other shape yields a SKIPPED
    #    result with MODE_INVALID for symmetry with the Stage
    #    28.11 probe contract -- the operator constructs the
    #    runtime-config via the readiness boundary).
    if not isinstance(
        runtime_config,
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    ):
        return build_hint_probe_result(
            mode=(
                mode
                if is_probe_mode_value(mode)
                else PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN
            ),
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
        )

    # 2. Validate mode.
    if not is_probe_mode_value(mode):
        return build_hint_probe_result(
            mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
        )

    # 3. Validate live-flag.
    if not isinstance(live_flag_set, bool) or not live_flag_set:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_LIVE_FLAG_NOT_SET,
        )

    # 4. Validate max_messages_to_scan.
    if (
        isinstance(max_messages_to_scan, bool)
        or not isinstance(max_messages_to_scan, int)
        or max_messages_to_scan <= 0
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=(
                REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID
            ),
        )

    # 5. Validate channel_factory (when not None).
    if channel_factory is not None and not callable(
        channel_factory,
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=(
                REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE
            ),
        )

    provider_name = runtime_config.safe_config.provider_id
    timeout_seconds = runtime_config.timeout_seconds

    events_scanned = 0
    transactions_scanned = 0
    last_extraction_result = None

    try:
        with _open_channel(
            runtime_config, channel_factory,
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
                return build_hint_probe_result(
                    mode=mode,
                    status=PROBE_STATUS_FAILED,
                    refusal_reason=(
                        REFUSAL_REASON_SUBSCRIBE_FAILED
                    ),
                )
            except Exception:
                return build_hint_probe_result(
                    mode=mode,
                    status=PROBE_STATUS_FAILED,
                    refusal_reason=(
                        REFUSAL_REASON_SUBSCRIBE_FAILED
                    ),
                )

            try:
                iterator = iter(response_iter)
            except TypeError:
                return build_hint_probe_result(
                    mode=mode,
                    status=PROBE_STATUS_FAILED,
                    refusal_reason=(
                        REFUSAL_REASON_STREAM_ERROR
                    ),
                )

            for _ in range(max_messages_to_scan):
                try:
                    update = next(iterator)
                except StopIteration:
                    break
                except grpc.RpcError:
                    return build_hint_probe_result(
                        mode=mode,
                        status=PROBE_STATUS_FAILED,
                        refusal_reason=(
                            REFUSAL_REASON_STREAM_ERROR
                        ),
                        events_scanned=events_scanned,
                        transactions_scanned=(
                            transactions_scanned
                        ),
                    )
                events_scanned += 1

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

                transactions_scanned += 1

                try:
                    payload, extraction = (
                        decode_subscribe_update_with_pumpswap_hints(
                            update,
                            provider_name=provider_name,
                        )
                    )
                except Stage28_11DecodeError:
                    # Baseline decoder refused this update;
                    # continue scanning the rest of the
                    # bounded budget. The closed-set reason on
                    # the Stage 28.11 error is not surfaced
                    # here because we keep looking for a
                    # hint-bearing transaction.
                    continue
                except Exception:
                    return build_hint_probe_result(
                        mode=mode,
                        status=PROBE_STATUS_FAILED,
                        refusal_reason=(
                            REFUSAL_REASON_DECODE_FAILED
                        ),
                        events_scanned=events_scanned,
                        transactions_scanned=(
                            transactions_scanned
                        ),
                    )

                last_extraction_result = extraction

                if is_hint_bearing_payload(payload):
                    # Best-effort: cancel the upstream stream
                    # so the server tears down its side
                    # promptly. ``cancel()`` is safe to call
                    # even after the stream has naturally
                    # terminated.
                    try:
                        response_iter.cancel()
                    except Exception:
                        pass
                    return build_hint_probe_result(
                        mode=mode,
                        status=PROBE_STATUS_DECODED_WITH_HINTS,
                        refusal_reason=REFUSAL_REASON_NONE,
                        hint_bearing_payload=payload,
                        extraction_result=extraction,
                        events_scanned=events_scanned,
                        transactions_scanned=(
                            transactions_scanned
                        ),
                        handoff_ready=True,
                    )

            # Loop fell through: no hint-bearing payload
            # surfaced within the bounded budget. Cancel the
            # upstream stream and return a refusal.
            try:
                response_iter.cancel()
            except Exception:
                pass

            if transactions_scanned == 0:
                return build_hint_probe_result(
                    mode=mode,
                    status=PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
                    refusal_reason=(
                        REFUSAL_REASON_NO_TRANSACTION_RECEIVED
                    ),
                    extraction_result=last_extraction_result,
                    events_scanned=events_scanned,
                    transactions_scanned=transactions_scanned,
                )
            return build_hint_probe_result(
                mode=mode,
                status=PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
                refusal_reason=(
                    REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED
                ),
                extraction_result=last_extraction_result,
                events_scanned=events_scanned,
                transactions_scanned=transactions_scanned,
            )
    except grpc.RpcError as err:
        # Channel-open or unexpected channel-level error.
        # Surface CONNECT_FAILED without echoing the raw code
        # (closed-set token policy).
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_CONNECT_FAILED,
        )
    except Stage28_11InvalidRuntimeConfigError:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
        )
    except Exception:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_CONNECT_FAILED,
        )


__all__ = (
    "GRPC_METADATA_KEY_X_TOKEN",
    "STAGE29_1_TRANSACTION_FILTER_NAME",
    "DEFAULT_MAX_MESSAGES_TO_SCAN",
    "build_pumpswap_subscribe_request",
    "run_stage29_1_pumpswap_hint_probe",
)
