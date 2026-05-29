"""Stage 30.6.1 pure offline storage-budget policy evaluator.

Pure deterministic function ``evaluate_storage_budget(observation,
policy)`` that classifies a caller-supplied disk-used percentage
against a storage-budget policy into a closed-set
``Stage30_6StorageBudgetDecision``. This is the Stage 30.6 policy
brain: the deterministic disk-budget decision logic that lands BEFORE
any storage writer or 24h soak.

The evaluator NEVER reads actual disk, NEVER reads the process
environment, NEVER touches the filesystem or network, NEVER calls
``datetime.now``, and NEVER mutates its inputs. It is TOTAL: it never
raises for bad observation / policy input. Any invalid / missing /
misconfigured input fails closed to a ``STORAGE_BUDGET_INVALID_INPUT``
/ ``INVALID_INPUT_REFUSE_WRITES`` decision (refuse writes, emit a
private operator warning) rather than raising -- the Stage 30.6.0 spec
lock Section 5 discipline that "a full disk never produces a weird
crash". ``runtime_consumable`` is hard-locked ``False`` on every
decision: the decision is a recommendation, never a claim that a
write executed.

Classification (with a valid policy + valid observation):

  * ``disk_used_pct < soft``         -> ``STORAGE_BUDGET_OK`` /
                                        ``ALLOW_WRITES``.
  * ``soft <= disk_used_pct < hard`` -> ``STORAGE_BUDGET_SOFT_ALARM`` /
                                        ``ALLOW_WRITES_WITH_WARNING``.
  * ``disk_used_pct >= hard``        -> ``STORAGE_BUDGET_HARD_STOP`` /
                                        ``REFUSE_NEW_WRITES``.

With the default policy (soft 65.0 / hard 90.0): exactly 65.0 is a
SOFT_ALARM (>= soft, < hard) and exactly 90.0 is a HARD_STOP
(>= hard).

Discipline:

  * Stdlib only (``math`` / ``typing``).
  * Stage 30.6.1 sibling module ``stage30_6_storage_budget_models``
    imported read-only.
  * No ``os`` import, no env read, no ``pathlib`` / ``shutil`` /
    ``sqlite3`` / zstd import, no actual-disk read.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook, provider
    reference.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem / disk I/O at import time. No
    top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import math
from typing import Optional

from PHX2.stage30.stage30_6_storage_budget_models import (
    ALLOW_WRITES,
    ALLOW_WRITES_WITH_WARNING,
    INVALID_INPUT_REFUSE_WRITES,
    REFUSE_NEW_WRITES,
    STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
    STORAGE_BUDGET_HARD_STOP,
    STORAGE_BUDGET_INVALID_INPUT,
    STORAGE_BUDGET_MAX_USED_PCT,
    STORAGE_BUDGET_MIN_USED_PCT,
    STORAGE_BUDGET_OK,
    STORAGE_BUDGET_REASON_HARD_STOP_REACHED,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
    STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED,
    STORAGE_BUDGET_SOFT_ALARM,
    Stage30_6StorageBudgetDecision,
    Stage30_6StorageBudgetPolicy,
    is_finite_real,
)


# ---------------------------------------------------------------------------
# Internal helpers (pure)
# ---------------------------------------------------------------------------


def _finite_real_or_none(value: object) -> Optional[float]:
    """Return ``float(value)`` if ``value`` is a finite real number
    (and not a ``bool``); otherwise ``None``.

    A very large ``int`` that cannot be represented as a ``float``
    yields ``None`` (the ``OverflowError`` is swallowed) so this helper
    is total and never raises.
    """
    if not is_finite_real(value):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (OverflowError, ValueError):
        return None


def _build_decision(
    *,
    status: str,
    action: str,
    should_allow_new_writes: bool,
    should_emit_operator_warning: bool,
    reason: str,
    disk_used_pct: Optional[float],
    soft_alarm_used_pct: Optional[float],
    hard_stop_used_pct: Optional[float],
    policy_version: Optional[str],
) -> Stage30_6StorageBudgetDecision:
    return Stage30_6StorageBudgetDecision(
        schema_version=STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
        status=status,
        action=action,
        should_allow_new_writes=should_allow_new_writes,
        should_emit_operator_warning=should_emit_operator_warning,
        reason=reason,
        disk_used_pct=disk_used_pct,
        soft_alarm_used_pct=soft_alarm_used_pct,
        hard_stop_used_pct=hard_stop_used_pct,
        policy_version=policy_version,
        runtime_consumable=False,
    )


def _invalid_decision(
    *,
    reason: str,
    disk_used_pct: Optional[float],
    soft_alarm_used_pct: Optional[float],
    hard_stop_used_pct: Optional[float],
    policy_version: Optional[str],
) -> Stage30_6StorageBudgetDecision:
    """Build the fail-closed INVALID_INPUT decision: refuse new writes
    and emit a private operator warning.
    """
    return _build_decision(
        status=STORAGE_BUDGET_INVALID_INPUT,
        action=INVALID_INPUT_REFUSE_WRITES,
        should_allow_new_writes=False,
        should_emit_operator_warning=True,
        reason=reason,
        disk_used_pct=disk_used_pct,
        soft_alarm_used_pct=soft_alarm_used_pct,
        hard_stop_used_pct=hard_stop_used_pct,
        policy_version=policy_version,
    )


# ---------------------------------------------------------------------------
# Public: evaluate_storage_budget
# ---------------------------------------------------------------------------


def evaluate_storage_budget(
    observation: object,
    policy: Optional[object] = None,
) -> Stage30_6StorageBudgetDecision:
    """Classify a caller-supplied disk-used percentage against a
    storage-budget policy into a closed-set decision.

    Pure / deterministic / total. NEVER reads actual disk, NEVER reads
    the process environment, NEVER touches the filesystem or network,
    NEVER calls ``datetime.now``. NEVER raises for bad observation /
    policy input: any invalid / missing / misconfigured input fails
    closed to ``STORAGE_BUDGET_INVALID_INPUT`` /
    ``INVALID_INPUT_REFUSE_WRITES`` (refuse writes, emit operator
    warning). ``runtime_consumable`` is hard-locked ``False`` on every
    decision.

    Fail-closed INVALID_INPUT cases:

      * policy threshold non-numeric / non-finite,
      * policy threshold outside [0, 100],
      * policy ``soft >= hard`` inversion,
      * observation ``disk_used_pct`` missing (``None``),
      * observation ``disk_used_pct`` non-number (incl. ``bool``),
      * observation ``disk_used_pct`` non-finite (NaN / inf),
      * observation ``disk_used_pct`` outside [0, 100].

    ``policy`` defaults to a default ``Stage30_6StorageBudgetPolicy``
    (soft 65.0 / hard 90.0) when ``None``. Both ``policy`` and
    ``observation`` are read duck-typed via ``getattr`` so a simple
    namespace satisfies the contract; a ``None`` / attribute-less
    observation degrades to the missing-disk fail-closed decision.
    """
    if policy is None:
        policy = Stage30_6StorageBudgetPolicy()

    raw_policy_version = getattr(policy, "policy_version", None)
    policy_version: Optional[str] = (
        raw_policy_version
        if isinstance(raw_policy_version, str)
        else None
    )

    raw_soft = getattr(policy, "soft_alarm_used_pct", None)
    raw_hard = getattr(policy, "hard_stop_used_pct", None)
    soft = _finite_real_or_none(raw_soft)
    hard = _finite_real_or_none(raw_hard)

    raw_disk = getattr(observation, "disk_used_pct", None)
    disk_echo = _finite_real_or_none(raw_disk)

    # ----- Policy validity (fail closed) ---------------------------------
    if soft is None or hard is None:
        return _invalid_decision(
            reason=(
                STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC
            ),
            disk_used_pct=disk_echo,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    if not (
        STORAGE_BUDGET_MIN_USED_PCT <= soft <= STORAGE_BUDGET_MAX_USED_PCT
        and STORAGE_BUDGET_MIN_USED_PCT
        <= hard
        <= STORAGE_BUDGET_MAX_USED_PCT
    ):
        return _invalid_decision(
            reason=(
                STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE
            ),
            disk_used_pct=disk_echo,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    if soft >= hard:
        return _invalid_decision(
            reason=STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD,
            disk_used_pct=disk_echo,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )

    # ----- Observation validity (fail closed) ----------------------------
    if raw_disk is None:
        return _invalid_decision(
            reason=STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING,
            disk_used_pct=None,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    if isinstance(raw_disk, bool) or not isinstance(
        raw_disk, (int, float)
    ):
        return _invalid_decision(
            reason=STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER,
            disk_used_pct=None,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    if isinstance(raw_disk, float) and not math.isfinite(raw_disk):
        return _invalid_decision(
            reason=STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
            disk_used_pct=None,
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )

    # ``raw_disk`` is now a finite real (an ``int`` or a finite
    # ``float``). The range / classification comparisons run on
    # ``raw_disk`` directly so a very large ``int`` never triggers an
    # ``OverflowError`` via ``float()``; the echoed value is the safe
    # ``float`` form (``None`` if it cannot be represented).
    if not (
        STORAGE_BUDGET_MIN_USED_PCT
        <= raw_disk
        <= STORAGE_BUDGET_MAX_USED_PCT
    ):
        return _invalid_decision(
            reason=(
                STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE
            ),
            disk_used_pct=_finite_real_or_none(raw_disk),
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )

    # ----- Classify (deterministic) --------------------------------------
    if raw_disk >= hard:
        return _build_decision(
            status=STORAGE_BUDGET_HARD_STOP,
            action=REFUSE_NEW_WRITES,
            should_allow_new_writes=False,
            should_emit_operator_warning=True,
            reason=STORAGE_BUDGET_REASON_HARD_STOP_REACHED,
            disk_used_pct=_finite_real_or_none(raw_disk),
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    if raw_disk >= soft:
        return _build_decision(
            status=STORAGE_BUDGET_SOFT_ALARM,
            action=ALLOW_WRITES_WITH_WARNING,
            should_allow_new_writes=True,
            should_emit_operator_warning=True,
            reason=STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED,
            disk_used_pct=_finite_real_or_none(raw_disk),
            soft_alarm_used_pct=soft,
            hard_stop_used_pct=hard,
            policy_version=policy_version,
        )
    return _build_decision(
        status=STORAGE_BUDGET_OK,
        action=ALLOW_WRITES,
        should_allow_new_writes=True,
        should_emit_operator_warning=False,
        reason=STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
        disk_used_pct=_finite_real_or_none(raw_disk),
        soft_alarm_used_pct=soft,
        hard_stop_used_pct=hard,
        policy_version=policy_version,
    )


__all__ = (
    "evaluate_storage_budget",
)
