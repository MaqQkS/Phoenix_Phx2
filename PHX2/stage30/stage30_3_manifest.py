"""Stage 30.3 compact private operator runtime wiring manifest.

Constants-only re-export manifest. Pins the Stage 30.3A
inventory, the closed-set surface (compact outcome tokens,
snapshot-write sub-reason tokens, wrapper-order labels, the
forbidden-field-name vocabulary), the locked schema version, the
locked JSONL artifact basename, and the Stage 30.3 forbidden-
surface list inherited from the Stage 30.0 spec lock.

The Stage 30.3 forbidden surface (unchanged from Stage 30.0
except that Stage 30.3 IS the bounded private operator runtime
wiring substage and so removes that single surface from the
inherited list):

  * Market-cap / liquidity / volume adapter (Stage 30.4 scope).
  * Public routing, subscriber / paid routing, Telegram, X /
    social.
  * Stage 26 / Stage 29 enforcement activation.
  * Trading / wallet / signing / private key surfaces.
  * Live operator-channel send, live gRPC / HTTP / WebSocket
    provider call, live secret read.
  * Bonding-curve decoder for the upstream meme-launch surface.
  * Stage 27 / Stage 28 / Stage 29 production source
    modification.

Stage 30.3A scope (this turn):

  * Standalone wrapper / recorder / projection / writer /
    models / manifest.
  * Offline tests only.
  * Zero parallel orchestrator file.
  * Zero Stage 28.9 wiring file.
  * Zero live operator-channel ceremony.

Stage 30.3B scope (deferred, operator-authorized):

  * Parallel orchestrator that calls
    ``run_stage28_9_live_provider_session(...)`` directly with
    the Stage 30.3A wrapper + recorder injected.
  * Offline session tests.

Stage 30.3C scope (deferred, operator-authorized):

  * Controlled private live ceremony, separately authorized.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 30.3A sibling
    modules it re-exports,
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

from PHX2.stage30.stage30_3_compact_body_transport_wrapper import (
    Stage30_3CompactBodyTransportWrapper
    as _Stage30_3CompactBodyTransportWrapper,
)
from PHX2.stage30.stage30_3_compact_candidate_context_recorder import (
    Stage30_3CompactCandidateContextRecorder
    as _Stage30_3CompactCandidateContextRecorder,
)
from PHX2.stage30.stage30_3_compact_candidate_projection import (
    build_compact_ping_input_record
    as _build_compact_ping_input_record,
    project_recorded_entry_to_tier_decision_record
    as _project_recorded_entry_to_tier_decision_record,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_FAILED_CAP as _COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER
    as _COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_EXCEPTION
    as _COMPACT_OUTCOME_FAILED_EXCEPTION,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE
    as _COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
    as _COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION
    as _COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_RENDERED as _COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE
    as _COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    COMPACT_OUTCOME_VALUES as _COMPACT_OUTCOME_VALUES,
    FORBIDDEN_RECORD_FIELD_NAMES
    as _FORBIDDEN_RECORD_FIELD_NAMES,
    SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED
    as _SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED
    as _SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_VALUES
    as _SNAPSHOT_WRITE_REASON_VALUES,
    STAGE30_3_MINOR_VERSION as _STAGE30_3_MINOR_VERSION,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    as _STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
    as _STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
    Stage30_3CompactRuntimeContext
    as _Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError
    as _Stage30_3CompactRuntimeError,
    Stage30_3RecordedCandidateContext
    as _Stage30_3RecordedCandidateContext,
    Stage30_3RuntimeWiringArtifactRecord
    as _Stage30_3RuntimeWiringArtifactRecord,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT
    as _WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP
    as _WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK
    as _WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION
    as _WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY
    as _WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_VALUES
    as _WRAPPER_ORDER_LABEL_VALUES,
    is_compact_outcome_value as _is_compact_outcome_value,
    is_forbidden_record_field_name
    as _is_forbidden_record_field_name,
    is_snapshot_write_reason_value
    as _is_snapshot_write_reason_value,
    is_wrapper_order_label_value
    as _is_wrapper_order_label_value,
)
from PHX2.stage30.stage30_3_runtime_wiring_artifact_writer import (
    append_runtime_wiring_record as _APPEND_RUNTIME_WIRING_RECORD,
    encode_runtime_wiring_jsonl_line
    as _ENCODE_RUNTIME_WIRING_JSONL_LINE,
    runtime_wiring_record_to_dict
    as _RUNTIME_WIRING_RECORD_TO_DICT,
)


# ---------------------------------------------------------------------------
# Stage 30.3A inventory
# ---------------------------------------------------------------------------


STAGE30_3_PRODUCTION_INVENTORY: Tuple[str, ...] = (
    "stage30_3_compact_runtime_models.py",
    "stage30_3_compact_candidate_projection.py",
    "stage30_3_compact_candidate_context_recorder.py",
    "stage30_3_compact_body_transport_wrapper.py",
    "stage30_3_runtime_wiring_artifact_writer.py",
    "stage30_3_manifest.py",
)


STAGE30_3_TEST_INVENTORY: Tuple[str, ...] = (
    "test_stage_30_3_compact_runtime_models.py",
    "test_stage_30_3_compact_candidate_projection.py",
    "test_stage_30_3_compact_candidate_context_recorder.py",
    "test_stage_30_3_compact_body_transport_wrapper.py",
    "test_stage_30_3_compact_body_transport_wrapper_composes_with_stage29_5_6.py",
    "test_stage_30_3_runtime_wiring_artifact_writer.py",
    "test_stage_30_3_spec_lock.py",
)


# ---------------------------------------------------------------------------
# Stage 30.3 forbidden surface (inherited from the Stage 30.0 spec
# lock; Stage 30.3 IS the bounded private operator runtime wiring
# substage, so that single surface is removed from the inherited
# list).
# ---------------------------------------------------------------------------


STAGE30_3_FORBIDDEN_SURFACES: Tuple[str, ...] = (
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
    "live operator-channel send",
    "live gRPC HTTP WebSocket provider call",
    "live secret read",
    "pump" + ".fun bonding-curve decoder",
    "Stage 27 production source modification",
    "Stage 28 production source modification",
    "Stage 29 production source modification",
)


# ---------------------------------------------------------------------------
# Re-exports (closed-set surface + records + wrapper / recorder /
# projection / writer)
# ---------------------------------------------------------------------------


STAGE30_3_MINOR_VERSION: str = _STAGE30_3_MINOR_VERSION
STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION: str = (
    _STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
)
STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME: str = (
    _STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
)


COMPACT_OUTCOME_RENDERED: str = _COMPACT_OUTCOME_RENDERED
COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE: str = (
    _COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE
)
COMPACT_OUTCOME_FAILED_INPUT_SHAPE: str = (
    _COMPACT_OUTCOME_FAILED_INPUT_SHAPE
)
COMPACT_OUTCOME_FAILED_TIER_DECISION: str = (
    _COMPACT_OUTCOME_FAILED_TIER_DECISION
)
COMPACT_OUTCOME_FAILED_COMPACT_RENDER: str = (
    _COMPACT_OUTCOME_FAILED_COMPACT_RENDER
)
COMPACT_OUTCOME_FAILED_CAP: str = _COMPACT_OUTCOME_FAILED_CAP
COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE: str = (
    _COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
)
COMPACT_OUTCOME_FAILED_EXCEPTION: str = (
    _COMPACT_OUTCOME_FAILED_EXCEPTION
)
COMPACT_OUTCOME_VALUES: Tuple[str, ...] = _COMPACT_OUTCOME_VALUES


SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED: str = (
    _SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED
)
SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED: str = (
    _SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED
)
SNAPSHOT_WRITE_REASON_VALUES: Tuple[str, ...] = (
    _SNAPSHOT_WRITE_REASON_VALUES
)


WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY: str = (
    _WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY
)
WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION: str = (
    _WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION
)
WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK: str = (
    _WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK
)
WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP: str = (
    _WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP
)
WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT: str = (
    _WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT
)
WRAPPER_ORDER_LABEL_VALUES: Tuple[str, ...] = (
    _WRAPPER_ORDER_LABEL_VALUES
)


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    _FORBIDDEN_RECORD_FIELD_NAMES
)


Stage30_3CompactRuntimeContext = _Stage30_3CompactRuntimeContext
Stage30_3RecordedCandidateContext = (
    _Stage30_3RecordedCandidateContext
)
Stage30_3RuntimeWiringArtifactRecord = (
    _Stage30_3RuntimeWiringArtifactRecord
)
Stage30_3CompactRuntimeError = _Stage30_3CompactRuntimeError


is_compact_outcome_value = _is_compact_outcome_value
is_snapshot_write_reason_value = _is_snapshot_write_reason_value
is_wrapper_order_label_value = _is_wrapper_order_label_value
is_forbidden_record_field_name = _is_forbidden_record_field_name


Stage30_3CompactCandidateContextRecorder = (
    _Stage30_3CompactCandidateContextRecorder
)
Stage30_3CompactBodyTransportWrapper = (
    _Stage30_3CompactBodyTransportWrapper
)


project_recorded_entry_to_tier_decision_record = (
    _project_recorded_entry_to_tier_decision_record
)
build_compact_ping_input_record = _build_compact_ping_input_record


runtime_wiring_record_to_dict = _RUNTIME_WIRING_RECORD_TO_DICT
encode_runtime_wiring_jsonl_line = _ENCODE_RUNTIME_WIRING_JSONL_LINE
append_runtime_wiring_record = _APPEND_RUNTIME_WIRING_RECORD


__all__ = (
    # Version + locked artifact basename.
    "STAGE30_3_MINOR_VERSION",
    "STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION",
    "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
    # Inventory.
    "STAGE30_3_PRODUCTION_INVENTORY",
    "STAGE30_3_TEST_INVENTORY",
    # Forbidden surface.
    "STAGE30_3_FORBIDDEN_SURFACES",
    # Compact outcome tokens.
    "COMPACT_OUTCOME_RENDERED",
    "COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE",
    "COMPACT_OUTCOME_FAILED_INPUT_SHAPE",
    "COMPACT_OUTCOME_FAILED_TIER_DECISION",
    "COMPACT_OUTCOME_FAILED_COMPACT_RENDER",
    "COMPACT_OUTCOME_FAILED_CAP",
    "COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE",
    "COMPACT_OUTCOME_FAILED_EXCEPTION",
    "COMPACT_OUTCOME_VALUES",
    # Snapshot-write sub-reason tokens.
    "SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED",
    "SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED",
    "SNAPSHOT_WRITE_REASON_VALUES",
    # Wrapper-order labels.
    "WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY",
    "WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION",
    "WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK",
    "WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP",
    "WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT",
    "WRAPPER_ORDER_LABEL_VALUES",
    # Records + forbidden-field guard + error.
    "Stage30_3CompactRuntimeContext",
    "Stage30_3RecordedCandidateContext",
    "Stage30_3RuntimeWiringArtifactRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "Stage30_3CompactRuntimeError",
    # Helpers.
    "is_compact_outcome_value",
    "is_snapshot_write_reason_value",
    "is_wrapper_order_label_value",
    "is_forbidden_record_field_name",
    # Recorder + wrapper.
    "Stage30_3CompactCandidateContextRecorder",
    "Stage30_3CompactBodyTransportWrapper",
    # Projection.
    "project_recorded_entry_to_tier_decision_record",
    "build_compact_ping_input_record",
    # Writer.
    "runtime_wiring_record_to_dict",
    "encode_runtime_wiring_jsonl_line",
    "append_runtime_wiring_record",
)
