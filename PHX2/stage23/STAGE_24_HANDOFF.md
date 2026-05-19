# Stage 24 handoff

Closing stage: Stage 23 (core on-chain filters, observe-only
rebuild). See [STAGE_23_CLOSURE_AUDIT.md](STAGE_23_CLOSURE_AUDIT.md)
for the closing audit.

This document is a forward-looking scope note. **It is not a
commitment**; Stage 24 starts with its own brainstorm /
planning artifact, just as Stage 23 did
(`PHX2/docs/STAGE_23_BRAINSTORM.md`). What follows is a sketch
the Stage 24 author should consult, accept, or amend before
landing 24.1.

## 1. Stage 24 purpose

Stage 24 introduces **execution-fee and execution-quality
primitives** to PHX2. The Stage 23 surface answers "what does
this token's holder / launch / wallet-source shape look like?".
Stage 24's surface answers "what does the execution path on a
Solana submission cost in terms of priority fee / Jito tip /
compute budget, and what is the inclusion / execution quality
we observe?".

Execution fees and execution quality are separate concerns from
the Stage 23 filter labels and feed into a different future
calibration loop. They are also separate from Stage 25 ATH /
migration measurement primitives, Stage 26 calibration /
enforcement, and Stage 27+ X / social work.

## 2. Stage 24 likely primitives

Stage 24 is expected to add observe-only readers / decoders /
recorders for:

  * **Axiom / global-fee amount.** The router-level "global fee"
    paid into a Solana program's fee account, when it can be
    decoded from a transaction's instructions.
  * **Priority fee.** The Solana priority-fee primitive
    (microlamports per compute unit), read off the transaction
    or estimated from recent block-level priority-fee
    distributions.
  * **Jito tip.** The Jito tip transfer amount, when present,
    read off the Jito tip account transfers in the transaction.
  * **Compute budget.** The compute-budget program limits and
    requested units, read off the transaction's
    compute-budget instructions.
  * **Execution quality / inclusion quality.** A composite
    observation of whether a submitted transaction landed, in
    what slot, with what slot-delta from estimate, and at what
    realized fee.
  * **Router / global-fee decoder, if appropriate.** A
    deterministic instruction decoder for the global-fee
    program, factored carefully so it does NOT pull in any RPC
    client.

All Stage 24 primitives should be observe-only at first land.

## 3. Stage 23 artifacts as Stage 24 context

Stage 24 should treat Stage 23 artifacts as **read-only
context**. The Stage 23 evaluation JSONL
(`stage23_filter_evaluations.jsonl`), summary CSVs
(`stage23_filter_summary.csv`,
`stage23_reason_code_counts.csv`,
`stage23_data_status_counts.csv`,
`stage23_label_counts.csv`), and manifest
(`stage23_manifest.json`) are valid inputs to a future
Stage 24-aware analyzer.

Stage 24 **must not mutate Stage 23 artifacts or contracts**:

  * Stage 24 must not re-open `PHX2/stage23/constants.py`,
    `PHX2/stage23/models.py`,
    `PHX2/stage23/filter_contracts.py`,
    `PHX2/stage23/runner.py`, or
    `PHX2/stage23/artifact_writer.py`.
  * Stage 24 must not add a member to any closed-set Stage 23
    tuple (`LABELS`, `DATA_STATUSES`, `FILTER_FAMILIES`,
    `INPUT_KINDS`).
  * Stage 24 must not change the locked Stage 23 artifact
    filenames or schema versions.
  * Stage 24 must not change the deterministic-hash bodies
    (`compute_input_hash` / `compute_evaluation_hash`).

If a Stage 24 primitive needs a Stage 23 contract change, the
change is its own separately-justified sub-stage, NOT a Stage 24
side-effect.

## 4. Stage 24 should remain observe-first

Like Stage 23, Stage 24 should land **observe-first**: every
Stage 24 primitive should ship as a pure projection / decoder
that emits structured records onto disk and never blocks,
gates, routes, dispatches, or alerts. A Stage 24 record is
evidence, not a decision.

Promotion of any Stage 24 primitive to enforcement is a Stage 26
concern; it is out of scope for the Stage 24 land itself.

## 5. Stage 24 should NOT do

Stage 24's scope is execution-fee and execution-quality
primitives. The following are explicitly out of Stage 24:

  * **ATH / migration hardening — Stage 25.** Stage 25 owns
    all-time-high tracking, migration-event hardening, and the
    associated Birdeye / Dexscreener / external-reference
    integration policy.
  * **Calibration / enforcement — Stage 26.** Stage 26 owns
    threshold calibration against labeled ground truth and the
    promotion of observe-only filters to enforcement /
    blocking. Stage 24 does not block.
  * **X / social — Stage 27+.** Stage 27 and later own X API
    integration, social-graph scoring, and social-intel
    primitives. Stage 24 does not import any X API or social
    library.
  * **Public / subscriber routing.** Stage 24 does not add any
    Discord / Telegram / subscriber / public-channel /
    paid-signal routing. The PHX2 routing surface is reserved
    for a separately-justified later stage.

## 6. Stage 24 must preserve filter_version vs threshold_version separation

Stage 23 ships two version axes on every emitted record:

  * `filter_version` — the implementation-version axis for a
    filter / decoder.
  * `threshold_version` — the threshold-configuration axis
    locked at Stage 23 to `"thresholds_v0_observe_only"`.

Stage 24 should preserve this two-axis discipline for its own
execution-fee / execution-quality primitives. A Stage 24
primitive that depends on a threshold value MUST carry a
`threshold_version` axis distinct from its `filter_version`
axis so a future Stage 26 calibration pass can re-tune
thresholds without bumping the implementation axis.

## 7. Stage 24 should use missing/unsupported semantics rather than fake confidence

Stage 23 emits explicit `MISSING_INPUT` / `INSUFFICIENT_DATA` /
`UNKNOWN` labels with explicit `MISSING` / `PARTIAL` /
`UNSUPPORTED` data statuses when input primitives are absent.
`NORMAL` is never the default for "we don't know".

Stage 24 should adopt the same semantics for its execution-fee /
execution-quality records: a transaction that did not carry a
Jito tip should yield a `MISSING` / `UNSUPPORTED` record (or
its Stage 24 equivalent) rather than a fabricated zero. Stage
24 should be honest about what it does not know; downstream
calibration depends on that honesty.

## 8. Stage 24 should not rewrite Stage 21/22/23 closed contracts

The following closed contracts are sealed and Stage 24 must not
rewrite them unless a separately-justified contract patch lands
first:

  * Stage 21 capture / decode contract surfaces.
  * Stage 22 ingestion / dedupe / raw-capture contract surfaces.
  * Stage 23 filter / input-reader / manifest / runner /
    artifact-writer contract surfaces.

Stage 24 reads Stage 22 / Stage 23 artifacts; it does not modify
them. Stage 24 must not add `PHX2.stage21` / `PHX2.stage22` /
`PHX2.stage23` production imports to its own modules unless a
separately-justified cross-stage import policy is established
first.
