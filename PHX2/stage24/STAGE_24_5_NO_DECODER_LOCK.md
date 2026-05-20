# PHX2 Stage 24.5 — No-Confirmed-Decoder Lock (Path B)

**Status:** lock document. No confirmed Axiom / router / global-fee decoder lands at Stage 24.5.
**Predecessors:** Stage 24.0 (`3957347`), 24.1 (`a0ce8d8`), 24.2 (`107fc3b`), 24.3 (`a593cf7`), 24.4 (`cd8d7a8`).
**Stage 24.4 final tests at lock time:** 375 passed.
**Source-of-truth contract for router/global-fee:** Stage 24.4 candidate-only semantics in `PHX2/stage24/router_fee.py`.

---

## 1. Stage 24.5 took Path B

Stage 24.5 took **Path B** of the Stage 24 brainstorm doc (`PHX2/docs/STAGE_24_BRAINSTORM.md`, §5 / §15 / §19).

Path A would have promoted the router/global-fee primitive from candidate to `decoder_status=DECODED`, but only if sanitized real (or fixture-proven synthetic) Axiom / FLASHX8 transactions proved the instruction layout, account layout, fee-account movement, lamport / token flow, and instruction location. None of that proof has arrived. Stage 24.5 therefore lands as a documented no-op for the confirmed-decoder surface and preserves the 24.4 candidate-only contract verbatim.

## 2. No confirmed Axiom / router / global-fee decoder exists

There is **no confirmed** Axiom, router, or global-fee decoder in the Stage 24 tree at the close of Stage 24.5.

`PHX2/stage24/router_fee.py` carries only the 24.4 candidate scaffold: `decode_router_fee_candidate(execution_input)`. It does NOT contain `decode_router_fee_confirmed`, `decode_axiom_global_fee`, or any other symbol that promotes a router/global-fee primitive to `decoder_status=DECODED`. The decoder name and version axes are pinned to `router_fee_candidate_v0` / `stage24_v0_router_fee_candidate`.

## 3. Stage 24.4 candidate-only semantics remain the truth

Every router/global-fee primitive emitted by the Stage 24 tree at the close of 24.5 carries:

- `decoder_status` ∈ `{ABSENT, UNSUPPORTED, DECODE_UNCONFIRMED}` — **never `DECODED`**.
- `amount_lamports` is `None` — **never zero as a stand-in**, never a heuristic fabrication.
- `amount_token` is `None`; `mint` is `""`.
- `fee_source` ∈ `{UNKNOWN, ROUTER_FEE_CANDIDATE, AXIOM_GLOBAL_FEE_CANDIDATE}` — **never `AXIOM_GLOBAL_FEE`**, never `ROUTER_FEE`.

This is the existing Stage 24.4 contract; Stage 24.5 does not change router_fee.py and does not weaken it.

## 4. Current fixture inventory

At the close of Stage 24.5:

| Category | Count |
|---|---:|
| Sanitized real FLASHX8 fixtures | **0** |
| Sanitized real Axiom Trading Program 1 fixtures | **0** |
| Confirmed fee-recipient layouts | **0** |
| Confirmed balance-reconciliation paths | **0** |

The `INPUT_KIND_SANITIZED_REAL_DECODED_TX_JSONL` axis remains reserved in `PHX2/stage24/constants.py` for future Path A but no caller produces it and no file under `PHX2/tests/stage24/fixtures/` carries the `sanitized` / `axiom_capture` / `flashx8_capture` substring.

## 5. Six required proof criteria — all unmet

Brainstorm §9 requires all six of the following for a router/global-fee promotion. At the close of Stage 24.5, each is explicitly unmet:

- [ ] **Active router program ID confirmed in real fixtures.** Both active IDs are recognized as candidates in `ACTIVE_AXIOM_ROUTER_PROGRAM_IDS`, but no sanitized real transaction touching either ID has landed in the fixtures tree.
- [ ] **Instruction / account layout understood.** No discriminator constant, no Anchor selector, no account-positional schema is documented anywhere in `PHX2/stage24/`.
- [ ] **Fee account movement identified.** No code path consults `pre_balances` / `post_balances` for router-fee attribution. The 24.4 numeric features count *candidate* transfers; they do not attribute amount.
- [ ] **Lamport / token flow reconciled.** No reconciliation path exists. `amount_lamports` and `amount_token` are unconditionally `None` for every router-fee primitive.
- [ ] **Fee location identified.** Every active-router result hard-codes `instruction_location=TOP_LEVEL`; the closed set's other locations (`INNER`, `BALANCE_DELTA`, `TOKEN_BALANCE_DELTA`) are not used by the router decoder.
- [ ] **Negative / lookalike fixtures reject false positives.** No sanitized real or layout-proving synthetic negatives have landed. The 24.4 negatives only exercise the shape scanner, not a decode rejection.

