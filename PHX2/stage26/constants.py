"""Stage 26.1 locked constants -- calibration input contracts surface.

Stage 26.1 declares the closed-set vocabularies, version axes, and
typed-error code tokens the Stage 26.1 calibration-input contract
and the Stage 25 artifact reader / validator surfaces consume. Stage
26.1 is a calibration-input-contract sub-stage: it reads Stage 25
artifacts into typed in-memory records and reports per-artifact
validation facts; it does NOT decide denominator inclusion /
exclusion, build calibration cohorts, generate thresholds, generate
policy candidates, write artifacts, define a CLI, read the process
environment, or open a network / DB connection. See
``PHX2/stage26/STAGE_26_0_SPEC_LOCK.md`` for the locked Stage 26.1
charter.

Closed sets declared here:

  * ``CALIBRATION_INPUT_KINDS``    -- one kind per Stage 25 artifact
                                      projected into a Stage 26.1
                                      input record.
  * ``MEASUREMENT_TRUTH_CLASSES``  -- the Stage 25 measurement-status
                                      vocabulary re-asserted verbatim
                                      for Stage 26.1 callers; Stage 26
                                      never adds, removes, or renames
                                      a token. The tuple is the exact
                                      ``MEASUREMENT_STATUSES`` tuple
                                      imported from
                                      ``PHX2.stage25.constants``.
  * ``ARTIFACT_VALIDATION_STATUSES`` -- closed set of per-artifact
                                        validation outcomes the
                                        Stage 26.1 validator emits.
  * ``EXCLUSION_REASONS``          -- closed set of validation /
                                      reporting vocabulary used to
                                      annotate per-row validation
                                      failures. NEVER used by Stage
                                      26.1 to assign a calibration-
                                      eligibility decision -- per-row
                                      eligibility is Stage 26.2.
  * ``STAGE26_ERROR_CODES``        -- closed set of typed-error code
                                      tokens, all prefixed
                                      ``STG26_CAL_``.

Stage 26 does NOT declare:

  * any denominator-status vocabulary -- Stage 26.2.
  * any cohort vocabulary             -- Stage 26.3.
  * any threshold vocabulary          -- Stage 26.4.
  * any policy-candidate vocabulary   -- Stage 26.5.
  * any approval-state vocabulary     -- Stage 26.6.

Stage 26 only imports from ``PHX2.stage25.constants`` (the locked
Stage 25 schema / vocabulary surface). Importing any other Stage 25
module from Stage 26.1 is forbidden by the Stage 26.1 boundary
tests.
"""

from __future__ import annotations

from PHX2.stage26.stage25_schema_whitelist import (
    MEASUREMENT_STATUSES,
    OBSERVE_ONLY_MODE,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
)


# ---------------------------------------------------------------------------
# Stage 26 version strings
# ---------------------------------------------------------------------------


STAGE26_NAME: str = "stage26"
STAGE26_MINOR_VERSION: str = "26.1"
STAGE26_STAGE_VERSION: str = STAGE26_MINOR_VERSION


# Stage 26.1 calibration-input contract version axis. Bumping the
# Stage 26.1 calibration-input record shape requires bumping this
# axis.
STAGE26_CALIBRATION_INPUT_VERSION: str = (
    "stage26_calibration_input_v0"
)


# Stage 26 observe-only posture marker. Re-asserts the Stage 25
# locked ``OBSERVE_ONLY_MODE`` token so the Stage 26.1 validator can
# verify it on each Stage 25 manifest without importing the manifest
# module.
STAGE26_OBSERVE_ONLY_MODE: str = OBSERVE_ONLY_MODE


# ---------------------------------------------------------------------------
# CALIBRATION_INPUT_KINDS -- one kind per Stage 25 artifact projection
# ---------------------------------------------------------------------------


