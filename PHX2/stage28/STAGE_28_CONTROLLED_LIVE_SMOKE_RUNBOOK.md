# PHX2 Stage 28.7 — Controlled Live Smoke Runbook

This runbook documents how a Stage 28.7-accepted operator MAY
perform a **single tightly controlled private Discord smoke**
against the operator's private webhook, using the existing
Stage 27.7b private Discord sender and the Stage 28.6 bounded
private session runner. The controlled live smoke is **not**
performed by Stage 28.7 production code and is **not** invoked
by the Stage 28.7 test suite. It is a manual operator procedure
documented here so it can be re-performed safely later under
explicit authorization.

> **Stage 28.7 production code is offline-only.** The longer-
> session smoke harness shipped in
> `longer_session_smoke_harness.py` opens no network connection,
> never reads the process environment, never invokes a real
> Discord webhook, never connects to a real provider, and never
> performs a real live send. The fields `live_send_attempted` and
> `live_send_count` on the Stage 28.7 smoke summary are always
> `false` / `0`.

If any precondition or gate below fails, **abort**. Do not retry
the smoke until the failing item is fully understood and fixed.

**Stage 28.7 is NOT Stage 28 closure.** This runbook must not
create the `stage-28-closed` tag, must not ship a Stage 28
closure audit doc, must not ship a Stage 29 handoff doc, and
must not ship a Stage 28-wide manifest. Those are Stage 28.8
scope. Stage 28.7 does not authorize Stage 28 closure.

---

## A. Authorization gates (operator must satisfy every gate)

The controlled live smoke runs ONLY when EVERY one of the
following gates passes:

- [ ] **Explicit operator authorization.** The operator has typed
      an explicit per-smoke authorization phrase before kicking
      off the procedure, e.g. "I authorize one Stage 28.7
      controlled private live smoke against my private operator
      webhook." A written authorization MUST exist in the
      operator's audit log.

- [ ] **Live request flags are explicit.** Any wrapper script or
      scratch helper invoking the Stage 27.7b dispatch MUST pass
      `operator_live_request=True`, `smoke_dispatch_request=True`,
      and `dispatch_mode="LIVE_SEND"`. A missing or false flag is
      a `REFUSED_UNAUTHORIZED_MODE` / `REFUSED_NOT_LIVE` refusal.

- [ ] **Private operator webhook only.** The dispatch MUST target
      the operator's private webhook. No public, subscriber,
      paid-tier, channel-routed, or broad-distribution webhook is
      permitted at Stage 28.7. The `webhook_identity` argument is
      a short safe-to-display label (e.g.
      `PRIVATE_OPERATOR_WEBHOOK`); the raw URL is read through
      Stage 27's `live_secrets_readiness.py` only.

- [ ] **Exactly one live send.** The smoke dispatches exactly
      ONE Stage 27.5 ping payload. The `max_live_sends` budget
      is locked to `1`. The Stage 27.7b dispatch refuses any
      `payloads` length other than `1` with
      `REFUSED_MULTIPLE_PAYLOADS`.

- [ ] **Out-of-repo artifact directory.** The smoke writes
      artifacts into a freshly-created scratch directory OUTSIDE
      the tracked Stage 28 production tree (e.g. a `/tmp/`-class
      directory or the equivalent on this machine). The
      `output_dir` argument MUST be supplied explicitly; the
      harness never defaults to a path under the production tree.

- [ ] **Stage 28.7 offline smoke already passed.** The Stage
      28.7 longer-session offline smoke must have been performed
      and accepted per
      `STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md` before the
      controlled live smoke is even attempted.

- [ ] **Stage 27.1 readiness resolves `LIVE_ALLOWED`.** The
      Stage 27.1 readiness report MUST show
      `all_required_live_present is True` and the resolved
      authority token MUST be `LIVE_ALLOWED`. Stage 27.7b cross-
      checks the token against `LIVE_MODE_AUTHORITY_LIVE_ALLOWED`;
      any other value fails closed with `REFUSED_NOT_LIVE`.

