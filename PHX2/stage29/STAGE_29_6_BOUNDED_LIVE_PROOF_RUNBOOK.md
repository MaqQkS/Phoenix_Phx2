# Stage 29.6 Bounded Private Single-Shot Live Proof Runbook (Option A)

## 1. Canonical Stage 29.6 mission sentence

Stage 29.6 is the bounded private single-shot live proof substage that uses the existing Stage 29.3 mode 3 `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN` entrypoint wired with the already-committed Stage 29.5.5 migration context recorder, the already-committed Stage 29.5.5 side-channel artifact writer, and the already-committed Stage 29.5.6 private Discord body injector to prove end-to-end that exactly one private operator Discord ping reaches the operator-supplied private webhook with the Stage 29.5.5 rendered migration context block visible in the operator-visible private ping body (either as the full rendered block or as the deterministic compact fallback) and with every Stage 28.9 / Stage 29.3 / Stage 29.5.5 acceptance artifact captured under the operator-supplied scratch `output_dir`, while shipping ZERO new production .py file, ZERO orchestrator or wrapper module, ZERO renderer change, ZERO new data source, ZERO new live provider code, ZERO modification to any Stage 27 / Stage 28 / Stage 29.3 / Stage 29.4 / Stage 29.5.4 / Stage 29.5.5 / Stage 29.5.6 production source, ZERO public / subscriber / paid / Telegram / X / social routing, ZERO enforcement activation, ZERO Axiom / Ante filter, ZERO trading / wallet / signing surface, ZERO Stage 30 anticipation, and ZERO commit / tag / push at Stage 29.6 implementation time.

## 2. Scope

Stage 29.6 (Option A) ships:

- this runbook (`STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md`);
- a Stage 29.6 spec-lock markdown (`STAGE_29_6_SPEC_LOCK.md`) that pins the Option A no-production-code stance and the forbidden-file list;
- two Stage 29.6 acceptance test files under `PHX2/tests/stage29/`:
  - `test_stage_29_6_spec_lock.py` — pins the Option A stance against this runbook + the absence of any `stage29_6_*.py` production file;
  - `test_stage_29_6_bounded_live_proof.py` — fake end-to-end Stage 29.3 mode-3 ceremony with the Stage 29.5.5 recorder + Stage 29.5.5 side-channel writer + Stage 29.5.6 injector wired through the existing `run_stage29_3_first_private_tradeable_smoke` entrypoint, capturing exactly one fake-transport-recorded private payload with the migration context block visible (full or compact);
- five narrow allowlist widenings in already-existing test inventory pins (`test_stage_29_0_spec_lock.py` + four Stage 28 boundary tests `test_stage_28_8_boundaries.py` / `test_stage_28_9_boundaries.py` / `test_stage_28_10_boundaries.py` / `test_stage_28_11_boundaries.py`) so the new Stage 29.6 markdown and test files are admitted by the existing strict-inventory scans. The widenings add the two Stage 29.6 markdown basenames to each "Stage 29 production allowed" set and the two Stage 29.6 test basenames to each "Stage 29 tests allowed" set; the widenings introduce ZERO test logic, ZERO production logic, and ZERO Stage 29.6 module name.

Stage 29.6 ships ZERO new `stage29_6_*.py` production module, ZERO orchestrator, ZERO wrapper, ZERO renderer change, ZERO new data source, ZERO new live provider code, ZERO live Chainstack gRPC call, ZERO live Birdeye HTTP call, ZERO live Helius WebSocket call, ZERO live Discord send during implementation or tests, ZERO Telegram / X / social sender, ZERO automated trading / wallet / private-key / signer surface, ZERO public / subscriber / paid-tier routing, ZERO Stage 26 enforcement activation, ZERO new env names, ZERO new third-party runtime dependency, ZERO Pump.fun bonding-curve decoder, ZERO Dexscreener / Helius-as-price-source, ZERO Axiom fee filter, ZERO Ante filter, ZERO Stage 29.3 / Stage 29.4 / Stage 29.5.4 / Stage 29.5.5 / Stage 29.5.6 production source modification, ZERO Stage 27.5 private ping renderer modification, ZERO Stage 28.4 audited HTTP transport modification, ZERO Stage 28.9 dispatch wrapper modification, ZERO change to the Stage 29.3 default behavior when none of the optional Stage 29.5.X kwargs are supplied, ZERO Stage 30 anticipation, ZERO Stage 29 closure or tag, ZERO commit, ZERO push.

## 3. Why Stage 29.6 = Option A

