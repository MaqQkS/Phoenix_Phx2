"""Stage 20 locked constants.

All version strings, eligibility-state taxonomy, label-to-state
mapping, error and warning code enums, and hand-duplicated
upstream Stage 18 + Stage 19 schema pins live here. The mapping
and the schema pins are intentionally module-level frozen objects
so any drift requires a STAGE20_VERSION bump.

Hand-duplicated upstream schema:

  * Stage 18 review_matrix.csv column tuple (17 cols)
    -- duplicated from PHX2/stage18/constants.py and verified
       against the same tuple as it appears in PHX2/stage19/
       constants.py STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS.
  * Stage 19 operator_review_ledger.csv column tuple (13 cols)
    -- duplicated from PHX2/stage19/constants.py LEDGER_COLUMNS.
  * Stage 19 operator_review_summary.csv column tuple (11 cols)
    -- duplicated from PHX2/stage19/constants.py SUMMARY_COLUMNS.
  * Stage 19 review-label vocabulary (6 labels)
    -- duplicated from PHX2/stage19/constants.py LABELS.
  * Stage 19 manifest hash-field key names
    -- duplicated from PHX2/stage19/manifest.py build_manifest.

The import-boundary policy forbids Stage 20 production code from
importing any of those modules; duplication is the contract.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 20 version strings
# ---------------------------------------------------------------------------


STAGE20_VERSION: str = "stage20_v0_observe_only"
# Minor version axis introduced at Stage 20.2 per operator decision
# B2-c. Both STAGE20_VERSION and STAGE20_MINOR_VERSION are mixed
# into every ID derivation (stage20_run_id, candidate_id,
# decision_id) and both are emitted on the manifest. Bumping either
# axis invalidates the cache; bumping STAGE20_VERSION is a stage
# break, bumping STAGE20_MINOR_VERSION is a within-stage iteration.
STAGE20_MINOR_VERSION: str = "20.2"
CONSUMER_CONTRACT_VERSION: str = "stage20_to_stage21_v0"
MAPPING_VERSION: str = "v0"

STALENESS_THRESHOLD_DAYS: int = 30

SAFE_FOR_LIVE_DISPATCH: bool = False


# ---------------------------------------------------------------------------
# Stage 18 schema pins
# (duplicated from PHX2/stage18/constants.py and
#  PHX2/stage18/manifest.py per the import-boundary policy)
# ---------------------------------------------------------------------------


STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION: str = "stage18_run_manifest_v0"
STAGE18_MANIFEST_FILENAME: str = "manifest.json"
STAGE18_REVIEW_MATRIX_FILENAME: str = "review_matrix.csv"

STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "window_label",
    "classification",
    "stage17_label_preserved",
    "insufficient_sample_reason",
    "data_block_reason",
    "gate_trips_all",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_with_complete_outcome",
    "delta_hit_2x_rate",
    "unevaluable_rate",
    "incomplete_outcome_ratio",
    "tier_coverage",
)


# ---------------------------------------------------------------------------
# Stage 19 schema pins
# (duplicated from PHX2/stage19/constants.py and
#  PHX2/stage19/manifest.py per the import-boundary policy)
# ---------------------------------------------------------------------------


STAGE19_EXPECTED_MANIFEST_SCHEMA_VERSION: str = "stage19_ledger_v1"
STAGE19_MANIFEST_FILENAME: str = "manifest.json"
STAGE19_LEDGER_FILENAME: str = "operator_review_ledger.csv"
STAGE19_SUMMARY_FILENAME: str = "operator_review_summary.csv"

STAGE19_LEDGER_EXPECTED_COLUMNS: tuple[str, ...] = (
    "stage19_run_id",
    "ledger_row_id",
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "review_sequence",
    "review_label",
    "review_notes",
    "review_timestamp_utc",
    "stage18_classification",
    "stage17_label_preserved",
)

STAGE19_SUMMARY_EXPECTED_COLUMNS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "current_review_sequence",
    "current_review_label",
    "current_review_notes",
    "current_review_timestamp_utc",
    "stage18_classification",
    "stage17_label_preserved",
)

STAGE19_REVIEW_LABELS: tuple[str, ...] = (
    "REVIEW_PROMISING_CONFIRMED",
    "REVIEW_HARMFUL_CONFIRMED",
    "REVIEW_REJECTED",
    "WATCHLIST",
    "NEEDS_MORE_DATA",
    "INCONCLUSIVE",
)


# Stage 19 manifest keys that carry SHA-256 hashes Stage 20 verifies
# (sourced from PHX2/stage19/manifest.py build_manifest output)
STAGE19_MANIFEST_KEY_STAGE18_MANIFEST_HASH: str = "stage18_manifest_sha256"
STAGE19_MANIFEST_KEY_STAGE18_REVIEW_MATRIX_HASH: str = "stage18_review_matrix_sha256"

# Stage 19 manifest keys Stage 20 reads for run-id provenance
STAGE19_MANIFEST_KEY_STAGE19_RUN_ID: str = "stage19_run_id"
STAGE19_MANIFEST_KEY_STAGE18_RUN_ID: str = "stage18_run_id"

# Stage 19 ledger timestamp format (per
# PHX2/stage19/readers.py _RUN_TIMESTAMP_FORMAT)
STAGE19_LEDGER_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Stage 20 preview eligibility state taxonomy (4 values, frozen)
# ---------------------------------------------------------------------------


class PreviewEligibilityState(str, Enum):
    """The four preview eligibility states Stage 20 emits.

    Ordered weakest to strongest. ``PREVIEW_ELIGIBLE`` is NOT
    dispatch authorization; ``SAFE_FOR_LIVE_DISPATCH`` is the
    only gate that grants live dispatch and is hardcoded False
    in this stage.
    """

    PREVIEW_EXCLUDED = "PREVIEW_EXCLUDED"
    PREVIEW_NEEDS_MORE_DATA = "PREVIEW_NEEDS_MORE_DATA"
    PREVIEW_OBSERVE_ONLY = "PREVIEW_OBSERVE_ONLY"
    PREVIEW_ELIGIBLE = "PREVIEW_ELIGIBLE"


# Locked v0 label-to-state mapping. Mutation requires a
# STAGE20_VERSION bump.
LABEL_TO_STATE_MAPPING_V0: Mapping[str, PreviewEligibilityState] = MappingProxyType({
    "REVIEW_PROMISING_CONFIRMED": PreviewEligibilityState.PREVIEW_ELIGIBLE,
    "WATCHLIST": PreviewEligibilityState.PREVIEW_OBSERVE_ONLY,
    "NEEDS_MORE_DATA": PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA,
    "INCONCLUSIVE": PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA,
    "REVIEW_HARMFUL_CONFIRMED": PreviewEligibilityState.PREVIEW_EXCLUDED,
    "REVIEW_REJECTED": PreviewEligibilityState.PREVIEW_EXCLUDED,
})


# ---------------------------------------------------------------------------
# E-codes (closed set; some active in 20.1, others reserved for 20.2 / 20.3)
# ---------------------------------------------------------------------------


class EligibilityErrorCode(str, Enum):
    """Closed set of Stage 20 error codes.

    20.1 active codes:  E2001, E2002, E2003, E2005, E2006, E2007,
                        E2008, E2009, E2010, E2022.
    20.1 deferred:      E2004 (no source-of-truth hash for Stage 19
                        ledger output exists; defined but inactive).
    20.2 reserved:      E2011, E2015, E2016, E2017, E2020, E2021,
                        E2023, E2024, E2025.
    20.3 reserved:      E2012, E2013, E2014.
    """

    # Input contract (E2001..E2009)
    E2001 = "E2001"
    E2002 = "E2002"
    E2003 = "E2003"
    E2004 = "E2004"
    E2005 = "E2005"
    E2006 = "E2006"
    E2007 = "E2007"
    E2008 = "E2008"
    E2009 = "E2009"
    # Processing (E2010..E2017)
    E2010 = "E2010"
    E2011 = "E2011"
    E2012 = "E2012"
    E2013 = "E2013"
    E2014 = "E2014"
    E2015 = "E2015"
    E2016 = "E2016"
    E2017 = "E2017"
    # Output (E2020..E2025; E2018, E2019 intentionally skipped)
    E2020 = "E2020"
    E2021 = "E2021"
    E2022 = "E2022"
    E2023 = "E2023"
    E2024 = "E2024"
    E2025 = "E2025"


class EligibilityWarningCode(str, Enum):
    """Closed set of Stage 20 warning codes.

    20.1 active warnings:  W2001, W2004, W2005.
    20.2 reserved:         W2002, W2003, W2006, W2007.
    """

    W2001 = "W2001"
    W2002 = "W2002"
    W2003 = "W2003"
    W2004 = "W2004"
    W2005 = "W2005"
    W2006 = "W2006"
    W2007 = "W2007"


# Snake_case names for each code. Match the renamings from
# Stage 20.1 STEP 0 operator decisions:
#   * E2006: renamed from "duplicate_review_id" (Stage 19 has no
#     review_id column) to "duplicate_ledger_row_id".
#   * W2004: renamed from "multiple_reviews_for_same_token"
#     (Stage 18/19 have no token concept) to
#     "multiple_operators_per_review_slice".
ERROR_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "E2001": "stage18_manifest_missing",
    "E2002": "stage19_manifest_missing",
    "E2003": "stage18_review_matrix_hash_mismatch",
    "E2004": "stage19_ledger_hash_mismatch",
    "E2005": "stage19_ledger_label_not_in_taxonomy",
    "E2006": "stage19_ledger_duplicate_ledger_row_id",
    "E2007": "stage19_ledger_row_missing_label",
    "E2008": "stage18_review_matrix_missing_required_column",
    "E2009": "stage19_ledger_missing_required_column",
    "E2010": "eligibility_taxonomy_incomplete",
    "E2011": "candidate_id_collision",
    "E2012": "filter_interface_schema_violation",
    "E2013": "filter_mode_not_observe_only_in_v0",
    "E2014": "filter_ordering_index_collision",
    "E2015": "decision_step_index_collision",
    "E2016": "multiple_or_zero_terminating_steps",
    "E2017": "decision_state_inconsistency",
    "E2020": "preview_candidates_nondeterministic",
    "E2021": "manifest_input_hashes_missing",
    "E2022": "safe_for_live_dispatch_not_false",
    "E2023": "output_row_count_mismatch",
    "E2024": "manifest_output_hashes_missing",
    "E2025": "output_csv_missing_required_column",
})

WARNING_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "W2001": "stage19_ledger_stale_overall",
    "W2002": "preview_eligible_count_zero",
    "W2003": "tier_hint_missing",
    "W2004": "multiple_operators_per_review_slice",
    "W2005": "stage18_evidence_missing_for_review",
    "W2006": "candidate_review_stale",
    "W2007": "eligibility_mapping_drift_detected",
})


# Codes that 20.1 actively emits vs. defines-but-defers. Used by
# the deferred-test in test_hash_verifier and as documentation of
# scope.
CODES_ACTIVE_IN_STAGE_20_1: frozenset[str] = frozenset({
    "E2001",
    "E2002",
    "E2003",
    "E2005",
    "E2006",
    "E2007",
    "E2008",
    "E2009",
    "E2010",
    "E2022",
})

CODES_DEFERRED_IN_STAGE_20_1: frozenset[str] = frozenset({
    # E2004 deferred because no source-of-truth Stage 19 ledger hash
    # exists anywhere in the current pipeline.
    "E2004",
    # 20.2 codes
    "E2011",
    "E2015",
    "E2016",
    "E2017",
    "E2020",
    "E2021",
    "E2023",
    "E2024",
    "E2025",
    # 20.3 codes
    "E2012",
    "E2013",
    "E2014",
})

WARNINGS_ACTIVE_IN_STAGE_20_1: frozenset[str] = frozenset({
    "W2001",
    "W2004",
    "W2005",
})

WARNINGS_DEFERRED_IN_STAGE_20_1: frozenset[str] = frozenset({
    "W2002",
    "W2003",
    "W2006",
    "W2007",
})


# ---------------------------------------------------------------------------
# Reason code string constants
# (used by 20.2 candidate building and 20.3 filter scaffolding;
#  defined here so the constants module is the single source of truth)
# ---------------------------------------------------------------------------


REASON_CODE_LABEL_MAPPED: str = "LABEL_MAPPED_FROM_OPERATOR_REVIEW"
REASON_CODE_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
REASON_CODE_OPERATOR_EXCLUDED: str = "OPERATOR_EXCLUDED"
REASON_CODE_WATCHLIST_OBSERVE_ONLY: str = "WATCHLIST_OBSERVE_ONLY"
REASON_CODE_DISPATCH_SAFETY_DISABLED: str = "DISPATCH_SAFETY_DISABLED"
REASON_CODE_FILTER_OBSERVE_ONLY_PASSTHROUGH: str = "FILTER_OBSERVE_ONLY_PASSTHROUGH"


# ---------------------------------------------------------------------------
# Stage 20.2 — decision-chain vocabularies
# ---------------------------------------------------------------------------
#
# DEFAULT chain (4 steps per candidate, used in 20.2):
#     0: slice_resolved       (state: passed)
#     1: mapping_applied      (state: passed)
#     2: staleness_evaluated  (state: passed)
#     3: terminal             (state: terminal, terminating=true,
#                              decision_outcome = candidate.preview_state)
#
# FALLBACK chain (2 steps; preserved for shape reference only --
# 20.2 ships the 4-step chain per operator approval):
#     0: mapping_applied      (state: passed)
#     1: terminal             (state: terminal, terminating=true)


DECISION_STEP_NAMES_4: tuple[str, ...] = (
    "slice_resolved",
    "mapping_applied",
    "staleness_evaluated",
    "terminal",
)

DECISION_STEP_NAMES_2: tuple[str, ...] = (
    "mapping_applied",
    "terminal",
)

DECISION_STEP_STATES: tuple[str, ...] = (
    "entered",
    "passed",
    "failed",
    "terminal",
)


# ---------------------------------------------------------------------------
# Stage 20.2 — output CSV column tuples (LOCKED ORDER)
# ---------------------------------------------------------------------------
#
# Both CSV writers iterate over the locked column tuple, NOT over
# the NamedTuple._fields of PreviewCandidate / DecisionStep. The
# model classes may carry additional fields (e.g. 20.1-era fields
# preserved by additive extension); they are not emitted unless
# their name appears in the column tuple below.
#
# preview_candidates.csv -- 18 columns (operator-historical preview
# eligibility per (slice, operator) pair). Sort: review_timestamp_utc
# ASC, candidate_id ASC. Header always written, even on empty data.


PREVIEW_CANDIDATES_CSV_COLUMNS: tuple[str, ...] = (
    "candidate_id",
    "stage20_run_id",
    "stage18_run_id",
    "stage19_run_id",
    "source_ledger_row_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "review_timestamp_utc",
    "review_label",
    "preview_state",
    "mapping_version",
    "tier_hint",
    "review_age_days",
    "review_stale",
    "multiple_operators_for_slice",
    "notes",
)


# alert_eligibility_decisions.csv -- 10 columns (ordered audit trail
# per PreviewCandidate documenting how the terminal preview_state was
# reached). Sort: candidate_id ASC, decision_step_index ASC. Header
# always written.

ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS: tuple[str, ...] = (
    "decision_id",
    "candidate_id",
    "stage20_run_id",
    "decision_step_index",
    "decision_step_name",
    "decision_step_state",
    "decision_step_terminating",
    "decision_outcome",
    "evidence_code",
    "evidence_detail",
)


# ---------------------------------------------------------------------------
# CSV column -> NamedTuple field aliases (centralized per operator
# Phase B constraint #1)
# ---------------------------------------------------------------------------
#
# Each map records the model field name a given CSV column reads
# from. The Phase B model additions added the 20.2-aligned alias
# fields directly to PreviewCandidate and DecisionStep so every
# CSV column now maps 1:1 to a model field with the same name -- the
# alias maps below are empty. They are kept (frozen via
# MappingProxyType) as a single source of truth so that any future
# divergence between CSV name and model field name is registered in
# exactly one place rather than scattered across the builder and
# the writer.
#
# Convention: if a CSV column name is absent from the alias map,
# the model field name is the CSV column name verbatim.


PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD: Mapping[str, str] = MappingProxyType({})

ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD: Mapping[str, str] = (
    MappingProxyType({})
)


def csv_column_to_model_field(
    csv_column: str,
    alias_map: Mapping[str, str],
) -> str:
    """Resolve a CSV column name to its source model field.

    Reads the alias map first; falls back to the column name itself
    when the map carries no entry. The two locked alias maps live
    in this module so callers (builder + writer) never embed a
    branching alias check inline.
    """

    return alias_map.get(csv_column, csv_column)


# ---------------------------------------------------------------------------
# Stage 20.2 -- run-log event sequence (locked, in this exact order)
# ---------------------------------------------------------------------------
#
# Every run emits these 9 events into stage20_run.log in order. The
# log writer asserts the produced event sequence matches this tuple
# before serializing.

STAGE20_RUN_LOG_EVENT_SEQUENCE: tuple[str, ...] = (
    "run_started",
    "inputs_validated",
    "slices_resolved",
    "candidates_built",
    "decisions_built",
    "warnings_emitted",
    "artifacts_written",
    "manifest_written",
    "run_completed",
)


# ---------------------------------------------------------------------------
# Stage 20.2 -- manifest key groups (used by manifest shape validator)
# ---------------------------------------------------------------------------

PREVIEW_STATE_COUNT_KEYS: tuple[str, ...] = (
    "PREVIEW_ELIGIBLE",
    "PREVIEW_OBSERVE_ONLY",
    "PREVIEW_NEEDS_MORE_DATA",
    "PREVIEW_EXCLUDED",
)

MANIFEST_REQUIRED_INPUT_HASH_KEYS: tuple[str, ...] = (
    "stage18_manifest_sha256",
    "stage18_review_matrix_sha256",
    "stage19_ledger_sha256",
    "stage19_manifest_sha256",
)

MANIFEST_REQUIRED_OUTPUT_HASH_KEYS: tuple[str, ...] = (
    "preview_candidates_csv_sha256",
    "alert_eligibility_decisions_csv_sha256",
    "readme_md_sha256",
    "stage20_run_log_sha256",
)

MANIFEST_WARNING_KEYS: tuple[str, ...] = (
    "W2001_run_median_staleness_exceeded",
    "W2002_preview_eligible_count_zero",
    "W2003_tier_hint_missing_count",
    "W2004_multiple_operators_per_review_slice_count",
    "W2005_stage18_evidence_missing_for_review_count",
    "W2006_candidate_review_stale_count",
    "W2007_eligibility_mapping_drift_detected",
)


__all__ = [
    "ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS",
    "ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD",
    "CODES_ACTIVE_IN_STAGE_20_1",
    "CODES_DEFERRED_IN_STAGE_20_1",
    "CONSUMER_CONTRACT_VERSION",
    "DECISION_STEP_NAMES_2",
    "DECISION_STEP_NAMES_4",
    "DECISION_STEP_STATES",
    "ERROR_CODE_NAMES",
    "EligibilityErrorCode",
    "EligibilityWarningCode",
    "LABEL_TO_STATE_MAPPING_V0",
    "MANIFEST_REQUIRED_INPUT_HASH_KEYS",
    "MANIFEST_REQUIRED_OUTPUT_HASH_KEYS",
    "MANIFEST_WARNING_KEYS",
    "MAPPING_VERSION",
    "PREVIEW_CANDIDATES_CSV_COLUMNS",
    "PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD",
    "PREVIEW_STATE_COUNT_KEYS",
    "PreviewEligibilityState",
    "REASON_CODE_DISPATCH_SAFETY_DISABLED",
    "REASON_CODE_FILTER_OBSERVE_ONLY_PASSTHROUGH",
    "REASON_CODE_INSUFFICIENT_EVIDENCE",
    "REASON_CODE_LABEL_MAPPED",
    "REASON_CODE_OPERATOR_EXCLUDED",
    "REASON_CODE_WATCHLIST_OBSERVE_ONLY",
    "SAFE_FOR_LIVE_DISPATCH",
    "STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION",
    "STAGE18_MANIFEST_FILENAME",
    "STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS",
    "STAGE18_REVIEW_MATRIX_FILENAME",
    "STAGE19_EXPECTED_MANIFEST_SCHEMA_VERSION",
    "STAGE19_LEDGER_EXPECTED_COLUMNS",
    "STAGE19_LEDGER_FILENAME",
    "STAGE19_LEDGER_TIMESTAMP_FORMAT",
    "STAGE19_MANIFEST_FILENAME",
    "STAGE19_MANIFEST_KEY_STAGE18_MANIFEST_HASH",
    "STAGE19_MANIFEST_KEY_STAGE18_REVIEW_MATRIX_HASH",
    "STAGE19_MANIFEST_KEY_STAGE18_RUN_ID",
    "STAGE19_MANIFEST_KEY_STAGE19_RUN_ID",
    "STAGE19_REVIEW_LABELS",
    "STAGE19_SUMMARY_EXPECTED_COLUMNS",
    "STAGE19_SUMMARY_FILENAME",
    "STAGE20_MINOR_VERSION",
    "STAGE20_RUN_LOG_EVENT_SEQUENCE",
    "STAGE20_VERSION",
    "STALENESS_THRESHOLD_DAYS",
    "WARNINGS_ACTIVE_IN_STAGE_20_1",
    "WARNINGS_DEFERRED_IN_STAGE_20_1",
    "WARNING_CODE_NAMES",
    "csv_column_to_model_field",
]
