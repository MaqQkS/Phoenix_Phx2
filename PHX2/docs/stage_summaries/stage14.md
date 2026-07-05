# Stage 14 — Offline Historical Shadow-Policy Replay

## 1. Purpose

Stage 14 reads Stage 13's policy-recommendation outputs and Stage 12's per-decision history, translates the eligible Stage 13 ADVANCE_AS_CANDIDATE rows into a draft set of shadow BLOCK rules, replays those rules against the historical alert decisions, and writes a run directory of replay diagnostics. The single question it answers is: "If we had turned the safe Stage 13 candidates into a draft shadow policy at the time of those historical decisions, which decisions would have been blocked instead of alerted, and what were the outcomes of the decisions we would have suppressed?" Stage 14 explicitly does NOT answer whether the shadow policy is good, whether any rule should be promoted, or what alerting behavior should change going forward. It is artifact-only, offline, and produces nothing the runtime is allowed to consume; human approval belongs in Stage 15, and any hard-block promotion is Stage 16+.

## 2. Commit chain

- Stage 13.1 prerequisite: `1474a52` — Stage 13.1 expose filter identity columns (added the four explicit filter-identity columns to Stage 13's candidate CSV that Stage 14 tuple-matches against)
- Stage 14 implementation commit: `6c11b8a` — Stage 14 shadow policy replay
- Stage 14 audit remediation commits: none separate. The Codex MEDIUM and LOW findings were both patched against the working tree before the commit landed, so `6c11b8a` contains the audited-and-remediated implementation in a single commit.
- Test count at close: **983 passed, 3 skipped, 0 failed**
- Codex audit result: **0 Critical, 0 High, 0 Medium, 0 Low** remaining after pre-commit remediation. The two non-zero findings during review (one Medium, one Low) were both resolved prior to commit; see §11 for details.

## 3. Module inventory

All paths relative to repository root.

- `PHX2/stage14/__init__.py` — Package marker plus the Stage 14 substrate-lock summary docstring (no executable code).
- `PHX2/stage14/types.py` — Locked vocabularies (`PolicySurface`, `TierScope`, `SimulatedAction`, `Direction`), exclusion-reason constants, warning-flag constants, advisory threshold constants, and the in-memory dataclasses (`SourceRecommendation`, `ShadowRule`, `ExcludedRow`, `LongCsvRow`, `ReplayRow`, `ImpactCounts`, `RuleImpact`, `ReplayImpact`).
- `PHX2/stage14/hashing.py` — Stdlib SHA-256 helpers (`sha256_file`, `sha256_bytes`, `short_content_hash`). A deliberate copy of the Stage 13 hashing helpers so Stage 14 does not import a Stage 13 runtime module.
- `PHX2/stage14/loader.py` — Reads and validates the Stage 13 run directory (manifest + candidate CSV) and the Stage 12 run directory (manifest + long CSV). Enforces all schema-version and manifest-hash invariants. Owns `resolve_stage12_run_path`.
- `PHX2/stage14/rules.py` — Translates Stage 13 candidate rows into shadow rules. Houses the eligibility gate, the exclusion-reason routing, and `compute_rule_id`.
- `PHX2/stage14/replay.py` — Matches long-CSV rows against the rule index by tuple and aggregates per `alert_decision_id` into `ReplayRow` objects.
- `PHX2/stage14/metrics.py` — Computes by-tier / by-rule / by-filter impact summaries and the advisory warning-flag set.
- `PHX2/stage14/writer.py` — Renders all 13 output artifacts with byte-stable formatting (locked column orders, `lineterminator="\n"`, sorted-keys JSON, dynamic threshold formatting in the markdown).
- `PHX2/stage14/pipeline.py` — Pure-ish `run(...)` orchestrator. Loads, translates, replays, aggregates, writes, then writes the manifest last. Holds the `sum(rule.source_row_count) + len(excluded) == len(candidate_rows)` integrity check.
- `PHX2/stage14/cli.py` — argparse entry point. Captures the git fingerprint via subprocess (CLI-only side effect), maps invariant violations to exit code 3, missing-path errors to exit code 2, and prints the run-directory path to stdout on success.

## 4. Locked invariants

- [ ] **Stage 13 schema_version** equals `"1.1"` exactly. Reject anything else (`PHX2/stage14/loader.py:49`, `:226-234`).
- [ ] **Stage 12 schema_version** equals `"1"` exactly (`PHX2/stage14/loader.py:43`, `:329-337`).
- [ ] **Stage 13 `safe_for_live_policy_consumption`** must be present and the literal Python `False` on input. The field name is `safe_for_live_policy_consumption`; any non-False value (including `None`, missing, `"false"` string) is rejected (`PHX2/stage14/loader.py:236-251`).
- [ ] **Stage 14 manifest `safe_for_live_policy_consumption`** is emitted as the literal Python `False` (`PHX2/stage14/types.py:65`, written into the manifest at `PHX2/stage14/pipeline.py:127`).
- [ ] **`runtime_consumable=false` on `shadow_policy_rules.json`**, emitted as the literal Python `False` (JSON bare `false`, not the string `"false"`). Constant at `PHX2/stage14/types.py:71`; written at `PHX2/stage14/writer.py:204`.
- [ ] **Stage 12 manifest hash agreement** is required in BOTH the default-path branch (Stage 12 path taken from Stage 13's recorded `stage12_run_path`) and the `--stage12-run` override branch. The expected hash is sourced from Stage 13's recorded `stage12_manifest_hash`; a missing recorded hash is itself a hard fail (`PHX2/stage14/loader.py:340-388`).
- [ ] **`load_stage12_run`'s `expected_manifest_hash` keyword argument is required** — no default, no opt-out. Direct callers cannot bypass the integrity check (`PHX2/stage14/loader.py:258-262`).
- [ ] **Required Stage 12 long-CSV columns** (extras tolerated): `alert_decision_id`, `tier_name`, `decision_type`, `filter_name`, `filter_version`, `filter_label`, `threshold_version`, `has_primary_outcome`, `primary_outcome_hit_2x_24h` (`PHX2/stage14/loader.py:99-109`).
- [ ] **Required Stage 13 candidate-CSV columns** (29 total, all expected verbatim from Stage 13's writer): `policy_surface`, `cohort_id`, `filter_name`, `filter_version`, `filter_label`, `threshold_version`, `tier_scope`, `action_class`, `direction`, `evidence_class`, `policy_severity`, `review_priority`, `n_complete`, `n_censored`, `cohort_rate`, `baseline_rate`, `lift_absolute`, `lift_relative`, `wilson_ci_low`, `wilson_ci_high`, `ci_excludes_baseline`, `censoring_rate`, `censoring_warning_flag`, `watchlist_flag`, `tier_evidence_support`, `cross_tier_disagreement`, `loosen_capped_flag`, `confidence_ceiling_applied`, `notes`. The bolded subset added by Stage 13.1 is `filter_name`, `filter_version`, `filter_label`, `threshold_version` — Stage 14 cannot operate without these (`PHX2/stage14/loader.py:56-86`).
- [ ] **Manifest is written LAST**. The pipeline calls `write_run_log` then `write_manifest` as the final two writes; the manifest is the last byte written to disk (`PHX2/stage14/pipeline.py:305`, `:308`).
- [ ] **Every candidate row accounted for**. The pipeline enforces `sum(rule.source_row_count for rule in rules) + len(excluded) == len(candidate_rows)` and raises `RuntimeError` otherwise (`PHX2/stage14/pipeline.py:240-247`).
- [ ] **No DB access**. `grep -E '\b(sqlite3?|psycopg|pymongo|sqlalchemy|aiosqlite|asyncpg|mysql|redis)\b' PHX2/stage14/` returns zero matches.
- [ ] **No network access**. `grep -E '\b(requests|httpx|urllib|socket|aiohttp|websocket|grpc|http\.client|httplib)\b' PHX2/stage14/` returns only a docstring line in `__init__.py` that declares "no network I/O". The full import surface is stdlib (`csv`, `json`, `hashlib`, `dataclasses`, `datetime`, `pathlib`, `typing`, `collections`, `argparse`, `subprocess`, `sys`, `io`) plus intra-`PHX2.stage14` imports. The single `subprocess` usage is in `cli.py` for a local `git rev-parse HEAD` capture.
- [ ] **Output directory isolation**. The pipeline creates `run_dir = <output_root>/<UTC_timestamp>/` via `_create_run_dir(..., exist_ok=False)` and passes only that single path to every writer. The loaders only read; they never write. Test `test_output_is_inside_run_directory_only` walks `tmp_path` pre- and post-run and asserts every newly created file is under the run directory. Test `test_stage_inputs_unchanged` re-hashes the Stage 12 + Stage 13 input files before and after a run and asserts byte equality.

## 5. Rule translation rules

**Eligibility gate** (all five conditions required; evaluated in order at `PHX2/stage14/rules.py:55-72`):

1. `policy_surface == "filter_label_blocking"`
2. `action_class == "ADVANCE_AS_CANDIDATE"`
3. `direction == "tighten"`
4. `tier_scope in {"T1", "T2", "T3"}`
5. All four filter-identity columns (`filter_name`, `filter_version`, `filter_label`, `threshold_version`) non-empty after `strip()`.

**Exclusion-reason vocabulary** (locked; constants in `PHX2/stage14/types.py:105-122`). A failing row is attributed to the FIRST gate it violates:

| Order | Reason | Triggered by |
| --- | --- | --- |
| 1 | `not_filter_label_surface` | `policy_surface != "filter_label_blocking"` |
| 2 | `not_advance_candidate` | `action_class != "ADVANCE_AS_CANDIDATE"` (covers HOLD_OBSERVE_ONLY, ANOMALY_FLAG, NO_SIGNAL_FOUND, INSUFFICIENT_EVIDENCE) |
| 3 | `not_tighten` | `direction != "tighten"` (covers loosen, none) |
| 4 | `tier_scope_overall` | `tier_scope not in {T1, T2, T3}` |
| 5 | `missing_filter_identity` | any of the four filter-identity columns empty |

**Rule ID derivation** (`PHX2/stage14/rules.py:107-118`):

```
canonical = "|".join([
    policy_surface, tier_scope, filter_name, filter_version,
    filter_label, threshold_version, simulated_action
])
rule_id = "shadow_rule_" + sha256(canonical.encode("utf-8")).hexdigest()[:12]
```

The hash truncation length is **12 hex characters** (48 bits). Content-stable: reruns over the same Stage 13 candidate set produce the same rule_id; inserting unrelated candidates does not shift the IDs of unchanged rules.

**Sort order for `shadow_policy_rules.json`**: rules are sorted by `rule_id` lexicographically (`PHX2/stage14/rules.py:225` and again defensively in the writer at `PHX2/stage14/writer.py:191`). Each rule's `source_recommendations` list is sorted by `cohort_id`.

## 6. Replay semantics

**Live-alert filter on Stage 12 long-CSV rows**: a row participates in matching only if its `decision_type` equals `"would_alert"` (constant `WOULD_ALERT_DECISION_TYPE` at `PHX2/stage14/replay.py:50`). Decisions whose `decision_type` is anything else still produce a `ReplayRow` (so the replay output preserves the full long-CSV decision set), but they cannot be marked `decision_changed=true` — the shadow rule "blocking" a non-alerting decision is a no-op.

**Match tuple** (`PHX2/stage14/replay.py:80-89`): a long-CSV row matches a rule when

```
(row.tier_name, row.filter_name, row.filter_version, row.filter_label, row.threshold_version)
==
(rule.tier_scope, rule.filter_name, rule.filter_version, rule.filter_label, rule.threshold_version)
```

A long-CSV row with any of those five fields null cannot form an identity tuple and is silently skipped during matching (it may still contribute the decision's outcome fields if it is the first row absorbed for that decision).

**Per-decision aggregation** (`PHX2/stage14/replay.py:133-218`):

- One `ReplayRow` per unique `alert_decision_id`. The long CSV is decision × filter, so multiple long rows can collapse to one replay row.
- `triggering_rule_ids` is the deduped + sorted tuple of every matching rule across all of the decision's filter rows. `n_triggering_rules` is the length of this tuple after dedup, NOT the count of matching long-CSV rows.
- The decision-level fields (`token_address`, `tier_name`, `original_action`, outcome flags) are taken from the FIRST absorbed row for that decision. By Stage 12's contract these values are identical across the decision's rows.
- `simulated_action` is `"SIMULATED_BLOCK"` when at least one rule matched, else `"SIMULATED_PASS"`. There is no third value in v0.
- `decision_changed` is `True` only when `original_action == "would_alert"` AND `simulated_action == "SIMULATED_BLOCK"`. A SIMULATED_BLOCK against a non-alerting decision is recorded but does not count as a behavioral change.

**Output value vocabulary for `simulated_action`**: exactly `"SIMULATED_BLOCK"` or `"SIMULATED_PASS"`. The `allowed_actions` field in `shadow_policy_rules.json` and in the manifest is hardcoded to `["SIMULATED_BLOCK"]` — the PASS value is the no-change baseline and is not a rule action.

**`original_action` handling**: copied verbatim from the Stage 12 long CSV's `decision_type` column. No renaming, no normalization. The historical action stays recognizable in Stage 12 vocabulary (typically the literal string `"would_alert"`).

## 7. Warning flags and thresholds

All thresholds defined as named constants in `PHX2/stage14/types.py:140-172` and used unmodified by `PHX2/stage14/metrics.py:243-294`. All flags are **advisory only** — no pass/fail behavior anywhere in the pipeline branches on a flag's presence.

| Flag | Threshold | Trigger condition |
| --- | --- | --- |
| `unmatched_filter_tuple` | (no numeric threshold) | Rule's `n_matched == 0` — the rule's identity tuple did not appear in any historical filter evaluation. |
| `small_n_rule` | `< 10` | `0 < n_matched < SMALL_N_RULE_THRESHOLD`. Excludes the unmatched case (which carries its own flag). |
| `excessive_block_rate` | `> 0.30` | `n_matched / tier_live_total > EXCESSIVE_BLOCK_RATE_THRESHOLD`. The denominator is the live-decision count for the rule's own tier, not the run-wide total. **Differs from locked plan**: original plan proposed `> 0.5`; pushed back during review on the basis that blocking a third of historical live alerts is already a sizable intervention. |
| `high_winners_blocked_rate` | `> 0.30` | Among the rule's blocked-with-primary-outcome decisions, the 2x-winner share exceeds the threshold: `n_blocked_winners_2x / n_blocked_with_primary_outcome > HIGH_WINNERS_BLOCKED_RATE_THRESHOLD`. |
| `unknown_outcome_rate` | `> 0.30` | Of the rule's matched decisions, the no-primary-outcome share exceeds the threshold: `n_blocked_no_outcome / n_matched > UNKNOWN_OUTCOME_RATE_THRESHOLD`. |
| `missing_outcome_data` | `< 0.50` (replay-wide) | Across all live alert decisions (`decision_type == "would_alert"`), the primary-outcome share is below `MISSING_OUTCOME_DATA_OVERALL_THRESHOLD`. Also fires when there are zero live decisions in scope. This is the only flag scoped to the whole replay rather than to a rule. |

## 8. Output artifact inventory

13 artifacts, all written into `<output_root>/<UTC_timestamp>/`. Filenames are locked at `PHX2/stage14/writer.py:47-59`. Sort orders are documented per writer in `PHX2/stage14/writer.py`.

| # | Filename | Purpose | Sort order | Stage 15 handoff? |
| --- | --- | --- | --- | --- |
| 1 | `shadow_policy_rules.json` | Translated shadow rules with full source-recommendation lineage. The primary handoff surface. | rules sorted by `rule_id`; each rule's `source_recommendations` sorted by `cohort_id` | **Primary** |
| 2 | `excluded_recommendations.csv` | Every Stage 13 candidate row that did not become a rule, with its locked exclusion reason | `(policy_surface, cohort_id, tier_scope, action_class)` | Informational only |
| 3 | `shadow_policy_replay_results.csv` | One row per unique `alert_decision_id` (the full replay set) | `alert_decision_id` ASC | Informational; reviewer-facing |
| 4 | `shadow_vs_live_decision_diff.csv` | Subset of (3) where `decision_changed == true` | `alert_decision_id` ASC | Informational |
| 5 | `blocked_decisions_simulated.csv` | Subset of (3) where `simulated_action == "SIMULATED_BLOCK"` | `alert_decision_id` ASC | Informational |
| 6 | `would_have_blocked_winners.csv` | (5) ∩ `has_primary_outcome=true` ∩ `primary_outcome_hit_2x_24h=true` | `alert_decision_id` ASC | Informational (missed-winner proxy) |
| 7 | `saved_noise_simulated.csv` | (5) ∩ `has_primary_outcome=true` ∩ `primary_outcome_hit_2x_24h=false` | `alert_decision_id` ASC | Informational (saved-noise proxy) |
| 8 | `impact_summary_by_tier.csv` | Counts by `tier_name` plus an `overall` row | `overall` first, then T1/T2/T3 | Informational |
| 9 | `impact_summary_by_rule.csv` | Counts keyed by `rule_id` plus warning-flag column | `rule_id` ASC | Informational |
| 10 | `impact_summary_by_filter.csv` | Counts aggregated to `filter_name` (collapsing version / label / threshold) | `filter_name` ASC | Informational |
| 11 | `stage14_shadow_policy_review.md` | Human-readable reviewer document | rule and tier tables match the corresponding CSV orders | Informational; reviewer-facing |
| 12 | `stage14_run.log` | Timestamped event log of the pipeline run | insertion order | Diagnostic |
| 13 | `manifest.json` | Run identity, input hashes, safety flags, artifact filename inventory. **Written LAST.** | sorted JSON keys | **Primary** (lineage anchor) |

## 9. Stage 14 → Stage 15 handoff

Stage 15 is the human-approval layer. The contract below describes exactly what Stage 15 is expected to consume from a Stage 14 run directory.

**Files Stage 15 reads**:

1. `manifest.json` — the lineage anchor. Stage 15 must use it to verify the run identity and to chain back to Stage 13's manifest hash and Stage 12's manifest hash.
2. `shadow_policy_rules.json` — the rule set under review. Stage 15 consumes the `rules[]` items; each item's `rule_id`, identity tuple (`tier_scope`, `filter_name`, `filter_version`, `filter_label`, `threshold_version`), and `source_recommendations` constitute the proposal under review.
3. `impact_summary_by_rule.csv` — the per-rule replay numbers and advisory `warning_flags` column.
4. Optionally: `shadow_policy_replay_results.csv` and `stage14_shadow_policy_review.md` for spot-checking.

**Schema of `shadow_policy_rules.json`** (top-level keys sorted alphabetically by the writer):

- `allowed_actions: ["SIMULATED_BLOCK"]` — fixed list. Any future expansion is a Stage 14 schema bump and requires Stage 15 to be re-audited in lockstep.
- `rule_count: <int>` — equal to `len(rules)`.
- `rules: [...]` — list of rule objects, sorted by `rule_id`.
- `runtime_consumable: false` — hardcoded.
- `stage14_schema_version: "1.0"` — pinned in `PHX2/stage14/types.py:42`.
- `stage14_version: "0.1.0"` — pinned in `PHX2/stage14/types.py:41`.

**Schema of each `rules[]` item**:

- `rule_id: str` — `shadow_rule_<12 hex chars>`. Content-stable.
- `policy_surface: "filter_label_blocking"`
- `tier_scope: "T1" | "T2" | "T3"`
- `filter_name: str`
- `filter_version: str`
- `filter_label: str`
- `threshold_version: str`
- `simulated_action: "SIMULATED_BLOCK"`
- `direction: "tighten"`
- `source_row_count: int` — `len(source_recommendations)`.
- `source_recommendations: [...]` — sorted by `cohort_id`. Each entry: `cohort_id`, `evidence_class`, `policy_severity`, `review_priority`, `n_complete`, `cohort_rate`, `baseline_rate`, `lift_absolute`, `lift_relative`.

**Lineage chain** (Stage 15 must be able to follow this end-to-end):

```
Stage 14 manifest.json
  ├── stage14_version, stage14_schema_version
  ├── safe_for_live_policy_consumption=false, runtime_consumable=false
  ├── stage13_run_path, stage13_manifest_hash, stage13_candidate_csv_hash
  │     │
  │     └── Stage 13 manifest.json
  │           ├── safe_for_live_policy_consumption=false (verified)
  │           ├── stage12_run_path, stage12_manifest_hash
  │           ├── stage12_input_hashes (the four cohort CSVs)
  │           └── recommendation_set_version (content hash of candidate CSV)
  │
  ├── stage12_run_path, stage12_manifest_hash, stage12_long_csv_hash
  │     │
  │     └── Stage 12 manifest.json
  │           ├── run_id, schema_version="1", data_window_start/end
  │           └── pre/post-join row counts, primitives_analyzed
  │
  ├── stage13_recommendation_set_version (re-recorded for convenience)
  ├── rule_count, excluded_count, n_live_decisions, n_simulated_blocks
  ├── allowed_actions=["SIMULATED_BLOCK"]
  ├── overall_warning_flags
  ├── artifact_filenames (the 13 emitted files)
  └── git_commit
```

**What Stage 15 must NOT consume**:

- `excluded_recommendations.csv` is informational only. The exclusion reasons are diagnostic, not a list of "rejected" rules to reconsider.
- The replay-result CSVs (`shadow_policy_replay_results.csv`, `shadow_vs_live_decision_diff.csv`, etc.) are diagnostics. Stage 15 may surface them to a reviewer but must not treat their presence/absence as policy guidance.
- `stage14_run.log` is plain-text diagnostics and has no machine schema.
- The advisory `warning_flags` are reviewer hints, not normative gates.

**Stable identifiers Stage 15 can rely on**:

- `rule_id` is stable across Stage 14 reruns when the underlying rule identity (the seven-component canonical tuple) is unchanged. A Stage 13 re-run that re-emits the same candidate row will produce the same `rule_id` on the next Stage 14 run.
- `stage13_manifest_hash` and `stage12_manifest_hash` are stable identifiers for the input artifacts. Stage 15 should pin a review session to a specific pair of these hashes.
- `stage13_recommendation_set_version` is a content hash over the Stage 13 candidate CSV; it lets Stage 15 detect when the same logical Stage 13 review has been re-published with new evidence.

## 10. Test surface

Test files under `PHX2/tests/test_stage14_*.py` (7 files, 105 tests collected, all passing):

- `test_stage14_loader.py` — 21 tests. Schema-version mismatches (Stage 13 1.0 / 1.2 / 2.0 rejected; only "1.1" accepted), Stage 12 schema_version mismatches, `safe_for_live` invariant violations, missing-input + missing-column hard fails, `expected_manifest_hash` keyword requirement (TypeError if omitted), Stage 12 nullable bool coercion, and the four branches of `resolve_stage12_run_path`.
- `test_stage14_rules.py` — 21 tests. Eligibility gate matrix (each exclusion reason exercised), content-stable rule IDs across reruns and insertion reordering, tier / filter-version distinctness, duplicate-row collapse with all source cohort_ids preserved, gate ordering, the every-row-accounted-for invariant, and `compute_rule_id` format + sensitivity to each input field.
- `test_stage14_replay.py` — 12 tests. Single + multi-rule matches, tier / filter-tuple / missing-identity mismatches, deduped triggering rule IDs, non-`would_alert` decisions not flagged as changed, no-filter-row decisions producing SIMULATED_PASS, one-row-per-decision aggregation, output sort order, outcome-field carry-through.
- `test_stage14_metrics.py` — 12 tests. Aggregate counts by tier / rule / filter, every warning flag's positive trigger plus the `excessive_block_rate` boundary case (40% triggers, 20% does not) that anchors the post-pushback 0.3 threshold, non-`would_alert` decisions excluded from counts, zero-match rule, and filter aggregation across threshold_version variants.
- `test_stage14_writer.py` — 19 tests. `runtime_consumable=false` as bare JSON `false`, locked CSV column headers, byte-identical reruns, decision-diff and blocked / winners / saved-noise filtering, impact CSV ordering (overall first, then T1/T2/T3), warning-flag rendering, manifest sorted keys + trailing newline, run-log content, markdown empty-input safety, markdown rule-table population.
- `test_stage14_pipeline.py` — 12 tests. All 13 artifacts present, safety flags on manifest and rules JSON, byte-identical reruns at the pipeline level, Stage 12 + Stage 13 inputs unchanged after a run, Stage 12 override hash match + mismatch, default-path hash match + tampered-manifest mismatch (the Medium-finding scenario), block-count aggregation, exclusion accounting, manifest-mtime-after-others discipline, output-confined-to-run-dir invariant, zero-eligible-candidates path.
- `test_stage14_cli.py` — 8 tests. argparse plumbing for required + optional flags, exit code 2 for missing `--stage13-run` / missing `--stage12-run` paths, exit code 3 for invariant violations (`safe_for_live=true` and hash mismatch), happy-path stdout printing.

Fixtures at `PHX2/tests/fixtures/stage14/stage14_fixture_writer.py` (432 lines). The fixture writer materializes paired Stage 12 + Stage 13 run directories from in-memory `Stage12LongRow` and `Stage13CandidateRow` dataclasses, computes the Stage 12 manifest hash, and embeds it into the Stage 13 manifest so the integrity chain is intact. Default bundle covers: one ADVANCE T1 fee_gate_v1 scam_likely candidate, three Stage 12 long rows (winner, loser, no-outcome). Tests override either list to exercise winners-blocked, saved-noise, no-outcome, multi-rule, override-hash-mismatch, and tampered-manifest scenarios.

## 11. Codex audit findings and resolutions

- **Critical**: zero findings.
- **High**: zero findings.
- **Medium**: one finding, resolved pre-commit.
  - **M1** — Stage 14 must validate the Stage 12 manifest hash even when using the default Stage 12 path from the Stage 13 manifest, not only when `--stage12-run` is supplied. Resolution: rolled into commit `6c11b8a`. `resolve_stage12_run_path` was rewritten to require Stage 13's recorded `stage12_manifest_hash` in BOTH branches; the loader's hash check became unconditional. New tests `test_default_stage12_path_with_tampered_manifest_fails` and `test_default_stage12_path_with_matching_hash_succeeds` cover the scenario end-to-end.
- **Low**: one finding, resolved pre-commit.
  - **L1** — `load_stage12_run(..., expected_manifest_hash=None)` allowed direct callers to bypass the manifest hash check even though the CLI/pipeline path was already safe. Resolution: rolled into commit `6c11b8a`. The keyword argument is now required (no default); the `is not None` short-circuit was removed; callers must supply a hash. New test `test_load_stage12_requires_expected_manifest_hash_kwarg` pins down the TypeError when the keyword is omitted.
- **Informational / deferred**: four items not patched, documented as accepted for v0.
  - `12-hex rule_id collision risk` — 48 bits of entropy is sufficient for the rule-count Stage 14 ever produces in one run. Accepted for v0.
  - `crossed/compound-rule detector not implemented` — the v0 eligibility gate already excludes crossed rules at the surface level, so a dedicated detector is unnecessary at this stage.
  - `explicit DB/network guard tests` — the static import audit already passed; runtime guard tests are nice-to-have only.
  - `INSUFFICIENT_EVIDENCE exclusion test` — added pre-commit as a quick addition (`test_excludes_insufficient_evidence` in `test_stage14_rules.py`). The user noted this was optional but trivial; it is now in the suite.

## 12. Known limitations and explicit non-goals

Stage 14 v0 is intentionally narrow. The following are NOT in scope:

- No `primitive_bucket_cohort` rules — primitive-bucket cohorts always route to `not_filter_label_surface`.
- No loosen-direction rules — loosen rows always route to `not_tighten`.
- No `overall` tier rules — overall rows always route to `tier_scope_overall`.
- No `WARN`, `SOFT_BLOCK`, `DEPRIORITIZE`, or any other action class. The only emitted simulated action is `SIMULATED_BLOCK`.
- No crossed or compound rules. Every rule is single-axis on one filter identity tuple.
- No live policy mutation. Stage 14 produces no live-config writes, no threshold updates, no alert-behavior changes.
- No DB reads. No DB writes.
- No network access. No Discord, Telegram, gRPC, websocket, or HTTP traffic of any kind.
- No scoring, no ML, no model training, no inference.
- No threshold mutation. The numeric thresholds in `PHX2/stage14/types.py` are advisory warning-flag boundaries for review-time diagnostics, not live policy values.
- No runtime-consumable artifacts. Every output file carries `runtime_consumable=false` either on its own top-level (the rules JSON) or via the manifest's `safe_for_live_policy_consumption=false`.
- No mutation of Stage 12 or Stage 13 artifacts. Stage 14 only reads upstream input.
- No classification of rules or policies as "good" or "bad". The advisory flags are reviewer hints; pass/fail belongs to Stage 15.

## 13. Stage 14 anti-patterns to guard against in Stage 15

Stage 15's job is human approval. These are the design-level moves Stage 15 must NOT make, because each would erode a property Stage 14 currently guarantees:

- Do not promote any Stage 14 output file (`shadow_policy_rules.json`, any CSV, the manifest) to a runtime-consumable state without explicit human approval. The `runtime_consumable: false` flag is the contract; setting it true elsewhere in the pipeline is the exact failure mode Stage 14 was built to prevent.
- Do not treat Stage 14's `warning_flags` or `overall_warning_flags` as normative gates. They are reviewer hints. A clean flag set does not authorize promotion; a noisy flag set does not bar review.
- Do not modify, regenerate, re-sort, or post-process Stage 14 artifacts inside Stage 15. The artifact bytes are the audit record. Stage 15 must read them; if a change is needed, it must trigger a fresh Stage 14 run with new inputs.
- Do not open a DB connection or make a network call from Stage 15. Stage 15's job is artifact review, not data acquisition. If new evidence is needed, it belongs in a new Stage 12 / Stage 13 run that Stage 14 then re-replays.
- Do not infer rule approval from Stage 14 metrics alone. The replay numbers describe what would have happened on historical data; they do not authorize live behavior. Approval requires explicit human sign-off captured outside the Stage 14 artifact set.
- Do not break the lineage chain. Every Stage 15 review record should pin a specific `(stage14_run_id, stage14_manifest_hash, stage13_manifest_hash, stage12_manifest_hash)` tuple. A Stage 14 rerun against the same Stage 13 produces byte-identical rule bytes only when the inputs are byte-identical; any drift in upstream hashes invalidates the prior review.
- Do not reuse `rule_id` to encode review state. `rule_id` is a content hash; it carries identity, not approval. Stage 15's approval state belongs in a separate persistent store keyed by the rule_id, not encoded into the rule_id itself.
