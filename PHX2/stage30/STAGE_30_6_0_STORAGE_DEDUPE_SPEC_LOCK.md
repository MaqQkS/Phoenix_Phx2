# PHX2 Stage 30.6.0 — 24/7 Readiness Storage + Dedupe Spec Lock

Stage 30.6.0 is spec lock and tests only. Stage 30.6.0 ships exactly
three new files (this markdown, `stage30_6_manifest.py`, and the
Stage 30.6.0 spec-lock pin test) plus one narrow test-only allowlist
widening on the Stage 30.0 inventory pin. Stage 30.6.0 ships ZERO
production `.py` file beyond the manifest, ZERO storage writer, ZERO
dedupe engine, ZERO budget evaluator, ZERO lifecycle-seal aggregate,
ZERO database migration, ZERO filesystem writer, ZERO zstd
dependency or implementation, ZERO live provider call, ZERO Discord
send, ZERO candidate scan, ZERO ATH, ZERO Net, ZERO filters, ZERO
enforcement, and ZERO modification to any Stage 21-29 production
source or to any Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 runtime
source. Every Stage 30.6.1+ substage requires separately authorized
scope before any production `.py` file lands.

This document is the spec-lock / handoff contract for making PHX2
safe to leave running for long private soaks before ATH context is
added. It is prose plus closed-set token tables. It carries no
provider credential, no private transport destination, no provider
host address, no transport scheme prefix, no raw request / response
payload field name, and no request auth-metadata (see Section 12).

## 1. Stage 30.6 scope and stance

Stage 30.6 is the 24/7-readiness storage and dedupe family of Stage
30. Its single goal is to lock the storage and dedupe architecture
so PHX2 can run unattended for long private soaks without:

- repeated same-token pings,
- same-tier spam,
- unbounded raw-event / database / file bloat,
- the legacy PHX1-style giant DB / log accumulation, or
- out-of-disk crashes.

Stage 30.6 is explicitly:

- storage + dedupe readiness only.
- NO ATH. ATH context stays out of Stage 30.6 (see Section 11).
- NO Net. Net flow stays deferred.
- NO filters. No filter logic is added or activated.
- NO enforcement. Stage 26 / Stage 29 enforcement stays inactive.
- NO live. No live run of any kind in any Stage 30.6.0 step.
- NO Discord. No Discord send in any Stage 30.6.0 step.
- NO provider calls. No live gRPC / HTTP / WebSocket provider call
  of any kind during Stage 30.6.0.
- NO candidate scan. No live candidate scan.
- NO database migration, NO SQLite write, NO filesystem writer.
- NO dedupe logic implemented yet — Stage 30.6.0 locks the dedupe
  contract only.
- NO public or subscriber routing. The compact ping stays a single
  private operator surface.
- NO trading, NO wallet, NO signer surface.
- NO Telegram, NO X, NO social surface.

Stage 30.6.0 specifically is spec lock and tests only. Stage 30.6.0
is NOT a storage implementation, is NOT a dedupe implementation, is
NOT live runtime, is NOT Discord, is NOT ATH, and is NOT a tag or a
closure. Stage 30.6.0 makes no commit, no tag, and no push by
itself.

## 2. 24/7 readiness definition

"Safe to leave running" is defined for Stage 30.6 as the conjunction
of all of the following commitments:

- controlled private soak mode — the long run is a bounded private
  operator soak, never a public service;
- bounded write growth — every write surface has an explicit bound;
- dedupe / session persistence — a persisted seen-state suppresses
  duplicate alerts;
- restart-safe seen-state — the seen-state survives a process
  restart before any 24h soak begins;
- disk budget guardrails — soft and hard disk thresholds gate
  writes (Section 5);
- no public routing — the run never routes to any public audience;
- no enforcement by default — Stage 26 / Stage 29 enforcement stays
  inactive;
- filters observe-only unless later promoted — any filter is
  observe-only until a separate stage explicitly promotes it;
- operator kill switch — the operator can stop the run at any time
  through a documented kill switch.

A run that does not satisfy every clause above is NOT considered
safe to leave running 24/7.

## 3. Storage lifecycle tiers

