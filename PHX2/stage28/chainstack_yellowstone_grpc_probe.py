"""Stage 28.11 Chainstack Yellowstone gRPC probe orchestrator.

This module composes the Stage 28.11 readiness + client + decode
layers into a single bounded probe entry point that the operator
runs at the boundary BEFORE any later Stage 28.12 substage may
wire the real client into the Stage 28.9 wrapper.

The probe runs in one of three explicit modes:

  1. ``MODE_READINESS_ONLY`` -- re-validates the runtime-config
     shape with no network access. No Discord. No subscribe. No
     decode.
  2. ``MODE_PROVIDER_CONNECT_ONLY`` -- opens the secure gRPC
     channel, calls ``Ping()``, tears the channel down. No
     stream subscription. No event decode. No Discord.
  3. ``MODE_ONE_EVENT_DECODE_DRY_RUN`` -- opens the secure
     channel, subscribes with a minimal transaction filter,
     reads at most ONE upstream ``SubscribeUpdate``, decodes it
     into the Stage 28.10 safe payload, tears the channel down.
     No Discord. No Stage 28.9 wrapper. No dispatch.

The probe returns a single Stage 28.11
``Stage28_11GrpcProbeResult`` record that carries:

  * the closed-set ``mode`` token executed,
  * the closed-set ``status`` token (READY / CONNECTED /
    DECODED / FAILED / SKIPPED),
  * the closed-set ``refusal_reason`` token (``NONE`` on
    success),
  * the booleans ``ready`` / ``connected`` / ``decoded``,
  * the optional Stage 28.10 payload (set only in dry-run
    mode),
  * the boolean ``handoff_ready`` -- True iff every sub-step
    the requested mode targeted passed AND the live-gate env
    flag was set.

The ``handoff_ready`` axis is the explicit signal the operator
inspects before authorizing Stage 28.12 (Stage 28.9 wrapper
with ``max_events=1`` / ``max_dispatches=1``). **Stage 28.11
itself does NOT invoke the Stage 28.9 wrapper.**

This module imports stdlib (``typing``) plus the Stage 28.11
models / readiness / client modules + Stage 28.10 models. It
does NOT import:

  * Stage 21-27 production code,
  * the Stage 28.9 adapter / Stage 28.9 transport,
  * any Discord / Telegram / X / messaging / trade / wallet
    library,
  * ``grpc`` directly (the client module owns that surface),
  * ``os`` / the process environment (the readiness module
    owns that surface).
"""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage28.chainstack_yellowstone_grpc_client import (
    Stage28_11ChainstackYellowstoneGrpcClient,
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
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_NO_EVENT_RECEIVED,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11ConnectError,
    Stage28_11DecodeError,
    Stage28_11GrpcError,
    Stage28_11GrpcProbeResult,
    Stage28_11InvalidRuntimeConfigError,
    build_grpc_probe_result,
    is_mode_value,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    build_runtime_config_from_env,
    detect_stage28_11_grpc_readiness,
)


# ---------------------------------------------------------------------------
# Probe entry point
# ---------------------------------------------------------------------------


