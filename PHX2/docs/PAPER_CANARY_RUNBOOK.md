# PHX2 bounded paper canary: inactive deployment plan

This runbook is for a later, separately authorized paper canary. The repository
preflight and PowerShell wrapper only inspect local files and print a redacted
plan. They do not source credentials, start either runtime, enable Telegram,
purchase services, update an external launcher, or make provider requests.
Passing offline tests is not evidence of profitable execution or live readiness.

## Reviewable code and plan

Use `PHX2/scripts/phx2_paper_plan.ps1` or
`python -m PHX2.scripts.phx2_paper_preflight`. The wrapper invokes only the
report-only preflight module in the project's `.venv`. There is deliberately no
`--launch`, `--enable-telegram`, or `--enable-paper-telegram` preflight option.

Select an exact producer run directory, a separate paper output root, and a
stable paper run ID. Restart binds to the saved source-root selection. There may
be at most 16 roots, each explicitly selected; rollover is additive only as
described below. A new source may be empty before producer start. The only
accepted streams in each root are its direct `pricing_tail.jsonl` and direct children of
`candidates/` ending in `.jsonl`. Production ingestion admits only
`BUILD30_CANDIDATE_RECHECK` and `FREE_TIER_PRICING_TAIL` records. Do not select the
entire artifacts tree, an old-run parent, `would_ping_records.jsonl`, a glob,
paper outputs, or any PHX1 directory/database. Input roots cannot overlap each
other or the paper output root in either direction. For resume, preflight reads
bounded canonical state and verifies consumed-file metadata plus at most 256
prefix bytes per file. It reports only status/counts, never state or input
contents. The runtime repeats its checks under the paper lease; a report cannot
guarantee files will remain unchanged after preflight.

Across all selected roots, at most **4,096 direct allowed stream files** may be
selected. Preflight uses lazy `os.scandir` enumeration and refuses aggregate
overflow without materializing an unbounded directory listing. The paper poller
additionally limits each poll to **64 files, 4 MiB aggregate input bytes and
1,024 complete records**. Its fair file cursor is checkpointed, and deferred
files/records keep their previous byte offsets. These are aggregate limits, not
per-root allowances; adding roots does not multiply the polling budget.
Every shared `pricing_tail.jsonl` receives a reserved share of half the byte
and record budget on every poll, so historical candidate files cannot delay
open-position quotes. The remaining budget serves candidate files in fair
rotation. Unused tail budget is available to candidates. Tail row size is capped
at its reserved byte share; candidate rows are capped at 2 MiB when tails are
selected, otherwise 4 MiB. A row exceeding its stable cap is refused explicitly.
Rows exceeding only the residual poll budget are deferred. The source never
silently skips a row or advances its checkpoint to make room. Identity checks
also read at most 256 anchor bytes per visited file.

Preflight requires the actual full 40-character HEAD and a reviewed SHA-256 of
the working source tree. Omitting these initially prints the observed values
and a blocked plan. Review the diff before supplying them; copying a freshly
observed digest automatically is not review. The digest covers tracked and
non-ignored new Python/PowerShell source, tests, project metadata and requirement
files; it reflects edits and deletions. It excludes `.env`, credentials, runtime
logs, databases, and user paper configurations. The plan separately includes the
paper model's behavioral configuration digest. Re-run immediately before any
future activation, after every edit or dependency change. A branch name alone
does not pin the code. A valid plan is still inactive and does not grant approval.

All budget decisions must be explicit: 1–3600 seconds, positive market-request
and Helius-byte limits, separate discovery (0–100) and paper (0–20) message limits
(zero means no messages in this plan), tail capacity, and a reviewed private destination
alias if either message budget is positive. These are preflight bounds, not a
service-price estimate or automatic runtime deployment. Never paste a token,
chat ID, authenticated URL, or whole config into the alias.

An offline invocation template (replace placeholders with reviewed local values):

```powershell
.\PHX2\scripts\phx2_paper_plan.ps1 `
  -Config '<paper-config.json>' -SourceRoot '<one-producer-run>' `
  -OutRoot '<paper-output-root>' -RunId '<stable-paper-run-id>' `
  -ReviewedHead '<full-reviewed-HEAD>' -ReviewedSourceSha256 '<reviewed-source-SHA256>' `
  -TailCapacity <reviewed-capacity> -MaxRuntimeSeconds <reviewed-seconds> `
  -MaxMarketRequests <reviewed-request-cap> -HeliusMaxRawBytes <reviewed-byte-cap> `
  -MaxDiscoveryMessages 0 -MaxPaperMessages 0
```

