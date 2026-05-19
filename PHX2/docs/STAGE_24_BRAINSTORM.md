# PHX2 Stage 24 — Brainstorm & Scope Lock (Stage 24.0)

**Status:** planning document only. No production code, no tests, no roadmap edits.
**Predecessors (closed/tagged):** `stage-20-closed`, `stage-21-closed`, `stage-22-closed`, `stage-23-closed`.
**Stage 23 closure commit:** `401f05b0247120a200c1e72eceb7100c6b36f015` (subject: *phx2 stage 23.6: closure audit and stage 24 handoff*).
**Stage 23 final tests:** 764 passed, 1 skipped.
**Stage 23 handoff doc:** [PHX2/stage23/STAGE_24_HANDOFF.md](../stage23/STAGE_24_HANDOFF.md).
**Stage 23 closure audit:** [PHX2/stage23/STAGE_23_CLOSURE_AUDIT.md](../stage23/STAGE_23_CLOSURE_AUDIT.md).

---

## 1. Stage 24 Mission

Stage 24 is the **first observe-only execution-fee and execution-quality primitive stage** after the Stage 23 filter rebuild.

- **Observe-only.** Decodes and records evidence from transaction-level data; never blocks, routes, dispatches, alerts, or monetizes.
- Reads **transaction-level evidence** (decoded tx JSONL or synthetic fixtures) and emits deterministic, redacted, hashed execution-primitive records to disk.
- Builds a **stable execution-fee / execution-quality surface** that a later Stage 26 calibration pass can re-tune without rewriting Stage 24's contracts.
- Does not enforce. Does not gate ingestion. Does not select audience. Does not modify Stage 21 / Stage 22 / Stage 23 closed contracts.
- Whether any specific fee or quality measurement is *actionable* is a Stage 26+ question. Stage 24 only produces the evidence.

The job of Stage 24 is to take a Stage 24-shaped transaction observation and emit deterministic, redacted execution primitives (priority fee, compute budget, Jito tip, router/global-fee candidates, execution quality) to disk. Nothing more.

---

## 2. Locked Boundaries — DO NOT include in Stage 24

Stage 24 must **not** include:

- **ATH / migration measurement hardening** — deferred to **Stage 25**.
- **Calibration / enforcement candidates / threshold tuning for action** — deferred to **Stage 26**.
- **X API / social ranking / social intelligence sidecar** — deferred to **Stage 27+**.
- **Public / subscriber routing** of execution-fee or execution-quality records.
- **Discord / Telegram / paid-signal / public-channel dispatch** of any kind.
- **Live alert behavior.** Stage 24 emits records to disk; it never sends a live alert.
- **DB writes.** Stage 24 writes JSONL / CSV / JSON artifacts to a caller-supplied artifact directory; it never opens a database connection.
- **Network / RPC calls.** No Helius / Jito / Axiom client. No HTTP. No websockets. No raw socket I/O.
- **CLI / live runner.** Stage 24 ships pure, side-effect-free functions and a caller-driven offline runner. It does not ship a process that runs indefinitely.
- **Mutation of Stage 21 / Stage 22 / Stage 23 closed contracts** unless a contract change is separately justified in writing. Stage 24 reads upstream artifacts; it does not modify upstream modules.
- **Fake Axiom / global-fee claims without proof.** Stage 24 must never assert a decoded Axiom / router / global-fee amount unless a fixture proves the layout (§8).
- **Phoenix1 copy-paste spaghetti.** Stage 24 is a clean rebuild; no Phoenix1 fee / Jito / Axiom code is imported or transcribed verbatim.
- **Reading env vars** from inside Stage 24 production modules.
- **Top-level I/O** at import time.

If a feature is tempting but lives in the list above, write it down for the corresponding later stage and leave Stage 24 alone.

---

## 3. Execution-Fee Primitive Definition

An **execution-fee primitive** is a deterministic per-transaction record describing one fee-category observation on a single transaction. Every execution-fee primitive carries:

- `tx_signature` — Solana transaction signature when present; empty string when absent.
- `slot` — slot number when present; `-1` sentinel when absent.
- `provider_id` — short non-secret operator label (e.g. `"helius"`).
- `observed_at_utc` — ISO-8601 UTC string from the upstream observation. May be empty.
- `primitive_family` — closed-set token from §12 (`COMPUTE_BUDGET` / `PRIORITY_FEE` / `JITO_TIP` / `ROUTER_FEE` / `EXECUTION_QUALITY`).
- `fee_source` — closed-set token from §12 (`PRIORITY_FEE_CANDIDATE` / `JITO_TIP_CANDIDATE` / `ROUTER_FEE_CANDIDATE` / `AXIOM_GLOBAL_FEE_CANDIDATE` / `COMPUTE_BUDGET_UNIT_PRICE` / `COMPUTE_BUDGET_UNIT_LIMIT` / `NOT_APPLICABLE`). Identifies the *kind* of fee being recorded.
- `decoder_status` — closed-set token from §12 describing the decoder's confidence (`DECODED` / `PARTIAL` / `DECODE_UNCONFIRMED` / `UNSUPPORTED` / `ABSENT` / `NOT_APPLICABLE` / `DECODE_FAILED` / `INPUT_REJECTED`).
- `data_status` — closed-set token from §12 (`COMPLETE` / `PARTIAL` / `MISSING` / `UNSUPPORTED`).
- `confidence_level` — closed-set token from §12 (`HIGH` / `MEDIUM` / `LOW` / `NONE`). Mirrors `decoder_status` but is a coarser axis a future Stage 26 pass can roll up on.
- `route_family` — closed-set token from §12 (`AXIOM_TRADING_PROGRAM_1` / `AXIOM_TRADE_FLASHX` / `JITO_TIP_ACCOUNT` / `COMPUTE_BUDGET_PROGRAM` / `SYSTEM_PROGRAM` / `OTHER` / `UNKNOWN`). Records which on-chain program / account family the primitive was sourced from.
- `instruction_location` — closed-set token from §12 (`TOP_LEVEL` / `INNER` / `SYSTEM_TRANSFER` / `TOKEN_TRANSFER` / `PROGRAM_INSTRUCTION_DATA` / `NOT_APPLICABLE`). Records where in the transaction the evidence was decoded from.
- `amount_lamports` — non-negative integer lamport amount when decoded; `None` when not decoded. **Never zero as a stand-in for "unknown" (§14).**
- `amount_token_units` — non-negative integer token amount when decoded (e.g. for SPL tokens in a router/global-fee transfer); `None` when not applicable or not decoded.
- `amount_token_mint` — token mint identifier when the amount is denominated in an SPL token; empty string otherwise.
- `unit_price_microlamports` — priority-fee unit price when applicable; `None` otherwise.
- `unit_limit` — compute-budget unit limit when applicable; `None` otherwise.
- `program_id` — referenced program ID when applicable; empty string when not applicable. Only the active program IDs in §8 are recognized; deprecated IDs map to `route_family=OTHER`.
- `reason_codes` — tuple of short codes explaining *why* the decoder produced the recorded status (`MISSING_COMPUTE_BUDGET_INSTRUCTION`, `JITO_TIP_ACCOUNT_NOT_FOUND`, `ROUTER_FEE_CANDIDATE_NO_LAYOUT_EVIDENCE`, etc.).
- `missing_features` — tuple of input field names the upstream observation did NOT carry.
- `input_hash` — deterministic SHA-256 of the canonicalized input.
- `primitive_hash` — deterministic SHA-256 of the canonicalized primitive body (excluding `observed_at_utc` and `created_at_utc`).
- `created_at_utc` — caller-injectable clock value. Not included in the hash.

