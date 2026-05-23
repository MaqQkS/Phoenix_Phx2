"""Stage 28.3b retry-policy model tests.

Pins:

  * Locked Stage 28.3b version axes and the redaction token.
  * Closed-set retry-outcome / profile-name / terminal-reason /
    safe-retry-reason-code vocabularies.
  * Closed-set validators accept exactly their closed set and
    reject everything else.
  * Stage 28.3b model exceptions never carry raw secret-like
    values; they expose only closed-set tokens.
  * ``Stage28_3bRetryPolicyInput`` and ``Stage28_3bRetryDecision``
    are immutable NamedTuple records with stable field tuples.
  * ``build_retry_policy_input`` accepts only non-negative ``int``
    attempt / budget counters and rejects ``bool`` aliases.
  * Locked retry-after caps are non-negative finite ``float``s.
  * Canary webhook URL / API key / bearer / provider endpoint /
    raw env-like value never appears in any record's repr / str.
"""

from __future__ import annotations

import math

import pytest

from PHX2.stage28.failure_classification_models import (
    DISPATCH_SAFETY_DEFERRED,
    DOMAIN_DISCORD_TRANSPORT,
    FAILURE_KIND_DISCORD_RATE_LIMITED,
    OPERATOR_VISIBILITY_NOTICE,
    OPERATOR_VISIBILITY_VALUES,
    RECOMMENDED_ACTION_RETRY_PENDING,
    REDACTION_STATUS_APPLIED,
    REDACTION_STATUS_VALUES,
    SESSION_CONTINUATION_CONTINUE,
    SESSION_CONTINUATION_STATUS_VALUES,
    SEVERITY_WARNING,
    Stage28_3aFailureClassification,
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
    RETRY_OUTCOME_VALUES,
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
    SAFE_RETRY_REASON_CODE_VALUES,
    STAGE28_3B_MINOR_VERSION,
    STAGE28_3B_OPERATOR_VISIBILITY_VALUES,
    STAGE28_3B_REDACTION_STATUS_VALUES,
    STAGE28_3B_REDACTION_TOKEN,
    STAGE28_3B_SCHEMA_VERSION,
    STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES,
    TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED,
    TERMINAL_REASON_NONE,
    TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE,
    TERMINAL_REASON_PROFILE_EXHAUSTED,
    TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    TERMINAL_REASON_VALUES,
    RetryProfile,
    Stage28_3bInvalidRetryPolicyInputError,
    Stage28_3bInvalidRetryProfileError,
    Stage28_3bRetryDecision,
    Stage28_3bRetryPolicyError,
    Stage28_3bRetryPolicyInput,
    build_retry_policy_input,
    is_non_retry_outcome,
    is_retry_allowed_outcome,
    is_retry_outcome_value,
    is_retry_profile_name_value,
    is_safe_retry_reason_code_value,
    is_terminal_reason_value,
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
_CANARY_API_KEY: str = "s" + "k-CANARY-API-KEY-DO-NOT-LEAK-1234567890"
_CANARY_BEARER: str = (
    "B" + "earer CANARY-TOKEN-DO-NOT-LEAK-987654321"
)
_CANARY_AUTH_HEADER: str = (
    "A" + "uthorization: " + "B" + "earer CANARY-AUTH"
)
_CANARY_RAW_ENV: str = (
    "DISCORD_WEBHOOK" + "_URL=h" + "ttps://canary"
)


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
            f"canary value {canary!r} leaked into Stage 28.3b surface"
        )


# ---------------------------------------------------------------------------
# Stage 28.3a record fixture helper
# ---------------------------------------------------------------------------


