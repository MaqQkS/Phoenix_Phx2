# Stage 29.5.4 Migration Context Injection Runbook

## 1. Canonical Stage 29.5.4 mission sentence

Stage 29.5.4 is the direct opt-in migration context injection substage that lets an operator thread the Stage 29.5.2 offline composition into the Stage 29.3 private tradeable ping path via a single optional `migration_source` kwarg on `run_stage29_3_first_private_tradeable_smoke`, while preserving `Stage29_3NoMigrationEvidenceSource` as the hard default and modifying no Stage 29.4, Stage 29.5, Stage 29.5.2, or Stage 29.5.3 production source.

## 2. Scope

Stage 29.5.4 ships:

- a Stage 27.4 `MigrationContextSource` Protocol adapter (`Stage29_5_4MigrationContextSourceAdapter`) that wraps the Stage 29.5.2 offline integration entrypoint and projects each `read_migration_snapshot(token_mint)` call onto a Stage 27.4 `MigrationSourceSnapshot` via a closed-set, deliberately-conservative behavior matrix;
- two operator-supplied Protocol surfaces (`Stage29_5_4MigrationEvidenceProvider`, `Stage29_5_4AthContextProvider`) that let the operator wire any in-memory evidence sequence + ATH context lookup;
- a constants-only Stage 29.5.4 manifest;
- this runbook and a dedicated test surface;
- one tiny edit to `stage29_3_tradeable_smoke.py`: a new `migration_source: Optional[MigrationContextSource] = None` kwarg threaded one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`, with a conditional fallback that preserves `Stage29_3NoMigrationEvidenceSource()` byte-equivalently when the caller does not pass the kwarg.

Stage 29.5.4 ships ZERO live Chainstack gRPC call, ZERO live Birdeye HTTP call, ZERO live Helius WebSocket call, ZERO live Discord send, ZERO Telegram / X / social sender, ZERO automated trading / wallet / private-key / signer surface, ZERO public / subscriber / paid-tier routing, ZERO Stage 26 enforcement activation, ZERO new env names, ZERO new third-party runtime dependency, ZERO Pump.fun bonding-curve decoder, ZERO Dexscreener / Helius as a price source, ZERO PHX1 import path, ZERO formatted Discord rendering of migration context, ZERO Stage 29.4 runtime wiring change, ZERO Stage 29.5 manifest inventory change, ZERO Stage 29.5.2 manifest inventory change, ZERO Stage 29.5.3 manifest inventory change.

## 3. Why a separate Stage 29.5.4 substage

Stage 29.5.3 shipped the deferred-observation soak pass-entrypoint wrapper that bridges the offline composition into the Stage 29.4 short-session private soak path via a post-soak `flush_pending_observations()` step. The Stage 29.5.3 design deliberately deferred all provider / composition / artifact work to the post-soak flush, so the Stage 29.5 migration context never reaches the Stage 27.6 candidate assembler inside a Stage 29.3 mode-3 ceremony. The Stage 29.5.3 forbidden-surface tuple kept "direct Stage 29.3 migration-context injection" pinned forbidden.

Stage 29.5.4 unlocks exactly that one surface. The Stage 27.6 `read_migration_context` call at the assembler's `_build_measurement_context` is the load-bearing seam: the candidate's measurement context (and downstream Stage 27.5 / Stage 28.9 dispatch) consumes the `MigrationSourceSnapshot` BEFORE the candidate is dispatched. Threading the Stage 29.5 projection in via the Stage 29.5.3 wrapper would be too late. Stage 29.5.4 instead adds one optional kwarg to the Stage 29.3 mode-3 public entrypoint; default Stage 29.3 behavior remains byte-equivalent to today.

## 4. Data flow

```
operator builds an evidence_provider callable
    (Stage29_5_4MigrationEvidenceProvider Protocol)
        token_mint -> Sequence[Stage29_5MigrationEvidenceRecord]

operator builds an ath_context_provider callable
    (Stage29_5_4AthContextProvider Protocol)
        token_mint -> Optional[AthContextRecord]

operator builds the adapter:
    adapter = Stage29_5_4MigrationContextSourceAdapter(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_context_provider,
        clock=stage29_5_4_clock_callable,
        time_window_start_utc=None,                # caller-supplied
        time_window_end_utc=None,                  # caller-supplied
        expected_pool_program_id=None,             # caller-supplied
    )

operator passes the adapter as migration_source to
    run_stage29_3_first_private_tradeable_smoke.

