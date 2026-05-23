"""Stage 28.3a failure classification closed-set vocabularies + records.

Stage 28.3a ships pure, deterministic, redaction-safe failure-
classification primitives for Stage 28 reliability hardening.

The classification primitives map an opaque failure description
(``failure_kind_hint`` + optional domain / status / exception /
state hints) to a stable closed-set output record carrying:

  * the classified ``failure_kind`` (closed-set),
  * the ``domain`` (closed-set),
  * a ``retryable_in_principle`` boolean,
  * the ``recommended_action`` (closed-set; consumed by the future
    Stage 28.3b retry policy),
  * the ``severity`` (closed-set: INFO / WARNING / ERROR /
    CRITICAL),
  * the ``dispatch_safety_status`` (closed-set: DISPATCH_DEFERRED
    / DISPATCH_SUPPRESSED / DISPATCH_FAIL_CLOSED),
  * the ``session_continuation_status`` (closed-set:
    CONTINUE_SESSION / STOP_SESSION),
  * the ``operator_visibility`` (closed-set: LOG_ONLY /
    OPERATOR_NOTICE / OPERATOR_ESCALATE),
  * a ``safe_reason_code`` (closed-set, redaction-safe snake_case
    derived from ``failure_kind``),
  * a ``redaction_status`` (closed-set).

Stage 28.3a is NOT retry policy. Stage 28.3a is the vocabulary +
classifier layer that the Stage 28.3b retry policy will consume.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here. The Stage 28.3a boundary scan pins
    this.
  * No network. No HTTP. No gRPC. No Discord. No file I/O at
    import or call time.
  * No retry. No backoff. No sleep. No clocks. No scheduling.
    Classification does not retry; classification only labels.
  * No raw secret value is ever carried on a classification
    output. Even when the caller supplies a ``raw_message``, the
    classifier never copies it onto the output record; the output
    surface is restricted to closed-set tokens + a closed-set
    ``safe_reason_code``.
  * ``repr()`` / ``str()`` of any classification output is safe to
    log / print / persist; no URL host substring, no API-key
    substring, no bearer-token substring, no Discord webhook
    substring, no raw exception text reaches the output record.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2
production code, does NOT import any network / RPC / messaging /
DB / scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 28.3a version axes
# ---------------------------------------------------------------------------


STAGE28_3A_MINOR_VERSION: str = "28.3a"
STAGE28_3A_SCHEMA_VERSION: str = "stage28_3a_failure_classification_v0"


# ---------------------------------------------------------------------------
# Closed-set: failure kinds
# ---------------------------------------------------------------------------


# Provider domain.
FAILURE_KIND_PROVIDER_DISCONNECTED: str = "PROVIDER_DISCONNECTED"
FAILURE_KIND_PROVIDER_TIMEOUT: str = "PROVIDER_TIMEOUT"
FAILURE_KIND_PROVIDER_RATE_LIMITED: str = "PROVIDER_RATE_LIMITED"
FAILURE_KIND_PROVIDER_AUTH_FAILED: str = "PROVIDER_AUTH_FAILED"
FAILURE_KIND_PROVIDER_MALFORMED_EVENT: str = (
    "PROVIDER_MALFORMED_EVENT"
)

# Price domain.
FAILURE_KIND_PRICE_TIMEOUT: str = "PRICE_TIMEOUT"
FAILURE_KIND_PRICE_STALE: str = "PRICE_STALE"
FAILURE_KIND_PRICE_MISSING: str = "PRICE_MISSING"

# Discord transport domain.
FAILURE_KIND_DISCORD_RATE_LIMITED: str = "DISCORD_RATE_LIMITED"
FAILURE_KIND_DISCORD_SERVER_ERROR: str = "DISCORD_SERVER_ERROR"
FAILURE_KIND_DISCORD_NETWORK_ERROR: str = "DISCORD_NETWORK_ERROR"
FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED: str = (
    "DISCORD_AUTH_OR_WEBHOOK_REFUSED"
)

# Artifact domain.
FAILURE_KIND_ARTIFACT_WRITE_FAILED: str = "ARTIFACT_WRITE_FAILED"
FAILURE_KIND_ARTIFACT_READ_FAILED: str = "ARTIFACT_READ_FAILED"

# Ledger domain.
FAILURE_KIND_LEDGER_WRITE_FAILED: str = "LEDGER_WRITE_FAILED"
FAILURE_KIND_LEDGER_REPLAY_FAILED: str = "LEDGER_REPLAY_FAILED"
FAILURE_KIND_LEDGER_AMBIGUOUS_SEND: str = "LEDGER_AMBIGUOUS_SEND"
FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL: str = (
    "LEDGER_DUPLICATE_TERMINAL"
)

# Generic internal event.
FAILURE_KIND_MALFORMED_EVENT: str = "MALFORMED_EVENT"

# Pair classification domain (Stage 27 suppression cases).
FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED: str = (
    "UNKNOWN_PAIR_SUPPRESSED"
)
FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED: str = (
    "DISAGREE_PAIR_SUPPRESSED"
)
FAILURE_KIND_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"

# Config domain.
FAILURE_KIND_CONFIG_NOT_READY: str = "CONFIG_NOT_READY"
FAILURE_KIND_CONFIG_CONFLICT: str = "CONFIG_CONFLICT"

# Internal safety.
FAILURE_KIND_SECRET_REDACTION_VIOLATION: str = (
    "SECRET_REDACTION_VIOLATION"
)
FAILURE_KIND_RETRY_BUDGET_EXHAUSTED: str = (
    "RETRY_BUDGET_EXHAUSTED"
)
FAILURE_KIND_INTERNAL_INVARIANT_BROKEN: str = (
    "INTERNAL_INVARIANT_BROKEN"
)

# Operator.
FAILURE_KIND_OPERATOR_SHUTDOWN: str = "OPERATOR_SHUTDOWN"

# Unknown / fallback.
FAILURE_KIND_UNKNOWN_FAILURE: str = "UNKNOWN_FAILURE"


FAILURE_KIND_VALUES: tuple[str, ...] = (
    FAILURE_KIND_PROVIDER_DISCONNECTED,
    FAILURE_KIND_PROVIDER_TIMEOUT,
    FAILURE_KIND_PROVIDER_RATE_LIMITED,
    FAILURE_KIND_PROVIDER_AUTH_FAILED,
    FAILURE_KIND_PROVIDER_MALFORMED_EVENT,
    FAILURE_KIND_PRICE_TIMEOUT,
    FAILURE_KIND_PRICE_STALE,
    FAILURE_KIND_PRICE_MISSING,
    FAILURE_KIND_DISCORD_RATE_LIMITED,
    FAILURE_KIND_DISCORD_SERVER_ERROR,
    FAILURE_KIND_DISCORD_NETWORK_ERROR,
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED,
    FAILURE_KIND_ARTIFACT_WRITE_FAILED,
    FAILURE_KIND_ARTIFACT_READ_FAILED,
    FAILURE_KIND_LEDGER_WRITE_FAILED,
    FAILURE_KIND_LEDGER_REPLAY_FAILED,
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND,
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL,
    FAILURE_KIND_MALFORMED_EVENT,
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
    FAILURE_KIND_USDC_OBSERVE_ONLY,
    FAILURE_KIND_CONFIG_NOT_READY,
    FAILURE_KIND_CONFIG_CONFLICT,
    FAILURE_KIND_SECRET_REDACTION_VIOLATION,
    FAILURE_KIND_RETRY_BUDGET_EXHAUSTED,
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN,
    FAILURE_KIND_OPERATOR_SHUTDOWN,
    FAILURE_KIND_UNKNOWN_FAILURE,
)


# ---------------------------------------------------------------------------
# Closed-set: failure domains
# ---------------------------------------------------------------------------


DOMAIN_PROVIDER: str = "provider"
DOMAIN_PRICE: str = "price"
DOMAIN_DISCORD_TRANSPORT: str = "discord_transport"
DOMAIN_ARTIFACT: str = "artifact"
DOMAIN_LEDGER: str = "ledger"
DOMAIN_CONFIG: str = "config"
DOMAIN_PAIR_CLASSIFICATION: str = "pair_classification"
DOMAIN_OPERATOR: str = "operator"
DOMAIN_INTERNAL: str = "internal"


DOMAIN_VALUES: tuple[str, ...] = (
    DOMAIN_PROVIDER,
    DOMAIN_PRICE,
    DOMAIN_DISCORD_TRANSPORT,
    DOMAIN_ARTIFACT,
    DOMAIN_LEDGER,
    DOMAIN_CONFIG,
    DOMAIN_PAIR_CLASSIFICATION,
    DOMAIN_OPERATOR,
    DOMAIN_INTERNAL,
)


# ---------------------------------------------------------------------------
# Closed-set: recommended actions
# ---------------------------------------------------------------------------


# Recommendations Stage 28.3b retry policy will consume. Stage
# 28.3a never applies these; it only labels.
RECOMMENDED_ACTION_RETRY_PENDING: str = "RETRY_PENDING"
RECOMMENDED_ACTION_NO_RETRY_TERMINAL: str = "NO_RETRY_TERMINAL"
RECOMMENDED_ACTION_FAIL_CLOSED: str = "FAIL_CLOSED"
RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED: str = (
    "DUPLICATE_SUPPRESSED"
)
RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED: str = (
    "AMBIGUOUS_SUPPRESSED"
)
RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE: str = (
    "SUPPRESS_NOT_ELIGIBLE"
)
RECOMMENDED_ACTION_OPERATOR_REVIEW: str = "OPERATOR_REVIEW"
RECOMMENDED_ACTION_STOP_SESSION: str = "STOP_SESSION"


RECOMMENDED_ACTION_VALUES: tuple[str, ...] = (
    RECOMMENDED_ACTION_RETRY_PENDING,
    RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
    RECOMMENDED_ACTION_FAIL_CLOSED,
    RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED,
    RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED,
    RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
    RECOMMENDED_ACTION_OPERATOR_REVIEW,
    RECOMMENDED_ACTION_STOP_SESSION,
)


# ---------------------------------------------------------------------------
# Closed-set: severity
# ---------------------------------------------------------------------------


SEVERITY_INFO: str = "INFO"
SEVERITY_WARNING: str = "WARNING"
SEVERITY_ERROR: str = "ERROR"
SEVERITY_CRITICAL: str = "CRITICAL"


SEVERITY_VALUES: tuple[str, ...] = (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ERROR,
    SEVERITY_CRITICAL,
)


# ---------------------------------------------------------------------------
# Closed-set: dispatch safety status
# ---------------------------------------------------------------------------


# A classified failure never produces ``DISPATCH_ALLOWED``: this
# vocabulary is the failure-side dispatch status only.
#   * DISPATCH_DEFERRED      -- retryable in principle; the Stage
#                                28.3b retry policy decides whether
#                                / when to re-attempt.
#   * DISPATCH_SUPPRESSED    -- deliberately suppressed; do not
#                                retry (duplicates, ambiguous
#                                ledger state, pair-suppression
#                                cases, etc.).
#   * DISPATCH_FAIL_CLOSED   -- safety violation or hard-fail
#                                condition; do not retry; escalate
#                                to operator.
DISPATCH_SAFETY_DEFERRED: str = "DISPATCH_DEFERRED"
DISPATCH_SAFETY_SUPPRESSED: str = "DISPATCH_SUPPRESSED"
DISPATCH_SAFETY_FAIL_CLOSED: str = "DISPATCH_FAIL_CLOSED"


DISPATCH_SAFETY_STATUS_VALUES: tuple[str, ...] = (
    DISPATCH_SAFETY_DEFERRED,
    DISPATCH_SAFETY_SUPPRESSED,
    DISPATCH_SAFETY_FAIL_CLOSED,
)


# ---------------------------------------------------------------------------
# Closed-set: session continuation status
# ---------------------------------------------------------------------------


SESSION_CONTINUATION_CONTINUE: str = "CONTINUE_SESSION"
SESSION_CONTINUATION_STOP: str = "STOP_SESSION"


SESSION_CONTINUATION_STATUS_VALUES: tuple[str, ...] = (
    SESSION_CONTINUATION_CONTINUE,
    SESSION_CONTINUATION_STOP,
)


# ---------------------------------------------------------------------------
# Closed-set: operator visibility
# ---------------------------------------------------------------------------


OPERATOR_VISIBILITY_LOG_ONLY: str = "LOG_ONLY"
OPERATOR_VISIBILITY_NOTICE: str = "OPERATOR_NOTICE"
OPERATOR_VISIBILITY_ESCALATE: str = "OPERATOR_ESCALATE"


OPERATOR_VISIBILITY_VALUES: tuple[str, ...] = (
    OPERATOR_VISIBILITY_LOG_ONLY,
    OPERATOR_VISIBILITY_NOTICE,
    OPERATOR_VISIBILITY_ESCALATE,
)


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


REDACTION_STATUS_APPLIED: str = "REDACTION_APPLIED"
REDACTION_STATUS_NOT_APPLICABLE: str = "REDACTION_NOT_APPLICABLE"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_APPLIED,
    REDACTION_STATUS_NOT_APPLICABLE,
)


# ---------------------------------------------------------------------------
# Closed-set: safe reason codes
# ---------------------------------------------------------------------------


# Stage 28.3a safe reason codes are deterministic, redaction-safe
# snake_case derivations of the failure-kind tokens. They are
# locked here so downstream readers can pin the set without
# re-deriving it from the failure-kind tokens.
SAFE_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    kind.lower() for kind in FAILURE_KIND_VALUES
)


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


# Distinctive Stage 28.3a redaction token. Distinct from the Stage
# 27, Stage 28.1, and Stage 28.2 redaction tokens so a leak-scan
# test for one cannot collide with another.
STAGE28_3A_REDACTION_TOKEN: str = "<<STAGE28_3A_REDACTED>>"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def is_failure_kind_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    failure-kind token."""
    return isinstance(value, str) and value in FAILURE_KIND_VALUES


