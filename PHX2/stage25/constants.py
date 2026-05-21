"""Stage 25 locked constants (foundation only at 25.1).

Every Stage 25 closed-set vocabulary, version axis, tolerance
literal, and boundary-scan input lives here. Stage 25 mirrors the
Stage 21 / Stage 22 / Stage 23 / Stage 24 convention: every
closed-set surface is a ``tuple[str, ...]`` declared once in this
module and consumed verbatim by callers.

Stage 25.1 is contracts-only: this module is read by
``PHX2/stage25/models.py``,
``PHX2/stage25/measurement_contracts.py``,
``PHX2/stage25/input_reader.py``,
``PHX2/stage25/stage25_manifest.py``, and by the
``PHX2/tests/stage25/`` boundary tests. No Stage 25 production
module outside this module may declare a Stage 25 closed-set
token.

The Stage 25 forbidden-routing tuple intentionally mirrors the
Stage 21 / Stage 22 / Stage 23 / Stage 24 sets but is
re-declared locally so the identifier-aware boundary scanner in
``test_stage_25_1_boundaries.py`` does not need to reach into
prior stages.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 25 version strings
# ---------------------------------------------------------------------------


STAGE25_VERSION: str = "stage25_v0_measurement_foundation"
# Minor version axis. Bump on every sub-stage merge: 25.1 -> 25.2 -> ...
STAGE25_MINOR_VERSION: str = "25.1"

# Stage name token. Mirrors the prior-stage discipline.
STAGE_NAME: str = "stage25"

# Locked alias for the minor version. Documented as the public
# stage version axis emitted on manifest records.
STAGE_VERSION: str = STAGE25_MINOR_VERSION


# Stage 25 schema version. Per-record schema version used by the
# measurement / observation surface and the manifest surface. The
# schema version is intentionally orthogonal to STAGE_VERSION:
# bumping the stage version axis (25.1 -> 25.2) does NOT
# automatically bump the schema version; the on-disk record shape
# is bumped only when it materially changes.
DEFAULT_SCHEMA_VERSION: str = "stage25_v0_measurement"
STAGE25_MANIFEST_SCHEMA_VERSION: str = "stage25_v0_manifest"


# Observe-only posture marker. The single canonical short string
# manifest records carry to assert Stage 25's posture. Stage 25
# never blocks, gates, or routes -- it only emits evidence.
OBSERVE_ONLY_MODE: str = "observe_only"


# Threshold-version axis. Stage 25.1 has no thresholds; Stage 26
# is the calibration / enforcement stage that consumes Stage 25
# evidence. The threshold axis is reserved here so 25.1+ records
# carry a stable, deterministic threshold-version string even when
# no measurer applies a threshold.
DEFAULT_THRESHOLD_VERSION: str = "thresholds_v0_observe_only"


# Redaction confirmation token. A future Stage 25.5 runner sets
# this on a manifest after running its own redaction sweep; an
# operator can grep manifests for the absence of this token to
# detect runners that skipped the sweep. Stage 25.1 ships the
# token only; no runner sets it yet.
REDACTION_CONFIRMED_TOKEN: str = "stage25_redaction_confirmed"


# ---------------------------------------------------------------------------
# Stage 25 runner / writer version axes (Stage 25.6 surface)
# ---------------------------------------------------------------------------
#
# Stage 25.6 ships the pure runner and the deterministic artifact
# writer. The version axes below are the locked identifiers the
# runner / writer emit so downstream readers can pin the exact
# code that produced a runner result / artifact manifest record
# without inspecting commit hashes. Bumping runner / writer
# semantics requires bumping the ``_VERSION`` axis.


STAGE25_RUNNER_NAME: str = "stage25_measurement_runner"
STAGE25_RUNNER_VERSION: str = "stage25_runner_v0"
STAGE25_ARTIFACT_WRITER_NAME: str = "stage25_artifact_writer"
STAGE25_ARTIFACT_WRITER_VERSION: str = "stage25_writer_v0"
# Alias the writer axes under the Stage 25.6 spec names so downstream
# callers can import either form. The two name pairs always carry the
# same value: the alias is a synonym, not a separate axis.
STAGE25_WRITER_NAME: str = STAGE25_ARTIFACT_WRITER_NAME
STAGE25_WRITER_VERSION: str = STAGE25_ARTIFACT_WRITER_VERSION
STAGE25_SUMMARY_VERSION: str = "stage25_summary_v0"


# ---------------------------------------------------------------------------
# Stage 25.2 migration observation / measurer version axes
# ---------------------------------------------------------------------------
#
# Stage 25.2 ships the migration observation helpers and the
# migration measurer. The version axes below are the locked
# identifiers the measurer / helper modules emit so downstream
# readers can pin the exact code that produced a measurement
# record without inspecting commit hashes. Bumping the measurer
# semantics requires bumping the ``_VERSION`` axis.


STAGE25_MIGRATION_OBSERVATION_VERSION: str = (
    "stage25_migration_observation_v0"
)
STAGE25_MIGRATION_MEASURER_NAME: str = "stage25_migration_measurer"
STAGE25_MIGRATION_MEASURER_VERSION: str = (
    "stage25_migration_measurer_v0"
)


# ---------------------------------------------------------------------------
# Stage 25.3 price observation / window version axes
# ---------------------------------------------------------------------------
#
# Stage 25.3 ships the price-observation helpers and the price-
# window projector. The version axes below are the locked
# identifiers the helper / projector modules emit so downstream
# readers can pin the exact code that produced a price-window
# observation record. Bumping the projector semantics requires
# bumping the ``_VERSION`` axis.


STAGE25_PRICE_OBSERVATION_VERSION: str = (
    "stage25_price_observation_v0"
)
STAGE25_PRICE_WINDOW_VERSION: str = "stage25_price_window_v0"


# ---------------------------------------------------------------------------
# Stage 25.4 ATH candidate version axis
# ---------------------------------------------------------------------------
#
# Stage 25.4 ships the ATH candidate builder. The version axis below
# is the locked identifier the builder module emits so downstream
# readers can pin the exact code that produced a candidate row.
# Bumping the builder semantics requires bumping the ``_VERSION``
# axis. Stage 25.4 emits candidates only -- the consolidated ATH
# measurement is Stage 25.5+ work and is intentionally absent here.


STAGE25_ATH_CANDIDATE_VERSION: str = "stage25_ath_candidate_v0"


# ---------------------------------------------------------------------------
# Stage 25.5 source reconciliation / ATH measurement version axes
# ---------------------------------------------------------------------------
#
# Stage 25.5 ships the source-reconciliation reconciler that consumes
# per-source ``Stage25ATHCandidate`` rows and emits one
# ``Stage25SourceReconciliation`` record plus one
# ``Stage25ATHMeasurement`` record per token. The version axes below
# are the locked identifiers the reconciler emits so downstream
# readers can pin the exact code that produced a reconciliation /
# measurement record. Bumping the reconciler semantics requires
# bumping the ``_VERSION`` axis.


STAGE25_SOURCE_RECONCILIATION_VERSION: str = (
    "stage25_source_reconciliation_v0"
)
STAGE25_ATH_MEASUREMENT_VERSION: str = "stage25_ath_measurement_v0"
STAGE25_ATH_MEASURER_NAME: str = "stage25_ath_measurer"


# ---------------------------------------------------------------------------
# MEASUREMENT_FAMILIES -- closed set of measurement families
# ---------------------------------------------------------------------------


MEASUREMENT_FAMILY_MIGRATION: str = "MIGRATION"
MEASUREMENT_FAMILY_ATH: str = "ATH"


MEASUREMENT_FAMILIES: tuple[str, ...] = (
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_FAMILY_ATH,
)


# ---------------------------------------------------------------------------
# SOURCE_FAMILIES -- closed set of evidence sources
# ---------------------------------------------------------------------------


SOURCE_FAMILY_BIRDEYE: str = "BIRDEYE"
SOURCE_FAMILY_DEXSCREENER: str = "DEXSCREENER"
SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY: str = "ON_CHAIN_SWAP_REPLAY"
SOURCE_FAMILY_WEBSOCKET_CAPTURE: str = "WEBSOCKET_CAPTURE"
SOURCE_FAMILY_UNKNOWN_SOURCE: str = "UNKNOWN_SOURCE"


SOURCE_FAMILIES: tuple[str, ...] = (
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_FAMILY_WEBSOCKET_CAPTURE,
    SOURCE_FAMILY_UNKNOWN_SOURCE,
)


# ---------------------------------------------------------------------------
# SOURCE_STATUSES -- closed set of per-source completeness tokens
# ---------------------------------------------------------------------------


SOURCE_STATUS_PRESENT: str = "PRESENT"
SOURCE_STATUS_ABSENT: str = "ABSENT"
SOURCE_STATUS_PARTIAL: str = "PARTIAL"
SOURCE_STATUS_UNSUPPORTED: str = "UNSUPPORTED"
SOURCE_STATUS_AMBIGUOUS: str = "AMBIGUOUS"
SOURCE_STATUS_MALFORMED: str = "MALFORMED"
SOURCE_STATUS_DECODE_FAILED: str = "DECODE_FAILED"


SOURCE_STATUSES: tuple[str, ...] = (
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_UNSUPPORTED,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_DECODE_FAILED,
)


# ---------------------------------------------------------------------------
# MEASUREMENT_STATUSES -- closed set of per-measurement outcome tokens
# ---------------------------------------------------------------------------


MEASUREMENT_STATUS_MEASURED: str = "MEASURED"
MEASUREMENT_STATUS_PARTIAL: str = "PARTIAL"
MEASUREMENT_STATUS_UNSUPPORTED: str = "UNSUPPORTED"
MEASUREMENT_STATUS_AMBIGUOUS: str = "AMBIGUOUS"
MEASUREMENT_STATUS_SOURCE_CONFLICT: str = "SOURCE_CONFLICT"
MEASUREMENT_STATUS_MISSING: str = "MISSING"
MEASUREMENT_STATUS_REJECTED: str = "REJECTED"
MEASUREMENT_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"


MEASUREMENT_STATUSES: tuple[str, ...] = (
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_UNSUPPORTED,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_NOT_APPLICABLE,
)


# ---------------------------------------------------------------------------
# CONFIDENCE_LEVELS -- coarse confidence axis
# ---------------------------------------------------------------------------


CONFIDENCE_LEVEL_HIGH: str = "HIGH"
CONFIDENCE_LEVEL_MEDIUM: str = "MEDIUM"
CONFIDENCE_LEVEL_LOW: str = "LOW"
CONFIDENCE_LEVEL_NONE: str = "NONE"


CONFIDENCE_LEVELS: tuple[str, ...] = (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
)


# ---------------------------------------------------------------------------
# REJECTION_REASONS -- closed set of input-rejection reason tokens
# ---------------------------------------------------------------------------


REJECTION_REASON_INPUT_MALFORMED: str = "INPUT_MALFORMED"
REJECTION_REASON_FORBIDDEN_FIELD_SUBSTRING: str = "FORBIDDEN_FIELD_SUBSTRING"
REJECTION_REASON_FORBIDDEN_VALUE_SUBSTRING: str = "FORBIDDEN_VALUE_SUBSTRING"
REJECTION_REASON_LONG_HEX_RUN_DETECTED: str = "LONG_HEX_RUN_DETECTED"
REJECTION_REASON_UNKNOWN_INPUT_KIND: str = "UNKNOWN_INPUT_KIND"
REJECTION_REASON_UNKNOWN_SOURCE_FAMILY: str = "UNKNOWN_SOURCE_FAMILY"
REJECTION_REASON_SOURCE_BUILDER_TYPED_ERROR: str = (
    "SOURCE_BUILDER_TYPED_ERROR"
)
# Reason recorded when a measurer refuses to produce a measured
# ATH because the migration measurement carries the AMBIGUOUS
# status. See the Stage 25 honesty rules in the package docstring
# -- a measured ATH requires a known migration boundary.
REJECTION_REASON_MIGRATION_AMBIGUOUS_PROHIBITS_ATH: str = (
    "MIGRATION_AMBIGUOUS_BLOCKS_ATH"
)
REJECTION_REASON_PRE_MIGRATION_OBSERVATION_USED_FOR_ATH: str = (
    "PRE_MIGRATION_OBSERVATION_USED_FOR_ATH"
)
REJECTION_REASON_ZERO_PRICE_WITHOUT_EXPLICIT_OBSERVED_ZERO: str = (
    "ZERO_PRICE_WITHOUT_EXPLICIT_OBSERVED_ZERO"
)
REJECTION_REASON_NEGATIVE_PRICE: str = "NEGATIVE_PRICE"
REJECTION_REASON_NON_FINITE_PRICE: str = "NON_FINITE_PRICE"
REJECTION_REASON_DUPLICATE_OBSERVATION: str = "DUPLICATE_OBSERVATION"
REJECTION_REASON_NULL_REQUIRES_EXPLICIT_STATUS: str = (
    "NULL_REQUIRES_EXPLICIT_STATUS"
)


REJECTION_REASONS: tuple[str, ...] = (
    REJECTION_REASON_INPUT_MALFORMED,
    REJECTION_REASON_FORBIDDEN_FIELD_SUBSTRING,
    REJECTION_REASON_FORBIDDEN_VALUE_SUBSTRING,
    REJECTION_REASON_LONG_HEX_RUN_DETECTED,
    REJECTION_REASON_UNKNOWN_INPUT_KIND,
    REJECTION_REASON_UNKNOWN_SOURCE_FAMILY,
    REJECTION_REASON_SOURCE_BUILDER_TYPED_ERROR,
    REJECTION_REASON_MIGRATION_AMBIGUOUS_PROHIBITS_ATH,
    REJECTION_REASON_PRE_MIGRATION_OBSERVATION_USED_FOR_ATH,
    REJECTION_REASON_ZERO_PRICE_WITHOUT_EXPLICIT_OBSERVED_ZERO,
    REJECTION_REASON_NEGATIVE_PRICE,
    REJECTION_REASON_NON_FINITE_PRICE,
    REJECTION_REASON_DUPLICATE_OBSERVATION,
    REJECTION_REASON_NULL_REQUIRES_EXPLICIT_STATUS,
)


# ---------------------------------------------------------------------------
# PRICE_WINDOW_KINDS -- closed set of price-window tokens
# ---------------------------------------------------------------------------


PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY: str = "POST_MIGRATION_PRIMARY"
PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED: str = "POST_MIGRATION_EXTENDED"
PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED: str = "PRE_MIGRATION_EXCLUDED"
PRICE_WINDOW_KIND_UNKNOWN_WINDOW: str = "UNKNOWN_WINDOW"


PRICE_WINDOW_KINDS: tuple[str, ...] = (
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
)


# ---------------------------------------------------------------------------
# ATH_CANDIDATE_KINDS -- closed set of ATH-candidate kinds
# ---------------------------------------------------------------------------


ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK: str = "SOURCE_REPORTED_PEAK"
ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK: str = "SWAP_REPLAY_PEAK"
ATH_CANDIDATE_KIND_COMBINED_PEAK: str = "COMBINED_PEAK"
ATH_CANDIDATE_KIND_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"


ATH_CANDIDATE_KINDS: tuple[str, ...] = (
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK,
    ATH_CANDIDATE_KIND_COMBINED_PEAK,
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
)


# ---------------------------------------------------------------------------
# RECONCILIATION_STATUSES -- closed set of source-reconciliation outcomes
# ---------------------------------------------------------------------------
#
# SINGLE_SOURCE is recorded by future reconcilers when only one
# source contributed evidence to a measurement. Stage 25.1 does
# NOT permanently encode "single source can never become
# measured." Future versioned measurement policy (Stage 25.5+)
# decides how to translate SINGLE_SOURCE reconciliation into a
# measurement_status.


RECONCILIATION_STATUS_AGREED: str = "AGREED"
RECONCILIATION_STATUS_DISAGREED_MINOR: str = "DISAGREED_MINOR"
RECONCILIATION_STATUS_DISAGREED_MAJOR: str = "DISAGREED_MAJOR"
RECONCILIATION_STATUS_SINGLE_SOURCE: str = "SINGLE_SOURCE"
RECONCILIATION_STATUS_NO_SOURCES: str = "NO_SOURCES"
RECONCILIATION_STATUS_AMBIGUOUS: str = "AMBIGUOUS"


RECONCILIATION_STATUSES: tuple[str, ...] = (
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_DISAGREED_MINOR,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_AMBIGUOUS,
)


# ---------------------------------------------------------------------------
# QUOTE_DENOMINATIONS -- closed set of price denominations
# ---------------------------------------------------------------------------


QUOTE_DENOMINATION_USD_MICRO: str = "USD_MICRO"
QUOTE_DENOMINATION_SOL_LAMPORTS: str = "SOL_LAMPORTS"
QUOTE_DENOMINATION_UNKNOWN_QUOTE: str = "UNKNOWN_QUOTE"


QUOTE_DENOMINATIONS: tuple[str, ...] = (
    QUOTE_DENOMINATION_USD_MICRO,
    QUOTE_DENOMINATION_SOL_LAMPORTS,
    QUOTE_DENOMINATION_UNKNOWN_QUOTE,
)


# ---------------------------------------------------------------------------
# INPUT_KINDS -- closed set of Stage 25 input source kinds
# ---------------------------------------------------------------------------


INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL: str = "migration_observations_jsonl"
INPUT_KIND_PRICE_OBSERVATIONS_JSONL: str = "price_observations_jsonl"
INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL: str = (
    "synthetic_migration_observations_jsonl"
)
INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL: str = (
    "synthetic_price_observations_jsonl"
)
INPUT_KIND_SANITIZED_REAL_MIGRATION_OBSERVATIONS_JSONL: str = (
    "sanitized_real_migration_observations_jsonl"
)
INPUT_KIND_SANITIZED_REAL_PRICE_OBSERVATIONS_JSONL: str = (
    "sanitized_real_price_observations_jsonl"
)


INPUT_KINDS: tuple[str, ...] = (
    INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL,
    INPUT_KIND_SANITIZED_REAL_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SANITIZED_REAL_PRICE_OBSERVATIONS_JSONL,
)


# Sub-partition: the migration-observation kinds. The price-
# observation kinds are the complement. The reader uses these to
# select the per-row builder without re-pattern-matching on the
# token's substring.


MIGRATION_OBSERVATION_INPUT_KINDS: tuple[str, ...] = (
    INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SANITIZED_REAL_MIGRATION_OBSERVATIONS_JSONL,
)


PRICE_OBSERVATION_INPUT_KINDS: tuple[str, ...] = (
    INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL,
    INPUT_KIND_SANITIZED_REAL_PRICE_OBSERVATIONS_JSONL,
)


# ---------------------------------------------------------------------------
# Reason-code tokens carried inside ``reason_codes`` tuples
# ---------------------------------------------------------------------------
#
# Closed-set short tokens callers attach to the ``reason_codes``
# tuple on observations / measurements / candidates so downstream
# readers can group rows without parsing free-form text. The set
# is intentionally minimal at 25.1 -- only the invariants the
# Stage 25.1 validators check are listed.


REASON_CODE_PRICE_OBSERVED_ZERO: str = "PRICE_OBSERVED_ZERO"


# ---------------------------------------------------------------------------
# Migration measurement reason codes (Stage 25.2)
# ---------------------------------------------------------------------------
#
# Closed-set short tokens the Stage 25.2 migration measurer / helper
# emits on observations and on consolidated migration measurement
# records. They name the WHY of a measurement_status / partial
# evidence assignment so downstream readers can group rows without
# parsing free-form text.
#
# Naming mirrors the existing ``REASON_CODE_PRICE_OBSERVED_ZERO``
# pattern: the constant name carries the ``REASON_CODE_`` prefix,
# the value is the canonical short token. The forbidden-vocabulary
# scanner inspects identifier positions, not string literal values,
# so the canonical token can contain Stage 25 vocabulary like
# ``MIGRATION`` and ``BLOCK_TIME`` without tripping the scanner.


REASON_CODE_MIGRATION_NO_OBSERVATIONS: str = "MIGRATION_NO_OBSERVATIONS"
REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES: str = (
    "MIGRATION_NO_CONTRIBUTING_SOURCES"
)
REASON_CODE_MIGRATION_SINGLE_SOURCE: str = "MIGRATION_SINGLE_SOURCE"
REASON_CODE_MIGRATION_SOURCES_AGREED: str = "MIGRATION_SOURCES_AGREED"
REASON_CODE_MIGRATION_SOURCES_DISAGREED: str = (
    "MIGRATION_SOURCES_DISAGREED"
)
REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT: str = (
    "MIGRATION_SAME_SOURCE_CONFLICT"
)
REASON_CODE_MIGRATION_BLOCK_TIME_MISSING: str = (
    "MIGRATION_BLOCK_TIME_MISSING"
)
REASON_CODE_MIGRATION_SIGNATURE_MISSING: str = (
    "MIGRATION_SIGNATURE_MISSING"
)
REASON_CODE_MIGRATION_SLOT_MISSING: str = "MIGRATION_SLOT_MISSING"
REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS: str = (
    "MIGRATION_UNSUPPORTED_SOURCE_STATUS"
)
REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS: str = (
    "MIGRATION_AMBIGUOUS_SOURCE_STATUS"
)
REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED: str = (
    "MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED"
)
REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED: str = (
    "MIGRATION_TOKEN_MISMATCH_REJECTED"
)


# ---------------------------------------------------------------------------
# Price observation / price-window reason codes (Stage 25.3)
# ---------------------------------------------------------------------------
#
# Closed-set short tokens the Stage 25.3 price-observation helpers
# and the price-window projector attach to ``reason_codes`` tuples
# on price-window observation records. They name the WHY of a
# window-kind assignment / contribution decision without requiring
# downstream readers to parse free-form text.


REASON_CODE_PRICE_OBSERVATION_DUPLICATE_COLLAPSED: str = (
    "PRICE_OBSERVATION_DUPLICATE_COLLAPSED"
)
REASON_CODE_PRICE_OBSERVATION_NO_PRICE: str = "PRICE_OBSERVATION_NO_PRICE"
REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT: str = (
    "PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT"
)
REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS: str = (
    "PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS"
)
REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED: str = (
    "PRICE_WINDOW_PRE_MIGRATION_EXCLUDED"
)
REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY: str = (
    "PRICE_WINDOW_POST_MIGRATION_PRIMARY"
)
REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED: str = (
    "PRICE_WINDOW_POST_MIGRATION_EXTENDED"
)
REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION: str = (
    "PRICE_WINDOW_UNKNOWN_MIGRATION"
)
REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING: str = (
    "PRICE_WINDOW_OBSERVED_AT_MISSING"
)
REASON_CODE_PRICE_WINDOW_TOKEN_MISMATCH_REJECTED: str = (
    "PRICE_WINDOW_TOKEN_MISMATCH_REJECTED"
)
REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED: str = (
    "PRICE_WINDOW_MIGRATION_NOT_MEASURED"
)
REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS: str = (
    "PRICE_WINDOW_PARTIAL_SOURCE_STATUS"
)
REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS: str = (
    "PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS"
)


# ---------------------------------------------------------------------------
# ATH candidate reason codes (Stage 25.4)
# ---------------------------------------------------------------------------
#
# Closed-set short tokens the Stage 25.4 ATH candidate builder
# attaches to ``reason_codes`` tuples on candidate records. They name
# the WHY of a candidate-kind / peak-selection / non-contribution
# decision without requiring downstream readers to parse free-form
# text.


REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK: str = (
    "ATH_CANDIDATE_SELECTED_SOURCE_PEAK"
)
REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK: str = (
    "ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK"
)
REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA: str = (
    "ATH_CANDIDATE_INSUFFICIENT_DATA"
)
REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS: str = (
    "ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS"
)
REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED: str = (
    "ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED"
)
REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED: str = (
    "ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED"
)
REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED: str = (
    "ATH_CANDIDATE_NULL_PRICE_EXCLUDED"
)
REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS: str = (
    "ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS"
)
REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS: str = (
    "ATH_CANDIDATE_PARTIAL_SOURCE_STATUS"
)
REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED: str = (
    "ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED"
)
REASON_CODE_ATH_CANDIDATE_TOKEN_SOURCE_MISMATCH_REJECTED: str = (
    "ATH_CANDIDATE_TOKEN_SOURCE_MISMATCH_REJECTED"
)


# ---------------------------------------------------------------------------
# Stage 25.5 source-reconciliation / ATH-measurement reason codes
# ---------------------------------------------------------------------------
#
# Closed-set short tokens the Stage 25.5 source reconciler attaches
# to the ``reason_codes`` tuple on ``Stage25SourceReconciliation``
# and ``Stage25ATHMeasurement`` records. They name the WHY of a
# reconciliation outcome / consolidated measurement assignment so
# downstream readers can group rows without parsing free-form text.


REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES: str = (
    "SOURCE_RECONCILIATION_NO_CANDIDATES"
)
REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES: str = (
    "SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES"
)
REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL: str = (
    "SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL"
)
REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED: str = (
    "SOURCE_RECONCILIATION_SOURCES_AGREED"
)
REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR: str = (
    "SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR"
)
REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR: str = (
    "SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR"
)
REASON_CODE_SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE: str = (
    "SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE"
)
REASON_CODE_SOURCE_RECONCILIATION_INSUFFICIENT_DATA: str = (
    "SOURCE_RECONCILIATION_INSUFFICIENT_DATA"
)
REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT: str = (
    "SOURCE_RECONCILIATION_PRICE_DISAGREEMENT"
)
REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT: str = (
    "SOURCE_RECONCILIATION_TIME_DISAGREEMENT"
)
REASON_CODE_SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE: str = (
    "SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE"
)
REASON_CODE_SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED: str = (
    "SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED"
)
REASON_CODE_SOURCE_RECONCILIATION_NULL_PEAK_TIME: str = (
    "SOURCE_RECONCILIATION_NULL_PEAK_TIME"
)
REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES: str = (
    "ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES"
)
REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE: str = (
    "ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE"
)
REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT: str = (
    "ATH_MEASUREMENT_SOURCE_CONFLICT"
)
REASON_CODE_ATH_MEASUREMENT_MISSING_NO_SOURCES: str = (
    "ATH_MEASUREMENT_MISSING_NO_SOURCES"
)
REASON_CODE_ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION: str = (
    "ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION"
)
REASON_CODE_ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION: str = (
    "ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION"
)
REASON_CODE_ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES: str = (
    "ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES"
)
REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR: str = (
    "ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR"
)
REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED: str = (
    "ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED"
)


REASON_CODES: tuple[str, ...] = (
    REASON_CODE_PRICE_OBSERVED_ZERO,
    REASON_CODE_MIGRATION_NO_OBSERVATIONS,
    REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
    REASON_CODE_MIGRATION_SINGLE_SOURCE,
    REASON_CODE_MIGRATION_SOURCES_AGREED,
    REASON_CODE_MIGRATION_SOURCES_DISAGREED,
    REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT,
    REASON_CODE_MIGRATION_BLOCK_TIME_MISSING,
    REASON_CODE_MIGRATION_SIGNATURE_MISSING,
    REASON_CODE_MIGRATION_SLOT_MISSING,
    REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
    REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED,
    REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED,
    REASON_CODE_PRICE_OBSERVATION_DUPLICATE_COLLAPSED,
    REASON_CODE_PRICE_OBSERVATION_NO_PRICE,
    REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT,
    REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS,
    REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED,
    REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION,
    REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING,
    REASON_CODE_PRICE_WINDOW_TOKEN_MISMATCH_REJECTED,
    REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED,
    REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS,
    REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK,
    REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA,
    REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS,
    REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED,
    REASON_CODE_ATH_CANDIDATE_TOKEN_SOURCE_MISMATCH_REJECTED,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR,
    REASON_CODE_SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE,
    REASON_CODE_SOURCE_RECONCILIATION_INSUFFICIENT_DATA,
    REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT,
    REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT,
    REASON_CODE_SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE,
    REASON_CODE_SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED,
    REASON_CODE_SOURCE_RECONCILIATION_NULL_PEAK_TIME,
    REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE,
    REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT,
    REASON_CODE_ATH_MEASUREMENT_MISSING_NO_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION,
    REASON_CODE_ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION,
    REASON_CODE_ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR,
    REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED,
)


# ---------------------------------------------------------------------------
# Tolerance / sentinel constants
# ---------------------------------------------------------------------------


# Reconciliation tolerance between two sources' migration block
# times before they are recorded as DISAGREED_MINOR / DISAGREED_MAJOR.
# Stage 25.1 ships the value; future reconcilers consume it.
MIGRATION_TIMESTAMP_TOLERANCE_SECONDS: int = 60

# Reconciliation tolerance between two sources' ATH peak times
# before they are recorded as DISAGREED_MINOR / DISAGREED_MAJOR.
PEAK_TIME_TOLERANCE_SECONDS: int = 120

# Parts-per-million tolerance between two sources' reported peak
# prices before they are recorded as DISAGREED_MINOR / DISAGREED_MAJOR.
PRICE_DISAGREEMENT_TOLERANCE_PPM: int = 50_000

# Stage 25.5 source-reconciliation major-disagreement thresholds.
# When two sources' reported peak prices / peak times exceed the
# MAJOR threshold the reconciliation refuses to record either source
# as ``MEASURED`` and instead emits a SOURCE_CONFLICT outcome. When
# the disagreement exceeds the MINOR tolerance but stays under MAJOR
# the reconciliation records ``DISAGREED_MINOR`` (no measured peak).
PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM: int = 250_000
PEAK_TIME_MAJOR_TOLERANCE_SECONDS: int = 600

# Duration of the post-migration primary ATH window in seconds.
# Stage 25.1 ships the value; future window projectors consume it.
POST_MIGRATION_PRIMARY_WINDOW_SECONDS: int = 6 * 3600

# Long-hex-run threshold for the value-shape leak detector. A
# value containing a contiguous run of >= 40 hex characters is
# rejected by the input reader as a credential / API-key shape.
STAGE25_LONG_HEX_RUN_MIN_LEN: int = 40


# ---------------------------------------------------------------------------
# Stage 25 forbidden routing tokens (locally re-declared)
# ---------------------------------------------------------------------------
#
# Stage 25 inherits the prior-stage prohibition against
# subscriber / public / paid routing and re-declares the locked
# tuple locally so the Stage 25 routing-scan boundary test does
# not need to reach into prior stages. Stage 25 does NOT route --
# it emits evidence.


STAGE25_FORBIDDEN_ROUTING_TOKENS: tuple[str, ...] = (
    "subscriber",
    "subscribers",
    "subscriber_channel",
    "public_channel",
    "public_signal",
    "public_dispatch",
    "paid_signal",
    "paid_signals",
    "paid_channel",
    "paid_dispatch",
)


# ---------------------------------------------------------------------------
# Stage 25 forbidden vocabulary (boundary scanner input)
# ---------------------------------------------------------------------------
#
# Identifier-position substrings the Stage 25 production source
# MUST NOT define. These are concerns that belong to strictly
# later stages or are forever forbidden in Stage 25:
#
#   * ``dispatch`` / ``telegram`` -- transport / routing concerns.
#   * ``scheduler`` / ``daemon`` / ``worker`` / ``run_loop`` --
#     long-running infra (out of scope).
#   * ``x_api`` / ``social`` -- Stage 27+ social-intelligence
#     sidecar.
#
# IMPORTANT: Stage 25's domain vocabulary -- ``migration`` /
# ``birdeye`` / ``dexscreener`` / ``ath`` / ``peak`` / ``source`` /
# ``reconciliation`` / ``candidate`` / ``price`` / ``window`` /
# ``measurement`` / ``observation`` / ``swap_replay`` -- is
# deliberately OMITTED from this tuple because these are the
# Stage 25 vocabulary.
#
# The boundary scanner consumes this tuple against AST identifier
# positions only, so docstring / comment phrases like
# "ambiguous migration blocks measured ATH" do not trigger the
# scanner.


STAGE25_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    "dispatch",
    "telegram",
    "scheduler",
    "daemon",
    "worker",
    "run_loop",
    "x_api",
    "social",
)


# ---------------------------------------------------------------------------
# Stage 24 execution-fee vocabulary forbidden in Stage 25
# ---------------------------------------------------------------------------
#
# Stage 25 must NOT introduce Stage 24 execution-fee logic. The
# identifier-position substrings below are the Stage 24 execution-
# fee tokens; the boundary scanner refuses any Stage 25
# production identifier that contains them.


STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY: tuple[str, ...] = (
    "axiom",
    "jito",
    "compute_budget",
    "router_fee",
)


# ---------------------------------------------------------------------------
# Stage 25 input-reader redaction discipline
# ---------------------------------------------------------------------------
#
# Field-name substrings that, if seen on an input row, cause the
# reader to reject the row with ``Stage25InputError``. Mirrors
# the Stage 22 / 23 / 24 second-line-of-defense pattern: if an
# upstream artifact ever leaks a secret-bearing field, Stage 25
# refuses to ingest it rather than passing it through.


STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "webhook_url",
    "webhook",
    "rpc_url",
    "raw_response_body",
    "raw_response",
    "response_body",
    "exception_message",
    "exception_repr",
    "exception_args",
    "headers",
    "authorization",
    "bearer",
    "password",
    "secret",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
)


# URL-scheme fragments and webhook host literals are constructed
# at runtime via string concatenation so the literal substrings
# the Stage 25 boundary scanner forbids never appear in this
# source file. Mirrors the Stage 24 pattern.


_COLON_SLASH_SLASH: str = ":" + "//"
_HTTP_SCHEME: str = "http" + _COLON_SLASH_SLASH
_HTTPS_SCHEME: str = "https" + _COLON_SLASH_SLASH
_WS_SCHEME: str = "ws" + _COLON_SLASH_SLASH
_WSS_SCHEME: str = "wss" + _COLON_SLASH_SLASH

_DOT_COM: str = "." + "com"
_DISCORD_HOST: str = "dis" + "cord" + _DOT_COM
_DISCORDAPP_HOST: str = "dis" + "cordapp" + _DOT_COM
_HOOKS_SLACK_HOST: str = "hooks" + ".sl" + "ack" + _DOT_COM


# Substrings the input reader rejects anywhere inside a value of
# a preserved row field (case-insensitive). The colon-slash-slash
# entry catches URL prefixes that drop the scheme as well as the
# concrete schemes.


STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS: tuple[str, ...] = (
    _HTTP_SCHEME,
    _HTTPS_SCHEME,
    _WS_SCHEME,
    _WSS_SCHEME,
    _COLON_SLASH_SLASH,
    _DISCORD_HOST,
    _DISCORDAPP_HOST,
    _HOOKS_SLACK_HOST,
)


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------
#
# Stage 25.1 keeps these as plain ``ValueError``-raising
# predicates in this module. The Stage 25 model / manifest / input
# reader modules import them; the modules themselves raise the
# Stage 25-typed error subclass after catching the ``ValueError``
# if a typed error is required.
#
# The motivation for keeping the assertion helpers here (rather
# than re-implementing the membership check in every model
# constructor) is so every closed-set surface speaks the same
# error vocabulary and the boundary scanner only has to inspect
# this single module's source for closed-set drift.


class _Stage25ClosedSetError(ValueError):
    """Module-local sentinel raised by the closed-set helpers.

    Re-raised as a Stage 25-typed error by the caller after
    catching the assertion failure. Stage 25.1 callers in the
    ``models`` / ``input_reader`` / ``stage25_manifest`` modules
    convert this into ``Stage25ContractError`` /
    ``Stage25InputError`` / ``Stage25ManifestError`` as
    appropriate.
    """


def _assert_in_closed_set(
    *,
    field_name: str,
    value: str,
    members: tuple[str, ...],
) -> None:
    if value not in members:
        raise _Stage25ClosedSetError(
            f"{field_name} {value!r} is not a closed-set Stage 25 "
            f"{field_name}"
        )


def assert_measurement_family_in_closed_set(measurement_family: str) -> None:
    _assert_in_closed_set(
        field_name="measurement_family",
        value=measurement_family,
        members=MEASUREMENT_FAMILIES,
    )


def assert_source_family_in_closed_set(source_family: str) -> None:
    _assert_in_closed_set(
        field_name="source_family",
        value=source_family,
        members=SOURCE_FAMILIES,
    )


def assert_source_status_in_closed_set(source_status: str) -> None:
    _assert_in_closed_set(
        field_name="source_status",
        value=source_status,
        members=SOURCE_STATUSES,
    )


def assert_measurement_status_in_closed_set(measurement_status: str) -> None:
    _assert_in_closed_set(
        field_name="measurement_status",
        value=measurement_status,
        members=MEASUREMENT_STATUSES,
    )


def assert_confidence_level_in_closed_set(confidence_level: str) -> None:
    _assert_in_closed_set(
        field_name="confidence_level",
        value=confidence_level,
        members=CONFIDENCE_LEVELS,
    )


def assert_rejection_reason_in_closed_set(rejection_reason: str) -> None:
    _assert_in_closed_set(
        field_name="rejection_reason",
        value=rejection_reason,
        members=REJECTION_REASONS,
    )


def assert_price_window_kind_in_closed_set(window_kind: str) -> None:
    _assert_in_closed_set(
        field_name="window_kind",
        value=window_kind,
        members=PRICE_WINDOW_KINDS,
    )


def assert_ath_candidate_kind_in_closed_set(candidate_kind: str) -> None:
    _assert_in_closed_set(
        field_name="candidate_kind",
        value=candidate_kind,
        members=ATH_CANDIDATE_KINDS,
    )


def assert_reconciliation_status_in_closed_set(
    reconciliation_status: str,
) -> None:
    _assert_in_closed_set(
        field_name="reconciliation_status",
        value=reconciliation_status,
        members=RECONCILIATION_STATUSES,
    )


def assert_quote_denomination_in_closed_set(
    quote_denomination: str,
) -> None:
    _assert_in_closed_set(
        field_name="quote_denomination",
        value=quote_denomination,
        members=QUOTE_DENOMINATIONS,
    )


def assert_input_kind_in_closed_set(input_kind: str) -> None:
    _assert_in_closed_set(
        field_name="input_kind",
        value=input_kind,
        members=INPUT_KINDS,
    )


# ---------------------------------------------------------------------------
# Optional / sentinel int assertions
# ---------------------------------------------------------------------------


def assert_optional_non_negative_int(
    *,
    field_name: str,
    value: object,
) -> None:
    """Raise ``_Stage25ClosedSetError`` unless ``value`` is ``None`` or a
    non-negative ``int`` (excluding ``bool``).

    Stage 25's price / amount fields encode "unknown" as ``None``
    and a real observed value as a non-negative int. A negative
    value is a contract violation; ``0`` is permitted only with an
    explicit reason code (caller enforces the reason-code
    invariant separately).
    """
    if value is None:
        return
    if isinstance(value, bool):
        raise _Stage25ClosedSetError(
            f"{field_name}: bool is not a valid optional non-negative int"
        )
    if not isinstance(value, int):
        raise _Stage25ClosedSetError(
            f"{field_name}: expected int or None, got "
            f"{type(value).__name__}"
        )
    if value < 0:
        raise _Stage25ClosedSetError(
            f"{field_name}: must be >= 0 or None"
        )


def assert_non_negative_int_or_minus_one_sentinel(
    *,
    field_name: str,
    value: object,
) -> None:
    """Raise ``_Stage25ClosedSetError`` unless ``value`` is a strict
    ``int`` (excluding ``bool``) that is either ``-1`` or
    non-negative.

    Stage 25 uses ``-1`` as the "absent" sentinel for slot /
    block-time fields so a ``NamedTuple`` field can keep its
    ``int`` annotation without admitting ``None`` (which would
    break the deterministic canonical-JSON contract on records
    whose hashes cover those fields).
    """
    if isinstance(value, bool):
        raise _Stage25ClosedSetError(
            f"{field_name}: bool is not a valid int"
        )
    if not isinstance(value, int):
        raise _Stage25ClosedSetError(
            f"{field_name}: expected int, got {type(value).__name__}"
        )
    if value < -1:
        raise _Stage25ClosedSetError(
            f"{field_name}: must be -1 (absent sentinel) or >= 0"
        )


# ---------------------------------------------------------------------------
# Stage 25.6 locked artifact filenames
# ---------------------------------------------------------------------------
#
# Filenames the Stage 25.6 deterministic writer emits into the
# operator-supplied output directory. Locked here so downstream
# readers can rely on basenames without re-deriving them at the
# writer surface.


STAGE25_MIGRATION_OBSERVATIONS_FILENAME: str = (
    "stage25_migration_observations.jsonl"
)
STAGE25_MIGRATION_MEASUREMENTS_FILENAME: str = (
    "stage25_migration_measurements.jsonl"
)
STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME: str = (
    "stage25_price_window_observations.jsonl"
)
STAGE25_ATH_CANDIDATES_FILENAME: str = "stage25_ath_candidates.jsonl"
STAGE25_SOURCE_RECONCILIATIONS_FILENAME: str = (
    "stage25_source_reconciliations.jsonl"
)
STAGE25_ATH_MEASUREMENTS_FILENAME: str = "stage25_ath_measurements.jsonl"
STAGE25_MEASUREMENT_REJECTIONS_FILENAME: str = (
    "stage25_measurement_rejections.jsonl"
)
STAGE25_SUMMARY_FILENAME: str = "stage25_summary.json"
STAGE25_MANIFEST_FILENAME: str = "stage25_manifest.json"


STAGE25_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_MANIFEST_FILENAME,
)


# Stage 25.6 does NOT emit the optional source-coverage CSV. The
# decision is locked here so future sub-stages cannot silently
# enable it; future sub-stages flipping the flag MUST update the
# Stage 25.6 boundary tests at the same time.
STAGE25_EMITS_SOURCE_COVERAGE_CSV: bool = False


__all__ = [
    "ATH_CANDIDATE_KINDS",
    "ATH_CANDIDATE_KIND_COMBINED_PEAK",
    "ATH_CANDIDATE_KIND_INSUFFICIENT_DATA",
    "ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK",
    "ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK",
    "CONFIDENCE_LEVELS",
    "CONFIDENCE_LEVEL_HIGH",
    "CONFIDENCE_LEVEL_LOW",
    "CONFIDENCE_LEVEL_MEDIUM",
    "CONFIDENCE_LEVEL_NONE",
    "DEFAULT_SCHEMA_VERSION",
    "DEFAULT_THRESHOLD_VERSION",
    "INPUT_KINDS",
    "INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL",
    "INPUT_KIND_PRICE_OBSERVATIONS_JSONL",
    "INPUT_KIND_SANITIZED_REAL_MIGRATION_OBSERVATIONS_JSONL",
    "INPUT_KIND_SANITIZED_REAL_PRICE_OBSERVATIONS_JSONL",
    "INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL",
    "INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL",
    "MEASUREMENT_FAMILIES",
    "MEASUREMENT_FAMILY_ATH",
    "MEASUREMENT_FAMILY_MIGRATION",
    "MEASUREMENT_STATUSES",
    "MEASUREMENT_STATUS_AMBIGUOUS",
    "MEASUREMENT_STATUS_MEASURED",
    "MEASUREMENT_STATUS_MISSING",
    "MEASUREMENT_STATUS_NOT_APPLICABLE",
    "MEASUREMENT_STATUS_PARTIAL",
    "MEASUREMENT_STATUS_REJECTED",
    "MEASUREMENT_STATUS_SOURCE_CONFLICT",
    "MEASUREMENT_STATUS_UNSUPPORTED",
    "MIGRATION_OBSERVATION_INPUT_KINDS",
    "MIGRATION_TIMESTAMP_TOLERANCE_SECONDS",
    "OBSERVE_ONLY_MODE",
    "PEAK_TIME_MAJOR_TOLERANCE_SECONDS",
    "PEAK_TIME_TOLERANCE_SECONDS",
    "POST_MIGRATION_PRIMARY_WINDOW_SECONDS",
    "PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM",
    "PRICE_DISAGREEMENT_TOLERANCE_PPM",
    "PRICE_OBSERVATION_INPUT_KINDS",
    "PRICE_WINDOW_KINDS",
    "PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED",
    "PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY",
    "PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED",
    "PRICE_WINDOW_KIND_UNKNOWN_WINDOW",
    "QUOTE_DENOMINATIONS",
    "QUOTE_DENOMINATION_SOL_LAMPORTS",
    "QUOTE_DENOMINATION_UNKNOWN_QUOTE",
    "QUOTE_DENOMINATION_USD_MICRO",
    "REASON_CODES",
    "REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA",
    "REASON_CODE_ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION",
    "REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES",
    "REASON_CODE_ATH_MEASUREMENT_MISSING_NO_SOURCES",
    "REASON_CODE_ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION",
    "REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR",
    "REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE",
    "REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT",
    "REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED",
    "REASON_CODE_ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES",
    "REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS",
    "REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS",
    "REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED",
    "REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS",
    "REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED",
    "REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK",
    "REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK",
    "REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED",
    "REASON_CODE_ATH_CANDIDATE_TOKEN_SOURCE_MISMATCH_REJECTED",
    "REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED",
    "REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS",
    "REASON_CODE_MIGRATION_BLOCK_TIME_MISSING",
    "REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED",
    "REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES",
    "REASON_CODE_MIGRATION_NO_OBSERVATIONS",
    "REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT",
    "REASON_CODE_MIGRATION_SIGNATURE_MISSING",
    "REASON_CODE_MIGRATION_SINGLE_SOURCE",
    "REASON_CODE_MIGRATION_SLOT_MISSING",
    "REASON_CODE_MIGRATION_SOURCES_AGREED",
    "REASON_CODE_MIGRATION_SOURCES_DISAGREED",
    "REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED",
    "REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS",
    "REASON_CODE_PRICE_OBSERVATION_DUPLICATE_COLLAPSED",
    "REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS",
    "REASON_CODE_PRICE_OBSERVATION_NO_PRICE",
    "REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT",
    "REASON_CODE_PRICE_OBSERVED_ZERO",
    "REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS",
    "REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED",
    "REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING",
    "REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS",
    "REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED",
    "REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY",
    "REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED",
    "REASON_CODE_PRICE_WINDOW_TOKEN_MISMATCH_REJECTED",
    "REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION",
    "REASON_CODE_SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE",
    "REASON_CODE_SOURCE_RECONCILIATION_INSUFFICIENT_DATA",
    "REASON_CODE_SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE",
    "REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES",
    "REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES",
    "REASON_CODE_SOURCE_RECONCILIATION_NULL_PEAK_TIME",
    "REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT",
    "REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL",
    "REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED",
    "REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR",
    "REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR",
    "REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT",
    "REASON_CODE_SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED",
    "RECONCILIATION_STATUSES",
    "RECONCILIATION_STATUS_AGREED",
    "RECONCILIATION_STATUS_AMBIGUOUS",
    "RECONCILIATION_STATUS_DISAGREED_MAJOR",
    "RECONCILIATION_STATUS_DISAGREED_MINOR",
    "RECONCILIATION_STATUS_NO_SOURCES",
    "RECONCILIATION_STATUS_SINGLE_SOURCE",
    "REDACTION_CONFIRMED_TOKEN",
    "REJECTION_REASONS",
    "REJECTION_REASON_DUPLICATE_OBSERVATION",
    "REJECTION_REASON_FORBIDDEN_FIELD_SUBSTRING",
    "REJECTION_REASON_FORBIDDEN_VALUE_SUBSTRING",
    "REJECTION_REASON_INPUT_MALFORMED",
    "REJECTION_REASON_LONG_HEX_RUN_DETECTED",
    "REJECTION_REASON_MIGRATION_AMBIGUOUS_PROHIBITS_ATH",
    "REJECTION_REASON_NEGATIVE_PRICE",
    "REJECTION_REASON_NON_FINITE_PRICE",
    "REJECTION_REASON_NULL_REQUIRES_EXPLICIT_STATUS",
    "REJECTION_REASON_PRE_MIGRATION_OBSERVATION_USED_FOR_ATH",
    "REJECTION_REASON_SOURCE_BUILDER_TYPED_ERROR",
    "REJECTION_REASON_UNKNOWN_INPUT_KIND",
    "REJECTION_REASON_UNKNOWN_SOURCE_FAMILY",
    "REJECTION_REASON_ZERO_PRICE_WITHOUT_EXPLICIT_OBSERVED_ZERO",
    "SOURCE_FAMILIES",
    "SOURCE_FAMILY_BIRDEYE",
    "SOURCE_FAMILY_DEXSCREENER",
    "SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY",
    "SOURCE_FAMILY_UNKNOWN_SOURCE",
    "SOURCE_FAMILY_WEBSOCKET_CAPTURE",
    "SOURCE_STATUSES",
    "SOURCE_STATUS_ABSENT",
    "SOURCE_STATUS_AMBIGUOUS",
    "SOURCE_STATUS_DECODE_FAILED",
    "SOURCE_STATUS_MALFORMED",
    "SOURCE_STATUS_PARTIAL",
    "SOURCE_STATUS_PRESENT",
    "SOURCE_STATUS_UNSUPPORTED",
    "STAGE25_ARTIFACT_FILENAMES",
    "STAGE25_ARTIFACT_WRITER_NAME",
    "STAGE25_ARTIFACT_WRITER_VERSION",
    "STAGE25_ATH_CANDIDATES_FILENAME",
    "STAGE25_ATH_CANDIDATE_VERSION",
    "STAGE25_ATH_MEASUREMENTS_FILENAME",
    "STAGE25_ATH_MEASUREMENT_VERSION",
    "STAGE25_ATH_MEASURER_NAME",
    "STAGE25_EMITS_SOURCE_COVERAGE_CSV",
    "STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS",
    "STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS",
    "STAGE25_FORBIDDEN_ROUTING_TOKENS",
    "STAGE25_FORBIDDEN_STAGE24_EXECUTION_FEE_VOCABULARY",
    "STAGE25_FORBIDDEN_VOCABULARY",
    "STAGE25_LONG_HEX_RUN_MIN_LEN",
    "STAGE25_MANIFEST_FILENAME",
    "STAGE25_MANIFEST_SCHEMA_VERSION",
    "STAGE25_MEASUREMENT_REJECTIONS_FILENAME",
    "STAGE25_MIGRATION_MEASUREMENTS_FILENAME",
    "STAGE25_MIGRATION_MEASURER_NAME",
    "STAGE25_MIGRATION_MEASURER_VERSION",
    "STAGE25_MIGRATION_OBSERVATIONS_FILENAME",
    "STAGE25_MIGRATION_OBSERVATION_VERSION",
    "STAGE25_MINOR_VERSION",
    "STAGE25_PRICE_OBSERVATION_VERSION",
    "STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME",
    "STAGE25_PRICE_WINDOW_VERSION",
    "STAGE25_RUNNER_NAME",
    "STAGE25_RUNNER_VERSION",
    "STAGE25_SOURCE_RECONCILIATIONS_FILENAME",
    "STAGE25_SOURCE_RECONCILIATION_VERSION",
    "STAGE25_SUMMARY_FILENAME",
    "STAGE25_SUMMARY_VERSION",
    "STAGE25_VERSION",
    "STAGE25_WRITER_NAME",
    "STAGE25_WRITER_VERSION",
    "STAGE_NAME",
    "STAGE_VERSION",
    "_Stage25ClosedSetError",
    "assert_ath_candidate_kind_in_closed_set",
    "assert_confidence_level_in_closed_set",
    "assert_input_kind_in_closed_set",
    "assert_measurement_family_in_closed_set",
    "assert_measurement_status_in_closed_set",
    "assert_non_negative_int_or_minus_one_sentinel",
    "assert_optional_non_negative_int",
    "assert_price_window_kind_in_closed_set",
    "assert_quote_denomination_in_closed_set",
    "assert_reconciliation_status_in_closed_set",
    "assert_rejection_reason_in_closed_set",
    "assert_source_family_in_closed_set",
    "assert_source_status_in_closed_set",
]
