"""Stage 28.3a failure-classification pure deterministic classifier.

This module provides the pure deterministic classifier that maps a
``Stage28_3aFailureInput`` to a ``Stage28_3aFailureClassification``
output record over the locked Stage 28.3a closed-set vocabularies.

Classifier contract:

  * Pure: same input -> same output, always. The classifier never
    reads the process environment, never opens a file, never
    contacts the network, never sleeps, never reads a clock,
    never schedules a task.
  * Deterministic: no randomness, no iteration over unordered
    sets in a way that leaks insertion order, no implicit
    dependence on dict ordering.
  * Closed-set output: every output field is drawn from the
    Stage 28.3a closed-set vocabularies declared in
    ``failure_classification_models``.
  * Redaction-safe: the input's ``raw_message`` field is accepted
    for test fixtures (callers may pass it through from a caught
    exception) but is NEVER copied to the classification output.
    The output exposes only closed-set tokens.

Classification path:

  1. If ``failure_kind_hint`` is set AND is a closed-set
     ``FAILURE_KIND_*`` value, the classifier uses it directly.
  2. Otherwise the classifier runs a deterministic inference pass
     over the other hint fields (pair / ledger / artifact / config
     / Discord transport / provider / price). Inference rules are
     evaluated in a locked priority order; the first matching rule
     wins.
  3. If no rule matches, the classifier returns the
     ``UNKNOWN_FAILURE`` classification with a safe fallback
     posture (not retryable in principle, fail-closed dispatch,
     continue-session, operator-escalate).

What the classifier does NOT do (each of these belongs to a later
Stage 28 substage and is explicitly out of Stage 28.3a scope):

  * No retry / backoff (Stage 28.3b).
  * No audited HTTP / Discord transport (Stage 28.4).
  * No heartbeat / health snapshot / CLI status (Stage 28.5).
  * No bounded private session runner (Stage 28.6).
  * No longer-session smoke harness / live smoke (Stage 28.7).
  * No Stage 29 enforcement / approval / activation semantics.
  * No public routing / subscriber routing / paid-tier routing.
  * No X / social / Telegram.
  * No automated trading / wallet / signer logic / position
    sizing / trade execution.

This module imports only stdlib (``typing``) plus the Stage 28.3a
models module. It does NOT import Stage 21-27 production code,
does NOT import Stage 28.1 / 28.2 production code, does NOT
import any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional

from PHX2.stage28.failure_classification_models import (
    DISPATCH_SAFETY_DEFERRED,
    DISPATCH_SAFETY_FAIL_CLOSED,
    DISPATCH_SAFETY_SUPPRESSED,
    DOMAIN_ARTIFACT,
    DOMAIN_CONFIG,
    DOMAIN_DISCORD_TRANSPORT,
    DOMAIN_INTERNAL,
    DOMAIN_LEDGER,
    DOMAIN_OPERATOR,
    DOMAIN_PAIR_CLASSIFICATION,
    DOMAIN_PRICE,
    DOMAIN_PROVIDER,
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
    OPERATOR_VISIBILITY_LOG_ONLY,
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
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Stage28_3aFailureClassification,
    Stage28_3aFailureInput,
    is_failure_kind_value,
)


# ---------------------------------------------------------------------------
# Per-kind classification row
# ---------------------------------------------------------------------------


class _ClassificationRow(NamedTuple):
    """Immutable row in the locked per-failure-kind mapping table.

    A row's fields populate every non-``failure_kind`` field on the
    classification output. ``failure_kind`` is keyed by the
    mapping; ``safe_reason_code`` is derived deterministically from
    the failure-kind token (lowercased); ``redaction_status`` is
    always ``REDACTION_APPLIED`` because the classifier always
    enforces its drop-the-raw-message discipline.
    """

    domain: str
    retryable_in_principle: bool
    recommended_action: str
    severity: str
    dispatch_safety_status: str
    session_continuation_status: str
    operator_visibility: str


# ---------------------------------------------------------------------------
# Locked per-failure-kind classification table
# ---------------------------------------------------------------------------


# Every closed-set failure-kind token MUST appear as a key here.
# The Stage 28.3a model tests pin coverage so a future renamed or
# added kind is caught immediately.
_FAILURE_KIND_TO_ROW: Mapping[str, _ClassificationRow] = {
    # Provider domain -----------------------------------------------------
    FAILURE_KIND_PROVIDER_DISCONNECTED: _ClassificationRow(
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_PROVIDER_TIMEOUT: _ClassificationRow(
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_PROVIDER_RATE_LIMITED: _ClassificationRow(
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_PROVIDER_AUTH_FAILED: _ClassificationRow(
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_OPERATOR_REVIEW,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    FAILURE_KIND_PROVIDER_MALFORMED_EVENT: _ClassificationRow(
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    # Price domain --------------------------------------------------------
    FAILURE_KIND_PRICE_TIMEOUT: _ClassificationRow(
        domain=DOMAIN_PRICE,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_PRICE_STALE: _ClassificationRow(
        domain=DOMAIN_PRICE,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_PRICE_MISSING: _ClassificationRow(
        domain=DOMAIN_PRICE,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    # Discord transport domain --------------------------------------------
    FAILURE_KIND_DISCORD_RATE_LIMITED: _ClassificationRow(
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_DISCORD_SERVER_ERROR: _ClassificationRow(
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_DISCORD_NETWORK_ERROR: _ClassificationRow(
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED: _ClassificationRow(
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_OPERATOR_REVIEW,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    # Artifact domain -----------------------------------------------------
    FAILURE_KIND_ARTIFACT_WRITE_FAILED: _ClassificationRow(
        domain=DOMAIN_ARTIFACT,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_ARTIFACT_READ_FAILED: _ClassificationRow(
        domain=DOMAIN_ARTIFACT,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    # Ledger domain -------------------------------------------------------
    FAILURE_KIND_LEDGER_WRITE_FAILED: _ClassificationRow(
        domain=DOMAIN_LEDGER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_LEDGER_REPLAY_FAILED: _ClassificationRow(
        domain=DOMAIN_LEDGER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND: _ClassificationRow(
        domain=DOMAIN_LEDGER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL: _ClassificationRow(
        domain=DOMAIN_LEDGER,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED,
        severity=SEVERITY_INFO,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_LOG_ONLY,
    ),
    # Internal / event ----------------------------------------------------
    FAILURE_KIND_MALFORMED_EVENT: _ClassificationRow(
        domain=DOMAIN_INTERNAL,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    # Pair classification domain (Stage 27 suppression cases) -------------
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED: _ClassificationRow(
        domain=DOMAIN_PAIR_CLASSIFICATION,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
        severity=SEVERITY_INFO,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_LOG_ONLY,
    ),
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED: _ClassificationRow(
        domain=DOMAIN_PAIR_CLASSIFICATION,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
        severity=SEVERITY_INFO,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_LOG_ONLY,
    ),
    FAILURE_KIND_USDC_OBSERVE_ONLY: _ClassificationRow(
        domain=DOMAIN_PAIR_CLASSIFICATION,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
        severity=SEVERITY_INFO,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_LOG_ONLY,
    ),
    # Config domain -------------------------------------------------------
    FAILURE_KIND_CONFIG_NOT_READY: _ClassificationRow(
        domain=DOMAIN_CONFIG,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_OPERATOR_REVIEW,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    FAILURE_KIND_CONFIG_CONFLICT: _ClassificationRow(
        domain=DOMAIN_CONFIG,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_OPERATOR_REVIEW,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    # Internal safety -----------------------------------------------------
    FAILURE_KIND_SECRET_REDACTION_VIOLATION: _ClassificationRow(
        domain=DOMAIN_INTERNAL,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_CRITICAL,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    FAILURE_KIND_RETRY_BUDGET_EXHAUSTED: _ClassificationRow(
        domain=DOMAIN_INTERNAL,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    ),
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN: _ClassificationRow(
        domain=DOMAIN_INTERNAL,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_FAIL_CLOSED,
        severity=SEVERITY_CRITICAL,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
    # Operator ------------------------------------------------------------
    FAILURE_KIND_OPERATOR_SHUTDOWN: _ClassificationRow(
        domain=DOMAIN_OPERATOR,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_STOP_SESSION,
        severity=SEVERITY_INFO,
        dispatch_safety_status=DISPATCH_SAFETY_SUPPRESSED,
        session_continuation_status=SESSION_CONTINUATION_STOP,
        operator_visibility=OPERATOR_VISIBILITY_LOG_ONLY,
    ),
    # Unknown / fallback --------------------------------------------------
    FAILURE_KIND_UNKNOWN_FAILURE: _ClassificationRow(
        domain=DOMAIN_INTERNAL,
        retryable_in_principle=False,
        recommended_action=RECOMMENDED_ACTION_OPERATOR_REVIEW,
        severity=SEVERITY_ERROR,
        dispatch_safety_status=DISPATCH_SAFETY_FAIL_CLOSED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_ESCALATE,
    ),
}


# ---------------------------------------------------------------------------
# Inference vocabularies (closed-set)
# ---------------------------------------------------------------------------


# Pair-status tokens (mirror Stage 27 pair classification). Kept
# narrow on purpose; the Stage 27 classifier is the authoritative
# source and the Stage 28.3a classifier does not redefine it.
_PAIR_STATUS_UNKNOWN: str = "UNKNOWN"
_PAIR_STATUS_DISAGREE: str = "DISAGREE"
_PAIR_STATUS_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"


# Stage 28.2 dedupe-state tokens used for ledger-state inference.
# Re-declared as literals here so the classifier does not need to
# import Stage 28.2 production code (preserving Stage 28.3a's
# clean stage-independence at the boundary).
_LEDGER_STATE_DISPATCHED_AMBIGUOUS: str = "DISPATCHED_AMBIGUOUS"
_LEDGER_STATE_DISPATCHED_OK: str = "DISPATCHED_OK"
_LEDGER_STATE_DISPATCHED_FAILED: str = "DISPATCHED_FAILED"
_LEDGER_STATE_REFUSED_PRE_SEND: str = "REFUSED_PRE_SEND"
_LEDGER_TERMINAL_STATES: tuple[str, ...] = (
    _LEDGER_STATE_DISPATCHED_OK,
    _LEDGER_STATE_DISPATCHED_FAILED,
    _LEDGER_STATE_REFUSED_PRE_SEND,
)


# Stage 28.2 ledger-error operation tokens.
_LEDGER_OPERATION_REPLAY: str = "REPLAY_FAILED"
_LEDGER_OPERATION_WRITE: str = "WRITE_FAILED"


# Artifact-operation tokens.
_ARTIFACT_OPERATION_WRITE: str = "WRITE"
_ARTIFACT_OPERATION_WRITE_FAILED: str = "WRITE_FAILED"
_ARTIFACT_OPERATION_READ: str = "READ"
_ARTIFACT_OPERATION_READ_FAILED: str = "READ_FAILED"
_ARTIFACT_WRITE_TOKENS: tuple[str, ...] = (
    _ARTIFACT_OPERATION_WRITE,
    _ARTIFACT_OPERATION_WRITE_FAILED,
)
_ARTIFACT_READ_TOKENS: tuple[str, ...] = (
    _ARTIFACT_OPERATION_READ,
    _ARTIFACT_OPERATION_READ_FAILED,
)


# Config-reason tokens. The Stage 28.1 readiness layer is the
# authoritative source for config-failure reasons; here we use a
# narrow closed-set hint vocabulary.
_CONFIG_REASON_CONFLICT: str = "CONFLICT"
_CONFIG_REASON_NOT_READY: str = "NOT_READY"


# Discord-transport status-code partitions.
_DISCORD_RATE_LIMITED_STATUS_CODE: int = 429
_DISCORD_AUTH_OR_REFUSED_STATUS_CODES: frozenset[int] = frozenset(
    {401, 403, 404}
)


# Provider status-code partitions.
_PROVIDER_AUTH_FAILED_STATUS_CODES: frozenset[int] = frozenset(
    {401, 403}
)
_PROVIDER_RATE_LIMITED_STATUS_CODE: int = 429


# Network-style exception class names that imply a transport-level
# network failure rather than an application-level error. Kept
# narrow and exhaustive; classifier never imports or instantiates
# any of these exception types.
_NETWORK_EXCEPTION_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "OSError",
        "TimeoutError",
    }
)


# Provider-disconnect-style exception class names.
_PROVIDER_DISCONNECT_EXCEPTION_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "EOFError",
    }
)


# Timeout-style exception class names.
_TIMEOUT_EXCEPTION_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "TimeoutError",
        "asyncio.TimeoutError",
        "concurrent.futures.TimeoutError",
    }
)


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------


def _is_discord_server_error_status(status_code: Optional[int]) -> bool:
    return (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 500 <= status_code < 600
    )


def _infer_failure_kind(failure_input: Stage28_3aFailureInput) -> str:
    """Return the closed-set failure-kind token implied by the
    hints in ``failure_input``.

    Inference order is locked (first matching rule wins):

      1. ``failure_kind_hint`` is itself a closed-set kind.
      2. ``pair_status`` matches a Stage 27 suppression token.
      3. ``ledger_state`` matches a Stage 28.2 dedupe terminal /
         ambiguous token (or ``domain_hint == "ledger"`` plus a
         ledger operation hint).
      4. ``artifact_operation`` matches a closed-set artifact-op
         token.
      5. ``config_reason`` matches a closed-set config reason.
      6. ``domain_hint == "discord_transport"`` plus status-code /
         exception-type disambiguation.
      7. ``domain_hint == "provider"`` plus status-code /
         exception-type disambiguation.
      8. ``domain_hint == "price"`` plus exception-type
         disambiguation.
      9. Fall through -> ``UNKNOWN_FAILURE``.
    """
    # 1. Caller-supplied closed-set kind wins.
    hint = failure_input.failure_kind_hint
    if is_failure_kind_value(hint):
        # ``hint`` is known to be a str at this point because
        # ``is_failure_kind_value`` checks ``isinstance(value, str)``.
        return str(hint)

    # 2. Pair-classification suppression cases.
    pair_status = failure_input.pair_status
    if pair_status == _PAIR_STATUS_UNKNOWN:
        return FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED
    if pair_status == _PAIR_STATUS_DISAGREE:
        return FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED
    if pair_status == _PAIR_STATUS_USDC_OBSERVE_ONLY:
        return FAILURE_KIND_USDC_OBSERVE_ONLY

    # 3. Ledger-layer cases.
    ledger_state = failure_input.ledger_state
    if ledger_state == _LEDGER_STATE_DISPATCHED_AMBIGUOUS:
        return FAILURE_KIND_LEDGER_AMBIGUOUS_SEND
    if (
        isinstance(ledger_state, str)
        and ledger_state in _LEDGER_TERMINAL_STATES
    ):
        return FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL
    if failure_input.domain_hint == DOMAIN_LEDGER:
        if ledger_state == _LEDGER_OPERATION_REPLAY:
            return FAILURE_KIND_LEDGER_REPLAY_FAILED
        if ledger_state == _LEDGER_OPERATION_WRITE:
            return FAILURE_KIND_LEDGER_WRITE_FAILED

    # 4. Artifact cases.
    artifact_operation = failure_input.artifact_operation
    if (
        isinstance(artifact_operation, str)
        and artifact_operation in _ARTIFACT_WRITE_TOKENS
    ):
        return FAILURE_KIND_ARTIFACT_WRITE_FAILED
    if (
        isinstance(artifact_operation, str)
        and artifact_operation in _ARTIFACT_READ_TOKENS
    ):
        return FAILURE_KIND_ARTIFACT_READ_FAILED

    # 5. Config cases.
    config_reason = failure_input.config_reason
    if config_reason == _CONFIG_REASON_CONFLICT:
        return FAILURE_KIND_CONFIG_CONFLICT
    if config_reason == _CONFIG_REASON_NOT_READY:
        return FAILURE_KIND_CONFIG_NOT_READY

    # 6. Discord transport cases.
    domain_hint = failure_input.domain_hint
    status_code = failure_input.status_code
    exception_type_name = failure_input.exception_type_name
    if domain_hint == DOMAIN_DISCORD_TRANSPORT:
        if status_code == _DISCORD_RATE_LIMITED_STATUS_CODE:
            return FAILURE_KIND_DISCORD_RATE_LIMITED
        if _is_discord_server_error_status(status_code):
            return FAILURE_KIND_DISCORD_SERVER_ERROR
        if (
            isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and status_code in _DISCORD_AUTH_OR_REFUSED_STATUS_CODES
        ):
            return FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED
        if (
            isinstance(exception_type_name, str)
            and exception_type_name in _NETWORK_EXCEPTION_TYPE_NAMES
        ):
            return FAILURE_KIND_DISCORD_NETWORK_ERROR

    # 7. Provider cases.
    if domain_hint == DOMAIN_PROVIDER:
        if (
            isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and status_code in _PROVIDER_AUTH_FAILED_STATUS_CODES
        ):
            return FAILURE_KIND_PROVIDER_AUTH_FAILED
        if status_code == _PROVIDER_RATE_LIMITED_STATUS_CODE:
            return FAILURE_KIND_PROVIDER_RATE_LIMITED
        if (
            isinstance(exception_type_name, str)
            and exception_type_name in _TIMEOUT_EXCEPTION_TYPE_NAMES
        ):
            return FAILURE_KIND_PROVIDER_TIMEOUT
        if (
            isinstance(exception_type_name, str)
            and exception_type_name
            in _PROVIDER_DISCONNECT_EXCEPTION_TYPE_NAMES
        ):
            return FAILURE_KIND_PROVIDER_DISCONNECTED

    # 8. Price cases.
    if domain_hint == DOMAIN_PRICE:
        if (
            isinstance(exception_type_name, str)
            and exception_type_name in _TIMEOUT_EXCEPTION_TYPE_NAMES
        ):
            return FAILURE_KIND_PRICE_TIMEOUT

    # 9. Fall through.
    return FAILURE_KIND_UNKNOWN_FAILURE


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------


def classify_failure(
    failure_input: Stage28_3aFailureInput,
) -> Stage28_3aFailureClassification:
    """Classify a Stage 28.3a failure input into the locked closed-
    set ``Stage28_3aFailureClassification`` output record.

    Pure: same input -> same output. No env, no I/O, no network,
    no clocks, no sleeps. Raw exception text in
    ``failure_input.raw_message`` is dropped and never appears on
    the output record.
    """
    kind = _infer_failure_kind(failure_input)
    row = _FAILURE_KIND_TO_ROW[kind]
    safe_reason_code = kind.lower()
    return Stage28_3aFailureClassification(
        failure_kind=kind,
        domain=row.domain,
        retryable_in_principle=row.retryable_in_principle,
        recommended_action=row.recommended_action,
        severity=row.severity,
        dispatch_safety_status=row.dispatch_safety_status,
        session_continuation_status=row.session_continuation_status,
        operator_visibility=row.operator_visibility,
        safe_reason_code=safe_reason_code,
        redaction_status=REDACTION_STATUS_APPLIED,
    )


# ---------------------------------------------------------------------------
# Stage 28.3a coverage sanity (table covers every closed-set kind)
# ---------------------------------------------------------------------------


# Asserted at import time so a future kind added to the closed
# set without a matching row in the table fails fast. The assertion
# is a top-level Assert (not a Call), so the boundary scan's no-
# top-level-Call rule is preserved.
assert set(_FAILURE_KIND_TO_ROW.keys()) == set(FAILURE_KIND_VALUES), (
    "Stage 28.3a classifier row table must cover every closed-set "
    "failure-kind value"
)


__all__ = (
    "classify_failure",
)
