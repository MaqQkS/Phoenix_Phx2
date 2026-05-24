# PHX2 Stage 29 Handoff

This document hands the Stage 29 charter from the closing Stage
28 reliability pass to a future Stage 29 implementation pass.
Stage 28.8 ships this handoff document as a planning artifact
only. Stage 28.8 does not implement Stage 29.

---

## 1. Stage 29 mission

Stage 29 is **approved enforcement / live gating for private
pings**. Stage 29 turns the Stage 26.6 operator-approved policy
candidates into runtime gating decisions for the Stage 28
private live runner, while preserving the Stage 26 / Stage 28
discipline that audience is private-operator-only and that
runtime never receives unapproved policy candidates.

Stage 29 does not broaden audience, does not introduce a public
distribution surface, and does not introduce a trading verdict
surface.

---

## 2. Inputs from Stage 28

Stage 29 builds directly on the Stage 28 reliability surface:

- the bounded private session runner (Stage 28.6)
- the restart-safe dispatch ledger (Stage 28.2)
- the failure classifier (Stage 28.3a)
- the bounded retry policy (Stage 28.3b)
- the audited private Discord transport (Stage 28.4)
- the heartbeat / health snapshot / final-summary / CLI status
  artifacts (Stage 28.5)
- the longer-session offline smoke harness and the controlled
  live smoke runbook (Stage 28.7)

Stage 29 consumes these as already-reliable primitives. Stage
29 must not rewrite them, must not bypass them, and must not
relax their redaction / audit / bounded-retry guarantees.

---

## 3. Upstream evidence from Stage 26

Stage 29's enforcement decisions are anchored in evidence
produced by Stage 26:

- policy candidate artifacts (Stage 26.5)
- threshold candidates (Stage 26.4)
- operator review packets (Stage 26.6)
- **approved / reviewed policies only** — Stage 29 must never
  promote a Stage 26.5 candidate into runtime gating without
  evidence of an operator-approved Stage 26.6 review packet

Stage 29 must pin the approval evidence by reference (artifact
basename + SHA-256) and must never mutate the upstream Stage
25 / Stage 26 artifacts in place.

---

## 4. Required starting point

Stage 29.0 must be **spec lock / enforcement charter only**. It
must ship the canonical Stage 29 scope sentence, the closed-set
gate-mode vocabulary, the closed-set gate-decision vocabulary,
the approval-evidence pinning contract, the planned Stage 29
substage list, and the Stage 30+ handoff intent — and nothing
else.

Stage 29.0 must NOT ship a runtime policy reader, a gate
evaluator, a runner adapter, a dispatch wrapper, a fail-closed
artifact writer, or any other implementation file. Stage 29.0
must pass an empty-implementation boundary scan that confirms
no Stage 29 production .py file other than the package marker
and the spec-lock doc ships at Stage 29.0.

---

## 5. Observe-only versus enforced gates

Stage 29 must separate three distinct gate modes:

1. **observe-only** — the gate reads the approved policy,
   records what it WOULD do, but does not modify the Stage 28
   dispatch decision. Used during operator review.
2. **shadow** — the gate runs alongside the live dispatch path
   and records its decision into a separate audit artifact, but
   does not modify the Stage 28 dispatch decision. Used to
   collect divergence evidence between the proposed enforcement
   and the live private runner.
3. **enforced** — the gate's decision is the authoritative
   dispatch decision; the Stage 28 dispatch is suppressed or
   allowed per the gate. Used only after explicit operator
   authorization on a per-policy basis.

Every enforced gate must be **explicitly versioned and
approved**. The Stage 29 manifest must pin the approved policy
versions, and the gate evaluator must refuse to enforce a
policy whose approval evidence cannot be replayed.

Every gate decision must carry a **closed-set suppress / allow
reason** and that reason must be recorded on the dispatch audit
artifact alongside the run identity.

---

## 6. Proposed Stage 29 outline

The Stage 29 substage plan below is the proposed roadmap. Each
substage requires its own explicit operator authorization
before implementation begins.

- **29.0** spec lock / enforcement charter
- **29.1** approved policy-candidate reader and approval
  evidence pinning
- **29.2** observe-only gate evaluator
- **29.3** private-runner shadow gate artifacts
- **29.4** enforced private dispatch gate adapter
- **29.5** fail-closed reason codes and operator audit
  artifacts
- **29.6** controlled private enforcement smoke runbook
- **29.7** closure audit / Stage 30+ handoff

Stage 29 substages must each preserve the Stage 28 reliability
discipline: no env reads outside the locked readiness site, no
new network library imports, no public routing, no Telegram /
X / social, no automated trading, no wallet / signer logic, no
dashboard / HTTP control server, no daemon / watchdog.

---

## 7. Stage 29 must not include

Stage 29 must not include any of the following:

- public routing
- subscriber routing
- paid tiers
- Telegram
- X/social
- automated trading
- wallet/private-key/signer logic
- trade execution
- position sizing
- public dashboard/control server

The Stage 29 charter (Stage 29.0) must declare each exclusion
in writing and the Stage 29 boundary scans must pin each
exclusion against the Stage 29 production / doc / test tree.

---

## 8. Stage 30+ ownership

The following surfaces are explicitly out of Stage 29 scope and
belong to Stage 30+:

- X / social sidecar
- provider-agnostic social event schema
- social boost / annotation, not the core brain

Stage 29 must not introduce any X / social code, must not
introduce a public broadcast surface, and must not introduce a
social-event ingestion adapter. Stage 30+ owns the X / social
sidecar and ships it as an annotation layer next to the core
private brain, never as the core brain itself.
