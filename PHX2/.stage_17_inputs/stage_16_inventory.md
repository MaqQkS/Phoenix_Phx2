# Stage 16 Scope Inventory (read-only)

Produced by an inventory pass against the PHX2 repository at HEAD
`c6d55282ac7e7f2bf3c89598a86993546c708ae6` ("Stage 16B observe-only runtime
telemetry sidecar"). Read-only: no source files modified, no migrations run,
no commits made.

## Step 0 — Self-check (opening)

- `git status --short` (verbatim):
  ```
  ?? PHX2/docs/
  ?? ROADMAP.md
  ```
- `git log -1 --format="%H %s"` (verbatim):
  ```
  c6d55282ac7e7f2bf3c89598a86993546c708ae6 Stage 16B observe-only runtime telemetry sidecar
  ```
- PHX2 root: `C:\Users\BalaC\Downloads\Phoenix_PHX2\` (the Python package
  lives at `PHX2/` underneath the repo root).
- SQLite DB path used by tests: there is **no canonical persistent PHX2 DB on
  disk**. Every test creates a fresh ephemeral SQLite file under a pytest
  `--basetemp` directory (e.g. `.pytest_basetmp_stage16b_reaudit2_full_b/
  <test_dir>/stage16b_<uuid>.db`). The repo's `data/` directory exists but
  contains no `*.db` (and `data/*.db` is `.gitignore`d). For schema and
  example-data inspection this report uses a copy of one populated Stage 16B
  test fixture DB (placed in `%TEMP%`, opened via
  `sqlite3.connect('file:...?mode=ro', uri=True)`).
- Read-only path used: `file:%TEMP%\phx2_inv_ro.db?mode=ro` (URI read-only
  mode); no writes were issued against any DB during this inventory.

## Section 1 — Stage 16A files and behavior

Source commit: `52e1bf2200b58d5a5d66e6bb9d11ebff16484a3d` ("Stage 16A
observe-only runtime policy artifact and evaluator"). All Stage 16A files
were added in that single commit. Line counts below are from the current
working-tree files (which equal the commit-introduced sizes; the working
tree shows no Stage 16A modifications between Stage 16A and Stage 16B).

### 1.1 Files

**New (production) files** (all under `PHX2/stage16a/` plus one script):

| Path | Lines |
| --- | --- |
| `PHX2/stage16a/__init__.py` | 1 |
| `PHX2/stage16a/cli.py` | 373 |
| `PHX2/stage16a/errors.py` | 137 |
| `PHX2/stage16a/hashing.py` | 120 |
| `PHX2/stage16a/models.py` | 155 |
| `PHX2/stage16a/observe_only_policy_evaluator.py` | 101 |
| `PHX2/stage16a/observe_only_policy_loader.py` | 269 |
| `PHX2/stage16a/runtime_policy_builder.py` | 150 |
| `PHX2/stage16a/safety.py` | 178 |
| `PHX2/stage16a/stage15_loader.py` | 414 |
| `PHX2/scripts/run_stage16a.py` | 21 |

**Modified files**: `.gitignore` (added Stage 16A run-output exclusions:
`PHX2/stage16a_runs/`, `stage16a_runs/`).

**Migration files**: none. Stage 16A is artifact-only; it never opens a DB.

**Test files** (all under `PHX2/tests/stage16a/`):

| Path |
| --- |
| `PHX2/tests/stage16a/__init__.py` |
| `PHX2/tests/stage16a/conftest.py` |
| `PHX2/tests/stage16a/fixtures/__init__.py` |
| `PHX2/tests/stage16a/fixtures/builders.py` |
| `PHX2/tests/stage16a/test_cli_smoke.py` |
| `PHX2/tests/stage16a/test_determinism.py` |
| `PHX2/tests/stage16a/test_errors.py` |
| `PHX2/tests/stage16a/test_evaluator_matching.py` |
| `PHX2/tests/stage16a/test_evaluator_purity.py` |
| `PHX2/tests/stage16a/test_hashing.py` |
| `PHX2/tests/stage16a/test_import_boundaries.py` |
| `PHX2/tests/stage16a/test_manifest_lineage.py` |
| `PHX2/tests/stage16a/test_manifest_write_order.py` |
| `PHX2/tests/stage16a/test_models.py` |
| `PHX2/tests/stage16a/test_runtime_loader_clean.py` |
| `PHX2/tests/stage16a/test_runtime_loader_r_codes.py` |
| `PHX2/tests/stage16a/test_runtime_loader_safety_rejection.py` |
| `PHX2/tests/stage16a/test_runtime_policy_builder.py` |
| `PHX2/tests/stage16a/test_safety_constants.py` |
| `PHX2/tests/stage16a/test_stage15_loader_clean_run.py` |
| `PHX2/tests/stage16a/test_stage15_loader_l_codes.py` |
| `PHX2/tests/stage16a/test_three_tier_exit.py` |

### 1.2 Modules / classes / responsibilities

For each Stage 16A module, the responsibility (quoting module docstring
where present), public methods/signatures, and read/write surface:

#### `PHX2/stage16a/models.py`

- Responsibility (docstring):
  > "Stage 16A frozen dataclasses for loaded policies, decision contexts,
  > rule matches, and observe-only evaluation results. All dataclasses are
  > `frozen=True` so the evaluator pipeline cannot mutate shared state."
- Public dataclasses: `LoadedRule`, `LoadedObserveOnlyPolicy`,
  `FilterEvaluationSnapshot`, `DecisionContext`, `RuleMatch`,
  `RuleUnevaluable`, `ObserveOnlyEvaluationResult` (all `@dataclass(frozen=True)`).
- Reads: nothing (pure dataclasses).
- Writes: nothing.
- Network: none.
- Scheduler/daemon: none.

#### `PHX2/stage16a/hashing.py`

- Responsibility (docstring):
  > "Stage 16A hashing helpers. Two surfaces: Stage 15-style file-bytes /
  > raw-bytes SHA-256... Compact canonical-JSON helpers... used to compute
  > the Stage 16A runtime artifact's `policy_hash` field..."
- Public functions:
  - `canonical_json_dumps(value: Any) -> str`
  - `sha256_bytes(data: bytes) -> str` → `"sha256:<hex>"`
  - `sha256_file(path: Path) -> str` → `"sha256:<hex>"` (chunked read)
  - `sha256_canonical_dict(value: Any) -> str`
  - `sha256_canonical_file(path: Path) -> str`
- Reads: bytes from a `Path` when called.
- Writes: nothing.
- Network: none. Scheduler: none.

#### `PHX2/stage16a/safety.py`

- Responsibility (docstring):
  > "Stage 16A safety-surface constants: the single source of truth for what
  > a valid Stage 15 input and Stage 16A runtime artifact look like."
- Public constants: `ALLOWED_TIER_SCOPES`, `ALLOWED_FILTER_LABELS`,
  `REQUIRED_PREDICATE_KEYS_STAGE15`, `REQUIRED_PREDICATE_KEYS_RUNTIME`,
  `EXPECTED_STAGE15_SAFETY_SURFACE`, `EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE`,
  `EXPECTED_RUNTIME_SAFETY_SURFACE`.
- Public functions: `assert_subset_match(expected, actual, *, code, context="")`,
  `assert_exact_match(expected, actual, *, code, context="")`.
- Reads/Writes: none. Network: none. Scheduler: none.

#### `PHX2/stage16a/errors.py`

- Responsibility (docstring):
  > "Stage 16A error type and closed-set L01-L22 / R01-R08 / B01 error
  > codes."
- Public symbols: `L_CODES`, `R_CODES`, `B_CODES`, `ALL_CODES`,
  `MESSAGE_TEMPLATES`, `Stage16AError(code, detail="")`.
- Reads/Writes/Network/Scheduler: none.

#### `PHX2/stage16a/stage15_loader.py`

- Responsibility (docstring):
  > "Validates and loads a Stage 15 approved-draft artifact against the
  > L01-L22 load-time invariants."
- Public dataclass: `Stage15ApprovedDraft`.
- Public class: `Stage15ApprovedDraftLoader`
  - `.load(stage15_run_path: Path) -> Stage15ApprovedDraft`
- Public free functions:
  - `initialize_output_dir(output_dir: Path) -> None` (L21)
  - `capture_git_commit(repo_root: Path | None = None) -> str` (L22; calls
    `git rev-parse HEAD` via `subprocess.run`)
- Reads: file bytes from `manifest.json` and `approved_observe_only_policy_draft.json`
  inside the Stage 15 run directory.
- Writes: only directory creation in `initialize_output_dir` (creates the
  Stage 16A output dir if absent).
- Network: none. Scheduler: none.

#### `PHX2/stage16a/observe_only_policy_loader.py`

- Responsibility (docstring):
  > "Validates and loads an observe_only_runtime_policy.json artifact
  > against the R01-R08 runtime-load invariants. R-codes are checked in
  > declared order; first failure raises Stage16AError with the specific
  > code. The loader does NOT cache."
- Public class: `ObserveOnlyPolicyLoader`
  - `.load(runtime_policy_path: Path) -> LoadedObserveOnlyPolicy`
- Reads: bytes from `runtime_policy_path`. Writes: none. Network: none.

#### `PHX2/stage16a/runtime_policy_builder.py`

- Responsibility (docstring):
  > "Builds the Stage 16A observe_only_runtime_policy.json body from a
  > validated Stage 15 approved draft."
- Public class: `RuntimePolicyBuilder`
  - `.build(draft: Stage15ApprovedDraft, *, now_utc: datetime, git_commit: str) -> dict[str, Any]`
- Reads: only the in-memory `Stage15ApprovedDraft`.
- Writes: none (returns a dict; the CLI writes the file).
- Network: none. Scheduler: none.

#### `PHX2/stage16a/observe_only_policy_evaluator.py`

- Responsibility (docstring):
  > "Pure function. Returns matches against the loaded observe-only policy.
  > NEVER returns a blocking decision. NEVER writes. NEVER calls into alert
  > flow."
- Public class: `ObserveOnlyPolicyEvaluator(policy: LoadedObserveOnlyPolicy)`
  - `.evaluate_for_decision(context: DecisionContext) -> ObserveOnlyEvaluationResult`
- Reads/Writes: pure (no I/O).

#### `PHX2/stage16a/cli.py`

- Responsibility (docstring):
  > "Stage 16A CLI entry: parses args, dispatches the three-tier exit
  > pipeline, and never opens a DB or network connection."
- Public functions: `make_parser() -> argparse.ArgumentParser`,
  `main(argv: list[str] | None = None) -> int`.
- Public exit-code constants: `EXIT_OK=0`, `EXIT_OUTPUT_DIR_FAIL=2`,
  `EXIT_LOAD_TIME_FAIL=3`, `EXIT_UNEXPECTED=5`.
- Public filename constants: `RUN_LOG_FILENAME="stage16a_run.log"`,
  `MANIFEST_FILENAME="stage16a_manifest.json"`,
  `RUNTIME_POLICY_FILENAME="observe_only_runtime_policy.json"`.
- Reads: Stage 15 input directory (via `Stage15ApprovedDraftLoader`).
- Writes: three files in `--output-dir`:
  `observe_only_runtime_policy.json`, `stage16a_run.log`,
  `stage16a_manifest.json`. Manifest is written via `os.replace` from a
  `.tmp` sibling for atomicity.
- Network: none. Scheduler: none.

#### `PHX2/scripts/run_stage16a.py`

- 21-line thin wrapper that prepends the repo root to `sys.path` and calls
  `PHX2.stage16a.cli.main()`.

**Network surface (verified)**: `grep -rE "requests|httpx|urllib|socket\."
PHX2/stage16a/` returns nothing. Stage 16A makes no network calls. The
only subprocess call is `git rev-parse HEAD` in
`stage15_loader.capture_git_commit`.

**Scheduler/daemon/background loop**: none. No `schedule`, `daemon`,
`asyncio.run_forever`, or `cron` references; the only `while True:` loop
in Stage 16A is a 64 KiB chunked file-read in `hashing.sha256_file` (line
85), which terminates on EOF.

### 1.3 Observe-only runtime policy artifact format

- File format: **JSON** (pretty-printed: `sort_keys=True, indent=2,
  ensure_ascii=False, trailing newline`; see `cli._json_bytes` at
  [PHX2/stage16a/cli.py:274](PHX2/stage16a/cli.py:274)).
- Location on disk: the file `observe_only_runtime_policy.json` inside a
  Stage 16A run output dir (`--output-dir`, by convention under
  `PHX2/stage16a_runs/`). Not stored in any DB.
- Top-level shape (from `RuntimePolicyBuilder.build`):
  ```python
  body = {
      "schema_version": "observe_only_runtime_policy_v0",
      "rule_count": len(rules_out),
      "generated_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
      "git_commit": git_commit,
      "safety_surface": safety_surface,   # exact-match dict
      "lineage": lineage,                  # 12+ Stage 15/14/13/12 hashes
      "rules": rules_out,                  # list of rule dicts
      "policy_hash": sha256_canonical_dict(body)   # added after build
  }
  ```
- A "rule" carries exactly these fields (per `RuntimePolicyBuilder.build`
  at [PHX2/stage16a/runtime_policy_builder.py:91-105](PHX2/stage16a/runtime_policy_builder.py:91)):
  ```python
  {
      "rule_id": str,
      "predicate": {
          "tier_scope": str,            # T1 | T2 | T3
          "filter_name": str,
          "filter_version": str,
          "filter_label": str,          # NORMAL | ELEVATED | SUSPICIOUS | SCAM_LIKELY | UNKNOWN
          "threshold_version": str,
      },
      "intended_action": "LOG_WOULD_BLOCK",
      "hard_block_allowed": False,
      "source_stage14_rule_hash": str,
      "operator_reason": str,
      "reviewed_at_utc": str,
  }
  ```
- A "policy" carries (per `models.LoadedObserveOnlyPolicy` and the body
  shape):
  - `schema_version` literal `"observe_only_runtime_policy_v0"`
  - `policy_hash` (sha256 over canonical JSON of body sans policy_hash)
  - `generated_at_utc` (ISO 8601 UTC)
  - `git_commit` (40-hex)
  - `rules: tuple[LoadedRule, ...]`
  - `lineage` (MappingProxyType of Stage 15/14/13/12 hashes + reviewer)
  - **No "enabled" flag**. **No "version" beyond `schema_version`.**
  - `safety_surface` is on the artifact body but not on `LoadedObserveOnlyPolicy`;
    the loader validates the surface and discards it.
- `policy_hash` is computed via `sha256_canonical_dict` (quoted verbatim
  from [PHX2/stage16a/hashing.py:98-106](PHX2/stage16a/hashing.py:98)):
  ```python
  def sha256_canonical_dict(value: Any) -> str:
      """Return ``"sha256:<hex>"`` over ``canonical_json_dumps(value)``.

      Used to compute the Stage 16A runtime artifact's ``policy_hash`` over
      the body dict sans the ``policy_hash`` field itself.
      """

      encoded = canonical_json_dumps(value).encode("utf-8")
      return sha256_bytes(encoded)
  ```
  …where `canonical_json_dumps` is `json.dumps(value, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)` (no trailing newline).
  The builder applies this to `body` **before** the `policy_hash` field is
  added (see [PHX2/stage16a/runtime_policy_builder.py:128-129](PHX2/stage16a/runtime_policy_builder.py:128)).
- Representative example exists in the build fixture but no fixture-pinned
  on-disk artifact is committed; tests synthesize body shape via
  `RuntimePolicyBuilder.build`.

### 1.4 How Stage 16A evaluates a rule against an alert_decision

- Entry-point method and signature (from
  [PHX2/stage16a/observe_only_policy_evaluator.py:42-44](PHX2/stage16a/observe_only_policy_evaluator.py:42)):
  ```python
  def evaluate_for_decision(
      self, context: DecisionContext
  ) -> ObserveOnlyEvaluationResult
  ```
- Inputs consumed: a `DecisionContext` (frozen dataclass) carrying
  `alert_decision_id: int`, `tier_name: Optional[str]`,
  `filter_evaluations: tuple[FilterEvaluationSnapshot, ...]`,
  `evaluated_at_utc: Optional[str]`. The evaluator was constructed with a
  bound `LoadedObserveOnlyPolicy`.
- Output structure: `ObserveOnlyEvaluationResult(alert_decision_id,
  policy_hash, matched_rules: tuple[RuleMatch, ...], unevaluable_rules:
  tuple[RuleUnevaluable, ...], enforcement_effect="NONE",
  dispatch_allowed=True, live_decision_mutated=False)` (the latter three
  are Literal-typed defaults; the evaluator has no path that produces any
  other value).
- The output is **NOT persisted by Stage 16A**. Stage 16A writes only its
  three on-disk artifact files (manifest, runtime policy, run log).
  Stage 16B persists per-rule evaluation rows into
  `observe_only_policy_evaluations`.
- "evaluation_status" is a Stage **16B** concept (string column on
  `observe_only_policy_evaluations` with values `'MATCHED'`,
  `'NOT_MATCHED'`, `'UNEVALUABLE'`, enforced by a CHECK constraint — see
  Section 2.3). **Stage 16A has no `evaluation_status` enum**. Its
  evaluator returns `RuleMatch` and `RuleUnevaluable` dataclasses, and
  `RuleUnevaluable.reason` carries the literal string
  `"tier_name_missing_on_decision"` (constant
  `_TIER_MISSING_REASON` at
  [PHX2/stage16a/observe_only_policy_evaluator.py:29](PHX2/stage16a/observe_only_policy_evaluator.py:29);
  this is the only `RuleUnevaluable.reason` value emitted by the current
  evaluator).

## Section 2 — Stage 16B files and behavior

Source commit: `c6d55282ac7e7f2bf3c89598a86993546c708ae6` ("Stage 16B
observe-only runtime telemetry sidecar"). All Stage 16B files were added
or modified in that single commit.

### 2.1 Files

**New files** (production):

| Path | Lines |
| --- | --- |
| `PHX2/stage16b/__init__.py` | 1 |
| `PHX2/stage16b/cli.py` | 260 |
| `PHX2/stage16b/decision_context_assembler.py` | 92 |
| `PHX2/stage16b/errors.py` | 90 |
| `PHX2/stage16b/migrations.py` | 34 |
| `PHX2/stage16b/models.py` | 61 |
| `PHX2/stage16b/observer.py` | 185 |
| `PHX2/stage16b/repository.py` | 208 |
| `PHX2/stage16b/row_builder.py` | 142 |
| `PHX2/scripts/run_stage16b_observer_once.py` | 22 |

**Modified files**:

| Path | +Lines | −Lines |
| --- | --- | --- |
| `.gitignore` | 8 | 1 |
| `PHX2/db/__init__.py` | +196 / −0 (re-exports Stage 16B migration symbols) |  |
| `PHX2/db/migrations.py` | 392 | 0 (added Stage 16B SQL, validators, and the `apply_stage16b_*` functions) |

**Test files** (all under `PHX2/tests/stage16b/`):

| Path |
| --- |
| `PHX2/tests/stage16b/__init__.py` |
| `PHX2/tests/stage16b/conftest.py` (20 lines) |
| `PHX2/tests/stage16b/fixtures/__init__.py` |
| `PHX2/tests/stage16b/fixtures/builders.py` (270 lines) |
| `PHX2/tests/stage16b/test_cli.py` (576 lines) |
| `PHX2/tests/stage16b/test_cli_smoke.py` (20) |
| `PHX2/tests/stage16b/test_decision_context_assembler.py` (412) |
| `PHX2/tests/stage16b/test_determinism.py` (279) |
| `PHX2/tests/stage16b/test_import_boundaries.py` (638) |
| `PHX2/tests/stage16b/test_integration_end_to_end.py` (459) |
| `PHX2/tests/stage16b/test_migration.py` (838) |
| `PHX2/tests/stage16b/test_models.py` (163) |
| `PHX2/tests/stage16b/test_observer_idempotency.py` (241) |
| `PHX2/tests/stage16b/test_observer_matching.py` (423) |
| `PHX2/tests/stage16b/test_observer_non_mutation.py` (189) |
| `PHX2/tests/stage16b/test_observer_partial_crash.py` (190) |
| `PHX2/tests/stage16b/test_observer_uses_stage16a_evaluator.py` (191) |
| `PHX2/tests/stage16b/test_repository.py` (527) |
| `PHX2/tests/stage16b/test_row_builder.py` (591) |

**Migration files**: not separate files — the Stage 16B DDL,
column/index/UNIQUE/FK invariants, and `apply_stage16b_*` functions live
inside `PHX2/db/migrations.py` (lines 31, 1201-1548). Stage 16B's own
`PHX2/stage16b/migrations.py` is a 34-line re-export shim that imports
from `PHX2.db.migrations` to keep Stage 16B's package boundary clean.

### 2.2 Modules / classes / responsibilities

#### `PHX2/stage16b/models.py`

- Docstring: "Stage 16B frozen dataclasses for one telemetry row and the
  per-run observer report; pure data, no I/O."
- Public: `ObserveOnlyEvaluationRow` (frozen),
  `ObserverRunReport` (frozen).
- Reads/Writes/Network/Scheduler: none.

#### `PHX2/stage16b/errors.py`

- Docstring: "Stage 16B closed-set error codes (M01-M08) and exception type
  used by the observer CLI, migration check, and repository surfaces."
- Public: `M_CODES`, `ALL_CODES`, `MESSAGE_TEMPLATES`,
  `Stage16BError(code, detail="")`.
- Reads/Writes/Network/Scheduler: none.

#### `PHX2/stage16b/migrations.py`

- Docstring: "Stage 16B owns this one table. Migration is not auto-applied;
  observer fails M01 if table is missing."
- Pure re-export of: `EXPECTED_STAGE_16B_COLUMNS`,
  `EXPECTED_STAGE_16B_FOREIGN_KEY`, `EXPECTED_STAGE_16B_INDEXES`,
  `EXPECTED_STAGE_16B_UNIQUE_COLUMNS`,
  `STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL`, `STAGE_16B_VERSION`,
  `Stage16BMigrationError`,
  `apply_stage16b_observe_only_policy_evaluations`,
  `apply_stage16b_schema` (all defined in `PHX2/db/migrations.py`).

#### `PHX2/stage16b/decision_context_assembler.py`

- Docstring: "Reads one alert_decisions row plus its filter_evaluations
  rows from the PHX2 SQLite DB and builds a Stage 16A DecisionContext;
  read-only, never writes."
- Public class: `DecisionContextAssembler(connection)`
  - `.assemble(alert_decision_id: int) -> Optional[DecisionContext]`
- Reads (SQL):
  - `SELECT id, tier_name FROM alert_decisions WHERE id = ?`
  - `SELECT filter_name, filter_version, label, threshold_version FROM
    filter_evaluations WHERE alert_decision_id = ? ORDER BY id ASC`
- Writes: none (read-only). Network: none. Scheduler: none.

#### `PHX2/stage16b/repository.py`

- Docstring: "Append-only. No update_*, delete_*, mutate_*, mark_*,
  save_*, upsert_*, set_*, or clear_* methods. Owns exactly one table:
  observe_only_policy_evaluations."
- Public class: `ObserveOnlyEvaluationRepository(connection: sqlite3.Connection)`
  - `.insert_evaluation_rows(rows: Sequence[ObserveOnlyEvaluationRow]) -> int`
  - `.list_alert_decision_ids_missing_policy_eval(policy_hash: str, limit: int) -> tuple[int, ...]`
  - `.count_evaluations_for_policy(policy_hash: str) -> int`
  - `._commit_if_top_level(was_in_transaction: bool)` (helper)
- Module-level constants: `WOULD_ALERT_DECISION_TYPE = "would_alert"`,
  `WOULD_ALERT_FLAG = 1`.
- Reads (SQL): SELECT from `alert_decisions` for the anti-join (column
  references `decision_type`, `would_alert`, `id`) plus
  `observe_only_policy_evaluations` for the NOT EXISTS clause.
- Writes (SQL): `INSERT OR IGNORE INTO observe_only_policy_evaluations
  (… 11 columns …) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`. The
  repository owns the `created_at_utc` stamp at insert time (function
  `_now_utc_iso`).
- Network: none. Scheduler: none.

#### `PHX2/stage16b/row_builder.py`

- Docstring: "Pure function that turns one ObserveOnlyEvaluationResult plus
  its source LoadedObserveOnlyPolicy into one row per policy rule (MATCHED,
  NOT_MATCHED, or UNEVALUABLE); no I/O."
- Public function: `build_rows_for_decision(alert_decision_id, tier_name,
  policy, result, evaluated_at_utc) -> tuple[ObserveOnlyEvaluationRow, ...]`.
- Output row count is ALWAYS `len(policy.rules)`.
- `evaluation_status` literals emitted: `"MATCHED"`, `"NOT_MATCHED"`,
  `"UNEVALUABLE"` (string literals — no `evaluation_status` enum
  anywhere in PHX2).
- Reads/Writes/Network/Scheduler: none.

#### `PHX2/stage16b/observer.py`

- Docstring: "Sidecar one-shot observer. Reads already-committed alert
  decisions, evaluates against an observe-only runtime policy via Stage
  16A's pure evaluator, writes append-only telemetry. NEVER returns a
  value consumed by alert eligibility or dispatch. NEVER mutates any
  upstream table. Safe to never run; safe to crash."
- Public class: `ObserveOnlyObserverService(policy_loader, evaluator_factory,
  assembler, repository, clock)`
  - `.run_once(runtime_policy_path: Path, limit: int) -> ObserverRunReport`
- Reads: indirectly via injected `assembler` and `repository`.
- Writes: indirectly via injected `repository.insert_evaluation_rows`.
- Network: none. Scheduler: none — explicit one-shot ("`No daemon. No
  enforcement.`" per CLI prog description).

#### `PHX2/stage16b/cli.py`

- Docstring: "Stage 16B CLI entry: parses CLI args, runs the one-shot
  observer, prints a single summary line to stdout, exits with the locked
  exit-code class (0/2/3/4/5)."
- Public: `make_parser`, `main(argv=None) -> int`.
- Exit codes: `EXIT_OK=0`, `EXIT_CLI_ARG_ERROR=2`, `EXIT_LOAD_ERROR=3`,
  `EXIT_RUNTIME_ERROR=4`, `EXIT_UNEXPECTED=5`.
- Required CLI flags: `--runtime-policy-path` (Path),
  `--db-path` (Path), `--limit` (int ≥ 0).
- Reads: opens the DB at `--db-path` via raw `sqlite3.connect`
  (deliberately not `PHX2.db.connection`), checks the three required
  tables (`observe_only_policy_evaluations`, `alert_decisions`,
  `filter_evaluations`) via `sqlite_master`, then runs the observer.
- Writes (DB): rows into `observe_only_policy_evaluations` via the
  repository (only via the observer's `run_once`).
- Writes (stdout): a single locked-format summary line on clean run.
- Network: none. Scheduler: none.

#### `PHX2/scripts/run_stage16b_observer_once.py`

- 22-line thin wrapper; prepends repo root to `sys.path` and delegates to
  `PHX2.stage16b.cli.main`.

**Network surface (verified)**: `grep -rE "requests|httpx|urllib|socket\."
PHX2/stage16b/` returns nothing.

**Scheduler/daemon**: none. The CLI prog description says "No daemon.";
the only `while True:` loop in Stage 16B-adjacent code is the chunked-read
loop inside `PHX2/stage16a/hashing.py` (not Stage 16B itself).

### 2.3 `observe_only_policy_evaluations` table

CREATE TABLE SQL (verbatim from `STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL`
at [PHX2/db/migrations.py:1201-1247](PHX2/db/migrations.py:1201)):

```sql
CREATE TABLE IF NOT EXISTS observe_only_policy_evaluations (
    id INTEGER PRIMARY KEY,
    alert_decision_id INTEGER NOT NULL,
    tier_name_snapshot TEXT,
    policy_hash TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    evaluation_status TEXT NOT NULL,
    matched INTEGER NOT NULL,
    would_have_blocked INTEGER NOT NULL,
    unevaluable_reason TEXT,
    predicate_snapshot_json TEXT NOT NULL,
    evaluated_at_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,

    CHECK (evaluation_status IN ('MATCHED', 'NOT_MATCHED', 'UNEVALUABLE')),
    CHECK (matched IN (0, 1)),
    CHECK (would_have_blocked IN (0, 1)),
    CHECK (
        (evaluation_status = 'MATCHED'
            AND matched = 1
            AND would_have_blocked = 1
            AND unevaluable_reason IS NULL)
        OR
        (evaluation_status = 'NOT_MATCHED'
            AND matched = 0
            AND would_have_blocked = 0
            AND unevaluable_reason IS NULL)
        OR
        (evaluation_status = 'UNEVALUABLE'
            AND matched = 0
            AND would_have_blocked = 0
            AND unevaluable_reason IS NOT NULL)
    ),
    UNIQUE(alert_decision_id, policy_hash, rule_id),
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_decision
    ON observe_only_policy_evaluations(alert_decision_id);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_policy_rule_time
    ON observe_only_policy_evaluations(policy_hash, rule_id, evaluated_at_utc);

CREATE INDEX IF NOT EXISTS idx_observe_only_policy_eval_status
    ON observe_only_policy_evaluations(evaluation_status);
```

`PRAGMA table_info('observe_only_policy_evaluations')` (against a populated
test fixture DB; same shape on any fresh-migrated DB):

```
cid name                       type     notnull dflt   pk
 0  id                          INTEGER  0       NULL    1
 1  alert_decision_id           INTEGER  1       NULL    0
 2  tier_name_snapshot          TEXT     0       NULL    0
 3  policy_hash                 TEXT     1       NULL    0
 4  rule_id                     TEXT     1       NULL    0
 5  evaluation_status           TEXT     1       NULL    0
 6  matched                     INTEGER  1       NULL    0
 7  would_have_blocked          INTEGER  1       NULL    0
 8  unevaluable_reason          TEXT     0       NULL    0
 9  predicate_snapshot_json     TEXT     1       NULL    0
10  evaluated_at_utc            TEXT     1       NULL    0
11  created_at_utc              TEXT     1       NULL    0
```

`PRAGMA index_list('observe_only_policy_evaluations')` (verbatim):

```
seq name                                                          unique origin partial
 0  idx_observe_only_policy_eval_status                            0      c      0
 1  idx_observe_only_policy_eval_policy_rule_time                  0      c      0
 2  idx_observe_only_policy_eval_decision                          0      c      0
 3  sqlite_autoindex_observe_only_policy_evaluations_1             1      u      0
```

`PRAGMA index_info(<each>)`:

```
idx_observe_only_policy_eval_status:
  seqno=0 cid=5 name=evaluation_status
idx_observe_only_policy_eval_policy_rule_time:
  seqno=0 cid=3 name=policy_hash
  seqno=1 cid=4 name=rule_id
  seqno=2 cid=10 name=evaluated_at_utc
idx_observe_only_policy_eval_decision:
  seqno=0 cid=1 name=alert_decision_id
sqlite_autoindex_observe_only_policy_evaluations_1 (UNIQUE):
  seqno=0 cid=1 name=alert_decision_id
  seqno=1 cid=3 name=policy_hash
  seqno=2 cid=4 name=rule_id
```

`PRAGMA foreign_key_list('observe_only_policy_evaluations')` (verbatim):

```
id=0 seq=0 table=alert_decisions from=alert_decision_id to=id
  on_update=NO ACTION on_delete=NO ACTION match=NONE
```

UNIQUE constraints (and their columns):
- `UNIQUE(alert_decision_id, policy_hash, rule_id)` — backed by
  `sqlite_autoindex_observe_only_policy_evaluations_1`.

Column representing "would this rule have blocked this decision": exact
name `would_have_blocked` (type `INTEGER`, NOT NULL, CHECK constrained to
{0, 1}; bound to `matched` via the compound CHECK so it is 1 iff the row
is MATCHED).

### 2.4 How Stage 16B writes rows

- Insert method: `ObserveOnlyEvaluationRepository.insert_evaluation_rows`
  ([PHX2/stage16b/repository.py:83-142](PHX2/stage16b/repository.py:83)).
- When in alert flow: **not in the alert flow**. Stage 16B runs strictly
  as a one-shot sidecar process invoked via
  `PHX2/scripts/run_stage16b_observer_once.py` /
  `PHX2.stage16b.cli.main`. The CLI prog description (verbatim):
  > "Stage 16B: one-shot sidecar observer. Evaluates already-committed
  > WOULD_ALERT alert decisions against a Stage 16A observe-only runtime
  > policy and writes append-only telemetry to
  > observe_only_policy_evaluations. No daemon. No enforcement. No
  > alert-flow integration."
  It is therefore neither synchronous with `AlertEligibilityEngine` nor
  triggered after a decision; rows are emitted on-demand when an operator
  runs the script.
- Trigger predicate: `list_alert_decision_ids_missing_policy_eval` filters
  to **decisions where `decision_type='would_alert' AND would_alert=1`**
  (constants `WOULD_ALERT_DECISION_TYPE` and `WOULD_ALERT_FLAG` at
  [PHX2/stage16b/repository.py:18-19](PHX2/stage16b/repository.py:18)),
  AND that have no telemetry row for the given `policy_hash` (anti-join
  via `NOT EXISTS`). One run-pass emits exactly `len(policy.rules)` rows
  per qualifying decision (see Section 2.3 row-count invariant in
  `row_builder`).
- Use of `PHX2Connection.transaction()` and `_commit_if_top_level`: Stage
  16B deliberately does **not** use `PHX2Connection`. Quoting the
  repository docstring ([PHX2/stage16b/repository.py:34-50](PHX2/stage16b/repository.py:34)):
  > "Accepts a raw `sqlite3.Connection`. The repository deliberately
  > does NOT subclass `PHX2.db.repositories.RepositoryContract` and does
  > NOT use `PHX2.db.connection.PHX2Connection`: importing either of
  > those modules would transitively load `PHX2.config.settings` and
  > `PHX2.models` / `PHX2.models.enums`, widening Stage 16B's sidecar
  > import boundary beyond the locked surface (the audit flagged this as
  > a HIGH finding and required the move to raw sqlite3)."
  It implements its own `_commit_if_top_level` (verbatim at
  [PHX2/stage16b/repository.py:57-79](PHX2/stage16b/repository.py:57)):
  ```python
  def _commit_if_top_level(self, was_in_transaction: bool) -> None:
      if not was_in_transaction:
          self.connection.commit()
  ```
  Snapshot of `connection.in_transaction` taken **before** the loop of
  `execute(INSERT OR IGNORE …)` calls (lines 104-106), then commit at end
  if the snapshot was `False`. In practice the observer never composes
  writes under an outer transaction (Stage 16B doc comment, line 73-76).
- Idempotency: re-run on the same `(alert_decision_id, policy_hash,
  rule_id)` is handled by **`INSERT OR IGNORE`** against the UNIQUE
  constraint (DDL line 1235 — `UNIQUE(alert_decision_id, policy_hash,
  rule_id)`). `cursor.rowcount` is 0 for an ignored insert, so the
  repository accumulates `inserted += cursor.rowcount` and returns the
  count of newly-written rows; the duplicates are silently dropped. A
  second observer pass thus produces `rows_ignored_duplicates == total
  emitted` and `rows_inserted == 0` for already-evaluated decisions. The
  observer additionally short-circuits the second pass entirely via
  `list_alert_decision_ids_missing_policy_eval`'s NOT EXISTS anti-join,
  which excludes any decision that has at least one telemetry row for the
  given `policy_hash`. (See
  [PHX2/stage16b/repository.py:146-192](PHX2/stage16b/repository.py:146).)

### 2.5 Current data in `observe_only_policy_evaluations`

There is no persistent PHX2 database. The repo's `data/` directory is
empty; all `*.db` files exist only under pytest `--basetemp` directories
(which are `.gitignore`d). To produce a representative inventory, this
report queries a copy of one rich Stage 16B test fixture (the
`test_observer_two_fresh_runs_p0/run_b/stage16b_<uuid>.db` snapshot,
copied read-only to `%TEMP%`); a second smaller fixture
(`test_cli_multi_decision_run_wr0`) was also queried. Both are illustrative
of the Stage 16B output shape but are **NOT a "current production"
inventory** — none exists.

Test fixture `test_observer_two_fresh_runs_p0/run_b/<uuid>.db`:

- Total rows: 3 alert_decisions × 2 policy rules = 6.
- DISTINCT `policy_hash`:
  `sha256:1f7a684c7439b2a29c962178c8902facfb78e3136704abc824c08ffa3c45cf44 → 6`
- DISTINCT `rule_id` (count):
  `rule_t2_fee_gate_scam_likely → 3`,
  `rule_t1_fee_gate_normal → 3`.
- DISTINCT `evaluation_status` (count):
  `NOT_MATCHED → 3`, `UNEVALUABLE → 2`, `MATCHED → 1`.
- DISTINCT `would_have_blocked` (count):
  `0 → 5`, `1 → 1`.
- Rows whose `alert_decision_id` resolves to WOULD_ALERT vs other:
  `WOULD_ALERT → 6` (all rows in this fixture).

Test fixture `test_cli_multi_decision_run_wr0/<uuid>.db`:

- Total rows: 3.
- DISTINCT `policy_hash`:
  `sha256:6c156fe5a06b5f14f8c9cfa83ff78a59a0894bc6c8d1fdeeccfc4e3874c6ae34 → 3`.
- DISTINCT `rule_id`: `rule_t2_fee_gate_scam_likely → 3`.
- DISTINCT `evaluation_status`: `MATCHED → 3`.
- DISTINCT `would_have_blocked`: `1 → 3`.
- All 3 rows resolve to a WOULD_ALERT `alert_decision`.

## Section 3 — Adjacent table schemas needed by Stage 17

### 3.1 `alert_decisions`

CREATE TABLE SQL (verbatim from `CORE_TELEMETRY_SQL` at
[PHX2/db/migrations.py:142-184](PHX2/db/migrations.py:142); the
post-Stage-9A `current_price`/`current_mcap` columns are included in
`CORE_TELEMETRY_SQL` itself so fresh test DBs are byte-equivalent to
post-Stage-9 production DBs):

```sql
CREATE TABLE IF NOT EXISTS alert_decisions (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    tier_index INTEGER,
    tier_name TEXT,
    primary_reason TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    would_alert INTEGER NOT NULL,
    blocked INTEGER NOT NULL,
    skipped INTEGER NOT NULL,
    price_observation_id INTEGER,
    ath_event_id INTEGER,
    field_features_id INTEGER,
    score_features_id INTEGER,
    clock_features_id INTEGER,
    field_score REAL,
    setup_score REAL,
    clock_score REAL,
    risk_score REAL,
    composite_score REAL,
    ath_price REAL,
    ath_status TEXT NOT NULL,
    ath_confidence TEXT NOT NULL,
    ath_source TEXT,
    price_age_seconds REAL,
    pump_multiple REAL,
    drawdown_from_ath REAL,
    -- current_price / current_mcap: written by AlertEligibilityEngine starting Stage 9.
    -- Included in CORE_TELEMETRY_SQL so fresh-DB test fixtures match production DBs after
    -- Stage 9A's ALTER TABLE migration. Stage 9A (apply_stage9_alert_decision_extension)
    -- remains authoritative for upgrading pre-Stage-9 production databases.
    current_price REAL,
    current_mcap REAL,
    filter_labels_json TEXT NOT NULL DEFAULT '{}',
    tier_context_json TEXT NOT NULL DEFAULT '{}',
    key_feature_snapshot_json TEXT NOT NULL DEFAULT '{}',
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);
```

`PRAGMA table_info(alert_decisions)`:

```
cid name                       type     notnull dflt   pk
 0  id                          INTEGER  0       NULL    1
 1  token_address               TEXT     1       NULL    0
 2  evaluated_at                TEXT     1       NULL    0
 3  decision_type               TEXT     1       NULL    0
 4  tier_index                  INTEGER  0       NULL    0
 5  tier_name                   TEXT     0       NULL    0
 6  primary_reason              TEXT     1       NULL    0
 7  reasons_json                TEXT     1       '[]'    0
 8  would_alert                 INTEGER  1       NULL    0
 9  blocked                     INTEGER  1       NULL    0
10  skipped                     INTEGER  1       NULL    0
11  price_observation_id        INTEGER  0       NULL    0
12  ath_event_id                INTEGER  0       NULL    0
13  field_features_id           INTEGER  0       NULL    0
14  score_features_id           INTEGER  0       NULL    0
15  clock_features_id           INTEGER  0       NULL    0
16  field_score                 REAL     0       NULL    0
17  setup_score                 REAL     0       NULL    0
18  clock_score                 REAL     0       NULL    0
19  risk_score                  REAL     0       NULL    0
20  composite_score             REAL     0       NULL    0
21  ath_price                   REAL     0       NULL    0
22  ath_status                  TEXT     1       NULL    0
23  ath_confidence              TEXT     1       NULL    0
24  ath_source                  TEXT     0       NULL    0
25  price_age_seconds           REAL     0       NULL    0
26  pump_multiple               REAL     0       NULL    0
27  drawdown_from_ath           REAL     0       NULL    0
28  current_price               REAL     0       NULL    0
29  current_mcap                REAL     0       NULL    0
30  filter_labels_json          TEXT     1       '{}'    0
31  tier_context_json           TEXT     1       '{}'    0
32  key_feature_snapshot_json   TEXT     1       '{}'    0
33  policy_version              TEXT     1       NULL    0
34  created_at                  TEXT     1       NULL    0
35  data_status                 TEXT     1       NULL    0
36  missing_reasons_json        TEXT     1       '[]'    0
```

`PRAGMA index_list(alert_decisions)` (all non-unique secondary indexes;
no UNIQUE constraints other than the implicit PK):

```
idx_alert_decisions_policy_version   on (policy_version)
idx_alert_decisions_tier_index       on (tier_index)
idx_alert_decisions_would_alert      on (would_alert)
idx_alert_decisions_primary_reason   on (primary_reason)
idx_alert_decisions_decision_type    on (decision_type)
idx_alert_decisions_token_eval       on (token_address, evaluated_at)
```

`PRAGMA foreign_key_list(alert_decisions)`: **(none).** `alert_decisions`
has no outbound FKs (its referenced columns
`price_observation_id`/`ath_event_id`/`field_features_id`/etc. are not
declared as FKs in the DDL).

DISTINCT `decision_type` values (queried against the two test fixtures
combined, since there is no production DB):
- `would_alert → 6` (in both fixtures all decisions are WOULD_ALERT).

The full `DecisionType` enum vocabulary (from
[PHX2/models/enums.py:54-61](PHX2/models/enums.py:54)) is:

```python
class DecisionType(str, Enum):
    WOULD_ALERT = "would_alert"
    SKIP = "skip"
    BLOCK = "block"
    ERROR = "error"
```

DISTINCT `tier_name` values:
- Larger fixture (`test_observer_two_fresh_runs_p0/run_b`): `None → 1`,
  `'T1' → 1`, `'T3' → 1` (NOTE: NULL tier_name present on a WOULD_ALERT row).
- Smaller fixture (`test_cli_multi_decision_run_wr0`): `'T2' → 3`.

`as_of_time` on `alert_decisions`: **not a stored column** on
`alert_decisions`. The closest stored column is `evaluated_at TEXT NOT NULL`.
`as_of_time` IS a stored column on `filter_evaluations` and
`decision_score_features` (both `TEXT NOT NULL`).

Total `alert_decisions` row counts:
- Larger fixture: 3 total; 3 WOULD_ALERT.
- Smaller fixture: 3 total; 3 WOULD_ALERT.

### 3.2 `outcome_windows`

Canonical name: **`outcome_windows`** (the user's prompt matches the
actual name). The current schema is the Stage 9B recreate, not the Stage
4B scaffold.

CREATE TABLE SQL (verbatim from `STAGE_9_OUTCOME_WINDOWS_SQL` at
[PHX2/db/migrations.py:709-748](PHX2/db/migrations.py:709)):

```sql
CREATE TABLE outcome_windows (
    id INTEGER PRIMARY KEY,
    alert_decision_id INTEGER NOT NULL,
    token_address TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    window_start_time TEXT NOT NULL,
    window_end_time TEXT NOT NULL,
    alert_price REAL,
    alert_mcap REAL,
    max_price REAL,
    max_mcap REAL,
    max_observation_time TEXT,
    min_price REAL,
    min_mcap REAL,
    min_observation_time TEXT,
    max_return_multiple REAL,
    max_return_pct REAL,
    min_return_multiple REAL,
    min_return_pct REAL,
    max_drawdown_from_peak_pct REAL,
    time_to_max_return_seconds REAL,
    hit_2x INTEGER,
    hit_3x INTEGER,
    hit_5x INTEGER,
    observations_count INTEGER,
    first_observation_time TEXT,
    last_observation_time TEXT,
    data_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id),
    UNIQUE (alert_decision_id, window_seconds),
    CHECK (data_status IN ('COMPLETE', 'NO_PRICE_DATA', 'INVALID_ALERT_PRICE')),
    CHECK (window_seconds IN (300, 900, 1800, 3600, 14400, 86400))
);

CREATE INDEX idx_outcome_windows_token_address ON outcome_windows(token_address);
CREATE INDEX idx_outcome_windows_alert_decision_id ON outcome_windows(alert_decision_id);
CREATE INDEX idx_outcome_windows_window_start_time ON outcome_windows(window_start_time);
```

`PRAGMA table_info(outcome_windows)`:

```
cid name                          type     notnull dflt pk
 0  id                             INTEGER  0       NULL 1
 1  alert_decision_id              INTEGER  1       NULL 0
 2  token_address                  TEXT     1       NULL 0
 3  window_seconds                 INTEGER  1       NULL 0
 4  window_start_time              TEXT     1       NULL 0
 5  window_end_time                TEXT     1       NULL 0
 6  alert_price                    REAL     0       NULL 0
 7  alert_mcap                     REAL     0       NULL 0
 8  max_price                      REAL     0       NULL 0
 9  max_mcap                       REAL     0       NULL 0
10  max_observation_time           TEXT     0       NULL 0
11  min_price                      REAL     0       NULL 0
12  min_mcap                       REAL     0       NULL 0
13  min_observation_time           TEXT     0       NULL 0
14  max_return_multiple            REAL     0       NULL 0
15  max_return_pct                 REAL     0       NULL 0
16  min_return_multiple            REAL     0       NULL 0
17  min_return_pct                 REAL     0       NULL 0
18  max_drawdown_from_peak_pct     REAL     0       NULL 0
19  time_to_max_return_seconds     REAL     0       NULL 0
20  hit_2x                         INTEGER  0       NULL 0
21  hit_3x                         INTEGER  0       NULL 0
22  hit_5x                         INTEGER  0       NULL 0
23  observations_count             INTEGER  0       NULL 0
24  first_observation_time         TEXT     0       NULL 0
25  last_observation_time          TEXT     0       NULL 0
26  data_status                    TEXT     1       NULL 0
27  created_at                     TEXT     1       NULL 0
```

`PRAGMA index_list(outcome_windows)`:

```
idx_outcome_windows_window_start_time           non-unique     on (window_start_time)
idx_outcome_windows_alert_decision_id           non-unique     on (alert_decision_id)
idx_outcome_windows_token_address               non-unique     on (token_address)
sqlite_autoindex_outcome_windows_1              UNIQUE origin=u on (alert_decision_id, window_seconds)
```

`PRAGMA foreign_key_list(outcome_windows)`:

```
id=0 seq=0 table=alert_decisions from=alert_decision_id to=id
  on_update=NO ACTION on_delete=NO ACTION match=NONE
```

DISTINCT `window_seconds` ("window_label" equivalent) values from
fixtures: **0 rows** in both fixtures — Stage 16B tests do not populate
`outcome_windows`. The full allowed set is enforced by the CHECK constraint:
`(300, 900, 1800, 3600, 14400, 86400)`. Stage 12 analysis maps these
seconds → labels via the constant
`WINDOWS = ((300,"5m"),(900,"15m"),(1800,"30m"),(3600,"1h"),(14400,"4h"),(86400,"24h"))`
([PHX2/analysis/decision_outcome_analysis.py:49-56](PHX2/analysis/decision_outcome_analysis.py:49)).

Whether `hit_2x`, `hit_3x`, `hit_5x` are stored: **yes**, stored columns
of type `INTEGER` (nullable; the OutcomeTrackingService writes `True`/`False`
→ adapted to 1/0 by `_to_db_value`). They are also queryable via
`SELECT max_return_multiple, …, hit_2x, hit_3x, hit_5x` — they are
**not** derived at read time. (`AnalysisService` re-derives them from
`max_return_multiple` only when joining shows nulls; see
`_derive_primary_outcome_flags` at
[PHX2/analysis/decision_outcome_analysis.py:330](PHX2/analysis/decision_outcome_analysis.py:330).)

Maturity / closed / finalized column: **no dedicated boolean column.** The
closest signal is `data_status TEXT NOT NULL` constrained by
`CHECK (data_status IN ('COMPLETE', 'NO_PRICE_DATA', 'INVALID_ALERT_PRICE'))`.
There is **no default** on `data_status`.

Since no maturity column exists, the convention is encoded in
`OutcomeTrackingService._process_window` (verbatim from
[PHX2/services/outcome_tracking_service.py:389-396](PHX2/services/outcome_tracking_service.py:389)):

```python
window_start = decision.evaluated_at
window_end = window_start + timedelta(seconds=window_seconds)
if as_of_time < window_end:
    return WindowProcessingResult(
        window_seconds=window_seconds,
        status=OutcomeWindowStatus.WINDOW_NOT_ELAPSED,
    )
```

`WINDOW_NOT_ELAPSED` is a service-only `OutcomeWindowStatus` that is
**never persisted** — the OutcomeWindowRepository.insert path raises
`ValueError` for any status not in `PERSISTABLE_OUTCOME_WINDOW_STATUSES`
([PHX2/db/repositories.py:1656-1662](PHX2/db/repositories.py:1656)). In
other words, the existence of a row in `outcome_windows` implies
`as_of_time >= decision.evaluated_at + window_seconds` at the time of
insert (per the service path; the schema itself does not enforce this).

Column names asked about vs. actual stored names:

| User-asked name | Stored name (actual) |
| --- | --- |
| `max_return` | `max_return_multiple` (and `max_return_pct`) |
| `max_drawdown_after` | `max_drawdown_from_peak_pct` |
| `time_to_max_return` | `time_to_max_return_seconds` |
| `last_observed_price` | **not present**; closest: `max_price`/`min_price` (extremes), `last_observation_time` (time only) |
| `last_observed_mcap` | **not present**; closest: `max_mcap`/`min_mcap`, `last_observation_time` |
| `hit_2x`/`hit_3x`/`hit_5x` | identical (stored) |

Total `outcome_windows` row count in both fixtures: 0. WOULD_ALERT join
counts grouped by `window_seconds` also: 0 (no rows to join).

### 3.3 Triple-join cardinality (naive)

Query executed (column names adjusted from the prompt's
`ow.window_label` → actual `ow.window_seconds`):

```sql
SELECT ow.window_seconds AS window_label, COUNT(*) AS n
FROM observe_only_policy_evaluations e
JOIN alert_decisions ad ON ad.id = e.alert_decision_id
JOIN outcome_windows ow ON ow.alert_decision_id = ad.id
WHERE ad.decision_type = 'would_alert' AND ad.would_alert = 1
GROUP BY ow.window_seconds
ORDER BY ow.window_seconds;
```

Result (both fixtures): **empty** (0 rows). `outcome_windows` is unpopulated
in Stage 16B test fixtures.

### 3.4 Triple-join cardinality (matured)

The maturity proxy used is `ow.data_status = 'COMPLETE'` (the only
"valid metrics persisted" status). The other two persistable statuses
(`NO_PRICE_DATA`, `INVALID_ALERT_PRICE`) are persisted but lack metrics.

Query executed:

```sql
SELECT ow.window_seconds AS window_label, COUNT(*) AS n
FROM observe_only_policy_evaluations e
JOIN alert_decisions ad ON ad.id = e.alert_decision_id
JOIN outcome_windows ow ON ow.alert_decision_id = ad.id
WHERE ad.decision_type = 'would_alert' AND ad.would_alert = 1
  AND ow.data_status = 'COMPLETE'
GROUP BY ow.window_seconds
ORDER BY ow.window_seconds;
```

Result (both fixtures): **empty** (0 rows; the matured filter is a strict
subset of the naive set, which was already empty).

Both results are an artifact of the test fixtures being Stage-16B-only;
the joined OutcomeWindow / AlertDecision overlap is not exercised by
Stage 16B tests.

## Section 4 — Repository and code conventions

### 4.1 Repository classes touching the four tables

All defined in `PHX2/db/repositories.py`. Each inherits
`RepositoryContract` (which holds `connection`, `_commit_if_top_level`,
`_insert`, `_fetchone`, `_fetchall`) except where noted.

#### `AlertDecisionRepository` ([PHX2/db/repositories.py:605](PHX2/db/repositories.py:605))

- Docstring: "Persistence for alert_decisions."
- Public methods (signatures):
  - `insert(self, decision: AlertDecision) -> int`
  - `get(self, decision_id: int) -> Optional[AlertDecision]`
  - `list_by_token(self, token_address: str, limit: int = 100) -> List[AlertDecision]`
  - `list_recent(self, limit: int = 100) -> List[AlertDecision]`
  - `list_would_alert(self, limit: int = 100, offset: int = 0, order: Literal["asc","desc"]="desc") -> List[AlertDecision]`
  - `list_pending_would_alert_with_ids(self, limit: int = 100, offset: int = 0) -> List[tuple]` — returns
    `(id, AlertDecision)`; filters `decision_type='would_alert' AND would_alert=1`; oldest-first.
  - `list_would_alerts_for_token(self, token_address: str, as_of_time: Optional[datetime] = None, limit: int = 1000) -> List[AlertDecision]`

#### `FilterEvaluationRepository` ([PHX2/db/repositories.py:778](PHX2/db/repositories.py:778))

- Docstring: "Persistence for filter_evaluations."
- Public methods:
  - `insert(self, result: FilterResult) -> int`
  - `list_by_token(self, token_address: str, limit: int = 100) -> List[FilterResult]`
  - `get_by_decision(self, alert_decision_id: int) -> List[FilterResult]` —
    SELECT * WHERE `alert_decision_id = ?` ORDER BY `id ASC`.
  - `exists_for_decision(self, alert_decision_id, filter_name, filter_version, threshold_version) -> bool`

#### `OutcomeWindowRepository` ([PHX2/db/repositories.py:1645](PHX2/db/repositories.py:1645))

- Docstring: "Persistence for outcome_windows. Stage 9 schema: insert-only.
  There is no update, delete, or recompute path in v0; once a row is
  written for a (alert_decision_id, window_seconds) pair it is terminal.
  Service-only statuses (PARTIAL, WINDOW_NOT_ELAPSED, ALREADY_RECORDED)
  are rejected before the DB call as defense in depth against the
  schema-level CHECK constraint."
- Public methods:
  - `insert(self, outcome: OutcomeWindow) -> int` — raises `ValueError`
    on a non-persistable `data_status`.
  - `get_by_decision_and_window(self, alert_decision_id: int, window_seconds: int) -> Optional[OutcomeWindow]`
  - `get_all_for_decision(self, alert_decision_id: int) -> List[OutcomeWindow]` —
    SELECT * WHERE `alert_decision_id = ?` ORDER BY `window_seconds ASC, id ASC`.

#### `ObserveOnlyEvaluationRepository` ([PHX2/stage16b/repository.py:29](PHX2/stage16b/repository.py:29))

- Docstring (line 1, condensed): "Append-only. … Owns exactly one table:
  observe_only_policy_evaluations." Does NOT inherit `RepositoryContract`.
- Public methods:
  - `insert_evaluation_rows(self, rows: Sequence[ObserveOnlyEvaluationRow]) -> int`
  - `list_alert_decision_ids_missing_policy_eval(self, policy_hash: str, limit: int) -> tuple[int, ...]`
  - `count_evaluations_for_policy(self, policy_hash: str) -> int`

### 4.2 Specific helpers / patterns

`get_*_by_decision_id` / `list_*_for_decision` helpers present:
- `FilterEvaluationRepository.get_by_decision(alert_decision_id)`
- `OutcomeWindowRepository.get_all_for_decision(alert_decision_id)`
- `OutcomeWindowRepository.get_by_decision_and_window(alert_decision_id, window_seconds)`
- `AlertDecisionRepository.get(decision_id)`
- (Stage 16B) `ObserveOnlyEvaluationRepository.list_alert_decision_ids_missing_policy_eval(policy_hash, limit)`

`get_latest_at_or_before` helpers (three present):
- `PriceObservationRepository.get_latest_at_or_before` at
  [PHX2/db/repositories.py:300](PHX2/db/repositories.py:300)
- `FieldFeatureRepository.get_latest_at_or_before` at
  [PHX2/db/repositories.py:1401](PHX2/db/repositories.py:1401)
- `ScoreFeatureRepository.get_latest_at_or_before` at
  [PHX2/db/repositories.py:1481](PHX2/db/repositories.py:1481)
- `ClockFeatureRepository.get_latest_at_or_before` at
  [PHX2/db/repositories.py:1628](PHX2/db/repositories.py:1628)

(None of these four tables — `alert_decisions`, `filter_evaluations`,
`outcome_windows`, `observe_only_policy_evaluations` — exposes a
`get_latest_at_or_before` helper.)

`PHX2Connection.transaction()` (verbatim from
[PHX2/db/connection.py:20-71](PHX2/db/connection.py:20)):

```python
class PHX2Connection:
    """Wrapper around sqlite3.Connection that owns explicit transaction state.

    Repositories on the same wrapper share one transaction, which lets services
    compose atomic cross-repository writes via `with conn.transaction(): ...`.
    """

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw
        self._in_transaction: bool = False

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._in_transaction:
            raise RuntimeError("nested transactions not supported")
        self._in_transaction = True
        try:
            yield
        except BaseException:
            self._raw.rollback()
            raise
        else:
            self._raw.commit()
        finally:
            self._in_transaction = False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._raw.execute(sql, params)

    def executescript(self, sql: str) -> sqlite3.Cursor:
        return self._raw.executescript(sql)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()
```

`_commit_if_top_level` pattern — two distinct implementations:

1. `RepositoryContract._commit_if_top_level` at
   [PHX2/db/repositories.py:113-115](PHX2/db/repositories.py:113):
   ```python
   def _commit_if_top_level(self) -> None:
       if not self.connection.in_transaction:
           self.connection.commit()
   ```
   Used by every Stage 4/9/10/11 repository (which subclasses
   `RepositoryContract`).
2. `ObserveOnlyEvaluationRepository._commit_if_top_level` at
   [PHX2/stage16b/repository.py:57-79](PHX2/stage16b/repository.py:57) (Stage
   16B) takes an explicit `was_in_transaction: bool` snapshot, because
   Stage 16B uses raw `sqlite3.Connection` (whose `in_transaction` is
   dirty-flag based and would flip True after the first execute):
   ```python
   def _commit_if_top_level(self, was_in_transaction: bool) -> None:
       if not was_in_transaction:
           self.connection.commit()
   ```

`DataStatus` enum definition (verbatim from
[PHX2/models/enums.py:6-15](PHX2/models/enums.py:6)):

```python
class DataStatus(str, Enum):
    """Data completeness status for PHX2 records."""

    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    NO_EVENTS = "no_events"
    DATA_LIMITED = "data_limited"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ERROR = "error"
```

Tables carrying a `data_status` column (per the migrations file):
`token_sequence_state`, `migration_events`, `price_observations`,
`ath_state`, `ath_events`, `alert_decisions`, `filter_evaluations`,
`fee_windows`, `field_features`, `score_features`, `clock_features`,
`outcome_windows`, `decision_score_features`.

Notes on `data_status` value vocabularies:
- Most tables carry the lower-case `DataStatus` vocabulary (`'ok'`,
  `'partial'`, `'missing'`, `'no_events'`, `'data_limited'`,
  `'source_unavailable'`, `'error'`).
- `outcome_windows.data_status` is **enum-isolated** with a CHECK
  constraint to only `'COMPLETE'`, `'NO_PRICE_DATA'`,
  `'INVALID_ALERT_PRICE'` (the `OutcomeWindowStatus` enum, not
  `DataStatus`).

Maturity helper for outcome windows: **no standalone helper.** The
maturity logic is inlined in `OutcomeTrackingService._process_window`
(see Section 3.2). The OutcomeTrackingService docstring at
[PHX2/services/outcome_tracking_service.py:11](PHX2/services/outcome_tracking_service.py:11)
states: "There is no internal scheduler or background loop in v0."

`hit_2x`/`3x`/`5x` derivation helper: `_derive_primary_outcome_flags` at
[PHX2/analysis/decision_outcome_analysis.py:330](PHX2/analysis/decision_outcome_analysis.py:330)
(Stage 12 analysis layer). This is a pandas-DataFrame transform, not a
repository helper; it re-derives flags from `max_return_multiple` only as
a fallback when the stored `hit_*` columns are missing/NULL on the joined
long DataFrame.

### 4.3 Test fixture conventions

- Top-level test directory: `PHX2/tests/` (sibling layout — file-per-module
  for older code; `PHX2/tests/stageNN/` per-stage subdirectories for stages
  13/14/15/16a/16b).
- Shared fixture builders: `PHX2/tests/fixtures/analysis_fixture_builder.py`.
  All four tables of interest have a canonical INSERT helper here:
  - `insert_alert_decision(connection, *, decision_id, token_address,
    evaluated_at, decision_type='would_alert', tier_index=1, tier_name='T1',
    primary_reason='would_alert', would_alert=True, blocked=False,
    skipped=False, current_price=1.0, current_mcap=100_000.0,
    pump_multiple=2.5, drawdown_from_ath=-0.30, ath_status='confirmed',
    ath_confidence='high', policy_version='phx2-fixture',
    data_status='ok', extra=None) -> None`
  - `insert_filter_evaluation(connection, *, filter_evaluation_id,
    alert_decision_id, token_address, as_of_time, filter_name='fee_gate',
    filter_version='v1', threshold_version='v1', label='NORMAL',
    score=0.5, would_block=False, policy_action='allow', reason=None,
    data_status='ok') -> None`
  - `insert_decision_score_features(connection, *, snapshot_id,
    alert_decision_id, token_address, decision_time, as_of_time=None,
    feature_version='v1', schema_version='1', token_symbol='TOK',
    tier_index=1, tier_name='T1', data_status='ok', ath_time=None,
    migration_time=None, source_snapshot=None, primitive_overrides=None) -> None`
  - `insert_outcome_window(connection, *, outcome_id=None,
    alert_decision_id, token_address, window_seconds, window_start_time,
    window_end_time, alert_price=1.0, alert_mcap=100_000.0,
    max_price=2.0, max_mcap=200_000.0, max_observation_time=None,
    min_price=0.8, min_mcap=80_000.0, min_observation_time=None,
    max_return_multiple=2.0, max_return_pct=100.0, min_return_multiple=0.8,
    min_return_pct=-20.0, max_drawdown_from_peak_pct=-10.0,
    time_to_max_return_seconds=600.0, hit_2x=True, hit_3x=False,
    hit_5x=False, observations_count=30, first_observation_time=None,
    last_observation_time=None, data_status='COMPLETE') -> None`
- Stage 16B-specific wrappers ([PHX2/tests/stage16b/fixtures/builders.py](PHX2/tests/stage16b/fixtures/builders.py)):
  - `make_stage16b_db_path(base: Path) -> Path`
  - `stage16b_phx2_connection(path: Path) -> Iterator[sqlite3.Connection]`
    (context manager applying `apply_stage16b_schema` on a raw `sqlite3.Connection`)
  - `make_loaded_policy(*rules: LoadedRule, policy_hash=DEFAULT_POLICY_HASH) -> LoadedObserveOnlyPolicy`
  - `class StubPolicyLoader`
  - `insert_would_alert_decision(connection, *, decision_id, tier_name='T1', token_address='tok') -> None`
    (delegates to the shared `insert_alert_decision`)
  - `insert_canonical_filter_evaluation(connection, *, fe_id, alert_decision_id,
    label='NORMAL', filter_name='fee_gate',
    filter_version='fee_gate_v1_no_bribes',
    threshold_version='thresholds_v0_observe_only', token_address='tok') -> None`
    (delegates to the shared `insert_filter_evaluation`)
  - `make_observer(connection, *, policy_loader, evaluator_factory=None,
    clock=None, repository=None, assembler=None) -> ObserveOnlyObserverService`
- Stage 14/15 each have their own fixture subdirectories
  (`PHX2/tests/fixtures/stage13/`, `…/stage14/`,
  `PHX2/tests/stage15/fixtures/`).

### 4.4 Analysis / report module precedent

Directories present in `PHX2/`:
- `PHX2/scripts/` (CLI entry-point scripts; thin `sys.path` setup +
  delegation to a `*.cli.main` function in another package).
- `PHX2/analysis/` (Stage 12 decision-outcome analysis package).
- No `PHX2/reports/` or `PHX2/tools/` directories exist.

Prior pure-analysis module precedent: **yes — `PHX2/analysis/` (Stage 12).**
Shape:

- `PHX2/analysis/decision_outcome_analysis.py` (orchestrator). Docstring
  (verbatim, [PHX2/analysis/decision_outcome_analysis.py:1-20](PHX2/analysis/decision_outcome_analysis.py:1)):
  > "Stage 12 pipeline orchestrator. Pure function `run(readers, params)
  > -> RunResult`: Reads alert_decisions, filter_evaluations,
  > decision_score_features, outcome_windows via `SubstrateReaders` (L4
  > enforced by the dataclass signature). Left-joins them at
  > alert_decision_id to produce the long DataFrame. Derives the primary
  > 24h outcome flags… Returns a `RunResult` containing all DataFrames +
  > manifest + README context. NO file I/O happens inside this function —
  > the caller (CLI) writes files via `writers`."
- `PHX2/analysis/cli.py` (CLI wrapper using argparse). Output convention:
  per-run immutable directory of CSVs + manifest.json + README.md under
  `PHX2/analysis/output/decision_outcome_analysis/<run_id>/` (default
  output root; configurable via `--output-dir`).
- `PHX2/analysis/readers.py`, `writers.py`, `manifest.py`, `metrics.py`,
  `buckets.py` — supporting modules.
- `PHX2/analysis/output/` is `.gitignore`d except for `.gitkeep`.

CLI entry-point convention (`argparse`, NOT click/typer):

Representative example from the most recent CLI-creating stage's CLI
parser ([PHX2/stage16b/cli.py:41-79](PHX2/stage16b/cli.py:41)):

```python
def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_stage16b_observer_once",
        description=(
            "Stage 16B: one-shot sidecar observer. …"
        ),
    )
    parser.add_argument(
        "--runtime-policy-path",
        required=True,
        type=Path,
        help="Path to a Stage 16A observe_only_runtime_policy.json artifact.",
    )
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="Path to the PHX2 SQLite database.",
    )
    parser.add_argument(
        "--limit",
        required=True,
        type=int,
        help="Max number of un-evaluated WOULD_ALERT decisions to process …",
    )
    return parser
```

Every Stage 12+ CLI (Stage 12 analysis, Stage 13, 14, 15, 16A, 16B) uses
`argparse` and exposes `make_parser() -> ArgumentParser` plus
`main(argv: list[str] | None = None) -> int`. None use `click` or
`typer`.

### 4.5 Migration numbering / dual-migration pattern

Migrations directory: **there is no separate `migrations/` directory.** All
PHX2 schema migrations live in the single file `PHX2/db/migrations.py`
(1548 lines). Migration filenames as a concept do not exist; instead,
migration **versions** are string constants at the top of the file (lines
22-31):

```
STAGE_4A_VERSION = "stage_4a_core_telemetry"
STAGE_4B_VERSION = "stage_4b_field_score_clock"
STAGE_5A_VERSION = "stage_5a_raw_pumpswap_events"
STAGE_5C1_VERSION = "stage_5c1_price_curve_points"
STAGE_9A_VERSION = "stage_9a_alert_decision_current_price"
STAGE_9B_VERSION = "stage_9b_outcome_windows_recreate"
STAGE_10A_VERSION = "stage_10a_field_features_event_count_5m"
STAGE_10B_VERSION = "stage_10b_filter_evaluations_extension"
STAGE_11A_VERSION = "stage_11a_decision_score_features"
STAGE_16B_VERSION = "stage_16b_observe_only_policy_evaluations"
```

The 10 versions above are the complete migration ledger (also reflected
verbatim in the `schema_migrations` table contents of any fresh-migrated
DB). The "head migration" is the last `apply_stage*_schema` chain caller
— `apply_stage16b_schema(connection)` at
[PHX2/db/migrations.py:1521-1532](PHX2/db/migrations.py:1521):

```python
def apply_stage16b_schema(connection: sqlite3.Connection) -> None:
    """Apply Stage 4 through Stage 16B schema in order.

    Stage 16B: idempotently create ``observe_only_policy_evaluations``,
    the append-only telemetry sink written by the Stage 16B sidecar
    observer. The observer reuses Stage 16A's loader and evaluator and
    never participates in alert eligibility or dispatch.
    """

    apply_stage11_schema(connection)
    apply_stage16b_observe_only_policy_evaluations(connection)
    connection.commit()
```

"Dual-migration pattern": within `PHX2/db/migrations.py`, several stages
pair an **ALTER TABLE-style extension** with a **table-recreate** step.
Concrete examples:

- **Stage 9:** `apply_stage9_alert_decision_extension` (Stage 9A, ALTERs
  `alert_decisions` to add `current_price`/`current_mcap`) paired with
  `apply_stage9_outcome_windows_recreate` (Stage 9B, drops the Stage 4B
  scaffold table and recreates with the Stage 9 schema). See lines
  751-851. Pair functions: `apply_stage9_alert_decision_extension` (line
  751) + `apply_stage9_outcome_windows_recreate` (line 779). Differing
  content shape: the 9A path uses `ALTER TABLE alert_decisions ADD
  COLUMN`; the 9B path executes the multi-line
  `STAGE_9_OUTCOME_WINDOWS_SQL` script and refuses on non-empty Stage 4B
  scaffold data.
- **Stage 10:** `apply_stage10_field_features_extension` (Stage 10A, ALTER
  `field_features`) paired with
  `apply_stage10_filter_evaluations_recreate` (Stage 10B, recreate
  `filter_evaluations`). See lines 896-986. Same A/B pattern.
- **Stage 11:** `apply_stage11_decision_score_features` is a single-step
  create-only migration ([PHX2/db/migrations.py:1122-1149](PHX2/db/migrations.py:1122)).
- **Stage 16B:** `apply_stage16b_observe_only_policy_evaluations` is a
  hardened first-run-or-validate pattern (lines 1468-1518). On first run
  it creates the table + three indexes from
  `STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL`; on re-run it validates
  table shape (columns, UNIQUE, FK) and indexes against
  `EXPECTED_STAGE_16B_*` tuples before idempotently repairing missing
  indexes via `CREATE INDEX IF NOT EXISTS`.

## Section 5 — Negative inventory (modules Stage 17 must not touch)

Each module/file confirmed present (`existing`) or absent (`absent`) at
HEAD `c6d5528…`; "untouched by Stage 17 work" is trivially confirmed —
no Stage 17 code exists.

### 5.1 AlertDispatcher / Discord / Telegram / webhook modules

- `PHX2/services/alert_dispatcher.py` — existing.
- `PHX2/dispatch/dispatcher.py` — existing.
- `PHX2/dispatch/routing.py` — existing.
- `PHX2/dispatch/preview_pipeline.py` — existing.
- `PHX2/dispatch/sinks/base.py` — existing.
- `PHX2/dispatch/sinks/console.py` — existing.
- `PHX2/dispatch/sinks/discord.py` — existing.
- `PHX2/dispatch/sinks/file_preview.py` — existing.
- `PHX2/dispatch/transport/http_client.py` — existing.
- `PHX2/integrations/discord_client.py` — existing.
- `PHX2/integrations/telegram_client.py` — existing.

### 5.2 AlertEligibilityEngine

- `PHX2/services/alert_eligibility_engine.py` — existing.

### 5.3 FilterEvaluationEngine

- `PHX2/services/filter_evaluation_engine.py` — existing.
- `PHX2/filters/base.py`, `PHX2/filters/fee_gate.py` — existing.

### 5.4 OutcomeTrackingService

- `PHX2/services/outcome_tracking_service.py` — existing.

### 5.5 Schedulers / daemons / periodic / always-on entry points

`grep -rnE "schedule|daemon|while True|asyncio\.run_forever|cron" PHX2/`
hits (all benign):

- `PHX2/services/outcome_tracking_service.py:11` — docstring text:
  "There is no internal scheduler or background loop in v0."
- `PHX2/stage13/hashing.py:33`, `PHX2/stage14/hashing.py:36`,
  `PHX2/stage15/hashing.py:26`, `PHX2/stage16a/hashing.py:85` — all are
  chunked-read `while True: chunk = f.read(...); if not chunk: break` in
  the canonical `sha256_file` helper.
- `PHX2/stage16b/cli.py:54` — CLI prog-description string fragment "No
  daemon. No enforcement."
- `PHX2/tests/fixtures/stage14/stage14_fixture_writer.py:359` — fixture
  generation loop.

No real scheduler, daemon, periodic, asyncio loop, or cron entry exists
in PHX2 (in either Stage 16A, 16B, or any other production module).

### 5.6 Policy promotion / shadow / live-policy modules

`grep -rnE "policy_promotion|promote_rule|shadow_policy|live_policy" PHX2/`
hits — all reference **Stage 14 shadow-policy ARTIFACT names**
(`shadow_policy_rules.json`, `shadow_policy_replay_results.csv`,
`stage14_shadow_policy_review.md`) and `safe_for_live_policy_consumption`
manifest flags. No module named `policy_promotion`, `promote_rule`,
`shadow_policy`, or `live_policy` exists; no class or function with those
names exists. Stage 14 produces shadow-policy artifacts that Stage 15
operator-approves and Stage 16A consumes; **there is no automated
promotion path** anywhere in the codebase.

Specific hit files (paths only):

```
PHX2/stage15/loaders.py
PHX2/stage15/markdown.py
PHX2/stage15/reconciler.py
PHX2/stage14/loader.py
PHX2/stage14/writer.py
PHX2/stage14/types.py
PHX2/stage14/pipeline.py
PHX2/stage14/__init__.py
PHX2/stage13/pipeline.py
PHX2/stage13/writer.py
PHX2/stage13/__init__.py
PHX2/tests/stage15/test_isolation.py
PHX2/tests/stage15/test_hash_lineage.py
PHX2/tests/stage15/test_markdown.py
PHX2/tests/stage15/test_writer.py
PHX2/tests/stage15/test_loaders_load_time_errors.py
PHX2/tests/stage15/fixtures/builders.py
PHX2/tests/test_stage14_loader.py
PHX2/tests/test_stage14_pipeline.py
PHX2/tests/test_stage14_writer.py
PHX2/tests/fixtures/stage14/stage14_fixture_writer.py
PHX2/tests/test_stage13_writer.py
PHX2/tests/test_stage13_pipeline.py
PHX2/docs/stage_summaries/stage14.md
```

### 5.7 Ingest adapters

- `PHX2/services/pumpswap_event_ingestion_service.py` — existing.
- `PHX2/services/migration_service.py` — existing.
- `PHX2/services/price_service.py` — existing.
- `PHX2/services/curve_capture_service.py` — existing.
- `PHX2/services/ath_service.py` — existing.
- `PHX2/services/clock_feature_service.py` — existing.
- `PHX2/services/field_feature_service.py` — existing.
- `PHX2/services/score_feature_service.py` — existing.
- `PHX2/services/feature_window_service.py` — existing.
- `PHX2/services/telemetry_service.py` — existing.
- `PHX2/services/decision_feature_snapshot_service.py` — existing.

### 5.8 Pre-existing Stage 17 work — none

- `grep -rn "stage_17\|stage17" PHX2/` → **no matches.**
- `grep -rn "policy_effectiveness\|observe_only_outcome\|policy_evaluation_outcome" PHX2/` → **no matches.**
- `find PHX2 -iname "*stage_17*" -o -iname "*policy_effectiveness*"` → **no matches.**

All three negative queries returned empty as expected.

## Section 6 — Risk notes (factual, no recommendations)

Observations relevant to Stage 17 design surfaced during this inventory:

1. **Column-name divergence between the Stage 17 prompt and actual
   `outcome_windows` schema.** The prompt asks about `max_return`,
   `max_drawdown_after`, `time_to_max_return`, `last_observed_price`,
   `last_observed_mcap`, `window_label`. The actual columns are
   `max_return_multiple` (+ `max_return_pct`), `max_drawdown_from_peak_pct`,
   `time_to_max_return_seconds`, **no** `last_observed_price` /
   `last_observed_mcap` (the per-window last-observation surface stores
   only `last_observation_time` + `min_observation_time` +
   `max_observation_time` plus the price/mcap extremes), and the window
   identifier is `window_seconds` (INTEGER) — there is no
   `window_label` text column. Stage 12 maps seconds → label text via the
   `WINDOWS` constant in
   `PHX2/analysis/decision_outcome_analysis.py:49-56`.
   File: [PHX2/db/migrations.py:709-748](PHX2/db/migrations.py:709).

2. **No persistent PHX2 database exists on disk.** `data/` is empty;
   `data/*.db` is `.gitignore`d; all DB queries in this report were
   against pytest fixture DBs copied to `%TEMP%` (read-only). Stage 17
   has no "current production" baseline to design against from this repo
   alone; any volume / cardinality assumptions must come from elsewhere.
   File evidence: `ls data/` shows only `.` and `..`; `.gitignore`
   line `data/*.db`.

3. **`tier_name` is nullable on `alert_decisions` and is NULL in
   practice.** The Stage 16B test fixture
   `test_observer_two_fresh_runs_p0/run_b` contains a WOULD_ALERT
   `alert_decisions` row with `tier_name IS NULL`, and Stage 16B's
   evaluator emits 2 `UNEVALUABLE` telemetry rows for it (one per
   policy rule, both with `unevaluable_reason='tier_name_missing_on_decision'`).
   Files: [PHX2/db/migrations.py:148](PHX2/db/migrations.py:148) (DDL
   declares `tier_name TEXT` nullable);
   [PHX2/stage16a/observe_only_policy_evaluator.py:29](PHX2/stage16a/observe_only_policy_evaluator.py:29)
   (`_TIER_MISSING_REASON = "tier_name_missing_on_decision"`).

4. **`evaluation_status` literals are not enumerated in any Python
   `Enum` class.** They are enforced only by the table CHECK constraint
   (`'MATCHED'|'NOT_MATCHED'|'UNEVALUABLE'`) and by Stage 16B's
   `row_builder.build_rows_for_decision` switch (string literals). No
   `EvaluationStatus` enum exists anywhere under `PHX2/models/`.
   Files: [PHX2/db/migrations.py:1216](PHX2/db/migrations.py:1216);
   [PHX2/stage16b/row_builder.py:105,120,134](PHX2/stage16b/row_builder.py:105).

5. **FK declarations on the three Stage-relevant tables are inert at
   runtime.** All three FKs (`filter_evaluations(alert_decision_id) →
   alert_decisions(id)`, `outcome_windows(alert_decision_id) →
   alert_decisions(id)`, `observe_only_policy_evaluations(alert_decision_id)
   → alert_decisions(id)`) are declared in the DDL and visible in
   `PRAGMA foreign_key_list`, but `PRAGMA foreign_keys = ON` is **never
   issued** anywhere in `PHX2/db/`. The Stage 16B migrations.py
   docstring at [PHX2/db/migrations.py:1196-1200](PHX2/db/migrations.py:1196)
   states: "The FK declaration to `alert_decisions(id)` is inert at
   runtime (`PRAGMA foreign_keys` is OFF globally; same posture as
   `filter_evaluations` and `decision_score_features`) but documents the
   relationship and would activate cleanly if FK enforcement is later
   enabled."

6. **Stage 16B deliberately bypasses `PHX2Connection` and
   `RepositoryContract`.** Stage 16B uses raw `sqlite3.Connection`
   everywhere (assembler, repository, CLI) to keep its sidecar import
   boundary clean of `PHX2.config.settings` and `PHX2.models.enums`.
   This means Stage 16B has its own `_commit_if_top_level` with a
   pre-snapshot `was_in_transaction` arg (different signature from the
   `RepositoryContract` version). If Stage 17 lives inside or alongside
   Stage 16B, it inherits this constraint.
   Files:
   [PHX2/stage16b/repository.py:34-50](PHX2/stage16b/repository.py:34)
   (boundary docstring);
   [PHX2/stage16b/cli.py:178-184](PHX2/stage16b/cli.py:178)
   (CLI uses `sqlite3.connect` directly).

7. **`OutcomeTrackingService` re-derives `hit_2x/3x/5x` from
   `max_return_multiple` at write time, and the stored
   `outcome_windows.hit_*` columns are populated from those booleans.**
   The Stage 12 analysis layer additionally has a
   `_derive_primary_outcome_flags` fallback that re-derives from
   `max_return_multiple` on join. Two write/derive paths exist; both
   agree on the predicate `multiple >= 2.0/3.0/5.0`.
   Files:
   [PHX2/services/outcome_tracking_service.py:223-225](PHX2/services/outcome_tracking_service.py:223);
   [PHX2/analysis/decision_outcome_analysis.py:330](PHX2/analysis/decision_outcome_analysis.py:330).

8. **There is no separate `migrations/` directory.** All DDL, migration
   helpers, and migration version constants live in a single file
   (`PHX2/db/migrations.py`, 1548 lines). Stage 17 schema additions, if
   any, would extend this file rather than land as a new file. The
   "dual-migration pattern" (Section 4.5) is a per-stage **pair of
   Python functions** within the same file (e.g. `apply_stage9_*` /
   `apply_stage10_*` each splitting an extension step from a recreate
   step), not a pair of SQL files.

9. **`max_return_multiple` on `outcome_windows` is REAL nullable.** It is
   the canonical "outcome metric" but is allowed to be NULL on persisted
   `NO_PRICE_DATA` and `INVALID_ALERT_PRICE` rows. Any Stage 17 join
   that filters / aggregates on `max_return_multiple` must handle NULL
   explicitly (Stage 12 analysis pre-coerces to a fallback path via
   `_derive_primary_outcome_flags`).
   File: [PHX2/db/migrations.py:725](PHX2/db/migrations.py:725).

10. **Stage 16B's WOULD_ALERT predicate is `decision_type='would_alert'
    AND would_alert=1` (both filters layered).** Mirrors
    `AlertDecisionRepository.list_pending_would_alert_with_ids`
    ([PHX2/db/repositories.py:709-737](PHX2/db/repositories.py:709)).
    Stage 16B's own implementation re-declares the constants
    `WOULD_ALERT_DECISION_TYPE='would_alert'` and `WOULD_ALERT_FLAG=1`
    at [PHX2/stage16b/repository.py:18-19](PHX2/stage16b/repository.py:18).
    Two-source rule for "what counts as WOULD_ALERT" — both must hold.

11. **Stage 16B's `unevaluable_reason` is open-ended TEXT, not
    enumerated.** Today only one literal is emitted
    (`'tier_name_missing_on_decision'`), but the CHECK constraint allows
    any non-NULL TEXT.
    Files: [PHX2/db/migrations.py:1230](PHX2/db/migrations.py:1230) (CHECK);
    [PHX2/stage16a/observe_only_policy_evaluator.py:29](PHX2/stage16a/observe_only_policy_evaluator.py:29)
    (sole reason literal).

12. **`observe_only_policy_evaluations.tier_name_snapshot` is nullable,
    snapshotted at row-build time, and can disagree with
    `alert_decisions.tier_name` at read time.** The Stage 16B row builder
    receives `tier_name` from the `DecisionContext` (a point-in-time
    snapshot of `alert_decisions.tier_name` at assemble-time) and stores
    it on the row. If `alert_decisions.tier_name` were later updated
    (today no service does this; `OutcomeTrackingService` is the only
    service that touches `alert_decisions`, and only via reads), the
    Stage 16B snapshot would diverge.
    File: [PHX2/stage16b/row_builder.py:101-140](PHX2/stage16b/row_builder.py:101).

## Final Section — Step 0 Exit Check

Re-run `git status --short` (after inventory completion, before this
file's final write):
```
?? PHX2/docs/
?? ROADMAP.md
```
Matches the opening snapshot. The two untracked entries (`PHX2/docs/` and
`ROADMAP.md`) were already untracked at the start of this run and were
not touched by this inventory. The inventory file itself
(`PHX2/.stage_17_inputs/stage_16_inventory.md`) is a new file in a new
directory; it will appear in the post-write `git status` but is the
single permitted mutation per the task spec.

No source files modified; no migrations run; no commits made; no DB
files in the repo touched. The only filesystem writes were:
1. `PHX2/.stage_17_inputs/` (directory created).
2. `PHX2/.stage_17_inputs/stage_16_inventory.md` (this file).
3. `%TEMP%\phx2_inv_ro.db`, `%TEMP%\phx2_inv_ro2.db`,
   `%TEMP%\phx2_inv_query.py`, `%TEMP%\phx2_inv_query2.py` (all under
   the user's Windows TEMP — outside the repo).

DB row counts (re-checked on the two read-only fixture copies; unchanged
from the opening reads since both queries used `?mode=ro` and TEMP-side
copies):

- `test_observer_two_fresh_runs_p0/run_b`: `observe_only_policy_evaluations=6`,
  `alert_decisions=3`, `outcome_windows=0`, `filter_evaluations` (not
  counted again — unchanged contract).
- `test_cli_multi_decision_run_wr0`: `observe_only_policy_evaluations=3`,
  `alert_decisions=3`, `outcome_windows=0`.

STAGE 16 INVENTORY COMPLETE — NO MUTATIONS.
