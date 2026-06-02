# PHX2 Stage 30.11.0 — Dip-Gated Live Dispatch Wiring Spec Lock

Stage 30.11.0 is spec lock and tests only. Stage 30.11.0 ships exactly three
new files (this markdown, `stage30_11_manifest.py`, and the Stage 30.11.0
spec-lock pin test) plus one narrow test-only allowlist widening on the Stage
30.0 inventory pin and one narrow guard widening on the Stage 30.9.0 inventory
pin (so the Stage 30.11.0 scaffold is admitted while Stage 30.11.1+ and Stage
31 stay forbidden). Stage 30.11.0 ships ZERO production `.py` file beyond the
constants-only manifest, ZERO assembly bridge, ZERO runtime gate seam, ZERO
real dispatch sink, ZERO runtime wiring, ZERO artifact integration, ZERO new
live runner, ZERO new provider, ZERO new readiness gate, ZERO direct Stage 28
suppression-logic edit, ZERO live provider call, ZERO Discord send, ZERO live
run, ZERO env read, ZERO database, ZERO SQLite, ZERO zstd dependency or
implementation, ZERO compression, ZERO default storage root, ZERO broad
always-on daemon, ZERO public / subscriber / paid routing, ZERO Telegram / X /
social, ZERO trading / wallet / signing, ZERO enforcement, ZERO Stage 31, and
ZERO edit to any existing live runner / orchestrator / transport / Stage 28
suppression implementation file. Every Stage 30.11.1+ substage requires
separately authorized scope before any production `.py` file lands.

This document is the spec-lock / handoff contract for wiring the committed
dip-filtered gate seam into the live candidate-to-dispatch path so a private
compact ping is sent only for an eligible dip. It is prose plus closed-set
token tables. It carries no provider credential, no private transport
destination, no provider host address, no transport scheme prefix, no raw
request / response payload field name, and no request auth-metadata (see
Section 13).

The single most important Stage 30.11 planning finding: the dip-focused
eligibility decision is ALREADY proven offline. The committed Stage 30.9.3
seam composes the Stage 30.10 dip-gate stack and lets only a `PASS_TO_DISPATCH`
candidate reserve a dispatch — but that seam is pure / offline and consumes a
pre-assembled live gate input. Nothing committed assembles a live candidate
into that input, and nothing committed wires the seam into the live
candidate-to-dispatch path. The only committed live path is the ungated Stage
29.3 smoke, which dispatches the first assembled tradeable candidate with no
dip gate. Stage 30.11 wires the committed dip gate into the live path so a
private compact ping is sent only for an eligible dip, against committed +
tested code, with a bounded wall-clock runtime. Stage 30.11 does NOT build a
new live runner, does NOT build a new provider, and does NOT reimplement
readiness or suppression.

## 1. Purpose

Stage 30.11 is the dip-gated live dispatch wiring. Its purpose is to make the
live private compact dispatch path dip-focused by reusing the committed gate,
not by improvising one. The target behavior:

- run the committed Stage 30.9.3 dip gate over each live-assembled candidate;
- reserve a dispatch and drive the private send only for a `PASS_TO_DISPATCH`
  candidate;
- suppress every non-dip candidate cleanly before dispatch reservation; and
- bound the live run with an explicit wall-clock `max_runtime_seconds` cap.

The bot must NOT ping every migrated token. The bot must NOT ping every
tradeable candidate. The bot must ping only a compact tier-dip eligible
candidate, exactly as the committed dip gate already rules offline.

Stage 30.11.0 specifically is spec lock and tests only. Stage 30.11.0 is NOT
an assembly bridge, is NOT a runtime gate seam, is NOT a real dispatch sink,
is NOT a runtime wiring, is NOT an artifact integration, is NOT a live run, is
NOT a Discord send, and is NOT a tag / push / closure. Stage 30.11.0 makes no
commit, no tag, and no push by itself.

## 2. Non-purpose

Stage 30.11 is explicitly NOT, and Stage 30.11.0 implements no part of, any of
the following. Stated as the closed non-purpose list (each is a hard
negative):

