# PHX2 Stage 25 Closure Audit — ATH/migration measurement hardening

## 1. Closure status

- Stage 25.1 through 25.6 implemented and committed.
- Stage 25.7 adds closure docs and tests only; no Stage 25.1–25.6
  production logic was changed during the closure pass.
- Stage 25 remains untagged until the operator creates the
  `stage-25-closed` annotated tag (see Section 11).

## 2. Commit inventory

The six Stage 25 substage commits, in order:

| Substage | Full SHA | Short | Subject |
| --- | --- | --- | --- |
| 25.1 | `2a9ba710aa1728af486e8b7b582542d1db3d6a50` | `2a9ba71` | phx2 stage 25.1: measurement contracts and input scaffolding |
| 25.2 | `76a7051382d46540de4763e7da96c674f0924242` | `76a7051` | phx2 stage 25.2: migration measurement scaffold |
| 25.3 | `dd4990abde77b726dc54879d2230d7a4a961ae33` | `dd4990a` | phx2 stage 25.3: price observation window scaffold |
| 25.4 | `a3bd7645f50cf30198d537e71bfe44eee3504554` | `a3bd764` | phx2 stage 25.4: ath candidate builder from source windows |
| 25.5 | `16a6129530760a91ca56e2e2abceb158205ac47b` | `16a6129` | phx2 stage 25.5: source reconciliation and confidence labeling |
| 25.6 | `18c20db27de757e67fd9fc1f6dc8a14e318d5097` | `18c20db` | phx2 stage 25.6: runner writer and deterministic measurement artifacts |

## 3. Stage 25 mission

Stage 25 produces **deterministic, redacted, hashed observe-only
measurement evidence** for migration boundary and post-migration
ATH (all-time-high) truth.

Stage 25 explicitly does NOT:

- calibrate thresholds (Stage 26 surface)
- enforce gates / blocks / routing decisions (Stage 26+ surface)
- dispatch to Discord / Telegram / public / subscriber channels
- ingest or rank X / social-intelligence evidence
- reopen confirmed Axiom / global-fee / execution-fee decoding
  (Stage 24 closed surface)
- read or write any DB, RPC, or network resource at runtime

Stage 25 emits one immutable, source-attributed, status-honest
measurement bundle per run. Every downstream consumer (Stage 26+)
must respect the in-band status tokens (`MEASURED` / `PARTIAL` /
`AMBIGUOUS` / `SOURCE_CONFLICT` / `MISSING` / `UNSUPPORTED` /
`REJECTED` / `NOT_APPLICABLE`) verbatim.

## 4. Substage summary

| Substage | Scope |
| --- | --- |
| 25.1 | Contracts / models / input reader / manifest scaffolding |
| 25.2 | Migration event / timestamp measurement scaffold |
| 25.3 | Price observation / source adapter artifact reader |
| 25.4 | ATH candidate builder from source-windowed observations |
| 25.5 | Source reconciliation + confidence labeling |
| 25.6 | Runner / writer / deterministic artifacts |
| 25.7 | Closure audit + Stage 26 handoff (docs/tests only) |

## 5. Measurement truth invariants

These invariants are the load-bearing honesty contract every Stage
25 measurement run satisfies. Future stages (especially Stage 26
calibration / enforcement) MUST NOT relax any of them.

- no fake ATH when source data is missing
- no fake migration timestamp when migration evidence is ambiguous
- no `0` price as a missing sentinel
- no `0` ATH as a missing sentinel
- `None` / null requires an explicit closed-set status token; the
  pair `(price=None, source_status=PRESENT)` is rejected at record
  construction
- ambiguous migration cannot produce a measured ATH
  (`migration_measurement_blocks_measured_ath`)
- pre-migration price windows (`PRE_MIGRATION_EXCLUDED`) cannot
  become ATH-eligible
- `UNKNOWN_WINDOW` price windows cannot become ATH-eligible
- any `AMBIGUOUS` source-status candidate poisons the entire
  per-token reconciliation
- a `MEASURED` ATH measurement requires at least two distinct contributing source families (`AGREED` reconciliation)
- `SINGLE_SOURCE` reconciliation remains `PARTIAL`, never
  `MEASURED`
- `DISAGREED_MAJOR` reconciliation produces `SOURCE_CONFLICT`, never
  `MEASURED`
- a non-`MEASURED` ATH measurement cannot carry fake peak fields:
  `consolidated_peak_price` is `None`, `peak_source_family` is the
  empty string, `reconciled_peak_observed_at_utc` is the empty
  string, slot/block-time are the `-1` absent sentinel

## 6. Locked artifact filenames

Stage 25.6 ships the deterministic writer. The locked artifact
basenames are:

JSONL:

- `stage25_migration_observations.jsonl`
- `stage25_migration_measurements.jsonl`
- `stage25_price_window_observations.jsonl`
- `stage25_ath_candidates.jsonl`
- `stage25_source_reconciliations.jsonl`
- `stage25_ath_measurements.jsonl`
- `stage25_measurement_rejections.jsonl`

JSON:

- `stage25_summary.json`
- `stage25_manifest.json`

CSV (optional, locked off in 25.6):

- `STAGE25_EMITS_SOURCE_COVERAGE_CSV = False` — Stage 25 does NOT
  emit the optional source-coverage CSV. The decision is locked
  in `PHX2/stage25/constants.py`; future sub-stages that flip the
  flag MUST update this audit and the Stage 25.6 boundary tests at
  the same time.

