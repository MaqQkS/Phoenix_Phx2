# Stage 30.11.18 — Harvested-Facts → Curated Compose Session Adapter (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.18: adapt harvested candidate facts into curated compose session`

**Status:** committed, offline / fakes-only, **no real send**. The real harvest +
market-context enrichment that produces the facts, and the controlled live send,
remain a SEPARATE, explicitly operator-authorized, **ceremony-injected** step that
is **not** built or run by this stage.

---

## 1. Purpose

Stop hand-feeding pre-built requests. Provide the smallest committed **shape
bridge** that lets a ceremony feed already-harvested + enriched candidate **facts**
(rather than hand-built `Stage30_11_13RevalidationRequest` objects) into the
already-proven Stage 30.11.17 operator-curated compose session:

```
iterable of harvested-candidate FACTS
  → Layer-1 projection (presence / shape / positivity)        # Stage 30.11.18
      → PROJECTED  → Stage30_11_13RevalidationRequest
      → REJECTED_* → fail-closed, never reaches the composer
  → Stage30_11_17OperatorCuratedCandidate (one per projected fact)
  → run_stage30_11_17_operator_curated_compose_session(...)   # committed Stage 30.11.17
      → committed Stage 30.11.13 composer (Layer-2)            # authoritative
      → ONE shared injected Stage 30.11.15 dedupe ledger
  → rolled-up redaction-safe report (Layer-1 counts + embedded session result)
```

