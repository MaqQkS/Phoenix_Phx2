# Stage 22 Operator Runbook -- First Private Ping

Operator-facing handoff doc for Stage 22.5. This describes how
to run the bounded private ingest path locally with real
provider keys against a private recipient.

This document is the runbook companion to
`STAGE_22_CLOSURE_AUDIT.md`. The audit doc records WHAT Stage
22 is and HOW its boundaries are enforced; this doc records
WHAT THE OPERATOR DOES to drive a first private ping safely.

> **Do not paste any real key, recipient id, or URL into an AI
> chat (Claude, Codex, ChatGPT, or any other model surface).**
> Do not commit any such value, ever. Do not put any such
> value in this runbook, in any other doc, in ROADMAP.md, in
> CLAUDE.md, in tests, or in any tracked source file. Sample
> scratch scripts must live outside the repository, in a path
> the operator owns.

## 1. Stage 22 purpose

Stage 22 hardens the ingest path so it can be driven once,
locally, against a single provider with a single private
recipient, without leaking secrets and without behaving like a
production service. Every operation is bounded: the runner
fetches at most one provider attempt, processes at most a small
caller-supplied number of events, and dispatches at most a
small caller-supplied number of times.

## 2. What Stage 22 CAN do now

  * Bounded one-shot private ingest via
    `PHX2.stage22.bounded_live_runner.run_bounded_private_ingest`.
  * Provider fetch wrapped by the Stage 21 Helius adapter,
    composed through
    `PHX2.stage22.live_composition.build_live_fetch_outcome_fn`.
  * Per-event decode isolation: a single malformed event does
    not abort the surrounding batch.
  * Raw capture: every received event is appended to a
    caller-supplied capture writer; the in-memory writer and
    the JSONL writer both satisfy the same Protocol.
  * Dedupe: a JSONL or in-memory ledger records seen and
    dispatched state per ingest key.
  * Private Discord ping: a sanitized short body is sent via
    the Stage 21.3C Discord private transport.

## 3. What Stage 22 CANNOT do yet

These are deferred. The operator runbook MUST NOT instruct any
of them, and Stage 22 production code MUST NOT begin to
implement any of them.

  * No filters, no scoring, no eligibility gating, no Ante /
    holder / wallet checks.
  * No ATH measurement, no Birdeye correctness, no price
    enrichment, no migration measurement.
  * No fee execution, no Jito, no Axiom, no global fee model.
  * No X / social ingest, no X / social routing.
  * No public Discord routing, no subscriber routing, no paid
    routing of any kind.
  * No Telegram of any kind.
  * No long-running daemon, scheduler, orchestrator, run-loop,
    or worker.
  * No retry execution layer (the retry decision token
    vocabulary exists in 22.1 but no executor is shipped).
  * No production monetized service. The bounded runner is a
    one-shot smoke path only.

## 4. Local secret setup

### 4.1 Key policy (READ FIRST)

  1. Do NOT paste any real provider key, webhook URL, recipient
     id, bearer token, or private key into any AI chat session
     (Claude, Codex, ChatGPT, or any other). The cost of a
     single accidental paste is unbounded.
  2. Do NOT commit any of those values to git. Do NOT add them
     to any doc, ROADMAP entry, CLAUDE.md file, test fixture,
     or production module.
  3. Do NOT email, Slack, or otherwise share the values with
     anyone the recipient was not configured for.
  4. Treat the private Discord recipient id as a secret too.
     The bounded runner reaches it via the Stage 21.3C
     transport's recipient field; the value never appears in
     any Stage 22 production source.

### 4.2 PowerShell session env var pattern (recommended)

The simplest safe pattern: set the env vars in the operator's
own PowerShell session, run the scratch script in the same
session, then close the session. Nothing touches disk.

Before the first run, the operator MUST inspect the actual
Stage 21 surfaces to confirm the exact env var key names. The
runbook intentionally avoids reproducing the values here so a
drift in Stage 21 does not silently invalidate this doc.

  * `PHX2/stage21/constants.py` -- defines the base env var
    NAMES for provider / API key / RPC URL / Discord webhook
    configuration (for example `PHX2_STAGE21_PROVIDER_API_KEY`,
    `PHX2_STAGE21_PROVIDER_RPC_URL`,
    `PHX2_STAGE21_DISCORD_WEBHOOK_URL` -- the canonical names
    are whatever is declared in `constants.py`, not whatever
    appears in this runbook).
  * `PHX2/stage21/config.py` -- the SINGLE Stage 21 entry
    point that actually reads `os.environ` and projects it
    onto a `Stage21Config`. Every other Stage 21 module
    receives the result.
  * `PHX2/stage21/live_secrets_boundary.py` -- defines the
    LIVE-READINESS OVERLAY env var names (smoke-mode flag,
    provider-id pin, safe-for-live-dispatch flag, live-safety
    acknowledgement). These overlay names sit ON TOP of the
    base config; this file is NOT the source of truth for
    the provider key / RPC / webhook names. Conflating the
    two surfaces is a documented failure mode and the reason
    this section reads from three files, not one.
  * Discord recipient id (`PHX2_DISCORD_PRIVATE_RECIPIENT`
    in the illustrative snippet below) is a `scratch-script local`
    convenience name. There is no Stage 21 or Stage 22 config
    surface that formalises a recipient env var today; the
    scratch script consumes whatever name the operator chooses.
    If a future Stage 21 / Stage 22 change introduces a formal
    recipient config surface, update this section.

