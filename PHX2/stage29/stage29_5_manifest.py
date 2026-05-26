"""Stage 29.5 Helius WS migration evidence + private ping
context join manifest.

Stage 29.5 closes the migration evidence gap that prevents the
Stage 29.3 + Stage 29.4 private ping chain from confirming a
post-migration ATH on every dispatched private operator ping.

Stage 29.5 ships:

  * the Stage 29.5 closed-set vocabularies + immutable record
    shapes (``stage29_5_migration_models``),
  * the Stage 29.5 Helius WebSocket migration evidence adapter
    boundary, Protocol-typed over an INJECTED transport
    (``stage29_5_helius_ws_adapter``),
  * the Stage 29.5 migration evidence artifact reader (pure file
    reader, ``stage29_5_migration_artifact_reader``),
  * the Stage 29.5 candidate-to-migration join layer
    (``stage29_5_candidate_to_migration_join``),
  * the Stage 29.5 private ping migration context projection
    (``stage29_5_private_ping_context_projection``),
  * the Stage 29.5.0 spec-lock runbook
    (``STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md``),
  * this manifest.

Stage 29.5 ships NO live network call, NO live Helius
WebSocket, NO real ``websockets`` / ``websocket-client`` /
``aiohttp`` / ``socket`` import, NO outbound HTTP, NO outbound
gRPC, NO Discord send, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO public / subscriber / paid-tier
routing, NO Stage 26 enforcement activation, NO Stage 28.9
wrapper invocation, NO Stage 28.6 bounded runner invocation, NO
Stage 28.4 audited transport invocation, NO Pump.fun bonding-
curve decoder, NO Dexscreener, NO Helius as a price source, NO
PHX1 import path, NO new env name, NO new third-party runtime
dependency.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5 sibling
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

from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes as _CANDIDATE_AXES,
    join_candidate_to_migration_evidence as _JOIN_FN,
)
from PHX2.stage29.stage29_5_helius_ws_adapter import (
    STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ
    as _WS_DEFAULT_MAX,
    STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ
    as _WS_HARD_MAX,
    STAGE29_5_HELIUS_WS_MIGRATION_KIND
    as _WS_MIGRATION_KIND,
    Stage29_5HeliusWebSocketAdapter as _WS_ADAPTER,
    Stage29_5WebSocketTransport as _WS_TRANSPORT_PROTOCOL,
    parse_helius_ws_migration_message as _WS_PARSE_FN,
)
from PHX2.stage29.stage29_5_migration_artifact_reader import (
    STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL
    as _ARTIFACT_DEFAULT_MAX,
    STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL
    as _ARTIFACT_HARD_MAX,
    STAGE29_5_MIGRATION_ARTIFACT_KIND
    as _ARTIFACT_KIND,
    Stage29_5MigrationArtifactReader as _ARTIFACT_READER,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT,
    STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES
    as _ENFORCEMENT_VALUES,
    STAGE29_5_MEASUREMENT_STATUS_VALUES
    as _MEASUREMENT_VALUES,
    STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
    as _EVIDENCE_SCHEMA_VERSION,
    STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION
    as _JOIN_SCHEMA_VERSION,
    STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
    as _JOIN_STATUS_VALUES,
    STAGE29_5_MIGRATION_SOURCE_VALUES
    as _MIGRATION_SOURCE_VALUES,
    STAGE29_5_MIGRATION_STATUS_VALUES
    as _MIGRATION_STATUS_VALUES,
    STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION
    as _CONTEXT_SCHEMA_VERSION,
    STAGE29_5_REDACTION_STATUS_VALUES
    as _REDACTION_STATUS_VALUES,
    STAGE29_5_REFUSAL_REASON_VALUES
    as _REFUSAL_REASON_VALUES,
    STAGE29_5_WARNING_CODE_VALUES
    as _WARNING_CODE_VALUES,
    Stage29_5MigrationEvidenceError as _ERROR_TYPE,
    Stage29_5MigrationEvidenceRecord
    as _EVIDENCE_RECORD,
    Stage29_5MigrationJoinRecord as _JOIN_RECORD,
    Stage29_5PrivatePingMigrationContext
    as _CONTEXT_RECORD,
)
from PHX2.stage29.stage29_5_private_ping_context_projection import (
    project_private_ping_migration_context as _PROJECT_FN,
)


# ---------------------------------------------------------------------------
# Stage 29.5 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


STAGE29_5_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
)


STAGE29_5_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_migration_models.py",
    "test_stage_29_5_helius_ws_adapter.py",
    "test_stage_29_5_migration_artifact_reader.py",
    "test_stage_29_5_candidate_to_migration_join.py",
    "test_stage_29_5_private_ping_context_projection.py",
    "test_stage_29_5_manifest.py",
    "test_stage_29_5_boundaries.py",
    "test_stage_29_5_spec_lock.py",
)


# Stage 29.5 admits ZERO env-read sites. The Helius WS adapter
# takes its transport via constructor injection; the artifact
# reader takes its path via method argument; the join layer and
# projection are pure functions. No env reads anywhere.
STAGE29_5_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5 admits ZERO outbound-HTTP / outbound-WS / outbound-
# socket sites at Stage 29.5.1. The Helius WS adapter is
# Protocol-typed over an INJECTED transport; the concrete
# transport class is intentionally not shipped at Stage 29.5.1
# and is reserved for a separately authorized operator substage.
STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5 closed-set surface (re-exported for boundary tests)
# ---------------------------------------------------------------------------


STAGE29_5_MIGRATION_STATUS_VALUES: tuple[str, ...] = (
    _MIGRATION_STATUS_VALUES
)
STAGE29_5_MIGRATION_SOURCE_VALUES: tuple[str, ...] = (
    _MIGRATION_SOURCE_VALUES
)
STAGE29_5_MIGRATION_JOIN_STATUS_VALUES: tuple[str, ...] = (
    _JOIN_STATUS_VALUES
)
STAGE29_5_MEASUREMENT_STATUS_VALUES: tuple[str, ...] = (
    _MEASUREMENT_VALUES
)
STAGE29_5_WARNING_CODE_VALUES: tuple[str, ...] = (
    _WARNING_CODE_VALUES
)
STAGE29_5_REDACTION_STATUS_VALUES: tuple[str, ...] = (
    _REDACTION_STATUS_VALUES
)
STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES: tuple[
    str, ...
] = _ENFORCEMENT_VALUES
STAGE29_5_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    _REFUSAL_REASON_VALUES
)


STAGE29_5_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


# ---------------------------------------------------------------------------
# Stage 29.5 schema-version pins
# ---------------------------------------------------------------------------


STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION: str = (
    _EVIDENCE_SCHEMA_VERSION
)
STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION: str = (
    _JOIN_SCHEMA_VERSION
)
STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION: str = (
    _CONTEXT_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Stage 29.5 adapter / reader bounds
# ---------------------------------------------------------------------------


STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ: int = (
    _WS_DEFAULT_MAX
)
STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ: int = (
    _WS_HARD_MAX
)
STAGE29_5_HELIUS_WS_MIGRATION_KIND: str = _WS_MIGRATION_KIND


STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL: int = (
    _ARTIFACT_DEFAULT_MAX
)
STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL: int = (
    _ARTIFACT_HARD_MAX
)
STAGE29_5_MIGRATION_ARTIFACT_KIND: str = _ARTIFACT_KIND


# ---------------------------------------------------------------------------
# Stage 29.5 forbidden-surface pins
# ---------------------------------------------------------------------------


STAGE29_5_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "daemon / systemd / watchdog / autorestart service",
    "infinite loop / unbounded session",
    "Discord dispatch behavior change",
    "public dashboard",
    "HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    "PHX1 import path",
    "direct PHX1 spaghetti copy",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "third or fourth provider beyond Stage 28.11 + Stage 29.2 "
    "+ Stage 29.5 Helius migration evidence only",
    "persistent dedupe index",
    "Stage 29.6+ implementation",
    "live Helius WebSocket call",
    "real websockets-library transport",
    "real socket-based transport",
    "synthetic migration source in production data flow",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_MODELS_EVIDENCE_RECORD_REF: object = _EVIDENCE_RECORD
_MODELS_JOIN_RECORD_REF: object = _JOIN_RECORD
_MODELS_CONTEXT_RECORD_REF: object = _CONTEXT_RECORD
_MODELS_ERROR_TYPE_REF: object = _ERROR_TYPE
_WS_TRANSPORT_PROTOCOL_REF: object = _WS_TRANSPORT_PROTOCOL
_WS_ADAPTER_REF: object = _WS_ADAPTER
_WS_PARSE_FN_REF: object = _WS_PARSE_FN
_ARTIFACT_READER_REF: object = _ARTIFACT_READER
_CANDIDATE_AXES_REF: object = _CANDIDATE_AXES
_JOIN_FN_REF: object = _JOIN_FN
_PROJECT_FN_REF: object = _PROJECT_FN


__all__ = (
    "STAGE29_5_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_DOC_BASENAMES",
    "STAGE29_5_TEST_BASENAMES",
    "STAGE29_5_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_MIGRATION_STATUS_VALUES",
    "STAGE29_5_MIGRATION_SOURCE_VALUES",
    "STAGE29_5_MIGRATION_JOIN_STATUS_VALUES",
    "STAGE29_5_MEASUREMENT_STATUS_VALUES",
    "STAGE29_5_WARNING_CODE_VALUES",
    "STAGE29_5_REDACTION_STATUS_VALUES",
    "STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES",
    "STAGE29_5_REFUSAL_REASON_VALUES",
    "STAGE29_5_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION",
    "STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION",
    "STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ",
    "STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ",
    "STAGE29_5_HELIUS_WS_MIGRATION_KIND",
    "STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL",
    "STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL",
    "STAGE29_5_MIGRATION_ARTIFACT_KIND",
    "STAGE29_5_FORBIDDEN_SURFACES",
)
