# PHX2 Architecture Dump

A builder-to-builder memo. The goal is to explain PHX2 well enough to be critiqued, without handing over the recipe it was built to study.

---

## Executive Summary

PHX2 is a staged, observe-first signal and research system targeting Solana token lifecycle events. The system observes on-chain activity, measures candidate context, applies an operator-reviewable policy layer, renders private operator pings, and dispatches them through a hardened private transport. It is currently a research and review tool, not an execution system: there is no automated trading, no wallet logic, and no public or subscriber routing.

The system is a deliberate ground-up restage of an older project ("Phoenix"). PHX2 keeps the conceptual goals but rebuilds them under a strict staged-development discipline: every increment lands as a numbered sub-stage with focused tests, an audit-grade closure artifact, and an operator-gated closure step. The reason for this rigor is that the previous system became hard to reason about and hard to evolve; PHX2 trades velocity for a verifiable, agent-readable substrate.

Current maturity: synthetic, dry-run, and live smoke paths all pass end to end; private Discord dispatch works on a controlled private channel; reliability hardening (bounded runners, restart-safe ledgers, health heartbeats, longer-session smoke harnesses) is in place and audited. The next sensitive step is wiring a real provider-backed lifecycle candidate into the existing private ping path under the same redaction and dedupe rules.

---

## 1. High-Level Purpose

PHX2 watches a specific class of Solana token lifecycle events, measures the surrounding context for each candidate, labels candidates with quality tags, and delivers concise private alerts to a single operator. Around that core, it maintains structured artifacts of every observed event and every decision the policy layer made, so that the system's quality can be evaluated and so that an agent or automation layer can later consume the environment as ground truth.

The underlying claim PHX2 is built to test is: a small number of well-defined lifecycle setups produce measurably better outcome distributions when filtered with the right candidate context. PHX2 does not need to be right about every candidate; it needs to be honest about every candidate.

---

## 2. Why Staged Instead of Hacked Together

The earlier Phoenix system was a single monolithic loop. It worked, but two specific failure modes hurt:

- It was hard to know what the system actually saw at the moment it made a call, because state mutated across loops.
- It was hard to make a meaningful change without risk of regressing an unrelated path, because layer boundaries were soft.

PHX2 was rebuilt as a sequence of small numbered sub-stages. Each sub-stage:

- Lands one capability or one hardening item, never two at once.
- Ships with focused tests that are expected to fail until the sub-stage is functional.
- Produces a closure artifact (a stage summary) describing inputs, outputs, deferred items, and known limitations.
- Closes only after explicit operator authorization, not on the author's judgment.

This is slower than a hackathon style. The payoff is a defensible audit trail, a test surface that grows with the system instead of lagging behind it, and stage-bounded semantics that a future agent can rely on when reading PHX2's artifacts.

---

## 3. Major System Layers

PHX2 is divided into seven layers. Each layer has a defined contract with the layers around it, and each layer can be exercised in isolation by test harnesses.

### 3.1 Ingestion / Provider Boundary

Provider adapters are the only components that talk to the outside world. Each adapter wraps one external source behind a stable internal interface so that the rest of the system never depends on a provider's wire format. Adapters handle backoff, retry, and rate-limit awareness, and produce typed events. Adapters do not interpret events; they normalize and pass them inward.

This boundary exists so the system can switch providers, run two providers in parallel for cross-validation, or run a synthetic provider during tests without touching downstream code.

### 3.2 Normalization / Event Contracts

Inside the boundary, events are translated into a small set of internal event types with stable, versioned schemas. These schemas form the contract every downstream layer reads against. The normalization layer is intentionally dumb: it does not measure, score, or decide. It enforces that downstream code never has to guess at provider-specific shape variations.

### 3.3 Measurement / Context Layer

The measurement layer takes a normalized event and computes candidate context: the surrounding state a policy layer or operator will need to make a judgment. Context is computed deterministically from inputs that exist at the time of the event, never from future state, so a candidate's context is reproducible from the event ledger.

Most of the proprietary work lives in this layer, and this memo deliberately abstracts the details. The interface, however, is simple: normalized event in, candidate context object out, with an explicit set of fields that downstream layers may read.

### 3.4 Candidate / Policy Review Layer

The policy layer is where candidate contexts are converted into quality labels. Labels are categorical and operator-facing, not raw numeric scores. The policy layer is intentionally observe-only: it produces a label and a record of why it produced that label, but it does not gate anything by itself. Gating is a separate concern owned downstream.

