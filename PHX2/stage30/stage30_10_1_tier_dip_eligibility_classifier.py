"""Stage 30.10.1 compact tier-dip eligibility classifier.

Pure, offline classifier that maps a Stage 30.10.1
``Stage30_10DipEligibilityInput`` + an explicit
``Stage30_10DipEligibilityPolicy`` onto exactly one
``Stage30_10DipEligibilityRecord``. This is the eligibility brain that makes
the compact private ping dip-focused: it decides SEND only for a true
tier-dip opportunity and SKIP for everything else, fail-closed.

The classifier NEVER fetches market data, NEVER opens a network connection,
NEVER reads the process environment, NEVER calls ``datetime.now`` (the clock
is caller-injected on the input), NEVER mutates its inputs, and NEVER wires
into the live runtime / Stage 28 suppression / Stage 30.3 / Stage 30.4
orchestrators. Stage 30.10.1 is fake / offline only; nothing existing
imports it.

Deterministic decision precedence (top-down, first match wins). Each branch
returns a record echoing the input signals with the closed-set decision +
reason + ``send_allowed`` flag:

  1. ``input_record`` is not a ``Stage30_10DipEligibilityInput``  -> raise
     ``Stage30_10DipEligibilityError`` (a caller-shape failure: there is no
     input to echo).
  2. invalid policy (wrong type or a bad ``allowed_tiers`` / non-bool axis)
     -> ``INVALID_INPUT`` / ``INVALID_POLICY``.
  3. blank ``candidate_id``      -> ``INVALID_INPUT`` / ``INVALID_CANDIDATE_ID``.
  4. blank ``token_mint``        -> ``INVALID_INPUT`` / ``INVALID_TOKEN_MINT``.
  5. unsafe ``created_at_utc``   -> ``INVALID_INPUT`` / ``INVALID_CREATED_AT_UTC``.
  6. ``require_migration_present`` and migration not PRESENT
                                 -> ``SKIPPED_MISSING_MIGRATION`` /
                                    ``MISSING_MIGRATION``.
  7. ATH not PRESENT             -> ``SKIPPED_MISSING_ATH`` / ``MISSING_ATH``.
  8. ``require_post_migration_ath`` and ``post_migration_ath_verified`` is
     not ``True``                -> ``SKIPPED_MISSING_ATH`` /
                                    ``PRE_MIGRATION_ATH_NOT_ALLOWED``.
  9. ``require_current_market_context`` and market context not PRESENT
                                 -> ``SKIPPED_MISSING_MARKET_CONTEXT`` /
                                    ``MISSING_MARKET_CONTEXT``; or current
                                    market cap missing / non-positive
                                 -> ``SKIPPED_MISSING_MARKET_CONTEXT`` /
                                    ``MISSING_CURRENT_MARKET_CAP``.
 10. ``drawdown_from_ath`` missing / not a finite Decimal (non-Decimal,
     ``NaN``, ``Infinity``, ``-Infinity``)
                                 -> ``SKIPPED_NOT_DIP`` / ``MISSING_DRAWDOWN``.
 11. normalized tier is ``TIER_UNKNOWN``
                                 -> ``SKIPPED_TIER_UNKNOWN`` / ``TIER_UNKNOWN``.
 12. normalized tier is ``TIER_NOT_APPLICABLE``
                                 -> ``SKIPPED_TIER_NOT_APPLICABLE`` /
                                    ``TIER_NOT_APPLICABLE``.
 13. unrecognized / ``None`` tier -> fail closed:
                                    ``fail_closed_on_unknown`` ?
                                    ``SKIPPED_TIER_UNKNOWN`` :
                                    ``SKIPPED_NOT_DIP`` (both no-send, reason
                                    ``TIER_UNKNOWN``).
 14. in-band tier in ``allowed_tiers``
                                 -> ``ELIGIBLE_DIP`` / ``TIER_ALLOWED``,
                                    ``send_allowed=True`` (the ONLY send).
 15. in-band tier NOT in ``allowed_tiers``
                                 -> ``SKIPPED_NOT_DIP`` / ``TIER_NOT_ALLOWED``.

``ELIGIBLE_DIP`` is reachable ONLY at branch 14, after every required signal
(migration, ATH, post-migration ATH, market context, current market cap, and
a finite-Decimal drawdown) is present and the tier is an allowed in-band
tier. No candidate with a missing / degraded / malformed / unrecognized
signal can ever become eligible.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.10.1 models sibling (no other PHX2 module; no
    Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression import).
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

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
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
    Stage30_10DipEligibilityRecord,
    TIER_CODE_TIER_NOT_APPLICABLE,
    TIER_CODE_TIER_UNKNOWN,
    is_finite_decimal,
    is_present_status,
    is_safe_created_at_utc,
    is_valid_policy,
    normalize_tier_token,
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_10DipEligibilityError(Exception):
    """Closed-set Stage 30.10.1 classifier error.

    Raised ONLY for a caller-shape failure the classifier cannot classify
    (an ``input_record`` that is not a ``Stage30_10DipEligibilityInput`` --
    there is no input to echo). Degraded / invalid input VALUES never raise;
    they fail closed to an ``INVALID_INPUT`` record. Carries only a closed-set
    reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.10.1 dip eligibility error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string."""
    return isinstance(value, str) and value.strip() != ""


def _is_positive_decimal(value: object) -> bool:
    """Return ``True`` iff ``value`` is a finite, strictly-positive Decimal.

    A missing (``None``), non-Decimal, non-finite (``NaN`` / ``Infinity``),
    zero, or negative value is NOT positive. Pure / total; never raises.
    """
    if not isinstance(value, Decimal):
        return False
    if not value.is_finite():
        return False
    return value > 0


def _record(
    input_record: Stage30_10DipEligibilityInput,
    decision: str,
    reason: str,
    send_allowed: bool,
) -> Stage30_10DipEligibilityRecord:
    """Build an eligibility record echoing ``input_record``'s signals with
    the given ``decision`` / ``reason`` / ``send_allowed``. Pure; no I/O.
    """
    return Stage30_10DipEligibilityRecord(
        candidate_id=input_record.candidate_id,
        token_mint=input_record.token_mint,
        tier_token=input_record.tier_token,
        drawdown_from_ath=input_record.drawdown_from_ath,
        migration_status=input_record.migration_status,
        ath_status=input_record.ath_status,
        market_context_status=input_record.market_context_status,
        current_market_cap_usd=input_record.current_market_cap_usd,
        post_migration_ath_verified=input_record.post_migration_ath_verified,
        decision=decision,
        reason=reason,
        send_allowed=send_allowed,
        created_at_utc=input_record.created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------


def classify_tier_dip_eligibility(
    input_record: Stage30_10DipEligibilityInput,
    policy: Stage30_10DipEligibilityPolicy = (
        DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY
    ),
) -> Stage30_10DipEligibilityRecord:
    """Classify one candidate's compact tier-dip eligibility.

    Pure / deterministic / no I/O. Identical inputs always produce a
    byte-identical record. Returns a ``Stage30_10DipEligibilityRecord`` whose
    ``send_allowed`` is ``True`` ONLY for an ``ELIGIBLE_DIP`` decision; every
    other decision is a clean no-send. Raises
    ``Stage30_10DipEligibilityError`` only when ``input_record`` is not a
    ``Stage30_10DipEligibilityInput`` (a caller-shape failure with no input
    to echo). See the module docstring for the full decision precedence.
    """
    # ---- Caller-shape guard: must have an input to echo ----
    if not isinstance(input_record, Stage30_10DipEligibilityInput):
        raise Stage30_10DipEligibilityError("INVALID_INPUT_RECORD_TYPE")

    # ---- Invalid policy -> classified INVALID (no send) ----
    if not is_valid_policy(policy):
        return _record(
            input_record,
            DECISION_INVALID_INPUT,
            REASON_INVALID_POLICY,
            False,
        )

    # ---- Invalid input fields -> classified INVALID (no send) ----
    if not _is_nonblank_str(input_record.candidate_id):
        return _record(
            input_record,
            DECISION_INVALID_INPUT,
            REASON_INVALID_CANDIDATE_ID,
            False,
        )
    if not _is_nonblank_str(input_record.token_mint):
        return _record(
            input_record,
            DECISION_INVALID_INPUT,
            REASON_INVALID_TOKEN_MINT,
            False,
        )
    if not is_safe_created_at_utc(input_record.created_at_utc):
        return _record(
            input_record,
            DECISION_INVALID_INPUT,
            REASON_INVALID_CREATED_AT_UTC,
            False,
        )

    # ---- Required-signal gates (fail-closed) ----

    # Migration must be present (when required).
    if policy.require_migration_present and not is_present_status(
        input_record.migration_status, MIGRATION_STATUS_PRESENT
    ):
        return _record(
            input_record,
            DECISION_SKIPPED_MISSING_MIGRATION,
            REASON_MISSING_MIGRATION,
            False,
        )

    # ATH must be present.
    if not is_present_status(input_record.ath_status, ATH_STATUS_PRESENT):
        return _record(
            input_record,
            DECISION_SKIPPED_MISSING_ATH,
            REASON_MISSING_ATH,
            False,
        )

    # ATH must be verified post-migration (when required).
    if (
        policy.require_post_migration_ath
        and input_record.post_migration_ath_verified is not True
    ):
        return _record(
            input_record,
            DECISION_SKIPPED_MISSING_ATH,
            REASON_PRE_MIGRATION_ATH_NOT_ALLOWED,
            False,
        )

    # Current market context must be present + carry a positive market cap
    # (when required).
    if policy.require_current_market_context:
        if not is_present_status(
            input_record.market_context_status,
            MARKET_CONTEXT_STATUS_PRESENT,
        ):
            return _record(
                input_record,
                DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
                REASON_MISSING_MARKET_CONTEXT,
                False,
            )
        if not _is_positive_decimal(input_record.current_market_cap_usd):
            return _record(
                input_record,
                DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
                REASON_MISSING_CURRENT_MARKET_CAP,
                False,
            )

    # A usable drawdown magnitude must be available to confirm a dip. The
    # magnitude must be a FINITE Decimal: a missing (None), malformed
    # non-Decimal (str / float / other), or non-finite (NaN / Infinity /
    # -Infinity) drawdown all fail closed here, so a malformed magnitude can
    # never reach ELIGIBLE_DIP. A finite signed / zero Decimal is structurally
    # valid; eligibility then hinges on the tier token below.
    if not is_finite_decimal(input_record.drawdown_from_ath):
        return _record(
            input_record,
            DECISION_SKIPPED_NOT_DIP,
            REASON_MISSING_DRAWDOWN,
            False,
        )

    # ---- Tier classification (fail-closed) ----
    normalized: Optional[str] = normalize_tier_token(input_record.tier_token)

    if normalized == TIER_CODE_TIER_UNKNOWN:
        return _record(
            input_record,
            DECISION_SKIPPED_TIER_UNKNOWN,
            REASON_TIER_UNKNOWN,
            False,
        )

    if normalized == TIER_CODE_TIER_NOT_APPLICABLE:
        return _record(
            input_record,
            DECISION_SKIPPED_TIER_NOT_APPLICABLE,
            REASON_TIER_NOT_APPLICABLE,
            False,
        )

    if normalized is None:
        # Unrecognized / missing tier: NEVER eligible. The declared posture
        # selects the skip bucket; both are a clean no-send.
        if policy.fail_closed_on_unknown:
            return _record(
                input_record,
                DECISION_SKIPPED_TIER_UNKNOWN,
                REASON_TIER_UNKNOWN,
                False,
            )
        return _record(
            input_record,
            DECISION_SKIPPED_NOT_DIP,
            REASON_TIER_UNKNOWN,
            False,
        )

    # ``normalized`` is one of the in-band tier codes (TIER_1/2/3).
    if normalized in policy.allowed_tiers:
        return _record(
            input_record,
            DECISION_ELIGIBLE_DIP,
            REASON_TIER_ALLOWED,
            True,
        )

    return _record(
        input_record,
        DECISION_SKIPPED_NOT_DIP,
        REASON_TIER_NOT_ALLOWED,
        False,
    )


__all__ = (
    "Stage30_10DipEligibilityError",
    "classify_tier_dip_eligibility",
)
