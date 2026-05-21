"""Stage 25 schema / vocabulary whitelist re-export surface.

Stage 26.1 production code consumes Stage 25 schema tokens through
this module. The module imports a deliberately small, locked set of
names from ``PHX2.stage25.constants`` (the canonical Stage 25
schema / vocabulary surface) and re-exports them under their original
names.

The locked whitelist policy (Stage 26.0 spec-lock §8):

  * Stage 26 production code MAY import (read-only) from
    ``PHX2.stage25.constants`` only.
  * Stage 26 production code MUST NOT import from any other
    ``PHX2.stage25`` module -- in particular, NOT from
    ``PHX2.stage25.models``, ``PHX2.stage25.errors``,
    ``PHX2.stage25.measurement_contracts``,
    ``PHX2.stage25.input_reader``, ``PHX2.stage25.summary``,
    ``PHX2.stage25.runner``, ``PHX2.stage25.artifact_writer``,
    ``PHX2.stage25.stage25_manifest``, or any per-row Stage 25 model
    module.

This module exists so the Stage 26.1 production tree has exactly
ONE import surface that touches ``PHX2.stage25`` directly; every
other Stage 26.1 production module imports Stage 25 vocabulary
through this whitelist. The Stage 26.1 boundary tests
(``test_stage_26_1_stage25_schema_whitelist.py`` and
``test_stage_26_1_boundaries.py``) pin both invariants:

  1. this module imports exactly the locked symbol set from
     ``PHX2.stage25.constants`` and nothing else from
     ``PHX2.stage25``;
  2. every other Stage 26 production module imports no
     ``PHX2.stage25`` symbol -- it consumes the Stage 25 vocabulary
     via this whitelist.

If a future Stage 26.x sub-stage needs a Stage 25 schema token not
listed here, the correct response is to extend the whitelist below
AND extend the boundary test's locked symbol set in the same
commit. The wrong response is to broaden the import to a different
Stage 25 module.
"""

from __future__ import annotations

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KINDS,
    CONFIDENCE_LEVELS,
    MEASUREMENT_FAMILIES,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_STATUSES,
    MEASUREMENT_STATUS_MEASURED,
    OBSERVE_ONLY_MODE,
    PRICE_WINDOW_KINDS,
    QUOTE_DENOMINATIONS,
    RECONCILIATION_STATUSES,
    REDACTION_CONFIRMED_TOKEN,
    REJECTION_REASONS,
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    SOURCE_FAMILIES,
    SOURCE_STATUSES,
    STAGE25_ARTIFACT_FILENAMES,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MANIFEST_SCHEMA_VERSION,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_SUMMARY_VERSION,
    STAGE25_WRITER_NAME,
    STAGE25_WRITER_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
)


# ---------------------------------------------------------------------------
# Locked symbol whitelist
# ---------------------------------------------------------------------------
#
# Tuple of every symbol the Stage 26 production tree is permitted to
# consume from ``PHX2.stage25``. The boundary test asserts the
# imported names above match this tuple exactly.


STAGE25_SCHEMA_WHITELIST_SYMBOLS: tuple[str, ...] = (
    "ATH_CANDIDATE_KINDS",
    "CONFIDENCE_LEVELS",
    "MEASUREMENT_FAMILIES",
    "MEASUREMENT_FAMILY_ATH",
    "MEASUREMENT_FAMILY_MIGRATION",
    "MEASUREMENT_STATUSES",
    "MEASUREMENT_STATUS_MEASURED",
    "OBSERVE_ONLY_MODE",
    "PRICE_WINDOW_KINDS",
    "QUOTE_DENOMINATIONS",
    "RECONCILIATION_STATUSES",
    "REDACTION_CONFIRMED_TOKEN",
    "REJECTION_REASONS",
    "SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
    "SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    "SELF_REFERENTIAL_MANIFEST_SHA256",
    "SOURCE_FAMILIES",
    "SOURCE_STATUSES",
    "STAGE25_ARTIFACT_FILENAMES",
    "STAGE25_ATH_CANDIDATES_FILENAME",
    "STAGE25_ATH_MEASUREMENTS_FILENAME",
    "STAGE25_MANIFEST_FILENAME",
    "STAGE25_MANIFEST_SCHEMA_VERSION",
    "STAGE25_MEASUREMENT_REJECTIONS_FILENAME",
    "STAGE25_MIGRATION_MEASUREMENTS_FILENAME",
    "STAGE25_MIGRATION_OBSERVATIONS_FILENAME",
    "STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME",
    "STAGE25_RUNNER_NAME",
    "STAGE25_RUNNER_VERSION",
    "STAGE25_SOURCE_RECONCILIATIONS_FILENAME",
    "STAGE25_SUMMARY_FILENAME",
    "STAGE25_SUMMARY_VERSION",
    "STAGE25_WRITER_NAME",
    "STAGE25_WRITER_VERSION",
    "STAGE_NAME",
    "STAGE_VERSION",
)


__all__ = [
    "ATH_CANDIDATE_KINDS",
    "CONFIDENCE_LEVELS",
    "MEASUREMENT_FAMILIES",
    "MEASUREMENT_FAMILY_ATH",
    "MEASUREMENT_FAMILY_MIGRATION",
    "MEASUREMENT_STATUSES",
    "MEASUREMENT_STATUS_MEASURED",
    "OBSERVE_ONLY_MODE",
    "PRICE_WINDOW_KINDS",
    "QUOTE_DENOMINATIONS",
    "RECONCILIATION_STATUSES",
    "REDACTION_CONFIRMED_TOKEN",
    "REJECTION_REASONS",
    "SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
    "SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    "SELF_REFERENTIAL_MANIFEST_SHA256",
    "SOURCE_FAMILIES",
    "SOURCE_STATUSES",
    "STAGE25_ARTIFACT_FILENAMES",
    "STAGE25_ATH_CANDIDATES_FILENAME",
    "STAGE25_ATH_MEASUREMENTS_FILENAME",
    "STAGE25_MANIFEST_FILENAME",
    "STAGE25_MANIFEST_SCHEMA_VERSION",
    "STAGE25_MEASUREMENT_REJECTIONS_FILENAME",
    "STAGE25_MIGRATION_MEASUREMENTS_FILENAME",
    "STAGE25_MIGRATION_OBSERVATIONS_FILENAME",
    "STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME",
    "STAGE25_RUNNER_NAME",
    "STAGE25_RUNNER_VERSION",
    "STAGE25_SOURCE_RECONCILIATIONS_FILENAME",
    "STAGE25_SCHEMA_WHITELIST_SYMBOLS",
    "STAGE25_SUMMARY_FILENAME",
    "STAGE25_SUMMARY_VERSION",
    "STAGE25_WRITER_NAME",
    "STAGE25_WRITER_VERSION",
    "STAGE_NAME",
    "STAGE_VERSION",
]
