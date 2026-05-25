"""Stage 29.1 PumpSwap hint-aware decoder.

Thin composition layer that calls the unchanged Stage 28.11
decoder for the safe-shape projection, calls the Stage 29.1
PumpSwap hint extractor for the hint axes, and (when hints were
successfully extracted) rebuilds a single new Stage 28.10 payload
record with the hint slots populated AND the placeholder
``mint`` slot overridden to the extracted ``base_mint``.

The Stage 28.11 client / decoder / generated-stub surface is NOT
modified at Stage 29.1. The hint-aware decoder is a Stage 29.1
sibling that wraps the Stage 28.11 baseline.

The decoder returns ``(payload, extraction_result)`` so callers
(the Stage 29.1 live probe + offline tests) can inspect both:

  * the ``payload`` is always a valid Stage 28.10
    ``Stage28_10ChainstackYellowstonePayload`` -- either the
    baseline Stage 28.11 payload (mint = placeholder, every
    hint slot ``None``) when the extractor reported NO_EVIDENCE
    OR the rebuilt hinted payload when the extractor reported
    HINTS_EXTRACTED;
  * the ``extraction_result`` is the
    ``Stage29_1PumpSwapHintExtractionResult`` the extractor
    returned (or a refused variant carrying
    ``BASE_MINT_REJECTED_SAFE_SHAPE`` / ``POOL_ACCOUNT_REJECTED_SAFE_SHAPE``
    when the Stage 28.10 payload builder refused the
    extractor's strings).

This module imports ONLY stdlib (``typing``) plus the Stage 28.10
models module (for ``build_chainstack_yellowstone_payload`` +
the closed-set instruction-kind token), the Stage 28.11 decoder
module, the Stage 28.11 decode-error type, the Stage 28.11
placeholder-mint constant, and the Stage 29.1 extractor + models.
It does NOT import:

  * Stage 21-27 production code,
  * Stage 28.0 - 28.9 production code beyond the Stage 28.10
    models and Stage 28.11 decoder modules,
  * ``grpc`` / ``grpcio`` (gRPC is the live-probe module's
    surface),
  * any network / RPC / messaging / DB / scheduler / wallet /
    trading / Discord / Telegram / X / dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level I/O at import time.
  * No fabrication: the hinted payload's slots are sourced
    directly from the extractor; the extractor sources them
    directly from upstream evidence.
  * The placeholder mint is overridden ONLY when the extractor
    returned HINTS_EXTRACTED. NO_EVIDENCE preserves the
    baseline (mint = placeholder).
  * The Stage 28.10 payload builder's safe-shape validators
    run on EVERY rebuilt payload. A rejection (e.g. base mint
    starts with a WIF prefix) is caught and reported as a
    NO_EVIDENCE result with a closed-set reason; the baseline
    payload is returned in that case so downstream consumers
    still receive a valid record.
"""

from __future__ import annotations

from typing import Tuple

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    STAGE28_11_PLACEHOLDER_MINT,
    decode_subscribe_update_to_payload,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11DecodeError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    INSTRUCTION_KIND_PUMP_SWAP,
    Stage28_10ChainstackYellowstoneError,
    Stage28_10ChainstackYellowstonePayload,
    build_chainstack_yellowstone_payload,
)
from PHX2.stage29.pumpswap_hint_extractor import (
    extract_pumpswap_hints,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    HINT_EXTRACTION_OUTCOME_NO_EVIDENCE,
    NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE,
    NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE,
    POOL_ACCOUNT_EVIDENCE_SOURCE_NONE,
    QUOTE_MINT_EVIDENCE_SOURCE_NONE,
    Stage29_1PumpSwapHintExtractionResult,
)


