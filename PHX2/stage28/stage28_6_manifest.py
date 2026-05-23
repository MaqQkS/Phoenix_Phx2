"""Stage 28.6 bounded private session runner manifest.

Stage 28.6 is the longer-session bounded private runner substage
of Stage 28. It composes the Stage 28.1 / 28.2 / 28.3a / 28.3b /
28.4 / 28.5 reliability primitives into a single, deterministic,
redaction-safe runner with graceful shutdown semantics. Stage
28.6 ships NO live smoke; the runner consumes a caller-supplied
bounded candidate stream and a caller-injected transport
(typically a fake transport in tests; a Stage 28.4-shaped adapter
in a future Stage 28.7 authorized smoke).

Stage 28.6 ships NO live smoke, NO real Discord send, NO real
provider connection, NO uncontrolled session, NO daemon /
service / watchdog / autorestart service, NO Stage 29
enforcement, NO X / social, NO Telegram, NO public routing, NO
subscriber routing, NO paid tier routing, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO dashboard / HTTP control server. Stage 28.6
reads NO process environment variables; every dependency is a
caller-injected primitive.

The Stage 28.6 runner accepts a transport implementing the
``Stage28_6PrivateTransport`` protocol via dependency injection.
Tests inject a deterministic ``Stage28_6FakeTransport``; a future
Stage 28.7 substage will introduce a thin adapter that binds a
real Stage 28.4 ``Stage28_4AuditedHttpTransport`` + a webhook URL
inside itself.

Stage 28.6 may execute bounded immediate retry attempts against
the injected transport. Every retry attempt is:

  * counted in the run summary,
  * bounded by the per-failure Stage 28.3b retry profile,
  * bounded by the session-wide ``max_total_retries`` budget,
  * bounded by a hard local cap that prevents an unbounded loop
    even if the policy somehow returns RETRY_ALLOWED forever,
  * executed without sleeping, scheduling, queuing, or spawning
    a thread / async task / subprocess.

This manifest module exposes the locked Stage 28.6 schema axes
and source-file basename inventories so downstream substages
(28.7+) can pin against them without re-deriving them from the
models / runner layers.

Exposed surface:

  * ``STAGE28_6_MINOR_VERSION``                          -- ``"28.6"``.
  * ``STAGE28_6_SCHEMA_VERSION``                         -- locked
                                                            Stage 28.6
                                                            run-summary
                                                            schema
                                                            version.
  * ``STAGE28_6_PRODUCTION_PY_BASENAMES``                -- locked
                                                            Stage 28.6
                                                            production
                                                            .py basename
                                                            inventory.
  * ``STAGE28_6_TEST_BASENAMES``                         -- locked
                                                            Stage 28.6
                                                            test file
                                                            basename
                                                            inventory.
  * ``STAGE28_6_SCOPE_LOCKS``                            -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            scope
                                                            locks.
  * ``STAGE28_6_CANDIDATE_PAIR_STATUS_VALUES``           -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            candidate
                                                            pair status
                                                            tokens.
  * ``STAGE28_6_CANDIDATE_PRICE_STATUS_VALUES``          -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            candidate
                                                            price status
                                                            tokens.
  * ``STAGE28_6_RUN_STOP_REASON_VALUES``                 -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            run-summary
                                                            stop-reason
                                                            tokens.
  * ``STAGE28_6_FINAL_HEALTH_STATUS_VALUES``             -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            final
                                                            health
                                                            status
                                                            tokens.
  * ``STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES``        -- closed-set
                                                            tuple of
                                                            Stage 28.6
                                                            run-summary
                                                            counter
                                                            field names.
  * ``STAGE28_6_RUN_SUMMARY_FIELD_NAMES``                -- canonical
                                                            Stage 28.6
                                                            run-summary
                                                            field-name
                                                            inventory.

This module imports only stdlib (``typing``) plus the Stage 28.6
session-runner models module. It does NOT import Stage 21-27
production code, does NOT import any network / RPC / messaging /
DB / scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_VALUES as _CANDIDATE_PAIR_STATUS_VALUES,
    CANDIDATE_PRICE_STATUS_VALUES as _CANDIDATE_PRICE_STATUS_VALUES,
    STAGE28_6_FINAL_HEALTH_STATUS_VALUES as _STAGE28_6_FINAL_HEALTH_STATUS_VALUES,
    STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES as _STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES,
    STAGE28_6_MINOR_VERSION as _STAGE28_6_MINOR_VERSION,
    STAGE28_6_REDACTION_STATUS_VALUES as _STAGE28_6_REDACTION_STATUS_VALUES,
    STAGE28_6_RUN_STOP_REASON_VALUES as _STAGE28_6_RUN_STOP_REASON_VALUES,
    STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES as _STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES,
    STAGE28_6_RUN_SUMMARY_FIELD_NAMES as _STAGE28_6_RUN_SUMMARY_FIELD_NAMES,
    STAGE28_6_SCHEMA_VERSION as _STAGE28_6_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE28_6_MINOR_VERSION: str = _STAGE28_6_MINOR_VERSION
STAGE28_6_SCHEMA_VERSION: str = _STAGE28_6_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.6 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_6_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "session_runner_models.py",
    "bounded_private_session_runner.py",
    "stage28_6_manifest.py",
)


STAGE28_6_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_6_session_runner_models.py",
    "test_stage_28_6_bounded_private_session_runner.py",
    "test_stage_28_6_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_6_CANDIDATE_PAIR_STATUS_VALUES: tuple[str, ...] = tuple(
    _CANDIDATE_PAIR_STATUS_VALUES
)
STAGE28_6_CANDIDATE_PRICE_STATUS_VALUES: tuple[str, ...] = tuple(
    _CANDIDATE_PRICE_STATUS_VALUES
)
STAGE28_6_RUN_STOP_REASON_VALUES: tuple[str, ...] = tuple(
    _STAGE28_6_RUN_STOP_REASON_VALUES
)
STAGE28_6_FINAL_HEALTH_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_6_FINAL_HEALTH_STATUS_VALUES
)
STAGE28_6_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_6_REDACTION_STATUS_VALUES
)
STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES: tuple[str, ...] = tuple(
    _STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES
)


# ---------------------------------------------------------------------------
# Field-name inventories re-exported
# ---------------------------------------------------------------------------


STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES: tuple[str, ...] = tuple(
    _STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES
)
STAGE28_6_RUN_SUMMARY_FIELD_NAMES: tuple[str, ...] = tuple(
    _STAGE28_6_RUN_SUMMARY_FIELD_NAMES
)


# ---------------------------------------------------------------------------
# Stage 28.6 scope locks
# ---------------------------------------------------------------------------


STAGE28_6_SCOPE_LOCKS: tuple[str, ...] = (
    "bounded-private-session-runner-only scope",
    "fake / injected dependencies only",
    "no real provider connection",
    "no real Discord send",
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
    "no live smoke",
    "no stage-28 closure",
    "no sleep / no scheduling / no backoff execution",
    "bounded immediate retry attempts only",
    "redaction-safe records",
    "explicit caller-supplied paths only",
)


__all__ = (
    "STAGE28_6_MINOR_VERSION",
    "STAGE28_6_SCHEMA_VERSION",
    "STAGE28_6_PRODUCTION_PY_BASENAMES",
    "STAGE28_6_TEST_BASENAMES",
    "STAGE28_6_CANDIDATE_PAIR_STATUS_VALUES",
    "STAGE28_6_CANDIDATE_PRICE_STATUS_VALUES",
    "STAGE28_6_RUN_STOP_REASON_VALUES",
    "STAGE28_6_FINAL_HEALTH_STATUS_VALUES",
    "STAGE28_6_REDACTION_STATUS_VALUES",
    "STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES",
    "STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES",
    "STAGE28_6_RUN_SUMMARY_FIELD_NAMES",
    "STAGE28_6_SCOPE_LOCKS",
)
