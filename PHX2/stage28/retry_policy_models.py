"""Stage 28.3b retry-policy closed-set vocabularies + records.

Stage 28.3b ships pure, deterministic, redaction-safe retry-
policy primitives for Stage 28 reliability hardening. The retry
policy consumes Stage 28.3a failure-classification outputs and
produces bounded, deterministic retry decisions for future Stage
28 runner / transport substages.

The retry-policy primitives answer, for a single classified
failure:

  * Is this failure retryable under the current policy?
  * How many bounded attempts are permitted?
  * Has the per-failure or global retry budget been exhausted?
  * What deterministic delay should a future runner wait before
    the next attempt (no sleep is ever performed here)?
  * What terminal outcome should be emitted on exhaustion?
  * Should future behavior continue the session, suppress the
    dispatch intent, fail closed, or stop the session?

Stage 28.3b is NOT a retry executor. Stage 28.3b emits a
decision record only; it never sleeps, never schedules, never
sends, never opens a socket, never reads a clock, never reads
the process environment. A future Stage 28 substage will be the
retry executor; Stage 28.3b is the contracts layer that the
executor will consume.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here; the Stage 28.3b boundary scan pins
    this.
  * No network. No HTTP. No gRPC. No private dispatch. No
    provider connection. No file I/O at import or call time.
  * No sleep. No backoff execution. No scheduling. No queue.
    No threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.3b record.
    Even when an upstream caller might have constructed a
    ``raw_message`` on the Stage 28.3a input layer, the Stage
    28.3b retry-policy output never re-exposes it; the decision
    record exposes only closed-set tokens + a closed-set safe
    reason code.
  * ``repr()`` / ``str()`` of any Stage 28.3b record is safe to
    log / print / persist; no URL host substring, no API-key
    substring, no bearer-token substring, no private webhook
    substring, and no raw exception text reaches the decision
    record.

This module imports only stdlib (``typing``) plus the Stage
28.3a failure-classification models module. It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2
production code, does NOT import the Stage 28.3a classifier
itself, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from PHX2.stage28.failure_classification_models import (
    OPERATOR_VISIBILITY_VALUES as _OPERATOR_VISIBILITY_VALUES,
    REDACTION_STATUS_VALUES as _REDACTION_STATUS_VALUES,
    SESSION_CONTINUATION_STATUS_VALUES as _SESSION_CONTINUATION_STATUS_VALUES,
    Stage28_3aFailureClassification,
)


# ---------------------------------------------------------------------------
# Stage 28.3b version axes
# ---------------------------------------------------------------------------


STAGE28_3B_MINOR_VERSION: str = "28.3b"
STAGE28_3B_SCHEMA_VERSION: str = "stage28_3b_retry_policy_v0"


# Distinctive Stage 28.3b redaction token. Distinct from the Stage
# 27, Stage 28.1, Stage 28.2, and Stage 28.3a redaction tokens so a
# leak-scan test for one cannot collide with another.
STAGE28_3B_REDACTION_TOKEN: str = "<<STAGE28_3B_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: retry outcomes
# ---------------------------------------------------------------------------


# Closed-set retry-outcome tokens. Every Stage 28.3b decision
# record carries exactly one of these. The set is intentionally
# broad enough to express both the retry verdict (allowed /
# exhausted / suppressed / not-allowed) and the terminal-state
# verdict (fail-closed / stop-session / operator-review-required /
# no-retry-terminal); a single closed-set keeps downstream
# branching narrow.
RETRY_OUTCOME_ALLOWED: str = "RETRY_ALLOWED"
RETRY_OUTCOME_NOT_ALLOWED: str = "RETRY_NOT_ALLOWED"
RETRY_OUTCOME_EXHAUSTED: str = "RETRY_EXHAUSTED"
RETRY_OUTCOME_SUPPRESSED: str = "RETRY_SUPPRESSED"
RETRY_OUTCOME_FAIL_CLOSED: str = "FAIL_CLOSED"
RETRY_OUTCOME_STOP_SESSION: str = "STOP_SESSION"
RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED: str = (
    "OPERATOR_REVIEW_REQUIRED"
)
RETRY_OUTCOME_NO_RETRY_TERMINAL: str = "NO_RETRY_TERMINAL"


RETRY_OUTCOME_VALUES: tuple[str, ...] = (
    RETRY_OUTCOME_ALLOWED,
    RETRY_OUTCOME_NOT_ALLOWED,
    RETRY_OUTCOME_EXHAUSTED,
    RETRY_OUTCOME_SUPPRESSED,
    RETRY_OUTCOME_FAIL_CLOSED,
    RETRY_OUTCOME_STOP_SESSION,
    RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
    RETRY_OUTCOME_NO_RETRY_TERMINAL,
)


# Outcomes that mean "no retry is happening from this decision".
# The retry-policy decision function uses this set to derive the
# ``retry_allowed`` boolean.
_NON_RETRY_ALLOWED_OUTCOMES: frozenset[str] = frozenset(
    {
        RETRY_OUTCOME_NOT_ALLOWED,
        RETRY_OUTCOME_EXHAUSTED,
        RETRY_OUTCOME_SUPPRESSED,
        RETRY_OUTCOME_FAIL_CLOSED,
        RETRY_OUTCOME_STOP_SESSION,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        RETRY_OUTCOME_NO_RETRY_TERMINAL,
    }
)


# ---------------------------------------------------------------------------
# Closed-set: retry profile names
# ---------------------------------------------------------------------------


# Closed-set Stage 28.3b retry-profile names. Each profile is a
# bounded retry schedule with an explicit terminal outcome.
RETRY_PROFILE_NAME_NO_RETRY: str = "NO_RETRY"
RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED: str = (
    "DISCORD_RATE_LIMITED"
)
RETRY_PROFILE_NAME_DISCORD_TRANSIENT: str = "DISCORD_TRANSIENT"
RETRY_PROFILE_NAME_PROVIDER_RECONNECT: str = "PROVIDER_RECONNECT"
RETRY_PROFILE_NAME_PRICE_REFRESH: str = "PRICE_REFRESH"
RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE: str = "ARTIFACT_WRITE_ONCE"
RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE: str = "LEDGER_WRITE_ONCE"
RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX: str = "CONFIG_OPERATOR_FIX"
RETRY_PROFILE_NAME_INTERNAL_STOP: str = "INTERNAL_STOP"
RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP: str = (
    "SECRET_VIOLATION_STOP"
)


RETRY_PROFILE_NAME_VALUES: tuple[str, ...] = (
    RETRY_PROFILE_NAME_NO_RETRY,
    RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
    RETRY_PROFILE_NAME_DISCORD_TRANSIENT,
    RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
    RETRY_PROFILE_NAME_PRICE_REFRESH,
    RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE,
    RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE,
    RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX,
    RETRY_PROFILE_NAME_INTERNAL_STOP,
    RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP,
)


# ---------------------------------------------------------------------------
# Closed-set: terminal reasons
# ---------------------------------------------------------------------------


# Closed-set Stage 28.3b terminal reasons. Populated on the
# ``terminal_reason_if_exhausted`` field of the decision record
# when the retry verdict is NOT ``RETRY_ALLOWED``. Each token is
# safe-to-log / safe-to-persist; no raw secret material reaches
# this surface.
TERMINAL_REASON_NONE: str = "NONE"
TERMINAL_REASON_PROFILE_EXHAUSTED: str = "PROFILE_EXHAUSTED"
TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED: str = (
    "GLOBAL_BUDGET_EXHAUSTED"
)
TERMINAL_REASON_RATE_LIMIT_EXHAUSTED: str = "RATE_LIMIT_EXHAUSTED"
TERMINAL_REASON_SERVER_ERROR_EXHAUSTED: str = (
    "SERVER_ERROR_EXHAUSTED"
)
TERMINAL_REASON_NETWORK_EXHAUSTED: str = "NETWORK_EXHAUSTED"
TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED: str = (
    "PROVIDER_RECONNECT_EXHAUSTED"
)
TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED: str = (
    "PRICE_REFRESH_EXHAUSTED"
)
TERMINAL_REASON_ARTIFACT_WRITE_EXHAUSTED: str = (
    "ARTIFACT_WRITE_EXHAUSTED"
)
TERMINAL_REASON_LEDGER_WRITE_EXHAUSTED: str = (
    "LEDGER_WRITE_EXHAUSTED"
)
TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE: str = (
    "NOT_RETRYABLE_IN_PRINCIPLE"
)
TERMINAL_REASON_SUPPRESSED_DUPLICATE: str = "SUPPRESSED_DUPLICATE"
TERMINAL_REASON_SUPPRESSED_AMBIGUOUS: str = (
    "SUPPRESSED_AMBIGUOUS"
)
TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE: str = (
    "SUPPRESSED_NOT_ELIGIBLE"
)
TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION: str = (
    "FAIL_CLOSED_BY_CLASSIFICATION"
)
TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED: str = (
    "OPERATOR_REVIEW_REQUIRED"
)
TERMINAL_REASON_OPERATOR_SHUTDOWN: str = "OPERATOR_SHUTDOWN"
TERMINAL_REASON_SECRET_REDACTION_VIOLATION: str = (
    "SECRET_REDACTION_VIOLATION"
)
TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN: str = (
    "INTERNAL_INVARIANT_BROKEN"
)
TERMINAL_REASON_LEDGER_REPLAY_FAILED: str = "LEDGER_REPLAY_FAILED"
TERMINAL_REASON_NO_RETRY_TERMINAL: str = "NO_RETRY_TERMINAL"
TERMINAL_REASON_UNKNOWN_FAILURE: str = "UNKNOWN_FAILURE"


TERMINAL_REASON_VALUES: tuple[str, ...] = (
    TERMINAL_REASON_NONE,
    TERMINAL_REASON_PROFILE_EXHAUSTED,
    TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED,
    TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    TERMINAL_REASON_SERVER_ERROR_EXHAUSTED,
    TERMINAL_REASON_NETWORK_EXHAUSTED,
    TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED,
    TERMINAL_REASON_ARTIFACT_WRITE_EXHAUSTED,
    TERMINAL_REASON_LEDGER_WRITE_EXHAUSTED,
    TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE,
    TERMINAL_REASON_SUPPRESSED_DUPLICATE,
    TERMINAL_REASON_SUPPRESSED_AMBIGUOUS,
    TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    TERMINAL_REASON_OPERATOR_SHUTDOWN,
    TERMINAL_REASON_SECRET_REDACTION_VIOLATION,
    TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN,
    TERMINAL_REASON_LEDGER_REPLAY_FAILED,
    TERMINAL_REASON_NO_RETRY_TERMINAL,
    TERMINAL_REASON_UNKNOWN_FAILURE,
)


# ---------------------------------------------------------------------------
# Retry-after handling caps
# ---------------------------------------------------------------------------


# Locked retry-after cap. Any caller-supplied numeric retry-after
# hint is clamped to this maximum before the decision is emitted.
# Stage 28.3b never sleeps; the cap exists to keep a future
# executor's bounded wait small.
RETRY_AFTER_MAX_SECONDS: float = 30.0


# Locked floor: retry-after hints below the floor are treated as
# the floor. Prevents a malicious / buggy hint from collapsing to
# zero.
RETRY_AFTER_MIN_SECONDS: float = 0.0


# Locked default delay used when the caller signals "rate limited"
# but does NOT supply a numeric retry-after hint.
RETRY_AFTER_DEFAULT_SECONDS: float = 1.0


# ---------------------------------------------------------------------------
# Retry profile record
# ---------------------------------------------------------------------------


class RetryProfile(NamedTuple):
    """Immutable Stage 28.3b retry profile.

    Closed-set fields:

      * ``name``                           -- closed-set
                                              ``RETRY_PROFILE_NAME_*``
                                              token.
      * ``max_attempts``                   -- non-negative ``int``;
                                              the maximum number of
                                              bounded retry attempts
                                              the profile permits.
                                              ``0`` means no retry.
      * ``delay_schedule_seconds``         -- finite tuple of non-
                                              negative ``float``
                                              delays. Length MUST
                                              equal ``max_attempts``.
                                              The delay for the
                                              ``i``-th retry (1-based
                                              attempt index ``i``) is
                                              ``delay_schedule_seconds[i-1]``.
      * ``max_total_delay_seconds``        -- optional non-negative
                                              ``float``; the policy
                                              caps cumulative delay
                                              at this value when
                                              non-``None``.
      * ``terminal_retry_outcome``         -- closed-set
                                              ``RETRY_OUTCOME_*`` to
                                              emit when the profile
                                              has no remaining
                                              attempts.
      * ``terminal_reason``                -- closed-set
                                              ``TERMINAL_REASON_*``
                                              to emit alongside the
                                              terminal outcome.
      * ``terminal_session_continuation``  -- closed-set
                                              ``SESSION_CONTINUATION_*``
                                              recommendation when
                                              terminal.
      * ``terminal_dispatch_allowed``      -- ``bool``; whether the
                                              future runner may
                                              attempt to dispatch
                                              after exhaustion.
                                              Always ``False`` for
                                              Stage 28.3b profiles.
      * ``terminal_operator_visibility``   -- closed-set
                                              ``OPERATOR_VISIBILITY_*``
                                              recommendation when
                                              terminal.
    """

    name: str
    max_attempts: int
    delay_schedule_seconds: tuple[float, ...]
    max_total_delay_seconds: Optional[float]
    terminal_retry_outcome: str
    terminal_reason: str
    terminal_session_continuation: str
    terminal_dispatch_allowed: bool
    terminal_operator_visibility: str


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_3bRetryPolicyError(Exception):
    """Base type for every Stage 28.3b retry-policy error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_3bInvalidRetryPolicyInputError(
    Stage28_3bRetryPolicyError
):
    """Raised when a ``Stage28_3bRetryPolicyInput`` field fails
    Stage 28.3b construction validation.

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.3b invalid retry-policy input: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_3bInvalidRetryProfileError(Stage28_3bRetryPolicyError):
    """Raised when a ``RetryProfile`` instance fails the locked
    Stage 28.3b profile invariants (length / sign / cap checks).

    Carries only the profile name + a closed-set reason token;
    never the raw rejected value.
    """

    def __init__(self, profile_name: str, reason: str) -> None:
        self.profile_name: str = profile_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.3b invalid retry profile: "
            f"profile_name={profile_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def is_retry_outcome_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3b
    retry-outcome token."""
    return isinstance(value, str) and value in RETRY_OUTCOME_VALUES


