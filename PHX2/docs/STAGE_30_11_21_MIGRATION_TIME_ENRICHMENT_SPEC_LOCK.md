# Stage 30.11.21 — Migration-Time Enrichment Adapter (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.21: enrich harvested facts with migration time`

**Status:** committed, offline / fakes-only, **no real send**. The real Stage 29.5
migration evidence (the operator wraps the committed Stage 29.5 reader behind the
injected Stage 30.11.9 provider seam), the real-fed dry-run ceremony, and the
controlled capped private send remain a SEPARATE, explicitly operator-authorized,
**ceremony-injected** step that is **not** built or run by this stage.

---

## 1. Purpose

Close the **last** hand-fed harvested-facts blocker the Stage 30.11.18 contract
exposed (`REJECTED_MIGRATION_NOT_CONFIRMED` / `REJECTED_MISSING_MIGRATION_TIME_UTC` /
`REJECTED_INVALID_MIGRATION_TIME_UTC`) by **reusing** the already-committed Stage
30.11.8 migration-confirmation authority — **no new fetcher is built and no bare
timestamp is copied**. The Stage 30.11.6 harvest carries no migration anchor, so
before this seam every real harvested fact had to hand-feed `migration_time_utc` (and
assert `migration_confirmed`). Given a base `Stage30_11_18HarvestedCandidateFacts` and
an **injected, duck-typed** migration evidence source, resolve the migration verdict
through the committed confirmation and, **only on a confirmed resolution**, fill the
three migration fields and run the enriched facts through the committed Stage 30.11.20
/ 30.11.19 / 30.11.18 / 30.11.17 chain:

```
base harvested facts (migration_time_utc = placeholder, migration_confirmed = False)
  → enrich_facts_with_migration_time(base, evidence_source=…)         # Layer-0'''
      → resolve_candidate_migration(base, evidence_source)            # COMMITTED 30.11.8
          → evidence_source.lookup_migration_evidence(token_mint)     # COMMITTED 30.11.9 surface
      → CONFIRMED  → replace(base, migration_time_utc=resolution.migration_event_time_utc,
                             migration_confirmed=True,
                             migration_source=safe_gated(resolution.source_ref))
      → SKIPPED_*  → enriched_facts=None (NOT forwarded; no silent pass-through)
  → enriched facts ONLY
  → run_stage30_11_20_price_enriched_session(...)    # L0'' current price
  → run_stage30_11_19_enriched_session(...)          # L0' MC/LP/fetched-at bundle
  → run_stage30_11_18_curated_session(...)           # L1 projection
  → run_stage30_11_17_operator_curated_compose_session(...)   # L2 composer
  → ONE combined nested redaction-safe Stage30_11_21MigrationEnrichmentSessionReport
```

The migration verdict + anchor **already exist with the correct semantics**: the
committed Stage 30.11.8 `resolve_candidate_migration` returns a
`Stage30_11_8MigrationResolution` whose `migration_event_time_utc` is the **confirmed
migration anchor** (the post-migration moment the later ATH / drawdown step needs —
not an `observed_at`), bound **only** when the evidence is redaction-`SAFE`, an
on-chain `COMPLETE` reading, not stale, with a strict trailing-Z, calendar-valid
ISO-8601 UTC anchor. Stage 30.11.21 is the thin committed **mapper** from that
confirmed resolution onto the facts; the migration verdict stays the committed Stage
30.11.8 confirmation's to decide. This is **not a fake layer**: every COMPLETE / SAFE
/ staleness / anchor-validity check is the committed confirmation's, reused verbatim.

## 2. The locked contract

### 2.1 Input / output type, and the three enriched fields

- **Input = output type = `Stage30_11_18HarvestedCandidateFacts`.** Enrichment is a
  `dataclasses.replace` of **only** `migration_time_utc`, `migration_confirmed`, and
  `migration_source` on a COPY of the base fact.
- `migration_time_utc` ← `resolution.migration_event_time_utc` (the confirmed anchor).
- `migration_confirmed` ← `True` (**earned** via the committed confirmation, never
  passed through from the base; the base may assert `False`).