# ---- Stage 29.3 mode-3 path (per ceremony) ----

per Stage 27.6 candidate assembly (one call per assembled
candidate):

    snapshot = adapter.read_migration_snapshot(token_mint)
    # adapter internals:
    #   - safe-shape token_mint validation (UNKNOWN snapshot on
    #     unsafe shape, never raises)
    #   - candidate_axes = Stage29_5CandidateAxes(base_mint=token_mint)
    #   - evidence = evidence_provider(token_mint)
    #   - ath_context = ath_context_provider(token_mint)
    #   - result = run_stage29_5_2_offline_integration(...)
    #   - projection -> MigrationSourceSnapshot via behavior
    #     matrix (closed-set; see section 5)

    # Stage 27.4 read_migration_context consumes the snapshot
    # exactly as it would consume Stage29_3NoMigrationEvidenceSource's
    # output: closed-set MIGRATION_STATUS / MIGRATION_REASON /
    # MIGRATION_SOURCE verdict on a MigrationContextRecord.

    # Stage 28.9 dispatch semantics UNCHANGED. Stage 29.3 bounded
    # budget UNCHANGED (max_events=1 / max_dispatches=1 /
    # max_total_retries=0 / max_ticks=1). private operator
    # dispatch path UNCHANGED.

# ---- end of Stage 29.3 mode-3 ----

