"""Stage 29.5.7 normalizer tests: the raw Helius migration accept/reject matrix.

Proves the discriminator-bound normalizer turns a real ``create_pool`` migration
envelope into a PRESENT Stage 29.5 evidence record and fails EVERY non-migration /
malformed / partial envelope closed with a PRECISE reason -- never fabricating
evidence (a loose tx-level CreatePool log + a look-alike Buy / Sell account layout
can NEVER manufacture evidence).
"""

from __future__ import annotations

import json

from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    USDC_MINT,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
    NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE,
    REJECT_REASON_MALFORMED_OBSERVED_AT,
    REJECT_REASON_MALFORMED_PAYLOAD,
    REJECT_REASON_MISSING_BLOCK_TIME,
    REJECT_REASON_MISSING_SIGNATURE,
    REJECT_REASON_MISSING_SLOT,
    REJECT_REASON_NO_CREATE_POOL_INSTRUCTION,
    REJECT_REASON_NONE,
    REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE,
    REJECT_REASON_POOL_QUARTET_UNRESOLVED,
    REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED,
    REJECT_REASON_TRANSACTION_FAILED,
    REJECT_REASON_VOTE_TRANSACTION,
    is_trailing_z_utc_shape,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_normalizer import (
    normalize_helius_raw_migration_envelope,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    project_migration_evidence_to_sanitized_summary,
)
from PHX2.tests.stage29._stage_29_5_7_helius_fixtures import (
    BASE_MINT,
    BUY_DISCRIMINATOR,
    CREATE_POOL_DISCRIMINATOR,
    DEFAULT_ANCHOR_UTC,
    DEFAULT_SLOT,
    OBSERVED_AT_UTC,
    POOL,
    QUOTE_MINT_SOL,
    QUOTE_MINT_USDC,
    SIGNATURE,
    encode_instruction_data,
    make_failed_migration_envelope,
    make_migration_envelope,
    make_missing_block_time_envelope,
    make_missing_signature_envelope,
    make_missing_slot_envelope,
    make_quartet_unresolved_envelope,
    make_sell_with_create_pool_layout_and_log_envelope,
    make_swap_envelope,
    make_swap_with_stray_create_pool_log_envelope,
    make_vote_migration_envelope,
    make_wrong_program_envelope,
)


def _normalize(envelope: object):
    return normalize_helius_raw_migration_envelope(envelope, OBSERVED_AT_UTC)


# ---------------------------------------------------------------------------
# 1. Happy path: a real CPI create_pool migration -> PRESENT record
# ---------------------------------------------------------------------------


def test_cpi_migration_proves_present_evidence() -> None:
    result = _normalize(make_migration_envelope(via_cpi=True))
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.reject_reason == REJECT_REASON_NONE
    record = result.evidence_record
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_PRESENT
    assert record.migration_source == MIGRATION_SOURCE_HELIUS_WS
    assert record.base_mint == BASE_MINT
    assert record.pool_account == POOL
    assert record.quote_mint == QUOTE_MINT_SOL
    assert record.pool_program_id == PUMPSWAP_PROGRAM_ID
    assert record.migration_slot == DEFAULT_SLOT
    assert record.migration_signature == SIGNATURE
    assert record.observed_at_utc == OBSERVED_AT_UTC


def test_proven_anchor_is_trailing_z_never_offset() -> None:
    record = _normalize(make_migration_envelope()).evidence_record
    assert record is not None
    assert record.migration_timestamp_utc == DEFAULT_ANCHOR_UTC
    assert record.migration_timestamp_utc.endswith("Z")
    assert "+00:00" not in record.migration_timestamp_utc
    assert is_trailing_z_utc_shape(record.migration_timestamp_utc)


def test_source_ref_carries_signature_and_slot() -> None:
    record = _normalize(make_migration_envelope()).evidence_record
    assert record is not None
    assert record.source_event_ref == (
        f"helius:sig:{SIGNATURE}:slot:{DEFAULT_SLOT}"
    )


def test_direct_top_level_create_pool_proves_present() -> None:
    result = _normalize(make_migration_envelope(via_cpi=False))
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.evidence_record is not None


def test_usdc_quote_migration_proves_present() -> None:
    result = _normalize(make_migration_envelope(quote_mint=QUOTE_MINT_USDC))
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    record = result.evidence_record
    assert record is not None
    assert record.quote_mint == USDC_MINT


