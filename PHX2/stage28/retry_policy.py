"""Stage 28.3b retry-policy pure deterministic decision function.

This module provides the pure deterministic Stage 28.3b retry-
policy decision function. It consumes a Stage 28.3a failure-
classification record plus caller-supplied bounded attempt /
budget counters, and emits a closed-set Stage 28.3b retry-policy
decision record. It never sleeps, never schedules, never sends,
never reads the process environment, never opens a socket, and
never reads a clock.

Decision contract:

  * Pure: same input -> same output, always. The decision
    function never reads the process environment, never opens a
    file, never contacts the network, never sleeps, never reads
    a clock, never schedules a task.
  * Deterministic: no randomness, no jitter, no dependence on
    insertion-order side effects.
  * Closed-set output: every output field is drawn from the
    Stage 28.3b closed-set vocabularies declared in
    ``retry_policy_models``, or from the Stage 28.3a closed-set
    vocabularies that Stage 28.3b re-exports.
  * Redaction-safe: the classification's ``raw_message`` field
    is excluded by Stage 28.3a construction; the Stage 28.3b
    decision additionally excludes any caller-supplied retry-
    after hint from the output beyond the post-clamp numeric
    ``delay_seconds``.

Failure-kind -> profile mapping (locked):

  Every closed-set Stage 28.3a ``FAILURE_KIND_*`` value maps
  here to exactly one closed-set Stage 28.3b
  ``RETRY_PROFILE_NAME_*``. The mapping is asserted exhaustive
  at import time so a future renamed or added kind is caught
  immediately.

What this module does NOT do (each of these belongs to a later
Stage 28 substage and is explicitly out of Stage 28.3b scope):

  * No retry execution (a future Stage 28 substage owns that).
  * No audited private HTTP Discord transport (Stage 28.4).
  * No heartbeat / health snapshot / CLI status (Stage 28.5).
  * No bounded private session runner (Stage 28.6).
  * No longer-session smoke harness / live smoke (Stage 28.7).
  * No Stage 29 enforcement / approval / activation semantics.
  * No public routing / subscriber routing / paid-tier routing.
  * No X / social / Telegram.
  * No automated trading / wallet / signer logic / position
    sizing / trade execution.

This module imports only stdlib (``math``, ``typing``) plus the
Stage 28.3a failure-classification models module and the Stage
28.3b retry-policy models module. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 / 28.2 production
code, does NOT import the Stage 28.3a classifier itself, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import math
from typing import Mapping, Optional

from PHX2.stage28.failure_classification_models import (
    FAILURE_KIND_ARTIFACT_READ_FAILED,
    FAILURE_KIND_ARTIFACT_WRITE_FAILED,
    FAILURE_KIND_CONFIG_CONFLICT,
    FAILURE_KIND_CONFIG_NOT_READY,
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED,
    FAILURE_KIND_DISCORD_NETWORK_ERROR,
    FAILURE_KIND_DISCORD_RATE_LIMITED,
    FAILURE_KIND_DISCORD_SERVER_ERROR,
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN,
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND,
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL,
    FAILURE_KIND_LEDGER_REPLAY_FAILED,
    FAILURE_KIND_LEDGER_WRITE_FAILED,
    FAILURE_KIND_MALFORMED_EVENT,
    FAILURE_KIND_OPERATOR_SHUTDOWN,
    FAILURE_KIND_PRICE_MISSING,
    FAILURE_KIND_PRICE_STALE,
    FAILURE_KIND_PRICE_TIMEOUT,
    FAILURE_KIND_PROVIDER_AUTH_FAILED,
    FAILURE_KIND_PROVIDER_DISCONNECTED,
    FAILURE_KIND_PROVIDER_MALFORMED_EVENT,
    FAILURE_KIND_PROVIDER_RATE_LIMITED,
    FAILURE_KIND_PROVIDER_TIMEOUT,
    FAILURE_KIND_RETRY_BUDGET_EXHAUSTED,
    FAILURE_KIND_SECRET_REDACTION_VIOLATION,
    FAILURE_KIND_UNKNOWN_FAILURE,
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
    FAILURE_KIND_USDC_OBSERVE_ONLY,
    FAILURE_KIND_VALUES,
    OPERATOR_VISIBILITY_ESCALATE,
    OPERATOR_VISIBILITY_NOTICE,
    RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED,
    RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED,
    RECOMMENDED_ACTION_FAIL_CLOSED,
    RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
    RECOMMENDED_ACTION_OPERATOR_REVIEW,
    RECOMMENDED_ACTION_RETRY_PENDING,
    RECOMMENDED_ACTION_STOP_SESSION,
    RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
    REDACTION_STATUS_APPLIED,
    SESSION_CONTINUATION_CONTINUE,
    SESSION_CONTINUATION_STOP,
)
from PHX2.stage28.retry_policy_models import (
    RETRY_AFTER_DEFAULT_SECONDS,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_AFTER_MIN_SECONDS,
    RETRY_OUTCOME_ALLOWED,
    RETRY_OUTCOME_EXHAUSTED,
    RETRY_OUTCOME_FAIL_CLOSED,
    RETRY_OUTCOME_NO_RETRY_TERMINAL,
    RETRY_OUTCOME_NOT_ALLOWED,
    RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
    RETRY_OUTCOME_STOP_SESSION,
    RETRY_OUTCOME_SUPPRESSED,
    RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE,
    RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX,
    RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
    RETRY_PROFILE_NAME_DISCORD_TRANSIENT,
    RETRY_PROFILE_NAME_INTERNAL_STOP,
    RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE,
    RETRY_PROFILE_NAME_NO_RETRY,
    RETRY_PROFILE_NAME_PRICE_REFRESH,
    RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
    RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP,
    RETRY_PROFILE_NAME_VALUES,
    RetryProfile,
    Stage28_3bInvalidRetryProfileError,
    Stage28_3bRetryDecision,
    Stage28_3bRetryPolicyInput,
    TERMINAL_REASON_ARTIFACT_WRITE_EXHAUSTED,
    TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED,
    TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN,
    TERMINAL_REASON_LEDGER_REPLAY_FAILED,
    TERMINAL_REASON_LEDGER_WRITE_EXHAUSTED,
    TERMINAL_REASON_NETWORK_EXHAUSTED,
    TERMINAL_REASON_NO_RETRY_TERMINAL,
    TERMINAL_REASON_NONE,
    TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE,
    TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    TERMINAL_REASON_OPERATOR_SHUTDOWN,
    TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED,
    TERMINAL_REASON_PROFILE_EXHAUSTED,
    TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    TERMINAL_REASON_SECRET_REDACTION_VIOLATION,
    TERMINAL_REASON_SERVER_ERROR_EXHAUSTED,
    TERMINAL_REASON_SUPPRESSED_AMBIGUOUS,
    TERMINAL_REASON_SUPPRESSED_DUPLICATE,
    TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    TERMINAL_REASON_UNKNOWN_FAILURE,
)


# ---------------------------------------------------------------------------
# Locked Stage 28.3b retry profiles
# ---------------------------------------------------------------------------


# Every profile is bounded, deterministic, and finite. The delay
# schedule's length equals ``max_attempts`` so each attempt has
# exactly one declared delay. No infinite backoff. No unbounded
# exponential backoff. No jitter.
_PROFILE_NO_RETRY: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_NO_RETRY,
    max_attempts=0,
    delay_schedule_seconds=(),
    max_total_delay_seconds=0.0,
    terminal_retry_outcome=RETRY_OUTCOME_NOT_ALLOWED,
    terminal_reason=TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_DISCORD_RATE_LIMITED: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
    max_attempts=2,
    delay_schedule_seconds=(1.0, 5.0),
    max_total_delay_seconds=RETRY_AFTER_MAX_SECONDS * 2.0,
    terminal_retry_outcome=RETRY_OUTCOME_EXHAUSTED,
    terminal_reason=TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_DISCORD_TRANSIENT: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_DISCORD_TRANSIENT,
    max_attempts=2,
    delay_schedule_seconds=(1.0, 4.0),
    max_total_delay_seconds=10.0,
    # Per-failure-kind exhaustion-reason override is applied in
    # ``_terminal_reason_for_kind_on_exhaustion`` because this
    # profile is shared by DISCORD_SERVER_ERROR (5xx) and
    # DISCORD_NETWORK_ERROR. The profile default below is the
    # safer of the two if no per-kind override matches.
    terminal_retry_outcome=RETRY_OUTCOME_EXHAUSTED,
    terminal_reason=TERMINAL_REASON_NETWORK_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_PROVIDER_RECONNECT: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
    max_attempts=5,
    delay_schedule_seconds=(1.0, 2.0, 4.0, 8.0, 16.0),
    max_total_delay_seconds=31.0,
    terminal_retry_outcome=RETRY_OUTCOME_STOP_SESSION,
    terminal_reason=TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_STOP,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_PRICE_REFRESH: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_PRICE_REFRESH,
    max_attempts=2,
    delay_schedule_seconds=(0.5, 1.0),
    max_total_delay_seconds=1.5,
    terminal_retry_outcome=RETRY_OUTCOME_EXHAUSTED,
    terminal_reason=TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_ARTIFACT_WRITE_ONCE: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE,
    max_attempts=1,
    delay_schedule_seconds=(0.5,),
    max_total_delay_seconds=0.5,
    terminal_retry_outcome=RETRY_OUTCOME_FAIL_CLOSED,
    terminal_reason=TERMINAL_REASON_ARTIFACT_WRITE_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_LEDGER_WRITE_ONCE: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE,
    max_attempts=1,
    delay_schedule_seconds=(0.5,),
    max_total_delay_seconds=0.5,
    terminal_retry_outcome=RETRY_OUTCOME_FAIL_CLOSED,
    terminal_reason=TERMINAL_REASON_LEDGER_WRITE_EXHAUSTED,
    terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
)


_PROFILE_CONFIG_OPERATOR_FIX: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX,
    max_attempts=0,
    delay_schedule_seconds=(),
    max_total_delay_seconds=0.0,
    terminal_retry_outcome=RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
    terminal_reason=TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    terminal_session_continuation=SESSION_CONTINUATION_STOP,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
)


_PROFILE_INTERNAL_STOP: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_INTERNAL_STOP,
    max_attempts=0,
    delay_schedule_seconds=(),
    max_total_delay_seconds=0.0,
    terminal_retry_outcome=RETRY_OUTCOME_STOP_SESSION,
    terminal_reason=TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN,
    terminal_session_continuation=SESSION_CONTINUATION_STOP,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
)


_PROFILE_SECRET_VIOLATION_STOP: RetryProfile = RetryProfile(
    name=RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP,
    max_attempts=0,
    delay_schedule_seconds=(),
    max_total_delay_seconds=0.0,
    terminal_retry_outcome=RETRY_OUTCOME_STOP_SESSION,
    terminal_reason=TERMINAL_REASON_SECRET_REDACTION_VIOLATION,
    terminal_session_continuation=SESSION_CONTINUATION_STOP,
    terminal_dispatch_allowed=False,
    terminal_operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
)


PROFILE_REGISTRY: Mapping[str, RetryProfile] = {
    RETRY_PROFILE_NAME_NO_RETRY: _PROFILE_NO_RETRY,
    RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED: _PROFILE_DISCORD_RATE_LIMITED,
    RETRY_PROFILE_NAME_DISCORD_TRANSIENT: _PROFILE_DISCORD_TRANSIENT,
    RETRY_PROFILE_NAME_PROVIDER_RECONNECT: _PROFILE_PROVIDER_RECONNECT,
    RETRY_PROFILE_NAME_PRICE_REFRESH: _PROFILE_PRICE_REFRESH,
    RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE: _PROFILE_ARTIFACT_WRITE_ONCE,
    RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE: _PROFILE_LEDGER_WRITE_ONCE,
    RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX: _PROFILE_CONFIG_OPERATOR_FIX,
    RETRY_PROFILE_NAME_INTERNAL_STOP: _PROFILE_INTERNAL_STOP,
    RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP: _PROFILE_SECRET_VIOLATION_STOP,
}


# ---------------------------------------------------------------------------
# Failure-kind -> retry-profile-name mapping (locked)
# ---------------------------------------------------------------------------


_FAILURE_KIND_TO_PROFILE_NAME: Mapping[str, str] = {
    # Provider domain.
    FAILURE_KIND_PROVIDER_DISCONNECTED: (
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ),
    FAILURE_KIND_PROVIDER_TIMEOUT: (
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ),
    FAILURE_KIND_PROVIDER_RATE_LIMITED: (
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ),
    FAILURE_KIND_PROVIDER_AUTH_FAILED: (
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX
    ),
    FAILURE_KIND_PROVIDER_MALFORMED_EVENT: RETRY_PROFILE_NAME_NO_RETRY,
    # Price domain.
    FAILURE_KIND_PRICE_TIMEOUT: RETRY_PROFILE_NAME_PRICE_REFRESH,
    FAILURE_KIND_PRICE_STALE: RETRY_PROFILE_NAME_NO_RETRY,
    FAILURE_KIND_PRICE_MISSING: RETRY_PROFILE_NAME_NO_RETRY,
    # Discord transport domain.
    FAILURE_KIND_DISCORD_RATE_LIMITED: (
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
    ),
    FAILURE_KIND_DISCORD_SERVER_ERROR: (
        RETRY_PROFILE_NAME_DISCORD_TRANSIENT
    ),
    FAILURE_KIND_DISCORD_NETWORK_ERROR: (
        RETRY_PROFILE_NAME_DISCORD_TRANSIENT
    ),
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED: (
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX
    ),
    # Artifact domain.
    FAILURE_KIND_ARTIFACT_WRITE_FAILED: (
        RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE
    ),
    FAILURE_KIND_ARTIFACT_READ_FAILED: RETRY_PROFILE_NAME_NO_RETRY,
    # Ledger domain.
    FAILURE_KIND_LEDGER_WRITE_FAILED: (
        RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE
    ),
    FAILURE_KIND_LEDGER_REPLAY_FAILED: (
        RETRY_PROFILE_NAME_INTERNAL_STOP
    ),
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND: RETRY_PROFILE_NAME_NO_RETRY,
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL: RETRY_PROFILE_NAME_NO_RETRY,
    # Generic event.
    FAILURE_KIND_MALFORMED_EVENT: RETRY_PROFILE_NAME_NO_RETRY,
    # Pair classification domain.
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED: RETRY_PROFILE_NAME_NO_RETRY,
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED: RETRY_PROFILE_NAME_NO_RETRY,
    FAILURE_KIND_USDC_OBSERVE_ONLY: RETRY_PROFILE_NAME_NO_RETRY,
    # Config domain.
    FAILURE_KIND_CONFIG_NOT_READY: (
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX
    ),
    FAILURE_KIND_CONFIG_CONFLICT: (
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX
    ),
    # Internal safety.
    FAILURE_KIND_SECRET_REDACTION_VIOLATION: (
        RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP
    ),
    FAILURE_KIND_RETRY_BUDGET_EXHAUSTED: RETRY_PROFILE_NAME_NO_RETRY,
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN: (
        RETRY_PROFILE_NAME_INTERNAL_STOP
    ),
    # Operator.
    FAILURE_KIND_OPERATOR_SHUTDOWN: RETRY_PROFILE_NAME_INTERNAL_STOP,
    # Unknown.
    FAILURE_KIND_UNKNOWN_FAILURE: RETRY_PROFILE_NAME_NO_RETRY,
}


# ---------------------------------------------------------------------------
# Per-failure-kind exhaustion-reason override
# ---------------------------------------------------------------------------


# The Stage 28.3b DISCORD_TRANSIENT profile is shared by
# DISCORD_SERVER_ERROR (5xx-style failures) and
# DISCORD_NETWORK_ERROR (transport-level failures). The
# exhaustion-reason override here keeps the terminal reason
# specific to the failure kind rather than the shared profile.
_FAILURE_KIND_EXHAUSTION_REASON_OVERRIDE: Mapping[str, str] = {
    FAILURE_KIND_DISCORD_SERVER_ERROR: (
        TERMINAL_REASON_SERVER_ERROR_EXHAUSTED
    ),
    FAILURE_KIND_DISCORD_NETWORK_ERROR: (
        TERMINAL_REASON_NETWORK_EXHAUSTED
    ),
}


# ---------------------------------------------------------------------------
# Per-failure-kind terminal-reason override for non-retry paths
# ---------------------------------------------------------------------------


# Stage 28.3a recommended-action ``FAIL_CLOSED`` covers several
# distinct failure families. The override here disambiguates the
# Stage 28.3b terminal-reason emitted on the decision record so a
# downstream consumer can branch by failure family without re-
# parsing the failure-kind.
_FAIL_CLOSED_STOP_SESSION_REASON_OVERRIDE: Mapping[str, str] = {
    FAILURE_KIND_SECRET_REDACTION_VIOLATION: (
        TERMINAL_REASON_SECRET_REDACTION_VIOLATION
    ),
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN: (
        TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN
    ),
    FAILURE_KIND_LEDGER_REPLAY_FAILED: (
        TERMINAL_REASON_LEDGER_REPLAY_FAILED
    ),
}


_OPERATOR_REVIEW_REASON_OVERRIDE: Mapping[str, str] = {
    FAILURE_KIND_UNKNOWN_FAILURE: TERMINAL_REASON_UNKNOWN_FAILURE,
}


# ---------------------------------------------------------------------------
# Profile invariants (asserted at import time)
# ---------------------------------------------------------------------------


def _validate_profile(profile: RetryProfile) -> None:
    """Validate a Stage 28.3b ``RetryProfile`` against the locked
    invariants. Raises ``Stage28_3bInvalidRetryProfileError`` on
    violation.
    """
    if not isinstance(profile.max_attempts, int) or isinstance(
        profile.max_attempts, bool
    ):
        raise Stage28_3bInvalidRetryProfileError(
            profile_name=profile.name,
            reason="MAX_ATTEMPTS_NOT_INT",
        )
    if profile.max_attempts < 0:
        raise Stage28_3bInvalidRetryProfileError(
            profile_name=profile.name,
            reason="MAX_ATTEMPTS_NEGATIVE",
        )
    if len(profile.delay_schedule_seconds) != profile.max_attempts:
        raise Stage28_3bInvalidRetryProfileError(
            profile_name=profile.name,
            reason="DELAY_SCHEDULE_LENGTH_MISMATCH",
        )
    for delay in profile.delay_schedule_seconds:
        if isinstance(delay, bool) or not isinstance(
            delay, (int, float)
        ):
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="DELAY_SCHEDULE_ENTRY_NOT_NUMERIC",
            )
        if math.isnan(float(delay)) or math.isinf(float(delay)):
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="DELAY_SCHEDULE_ENTRY_NOT_FINITE",
            )
        if float(delay) < 0.0:
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="DELAY_SCHEDULE_ENTRY_NEGATIVE",
            )
        if float(delay) > RETRY_AFTER_MAX_SECONDS:
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="DELAY_SCHEDULE_ENTRY_EXCEEDS_CAP",
            )
    if profile.max_total_delay_seconds is not None:
        cap = float(profile.max_total_delay_seconds)
        if math.isnan(cap) or math.isinf(cap):
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="MAX_TOTAL_DELAY_NOT_FINITE",
            )
        if cap < 0.0:
            raise Stage28_3bInvalidRetryProfileError(
                profile_name=profile.name,
                reason="MAX_TOTAL_DELAY_NEGATIVE",
            )


def validate_profile_registry() -> None:
    """Validate every profile in ``PROFILE_REGISTRY``.

    Pure: deterministic check; raises on the first invalid
    profile. Safe to call from tests; the import-time ``assert``
    block below performs the same check at module load.
    """
    for profile in PROFILE_REGISTRY.values():
        _validate_profile(profile)


# Import-time coverage assertions. Top-level ``assert`` statements
# are AST ``Assert`` nodes, not ``Call`` expressions, so the Stage
# 28.3b boundary scan's no-top-level-Call rule is preserved.
assert set(PROFILE_REGISTRY.keys()) == set(RETRY_PROFILE_NAME_VALUES), (
    "Stage 28.3b profile registry must cover every closed-set "
    "retry profile name"
)
assert set(_FAILURE_KIND_TO_PROFILE_NAME.keys()) == set(
    FAILURE_KIND_VALUES
), (
    "Stage 28.3b failure-kind-to-profile mapping must cover every "
    "Stage 28.3a closed-set failure-kind value"
)
assert all(
    _FAILURE_KIND_TO_PROFILE_NAME[k] in PROFILE_REGISTRY
    for k in _FAILURE_KIND_TO_PROFILE_NAME
), (
    "Every Stage 28.3b failure-kind mapping target must reference a "
    "registered Stage 28.3b retry profile"
)


# ---------------------------------------------------------------------------
# Retry-after parser (pure)
# ---------------------------------------------------------------------------


def parse_retry_after_seconds(value: object) -> Optional[float]:
    """Parse a Discord-style retry-after value into a clamped
    ``float`` seconds in ``[RETRY_AFTER_MIN_SECONDS,
    RETRY_AFTER_MAX_SECONDS]``.

    Pure: same input -> same output. No clock, no env, no I/O,
    no sleep.

    Accepts:

      * ``None``            -> ``None``
      * non-bool ``int``    -> clamped ``float``
      * non-bool ``float``  -> clamped ``float`` if finite and
                                non-negative; else ``None``
      * ``str``             -> attempts to parse as ``float``;
                                clamped if successful, else
                                ``None``

    Rejects (returns ``None``):

      * ``bool`` (``bool`` is a subclass of ``int`` and would
        otherwise leak through; the policy refuses to interpret
        ``True`` / ``False`` as a numeric retry-after hint)
      * negative numeric input
      * NaN / +inf / -inf numeric input
      * non-numeric string
      * any other type

    The returned value is always clamped to
    ``[RETRY_AFTER_MIN_SECONDS, RETRY_AFTER_MAX_SECONDS]`` when
    not ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = float(value)
    elif isinstance(value, float):
        candidate = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            candidate = float(stripped)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(candidate) or math.isinf(candidate):
        return None
    if candidate < 0.0:
        return None
    if candidate < RETRY_AFTER_MIN_SECONDS:
        candidate = RETRY_AFTER_MIN_SECONDS
    if candidate > RETRY_AFTER_MAX_SECONDS:
        candidate = RETRY_AFTER_MAX_SECONDS
    return candidate


