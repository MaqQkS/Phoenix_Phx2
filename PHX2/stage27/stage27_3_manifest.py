"""Stage 27.3 provider-ingest composition manifest constants.

Stage 27.3 is a pure / deterministic composition layer with no
runner, no artifact writer, no JSON manifest serialization, and
no live network surface. This manifest module ships only the
locked Stage 27.3 schema axes that downstream substages
(27.4..27.8) can pin against without re-deriving them from the
model layer.

Exposed surface:

  * ``STAGE27_3_MINOR_VERSION``         -- ``"27.3"`` (re-exported
                                           from the model layer
                                           for a stable handle).
  * ``STAGE27_3_SCHEMA_VERSION``        -- the locked
                                           Stage 27.3 schema
                                           version string.
  * ``STAGE27_3_PRODUCTION_BASENAMES``  -- the locked Stage 27.3
                                           production source-file
                                           basename set.
  * ``STAGE27_3_TEST_BASENAMES``        -- the locked Stage 27.3
                                           test-file basename set.

This module imports only stdlib (``typing``) plus Stage 27.3
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.provider_ingest_models import (
    STAGE27_3_MINOR_VERSION as _STAGE27_3_MINOR_VERSION,
    STAGE27_3_SCHEMA_VERSION as _STAGE27_3_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE27_3_MINOR_VERSION: str = _STAGE27_3_MINOR_VERSION
STAGE27_3_SCHEMA_VERSION: str = _STAGE27_3_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Locked Stage 27.3 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_3_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "provider_ingest_models.py",
    "provider_ingest_contracts.py",
    "provider_event_adapter.py",
    "live_provider_composition.py",
    "stage27_3_manifest.py",
)


STAGE27_3_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_3_provider_ingest_models.py",
    "test_stage_27_3_provider_event_adapter.py",
    "test_stage_27_3_live_provider_composition.py",
    "test_stage_27_3_boundaries.py",
)