def is_retry_profile_name_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3b
    retry-profile-name token."""
    return (
        isinstance(value, str) and value in RETRY_PROFILE_NAME_VALUES
    )


def is_terminal_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3b
    terminal-reason token."""
    return (
        isinstance(value, str) and value in TERMINAL_REASON_VALUES
    )


def is_retry_allowed_outcome(value: object) -> bool:
    """Return ``True`` iff ``value`` is exactly the
    ``RETRY_ALLOWED`` outcome."""
    return value == RETRY_OUTCOME_ALLOWED


def is_non_retry_outcome(value: object) -> bool:
    """Return ``True`` iff ``value`` is one of the closed-set
    non-retry outcomes (i.e. any Stage 28.3b outcome except
    ``RETRY_ALLOWED``)."""
    return (
        isinstance(value, str) and value in _NON_RETRY_ALLOWED_OUTCOMES
    )


# ---------------------------------------------------------------------------
# Stage28_3bRetryPolicyInput
# ---------------------------------------------------------------------------


class Stage28_3bRetryPolicyInput(NamedTuple):
    """Immutable Stage 28.3b retry-policy input.

    Closed-set / opaque fields:

      * ``classification``                 -- locked Stage 28.3a
                                              ``Stage28_3aFailureClassification``
                                              record; the policy
                                              never re-classifies and
                                              never mutates this
                                              value.
      * ``attempts_already_made``          -- zero-based count of
                                              retry attempts already
                                              executed for the
                                              current dispatch
                                              intent. The next retry,
                                              if allowed, will be
                                              attempt index
                                              ``attempts_already_made
                                              + 1`` (1-based).
      * ``global_retries_used``            -- zero-based count of
                                              retries already used
                                              across the current
                                              session-wide budget.
                                              The policy never
                                              persists this; the
                                              caller supplies it.
      * ``global_max_retries``             -- non-negative ``int``
                                              session-wide retry
                                              budget cap. ``None``
                                              means the policy
                                              does not enforce a
                                              session-wide cap.
      * ``retry_after_hint_seconds``       -- optional ``float`` /
                                              ``int`` retry-after
                                              hint. Used only by the
                                              ``DISCORD_RATE_LIMITED``
                                              profile; clamped by the
                                              policy. Negative / NaN /
                                              infinite / huge values
                                              are refused (defaulted)
                                              by the policy.

    The named-tuple shape gives the record built-in immutability,
    structural equality, and a safe ``repr()`` over its declared
    fields. The classification field is itself a Stage 28.3a
    closed-set NamedTuple, so ``repr()`` of the policy input never
    exposes raw secret material from the upstream failure source.
    """

    classification: Stage28_3aFailureClassification
    attempts_already_made: int
    global_retries_used: int
    global_max_retries: Optional[int]
    retry_after_hint_seconds: Optional[float]