- NOT a new live runner;
- NOT a new provider;
- NOT a new readiness gate;
- NOT a direct edit of Stage 28 suppression logic;
- NOT a reuse of the ungated Stage 29.3 send path directly;
- NOT a public bot;
- NOT subscriber routing;
- NOT paid / tier routing;
- NOT Telegram / X / social;
- NOT trading / wallet / signing;
- NOT enforcement activation;
- NOT a broad always-on daemon / background service;
- NOT a database / SQLite store;
- NOT a zstd / compression layer;
- NOT a default real storage root; and
- NOT Stage 31.

## 3. Why now

The dip-focused eligibility decision is proven offline; the live wiring is the
missing half. These findings are LOCKED so Stage 30.11 fills exactly this gap:

1. **Committed seam is offline.** The committed Stage 30.9.3 seam composes the
   Stage 30.10 dip-gate stack and lets only a `PASS_TO_DISPATCH` candidate
   reserve a dispatch — but it is pure / offline and consumes a pre-assembled
   live gate input.
2. **No assembly bridge.** Nothing committed assembles a live candidate into
   the Stage 30.9.3 live gate input.
3. **No live wiring.** Nothing committed wires the Stage 30.9.3 seam into the
   live candidate-to-dispatch path.
4. **Only the ungated path is live.** The only committed live path is the
   ungated Stage 29.3 smoke, which dispatches the first assembled tradeable
   candidate with no dip gate.
5. **No hand-improvising.** Running the live ceremony today would require
   hand-improvising a live dispatch path; Stage 30.11 builds and proves it
   first.
6. **No wall-clock bound.** The bounded session has count bounds plus an
   external stop signal but no native wall-clock runtime bound.

Stage 30.11 exists to wire the committed dip gate into the live path and prove
it offline before the controlled live ceremony resumes.

## 4. Gate placement and only-PASS send

The committed dip gate MUST be evaluated BEFORE dispatch reservation and
BEFORE the private Discord send. The locked placement contract:

- the gate runs BEFORE the bounded session reserves dispatch intent;
- the gate runs BEFORE any private send;
- only a `PASS_TO_DISPATCH` candidate may reserve a dispatch and drive the
  private send;
- a normal non-dip skip is a clean no-send, NOT a dispatch failure; and
- the tier / ATH / drawdown signals stay dispatch eligibility, not
  display-only.

Do NOT gate at the transport layer if that would count suppressed non-dips as
dispatch failures. Specifically, Stage 30.11 must NOT reuse the Stage 28.4 /
Stage 30.3 `PAYLOAD_REFUSED` transport-veto path for a normal non-dip skip:
there is no transport-layer veto for a normal non-dip skip. A non-dip
candidate is simply not reserved and not sent; it never becomes a
`PAYLOAD_REFUSED`-style transport failure.

The only-PASS real-send rule is absolute: the real dispatch sink (the
committed private ping plus the audited transport) is invoked ONLY for a
`PASS_TO_DISPATCH` candidate and ONLY within the dispatch and private-send
caps (`max_dispatches` / `max_private_discord_sends`). A non-dip or invalid
candidate can never reach the real sink. The run stops after the dispatch /
private-send cap is reached. The real send is impossible without a
`PASS_TO_DISPATCH` decision.

## 5. Existing logic reuse

Stage 30.11 MUST reuse the existing logic. It introduces NO new gate, NO new
provider, NO new live runner, and NO new transport. The locked reuse surfaces,
by exact name:

- `run_dip_filtered_live_gate_integration` — the committed Stage 30.9.3
  bounded orchestrator that runs the dip gate over a candidate stream and
  calls an injected dispatch sink only for a `PASS_TO_DISPATCH` candidate.
- `evaluate_dip_filtered_live_gate` — the committed Stage 30.9.3 adapter that
  runs the Stage 30.10 dip-gate stack over one assembled live candidate.
- `Stage30_9_3LiveGateInput` — the committed assembled-live-candidate carrier
  the seam evaluates.
- the Stage 30.10.1 / 30.10.2 / 30.10.3 dip-gate stack — the committed
  classifier, pre-dispatch gate, and gate artifact projection.
- `decide_tier` / `TierDecisionRecord` / `tier_token` — the Stage 30.1 tier
  projection.
- the existing ATH context — the ATH presence / drawdown evidence.
- the existing migration context — the migration presence / status.
- the existing MC / LP / current market context — the current market-cap /
  price availability.
- the existing Stage 28 / 29 / 30 live session and gates — Stage 30.11
  composes this path behind the dip gate; it does NOT fork it and does NOT
  reimplement it.

