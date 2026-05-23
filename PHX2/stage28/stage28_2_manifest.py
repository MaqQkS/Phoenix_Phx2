"""Stage 28.2 restart-safe dispatch ledger manifest.

Stage 28.2 is the restart-safe private dispatch ledger substage of
Stage 28. It introduces an append-only, replayable, redaction-safe
JSONL ledger of dispatch intent + pre-send provenance reference +
terminal dispatch result, exposing closed-set decisions
(``PROCEED`` / ``SUPPRESS_DUPLICATE_TERMINAL`` /
``SUPPRESS_AMBIGUOUS`` / ``REJECTED_INVALID_TRANSITION``) so a
future Stage 28.6 bounded private runner can prevent duplicate
private Discord pings across process restarts.

Stage 28.2 ships NO retry / backoff logic, NO failure
classification, NO audited Discord HTTP transport, NO heartbeat /
health snapshot, NO CLI status line, NO bounded private session
runner, NO longer-session smoke harness, NO live smoke, NO Stage
29 enforcement, NO X / social, NO Telegram, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO public routing, and NO dashboard / HTTP
control server. Stage 28.2 reads NO process environment variables;
the ledger path is always a caller-supplied explicit ``Path``.

This manifest module exposes the locked Stage 28.2 schema axes
and source-file basename inventories so downstream substages
(28.3+) can pin against them without re-deriving them from the
models / ledger layers.

Exposed surface:

  * ``STAGE28_2_MINOR_VERSION``           -- ``"28.2"``.
  * ``STAGE28_2_SCHEMA_VERSION``          -- locked Stage 28.2
                                              dispatch-ledger
                                              schema version.
  * ``STAGE28_2_PRODUCTION_PY_BASENAMES`` -- locked Stage 28.2
                                              production .py
                                              basename set.
  * ``STAGE28_2_TEST_BASENAMES``          -- locked Stage 28.2
                                              test file basename
                                              set.
  * ``STAGE28_2_SCOPE_LOCKS``             -- closed-set tuple of
                                              Stage 28.2 scope
                                              locks (ledger-only;
                                              no network, no
                                              dispatch, no retry,
                                              no transport, no
                                              health, no runner,
                                              no live smoke, no
                                              enforcement, no
                                              public routing, no
                                              X / social, no
                                              Telegram, no
                                              automated trading,
                                              no wallet / private-
                                              key logic).
  * ``STAGE28_2_DEDUPE_KEY_FIELDS``       -- the closed-set tuple
                                              of Stage 28.2 dedupe
                                              key field names
                                              (token_mint /
                                              pair_quote_asset /
                                              event_kind /
                                              ping_type /
                                              normalized_event_id).
  * ``STAGE28_2_DEDUPE_STATE_VALUES``     -- the closed-set tuple
                                              of Stage 28.2 dedupe
                                              state values
                                              (RESERVED /
                                              PRE_SEND_RECORDED /
                                              DISPATCHED_OK /
                                              DISPATCHED_FAILED /
                                              DISPATCHED_AMBIGUOUS /
                                              REFUSED_PRE_SEND).
  * ``STAGE28_2_DISPATCH_DECISION_VALUES`` -- the closed-set tuple
                                               of Stage 28.2
                                               dispatch decision
                                               values.
  * ``STAGE28_2_RECORD_KIND_VALUES``       -- the closed-set tuple
                                               of Stage 28.2
                                               record kind values
                                               (RESERVE / PRE_SEND
                                               / TERMINAL).

This module imports only stdlib (``typing``) plus Stage 28.2
production modules. It does NOT import Stage 21-27 production
code, does NOT import Stage 28.1 production code, does NOT
import any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_STATE_VALUES as _DEDUPE_STATE_VALUES,
    DISPATCH_DECISION_VALUES as _DISPATCH_DECISION_VALUES,
    RECORD_KIND_VALUES as _RECORD_KIND_VALUES,
    STAGE28_2_MINOR_VERSION as _STAGE28_2_MINOR_VERSION,
    STAGE28_2_SCHEMA_VERSION as _STAGE28_2_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE28_2_MINOR_VERSION: str = _STAGE28_2_MINOR_VERSION
STAGE28_2_SCHEMA_VERSION: str = _STAGE28_2_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.2 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_2_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "dispatch_ledger_models.py",
    "dispatch_ledger.py",
    "stage28_2_manifest.py",
)


STAGE28_2_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_2_dispatch_ledger_models.py",
    "test_stage_28_2_dispatch_ledger.py",
    "test_stage_28_2_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_2_DEDUPE_KEY_FIELDS: tuple[str, ...] = (
    "token_mint",
    "pair_quote_asset",
    "event_kind",
    "ping_type",
    "normalized_event_id",
)


STAGE28_2_DEDUPE_STATE_VALUES: tuple[str, ...] = tuple(
    _DEDUPE_STATE_VALUES
)


STAGE28_2_DISPATCH_DECISION_VALUES: tuple[str, ...] = tuple(
    _DISPATCH_DECISION_VALUES
)


STAGE28_2_RECORD_KIND_VALUES: tuple[str, ...] = tuple(
    _RECORD_KIND_VALUES
)


# ---------------------------------------------------------------------------
# Stage 28.2 scope locks
# ---------------------------------------------------------------------------


# Stage 28.2 is restart-safe dispatch ledger only. The following
# locks are declared here so a downstream audit can pin them
# without re-reading the entire substage:
STAGE28_2_SCOPE_LOCKS: tuple[str, ...] = (
    "ledger-only scope",
    "no env reads",
    "no network calls",
    "no HTTP",
    "no gRPC",
    "no Discord dispatch",
    "no provider connection",
    "no retry / backoff",
    "no failure classification",
    "no audited HTTP transport",
    "no heartbeat / health snapshot",
    "no CLI status line",
    "no bounded private session runner",
    "no longer-session smoke harness",
    "no live smoke",
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
    "STAGE28_2_MINOR_VERSION",
    "STAGE28_2_SCHEMA_VERSION",
    "STAGE28_2_PRODUCTION_PY_BASENAMES",
    "STAGE28_2_TEST_BASENAMES",
    "STAGE28_2_DEDUPE_KEY_FIELDS",
    "STAGE28_2_DEDUPE_STATE_VALUES",
    "STAGE28_2_DISPATCH_DECISION_VALUES",
    "STAGE28_2_RECORD_KIND_VALUES",
    "STAGE28_2_SCOPE_LOCKS",
)