The enabled BALA strategy must have `initials_recovery_multiple=1.35`,
`take_profit_pct=null`, and `runner_trailing_stop_pct=0.30`. A full-position 35%
take profit does not meet this policy. Recovery is net of simulated exit fees,
slippage and impact against the full accumulated entry cost; the runner retains
the fixed 30% trail, including high-quality entries. Other strategies remain
separately configured and are not silently converted to BALA. Sum of enabled
strategy position limits must fit the selected tail capacity; if not, make an
explicit reviewed exposure/capacity decision. Preflight never changes policy to
force entries. Its policy values are intended values plus `policy_matches`; an
unmatched config produces a blocking reason, never a success claim.

The latest non-secret configuration audit reported **six enabled strategies
with a combined worst-case limit of 135 open positions, against 32 tail slots**.
That existing combination is blocked for a bounded canary. Before activation,
choose and review an explicit canary configuration/exposure limit or a capacity
and provider budget that can sustain it. Do not silently change the external
config, disable strategies, increase capacity, or relax eligibility. This
runbook update did not reread or modify the external configuration.

## Separate owners and persistent state

The producer and paper process each have one owner. The existing producer
watchdog does not own paper. Do not start a second producer or attach a second
paper owner to the same run. The paper lease is acquired before engine writes.
Keep a stable paper run ID/output root across restarts so the same ledger,
checkpoints, exposure and durable notification state resume together.

Pair producer `--paper-state-file <paper-run>/paper_state.json` with
`--paper-coverage-required`. Paper publishes atomic `open_mints` and heartbeat
feedback there. Pricing capacity must cover every open paper mint, including
after watchlist expiry or terminal alert state. Stale/missing feedback blocks
new entry coverage; missing/stale quotes must remain unavailable rather than
becoming invented executable prices. A path written in a plan does not prove
that the paired producer is running or honoring that path; inspect its eventual
config echo and heartbeat during the authorized canary.

The future paper-only CLI shape is:

```text
python -m PHX2.scripts.phx2_live_paper_trade
  --config <reviewed-paper-config.json>
  --inputs <one-producer-run> --producer-streams-only
  --run-id <stable-paper-run-id> --out-root <paper-output-root>
  --reviewed-head <full-reviewed-HEAD>
  --reviewed-source-digest <reviewed-source-SHA256>
  --max-runtime-seconds <reviewed-seconds>
  --stop-file <paper-run>/STOP
```

This is wiring documentation, not an instruction to start it now. The paper
process reads producer files and simulates fills; it never launches the producer
or performs wallet transactions. Its default notification mode is a durable
outbox without delivery. Real paper Telegram requires a separate explicit
enable flag and reviewed private destination, credential boundary and message
budget. Its live CLI also requires the reviewed code pins; `--once` is a bounded
offline exception, never an exception for real sends. The final CLI help/config
echo must be reviewed before deployment.

`--once` means **one bounded main poll plus the existing bounded final catch-up
poll (up to two polls)**, not a promise to exhaust the entire backlog. If more
files, bytes or complete records are available than those polls permit, the
remaining work stays deferred for a later pass with the same stable paper state
and source selection. A partial last line also remains unread until complete.
Do not report a one-pass result as full replay coverage without checking the
remaining backlog. Runtime shutdown is cooperative: an in-progress bounded
batch and final catch-up can finish after the requested deadline. Allow for
that settle time when observing the canary; it is not an unlimited drain.

Paper sends require `--enable-paper-telegram`, a positive
`--max-paper-messages` limit no greater than 20,
`--confirm-paper-destination PHX2_PAPER_CANARY`, and
`--paper-destination-sha256` matching the reviewed actual destination. Only the
separate `PHX2_PAPER_TELEGRAM_BOT_TOKEN` and `PHX2_PAPER_TELEGRAM_CHAT_ID` boundary
may supply paper credentials; discovery credentials are not a fallback. These
gates are documented for later review, not supplied to a running command here.
For discovery, **never translate a zero message budget into
`--max-sends-per-run 0`**: that producer value means unlimited. Leave its transport
disabled. The preflight's inert option map always leaves both transports off,
even when proposed positive budgets have been recorded.

For producer rollover, keep the stable paper run and feedback path. The live
CLI requires **`--allow-input-rollover` and `--inputs` retaining ALL old roots
plus the new root**. A changed root list without the flag is refused. The flag
does not permit removing or replacing a root, resetting offsets, or ignoring a
consumed file that is now missing, truncated or replaced. The total root count
is at most 16. A later transition beyond that bound needs a separately reviewed
migration; it must not discard exposure or pretend the old input never existed.