**Every primitive is emitted.** Missing data does not skip the record; it emits a deterministic record with the appropriate `decoder_status` / `data_status` / `reason_codes`.

---

## 4. Execution-Quality Primitive Definition

An **execution-quality primitive** is a deterministic per-transaction record describing inclusion / landing quality, separate from the fee primitives. It shares the metadata fields of §3 (`tx_signature`, `slot`, `provider_id`, `observed_at_utc`, `decoder_status`, `data_status`, `confidence_level`, `reason_codes`, `missing_features`, `input_hash`, `primitive_hash`, `created_at_utc`) and adds:

- `primitive_family` — fixed to `EXECUTION_QUALITY`.
- `landed` — `True` / `False` / `None` (None when the upstream observation did not carry enough information to decide). Never silently `False` as a default.
- `landed_slot` — slot the transaction landed in; `-1` when not decoded.
- `submitted_slot` — slot the transaction was submitted in if recorded; `-1` when not decoded.
- `slot_delta` — `landed_slot - submitted_slot` when both are known; `None` otherwise.
- `realized_priority_fee_lamports` — realized priority fee when decoded; `None` otherwise.
- `realized_jito_tip_lamports` — realized Jito tip when decoded; `None` otherwise.
- `realized_router_fee_lamports` — realized router/global-fee amount when **decoded** (`decoder_status=DECODED`); `None` otherwise. Never fabricated from a candidate (see §8).
- `error_code` — short non-secret error token when the transaction failed; empty string otherwise. Never the raw RPC exception message (Stage 24 forbidden-substring policy).

Stage 24 makes no judgment about whether a quality observation is *good*. It records the observation honestly. A Stage 26 calibration pass decides whether `slot_delta > N` is bad.

---

## 5. Recommended Sub-Stage Breakdown

| Sub-stage | Scope |
|-----------|-------|
| **24.0** | This scope-lock doc. No production code. No tests. (You are here.) |
| **24.1** | Contracts, constants, closed sets, immutable models, input reader, manifest scaffolding. No decoder logic yet. Mirrors Stage 23.1 discipline. |
| **24.2** | Compute-budget + priority-fee decoder. Synthetic fixtures only. Real decoders (the cheapest pair to decode). |
| **24.3** | Jito tip decoder. Synthetic fixtures only. Real decoder. |
| **24.4** | Router / global-fee **candidate** scaffold. Emits `*_CANDIDATE` records for the two active program IDs in §8 with `decoder_status=DECODE_UNCONFIRMED` / `UNSUPPORTED` and an explicit `ROUTER_FEE_CANDIDATE_NO_LAYOUT_EVIDENCE` reason. **No fake decode.** |
| **24.5** | **Confirmed** Axiom / router / global-fee decoder, **only if sanitized real or synthetic fixtures prove the layout** (active program ID, instruction/account layout, fee account movement, lamport/token flow, location of the fee in the transaction). If fixtures do not arrive, 24.5 lands as a documented no-op and 24.6 ships with `decoder_status=DECODE_UNCONFIRMED` for router/global-fee. |
| **24.6** | Unified observe-only runner + artifact writer (manifest, summary, per-primitive JSONL, decoder coverage CSV, rejections JSONL). Deterministic artifacts. Synthetic fixtures + real Stage 22-shaped artifacts (as source material only). |
| **24.7** | Closure audit + Stage 25 handoff doc. Tag `stage-24-closed`. |

Each sub-stage is a bounded, reviewable patch with its own tests, mirroring Stage 22 / Stage 23 discipline.

---

## 6. What is Pure Architecture First

The following pieces land in **24.1** as pure architecture with no decode behavior:

