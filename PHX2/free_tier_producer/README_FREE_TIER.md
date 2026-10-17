# PHX2 live free-tier producer + paper trading bridge (out-of-repo)

Bridges **fresh PHX2 live discovery** to the **committed paper engine** on free-tier data:

```
read-only Helius WS discovery (committed Build 26 capture, reused verbatim)
  -> bounded watchlist (Build 30, reused verbatim)
  -> committed cap-1 engine per tick (Build 29, reused verbatim):
       pump gate -> FREE-TIER market resolve (keyless public pools/candles data behind the
       committed Birdeye transport seam) -> pre-reserve liquidity floor -> committed composer
       (dip gate + anchored ATH + market freshness) -> dedupe RESERVE (fresh free-tier ledger)
       -> committed Stage 30.11.16 guard
  -> DEFAULT transport: no-send recorder (WOULD-PING artifacts; sends NOTHING)
  -> growing artifact dir  ->  committed paper engine tails it and actively paper-trades
```

**Safety:** no wallet, no signing, no swaps, no real trading surface anywhere. Private Discord is
**disabled by default** (no-send mode even drops the webhook env var from the process). No
public/subscriber routing. No gRPC. No paid key required (an optional keyed market fallback exists
behind `--allow-birdeye-fallback`, used only if the env has the key). Own fresh dedupe ledger at
`C:\Users\BalaC\phx2_live_free_tier\ping_dedupe.jsonl`; any ledger/out path inside the historical
ceremony/production trees is **refused**, so old ledgers can never be touched. No secret is ever
printed (PRESENT/MISSING only).

## Files

- `free_tier_market_transport.py` — free keyless market data (pools lookup + pool candles) behind
  the committed Birdeye transport Protocol; optional keyed fallback; caches + pacing + budgets
  (counts HTTP 429s precisely in `stats()["http_429"]`).
- `free_tier_no_send_transport.py` — the DEFAULT guard transport: records would-pings, sends nothing.
- `free_tier_pricing_tail.py` — bounded market-refresh tail: tracks **every guard-accepted
  watchlist mint** (plus would-pinged mints) so the paper engine keeps receiving price samples
  for the whole tail window (per-mint `--tail-poll-interval-seconds` spend gate); owns the run's
  market-freshness telemetry (fresh/stale/unavailable counts + last refresh + closed-set error).
- `free_tier_polling_discovery.py` — **cheap HTTP polling discovery** (2026-07-10): keyless
  new-pools listing → per new pool ONE bounded `getSignaturesForAddress(pool)` page → IFF the page
  is complete, ONE `getTransaction` of the oldest (=creation) signature → committed Stage 29.5.7
  normalizer extracts the ACTUAL base mint. Durable pool/sig dedupe in `polling_seen.jsonl`.
- `free_tier_credit_budget.py` — cumulative PER-RUN credit/rate budget (the committed capture caps
  are per seed window only): send cap, RAW WS messages, seed windows, polls, candidates,
  getTransaction (shared across WS windows + polling), market requests, 429 tripwire (market +
  polling combined), consecutive-WS-fault tripwire, RPC-error tripwire. Crossing a ceiling ends the
  run at a tick boundary with `stop_reason=BUDGET_<reason>` (exit 0 when every
  ledger/artifact/redaction invariant held). Counters ride every heartbeat + producer_summary.
- `free_tier_risk.py` — **lightweight scam/bundle risk layer (2026-07-11)**: classifies every
  guard-accepted mint RISK_LOW / RISK_MEDIUM / RISK_HIGH / RISK_UNKNOWN from signals the run
  already pays for (LP level/trend, spike-dump / early-drawdown price shape, market staleness +
  refresh failures, polling creation-page signature count). ZERO extra HTTP/RPC/WS spend; NO
  holder/bundler-account scan exists (those signals are always reported UNKNOWN). Labels + reasons
  ride candidate/would-ping/send artifacts, heartbeat + summary (`risk_summary`), the dashboard,
  and a `Risk: <LABEL> — <reasons>` line appended to the outgoing ping body. In explicit
  `DISABLED_SINGLE_STREAM` production, RISK_MEDIUM is warning-only while RISK_HIGH remains a hard
  pre-reservation delivery block. The committed paper engine consumes the labels: default
  strategies refuse RISK_HIGH entries (recorded `SKIPPED_HIGH_RISK` rows), bala gates RISK_MEDIUM
  on LP/MC/freshness, and the
  `HIGH_RISK_OBSERVER` bucket studies the high-risk cohort separately.
