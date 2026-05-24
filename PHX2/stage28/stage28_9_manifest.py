"""Stage 28.9 private live provider session adapter manifest.

Stage 28.9 is the post-Stage-28-closure operational bridge that
wires real provider-backed candidate events from the existing
Stage 21 / Stage 27 chain into the already-closed Stage 28.6
bounded private session runner so the operator can see real
private Discord coin pings without re-opening any Stage 28
reliability surface.

Stage 28.9 is intentionally narrow:

  * no Stage 29 enforcement / approval / activation semantics,
  * no public routing, no subscriber routing, no paid tier
    routing,
  * no Telegram, no X / social,
  * no automated trading, no wallet / private-key / signer
    logic, no position sizing, no trade execution,
  * no dashboard / HTTP control server, no daemon / systemd /
    watchdog / autorestart service,
  * no Stage 28 closure / no ``stage-28-closed`` tag movement /
    no Stage 28-wide manifest changes beyond a narrow optional
    note,
  * fake provider event source + fake transport in tests; the
    real provider client + the real Stage 28.4 audited transport
    are supplied at the operator boundary only.

This manifest module exposes the locked Stage 28.9 schema axes,
production-file / doc / test basename inventories, scope locks,
session-outcome / refusal-reason / session-mode vocabularies,
session-result field-name inventory, and the locked Stage 29-
pending filter-enforcement marker so downstream substages (Stage
29+, when implemented) can pin against them without re-deriving
them from the adapter layer.

This module is constants-only:

  * imports only stdlib (``typing``) plus the Stage 28.9 models
    + adapter + transport modules,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage28.live_provider_session_adapter import (
    STAGE28_9_CONTENT_MAX_CHARS as _ADAPTER_CONTENT_MAX_CHARS,
    STAGE28_9_DISPATCH_LEDGER_BASENAME as _ADAPTER_LEDGER_BASENAME,
    STAGE28_9_FINAL_SUMMARY_BASENAME as _ADAPTER_FINAL_SUMMARY_BASENAME,
    STAGE28_9_HEALTH_SNAPSHOT_BASENAME as _ADAPTER_HEALTH_SNAPSHOT_BASENAME,
    STAGE28_9_HEARTBEAT_BASENAME as _ADAPTER_HEARTBEAT_BASENAME,
    STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH as _ADAPTER_OUTPUT_DIR_LABEL_MAX_LENGTH,
    STAGE28_9_PENDING_ARTIFACT_PREFIX as _ADAPTER_PENDING_ARTIFACT_PREFIX,
    STAGE28_9_PING_TYPE_LABEL as _ADAPTER_PING_TYPE_LABEL,
    STAGE28_9_RUNNER_ARTIFACT_BASENAMES as _ADAPTER_RUNNER_ARTIFACT_BASENAMES,
)
from PHX2.stage28.live_provider_session_models import (
    FILTER_ENFORCEMENT_NOTICE_TEXT as _MODELS_FILTER_ENFORCEMENT_NOTICE_TEXT,
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING as _MODELS_FILTER_ENFORCEMENT_STATUS,
    POLICY_MODE_PRIVATE_OPERATOR_ONLY as _MODELS_POLICY_MODE_PRIVATE_OPERATOR_ONLY,
    REDACTION_STATUS_VALUES as _MODELS_REDACTION_STATUS_VALUES,
    REFUSAL_REASON_VALUES as _MODELS_REFUSAL_REASON_VALUES,
    SESSION_MODE_VALUES as _MODELS_SESSION_MODE_VALUES,
    SESSION_OUTCOME_VALUES as _MODELS_SESSION_OUTCOME_VALUES,
    STAGE28_9_MINOR_VERSION as _MODELS_STAGE28_9_MINOR_VERSION,
    STAGE28_9_REDACTION_TOKEN as _MODELS_STAGE28_9_REDACTION_TOKEN,
    STAGE28_9_SCHEMA_VERSION as _MODELS_STAGE28_9_SCHEMA_VERSION,
    STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES as _MODELS_COUNTER_FIELD_NAMES,
    STAGE28_9_SESSION_RESULT_FIELD_NAMES as _MODELS_FIELD_NAMES,
)


# ---------------------------------------------------------------------------
# Re-exports of the locked Stage 28.9 schema axes
# ---------------------------------------------------------------------------


STAGE28_9_MINOR_VERSION: str = _MODELS_STAGE28_9_MINOR_VERSION
STAGE28_9_SCHEMA_VERSION: str = _MODELS_STAGE28_9_SCHEMA_VERSION
STAGE28_9_REDACTION_TOKEN: str = _MODELS_STAGE28_9_REDACTION_TOKEN


# Stage 29-pending filter-enforcement marker. Constant; the
# Stage 28.9 result schema pins this value on every result.
FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING: str = (
    _MODELS_FILTER_ENFORCEMENT_STATUS
)
FILTER_ENFORCEMENT_NOTICE_TEXT: str = (
    _MODELS_FILTER_ENFORCEMENT_NOTICE_TEXT
)
POLICY_MODE_PRIVATE_OPERATOR_ONLY: str = (
    _MODELS_POLICY_MODE_PRIVATE_OPERATOR_ONLY
)


# ---------------------------------------------------------------------------
# Locked Stage 28.9 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_9_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "live_provider_session_models.py",
    "live_provider_session_adapter.py",
    "live_provider_session_transport.py",
    "stage28_9_manifest.py",
)


STAGE28_9_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_9_PRIVATE_LIVE_PROVIDER_RUNBOOK.md",
)


STAGE28_9_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_9_live_provider_session_models.py",
    "test_stage_28_9_live_provider_session_adapter.py",
    "test_stage_28_9_live_provider_session_transport.py",
    "test_stage_28_9_runbook.py",
    "test_stage_28_9_boundaries.py",
)


# ---------------------------------------------------------------------------
# Locked Stage 28.9 closed-set vocabularies re-exported for pinning
# ---------------------------------------------------------------------------


STAGE28_9_SESSION_OUTCOME_VALUES: tuple[str, ...] = tuple(
    _MODELS_SESSION_OUTCOME_VALUES
)
STAGE28_9_REFUSAL_REASON_VALUES: tuple[str, ...] = tuple(
    _MODELS_REFUSAL_REASON_VALUES
)
STAGE28_9_SESSION_MODE_VALUES: tuple[str, ...] = tuple(
    _MODELS_SESSION_MODE_VALUES
)
STAGE28_9_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _MODELS_REDACTION_STATUS_VALUES
)


# ---------------------------------------------------------------------------
# Field-name inventories re-exported
# ---------------------------------------------------------------------------


STAGE28_9_SESSION_RESULT_FIELD_NAMES: tuple[str, ...] = tuple(
    _MODELS_FIELD_NAMES
)
STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES: tuple[str, ...] = tuple(
    _MODELS_COUNTER_FIELD_NAMES
)


# ---------------------------------------------------------------------------
# Re-export of Stage 28.9 adapter-side constants
# ---------------------------------------------------------------------------


STAGE28_9_PING_TYPE_LABEL: str = _ADAPTER_PING_TYPE_LABEL
STAGE28_9_PENDING_ARTIFACT_PREFIX: str = (
    _ADAPTER_PENDING_ARTIFACT_PREFIX
)
STAGE28_9_CONTENT_MAX_CHARS: int = _ADAPTER_CONTENT_MAX_CHARS
STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH: int = (
    _ADAPTER_OUTPUT_DIR_LABEL_MAX_LENGTH
)
STAGE28_9_DISPATCH_LEDGER_BASENAME: str = (
    _ADAPTER_LEDGER_BASENAME
)
STAGE28_9_HEARTBEAT_BASENAME: str = _ADAPTER_HEARTBEAT_BASENAME
STAGE28_9_HEALTH_SNAPSHOT_BASENAME: str = (
    _ADAPTER_HEALTH_SNAPSHOT_BASENAME
)
STAGE28_9_FINAL_SUMMARY_BASENAME: str = (
    _ADAPTER_FINAL_SUMMARY_BASENAME
)
STAGE28_9_RUNNER_ARTIFACT_BASENAMES: tuple[str, ...] = tuple(
    _ADAPTER_RUNNER_ARTIFACT_BASENAMES
)


# ---------------------------------------------------------------------------
# Stage 28.9 scope locks
# ---------------------------------------------------------------------------


STAGE28_9_SCOPE_LOCKS: tuple[str, ...] = (
    "private live provider session adapter scope",
    "bridge real provider-backed candidates to Stage 28.6 runner",
    (
        "narrow Stage 28 boundary exception: Stage 21 / Stage 27 "
        "imports allowed in adapter module only"
    ),
    "fake provider event source + fake transport in tests only",
    "no real provider connection in tests",
    "no real Discord send in tests",
    "no env reads",
    "no public routing",
    "no subscriber routing",
    "no paid tier routing",
    "no X / social",
    "no Telegram",
    "no Stage 29 enforcement",
    "no approval / activation semantics",
    "no automated trading",
    "no wallet / private-key / signer logic",
    "no position sizing",
    "no trade execution",
    "no dashboard / HTTP control server",
    "no daemon / systemd / watchdog / autorestart service",
    "no Stage 28 closure tag movement",
    "no Stage 28-wide manifest rewrite",
    "no sleep / no scheduling / no backoff execution",
    "explicit caller-supplied output directory",
    "explicit operator authorization required for live private session",
    (
        "Stage 29-pending filter-enforcement marker on every "
        "rendered Discord payload"
    ),
    "redaction-safe records",
)


# ---------------------------------------------------------------------------
# Stage 28.9 forbidden surface re-declaration (defence in depth)
# ---------------------------------------------------------------------------


STAGE28_9_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "Stage 29 implementation",
    "enforcement",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "dashboard / HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
)


__all__ = (
    "STAGE28_9_MINOR_VERSION",
    "STAGE28_9_SCHEMA_VERSION",
    "STAGE28_9_REDACTION_TOKEN",
    "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING",
    "FILTER_ENFORCEMENT_NOTICE_TEXT",
    "POLICY_MODE_PRIVATE_OPERATOR_ONLY",
    "STAGE28_9_PRODUCTION_PY_BASENAMES",
    "STAGE28_9_DOC_BASENAMES",
    "STAGE28_9_TEST_BASENAMES",
    "STAGE28_9_SESSION_OUTCOME_VALUES",
    "STAGE28_9_REFUSAL_REASON_VALUES",
    "STAGE28_9_SESSION_MODE_VALUES",
    "STAGE28_9_REDACTION_STATUS_VALUES",
    "STAGE28_9_SESSION_RESULT_FIELD_NAMES",
    "STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES",
    "STAGE28_9_PING_TYPE_LABEL",
    "STAGE28_9_PENDING_ARTIFACT_PREFIX",
    "STAGE28_9_CONTENT_MAX_CHARS",
    "STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH",
    "STAGE28_9_DISPATCH_LEDGER_BASENAME",
    "STAGE28_9_HEARTBEAT_BASENAME",
    "STAGE28_9_HEALTH_SNAPSHOT_BASENAME",
    "STAGE28_9_FINAL_SUMMARY_BASENAME",
    "STAGE28_9_RUNNER_ARTIFACT_BASENAMES",
    "STAGE28_9_SCOPE_LOCKS",
    "STAGE28_9_FORBIDDEN_SURFACES",
)
