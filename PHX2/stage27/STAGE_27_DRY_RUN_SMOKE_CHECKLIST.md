# PHX2 Stage 27.7a — Dry-Run Smoke Checklist

This checklist is the operator gate for running and accepting a
Stage 27.7a dry-run smoke. It pairs with
`STAGE_27_OPERATOR_RUNBOOK.md`. Stage 27.7a is **dry-run only**:
no Discord send, no real provider call, no live network, no Stage
29 enforcement.

If any item below fails, the smoke must be considered FAILED. Do
NOT proceed to Stage 27.7b until every item passes.

---

## A. Pre-smoke checks (repo state)

- [ ] **Git status shows only known pre-existing untracked paths.**
      Run `git status --short` before kicking off the smoke. The
      only entries permitted are the known pre-existing untracked
      paths (e.g. `PHX2/.stage_17_inputs/`,
      `PHX2/docs/stage_summaries/`, `ROADMAP.md`). Any other
      untracked file is unexpected; investigate before continuing.

- [ ] **No `stage-27` tag exists.** Run `git tag --list | grep
      stage-27` and confirm the result is empty. Stage 27 tag
      creation is an operator-only action; the implementation
      pass must not have created a tag.

- [ ] **No Discord sender module exists.** Run
      `git ls-files PHX2/stage27 | grep -i 'discord_sender'` and
      confirm the result is empty. Also confirm
      `PHX2/stage27/private_discord_sender.py` does not exist on
      disk. This file is reserved for Stage 27.7b only.

- [ ] **No live provider / API calls are enabled.** Inspect the
      smoke harness import graph:
      `python -c "import PHX2.stage27.dry_run_smoke_harness, sys;
      print(sorted(m for m in sys.modules if 'requests' in m or
      'httpx' in m or 'aiohttp' in m or 'urllib3' in m or
      'websockets' in m or 'grpc' in m or 'discord' in m or
      'telegram' in m))"`. The printed list MUST be empty.

- [ ] **Env-read boundary remains isolated to
      `live_secrets_readiness.py`.** Run
      `grep -nE "os\.environ|os\.getenv|os\.environb" PHX2/stage27`
      and confirm every hit is inside `live_secrets_readiness.py`.
      No env read is permitted in `dry_run_smoke_harness.py`,
      `stage27_7_manifest.py`, or anywhere else under
      `PHX2/stage27/`.

- [ ] **Dry-run output root is outside tracked production paths or
      is an injected temp directory.** The smoke harness refuses to
      run without an explicitly injected `output_root`. The test
      suite uses `pytest`'s tmp dir; an operator running the
      harness by hand must pass a path that is outside the tracked
      Stage 27 production tree (e.g. a freshly-created scratch
      directory under `/tmp` or the equivalent on this machine).

---

## B. Post-smoke checks (artifacts)

- [ ] **Smoke artifacts are present and redacted.** Every file in
      the output root should be a Stage 27.5 dry-run artifact
      (`ping_<id>_payload.json`, `ping_<id>_provenance.json`) or
      the optional Stage 27.6 run-summary artifact
      (`run_<run_id>_summary.json`). Open each file and confirm
      every value is a closed-set token, a canonical decimal-text
      number, or a short safe-to-display string.

- [ ] **No webhook / API / RPC secret appears in any artifact.**
      Grep each artifact:
      `grep -rE "h""ttps?://|w""ss?://|api[_-]?key|webhook|bearer
      |authorization" <output_root>`. The grep MUST return
      nothing.

- [ ] **No raw payload blob appears in any artifact.** Grep for
      conspicuous payload field substrings:
      `grep -rE "raw_payload|payload_blob|raw_response|response_body
      |encoded_payload" <output_root>`. The grep MUST return
      nothing. Stage 27.5 only emits the safe-to-display canonical
      fields.

- [ ] **UNKNOWN and DISAGREE pairs are suppressed from live-ready
      status.** Inspect each ping payload. Every UNKNOWN payload
      MUST carry `render_status="RENDERED_SUPPRESSED"`,
      `pair_live_policy="LIVE_SUPPRESS_UNKNOWN"`, and
      `calibration_lane="UNKNOWN_PAIR_OBSERVE_ONLY"`. Every
      DISAGREE payload MUST carry
      `render_status="RENDERED_SUPPRESSED"`,
      `pair_live_policy="LIVE_SUPPRESS_DISAGREE"`, and
      `calibration_lane="DISAGREE_PAIR_OBSERVE_ONLY"`.