Stage 29.5.6 closed the last piece of pre-live wiring: the private Discord body migration context injector is committed locally (HEAD `1bc7cdd`), the Stage 29.5.5 recorder is committed, the Stage 29.5.5 side-channel writer is committed, the Stage 29.3 entrypoint already accepts the optional `migration_source` / `migration_context_renderer` / `private_discord_body_injector` kwargs, and Stage 29.3 mode 3 already locks `max_events=1` / `max_dispatches=1` / `max_total_retries=0` / `max_ticks=1`. Composing those existing exports into one bounded single-shot live proof needs ZERO new production module: it needs an operator scratch script (documented here in Section 6) plus a fake-driven acceptance test that verifies the same composition wires together correctly. Adding a Stage 29.6 orchestrator wrapper would create new domain logic that the operator does not need to reach the goal. Adding renderer changes would touch Stage 27.5 / Stage 29.5.5 production source, which is forbidden. Option A is therefore both the minimum and the maximum Stage 29.6 should ship.

## 4. Stage 29.6 success criteria

For Stage 29.6 to be declared successful AFTER the operator runs the ceremony in Section 6 the following pins MUST hold:

**A.** The private ping is sent exactly once to the operator-supplied private webhook (Stage 28.9 `dispatch_success == 1`, Stage 29.3 `tradeable_smoke_outcome == DISPATCHED`).

**B.** The dispatched body carries the Stage 29.5.5 migration context (either as the full Stage 29.5.5 rendered block carrying the `PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT` header, or as the deterministic compact fallback opening with the `[MIGRATION CONTEXT]` header). On either branch the dispatched body MUST carry the three Stage 29.5.5 safety pin lines `filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING`, `informational_only: true`, `not_a_trading_verdict: true`.

**C.** Every Stage 28.9 + Stage 29.3 + Stage 29.5.5 acceptance artifact exists under the operator-supplied `output_dir`:
  - Stage 28.9: `stage28_9_dispatch_ledger.jsonl`, `stage28_9_heartbeat.jsonl`, `stage28_9_health_snapshot.json`, `stage28_9_final_run_summary.json`.
  - Stage 29.3: `stage29_3_tradeable_smoke_result.json`, `stage29_3_extracted_hints.json`, `stage29_3_birdeye_evidence.json`, `stage29_3_redaction_scan.json`.
  - Stage 29.5.5: `stage29_5_5_side_channel_migration_context_artifact.json`.

**D.** The Stage 29.3 redaction scan artifact (`stage29_3_redaction_scan.json`) reports its closed-set status as the safe verdict.

**E.** No webhook URL, Chainstack endpoint, Chainstack x-token, Birdeye API key, Birdeye base URL, Helius API key, bearer token, authorization header, wallet / private-key / signer field, raw upstream provider payload blob, or Pump.fun bonding-curve program-id literal appears in any artifact file under `output_dir` (operator manual confirmation in addition to the Stage 29.3 redaction scan).

**F.** The operator confirms the dispatched body is readable / useful for the bounded live proof, OR records a precise readability complaint in the post-ceremony operator report so the Stage 30 planning chat can pick up the readability axis from a concrete artifact.

**G.** The Stage 29.6 ceremony NEVER activates Stage 26 / Stage 29 enforcement, NEVER routes to public / subscriber / paid audiences, NEVER sends to Telegram / X / any social surface, NEVER touches an Axiom fee filter or Ante filter, NEVER touches a wallet / signer surface, NEVER executes a trade, NEVER closes or tags Stage 29, and NEVER starts Stage 30.

## 5. Exact wiring (what the operator scratch script composes)

Stage 29.6 reuses the already-exported existing surfaces verbatim. The operator scratch script (an out-of-tree `.py` file the operator owns in their scratch workspace; the runbook does NOT commit this file) composes them as follows:

```
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    build_runtime_configs_from_env,
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
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
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    Stage29_5_6PrivateDiscordBodyInjector,
)
```

The operator then constructs the four pieces:

1. `recorder = Stage29_5_5MigrationContextRecorder(evidence_provider=..., ath_context_provider=..., clock=..., renderer=render_private_discord_migration_context_block)` — the operator supplies the three callables backed by the operator's evidence + ATH-context surfaces. The `renderer` callable is bound so Phase 2 of the recorder records each rendered block.
2. `writer = Stage29_5_5SideChannelArtifactWriter()` — wired into the `migration_context_renderer` kwarg below; on Stage 29.3 mode 3 completion this writes the `stage29_5_5_side_channel_migration_context_artifact.json` artifact under `output_dir`.
3. `injector = Stage29_5_6PrivateDiscordBodyInjector(migration_source=recorder)` — bound to the same recorder reference passed to the Stage 29.3 `migration_source` kwarg below; Stage 29.3 mode 3 calls `injector.wrap_transport(transport)` to produce the body-injecting wrapper.
4. `runtime_configs = build_runtime_configs_from_env(chainstack_mode=...)` — builds the Stage 28.11 + Stage 29.2 readiness boundaries from the operator's environment.

