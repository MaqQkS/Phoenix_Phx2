# Stage 29.5.5 Private Discord Migration Context Rendering Runbook

## 1. Canonical Stage 29.5.5 mission sentence

Stage 29.5.5 is the formatted private Discord migration context rendering substage that adds a deterministic redaction-safe offline renderer plus a Stage 29.5.5 recording adapter and a Stage 29.5.5 side-channel artifact writer, threads one optional `migration_context_renderer` kwarg into `run_stage29_3_first_private_tradeable_smoke` so an operator may capture per-candidate rendered migration context blocks as a side-channel artifact without modifying the dispatched Discord body, and modifies no Stage 29.4, Stage 29.5, Stage 29.5.2, Stage 29.5.3, or Stage 29.5.4 production source.

## 2. Scope

Stage 29.5.5 ships:

- a pure renderer function (`render_private_discord_migration_context_block`) that projects a Stage 29.5 `Stage29_5PrivatePingMigrationContext` onto a Stage 29.5.5 `Stage29_5_5RenderedMigrationContextBlock` carrying deterministic plain-text lines plus a closed-set display-token field set;
- a Stage 29.5.5 recording adapter (`Stage29_5_5MigrationContextRecorder`) implementing the Stage 27.4 `MigrationContextSource` Protocol, with the same provider-chain constructor shape as the Stage 29.5.4 adapter, that on each `read_migration_snapshot(token_mint)` call computes the Stage 29.5.2 offline integration result once, optionally renders the projection (when an operator-supplied renderer callable is wired into the recorder's constructor), records the projection + the rendered block + the projected Stage 27.4 snapshot as a `Stage29_5_5RecordedRenderEntry`, and returns the same Stage 27.4 snapshot the Stage 29.5.4 adapter would have produced for the same inputs;
- a Stage 29.5.5 side-channel artifact writer (`Stage29_5_5SideChannelArtifactWriter`) that duck-types `migration_source.recorded_entries` and writes a deterministic JSON artifact bundle to a Stage 29.3 mode-3 `output_dir`;
- a constants-only Stage 29.5.5 manifest;
- this runbook and a dedicated Stage 29.5.5 test surface;
- one tiny edit to `stage29_3_tradeable_smoke.py`: a new keyword-only `migration_context_renderer: Optional[object] = None` kwarg on `run_stage29_3_first_private_tradeable_smoke` threaded one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`, with a post-session conditional call `migration_context_renderer.write_side_channel_artifact(output_dir=..., migration_source=resolved_migration_source)` inside a `try` / `except Exception: pass` guard. The kwarg is annotated `Optional[object]` so the Stage 29.3 production source carries ZERO `stage29_5_5*` imports (mirroring the Stage 29.5.4 patch's `Optional[MigrationContextSource]` typing discipline).

Stage 29.5.5 ships ZERO live Chainstack gRPC call, ZERO live Birdeye HTTP call, ZERO live Helius WebSocket call, ZERO live Discord send, ZERO Telegram / X / social sender, ZERO automated trading / wallet / private-key / signer surface, ZERO public / subscriber / paid-tier routing, ZERO Stage 26 enforcement activation, ZERO new env names, ZERO new third-party runtime dependency, ZERO Pump.fun bonding-curve decoder, ZERO Dexscreener / Helius as a price source, ZERO legacy (pre-PHX2) import path, ZERO Stage 29.4 runtime wiring change, ZERO Stage 29.5 manifest inventory change, ZERO Stage 29.5.2 manifest inventory change, ZERO Stage 29.5.3 manifest inventory change, ZERO Stage 29.5.4 manifest inventory change, ZERO change to the live dispatched Discord body, ZERO change to the Stage 28.9 dispatch ledger, and ZERO change to the Stage 28.4 audited Discord HTTP transport.

## 3. Why a separate Stage 29.5.5 substage

Stage 29.5.4 wired the Stage 29.5.2 offline composition into the Stage 29.3 mode-3 path via an opt-in `migration_source` kwarg whose value implements the Stage 27.4 `MigrationContextSource` Protocol. The Stage 29.5.4 adapter projects the Stage 29.5 `Stage29_5PrivatePingMigrationContext` down to a Stage 27.4 `MigrationSourceSnapshot` and discards the Stage 29.5 projection — the richer Stage 29.5 measurement status, warning codes, and post-migration ATH verification token never reach an operator-visible surface. The Stage 29.5.4 runbook (Section 9) explicitly deferred "formatted Discord rendering of migration context" to Stage 29.5.5, calling out that "Adding a migration-context section to the dispatched message body is a separately spec-locked decision (rendering format, closed-set field selection, redaction discipline)."

Stage 29.5.5 unlocks exactly that one surface for the OFFLINE / side-channel path. The Stage 29.5.5 design preserves the Stage 29.5 spec lock's pin "Discord dispatch behavior change (Stage 29.5 must not modify how Stage 28.4 dispatches, what audience receives the ping, or what the dispatch ledger records)" by deliberately NOT injecting the rendered block into the live dispatched message body. The Stage 29.5.5 rendered block is captured ONLY in a side-channel artifact file under the Stage 29.3 mode-3 `output_dir`; the Stage 27.5 private ping renderer and the Stage 28.4 audited HTTP transport and the Stage 28.9 dispatch wrapper continue to render + dispatch exactly as they did before Stage 29.5.5.

Wiring the rendered block into the live dispatched Discord body is a separately spec-locked decision deferred indefinitely (see Section 9).

## 4. Data flow

```
operator builds an evidence_provider callable
    (Stage29_5_4MigrationEvidenceProvider Protocol, reused)
        token_mint -> Sequence[Stage29_5MigrationEvidenceRecord]

operator builds an ath_context_provider callable
    (Stage29_5_4AthContextProvider Protocol, reused)
        token_mint -> Optional[AthContextRecord]

operator builds the Stage 29.5.5 renderer reference
    (the Stage 29.5.5 pure renderer fn or a fake that returns
     the same closed-set Stage29_5_5RenderedMigrationContextBlock
     shape)

operator builds the Stage 29.5.5 recording adapter:
    recorder = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_context_provider,
        clock=stage29_5_5_clock_callable,
        renderer=render_private_discord_migration_context_block,
        time_window_start_utc=None,
        time_window_end_utc=None,
        expected_pool_program_id=None,
    )

