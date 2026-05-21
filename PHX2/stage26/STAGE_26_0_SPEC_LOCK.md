# PHX2 Stage 26.0 — Stage 26 spec-lock + Stage 26.1 implementation charter

Stage 26.0 is a **planning / spec-lock only** sub-stage. No Stage 26
production code (readers, models, calibration logic, denominators,
cohorts, thresholds, policy candidates, runners, writers, CLIs)
ships in this commit. The single output of Stage 26.0 is this
spec-lock document plus the Stage 26 package scaffold
(`PHX2/stage26/__init__.py`).

This document is the authoritative reference for every Stage 26.x
sub-stage from 26.1 onward.

---

## 1. Stage 26 mission

Stage 26 consumes Stage 25 measurement artifacts and produces
**observe-only calibration surfaces and candidate (proposed) policy
evidence**, without mutating measurement truth.

Stage 26 is a calibration / candidate-policy layer. Stage 26 is
NOT a new measurement layer; Stage 25's recorded measurement
status tokens (`MEASURED` / `PARTIAL` / `SOURCE_CONFLICT` /
`AMBIGUOUS` / `MISSING` / `UNSUPPORTED` / `REJECTED` /
`NOT_APPLICABLE`) are the input contract, not a re-derivable side
artifact. Stage 26 reads them, never recomputes them, never
upgrades them.

Stage 26 is observe-only. It does NOT enforce, dispatch, route,
gate, or block. Approved candidate policies become live only in a
later, explicitly-authorized stage (Stage 29 per the corrected
roadmap, see §11).

---

## 2. Stage 26.0 mission

Lock the Stage 26 architecture and the Stage 26.1 implementation
charter **before** any Stage 26.1 code is written. Specifically:

- lock the Stage 26 sub-stage order (§5),
- lock the Stage 26.1 charter — what 26.1 does and does not do (§6),
- lock the Stage 25 artifacts Stage 26.1 requires (§7),
- lock the Stage 25 schema / vocabulary import surface (§8),
- lock the Stage 26.1 closed-set / deferred-status policy (§9),
- lock the measurement-truth preservation rules (§10),
- lock the forbidden boundaries (§4 and §6),
- lock the corrected Stage 27+ roadmap (§11),
- record the Stage 25 tag-readiness state (§3) and the explicit
  Stage 26.1 implementation block (§12).

---

## 3. Stage 25 tag-readiness status (verified at Stage 26.0 plan time)

- Current `HEAD` SHA: `ff241c4cab13a720904be17329da9680f25de321`
- Current `HEAD` subject: `docs: update PHX2 README for stage 25 closure`
- `stage-25-closed` annotated tag: **NOT PRESENT** at Stage 26.0
  plan time.
- `git status` shows only the pre-existing untracked paths:
  - `PHX2/.stage_17_inputs/`
  - `PHX2/docs/stage_summaries/`
  - `ROADMAP.md`
- Stage 25 closure docs are committed and present:
  - `PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md`
  - `PHX2/stage25/STAGE_26_HANDOFF.md`

Stage 26.0 does NOT create the `stage-25-closed` tag. Per the
Stage 25.7 closure-audit document (§11), the tag is reserved for
the operator and is created only after explicit operator
authorization. Until the operator creates the tag in this chat,
Stage 26.1 implementation is BLOCKED (see §12).

---

## 4. Stage 26 high-level invariants

These invariants apply to every Stage 26 sub-stage and are not
relaxable by any individual sub-stage:

1. **Read-only against Stage 25 artifacts.** No Stage 26 module
   writes to, renames, deletes, or otherwise mutates a Stage 25
   artifact file.
2. **Measurement-truth preservation.** Stage 26 never rewrites,
   collapses, or "fixes" a Stage 25 status token. See §10.
3. **Manifest verification before consumption.** Every Stage 26
   reader verifies the Stage 25 manifest's per-file `sha256` +
   `byte_count` against the on-disk bytes, honoring the
   `SELF_REFERENTIAL_MANIFEST_SHA256` sentinel for the manifest
   self-entry.