## 7. Manifest / writer invariants

- Every manifest file entry records `file_basename`, `sha256`,
  `row_count`, and `byte_count`. `row_count = -1` and
  `byte_count = -1` are reserved for the "not applicable" sentinel
  case (the manifest's own self-entry).
- The artifact manifest carries the runner / writer identity
  tokens (`runner_name`, `runner_version`, `writer_name`,
  `writer_version`) so downstream readers can pin the exact runner
  / writer pair that produced a manifest.
- The artifact manifest carries the locked `observe_only_mode`
  token and the `redaction_confirmed` token. The
  `redaction_confirmed` field is set to the locked
  `REDACTION_CONFIRMED_TOKEN` value (`"stage25_redaction_confirmed"`)
  only after the writer's redaction sweep passes; an empty string
  signals a manifest that did not run the sweep.
- The manifest carries the caller-injected `created_at_utc`
  string; the writer never reads the wall clock.
- The optional Stage 24 manifest pin is recorded as
  `(upstream_manifest_basename, upstream_manifest_sha256)` only —
  Stage 25 does NOT import Stage 24 production code, and the pin
  carries no Stage 24 execution-fee state.
- The manifest's own self-entry uses the locked sentinel
  `SELF_REFERENTIAL_MANIFEST_SHA256` (a non-hex string deliberately
  designed not to be confused with a real 64-hex digest) and the
  `-1` sentinel for both `row_count` and `byte_count`. The
  self-entry convention is the Stage 25.6 deterministic solution
  to the self-referential hash problem: the manifest cannot record
  the true hash of its own bytes without breaking the hash chain.
- The writer runs a redaction sweep over every row, the summary
  mapping, AND the assembled artifact-manifest body BEFORE any
  bytes hit disk. URL / webhook / secret-bearing value substrings
  are rejected even inside `*_hash` / `*_sha256` fields; the
  hash-field allowlist only relaxes the long-hex-run check, never
  the URL / webhook / forbidden-field-name checks.
- The writer never leaves partial artifacts on validation /
  redaction failure: every check (output_dir / created_at_utc /
  tuple-types / summary `row_counts` / Stage 24 pin / row
  redaction / manifest redaction) runs BEFORE the first atomic
  write.
- Identical input tuples + identical injected `created_at_utc`
  produce byte-identical artifact files (canonical JSON sorted
  keys, no whitespace, UTF-8, deterministic per-tuple sort orders
  inherited from Stage 25.2–25.5).

## 8. Boundary invariants

- No Stage 25 production module imports `PHX2.stage21` /
  `PHX2.stage22` / `PHX2.stage23` / `PHX2.stage24` production code.
- No Stage 25 production module imports a network / RPC /
  messaging / DB / scheduler / secrets-management library.
- No Stage 25 production module reads `os.environ` / `os.getenv`.
- No Stage 25 production module contains a CLI surface or
  `__name__ == "__main__"` guard.
- No Stage 25 production module performs top-level (import-time)
  file I/O. The Stage 25.6 `artifact_writer` module is the ONLY
  Stage 25 production module permitted to call file-write
  primitives, and it does so exclusively inside the explicit
  `write_stage25_artifacts` / `write_atomic_text` function bodies
  — never at import time.
- Stage 25 production code does not implement Stage 26 calibration
  / enforcement logic.
- Stage 25 production code does not implement Stage 27 X / social
  ranking logic.
- Stage 25 production code does not reopen Stage 24 execution-fee
  decoding (Axiom / global-fee / Jito / compute_budget /
  router_fee identifiers remain on the Stage 25 forbidden
  identifier list).

## 9. Test status

- Codex Stage 25.7 planning audit: **PASS** (no critical, no
  major, no minor findings).
- Latest focused Stage 25 suite before 25.7 closure: 801 passed.
- The Stage 25.7 closure tests in
  `PHX2/tests/stage25/test_stage_25_7_closure_audit.py` pin this
  document's content (commit SHAs, invariants, locks, handoff
  references) at the source-text level so a future regression
  flips the test red rather than silently drifting.

## 10. Stage 25.7 implementation discipline

Stage 25.7 is a **docs-and-tests-only** closure pass:

- No Stage 25.1–25.6 production logic was changed.
- No new Stage 25 production `.py` modules were added.
- No `os.environ` reads, no network calls, no DB writes, no
  dispatchers, no CLI entry points, no Discord / Telegram /
  webhook code, no calibration / enforcement / X / social
  modules were added.
- The Stage 25.6 boundary test was updated to remove the two
  closure documents (`STAGE_25_CLOSURE_AUDIT.md`,
  `STAGE_26_HANDOFF.md`) from its forbidden-future-filename list
  so that the closure docs are admitted by the inventory check.

## 11. Tag guidance

This implementation does not create any tag. No tag is created
by Stage 25.7 — operator authorization is required. The
`stage-25-closed` annotated tag is reserved for the operator and
will be created only after:

1. The operator runs the final focused Stage 25 test pass and
   verifies all tests pass.
2. The operator reviews this audit document and the Stage 26
   handoff document (`STAGE_26_HANDOFF.md`).
3. The operator gives explicit authorization to tag.

No Stage 25 production module, test file, or documentation in
this pass calls `git tag`, writes to `.git/`, or otherwise
attempts to create the closure tag automatically.
