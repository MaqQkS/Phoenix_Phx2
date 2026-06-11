# Stage 30.11.23 — discovered migration-evidence → real-fed candidate + evidence bridge (SPEC LOCK)

Status: committed offline / fake / no-send bridge.
Minor version: `30.11.23`.
Report schema version: `stage30_11_23_v0_migration_evidence_candidate_bridge`.

## Blocker closed

Stage 30.11.22 proved the fundamentals chain (harvest → bridge →
30.11.21/20/19/18/17 → recorded would-send) with **real provider reads + a fake
dispatch**, but it still required the operator to hand-feed a candidate mint
(`CURATED_MINT`) and a migration anchor (`CURATED_MIGRATION_TIME_UTC`) and to keep
the candidate mint in sync with a hand-built migration-evidence record. Nothing
committed converted a **discovered** migration event into the two inputs the 30.11.22
chain consumes. Stage 30.11.23 closes exactly that gap: it derives **both** the
discovered candidate **and** its mint-keyed migration evidence from **one** committed
Stage 29.5.7 sanitized migration-evidence summary, so neither is hand-typed and they
cannot desync. It replaces **only** the manual mint/anchor inputs; the fundamentals
chain is untouched.

## Load-bearing invariant

The committed Stage 30.11.8 confirmation keys the evidence lookup off the candidate's
`token_mint`. Stage 30.11.23 feeds the summary's `token_mint` to **both** the candidate
`token_mint` **and** the evidence record `token_mint` — the same string both sides — so
the confirmation always finds the matching record. This is the property the manual
`CURATED_MINT` flow maintained by hand.

## Input (consumed duck-typed; Stage 29 type never imported)

`Stage29_5_7SanitizedMigrationEvidenceSummary` shape, read via the six documented
fields: `token_mint`, `measurement_status`, `migration_event_time_utc`, `warnings`,
`redaction_status`, `source_ref`. The committed bridge imports **no** Stage 29 type
(leaf boundary forbids Stage 21-29 imports); the real producer (an out-of-repo
Helius WebSocket/RPC capture driving the committed Stage 29.5.7 producer) emits the
summaries at the ceremony.

## Output (one bundle, both sides, derived from one summary list)

`Stage30_11_23RealFedInputs`:
- `events` — discovered-candidate carriers (the committed Stage 30.11.6 / 30.11.22
  `events` slot).
- `assembler` — trivial committed assembler (the migration-discovered candidate's
  "assembly" is identity).
- `record_flattener` — committed placeholder flattener (fills the Stage 30.11.5
  flat-projection shape; every field except `token_mint` + `candidate_id` is an inert
  placeholder the committed Stage 30.11.22 bridge discards).
- `evidence_source` — mint-keyed committed Stage 30.11.9
  `Stage30_11_9MigrationEvidenceSourceAdapter`.
- `report` — embedded `Stage30_11_23BridgeReport`.

The operator unpacks the bundle into `run_stage30_11_22_real_fed_dry_run`.

## Mapping (exact; fabricates nothing)

| summary | destination |
|---|---|
| `token_mint` | candidate `token_mint` **and** evidence `token_mint` (same string) |
| `migration_event_time_utc` | evidence `migration_event_time_utc` (verbatim) |
| `measurement_status` (`COMPLETE`) | evidence `measurement_status` (verbatim) |
| `redaction_status` (`SAFE`) | evidence `redaction_status` (verbatim) |
| `warnings` (`()`) | evidence `warnings` (verbatim, shape-validated) |
| `source_ref` | evidence `source_ref` only — never echoed in a bridge event; candidate `source_ref` is `None` |

The evidence record is built by **reusing** the committed Stage 30.11.9
`build_evidence_record_from_sanitized_projection(...)` (rename-only, verbatim carry,
warnings-shape fail-closed). The mint-keyed source is built via the committed
`build_migration_evidence_source(provider)`.

## Closed-set bridge decisions

`BRIDGED_CANDIDATE_AND_EVIDENCE` (pass) plus: `SKIPPED_NOT_A_SUMMARY`,
`SKIPPED_MISSING_TOKEN_MINT`, `SKIPPED_INVALID_TOKEN_MINT`,
`SKIPPED_MISSING_MIGRATION_TIME`, `SKIPPED_NOT_COMPLETE_MEASUREMENT`,
`SKIPPED_UNSAFE_REDACTION`, `SKIPPED_MALFORMED_WARNINGS`,
`SKIPPED_EVIDENCE_UNBUILDABLE`, `SKIPPED_DUPLICATE_MINT`.