# default behavior (operator omits migration_source kwarg):
#   - run_stage29_3_first_private_tradeable_smoke(..., migration_source=None)
#   - _run_mode_one_real_private_tradeable_ping_dry_run
#     constructs Stage29_3NoMigrationEvidenceSource() and assigns
#     it to Stage27_6Sources.migration_source -- BYTE-EQUIVALENT
#     to the pre-Stage-29.5.4 code path.
```

## 5. Behavior matrix (closed-set)

The adapter projects the Stage 29.5.2 offline integration result onto a Stage 27.4 `MigrationSourceSnapshot` using the following deliberately-conservative mapping. The mapping NEVER surfaces a half-valid migration timestamp as authoritative.

| Stage 29.5 projection.measurement_status | Stage 29.5 projection.migration_source | Stage 29.5 projection.migration_timestamp_utc | Stage 27.4 MigrationSourceSnapshot |
|---|---|---|---|
| COMPLETE | HELIUS_WS | non-None | populated: `migration_event_id`=first matched evidence's `migration_signature`; `migration_timestamp_utc`=projection's value; `migration_source`=`ON_CHAIN_MIGRATION_EVENT`; `source_event_ref`=first matched evidence's `source_event_ref`; `raw_capture_ref`=None |
| COMPLETE | STAGE29_MIGRATION_ARTIFACT | non-None | populated (same shape as HELIUS_WS row) |
| COMPLETE | SYNTHETIC_TEST_ONLY | any | `MIGRATION_SOURCE_UNKNOWN` snapshot (no spurious authority promotion for synthetic fixtures) |
| COMPLETE | UNKNOWN | any | `MIGRATION_SOURCE_UNKNOWN` snapshot |
| COMPLETE | any | None | `MIGRATION_SOURCE_UNKNOWN` snapshot (defensive: COMPLETE should always carry timestamp, but the adapter is the last gate before Stage 27.4 sees the snapshot) |
| PARTIAL_MIGRATION_PRESENT | any | any | `MIGRATION_SOURCE_UNKNOWN` snapshot (half-valid migration context NEVER promoted) |
| MISSING_MIGRATION | any | any | `MIGRATION_SOURCE_UNKNOWN` snapshot |
| INVALID_MIGRATION | any | any | `MIGRATION_SOURCE_UNKNOWN` snapshot |
| CONFLICTING_MIGRATION | any | any | `MIGRATION_SOURCE_UNKNOWN` snapshot |

For any internal exception (provider callable raising, offline integration caller-shape failure, projection validator failure, clock returning a malformed string, unsafe `token_mint`), the adapter returns `MIGRATION_SOURCE_UNKNOWN` snapshot. `read_migration_snapshot` is non-raising by contract: the adapter must never block Stage 27.6 / Stage 28.9 dispatch.

## 6. Acceptance criteria

**A.** `Stage29_5_4MigrationContextSourceAdapter.read_migration_snapshot(token_mint)` returns a Stage 27.4 `MigrationSourceSnapshot` for every input — never raises.

**B.** COMPLETE + trusted (HELIUS_WS / STAGE29_MIGRATION_ARTIFACT) + non-None timestamp produces a populated snapshot with `migration_source = ON_CHAIN_MIGRATION_EVENT`.

**C.** SYNTHETIC_TEST_ONLY NEVER produces a populated snapshot regardless of measurement status.

**D.** PARTIAL_MIGRATION_PRESENT / MISSING_MIGRATION / INVALID_MIGRATION / CONFLICTING_MIGRATION all degrade to `MIGRATION_SOURCE_UNKNOWN` snapshot.

**E.** The default Stage 29.3 mode-3 call (no `migration_source` kwarg) constructs `Stage29_3NoMigrationEvidenceSource()` and assigns it to `Stage27_6Sources.migration_source` byte-equivalently to the pre-Stage-29.5.4 code path.

**F.** When the operator passes a `migration_source` instance to `run_stage29_3_first_private_tradeable_smoke`, the supplied instance is assigned to `Stage27_6Sources.migration_source` and `Stage29_3NoMigrationEvidenceSource` is NOT constructed.

**G.** Stage 29.3 mode-3 still references the `Stage29_3NoMigrationEvidenceSource` class as the conditional fallback; the existing Stage 29.5.2 / Stage 29.5.3 cross-stage pins that assert the class is referenced in the source remain green.

**H.** Stage 29.3 production source carries NO `stage29_5*` / `stage29_5_2*` / `stage29_5_3*` / `stage29_5_4*` import; the parameter's static type is the existing Stage 27.4 `MigrationContextSource` Protocol that Stage 29.3 already had access to via its existing Stage 27.4 imports.

**I.** Stage 29.4 production source is untouched at Stage 29.5.4; Stage 29.4 soak orchestrator continues to import zero `stage29_5*` modules.

**J.** Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 production source is untouched at Stage 29.5.4.

**K.** The adapter's `filter_enforcement_status` flows through the Stage 29.5.2 offline integration unchanged: the locked `NOT_ACTIVE_STAGE_29_PENDING` token is preserved on every Stage 29.5.4 code path.

**L.** The adapter reads zero env names. The Stage 29.5.4 adapter, the Stage 29.5.4 manifest, and the Stage 29.5.4 runbook reference no env literal.

**M.** The adapter imports zero outbound-network libraries (no `urllib`, no `requests`, no `httpx`, no `aiohttp`, no `websockets`, no `websocket`, no `http.client`, no `socket`, no `grpc`, no `asyncio`).

**N.** No duplicate dispatch occurs: with `max_dispatches=1`, the Stage 29.3 mode-3 ceremony makes at most one Discord call regardless of whether the operator wires the Stage 29.5.4 adapter. The Stage 28.9 dispatch ledger semantics are unchanged.

**O.** Counter invariants: `events_seen <= 1`, `candidates_dispatched <= 1`, `dispatch_success <= 1` in every controlled test exercising the Stage 29.3 mode-3 chain with the Stage 29.5.4 adapter wired.

**P.** No public / subscriber / paid-tier routing. No Stage 26 enforcement activation. No Telegram / X / social sender. No automated trading / position sizing / trade execution. No wallet / private-key / signer surface.

## 7. Forbidden surfaces (Stage 29.5.4)

Stage 29.5.4 unlocks exactly one Stage 29.5.3 forbidden surface: **direct Stage 29.3 migration-context injection** (via the new optional `migration_source` kwarg).

Every other Stage 29.5.3 forbidden surface remains pinned at Stage 29.5.4. The Stage 29.5.4 manifest tuple `STAGE29_5_4_FORBIDDEN_SURFACES` is the canonical list; the Stage 29.5.4 manifest test asserts the tuple shape verbatim.

## 8. Files added at Stage 29.5.4

**Production (new):**

- `PHX2/stage29/stage29_5_4_migration_context_source_adapter.py`
- `PHX2/stage29/stage29_5_4_manifest.py`

**Doc (new):**

- `PHX2/stage29/STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md` (this file)

**Production (edited):**

- `PHX2/stage29/stage29_3_tradeable_smoke.py` — adds optional `migration_source: Optional[MigrationContextSource] = None` kwarg on `run_stage29_3_first_private_tradeable_smoke`; threads one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`; conditional fallback to `Stage29_3NoMigrationEvidenceSource()` when the kwarg is None. Adds the `MigrationContextSource` symbol to the existing Stage 27.4 import block. No other change.

