# PHX2 Roadmap and Stage History

This document is a factual roadmap for PHX2 stages 0-14, with proposed
future stages clearly separated from implemented work.

## Source Notes

Sources inspected for this write-up:

- `git log --oneline --decorate`
- `git status --short`
- `PHX2/` directory structure
- `PHX2/README.md`, `PHX2/SAFETY.md`, and committed Stage 14 source/tests
- stage folders: `PHX2/analysis`, `PHX2/stage13`, `PHX2/stage14`
- service folders: `PHX2/services`, `PHX2/filters`, `PHX2/renderers`, `PHX2/dispatch`
- tests and fixtures under `PHX2/tests`
- schema constants and migration entry points in `PHX2/db/migrations.py`
- relevant module docstrings and writer/loader constants

Accuracy note: the local git history begins at commit `01cffa3`, titled
`Stage 6.5: relocate PHX2 to its own sibling directory`. Older stage
implementation commits for stages 0-6 are not present in this repository.
Where an older stage is described from current files rather than original
stage commits, it is marked `inferred`. Where the purpose is not present in
code, tests, docs, or commit messages, it is marked `Needs confirmation`.

## Project Overview

PHX2 is a staged Phoenix fork that builds an offline and auditable policy
pipeline before live alert enforcement.

The project separates historical evidence gathering from recommendation,
offline replay, human approval, live observe-only telemetry, and any eventual
limited enforcement. The recent Stage 12-14 chain is deliberately artifact
driven: Stage 12 explains what happened historically, Stage 13 identifies
evidence-supported policy candidates, Stage 13.1 makes candidate identity
explicit, and Stage 14 replays those candidates offline to ask what would
have changed historically.

## Status Legend

- `done`: supported by a local commit, explicit code/docs, and tests.
- `inferred`: supported by current code/docs/tests, but the original stage
  commit is not in local history.
- `partial`: evidence exists for part of the stage, but the stage boundary is
  incomplete or mixed with another stage.
- `unknown`: the repo does not contain enough evidence to describe the stage
  without guessing.
- `Needs confirmation`: the exact purpose, commit, or scope should be
  confirmed from external notes or missing history.

## Stage Table

