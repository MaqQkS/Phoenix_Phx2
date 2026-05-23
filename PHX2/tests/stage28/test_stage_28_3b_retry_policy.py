"""Stage 28.3b retry-policy decision tests.

Pins:

  * Retryable Stage 28.3a classification with attempts remaining
    -> ``RETRY_ALLOWED`` with deterministic delay.
  * Retryable Stage 28.3a classification with attempts exhausted
    -> ``RETRY_EXHAUSTED`` with per-failure terminal-reason.
  * Global retry budget exhausted -> ``RETRY_EXHAUSTED`` with
    ``GLOBAL_BUDGET_EXHAUSTED`` terminal-reason and stop-session
    recommendation.
  * Nonretryable classification -> non-retry-allowed outcome with
    matching closed-set terminal-reason.
  * Per-failure-kind outcome mapping is exhaustive over every
    locked Stage 28.3a ``FAILURE_KIND_*`` token.
  * Discord 429 honors a clamped retry-after hint when present,
    falls back to a default delay when missing, falls back to the
    profile delay when the hint is invalid.
  * Pure: same input -> same output.
  * Pure: ``parse_retry_after_seconds`` clamps to
    ``[RETRY_AFTER_MIN_SECONDS, RETRY_AFTER_MAX_SECONDS]`` and
    refuses negative / NaN / infinite / non-numeric input.
  * Redaction: canary URL / API-key / bearer / auth-header / raw
    env string never appears in any decision repr / str / safe
    reason code.
  * Decision output never contains routing / subscriber / paid-
    tier / trading / signer / wallet / public-channel fields.
"""

from __future__ import annotations

import math

import pytest

from PHX2.stage28.failure_classification import classify_failure
from PHX2.stage28.failure_classification_models import (
    DISPATCH_SAFETY_DEFERRED,
    DISPATCH_SAFETY_FAIL_CLOSED,
    DISPATCH_SAFETY_SUPPRESSED,
    DOMAIN_DISCORD_TRANSPORT,
    DOMAIN_INTERNAL,
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
    OPERATOR_VISIBILITY_NOTICE,
    RECOMMENDED_ACTION_RETRY_PENDING,
    REDACTION_STATUS_APPLIED,
    SESSION_CONTINUATION_CONTINUE,
    SESSION_CONTINUATION_STOP,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Stage28_3aFailureClassification,
    build_failure_input,
)
from PHX2.stage28.retry_policy import (
    PROFILE_REGISTRY,
    decide_retry,
    get_profile_for_failure_kind,
    parse_retry_after_seconds,
    validate_profile_registry,
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
    TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    TERMINAL_REASON_SECRET_REDACTION_VIOLATION,
    TERMINAL_REASON_SERVER_ERROR_EXHAUSTED,
    TERMINAL_REASON_SUPPRESSED_AMBIGUOUS,
    TERMINAL_REASON_SUPPRESSED_DUPLICATE,
    TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    TERMINAL_REASON_UNKNOWN_FAILURE,
    Stage28_3bRetryPolicyInput,
    build_retry_policy_input,
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
# Fixtures
# ---------------------------------------------------------------------------


def _classify(failure_kind: str) -> Stage28_3aFailureClassification:
    return classify_failure(
        build_failure_input(failure_kind_hint=failure_kind)
    )


def _input(
    failure_kind: str,
    *,
    attempts_already_made: int = 0,
    global_retries_used: int = 0,
    global_max_retries=None,
    retry_after_hint_seconds=None,
) -> Stage28_3bRetryPolicyInput:
    return build_retry_policy_input(
        classification=_classify(failure_kind),
        attempts_already_made=attempts_already_made,
        global_retries_used=global_retries_used,
        global_max_retries=global_max_retries,
        retry_after_hint_seconds=retry_after_hint_seconds,
    )


# ---------------------------------------------------------------------------
# 1. Locked profile registry invariants
# ---------------------------------------------------------------------------


def test_profile_registry_validates_clean():
    validate_profile_registry()


def test_profile_registry_covers_every_profile_name():
    from PHX2.stage28.retry_policy_models import (
        RETRY_PROFILE_NAME_VALUES,
    )

    assert set(PROFILE_REGISTRY.keys()) == set(
        RETRY_PROFILE_NAME_VALUES
    )


def test_every_failure_kind_has_a_profile():
    for kind in FAILURE_KIND_VALUES:
        profile = get_profile_for_failure_kind(kind)
        assert profile.name in PROFILE_REGISTRY


def test_no_profile_has_infinite_or_unbounded_schedule():
    for profile in PROFILE_REGISTRY.values():
        assert profile.max_attempts == len(
            profile.delay_schedule_seconds
        )
        for delay in profile.delay_schedule_seconds:
            assert isinstance(delay, (int, float))
            assert not math.isnan(float(delay))
            assert not math.isinf(float(delay))
            assert float(delay) >= 0.0
            assert float(delay) <= RETRY_AFTER_MAX_SECONDS


def test_no_retry_profile_has_zero_attempts():
    for name in (
        RETRY_PROFILE_NAME_NO_RETRY,
        RETRY_PROFILE_NAME_CONFIG_OPERATOR_FIX,
        RETRY_PROFILE_NAME_INTERNAL_STOP,
        RETRY_PROFILE_NAME_SECRET_VIOLATION_STOP,
    ):
        profile = PROFILE_REGISTRY[name]
        assert profile.max_attempts == 0
        assert profile.delay_schedule_seconds == ()


def test_discord_rate_limited_profile_schedule_is_finite():
    profile = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
    ]
    assert profile.max_attempts == 2
    assert len(profile.delay_schedule_seconds) == 2