def build_retry_policy_input(
    *,
    classification: Stage28_3aFailureClassification,
    attempts_already_made: int = 0,
    global_retries_used: int = 0,
    global_max_retries: Optional[int] = None,
    retry_after_hint_seconds: Optional[float] = None,
) -> Stage28_3bRetryPolicyInput:
    """Construct an immutable ``Stage28_3bRetryPolicyInput`` from
    keyword-only fields.

    Validation:

      * ``classification`` MUST be a Stage 28.3a
        ``Stage28_3aFailureClassification`` instance.
      * ``attempts_already_made`` MUST be a non-negative ``int``
        (booleans are rejected because ``bool`` is a subclass of
        ``int`` and would otherwise leak through).
      * ``global_retries_used`` MUST be a non-negative ``int``
        (booleans rejected as above).
      * ``global_max_retries`` MUST be ``None`` or a non-negative
        ``int`` (booleans rejected).
      * ``retry_after_hint_seconds`` MUST be ``None`` or a numeric
        ``int`` / ``float``; the policy itself further refuses
        negative / NaN / infinite / huge values when consuming
        the hint, so this constructor accepts any numeric shape
        and defers semantic clamping to the policy.
    """
    if not isinstance(classification, Stage28_3aFailureClassification):
        raise Stage28_3bInvalidRetryPolicyInputError(
            field_name="classification",
            reason="CLASSIFICATION_NOT_STAGE_28_3A_RECORD",
        )
    if isinstance(attempts_already_made, bool) or not isinstance(
        attempts_already_made, int
    ):
        raise Stage28_3bInvalidRetryPolicyInputError(
            field_name="attempts_already_made",
            reason="ATTEMPTS_NOT_INT",
        )
    if attempts_already_made < 0:
        raise Stage28_3bInvalidRetryPolicyInputError(
            field_name="attempts_already_made",
            reason="ATTEMPTS_NEGATIVE",
        )
    if isinstance(global_retries_used, bool) or not isinstance(
        global_retries_used, int
    ):
        raise Stage28_3bInvalidRetryPolicyInputError(
            field_name="global_retries_used",
            reason="GLOBAL_USED_NOT_INT",
        )
    if global_retries_used < 0:
        raise Stage28_3bInvalidRetryPolicyInputError(
            field_name="global_retries_used",
            reason="GLOBAL_USED_NEGATIVE",
        )
    if global_max_retries is not None:
        if isinstance(global_max_retries, bool) or not isinstance(
            global_max_retries, int
        ):
            raise Stage28_3bInvalidRetryPolicyInputError(
                field_name="global_max_retries",
                reason="GLOBAL_MAX_NOT_INT",
            )
        if global_max_retries < 0:
            raise Stage28_3bInvalidRetryPolicyInputError(
                field_name="global_max_retries",
                reason="GLOBAL_MAX_NEGATIVE",
            )
    if retry_after_hint_seconds is not None:
        if isinstance(
            retry_after_hint_seconds, bool
        ) or not isinstance(
            retry_after_hint_seconds, (int, float)
        ):
            raise Stage28_3bInvalidRetryPolicyInputError(
                field_name="retry_after_hint_seconds",
                reason="RETRY_AFTER_NOT_NUMERIC",
            )
    return Stage28_3bRetryPolicyInput(
        classification=classification,
        attempts_already_made=attempts_already_made,
        global_retries_used=global_retries_used,
        global_max_retries=global_max_retries,
        retry_after_hint_seconds=(
            float(retry_after_hint_seconds)
            if retry_after_hint_seconds is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Stage28_3bRetryDecision (output)
# ---------------------------------------------------------------------------


class Stage28_3bRetryDecision(NamedTuple):
    """Immutable Stage 28.3b retry-policy decision output.

    Closed-set fields:

      * ``retry_outcome``                  -- ``RETRY_OUTCOME_*``.
      * ``retry_allowed``                  -- ``bool``; ``True`` iff
                                              ``retry_outcome ==
                                              RETRY_ALLOWED``.
      * ``delay_seconds``                  -- optional non-negative
                                              ``float`` delay for the
                                              next retry attempt;
                                              ``None`` when no retry
                                              is allowed.
      * ``next_attempt_index``             -- 1-based attempt index
                                              the next retry would
                                              take; ``None`` when no
                                              retry is allowed.
      * ``attempts_remaining``             -- non-negative ``int``
                                              count of retry attempts
                                              still permitted under
                                              this profile (after
                                              this decision).
      * ``profile_name``                   -- closed-set
                                              ``RETRY_PROFILE_NAME_*``
                                              the policy used.
      * ``terminal_reason_if_exhausted``   -- closed-set
                                              ``TERMINAL_REASON_*``;
                                              always populated
                                              (``NONE`` when retry is
                                              allowed).
      * ``dispatch_allowed``               -- ``bool``; whether the
                                              future runner may
                                              attempt to dispatch.
                                              Always ``False`` for
                                              non-retry outcomes;
                                              ``True`` is reserved
                                              for the
                                              ``RETRY_ALLOWED`` path
                                              (which means the
                                              executor may try the
                                              next attempt).
      * ``session_continuation_status``    -- closed-set
                                              ``SESSION_CONTINUATION_*``.
      * ``operator_visibility``            -- closed-set
                                              ``OPERATOR_VISIBILITY_*``.
      * ``safe_reason_code``               -- closed-set lowercase
                                              snake_case reason
                                              code; deterministically
                                              derived from
                                              ``retry_outcome``.
      * ``redaction_status``               -- closed-set
                                              ``REDACTION_STATUS_*``.

    Excluded by construction:

      * raw exception text
      * raw status messages
      * URLs / private webhook identifiers / API keys / bearer
        tokens / auth headers
      * raw retry-after hint string (only the post-clamp numeric
        ``delay_seconds`` is exposed)
      * any caller-supplied input field that may carry secret-
        like material
    """

    retry_outcome: str
    retry_allowed: bool
    delay_seconds: Optional[float]
    next_attempt_index: Optional[int]
    attempts_remaining: int
    profile_name: str
    terminal_reason_if_exhausted: str
    dispatch_allowed: bool
    session_continuation_status: str
    operator_visibility: str
    safe_reason_code: str
    redaction_status: str


# ---------------------------------------------------------------------------
# Closed-set safe reason codes (lowercased outcome tokens)
# ---------------------------------------------------------------------------


# Stage 28.3b safe reason codes are deterministic, redaction-safe
# snake_case derivations of the retry-outcome tokens. They are
# locked here so downstream readers can pin the set without re-
# deriving it from the retry-outcome tokens.
SAFE_RETRY_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    outcome.lower() for outcome in RETRY_OUTCOME_VALUES
)


def is_safe_retry_reason_code_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3b
    safe-retry-reason-code token."""
    return (
        isinstance(value, str)
        and value in SAFE_RETRY_REASON_CODE_VALUES
    )


# ---------------------------------------------------------------------------
# Re-exports from Stage 28.3a for downstream pinning convenience
# ---------------------------------------------------------------------------


# Re-exported here so Stage 28.3b consumers can pin the
# session-continuation / operator-visibility / redaction-status
# closed-sets without re-importing the Stage 28.3a models module.
STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES: tuple[str, ...] = tuple(
    _SESSION_CONTINUATION_STATUS_VALUES
)


STAGE28_3B_OPERATOR_VISIBILITY_VALUES: tuple[str, ...] = tuple(
    _OPERATOR_VISIBILITY_VALUES
)


STAGE28_3B_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _REDACTION_STATUS_VALUES
)


__all__ = (
    # Version axes.
    "STAGE28_3B_MINOR_VERSION",
    "STAGE28_3B_SCHEMA_VERSION",
    "STAGE28_3B_REDACTION_TOKEN",
    # Retry-outcome constants.
    "RETRY_OUTCOME_ALLOWED",
    "RETRY_OUTCOME_NOT_ALLOWED",
    "RETRY_OUTCOME_EXHAUSTED",
    "RETRY_OUTCOME_SUPPRESSED",
    "RETRY_OUTCOME_FAIL_CLOSED",
    "RETRY_OUTCOME_STOP_SESSION",
    "RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED",
    "RETRY_OUTCOME_NO_RETRY_TERMINAL",
    "RETRY_OUTCOME_VALUES",
    # Retry-profile-name constants.
    "RETRY_PROFILE_NAME_NO_RETRY",
    "RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED",
    "RETRY_PROFILE_NAME_DISCORD_TRANSIENT",
    "RETRY_PROFILE_NAME_PROVIDER_RECONNECT",
    "RETRY_PROFILE_NAME_PRICE_REFRESH",
    "RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE",
    "RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE",
    "RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX",
    "RETRY_PROFILE_NAME_INTERNAL_STOP",
    "RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP",
    "RETRY_PROFILE_NAME_VALUES",
    # Terminal-reason constants.
    "TERMINAL_REASON_NONE",
    "TERMINAL_REASON_PROFILE_EXHAUSTED",
    "TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED",
    "TERMINAL_REASON_RATE_LIMIT_EXHAUSTED",
    "TERMINAL_REASON_SERVER_ERROR_EXHAUSTED",
    "TERMINAL_REASON_NETWORK_EXHAUSTED",
    "TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED",
    "TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED",
    "TERMINAL_REASON_ARTIFACT_WRITE_EXHAUSTED",
    "TERMINAL_REASON_LEDGER_WRITE_EXHAUSTED",
    "TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE",
    "TERMINAL_REASON_SUPPRESSED_DUPLICATE",
    "TERMINAL_REASON_SUPPRESSED_AMBIGUOUS",
    "TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE",
    "TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION",
    "TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED",
    "TERMINAL_REASON_OPERATOR_SHUTDOWN",
    "TERMINAL_REASON_SECRET_REDACTION_VIOLATION",
    "TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN",
    "TERMINAL_REASON_LEDGER_REPLAY_FAILED",
    "TERMINAL_REASON_NO_RETRY_TERMINAL",
    "TERMINAL_REASON_UNKNOWN_FAILURE",
    "TERMINAL_REASON_VALUES",
    # Retry-after caps.
    "RETRY_AFTER_MAX_SECONDS",
    "RETRY_AFTER_MIN_SECONDS",
    "RETRY_AFTER_DEFAULT_SECONDS",
    # Records.
    "RetryProfile",
    "Stage28_3bRetryPolicyInput",
    "Stage28_3bRetryDecision",
    # Re-exported closed-sets.
    "STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES",
    "STAGE28_3B_OPERATOR_VISIBILITY_VALUES",
    "STAGE28_3B_REDACTION_STATUS_VALUES",
    # Safe reason codes.
    "SAFE_RETRY_REASON_CODE_VALUES",
    # Validators.
    "is_retry_outcome_value",
    "is_retry_profile_name_value",
    "is_terminal_reason_value",
    "is_retry_allowed_outcome",
    "is_non_retry_outcome",
    "is_safe_retry_reason_code_value",
    # Builders.
    "build_retry_policy_input",
    # Exceptions.
    "Stage28_3bRetryPolicyError",
    "Stage28_3bInvalidRetryPolicyInputError",
    "Stage28_3bInvalidRetryProfileError",
)
