"""Stage 29.2 Birdeye live-probe orchestrator.

The single Stage 29.2 surface that ties the Stage 29.2
readiness + HTTP transport + price source + ATH source surfaces
together into a bounded one-shot probe. Returns a
``Stage29_2BirdeyeHintProbeResult`` carrying the closed-set
status + refusal-reason tokens + a Stage 29.2 evidence record
(when mode 3 produced one) + safe length / live-flag /
timeout / handoff axes.

The probe orchestrator is the SECOND Stage 29.2 production
module allowed to *invoke* outbound HTTP via the Stage 29.2
HTTP transport (it does not import ``urllib`` directly; it
instantiates ``Stage29_2BirdeyeUrlibTransport`` when no
caller-supplied transport factory is provided).

The probe NEVER:

  * sends a Discord message,
  * sends a Telegram / X / social message,
  * touches a wallet / private-key / signer surface,
  * sizes / executes a trade,
  * invokes Stage 26 enforcement,
  * invokes the Stage 28.9 wrapper / Stage 28.6 runner / Stage
    28.4 transport,
  * persists an artifact on its own (the operator's caller is
    responsible for writing the result to an artifact directory
    outside the PHX2 tree),
  * retries on failure (one shot, no retries).

This module imports stdlib (``datetime`` / ``decimal`` /
``typing``) plus the Stage 29.2 constants / models / readiness
/ http transport / price source / ATH source / probe-models
modules + the Stage 29.1 manifest (for the re-exported
``WRAPPED_SOL_MINT`` constant used by the HTTP_CONNECT_ONLY
mode). It does NOT import:

  * Stage 21-28 production code,
  * any PHX1 / legacy Phoenix-1 source tree module,
  * any third-party HTTP / wallet / trading / Discord / Telegram
    / X library,
  * ``os`` / the process environment (the Stage 29.2 readiness
    module owns the only env-read boundary).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Optional

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_DEFAULT_OHLCV_TYPE,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_LOOKBACK_HOURS,
    is_allowed_ohlcv_type,
    is_safe_lookback_hours,
    is_safe_mint,
)
from PHX2.stage29.stage29_1_manifest import (
    WRAPPED_SOL_MINT,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    fetch_birdeye_ath_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpTransport,
    Stage29_2BirdeyeUrlibTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_FRESHNESS_STATUS_STALE,
    BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID,
    BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE,
    BIRDEYE_REFUSAL_REASON_MODE_INVALID,
    BIRDEYE_REFUSAL_REASON_NONE,
    BIRDEYE_REFUSAL_REASON_OHLCV_TYPE_INVALID,
    BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE,
    NO_INVENTION_AUDIT_FAILED,
    NO_INVENTION_AUDIT_PASSED,
    Stage29_2BirdeyeAthSnapshot,
    Stage29_2BirdeyePriceSnapshot,
    build_birdeye_evidence_record,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    fetch_birdeye_price_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_probe_models import (
    PROBE_MODE_HTTP_CONNECT_ONLY,
    PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE,
    PROBE_STATUS_FETCHED_PRICE_ONLY,
    PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_READY,
    PROBE_STATUS_SKIPPED,
    Stage29_2BirdeyeHintProbeResult,
    build_hint_probe_result,
    is_probe_mode_value,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    READINESS_STATUS_READY,
    Stage29_2BirdeyeRuntimeConfig,
    Stage29_2ReadinessEnvError,
    build_runtime_config_from_env,
    detect_stage29_2_birdeye_readiness,
)


# Transport factory type: callable that returns a fresh transport
# instance. The default factory returns ``Stage29_2BirdeyeUrlibTransport``.
TransportFactory = Callable[[], Stage29_2BirdeyeHttpTransport]


# Bounded staleness threshold for the probe-layer freshness
# verdict (seconds between the price snapshot's
# ``fetched_at_utc`` and the probe's wall-clock now). The
# Stage 27.4 reader has its own staleness threshold; this
# probe-layer threshold is purely for the operator audit log.
PROBE_FRESHNESS_STALENESS_THRESHOLD_SECONDS: int = 300


def _default_transport_factory() -> Stage29_2BirdeyeHttpTransport:
    return Stage29_2BirdeyeUrlibTransport()


# ---------------------------------------------------------------------------
# Probe orchestrator
# ---------------------------------------------------------------------------


def run_stage29_2_birdeye_probe(
    *,
    mode: str,
    base_mint: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    transport_factory: Optional[TransportFactory] = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    ohlcv_type: str = BIRDEYE_DEFAULT_OHLCV_TYPE,
    migration_timestamp_utc: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> Stage29_2BirdeyeHintProbeResult:
    """Run a Stage 29.2 Birdeye live probe in the given mode.

    Modes:

      * ``READINESS_ONLY`` -- no network. Asserts the env-read
        boundary projects cleanly and the readiness verdict is
        ``READY``. Returns the readiness axes + handoff_ready.
      * ``HTTP_CONNECT_ONLY`` -- exactly one outbound
        ``GET /defi/price?address=<WRAPPED_SOL_MINT>`` to prove
        credentials are accepted. Reports HTTP status code.
      * ``ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN`` -- takes the
        caller-supplied ``base_mint`` (from the Stage 29.1
        PumpSwap probe), makes at most two outbound requests
        (one ``/defi/price`` + one ``/defi/ohlcv``), builds a
        Stage 29.2 evidence record (with locally-computed
        drawdown for telemetry), and runs the no-invention
        audit.

    NEVER retries. NEVER loops. NEVER persists an artifact.
    """
    if not is_probe_mode_value(mode):
        safe_mode = mode if isinstance(mode, str) else ""
        return build_hint_probe_result(
            mode=safe_mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=BIRDEYE_REFUSAL_REASON_MODE_INVALID,
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=0,
            base_url_length=0,
            live_flag_set=False,
            timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
            handoff_ready=False,
        )
    if transport_factory is not None and not callable(
        transport_factory
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=0,
            base_url_length=0,
            live_flag_set=False,
            timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
            handoff_ready=False,
        )

    # ---------- READINESS_ONLY ----------
    report = detect_stage29_2_birdeye_readiness(env=env)
    if mode == PROBE_MODE_READINESS_ONLY:
        if report.status != READINESS_STATUS_READY:
            return build_hint_probe_result(
                mode=mode,
                status=PROBE_STATUS_NOT_READY,
                refusal_reason=report.refusal_reason,
                base_mint=base_mint,
                evidence=None,
                http_status_code=0,
                api_key_length=report.api_key_length,
                base_url_length=report.base_url_length,
                live_flag_set=report.live_flag_set,
                timeout_seconds=report.timeout_seconds,
                handoff_ready=False,
            )
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_READY,
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=True,
        )

    # ---------- modes 2 + 3 share a readiness + live-gate guard ----------
    if report.status != READINESS_STATUS_READY:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=report.refusal_reason,
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )
    if not report.live_flag_set:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    try:
        runtime_config: Stage29_2BirdeyeRuntimeConfig = (
            build_runtime_config_from_env(env=env)
        )
    except Stage29_2ReadinessEnvError as exc:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_SKIPPED,
            refusal_reason=exc.refusal_reason,
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    factory = (
        transport_factory
        if transport_factory is not None
        else _default_transport_factory
    )
    try:
        transport = factory()
    except Exception:
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    # ---------- HTTP_CONNECT_ONLY ----------
    if mode == PROBE_MODE_HTTP_CONNECT_ONLY:
        snapshot = fetch_birdeye_price_snapshot(
            base_mint=WRAPPED_SOL_MINT,
            transport=transport,
            endpoint_secret=runtime_config.endpoint_secret,
            timeout_seconds=runtime_config.timeout_seconds,
        )
        if (
            snapshot.birdeye_price_status
            == BIRDEYE_PRICE_STATUS_PRESENT
        ):
            return build_hint_probe_result(
                mode=mode,
                status=PROBE_STATUS_CONNECTED,
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                base_mint=base_mint,
                evidence=None,
                http_status_code=200,
                api_key_length=report.api_key_length,
                base_url_length=report.base_url_length,
                live_flag_set=report.live_flag_set,
                timeout_seconds=report.timeout_seconds,
                handoff_ready=True,
            )
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=_map_snapshot_failure_to_refusal(
                snapshot,
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    # ---------- ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN ----------
    if mode != PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN:
        # Defensive: unreachable given the closed-set guard
        # above, but keeps the function total.
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=BIRDEYE_REFUSAL_REASON_MODE_INVALID,
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    if not isinstance(base_mint, str) or not is_safe_mint(
        base_mint
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )
    if not is_safe_lookback_hours(lookback_hours):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )
    if not is_allowed_ohlcv_type(ohlcv_type):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FAILED,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_OHLCV_TYPE_INVALID
            ),
            base_mint=base_mint,
            evidence=None,
            http_status_code=0,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )

    price_snapshot = fetch_birdeye_price_snapshot(
        base_mint=base_mint,
        transport=transport,
        endpoint_secret=runtime_config.endpoint_secret,
        timeout_seconds=runtime_config.timeout_seconds,
    )
    ath_snapshot = fetch_birdeye_ath_snapshot(
        base_mint=base_mint,
        transport=transport,
        endpoint_secret=runtime_config.endpoint_secret,
        timeout_seconds=runtime_config.timeout_seconds,
        lookback_hours=lookback_hours,
        ohlcv_type=ohlcv_type,
        now_utc=now_utc,
        migration_timestamp_utc=migration_timestamp_utc,
    )

    drawdown_ratio = _compute_drawdown_ratio(
        price_snapshot, ath_snapshot
    )
    freshness_status = _combine_freshness(
        price_snapshot, ath_snapshot
    )
    audit = _no_invention_audit(price_snapshot, ath_snapshot)
    evidence = build_birdeye_evidence_record(
        base_mint=base_mint,
        price_snapshot=price_snapshot,
        ath_snapshot=ath_snapshot,
        drawdown_ratio=drawdown_ratio,
        freshness_status=freshness_status,
        no_invention_audit=audit,
    )

    if (
        price_snapshot.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_PRESENT
        and ath_snapshot.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_PRESENT
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH,
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            base_mint=base_mint,
            evidence=evidence,
            http_status_code=200,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=True,
        )
    if (
        price_snapshot.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_PRESENT
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FETCHED_PRICE_ONLY,
            refusal_reason=_map_snapshot_failure_to_refusal(
                ath_snapshot
            ),
            base_mint=base_mint,
            evidence=evidence,
            http_status_code=200,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )
    if (
        ath_snapshot.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_PRESENT
    ):
        return build_hint_probe_result(
            mode=mode,
            status=PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE,
            refusal_reason=_map_snapshot_failure_to_refusal(
                price_snapshot
            ),
            base_mint=base_mint,
            evidence=evidence,
            http_status_code=200,
            api_key_length=report.api_key_length,
            base_url_length=report.base_url_length,
            live_flag_set=report.live_flag_set,
            timeout_seconds=report.timeout_seconds,
            handoff_ready=False,
        )
    return build_hint_probe_result(
        mode=mode,
        status=PROBE_STATUS_FAILED,
        refusal_reason=_map_snapshot_failure_to_refusal(
            price_snapshot
        ),
        base_mint=base_mint,
        evidence=evidence,
        http_status_code=0,
        api_key_length=report.api_key_length,
        base_url_length=report.base_url_length,
        live_flag_set=report.live_flag_set,
        timeout_seconds=report.timeout_seconds,
        handoff_ready=False,
    )


def _map_snapshot_failure_to_refusal(snapshot: object) -> str:
    """Project a Stage 29.2 snapshot status into the closed-set
    refusal-reason token used on the probe result. ``PRESENT``
    snapshots project to ``NONE``.
    """
    if isinstance(snapshot, Stage29_2BirdeyePriceSnapshot):
        status = snapshot.birdeye_price_status
    elif isinstance(snapshot, Stage29_2BirdeyeAthSnapshot):
        status = snapshot.birdeye_ath_status
    else:
        return BIRDEYE_REFUSAL_REASON_NONE
    if status == BIRDEYE_PRICE_STATUS_PRESENT:
        return BIRDEYE_REFUSAL_REASON_NONE
    if status == BIRDEYE_ATH_STATUS_PRESENT:
        return BIRDEYE_REFUSAL_REASON_NONE
    return BIRDEYE_REFUSAL_REASON_NONE


def _compute_drawdown_ratio(
    price_snapshot: Stage29_2BirdeyePriceSnapshot,
    ath_snapshot: Stage29_2BirdeyeAthSnapshot,
) -> Optional[str]:
    """Compute the drawdown ratio
    ``(price - ath) / ath`` as canonical decimal text. Returns
    ``None`` when either side is missing, units disagree, the
    ATH is zero / non-positive, or arithmetic fails. Telemetry-
    only: the Stage 27.4 reader computes drawdown amount
    (ath - price) separately for the existing closed-set
    drawdown-basis logic.
    """
    if (
        price_snapshot.birdeye_price_status
        != BIRDEYE_PRICE_STATUS_PRESENT
    ):
        return None
    if (
        ath_snapshot.birdeye_ath_status
        != BIRDEYE_ATH_STATUS_PRESENT
    ):
        return None
    if price_snapshot.price_value is None:
        return None
    if ath_snapshot.ath_value is None:
        return None
    if price_snapshot.price_unit != ath_snapshot.ath_unit:
        return None
    try:
        price_dec = Decimal(price_snapshot.price_value)
        ath_dec = Decimal(ath_snapshot.ath_value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if ath_dec <= 0:
        return None
    try:
        ratio = (price_dec - ath_dec) / ath_dec
    except (InvalidOperation, ArithmeticError):
        return None
    return format(ratio, "f")


def _combine_freshness(
    price_snapshot: Stage29_2BirdeyePriceSnapshot,
    ath_snapshot: Stage29_2BirdeyeAthSnapshot,
) -> str:
    """Combine the two per-snapshot freshness tokens into a
    single closed-set overall freshness verdict.

    Rules:

      * both FRESH -> FRESH
      * either STALE -> STALE
      * else UNKNOWN
    """
    p = price_snapshot.birdeye_freshness_status
    a = ath_snapshot.birdeye_freshness_status
    if (
        p == BIRDEYE_FRESHNESS_STATUS_FRESH
        and a == BIRDEYE_FRESHNESS_STATUS_FRESH
    ):
        return BIRDEYE_FRESHNESS_STATUS_FRESH
    if (
        p == BIRDEYE_FRESHNESS_STATUS_STALE
        or a == BIRDEYE_FRESHNESS_STATUS_STALE
    ):
        return BIRDEYE_FRESHNESS_STATUS_STALE
    return BIRDEYE_FRESHNESS_STATUS_UNKNOWN


def _no_invention_audit(
    price_snapshot: Stage29_2BirdeyePriceSnapshot,
    ath_snapshot: Stage29_2BirdeyeAthSnapshot,
) -> str:
    """Return ``PASSED`` iff:

      * every snapshot that is NOT ``PRESENT`` has its numeric
        value field as ``None``,
      * every snapshot that IS ``PRESENT`` has its numeric value
        field as a non-empty string.

    Returns ``FAILED`` otherwise. Stage 29.2's discipline says a
    snapshot must NEVER carry a fabricated number.
    """
    if (
        price_snapshot.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_PRESENT
    ):
        if not isinstance(price_snapshot.price_value, str):
            return NO_INVENTION_AUDIT_FAILED
        if price_snapshot.price_value == "":
            return NO_INVENTION_AUDIT_FAILED
    else:
        if price_snapshot.price_value is not None:
            return NO_INVENTION_AUDIT_FAILED

    if (
        ath_snapshot.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_PRESENT
    ):
        if not isinstance(ath_snapshot.ath_value, str):
            return NO_INVENTION_AUDIT_FAILED
        if ath_snapshot.ath_value == "":
            return NO_INVENTION_AUDIT_FAILED
    else:
        if ath_snapshot.ath_value is not None:
            return NO_INVENTION_AUDIT_FAILED

    return NO_INVENTION_AUDIT_PASSED


__all__ = (
    "TransportFactory",
    "PROBE_FRESHNESS_STALENESS_THRESHOLD_SECONDS",
    "run_stage29_2_birdeye_probe",
)
