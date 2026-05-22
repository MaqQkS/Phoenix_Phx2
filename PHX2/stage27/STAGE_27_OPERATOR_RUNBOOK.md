# PHX2 Stage 27 — Operator Runbook (Stage 27.7a)

Stage 27.7a is a **docs + dry-run smoke** pass on top of the Stage
27.0 → 27.6 architecture. It ships this operator runbook, the
companion `STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md`, a deterministic
in-process smoke harness (`dry_run_smoke_harness.py`), and the
Stage 27.7a manifest (`stage27_7_manifest.py`). It ships **no**
Discord sender, **no** live provider client, **no** real network
call, **no** new env-read site, and **no** Stage 29 enforcement.

---

## 1. What Stage 27 currently does

Canonical Stage 27 mission (single-line, verbatim from the Stage
27.0 spec lock):

> Stage 27 turns PHX2 into a private live PHX1-parity tradeable ping runner, with pair-aware SOL/USDC handling, while keeping enforcement and public routing out of scope.

In short: a private live PHX1-parity tradeable ping runner.

By the end of Stage 27.6 the pipeline is end-to-end and bounded:

- **Stage 27.0** — spec lock + architecture charter.
- **Stage 27.1** — operator config, run / session identity, two-
  factor LIVE authorization, isolated env-read site
  (`live_secrets_readiness.py`). LIVE remains fail-closed unless
  the env/config flag and the explicit operator argument both
  authorize it.
- **Stage 27.2** — pair classification contracts and skeleton
  classifier. UNKNOWN, USDC, SOL, DISAGREE pair verdicts are
  closed-set tokens. USDC and UNKNOWN never map to
  `EXISTING_SOL_LANE`.
- **Stage 27.3** — provider ingest composition. Stage 21 / 22
  normalized provider events are projected into a closed-shape
  `ProviderIngestOutputRecord` and a pair verdict is attached.
- **Stage 27.4** — price / migration / ATH measurement context.
  Each context is read through an injected source Protocol, never
  from a real provider or HTTP endpoint at the Stage 27 boundary.
- **Stage 27.5** — private-ping renderer + provenance writer.
  Outputs are deterministic, redacted, and offline.
- **Stage 27.6** — bounded dry-run runner + run-local dedupe. The
  runner is `DRY_RUN` only; `live_mode_authority="LIVE_ALLOWED"`
  fail-closes to a `LIVE_REFUSED` summary with zero events
  processed.

The pipeline is `Stage 27.3 → 27.2 → 27.4 → 27.5 → 27.6`, and
Stage 27.7a now adds a deterministic in-process **smoke harness**
that drives that pipeline over fake provider events, fake price /
ATH / migration sources, and a frozen clock.

---

## 2. What Stage 27.7a does NOT do

Stage 27.7a is **dry-run only**. It must not:

- create `private_discord_sender.py`,
- call Discord, Telegram, X / social, or any webhook,
- import a Discord, Telegram, X / social, or webhook library,
- read a webhook URL,
- send any message anywhere,
- call Helius, gRPC, Birdeye, or any HTTP / WebSocket endpoint,
- import `requests`, `httpx`, `aiohttp`, `grpc`, `websockets`,
- read a real `.env` value,
- promote UNKNOWN / DISAGREE / USDC into the existing SOL
  calibration lane,
- enforce a Stage 26 candidate policy,
- ship a public router, subscriber router, X / social module, or
  any Stage 29 enforcement gate.

Stage 27.7a only adds these production files under
`PHX2/stage27/`:

- `STAGE_27_OPERATOR_RUNBOOK.md` *(this document)*
- `STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md`
- `dry_run_smoke_harness.py`
- `stage27_7_manifest.py`

Every other Stage 27.7+ implementation basename — most importantly
`private_discord_sender.py` — remains blocked until its own
substage's explicit operator authorization.

---

## 3. Dry-run-only status

Stage 27.7a is a dry-run posture. The smoke harness ALWAYS:

- defaults to `DRY_RUN`,
- refuses `live_mode_authority="LIVE_ALLOWED"` (the Stage 27.6
  runner fail-closes with `mode=LIVE_REFUSED` / `stop_reason=
  LIVE_MODE_REFUSED`),
- requires an explicitly injected output root (no env / no global
  state),
- writes artifacts only under that injected root,
- never opens a network connection.

Stage 27.7a is **not** the controlled live smoke stage. The first
single private Discord ping smoke belongs to Stage 27.7b and only
runs after explicit per-substage operator authorization in that
turn's prompt.

---

## 4. How to run the dry-run smoke

The smoke harness is meant to be driven from the focused Stage
27.7a test suite, not from a CLI (Stage 27.7a ships no CLI). The
canonical entry point is:

    from PHX2.stage27.dry_run_smoke_harness import (
        build_default_smoke_events,
        build_default_smoke_sources,
        run_dry_run_smoke,
    )
    from pathlib import Path

    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=Path("/path/to/temp/dir"),
        smoke_id="smoke-001",
        run_id="run-001",
        session_id="sess-001",
        max_events=32,
    )

The harness wraps the Stage 27.6 bounded dry-run runner, so the
returned result carries the Stage 27.6 `run_summary` plus the
Stage 27.7a `smoke_summary` (which projects the run summary plus
the additional `smoke_id` and `output_root` fields documented in
Section 6).

To execute the smoke from the tests directly:

    py -m pytest PHX2/tests/stage27/test_stage_27_7_dry_run_smoke_harness.py -q

The test suite injects a temp directory for `output_root`, a
frozen clock, and synthetic provider events.

---

## 5. Expected artifact output shape

The Stage 27.6 dry-run artifact pair convention from Stage 27.5
applies unchanged:

- `ping_<ping_id>_payload.json` — Stage 27.5 ping payload.
- `ping_<ping_id>_provenance.json` — Stage 27.5 provenance.

For a successful SOL or USDC candidate the harness writes both
files. For a SUPPRESSED UNKNOWN / DISAGREE candidate the harness
also writes both files (so the operator has the full provenance
of the suppression decision), and the
`render_status` / `candidate_status` tokens identify the
suppression. The optional run summary lands at
`run_<run_id>_summary.json` under the same output root.

Every file is JSON; every value carries either a closed-set token,
a canonical decimal-text number, or a safe-to-display string.
There is no raw provider payload blob, no webhook URL, no API
key, and no enforcement decision in any artifact.

---

## 6. Expected smoke summary counters

The Stage 27.7a smoke summary is a small immutable record. The
canonical JSON encoding is `sort_keys=True`, `separators=(",",":")`,
`ensure_ascii=False`, so two identical runs produce byte-equal
encodings. The fields are:

- `smoke_id`                   — caller-supplied stable smoke id.
- `run_id` / `session_id`      — caller-supplied run / session
                                  identifiers (`None` when not
                                  attached).
- `mode`                       — `DRY_RUN` or `LIVE_REFUSED`.
- `events_seen`                — count of events drained from the
                                  smoke input iterable.
- `candidates_assembled`       — count of candidates with the
                                  Stage 27.6 `ASSEMBLED` token.
- `pings_rendered`             — count of successful
                                  `RENDERED_DRY_RUN` candidates
                                  (SOL + USDC).
- `artifacts_written`          — count of Stage 27.5 artifact
                                  files persisted (two per
                                  rendered candidate).
- `duplicates_skipped`         — count of `SKIPPED_DUPLICATE`
                                  results.
- `unknown_suppressed`         — count of `SUPPRESSED_UNKNOWN_PAIR`.
- `disagree_suppressed`        — count of `SUPPRESSED_DISAGREE_PAIR`.
- `usdc_observe_only_count`    — count of `RENDERED_DRY_RUN`
                                  results whose candidate reason
                                  is `USDC_OBSERVE_ONLY`.
- `unsupported_skipped`        — count of `SKIPPED_UNSUPPORTED_EVENT`
                                  / `SKIPPED_MISSING_TOKEN`.