| Stage | Stage name | Status | Commit hash if known | Purpose | Main inputs | Main outputs | DB touch | Live alert behavior | Test coverage / verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Boundary and safety scaffold | inferred | Needs confirmation; mentioned in `PHX2/README.md` and `PHX2/SAFETY.md` | Establish Phoenix1 isolation and dry-run-first boundaries before behavior. | None confirmed. | Safety contract and staged-project intent. | No DB touch confirmed. | No. | Documentation only; exact commit needs confirmation. |
| 1 | Package/import scaffold | done | Present by `01cffa3`; original stage commit unavailable | Create inert PHX2 package boundaries and placeholder modules. | None. | Importable package, placeholder services, integration clients, scripts. | No. | No. | `PHX2/tests/test_imports.py`; placeholder docstrings. |
| 2 | Typed settings and DB connection boundaries | done | Present by `01cffa3`; original stage commit unavailable | Define typed dry-run settings and separate Phoenix1 read-only vs PHX2 dry-run DB access. | Config defaults and database paths. | `PHX2Settings`, read-only Phoenix1 helper, PHX2 dry-run connection helper. | Opens connections only; creates no schema. | No. | `PHX2/tests/test_settings.py`, `PHX2/tests/test_db_connection.py`. |
| 3 | Needs confirmation | unknown | Needs confirmation | Needs confirmation. No explicit Stage 3 references were found. | Needs confirmation. | Needs confirmation. | Needs confirmation. | Needs confirmation. | Needs confirmation. |
| 4 | PHX2 dry-run schema | done | Present by `01cffa3`; original stage commit unavailable | Create PHX2-only dry-run tables for telemetry and research scaffolding. | PHX2 dry-run SQLite connection. | Stage 4A core telemetry tables and Stage 4B field/score/clock research scaffolds. | Yes, creates PHX2 schema only. | No. | `PHX2/tests/test_schema_migrations.py`, repository round-trip tests. |
| 5 | Intake/materialization substrate | done for explicit Stage 5A/5C.1; partly inferred for adjacent services | Present by `01cffa3`; original stage commit unavailable | Add PHX2 raw PumpSwap intake and observe-only price curve substrate. | Normalized migration events, raw PumpSwap events, price observations, token state. | `raw_pumpswap_events`, `price_curve_points`, PHX2 state and feature rows used by later stages. | Yes, writes PHX2 dry-run tables. | No. | Stage 5 schema tests plus migration, raw event, price, ATH, feature, clock, curve service tests. |
| 6 | Needs confirmation / pre-Stage-7 observe-only substrate | unknown | Needs confirmation | Needs confirmation. Current code already contains several observe-only services by `01cffa3`, but no Stage 6 label was found. | Needs confirmation. | Needs confirmation. | Needs confirmation. | No live behavior confirmed. | Existing service tests cover the substrate, but the Stage 6 boundary needs confirmation. |
| 6.5 | Relocate PHX2 to independent sibling repo | done | `01cffa3` | Establish PHX2 as an independent project with its own git history. | Existing `Phoenix_Bot/PHX2/` source, per commit message. | `PHX2/` source, `.gitignore`, `pytest.ini`, independent history. | No code logic or schema change per commit message. | No. | Commit message says relocation only and Phoenix1 untouched. |
| 7 | AlertEligibilityEngine | done | `e1a6af6`; temporal fix `da583a1` | Record observe-only alert eligibility decisions. | PHX2 token state, latest price observation, ATH state, optional field/clock features. | `alert_decisions` rows with `WOULD_ALERT`, `SKIP`, or internal block/error decisions. | Yes, writes `alert_decisions`. | No live sending or enforcement; no rendering/dispatch in Stage 7 itself. | `PHX2/tests/test_alert_eligibility_engine.py`, model and repository tests. |
| 8 | AlertRenderer + Dispatcher + DiscordSink | done | `1f6f431` | Render dry-run alert previews and route them to preview/audit sinks. | `alert_decisions` plus state snapshots/rendering context. | Rendered alerts, dispatch audit rows, console/file/private-preview sink behavior. | Yes, adds/writes `dispatch_events`. | No hard-blocking; preview delivery only, with dispatcher failures isolated. | Renderer and dispatch tests under `PHX2/tests/renderers` and `PHX2/tests/dispatch`. |
| 9 | OutcomeTrackingService | done | `fdf3d62`; follow-up `96cb3bc`; remediation `0cefdd2` | Measure forward outcomes for historical `WOULD_ALERT` decisions. | `alert_decisions`, `price_observations`, alert price/current price. | `outcome_windows`, outcome metrics, `current_price`/`current_mcap` columns on alert decisions. | Yes, Stage 9A/9B schema changes and outcome rows. | No decision logic change except persisting current price/mcap already available to Stage 7. | Commit reports 532 passed/2 skipped, remediation reports 538 passed/2 skipped. |
| 10 | FilterEvaluationEngine + FeeGateFilter | done | `bee8bd5`; remediation `e5c65f5` | Record observe-only filter labels around alert decisions. | `alert_decisions`, `field_features`, Fee Gate primitives. | `filter_evaluations`, `FilterResult`, `DecisionFilterEvaluationResult`, `field_features.event_count_5m`. | Yes, Stage 10A/10B schema changes and filter rows. | No. Filter telemetry is not coupled to eligibility, rendering, dispatch, or live data sources. | Commit reports 66 new tests; remediation reports 593 passed/3 skipped with pre-existing env errors. |
| 11 | DecisionFeatureSnapshotService | done | `8fbdb84` (`stage-11-closed` tag) | Record typed decision-time feature snapshots for later analysis. | `alert_decisions`, token state, ATH/ATH events, field/clock features, fee windows. | `decision_score_features` rows and repository/service result types. | Yes, Stage 11A schema and one-table writer. | No scores, labels, policy verdicts, composites, or runtime behavior changes. | Commit reports 56 new tests and 662 passing/3 skipped, with 14 unrelated pre-existing Windows temp errors. |
| 12 | Decision outcome analysis | done | `ef66e35` | Join historical decisions, filters, snapshots, and outcomes into offline analysis artifacts. | PHX2 SQLite DB opened read-only; `alert_decisions`, `filter_evaluations`, `decision_score_features`, `outcome_windows`, optional token symbol. | Immutable Stage 12 run directory with long CSV, cohort CSVs, manifest, README. | Reads DB in read-only mode; writes files only. | No. Research-only output, no policy influence. | Commit reports full suite passed twice at 734 passed/3 skipped and targeted audit passed. |
| 13 | Policy recommendation builder | done | `a55bedc` | Classify Stage 12 cohorts into evidence-only policy-review recommendations. | Stage 12 `manifest.json` plus four cohort CSVs. | Stage 13 run directory: `candidate_recommendations.csv`, `evidence_summary.csv`, `insufficient_evidence_cohorts.csv`, `manifest.json`, markdown review. | No DB connection. | No. `safe_for_live_policy_consumption=false`; no threshold values emitted. | Commit reports full suite passed twice at 873 passed/3 skipped and targeted audit passed. |
| 13.1 | Expose filter identity columns | done | `1474a52` | Add explicit filter identity columns so Stage 14 does not parse `cohort_id`. | Stage 13 recommendation rows. | Stage 13 schema `1.1` candidate CSV columns: `filter_name`, `filter_version`, `filter_label`, `threshold_version`. | No. | No. | `PHX2/tests/test_stage13_builder.py`, `PHX2/tests/test_stage13_writer.py`. |
| 14 | Shadow policy replay | done | `6c11b8a` | Replay eligible Stage 13 candidates offline against Stage 12 historical decisions. | Stage 13 candidate CSV + manifest, Stage 12 long CSV + manifest. | Stage 14 run directory with shadow rules, exclusions, replay results, impact summaries, review markdown, run log, manifest. | No DB connection; files only. | No. Artifact-only; outputs are not runtime consumable. | Stage 14 docs report 983 passed/3 skipped; tests in `PHX2/tests/test_stage14_*.py`. |