def is_domain_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    failure-domain token."""
    return isinstance(value, str) and value in DOMAIN_VALUES


def is_recommended_action_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    recommended-action token."""
    return (
        isinstance(value, str) and value in RECOMMENDED_ACTION_VALUES
    )


def is_severity_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    severity token."""
    return isinstance(value, str) and value in SEVERITY_VALUES


def is_dispatch_safety_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    dispatch-safety-status token."""
    return (
        isinstance(value, str)
        and value in DISPATCH_SAFETY_STATUS_VALUES
    )


def is_session_continuation_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    session-continuation-status token."""
    return (
        isinstance(value, str)
        and value in SESSION_CONTINUATION_STATUS_VALUES
    )


def is_operator_visibility_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    operator-visibility token."""
    return (
        isinstance(value, str) and value in OPERATOR_VISIBILITY_VALUES
    )


def is_redaction_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    redaction-status token."""
    return (
        isinstance(value, str) and value in REDACTION_STATUS_VALUES
    )


def is_safe_reason_code_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.3a
    safe-reason-code token."""
    return (
        isinstance(value, str) and value in SAFE_REASON_CODE_VALUES
    )


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_3aFailureClassificationError(Exception):
    """Base type for every Stage 28.3a failure-classification error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_3aInvalidFailureInputError(
    Stage28_3aFailureClassificationError
):
    """Raised when a ``Stage28_3aFailureInput`` field fails Stage
    28.3a construction validation.

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.3a invalid failure input: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage28_3aFailureInput
# ---------------------------------------------------------------------------


