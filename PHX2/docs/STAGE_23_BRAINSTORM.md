# PHX2 Stage 23 — Brainstorm & Planning (Stage 23.0)

**Status:** planning document only. No production code, no tests, no roadmap edits.
**Predecessors (closed/tagged):** `stage-20-closed`, `stage-21-closed`, `stage-22-closed`.
**Stage 22 closure commit:** `9647f8eb94204203d2d8ef1da035e3bc5ed28b5d`.
**Stage 22 live proof:** Discord-only smoke OK; Helius RPC 200/ok; private smoke produced `helius_events: 1` + dispatch; bounded runner returned `outcome='ok'` with 1 received / 1 normalized / 0 malformed / 1 new / 1 dispatched / 0 transport_refused / 1 provider attempt (`helius`); artifacts written outside repo and verified clean of secrets.

---

## 1. Stage 23 Mission

Stage 23 is the **first clean PHX2 filter rebuild/import stage** after live ingestion hardening.

- **Observe-only.** Evaluates and labels; never blocks, routes, or monetizes.
- Creates a **stable filter-evaluation surface** that downstream stages can build on.
- Does not enforce. Does not gate ingestion. Does not select audience.
- Whether any specific label is *useful* is a Stage 26+ question. Stage 23 only produces the evidence.

The job of Stage 23 is to take Stage 22-shaped events and emit deterministic, redacted, hashed filter evaluations to disk. Nothing more.

---

## 2. Locked Boundaries — DO NOT include in Stage 23

Stage 23 must **not** include:

- **ATH / migration measurement hardening** — deferred to **Stage 25**.
- **Axiom / global fee / Jito tip / priority fee / compute-budget / execution-quality work** — deferred to **Stage 24**.
- **X API / social ranking / social intelligence sidecar** — deferred to **Stage 27+**.
- **Calibration / enforcement candidates / threshold tuning for action** — deferred to **Stage 26**.
- **Public / subscriber routing** of evaluations.
- **Broad live architecture rewrites** of the Stage 22 ingest path.
- **Stage 21 / Stage 22 contract edits**, unless absolutely necessary and separately justified in writing. Stage 23 reads Stage 22 artifacts; it does not modify Stage 21/22 modules.
- **Enforcement / blocking** of any kind.
- **Reading env vars** from inside Stage 23 modules.
- **Network calls** of any kind from Stage 23 modules.

If a feature is tempting but lives in the list above, write it down for the corresponding later stage and leave Stage 23 alone.

---

## 3. Candidate Filter Families

Three observe-only families are in scope for Stage 23. Each family is a *folder of labels*, not a single boolean.

### A. Holder Concentration (`HOLDER_CONCENTRATION`)

Deterministic, snapshot-based. Examples:

- Top-1 holder concentration (% supply).
- Top-10 / Top-20 / Top-50 concentration.
- Holder breadth / unique owner count.
- Creator / dev / early-buyer retained concentration.
- Pool-related concentration (LP wallet vs non-LP wallet share).
- Source-related concentration (clustered funding source share).
- **Missing holder snapshot handling** — must emit `INSUFFICIENT_DATA` / `MISSING_INPUT`, not silently zero out.

### B. Launch Structure / Ante-style Bundle-like Signals (`LAUNCH_STRUCTURE`)

Pattern signals on the first slots/blocks of a token's life. Examples:

- Same-slot or near-slot buyer clustering.
- First-N-holder concentration at launch.
- First-N-source concentration at launch.
- Launch-window wallet clustering (small wallet set acquiring large share quickly).
- Repeated source wallets across the first N buys.
- Bundle-like launch pattern labels (heuristic only).
- **Do not claim Ante parity.** Stage 23 emits *labels*, not "this is an Ante bundle." Parity claims require Stage 26-level calibration plus ground-truth comparison and are out of scope here.

### C. Wallet / Source Quality / Provenance (`WALLET_SOURCE_QUALITY`)

Per-wallet provenance signals on the early flow. Examples:

- Fresh-wallet density (share of early buyers with near-zero age).
- Wallet age distribution / source-quality histogram.
- Funding-source links (CEX deposit, known mixer, common funder).
- Dev / source wallet quality signals.
- Repeated source wallets in early flow (overlap with B).
- "Manufactured vs organic-looking early flow" label.
- **Honestly mark unsupported / missing primitives.** If wallet age or funding-trace primitives are not available, emit `UNSUPPORTED` or `MISSING` rather than fabricating a score.

---

## 4. Recommended Stage Breakdown

| Sub-stage | Scope |
|-----------|-------|
| **23.1** | Contracts, constants, closed sets, immutable models, input reader, manifest scaffolding. No filter logic yet. |
| **23.2** | Holder concentration observe-only filter. Synthetic fixtures only. |
| **23.3** | Launch structure / bundle-like observe-only filter. Synthetic fixtures. |
| **23.4** | Wallet / source-quality observe-only surface. Heavy use of `UNSUPPORTED` until primitives exist. |
| **23.5** | Unified observe-only runner + artifact writer (`stage23_filter_evaluations.jsonl`, summary CSVs, manifest). |
| **23.6** | Closure audit + Stage 24 handoff doc. Tag `stage-23-closed`. |

