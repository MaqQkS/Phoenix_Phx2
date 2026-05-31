# PHX2 Stage 30.9.0 — Bounded Private Live Compact Session Bridge Spec Lock

Stage 30.9.0 is spec lock and tests only. Stage 30.9.0 ships exactly
three new files (this markdown, `stage30_9_manifest.py`, and the Stage
30.9.0 spec-lock pin test) plus one narrow test-only allowlist widening on
the Stage 30.0 inventory pin. Stage 30.9.0 ships ZERO production `.py`
file beyond the constants-only manifest, ZERO runtime code, ZERO artifact
bridge, ZERO capture transport, ZERO post-session projector, ZERO live
provider call, ZERO Discord send, ZERO env read, ZERO database, ZERO
SQLite, ZERO zstd dependency or implementation, ZERO compression, ZERO
default storage root, ZERO public / subscriber / paid routing, ZERO
Telegram / X / social, ZERO trading / wallet / signing, ZERO enforcement,
ZERO background daemon, and ZERO edit to any existing live runner /
orchestrator / transport / Stage 30.8 implementation file. Every Stage
30.9.1+ substage requires separately authorized scope before any
production `.py` file lands.

This document is the spec-lock / handoff contract for safely bridging the
ALREADY-EXISTING bounded private live compact-ping engine to the
ALREADY-EXISTING Stage 30.8 compact session artifact storage chain, so the
operator can eventually leave the bot running and collect retained /
duplicate / invalid artifact proof over real-shaped sessions. It is prose
plus closed-set token tables. It carries no provider credential, no
private transport destination, no provider host address, no transport
scheme prefix, no raw request / response payload field name, and no
request auth-metadata (see Section 11).

The single most important Stage 30.9 planning finding: the bounded private
live compact-ping chain ALREADY EXISTS and has already run live in earlier
proof stages. Stage 30.9 does NOT build a new live runner and does NOT
reimplement readiness gates. The only missing capability is persisting
Stage 30.8-format compact session artifacts from a live-shaped session and
proving retained / duplicate / invalid over them.

## 1. Purpose

Stage 30.9 is a bounded private live compact session bridge. Its purpose
is to:

- reuse the existing bounded private live compact engine (no new live
  loop);
- send compact private Discord pings under an explicit operator request
  (the existing live-operator-request gate);
- persist Stage 30.8-compatible compact session artifacts AFTER the
  session ends; and
- prove retained / duplicate / invalid artifacts post-session over those
  persisted artifacts.

Stage 30.9.0 specifically is spec lock and tests only. Stage 30.9.0 is NOT
a bridge implementation, is NOT a capture transport, is NOT a projector,
is NOT a live run, is NOT a Discord send, and is NOT a tag / push /
closure. Stage 30.9.0 makes no commit, no tag, and no push by itself.

## 2. Non-purpose

Stage 30.9 is explicitly NOT, and Stage 30.9.0 implements no part of, any
of the following. Stated as the closed non-purpose list (each is a hard
negative):

- NOT a new live runner;
- NOT a new readiness gate;
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

## 3. Existing engine reuse

Stage 30.9 MUST reuse the existing bounded private live compact engine. It
introduces NO new live loop. The locked reuse surfaces, by exact name:

- `run_stage30_4_2_compact_runtime_session` — the live compact engine
  entry (the opt-in parallel compact runtime session orchestrator).
- `run_stage30_3_compact_runtime_session` — the compact body wrapper layer
  beneath it.
- `run_stage28_9_live_provider_session` — the live provider session
  adapter the compact body wraps.
- `evaluate_stage28_9_readiness` — the readiness gate (the ONLY readiness
  gate; Stage 30.9 reimplements none).
- `Stage28_9LiveProviderSessionConfig` — the bounded caps / session
  identity config (`run_id` / `session_id` / `max_events` /
  `max_dispatches` / `max_ticks` / `max_total_retries` / `session_mode` /
  the safe output-dir label).
- `Stage28_9PrivateWebhookTransport` and the Stage 28.4 audited HTTP
  transport — the private webhook dispatch path.
- `Stage28_6BoundedPrivateSessionRunner` — the bounded private session
  runner that reserves dispatch intent before any send.
- the Stage 27.6 / Stage 28.2 runtime dedupe / dispatch ledger — the
  runtime dedupe and dispatch-intent ledger (the source of the
  `dedupe_key`).

The existing live compact path composes as:
`run_stage30_4_2_compact_runtime_session` →
`run_stage30_3_compact_runtime_session` →
`run_stage28_9_live_provider_session` →
`Stage28_6BoundedPrivateSessionRunner` →
`Stage28_9PrivateWebhookTransport` / Stage 28.4 audited HTTP transport.

