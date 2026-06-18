# Stage 30.13.3 — Deferred Real Read-Only Helius WS Capture (HANDOFF)

Build #24, substage 30.13.3. **Docs only. Specification of a future step — NOT built and
NOT run in Stage 30.13.** This document hands off the one remaining piece Build #24
deliberately did not build: a **real read-only Helius WebSocket capture** that feeds the
committed Stage 30.13.0 auto-seeder live. It is a SEPARATE, explicitly
**operator-authorized** step.

Stage 30.13.0–30.13.2 are offline and fakes-only: the discovery transport is injected
(`Stage29_5WebSocketTransport`), and the recheck/fake-send is a recording fake. This
handoff specifies how to swap the fake transport for a real read-only socket **without
changing any committed code**.

## How it plugs in (no committed code change)

- The committed Stage 29.5 adapter (`Stage29_5HeliusWebSocketAdapter`) already consumes
  an injected transport behind the `Stage29_5WebSocketTransport` Protocol
  (`recv_one_message(timeout_seconds) -> Optional[bytes]`, `close()`).
- The future wrapper supplies a **concrete read-only socket transport** implementing that
  Protocol and passes it to the committed Build #24 path (the Stage 30.13.0 auto-seeder,
  e.g. via the Stage 30.13.1 seed-only entry). The auto-seeder, models, bridge, and
  recheck chain are reused **verbatim**.
- The real wrapper and the concrete socket transport live **out-of-repo** (operator
  glue), exactly as the Stage 29.5 / 29.5.7 docstrings already defer the real socket.

## Hard constraints (read-only discovery only)

This step is **read-only discovery**. It MUST NOT:

- perform any **send** — no real Discord, no live send, **no send** of any kind;
- present an **approval token** or perform an **arm** / arm flip;
- read or mutate the **durable** one-send **ledger** (`ping_dedupe.jsonl`);
- touch any **wallet / signing / trading** surface;
- use **gRPC** / Yellowstone (this is the Helius WS path, not the Chainstack gRPC path);
- perform any **public / subscriber routing** — existing private operator posture only;
- print, log, or commit the **API key** — the key is read from the environment by the
  out-of-repo wrapper and is **never printed** and **never committed**.

## Bounded + fail-closed

- The capture is **bounded**: the committed adapter caps each scan
  (`max_messages_to_read`, hard cap 1024) and the auto-seeder caps each seed run
  (`max_seed`, hard cap 10).
- It **fails closed on malformed capture / WS errors**: the committed adapter raises a
  closed-set `Stage29_5MigrationEvidenceError`, which the committed Stage 30.13.0
  auto-seeder converts to a `WS_CAPTURE_FAILED` error outcome — it never crashes and
  never seeds on a degraded capture.
- Discovered fresh pump-suffix migrated mints are auto-seeded into the seeded watchlist;
  the **recheck / fake-send** (or, only under separate operator authorization, a real
  send) remains downstream and gated.

## Gating

This step requires explicit **operator authorization** and is out of scope for Stage
30.13. Running a real read-only capture is a discovery action only; any **real send**
remains a further, separately authorized ceremony with its own cap-1 / baseline /
approval discipline (unchanged by Build #24).

## Acceptance (for the future step, when authorized)

- A concrete read-only `Stage29_5WebSocketTransport` is injected; no committed file is
  edited.
- The bounded capture fails closed on WS/transport errors; the four-count ledger
  (`accepted` / `rejected` / `duplicate` / `error`) is recorded.
- No send, no arm, no durable ledger mutation, no API key printed/committed, no gRPC, no
  public routing.
