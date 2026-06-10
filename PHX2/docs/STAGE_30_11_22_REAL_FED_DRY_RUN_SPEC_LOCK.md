# Stage 30.11.22 — Real-Fed Dry-Run Wrapper (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.22: bridge harvested candidates into real-fed dry run`

**Status:** committed, offline / fakes-only, **no real send**. The real live event
source + provider sources (the operator constructs them at the ceremony and injects
them into the wrapper), the real-fed dry-run ceremony, and the controlled capped
private send remain a SEPARATE, explicitly operator-authorized, **ceremony-injected**
step that is **not** built or run by this stage.

---

## 1. Purpose

Close the **last committed gap** before an operator-authorized real-fed dry-run
ceremony can run. The committed Stage 30.11.6 harvest seam emits a
`Stage30_11_6CandidateProjection` tuple, but the committed enrichment chain consumes
a `Stage30_11_18HarvestedCandidateFacts` base fact — a **different shape**. Before
this slice, nothing committed mapped the one onto the other, so a ceremony had to
hand-build that correctness-critical base fact in **untested out-of-repo glue**. This
slice ships the mapping **in-repo** (a pure bridge) plus a thin orchestration wrapper,
both fully injected and offline:

```
bounded live event source (operator-constructed; injected)
  → harvest_live_candidates(events, assembler=…, record_flattener=…, max_harvest≤10)   # COMMITTED 30.11.6
      → candidate_source: tuple[Stage30_11_6CandidateProjection]
  → project_harvested_candidate_to_base_facts(projection, created_at_utc=…)            # 30.11.22 BRIDGE
      → Stage30_11_18HarvestedCandidateFacts (token_mint + candidate_id verbatim; rest = sentinels)
  → run_stage30_11_21_migration_time_enriched_session(base_facts, …)                   # COMMITTED 30.11.21
      → 30.11.20 price → 30.11.19 MC/LP → 30.11.18 projection → 30.11.17 compose/dedupe
      → RECORDED would-send through the FAKE transport (NEVER a real send)
  → Stage30_11_22RealFedDryRunReport (one combined, redaction-safe report)
```

This is **not a fake layer**: the migration verdict, the price / market-context /
ATH reads, the freshness / tier / dip gate, and the dedupe are all the committed
downstream slices', reused verbatim. The only genuinely new logic is the ~15-line
pure bridge.

## 2. The locked contract

### 2.1 The bridge — `project_harvested_candidate_to_base_facts`

Pure / total. From one `Stage30_11_6CandidateProjection`:

- **`token_mint` ← `projection.token_mint` (verbatim).** The real on-chain identity
  that drives every injected source lookup and the migration-anchored ATH window.
- **`candidate_id` ← `projection.candidate_id` (verbatim).** The run-scoped id.
- **`created_at_utc` ← caller-injected.**
- Every field the enrichment fills is stamped with a **sentinel**:
  - `migration_time_utc` / `current_price` / `current_market_cap_usd` /
    `liquidity_usd` / `market_context_fetched_at_utc` ← `PENDING_ENRICHMENT`
  - `market_context_status` ← `PENDING`
- `migration_confirmed = True` is set but **NOT trusted**: the committed Stage 30.11.21
  adapter re-confirms the migration from the injected evidence source (it reads the
  token mint + evidence, never the base flag) and only forwards a confirmed fact.
- `symbol_or_name` / `migration_source` / `age_display` = `None`.

`PENDING_ENRICHMENT` is deliberately **non-ISO + non-numeric**. The enrichment
**overwrites** each sentinel on a confirmed / present reading and **drops** the fact on
a skip (no silent pass-through), so a sentinel can never reach the composer; a bug
leak would fail closed at the Stage 30.11.18 Layer-1 shape / positivity check, never
silently dispatch.

### 2.2 The wrapper — `run_stage30_11_22_real_fed_dry_run`

- **Fail closed first:** an out-of-caps session config raises
  `Stage30_11_22RealFedDryRunError` before harvesting; an out-of-bounds `max_harvest`
  raises the committed `Stage30_11_6CandidateHarvestError`.
