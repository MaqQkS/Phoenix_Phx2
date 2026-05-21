# PHX2 Stage 26 Handoff — calibration/enforcement candidates from Stage 25 measurement artifacts

## 1. Stage 26 purpose

Stage 26 is the first PHX2 stage that consumes Stage 25's
deterministic measurement artifacts to:

- calibrate measurement-aware enforcement candidates,
- evaluate thresholds and rules from the measured outcomes Stage
  25 emits,
- preserve the observe-only → enforcement transition discipline
  so a calibration error never silently silently promotes
  unmeasured evidence to a binding decision.

Stage 26 is a calibration / enforcement layer. Stage 26 is NOT a
new measurement layer; the measurement truth Stage 25 records is
the input contract, not a re-derivable side artifact.

## 2. Stage 26 may consume

The Stage 25.6 writer emits the following artifacts into a
caller-supplied output directory. Stage 26 reads them as
read-only inputs:

- `stage25_migration_measurements.jsonl`
- `stage25_price_window_observations.jsonl`
- `stage25_ath_candidates.jsonl`
- `stage25_source_reconciliations.jsonl`
- `stage25_ath_measurements.jsonl`
- `stage25_measurement_rejections.jsonl`
- `stage25_summary.json`
- `stage25_manifest.json`

Stage 26 SHOULD verify the manifest's per-file `sha256` and
`byte_count` against the on-disk bytes before consuming any
artifact row. The manifest's own self-entry uses the locked
`SELF_REFERENTIAL_MANIFEST_SHA256` sentinel and `-1` byte_count —
Stage 26 must detect the sentinel and skip the bytes-equal
verification for the manifest self-entry only.

The Stage 25.6 runner does NOT emit
`stage25_migration_observations.jsonl` as a Stage 26 input
contract because the migration measurements supersede the raw
observations for downstream calibration. Stage 26 readers MAY
inspect it for diagnostic purposes but MUST NOT treat the raw
observations as authoritative migration truth — the consolidated
`stage25_migration_measurements.jsonl` rows are the
authoritative truth.

## 3. Stage 26 must NOT

These are hard rules. Any Stage 26 surface that violates one of
these is broken; downstream Stage 26 boundary tests will fail
fast on each:

- mutate any Stage 25 artifact file (read-only ingestion).
- import `PHX2.stage25` production internals for runtime
  behaviour beyond the published artifact contracts; if a Stage
  26 surface needs a Stage 25 invariant value (e.g. a closed-set
  token), it MAY import the constant from `PHX2.stage25.constants`
  read-only.
- rewrite migration or ATH truth. The `measurement_status` /
  `reconciliation_status` / `confidence_level` tokens on each
  Stage 25 row are authoritative; Stage 26 reads them, never
  recomputes them.
- treat `PARTIAL`, `SOURCE_CONFLICT`, `AMBIGUOUS`, or `MISSING`
  rows as `MEASURED`. Each of those statuses is a deliberate
  Stage 25 honesty signal that downstream calibration MUST
  preserve.
- silently pick a source winner. If Stage 25 emitted
  `SOURCE_CONFLICT`, Stage 26 cannot collapse it to a single
  source. Source picking is a measurement-layer decision and
  Stage 25 has already declared it ambiguous.
- implement Stage 27 X / social ranking, social-token joins,
  social boost / context labels, or tweet / external-source
  intelligence.
- implement public / subscriber / paid routing, Discord /
  Telegram dispatch, or any transport. Stage 26 is observe-only
  calibration first.
- reopen the confirmed Axiom / global-fee / execution-fee
  decoder. Stage 24 closed that work; Stage 25 took only the
  manifest basename + sha256 pin as context. Stage 26 must do
  the same.
- bypass manifest / redaction / determinism rules. A Stage 26
  artifact MUST satisfy the same redaction / observe-only /
  manifest discipline Stage 25 imposes on its own outputs.

## 4. Stage 26 calibration principles

These principles translate Stage 25's status vocabulary into the
calibration / enforcement layer Stage 26 will build:

- `MEASURED` means: the measurement is `AGREED` across at least
  two distinct contributing source families, the observation
  occurred in a post-migration window, and the source-attributed
  truth is bound into the canonical `measurement_hash`. Stage 26
  is free to use `MEASURED` rows as binding calibration input.
- `PARTIAL` means: the evidence is real and usable for
  qualitative calibration but does NOT meet the cross-source
  honesty bar. Stage 26 must NOT silently elevate `PARTIAL` to
  binding truth; calibrators MAY use it as a soft signal with
  explicit `PARTIAL`-aware logic.