4. **Pinned upstream provenance.** Every Stage 26 artifact records
   the Stage 25 manifest pin as `(basename, sha256)` only —
   mirroring the Stage 24 → Stage 25 pin convention.
5. **Observe-only.** Stage 26 emits candidate evidence for operator
   review. It never dispatches, routes, blocks, gates, or wires a
   live decision path.
6. **Deterministic.** Identical inputs + identical injected
   `created_at_utc` produce byte-identical Stage 26 artifacts.
7. **Redaction discipline.** Stage 26 outputs satisfy the same
   redaction / forbidden-substring discipline Stage 25 imposes on
   its own outputs (the Stage 25 forbidden-substring vocabularies
   are reused).
8. **No live surfaces.** No network, RPC, DB, scheduler, secrets
   manager, environment read, CLI entrypoint, dispatcher,
   Discord / Telegram / public / subscriber / X / social code.
9. **No Stage 24 execution-fee reopening.** Stage 26 carries the
   Stage 25 manifest pin forward only; it does NOT reopen Axiom /
   global-fee / execution-fee decoding. (See §11 for the Stage 29
   enforcement-wiring deferral.)

---

## 5. Locked Stage 26 sub-stage order

Stage 26 ships in the following locked order. Each sub-stage is its
own commit, planning-turn-first per the PHX2 sub-stage workflow.

| Sub-stage | Scope |
| --- | --- |
| **26.0** | Spec-lock + Stage 26.1 implementation charter (this document). No Stage 26 production code. |
| **26.1** | Calibration input contracts + Stage 25 artifact readers (read-only, in-memory, deterministic). |
| **26.2** | Denominator / outcome-eligibility semantics — what counts as a "calibration-eligible" row, what does not, and why. |
| **26.3** | Calibration cohort builder — assembles cohorts using only the 26.2 eligibility decisions. |
| **26.4** | Threshold candidate generator — produces candidate threshold proposals from cohorts. |
| **26.5** | Observe-only policy candidate artifact builder — emits candidate-policy evidence for operator review (no enforcement, no dispatch). |
| **26.6** | Operator review packet / approval handoff. |
| **26.7** | Closure audit + Stage 27 handoff. |

**Rationale for ordering 26.2 before 26.3.** Denominator /
outcome-eligibility semantics must be locked **before** the cohort
builder so the cohort builder does not silently decide what counts.
A cohort builder that bakes in eligibility rules implicitly is a
denominator-honesty hazard.

---

## 6. Stage 26.1 charter (locked)

### 6.1 What 26.1 SHALL do

- read the Stage 25 manifest from a caller-supplied path,
- validate the manifest's stage / schema / observe-only-mode /
  redaction-confirmed / runner-name / runner-version / writer-name /
  writer-version tokens,
- validate every manifest file entry's `sha256` and `byte_count`
  against the on-disk bytes (honoring the
  `SELF_REFERENTIAL_MANIFEST_SHA256` sentinel for the manifest
  self-entry),
- read each Stage 25 artifact JSONL listed in the manifest using
  pure, side-effect-free row projectors,
- validate the `row_count` recorded in the manifest against the
  number of non-blank lines projected from the file (empty-but-
  present artifacts are valid when the manifest declares
  `row_count = 0`),
- preserve Stage 25's measurement status tokens **verbatim** on each
  projected record,
- return typed, immutable Stage 26 input records (Python
  `NamedTuple` is preferred to mirror the Stage 25 record style),
- pin the consumed Stage 25 manifest by `(basename, sha256)` only
  in the in-memory Stage 26 input bundle,
- raise typed Stage 26 errors (`Stage26ReaderError`,
  `Stage26ManifestError`, `Stage26SchemaError`, etc.) on every
  validation failure,
- remain deterministic, side-effect-free, and read-only.

### 6.2 What 26.1 SHALL NOT do

- **must not** join rows by mint (token / address) — joins are 26.3,
- **must not** build cohorts — cohorts are 26.3,
- **must not** assign `denominator_status` — denominator semantics
  are 26.2,
- **must not** assign a calibration-row status to any row —
  per-row eligibility classification is 26.2,