- **Safe-by-construction defaults:** an absent `transport_client` defaults to the
  committed Stage 30.11.5 **recording FAKE** client (records a would-send, opens no
  socket); an absent `ledger` defaults to the committed Stage 30.11.15 **in-memory**
  ledger (no I/O — it **cannot** touch the durable one-send ledger); an absent
  `config` defaults to `max_candidates=10` / `max_compositions=10`.
- Every provider source (assembler, record flattener, evidence source, price source,
  market-context source, ATH source transport + secret, clocks) is **injected** — the
  wrapper constructs **no** real provider transport.

## 3. Caps

| Cap | Value | Enforced by |
|---|---|---|
| `max_harvest` | ≤ 10 (hard) | committed Stage 30.11.6 harvest seam |
| `max_candidates` | ≤ 10 (hard) | committed Stage 30.11.17 session config |
| `max_compositions` | ≤ 10 | committed Stage 30.11.17 session config |
| would-sends | ≤ dispatched ≤ `max_compositions` | recorded by the FAKE client |
| **real sends** | **0, structurally** | recording-fake transport only; no real-send guard imported |

The wall-clock / event-count budget on the **real** event source is the ceremony's to
impose (the committed chain has no time-bounded loop). It is the cost lever: each
harvested candidate triggers the injected price / market-context / ATH reads.

## 4. Dedupe

The dry run uses the **in-memory** ledger by default — it persists nothing and
**cannot** touch the durable one-send ledger path. An in-run duplicate (same mint /
tier / drawdown band / ATH flag / policy) is suppressed by the one shared ledger and
reported as `dedupe_blocked`, never sent. An injected ledger is honored (the cross-run
guarantee still holds).

## 5. The report — `Stage30_11_22RealFedDryRunReport`

Surfaces, for one dry run: `events_seen`, `candidates_harvested`, the harvest skip
tallies, `base_facts_built`, the per-stage Layer-0 `enriched` / `skipped` counts +
**skip histograms** (migration / price / market), the Layer-1 `projected` /
`rejected_projection`, the Layer-2 `composed` / `dispatched` / `dedupe_blocked` /
`would_send_recorded` / `stop_reason`, the **embedded** Stage 30.11.21 session report
(the full combined nested report — nothing is lost), the **no-real-send attestation**,
the combined `redaction_status`, and a caller-injected timestamp.

The **no-real-send attestation** pins the recording-fake transport-client kind, the
in-memory ledger kind, the recorded would-send tally, and two `False` flags
(`real_send_performed`, `real_send_guard_invoked`) the path can never flip.

## 6. Redaction

The report carries only closed-set tokens + safe-echo kind tokens + injected
timestamps + the already-redaction-safe embedded report — **no** magnitude, body, url,
exception text, or secret. Its `redaction_status` is `REDACTED` only when its own
fields self-scan clean **and** the embedded Stage 30.11.21 report is `REDACTED`.

## 7. What this stage does NOT do

No real send · no private message send · no real-send guard call or import · no real
provider transport construction · no Stage 27 / 28 / 29 import · no Stage 30.4.3 source
import · no Stage 30.11.11 ATH-source import · no env read · no network / socket · no
durable-ledger mutation · no filesystem write · no `while` loop / daemon · no renderer
/ tier-band / dedupe-key / composer edit · no public / subscriber routing · no wallet /
signing / trading · no new alpha filter · no commit / tag / push.

## 8. Boundary / discipline

Committed code stays **Stage 30-only / import-safe**: the models module imports no
PHX2; the adapter + proof import only committed Stage 30.11 siblings (the 30.11.6
harvest seam + projection models, the 30.11.18 facts type, the 30.11.21 enrichment
entrypoint, the 30.11.17 session models, the 30.11.15 in-memory ledger, the 30.11.5
recording fake client). Stdlib is `__future__` / `typing` / `dataclasses` only. No
module-level call (no import-time I/O).

## 9. Next steps (separate, operator-authorized)

1. **Real-fed dry-run ceremony** — out-of-repo: construct the real live event source +
   provider sources, inject them into `run_stage30_11_22_real_fed_dry_run` with the
   FAKE transport + in-memory ledger, write the redacted report. No real send.
2. **Capped private send** — swap the FAKE transport for the real private dispatch
   **behind** the committed Stage 30.11.16 real-send guard, swap the in-memory ledger
   for the durable one, cap to one send, run once.