- `errors`                     — count of `ERROR` /
                                  `ARTIFACT_WRITE_FAILED`.
- `output_root`                — the resolved absolute path string
                                  of the injected output root.
- `schema_version`             — locked Stage 27.7a smoke summary
                                  schema version.

No secret, raw payload, webhook URL, API key, or BUY / SELL /
APPROVED / GATE token ever appears in the smoke summary.

---

## 7. How to inspect ping and provenance artifacts

After a smoke run the operator (or the test fixture) can inspect
each artifact in the output root:

- `ls <output_root>` lists `ping_*_payload.json`,
  `ping_*_provenance.json`, and (if requested) the run-summary
  artifact.
- `python -m json.tool <output_root>/ping_<id>_payload.json`
  pretty-prints the payload record. The `render_status`,
  `pair_type`, `quote_asset`, `pair_detection_status`,
  `pair_live_policy`, and `calibration_lane` fields identify the
  pair-aware verdict.
- `python -m json.tool <output_root>/ping_<id>_provenance.json`
  pretty-prints the matching provenance record. The
  `redaction_status` token is always `REDACTED`; the
  `artifact_kind` token is always `PRIVATE_PING_DRY_RUN`.

The pair-aware verdict + the calibration lane must match the
event class. Section 9 lists the expected combinations.

---

## 8. How to verify no Discord send occurred

Stage 27.7a is dry-run only; verification is a static + behavioral
check, not a network probe:

- `git ls-files PHX2/stage27 | grep -i discord` MUST return
  nothing (no Discord-related module exists yet; the file
  `private_discord_sender.py` is reserved for Stage 27.7b only and
  must remain absent at Stage 27.7a closure).
- `grep -r "discord" PHX2/stage27` MUST return only the spec-lock
  doc / runbook / checklist references — never a transport
  module, never a webhook URL, never an import of a Discord
  library.
- The Stage 27.7a boundary tests assert that no production file
  imports `requests`, `httpx`, `aiohttp`, `urllib3`,
  `websockets`, `grpc`, `discord`, `telegram`, `webhook`, or any
  other forbidden runtime library.
- The harness itself never calls `Path.write_bytes` outside the
  injected output root; the Stage 27.5 path-safety helpers
  reject any path-traversal target before the write.

If any of the above checks reports a hit, the Stage 27.7a smoke
must be considered failed.

---

## 9. How to verify pair-aware behavior

The smoke harness ships deterministic fake events covering every
pair-aware class. The expected mapping is:

| Event class | quote_asset | pair_detection_status | calibration_lane               | live_policy             |
| ----------- | ----------- | --------------------- | ------------------------------ | ----------------------- |
| SOL         | `SOL`       | `CONFIRMED`           | `EXISTING_SOL_LANE`            | `LIVE_ALLOWED`          |
| USDC        | `USDC`      | `CONFIRMED`           | `USDC_OBSERVE_ONLY`            | `LIVE_ALLOWED`          |
| UNKNOWN     | `UNKNOWN`   | `UNRESOLVED`          | `UNKNOWN_PAIR_OBSERVE_ONLY`    | `LIVE_SUPPRESS_UNKNOWN` |
| DISAGREE    | `SOL`       | `DISAGREE`            | `DISAGREE_PAIR_OBSERVE_ONLY`   | `LIVE_SUPPRESS_DISAGREE`|

Locked rules:

- SOL events MUST resolve to `EXISTING_SOL_LANE`.
- USDC events MUST stay `USDC_OBSERVE_ONLY`; USDC must never map
  into `EXISTING_SOL_LANE`.
- UNKNOWN events MUST stay observe-only and SUPPRESSED in any
  LIVE posture.
- DISAGREE events MUST stay observe-only and SUPPRESSED in any
  LIVE posture.
- A duplicate event (same dedupe key inside the same run) is
  short-circuited with `SKIPPED_DUPLICATE`; no second artifact is
  written.

---

## 10. How to verify no real API keys were read

