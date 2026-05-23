# PHX2 Stage 28.7 — Longer-Session Smoke Checklist

This checklist is the operator gate for running and accepting a
Stage 28.7 longer-session offline smoke. It pairs with
`STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md`. Stage 28.7 is
**offline-only**: the production harness opens no network
connection, never reads the process environment, never invokes a
real Discord webhook, never connects to a real provider, never
performs a real live send, and never executes a real trade.

If any item below fails, the smoke must be considered FAILED. Do
NOT proceed to the controlled live smoke runbook until every
offline item passes, and never close Stage 28 from this checklist
— closure audit + Stage 29 handoff are Stage 28.8 scope, not
Stage 28.7.

---

## A. Pre-smoke checks (repo state)

- [ ] **Git status shows only known pre-existing untracked paths.**
      Run `git status --short` before kicking off the smoke. The
      only entries permitted are the known pre-existing untracked
      paths (e.g. `PHX2/.stage_17_inputs/`,
      `PHX2/docs/stage_summaries/`, `ROADMAP.md`). Any other
      untracked file is unexpected; investigate before continuing.

- [ ] **No `stage-28` tag exists.** Run `git tag --list "stage-28*"`
      and confirm the result is empty. Stage 28 tag creation is
      reserved for the Stage 28.8 closure pass with explicit
      operator authorization. Stage 28.7 must not create the
      `stage-28-closed` tag.

- [ ] **No Stage 28 closure audit doc exists yet.** Run
      `git ls-files PHX2/stage28 | grep -E "STAGE_28_CLOSURE_AUDIT|STAGE_29_HANDOFF|stage28_manifest\\.py"`
      and confirm the result is empty. Those filenames are
      reserved for Stage 28.8.

- [ ] **The Stage 28.7 production files exist exactly.** Run
      `git ls-files PHX2/stage28 | sort` and confirm the Stage
      28.7 entries are exactly
      `longer_session_smoke_harness.py`,
      `stage28_7_manifest.py`,
      `STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md`, and
      `STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md`.

- [ ] **No live provider / API calls are enabled.** Inspect the
      smoke harness import graph:
      `python -c "import PHX2.stage28.longer_session_smoke_harness,
      sys; print(sorted(m for m in sys.modules if 'requests' in m
      or 'httpx' in m or 'aiohttp' in m or 'urllib3' in m or
      'urllib' in m or 'websockets' in m or 'grpc' in m or
      'discord' in m or 'telegram' in m or 'socket' in m))"`. The
      printed list MUST be empty.

- [ ] **Env-read boundary remains isolated to Stage 27's
      `live_secrets_readiness.py`.** Run
      `grep -nE "os\\.environ|os\\.getenv|os\\.environb" PHX2/stage28`
      and confirm the result is empty. Stage 28.7 adds no env
      reads of its own.

- [ ] **Offline output directory is out-of-repo (outside the
      tracked production tree).** The smoke harness refuses to
      run without an explicitly injected `output_dir`. The unit
      test suite uses `pytest`'s tmp dir; an operator running the
      harness by hand must pass an out-of-repo path that is
      outside the tracked Stage 28 production tree (e.g. a
      freshly-created scratch directory outside the repo).

---

## B. Post-smoke checks (artifacts)

- [ ] **Stage 28.7 smoke artifacts are present.** Every Stage
      28.7 smoke run writes
      `stage28_7_heartbeat.jsonl`,
      `stage28_7_health_snapshot.json`,
      `stage28_7_final_run_summary.json`,
      `stage28_7_smoke_summary.json`, and the optional
      `stage28_7_redaction_scan.json` into the operator-supplied
      `output_dir`. Open each file and confirm every value is a
      closed-set token, a canonical decimal-text number, or a
      short safe-to-display string.

- [ ] **redaction scan passes.** Inspect
      `stage28_7_redaction_scan.json`. The `redaction_status`
      field MUST be `SAFE`. If it is `FAILED`, abort the smoke
      review, investigate which artifact tripped which forbidden
      substring during the redaction scan, and rerun only after
      the root cause is fixed.

- [ ] **No webhook URL appears in any artifact.** Grep each
      artifact:
      `grep -rE "h""ttps?://|w""ss?://|/webhooks/|discord""\\.com|discord""app\\.com" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No raw secret / auth header appears in any artifact.**
      Grep each artifact:
      `grep -rEi "(api[_-]?key|bearer|authorization|private_key|wallet_seed|signer_address)" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No raw provider response body appears in any artifact.**
      Grep each artifact:
      `grep -rE "raw_response|response_body|raw_payload|payload_blob" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No public-routing / subscriber-routing / paid-tier
      language appears in any artifact.** Grep:
      `grep -rEi "(subscriber_id|public_channel_id|paid_tier|route_id|approval_status|enforcement_result)" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE /
      POSITION-SIZE / AUTO-TRADE / ENFORCEMENT language appears
      in any artifact.** Grep:
      `grep -rEi "(buy_signal|sell_signal|approved|gate_decision|block_trade|execute_trade|position_size|auto_trade|enforcement_gate)" <output_dir>`.
      The grep MUST return nothing. Stage 28.7 is a private smoke
      harness, not a trading verdict surface.

---

## C. Smoke summary counters

- [ ] **`schema_version == "stage28_7_longer_session_smoke_harness_v0"`.**
      Any other value indicates a stale artifact or a manifest
      drift; investigate before continuing.