- `SOURCE_CONFLICT` and `AMBIGUOUS` must remain separate in
  Stage 26's downstream books. `SOURCE_CONFLICT` records two-
  or-more sources whose reconciled disagreement exceeds the
  Stage 25 MAJOR tolerance; `AMBIGUOUS` records evidence that
  the measurement layer refused to honestly resolve. Stage 26
  calibrators must surface both classes separately to the
  operator and never collapse them.
- `MISSING` / `UNSUPPORTED` must NOT be backfilled with fake
  values. A `MISSING` migration measurement has no consolidated
  block time; Stage 26 cannot synthesise one. A `MISSING` ATH
  measurement has `consolidated_peak_price = None`; Stage 26
  cannot substitute `0`, the previous run's value, or any other
  default.
- Single-source evidence defaults to `PARTIAL`. A future
  versioned Stage 26 calibration policy MAY admit single-source
  evidence into a narrowly scoped calibration view, but ONLY
  with an explicit `SINGLE_SOURCE_AWARE` policy version token
  bound into the calibration record's hash so the elevation is
  auditable.
- Calibration must preserve denominator honesty. A Stage 26
  threshold / ratchet that divides by the number of "measured"
  tokens MUST exclude tokens whose Stage 25 status is
  `PARTIAL` / `SOURCE_CONFLICT` / `AMBIGUOUS` / `MISSING` /
  `UNSUPPORTED` unless the calibration policy explicitly admits
  the lower-honesty status (with the same versioned policy
  token discipline as above).

## 5. Stage 27+ deferrals

The following surfaces are intentionally deferred to Stage 27 or
later. They MUST NOT appear in Stage 26 production code:

- X / social ranking, scoring, or weighting.
- Tweet / source intelligence ingestion.
- Social-token joins (e.g. joining a Stage 25 measurement record
  against an external social profile).
- Social boost / context labels (e.g. "high-engagement",
  "trending") attached to a measurement.
- Public / subscriber routing, paid signal tiers, or any
  monetization-aware dispatch logic.
- Discord / Telegram distribution tiers.

## 6. Stage 24 / Axiom deferral

The confirmed Axiom / global-fee / execution-fee decoder remains
deferred. It is NOT reopened by Stage 25 and MUST NOT be
reopened by Stage 26 unless:

1. Sanitized real fixtures (no live secret values, no live
   webhook hosts, no live API keys) are committed under a
   Stage 26 sub-stage's test fixture directory.
2. A separate proof-of-correctness audit document accompanies
   the reopening.
3. The reopening is explicitly authorized by the operator (no
   stage automation should auto-reopen it).

Stage 25 consumed Stage 24 only as an OPTIONAL manifest pin
(`Stage25Stage24ManifestPin` with `basename` + `sha256` only).
That pin is provenance, not execution-fee logic. Stage 26 must
maintain the same boundary: a Stage 26 calibration record MAY
record a Stage 25 manifest sha256 as upstream provenance, but
MUST NOT import or re-derive Stage 24 execution-fee state.

## 7. Recommended Stage 26 first substage

**Stage 26.1 — calibration input contracts + artifact readers.**

Stage 26.1 ships:

- Typed input contracts for every Stage 25 artifact basename
  listed in Section 2.
- Pure, side-effect-free readers that project each JSONL row
  into an immutable Stage 26 input record.
- Manifest verification (per-file `sha256` / `byte_count`
  recompute against on-disk bytes, with the
  `SELF_REFERENTIAL_MANIFEST_SHA256` exception for the
  manifest self-entry).
- A read-only Stage 25 status-token consumer (so Stage 26.1
  cannot accidentally rewrite measurement status).
- A `Stage26InputManifest` recording the Stage 25 manifest pin
  by basename + sha256 only (mirroring the Stage 24 → 25 pin
  pattern).

Stage 26.1 does NOT yet ship:

- enforcement of any threshold,
- calibration of any rule,
- any X / social / tweet ingestion,
- any routing / dispatch / Discord / Telegram surface,
- any DB / RPC / network code,
- any CLI surface,
- any modification of Stage 25 artifacts.

Stage 26.2+ adds the actual calibration / threshold-fitting
logic on top of the Stage 26.1 read-only contract layer. The
order matches the Stage 24 / Stage 25 pattern: contracts first,
domain logic second, runner / writer next, closure audit /
handoff last.