- **must not** generate thresholds — 26.4,
- **must not** generate policy candidates — 26.5,
- **must not** write artifacts to disk — no Stage 26 writer ships
  before 26.5 (and 26.5 only writes observe-only candidate
  artifacts),
- **must not** define a CLI entrypoint,
- **must not** read `os.environ` / `os.getenv`,
- **must not** import any network / RPC / messaging / DB /
  scheduler / secrets-management library,
- **must not** dispatch, send, route, notify, or otherwise produce
  a side effect outside of returning in-memory records,
- **must not** enforce any decision.

### 6.3 26.1 boundary forbiddances (to be enforced by 26.1 boundary tests)

26.1 boundary tests must forbid imports from:

- `PHX2.stage21`
- `PHX2.stage22`
- `PHX2.stage23`
- `PHX2.stage24`
- broad imports from `PHX2.stage25` outside the schema whitelist
  declared in §8

26.1 boundary tests must forbid:

- network libraries (requests / httpx / aiohttp / websockets /
  socket / urllib clients / etc.),
- DB libraries (sqlalchemy / asyncpg / psycopg / sqlite / etc.),
- dispatch / send / route / notify behavior (Discord / Telegram /
  webhooks / email / push),
- CLI entrypoints,
- `os.environ` / `os.getenv`,
- output writers (any open-for-write outside the no-op reader
  scope),
- enforcement / gating / blocking,
- X / social ingestion,
- Axiom / global-fee decoder logic,
- Stage 24 execution-fee reopening.

---

## 7. Required Stage 25 artifacts for Stage 26.1

Stage 26.1 requires the Stage 25.6 deterministic-writer outputs:

JSONL artifacts:

- `stage25_migration_observations.jsonl`
- `stage25_migration_measurements.jsonl`
- `stage25_price_window_observations.jsonl`
- `stage25_ath_candidates.jsonl`
- `stage25_source_reconciliations.jsonl`
- `stage25_ath_measurements.jsonl`
- `stage25_measurement_rejections.jsonl`

JSON artifacts:

- `stage25_summary.json`
- `stage25_manifest.json`

**Authoritativeness rule.** The Stage 25 manifest is the
authoritative declaration of which artifacts a Stage 25 run
produced. If the manifest declares an artifact basename, Stage 26.1
requires that file to be present on disk, validates its `sha256` /
`byte_count` against the manifest, and reads it. Empty-but-present
JSONL artifacts are valid Stage 26.1 inputs when the manifest's
`row_count` for that artifact is `0`.

**Migration-observations consumption note.** The Stage 26 handoff
document (`PHX2/stage25/STAGE_26_HANDOFF.md` §2) states that the
consolidated `stage25_migration_measurements.jsonl` rows are the
authoritative migration truth and the raw
`stage25_migration_observations.jsonl` rows MUST NOT be treated as
authoritative migration truth by Stage 26. Stage 26.1 reads the
observations file (when the manifest declares it) for
diagnostic / provenance purposes only; downstream Stage 26.x
calibration logic must source migration truth from the
consolidated measurement rows.

---

## 8. Stage 25 schema / vocabulary dependency — whitelist decision

### 8.1 Decision: option **A** is unnecessary because Stage 25 already exposes a clean schema/vocabulary module.

`PHX2/stage25/constants.py` already declares the closed-set
vocabularies, version axes, and locked artifact basenames Stage 26
needs:

- measurement-status / source-status / reconciliation-status /
  confidence-level / rejection-reason / price-window-kind /
  ATH-candidate-kind / measurement-family / source-family tuples,
- `STAGE25_*_FILENAME` constants and the `STAGE25_ARTIFACT_FILENAMES`
  tuple,
- `STAGE25_MANIFEST_SCHEMA_VERSION`, `STAGE25_RUNNER_NAME`,
  `STAGE25_RUNNER_VERSION`, `STAGE25_WRITER_NAME`,
  `STAGE25_WRITER_VERSION`, `STAGE25_SUMMARY_VERSION`,