- [ ] **The injected transport is operator-audited.** Tests use
      `Stage27_7bFakeDiscordTransport`. The Stage 28.7 controlled
      live smoke MUST inject the operator's audited live
      transport (no Stage 28.7 production code does this). The
      operator MUST own the audit log of the transport.

---

## B. Pre-smoke environment verification

- [ ] **Working tree is clean.** Run `git status --short` and
      confirm only known pre-existing untracked paths show.

- [ ] **No stage-28 tag exists.** Run
      `git tag --list "stage-28*"` and confirm the result is
      empty. Stage 28 tag creation belongs to Stage 28.8 closure
      with separate operator authorization.

- [ ] **No Stage 28 closure / Stage 29 handoff doc exists.** Run
      `git ls-files PHX2/stage28 | grep -E "STAGE_28_CLOSURE_AUDIT|STAGE_29_HANDOFF|stage28_manifest\\.py"`
      and confirm the result is empty. Those are Stage 28.8.

- [ ] **Pre-flight redaction scan of the offline-smoke output.**
      Re-run `scan_stage28_7_artifacts_for_redaction(...)` over
      the Stage 28.7 offline smoke's `output_dir` and confirm
      `redaction_status == "SAFE"`.

- [ ] **No second env-read site.** Confirm
      `grep -nE "os\\.environ|os\\.getenv|os\\.environb" PHX2/stage28`
      returns nothing. The Stage 27.1 `live_secrets_readiness.py`
      remains the only env-read site for any webhook URL.

---

## C. Performing the controlled live smoke

The Stage 28.7 production harness is offline-only and does NOT
expose a live-send callable. To perform the controlled live
smoke, the operator authors a small scratch script OUTSIDE the
tracked tree that:

1. Reads the webhook URL through Stage 27's
   `live_secrets_readiness.py` only (no second env-read site).
2. Constructs the operator's audited live transport implementing
   `Stage28_6PrivateTransport` (the `send_one_audited_post` method
   that returns a `Stage28_4TransportResult`). Stage 28.7
   production code provides no live transport implementation;
   the operator owns the audit log.
3. Builds exactly ONE Stage 28.6 candidate via
   `build_candidate_event(...)` using a safe synthetic mint /
   pair / payload. No subscriber, channel, public-routing,
   paid-tier, audience, route_id, approval, enforcement, trade,
   wallet, or signer field appears anywhere in the candidate.
4. Constructs the Stage 28.6 runner via
   `Stage28_6BoundedPrivateSessionRunner(...)` with
   `max_dispatches=1`, `max_events=1`, and an injected
   `Stage28_6StopSignal` ready to be triggered after the one
   send.
5. Runs the smoke once. Captures the in-memory
   `Stage28_6RunSummary` and writes the Stage 28.7 smoke summary
   + redaction scan via
   `write_stage28_7_smoke_summary(...)` /
   `write_stage28_7_redaction_scan(...)`.
6. Exits the scratch process. The Stage 28.7 production harness
   is NOT invoked here.

> The scratch script lives OUTSIDE the tracked Stage 28
> production tree. It is never committed to the repository. The
> operator removes the script after the controlled smoke.

---

## D. Post-smoke verification

- [ ] **`dispatch_status == "SENT"`.** For the happy path the
      Stage 27.7b dispatch result reports `SENT`. Any other
      status is a refusal / transport error; inspect the
      closed-set `dispatch_reason` token before retrying.

- [ ] **`transport_status_code` is the expected success code**
      (typically `200` / `204` for a Discord webhook). A
      non-success status returns `TRANSPORT_ERROR` /
      `TRANSPORT_NON_SUCCESS` and counts as a failed smoke.

- [ ] **The injected transport recorded exactly ONE call.** The
      operator's audited live transport audit log MUST show
      exactly one outbound webhook call. A larger count is a
      bug; investigate before retrying.