The report-only Python preflight mirrors this with the original `--source-root`,
repeatable `--additional-source-root` arguments for every other retained/new
root, and `--allow-input-rollover`. Keep the remaining reviewed pins, budgets,
config and paper output arguments. The existing PowerShell wrapper remains the
single-root initial/resume convenience path; use the Python preflight directly
for additive rollover. Its inert option map shows the same live rollover flag.

Canonical `paper_state.json` has a **24 MiB commit limit**, below the producer
feedback reader's 32 MiB limit. Exceeding it causes a safe stop before the new
state is committed; do not enlarge the file limit casually, delete canonical
state, or reset history to bypass it. Existing live books with non-empty legacy
ledgers and no canonical state require a reviewed migration or a separately
reviewed new canary run. Starting a new canary is not migration of old open
positions; account for those separately before retiring their owner.

Partial JSONL writes wait for completion; replay must not duplicate fills,
recovery, or final exits. Stop cooperatively, allow final catch-up/state flush,
then verify the lease is released. Open positions stay open for resume. Do not
remove an active lease or uncertain delivery record just to make a restart pass.

Discovery messages and `PAPER` entry/recovery/final-exit messages have separate
event identities and delivery state. A confirmed receipt may be committed once;
an interrupted or ambiguous send remains held for reconciliation rather than
being blindly resent. A producer discovery notification never proves that a
paper fill happened. Do not infer a real exchange fill from either message type.

## Helius and Birdeye requirements from the implemented code

These are source requirements, not current subscription entitlements or purchase
recommendations. No provider was contacted to verify them. Have the parent
verify current official endpoint access, rate limits and billing before buying
or wiring a plan. Credentials must be entered through the private configuration
boundary, never chat or a review bundle.

| Provider capability | Why the pipeline uses it | Request pattern / local controls |
|---|---|---|
| Helius Enhanced WebSocket `transactionSubscribe`, full `jsonParsed`, confirmed, tight `accountRequired` Pump + PumpSwap filter | Structurally proven migration discovery | One live subscription, 30-second keepalive, persistent bounded reconnect backoff. WSS is live-only; reconnect does not replay slots. |
| Helius `getTransactionsForAddress`, full confirmed successful transactions, ascending exact slot range | Repair a recorded stream gap | Default 25 rows/page, at most 5 pages, 125 results, 50 locally modeled credits, 50,000 slots, 16 MiB/attempt, at most 3 recovery attempts/gap. Partial results leave coverage unresolved. |
| Helius standard Solana `getTokenSupply` | Exact-mint authoritative supply for USD market cap | One call/cache miss; default in-memory TTL 3600 seconds. Restarts can cause new cache misses. |
| Helius standard Solana `getMultipleAccounts` | Authenticated fresh-market fallback for one proven pool and its two vaults | One call for those three accounts when eligible market fallback is needed; concurrency bounded to 4 by default, separately attributed in market request tickets. |
| Birdeye `GET /defi/price` on Solana | Current token/USD quotes and one startup credential validation | Price refresh TTL defaults to 12 seconds for active and 30 for pending candidates. Startup validation is one additional request before runtime arming. |
| Birdeye `GET /defi/token_overview` | Market/volume/fee evidence and optional `logoURI` metadata | Overview TTL defaults to 30 seconds active / 90 pending. The logo metadata adds no separate provider call. |
| Birdeye `GET /defi/v3/ohlcv/pair`, 15-second and 1-second intervals, range mode, no padding | Post-migration pair ATH and peak refinement | Initial 900-candle pages (3h45m each at 15s), bounded history paging; later work continues after a durable cursor. Six hours takes two coarse pages before refinement/valuation. |
| Birdeye `GET /defi/v3/ohlcv`, USD series at corresponding timestamps | Validate quote-native pair ATH against same-time token/USD value | Additional bounded valuation requests; unavailable/misaligned evidence pends the candidate. It must not manufacture full-history confidence. |

Source references: `free_tier_producer/helius_source.py`,
`shadow_probes/helius_developer.py`, `helius_gap_recovery.py`,
`authoritative_supply.py`, `authenticated_market_fallback.py`,
`paid_birdeye.py`, and `stage29/birdeye_constants.py`. Legacy
`/defi/ohlcv` remains in compatibility code; verify the V3 pair/token features
for the current producer rather than buying only legacy history access.

