# PHX2 Stage 27 Handoff — PHX1-parity private live tradeable ping runner

## 1. Stage 27 mission

**Stage 27 is the PHX1-parity private live tradeable ping runner.**

Stage 27 is the **first PHX2 stage** where the operator should
receive **real private Discord pings for manual trading**. Stage 27
moves PHX2 from the deterministic offline / observe-only posture
that Stage 25 (measurement) and Stage 26 (calibration / candidate-
policy evidence) carry into a bounded, operator-controlled live
runner that surfaces tradeable migration / ATH events to a private
Discord channel the operator alone watches.

Stage 27 explicitly:

- ingests live migration / event evidence,
- reads live price / ATH data through a provider API,
- renders private Discord pings the operator can act on manually,
- deduplicates events so the operator does not get repeated pings
  for the same token / migration / window,
- runs as a bounded continuous runner (not a one-shot CLI),
- ships an operator start / stop / verify runbook.

Stage 27 carries forward, observe-only, the Stage 23 / Stage 24
filter labels and the Stage 25 measurement-aware ATH / migration
context. Stage 27 does NOT relax any Stage 25 truth invariant and
does NOT relax any Stage 26 safety lock; an approved Stage 26
policy candidate is the only thing that could ever flip a Stage 27
ping from observe-only into a gated path, and that approval surface
is reserved for Stage 29 (see Section 7 below).

## 2. Stage 27 is NOT X / social

**Stage 27 is not the X / social stage.** Stage 27 ships zero X /
social ingestion, zero tweet / social-token joins, zero social
ranking / boost / context labels, and zero social-tier dispatch
code. X / social is intentionally deferred to **Stage 30+**, AFTER
PHX2 is producing tradeable private Discord pings end-to-end.

Stage 27 is not Stage 28 (live runner hardening), not Stage 29
(approved enforcement / live gating), and not Stage 30+ (X /
social sidecar). Each later stage is its own explicitly-authorized
implementation pass.

## 3. Stage 27 required surfaces

Stage 27 must include the following surfaces. Each surface is
listed with its scope and the explicit Stage 27 honesty boundary
the surface must respect. Surface implementation lands during the
Stage 27 implementation cycle; this handoff document only locks
the charter.

### 3.1 Local API key / `.env` setup

- A documented local `.env` (or equivalent) loading path so the
  operator can provide live API keys (provider / price-API / private
  Discord webhook) on the local machine. Keys NEVER ship in the
  repository. The runner refuses to start if a required key is
  missing.
- The runbook documents the minimal set of keys, how to verify
  each key, and how to rotate each key. The runner logs the
  presence (not the value) of each key at startup.

### 3.2 Helius / gRPC or provider ingest