def _retryable_classification() -> Stage28_3aFailureClassification:
    """Return a Stage 28.3a closed-set retryable classification
    suitable for constructing Stage 28.3b inputs in these model
    tests. Uses ``DISCORD_RATE_LIMITED`` because Stage 28.3a marks
    it ``retryable_in_principle=True``.
    """
    return Stage28_3aFailureClassification(
        failure_kind=FAILURE_KIND_DISCORD_RATE_LIMITED,
        domain=DOMAIN_DISCORD_TRANSPORT,
        retryable_in_principle=True,
        recommended_action=RECOMMENDED_ACTION_RETRY_PENDING,
        severity=SEVERITY_WARNING,
        dispatch_safety_status=DISPATCH_SAFETY_DEFERRED,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code=FAILURE_KIND_DISCORD_RATE_LIMITED.lower(),
        redaction_status=REDACTION_STATUS_APPLIED,
    )


# ---------------------------------------------------------------------------
# 1. Version axes + redaction token
# ---------------------------------------------------------------------------


def test_stage28_3b_minor_version_is_28_3b():
    assert STAGE28_3B_MINOR_VERSION == "28.3b"


def test_stage28_3b_schema_version_is_locked_v0():
    assert (
        STAGE28_3B_SCHEMA_VERSION == "stage28_3b_retry_policy_v0"
    )


def test_stage28_3b_redaction_token_is_locked():
    assert STAGE28_3B_REDACTION_TOKEN == "<<STAGE28_3B_REDACTED>>"


def test_stage28_3b_redaction_token_is_distinct_from_other_tokens():
    assert "STAGE28_3B_REDACTED" in STAGE28_3B_REDACTION_TOKEN
    assert "STAGE28_3A_REDACTED" not in STAGE28_3B_REDACTION_TOKEN
    assert "STAGE28_2_REDACTED" not in STAGE28_3B_REDACTION_TOKEN
    assert "STAGE28_1_REDACTED" not in STAGE28_3B_REDACTION_TOKEN


# ---------------------------------------------------------------------------
# 2. Closed-set: retry outcomes
# ---------------------------------------------------------------------------


_EXPECTED_RETRY_OUTCOME_VALUES: frozenset[str] = frozenset(
    {
        "RETRY_ALLOWED",
        "RETRY_NOT_ALLOWED",
        "RETRY_EXHAUSTED",
        "RETRY_SUPPRESSED",
        "FAIL_CLOSED",
        "STOP_SESSION",
        "OPERATOR_REVIEW_REQUIRED",
        "NO_RETRY_TERMINAL",
    }
)


def test_retry_outcome_values_match_locked_closed_set():
    assert (
        set(RETRY_OUTCOME_VALUES) == _EXPECTED_RETRY_OUTCOME_VALUES
    )
    assert len(RETRY_OUTCOME_VALUES) == len(
        _EXPECTED_RETRY_OUTCOME_VALUES
    )


def test_retry_outcome_values_are_uppercase_tokens():
    for v in RETRY_OUTCOME_VALUES:
        assert v.isupper(), f"retry outcome {v!r} must be uppercase"
        for ch in v:
            assert ch.isalpha() or ch == "_" or ch.isdigit(), (
                f"retry outcome {v!r} carries unexpected character "
                f"{ch!r}"
            )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_RETRY_OUTCOME_VALUES)
)
def test_is_retry_outcome_value_accepts_each_closed_set_value(value):
    assert is_retry_outcome_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "RANDOM",
        "retry_allowed",
        "RETRY ALLOWED",
        "RETRY-ALLOWED",
        None,
        0,
        1,
        True,
        False,
        b"RETRY_ALLOWED",
        ["RETRY_ALLOWED"],
        {"RETRY_ALLOWED"},
    ],
)
def test_is_retry_outcome_value_rejects_non_closed_set_input(value):
    assert not is_retry_outcome_value(value)