- `free_tier_session.py` — CLI: `--selftest` | `--preflight` | `--run` (+ gated
  `--enable-private-discord`), `--profile`, `--discovery-mode`.
- `free_tier_selftest.py` — offline checks (no socket, no send).

## RAW WS cap semantics (2026-07-09 postmortem)

**`ws_notifications_seen` counts RAW logsSubscribe messages on the socket — it is NOT the Helius
dashboard credit meter.** The 2026-07-09 armed run died at exactly 120,000 raw messages after
~10 minutes (3 seed windows × ~40k msgs ≈ 450 raw msgs/s) while the Helius dashboard showed only
~14k/1M credits used across all runs. The cap is a runaway-socket safety bound; size it from the
observed raw rate, never from plan credits. The flag is now
`--max-raw-ws-notifications-total` (`--max-ws-notifications-total` kept as a deprecated alias);
every snapshot carries `raw_ws_notifications_are_not_helius_credits: true`.

## Run profiles (`--profile`; explicit flags always win)

| profile | default mode | runtime | raw WS cap | seed windows | sends | getTx | market req | 429 | rpc errs | polls |
|---|---|---|---|---|---|---|---|---|---|---|
| *(none)* | ws | 7200s | 120,000 (legacy) | 120 | 3 | 1024 | 5,000 | 5 | 12 | 5000 |
| `short_test_10m` | ws | 600s | 200,000 | 6 | 3 | 256 | 2,000 | 5 | 12 | 60 |
| `live_2h` | ws | 7200s | **2,000,000** | 40 | 12 | 1024 | 20,000 | 8 | 24 | 600 |
| `live_4h` | ws | 14400s | **4,000,000** | 80 | 24 | 2048 | 40,000 | 8 | 32 | 1200 |
| `live_2h_low_credit` | **polling** | 7200s | 120,000 | 6 | 12 | 512 | 8,000 | 6 | 24 | 300 |
| `live_2h_hybrid_thin` | hybrid | 7200s | 400,000 | 12 | 12 | 768 | 12,000 | 6 | 24 | 300 |

WS-cap sizing: observed ≈40k raw msgs / 90s window; 2h at reseed 240s ≈ 30 windows ≈ 1.2M
expected → 2.0M cap ≈ 1.6× headroom (4h → 2.4M expected → 4.0M cap).

### Credit optimization (2026-07-10)

The `live_2h` **hybrid** run on 2026-07-10 (`out\live_private_02`) sent 4 real private pings and ran
the full 2h — but the Helius dashboard showed ~14k → ~94k credits, i.e. **~80k credits / 2h ≈ 40k/hr
≈ 960k/day**. That exhausts the 1M free tier in ~1 day and is not viable for 24/7. Attribution:
the run's only high-volume Helius surface was the broad `logsSubscribe` **firehose** (40 WS windows,
**1,552,992 raw WS messages**); the polling RPC surface was tiny (~383 `getSignaturesForAddress` +
353 `getTransaction`) and market HTTP (984) is keyless (not Helius). So the firehose is the dominant
credit driver, and the fix is to **stop opening it**:

- `--profile live_2h_low_credit` (**polling only, no WS firehose**) — the recommended next run. Its
  per-poll bounds (`poll_pools_per_cycle=6`, `poll_sig_page_limit=500`,
  `poll_max_gettransaction_per_cycle=6`) and run caps (`getTx≤512`, `polls≤300`) keep discovery to
  a few surgical RPCs/minute. Expected Helius load ≈ a few hundred–~1k reads / 2h (a >90% cut vs the
  firehose run), so 24/7 fits comfortably inside 1M/mo. Private ping / paper / dashboard / market
  refresh and the strict pump-suffix guard are unchanged.
- `--profile live_2h_hybrid_thin` — mostly polling with a WS window only every 5th reseed on a
  ~400k-msg budget (~4× less firehose than `live_2h`). **This is the Option B yield-vs-credits
  experiment shape (live_private_04)**: polling-only found 1 candidate / 0 pings in 2h
  (571 credits), full hybrid found plenty (4 pings) at ~80k credits/2h — hybrid-thin measures the
  middle. Expected ≈ 15–25k credits / 2h (≤400k raw WS msgs at the observed ~0.05 credits/msg
  + a few hundred polling reads); confirm from the operator-entered before/after credit values.

