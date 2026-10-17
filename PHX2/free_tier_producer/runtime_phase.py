"""Explicit runtime phases for a soak that must first finish a recovery.

An inherited recovery episode can take longer than the soak it precedes. Timing
the soak from process start would therefore either (a) count recovery time as
soak time, which it is not, or (b) force the operator to guess a total runtime
that happens to leave two clean hours at the end. Neither is evidence.

This module separates the two clocks:

``PRE_SOAK_RECOVERY``
    The producer is up, the single stream owner is up, delivery is configured
    but structurally blocked, and the inherited recovery episode is being
    resumed. The acceptance timer is NOT running.

``ACTIVE_STAGE9_SOAK``
    Recovery is complete and proven, the source-health latch is clear, and the
    ordinary production path is live. The acceptance timer runs here and only
    here.

The transition is one-way and is gated on facts the caller proves, not on
elapsed time. Nothing here sends, reads an environment file, or touches a
ledger; it owns two clocks and a closed-set phase name.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

PHASE_PRE_SOAK_RECOVERY = "PRE_SOAK_RECOVERY"
PHASE_ACTIVE_SOAK = "ACTIVE_STAGE9_SOAK"
RUNTIME_PHASES = (PHASE_PRE_SOAK_RECOVERY, PHASE_ACTIVE_SOAK)

#: Closed-set reasons the activation gate refused. Every one of them names a
#: fact that was not yet true, so the phase stays PRE_SOAK and the acceptance
#: timer stays stopped.
ACTIVATION_OK = "ACTIVATION_OK"
ACTIVATION_BLOCKED_RECOVERY_OPEN = "ACTIVATION_BLOCKED_RECOVERY_OPEN"
ACTIVATION_BLOCKED_OVERLAP_UNPROVEN = "ACTIVATION_BLOCKED_OVERLAP_UNPROVEN"
ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING = "ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING"
ACTIVATION_BLOCKED_SOURCE_UNHEALTHY = "ACTIVATION_BLOCKED_SOURCE_UNHEALTHY"
ACTIVATION_BLOCKED_RECOVERY_TERMINAL = "ACTIVATION_BLOCKED_RECOVERY_TERMINAL"
ACTIVATION_REASONS = (
    ACTIVATION_OK,
    ACTIVATION_BLOCKED_RECOVERY_OPEN,
    ACTIVATION_BLOCKED_OVERLAP_UNPROVEN,
    ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING,
    ACTIVATION_BLOCKED_SOURCE_UNHEALTHY,
    ACTIVATION_BLOCKED_RECOVERY_TERMINAL,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ActivationInputs:
    """Facts the caller has PROVEN, not opinions about them.

    ``recovery_episode_open`` and ``recovery_terminal`` come from the durable
    recovery store; ``overlap_proven`` and ``produced_blocks_remaining`` come
    from the same authenticated record; ``source_healthy`` comes from the
    cursor's source-health latch. A caller that cannot prove a field must pass
    the conservative value, which is the one that keeps the phase in pre-soak.
    """

    recovery_required: bool
    recovery_episode_open: bool
    recovery_terminal: bool
    overlap_proven: bool
    produced_blocks_remaining: int
    source_healthy: bool


def evaluate_activation(inputs: ActivationInputs) -> str:
    """One closed-set verdict on whether the acceptance timer may start."""

    if not inputs.recovery_required:
        # Nothing was inherited: the only remaining gate is the source latch.
        return (ACTIVATION_OK if inputs.source_healthy
                else ACTIVATION_BLOCKED_SOURCE_UNHEALTHY)
    if inputs.recovery_terminal:
        return ACTIVATION_BLOCKED_RECOVERY_TERMINAL
    if inputs.recovery_episode_open:
        return ACTIVATION_BLOCKED_RECOVERY_OPEN
    if not inputs.overlap_proven:
        return ACTIVATION_BLOCKED_OVERLAP_UNPROVEN
    if int(inputs.produced_blocks_remaining) > 0:
        return ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING
    if not inputs.source_healthy:
        return ACTIVATION_BLOCKED_SOURCE_UNHEALTHY
    return ACTIVATION_OK


class RuntimePhaseClock:
    """Two clocks and a one-way transition between them.

    ``active_seconds`` is the ONLY clock the acceptance requirement reads.
    Pre-soak seconds are recorded as evidence and never counted toward it.
    """

    def __init__(
        self,
        *,
        required_active_seconds: float,
        monotonic_fn: Callable[[], float] = time.monotonic,
        now_iso_fn: Callable[[], str] = _utc_now,
    ) -> None:
        self._required = max(0.0, float(required_active_seconds))
        self._monotonic = monotonic_fn
        self._now_iso = now_iso_fn
        self._phase = PHASE_PRE_SOAK_RECOVERY
        self._started_monotonic = self._monotonic()
        self._pre_soak_start_utc = self._now_iso()
        self._pre_soak_end_utc: Optional[str] = None
        self._active_start_monotonic: Optional[float] = None
        self._active_start_utc: Optional[str] = None
        self._last_activation_reason = ACTIVATION_BLOCKED_RECOVERY_OPEN
        self._activation_evaluations = 0

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def is_active(self) -> bool:
        return self._phase == PHASE_ACTIVE_SOAK

    def delivery_permitted(self) -> bool:
        """Delivery is structurally impossible before the active phase.

        This is a SECOND, independent block: the cursor's source-health latch
        already refuses send authorization while recovery is unproven. Both must
        agree before an alert can be composed for real delivery.
        """

        return self.is_active

    def pre_soak_seconds(self) -> float:
        if self._active_start_monotonic is not None:
            return max(0.0, self._active_start_monotonic
                       - self._started_monotonic)
        return max(0.0, self._monotonic() - self._started_monotonic)

    def active_seconds(self) -> float:
        if self._active_start_monotonic is None:
            return 0.0
        return max(0.0, self._monotonic() - self._active_start_monotonic)

    def active_requirement_met(self) -> bool:
        return self.active_seconds() >= self._required

    def evaluate(self, inputs: ActivationInputs) -> str:
        """Evaluate the gate; transition once, and only forwards."""

        self._activation_evaluations += 1
        if self.is_active:
            self._last_activation_reason = ACTIVATION_OK
            return ACTIVATION_OK
        reason = evaluate_activation(inputs)
        self._last_activation_reason = reason
        if reason == ACTIVATION_OK:
            self._active_start_monotonic = self._monotonic()
            self._active_start_utc = self._now_iso()
            self._pre_soak_end_utc = self._active_start_utc
            self._phase = PHASE_ACTIVE_SOAK
        return reason

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe phase evidence. No value here is a secret."""

        return {
            "runtime_phase": self._phase,
            "required_active_soak_seconds": self._required,
            "pre_soak_recovery_start_utc": self._pre_soak_start_utc,
            "pre_soak_recovery_end_utc": self._pre_soak_end_utc,
            "pre_soak_recovery_seconds": round(self.pre_soak_seconds(), 3),
            "active_soak_start_utc": self._active_start_utc,
            "active_soak_elapsed_seconds": round(self.active_seconds(), 3),
            "active_soak_requirement_met": self.active_requirement_met(),
            "delivery_permitted_by_phase": self.delivery_permitted(),
            "last_activation_reason": self._last_activation_reason,
            "activation_evaluations": int(self._activation_evaluations),
        }


__all__ = (
    "ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING",
    "ACTIVATION_BLOCKED_OVERLAP_UNPROVEN",
    "ACTIVATION_BLOCKED_RECOVERY_OPEN",
    "ACTIVATION_BLOCKED_RECOVERY_TERMINAL",
    "ACTIVATION_BLOCKED_SOURCE_UNHEALTHY",
    "ACTIVATION_OK",
    "ACTIVATION_REASONS",
    "ActivationInputs",
    "PHASE_ACTIVE_SOAK",
    "PHASE_PRE_SOAK_RECOVERY",
    "RUNTIME_PHASES",
    "RuntimePhaseClock",
    "evaluate_activation",
)
