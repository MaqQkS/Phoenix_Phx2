"""provider_backoff.py — per-provider bounded, jittered rate-limit backoff.

WHY THIS EXISTS (2026-07-31 restart-state root cause)
-----------------------------------------------------
The 2026-07-31 live retest died like this::

    Birdeye HTTP 429 x7  ->  budget cap max_429_total=5 crossed
                         ->  BUDGET_RATE_LIMIT_429 latched
                         ->  the WHOLE producer stopped
                         ->  the watchdog restarted it into a fresh run dir
                         ->  every tracked candidate's state was lost

Helius was healthy the entire time.  A market-data provider answering "slow
down" is a THROTTLE, not a fault: it says nothing about migration discovery,
the durable journal, or the candidates already being watched.  Terminating the
producer for it converts a recoverable, provider-local condition into a
process-wide restart — and a restart is the single most expensive event this
system can experience.

THE CONTRACT
------------
1. A 429 enters BOUNDED, JITTERED backoff scoped to ONE provider.  While the
   window is open that provider's requests are skipped (never dialled), so the
   throttle actually abates instead of being hammered.
2. Backoff climbs a FIXED ladder and stops climbing at its last rung.  There is
   no unbounded growth and no unbounded retry count.
3. Jitter is a bounded fraction of the rung, so N concurrent callers do not
   re-synchronize into a new burst.  ``jitter_fn`` is injectable, so offline
   tests are exactly deterministic.
4. A success CLEARS the backoff (recovery is observable, not assumed).
5. Sustained throttling is reported as ``PROVIDER_RATE_LIMIT_DEGRADED`` — a
   visible health/status degradation.  It never stops the producer and never
   deletes candidate state.
6. 401/403 are NOT throttles.  They are permanent credential rejections,
   counted separately here and left fatal at their own startup gate
   (:mod:`market_credential_check`).  This module never converts an auth
   rejection into "wait and retry".

Redaction discipline: closed-set tokens, counts and durations only.  No URL, no
host, no provider brand name, no key, no payload — nothing here may ever carry
a secret into an artifact.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

#: Closed-set provider scopes.  Deliberately ROLE labels, never brand names:
#: the runtime artifact scanner bans provider-name substrings.
PROVIDER_MARKET_PRIMARY = "MARKET_PRIMARY"
PROVIDER_DISCOVERY_POLLING = "DISCOVERY_POLLING"
PROVIDER_SCOPES = (PROVIDER_MARKET_PRIMARY, PROVIDER_DISCOVERY_POLLING)

#: Closed-set provider rate-limit statuses (artifact + health surface).
PROVIDER_RATE_LIMIT_OK = "PROVIDER_RATE_LIMIT_OK"
PROVIDER_RATE_LIMIT_BACKOFF = "PROVIDER_RATE_LIMIT_BACKOFF"
PROVIDER_RATE_LIMIT_DEGRADED = "PROVIDER_RATE_LIMIT_DEGRADED"
PROVIDER_RATE_LIMIT_STATUSES = (
    PROVIDER_RATE_LIMIT_OK,
    PROVIDER_RATE_LIMIT_BACKOFF,
    PROVIDER_RATE_LIMIT_DEGRADED,
)

#: Closed-set skip reason handed back to callers gated by an open window.
PROVIDER_SKIPPED_RATE_LIMIT_BACKOFF = "PROVIDER_RATE_LIMIT_BACKOFF"

#: Fixed backoff ladder in seconds.  Bounded by construction: the last rung is
#: the ceiling, so a provider throttling forever waits at most
#: ``60s * (1 + jitter_fraction)`` between probes and never longer.
DEFAULT_BACKOFF_LADDER_SECONDS: Tuple[float, ...] = (
    1.0, 2.0, 5.0, 15.0, 30.0, 60.0)

#: Jitter as a fraction of the selected rung: delay in
#: ``[rung, rung * (1 + fraction)]``.  Never negative, so the backoff can never
#: be shortened below its rung by jitter.
DEFAULT_JITTER_FRACTION = 0.25

#: Consecutive throttles (without an intervening success) that make the
#: provider DEGRADED in the operator-facing health surface.
DEFAULT_DEGRADED_AFTER_CONSECUTIVE = 5


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in (float("inf"), float("-inf")) \
            or parsed <= 0:
        return default
    return parsed


class ProviderRateLimitBackoff:
    """Bounded, jittered, provider-scoped throttle state.

    One instance per provider scope.  Thread-safe: the market transport calls
    it from every scheduler worker thread.
    """

    def __init__(
        self,
        provider: str = PROVIDER_MARKET_PRIMARY,
        *,
        ladder_seconds: Sequence[float] = DEFAULT_BACKOFF_LADDER_SECONDS,
        jitter_fraction: float = DEFAULT_JITTER_FRACTION,
        degraded_after_consecutive: int = DEFAULT_DEGRADED_AFTER_CONSECUTIVE,
        monotonic_fn: Callable[[], float] = time.monotonic,
        jitter_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if provider not in PROVIDER_SCOPES:
            raise ValueError("provider_scope_unsupported")
        ladder = tuple(
            _positive_float(rung, 1.0) for rung in (ladder_seconds or ()))
        if not ladder:
            raise ValueError("backoff_ladder_empty")
        self.provider = str(provider)
        self._ladder = ladder
        try:
            fraction = float(jitter_fraction)
        except (TypeError, ValueError):
            fraction = DEFAULT_JITTER_FRACTION
        self._jitter_fraction = fraction if 0.0 <= fraction <= 1.0 \
            else DEFAULT_JITTER_FRACTION
        self._degraded_after = max(1, int(degraded_after_consecutive))
        self._mono = monotonic_fn
        #: Returns a value in [0, 1); tests inject a constant for determinism.
        self._jitter = jitter_fn or random.random
        self._lock = threading.RLock()
        self._until: Optional[float] = None
        self._last_delay_seconds: float = 0.0
        self.consecutive_throttles = 0
        self.throttles_total = 0
        self.auth_failures_total = 0
        self.recoveries_total = 0
        self.requests_skipped_total = 0
        self.max_consecutive_throttles = 0

    # ------------------------------------------------------------------ state

    @property
    def backoff_ceiling_seconds(self) -> float:
        """Hard upper bound on any single wait this object can produce."""
        return self._ladder[-1] * (1.0 + self._jitter_fraction)

    @property
    def degraded(self) -> bool:
        """Sustained throttling: visible in health/status, never fatal."""
        with self._lock:
            return self.consecutive_throttles >= self._degraded_after

    def remaining_seconds(self) -> float:
        """Seconds left in the open window (0.0 when not backed off)."""
        with self._lock:
            return self._remaining_locked()

    def _remaining_locked(self) -> float:
        if self._until is None:
            return 0.0
        remaining = float(self._until) - float(self._mono())
        if remaining <= 0.0:
            self._until = None
            return 0.0
        return remaining

    def should_skip(self) -> bool:
        """True while this provider's requests must NOT be dialled."""
        with self._lock:
            if self._remaining_locked() <= 0.0:
                return False
            self.requests_skipped_total += 1
            return True

    @property
    def status(self) -> str:
        with self._lock:
            if self.consecutive_throttles >= self._degraded_after:
                return PROVIDER_RATE_LIMIT_DEGRADED
            if self._remaining_locked() > 0.0:
                return PROVIDER_RATE_LIMIT_BACKOFF
            return PROVIDER_RATE_LIMIT_OK

    # ------------------------------------------------------------ transitions

    def record_throttle(self) -> float:
        """Record one HTTP 429 and open/extend the bounded backoff window.

        Returns the jittered delay in seconds.  The rung is selected by the
        CONSECUTIVE throttle count and saturates at the last rung, so the wait
        is bounded no matter how long the provider throttles.
        """

        with self._lock:
            self.throttles_total += 1
            self.consecutive_throttles += 1
            self.max_consecutive_throttles = max(
                self.max_consecutive_throttles, self.consecutive_throttles)
            rung = self._ladder[
                min(self.consecutive_throttles - 1, len(self._ladder) - 1)]
            try:
                jitter = float(self._jitter())
            except (TypeError, ValueError):
                jitter = 0.0
            if jitter != jitter or jitter < 0.0 or jitter >= 1.0:
                jitter = 0.0
            delay = rung * (1.0 + self._jitter_fraction * jitter)
            self._last_delay_seconds = delay
            self._until = float(self._mono()) + delay
            return delay

    def record_success(self) -> bool:
        """Record one successful provider response; clears any backoff.

        Returns True when this call actually ended an open backoff/throttle
        streak (used by tests and telemetry to prove recovery happened).
        """

        with self._lock:
            recovered = bool(
                self.consecutive_throttles or self._until is not None)
            self.consecutive_throttles = 0
            self._until = None
            self._last_delay_seconds = 0.0
            if recovered:
                self.recoveries_total += 1
            return recovered

    def record_auth_failure(self) -> None:
        """Record a 401/403.  Explicitly NOT a throttle: no backoff, no retry.

        Permanent credential rejection is handled fatally at startup by
        :mod:`market_credential_check`; counting it here keeps the two classes
        distinguishable in one artifact instead of blurring into "429-ish".
        """

        with self._lock:
            self.auth_failures_total += 1

    # ------------------------------------------------------------- reporting

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe telemetry block (counts, seconds, closed-set tokens)."""

        with self._lock:
            remaining = self._remaining_locked()
            return {
                "kind": "PHX2_PROVIDER_RATE_LIMIT_BACKOFF",
                "provider": self.provider,
                "status": self.status,
                "degraded": self.consecutive_throttles >= self._degraded_after,
                "backed_off": remaining > 0.0,
                "backoff_remaining_seconds": round(remaining, 3),
                "last_backoff_seconds": round(self._last_delay_seconds, 3),
                "backoff_ceiling_seconds": round(
                    self.backoff_ceiling_seconds, 3),
                "consecutive_throttles": self.consecutive_throttles,
                "max_consecutive_throttles": self.max_consecutive_throttles,
                "throttles_total": self.throttles_total,
                "recoveries_total": self.recoveries_total,
                "requests_skipped_total": self.requests_skipped_total,
                "auth_failures_total": self.auth_failures_total,
                "degraded_after_consecutive": self._degraded_after,
                "ladder_seconds": list(self._ladder),
                "jitter_fraction": self._jitter_fraction,
            }


__all__ = (
    "PROVIDER_MARKET_PRIMARY",
    "PROVIDER_DISCOVERY_POLLING",
    "PROVIDER_SCOPES",
    "PROVIDER_RATE_LIMIT_OK",
    "PROVIDER_RATE_LIMIT_BACKOFF",
    "PROVIDER_RATE_LIMIT_DEGRADED",
    "PROVIDER_RATE_LIMIT_STATUSES",
    "PROVIDER_SKIPPED_RATE_LIMIT_BACKOFF",
    "DEFAULT_BACKOFF_LADDER_SECONDS",
    "DEFAULT_JITTER_FRACTION",
    "DEFAULT_DEGRADED_AFTER_CONSECUTIVE",
    "ProviderRateLimitBackoff",
)
