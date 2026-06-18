# Stage 30.13.1 — Seed-Only Fake Proof (RUNBOOK)

Build #24, substage 30.13.1. Committed, OFFLINE, fakes-only, no-send.

## What it proves

Driving the **real** committed Stage 29.5 `Stage29_5HeliusWebSocketAdapter` over an
**injected fake** `Stage29_5WebSocketTransport` (deterministic fixture bytes), the Stage
30.13.0 auto-seeder:

- discovers a bounded migration-evidence batch from the WS adapter;
- accepts a fresh pump-suffix migrated mint with complete evidence and seeds its
  committed Stage 29.5.7 sanitized COMPLETE summary into the watchlist;
- rejects a non-pump mint (`NOT_PUMP_SUFFIX`), a non-PRESENT record
  (`NOT_PRESENT_MIGRATION`), and a PRESENT pump mint with incomplete evidence
  (`INCOMPLETE_EVIDENCE`);
- dedupes a repeat pump mint (`DUPLICATE_MINT`, first-wins);
- fails closed to `WS_CAPTURE_FAILED` when the transport raises / yields a malformed
  payload (the WS adapter raises; the auto-seeder converts it to one `error` outcome and
  never crashes);
- records the `accepted` / `rejected` / `duplicate` / `error` ledger.

It **stops at the seeded watchlist** — it builds no runtime gate, bridge, transport
client, dispatch sink, composer, or ledger. The end-to-end flow through the committed
recheck / fake-send chain is the separate **Stage 30.13.2** proof.

## How to run

```
python -m pytest PHX2/tests/stage30/test_stage_30_13_1_fake_seed_only_proof.py -q
```

(On a machine whose system temp dir is locked, pass a writable
`--basetemp=<dir>`; this proof itself writes no files.)

## Boundary

The transport and clock are **injected**; the proof opens no socket, reads no env, reads
no wall clock, sends no message, touches no durable ledger, and writes no file.

## Non-goals / handoff

No real WebSocket / socket connection, no real Discord, no live send, no recheck /
fake-send (that is 30.13.2), no tag, no push. Wiring a **real read-only** Helius WS
socket transport behind the committed Stage 29.5 `Stage29_5WebSocketTransport` Protocol
is a SEPARATE, explicitly operator-authorized step specified in
`STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md`.