def test_retry_outcome_constants_match_string_literals():
    assert RETRY_OUTCOME_ALLOWED == "RETRY_ALLOWED"
    assert RETRY_OUTCOME_NOT_ALLOWED == "RETRY_NOT_ALLOWED"
    assert RETRY_OUTCOME_EXHAUSTED == "RETRY_EXHAUSTED"
    assert RETRY_OUTCOME_SUPPRESSED == "RETRY_SUPPRESSED"
    assert RETRY_OUTCOME_FAIL_CLOSED == "FAIL_CLOSED"
    assert RETRY_OUTCOME_STOP_SESSION == "STOP_SESSION"
    assert (
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED
        == "OPERATOR_REVIEW_REQUIRED"
    )
    assert RETRY_OUTCOME_NO_RETRY_TERMINAL == "NO_RETRY_TERMINAL"


def test_is_retry_allowed_outcome_accepts_only_retry_allowed():
    assert is_retry_allowed_outcome(RETRY_OUTCOME_ALLOWED)
    for v in RETRY_OUTCOME_VALUES:
        if v == RETRY_OUTCOME_ALLOWED:
            continue
        assert not is_retry_allowed_outcome(v)


def test_is_non_retry_outcome_accepts_every_non_retry_outcome():
    for v in RETRY_OUTCOME_VALUES:
        if v == RETRY_OUTCOME_ALLOWED:
            assert not is_non_retry_outcome(v)
        else:
            assert is_non_retry_outcome(v)


# ---------------------------------------------------------------------------
# 3. Closed-set: retry profile names
# ---------------------------------------------------------------------------


_EXPECTED_RETRY_PROFILE_NAME_VALUES: frozenset[str] = frozenset(
    {
        "NO_RETRY",
        "DISCORD_RATE_LIMITED",
        "DISCORD_TRANSIENT",
        "PROVIDER_RECONNECT",
        "PRICE_REFRESH",
        "ARTIFACT_WRITE_ONCE",
        "LEDGER_WRITE_ONCE",
        "CONFIG_OPERATOR_FIX",
        "INTERNAL_STOP",
        "SECRET_VIOLATION_STOP",
    }
)


def test_retry_profile_name_values_match_locked_closed_set():
    assert (
        set(RETRY_PROFILE_NAME_VALUES)
        == _EXPECTED_RETRY_PROFILE_NAME_VALUES
    )
    assert len(RETRY_PROFILE_NAME_VALUES) == len(
        _EXPECTED_RETRY_PROFILE_NAME_VALUES
    )


@pytest.mark.parametrize(
    "value", sorted(_EXPECTED_RETRY_PROFILE_NAME_VALUES)
)
def test_is_retry_profile_name_value_accepts_each(value):
    assert is_retry_profile_name_value(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "RANDOM",
        "no_retry",  # lowercase rejected
        "DISCORD",
        None,
        0,
        True,
    ],
)
def test_is_retry_profile_name_value_rejects_non_closed_set(value):
    assert not is_retry_profile_name_value(value)


def test_retry_profile_name_constants_match_string_literals():
    assert RETRY_PROFILE_NAME_NO_RETRY == "NO_RETRY"
    assert (
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
        == "DISCORD_RATE_LIMITED"
    )
    assert RETRY_PROFILE_NAME_DISCORD_TRANSIENT == "DISCORD_TRANSIENT"
    assert (
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT == "PROVIDER_RECONNECT"
    )
    assert RETRY_PROFILE_NAME_PRICE_REFRESH == "PRICE_REFRESH"
    assert (
        RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE
        == "ARTIFACT_WRITE_ONCE"
    )
    assert (
        RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE == "LEDGER_WRITE_ONCE"
    )
    assert (
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX
        == "CONFIG_OPERATOR_FIX"
    )
    assert RETRY_PROFILE_NAME_INTERNAL_STOP == "INTERNAL_STOP"
    assert (
        RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP
        == "SECRET_VIOLATION_STOP"
    )


# ---------------------------------------------------------------------------
# 4. Closed-set: terminal reasons
# ---------------------------------------------------------------------------


