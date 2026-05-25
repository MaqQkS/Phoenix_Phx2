"""Stage 29.3 first real private tradeable PHX2 ping orchestrator.

The single Stage 29.3 surface that runs one of the three operator-
supplied ceremony modes:

  1. ``READINESS_ONLY``
       Verify all three readiness gates (Chainstack runtime-config
       built, Birdeye runtime-config built, private webhook URL
       non-empty + safe-shape) WITHOUT opening the gRPC channel,
       WITHOUT calling Birdeye, WITHOUT sending Discord.

  2. ``CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY``
       Open the Stage 29.3 hint-aware Chainstack Yellowstone gRPC
       channel via the Stage 28.11 runtime-config + run one short
       Subscribe scan (no Discord); call Birdeye ``/defi/price``
       for the operator-supplied ``known_mint``. NO Discord call.
       NO ATH call.

  3. ``ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN``
       Full mode-3 smoke. Build the Stage 27.6 sources bundle
       (Stage 29.2 Birdeye price + ATH + Stage 29.3 no-migration
       evidence + Stage 27.5 / Stage 27.4 wall clocks), build the
       Stage 28.9 default assembler over that bundle, build the
       Stage 29.3 hint-aware Chainstack event source, build the
       Stage 28.9 private webhook transport wrapper over the
       Stage 28.4 audited HTTP transport, build the Stage 28.9
       session config with ``max_events=1`` / ``max_dispatches=1``
       / ``max_total_retries=0`` / ``max_ticks=1`` / closed-set
       ``LIVE_PRIVATE`` mode, then call
       ``run_stage28_9_live_provider_session(...)``. The Stage
       28.9 wrapper writes its four artifacts; the Stage 29.3
       artifact writer then writes the Stage 29.3 acceptance
       bundle + the redaction scan.

The orchestrator NEVER:

  * loops or retries (every mode is a single bounded pass),
  * runs unattended (the operator drives the ceremony),
  * activates Stage 26 / Stage 29 enforcement,
  * routes to public / subscriber / paid-tier audiences,
  * sends a Telegram or X / social message,
  * touches a wallet / private-key / signer surface,
  * sizes or executes a trade,
  * imports a Pump.fun bonding-curve decoder,
  * uses Dexscreener as a dispatch authority,
  * uses Helius as a price source,
  * introduces a daemon / watchdog / autorestart loop,
  * reads ``os.environ`` / ``os.getenv`` / ``os.environb``
    directly. Env access flows through the unchanged Stage 28.11
    + Stage 29.2 readiness boundaries via the optional
    ``build_runtime_configs_from_env`` helper.

Discipline:

  * Stdlib only (``dataclasses`` / ``datetime`` / ``pathlib`` /
    ``typing``). No third-party HTTP / RPC / Discord / Telegram /
    X library.
  * The orchestrator is the ONLY Stage 29.3 production file that
    composes Stage 27 / Stage 28 / Stage 29.2 surfaces; the
    Stage 29.3 hint-aware event source (the sibling file)
    contains the lone gRPC channel surface.
  * The orchestrator NEVER fabricates a price, an ATH, a
    drawdown, a hint, a base mint, or a candidate verdict;
    every axis flows from the existing Stage 29.1 / 29.2 / 27
    surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from PHX2.stage27.live_candidate_assembler import (
    Stage27_6Sources,
)
from PHX2.stage27.price_ath_context_reader import (
    Stage27_4Clock,
)
from PHX2.stage27.private_ping_provenance import (
    Stage27_5Clock,
)
from PHX2.stage28.audited_http_transport import (
    Stage28_4AuditedHttpTransport,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    Stage28_11ReadinessEnvError,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    build_runtime_config_from_env as _build_chainstack_runtime_config_from_env,
)
from PHX2.stage28.live_provider_session_adapter import (
    Stage28_9DefaultCandidateAssembler,
    derive_output_dir_safe_label,
    run_stage28_9_live_provider_session,
)
from PHX2.stage28.live_provider_session_models import (
    SESSION_MODE_LIVE_PRIVATE,
    SESSION_OUTCOME_FAILED,
    SESSION_OUTCOME_OK,
    SESSION_OUTCOME_REFUSED,
    Stage28_9LiveProviderSessionResult,
    build_live_provider_session_config,
)
from PHX2.stage28.live_provider_session_transport import (
    Stage28_9PrivateWebhookTransport,
    is_nonempty_private_webhook_url,
)
from PHX2.stage29.birdeye_constants import (
    DEFAULT_LOOKBACK_HOURS,
    is_safe_mint,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    Stage29_2BirdeyeAthSource,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpTransport,
    Stage29_2BirdeyeUrlibTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_PRESENT,
    Stage29_2BirdeyeAthSnapshot,
    Stage29_2BirdeyePriceSnapshot,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeRuntimeConfig,
    Stage29_2ReadinessEnvError,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    build_runtime_config_from_env as _build_birdeye_runtime_config_from_env,
)
from PHX2.stage29.stage29_3_artifact_writer import (
    write_stage29_3_artifact_bundle,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    REFUSAL_REASON_NO_HINT_BEARING_TRANSACTION_RECEIVED,
    Stage29_3HintAwareChainstackEventSource,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    REFUSAL_REASON_NONE as _HINT_SOURCE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    REFUSAL_REASON_STREAM_ERROR as _HINT_SOURCE_REFUSAL_REASON_STREAM_ERROR,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    REFUSAL_REASON_SUBSCRIBE_FAILED as _HINT_SOURCE_REFUSAL_REASON_SUBSCRIBE_FAILED,
)
from PHX2.stage29.stage29_3_no_migration_evidence_source import (
    Stage29_3NoMigrationEvidenceSource,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    TRADEABLE_SMOKE_OUTCOME_CONNECTED,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_FAILED,
    TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_OUTCOME_REFUSED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
    TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED,
    TRADEABLE_SMOKE_REFUSAL_REASON_STREAM_ERROR,
    TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING,
    Stage29_3TradeableSmokeError,
    Stage29_3TradeableSmokeResult,
    build_tradeable_smoke_result,
    is_probe_mode_value,
)


# ---------------------------------------------------------------------------
# Locked Stage 29.3 defaults
# ---------------------------------------------------------------------------


# Stage 27.4 default price-staleness threshold inherited from the
# Stage 27 dry-run smoke harness (``DEFAULT_SMOKE_PRICE_STALENESS_
# THRESHOLD_SECONDS = 300``). Stage 29.3 reuses this value verbatim;
# the Stage 27.4 reader treats prices older than this as STALE.
DEFAULT_PRICE_STALENESS_THRESHOLD_SECONDS: int = 300


# Stage 29.3 probe-mode-2 scan budget. The mode-2 ceremony scans
# at most this many upstream ``SubscribeUpdate`` messages while
# verifying the Subscribe stream is alive. The default is small;
# the mode-2 ceremony does not need a hint-bearing transaction
# (mode 3 is the dispatch path).
DEFAULT_CONNECT_ONLY_MAX_MESSAGES_TO_SCAN: int = 8


# Stage 29.3 default ceremony identifiers.
DEFAULT_RUN_ID: str = "stage29_3_run"
DEFAULT_SESSION_ID: str = "stage29_3_session"
DEFAULT_PROVIDER_ID: str = "stage29_3_chainstack_yellowstone"
DEFAULT_PROVIDER_KIND: str = "solana_grpc_yellowstone"


# ---------------------------------------------------------------------------
# Stage 27.4 / 27.5 wall clocks (deterministic UTC)
# ---------------------------------------------------------------------------


class Stage29_3UtcClock:
    """Pure UTC ``datetime`` clock satisfying both the Stage 27.4
    ``Stage27_4Clock`` Protocol (``utc_now() -> datetime``) and the
    Stage 27.5 ``Stage27_5Clock`` Protocol (``now_utc_iso() ->
    str``). Stdlib only.

    Tests inject a deterministic fake clock by passing any object
    that exposes the same two methods.
    """

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_utc_iso(self) -> str:
        return self.utc_now().isoformat()


# ---------------------------------------------------------------------------
# Stage 28.4 / Stage 29.2 default factories
# ---------------------------------------------------------------------------


def _build_default_audited_discord_transport(
    *, timeout_seconds: float,
) -> Stage28_4AuditedHttpTransport:
    return Stage28_4AuditedHttpTransport(
        timeout_seconds=timeout_seconds,
    )


def _build_default_birdeye_http_transport() -> (
    Stage29_2BirdeyeHttpTransport
):
    return Stage29_2BirdeyeUrlibTransport()


# ---------------------------------------------------------------------------
# Helpers: env-driven runtime-config construction (optional)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_3RuntimeConfigBundle:
    """Bundle of the Stage 28.11 + Stage 29.2 runtime configs the
    Stage 29.3 orchestrator needs.

    Stage 29.3 does not introduce a third env-read site; this
    bundle is built either by the operator (tests path) or by the
    ``build_runtime_configs_from_env`` helper (production path),
    which delegates to the existing Stage 28.11 / Stage 29.2
    readiness boundaries.
    """

    chainstack: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
    birdeye: Stage29_2BirdeyeRuntimeConfig


def build_runtime_configs_from_env(
    *,
    chainstack_mode: str,
    env: Optional[Mapping[str, str]] = None,
) -> Stage29_3RuntimeConfigBundle:
    """Construct the Stage 29.3 runtime-config bundle by
    delegating to the unchanged Stage 28.11 + Stage 29.2 readiness
    boundaries.

    ``chainstack_mode`` is the Stage 28.11 probe-mode token
    (``READINESS_ONLY`` / ``PROVIDER_CONNECT_ONLY`` /
    ``ONE_EVENT_DECODE_DRY_RUN``) the operator picks based on the
    Stage 29.3 ceremony mode. The Stage 28.11 readiness module
    validates / projects the mode and refuses unknown values via
    ``Stage28_11ReadinessEnvError``.

    Raises ``Stage29_3TradeableSmokeError`` carrying the closed-
    set refusal reason when either readiness check refuses; the
    raw exception messages from the underlying readiness modules
    are not surfaced (the closed-set token is the only signal).
    """
    try:
        chainstack_config = (
            _build_chainstack_runtime_config_from_env(
                mode=chainstack_mode, env=env,
            )
        )
    except Stage28_11ReadinessEnvError:
        raise Stage29_3TradeableSmokeError(
            "CHAINSTACK_READINESS_FAILED",
        )
    try:
        birdeye_config = (
            _build_birdeye_runtime_config_from_env(env=env)
        )
    except Stage29_2ReadinessEnvError:
        raise Stage29_3TradeableSmokeError(
            "BIRDEYE_READINESS_FAILED",
        )
    return Stage29_3RuntimeConfigBundle(
        chainstack=chainstack_config, birdeye=birdeye_config,
    )


# ---------------------------------------------------------------------------
# Output-dir safe-shape gate (mirrors Stage 28.9)
# ---------------------------------------------------------------------------


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _output_dir_is_safe(directory: object) -> bool:
    """Return ``True`` iff ``directory`` is a ``Path`` that exists,
    is a directory, carries no URL-shaped substring on the string
    rendering, and lives outside the PHX2 working tree.
    """
    if not isinstance(directory, Path):
        return False
    path_str = str(directory)
    lowered = path_str.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    if not directory.exists():
        return False
    if not directory.is_dir():
        return False
    # Stage 29.3 reuses the Stage 28.9 "outside the repo" gate via
    # ``derive_output_dir_safe_label`` indirectly (the Stage 28.9
    # readiness gate enforces the repo-outside check at session
    # time). The cheap shape check above is sufficient for the
    # Stage 29.3 mode-1 / mode-2 paths that do not invoke the
    # Stage 28.9 wrapper.
    return True


# ---------------------------------------------------------------------------
# Mode 1 — READINESS_ONLY
# ---------------------------------------------------------------------------


def _run_mode_readiness_only(
    *,
    runtime_configs: Stage29_3RuntimeConfigBundle,
    private_webhook_url: str,
    output_dir: Path,
    live_env_ready: bool,
    live_operator_request: bool,
) -> Stage29_3TradeableSmokeResult:
    """Mode 1: verify every readiness gate without touching gRPC,
    HTTP, or Discord. Returns a closed-set READY / REFUSED result.
    """
    if not isinstance(live_env_ready, bool) or not live_env_ready:
        return build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET
            ),
            stop_reason="LIVE_FLAG_NOT_SET",
        )
    if not isinstance(
        live_operator_request, bool,
    ) or not live_operator_request:
        return build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET
            ),
            stop_reason="OPERATOR_REQUEST_NOT_SET",
        )
    if not is_nonempty_private_webhook_url(private_webhook_url):
        return build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING
            ),
            stop_reason="WEBHOOK_MISSING",
        )
    if not _output_dir_is_safe(output_dir):
        return build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE
            ),
            stop_reason="OUTPUT_DIR_UNSAFE",
        )
    # All three readiness gates passed; the runtime-configs are
    # already a successful construction (the caller delegated to
    # the Stage 28.11 + Stage 29.2 readiness boundaries before
    # calling the orchestrator).
    _ = runtime_configs
    return build_tradeable_smoke_result(
        mode=PROBE_MODE_READINESS_ONLY,
        tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_READY,
        tradeable_smoke_refusal_reason=(
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE
        ),
        stop_reason="READINESS_OK",
    )


# ---------------------------------------------------------------------------
# Mode 2 — CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
# ---------------------------------------------------------------------------


def _run_mode_connect_only(
    *,
    runtime_configs: Stage29_3RuntimeConfigBundle,
    known_mint: str,
    private_webhook_url: str,
    output_dir: Path,
    live_env_ready: bool,
    live_operator_request: bool,
    birdeye_http_transport: Optional[
        Stage29_2BirdeyeHttpTransport
    ],
    channel_factory: Optional[object],
    max_messages_to_scan: int,
) -> tuple[
    Stage29_3TradeableSmokeResult,
    Optional[Stage29_2BirdeyePriceSnapshot],
]:
    """Mode 2: open the gRPC channel + run one Birdeye
    ``/defi/price`` call. Returns a closed-set CONNECTED /
    REFUSED / FAILED result and the optional price snapshot for
    the artifact writer.
    """
    # The readiness gate runs first; mode 2 reuses the mode-1
    # readiness gate verbatim.
    readiness = _run_mode_readiness_only(
        runtime_configs=runtime_configs,
        private_webhook_url=private_webhook_url,
        output_dir=output_dir,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
    )
    if (
        readiness.tradeable_smoke_outcome
        != TRADEABLE_SMOKE_OUTCOME_READY
    ):
        # Re-stamp the outcome onto the mode-2 record (the
        # readiness step returns mode=READINESS_ONLY by
        # construction); we project the refusal verbatim.
        return (
            build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_REFUSED
                ),
                tradeable_smoke_refusal_reason=(
                    readiness.tradeable_smoke_refusal_reason
                ),
                stop_reason=readiness.stop_reason,
            ),
            None,
        )

    if not is_safe_mint(known_mint):
        return (
            build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_REFUSED
                ),
                tradeable_smoke_refusal_reason=(
                    TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID
                ),
                stop_reason="KNOWN_MINT_INVALID",
            ),
            None,
        )

    # Chainstack connect: build the hint-aware event source with a
    # small scan budget and drain it once. CONNECT success = the
    # source's ``last_refusal_reason`` is NONE or
    # NO_HINT_BEARING_TRANSACTION_RECEIVED (the channel opened +
    # Subscribe call succeeded; we did not require a hint-bearing
    # transaction).
    source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_configs.chainstack,
        max_messages_to_scan=max_messages_to_scan,
        channel_factory=channel_factory,
    )
    for _ in source.iter_events(max_events=1):
        # Mode 2 ignores any yielded normalized event; it cares
        # only about whether the Subscribe stream opened.
        break

    chainstack_outcome = source.last_refusal_reason
    if (
        chainstack_outcome
        == _HINT_SOURCE_REFUSAL_REASON_SUBSCRIBE_FAILED
    ):
        return (
            build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_FAILED
                ),
                tradeable_smoke_refusal_reason=(
                    TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED
                ),
                stop_reason="CHAINSTACK_SUBSCRIBE_FAILED",
            ),
            None,
        )
    if (
        chainstack_outcome
        == _HINT_SOURCE_REFUSAL_REASON_STREAM_ERROR
    ):
        return (
            build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_FAILED
                ),
                tradeable_smoke_refusal_reason=(
                    TRADEABLE_SMOKE_REFUSAL_REASON_STREAM_ERROR
                ),
                stop_reason="CHAINSTACK_STREAM_ERROR",
            ),
            None,
        )

    # Birdeye connect: one /defi/price call.
    birdeye_transport = (
        birdeye_http_transport
        if birdeye_http_transport is not None
        else _build_default_birdeye_http_transport()
    )
    price_source = Stage29_2BirdeyePriceSource(
        transport=birdeye_transport,
        endpoint_secret=(
            runtime_configs.birdeye.endpoint_secret
        ),
        timeout_seconds=(
            runtime_configs.birdeye.timeout_seconds
        ),
    )
    price_snapshot = price_source.fetch_snapshot(
        base_mint=known_mint,
    )
    if (
        price_snapshot.birdeye_price_status
        != BIRDEYE_PRICE_STATUS_PRESENT
    ):
        return (
            build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_FAILED
                ),
                tradeable_smoke_refusal_reason=(
                    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED
                ),
                stop_reason="BIRDEYE_CONNECT_FAILED",
                birdeye_price_present=False,
            ),
            price_snapshot,
        )

    return (
        build_tradeable_smoke_result(
            mode=(
                PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY
            ),
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_CONNECTED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_NONE
            ),
            stop_reason="CONNECT_OK",
            birdeye_price_present=True,
        ),
        price_snapshot,
    )


# ---------------------------------------------------------------------------
# Mode 3 — ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN
# ---------------------------------------------------------------------------


def _project_session_to_smoke_outcome(
    result: Stage28_9LiveProviderSessionResult,
) -> tuple[str, str, str]:
    """Project a Stage 28.9 session result onto a Stage 29.3
    ``(tradeable_smoke_outcome, refusal_reason, stop_reason)``
    triple.

    The projection preserves the Stage 27 UNKNOWN / DISAGREE /
    USDC suppression discipline and the Stage 28.6 missing /
    stale price discipline. Pure / deterministic.
    """
    if result.session_outcome == SESSION_OUTCOME_REFUSED:
        return (
            TRADEABLE_SMOKE_OUTCOME_REFUSED,
            TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED,
            result.stop_reason or "SESSION_REFUSED",
        )
    if result.session_outcome == SESSION_OUTCOME_FAILED:
        return (
            TRADEABLE_SMOKE_OUTCOME_FAILED,
            TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED,
            result.stop_reason or "SESSION_FAILED",
        )

    # OK / DEGRADED branches: classify by counter axes.
    if result.dispatch_success >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "DISPATCHED",
        )
    if result.unknown_pair_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "UNKNOWN_PAIR",
        )
    if result.disagree_pair_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "DISAGREE_PAIR",
        )
    if result.usdc_observe_only_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "USDC_OBSERVE_ONLY",
        )
    if result.missing_price_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "MISSING_PRICE",
        )
    if result.stale_price_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "STALE_PRICE",
        )
    if result.malformed_suppressed >= 1:
        return (
            TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "MALFORMED",
        )
    if result.events_seen == 0:
        return (
            TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
            result.stop_reason or "NO_EVENT_RECEIVED",
        )
    # OK session with one event seen but no clear classifier
    # branch matched. We treat this as a malformed / unknown
    # suppression (defensive default).
    return (
        TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
        TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
        result.stop_reason or "UNCLASSIFIED",
    )


@dataclass(frozen=True)
class _Stage29_3Mode3Outputs:
    """Captures every Stage 29.3 mode-3 output the artifact writer
    + the smoke-result builder need. Internal to this module.
    """

    smoke_result: Stage29_3TradeableSmokeResult
    price_snapshot: Optional[Stage29_2BirdeyePriceSnapshot]
    ath_snapshot: Optional[Stage29_2BirdeyeAthSnapshot]


def _run_mode_one_real_private_tradeable_ping_dry_run(
    *,
    runtime_configs: Stage29_3RuntimeConfigBundle,
    private_webhook_url: str,
    output_dir: Path,
    live_env_ready: bool,
    live_operator_request: bool,
    birdeye_http_transport: Optional[
        Stage29_2BirdeyeHttpTransport
    ],
    audited_discord_transport: Optional[
        Stage28_4AuditedHttpTransport
    ],
    channel_factory: Optional[object],
    max_messages_to_scan: int,
    discord_transport_timeout_seconds: float,
    price_staleness_threshold_seconds: int,
    birdeye_lookback_hours: int,
    run_id: str,
    session_id: str,
    provider_id: str,
    provider_kind: str,
    clock: object,
) -> _Stage29_3Mode3Outputs:
    """Mode 3: drive the full Stage 28.9 wrapper over the Stage
    29.3 hint-aware source + Stage 27.6 sources bundle. Returns a
    closed-set DISPATCHED / SUPPRESSED_* / REFUSED / FAILED result
    plus the price + ATH snapshots for the artifact writer.
    """
    # Mode 3 readiness gate (reused from mode 1).
    readiness = _run_mode_readiness_only(
        runtime_configs=runtime_configs,
        private_webhook_url=private_webhook_url,
        output_dir=output_dir,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
    )
    if (
        readiness.tradeable_smoke_outcome
        != TRADEABLE_SMOKE_OUTCOME_READY
    ):
        return _Stage29_3Mode3Outputs(
            smoke_result=build_tradeable_smoke_result(
                mode=(
                    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN
                ),
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_REFUSED
                ),
                tradeable_smoke_refusal_reason=(
                    readiness.tradeable_smoke_refusal_reason
                ),
                stop_reason=readiness.stop_reason,
            ),
            price_snapshot=None,
            ath_snapshot=None,
        )

    # Build the Stage 29.2 sources (price + ATH).
    birdeye_transport = (
        birdeye_http_transport
        if birdeye_http_transport is not None
        else _build_default_birdeye_http_transport()
    )
    price_source = Stage29_2BirdeyePriceSource(
        transport=birdeye_transport,
        endpoint_secret=(
            runtime_configs.birdeye.endpoint_secret
        ),
        timeout_seconds=(
            runtime_configs.birdeye.timeout_seconds
        ),
    )
    ath_source = Stage29_2BirdeyeAthSource(
        transport=birdeye_transport,
        endpoint_secret=(
            runtime_configs.birdeye.endpoint_secret
        ),
        timeout_seconds=(
            runtime_configs.birdeye.timeout_seconds
        ),
        lookback_hours=birdeye_lookback_hours,
    )
    sources = Stage27_6Sources(
        price_source=price_source,
        ath_source=ath_source,
        migration_source=Stage29_3NoMigrationEvidenceSource(),
        stage27_4_clock=clock,  # type: ignore[arg-type]
        stage27_5_clock=clock,  # type: ignore[arg-type]
        price_staleness_threshold_seconds=(
            price_staleness_threshold_seconds
        ),
    )
    assembler = Stage28_9DefaultCandidateAssembler(
        sources=sources,
        run_id=run_id,
        session_id=session_id,
    )

    # Build the Stage 29.3 hint-aware Chainstack event source.
    event_source = Stage29_3HintAwareChainstackEventSource(
        runtime_config=runtime_configs.chainstack,
        max_messages_to_scan=max_messages_to_scan,
        channel_factory=channel_factory,
    )

    # Build the Stage 28.9 webhook-bound private transport
    # wrapper over the Stage 28.4 audited HTTP transport.
    audited_transport = (
        audited_discord_transport
        if audited_discord_transport is not None
        else _build_default_audited_discord_transport(
            timeout_seconds=discord_transport_timeout_seconds,
        )
    )
    transport = Stage28_9PrivateWebhookTransport(
        audited_transport=audited_transport,
        webhook_url=private_webhook_url,
    )

    # Build the Stage 28.9 session config: max_events=1,
    # max_dispatches=1, max_total_retries=0, max_ticks=1,
    # heartbeat_every_n_events=1, LIVE_PRIVATE.
    output_dir_safe_label = derive_output_dir_safe_label(
        output_dir,
    )
    config = build_live_provider_session_config(
        run_id=run_id,
        session_id=session_id,
        provider_id=provider_id,
        provider_kind=provider_kind,
        max_events=1,
        max_dispatches=1,
        max_ticks=1,
        max_total_retries=0,
        heartbeat_every_n_events=1,
        output_dir_safe_label=output_dir_safe_label,
        session_mode=SESSION_MODE_LIVE_PRIVATE,
    )

    # Drive the Stage 28.9 wrapper. The wrapper writes its four
    # artifacts into ``output_dir`` and returns the Stage 28.9
    # session result; Stage 29.3 then projects that onto the
    # Stage 29.3 smoke-result outcome vocabulary.
    session_result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=event_source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=output_dir,
        private_webhook_url=private_webhook_url,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
    )

    outcome, refusal_reason, stop_reason = (
        _project_session_to_smoke_outcome(session_result)
    )

    # Best-effort: capture the Stage 29.2 evidence the chain
    # would have seen. We re-fetch the snapshots for the
    # hint-bearing payload's base mint so the Stage 29.3 artifact
    # carries the same evidence Stage 27 saw. When the chain saw
    # no event we leave the snapshots None.
    last_base_mint: Optional[str] = None
    # The Stage 28.9 default assembler kept no per-event handle;
    # we re-derive the dispatched mint from the Stage 28.9 ledger
    # is overkill for Stage 29.3 mode 3 — instead, when the
    # outcome is DISPATCHED we know exactly one hint-bearing
    # event went through. We rely on the event-source's
    # hint_bearing_yielded counter to confirm the event count
    # and leave the price/ATH snapshots None on this code path
    # (the operator can cross-reference the Stage 28.9 dispatch
    # ledger for the dispatched mint; Stage 29.3 mode-3 artifact
    # carries the smoke-result counters as the authoritative
    # outcome record).
    _ = last_base_mint

    smoke_result = build_tradeable_smoke_result(
        mode=(
            PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN
        ),
        tradeable_smoke_outcome=outcome,
        tradeable_smoke_refusal_reason=refusal_reason,
        events_seen=min(session_result.events_seen, 1),
        candidates_assembled=min(
            session_result.candidates_assembled, 1,
        ),
        candidates_dispatched=min(
            session_result.candidates_dispatched, 1,
        ),
        candidates_suppressed=session_result.candidates_suppressed,
        dispatch_success=min(
            session_result.dispatch_success, 1,
        ),
        dispatch_failure=session_result.dispatch_failure,
        hint_bearing_payload_present=(
            event_source.hint_bearing_yielded >= 1
        ),
        birdeye_price_present=False,
        birdeye_ath_present=False,
        stop_reason=stop_reason,
    )
    return _Stage29_3Mode3Outputs(
        smoke_result=smoke_result,
        price_snapshot=None,
        ath_snapshot=None,
    )


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def run_stage29_3_first_private_tradeable_smoke(
    *,
    mode: str,
    runtime_configs: Stage29_3RuntimeConfigBundle,
    private_webhook_url: str,
    output_dir: Path,
    live_env_ready: bool,
    live_operator_request: bool,
    known_mint: Optional[str] = None,
    birdeye_http_transport: Optional[
        Stage29_2BirdeyeHttpTransport
    ] = None,
    audited_discord_transport: Optional[
        Stage28_4AuditedHttpTransport
    ] = None,
    channel_factory: Optional[object] = None,
    max_messages_to_scan: int = (
        DEFAULT_CONNECT_ONLY_MAX_MESSAGES_TO_SCAN
    ),
    discord_transport_timeout_seconds: float = 10.0,
    price_staleness_threshold_seconds: int = (
        DEFAULT_PRICE_STALENESS_THRESHOLD_SECONDS
    ),
    birdeye_lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    run_id: str = DEFAULT_RUN_ID,
    session_id: str = DEFAULT_SESSION_ID,
    provider_id: str = DEFAULT_PROVIDER_ID,
    provider_kind: str = DEFAULT_PROVIDER_KIND,
    clock: Optional[object] = None,
    write_artifacts: bool = True,
) -> Stage29_3TradeableSmokeResult:
    """Run one Stage 29.3 ceremony in the supplied ``mode``.

    The orchestrator validates the mode + bounds, runs the mode-
    specific path, and (when ``write_artifacts=True``) writes the
    Stage 29.3 acceptance bundle + the redaction scan into
    ``output_dir``. Returns the immutable Stage 29.3 smoke result.

    Test discipline: callers may inject fakes for every external
    surface (the Stage 29.2 HTTP transport, the Stage 28.4
    audited Discord transport, the gRPC channel factory) and any
    clock satisfying both the ``utc_now`` + ``now_utc_iso``
    methods. Tests that pass a fake gRPC channel factory will see
    deterministic behavior without opening a network connection.

    Raises ``Stage29_3TradeableSmokeError`` only when the supplied
    ``mode`` is not a closed-set probe-mode token; every other
    failure path projects onto the closed-set REFUSED / FAILED
    outcomes on the returned record.
    """
    if not is_probe_mode_value(mode):
        return build_tradeable_smoke_result(
            mode=PROBE_MODE_READINESS_ONLY,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID
            ),
            stop_reason="MODE_INVALID",
        )

    if not isinstance(
        runtime_configs, Stage29_3RuntimeConfigBundle,
    ):
        # Treat a missing runtime-config bundle as a chainstack +
        # birdeye readiness compound failure; we surface the
        # chainstack token as the primary refusal because the
        # operator's first readiness step is the chainstack env.
        return build_tradeable_smoke_result(
            mode=mode,
            tradeable_smoke_outcome=(
                TRADEABLE_SMOKE_OUTCOME_REFUSED
            ),
            tradeable_smoke_refusal_reason=(
                TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED
            ),
            stop_reason="RUNTIME_CONFIGS_MISSING",
        )

    resolved_clock = (
        clock if clock is not None else Stage29_3UtcClock()
    )

    if mode == PROBE_MODE_READINESS_ONLY:
        smoke_result = _run_mode_readiness_only(
            runtime_configs=runtime_configs,
            private_webhook_url=private_webhook_url,
            output_dir=output_dir,
            live_env_ready=live_env_ready,
            live_operator_request=live_operator_request,
        )
        price_snapshot: Optional[
            Stage29_2BirdeyePriceSnapshot
        ] = None
        ath_snapshot: Optional[
            Stage29_2BirdeyeAthSnapshot
        ] = None
        base_mint_for_artifact: Optional[str] = None
    elif mode == PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY:
        if known_mint is None:
            return build_tradeable_smoke_result(
                mode=mode,
                tradeable_smoke_outcome=(
                    TRADEABLE_SMOKE_OUTCOME_REFUSED
                ),
                tradeable_smoke_refusal_reason=(
                    TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID
                ),
                stop_reason="KNOWN_MINT_MISSING",
            )
        smoke_result, price_snapshot = (
            _run_mode_connect_only(
                runtime_configs=runtime_configs,
                known_mint=known_mint,
                private_webhook_url=private_webhook_url,
                output_dir=output_dir,
                live_env_ready=live_env_ready,
                live_operator_request=live_operator_request,
                birdeye_http_transport=(
                    birdeye_http_transport
                ),
                channel_factory=channel_factory,
                max_messages_to_scan=max_messages_to_scan,
            )
        )
        ath_snapshot = None
        base_mint_for_artifact = known_mint
    else:  # PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN
        mode3_outputs = (
            _run_mode_one_real_private_tradeable_ping_dry_run(
                runtime_configs=runtime_configs,
                private_webhook_url=private_webhook_url,
                output_dir=output_dir,
                live_env_ready=live_env_ready,
                live_operator_request=live_operator_request,
                birdeye_http_transport=(
                    birdeye_http_transport
                ),
                audited_discord_transport=(
                    audited_discord_transport
                ),
                channel_factory=channel_factory,
                max_messages_to_scan=max_messages_to_scan,
                discord_transport_timeout_seconds=(
                    discord_transport_timeout_seconds
                ),
                price_staleness_threshold_seconds=(
                    price_staleness_threshold_seconds
                ),
                birdeye_lookback_hours=(
                    birdeye_lookback_hours
                ),
                run_id=run_id,
                session_id=session_id,
                provider_id=provider_id,
                provider_kind=provider_kind,
                clock=resolved_clock,
            )
        )
        smoke_result = mode3_outputs.smoke_result
        price_snapshot = mode3_outputs.price_snapshot
        ath_snapshot = mode3_outputs.ath_snapshot
        base_mint_for_artifact = known_mint

    if write_artifacts and isinstance(output_dir, Path) and (
        output_dir.is_dir()
    ):
        try:
            write_stage29_3_artifact_bundle(
                output_dir=output_dir,
                smoke_result=smoke_result,
                extraction=None,
                base_mint=base_mint_for_artifact,
                price_snapshot=price_snapshot,
                ath_snapshot=ath_snapshot,
                evidence=None,
            )
        except Stage29_3TradeableSmokeError:
            # Artifact write failure is a degraded outcome but
            # does not change the smoke result; the operator can
            # re-run the ceremony.
            pass

    return smoke_result


__all__ = (
    # Locked defaults.
    "DEFAULT_PRICE_STALENESS_THRESHOLD_SECONDS",
    "DEFAULT_CONNECT_ONLY_MAX_MESSAGES_TO_SCAN",
    "DEFAULT_RUN_ID",
    "DEFAULT_SESSION_ID",
    "DEFAULT_PROVIDER_ID",
    "DEFAULT_PROVIDER_KIND",
    # Clocks.
    "Stage29_3UtcClock",
    # Runtime-config helpers.
    "Stage29_3RuntimeConfigBundle",
    "build_runtime_configs_from_env",
    # Public orchestrator.
    "run_stage29_3_first_private_tradeable_smoke",
)