- `migration_source` ← the safe-gated `resolution.source_ref`, or `None` if it fails
  the safe-shape gate (so a present-but-unsafe provenance — a url / scheme — is
  dropped to `None` rather than written onto the facts).
- **`age_display` is carried through UNCHANGED and is NEVER derived.** Deriving an age
  needs `now − migration_time` clock arithmetic; this slice imports no clock /
  `datetime` and adds no new clock logic.
- **`current_price` and the Stage 30.11.19 market-context bundle**
  (`current_market_cap_usd` / `liquidity_usd` / `market_context_fetched_at_utc` /
  `market_context_status`) are carried through UNCHANGED (separate seams).

### 2.2 The duck-typed surface (the locked key decision — Path A)

The adapter **reuses** the committed Stage 30.11.8 `resolve_candidate_migration(base,
evidence_source)`, which calls **only**
`evidence_source.lookup_migration_evidence(token_mint)` — the surface the committed
Stage 30.11.9 mint-keyed evidence-source adapter already exposes — and returns a
`Stage30_11_8MigrationResolution` the adapter reads by attribute (`confirmed`,
`migration_event_time_utc`, `source_ref`, `reason`). The committed real evidence
source is injectable DIRECTLY (the operator wraps the committed Stage 29.5 reader
behind the Stage 30.11.9 provider seam, out-of-repo). The confirm decision + fail
reasons are mirrored BY VALUE (a manifest pin cross-checks them against Stage 30.11.8,
and the evidence-source method against the committed Stage 30.11.9 adapter); committed
Stage 30.11.21 production code imports **no Stage 21-29 module, no Stage 30.11.11
migration-anchored ATH source, no Stage 30.11.9 source module, and no real provider
transport**.

### 2.3 Fail-closed ladder (first failing check wins → that `SKIPPED_*`)

1. non-facts base → `SKIPPED_NOT_BASE_FACTS`
2. resolve the migration verdict via the committed Stage 30.11.8
   `resolve_candidate_migration` (never raises; always returns a resolution)
3. on an **UNCONFIRMED** resolution, fail closed to the `SKIPPED_*` token that
   **mirrors** the committed Stage 30.11.8 fail reason (`SKIPPED_<R>` carries reason
   `<R>`):
   - `SKIPPED_BLANK_CANDIDATE_MINT` · `SKIPPED_MISSING_MIGRATION_EVIDENCE` ·
     `SKIPPED_EVIDENCE_MINT_MISMATCH` · `SKIPPED_REDACTION_UNSAFE` ·
     `SKIPPED_UNKNOWN_MIGRATION` · `SKIPPED_PARTIAL_MIGRATION_UNVERIFIED` ·
     `SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION` ·
     `SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE` ·
     `SKIPPED_INVALID_MIGRATION_EVIDENCE` · `SKIPPED_STALE_MIGRATION_EVIDENCE` ·
     `SKIPPED_INVALID_MIGRATION_ANCHOR`
4. on a **CONFIRMED** resolution, a defensive re-check that the bound anchor is
   non-blank (the committed confirmation guarantees a strict trailing-Z anchor on
   confirm; a degenerate carrier → `SKIPPED_INVALID_MIGRATION_ANCHOR`)
5. all pass → `ENRICHED`

The COMPLETE / SAFE / staleness / strict-trailing-Z-anchor checks are **the committed
Stage 30.11.8 confirmation's** — this adapter re-implements none of them.

### 2.4 Skip behavior — no silent pass-through

`enrich_facts_with_migration_time(...) -> Stage30_11_21MigrationEnrichmentResult{
decision, enriched_facts}`. `enriched_facts` is the filled facts ONLY on `ENRICHED`;
on every `SKIPPED_*` it is `None`, the base fact is **not mutated and not forwarded**
to the Stage 30.11.20 session. The blocker is a visible `SKIPPED_*` count + event in
the report — surfacing the precise confirmation cause — not silently re-derived
downstream.