- `OBSERVE_ONLY_MODE`, `REDACTION_CONFIRMED_TOKEN`,
- the `STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS` /
  `STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS` /
  `SELF_REFERENTIAL_MANIFEST_SHA256` /
  `SELF_REFERENTIAL_MANIFEST_BYTE_COUNT` /
  `SELF_REFERENTIAL_MANIFEST_ROW_COUNT` sentinels.

The `PHX2/stage25/STAGE_26_HANDOFF.md` document explicitly admits
read-only constant imports from `PHX2.stage25.constants` (§3).

### 8.2 Locked whitelist for Stage 26

Stage 26 production code MAY import (read-only) from:

- **`PHX2.stage25.constants`** — closed-set vocabularies, locked
  artifact basenames, version axes, observe-only / redaction
  tokens, manifest sentinels, forbidden-substring tuples.

Stage 26 production code MUST NOT import from any other
`PHX2.stage25` module. Specifically forbidden:

- `PHX2.stage25.models`
- `PHX2.stage25.errors`
- `PHX2.stage25.measurement_contracts`
- `PHX2.stage25.migration_observation`
- `PHX2.stage25.migration_measurement`
- `PHX2.stage25.price_observation`
- `PHX2.stage25.price_window`
- `PHX2.stage25.ath_candidate`
- `PHX2.stage25.source_reconciliation`
- `PHX2.stage25.input_reader`
- `PHX2.stage25.summary`
- `PHX2.stage25.runner`
- `PHX2.stage25.artifact_writer`
- `PHX2.stage25.stage25_manifest`

Rationale: Stage 26 must read the on-disk JSONL/JSON byte stream
and project rows into Stage 26-local record types. Importing Stage
25 record classes would couple Stage 26 to Stage 25 in-memory
shapes and would tempt Stage 26 code to share Stage 25's
construction-time invariants (e.g. Stage 25's hash-recomputation,
Stage 25's redaction sweep, Stage 25's measurement-status
derivation). Stage 26 reads the artifact contract; it does not
reuse the Stage 25 producer plumbing.

### 8.3 Extraction patch decision

No tiny Stage 25 schema-vocabulary extraction patch is needed
before Stage 26.1. `PHX2/stage25/constants.py` already serves
exactly that role. Option **A** in the Stage 26.0 spec ("a tiny
Stage 25 schema-vocabulary extraction patch before 26.1") is
therefore unnecessary; option **B** (duplicating schema locks in
Stage 26 with explicit drift tests) is rejected as redundant for
the same reason. The whitelist approach in §8.2 is the locked
choice.

---

## 9. Stage 26.1 closed-set / deferred-status policy

### 9.1 26.1 MAY declare these Stage 26-local closed sets

- `calibration_input_kind` — closed set of Stage 26.1 input record
  kinds (e.g. one kind per Stage 25 artifact projected into a Stage
  26 record),
- `measurement_truth_class` — a Stage 26 surface that re-uses the
  Stage 25 `MEASUREMENT_STATUSES` vocabulary verbatim (via the §8
  whitelist) and never adds, removes, or renames a token,
- `artifact_validation_status` — closed set of per-artifact
  validation outcomes Stage 26.1's reader emits (e.g. `VALIDATED` /
  `MANIFEST_HASH_MISMATCH` / `MANIFEST_BYTE_COUNT_MISMATCH` /
  `MANIFEST_ROW_COUNT_MISMATCH` / `FILE_MISSING` / `FILE_NOT_REGULAR`,
  exact tokens to be locked in 26.1),
- `exclusion_reason` — closed set used **strictly for validation
  and reporting vocabulary** by 26.1 (e.g. why a row failed
  manifest-level validation). 26.1's `exclusion_reason` MUST NOT be
  used to assign a calibration-eligibility decision to a row; that
  is a 26.2 surface.
- Stage 26 error-code style — typed Stage 26 errors rooted at a
  Stage 26 local `Stage26Error` base, mirroring the Stage 25
  `Stage25Error` pattern.

### 9.2 26.1 SHALL NOT declare `denominator_status`