CALIBRATION_INPUT_KIND_MIGRATION_OBSERVATION: str = (
    "MIGRATION_OBSERVATION"
)
CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT: str = (
    "MIGRATION_MEASUREMENT"
)
CALIBRATION_INPUT_KIND_PRICE_WINDOW_OBSERVATION: str = (
    "PRICE_WINDOW_OBSERVATION"
)
CALIBRATION_INPUT_KIND_ATH_CANDIDATE: str = "ATH_CANDIDATE"
CALIBRATION_INPUT_KIND_SOURCE_RECONCILIATION: str = (
    "SOURCE_RECONCILIATION"
)
CALIBRATION_INPUT_KIND_ATH_MEASUREMENT: str = "ATH_MEASUREMENT"
CALIBRATION_INPUT_KIND_MEASUREMENT_REJECTION: str = (
    "MEASUREMENT_REJECTION"
)
CALIBRATION_INPUT_KIND_SUMMARY: str = "SUMMARY"
CALIBRATION_INPUT_KIND_MANIFEST: str = "MANIFEST"


CALIBRATION_INPUT_KINDS: tuple[str, ...] = (
    CALIBRATION_INPUT_KIND_MIGRATION_OBSERVATION,
    CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
    CALIBRATION_INPUT_KIND_PRICE_WINDOW_OBSERVATION,
    CALIBRATION_INPUT_KIND_ATH_CANDIDATE,
    CALIBRATION_INPUT_KIND_SOURCE_RECONCILIATION,
    CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
    CALIBRATION_INPUT_KIND_MEASUREMENT_REJECTION,
    CALIBRATION_INPUT_KIND_SUMMARY,
    CALIBRATION_INPUT_KIND_MANIFEST,
)


# Mapping from Stage 25 artifact basename to its calibration-input
# kind. Used by the Stage 26.1 reader to label projected records.
# Declared as a deterministic tuple-of-pairs (sorted by basename) so
# the boundary scanner can read it as immutable structural data
# rather than a runtime-mutable mapping.
CALIBRATION_INPUT_KIND_BY_ARTIFACT_BASENAME: tuple[
    tuple[str, str], ...
] = (
    (
        STAGE25_ATH_CANDIDATES_FILENAME,
        CALIBRATION_INPUT_KIND_ATH_CANDIDATE,
    ),
    (
        STAGE25_ATH_MEASUREMENTS_FILENAME,
        CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
    ),
    (
        STAGE25_MANIFEST_FILENAME,
        CALIBRATION_INPUT_KIND_MANIFEST,
    ),
    (
        STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
        CALIBRATION_INPUT_KIND_MEASUREMENT_REJECTION,
    ),
    (
        STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
        CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
    ),
    (
        STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
        CALIBRATION_INPUT_KIND_MIGRATION_OBSERVATION,
    ),
    (
        STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
        CALIBRATION_INPUT_KIND_PRICE_WINDOW_OBSERVATION,
    ),
    (
        STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
        CALIBRATION_INPUT_KIND_SOURCE_RECONCILIATION,
    ),
    (
        STAGE25_SUMMARY_FILENAME,
        CALIBRATION_INPUT_KIND_SUMMARY,
    ),
)


# ---------------------------------------------------------------------------
# MEASUREMENT_TRUTH_CLASSES -- Stage 25 measurement-status tokens re-asserted
# ---------------------------------------------------------------------------
#
# Stage 26 preserves Stage 25's measurement truth classes verbatim and
# never invents new tokens. The tuple is the exact
# ``MEASUREMENT_STATUSES`` tuple imported from
# ``PHX2.stage25.constants``; Stage 26.1 callers use this name when
# they want a Stage 26-local handle to the same closed set.


MEASUREMENT_TRUTH_CLASSES: tuple[str, ...] = MEASUREMENT_STATUSES


# ---------------------------------------------------------------------------
# ARTIFACT_VALIDATION_STATUSES -- per-artifact validation outcomes
# ---------------------------------------------------------------------------