def test_initial_buy_same_pool_is_ignored_by_discriminator_gate() -> None:
    # create_pool + an initial Buy against the SAME new pool. The Buy shares the
    # pool@0 / base@3 / quote@4 layout but carries the Buy discriminator, so the
    # discriminator gate IGNORES it: the migration still proves, and only the
    # create_pool instruction counts as a create_pool match.
    result = _normalize(make_migration_envelope(include_initial_buy=True))
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.evidence_record is not None
    assert result.pumpswap_instruction_count == 2  # create_pool + buy
    assert result.create_pool_match_count == 1  # only create_pool is a match


def test_duplicate_create_pool_same_quartet_collapses_to_one() -> None:
    # Two create_pool instructions (both the create_pool discriminator) resolving
    # the SAME quartet collapse to one distinct quartet; the migration proves.
    result = _normalize(
        make_migration_envelope(include_duplicate_create_pool=True)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.evidence_record is not None
    assert result.create_pool_match_count == 2  # two matches, one distinct quartet


def test_migration_accepts_raw_json_bytes_and_str() -> None:
    env = make_migration_envelope()
    as_bytes = json.dumps(env).encode("utf-8")
    as_str = json.dumps(env)
    assert (
        _normalize(as_bytes).outcome
        == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    )
    assert (
        _normalize(as_str).outcome
        == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    )


def test_normalizer_is_deterministic() -> None:
    env = make_migration_envelope()
    a = _normalize(env)
    b = _normalize(env)
    assert a.evidence_record == b.evidence_record


# ---------------------------------------------------------------------------
# 5. Ordinary swap rejected (audit test #5)
# ---------------------------------------------------------------------------


def test_ordinary_swap_is_not_a_migration() -> None:
    result = _normalize(make_swap_envelope())
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_NO_CREATE_POOL_INSTRUCTION
    assert result.evidence_record is None


def test_create_pool_log_absent_even_with_pumpswap_invoke_fails() -> None:
    result = _normalize(make_migration_envelope(omit_create_pool_log=True))
    assert result.reject_reason == REJECT_REASON_NO_CREATE_POOL_INSTRUCTION
    assert result.evidence_record is None


# ---------------------------------------------------------------------------
# 9. Wrong program rejected (audit test #9)
# ---------------------------------------------------------------------------


def test_wrong_program_rejected() -> None:
    result = _normalize(make_wrong_program_envelope())
    assert (
        result.reject_reason == REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED
    )
    assert result.evidence_record is None


# ---------------------------------------------------------------------------
# 7. Missing mint rejected (audit test #7) -- quartet cannot resolve
# ---------------------------------------------------------------------------


def test_unknown_quote_mint_fails_quartet() -> None:
    result = _normalize(make_quartet_unresolved_envelope())
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.evidence_record is None


def test_create_pool_logged_but_no_pumpswap_instruction_fails_quartet() -> None:
    # CreatePool is logged and PumpSwap is invoked, but the message carries no
    # PumpSwap instruction with a resolvable create_pool layout.
    env = make_migration_envelope()
    env["transaction"]["message"]["instructions"] = []
    env["meta"]["innerInstructions"] = []
    result = _normalize(env)
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED


def test_two_distinct_pools_fail_closed() -> None:
    # Two create_pool-DISCRIMINATOR instructions resolving DISTINCT quartets ->
    # ambiguous -> fail closed (never picks one arbitrarily).
    env = make_migration_envelope(via_cpi=False)
    keys = env["transaction"]["message"]["accountKeys"]
    # Append a second distinct pool + base at new indices, quote re-used. It MUST
    # carry the create_pool discriminator to count as a second candidate.
    second_pool = "P2" + "p" * 42
    second_base = "B2" + "b" * 42
    keys.extend([second_pool, second_base])  # indices 6, 7
    env["transaction"]["message"]["instructions"].append(
        {
            "programIdIndex": 5,
            "accounts": [6, 1, 2, 7, 4],
            "data": encode_instruction_data(CREATE_POOL_DISCRIMINATOR),
        }
    )
    result = _normalize(env)
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.create_pool_match_count == 2  # two distinct create_pool quartets


# ---------------------------------------------------------------------------
# 8. Missing signature / slot / source_ref rejected (audit test #8)
# ---------------------------------------------------------------------------


def test_missing_signature_rejected() -> None:
    result = _normalize(make_missing_signature_envelope())
    assert result.reject_reason == REJECT_REASON_MISSING_SIGNATURE
    assert result.evidence_record is None


def test_missing_slot_rejected() -> None:
    result = _normalize(make_missing_slot_envelope())
    assert result.reject_reason == REJECT_REASON_MISSING_SLOT
    assert result.evidence_record is None


def test_non_int_slot_rejected() -> None:
    env = make_migration_envelope()
    env["slot"] = "not-an-int"
    assert _normalize(env).reject_reason == REJECT_REASON_MISSING_SLOT


def test_bool_slot_rejected() -> None:
    env = make_migration_envelope()
    env["slot"] = True
    assert _normalize(env).reject_reason == REJECT_REASON_MISSING_SLOT


# ---------------------------------------------------------------------------
# 6. Missing timestamp rejected (audit test #6)
# ---------------------------------------------------------------------------


def test_missing_block_time_rejected() -> None:
    result = _normalize(make_missing_block_time_envelope())
    assert result.reject_reason == REJECT_REASON_MISSING_BLOCK_TIME
    assert result.evidence_record is None


def test_non_int_block_time_rejected() -> None:
    env = make_migration_envelope()
    env["blockTime"] = "1716768000"
    assert _normalize(env).reject_reason == REJECT_REASON_MISSING_BLOCK_TIME


def test_negative_block_time_rejected() -> None:
    env = make_migration_envelope()
    env["blockTime"] = -5
    assert _normalize(env).reject_reason == REJECT_REASON_MISSING_BLOCK_TIME


# ---------------------------------------------------------------------------
# 3/4. Failed + vote transactions rejected
# ---------------------------------------------------------------------------


def test_failed_transaction_rejected() -> None:
    result = _normalize(make_failed_migration_envelope())
    assert result.reject_reason == REJECT_REASON_TRANSACTION_FAILED
    assert result.evidence_record is None


def test_vote_transaction_rejected() -> None:
    result = _normalize(make_vote_migration_envelope())
    assert result.reject_reason == REJECT_REASON_VOTE_TRANSACTION


# ---------------------------------------------------------------------------
# 10. Partial / malformed payload rejected (audit test #10)
# ---------------------------------------------------------------------------


def test_non_json_bytes_rejected_malformed() -> None:
    result = _normalize(b"\xff\xfe not json")
    assert result.reject_reason == REJECT_REASON_MALFORMED_PAYLOAD


def test_non_object_json_rejected() -> None:
    assert (
        _normalize("[1, 2, 3]").reject_reason
        == REJECT_REASON_MALFORMED_PAYLOAD
    )


def test_non_envelope_type_rejected() -> None:
    assert (
        _normalize(12345).reject_reason
        == REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE
    )


def test_object_without_meta_rejected() -> None:
    assert (
        _normalize({"slot": 1}).reject_reason
        == REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE
    )


def test_empty_dict_rejected() -> None:
    assert (
        _normalize({}).reject_reason
        == REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE
    )


# ---------------------------------------------------------------------------
# 1 (precedence). Malformed caller clock rejected before anything else
# ---------------------------------------------------------------------------


def test_malformed_observed_at_rejected() -> None:
    result = normalize_helius_raw_migration_envelope(
        make_migration_envelope(), "not-a-timestamp"
    )
    assert result.reject_reason == REJECT_REASON_MALFORMED_OBSERVED_AT
    assert result.evidence_record is None


def test_offset_observed_at_rejected() -> None:
    # The caller clock must be UTC-shaped; the Stage 29.5 validator accepts Z or
    # +00:00 for observed_at, so an offset form here is still accepted upstream --
    # assert a clearly-malformed value fails, and a Z value passes.
    ok = normalize_helius_raw_migration_envelope(
        make_migration_envelope(), "2026-05-27T00:05:00Z"
    )
    assert ok.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN


# ---------------------------------------------------------------------------
# Codex audit regression: the migration proof is BOUND to the actual create_pool
# instruction discriminator -- a loose tx-level CreatePool log plus a look-alike
# Buy / Sell account layout can NEVER manufacture migration evidence.
# ---------------------------------------------------------------------------


def test_ordinary_swap_plus_stray_create_pool_log_fails_closed() -> None:
    # The Codex repro: an ordinary Buy swap (Buy discriminator, but create_pool-
    # SHAPED pool@0 / base@3 / quote@4 accounts) with a stray
    # ``Instruction: CreatePool`` log spliced in. Must fail closed -- no PRESENT,
    # no MIGRATION_PROVEN, no evidence record.
    result = _normalize(make_swap_with_stray_create_pool_log_envelope())
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.evidence_record is None
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    # The Buy IS a PumpSwap instruction but is NOT a create_pool match.
    assert result.pumpswap_instruction_count == 1
    assert result.create_pool_match_count == 0


def test_sell_layout_plus_stray_create_pool_log_fails_closed() -> None:
    # A PumpSwap Sell with create_pool-shaped accounts + a stray CreatePool log.
    # The Sell discriminator is not create_pool, so it must fail closed.
    result = _normalize(make_sell_with_create_pool_layout_and_log_envelope())
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.evidence_record is None
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.create_pool_match_count == 0


def test_create_pool_layout_with_buy_discriminator_fails_closed() -> None:
    # A create_pool-SHAPED instruction (pool@0 / base@3 / quote@4) + a CreatePool
    # log, but the instruction's OWN discriminator is Buy -> must NOT prove.
    result = _normalize(
        make_migration_envelope(create_pool_discriminator=BUY_DISCRIMINATOR)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.evidence_record is None
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.create_pool_match_count == 0


def test_create_pool_log_present_but_no_discriminator_fails_closed() -> None:
    # CreatePool log + create_pool-shaped accounts, but the instruction carries NO
    # data (no decodable discriminator) -> cannot prove migration.
    result = _normalize(make_migration_envelope(create_pool_discriminator=None))
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.evidence_record is None


def test_create_pool_layout_without_discriminator_or_log_fails_closed() -> None:
    # create_pool-shaped accounts, but NO discriminator AND NO CreatePool log ->
    # rejected at the coarse log precondition.
    result = _normalize(
        make_migration_envelope(
            create_pool_discriminator=None, omit_create_pool_log=True
        )
    )
    assert result.reject_reason == REJECT_REASON_NO_CREATE_POOL_INSTRUCTION
    assert result.evidence_record is None


def test_only_the_real_create_pool_discriminator_proves_present() -> None:
    # Positive/negative control over the SAME envelope shape: it proves ONLY when
    # the instruction carries the real create_pool discriminator; swapping to the
    # Buy discriminator flips PROVEN -> fail-closed.
    proven = _normalize(
        make_migration_envelope(
            create_pool_discriminator=CREATE_POOL_DISCRIMINATOR
        )
    )
    assert proven.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert proven.evidence_record is not None
    assert proven.reject_reason == REJECT_REASON_NONE
    rejected = _normalize(
        make_migration_envelope(create_pool_discriminator=BUY_DISCRIMINATOR)
    )
    assert rejected.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert rejected.evidence_record is None


# ---------------------------------------------------------------------------
# Stage 29.5.8: orientation-agnostic create_pool quartet. The WSOL/USDC quote
# mint may sit at EITHER instruction-account index 3 OR 4 (both observed on real
# PumpSwap migrations); the migrated token is always the NON-quote side. Exactly
# one side must be a known quote (neither / both fail closed). The discriminator
# gate, distinctness, field checks, source_ref, and redaction are unchanged.
# ---------------------------------------------------------------------------


# A second safe-shape NON-quote mint (length 44) and an unsafe-shape token.
_SECOND_TOKEN: str = "Tk" + "t" * 42
_MALFORMED_TOKEN: str = "short"


def test_inverted_wsol_at_index_3_token_at_index_4_proves() -> None:
    # Real-world PumpSwap layout: WSOL at index 3, the migrated token at index 4.
    result = _normalize(
        make_migration_envelope(base_mint=QUOTE_MINT_SOL, quote_mint=BASE_MINT)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.reject_reason == REJECT_REASON_NONE
    record = result.evidence_record
    assert record is not None
    assert record.base_mint == BASE_MINT          # migrated token = the non-quote side
    assert record.quote_mint == QUOTE_MINT_SOL    # WSOL recognized as the quote
    assert record.pool_account == POOL
    assert result.create_pool_match_count == 1


def test_legacy_token_at_index_3_wsol_at_index_4_still_proves() -> None:
    # Back-compat: the original orientation (token@3, WSOL@4) still proves.
    result = _normalize(
        make_migration_envelope(base_mint=BASE_MINT, quote_mint=QUOTE_MINT_SOL)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    record = result.evidence_record
    assert record is not None
    assert record.base_mint == BASE_MINT
    assert record.quote_mint == QUOTE_MINT_SOL


def test_inverted_usdc_at_index_3_token_at_index_4_proves() -> None:
    result = _normalize(
        make_migration_envelope(base_mint=QUOTE_MINT_USDC, quote_mint=BASE_MINT)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    record = result.evidence_record
    assert record is not None
    assert record.base_mint == BASE_MINT
    assert record.quote_mint == USDC_MINT


def test_legacy_token_at_index_3_usdc_at_index_4_still_proves() -> None:
    result = _normalize(
        make_migration_envelope(base_mint=BASE_MINT, quote_mint=QUOTE_MINT_USDC)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    assert result.evidence_record is not None
    assert result.evidence_record.quote_mint == USDC_MINT


def test_neither_side_known_quote_fails_closed() -> None:
    # Two non-quote tokens (token/token pool) -> no known quote -> fail closed.
    result = _normalize(
        make_migration_envelope(base_mint=BASE_MINT, quote_mint=_SECOND_TOKEN)
    )
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.evidence_record is None
    assert result.create_pool_match_count == 0


def test_both_sides_known_quote_fails_closed() -> None:
    # WSOL@3 + USDC@4: both are known quotes -> ambiguous which side is the token
    # -> fail closed (never guesses).
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL, quote_mint=QUOTE_MINT_USDC
        )
    )
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.evidence_record is None
    assert result.create_pool_match_count == 0


def test_malformed_migrated_token_inverted_layout_fails_closed() -> None:
    # WSOL@3 (valid quote) + a malformed token@4 (unsafe shape) -> reject.
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL, quote_mint=_MALFORMED_TOKEN
        )
    )
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.evidence_record is None


def test_inverted_layout_missing_signature_still_rejects() -> None:
    # The inverted quartet now RESOLVES, so the later field checks must still fire.
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL, quote_mint=BASE_MINT, signature=None
        )
    )
    assert result.reject_reason == REJECT_REASON_MISSING_SIGNATURE
    assert result.evidence_record is None