def test_discord_transient_profile_schedule_is_finite():
    profile = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_DISCORD_TRANSIENT
    ]
    assert profile.max_attempts == 2
    assert profile.delay_schedule_seconds == (1.0, 4.0)


def test_provider_reconnect_profile_is_5_attempts():
    profile = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ]
    assert profile.max_attempts == 5
    assert profile.delay_schedule_seconds == (1.0, 2.0, 4.0, 8.0, 16.0)


def test_price_refresh_profile_is_2_attempts():
    profile = PROFILE_REGISTRY[RETRY_PROFILE_NAME_PRICE_REFRESH]
    assert profile.max_attempts == 2
    assert profile.delay_schedule_seconds == (0.5, 1.0)


def test_artifact_and_ledger_write_once_profiles_allow_one_attempt():
    for name in (
        RETRY_PROFILE_NAME_ARTIFACT_WRITE_ONCE,
        RETRY_PROFILE_NAME_LEDGER_WRITE_ONCE,
    ):
        profile = PROFILE_REGISTRY[name]
        assert profile.max_attempts == 1
        assert profile.delay_schedule_seconds == (0.5,)


# ---------------------------------------------------------------------------
# 2. Retryable: RETRY_ALLOWED with attempts remaining
# ---------------------------------------------------------------------------


_RETRYABLE_KINDS_WITH_PROFILE: tuple[tuple[str, str, int], ...] = (
    (
        FAILURE_KIND_PROVIDER_DISCONNECTED,
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
        5,
    ),
    (
        FAILURE_KIND_PROVIDER_TIMEOUT,
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
        5,
    ),
    (
        FAILURE_KIND_PROVIDER_RATE_LIMITED,
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT,
        5,
    ),
    (
        FAILURE_KIND_PRICE_TIMEOUT,
        RETRY_PROFILE_NAME_PRICE_REFRESH,
        2,
    ),
    (
        FAILURE_KIND_DISCORD_RATE_LIMITED,
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED,
        2,
    ),
    (
        FAILURE_KIND_DISCORD_SERVER_ERROR,
        RETRY_PROFILE_NAME_DISCORD_TRANSIENT,
        2,
    ),
    (
        FAILURE_KIND_DISCORD_NETWORK_ERROR,
        RETRY_PROFILE_NAME_DISCORD_TRANSIENT,
        2,
    ),
)