ARTIFACT_VALIDATION_STATUS_VALIDATED: str = "VALIDATED"
ARTIFACT_VALIDATION_STATUS_FILE_MISSING: str = "FILE_MISSING"
ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR: str = "FILE_NOT_REGULAR"
ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH: str = (
    "MANIFEST_HASH_MISMATCH"
)
ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH: str = (
    "MANIFEST_BYTE_COUNT_MISMATCH"
)
ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH: str = (
    "MANIFEST_ROW_COUNT_MISMATCH"
)
ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID: str = "SCHEMA_INVALID"
ARTIFACT_VALIDATION_STATUS_UNEXPECTED_EXTRA_FIELD: str = (
    "UNEXPECTED_EXTRA_FIELD"
)
ARTIFACT_VALIDATION_STATUS_RECORD_SCHEMA_INVALID: str = (
    "RECORD_SCHEMA_INVALID"
)
ARTIFACT_VALIDATION_STATUS_RECORD_TRUTH_CLASS_INVALID: str = (
    "RECORD_TRUTH_CLASS_INVALID"
)
ARTIFACT_VALIDATION_STATUS_RECORD_NULL_AS_ZERO_VIOLATION: str = (
    "RECORD_NULL_AS_ZERO_VIOLATION"
)
ARTIFACT_VALIDATION_STATUS_REFERENTIAL_LINK_BROKEN: str = (
    "REFERENTIAL_LINK_BROKEN"
)


ARTIFACT_VALIDATION_STATUSES: tuple[str, ...] = (
    ARTIFACT_VALIDATION_STATUS_VALIDATED,
    ARTIFACT_VALIDATION_STATUS_FILE_MISSING,
    ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
    ARTIFACT_VALIDATION_STATUS_UNEXPECTED_EXTRA_FIELD,
    ARTIFACT_VALIDATION_STATUS_RECORD_SCHEMA_INVALID,
    ARTIFACT_VALIDATION_STATUS_RECORD_TRUTH_CLASS_INVALID,
    ARTIFACT_VALIDATION_STATUS_RECORD_NULL_AS_ZERO_VIOLATION,
    ARTIFACT_VALIDATION_STATUS_REFERENTIAL_LINK_BROKEN,
)


# ---------------------------------------------------------------------------
# EXCLUSION_REASONS -- validation / reporting vocabulary ONLY
# ---------------------------------------------------------------------------
#
# Closed-set short tokens the Stage 26.1 validator attaches to a
# per-row validation entry when a row fails manifest-level / schema-
# level validation. NEVER used to assign a calibration-eligibility
# decision -- per-row eligibility is Stage 26.2. The names are
# deliberately validation-shaped, not eligibility-shaped.


EXCLUSION_REASON_MANIFEST_DECLARED_FILE_MISSING: str = (
    "MANIFEST_DECLARED_FILE_MISSING"
)
EXCLUSION_REASON_MANIFEST_HASH_MISMATCH: str = (
    "MANIFEST_HASH_MISMATCH"
)
EXCLUSION_REASON_MANIFEST_BYTE_COUNT_MISMATCH: str = (
    "MANIFEST_BYTE_COUNT_MISMATCH"
)
EXCLUSION_REASON_MANIFEST_ROW_COUNT_MISMATCH: str = (
    "MANIFEST_ROW_COUNT_MISMATCH"
)
EXCLUSION_REASON_RECORD_SCHEMA_INVALID: str = "RECORD_SCHEMA_INVALID"
EXCLUSION_REASON_RECORD_TRUTH_CLASS_INVALID: str = (
    "RECORD_TRUTH_CLASS_INVALID"
)
EXCLUSION_REASON_RECORD_NULL_AS_ZERO_VIOLATION: str = (
    "RECORD_NULL_AS_ZERO_VIOLATION"
)
EXCLUSION_REASON_REFERENTIAL_LINK_BROKEN: str = (
    "REFERENTIAL_LINK_BROKEN"
)


