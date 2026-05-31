# PHX2 Stage 30.8.2 — Temp-Dir Compact Session Artifact Writer Closure Audit

Stage 30.8.2 closure audit is a closure / handoff slice, NOT a feature
implementation. It ships exactly two files (this closure audit and the
companion closure-audit test `test_stage_30_8_2_closure_audit.py`) and it
widens exactly two inventory-pin allowlists
(`test_stage_30_0_spec_lock.py` and
`test_stage_30_8_0_storage_spec_lock.py`) to admit those two files. This
closure slice adds ZERO production code, makes ZERO manifest change, makes
ZERO change to the Stage 30.8.2 writer behavior, edits NO renderer / no
compact models / no orchestrator / no Stage 30.7 file, performs NO commit
/ tag / push, and does NOT begin Stage 30.8.3.

This document is the closure record for the Stage 30.8.2 temp-dir compact
session artifact writer, situated in the Stage 30.8 compact session
artifact / storage-readiness family (substages 30.8.0 through 30.8.2). It
carries no provider credential, no private transport destination, no
provider host address, no transport scheme prefix, no raw provider
payload, and no request auth-metadata.

## 1. Stage 30.8.2 purpose

Stage 30.8 is the compact session artifact / storage-readiness family of
Stage 30: it prepares safe, bounded, durable capture of compact private
ping / session artifacts so the operator can eventually leave the bot
running for long private soaks / eventual 24/7 collection WITHOUT bloating
the repo, losing dedupe / session identity, writing secrets, writing raw
provider payloads, enabling enforcement / trading / public routing, or
coupling storage to live provider code.

Stage 30.8.2 is the FIRST Stage 30.8 storage writer slice. Its single
deliverable is a small, fail-closed, stdlib-only writer that persists a
caller-assembled bundle of validated Stage 30.8.1 compact artifacts to a
caller-PROVIDED output directory (a temporary / out-of-repo directory in
the Stage 30.8.2 tests), writing deterministic JSON only.

The Stage 30.8.2 stance, pinned:

- A storage writer is an atomicity / containment / fail-closed problem,
  never a convenience. A partially-written or stale-member bundle is worse
  than no bundle.
- Stage 30.8.2 owns ONLY the temp-dir bundle writer; the Stage 30.8.1
  models own the artifact shapes and the Stage 30.8.1 validators own the
  per-artifact validity decision.
- Every offline / temp-dir slice lands and is proven before any live or
  real-collection-root slice is even authorized. Stage 30.8.2 is temp-dir
  / fake / offline only.

## 2. Commit chain

The Stage 30.8 family has landed, so far, as three commits on `master`:

- 30.8.0 — lock compact session storage spec —
  `1c2bf4ddf73577fa97f575bd62c49bc031add9a2`
- 30.8.1 — compact artifact models and validators —
  `5f00b8cf5de0a2333ce2bb470abec21b5b128ee0`
- 30.8.2 — temp artifact writer —
  `115a72343de1573698378e22aa12c257a42d79c3`

This closure-audit slice builds on top of the 30.8.2 commit. The required
parent / current HEAD for this closure audit is
`115a72343de1573698378e22aa12c257a42d79c3`. This closure slice itself
makes no commit; the SHA above is the last commit in the chain at closure
time.

### Stage 30.8.2 commit metadata

The audited Stage 30.8.2 commit, recorded explicitly:

- Full SHA: `115a72343de1573698378e22aa12c257a42d79c3`
- Short SHA: `115a723`
- Subject: `phx2 stage 30.8.2: temp artifact writer`
- Parent SHA: `5f00b8cf5de0a2333ce2bb470abec21b5b128ee0` (the Stage 30.8.1
  commit)
- Tag status: no tag created for Stage 30.8.2.
- Push status: no push performed for Stage 30.8.2.

This closure-audit slice itself creates no tag and performs no push; it is
docs/tests only and awaits a separate operator commit decision.

## 3. Final proof line

The Stage 30.8 family captures, durably, the exact compact body state line
the Stage 30.7 ATH context family produced fully offline (no Discord send,
no live provider call):

```
• MC: $83k | ATH: $120k | Mig: Known
```

This is the exact compact state line a `compact_ping_artifact` durably
persists: the already-rendered `compact_body_text` plus the
operator-visible `MC` / `ATH` / `Mig` / `LP` / `Net` display strings, never
the raw provider input. Stage 30.8.2 persists that sanitized projection to
disk; it never re-derives or fabricates any market value.

## 4. Final data path

The complete Stage 30.8.2 write data path, end to end:

```
caller-assembled Stage 30.8.1 compact artifacts
  -> Stage30_8CompactSessionArtifactBundle
  -> write_compact_session_artifact_bundle(output_dir, bundle)
  -> per-member EXACT-type gate + Stage 30.8.1 validator (validate first)
  -> field-projected deterministic JSON (members, validation_result, manifest)
  -> hidden staging directory under output_dir
  -> staged-bundle completeness verify
  -> whole-directory rename onto the final session directory
```

