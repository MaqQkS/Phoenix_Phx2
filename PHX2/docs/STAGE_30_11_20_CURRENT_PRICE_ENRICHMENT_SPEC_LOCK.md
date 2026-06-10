# Stage 30.11.20 — Current-Price Enrichment Adapter (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.20: enrich harvested facts with current price`

**Status:** committed, offline / fakes-only, **no real send**. The real
`/defi/price` read (the operator constructs the committed Stage 29.2 price source
over a real transport + secret), the real-fed dry-run ceremony, and the controlled
live send remain a SEPARATE, explicitly operator-authorized, **ceremony-injected**
step that is **not** built or run by this stage.

---

## 1. Purpose

Close the `current_price` blocker the Stage 30.11.18 contract exposed
(`REJECTED_MISSING_CURRENT_PRICE` / `REJECTED_INVALID_CURRENT_PRICE`) by
**reusing** the already-committed, live-proven Stage 29.2 Birdeye `/defi/price`
price source — **no new fetcher is built and no read() shim is forced**. The
Stage 30.11.6 harvest carries no price field, so before this seam every real
harvested fact had to hand-feed `current_price` (the Stage 30.11.19 proof
literally hand-feeds `PROOF_CURRENT_PRICE`). Given a base
`Stage30_11_18HarvestedCandidateFacts` and an **injected, duck-typed** price
source, overwrite ONLY `current_price` and run the enriched facts through the
committed Stage 30.11.19 / 30.11.18 / 30.11.17 chain:

```
base harvested facts (current_price = placeholder)
  → enrich_facts_with_current_price(base, price_source=…)            # Layer-0''
      → price_source.fetch_snapshot(base_mint=token_mint)            # NATIVE surface
      → ENRICHED   → replace(base, current_price=snapshot.price_value)
      → SKIPPED_*  → enriched_facts=None (NOT forwarded; no silent pass-through)
  → enriched facts ONLY
  → run_stage30_11_19_enriched_session(...)    # Layer-0' MC/LP/fetched-at bundle
  → run_stage30_11_18_curated_session(...)     # Layer-1 projection
  → run_stage30_11_17_operator_curated_compose_session(...)   # Layer-2 composer
  → ONE combined nested redaction-safe Stage30_11_20PriceEnrichmentSessionReport
```

A committed price source already exists: `Stage29_2BirdeyePriceSource` (Birdeye
`/defi/price`) exposes the **never-raises** rich surface
`fetch_snapshot(*, base_mint) -> Stage29_2BirdeyePriceSnapshot` carrying
`price_value` (canonical decimal text, full sub-micro precision),
`birdeye_price_status` (`PRESENT` / `MISSING` / `SOURCE_ERROR`), and
`fetched_at_utc`. Stage 30.11.20 is the thin committed **mapper** from that
snapshot onto the facts; the live read stays ceremony-injected.

## 2. The locked contract

### 2.1 Input / output type, and the ONE enriched field

- **Input = output type = `Stage30_11_18HarvestedCandidateFacts`.** Enrichment is
  a `dataclasses.replace` of **only** `current_price` on a COPY of the base fact.
- **`market_context_fetched_at_utc` is NEVER overwritten.** The composer pins that
  field's semantics to "time the MC + LP snapshot was fetched" and its freshness
  bound covers MC + LP; the request has no price-timestamp field. The snapshot's
  own `fetched_at_utc` is validated for **reading coherence only** (presence +
  ISO shape) and written NOWHERE.
- **`migration_time_utc` is carried through UNCHANGED.** It is NEVER enriched here
  (the next separate seam).

### 2.2 The duck-typed surface (the locked key decision)

The adapter calls **only** `price_source.fetch_snapshot(base_mint=token_mint)` —
the NATIVE never-raises surface the committed Stage 29.2 price source already
exposes — and reads the snapshot by attribute (`price_value`,
`birdeye_price_status`, `fetched_at_utc`). **No read() shim** is forced on the
ceremony: the committed real price source is injectable DIRECTLY, zero shim, zero
fake layer. The Stage 27.4 `read_price_snapshot` protocol surface is deliberately
NOT used (it raises on SOURCE_ERROR and drags a `pair_quote_asset` Stage-27
concept into 30.11.x). The status tokens are mirrored BY VALUE (a manifest pin
test cross-checks them against Stage 29.2); committed Stage 30.11.20 production
code imports **no Stage 29 module**.