Stage 30.9 wraps and observes this path; it does NOT fork it, does NOT
reimplement it, and does NOT introduce a parallel live loop.

## 4. Stage 30.8 artifact bridge contract

Stage 30.9.1 will add the artifact bridge. This section LOCKS its design;
Stage 30.9.0 implements none of it.

The bridge is two pieces: a thin innermost capture transport and a
post-session projector.

### 4.1 Thin innermost capture transport

The capture transport:

- wraps the inner transport (the existing private dispatch transport);
- records the safe-shape webhook identity (`webhook_identity`), never the
  destination;
- records the enriched compact payload content exactly as sent;
- records the sanitized transport result (a closed-set status code only);
- forwards the payload verbatim to the inner transport;
- does NO mutation of the payload;
- does NO filesystem I/O; and
- does NO network itself, except the delegated inner transport.

The capture transport is the innermost wrapper: it sees exactly what is
sent, records a sanitized projection, and forwards unchanged.

### 4.2 Post-session projector

The post-session projector:

- joins the capture records with the Stage 28.9 / Stage 28.2 dispatch
  ledger data;
- obtains the `dedupe_key` from the runtime dispatch ledger, NOT by
  recomputing it ad hoc;
- emits Stage 30.8.1 model types;
- writes ONE Stage 30.8 compact session bundle with
  `write_compact_session_artifact_bundle`; and
- runs `read_compact_session_bundle` and `build_compact_session_index`
  for the post-session retained / duplicate / invalid proof.

### 4.3 Write timing (post-session only)

- Stage 30.8 writes are POST-SESSION ONLY.
- The Stage 30.8 writer is NEVER called per ping.
- The Stage 30.8 index is post-run proof ONLY; it is NEVER a runtime gate.

## 5. Gating and caps

Stage 30.9 reuses the existing readiness gate and bounded caps unchanged.
The locked gating contract:

- `live_env_ready` must be explicit `True`.
- `live_operator_request` must be explicit `True`.
- `private_webhook_url` must be private, non-empty, and pass the existing
  shape-safe gate.
- `output_dir` must be explicit and safe.
- `output_dir` must remain outside the repository when the existing
  readiness gate requires it.
- `max_events` must be `> 0`.
- `max_dispatches` must be `> 0`.
- `max_ticks` must be `> 0` if used.
- `max_total_retries` must be bounded (non-negative, finite).
- DRY_RUN vs LIVE_PRIVATE separation flows through the existing config /
  `session_mode` (`DRY_RUN` / `LIVE_PRIVATE`), never a new switch.
- There is no default storage root.

Important caps caveat:

- `max_runtime_seconds` is NOT currently supported on this compact path,
  unless an existing `stop_signal` path is driven externally.
- Stage 30.9 does NOT invent a wall-clock loop and does NOT add a
  background daemon. A bounded run stops on the existing event / dispatch
  / tick caps (or an externally driven `stop_signal`), never on a new
  internal timer.

## 6. Dedupe stance

The locked dedupe stance:

- runtime dedupe remains Stage 27.6 + Stage 28.2 (the runtime dedupe /
  dispatch-intent ledger);
- the Stage 30.8 dedupe index remains post-run proof ONLY;
- the `dedupe_key` must be carried into the Stage 30.8 compact ping
  artifacts (sourced from the runtime dispatch ledger);
- there is NO new DB-backed dedupe; and
- there is NO cross-session runtime dedupe in Stage 30.9.

The runtime suppresses a duplicate candidate BEFORE any send (Stage 27.6 /
Stage 28.2). The Stage 30.8 index re-proves retained / duplicate / invalid
AFTER the run, over the persisted artifacts, as an independent post-run
check — never as a runtime gate.

## 6.1 Dedupe / suppression status tokens

The post-session proof reuses the existing Stage 30.8.3 per-ping dedupe
status closed set, unchanged:

- `RETAINED` — exactly one terminal ping artifact retained per
  `dedupe_key`;
- `DUPLICATE_SUPPRESSED` — a repeat of an already-retained `dedupe_key`;
- `INVALID_SUPPRESSED` — a missing / unknown `dedupe_key` pair (never
  retained).

## 7. Artifact fields

Every persisted Stage 30.8 compact ping artifact carries the following
stable identity. Each is a safe-shape opaque id, a closed-set token, or an
ISO-8601 UTC timestamp. NONE is a secret, a raw payload, a host, or a
transport destination:

- `run_id` — the runtime-context run identifier.
- `session_id` — the private-soak session identifier.
- `ping_id` — the compact ping identifier.
- `candidate_id` — the candidate identifier.
- `token_mint` — the candidate / token mint (safe-shape base58).
- `dedupe_key` — the dedupe key from the runtime dispatch ledger.
- `artifact_created_at_utc` — the artifact creation timestamp (ISO-8601
  UTC, from the caller-injected clock).