operator builds the Stage 29.5.5 side-channel artifact writer:
    writer = Stage29_5_5SideChannelArtifactWriter()

operator passes the recorder as migration_source AND the writer
as migration_context_renderer to
    run_stage29_3_first_private_tradeable_smoke.

# ---- Stage 29.3 mode-3 path (per ceremony) ----

per Stage 27.6 candidate assembly (one call per assembled
candidate, max_dispatches=1):

    snapshot = recorder.read_migration_snapshot(token_mint)
    # recorder internals:
    #   - safe-shape token_mint validation (UNKNOWN snapshot on
    #     unsafe shape, never raises)
    #   - candidate_axes = Stage29_5CandidateAxes(base_mint=token_mint)
    #   - evidence = evidence_provider(token_mint)
    #   - ath_context = ath_context_provider(token_mint)
    #   - result = run_stage29_5_2_offline_integration(...)
    #   - if renderer is wired:
    #         rendered_block = renderer(result.private_ping_context)
    #         recorder._recorded_entries.append(
    #             Stage29_5_5RecordedRenderEntry(
    #                 token_mint=token_mint,
    #                 projection=result.private_ping_context,
    #                 rendered_block=rendered_block,
    #                 snapshot=snapshot,
    #             )
    #         )
    #   - snapshot = closed-set projection (same closed-set
    #     mapping as the Stage 29.5.4 adapter; see Section 5)

    # Stage 27.4 read_migration_context consumes the snapshot
    # exactly as it would consume Stage29_3NoMigrationEvidenceSource's
    # output. The Stage 28.9 dispatch wrapper sees no Stage 29.5.5
    # surface; the dispatched Discord body is the unchanged Stage
    # 27.5 plain-text rendering of the Stage 27.4 measurement
    # context record.

# ---- end of Stage 28.9 session ----

# Stage 29.5.5 side-channel artifact write (post-session, only
# when migration_context_renderer is non-None AND write_artifacts
# is True):

    try:
        migration_context_renderer.write_side_channel_artifact(
            output_dir=output_dir,
            migration_source=recorder,
        )
    except Exception:
        # Side-channel artifact write failure is a degraded
        # outcome that does NOT affect the smoke result or the
        # dispatched-Discord outcome.
        pass