@pytest.mark.parametrize(
    "failure_kind,profile_name,max_attempts",
    _RETRYABLE_KINDS_WITH_PROFILE,
)
def test_retryable_kind_with_attempts_remaining_yields_retry_allowed(
    failure_kind: str, profile_name: str, max_attempts: int
):
    decision = decide_retry(_input(failure_kind))
    assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED
    assert decision.retry_allowed is True
    assert decision.profile_name == profile_name
    assert decision.next_attempt_index == 1
    assert decision.attempts_remaining == max_attempts - 1
    assert decision.delay_seconds is not None
    assert decision.delay_seconds >= 0.0
    assert (
        decision.terminal_reason_if_exhausted == TERMINAL_REASON_NONE
    )
    assert decision.dispatch_allowed is True
    assert decision.safe_reason_code == "retry_allowed"
    assert decision.redaction_status == REDACTION_STATUS_APPLIED


# ---------------------------------------------------------------------------
# 3. Retryable: RETRY_EXHAUSTED with attempts exhausted
# ---------------------------------------------------------------------------


_RETRYABLE_EXHAUSTION_TARGETS: tuple[tuple[str, int, str], ...] = (
    (
        FAILURE_KIND_DISCORD_RATE_LIMITED,
        2,
        TERMINAL_REASON_RATE_LIMIT_EXHAUSTED,
    ),
    (
        FAILURE_KIND_DISCORD_SERVER_ERROR,
        2,
        TERMINAL_REASON_SERVER_ERROR_EXHAUSTED,
    ),
    (
        FAILURE_KIND_DISCORD_NETWORK_ERROR,
        2,
        TERMINAL_REASON_NETWORK_EXHAUSTED,
    ),
    (
        FAILURE_KIND_PROVIDER_DISCONNECTED,
        5,
        TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    ),
    (
        FAILURE_KIND_PROVIDER_TIMEOUT,
        5,
        TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    ),
    (
        FAILURE_KIND_PROVIDER_RATE_LIMITED,
        5,
        TERMINAL_REASON_PROVIDER_RECONNECT_EXHAUSTED,
    ),
    (
        FAILURE_KIND_PRICE_TIMEOUT,
        2,
        TERMINAL_REASON_PRICE_REFRESH_EXHAUSTED,
    ),
)


@pytest.mark.parametrize(
    "failure_kind,max_attempts,expected_terminal",
    _RETRYABLE_EXHAUSTION_TARGETS,
)
def test_retryable_kind_with_exhausted_attempts_yields_exhausted(
    failure_kind: str, max_attempts: int, expected_terminal: str
):
    decision = decide_retry(
        _input(failure_kind, attempts_already_made=max_attempts)
    )
    assert decision.retry_outcome == RETRY_OUTCOME_EXHAUSTED
    assert decision.retry_allowed is False
    assert decision.delay_seconds is None
    assert decision.next_attempt_index is None
    assert (
        decision.terminal_reason_if_exhausted == expected_terminal
    )
    assert decision.dispatch_allowed is False
    assert decision.redaction_status == REDACTION_STATUS_APPLIED


def test_provider_reconnect_exhaustion_recommends_stop_session():
    decision = decide_retry(
        _input(
            FAILURE_KIND_PROVIDER_DISCONNECTED,
            attempts_already_made=5,
        )
    )
    assert (
        decision.session_continuation_status
        == SESSION_CONTINUATION_STOP
    )


def test_discord_rate_limit_exhaustion_keeps_session_continuing():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED, attempts_already_made=2
        )
    )
    assert (
        decision.session_continuation_status
        == SESSION_CONTINUATION_CONTINUE
    )


# ---------------------------------------------------------------------------
# 4. Global retry budget exhausted
# ---------------------------------------------------------------------------


