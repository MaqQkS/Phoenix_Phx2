"""Stage 29.2 Birdeye probe models.

Closed-set vocabularies + the immutable probe-result record the
Stage 29.2 live probe orchestrator returns.

Closed-set vocabularies (mirror of the Stage 29.1 probe-model
pattern):

  * ``probe_mode``           -- ``READINESS_ONLY`` /
                                ``HTTP_CONNECT_ONLY`` /
                                ``ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN``
  * ``probe_status``         -- ``READY`` / ``NOT_READY`` /
                                ``CONNECTED`` /
                                ``FETCHED_WITH_PRICE_AND_ATH`` /
                                ``FETCHED_PRICE_ONLY`` /
                                ``FETCHED_NO_ATH_EVIDENCE`` /
                                ``FAILED`` / ``SKIPPED``
  * ``probe_refusal_reason`` -- the closed-set token set
                                pulled from Stage 29.2 models +
                                a few probe-specific additions.

This module imports ONLY stdlib (``dataclasses`` / ``typing``)
plus the Stage 29.2 constants + models + readiness modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PHX2.stage29.birdeye_constants import (
    STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_VALUES,
    Stage29_2BirdeyeError,
    Stage29_2BirdeyeEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Probe mode closed set
# ---------------------------------------------------------------------------


PROBE_MODE_READINESS_ONLY: str = "READINESS_ONLY"
PROBE_MODE_HTTP_CONNECT_ONLY: str = "HTTP_CONNECT_ONLY"
PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN: str = (
    "ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN"
)


PROBE_MODE_VALUES: tuple[str, ...] = (
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_HTTP_CONNECT_ONLY,
    PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
)


def is_probe_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in PROBE_MODE_VALUES


# ---------------------------------------------------------------------------
# Probe status closed set
# ---------------------------------------------------------------------------


PROBE_STATUS_READY: str = "READY"
PROBE_STATUS_NOT_READY: str = "NOT_READY"
PROBE_STATUS_CONNECTED: str = "CONNECTED"
PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH: str = (
    "FETCHED_WITH_PRICE_AND_ATH"
)
PROBE_STATUS_FETCHED_PRICE_ONLY: str = "FETCHED_PRICE_ONLY"
PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE: str = (
    "FETCHED_NO_ATH_EVIDENCE"
)
PROBE_STATUS_FAILED: str = "FAILED"
PROBE_STATUS_SKIPPED: str = "SKIPPED"


PROBE_STATUS_VALUES: tuple[str, ...] = (
    PROBE_STATUS_READY,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH,
    PROBE_STATUS_FETCHED_PRICE_ONLY,
    PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_SKIPPED,
)


def is_probe_status_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in PROBE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeHintProbeResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeHintProbeResult:
    """Immutable Stage 29.2 Birdeye live-probe result.

    Carries:

      * ``mode`` -- closed-set probe-mode token,
      * ``status`` -- closed-set probe-status token,
      * ``refusal_reason`` -- closed-set Stage 29.2 refusal
        token (re-uses the Stage 29.2 models refusal set,
        keeping vocabulary unified across surfaces),
      * ``base_mint`` -- the operator-supplied mint that the
        probe targeted; ``None`` for readiness-only / connect-
        only modes,
      * ``evidence`` -- Stage 29.2 evidence record (price +
        ATH + drawdown + freshness + audit) when the mode-3
        probe produced one; ``None`` for other modes / refusal
        paths,
      * ``http_status_code`` -- non-zero only for connect-only
        / dry-run modes when an HTTP response was observed,
      * ``api_key_length`` / ``base_url_length`` -- safe
        length counters mirrored from the readiness report so
        the operator can audit env presence in a redaction-safe
        way,
      * ``live_flag_set`` -- the readiness boolean (the
        ``PHX2_STAGE29_2_ALLOW_LIVE_HTTP=1`` gate),
      * ``timeout_seconds`` -- the bounded int timeout used,
      * ``handoff_ready`` -- ``True`` iff every sub-step the
        probe targeted passed AND the live-gate env was set;
        mirrors the Stage 28.11 / Stage 29.1 ``handoff_ready``
        axis for operator audit symmetry,
      * ``schema_version`` -- locked Stage 29.2 probe schema
        version string.
    """

    mode: str
    status: str
    refusal_reason: str
    base_mint: Optional[str]
    evidence: Optional[Stage29_2BirdeyeEvidenceRecord]
    http_status_code: int
    api_key_length: int
    base_url_length: int
    live_flag_set: bool
    timeout_seconds: int
    handoff_ready: bool
    schema_version: str

    def __post_init__(self) -> None:
        _validate_probe_result(self)


def _validate_probe_result(
    record: "Stage29_2BirdeyeHintProbeResult",
) -> None:
    # The ``mode`` field is a string echo of the operator-supplied
    # mode argument. The probe orchestrator routes off
    # ``is_probe_mode_value``; this validator only requires the
    # field to be a string so a refusal-recording branch can
    # echo back an invalid input verbatim (or empty-string when
    # the input was non-string).
    if not isinstance(record.mode, str):
        raise Stage29_2BirdeyeError("MODE_NOT_STR")
    if not is_probe_status_value(record.status):
        raise Stage29_2BirdeyeError(
            "PROBE_STATUS_NOT_CLOSED_SET"
        )
    if record.refusal_reason not in BIRDEYE_REFUSAL_REASON_VALUES:
        raise Stage29_2BirdeyeError(
            "REFUSAL_REASON_NOT_CLOSED_SET"
        )
    if record.base_mint is not None and not isinstance(
        record.base_mint, str
    ):
        raise Stage29_2BirdeyeError(
            "BASE_MINT_NOT_STR_OR_NONE"
        )
    if record.evidence is not None and not isinstance(
        record.evidence, Stage29_2BirdeyeEvidenceRecord
    ):
        raise Stage29_2BirdeyeError(
            "EVIDENCE_TYPE_INVALID"
        )
    if (
        isinstance(record.http_status_code, bool)
        or not isinstance(record.http_status_code, int)
        or record.http_status_code < 0
    ):
        raise Stage29_2BirdeyeError(
            "HTTP_STATUS_CODE_UNSAFE"
        )
    if (
        isinstance(record.api_key_length, bool)
        or not isinstance(record.api_key_length, int)
        or record.api_key_length < 0
    ):
        raise Stage29_2BirdeyeError(
            "API_KEY_LENGTH_UNSAFE"
        )
    if (
        isinstance(record.base_url_length, bool)
        or not isinstance(record.base_url_length, int)
        or record.base_url_length < 0
    ):
        raise Stage29_2BirdeyeError(
            "BASE_URL_LENGTH_UNSAFE"
        )
    if not isinstance(record.live_flag_set, bool):
        raise Stage29_2BirdeyeError(
            "LIVE_FLAG_SET_NOT_BOOL"
        )
    if not is_safe_timeout_seconds(record.timeout_seconds):
        raise Stage29_2BirdeyeError(
            "TIMEOUT_SECONDS_UNSAFE"
        )
    if not isinstance(record.handoff_ready, bool):
        raise Stage29_2BirdeyeError(
            "HANDOFF_READY_NOT_BOOL"
        )
    if not isinstance(record.schema_version, str):
        raise Stage29_2BirdeyeError(
            "SCHEMA_VERSION_NOT_STR"
        )


def build_hint_probe_result(
    *,
    mode: str,
    status: str,
    refusal_reason: str,
    base_mint: Optional[str],
    evidence: Optional[Stage29_2BirdeyeEvidenceRecord],
    http_status_code: int,
    api_key_length: int,
    base_url_length: int,
    live_flag_set: bool,
    timeout_seconds: int,
    handoff_ready: bool,
) -> Stage29_2BirdeyeHintProbeResult:
    """Construct a validated probe-result record."""
    return Stage29_2BirdeyeHintProbeResult(
        mode=mode,
        status=status,
        refusal_reason=refusal_reason,
        base_mint=base_mint,
        evidence=evidence,
        http_status_code=http_status_code,
        api_key_length=api_key_length,
        base_url_length=base_url_length,
        live_flag_set=live_flag_set,
        timeout_seconds=timeout_seconds,
        handoff_ready=handoff_ready,
        schema_version=STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION,
    )


__all__ = (
    "PROBE_MODE_READINESS_ONLY",
    "PROBE_MODE_HTTP_CONNECT_ONLY",
    "PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN",
    "PROBE_MODE_VALUES",
    "is_probe_mode_value",
    "PROBE_STATUS_READY",
    "PROBE_STATUS_NOT_READY",
    "PROBE_STATUS_CONNECTED",
    "PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH",
    "PROBE_STATUS_FETCHED_PRICE_ONLY",
    "PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE",
    "PROBE_STATUS_FAILED",
    "PROBE_STATUS_SKIPPED",
    "PROBE_STATUS_VALUES",
    "is_probe_status_value",
    "Stage29_2BirdeyeHintProbeResult",
    "build_hint_probe_result",
)