The operator runs:

```
result = run_stage29_3_first_private_tradeable_smoke(
    mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    runtime_configs=runtime_configs,
    private_webhook_url=<operator-supplied private webhook URL>,
    output_dir=<operator-supplied scratch path outside the PHX2 repo>,
    live_env_ready=True,
    live_operator_request=True,
    known_mint=<operator-supplied base mint>,
    migration_source=recorder,
    migration_context_renderer=writer,
    private_discord_body_injector=injector,
)
```

Stage 29.3 mode 3 keeps its locked bounds verbatim: `max_events=1`, `max_dispatches=1`, `max_total_retries=0`, `max_ticks=1`, `heartbeat_every_n_events=1`, `session_mode=LIVE_PRIVATE`. The operator does NOT pass any of those bounds; they live inside `_run_mode_one_real_private_tradeable_ping_dry_run` and Stage 29.6 does NOT widen them.

## 6. Live ceremony (do not run until the operator is authorized)

Stage 29.6 is single-shot. The operator runs each phase sequentially; later phases assume the earlier phases succeeded.

### Phase 0 — Operator preparation (offline, no network calls)

- Pick a scratch `output_dir` outside the PHX2 repo (e.g. `~/phx2_stage29_6_proof_<date>/`); the directory MUST exist, be a directory, and live entirely outside the PHX2 working tree.
- Verify the env vars are set for: Stage 28.11 Chainstack Yellowstone endpoint + x-token, Stage 29.2 Birdeye API key + base URL, the operator-supplied private webhook URL.
- Do NOT export the env vars in the same shell the operator commits or pushes from; keep the live ceremony shell separate.
- Decide and commit on the operator's `known_mint` (a real Solana base mint the operator wants to cross-reference for the Phase 2 Birdeye `/defi/price` call).
- Do NOT set `live_env_ready=True` or `live_operator_request=True` until Phase 3 is ready to run.

### Phase 1 — Readiness-only (Stage 29.3 mode 1, NO live calls)

Run `run_stage29_3_first_private_tradeable_smoke(mode=PROBE_MODE_READINESS_ONLY, ...)` with `live_env_ready=True` and `live_operator_request=True` to verify the three readiness gates pass without opening the gRPC channel, without calling Birdeye, and without sending Discord. Expected outcome: `tradeable_smoke_outcome == READY` with `tradeable_smoke_refusal_reason == NONE`. The Stage 29.3 acceptance artifact bundle is written under `output_dir` for the operator's record. No network calls in Phase 1.

### Phase 2 — Connect-only (Stage 29.3 mode 2, Chainstack + Birdeye, NO Discord send)

Run `run_stage29_3_first_private_tradeable_smoke(mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY, ..., known_mint=<operator-supplied base mint>)` with `live_env_ready=True` and `live_operator_request=True`. The Stage 29.3 hint-aware Chainstack gRPC channel opens, runs one short Subscribe scan, and the Birdeye `/defi/price` endpoint is called once for the operator-supplied known mint. NO Discord send is performed in Phase 2. Expected outcome: `tradeable_smoke_outcome == CONNECTED` with both transports proven healthy.

### Phase 3 — Bounded private mode-3 (Stage 29.3 mode 3, exactly one Discord send)

This is the only Stage 29.6 phase that sends to Discord. The operator explicitly re-confirms `live_env_ready=True` and `live_operator_request=True` immediately before running this phase. The operator constructs the four wiring pieces from Section 5 and calls `run_stage29_3_first_private_tradeable_smoke(mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN, ..., migration_source=recorder, migration_context_renderer=writer, private_discord_body_injector=injector)`. Stage 29.3 mode 3 opens the Chainstack channel, drains exactly one hint-bearing transaction (`max_events=1`), assembles exactly one Stage 27.6 candidate, runs Stage 28.9 with `max_dispatches=1`, and the Stage 29.5.6 wrapper appends the Stage 29.5.5 rendered migration context to the Stage 28.9 body (full block when it fits, deterministic compact block when the full would overflow the 1900-char combined-content cap). Expected outcome: `tradeable_smoke_outcome == DISPATCHED`.

