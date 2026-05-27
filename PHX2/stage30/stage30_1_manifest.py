"""Stage 30.1 tier decision manifest.

Constants-only re-export manifest. Pins the Stage 30.1 inventory,
the closed-set surface (tier tokens, tier reasons, basis tokens, the
forbidden-field-name vocabulary), the locked schema version, the
locked JSONL artifact basename, and the Stage 30.1 forbidden-surface
list inherited from the Stage 30.0 spec lock.

The Stage 30.1 forbidden surface (unchanged from Stage 30.0):

  * Compact private ping body rendering (Stage 30.2 scope).
  * Bounded private runtime session wiring (Stage 30.3 scope).
  * Market-cap / liquidity / volume adapter (Stage 30.4 scope).
  * Public routing, subscriber / paid routing, Telegram, X / social.
  * Stage 26 / Stage 29 enforcement activation.
  * Trading / wallet / signing / private key surfaces.
  * Live Discord send, live gRPC / HTTP / WebSocket provider call,
    live secret read.
  * Pump.fun bonding-curve decoder.
  * Stage 27 / Stage 28 / Stage 29 production source modification.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 30.1 sibling modules
    it re-exports,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.tier_decision_artifact_writer import (
    append_tier_decision_record as _APPEND_TIER_DECISION_RECORD,
    encode_tier_decision_jsonl_line
    as _ENCODE_TIER_DECISION_JSONL_LINE,
    tier_decision_record_to_dict
    as _TIER_DECISION_RECORD_TO_DICT,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_MC as _BASIS_MC,
    BASIS_PRICE as _BASIS_PRICE,
    BASIS_VALUES as _BASIS_VALUES,
    FORBIDDEN_RECORD_FIELD_NAMES
    as _FORBIDDEN_RECORD_FIELD_NAMES,
    STAGE30_1_MINOR_VERSION as _STAGE30_1_MINOR_VERSION,
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    as _STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION
    as _STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    Stage30_1TierDecisionError as _Stage30_1TierDecisionError,
    TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION
    as _NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    TIER_REASON_NA_MIGRATION_MISSING as _NA_MIGRATION_MISSING,
    TIER_REASON_NA_MIGRATION_SOURCE_ERROR
    as _NA_MIGRATION_SOURCE_ERROR,
    TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR
    as _NA_MIGRATION_UNSUPPORTED_PAIR,
    TIER_REASON_NA_MIGRATION_UNTRUSTED as _NA_MIGRATION_UNTRUSTED,
    TIER_REASON_TIER_1_IN_BAND as _TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND as _TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND as _TIER_3_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT
    as _UNKNOWN_ATH_NOT_PRESENT,
    TIER_REASON_UNKNOWN_BELOW_TIER_1 as _UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED
    as _UNKNOWN_DRAWDOWN_MALFORMED,
    TIER_REASON_UNKNOWN_DRAWDOWN_MISSING
    as _UNKNOWN_DRAWDOWN_MISSING,
    TIER_REASON_UNKNOWN_GRAVEYARD as _UNKNOWN_GRAVEYARD,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2 as _UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3 as _UNKNOWN_IN_GAP_T2_T3,
    TIER_REASON_VALUES as _TIER_REASON_VALUES,
    TIER_TOKEN_TIER_1 as _TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2 as _TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3 as _TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_NOT_APPLICABLE as _TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN as _TIER_TOKEN_TIER_UNKNOWN,
    TIER_TOKEN_VALUES as _TIER_TOKEN_VALUES,
    TierDecisionRecord as _TierDecisionRecord,
    is_basis_value as _is_basis_value,
    is_forbidden_record_field_name
    as _is_forbidden_record_field_name,
    is_tier_reason_value as _is_tier_reason_value,
    is_tier_token_value as _is_tier_token_value,
)
from PHX2.stage30.tier_decision_projector import (
    decide_tier as _decide_tier,
)


# ---------------------------------------------------------------------------
# Stage 30.1 inventory
# ---------------------------------------------------------------------------


STAGE30_1_PRODUCTION_INVENTORY: Tuple[str, ...] = (
    "tier_decision_models.py",
    "tier_decision_projector.py",
    "tier_decision_artifact_writer.py",
    "stage30_1_manifest.py",
)


STAGE30_1_TEST_INVENTORY: Tuple[str, ...] = (
    "test_stage_30_1_tier_decision_models.py",
    "test_stage_30_1_tier_decision_projector.py",
    "test_stage_30_1_tier_decision_artifact_writer.py",
)


# ---------------------------------------------------------------------------
# Stage 30.1 forbidden surface (inherited from the Stage 30.0 spec lock)
# ---------------------------------------------------------------------------


STAGE30_1_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "compact private ping body rendering",
    "bounded private runtime session wiring",
    "market-cap liquidity volume adapter",
    "public audience routing",
    "subscriber paid audience routing",
    "Telegram surface",
    "X social surface",
    "Stage 26 enforcement activation",
    "Stage 29 enforcement activation",
    "trading verdict emission",
    "wallet signing surface",
    "private key surface",
    "live Discord send",
    "live gRPC HTTP WebSocket provider call",
    "live secret read",
    "Pump.fun bonding-curve decoder",
    "Stage 27 production source modification",
    "Stage 28 production source modification",
    "Stage 29 production source modification",
)


# ---------------------------------------------------------------------------
# Re-exports (closed-set surface + record + projector + writer)
# ---------------------------------------------------------------------------


STAGE30_1_MINOR_VERSION: str = _STAGE30_1_MINOR_VERSION
STAGE30_1_TIER_DECISION_SCHEMA_VERSION: str = (
    _STAGE30_1_TIER_DECISION_SCHEMA_VERSION
)
STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME: str = (
    _STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
)


TIER_TOKEN_TIER_1: str = _TIER_TOKEN_TIER_1
TIER_TOKEN_TIER_2: str = _TIER_TOKEN_TIER_2
TIER_TOKEN_TIER_3: str = _TIER_TOKEN_TIER_3
TIER_TOKEN_TIER_UNKNOWN: str = _TIER_TOKEN_TIER_UNKNOWN
TIER_TOKEN_TIER_NOT_APPLICABLE: str = _TIER_TOKEN_TIER_NOT_APPLICABLE
TIER_TOKEN_VALUES: Tuple[str, ...] = _TIER_TOKEN_VALUES


TIER_REASON_NA_MIGRATION_MISSING: str = _NA_MIGRATION_MISSING
TIER_REASON_NA_MIGRATION_UNTRUSTED: str = _NA_MIGRATION_UNTRUSTED
TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR: str = (
    _NA_MIGRATION_UNSUPPORTED_PAIR
)
TIER_REASON_NA_MIGRATION_SOURCE_ERROR: str = (
    _NA_MIGRATION_SOURCE_ERROR
)
TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION: str = (
    _NA_ATH_MAY_INCLUDE_PRE_MIGRATION
)
TIER_REASON_UNKNOWN_ATH_NOT_PRESENT: str = _UNKNOWN_ATH_NOT_PRESENT
TIER_REASON_UNKNOWN_DRAWDOWN_MISSING: str = _UNKNOWN_DRAWDOWN_MISSING
TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED: str = (
    _UNKNOWN_DRAWDOWN_MALFORMED
)
TIER_REASON_UNKNOWN_BELOW_TIER_1: str = _UNKNOWN_BELOW_TIER_1
TIER_REASON_UNKNOWN_IN_GAP_T1_T2: str = _UNKNOWN_IN_GAP_T1_T2
TIER_REASON_UNKNOWN_IN_GAP_T2_T3: str = _UNKNOWN_IN_GAP_T2_T3
TIER_REASON_UNKNOWN_GRAVEYARD: str = _UNKNOWN_GRAVEYARD
TIER_REASON_TIER_1_IN_BAND: str = _TIER_1_IN_BAND
TIER_REASON_TIER_2_IN_BAND: str = _TIER_2_IN_BAND
TIER_REASON_TIER_3_IN_BAND: str = _TIER_3_IN_BAND
TIER_REASON_VALUES: Tuple[str, ...] = _TIER_REASON_VALUES


BASIS_PRICE: str = _BASIS_PRICE
BASIS_MC: str = _BASIS_MC
BASIS_VALUES: Tuple[str, ...] = _BASIS_VALUES


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    _FORBIDDEN_RECORD_FIELD_NAMES
)


TierDecisionRecord = _TierDecisionRecord
Stage30_1TierDecisionError = _Stage30_1TierDecisionError


is_tier_token_value = _is_tier_token_value
is_tier_reason_value = _is_tier_reason_value
is_basis_value = _is_basis_value
is_forbidden_record_field_name = _is_forbidden_record_field_name


decide_tier = _decide_tier


tier_decision_record_to_dict = _TIER_DECISION_RECORD_TO_DICT
encode_tier_decision_jsonl_line = _ENCODE_TIER_DECISION_JSONL_LINE
append_tier_decision_record = _APPEND_TIER_DECISION_RECORD


__all__ = (
    # Version + locked artifact basename.
    "STAGE30_1_MINOR_VERSION",
    "STAGE30_1_TIER_DECISION_SCHEMA_VERSION",
    "STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME",
    # Inventory.
    "STAGE30_1_PRODUCTION_INVENTORY",
    "STAGE30_1_TEST_INVENTORY",
    # Forbidden surface.
    "STAGE30_1_FORBIDDEN_SURFACES",
    # Tier tokens.
    "TIER_TOKEN_TIER_1",
    "TIER_TOKEN_TIER_2",
    "TIER_TOKEN_TIER_3",
    "TIER_TOKEN_TIER_UNKNOWN",
    "TIER_TOKEN_TIER_NOT_APPLICABLE",
    "TIER_TOKEN_VALUES",
    # Tier reasons.
    "TIER_REASON_NA_MIGRATION_MISSING",
    "TIER_REASON_NA_MIGRATION_UNTRUSTED",
    "TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR",
    "TIER_REASON_NA_MIGRATION_SOURCE_ERROR",
    "TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION",
    "TIER_REASON_UNKNOWN_ATH_NOT_PRESENT",
    "TIER_REASON_UNKNOWN_DRAWDOWN_MISSING",
    "TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED",
    "TIER_REASON_UNKNOWN_BELOW_TIER_1",
    "TIER_REASON_UNKNOWN_IN_GAP_T1_T2",
    "TIER_REASON_UNKNOWN_IN_GAP_T2_T3",
    "TIER_REASON_UNKNOWN_GRAVEYARD",
    "TIER_REASON_TIER_1_IN_BAND",
    "TIER_REASON_TIER_2_IN_BAND",
    "TIER_REASON_TIER_3_IN_BAND",
    "TIER_REASON_VALUES",
    # Basis.
    "BASIS_PRICE",
    "BASIS_MC",
    "BASIS_VALUES",
    # Record + forbidden-field guard + error.
    "TierDecisionRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "Stage30_1TierDecisionError",
    # Helpers.
    "is_tier_token_value",
    "is_tier_reason_value",
    "is_basis_value",
    "is_forbidden_record_field_name",
    # Projector.
    "decide_tier",
    # Writer.
    "tier_decision_record_to_dict",
    "encode_tier_decision_jsonl_line",
    "append_tier_decision_record",
)
