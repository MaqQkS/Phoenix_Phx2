"""Stage 28.3a failure-classification manifest.

Stage 28.3a is the failure-classification substage of Stage 28.
It introduces pure, deterministic, redaction-safe closed-set
primitives that map an opaque failure description into a stable
``Stage28_3aFailureClassification`` record over the locked Stage
28.3a closed-set vocabularies (failure kinds, domains, recommended
actions, severities, dispatch-safety status, session-continuation
status, operator-visibility, safe reason codes, redaction status).

Stage 28.3a ships NO retry / backoff policy, NO audited Discord
HTTP transport, NO heartbeat / health snapshot, NO CLI status
line, NO bounded private session runner, NO longer-session smoke
harness, NO live smoke, NO Stage 29 enforcement, NO X / social,
NO Telegram, NO public routing, NO subscriber routing, NO paid
tier routing, NO automated trading, NO wallet / private-key /
signer logic, NO position sizing, NO trade execution, NO
dashboard / HTTP control server, and NO daemon / systemd /
watchdog / autorestart service. Stage 28.3a reads NO process
environment variables; all classifier inputs are caller-supplied
closed-set hints.

This manifest module exposes the locked Stage 28.3a schema axes
and source-file basename inventories so downstream substages
(28.3b+) can pin against them without re-deriving them from the
models / classifier layers.

Exposed surface:

  * ``STAGE28_3A_MINOR_VERSION``           -- ``"28.3a"``.
  * ``STAGE28_3A_SCHEMA_VERSION``          -- locked Stage 28.3a
                                              failure-classification
                                              schema version.
  * ``STAGE28_3A_PRODUCTION_PY_BASENAMES`` -- locked Stage 28.3a
                                              production .py
                                              basename set.
  * ``STAGE28_3A_TEST_BASENAMES``          -- locked Stage 28.3a
                                              test file basename
                                              set.
  * ``STAGE28_3A_SCOPE_LOCKS``             -- closed-set tuple of
                                              Stage 28.3a scope
                                              locks (classification-
                                              only; no env, no
                                              network, no dispatch,
                                              no retry policy, no
                                              transport, no health,
                                              no runner, no live
                                              smoke, no enforcement,
                                              no public routing, no
                                              X / social, no
                                              Telegram, no automated
                                              trading, no wallet /
                                              private-key logic).
  * ``STAGE28_3A_FAILURE_KIND_VALUES``     -- the closed-set tuple
                                              of Stage 28.3a
                                              failure-kind values
                                              (re-exported from the
                                              models layer for pin
                                              sites).
  * ``STAGE28_3A_DOMAIN_VALUES``           -- the closed-set tuple
                                              of Stage 28.3a
                                              failure-domain values.
  * ``STAGE28_3A_RECOMMENDED_ACTION_VALUES`` -- the closed-set
                                                tuple of Stage 28.3a
                                                recommended-action
                                                values.
  * ``STAGE28_3A_SEVERITY_VALUES``         -- the closed-set tuple
                                              of Stage 28.3a
                                              severity values.
  * ``STAGE28_3A_DISPATCH_SAFETY_STATUS_VALUES`` -- the closed-set
                                                    tuple of Stage
                                                    28.3a dispatch-
                                                    safety-status
                                                    values.
  * ``STAGE28_3A_SESSION_CONTINUATION_STATUS_VALUES`` -- the closed-
                                                          set tuple
                                                          of Stage
                                                          28.3a
                                                          session-
                                                          continuation-
                                                          status
                                                          values.
  * ``STAGE28_3A_OPERATOR_VISIBILITY_VALUES`` -- the closed-set
                                                  tuple of Stage
                                                  28.3a operator-
                                                  visibility values.
  * ``STAGE28_3A_REDACTION_STATUS_VALUES``   -- the closed-set
                                                  tuple of Stage
                                                  28.3a redaction-
                                                  status values.
  * ``STAGE28_3A_SAFE_REASON_CODE_VALUES``   -- the closed-set
                                                  tuple of Stage
                                                  28.3a safe-reason-
                                                  code values.

This module imports only stdlib (``typing``) plus the Stage 28.3a
production models module. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 / 28.2 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.failure_classification_models import (
    DISPATCH_SAFETY_STATUS_VALUES as _DISPATCH_SAFETY_STATUS_VALUES,
    DOMAIN_VALUES as _DOMAIN_VALUES,
    FAILURE_KIND_VALUES as _FAILURE_KIND_VALUES,
    OPERATOR_VISIBILITY_VALUES as _OPERATOR_VISIBILITY_VALUES,
    RECOMMENDED_ACTION_VALUES as _RECOMMENDED_ACTION_VALUES,
    REDACTION_STATUS_VALUES as _REDACTION_STATUS_VALUES,
    SAFE_REASON_CODE_VALUES as _SAFE_REASON_CODE_VALUES,
    SESSION_CONTINUATION_STATUS_VALUES as _SESSION_CONTINUATION_STATUS_VALUES,
    SEVERITY_VALUES as _SEVERITY_VALUES,
    STAGE28_3A_MINOR_VERSION as _STAGE28_3A_MINOR_VERSION,
    STAGE28_3A_SCHEMA_VERSION as _STAGE28_3A_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE28_3A_MINOR_VERSION: str = _STAGE28_3A_MINOR_VERSION
STAGE28_3A_SCHEMA_VERSION: str = _STAGE28_3A_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.3a source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_3A_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "failure_classification_models.py",
    "failure_classification.py",
    "stage28_3a_manifest.py",
)


STAGE28_3A_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_3a_failure_classification_models.py",
    "test_stage_28_3a_failure_classification.py",
    "test_stage_28_3a_boundaries.py",
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_3A_FAILURE_KIND_VALUES: tuple[str, ...] = tuple(
    _FAILURE_KIND_VALUES
)


STAGE28_3A_DOMAIN_VALUES: tuple[str, ...] = tuple(_DOMAIN_VALUES)


STAGE28_3A_RECOMMENDED_ACTION_VALUES: tuple[str, ...] = tuple(
    _RECOMMENDED_ACTION_VALUES
)


STAGE28_3A_SEVERITY_VALUES: tuple[str, ...] = tuple(_SEVERITY_VALUES)


STAGE28_3A_DISPATCH_SAFETY_STATUS_VALUES: tuple[str, ...] = tuple(
    _DISPATCH_SAFETY_STATUS_VALUES
)


STAGE28_3A_SESSION_CONTINUATION_STATUS_VALUES: tuple[str, ...] = tuple(
    _SESSION_CONTINUATION_STATUS_VALUES
)


STAGE28_3A_OPERATOR_VISIBILITY_VALUES: tuple[str, ...] = tuple(
    _OPERATOR_VISIBILITY_VALUES
)


STAGE28_3A_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _REDACTION_STATUS_VALUES
)


STAGE28_3A_SAFE_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    _SAFE_REASON_CODE_VALUES
)


# ---------------------------------------------------------------------------
# Stage 28.3a scope locks
# ---------------------------------------------------------------------------


# Stage 28.3a is failure-classification only. The following locks
# are declared here so a downstream audit can pin them without
# re-reading the entire substage:
STAGE28_3A_SCOPE_LOCKS: tuple[str, ...] = (
    "classification-only scope",
    "no env reads",
    "no network calls",
    "no HTTP",
    "no gRPC",
    "no Discord dispatch",
    "no provider connection",
    "no retry / backoff",
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
    "STAGE28_3A_MINOR_VERSION",
    "STAGE28_3A_SCHEMA_VERSION",
    "STAGE28_3A_PRODUCTION_PY_BASENAMES",
    "STAGE28_3A_TEST_BASENAMES",
    "STAGE28_3A_FAILURE_KIND_VALUES",
    "STAGE28_3A_DOMAIN_VALUES",
    "STAGE28_3A_RECOMMENDED_ACTION_VALUES",
    "STAGE28_3A_SEVERITY_VALUES",
    "STAGE28_3A_DISPATCH_SAFETY_STATUS_VALUES",
    "STAGE28_3A_SESSION_CONTINUATION_STATUS_VALUES",
    "STAGE28_3A_OPERATOR_VISIBILITY_VALUES",
    "STAGE28_3A_REDACTION_STATUS_VALUES",
    "STAGE28_3A_SAFE_REASON_CODE_VALUES",
    "STAGE28_3A_SCOPE_LOCKS",
)