## Detailed Stage Notes

### Stage 0 - Boundary and Safety Scaffold

- Added: Needs confirmation. `PHX2/README.md` and `PHX2/SAFETY.md` state that Stage 0 and Stage 1 establish boundaries before behavior.
- Intentionally did not do: no runtime behavior, no live alerting, no Phoenix1 mutation per the safety contract.
- Key files/modules: `PHX2/README.md`, `PHX2/SAFETY.md`.
- Key tests: Needs confirmation.
- Safety boundaries: Phoenix1 remains the live collector and baseline; PHX2 must not mutate Phoenix1 tables or send live alerts during scaffolding.
- Handoff: Stage 1 package scaffold.

### Stage 1 - Package/Import Scaffold

- Added: inert package boundaries, importable placeholder modules, placeholder integrations, placeholder service owners, and a no-op entrypoint.
- Intentionally did not do: no scoring formulas, no DB schemas, no network calls, no Telegram or Discord sends.
- Key files/modules: `PHX2/__init__.py`, `PHX2/main.py`, `PHX2/integrations/*`, `PHX2/services/score_feature_service.py`, placeholder renderer/scripts.
- Key tests: `PHX2/tests/test_imports.py`.
- Safety boundaries: imports should not perform side effects; integration clients are placeholders only.
- Handoff: Stage 2 settings and connection boundaries.

### Stage 2 - Settings and DB Boundaries

- Added: typed settings for dry-run mode, Phoenix1 read-only DB path, PHX2 dry-run DB path, feature/outcome window settings, score version marker, and disabled dispatch defaults.
- Intentionally did not do: no schema creation, no Phoenix1 runtime config import, no network clients, no alert sending.
- Key files/modules: `PHX2/config/settings.py`, `PHX2/db/connection.py`.
- Key tests: `PHX2/tests/test_settings.py`, `PHX2/tests/test_db_connection.py`.
- Safety boundaries: Phoenix1 is opened through SQLite `mode=ro`; PHX2 uses a separate dry-run DB path and the connection helper creates no tables.
- Handoff: Stage 4 schema work. Stage 3 needs confirmation.

### Stage 3 - Needs Confirmation

- Added: Needs confirmation.
- Intentionally did not do: Needs confirmation.
- Key files/modules: Needs confirmation.
- Key tests: Needs confirmation.
- Safety boundaries: Needs confirmation.
- Handoff: Needs confirmation.

### Stage 4 - PHX2 Dry-Run Schema

