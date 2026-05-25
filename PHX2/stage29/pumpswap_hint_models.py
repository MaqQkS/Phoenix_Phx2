"""Stage 29.1 PumpSwap hint extraction models.

Closed-set vocabularies + the immutable extraction-result record
the Stage 29.1 hint extractor returns. The vocabularies use the
exact names reserved in
``PHX2/stage29/STAGE_29_0_SPEC_LOCK.md`` §13 (Stage 29.0 reserved
the names; Stage 29.1 ships the runtime constants).

This module imports ONLY stdlib (``dataclasses`` / ``typing``).
It does NOT import:

  * Stage 21-28 production code,
  * ``grpc`` / ``grpcio`` / ``protobuf`` / generated stubs,
  * any network / RPC / messaging / DB / scheduler / wallet /
    trading / Discord / Telegram / X / dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level I/O at import time.
  * Hint extraction results carry ONLY closed-set tokens + safe
    optional base58 strings; no raw upstream bytes, log strings,
    or instruction data ever appear on a result record.
  * ``no_evidence_reason`` is ALWAYS one of the closed-set
    tokens; the extractor never leaks freeform text on this
    axis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Closed-set: hint_extraction_outcome
# ---------------------------------------------------------------------------


HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED: str = "HINTS_EXTRACTED"
HINT_EXTRACTION_OUTCOME_NO_EVIDENCE: str = "NO_EVIDENCE"


HINT_EXTRACTION_OUTCOME_VALUES: tuple[str, ...] = (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
)


def is_hint_extraction_outcome_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in HINT_EXTRACTION_OUTCOME_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: no_evidence_reason
# ---------------------------------------------------------------------------


NO_EVIDENCE_REASON_NONE: str = "NONE"
NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION: str = (
    "UPDATE_NOT_TRANSACTION"
)
NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED: str = (
    "TRANSACTION_IS_VOTE_SKIPPED"
)
NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR: str = (
    "TRANSACTION_FAILED_PER_META_ERR"
)
NO_EVIDENCE_REASON_META_MISSING: str = "META_MISSING"
NO_EVIDENCE_REASON_NO_TOKEN_BALANCES: str = "NO_TOKEN_BALANCES"
NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES: str = (
    "NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES"
)
NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE: str = (
    "NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE"
)
NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES: str = (
    "POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES"
)
NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS: str = (
    "POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS"
)
NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE: str = (
    "BASE_MINT_REJECTED_SAFE_SHAPE"
)
NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE: str = (
    "POOL_ACCOUNT_REJECTED_SAFE_SHAPE"
)
NO_EVIDENCE_REASON_QUOTE_MINT_NOT_KNOWN_QUOTE: str = (
    "QUOTE_MINT_NOT_KNOWN_QUOTE"
)


NO_EVIDENCE_REASON_VALUES: tuple[str, ...] = (
    NO_EVIDENCE_REASON_NONE,
    NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
    NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
    NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
    NO_EVIDENCE_REASON_META_MISSING,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
    NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES,
    NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS,
    NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE,
    NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE,
    NO_EVIDENCE_REASON_QUOTE_MINT_NOT_KNOWN_QUOTE,
)


def is_no_evidence_reason_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in NO_EVIDENCE_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: pool_account_evidence_source
# ---------------------------------------------------------------------------


POOL_ACCOUNT_EVIDENCE_SOURCE_NONE: str = "NONE"
POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING: str = (
    "TOKEN_BALANCE_OWNER_GROUPING"
)


POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES: tuple[str, ...] = (
    POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
    POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING,
)


def is_pool_account_evidence_source_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: quote_mint_evidence_source
# ---------------------------------------------------------------------------


QUOTE_MINT_EVIDENCE_SOURCE_NONE: str = "NONE"
QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE: str = (
    "POOL_OWNER_TOKEN_BALANCE"
)


QUOTE_MINT_EVIDENCE_SOURCE_VALUES: tuple[str, ...] = (
    QUOTE_MINT_EVIDENCE_SOURCE_NONE,
    QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE,
)


def is_quote_mint_evidence_source_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in QUOTE_MINT_EVIDENCE_SOURCE_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 29.1 module-local exception
# ---------------------------------------------------------------------------


class Stage29_1PumpSwapHintExtractorError(Exception):
    """Base type for every Stage 29.1 PumpSwap hint extractor
    validation error. Module-local; not a subclass of any central
    PHX2 error registry. The constructor NEVER carries a raw
    upstream protobuf field value, a raw log string, or a raw
    instruction byte sequence; callers pass only the closed-set
    reason token.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 29.1 PumpSwap hint extractor error: "
            f"reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage29_1PumpSwapHintExtractionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_1PumpSwapHintExtractionResult:
    """Immutable Stage 29.1 PumpSwap hint extraction result.

    All hint axes are ``Optional[str]``; the extractor populates
    them ONLY when explicit token-balance evidence supports the
    value. When the evidence is insufficient the axis stays
    ``None`` and ``no_evidence_reason`` carries the closed-set
    token explaining why.

    Fields:

      * ``outcome`` -- closed-set
        ``HINT_EXTRACTION_OUTCOME_*`` token. ``HINTS_EXTRACTED``
        iff at least the (``base_mint``, ``pool_account``,
        ``quote_mint``, ``pool_program_id``) quartet is non-None;
        ``NO_EVIDENCE`` otherwise.
      * ``base_mint`` -- the non-quote SPL mint observed at the
        pool owner; ``None`` when no evidence supports a single
        unambiguous base mint.
      * ``pool_account`` -- the SPL Token Account ``owner`` that
        holds both a known quote mint and exactly one non-quote
        mint; ``None`` when no evidence supports a single
        unambiguous pool.
      * ``quote_mint`` -- the known quote mint observed at the
        pool owner (``WRAPPED_SOL_MINT`` or ``USDC_MINT``);
        ``None`` when no evidence supports a known quote.
      * ``pool_program_id`` -- the PumpSwap program id (the
        Stage 29.1 probe narrows the upstream subscription to
        this program); populated only when the heuristic
        identifies a pool, ``None`` otherwise.
      * ``provider_pair_type_hint`` -- closed-set
        ``"PUMP_SOL"`` / ``"PUMP_USDC"`` token derived from
        ``quote_mint``; ``None`` when the quote mint is unknown
        or the heuristic did not identify a pool.
      * ``provider_quote_asset_hint`` -- closed-set ``"SOL"`` /
        ``"USDC"`` token derived from ``quote_mint``; ``None``
        when the quote mint is unknown or the heuristic did not
        identify a pool.
      * ``bonding_curve_version_hint`` -- always ``None`` at
        Stage 29.1 (PumpSwap is the post-migration AMM; the
        bonding-curve version axis applies to the Pump.fun
        pre-migration program and is deferred to a future
        explicitly-authorized substage).
      * ``no_evidence_reason`` -- closed-set
        ``NO_EVIDENCE_REASON_*`` token. ``"NONE"`` iff
        ``outcome == HINTS_EXTRACTED``.
      * ``pool_account_evidence_source`` -- closed-set
        ``POOL_ACCOUNT_EVIDENCE_SOURCE_*`` token.
      * ``quote_mint_evidence_source`` -- closed-set
        ``QUOTE_MINT_EVIDENCE_SOURCE_*`` token.
      * ``spl_token_balance_count`` -- safe counter of how many
        SPL Token / Token-2022 entries the extractor considered
        (``pre`` + ``post`` combined, deduplicated by
        ``(owner, mint)``). Never carries raw amounts, decimals,
        or balance bytes.
      * ``pool_owner_candidate_count`` -- safe counter of how
        many distinct owners held both a known quote mint and at
        least one non-quote mint.
    """

    outcome: str
    base_mint: Optional[str]
    pool_account: Optional[str]
    quote_mint: Optional[str]
    pool_program_id: Optional[str]
    provider_pair_type_hint: Optional[str]
    provider_quote_asset_hint: Optional[str]
    bonding_curve_version_hint: Optional[str]
    no_evidence_reason: str
    pool_account_evidence_source: str
    quote_mint_evidence_source: str
    spl_token_balance_count: int
    pool_owner_candidate_count: int

    def __post_init__(self) -> None:
        _validate_extraction_result_fields(self)