def _refused_extraction_result(
    *,
    reason: str,
    spl_token_balance_count: int,
    pool_owner_candidate_count: int,
) -> Stage29_1PumpSwapHintExtractionResult:
    """Build a NO_EVIDENCE result that records the Stage 28.10
    builder rejected the extractor's hinted values. The result
    preserves the extractor's safe counters so the operator
    artifact still records how many TokenBalance entries were
    considered.
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


def decode_subscribe_update_with_pumpswap_hints(
    update: object,
    *,
    provider_name: str,
) -> Tuple[
    Stage28_10ChainstackYellowstonePayload,
    Stage29_1PumpSwapHintExtractionResult,
]:
    """Decode one Yellowstone ``SubscribeUpdate`` into a
    ``(payload, extraction_result)`` pair.

    Pure / deterministic.

      1. The Stage 28.11 baseline decoder is called first; its
         exception (``Stage28_11DecodeError``) is re-raised verbatim
         so the caller sees the same shape it would see when
         calling Stage 28.11 alone. The baseline decoder enforces
         the upstream protobuf shape and rejects vote /
         malformed transactions.
      2. The Stage 29.1 PumpSwap hint extractor is called on the
         same ``update``. It returns either a NO_EVIDENCE result
         (with a closed-set reason) or a HINTS_EXTRACTED result.
      3. NO_EVIDENCE -> return ``(baseline_payload,
         extraction_result)`` unchanged. Downstream consumers see
         a baseline payload with mint = placeholder and every
         hint slot ``None``.
      4. HINTS_EXTRACTED -> attempt to rebuild a new
         ``Stage28_10ChainstackYellowstonePayload`` via
         ``build_chainstack_yellowstone_payload`` with:

           * ``mint`` overridden from the Stage 28.11 placeholder
             to the extractor's ``base_mint``,
           * ``instruction_kind`` overridden from ``UNKNOWN`` to
             ``PUMP_SWAP``,
           * the four hint slots (``quote_mint``, ``pool_account``,
             ``pool_program_id``, ``base_mint``) populated from
             the extractor,
           * the two provider-side hint slots
             (``provider_quote_asset_hint``,
             ``provider_pair_type_hint``) populated,
           * ``bonding_curve_version_hint`` and
             ``provider_bonding_curve_version_hint`` left
             ``None`` (Stage 29.1 does not decode bonding-curve
             evidence).

         If the Stage 28.10 builder raises (e.g. the base_mint
         string trips the WIF private-key-like guard at
         ``is_safe_payload_string``), the rejection is caught
         and the function returns ``(baseline_payload,
         refused_extraction_result)`` where the refused result
         carries the closed-set reason
         ``BASE_MINT_REJECTED_SAFE_SHAPE`` (the most common
         cause; the function uses a coarse heuristic on the
         error's reason token to pick between
         ``BASE_MINT_REJECTED_SAFE_SHAPE`` and
         ``POOL_ACCOUNT_REJECTED_SAFE_SHAPE``).
    """
    baseline_payload = decode_subscribe_update_to_payload(
        update,
        provider_name=provider_name,
    )

    extraction = extract_pumpswap_hints(update)
    if extraction.outcome == HINT_EXTRACTION_OUTCOME_NO_EVIDENCE:
        return baseline_payload, extraction

    # HINTS_EXTRACTED: rebuild payload with hint slots populated.
    try:
        hinted_payload = build_chainstack_yellowstone_payload(
            provider_event_id=baseline_payload.provider_event_id,
            provider_name=baseline_payload.provider_name,
            source_kind=baseline_payload.source_kind,
            mint=extraction.base_mint,
            event_type=baseline_payload.event_type,
            observed_at_utc=baseline_payload.observed_at_utc,
            slot=baseline_payload.slot,
            signature=baseline_payload.signature,
            instruction_kind=INSTRUCTION_KIND_PUMP_SWAP,
            decoded_fields=dict(baseline_payload.decoded_fields),
            chain=baseline_payload.chain,
            quote_mint=extraction.quote_mint,
            pool_account=extraction.pool_account,
            pool_program_id=extraction.pool_program_id,
            base_mint=extraction.base_mint,
            bonding_curve_version_hint=None,
            provider_quote_asset_hint=(
                extraction.provider_quote_asset_hint
            ),
            provider_pair_type_hint=(
                extraction.provider_pair_type_hint
            ),
            provider_bonding_curve_version_hint=None,
        )
    except Stage28_10ChainstackYellowstoneError as err:
        # The Stage 28.10 factory rejected one of the projected
        # hint values. The error's ``field_name`` attribute (when
        # present) tells us whether the base mint or the pool
        # account tripped the safe-shape guard; default to the
        # base_mint reason when the field is unknown.
        field_name = getattr(err, "field_name", "")
        if field_name == "pool_account":
            reason = (
                NO_EVIDENCE_REASON_POOL_ACCOUNT_REJECTED_SAFE_SHAPE
            )
        else:
            reason = (
                NO_EVIDENCE_REASON_BASE_MINT_REJECTED_SAFE_SHAPE
            )
        refused = _refused_extraction_result(
            reason=reason,
            spl_token_balance_count=(
                extraction.spl_token_balance_count
            ),
            pool_owner_candidate_count=(
                extraction.pool_owner_candidate_count
            ),
        )
        return baseline_payload, refused

    return hinted_payload, extraction


def is_hint_bearing_payload(
    payload: Stage28_10ChainstackYellowstonePayload,
) -> bool:
    """Return ``True`` iff ``payload`` carries non-None values on
    the Stage 29.1 hint-bearing quartet (base_mint, pool_account,
    quote_mint, pool_program_id) AND a closed-set
    ``provider_pair_type_hint`` AND ``mint`` is NOT the Stage
    28.11 placeholder. Used by the Stage 29.1 live probe to
    distinguish a hinted result from a baseline result.

    Pure / deterministic. Returns ``False`` for non-payload
    inputs.
    """
    if not isinstance(
        payload, Stage28_10ChainstackYellowstonePayload,
    ):
        return False
    if payload.mint == STAGE28_11_PLACEHOLDER_MINT:
        return False
    if payload.base_mint is None or payload.base_mint == "":
        return False
    if payload.pool_account is None or payload.pool_account == "":
        return False
    if payload.quote_mint is None or payload.quote_mint == "":
        return False
    if (
        payload.pool_program_id is None
        or payload.pool_program_id == ""
    ):
        return False
    if payload.provider_pair_type_hint not in (
        "PUMP_SOL", "PUMP_USDC",
    ):
        return False
    return True


# The geyser_pb2 import above is intentional. It pins the Stage
# 29.1 hint-aware decoder to the same generated-stub package the
# Stage 28.11 decoder uses, so the boundary scan can assert this
# module is allowed to depend on it.
_GENERATED_STUB_MARKER: object = _geyser_pb2.SubscribeUpdate


__all__ = (
    "decode_subscribe_update_with_pumpswap_hints",
    "is_hint_bearing_payload",
)