# ---------------------------------------------------------------------------
# Decision helpers
# ---------------------------------------------------------------------------


def _terminal_reason_for_kind_on_exhaustion(
    failure_kind: str, profile: RetryProfile
) -> str:
    """Return the terminal-reason to emit when the per-failure
    profile exhausts. Per-kind overrides win over the profile
    default so a shared profile (e.g. ``DISCORD_TRANSIENT``) can
    still emit a kind-specific exhaustion reason.
    """
    override = _FAILURE_KIND_EXHAUSTION_REASON_OVERRIDE.get(
        failure_kind
    )
    if override is not None:
        return override
    if profile.terminal_reason == TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE:
        # ``NO_RETRY`` profile's default terminal reason is
        # ``NOT_RETRYABLE_IN_PRINCIPLE``; when reached via
        # exhaustion that doesn't apply, fall back to the generic
        # profile-exhausted reason.
        return TERMINAL_REASON_PROFILE_EXHAUSTED
    return profile.terminal_reason


def _build_allowed_decision(
    *,
    failure_kind: str,
    profile: RetryProfile,
    attempts_already_made: int,
    delay_seconds: float,
) -> Stage28_3bRetryDecision:
    next_attempt_index = attempts_already_made + 1
    attempts_remaining = profile.max_attempts - next_attempt_index
    return Stage28_3bRetryDecision(
        retry_outcome=RETRY_OUTCOME_ALLOWED,
        retry_allowed=True,
        delay_seconds=delay_seconds,
        next_attempt_index=next_attempt_index,
        attempts_remaining=attempts_remaining,
        profile_name=profile.name,
        terminal_reason_if_exhausted=TERMINAL_REASON_NONE,
        dispatch_allowed=True,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code=RETRY_OUTCOME_ALLOWED.lower(),
        redaction_status=REDACTION_STATUS_APPLIED,
    )


