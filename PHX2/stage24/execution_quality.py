"""Stage 24.6 execution-quality primitive evaluator.

This module composes an observe-only per-transaction execution-
quality record from the upstream transaction metadata and the
already-decoded Stage 24.2 / 24.3 / 24.4 fee primitives. It is
NOT a decoder of new instruction bytes; it joins outputs that
the per-fee decoders already produced and surfaces transaction-
landing evidence.

Scope (Stage 24.6):

  * Compose ``Stage24ExecutionQualityResult`` from a
    ``Stage24ExecutionInput`` plus optional upstream
    ``Stage24ComputeBudgetResult`` / ``Stage24PriorityFeeResult``
    / ``Stage24JitoTipResult`` / ``Stage24RouterFeeResult`` records.
  * Carry ``landed`` / ``landed_slot`` / ``submitted_slot`` /
    ``slot_delta`` / realized priority-fee / realized Jito-tip /
    realized router-fee (always ``None`` at 24.6 per the Stage
    24.5 lock) and a short non-secret ``error_code``.
  * Record observed-only counters such as
    ``compute_unit_utilization_ratio`` (only when both
    ``compute_units_consumed`` and ``compute_unit_limit`` are
    present) in the numeric features.

Out of scope:

  * Decoded router/global-fee amount extraction. Stage 24.5 took
    Path B; ``realized_router_fee_lamports`` stays ``None`` and
    a ``ROUTER_FEE_NOT_CONFIRMED`` reason is recorded for every
    transaction the upstream router-fee surface saw an active
    program for.
  * Thresholds, classification, or quality scoring. Stage 24 is
    observe-only; quality classification is a Stage 26 concern.

Honesty rules (mirrors Stage 24 brainstorm doc Section 14):

  * ``transaction_status`` decoded as a clear-success token
    (``"success"`` / ``"ok"``) -> ``landed = True``.
  * ``transaction_status`` decoded as a clear-failure token
    (``"err"`` / ``"error"`` / ``"failed"`` / ``"failure"``) ->
    ``landed = False``.
  * ``transaction_status`` empty / unknown token -> ``landed =
    None`` and a ``EXECUTION_QUALITY_LANDING_UNKNOWN`` reason is
    recorded.
  * Failed transactions never claim a positive landed-quality
    decode -- ``data_status`` falls back to ``PARTIAL`` and
    ``confidence_level`` to ``LOW``.
  * ``compute_unit_utilization_ratio`` is computed ONLY when both
    ``compute_units_consumed`` (from upstream meta) and the
    decoded ``unit_limit`` are non-negative ints; otherwise the
    field is ``None`` and the reason
    ``COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE`` is recorded.
  * The realized priority-fee field carries the upstream Stage
    24.2 ``amount_lamports`` value when the priority-fee decoder
    confidently decoded a value (``decoder_status=DECODED``).
    For ``PARTIAL`` / ``DECODE_UNCONFIRMED`` / other statuses,
    the realized value stays ``None`` and a
    ``PRIORITY_FEE_NOT_CONFIRMED`` reason is recorded.
  * The realized Jito-tip field carries the upstream Stage 24.3
    ``amount_lamports`` value only when the Jito-tip decoder
    confidently decoded a value. Otherwise the realized value
    stays ``None`` and a ``JITO_TIP_NOT_CONFIRMED`` reason is
    recorded.
  * The realized router-fee field is always ``None`` at Stage
    24.6 because Stage 24.5 took Path B (no confirmed decoder).
    The reason ``ROUTER_FEE_NOT_CONFIRMED`` is recorded when the
    upstream router-fee surface saw an active program.

This module imports only stdlib (``types`` / ``typing``) plus
the Stage 24 constants and models. It does NOT import Stage 21
/ Stage 22 / Stage 23 modules; it does NOT import any network /
RPC / messaging / DB / scheduler / secrets-management library;
it does NOT read the process environment; it does NOT define a
CLI surface; and it contains no top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional

from PHX2.stage24.constants import (
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODED,
    DECODER_STATUS_PARTIAL,
    DEFAULT_THRESHOLD_VERSION,
    EXECUTION_QUALITY_DECODER_NAME,
    EXECUTION_QUALITY_DECODER_VERSION,
    FEE_SOURCE_UNKNOWN,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
    STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER,
)
from PHX2.stage24.models import (
    Stage24ComputeBudgetResult,
    Stage24ExecutionInput,
    Stage24ExecutionQualityResult,
    Stage24JitoTipResult,
    Stage24PriorityFeeResult,
    Stage24RouterFeeResult,
    build_execution_quality_result,
)


# ---------------------------------------------------------------------------
# Locked token sets (transaction-status interpretation)
# ---------------------------------------------------------------------------


_LANDED_SUCCESS_TOKENS: frozenset[str] = frozenset(
    {"success", "ok"}
)
_LANDED_FAILURE_TOKENS: frozenset[str] = frozenset(
    {"err", "error", "failed", "failure"}
)


# ---------------------------------------------------------------------------
# Meta-field keys consumed for utilization ratio + submitted-slot
# ---------------------------------------------------------------------------


META_KEY_COMPUTE_UNITS_CONSUMED: str = "compute_units_consumed"
META_KEY_SUBMITTED_SLOT: str = "submitted_slot"
META_KEY_ERROR_CODE: str = "error_code"


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


REASON_EXECUTION_QUALITY_LANDED: str = "EXECUTION_QUALITY_LANDED"
REASON_EXECUTION_QUALITY_FAILED: str = "EXECUTION_QUALITY_FAILED"
REASON_EXECUTION_QUALITY_LANDING_UNKNOWN: str = (
    "EXECUTION_QUALITY_LANDING_UNKNOWN"
)
REASON_PRIORITY_FEE_NOT_CONFIRMED: str = "PRIORITY_FEE_NOT_CONFIRMED"
REASON_JITO_TIP_NOT_CONFIRMED: str = "JITO_TIP_NOT_CONFIRMED"
REASON_ROUTER_FEE_NOT_CONFIRMED: str = "ROUTER_FEE_NOT_CONFIRMED"
REASON_COMPUTE_UNIT_UTILIZATION_DERIVED: str = (
    "COMPUTE_UNIT_UTILIZATION_DERIVED"
)
REASON_COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE: str = (
    "COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE"
)
REASON_EXECUTION_QUALITY_OBSERVE_ONLY: str = (
    "EXECUTION_QUALITY_OBSERVE_ONLY"
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _classify_landed(
    transaction_status: str,
) -> tuple[Optional[bool], bool]:
    """Classify ``transaction_status`` into ``(landed, is_unknown)``."""
    if not isinstance(transaction_status, str):
        return None, True
    token = transaction_status.strip().lower()
    if token == "":
        return None, True
    if token in _LANDED_SUCCESS_TOKENS:
        return True, False
    if token in _LANDED_FAILURE_TOKENS:
        return False, False
    return None, True


def _project_non_negative_int(
    *,
    meta: Mapping[str, object],
    key: str,
) -> Optional[int]:
    """Return ``meta[key]`` if it is a non-negative ``int`` (not bool); else None."""
    raw = meta.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if not isinstance(raw, int):
        return None
    if raw < 0:
        return None
    return raw


def _project_short_error_code(meta: Mapping[str, object]) -> str:
    """Return a short non-secret error code from meta, or ``""``.

    The Stage 24 contract forbids surfacing raw RPC exception
    messages. The reader has already rejected secret-bearing
    fields at the input layer; this helper additionally caps the
    error-code string to a safe short length and falls back to
    ``""`` for any unexpected shape.
    """
    raw = meta.get(META_KEY_ERROR_CODE)
    if not isinstance(raw, str):
        return ""
    if raw == "":
        return ""
    if len(raw) > 64:
        return ""
    return raw


def _is_router_fee_active_candidate(
    router_fee_result: Optional[Stage24RouterFeeResult],
) -> bool:
    """Return True when the router-fee surface saw an active program."""
    if router_fee_result is None:
        return False
    route_family = router_fee_result.route_family
    return route_family != ROUTE_FAMILY_NO_ROUTER_DETECTED and (
        router_fee_result.decoder_status != DECODER_STATUS_ABSENT
    )


def _resolve_realized_priority_fee(
    priority_fee_result: Optional[Stage24PriorityFeeResult],
) -> Optional[int]:
    if priority_fee_result is None:
        return None
    if priority_fee_result.decoder_status != DECODER_STATUS_DECODED:
        return None
    return priority_fee_result.amount_lamports


def _resolve_realized_jito_tip(
    jito_tip_result: Optional[Stage24JitoTipResult],
) -> Optional[int]:
    if jito_tip_result is None:
        return None
    if jito_tip_result.decoder_status != DECODER_STATUS_DECODED:
        return None
    return jito_tip_result.amount_lamports


def _compute_utilization_basis_points(
    *,
    compute_units_consumed: Optional[int],
    compute_unit_limit: Optional[int],
) -> Optional[int]:
    """Return utilization ratio in basis points (0..10_000), or None.

    Stage 24 carries the ratio as an integer (basis points) so
    the canonical-JSON encoding stays float-free. ``None`` when
    either input is missing or the limit is zero.
    """
    if compute_units_consumed is None or compute_unit_limit is None:
        return None
    if compute_unit_limit == 0:
        return None
    basis_points = (compute_units_consumed * 10_000) // compute_unit_limit
    if basis_points < 0:
        return None
    return basis_points


# ---------------------------------------------------------------------------
# Public evaluator
# ---------------------------------------------------------------------------


def evaluate_execution_quality(
    *,
    execution_input: Stage24ExecutionInput,
    compute_budget_result: Optional[Stage24ComputeBudgetResult] = None,
    priority_fee_result: Optional[Stage24PriorityFeeResult] = None,
    jito_tip_result: Optional[Stage24JitoTipResult] = None,
    router_fee_result: Optional[Stage24RouterFeeResult] = None,
) -> Stage24ExecutionQualityResult:
    """Compose an observe-only execution-quality primitive.

    Pure function: depends only on the upstream record arguments.
    No side effects, no network, no env reads.
    """
    landed, landing_unknown = _classify_landed(
        execution_input.transaction_status
    )
    landed_slot = execution_input.slot
    submitted_slot_value = _project_non_negative_int(
        meta=execution_input.meta,
        key=META_KEY_SUBMITTED_SLOT,
    )
    submitted_slot_int = (
        submitted_slot_value if submitted_slot_value is not None else -1
    )
    if (
        submitted_slot_value is not None
        and isinstance(landed_slot, int)
        and landed_slot >= 0
    ):
        slot_delta: Optional[int] = landed_slot - submitted_slot_value
    else:
        slot_delta = None

    consumed_units = _project_non_negative_int(
        meta=execution_input.meta,
        key=META_KEY_COMPUTE_UNITS_CONSUMED,
    )
    compute_unit_limit = (
        compute_budget_result.unit_limit
        if compute_budget_result is not None
        else None
    )
    utilization_basis_points = _compute_utilization_basis_points(
        compute_units_consumed=consumed_units,
        compute_unit_limit=compute_unit_limit,
    )

    realized_priority_fee_lamports = _resolve_realized_priority_fee(
        priority_fee_result
    )
    realized_jito_tip_lamports = _resolve_realized_jito_tip(
        jito_tip_result
    )
    # Stage 24.5 took Path B: no confirmed router/global-fee
    # decoder exists, so the realized router-fee field is always
    # None. This is a hard invariant the runner / writer rely on.
    realized_router_fee_lamports: Optional[int] = None

    router_fee_active_candidate = _is_router_fee_active_candidate(
        router_fee_result
    )

    reasons: list[str] = [REASON_EXECUTION_QUALITY_OBSERVE_ONLY]
    if landed is True:
        reasons.append(REASON_EXECUTION_QUALITY_LANDED)
    elif landed is False:
        reasons.append(REASON_EXECUTION_QUALITY_FAILED)
    if landing_unknown:
        reasons.append(REASON_EXECUTION_QUALITY_LANDING_UNKNOWN)

    if utilization_basis_points is None:
        reasons.append(REASON_COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE)
    else:
        reasons.append(REASON_COMPUTE_UNIT_UTILIZATION_DERIVED)

    if realized_priority_fee_lamports is None:
        reasons.append(REASON_PRIORITY_FEE_NOT_CONFIRMED)
    if realized_jito_tip_lamports is None:
        reasons.append(REASON_JITO_TIP_NOT_CONFIRMED)
    if router_fee_active_candidate:
        reasons.append(REASON_ROUTER_FEE_NOT_CONFIRMED)

    # decoder_status / data_status / confidence:
    # - landed True with at least one fee primitive informed:
    #   PARTIAL (we never claim DECODED for execution quality
    #   in Stage 24.6 because the router-fee surface is
    #   unconfirmed).
    # - landed False: PARTIAL with low confidence; failed txs
    #   never get a HIGH quality decode.
    # - landing unknown: ABSENT / MISSING / NONE.
    if landed is None:
        decoder_status = DECODER_STATUS_ABSENT
        data_status = DATA_STATUS_MISSING
        confidence_level = CONFIDENCE_LEVEL_NONE
    elif landed is False:
        decoder_status = DECODER_STATUS_PARTIAL
        data_status = DATA_STATUS_PARTIAL
        confidence_level = CONFIDENCE_LEVEL_MEDIUM
    else:
        # Landed successfully. We never escalate to DECODED
        # because the router-fee surface is unconfirmed (Stage
        # 24.5 Path B). The data_status is COMPLETE when both
        # the priority-fee surface decoded and utilization was
        # derivable; PARTIAL otherwise.
        priority_fee_confidently_decoded = (
            realized_priority_fee_lamports is not None
        )
        if (
            priority_fee_confidently_decoded
            and utilization_basis_points is not None
        ):
            decoder_status = DECODER_STATUS_PARTIAL
            data_status = DATA_STATUS_COMPLETE
            confidence_level = CONFIDENCE_LEVEL_MEDIUM
        else:
            decoder_status = DECODER_STATUS_PARTIAL
            data_status = DATA_STATUS_PARTIAL
            confidence_level = CONFIDENCE_LEVEL_MEDIUM

    error_code = _project_short_error_code(execution_input.meta)

    numeric_features: dict[str, object] = {
        "landed_slot": landed_slot,
        "submitted_slot": submitted_slot_int,
        "slot_delta": slot_delta,
        "compute_units_consumed": consumed_units,
        "compute_unit_limit": compute_unit_limit,
        "compute_unit_utilization_basis_points": (
            utilization_basis_points
        ),
        "priority_fee_estimated_lamports": (
            realized_priority_fee_lamports
        ),
        "jito_tip_lamports": realized_jito_tip_lamports,
        "router_fee_amount_lamports": None,
        "execution_fee_components_known_count": _known_components_count(
            priority_fee_known=realized_priority_fee_lamports is not None,
            jito_tip_known=realized_jito_tip_lamports is not None,
        ),
        "execution_fee_components_unknown_count": (
            _unknown_components_count(
                priority_fee_known=(
                    realized_priority_fee_lamports is not None
                ),
                jito_tip_known=realized_jito_tip_lamports is not None,
                router_fee_active_candidate=(
                    router_fee_active_candidate
                ),
            )
        ),
        "router_fee_active_candidate": router_fee_active_candidate,
    }

    evidence: dict[str, object] = {
        "transaction_status": execution_input.transaction_status,
        "transaction_status_normalized": (
            execution_input.transaction_status.strip().lower()
            if isinstance(execution_input.transaction_status, str)
            else ""
        ),
        "router_fee_confirmed_decoder": (
            STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER
        ),
        "compute_budget_decoder_status": (
            compute_budget_result.decoder_status
            if compute_budget_result is not None
            else ""
        ),
        "priority_fee_decoder_status": (
            priority_fee_result.decoder_status
            if priority_fee_result is not None
            else ""
        ),
        "jito_tip_decoder_status": (
            jito_tip_result.decoder_status
            if jito_tip_result is not None
            else ""
        ),
        "router_fee_decoder_status": (
            router_fee_result.decoder_status
            if router_fee_result is not None
            else ""
        ),
        "router_fee_route_family": (
            router_fee_result.route_family
            if router_fee_result is not None
            else ""
        ),
    }

    return build_execution_quality_result(
        decoder_name=EXECUTION_QUALITY_DECODER_NAME,
        decoder_version=EXECUTION_QUALITY_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        landed=landed,
        landed_slot=landed_slot,
        submitted_slot=submitted_slot_int,
        slot_delta=slot_delta,
        realized_priority_fee_lamports=realized_priority_fee_lamports,
        realized_jito_tip_lamports=realized_jito_tip_lamports,
        realized_router_fee_lamports=realized_router_fee_lamports,
        error_code=error_code,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _known_components_count(
    *,
    priority_fee_known: bool,
    jito_tip_known: bool,
) -> int:
    count = 0
    if priority_fee_known:
        count += 1
    if jito_tip_known:
        count += 1
    return count


def _unknown_components_count(
    *,
    priority_fee_known: bool,
    jito_tip_known: bool,
    router_fee_active_candidate: bool,
) -> int:
    count = 0
    if not priority_fee_known:
        count += 1
    if not jito_tip_known:
        count += 1
    # router-fee is always unknown at Stage 24.6 (Path B); it
    # only counts as an "unknown component" when the upstream
    # router-fee surface saw an active program, otherwise it is
    # treated as ABSENT (not unknown).
    if router_fee_active_candidate:
        count += 1
    return count


__all__ = [
    "META_KEY_COMPUTE_UNITS_CONSUMED",
    "META_KEY_ERROR_CODE",
    "META_KEY_SUBMITTED_SLOT",
    "REASON_COMPUTE_UNIT_UTILIZATION_DERIVED",
    "REASON_COMPUTE_UNIT_UTILIZATION_NOT_DERIVABLE",
    "REASON_EXECUTION_QUALITY_FAILED",
    "REASON_EXECUTION_QUALITY_LANDED",
    "REASON_EXECUTION_QUALITY_LANDING_UNKNOWN",
    "REASON_EXECUTION_QUALITY_OBSERVE_ONLY",
    "REASON_JITO_TIP_NOT_CONFIRMED",
    "REASON_PRIORITY_FEE_NOT_CONFIRMED",
    "REASON_ROUTER_FEE_NOT_CONFIRMED",
    "evaluate_execution_quality",
]
