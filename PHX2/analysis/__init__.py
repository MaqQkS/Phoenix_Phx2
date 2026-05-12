"""PHX2 Stage 12 decision_outcome_analysis package.

This package is an offline, read-only analysis layer that joins
alert_decisions, filter_evaluations, decision_score_features, and
outcome_windows at the alert_decision_id level and emits an immutable
run directory of long-format and cohort summary CSVs plus manifest.json
and README.md.

L1-L8 substrate locks (see Stage 12 Locked Design Spec):
  * Opens the PHX2 SQLite DB read-only (sqlite3 URI mode=ro).
  * Writes nothing to substrate, runtime, or analysis tables.
  * Reads only from alert_decisions, filter_evaluations,
    decision_score_features, outcome_windows (analytical) plus optional
    display-only join to token_sequence_state.symbol.
  * Performs no network I/O.
  * Runs no significance tests.
  * Produces no scores.
  * Influences no policy.
"""