`denominator_status` is the central locked vocabulary of the
denominator / outcome-eligibility surface (Stage 26.2). 26.1 must
not declare it, must not reference it in code, and must not allow
26.1 callers to set it on a 26.1 record.

If a future Stage 26.1 contributor argues for a "deferred"
`denominator_status` enum in 26.1 as documentation: rejected.
Vocabulary placement follows the sub-stage that owns the decision
that produces it. The decision that produces `denominator_status`
belongs to 26.2, so the vocabulary belongs to 26.2.

---

## 10. Measurement truth preservation rules

Stage 25 records measurement evidence using a closed set of truth
classes. Every one is a **first-class outcome**, not a "bad"
bucket. Stage 26 preserves them verbatim.

Locked truth classes (sourced from `PHX2.stage25.constants`):

- `MEASURED`
- `PARTIAL`
- `SOURCE_CONFLICT`
- `AMBIGUOUS`
- `MISSING`
- `UNSUPPORTED`
- `REJECTED`
- `NOT_APPLICABLE`

**Window-ineligibility note.** Stage 25 expresses
window-ineligibility through `PRICE_WINDOW_KINDS`:
`PRE_MIGRATION_EXCLUDED` and `UNKNOWN_WINDOW` are the
window-ineligible categories. Stage 25 does not emit a literal
`WINDOW_INELIGIBLE` measurement-status token; the window
ineligibility flows through the price-window-kind vocabulary and
ultimately produces `MEASUREMENT_STATUS_REJECTED` /
`MEASUREMENT_STATUS_MISSING` on downstream ATH measurements per
the Stage 25 closure-audit invariants. Stage 26 must preserve
those window-kind tokens and the resulting measurement statuses
verbatim and MUST NOT collapse window-ineligible rows into the
eligible bucket.

### Truth-class rules

- `MEASURED` is **not** the same as "truthy" — it is a specific
  Stage 25 honesty signal (two-or-more agreed source families,
  post-migration window, source-attributed truth bound into the
  `measurement_hash`).
- `PARTIAL` is **not** failure. It is real evidence below the
  cross-source honesty bar.
- `SOURCE_CONFLICT` is **not** failure. It records that two or
  more sources disagreed beyond the Stage 25 MAJOR tolerance.
- `AMBIGUOUS` is **not** failure. It records evidence the
  measurement layer refused to honestly resolve.
- `MISSING` is **not** failure. It records the absence of evidence,
  not a synthetic zero.
- `UNSUPPORTED` is **not** failure. It records that the row was
  out of scope for the measurement.
- `REJECTED` is **not** failure. It records that the row failed a
  Stage 25 validation rule.
- `NOT_APPLICABLE` is **not** failure.
- `None` / `null` MUST NOT be coerced to `0`, the empty string, the
  previous-run's value, or any synthetic default. Stage 25
  enforces this at construction time; Stage 26 must enforce it
  again at every read / project / consume boundary.

### Hard prohibitions

Stage 26 MUST NOT:

- upgrade `PARTIAL` into `MEASURED`,
- upgrade `SOURCE_CONFLICT` into `MEASURED`,
- upgrade `AMBIGUOUS` into `MEASURED`,
- upgrade `MISSING` into `MEASURED`,
- upgrade `UNSUPPORTED` into `MEASURED`,
- upgrade `REJECTED` into `MEASURED`,
- collapse `SOURCE_CONFLICT` to a single "winning" source — source
  picking is a measurement-layer decision and Stage 25 has already
  declared the row ambiguous,
- backfill `MISSING` peak prices, peak times, slots, or block-times
  with synthetic defaults,
- treat any non-`MEASURED` row as `MEASURED` for any reason,
  including for "convenience" in a calibration cohort.

Calibrators (26.4+) MAY admit non-`MEASURED` rows into a
calibration view, but ONLY under an explicit, versioned policy
token (mirroring the Stage 25 `SINGLE_SOURCE_AWARE` discipline
described in `PHX2/stage25/STAGE_26_HANDOFF.md` §4); the elevation
MUST be auditable in the resulting Stage 26 candidate-policy
artifact.

---

