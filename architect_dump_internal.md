# PHX2 Internal Architecture Dump (Private)

> **Private founder/operator document. Trade secrets included.**
> Do not share. Do not paste into Discord, Slack, public gists, or LLM prompts you don't control. Do not give this file to outside mentors — use [architect_dump.md](architect_dump.md) for that. If this file lives in a git working tree, consider gitignoring it or moving it outside the repo before any push.

---

## 1. Executive Summary

PHX2 is a staged rewrite of Phoenix v1: a private Solana memecoin signal / research / private-ping system whose purpose is to detect, measure, and dispatch a specific lifecycle setup around token launches — and to do it as a research environment, not a hacked bot.

The problem PHX2 solves: Phoenix v1 worked but was a tangle. Filters, measurement, and dispatch were braided into the same loop. There was no way to inspect what the system saw at the moment it made a call, no way to evolve one piece without risk of breaking another, no way to build calibration on top of it, and no way for a future agent to read it. The thesis was real; the substrate was opaque.

PHX2 exists because the fix wasn't a better feature — it was a better substrate.

How it differs from Phoenix v1:

- **Layered, not monolithic.** Every concern (ingestion, normalization, measurement, filtering, calibration, candidate assembly, rendering, dispatch, artifacts) is its own layer with explicit contracts.
- **Observe-only before enforcement.** Every new capability lands passive. Gating is a separate, later decision.
- **Pair-aware lanes.** SOL-pair, USDC-pair, and UNKNOWN/DISAGREE are isolated calibration lanes. No more cross-contamination between asset types.
- **Staged, not cowboy.** Sub-stages with focused tests, closure artifacts, and operator-gated closure.
- **Private-only.** No public routing exists yet. Transport is one private Discord channel under operator control.
- **Restart-safe and bounded.** Dispatch ledger survives crashes. Runners have explicit session bounds. Health heartbeats prove liveness.
- **Agent-readable substrate.** Artifacts are designed for a future agent to consume, not just an operator.

Honest summary: PHX2 is a finished pipeline pointed at a synthetic signal. The next sensitive step is pointing it at the real signal.

---

## 2. The Core Alpha Thesis

The trade PHX2 is built to capture lives at a specific point in a Solana memecoin's lifecycle. The thesis breaks into measurable phases:

**a. Launch / migration.** A new token completes its bonding-curve graduation (or venue-specific migration equivalent). This is **clock-zero** for the system — many of the downstream measurements anchor here.

**b. Initial expansion.** Post-migration, the token enters its first run. Volume, holder count, and price move together or they don't. The *shape* of the expansion is the first piece of signal — a clean expansion with broad participation is structurally different from a thin, bundled, or wash-traded one.

**c. ATH formation.** The token prints an all-time high. Measuring this correctly is one of the hardest parts of the system. ATH is not just "max price seen" — it must survive stale data, exchange-specific quirks, brief illiquid wicks, and reorgs. Wrong ATH poisons everything downstream.

**d. Failed reclaim / post-ATH weakness.** After ATH, the token attempts to reclaim. The structure of that attempt — how decisive, how it interacts with the prior expansion's participants, how it behaves into the ATH zone — separates tokens that have more upside from tokens that are done.

**e. Pullback / drawdown tiers.** Drawdown from ATH defines a tier. Different tiers behave differently. Calibration lanes exist partly to keep tiers from contaminating one another.

### Why this creates asymmetric trade opportunities

The setup has a known invalidation point (ATH, or the reclaim failure structure) and an upside that can be multiples of risk if the token is structurally healthy. The edge is not in being right every time — it is in being *honest* about which candidates have the right structure and which don't.

### Why timing matters

The window between "this candidate is showing the setup" and "this candidate has already moved" is short. Late = setup gone. Early = guessing. The measurement clock has to be tight.

### Why measurement matters

Every downstream decision sits on context numbers — drawdown, time since ATH, time since migration, observation windows. A measurement error in any of those is not a small bug; it is a **category-changing** bug. A meaningful ATH error can flip a clean candidate into a noisy one or vice versa. The tier label flips. The policy decision flips. Measurement errors are silent category errors, not noise.

### Sources of poison (why false positives happen)

- **Scams and rugs.** Mint authority, freeze authority, LP pull behavior — turns a clean-looking expansion into a trap.
- **Wash trading.** Concentrated wallets cycling volume produce healthy-looking event pace and fee pace without real participation.
- **Bad liquidity.** Thin pools produce wicks that look like real moves. Thin pools also make any actual trade impossible to size.
- **Bundled launches.** A bundle launched and sniped by the same network looks organic for the first minutes — and isn't.
- **Weak holder quality.** Fresh wallets, funder networks, low diversity — holder distribution must look like real people, not one entity wearing many hats.
- **Bad fee structure.** Creator fee share too high, protocol fee structure misaligned with healthy market behavior, fee paid by suspect wallets — all tells.
- **Bad source quality.** The funding chain into early buyers — if it traces back to a small set of related wallets, the expansion is fake.

