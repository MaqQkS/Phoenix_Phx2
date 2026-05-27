"""Stage 29.5.4 migration context injection manifest.

Constants-only re-export manifest. Pins the Stage 29.5.4
inventory, the zero env-read / zero outbound-network admission
tuples, the locked enforcement / redaction tokens, the locked
Stage 29.5.4 schema version, and the Stage 29.5.4
forbidden-surface list.

Stage 29.5.4 narrows the Stage 29.5.3 forbidden-surface list by
unlocking exactly one surface:

  * "direct Stage 29.3 migration-context injection" -- this
    substage's primary surface (a single optional ``migration_source``
    kwarg on ``run_stage29_3_first_private_tradeable_smoke``).

Every other Stage 29.5.3 forbidden surface remains pinned on the
Stage 29.5.4 list (including formatted Discord rendering of
migration context, Stage 29.4 runtime wiring change, Stage 29.5 /
29.5.2 / 29.5.3 manifest inventory changes, public / subscriber /
paid routing, Telegram / X / social, automated trading / wallet /
signer, Pump.fun bonding-curve, Dexscreener as a dispatch
authority, Helius as a price source, live Helius WebSocket call,
live Chainstack gRPC call, live Birdeye HTTP call, live Discord
call, new env name, new third-party runtime dependency, PHX1
import path, Stage 29.6+ implementation).

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.4 sibling
    adapter module and the Stage 29.5 schema constants it
    re-exports,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_4_migration_context_source_adapter import (
    STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION
    as _ADAPTER_SCHEMA_VERSION,
    Stage29_5_4AthContextProvider
    as _ATH_CONTEXT_PROVIDER_PROTOCOL,
    Stage29_5_4MigrationContextSourceAdapter
    as _ADAPTER_CLASS,
    Stage29_5_4MigrationEvidenceProvider
    as _EVIDENCE_PROVIDER_PROTOCOL,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT,
    REDACTION_STATUS_SAFE as _LOCKED_REDACTION,
)


# ---------------------------------------------------------------------------
# Stage 29.5.4 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_4_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_4_migration_context_source_adapter.py",
    "stage29_5_4_manifest.py",
)


STAGE29_5_4_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
)


STAGE29_5_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_4_migration_context_source_adapter.py",
    "test_stage_29_5_4_stage29_3_integration.py",
    "test_stage_29_5_4_default_preserves_no_migration_path.py",
    "test_stage_29_5_4_no_duplicate_dispatch.py",
    "test_stage_29_5_4_no_live_surface.py",
    "test_stage_29_5_4_no_public_no_enforcement_no_trading_no_social.py",
    "test_stage_29_5_4_boundaries.py",
    "test_stage_29_5_4_manifest.py",
    "test_stage_29_5_4_spec_lock.py",
    "test_stage_29_5_4_counter_invariants.py",
)


# Stage 29.5.4 admits ZERO env-read sites. The adapter is a pure
# composition layer; env access flows through the unchanged Stage
# 28.11 + Stage 29.2 readiness boundaries via the Stage 29.3
# entrypoint that consumes the adapter at the operator's option.
STAGE29_5_4_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.4 admits ZERO outbound-HTTP / outbound-WS /
# outbound-socket / outbound-gRPC sites. The adapter is
# observational; live transports remain owned by the upstream
# Stage 29.5 Helius WS adapter / Stage 29.5 artifact reader /
# Stage 29.2 Birdeye source the operator wires into the
# evidence_provider / ath_context_provider callables.
STAGE29_5_4_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.4 schema-version pin
# ---------------------------------------------------------------------------


STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION: str = (
    _ADAPTER_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Stage 29.5.4 locked enforcement / redaction tokens (echoed from
# Stage 29.5 models; the adapter never overrides them)
# ---------------------------------------------------------------------------


STAGE29_5_4_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


STAGE29_5_4_REDACTION_STATUS_LOCKED: str = _LOCKED_REDACTION


# ---------------------------------------------------------------------------
# Stage 29.5.4 forbidden-surface pins
# ---------------------------------------------------------------------------
#
# Stage 29.5.4 unlocks exactly one surface from the Stage 29.5.3
# forbidden-surface list:
#
#   * "direct Stage 29.3 migration-context injection"
#
# Every other Stage 29.5.3 forbidden surface remains pinned here.
# The Stage 29.5.3 manifest's forbidden-surface tuple is unchanged
# byte-for-byte; the Stage 29.5.3 boundary scan reads only Stage
# 29.5.3 production files, so the Stage 29.5.3 pins remain green.


STAGE29_5_4_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "Stage 29.4 runtime wiring change",
    "Stage 29.5 manifest inventory change",
    "Stage 29.5.2 manifest inventory change",
    "Stage 29.5.3 manifest inventory change",
    "Stage 29.6+ implementation",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_ADAPTER_CLASS_REF: object = _ADAPTER_CLASS
_EVIDENCE_PROVIDER_PROTOCOL_REF: object = (
    _EVIDENCE_PROVIDER_PROTOCOL
)
_ATH_CONTEXT_PROVIDER_PROTOCOL_REF: object = (
    _ATH_CONTEXT_PROVIDER_PROTOCOL
)


__all__ = (
    "STAGE29_5_4_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_4_DOC_BASENAMES",
    "STAGE29_5_4_TEST_BASENAMES",
    "STAGE29_5_4_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_4_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION",
    "STAGE29_5_4_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_4_REDACTION_STATUS_LOCKED",
    "STAGE29_5_4_FORBIDDEN_SURFACES",
)