def test_terminal_reason_values_are_a_finite_uppercase_closed_set():
    assert len(TERMINAL_REASON_VALUES) >= 8
    for v in TERMINAL_REASON_VALUES:
        assert v.isupper(), f"terminal reason {v!r} must be uppercase"
        for ch in v:
            assert ch.isalpha() or ch == "_" or ch.isdigit()


def test_terminal_reason_none_is_present():
    assert TERMINAL_REASON_NONE in TERMINAL_REASON_VALUES


def test_terminal_reason_profile_exhausted_is_present():
    assert TERMINAL_REASON_PROFILE_EXHAUSTED in TERMINAL_REASON_VALUES


def test_terminal_reason_global_budget_exhausted_is_present():
    assert (
        TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED
        in TERMINAL_REASON_VALUES
    )


def test_terminal_reason_not_retryable_in_principle_is_present():
    assert (
        TERMINAL_REASON_NOT_RETRYABLE_IN_PRINCIPLE
        in TERMINAL_REASON_VALUES
    )


def test_terminal_reason_fail_closed_by_classification_is_present():
    assert (
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION
        in TERMINAL_REASON_VALUES
    )


def test_terminal_reason_rate_limit_exhausted_is_present():
    assert (
        TERMINAL_REASON_RATE_LIMIT_EXHAUSTED in TERMINAL_REASON_VALUES
    )


@pytest.mark.parametrize("value", sorted(TERMINAL_REASON_VALUES))
def test_is_terminal_reason_value_accepts_each(value):
    assert is_terminal_reason_value(value)


@pytest.mark.parametrize(
    "value", ["", "random", "PROFILE", None, 0, True]
)
def test_is_terminal_reason_value_rejects_non_closed_set(value):
    assert not is_terminal_reason_value(value)


# ---------------------------------------------------------------------------
# 5. Closed-set: safe retry reason codes
# ---------------------------------------------------------------------------


def test_safe_retry_reason_code_values_are_lowercased_outcomes():
    assert set(SAFE_RETRY_REASON_CODE_VALUES) == {
        v.lower() for v in RETRY_OUTCOME_VALUES
    }
    assert len(SAFE_RETRY_REASON_CODE_VALUES) == len(
        RETRY_OUTCOME_VALUES
    )


def test_safe_retry_reason_codes_are_all_lowercase():
    for v in SAFE_RETRY_REASON_CODE_VALUES:
        assert v.islower(), (
            f"safe retry reason code {v!r} must be lowercase"
        )
        for ch in v:
            assert ch.isalpha() or ch == "_" or ch.isdigit()


def test_is_safe_retry_reason_code_value_accepts_each():
    for v in SAFE_RETRY_REASON_CODE_VALUES:
        assert is_safe_retry_reason_code_value(v)


def test_is_safe_retry_reason_code_rejects_uppercase_outcome():
    for v in RETRY_OUTCOME_VALUES:
        assert not is_safe_retry_reason_code_value(v)


# ---------------------------------------------------------------------------
# 6. Retry-after caps
# ---------------------------------------------------------------------------


def test_retry_after_max_seconds_is_finite_positive_float():
    assert isinstance(RETRY_AFTER_MAX_SECONDS, float)
    assert not math.isnan(RETRY_AFTER_MAX_SECONDS)
    assert not math.isinf(RETRY_AFTER_MAX_SECONDS)
    assert RETRY_AFTER_MAX_SECONDS > 0.0
    assert RETRY_AFTER_MAX_SECONDS <= 30.0


def test_retry_after_max_seconds_is_locked_at_30():
    assert RETRY_AFTER_MAX_SECONDS == 30.0


def test_retry_after_min_seconds_is_non_negative_finite_float():
    assert isinstance(RETRY_AFTER_MIN_SECONDS, float)
    assert not math.isnan(RETRY_AFTER_MIN_SECONDS)
    assert not math.isinf(RETRY_AFTER_MIN_SECONDS)
    assert RETRY_AFTER_MIN_SECONDS >= 0.0


