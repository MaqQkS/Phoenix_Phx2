"""Stage 29.5.2 offline integration proof manifest.

Stage 29.5.2 ships a pure offline composition layer over the
Stage 29.5 join + projection + the Stage 27.4 ATH context types.
The Stage 29.5.2 production inventory lives outside the Stage
29.5 production inventory pinned by ``stage29_5_manifest`` --
the Stage 29.5 manifest's tuples are unchanged at Stage 29.5.2,
which is the explicit substage discipline (every Stage 29.5
boundary scan pin survives without modification).

Stage 29.5.2 ships:

  * the Stage 29.5.2 offline integration composition module
    (``stage29_5_2_offline_integration``),
  * the Stage 29.5.2 synthetic migration evidence fixture
    builders module (``stage29_5_2_synthetic_evidence_fixtures``;
    the sole authorized site for the synthetic-source token
    literal that the Stage 29.5 closed-set vocabulary reserves
    for test fixtures),
  * this manifest module,
  * the Stage 29.5.2 offline integration proof runbook
    (``STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md``),
  * the Stage 29.5.2 test surface (see
    ``STAGE29_5_2_TEST_BASENAMES``).

Stage 29.5.2 ships NO live network call, NO live Helius WS, NO
real ``websockets`` / ``websocket-client`` / ``aiohttp`` /
``socket`` / ``grpc`` import, NO outbound HTTP, NO outbound gRPC,
NO Discord send, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO public / subscriber / paid-tier
routing, NO Stage 26 enforcement activation, NO Stage 28.9
wrapper invocation, NO Stage 28.6 bounded runner invocation, NO
Stage 28.4 audited transport invocation, NO Pump.fun bonding-
curve decoder, NO Dexscreener, NO Helius as a price source, NO
PHX1 import path, NO new env name, NO new third-party runtime
dependency.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.2 sibling
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

from PHX2.stage29.stage29_5_2_offline_integration import (
    STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
    as _OFFLINE_INTEGRATION_SCHEMA_VERSION,
    Stage29_5_2OfflineIntegrationError
    as _OFFLINE_INTEGRATION_ERROR_TYPE,
    Stage29_5_2OfflineIntegrationResult
    as _OFFLINE_INTEGRATION_RESULT,
    run_stage29_5_2_offline_integration
    as _OFFLINE_INTEGRATION_FN,
)
from PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures import (
    build_synthetic_conflicting_evidence
    as _BUILDER_CONFLICTING,
    build_synthetic_invalid_evidence as _BUILDER_INVALID,
    build_synthetic_missing_evidence as _BUILDER_MISSING,
    build_synthetic_present_evidence as _BUILDER_PRESENT,
    build_synthetic_stale_evidence as _BUILDER_STALE,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT,
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_2_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_2_offline_integration.py",
    "stage29_5_2_synthetic_evidence_fixtures.py",
    "stage29_5_2_manifest.py",
)


STAGE29_5_2_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md",
)


STAGE29_5_2_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_2_offline_integration.py",
    "test_stage_29_5_2_boundaries.py",
    "test_stage_29_5_2_no_integration_into_stage_29_3.py",
    "test_stage_29_5_2_manifest.py",
    "test_stage_29_5_2_spec_lock.py",
)


# Stage 29.5.2 admits ZERO env-read sites. The composition module
# is a pure function over caller-supplied records and a caller-
# supplied clock; the fixtures module is a pure builder; the
# manifest is constants-only.
STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.2 admits ZERO outbound-HTTP / outbound-WS /
# outbound-socket / outbound-gRPC sites. The composition layer is
# purely offline.
STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.2 schema-version pin
# ---------------------------------------------------------------------------


STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION: str = (
    _OFFLINE_INTEGRATION_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 locked enforcement token (echoed from Stage 29.5
# models)
# ---------------------------------------------------------------------------


STAGE29_5_2_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 synthetic-token guard pins
# ---------------------------------------------------------------------------


# The Stage 29.5.2 boundary scan reads this tuple to determine
# which Stage 29.5.2 production file is permitted to carry the
# bare synthetic-source token literal at runtime. Only the
# fixtures module is allowed to do so; the offline integration
# composition module + this manifest must never reference the
# bare literal at runtime.
STAGE29_5_2_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES: tuple[
    str, ...
] = (
    "stage29_5_2_synthetic_evidence_fixtures.py",
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 forbidden-surface pins
# ---------------------------------------------------------------------------


STAGE29_5_2_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "Stage 29.3 runtime wiring change",
    "Stage 29.4 runtime wiring change",
    "Stage 29.5 manifest inventory change",
    "Stage 29.6+ implementation",
    "soak pass-entrypoint wrapper",
    "side-channel artifact surface",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_OFFLINE_INTEGRATION_RESULT_REF: object = (
    _OFFLINE_INTEGRATION_RESULT
)
_OFFLINE_INTEGRATION_FN_REF: object = _OFFLINE_INTEGRATION_FN
_OFFLINE_INTEGRATION_ERROR_TYPE_REF: object = (
    _OFFLINE_INTEGRATION_ERROR_TYPE
)
_BUILDER_PRESENT_REF: object = _BUILDER_PRESENT
_BUILDER_MISSING_REF: object = _BUILDER_MISSING
_BUILDER_INVALID_REF: object = _BUILDER_INVALID
_BUILDER_STALE_REF: object = _BUILDER_STALE
_BUILDER_CONFLICTING_REF: object = _BUILDER_CONFLICTING


__all__ = (
    "STAGE29_5_2_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_2_DOC_BASENAMES",
    "STAGE29_5_2_TEST_BASENAMES",
    "STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_2_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES",
    "STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION",
    "STAGE29_5_2_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_2_FORBIDDEN_SURFACES",
)