- [ ] **USDC pairs are observe-only.** Every USDC payload MUST
      carry `render_status="RENDERED_OBSERVE_ONLY"`,
      `quote_asset="USDC"`, and
      `calibration_lane="USDC_OBSERVE_ONLY"`. USDC MUST NOT carry
      `calibration_lane="EXISTING_SOL_LANE"`.

- [ ] **SOL pairs are on the existing SOL calibration lane.**
      Every SOL payload MUST carry `quote_asset="SOL"` and
      `calibration_lane="EXISTING_SOL_LANE"`.

- [ ] **No BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE /
      POSITION-SIZE / AUTO-TRADE / ENFORCEMENT language appears in
      any artifact, doc, or summary.** Grep:
      `grep -rEi "(buy|sell|approved|gate_decision|block_trade
      |execute_trade|position_size|auto_trade|enforcement_gate)"
      <output_root>`. The grep MUST return nothing. Stage 27 is
      private dry-run pings, not a trading verdict surface.

- [ ] **No Discord transport call occurred.** Inspect the smoke
      summary: `mode` MUST be `DRY_RUN` (never anything else) and
      `artifacts_written` reflects only Stage 27.5 dry-run files.
      The harness never opens a network connection; reconfirm
      `netstat -an` shows no Stage 27-attributable network
      activity during the smoke window.

---

## C. Smoke summary counters

- [ ] **`mode == "DRY_RUN"`.** Any other value means LIVE was
      requested or the smoke was misconfigured.
- [ ] **`events_seen` matches the input event count** for the
      default smoke event set (or the operator-supplied set).
- [ ] **`pings_rendered` counts only SOL + USDC `RENDERED_DRY_RUN`
      candidates.**
- [ ] **`unknown_suppressed`, `disagree_suppressed`,
      `usdc_observe_only_count`, `duplicates_skipped`,
      `unsupported_skipped`, `errors`** all line up with the
      input event distribution.
- [ ] **`schema_version` is the Stage 27.7a smoke summary
      version** (`stage27_v0_dry_run_smoke_summary`).
- [ ] **`output_root` is the absolute path of the injected temp
      directory**, not a hard-coded production directory.

---

## D. Boundary re-checks (post-smoke)

- [ ] **No tag was created during the smoke.** Re-run
      `git tag --list | grep stage-27` after the smoke and confirm
      the result is still empty.
- [ ] **No push occurred.** Re-run `git log origin/main..HEAD --
      oneline` and inspect the working tree; the smoke must not
      have triggered any push.
- [ ] **Git status after the smoke shows only known pre-existing
      untracked paths plus the temp output root** (if the operator
      chose a path under the working tree). Re-run
      `git status --short`. No new untracked file inside
      `PHX2/stage27/` may have appeared as a side effect of the
      smoke.
- [ ] **The Stage 27.7a focused test suite passes.** Re-run
      `py -m pytest PHX2/tests/stage27 -q` and confirm the
      Stage 27.0 → 27.7a tests all pass.
- [ ] **The Stage 25.7 + Stage 26.7 closure audits still pass.**
      Re-run
      `py -m pytest PHX2/tests/stage25/test_stage_25_7_closure_audit.py PHX2/tests/stage26/test_stage_26_7_closure_audit.py -q`.

---

## E. Out-of-scope confirmations

The following items MUST remain absent at Stage 27.7a closure.
Confirm each:

- [ ] No Discord sender / Discord client / webhook poster.
- [ ] No public router / subscriber router / live router.
- [ ] No Telegram or X / social module.
- [ ] No Stage 26 candidate-policy enforcement.
- [ ] No Stage 29 enforcement gate.
- [ ] No persistent dedupe ledger (the run-local dedupe from
      Stage 27.6 is in-memory only).
- [ ] No database write / SQLAlchemy / SQLite import.
- [ ] No real `.env` value was read at smoke time; the env-read
      boundary remains exactly `live_secrets_readiness.py`.

---

## F. Sign-off

Once every box above is checked, the Stage 27.7a dry-run smoke
is considered ACCEPTED. The next gated substage is **Stage 27.7b**
(the controlled live smoke), and it MUST NOT begin without its
own explicit per-substage operator authorization prompt.

Stage 27.7a does **not** authorize Stage 27.7b. Stage 27.7a does
**not** authorize a tag or a push. Stage 27.7a does **not**
authorize any Stage 28 hardening surface or Stage 29 enforcement
surface.