- Added: PHX2-only schema migrations for core telemetry and research scaffolding. The explicit Stage 4 tables include `schema_migrations`, `token_sequence_state`, `migration_events`, `price_observations`, `ath_state`, `ath_events`, `alert_decisions`, `filter_evaluations`, `fee_windows`, `field_features`, `score_features`, `clock_features`, `dispatch_events`, and scaffold `outcome_windows`.
- Intentionally did not do: no Phoenix1 imports, no Phoenix1 table mutation, no strategy logic, no sending.
- Key files/modules: `PHX2/db/migrations.py`, `PHX2/db/repositories.py`, model dataclasses under `PHX2/models`.
- Key tests: `PHX2/tests/test_schema_migrations.py`, `PHX2/tests/test_repository_roundtrip.py`, `PHX2/tests/test_repositories.py`.
- Safety boundaries: schema is PHX2 dry-run only; migration rows record Stage 4A and Stage 4B.
- Handoff: Stage 5 raw event and price-curve substrate.

### Stage 5 - Intake and Materialization Substrate

- Added: explicit Stage 5A `raw_pumpswap_events` schema and explicit Stage 5C.1 `price_curve_points` schema. Current files present by `01cffa3` also include PHX2 service owners for normalized migration intake, raw event intake, price observations, ATH state/events, fee windows, field features, clock features, and curve capture.
- Intentionally did not do: service docstrings repeatedly state no live streams, no external price API polling, no alert evaluation, no score formulas, and no message dispatch from these services.
- Key files/modules: `PHX2/services/migration_service.py`, `PHX2/services/pumpswap_event_ingestion_service.py`, `PHX2/services/price_service.py`, `PHX2/services/ath_service.py`, `PHX2/services/feature_window_service.py`, `PHX2/services/field_feature_service.py`, `PHX2/services/clock_feature_service.py`, `PHX2/services/curve_capture_service.py`, `PHX2/db/migrations.py`.
- Key tests: `PHX2/tests/test_migration_service.py`, `PHX2/tests/test_pumpswap_event_ingestion_service.py`, `PHX2/tests/test_price_service.py`, `PHX2/tests/test_ath_service.py`, `PHX2/tests/test_feature_window_service.py`, `PHX2/tests/test_field_feature_service.py`, `PHX2/tests/test_clock_feature_service.py`, `PHX2/tests/test_curve_capture_service.py`, `PHX2/tests/test_schema_migrations.py`.
- Safety boundaries: PHX2 writes are owned by specific services and remain observe-only; Phoenix1 is not mutated.
- Handoff: Stage 6 needs confirmation; Stage 7 consumes the resulting state/features for alert eligibility.

### Stage 6 - Needs Confirmation / Pre-Stage-7 Substrate

- Added: Needs confirmation. The local history has no Stage 6 commit or explicit Stage 6 module docstring.
- Intentionally did not do: Needs confirmation.
- Key files/modules: Needs confirmation. Current observe-only service files existed by the Stage 6.5 relocation commit, but their exact stage assignment is not proven here.
- Key tests: Needs confirmation for Stage 6-specific tests.
- Safety boundaries: no live behavior change is confirmed in repo evidence.
- Handoff: Stage 6.5 relocation and Stage 7 AlertEligibilityEngine.

### Stage 6.5 - Relocation Checkpoint

- Added: independent PHX2 repo history, `.gitignore`, `pytest.ini`, and copied PHX2 source under `PHX2/`.
- Intentionally did not do: commit message says relocation only and no code logic changes.
- Key files/modules: entire `PHX2/` tree as of `01cffa3`.
- Key tests: not a behavior stage; verification is the commit message and preserved test suite.
- Safety boundaries: Phoenix1 untouched; PHX2 source copied from the prior location.
- Handoff: Stage 7 implementation in local history.

### Stage 7 - AlertEligibilityEngine

- Added: `AlertEligibilityEngine`, tier policy, drawdown/pump eligibility decisions, duplicate/higher-tier suppression, decision audit rows, and later temporal correctness fixes in Stage 7.1.
- Intentionally did not do: no rendering, dispatch, network I/O, or writes to any table other than `alert_decisions` in Stage 7 itself.
- Key files/modules: `PHX2/services/alert_eligibility_engine.py`, `PHX2/models/alert_decision.py`, `PHX2/db/repositories.py`.
- Key tests: `PHX2/tests/test_alert_eligibility_engine.py`, `PHX2/tests/test_models.py`, `PHX2/tests/test_repository_roundtrip.py`.
- Safety boundaries: records observe-only decisions; dispatcher state must not affect engine output.
- Handoff: Stage 8 preview rendering/dispatch consumes `alert_decisions`.

### Stage 8 - AlertRenderer + Dispatcher + DiscordSink

