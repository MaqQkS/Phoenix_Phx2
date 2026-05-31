"""Stage 30.10.1 compact tier-dip eligibility classifier tests.

Proves the pure offline classifier is dip-focused and fail-closed:

  * Tier 1 / Tier 2 / Tier 3 (with every required signal present) are the
    ONLY eligible candidates;
  * Tier Unknown / Tier Not Applicable / missing ATH / missing migration /
    missing market context / missing-or-non-positive current MC / missing
    drawdown / pre-migration ATH / a policy-excluded tier / an unrecognized
    tier are all suppressed (no send);
  * a blank candidate id / token mint, an unsafe created_at_utc, and an
    invalid policy are all classified INVALID_INPUT (no send);
  * the display ``Tier N`` tokens and the already-normalized ``TIER_N``
    codes classify identically;
  * NO candidate with a missing / degraded / unrecognized signal can ever
    become ELIGIBLE_DIP; and
  * the classifier is pure / deterministic and emits only closed-set tokens.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier import (
    Stage30_10DipEligibilityError,
    classify_tier_dip_eligibility,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DECISION_ELIGIBLE_DIP,
    DECISION_INVALID_INPUT,
    DECISION_SKIPPED_MISSING_ATH,
    DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
    DECISION_SKIPPED_MISSING_MIGRATION,
    DECISION_SKIPPED_NOT_DIP,
    DECISION_SKIPPED_TIER_NOT_APPLICABLE,
    DECISION_SKIPPED_TIER_UNKNOWN,
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
    STAGE30_10_1_ELIGIBILITY_DECISIONS,
    STAGE30_10_1_ELIGIBILITY_REASONS,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _eligible_input(**overrides) -> Stage30_10DipEligibilityInput:
    """A fully dip-eligible base input; overrides isolate one rule."""
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


def _classify(**overrides):
    return classify_tier_dip_eligibility(_eligible_input(**overrides))


# ---------------------------------------------------------------------------
# 1. Eligible: Tier 1 / Tier 2 / Tier 3
# ---------------------------------------------------------------------------


def test_tier_1_eligible() -> None:
    rec = _classify(tier_token="Tier 1")
    assert rec.decision == DECISION_ELIGIBLE_DIP
    assert rec.reason == REASON_TIER_ALLOWED
    assert rec.send_allowed is True


def test_tier_2_eligible() -> None:
    rec = _classify(tier_token="Tier 2", drawdown_from_ath=Decimal("0.70"))
    assert rec.decision == DECISION_ELIGIBLE_DIP
    assert rec.reason == REASON_TIER_ALLOWED
    assert rec.send_allowed is True


def test_tier_3_eligible() -> None:
    rec = _classify(tier_token="Tier 3", drawdown_from_ath=Decimal("0.90"))
    assert rec.decision == DECISION_ELIGIBLE_DIP
    assert rec.reason == REASON_TIER_ALLOWED
    assert rec.send_allowed is True


def test_eligible_record_echoes_input_and_clock() -> None:
    record_input = _eligible_input(
        candidate_id="cand-echo",
        token_mint="mint-echo",
        tier_token="Tier 2",
        drawdown_from_ath=Decimal("0.66"),
        current_market_cap_usd=Decimal("55555.5"),
        created_at_utc="2026-05-31T12:34:56Z",
    )
    rec = classify_tier_dip_eligibility(record_input)
    assert rec.decision == DECISION_ELIGIBLE_DIP
    assert rec.candidate_id == "cand-echo"
    assert rec.token_mint == "mint-echo"
    assert rec.tier_token == "Tier 2"
    assert rec.drawdown_from_ath == Decimal("0.66")
    assert rec.current_market_cap_usd == Decimal("55555.5")
    assert rec.migration_status == "PRESENT"
    assert rec.ath_status == "PRESENT"
    assert rec.market_context_status == "PRESENT"
    assert rec.post_migration_ath_verified is True
    # created_at_utc is the caller-injected value, echoed verbatim.
    assert rec.created_at_utc == "2026-05-31T12:34:56Z"


# ---------------------------------------------------------------------------
# 2. Suppressed tier tokens
# ---------------------------------------------------------------------------


def test_tier_unknown_suppressed() -> None:
    rec = _classify(tier_token="Tier Unknown")
    assert rec.decision == DECISION_SKIPPED_TIER_UNKNOWN
    assert rec.reason == REASON_TIER_UNKNOWN
    assert rec.send_allowed is False


def test_tier_not_applicable_suppressed() -> None:
    rec = _classify(tier_token="Tier Not Applicable")
    assert rec.decision == DECISION_SKIPPED_TIER_NOT_APPLICABLE
    assert rec.reason == REASON_TIER_NOT_APPLICABLE
    assert rec.send_allowed is False


# ---------------------------------------------------------------------------
# 3. Missing required signals suppressed
# ---------------------------------------------------------------------------


def test_missing_migration_suppressed() -> None:
    for status in ("MISSING", None, "UNTRUSTED"):
        rec = _classify(migration_status=status)
        assert rec.decision == DECISION_SKIPPED_MISSING_MIGRATION
        assert rec.reason == REASON_MISSING_MIGRATION
        assert rec.send_allowed is False


def test_missing_ath_suppressed() -> None:
    for status in ("UNAVAILABLE", None, "MISSING"):
        rec = _classify(ath_status=status)
        assert rec.decision == DECISION_SKIPPED_MISSING_ATH
        assert rec.reason == REASON_MISSING_ATH
        assert rec.send_allowed is False


def test_pre_migration_ath_suppressed_when_required() -> None:
    # ATH present, but not verified post-migration -> suppressed (require
    # _post_migration_ath defaults True).
    for verified in (False, None):
        rec = _classify(post_migration_ath_verified=verified)
        assert rec.decision == DECISION_SKIPPED_MISSING_ATH
        assert rec.reason == REASON_PRE_MIGRATION_ATH_NOT_ALLOWED
        assert rec.send_allowed is False


def test_missing_market_context_suppressed() -> None:
    for status in ("MISSING", None, "SOURCE_ERROR"):
        rec = _classify(market_context_status=status)
        assert rec.decision == DECISION_SKIPPED_MISSING_MARKET_CONTEXT
        assert rec.reason == REASON_MISSING_MARKET_CONTEXT
        assert rec.send_allowed is False


def test_missing_or_non_positive_current_mc_suppressed() -> None:
    # Market context present, but the current market cap is missing /
    # zero / negative -> suppressed with the MC-specific reason.
    for mc in (None, Decimal("0"), Decimal("-1.5")):
        rec = _classify(current_market_cap_usd=mc)
        assert rec.decision == DECISION_SKIPPED_MISSING_MARKET_CONTEXT
        assert rec.reason == REASON_MISSING_CURRENT_MARKET_CAP
        assert rec.send_allowed is False


def test_missing_drawdown_suppressed() -> None:
    # Even a Tier 1 candidate with no drawdown is not a confirmed dip.
    rec = _classify(tier_token="Tier 1", drawdown_from_ath=None)
    assert rec.decision == DECISION_SKIPPED_NOT_DIP
    assert rec.reason == REASON_MISSING_DRAWDOWN
    assert rec.send_allowed is False


def test_malformed_drawdown_suppressed() -> None:
    # Python does not enforce type annotations at runtime: a non-None but
    # malformed drawdown (non-Decimal, or a non-finite Decimal NaN / +Inf /
    # -Inf) must fail closed and can NEVER reach ELIGIBLE_DIP, even with
    # Tier 1 + every other required signal present. No float coercion.
    for bad in (
        "0.55",
        0.55,
        0,
        object(),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ):
        rec = _classify(tier_token="Tier 1", drawdown_from_ath=bad)
        assert rec.decision == DECISION_SKIPPED_NOT_DIP, (
            f"malformed drawdown {bad!r} must be SKIPPED_NOT_DIP"
        )
        assert rec.reason == REASON_MISSING_DRAWDOWN
        assert rec.send_allowed is False
        assert rec.decision != DECISION_ELIGIBLE_DIP


def test_valid_signed_and_zero_drawdown_preserved() -> None:
    # A finite Decimal drawdown is structurally valid regardless of sign /
    # zero; eligibility then hinges on the tier token. The Decimal value is
    # echoed verbatim (no float coercion).
    for dd in (Decimal("0.50"), Decimal("-0.50"), Decimal("0")):
        rec = _classify(tier_token="Tier 1", drawdown_from_ath=dd)
        assert rec.decision == DECISION_ELIGIBLE_DIP, (
            f"finite drawdown {dd!r} with Tier 1 must be ELIGIBLE_DIP"
        )
        assert rec.send_allowed is True
        assert rec.drawdown_from_ath == dd
        assert isinstance(rec.drawdown_from_ath, Decimal)
    # A structurally-valid zero drawdown still defers to the tier token: a
    # suppressed tier is suppressed even with a valid drawdown present.
    rec = _classify(tier_token="Tier Unknown", drawdown_from_ath=Decimal("0"))
    assert rec.decision == DECISION_SKIPPED_TIER_UNKNOWN
    assert rec.send_allowed is False


# ---------------------------------------------------------------------------
# 4. Policy-driven tier suppression
# ---------------------------------------------------------------------------


def test_disallowed_tier_suppressed_when_policy_excludes_it() -> None:
    policy = Stage30_10DipEligibilityPolicy(
        allowed_tiers=("TIER_1", "TIER_2")
    )
    rec = classify_tier_dip_eligibility(
        _eligible_input(tier_token="Tier 3", drawdown_from_ath=Decimal("0.9")),
        policy,
    )
    assert rec.decision == DECISION_SKIPPED_NOT_DIP
    assert rec.reason == REASON_TIER_NOT_ALLOWED
    assert rec.send_allowed is False


def test_unknown_tier_suppressed_fail_closed() -> None:
    # Default policy fails closed on an unrecognized tier.
    for token in ("garbage", "T1", "Tier 4", "tier 1"):
        rec = _classify(tier_token=token)
        assert rec.decision == DECISION_SKIPPED_TIER_UNKNOWN
        assert rec.reason == REASON_TIER_UNKNOWN
        assert rec.send_allowed is False


def test_unknown_tier_never_eligible_even_when_not_fail_closed() -> None:
    # With fail_closed_on_unknown=False the skip bucket changes but the
    # candidate is STILL never eligible (no fail-open).
    policy = Stage30_10DipEligibilityPolicy(fail_closed_on_unknown=False)
    rec = classify_tier_dip_eligibility(
        _eligible_input(tier_token="garbage"), policy
    )
    assert rec.decision == DECISION_SKIPPED_NOT_DIP
    assert rec.reason == REASON_TIER_UNKNOWN
    assert rec.send_allowed is False
    assert rec.decision != DECISION_ELIGIBLE_DIP


# ---------------------------------------------------------------------------
# 5. Invalid input
# ---------------------------------------------------------------------------


def test_blank_candidate_id_invalid() -> None:
    for cid in ("", "   "):
        rec = _classify(candidate_id=cid)
        assert rec.decision == DECISION_INVALID_INPUT
        assert rec.reason == REASON_INVALID_CANDIDATE_ID
        assert rec.send_allowed is False


def test_blank_token_mint_invalid() -> None:
    for mint in ("", "  "):
        rec = _classify(token_mint=mint)
        assert rec.decision == DECISION_INVALID_INPUT
        assert rec.reason == REASON_INVALID_TOKEN_MINT
        assert rec.send_allowed is False


def test_invalid_created_at_utc_invalid() -> None:
    for ts in ("", "not-a-time", "2026-01-01 00:00:00Z", "2026-01-01T00:00:00"):
        rec = _classify(created_at_utc=ts)
        assert rec.decision == DECISION_INVALID_INPUT
        assert rec.reason == REASON_INVALID_CREATED_AT_UTC
        assert rec.send_allowed is False


def test_invalid_policy_classified_invalid() -> None:
    bad_policy = Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_9",))
    rec = classify_tier_dip_eligibility(_eligible_input(), bad_policy)
    assert rec.decision == DECISION_INVALID_INPUT
    assert rec.reason == REASON_INVALID_POLICY
    assert rec.send_allowed is False


def test_non_input_object_raises() -> None:
    for bogus in (None, "not-an-input", 123, {"candidate_id": "c"}):
        with pytest.raises(Stage30_10DipEligibilityError):
            classify_tier_dip_eligibility(bogus)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Normalization equivalence (display vs already-normalized)
# ---------------------------------------------------------------------------


def test_display_and_normalized_tokens_classify_identically() -> None:
    for display, code in (
        ("Tier 1", "TIER_1"),
        ("Tier 2", "TIER_2"),
        ("Tier 3", "TIER_3"),
    ):
        display_rec = _classify(tier_token=display)
        code_rec = _classify(tier_token=code)
        assert display_rec.decision == DECISION_ELIGIBLE_DIP
        assert code_rec.decision == DECISION_ELIGIBLE_DIP
        assert display_rec.send_allowed is True
        assert code_rec.send_allowed is True


def test_normalized_suppressed_tokens_work() -> None:
    assert _classify(tier_token="TIER_UNKNOWN").decision == (
        DECISION_SKIPPED_TIER_UNKNOWN
    )
    assert _classify(tier_token="TIER_NOT_APPLICABLE").decision == (
        DECISION_SKIPPED_TIER_NOT_APPLICABLE
    )


# ---------------------------------------------------------------------------
# 7. No candidate with missing data can become ELIGIBLE_DIP
# ---------------------------------------------------------------------------


def test_no_missing_data_candidate_is_ever_eligible() -> None:
    degraded_overrides = (
        {"tier_token": "Tier Unknown"},
        {"tier_token": "Tier Not Applicable"},
        {"tier_token": None},
        {"tier_token": "garbage"},
        {"migration_status": None},
        {"migration_status": "MISSING"},
        {"ath_status": None},
        {"ath_status": "UNAVAILABLE"},
        {"post_migration_ath_verified": False},
        {"post_migration_ath_verified": None},
        {"market_context_status": None},
        {"market_context_status": "MISSING"},
        {"current_market_cap_usd": None},
        {"current_market_cap_usd": Decimal("0")},
        {"current_market_cap_usd": Decimal("-1")},
        {"drawdown_from_ath": None},
        {"drawdown_from_ath": "0.55"},
        {"drawdown_from_ath": 0.55},
        {"drawdown_from_ath": object()},
        {"drawdown_from_ath": Decimal("NaN")},
        {"drawdown_from_ath": Decimal("Infinity")},
        {"drawdown_from_ath": Decimal("-Infinity")},
        {"candidate_id": ""},
        {"token_mint": ""},
        {"created_at_utc": "bad"},
    )
    for overrides in degraded_overrides:
        rec = _classify(**overrides)
        assert rec.decision != DECISION_ELIGIBLE_DIP, (
            f"degraded input {overrides!r} must not be ELIGIBLE_DIP"
        )
        assert rec.send_allowed is False, (
            f"degraded input {overrides!r} must not be send-allowed"
        )


# ---------------------------------------------------------------------------
# 8. Purity + closed-set output invariants
# ---------------------------------------------------------------------------


def test_classifier_is_deterministic() -> None:
    record_input = _eligible_input()
    first = classify_tier_dip_eligibility(record_input)
    second = classify_tier_dip_eligibility(record_input)
    assert first == second


def test_all_outcomes_emit_closed_set_tokens_and_consistent_send_flag() -> None:
    sweep = (
        _eligible_input(tier_token="Tier 1"),
        _eligible_input(tier_token="Tier 2", drawdown_from_ath=Decimal("0.7")),
        _eligible_input(tier_token="Tier 3", drawdown_from_ath=Decimal("0.9")),
        _eligible_input(tier_token="Tier Unknown"),
        _eligible_input(tier_token="Tier Not Applicable"),
        _eligible_input(tier_token="garbage"),
        _eligible_input(migration_status=None),
        _eligible_input(ath_status=None),
        _eligible_input(post_migration_ath_verified=False),
        _eligible_input(market_context_status=None),
        _eligible_input(current_market_cap_usd=None),
        _eligible_input(drawdown_from_ath=None),
        _eligible_input(drawdown_from_ath=Decimal("NaN")),
        _eligible_input(drawdown_from_ath="0.55"),
        _eligible_input(candidate_id=""),
        _eligible_input(token_mint=""),
        _eligible_input(created_at_utc="bad"),
    )
    for record_input in sweep:
        rec = classify_tier_dip_eligibility(record_input)
        assert rec.decision in STAGE30_10_1_ELIGIBILITY_DECISIONS
        assert rec.reason in STAGE30_10_1_ELIGIBILITY_REASONS
        # send_allowed is True iff and only iff the decision is ELIGIBLE_DIP.
        assert rec.send_allowed == (rec.decision == DECISION_ELIGIBLE_DIP)