def test_retry_after_default_seconds_is_within_locked_caps():
    assert isinstance(RETRY_AFTER_DEFAULT_SECONDS, float)
    assert not math.isnan(RETRY_AFTER_DEFAULT_SECONDS)
    assert not math.isinf(RETRY_AFTER_DEFAULT_SECONDS)
    assert RETRY_AFTER_MIN_SECONDS <= RETRY_AFTER_DEFAULT_SECONDS
    assert RETRY_AFTER_DEFAULT_SECONDS <= RETRY_AFTER_MAX_SECONDS


# ---------------------------------------------------------------------------
# 7. RetryProfile NamedTuple
# ---------------------------------------------------------------------------


_EXPECTED_PROFILE_FIELDS: tuple[str, ...] = (
    "name",
    "max_attempts",
    "delay_schedule_seconds",
    "max_total_delay_seconds",
    "terminal_retry_outcome",
    "terminal_reason",
    "terminal_session_continuation",
    "terminal_dispatch_allowed",
    "terminal_operator_visibility",
)


def test_retry_profile_field_set_is_locked():
    assert RetryProfile._fields == _EXPECTED_PROFILE_FIELDS


def test_retry_profile_is_immutable_named_tuple():
    profile = RetryProfile(
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
    with pytest.raises(AttributeError):
        profile.max_attempts = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. Stage28_3bRetryPolicyInput shape + immutability + builder
# ---------------------------------------------------------------------------


_EXPECTED_INPUT_FIELDS: tuple[str, ...] = (
    "classification",
    "attempts_already_made",
    "global_retries_used",
    "global_max_retries",
    "retry_after_hint_seconds",
)


def test_retry_policy_input_field_set_is_locked():
    assert (
        Stage28_3bRetryPolicyInput._fields == _EXPECTED_INPUT_FIELDS
    )


def test_retry_policy_input_is_immutable_named_tuple():
    cls = _retryable_classification()
    inp = build_retry_policy_input(classification=cls)
    with pytest.raises(AttributeError):
        inp.attempts_already_made = 1  # type: ignore[misc]


def test_build_retry_policy_input_accepts_defaults():
    cls = _retryable_classification()
    inp = build_retry_policy_input(classification=cls)
    assert inp.classification is cls
    assert inp.attempts_already_made == 0
    assert inp.global_retries_used == 0
    assert inp.global_max_retries is None
    assert inp.retry_after_hint_seconds is None


def test_build_retry_policy_input_rejects_non_classification():
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification="not_a_classification"  # type: ignore[arg-type]
        )
    assert exc_info.value.field_name == "classification"
    assert (
        exc_info.value.reason
        == "CLASSIFICATION_NOT_STAGE_28_3A_RECORD"
    )


def test_build_retry_policy_input_rejects_bool_attempts():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls,
            attempts_already_made=True,  # type: ignore[arg-type]
        )
    assert exc_info.value.field_name == "attempts_already_made"
    assert exc_info.value.reason == "ATTEMPTS_NOT_INT"


def test_build_retry_policy_input_rejects_negative_attempts():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls, attempts_already_made=-1
        )
    assert exc_info.value.field_name == "attempts_already_made"
    assert exc_info.value.reason == "ATTEMPTS_NEGATIVE"


def test_build_retry_policy_input_rejects_non_int_attempts():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls,
            attempts_already_made="2",  # type: ignore[arg-type]
        )
    assert exc_info.value.field_name == "attempts_already_made"
    assert exc_info.value.reason == "ATTEMPTS_NOT_INT"


def test_build_retry_policy_input_rejects_bool_global_used():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls,
            global_retries_used=False,  # type: ignore[arg-type]
        )
    assert exc_info.value.field_name == "global_retries_used"