Expanded, with the owning surface of each hop:

- A future caller assembles, in memory, the Stage 30.8.1 compact artifacts
  for ONE private-soak session (a session summary, terminal ping
  artifacts, dispatch-attempt artifacts, error artifacts, a storage-budget
  snapshot) into a **`Stage30_8CompactSessionArtifactBundle`** — a lenient,
  passive, frozen carrier that does NOT validate its members at
  construction.
- The public entry point
  **`write_compact_session_artifact_bundle(output_dir, bundle)`** gates the
  inputs fail-closed, in order: the `output_dir` must be an explicit `str`
  / `Path` (no empty, no bare `.`, no default storage root); the `bundle`
  must be EXACTLY a `Stage30_8CompactSessionArtifactBundle`; the
  `session_id` must be a safe single path component; every present member
  must be the EXACT Stage 30.8.1 model type and must pass its matching
  Stage 30.8.1 validator (the bundle must hold at least one member); and
  the session directory must resolve strictly under `output_dir`.
- Only after ALL gates pass does the writer serialize the whole bundle
  up-front (pure; no I/O), build the COMPLETE bundle in a fresh hidden
  staging directory, verify the staged bundle is complete and
  self-consistent, and promote it onto the final session directory by a
  whole-directory rename.

There is no duplicate validity logic on this path: the per-artifact valid
/ invalid decision lives entirely in the Stage 30.8.1 validators; the
writer adds only the bundle-level type gate, path containment, and atomic
promotion.

## 5. File inventory by substage

### Stage 30.8.0 — `1c2bf4d`
- Production / docs: `STAGE_30_8_0_COMPACT_SESSION_STORAGE_SPEC_LOCK.md`,
  `stage30_8_manifest.py` (constants-only manifest).
- Tests: `test_stage_30_8_0_storage_spec_lock.py`; narrow inventory-
  allowlist widening on `test_stage_30_0_spec_lock.py`.
- Spec lock + manifest + pin test only. ZERO storage writer, ZERO
  database, ZERO SQLite, ZERO filesystem artifact writer, ZERO zstd.

### Stage 30.8.1 — `5f00b8c`
- Production: `stage30_8_artifact_models.py` (passive frozen compact
  artifact records + closed-set vocabularies),
  `stage30_8_artifact_validators.py` (deterministic per-artifact
  validators). Additive constants edit to `stage30_8_manifest.py`.
- Tests: `test_stage_30_8_1_artifact_models.py`,
  `test_stage_30_8_1_artifact_validators.py`,
  `test_stage_30_8_1_boundaries.py`, `test_stage_30_8_1_manifest.py`.
- Pure models + validators only. NO writer, NO database / SQLite /
  filesystem artifact writer, NO zstd / compression, NO dedupe / session
  index. The models import no PHX2 module; the validators import only the
  models sibling.

### Stage 30.8.2 — `115a723`
- Production: `stage30_8_temp_artifact_writer.py` (the temp-dir bundle
  writer: input bundle carrier + write-result record + the
  `write_compact_session_artifact_bundle` entry point). Additive constants
  edit to `stage30_8_manifest.py`.
- Tests: `test_stage_30_8_2_temp_artifact_writer.py`,
  `test_stage_30_8_2_boundaries.py`, `test_stage_30_8_2_manifest.py`.
- Inventory-allowlist widening on `test_stage_30_0_spec_lock.py`.
- The writer imports ONLY stdlib (`json` / `pathlib` / `re` /
  `dataclasses` / `typing`) plus the Stage 30.8.1 models + validators
  siblings. No renderer / compact models / orchestrator / Stage 30.7 edit.

### Stage 30.8.2 closure (this slice, uncommitted)
- Docs: `STAGE_30_8_2_TEMP_ARTIFACT_WRITER_CLOSURE_AUDIT.md` (this file).
- Tests: `test_stage_30_8_2_closure_audit.py`.
- Inventory-allowlist widening only: `test_stage_30_0_spec_lock.py`,
  `test_stage_30_8_0_storage_spec_lock.py`.
- No production code, no manifest change, no renderer / compact models /
  orchestrator / Stage 30.7 edit, no writer behavior change.

## 6. Safety invariants

The Stage 30.8.2 writer holds the following invariants. They were proven
by the Stage 30.8.2 boundary tests (positive stdlib + PHX2 import
allowlists, an AST no-top-level-Call check, forbidden-needle scans, and
no-runtime-integration pins) and the Stage 30.8.2 writer / manifest tests,
and are re-stated here for the record:

- offline / temp-dir only
- no live provider / Discord call
- no env read
- no database / SQLite
- no zstd / compression
- no network module
- caller-provided output directory only
- no default storage root / real bot artifact directory
- no enforcement / public routing / trading / wallet / social
- no drawdown / tier recomputation
- no Stage 25 / 27 / 28 / 29 production import
- no Stage 29.5 production import
- renderer / compact models / orchestrator untouched

The Stage 30.8.2 writer module imports only `__future__` / `typing` /
`dataclasses` / `json` / `pathlib` / `re` from the standard library and,
for PHX2, only the Stage 30.8.1 models + validators siblings. It imports
NO `os` (so it performs NO `os.environ` / `os.getenv` env read), NO
`sqlite3`, NO `zstd` / compression module, NO `shutil`, NO network module,
NO provider / Discord surface, and NO Stage 21–29 / Stage 29.5 / PHX1
module. The runtime orchestrators, the compact renderer, and the compact
models do NOT import the writer (the writer stays a standalone temp-dir
sink).

## 7. Fail-closed write invariants

The writer NEVER persists a partial, stale, or unvalidated bundle. The
fail-closed rules, proven across the Stage 30.8.2 tests:

- Validate every present member with its matching Stage 30.8.1 validator
  BEFORE any byte is written; a single INVALID member aborts the whole
  bundle and writes nothing (`status = INVALID`,
  `reason = INVALID_ARTIFACT`, the underlying validator reason carried on
  `validation_reason`).
- Every accepted member must be the EXACT Stage 30.8.1 model type
  (`type(x) is Model`, never a subclass), so a subclass carrying an extra
  field is rejected with `reason = INVALID_ARTIFACT_TYPE`; an empty bundle
  is rejected with `reason = EMPTY_BUNDLE`.
- The `session_id` is sanitized to a single safe path component (no `..`,
  no separator, no drive / colon, no NUL, no whitespace-only id) AND the
  resolved session directory is asserted to stay strictly under
  `output_dir`; a containment failure fails closed with
  `reason = PATH_ESCAPE`.
- The writer builds the COMPLETE bundle in a fresh hidden staging
  directory `output_dir/.<session>.staging.<n>`, writes the member JSON,
  then `validation_result.json`, then `manifest.json` LAST (the commit
  marker), and verifies the staged directory contains EXACTLY the expected
  files and that the staged `manifest.json` references exactly the staged
  member files.
- Promotion is a whole-directory rename: any prior final directory is
  first moved aside to a unique `output_dir/.<session>.previous.<n>`, then
  the staging directory is renamed onto the final session directory — a
  whole-directory swap, so NO stale member file from a prior, larger
  bundle can survive.
- On any filesystem failure the writer fails closed and returns
  `WRITE_FAILED`: a pre-promotion failure leaves the prior final directory
  untouched and cleans the staging directory; a failure during the
  staging→final rename rolls the previous directory back into place. The
  result NEVER reports a final directory whose `manifest.json` references
  missing or partially-replaced files, and `safe_to_persist` is `True`
  ONLY when `status` is `WRITTEN`.

The closed set of write statuses is `WRITTEN` / `INVALID` /
`WRITE_FAILED`. The closed set of writer-owned reasons is `OK`,
`INVALID_OUTPUT_DIR`, `INVALID_BUNDLE_TYPE`, `INVALID_SESSION_ID`,
`EMPTY_BUNDLE`, `INVALID_ARTIFACT_TYPE`, `INVALID_ARTIFACT`,
`PATH_ESCAPE`, `WRITE_FAILED`.

## 8. Determinism and no-leak invariants

The persisted bytes are deterministic and leak nothing beyond the
sanitized Stage 30.8.1 model fields:

- Stable lower-snake filenames (`manifest.json`,
  `validation_result.json`, `session_summary.json`,
  `storage_budget_snapshot.json`, and zero-padded
  `ping_artifact_<NNNN>.json` / `dispatch_attempt_<NNNN>.json` /
  `error_artifact_<NNNN>.json`), so a lexical sort matches insertion order.
- JSON written with sorted keys, real UTF-8 (no ASCII escaping), a
  two-space indent, and a single trailing newline. The same input
  serializes to identical bytes regardless of where it is written.
- The persisted JSON carries no absolute path and no wall-clock value: the
  writer reads no clock and the transient staging / previous directory
  names are never persisted into any artifact. The bundle manifest
  envelope is identified by the bundle schema version
  `stage30_8_v0_compact_session_bundle`.
- Serialization NEVER uses `dataclasses.asdict`; it projects ONLY the
  canonical fields enumerated from the BASE Stage 30.8.1 model class, so an
  extra attribute on a subclass or duck-typed object can never leak into a
  persisted artifact. A non-leaf value (a nested object in a flat field, a
  binary blob) raises and fails the write closed rather than persisting an
  unexpected value.