### Phase 4 — Artifact capture (no network calls)

The operator confirms every expected artifact exists under `output_dir`:

- Stage 28.9 (4 artifacts): `stage28_9_dispatch_ledger.jsonl`, `stage28_9_heartbeat.jsonl`, `stage28_9_health_snapshot.json`, `stage28_9_final_run_summary.json`.
- Stage 29.3 (4 artifacts): `stage29_3_tradeable_smoke_result.json`, `stage29_3_extracted_hints.json`, `stage29_3_birdeye_evidence.json`, `stage29_3_redaction_scan.json`.
- Stage 29.5.5 (1 artifact): `stage29_5_5_side_channel_migration_context_artifact.json`.

The operator does NOT modify, move, copy outside `output_dir`, or upload any of these artifacts during Phase 4. The artifact bundle stays local.

### Phase 5 — Redaction scan (no network calls)

The operator confirms `stage29_3_redaction_scan.json` reports the safe closed-set status. The operator additionally runs a manual local grep over every artifact under `output_dir` for the URL host literal substrings, the bearer / authorization header literal substrings, the API-key prefix substrings, and the wallet / private-key / signer literal substrings; any hit aborts Stage 29.6 and the operator records the leak for triage. No leak is the only acceptable outcome.

### Phase 6 — Operator readability report (no network calls)

