# Stage 30.13.2 — End-to-End Fake-Send Proof (RUNBOOK)

Build #24, substage 30.13.2. Committed, OFFLINE, fakes-only, no-send.

## What it proves

The **whole** Build #24 path reaches a fake dispatch with no hand-fed input and no real
send:

```
injected fake WS transport + clock
  -> Stage 30.13.1 seed-only proof (real Stage 29.5 Helius WS adapter -> Stage 30.13.0
     auto-seeder) -> seeded sanitized summaries (the watchlist)
  -> Stage 30.11.23 fake real-fed dry-run proof (committed Stage 30.11.23 bridge ->
     committed Stage 30.11.22 dry-run chain over injected Birdeye-style price /
     market-context / ATH fakes + a recording FAKE dispatch client + an in-memory ledger)
  -> a RECORDED would-send (dispatched == 1), NEVER a real send
```

The dispatched mint **traces to the WS-discovered pump-suffix summary** — there is no
`CURATED_MINT` / hand-fed mint anywhere in the path. This is the existing, proven
`30.11.23 -> 30.11.22` recheck/fake-send chain; Build #24 simply auto-produces its input
from bounded WS discovery.

## How to run

```
python -m pytest PHX2/tests/stage30/test_stage_30_13_2_fake_end_to_end_proof.py -q
```

(On a machine whose system temp dir is locked, pass a writable `--basetemp=<dir>`; this
proof itself writes no files — the dedupe ledger is in-memory.)

## Boundary

The transport, clock, and every provider source (price / market-context / ATH) are
**injected**; the dispatch client is a recording **fake** and the ledger is **in-memory**.
The proof opens no socket, reads no env, reads no wall clock, sends no message, calls no
real dispatch, calls no Stage 30.11.16 real-send guard, touches no durable ledger, and
writes no file. The no-real-send attestation flags on the dry-run report are pinned
(`real_send_performed == False`, `real_send_guard_invoked == False`).

## Non-goals / handoff

No real WebSocket / socket connection, no real Discord, no live send, no approval token,
no arm, no durable ledger mutation, no tag, no push. Wiring a **real read-only** Helius
WS socket transport behind the committed Stage 29.5 `Stage29_5WebSocketTransport`
Protocol — and running the controlled capped private send — is a SEPARATE, explicitly
operator-authorized step specified in `STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md`.
