# Stage 30.11.19 — Market-Context Enrichment Adapter (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.19: enrich harvested facts with market context`

**Status:** committed, offline / fakes-only, **no real send**. The real
token-overview read (the operator constructs the committed Stage 30.4.3 source over
a real Stage 29.2 transport) and the controlled live send remain a SEPARATE,
explicitly operator-authorized, **ceremony-injected** step that is **not** built or
run by this stage.

---

## 1. Purpose

Close the liquidity blocker the Stage 30.11.18 contract exposed
(`REJECTED_MISSING_LIQUIDITY_USD`) by **reusing** the already-committed,
live-proven Stage 30.4.3 Birdeye token-overview market-context source — **no new
fetcher is built**. Given a base `Stage30_11_18HarvestedCandidateFacts` and an
**injected, duck-typed** market-context source, fill the coherent market-context
bundle and run the enriched facts through the committed Stage 30.11.18 / 30.11.17
session:

```
base harvested facts
  → enrich_facts_with_market_context(base, market_context_source=…)   # Layer-0
      → source.read(token_mint) → Stage30_4MarketContextSourceReading
      → ENRICHED   → replace(base, MC, LP, fetched_at, status=PRESENT)
      → SKIPPED_*  → enriched_facts=None (NOT forwarded; no silent pass-through)
  → enriched facts ONLY
  → run_stage30_11_18_curated_session(...)     # Layer-1 projection
  → run_stage30_11_17_operator_curated_compose_session(...)   # Layer-2 composer
  → one combined redaction-safe Stage30_11_19EnrichmentSessionReport
```

A committed liquidity source already exists: `Stage30_4_3BirdeyeMarketContextSource`
(Birdeye `/defi/token_overview`) yields `market_cap_usd_value`,
`liquidity_usd_value`, and `observed_at_utc` in one reading, via an injected Stage
29.2 transport. Stage 30.11.19 is the thin committed **mapper** from that reading
onto the facts; the live read stays ceremony-injected.

## 2. The locked contract

### 2.1 Input / output type, and the coherent bundle

- **Input = output type = `Stage30_11_18HarvestedCandidateFacts`.** Enrichment is a
  `dataclasses.replace` of **only** the four market-context fields on a COPY of the
  base fact.
- The four enriched fields (a coherent bundle from ONE reading):
  `current_market_cap_usd`, `liquidity_usd`, `market_context_fetched_at_utc`,
  `market_context_status`.
- **`current_price` and `migration_time_utc` are carried through UNCHANGED.** They
  are NEVER enriched here (separate seams).

### 2.2 Reading → facts mapping (the `ENRICHED` path)

Given `reading = market_context_source.read(token_mint)` (duck-typed):

| Facts field (overwritten) | ← reading field | rule |
|---|---|---|
| `current_market_cap_usd` | `market_cap_usd_value` | present + finite decimal `> 0` |
| `liquidity_usd` | `liquidity_usd_value` | present + finite decimal `> 0` |
| `market_context_fetched_at_utc` | `observed_at_utc` | present + ISO-8601 shape |
| `market_context_status` | *(derived)* | set to `"PRESENT"` (MC + LP + observed-at all pass and `reading.stale` is falsy) |

The Layer-0 positivity + ISO-shape checks REUSE the committed Stage 30.11.18
predicates (`is_positive_decimal_text`, `is_iso_utc_shape`) — no decimal / datetime
import. **Staleness distinction:** Layer-0 checks only `reading.stale` (the
source's own flag). The time-based freshness (`created_at_utc` −
`market_context_fetched_at_utc` ≤ 300s) stays the **composer's Layer-2**
`MARKET_CONTEXT_STALE`.

### 2.3 Fail-closed ladder (first failing check wins → that `SKIPPED_*`)

1. non-facts base → `SKIPPED_NOT_BASE_FACTS`
2. `source.read(...)` returns `None` (or the source lacks a callable `read`, or
   `read` raises) → `SKIPPED_NO_MARKET_CONTEXT_READING`
3. reading missing required attrs / wrong shape → `SKIPPED_NOT_A_MARKET_CONTEXT_READING`
4. `reading.stale` truthy → `SKIPPED_STALE_MARKET_CONTEXT`
5. missing MC → `SKIPPED_MISSING_MARKET_CAP`
6. invalid/non-positive MC → `SKIPPED_INVALID_MARKET_CAP`
7. missing LP → `SKIPPED_MISSING_LIQUIDITY_USD`
8. invalid/non-positive LP → `SKIPPED_INVALID_LIQUIDITY_USD`
9. missing observed-at → `SKIPPED_MISSING_OBSERVED_AT`
10. invalid observed-at → `SKIPPED_INVALID_OBSERVED_AT`
11. all pass → `ENRICHED`