# ---- end of Stage 29.3 mode-3 ----

# default behavior (operator omits migration_context_renderer
# kwarg):
#   - run_stage29_3_first_private_tradeable_smoke(...,
#       migration_context_renderer=None)
#   - _run_mode_one_real_private_tradeable_ping_dry_run sees
#     migration_context_renderer is None and skips the post-
#     session call entirely. The Stage 29.3 mode-3 behavior is
#     BYTE-EQUIVALENT to the pre-Stage-29.5.5 code path.
```

The Stage 29.5.5 rendered block carries no raw payload, no raw URL, no raw secret, no Discord-side webhook reference, no wallet / private-key field, no audience-routing field, and no trading verdict (BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE / POSITION-SIZE / AUTO-TRADE language is rejected by the Stage 29.5.5 boundary scan). The rendered block always carries `redaction_status = SAFE` and `filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING`. The rendered block always carries an `informational_only = true` flag and an explicit `not_a_trading_verdict = true` flag so a downstream operator reviewer cannot misread the block as enforcement / dispatch authority.

## 5. Status display matrix (closed-set)

The Stage 29.5.5 renderer maps every Stage 29.5 `(measurement_status, migration_source, post_migration_ath_verified)` tuple onto a closed-set `(migration_evidence_status_display, migration_evidence_source_trust_display, post_migration_ath_verified_display)` triple. The mapping is deterministic, identity-pure, and never widens the closed-set output vocabulary.

### 5.1 `migration_evidence_status_display`

| Stage 29.5 `measurement_status` | Stage 29.5.5 `migration_evidence_status_display` |
|---|---|
| COMPLETE | `MIGRATION_EVIDENCE_COMPLETE` |
| PARTIAL_MIGRATION_PRESENT | `MIGRATION_EVIDENCE_PARTIAL` |
| MISSING_MIGRATION | `MIGRATION_EVIDENCE_MISSING` |
| INVALID_MIGRATION | `MIGRATION_EVIDENCE_INVALID` |
| CONFLICTING_MIGRATION | `MIGRATION_EVIDENCE_CONFLICTING` |

### 5.2 `migration_evidence_source_trust_display`

The source-trust display token is derived from BOTH the measurement status AND the Stage 29.5 `migration_source` so the renderer NEVER promotes a `COMPLETE` projection with a `SYNTHETIC_TEST_ONLY` or `UNKNOWN` source to a trusted-complete display token.

| measurement_status | migration_source | source_trust_display |
|---|---|---|
| COMPLETE | HELIUS_WS | `SOURCE_TRUSTED_ON_CHAIN` |
| COMPLETE | STAGE29_MIGRATION_ARTIFACT | `SOURCE_TRUSTED_ON_CHAIN` |
| COMPLETE | SYNTHETIC_TEST_ONLY | `SOURCE_UNTRUSTED_SYNTHETIC` |
| COMPLETE | UNKNOWN | `SOURCE_UNTRUSTED_UNKNOWN` |
| PARTIAL_MIGRATION_PRESENT | HELIUS_WS | `SOURCE_PARTIAL_ON_CHAIN` |
| PARTIAL_MIGRATION_PRESENT | STAGE29_MIGRATION_ARTIFACT | `SOURCE_PARTIAL_ON_CHAIN` |
| PARTIAL_MIGRATION_PRESENT | SYNTHETIC_TEST_ONLY | `SOURCE_PARTIAL_SYNTHETIC` |
| PARTIAL_MIGRATION_PRESENT | UNKNOWN | `SOURCE_NO_SOURCE` |
| MISSING_MIGRATION | any | `SOURCE_NO_SOURCE` |
| INVALID_MIGRATION | HELIUS_WS | `SOURCE_PARTIAL_ON_CHAIN` |
| INVALID_MIGRATION | STAGE29_MIGRATION_ARTIFACT | `SOURCE_PARTIAL_ON_CHAIN` |
| INVALID_MIGRATION | SYNTHETIC_TEST_ONLY | `SOURCE_PARTIAL_SYNTHETIC` |
| INVALID_MIGRATION | UNKNOWN | `SOURCE_NO_SOURCE` |
| CONFLICTING_MIGRATION | HELIUS_WS | `SOURCE_PARTIAL_ON_CHAIN` |
| CONFLICTING_MIGRATION | STAGE29_MIGRATION_ARTIFACT | `SOURCE_PARTIAL_ON_CHAIN` |
| CONFLICTING_MIGRATION | SYNTHETIC_TEST_ONLY | `SOURCE_PARTIAL_SYNTHETIC` |
| CONFLICTING_MIGRATION | UNKNOWN | `SOURCE_NO_SOURCE` |

### 5.3 `post_migration_ath_verified_display`

| Stage 29.5 `post_migration_ath_verified` | Stage 29.5.5 `post_migration_ath_verified_display` |
|---|---|
| True | `ATH_VERIFIED_POST_MIGRATION` |
| False | `ATH_NOT_VERIFIED_POST_MIGRATION` |
| None | `ATH_VERIFICATION_UNKNOWN` |

### 5.4 Echo fields

The renderer echoes the following Stage 29.5 projection fields verbatim onto the rendered block:

- `migration_timestamp_utc_display` — the projection's `migration_timestamp_utc` string when populated, otherwise the literal token `MISSING`.
- `migration_slot_display` — `str(projection.migration_slot)` when populated, otherwise the literal token `MISSING`.
- `migration_source_token` — echo of `projection.migration_source` (closed-set Stage 29.5 token).
- `join_status_echoed_token` — echo of `projection.join_status_echoed` (closed-set Stage 29.5 token).
- `warnings_display` — comma-joined sorted-by-input-order sequence of `projection.warnings`, or the literal token `NONE` when empty.
- `redaction_status` — echo of `projection.redaction_status` (always `SAFE` by the Stage 29.5 projection contract; the renderer rejects any other value with `ValueError`).
- `filter_enforcement_status` — echo of `projection.filter_enforcement_status` (always `NOT_ACTIVE_STAGE_29_PENDING` by the Stage 29.5 projection contract; the renderer rejects any other value with `ValueError`).
- `observed_at_utc` — echo of `projection.observed_at_utc`.

### 5.5 Informational-only flags

Every rendered block carries the following two boolean flags as pinned `True`:

- `informational_only` — pins that the block is a private operator audit surface only, not a dispatch authority.
- `not_a_trading_verdict` — pins that the block is NOT a BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE / POSITION-SIZE / AUTO-TRADE verdict.

The renderer is the sole authority that constructs the block; the operator cannot override either flag from the call site.

## 6. Acceptance criteria

**A.** `render_private_discord_migration_context_block(projection)` is a pure function — same inputs always produce the same `Stage29_5_5RenderedMigrationContextBlock`; no env reads, no network, no file I/O.

**B.** The renderer rejects non-`Stage29_5PrivatePingMigrationContext` inputs with `ValueError`. The renderer rejects any projection carrying a non-`SAFE` redaction status with `ValueError`. The renderer rejects any projection carrying a non-`NOT_ACTIVE_STAGE_29_PENDING` filter enforcement status with `ValueError`.

**C.** Every renderer output carries `informational_only = True`, `not_a_trading_verdict = True`, `redaction_status = SAFE`, and `filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING`.

**D.** The status display matrix in Section 5 is enforced verbatim by the renderer's closed-set mapping function. A `COMPLETE` projection with a `SYNTHETIC_TEST_ONLY` or `UNKNOWN` migration source NEVER renders as `SOURCE_TRUSTED_ON_CHAIN`.

**E.** The rendered block's `body_text` field is a deterministic plain-text rendering of the closed-set display tokens; the line order, label vocabulary, and whitespace are pinned by the renderer and the renderer test surface. The `body_text` never contains BUY / SELL / APPROVED / GATE / BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE / AUTO-TRADE language.

**F.** The renderer output carries NO raw URL host literal, NO raw API-key shape, NO raw webhook URL, NO raw Helius / Chainstack / Birdeye payload, NO wallet / private-key / signer field, and NO pre-PHX2 / legacy import reference. The Stage 29.5.5 redaction test surface enforces the closed-set forbidden-substring tuple (URL hosts, API-key prefixes, webhook URLs, env-name assignment prefixes, legacy bot identifiers) against the rendered block AND the side-channel artifact JSON.

**G.** `Stage29_5_5MigrationContextRecorder.read_migration_snapshot(token_mint)` returns a Stage 27.4 `MigrationSourceSnapshot` for every input — never raises. The Stage 27.4 snapshot produced by the recorder for a given `(evidence, ath_context, time_window)` triple is identical to the snapshot the Stage 29.5.4 adapter would produce for the same inputs (same closed-set projection rules).

**H.** When the operator constructs the recorder WITH a renderer callable, every `read_migration_snapshot(token_mint)` call records one `Stage29_5_5RecordedRenderEntry` on the recorder's `recorded_entries` tuple (capturing the token_mint, the Stage 29.5 projection, the rendered block, and the Stage 27.4 snapshot). When the operator omits the renderer, the recorder records ZERO entries and behaves byte-equivalently to a Stage 29.5.4 adapter on the Stage 27.4 snapshot axis.

**I.** `Stage29_5_5SideChannelArtifactWriter.write_side_channel_artifact(output_dir, migration_source)` writes a deterministic JSON artifact file under `output_dir` when `migration_source` exposes a `recorded_entries` attribute carrying at least one entry; otherwise it no-ops (returns None) without raising. The writer NEVER opens a network connection, NEVER reads the process environment, and NEVER touches a wallet / private-key / signer surface.

**J.** The default Stage 29.3 mode-3 call (no `migration_context_renderer` kwarg) does NOT invoke any Stage 29.5.5 surface; the Stage 29.3 mode-3 outcome and Stage 28.9 counters are BYTE-EQUIVALENT to the pre-Stage-29.5.5 code path.

**K.** When the operator passes a Stage 29.5.5 side-channel writer as `migration_context_renderer` to `run_stage29_3_first_private_tradeable_smoke` AND a Stage 29.5.5 recorder as `migration_source`, AND `write_artifacts=True`, the post-session side-channel artifact write happens exactly once; the dispatched-Discord count remains exactly one; the Stage 28.9 dispatch ledger record is unchanged.

**L.** Stage 29.3 production source carries NO `stage29_5_5*` import; the new kwarg's static type is `Optional[object]` to keep the existing "Stage 29.3 does not import any stage29_5* module" pin green.

**M.** Stage 29.4 production source is untouched at Stage 29.5.5; the Stage 29.4 soak orchestrator continues to import zero `stage29_5*` modules.

**N.** Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 / Stage 29.5.4 production source is untouched at Stage 29.5.5; the Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 / Stage 29.5.4 manifest production-inventory tuples are unchanged byte-for-byte.

**O.** The recorder's `filter_enforcement_status` flows through unchanged: the locked `NOT_ACTIVE_STAGE_29_PENDING` token is preserved on every Stage 29.5.5 code path. The side-channel artifact carries the locked enforcement token verbatim.

**P.** The Stage 29.5.5 production source reads zero env names. The Stage 29.5.5 production source imports zero outbound-network libraries (no `urllib`, no `requests`, no `httpx`, no `aiohttp`, no `websockets`, no `websocket`, no `http.client`, no `socket`, no `grpc`, no `asyncio`).

**Q.** No public / subscriber / paid-tier routing. No Stage 26 enforcement activation. No Telegram / X / social sender. No automated trading / position sizing / trade execution. No wallet / private-key / signer surface.

**R.** No duplicate dispatch occurs: with `max_dispatches=1`, the Stage 29.3 mode-3 ceremony makes at most one Discord call regardless of whether the Stage 29.5.5 recorder + writer are wired. The Stage 28.9 dispatch ledger semantics are unchanged. The Stage 29.5.5 side-channel artifact write is a local file write that does NOT call Stage 28.4 audited HTTP transport.

## 7. Forbidden surfaces (Stage 29.5.5)

Stage 29.5.5 unlocks exactly one Stage 29.5.4 forbidden surface: **formatted Discord rendering** (via the new Stage 29.5.5 pure renderer + recording adapter + side-channel writer + the optional `migration_context_renderer` kwarg on Stage 29.3 mode-3). The unlocked surface is OFFLINE / side-channel only; the live dispatched Discord body is unchanged.

Every other Stage 29.5.4 forbidden surface remains pinned at Stage 29.5.5. The Stage 29.5.5 manifest tuple `STAGE29_5_5_FORBIDDEN_SURFACES` is the canonical list; the Stage 29.5.5 manifest test asserts the tuple shape verbatim. Additionally, the following surfaces are explicitly forbidden at Stage 29.5.5 and are pinned by the Stage 29.5.5 boundary scan:

- **changing the live dispatched Discord body** — Stage 29.5.5 ships ZERO modification to the Stage 27.5 private ping renderer, the Stage 28.4 audited HTTP transport, the Stage 28.9 dispatch wrapper, or the Stage 28.2 dispatch ledger.
- **public-side rendering** — the Stage 29.5.5 renderer is consumed by the side-channel writer only; it never reaches a public / subscriber / paid-tier audience surface (none of which exist in PHX2).
- **enforcement activation** — the rendered block carries the locked `NOT_ACTIVE_STAGE_29_PENDING` enforcement token verbatim and an explicit `not_a_trading_verdict = True` flag.
- **trading verdict language** — BUY / SELL / APPROVED / GATE / BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE / AUTO-TRADE language is rejected by the Stage 29.5.5 boundary scan over both the production source and the rendered block's `body_text`.

## 8. Files added at Stage 29.5.5

**Production (new):**

- `PHX2/stage29/stage29_5_5_render_models.py`
- `PHX2/stage29/stage29_5_5_private_discord_migration_context_renderer.py`
- `PHX2/stage29/stage29_5_5_migration_context_recorder.py`
- `PHX2/stage29/stage29_5_5_side_channel_artifact_writer.py`
- `PHX2/stage29/stage29_5_5_manifest.py`

**Doc (new):**

- `PHX2/stage29/STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md` (this file)

**Production (edited):**

- `PHX2/stage29/stage29_3_tradeable_smoke.py` — adds optional `migration_context_renderer: Optional[object] = None` kwarg on `run_stage29_3_first_private_tradeable_smoke` (keyword-only); threads one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`; post-session, when `migration_context_renderer is not None` AND `write_artifacts is True`, calls `migration_context_renderer.write_side_channel_artifact(output_dir=..., migration_source=resolved_migration_source)` inside a `try` / `except Exception: pass` guard. Default behavior (`migration_context_renderer=None`) is byte-equivalent to the pre-Stage-29.5.5 code path. No other change to Stage 29.3 production source.