The policy layer's other job is to produce operator review artifacts: structured records of every candidate it saw, the label it assigned, and the inputs it considered. These artifacts are the substrate the operator (and, later, an agent) uses to evaluate whether the policy is correctly tuned.

### 3.5 Private Ping / Rendering Layer

The rendering layer takes a labeled candidate and produces a private ping payload: a short, opinionated message intended for one operator. Rendering owns redaction: anything that would leak alpha into a transport, log, or artifact is omitted, replaced with a stable placeholder, or summarized. Rendering also handles pair-aware calibration lanes, so candidates from different lifecycle categories do not get mixed in ways that confuse downstream review.

Rendering is intentionally separated from dispatch because the same rendered payload may eventually feed multiple consumers (private operator channel, private log archive, agent-readable feed). Today, only the operator channel is wired.

### 3.6 Dispatch / Reliability Layer

Dispatch is the last hop before a payload leaves the system. It handles:

- **Deduplication.** The same lifecycle setup should not produce repeat pings during a single window.
- **Rate awareness.** Bursts are bounded so the transport is not overwhelmed.
- **Restart safety.** A ledger of what has been dispatched survives process restart, so the system does not re-emit recent pings after a crash or planned restart.
- **Health heartbeats.** The system periodically writes a health artifact so an operator (or, later, a watchdog) can confirm liveness without reading the transport.
- **Bounded runners.** The dispatch path runs under a session runner with explicit start and stop conditions, so the system never silently drifts.

Dispatch is also where the private transport is invoked. The transport is currently a private Discord channel, abstracted behind an interface so it can be swapped later without changing upstream layers.

### 3.7 Artifact / Provenance / Audit Layer

Every sub-stage produces artifacts: closure summaries, smoke-run outputs, focused test results, ledgers, and review packets. Artifacts are written to a versioned location with a stable layout. Each artifact records:

- What inputs the run was given.
- What stage and code state produced it.
- What decisions the policy layer made.
- What was redacted before output.

This layer is the most important one for the long-term goal. Without provenance, no agent can evaluate the system; without redaction, no artifact is safe to circulate. The discipline here is that every layer above must write through this layer rather than logging ad-hoc.

---

## 4. Current Maturity Level

PHX2 is in a mid-stage state. Concretely:

- Synthetic, dry-run, and live smoke paths all pass through the full pipeline end to end.
- The private Discord dispatch path is wired and exercised on a private channel under operator control.
- Reliability hardening — bounded runners, restart-safe ledgers, health heartbeats, status artifacts, longer-session smoke harnesses — is in place and audited.
- Tests are extensive at the layer level; the test surface grows with each sub-stage and is treated as a hard requirement, not a nice-to-have. The system is heavily tested.
- The system has **not yet** been wired to a real provider-backed tradeable candidate. That is the next sensitive step (see §9).

The framing is deliberate: PHX2 is a finished pipeline that has not yet been pointed at the real signal. Pointing it is a separate, gated step.

---

## 5. The "Brain" Concept

PHX2 is built with a layered concept of where intelligence lives.

- **Today,** the operator is the source of truth. The system observes, labels, renders, and dispatches; the operator interprets and decides what (if anything) to do with each ping.
- **The artifacts and review packets the system produces are structured memory.** They are not just logs; they are designed to be read back later — by the operator, by an evaluation harness, or by an automation layer — to assess whether the policy layer is correctly tuned and whether the lifecycle setups it watches are actually predictive.
- **In the future,** an agent or automation layer can consume the environment PHX2 has built — the event ledger, the policy artifacts, the dispatch history, the outcome data — as ground truth. The goal is not to bolt an agent onto PHX2; the goal is to make PHX2 a clean, agent-readable substrate so an agent can be added without rewriting the system.

That is the most important architectural bet: keep the pipeline observe-only and the artifacts complete, so the agent layer can be added later as a consumer, not a participant.

---

## 6. Engineering Principles

These are constraints, not preferences:

