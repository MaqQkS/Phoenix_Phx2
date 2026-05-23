"""Stage 28.5 heartbeat / health snapshot / CLI status manifest.

Stage 28.5 is the heartbeat / health-snapshot / CLI-status
substage of Stage 28. It introduces the redaction-safe,
deterministic, operator-visibility primitives that future Stage
28.6 (longer-session bounded private runner) and Stage 28.7
(longer-session smoke harness) substages will use to emit
heartbeat / health-snapshot / final-run-summary / CLI-status
artifacts.

Stage 28.5 ships NO runner, NO retry execution, NO retry
scheduler, NO sleep / no scheduling / no backoff execution, NO
audited HTTP transport changes, NO bounded private session
runner, NO longer-session smoke harness, NO live smoke, NO Stage
29 enforcement, NO X / social, NO Telegram, NO public routing, NO
subscriber routing, NO paid tier routing, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO dashboard / HTTP control server, and NO
daemon / systemd / watchdog / autorestart service. Stage 28.5
reads NO process environment variables; every artifact path is a
caller-supplied ``pathlib.Path``.

Stage 28.5's heartbeat / snapshot / summary writers perform local
filesystem I/O ONLY against caller-supplied paths. They never
broadcast to any Discord channel, never forward to any subscriber,
never send to any public router, never call into any provider
client, never call HTTP / gRPC / sockets. The CLI status
formatter is pure: it returns a single-line string and performs
no I/O at all.

This manifest module exposes the locked Stage 28.5 schema axes
and source-file basename inventories so downstream substages
(28.6+) can pin against them without re-deriving them from the
models / writer / CLI layers.

Exposed surface:

  * ``STAGE28_5_MINOR_VERSION``                  -- ``"28.5"``.
  * ``STAGE28_5_HEARTBEAT_SCHEMA_VERSION``       -- locked
                                                    heartbeat-line
                                                    schema version.
  * ``STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION`` -- locked health-
                                                    snapshot
                                                    schema version.
  * ``STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION``   -- locked final-
                                                    run-summary
                                                    schema version.
  * ``STAGE28_5_CLI_STATUS_SCHEMA_VERSION``      -- locked CLI
                                                    status-line
                                                    model schema
                                                    version.
  * ``STAGE28_5_PRODUCTION_PY_BASENAMES``        -- locked Stage
                                                    28.5 production
                                                    .py basename
                                                    inventory.
  * ``STAGE28_5_TEST_BASENAMES``                 -- locked Stage
                                                    28.5 test file
                                                    basename
                                                    inventory.
  * ``STAGE28_5_SCOPE_LOCKS``                    -- closed-set
                                                    tuple of Stage
                                                    28.5 scope
                                                    locks.
  * ``STAGE28_5_PROVIDER_STATUS_VALUES`` etc.    -- closed-set
                                                    tuples of
                                                    Stage 28.5
                                                    status
                                                    vocabularies.
  * ``STAGE28_5_COUNTER_FIELD_NAMES``            -- closed-set
                                                    counter-field
                                                    name inventory
                                                    (per-tick).
  * ``STAGE28_5_FINAL_SUMMARY_TOTAL_FIELD_NAMES`` -- closed-set
                                                    total-counter
                                                    inventory
                                                    (cumulative).

This module imports only stdlib (``typing``) plus the Stage 28.5
production models module. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 / 28.2 / 28.3a /
28.3b / 28.4 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does NOT
read the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_VALUES as _ARTIFACT_STATUS_VALUES,
    CLI_STATUS_LINE_MODEL_FIELD_NAMES as _CLI_STATUS_LINE_MODEL_FIELD_NAMES,
    COUNTER_FIELD_NAMES as _COUNTER_FIELD_NAMES,
    DISPATCH_STATUS_VALUES as _DISPATCH_STATUS_VALUES,
    FINAL_SUMMARY_RECORD_FIELD_NAMES as _FINAL_SUMMARY_RECORD_FIELD_NAMES,
    FINAL_SUMMARY_TOTAL_FIELD_NAMES as _FINAL_SUMMARY_TOTAL_FIELD_NAMES,
    HEALTH_SNAPSHOT_RECORD_FIELD_NAMES as _HEALTH_SNAPSHOT_RECORD_FIELD_NAMES,
    HEALTH_STATUS_VALUES as _HEALTH_STATUS_VALUES,
    HEARTBEAT_RECORD_FIELD_NAMES as _HEARTBEAT_RECORD_FIELD_NAMES,
    LAST_EVENT_STATUS_VALUES as _LAST_EVENT_STATUS_VALUES,
    LAST_PING_STATUS_VALUES as _LAST_PING_STATUS_VALUES,
    LEDGER_STATUS_VALUES as _LEDGER_STATUS_VALUES,
    PRICE_STATUS_VALUES as _PRICE_STATUS_VALUES,
    PROVIDER_STATUS_VALUES as _PROVIDER_STATUS_VALUES,
    REDACTION_STATUS_VALUES as _REDACTION_STATUS_VALUES,
    RETRY_BUDGET_STATUS_VALUES as _RETRY_BUDGET_STATUS_VALUES,
    STAGE28_5_CLI_STATUS_SCHEMA_VERSION as _STAGE28_5_CLI_STATUS_SCHEMA_VERSION,
    STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION as _STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION,
    STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION as _STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    STAGE28_5_HEARTBEAT_SCHEMA_VERSION as _STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
    STAGE28_5_MINOR_VERSION as _STAGE28_5_MINOR_VERSION,
    STOP_REASON_VALUES as _STOP_REASON_VALUES,
    TRANSPORT_STATUS_VALUES as _TRANSPORT_STATUS_VALUES,
)


# Re-export for downstream pin sites.
STAGE28_5_MINOR_VERSION: str = _STAGE28_5_MINOR_VERSION
STAGE28_5_HEARTBEAT_SCHEMA_VERSION: str = (
    _STAGE28_5_HEARTBEAT_SCHEMA_VERSION
)
STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION: str = (
    _STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION
)
STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION: str = (
    _STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION
)
STAGE28_5_CLI_STATUS_SCHEMA_VERSION: str = (
    _STAGE28_5_CLI_STATUS_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Locked Stage 28.5 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "health_status_models.py",
    "heartbeat_writer.py",
    "health_snapshot_writer.py",
    "cli_status_line.py",
    "stage28_5_manifest.py",
)


STAGE28_5_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_5_health_status_models.py",
    "test_stage_28_5_heartbeat_writer.py",
    "test_stage_28_5_health_snapshot_writer.py",
    "test_stage_28_5_cli_status_line.py",
    "test_stage_28_5_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_5_PROVIDER_STATUS_VALUES: tuple[str, ...] = tuple(
    _PROVIDER_STATUS_VALUES
)
STAGE28_5_PRICE_STATUS_VALUES: tuple[str, ...] = tuple(
    _PRICE_STATUS_VALUES
)
STAGE28_5_DISPATCH_STATUS_VALUES: tuple[str, ...] = tuple(
    _DISPATCH_STATUS_VALUES
)
STAGE28_5_LEDGER_STATUS_VALUES: tuple[str, ...] = tuple(
    _LEDGER_STATUS_VALUES
)
STAGE28_5_TRANSPORT_STATUS_VALUES: tuple[str, ...] = tuple(
    _TRANSPORT_STATUS_VALUES
)
STAGE28_5_ARTIFACT_STATUS_VALUES: tuple[str, ...] = tuple(
    _ARTIFACT_STATUS_VALUES
)
STAGE28_5_HEALTH_STATUS_VALUES: tuple[str, ...] = tuple(
    _HEALTH_STATUS_VALUES
)
STAGE28_5_STOP_REASON_VALUES: tuple[str, ...] = tuple(
    _STOP_REASON_VALUES
)
STAGE28_5_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _REDACTION_STATUS_VALUES
)
STAGE28_5_LAST_EVENT_STATUS_VALUES: tuple[str, ...] = tuple(
    _LAST_EVENT_STATUS_VALUES
)
STAGE28_5_LAST_PING_STATUS_VALUES: tuple[str, ...] = tuple(
    _LAST_PING_STATUS_VALUES
)
STAGE28_5_RETRY_BUDGET_STATUS_VALUES: tuple[str, ...] = tuple(
    _RETRY_BUDGET_STATUS_VALUES
)


# ---------------------------------------------------------------------------
# Field-name inventories re-exported
# ---------------------------------------------------------------------------


STAGE28_5_COUNTER_FIELD_NAMES: tuple[str, ...] = tuple(
    _COUNTER_FIELD_NAMES
)
STAGE28_5_FINAL_SUMMARY_TOTAL_FIELD_NAMES: tuple[str, ...] = tuple(
    _FINAL_SUMMARY_TOTAL_FIELD_NAMES
)
STAGE28_5_HEARTBEAT_RECORD_FIELD_NAMES: tuple[str, ...] = tuple(
    _HEARTBEAT_RECORD_FIELD_NAMES
)
STAGE28_5_HEALTH_SNAPSHOT_RECORD_FIELD_NAMES: tuple[str, ...] = (
    tuple(_HEALTH_SNAPSHOT_RECORD_FIELD_NAMES)
)
STAGE28_5_FINAL_SUMMARY_RECORD_FIELD_NAMES: tuple[str, ...] = (
    tuple(_FINAL_SUMMARY_RECORD_FIELD_NAMES)
)
STAGE28_5_CLI_STATUS_LINE_MODEL_FIELD_NAMES: tuple[str, ...] = (
    tuple(_CLI_STATUS_LINE_MODEL_FIELD_NAMES)
)


# ---------------------------------------------------------------------------
# Stage 28.5 scope locks
# ---------------------------------------------------------------------------


# Stage 28.5 is the heartbeat / health-snapshot / CLI-status layer
# only. The following locks are declared here so a downstream
# audit can pin them without re-reading the entire substage:
STAGE28_5_SCOPE_LOCKS: tuple[str, ...] = (
    "heartbeat-and-health-snapshot-and-cli-status-only scope",
    "redaction-safe records",
    "explicit caller-supplied paths only",
    "atomic snapshot overwrite",
    "append-only heartbeat",
    "no env reads",
    "no network calls",
    "no Discord dispatch",
    "no provider connection",
    "no retry execution",
    "no audited transport changes",
    "no sleep / no scheduling / no backoff execution",
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
    "STAGE28_5_MINOR_VERSION",
    "STAGE28_5_HEARTBEAT_SCHEMA_VERSION",
    "STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION",
    "STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION",
    "STAGE28_5_CLI_STATUS_SCHEMA_VERSION",
    "STAGE28_5_PRODUCTION_PY_BASENAMES",
    "STAGE28_5_TEST_BASENAMES",
    "STAGE28_5_PROVIDER_STATUS_VALUES",
    "STAGE28_5_PRICE_STATUS_VALUES",
    "STAGE28_5_DISPATCH_STATUS_VALUES",
    "STAGE28_5_LEDGER_STATUS_VALUES",
    "STAGE28_5_TRANSPORT_STATUS_VALUES",
    "STAGE28_5_ARTIFACT_STATUS_VALUES",
    "STAGE28_5_HEALTH_STATUS_VALUES",
    "STAGE28_5_STOP_REASON_VALUES",
    "STAGE28_5_REDACTION_STATUS_VALUES",
    "STAGE28_5_LAST_EVENT_STATUS_VALUES",
    "STAGE28_5_LAST_PING_STATUS_VALUES",
    "STAGE28_5_RETRY_BUDGET_STATUS_VALUES",
    "STAGE28_5_COUNTER_FIELD_NAMES",
    "STAGE28_5_FINAL_SUMMARY_TOTAL_FIELD_NAMES",
    "STAGE28_5_HEARTBEAT_RECORD_FIELD_NAMES",
    "STAGE28_5_HEALTH_SNAPSHOT_RECORD_FIELD_NAMES",
    "STAGE28_5_FINAL_SUMMARY_RECORD_FIELD_NAMES",
    "STAGE28_5_CLI_STATUS_LINE_MODEL_FIELD_NAMES",
    "STAGE28_5_SCOPE_LOCKS",
)