- [ ] **`smoke_status` is `OK` or `DEGRADED`.** `REFUSED` means
      the harness refused to run (e.g. redaction failure or
      output-dir refusal); abort and inspect the closed-set
      `safe_reason_code`.

- [ ] **`redaction_status == "SAFE"`.** Any other value is a
      blocker. `NOT_SCANNED` is acceptable only when the operator
      deliberately disabled the scan and ran an external scanner.

- [ ] **`live_send_attempted == false` and `live_send_count == 0`.**
      Stage 28.7 production code never performs a live send;
      these fields must be `false` / `0` on every offline smoke
      summary.

- [ ] **`offline_candidate_count` matches the input synthetic
      stream size** (10 for the default
      `build_stage28_7_synthetic_candidates()` stream).

- [ ] **`events_seen` >= `offline_candidate_count` is false
      only when the harness short-circuited on `max_events`.**
      For the default smoke `events_seen` equals
      `offline_candidate_count`.

- [ ] **`dispatch_success` >= 1 and `dispatch_failure` is zero**
      for the default synthetic stream (the first dispatchable
      candidate exercises the retry path against the default
      scripted fake transport; subsequent dispatchable
      candidates succeed on the first attempt).

- [ ] **`duplicate_suppressed` >= 1**, reflecting the synthetic
      duplicate candidate.

- [ ] **`suppressed_count` aggregates** UNKNOWN, DISAGREE, USDC,
      STALE, MISSING, malformed, and duplicate counts; it must
      be greater than zero for the default synthetic stream.

- [ ] **`heartbeat_count` >= 1.** The default heartbeat cadence
      is one heartbeat every 3 observed events; the default
      synthetic stream emits at least three heartbeats.

- [ ] **`stop_reason`** is a closed-set Stage 28.5 stop-reason
      token. `MAX_EVENTS` is the expected value for the default
      bounded smoke.

- [ ] **`final_health_status`** is `HEALTHY` or `DEGRADED`. A
      `FAILED` value indicates a ledger / artifact failure;
      inspect counters before re-running.

- [ ] **`output_dir_safe_label`** is the short safe basename of
      the operator-supplied output dir. The harness MUST NOT echo
      the absolute path on the smoke summary.

---

## D. Out-of-scope confirmations (Stage 28.7 must not have done)

The following items MUST remain absent at Stage 28.7 acceptance.
Confirm each:

- [ ] No real Discord send (`live_send_attempted == false`).
- [ ] No real provider connection (no Helius / Birdeye / RPC
      hostname appears in any artifact).
- [ ] No public router / subscriber router / paid tier router /
      live router.
- [ ] No Telegram or X / social module.
- [ ] No Stage 29 enforcement gate / `enforce_policy.py` /
      `enforcement_gate.py`.
- [ ] No automated trading / `auto_trade*.py` /
      `position_size*.py`.
- [ ] No wallet / private-key / signer logic, no position
      sizing, no trade execution.
- [ ] No dashboard / HTTP control server / daemon / systemd /
      watchdog / autorestart service.
- [ ] No persistent dedupe ledger committed to the repo; the
      Stage 28.2 ledger lives only under the operator-supplied
      `output_dir` for the smoke run.
- [ ] No second env-read site outside Stage 27's
      `live_secrets_readiness.py`.

---

## E. Boundary re-checks (post-smoke)

- [ ] **No tag was created during the smoke.** Re-run
      `git tag --list "stage-28*"` after the smoke and confirm
      the result is still empty.

- [ ] **No push occurred.** Re-run
      `git log origin/main..HEAD --oneline` and inspect the
      working tree; the smoke must not have triggered any push.

- [ ] **Git status after the smoke shows only known pre-existing
      untracked paths plus the temp output dir** (if the operator
      chose a path under the working tree). Re-run
      `git status --short`. No new untracked file inside
      `PHX2/stage28/` may have appeared as a side effect of the
      smoke.

- [ ] **The Stage 28.7 focused test suite passes.** Re-run
      `py -B -m pytest PHX2/tests/stage28 -q -p no:cacheprovider`
      and confirm the Stage 28.0 → 28.7 tests all pass.

- [ ] **The Stage 27 focused test suite still passes.** Re-run
      `py -B -m pytest PHX2/tests/stage27 -q -p no:cacheprovider`.

- [ ] **The Stage 25.7 + Stage 26.7 closure audits still pass.**
      Re-run
      `py -B -m pytest PHX2/tests/stage25/test_stage_25_7_closure_audit.py PHX2/tests/stage26/test_stage_26_7_closure_audit.py -q -p no:cacheprovider`.

---

## F. Sign-off

Once every box above is checked, the Stage 28.7 longer-session
offline smoke is considered ACCEPTED. The next gated work is the
**controlled live smoke** documented in
`STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md`, and it MUST NOT
begin without its own explicit per-event operator authorization
prompt.

Stage 28.7 does **not** authorize the controlled live smoke
itself. Stage 28.7 does **not** authorize a `stage-28-closed`
tag or a push. Stage 28.7 does **not** authorize any Stage 28
closure audit, any Stage 29 handoff doc, any Stage 28-wide
manifest, any Stage 29 enforcement surface, or any Stage 30+ X /
social / Telegram surface.

The Stage 28 closure audit + Stage 29 handoff are **Stage 28.8**
scope, performed only after Stage 28.7 is fully accepted with an
explicit operator authorization to begin Stage 28.8.