**Tests (new):**

- `PHX2/tests/stage29/test_stage_29_5_5_render_models.py`
- `PHX2/tests/stage29/test_stage_29_5_5_renderer.py`
- `PHX2/tests/stage29/test_stage_29_5_5_status_matrix.py`
- `PHX2/tests/stage29/test_stage_29_5_5_migration_context_recorder.py`
- `PHX2/tests/stage29/test_stage_29_5_5_side_channel_artifact_writer.py`
- `PHX2/tests/stage29/test_stage_29_5_5_redaction.py`
- `PHX2/tests/stage29/test_stage_29_5_5_stage29_3_integration.py`
- `PHX2/tests/stage29/test_stage_29_5_5_default_preserves_no_renderer_path.py`
- `PHX2/tests/stage29/test_stage_29_5_5_no_duplicate_dispatch.py`
- `PHX2/tests/stage29/test_stage_29_5_5_no_live_surface.py`
- `PHX2/tests/stage29/test_stage_29_5_5_no_enforcement_activation.py`
- `PHX2/tests/stage29/test_stage_29_5_5_no_public_no_enforcement_no_trading_no_social.py`
- `PHX2/tests/stage29/test_stage_29_5_5_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_5_5_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_5_spec_lock.py`
- `PHX2/tests/stage29/test_stage_29_5_5_counter_invariants.py`

