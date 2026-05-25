"""Stage 29.1 PumpSwap hint extractor manifest.

Stage 29.1 is the FIRST Stage 29 substage past the Stage 29.0
spec-lock pass to ship runtime code. It ships:

  * the PumpSwap program constants (program id, known quote
    mints, SPL Token program ids, PumpSwap Anchor BuyEvent /
    SellEvent event discriminators, vendored-IDL provenance
    pins),
  * the closed-set hint-extraction outcome / no-evidence-reason
    / evidence-source vocabularies + the immutable hint
    extraction result record,
  * the pure hint extractor function
    (``extract_pumpswap_hints``),
  * the thin hint-aware decoder that wraps the unchanged Stage
    28.11 baseline decoder + the Stage 29.1 extractor and
    rebuilds a hint-populated Stage 28.10 payload,
  * the closed-set probe mode / status / refusal-reason
    vocabularies + the immutable probe-result record,
  * the live probe orchestrator (the single Stage 29.1
    production file allowed to import ``grpc``),
  * the operator runbook,
  * this manifest,
  * the vendored public PumpSwap Anchor IDL at
    ``PHX2/proto/stage29_1/source/pump_amm.json``.

Stage 29.1 ships NO real Discord send, NO Birdeye adapter, NO
Telegram, NO X / social, NO automated trading, NO wallet /
private-key / signer logic, NO position sizing, NO trade
execution, NO public / subscriber / paid-tier routing, NO Stage
26 enforcement activation, NO Stage 28.9 wrapper invocation, NO
Stage 28.6 runner invocation, NO Stage 28.4 transport
invocation, NO Pump.fun bonding-curve decoder, and NO Pump.fun
bonding-curve program id constant.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.1 sibling
    modules,
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

from PHX2.stage29.pumpswap_hint_aware_decoder import (
    decode_subscribe_update_with_pumpswap_hints
    as _DECODER_DECODE_WITH_HINTS,
    is_hint_bearing_payload as _DECODER_IS_HINT_BEARING,
)
from PHX2.stage29.pumpswap_hint_extractor import (
    extract_pumpswap_hints as _EXTRACTOR_FN,
)
from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_VALUES as _MODELS_OUTCOME_VALUES,
    NO_EVIDENCE_REASON_VALUES as _MODELS_NO_EVIDENCE_VALUES,
    POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES
    as _MODELS_POOL_ACCOUNT_SOURCE_VALUES,
    QUOTE_MINT_EVIDENCE_SOURCE_VALUES
    as _MODELS_QUOTE_MINT_SOURCE_VALUES,
    Stage29_1PumpSwapHintExtractionResult as _MODELS_RESULT_TYPE,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES as _CONSTANTS_BUY_DISC,
    PUMPSWAP_PROGRAM_ID as _CONSTANTS_PUMPSWAP_PROGRAM_ID,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES
    as _CONSTANTS_SELL_DISC,
    SPL_TOKEN_2022_PROGRAM_ID as _CONSTANTS_SPL_TOKEN_2022_PID,
    SPL_TOKEN_PROGRAM_ID as _CONSTANTS_SPL_TOKEN_PID,
    STAGE29_1_MINOR_VERSION as _CONSTANTS_MINOR_VERSION,
    STAGE29_1_SCHEMA_VERSION as _CONSTANTS_SCHEMA_VERSION,
    USDC_MINT as _CONSTANTS_USDC_MINT,
    VENDORED_PUMP_AMM_IDL_BYTE_LENGTH
    as _CONSTANTS_VENDORED_IDL_BYTES,
    VENDORED_PUMP_AMM_IDL_RELATIVE_PATH
    as _CONSTANTS_VENDORED_IDL_PATH,
    VENDORED_PUMP_AMM_IDL_SHA256 as _CONSTANTS_VENDORED_IDL_SHA,
    WRAPPED_SOL_MINT as _CONSTANTS_WSOL_MINT,
)
from PHX2.stage29.stage29_1_hint_probe_models import (
    PROBE_MODE_VALUES as _PROBE_MODE_VALUES,
    PROBE_STATUS_VALUES as _PROBE_STATUS_VALUES,
    REFUSAL_REASON_VALUES as _PROBE_REFUSAL_VALUES,
    Stage29_1HintProbeResult as _PROBE_RESULT_TYPE,
)
from PHX2.stage29.stage29_1_pumpswap_hint_probe import (
    DEFAULT_MAX_MESSAGES_TO_SCAN as _PROBE_DEFAULT_MAX_MESSAGES,
    GRPC_METADATA_KEY_X_TOKEN as _PROBE_METADATA_KEY,
    STAGE29_1_TRANSACTION_FILTER_NAME as _PROBE_FILTER_NAME,
    run_stage29_1_pumpswap_hint_probe as _PROBE_ENTRY_FN,
)


# ---------------------------------------------------------------------------
# Stage 29.1 inventory pins
# ---------------------------------------------------------------------------


STAGE29_1_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "pumpswap_program_constants.py",
    "pumpswap_hint_models.py",
    "pumpswap_hint_extractor.py",
    "pumpswap_hint_aware_decoder.py",
    "stage29_1_hint_probe_models.py",
    "stage29_1_pumpswap_hint_probe.py",
    "stage29_1_manifest.py",
)


STAGE29_1_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md",
)


STAGE29_1_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_1_pumpswap_program_constants.py",
    "test_stage_29_1_pumpswap_hint_models.py",
    "test_stage_29_1_pumpswap_hint_extractor.py",
    "test_stage_29_1_pumpswap_hint_aware_decoder.py",
    "test_stage_29_1_hint_probe_models.py",
    "test_stage_29_1_pumpswap_hint_probe.py",
    "test_stage_29_1_runbook.py",
    "test_stage_29_1_boundaries.py",
    "test_stage_29_1_vendored_idl.py",
)


# Stage 29.1 admits ``grpc`` + generated stubs ONLY in these
# modules. Every other Stage 29.1 production .py file must NOT
# import them.
STAGE29_1_GRPC_ADMITTED_BASENAMES: tuple[str, ...] = (
    "stage29_1_pumpswap_hint_probe.py",
)


# Stage 29.1 admits generated Yellowstone protobuf stubs in
# these modules ONLY.
STAGE29_1_GENERATED_STUB_ADMITTED_BASENAMES: tuple[str, ...] = (
    "pumpswap_hint_extractor.py",
    "pumpswap_hint_aware_decoder.py",
    "stage29_1_pumpswap_hint_probe.py",
)


# Stage 29.1 admits NO ``os.environ`` reads in ANY production
# .py module. The unchanged Stage 28.11 readiness module remains
# the single env-read boundary for the Stage 28.11 + Stage 29.1
# chain.
STAGE29_1_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Stage 29.1 vendored-IDL pins
# ---------------------------------------------------------------------------


STAGE29_1_VENDORED_IDL_RELATIVE_PATH: str = (
    _CONSTANTS_VENDORED_IDL_PATH
)
STAGE29_1_VENDORED_IDL_SHA256: str = _CONSTANTS_VENDORED_IDL_SHA
STAGE29_1_VENDORED_IDL_BYTE_LENGTH: int = (
    _CONSTANTS_VENDORED_IDL_BYTES
)
STAGE29_1_VENDORED_IDL_ADDRESS: str = (
    _CONSTANTS_PUMPSWAP_PROGRAM_ID
)
STAGE29_1_VENDORED_IDL_NAME: str = "pump_amm"


# ---------------------------------------------------------------------------
# Stage 29.1 closed-set surface (re-exported for boundary tests)
# ---------------------------------------------------------------------------


STAGE29_1_HINT_EXTRACTION_OUTCOME_VALUES: tuple[str, ...] = (
    _MODELS_OUTCOME_VALUES
)
STAGE29_1_NO_EVIDENCE_REASON_VALUES: tuple[str, ...] = (
    _MODELS_NO_EVIDENCE_VALUES
)
STAGE29_1_POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES: tuple[
    str, ...
] = _MODELS_POOL_ACCOUNT_SOURCE_VALUES
STAGE29_1_QUOTE_MINT_EVIDENCE_SOURCE_VALUES: tuple[str, ...] = (
    _MODELS_QUOTE_MINT_SOURCE_VALUES
)
STAGE29_1_PROBE_MODE_VALUES: tuple[str, ...] = _PROBE_MODE_VALUES
STAGE29_1_PROBE_STATUS_VALUES: tuple[str, ...] = (
    _PROBE_STATUS_VALUES
)
STAGE29_1_PROBE_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    _PROBE_REFUSAL_VALUES
)


# ---------------------------------------------------------------------------
# Stage 29.1 version + filter pins
# ---------------------------------------------------------------------------


STAGE29_1_MINOR_VERSION: str = _CONSTANTS_MINOR_VERSION
STAGE29_1_SCHEMA_VERSION: str = _CONSTANTS_SCHEMA_VERSION
STAGE29_1_TRANSACTION_FILTER_NAME: str = _PROBE_FILTER_NAME
STAGE29_1_DEFAULT_MAX_MESSAGES_TO_SCAN: int = (
    _PROBE_DEFAULT_MAX_MESSAGES
)
STAGE29_1_GRPC_METADATA_KEY_X_TOKEN: str = _PROBE_METADATA_KEY


# ---------------------------------------------------------------------------
# Stage 29.1 forbidden-surface pins
# ---------------------------------------------------------------------------


STAGE29_1_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "Discord send",
    "diagnostic Discord smoke",
    "Birdeye adapter",
    "Dexscreener as a dispatch authority",
    "Helius as a primary provider",
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
    "Stage 28.9 wrapper invocation in Stage 29.1",
    "Stage 28.6 bounded runner invocation in Stage 29.1",
    "Stage 28.4 audited transport invocation in Stage 29.1",
    "Pump.fun bonding-curve decoder",
    "Pump.fun bonding-curve program id constant",
    "Stage 29.2 Birdeye adapter implementation",
    "Stage 29.3 tradeable Discord smoke",
    "PHX1 import path",
)


# ---------------------------------------------------------------------------
# Public re-exports used by Stage 29.1 boundary tests
# ---------------------------------------------------------------------------


PUMPSWAP_PROGRAM_ID: str = _CONSTANTS_PUMPSWAP_PROGRAM_ID
WRAPPED_SOL_MINT: str = _CONSTANTS_WSOL_MINT
USDC_MINT: str = _CONSTANTS_USDC_MINT
SPL_TOKEN_PROGRAM_ID: str = _CONSTANTS_SPL_TOKEN_PID
SPL_TOKEN_2022_PROGRAM_ID: str = _CONSTANTS_SPL_TOKEN_2022_PID
PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES: bytes = (
    _CONSTANTS_BUY_DISC
)
PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES: bytes = (
    _CONSTANTS_SELL_DISC
)


# Sentinels so the boundary scan can pin these named callables /
# types exist at import time without invoking them.
_EXTRACTOR_FN_REF: object = _EXTRACTOR_FN
_DECODER_DECODE_WITH_HINTS_REF: object = _DECODER_DECODE_WITH_HINTS
_DECODER_IS_HINT_BEARING_REF: object = _DECODER_IS_HINT_BEARING
_PROBE_ENTRY_FN_REF: object = _PROBE_ENTRY_FN
_MODELS_RESULT_TYPE_REF: object = _MODELS_RESULT_TYPE
_PROBE_RESULT_TYPE_REF: object = _PROBE_RESULT_TYPE


__all__ = (
    "STAGE29_1_PRODUCTION_PY_BASENAMES",
    "STAGE29_1_DOC_BASENAMES",
    "STAGE29_1_TEST_BASENAMES",
    "STAGE29_1_GRPC_ADMITTED_BASENAMES",
    "STAGE29_1_GENERATED_STUB_ADMITTED_BASENAMES",
    "STAGE29_1_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_1_VENDORED_IDL_RELATIVE_PATH",
    "STAGE29_1_VENDORED_IDL_SHA256",
    "STAGE29_1_VENDORED_IDL_BYTE_LENGTH",
    "STAGE29_1_VENDORED_IDL_ADDRESS",
    "STAGE29_1_VENDORED_IDL_NAME",
    "STAGE29_1_HINT_EXTRACTION_OUTCOME_VALUES",
    "STAGE29_1_NO_EVIDENCE_REASON_VALUES",
    "STAGE29_1_POOL_ACCOUNT_EVIDENCE_SOURCE_VALUES",
    "STAGE29_1_QUOTE_MINT_EVIDENCE_SOURCE_VALUES",
    "STAGE29_1_PROBE_MODE_VALUES",
    "STAGE29_1_PROBE_STATUS_VALUES",
    "STAGE29_1_PROBE_REFUSAL_REASON_VALUES",
    "STAGE29_1_MINOR_VERSION",
    "STAGE29_1_SCHEMA_VERSION",
    "STAGE29_1_TRANSACTION_FILTER_NAME",
    "STAGE29_1_DEFAULT_MAX_MESSAGES_TO_SCAN",
    "STAGE29_1_GRPC_METADATA_KEY_X_TOKEN",
    "STAGE29_1_FORBIDDEN_SURFACES",
    "PUMPSWAP_PROGRAM_ID",
    "WRAPPED_SOL_MINT",
    "USDC_MINT",
    "SPL_TOKEN_PROGRAM_ID",
    "SPL_TOKEN_2022_PROGRAM_ID",
    "PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES",
    "PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES",
)