- Added: rendering context assembly, alert renderer, plain-text and Discord adapters, dispatcher, routing, console/file/Discord preview sinks, HTTP transport abstraction, dispatch audit rows, and preview pipeline integration.
- Intentionally did not do: no coupling to Stage 7 decision logic and no mutation of other tables beyond dispatch audit rows, per commit message.
- Key files/modules: `PHX2/renderers/*`, `PHX2/dispatch/*`, `PHX2/models/dispatch_event.py`, `PHX2/db/migrations.py`.
- Key tests: `PHX2/tests/renderers/*`, `PHX2/tests/dispatch/*`.
- Safety boundaries: dispatcher catches failures; webhook URL is constructor-injected and redacted from persisted errors; private preview is not hard-block enforcement.
- Handoff: Stage 9 outcome tracking can evaluate historical `WOULD_ALERT` decisions independently of preview behavior.

### Stage 9 - OutcomeTrackingService

- Added: forward-return outcome measurement for `WOULD_ALERT` decisions, `outcome_windows` schema replacement, current price/mcap columns on `alert_decisions`, `OutcomeTrackingService`, outcome metrics, repository extensions, and remediation for idempotent migration safety and error handling.
- Intentionally did not do: no alert decision logic changes beyond persisting already-known `current_price`/`current_mcap`; no dispatch mutation.
- Key files/modules: `PHX2/services/outcome_tracking_service.py`, `PHX2/models/outcome_window.py`, `PHX2/models/outcome_tracking_result.py`, `PHX2/db/migrations.py`, `PHX2/db/repositories.py`.
- Key tests: `PHX2/tests/test_outcome_tracking_service.py`, `PHX2/tests/test_outcome_metrics.py`, `PHX2/tests/test_schema_migrations.py`, Stage 7 regression tests.
- Safety boundaries: migration refuses to drop non-empty Stage 4B scaffold data; unique races map to `ALREADY_RECORDED`; unexpected DB errors no longer masquerade as pending windows after remediation.
- Handoff: Stage 10 records filter telemetry; Stage 12 later joins outcomes with decisions/filter/snapshot data.

### Stage 10 - FilterEvaluationEngine + FeeGateFilter

- Added: filter substrate, Fee Gate v1.0 observe-only filter, `filter_evaluations` schema extension, `threshold_version`, `output_reason_json`, `FilterLabel`, `DecisionFilterEvaluationResult`, `field_features.event_count_5m`, repository helpers, and migration rerun/payload-shape remediation.
- Intentionally did not do: no change to alert eligibility, renderer output, dispatch behavior, outcome tracking, or live data sources.
- Key files/modules: `PHX2/services/filter_evaluation_engine.py`, `PHX2/filters/base.py`, `PHX2/filters/fee_gate.py`, `PHX2/models/filter_result.py`, `PHX2/models/filter_evaluation_result.py`, `PHX2/db/migrations.py`.
- Key tests: `PHX2/tests/test_filter_evaluation_engine.py`, `PHX2/tests/test_fee_gate.py`, `PHX2/tests/test_filter_evaluation_pipeline.py`, `PHX2/tests/test_field_feature_service.py`, `PHX2/tests/test_schema_migrations.py`.
- Safety boundaries: observe-only filter rows; per-filter exceptions are isolated; caller validation failures return result objects; Phoenix1 lineage is documented only, not imported.
- Handoff: Stage 11 snapshots decision-time primitives; Stage 12 consumes filter labels.

### Stage 11 - DecisionFeatureSnapshotService

- Added: `decision_score_features` table, `DecisionFeatureSnapshotService`, `DecisionScoreFeatures` model, snapshot result wrapper, repository, and `FeeWindowRepository.get_by_id`.
- Intentionally did not do: no reads from `filter_evaluations`, `outcome_windows`, `dispatch_events`, legacy `score_features`, `price_observations`, `raw_pumpswap_events`, or live infrastructure; no risk score, setup score, composite scoring, labels, or policy verdicts.
- Key files/modules: `PHX2/services/decision_feature_snapshot_service.py`, `PHX2/models/decision_score_features.py`, `PHX2/models/decision_feature_snapshot_result.py`, `PHX2/db/migrations.py`, `PHX2/db/repositories.py`.
- Key tests: `PHX2/tests/test_decision_feature_snapshot_service.py`, `PHX2/tests/test_decision_score_feature_repository.py`, `PHX2/tests/test_schema_migrations.py`, `PHX2/tests/test_repository_roundtrip.py`.
- Safety boundaries: writes only `decision_score_features`; default `as_of_time` is the decision's evaluated time; validation failures short-circuit before writes.
- Handoff: Stage 12 joins typed snapshots with decisions, filters, and outcomes.