Before Stage 30.11.18 the ONLY way to obtain a `Stage30_11_13RevalidationRequest`
was to hand-build it (the Stage 30.11.13 fake proof's `default_proof_request`). No
committed bridge mapped a candidate/projection into a dispatch request. Stage
30.11.18 is that missing bridge — committed, offline, tested — so any upstream
harvested-record producer (including the real provider → assembler → harvest chain,
wired only at a ceremony) can feed the bounded session **with zero hand-built
requests**.

## 2. The locked contract

### 2.1 Flat 13-field harvested facts model

`Stage30_11_18HarvestedCandidateFacts` is a **flat** carrier of EXACTLY the 13
inputs the committed Stage 30.11.13 revalidation request consumes (a near 1:1 map;
**not** a nested-context object). A pin test asserts the facts field SET equals the
committed request's dataclass field set.

Required (absent / malformed → fail-closed Layer-1 `REJECTED_*`):
`token_mint`, `candidate_id`, `migration_time_utc`, `current_price`,
`current_market_cap_usd`, **`liquidity_usd`**, `market_context_status`,
`market_context_fetched_at_utc`, `created_at_utc`.

Optional (absent → no rejection; carried through):
`migration_confirmed` (default `True`; an explicit non-`True` → rejected),
`symbol_or_name`, `migration_source`, `age_display`.

### 2.2 `liquidity_usd` is REQUIRED

Even though the Stage 30.11.13 request types `liquidity_usd` as `Optional`, the
committed composer fails closed without it (`LIQUIDITY_UNAVAILABLE`). Stage 30.11.18
therefore makes `liquidity_usd` **required** in the facts contract and rejects a
missing / non-positive value EARLY with a precise Layer-1 token, rather than letting
it surface as a buried composer reason. **`liquidity_usd` has no source anywhere in
the existing Stage 27 / Stage 29 context records** — it must be supplied by the
ceremony-injected enrichment (the real next blocker, deferred).

### 2.3 Two-layer validation model

- **Layer 1 (Stage 30.11.18 adapter — pure, no clock, no transport):** presence /
  shape / positivity of the scalar inputs only. Produces a closed-set per-fact
  decision: `PROJECTED` (a well-formed request was built) or one of the
  `REJECTED_*` tokens (the fact never reaches the composer).
- **Layer 2 (committed Stage 30.11.13 composer — AUTHORITATIVE):** freshness
  (stale / future fetch), ATH resolution, tier eligibility, and the dip gate. A
  projected fact may still be rejected at Layer-2; that verdict is surfaced
  VERBATIM in the embedded Stage 30.11.17 session result's mirrored compose reason
  (e.g. `MARKET_CONTEXT_STALE`, `MARKET_CONTEXT_TIMESTAMP_FUTURE`,
  `TIER_NOT_ELIGIBLE`). The adapter NEVER re-implements the freshness clock and
  NEVER mints a stale / ATH / tier token.

### 2.4 Per-field mapping (facts → request) + Layer-1 token

| Request field | Layer-1 rule (pure) | Layer-1 reject token(s) | Layer-2 (composer) token |
| --- | --- | --- | --- |
| `token_mint` | non-blank + safe-echo | `REJECTED_MISSING_TOKEN_MINT` / `REJECTED_INVALID_TOKEN_MINT` | `INVALID_REQUEST` |
| `candidate_id` | non-blank + safe-echo | `REJECTED_MISSING_CANDIDATE_ID` / `REJECTED_INVALID_CANDIDATE_ID` | `INVALID_REQUEST` |
| `migration_confirmed` | `is True` | `REJECTED_MIGRATION_NOT_CONFIRMED` | `INVALID_REQUEST` |
| `migration_time_utc` | non-blank + ISO shape | `REJECTED_MISSING_MIGRATION_TIME_UTC` / `REJECTED_INVALID_MIGRATION_TIME_UTC` | `INVALID_REQUEST` |
| `created_at_utc` | non-blank + ISO shape | `REJECTED_MISSING_CREATED_AT` / `REJECTED_INVALID_CREATED_AT` | `INVALID_REQUEST` |
| `market_context_status` | `== "PRESENT"` | `REJECTED_MARKET_CONTEXT_NOT_PRESENT` | `MARKET_CONTEXT_MISSING` |
| `current_market_cap_usd` | finite decimal `> 0` | `REJECTED_MISSING_MARKET_CAP` / `REJECTED_INVALID_MARKET_CAP` | `MARKET_CAP_UNAVAILABLE` |
| `current_price` | finite decimal `> 0` | `REJECTED_MISSING_CURRENT_PRICE` / `REJECTED_INVALID_CURRENT_PRICE` | `CURRENT_PRICE_UNAVAILABLE` |
| `liquidity_usd` | finite decimal `> 0` | `REJECTED_MISSING_LIQUIDITY_USD` / `REJECTED_INVALID_LIQUIDITY_USD` | `LIQUIDITY_UNAVAILABLE` |
| `market_context_fetched_at_utc` | non-blank + ISO **shape only** | `REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT` / `REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT` | `MARKET_CONTEXT_TIMESTAMP_MISSING` / `…_FUTURE` / `MARKET_CONTEXT_STALE` |
| `symbol_or_name` | optional, carried | — | — |
| `migration_source` | optional, carried | — | — |
| `age_display` | optional, carried | — | — |

The Layer-1 ISO check is **conservative-lax** (charset + digit-count only, no clock,
no `datetime` import): it rejects obvious non-timestamp garbage but NEVER rejects a
value the composer would accept; staleness / future is Layer-2.

## 3. What this stage is NOT (hard exclusions)

- **No** committed live provider imports. No Chainstack / Yellowstone gRPC, no
  Stage 28 / Stage 29 live provider session, no Stage 21–29 import of any kind. The
  real harvest source is **ceremony-injected**, never a committed import.
- **No** committed real harvest runner. Stage 30.11.6 `harvest_live_candidates` with
  a real assembler/flattener, and the market-context enrichment that fills the
  facts, stay deferred to the out-of-repo ceremony.
- **No** real send. The only transport is the injected committed Stage 30.11.5
  recording **fake** client (a RECORDED would-send, never a real send). **No** call
  to / import of the Stage 30.11.16 real private transport guard.
- **No** Discord / webhook call. No network, no env read, no wall-clock read (every
  clock is injected; the composer owns the Layer-2 freshness clock).
- **No** wallet / signing / trading. **No** public / subscriber / paid routing.
- **No** renderer polish, **no** `while`/daemon loop, **no** background service.
- **No** mutation of the operator ceremony ledger at
  `C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl`. The ledger is always
  caller-injected; committed tests use an in-memory ledger or a `tmp_path` JSONL
  ledger.
- **No** edit of the committed composer / session / dedupe / ledger / renderer /
  tier-band internals (import of public symbols only).
- **No** commit/tag/push until operator approval.

## 4. Files

### Added (production — `PHX2/stage30/`)
- `stage30_11_18_harvested_facts_models.py` — pure leaf models + closed-set
  Layer-1 decision vocabulary + redaction tokens + safe-shape predicates (imports
  **no** PHX2).
- `stage30_11_18_harvest_to_curated_adapter.py` — Layer-1 projection
  (`project_harvested_facts_to_request`) + the bounded session driver
  (`run_stage30_11_18_curated_session`) + the pure ISO-shape / positive-decimal
  predicates + the redaction self-scan.
- `stage30_11_18_fake_harvest_session_proof.py` — thin offline driver (defaults the
  in-memory ledger + recording fake client; the fake ATH transport is injected).

### Added (docs)
- `PHX2/docs/STAGE_30_11_18_HARVESTED_FACTS_CURATED_SESSION_SPEC_LOCK.md` (this).

### Added (tests — `PHX2/tests/stage30/`)
- `test_stage_30_11_18_harvest_to_curated_adapter.py`
- `test_stage_30_11_18_fake_harvest_session_proof.py`
- `test_stage_30_11_18_boundaries.py`
- `test_stage_30_11_18_manifest.py`

### Updated
- `PHX2/stage30/stage30_11_manifest.py` — Stage 30.11.18 manifest section +
  `__all__` exports only (constants mirrored BY VALUE).
- `PHX2/tests/stage30/test_stage_30_0_spec_lock.py` — register the 3 production +
  4 test basenames in the package inventories.
- `PHX2/tests/stage30/test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py`
  — register the 30.11.18 production + test entries; admit minor token 18 (the
  future-file guard now catches 30.11.19+).
- `PHX2/tests/stage30/test_stage_30_11_5_boundaries.py` — admit the 30.11.18 proof
  as a sanctioned importer of the Stage 30.11.5 recording fake client.
- `PHX2/tests/stage30/test_stage_30_9_0_bounded_private_live_compact_spec_lock.py`
  — admit the 30.11.18 basenames among Stage 30.10+ files.

These four registration edits are mandatory Stage 30.11 admission bookkeeping, the
same as every prior Stage 30.11.x slice; no logic is changed.

### Reuse / import-only (NOT edited)
- `stage30_11_13_committed_no_send_composer.py` (`Stage30_11_13RevalidationRequest`)
- `stage30_11_17_operator_curated_candidate_list_models.py`
  (`Stage30_11_17OperatorCuratedCandidate`, `Stage30_11_17SessionConfig`,
  `default_session_config`, `is_within_session_caps`)
- `stage30_11_17_operator_curated_compose_session.py`
  (`run_stage30_11_17_operator_curated_compose_session`)
- `stage30_11_15_ping_dedupe_ledger.py` (`InMemoryPingDedupeLedger`,
  `JsonlPingDedupeLedger`)
- `stage30_11_5_fake_live_wiring_proof.py` (`Stage30_11_5RecordingFakeTransportClient`)

## 5. Model / API shape

- `Stage30_11_18HarvestedCandidateFacts{ token_mint, candidate_id,
  migration_time_utc, current_price, current_market_cap_usd, liquidity_usd,
  market_context_status, market_context_fetched_at_utc, created_at_utc,
  migration_confirmed=True, symbol_or_name=None, migration_source=None,
  age_display=None }`
- `Stage30_11_18ProjectionEvent{ index, decision, candidate_id, token_mint,
  created_at_utc }`  (redaction-safe; no magnitude)
- `Stage30_11_18SessionReport{ projection_events, facts_seen, projected,
  rejected_projection, session_result, redaction_status, created_at_utc }`
- `project_harvested_facts_to_request(facts) -> Stage30_11_18ProjectionResult`
- `run_stage30_11_18_curated_session(facts, *, config, ledger, ath_transport,
  ath_endpoint_secret, now_utc, transport_client, now_seconds,
  ath_timeout_seconds=10, market_context_max_age_seconds=None, ttl_seconds=None)
  -> Stage30_11_18SessionReport`

## 6. Bounds + defaults

- Dry / no-send only (fake recording client).
- Scans AT MOST `config.max_candidates` facts (`<= 10`, mirrors the committed Stage
  30.11.17 session caps); a larger input is bounded — `facts_seen` equal to the cap
  signals the scan stopped early.
- `is_within_session_caps(config)` is checked FIRST; an out-of-cap config raises
  `Stage30_11_18HarvestAdapterError` before any fact is scanned.
- ONE shared injected ledger across all entries (in-memory / temp in tests).
- Single bounded `for` loop; no `while`; no daemon.
- Redaction-safe report only: `redaction_status == REDACTED` iff the Layer-1
  projection events AND the embedded session result are both redacted; an unsafe id
  is redacted to `REDACTED_UNSAFE_ID`, never echoed raw; no magnitude / body / url /
  secret is ever carried.

## 7. Layer-1 decision vocabulary (closed set, 20 tokens)

`PROJECTED` · `REJECTED_NOT_A_FACTS_RECORD` ·
`REJECTED_MISSING_TOKEN_MINT` / `REJECTED_INVALID_TOKEN_MINT` ·
`REJECTED_MISSING_CANDIDATE_ID` / `REJECTED_INVALID_CANDIDATE_ID` ·
`REJECTED_MIGRATION_NOT_CONFIRMED` ·
`REJECTED_MISSING_MIGRATION_TIME_UTC` / `REJECTED_INVALID_MIGRATION_TIME_UTC` ·
`REJECTED_MISSING_CREATED_AT` / `REJECTED_INVALID_CREATED_AT` ·
`REJECTED_MARKET_CONTEXT_NOT_PRESENT` ·
`REJECTED_MISSING_MARKET_CAP` / `REJECTED_INVALID_MARKET_CAP` ·
`REJECTED_MISSING_CURRENT_PRICE` / `REJECTED_INVALID_CURRENT_PRICE` ·
`REJECTED_MISSING_LIQUIDITY_USD` / `REJECTED_INVALID_LIQUIDITY_USD` ·
`REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT` /
`REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT`.

## 8. Test obligations (proven)

- happy path: a complete fact projects 1:1 into a committed request (`PROJECTED`),
  and every required field maps through unchanged.
- every `REJECTED_*` token: one malformed fact per token, first-failing check wins;
  no request is built; an unsafe id is redacted, never echoed raw.
- the pure predicates (`is_iso_utc_shape`, `is_positive_decimal_text`) are total.
- out-of-cap config raises before any fact is scanned.
- end-to-end fake proof: a coherent fact projects + dispatches (recorded
  would-send), a duplicate is suppressed over the ONE shared ledger, a malformed
  fact is rejected at Layer-1 and never reaches the composer; `redaction_status ==
  REDACTED`; fake-client `attempted == dispatched`; the operator ceremony
  `ping_dedupe.jsonl` is never referenced anywhere.
- boundary scan over the three production modules: no Stage 21–29 import, no Stage
  30.11.16 guard import, no Stage 30.11.6 harvest import, no live-provider / secret /
  transport / url needle, no env read, no filesystem write, no `while` / daemon, no
  top-level call; `decimal` is the only stdlib admitted beyond
  `__future__` / `typing` / `dataclasses` (for the Layer-1 positivity check).
- manifest mirrors all constants BY VALUE; the facts field SET equals the committed
  request inputs; the spec-lock doc exists.

## 9. Next allowed step

`operator-authorized ceremony-injected real harvest + enrichment (separate step)`.
Stage 30.11.18 ships no part of it. The deferred next blocker is the **enrichment**
that produces dispatch-eligible facts from a real harvest — supplying
`current_price`, `migration_time_utc`, `market_context_fetched_at_utc`, and
especially `liquidity_usd` (which has no existing source). Until then, a dry-run
over real un-enriched harvest output will surface `REJECTED_*` buckets that NAME the
missing fields — honest progress, not a finished auto-pipeline. A real send would
still compose a `PROJECTED` → `DISPATCHED` result through the SEPARATE Stage
30.11.16 real-send guard with a real audited transport + a valid operator-auth
sentinel — an explicit, separately-authorized ceremony, not this stage.
