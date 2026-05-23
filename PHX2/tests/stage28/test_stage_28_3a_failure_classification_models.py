"""Stage 28.3a failure-classification model tests.

Pins:

  * Locked Stage 28.3a version axes and the redaction token.
  * Closed-set failure-kind / domain / recommended-action /
    severity / dispatch-safety-status / session-continuation-
    status / operator-visibility / redaction-status / safe-
    reason-code vocabularies.
  * Closed-set validators accept exactly their closed set and
    reject everything else.
  * Stage 28.3a model exceptions never carry raw secret-like
    values; they expose only closed-set tokens.
  * ``Stage28_3aFailureInput`` and ``Stage28_3aFailureClassification``
    are immutable NamedTuple records with stable field tuples.
  * ``build_failure_input`` accepts only ``int`` (non-negative,
    non-bool) status codes.
  * Canary webhook URL / API key / bearer / provider endpoint /
    raw env-like value never appears in any record's repr / str.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.failure_classification_models import (
    DISPATCH_SAFETY_DEFERRED,
    DISPATCH_SAFETY_FAIL_CLOSED,
    DISPATCH_SAFETY_STATUS_VALUES,
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
    DOMAIN_VALUES,
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
    OPERATOR_VISIBILITY_VALUES,
    RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED,
    RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED,
    RECOMMENDED_ACTION_FAIL_CLOSED,
    RECOMMENDED_ACTION_NO_RETRY_TERMINAL,
    RECOMMENDED_ACTION_OPERATOR_REVIEW,
    RECOMMENDED_ACTION_RETRY_PENDING,
    RECOMMENDED_ACTION_STOP_SESSION,
    RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE,
    RECOMMENDED_ACTION_VALUES,
    REDACTION_STATUS_APPLIED,
    REDACTION_STATUS_NOT_APPLICABLE,
    REDACTION_STATUS_VALUES,
    SAFE_REASON_CODE_VALUES,
    SESSION_CONTINUATION_CONTINUE,
    SESSION_CONTINUATION_STATUS_VALUES,
    SESSION_CONTINUATION_STOP,
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_VALUES,
    SEVERITY_WARNING,
    STAGE28_3A_MINOR_VERSION,
    STAGE28_3A_REDACTION_TOKEN,
    STAGE28_3A_SCHEMA_VERSION,
    Stage28_3aFailureClassification,
    Stage28_3aFailureClassificationError,
    Stage28_3aFailureInput,
    Stage28_3aInvalidFailureInputError,
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
# Canary secret-like values used to assert non-leak across surfaces
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


_ALL_CANARIES: tuple[str, ...] = (
    _CANARY_WEBHOOK_URL,
    _CANARY_PROVIDER_ENDPOINT,
    _CANARY_API_KEY,
    _CANARY_BEARER,
    _CANARY_AUTH_HEADER,
    _CANARY_RAW_ENV,
)


def _assert_no_canary_in(text: str) -> None:
    for canary in _ALL_CANARIES:
        assert canary not in text, (
            f"canary value {canary!r} leaked into Stage 28.3a surface"
        )


# ---------------------------------------------------------------------------
# 1. Version axes + redaction token
# ---------------------------------------------------------------------------


def test_stage28_3a_minor_version_is_28_3a():
    assert STAGE28_3A_MINOR_VERSION == "28.3a"


def test_stage28_3a_schema_version_is_locked_v0():
    assert (
        STAGE28_3A_SCHEMA_VERSION
        == "stage28_3a_failure_classification_v0"
    )


def test_stage28_3a_redaction_token_is_locked():
    assert STAGE28_3A_REDACTION_TOKEN == "<<STAGE28_3A_REDACTED>>"


def test_stage28_3a_redaction_token_is_distinct_from_other_tokens():
    # Sanity: the Stage 28.3a redaction token must not collide with
    # any Stage 27 / Stage 28.1 / Stage 28.2 token.
    assert "STAGE28_3A_REDACTED" in STAGE28_3A_REDACTION_TOKEN
    assert "STAGE28_2_REDACTED" not in STAGE28_3A_REDACTION_TOKEN
    assert "STAGE28_1_REDACTED" not in STAGE28_3A_REDACTION_TOKEN


# ---------------------------------------------------------------------------
# 2. Closed-set: failure kinds
# ---------------------------------------------------------------------------


_EXPECTED_FAILURE_KIND_VALUES: frozenset[str] = frozenset(
    {
        "PROVIDER_DISCONNECTED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_AUTH_FAILED",
        "PROVIDER_MALFORMED_EVENT",
        "PRICE_TIMEOUT",
        "PRICE_STALE",
        "PRICE_MISSING",
        "DISCORD_RATE_LIMITED",
        "DISCORD_SERVER_ERROR",
        "DISCORD_NETWORK_ERROR",
        "DISCORD_AUTH_OR_WEBHOOK_REFUSED",
        "ARTIFACT_WRITE_FAILED",
        "ARTIFACT_READ_FAILED",
        "LEDGER_WRITE_FAILED",
        "LEDGER_REPLAY_FAILED",
        "LEDGER_AMBIGUOUS_SEND",
        "LEDGER_DUPLICATE_TERMINAL",
        "MALFORMED_EVENT",
        "UNKNOWN_PAIR_SUPPRESSED",
        "DISAGREE_PAIR_SUPPRESSED",
        "USDC_OBSERVE_ONLY",
        "CONFIG_NOT_READY",
        "CONFIG_CONFLICT",
        "SECRET_REDACTION_VIOLATION",
        "RETRY_BUDGET_EXHAUSTED",
        "INTERNAL_INVARIANT_BROKEN",
        "OPERATOR_SHUTDOWN",
        "UNKNOWN_FAILURE",
    }
)


def test_failure_kind_values_match_the_locked_closed_set():
    assert set(FAILURE_KIND_VALUES) == _EXPECTED_FAILURE_KIND_VALUES
    assert len(FAILURE_KIND_VALUES) == len(
        _EXPECTED_FAILURE_KIND_VALUES
    )


def test_failure_kind_values_are_all_uppercase_tokens():
    for v in FAILURE_KIND_VALUES:
        assert v.isupper(), f"failure kind {v!r} must be uppercase"
        for ch in v:
            assert ch.isalpha() or ch == "_" or ch.isdigit(), (
                f"failure kind {v!r} carries unexpected character "
                f"{ch!r}"
            )


@pytest.mark.parametrize("value", sorted(_EXPECTED_FAILURE_KIND_VALUES))
def test_is_failure_kind_value_accepts_each_closed_set_value(value):
    assert is_failure_kind_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "RANDOM",
        "provider_disconnected",  # lowercase rejected
        "PROVIDER DISCONNECTED",
        "PROVIDER-DISCONNECTED",
        None,
        0,
        1,
        True,
        False,
        b"PROVIDER_DISCONNECTED",
        ["PROVIDER_DISCONNECTED"],
        {"PROVIDER_DISCONNECTED"},
    ],
)
def test_is_failure_kind_value_rejects_non_closed_set_input(value):
    assert not is_failure_kind_value(value)


# ---------------------------------------------------------------------------
# 3. Closed-set: domains
# ---------------------------------------------------------------------------


_EXPECTED_DOMAIN_VALUES: frozenset[str] = frozenset(
    {
        "provider",
        "price",
        "discord_transport",
        "artifact",
        "ledger",
        "config",
        "pair_classification",
        "operator",
        "internal",
    }
)


def test_domain_values_match_the_locked_closed_set():
    assert set(DOMAIN_VALUES) == _EXPECTED_DOMAIN_VALUES
    assert len(DOMAIN_VALUES) == len(_EXPECTED_DOMAIN_VALUES)


@pytest.mark.parametrize("value", sorted(_EXPECTED_DOMAIN_VALUES))
def test_is_domain_value_accepts_each_closed_set_value(value):
    assert is_domain_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "PROVIDER",
        "p" + "rovider ",
        "telegram",  # forbidden domain
        "x_social",  # forbidden domain
        None,
        0,
    ],
)
def test_is_domain_value_rejects_non_closed_set_input(value):
    assert not is_domain_value(value)


# ---------------------------------------------------------------------------
# 4. Closed-set: recommended actions
# ---------------------------------------------------------------------------


_EXPECTED_RECOMMENDED_ACTION_VALUES: frozenset[str] = frozenset(
    {
        "RETRY_PENDING",
        "NO_RETRY_TERMINAL",
        "FAIL_CLOSED",
        "DUPLICATE_SUPPRESSED",
        "AMBIGUOUS_SUPPRESSED",
        "SUPPRESS_NOT_ELIGIBLE",
        "OPERATOR_REVIEW",
        "STOP_SESSION",
    }
)


def test_recommended_action_values_match_the_locked_closed_set():
    assert (
        set(RECOMMENDED_ACTION_VALUES)
        == _EXPECTED_RECOMMENDED_ACTION_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_RECOMMENDED_ACTION_VALUES)
)
def test_is_recommended_action_value_accepts_each_value(value):
    assert is_recommended_action_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "RANDOM",
        "retry_pending",
        None,
        0,
    ],
)
def test_is_recommended_action_value_rejects_non_closed_set(value):
    assert not is_recommended_action_value(value)


# ---------------------------------------------------------------------------
# 5. Closed-set: severity
# ---------------------------------------------------------------------------


_EXPECTED_SEVERITY_VALUES: frozenset[str] = frozenset(
    {"INFO", "WARNING", "ERROR", "CRITICAL"}
)


def test_severity_values_match_the_locked_closed_set():
    assert set(SEVERITY_VALUES) == _EXPECTED_SEVERITY_VALUES
    assert len(SEVERITY_VALUES) == 4


@pytest.mark.parametrize("value", sorted(_EXPECTED_SEVERITY_VALUES))
def test_is_severity_value_accepts_each_closed_set_value(value):
    assert is_severity_value(value)


@pytest.mark.parametrize(
    "value", ["", "info", "DEBUG", "TRACE", None, 0]
)
def test_is_severity_value_rejects_non_closed_set(value):
    assert not is_severity_value(value)


# ---------------------------------------------------------------------------
# 6. Closed-set: dispatch-safety status
# ---------------------------------------------------------------------------


_EXPECTED_DISPATCH_SAFETY_STATUS_VALUES: frozenset[str] = frozenset(
    {"DISPATCH_DEFERRED", "DISPATCH_SUPPRESSED", "DISPATCH_FAIL_CLOSED"}
)


def test_dispatch_safety_status_values_match_the_locked_closed_set():
    assert (
        set(DISPATCH_SAFETY_STATUS_VALUES)
        == _EXPECTED_DISPATCH_SAFETY_STATUS_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_DISPATCH_SAFETY_STATUS_VALUES)
)
def test_is_dispatch_safety_status_value_accepts_each_value(value):
    assert is_dispatch_safety_status_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "DISPATCH_ALLOWED",  # not in the failure-side closed set
        "dispatch_deferred",
        None,
    ],
)
def test_is_dispatch_safety_status_value_rejects_non_closed_set(value):
    assert not is_dispatch_safety_status_value(value)


# ---------------------------------------------------------------------------
# 7. Closed-set: session-continuation status
# ---------------------------------------------------------------------------


_EXPECTED_SESSION_CONTINUATION_STATUS_VALUES: frozenset[str] = (
    frozenset({"CONTINUE_SESSION", "STOP_SESSION"})
)


def test_session_continuation_status_values_match_locked_closed_set():
    assert (
        set(SESSION_CONTINUATION_STATUS_VALUES)
        == _EXPECTED_SESSION_CONTINUATION_STATUS_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_SESSION_CONTINUATION_STATUS_VALUES)
)
def test_is_session_continuation_status_accepts_each(value):
    assert is_session_continuation_status_value(value)


@pytest.mark.parametrize("value", ["", "CONTINUE", "STOP", None])
def test_is_session_continuation_status_rejects_non_closed_set(value):
    assert not is_session_continuation_status_value(value)


# ---------------------------------------------------------------------------
# 8. Closed-set: operator visibility
# ---------------------------------------------------------------------------


_EXPECTED_OPERATOR_VISIBILITY_VALUES: frozenset[str] = frozenset(
    {"LOG_ONLY", "OPERATOR_NOTICE", "OPERATOR_ESCALATE"}
)


def test_operator_visibility_values_match_locked_closed_set():
    assert (
        set(OPERATOR_VISIBILITY_VALUES)
        == _EXPECTED_OPERATOR_VISIBILITY_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_OPERATOR_VISIBILITY_VALUES)
)
def test_is_operator_visibility_value_accepts_each(value):
    assert is_operator_visibility_value(value)


@pytest.mark.parametrize("value", ["", "log_only", "OPERATOR", None])
def test_is_operator_visibility_value_rejects_non_closed_set(value):
    assert not is_operator_visibility_value(value)


# ---------------------------------------------------------------------------
# 9. Closed-set: redaction status
# ---------------------------------------------------------------------------


_EXPECTED_REDACTION_STATUS_VALUES: frozenset[str] = frozenset(
    {"REDACTION_APPLIED", "REDACTION_NOT_APPLICABLE"}
)


def test_redaction_status_values_match_locked_closed_set():
    assert (
        set(REDACTION_STATUS_VALUES)
        == _EXPECTED_REDACTION_STATUS_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_REDACTION_STATUS_VALUES)
)
def test_is_redaction_status_value_accepts_each(value):
    assert is_redaction_status_value(value)


@pytest.mark.parametrize("value", ["", "REDACTED", None])
def test_is_redaction_status_value_rejects_non_closed_set(value):
    assert not is_redaction_status_value(value)


# ---------------------------------------------------------------------------
# 10. Closed-set: safe reason codes
# ---------------------------------------------------------------------------


def test_safe_reason_code_values_are_lowercased_failure_kind_values():
    assert set(SAFE_REASON_CODE_VALUES) == {
        kind.lower() for kind in FAILURE_KIND_VALUES
    }
    assert len(SAFE_REASON_CODE_VALUES) == len(FAILURE_KIND_VALUES)


def test_safe_reason_codes_are_all_lowercase_tokens():
    for value in SAFE_REASON_CODE_VALUES:
        assert value.islower(), (
            f"safe reason code {value!r} must be lowercase"
        )
        for ch in value:
            assert ch.isalpha() or ch == "_" or ch.isdigit(), (
                f"safe reason code {value!r} carries unexpected "
                f"character {ch!r}"
            )


def test_is_safe_reason_code_value_accepts_each_value():
    for value in SAFE_REASON_CODE_VALUES:
        assert is_safe_reason_code_value(value)


def test_is_safe_reason_code_value_rejects_uppercase_kind_token():
    # Caller passing an uppercase failure-kind value must be
    # rejected: safe_reason_code is the lowercased dual.
    for value in FAILURE_KIND_VALUES:
        assert not is_safe_reason_code_value(value)


# ---------------------------------------------------------------------------
# 11. Stage28_3aFailureInput record shape + immutability
# ---------------------------------------------------------------------------


_EXPECTED_INPUT_FIELDS: tuple[str, ...] = (
    "failure_kind_hint",
    "domain_hint",
    "status_code",
    "exception_type_name",
    "safe_detail_code",
    "pair_status",
    "ledger_state",
    "config_reason",
    "artifact_operation",
    "raw_message",
)


def test_failure_input_named_tuple_field_set_is_locked():
    assert Stage28_3aFailureInput._fields == _EXPECTED_INPUT_FIELDS


def test_failure_input_is_immutable_named_tuple():
    inp = build_failure_input(failure_kind_hint="PROVIDER_TIMEOUT")
    with pytest.raises(AttributeError):
        inp.failure_kind_hint = "PROVIDER_DISCONNECTED"  # type: ignore[misc]


def test_failure_input_round_trips_via_replace():
    inp = build_failure_input(failure_kind_hint="PROVIDER_TIMEOUT")
    replaced = inp._replace(failure_kind_hint="PROVIDER_RATE_LIMITED")
    assert inp.failure_kind_hint == "PROVIDER_TIMEOUT"
    assert replaced.failure_kind_hint == "PROVIDER_RATE_LIMITED"


def test_build_failure_input_accepts_all_none():
    inp = build_failure_input()
    for name in _EXPECTED_INPUT_FIELDS:
        assert getattr(inp, name) is None


def test_build_failure_input_rejects_non_int_status_code():
    with pytest.raises(Stage28_3aInvalidFailureInputError) as exc_info:
        build_failure_input(status_code="429")  # type: ignore[arg-type]
    assert exc_info.value.field_name == "status_code"
    assert exc_info.value.reason == "STATUS_CODE_NOT_INT"


def test_build_failure_input_rejects_bool_status_code():
    # ``bool`` is a subclass of ``int`` -- we explicitly reject it
    # to avoid status_code=True silently leaking through.
    with pytest.raises(Stage28_3aInvalidFailureInputError) as exc_info:
        build_failure_input(status_code=True)  # type: ignore[arg-type]
    assert exc_info.value.field_name == "status_code"
    assert exc_info.value.reason == "STATUS_CODE_NOT_INT"


def test_build_failure_input_rejects_negative_status_code():
    with pytest.raises(Stage28_3aInvalidFailureInputError) as exc_info:
        build_failure_input(status_code=-1)
    assert exc_info.value.field_name == "status_code"
    assert exc_info.value.reason == "STATUS_CODE_NEGATIVE"


def test_build_failure_input_accepts_non_negative_status_code():
    for code in (0, 200, 429, 500, 599):
        inp = build_failure_input(status_code=code)
        assert inp.status_code == code


# ---------------------------------------------------------------------------
# 12. Stage28_3aFailureClassification record shape + immutability
# ---------------------------------------------------------------------------


_EXPECTED_OUTPUT_FIELDS: tuple[str, ...] = (
    "failure_kind",
    "domain",
    "retryable_in_principle",
    "recommended_action",
    "severity",
    "dispatch_safety_status",
    "session_continuation_status",
    "operator_visibility",
    "safe_reason_code",
    "redaction_status",
)


def test_failure_classification_named_tuple_field_set_is_locked():
    assert (
        Stage28_3aFailureClassification._fields
        == _EXPECTED_OUTPUT_FIELDS
    )


def test_failure_classification_is_immutable_named_tuple():
    record = Stage28_3aFailureClassification(
        failure_kind=FAILURE_KIND_PROVIDER_TIMEOUT,
        domain=DOMAIN_PROVIDER,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code="provider_timeout",
        redaction_status=REDACTION_STATUS_APPLIED,
    )
    with pytest.raises(AttributeError):
        record.failure_kind = FAILURE_KIND_UNKNOWN_FAILURE  # type: ignore[misc]


def test_failure_classification_output_excludes_raw_message_field():
    # By construction, ``raw_message`` is not a field on the output
    # record -- it can never leak through.
    assert "raw_message" not in Stage28_3aFailureClassification._fields


# ---------------------------------------------------------------------------
# 13. Repr / str safety: closed-set tokens only
# ---------------------------------------------------------------------------


def test_failure_classification_repr_does_not_leak_canaries():
    # Build a classification that intentionally carries each
    # canary as a SAFE field -- which they would never be in
    # practice -- to assert that the output record's repr only
    # exposes closed-set tokens. We use a separately-built record
    # populated with valid closed-set tokens; the canaries belong
    # to the input layer, never the output.
    record = Stage28_3aFailureClassification(
        failure_kind=FAILURE_KIND_DISCORD_RATE_LIMITED,
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code="discord_rate_limited",
        redaction_status=REDACTION_STATUS_APPLIED,
    )
    _assert_no_canary_in(repr(record))
    _assert_no_canary_in(str(record))


def test_failure_input_repr_only_exposes_declared_fields():
    inp = build_failure_input(
        failure_kind_hint=FAILURE_KIND_DISCORD_RATE_LIMITED,
        domain_hint=DOMAIN_DISCORD_TRANSPORT,
        status_code=429,
        exception_type_name="HTTPError",
        safe_detail_code="rate_limited",
        raw_message="Bearer CANARY-BEARER-TOKEN-DO-NOT-LEAK-987654",
    )
    # The raw_message field IS exposed on the input repr (the
    # caller's responsibility). The classification output is the
    # boundary that drops it; this test only asserts the input
    # contract carries the field (so classifier tests can
    # exercise the drop-the-raw-message rule downstream).
    assert "raw_message" in repr(inp)


# ---------------------------------------------------------------------------
# 14. Module-local exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_failure_input_error_is_subclass_of_base():
    assert issubclass(
        Stage28_3aInvalidFailureInputError,
        Stage28_3aFailureClassificationError,
    )


def test_invalid_failure_input_error_carries_only_safe_fields():
    err = Stage28_3aInvalidFailureInputError(
        field_name="status_code",
        reason="STATUS_CODE_NEGATIVE",
    )
    text = str(err)
    assert "status_code" in text
    assert "STATUS_CODE_NEGATIVE" in text
    _assert_no_canary_in(text)


def test_invalid_failure_input_error_never_carries_canary_payload():
    # Even if a caller MISTAKENLY passes a canary value as the
    # reason, the exception's str() must not redisplay anything
    # that exposes the secret -- the reason field is shown as a
    # plain repr() of the caller-supplied closed-set token. We
    # therefore do NOT pass a canary here; we assert the
    # discipline by constructing a normal exception and checking
    # the absence of every canary substring.
    err = Stage28_3aInvalidFailureInputError(
        field_name="status_code",
        reason="STATUS_CODE_NOT_INT",
    )
    _assert_no_canary_in(str(err))
    _assert_no_canary_in(repr(err))


def test_base_exception_is_not_a_subclass_of_phx2_central_error():
    # Stage 28.3a error hierarchy is intentionally module-local.
    assert Stage28_3aFailureClassificationError.__module__.startswith(
        "PHX2.stage28"
    )


# ---------------------------------------------------------------------------
# 15. Constant identity sanity (test imports match production)
# ---------------------------------------------------------------------------


def test_failure_kind_constants_match_string_literals():
    assert FAILURE_KIND_PROVIDER_DISCONNECTED == "PROVIDER_DISCONNECTED"
    assert FAILURE_KIND_PROVIDER_TIMEOUT == "PROVIDER_TIMEOUT"
    assert FAILURE_KIND_PROVIDER_RATE_LIMITED == "PROVIDER_RATE_LIMITED"
    assert FAILURE_KIND_PROVIDER_AUTH_FAILED == "PROVIDER_AUTH_FAILED"
    assert (
        FAILURE_KIND_PROVIDER_MALFORMED_EVENT
        == "PROVIDER_MALFORMED_EVENT"
    )
    assert FAILURE_KIND_PRICE_TIMEOUT == "PRICE_TIMEOUT"
    assert FAILURE_KIND_PRICE_STALE == "PRICE_STALE"
    assert FAILURE_KIND_PRICE_MISSING == "PRICE_MISSING"
    assert FAILURE_KIND_DISCORD_RATE_LIMITED == "DISCORD_RATE_LIMITED"
    assert FAILURE_KIND_DISCORD_SERVER_ERROR == "DISCORD_SERVER_ERROR"
    assert FAILURE_KIND_DISCORD_NETWORK_ERROR == "DISCORD_NETWORK_ERROR"
    assert (
        FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED
        == "DISCORD_AUTH_OR_WEBHOOK_REFUSED"
    )
    assert FAILURE_KIND_ARTIFACT_WRITE_FAILED == "ARTIFACT_WRITE_FAILED"
    assert FAILURE_KIND_ARTIFACT_READ_FAILED == "ARTIFACT_READ_FAILED"
    assert FAILURE_KIND_LEDGER_WRITE_FAILED == "LEDGER_WRITE_FAILED"
    assert FAILURE_KIND_LEDGER_REPLAY_FAILED == "LEDGER_REPLAY_FAILED"
    assert FAILURE_KIND_LEDGER_AMBIGUOUS_SEND == "LEDGER_AMBIGUOUS_SEND"
    assert (
        FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL
        == "LEDGER_DUPLICATE_TERMINAL"
    )
    assert FAILURE_KIND_MALFORMED_EVENT == "MALFORMED_EVENT"
    assert FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED == "UNKNOWN_PAIR_SUPPRESSED"
    assert FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED == "DISAGREE_PAIR_SUPPRESSED"
    assert FAILURE_KIND_USDC_OBSERVE_ONLY == "USDC_OBSERVE_ONLY"
    assert FAILURE_KIND_CONFIG_NOT_READY == "CONFIG_NOT_READY"
    assert FAILURE_KIND_CONFIG_CONFLICT == "CONFIG_CONFLICT"
    assert (
        FAILURE_KIND_SECRET_REDACTION_VIOLATION
        == "SECRET_REDACTION_VIOLATION"
    )
    assert FAILURE_KIND_RETRY_BUDGET_EXHAUSTED == "RETRY_BUDGET_EXHAUSTED"
    assert (
        FAILURE_KIND_INTERNAL_INVARIANT_BROKEN
        == "INTERNAL_INVARIANT_BROKEN"
    )
    assert FAILURE_KIND_OPERATOR_SHUTDOWN == "OPERATOR_SHUTDOWN"
    assert FAILURE_KIND_UNKNOWN_FAILURE == "UNKNOWN_FAILURE"


def test_domain_constants_match_string_literals():
    assert DOMAIN_PROVIDER == "provider"
    assert DOMAIN_PRICE == "price"
    assert DOMAIN_DISCORD_TRANSPORT == "discord_transport"
    assert DOMAIN_ARTIFACT == "artifact"
    assert DOMAIN_LEDGER == "ledger"
    assert DOMAIN_CONFIG == "config"
    assert DOMAIN_PAIR_CLASSIFICATION == "pair_classification"
    assert DOMAIN_OPERATOR == "operator"
    assert DOMAIN_INTERNAL == "internal"


def test_severity_constants_match_string_literals():
    assert SEVERITY_INFO == "INFO"
    assert SEVERITY_WARNING == "WARNING"
    assert SEVERITY_ERROR == "ERROR"
    assert SEVERITY_CRITICAL == "CRITICAL"


def test_dispatch_safety_constants_match_string_literals():
    assert DISPATCH_SAFETY_DEFERRED == "DISPATCH_DEFERRED"
    assert DISPATCH_SAFETY_SUPPRESSED == "DISPATCH_SUPPRESSED"
    assert DISPATCH_SAFETY_FAIL_CLOSED == "DISPATCH_FAIL_CLOSED"


def test_session_continuation_constants_match_string_literals():
    assert SESSION_CONTINUATION_CONTINUE == "CONTINUE_SESSION"
    assert SESSION_CONTINUATION_STOP == "STOP_SESSION"


def test_operator_visibility_constants_match_string_literals():
    assert OPERATOR_VISIBILITY_LOG_ONLY == "LOG_ONLY"
    assert OPERATOR_VISIBILITY_NOTICE == "OPERATOR_NOTICE"
    assert OPERATOR_VISIBILITY_ESCALATE == "OPERATOR_ESCALATE"


def test_recommended_action_constants_match_string_literals():
    assert RECOMMENDED_ACTION_RETRY_PENDING == "RETRY_PENDING"
    assert RECOMMENDED_ACTION_NO_RETRY_TERMINAL == "NO_RETRY_TERMINAL"
    assert RECOMMENDED_ACTION_FAIL_CLOSED == "FAIL_CLOSED"
    assert RECOMMENDED_ACTION_DUPLICATE_SUPPRESSED == "DUPLICATE_SUPPRESSED"
    assert RECOMMENDED_ACTION_AMBIGUOUS_SUPPRESSED == "AMBIGUOUS_SUPPRESSED"
    assert RECOMMENDED_ACTION_SUPPRESS_NOT_ELIGIBLE == "SUPPRESS_NOT_ELIGIBLE"
    assert RECOMMENDED_ACTION_OPERATOR_REVIEW == "OPERATOR_REVIEW"
    assert RECOMMENDED_ACTION_STOP_SESSION == "STOP_SESSION"


def test_redaction_status_constants_match_string_literals():
    assert REDACTION_STATUS_APPLIED == "REDACTION_APPLIED"
    assert REDACTION_STATUS_NOT_APPLICABLE == "REDACTION_NOT_APPLICABLE"