## 6. Runtime bound

Stage 30.11 adds the wall-clock `max_runtime_seconds` bound the bounded
session lacks today. The locked runtime-bound contract:

- `max_runtime_seconds` is an explicit wall-clock cap;
- the wiring stops cleanly when `max_runtime_seconds` elapses;
- the wall-clock bound composes with the existing count bounds;
- the wall-clock bound composes with the existing external stop signal; and
- there is no broad always-on daemon, no background service, and no
  autorestart loop.

## 7. Permitted scope expansion

Unlike the offline-only Stage 30.9.x / 30.10.x slices (which forbid every
Stage 21-29 production import), the Stage 30.11 RUNTIME wiring slices
(30.11.1+) are EXPLICITLY permitted to compose the committed live surfaces
behind the dip gate. The locked scope-expansion contract:

- Stage 30.11 runtime slices MAY compose the committed live surfaces behind
  the dip gate;
- the Stage 30.11.0 spec-lock files import nothing (the manifest is
  constants-only);
- per-slice permitted-import allowlists are pinned when each runtime slice
  lands;
- Stage 30.11 wires and composes; it never forks or reimplements;
- Stage 30.11 adds no new provider, no new runner, and no new readiness gate;
  and
- Stage 30.11 never widens routing beyond the private operator route.

## 8. Dip-gate decisions and result counters

Stage 30.11 reuses the committed Stage 30.9.3 dip-gate decision tokens
verbatim, one per evaluated live candidate, drawn from this closed set:

- `PASS_TO_DISPATCH` — an eligible dip (the only decision that reserves a
  dispatch / drives the private send);
- `SKIP_BEFORE_DISPATCH` — a normal non-dip, suppressed cleanly before
  dispatch reservation; and
- `INVALID_INPUT` — a malformed candidate, suppressed before reservation.

`PASS_TO_DISPATCH` is the only decision that allows a downstream send; every
other token is a no-send.

The live wiring tallies a bounded-run result over these counter axes:
`candidates_seen`, `candidates_evaluated`, `candidates_passed_gate`,
`candidates_skipped_before_dispatch`, `invalid_inputs`,
`dispatch_attempts_reserved`, `dispatch_failures_recorded`,
`transport_veto_count`, `payload_refused_count`, `private_discord_sends`, and
`created_at_utc`. The axes `dispatch_failures_recorded` /
`transport_veto_count` / `payload_refused_count` are ALWAYS 0 for a dip-gated
skip: a non-dip is suppressed before reservation, so it is never a dispatch
failure, never a transport veto, and never a `PAYLOAD_REFUSED` use. The
`created_at_utc` axis is caller-injected on the offline proof; no field is a
secret, a raw payload, a host, or a transport destination.

## 9. Failure behavior

Stage 30.11 is fail-closed end-to-end. The locked failure contract:

- readiness failure ⇒ no provider call, no Discord send;
- non-PASS candidate ⇒ suppressed before reservation, no send;
- invalid candidate ⇒ `INVALID_INPUT`, no reservation, no send;
- provider failure ⇒ bounded, no crash;
- Discord failure ⇒ closed-set transport failure, no crash;
- dispatch / private-send cap reached ⇒ clean bounded stop;
- `max_runtime_seconds` elapsed ⇒ clean bounded stop; and
- fail closed on any unknown / missing input, never fail open.

A skip NEVER becomes a transport failure: a non-dip candidate is simply not
reserved and not sent.

## 10. Future slices

Stage 30.11 is sequenced fake / offline before live, smallest reversible slice
first:

- Stage 30.11.0 — this spec lock only (spec doc + constants-only manifest +
  pin test). No runtime, no bridge, no seam, no sink, no live.
- Stage 30.11.1 — the fake / offline live-candidate-to-dip-gate-input assembly
  bridge: a pure mapping that composes the existing tier / ATH / migration /
  market-context surfaces into the committed Stage 30.9.3 live gate input,
  proven with fakes only. No runtime wiring, no live provider call, no Discord
  send.
- Stage 30.11.2 — the runtime gate seam with fakes only: run the committed dip
  gate over each live-assembled candidate inside the bounded session, reserve
  a dispatch only for a `PASS_TO_DISPATCH` candidate, and enforce a wall-clock
  `max_runtime_seconds` bound. Fake provider plus fake transport only.