### 2.4 Skip behavior — no silent pass-through

`enrich_facts_with_market_context(...) -> Stage30_11_19EnrichmentResult{decision,
enriched_facts}`. `enriched_facts` is the filled facts ONLY on `ENRICHED`; on every
`SKIPPED_*` it is `None`, the base fact is **not mutated and not forwarded** to the
Stage 30.11.18 session. The blocker is a visible `SKIPPED_*` count + event in the
report — not silently re-derived downstream.

### 2.5 Three honest layers

L0 enrichment (this stage) → L1 Stage 30.11.18 projection → L2 Stage 30.11.13
composer. An `ENRICHED` fact can still be Stage 30.11.18-`REJECTED` for missing
`current_price` / `migration_time_utc` (separate seams) — that is expected and is
shown in the embedded report.

## 3. What this stage is NOT (hard exclusions)

- **No** new market-context fetcher (Stage 30.4.3 is reused, NOT edited or
  re-implemented).
- **No** Stage 21-29 import in committed production; **no** Stage 30.4.3 source
  import; **no** real provider transport construction. The market-context source is
  **injected and read duck-typed** (`source.read(token_mint)` + attribute access).
- **No** real send. The only transport is the injected committed Stage 30.11.5
  recording **fake** client. **No** call to / import of the Stage 30.11.16 real
  private transport guard.
- **No** `current_price` / `migration_time_utc` enrichment.
- **No** Discord / webhook call. No network, no env read, no wall-clock read (clocks
  injected; the composer owns the Layer-2 freshness clock).
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
- `stage30_11_19_market_context_enrichment_models.py` — pure leaf models +
  closed-set Layer-0 decision vocabulary + redaction tokens + safe-shape predicates
  (imports **no** PHX2).
- `stage30_11_19_market_context_enrichment_adapter.py` — `enrich_facts_with_market_context(...)`
  + `run_stage30_11_19_enriched_session(...)` + the redaction self-scan.
- `stage30_11_19_fake_market_context_enrichment_proof.py` — thin offline driver
  (defaults the in-memory ledger + recording fake client; the market-context source
  + fake ATH transport are injected).

### Added (docs)
- `PHX2/docs/STAGE_30_11_19_MARKET_CONTEXT_ENRICHMENT_SPEC_LOCK.md` (this).

### Added (tests — `PHX2/tests/stage30/`)
- `test_stage_30_11_19_market_context_enrichment_adapter.py`
- `test_stage_30_11_19_fake_market_context_enrichment_proof.py`
- `test_stage_30_11_19_boundaries.py`
- `test_stage_30_11_19_manifest.py`

### Updated
- `PHX2/stage30/stage30_11_manifest.py` — Stage 30.11.19 manifest section +
  `__all__` exports only (constants mirrored BY VALUE).
- `PHX2/tests/stage30/test_stage_30_0_spec_lock.py`,
  `test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py`,
  `test_stage_30_11_5_boundaries.py`,
  `test_stage_30_9_0_bounded_private_live_compact_spec_lock.py` — the four Stage
  30.11 admission guards, extended additively (future-token guard 19→20). The same
  bookkeeping as every prior Stage 30.11.x slice; no logic changed.

### Reuse / import-only (NOT edited)
- `stage30_11_18_harvested_facts_models.py` (`Stage30_11_18HarvestedCandidateFacts`)
- `stage30_11_18_harvest_to_curated_adapter.py` (`run_stage30_11_18_curated_session`,
  `is_positive_decimal_text`, `is_iso_utc_shape`)
- `stage30_11_17_operator_curated_candidate_list_models.py` (`Stage30_11_17SessionConfig`,
  `is_within_session_caps`, `default_session_config`)
- `stage30_11_15_ping_dedupe_ledger.py` (`InMemoryPingDedupeLedger`)
- `stage30_11_5_fake_live_wiring_proof.py` (`Stage30_11_5RecordingFakeTransportClient`)
- `stage30_4_3_market_context_birdeye_source.py` (the real source the proof test +
  ceremony construct over an injected transport; committed Stage 30.11.19 imports it
  NOT at all)

