"""Stage 29.1 PumpSwap hint extractor.

Pure function ``extract_pumpswap_hints(update)`` that consumes a
single Yellowstone ``SubscribeUpdate`` protobuf message and
returns a ``Stage29_1PumpSwapHintExtractionResult`` carrying the
mint / pool / quote hints derived from the message's
``meta.{pre,post}_token_balances`` evidence.

The extractor implements a token-balance owner-grouping heuristic
that mirrors the well-bounded PumpSwap pool-shape rule:

  * group all SPL Token / Token-2022 ``TokenBalance`` entries by
    their ``owner`` field,
  * find owners whose mint set contains exactly one known quote
    mint (``WRAPPED_SOL_MINT`` or ``USDC_MINT``) AND exactly one
    non-quote mint,
  * if exactly one such owner exists, that owner IS the pool
    account and the non-quote mint IS the base mint,
  * otherwise the extractor returns a closed-set NO_EVIDENCE
    result whose reason token describes the ambiguity.

This heuristic relies ONLY on protobuf fields the Stage 28.11
generated stubs expose at type ``string`` (``TokenBalance.mint``,
``TokenBalance.owner``, ``TokenBalance.program_id``); the
extractor does NOT need to base58-encode raw account-key bytes,
does NOT parse Anchor instruction data, does NOT decode Anchor
event logs, and does NOT consult an Anchor IDL at runtime.

This module imports ONLY stdlib (``typing``) plus the Stage 28.11
generated protobuf stubs (``geyser_pb2``) and the Stage 29.1
constants + models. It does NOT import:

  * Stage 21-27 production code,
  * Stage 28.0 - 28.9 production code (the Stage 28.10 model
    module would be a tempting import for ``is_safe_payload_string``
    but the extractor stays self-contained; the Stage 29.1
    hint-aware decoder layer is what calls Stage 28.10's
    ``build_chainstack_yellowstone_payload`` and catches its
    validation rejection),
  * ``grpc`` / ``grpcio`` (gRPC is the live-probe module's
    surface, not this pure extractor's),
  * any network / RPC / messaging / DB / scheduler / wallet /
    trading / Discord / Telegram / X / dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module. The legacy
    ``grpc_decoder`` file in the operator's local legacy tree
    was design evidence only; the extractor here is
    independently re-implemented from the spec.

Discipline:

  * No env reads.
  * No network.
  * No top-level I/O at import time.
  * No fabrication: every populated hint slot is sourced
    directly from a ``TokenBalance`` field; missing evidence
    yields ``None`` plus a closed-set reason.
  * No SOL invention.
  * No USDC invention.
  * Vote transactions are skipped deterministically.
  * Failed transactions (``meta.err`` set) yield NO_EVIDENCE
    with ``TRANSACTION_FAILED_PER_META_ERR`` rather than
    extracting hints from a failed swap.
"""

from __future__ import annotations

from typing import Optional

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    NO_EVIDENCE_REASON_META_MISSING,
    NO_EVIDENCE_REASON_NONE,
    NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
    NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
    NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES,
    NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS,
    NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
    NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
    NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
    POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
    POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING,
    QUOTE_MINT_EVIDENCE_SOURCE_NONE,
    QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE,
    Stage29_1PumpSwapHintExtractionResult,
)
from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT,
    PUMPSWAP_PROGRAM_ID,
    is_spl_token_program_id,
)


# ---------------------------------------------------------------------------
# Internal helpers (pure)
# ---------------------------------------------------------------------------


def _has_field(message: object, name: str) -> bool:
    """Return ``True`` iff a protobuf-shaped ``message`` reports
    ``HasField(name)`` truthy. Tolerant of non-protobuf inputs so
    the extractor refuses them deterministically.
    """
    has_field = getattr(message, "HasField", None)
    if not callable(has_field):
        return False
    try:
        return bool(has_field(name))
    except Exception:
        return False