**Tests (narrow allowlist widenings, test-files-only):**

- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py` — add Stage 29.5.5 production + test allowlist frozensets; union into the existing Stage 29.0+29.1 production + test unions; extend the `test_no_python_module_under_stage29_beyond_init` allowed-py union.
- `PHX2/tests/stage29/test_stage_29_5_spec_lock.py` — extend the `only_planned_stage29_5_py_modules_exist_at_29_5_1` exclusion to also skip `stage29_5_5_*.py` (same one-line shape as the existing 29.5.2 / 29.5.3 / 29.5.4 exclusions).

## 9. Deferred after Stage 29.5.5

- **Injecting the Stage 29.5.5 rendered block into the live dispatched Discord body** — deferred indefinitely. The Stage 29.5 spec lock pins "Discord dispatch behavior change (Stage 29.5 must not modify how Stage 28.4 dispatches, what audience receives the ping, or what the dispatch ledger records)"; a future spec-locked substage would need to either widen the Stage 29.5 spec lock or layer a Stage 27.5.x edit. Stage 29.5.5 does NOT take either step.
- **Public / subscriber / paid-tier rendering of the migration context** — permanently forbidden under the Stage 29.5 spec lock's no-public-routing / no-subscriber-routing / no-paid-tier-routing pins.
- **Live Helius WebSocket migration-evidence ingestion** — deferred (the Stage 29.5 Helius WS adapter is the upstream layer the operator wires into the Stage 29.5.5 recorder's `evidence_provider` callable; today operators may pass an in-memory list or a Stage 29.5 artifact reader's output).
- **Stage 29.3 default flip from `NoMigrationEvidence` to a real source** — deferred indefinitely. The `migration_source` kwarg + the `migration_context_renderer` kwarg both stay default-`None` forever; flipping either default is a separately spec-locked decision.
- **Stage 29.4 soak orchestrator auto-wires the Stage 29.5.5 recorder** — deferred. The soak orchestrator's pass-entrypoint contract is unchanged at Stage 29.5.5; operators may pass the Stage 29.5.5 recorder into the Stage 29.5.3 wrapper's `inner_pass_entrypoint` closure or directly into `run_stage29_3_first_private_tradeable_smoke`.
- **Stage 29.6+ implementation** — pinned absent in the Stage 29.5.5 forbidden-surface tuple.
- **Pump.fun bonding-curve decoder, Dexscreener, Helius-as-price-source, third / fourth provider** — all deferred.
- **Legacy / pre-PHX2 import path** — permanently forbidden.

## 10. Operator runbook (minimal)

To exercise the Stage 29.5.5 opt-in renderer + side-channel artifact write in a controlled offline test:

```
from PHX2.stage29.stage29_3_tradeable_smoke import (
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    Stage29_5_5SideChannelArtifactWriter,
)