def run_stage28_11_probe(
    *,
    runtime_config: (
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
    ),
    mode: str,
    live_flag_set: bool,
    channel_factory: Optional[object] = None,
) -> Stage28_11GrpcProbeResult:
    """Run a Stage 28.11 probe against a caller-supplied
    runtime-config + mode.

    The probe NEVER:

      * sends a Discord message,
      * invokes the Stage 28.9 wrapper,
      * persists an enforcement artifact,
      * touches Stage 29 surfaces,
      * sends a Telegram / X / social message,
      * touches a wallet / private-key / signer surface,
      * sizes / executes a trade.

    Arguments:

      * ``runtime_config`` -- the Stage 28.11 runtime config
                              (typically built from env via
                              ``build_runtime_config_from_env``).
      * ``mode`` -- the closed-set Stage 28.11 mode token to
                    execute.
      * ``live_flag_set`` -- True iff
                              ``PHX2_STAGE28_11_ALLOW_LIVE_GRPC``
                              is set; gates real network access
                              (the readiness-only mode does NOT
                              require the live flag).
      * ``channel_factory`` -- optional injection seam for tests
                                (an offline channel factory).
                                Production callers pass ``None``.

    Returns a ``Stage28_11GrpcProbeResult`` with the closed-set
    status / refusal-reason tokens + the booleans.
    """
    if not is_mode_value(mode):
        return build_grpc_probe_result(
            mode=MODE_READINESS_ONLY,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
            ready=False,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    # --- 1. readiness-only --------------------------------------------
    try:
        _validate_runtime_config(runtime_config)
    except Stage28_11InvalidRuntimeConfigError as err:
        return build_grpc_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
            ready=False,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    if mode == MODE_READINESS_ONLY:
        return build_grpc_probe_result(
            mode=MODE_READINESS_ONLY,
            status=PROBE_STATUS_READY,
            refusal_reason=REFUSAL_REASON_NONE,
            ready=True,
            connected=False,
            decoded=False,
            decoded_payload=None,
            # Readiness-only is a paper check; the live-gate
            # flag is what the operator inspects when deciding
            # whether to escalate to connect-only / dry-run /
            # Stage 28.12. Readiness alone never reports
            # ``handoff_ready=True``.
            handoff_ready=False,
            events_received=0,
        )

    # Modes 2 + 3 require the live-gate env flag.
    if not live_flag_set:
        return build_grpc_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_LIVE_FLAG_NOT_SET,
            ready=True,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    client = Stage28_11ChainstackYellowstoneGrpcClient(
        runtime_config=runtime_config,
    )

    # --- 2. provider-connect-only -------------------------------------
    try:
        client.provider_connect_only(
            channel_factory=channel_factory,
        )
    except Stage28_11ConnectError:
        return build_grpc_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_CONNECT_FAILED,
            ready=True,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    if mode == MODE_PROVIDER_CONNECT_ONLY:
        return build_grpc_probe_result(
            mode=MODE_PROVIDER_CONNECT_ONLY,
            status=PROBE_STATUS_CONNECTED,
            refusal_reason=REFUSAL_REASON_NONE,
            ready=True,
            connected=True,
            decoded=False,
            decoded_payload=None,
            # Connect-only succeeded; the operator may proceed
            # to the one-event decode dry run. ``handoff_ready``
            # remains False because the dry-run sub-step has not
            # yet been exercised.
            handoff_ready=False,
            events_received=0,
        )

    # --- 3. one-event decode dry run ---------------------------------
    try:
        payload = client.one_event_decode_dry_run(
            channel_factory=channel_factory,
        )
    except Stage28_11ConnectError:
        return build_grpc_probe_result(
            mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_CONNECT_FAILED,
            ready=True,
            connected=True,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )
    except Stage28_11DecodeError as err:
        # Distinguish "no event received within the deadline"
        # from other decode failures so the operator can adjust
        # the timeout vs. inspect a real decode bug.
        no_event = err.reason == "NO_TRANSACTION_UPDATE_RECEIVED"
        return build_grpc_probe_result(
            mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                REFUSAL_REASON_NO_EVENT_RECEIVED
                if no_event
                else REFUSAL_REASON_DECODE_FAILED
            ),
            ready=True,
            connected=True,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )
    except Stage28_11GrpcError:
        # Any other Stage 28.11 error → decode-failed.
        return build_grpc_probe_result(
            mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_DECODE_FAILED,
            ready=True,
            connected=True,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    return build_grpc_probe_result(
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        status=PROBE_STATUS_DECODED,
        refusal_reason=REFUSAL_REASON_NONE,
        ready=True,
        connected=True,
        decoded=True,
        decoded_payload=payload,
        # All three sub-steps that the dry-run mode targets
        # passed: readiness, connect, decode. The operator MAY
        # now consider Stage 28.12 (Stage 28.9 wrapper with
        # ``max_events=1`` / ``max_dispatches=1``) under
        # separate explicit authorization. Stage 28.11 does NOT
        # invoke Stage 28.12 itself.
        handoff_ready=True,
        events_received=1,
    )


# ---------------------------------------------------------------------------
# Combined env -> probe entry point
# ---------------------------------------------------------------------------


def run_stage28_11_probe_from_env(
    *,
    mode: str,
    env: Optional[Mapping[str, str]] = None,
    channel_factory: Optional[object] = None,
) -> Stage28_11GrpcProbeResult:
    """End-to-end Stage 28.11 probe driven by the env.

    Reads the Stage 28.11 env-name surface via the readiness
    boundary, builds the runtime config + private secret, and
    invokes ``run_stage28_11_probe``. When the env did not pass
    readiness, returns a Stage 28.11 probe-result with the
    appropriate closed-set ``refusal_reason`` and status
    ``PROBE_STATUS_FAILED`` (or ``PROBE_STATUS_READY`` mapped to
    ``PROBE_STATUS_FAILED`` for non-readiness-only modes).

    Tests pass an explicit ``env`` mapping; production callers
    pass ``None`` to let the readiness layer consult
    ``os.environ`` once.
    """
    if not is_mode_value(mode):
        return build_grpc_probe_result(
            mode=MODE_READINESS_ONLY,
            status=PROBE_STATUS_FAILED,
            refusal_reason=REFUSAL_REASON_MODE_INVALID,
            ready=False,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    readiness_report = detect_stage28_11_grpc_readiness(env=env)
    if readiness_report.status != PROBE_STATUS_READY:
        return build_grpc_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=readiness_report.refusal_reason,
            ready=False,
            connected=False,
            decoded=False,
            decoded_payload=None,
            handoff_ready=False,
            events_received=0,
        )

    runtime_config = build_runtime_config_from_env(
        mode=mode,
        env=env,
    )
    return run_stage28_11_probe(
        runtime_config=runtime_config,
        mode=mode,
        live_flag_set=readiness_report.live_flag_set,
        channel_factory=channel_factory,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_runtime_config(
    record: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
) -> None:
    """Re-validate the runtime-config shape from inside the
    probe layer so an upstream construction by a caller that
    bypassed the builder still trips the safe-shape contract.

    Pure / deterministic. The Stage 28.11 dataclass already
    runs ``__post_init__`` validation; this helper provides a
    function-call seam for the probe's mode dispatch.
    """
    from PHX2.stage28.chainstack_yellowstone_grpc_models import (
        _validate_runtime_config_fields,
    )
    _validate_runtime_config_fields(record)


__all__ = (
    "run_stage28_11_probe",
    "run_stage28_11_probe_from_env",
)