Stage 30.6 pins a four-tier lifecycle-tier storage model, NOT a
simple time-only storage model. Hot writes and durable writes are
split: raw events are temporary, aggregates are durable. The four
tiers are `TIER_0_WAL_BUFFER`, `TIER_1_HOT_RAW`,
`TIER_2_DURABLE_TOKEN_SUMMARY`, and `TIER_3_SEALED_ARCHIVE`.

### 3.1 Tier 0 / WAL buffer

- a short-lived rotating raw buffer;
- holds only the last N files or roughly the last ~10 minutes;
- not durable history;
- safe to delete at any time;
- used for crash / replay / debug only.

### 3.2 Tier 1 / Hot raw

- short-lived raw per-event / per-sample evidence for fresh tokens;
- retention target around 24-48h;
- day-rolled or mint-scoped chunks;
- the raw stream is not kept forever.

### 3.3 Tier 2 / Durable token summary

- one evolving aggregate per mint / session;
- durable but compact;
- keeps peak MC, current MC, ATH when available, migration status,
  pings sent, tiers hit, LP, trade / event counts, timestamps,
  source statuses, and outcome pointers;
- carries no raw provider payloads.

### 3.4 Tier 3 / Sealed archive

- after a token lifecycle completes / dies / goes stale, seal it
  into an immutable compact summary;
- compress the evidence bundle with zstd where applicable;
- the raw stream is eligible for deletion after seal;
- daily archive files are preferred.

## 4. Dedupe and session persistence

Stage 30.6 locks (does not yet implement) the following dedupe
contract:

- no repeated first ping for the same mint in the same session;
- no repeated same tier for the same mint;
- ping again only on a meaningful state change, drawn from this
  closed set:
  - a new tier (`NEW_TIER`);
  - Mig Unknown -> Known / Unverified
    (`MIG_UNKNOWN_TO_KNOWN_OR_UNVERIFIED`);
  - ATH Unknown -> Known (`ATH_UNKNOWN_TO_KNOWN`) — gated on Stage
    30.7 shipping ATH; the trigger is reserved here, not active;
  - a material drawdown / tier transition
    (`MATERIAL_DRAWDOWN_OR_TIER_TRANSITION`);
  - an operator-approved re-alert condition
    (`OPERATOR_APPROVED_REALERT`).

Restart safety. The dedupe / session seen-state must be restart-safe
before any 24h soak: a restart must not re-emit a ping that was
already sent for the same mint + state class. The Stage 29.4 cross-
pass dedupe index is in-memory only and does NOT survive a restart;
Stage 30.6 closes that gap with a persisted seen-state (the Stage
22.2 append-only JSONL dedupe-ledger replay pattern is the reuse
candidate).

Dedupe key. The dedupe key must include the mint plus an
alert / tier / state class plus a policy-version / session-scope
axis as appropriate, so that a policy change or a new session can
intentionally re-alert without defeating in-session suppression.

## 5. Disk budget guardrails

Stage 30.6 requires disk-budget guardrails before any long soak:

- a soft disk alarm around 65% disk used fires a private operator
  warning;
- a hard stop around 90% disk used refuses new writes;
- a full disk never produces a weird crash — writes fail closed
  with a private operator warning rather than raising an unhandled
  error;
- the storage budget is visible in the per-run storage summary
  (Section 8);
- prune is not the first line of defense — the soft alarm and the
  fail-closed hard stop come first; pruning is a later, separate
  recovery action.

## 6. Day rolling and archive compression

Stage 30.6 requires day rolling and archive compression:

- day-rolling files for artifacts and logs;
- zstd compression for older archives where applicable;
- no single giant forever-growing file;
- archives are compressed or deleted by date or by lifecycle seal,
  never accumulated without bound.

Stage 30.6.0 names zstd only as a documented design target. Stage
30.6.0 adds no zstd dependency and no zstd implementation; a real
compression step, if any, lands in a later separately authorized
substage.

## 7. Database anti-bloat

Stage 30.6 requires main-database anti-bloat:

- no raw per-trade / per-event rows are kept forever in the main
  database;
- the main database stores only compact durable summaries, dedupe
  state, the ping ledger, and sealed lifecycle summaries;
- raw event payloads belong in short-lived files or compressed
  archives, not in unbounded database tables;
- future migrations must include size / retention expectations.

This is the direct countermeasure to the legacy PHX1-style giant DB
accumulation: the durable database is a compact aggregate store, and
the high-volume raw stream lives in rotating / sealed files instead.