- Stage 27.7a does not add a new env-read site. The Stage 27
  env-read boundary remains exactly
  `PHX2/stage27/live_secrets_readiness.py`.
- `grep -nE "os\.environ|os\.getenv" PHX2/stage27/dry_run_smoke_harness.py PHX2/stage27/stage27_7_manifest.py`
  MUST return nothing.
- The smoke harness accepts every input as an argument
  (`output_root`, `events`, `sources`, ids, bounds); no value is
  read from `.env` or the process environment.
- The Stage 27.7a boundary tests assert the env-read boundary
  remains isolated to `live_secrets_readiness.py`.

---

## 11. How to interpret measurement warnings

A SOL candidate may render with the Stage 27.5
`RENDERED_WITH_WARNINGS` status when at least one measurement
axis is degraded. The corresponding Stage 27.6 candidate carries
the closed-set reason `RENDERED_WITH_WARNINGS`. Typical causes:

- `STALE` price (snapshot age exceeded the staleness threshold),
- `MAY_INCLUDE_PRE_MIGRATION` ATH (window not promised to start
  strictly post-migration),
- `UNTRUSTED` migration source (operator-provided / non-trusted
  upstream),
- `MISSING` price / ATH / migration (source returned `None`),
- `SOURCE_ERROR` on any sub-context.

In every case the ping payload still renders, the provenance
artifact is still written, and the operator sees the explicit
warning sentinel (e.g. `STALE`, `MAY_INCLUDE_PRE_MIGRATION`,
`UNTRUSTED`, `MISSING`, `SOURCE_ERROR`) rather than a fake zero.
A degraded measurement is a signal to inspect the source, not to
ship enforcement.

---

## 12. What remains for Stage 27.7b controlled live smoke

Stage 27.7b is the **first** controlled live smoke pass:

- It introduces a `private_discord_sender.py` transport surface
  for a single private operator Discord webhook.
- It introduces the LIVE gate that consumes both Stage 27.1
  authorization factors (env/config flag AND explicit operator
  argument) at the dispatch boundary.
- It ships the first single private Discord ping smoke under
  strict bounds (max_pings=1, single token, dry-run-equivalent
  payload).
- It MUST NOT begin until its own per-substage operator
  authorization in a future prompt. Stage 27.7a does **not**
  pre-authorize Stage 27.7b.

---

## 13. What remains for Stage 28 hardening

Stage 28 is the hardening stage. Crash recovery, retries / backoff,
health checks, restart-safe dedupe, richer provider failure
handling, monitoring, and longer-running reliability belong there,
not in Stage 27. Stage 27.7a explicitly does not implement any
of those surfaces.

---

## 14. What remains for Stage 29 enforcement

Stage 29 is where approved enforcement and live gating live.
Stage 26 candidate policies become enforcement only through Stage
29's explicit authorization gate. Stage 27.7a is observe + render
only; it does not promote any Stage 26 candidate policy into a
live verdict.

---

## 15. Stage 27.7a closure conditions

Stage 27.7a is closed when:

- this runbook exists and contains the dry-run-only status,
- `STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md` exists and contains the
  no-Discord / no-live / no-real-API / no-enforcement /
  pair-aware checks,
- `dry_run_smoke_harness.py` exists and refuses
  `LIVE_ALLOWED`, requires an injected output root, never reads
  the process environment, and never imports a network /
  messaging library,
- `stage27_7_manifest.py` exposes the Stage 27.7a production +
  test basename inventories and schema version,
- the Stage 27.7a test suite passes,
- the Stage 27.0 → 27.6 tests still pass,
- the Stage 25.7 + Stage 26.7 closure audits still pass under
  the narrow Stage 27.7a allowlist amendment,
- no Discord sender, no live provider client, no public router,
  no subscriber router, no X / social module, and no Stage 29
  enforcement gate has been introduced,
- no commit, tag, or push is performed by the implementation
  pass itself.

Tag creation (`stage-27-7a-closed` or any other Stage 27 tag) is
an operator-only action and is not performed by Stage 27.7a
implementation.
