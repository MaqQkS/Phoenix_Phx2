"""Stage 29.1 PumpSwap hint-probe models.

Closed-set vocabularies + the immutable probe-result record the
Stage 29.1 live probe orchestrator returns.

This module imports ONLY stdlib (``dataclasses`` / ``typing``)
plus the Stage 28.10 payload model + the Stage 29.1 hint
extraction result model. It does NOT import:

  * Stage 21-27 production code,
  * Stage 28.0 - 28.9 production code beyond the Stage 28.10
    payload model,
  * ``grpc`` / ``grpcio`` / ``protobuf`` / generated stubs (gRPC
    is the live-probe module's surface, not the probe model's),
  * any network / RPC / messaging / DB / scheduler / wallet /
    trading / Discord / Telegram / X / dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level I/O at import time.
  * Probe-result records carry ONLY closed-set tokens, safe
    counters, the optional Stage 28.10 payload (which is itself
    redaction-safe), and the optional Stage 29.1 extraction
    result. No raw upstream bytes, log strings, or instruction
    data ever appear on a probe-result record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstonePayload,
)
from PHX2.stage29.pumpswap_hint_models import (
    Stage29_1PumpSwapHintExtractionResult,
)


# ---------------------------------------------------------------------------
# Stage 29.1 closed-set: probe mode
# ---------------------------------------------------------------------------


PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN: str = (
    "ONE_PUMPSWAP_EVENT_HINT_DRY_RUN"
)


PROBE_MODE_VALUES: tuple[str, ...] = (
    PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
)


def is_probe_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in PROBE_MODE_VALUES


# ---------------------------------------------------------------------------
# Stage 29.1 closed-set: probe status
# ---------------------------------------------------------------------------


PROBE_STATUS_DECODED_WITH_HINTS: str = "DECODED_WITH_HINTS"
PROBE_STATUS_DECODED_NO_HINT_EVIDENCE: str = (
    "DECODED_NO_HINT_EVIDENCE"
)
PROBE_STATUS_FAILED: str = "FAILED"
PROBE_STATUS_SKIPPED: str = "SKIPPED"


PROBE_STATUS_VALUES: tuple[str, ...] = (
    PROBE_STATUS_DECODED_WITH_HINTS,
    PROBE_STATUS_DECODED_NO_HINT_EVIDENCE,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_SKIPPED,
)


def is_probe_status_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in PROBE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 29.1 closed-set: refusal reason
# ---------------------------------------------------------------------------


REFUSAL_REASON_NONE: str = "NONE"
REFUSAL_REASON_MODE_INVALID: str = "MODE_INVALID"
REFUSAL_REASON_LIVE_FLAG_NOT_SET: str = "LIVE_FLAG_NOT_SET"
REFUSAL_REASON_CONNECT_FAILED: str = "CONNECT_FAILED"
REFUSAL_REASON_SUBSCRIBE_FAILED: str = "SUBSCRIBE_FAILED"
REFUSAL_REASON_STREAM_ERROR: str = "STREAM_ERROR"
REFUSAL_REASON_NO_TRANSACTION_RECEIVED: str = (
    "NO_TRANSACTION_RECEIVED"
)
REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED: str = (
    "NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED"
)
REFUSAL_REASON_DECODE_FAILED: str = "DECODE_FAILED"
REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID: str = (
    "MAX_MESSAGES_TO_SCAN_INVALID"
)
REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE: str = (
    "CHANNEL_FACTORY_NOT_CALLABLE"
)


REFUSAL_REASON_VALUES: tuple[str, ...] = (
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_SUBSCRIBE_FAILED,
    REFUSAL_REASON_STREAM_ERROR,
    REFUSAL_REASON_NO_TRANSACTION_RECEIVED,
    REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID,
    REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
)


def is_refusal_reason_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 29.1 module-local exception
# ---------------------------------------------------------------------------


class Stage29_1HintProbeError(Exception):
    """Base type for every Stage 29.1 hint-probe validation
    error. Module-local; not a subclass of any central PHX2
    error registry. NEVER carries a raw endpoint URL, raw
    x-token, raw upstream protobuf field value, or raw gRPC
    error traceback; the constructor accepts only a closed-set
    reason token.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 29.1 hint-probe error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage29_1HintProbeResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_1HintProbeResult:
    """Immutable Stage 29.1 PumpSwap hint-probe result.

    Carries:

      * ``mode`` -- the closed-set
        ``PROBE_MODE_*`` token the probe executed,
      * ``status`` -- the closed-set ``PROBE_STATUS_*``
        token,
      * ``refusal_reason`` -- the closed-set
        ``REFUSAL_REASON_*`` token; ``NONE`` on success,
      * ``hint_bearing_payload`` -- the Stage 28.10 payload
        returned by the hint-aware decoder when status is
        ``DECODED_WITH_HINTS``; ``None`` for every other
        status,
      * ``extraction_result`` -- the Stage 29.1 hint
        extraction result the extractor produced for the
        winning event (when ``DECODED_WITH_HINTS``) OR for
        the last scanned event (when
        ``DECODED_NO_HINT_EVIDENCE``); ``None`` for failure /
        skip statuses,
      * ``events_scanned`` -- safe counter of how many
        upstream ``SubscribeUpdate`` messages the probe
        consumed before returning,
      * ``transactions_scanned`` -- safe counter of how many
        of those messages carried a transaction variant,
      * ``handoff_ready`` -- boolean True iff every sub-step
        the probe targeted passed AND the live-gate env was
        set; mirrors the Stage 28.11 ``handoff_ready`` axis
        for operator audit symmetry.
    """

    mode: str
    status: str
    refusal_reason: str
    hint_bearing_payload: Optional[
        Stage28_10ChainstackYellowstonePayload
    ]
    extraction_result: Optional[
        Stage29_1PumpSwapHintExtractionResult
    ]
    events_scanned: int
    transactions_scanned: int
    handoff_ready: bool

    def __post_init__(self) -> None:
        _validate_probe_result_fields(self)


