"""Persistent bounded-backoff reconnect policy for the one live WSS owner.

WHY THIS EXISTS
---------------
The Helius source used a five-attempt ceiling: after five consecutive transport
failures it set ``STREAM_FAILED`` / ``RECONNECTS_EXHAUSTED`` and stopped.  An
ordinary provider outage longer than five attempts therefore killed continuous
discovery permanently, with no operator signal other than a stopped stream.
PHX1 reconnects indefinitely; PHX2 now does too, WITHOUT giving up any of its
ownership or integrity rules.

THE CONTRACT
------------
1. RECONNECT FOREVER for ordinary temporary provider failures.  There is no
   attempt ceiling; the loop ends only on operator shutdown, an authentication
   rejection, or a proven non-recoverable integrity/configuration failure.

2. BOUNDED EXPONENTIAL BACKOFF.  Delays follow the fixed ladder
   ``1, 2, 5, 10, 30`` seconds and then stay capped near ``60`` seconds
   (:data:`RECONNECT_MAX_DELAY_SECONDS`).  The ladder is monotone and every
   value is bounded, so a long outage settles at one attempt per minute instead
   of hammering the provider.

3. BOUNDED JITTER.  Each delay carries ``+[0, jitter_fraction) * base`` seconds
   of jitter so many producers (or many restarts of one producer) never
   synchronize into a reconnect storm.  Jitter only ever ADDS, is bounded by
   ``base * jitter_fraction``, and the total is still bounded by
   ``max_delay * (1 + jitter_fraction)``.

4. BACKOFF RESET AFTER A HEALTHY CONNECTION.  A connection that stayed up for
   at least :data:`HEALTHY_CONNECTION_SECONDS` proves the outage is over, so the
   next failure starts again at the bottom of the ladder.  A connection that
   flaps (established, dies immediately) does NOT reset, so a flapping provider
   still backs off.

5. FAILURE CLASSES ARE CLOSED-SET AND SEPARATE.  Authentication rejection is
   never retried and is reported distinctly from a transient outage; only a
   proven non-recoverable integrity/configuration failure is allowed to be
   escalated by an outer layer into a circuit-open condition.  An ordinary
   temporary provider outage is NEVER an integrity failure.

6. OPERATOR SHUTDOWN WINS IMMEDIATELY.  ``decide(..., shutdown_requested=True)``
   returns the shutdown action regardless of failure class, and the delay is
   zero, so a shutdown during a 60-second backoff exits promptly rather than
   waiting out the sleep.  (The caller performs the wait on an interruptible
   event; this module only decides.)

Nothing here performs I/O, reads the clock by itself, or carries provider text:
every value is a number or a closed-set token, so a policy snapshot is safe in
any artifact.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

#: Fixed monotone backoff ladder in seconds.  The last entry is the cap.
RECONNECT_LADDER_SECONDS: Tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

#: Hard ceiling for the BASE delay (before jitter).
RECONNECT_MAX_DELAY_SECONDS = 60.0

#: Additive jitter as a fraction of the base delay: ``[0, fraction) * base``.
RECONNECT_JITTER_FRACTION = 0.2

#: A connection that stayed up at least this long counts as sustained-healthy
#: and resets the backoff ladder.
HEALTHY_CONNECTION_SECONDS = 60.0

# -- failure classes (closed set; never provider exception text) -------------
FAILURE_TRANSIENT = "TRANSIENT_PROVIDER_FAILURE"
FAILURE_AUTHENTICATION = "AUTHENTICATION_REJECTED"
FAILURE_INTEGRITY = "NON_RECOVERABLE_INTEGRITY_FAILURE"
FAILURE_OPERATOR_SHUTDOWN = "OPERATOR_SHUTDOWN"

RECONNECT_FAILURE_CLASSES = (
    FAILURE_TRANSIENT,
    FAILURE_AUTHENTICATION,
    FAILURE_INTEGRITY,
    FAILURE_OPERATOR_SHUTDOWN,
)

# -- decisions (closed set) --------------------------------------------------
ACTION_RECONNECT = "RECONNECT"
ACTION_STOP_AUTHENTICATION = "STOP_AUTHENTICATION"
ACTION_STOP_INTEGRITY = "STOP_INTEGRITY"
ACTION_STOP_OPERATOR_SHUTDOWN = "STOP_OPERATOR_SHUTDOWN"

RECONNECT_ACTIONS = (
    ACTION_RECONNECT,
    ACTION_STOP_AUTHENTICATION,
    ACTION_STOP_INTEGRITY,
    ACTION_STOP_OPERATOR_SHUTDOWN,
)

#: Only these two actions may ever be escalated into a circuit-open condition.
#: An ordinary outage must not reach the breaker.
CIRCUIT_ELIGIBLE_ACTIONS = (
    ACTION_STOP_AUTHENTICATION,
    ACTION_STOP_INTEGRITY,
)


class ReconnectPolicyConfigurationError(ValueError):
    """The reconnect ladder or jitter bound is unsafe."""


def classify_reconnect_failure(
    error_token: object,
    *,
    integrity_tokens: Sequence[str] = (),
) -> str:
    """Map a closed-set source error token to a reconnect failure class.

    ``error_token`` is one of the source's own ``ERROR_*`` tokens (never
    provider exception text).  Anything not explicitly known is TRANSIENT: the
    fail-safe direction here is "keep reconnecting", because refusing to
    reconnect is what silently ends discovery.  Escalation to an integrity stop
    requires the caller to name the token explicitly.
    """

    token = str(error_token or "")
    if token in tuple(str(item) for item in integrity_tokens):
        return FAILURE_INTEGRITY
    if token in ("AUTH_FAILURE", "AUTHENTICATION_REJECTED", "PROVIDER_AUTH_FAILURE"):
        return FAILURE_AUTHENTICATION
    return FAILURE_TRANSIENT


@dataclass(frozen=True)
class ReconnectDecision:
    """One reconnect verdict: what to do, and how long to wait first."""

    action: str
    failure_class: str
    attempt: int
    base_delay_seconds: float
    jitter_seconds: float
    delay_seconds: float

    @property
    def should_reconnect(self) -> bool:
        return self.action == ACTION_RECONNECT

    @property
    def circuit_eligible(self) -> bool:
        """True only for a stop an outer layer may treat as circuit-open."""

        return self.action in CIRCUIT_ELIGIBLE_ACTIONS

    def to_record(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "failure_class": self.failure_class,
            "attempt": int(self.attempt),
            "base_delay_seconds": round(float(self.base_delay_seconds), 3),
            "jitter_seconds": round(float(self.jitter_seconds), 3),
            "delay_seconds": round(float(self.delay_seconds), 3),
        }


class PersistentReconnectPolicy:
    """Attempt-unbounded, delay-bounded reconnect scheduling with jitter.

    The policy owns no clock: the caller supplies connection start/end
    timestamps.  That keeps every test deterministic and keeps the policy
    reusable from both the async source loop and an operator projection.
    """

    def __init__(
        self,
        *,
        ladder: Sequence[float] = RECONNECT_LADDER_SECONDS,
        max_delay_seconds: float = RECONNECT_MAX_DELAY_SECONDS,
        jitter_fraction: float = RECONNECT_JITTER_FRACTION,
        healthy_connection_seconds: float = HEALTHY_CONNECTION_SECONDS,
        rand_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        values = tuple(float(item) for item in ladder or ())
        if not values:
            raise ReconnectPolicyConfigurationError(
                "reconnect ladder must not be empty")
        if any(value < 0.0 for value in values):
            raise ReconnectPolicyConfigurationError(
                "reconnect ladder must be non-negative")
        if any(right < left for left, right in zip(values, values[1:])):
            raise ReconnectPolicyConfigurationError(
                "reconnect ladder must be monotone non-decreasing")
        cap = float(max_delay_seconds)
        if not 0.0 <= cap <= 300.0:
            raise ReconnectPolicyConfigurationError(
                "reconnect maximum delay is out of range")
        fraction = float(jitter_fraction)
        if not 0.0 <= fraction <= 1.0:
            raise ReconnectPolicyConfigurationError(
                "reconnect jitter fraction is out of range")
        healthy = float(healthy_connection_seconds)
        if healthy < 0.0:
            raise ReconnectPolicyConfigurationError(
                "healthy-connection threshold is out of range")
        self._ladder = values
        self._max_delay = cap
        self._jitter_fraction = fraction
        self._healthy_after = healthy
        self._rand = rand_fn or random.random
        self.consecutive_failures = 0
        self.reconnects_total = 0
        self.backoff_resets_total = 0
        self.longest_backoff_seconds = 0.0
        self.sustained_connections_total = 0
        self.last_connection_seconds: Optional[float] = None
        self.last_failure_class: Optional[str] = None
        self.last_action: Optional[str] = None
        self._connection_started_at: Optional[float] = None

    # -- ladder ------------------------------------------------------------

    @property
    def ladder(self) -> Tuple[float, ...]:
        return self._ladder

    @property
    def max_delay_seconds(self) -> float:
        return self._max_delay

    @property
    def jitter_fraction(self) -> float:
        return self._jitter_fraction

    def base_delay_for(self, attempt: object) -> float:
        """Ladder value for a zero-based attempt index, capped."""

        try:
            index = int(attempt)
        except (TypeError, ValueError):
            index = 0
        if index < 0:
            index = 0
        if index >= len(self._ladder):
            index = len(self._ladder) - 1
        return min(self._ladder[index], self._max_delay)

    # -- connection lifecycle ----------------------------------------------

    def note_connection_established(self, *, at_epoch: object = None) -> None:
        """Record that a socket opened; the healthy timer starts here."""

        try:
            self._connection_started_at = (
                None if at_epoch is None else float(at_epoch))
        except (TypeError, ValueError):
            self._connection_started_at = None

    def note_connection_closed(self, *, at_epoch: object = None) -> bool:
        """Close the current connection; True when the backoff was reset.

        A connection that lasted at least ``healthy_connection_seconds`` proves
        the provider recovered, so the ladder restarts from the bottom.  A
        flapping connection leaves the ladder where it is.
        """

        started = self._connection_started_at
        self._connection_started_at = None
        if started is None or at_epoch is None:
            self.last_connection_seconds = None
            return False
        try:
            elapsed = max(0.0, float(at_epoch) - float(started))
        except (TypeError, ValueError):
            self.last_connection_seconds = None
            return False
        self.last_connection_seconds = elapsed
        if elapsed >= self._healthy_after:
            self.sustained_connections_total += 1
            return self.reset_backoff()
        return False

    def reset_backoff(self) -> bool:
        """Restart the ladder; True when something was actually reset."""

        if self.consecutive_failures == 0:
            return False
        self.consecutive_failures = 0
        self.backoff_resets_total += 1
        return True

    # -- decisions ---------------------------------------------------------

    def decide(
        self,
        *,
        failure_class: str = FAILURE_TRANSIENT,
        shutdown_requested: bool = False,
    ) -> ReconnectDecision:
        """Decide what happens after one connection attempt failed."""

        if shutdown_requested:
            self.last_failure_class = FAILURE_OPERATOR_SHUTDOWN
            self.last_action = ACTION_STOP_OPERATOR_SHUTDOWN
            return ReconnectDecision(
                action=ACTION_STOP_OPERATOR_SHUTDOWN,
                failure_class=FAILURE_OPERATOR_SHUTDOWN,
                attempt=self.consecutive_failures,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                delay_seconds=0.0,
            )
        safe_class = (
            failure_class if failure_class in RECONNECT_FAILURE_CLASSES
            else FAILURE_TRANSIENT)
        self.last_failure_class = safe_class
        if safe_class == FAILURE_AUTHENTICATION:
            self.last_action = ACTION_STOP_AUTHENTICATION
            return ReconnectDecision(
                action=ACTION_STOP_AUTHENTICATION,
                failure_class=safe_class,
                attempt=self.consecutive_failures,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                delay_seconds=0.0,
            )
        if safe_class == FAILURE_INTEGRITY:
            self.last_action = ACTION_STOP_INTEGRITY
            return ReconnectDecision(
                action=ACTION_STOP_INTEGRITY,
                failure_class=safe_class,
                attempt=self.consecutive_failures,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                delay_seconds=0.0,
            )
        if safe_class == FAILURE_OPERATOR_SHUTDOWN:
            self.last_action = ACTION_STOP_OPERATOR_SHUTDOWN
            return ReconnectDecision(
                action=ACTION_STOP_OPERATOR_SHUTDOWN,
                failure_class=safe_class,
                attempt=self.consecutive_failures,
                base_delay_seconds=0.0,
                jitter_seconds=0.0,
                delay_seconds=0.0,
            )
        attempt = self.consecutive_failures
        base = self.base_delay_for(attempt)
        jitter = 0.0
        if self._jitter_fraction > 0.0 and base > 0.0:
            try:
                draw = float(self._rand())
            except Exception:
                draw = 0.0
            draw = min(max(draw, 0.0), 1.0)
            jitter = base * self._jitter_fraction * draw
        delay = base + jitter
        self.consecutive_failures = attempt + 1
        self.reconnects_total += 1
        self.last_action = ACTION_RECONNECT
        if delay > self.longest_backoff_seconds:
            self.longest_backoff_seconds = delay
        return ReconnectDecision(
            action=ACTION_RECONNECT,
            failure_class=safe_class,
            attempt=attempt,
            base_delay_seconds=base,
            jitter_seconds=jitter,
            delay_seconds=delay,
        )

    # -- observability -----------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe policy state for status and artifacts."""

        return {
            "policy": "PERSISTENT_BOUNDED_BACKOFF",
            "persistent": True,
            "attempt_ceiling": None,
            "ladder_seconds": list(self._ladder),
            "max_delay_seconds": self._max_delay,
            "jitter_fraction": self._jitter_fraction,
            "healthy_connection_seconds": self._healthy_after,
            "consecutive_failures": int(self.consecutive_failures),
            "reconnects_total": int(self.reconnects_total),
            "backoff_resets_total": int(self.backoff_resets_total),
            "sustained_connections_total": int(
                self.sustained_connections_total),
            "longest_backoff_seconds": round(
                float(self.longest_backoff_seconds), 3),
            "last_connection_seconds": (
                None if self.last_connection_seconds is None
                else round(float(self.last_connection_seconds), 3)),
            "next_base_delay_seconds": self.base_delay_for(
                self.consecutive_failures),
            "last_failure_class": self.last_failure_class,
            "last_action": self.last_action,
        }


__all__ = (
    "ACTION_RECONNECT",
    "ACTION_STOP_AUTHENTICATION",
    "ACTION_STOP_INTEGRITY",
    "ACTION_STOP_OPERATOR_SHUTDOWN",
    "CIRCUIT_ELIGIBLE_ACTIONS",
    "FAILURE_AUTHENTICATION",
    "FAILURE_INTEGRITY",
    "FAILURE_OPERATOR_SHUTDOWN",
    "FAILURE_TRANSIENT",
    "HEALTHY_CONNECTION_SECONDS",
    "PersistentReconnectPolicy",
    "RECONNECT_ACTIONS",
    "RECONNECT_FAILURE_CLASSES",
    "RECONNECT_JITTER_FRACTION",
    "RECONNECT_LADDER_SECONDS",
    "RECONNECT_MAX_DELAY_SECONDS",
    "ReconnectDecision",
    "ReconnectPolicyConfigurationError",
    "classify_reconnect_failure",
)
