"""Stage 28.7 longer-session smoke harness manifest.

Stage 28.7 is the longer-session smoke / controlled live smoke
runbook substage of Stage 28. It composes the Stage 28.1 / 28.2
/ 28.3a / 28.3b / 28.4 / 28.5 / 28.6 reliability primitives in an
offline smoke harness, plus ships two operator docs (the longer-
session smoke checklist + the controlled live smoke runbook).
Stage 28.7 ships NO live smoke callable in production code, NO
real Discord send, NO real provider connection, NO Stage 28
closure, NO Stage 29 enforcement, NO public routing, NO
subscriber routing, NO paid tier routing, NO X / social, NO
Telegram, NO automated trading, NO wallet / private-key / signer
logic, NO position sizing, NO trade execution, NO dashboard / HTTP
control server, NO daemon / systemd / watchdog / autorestart
service. Stage 28.7 reads NO process environment variables;
every dependency is a caller-injected primitive.

Stage 28.8 (not yet implemented) is the closure audit + Stage 29
handoff substage. Stage 28.7 does NOT create the
``stage-28-closed`` tag, does NOT ship the Stage 28 closure audit
doc, does NOT ship the Stage 29 handoff doc, and does NOT ship a
Stage 28-wide manifest (``stage28_manifest.py``).

This manifest module exposes the locked Stage 28.7 schema axes
and source-file / doc / test basename inventories so downstream
substages (28.8+) can pin against them without re-deriving them
from the harness / doc layers.

Exposed surface:

  * ``STAGE28_7_MINOR_VERSION``                  -- ``"28.7"``.
  * ``STAGE28_7_SCHEMA_VERSION``                 -- locked Stage
                                                    28.7 smoke
                                                    summary
                                                    schema
                                                    version.
  * ``STAGE28_7_PRODUCTION_PY_BASENAMES``        -- locked Stage
                                                    28.7
                                                    production
                                                    .py basename
                                                    inventory.
  * ``STAGE28_7_DOC_BASENAMES``                  -- locked Stage
                                                    28.7 operator
                                                    doc basename
                                                    inventory.
  * ``STAGE28_7_TEST_BASENAMES``                 -- locked Stage
                                                    28.7 test
                                                    file basename
                                                    inventory.
  * ``STAGE28_7_ARTIFACT_BASENAMES``             -- locked Stage
                                                    28.7 smoke
                                                    artifact
                                                    basename
                                                    inventory.
  * ``STAGE28_7_SCOPE_LOCKS``                    -- closed-set
                                                    tuple of
                                                    Stage 28.7
                                                    scope locks.
  * ``STAGE28_7_SMOKE_STATUS_VALUES``            -- closed-set
                                                    tuple of
                                                    Stage 28.7
                                                    smoke-status
                                                    tokens.
  * ``STAGE28_7_REDACTION_STATUS_VALUES``        -- closed-set
                                                    tuple of
                                                    Stage 28.7
                                                    redaction-
                                                    status tokens.
  * ``STAGE28_7_SAFE_REASON_CODE_VALUES``        -- closed-set
                                                    tuple of
                                                    Stage 28.7
                                                    smoke-safe-
                                                    reason tokens.
  * ``STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES``      -- canonical
                                                    Stage 28.7
                                                    smoke-summary
                                                    field-name
                                                    inventory.
  * ``STAGE28_7_REDACTION_SCAN_FIELD_NAMES``     -- canonical
                                                    Stage 28.7
                                                    redaction-
                                                    scan field-
                                                    name
                                                    inventory.
  * ``STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS``  -- locked Stage
                                                    28.7
                                                    forbidden
                                                    artifact
                                                    substring
                                                    vocabulary
                                                    (the
                                                    redaction-scan
                                                    denylist).

This module imports only stdlib (``typing``) plus the Stage 28.7
smoke harness module. It does NOT import Stage 21-27 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.longer_session_smoke_harness import (
    STAGE28_7_ARTIFACT_BASENAMES as _STAGE28_7_ARTIFACT_BASENAMES,
    STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS as _STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS,
    STAGE28_7_MINOR_VERSION as _STAGE28_7_MINOR_VERSION,
    STAGE28_7_REDACTION_SCAN_FIELD_NAMES as _STAGE28_7_REDACTION_SCAN_FIELD_NAMES,
    STAGE28_7_SCHEMA_VERSION as _STAGE28_7_SCHEMA_VERSION,
    STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES as _STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES,
    SMOKE_REDACTION_STATUS_VALUES as _SMOKE_REDACTION_STATUS_VALUES,
    SMOKE_SAFE_REASON_CODE_VALUES as _SMOKE_SAFE_REASON_CODE_VALUES,
    SMOKE_STATUS_VALUES as _SMOKE_STATUS_VALUES,
)


# Re-export for downstream pin sites.
STAGE28_7_MINOR_VERSION: str = _STAGE28_7_MINOR_VERSION
STAGE28_7_SCHEMA_VERSION: str = _STAGE28_7_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 28.7 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_7_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "longer_session_smoke_harness.py",
    "stage28_7_manifest.py",
)


STAGE28_7_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
    "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
)


STAGE28_7_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_7_longer_session_smoke_harness.py",
    "test_stage_28_7_boundaries.py",
    "test_stage_28_7_smoke_docs.py",
)


STAGE28_7_ARTIFACT_BASENAMES: tuple[str, ...] = tuple(
    _STAGE28_7_ARTIFACT_BASENAMES
)


# ---------------------------------------------------------------------------
# Closed-set vocabularies re-exported for downstream pinning
# ---------------------------------------------------------------------------


STAGE28_7_SMOKE_STATUS_VALUES: tuple[str, ...] = tuple(
    _SMOKE_STATUS_VALUES
)
STAGE28_7_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _SMOKE_REDACTION_STATUS_VALUES
)
STAGE28_7_SAFE_REASON_CODE_VALUES: tuple[str, ...] = tuple(
    _SMOKE_SAFE_REASON_CODE_VALUES
)


# ---------------------------------------------------------------------------
# Field-name inventories re-exported
# ---------------------------------------------------------------------------


STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES: tuple[str, ...] = tuple(
    _STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES
)
STAGE28_7_REDACTION_SCAN_FIELD_NAMES: tuple[str, ...] = tuple(
    _STAGE28_7_REDACTION_SCAN_FIELD_NAMES
)


# ---------------------------------------------------------------------------
# Forbidden-artifact-substring vocabulary
# ---------------------------------------------------------------------------


STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS: tuple[str, ...] = tuple(
    _STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS
)


# ---------------------------------------------------------------------------
# Stage 28.7 scope locks
# ---------------------------------------------------------------------------


STAGE28_7_SCOPE_LOCKS: tuple[str, ...] = (
    "longer-session smoke harness scope",
    "controlled live smoke runbook scope",
    "offline smoke harness only in production code",
    "fake / injected transport only",
    "synthetic candidate events only",
    "explicit caller-supplied output directory",
    "no real provider connection",
    "no real Discord send in tests",
    "no real live send in tests",
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
    "no Stage 28 closure",
    "no stage-28-closed tag",
    "no Stage 28-wide manifest",
    "no Stage 28 closure audit doc",
    "no Stage 29 handoff doc",
    "no sleep / no scheduling / no backoff execution",
    "redaction-safe artifacts",
    "explicit operator authorization required for controlled live smoke",
)


__all__ = (
    "STAGE28_7_MINOR_VERSION",
    "STAGE28_7_SCHEMA_VERSION",
    "STAGE28_7_PRODUCTION_PY_BASENAMES",
    "STAGE28_7_DOC_BASENAMES",
    "STAGE28_7_TEST_BASENAMES",
    "STAGE28_7_ARTIFACT_BASENAMES",
    "STAGE28_7_SMOKE_STATUS_VALUES",
    "STAGE28_7_REDACTION_STATUS_VALUES",
    "STAGE28_7_SAFE_REASON_CODE_VALUES",
    "STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES",
    "STAGE28_7_REDACTION_SCAN_FIELD_NAMES",
    "STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS",
    "STAGE28_7_SCOPE_LOCKS",
)