### Stage 12 - Decision Outcome Analysis

- Added: offline read-only analysis package with substrate readers, pure-ish run orchestration, CLI wrapper, deterministic artifact writers, Wilson CI/cohort metrics, primitive bucketing, manifest/README reporting, and fixtures.
- Intentionally did not do: no DB writes, no network I/O, no significance tests, no scores, no policy influence.
- Key files/modules: `PHX2/analysis/__init__.py`, `PHX2/analysis/decision_outcome_analysis.py`, `PHX2/analysis/readers.py`, `PHX2/analysis/metrics.py`, `PHX2/analysis/buckets.py`, `PHX2/analysis/manifest.py`, `PHX2/analysis/writers.py`, `PHX2/analysis/cli.py`.
- Key tests: `PHX2/tests/test_analysis_pipeline.py`, `PHX2/tests/test_analysis_metrics.py`, `PHX2/tests/test_analysis_buckets.py`, `PHX2/tests/test_analysis_read_isolation.py`, `PHX2/tests/test_analysis_repro.py`, `PHX2/tests/fixtures/analysis_fixture_builder.py`.
- Safety boundaries: PHX2 SQLite is opened read-only; allowed analytical tables are constrained; generated artifacts carry research-only warnings.
- Handoff: Stage 13 consumes the Stage 12 manifest and four cohort CSVs. Stage 14 later consumes the Stage 12 long CSV for replay.

Stage 12 outputs include:

- `decision_filter_outcome_long.csv`
- `cohort_tier_baseline.csv`
- `cohort_filter_label_overall.csv`
- `cohort_filter_label_by_tier.csv`
- `cohort_primitive_bucket_by_tier.csv`
- `manifest.json`
- `README.md`

### Stage 13 - Policy Recommendation Builder

- Added: evidence-only Stage 13 package that loads Stage 12 run artifacts, classifies cohorts into action/evidence/direction buckets, writes policy-review CSV/markdown artifacts, records input hashes, and hardcodes `safe_for_live_policy_consumption=false`.
- Intentionally did not do: no DB connection, no `PHX2.analysis` runtime imports, no network I/O, no specific threshold values, no crossed-feature rules, and no live policy consumption.
- Key files/modules: `PHX2/stage13/types.py`, `PHX2/stage13/wilson.py`, `PHX2/stage13/hashing.py`, `PHX2/stage13/classifier.py`, `PHX2/stage13/loader.py`, `PHX2/stage13/builder.py`, `PHX2/stage13/writer.py`, `PHX2/stage13/pipeline.py`, `PHX2/stage13/cli.py`.
- Key tests: `PHX2/tests/test_stage13_builder.py`, `PHX2/tests/test_stage13_classifier.py`, `PHX2/tests/test_stage13_loader.py`, `PHX2/tests/test_stage13_pipeline.py`, `PHX2/tests/test_stage13_writer.py`, `PHX2/tests/test_stage13_wilson.py`, `PHX2/tests/test_stage13_hashing.py`.
- Safety boundaries: loosen-direction findings are capped at `HOLD_OBSERVE_ONLY`; recommendations are evidence-review artifacts, not runtime policy.
- Handoff: Stage 13.1 makes filter identity explicit; Stage 14 consumes Stage 13 candidates and manifest.

Stage 13 outputs include:

- `candidate_recommendations.csv`
- `evidence_summary.csv`
- `insufficient_evidence_cohorts.csv`
- `manifest.json`
- `stage13_policy_review.md`

### Stage 13.1 - Expose Filter Identity Columns

- Added: Stage 13 schema `1.1`, with `filter_name`, `filter_version`, `filter_label`, and `threshold_version` columns populated for `filter_label_blocking` rows and empty for primitive bucket rows.
- Intentionally did not do: no classification logic change, no DB access, no live policy change, and no removal of `cohort_id` back-compat traceability.
- Key files/modules: `PHX2/stage13/types.py`, `PHX2/stage13/builder.py`, `PHX2/stage13/writer.py`, `PHX2/stage13/pipeline.py`.
- Key tests: `PHX2/tests/test_stage13_builder.py`, `PHX2/tests/test_stage13_writer.py`.
- Safety boundaries: downstream stages can tuple-match identity without parsing `cohort_id`.
- Handoff: Stage 14 requires Stage 13 schema version exactly `1.1`.