def test_global_budget_exhausted_yields_exhausted_with_stop_session():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            attempts_already_made=0,
            global_retries_used=10,
            global_max_retries=10,
        )
    )
    assert decision.retry_outcome == RETRY_OUTCOME_EXHAUSTED
    assert (
        decision.terminal_reason_if_exhausted
        == TERMINAL_REASON_GLOBAL_BUDGET_EXHAUSTED
    )
    assert (
        decision.session_continuation_status
        == SESSION_CONTINUATION_STOP
    )
    assert (
        decision.operator_visibility == OPERATOR_VISIBILITY_ESCALATE
    )


def test_global_budget_none_allows_retry_when_per_failure_has_budget():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            attempts_already_made=0,
            global_retries_used=999,
            global_max_retries=None,
        )
    )
    assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED


def test_global_budget_unused_under_limit_allows_retry():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            attempts_already_made=0,
            global_retries_used=3,
            global_max_retries=10,
        )
    )
    assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED


# ---------------------------------------------------------------------------
# 5. Nonretryable mappings (every kind)
# ---------------------------------------------------------------------------


_NONRETRYABLE_KIND_OUTCOMES: tuple[tuple[str, str, str], ...] = (
    # Suppressed (ledger / pair).
    (
        FAILURE_KIND_LEDGER_AMBIGUOUS_SEND,
        RETRY_OUTCOME_SUPPRESSED,
        TERMINAL_REASON_SUPPRESSED_AMBIGUOUS,
    ),
    (
        FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL,
        RETRY_OUTCOME_SUPPRESSED,
        TERMINAL_REASON_SUPPRESSED_DUPLICATE,
    ),
    (
        FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
        RETRY_OUTCOME_SUPPRESSED,
        TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    ),
    (
        FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
        RETRY_OUTCOME_SUPPRESSED,
        TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    ),
    (
        FAILURE_KIND_USDC_OBSERVE_ONLY,
        RETRY_OUTCOME_SUPPRESSED,
        TERMINAL_REASON_SUPPRESSED_NOT_ELIGIBLE,
    ),
    # Operator review (auth / config / unknown).
    (
        FAILURE_KIND_PROVIDER_AUTH_FAILED,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    ),
    (
        FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    ),
    (
        FAILURE_KIND_CONFIG_NOT_READY,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    ),
    (
        FAILURE_KIND_CONFIG_CONFLICT,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        TERMINAL_REASON_OPERATOR_REVIEW_REQUIRED,
    ),
    (
        FAILURE_KIND_UNKNOWN_FAILURE,
        RETRY_OUTCOME_OPERATOR_REVIEW_REQUIRED,
        TERMINAL_REASON_UNKNOWN_FAILURE,
    ),
    # Fail closed (artifact / ledger write / price).
    (
        FAILURE_KIND_ARTIFACT_WRITE_FAILED,
        RETRY_OUTCOME_FAIL_CLOSED,
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    ),
    (
        FAILURE_KIND_ARTIFACT_READ_FAILED,
        RETRY_OUTCOME_FAIL_CLOSED,
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    ),
    (
        FAILURE_KIND_LEDGER_WRITE_FAILED,
        RETRY_OUTCOME_FAIL_CLOSED,
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    ),
    (
        FAILURE_KIND_PRICE_STALE,
        RETRY_OUTCOME_FAIL_CLOSED,
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    ),
    (
        FAILURE_KIND_PRICE_MISSING,
        RETRY_OUTCOME_FAIL_CLOSED,
        TERMINAL_REASON_FAIL_CLOSED_BY_CLASSIFICATION,
    ),
    # Stop session (severe).
    (
        FAILURE_KIND_LEDGER_REPLAY_FAILED,
        RETRY_OUTCOME_STOP_SESSION,
        TERMINAL_REASON_LEDGER_REPLAY_FAILED,
    ),
    (
        FAILURE_KIND_SECRET_REDACTION_VIOLATION,
        RETRY_OUTCOME_STOP_SESSION,
        TERMINAL_REASON_SECRET_REDACTION_VIOLATION,
    ),
    (
        FAILURE_KIND_INTERNAL_INVARIANT_BROKEN,
        RETRY_OUTCOME_STOP_SESSION,
        TERMINAL_REASON_INTERNAL_INVARIANT_BROKEN,
    ),
    (
        FAILURE_KIND_OPERATOR_SHUTDOWN,
        RETRY_OUTCOME_STOP_SESSION,
        TERMINAL_REASON_OPERATOR_SHUTDOWN,
    ),
    # No-retry-terminal.
    (
        FAILURE_KIND_PROVIDER_MALFORMED_EVENT,
        RETRY_OUTCOME_NO_RETRY_TERMINAL,
        TERMINAL_REASON_NO_RETRY_TERMINAL,
    ),
    (
        FAILURE_KIND_MALFORMED_EVENT,
        RETRY_OUTCOME_NO_RETRY_TERMINAL,
        TERMINAL_REASON_NO_RETRY_TERMINAL,
    ),
    (
        FAILURE_KIND_RETRY_BUDGET_EXHAUSTED,
        RETRY_OUTCOME_NO_RETRY_TERMINAL,
        TERMINAL_REASON_NO_RETRY_TERMINAL,
    ),
)