def _no_evidence_result(
    reason: str,
    *,
    spl_token_balance_count: int = 0,
    pool_owner_candidate_count: int = 0,
) -> Stage29_1PumpSwapHintExtractionResult:
    """Build a NO_EVIDENCE result with the given closed-set
    reason. All hint slots default to ``None``; the result is
    safe for the Stage 29.1 hint-aware decoder to forward.
    """
    return Stage29_1PumpSwapHintExtractionResult(
        outcome=HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
        base_mint=None,
        pool_account=None,
        quote_mint=None,
        pool_program_id=None,
        provider_pair_type_hint=None,
        provider_quote_asset_hint=None,
        bonding_curve_version_hint=None,
        no_evidence_reason=reason,
        pool_account_evidence_source=(
            POOL_ACCOUNT_EVIDENCE_SOURCE_NONE
        ),
        quote_mint_evidence_source=(
            QUOTE_MINT_EVIDENCE_SOURCE_NONE
        ),
        spl_token_balance_count=spl_token_balance_count,
        pool_owner_candidate_count=pool_owner_candidate_count,
    )


def _collect_spl_token_balance_owner_mints(
    meta: object,
) -> tuple[
    dict[str, set[str]],
    int,
    int,
]:
    """Walk ``meta.pre_token_balances`` + ``meta.post_token_balances``
    and project them into an owner-to-mint-set mapping.

    Returns ``(owner_to_mints, raw_balance_count,
    spl_balance_count)``:

      * ``owner_to_mints`` is a dict mapping each SPL Token /
        Token-2022 ``owner`` string to the set of ``mint``
        strings observed under that owner. Entries owned by any
        other program (mock token programs, future extensions,
        malformed entries with empty / non-string fields) are
        skipped silently.
      * ``raw_balance_count`` is the total number of pre + post
        TokenBalance entries the meta carried before filtering.
      * ``spl_balance_count`` is the count after filtering to
        SPL Token / Token-2022 entries, deduplicated by
        ``(owner, mint)``.

    Pure / deterministic. The mapping order is insertion-order
    (Python dict preserves it) and the inner sets are deterministic
    because we add deduplicated string values.
    """
    owner_to_mints: dict[str, set[str]] = {}
    raw_balance_count = 0
    spl_balance_count = 0
    seen_pairs: set[tuple[str, str]] = set()

    pre = list(getattr(meta, "pre_token_balances", []))
    post = list(getattr(meta, "post_token_balances", []))
    for bal in pre + post:
        raw_balance_count += 1
        program_id = getattr(bal, "program_id", "")
        if not is_spl_token_program_id(program_id):
            continue
        owner = getattr(bal, "owner", "")
        mint = getattr(bal, "mint", "")
        if not isinstance(owner, str) or owner == "":
            continue
        if not isinstance(mint, str) or mint == "":
            continue
        pair = (owner, mint)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        spl_balance_count += 1
        mints = owner_to_mints.setdefault(owner, set())
        mints.add(mint)

    return owner_to_mints, raw_balance_count, spl_balance_count