**Tests (new):**

- `PHX2/tests/stage29/test_stage_29_5_4_migration_context_source_adapter.py`
- `PHX2/tests/stage29/test_stage_29_5_4_stage29_3_integration.py`
- `PHX2/tests/stage29/test_stage_29_5_4_default_preserves_no_migration_path.py`
- `PHX2/tests/stage29/test_stage_29_5_4_no_duplicate_dispatch.py`
- `PHX2/tests/stage29/test_stage_29_5_4_no_live_surface.py`
- `PHX2/tests/stage29/test_stage_29_5_4_no_public_no_enforcement_no_trading_no_social.py`
- `PHX2/tests/stage29/test_stage_29_5_4_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_5_4_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_4_spec_lock.py`
- `PHX2/tests/stage29/test_stage_29_5_4_counter_invariants.py`

**Tests (narrow allowlist widenings, test-files-only):**

- `PHX2/tests/stage28/test_stage_28_8_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_9_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_10_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_11_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py`
- `PHX2/tests/stage29/test_stage_29_5_spec_lock.py`
- `PHX2/tests/stage29/test_stage_29_5_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_5_2_no_integration_into_stage_29_3.py`
- `PHX2/tests/stage29/test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py`

## 9. Deferred after Stage 29.5.4

- **Formatted Discord rendering of migration context** — deferred to Stage 29.5.5. The Stage 29.5.4 adapter wires the migration context into the Stage 27.6 candidate assembler; the Stage 27.5 private ping renderer + Stage 28.9 dispatch body continue to render exactly as they did before Stage 29.5.4. Adding a migration-context section to the dispatched message body is a separately spec-locked decision (rendering format, closed-set field selection, redaction discipline).
- **Live Helius WebSocket migration-evidence ingestion** — deferred (the Stage 29.5 Helius WS adapter is the upstream layer the operator wires into the Stage 29.5.4 `evidence_provider` callable; today operators may pass an in-memory list or a Stage 29.5 artifact reader's output).
- **Stage 29.3 default flip from `NoMigrationEvidence` to a real source** — deferred indefinitely. The `migration_source` kwarg stays default-`None` forever; flipping the default is a separately spec-locked decision.
- **Stage 29.4 soak orchestrator auto-wires the Stage 29.5.4 adapter** — deferred. The soak orchestrator's pass-entrypoint contract is unchanged at Stage 29.5.4; operators may pass the Stage 29.5.4 adapter into the Stage 29.5.3 wrapper's `inner_pass_entrypoint` closure or directly into `run_stage29_3_first_private_tradeable_smoke`.
- **Stage 29.6+ implementation** — pinned absent in the Stage 29.5.4 forbidden-surface tuple.
- **Pump.fun bonding-curve decoder, Dexscreener, Helius-as-price-source, third / fourth provider** — all deferred.
- **PHX1 / legacy phoenix-1 import path** — permanently forbidden.

## 10. Operator runbook (minimal)

To exercise the Stage 29.5.4 opt-in injection in a controlled offline test:

```
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_4_migration_context_source_adapter import (
    Stage29_5_4MigrationContextSourceAdapter,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)

def evidence_provider(token_mint):
    return [
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=token_mint,
            pool_account=...,
            pool_program_id=...,
            quote_mint=...,
            migration_timestamp_utc=...,
            migration_slot=...,
            migration_signature=...,
            observed_at_utc=...,
            source_event_ref=...,
        ),
    ]

def ath_context_provider(token_mint):
    return ...  # optional Stage 27.4 AthContextRecord or None

adapter = Stage29_5_4MigrationContextSourceAdapter(
    evidence_provider=evidence_provider,
    ath_context_provider=ath_context_provider,
    clock=lambda: "2026-01-01T00:00:00+00:00",
)

result = run_stage29_3_first_private_tradeable_smoke(
    mode=...,
    runtime_configs=...,
    private_webhook_url=...,
    output_dir=...,
    live_env_ready=...,
    live_operator_request=...,
    migration_source=adapter,  # <-- Stage 29.5.4 opt-in
)
```

Omitting the `migration_source` kwarg restores the default `Stage29_3NoMigrationEvidenceSource()` injection byte-equivalently.

## 11. Stage 29.5.4 schema version

`stage29_5_4_v0_migration_context_source_adapter`

Pinned by `STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION` in both the adapter module and the Stage 29.5.4 manifest. Re-exported through the manifest for cross-checks.