class Stage28_3aFailureInput(NamedTuple):
    """Immutable Stage 28.3a failure-classification input.

    Closed-set / opaque hint fields:

      * ``failure_kind_hint``    -- closed-set ``FAILURE_KIND_*``
                                    token if the caller already
                                    knows the kind; ``None`` to
                                    request inference from the
                                    other hints.
      * ``domain_hint``          -- closed-set ``DOMAIN_*`` token if
                                    the caller knows the domain;
                                    ``None`` to defer.
      * ``status_code``          -- HTTP-style numeric status code;
                                    used only to disambiguate
                                    Discord transport failures.
      * ``exception_type_name``  -- safe exception class name string
                                    (e.g. ``"TimeoutError"``) --
                                    the class name only, never the
                                    exception instance.
      * ``safe_detail_code``     -- closed-set short caller-supplied
                                    detail code if the caller wants
                                    to pass a sub-kind hint.
      * ``pair_status``          -- closed-set pair-classification
                                    status if the failure originated
                                    in pair classification (e.g.
                                    ``"UNKNOWN"`` / ``"DISAGREE"`` /
                                    ``"USDC_OBSERVE_ONLY"``).
      * ``ledger_state``         -- closed-set Stage 28.2 dedupe
                                    state if the failure originated
                                    in the ledger replay layer.
      * ``config_reason``        -- closed-set config-failure reason
                                    if the failure originated in
                                    Stage 28.1 config readiness.
      * ``artifact_operation``   -- closed-set artifact-op token
                                    (``"WRITE"`` / ``"READ"``) if
                                    the failure originated in an
                                    artifact write / read.
      * ``raw_message``          -- optional raw exception message
                                    string. Accepted for test
                                    fixtures, but NEVER copied to
                                    the classification output --
                                    the classifier drops it.

    The named-tuple shape gives the record built-in immutability,
    structural equality, and a safe ``repr()`` over its declared
    fields.
    """

    failure_kind_hint: Optional[str]
    domain_hint: Optional[str]
    status_code: Optional[int]
    exception_type_name: Optional[str]
    safe_detail_code: Optional[str]
    pair_status: Optional[str]
    ledger_state: Optional[str]
    config_reason: Optional[str]
    artifact_operation: Optional[str]
    raw_message: Optional[str]


