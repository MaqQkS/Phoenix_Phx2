"""Stage 29.3 tradeable-smoke models.

Closed-set vocabularies + immutable ``Stage29_3TradeableSmokeResult``
record + module-local exception hierarchy for the Stage 29.3 first
real private tradeable PHX2 ping.

Stage 29.3 is the live tradeability unblocker substage that wires
the existing Stage 27 / Stage 28.4 / Stage 28.6 / Stage 28.9
private dispatch chain to:

  * the Stage 29.1 PumpSwap hint-aware decoder (real Chainstack
    Yellowstone evidence -> Stage 28.10 payloads with non-None
    hint slots),
  * the Stage 29.2 Birdeye price / ATH sources (real live price
    + ATH evidence via the Stage 27.4 Protocol surface).

The Stage 29.3 acceptance ceremony has THREE caller-supplied
modes:

  * ``READINESS_ONLY``                            -- verify all
                                                     three readiness
                                                     gates (Chainstack
                                                     env, Birdeye
                                                     env, private
                                                     webhook URL)
                                                     without
                                                     touching
                                                     gRPC / HTTP /
                                                     Discord.
  * ``CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY``       -- open the gRPC
                                                     channel, do one
                                                     Birdeye
                                                     ``/defi/price``
                                                     for a known
                                                     mint, close;
                                                     no Discord call.
  * ``ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN``   -- full mode-3
                                                     smoke:
                                                     ``max_events=1``,
                                                     ``max_dispatches=1``,
                                                     exactly one
                                                     private
                                                     operator
                                                     Discord ping
                                                     OR exactly one
                                                     suppression /
                                                     refusal verdict.

Discipline:

  * No env reads here. The Stage 28.11 / Stage 29.2 readiness
    boundaries own the only env-read sites; this module is pure
    data.
  * No network. No HTTP. No gRPC. No file I/O at import or call
    time.
  * No raw secret value is ever carried on a Stage 29.3 record.
    Provider IDs / safe identifiers / counters only; webhook URL /
    x-token / Birdeye API key are NEVER stored on these records.
  * ``repr()`` / ``str()`` of any Stage 29.3 record is safe to
    log / print / persist.

Stage 29.3 ships NO public routing, NO subscriber routing, NO paid
tier routing, NO Telegram, NO X / social, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO Stage 26 policy enforcement activation, NO
Pump.fun bonding-curve decoder, NO Dexscreener as a dispatch
authority, NO Helius as a price source, NO daemon / watchdog /
autorestart loop, NO ``Phoenix_Bot`` / PHX1 import path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Stage 29.3 version axes
# ---------------------------------------------------------------------------


STAGE29_3_MINOR_VERSION: str = "29.3"
STAGE29_3_SCHEMA_VERSION: str = (
    "stage29_3_tradeable_smoke_v0"
)


# Distinctive Stage 29.3 redaction token. Distinct from the Stage
# 27 / 28.x / 29.1 / 29.2 redaction tokens so a leak-scan test for
# one cannot collide with another.
STAGE29_3_REDACTION_TOKEN: str = "<<STAGE29_3_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: probe mode (the three operator-supplied ceremony modes)
# ---------------------------------------------------------------------------


PROBE_MODE_READINESS_ONLY: str = "READINESS_ONLY"
PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY: str = (
    "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY"
)
PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN: str = (
    "ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN"
)


PROBE_MODE_VALUES: tuple[str, ...] = (
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
)


def is_probe_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in PROBE_MODE_VALUES


# ---------------------------------------------------------------------------
# Closed-set: tradeable smoke outcome
# ---------------------------------------------------------------------------


TRADEABLE_SMOKE_OUTCOME_DISPATCHED: str = "DISPATCHED"
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR: str = (
    "SUPPRESSED_UNKNOWN_PAIR"
)
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR: str = (
    "SUPPRESSED_DISAGREE_PAIR"
)
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY: str = (
    "SUPPRESSED_USDC_OBSERVE_ONLY"
)
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE: str = (
    "SUPPRESSED_MISSING_PRICE"
)
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE: str = (
    "SUPPRESSED_STALE_PRICE"
)
TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED: str = (
    "SUPPRESSED_MALFORMED"
)
TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED: str = (
    "NO_EVENT_RECEIVED"
)
TRADEABLE_SMOKE_OUTCOME_READY: str = "READY"
TRADEABLE_SMOKE_OUTCOME_CONNECTED: str = "CONNECTED"
TRADEABLE_SMOKE_OUTCOME_REFUSED: str = "REFUSED"
TRADEABLE_SMOKE_OUTCOME_FAILED: str = "FAILED"


TRADEABLE_SMOKE_OUTCOME_VALUES: tuple[str, ...] = (
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
    TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_OUTCOME_CONNECTED,
    TRADEABLE_SMOKE_OUTCOME_REFUSED,
    TRADEABLE_SMOKE_OUTCOME_FAILED,
)


# Subset of outcomes that correspond to a successful mode-1 / mode-2
# / mode-3 happy-path (the operator may treat any of these as a
# legitimate non-error ceremony outcome). DISPATCHED is the only
# mode-3 outcome that proves the end-to-end real-event-to-real-
# private-ping path; the SUPPRESSED_* outcomes prove the chain
# correctly refused a non-tradeable event.
TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES: tuple[str, ...] = (
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE,
    TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED,
    TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_OUTCOME_CONNECTED,
)


def is_tradeable_smoke_outcome_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in TRADEABLE_SMOKE_OUTCOME_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: tradeable smoke refusal reason
# ---------------------------------------------------------------------------


TRADEABLE_SMOKE_REFUSAL_REASON_NONE: str = "NONE"
TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID: str = (
    "MODE_INVALID"
)
TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED: str = (
    "CHAINSTACK_READINESS_FAILED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED: str = (
    "BIRDEYE_READINESS_FAILED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING: str = (
    "WEBHOOK_MISSING"
)
TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET: str = (
    "LIVE_FLAG_NOT_SET"
)
TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET: str = (
    "OPERATOR_REQUEST_NOT_SET"
)
TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE: str = (
    "OUTPUT_DIR_UNSAFE"
)
TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID: str = (
    "KNOWN_MINT_INVALID"
)
TRADEABLE_SMOKE_REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE: str = (
    "CHANNEL_FACTORY_NOT_CALLABLE"
)
TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED: str = (
    "SUBSCRIBE_FAILED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_STREAM_ERROR: str = (
    "STREAM_ERROR"
)
TRADEABLE_SMOKE_REFUSAL_REASON_DECODE_FAILED: str = (
    "DECODE_FAILED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED: str = (
    "BIRDEYE_CONNECT_FAILED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED: str = (
    "SESSION_REFUSED"
)
TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED: str = (
    "SESSION_FAILED"
)


TRADEABLE_SMOKE_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
    TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING,
    TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET,
    TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID,
    TRADEABLE_SMOKE_REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE,
    TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_STREAM_ERROR,
    TRADEABLE_SMOKE_REFUSAL_REASON_DECODE_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED,
    TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED,
)


def is_tradeable_smoke_refusal_reason_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value in TRADEABLE_SMOKE_REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
)


def is_redaction_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: filter-enforcement status (Stage 29 enforcement pending)
# ---------------------------------------------------------------------------


# Stage 29.3 explicitly does NOT activate Stage 26 / Stage 29
# policy enforcement. The locked marker pins this on every Stage
# 29.3 record so a downstream reader can rely on the value to gate
# against enforcement-on assumptions.
FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING: str = (
    "NOT_ACTIVE_STAGE_29_PENDING"
)


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage29_3TradeableSmokeError(Exception):
    """Base type for every Stage 29.3 tradeable-smoke validation
    error. Module-local; not a subclass of any central PHX2 error
    registry. The constructor NEVER carries a raw upstream payload,
    a raw env value, a raw URL, or a raw secret; callers pass only
    closed-set tokens.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 29.3 tradeable smoke error: "
            f"reason={reason!r}"
        )


