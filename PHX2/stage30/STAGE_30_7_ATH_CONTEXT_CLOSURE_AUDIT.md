# PHX2 Stage 30.7.4 — ATH Context Bridge Closure Audit

Stage 30.7.4 is a closure audit and handoff slice, NOT a feature
implementation. It ships exactly two markdown documents (this closure
audit and the companion `STAGE_30_7_ATH_CONTEXT_HANDOFF.md`) plus one
constants-only manifest module (`stage30_7_4_manifest.py`) plus four
test modules, and it widens exactly two inventory-pin allowlists
(`test_stage_30_0_spec_lock.py` and
`test_stage_30_7_0_ath_context_spec_lock.py`) to admit those files.
Stage 30.7.4 adds ZERO runtime production code, edits NO renderer / no
compact models / no orchestrator, performs NO commit / tag / push, and
does NOT begin Stage 30.8.

This document is the closure record for the Stage 30.7 ATH context
bridge family (substages 30.7.0 through 30.7.3). It carries no provider
credential, no private transport destination, no provider host address,
no transport scheme prefix, no raw provider payload, and no request auth
metadata.

## 1. Stage 30.7 purpose

Stage 30.7 is the ATH context family of Stage 30. Its single deliverable
was moving the compact private-ping body `ATH` token from the literal
`Unknown` toward an honest, evidence-backed ATH display value, WITHOUT
fabricating a peak and WITHOUT touching the `MC` / `LP` / `Mig` behavior
that earlier Stage 30 slices established.

The Stage 30.7 stance, pinned:

- ATH is a measurement / evidence problem, never an estimate. An honest
  ATH market cap requires the circulating supply at the historical peak,
  which no current source ships directly.
- Stage 30.7 owns only the compact `ATH` display contract; the upstream
  sources own the ATH-measurement semantics.
- Every offline / fake slice lands and is proven before any live or
  Discord slice is even authorized.

Stage 30.7 preserved the exact compact line shape; it replaced only the
`ATH` token:

```
• MC: <mc> | ATH: <ath> | Mig: <mig>
```

## 2. Commit chain

The Stage 30.7 family landed as four commits on `master`:

- 30.7.0 — lock ATH context bridge spec —
  `e5aa703cce3f3043d2ae9b35b2b8bc02be6fb09f`
- 30.7.1 — add ATH context projection model —
  `837a0588959f62c0e6cf059091557d43bf513b2e`
- 30.7.2 — fake-wire ATH context into compact ping —
  `ba71b6ea3efdb282d167a5760d2d31428612c04c`
- 30.7.3 — bridge sanitized ATH evidence —
  `3d4c5bed1967c431a6001173e907dda0c528fc33`

Stage 30.7.4 (this slice) builds on top of the 30.7.3 commit. The
required parent / current HEAD for Stage 30.7.4 is
`3d4c5bed1967c431a6001173e907dda0c528fc33`. Stage 30.7.4 itself makes no
commit; the SHA above is the last commit in the chain at closure time.

## 3. Final proof line

The Stage 30.7 family produced, fully offline (no Discord send, no live
provider call), the following compact body state line:

```
• MC: $83k | ATH: $120k | Mig: Known
```

This exact line is asserted by both the Stage 30.7.2 runtime-integration
test and the Stage 30.7.3 runtime-integration test, each of which drives
the offline Stage 30.4.2 compact runtime replacement path with a fake /
sanitized resolver and renders the compact body. The `$120k` ATH token
is produced ONLY for a trusted observed-market-cap USD projection; every
other evidence shape renders `ATH: Unknown`.

## 4. Final data path

The complete Stage 30.7 ATH data path, end to end:

```
sanitized ATH evidence
  -> Stage30_7AthContextEvidence
  -> project_ath_context(...)
  -> compact ATH text
  -> ath_mc_text
  -> compact ping body
```

Expanded, with the owning module of each hop:

- A future caller supplies **sanitized ATH evidence** — a plain `dict`,
  any attribute-bearing object, or the Stage-30-owned
  `Stage30_7_3SanitizedUpstreamAthEvidence` dataclass. NEVER a raw
  provider payload.