## 11. Updated Stage 27+ roadmap correction

The Stage 26 roadmap is corrected as follows. The corrected
roadmap supersedes any earlier informal mention of Stage 27 as the
X / social stage.

| Stage | Role |
| --- | --- |
| **Stage 26** | Calibration / candidate-policy evidence (observe-only). |
| **Stage 27** | PHX1-parity **private** live tradeable ping runner. |
| **Stage 28** | Private live runner hardening. |
| **Stage 29** | Approved enforcement wiring / live gating (consumes the operator-approved Stage 26.6 policies). |
| **Stage 30+** | X / social sidecar (after PHX2 is producing tradeable private pings). |

**Important:** Stage 27 is NOT the X / social stage. X / social is
deferred to Stage 30+ and waits until after PHX2 is producing
tradeable private pings. The Stage 25 closure handoff
(`PHX2/stage25/STAGE_26_HANDOFF.md` §5) still references "Stage
27+ deferrals" for X / social; that wording is consistent with
this corrected roadmap (X / social is a Stage 27+ deferral and now
lands specifically at Stage 30+).

---

## 12. Stage 26.1 implementation block

**Stage 26.1 implementation is BLOCKED** until both of the
following are true:

1. The `stage-25-closed` annotated tag exists in the repository
   and points to the Stage 25 closure commit (currently
   `ff241c4cab13a720904be17329da9680f25de321`, subject `docs:
   update PHX2 README for stage 25 closure`).
2. The operator gives explicit authorization in this chat to begin
   Stage 26.1 implementation.

Stage 26.1 implementation MUST NOT start under any of the
following circumstances:

- the `stage-25-closed` tag is absent,
- the `stage-25-closed` tag points to a different commit than the
  Stage 25 closure commit recorded in
  `PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md`,
- the operator has not explicitly authorized Stage 26.1
  implementation,
- any of the Stage 25.7 closure documents
  (`PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md`,
  `PHX2/stage25/STAGE_26_HANDOFF.md`) have been removed or
  materially edited without a documented Stage 25.x re-closure.

---

## 13. Stage 26.0 acceptance criteria (recorded)

The Stage 26.0 plan-turn satisfies the following:

- No Stage 26.1 implementation module is created.
- No Stage 25 artifact reader, model, calibration record,
  denominator helper, cohort builder, threshold generator, policy
  candidate, runner, writer, or CLI is added.
- No Stage 25 production behavior is changed.
- No Stage 21 / Stage 22 / Stage 23 / Stage 24 file is changed.
- No live routing / dispatch / social / Axiom / global-fee /
  execution-fee work is performed.
- The Stage 26.0 spec-lock document (this file) exists.
- The Stage 26 package scaffold (`PHX2/stage26/__init__.py`)
  exists and exports no Stage 26 runtime symbols.
- The Stage 25.7 closure-audit test
  `PHX2/tests/stage25/test_stage_25_7_closure_audit.py` was
  narrowly amended (one test renamed from
  `test_stage26_implementation_tree_does_not_exist` to
  `test_stage26_tree_is_only_stage26_0_scaffold`, its body
  relaxed to admit exactly `__init__.py` +
  `STAGE_26_0_SPEC_LOCK.md` under `PHX2/stage26/`, and the
  matching one-line update to the module docstring) so the
  Stage 26.0 spec-lock scaffold does not block the Stage 25.7
  closure-audit pass. Stage 27's parallel
  `test_stage27_implementation_tree_does_not_exist` was NOT
  touched. No other Stage 25 test, no Stage 25 production
  module, and no Stage 21 / 22 / 23 / 24 file was changed.
- `git status` shows the approved Stage 26.0 files
  (`PHX2/stage26/__init__.py`,
  `PHX2/stage26/STAGE_26_0_SPEC_LOCK.md`) plus the single
  amended test file
  (`PHX2/tests/stage25/test_stage_25_7_closure_audit.py`) plus
  the pre-existing untracked paths recorded in §3.
- No commit is created by Stage 26.0 unless the operator
  explicitly requests a commit after reviewing the diff.
- No push is performed by Stage 26.0.