def _validate_extraction_result_fields(
    record: "Stage29_1PumpSwapHintExtractionResult",
) -> None:
    """Validate every field of a
    ``Stage29_1PumpSwapHintExtractionResult``.

    Pure / deterministic. Raises
    ``Stage29_1PumpSwapHintExtractorError`` on the first failing
    field; the error carries only a closed-set field-name reason
    token, never the raw unsafe value.
    """
    if not is_hint_extraction_outcome_value(record.outcome):
        raise Stage29_1PumpSwapHintExtractorError(
            "OUTCOME_NOT_CLOSED_SET",
        )
    if not is_no_evidence_reason_value(record.no_evidence_reason):
        raise Stage29_1PumpSwapHintExtractorError(
            "NO_EVIDENCE_REASON_NOT_CLOSED_SET",
        )
    if not is_pool_account_evidence_source_value(
        record.pool_account_evidence_source,
    ):
        raise Stage29_1PumpSwapHintExtractorError(
            "POOL_ACCOUNT_EVIDENCE_SOURCE_NOT_CLOSED_SET",
        )
    if not is_quote_mint_evidence_source_value(
        record.quote_mint_evidence_source,
    ):
        raise Stage29_1PumpSwapHintExtractorError(
            "QUOTE_MINT_EVIDENCE_SOURCE_NOT_CLOSED_SET",
        )

    if (
        isinstance(record.spl_token_balance_count, bool)
        or not isinstance(record.spl_token_balance_count, int)
        or record.spl_token_balance_count < 0
    ):
        raise Stage29_1PumpSwapHintExtractorError(
            "SPL_TOKEN_BALANCE_COUNT_UNSAFE",
        )
    if (
        isinstance(record.pool_owner_candidate_count, bool)
        or not isinstance(record.pool_owner_candidate_count, int)
        or record.pool_owner_candidate_count < 0
    ):
        raise Stage29_1PumpSwapHintExtractorError(
            "POOL_OWNER_CANDIDATE_COUNT_UNSAFE",
        )

    # Closed-set internal consistency: when outcome is
    # HINTS_EXTRACTED the quartet must be populated AND the
    # no_evidence_reason must be NONE. When outcome is
    # NO_EVIDENCE every hint must be None AND no_evidence_reason
    # must NOT be NONE.
    if record.outcome == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED:
        for slot in (
            record.base_mint,
            record.pool_account,
            record.quote_mint,
            record.pool_program_id,
        ):
            if not isinstance(slot, str) or slot == "":
                raise Stage29_1PumpSwapHintExtractorError(
                    "HINTS_EXTRACTED_BUT_QUARTET_MISSING_SLOT",
                )
        if record.no_evidence_reason != NO_EVIDENCE_REASON_NONE:
            raise Stage29_1PumpSwapHintExtractorError(
                "HINTS_EXTRACTED_BUT_NO_EVIDENCE_REASON_SET",
            )
        if record.provider_pair_type_hint not in (
            "PUMP_SOL", "PUMP_USDC",
        ):
            raise Stage29_1PumpSwapHintExtractorError(
                "PROVIDER_PAIR_TYPE_HINT_NOT_CLOSED_SET",
            )
        if record.provider_quote_asset_hint not in ("SOL", "USDC"):
            raise Stage29_1PumpSwapHintExtractorError(
                "PROVIDER_QUOTE_ASSET_HINT_NOT_CLOSED_SET",
            )
    else:
        # NO_EVIDENCE: every hint slot must be None.
        for slot in (
            record.base_mint,
            record.pool_account,
            record.quote_mint,
            record.pool_program_id,
            record.provider_pair_type_hint,
            record.provider_quote_asset_hint,
        ):
            if slot is not None:
                raise Stage29_1PumpSwapHintExtractorError(
                    "NO_EVIDENCE_BUT_SLOT_POPULATED",
                )
        if record.no_evidence_reason == NO_EVIDENCE_REASON_NONE:
            raise Stage29_1PumpSwapHintExtractorError(
                "NO_EVIDENCE_BUT_REASON_NONE",
            )

    # Stage 29.1 NEVER promotes a bonding_curve_version_hint from
    # PumpSwap evidence; the axis is reserved for the deferred
    # Pump.fun bonding-curve substage.
    if record.bonding_curve_version_hint is not None:
        raise Stage29_1PumpSwapHintExtractorError(
            "BONDING_CURVE_VERSION_HINT_NOT_ALLOWED_AT_29_1",
        )