@pytest.mark.parametrize(
    "failure_kind,expected_outcome,expected_terminal",
    _NONRETRYABLE_KIND_OUTCOMES,
)
def test_nonretryable_kind_maps_to_expected_outcome(
    failure_kind: str,
    expected_outcome: str,
    expected_terminal: str,
):
    decision = decide_retry(_input(failure_kind))
    assert decision.retry_outcome == expected_outcome
    assert decision.retry_allowed is False
    assert decision.delay_seconds is None
    assert decision.next_attempt_index is None
    assert decision.dispatch_allowed is False
    assert (
        decision.terminal_reason_if_exhausted == expected_terminal
    )
    assert decision.safe_reason_code == expected_outcome.lower()
    assert decision.redaction_status == REDACTION_STATUS_APPLIED


def test_every_failure_kind_is_covered_by_a_test_case():
    retryable_kinds = {k for (k, _, _) in _RETRYABLE_KINDS_WITH_PROFILE}
    nonretryable_kinds = {k for (k, _, _) in _NONRETRYABLE_KIND_OUTCOMES}
    covered = retryable_kinds | nonretryable_kinds
    assert covered == set(FAILURE_KIND_VALUES), (
        f"Stage 28.3b retry-policy test set must cover every "
        f"closed-set Stage 28.3a failure kind. Missing: "
        f"{set(FAILURE_KIND_VALUES) - covered!r}; extras: "
        f"{covered - set(FAILURE_KIND_VALUES)!r}"
    )


# ---------------------------------------------------------------------------
# 6. Discord 429 + retry-after handling
# ---------------------------------------------------------------------------


def test_discord_429_uses_retry_after_int_when_present():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=7,
        )
    )
    assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED
    assert decision.delay_seconds == 7.0


def test_discord_429_uses_retry_after_float_when_present():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=3.5,
        )
    )
    assert decision.delay_seconds == 3.5


def test_discord_429_caps_huge_retry_after_to_locked_max():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=10000.0,
        )
    )
    assert decision.delay_seconds == RETRY_AFTER_MAX_SECONDS


def test_discord_429_falls_back_to_default_when_hint_missing():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=None,
        )
    )
    assert decision.delay_seconds == RETRY_AFTER_DEFAULT_SECONDS


def test_discord_429_falls_back_to_profile_delay_when_hint_invalid():
    # Negative input -> parser returns None -> policy falls back to
    # the profile's scheduled delay (NOT the missing-hint default).
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=-5.0,
        )
    )
    expected_profile_delay = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
    ].delay_schedule_seconds[0]
    assert decision.delay_seconds == expected_profile_delay


