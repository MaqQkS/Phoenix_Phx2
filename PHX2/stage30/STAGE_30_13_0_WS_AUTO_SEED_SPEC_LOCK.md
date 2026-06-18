# Stage 30.13.0 — Bounded Helius WS Auto-Seeding (SPEC LOCK)

Build #24. Committed, OFFLINE, fakes-only, no-send. This document is the locked
contract for the Stage 30.13.0 auto-seed models + auto-seeder. The two later proof
substages (30.13.1 seed-only, 30.13.2 end-to-end) and the deferred real-capture handoff
(30.13.3) are governed by their own runbooks but inherit every invariant below.

## Purpose

Turn bounded Helius WS discovery output into automatically seeded candidates for the
existing supervised monitor / watchlist path — proving fresh pump-suffix migrated mints
can be discovered and seeded **without any manual hand-fed input**, **before** the
existing recheck / fake-send runs. The auto-seeder is the committed front-end that
removes the last manual input the `30.11.23 → 30.11.22` chain still required (a hand-fed
sanitized migration summary).

## Discovery currency (locked)

- Input: an injected `discovery` exposing `read_migration_evidence_batch()` returning an
  iterable of `Stage29_5MigrationEvidenceRecord` (the committed
  `Stage29_5HeliusWebSocketAdapter` over a transport at the ceremony; a fake transport
  in the proofs).
- Accepted records are projected to the committed
  `Stage29_5_7SanitizedMigrationEvidenceSummary` via the committed
  `project_migration_evidence_to_sanitized_summary` — the exact input the committed
  Stage 30.11.23 bridge consumes.
- Pump-suffix criterion = the literal `"pump"` base-mint suffix.
  **No migration-age bound in Build #24.**

## Locked per-record decision ladder (top-down, first match wins; ≤ `max_seed`)

1. not a `Stage29_5MigrationEvidenceRecord` → `ERROR` / `NOT_A_RECORD`
2. `migration_status != PRESENT` → `REJECTED` / `NOT_PRESENT_MIGRATION`
3. `base_mint` not a safe-shape pump-suffix mint → `REJECTED` / `NOT_PUMP_SUFFIX`
4. `base_mint` already accepted this run → `DUPLICATE` / `DUPLICATE_MINT` (first-wins)
5. `project_migration_evidence_to_sanitized_summary(record) is None` → `REJECTED` /
   `INCOMPLETE_EVIDENCE`
6. otherwise → `ACCEPTED` / `SEEDED_FRESH_PUMP_MIGRATION`; the sanitized COMPLETE
   summary is accumulated into the seeded watchlist.

A batch read that raises (malformed capture / budget / transport / WS error) is a clean
batch-level `ERROR` / `WS_CAPTURE_FAILED`: it seeds nothing and never escapes.

## Locked four-count ledger (the counts Build #24 records)

`accepted` / `rejected` / `duplicate` / `error`, carried on `Stage30_13SeedSummary`
alongside `records_seen`. Invariants the auto-seeder maintains:

- `len(outcomes) == accepted + rejected + duplicate + error`
- `records_seen == accepted + rejected + duplicate + (NOT_A_RECORD count)`
- a batch-level `WS_CAPTURE_FAILED` is one `error` outcome with `records_seen == 0`.
- `ACCEPTED` is the ONLY decision that appends a seeded summary; therefore
  `len(seeded_summaries) == accepted`.

## Locked discipline (every Stage 30.13 production module)

- Stdlib only (`dataclasses` / `typing`); the models leaf imports **no** PHX2 module.
- The auto-seeder imports ONLY the 30.13.0 models sibling + the three committed Stage
  29.5 discovery-currency modules (`stage29_5_migration_models`,
  `stage29_5_7_live_migration_evidence_producer`,
  `stage29_5_helius_ws_adapter`). No Birdeye / Stage 27 / Stage 28 / Stage 29.1–29.4
  import. (This Stage-29.5 deviation from the leaf "no Stage 21–29" rule is the
  documented, scoped purpose of a discovery front-end.)
- No `os.environ` / `os.getenv` (no env read). No `time` / `datetime` (no wall-clock
  read; `created_at_utc` is caller-injected). No network / socket / HTTP / gRPC /
  WebSocket. No database / compression. No filesystem write. No durable ledger
  read/mutation. No module-level Call (no implicit I/O at import time). No `while` loop /
  daemon. No raw secret / URL / provider-name literal in source.
- Redaction self-scan over every emitted seed-outcome string field; an unsafe mint is
  echoed as `REDACTED_UNSAFE_ID`, never raw.

## Non-goals (NOT built in Stage 30.13)

- No real WebSocket / socket / HTTP / gRPC connection; no real Discord; no live send; no
  approval token; no arm flip; no durable `ping_dedupe` ledger access; no wallet /
  signing / trading; no public / subscriber routing; no `PHX2/main.py` live-flag edit;
  no edit of any Stage 27 / 28 / 29 / 30.11 production file; no tag; no push.

## Handoff

Wiring a **real read-only Helius WS socket transport** behind the committed Stage 29.5
`Stage29_5WebSocketTransport` Protocol (and running the controlled capped private send)
is a SEPARATE, explicitly operator-authorized step. It is specified — but not built or
run — in `STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md`.
