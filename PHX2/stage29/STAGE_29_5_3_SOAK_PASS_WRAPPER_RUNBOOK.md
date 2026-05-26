# Stage 29.5.3 Soak Pass-Entrypoint Wrapper Runbook

## 1. Canonical Stage 29.5.3 mission sentence

Stage 29.5.3 is the runtime-adjacent soak pass-entrypoint wrapper and side-channel artifact surface substage that lets an operator thread the Stage 29.5.2 offline migration context composition into the Stage 29.4 short-session private soak path without modifying any Stage 29.3 or Stage 29.4 production source.

## 2. Scope

Stage 29.5.3 ships:

- a runtime-adjacent soak pass-entrypoint wrapper around an INJECTED inner Stage 29.4 pass entrypoint;
- a side-channel artifact writer that persists one JSONL observation line per pass into `stage29_5_3_migration_context.jsonl` inside the operator-supplied soak output directory;
- closed-set Stage 29.5.3 observation status vocabulary + immutable Stage 29.5.3 wrapped-pass observation record;
- a constants-only Stage 29.5.3 manifest;
- this runbook and a dedicated test surface.

Stage 29.5.3 ships ZERO live Chainstack gRPC call, ZERO live Birdeye HTTP call, ZERO live Helius WebSocket call, ZERO Discord send, ZERO Telegram / X / social sender, ZERO automated trading / wallet / private-key / signer surface, ZERO public / subscriber / paid-tier routing, ZERO Stage 26 enforcement activation, ZERO new env names, ZERO new third-party runtime dependency, ZERO Pump.fun bonding-curve decoder, ZERO Dexscreener / Helius as a price source, ZERO PHX1 import path, ZERO direct Stage 29.3 migration-context injection, ZERO Stage 29.5 manifest inventory change, ZERO Stage 29.5.2 manifest inventory change.

## 3. Why a separate Stage 29.5.3 substage

Stage 29.5.2 shipped the offline composition proof: a pure function that joins a Stage 29.5 candidate to a sequence of Stage 29.5 migration evidence records and projects a Stage 29.5 private ping migration context with a Stage 27.4 ATH context. Stage 29.5.2 explicitly forbade two surfaces:

- the soak pass-entrypoint wrapper that bridges the offline composition into the Stage 29.4 soak path;
- the side-channel artifact surface that persists per-pass observations.

Stage 29.5.3 unlocks exactly those two surfaces, in new `stage29_5_3_*.py` files under `PHX2/stage29/`, with the same offline / observational discipline Stage 29.5.2 applied to the composition itself. The wrapper does NOT modify any Stage 29.3 production file, does NOT modify any Stage 29.4 production file, and does NOT modify any Stage 29.5 / Stage 29.5.2 production file.

## 4. Data flow

The Stage 29.5.3 wrapper is DEFERRED-OBSERVATION. The wrapper's `__call__` performs only the inner pass delegation plus a minimal pending-observation append; provider / composition / artifact work is moved out to an explicit post-soak step (`flush_pending_observations`). This invariant pins that the wrapper does NOT add latency inside the Stage 29.4 timed pass boundary (the Stage 29.4 orchestrator's wall-clock pre-check and post-pass-check fire identically whether the operator wraps the inner entrypoint or runs it raw).