# ---------------------------------------------------------------------------
# 7. parse_retry_after_seconds (pure parser)
# ---------------------------------------------------------------------------


def test_parse_retry_after_seconds_none_returns_none():
    assert parse_retry_after_seconds(None) is None


def test_parse_retry_after_seconds_int_clamped_within_range():
    assert parse_retry_after_seconds(0) == 0.0
    assert parse_retry_after_seconds(10) == 10.0


def test_parse_retry_after_seconds_int_capped_to_max():
    assert (
        parse_retry_after_seconds(10000)
        == RETRY_AFTER_MAX_SECONDS
    )


def test_parse_retry_after_seconds_float_accepted_when_finite():
    assert parse_retry_after_seconds(3.5) == 3.5


def test_parse_retry_after_seconds_float_capped_to_max():
    assert (
        parse_retry_after_seconds(99.9)
        == RETRY_AFTER_MAX_SECONDS
    )


def test_parse_retry_after_seconds_floor_to_min():
    # Stage 28.3b floor is 0.0; anything below that is rejected
    # via the negative-input rule.
    assert parse_retry_after_seconds(0.0) == RETRY_AFTER_MIN_SECONDS


def test_parse_retry_after_seconds_negative_rejected():
    assert parse_retry_after_seconds(-1) is None
    assert parse_retry_after_seconds(-0.001) is None


def test_parse_retry_after_seconds_nan_rejected():
    assert parse_retry_after_seconds(float("nan")) is None


def test_parse_retry_after_seconds_infinite_rejected():
    assert parse_retry_after_seconds(float("inf")) is None
    assert parse_retry_after_seconds(float("-inf")) is None


def test_parse_retry_after_seconds_bool_rejected():
    assert parse_retry_after_seconds(True) is None
    assert parse_retry_after_seconds(False) is None


def test_parse_retry_after_seconds_numeric_string_accepted_and_capped():
    assert parse_retry_after_seconds("5") == 5.0
    assert parse_retry_after_seconds("3.5") == 3.5
    assert (
        parse_retry_after_seconds("9999.0")
        == RETRY_AFTER_MAX_SECONDS
    )


def test_parse_retry_after_seconds_string_with_whitespace():
    assert parse_retry_after_seconds("  4  ") == 4.0


def test_parse_retry_after_seconds_nonnumeric_string_rejected():
    assert parse_retry_after_seconds("soon") is None
    assert parse_retry_after_seconds("") is None
    assert parse_retry_after_seconds("   ") is None


def test_parse_retry_after_seconds_negative_string_rejected():
    assert parse_retry_after_seconds("-3") is None


def test_parse_retry_after_seconds_other_types_rejected():
    assert parse_retry_after_seconds([1]) is None
    assert parse_retry_after_seconds({"x": 1}) is None
    assert parse_retry_after_seconds(b"5") is None


def test_parse_retry_after_seconds_never_exceeds_cap():
    for v in (1, 5, 30, 1000, 1e9, "60", "1e9"):
        parsed = parse_retry_after_seconds(v)
        if parsed is not None:
            assert parsed <= RETRY_AFTER_MAX_SECONDS
            assert parsed >= RETRY_AFTER_MIN_SECONDS


# ---------------------------------------------------------------------------
# 8. Purity: same input -> same output
# ---------------------------------------------------------------------------


def test_decide_retry_is_pure_for_each_failure_kind():
    for kind in FAILURE_KIND_VALUES:
        inp = _input(kind, attempts_already_made=0)
        a = decide_retry(inp)
        b = decide_retry(inp)
        assert a == b, (
            f"decide_retry({kind!r}) is not pure: {a!r} != {b!r}"
        )


