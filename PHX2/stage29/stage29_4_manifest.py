"""Stage 29.4 short-session private soak manifest.

Constants-only re-export manifest mirroring the Stage 29.1 /
Stage 29.2 / Stage 29.3 manifest patterns. Pins:

  * the Stage 29.4 production .py inventory,
  * the Stage 29.4 doc inventory,
  * the Stage 29.4 test inventory,
  * the reused Stage 28.11 / Stage 29.2 / Stage 29.3 env-name set
    (Stage 29.4 introduces ZERO new env names),
  * the locked Stage 29.4 acceptance-artifact basenames,
  * the locked Stage 29.4 closed-set vocabulary axes,
  * the forbidden-surface inventory (closed-set).

This module performs NO runtime work, NO env reads, NO network
access, NO file I/O at import time, and NO Stage 27 / Stage 28 /
Stage 29.1 / Stage 29.2 / Stage 29.3 production-side coupling. It
re-exports tokens / constants / names that other Stage 29.4
modules already own.
"""

from __future__ import annotations

from PHX2.stage29.stage29_4_soak_artifact_writer import (
    STAGE29_4_ARTIFACT_BASENAMES as _STAGE29_4_ARTIFACT_BASENAMES,
)
from PHX2.stage29.stage29_4_soak_artifact_writer import (
    STAGE28_9_COMPANION_ARTIFACT_BASENAMES as _STAGE28_9_COMPANION_ARTIFACT_BASENAMES,
)
from PHX2.stage29.stage29_4_soak_artifact_writer import (
    STAGE29_3_COMPANION_ARTIFACT_BASENAMES as _STAGE29_3_COMPANION_ARTIFACT_BASENAMES,
)
from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_VALUES as _STAGE29_4_DEDUPE_OUTCOME_VALUES,
)
from PHX2.stage29.stage29_4_soak_models import (
    PROBE_MODE_VALUES as _STAGE29_4_PROBE_MODE_VALUES,
)
from PHX2.stage29.stage29_4_soak_models import (
    REDACTION_STATUS_VALUES as _STAGE29_4_REDACTION_STATUS_VALUES,
)
from PHX2.stage29.stage29_4_soak_models import (
    SOAK_OUTCOME_VALUES as _STAGE29_4_SOAK_OUTCOME_VALUES,
)
from PHX2.stage29.stage29_4_soak_models import (
    STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION as _STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION,
)
from PHX2.stage29.stage29_4_soak_models import (
    STAGE29_4_HEARTBEAT_SCHEMA_VERSION as _STAGE29_4_HEARTBEAT_SCHEMA_VERSION,
)
from PHX2.stage29.stage29_4_soak_models import (
    STAGE29_4_MINOR_VERSION as _STAGE29_4_MINOR_VERSION,
)
from PHX2.stage29.stage29_4_soak_models import (
    STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION as _STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION,
)
from PHX2.stage29.stage29_4_soak_models import (
    STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION as _STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Stage 29.4 production .py inventory
# ---------------------------------------------------------------------------


STAGE29_4_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_4_soak_models.py",
    "stage29_4_dedupe_index.py",
    "stage29_4_soak_orchestrator.py",
    "stage29_4_soak_artifact_writer.py",
    "stage29_4_manifest.py",
)


# ---------------------------------------------------------------------------
# Stage 29.4 doc inventory
# ---------------------------------------------------------------------------


STAGE29_4_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
)


# ---------------------------------------------------------------------------
# Stage 29.4 test inventory
# ---------------------------------------------------------------------------


STAGE29_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_4_spec_lock.py",
    "test_stage_29_4_soak_models.py",
    "test_stage_29_4_dedupe_index.py",
    "test_stage_29_4_soak_orchestrator.py",
    "test_stage_29_4_soak_artifact_writer.py",
    "test_stage_29_4_boundaries.py",
)


# ---------------------------------------------------------------------------
# Stage 29.4 env discipline (zero new env names; reused from
# Stage 28.11 / Stage 29.2 via Stage 29.3 entry point)
# ---------------------------------------------------------------------------


# Stage 28.11 env names reused by Stage 29.4 via the Stage 28.11
# readiness boundary that the Stage 29.3 entry point already
# invokes. Stage 29.4 production source contains zero direct env
# reads.
STAGE29_4_REUSED_STAGE28_11_ENV_NAMES: tuple[str, ...] = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
)


# Stage 29.2 env names reused by Stage 29.4 via the Stage 29.2
# readiness boundary that the Stage 29.3 entry point already
# invokes. Stage 29.4 production source contains zero direct env
# reads.
STAGE29_4_REUSED_STAGE29_2_ENV_NAMES: tuple[str, ...] = (
    "PHX2_STAGE29_2_BIRDEYE_API_KEY",
    "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
    "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
)