Example shape (illustrative names; the canonical names live
in the Stage 21 surfaces listed above -- copy them from
there, not from this snippet). Replace the placeholder
values; do not commit this snippet anywhere with real values
inlined.

```powershell
# In a NEW PowerShell window, before running the scratch script.
# The four names below are illustrative; copy the canonical
# names from PHX2/stage21/constants.py (base config) and
# PHX2/stage21/live_secrets_boundary.py (live-readiness
# overlay) before pasting real values.
$env:PHX2_STAGE21_PROVIDER_API_KEY     = '<paste-your-provider-api-key-here>'
$env:PHX2_STAGE21_PROVIDER_RPC_URL     = '<paste-your-provider-rpc-endpoint-here>'
$env:PHX2_STAGE21_DISCORD_WEBHOOK_URL  = '<paste-your-private-webhook-here>'
$env:PHX2_DISCORD_PRIVATE_RECIPIENT    = '<paste-your-private-recipient-id-here>'
# After the run, close this PowerShell window. The env vars
# disappear with the session; nothing is persisted to disk.
```

The live-readiness overlay env vars
(`PHX2_STAGE21_LIVE_SMOKE_MODE`,
`PHX2_STAGE21_PROVIDER_ID`,
`PHX2_STAGE21_SAFE_FOR_LIVE_DISPATCH`,
`PHX2_STAGE21_LIVE_SAFETY_ACKNOWLEDGEMENT` -- canonical names
in `PHX2/stage21/live_secrets_boundary.py`) gate whether the
readiness check returns `True`; they have to be set in the
same PowerShell session alongside the base config vars.
Inspect both files before the first run.

### 4.3 Optional `.env.local` pattern (only if ignored)

If a persistent local env file is required, gate it on a
`git check-ignore` check first:

```powershell
# Confirm the .env.local pattern is gitignored BEFORE creating
# the file. If this command prints nothing, the file is NOT
# ignored and the operator MUST stop and update .gitignore
# before continuing.
git check-ignore -v PHX2/.env.local
```

The repository's `.gitignore` already lists `.env` and
`.env.*`, so `PHX2/.env.local` is ignored by the
`.env.*` pattern at the repository root. Do NOT commit a
`.env.local` file. Do NOT name an env file in a way that
escapes the existing ignore rules (e.g. do not call it
`env.local`, `env_local`, or `localenv`). Re-run
`git check-ignore -v` after any rename.

### 4.4 What MUST NOT be done

  * Do NOT pass real key values as CLI arguments (process
    listings preserve them).
  * Do NOT write real key values into any file inside the
    repository, including `.env.local`, scratch scripts under
    the repo tree, test fixtures, or docs.
  * Do NOT echo real key values to the console after the run.
  * Do NOT use any global system env var for the keys; scope
    them to the PowerShell session that will run the script.

## 5. Pre-run safety checklist

Run all of these BEFORE the scratch script:

  1. `git status --short` -- the only untracked entries should
     be the three pre-existing paths
     (`PHX2/.stage_17_inputs/`, `PHX2/docs/`, `ROADMAP.md`)
     and any new Stage 22.6 doc / test files. If a `.env`-shape
     or key-bearing file appears, STOP.
  2. `git diff` -- empty, or only the Stage 22.6 doc / test
     edits. No tracked file should contain a real key.
  3. `git diff --cached` -- empty. No real key should ever
     enter the index.
  4. `git check-ignore -v PHX2/.env.local` (if using the
     `.env.local` pattern) -- confirms the file is ignored.
  5. The intended Discord recipient is the private channel the
     operator owns, NOT a public channel and NOT a subscriber
     channel.
  6. The intended Helius endpoint is the operator's own key.

If any of the six fails, STOP. Do not run.

## 6. One-shot live run pattern