def test_decide_retry_is_pure_on_exhaustion_path():
    inp = _input(
        FAILURE_KIND_DISCORD_RATE_LIMITED, attempts_already_made=2
    )
    a = decide_retry(inp)
    b = decide_retry(inp)
    assert a == b


def test_decide_retry_is_pure_on_global_budget_exhaustion():
    inp = _input(
        FAILURE_KIND_DISCORD_RATE_LIMITED,
        global_retries_used=5,
        global_max_retries=5,
    )
    a = decide_retry(inp)
    b = decide_retry(inp)
    assert a == b


# ---------------------------------------------------------------------------
# 9. No-dispatch invariants: dispatch never allowed for forbidden kinds
# ---------------------------------------------------------------------------


_KINDS_THAT_MUST_NEVER_DISPATCH: tuple[str, ...] = (
    FAILURE_KIND_PRICE_STALE,
    FAILURE_KIND_PRICE_MISSING,
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND,
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL,
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
    FAILURE_KIND_USDC_OBSERVE_ONLY,
    FAILURE_KIND_SECRET_REDACTION_VIOLATION,
    FAILURE_KIND_INTERNAL_INVARIANT_BROKEN,
    FAILURE_KIND_LEDGER_REPLAY_FAILED,
    FAILURE_KIND_UNKNOWN_FAILURE,
    FAILURE_KIND_CONFIG_CONFLICT,
    FAILURE_KIND_CONFIG_NOT_READY,
    FAILURE_KIND_OPERATOR_SHUTDOWN,
    FAILURE_KIND_RETRY_BUDGET_EXHAUSTED,
    FAILURE_KIND_MALFORMED_EVENT,
    FAILURE_KIND_PROVIDER_MALFORMED_EVENT,
    FAILURE_KIND_ARTIFACT_WRITE_FAILED,
    FAILURE_KIND_ARTIFACT_READ_FAILED,
    FAILURE_KIND_LEDGER_WRITE_FAILED,
    FAILURE_KIND_PROVIDER_AUTH_FAILED,
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED,
)


@pytest.mark.parametrize(
    "failure_kind", _KINDS_THAT_MUST_NEVER_DISPATCH
)
def test_forbidden_dispatch_kind_never_yields_dispatch_allowed(
    failure_kind: str,
):
    for attempts in (0, 1, 5):
        decision = decide_retry(
            _input(failure_kind, attempts_already_made=attempts)
        )
        assert decision.retry_allowed is False
        assert decision.dispatch_allowed is False
        assert decision.delay_seconds is None


# ---------------------------------------------------------------------------
# 10. Redaction: canary values never leak via decision repr/str
# ---------------------------------------------------------------------------


def test_decision_repr_does_not_leak_canaries_for_any_kind():
    for kind in FAILURE_KIND_VALUES:
        decision = decide_retry(_input(kind))
        _assert_no_canary_in(repr(decision))
        _assert_no_canary_in(str(decision))
        _assert_no_canary_in(decision.safe_reason_code)
        _assert_no_canary_in(
            decision.terminal_reason_if_exhausted
        )


def test_decision_carries_no_routing_or_signer_fields():
    forbidden_substrings = (
        "webhook" + "_url",
        "private" + "_key",
        "bearer" + "_token",
        "wallet" + "_address",
        "signer" + "_address",
        "subscriber" + "_id",
        "public" + "_channel_id",
        "paid" + "_tier",
        "approval" + "_status",
        "enforcement" + "_result",
        "trade" + "_side",
        "position" + "_size",
    )
    for kind in FAILURE_KIND_VALUES:
        decision = decide_retry(_input(kind))
        decision_repr = repr(decision)
        for needle in forbidden_substrings:
            assert needle not in decision_repr, (
                f"forbidden routing/signer substring {needle!r} "
                f"leaked into Stage 28.3b decision repr for "
                f"failure kind {kind!r}"
            )