EXCLUSION_REASONS: tuple[str, ...] = (
    EXCLUSION_REASON_MANIFEST_DECLARED_FILE_MISSING,
    EXCLUSION_REASON_MANIFEST_HASH_MISMATCH,
    EXCLUSION_REASON_MANIFEST_BYTE_COUNT_MISMATCH,
    EXCLUSION_REASON_MANIFEST_ROW_COUNT_MISMATCH,
    EXCLUSION_REASON_RECORD_SCHEMA_INVALID,
    EXCLUSION_REASON_RECORD_TRUTH_CLASS_INVALID,
    EXCLUSION_REASON_RECORD_NULL_AS_ZERO_VIOLATION,
    EXCLUSION_REASON_REFERENTIAL_LINK_BROKEN,
)


# ---------------------------------------------------------------------------
# STAGE26_ERROR_CODES -- typed-error code tokens (prefix STG26_CAL_)
# ---------------------------------------------------------------------------


STG26_CAL_MANIFEST_NOT_FOUND: str = "STG26_CAL_MANIFEST_NOT_FOUND"
STG26_CAL_MANIFEST_SCHEMA_INVALID: str = (
    "STG26_CAL_MANIFEST_SCHEMA_INVALID"
)
STG26_CAL_MANIFEST_HASH_SELF_INVALID: str = (
    "STG26_CAL_MANIFEST_HASH_SELF_INVALID"
)
STG26_CAL_ARTIFACT_MISSING_REQUIRED: str = (
    "STG26_CAL_ARTIFACT_MISSING_REQUIRED"
)
STG26_CAL_ARTIFACT_HASH_MISMATCH: str = (
    "STG26_CAL_ARTIFACT_HASH_MISMATCH"
)
STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH: str = (
    "STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH"
)
STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH: str = (
    "STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH"
)
STG26_CAL_ARTIFACT_SCHEMA_INVALID: str = (
    "STG26_CAL_ARTIFACT_SCHEMA_INVALID"
)
STG26_CAL_ARTIFACT_UNEXPECTED_EXTRA: str = (
    "STG26_CAL_ARTIFACT_UNEXPECTED_EXTRA"
)
STG26_CAL_RECORD_SCHEMA_INVALID: str = (
    "STG26_CAL_RECORD_SCHEMA_INVALID"
)
STG26_CAL_RECORD_TRUTH_CLASS_INVALID: str = (
    "STG26_CAL_RECORD_TRUTH_CLASS_INVALID"
)
STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION: str = (
    "STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION"
)
STG26_CAL_REFERENTIAL_LINK_BROKEN: str = (
    "STG26_CAL_REFERENTIAL_LINK_BROKEN"
)
STG26_CAL_STAGE25_SCHEMA_WHITELIST_DRIFT: str = (
    "STG26_CAL_STAGE25_SCHEMA_WHITELIST_DRIFT"
)
STG26_CAL_FORBIDDEN_STAGE_IMPORT: str = (
    "STG26_CAL_FORBIDDEN_STAGE_IMPORT"
)


STAGE26_ERROR_CODES: tuple[str, ...] = (
    STG26_CAL_MANIFEST_NOT_FOUND,
    STG26_CAL_MANIFEST_SCHEMA_INVALID,
    STG26_CAL_MANIFEST_HASH_SELF_INVALID,
    STG26_CAL_ARTIFACT_MISSING_REQUIRED,
    STG26_CAL_ARTIFACT_HASH_MISMATCH,
    STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH,
    STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH,
    STG26_CAL_ARTIFACT_SCHEMA_INVALID,
    STG26_CAL_ARTIFACT_UNEXPECTED_EXTRA,
    STG26_CAL_RECORD_SCHEMA_INVALID,
    STG26_CAL_RECORD_TRUTH_CLASS_INVALID,
    STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
    STG26_CAL_REFERENTIAL_LINK_BROKEN,
    STG26_CAL_STAGE25_SCHEMA_WHITELIST_DRIFT,
    STG26_CAL_FORBIDDEN_STAGE_IMPORT,
)


