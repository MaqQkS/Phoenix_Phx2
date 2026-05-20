# Stage 25 handoff

Closing stage: Stage 24 (execution-fee and execution-quality
primitive foundation, observe-only). See
[STAGE_24_CLOSURE_AUDIT.md](STAGE_24_CLOSURE_AUDIT.md) for the
closing audit.

This document is a forward-looking scope note. **It is not a
commitment**; Stage 25 starts with its own brainstorm /
planning artifact, just as Stage 23 and Stage 24 did. What
follows is a sketch the Stage 25 author should consult, accept,
or amend before landing 25.1.

## 1. Stage 25 purpose

Stage 25 introduces **ATH / migration measurement hardening**
to PHX2. The Stage 23 surface answers "what does this token's
holder / launch / wallet-source shape look like?". The Stage 24
surface answers "what does the execution path on a Solana
submission cost (priority fee / Jito tip / router-fee
candidate / compute budget) and what is the inclusion / landing
quality we observe?". Stage 25's surface answers "what does the
post-launch / post-migration peak look like, and how do we
reconcile that observation across independent source providers
deterministically?".

ATH (all-time-high) and migration-event measurement are the
Stage 25 mission. The Stage 25 land is observe-only at first;
calibration / enforcement is deferred to Stage 26, and X /
social-intelligence is deferred to Stage 27+.

## 2. What Stage 25 should consume from Stage 24

Stage 25 treats the Stage 24 artifacts as **read-only context**.
The Stage 24 artifact set (locked in
`PHX2/stage24/constants.py` and emitted by
`PHX2/stage24/artifact_writer.py`) is a valid input to a future
Stage 25-aware analyzer:

  * **Execution-primitive artifacts.**
    `stage24_execution_primitives.jsonl`,
    `stage24_compute_budget_results.jsonl`,
    `stage24_priority_fee_results.jsonl`,
    `stage24_jito_tip_results.jsonl`,
    `stage24_router_fee_results.jsonl`,
    `stage24_router_fee_candidates.jsonl`,
    `stage24_execution_quality_results.jsonl`. Stage 25 should
    read these by field-name only via a Stage 25-shaped
    projection step; Stage 25 must not import Stage 24
    production modules.
  * **Run-level summary and coverage artifacts.**
    `stage24_summary.json` (per-(primitive_family,
    decoder_status) counters plus the router-fee
    candidate / confirmed split) and `stage24_decoder_coverage.csv`
    (per-(primitive_family, decoder_status, data_status)
    coverage matrix) give Stage 25 a deterministic per-run
    surface to gate its own measurement quality without
    re-counting the JSONL rows.
  * **Rejection artifacts.** `stage24_rejections.jsonl` carries
    one row per Stage 24 input rejected by a decoder's typed
    error path. Stage 25 should treat a rejected Stage 24 input
    as missing context for its own measurement records rather
    than re-deriving the rejection reason from the source.
  * **Priority-fee / Jito / router-fee candidate context.** A
    transaction whose Stage 24 surface shows a `PARTIAL`
    priority-fee primitive, a present Jito tip, or an
    `AXIOM_GLOBAL_FEE_CANDIDATE` router-fee primitive carries
    useful context for a Stage 25 ATH-window measurement: it
    helps explain why a specific submission landed (or didn't)
    at the slot Stage 25 cares about. Stage 25 treats this
    context as diagnostic, not as a threshold input.
  * **Execution-quality context.**
    `stage24_execution_quality_results.jsonl` carries
    `landed` / `landed_slot` / `submitted_slot` / `slot_delta`
    plus the realized priority-fee / Jito-tip / router-fee
    amounts (when decoded). Stage 25 should use this to
    diagnose transaction quality around the
    migration / ATH window without re-deriving inclusion
    metrics from raw transactions.
  * **Stage 24 manifest.** `stage24_manifest.json` carries the
    runner / writer versions, the Stage 24.5 lock scalar
    markers
    (`stage_24_5_has_confirmed_router_fee_decoder`,
    `stage_24_5_real_fixture_count`,
    `stage_24_5_confirmed_layout_count`), and every artifact's
    SHA-256. Stage 25 should pin the Stage 24 manifest hash
    set it consumes for deterministic reproducibility.

Stage 25 **must not mutate Stage 24 artifacts or contracts**.
Stage 25 must not re-open `PHX2/stage24/constants.py`,
`PHX2/stage24/models.py`,
`PHX2/stage24/decoder_contracts.py`,
`PHX2/stage24/runner.py`,
`PHX2/stage24/artifact_writer.py`, or any decoder module.
Stage 25 must not add a member to any closed-set Stage 24
tuple. Stage 25 must not change the locked Stage 24 artifact
filenames or schema versions.

## 3. What Stage 25 must not do

Stage 25's scope is ATH / migration measurement hardening. The
following are explicitly out of Stage 25:

  * **Calibration / enforcement — Stage 26.** Stage 26 owns
    threshold calibration against labeled reference observations
    and the promotion of observe-only filters / primitives to
    enforcement. Stage 25 does not block, gate, or pick
    thresholds for action. Stage 25 emits measurement evidence;
    Stage 26 decides what to do with it.
  * **X / social — Stage 27+.** Stage 27 and later own X API
    integration, social-graph scoring, and social-intel
    primitives. Stage 25 does not import any X API or social
    library. Stage 25 does not blend social-graph signals into
    its ATH / migration measurement records.
  * **Public / subscriber routing.** Stage 25 does not add any
    Discord / Telegram / subscriber / public-channel /
    paid-signal routing. The PHX2 routing surface remains
    reserved for a separately-justified later stage.
  * **Confirmed Axiom / global-fee decoder.** Stage 25 must not
    promote any Stage 24 router-fee primitive to
    `decoder_status = DECODED` and must not add a confirmed
    Axiom / router / global-fee decoder unless that promotion
    is **separately reopened with fixture proof** per the six
    proof criteria documented in
    `PHX2/stage24/STAGE_24_5_NO_DECODER_LOCK.md`. The
    sanitized real fixtures and the confirmed-decoder land are
    their own Stage 24.x sub-stage, not a Stage 25
    side-effect.

## 4. Stage 25 likely work

The Stage 25 brainstorm should consider, accept, or amend the
following observe-only primitive sketches:

  * **Migration timestamp hardening.** Today PHX2 derives a
    migration timestamp from upstream provider observations.
    Stage 25 should harden this: a single deterministic
    migration timestamp per token, reconciled across the
    providers Stage 25 admits, with explicit
    `MISSING` / `PARTIAL` / `UNSUPPORTED` semantics when the
    reconciliation fails. A migration record carries an
    `observed_at_utc` from each contributing source plus a
    deterministic
    `reconciliation_status` token.
  * **ATH source reconciliation.** ATH should be reconciled
    across independent sources (e.g. Birdeye / Dexscreener /
    on-chain swap-log replay / a WebSocket capture). Stage 25
    should record per-source ATH observations plus a
    reconciled record with explicit disagreement reasons in
    the closed-set vocabulary, never picking a winner silently.
  * **Time-to-ATH and post-migration peak measurement.**
    Stage 25 should record the time between a token's
    migration timestamp and its post-migration peak, with the
    peak qualified by which source carried it. A token whose
    sources disagree on the peak time emits multiple per-source
    records plus a deterministic reconciliation record with an
    explicit reason code.
  * **Birdeye / Dexscreener / WebSocket source comparison.**
    The Stage 25 brainstorm should pin a closed-set
    `MEASUREMENT_SOURCE` tuple (e.g. `BIRDEYE`,
    `DEXSCREENER`, `ON_CHAIN_SWAP_REPLAY`,
    `WEBSOCKET_CAPTURE`) and decide, per primitive, which
    sources are required vs. optional vs. forbidden. Stage 25
    must be honest about which sources it can and cannot
    reconcile against, mirroring Stage 24's
    candidate / decoded distinction.
  * **Deterministic measurement artifacts.** Stage 25 should
    ship a deterministic artifact writer in the same shape as
    Stage 23 / Stage 24: an immutable runner result, a
    canonical-JSON manifest with per-artifact SHA-256, locked
    artifact filenames, atomic writes, a redaction sweep over
    outbound bodies, and no top-level I/O. The Stage 25
    manifest should embed the Stage 24 manifest's SHA-256 (or
    the Stage 24 artifact filename hashes) so the Stage 25
    artifacts pin which Stage 24 run they were derived from.