```
operator builds production_pass_entrypoint
    (Stage 29.4 Stage29_4PassEntrypoint over
     run_stage29_3_first_private_tradeable_smoke)

operator builds an evidence_provider callable
    (Stage29_5_3MigrationEvidenceProvider Protocol)

operator builds an ath_context_provider callable
    (Stage29_5_3AthContextProvider Protocol)

operator wraps:
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=production_pass_entrypoint,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_context_provider,
        clock=stage29_5_3_clock_callable,
        time_window_start_utc=None,                # caller-supplied
        time_window_end_utc=None,                  # caller-supplied
        expected_pool_program_id=None,             # caller-supplied
        write_side_channel_artifact=True,
    )

operator passes the wrapper as pass_entrypoint to
    run_stage29_4_short_session_private_soak.

# ---- Stage 29.4 timed pass boundary (per pass) ----

per pass (wrapper.__call__(pass_index, bounds, soak_output_dir)):

    inner_result = inner_pass_entrypoint(
        pass_index=pass_index,
        bounds=bounds,
        soak_output_dir=soak_output_dir,
    )
    # Stage 29.3 ceremony runs. Stage 27.6 sources bundle STILL
    # carries Stage29_3NoMigrationEvidenceSource (Stage 29.3
    # production unchanged). Stage 28.9 dispatch semantics
    # UNCHANGED.

    candidate_base_mint = (
        inner_result.dedupe_key.token_mint
        if inner_result.dedupe_key is not None
           and is_stage29_5_3_safe_candidate_base_mint(
               inner_result.dedupe_key.token_mint,
           )
        else None
    )

    wrapper._pending.append(
        Stage29_5_3PendingPassObservation(
            pass_index=pass_index,
            candidate_base_mint=candidate_base_mint,
            soak_output_dir=soak_output_dir,
        )
    )

    return inner_result   # BYTE-EQUAL ECHO. NO mutation.
                          # NO subclass. Stage 29.4 soak
                          # orchestrator's isinstance check
                          # passes by construction.

# ---- end of Stage 29.4 timed pass boundary ----
# Stage 29.4 returns the Stage29_4SoakSummary here.
# Wrapper has NOT called evidence_provider, NOT called
# ath_context_provider, NOT called
# run_stage29_5_2_offline_integration, NOT written the
# side-channel artifact, NOT called the operator clock.

# ---- post-soak flush (operator-driven) ----

composed = wrapper.flush_pending_observations()    # strict=False default

# per pending (flush walks self._pending in pass-arrival order):

    observed_at_utc = clock()   # only here, never in __call__

    if pending.candidate_base_mint is None:
        observation_status = "NO_CANDIDATE_AXES"
        composition_result = None
    else:
        candidate_axes = Stage29_5CandidateAxes(
            base_mint=pending.candidate_base_mint,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
        )
        try:
            evidence_records = evidence_provider(
                base_mint=candidate_axes.base_mint,
            )
            ath_context = ath_context_provider(
                base_mint=candidate_axes.base_mint,
            )
            composition_result = run_stage29_5_2_offline_integration(
                candidate_axes=candidate_axes,
                evidence_records=evidence_records,
                ath_context=ath_context,
                clock=clock,
                time_window_start_utc=time_window_start_utc,
                time_window_end_utc=time_window_end_utc,
                expected_pool_program_id=expected_pool_program_id,
            )
            observation_status = "COMPOSED"
        except Stage29_5_3MigrationEvidenceProviderError:
            # strict=False default: swallow + record closed-set.
            # strict=True: re-raise.
            observation_status = "PROVIDER_REJECTED"
        except Stage29_5_2OfflineIntegrationError:
            observation_status = "COMPOSITION_REJECTED"

    observation = Stage29_5_3WrappedPassObservation(
        pass_index=pending.pass_index,
        observation_status=observation_status,
        candidate_base_mint=<...>,
        join_status_echoed=<...>,
        measurement_status_echoed=<...>,
        post_migration_ath_verified_echoed=<...>,
        warnings_echoed=<tuple>,
        observed_at_utc=observed_at_utc,
        filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING,
        redaction_status=SAFE,
        schema_version="stage29_5_3_wrapped_pass_observation_v0",
    )
    wrapper._observations.append(observation)

    if write_side_channel_artifact:
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=pending.soak_output_dir,
            observation=observation,
        )    # non-strict: best-effort, errors swallowed
             # strict: errors propagate
```

The wrapper must return the inner result by identity (Python `is` equality). The wrapper never constructs a new `Stage29_4PassResult` value and never wraps the inner result in a subclass; it returns the exact same object reference the inner pass entrypoint produced. Tests pin this invariant by asserting `wrapper(...) is inner_result`.

The deferred-observation design guarantees:

- `wrapper.__call__` calls the inner pass entrypoint exactly once.
- `wrapper.__call__` returns the inner pass result by identity.
- `wrapper.__call__` does NOT call `evidence_provider`.
- `wrapper.__call__` does NOT call `ath_context_provider`.
- `wrapper.__call__` does NOT call `run_stage29_5_2_offline_integration`.
- `wrapper.__call__` does NOT write the side-channel artifact.
- `wrapper.__call__` does NOT call the operator clock.
- The Stage 29.4 timed pass boundary therefore observes only the inner pass latency. Slow / failing providers cannot perturb Stage 29.4 soak summary counters (`passes_attempted`, `dispatch_success_total`, `soak_outcome`, etc.).

Operator post-soak flush API:

- `wrapper.pending_observations` — a tuple snapshot of pending observations awaiting flush.
- `wrapper.flush_pending_observations(strict=False)` — materializes composed observations, optionally writes the JSONL side-channel artifact, and returns a tuple of the observations newly composed by this flush call. Non-strict mode (default) swallows provider / composition / artifact failures into the closed-set observation status. Strict mode propagates them so the operator can retry.
- `wrapper.observations` — a tuple snapshot of every composed observation materialized by past flush calls, in pass-arrival order.