- All closed-set tuples (§12).
- All immutable model `NamedTuple` records (§11).
- The Stage 24 input reader (Stage 24-shaped JSONL → `Stage24ExecutionInput`).
- The Stage 24 manifest record types + canonical serializers.
- The Stage 24 errors module (`Stage24Error` + typed subclasses, mirroring `Stage23Error`).
- The Stage 24 constants forbidden-vocabulary tuple (boundary-scan input), forbidden-routing tuple, forbidden-input-field-substring tuple, forbidden-input-value-substring tuple. Mirrors Stage 23's pattern.
- The Stage 24 redaction-confirmation token vocabulary (no runner sets it at 24.1).
- A locked `STAGE24_VERSION` / `STAGE24_MINOR_VERSION` / `DEFAULT_SCHEMA_VERSION` triple, orthogonal axes for stage version vs schema version vs threshold version.

24.1 ships **zero decoders**. Every decoder Protocol method called on a model returns a deterministic `decoder_status=UNSUPPORTED` placeholder in 24.1 (or 24.1 ships only the contract Protocol with no default implementation — TBD in Appendix A).

---

## 7. What Becomes Real Decoders in Stage 24

The following pieces land in **24.2 / 24.3 / 24.4 / 24.5** as real decoders against fixture-backed evidence:

| Sub-stage | Real decoder | Evidence source |
|-----------|--------------|-----------------|
| **24.2** | ComputeBudget program `SetComputeUnitLimit` / `SetComputeUnitPrice` instructions. Priority fee = `unit_price * unit_limit / 1_000_000`. | Synthetic decoded-tx fixtures with the ComputeBudget program ID, instruction discriminator, and `u32` / `u64` little-endian fields. ComputeBudget is well-documented; no real-fixture dependency. |
| **24.3** | Jito tip — system-transfer instruction whose destination is one of the known Jito tip accounts (the eight standard tip wallets). | Synthetic decoded-tx fixtures with a system-program `Transfer` to a Jito tip account. Jito tip account list is well-known; no real-fixture dependency. The decoder MUST require the tip-account match, not just a "looks like a tip" heuristic. |
| **24.4** | Router / global-fee **candidate** scaffold — recognize the two active Axiom program IDs (§8) when they appear as instruction program IDs, but emit `decoder_status=DECODE_UNCONFIRMED` + `fee_source=ROUTER_FEE_CANDIDATE` / `AXIOM_GLOBAL_FEE_CANDIDATE` + `amount_lamports=None`. No decoded amount. | Synthetic fixtures that include each active program ID as an instruction. No layout decode. |
| **24.5** | Router / global-fee **confirmed** decoder — only lands if a sanitized real (or fixture-proven synthetic) transaction proves: (a) active program ID, (b) instruction / account layout, (c) fee account movement, (d) actual lamport / token flow, (e) instruction location (top-level vs inner vs system-transfer vs token-transfer vs program-instruction-data). | Sanitized real FLASHX8 / Axiom transaction fixtures, redacted to remove operator identity. If unavailable, 24.5 is a documented no-op. |

ExecutionQuality (the §4 primitive) is a **24.6** concern, not a 24.2–24.5 concern, because it composes the per-fee decoders' outputs with submission / landing metadata.

---

## 8. Axiom / Router / Global-Fee Honesty Rules

Stage 24 is honest about what it does and does not know about Axiom and other router-level fees.

### Active program IDs (recognized at 24.4 as candidates, 24.5 as decoded if proven)

- `AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzpgbMG6` — Trading Program 1, active. Maps to `route_family=AXIOM_TRADING_PROGRAM_1`.
- `FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9` — Axiom Trade, active / high-volume. Maps to `route_family=AXIOM_TRADE_FLASHX`.

### Deprecated / excluded program IDs (NOT recognized; map to `route_family=OTHER`)

- `AxiomxSitivYjPjKgJ9XSrdhsydtZssk7TEDam3PxKcC` — deprecated.
- `Axiom3a2w1UbMt2SMgqSvRiuJFTPusDhwKamNgPTeNQ9` — deprecated.

A transaction that touches a deprecated program ID is NOT treated as an Axiom router/global-fee candidate. It is treated as an `OTHER` program and emits a primitive with `decoder_status=NOT_APPLICABLE` for the router-fee family.

### Honesty rules

**DO:**
- Emit `decoder_status=DECODE_UNCONFIRMED` with `fee_source=ROUTER_FEE_CANDIDATE` / `AXIOM_GLOBAL_FEE_CANDIDATE` and `amount_lamports=None` when an active program ID is observed but no layout evidence has been confirmed.
- Emit `decoder_status=ABSENT` when no active program ID is touched at all.
- Emit `decoder_status=NOT_APPLICABLE` when a transaction is malformed at the input layer or its primitive family does not apply.
- Promote a primitive to `decoder_status=DECODED` only when a fixture-backed test asserts the exact (program ID, instruction layout, account layout, lamport/token flow, instruction location) for that fee.

**DO NOT:**
- Emit `decoder_status=DECODED` for any router / global-fee primitive without fixture-backed evidence.
- Use `0` as a stand-in for "unknown router fee". Use `amount_lamports=None` + `decoder_status` that explains the gap.
- Treat a deprecated program ID as an active candidate.
- Make `ROUTER_FEE_CANDIDATE` a `decoder_status`. It is a `fee_source`. The decoder's confidence is recorded separately in `decoder_status`.
- Conflate "we saw the program ID" with "we decoded the fee". The first is a candidate; the second is a confirmed decode.
- Fabricate an `amount_lamports` from heuristics (e.g., the largest non-priority transfer in the tx). If the layout is not proven, the amount is `None`.

---

## 9. Candidate vs Decoded Promotion Criteria

A primitive moves from **candidate** to **decoded** only when ALL of the following are true and a fixture-backed test asserts each:

1. **Active program ID present.** The transaction references one of the two active program IDs in §8 (or a Jito tip account, or the ComputeBudget program, depending on the primitive family).
2. **Instruction layout known.** The instruction's discriminator + account layout + data layout is documented in Stage 24's constants / decoder module, with a citation in a comment to either an official program reference or a sanitized fixture.
3. **Fee account movement observed.** The transaction shows a measurable lamport or token movement attributable to the fee account specified by the layout.
4. **Lamport / token flow extracted.** A specific `amount_lamports` or `(amount_token_units, amount_token_mint)` pair is extractable from the transaction's pre/post balances or instruction data.
5. **Instruction location identified.** The decoder records `instruction_location` from the closed set in §12 — `TOP_LEVEL`, `INNER`, `SYSTEM_TRANSFER`, `TOKEN_TRANSFER`, or `PROGRAM_INSTRUCTION_DATA`. "We don't know where" → not decoded.
6. **Fixture-backed test asserts the full chain.** A Stage 24 test asserts (1)–(5) end-to-end on a fixture and verifies that the emitted `decoder_status=DECODED` with the exact decoded amount.

If any of (1)–(5) is missing, the primitive stays at `decoder_status=DECODE_UNCONFIRMED` / `PARTIAL` / `UNSUPPORTED` and the missing pieces are recorded in `reason_codes`.

This is a one-way promotion. Stage 24 never demotes a `DECODED` primitive to a candidate at runtime; demotion happens by deleting / rewriting the decoder in a future Stage 24.x patch.

---

## 10. Input Artifact Strategy

Stage 24 consumes **transaction-level evidence**. The acceptable input shapes at 24.1 are:

- **Decoded-tx JSONL** — one Solana-style decoded transaction per JSONL row. Each row has at minimum: `signature`, `slot`, `instructions` (list of `{program_id, accounts, data}`), `inner_instructions` (optional), `pre_balances` / `post_balances` (optional), `pre_token_balances` / `post_token_balances` (optional), `meta.fee` (optional), `meta.err` (optional). Fields outside Stage 24's preserved-field allowlist are dropped at read time.
- **Synthetic tx fixtures** — small JSON files mirroring the decoded-tx JSONL shape, written by Stage 24 fixture builders. Used by 24.1–24.4.
- **Stage 22 raw-capture as source material only.** Stage 24 may read `raw_capture.jsonl` artifacts from a prior Stage 22 run **only** as raw material from which a separately-justified Stage 24-shaped decoded-tx JSONL is derived. Stage 24 does NOT directly import the Stage 22 raw payload format into its decoders. Stage 24 modules must NOT import `PHX2.stage22` production modules.
- **Optional sanitized real FLASHX8 / Axiom tx fixtures for 24.5.** Used only to confirm the router/global-fee layout. Real fixtures must be sanitized: no operator identity, no keypairs, no webhook URLs, no API keys, no RPC URLs. Failure of the Stage 24 redaction sweep on any real fixture is a hard test failure; 24.5 cannot land with an unsanitized fixture.

### Stage 24.0 ground rules for inputs

- **No hardcoded live-smoke path.** Tests / fixtures live under the Stage 24 fixtures tree, not under any scratch directory.
- **No live RPC calls** from Stage 24 modules. Ever.
- **No network calls.** No `requests`, `httpx`, `urllib`, sockets, websocket clients, or RPC SDKs.
- **No env reads** inside Stage 24 modules. If a path is needed at runtime, the caller (a separate runner harness) supplies it.
- **Synthetic fixtures first.** 24.2 / 24.3 / 24.4 are built and tested against deterministic synthetic fixtures.
- **Real Stage 22 artifacts later**, for an offline pass in 24.6 — reading the on-disk JSONL from a prior Stage 22 run, *not* triggering Stage 22 from Stage 24.

---

## 11. Output Artifact Plan

Stage 24 writes to a Stage 24 artifact directory **supplied by the caller**, never to a hardcoded path. The locked artifact set:

- `stage24_manifest.json` — combined input + artifact manifest, run metadata, stage version, schema versions, decoder versions, threshold versions, redaction confirmation. Mirrors `stage23_manifest.json`.
- `stage24_summary.json` — per-(primitive_family, fee_source, decoder_status) counts plus per-route_family counts for a run.
- `stage24_execution_primitives.jsonl` — one line per `Stage24ExecutionPrimitive`. Sorted by `(tx_signature, primitive_family, fee_source, primitive_hash)`. The unified view of every primitive the run produced.
- `stage24_compute_budget_results.jsonl` — one line per `Stage24ComputeBudgetResult`. Per-tx compute-budget decoder output. Sorted by `(tx_signature, primitive_hash)`.
- `stage24_priority_fee_results.jsonl` — one line per `Stage24PriorityFeeResult`. Per-tx priority-fee decoder output.
- `stage24_jito_tip_results.jsonl` — one line per `Stage24JitoTipResult`. Per-tx Jito-tip decoder output.
- `stage24_router_fee_results.jsonl` — one line per `Stage24RouterFeeResult` with `decoder_status=DECODED` (24.5 only; empty until 24.5 lands with fixture evidence).
- `stage24_router_fee_candidates.jsonl` — one line per `Stage24RouterFeeResult` with `decoder_status∈{DECODE_UNCONFIRMED, PARTIAL, UNSUPPORTED}`. The candidate side of the router/global-fee surface.
- `stage24_execution_quality_results.jsonl` — one line per `Stage24ExecutionQualityResult`. Per-tx inclusion / landing quality.
- `stage24_decoder_coverage.csv` — per-(primitive_family, decoder_status) coverage matrix. Operator-facing summary of "how much of the run did each decoder confidently decode".
- `stage24_rejections.jsonl` — one line per rejected input row (malformed JSON, forbidden field substring, forbidden value substring, unparsable instruction list). Carries the rejection reason and the row's hash but never the raw value.

All artifacts must pass the redaction tests in §15 / §16. No secret, key, URL, webhook, env value, or unsanitized real operator identity may appear.

The `*_results.jsonl` family is the per-decoder unfiltered view; `stage24_execution_primitives.jsonl` is the unified view a Stage 26 calibrator can read without joining tables.

---