def test_build_retry_policy_input_rejects_negative_global_used():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls, global_retries_used=-1
        )
    assert exc_info.value.field_name == "global_retries_used"
    assert exc_info.value.reason == "GLOBAL_USED_NEGATIVE"


def test_build_retry_policy_input_rejects_negative_global_max():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls, global_max_retries=-3
        )
    assert exc_info.value.field_name == "global_max_retries"
    assert exc_info.value.reason == "GLOBAL_MAX_NEGATIVE"


def test_build_retry_policy_input_rejects_non_numeric_retry_after():
    cls = _retryable_classification()
    with pytest.raises(
        Stage28_3bInvalidRetryPolicyInputError
    ) as exc_info:
        build_retry_policy_input(
            classification=cls,
            retry_after_hint_seconds="2.5",  # type: ignore[arg-type]
        )
    assert exc_info.value.field_name == "retry_after_hint_seconds"


def test_build_retry_policy_input_accepts_numeric_retry_after():
    cls = _retryable_classification()
    inp = build_retry_policy_input(
        classification=cls, retry_after_hint_seconds=2
    )
    assert inp.retry_after_hint_seconds == 2.0
    inp = build_retry_policy_input(
        classification=cls, retry_after_hint_seconds=3.5
    )
    assert inp.retry_after_hint_seconds == 3.5


# ---------------------------------------------------------------------------
# 9. Stage28_3bRetryDecision shape + immutability
# ---------------------------------------------------------------------------


_EXPECTED_DECISION_FIELDS: tuple[str, ...] = (
    "retry_outcome",
    "retry_allowed",
    "delay_seconds",
    "next_attempt_index",
    "attempts_remaining",
    "profile_name",
    "terminal_reason_if_exhausted",
    "dispatch_allowed",
    "session_continuation_status",
    "operator_visibility",
    "safe_reason_code",
    "redaction_status",
)


def test_retry_decision_field_set_is_locked():
    assert (
        Stage28_3bRetryDecision._fields == _EXPECTED_DECISION_FIELDS
    )


def test_retry_decision_is_immutable_named_tuple():
    decision = Stage28_3bRetryDecision(
        retry_outcome=RETRY_OUTCOME_ALLOWED,
        retry_allowed=True,
        delay_seconds=1.0,
        next_attempt_index=1,
        attempts_remaining=1,
        profile_name=RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
        terminal_reason_if_exhausted=TERMINAL_REASON_NONE,
        dispatch_allowed=True,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code="retry_allowed",
        redaction_status=REDACTION_STATUS_APPLIED,
    )
    with pytest.raises(AttributeError):
        decision.retry_allowed = False  # type: ignore[misc]


def test_retry_decision_excludes_raw_classifier_message_field():
    # By construction, ``raw_message`` is not a field on the
    # decision record. The classification record drops it on the
    # Stage 28.3a layer; the Stage 28.3b layer never re-introduces
    # it.
    assert "raw_message" not in Stage28_3bRetryDecision._fields


def test_retry_decision_excludes_routing_subscriber_or_trade_fields():
    forbidden = {
        "subscriber_id",
        "public_channel_id",
        "paid_tier",
        "audience",
        "route_id",
        "approval_status",
        "enforcement_result",
        "trade_side",
        "position_size",
        "wallet_address",
        "signer_address",
        "private_key",
        "bearer_token",
        "webhook_url",
        "provider_endpoint",
        "api_key",
    }
    actual = set(Stage28_3bRetryDecision._fields)
    leaked = actual & forbidden
    assert not leaked, (
        f"Stage 28.3b decision record must not declare forbidden "
        f"fields {leaked!r}"
    )


# ---------------------------------------------------------------------------
# 10. Repr / str safety: closed-set tokens only
# ---------------------------------------------------------------------------


