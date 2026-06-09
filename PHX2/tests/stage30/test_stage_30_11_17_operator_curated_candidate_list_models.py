"""Stage 30.11.17 operator-curated compose session model tests.

Pure / offline. Proves the passive model layer: the schema identity, the bounded
caps, the closed-set per-entry outcome / stop-reason / redaction vocabularies, the
pure safe-shape predicates, the cap validator + default config builder, the
immutable carriers + their field names. No live call, no env read, no I/O.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_DISPATCHED,
    ENTRY_OUTCOME_ERROR,
    ENTRY_OUTCOME_REJECTED,
    STAGE30_11_17_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_17_ENTRY_OUTCOMES,
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_17_MINOR_VERSION,
    STAGE30_11_17_REDACTED_UNSAFE_ID,
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STAGE30_11_17_REDACTION_STATUS_VIOLATION,
    STAGE30_11_17_REDACTION_STATUSES,
    STAGE30_11_17_SESSION_SCHEMA_VERSION,
    STAGE30_11_17_SOURCE_STAGE,
    STAGE30_11_17_STOP_REASONS,
    STOP_REASON_CANDIDATE_CAP,
    STOP_REASON_COMPLETED,
    STOP_REASON_COMPOSITION_CAP,
    Stage30_11_17OperatorCuratedCandidate,
    Stage30_11_17SessionConfig,
    Stage30_11_17SessionEvent,
    Stage30_11_17SessionResult,
    default_session_config,
    is_entry_outcome,
    is_nonblank_str,
    is_safe_echo_id,
    is_stop_reason,
    is_within_session_caps,
    operator_curated_candidate_field_names,
    session_config_field_names,
    session_event_field_names,
    session_result_field_names,
)


# ---------------------------------------------------------------------------
# 1. Schema identity + caps
# ---------------------------------------------------------------------------


def test_minor_version_and_schema_identity() -> None:
    assert STAGE30_11_17_MINOR_VERSION == "30.11.17"
    assert STAGE30_11_17_SESSION_SCHEMA_VERSION == (
        "stage30_11_17_v0_operator_curated_compose_session"
    )
    assert STAGE30_11_17_SOURCE_STAGE == "30.11.17"


def test_caps_pinned_and_mirror_committed_runner_ceiling() -> None:
    assert STAGE30_11_17_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_17_DEFAULT_MAX_CANDIDATES == 10


# ---------------------------------------------------------------------------
# 2. Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_entry_outcomes_closed_set() -> None:
    assert STAGE30_11_17_ENTRY_OUTCOMES == (
        ENTRY_OUTCOME_DISPATCHED,
        ENTRY_OUTCOME_REJECTED,
        ENTRY_OUTCOME_DEDUPE_BLOCKED,
        ENTRY_OUTCOME_ERROR,
    )
    assert STAGE30_11_17_ENTRY_OUTCOMES == (
        "DISPATCHED",
        "REJECTED",
        "DEDUPE_BLOCKED",
        "ERROR",
    )
    for outcome in STAGE30_11_17_ENTRY_OUTCOMES:
        assert is_entry_outcome(outcome)
    assert not is_entry_outcome("SENT")
    assert not is_entry_outcome(None)


def test_stop_reasons_closed_set() -> None:
    assert STAGE30_11_17_STOP_REASONS == (
        STOP_REASON_COMPLETED,
        STOP_REASON_CANDIDATE_CAP,
        STOP_REASON_COMPOSITION_CAP,
    )
    for reason in STAGE30_11_17_STOP_REASONS:
        assert is_stop_reason(reason)
    assert not is_stop_reason("STOPPED_BY_TIMEOUT")
    assert not is_stop_reason(123)


def test_redaction_status_tokens() -> None:
    assert STAGE30_11_17_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_17_REDACTION_STATUS_VIOLATION == "REDACTION_VIOLATION"
    assert STAGE30_11_17_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_17_REDACTED_UNSAFE_ID == "REDACTED_UNSAFE_ID"


# ---------------------------------------------------------------------------
# 3. Safe-shape predicates
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x")
    assert not is_nonblank_str("")
    assert not is_nonblank_str("   ")
    assert not is_nonblank_str(None)
    assert not is_nonblank_str(5)


def test_is_safe_echo_id_accepts_ids_rejects_unsafe() -> None:
    assert is_safe_echo_id("Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe")
    assert is_safe_echo_id("stage30_11_17_cand-1")
    assert is_safe_echo_id("DIP_WATCH_1")
    # Unsafe: whitespace / url / path / quote / control / over-long.
    assert not is_safe_echo_id("dip watch")
    assert not is_safe_echo_id("a/b")
    assert not is_safe_echo_id("x" * 129)
    assert not is_safe_echo_id("")
    assert not is_safe_echo_id(None)


# ---------------------------------------------------------------------------
# 4. Cap validator + default config
# ---------------------------------------------------------------------------


def _config(max_candidates: int, max_compositions: int):
    return Stage30_11_17SessionConfig(
        max_candidates=max_candidates,
        max_compositions=max_compositions,
        created_at_utc="2026-06-07T07:06:40Z",
    )


def test_is_within_session_caps_accepts_valid() -> None:
    assert is_within_session_caps(_config(1, 1))
    assert is_within_session_caps(_config(10, 10))
    assert is_within_session_caps(_config(10, 3))


def test_is_within_session_caps_rejects_invalid() -> None:
    assert not is_within_session_caps(_config(0, 0))
    assert not is_within_session_caps(_config(11, 11))
    assert not is_within_session_caps(_config(5, 6))  # comp > cand
    assert not is_within_session_caps(_config(5, 0))  # comp < 1
    # bool caps are not budgets.
    assert not is_within_session_caps(
        Stage30_11_17SessionConfig(
            max_candidates=True, max_compositions=1, created_at_utc="x"
        )
    )
    # blank timestamp fails closed.
    assert not is_within_session_caps(
        Stage30_11_17SessionConfig(
            max_candidates=3, max_compositions=3, created_at_utc="  "
        )
    )
    assert not is_within_session_caps(object())
    assert not is_within_session_caps(None)


def test_default_session_config() -> None:
    config = default_session_config(created_at_utc="2026-06-07T07:06:40Z")
    assert config.max_candidates == STAGE30_11_17_DEFAULT_MAX_CANDIDATES
    assert config.max_compositions == STAGE30_11_17_DEFAULT_MAX_CANDIDATES
    assert config.created_at_utc == "2026-06-07T07:06:40Z"
    assert is_within_session_caps(config)


# ---------------------------------------------------------------------------
# 5. Immutable carriers + field names
# ---------------------------------------------------------------------------


def test_candidate_carries_request_and_optional_label() -> None:
    candidate = Stage30_11_17OperatorCuratedCandidate(
        request={"token_mint": "abc"}, curated_label="DIP_1"
    )
    assert candidate.request == {"token_mint": "abc"}
    assert candidate.curated_label == "DIP_1"
    # curated_label is optional.
    bare = Stage30_11_17OperatorCuratedCandidate(request=object())
    assert bare.curated_label is None


def test_candidate_field_names() -> None:
    assert operator_curated_candidate_field_names() == ("request", "curated_label")


def test_session_config_field_names() -> None:
    assert session_config_field_names() == (
        "max_candidates",
        "max_compositions",
        "created_at_utc",
    )


def test_session_event_field_names_and_no_body_or_secret() -> None:
    names = session_event_field_names()
    assert names == (
        "index",
        "candidate_id",
        "token_mint",
        "curated_label",
        "outcome",
        "compose_decision",
        "compose_reason",
        "dedupe_verdict",
        "dedupe_reason",
        "transport_attempts",
        "body_present",
        "created_at_utc",
    )
    # The event carries no body text / url / secret field (only a body_present bool).
    for name in names:
        lower = name.lower()
        for forbidden in ("url", "secret", "webhook", "content"):
            assert forbidden not in lower
        if "body" in lower:
            assert lower == "body_present"


def test_session_result_field_names() -> None:
    assert session_result_field_names() == (
        "events",
        "candidates_seen",
        "compositions_attempted",
        "dispatched",
        "rejected",
        "dedupe_blocked",
        "errors",
        "would_send_recorded",
        "stop_reason",
        "redaction_status",
        "created_at_utc",
    )


def test_models_are_frozen() -> None:
    import dataclasses
    import pytest

    event = Stage30_11_17SessionEvent(
        index=0,
        candidate_id="c",
        token_mint="m",
        curated_label="",
        outcome=ENTRY_OUTCOME_DISPATCHED,
        compose_decision="NO_SEND_DISPATCHED",
        compose_reason="NO_SEND_DISPATCH_RECORDED",
        dedupe_verdict="DEDUPE_ALLOWED",
        dedupe_reason="DEDUPE_REASON_NEW_KEY",
        transport_attempts=1,
        body_present=True,
        created_at_utc="2026-06-07T07:06:40Z",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.outcome = "REJECTED"  # type: ignore[misc]

    result = Stage30_11_17SessionResult(
        events=(event,),
        candidates_seen=1,
        compositions_attempted=1,
        dispatched=1,
        rejected=0,
        dedupe_blocked=0,
        errors=0,
        would_send_recorded=1,
        stop_reason=STOP_REASON_COMPLETED,
        redaction_status=STAGE30_11_17_REDACTION_STATUS_REDACTED,
        created_at_utc="2026-06-07T07:06:40Z",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.dispatched = 2  # type: ignore[misc]