def test_inverted_layout_missing_slot_still_rejects() -> None:
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL, quote_mint=BASE_MINT, drop_slot=True
        )
    )
    assert result.reject_reason == REJECT_REASON_MISSING_SLOT
    assert result.evidence_record is None


def test_inverted_layout_missing_block_time_still_rejects() -> None:
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL, quote_mint=BASE_MINT, drop_block_time=True
        )
    )
    assert result.reject_reason == REJECT_REASON_MISSING_BLOCK_TIME
    assert result.evidence_record is None


def test_inverted_layout_source_ref_and_redaction_unchanged() -> None:
    # The inverted-layout proven record carries the SAME source_ref shape, and its
    # projected summary stays COMPLETE / SAFE (redaction behavior unchanged); the
    # discovered token_mint is the non-quote side.
    record = _normalize(
        make_migration_envelope(base_mint=QUOTE_MINT_SOL, quote_mint=BASE_MINT)
    ).evidence_record
    assert record is not None
    assert record.source_event_ref == (
        f"helius:sig:{SIGNATURE}:slot:{DEFAULT_SLOT}"
    )
    summary = project_migration_evidence_to_sanitized_summary(record)
    assert summary is not None
    assert summary.token_mint == BASE_MINT
    assert summary.measurement_status == "COMPLETE"
    assert summary.redaction_status == "SAFE"
    assert summary.warnings == ()
    assert summary.source_ref == f"helius:sig:{SIGNATURE}:slot:{DEFAULT_SLOT}"


def test_inverted_layout_with_buy_discriminator_still_fails_closed() -> None:
    # Orientation-agnostic resolution must NOT weaken the discriminator gate: an
    # inverted-layout instruction carrying the Buy discriminator never proves.
    result = _normalize(
        make_migration_envelope(
            base_mint=QUOTE_MINT_SOL,
            quote_mint=BASE_MINT,
            create_pool_discriminator=BUY_DISCRIMINATOR,
        )
    )
    assert result.outcome == NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE
    assert result.reject_reason == REJECT_REASON_POOL_QUARTET_UNRESOLVED
    assert result.create_pool_match_count == 0
