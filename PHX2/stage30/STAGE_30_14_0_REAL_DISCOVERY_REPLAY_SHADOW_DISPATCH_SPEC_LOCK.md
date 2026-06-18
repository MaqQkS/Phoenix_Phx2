# Stage 30.14.0 — Real-Discovery Replay → Shadow Dispatch (SPEC LOCK)

Build #26, substage 30.14.0. Committed, OFFLINE, SYNTHETIC-fixture only, no-send. This
document is the locked contract for the Stage 30.14.0 replay-discovery models + replay
source + shadow-dispatch orchestrator + manifest. It composes (never edits) the committed
Stage 30.13.0 auto-seeder and the committed Stage 30.11.23 → 30.11.22 recheck / fake-send
chain.

## Build numbering

- **Build #24** — committed offline WS auto-seeder (Stage 30.13.0–30.13.2 + 30.13.3
  handoff + 30.13.4 hardening).
- **Build #25** — the Stage 30.13.3 handoff executed out-of-repo: a real **read-only**
  Helius WS capture that accepted the real `*pump` mint
  `A2R6WLJV67K6TVCHNWbEULcWzYobHYPdwe5beC2Rpump`. Read-only discovery only; it persisted
  the discovery **decision** ledger (the accepted mint + four counts), **not** the
  underlying migration evidence.
- **Build #26 (this slice, 30.14.x)** — take a discovered migration evidence record and
  run it through the existing committed recheck → fake-dispatch chain. Build 26.0 is the
  committed, offline, **synthetic** plumbing proof; pointing the same seam at a real
  evidence-bearing artifact (Build 26.1) is deferred and **blocked** (see Handoff).

## Purpose

Prove, with a SYNTHETIC migration evidence record replayed from memory (never a live
capture), that a discovered `*pump` mint flows end-to-end to a **fake dispatch decision**
through the committed chain — and that the dispatched mint traces back to the discovered
mint — with **no real send**, no durable ledger, and no provider/network/secret surface.

## Locked composition (top-down)

```
SYNTHETIC Stage29_5MigrationEvidenceRecord (built by the test; PRESENT + full quartet +
    trailing-Z anchor + slot + signature + source_ref)
  → Stage30_14ReplayDiscoverySource.read_migration_evidence_batch()   (in-memory; no socket)
  → committed build_seeded_watchlist_from_ws_discovery (Stage 30.13.0; max_seed = 1)
      → seeded watchlist = (Stage29_5_7SanitizedMigrationEvidenceSummary,)
  → committed run_stage30_11_23_fake_real_fed_dry_run_proof (max_summaries = 1)
      = Stage 30.11.23 bridge → Stage 30.11.22 dry-run
        (30.11.8 confirmation → 30.11.7 enrichment → 30.9.3 dip gate)
        over INJECTED deterministic FAKE price / market-context / ATH sources
        + a FRESH in-memory dedupe ledger + a FRESH recording FAKE dispatch client
  → Stage30_14ShadowDispatchResult (seed result + dry-run result + dispatch trace)
```

## Locked discipline (every Stage 30.14 production module)

- Stdlib only (`dataclasses` / `typing`); the models leaf imports **no** PHX2 module.
- The replay source imports ONLY the committed Stage 29.5 migration-models closed-set
  capture error (the scoped discovery-currency deviation) + the 30.14.0 models sibling.
- The orchestrator imports ONLY the 30.14.0 siblings + the committed Stage 30.13.0
  auto-seeder + the committed Stage 30.11.23 fake proof. No Birdeye / Stage 27 / Stage 28
  / Stage 29.1–29.4 import; the committed Stage 29.5 record/projection/WS-adapter are
  reached **transitively** through the auto-seeder, never imported directly.
- No `os.environ` / `os.getenv` (no env read). No `time` / `datetime` (no wall-clock read;
  every timestamp/clock is caller-injected). No network / socket / HTTP / gRPC / WebSocket.
  No database / compression. No filesystem write. No durable ledger read/mutation. No
  module-level Call (no implicit I/O at import time). No `while` loop / daemon.
- Redaction self-scan over every emitted dispatch-trace string field; an unsafe mint / kind
  token is echoed as `REDACTED_UNSAFE_ID`, never raw. No bare provider name, no `://`
  literal, no URL / webhook / auth / key / RPC / PEM needle in source.

## Locked caps (Build 26.0)

- `max_seed = 1`, `max_rechecks = 1`, `max_fake_dispatches = 1` — each locked to exactly 1
  (a single synthetic discovered mint). The orchestrator fails closed
  (`Stage30_14ShadowDispatchError`) on any other value before driving the chain. `max_seed`
  is passed to the committed auto-seeder; `max_rechecks` is passed to the committed bridge
  as `max_summaries`; with one seeded summary the recorded would-send is bounded to one by
  construction.

## Locked safety hardening (mirrors Stage 30.13.4)

- The orchestrator exposes **no** `ledger` and **no** `transport_client` parameter, so a
  replayed candidate can never reach a non-fake dispatch client or a durable ledger through
  accidental caller injection; the committed proof always builds a fresh in-memory ledger +
  a fresh recording FAKE client.
- The injected price / market-context / ATH sources MUST each carry the
  `Stage30_14FakeOnly` marker; a live-capable component is refused before the chain runs.
- The Stage 30.11.16 real-send guard is never imported; the dry-run attestation pins
  `real_send_performed = False` and `real_send_guard_invoked = False`.

## Required proof (asserted by the focused tests)

- exactly one synthetic `*pump` seed accepted (`seed_result.summary.accepted == 1`);
- deterministic fixture recheck/enrichment;
- a fake dispatch decision recorded (`report.dispatched == 1`,
  `would_send_recorded == 1`);
- the dispatched mint traces to the synthetic discovered mint
  (`trace.mint_traces_through is True`; `trace.discovered_mint == trace.dispatched_mint`);
- `real_send_performed == False`; `real_send_guard_invoked == False`;
- `ledger_kind` is the in-memory ledger; `transport_client_kind` is the recording fake
  client;
- no durable ledger path/import/reference; no Discord/webhook/send/approval/arm surface; no
  Stage 28 / gRPC / Yellowstone surface;
- redaction clean (`report.redaction_status == REDACTED`; `trace.redaction_status ==
  REDACTED`).

## Non-goals (NOT built in Stage 30.14)

- No real capture / socket / RPC; no real Discord; no live send; no approval token; no arm
  flip; no durable `ping_dedupe` ledger access; no wallet / signing / trading; no public /
  subscriber routing; no Stage 28 / gRPC / Yellowstone; no `PHX2/main.py` live-flag edit;
  no edit of any committed Stage 27 / 28 / 29 / 30.11 / 30.13 production file; no copying of
  out-of-repo Build #25 artifacts or Phase 1C fixtures into the repo; no tag; no push.

## Handoff (Build 26.1 — deferred and blocked)

Pointing the committed Stage 30.14.0 replay source at a **real, evidence-bearing artifact**
(so the dispatched mint traces to the real Build #25 `A2R6…pump` discovery) is a SEPARATE,
explicitly **operator-authorized** step. It is **blocked** until an evidence-preserving
capture persists a redaction-safe sanitized COMPLETE summary (`token_mint` +
`migration_event_time_utc` + `source_ref` in the allowlisted `helius:sig:<sig>:slot:<n>`
form + `warnings=()` + `COMPLETE` + `SAFE`) — Build #25 v1 did not. Build 26.0 fabricates
none of those fields; it replays only what a caller injects. No real evidence is copied into
the repo.