### Stage 14 - Shadow Policy Replay

- Added: offline artifact-only Stage 14 package that loads Stage 13 and Stage 12 run directories, validates schema/hash invariants, translates eligible Stage 13 candidates into shadow `SIMULATED_BLOCK` rules, replays them against historical decisions, computes advisory impact metrics, and writes a deterministic run directory.
- Intentionally did not do: no DB connection, no network I/O, no live config mutation, no threshold mutation, no scoring or ML, no crossed/compound rules, no classification of rules as good or bad, and no runtime-consumable output.
- Key files/modules: `PHX2/stage14/types.py`, `PHX2/stage14/hashing.py`, `PHX2/stage14/loader.py`, `PHX2/stage14/rules.py`, `PHX2/stage14/replay.py`, `PHX2/stage14/metrics.py`, `PHX2/stage14/writer.py`, `PHX2/stage14/pipeline.py`, `PHX2/stage14/cli.py`.
- Key tests: `PHX2/tests/test_stage14_loader.py`, `PHX2/tests/test_stage14_rules.py`, `PHX2/tests/test_stage14_replay.py`, `PHX2/tests/test_stage14_metrics.py`, `PHX2/tests/test_stage14_writer.py`, `PHX2/tests/test_stage14_pipeline.py`, `PHX2/tests/test_stage14_cli.py`, `PHX2/tests/fixtures/stage14/stage14_fixture_writer.py`.
- Safety boundaries: Stage 13 `safe_for_live_policy_consumption` must be literal false; Stage 14 manifest carries `safe_for_live_policy_consumption=false`; `shadow_policy_rules.json` carries `runtime_consumable=false`; manifest is written last.
- Handoff: Stage 15 is expected to be human approval. No Stage 15 implementation exists in this repo.

Stage 14 outputs include:

- `shadow_policy_rules.json`
- `excluded_recommendations.csv`
- `shadow_policy_replay_results.csv`
- `shadow_vs_live_decision_diff.csv`
- `blocked_decisions_simulated.csv`
- `would_have_blocked_winners.csv`
- `saved_noise_simulated.csv`
- `impact_summary_by_tier.csv`
- `impact_summary_by_rule.csv`
- `impact_summary_by_filter.csv`
- `stage14_shadow_policy_review.md`
- `stage14_run.log`
- `manifest.json`

## Current Pipeline Explanation

### Stage 12: What happened historically?

Stage 12 opens the PHX2 SQLite DB read-only and joins historical
`alert_decisions`, `filter_evaluations`, `decision_score_features`, and
`outcome_windows` at the `alert_decision_id` level. It emits a deterministic
run directory with a long decision-by-filter CSV, cohort summaries, a manifest,
and a README. Its output is research-only and does not influence policy.

### Stage 13: Which cohorts look evidence-supported enough to consider?

Stage 13 reads Stage 12 filesystem artifacts, not the DB. It classifies cohort
rows into review categories such as `ADVANCE_AS_CANDIDATE`,
`HOLD_OBSERVE_ONLY`, `ANOMALY_FLAG`, `NO_SIGNAL_FOUND`, or
`INSUFFICIENT_EVIDENCE`. It emits evidence-review artifacts and a manifest with
`safe_for_live_policy_consumption=false`. It recommends candidates for review;
it does not emit live policy thresholds.

### Stage 13.1: Expose filter identity columns

Stage 13.1 changes Stage 13's candidate CSV schema to `1.1` by adding
`filter_name`, `filter_version`, `filter_label`, and `threshold_version`.
This prevents Stage 14 from parsing `cohort_id` to recover identity. Primitive
bucket rows intentionally leave these columns empty.

### Stage 14: What would have changed historically?

Stage 14 reads a Stage 13 run and a Stage 12 run. It validates the Stage 13
schema version, the Stage 13 safety flag, the Stage 12 schema version, and the
Stage 12 manifest hash recorded by Stage 13. It translates only eligible
`filter_label_blocking` / `ADVANCE_AS_CANDIDATE` / `tighten` / T1-T3 rows with
complete filter identity into draft shadow block rules, then replays those
rules against historical Stage 12 long-CSV rows.

The result is diagnostic: which historical live-alert decisions would have
been simulated blocks, which of those had 2x/3x/5x outcomes, which looked like
saved noise, and which rules carry advisory warning flags. Stage 14 does not
approve policy and does not change live alert behavior.

