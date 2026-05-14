"""Stage 19 locked constants.

All schema versions, file names, label vocabularies, column tuples,
and length caps that govern the Stage 19 operator-review-ledger
build live here. The Stage 18 column tuples and field names that
Stage 19 consumes are duplicated verbatim from Stage 18's writers /
manifest so Stage 19 can validate input shape without importing
``PHX2.stage18``; this matches the locked import-boundary policy
(Stage 19 is forbidden from importing any ``PHX2.stage17`` or
``PHX2.stage18`` module).

Cross-stage column-name renames (locked, intentional namespacing):

  * Operator-input column ``stage18_run_id`` maps to Stage 18's
    flat manifest key ``run_id``. Readers extract
    ``manifest["run_id"]`` and compare against the operator-input
    ``stage18_run_id`` value. The rename disambiguates from
    ``stage19_run_id`` (the run id of the Stage 19 invocation
    itself, recorded in Stage 19's own ledger and manifest).
  * Stage 19 ledger column ``stage18_classification`` maps to
    Stage 18's ``review_matrix.csv`` source column
    ``classification``. Readers extract from source key
    ``classification``; writers emit under namespaced ledger key
    ``stage18_classification``. The rename disambiguates from any
    future Stage 19-introduced classification field and makes the
    ledger self-describing about which stage produced the value.

Per-row vs. per-run inputs:

  * The operator-input CSV (``operator_review_input.csv``)
    contains exactly six columns: ``stage18_run_id``,
    ``policy_hash``, ``rule_id``, ``window_seconds``,
    ``review_label``, ``review_notes``. ``operator_id`` is **not**
    a CSV column -- it is a single CLI scalar passed once per
    Stage 19 invocation via ``--operator-id`` and stamped onto
    every ledger row produced by that run. Likewise the run-level
    ``stage19_run_id`` and ``review_timestamp_utc`` fields are
    derived per-run, not per CSV row.

Stage 19 is observe-only: it records human review judgments
against Stage 18 review packets and emits a ledger CSV plus one
summary CSV. It performs no enforcement, no policy mutation, no
promotion, no threshold tuning, no dashboards, no daemons or
schedulers, no model training, and no pings of any kind. The
six review labels in ``LABELS`` are review judgments only -- they
are not activation commands.

v0 simplifications:

  * Exactly one summary file: ``operator_review_summary.csv``. No
    cross-operator-latest summary in v0; that artifact is dropped.
  * ``operator_id`` is canonicalized by stripping leading and
    trailing whitespace before validation; the stripped form is
    the value emitted in the ledger and summary.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 19 versions
# ---------------------------------------------------------------------------


STAGE19_VERSION: str = "0.1.0"
STAGE19_SCHEMA_VERSION: str = "stage19_ledger_v1"


# ---------------------------------------------------------------------------
# Stage 18 pinned constants (verified at STEP 0 against Stage 18 source)
# ---------------------------------------------------------------------------
#
# These three values are the contract between Stage 18 outputs and
# Stage 19 inputs. They are intentionally hand-duplicated rather
# than imported across the stage boundary so:
#
#   * Stage 19 satisfies its hard import-boundary policy
#     (stdlib + PHX2.stage19 only).
#   * Drift in Stage 18's writer or manifest emitter produces a
#     loud E04 / E05 / E07 in Stage 19 rather than a silent
#     re-aliasing.
#
# If Stage 18 bumps its manifest schema or column tuple, these
# constants must be re-pinned and Stage 19's tests refreshed.


STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION: str = "stage18_run_manifest_v0"

STAGE18_MANIFEST_RUN_ID_KEY: str = "run_id"

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
# Required Stage 18 input artifacts (Stage 19 reads these)
# ---------------------------------------------------------------------------


STAGE18_MANIFEST_FILENAME: str = "manifest.json"
STAGE18_REVIEW_MATRIX_FILENAME: str = "review_matrix.csv"

REQUIRED_STAGE18_INPUT_FILES: tuple[str, ...] = (
    STAGE18_MANIFEST_FILENAME,
    STAGE18_REVIEW_MATRIX_FILENAME,
)


# ---------------------------------------------------------------------------
# Operator review-label vocabulary (locked, six labels in locked order)
# ---------------------------------------------------------------------------
#
# These are the only string literals Stage 19 will accept in the
# ``review_label`` column of the operator-input CSV (case
# sensitive, no whitespace tolerance). Any other value is an E09
# violation in the validators (Phase 19.2).
#
# These labels are review judgments only; they are not
# activation commands. Stage 19 records them and never acts on
# them.


LABELS: tuple[str, ...] = (
    "REVIEW_PROMISING_CONFIRMED",
    "REVIEW_HARMFUL_CONFIRMED",
    "REVIEW_REJECTED",
    "WATCHLIST",
    "NEEDS_MORE_DATA",
    "INCONCLUSIVE",
)


# ---------------------------------------------------------------------------
# Operator-input CSV column tuple (locked, six columns)
# ---------------------------------------------------------------------------
#
# Header that ``operator_review_input.csv`` must match exactly
# (order, spelling, case). Validated by readers (Phase 19.2)
# against this tuple; any mismatch is an E07 violation.
#
# ``operator_id`` is intentionally absent: it is a CLI scalar
# (``--operator-id``), not a per-row CSV column, so a single
# Stage 19 run records exactly one operator's reviews.


OPERATOR_INPUT_COLUMNS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "review_label",
    "review_notes",
)


# ---------------------------------------------------------------------------
# Stage 19 ledger CSV column tuple (locked, thirteen columns)
# ---------------------------------------------------------------------------
#
# The ledger pairs each operator review judgment with the upstream
# Stage 18 evidence, the run-level identifiers
# (``stage19_run_id``, ``review_timestamp_utc``), and the per-row
# bookkeeping (``ledger_row_id``, ``review_sequence``).
#
# Field provenance:
#   * stage19_run_id            -- per Stage 19 run, not per row
#   * ledger_row_id             -- deterministic SHA-256 prefix
#                                  (Phase 19.2 derivation)
#   * stage18_run_id            -- from operator input row
#   * policy_hash, rule_id,
#     window_seconds            -- from operator input row
#   * operator_id               -- CLI scalar (--operator-id)
#   * review_sequence           -- per (slice, operator) chain
#                                  from prior ledger
#   * review_label              -- from operator input row
#   * review_notes              -- from operator input row
#   * review_timestamp_utc      -- CLI scalar (--run-timestamp)
#   * stage18_classification    -- from review_matrix source
#                                  column ``classification``
#                                  (namespaced rename)
#   * stage17_label_preserved   -- from review_matrix verbatim


LEDGER_COLUMNS: tuple[str, ...] = (
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


# ---------------------------------------------------------------------------
# Operator-review summary CSV column tuple (locked, eleven columns)
# ---------------------------------------------------------------------------
#
# v0 emits exactly one summary file: ``operator_review_summary.csv``.
# One row per ``(stage18_run_id, policy_hash, rule_id,
# window_seconds, operator_id)`` tuple, selecting the row with
# MAX(review_sequence) within each group as the "current" review
# state. The summary is **not** a count aggregation, **not**
# grouped only by operator_id, and **not** a cross-operator
# consensus file (cross-operator reconciliation is deferred to
# Stage 20+).
#
# Fields prefixed ``current_`` are the values from the
# max-sequence row in the ledger; the unprefixed slice/operator
# fields are the grouping key.


SUMMARY_COLUMNS: tuple[str, ...] = (
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


# ---------------------------------------------------------------------------
# Stage 19 file names (input + output artifacts)
# ---------------------------------------------------------------------------


OPERATOR_INPUT_FILENAME: str = "operator_review_input.csv"
LEDGER_FILENAME: str = "operator_review_ledger.csv"
SUMMARY_FILENAME: str = "operator_review_summary.csv"
MANIFEST_FILENAME: str = "manifest.json"
README_FILENAME: str = "README.md"
RUN_LOG_FILENAME: str = "stage19_run.log"


# ---------------------------------------------------------------------------
# Length caps on operator-supplied free-text fields
# ---------------------------------------------------------------------------
#
# Caps apply after the v0 strip canonicalization on
# ``operator_id``. ``review_notes`` is not stripped (whitespace
# inside a note is meaningful), but the cap is enforced on the
# raw cell value as read.


MAX_OPERATOR_ID_LENGTH: int = 64
MAX_REVIEW_NOTES_LENGTH: int = 2000


__all__ = [
    "LABELS",
    "LEDGER_COLUMNS",
    "LEDGER_FILENAME",
    "MANIFEST_FILENAME",
    "MAX_OPERATOR_ID_LENGTH",
    "MAX_REVIEW_NOTES_LENGTH",
    "OPERATOR_INPUT_COLUMNS",
    "OPERATOR_INPUT_FILENAME",
    "README_FILENAME",
    "REQUIRED_STAGE18_INPUT_FILES",
    "RUN_LOG_FILENAME",
    "STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION",
    "STAGE18_MANIFEST_FILENAME",
    "STAGE18_MANIFEST_RUN_ID_KEY",
    "STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS",
    "STAGE18_REVIEW_MATRIX_FILENAME",
    "STAGE19_SCHEMA_VERSION",
    "STAGE19_VERSION",
    "SUMMARY_COLUMNS",
    "SUMMARY_FILENAME",
]