### 4.1 Why deferred observation

The earlier inline-observation design called `evidence_provider`, `ath_context_provider`, `run_stage29_5_2_offline_integration`, and the artifact writer from inside `wrapper.__call__`. The Stage 29.4 orchestrator checks wall-clock elapsed BEFORE each pass AND AFTER each pass; any latency inside `wrapper.__call__` therefore extends the pass-boundary measurement. A slow evidence provider trip-time of T seconds shifts the post-pass wall-clock check by T seconds, which can flip the closed-set soak outcome from `COMPLETED_AT_DISPATCH_CAP` (raw inner) to `COMPLETED_AT_WALL_CLOCK` (wrapped inner) and reduce `passes_attempted` / `dispatch_success_total` accordingly. The deferred-observation design pins zero provider / composition / artifact latency inside the Stage 29.4 timed pass boundary so the wrapped soak summary equals the raw inner soak summary byte-for-byte (modulo the wall-clock-derived `start_utc_iso` / `end_utc_iso` / `elapsed_wall_clock_seconds` axes that legitimately differ across two distinct orchestrator runs).

## 5. Closed-set observation status vocabulary

The Stage 29.5.3 wrapper records exactly one of four closed-set tokens on every per-pass observation:

- `NO_CANDIDATE_AXES` -- the inner pass returned no dedupe-key candidate (the inner pass observed `SUPPRESSED_*` / `NO_EVENT_RECEIVED` / `FAILED` / `REFUSED` outcomes; or the dedupe key was present but the `token_mint` rejected the Stage 29.5 safe-shape validator).
- `COMPOSED` -- the wrapper successfully built candidate axes, called `run_stage29_5_2_offline_integration`, and captured the closed-set Stage 29.5 join / projection verdict.
- `COMPOSITION_REJECTED` -- the Stage 29.5.2 composition raised on caller-shape / validator grounds; the wrapper swallowed the error and recorded the closed-set status.
- `PROVIDER_REJECTED` -- the operator-supplied evidence-provider / ATH-context-provider raised; the wrapper swallowed the error and recorded the closed-set status.

The observation record is observational only. Nothing on it gates the Stage 28.9 dispatch chain, the Stage 29.3 smoke outcome, or the Stage 29.4 soak summary outcome.

## 6. Side-channel artifact

The wrapper optionally appends one JSONL line per observation into the locked basename `stage29_5_3_migration_context.jsonl` under the operator-supplied soak output directory. Each line is a canonical JSON object with sorted keys, no extra whitespace, and an LF terminator. The encoding is deterministic: same observation -> byte-equal line.

The JSONL line carries only:

- the closed-set Stage 29.5.3 schema version (`stage29_5_3_wrapped_pass_observation_v0`);
- the 1-based pass index;
- the closed-set observation status token;
- the optional candidate base mint echo;
- the optional Stage 29.5 join status echo;
- the optional Stage 29.5 measurement status echo;
- the optional Stage 29.5 `post_migration_ath_verified` echo;
- the Stage 29.5 warning code tuple echo (as a JSON array);
- the safe-shape observed_at_utc string;
- the locked `filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`;
- the locked `redaction_status=SAFE`.

No webhook URL, RPC endpoint, API key, bearer token, auth header, raw provider payload, or raw exception string is ever carried on the JSONL line.

Artifact write failures (closed-set `Stage29_5_3SideChannelArtifactError` or `OSError`) are swallowed by the wrapper; they never affect the inner Stage 29.4 pass result and never change the soak outcome.

## 7. Stage 29.5.3 acceptance criteria (offline)

A. The Stage 29.5.3 focused test suite passes against the new production tree.

B. The full Stage 29 test suite continues to pass (Stage 29.0..29.5.2 regressions hold byte-for-byte).

C. The Stage 29.5 regression suite (`test_stage_29_5_*.py`) continues to pass; the Stage 29.5 production 6-file inventory is unchanged.

D. The Stage 29.0 spec-lock test passes with its narrow allowlist widening for the Stage 29.5.3 inventory.

E. The four touched Stage 28 boundary tests pass with their narrow allowlist widenings.

F. No Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 / Stage 29.5 / Stage 29.5.2 production .py file is modified at Stage 29.5.3.

G. No live Chainstack gRPC call is performed during the Stage 29.5.3 work.

H. No live Birdeye HTTP call is performed during the Stage 29.5.3 work.

I. No live Helius WebSocket call is performed during the Stage 29.5.3 work.

J. No private operator Discord send is performed during the Stage 29.5.3 work.

K. No tag is created and no push is performed by the automated agent.