__all__ = (
    "HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED",
    "HINT_EXTRACTION_OUTCOME_NO_EVIDENCE",
    "HINT_EXTRACTION_OUTCOME_VALUES",
    "is_hint_extraction_outcome_value",
    "NO_EVIDENCE_REASON_NONE",
    "NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION",
    "NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED",
    "NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR",
    "NO_EVIDENCE_REASON_META_MISSING",
    "NO_EVIDENCE_REASON_NO_TOKEN_BALANCES",
    "NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES",
    "NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE",
    "NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES",
    "NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS",
    "NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE",
    "NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE",
    "NO_EVIDENCE_REASON_QUOTE_MINT_NOT_KNOWN_QUOTE",
    "NO_EVIDENCE_REASON_VALUES",
    "is_no_evidence_reason_value",
    "POOL_ACCOUNT_EVIDENCE_SOURCE_NONE",
    "POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING",
    "POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES",
    "is_pool_account_evidence_source_value",
    "QUOTE_MINT_EVIDENCE_SOURCE_NONE",
    "QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE",
    "QUOTE_MINT_EVIDENCE_SOURCE_VALUES",
    "is_quote_mint_evidence_source_value",
    "Stage29_1PumpSwapHintExtractorError",
    "Stage29_1PumpSwapHintExtractionResult",
)