## 5. Explicit note: Stage 24 does not solve ATH

Stage 24 does **not** solve ATH or migration measurement. Stage
24 ships execution-fee and execution-quality primitives that may
later **explain or diagnose** transaction quality around the
migration / ATH window — for example, a transaction that did not
land at the slot Stage 25 cares about may carry Stage 24
execution-quality evidence that explains the failure (a Jito
tip that was absent, a priority fee that was estimated and
under-priced, a router-fee candidate that fired the wrapped-swap
heuristic). That is **diagnosis**, not measurement.

ATH itself is a Stage 25 concern. Stage 24's job is to give
Stage 25 enough execution-context to ask honest questions about
why a given transaction did or didn't land near the
migration / ATH window. The Stage 24 surface is not an ATH
detector and was never intended to be one.

## 6. Stage 25 should remain observe-first

Like Stage 23 and Stage 24, Stage 25 should land **observe-first**:
every Stage 25 primitive should ship as a pure projection /
reconciler that emits structured records onto disk and never
blocks, gates, routes, dispatches, or alerts. A Stage 25 record
is measurement evidence, not a decision.

Promotion of any Stage 25 primitive to enforcement is a Stage 26
concern; it is out of scope for the Stage 25 land itself.

## 7. Stage 25 must preserve the filter / threshold version axis discipline

Stage 23 and Stage 24 each ship two version axes on every
emitted record:

  * `filter_version` / `decoder_version` — the
    implementation-version axis for a filter / decoder.
  * `threshold_version` — the threshold-configuration axis
    locked at Stage 23 / Stage 24 to
    `"thresholds_v0_observe_only"`.

Stage 25 should preserve this two-axis discipline for its own
ATH / migration measurement primitives. A Stage 25 primitive
that depends on a threshold value MUST carry a
`threshold_version` axis distinct from its implementation axis
so a future Stage 26 calibration pass can re-tune thresholds
without bumping the implementation axis.

## 8. Stage 25 should not rewrite Stage 21 / Stage 22 / Stage 23 / Stage 24 closed contracts

The following closed contracts are sealed and Stage 25 must
not rewrite them unless a separately-justified contract patch
lands first:

  * Stage 21 capture / decode contract surfaces.
  * Stage 22 ingestion / dedupe / raw-capture contract surfaces.
  * Stage 23 filter / input-reader / manifest / runner /
    artifact-writer contract surfaces.
  * Stage 24 execution-fee / execution-quality / runner /
    artifact-writer contract surfaces, including the eleven
    locked artifact filenames, the Stage 24.5 lock scalar
    markers, and the candidate-only router / global-fee
    semantics.

Stage 25 reads Stage 24 artifacts; it does not modify them.
Stage 25 must not add `PHX2.stage21` / `PHX2.stage22` /
`PHX2.stage23` / `PHX2.stage24` production imports to its own
modules unless a separately-justified cross-stage import policy
is established first.