The operator captures the dispatched body content (visually confirmed in the operator's private Discord channel) and writes a `stage29_6_live_proof_report.md` in the operator's scratch space (NOT committed to the PHX2 repo). The report records: which append branch fired (full block or deterministic compact fallback), whether the body was readable and useful for the bounded proof, any specific readability complaint that should feed Stage 30 planning, and an explicit "Stage 30 NOT started" note. The report stays local. The operator does NOT commit, tag, or push during Stage 29.6.

## 7. Stage 29.6 forbidden surfaces

Stage 29.6 MUST NOT touch any of:

- `PHX2/stage27/*` (all of Stage 27 production source);
- `PHX2/stage28/*` production files (all of Stage 28 production source; read-only references only);
- `PHX2/stage29/stage29_3_tradeable_smoke.py` (Stage 29.3 production);
- `PHX2/stage29/stage29_4_*.py` (Stage 29.4 production);
- `PHX2/stage29/stage29_5_4_*.py` (Stage 29.5.4 production);
- `PHX2/stage29/stage29_5_5_*.py` (Stage 29.5.5 production);
- `PHX2/stage29/stage29_5_6_*.py` (Stage 29.5.6 production);
- any private Discord sender or transport production file;
- any live provider, Birdeye, Chainstack, or Helius production file;
- any routing, enforcement, trading, wallet, or signing file;
- any public, subscriber, paid-tier, Telegram, X, or social file.

Stage 29.6 MUST NOT add any `PHX2/stage29/stage29_6_*.py` production file, any orchestrator or wrapper module, any renderer change, any new data source, or any new live provider code. The only Stage 29.6 deliverables are the two markdown files and the two test files under `PHX2/tests/stage29/`.

## 8. Stage 29.6 non-goals

Stage 29.6 explicitly does NOT:

- start Stage 30 or anticipate Stage 30 design choices;
- close, tag, or push Stage 29;
- add public, subscriber, or paid-tier routing;
- add a Telegram, X, or social sender surface;
- activate Stage 26 / Stage 29 policy enforcement;
- add an Axiom fee filter, an Ante filter, or any new filter framework;
- add a trading, wallet, signing, or position-sizing surface;
- add a new data source for market cap, liquidity, volume, or token-age;
- add a new live provider surface beyond Stage 28.11 (Chainstack) + Stage 29.2 (Birdeye);
- introduce a daemon, watchdog, autorestart, dashboard, or HTTP control server;
- introduce any new production .py file or any production-source modification.

## 9. Stage 29.6 testing discipline

Stage 29.6 tests are fake-driven by construction. The `test_stage_29_6_bounded_live_proof.py` test composes the Stage 29.5.5 recorder + Stage 29.5.5 side-channel writer + Stage 29.5.6 injector through the Stage 29.3 mode-3 entrypoint with the existing fake Chainstack channel factory, the existing fake Birdeye HTTP transport, and a fake Stage 28.4 audited Discord transport that captures the dispatched payload in memory. No real Chainstack gRPC channel is opened by the test. No real Birdeye HTTP request is sent by the test. No real Discord webhook is hit by the test. The test asserts the dispatched body carries the Stage 29.5.5 migration context (via the cross-path safety-pin markers), the Stage 28.9 dispatch counter is exactly one, and the Stage 29.5.5 side-channel artifact exists under the test's scratch `output_dir`. A second test variant pins that omitting the recorder degrades gracefully (no Stage 29.5.5 block in dispatched body, no Stage 29.5.5 artifact written, dispatch still succeeds via the Stage 28.9 path).

## 10. Stage 30 note

Stage 30 remains undefined at Stage 29.6 implementation time. Stage 30 will be planned in a separate chat AFTER the operator runs the Section 6 ceremony and writes the Phase 6 readability report. Likely Stage 30 candidates include private-body readability polish, longer private reliability soak, an operator workflow cleanup, or a focused bug fix — the exact direction depends on what the live proof reveals. Stage 29.6 makes ZERO Stage 30 design commitment.

## 11. Stage 29.6 acceptance criteria letters

**A.** Stage 29.6 ships ZERO new `stage29_6_*.py` production module under `PHX2/stage29/`.

**B.** Stage 29.6 ships `STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md` (this file) and `STAGE_29_6_SPEC_LOCK.md` under `PHX2/stage29/`.

**C.** Stage 29.6 ships `test_stage_29_6_spec_lock.py` and `test_stage_29_6_bounded_live_proof.py` under `PHX2/tests/stage29/`.

**D.** Stage 29.6 widens the existing strict-inventory allowlists in `test_stage_29_0_spec_lock.py` + four Stage 28 boundary tests by adding the Stage 29.6 markdown basenames + Stage 29.6 test basenames; the widenings introduce ZERO test logic and ZERO production logic.

**E.** Stage 29.6 modifies ZERO Stage 27, Stage 28, Stage 29.3, Stage 29.4, Stage 29.5.4, Stage 29.5.5, or Stage 29.5.6 production source file.

**F.** The fake end-to-end Stage 29.6 acceptance test wires the existing Stage 29.3 + Stage 29.5.5 recorder + Stage 29.5.5 side-channel writer + Stage 29.5.6 injector and dispatches exactly one fake-captured private payload with the migration context block visible.

**G.** The fake end-to-end Stage 29.6 acceptance test confirms the Stage 28.9 dispatch counter axis is exactly one (the locked Stage 29.3 mode-3 `max_dispatches=1` bound is honored).

**H.** The Stage 29.6 acceptance tests perform ZERO outbound network call.

**I.** The Stage 29.6 acceptance tests assert that omitting the recorder degrades the dispatched body gracefully (no Stage 29.5.5 block; dispatch still succeeds).

**J.** The Stage 29.6 acceptance tests pin the expected artifact basename inventory under the test's scratch `output_dir`.

**K.** The Stage 29.6 runbook (this file) names the Stage 29.3 modes `READINESS_ONLY`, `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY`, `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN` verbatim.

**L.** The Stage 29.6 runbook pins `max_events=1` and `max_dispatches=1` as already locked by Stage 29.3 mode 3.

**M.** The Stage 29.6 runbook names the three exact Stage 29.3 optional kwargs `migration_source`, `migration_context_renderer`, `private_discord_body_injector`.

**N.** The Stage 29.6 runbook names the two operator authorization gates `live_env_ready=True` and `live_operator_request=True`.

**O.** The Stage 29.6 runbook explicitly forbids Stage 30, enforcement activation, public / subscriber / paid routing, Telegram / X / social senders, Axiom / Ante filters, and trading / wallet / signing surfaces.

**P.** The Stage 29.6 runbook does not introduce any URL host literal, bearer / authorization literal, API-key prefix literal, raw secret literal, Pump.fun bonding-curve program-id literal, or legacy pre-PHX2 substring.

**Q.** The Stage 29.6 runbook describes the Stage 29.5.6 injector's full-first / compact-fallback / skip-only-when-both-overflow discipline and the 1900-char combined-content cap pin.

**R.** The Stage 29.6 ceremony is single-shot (exactly one Discord dispatch on Phase 3) and the operator does NOT commit, tag, or push during the ceremony.

## 12. Stage 29.6 file inventory pin

The Stage 29.6 file inventory is exactly:

- `PHX2/stage29/STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md` (this file).
- `PHX2/stage29/STAGE_29_6_SPEC_LOCK.md`.
- `PHX2/tests/stage29/test_stage_29_6_spec_lock.py`.
- `PHX2/tests/stage29/test_stage_29_6_bounded_live_proof.py`.

Any additional Stage 29.6 file requires a separate authorization. Any `PHX2/stage29/stage29_6_*.py` file is forbidden at Stage 29.6.