The filter layer's job is not to "score" tokens. It is to **label which sources of poison are present** and which aren't.

---

## 3. PHX2's Brain Model

Right now, **you are the brain.** The system is not making trading decisions. You are.

What the system is doing instead is building a **field** around your judgment — a structured environment that converts your intuition into evidence other things can read.

The vocabulary that matters:

- **Field.** The structured environment surrounding the decision. Not the decision itself, but the things the decision is made against: candidate context, lifecycle clock, filter labels, calibration lane, prior outcomes.
- **Score.** Not a single number. A vector of labels and measurements. The system's job is to populate the score honestly, not to collapse it into one decision.
- **Clock.** Time anchored to events that matter (migration, ATH, expansion start), not wall time. The clock is what makes context comparable across candidates.
- **Sequence labeling.** Each candidate is a sequence of states — pre-migration, migration, expansion, ATH, post-ATH, reclaim attempt, drawdown tier. The labels themselves are the data.
- **Structured environment.** The artifact substrate. Manifests, review packets, calibration outputs, dispatch ledgers.
- **Source of truth.** You, today. Artifacts in the future.
- **Operator review.** The manual loop where you read the structured outputs and decide whether the policy layer is reading the field correctly.
- **Observe-only before enforcement.** The rule. Every new measurement, filter, or policy candidate lands passive first. Gating is a separate, later decision.

The trajectory is:

```
human intuition
   ↓
structured measurements
   ↓
labeled candidates
   ↓
operator review packets
   ↓
calibrated policies
   ↓
approved enforcement
   ↓
agent-readable environment
```

You are at "structured measurements → labeled candidates → operator review packets" right now. The next step (Stage 29) is the first piece of "approved enforcement" — and it is enforcement only of the dispatch decision (this candidate qualifies as a private ping), **not** of any trade decision.

The long-term goal is not a better alert bot. It is an environment an agent can read. The alerts are a useful operator surface along the way.

---

## 4. Full System Layer Breakdown

### A. Provider / Ingestion Layer

The boundary between the outside world and PHX2. The provider adapter is the only place the system speaks any external wire format.

Inside the adapter:
- gRPC / API / log subscriptions / raw event intake.
- Backoff, retry, rate-limit awareness, connection lifecycle.
- Provider-specific event shapes translated into typed events.
- Malformed events logged and counted, not silently dropped — malformed event rates are themselves a signal about provider health.

**Why provider adapters must stay replaceable.** Providers change pricing, deprecate endpoints, change schemas, and occasionally go down. The system must be able to swap a provider with no changes above this layer. Provider identity must not leak upward.

**Why raw capture matters.** For high-value candidate windows, the raw provider events should be preserved alongside the normalized version. Two reasons: (1) replay — if a measurement bug is found later, the only way to evaluate the fix is against the real raw stream that produced the original candidate; (2) provider divergence — if two providers disagree, you can only reconstruct what happened by holding the raw.

**Failure handling.** Provider downtime cannot crash the pipeline. The system must continue, must report degraded mode, and must **not** silently mark candidates as clean when input data was incomplete.

### B. Normalization Layer

Provider-specific raw events become Phoenix-owned event contracts. Stable, versioned schemas. Every downstream layer reads these, never the raw.

Rules:
- Normalization is dumb. No measurement, no scoring, no decisions. Pure shape translation plus a tiny amount of provider-quality metadata (canonical source vs fallback).
- Schemas are versioned. A schema change is not a free action; it requires an explicit sub-stage and migration of consumers.
- Replay works against normalized events, not raw. (Raw is for forensics; normalized is for the pipeline.)

**Why this is non-negotiable for the agent goal.** An agent reading the artifact layer needs stable types. If schemas are unstable, the agent breaks on every internal change. The normalization layer is what makes the agent's contract stable.

### C. Pair / Quote Asset Awareness

Solana memecoins trade against multiple quote assets — predominantly SOL, sometimes USDC, occasionally other configurations. PHX2 treats these as **separate calibration lanes**, not a single market.

Lanes:
- **SOL-pair.** The primary lane. Most candidates, most calibration data.
- **USDC-pair.** Real but rarer. Behaves differently because the quote asset itself doesn't move. **Observe-only** until enough data exists to calibrate this lane on its own.
- **UNKNOWN.** A candidate where the system could not confidently determine the quote asset. **Suppressed from live trust.** Logged, observed, but no ping.
- **DISAGREE.** Multiple signals about the quote asset disagree. Same treatment as UNKNOWN.

**Why pair type matters.** SOL-pair candidates have prices in SOL. SOL itself moves. A drawdown measured in SOL is a different drawdown than one in USD. The calibration of "how much pullback is healthy" is not transferable between lanes. Mixing them is the fastest way to overfit a policy to a market regime.

**Why UNKNOWN/DISAGREE suppress.** If the system can't agree with itself about what the candidate is denominated in, anything downstream is suspect. Better to silently drop than ping with the wrong context.

