"""Stage 28.1 provider-neutral config manifest.

Stage 28.1 is the provider-neutral config wrapper / secrets-
readiness cleanup layer for Stage 28. It introduces Stage 28
provider-neutral env names (``PHX2_PROVIDER_GRPC_ENDPOINT``,
``PHX2_PROVIDER_RPC_URL``, ``PHX2_PROVIDER_API_KEY``,
``PHX2_PROVIDER_ID``, ``PHX2_PROVIDER_KIND``) and preserves
Stage 27-era ``HELIUS_*`` / ``PHX2_HELIUS_*`` names as legacy
aliases. Stage 28.1 ships NO dispatch ledger, NO retry policy,
NO audited Discord transport, NO heartbeat / health snapshot, NO
longer-session runner, NO Stage 29 enforcement, NO X / social,
NO Telegram, NO automated trading, and NO public routing.

This manifest module exposes the locked Stage 28.1 schema axes
and source-file basename inventories so downstream substages
(28.2+) can pin against them without re-deriving them from the
models / resolver layers.

Exposed surface:

  * ``STAGE28_1_MINOR_VERSION``           -- ``"28.1"``.
  * ``STAGE28_1_SCHEMA_VERSION``          -- locked Stage 28.1
                                              provider-neutral
                                              config schema
                                              version.
  * ``STAGE28_1_PRODUCTION_PY_BASENAMES`` -- locked Stage 28.1
                                              production .py
                                              basename set.
  * ``STAGE28_1_TEST_BASENAMES``          -- locked Stage 28.1
                                              test file basename
                                              set.
  * ``STAGE28_1_SCOPE_LOCKS``             -- closed-set tuple of
                                              Stage 28.1 scope
                                              locks (no network,
                                              no dispatch, no
                                              dedupe, no retry,
                                              no Stage 29
                                              enforcement, no X /
                                              social, no public
                                              routing, no
                                              Telegram, no
                                              automated trading,
                                              no wallet / private-
                                              key logic).

This module imports only stdlib (``typing``) plus Stage 28.1
production modules. It does NOT import Stage 21-27 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.provider_neutral_models import (
    STAGE28_1_MINOR_VERSION as _STAGE28_1_MINOR_VERSION,
    STAGE28_1_SCHEMA_VERSION as _STAGE28_1_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE28_1_MINOR_VERSION: str = _STAGE28_1_MINOR_VERSION
STAGE28_1_SCHEMA_VERSION: str = _STAGE28_1_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.1 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_1_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "provider_neutral_models.py",
    "provider_neutral_config.py",
    "provider_neutral_readiness.py",
    "stage28_1_manifest.py",
)


STAGE28_1_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_1_provider_neutral_models.py",
    "test_stage_28_1_provider_neutral_config.py",
    "test_stage_28_1_provider_neutral_readiness.py",
    "test_stage_28_1_boundaries.py",
)


# ---------------------------------------------------------------------------
# Stage 28.1 scope locks
# ---------------------------------------------------------------------------


# Stage 28.1 is config / readiness cleanup only. The following
# locks are declared here so a downstream audit can pin them
# without re-reading the entire substage:
STAGE28_1_SCOPE_LOCKS: tuple[str, ...] = (
    "no network calls",
    "no Discord dispatch",
    "no provider connection",
    "no dispatch ledger",
    "no retry / backoff",
    "no failure classification",
    "no audited HTTP transport",
    "no heartbeat / health snapshot",
    "no CLI status line",
    "no bounded private session runner",
    "no longer-session smoke harness",
    "no Stage 29 enforcement",
    "no X / social",
    "no Telegram",
    "no public routing",
    "no subscriber routing",
    "no paid tier routing",
    "no automated trading",
    "no wallet / private-key / signer logic",
    "no position sizing",
    "no trade execution",
    "no dashboard / HTTP control server",
    "no daemon / systemd / watchdog / autorestart service",
)


__all__ = (
    "STAGE28_1_MINOR_VERSION",
    "STAGE28_1_SCHEMA_VERSION",
    "STAGE28_1_PRODUCTION_PY_BASENAMES",
    "STAGE28_1_TEST_BASENAMES",
    "STAGE28_1_SCOPE_LOCKS",
)