def build_failure_input(
    *,
    failure_kind_hint: Optional[str] = None,
    domain_hint: Optional[str] = None,
    status_code: Optional[int] = None,
    exception_type_name: Optional[str] = None,
    safe_detail_code: Optional[str] = None,
    pair_status: Optional[str] = None,
    ledger_state: Optional[str] = None,
    config_reason: Optional[str] = None,
    artifact_operation: Optional[str] = None,
    raw_message: Optional[str] = None,
) -> Stage28_3aFailureInput:
    """Construct an immutable ``Stage28_3aFailureInput`` from
    keyword-only fields.

    Only structural / type validation is performed here. Closed-set
    membership of ``failure_kind_hint`` / ``domain_hint`` is NOT
    enforced at construction; the classifier handles
    ``UNKNOWN_FAILURE`` fallback for unrecognized hints.

    ``status_code`` must be ``None`` or a non-negative ``int``
    (booleans are rejected because ``bool`` is a subclass of
    ``int`` and would otherwise leak through).
    """
    if status_code is not None:
        if isinstance(status_code, bool) or not isinstance(
            status_code, int
        ):
            raise Stage28_3aInvalidFailureInputError(
                field_name="status_code",
                reason="STATUS_CODE_NOT_INT",
            )
        if status_code < 0:
            raise Stage28_3aInvalidFailureInputError(
                field_name="status_code",
                reason="STATUS_CODE_NEGATIVE",
            )
    return Stage28_3aFailureInput(
        failure_kind_hint=failure_kind_hint,
        domain_hint=domain_hint,
        status_code=status_code,
        exception_type_name=exception_type_name,
        safe_detail_code=safe_detail_code,
        pair_status=pair_status,
        ledger_state=ledger_state,
        config_reason=config_reason,
        artifact_operation=artifact_operation,
        raw_message=raw_message,
    )