### 2.3 Fail-closed ladder (first failing check wins → that `SKIPPED_*`)

1. non-facts base → `SKIPPED_NOT_BASE_FACTS`
2. `fetch_snapshot(...)` returns `None` (or the source lacks a callable
   `fetch_snapshot`, or the call raises) → `SKIPPED_NO_PRICE_READING`
3. snapshot missing required attrs / wrong shape → `SKIPPED_NOT_A_PRICE_READING`
4. `birdeye_price_status == "SOURCE_ERROR"` → `SKIPPED_PRICE_SOURCE_ERROR`
5. `birdeye_price_status == "MISSING"` → `SKIPPED_PRICE_MISSING`
6. any other non-`PRESENT` status → `SKIPPED_PRICE_STATUS_UNRECOGNIZED`
7. missing/blank `price_value` → `SKIPPED_MISSING_PRICE_VALUE`
8. invalid / non-positive `price_value` (incl. literal `"0"` — a valid PRESENT
   reading at the source that can never dispatch) → `SKIPPED_INVALID_PRICE_VALUE`
9. missing `fetched_at_utc` → `SKIPPED_MISSING_PRICE_FETCHED_AT`
10. non-ISO-shape `fetched_at_utc` → `SKIPPED_INVALID_PRICE_FETCHED_AT`
11. all pass → `ENRICHED`

The positivity + ISO-shape checks REUSE the committed Stage 30.11.18 predicates
(`is_positive_decimal_text`, `is_iso_utc_shape`) — no decimal / datetime import.

### 2.4 Skip behavior — no silent pass-through

`enrich_facts_with_current_price(...) -> Stage30_11_20PriceEnrichmentResult{
decision, enriched_facts}`. `enriched_facts` is the filled facts ONLY on
`ENRICHED`; on every `SKIPPED_*` it is `None`, the base fact is **not mutated and
not forwarded** to the Stage 30.11.19 session. The blocker is a visible
`SKIPPED_*` count + event in the report — not silently re-derived downstream.

### 2.5 Four honest layers — 30.11.20 wraps 30.11.19

L0'' price enrichment (this stage) → L0' Stage 30.11.19 market-context enrichment
→ L1 Stage 30.11.18 projection → L2 Stage 30.11.13 composer. The wrap order is
forced: 30.11.19's runner internally drives 30.11.18 → 30.11.17, so composing
without editing committed internals means price enrichment runs OUTERMOST. An
`ENRICHED` fact can still fail closed at 30.11.19 (e.g.
`SKIPPED_MISSING_LIQUIDITY_USD`) or be Stage 30.11.18-`REJECTED` for the still
hand-fed `migration_time_utc` — that is expected and is shown in the embedded
report. ONE combined nested report: the 30.11.20 report embeds the 30.11.19
report, which embeds the 30.11.18 report, which embeds the 30.11.17 session
result.

## 3. What this stage is NOT (hard exclusions)

- **No** new price fetcher (the Stage 29.2 price source is reused, NOT edited or
  re-implemented). **No** read() shim.
- **No** Stage 21-29 import in committed production; **no** Stage 29.2 price
  source import; **no** Stage 30.4.3 source import; **no** real provider
  transport construction. The price source is **injected and read duck-typed**
  (`source.fetch_snapshot(base_mint=...)` + attribute access).
- **No** real send. The only transport is the injected committed Stage 30.11.5
  recording **fake** client. **No** call to / import of the Stage 30.11.16 real
  private transport guard.
- **No** `migration_time_utc` enrichment. **No** `market_context_fetched_at_utc`
  overwrite.
- **No** Discord / webhook call. No network, no env read, no wall-clock read
  (clocks injected; the composer owns the Layer-2 freshness clock).
- **No** wallet / signing / trading. **No** public / subscriber / paid routing.
- **No** renderer polish, **no** `while`/daemon loop, **no** background service.
- **No** mutation of the operator ceremony ledger at
  `C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl`. The ledger is always
  caller-injected; committed tests use an in-memory ledger.