def test_retry_decision_repr_does_not_leak_canaries():
    decision = Stage28_3bRetryDecision(
        retry_outcome=RETRY_OUTCOME_ALLOWED,
        retry_allowed=True,
        delay_seconds=1.0,
        next_attempt_index=1,
        attempts_remaining=1,
        profile_name=RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
        terminal_reason_if_exhausted=TERMINAL_REASON_NONE,
        dispatch_allowed=True,
        session_continuation_status=SESSION_CONTINUATION_CONTINUE,
        operator_visibility=OPERATOR_VISIBILITY_NOTICE,
        safe_reason_code="retry_allowed",
        redaction_status=REDACTION_STATUS_APPLIED,
    )
    _assert_no_canary_in(repr(decision))
    _assert_no_canary_in(str(decision))


def test_retry_policy_input_repr_does_not_leak_canaries():
    cls = _retryable_classification()
    inp = build_retry_policy_input(
        classification=cls,
        attempts_already_made=0,
        retry_after_hint_seconds=2.0,
    )
    _assert_no_canary_in(repr(inp))
    _assert_no_canary_in(str(inp))


def test_retry_profile_repr_does_not_leak_canaries():
    profile = RetryProfile(
        name=RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
        max_attempts=2,
        delay_schedule_seconds=(1.0, 5.0),
        max_total_delay_seconds=10.0,
        terminal_retry_outcome=RETRY_OUTCOME_EXHAUSTED,
        terminal_reason=TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
        terminal_session_continuation=SESSION_CONTINUATION_CONTINUE,
        terminal_dispatch_allowed=False,
        terminal_operator_visibility=OPERATOR_VISIBILITY_NOTICE,
    )
    _assert_no_canary_in(repr(profile))
    _assert_no_canary_in(str(profile))


# ---------------------------------------------------------------------------
# 11. Module-local exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_input_error_is_subclass_of_base():
    assert issubclass(
        Stage28_3bInvalidRetryPolicyInputError,
        Stage28_3bRetryPolicyError,
    )


def test_invalid_profile_error_is_subclass_of_base():
    assert issubclass(
        Stage28_3bInvalidRetryProfileError,
        Stage28_3bRetryPolicyError,
    )


def test_invalid_input_error_carries_only_safe_fields():
    err = Stage28_3bInvalidRetryPolicyInputError(
        field_name="attempts_already_made",
        reason="ATTEMPTS_NEGATIVE",
    )
    text = str(err)
    assert "attempts_already_made" in text
    assert "ATTEMPTS_NEGATIVE" in text
    _assert_no_canary_in(text)
    _assert_no_canary_in(repr(err))


def test_invalid_profile_error_carries_only_safe_fields():
    err = Stage28_3bInvalidRetryProfileError(
        profile_name="DISCORD_RATE_LIMITED",
        reason="DELAY_SCHEDULE_ENTRY_NEGATIVE",
    )
    text = str(err)
    assert "DISCORD_RATE_LIMITED" in text
    assert "DELAY_SCHEDULE_ENTRY_NEGATIVE" in text
    _assert_no_canary_in(text)


def test_base_exception_is_module_local():
    # Stage 28.3b error hierarchy is intentionally module-local.
    assert Stage28_3bRetryPolicyError.__module__.startswith(
        "PHX2.stage28"
    )


# ---------------------------------------------------------------------------
# 12. Re-exported Stage 28.3a closed-sets
# ---------------------------------------------------------------------------


def test_session_continuation_status_re_export_matches_stage_28_3a():
    assert set(STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES) == set(
        SESSION_CONTINUATION_STATUS_VALUES
    )


def test_operator_visibility_re_export_matches_stage_28_3a():
    assert set(STAGE28_3B_OPERATOR_VISIBILITY_VALUES) == set(
        OPERATOR_VISIBILITY_VALUES
    )


def test_redaction_status_re_export_matches_stage_28_3a():
    assert set(STAGE28_3B_REDACTION_STATUS_VALUES) == set(
        REDACTION_STATUS_VALUES
    )