## 5. Model / API shape

- `Stage30_11_19EnrichmentResult{ decision: str, enriched_facts: Any }`
- `Stage30_11_19EnrichmentEvent{ index, decision, candidate_id, token_mint,
  created_at_utc }`  (redaction-safe; no magnitude)
- `Stage30_11_19EnrichmentSessionReport{ enrichment_events, facts_seen, enriched,
  skipped, downstream_report, redaction_status, created_at_utc }`
- `enrich_facts_with_market_context(base_facts, *, market_context_source) ->
  Stage30_11_19EnrichmentResult`
- `run_stage30_11_19_enriched_session(base_facts, *, market_context_source, config,
  ledger, ath_transport, ath_endpoint_secret, now_utc, transport_client,
  now_seconds, ath_timeout_seconds=10, market_context_max_age_seconds=None,
  ttl_seconds=None) -> Stage30_11_19EnrichmentSessionReport`

## 6. Bounds + defaults

- Dry / no-send only (fake recording client).
- Scans AT MOST `config.max_candidates` base facts (`<= 10`, mirrors the committed
  Stage 30.11.17 session caps); an out-of-cap config raises
  `Stage30_11_19MarketContextEnrichmentError` before any fact is scanned.
- ONE shared injected ledger across the downstream session (in-memory in tests).
- Single bounded `for` loop; no `while`; no daemon.
- Combined `redaction_status == REDACTED` iff the Layer-0 enrichment events AND the
  embedded Stage 30.11.18 report are both redacted; an unsafe id is redacted to
  `REDACTED_UNSAFE_ID`; no magnitude / body / url / secret is ever carried.

## 7. Layer-0 decision vocabulary (closed set, 11 tokens)

`ENRICHED` · `SKIPPED_NOT_BASE_FACTS` · `SKIPPED_NO_MARKET_CONTEXT_READING` ·
`SKIPPED_NOT_A_MARKET_CONTEXT_READING` · `SKIPPED_STALE_MARKET_CONTEXT` ·
`SKIPPED_MISSING_MARKET_CAP` / `SKIPPED_INVALID_MARKET_CAP` ·
`SKIPPED_MISSING_LIQUIDITY_USD` / `SKIPPED_INVALID_LIQUIDITY_USD` ·
`SKIPPED_MISSING_OBSERVED_AT` / `SKIPPED_INVALID_OBSERVED_AT`.

## 8. Test obligations (proven)

- happy path: a usable reading fills the bundle (`ENRICHED`); the four market fields
  are overwritten from the reading; `current_price` + `migration_time_utc` + every
  other field carried unchanged.
- every `SKIPPED_*` token: one reading/base per token, first-failing check wins;
  `enriched_facts is None`; a source that returns `None` or raises →
  `SKIPPED_NO_MARKET_CONTEXT_READING`.
- out-of-cap config raises before any fact is scanned.
- end-to-end fake proof: the REAL Stage 30.4.3 source over a FAKE token-overview
  transport enriches MC/LP/fetched-at; the enriched fact projects (`PROJECTED`) and
  dispatches through the committed Stage 30.11.18 / 30.11.17 session (a RECORDED
  would-send); a token-overview body WITHOUT liquidity →
  `SKIPPED_MISSING_LIQUIDITY_USD`, NOT forwarded (the embedded session sees nothing).
- boundary scan over the three production modules: no Stage 21-29 import, no Stage
  30.4.3 / Birdeye import, no Stage 30.11.16 guard import; no live-provider / secret
  / transport / url needle; no env read, no filesystem write, no `while` / daemon,
  no top-level call; only `__future__` / `typing` / `dataclasses` stdlib.
- manifest mirrors all constants BY VALUE; the enriched market fields are a subset
  of the committed facts fields and exclude `current_price` / `migration_time_utc`;
  the spec-lock doc exists.

## 9. Next allowed step

`operator-authorized current_price + migration_time enrichment seams (separate
steps)`. Stage 30.11.19 ships no part of them. After the market-context bundle is
enriched, a fully dispatch-eligible real candidate still needs `current_price` (the
Birdeye `/defi/price` source) and `migration_time_utc` (migration evidence) — the
remaining seams. A real send would compose an `ENRICHED → PROJECTED → DISPATCHED`
result through the SEPARATE Stage 30.11.16 real-send guard with a real audited
transport + a valid operator-auth sentinel — an explicit, separately-authorized
ceremony, not this stage.