def _validate_probe_result_fields(
    record: "Stage29_1HintProbeResult",
) -> None:
    """Validate every field of a ``Stage29_1HintProbeResult``.

    Pure / deterministic. Raises ``Stage29_1HintProbeError`` on
    the first failing field; the error carries only a closed-set
    reason token.
    """
    if not is_probe_mode_value(record.mode):
        raise Stage29_1HintProbeError("MODE_NOT_CLOSED_SET")
    if not is_probe_status_value(record.status):
        raise Stage29_1HintProbeError("STATUS_NOT_CLOSED_SET")
    if not is_refusal_reason_value(record.refusal_reason):
        raise Stage29_1HintProbeError(
            "REFUSAL_REASON_NOT_CLOSED_SET",
        )
    if (
        isinstance(record.events_scanned, bool)
        or not isinstance(record.events_scanned, int)
        or record.events_scanned < 0
    ):
        raise Stage29_1HintProbeError(
            "EVENTS_SCANNED_UNSAFE",
        )
    if (
        isinstance(record.transactions_scanned, bool)
        or not isinstance(record.transactions_scanned, int)
        or record.transactions_scanned < 0
    ):
        raise Stage29_1HintProbeError(
            "TRANSACTIONS_SCANNED_UNSAFE",
        )
    if not isinstance(record.handoff_ready, bool):
        raise Stage29_1HintProbeError(
            "HANDOFF_READY_NOT_BOOL",
        )
    if record.hint_bearing_payload is not None and not isinstance(
        record.hint_bearing_payload,
        Stage28_10ChainstackYellowstonePayload,
    ):
        raise Stage29_1HintProbeError(
            "PAYLOAD_NOT_STAGE28_10_PAYLOAD",
        )
    if record.extraction_result is not None and not isinstance(
        record.extraction_result,
        Stage29_1PumpSwapHintExtractionResult,
    ):
        raise Stage29_1HintProbeError(
            "EXTRACTION_RESULT_NOT_STAGE29_1_RESULT",
        )

    if record.status == PROBE_STATUS_DECODED_WITH_HINTS:
        if record.hint_bearing_payload is None:
            raise Stage29_1HintProbeError(
                "DECODED_WITH_HINTS_BUT_PAYLOAD_MISSING",
            )
        if record.extraction_result is None:
            raise Stage29_1HintProbeError(
                "DECODED_WITH_HINTS_BUT_EXTRACTION_MISSING",
            )
        if record.refusal_reason != REFUSAL_REASON_NONE:
            raise Stage29_1HintProbeError(
                "DECODED_WITH_HINTS_BUT_REFUSAL_REASON_SET",
            )
    elif record.status == PROBE_STATUS_DECODED_NO_HINT_EVIDENCE:
        if record.hint_bearing_payload is not None:
            raise Stage29_1HintProbeError(
                "DECODED_NO_HINT_EVIDENCE_BUT_PAYLOAD_SET",
            )
        # extraction_result may be present (records the reason
        # the last scanned event yielded NO_EVIDENCE) OR None
        # (when no transaction surfaced at all). Either is fine.
        if record.refusal_reason == REFUSAL_REASON_NONE:
            raise Stage29_1HintProbeError(
                "DECODED_NO_HINT_EVIDENCE_BUT_REFUSAL_NONE",
            )
    else:
        # FAILED / SKIPPED.
        if record.hint_bearing_payload is not None:
            raise Stage29_1HintProbeError(
                "NON_SUCCESS_STATUS_BUT_PAYLOAD_SET",
            )
        if record.refusal_reason == REFUSAL_REASON_NONE:
            raise Stage29_1HintProbeError(
                "NON_SUCCESS_STATUS_BUT_REFUSAL_NONE",
            )


