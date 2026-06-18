"""Stage 30.13.0 auto-seed models tests.

Offline / pure only. Pins the pump-suffix predicate, the bounded seed-cap predicate,
the closed-set seed-decision / seed-reason vocabularies + validators, the redaction
status tokens, the safe-echo / non-blank predicates, and the passive dataclass field
shapes.
"""

from __future__ import annotations

from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_DECISION_ACCEPTED,
    SEED_DECISION_DUPLICATE,
    SEED_DECISION_ERROR,
    SEED_DECISION_REJECTED,
    SEED_REASON_DUPLICATE_MINT,
    SEED_REASON_INCOMPLETE_EVIDENCE,
    SEED_REASON_NOT_A_RECORD,
    SEED_REASON_NOT_PRESENT_MIGRATION,
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_WS_CAPTURE_FAILED,
    STAGE30_13_DEFAULT_MAX_SEED,
    STAGE30_13_MAX_SEED_HARD_CAP,
    STAGE30_13_PUMP_MINT_SUFFIX,
    STAGE30_13_SEED_ACCEPT_DECISION,
    STAGE30_13_SEED_ACCEPT_REASON,
    STAGE30_13_SEED_DECISIONS,
    STAGE30_13_SEED_REASONS,
    STAGE30_13_REDACTION_STATUS_REDACTED,
    STAGE30_13_REDACTION_STATUS_VIOLATION,
    STAGE30_13_REDACTION_STATUSES,
    auto_seed_result_field_names,
    is_nonblank_str,
    is_pump_suffix_mint,
    is_safe_echo_id,
    is_seed_decision,
    is_seed_reason,
    is_within_seed_cap,
    seed_outcome_field_names,
    seed_summary_field_names,
)


_PUMP_MINT = "A" * 40 + "pump"   # 44 chars, safe shape, pump suffix
_NON_PUMP_MINT = "A" * 44        # 44 chars, no pump suffix


# ---------------------------------------------------------------------------
# is_pump_suffix_mint
# ---------------------------------------------------------------------------


def test_pump_suffix_accepts_safe_pump_mint() -> None:
    assert is_pump_suffix_mint(_PUMP_MINT) is True


def test_pump_suffix_rejects_non_pump_mint() -> None:
    assert is_pump_suffix_mint(_NON_PUMP_MINT) is False


def test_pump_suffix_rejects_too_short() -> None:
    # 24 chars (< 32), even though it ends with "pump".
    assert is_pump_suffix_mint("A" * 20 + "pump") is False


def test_pump_suffix_rejects_too_long() -> None:
    # 65 chars (> 64), even though it ends with "pump".
    assert is_pump_suffix_mint("A" * 61 + "pump") is False


def test_pump_suffix_rejects_whitespace() -> None:
    assert is_pump_suffix_mint("A" * 39 + " pump") is False


def test_pump_suffix_rejects_non_string() -> None:
    assert is_pump_suffix_mint(None) is False
    assert is_pump_suffix_mint(12345) is False
    assert is_pump_suffix_mint(b"x" * 40 + b"pump") is False


def test_pump_suffix_constant_is_literal_pump() -> None:
    assert STAGE30_13_PUMP_MINT_SUFFIX == "pump"


# ---------------------------------------------------------------------------
# is_within_seed_cap
# ---------------------------------------------------------------------------


def test_seed_cap_accepts_one_through_hard_cap() -> None:
    assert is_within_seed_cap(1) is True
    assert is_within_seed_cap(STAGE30_13_MAX_SEED_HARD_CAP) is True


def test_seed_cap_rejects_zero_and_over_cap() -> None:
    assert is_within_seed_cap(0) is False
    assert is_within_seed_cap(STAGE30_13_MAX_SEED_HARD_CAP + 1) is False


def test_seed_cap_rejects_bool_and_non_int() -> None:
    assert is_within_seed_cap(True) is False
    assert is_within_seed_cap(False) is False
    assert is_within_seed_cap("5") is False
    assert is_within_seed_cap(5.0) is False


def test_seed_cap_constants_match_ceiling() -> None:
    assert STAGE30_13_MAX_SEED_HARD_CAP == 10
    assert STAGE30_13_DEFAULT_MAX_SEED == 10


# ---------------------------------------------------------------------------
# Closed-set decisions / reasons
# ---------------------------------------------------------------------------


def test_seed_decisions_are_the_four_counts() -> None:
    assert STAGE30_13_SEED_DECISIONS == (
        SEED_DECISION_ACCEPTED,
        SEED_DECISION_REJECTED,
        SEED_DECISION_DUPLICATE,
        SEED_DECISION_ERROR,
    )


def test_seed_reasons_are_the_closed_set() -> None:
    assert STAGE30_13_SEED_REASONS == (
        SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
        SEED_REASON_NOT_PRESENT_MIGRATION,
        SEED_REASON_NOT_PUMP_SUFFIX,
        SEED_REASON_INCOMPLETE_EVIDENCE,
        SEED_REASON_DUPLICATE_MINT,
        SEED_REASON_WS_CAPTURE_FAILED,
        SEED_REASON_NOT_A_RECORD,
    )


def test_accept_decision_and_reason_are_the_single_seed_tokens() -> None:
    assert STAGE30_13_SEED_ACCEPT_DECISION == SEED_DECISION_ACCEPTED
    assert STAGE30_13_SEED_ACCEPT_REASON == SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION


def test_is_seed_decision_validator() -> None:
    for token in STAGE30_13_SEED_DECISIONS:
        assert is_seed_decision(token) is True
    assert is_seed_decision("NOPE") is False
    assert is_seed_decision(None) is False


def test_is_seed_reason_validator() -> None:
    for token in STAGE30_13_SEED_REASONS:
        assert is_seed_reason(token) is True
    assert is_seed_reason("NOPE") is False
    assert is_seed_reason(None) is False


def test_redaction_statuses_closed_set() -> None:
    assert STAGE30_13_REDACTION_STATUSES == (
        STAGE30_13_REDACTION_STATUS_REDACTED,
        STAGE30_13_REDACTION_STATUS_VIOLATION,
    )


# ---------------------------------------------------------------------------
# Safe-shape predicates
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x") is True
    assert is_nonblank_str("") is False
    assert is_nonblank_str("   ") is False
    assert is_nonblank_str(None) is False


def test_is_safe_echo_id() -> None:
    assert is_safe_echo_id(_PUMP_MINT) is True
    assert is_safe_echo_id("candidate_000001") is True
    assert is_safe_echo_id("a-b-c") is True
    assert is_safe_echo_id("") is False
    assert is_safe_echo_id("has space") is False
    assert is_safe_echo_id("has/slash") is False
    assert is_safe_echo_id("x" * 129) is False
    assert is_safe_echo_id(None) is False


# ---------------------------------------------------------------------------
# Passive dataclass field shapes
# ---------------------------------------------------------------------------


def test_seed_outcome_fields() -> None:
    assert seed_outcome_field_names() == (
        "token_mint",
        "seed_decision",
        "seed_reason",
        "created_at_utc",
    )


def test_seed_summary_fields_carry_the_four_counts() -> None:
    assert seed_summary_field_names() == (
        "records_seen",
        "accepted",
        "rejected",
        "duplicate",
        "error",
        "created_at_utc",
    )


def test_auto_seed_result_fields() -> None:
    assert auto_seed_result_field_names() == (
        "outcomes",
        "seeded_summaries",
        "summary",
        "redaction_status",
        "created_at_utc",
    )