- [ ] **The webhook URL does NOT appear in any artifact.** Open
      every file under the smoke `output_dir`. Grep:
      `grep -rE "h""ttps?://|w""ss?://|/webhooks/|discord""\\.com|discord""app\\.com" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No raw secret / auth header appears in any artifact.**
      Grep:
      `grep -rEi "(api[_-]?key|bearer|authorization|private_key|wallet_seed|signer_address)" <output_dir>`.
      The grep MUST return nothing.

- [ ] **No raw Discord response body appears in any artifact.**
      Grep:
      `grep -rE "raw_response|response_body|raw_payload|payload_blob" <output_dir>`.
      The grep MUST return nothing.

- [ ] **Stage 28.7 redaction scan passes.** Re-run
      `scan_stage28_7_artifacts_for_redaction(...)` over the
      live-smoke output_dir and confirm `redaction_status ==
      "SAFE"`.

- [ ] **Smoke summary records the live send.** The operator's
      scratch helper SHOULD write a smoke-summary JSON with
      `live_send_attempted == true` and `live_send_count == 1`.
      Stage 28.7 production code never sets those flags; only
      the operator's manual scratch helper may.

- [ ] **Final report.** The operator records the following in
      the controlled-smoke audit log:
      - `run_id`, `session_id`, `smoke_id`,
      - `send count` (must be `1`),
      - `artifact paths` (relative to the out-of-repo output
        directory),
      - `redaction_status` (must be `SAFE`),
      - Stage 28 and Stage 27 focused test counts before and
        after the smoke.

---

## E. Out-of-scope confirmations (controlled smoke must not have done)

The following items MUST remain absent at the controlled live
smoke. Confirm each:

- [ ] No public router / subscriber router / paid tier router /
      live router was invoked.
- [ ] No Telegram / X / social transport was invoked.
- [ ] No broad Discord community distribution / role-gated
      community routing / Discord slash command / Discord bot
      command tree was used.
- [ ] No Stage 29 enforcement gate / `enforce_policy.py` /
      `enforcement_gate.py` was used.
- [ ] No automated trading / `auto_trade*.py` /
      `position_size*.py` / wallet / signer logic was used.
- [ ] No persistent dedupe ledger / database / scheduler / queue
      / daemon / background worker was started.
- [ ] No second env-read site outside Stage 27's
      `live_secrets_readiness.py` was added or used.
- [ ] No `stage-28-closed` tag was created. No Stage 28 closure
      audit doc was created. No Stage 29 handoff doc was
      created. No Stage 28-wide manifest was created.

---

## F. Stage 28.7 is not Stage 28.8 closure

Stage 28.7 is the proof stage. Stage 28.7 does NOT close Stage
28 and does NOT tag `stage-28-closed`. The Stage 28 closure audit
+ Stage 29 handoff are Stage 28.8 scope. Stage 28.8 begins only
with a separate explicit operator authorization, performs the
closure audit, ships the Stage 28 closure audit doc + Stage 29
handoff doc + Stage 28-wide manifest, and creates the
`stage-28-closed` tag.

## G. Stage 28.7 is not Stage 29 enforcement

Stage 29 is where approved enforcement and live gating live.
Stage 26 candidate policies remain review-only at Stage 28.7;
they become enforcement only through Stage 29's explicit
authorization gate. Stage 28.7 ships no enforcement surface and
NO BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE / POSITION-
SIZE / AUTO-TRADE / ENFORCEMENT_RESULT language ever appears in
any Stage 28.7 artifact, dispatch result, or operator surface.

## H. Stage 28.7 is not Stage 30+ X / social

X / social distribution belongs to Stage 30+. Stage 28.7 ships
no Telegram, no X / Twitter, no social sidecar, no tweet
ranking, no social scoring, and no broad Discord community
distribution. The controlled live smoke targets exactly ONE
private operator webhook.