def _select_pool_owner_candidate(
    owner_to_mints: dict[str, set[str]],
) -> tuple[Optional[tuple[str, str, str]], str, int]:
    """Apply the PumpSwap owner-grouping rule to the owner-to-mint
    mapping.

    Returns ``(candidate, reason, candidate_count)``:

      * ``candidate`` is a ``(pool_account, base_mint,
        quote_mint)`` tuple when exactly one owner unambiguously
        identifies a PumpSwap pool; ``None`` otherwise.
      * ``reason`` is the closed-set NO_EVIDENCE reason when
        ``candidate is None``; ``NONE`` when a candidate was
        selected.
      * ``candidate_count`` is the number of owners whose mint
        set held both a known quote and at least one non-quote
        mint (for safe-counter pinning on the result).
    """
    known_quotes = (
        KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT.keys()
    )

    # Per-owner classification.
    candidates: list[tuple[str, str, str]] = []
    saw_multi_non_quote = False
    for owner, mints in owner_to_mints.items():
        owner_known_quotes = [
            m for m in mints if m in known_quotes
        ]
        owner_non_quotes = [
            m for m in mints if m not in known_quotes
        ]
        if not owner_known_quotes:
            continue
        if not owner_non_quotes:
            continue
        # This owner holds at least one known quote and at least
        # one non-quote mint -- counts as a candidate at the
        # safe-counter level.
        if (
            len(owner_known_quotes) != 1
            or len(owner_non_quotes) != 1
        ):
            # Ambiguous on the per-owner axis. Record that we
            # observed a multi-non-quote owner so the caller can
            # surface the precise reason when no clean candidate
            # exists.
            if len(owner_non_quotes) > 1:
                saw_multi_non_quote = True
            continue
        # Deterministic single-quote, single-non-quote owner.
        # Both lists have exactly one element by construction.
        quote_mint = owner_known_quotes[0]
        base_mint = owner_non_quotes[0]
        candidates.append((owner, base_mint, quote_mint))

    if len(candidates) == 1:
        return candidates[0], NO_EVIDENCE_REASON_NONE, 1
    if len(candidates) > 1:
        return (
            None,
            NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES,
            len(candidates),
        )
    # Zero candidates. Distinguish the multi-non-quote case from
    # the no-pool-at-all case.
    if saw_multi_non_quote:
        return (
            None,
            (
                NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS
            ),
            0,
        )
    return (
        None,
        NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE,
        0,
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def extract_pumpswap_hints(
    update: object,
) -> Stage29_1PumpSwapHintExtractionResult:
    """Extract PumpSwap mint / pool / quote hints from a single
    Yellowstone ``SubscribeUpdate`` message.

    Pure / deterministic. The extractor:

      * refuses any input that is not a ``SubscribeUpdate``
        protobuf shape with the ``transaction`` oneof set
        (returns NO_EVIDENCE with
        ``UPDATE_NOT_TRANSACTION``),
      * skips vote transactions
        (``TRANSACTION_IS_VOTE_SKIPPED``),
      * refuses to extract hints from failed transactions
        (``meta.err`` set ->
        ``TRANSACTION_FAILED_PER_META_ERR``),
      * walks ``meta.pre_token_balances`` +
        ``meta.post_token_balances``, filters to SPL Token /
        Token-2022 entries, groups by ``owner``,
      * applies the closed-set PumpSwap owner-grouping rule
        documented above to identify a single unambiguous pool,
      * populates the four-axis hint quartet (base_mint /
        pool_account / quote_mint / pool_program_id) and the
        provider_pair_type_hint / provider_quote_asset_hint
        slots only when the rule yields exactly one candidate;
        leaves every slot ``None`` and emits a closed-set
        no_evidence_reason otherwise,
      * never fabricates a SOL hint, never fabricates a USDC
        hint, never invents a mint / pool / program-id value.
    """
    if not isinstance(update, _geyser_pb2.SubscribeUpdate):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
        )
    if not _has_field(update, "transaction"):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
        )

    tx_wrapper = update.transaction
    if not _has_field(tx_wrapper, "transaction"):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION,
        )
    tx_info = tx_wrapper.transaction

    if bool(getattr(tx_info, "is_vote", False)):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED,
        )

    if not _has_field(tx_info, "meta"):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_META_MISSING,
        )
    meta = tx_info.meta

    if _has_field(meta, "err"):
        return _no_evidence_result(
            NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR,
        )

    (
        owner_to_mints,
        raw_balance_count,
        spl_balance_count,
    ) = _collect_spl_token_balance_owner_mints(meta)

    if raw_balance_count == 0:
        return _no_evidence_result(
            NO_EVIDENCE_REASON_NO_TOKEN_BALANCES,
        )
    if spl_balance_count == 0:
        return _no_evidence_result(
            (
                NO_EVIDENCE_REASON_NO_SPL_TOKEN_PROGRAM_TOKEN_BALANCES
            ),
            spl_token_balance_count=0,
        )

    (
        candidate,
        reason,
        candidate_count,
    ) = _select_pool_owner_candidate(owner_to_mints)

    if candidate is None:
        return _no_evidence_result(
            reason,
            spl_token_balance_count=spl_balance_count,
            pool_owner_candidate_count=candidate_count,
        )

    pool_account, base_mint, quote_mint = candidate
    provider_pair_type_hint = (
        KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT[quote_mint]
    )
    provider_quote_asset_hint = (
        KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT[quote_mint]
    )

    return Stage29_1PumpSwapHintExtractionResult(
        outcome=HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
        base_mint=base_mint,
        pool_account=pool_account,
        quote_mint=quote_mint,
        pool_program_id=PUMPSWAP_PROGRAM_ID,
        provider_pair_type_hint=provider_pair_type_hint,
        provider_quote_asset_hint=provider_quote_asset_hint,
        bonding_curve_version_hint=None,
        no_evidence_reason=NO_EVIDENCE_REASON_NONE,
        pool_account_evidence_source=(
            POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
        ),
        quote_mint_evidence_source=(
            QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
        ),
        spl_token_balance_count=spl_balance_count,
        pool_owner_candidate_count=candidate_count,
    )


__all__ = (
    "extract_pumpswap_hints",
)