def test_decision_safe_reason_code_is_always_closed_set():
    from PHX2.stage28.retry_policy_models import (
        SAFE_RETRY_REASON_CODE_VALUES,
    )

    for kind in FAILURE_KIND_VALUES:
        decision = decide_retry(_input(kind))
        assert (
            decision.safe_reason_code in SAFE_RETRY_REASON_CODE_VALUES
        )


def test_decision_terminal_reason_is_always_closed_set():
    from PHX2.stage28.retry_policy_models import (
        TERMINAL_REASON_VALUES,
    )

    for kind in FAILURE_KIND_VALUES:
        decision = decide_retry(_input(kind))
        assert (
            decision.terminal_reason_if_exhausted
            in TERMINAL_REASON_VALUES
        )


# ---------------------------------------------------------------------------
# 11. Provider-disconnect intermediate attempts use the profile schedule
# ---------------------------------------------------------------------------


def test_provider_reconnect_uses_profile_schedule_per_attempt():
    profile = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ]
    for attempts_already_made in range(profile.max_attempts):
        decision = decide_retry(
            _input(
                FAILURE_KIND_PROVIDER_DISCONNECTED,
                attempts_already_made=attempts_already_made,
            )
        )
        assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED
        assert decision.delay_seconds == (
            profile.delay_schedule_seconds[attempts_already_made]
        )
        assert (
            decision.next_attempt_index
            == attempts_already_made + 1
        )
        assert decision.attempts_remaining == (
            profile.max_attempts - attempts_already_made - 1
        )


def test_price_refresh_uses_profile_schedule_per_attempt():
    profile = PROFILE_REGISTRY[RETRY_PROFILE_NAME_PRICE_REFRESH]
    for attempts_already_made in range(profile.max_attempts):
        decision = decide_retry(
            _input(
                FAILURE_KIND_PRICE_TIMEOUT,
                attempts_already_made=attempts_already_made,
            )
        )
        assert decision.retry_outcome == RETRY_OUTCOME_ALLOWED
        assert decision.delay_seconds == (
            profile.delay_schedule_seconds[attempts_already_made]
        )


# ---------------------------------------------------------------------------
# 12. Retry-after handling with the Stage 28.3a classifier output
# ---------------------------------------------------------------------------


def test_discord_429_invalid_retry_after_nan_falls_back():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=float("nan"),
        )
    )
    expected_profile_delay = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
    ].delay_schedule_seconds[0]
    assert decision.delay_seconds == expected_profile_delay


def test_discord_429_invalid_retry_after_infinite_falls_back():
    decision = decide_retry(
        _input(
            FAILURE_KIND_DISCORD_RATE_LIMITED,
            retry_after_hint_seconds=float("inf"),
        )
    )
    expected_profile_delay = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_DISCORD_RATE_LIMITED
    ].delay_schedule_seconds[0]
    assert decision.delay_seconds == expected_profile_delay


def test_non_discord_429_kind_ignores_retry_after_hint():
    # PROVIDER_TIMEOUT should use the PROVIDER_RECONNECT profile's
    # scheduled delay, not the caller-supplied retry-after hint.
    decision = decide_retry(
        _input(
            FAILURE_KIND_PROVIDER_TIMEOUT,
            retry_after_hint_seconds=22.0,
        )
    )
    expected_profile_delay = PROFILE_REGISTRY[
        RETRY_PROFILE_NAME_PROVIDER_RECONNECT
    ].delay_schedule_seconds[0]
    assert decision.delay_seconds == expected_profile_delay


# ---------------------------------------------------------------------------
# 13. Profile name on decision matches the failure kind mapping
# ---------------------------------------------------------------------------


def test_decision_profile_name_matches_kind_mapping_for_all_kinds():
    for kind in FAILURE_KIND_VALUES:
        decision = decide_retry(_input(kind))
        expected = get_profile_for_failure_kind(kind).name
        assert decision.profile_name == expected, (
            f"failure kind {kind!r}: decision profile_name "
            f"{decision.profile_name!r} != expected {expected!r}"
        )
