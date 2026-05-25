"""Stage 29.2 Birdeye price / ATH adapter manifest.

Stage 29.2 is the second Stage 29 substage past the Stage 29.0
spec-lock pass + the Stage 29.1 PumpSwap hint extractor. It
ships the Birdeye-backed implementation of the existing Stage
27.4 ``PriceContextSource`` and ``AthContextSource`` Protocols
so the existing Stage 27.6 candidate chain can carry real
Birdeye live context for a Stage 29.1-extracted PumpSwap
``base_mint``.

Stage 29.2 ships:

  * Stage-29.2-pinned program constants (endpoint paths,
    headers, OHLCV resolutions, safe-shape validators),
  * the closed-set Birdeye price / ATH / freshness / refusal
    vocabularies + the immutable snapshot / evidence records,
  * the SOLE Stage 29.2 env-read boundary
    (``stage29_2_birdeye_readiness.py``) reading exactly four
    locked env names,
  * the SOLE Stage 29.2 outbound-HTTP transport
    (``stage29_2_birdeye_http_transport.py``) using stdlib
    ``urllib.request`` only,
  * the Stage 27.4 ``PriceContextSource`` Protocol
    implementation backed by ``/defi/price``,
  * the Stage 27.4 ``AthContextSource`` Protocol implementation
    backed by ``/defi/ohlcv`` (ATH from ``max(items[].h)``
    candle highs),
  * the Stage 29.2 probe model layer + the Stage 29.2 live
    probe orchestrator (the second Stage 29.2 production file
    allowed to invoke outbound HTTP via the transport),
  * the operator runbook,
  * this manifest.

Stage 29.2 ships NO Discord send, NO Telegram, NO X / social,
NO automated trading, NO wallet / private-key / signer logic,
NO position sizing, NO trade execution, NO public / subscriber
/ paid-tier routing, NO Stage 26 enforcement activation, NO
Stage 28.9 wrapper invocation, NO Stage 28.6 bounded runner
invocation, NO Stage 28.4 audited transport invocation, NO
Pump.fun bonding-curve decoder, NO Dexscreener, NO Helius, NO
Stage 29.3 tradeable smoke harness, NO PHX1 import path.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.2 sibling
    modules + the Stage 29.1 manifest (for the re-exported
    ``WRAPPED_SOL_MINT`` constant the Stage 29.2 probe uses in
    its ``HTTP_CONNECT_ONLY`` mode),
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import
    time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_DEFAULT_OHLCV_TYPE as _BIRDEYE_DEFAULT_OHLCV_TYPE,
    BIRDEYE_OHLCV_SOURCE_LABEL
    as _BIRDEYE_OHLCV_SOURCE_LABEL,
    BIRDEYE_OHLCV_TYPE_ALLOWED
    as _BIRDEYE_OHLCV_TYPE_ALLOWED,
    BIRDEYE_PATH_OHLCV as _BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE as _BIRDEYE_PATH_PRICE,
    BIRDEYE_PRICE_SOURCE_LABEL
    as _BIRDEYE_PRICE_SOURCE_LABEL,
    BIRDEYE_REPORTING_UNIT_USD as _BIRDEYE_REPORTING_UNIT_USD,
    BIRDEYE_X_CHAIN_VALUE_SOLANA
    as _BIRDEYE_X_CHAIN_VALUE_SOLANA,
    DEFAULT_HTTP_TIMEOUT_SECONDS
    as _DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_LOOKBACK_HOURS as _DEFAULT_LOOKBACK_HOURS,
    MAX_LOOKBACK_HOURS as _MAX_LOOKBACK_HOURS,
    MIN_LOOKBACK_HOURS as _MIN_LOOKBACK_HOURS,
    STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION
    as _STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION,
    STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION
    as _STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION,
    STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION
    as _STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION,
    STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION
    as _STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION,
    STAGE29_2_MINOR_VERSION as _STAGE29_2_MINOR_VERSION,
    STAGE29_2_PROBE_MAX_REQUESTS
    as _STAGE29_2_PROBE_MAX_REQUESTS,
    STAGE29_2_REDACTION_TOKEN as _STAGE29_2_REDACTION_TOKEN,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    Stage29_2BirdeyeAthSource as _MODELS_ATH_SOURCE,
    fetch_birdeye_ath_snapshot as _MODELS_ATH_FETCH,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult as _MODELS_HTTP_RESULT,
    Stage29_2BirdeyeHttpTransport as _MODELS_HTTP_PROTOCOL,
    Stage29_2BirdeyeUrlibTransport as _MODELS_HTTP_TRANSPORT,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_VALUES as _MODELS_ATH_STATUS_VALUES,
    BIRDEYE_FRESHNESS_STATUS_VALUES
    as _MODELS_FRESHNESS_STATUS_VALUES,
    BIRDEYE_PRICE_STATUS_VALUES
    as _MODELS_PRICE_STATUS_VALUES,
    BIRDEYE_REFUSAL_REASON_VALUES
    as _MODELS_REFUSAL_REASON_VALUES,
    NO_INVENTION_AUDIT_VALUES
    as _MODELS_NO_INVENTION_VALUES,
    Stage29_2BirdeyeAthSnapshot as _MODELS_ATH_SNAPSHOT,
    Stage29_2BirdeyeError as _MODELS_ERROR_TYPE,
    Stage29_2BirdeyeEvidenceRecord
    as _MODELS_EVIDENCE_RECORD,
    Stage29_2BirdeyePriceSnapshot as _MODELS_PRICE_SNAPSHOT,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource as _MODELS_PRICE_SOURCE,
    fetch_birdeye_price_snapshot as _MODELS_PRICE_FETCH,
)
from PHX2.stage29.stage29_2_birdeye_probe import (
    run_stage29_2_birdeye_probe as _PROBE_ENTRY_FN,
)
from PHX2.stage29.stage29_2_birdeye_probe_models import (
    PROBE_MODE_VALUES as _PROBE_MODE_VALUES,
    PROBE_STATUS_VALUES as _PROBE_STATUS_VALUES,
    Stage29_2BirdeyeHintProbeResult
    as _PROBE_RESULT_TYPE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    READINESS_STATUS_VALUES as _READINESS_STATUS_VALUES,
    STAGE29_2_READ_ENV_NAMES as _STAGE29_2_READ_ENV_NAMES,
    Stage29_2BirdeyeEndpointSecret
    as _READINESS_SECRET_TYPE,
    Stage29_2BirdeyeReadinessReport
    as _READINESS_REPORT_TYPE,
    Stage29_2BirdeyeRuntimeConfig
    as _READINESS_RUNTIME_TYPE,
    Stage29_2ReadinessEnvError
    as _READINESS_ENV_ERROR_TYPE,
    Stage29_2SafeEnvProjection
    as _READINESS_PROJECTION_TYPE,
    TIMEOUT_STATUS_VALUES as _TIMEOUT_STATUS_VALUES,
)


# ---------------------------------------------------------------------------
# Stage 29.2 inventory pins
# ---------------------------------------------------------------------------


STAGE29_2_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "birdeye_constants.py",
    "stage29_2_birdeye_models.py",
    "stage29_2_birdeye_readiness.py",
    "stage29_2_birdeye_http_transport.py",
    "stage29_2_birdeye_price_source.py",
    "stage29_2_birdeye_ath_source.py",
    "stage29_2_birdeye_probe_models.py",
    "stage29_2_birdeye_probe.py",
    "stage29_2_manifest.py",
)


STAGE29_2_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md",
)


STAGE29_2_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_2_birdeye_constants.py",
    "test_stage_29_2_birdeye_models.py",
    "test_stage_29_2_birdeye_readiness.py",
    "test_stage_29_2_birdeye_http_transport.py",
    "test_stage_29_2_birdeye_price_source.py",
    "test_stage_29_2_birdeye_ath_source.py",
    "test_stage_29_2_birdeye_probe_models.py",
    "test_stage_29_2_birdeye_probe.py",
    "test_stage_29_2_runbook.py",
    "test_stage_29_2_boundaries.py",
)


# Stage 29.2 admits ``os.environ`` ONLY in this module. Every
# other Stage 29.2 production .py file stays env-free.
STAGE29_2_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = (
    "stage29_2_birdeye_readiness.py",
)


# Stage 29.2 admits ``urllib.request`` ONLY in this module.
# Every other Stage 29.2 production .py file stays HTTP-import-
# free; the probe orchestrator invokes the transport via the
# ``Stage29_2BirdeyeUrlibTransport`` factory but does not import
# urllib directly.
STAGE29_2_HTTP_ADMITTED_BASENAMES: tuple[str, ...] = (
    "stage29_2_birdeye_http_transport.py",
)


# ---------------------------------------------------------------------------
# Stage 29.2 closed-set surface (re-exported for boundary tests)
# ---------------------------------------------------------------------------


STAGE29_2_BIRDEYE_PRICE_STATUS_VALUES: tuple[str, ...] = (
    _MODELS_PRICE_STATUS_VALUES
)
STAGE29_2_BIRDEYE_ATH_STATUS_VALUES: tuple[str, ...] = (
    _MODELS_ATH_STATUS_VALUES
)
STAGE29_2_BIRDEYE_FRESHNESS_STATUS_VALUES: tuple[str, ...] = (
    _MODELS_FRESHNESS_STATUS_VALUES
)
STAGE29_2_BIRDEYE_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    _MODELS_REFUSAL_REASON_VALUES
)
STAGE29_2_NO_INVENTION_AUDIT_VALUES: tuple[str, ...] = (
    _MODELS_NO_INVENTION_VALUES
)
STAGE29_2_READINESS_STATUS_VALUES: tuple[str, ...] = (
    _READINESS_STATUS_VALUES
)
STAGE29_2_TIMEOUT_STATUS_VALUES: tuple[str, ...] = (
    _TIMEOUT_STATUS_VALUES
)
STAGE29_2_PROBE_MODE_VALUES: tuple[str, ...] = (
    _PROBE_MODE_VALUES
)
STAGE29_2_PROBE_STATUS_VALUES: tuple[str, ...] = (
    _PROBE_STATUS_VALUES
)
STAGE29_2_PROBE_OHLCV_TYPE_ALLOWED: tuple[str, ...] = (
    _BIRDEYE_OHLCV_TYPE_ALLOWED
)


# ---------------------------------------------------------------------------
# Stage 29.2 version + endpoint pins
# ---------------------------------------------------------------------------


STAGE29_2_MINOR_VERSION: str = _STAGE29_2_MINOR_VERSION
STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION: str = (
    _STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION
)
STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION: str = (
    _STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION
)
STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION: str = (
    _STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION
)
STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION: str = (
    _STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION
)
STAGE29_2_REDACTION_TOKEN: str = _STAGE29_2_REDACTION_TOKEN
STAGE29_2_BIRDEYE_PATH_PRICE: str = _BIRDEYE_PATH_PRICE
STAGE29_2_BIRDEYE_PATH_OHLCV: str = _BIRDEYE_PATH_OHLCV
STAGE29_2_BIRDEYE_X_CHAIN_VALUE_SOLANA: str = (
    _BIRDEYE_X_CHAIN_VALUE_SOLANA
)
STAGE29_2_BIRDEYE_PRICE_SOURCE_LABEL: str = (
    _BIRDEYE_PRICE_SOURCE_LABEL
)
STAGE29_2_BIRDEYE_OHLCV_SOURCE_LABEL: str = (
    _BIRDEYE_OHLCV_SOURCE_LABEL
)
STAGE29_2_BIRDEYE_REPORTING_UNIT_USD: str = (
    _BIRDEYE_REPORTING_UNIT_USD
)
STAGE29_2_DEFAULT_OHLCV_TYPE: str = _BIRDEYE_DEFAULT_OHLCV_TYPE
STAGE29_2_DEFAULT_HTTP_TIMEOUT_SECONDS: int = (
    _DEFAULT_HTTP_TIMEOUT_SECONDS
)
STAGE29_2_DEFAULT_LOOKBACK_HOURS: int = _DEFAULT_LOOKBACK_HOURS
STAGE29_2_MIN_LOOKBACK_HOURS: int = _MIN_LOOKBACK_HOURS
STAGE29_2_MAX_LOOKBACK_HOURS: int = _MAX_LOOKBACK_HOURS
STAGE29_2_PROBE_MAX_REQUESTS: int = (
    _STAGE29_2_PROBE_MAX_REQUESTS
)
STAGE29_2_READ_ENV_NAMES_PIN: tuple[str, ...] = (
    _STAGE29_2_READ_ENV_NAMES
)


# ---------------------------------------------------------------------------
# Stage 29.2 forbidden-surface pins
# ---------------------------------------------------------------------------


STAGE29_2_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "Discord send",
    "diagnostic Discord smoke",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Stage 26 policy enforcement activation",
    "Stage 28.9 wrapper invocation in Stage 29.2",
    "Stage 28.6 bounded runner invocation in Stage 29.2",
    "Stage 28.4 audited transport invocation in Stage 29.2",
    "Pump.fun bonding-curve decoder",
    "Pump.fun bonding-curve program id constant",
    "Stage 29.3 tradeable Discord smoke",
    "Dexscreener as a dispatch authority",
    "Dexscreener as a price fallback in Stage 29.2",
    "Helius as a price source",
    "PHX1 import path",
    "raw API key on any public surface",
    "raw Birdeye base URL host literal in production source",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_PROBE_ENTRY_FN_REF: object = _PROBE_ENTRY_FN
_MODELS_PRICE_SOURCE_REF: object = _MODELS_PRICE_SOURCE
_MODELS_ATH_SOURCE_REF: object = _MODELS_ATH_SOURCE
_MODELS_PRICE_FETCH_REF: object = _MODELS_PRICE_FETCH
_MODELS_ATH_FETCH_REF: object = _MODELS_ATH_FETCH
_MODELS_PRICE_SNAPSHOT_REF: object = _MODELS_PRICE_SNAPSHOT
_MODELS_ATH_SNAPSHOT_REF: object = _MODELS_ATH_SNAPSHOT
_MODELS_EVIDENCE_RECORD_REF: object = _MODELS_EVIDENCE_RECORD
_MODELS_ERROR_TYPE_REF: object = _MODELS_ERROR_TYPE
_MODELS_HTTP_RESULT_REF: object = _MODELS_HTTP_RESULT
_MODELS_HTTP_PROTOCOL_REF: object = _MODELS_HTTP_PROTOCOL
_MODELS_HTTP_TRANSPORT_REF: object = _MODELS_HTTP_TRANSPORT
_READINESS_PROJECTION_REF: object = _READINESS_PROJECTION_TYPE
_READINESS_REPORT_REF: object = _READINESS_REPORT_TYPE
_READINESS_SECRET_REF: object = _READINESS_SECRET_TYPE
_READINESS_RUNTIME_REF: object = _READINESS_RUNTIME_TYPE
_READINESS_ENV_ERROR_REF: object = _READINESS_ENV_ERROR_TYPE
_PROBE_RESULT_REF: object = _PROBE_RESULT_TYPE


__all__ = (
    "STAGE29_2_PRODUCTION_PY_BASENAMES",
    "STAGE29_2_DOC_BASENAMES",
    "STAGE29_2_TEST_BASENAMES",
    "STAGE29_2_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_2_HTTP_ADMITTED_BASENAMES",
    "STAGE29_2_BIRDEYE_PRICE_STATUS_VALUES",
    "STAGE29_2_BIRDEYE_ATH_STATUS_VALUES",
    "STAGE29_2_BIRDEYE_FRESHNESS_STATUS_VALUES",
    "STAGE29_2_BIRDEYE_REFUSAL_REASON_VALUES",
    "STAGE29_2_NO_INVENTION_AUDIT_VALUES",
    "STAGE29_2_READINESS_STATUS_VALUES",
    "STAGE29_2_TIMEOUT_STATUS_VALUES",
    "STAGE29_2_PROBE_MODE_VALUES",
    "STAGE29_2_PROBE_STATUS_VALUES",
    "STAGE29_2_PROBE_OHLCV_TYPE_ALLOWED",
    "STAGE29_2_MINOR_VERSION",
    "STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION",
    "STAGE29_2_REDACTION_TOKEN",
    "STAGE29_2_BIRDEYE_PATH_PRICE",
    "STAGE29_2_BIRDEYE_PATH_OHLCV",
    "STAGE29_2_BIRDEYE_X_CHAIN_VALUE_SOLANA",
    "STAGE29_2_BIRDEYE_PRICE_SOURCE_LABEL",
    "STAGE29_2_BIRDEYE_OHLCV_SOURCE_LABEL",
    "STAGE29_2_BIRDEYE_REPORTING_UNIT_USD",
    "STAGE29_2_DEFAULT_OHLCV_TYPE",
    "STAGE29_2_DEFAULT_HTTP_TIMEOUT_SECONDS",
    "STAGE29_2_DEFAULT_LOOKBACK_HOURS",
    "STAGE29_2_MIN_LOOKBACK_HOURS",
    "STAGE29_2_MAX_LOOKBACK_HOURS",
    "STAGE29_2_PROBE_MAX_REQUESTS",
    "STAGE29_2_READ_ENV_NAMES_PIN",
    "STAGE29_2_FORBIDDEN_SURFACES",
)
