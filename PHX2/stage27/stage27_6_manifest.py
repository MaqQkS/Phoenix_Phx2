"""Stage 27.6 bounded dry-run candidate / runner manifest.

Stage 27.6 ships the bounded dry-run candidate assembler + runner +
run-local dedupe surface; no Discord transport, no real provider /
RPC connection, no persistent dedupe ledger, no Stage 26 candidate
policy enforcement, no public routing, no X / social. This manifest
module ships only the locked Stage 27.6 schema axes and source-file
basename inventories that downstream substages (27.7..27.8) can pin
against without re-deriving them from the model layer.

Exposed surface:

  * ``STAGE27_6_MINOR_VERSION``                  -- ``"27.6"``.
  * ``STAGE27_6_CANDIDATE_SCHEMA_VERSION``       -- locked Stage 27.6
                                                    live-candidate
                                                    schema version.
  * ``STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION``     -- locked Stage 27.6
                                                    run-summary
                                                    schema version.
  * ``STAGE27_6_DEDUPE_SCHEMA_VERSION``          -- locked Stage 27.6
                                                    run-local dedupe
                                                    schema version.
  * ``STAGE27_6_PRODUCTION_BASENAMES``           -- locked Stage 27.6
                                                    production source
                                                    file basename set.
  * ``STAGE27_6_TEST_BASENAMES``                 -- locked Stage 27.6
                                                    test file basename
                                                    set.

This module imports only stdlib (``typing``) plus Stage 27.6
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.bounded_tradeable_ping_runner import (
    STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION as _STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
)
from PHX2.stage27.live_candidate_assembler import (
    STAGE27_6_CANDIDATE_SCHEMA_VERSION as _STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    STAGE27_6_MINOR_VERSION as _STAGE27_6_MINOR_VERSION,
)
from PHX2.stage27.live_dedupe import (
    STAGE27_6_DEDUPE_SCHEMA_VERSION as _STAGE27_6_DEDUPE_SCHEMA_VERSION,
)


STAGE27_6_MINOR_VERSION: str = _STAGE27_6_MINOR_VERSION
STAGE27_6_CANDIDATE_SCHEMA_VERSION: str = (
    _STAGE27_6_CANDIDATE_SCHEMA_VERSION
)
STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION: str = (
    _STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION
)
STAGE27_6_DEDUPE_SCHEMA_VERSION: str = (
    _STAGE27_6_DEDUPE_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Locked Stage 27.6 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_6_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "live_dedupe.py",
    "live_candidate_assembler.py",
    "bounded_tradeable_ping_runner.py",
    "stage27_6_manifest.py",
)


STAGE27_6_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_6_live_dedupe.py",
    "test_stage_27_6_live_candidate_assembler.py",
    "test_stage_27_6_bounded_tradeable_ping_runner.py",
    "test_stage_27_6_boundaries.py",
)