- **No** edit of the committed source / adapter / session / composer / renderer /
  tier-band internals (import of public symbols only).
- **No** commit/tag/push until operator approval.

## 4. Files

### Added (production — `PHX2/stage30/`)
- `stage30_11_20_current_price_enrichment_models.py` — pure leaf models +
  closed-set Layer-0 decision vocabulary + duck-typed surface pins + redaction
  tokens + safe-shape predicates (imports **no** PHX2).
- `stage30_11_20_current_price_enrichment_adapter.py` —
  `enrich_facts_with_current_price(...)` +
  `run_stage30_11_20_price_enriched_session(...)` + the redaction self-scan.
- `stage30_11_20_fake_current_price_enrichment_proof.py` — thin offline driver
  (defaults the in-memory ledger + recording fake client; the price source +
  market-context source + fake ATH transport are injected).

### Added (docs)
- `PHX2/docs/STAGE_30_11_20_CURRENT_PRICE_ENRICHMENT_SPEC_LOCK.md` (this).

### Added (tests — `PHX2/tests/stage30/`)
- `test_stage_30_11_20_current_price_enrichment_adapter.py`
- `test_stage_30_11_20_fake_current_price_enrichment_proof.py`
- `test_stage_30_11_20_boundaries.py`
- `test_stage_30_11_20_manifest.py`

### Updated
- `PHX2/stage30/stage30_11_manifest.py` — Stage 30.11.20 manifest section +
  `__all__` exports only (constants mirrored BY VALUE).
- `PHX2/tests/stage30/test_stage_30_0_spec_lock.py`,
  `test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py`,
  `test_stage_30_11_5_boundaries.py`,
  `test_stage_30_9_0_bounded_private_live_compact_spec_lock.py` — the four Stage
  30.11 admission guards, extended additively (future-token guard 20→21). The same
  bookkeeping as every prior Stage 30.11.x slice; no logic changed.

### Reuse / import-only (NOT edited)
- `stage30_11_19_market_context_enrichment_adapter.py`
  (`run_stage30_11_19_enriched_session`)
- `stage30_11_18_harvested_facts_models.py` (`Stage30_11_18HarvestedCandidateFacts`)
- `stage30_11_18_harvest_to_curated_adapter.py` (`is_positive_decimal_text`,
  `is_iso_utc_shape`)
- `stage30_11_17_operator_curated_candidate_list_models.py` (`Stage30_11_17SessionConfig`,
  `is_within_session_caps`, `default_session_config`)
- `stage30_11_15_ping_dedupe_ledger.py` (`InMemoryPingDedupeLedger`)
- `stage30_11_5_fake_live_wiring_proof.py` (`Stage30_11_5RecordingFakeTransportClient`)
- `stage29_2_birdeye_price_source.py` (the real price source the proof test +
  ceremony construct over an injected transport; committed Stage 30.11.20 imports
  it NOT at all)
- `stage30_4_3_market_context_birdeye_source.py` (the real market-context source
  the proof test + ceremony construct; likewise never imported by committed
  Stage 30.11.20)

## 5. Model / API shape

- `Stage30_11_20PriceEnrichmentResult{ decision: str, enriched_facts: Any }`
- `Stage30_11_20PriceEnrichmentEvent{ index, decision, candidate_id, token_mint,
  created_at_utc }`  (redaction-safe; no magnitude — the fetched price text goes
  ONLY into the facts copy, never into an event)
- `Stage30_11_20PriceEnrichmentSessionReport{ enrichment_events, facts_seen,
  enriched, skipped, downstream_report, redaction_status, created_at_utc }`
- `enrich_facts_with_current_price(base_facts, *, price_source) ->
  Stage30_11_20PriceEnrichmentResult`
- `run_stage30_11_20_price_enriched_session(base_facts, *, price_source,
  market_context_source, config, ledger, ath_transport, ath_endpoint_secret,
  now_utc, transport_client, now_seconds, ath_timeout_seconds=10,
  market_context_max_age_seconds=None, ttl_seconds=None) ->
  Stage30_11_20PriceEnrichmentSessionReport`

## 6. Bounds + defaults