## 6. What future Path A would require

If a future Stage 24.x sub-stage attempts Path A, the lock test in `PHX2/tests/stage24/test_stage_24_5_no_confirmed_router_fee_decoder.py` is the explicit drift point. To clear it, the patch must land all of the following together:

- **At least 3 successful sanitized real FLASHX8 fixtures** across different swap shapes (e.g. different notional sizes, different mints, different block ranges) so a single-tx coincidence cannot anchor the layout claim.
- **At least 3 successful sanitized real Axiom Trading Program 1 fixtures** with the same diversity bar. A layout proven only for FLASHX8 does not promote Trading Program 1, and vice versa.
- **Failed-tx negatives** for each active route family (`transaction_status != "success"`) to confirm a failed tx never produces `decoder_status=DECODED` even when the data shape would have matched.
- **Deprecated-router negatives** confirming `route_family=DEPRECATED_AXIOM` stays `UNSUPPORTED` even when a fee-shaped transfer happens to co-occur.
- **Lookalike transfer negatives** — txs that touch an active router AND carry a non-router transfer of approximately fee-sized lamports to an unrelated account, to confirm the decoder does not grab the largest non-priority transfer as the fee.
- **Pre/post balance reconciliation** — an account-delta path that computes `post_balances[i*] − pre_balances[i*]` against the hypothesized fee-account index and confirms the delta after subtracting `meta.fee`, the Jito tip, and any rent transfers.
- **Inner / top-level transfer reconciliation**, if the layout places the fee in an inner CPI or a top-level System transfer. The decoder must surface `instruction_location` from the closed-set (`TOP_LEVEL`, `INNER`, `BALANCE_DELTA`, `TOKEN_BALANCE_DELTA`) per the actual evidence path, not a hard-coded default.

Both reconciliation paths (account-delta and inner-CPI transfer) must agree on at least two of the three real fixtures per active program before the decoder is allowed to emit `decoder_status=DECODED`.

## 7. Honesty claims preserved at Stage 24.5

- Unknown router / global fee remains `amount_lamports=None`.
- **No fake zero.** A missing or unknown router-fee amount is never substituted with `0`. The candidate result records `None` plus a documented `decoder_status` and `reason_codes`.
- **No `DECODED` router_fee status.** No router-fee primitive carries `decoder_status=DECODED` at the close of Stage 24.5.
- **No `AXIOM_GLOBAL_FEE` fee_source.** The decoded fee-source axis value `AXIOM_GLOBAL_FEE` remains reserved in the closed set; no Stage 24 code emits it. Only the `_CANDIDATE` variants are emitted by the live decoder.
- **Candidate labels only.** Active-router primitives carry `AXIOM_GLOBAL_FEE_CANDIDATE` or `ROUTER_FEE_CANDIDATE` and never the confirmed variants.

## 8. Stage 24.6 runner / writer guidance

When Stage 24.6 lands the unified runner + artifact writer, the router/global-fee surface must:

- Emit the per-tx `Stage24RouterFeeResult` rows produced by the 24.4 candidate decoder verbatim into `stage24_router_fee_candidates.jsonl`.
- Leave `stage24_router_fee_results.jsonl` **empty** (header / no data rows), since no confirmed router/global-fee primitive exists.
- Include `STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER=False`, `STAGE_24_5_REAL_FIXTURE_COUNT=0`, and `STAGE_24_5_CONFIRMED_LAYOUT_COUNT=0` in the artifact manifest's decoder-state block so downstream readers see the no-confirmed-decoder state explicitly.
- Not invent a `DECODED` router-fee row from any heuristic; the 24.6 runner is a writer, not a decoder, and must not promote candidate rows.

The 24.6 manifest summary for the router/global-fee family is therefore: **candidate artifacts only**, zero confirmed decoded global fees, with the per-(primitive_family, decoder_status) coverage matrix recording the candidate distribution honestly.