class Stage29_3InvalidSmokeResultError(
    Stage29_3TradeableSmokeError,
):
    """Raised when a ``Stage29_3TradeableSmokeResult`` field
    fails the locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"INVALID_SMOKE_RESULT_FIELD::{field_name}::{reason}"
        )


# ---------------------------------------------------------------------------
# Safe counter helper (mirrors Stage 28.5 ``is_safe_counter_value``)
# ---------------------------------------------------------------------------


def _is_safe_counter(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    if value < 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Stage29_3TradeableSmokeResult
# ---------------------------------------------------------------------------


STAGE29_3_SMOKE_RESULT_COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "events_seen",
    "candidates_assembled",
    "candidates_dispatched",
    "candidates_suppressed",
    "dispatch_success",
    "dispatch_failure",
)


STAGE29_3_SMOKE_RESULT_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "mode",
    "tradeable_smoke_outcome",
    "tradeable_smoke_refusal_reason",
    "events_seen",
    "candidates_assembled",
    "candidates_dispatched",
    "candidates_suppressed",
    "dispatch_success",
    "dispatch_failure",
    "hint_bearing_payload_present",
    "birdeye_price_present",
    "birdeye_ath_present",
    "stop_reason",
    "filter_enforcement_status",
    "redaction_status",
)


@dataclass(frozen=True)
class Stage29_3TradeableSmokeResult:
    """Immutable Stage 29.3 tradeable-smoke result record.

    Implemented as a frozen ``@dataclass`` so direct construction
    triggers ``__post_init__`` validation; callers cannot bypass
    the safe-shape checks by skipping the
    ``build_tradeable_smoke_result`` factory.

    Carries only closed-set tokens, safe counters, and bool axes.
    The record NEVER carries:

      * a webhook URL,
      * a Chainstack endpoint URL or x-token,
      * a Birdeye API key or base URL,
      * a wallet / private-key / signer field,
      * a raw upstream provider payload blob,
      * a raw exception string.

    Fields:

      * ``mode`` -- closed-set ``PROBE_MODE_*`` token.
      * ``tradeable_smoke_outcome`` -- closed-set
        ``TRADEABLE_SMOKE_OUTCOME_*`` token.
      * ``tradeable_smoke_refusal_reason`` -- closed-set
        ``TRADEABLE_SMOKE_REFUSAL_REASON_*`` token; ``NONE`` iff
        the outcome is in the non-error subset.
      * ``events_seen`` / ``candidates_assembled`` /
        ``candidates_dispatched`` / ``candidates_suppressed`` /
        ``dispatch_success`` / ``dispatch_failure`` -- safe
        non-negative ``int`` counters mirroring the Stage 28.9
        session-result counter axes (reduced to the Stage 29.3
        ceremony surface: max_events=1 / max_dispatches=1 means
        each counter is 0 or 1).
      * ``hint_bearing_payload_present`` -- ``True`` iff the
        Stage 29.1 hint-aware decoder surfaced a hint-bearing
        payload during this ceremony.
      * ``birdeye_price_present`` -- ``True`` iff the Stage 29.2
        price source returned a parseable price snapshot during
        this ceremony.
      * ``birdeye_ath_present`` -- ``True`` iff the Stage 29.2
        ATH source returned a parseable ATH snapshot during this
        ceremony.
      * ``stop_reason`` -- safe-shape short token describing why
        the ceremony exited (e.g. ``"DISPATCHED"`` /
        ``"NO_EVENT_RECEIVED"`` / ``"READINESS_REFUSED"``).
      * ``filter_enforcement_status`` -- locked
        ``NOT_ACTIVE_STAGE_29_PENDING`` on every Stage 29.3
        record (Stage 29.3 does not activate Stage 26 / Stage 29
        enforcement).
      * ``redaction_status`` -- locked ``REDACTION_STATUS_SAFE``
        on every well-formed Stage 29.3 result.
      * ``schema_version`` -- locked
        ``STAGE29_3_SCHEMA_VERSION``.
    """

    mode: str
    tradeable_smoke_outcome: str
    tradeable_smoke_refusal_reason: str
    events_seen: int
    candidates_assembled: int
    candidates_dispatched: int
    candidates_suppressed: int
    dispatch_success: int
    dispatch_failure: int
    hint_bearing_payload_present: bool
    birdeye_price_present: bool
    birdeye_ath_present: bool
    stop_reason: str
    filter_enforcement_status: str = (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    redaction_status: str = REDACTION_STATUS_SAFE
    schema_version: str = STAGE29_3_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_smoke_result_fields(self)


_SAFE_STOP_REASON_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_SAFE_STOP_REASON_MIN_LENGTH: int = 1
_SAFE_STOP_REASON_MAX_LENGTH: int = 64


def _is_safe_stop_reason(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_STOP_REASON_MIN_LENGTH:
        return False
    if len(value) > _SAFE_STOP_REASON_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_STOP_REASON_ALLOWED_CHARS:
            return False
    return True


def _validate_smoke_result_fields(
    record: "Stage29_3TradeableSmokeResult",
) -> None:
    if record.schema_version != STAGE29_3_SCHEMA_VERSION:
        raise Stage29_3InvalidSmokeResultError(
            field_name="schema_version",
            reason="SCHEMA_VERSION_NOT_LOCKED",
        )
    if not is_probe_mode_value(record.mode):
        raise Stage29_3InvalidSmokeResultError(
            field_name="mode",
            reason="MODE_NOT_CLOSED_SET",
        )
    if not is_tradeable_smoke_outcome_value(
        record.tradeable_smoke_outcome,
    ):
        raise Stage29_3InvalidSmokeResultError(
            field_name="tradeable_smoke_outcome",
            reason="OUTCOME_NOT_CLOSED_SET",
        )
    if not is_tradeable_smoke_refusal_reason_value(
        record.tradeable_smoke_refusal_reason,
    ):
        raise Stage29_3InvalidSmokeResultError(
            field_name="tradeable_smoke_refusal_reason",
            reason="REFUSAL_REASON_NOT_CLOSED_SET",
        )
    # Outcome / refusal-reason internal consistency.
    is_non_error = (
        record.tradeable_smoke_outcome
        in TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES
    )
    if is_non_error and (
        record.tradeable_smoke_refusal_reason
        != TRADEABLE_SMOKE_REFUSAL_REASON_NONE
    ):
        raise Stage29_3InvalidSmokeResultError(
            field_name="tradeable_smoke_refusal_reason",
            reason="NON_ERROR_REQUIRES_REFUSAL_REASON_NONE",
        )
    if not is_non_error and (
        record.tradeable_smoke_refusal_reason
        == TRADEABLE_SMOKE_REFUSAL_REASON_NONE
    ):
        raise Stage29_3InvalidSmokeResultError(
            field_name="tradeable_smoke_refusal_reason",
            reason=(
                "ERROR_OUTCOME_REQUIRES_REFUSAL_REASON_NOT_NONE"
            ),
        )
    # Safe counter axes.
    for name in STAGE29_3_SMOKE_RESULT_COUNTER_FIELD_NAMES:
        value = getattr(record, name)
        if not _is_safe_counter(value):
            raise Stage29_3InvalidSmokeResultError(
                field_name=name,
                reason="COUNTER_NOT_NONNEG_INT",
            )
    # Bool axes.
    for name in (
        "hint_bearing_payload_present",
        "birdeye_price_present",
        "birdeye_ath_present",
    ):
        value = getattr(record, name)
        if not isinstance(value, bool):
            raise Stage29_3InvalidSmokeResultError(
                field_name=name,
                reason="VALUE_NOT_BOOL",
            )
    # Bounds: Stage 29.3 is max_events=1, max_dispatches=1.
    if record.events_seen > 1:
        raise Stage29_3InvalidSmokeResultError(
            field_name="events_seen",
            reason="EXCEEDS_MAX_EVENTS_1",
        )
    if record.candidates_assembled > 1:
        raise Stage29_3InvalidSmokeResultError(
            field_name="candidates_assembled",
            reason="EXCEEDS_MAX_DISPATCHES_1",
        )
    if record.candidates_dispatched > 1:
        raise Stage29_3InvalidSmokeResultError(
            field_name="candidates_dispatched",
            reason="EXCEEDS_MAX_DISPATCHES_1",
        )
    if record.dispatch_success > 1:
        raise Stage29_3InvalidSmokeResultError(
            field_name="dispatch_success",
            reason="EXCEEDS_MAX_DISPATCHES_1",
        )
    # Stop reason shape.
    if not _is_safe_stop_reason(record.stop_reason):
        raise Stage29_3InvalidSmokeResultError(
            field_name="stop_reason",
            reason="STOP_REASON_UNSAFE",
        )
    # Filter-enforcement status is locked.
    if (
        record.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        raise Stage29_3InvalidSmokeResultError(
            field_name="filter_enforcement_status",
            reason="FILTER_ENFORCEMENT_STATUS_NOT_LOCKED",
        )
    # Redaction status closed set.
    if not is_redaction_status_value(record.redaction_status):
        raise Stage29_3InvalidSmokeResultError(
            field_name="redaction_status",
            reason="REDACTION_STATUS_NOT_CLOSED_SET",
        )


def build_tradeable_smoke_result(
    *,
    mode: object,
    tradeable_smoke_outcome: object,
    tradeable_smoke_refusal_reason: object,
    events_seen: object = 0,
    candidates_assembled: object = 0,
    candidates_dispatched: object = 0,
    candidates_suppressed: object = 0,
    dispatch_success: object = 0,
    dispatch_failure: object = 0,
    hint_bearing_payload_present: object = False,
    birdeye_price_present: object = False,
    birdeye_ath_present: object = False,
    stop_reason: object = "NO_EVENT_RECEIVED",
) -> Stage29_3TradeableSmokeResult:
    """Construct an immutable ``Stage29_3TradeableSmokeResult``
    with full validation. Raises
    ``Stage29_3InvalidSmokeResultError`` for any field that fails
    the locked allowlist.
    """
    return Stage29_3TradeableSmokeResult(
        mode=mode,  # type: ignore[arg-type]
        tradeable_smoke_outcome=(
            tradeable_smoke_outcome  # type: ignore[arg-type]
        ),
        tradeable_smoke_refusal_reason=(
            tradeable_smoke_refusal_reason  # type: ignore[arg-type]
        ),
        events_seen=events_seen,  # type: ignore[arg-type]
        candidates_assembled=(
            candidates_assembled  # type: ignore[arg-type]
        ),
        candidates_dispatched=(
            candidates_dispatched  # type: ignore[arg-type]
        ),
        candidates_suppressed=(
            candidates_suppressed  # type: ignore[arg-type]
        ),
        dispatch_success=(
            dispatch_success  # type: ignore[arg-type]
        ),
        dispatch_failure=(
            dispatch_failure  # type: ignore[arg-type]
        ),
        hint_bearing_payload_present=(
            hint_bearing_payload_present  # type: ignore[arg-type]
        ),
        birdeye_price_present=(
            birdeye_price_present  # type: ignore[arg-type]
        ),
        birdeye_ath_present=(
            birdeye_ath_present  # type: ignore[arg-type]
        ),
        stop_reason=stop_reason,  # type: ignore[arg-type]
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        redaction_status=REDACTION_STATUS_SAFE,
        schema_version=STAGE29_3_SCHEMA_VERSION,
    )


def smoke_result_to_dict(
    record: Stage29_3TradeableSmokeResult,
) -> dict:
    """Project a smoke result record into a deterministic-order
    dict suitable for tests and downstream inspection.
    """
    if not isinstance(record, Stage29_3TradeableSmokeResult):
        raise Stage29_3InvalidSmokeResultError(
            field_name="record",
            reason="NOT_A_SMOKE_RESULT_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in STAGE29_3_SMOKE_RESULT_FIELD_NAMES
    }


__all__ = (
    # Version axes.
    "STAGE29_3_MINOR_VERSION",
    "STAGE29_3_SCHEMA_VERSION",
    "STAGE29_3_REDACTION_TOKEN",
    # Probe-mode vocabulary.
    "PROBE_MODE_READINESS_ONLY",
    "PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
    "PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN",
    "PROBE_MODE_VALUES",
    "is_probe_mode_value",
    # Outcome vocabulary.
    "TRADEABLE_SMOKE_OUTCOME_DISPATCHED",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_UNKNOWN_PAIR",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_DISAGREE_PAIR",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MISSING_PRICE",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_STALE_PRICE",
    "TRADEABLE_SMOKE_OUTCOME_SUPPRESSED_MALFORMED",
    "TRADEABLE_SMOKE_OUTCOME_NO_EVENT_RECEIVED",
    "TRADEABLE_SMOKE_OUTCOME_READY",
    "TRADEABLE_SMOKE_OUTCOME_CONNECTED",
    "TRADEABLE_SMOKE_OUTCOME_REFUSED",
    "TRADEABLE_SMOKE_OUTCOME_FAILED",
    "TRADEABLE_SMOKE_OUTCOME_VALUES",
    "TRADEABLE_SMOKE_OUTCOME_NON_ERROR_VALUES",
    "is_tradeable_smoke_outcome_value",
    # Refusal-reason vocabulary.
    "TRADEABLE_SMOKE_REFUSAL_REASON_NONE",
    "TRADEABLE_SMOKE_REFUSAL_REASON_MODE_INVALID",
    "TRADEABLE_SMOKE_REFUSAL_REASON_CHAINSTACK_READINESS_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_READINESS_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_WEBHOOK_MISSING",
    "TRADEABLE_SMOKE_REFUSAL_REASON_LIVE_FLAG_NOT_SET",
    "TRADEABLE_SMOKE_REFUSAL_REASON_OPERATOR_REQUEST_NOT_SET",
    "TRADEABLE_SMOKE_REFUSAL_REASON_OUTPUT_DIR_UNSAFE",
    "TRADEABLE_SMOKE_REFUSAL_REASON_KNOWN_MINT_INVALID",
    "TRADEABLE_SMOKE_REFUSAL_REASON_CHANNEL_FACTORY_NOT_CALLABLE",
    "TRADEABLE_SMOKE_REFUSAL_REASON_SUBSCRIBE_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_STREAM_ERROR",
    "TRADEABLE_SMOKE_REFUSAL_REASON_DECODE_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_BIRDEYE_CONNECT_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_REFUSED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_SESSION_FAILED",
    "TRADEABLE_SMOKE_REFUSAL_REASON_VALUES",
    "is_tradeable_smoke_refusal_reason_value",
    # Redaction vocabulary.
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_VALUES",
    "is_redaction_status_value",
    # Filter-enforcement vocabulary.
    "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING",
    # Records.
    "Stage29_3TradeableSmokeResult",
    "STAGE29_3_SMOKE_RESULT_COUNTER_FIELD_NAMES",
    "STAGE29_3_SMOKE_RESULT_FIELD_NAMES",
    # Builders.
    "build_tradeable_smoke_result",
    "smoke_result_to_dict",
    # Exceptions.
    "Stage29_3TradeableSmokeError",
    "Stage29_3InvalidSmokeResultError",
)