The `COMPLETE` / `SAFE` screens are **Layer-0 routing hygiene only**: they stop an
obviously-doomed summary from consuming a candidate slot and give a precise
bridge-level skip reason. They **mirror but do not replace** the committed Stage
30.11.8 / Stage 30.11.21 confirmation — every bridged record carries those fields
verbatim and the confirmation independently re-checks `COMPLETE` / `SAFE` / staleness
/ the trailing-Z anchor. Migration confirmation stays downstream.

Duplicate mints: **first-wins**. A later summary with an already-bridged mint becomes
`SKIPPED_DUPLICATE_MINT` (logged), guaranteeing exactly one evidence record per mint
(the Stage 30.11.9 source requires a single bound record).

## Placeholder wart (accepted)

Routing the discovered candidate through the committed Stage 30.11.6 harvest seam (to
reuse Stage 30.11.22 verbatim) forces the flattener to emit shape-satisfying
placeholders (`PENDING` for status fields, `0` for the finite-`Decimal` fields). The
committed Stage 30.11.22 bridge reads only `token_mint` + `candidate_id` and stamps its
own `PENDING_ENRICHMENT` / `PENDING` sentinels, so **no placeholder ever reaches the
composer**. These are shape-satisfiers required by the committed projection contract,
not data. Stage 30.11.22 is not refactored.

## Redaction

No raw payloads / transaction JSON / endpoint URLs / API keys / WebSocket URLs / raw
exception text. Bridge events carry only the zero-based index, the closed-set decision
token, the safe-echo `token_mint`, and the injected timestamp — **no** `source_ref`,
**no** anchor, **no** measurement/redaction value. `source_ref` lives only on the
evidence record (never scanned) and is dropped downstream by Stage 30.11.21's
`_safe_migration_source` because its shape is not echo-safe. The committed production
source carries no bare provider needle (filenames + docstrings reference the producer
by stage number, not vendor).

## Boundary

Offline / pure / injected. No real Helius WS/RPC client; no network; no env reads; no
Discord/webhook; no Stage 30.11.16 guard; no wallet/signing/trading; no public/
subscriber routing; no dashboard; no alpha filters; no PHX1 import; no Stage 21-29
import in committed production. Committed PHX2 imports: the Stage 30.11.23 models
sibling + the committed Stage 30.11.9 evidence-source adapter (bridge); the committed
Stage 30.11.22 fake proof driver (fake proof). Stdlib: `__future__` / `typing` /
`dataclasses`.

## Production files

- `PHX2/stage30/stage30_11_23_migration_evidence_candidate_bridge_models.py`
- `PHX2/stage30/stage30_11_23_migration_evidence_candidate_bridge_adapter.py`
- `PHX2/stage30/stage30_11_23_fake_migration_evidence_candidate_bridge_proof.py`

## Tests

- `PHX2/tests/stage30/test_stage_30_11_23_migration_evidence_candidate_bridge_adapter.py`
- `PHX2/tests/stage30/test_stage_30_11_23_fake_migration_evidence_candidate_bridge_proof.py`
  (doubles as the composition proof: bridge → committed Stage 30.11.22 chain → recorded
  would-send, no manual mint)
- `PHX2/tests/stage30/test_stage_30_11_23_boundaries.py`
- `PHX2/tests/stage30/test_stage_30_11_23_manifest.py`

## Out-of-repo / next steps (operator-authorized, not built here)

- The real Stage 29.5.7 migration-evidence producer (Helius WebSocket/RPC capture).
- Real Birdeye price / market-context / ATH transport construction; env loading;
  Discord transport.
- The first non-manual no-send ceremony: producer → `sanitized_summaries` →
  `build_real_fed_inputs_from_migration_evidence` → `run_stage30_11_22_real_fed_dry_run`
  with real provider sources + the recording fake client + in-memory ledger.
- The later capped private send (durable `JsonlPingDedupeLedger`, the Stage 30.11.16
  guard, max one Discord send, explicit per-run authorization) — a separate step; the
  composer's tier/dip eligibility still governs.