**Why USDC stays observe-only.** Not enough data yet. The lane needs its own calibration before its candidates get live trust. Deliberate restraint, not a limitation.

### D. Measurement / Context Layer

Most of the proprietary work lives here. Most of the risk hides here.

Every candidate gets a context object with:
- **Migration context.** When did the token graduate? Immediate post-migration conditions?
- **Price context.** Current price, observation window, recent extremes, comparison points.
- **ATH context.** All-time high, when it printed, how durable it was. The hardest field in the system.
- **Drawdown.** Current drawdown from ATH, with tier classification.
- **Time since ATH / time since migration.** The two main clock readings.
- **Price observation windows.** Multiple windows so the system can reason about both micro and macro structure.
- **Candidate context.** The aggregate object downstream layers actually consume.

**Why ATH measurement is the hardest.** ATH is supposed to be a single number, but it isn't. Sources disagree on it. Brief illiquid wicks can push it up. Reorgs can change it after the fact. Stale price data can hide it. A wrong ATH means every downstream drawdown is wrong, which means every tier label is wrong, which means every policy decision is wrong. The system has to be **conservative** about ATH — better to under-report than to over-report.

**How measurement errors destroy alert quality.** A modest ATH error can flip a candidate's tier label. The tier label drives the policy decision. The candidate either gets a ping it shouldn't or doesn't get one it should. Measurement errors are not noise; they are silent category errors.

This is also the layer where backfilling and replay get hard, because measurements depend on observation windows that move with time. Every measurement function has to be deterministic given a fixed observation window — never depend on "now."

### E. Filter / Quality Layer

The filter layer attaches **quality labels** to candidates. Categorical, named internally. The label set covers the sources of poison from §2:

- **Fee behavior.** Is the fee structure consistent with a real market, or gamed?
- **Creator / LP / protocol fee shares.** Where is the value going? Pathological distribution = tell.
- **Event pace.** Is transaction frequency consistent with broad participation, or concentrated bursts?
- **Fee pace.** Are fees accumulating in a shape that matches event pace, or is one decoupled from the other?
- **Buy / sell behavior.** Is the buy/sell ratio plausible, or does it tell a story of one entity moving both sides?
- **Liquidity quality.** Pool depth, slippage profile, durability under simulated trade size.
- **Holder concentration.** Top-N holder share. Holder count growth shape.
- **Wallet / source quality.** Funding chains into early buyers. Wallet age. Behavioral fingerprints.
- **Bundle / funding / source signals.** Was this a bundled launch? Did sniper networks dominate the open?
- **Execution / priority fee / Jito / global fee primitives** (later). Whether the candidate's execution environment looks like a real market or a captured one.

**Why some filters are observe-only first.** A filter that has never been seen on real candidates may not behave the way the design predicts. Until the filter has run silent for long enough to know its false-positive and false-negative profile, it does not get to influence the candidate label that drives a ping. Observe-only is how new filters earn trust.

**Sticky vs stateless labels.** Some labels should stick once set — if a candidate ever showed bundle activity, that's not unset by later normal activity. Others should be stateless — recomputed every event because the underlying condition can resolve. The system has to be deliberate about which is which. A sticky label set wrongly is hard to unset. A stateless label that should have been sticky lets a poisoned candidate look clean later.

### F. Calibration / Policy Layer

The loop that converts measurements and labels into the rules the system follows.

- **Outcome windows.** For each candidate, the system records what happened in defined windows after the candidate was seen — price movement, drawdown trajectory, time-to-X.
- **Cohorts.** Candidates grouped by lane, tier, label set. Cohort behavior is what threshold candidates are evaluated against.
- **Threshold candidates.** Proposed parameter changes. Not applied immediately.
- **Policy candidates.** Proposed rule changes — when a candidate qualifies as a ping, when a label suppresses, when a lane becomes live.
- **Operator review packets.** Structured artifacts you read to decide whether a threshold or policy candidate should be promoted.
- **Approval handoffs.** Promotion to live policy requires explicit operator approval, recorded.

**Why Stage 26 artifacts are review-only.** Deliberately not auto-applied. The system can propose; only the operator promotes.

**Why enforcement is delayed.** Two reasons. (1) Enforcement on top of insufficient data is overfitting by another name. (2) Enforcement before the operator has internalized what the policy will do produces operator distrust later. Better to wait until you could predict the policy's output yourself.

**How the system avoids overfitting:**
- Cohorts must be large enough.
- Outcome windows are fixed, not chosen to flatter a result.
- Calibration based on real outcomes, not retrospective re-labeling.
- A policy candidate that performs well in-sample but only marginally out-of-sample does not promote.

**Why calibration must be based on real outcomes.** Synthetic tests prove the pipeline works. They do not prove the thesis works. Only real candidate streams over real time produce calibration data worth anything.

### G. Candidate Assembly Layer

Where a live provider-backed event becomes a candidate — the object the rendering and dispatch layers actually see.