def evidence_provider(token_mint):
    return [...]  # Stage 29.5 migration evidence records

def ath_context_provider(token_mint):
    return ...   # optional Stage 27.4 AthContextRecord or None

recorder = Stage29_5_5MigrationContextRecorder(
    evidence_provider=evidence_provider,
    ath_context_provider=ath_context_provider,
    clock=lambda: "2026-01-01T00:00:00+00:00",
    renderer=render_private_discord_migration_context_block,
)

writer = Stage29_5_5SideChannelArtifactWriter()

result = run_stage29_3_first_private_tradeable_smoke(
    mode=...,
    runtime_configs=...,
    private_webhook_url=...,
    output_dir=...,
    live_env_ready=...,
    live_operator_request=...,
    migration_source=recorder,
    migration_context_renderer=writer,  # <-- Stage 29.5.5 opt-in
)
```

Omitting the `migration_context_renderer` kwarg restores the default behavior byte-equivalently (no side-channel artifact, no rendering, no recording attempt). Passing a recorder as `migration_source` with `renderer=None` records nothing and behaves byte-equivalently to the Stage 29.5.4 adapter on the Stage 27.4 snapshot axis.

## 11. Stage 29.5.5 schema versions

`stage29_5_5_v0_private_discord_migration_context_renderer` — the pure renderer module's schema version pin.

`stage29_5_5_v0_rendered_migration_context_block` — the `Stage29_5_5RenderedMigrationContextBlock` dataclass's schema version pin.

`stage29_5_5_v0_migration_context_recorder` — the recorder class's schema version pin.

`stage29_5_5_v0_side_channel_artifact_writer` — the side-channel artifact writer's schema version pin.

Each pin is re-exported through the Stage 29.5.5 manifest module for cross-checks.
