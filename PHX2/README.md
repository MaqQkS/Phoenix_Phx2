# PHX2

PHX2 is a staged, auditable Phoenix fork. It is currently closed through Stage 20.

Each stage has been built dry-run-first, observe-only, and artifact-first, so that behavior can be reviewed before any live send path exists. PHX2 does not depend on the Phoenix1 runtime and does not perform any default public live sending.

## What PHX2 has built through Stage 20

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

## Safety truth (still in force)

- No default public live sending.
- No subscriber routing.
- No paid-signal routing.
- No Stage 21+ filter enforcement.
- No Phoenix1 runtime dependency.

These are not aspirational. They are the operating contract while PHX2 sits at Stage 20 closure. See [SAFETY.md](SAFETY.md) for the full contract.

## What Stage 21 is intended to introduce

Stage 21 is intended to introduce the first private, operator-controlled live ping path. That scope is expected to cover:

- Provider / API / gRPC ingestion behind a stage-owned boundary.
- Private Discord and Telegram preview pings for the operator only.

Stage 21 is explicitly **not** intended to include any of the following:

- Public routing.
- Paid-signal routing.
- Enforcement filters (filters remain observe-only).
- ATH hardening.
- Execution-fee primitives.
- X / social intelligence.

Those scopes belong to later stages and must not be pulled forward into Stage 21.

## Authoritative references

This README is descriptive. The stage-locked specs, manifests, and closure artifacts (most recently the Stage 20.4 closure / handoff) remain the source of truth for what PHX2 is allowed to do at the current stage.