## 12. Proposed Models (names only, no implementation)

Minimal immutable model surface for 24.1 to define:

- `Stage24ExecutionInput` — normalized observation snapshot for one transaction. Projected from a decoded-tx JSONL row by `Stage24InputReader`.
- `Stage24ExecutionPrimitive` — the unified per-primitive record (§3). The disk-shape every decoder eventually feeds into.
- `Stage24ComputeBudgetResult` — per-tx compute-budget decoder output. Carries `unit_limit`, `unit_price_microlamports`, `decoder_status`, `reason_codes`.
- `Stage24PriorityFeeResult` — per-tx priority-fee result. Derived from `Stage24ComputeBudgetResult` (`unit_price * unit_limit / 1_000_000`) when both are decoded.
- `Stage24JitoTipResult` — per-tx Jito-tip decoder output. Carries `tip_account`, `amount_lamports`, `decoder_status`.
- `Stage24RouterFeeResult` — per-tx router / global-fee result. Carries `route_family`, `fee_source`, `program_id`, `instruction_location`, `amount_lamports` / `(amount_token_units, amount_token_mint)`, `decoder_status`. The single record type that spans both 24.4 candidates and 24.5 decoded.
- `Stage24ExecutionQualityResult` — per-tx execution-quality primitive (§4).
- `Stage24RunnerResult` — immutable wrapper bundling all per-decoder result tuples plus aggregated counts. Mirrors `Stage23RunnerResult` discipline.
- `Stage24ArtifactManifest` / `Stage24InputManifest` — manifest record pair (mirrors Stage 23's manifest pair). The brief is one combined `Stage24ArtifactManifest`; for symmetry with Stage 23 the implementation will likely split into input-manifest + artifact-manifest under the same module.

All models immutable (`NamedTuple` or frozen dataclass). All hashing deterministic (sorted keys, canonical JSON). Same logical input → same `input_hash`. Same primitive body → same `primitive_hash`.

---

## 13. Proposed Closed Sets

These are normative for Stage 24. New values require a contract patch. Mirror Stage 23's closed-set discipline.

### `primitive_family`

- `COMPUTE_BUDGET`
- `PRIORITY_FEE`
- `JITO_TIP`
- `ROUTER_FEE`
- `EXECUTION_QUALITY`

### `decoder_status`

- `DECODED`             — full layout decoded; amount extracted.
- `PARTIAL`             — some layout decoded; some fields missing.
- `DECODE_UNCONFIRMED`  — recognized program ID / structure but layout not proven; amount NOT extracted.
- `UNSUPPORTED`         — primitive recognized but decoder not implemented for this case.
- `ABSENT`              — the primitive's source (e.g., ComputeBudget instruction) is not present in this transaction.
- `NOT_APPLICABLE`      — the primitive does not apply to this transaction at all.
- `DECODE_FAILED`       — decoder tried and the input did not match the expected layout (a real decode failure, distinct from `ABSENT`).
- `INPUT_REJECTED`      — the input row was rejected at the reader (redaction sweep, malformed JSON, forbidden substring).

### `data_status`

- `COMPLETE`
- `PARTIAL`
- `MISSING`
- `UNSUPPORTED`

### `confidence_level`

- `HIGH`   — `DECODED`.
- `MEDIUM` — `PARTIAL`.
- `LOW`    — `DECODE_UNCONFIRMED`.
- `NONE`   — `ABSENT` / `NOT_APPLICABLE` / `UNSUPPORTED` / `DECODE_FAILED` / `INPUT_REJECTED`.

A constants test asserts a stable mapping from `decoder_status` to `confidence_level`.

### `fee_source`

- `PRIORITY_FEE_CANDIDATE`        — priority-fee primitive (candidate / decoded).
- `JITO_TIP_CANDIDATE`            — Jito-tip primitive (candidate / decoded).
- `ROUTER_FEE_CANDIDATE`          — router-fee primitive recognized via an active non-Axiom router program.
- `AXIOM_GLOBAL_FEE_CANDIDATE`    — router-fee primitive recognized via one of the two active Axiom program IDs (§8).
- `COMPUTE_BUDGET_UNIT_PRICE`     — compute-budget primitive carrying the unit-price field.
- `COMPUTE_BUDGET_UNIT_LIMIT`     — compute-budget primitive carrying the unit-limit field.
- `NOT_APPLICABLE`                — primitive does not carry a fee-source axis (e.g., execution quality).

`fee_source` is a fee-kind axis. `decoder_status` is a confidence axis. They are orthogonal.

### `route_family`

- `AXIOM_TRADING_PROGRAM_1`  — `AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzpgbMG6` (active).
- `AXIOM_TRADE_FLASHX`       — `FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9` (active).
- `JITO_TIP_ACCOUNT`         — one of the known Jito tip accounts.
- `COMPUTE_BUDGET_PROGRAM`   — the Solana ComputeBudget program.
- `SYSTEM_PROGRAM`           — the Solana System program (used for plain transfers).
- `OTHER`                    — any program ID not in the active set above (including the two deprecated Axiom IDs in §8).
- `UNKNOWN`                  — primitive does not carry a route family.

### `instruction_location`

- `TOP_LEVEL`                — outer instruction in the transaction.
- `INNER`                    — inner instruction emitted by a CPI.
- `SYSTEM_TRANSFER`          — system-program transfer (e.g., Jito tip).
- `TOKEN_TRANSFER`           — SPL-token transfer.
- `PROGRAM_INSTRUCTION_DATA` — fee encoded in the program's own instruction data field.
- `NOT_APPLICABLE`           — primitive does not carry an instruction location.

### `input_kind`

- `DECODED_TX_JSONL`          — Stage 24-shaped decoded transaction JSONL (the canonical input).
- `SYNTHETIC_TX_FIXTURE`      — synthetic fixture used by 24.2 / 24.3 / 24.4 tests.
- `SANITIZED_REAL_TX_FIXTURE` — sanitized real transaction fixture used by 24.5 only.

Constants module must export each closed set as a frozen tuple and a closed-set test must assert no drift.

---

## 14. Missing / Unsupported Semantics

Stage 24 is honest about what it does and does not know. Mirrors the Stage 23 missing-primitive policy.

**DO:**
- Emit `decoder_status=ABSENT` when the primitive's source (e.g., ComputeBudget instruction, Jito tip transfer) is not in the transaction at all. `ABSENT` is a real, recorded observation.
- Emit `decoder_status=NOT_APPLICABLE` when the primitive does not apply (e.g., asking for a Jito tip on a transaction that does not pay one is `ABSENT`; asking for it on a malformed input row is `NOT_APPLICABLE`).
- Emit `decoder_status=DECODE_FAILED` when the decoder tried and the input did not match the layout. Distinct from `ABSENT`.
- Emit `decoder_status=DECODE_UNCONFIRMED` when the program / account is recognized but the layout is not proven (24.4 router/global-fee case).
- Emit `decoder_status=PARTIAL` when some layout decoded and some fields are missing.
- Emit `decoder_status=UNSUPPORTED` when the primitive is recognized but the decoder is not implemented for this case yet (e.g., 24.5 not landed → router-fee promotion is `UNSUPPORTED`).
- Emit `decoder_status=INPUT_REJECTED` when the input row failed the redaction sweep or could not be parsed. The rejection is recorded in `stage24_rejections.jsonl`.
- Always populate `reason_codes` explaining *what* was missing and *why* the status is what it is.
- Still produce a deterministic `Stage24ExecutionPrimitive` for partial / absent / unsupported cases — partial does not mean skip.

**DO NOT:**
- Substitute `0` for a missing Jito tip. `amount_lamports=None` + `decoder_status=ABSENT` is the honest record.
- Substitute `0` for an unknown router / global fee. `amount_lamports=None` + `decoder_status=DECODE_UNCONFIRMED` is the honest record.
- Conflate `ABSENT` (we looked, it wasn't there) with `UNSUPPORTED` (we don't know how to look yet) with `DECODE_FAILED` (we looked and the input didn't match) with `NOT_APPLICABLE` (this primitive doesn't apply to this kind of row) with `DECODE_UNCONFIRMED` (we saw the right program but didn't decode the layout) with `PARTIAL` (we decoded some fields but not all). These are six different states and Stage 24 distinguishes them.
- Silently drop a transaction without emitting a primitive. Every input row produces records for every primitive family (one per family).
- Invent a `confidence_level` that doesn't follow the `decoder_status` mapping in §13.
- Use `HIGH` confidence as a default when the decoder is uncertain.

---

## 15. Fixture Strategy

Stage 24 uses a layered fixture strategy:

- **Synthetic decoded-tx fixtures for 24.1.** Tiny JSON files exercising the input-reader contracts: malformed JSON, missing required fields, forbidden field substrings, forbidden value substrings, oversized rows. No decoder logic exercised; just the reader / contract surfaces.
- **Synthetic decoded-tx fixtures for 24.2.** Small JSON files with the ComputeBudget program ID, the `SetComputeUnitLimit` / `SetComputeUnitPrice` instruction discriminators, and known `u32` / `u64` little-endian fields. Edge cases: no compute-budget instructions (→ `ABSENT`), only unit-limit (→ `PARTIAL`), invalid discriminator (→ `DECODE_FAILED`).
- **Synthetic decoded-tx fixtures for 24.3.** Small JSON files with a system-program `Transfer` to a Jito tip account. Edge cases: tip to a non-Jito wallet (→ `ABSENT`), zero-amount transfer (→ `PARTIAL` or `ABSENT` with a documented choice), multiple tips in one tx (→ a recorded reason code).
- **Synthetic decoded-tx fixtures for 24.4.** Small JSON files referencing each active Axiom program ID (§8) as an instruction. Decoder emits `decoder_status=DECODE_UNCONFIRMED` + `fee_source=AXIOM_GLOBAL_FEE_CANDIDATE` + `amount_lamports=None`. Edge cases: deprecated program ID in the tx (→ `route_family=OTHER`, `decoder_status=NOT_APPLICABLE` for router-fee).
- **Sanitized real (or fixture-proven synthetic) Axiom / FLASHX8 transactions for 24.5.** Required only if 24.5 is to land with `decoder_status=DECODED` records. Each fixture must:
  - Reference one of the two active program IDs (§8).
  - Be redacted to remove any operator keypair / API key / webhook / RPC URL / scratch-directory path.
  - Carry a documented `(program_id, instruction_layout, account_layout, fee_account, lamport_or_token_flow, instruction_location)` chain that the 24.5 decoder asserts in its tests.

If 24.5 fixtures do not arrive, **24.5 lands as a documented no-op**: the router/global-fee surface stays at `decoder_status=DECODE_UNCONFIRMED` and the 24.6 runner emits empty `stage24_router_fee_results.jsonl`. The Stage 24 closure audit must explicitly call out this state.

---

## 16. Test Strategy by Sub-Stage

Stage 24.0 ships no tests. The list below is the contract for 24.1+.

### Cross-cutting (asserted at every sub-stage)

- Constants closed-set tests (no drift in `primitive_family` / `decoder_status` / `data_status` / `confidence_level` / `fee_source` / `route_family` / `instruction_location` / `input_kind`).
- Immutable model tests (`NamedTuple` frozen, no `setattr`).
- Deterministic hashing tests (same input → same `input_hash`; same primitive body → same `primitive_hash`).
- Artifact writer deterministic ordering tests (stable sort keys, stable JSON serialization).
- Secret-leak / redaction tests (no Helius key, no RPC URL, no Discord webhook, no env values ever appear in artifacts).
- No-env-read tests (static-import scan / runtime guard for `os.environ` usage in Stage 24 modules).
- No-network-call tests (static-import scan / runtime guard for `requests`, `httpx`, `urllib`, `socket`, websocket / RPC clients in Stage 24 modules).
- No-Stage-21/22/23-production-mutation tests (Stage 24 modules must not import-and-write Stage 21 / Stage 22 / Stage 23 ledgers or contracts).
- No-Birdeye / Dexscreener / ATH / migration import tests (Stage 25 vocabulary forbidden in Stage 24 source).
- No-X / social import tests (Stage 27+ vocabulary forbidden).
- No-Discord / Telegram / public-routing / paid-signal / subscriber import tests.
- No-enforce / gate / block identifier tests (Stage 26 vocabulary forbidden in Stage 24 source).

### 24.1

- Closed-set tests above for every Stage 24 closed-set tuple.
- Model immutability tests for every `Stage24*` record.
- Input reader malformed JSONL tests (skip-with-reason, never crash; rejected rows go to `stage24_rejections.jsonl`).
- Input reader forbidden-field-substring / forbidden-value-substring rejection tests.
- Manifest record canonical-JSON tests (byte-stable for identical manifests).
- Stage 24 boundary scanner asserting no Stage 24 module imports Stage 21 / Stage 22 / Stage 23 production modules.
- Stage 24 forbidden-vocabulary scanner asserting Stage 25 / Stage 26 / Stage 27 vocabulary does not appear as identifier positions in Stage 24 source.

### 24.2

- ComputeBudget decoder tests against synthetic fixtures: `DECODED` (both unit-limit and unit-price present), `PARTIAL` (one present), `ABSENT` (neither), `DECODE_FAILED` (bad discriminator).
- Priority-fee derivation tests (`unit_price * unit_limit / 1_000_000` arithmetic correct; rounding documented).
- Edge: multiple `SetComputeUnitLimit` instructions in one tx — documented choice (last-write-wins vs reject-with-reason).

### 24.3

- Jito tip decoder tests against synthetic fixtures: `DECODED` (tip to a Jito tip account), `ABSENT` (tip to a non-Jito wallet), `DECODE_FAILED` (malformed transfer instruction).
- Multiple-tip-in-one-tx test (documented choice: sum-and-record, with a reason code).
- Jito tip account list lockdown test (the eight standard tip wallets, as a frozen tuple; no drift).

### 24.4

- Router / global-fee candidate scaffold tests: an active Axiom program ID present → `decoder_status=DECODE_UNCONFIRMED` + `fee_source=AXIOM_GLOBAL_FEE_CANDIDATE` + `amount_lamports=None`.
- Deprecated Axiom program ID present → `route_family=OTHER` + `decoder_status=NOT_APPLICABLE` for router-fee. Asserts the deprecated IDs from §8 are NOT treated as candidates.
- No active program → `decoder_status=ABSENT`.
- The candidate writer must NOT emit any decoded amount.

### 24.5 (conditional on real / synthetic fixture evidence)

- For each landed real / synthetic Axiom fixture: end-to-end fixture-backed test asserting `decoder_status=DECODED` + exact `amount_lamports` (or `(amount_token_units, amount_token_mint)`) + exact `instruction_location` + exact `program_id` + exact `route_family`.
- A "fixture evidence inventory" test asserting that every `decoder_status=DECODED` router/global-fee primitive in the test suite is backed by a documented fixture in the Stage 24 fixtures tree.
- A regression test asserting that adding a *new* active program ID to the constants requires a new fixture before the constants test passes.

### 24.6

- Runner output tests: synthetic input → expected `Stage24RunnerResult` with the right per-family counts.
- Artifact writer round-trip tests: write all 10 artifacts, read back, assert byte-stability across two runs with identical inputs and identical injected clock.
- Redaction sweep test on every emitted artifact: no forbidden substring (URL schemes, webhook hosts, API key shapes, long hex / token-ish runs above the locked thresholds).
- Empty-input test: zero rows → all 10 artifacts written with zero data rows but valid headers / manifests.
- Decoder coverage CSV test: per-(primitive_family, decoder_status) counts add up to the per-family input row count.

### 24.7

- Closure audit test pinning the five short SHAs for 24.1–24.5 (with 24.5 marked no-op-if-no-fixtures).
- Final boundary scan: Stage 24 imports nothing from Stage 25 / Stage 26 / Stage 27 vocabulary, no `enforce` / `gate` / `block` / `dispatch` / `alert` identifiers, no `axiom` literal claims of `DECODED` without a fixture-backed test.

---

## 17. Codex Audit Checklist Before Stage 24 Closure

Mirrors the Stage 23 closure-audit discipline. Before tagging `stage-24-closed`:

1. **All 24.1–24.6 sub-stages landed** with their own tests; 24.7 carries the closure audit and the Stage 25 handoff doc.
2. **Test count and skip count** documented in the audit (mirror Stage 23's 764 passed / 1 skipped pin).
3. **Module inventory pinned**: every file under `PHX2/stage24/` listed with one-line purpose.
4. **Commit chain pinned**: the five short SHAs for 24.1 / 24.2 / 24.3 / 24.4 / 24.5 (with 24.5 marked as no-op if it landed without fixtures) plus 24.6.
5. **Closed-set lockdown**: every closed-set tuple in §13 asserted by a constants test.
6. **Honesty claim audit**: every `decoder_status=DECODED` test points to a fixture; every `*_CANDIDATE` test asserts `amount_lamports=None` for the unknown-amount case.
7. **No-fake-zero audit**: a grep over `stage24_*_results.jsonl` golden fixtures asserts no `amount_lamports=0` for the Jito-tip / router-fee cases unless paired with a `decoder_status=DECODED` and a real zero-amount transfer (e.g., a documented edge case).
8. **No Stage 21 / Stage 22 / Stage 23 production imports** in Stage 24 modules. The boundary scanner asserts this.
9. **No Stage 25 / Stage 26 / Stage 27 vocabulary** in Stage 24 identifier positions. The forbidden-vocabulary scanner asserts this.
10. **No env reads, no network calls, no DB writes, no CLI run loop.** Static-import scan + runtime guards.
11. **Redaction sweep** on every emitted artifact: no URL schemes, no webhook hosts, no API key shapes, no long token-ish runs above the locked thresholds.
12. **Active program ID set matches §8.** A constants test pins the two active Axiom IDs and the two deprecated IDs. Adding a new active ID requires a new fixture and a new test.
13. **Stage 25 handoff doc written** (`PHX2/stage24/STAGE_25_HANDOFF.md`) and `PHX2/stage24/STAGE_24_CLOSURE_AUDIT.md` written, mirroring the Stage 23 closure pair.
14. **No push, no force-push** as part of the audit. The audit runs against a local working tree.

---

## 18. Stage 25 / 26 / 27 Deferrals

- **Stage 25** — ATH / migration measurement hardening, Birdeye / Dexscreener / external-reference integration. (Not Stage 24.)
- **Stage 26** — Calibration / enforcement candidates. Decides which Stage 23 labels and which Stage 24 primitives become actionable thresholds, and which families to actually act on. Stage 24 emits the evidence; Stage 26 decides what to do with it.
- **Stage 27+** — X / social intelligence sidecar. Independent input source, never mixed into Stage 24.

Stage 24 emits the execution-fee and execution-quality evidence. Stages 26+ decide what to do with it.

---

## 19. Why Stage 24.1 Can Start Before Real Axiom Fixtures Are Collected

Stage 24.1 is the contract / model / input-reader / manifest scaffolding sub-stage. It does **not** need real Axiom or FLASHX8 transaction fixtures. Specifically:

- 24.1 ships closed sets, immutable models, the input reader, and the manifest types. No decoder.
- 24.2 ships the compute-budget + priority-fee decoder. Compute-budget is a public Solana program with well-documented layouts; synthetic fixtures are sufficient. No Axiom dependency.
- 24.3 ships the Jito tip decoder. Jito tip accounts are well-known; synthetic system-transfer fixtures are sufficient. No Axiom dependency.
- 24.4 ships the router / global-fee **candidate** scaffold. It only needs synthetic fixtures referencing the two active Axiom program IDs (§8) as instruction program IDs. It does NOT decode the fee. No real-fixture dependency.
- 24.5 is the **only** sub-stage that depends on sanitized real (or fixture-proven synthetic) Axiom / FLASHX8 transactions. If those fixtures do not arrive, 24.5 lands as a documented no-op and Stage 24 still ships 24.6 / 24.7 with the router/global-fee surface stable at `decoder_status=DECODE_UNCONFIRMED`.

In short: **Stage 24.1 can start immediately**, in parallel with any effort to collect sanitized real fixtures for 24.5. The fixtures only become a blocker at the 24.5 boundary.

---

## 20. Output Format & Anti-Goals

**Format guidance for future Stage 24 docs and code:**
- Practical and implementation-ready, not aspirational.
- Headings, bullets, explicit **DO / DO NOT** sections.
- Closed sets first, behavior second, implementation last.
- Mirror the Stage 23 brainstorm / closure-audit / handoff structure.

**Anti-goals for Stage 24 (repeat for emphasis):**
- Stage 24 is **not** ATH / migration / Birdeye / Dexscreener.
- Stage 24 is **not** calibration / enforcement / threshold tuning for action.
- Stage 24 is **not** X / social intelligence.
- Stage 24 is **not** monetization.
- Stage 24 is **not** subscriber routing.
- Stage 24 is **not** enforcement.
- Stage 24 does **not** rewrite the roadmap.
- Stage 24 does **not** edit Stage 21 / Stage 22 / Stage 23 modules.
- Stage 24 does **not** claim `DECODED` for any router / global-fee primitive without fixture-backed evidence.
- Stage 24 does **not** use `0` as a stand-in for "unknown".

---

## Appendix A — Open Questions for Stage 24.1

Resolve these before 24.1 starts coding:

1. Final concrete path layout under `PHX2/stage24/` (mirror Stage 23's flat module layout?).
2. Whether `Stage24ExecutionInput` is per-transaction or per-(tx_signature, primitive_family). Likely per-transaction for 24.2–24.5 with per-family fan-out done in the runner at 24.6.
3. Canonical JSON serialization choice (sorted keys + UTF-8). Confirm whether Stage 23's `canonical_json` helper is acceptable as a Stage 24-local duplicate (mirroring Stage 23's deliberate copy of Stage 22's helper) rather than an import.
4. Clock injection convention (Stage 22 / Stage 23 pattern: caller supplies `created_at_utc`).
5. Whether the Stage 24 decoder Protocol is shipped at 24.1 (contract surface only, no decoders) or at 24.2 alongside the first decoder.
6. Fixture directory location and whether fixtures ship with the repo (recommend: yes, small synthetic JSON only at 24.1–24.4; sanitized real fixtures decided per 24.5).
7. Whether `Stage24RouterFeeResult` is a single type spanning candidate + decoded, or two types. Recommend single type with `decoder_status` doing the work (matches §13).
8. Exact set of Jito tip accounts to lock in 24.3 constants (the eight standard tip wallets, frozen tuple; document the source of the list in a code comment, not a network call).
9. Threshold-version axis name and initial value for Stage 24 (Stage 23 used `"thresholds_v0_observe_only"`; Stage 24 likely needs its own initial axis even though 24.1–24.5 have no thresholds — reserves the axis for Stage 26).
10. Whether 24.6 ships a separate runner module or extends the input-reader / writer pair (recommend separate runner module, mirroring Stage 23's `runner.py`).
