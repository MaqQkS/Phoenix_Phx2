"""Stage 24.6 deterministic decoder runner.

Orchestrates the Stage 24.2 / 24.3 / 24.4 / 24.6 decoders over
a tuple of ``Stage24ExecutionInput`` records and produces an
immutable ``Stage24RunnerResult`` plus the unified per-primitive
``Stage24ExecutionPrimitive`` rows downstream artifact writers
flatten to disk.

Scope (Stage 24.6):

  * Invoke ``decode_compute_budget`` / ``decode_priority_fee`` /
    ``decode_jito_tip`` / ``decode_router_fee_candidate`` /
    ``evaluate_execution_quality`` once per input row.
  * Build the unified per-primitive rows for each decoder
    output, plus the execution-quality row.
  * Carry typed ``Stage24Error`` failures through to a
    deterministic rejection record so the caller can persist
    them without losing the failure mode.
  * Inject ``created_at_utc`` rather than reading the clock.

Out of scope:

  * Reading inputs from disk. The runner consumes already-
    projected ``Stage24ExecutionInput`` records. Disk reads live
    in ``PHX2.stage24.input_reader``.
  * Writing artifacts to disk. The writer lives in
    ``PHX2.stage24.artifact_writer``.
  * Network / RPC / DB / dispatch / scheduler / CLI.
  * Promoting any router/global-fee primitive to ``DECODED``.

This module imports only stdlib (``types`` / ``typing``) plus
the Stage 24 constants, models, errors, and the per-fee
decoders. It does NOT import Stage 21 / Stage 22 / Stage 23
modules; it does NOT import any network / RPC / messaging / DB
/ scheduler / secrets-management library; it does NOT read the
process environment; it does NOT define a CLI surface; and it
contains no top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, NamedTuple, Optional

from PHX2.stage24.compute_budget import decode_compute_budget
from PHX2.stage24.constants import (
    STAGE24_REJECTION_REASON_BUILDER_TYPED_ERROR,
    STAGE24_REJECTION_REASON_DECODER_TYPED_ERROR,
    STAGE24_RUNNER_NAME,
    STAGE24_RUNNER_VERSION,
)
from PHX2.stage24.errors import Stage24Error
from PHX2.stage24.execution_quality import evaluate_execution_quality
from PHX2.stage24.jito_tip import decode_jito_tip
from PHX2.stage24.models import (
    Stage24ComputeBudgetResult,
    Stage24ExecutionInput,
    Stage24ExecutionPrimitive,
    Stage24ExecutionQualityResult,
    Stage24JitoTipResult,
    Stage24PriorityFeeResult,
    Stage24RouterFeeResult,
    Stage24RunnerResult,
    build_execution_primitive,
    build_runner_result,
)
from PHX2.stage24.priority_fee import (
    derive_priority_fee_from_compute_budget,
)
from PHX2.stage24.router_fee import decode_router_fee_candidate


# ---------------------------------------------------------------------------
# Runner identity (re-export for callers)
# ---------------------------------------------------------------------------


RUNNER_NAME: str = STAGE24_RUNNER_NAME
RUNNER_VERSION: str = STAGE24_RUNNER_VERSION


# ---------------------------------------------------------------------------
# Default decoder name list
# ---------------------------------------------------------------------------


def default_decoder_names() -> tuple[str, ...]:
    """Return the canonical list of decoders the runner invokes.

    The order here matches the runner's invocation order and the
    artifact writer's per-primitive sort key for ties on
    ``tx_signature``.
    """
    return (
        "compute_budget",
        "priority_fee",
        "jito_tip",
        "router_fee",
        "execution_quality",
    )


# ---------------------------------------------------------------------------
# Rejection record
# ---------------------------------------------------------------------------


class Stage24RejectionRecord(NamedTuple):
    """One rejection per (input_row, decoder_name) typed failure.

    Stage 24.6 lifts a typed ``Stage24Error`` raised by a
    decoder into this immutable record so the artifact writer
    can serialize it deterministically. The reason is a closed-
    set short token; the detail is a short non-secret label
    derived from the exception's class name (not the message).
    """

    input_id: str
    payload_hash: str
    decoder_name: str
    primitive_family: str
    reason: str
    error_class: str


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _safe_decoder_call(
    *,
    decoder_name: str,
    primitive_family: str,
    fn,
    execution_input: Stage24ExecutionInput,
    rejections: list[Stage24RejectionRecord],
):
    """Invoke ``fn(execution_input)`` and convert Stage24Error to rejection.

    Untyped exceptions are NOT swallowed; they propagate to the
    caller. Only ``Stage24Error`` subclasses are converted to a
    rejection record.
    """
    try:
        return fn(execution_input)
    except Stage24Error as exc:
        rejections.append(
            Stage24RejectionRecord(
                input_id=execution_input.input_id,
                payload_hash=execution_input.payload_hash,
                decoder_name=decoder_name,
                primitive_family=primitive_family,
                reason=STAGE24_REJECTION_REASON_DECODER_TYPED_ERROR,
                error_class=type(exc).__name__,
            )
        )
        return None


def _build_primitive_from_compute_budget(
    *,
    execution_input: Stage24ExecutionInput,
    result: Stage24ComputeBudgetResult,
    created_at_utc: str,
) -> Stage24ExecutionPrimitive:
    return build_execution_primitive(
        tx_signature=execution_input.signature,
        slot=execution_input.slot,
        provider_id=execution_input.provider_id,
        observed_at_utc=execution_input.observed_at_utc,
        primitive_family=result.primitive_family,
        fee_source=result.fee_source,
        decoder_status=result.decoder_status,
        data_status=result.data_status,
        confidence_level=result.confidence_level,
        route_family=result.route_family,
        instruction_location=result.instruction_location,
        program_id=result.program_id,
        amount_lamports=None,
        amount_token=None,
        mint="",
        unit_price_microlamports=result.unit_price_microlamports,
        unit_limit=result.unit_limit,
        reason_codes=result.reason_codes,
        numeric_features=result.numeric_features,
        evidence=result.evidence,
        missing_features=execution_input.missing_fields,
        input_hash=execution_input.payload_hash,
        created_at_utc=created_at_utc,
    )


def _build_primitive_from_priority_fee(
    *,
    execution_input: Stage24ExecutionInput,
    result: Stage24PriorityFeeResult,
    created_at_utc: str,
) -> Stage24ExecutionPrimitive:
    return build_execution_primitive(
        tx_signature=execution_input.signature,
        slot=execution_input.slot,
        provider_id=execution_input.provider_id,
        observed_at_utc=execution_input.observed_at_utc,
        primitive_family=result.primitive_family,
        fee_source=result.fee_source,
        decoder_status=result.decoder_status,
        data_status=result.data_status,
        confidence_level=result.confidence_level,
        route_family=result.route_family,
        instruction_location=result.instruction_location,
        program_id=result.program_id,
        amount_lamports=result.amount_lamports,
        amount_token=None,
        mint="",
        unit_price_microlamports=result.unit_price_microlamports,
        unit_limit=result.unit_limit,
        reason_codes=result.reason_codes,
        numeric_features=result.numeric_features,
        evidence=result.evidence,
        missing_features=execution_input.missing_fields,
        input_hash=execution_input.payload_hash,
        created_at_utc=created_at_utc,
    )


def _build_primitive_from_jito_tip(
    *,
    execution_input: Stage24ExecutionInput,
    result: Stage24JitoTipResult,
    created_at_utc: str,
) -> Stage24ExecutionPrimitive:
    return build_execution_primitive(
        tx_signature=execution_input.signature,
        slot=execution_input.slot,
        provider_id=execution_input.provider_id,
        observed_at_utc=execution_input.observed_at_utc,
        primitive_family=result.primitive_family,
        fee_source=result.fee_source,
        decoder_status=result.decoder_status,
        data_status=result.data_status,
        confidence_level=result.confidence_level,
        route_family=result.route_family,
        instruction_location=result.instruction_location,
        program_id=result.program_id,
        amount_lamports=result.amount_lamports,
        amount_token=None,
        mint="",
        unit_price_microlamports=None,
        unit_limit=None,
        reason_codes=result.reason_codes,
        numeric_features=result.numeric_features,
        evidence=result.evidence,
        missing_features=execution_input.missing_fields,
        input_hash=execution_input.payload_hash,
        created_at_utc=created_at_utc,
    )


def _build_primitive_from_router_fee(
    *,
    execution_input: Stage24ExecutionInput,
    result: Stage24RouterFeeResult,
    created_at_utc: str,
) -> Stage24ExecutionPrimitive:
    return build_execution_primitive(
        tx_signature=execution_input.signature,
        slot=execution_input.slot,
        provider_id=execution_input.provider_id,
        observed_at_utc=execution_input.observed_at_utc,
        primitive_family=result.primitive_family,
        fee_source=result.fee_source,
        decoder_status=result.decoder_status,
        data_status=result.data_status,
        confidence_level=result.confidence_level,
        route_family=result.route_family,
        instruction_location=result.instruction_location,
        program_id=result.program_id,
        amount_lamports=result.amount_lamports,
        amount_token=result.amount_token,
        mint=result.mint,
        unit_price_microlamports=None,
        unit_limit=None,
        reason_codes=result.reason_codes,
        numeric_features=result.numeric_features,
        evidence=result.evidence,
        missing_features=execution_input.missing_fields,
        input_hash=execution_input.payload_hash,
        created_at_utc=created_at_utc,
    )


def _build_primitive_from_execution_quality(
    *,
    execution_input: Stage24ExecutionInput,
    result: Stage24ExecutionQualityResult,
    created_at_utc: str,
) -> Stage24ExecutionPrimitive:
    numeric_features = result.numeric_features
    landed_value = result.landed
    extra_evidence: dict[str, object] = dict(result.evidence)
    extra_evidence["landed"] = (
        None if landed_value is None else bool(landed_value)
    )
    extra_evidence["error_code"] = result.error_code
    return build_execution_primitive(
        tx_signature=execution_input.signature,
        slot=execution_input.slot,
        provider_id=execution_input.provider_id,
        observed_at_utc=execution_input.observed_at_utc,
        primitive_family=result.primitive_family,
        fee_source=result.fee_source,
        decoder_status=result.decoder_status,
        data_status=result.data_status,
        confidence_level=result.confidence_level,
        route_family=result.route_family,
        instruction_location="UNKNOWN",
        program_id="",
        amount_lamports=result.realized_priority_fee_lamports,
        amount_token=None,
        mint="",
        unit_price_microlamports=None,
        unit_limit=None,
        reason_codes=result.reason_codes,
        numeric_features=numeric_features,
        evidence=MappingProxyType(extra_evidence),
        missing_features=execution_input.missing_fields,
        input_hash=execution_input.payload_hash,
        created_at_utc=created_at_utc,
    )


def _sort_inputs_deterministically(
    execution_inputs: tuple[Stage24ExecutionInput, ...],
) -> tuple[Stage24ExecutionInput, ...]:
    """Return ``execution_inputs`` sorted by ``(input_id, payload_hash)``."""
    return tuple(
        sorted(
            execution_inputs,
            key=lambda ei: (ei.input_id, ei.payload_hash),
        )
    )


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------


def run_stage24_decoders(
    *,
    execution_inputs: tuple[Stage24ExecutionInput, ...],
    created_at_utc: str,
) -> tuple[Stage24RunnerResult, tuple[Stage24RejectionRecord, ...]]:
    """Run the Stage 24 decoders over ``execution_inputs``.

    Pure function: depends only on the arguments. Returns a
    ``(Stage24RunnerResult, rejections_tuple)`` pair. The
    rejections tuple is empty when every decoder accepted every
    input. The runner does NOT swallow untyped exceptions: an
    unexpected ``Exception`` propagates to the caller.
    """
    if not isinstance(execution_inputs, tuple):
        raise TypeError("execution_inputs must be a tuple")
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise ValueError(
            "created_at_utc must be a non-empty string"
        )
    for ei in execution_inputs:
        if not isinstance(ei, Stage24ExecutionInput):
            raise TypeError(
                "every execution_inputs entry must be a "
                "Stage24ExecutionInput"
            )

    ordered = _sort_inputs_deterministically(execution_inputs)

    compute_budget_results: list[Stage24ComputeBudgetResult] = []
    priority_fee_results: list[Stage24PriorityFeeResult] = []
    jito_tip_results: list[Stage24JitoTipResult] = []
    router_fee_results: list[Stage24RouterFeeResult] = []
    execution_quality_results: list[Stage24ExecutionQualityResult] = []
    execution_primitives: list[Stage24ExecutionPrimitive] = []
    rejections: list[Stage24RejectionRecord] = []

    for execution_input in ordered:
        cb_result = _safe_decoder_call(
            decoder_name="compute_budget",
            primitive_family="COMPUTE_BUDGET",
            fn=decode_compute_budget,
            execution_input=execution_input,
            rejections=rejections,
        )
        pf_result: Optional[Stage24PriorityFeeResult]
        if cb_result is None:
            pf_result = None
        else:
            try:
                pf_result = derive_priority_fee_from_compute_budget(
                    execution_input=execution_input,
                    compute_budget_result=cb_result,
                )
            except Stage24Error as exc:
                rejections.append(
                    Stage24RejectionRecord(
                        input_id=execution_input.input_id,
                        payload_hash=execution_input.payload_hash,
                        decoder_name="priority_fee",
                        primitive_family="PRIORITY_FEE",
                        reason=(
                            STAGE24_REJECTION_REASON_DECODER_TYPED_ERROR
                        ),
                        error_class=type(exc).__name__,
                    )
                )
                pf_result = None

        jt_result = _safe_decoder_call(
            decoder_name="jito_tip",
            primitive_family="JITO_TIP",
            fn=decode_jito_tip,
            execution_input=execution_input,
            rejections=rejections,
        )
        rf_result = _safe_decoder_call(
            decoder_name="router_fee",
            primitive_family="ROUTER_FEE",
            fn=decode_router_fee_candidate,
            execution_input=execution_input,
            rejections=rejections,
        )

        try:
            eq_result = evaluate_execution_quality(
                execution_input=execution_input,
                compute_budget_result=cb_result,
                priority_fee_result=pf_result,
                jito_tip_result=jt_result,
                router_fee_result=rf_result,
            )
        except Stage24Error as exc:
            rejections.append(
                Stage24RejectionRecord(
                    input_id=execution_input.input_id,
                    payload_hash=execution_input.payload_hash,
                    decoder_name="execution_quality",
                    primitive_family="EXECUTION_QUALITY",
                    reason=STAGE24_REJECTION_REASON_BUILDER_TYPED_ERROR,
                    error_class=type(exc).__name__,
                )
            )
            eq_result = None

        if cb_result is not None:
            compute_budget_results.append(cb_result)
            execution_primitives.append(
                _build_primitive_from_compute_budget(
                    execution_input=execution_input,
                    result=cb_result,
                    created_at_utc=created_at_utc,
                )
            )
        if pf_result is not None:
            priority_fee_results.append(pf_result)
            execution_primitives.append(
                _build_primitive_from_priority_fee(
                    execution_input=execution_input,
                    result=pf_result,
                    created_at_utc=created_at_utc,
                )
            )
        if jt_result is not None:
            jito_tip_results.append(jt_result)
            execution_primitives.append(
                _build_primitive_from_jito_tip(
                    execution_input=execution_input,
                    result=jt_result,
                    created_at_utc=created_at_utc,
                )
            )
        if rf_result is not None:
            router_fee_results.append(rf_result)
            execution_primitives.append(
                _build_primitive_from_router_fee(
                    execution_input=execution_input,
                    result=rf_result,
                    created_at_utc=created_at_utc,
                )
            )
        if eq_result is not None:
            execution_quality_results.append(eq_result)
            execution_primitives.append(
                _build_primitive_from_execution_quality(
                    execution_input=execution_input,
                    result=eq_result,
                    created_at_utc=created_at_utc,
                )
            )

    runner_result = build_runner_result(
        compute_budget_results=tuple(compute_budget_results),
        priority_fee_results=tuple(priority_fee_results),
        jito_tip_results=tuple(jito_tip_results),
        router_fee_results=tuple(router_fee_results),
        execution_quality_results=tuple(execution_quality_results),
        execution_primitives=tuple(execution_primitives),
        input_count=len(ordered),
        input_rejection_count=len(rejections),
        created_at_utc=created_at_utc,
    )
    return runner_result, tuple(rejections)


__all__ = [
    "RUNNER_NAME",
    "RUNNER_VERSION",
    "Stage24RejectionRecord",
    "default_decoder_names",
    "run_stage24_decoders",
]