- A configured Helius or equivalent gRPC provider connection (or
  the operator's locked equivalent) feeds the migration / event
  stream into the alert candidate path. The provider choice is
  pinned in the Stage 27 configuration; runtime is single-provider
  per session.
- The ingest layer surfaces dropped-message / reconnect telemetry
  to the runner; persistent drops must be visible to the operator
  via the runbook's verify command.

### 3.3 Birdeye / API price + ATH read path

- A price + ATH read path against Birdeye (or the operator's
  locked equivalent live price API) supplies the current-price and
  rolling ATH context each candidate ping needs.
- Price / ATH reads are rate-limit-aware and back-off-aware; the
  runner pauses (not crashes) on a provider rate limit. Cached
  reads are version-stamped and short-TTL so a stale price never
  reaches a ping.
- Price / ATH reads are not Stage 25 measurement evidence; they
  are live operational context for the ping. Stage 25 evidence
  remains the authoritative measurement record.

### 3.4 Migration / event intake connected to the alert-candidate path

- Migration / event evidence from the ingest layer is joined to
  the alert-candidate path so each candidate ping records the
  upstream migration / event identifiers verbatim.
- The intake path does NOT mutate Stage 25 measurement truth and
  does NOT fabricate migration / ATH values. Live evidence
  augments operational context; honesty about missing / ambiguous
  evidence is preserved (the ping carries the live token's
  measurement status when it is available, and an explicit
  "unmeasured" tag when it is not).

### 3.5 Private Discord ping renderer

- A renderer that turns each candidate event into a single private
  Discord message the operator alone sees. The renderer ships its
  own redaction sweep so secrets / API keys / webhook hosts cannot
  leak into a rendered ping payload.
- The renderer routes ONLY to the private operator-owned channel.
  No public / subscriber / paid-tier routing ships in Stage 27.
- The renderer carries Stage 23 / Stage 24 filter labels and the
  Stage 25 measurement-aware ATH / migration context as observe-
  only annotations on the ping body.

### 3.6 Dedupe

- A deterministic dedupe layer prevents the operator from
  receiving repeated pings for the same logical event (same
  migration signature, same ATH window, same token). The dedupe
  window is bounded and operator-tunable; the runbook documents
  the default.
- Dedupe state is local-only; it never ships off-host.

### 3.7 Bounded continuous runner mode

- A bounded continuous runner mode the operator can start, stop,
  and inspect. The runner is bounded by an explicit per-session
  wall-clock or event-count cap so a runaway loop cannot ping the
  operator indefinitely.
- The runner exposes a health / heartbeat surface the operator
  runbook can query without restarting the loop.

### 3.8 Operator start / stop / verify runbook

- A `STAGE_27_RUNBOOK.md` (or equivalent) that documents:
    1. how the operator starts the runner with a chosen provider /
       channel configuration;
    2. how the operator verifies the runner is alive and ingesting
       events;
    3. how the operator stops the runner cleanly;
    4. how the operator inspects the dedupe state and recent ping
       inventory;
    5. how the operator rotates API keys and restarts the runner.

## 4. Stage 27 observe-only inheritance from earlier stages

### 4.1 Stage 23 / Stage 24 filters as observe-only labels / context

- The Stage 23 filter labels and the Stage 24 fee / execution-fee
  context are carried into Stage 27 as **observe-only annotations
  on each ping**. They influence operator visibility, not gating.
- Stage 27 does NOT reopen the confirmed Axiom / global-fee /
  execution-fee decoder. Stage 24 closed that work; Stage 27
  consumes only the Stage 24 outputs that Stage 25 already pinned
  by `basename` + `sha256`.

### 4.2 Stage 25 measurement-aware ATH / migration context

- Every ping carries the relevant Stage 25 measurement-status
  tokens verbatim (`MEASURED` / `PARTIAL` / `SOURCE_CONFLICT` /
  `AMBIGUOUS` / `MISSING` / `UNSUPPORTED` / `REJECTED` /
  `NOT_APPLICABLE`).
- Stage 27 NEVER upgrades `PARTIAL`, `SOURCE_CONFLICT`,
  `AMBIGUOUS`, `MISSING`, `UNSUPPORTED`, or `REJECTED` rows into
  `MEASURED`. The ping body distinguishes the truth class so the
  operator can act with the same honesty discipline Stage 25
  enforces.
- Stage 27 NEVER substitutes `0` for a missing price or ATH and
  NEVER substitutes a previous run's value for a missing
  measurement.

## 5. Pump pair-awareness (locked Stage 27 vocabulary)

Stage 27 must label each ping with the following closed-set
vocabulary so the operator can distinguish SOL-pair pings from
USDC-pair pings at a glance, and so the Stage 27 calibration
universe (when Stage 26 calibration is applied to Stage 27 live
data) does not silently merge two pair types into one denominator.

### 5.1 `quote_asset` closed set

- `SOL`
- `USDC`
- `UNKNOWN`

### 5.2 `pair_type` closed set

- `PUMP_SOL`
- `PUMP_USDC`
- `UNKNOWN`

### 5.3 `bonding_curve_version` closed set

- `SOL_LEGACY`
- `USDC_FIXED`
- `UNKNOWN`

### 5.4 USDC observe-only discipline

USDC-pair pings ship **labeled observe-only** until PHX2 has
accumulated enough USDC-pair measurement evidence to support a
separate USDC calibration cohort. Until that bar is met:

- USDC-pair pings carry an explicit `observe_only_pair=True` label
  in the ping body;
- USDC-pair pings are NEVER fed into the SOL-pair calibration
  cohort, even transiently;
- the operator runbook documents how to read a USDC observe-only
  ping (it is informational only — not a tradeable signal).

### 5.5 SOL-pair / USDC-pair universe separation

- The SOL-pair and USDC-pair measurement and calibration universes
  MUST stay separate. A single Stage 27 ping NEVER mixes SOL-pair
  evidence with USDC-pair evidence in the same numerator /
  denominator.
- When Stage 26 calibration is later applied to live Stage 27
  data, the calibration cohorts are partitioned by `pair_type`
  (and, where load-bearing, by `bonding_curve_version`). The
  Stage 26.2 denominator-honesty discipline applies: silently
  merging two pair types into one denominator is a denominator-
  honesty hazard and is forbidden.
- `UNKNOWN` is its own bucket: an `UNKNOWN`-pair ping is never
  silently routed into either the SOL or USDC cohort. The
  operator runbook documents how to triage `UNKNOWN`-pair pings.

## 6. Stage 27 hard prohibitions

These are hard rules. Any Stage 27 surface that violates one of
these is broken; Stage 27 boundary tests (added in the Stage 27
implementation cycle) will fail fast on each:

- No X / social ingestion, no tweet / social ranking / boost
  surface, no social-token joins (deferred to Stage 30+).
- No public / subscriber / paid-tier dispatch, no Discord
  publisher to a non-private channel, no Telegram subscriber
  router (deferred to Stage 30+ at the earliest).
- No reopening of the confirmed Axiom / global-fee / execution-
  fee decoder; Stage 24 remains closed. Stage 27 reads Stage 24
  outputs by `basename` + `sha256` pin only, identically to the
  Stage 25 / Stage 26 discipline.
- No upgrade of any Stage 25 non-`MEASURED` truth class into
  `MEASURED`.
- No fake ATH, no fake migration timestamp, no `0` price / ATH
  sentinel, no `None`-coerced-to-`0`.
- No live policy enforcement, no live gating decision, no live
  block / allow decision. Stage 27 is a ping runner; an approved
  Stage 26 policy candidate is the ONLY path that can promote a
  ping into a gated decision, and that approval surface lands at
  Stage 29.
- No silent merging of SOL-pair and USDC-pair evidence into one
  cohort (see Section 5.5).
- No leaking of API keys, webhook hosts, or RPC URLs into any
  rendered ping, log line, or on-disk artifact (Stage 27 ships
  its own redaction sweep).

## 7. Stage 28 / Stage 29 / Stage 30+ roadmap

The corrected post-Stage-27 roadmap (consistent with the Stage 26.0
spec-lock §11 corrected roadmap):

| Stage | Role |
| --- | --- |
| **Stage 27** | PHX1-parity private live tradeable ping runner (this handoff). |
| **Stage 28** | Private live runner hardening. |
| **Stage 29** | Approved enforcement / live gating (consumes operator-approved Stage 26.6 policies). |
| **Stage 30+** | X / social sidecar (after PHX2 is producing tradeable private pings end-to-end). |

Stage 28 hardens the Stage 27 runner: better backoff, better
provider failover, better dedupe persistence across restarts,
better operator tooling. Stage 28 still ships zero enforcement
and zero X / social.

Stage 29 wires approved Stage 26 policy candidates into the live
runner as **gating decisions**. Stage 29 is the first PHX2 stage
where `operator_approved = True` / `runtime_consumable = True` /
`enforcement_enabled = True` is permitted on a record, and ONLY on
records the operator has explicitly approved through an out-of-
band approval surface. Stage 26 review packets remain the input
material; Stage 29 wires the approval result into the live runner.

Stage 30+ ships the X / social sidecar AFTER Stage 27 and Stage
28 are producing tradeable private pings and Stage 29 has wired
the first approved policies. X / social is informational
augmentation of an existing ping path; it is not the ping path
itself.

## 8. Stage 27 entry preconditions

Stage 27 implementation is BLOCKED until all of the following are
true:

1. The Stage 26.7 closure audit (`STAGE_26_CLOSURE_AUDIT.md` in
   this directory) is committed.
2. The `stage-26-closed` annotated tag exists on the Stage 26
   closure commit (the operator creates the tag, not the
   implementation pass; see `STAGE_26_CLOSURE_AUDIT.md` §12).
3. The operator gives explicit authorization in a later turn to
   begin Stage 27.

Stage 27 implementation MUST NOT start under any of the following
circumstances:

- the `stage-26-closed` tag is absent;
- the operator has not explicitly authorized Stage 27;
- any of the Stage 26.7 closure documents (`STAGE_26_CLOSURE_AUDIT.md`
  / `STAGE_27_HANDOFF.md`) have been removed or materially edited
  without a documented Stage 26.x re-closure.

## 9. Stage 27 implementation discipline

Stage 27 is its own implementation cycle, planned in the same
sub-stage style as Stage 25 / Stage 26: contracts first, domain
logic next, runner / writer next, closure audit last. Each
sub-stage is its own commit, planning-turn-first, no autonomous
commit / push / tag.

Stage 27 must NOT be implemented as a single mega-commit. The
substages should mirror the locked PHX2 sub-stage workflow.

Specifically, Stage 27 implementation MUST NOT:

- ship any Stage 27 production code under `PHX2/stage27/` before
  Stage 26.7 is closed and Stage 27 is explicitly authorized;
- ship a runner / CLI / dispatcher / live-router / Discord /
  Telegram / X / social file under `PHX2/stage26/`;
- modify any Stage 25 production module;
- modify any Stage 26 production module beyond the narrowest,
  explicitly-authorized closure amendment;
- create the `stage-26-closed` tag (operator-only);
- create the `stage-27-closed` tag (operator-only, after Stage
  27 is implemented and reviewed);
- push any branch or tag.

## 10. Open questions reserved for the Stage 27 planning turn

The following questions are explicitly reserved for the Stage 27
planning turn and are NOT decided in this handoff document:

- Exact provider choice for the migration / event stream (Helius
  vs equivalent); the handoff requires "Helius / gRPC or provider
  ingest", and the planning turn locks the specific choice.
- Exact provider choice for live price / ATH (Birdeye vs
  equivalent); the handoff requires "Birdeye / API price + ATH
  read path", and the planning turn locks the specific choice.
- Exact dedupe key shape (per-token vs per-migration vs composite)
  and the default dedupe window length.
- Exact bounded-continuous-runner bound (wall-clock vs
  event-count) and the default cap.
- Exact ping rendering schema and whether the schema versions
  with a Stage 27 axis or a Stage 27 + Stage 25 axis.
- Whether USDC-pair pings get a dedicated observe-only channel
  separate from SOL-pair pings, or share one private channel with
  an explicit pair-type label.

The Stage 27 planning turn resolves each of these into a locked
charter document before any Stage 27 production code is written.
