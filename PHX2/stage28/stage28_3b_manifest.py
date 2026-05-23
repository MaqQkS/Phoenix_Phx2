"""Stage 28.3b retry-policy manifest.

Stage 28.3b is the retry-policy substage of Stage 28. It introduces
pure, deterministic, redaction-safe closed-set primitives that
consume Stage 28.3a failure-classification outputs and produce
bounded retry decisions for future Stage 28 runner / transport
substages.

Stage 28.3b ships NO audited Discord HTTP transport, NO heartbeat /
health snapshot, NO CLI status line, NO bounded private session
runner, NO longer-session smoke harness, NO live smoke, NO Stage
29 enforcement, NO X / social, NO Telegram, NO public routing, NO
subscriber routing, NO paid tier routing, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO dashboard / HTTP control server, and NO
daemon / systemd / watchdog / autorestart service. Stage 28.3b
reads NO process environment variables; every policy input is a
caller-supplied closed-set Stage 28.3a classification record plus
caller-supplied bounded attempt / budget counters.

Stage 28.3b never sleeps, never schedules, never queues, never
spawns threads / async tasks / subprocesses; the decision record
is the only output the policy emits, and a future Stage 28
substage owns the retry executor that will consume those
decisions.

This manifest module exposes the locked Stage 28.3b schema axes
and source-file basename inventories so downstream substages
(28.4+) can pin against them without re-deriving them from the
models / policy layers.

Exposed surface:

  * ``STAGE28_3B_MINOR_VERSION``                -- ``"28.3b"``.
  * ``STAGE28_3B_SCHEMA_VERSION``               -- locked Stage
                                                   28.3b retry-
                                                   policy schema
                                                   version.
  * ``STAGE28_3B_PRODUCTION_PY_BASENAMES``      -- locked Stage
                                                   28.3b production
                                                   .py basename set.
  * ``STAGE28_3B_TEST_BASENAMES``               -- locked Stage
                                                   28.3b test file
                                                   basename set.
  * ``STAGE28_3B_SCOPE_LOCKS``                  -- closed-set
                                                   tuple of Stage
                                                   28.3b scope
                                                   locks.
  * ``STAGE28_3B_RETRY_OUTCOME_VALUES``         -- closed-set
                                                   tuple of Stage
                                                   28.3b retry-
                                                   outcome values.
  * ``STAGE28_3B_RETRY_PROFILE_NAME_VALUES``    -- closed-set
                                                   tuple of Stage
                                                   28.3b retry-
                                                   profile-name
                                                   values.
  * ``STAGE28_3B_TERMINAL_REASON_VALUES``       -- closed-set
                                                   tuple of Stage
                                                   28.3b terminal-
                                                   reason values.
  * ``STAGE28_3B_SAFE_RETRY_REASON_CODE_VALUES`` -- closed-set
                                                    tuple of Stage
                                                    28.3b safe
                                                    retry-reason
                                                    code values.
  * ``STAGE28_3B_RETRY_AFTER_MAX_SECONDS``      -- locked numeric
                                                   retry-after cap.

This module imports only stdlib (``typing``) plus the Stage 28.3b
production models module. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 / 28.2 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.retry_policy_models import (
    RETRY_AFTER_DEFAULT_SECONDS as _RETRY_AFTER_DEFAULT_SECONDS,
    RETRY_AFTER_MAX_SECONDS as _RETRY_AFTER_MAX_SECONDS,
    RETRY_AFTER_MIN_SECONDS as _RETRY_AFTER_MIN_SECONDS,
    RETRY_OUTCOME_VALUES as _RETRY_OUTCOME_VALUES,
    RETRY_PROFILE_NAME_VALUES as _RETRY_PROFILE_NAME_VALUES,
    SAFE_RETRY_REASON_CODE_VALUES as _SAFE_RETRY_REASON_CODE_VALUES,
    STAGE28_3B_MINOR_VERSION as _STAGE28_3B_MINOR_VERSION,
    STAGE28_3B_OPERATOR_VISIBILITY_VALUES as _STAGE28_3B_OPERATOR_VISIBILITY_VALUES,
    STAGE28_3B_REDACTION_STATUS_VALUES as _STAGE28_3B_REDACTION_STATUS_VALUES,
    STAGE28_3B_SCHEMA_VERSION as _STAGE28_3B_SCHEMA_VERSION,
    STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES as _STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES,
    TERMINAL_REASON_VALUES as _TERMINAL_REASON_VALUES,
)


# Re-export for downstream pin sites.
STAGE28_3B_MINOR_VERSION: str = _STAGE28_3B_MINOR_VERSION
STAGE28_3B_SCHEMA_VERSION: str = _STAGE28_3B_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.3b source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_3B_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "retry_policy_models.py",
    "retry_policy.py",
    "stage28_3b_manifest.py",
)


STAGE28_3B_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_3b_retry_policy_models.py",
    "test_stage_28_3b_retry_policy.py",
    "test_stage_28_3b_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_3B_RETRY_OUTCOME_VALUES: tuple[str, ...] = tuple(
    _RETRY_OUTCOME_VALUES
)


STAGE28_3B_RETRY_PROFILE_NAME_VALUES: tuple[str, ...] = tuple(
    _RETRY_PROFILE_NAME_VALUES
)


STAGE28_3B_TERMINAL_REASON_VALUES: tuple[str, ...] = tuple(
    _TERMINAL_REASON_VALUES
)


STAGE28_3B_SAFE_RETRY_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    _SAFE_RETRY_REASON_CODE_VALUES
)


STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES
)


STAGE28_3B_OPERATOR_VISIBILITY_VALUES: tuple[str, ...] = tuple(
    _STAGE28_3B_OPERATOR_VISIBILITY_VALUES
)


STAGE28_3B_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_3B_REDACTION_STATUS_VALUES
)


# ---------------------------------------------------------------------------
# Retry-after caps re-exported
# ---------------------------------------------------------------------------


STAGE28_3B_RETRY_AFTER_MAX_SECONDS: float = _RETRY_AFTER_MAX_SECONDS
STAGE28_3B_RETRY_AFTER_MIN_SECONDS: float = _RETRY_AFTER_MIN_SECONDS
STAGE28_3B_RETRY_AFTER_DEFAULT_SECONDS: float = (
    _RETRY_AFTER_DEFAULT_SECONDS
)


# ---------------------------------------------------------------------------
# Stage 28.3b scope locks
# ---------------------------------------------------------------------------


# Stage 28.3b is retry-policy only. The following locks are
# declared here so a downstream audit can pin them without re-
# reading the entire substage:
STAGE28_3B_SCOPE_LOCKS: tuple[str, ...] = (
    "retry-policy-only scope",
    "no env reads",
    "no network calls",
    "no HTTP",
    "no gRPC",
    "no Discord dispatch",
    "no provider connection",
    "no retry execution",
    "no sleep / no scheduling / no backoff execution",
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
    "STAGE28_3B_MINOR_VERSION",
    "STAGE28_3B_SCHEMA_VERSION",
    "STAGE28_3B_PRODUCTION_PY_BASENAMES",
    "STAGE28_3B_TEST_BASENAMES",
    "STAGE28_3B_RETRY_OUTCOME_VALUES",
    "STAGE28_3B_RETRY_PROFILE_NAME_VALUES",
    "STAGE28_3B_TERMINAL_REASON_VALUES",
    "STAGE28_3B_SAFE_RETRY_REASON_CODE_VALUES",
    "STAGE28_3B_SESSION_CONTINUATION_STATUS_VALUES",
    "STAGE28_3B_OPERATOR_VISIBILITY_VALUES",
    "STAGE28_3B_REDACTION_STATUS_VALUES",
    "STAGE28_3B_RETRY_AFTER_MAX_SECONDS",
    "STAGE28_3B_RETRY_AFTER_MIN_SECONDS",
    "STAGE28_3B_RETRY_AFTER_DEFAULT_SECONDS",
    "STAGE28_3B_SCOPE_LOCKS",
)
