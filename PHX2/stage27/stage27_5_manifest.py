"""Stage 27.5 private-ping renderer / provenance manifest.

Stage 27.5 is a pure / deterministic rendering + provenance layer
with no runner, no continuous artifact stream, no live network
surface, no Discord client, no dedupe. This manifest module ships
only the locked Stage 27.5 schema axes and source-file basename
inventories that downstream substages (27.6..27.8) can pin against
without re-deriving them from the model layer.

Exposed surface:

  * ``STAGE27_5_MINOR_VERSION``               -- ``"27.5"`` (re-
                                                 exported from the
                                                 ping model layer for a
                                                 stable handle).
  * ``STAGE27_5_PING_SCHEMA_VERSION``         -- locked Stage 27.5
                                                 private-ping schema
                                                 version.
  * ``STAGE27_5_PROVENANCE_SCHEMA_VERSION``   -- locked Stage 27.5
                                                 provenance-artifact
                                                 schema version.
  * ``STAGE27_5_PRODUCTION_BASENAMES``        -- locked Stage 27.5
                                                 production source
                                                 file basename set.
  * ``STAGE27_5_TEST_BASENAMES``              -- locked Stage 27.5
                                                 test file basename
                                                 set.

This module imports only stdlib (``typing``) plus Stage 27.5
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.private_ping_models import (
    STAGE27_5_MINOR_VERSION as _STAGE27_5_MINOR_VERSION,
    STAGE27_5_PING_SCHEMA_VERSION as _STAGE27_5_PING_SCHEMA_VERSION,
    STAGE27_5_PROVENANCE_SCHEMA_VERSION as _STAGE27_5_PROVENANCE_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE27_5_MINOR_VERSION: str = _STAGE27_5_MINOR_VERSION
STAGE27_5_PING_SCHEMA_VERSION: str = _STAGE27_5_PING_SCHEMA_VERSION
STAGE27_5_PROVENANCE_SCHEMA_VERSION: str = (
    _STAGE27_5_PROVENANCE_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Locked Stage 27.5 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_5_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "private_ping_models.py",
    "private_ping_renderer.py",
    "private_ping_provenance.py",
    "private_ping_artifact_writer.py",
    "stage27_5_manifest.py",
)


STAGE27_5_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_5_private_ping_models.py",
    "test_stage_27_5_private_ping_renderer.py",
    "test_stage_27_5_private_ping_provenance.py",
    "test_stage_27_5_private_ping_artifact_writer.py",
    "test_stage_27_5_boundaries.py",
)