- The Stage 30.7.3 bridge
  (`sanitized_ath_evidence_to_stage30_evidence`) reads the sanitized
  fields by alias, maps each upstream token onto a Stage 30 closed-set
  token with fail-closed defaults, and builds a
  **`Stage30_7AthContextEvidence`** (Stage 30.7.1 lenient carrier).
- The Stage 30.7.1 pure projection brain
  (**`project_ath_context(...)`**) classifies the evidence and emits a
  `Stage30_7AthContextProjection` carrying a single safe **compact ATH
  text** (`ath_display_text`: a `$Y` value or the literal `Unknown`).
- The Stage 30.7.2 adapter (`ath_projection_to_compact_text` /
  `Stage30_7_2AthDisplayResolver`) hands that string to the orchestrator,
  which fills the existing Stage 30.2 **`ath_mc_text`** display slot.
- The Stage 30.2 renderer renders whatever short safe string occupies
  that slot into the **compact ping body** `ATH` token, falling back to
  `Unknown` when the slot is `None`.

There is no duplicate projection logic anywhere on this path: the honest
ATH decision order lives entirely in `project_ath_context`.

## 5. File inventory by substage

### Stage 30.7.0 — `e5aa703`
- Production / docs: `STAGE_30_7_0_ATH_CONTEXT_SPEC_LOCK.md`,
  `stage30_7_manifest.py` (constants-only manifest).
- Tests: `test_stage_30_7_0_ath_context_spec_lock.py`; narrow
  inventory-allowlist widening on `test_stage_30_0_spec_lock.py`.
- No ATH bridge code, no renderer / runtime change.

### Stage 30.7.1 — `837a058`
- Production: `stage30_7_ath_context_models.py` (closed-set vocabularies
  + lenient evidence carrier + validated projection record),
  `stage30_7_ath_context_projection.py` (pure `project_ath_context`).
  Additive constants edit to `stage30_7_manifest.py`.
- Tests: `test_stage_30_7_1_ath_context_models.py`,
  `test_stage_30_7_1_ath_context_projection.py`,
  `test_stage_30_7_1_boundaries.py`, `test_stage_30_7_1_manifest.py`.
- No renderer / models / orchestrator edit.

### Stage 30.7.2 — `ba71b6e`
- Production: `stage30_7_compact_ath_runtime_adapter.py` (projection-to-
  text converter + `Stage30_7_2AthDisplayResolver`). Additive constants
  edit to `stage30_7_manifest.py`.
- Runtime seam: the Stage 30.4.2
  `stage30_4_compact_runtime_session_orchestrator.py` gained ONE optional
  duck-typed `ath_context_resolver` parameter and a
  `_resolve_ath_display_text` helper that fills the existing `ath_mc_text`
  slot ONLY when a resolver is supplied. The default (no-resolver) path is
  byte-identical to the pre-30.7.2 behavior and keeps `ATH: Unknown`.
- Tests: `test_stage_30_7_2_compact_ath_runtime_adapter.py`,
  `test_stage_30_7_2_runtime_integration.py`,
  `test_stage_30_7_2_boundaries.py`, `test_stage_30_7_2_manifest.py`.
- This is the ONLY substage that edited the orchestrator. No renderer /
  compact models edit.

### Stage 30.7.3 — `3d4c5be`
- Production: `stage30_7_sanitized_ath_bridge.py` (sanitized upstream
  shape -> Stage 30.7.1 evidence normalizer + resolver builder). Additive
  constants edit to `stage30_7_manifest.py`.
- Tests: `test_stage_30_7_3_sanitized_ath_bridge.py`,
  `test_stage_30_7_3_runtime_integration.py`,
  `test_stage_30_7_3_boundaries.py`, `test_stage_30_7_3_manifest.py`.
- No orchestrator edit (the 30.7.2 `ath_context_resolver` seam is reused
  as-is). No renderer / compact models edit. Imports no Stage 25 / 27 /
  28 / 29 module.

### Stage 30.7.4 — closure (this slice, uncommitted)
- Docs / manifest: `STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md` (this file),
  `STAGE_30_7_ATH_CONTEXT_HANDOFF.md`, `stage30_7_4_manifest.py`
  (constants-only).
