"""Stage 27.4 measurement-context manifest constants.

Stage 27.4 is a pure / deterministic context-attachment layer with
no runner, no artifact writer, no JSON manifest serialization, and
no live network surface. This manifest module ships only the
locked Stage 27.4 schema axes and source-file basename inventories
that downstream substages (27.5..27.8) can pin against without
re-deriving them from the model layer.

Exposed surface:

  * ``STAGE27_4_MINOR_VERSION``               -- ``"27.4"`` (re-
                                                 exported from the
                                                 price/ATH model
                                                 layer for a stable
                                                 handle).
  * ``STAGE27_4_PRICE_ATH_SCHEMA_VERSION``    -- locked Stage 27.4
                                                 price/ATH schema
                                                 version.
  * ``STAGE27_4_MIGRATION_SCHEMA_VERSION``    -- locked Stage 27.4
                                                 migration schema
                                                 version.
  * ``STAGE27_4_MEASUREMENT_SCHEMA_VERSION``  -- locked Stage 27.4
                                                 combined measurement
                                                 schema version.
  * ``STAGE27_4_PRODUCTION_BASENAMES``        -- locked Stage 27.4
                                                 production source
                                                 file basename set.
  * ``STAGE27_4_TEST_BASENAMES``              -- locked Stage 27.4
                                                 test file basename
                                                 set.

This module imports only stdlib (``typing``) plus Stage 27.4
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.live_measurement_context import (
    STAGE27_4_MEASUREMENT_SCHEMA_VERSION as _STAGE27_4_MEASUREMENT_SCHEMA_VERSION,
)
from PHX2.stage27.migration_context_models import (
    STAGE27_4_MIGRATION_SCHEMA_VERSION as _STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.price_ath_context_models import (
    STAGE27_4_MINOR_VERSION as _STAGE27_4_MINOR_VERSION,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION as _STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
)


# Re-export for downstream pin sites.
STAGE27_4_MINOR_VERSION: str = _STAGE27_4_MINOR_VERSION
STAGE27_4_PRICE_ATH_SCHEMA_VERSION: str = (
    _STAGE27_4_PRICE_ATH_SCHEMA_VERSION
)
STAGE27_4_MIGRATION_SCHEMA_VERSION: str = (
    _STAGE27_4_MIGRATION_SCHEMA_VERSION
)
STAGE27_4_MEASUREMENT_SCHEMA_VERSION: str = (
    _STAGE27_4_MEASUREMENT_SCHEMA_VERSION
)


# ---------------------------------------------------------------------------
# Locked Stage 27.4 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_4_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "price_ath_context_models.py",
    "price_ath_context_contracts.py",
    "price_ath_context_reader.py",
    "migration_context_models.py",
    "live_measurement_context.py",
    "stage27_4_manifest.py",
)


STAGE27_4_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_4_price_ath_context_models.py",
    "test_stage_27_4_price_ath_context_reader.py",
    "test_stage_27_4_live_measurement_context.py",
    "test_stage_27_4_boundaries.py",
)