__all__ = [
    "ARTIFACT_VALIDATION_STATUSES",
    "ARTIFACT_VALIDATION_STATUS_FILE_MISSING",
    "ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR",
    "ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH",
    "ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH",
    "ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH",
    "ARTIFACT_VALIDATION_STATUS_RECORD_NULL_AS_ZERO_VIOLATION",
    "ARTIFACT_VALIDATION_STATUS_RECORD_SCHEMA_INVALID",
    "ARTIFACT_VALIDATION_STATUS_RECORD_TRUTH_CLASS_INVALID",
    "ARTIFACT_VALIDATION_STATUS_REFERENTIAL_LINK_BROKEN",
    "ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID",
    "ARTIFACT_VALIDATION_STATUS_UNEXPECTED_EXTRA_FIELD",
    "ARTIFACT_VALIDATION_STATUS_VALIDATED",
    "CALIBRATION_INPUT_KINDS",
    "CALIBRATION_INPUT_KIND_ATH_CANDIDATE",
    "CALIBRATION_INPUT_KIND_ATH_MEASUREMENT",
    "CALIBRATION_INPUT_KIND_BY_ARTIFACT_BASENAME",
    "CALIBRATION_INPUT_KIND_MANIFEST",
    "CALIBRATION_INPUT_KIND_MEASUREMENT_REJECTION",
    "CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT",
    "CALIBRATION_INPUT_KIND_MIGRATION_OBSERVATION",
    "CALIBRATION_INPUT_KIND_PRICE_WINDOW_OBSERVATION",
    "CALIBRATION_INPUT_KIND_SOURCE_RECONCILIATION",
    "CALIBRATION_INPUT_KIND_SUMMARY",
    "EXCLUSION_REASONS",
    "EXCLUSION_REASON_MANIFEST_BYTE_COUNT_MISMATCH",
    "EXCLUSION_REASON_MANIFEST_DECLARED_FILE_MISSING",
    "EXCLUSION_REASON_MANIFEST_HASH_MISMATCH",
    "EXCLUSION_REASON_MANIFEST_ROW_COUNT_MISMATCH",
    "EXCLUSION_REASON_RECORD_NULL_AS_ZERO_VIOLATION",
    "EXCLUSION_REASON_RECORD_SCHEMA_INVALID",
    "EXCLUSION_REASON_RECORD_TRUTH_CLASS_INVALID",
    "EXCLUSION_REASON_REFERENTIAL_LINK_BROKEN",
    "MEASUREMENT_TRUTH_CLASSES",
    "STAGE26_CALIBRATION_INPUT_VERSION",
    "STAGE26_ERROR_CODES",
    "STAGE26_MINOR_VERSION",
    "STAGE26_NAME",
    "STAGE26_OBSERVE_ONLY_MODE",
    "STAGE26_STAGE_VERSION",
    "STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH",
    "STG26_CAL_ARTIFACT_HASH_MISMATCH",
    "STG26_CAL_ARTIFACT_MISSING_REQUIRED",
    "STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH",
    "STG26_CAL_ARTIFACT_SCHEMA_INVALID",
    "STG26_CAL_ARTIFACT_UNEXPECTED_EXTRA",
    "STG26_CAL_FORBIDDEN_STAGE_IMPORT",
    "STG26_CAL_MANIFEST_HASH_SELF_INVALID",
    "STG26_CAL_MANIFEST_NOT_FOUND",
    "STG26_CAL_MANIFEST_SCHEMA_INVALID",
    "STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION",
    "STG26_CAL_RECORD_SCHEMA_INVALID",
    "STG26_CAL_RECORD_TRUTH_CLASS_INVALID",
    "STG26_CAL_REFERENTIAL_LINK_BROKEN",
    "STG26_CAL_STAGE25_SCHEMA_WHITELIST_DRIFT",
]