## 8. Forbidden surfaces under Stage 29.5.3

Stage 29.5.3 must not include:

- production enforcement,
- public routing,
- subscriber routing,
- paid tier routing,
- Telegram sender / Telegram client,
- X / social sidecar,
- automated trading / position sizing / trade execution,
- wallet / private-key / signer logic,
- private keys,
- Discord dispatch behavior change,
- formatted Discord rendering of migration context,
- public dashboard / HTTP control server,
- new env name,
- new third-party runtime dependency,
- PHX1 import path,
- direct PHX1 spaghetti copy,
- Pump.fun bonding-curve decoder,
- Dexscreener as a dispatch authority,
- Helius as a price source,
- live Helius WebSocket call during Stage 29.5.3 work,
- live Chainstack gRPC call during Stage 29.5.3 work,
- live Birdeye HTTP call during Stage 29.5.3 work,
- live Discord call during Stage 29.5.3 work,
- Stage 29.3 runtime wiring change,
- Stage 29.4 runtime wiring change,
- Stage 29.5 manifest inventory change,
- Stage 29.5.2 manifest inventory change,
- direct Stage 29.3 migration-context injection,
- Stage 29.6+ implementation.

Stage 29.5.3 must not create a `stage-29-5-3-closed` tag.

Stage 29.5.3 must not push to any remote.

## 9. Files added at Stage 29.5.3

Production / docs added under `PHX2/stage29/`:

- `PHX2/stage29/stage29_5_3_wrapped_pass_models.py`
- `PHX2/stage29/stage29_5_3_soak_pass_wrapper.py`
- `PHX2/stage29/stage29_5_3_side_channel_artifact_writer.py`
- `PHX2/stage29/stage29_5_3_manifest.py`
- `PHX2/stage29/STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md`

Tests added under `PHX2/tests/stage29/`:

- `PHX2/tests/stage29/test_stage_29_5_3_wrapped_pass_models.py`
- `PHX2/tests/stage29/test_stage_29_5_3_soak_pass_wrapper.py`
- `PHX2/tests/stage29/test_stage_29_5_3_side_channel_artifact_writer.py`
- `PHX2/tests/stage29/test_stage_29_5_3_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_3_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py`
- `PHX2/tests/stage29/test_stage_29_5_3_spec_lock.py`

Narrow test-files-only allowlist widenings (no production source edited). Exactly seven files are widened at Stage 29.5.3:

- `PHX2/tests/stage28/test_stage_28_8_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_9_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_10_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_11_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py`
- `PHX2/tests/stage29/test_stage_29_5_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_spec_lock.py`

The Stage 29.5.2 test files (`test_stage_29_5_2_manifest.py` and `test_stage_29_5_2_boundaries.py`) are NOT touched at Stage 29.5.3. The Stage 29.5.2 manifest already pins `"soak pass-entrypoint wrapper"` on its forbidden-surface tuple from the Stage 29.5.2 commit, and the Stage 29.5.2 boundary test already pins `"soak_pass_wrapper"` / `"stage29_5_3_"` on its forbidden later-substage-identifier substring tuple from the Stage 29.5.2 commit. Neither file requires a Stage 29.5.3 widening; both remain byte-for-byte identical to their Stage 29.5.2 state.

## 10. Carried-over Stage 29.3 / Stage 29.4 artifact-projection caveat

Stage 29.3 mode-3 ceremonies and Stage 29.4 mode-3 ceremonies still emit per-event artifact files with a safe-shape default projection (NO_EXTRACTION / MISSING) when the per-event hint extraction / Birdeye snapshots are not threaded back out to the artifact writer. Stage 29.5.3 acceptance does NOT depend on those projections being cleaned up. The authoritative proof axes remain the Stage 28.9 health-snapshot counters and the Stage 28.2 dispatch ledger terminal record. Cleaning up the Stage 29.3 / Stage 29.4 artifact projections is reserved for a separate operator-gated substage and is explicitly NOT part of Stage 29.5.3.

## 11. Deferred after Stage 29.5.3

The following surfaces remain deferred to a future operator-authorized substage:

- formatted Discord rendering of migration context;
- live Helius WS migration-evidence ingestion driving the evidence provider;
- public / subscriber / paid-tier routing of migration-context-aware pings;
- Stage 26 / Stage 29 policy enforcement activation;
- ghost-pair / measurement-status filters wired into Stage 28.9 suppression vocabulary;
- direct Stage 29.3 migration-context source swap (option C from the planning brief);
- Stage 29 closure (`stage-29-closed` annotated tag still unwritten);
- Stage 29.6+ implementation.