## Discovery modes (`--discovery-mode ws|polling|hybrid`)

- `ws` — legacy logsSubscribe windows (raw firehose ≈ 450 msgs/s while open). **This is the
  dominant Helius credit driver** — prefer `polling` for sustained runs.
- `polling` — no WS at all: keyless new-pools listing + surgical RPC per NEW pool
  (~2–10 RPC calls/minute total). The pump-suffix guard still runs on the
  **normalizer-extracted mint** — never listing JSON / pool address / log text.
- `hybrid` — polling every reseed + a WS window every `--ws-window-every-n-reseeds`; when the raw
  WS budget runs out the run **downgrades to polling-only** instead of stopping.

Mode resolution: explicit `--discovery-mode` wins, else the profile's default mode
(`live_2h_low_credit` pins `polling`, `live_2h_hybrid_thin` pins `hybrid`), else `ws`. Default
reseed interval is mode-aware: 240s (ws) / 60s (polling) / 120s (hybrid).

## Market refresh (2026-07-09 DATA_LOST postmortem)

Fresh pump mints often list price/MC before the free pairs lookup carries `liquidity.usd`; the
old single offset-0 attempt then failed `REAL_MARKET_INCOMPLETE` → `NO_SEND_MARKET_UNAVAILABLE`.
Now the committed sidecar's bounded escalating refresh retries at +10/+30/+60s after migration
(`--market-refresh-max-delay-seconds`, default 60; 0 restores the old behavior), the watchlist
keeps retrying every recheck tick, and the pricing tail keeps refreshing every accepted mint so
the paper engine no longer starves into `DATA_LOST` when the producer outlives the recheck window.
Stale/missing market context still **fails closed at the committed composer** (no ping).

## P1 scheduler capacity (PHX2-E2E-006, 2026-07-21)

Paid mode carries a structural P1 service contract: **every activated candidate whose fresh
trusted gRPC evidence projects entry into an unsent Tier 1/2/3 band reaches one explicit
result within 15.000 s of that evidence** — alert authorization, a closed-set temporary or
permanent block, a bounded provider-failure/backoff state, or an explicit
`P1_DEADLINE_MISSED` (never a silent pending candidate). The deadline clock starts at the
evidence timestamp, not at any poll loop.