- Stage 30.11.3 — the real dispatch sink adapter: compose the committed
  private ping plus audited transport as the seam's dispatch sink, invoked
  only for a `PASS_TO_DISPATCH` candidate. Still proven with fakes; the live
  ceremony is a separate operator-authorized step.
- Stage 30.11.4 — the offline end-to-end proof: fake provider to assembly to
  the committed dip gate to a fake sink, proving only-PASS dispatches plus the
  caps plus the wall-clock bound (the runtime counterpart of the Stage 30.10.3
  fake artifact proof).

Numbering may be adjusted if the project style suggests a better split; each
substage remains separately operator-authorized.

## 11. Stage 30.9.2 and 30.9.3 relationship

Stage 30.9.3 committed the pure / offline dip-gate seam
(`run_dip_filtered_live_gate_integration` / `evaluate_dip_filtered_live_gate`).
Stage 30.11 wires that committed seam into the live path and proves it offline
before the controlled live ceremony resumes. Stage 30.9.2 is paused, not
abandoned. Stage 30.9.2 is the bounded private live compact proof / operator
handoff. It resumes only after the dip-gated live dispatch path is wired and
proved offline. Until then, no live proof is run.

## 12. Forbidden surfaces

Stage 30.11 must NEVER touch any of the following. Explicitly listed as the
closed forbidden-surface set:

- a new live runner;
- a new provider;
- a new readiness gate;
- a direct Stage 28 suppression-logic edit;
- a transport-layer veto for a non-dip skip;
- a `PAYLOAD_REFUSED` for a normal non-dip skip;
- a non-dip counted as a dispatch failure;
- a direct reuse of the ungated Stage 29.3 send path;
- public routing;
- subscriber routing;
- paid tiers;
- Telegram;
- X / social;
- automated trading;
- wallet / signing;
- enforcement activation;
- auto-buy;
- strategy execution;
- a broad always-on daemon;
- a database / SQLite store;
- zstd / compression;
- a default storage root;
- a background service; and
- Stage 31.

In addition, Stage 30.11.0 edits NO existing live runner / orchestrator /
transport file, NO Stage 28 suppression implementation file, and NO Stage 25 /
27 / 28 / 29 production file. (The future Stage 30.11.1+ runtime slices compose
the committed live surfaces behind the dip gate under their own per-slice
permitted-import allowlists; see Section 7.)

## 13. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage 30.6.0 /
30.7.4 / 30.8.0 / 30.9.0 / 30.10.0 records. It carries no provider credential
strings, no private transport destination strings, no provider host address
strings, no transport scheme prefixes, no raw request-payload or
response-payload field names, and no request auth-metadata strings. It records
only closed-set tokens, field names, thresholds, prose, and safe design
labels.

The Stage 30.11.0 pin test enforces this by scanning this document, the
manifest, and the test, case-insensitively, against a split-literal
forbidden-substring vocabulary, so none of the three files can carry any of
the sanitized-away substrings even inside a negative claim.

---

_Stage 30.11.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.11.0 implementation.
- There is no Discord send during Stage 30.11.0 implementation.
- There is no assembly bridge, no runtime gate seam, no real dispatch sink,
  no runtime wiring, and no artifact integration at Stage 30.11.0.
- There is no new live runner, no new provider, and no new readiness gate at
  Stage 30.11.0.
- There is no direct edit of Stage 28 suppression logic at Stage 30.11.0.
- There is no database, no SQLite, no zstd dependency, no zstd
  implementation, and no compression at Stage 30.11.0.
- There is no default storage root and no background daemon at Stage 30.11.0.
- There is no env read at Stage 30.11.0.
- There is no edit to any existing live runner / orchestrator / transport
  file (the Stage 30.0 inventory allowlist widening and the Stage 30.9.0
  inventory guard widening excepted) at Stage 30.11.0.
- There is no public routing, no subscriber routing, no paid routing, no
  Telegram, no X / social, no trading / wallet / signing, and no enforcement
  at Stage 30.11.0.
- There is no Stage 25 / 27 / 28 / 29 (or Stage 29.5) production import at
  Stage 30.11.0.
- There is no Stage 30.11.1+ implementation file at Stage 30.11.0.
- There is no Stage 31 surface at Stage 30.11.0.
- There is no commit, no tag, and no push performed by Stage 30.11.0
  implementation. Commit gating is a separate operator decision after audit.
