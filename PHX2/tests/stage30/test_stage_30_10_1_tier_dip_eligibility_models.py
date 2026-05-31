"""Stage 30.10.1 compact tier-dip eligibility models tests.

Covers the immutable / frozen policy + input + record models, the closed-set
decision / reason / tier-code vocabularies + their predicates, the explicit
display-token normalization (no fuzzy matching), the ``PRESENT`` status
tokens, the caller-injected ``created_at_utc`` safe-shape validation, the
policy validity check, that ``Decimal`` magnitudes are preserved verbatim,
and that no field carries a secret- / env- / payload-class name.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    ATH_STATUS_PRESENT,
    DECISION_ELIGIBLE_DIP,
    DECISION_INVALID_INPUT,
    DECISION_SKIPPED_MISSING_ATH,
    DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
    DECISION_SKIPPED_MISSING_MIGRATION,
    DECISION_SKIPPED_NOT_DIP,
    DECISION_SKIPPED_TIER_NOT_APPLICABLE,
    DECISION_SKIPPED_TIER_UNKNOWN,
    DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY,
    MARKET_CONTEXT_STATUS_PRESENT,
    MIGRATION_STATUS_PRESENT,
    REASON_INVALID_CANDIDATE_ID,
    REASON_INVALID_CREATED_AT_UTC,
    REASON_INVALID_POLICY,
    REASON_INVALID_TOKEN_MINT,
    REASON_MISSING_ATH,
    REASON_MISSING_CURRENT_MARKET_CAP,
    REASON_MISSING_DRAWDOWN,
    REASON_MISSING_MARKET_CONTEXT,
    REASON_MISSING_MIGRATION,
    REASON_PRE_MIGRATION_ATH_NOT_ALLOWED,
    REASON_TIER_ALLOWED,
    REASON_TIER_NOT_ALLOWED,
    REASON_TIER_NOT_APPLICABLE,
    REASON_TIER_UNKNOWN,
    STAGE30_10_1_ALLOWED_TIER_CODES,
    STAGE30_10_1_ELIGIBILITY_DECISIONS,
    STAGE30_10_1_ELIGIBILITY_REASONS,
    STAGE30_10_1_MINOR_VERSION,
    STAGE30_10_1_SEND_ALLOWED_DECISION,
    STAGE30_10_1_TIER_CODE_VALUES,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
    Stage30_10DipEligibilityRecord,
    TIER_CODE_TIER_1,
    TIER_CODE_TIER_2,
    TIER_CODE_TIER_3,
    TIER_CODE_TIER_NOT_APPLICABLE,
    TIER_CODE_TIER_UNKNOWN,
    input_field_names,
    is_eligibility_decision,
    is_eligibility_reason,
    is_finite_decimal,
    is_present_status,
    is_safe_created_at_utc,
    is_valid_policy,
    normalize_tier_token,
    policy_field_names,
    record_field_names,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _valid_input(**overrides) -> Stage30_10DipEligibilityInput:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10DipEligibilityInput(**base)


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_10_1_MINOR_VERSION == "30.10.1"


# ---------------------------------------------------------------------------
# 2. Default policy: Tier 1/2/3 allowed, fail-closed
# ---------------------------------------------------------------------------


def test_default_policy_is_tier_1_2_3_allowed_fail_closed() -> None:
    p = DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY
    assert p.allowed_tiers == ("TIER_1", "TIER_2", "TIER_3")
    assert p.require_post_migration_ath is True
    assert p.require_migration_present is True
    assert p.require_current_market_context is True
    assert p.fail_closed_on_unknown is True


def test_default_policy_equals_all_default_construction() -> None:
    assert DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY == (
        Stage30_10DipEligibilityPolicy()
    )
    # Every field default matches the fail-closed stance.
    assert Stage30_10DipEligibilityPolicy().allowed_tiers == (
        "TIER_1",
        "TIER_2",
        "TIER_3",
    )


# ---------------------------------------------------------------------------
# 3. Models are immutable / frozen
# ---------------------------------------------------------------------------


def test_policy_is_frozen() -> None:
    p = Stage30_10DipEligibilityPolicy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.fail_closed_on_unknown = False  # type: ignore[misc]


def test_input_is_frozen() -> None:
    record = _valid_input()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.candidate_id = "other"  # type: ignore[misc]


def test_record_is_frozen() -> None:
    rec = Stage30_10DipEligibilityRecord(
        candidate_id="c",
        token_mint="m",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("1"),
        post_migration_ath_verified=True,
        decision=DECISION_ELIGIBLE_DIP,
        reason=REASON_TIER_ALLOWED,
        send_allowed=True,
        created_at_utc=_SAFE_CREATED_AT,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.send_allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. Closed-set constants pinned
# ---------------------------------------------------------------------------


def test_eligibility_decisions_closed_set_pinned() -> None:
    assert STAGE30_10_1_ELIGIBILITY_DECISIONS == (
        DECISION_ELIGIBLE_DIP,
        DECISION_SKIPPED_NOT_DIP,
        DECISION_SKIPPED_TIER_UNKNOWN,
        DECISION_SKIPPED_TIER_NOT_APPLICABLE,
        DECISION_SKIPPED_MISSING_ATH,
        DECISION_SKIPPED_MISSING_MIGRATION,
        DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
        DECISION_INVALID_INPUT,
    )
    # The literal values are the locked Stage 30.10.0 closed set.
    assert STAGE30_10_1_ELIGIBILITY_DECISIONS == (
        "ELIGIBLE_DIP",
        "SKIPPED_NOT_DIP",
        "SKIPPED_TIER_UNKNOWN",
        "SKIPPED_TIER_NOT_APPLICABLE",
        "SKIPPED_MISSING_ATH",
        "SKIPPED_MISSING_MIGRATION",
        "SKIPPED_MISSING_MARKET_CONTEXT",
        "INVALID_INPUT",
    )
    for token in STAGE30_10_1_ELIGIBILITY_DECISIONS:
        assert is_eligibility_decision(token)
    assert not is_eligibility_decision("NOPE")
    assert not is_eligibility_decision(None)
    assert not is_eligibility_decision(123)


def test_send_allowed_decision_is_eligible_dip() -> None:
    assert STAGE30_10_1_SEND_ALLOWED_DECISION == "ELIGIBLE_DIP"
    assert STAGE30_10_1_SEND_ALLOWED_DECISION == DECISION_ELIGIBLE_DIP


def test_eligibility_reasons_closed_set_pinned() -> None:
    assert STAGE30_10_1_ELIGIBILITY_REASONS == (
        REASON_TIER_ALLOWED,
        REASON_TIER_NOT_ALLOWED,
        REASON_TIER_UNKNOWN,
        REASON_TIER_NOT_APPLICABLE,
        REASON_MISSING_ATH,
        REASON_MISSING_MIGRATION,
        REASON_MISSING_DRAWDOWN,
        REASON_MISSING_MARKET_CONTEXT,
        REASON_MISSING_CURRENT_MARKET_CAP,
        REASON_PRE_MIGRATION_ATH_NOT_ALLOWED,
        REASON_INVALID_CANDIDATE_ID,
        REASON_INVALID_TOKEN_MINT,
        REASON_INVALID_CREATED_AT_UTC,
        REASON_INVALID_POLICY,
    )
    assert STAGE30_10_1_ELIGIBILITY_REASONS == (
        "TIER_ALLOWED",
        "TIER_NOT_ALLOWED",
        "TIER_UNKNOWN",
        "TIER_NOT_APPLICABLE",
        "MISSING_ATH",
        "MISSING_MIGRATION",
        "MISSING_DRAWDOWN",
        "MISSING_MARKET_CONTEXT",
        "MISSING_CURRENT_MARKET_CAP",
        "PRE_MIGRATION_ATH_NOT_ALLOWED",
        "INVALID_CANDIDATE_ID",
        "INVALID_TOKEN_MINT",
        "INVALID_CREATED_AT_UTC",
        "INVALID_POLICY",
    )
    for token in STAGE30_10_1_ELIGIBILITY_REASONS:
        assert is_eligibility_reason(token)
    assert not is_eligibility_reason("NOPE")
    assert not is_eligibility_reason(None)


def test_tier_codes_pinned() -> None:
    assert STAGE30_10_1_TIER_CODE_VALUES == (
        "TIER_1",
        "TIER_2",
        "TIER_3",
        "TIER_UNKNOWN",
        "TIER_NOT_APPLICABLE",
    )
    assert STAGE30_10_1_ALLOWED_TIER_CODES == ("TIER_1", "TIER_2", "TIER_3")
    # The allowable codes never include the suppressed tiers.
    assert TIER_CODE_TIER_UNKNOWN not in STAGE30_10_1_ALLOWED_TIER_CODES
    assert TIER_CODE_TIER_NOT_APPLICABLE not in STAGE30_10_1_ALLOWED_TIER_CODES


# ---------------------------------------------------------------------------
# 5. Normalization (no fuzzy matching)
# ---------------------------------------------------------------------------


def test_normalize_display_tokens() -> None:
    assert normalize_tier_token("Tier 1") == TIER_CODE_TIER_1
    assert normalize_tier_token("Tier 2") == TIER_CODE_TIER_2
    assert normalize_tier_token("Tier 3") == TIER_CODE_TIER_3
    assert normalize_tier_token("Tier Unknown") == TIER_CODE_TIER_UNKNOWN
    assert (
        normalize_tier_token("Tier Not Applicable")
        == TIER_CODE_TIER_NOT_APPLICABLE
    )


def test_normalize_already_normalized_codes_pass_through() -> None:
    assert normalize_tier_token("TIER_1") == TIER_CODE_TIER_1
    assert normalize_tier_token("TIER_2") == TIER_CODE_TIER_2
    assert normalize_tier_token("TIER_3") == TIER_CODE_TIER_3
    assert normalize_tier_token("TIER_UNKNOWN") == TIER_CODE_TIER_UNKNOWN
    assert (
        normalize_tier_token("TIER_NOT_APPLICABLE")
        == TIER_CODE_TIER_NOT_APPLICABLE
    )


def test_normalize_unrecognized_is_none_no_fuzzy() -> None:
    # Unrecognized / near-miss / non-string tokens are NEVER silently
    # coerced; they normalize to None (the classifier fails closed on them).
    for value in (
        None,
        "",
        "  ",
        "tier 1",
        "TIER1",
        "T1",
        "Tier 4",
        "Tier-1",
        "garbage",
        123,
        object(),
    ):
        assert normalize_tier_token(value) is None


# ---------------------------------------------------------------------------
# 6. Status tokens + present check
# ---------------------------------------------------------------------------


def test_present_status_tokens_are_present() -> None:
    assert MIGRATION_STATUS_PRESENT == "PRESENT"
    assert ATH_STATUS_PRESENT == "PRESENT"
    assert MARKET_CONTEXT_STATUS_PRESENT == "PRESENT"


def test_is_present_status() -> None:
    assert is_present_status("PRESENT", MIGRATION_STATUS_PRESENT)
    assert not is_present_status("MISSING", MIGRATION_STATUS_PRESENT)
    assert not is_present_status(None, ATH_STATUS_PRESENT)
    assert not is_present_status(123, ATH_STATUS_PRESENT)
    assert not is_present_status("", MARKET_CONTEXT_STATUS_PRESENT)


def test_is_finite_decimal() -> None:
    # Finite Decimals (incl. signed / zero) are accepted.
    for value in (
        Decimal("0.50"),
        Decimal("-0.50"),
        Decimal("0"),
        Decimal("0.0"),
        Decimal("123456.789"),
    ):
        assert is_finite_decimal(value)
    # Missing / non-Decimal / non-finite values are rejected (no float
    # coercion; Python does not enforce type annotations at runtime).
    for value in (
        None,
        "0.55",
        0.55,
        0,
        object(),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ):
        assert not is_finite_decimal(value)


# ---------------------------------------------------------------------------
# 7. created_at_utc safe-shape validation
# ---------------------------------------------------------------------------


def test_is_safe_created_at_utc() -> None:
    assert is_safe_created_at_utc("2026-01-01T00:00:00Z")
    assert is_safe_created_at_utc("2026-05-31T23:59:59.123456Z")
    # Rejected: blank, missing Z, naive, non-string, garbage / URL-shape.
    assert not is_safe_created_at_utc("")
    assert not is_safe_created_at_utc("   ")
    assert not is_safe_created_at_utc("2026-01-01T00:00:00")
    assert not is_safe_created_at_utc("2026-01-01 00:00:00Z")
    assert not is_safe_created_at_utc("not-a-timestamp")
    assert not is_safe_created_at_utc(None)
    assert not is_safe_created_at_utc(1234567890)


# ---------------------------------------------------------------------------
# 8. Policy validity
# ---------------------------------------------------------------------------


def test_is_valid_policy_accepts_default_and_subsets() -> None:
    assert is_valid_policy(DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY)
    assert is_valid_policy(Stage30_10DipEligibilityPolicy())
    assert is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_1",))
    )
    assert is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=())
    )


def test_is_valid_policy_rejects_bad_policies() -> None:
    # Wrong type.
    assert not is_valid_policy(None)
    assert not is_valid_policy("policy")
    assert not is_valid_policy(object())
    # allowed_tiers carrying a non-in-band / unknown code.
    assert not is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_9",))
    )
    assert not is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_UNKNOWN",))
    )
    assert not is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=("Tier 1",))
    )
    # allowed_tiers not a tuple.
    assert not is_valid_policy(
        Stage30_10DipEligibilityPolicy(allowed_tiers=["TIER_1"])  # type: ignore[arg-type]
    )
    # Non-bool axis.
    assert not is_valid_policy(
        Stage30_10DipEligibilityPolicy(require_migration_present="yes")  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 9. Decimal values preserved verbatim
# ---------------------------------------------------------------------------


def test_decimal_values_preserved_safely() -> None:
    dd = Decimal("0.847")
    mc = Decimal("987654.3210")
    record = _valid_input(drawdown_from_ath=dd, current_market_cap_usd=mc)
    # Identity / equality preserved; no float coercion.
    assert record.drawdown_from_ath == dd
    assert isinstance(record.drawdown_from_ath, Decimal)
    assert record.current_market_cap_usd == mc
    assert isinstance(record.current_market_cap_usd, Decimal)
    # Canonical text round-trips byte-exactly (no rounding).
    assert format(record.drawdown_from_ath, "f") == "0.847"
    assert format(record.current_market_cap_usd, "f") == "987654.3210"


# ---------------------------------------------------------------------------
# 10. Field-name helpers + no secret / env / payload field names
# ---------------------------------------------------------------------------


def test_field_name_helpers_pinned() -> None:
    assert policy_field_names() == (
        "allowed_tiers",
        "require_post_migration_ath",
        "require_migration_present",
        "require_current_market_context",
        "fail_closed_on_unknown",
    )
    assert input_field_names() == (
        "candidate_id",
        "token_mint",
        "tier_token",
        "drawdown_from_ath",
        "migration_status",
        "ath_status",
        "market_context_status",
        "current_market_cap_usd",
        "post_migration_ath_verified",
        "created_at_utc",
    )
    assert record_field_names() == (
        "candidate_id",
        "token_mint",
        "tier_token",
        "drawdown_from_ath",
        "migration_status",
        "ath_status",
        "market_context_status",
        "current_market_cap_usd",
        "post_migration_ath_verified",
        "decision",
        "reason",
        "send_allowed",
        "created_at_utc",
    )


_FORBIDDEN_FIELD_SUBSTRINGS = (
    "webhook",
    "api_key",
    "apikey",
    "bearer",
    "authorization",
    "secret",
    "password",
    "private_key",
    "privatekey",
    "mnemonic",
    "seed_phrase",
    "credential",
    "raw_payload",
    "payload",
    "getenv",
    "environ",
)


def test_no_secret_or_env_field_names() -> None:
    all_fields = (
        policy_field_names() + input_field_names() + record_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in _FORBIDDEN_FIELD_SUBSTRINGS:
            assert forbidden not in lower, (
                f"Stage 30.10.1 model field {name!r} carries a forbidden "
                f"secret / env / payload substring {forbidden!r}"
            )
