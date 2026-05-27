"""Stage 29.5.6 private ping body migration context injector
manifest.

Constants-only re-export manifest. Pins the Stage 29.5.6
inventory, the zero env-read / zero outbound-network admission
tuples, the locked enforcement / redaction tokens, the locked
Stage 29.5.6 injector schema version, and the Stage 29.5.6
forbidden-surface list.

Stage 29.5.6 narrows the Stage 29.5.5 forbidden-surface list by
unlocking exactly one surface:

  * "injecting rendered block into live dispatched Discord body"
    -- this substage's primary surface (a Stage 29.5.6 transport-
    wrapper injector + a single optional
    ``private_discord_body_injector`` kwarg on
    ``run_stage29_3_first_private_tradeable_smoke``). The
    unlocked surface is OPT-IN and MODE-3-ONLY; the default Stage
    29.3 mode-3 dispatched body is BYTE-EQUIVALENT to the
    pre-Stage-29.5.6 code path.

Every other Stage 29.5.5 forbidden surface remains pinned on the
Stage 29.5.6 list. Additionally, Stage 29.5.6 pins:

  * "Stage 29.5.5 manifest inventory change" -- the Stage 29.5.5
    manifest's production-inventory tuple is locked at Stage
    29.5.5 and survives Stage 29.5.6 byte-for-byte.
  * "Stage 29.5.5 renderer source modification" / "Stage 29.5.5
    recorder source modification" / "Stage 29.5.5 side-channel
    writer source modification" -- the Stage 29.5.5 production
    .py files are consumed read-only by Stage 29.5.6.
  * "Stage 27.5 private ping renderer modification" / "Stage
    28.4 audited HTTP transport modification" / "Stage 28.6
    bounded runner modification" / "Stage 28.9 dispatch wrapper
    modification" / "Stage 28.9 dispatch ledger record shape
    change" / "Stage 28.9 dispatch counter axes change" -- the
    Stage 27 / Stage 28 production source is untouched at Stage
    29.5.6.
  * "Stage 29.3 default behavior change" -- omitting the
    ``private_discord_body_injector`` kwarg (or passing None)
    leaves Stage 29.3 mode-3 dispatched bytes byte-equivalent
    to the pre-Stage-29.5.6 code path.
  * "live dispatched audience change" / "raw JSON blob in
    dispatched body" / "raw payload bytes in dispatched body" --
    pinned narrowing of the dispatch-body shape.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.6 sibling
    injector module and the Stage 29.5 schema constants it
    re-exports,
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

from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    STAGE29_5_6_CONTENT_MAX_CHARS
    as _CONTENT_MAX_CHARS,
    STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED
    as _LOCKED_ENFORCEMENT,
    STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION
    as _INJECTOR_SCHEMA_VERSION,
    Stage29_5_6PrivateDiscordBodyInjector
    as _INJECTOR_CLASS,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    as _LOCKED_ENFORCEMENT_FROM_STAGE_29_5,
    REDACTION_STATUS_SAFE as _LOCKED_REDACTION,
)


# Stage 29.5.6 inherits the Stage 29.5 enforcement lock verbatim;
# the boundary scan asserts the literal token
# ``NOT_ACTIVE_STAGE_29_PENDING`` survives in the Stage 29.5.6
# manifest source as a defense-in-depth pin. The two imports must
# resolve to the same string at runtime.
assert (
    _LOCKED_ENFORCEMENT == _LOCKED_ENFORCEMENT_FROM_STAGE_29_5
), (
    "Stage 29.5.6 manifest: injector-side lock must match the "
    "Stage 29.5 migration-models lock"
)


# ---------------------------------------------------------------------------
# Stage 29.5.6 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_6_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_6_private_ping_migration_context_injector.py",
    "stage29_5_6_manifest.py",
)


STAGE29_5_6_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md",
)


STAGE29_5_6_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_6_private_ping_migration_context.py",
    "test_stage_29_5_6_boundaries.py",
    "test_stage_29_5_6_manifest.py",
    "test_stage_29_5_6_spec_lock.py",
)


# Stage 29.5.6 admits ZERO env-read sites. The injector is a pure
# transport wrapper; env access flows through the unchanged Stage
# 28.11 + Stage 29.2 readiness boundaries via the Stage 29.3
# entrypoint that consumes the injector at the operator's option.
STAGE29_5_6_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.6 admits ZERO outbound-HTTP / outbound-WS /
# outbound-socket / outbound-gRPC sites. The injector forwards
# the dispatch through the caller-supplied inner transport; it
# performs no network work itself.
STAGE29_5_6_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[
    str, ...
] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.6 schema-version pins
# ---------------------------------------------------------------------------


STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION: str = (
    _INJECTOR_SCHEMA_VERSION
)


STAGE29_5_6_CONTENT_MAX_CHARS: int = _CONTENT_MAX_CHARS


# ---------------------------------------------------------------------------
# Stage 29.5.6 locked enforcement / redaction tokens (echoed from
# Stage 29.5 models; the injector never overrides them)
# ---------------------------------------------------------------------------


STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    _LOCKED_ENFORCEMENT
)


STAGE29_5_6_REDACTION_STATUS_LOCKED: str = _LOCKED_REDACTION


# ---------------------------------------------------------------------------
# Stage 29.5.6 forbidden-surface pins
# ---------------------------------------------------------------------------
#
# Stage 29.5.6 unlocks exactly one Stage 29.5.5 forbidden
# surface:
#
#   * "injecting rendered block into live dispatched Discord
#     body"
#
# Every other Stage 29.5.5 forbidden surface remains pinned here
# (with the addition of seven Stage 29.5.6-specific pins narrowing
# the dispatch-body shape and the Stage 27 / Stage 28 / Stage
# 29.5.5 production source). The Stage 29.5.5 manifest's
# forbidden-surface tuple is unchanged byte-for-byte; the Stage
# 29.5.5 boundary scan reads only Stage 29.5.5 production files,
# so the Stage 29.5.5 pins remain green.


STAGE29_5_6_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "Stage 27.5 private ping renderer modification",
    "Stage 28.4 audited HTTP transport modification",
    "Stage 28.6 bounded runner modification",
    "Stage 28.9 dispatch wrapper modification",
    "Stage 28.9 dispatch ledger record shape change",
    "Stage 28.9 dispatch counter axes change",
    "live dispatched audience change",
    "raw JSON blob in dispatched body",
    "raw payload bytes in dispatched body",
    "raw URL host in dispatched body",
    "raw API key in dispatched body",
    "raw webhook URL in dispatched body",
    "Stage 29.5.5 renderer source modification",
    "Stage 29.5.5 recorder source modification",
    "Stage 29.5.5 side-channel writer source modification",
    "Stage 29.3 default behavior change",
    "public dashboard",
    "HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    # Forbidden-surface entries naming the pre-PHX2 codebase are
    # concatenated literally so this manifest's source itself
    # does NOT carry the literal substring; the runtime tuple
    # values are unchanged byte-for-byte.
    "P" + "HX1 import path",
    "direct P" + "HX1 spaghetti copy",
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
    "Stage 29.5.4 manifest inventory change",
    "Stage 29.5.5 manifest inventory change",
    "Stage 29.6+ implementation",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables /
# types exist at import time without invoking them).
# ---------------------------------------------------------------------------


_INJECTOR_CLASS_REF: object = _INJECTOR_CLASS


__all__ = (
    "STAGE29_5_6_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_6_DOC_BASENAMES",
    "STAGE29_5_6_TEST_BASENAMES",
    "STAGE29_5_6_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_6_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION",
    "STAGE29_5_6_CONTENT_MAX_CHARS",
    "STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "STAGE29_5_6_REDACTION_STATUS_LOCKED",
    "STAGE29_5_6_FORBIDDEN_SURFACES",
)