- Tests: `test_stage_30_7_4_closure_audit.py`,
  `test_stage_30_7_4_handoff.py`, `test_stage_30_7_4_boundaries.py`,
  `test_stage_30_7_4_manifest.py`.
- Inventory-allowlist widening only: `test_stage_30_0_spec_lock.py`,
  `test_stage_30_7_0_ath_context_spec_lock.py`.
- No runtime production code, no renderer / compact models / orchestrator
  edit.

## 6. Safety invariants

The entire Stage 30.7 family holds the following invariants. They were
proven by the per-substage boundary tests (positive import allowlists +
forbidden-needle scans + AST checks) and are re-stated here for the
record:

- offline only
- no live/provider/Discord
- no env reads
- no DB/filesystem writer
- no zstd
- no enforcement/public routing/trading/wallet/social
- no drawdown/tier recomputation
- no Stage 25/27/28/29 production imports
- no Stage 29.5 production imports
- compact renderer/model untouched

The Stage 30.7.1 / 30.7.2 / 30.7.3 production modules import only
`__future__` / `typing` / `dataclasses` / `decimal` / `math` / `re` from
the standard library and, for PHX2, only their Stage 30.7 siblings. No
module on the path imports `os`, a network module, a database module, a
compression module, a provider client, a Discord surface, or any Stage
21–29 / Stage 29.5 / PHX1 module.

## 7. Redaction fail-closed invariants

ATH evidence is trusted for display ONLY when redaction safety is
explicitly asserted. The fail-closed rules, proven across the family:

- The official Stage 30.7.1 `Stage30_7AthContextEvidence` carrier
  defaults `redaction_safe=False`. An evidence built without explicitly
  asserting `redaction_safe=True` can NEVER project to `ATH_KNOWN`.
- Duck-typed evidence that is missing the `redaction_safe` attribute
  resolves to `None` in the projection and fails closed (a missing
  redaction proof is never trusted).
- The Stage 30.7.3 bridge sets `redaction_safe` to `True` ONLY for an
  upstream value that is exactly `True`; a missing or non-`True` upstream
  redaction flag fails closed to `False`.

## 8. Unit / basis honesty

The displayed ATH must be honest about its unit and its measurement
basis. The pinned outcomes:

- A USD observed market-cap ATH can display (the only basis that yields
  `ATH_KNOWN` and a `$Y` value).
- A price-derived ATH remains `Unknown` (a current-supply price-derived
  ATH market cap is honesty-limited; at most `ATH_UNVERIFIED`, never
  `ATH_KNOWN`).
- A USDC unit maps to `Unknown` unless explicitly authorized later (Stage
  30.7 never authorized a USDC ATH display; it is never silently treated
  as USD).
- A SOL value against a USD market context remains `Unknown` (USD is
  never treated as SOL or SOL as USD).
- An unsupported / missing / conflicting / stale / error source remains
  `Unknown` (a non-`PRESENT` source status dominates any claimed value).

## 9. What Stage 30.7 explicitly did NOT solve

Stage 30.7 closed the offline compact ATH display contract only. It did
NOT solve, and explicitly deferred:

- live ATH sourcing
- storage/session persistence
- zstd/day rolling
- drawdown from ATH
- tier dip
- enforcement
- public routing
- wallet/trading

## 10. Next recommended stage

Stage 30.8: compact session artifact / storage readiness for 24/7
collection.

The compact `MC` / `ATH` / `Mig` display contract is now offline-complete
and proven. The natural next problem is durable session artifact capture
and storage readiness for continuous 24/7 collection, which Stage 30.6
already spec-locked as a budget policy. Live ATH sourcing (a controlled,
separately operator-authorized Stage 30.7.5 probe) and any drawdown /
tier work remain gated behind that storage readiness and a separate
audit.

---

_Stage 30.7.4 is a closure audit and handoff slice. There is no runtime
code change, no renderer / compact models / orchestrator change, no
live / provider / Discord, no commit, no tag, and no push performed by
Stage 30.7.4 implementation._