A candidate is the conjunction of:
- Lifecycle phase (where in §2's sequence is this token?)
- Pair lane (SOL / USDC / UNKNOWN / DISAGREE)
- Measurement / context (the §D object)
- Filters (the §E label set)
- Policy artifacts (the §F lane- and label-aware rules)

**Observable vs tradeable.** A candidate is **observable** if measurement and labels are populated. It is **tradeable** if:
- Pair lane is SOL (USDC and UNKNOWN/DISAGREE are observe-only).
- Lifecycle phase matches the targeted setup.
- Label set does not include any disqualifying poison labels.
- Policy layer's current rules promote this combination to a ping.
- Measurement quality is high enough (no stale data, no provider degradation, no ATH ambiguity).

**What must be present before a ping is trusted.** Provenance: the candidate's full input lineage must be reconstructible from the artifact layer. If you can't trace it, you can't trust it.

### H. Private Ping / Rendering Layer

Rendering turns a candidate into a private operator ping. Separate from candidate logic on purpose — the same candidate may eventually feed multiple consumers (Discord, log archive, agent feed), and only the rendering layer should know each consumer's shape.

What appears in the private Discord ping:
- Token identity (operator-useful form).
- Lifecycle phase and tier label.
- A short summary of the candidate context — enough to act, not enough to reverse-engineer the recipe.
- Provenance pointer — the artifact ID you can read for the full picture.

What never leaks into a ping:
- Exact thresholds.
- Exact filter recipes.
- Exact measurement formulas.
- Anything that would let a reader reconstruct the policy from a small number of pings.

**Redaction is enforced at this layer**, not at the call site. Upstream layers can carry whatever fields they need. The rendering layer is the gate. If you ever find a leak, the fix lives here.

**Why rendering is separate from candidate logic.** Candidate logic is about *whether* this is the right thing to surface. Rendering is about *how*. Coupling the two means a change in the operator surface forces a change in the candidate logic and vice versa — and historically that's how Phoenix v1 became unevolvable.

### I. Dispatch / Reliability Layer

Stage 28's home. Everything about getting a ping out of the system without lying about it.

- **Private Discord transport.** One private operator channel. Abstracted behind an interface — swappable.
- **Restart-safe dispatch ledger.** Every dispatched ping is recorded before the network call resolves, so a crash mid-call does not produce a duplicate on restart, and a successful call does not get re-attempted.
- **Dedupe.** Within a window, the same lifecycle event does not produce repeat pings. Dedupe keys are explicit and stable.
- **Retries.** Transport failures retried with backoff. Permanent failures surfaced.
- **Failure classification.** Transport errors, ledger errors, redaction errors, and dispatch-policy errors are distinct categories.
- **Audited HTTP transport.** The outbound HTTP path is wrapped so every request and response is recorded.
- **Health snapshots.** Periodic state snapshots of dispatch internals.
- **Heartbeat / status artifacts.** Liveness signals you can read without inspecting the transport.
- **Bounded private session runner.** Long-running execution has explicit session limits. The system never silently drifts beyond a session bound.
- **Graceful shutdown.** Mid-flight dispatches complete or are recorded as pending; the ledger is consistent on exit.

**Why Stage 28 matters before relying on live pings.** Until dispatch reliability is hardened, you can't tell whether a missing ping means "candidate wasn't ping-worthy" or "transport ate it." If you can't tell which, the entire signal is unreadable. Stage 28 makes that distinction observable.

### J. Artifact / Audit Layer

The bottom of the stack and the top of the agent-readability story.

- **Manifests.** Every stage produces a manifest of what it produced and why.
- **Deterministic outputs.** Given the same inputs, the same outputs. No random ordering, no time-dependent salt.
- **Provenance records.** Every artifact carries lineage — what stage, what code state, what inputs.
- **Test gates.** Sub-stages do not close until focused tests pass.
- **Closure audits.** Every sub-stage closure produces an audit artifact the next sub-stage can read.
- **Stage handoffs.** Stage N's closure includes the explicit handoff document Stage N+1 needs.

**Why PHX2 is built like a research lab, not a hacked bot.** A bot's job is to fire. A lab's job is to produce reproducible evidence. PHX2 has to be the latter for the agent goal to be possible. Every artifact has to be something an external reader could pick up cold and understand.

---

## 5. Stage-by-Stage Timeline

### Stage 21 — Live path foundation
- **Added.** First real live-path plumbing — provider intake, candidate scaffolding, private ping primitives.
- **Why.** Phoenix v1's live path was tangled. This is the first layer-separated version.
- **Did not.** Reliability hardening. Real measurement hardening. Synthetic-only.
- **Risk reduced.** "Live path" stopped being a vague monolith.

### Stage 22 — Live ingestion hardening
- **Added.** Raw capture, bounded runner, provider failure handling.
- **Why.** Without raw capture, replay is impossible. Without a bounded runner, long-running execution drifts.
- **Did not.** Filter behavior on real data.
- **Risk reduced.** Provider misbehavior can no longer silently corrupt the candidate stream.

### Stage 23 — On-chain filters observe-only
- **Added.** First quality filters as passive labelers.
- **Why.** Filters had to run silent against real data before being trusted to influence pings.
- **Did not.** Enforcement. Filters could not gate.
- **Risk reduced.** Filter behavior could be evaluated against real candidate streams without consequence.

### Stage 24 — Execution fee primitives
- **Added.** Fee decomposition — creator share, LP share, protocol share, execution-fee primitives.
- **Why.** Fee shape is one of the strongest poison signals. Without primitives, no fee-based filter is possible.
- **Did not.** Use of these primitives in live policy.
- **Risk reduced.** The fee filter family stops being a future thing and becomes an inputs-ready thing.

### Stage 25 — ATH / migration measurement hardening
- **Added.** Real hardening for the two hardest fields.
- **Why.** Wrong ATH = wrong everything. Wrong migration anchor = wrong clock.
- **Did not.** New policy on top yet — measurement first, policy later.
- **Risk reduced.** Silent measurement errors stop being the dominant source of candidate noise.

### Stage 26 — Calibration / policy candidates / operator review packets
- **Added.** The calibration loop. Outcome windows, cohorts, threshold candidates, policy candidates, operator review packets, approval handoffs.
- **Why.** This is what makes PHX2 not-Phoenix-v1. The thesis can now evolve through structured review, not vibes.
- **Did not.** Enforce any candidate policies. Review-only.
- **Risk reduced.** Calibration is no longer ad-hoc.

### Stage 27 — PHX1-parity private live tradeable ping runner
- **Added.** Pair awareness, provider composition, private ping renderer, controlled private Discord smoke. End-to-end private-ping path on a controlled channel.
- **Why.** First time the full pipeline produced a real outbound private ping. Pair awareness arrived here.
- **Did not.** Enable enforcement based on calibration. Connect real provider-backed candidates.
- **Risk reduced.** Rendering and dispatch stops being theoretical.

### Stage 28 — Private live runner reliability hardening
- **Added (across 28.0–28.8).** Audited private Discord transport, health heartbeat & status artifacts, bounded private session runner, longer session smoke harness, closure audit and Stage 29 handoff.
- **Why.** Until reliability is hardened, every missing ping is ambiguous and every duplicate is a credibility hit. Stage 28 makes the dispatch layer trustworthy as a signal channel.
- **Did not.** Wire real provider-backed tradeable candidates. The transport is hardened; the upstream is still synthetic/smoke.
- **Risk reduced.** Transport reliability is no longer the bottleneck.

### Stage 29 — Approved enforcement wiring / live gating candidate policies
- **Will add.** First real provider-backed candidate intake into the private ping path. Policy enforcement on the dispatch decision (not the trade). Pair-aware lane respect at runtime. Suppression of UNKNOWN/DISAGREE. USDC stays observe-only.
- **Why.** First time the system points at the actual signal. From this point on, the artifacts are research output, not infrastructure output.
- **Will not.** Introduce public routing, automated trading, wallet logic, or social signals.
- **Risk reduced.** The gap between "pipeline works" and "pipeline finds the signal" closes.

### Stage 30+ — X / social sidecar
- **Will add.** Social-event adapters as a sidecar. Social signals as context augmentation, never as core brain. Replaceable social providers.
- **Why.** Social can boost confidence in a candidate already qualified on-chain. Social must never qualify a candidate by itself.
- **Will not.** Put social in the candidate-qualification path.

---

## 6. Current State of PHX2

Blunt:

- **Stage 28.8 is closed.** Stages 21–28 are all closed and tagged locally on master. Nothing is pushed to a remote.
- **Private Discord smoke succeeded.** The end-to-end private-ping path has been exercised on a controlled channel under your control.
- **Reliability hardening is in place.** Audited transport, health heartbeats, bounded runner, longer-session smoke harness — done.
- **Synthetic and controlled smoke tests have proven the transport path.** What this proves: the pipeline can render and dispatch a candidate object without crashing, dropping, or duplicating.
- **What this does NOT prove:** that the system can find the real signal in the real candidate stream. The candidate objects in smoke tests are constructed, not detected.
- **The missing piece is real provider-backed candidate wiring.** Provider adapter → normalization → measurement → filter → candidate assembly → render → dispatch, with a real candidate as input. That has not happened yet.
- **You do not yet have continuous real tradeable Discord pings.** Anything live so far has been smoke. This is the bottleneck.
- **The next important milestone is controlled real candidate smoke, not more synthetic test pings.** More synthetic pings teach you nothing new. The next thing to learn is whether the real candidate stream survives the pipeline.

State of the world: pipeline finished, dispatcher hardened, signal not yet pointed at the real source.

---

## 7. The Exact Next Milestone

Stage 29. Concretely:

- **Wire real provider-backed candidate intake.** The provider adapter must produce a real candidate object, end-to-end, from a real event.
- **Preserve pair awareness.** Lane attribution must survive the wiring. A SOL-pair candidate must arrive labeled SOL.
- **Preserve suppression for UNKNOWN / DISAGREE.** Real candidates the system can't agree about must not ping.
- **Preserve observe-only USDC.** USDC candidates can flow through measurement and rendering, but they do not dispatch.
- **Connect candidate context to the private ping renderer.** No new rendering. The existing renderer reads the existing candidate object.
- **Use Stage 28 reliability surfaces.** No bespoke reliability handling at this layer. The bounded runner, the audited transport, the dispatch ledger, the heartbeat — all of those carry this candidate.
- **Send controlled private Discord pings only.** Same private channel. No new audience.
- **No public routing. No subscribers. No automated trading. No wallet / private-key logic. No X / social in the core path.**

### What "first real tradeable ping" means

- It's the first ping you see in Discord that was produced from a real provider-backed candidate that survived the full pipeline.
- It's not "the system thinks this trade is good." It's "the system thinks this candidate matches the lifecycle setup and is structurally clean enough to surface."
- The decision to trade it is still yours.

### Minimum conditions before you trust the first real ping

- The candidate's full provenance chain is reconstructible from the artifact layer.
- The pair lane is SOL (or, if USDC, the ping was suppressed — which is itself a positive signal).
- No measurement quality flags are tripped (no stale price, no ATH ambiguity, no provider degradation).
- The filter labels are populated and reviewed.
- The dispatch ledger shows a single, clean send.
- The render output redacts everything it should.

If any condition fails, the first ping is not yet trusted — even if it fires. The point of the first ping is **not to make money**; it is to learn whether the pipeline does what it claims.

---

## 8. Core Risks / Failure Modes

A brutal list. Each item: the risk, what's mitigated, what's still needed.

- **Bad ATH measurement.** *Mitigated:* Stage 25 hardening. *Still needed:* continuous monitoring against real candidates to catch edge cases.
- **Stale price data.** *Mitigated:* provider failure handling, observation-window discipline. *Still needed:* explicit staleness flag at measurement output so downstream can refuse.
- **Fake volume / wash trading.** *Mitigated:* event-pace and buy/sell behavior filters. *Still needed:* calibration to learn the false-positive profile on real data.
- **Bundled launches.** *Mitigated:* bundle/funding/source signal filters. *Still needed:* source-quality wallet graphing depth.
- **Bad liquidity.** *Mitigated:* liquidity quality filter. *Still needed:* simulated trade-size durability check.
- **Provider downtime.** *Mitigated:* provider failure handling, degraded-mode reporting. *Still needed:* multi-provider parallel intake for cross-validation.
- **Duplicate dispatch.** *Mitigated:* restart-safe ledger, explicit dedupe keys. *Still needed:* continued vigilance — Stage 28 covered this.
- **Leaked webhook / provider secrets.** *Mitigated:* redaction at the rendering layer. *Still needed:* operational hygiene; gitignore discipline; no secret in any artifact, ever.
- **Overfitted thresholds.** *Mitigated:* calibration loop with operator review. *Still needed:* out-of-sample evaluation requirement before any promotion.
- **Premature enforcement.** *Mitigated:* observe-only-first rule. *Still needed:* discipline — the temptation will be to enforce before there's enough data.
- **Noisy social signals.** *Mitigated:* social is not in the core path. *Still needed:* hold that line through Stage 30.
- **Pair-mixing between SOL and USDC lanes.** *Mitigated:* lane attribution at normalization. *Still needed:* test that policies cannot accidentally read across lanes.
- **False confidence from synthetic tests.** *Mitigated:* awareness. *Still needed:* the next milestone is real-candidate smoke specifically because synthetic confidence has run its course.
- **Too much architecture before live data.** *Mitigated:* stage discipline forces real artifacts at every step. *Still needed:* honesty — every additional layer not justified by live data is debt.
- **Letting X / social distract from the on-chain engine.** *Mitigated:* social is explicitly Stage 30+. *Still needed:* when social work feels easier than candidate wiring, that is the signal to stay on candidate wiring.

The single biggest risk right now is **too much architecture before live data.** The pipeline is excellent. The signal has not yet been pointed at it. Every additional staging week before real-candidate smoke is a week where the pipeline could be wrong in a way you don't yet know about.

---

## 9. Trade Secret / Edge Inventory

Categories: **PUBLIC** (safe to discuss openly), **MENTOR-ABSTRACT** (safe with a trusted mentor in abstract form), **INTERNAL** (private/internal only), **NEVER** (never disclose).

| Edge component | Category |
| --- | --- |
| Staged architecture and sub-stage discipline | PUBLIC |
| Layer separation philosophy | PUBLIC |
| Observe-only before enforcement | PUBLIC |
| Provider-neutral adapter philosophy | PUBLIC |
| Reliability model (bounded runners, ledgers, heartbeats) | PUBLIC |
| Pair-aware lanes (the existence of) | PUBLIC |
| Artifact/audit philosophy | PUBLIC |
| Lifecycle setup framing (launch/migration/ATH/post-ATH) at high level | MENTOR-ABSTRACT |
| Drawdown tiering as a concept | MENTOR-ABSTRACT |
| Calibration loop and operator review | MENTOR-ABSTRACT |
| Quality filter families (named generically) | MENTOR-ABSTRACT |
| Pair-specific calibration as a concept | MENTOR-ABSTRACT |
| Private ping path as a concept | MENTOR-ABSTRACT |
| Exact lifecycle setup recipe | INTERNAL |
| Exact ATH / migration measurement logic | INTERNAL |
| Exact drawdown tier boundaries | INTERNAL |
| Exact timing windows | INTERNAL |
| Exact filter thresholds | INTERNAL |
| Exact filter decision recipes | INTERNAL |
| Pair-specific calibration constants | INTERNAL |
| Fee decomposition primitives (exact math) | INTERNAL |
| Calibration artifacts (raw) | INTERNAL |
| Policy review artifacts (raw) | INTERNAL |
| Operator review process specifics | INTERNAL |
| Provider identity | INTERNAL |
| Private Discord channel details | INTERNAL |
| Schema field names that reveal edge | INTERNAL |
| Private datasets | NEVER |
| Keys / endpoints / webhook URLs | NEVER |
| Raw operator review artifacts | NEVER |
| Exact candidate recipe in full | NEVER |
| Anything that lets someone clone the signal | NEVER |
| Wallet addresses / operator identity in artifacts | NEVER |

**Rule of thumb.** If a single artifact, leaked, would let a competent reader rebuild the signal → NEVER. If it teaches the shape of the system without enabling clone → MENTOR-ABSTRACT.

---

## 10. What to Show Paul / Outside Mentor vs What to Hide

| Bucket | Examples |
| --- | --- |
| **Can share openly** | Staged architecture. Provider-neutral adapter philosophy. Observe-only-before-enforcement principle. Artifact/review pipeline structure. Reliability model. The fact that PHX2 is a Solana memecoin research environment. |
| **Can share abstractly** | Lifecycle detection (the concept, not the recipe). Candidate context (the existence of, not the fields). Quality labels (the families, not the names). Calibration lanes (the existence of, not the constants). Private ping path (the existence of, not the format). Operator review loop (the existence of, not the artifacts). |
| **Do not share** | The exact trade setup. Threshold values. Drawdown tier boundaries when too revealing. Exact timing windows. Exact filter logic. Exact schema field names that expose edge. Provider identity. Webhook routing details. Closure SHAs or commit identifiers. Internal stage summaries (raw). |
| **Never share** | Any private key. Any webhook URL. Any provider endpoint with auth. Raw proprietary datasets. The exact candidate recipe in full. Private policy artifacts. Anything (including a single example screenshot) that would let a competent reader reverse the signal. |

[architect_dump.md](architect_dump.md) respects this table. This document does not.

---

## 11. Agent / Future Brain Roadmap

The substrate-first bet: don't build an agent on top of PHX2. Build PHX2 so an agent can be added on top.

Roles a future agent could play, in increasing autonomy:

1. **Reader.** Reads artifacts, surfaces what changed since last session. Pure summarization. Zero authority.
2. **Reviewer.** Reads candidate review packets and produces commentary you read. Still zero authority.
3. **Comparator.** Compares current candidate cohorts against historical cohorts. Surfaces drift. You decide what to do.
4. **Proposer.** Suggests threshold changes or policy candidates based on calibration data. You approve.
5. **Anomaly flagger.** Watches the live stream and flags anomalies (provider degradation, measurement drift, dispatch oddities). You confirm.
6. **Session summarizer.** Produces post-session summaries you can read in lieu of raw artifacts.
7. **Policy proposer.** Proposes complete policy changes — new lanes, new label suppressions. You approve. No autonomous promotion.
8. **Calibration proposer.** Runs calibration cohorts and proposes promotions. You approve.

What the agent should **never** have at first:
- Wallet authority.
- Private-key authority.
- Direct dispatch authority (no agent-fired pings).
- Policy promotion authority (agent proposes, you promote).
- Provider configuration authority.

"Agent as brain" eventually means: the agent reads the structured environment, proposes everything, and the operator confirms or vetoes. Approval lives with the operator. Execution remains separate from the agent entirely.

What stays human-controlled, probably forever:
- Capital allocation.
- Live trade decisions.
- Promotion of a candidate to live enforcement.
- Disclosure decisions (what gets shared with whom).

The agent's job is to make the operator's reading load smaller, not to replace the operator.

---

## 12. X / Social Sidecar Roadmap

Hold the line:

- **X / social is not core PHX2.** It is a Stage 30+ sidecar.
- **Social providers must be replaceable adapters.** Same rule as on-chain providers. Whether the source is TwitterAPI.io, official X API, or a scraper, the system above the adapter must not depend on it.
- **No social provider should become the brain.** Brain is on-chain candidate evidence. Social is context.
- **Social events become `SocialEvent` objects.** Normalized, typed, with provenance. Same discipline as on-chain events.
- **Social signals boost or contextualize.** They can raise the confidence of a candidate already qualified on-chain. They cannot qualify a candidate on their own. A token with strong social and no on-chain setup is **not** a ping. A token with the on-chain setup and corroborating social is a stronger ping.
- **Social comes after private tradeable pings are real.** Building social before real on-chain pings is the most attractive distraction in this project. It feels like progress because social work has fast feedback. It is not progress on the actual bottleneck.

The temptation to build social first is real. Resist it until Stage 29's candidate stream is producing real pings you trust.

---

## 13. Business / Distribution Roadmap

Distribution paths, ranked by edge-preservation:

1. **Solo, private.** You only. Maximum edge preservation. Current state.
2. **Private FNF group.** Friends and family. Small, trusted, vetted. Some signal echo, but contained.
3. **Founder lifetime slots.** A small, capped number of paid lifetime slots — early backers. Aligns incentives but irreversible.
4. **Paid tiers.** Recurring paid access at controlled tier size. Most revenue, most echo risk.
5. **Delayed public pings.** Public version delayed enough that the alpha is mostly extracted. Useful for marketing without surrendering edge.
6. **Open public pings.** Full echo. Edge destruction.

Marketing without surrendering edge:
- Receipts and PnL screenshots after the fact.
- Architectural posts that describe the system's discipline without the recipe (the [architect_dump.md](architect_dump.md) shape).
- Mentor and peer demos in abstract form.

**The rule.** Every echo step is a one-way door. You can only tighten distribution later at the cost of trust. You can always loosen it later. Default to tight.

### Why protecting edge matters

The signal works partly because few people are looking for *exactly* this lifecycle setup with *exactly* this measurement quality and *exactly* this filter set. Competing capital volume is what kills these setups. Edge preservation is not paranoia; it is the substrate's load-bearing assumption.

### How not to destroy the edge

- No public pings until paid tiers exist or the edge is already extracted.
- No public threshold disclosures.
- No public filter recipes.
- No screenshots that, taken together, would let someone reconstruct the setup.
- No mentor disclosures beyond the [architect_dump.md](architect_dump.md) abstraction level.

---

## 14. Biggest Architectural Questions

Sit with these:

- **Is the system too staged, or correctly staged?** Sub-stage discipline is buying real value. Is any sub-stage just performance? Honest test: does each closure document genuinely change what the next sub-stage can do?
- **Where is complexity actually helping vs slowing me down?** The seven-layer cut is real. The calibration loop is real. Is the artifact layer over-built relative to what real candidate data has actually justified yet?
- **What is the shortest path to real tradeable pings?** Stage 29. Specifically: real candidate intake → existing pipeline → existing dispatch. Don't add new layers en route. Don't build new filters en route. Don't refactor anything en route.
- **What must be proven with live data before enforcement?** That the labels distribute the way the thesis predicts. That ATH measurement holds on real candidates. That UNKNOWN/DISAGREE suppression catches what it should. That dedupe holds across real bursts. That dispatch latency is acceptable. That redaction holds.
- **What should stay manual?** Capital allocation. Trade decision. Promotion to enforcement. Disclosure decisions. Provider configuration.
- **What should become agent-readable?** Everything else. The reading load is what the agent layer should eventually carry.
- **Which filters are worth rebuilding from PHX1?** Only those whose PHX1 logic survived contact with real candidate streams. Anything PHX1 had that was theoretical should be re-derived from PHX2 data, not ported.
- **What is the minimum lovable private ping?** Token identity, lifecycle phase, tier label, one-line context summary, provenance pointer. Anything more is renderer scope creep.
- **How do I avoid leaking the alpha while getting feedback?** Use the abstraction levels in §§9–10. Default to MENTOR-ABSTRACT when in doubt. Never send a screenshot with raw fields.

When you feel lost, come back to these before adding anything new.

---

## 15. Final Mental Model

**PHX2 is not a bot.**

PHX2 is a **staged on-chain research environment** that converts your trading thesis into structured measurements, reviewable artifacts, calibrated policies, and (eventually) private live pings.

The trajectory is fixed:

> human intuition → structured evidence → observe-only policy → approved enforcement → agent-readable environment

The rules are fixed:
- No edge leakage.
- No premature distribution.
- No automated trading.
- No wallet authority.
- No public routing until edge is preserved another way.
- No social in the core path until the on-chain engine is real.

The current bottleneck is fixed: **point the pipeline at the real signal.**

Everything else is downstream of that.

When you reread this and feel lost, the answer is almost always:

1. Are you working on Stage 29's candidate wiring? If yes, continue.
2. If you're working on anything else, ask whether it's actually unblocking Stage 29 or just feels easier.
3. If it's the second, return to Stage 29.

The pipeline is built. The signal is waiting. Don't lose the plot.