# ---------------------------------------------------------------------------
# Stage28_3aFailureClassification (output)
# ---------------------------------------------------------------------------


class Stage28_3aFailureClassification(NamedTuple):
    """Immutable Stage 28.3a failure-classification output.

    Closed-set fields:

      * ``failure_kind``                 -- ``FAILURE_KIND_*``
      * ``domain``                       -- ``DOMAIN_*``
      * ``retryable_in_principle``       -- bool
      * ``recommended_action``           -- ``RECOMMENDED_ACTION_*``
      * ``severity``                     -- ``SEVERITY_*``
      * ``dispatch_safety_status``       -- ``DISPATCH_SAFETY_*``
      * ``session_continuation_status``  -- ``SESSION_CONTINUATION_*``
      * ``operator_visibility``          -- ``OPERATOR_VISIBILITY_*``
      * ``safe_reason_code``             -- snake_case closed-set
                                             reason code
      * ``redaction_status``             -- ``REDACTION_STATUS_*``

    Excluded by construction:

      * raw exception text
      * raw status messages
      * URLs / webhook identifiers / API keys / bearer tokens
      * any input field that may carry secret-like material

    The named-tuple shape gives the record built-in immutability,
    structural equality, and a safe ``repr()`` that exposes only
    the closed-set field values.
    """

    failure_kind: str
    domain: str
    retryable_in_principle: bool
    recommended_action: str
    severity: str
    dispatch_safety_status: str
    session_continuation_status: str
    operator_visibility: str
    safe_reason_code: str
    redaction_status: str


