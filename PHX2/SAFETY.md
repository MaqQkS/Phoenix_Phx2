# PHX2 Safety Contract

PHX2 is closed through Stage 20. This document captures the safety contract that remains in force at Stage 20 closure, before any Stage 21+ live-ping work begins.

## Hard Rules

- **Phoenix1 isolation.** Phoenix1 remains isolated. PHX2 must not mutate Phoenix1 tables. PHX2 runtime modules must not consume Phoenix1 code or rely on Phoenix1 database assumptions.
- **No public, subscriber, or paid routing.** No public routing, subscriber routing, or paid-signal routing is permitted before an explicit later-stage promotion that owns and gates that path.
- **No default live sends.** PHX2 must not perform any default live send. The first live path is reserved for Stage 21-owned private ping wiring (operator-only, private channels). Until that wiring exists and is explicitly enabled, dispatch stays at the preview/artifact layer.
- **Filters are observe-only.** Filter evaluation remains observe-only. Filters must not enforce, suppress, or gate dispatch unless a later stage explicitly promotes them to enforcement.
- **Stage-owned credential boundary.** Provider credentials, webhooks, and API keys must be loaded only through a stage-owned boundary. Scattered `os.getenv` reads inside runtime modules are not permitted.
- **Stage-owned network boundary.** Network, provider, and dispatch code must live only inside an explicitly owned Stage 21+ subtree or boundary. It must not be sprinkled across earlier-stage modules.

## Current Stage

PHX2 is at Stage 20 closure. The Stage 20.4 closure / handoff package is the authoritative current planning reference for what is in scope, what is deferred, and what Stage 21 is expected to pick up.

Through Stage 20, PHX2 has produced observe-only, artifact-first layers for schema and migration boundaries, alert eligibility decisions, renderer and dispatch preview primitives, outcome tracking, observe-only filter evaluation, decision feature snapshots, analysis / recommendation / replay layers, operator approval and review artifacts, and the Stage 20 preview candidate / empty filter interface / closure handoff work.

None of that constitutes a live send path.

## Verification Outputs

PHX2 proves behavior before any live sending through:

- PHX2-owned database rows.
- Preview candidate and decision snapshot artifacts.
- Renderer / dispatch preview artifacts.
- Operator approval and review artifacts.
- Replay and analysis outputs against snapshotted inputs.

Private operator-only channels (Discord, Telegram) are reserved for Stage 21 private ping wiring and are not active at Stage 20 closure.

## Authoritative References

Root documentation (this file and the root [README.md](README.md)) is descriptive only. It must not override stage-locked specs, stage manifests, or stage closure artifacts. Where this document and a stage-locked artifact disagree, the stage-locked artifact wins and this document should be corrected.