## Proposed Stage 15+ Roadmap

The following stages are proposed only. They are not implemented in this repo.

### Stage 15 - Proposed: Operator-Reviewed Observe-Only Policy Approval Artifact

Purpose: create an explicit human approval layer for observe-only
rules/artifacts from a specific Stage 14 run.

Proposed inputs:

- Stage 14 `manifest.json`
- Stage 14 `shadow_policy_rules.json`
- Stage 14 `impact_summary_by_rule.csv`
- optional Stage 14 replay CSVs and review markdown for operator context

Proposed outputs:

- an operator-reviewed approval artifact that records approved, rejected, or
  deferred observe-only rule decisions
- lineage back to Stage 14, Stage 13, and Stage 12 manifest hashes
- observe-only approval records only; it must not produce hard-blocking policy

Safety boundaries:

- no auto-promotion
- no DB/network requirement unless separately designed and approved
- no hard-blocking output
- no live alert behavior change
- approval state must be separate from Stage 14 `rule_id`

### Stage 16 - Proposed: Live Observe-Only Telemetry Wiring

Purpose: wire approved observe-only candidates into live observe-only
telemetry. Stage 16 still does not hard-block.

Proposed behavior:

- evaluate approved candidate rules against live decisions in observe-only mode
- record what the approved observe-only rules would have done
- compare live observe-only results with historical replay expectations
- surface drift, false-positive risk, and missing-data risk

Safety boundaries:

- still no hard-blocking
- no auto-promotion from observe-only telemetry to enforcement
- live behavior remains unchanged apart from telemetry/audit rows

### Stage 17+ - Proposed: Limited Hard-Block Promotion

Purpose: provide the first possible stage for narrow hard-block promotion, and
only after historical replay and live observe-only telemetry agree and a human
approves promotion.

Proposed constraints:

- limited scope, likely per-rule or per-filter identity
- explicit rollback path
- ongoing monitoring of blocked winners, unknown outcomes, and block rate
- promotion gates tied to both Stage 14 replay evidence and Stage 16 live
  observe-only evidence

Safety boundaries:

- no broad hard-block rollout
- no promotion from Stage 13 or Stage 14 alone
- no promotion from Stage 15 observe-only approval alone
- no promotion without a human approval artifact

## Safety Philosophy

The main safety principle is:

Historical evidence -> candidate recommendation -> offline replay -> human
approval -> live observe-only -> eventual limited enforcement.

This means:

- Stages 12-14 do not change live alert behavior.
- Stage 13 recommendations are not policy approvals.
- Stage 14 replay rules are not runtime-consumable policy files.
- There is no auto-promotion from evidence to enforcement.
- There is no live hard-blocking before approval.
- Artifacts and manifests are part of the audit trail.
- Hashes, schema versions, and explicit safety flags are part of the handoff
  contract between stages.

The recent chain is intentionally conservative. Stage 12 asks what happened,
Stage 13 asks what might be worth considering, Stage 13.1 makes identity
explicit, and Stage 14 asks what would have changed if those candidates had
existed historically. Approval and live behavior belong to later stages.

## Uncertainties

- Stage 0 exact commit and file scope: Needs confirmation.
- Stage 1 original commit: Needs confirmation. Current package scaffold and
  tests support the inferred implementation, but the local history starts
  later.
- Stage 2 original commit: Needs confirmation. Current settings/connection
  files and tests support the implementation, but the original commit is not
  in local history.
- Stage 3 purpose, files, and tests: Needs confirmation.
- Stage 4 original commit: Needs confirmation. Current migrations/tests support
  the stage, but the original implementation commit is not in local history.
- Stage 5 exact boundary beyond explicit Stage 5A and Stage 5C.1 migrations:
  Needs confirmation. Several observe-only services existed by the Stage 6.5
  relocation commit, but their original stage assignments are not proven.
- Stage 6 purpose, files, DB behavior, and tests: Needs confirmation.
- Stage 6.5 is a relocation checkpoint rather than a normal functional stage.
- Stage 11 has a `stage-11-closed` tag, but the implementation commit message
  calls it a pre-audit checkpoint. The roadmap treats it as done because later
  stages depend on it and the local tag names it closed.
- Stage 14 implementation is committed at `6c11b8a` and supported by committed
  source/tests.
- Stage 15 does not exist yet in this repo.