Each sub-stage is a bounded, reviewable patch with its own tests, mirroring Stage 22's discipline.

---

## 5. Why Holder Concentration Comes First (23.2)

Holder concentration is the right first filter because:

1. **It is deterministic.** Given a holder snapshot, the label is a pure function of the snapshot. No clock, no network, no provider drift.
2. **It is easy to fixture.** Synthetic holder lists are trivial JSON. No need to record a live mainnet snapshot to test it.
3. **It does not require Stage 24 primitives.** No fees, no Jito, no Axiom, no priority-fee semantics.
4. **It degrades gracefully.** Even with partial data (e.g., only top-50), it can emit a useful label with `data_status=PARTIAL`.
5. **It exercises the whole pipeline.** Input reader → filter eval → label → artifact writer. Once 23.2 lands, 23.3 and 23.4 are mostly *more filters* on the same surface.

In short: it is the **cheapest path to proving the surface is correct**.

---

## 6. Proposed Schemas / Models (names only, no implementation)

Minimal immutable model surface for 23.1 to define:

- `Stage23FilterInput` — normalized input snapshot for one event/token.
- `Stage23FilterResult` — one filter's verdict on one input.
- `Stage23FilterEvaluation` — wrapper bundling input ref + result + hashes + timestamps.
- `Stage23InputManifest` — manifest of which Stage 22 artifact files / fixtures fed a run.
- `Stage23ArtifactManifest` — manifest of which Stage 23 artifacts a run wrote.
- `Stage23FilterFamily` — closed-set enum (see §7).

### Required concepts every evaluation must carry

- `token_mint`
- `provider_id`
- `event_id` (or `captured_event_id`)
- `observed_at_utc`
- `filter_name`
- `filter_family`
- `filter_version`
- `threshold_version`
- `label` (closed set, §7)
- `data_status` (closed set, §7)
- `reason_codes` (list of short codes explaining the label)
- `numeric_features` (map of computed numerics, redacted-safe)
- `missing_features` (list of inputs that were absent)
- `input_hash` (deterministic hash of the canonicalized input)
- `evaluation_hash` (deterministic hash of the result body)
- `created_at_utc` (injectable clock for tests)

All models immutable. All hashing deterministic (sorted keys, canonical JSON).

---

## 7. Closed Sets

These are normative for Stage 23. New values require a contract patch.

### `label`

- `NORMAL`
- `ELEVATED`
- `SUSPICIOUS`
- `SCAM_LIKELY`
- `UNKNOWN`
- `INSUFFICIENT_DATA`
- `MISSING_INPUT`

### `data_status`

- `COMPLETE`
- `PARTIAL`
- `MISSING`
- `UNSUPPORTED`

### `filter_family`

- `HOLDER_CONCENTRATION`
- `LAUNCH_STRUCTURE`
- `WALLET_SOURCE_QUALITY`

Constants module must export these as frozen sets and a closed-set test must assert no drift.

---

## 8. Input Strategy

Stage 23 consumes **Stage 22-shaped artifacts** wherever possible. Useful fields:

- `raw_capture.jsonl` lines (per-provider captured payloads).
- `dedupe.jsonl` lines (dedupe-ledger view).
- `provider_id`.
- `event_id` / dedupe key.
- `token_mint` if present.
- `slot` / `signature` / log references if present.
- `observed_at` / `received_at` timestamps.
- Normalized payload summary if present.

### Stage 23.0 ground rules for inputs

- **No hardcoded live-smoke path.** Tests/fixtures live under the Stage 23 fixtures tree, not under `C:\Users\BalaC\Documents\phx2_scratch\...`.
- **No live provider calls** from Stage 23 modules. Ever.
- **No network calls.**
- **No env reads** inside Stage 23 modules. If a path is needed at runtime, the caller (a separate runner harness) supplies it.
- **Synthetic fixtures first.** Stage 23.2/23.3/23.4 are built and tested against deterministic fixtures.
- **Real Stage 22 artifacts later**, for an offline smoke pass in 23.5 — reading the on-disk JSONL from a prior Stage 22 run, *not* triggering Stage 22 from Stage 23.

---

## 9. Missing Primitive Policy

Stage 23 is honest about what it does and does not know.

**DO:**
- Emit `UNKNOWN` when the filter cannot produce a verdict.
- Emit `MISSING_INPUT` when a required input field is absent.
- Emit `INSUFFICIENT_DATA` when present-but-incomplete input can't support a label (e.g., 5 holders observed when top-50 is needed).
- Mark `data_status=UNSUPPORTED` when the primitive itself isn't implemented yet (e.g., wallet-age lookups in 23.4).
- Always populate `reason_codes` explaining *what* was missing and *why* the label is what it is.
- Still produce a deterministic `Stage23FilterEvaluation` for partial inputs — partial does not mean skip.

