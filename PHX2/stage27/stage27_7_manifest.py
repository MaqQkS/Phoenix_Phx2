"""Stage 27.7a operator runbook + dry-run smoke harness manifest.

Stage 27.7a is a docs + deterministic dry-run smoke harness pass.
No Discord transport, no real provider / RPC connection, no
persistent dedupe ledger, no Stage 26 candidate policy
enforcement, no public routing, no X / social. This manifest
module ships only the locked Stage 27.7a schema axes and source-
file basename inventories that downstream substages
(27.7b / 27.8) can pin against without re-deriving them from the
harness layer.

Exposed surface:

  * ``STAGE27_7A_MINOR_VERSION``                       -- ``"27.7a"``.
  * ``STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION``        -- locked
                                                          Stage 27.7a
                                                          dry-run smoke
                                                          summary schema
                                                          version.
  * ``STAGE27_7A_PRODUCTION_BASENAMES``                -- locked
                                                          Stage 27.7a
                                                          production
                                                          source +
                                                          markdown
                                                          basename set.
  * ``STAGE27_7A_PRODUCTION_PY_BASENAMES``             -- locked
                                                          Stage 27.7a
                                                          production .py
                                                          basename set.
  * ``STAGE27_7A_PRODUCTION_MD_BASENAMES``             -- locked
                                                          Stage 27.7a
                                                          production .md
                                                          basename set.
  * ``STAGE27_7A_TEST_BASENAMES``                      -- locked
                                                          Stage 27.7a
                                                          test file
                                                          basename set.

This module imports only stdlib (``typing``) plus Stage 27.7a
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.dry_run_smoke_harness import (
    STAGE27_7A_MINOR_VERSION as _STAGE27_7A_MINOR_VERSION,
    STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION as _STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE27_7A_MINOR_VERSION: str = _STAGE27_7A_MINOR_VERSION
STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION: str = (
    _STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Locked Stage 27.7a source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_7A_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "dry_run_smoke_harness.py",
    "stage27_7_manifest.py",
)


STAGE27_7A_PRODUCTION_MD_BASENAMES: tuple[str, ...] = (
    "STAGE_27_OPERATOR_RUNBOOK.md",
    "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
)


STAGE27_7A_PRODUCTION_BASENAMES: tuple[str, ...] = (
    STAGE27_7A_PRODUCTION_PY_BASENAMES
    + STAGE27_7A_PRODUCTION_MD_BASENAMES
)


STAGE27_7A_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_7_dry_run_smoke_harness.py",
    "test_stage_27_7_operator_runbook.py",
    "test_stage_27_7_boundaries.py",
)
