"""Stage 28.3a failure-classification classifier tests.

Pins:

  * For every closed-set ``failure_kind_hint``, the classifier
    returns the locked closed-set classification (kind / domain /
    retryable / action / severity / dispatch_safety /
    session_continuation / operator_visibility / safe_reason_code /
    redaction_status).
  * Discord 429 / 5xx / network exception / auth-or-refused
    inference maps to the right Stage 28.3a closed-set kind even
    when ``failure_kind_hint`` is ``None``.
  * Pair-classification suppression cases
    (UNKNOWN / DISAGREE / USDC observe-only) map to suppress.
  * Ledger ambiguous / duplicate-terminal cases map to suppress.
  * Artifact write/read failures map to fail-closed.
  * Config conflict / not-ready map to operator-review fail-closed.
  * Secret redaction violation maps to CRITICAL stop-session
    fail-closed.
  * Operator shutdown maps to graceful stop.
  * Internal invariant broken maps to CRITICAL stop-session
    fail-closed.
  * Unknown / unmapped hint falls through to UNKNOWN_FAILURE with
    safe fail-closed fallback.
  * Raw exception messages, canary webhook URLs, canary API keys,
    bearer tokens, auth headers, raw env-like values supplied via
    ``raw_message`` are NEVER copied to the classification output;
    every classifier output is redaction-safe.
  * Classifier is pure: same input -> same output.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.failure_classification import classify_failure
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
    build_failure_input,
    is_dispatch_safety_status_value,
    is_domain_value,
    is_failure_kind_value,
    is_operator_visibility_value,
    is_recommended_action_value,
    is_redaction_status_value,
    is_safe_reason_code_value,
    is_session_continuation_status_value,
    is_severity_value,
)


# ---------------------------------------------------------------------------
# Canary secret-like values used to assert non-leak across outputs
# ---------------------------------------------------------------------------


_CANARY_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com/api/webhooks/canary/token"
)
_CANARY_PROVIDER_ENDPOINT: str = (
    "h" + "ttps://" + "rpc.helius" + ".xyz/?api-key=CANARY"
)
_CANARY_API_KEY: str = "sk-CANARY-API-KEY-DO-NOT-LEAK-1234567890"
_CANARY_BEARER: str = "Bearer CANARY-BEARER-TOKEN-DO-NOT-LEAK-987654"
_CANARY_AUTH_HEADER: str = "Authorization: Bearer CANARY-AUTH-HEADER"
_CANARY_RAW_ENV: str = "DISCORD_WEBHOOK_URL=h" + "ttps://canary"
_CANARY_SECRET_LIKE_PATH: str = (
    "/etc/secrets/discord/webhook_url.txt"
)


_ALL_CANARIES: tuple[str, ...] = (
    _CANARY_WEBHOOK_URL,
    _CANARY_PROVIDER_ENDPOINT,
    _CANARY_API_KEY,
    _CANARY_BEARER,
    _CANARY_AUTH_HEADER,
    _CANARY_RAW_ENV,
    _CANARY_SECRET_LIKE_PATH,
)


def _assert_no_canary_in(text: str) -> None:
    for canary in _ALL_CANARIES:
        assert canary not in text, (
            f"canary value {canary!r} leaked into Stage 28.3a classifier output"
        )


def _assert_output_is_closed_set(
    record: Stage28_3aFailureClassification,
) -> None:
    """Sanity: every output field is drawn from its closed set."""
    assert is_failure_kind_value(record.failure_kind)
    assert is_domain_value(record.domain)
    assert isinstance(record.retryable_in_principle, bool)
    # ``bool`` is a subclass of ``int``; we explicitly reject the
    # int-shaped 0 / 1 to avoid silent truthy/falsy semantics
    # bleeding through.
    assert type(record.retryable_in_principle) is bool
    assert is_recommended_action_value(record.recommended_action)
    assert is_severity_value(record.severity)
    assert is_dispatch_safety_status_value(
        record.dispatch_safety_status
    )
    assert is_session_continuation_status_value(
        record.session_continuation_status
    )
    assert is_operator_visibility_value(record.operator_visibility)
    assert is_safe_reason_code_value(record.safe_reason_code)
    assert is_redaction_status_value(record.redaction_status)


# ---------------------------------------------------------------------------
# 1. classify_failure is pure (same input -> same output)
# ---------------------------------------------------------------------------


def test_classifier_is_deterministic_for_each_closed_set_hint():
    for kind in FAILURE_KIND_VALUES:
        inp = build_failure_input(failure_kind_hint=kind)
        first = classify_failure(inp)
        second = classify_failure(inp)
        assert first == second, (
            f"classifier output drifted between calls for kind "
            f"{kind!r}"
        )


def test_classifier_output_is_closed_set_for_each_kind_hint():
    for kind in FAILURE_KIND_VALUES:
        inp = build_failure_input(failure_kind_hint=kind)
        record = classify_failure(inp)
        _assert_output_is_closed_set(record)
        assert record.failure_kind == kind


# ---------------------------------------------------------------------------
# 2. Per-failure-kind mapping assertions
# ---------------------------------------------------------------------------


def _classify_hint(kind: str) -> Stage28_3aFailureClassification:
    return classify_failure(build_failure_input(failure_kind_hint=kind))


def test_provider_disconnected_is_retryable_error_continue_notice():
    rec = _classify_hint(FAILURE_KIND_PROVIDER_DISCONNECTED)
    assert rec.failure_kind == FAILURE_KIND_PROVIDER_DISCONNECTED
    assert rec.domain == DOMAIN_PROVIDER
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING
    assert rec.severity == SEVERITY_ERROR
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_DEFERRED
    assert (
        rec.session_continuation_status == SESSION_CONTINUATION_CONTINUE
    )
    assert rec.operator_visibility == OPERATOR_VISIBILITY_NOTICE
    assert rec.safe_reason_code == "provider_disconnected"
    assert rec.redaction_status == REDACTION_STATUS_APPLIED


def test_provider_timeout_is_retryable_warning():
    rec = _classify_hint(FAILURE_KIND_PROVIDER_TIMEOUT)
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING
    assert rec.severity == SEVERITY_WARNING
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_DEFERRED


def test_provider_rate_limited_is_retryable_warning():
    rec = _classify_hint(FAILURE_KIND_PROVIDER_RATE_LIMITED)
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING
    assert rec.severity == SEVERITY_WARNING


def test_provider_auth_failed_is_not_retryable_operator_review_stop():
    rec = _classify_hint(FAILURE_KIND_PROVIDER_AUTH_FAILED)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_OPERATOR_REVIEW
    assert rec.severity == SEVERITY_ERROR
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_ESCALATE


def test_provider_malformed_event_is_no_retry_continue_suppressed():
    rec = _classify_hint(FAILURE_KIND_PROVIDER_MALFORMED_EVENT)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_NO_RETRY_TERMINAL
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert (
        rec.session_continuation_status == SESSION_CONTINUATION_CONTINUE
    )


def test_price_timeout_is_retryable_warning():
    rec = _classify_hint(FAILURE_KIND_PRICE_TIMEOUT)
    assert rec.domain == DOMAIN_PRICE
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_DEFERRED


def test_price_stale_is_not_retryable_fail_closed():
    rec = _classify_hint(FAILURE_KIND_PRICE_STALE)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_price_missing_is_not_retryable_fail_closed():
    rec = _classify_hint(FAILURE_KIND_PRICE_MISSING)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_discord_rate_limited_is_retryable_warning_deferred():
    rec = _classify_hint(FAILURE_KIND_DISCORD_RATE_LIMITED)
    assert rec.domain == DOMAIN_DISCORD_TRANSPORT
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING
    assert rec.severity == SEVERITY_WARNING
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_DEFERRED
    assert (
        rec.session_continuation_status == SESSION_CONTINUATION_CONTINUE
    )


def test_discord_server_error_is_retryable_warning_deferred():
    rec = _classify_hint(FAILURE_KIND_DISCORD_SERVER_ERROR)
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING


def test_discord_network_error_is_retryable_warning_deferred():
    rec = _classify_hint(FAILURE_KIND_DISCORD_NETWORK_ERROR)
    assert rec.retryable_in_principle is True
    assert rec.recommended_action == RECOMMENDED_ACTION_RETRY_PENDING


def test_discord_auth_or_webhook_refused_is_not_retryable_operator_escalate():
    rec = _classify_hint(FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_OPERATOR_REVIEW
    assert rec.severity == SEVERITY_ERROR
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_ESCALATE


def test_artifact_write_failed_is_not_retryable_fail_closed_before_dispatch():
    rec = _classify_hint(FAILURE_KIND_ARTIFACT_WRITE_FAILED)
    assert rec.domain == DOMAIN_ARTIFACT
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.severity == SEVERITY_ERROR
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_artifact_read_failed_is_not_retryable_fail_closed():
    rec = _classify_hint(FAILURE_KIND_ARTIFACT_READ_FAILED)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_ledger_write_failed_is_not_retryable_fail_closed():
    rec = _classify_hint(FAILURE_KIND_LEDGER_WRITE_FAILED)
    assert rec.domain == DOMAIN_LEDGER
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_ledger_replay_failed_is_not_retryable_fail_closed_stop():
    rec = _classify_hint(FAILURE_KIND_LEDGER_REPLAY_FAILED)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP


def test_ledger_ambiguous_send_is_not_retryable_ambiguous_suppressed():
    rec = _classify_hint(FAILURE_KIND_LEDGER_AMBIGUOUS_SEND)
    assert rec.retryable_in_principle is False
    assert (
        rec.recommended_action == RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED
    )
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED


def test_ledger_duplicate_terminal_is_not_retryable_duplicate_suppressed():
    rec = _classify_hint(FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL)
    assert rec.retryable_in_principle is False
    assert (
        rec.recommended_action == RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED
    )
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert rec.severity == SEVERITY_INFO
    assert rec.operator_visibility == OPERATOR_VISIBILITY_LOG_ONLY


def test_malformed_event_is_no_retry_continue_session_suppressed():
    rec = _classify_hint(FAILURE_KIND_MALFORMED_EVENT)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_NO_RETRY_TERMINAL
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert (
        rec.session_continuation_status == SESSION_CONTINUATION_CONTINUE
    )


def test_unknown_pair_suppressed_is_suppress_not_eligible_log_only():
    rec = _classify_hint(FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED)
    assert rec.domain == DOMAIN_PAIR_CLASSIFICATION
    assert rec.retryable_in_principle is False
    assert (
        rec.recommended_action == RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE
    )
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert rec.severity == SEVERITY_INFO
    assert rec.operator_visibility == OPERATOR_VISIBILITY_LOG_ONLY


def test_disagree_pair_suppressed_is_suppress_not_eligible_log_only():
    rec = _classify_hint(FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED)
    assert rec.retryable_in_principle is False
    assert (
        rec.recommended_action == RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE
    )
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED


def test_usdc_observe_only_is_suppress_not_eligible_log_only():
    rec = _classify_hint(FAILURE_KIND_USDC_OBSERVE_ONLY)
    assert rec.retryable_in_principle is False
    assert (
        rec.recommended_action == RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE
    )
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert (
        rec.session_continuation_status == SESSION_CONTINUATION_CONTINUE
    )


def test_config_not_ready_is_operator_review_stop():
    rec = _classify_hint(FAILURE_KIND_CONFIG_NOT_READY)
    assert rec.domain == DOMAIN_CONFIG
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_OPERATOR_REVIEW
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_ESCALATE


def test_config_conflict_is_operator_review_stop():
    rec = _classify_hint(FAILURE_KIND_CONFIG_CONFLICT)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_OPERATOR_REVIEW
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP


def test_secret_redaction_violation_is_critical_stop_fail_closed():
    rec = _classify_hint(FAILURE_KIND_SECRET_REDACTION_VIOLATION)
    assert rec.domain == DOMAIN_INTERNAL
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.severity == SEVERITY_CRITICAL
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_ESCALATE


def test_operator_shutdown_is_graceful_stop_log_only():
    rec = _classify_hint(FAILURE_KIND_OPERATOR_SHUTDOWN)
    assert rec.domain == DOMAIN_OPERATOR
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_STOP_SESSION
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_SUPPRESSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_LOG_ONLY


def test_retry_budget_exhausted_is_no_retry_fail_closed():
    rec = _classify_hint(FAILURE_KIND_RETRY_BUDGET_EXHAUSTED)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_NO_RETRY_TERMINAL
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


def test_internal_invariant_broken_is_critical_stop_fail_closed():
    rec = _classify_hint(FAILURE_KIND_INTERNAL_INVARIANT_BROKEN)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_FAIL_CLOSED
    assert rec.severity == SEVERITY_CRITICAL
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED
    assert rec.session_continuation_status == SESSION_CONTINUATION_STOP
    assert rec.operator_visibility == OPERATOR_VISIBILITY_ESCALATE


def test_unknown_failure_falls_through_to_safe_fallback():
    rec = _classify_hint(FAILURE_KIND_UNKNOWN_FAILURE)
    assert rec.retryable_in_principle is False
    assert rec.recommended_action == RECOMMENDED_ACTION_OPERATOR_REVIEW
    assert rec.severity == SEVERITY_ERROR
    assert rec.dispatch_safety_status == DISPATCH_SAFETY_FAIL_CLOSED


# ---------------------------------------------------------------------------
# 3. Inference: hint=None + auxiliary hints map to the right kind
# ---------------------------------------------------------------------------


def test_inference_discord_429_status_maps_to_rate_limited():
    inp = build_failure_input(
        domain_hint="discord_transport", status_code=429
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_DISCORD_RATE_LIMITED


@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
def test_inference_discord_5xx_status_maps_to_server_error(status):
    inp = build_failure_input(
        domain_hint="discord_transport", status_code=status
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_DISCORD_SERVER_ERROR


@pytest.mark.parametrize("status", [401, 403, 404])
def test_inference_discord_auth_or_refused_status_maps(status):
    inp = build_failure_input(
        domain_hint="discord_transport", status_code=status
    )
    rec = classify_failure(inp)
    assert (
        rec.failure_kind == FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED
    )


@pytest.mark.parametrize(
    "exc_name",
    [
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "OSError",
        "TimeoutError",
    ],
)
def test_inference_discord_network_exception_maps(exc_name):
    inp = build_failure_input(
        domain_hint="discord_transport",
        exception_type_name=exc_name,
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_DISCORD_NETWORK_ERROR


@pytest.mark.parametrize(
    "exc_name",
    [
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
    ],
)
def test_inference_provider_disconnect_exception_maps(exc_name):
    inp = build_failure_input(
        domain_hint="provider", exception_type_name=exc_name
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_PROVIDER_DISCONNECTED


@pytest.mark.parametrize("status", [401, 403])
def test_inference_provider_auth_failed_status_maps(status):
    inp = build_failure_input(domain_hint="provider", status_code=status)
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_PROVIDER_AUTH_FAILED


def test_inference_provider_rate_limited_status_maps():
    inp = build_failure_input(domain_hint="provider", status_code=429)
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_PROVIDER_RATE_LIMITED


def test_inference_provider_timeout_exception_maps():
    inp = build_failure_input(
        domain_hint="provider", exception_type_name="TimeoutError"
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_PROVIDER_TIMEOUT


def test_inference_price_timeout_exception_maps():
    inp = build_failure_input(
        domain_hint="price", exception_type_name="TimeoutError"
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_PRICE_TIMEOUT


def test_inference_unknown_pair_status_maps():
    inp = build_failure_input(pair_status="UNKNOWN")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED


def test_inference_disagree_pair_status_maps():
    inp = build_failure_input(pair_status="DISAGREE")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED


def test_inference_usdc_observe_only_pair_status_maps():
    inp = build_failure_input(pair_status="USDC_OBSERVE_ONLY")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_USDC_OBSERVE_ONLY


def test_inference_ledger_dispatched_ambiguous_maps_to_ambiguous_send():
    inp = build_failure_input(ledger_state="DISPATCHED_AMBIGUOUS")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_LEDGER_AMBIGUOUS_SEND


@pytest.mark.parametrize(
    "ledger_state",
    ["DISPATCHED_OK", "DISPATCHED_FAILED", "REFUSED_PRE_SEND"],
)
def test_inference_ledger_terminal_state_maps_to_duplicate_terminal(
    ledger_state,
):
    inp = build_failure_input(ledger_state=ledger_state)
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL


def test_inference_ledger_write_failed_operation_with_domain_hint_maps():
    inp = build_failure_input(
        domain_hint="ledger", ledger_state="WRITE_FAILED"
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_LEDGER_WRITE_FAILED


def test_inference_ledger_replay_failed_operation_with_domain_hint_maps():
    inp = build_failure_input(
        domain_hint="ledger", ledger_state="REPLAY_FAILED"
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_LEDGER_REPLAY_FAILED


@pytest.mark.parametrize("op", ["WRITE", "WRITE_FAILED"])
def test_inference_artifact_write_op_maps(op):
    inp = build_failure_input(artifact_operation=op)
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_ARTIFACT_WRITE_FAILED


@pytest.mark.parametrize("op", ["READ", "READ_FAILED"])
def test_inference_artifact_read_op_maps(op):
    inp = build_failure_input(artifact_operation=op)
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_ARTIFACT_READ_FAILED


def test_inference_config_conflict_reason_maps():
    inp = build_failure_input(config_reason="CONFLICT")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_CONFIG_CONFLICT


def test_inference_config_not_ready_reason_maps():
    inp = build_failure_input(config_reason="NOT_READY")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_CONFIG_NOT_READY


def test_inference_empty_input_falls_through_to_unknown_failure():
    inp = build_failure_input()
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_UNKNOWN_FAILURE


def test_inference_unmapped_hint_falls_through_to_unknown_failure():
    # ``failure_kind_hint`` is non-None but NOT in the closed set.
    inp = build_failure_input(failure_kind_hint="BOGUS_KIND")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_UNKNOWN_FAILURE


def test_inference_unknown_domain_hint_alone_falls_through():
    inp = build_failure_input(domain_hint="x_social")
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_UNKNOWN_FAILURE


# ---------------------------------------------------------------------------
# 4. failure_kind_hint takes precedence over inference
# ---------------------------------------------------------------------------


def test_explicit_hint_overrides_inferred_kind():
    # Discord 5xx status alone would infer DISCORD_SERVER_ERROR;
    # a closed-set ``failure_kind_hint`` of DISCORD_RATE_LIMITED
    # must win.
    inp = build_failure_input(
        failure_kind_hint=FAILURE_KIND_DISCORD_RATE_LIMITED,
        domain_hint="discord_transport",
        status_code=503,
    )
    rec = classify_failure(inp)
    assert rec.failure_kind == FAILURE_KIND_DISCORD_RATE_LIMITED


# ---------------------------------------------------------------------------
# 5. Redaction: raw_message NEVER leaks into the classifier output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("canary", _ALL_CANARIES)
def test_classifier_output_drops_raw_message_canary(canary: str):
    inp = build_failure_input(
        failure_kind_hint=FAILURE_KIND_DISCORD_RATE_LIMITED,
        domain_hint="discord_transport",
        status_code=429,
        exception_type_name="HTTPError",
        raw_message=canary,
    )
    rec = classify_failure(inp)
    _assert_no_canary_in(repr(rec))
    _assert_no_canary_in(str(rec))
    for field_name in rec._fields:
        value = getattr(rec, field_name)
        assert canary not in repr(value), (
            f"canary {canary!r} leaked into output field "
            f"{field_name!r}"
        )


def test_classifier_output_drops_raw_message_for_every_failure_kind():
    for kind in FAILURE_KIND_VALUES:
        inp = build_failure_input(
            failure_kind_hint=kind,
            raw_message=_CANARY_WEBHOOK_URL,
        )
        rec = classify_failure(inp)
        _assert_no_canary_in(repr(rec))


def test_classifier_output_drops_exception_type_name_from_record():
    # exception_type_name is an input hint; it must not be copied
    # to the output record. We assert there is no output field
    # whose value equals the exception type name.
    inp = build_failure_input(
        failure_kind_hint=FAILURE_KIND_DISCORD_NETWORK_ERROR,
        exception_type_name="ConnectionError",
    )
    rec = classify_failure(inp)
    for field_name in rec._fields:
        value = getattr(rec, field_name)
        assert value != "ConnectionError"


def test_classifier_output_drops_status_code_from_record():
    inp = build_failure_input(
        failure_kind_hint=FAILURE_KIND_DISCORD_RATE_LIMITED,
        status_code=429,
    )
    rec = classify_failure(inp)
    for field_name in rec._fields:
        value = getattr(rec, field_name)
        # Output is all closed-set strings + a bool; no integer
        # leak.
        assert value != 429


# ---------------------------------------------------------------------------
# 6. Redaction status is always REDACTION_APPLIED for any classify call
# ---------------------------------------------------------------------------


def test_redaction_status_is_always_applied():
    for kind in FAILURE_KIND_VALUES:
        inp = build_failure_input(
            failure_kind_hint=kind, raw_message=_CANARY_BEARER
        )
        rec = classify_failure(inp)
        assert rec.redaction_status == REDACTION_STATUS_APPLIED


# ---------------------------------------------------------------------------
# 7. safe_reason_code is the lowercased failure_kind
# ---------------------------------------------------------------------------


def test_safe_reason_code_is_lowercased_failure_kind_for_each_kind():
    for kind in FAILURE_KIND_VALUES:
        rec = classify_failure(
            build_failure_input(failure_kind_hint=kind)
        )
        assert rec.safe_reason_code == kind.lower()


# ---------------------------------------------------------------------------
# 8. Every classifier output is closed-set
# ---------------------------------------------------------------------------


def test_every_failure_kind_output_is_closed_set():
    for kind in FAILURE_KIND_VALUES:
        rec = classify_failure(
            build_failure_input(failure_kind_hint=kind)
        )
        _assert_output_is_closed_set(rec)


# ---------------------------------------------------------------------------
# 9. Inferred output is closed-set too (no UNKNOWN_FAILURE leak from
#    a successfully-inferred case)
# ---------------------------------------------------------------------------


def test_inferred_classification_is_closed_set_for_known_inferences():
    inferred_inputs = (
        build_failure_input(
            domain_hint="discord_transport", status_code=429
        ),
        build_failure_input(
            domain_hint="discord_transport", status_code=503
        ),
        build_failure_input(
            domain_hint="discord_transport",
            exception_type_name="ConnectionError",
        ),
        build_failure_input(
            domain_hint="discord_transport", status_code=401
        ),
        build_failure_input(
            domain_hint="provider",
            exception_type_name="ConnectionError",
        ),
        build_failure_input(domain_hint="provider", status_code=429),
        build_failure_input(
            domain_hint="price", exception_type_name="TimeoutError"
        ),
        build_failure_input(pair_status="UNKNOWN"),
        build_failure_input(pair_status="DISAGREE"),
        build_failure_input(pair_status="USDC_OBSERVE_ONLY"),
        build_failure_input(ledger_state="DISPATCHED_AMBIGUOUS"),
        build_failure_input(ledger_state="DISPATCHED_OK"),
        build_failure_input(artifact_operation="WRITE_FAILED"),
        build_failure_input(artifact_operation="READ"),
        build_failure_input(config_reason="CONFLICT"),
        build_failure_input(config_reason="NOT_READY"),
    )
    for inp in inferred_inputs:
        rec = classify_failure(inp)
        _assert_output_is_closed_set(rec)
        # And the inferred kind must not silently collapse to
        # UNKNOWN_FAILURE.
        assert rec.failure_kind != FAILURE_KIND_UNKNOWN_FAILURE
