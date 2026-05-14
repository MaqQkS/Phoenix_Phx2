"""Stage 16B owns this one table. Migration is not auto-applied; observer fails M01 if table is missing."""

from __future__ import annotations

# Single source of truth for Stage 16B DDL lives in PHX2.db.migrations, which
# is where every other stage's CREATE TABLE / index DDL is kept (the
# canonical convention identified in STEP 0 V3). This module re-exports
# the Stage 16B-relevant symbols so the Stage 16B package and its tests
# can reference them through a Stage 16B-owned import surface without
# duplicating SQL between two files.

from PHX2.db.migrations import (
    EXPECTED_STAGE_16B_COLUMNS,
    EXPECTED_STAGE_16B_FOREIGN_KEY,
    EXPECTED_STAGE_16B_INDEXES,
    EXPECTED_STAGE_16B_UNIQUE_COLUMNS,
    STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL,
    STAGE_16B_VERSION,
    Stage16BMigrationError,
    apply_stage16b_observe_only_policy_evaluations,
    apply_stage16b_schema,
)

__all__ = [
    "EXPECTED_STAGE_16B_COLUMNS",
    "EXPECTED_STAGE_16B_FOREIGN_KEY",
    "EXPECTED_STAGE_16B_INDEXES",
    "EXPECTED_STAGE_16B_UNIQUE_COLUMNS",
    "STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL",
    "STAGE_16B_VERSION",
    "Stage16BMigrationError",
    "apply_stage16b_observe_only_policy_evaluations",
    "apply_stage16b_schema",
]