Save the script OUTSIDE the repository (for example under the
operator's `Documents` tree). Do NOT commit it. Do NOT name it
in a way that the repository might accidentally pick up.

The script's responsibilities are:

  * snapshot `os.environ` into a `Mapping[str, str]`;
  * construct a Helius adapter using only injected values;
  * construct a Discord private transport using only injected
    values;
  * wire them through
    `PHX2.stage22.live_composition` builders;
  * call `run_bounded_private_ingest` exactly once with
    `max_provider_attempts=1`, a small `max_events`, a small
    `max_dispatches`, and `stop_after_first_dispatch=True`;
  * write the raw-capture and dedupe artifacts under an
    operator-owned local path that is NOT inside the
    repository.

Illustrative shape (placeholders only -- do NOT inline real
values; do NOT save this file inside the repository):

```python
# scratch_first_private_ping.py
# Lives OUTSIDE the repository. Do NOT commit. Do NOT paste
# real key values into this file; the script reads them from
# the current PowerShell session env vars.

import os
from pathlib import Path

from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest
from PHX2.stage22.dedupe_ledger import JsonlDedupeLedger      # if shipped
from PHX2.stage22.raw_capture import JsonlRawCaptureWriter    # if shipped
from PHX2.stage22.live_composition import (
    Stage22DiscordPrivateTransportAdapter,
    build_live_fetch_outcome_fn,
    build_live_readiness_check_fn,
    classify_stage21_decode_exception,
    get_stage21_decode_fn,
)
# The Stage 21 adapter / transport constructors are the seam
# the scratch script wires up; consult their docstrings for
# the exact argument shape.

env_snapshot = dict(os.environ)

# Local, ignored, OUTSIDE the repo:
out_dir = Path.home() / "phx2_scratch_run"
out_dir.mkdir(parents=True, exist_ok=True)

readiness_check_fn = build_live_readiness_check_fn(env=env_snapshot)

# adapter = HeliusProviderAdapter(...)   # from PHX2.stage21
fetch_outcome_fn = build_live_fetch_outcome_fn(
    adapter=adapter,
    max_results=5,
)

# transport = DiscordPrivateTransport(...)  # from PHX2.stage21
private_transport = Stage22DiscordPrivateTransportAdapter(
    transport=transport,
    recipient=env_snapshot["PHX2_DISCORD_PRIVATE_RECIPIENT"],
)

raw_capture_writer = JsonlRawCaptureWriter(
    path=out_dir / "raw_capture.jsonl",
)
dedupe_ledger = JsonlDedupeLedger(
    path=out_dir / "dedupe.jsonl",
)

result = run_bounded_private_ingest(
    provider_id="helius",
    chain="solana",
    observed_at_utc="<rfc3339 timestamp>",
    received_at_utc="<rfc3339 timestamp>",
    failed_at_utc="<rfc3339 timestamp>",
    readiness_check_fn=readiness_check_fn,
    fetch_outcome_fn=fetch_outcome_fn,
    decode_event_fn=get_stage21_decode_fn(),
    classify_decode_error_fn=classify_stage21_decode_exception,
    raw_capture_writer=raw_capture_writer,
    dedupe_ledger=dedupe_ledger,
    private_transport=private_transport,
    max_provider_attempts=1,
    max_events=3,
    max_dispatches=1,
    stop_after_first_dispatch=True,
)

print(result.outcome, result.events_received, result.events_dispatched)
```

Notes:

  * `max_provider_attempts` MUST be `1`; the bounded runner
    raises if any other value is passed.
  * `max_events` and `max_dispatches` SHOULD be small (1 - 5)
    for the first smoke run.
  * `stop_after_first_dispatch=True` ends the per-envelope loop
    on the first successful dispatch so the smoke run cannot
    accidentally fan out.
  * The exact `JsonlDedupeLedger` / `JsonlRawCaptureWriter`
    constructor signatures live in the corresponding 22.2 / 22.3
    modules; consult them at run time. Both constructors take
    `path: pathlib.Path` (NOT `str`); passing a string raises a
    Stage 22 contract error. The example above passes
    `out_dir / "raw_capture.jsonl"` directly so the `Path /`
    operator yields a `Path`, not a string.
  * `print(result.outcome, ...)` should print only short
    closed-set tokens and small integers; no key material
    should appear in stdout.

## 7. Expected success

A first-private-ping success looks like all of the following:

  * `run_bounded_private_ingest` returns a
    `Stage22IngestResult` with `outcome == "ok"`.
  * `events_received >= 1`, `events_dispatched == 1`,
    `events_transport_refused == 0`.
  * The private Discord recipient receives ONE short message
    starting with the locked banner
    `[Stage 22.5 private-preview ingest]` and containing only
    `provider=`, `chain=`, `event_type=`, `mint=`, `slot=`,
    `event_id=` fields.
  * A raw-capture record exists in the JSONL artifact under
    the operator's local out-directory.
  * A dedupe record exists in the JSONL artifact under the
    operator's local out-directory.
  * `print(result.outcome, ...)` shows only short tokens and
    small integers; no key material in stdout.

## 8. Expected common failure outcomes

The runner returns one of these `outcome` tokens (closed set;
see `INGEST_RUNNER_OUTCOMES` in `PHX2/stage22/constants.py`):

  * `readiness_not_ready` -- the Stage 21.3A readiness gate
    rejected the env snapshot. Fix the env vars and retry.
  * `provider_failed` -- the Helius adapter raised. The
    `last_failure_label` is one of the closed Stage 22
    `PROVIDER_FAILURE_LABELS` tokens; never a raw exception
    message.
  * `provider_returned_zero` -- the adapter returned an empty
    response tuple. Typically benign on a quiet window.
  * `all_malformed` -- every received event failed decode.
    Each failure was captured in the raw-capture writer with
    a sanitized reason token from `MALFORMED_EVENT_REASONS`.
  * `all_duplicates` -- every received event was already
    marked dispatched in the ledger. Expected on a re-run with
    no new activity.
  * `transport_refused` -- the Discord transport refused every
    dispatch. The refusal token is one of the closed Stage
    21.3C rejection-reason tokens.
  * Other surfaces that may appear as Python exceptions (the
    runner does NOT swallow these):
      * `Stage22RunnerError` -- argument-validation contract
        violation in the scratch script. Fix the argument
        shape; do not paper over.
      * path / permission errors on the raw-capture or dedupe
        JSONL writer -- the out-directory is misconfigured or
        the operator lacks write access.
      * payload shape mismatch raised by the writer -- the
        scratch script wired the wrong record shape into the
        capture writer.

## 9. Post-run checks

After the run completes (or fails), in the same PowerShell
session:

  1. Inspect the printed `Stage22IngestResult` -- the outcome
     token and event counts should match section 7 for a
     success path, or one of the failure tokens above.
  2. Inspect the raw-capture JSONL file under the local
     out-directory. Each line is a sanitized record; there
     should be no raw exception text, no URL, no key, no
     recipient id.
  3. Inspect the dedupe JSONL file. It should contain a
     `seen` record and (on success) a matching `dispatched`
     record for the same key.
  4. Confirm the private Discord recipient received the
     expected short message (section 7). If a public channel
     received anything, treat it as a Stage 22 incident; see
     section 10.
  5. `git status --short` -- the result should be identical
     to the pre-run state. If any new tracked file appeared
     (especially one with a key-bearing name), STOP and
     investigate before any further action.
  6. Close the PowerShell session so the env vars disappear.

## 10. Stop conditions

Stop, do NOT retry, and investigate if any of these happen:

  * Any real secret value appears in stdout, in any artifact
    file, in any tracked file, or in any error message.
  * A public Discord channel, a subscriber channel, or any
    non-private recipient receives a message.
  * The runner raises an unexpected Stage 21 or Stage 22
    exception not listed in section 8.
  * The raw-capture writer fails to write but the dispatch
    succeeded (the bounded runner sequences capture BEFORE
    dispatch, so this is a contract violation).
  * The dedupe artifact looks inconsistent (a `dispatched`
    record with no preceding `seen` record on a fresh ledger).
  * The Discord transport repeatedly refuses dispatch with a
    rejection reason the operator does not recognise.
  * Repeated `all_malformed` outcomes on a non-empty fetch
    window -- the adapter or decoder has drifted.

In all stop cases: do not push, do not commit, do not amend,
do not delete the artifacts. Capture the printed outcome
token, the artifact paths, and any rejection-reason token, and
escalate.

## 11. Stage 23 / 24 / 25 handoff

  * Stage 23 -- filters / scoring / eligibility. The Stage 22
    bounded runner is the input boundary for Stage 23 work;
    Stage 23 work does NOT happen in Stage 22.6.
  * Stage 24 -- execution-side hardening (fee / Jito / Axiom
    / global fee model). Stage 22.6 does NOT touch any of
    that vocabulary; the corresponding tokens remain in the
    Stage 22 forbidden-vocabulary scanner.
  * Stage 25 -- ATH / Birdeye / migration measurement
    hardening. The Stage 22 private ping body intentionally
    omits all price / ATH / migration / filter / fee / X /
    social fields; Stage 25 is the earliest stage at which any
    such field may appear near a dispatch sink.

The first private ping is the END of Stage 22's operator
contract. Stages 23 / 24 / 25 begin only after the operator
has explicitly authorised a `stage-22-closed` tag.