- `artifact_kind` — the closed-set artifact kind (the Stage 30.8 compact
  ping artifact kind).

Provenance / sourcing is LOCKED as follows:

- the `dedupe_key` must come from the runtime dispatch ledger, NOT a
  recomputed ad-hoc value;
- the `session_id` / `run_id` must come from
  `Stage28_9LiveProviderSessionConfig`;
- the `ping_id` / `candidate_id` must come from the live candidate /
  adapter path; and
- the compact body content must be captured from the enriched payload
  actually sent, not reconstructed when avoidable.

## 8. Failure behavior

Stage 30.9 is fail-closed end-to-end. The locked failure contract:

- readiness failure ⇒ no provider call, no Discord send;
- provider failure ⇒ bounded, no crash;
- Discord failure ⇒ a closed-set transport failure, no crash;
- writer failure ⇒ an artifact-proof failure; sent pings are unaffected;
- reader / index failure ⇒ an artifact-proof failure;
- missing `dedupe_key` ⇒ an invalid artifact (proof marks it
  `INVALID_SUPPRESSED`);
- a duplicate candidate ⇒ runtime-suppressed BEFORE send;
- an invalid / unknown pair ⇒ runtime-suppressed BEFORE send; and
- a cap hit ⇒ a clean bounded stop.

A storage / proof failure NEVER unsends a ping and NEVER crashes the live
session: the artifact bridge is strictly downstream of the already-sent,
already-bounded compact pings.

## 9. Future slices

Stage 30.9 is sequenced fake / offline before live, smallest reversible
slice first:

- Stage 30.9.0 — this spec lock only (spec doc + constants-only manifest +
  pin test). No runtime, no bridge, no live.
- Stage 30.9.1 — the artifact bridge with fakes / offline only: the
  capture transport, the post-session projector, the Stage 30.8 bundle
  write, and the Stage 30.8 reader / index proof, all proven with a fake
  provider + fake Discord + temp dirs. No live provider call, no real
  Discord send.
- Stage 30.9.2 — the live proof doc / operator runbook / closure handoff:
  no new runtime unless explicitly authorized; an operator-driven bounded
  live proof executed out-of-repo; private Discord only.

Numbering may be adjusted if the project style suggests a better split;
each substage remains separately operator-authorized.

## 10. Forbidden surfaces

Stage 30.9 must NEVER touch any of the following. Explicitly listed as the
closed forbidden-surface set:

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
- a background service;
- inline per-ping Stage 30.8 writes; and
- Stage 31.

In addition, Stage 30.9 edits NO existing live runner / orchestrator /
transport file, NO Stage 30.8 implementation file (manifest / allowlist
widening excepted), and NO Stage 25 / 27 / 28 / 29 production file.

## 11. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage 30.6.0 /
30.7.4 / 30.8.0 records. It carries no provider credential strings, no
private transport destination strings, no provider host address strings,
no transport scheme prefixes, no raw request-payload or response-payload
field names, and no request auth-metadata strings. It records only
closed-set tokens, field names, thresholds, prose, and safe design labels.

The Stage 30.9.0 pin test enforces this by scanning this document, the
manifest, and the test, case-insensitively, against a split-literal
forbidden-substring vocabulary, so none of the three files can carry any
of the sanitized-away substrings even inside a negative claim.

---

_Stage 30.9.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.9.0 implementation.
- There is no Discord send during Stage 30.9.0 implementation.
- There is no artifact bridge, no capture transport, and no post-session
  projector at Stage 30.9.0.
- There is no Stage 30.8 writer / reader / index invocation at Stage
  30.9.0.
- There is no new live runner and no new readiness gate at Stage 30.9.0.
- There is no database, no SQLite, no zstd dependency, no zstd
  implementation, and no compression at Stage 30.9.0.
- There is no default storage root and no background daemon at Stage
  30.9.0.
- There is no env read at Stage 30.9.0.
- There is no edit to any existing live runner / orchestrator / transport
  file and no edit to any Stage 30.8 implementation file (the Stage 30.0
  inventory allowlist widening excepted) at Stage 30.9.0.
- There is no public routing, no subscriber routing, no paid routing, no
  Telegram, no X / social, no trading / wallet / signing, and no
  enforcement at Stage 30.9.0.
- There is no Stage 25 / 27 / 28 / 29 (or Stage 29.5) production import at
  Stage 30.9.0.
- There is no Stage 31 surface at Stage 30.9.0.
- There is no commit, no tag, and no push performed by Stage 30.9.0
  implementation. Commit gating is a separate operator decision after
  audit.