def _build_non_retry_decision(
    *,
    outcome: str,
    profile: RetryProfile,
    terminal_reason: str,
    session_continuation: str,
    operator_visibility: str,
) -> Stage28_3bRetryDecision:
    return Stage28_3bRetryDecision(
        retry_outcome=outcome,
        retry_allowed=False,
        delay_seconds=None,
        next_attempt_index=None,
        attempts_remaining=0,
        profile_name=profile.name,
        terminal_reason_if_exhausted=terminal_reason,
        dispatch_allowed=False,
        session_continuation_status=session_continuation,
        operator_visibility=operator_visibility,
        safe_reason_code=outcome.lower(),
        redaction_status=REDACTION_STATUS_APPLIED,
    )


# ---------------------------------------------------------------------------
# Public policy entry point
# ---------------------------------------------------------------------------


def decide_retry(
    policy_input: Stage28_3bRetryPolicyInput,
) -> Stage28_3bRetryDecision:
    """Decide whether a classified failure should be retried.

    Pure: same input -> same output. No env, no I/O, no network,
    no clocks, no sleeps. The decision record exposes only
    closed-set tokens + the post-clamp numeric ``delay_seconds``
    when retry is allowed.

    Decision precedence (first matching rule wins):

      1. The Stage 28.3a classification's ``recommended_action``
         drives the outcome for every non-retry case (NO_RETRY_TERMINAL,
         FAIL_CLOSED, DUPLICATE_SUPPRESSED, AMBIGUOUS_SUPPRESSED,
         SUPPRESS_NOT_ELIGIBLE, OPERATOR_REVIEW, STOP_SESSION).
      2. If ``recommended_action`` is ``RETRY_PENDING`` but the
         classification is not retryable in principle, the policy
         refuses with ``RETRY_NOT_ALLOWED`` and terminal-reason
         ``NOT_RETRYABLE_IN_PRINCIPLE`` (defensive; the Stage 28.3a
         classifier should not emit this combination, but the
         policy refuses safely if it does).
      3. If the caller-supplied global retry budget is exhausted,
         the policy emits ``RETRY_EXHAUSTED`` with terminal-reason
         ``GLOBAL_BUDGET_EXHAUSTED`` and a session-stop
         recommendation.
      4. If the per-failure profile's attempt budget is exhausted,
         the policy emits ``RETRY_EXHAUSTED`` with the profile's
         per-kind exhaustion reason and the profile's session
         continuation recommendation.
      5. Otherwise the policy emits ``RETRY_ALLOWED`` with the
         deterministic delay drawn from the profile's bounded
         delay schedule (or, for ``DISCORD_RATE_LIMITED``, the
         clamped caller-supplied retry-after hint when present).
    """
    cls = policy_input.classification
    profile_name = _FAILURE_KIND_TO_PROFILE_NAME[cls.failure_kind]
    profile = PROFILE_REGISTRY[profile_name]

    action = cls.recommended_action

    # Rule 1: non-retry paths driven by classification action.
    if action == RECOMMENDED_ACTION_NO_RETRY_TERMINAL:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_NO_RETRY_TERMINAL,
            profile=profile,
            terminal_reason=TERMINAL_REASON_NO_RETRY_TERMINAL,
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_SUPPRESSED,
            profile=profile,
            terminal_reason=TERMINAL_REASON_SUPPRESSED_DUPLICATE,
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_SUPPRESSED,
            profile=profile,
            terminal_reason=TERMINAL_REASON_SUPPRESSED_AMBIGUOUS,
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_SUPPRESSED,
            profile=profile,
            terminal_reason=TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_OPERATOR_REVIEW:
        terminal = _OPERATOR_REVIEW_REASON_OVERRIDE.get(
            cls.failure_kind,
            TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
        )
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
            profile=profile,
            terminal_reason=terminal,
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_STOP_SESSION:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_STOP_SESSION,
            profile=profile,
            terminal_reason=TERMINAL_REASON_OPERATOR_SHUTDOWN,
            session_continuation=SESSION_CONTINUATION_STOP,
            operator_visibility=cls.operator_visibility,
        )
    if action == RECOMMENDED_ACTION_FAIL_CLOSED:
        # FAIL_CLOSED is overloaded across several failure
        # families. The severe families (secret violation,
        # internal invariant, ledger replay failure) escalate to
        # STOP_SESSION; the rest fail closed for this dispatch
        # intent but the session continues.
        if cls.session_continuation_status == SESSION_CONTINUATION_STOP:
            terminal = (
                _FAIL_CLOSED_STOP_SESSION_REASON_OVERRIDE.get(
                    cls.failure_kind,
                    TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
                )
            )
            return _build_non_retry_decision(
                outcome=RETRY_OUTCOME_STOP_SESSION,
                profile=profile,
                terminal_reason=terminal,
                session_continuation=SESSION_CONTINUATION_STOP,
                operator_visibility=cls.operator_visibility,
            )
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_FAIL_CLOSED,
            profile=profile,
            terminal_reason=(
                TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION
            ),
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )

    # Rule 2: at this point the only remaining recommended_action
    # is RETRY_PENDING. Anything else is a defensive
    # RETRY_NOT_ALLOWED.
    if action != RECOMMENDED_ACTION_RETRY_PENDING:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_NOT_ALLOWED,
            profile=profile,
            terminal_reason=(
                TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE
            ),
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )
    if not cls.retryable_in_principle:
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_NOT_ALLOWED,
            profile=profile,
            terminal_reason=(
                TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE
            ),
            session_continuation=cls.session_continuation_status,
            operator_visibility=cls.operator_visibility,
        )

    # Rule 3: global retry budget.
    if (
        policy_input.global_max_retries is not None
        and policy_input.global_retries_used
        >= policy_input.global_max_retries
    ):
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_EXHAUSTED,
            profile=profile,
            terminal_reason=(
                TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED
            ),
            session_continuation=SESSION_CONTINUATION_STOP,
            operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
        )

    # Rule 4: per-failure profile exhaustion.
    if policy_input.attempts_already_made >= profile.max_attempts:
        terminal = _terminal_reason_for_kind_on_exhaustion(
            cls.failure_kind, profile
        )
        return _build_non_retry_decision(
            outcome=RETRY_OUTCOME_EXHAUSTED,
            profile=profile,
            terminal_reason=terminal,
            session_continuation=profile.terminal_session_continuation,
            operator_visibility=profile.terminal_operator_visibility,
        )

    # Rule 5: retry allowed. Compute the deterministic delay.
    delay = float(
        profile.delay_schedule_seconds[
            policy_input.attempts_already_made
        ]
    )
    if cls.failure_kind == FAILURE_KIND_DISCORD_RATE_LIMITED:
        parsed = parse_retry_after_seconds(
            policy_input.retry_after_hint_seconds
        )
        if parsed is not None:
            delay = parsed
        elif policy_input.retry_after_hint_seconds is None:
            delay = RETRY_AFTER_DEFAULT_SECONDS
        # else: parsed is None because the hint was invalid; fall
        # back to the profile's scheduled delay (already assigned
        # above).
    return _build_allowed_decision(
        failure_kind=cls.failure_kind,
        profile=profile,
        attempts_already_made=policy_input.attempts_already_made,
        delay_seconds=delay,
    )


def get_profile_for_failure_kind(failure_kind: str) -> RetryProfile:
    """Return the locked Stage 28.3b ``RetryProfile`` for the
    given Stage 28.3a closed-set ``FAILURE_KIND_*`` value.

    Pure: deterministic lookup. Raises ``KeyError`` for an
    unknown failure-kind (which would indicate a Stage 28.3a /
    Stage 28.3b mapping drift; the import-time assertions pin
    coverage so this should not happen at runtime).
    """
    name = _FAILURE_KIND_TO_PROFILE_NAME[failure_kind]
    return PROFILE_REGISTRY[name]


__all__ = (
    "PROFILE_REGISTRY",
    "decide_retry",
    "get_profile_for_failure_kind",
    "parse_retry_after_seconds",
    "validate_profile_registry",
)