# Stage 29.4 introduces ZERO new env names.
STAGE29_4_ZERO_OWN_ENV_NAMES: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Stage 29.4 acceptance-artifact basenames
# ---------------------------------------------------------------------------


STAGE29_4_ACCEPTANCE_ARTIFACT_BASENAMES: tuple[str, ...] = (
    _STAGE29_4_ARTIFACT_BASENAMES
)


STAGE29_4_STAGE29_3_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    _STAGE29_3_COMPANION_ARTIFACT_BASENAMES
)


STAGE29_4_STAGE28_9_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    _STAGE28_9_COMPANION_ARTIFACT_BASENAMES
)


# ---------------------------------------------------------------------------
# Stage 29.4 closed-set vocabulary axes
# ---------------------------------------------------------------------------


STAGE29_4_PROBE_MODE_VALUES: tuple[str, ...] = (
    _STAGE29_4_PROBE_MODE_VALUES
)


STAGE29_4_SOAK_OUTCOME_VALUES: tuple[str, ...] = (
    _STAGE29_4_SOAK_OUTCOME_VALUES
)


STAGE29_4_DEDUPE_OUTCOME_VALUES: tuple[str, ...] = (
    _STAGE29_4_DEDUPE_OUTCOME_VALUES
)


STAGE29_4_REDACTION_STATUS_VALUES: tuple[str, ...] = (
    _STAGE29_4_REDACTION_STATUS_VALUES
)


STAGE29_4_MINOR_VERSION: str = _STAGE29_4_MINOR_VERSION
STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION: str = (
    _STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION
)
STAGE29_4_HEARTBEAT_SCHEMA_VERSION: str = (
    _STAGE29_4_HEARTBEAT_SCHEMA_VERSION
)
STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION: str = (
    _STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION
)
STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION: str = (
    _STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Forbidden-surface inventory (Stage 29.4 must not ship any of
# these surfaces directly OR import them)
# ---------------------------------------------------------------------------


STAGE29_4_FORBIDDEN_SURFACE_TOKENS: tuple[str, ...] = (
    # Audience expansion: forbidden until separately authorized
    # post-Stage-29 substages.
    "public_router",
    "subscriber_router",
    "paid_tier_router",
    "telegram_sender",
    "telegram_client",
    "x_social",
    "social_sidecar",
    # Stage 26 / Stage 29 enforcement activation: forbidden until
    # separately authorized.
    "enforcement_gate",
    "enforce_policy",
    # Trading / wallet / signer: forbidden indefinitely.
    "auto_trade",
    "position_sizer",
    "trade_executor",
    "wallet_signer",
    "private_key_loader",
    # Daemon / watchdog / autorestart: forbidden indefinitely.
    "watchdog",
    "autorestart",
    "daemon",
    # Dexscreener as a dispatch authority + Helius as a price
    # source: forbidden indefinitely under Stage 29.
    "dexscreener_dispatch",
    "helius_price_source",
    # Pump.fun bonding-curve decoder: deferred to a separately
    # authorized post-Stage-29.3 substage.
    "pump_fun_bonding_curve_decoder",
    "bonding_curve_program_constants",
    # PHX1 / legacy Phoenix-1 source tree.
    "Phoenix" + "_Bot",
    # Persistent dedupe index: forbidden indefinitely under
    # Stage 29.4 (cross-pass dedupe is in-memory only and never
    # serialized to disk).
    "persistent_dedupe_index",
)


__all__ = (
    "STAGE29_4_PRODUCTION_PY_BASENAMES",
    "STAGE29_4_DOC_BASENAMES",
    "STAGE29_4_TEST_BASENAMES",
    "STAGE29_4_REUSED_STAGE28_11_ENV_NAMES",
    "STAGE29_4_REUSED_STAGE29_2_ENV_NAMES",
    "STAGE29_4_ZERO_OWN_ENV_NAMES",
    "STAGE29_4_ACCEPTANCE_ARTIFACT_BASENAMES",
    "STAGE29_4_STAGE29_3_COMPANION_ARTIFACT_BASENAMES",
    "STAGE29_4_STAGE28_9_COMPANION_ARTIFACT_BASENAMES",
    "STAGE29_4_PROBE_MODE_VALUES",
    "STAGE29_4_SOAK_OUTCOME_VALUES",
    "STAGE29_4_DEDUPE_OUTCOME_VALUES",
    "STAGE29_4_REDACTION_STATUS_VALUES",
    "STAGE29_4_MINOR_VERSION",
    "STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION",
    "STAGE29_4_HEARTBEAT_SCHEMA_VERSION",
    "STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION",
    "STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION",
    "STAGE29_4_FORBIDDEN_SURFACE_TOKENS",
)
