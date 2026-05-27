# Stage 29.6 Spec Lock

## 1. Stage 29.6 stance pin

Stage 29.6 is Option A only: a bounded private single-shot live proof using the existing Stage 29.3 mode-3 entrypoint with the already-committed Stage 29.5.5 recorder + Stage 29.5.5 side-channel writer + Stage 29.5.6 injector wired through the existing optional kwargs on `run_stage29_3_first_private_tradeable_smoke`. Stage 29.6 ships ZERO new production .py file, ZERO orchestrator, ZERO wrapper module, ZERO renderer change, ZERO new data source, ZERO new live provider code, ZERO modification to any Stage 27 / Stage 28 / Stage 29.3 / Stage 29.4 / Stage 29.5.4 / Stage 29.5.5 / Stage 29.5.6 production source file, ZERO public / subscriber / paid routing, ZERO Telegram / X / social surface, ZERO enforcement activation, ZERO Axiom or Ante filter, ZERO trading / wallet / signing surface, and ZERO Stage 30 anticipation.

## 2. Stage 29.6 allowed file inventory

The Stage 29.6 file inventory under the PHX2 repo is exactly:

- `PHX2/stage29/STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md` — the Stage 29.6 runbook.
- `PHX2/stage29/STAGE_29_6_SPEC_LOCK.md` — this file.
- `PHX2/tests/stage29/test_stage_29_6_spec_lock.py` — the Stage 29.6 spec-lock pin tests.
- `PHX2/tests/stage29/test_stage_29_6_bounded_live_proof.py` — the Stage 29.6 fake end-to-end acceptance test.

Stage 29.6 adds NO other file under the PHX2 repo at this substage. Any additional Stage 29.6 file requires a separately-authorized widening.

## 3. Stage 29.6 forbidden production-source touch list

Stage 29.6 MUST NOT add, modify, rename, delete, re-export, or otherwise touch any of:

- `PHX2/stage27/*` (all of Stage 27 production source).
- `PHX2/stage28/*` production files (all of Stage 28 production source).
- `PHX2/stage29/stage29_3_tradeable_smoke.py` (Stage 29.3 orchestrator).
- `PHX2/stage29/stage29_3_*.py` (any Stage 29.3 production module).
- `PHX2/stage29/stage29_4_*.py` (Stage 29.4 production modules).
- `PHX2/stage29/stage29_5_4_*.py` (Stage 29.5.4 production modules).
- `PHX2/stage29/stage29_5_5_*.py` (Stage 29.5.5 production modules).
- `PHX2/stage29/stage29_5_6_*.py` (Stage 29.5.6 production modules).
- `PHX2/stage29/stage29_5_2_*.py` / `PHX2/stage29/stage29_5_3_*.py` (Stage 29.5.2 / 29.5.3 production).
- `PHX2/stage29/stage29_5_*.py` and `PHX2/stage29/stage29_5_manifest.py` (Stage 29.5 production).
- `PHX2/stage29/stage29_1_*.py`, `PHX2/stage29/pumpswap_*.py`, `PHX2/stage29/birdeye_*.py`, `PHX2/stage29/stage29_2_*.py` (Stage 29.1 / 29.2 production).
- any private Discord sender, transport, or webhook production module.
- any live provider, Birdeye, Chainstack, Helius, or other RPC / WebSocket / HTTP production module.
- any routing, enforcement, trading, wallet, signing, position-sizing, or trade-execution production module.
- any public, subscriber, paid-tier, Telegram, X, or social production module.
- any Axiom-fee, Ante, or other new-filter-framework production module.
- any Pump.fun bonding-curve decoder.
- any daemon, watchdog, autorestart, dashboard, or HTTP control-server module.

## 4. Stage 29.6 allowed test-side widenings (allowlist-only, zero logic)

Stage 29.6 is permitted to widen the existing strict-inventory allowlists in the following ALREADY-existing test files to admit the two Stage 29.6 markdown basenames into the "Stage 29 production allowed" sets and the two Stage 29.6 test basenames into the "Stage 29 tests allowed" sets. The widenings introduce ZERO test logic, ZERO new assertion, and ZERO production logic; they are pure set-membership additions mirroring the Stage 29.5.6 allowlist-widening pattern:

- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py`.
- `PHX2/tests/stage28/test_stage_28_8_boundaries.py`.
- `PHX2/tests/stage28/test_stage_28_9_boundaries.py`.
- `PHX2/tests/stage28/test_stage_28_10_boundaries.py`.
- `PHX2/tests/stage28/test_stage_28_11_boundaries.py`.

Stage 29.6 MUST NOT widen any other test file. Stage 29.6 MUST NOT modify any production .py file.

## 5. Stage 29.6 ceremony pins

- The Stage 29.6 live ceremony is single-shot: exactly one Stage 29.3 mode-3 invocation dispatching exactly one private Discord ping.
- Stage 29.3 mode 3 keeps `max_events=1` / `max_dispatches=1` / `max_total_retries=0` / `max_ticks=1` verbatim; Stage 29.6 NEVER widens these bounds.
- Stage 29.6 NEVER closes, tags, or pushes Stage 29.
- Stage 29.6 NEVER starts Stage 30.
- Stage 29.6 NEVER sends a Telegram / X / social message.
- Stage 29.6 NEVER activates Stage 26 / Stage 29 enforcement.
- Stage 29.6 NEVER touches a wallet, signer, private key, or seed phrase surface.
- Stage 29.6 NEVER sizes or executes a trade.
- Stage 29.6 NEVER routes to a public, subscriber, or paid-tier audience.

## 6. Stage 29.6 testing discipline pins

- Stage 29.6 fake end-to-end test opens ZERO outbound network connection.
- Stage 29.6 fake end-to-end test uses a fake Chainstack channel factory, a fake Birdeye HTTP transport, and a fake Stage 28.4 audited Discord transport.
- Stage 29.6 fake end-to-end test captures the dispatched payload in memory and asserts the cross-path migration-context safety pins are present.
- Stage 29.6 fake end-to-end test asserts the Stage 28.9 dispatch counter is exactly one.
- Stage 29.6 fake end-to-end test asserts the absent-recorder branch degrades gracefully without raising.
- Stage 29.6 fake end-to-end test asserts the expected artifact basenames exist under the test's scratch `output_dir`.

## 7. Stage 29.6 acceptance criteria recap

Stage 29.6 is accepted when the four-file inventory under Section 2 ships, the allowed allowlist-only widenings under Section 4 land, the existing Stage 29.5.X tests continue to pass without modification, the Stage 29 + Stage 29.5 + Stage 29.0 spec-lock tests continue to pass with the widened allowlists, the four touched Stage 28 boundary tests continue to pass with the widened allowlists, and the Stage 29.6 acceptance tests pass. No commit / tag / push is performed at Stage 29.6 implementation time; commit gating is a separate operator decision after Codex audit.

## 8. Stage 29.6 live-call abstinence pins

The Stage 29.6 implementation substage is strictly offline. The following bullets are non-negotiable pins and MUST hold at Stage 29.6 implementation time:

- Stage 29.6 implementation/tests perform ZERO live WS/gRPC/HTTP calls.
- Stage 29.6 implementation/tests perform ZERO live Discord sends.
- The Stage 29.6 live ceremony requires separate explicit operator authorization before any live WS/gRPC/HTTP call or Discord send.
- Stage 29.6 implementation/commit does not itself run the live ceremony.

These pins distinguish the Stage 29.6 implementation substage (this commit's contents — pure docs + fake-driven tests + narrow allowlist widenings) from the Stage 29.6 live ceremony (the separately-authorized operator-run Section 6 phases of the runbook). The implementation substage NEVER touches a real Chainstack gRPC channel, NEVER calls a real Birdeye HTTP endpoint, NEVER opens a real Helius WebSocket, and NEVER sends to a real Discord webhook. The live ceremony — when, and only when, separately authorized by the operator — runs the Section 6 phases of `STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md` against the operator's own scratch workspace outside the PHX2 repo and is NOT performed as part of Stage 29.6 implementation or commit.