### 2.5 Four honest layers — 30.11.21 wraps 30.11.20

L0''' migration-time enrichment (this stage) → L0'' Stage 30.11.20 current-price
enrichment → L0' Stage 30.11.19 market-context enrichment → L1 Stage 30.11.18
projection → L2 Stage 30.11.13 composer. The wrap order is forced: each enrichment
runner internally drives the next, so composing without editing committed internals
means migration enrichment runs OUTERMOST. A `CONFIRMED` / `ENRICHED` fact can still
fail closed at 30.11.20 (e.g. `SKIPPED_PRICE_MISSING`), at 30.11.19 (e.g.
`SKIPPED_MISSING_LIQUIDITY_USD`), or be 30.11.18-`REJECTED` — that is expected and
shown in the embedded report. ONE combined nested report: the 30.11.21 report embeds
the 30.11.20 report, which embeds the 30.11.19 report, which embeds the 30.11.18
report, which embeds the 30.11.17 session result.

## 3. What this stage is NOT (hard exclusions)

- **No** new migration fetcher; **no** bare migration timestamp copy; **no** fake
  migration confirmation. The committed Stage 30.11.8 confirmation is **reused**, NOT
  edited or re-implemented.
- **No** Stage 21-29 import in committed production; **no** Stage 27 / Stage 28 /
  Stage 29 import; **no** **Stage 30.11.11** migration-anchored ATH source import (it
  drags Stage 27/29); **no** Stage 30.11.9 source module import; **no** real provider
  transport construction. The evidence source is **injected and read duck-typed**.
- **No** real send. The only transport is the injected committed Stage 30.11.5
  recording **fake** client. **No** call to / import of the Stage 30.11.16 real
  private transport guard.
- **No** `age_display` derivation; **no** clock / `datetime` / `re` import (the
  confirmation + anchor validation reuse the committed Stage 30.11.8 authority).
- **No** Discord / webhook call. No network, no env read, no wall-clock read.
- **No** wallet / signing / trading. **No** public / subscriber / paid routing.
- **No** renderer polish, **no** `while`/daemon loop, **no** background service.
- **No** mutation of the operator ceremony ledger at
  `C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl`. The ledger is always
  caller-injected; committed tests use an in-memory ledger.
- **No** edit of the committed confirmation / source / adapter / session / composer /
  renderer / tier-band internals (import of public symbols only).
- **No** commit/tag/push until operator approval.

## 4. Files

### Added (production — `PHX2/stage30/`)
- `stage30_11_21_migration_time_enrichment_models.py` — pure leaf models +
  closed-set Layer-0 decision vocabulary + duck-typed surface pins + redaction
  tokens + safe-shape predicates (imports **no** PHX2).
- `stage30_11_21_migration_time_enrichment_adapter.py` —
  `enrich_facts_with_migration_time(...)` +
  `run_stage30_11_21_migration_time_enriched_session(...)` + the committed-reason →
  `SKIPPED_*` mirror + the redaction self-scan.
- `stage30_11_21_fake_migration_time_enrichment_proof.py` — thin offline driver
  (defaults the in-memory ledger + recording fake client; the evidence source +
  price source + market-context source + fake ATH transport are injected).

### Added (docs)
- `PHX2/docs/STAGE_30_11_21_MIGRATION_TIME_ENRICHMENT_SPEC_LOCK.md` (this).

### Added (tests — `PHX2/tests/stage30/`)
- `test_stage_30_11_21_migration_time_enrichment_adapter.py`
- `test_stage_30_11_21_fake_migration_time_enrichment_proof.py`
- `test_stage_30_11_21_boundaries.py`
- `test_stage_30_11_21_manifest.py`

### Updated
- `PHX2/stage30/stage30_11_manifest.py` — Stage 30.11.21 manifest section +
  `__all__` exports only (constants mirrored BY VALUE).
- `PHX2/tests/stage30/test_stage_30_0_spec_lock.py`,
  `test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py`,
  `test_stage_30_11_5_boundaries.py`,
  `test_stage_30_9_0_bounded_private_live_compact_spec_lock.py` — the four Stage
  30.11 admission guards, extended **additively** (future-token guard 21→22; the
  Stage 30.11.5-leaf successor allowlist gains the Stage 30.11.21 basenames because
  the fake proof composes the committed Stage 30.11.5 recording client). The same
  bookkeeping as every prior Stage 30.11.x slice; no logic changed.

### Reuse / import-only (NOT edited)
- `stage30_11_8_migration_confirmation_adapter.py` (`resolve_candidate_migration`) —
  the committed migration-confirmation authority.
- `stage30_11_8_migration_confirmation_models.py` (`CONFIRM_REASON_*`) — the
  fail-reason tokens mirrored onto the `SKIPPED_*` vocabulary.
- `stage30_11_20_current_price_enrichment_adapter.py`
  (`run_stage30_11_20_price_enriched_session`)
- `stage30_11_18_harvested_facts_models.py` (`Stage30_11_18HarvestedCandidateFacts`)
- `stage30_11_17_operator_curated_candidate_list_models.py` (`Stage30_11_17SessionConfig`,
  `is_within_session_caps`, `default_session_config`)
- `stage30_11_15_ping_dedupe_ledger.py` (`InMemoryPingDedupeLedger`)
- `stage30_11_5_fake_live_wiring_proof.py` (`Stage30_11_5RecordingFakeTransportClient`)
- `stage30_11_9_migration_evidence_source_adapter.py` (the evidence source the proof
  test + ceremony construct over an injected provider; committed Stage 30.11.21
  imports it NOT at all)

## 5. Model / API shape

- `Stage30_11_21MigrationEnrichmentResult{ decision: str, enriched_facts: Any }`
- `Stage30_11_21MigrationEnrichmentEvent{ index, decision, candidate_id, token_mint,
  created_at_utc }`  (redaction-safe; no migration anchor / provenance — the confirmed
  anchor goes ONLY into the facts copy, never into an event)
- `Stage30_11_21MigrationEnrichmentSessionReport{ enrichment_events, facts_seen,
  enriched, skipped, downstream_report, redaction_status, created_at_utc }`
- `enrich_facts_with_migration_time(base_facts, *, evidence_source) ->
  Stage30_11_21MigrationEnrichmentResult`
- `run_stage30_11_21_migration_time_enriched_session(base_facts, *, evidence_source,
  price_source, market_context_source, config, ledger, ath_transport,
  ath_endpoint_secret, now_utc, transport_client, now_seconds, ath_timeout_seconds=10,
  market_context_max_age_seconds=None, ttl_seconds=None) ->
  Stage30_11_21MigrationEnrichmentSessionReport`

## 6. Bounds + defaults

- Dry / no-send only (fake recording client).
- Scans AT MOST `config.max_candidates` base facts (`<= 10`, mirrors the committed
  Stage 30.11.17 session caps); an out-of-cap config raises
  `Stage30_11_21MigrationTimeEnrichmentError` before any fact is scanned (the
  evidence source is never consulted).
- ONE shared injected ledger across the downstream session chain (in-memory in
  tests).
- Single bounded `for` loop; no `while`; no daemon.
- Combined `redaction_status == REDACTED` iff the Layer-0 enrichment events AND the
  embedded Stage 30.11.20 report are both redacted; an unsafe id is redacted to
  `REDACTED_UNSAFE_ID`; no migration anchor / provenance / magnitude / body / url /
  secret is ever carried in an event.

## 7. Layer-0 decision vocabulary (closed set, 13 tokens)

`ENRICHED` · `SKIPPED_NOT_BASE_FACTS` · `SKIPPED_BLANK_CANDIDATE_MINT` ·
`SKIPPED_MISSING_MIGRATION_EVIDENCE` · `SKIPPED_EVIDENCE_MINT_MISMATCH` ·
`SKIPPED_REDACTION_UNSAFE` · `SKIPPED_UNKNOWN_MIGRATION` ·
`SKIPPED_PARTIAL_MIGRATION_UNVERIFIED` · `SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION` ·
`SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE` · `SKIPPED_INVALID_MIGRATION_EVIDENCE` ·
`SKIPPED_STALE_MIGRATION_EVIDENCE` · `SKIPPED_INVALID_MIGRATION_ANCHOR`.

The eleven evidence/anchor `SKIPPED_*` tokens mirror the committed Stage 30.11.8
fail-closed reasons BY VALUE (manifest pin cross-checked).

## 8. Test obligations (proven)

- happy path: a CONFIRMED resolution overwrites ONLY the three migration fields
  (`migration_time_utc` from the confirmed anchor; `migration_confirmed` earned to
  `True`; `migration_source` = safe-gated `source_ref`); the price + market bundle +
  `age_display` + every other field carried unchanged; the base fact is never
  mutated; the fact mint is passed to the evidence source.
- every `SKIPPED_*` token: one evidence/base per token, mirroring each committed
  Stage 30.11.8 fail reason (incl. `EVIDENCE_MINT_MISMATCH` via a directly-injected
  wrong-mint evidence that bypasses the Stage 30.11.9 mint-binding); first-failing
  check wins; `enriched_facts is None`; a present-but-unsafe `source_ref` is dropped
  to `None` on confirm.
- out-of-cap config raises before any fact is scanned (evidence source never called).
- end-to-end fake proof: the COMMITTED Stage 30.11.9 source over a FAKE record
  provider + the REAL Stage 29.2 price source + Stage 30.4.3 market-context source
  over a FAKE Birdeye transport confirm + fill the `migration_time_utc=""` placeholder
  and the fact flows ENRICHED → (30.11.20) ENRICHED → (30.11.19) ENRICHED →
  (30.11.18) PROJECTED → DISPATCHED to a RECORDED would-send; a missing / stale
  migration → the precise `SKIPPED_*`, NOT forwarded (the embedded chain sees
  nothing, zero would-sends); a confirmed migration with a value-less price body
  fails closed at the committed Stage 30.11.20 layer (chain order proven); the ONE
  shared ledger blocks the in-run and cross-run duplicate; the scan is bounded at the
  candidate cap.
- boundary scan over the three production modules: no Stage 21-29 import (incl. no
  Stage 27 / 29 / Birdeye), no Stage 30.11.11 ATH-source import, no Stage 30.11.16
  guard import; no live-provider / secret / transport / url needle; no env read, no
  filesystem write, no `while` / daemon, no top-level call; only `__future__` /
  `typing` / `dataclasses` stdlib.
- manifest mirrors all constants BY VALUE; the confirm decision cross-checks against
  the committed Stage 30.11.8 `CONFIRM_DECISION_CONFIRMED`; the eleven `SKIPPED_*`
  evidence tokens mirror the committed Stage 30.11.8 `STAGE30_11_8_FAIL_CLOSED_REASONS`
  exactly; the resolution attrs are a subset of the committed Stage 30.11.8 resolution
  fields; the evidence-source method exists on the committed Stage 30.11.9 adapter;
  the enriched migration fields are exactly the three migration fields, disjoint from
  the Stage 30.11.20 price field + the Stage 30.11.19 market bundle; the spec-lock doc
  exists.

## 9. Next allowed step

`operator-authorized real-fed dry-run ceremony + capped private send (separate
steps)`. Stage 30.11.21 ships no part of them. With the migration-time seam landed,
the **harvested-facts enrichment chain is complete** — a real harvested candidate now
needs **zero** hand-fed market / migration fields (only identity + the caller
`created_at_utc`). The real-fed dry-run ceremony (real harvest + real migration
evidence + real price + real market context over the FAKE recording client) becomes
possible, and a real capped send would compose an `ENRICHED → … → DISPATCHED` result
through the SEPARATE Stage 30.11.16 real-send guard with a real audited transport + a
valid operator-auth sentinel — an explicit, separately-authorized ceremony, not this
stage.