__all__ = (
    # Version axes.
    "STAGE28_3A_MINOR_VERSION",
    "STAGE28_3A_SCHEMA_VERSION",
    "STAGE28_3A_REDACTION_TOKEN",
    # Failure-kind constants.
    "FAILURE_KIND_PROVIDER_DISCONNECTED",
    "FAILURE_KIND_PROVIDER_TIMEOUT",
    "FAILURE_KIND_PROVIDER_RATE_LIMITED",
    "FAILURE_KIND_PROVIDER_AUTH_FAILED",
    "FAILURE_KIND_PROVIDER_MALFORMED_EVENT",
    "FAILURE_KIND_PRICE_TIMEOUT",
    "FAILURE_KIND_PRICE_STALE",
    "FAILURE_KIND_PRICE_MISSING",
    "FAILURE_KIND_DISCORD_RATE_LIMITED",
    "FAILURE_KIND_DISCORD_SERVER_ERROR",
    "FAILURE_KIND_DISCORD_NETWORK_ERROR",
    "FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED",
    "FAILURE_KIND_ARTIFACT_WRITE_FAILED",
    "FAILURE_KIND_ARTIFACT_READ_FAILED",
    "FAILURE_KIND_LEDGER_WRITE_FAILED",
    "FAILURE_KIND_LEDGER_REPLAY_FAILED",
    "FAILURE_KIND_LEDGER_AMBIGUOUS_SEND",
    "FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL",
    "FAILURE_KIND_MALFORMED_EVENT",
    "FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED",
    "FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED",
    "FAILURE_KIND_USDC_OBSERVE_ONLY",
    "FAILURE_KIND_CONFIG_NOT_READY",
    "FAILURE_KIND_CONFIG_CONFLICT",
    "FAILURE_KIND_SECRET_REDACTION_VIOLATION",
    "FAILURE_KIND_RETRY_BUDGET_EXHAUSTED",
    "FAILURE_KIND_INTERNAL_INVARIANT_BROKEN",
    "FAILURE_KIND_OPERATOR_SHUTDOWN",
    "FAILURE_KIND_UNKNOWN_FAILURE",
    "FAILURE_KIND_VALUES",
    # Domain constants.
    "DOMAIN_PROVIDER",
    "DOMAIN_PRICE",
    "DOMAIN_DISCORD_TRANSPORT",
    "DOMAIN_ARTIFACT",
    "DOMAIN_LEDGER",
    "DOMAIN_CONFIG",
    "DOMAIN_PAIR_CLASSIFICATION",
    "DOMAIN_OPERATOR",
    "DOMAIN_INTERNAL",
    "DOMAIN_VALUES",
    # Recommended action constants.
    "RECOMMENDED_ACTION_RETRY_PENDING",
    "RECOMMENDED_ACTION_NO_RETRY_TERMINAL",
    "RECOMMENDED_ACTION_FAIL_CLOSED",
    "RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED",
    "RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED",
    "RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE",
    "RECOMMENDED_ACTION_OPERATOR_REVIEW",
    "RECOMMENDED_ACTION_STOP_SESSION",
    "RECOMMENDED_ACTION_VALUES",
    # Severity constants.
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_ERROR",
    "SEVERITY_CRITICAL",
    "SEVERITY_VALUES",
    # Dispatch safety status constants.
    "DISPATCH_SAFETY_DEFERRED",
    "DISPATCH_SAFETY_SUPPRESSED",
    "DISPATCH_SAFETY_FAIL_CLOSED",
    "DISPATCH_SAFETY_STATUS_VALUES",
    # Session continuation status constants.
    "SESSION_CONTINUATION_CONTINUE",
    "SESSION_CONTINUATION_STOP",
    "SESSION_CONTINUATION_STATUS_VALUES",
    # Operator visibility constants.
    "OPERATOR_VISIBILITY_LOG_ONLY",
    "OPERATOR_VISIBILITY_NOTICE",
    "OPERATOR_VISIBILITY_ESCALATE",
    "OPERATOR_VISIBILITY_VALUES",
    # Redaction status constants.
    "REDACTION_STATUS_APPLIED",
    "REDACTION_STATUS_NOT_APPLICABLE",
    "REDACTION_STATUS_VALUES",
    # Safe reason codes.
    "SAFE_REASON_CODE_VALUES",
    # Validators.
    "is_failure_kind_value",
    "is_domain_value",
    "is_recommended_action_value",
    "is_severity_value",
    "is_dispatch_safety_status_value",
    "is_session_continuation_status_value",
    "is_operator_visibility_value",
    "is_redaction_status_value",
    "is_safe_reason_code_value",
    # Exceptions.
    "Stage28_3aFailureClassificationError",
    "Stage28_3aInvalidFailureInputError",
    # Records.
    "Stage28_3aFailureInput",
    "Stage28_3aFailureClassification",
    # Builders.
    "build_failure_input",
)