def build_hint_probe_result(
    *,
    mode: str,
    status: str,
    refusal_reason: str,
    hint_bearing_payload: Optional[
        Stage28_10ChainstackYellowstonePayload
    ] = None,
    extraction_result: Optional[
        Stage29_1PumpSwapHintExtractionResult
    ] = None,
    events_scanned: int = 0,
    transactions_scanned: int = 0,
    handoff_ready: bool = False,
) -> Stage29_1HintProbeResult:
    """Construct a validated ``Stage29_1HintProbeResult`` via
    explicit keyword args.

    Pure / deterministic. Validation runs in
    ``__post_init__``; this factory exists for keyword-only
    ergonomics + the default-value contract.
    """
    return Stage29_1HintProbeResult(
        mode=mode,
        status=status,
        refusal_reason=refusal_reason,
        hint_bearing_payload=hint_bearing_payload,
        extraction_result=extraction_result,
        events_scanned=events_scanned,
        transactions_scanned=transactions_scanned,
        handoff_ready=handoff_ready,
    )


__all__ = (
    "PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN",
    "PROBE_MODE_VALUES",
    "is_probe_mode_value",
    "PROBE_STATUS_DECODED_WITH_HINTS",
    "PROBE_STATUS_DECODED_NO_HINT_EVIDENCE",
    "PROBE_STATUS_FAILED",
    "PROBE_STATUS_SKIPPED",
    "PROBE_STATUS_VALUES",
    "is_probe_status_value",
    "REFUSAL_REASON_NONE",
    "REFUSAL_REASON_MODE_INVALID",
    "REFUSAL_REASON_LIVE_FLAG_NOT_SET",
    "REFUSAL_REASON_CONNECT_FAILED",
    "REFUSAL_REASON_SUBSCRIBE_FAILED",
    "REFUSAL_REASON_STREAM_ERROR",
    "REFUSAL_REASON_NO_TRANSACTION_RECEIVED",
    "REFUSAL_REASON_NO_PUMPSWAP_HINT_BEARING_TRANSACTION_RECEIVED",
    "REFUSAL_REASON_DECODE_FAILED",
    "REFUSAL_REASON_MAX_MESSAGES_TO_SCAN_INVALID",
    "REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE",
    "REFUSAL_REASON_VALUES",
    "is_refusal_reason_value",
    "Stage29_1HintProbeError",
    "Stage29_1HintProbeResult",
    "build_hint_probe_result",
)
