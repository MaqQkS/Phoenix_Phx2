"""Stage 29.3 first-real-private-tradeable-PHX2-ping manifest.

Constants-only re-export manifest mirroring the Stage 29.1 and
Stage 29.2 manifest patterns. Pins:

  * the Stage 29.3 production .py inventory,
  * the Stage 29.3 doc inventory,
  * the Stage 29.3 test inventory,
  * the reused Stage 28.11 / Stage 29.2 env-name set,
  * the locked Stage 29.3 acceptance-artifact basenames,
  * the locked Stage 29.3 closed-set vocabulary sizes,
  * the forbidden-surface inventory (closed-set).

This module performs NO runtime work, NO env reads, NO network
access, NO file I/O at import time, and NO Stage 28.9 / Stage 27
production-side coupling. It re-exports tokens / constants /
names that other Stage 29.3 modules already own.
"""

from __future__ import annotations

from PHX2.stage29.stage29_3_artifact_writer import (
    STAGE28_9_COMPANION_ARTIFACT_BASENAMES as _STAGE28_9_COMPANION_ARTIFACT_BASENAMES,
)
from PHX2.stage29.stage29_3_artifact_writer import (
    STAGE29_3_ARTIFACT_BASENAMES as _STAGE29_3_ARTIFACT_BASENAMES,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    DEFAULT_MAX_MESSAGES_TO_SCAN as _STAGE29_3_DEFAULT_MAX_MESSAGES_TO_SCAN,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    STAGE29_3_TRANSACTION_FILTER_NAME as _STAGE29_3_TRANSACTION_FILTER_NAME,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_VALUES as _STAGE29_3_PROBE_MODE_VALUES,
)
from PHX2.stage29.stage29_3_smoke_models import (
    STAGE29_3_SCHEMA_VERSION as _STAGE29_3_SCHEMA_VERSION,
)
from PHX2.stage29.stage29_3_smoke_models import (
    TRADEABLE_SMOKE_OUTCOME_VALUES as _STAGE29_3_TRADEABLE_SMOKE_OUTCOME_VALUES,
)
from PHX2.stage29.stage29_3_smoke_models import (
    TRADEABLE_SMOKE_REFUSAL_REASON_VALUES as _STAGE29_3_TRADEABLE_SMOKE_REFUSAL_REASON_VALUES,
)


# ---------------------------------------------------------------------------
# Stage 29.3 production .py inventory
# ---------------------------------------------------------------------------


STAGE29_3_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_3_smoke_models.py",
    "stage29_3_no_migration_evidence_source.py",
    "stage29_3_hint_aware_event_source.py",
    "stage29_3_artifact_writer.py",
    "stage29_3_tradeable_smoke.py",
    "stage29_3_manifest.py",
)


# ---------------------------------------------------------------------------
# Stage 29.3 doc inventory
# ---------------------------------------------------------------------------


STAGE29_3_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md",
)


# ---------------------------------------------------------------------------
# Stage 29.3 test inventory
# ---------------------------------------------------------------------------


STAGE29_3_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_3_smoke_models.py",
    "test_stage_29_3_no_migration_evidence_source.py",
    "test_stage_29_3_hint_aware_event_source.py",
    "test_stage_29_3_tradeable_smoke_orchestrator.py",
    "test_stage_29_3_artifact_writer.py",
    "test_stage_29_3_runbook.py",
    "test_stage_29_3_boundaries.py",
)


# ---------------------------------------------------------------------------
# Stage 29.3 env discipline (zero new env names; reused from
# Stage 28.11 and Stage 29.2)
# ---------------------------------------------------------------------------


# Stage 28.11 env names reused by Stage 29.3 via the Stage 28.11
# readiness boundary. Stage 29.3 production source contains zero
# direct env reads.
STAGE29_3_REUSED_STAGE28_11_ENV_NAMES: tuple[str, ...] = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
)


# Stage 29.2 env names reused by Stage 29.3 via the Stage 29.2
# readiness boundary. Stage 29.3 production source contains zero
# direct env reads.
STAGE29_3_REUSED_STAGE29_2_ENV_NAMES: tuple[str, ...] = (
    "PHX2_STAGE29_2_BIRDEYE_API_KEY",
    "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
    "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
)


STAGE29_3_ZERO_OWN_ENV_NAMES: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Stage 29.3 acceptance-artifact basenames
# ---------------------------------------------------------------------------


STAGE29_3_ACCEPTANCE_ARTIFACT_BASENAMES: tuple[str, ...] = (
    _STAGE29_3_ARTIFACT_BASENAMES
)


STAGE29_3_STAGE28_9_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    _STAGE28_9_COMPANION_ARTIFACT_BASENAMES
)


# ---------------------------------------------------------------------------
# Stage 29.3 closed-set vocabulary axes
# ---------------------------------------------------------------------------


STAGE29_3_PROBE_MODE_VALUES: tuple[str, ...] = (
    _STAGE29_3_PROBE_MODE_VALUES
)


STAGE29_3_TRADEABLE_SMOKE_OUTCOME_VALUES: tuple[str, ...] = (
    _STAGE29_3_TRADEABLE_SMOKE_OUTCOME_VALUES
)


STAGE29_3_TRADEABLE_SMOKE_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    _STAGE29_3_TRADEABLE_SMOKE_REFUSAL_REASON_VALUES
)


STAGE29_3_SCHEMA_VERSION: str = _STAGE29_3_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Stage 29.3 Yellowstone subscription pins
# ---------------------------------------------------------------------------


STAGE29_3_TRANSACTION_FILTER_NAME: str = (
    _STAGE29_3_TRANSACTION_FILTER_NAME
)


STAGE29_3_DEFAULT_MAX_MESSAGES_TO_SCAN: int = (
    _STAGE29_3_DEFAULT_MAX_MESSAGES_TO_SCAN
)


# ---------------------------------------------------------------------------
# Forbidden-surface inventory (Stage 29.3 must not ship any of
# these surfaces directly OR import them)
# ---------------------------------------------------------------------------


STAGE29_3_FORBIDDEN_SURFACE_TOKENS: tuple[str, ...] = (
    # Audience expansion: forbidden until separately authorized
    # Stage 29.4+ substages.
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
)


__all__ = (
    "STAGE29_3_PRODUCTION_PY_BASENAMES",
    "STAGE29_3_DOC_BASENAMES",
    "STAGE29_3_TEST_BASENAMES",
    "STAGE29_3_REUSED_STAGE28_11_ENV_NAMES",
    "STAGE29_3_REUSED_STAGE29_2_ENV_NAMES",
    "STAGE29_3_ZERO_OWN_ENV_NAMES",
    "STAGE29_3_ACCEPTANCE_ARTIFACT_BASENAMES",
    "STAGE29_3_STAGE28_9_COMPANION_ARTIFACT_BASENAMES",
    "STAGE29_3_PROBE_MODE_VALUES",
    "STAGE29_3_TRADEABLE_SMOKE_OUTCOME_VALUES",
    "STAGE29_3_TRADEABLE_SMOKE_REFUSAL_REASON_VALUES",
    "STAGE29_3_SCHEMA_VERSION",
    "STAGE29_3_TRANSACTION_FILTER_NAME",
    "STAGE29_3_DEFAULT_MAX_MESSAGES_TO_SCAN",
    "STAGE29_3_FORBIDDEN_SURFACE_TOKENS",
)