- **Observe-only before enforcement.** Every new capability lands as a passive observer first. Gating, filtering, and side effects are added later, and only after observation has confirmed the capability behaves as expected on real inputs.
- **Private-only before public routing.** The system is wired exclusively to a single private operator channel. There is no public subscriber path, no broadcast feed, no third-party redistribution. The transport layer is built so adding any such routing would be a deliberate future decision, not an accidental side effect.
- **No automated trading.** PHX2 does not place orders. There is no execution module. The purpose is to surface candidates to an operator, not to act on them.
- **No wallet or private-key logic.** PHX2 does not handle keys, sign transactions, or hold custody of anything. This is a category boundary, not a current limitation.
- **No social / X module in the core path.** External social signals are explicitly outside the current pipeline. They may exist as a sidecar later, but they are not allowed to influence policy decisions in the core path.
- **Provenance and redaction first.** Every artifact carries provenance. Every output passes through redaction before it leaves the system. Both rules are enforced at the layer boundary, not at the caller's discretion.
- **Bounded runners and restart-safe ledgers.** Long-running processes are bounded by explicit session limits. State that must survive restart is written to a ledger; state that must not is held in-process only. The system is designed to crash safely and come back up without re-emitting recent dispatches.

---

## 7. What Is Intentionally Hidden In This Memo

This memo deliberately abstracts several things that would otherwise leak alpha or operational detail:

- The exact lifecycle setup the system watches is described as "lifecycle setup" only. The detection recipe is not in this document.
- The candidate context calculation is described as "context" without the specific signals, formulas, or windowed measurements that go into it.
- The quality label set is described categorically without naming labels, thresholds, or filter recipes.
- The pair-aware calibration lanes are mentioned as "calibration lanes" without describing how lanes are defined or which categories of candidate belong in which lane.
- The provider identity is abstracted as "provider adapter." The choice of provider is intentional and not part of this memo.
- The private transport is described as a "private Discord channel" at the highest level; webhook details, endpoint structure, and operational secrets are out of scope.
- File paths, directory layouts, schema field names, exact test counts, and commit identifiers are summarized rather than quoted. The system is heavily tested; the precise numbers are not the point here.
- The exact tradeable setup — the combination of lifecycle event, context, label, and lane that would actually produce an actionable ping in the wild — is not described in a way that would let it be cloned from this document.

The intent is for a reviewer to be able to critique the architecture, the staging discipline, the reliability model, and the agent-readability of the substrate, without being handed the recipe.

---

## 8. Questions I Want Feedback On

Concrete things a reviewer would help with:

- **Architecture blind spots.** Where is a layer doing something it shouldn't, or missing a responsibility it should own? Is the seven-layer cut the right cut, or are some of these layers actually one layer pretending to be two (or vice versa)?
- **Bad abstractions.** Are any of the interfaces between layers leaky in a way that will eventually force a rewrite? In particular, is the event contract layer holding up, or is it secretly coupled to the provider adapter's worldview?
- **Missing interfaces.** What contracts are implicit today that should be explicit? Especially around the artifact layer: is there a missing interface between "things the operator reads" and "things an agent will read"?
- **Reliability failure modes.** Where will the system fail in ways the current hardening does not catch? Bounded runners and restart-safe ledgers cover known failure modes; what unknown ones should I be planning for?
- **Overfitting risk.** Is the policy layer at risk of being tuned to look good on retrospective artifacts rather than on live distributions? How would you structure the evaluation harness to prevent that?
- **Complexity overshoot.** Where am I making this system more elaborate than it needs to be? Sub-stage discipline is valuable but slow. Is any layer paying for itself, or am I building scaffolding I will never use?
- **Agent-readability.** What would stop PHX2 from being a clean substrate that an agent can consume later? What changes now would make that future trivial instead of hard?

Honest, structural critique is more valuable than polish. If a layer should not exist, say so.

---

## 9. Current Next Step

The next milestone is wiring a real provider-backed lifecycle candidate into the existing private ping path, in a controlled way, while preserving every guarantee already in place: redaction at the rendering boundary, pair-aware lane handling, dedupe and rate awareness in dispatch, restart-safe ledger writes, and operator-only delivery.

The exact detection recipe is out of scope for this memo. What matters architecturally is:

- The capability lands as observe-only first. The candidate flows through the pipeline, gets a label, gets rendered, and lands in artifacts before any private ping fires.
- Only after artifact-side review confirms the candidate stream behaves as expected does the dispatch path get enabled for that candidate type.
- The transport remains the same private channel. No new audience is introduced as part of this step.
- The stage closes under the same discipline as every other sub-stage: focused tests, a closure artifact, deferred items captured, operator-authorized closure.

The reason this step is sensitive is that it is the first time the system points at the real signal it was built to study. Everything before this was infrastructure. From this point on, the artifacts the system produces become evaluable as research output, not just smoke output.