For `N_active` active and `N_pending` pending tokens, a useful planning estimate
for regular Birdeye polling before cache hits is
`N_active × (1/12 + 1/30) + N_pending × (1/30 + 1/90)` requests/second.
Thus 32 active tokens alone imply about 3.73 requests/second (224/minute).
This is a workload estimate, not a ceiling: add initial/incremental ATH pages,
refinements, exact-time USD valuation, priority refreshes, bounded retries and
tail lookups not satisfied by cache. Tail attempts are at most approximately
`tracked_mints × ceil(runtime_seconds / tail_interval_seconds)`; the default
tail interval is 60 seconds. One composite tail fetch can require more than one
physical provider request. Request tickets distinguish cache hits from dials.

The production scheduler's default start spacing is 0.09 seconds (about 11.1
starts/second) with 16 concurrent workers and a 15-second P1 deadline. This
does not establish that the account permits those rates. Set smaller explicit
exposure/capacity/throughput values for a bounded canary and re-evaluate the
startup capacity check; never merely stretch a deadline or relax filters to
manufacture an apparent healthy run. `--max-market-requests-total` and
`--max-market-calls-total` must both be finite for the canary; do not reuse the
unbounded managed 24/7 settings. The physical meter also attributes Helius
supply/fallback calls, but a request count is not equivalent to either
provider's billed credits. The startup Birdeye probe is separate. HTTP recovery
and WSS bytes need their own limits. Tick-boundary/response-byte limits can
observe a response already received; allow bounded in-flight headroom when
setting cost limits and review final ticket counts.

The repository's older Helius projection uses 9,156,315 uncompressed bytes over
582 seconds from a July 30 run, about 15.7 kB/second. Treat that as historical
activity evidence, not a current market rate or verified billing conversion.
The byte ceiling is available via `--helius-max-raw-bytes`. Broad historical
enumeration is not required by this pipeline. No Chainstack purchase is implied
by selecting `HELIUS_PRIMARY`; do not enable fallback providers casually.

Code already has isolated credential boundaries named `HELIUS_API_KEY`,
`HELIUS_RPC_URL`, `HELIUS_WS_URL`, `PHX2_STAGE29_2_BIRDEYE_API_KEY`, and
`PHX2_STAGE29_2_BIRDEYE_BASE_URL`; the Birdeye transport uses Solana `x-chain`.
These are variable names, not evidence that configured keys work. The earlier
read-only audit found the external producer launcher selected `HELIUS_PRIMARY`
and still pinned `78bdea6`, while the paper config had the intended BALA recovery
fields. No external config or credentials were reread or changed for this
preflight implementation; repeat a non-secret allowlist check at deployment.

## Remaining live decisions and acceptance evidence

1. Review the final diff, full offline test output, actual-render evidence or its
   explicit blocker, dependency pin and code digest. Confirm deployment version
   and exact source directories. Keep PHX1 completely isolated.
2. Approve finite runtime, Helius byte/recovery budget, physical market requests,
   maximum active candidates/exposure, retry headroom, and separate discovery/
   paper-message budgets. Confirm the exact private Telegram destination through
   the authorized configuration path. Decide whether public logo fetches are
   permitted; banners otherwise use local synthetic assets or text fallback.
3. Local image verification is complete after the explicitly authorized identical
   retry: **Pillow 13.0.0** is installed only in the project `.venv`, all 40
   presentation tests passed and the actual synthetic production banner is a
   1000x200 RGB PNG. The combined offline suite passed 509 tests with no skips.
   Preserve this reviewed dependency version when deploying; installation into
   another environment and real image delivery remain separate actions. All
   seven additional Helius asyncio cases also passed after explicit approval,
   using mocked providers, temporary test files and Windows loopback only;
   zero external connection attempts were observed. The reviewed optional
   image dependency is pinned in `PHX2/delivery/requirements-images.txt`.
4. Explicitly deploy the reviewed code pin and hash manifest to the external
   launcher, preserving its ledger baseline and stable runtime state. This is
   a separate deployment action. Never silently rewrite external configuration.
5. After explicit live authorization, verify one producer and one paper owner,
   exact config echoes, coverage-feedback freshness, bounded budgets and
   credential validity. The producer credential test is itself a provider call.
6. Observe genuine migrations through admission, activation, market evidence,
   coherent as-of snapshots and continued open-position pricing. Test a clean
   stop/restart, no duplicate fills or messages, preserved recovery/runner state,
   explicit stale/missing inputs, and receipt reconciliation. If no eligible
   candidate appears within the cap, report that result and stop.
7. Retain redacted summaries, counters, test outputs and receipts. Do not include
   secrets, full external configs, raw databases or sensitive logs in the review
   bundle. Return the final verified result to the user when work finishes;
   future monitoring is a separate action.
