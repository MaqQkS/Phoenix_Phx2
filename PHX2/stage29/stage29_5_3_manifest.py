"""Stage 29.5.3 soak pass-entrypoint wrapper manifest.

Constants-only re-export manifest. Pins the Stage 29.5.3
inventory, the zero env-read / zero outbound-network admission
tuples, the locked schema version + enforcement / redaction
tokens, the locked side-channel artifact basename, and the
Stage 29.5.3 forbidden-surface list.

Stage 29.5.3 narrows the Stage 29.5.2 forbidden-surface list by
unlocking exactly two surfaces:

  * "soak pass-entrypoint wrapper" -- this substage's primary
    surface.
  * "side-channel artifact surface" -- this substage's secondary
    surface.

Every other Stage 29.5.2 forbidden surface remains pinned on the
Stage 29.5.3 list (including Stage 29.3 runtime wiring change,
Stage 29.4 runtime wiring change, Stage 29.5 manifest inventory
change, formatted Discord rendering, public / subscriber / paid
routing, Telegram / X / social, automated trading / wallet /
signer, Pump.fun bonding-curve, Dexscreener as a dispatch
authority, Helius as a price source, live Helius WebSocket call,
live Chainstack gRPC call, live Birdeye HTTP call, new env name,
new third-party runtime dependency, PHX1 import path, Stage
29.6+ implementation).

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.3 sibling
    modules and the Stage 29.5 schema constants it re-exports,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_3_side_channel_artifact_writer import (
    STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    as _SIDE_CHANNEL_ARTIFACT_BASENAME,
    append_stage29_5_3_migration_context_observation
    as _APPEND_FN,
    encode_observation_jsonl_line as _ENCODE_FN,
)
from PHX2.stage29.stage29_5_3_soak_pass_wrapper import (
    Stage29_5_3AthContextProvider
    as _ATH_CONTEXT_PROVIDER_PROTOCOL,
    Stage29_5_3InnerPassEntrypoint
    as _INNER_PASS_ENTRYPOINT_PROTOCOL,
    Stage29_5_3MigrationContextSoakPassWrapper
    as _WRAPPER_CLASS,
    Stage29_5_3MigrationEvidenceProvider
    as _EVIDENCE_PROVIDER_PROTOCOL,
)
from PHX2.stage29.stage29_5_3_wrapped_pass_models import (
    OBSERVATION_STATUS_COMPOSED as _OBS_COMPOSED,
    OBSERVATION_STATUS_COMPOSITION_REJECTED
    as _OBS_COMPOSITION_REJECTED,
    OBSERVATION_STATUS_NO_CANDIDATE_AXES
    as _OBS_NO_CANDIDATE_AXES,
    OBSERVATION_STATUS_PROVIDER_REJECTED
    as _OBS_PROVIDER_REJECTED,
    STAGE29_5_3_OBSERVATION_FIELD_NAMES
    as _OBSERVATION_FIELD_NAMES,
    STAGE29_5_3_OBSERVATION_SCHEMA_VERSION
    as _OBSERVATION_SCHEMA_VERSION,
    STAGE29_5_3_OBSERVATION_STATUS_VALUES
    as _OBSERVATION_STATUS_VALUES,
    Stage29_5_3MigrationEvidenceProviderError
    as _EVIDENCE_PROVIDER_ERROR,
    Stage29_5_3PendingPassObservation
    as _PENDING_PASS_OBSERVATION,
    Stage29_5_3SideChannelArtifactError
    as _SIDE_CHANNEL_ARTIFACT_ERROR,
    Stage29_5_3WrappedPassError as _WRAPPED_PASS_ERROR,
    Stage29_5_3WrappedPassObservation as _WRAPPED_PASS_OBSERVATION,
    is_stage29_5_3_safe_candidate_base_mint
    as _IS_SAFE_CANDIDATE_BASE_MINT,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT,
    REDACTION_STATUS_SAFE as _LOCKED_REDACTION,
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_3_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_3_wrapped_pass_models.py",
    "stage29_5_3_soak_pass_wrapper.py",
    "stage29_5_3_side_channel_artifact_writer.py",
    "stage29_5_3_manifest.py",
)


STAGE29_5_3_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md",
)


STAGE29_5_3_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_3_wrapped_pass_models.py",
    "test_stage_29_5_3_soak_pass_wrapper.py",
    "test_stage_29_5_3_side_channel_artifact_writer.py",
    "test_stage_29_5_3_manifest.py",
    "test_stage_29_5_3_boundaries.py",
    "test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py",
    "test_stage_29_5_3_spec_lock.py",
)


# Stage 29.5.3 admits ZERO env-read sites. The wrapper is a pure
# delegation layer; env access flows through the unchanged Stage
# 28.11 + Stage 29.2 readiness boundaries via the inner pass
# entrypoint the operator supplies.
STAGE29_5_3_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.3 admits ZERO outbound-HTTP / outbound-WS /
# outbound-socket / outbound-gRPC sites. The wrapper is
# observational; live transports remain owned by the operator's
# inner pass entrypoint.
STAGE29_5_3_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.3 schema-version pin
# ---------------------------------------------------------------------------


STAGE29_5_3_OBSERVATION_SCHEMA_VERSION: str = (
    _OBSERVATION_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 closed-set observation status vocabulary
# ---------------------------------------------------------------------------


STAGE29_5_3_OBSERVATION_STATUS_VALUES: tuple[str, ...] = (
    _OBSERVATION_STATUS_VALUES
)


STAGE29_5_3_OBSERVATION_FIELD_NAMES: tuple[str, ...] = (
    _OBSERVATION_FIELD_NAMES
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 locked enforcement / redaction tokens (echoed from
# Stage 29.5 models)
# ---------------------------------------------------------------------------


STAGE29_5_3_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


STAGE29_5_3_REDACTION_STATUS_LOCKED: str = _LOCKED_REDACTION


# ---------------------------------------------------------------------------
# Stage 29.5.3 locked side-channel artifact basename
# ---------------------------------------------------------------------------


STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME: str = (
    _SIDE_CHANNEL_ARTIFACT_BASENAME
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 forbidden-surface pins
# ---------------------------------------------------------------------------
#
# Stage 29.5.3 unlocks exactly two surfaces from the Stage 29.5.2
# forbidden-surface list:
#
#   * "soak pass-entrypoint wrapper"
#   * "side-channel artifact surface"
#
# Every other Stage 29.5.2 forbidden surface remains pinned here.
# The Stage 29.5.2 manifest's forbidden-surface tuple is
# unchanged byte-for-byte; the Stage 29.5.2 boundary scan reads
# only Stage 29.5.2 production files, not Stage 29.5.3 production
# files, so the Stage 29.5.2 pins remain green.


STAGE29_5_3_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "production enforcement",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Telegram sender",
    "Telegram client",
    "X / social sidecar",
    "automated trading",
    "position sizing",
    "trade execution",
    "wallet / private-key / signer logic",
    "private keys",
    "Discord dispatch behavior change",
    "formatted Discord rendering",
    "public dashboard",
    "HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    "PHX1 import path",
    "direct PHX1 spaghetti copy",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "live Helius WebSocket call",
    "live Chainstack gRPC call",
    "live Birdeye HTTP call",
    "live Discord call",
    "Stage 29.3 runtime wiring change",
    "Stage 29.4 runtime wiring change",
    "Stage 29.5 manifest inventory change",
    "Stage 29.5.2 manifest inventory change",
    "direct Stage 29.3 migration-context injection",
    "Stage 29.6+ implementation",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_WRAPPER_CLASS_REF: object = _WRAPPER_CLASS
_EVIDENCE_PROVIDER_PROTOCOL_REF: object = (
    _EVIDENCE_PROVIDER_PROTOCOL
)
_ATH_CONTEXT_PROVIDER_PROTOCOL_REF: object = (
    _ATH_CONTEXT_PROVIDER_PROTOCOL
)
_INNER_PASS_ENTRYPOINT_PROTOCOL_REF: object = (
    _INNER_PASS_ENTRYPOINT_PROTOCOL
)
_WRAPPED_PASS_OBSERVATION_REF: object = (
    _WRAPPED_PASS_OBSERVATION
)
_PENDING_PASS_OBSERVATION_REF: object = (
    _PENDING_PASS_OBSERVATION
)
_IS_SAFE_CANDIDATE_BASE_MINT_REF: object = (
    _IS_SAFE_CANDIDATE_BASE_MINT
)
_WRAPPED_PASS_ERROR_REF: object = _WRAPPED_PASS_ERROR
_EVIDENCE_PROVIDER_ERROR_REF: object = (
    _EVIDENCE_PROVIDER_ERROR
)
_SIDE_CHANNEL_ARTIFACT_ERROR_REF: object = (
    _SIDE_CHANNEL_ARTIFACT_ERROR
)
_APPEND_FN_REF: object = _APPEND_FN
_ENCODE_FN_REF: object = _ENCODE_FN
_OBS_COMPOSED_REF: object = _OBS_COMPOSED
_OBS_COMPOSITION_REJECTED_REF: object = (
    _OBS_COMPOSITION_REJECTED
)
_OBS_NO_CANDIDATE_AXES_REF: object = _OBS_NO_CANDIDATE_AXES
_OBS_PROVIDER_REJECTED_REF: object = _OBS_PROVIDER_REJECTED


__all__ = (
    "STAGE29_5_3_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_3_DOC_BASENAMES",
    "STAGE29_5_3_TEST_BASENAMES",
    "STAGE29_5_3_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_3_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_3_OBSERVATION_SCHEMA_VERSION",
    "STAGE29_5_3_OBSERVATION_STATUS_VALUES",
    "STAGE29_5_3_OBSERVATION_FIELD_NAMES",
    "STAGE29_5_3_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_3_REDACTION_STATUS_LOCKED",
    "STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME",
    "STAGE29_5_3_FORBIDDEN_SURFACES",
)