## 8. Observability and per-run storage summary

Stage 30.6 requires a per-run storage summary on every long soak,
carrying:

- raw bytes written;
- durable rows written;
- archived / compressed bytes;
- dropped / pruned / sealed counts;
- dedupe suppressed counts;
- disk usage before and after the run.

Stage 30.6 also requires that a redaction scan runs before any
archive proof is considered safe, and that the run surfaces
operator-visible warnings (soft-alarm, hard-stop, fail-closed) so a
silent storage problem can never hide during a long soak.

## 9. Prior art and reuse

Stage 30.6 builds on existing PHX2 storage / dedupe primitives
rather than inventing new ones:

- the Stage 22.2 append-only JSONL dedupe ledger with cross-run
  replay (restart-safe seen / dispatched state) is the reuse
  candidate for the persisted dedupe / session seen-state;
- the Stage 22.3 append-only JSONL raw-capture writer (sanitized
  per-event evidence) is the reuse candidate for the Tier 1 hot-raw
  stream;
- the Stage 29.4 soak summary (rolled-up safe counters) is the reuse
  candidate for the per-run storage summary shape;
- the Stage 29.4 in-memory cross-pass dedupe index documents the
  exact restart-unsafe gap Stage 30.6 must close;
- the existing durable database is the reuse candidate for the
  compact Tier 2 summary store, under the anti-bloat rules of
  Section 7.

Each reuse is documented here as a design target only; Stage 30.6.0
imports none of these modules and changes none of them.

## 10. Non-goals

Stage 30.6.0 explicitly does NOT:

- implement a storage writer;
- implement a dedupe engine;
- run live;
- send Discord;
- add ATH;
- add filters;
- add enforcement;
- add public routing;
- add trading / wallet logic;
- add a zstd dependency (the word `zstd` appears in docs and tests
  only; no module import and no implementation ships).

## 11. Future slices

Stage 30.6 is sequenced fake / offline before live, smallest
reversible slice first:

- Stage 30.6.0 — storage + dedupe spec lock + manifest + pin test
  only (this commit). No production `.py` beyond the manifest.
- Stage 30.6.1 — storage budget models + pure policy evaluator.
- Stage 30.6.2 — rotating WAL / day-rolled artifact writer scaffold.
- Stage 30.6.3 — dedupe / session ledger scaffold.
- Stage 30.6.4 — lifecycle seal aggregate contract.
- Stage 30.6.5 — storage / dedupe offline integration proof.
- Stage 30.7 — ATH context bridge, after the storage / dedupe spec
  is locked.

ATH context is Stage 30.7. Stage 30.6.0 does not implement ATH. No
ATH mapping, no ATH basis, and no ATH storage column ships in any
Stage 30.6 storage slice; the `ATH_UNKNOWN_TO_KNOWN` re-alert
trigger is reserved in Section 4 but stays inactive until Stage 30.7
ships ATH.

## 12. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage
30.4.4 / 30.5.0 records. It carries no provider credential strings,
no private transport destination strings, no provider host address
strings, no transport scheme prefixes, no raw request-payload or
response-payload field names, and no request auth-metadata strings.
It records only closed-set tokens, field names, thresholds, prose,
and safe design labels.

The Stage 30.6.0 pin test enforces this by scanning this document,
the manifest, and the test, case-insensitively, against a split-
literal forbidden-substring vocabulary, so none of the three files
can carry any of the sanitized-away substrings even inside a
negative claim.

---

_Stage 30.6.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.6.0
  implementation.
- There is no Discord send during Stage 30.6.0 implementation.
- There is no candidate scan during Stage 30.6.0 implementation.
- There is no storage writer, no dedupe engine, no database
  migration, and no filesystem writer at Stage 30.6.0.
- There is no zstd dependency and no zstd implementation added at
  Stage 30.6.0.
- There is no runtime logic change and no Stage 27 / 28 / 29
  production change at Stage 30.6.0.
- There is no Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 runtime change
  at Stage 30.6.0.
- There is no ATH implementation at Stage 30.6.0.
- There is no filter and no enforcement added or activated at Stage
  30.6.0.
- There is no commit, no tag, and no push performed by Stage 30.6.0
  implementation. Commit gating is a separate operator decision
  after audit.