## 9. Storage location discipline

Stage 30.8.2 takes a caller-provided `output_dir` ONLY. There is no
default storage root, no repo-relative implicit output, no env-var lookup,
no global path config, and no home-directory expansion. Every Stage 30.8.2
test writes ONLY into a pytest `tmp_path` temporary directory (out of the
repository); none touches a real operator collection root, the repository
working tree, or any live runtime path. The default-storage-location and
real-collection-root decisions are explicitly deferred (Section 10).

## 10. What Stage 30.8.2 explicitly did NOT solve

Stage 30.8.2 closed the offline temp-dir bundle writer only. It did NOT
solve, and explicitly deferred:

- live capture / controlled session proof
- dedupe / session index integration
- write-time storage-budget enforcement
- day-partitioned rolling
- zstd compression
- default storage location / real collection root
- drawdown from ATH
- tier dip
- enforcement
- public routing
- wallet/trading

## 11. Next recommended stage

Stage 30.8.3: dedupe / session index integration (offline).

The temp-dir bundle writer is now offline-complete and proven. The natural
next problem is wiring the Stage 30.6 restart-safe dedupe / session
seen-state into the artifact index using fakes only, so duplicate terminal
ping artifacts collapse to exactly one per (session, ping) dedupe identity.
Write-time storage-budget enforcement (gating writes on the Stage 30.6
soft 65% / hard 90% disk caps), day-partitioned rolling, optional zstd
compression, a default storage location, and any live / real-collection
proof remain gated behind that offline integration and a separate audit.

## 12. Codex review history and final pass counts

Stage 30.8.2 was reviewed by Codex. The initial Codex review returned
FAIL; the committed Stage 30.8.2 writer design and its offline test suite
address every finding, and the Codex re-audit returned PASS WITH MINOR
NOTES. This section records that review history for the closure file.

### 12.1 Initial Codex FAIL findings

The initial Codex review flagged the following risks. Each is a risk the
committed writer / test suite remediates, NOT a behavior the committed
writer exhibits:

- direct writes into final session dir
- stale manifest / partial rewrite risk
- shrinking rewrite stale artifact risk
- isinstance + asdict subclass extra-field leak
- missing tests for failure/rewrite/manifest-order/shrinking rewrite
- future-stage guard only checked 30_8_3 and 30_8_4
- whitespace-only session IDs not tested

### 12.2 Remediations (committed at 115a723)

The committed Stage 30.8.2 writer and its offline test suite remediate
each finding:

- The writer never writes into the final session directory in place: it
  builds the complete bundle in a hidden staging directory under
  output_dir, writes the member JSON, then validation_result.json, then
  manifest.json last (the commit marker).
- A staging verification step asserts the staged directory holds exactly
  the expected files and that the staged manifest references exactly those
  members before any promotion.
- Promotion is a whole-directory replacement: any prior final directory is
  renamed aside (final→previous), then the staging directory is renamed in
  (staging→final); a promotion failure triggers a rollback that restores
  the previous directory, so a shrinking rewrite can never leave a stale
  member file behind.
- The subclass extra-field leak is closed by exact top-level type gates
  (`type(x) is Model`, not `isinstance`) plus strict base-model field
  projection (the canonical base-model fields only, never
  `dataclasses.asdict`).
- The future-stage guard was generalized from an enumerated 30_8_3 /
  30_8_4 check to a generic regex guard that blocks any
  `stage30_8_<N>=3`-or-higher minor token (`stage30_8_<N>` /
  `stage_30_8_<N>` for N >= 3).
- The writer test suite adds coverage for the failure, rewrite,
  manifest-order, shrinking-rewrite, and whitespace-only session IDs paths.

### 12.3 Codex re-audit verdict

- Verdict: PASS WITH MINOR NOTES
- Critical: none
- Major: none
- Safe to commit after final tests: yes

### 12.4 Codex re-audit final pass counts

The Codex re-audit reported the following pass counts for the surrounding
suite and the Stage 30.8.2 implementation tests (writer + boundaries +
manifest). This closure-audit test file adds its own cases on top of these
figures, so a re-run of `test_stage_30_8_2_*.py` or the full Stage 30 suite
on the committed tree reports a correspondingly higher total:

- Stage 30.8.2 targeted: 62 passed
- Stage 30.8.1 + 30.8.0 + 30.0 regression: 172 passed
- Stage 30.7.4 regression: 47 passed
- Full Stage 30 pre-commit: 2186 passed
- Full Stage 30 post-commit: 2186 passed
- git diff --check clean

---

_Stage 30.8.2 closure audit is a closure / handoff slice. There is no
production code change, no manifest change, no renderer / compact models /
orchestrator change, no Stage 30.7 file change, no writer behavior change,
no live / provider / Discord, no commit, no tag, and no push performed by
this closure slice._