**DO NOT:**
- Invent confidence numbers.
- Substitute zeros for missing values.
- Silently drop events without an evaluation record.
- Use `NORMAL` as a default for "we don't know."

---

## 10. Test Strategy (mandatory for future sub-stages, NOT for 23.0)

Stage 23.0 ships no tests. The list below is the contract for 23.1+.

- Constants closed-set tests (no drift in labels / data_status / families).
- Immutable model tests (dataclass/pydantic frozen, no setattr).
- Input reader malformed JSONL tests (skip-with-reason, never crash).
- Secret-leak / redaction tests (no Helius key, no RPC URL, no Discord webhook, no env values ever appear in artifacts).
- Deterministic hashing tests (same input → same `input_hash` / `evaluation_hash`).
- Artifact writer deterministic ordering tests (stable sort keys, stable JSON serialization).
- No-env-read tests (static-import scan / runtime guard for `os.environ` usage in Stage 23 modules).
- No-network-call tests (static-import scan / runtime guard for `requests`, `httpx`, `urllib`, sockets in Stage 23 modules).
- No-Stage-21/22-mutation tests (Stage 23 modules must not import-and-write Stage 21/22 ledgers).
- No-ATH / Birdeye / Dexscreener import tests.
- No-Axiom / Jito / priority-fee / global-fee import tests.
- No-X / social import tests.
- No-Discord / TG / public-routing import tests.
- Missing-primitive behavior tests (each family handles `MISSING` / `UNSUPPORTED` / `PARTIAL` deterministically).
- Duplicate / idempotency tests (same event evaluated twice yields the same evaluation; no double-write).

---

## 11. Artifact Strategy

Stage 23 writes to a Stage 23 artifact directory **supplied by the caller**, never to a hardcoded path. Proposed files:

- `stage23_filter_evaluations.jsonl` — one line per `Stage23FilterEvaluation`. Sorted by `(token_mint, filter_family, filter_name, evaluation_hash)`.
- `stage23_filter_summary.csv` — per-(filter_family, filter_name, label) counts for a run.
- `stage23_reason_code_counts.csv` — per-reason-code counts for a run.
- `stage23_manifest.json` — combined input + artifact manifest, run metadata, filter versions, threshold versions, redaction confirmation.

All artifacts must pass the redaction tests in §10. No secret, key, URL, webhook, or env value may appear.

---

## 12. Stage 24 Handoff Preview

Stage 24 picks up **execution-fee and execution-quality primitives**:

- Axiom / global fee amount.
- Priority fee.
- Jito tip.
- Compute-budget settings.
- Execution-quality / inclusion-quality measurements.

Stage 23 must **not** implement any of these. The only acceptable Stage 23 touchpoint is to reserve **deferred reason codes** or **`UNSUPPORTED` `data_status`** entries where a Stage 24 primitive would later upgrade an evaluation from `UNKNOWN` to a concrete label. No fee math, no Jito client, no Axiom client in Stage 23.

---

## 13. Stage 25 / 26 / 27 Deferrals

- **Stage 25** — ATH / migration measurement hardening. (Not Stage 23.)
- **Stage 26** — Calibration / enforcement candidates. Decides which Stage 23 labels become actionable thresholds and which families to actually act on.
- **Stage 27+** — X / social intelligence sidecar. Independent input source, never mixed into Stage 23.

Stage 23 emits the evidence. Stages 26+ decide what to do with it.

---

## 14. Output Format & Anti-Goals

**Format guidance for future Stage 23 docs and code:**
- Practical and implementation-ready, not aspirational.
- Headings, bullets, explicit **DO / DO NOT** sections.
- Closed sets first, behavior second, implementation last.

**Anti-goals for Stage 23 (repeat for emphasis):**
- Stage 23 is **not** ATH.
- Stage 23 is **not** Axiom / fee / Jito work.
- Stage 23 is **not** X / social intelligence.
- Stage 23 is **not** monetization.
- Stage 23 is **not** subscriber routing.
- Stage 23 is **not** enforcement.
- Stage 23 does **not** rewrite the roadmap.
- Stage 23 does **not** edit Stage 21 / Stage 22 modules.

---

## Appendix A — Open Questions for Stage 23.1

Resolve these before 23.1 starts coding:

1. Final concrete path layout under `PHX2/stage23/` (mirror Stage 22's structure?).
2. Whether `Stage23FilterInput` is per-event or per-(token_mint, slot-window). Likely per-event for 23.2, with a token-window adapter for 23.3.
3. Canonical JSON serialization choice (sorted keys + UTF-8; confirm Stage 22's existing helper is reusable as a read-only import).
4. Clock injection convention (Stage 22 pattern vs new convention).
5. Whether Stage 23 reuses Stage 22's redaction helper as a read-only import, or duplicates a Stage 23-local copy to keep Stage 22 untouched.
6. Fixture directory location and whether fixtures ship with the repo (recommend: yes, small synthetic JSON only, no captured live payloads).
