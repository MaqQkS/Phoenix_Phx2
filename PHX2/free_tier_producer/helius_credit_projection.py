"""Reproducible Helius credit projection for continuous discovery.

WHY THIS EXISTS
---------------
The abandoned broad-enumeration design projected ~78.9M credits/month — 788.7%
of the 10M Developer allowance — which is why it was rejected.  The replacement
architecture (one tight live WSS subscription + exact proven-gap HTTP recovery)
has to be shown to fit, not asserted to fit, so the model lives in code with its
inputs pinned to MEASURED production telemetry rather than to a guess.

THE MEASUREMENT
---------------
Run ``paid_primary_live_24x7_20260730T222054Z``, ticks 1..18, is the source of
the live-stream rate.  Between the tick-1 and tick-18 heartbeats the byte budget
recorded 618,959 -> 9,775,274 uncompressed WSS bytes across 582 seconds of
armed streaming under the exact production ``accountRequired`` Pump + PumpSwap
filter.  That is 9,156,315 bytes / 582 s = 15,732.5 B/s, billed at
``STREAM_CREDITS_PER_100KB`` (2 credits per 100 kB).

WHAT IS AND IS NOT MODELLED
---------------------------
Modelled: the tight live subscription, ordinary reconnect handshakes, and
bounded exact-gap HTTP recovery.  Curated DEX market requests are NOT Helius
credits and are reported separately (``curated_dex_requests_per_month``); they
are a different provider's free public surface and never consume this budget.

Not modelled, because the architecture forbids it: broad historical
enumeration, six-hour cold-start reconstruction, and speculative replay.  There
is no parameter in this module that could express one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from PHX2.free_tier_producer.helius_gap_recovery import (
    DEFAULT_MAX_CREDITS as GAP_RECOVERY_CREDIT_CEILING,
)
from PHX2.free_tier_producer.source_continuity import (
    DEFAULT_MAX_RECOVERY_ATTEMPTS,
)
from PHX2.shadow_probes.helius_developer import (
    DEVELOPER_MONTHLY_CREDITS,
    STREAM_BILLING_BYTES,
    STREAM_CREDITS_PER_100KB,
)

SECONDS_PER_MONTH = 30 * 24 * 60 * 60  # 2_592_000

# -- measured live-stream rate (see module docstring) ------------------------
MEASURED_RUN_ID = "paid_primary_live_24x7_20260730T222054Z"
MEASURED_WSS_BYTES = 9_775_274 - 618_959       # 9_156_315
MEASURED_WSS_SECONDS = 582.0
MEASURED_WSS_BYTES_PER_SECOND = MEASURED_WSS_BYTES / MEASURED_WSS_SECONDS

#: Headroom applied to the measured rate for the conservative case.  Pump
#: activity is bursty; doubling the measured rate covers a sustained market far
#: busier than the measurement window without inventing a number.
CONSERVATIVE_STREAM_MULTIPLIER = 2.0

#: Bytes on the wire for one reconnect: subscribe request + subscription
#: response + close frames.  Deliberately generous.
RECONNECT_HANDSHAKE_BYTES = 2_048

#: Worst sustained reconnect cadence the persistent policy can produce: the
#: backoff ladder caps near 60 s, so a total outage yields one attempt/minute.
WORST_CASE_RECONNECTS_PER_MONTH = SECONDS_PER_MONTH // 60

#: Ordinary case: a handful of provider-side disconnects per day.
ORDINARY_RECONNECTS_PER_DAY = 24

#: Conservative gap assumption: one proven slot gap every hour, each burning
#: the FULL bounded recovery ceiling on every bounded retry.  The measured run
#: detected zero gaps.
CONSERVATIVE_GAPS_PER_DAY = 24

#: Curated DEX polls: startup + one per 180 s, times ~3 requests per sweep.
CURATED_DEX_SWEEPS_PER_DAY = (24 * 60 * 60) // 180
CURATED_DEX_REQUESTS_PER_SWEEP = 3


def stream_credits_for_bytes(byte_count: float) -> float:
    """Helius stream billing: ``STREAM_CREDITS_PER_100KB`` per 100 kB."""

    return max(0.0, float(byte_count)) * STREAM_CREDITS_PER_100KB / float(
        STREAM_BILLING_BYTES)


def live_stream_credits_per_month(
    *,
    bytes_per_second: float = MEASURED_WSS_BYTES_PER_SECOND,
    multiplier: float = 1.0,
) -> float:
    """Monthly credits for one continuously-armed tight subscription."""

    rate = max(0.0, float(bytes_per_second)) * max(0.0, float(multiplier))
    return stream_credits_for_bytes(rate * SECONDS_PER_MONTH)


def reconnect_credits_per_month(*, reconnects_per_month: int) -> float:
    """Monthly credits burned by reconnect handshakes alone."""

    count = max(0, int(reconnects_per_month))
    return stream_credits_for_bytes(count * RECONNECT_HANDSHAKE_BYTES)


def gap_recovery_credits_per_month(
    *,
    gaps_per_day: int,
    attempts_per_gap: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    credits_per_attempt: int = GAP_RECOVERY_CREDIT_CEILING,
) -> float:
    """Monthly credits for exact proven-gap HTTP recovery at its ceiling.

    Every factor is a HARD bound the recoverer enforces: the per-attempt credit
    ceiling is ``HeliusRecoveryConfig.max_credits`` and the attempt budget is
    the continuity tracker's ``max_recovery_attempts``.  There is no unbounded
    term, which is exactly what separates this from broad enumeration.
    """

    per_gap = max(0, int(attempts_per_gap)) * max(0, int(credits_per_attempt))
    return float(max(0, int(gaps_per_day)) * per_gap * 30)


@dataclass(frozen=True)
class HeliusCreditProjection:
    """One named credit scenario and its share of the Developer allowance."""

    scenario: str
    live_stream_credits: float
    reconnect_credits: float
    gap_recovery_credits: float

    @property
    def total_credits(self) -> float:
        return (float(self.live_stream_credits)
                + float(self.reconnect_credits)
                + float(self.gap_recovery_credits))

    @property
    def allowance_fraction(self) -> float:
        return self.total_credits / float(DEVELOPER_MONTHLY_CREDITS)

    @property
    def fits_developer_allowance(self) -> bool:
        return self.total_credits <= float(DEVELOPER_MONTHLY_CREDITS)

    def to_record(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "live_stream_credits": round(float(self.live_stream_credits), 1),
            "reconnect_credits": round(float(self.reconnect_credits), 1),
            "gap_recovery_credits": round(float(self.gap_recovery_credits), 1),
            "total_credits": round(self.total_credits, 1),
            "developer_monthly_credits": DEVELOPER_MONTHLY_CREDITS,
            "allowance_percent": round(self.allowance_fraction * 100.0, 2),
            "headroom_credits": round(
                float(DEVELOPER_MONTHLY_CREDITS) - self.total_credits, 1),
            "fits_developer_allowance": self.fits_developer_allowance,
        }


def no_gap_projection() -> HeliusCreditProjection:
    """Normal operation: measured stream rate, no gaps, no recovery."""

    return HeliusCreditProjection(
        scenario="NO_GAP_NORMAL_OPERATION",
        live_stream_credits=live_stream_credits_per_month(),
        reconnect_credits=0.0,
        gap_recovery_credits=0.0,
    )


def ordinary_projection() -> HeliusCreditProjection:
    """Expected operation: measured rate, ordinary reconnects, a few gaps."""

    return HeliusCreditProjection(
        scenario="ORDINARY_OPERATION",
        live_stream_credits=live_stream_credits_per_month(),
        reconnect_credits=reconnect_credits_per_month(
            reconnects_per_month=ORDINARY_RECONNECTS_PER_DAY * 30),
        gap_recovery_credits=gap_recovery_credits_per_month(gaps_per_day=2),
    )


def conservative_projection() -> HeliusCreditProjection:
    """Conservative case: doubled stream rate, worst reconnect cadence, hourly
    gaps each burning the FULL bounded recovery ceiling on every retry."""

    return HeliusCreditProjection(
        scenario="CONSERVATIVE",
        live_stream_credits=live_stream_credits_per_month(
            multiplier=CONSERVATIVE_STREAM_MULTIPLIER),
        reconnect_credits=reconnect_credits_per_month(
            reconnects_per_month=WORST_CASE_RECONNECTS_PER_MONTH),
        gap_recovery_credits=gap_recovery_credits_per_month(
            gaps_per_day=CONSERVATIVE_GAPS_PER_DAY),
    )


def curated_dex_requests_per_month() -> int:
    """Curated DEX market requests — reported SEPARATELY from Helius credits.

    These are a different provider's public surface.  They consume zero Helius
    credits and are counted only so an operator sees the whole request budget.
    """

    return int(CURATED_DEX_SWEEPS_PER_DAY * CURATED_DEX_REQUESTS_PER_SWEEP * 30)


def projection_report() -> Dict[str, Any]:
    """All three scenarios plus the separate curated-DEX request count."""

    scenarios = [no_gap_projection(), ordinary_projection(),
                 conservative_projection()]
    return {
        "schema_version": "phx2_helius_credit_projection_v1",
        "measured_run_id": MEASURED_RUN_ID,
        "measured_wss_bytes": MEASURED_WSS_BYTES,
        "measured_wss_seconds": MEASURED_WSS_SECONDS,
        "measured_wss_bytes_per_second": round(
            MEASURED_WSS_BYTES_PER_SECOND, 1),
        "broad_historical_enumeration_modelled": False,
        "scenarios": [item.to_record() for item in scenarios],
        "curated_dex_requests_per_month": curated_dex_requests_per_month(),
        "curated_dex_consumes_helius_credits": False,
    }


__all__ = (
    "CONSERVATIVE_GAPS_PER_DAY",
    "CONSERVATIVE_STREAM_MULTIPLIER",
    "CURATED_DEX_REQUESTS_PER_SWEEP",
    "CURATED_DEX_SWEEPS_PER_DAY",
    "DEVELOPER_MONTHLY_CREDITS",
    "HeliusCreditProjection",
    "MEASURED_RUN_ID",
    "MEASURED_WSS_BYTES",
    "MEASURED_WSS_BYTES_PER_SECOND",
    "MEASURED_WSS_SECONDS",
    "ORDINARY_RECONNECTS_PER_DAY",
    "RECONNECT_HANDSHAKE_BYTES",
    "SECONDS_PER_MONTH",
    "WORST_CASE_RECONNECTS_PER_MONTH",
    "conservative_projection",
    "curated_dex_requests_per_month",
    "gap_recovery_credits_per_month",
    "live_stream_credits_per_month",
    "no_gap_projection",
    "ordinary_projection",
    "projection_report",
    "reconnect_credits_per_month",
    "stream_credits_for_bytes",
)
