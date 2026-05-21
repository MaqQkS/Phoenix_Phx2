# PHX2

PHX2 is a staged, auditable Phoenix fork. It is currently implemented through Stage 25.7 locally; Stage 25 is not tagged yet (operator authorization required).

Each stage has been built dry-run-first, observe-only, and artifact-first, so that behavior can be reviewed before any live send path exists. PHX2 does not depend on the Phoenix1 runtime and does not perform any default public live sending.

## What PHX2 has built through Stage 25.7

PHX2 has progressively layered the following observe-only and artifact-producing primitives:

- Schema and migration boundaries for the PHX2-owned database.
- Alert eligibility decisions evaluated against snapshotted features.
- Renderer and dispatch preview primitives that emit artifacts instead of sending.
- Outcome tracking for previewed candidates.
- Observe-only filter evaluation (no enforcement).
- Decision feature snapshots that pin the inputs behind each decision.
- Analysis, recommendation, and replay layers built on top of those snapshots.
- Operator approval and review artifacts for human-in-the-loop inspection.
- Stage 20 preview candidate builder, empty filter interface scaffolding, and the Stage 20.4 closure / handoff package.
- Stage 21–24 closed surfaces (private operator live-ping path, ATH/migration evidence intake, execution-primitive closure — see prior closure audits).
- Stage 25 ATH / migration measurement hardening (see below).

## Stage 25 closure — ATH/migration measurement hardening

Stage 25 produces deterministic, redacted, hashed observe-only measurement evidence for migration boundary and post-migration ATH truth. Substages:

- 25.1 measurement contracts and input scaffolding
- 25.2 migration measurement scaffold
- 25.3 price observation window scaffold
- 25.4 ATH candidate builder from source windows
- 25.5 source reconciliation and confidence labeling
- 25.6 runner / writer / deterministic measurement artifacts
- 25.7 closure audit and Stage 26 handoff (docs/tests only)

Stage 25 emits the following locked artifact basenames into a caller-supplied output directory (see `PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md` for the full set):

- `stage25_migration_observations.jsonl`
- `stage25_migration_measurements.jsonl`
- `stage25_price_window_observations.jsonl`
- `stage25_ath_candidates.jsonl`
- `stage25_source_reconciliations.jsonl`
- `stage25_ath_measurements.jsonl`
- `stage25_measurement_rejections.jsonl`
- `stage25_summary.json`
- `stage25_manifest.json`

### Stage 25 measurement-truth invariants

- no fake migration timestamp when migration evidence is ambiguous
- no fake ATH when source data is missing
- no `0` price / `0` ATH as a missing sentinel
- ambiguous, source-conflicted, or missing data stays explicit through the closed-set status vocabulary (`MEASURED` / `PARTIAL` / `AMBIGUOUS` / `SOURCE_CONFLICT` / `MISSING` / `UNSUPPORTED` / `REJECTED` / `NOT_APPLICABLE`)
- single-source evidence stays `PARTIAL` unless a future versioned policy explicitly admits it
- non-measured records cannot fake measured peak fields

### Stage 25 tag status

- `stage-25-closed` is **not** created yet.
- The tag is operator-created only, after explicit authorization, following the discipline documented in `PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md`.

## Safety truth (still in force)

- No default public live sending.
- No subscriber routing.
- No paid-signal routing.
- No Stage 21+ filter enforcement promoted to hard-block.
- No Phoenix1 runtime dependency.

These are not aspirational. They are the operating contract through Stage 25 closure. See [SAFETY.md](SAFETY.md) for the full contract.

## What Stage 26 is intended to introduce

Stage 26 consumes Stage 25's deterministic measurement artifacts to calibrate measurement-aware enforcement candidates. The recommended first substage is:

**Stage 26.1 — calibration input contracts + artifact readers.**

Stage 26 is intended to cover:

- typed input contracts for the Stage 25 artifact filenames listed above
- pure, side-effect-free readers that project each JSONL row into an immutable Stage 26 record
- Stage 25 manifest verification (`sha256` / `byte_count` recompute, with the documented `SELF_REFERENTIAL_MANIFEST_SHA256` exception for the manifest self-entry)

Stage 26 is explicitly **not** intended to include:

- enforcement of any threshold (later Stage 26 substage)
- silently picking a source winner when Stage 25 emitted `SOURCE_CONFLICT` or `AMBIGUOUS`
- backfilling `MISSING` / `UNSUPPORTED` rows with fake values
- mutating Stage 25 artifacts in any form
- rewriting migration / ATH truth (Stage 25 statuses are authoritative)
- Stage 27 X / social intelligence, social-token joins, or tweet ingestion
- public / subscriber routing, Discord / Telegram dispatch, or any transport surface
- reopening the confirmed Axiom / global-fee / execution-fee decoder (Stage 24 closed surface; only reopened on operator authorization with sanitized fixture proof)

Those scopes belong to later stages and must not be pulled forward into Stage 26.1.

## Authoritative references

This README is descriptive. The stage-locked specs, manifests, and closure artifacts remain the source of truth for what PHX2 is allowed to do at the current stage. Stage 25's authoritative closure documents live alongside the Stage 25 production code:

- `PHX2/stage25/STAGE_25_CLOSURE_AUDIT.md` — Stage 25 closure audit (commit inventory, invariants, locks, tag guidance)
- `PHX2/stage25/STAGE_26_HANDOFF.md` — Stage 26 handoff (calibration scope, must-not rules, deferrals)
