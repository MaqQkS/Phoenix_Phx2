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

---

## G. Stage 27.7b controlled private Discord live smoke

Stage 27.7b ships the first controlled private operator-only
Discord smoke. The smoke runs ONLY when every box below is
satisfied. If any box fails, abort — there is no second pass.

- [ ] **The operator authorization is explicit.** The dispatch
      call must receive `operator_live_request=True`,
      `smoke_dispatch_request=True`, and
      `dispatch_mode="LIVE_SEND"`. A missing or false flag is a
      `REFUSED_UNAUTHORIZED_MODE` / `REFUSED_NOT_LIVE` refusal.
- [ ] **Stage 27.1 LIVE composite resolves `LIVE_ALLOWED`.** The
      Stage 27.1 readiness report MUST show
      `all_required_live_present is True` and the resolved
      authority token MUST be `LIVE_ALLOWED`. The dispatch
      cross-checks the token against
      `LIVE_MODE_AUTHORITY_LIVE_ALLOWED`; any other value fails
      closed with `REFUSED_NOT_LIVE`.
- [ ] **Exactly ONE payload is being dispatched.** The
      `payloads` sequence length MUST be exactly `1`. The
      dispatch refuses any other length with
      `REFUSED_MULTIPLE_PAYLOADS`. The Stage 27.7b
      `STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH` constant is locked
      to `1`.
- [ ] **The webhook identity is a safe-to-display label.** The
      `webhook_identity` argument MUST be a short label (e.g.
      `PRIVATE_OPERATOR_WEBHOOK`); it MUST NOT contain the URL.
      The Stage 27.7b dispatch result echoes only this label,
      never the URL.
- [ ] **The webhook URL was read through
      `live_secrets_readiness.py` only.** Stage 27.7b adds no
      second env-read site. Confirm:
      `grep -nE "os\.environ|os\.getenv|os\.environb" PHX2/stage27`
      reports only hits inside `live_secrets_readiness.py`.
- [ ] **The injected transport is operator-audited.** Tests use
      `Stage27_7bFakeDiscordTransport`. The
      `Stage27_7bRealHttpDiscordTransport` placeholder raises
      `NotImplementedError`; an operator-authored live transport
      must be injected explicitly.
- [ ] **The pair-aware verdict allows live send.** UNKNOWN and
      DISAGREE pairs ALWAYS refuse with
      `REFUSED_SUPPRESSED_PAIR`. USDC pairs refuse unless the
      Stage 27.5 payload carries
      `render_status="RENDERED_OBSERVE_ONLY"`. SOL pairs refuse
      unless the Stage 27.5 payload carries
      `calibration_lane="EXISTING_SOL_LANE"`. The forbidden
      promotion of USDC / UNKNOWN / DISAGREE into the existing-
      SOL lane remains blocked.

---

## H. Stage 27.7b post-smoke verification

After the controlled smoke:

- [ ] **`dispatch_status == "SENT"`** for the happy path. Any
      other status is a refusal / transport error — inspect the
      closed-set `dispatch_reason` token before retrying.
- [ ] **`transport_status_code` is the expected success code**
      (typically `200` for a Discord webhook). A non-success
      status returns `TRANSPORT_ERROR` /
      `TRANSPORT_NON_SUCCESS`.
- [ ] **The injected transport recorded exactly ONE call.** For
      the fake transport,
      `Stage27_7bFakeDiscordTransport.call_count == 1`. For an
      operator-audited live transport, confirm the operator's
      audit log shows exactly one outbound webhook call.
- [ ] **The webhook URL does NOT appear in the dispatch result
      `repr()` / `str()`.** Confirm by inspecting
      `repr(dispatch_result)` — only the safe webhook identity
      label and closed-set tokens may appear.
- [ ] **The webhook URL does NOT appear in any artifact.** The
      Stage 27.5 dry-run artifacts (ping payload + provenance)
      never carried the URL. The Stage 27.7b dispatch result is
      not persisted to disk by the sender; if the operator
      writes it to an audit log, the operator MUST verify the
      log does not include the URL.
- [ ] **No raw provider payload blob, no API canary, and no
      RPC URL appears in any artifact or dispatch result.**
      Grep:
      `grep -rE "raw_payload|payload_blob|raw_response|response_body|api[_-]?key|bearer|authorization" <output_root>`.
      The grep MUST return nothing.
- [ ] **The dispatch result `mode` is `LIVE_SEND` only for the
      one successful smoke.** Every refusal / abort path keeps
      `dispatch_mode` reflecting the caller's request; tests
      assert each closed-set status pairs with the matching
      `dispatch_reason` token.

---

## I. Stage 27.7b out-of-scope confirmations

The following items MUST remain absent at Stage 27.7b closure:

- [ ] No public router / subscriber router / paid tier router /
      live router.
- [ ] No Telegram or X / social module.
- [ ] No broad Discord community distribution / role-gated
      community routing / Discord slash commands / Discord bot
      command tree.
- [ ] No Stage 29 enforcement gate / `enforce_policy.py` /
      `enforcement_gate.py`.
- [ ] No automated trading / `auto_trade*.py` /
      `position_size*.py`.
- [ ] No persistent dedupe ledger / database / scheduler /
      queue / daemon / background worker.
- [ ] No second env-read site outside
      `live_secrets_readiness.py`.

---

## J. Stage 27.7b is not Stage 28 hardening

Stage 27.7b is the controlled FIRST smoke, not the reliability
pass. Crash recovery, retries / backoff, health checks, restart-
safe dedupe, richer provider failure handling, monitoring, and
longer-running reliability belong to Stage 28. Stage 27.7b ships
none of those surfaces.

---

## K. Stage 27.7b is not Stage 29 enforcement

Stage 29 is where approved enforcement and live gating live.
Stage 26 candidate policies remain review-only at Stage 27.7b;
they become enforcement only through Stage 29's explicit
authorization gate. Stage 27.7b ships no enforcement surface and
NO BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE / POSITION-
SIZE / AUTO-TRADE language ever appears in a Stage 27.7b
dispatch result, in any artifact, or in any operator surface.