- Dry / no-send only (fake recording client).
- Scans AT MOST `config.max_candidates` base facts (`<= 10`, mirrors the committed
  Stage 30.11.17 session caps); an out-of-cap config raises
  `Stage30_11_20CurrentPriceEnrichmentError` before any fact is scanned (the
  price source is never called).
- ONE shared injected ledger across the downstream session chain (in-memory in
  tests).
- Single bounded `for` loop; no `while`; no daemon.
- Combined `redaction_status == REDACTED` iff the Layer-0 enrichment events AND
  the embedded Stage 30.11.19 report are both redacted; an unsafe id is redacted
  to `REDACTED_UNSAFE_ID`; no magnitude / body / url / secret is ever carried.

## 7. Layer-0 decision vocabulary (closed set, 11 tokens)

`ENRICHED` · `SKIPPED_NOT_BASE_FACTS` · `SKIPPED_NO_PRICE_READING` ·
`SKIPPED_NOT_A_PRICE_READING` · `SKIPPED_PRICE_SOURCE_ERROR` ·
`SKIPPED_PRICE_MISSING` · `SKIPPED_PRICE_STATUS_UNRECOGNIZED` ·
`SKIPPED_MISSING_PRICE_VALUE` / `SKIPPED_INVALID_PRICE_VALUE` ·
`SKIPPED_MISSING_PRICE_FETCHED_AT` / `SKIPPED_INVALID_PRICE_FETCHED_AT`.

## 8. Test obligations (proven)

- happy path: a PRESENT snapshot overwrites ONLY `current_price`; the
  market-context placeholders (incl. `market_context_fetched_at_utc`) and
  `migration_time_utc` + every other field carried unchanged; the base fact is
  never mutated; the fact mint is passed to the source as `base_mint`.
- every `SKIPPED_*` token: one snapshot/base per token, first-failing check wins;
  `enriched_facts is None`; a source that returns `None`, raises, or lacks
  `fetch_snapshot` → `SKIPPED_NO_PRICE_READING`; a SOURCE_ERROR snapshot that
  also carries a usable-looking value still skips on the status.
- out-of-cap config raises before any fact is scanned (source never called).
- end-to-end fake proof: the REAL Stage 29.2 price source over a FAKE
  `/defi/price` transport fills the `current_price=""` placeholder and the fact
  flows ENRICHED → (30.11.19) ENRICHED → (30.11.18) PROJECTED → DISPATCHED to a
  RECORDED would-send; a float sub-micro price body preserves full precision
  verbatim; a missing / zero / refused price → the precise `SKIPPED_*`, NOT
  forwarded (the embedded chain sees nothing, zero would-sends); a good price
  with a liquidity-less token-overview body fails closed at the committed Stage
  30.11.19 layer (chain order proven); the ONE shared ledger blocks the in-run
  and cross-run duplicate; the scan is bounded at the candidate cap.
- boundary scan over the three production modules: no Stage 21-29 import (incl.
  the Stage 29.2 price source), no Stage 30.4.3 / Birdeye import, no Stage
  30.11.16 guard import; no live-provider / secret / transport / url needle; no
  env read, no filesystem write, no `while` / daemon, no top-level call; only
  `__future__` / `typing` / `dataclasses` stdlib.
- manifest mirrors all constants BY VALUE; the price-status tokens cross-check
  against the committed Stage 29.2 vocabulary; the duck-typed method exists on
  the committed Stage 29.2 price source; the enriched price fields are exactly
  `("current_price",)`, disjoint from the Stage 30.11.19 market bundle; the
  spec-lock doc exists.

## 9. Next allowed step

`operator-authorized migration_time enrichment seam + real-fed dry-run ceremony
(separate steps)`. Stage 30.11.20 ships no part of them. After the price seam, a
fully dispatch-eligible real candidate still needs `migration_time_utc`
(migration evidence) — the last hand-fed field, since the Stage 30.11.6 harvest
does not carry the migration anchor. Once that seam lands, the real-fed dry-run
ceremony (real harvest + real price + real market context over the FAKE recording
client) becomes possible, and a real send would compose an `ENRICHED → PROJECTED
→ DISPATCHED` result through the SEPARATE Stage 30.11.16 real-send guard with a
real audited transport + a valid operator-auth sentinel — an explicit,
separately-authorized ceremony, not this stage.