Mechanics: tier-entry transitions open a P1 window and enqueue the overview job
immediately (event-driven; the 45 s recheck interval survives only as the MAXIMUM idle
wait — the watch loop's inter-tick wait is wakeable); provider requests overlap behind a
bounded concurrency gate (default 16) with request-START spacing (default 0.09 s ≈ 11.1
rps) enforced across all workers; pacing, HTTP and retries no longer share one lock, so a
hung mint occupies one slot, never the pool; reserved fast-lane workers
(`--market-p1-reserved-workers`, default 2) keep P0/P1 work dispatchable under any P2/P3
backlog; the provider handoff drains fully in bounded chunks each pass (no more 10-per-tick
quantization); equivalent work single-flights per (mint, generation, purpose) and a newer
generation supersedes stale queued work.

Startup refuses (`P1_CAPACITY_UNACHIEVABLE`, exit 2, before ANY provider/network object)
when the configured spacing/concurrency/budgets cannot serve the 128-candidate active cap
inside the deadline under the exact worst-case formula (`evaluate_p1_capacity`; production
default bound: **13.85 s ≤ 15.0 s**). The spacing default must match the operator's
provisioned paid-plan throughput — a mis-declared tier trips the existing 429
credit-budget stop observably. `--birdeye-min-interval-seconds` remains the explicit
spacing override (the old serialized 1.05 s default could not serve 128 candidates:
133.35 s pacing floor). Zero paid price calls are still required when trusted reserve
evidence is fresh; one logical overview per mint per window.

Observability (heartbeat `market_scheduler` block + producer summary + dashboard):
`scheduler_state` (`SCHEDULER_READY/DEGRADED/CAPACITY_REFUSED/SHUTTING_DOWN/STOPPED`),
capacity proof + bound, per-lane queue depths, open-window count + oldest P1 age,
`p1_enqueued/completed/deadline_met/deadline_missed/temporary_failures/permanent_blocks`
totals, provider logical/physical/timeout/error counts, cache hit/miss, coalesced +
superseded work, and bounded `scheduler_p50/p95/p99/max` seconds.

## Artifacts written to the out dir (default `out\live_01`)

`candidates/<mint8>.jsonl` (per-mint recheck series — the paper engine's main snapshot stream;
carries `risk_label` / `risk_reasons` / `risk_line` per recheck), `would_ping_records.jsonl`
(ping-boundary crossings, risk-tagged), `would_ping_bodies.jsonl` (the exact ping body that WOULD
have been sent, including the warn-only `Risk:` line), `pricing_tail.jsonl` (post-ping price
continuity), `sends.jsonl` (one record per dedupe reserve / would-ping attempt, risk-tagged),
`watch_state.jsonl`, `heartbeat.jsonl` + `producer_heartbeat.json` (both carry `risk_summary`),
`producer_summary.json`, `errors.jsonl`, `redaction_scan.json`. `polling_seen.jsonl` is
producer-internal dedupe state — the paper engine's input scanner now ignores it by default.

## Canonical invocation (READ THIS FIRST)

Every command below runs the **tracked repository module** from the **repository
root** using the **repository virtualenv**:

```powershell
$PY   = "C:\Users\BalaC\Downloads\Phoenix_PHX2\.venv\Scripts\python.exe"
$REPO = "C:\Users\BalaC\Downloads\Phoenix_PHX2"
cd $REPO

& $PY -m PHX2.free_tier_producer.free_tier_session --selftest
```

> **Do not run `free_tier_session.py` as a script from
> `C:\Users\BalaC\phx2_live_free_tier`.** That out-of-repo copy is a stale
> fork that predates the paid gRPC provider, the durable stream cursor and the
> reconnect-recovery contract entirely — it contains none of that code. The
> 2026-07-20 gRPC re-audit found this was the *documented* operator command,
> which is why the cursor work had no production effect at all. The stale copy
> is now a fail-closed shim that refuses to run and prints the command above.

### Durable state vs run artifacts

Two directories, deliberately separate:

| Flag | Holds | Rotate per run? |
|---|---|---|
| `--out-dir` | run artifacts (jsonl, summaries, heartbeats) | **yes** |
| `--cursor-state-dir` | the durable gRPC stream cursor | **never** |

The resume position must survive both a fresh run directory and a process
restart. `--cursor-state-dir` defaults to `--out-dir` only for backwards
compatibility; `--require-production-grpc` refuses that choice outright, along
with an ephemeral/temp location.

### Canonical paid-primary runtime root

`C:\Users\BalaC\phx2_paid_primary_runtime`

```
state\              durable cursor/checkpoint state   (never rotates)
ledger\             canonical paid-primary ping dedupe ledger
runs\<run-id>\      disposable per-run output
operator_logs\      wrapper transcripts, outside every run dir
```

> 2026-07-20: the re-audit found every armed launcher pointing `--out-dir` and
> `--ledger-path` into `phx2_production_private_live` / `phx2_one_send_ceremony`
> — both inside `_FORBIDDEN_WRITE_ROOTS`. The session refused with **exit 2**
> about 795 lines before the gRPC contract was reached, so no operator command
> could execute the repaired path at all. The guard is correct and unchanged;
> the launchers now target the root above. `PHX2.free_tier_producer.
> launcher_contract` holds the canonical paths and an offline validator for the
> whole argument vector, so a launcher can be checked without starting it.

The canonical ledger was seeded byte-for-byte from the active free-tier ledger
for send-history continuity. The frozen one-send ceremony ledger is **never** a
source and never a target.

## Commands

```powershell
$PY   = "C:\Users\BalaC\Downloads\Phoenix_PHX2\.venv\Scripts\python.exe"
$REPO = "C:\Users\BalaC\Downloads\Phoenix_PHX2"
cd $REPO

# offline selftest (no socket / no send)
& $PY -m PHX2.free_tier_producer.free_tier_session --selftest

# preflight (env presence only; NO socket/RPC/GET/send)
& $PY -m PHX2.free_tier_producer.free_tier_session --preflight `
    --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env
```

### A0. Production gRPC shape — REFERENCE (single Yellowstone stream + durable cursor)

> This block documents the **shape**, not the route. It carries no arm-gate flags, so it observes
> and never sends. To actually arm, run one of the three launchers in section D — never a Python
> session file invoked by hand.

```powershell
& $PY -m PHX2.free_tier_producer.free_tier_session --run `
    --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env `
    --provider-mode paid_primary `
    --discovery-mode polling `
    --require-production-grpc `
    --expected-head <THIS-REPO-HEAD> `
    --cursor-state-dir C:\Users\BalaC\phx2_paid_primary_runtime\state `
    --grpc-gap-recovery live_epoch `
    --enable-dexscreener-restart-backfill `
    --ledger-path C:\Users\BalaC\phx2_paid_primary_runtime\ledger\ping_dedupe.jsonl `
    --out-dir C:\Users\BalaC\phx2_paid_primary_runtime\runs\<run-id>
```

`--require-production-grpc` is evaluated in two stages, both **before any
channel, stub or subscription object exists**. It reports every violation at
once rather than one per attempt.

Stage 1 runs on argument values alone, *before* the `paid_mode` branch:

- `--provider-mode` is `paid_primary` or `paid_with_fallback`;
- `--cursor-state-dir` is explicit, stable and not the run dir;
- no legacy websocket discovery and no second discovery owner.

> Previously this lived **inside** the `if paid_mode:` branch it exists to
> require. Since `--provider-mode` defaults to `free_tier`, dropping that one
> token silently produced a send-capable run with no cursor, no contract, an
> open outbound health gate and legacy Helius discovery — no refusal anywhere.

Stage 2 runs once there are objects to inspect:

- `--provider-mode` is `paid_primary` or `paid_with_fallback` (the CLI default
  is `free_tier`, which builds **no cursor**);
- a cursor store was built, is not quarantined, and its subscription identity
  matches;
- `--cursor-state-dir` is stable — not the run dir, not a temp/scratch path;
- the source factory accepts a resume position (no zero-argument fallback);
- no legacy websocket discovery (`--discovery-mode ws|hybrid`) is selected;
- no second discovery owner is configured;
- `--expected-head` matches the repository's actual HEAD.

Production source health is governed by the current durable live epoch. Before
confirmed slot `H` arms `epoch_start_slot = H + 1`, outbound delivery is blocked.
A continuity break closes gap-crossing live candidates, starts a fresh epoch at
the new confirmed boundary, and does not load or execute historical block replay.

### A0.1 Live epoch plus bounded DexScreener restart backfill

**Production status: historical confirmed-RPC block replay is retired.** The
canonical launchers pin `--grpc-gap-recovery live_epoch` and
`--enable-dexscreener-restart-backfill`. Production starts at the current
confirmed boundary, durably arms `H + 1`, runs one bounded best-effort PHX1-style
DexScreener sweep per epoch, and makes no historical completeness claim.

The historical provider-replay/RPC-backfill implementation below is retained
only for explicit offline audit, diagnostics, research, and regression tests.
It is not loaded into active production health, cannot start production recovery
workers, and cannot gate live-epoch Telegram delivery.

**Exact circumstances that permit RPC recovery.** Only a SPECIFICALLY
classified replay-retention refusal may enter the bounded backfill:

- the retention pre-check (`SubscribeReplayInfo.first_available` above the
  safe boundary), or
- provider `OUT_OF_RANGE` against a requested replay.

Authentication failures, `INVALID_ARGUMENT` (malformed request), `NOT_FOUND`,
subscription-identity mismatches, cursor quarantine and every unknown provider
failure remain terminal exactly as certified — they are never converted.

**Commitment model.** The live Yellowstone subscription is `CONFIRMED`. The
backfill's authoritative RPC commitment is explicit
(`--rpc-recovery-commitment confirmed|finalized`, both >= the live stream's
level; `processed` is refused) and the backfill waits until the overlap target
is visible at that commitment before enumerating blocks. Missing or ambiguous
commitment configuration refuses startup.

**Historical offline implementation, in order.**

1. The cursor terminal-locks with its safe boundary preserved (certified,
   unchanged).
2. The owner opens ONE replacement gRPC stream with no `from_slot` — still the
   single Yellowstone owner — but QUARANTINED: its events go to a bounded,
   authenticated buffer, never to the queue/watchlist/scheduler.
3. The first quarantined transaction becomes the overlap target.
4. A provider-neutral Solana JSON-RPC adapter proves every slot from the
   immutable safe boundary through the target as produced-and-processed or
   proven-skipped (`getBlocks` range proof), fetching produced blocks in
   deterministic order and running every relevant transaction through the SAME
   production transaction/migration/reserve/fee decoders as the live path.
5. Progress persists after every completed block (authenticated checkpoint
   `rpc_gap_recovery.json` beside the cursor), so a restart resumes the SAME
   episode — never a fresh live-head session.
6. Recovery is proven ONLY by exact overlap: same slot, same transaction
   signature, same instruction identity, same subscription generation. A
   matching slot alone, a matching height alone, or any manual assertion is
   insufficient by construction.
7. On proof the cursor terminal state is retired ATOMICALLY, buffered
   quarantined events drain once (exact-identity dedupe absorbs the copies the
   backfill already applied), and the stream is promoted to healthy.

**Historical offline health semantics.** When this legacy path is invoked by an
explicit audit/diagnostic command, its terminal and overlap rules remain
fail-closed. These fields are audit-only in live-epoch production.

**Hard bounds.** Every limit is explicit, printed at startup, and validated
fail-closed (invalid values refuse startup; nothing is clamped): gap slots,
produced blocks, transactions, runtime, RPC requests/retries/consecutive
failures/429s, request spacing, concurrency, quarantine events/bytes/age,
commitment wait, overlap wait. Defaults live in
`rpc_gap_recovery.RpcGapRecoveryConfig` and are derived from the measured
production envelope (see the module docstring). Override via the
`--rpc-recovery-*` arguments.

**Terminal reasons** (closed set): `RPC_BACKFILL_GAP_TOO_LARGE`,
`RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED`, `RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED`,
`RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED`, `RPC_BACKFILL_TIMEOUT`,
`RPC_BACKFILL_RATE_LIMITED`, `RPC_BACKFILL_BLOCK_UNAVAILABLE`,
`RPC_BACKFILL_COMMITMENT_TIMEOUT`, `RPC_BACKFILL_FORK_INCONSISTENT`,
`RECOVERY_OVERLAP_NOT_PROVEN`, `RECOVERY_BUFFER_CAPACITY_EXCEEDED` and the
structural refusals in `rpc_gap_recovery.RECOVERY_TERMINAL_REASONS`. **No
limit failure may resume at the live head.**

**Production configuration.** Armed launchers pin `--grpc-gap-recovery
live_epoch` and `--enable-dexscreener-restart-backfill`; they carry no
`--rpc-recovery-*` flags. The active environment is the repository `.env`.
Legacy `provider_replay_only` and `rpc_backfill` controls remain accepted only by
explicit non-production audit/diagnostic commands and preserve the historical
evidence without marking its range complete or overlap-proven.

**Operator terminal-recovery tool** (tracked; drives the same historical
implementation and is not a production launcher):

```powershell
& $PY -m PHX2.free_tier_producer.terminal_recovery_operator inspect `
    --state-dir C:\Users\BalaC\phx2_paid_primary_runtime\state `
    --expected-state-digest <cursor-envelope-digest> `
    --expected-cursor-generation <generation> `
    --expected-subscription-identity-digest <identity-digest>
```

Actions: `inspect`, `export-evidence` (`--export-dir`),
`retry-provider-replay`, `plan-rpc-backfill` (fully offline),
`execute-rpc-backfill`, `resume-rpc-backfill`, `verify-recovery-state`.
Refusals are structural and fail-closed: stale digest/generation/identity, a
state directory owned by a live runtime, a directory that holds a real ping
ledger, non-terminal state, missing episode/target. Live actions additionally
require `--allow-network`, and execute/resume require
`--acknowledge-recovered-candidates-exported` because candidates recovered
outside a live session land in `operator_recovered_candidates.jsonl` for
review, not in the live watchlist. Every mutating action appends to
`operator_audit.jsonl`.

**Deliberately absent** — and refused if requested: `clear-cursor`,
`delete-state`, `skip-gap`, `force-healthy`, `mark-recovery-proven`,
`set-live-head`, `disable-overlap`, `ignore-corruption`. Never delete the
cursor, never hand-edit recovery state, never restart into a fresh state
directory to "fix" a terminal cursor: that silently abandons the unobserved
range the terminal state exists to protect. Only production evidence can
transition state to `RECOVERY_PROVEN`.

**Recovery evidence locations** (all inside the stable state dir):
`grpc_stream_cursor.json` (+`.bak`), `rpc_gap_recovery.json` (+`.bak`),
`rpc_recovery_quarantine.json` (+`.bak`), `operator_audit.jsonl`,
`operator_recovered_candidates.jsonl`; export copies with a SHA-256 manifest
via `export-evidence`.

**After a provider repair** (replay entitlement restored): run
`retry-provider-replay`. If the provider now honours the exact boundary
replay, the redelivered boundary event is the proof and the terminal state is
resolved through the same fail-closed cursor transition; the next production
run then proceeds normally. If it still refuses, the state is unchanged.

**Resuming an interrupted backfill:** the production session resumes the
persisted episode automatically at the next start; operator-driven resumption
is `resume-rpc-backfill` (it refuses if no durable progress exists — use
`execute-rpc-backfill` for a fresh episode, which refuses if progress exists).

**Escalation — required block unavailable:** if a produced block inside the
range stays unavailable past the retry budget (`RPC_BACKFILL_BLOCK_UNAVAILABLE`),
recovery is terminal on this endpoint. Do NOT clear anything. Provision a
different provider-neutral JSON-RPC endpoint with deeper ledger retention in
the env file and `resume-rpc-backfill`; if no provider can serve the block,
the range is unrecoverable and the decision to re-anchor is an explicit
operator decision that must be taken outside this tooling, with the evidence
exported first.

### A. Live free-tier artifact producer only (NO-SEND default)

```powershell
& $PY -m PHX2.free_tier_producer.free_tier_session --run --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env
```

Defaults: out dir `C:\Users\BalaC\phx2_live_free_tier\out\live_01`, 2h max runtime
(`--max-runtime-seconds 7200`; raise for longer sessions), seed window 90s every 240s, recheck
every 45s, would-ping cooldown 300s, liquidity floor $4500. Ctrl+C stops gracefully
(OPERATOR_INTERRUPTED postflight).

### A2. RECOMMENDED next 2h run shape — LOW CREDIT / polling-only (NO-SEND observation; arming is launcher-only, see D)

```powershell
& $PY -m PHX2.free_tier_producer.free_tier_session --run --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env `
    --profile live_2h_low_credit --discovery-mode polling `
    --out-dir C:\Users\BalaC\phx2_live_free_tier\out\live_private_03
```

`--profile live_2h_low_credit` pins **polling** (NO `logsSubscribe` firehose — the ~80k-credit/2h
driver in `live_private_02`) with tighter Helius/market ceilings; `--discovery-mode polling` is
explicit belt-and-suspenders. Expect `raw_ws_notifications_seen ≈ 0` and a >90% Helius-credit cut.
The previous 2.0M-cap hybrid shape (`--profile live_2h --discovery-mode hybrid`) still exists but
is the expensive path — use it only for a deliberate WS comparison.

> **Per-run out dir.** Always give each run its own `--out-dir` (…\out\**live_private_03**), and
> point the paper monitor at THAT subdir (section B), never the parent `…\out`. The 2026-07-10 run
> pointed paper at the parent `…\out`, so it tailed the old `live_private_01` backlog and logged
> **161 input decode errors**. Per-run isolation keeps `input_errors ≈ 0`.

### A3. Option B — 2h HYBRID-THIN yield-vs-credits experiment (live_private_04; NO-SEND observation, see D)

```powershell
& $PY -m PHX2.free_tier_producer.free_tier_session --run --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env `
    --profile live_2h_hybrid_thin `
    --out-dir C:\Users\BalaC\phx2_live_free_tier\out\live_private_04
```

`live_2h_hybrid_thin` pins **hybrid** discovery: cheap polling every reseed (120s) + a short WS
window only every **5th** reseed on a 400k raw-msg budget (vs live_2h's 2.0M); when the WS budget
runs out the run downgrades to polling-only instead of stopping. Record the Helius dashboard
credit value BEFORE and AFTER into `PHX2\dashboard\config.json` (`helius_credits`) so the credit
panel derives burn/hour + credits/ping. Paper monitor: section B with
`--inputs …\out\live_private_04` and `--run-id live_free_tier_private_04`.

### B. Live paper monitor only (committed engine, run from the repo)

```powershell
& $PY -m PHX2.scripts.phx2_live_paper_trade `
    --config C:\Users\BalaC\phx2_paper_trading\paper_config.json `
    --inputs C:\Users\BalaC\phx2_live_free_tier\out\live_private_03 `
    --run-id live_free_tier_private_03
```

**`--inputs` MUST be the producer's per-run out subdir** (…\out\**live_private_03**), matching the
producer `--out-dir` in section A2 — NOT the parent `…\out`. Pointing at the parent makes the
engine tail every sibling run's artifacts (old `live_private_01`/`_02` backlog), which is what
produced the **161 input decode errors** on 2026-07-10. Keep the run-id per-run too
(`live_free_tier_private_03`).

(Engine artifacts land in `C:\Users\BalaC\phx2_paper_trading\live_free_tier_private_03`. Stable
`--run-id` = restart-safe resume. Add `--max-runtime-seconds 120` for a bounded test pass.)

### C. Both together (two terminals)

```powershell
# Terminal 1 — producer (no-send), low-credit polling into a PER-RUN out dir:
$PY = "C:\Users\BalaC\Downloads\Phoenix_PHX2\.venv\Scripts\python.exe"
cd C:\Users\BalaC\Downloads\Phoenix_PHX2
& $PY -m PHX2.free_tier_producer.free_tier_session --run `
    --env C:\Users\BalaC\Downloads\Phoenix_PHX2\.env `
    --profile live_2h_low_credit --discovery-mode polling `
    --out-dir C:\Users\BalaC\phx2_live_free_tier\out\live_private_03

# Terminal 2 — paper monitor tailing THAT per-run subdir (never the parent …\out):
$PY = "C:\Users\BalaC\Downloads\Phoenix_PHX2\.venv\Scripts\python.exe"
& $PY -m PHX2.scripts.phx2_live_paper_trade `
    --config C:\Users\BalaC\phx2_paper_trading\paper_config.json `
    --inputs C:\Users\BalaC\phx2_live_free_tier\out\live_private_03 `
    --run-id live_free_tier_private_03
```

Start order doesn't matter (the engine tails growing files); watch
`C:\Users\BalaC\phx2_paper_trading\live_free_tier_private_03\live_monitor.json` /
`paper_summary.json` for the live book. The producer `--out-dir` and the paper `--inputs` must be
the SAME per-run subdir.

### D. Private operator Discord mode — LAUNCHER-ONLY (there is no inline armed command)

Arming is **not** a flag you bolt onto the observation commands above. There is exactly one
armed route, and it is a deliberate operator act through one of three PowerShell launchers in
`C:\Users\BalaC\phx2_production_private_live`:

| Launcher | Max runtime | Run id (under `runs\`) |
|---|---|---|
| `launch_window_04.ps1` | 30 min | `paid_primary_window_04` |
| `launch_soak_02h_01.ps1` | 2 h | `paid_primary_soak_02h_01` |
| `launch_pressure_24h_01.ps1` | 24 h | `paid_primary_pressure_24h_01` |

Each launcher fetches the locked authorization token into memory (never logged, never written to
a transcript) and executes the tracked module with the **complete** production gRPC contract:
paid-primary provider mode, the production-gRPC requirement flag, a stable `--cursor-state-dir`,
and the canonical paid-primary ledger — all under the runtime root above.
`PHX2.free_tier_producer.launcher_contract.validate_launcher_arguments` evaluates that whole
argument vector offline, so a launcher can be checked without starting it.

> **2026-07-20 (AE-7).** This section previously carried a complete, copy-pasteable armed command
> with no paid-primary provider mode, no production-gRPC flag, no `--cursor-state-dir` and no
> `--ledger-path` — so it defaulted to `free_tier` mode and the **free-tier** ledger. Following it
> armed a run that wrote send history into a different ledger from the one the launchers pin with
> `--require-baseline`, splitting dedupe and baseline history across two files that each believed
> they were authoritative. Sections A2/A3 pointed here ("arm flags per section D"), which made it
> the documented way to arm any run shape in this file.

Two rules follow from that:

- **One writer per ledger.** Never run a free-tier and a paid-primary writer against the same
  ledger, and never point an armed run at the free-tier ledger or at the frozen one-send ceremony
  ledger — the latter is historical and is never a runtime target.
- **Observation is not production.** Free-tier mode builds **no cursor**, so it can never be the
  production gRPC path regardless of what other flags are added to it.

No public/subscriber routing exists; the webhook env var (`PHX2_STAGE21_DISCORD_WEBHOOK_URL`) is
read only on the armed route and is never printed.
