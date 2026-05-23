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

---

## 16. Stage 27.7b — controlled private Discord live smoke

Stage 27.7b is the FIRST controlled private operator-only Discord
smoke pass on top of the Stage 27.0 → 27.7a architecture. It is
**not** broad production. It is **not** public routing. It is
**not** a subscriber feed. It is **not** a paid tier. It is
**not** a Telegram or X / social surface. It is **not** Stage 29
enforcement. It is **not** automated trading.

What Stage 27.7b ships under `PHX2/stage27/`:

- `private_discord_models.py` — closed-set dispatch status /
  reason / mode / redaction vocabularies plus the immutable
  `Stage27_7bDispatchResultRecord`.
- `private_discord_sender.py` — operator-only injectable sender
  that accepts a `Stage27_7bDiscordTransport` Protocol; tests
  inject `Stage27_7bFakeDiscordTransport`. The module's
  `Stage27_7bRealHttpDiscordTransport` is the isolated real-
  network surface and intentionally raises `NotImplementedError`
  until an operator-audited transport implementation is injected.
- `live_smoke_dispatch.py` — controlled one-ping smoke dispatcher
  that enforces three live-auth factors plus the pair-aware
  refuse rules plus the one-ping bound.
- `stage27_7b_manifest.py` — locked Stage 27.7b schema axes and
  basename inventories.

What Stage 27.7b deliberately does NOT ship:

- No `public_router.py` / `subscriber_router.py` /
  `paid_tier_router.py` / `live_router.py`.
- No `telegram_sender.py` / `x_social*.py` / `social_sidecar.py`.
- No `enforcement_gate.py` / `enforce_policy.py` / any Stage 29
  enforcement surface.
- No automated trading / `auto_trade*.py` / `position_size*.py`.
- No broad Discord community distribution / role-gated community
  routing / Discord slash commands / Discord bot command tree.
- No persistent dedupe ledger / database / scheduler / queue.
- No new env-read site outside `live_secrets_readiness.py`.

---

## 17. Stage 27.7b live smoke preconditions

Every precondition below MUST be satisfied before an operator
initiates a controlled live smoke. The Stage 27.7b dispatch
returns one of the closed-set refusal statuses
(`REFUSED_NOT_LIVE`, `REFUSED_UNAUTHORIZED_MODE`,
`REFUSED_MISSING_WEBHOOK`, `REFUSED_MULTIPLE_PAYLOADS`,
`REFUSED_SUPPRESSED_PAIR`) on any missing factor, and the
transport is NOT called.

1. **Stage 27.1 composite resolves `LIVE_ALLOWED`.** The
   composite resolves only when BOTH the `PHX2_LIVE_MODE_ALLOWED`
   env / config flag parses as truthy AND the explicit operator
   CLI / argument LIVE request is set AND every required live
   secret in `STAGE27_LIVE_REQUIRED_FIELD_NAMES` is `PRESENT` and
   not `MALFORMED`.
2. **`operator_live_request=True`** is passed to
   `dispatch_one_private_ping_smoke(...)` as a second cross-check
   factor (NOT just the Stage 27.1 composite).
3. **`smoke_dispatch_request=True`** is passed as a third
   explicit smoke-gating factor.
4. **`dispatch_mode="LIVE_SEND"`** is passed; the default is
   `DRY_RUN`.
5. **Exactly ONE** Stage 27.5 rendered ping payload is in the
   `payloads` sequence (length must equal 1).
6. The injected transport is an operator-audited live transport
   (NOT the placeholder `Stage27_7bRealHttpDiscordTransport`).
7. The injected webhook URL is for ONE private operator Discord
   webhook only; no broad community channel, no subscriber
   channel, no paid tier channel.
8. The injected `webhook_identity` is a short safe-to-display
   label (e.g. `PRIVATE_OPERATOR_WEBHOOK`); it MUST NOT contain
   the URL.

---

## 18. Stage 27.7b — how to set `.env` safely

The Stage 27 env-read boundary remains exactly
`PHX2/stage27/live_secrets_readiness.py`. Stage 27.7b adds no
second env-read site. The expected env / config variable names
(SECRET-kind redaction discipline applies on every name in the
`STAGE27_SECRET_NAMES` tuple) are:

- `PHX2_LIVE_MODE_ALLOWED` — truthy bool literal to authorize
  LIVE; falsy / missing fails closed.
- `PHX2_PRIVATE_DISCORD_WEBHOOK_URL` — the private operator
  webhook URL. SECRET-kind: Stage 27.1 redacts it on the
  readiness summary; the raw value never lands on a Stage 27.1
  record, on a Stage 27.5 artifact, or on a Stage 27.7b dispatch
  result.
- `HELIUS_API_KEY` / `HELIUS_RPC_URL` / `HELIUS_GRPC_ENDPOINT` /
  `BIRDEYE_API_KEY` — required-LIVE secrets.
- `PHX2_PROVIDER_ID` — required-LIVE config label (non-secret).
- `PHX2_STAGE27_SCRATCH_DIR` / `PHX2_RUNNER_MAX_EVENTS` /
  `PHX2_RUNNER_MAX_SECONDS` — optional config values.

Safe `.env` discipline:

- Store the `.env` outside any tracked path.
- Set the file mode to operator-only (`chmod 600` on POSIX).
- NEVER paste the webhook URL into a doc, a checklist, an issue,
  a pull-request description, a Slack / chat message, a runbook
  step, or a screenshot. The Stage 27.1 redaction surface, the
  Stage 27.7b dispatch result, and the Stage 27.5 artifacts MUST
  NOT carry the URL.
- Inspect the `Stage27SecretsReadinessReport` (via the operator
  config builder) before initiating the smoke; verify
  `all_required_live_present is True` and every SECRET-kind
  field is reported as `PRESENT` with kind `SECRET` and
  `safe_value is None`.

---

## 19. Stage 27.7b — how to verify private Discord channel only

- The injected `webhook_url` MUST be for ONE private operator
  Discord channel. The Stage 27.7b dispatch sends to that one
  URL or refuses; there is no fan-out, no per-tier routing, no
  subscriber list, no community broadcast.
- The injected `webhook_identity` SHOULD be a short label like
  `PRIVATE_OPERATOR_WEBHOOK`; the label is the only webhook-
  identifying string admitted onto the dispatch result.
- Confirm `Stage27_7bDispatchResultRecord.dispatch_status` is
  `SENT` and `transport_status_code` is the expected success
  code (e.g. `200`) for the one smoke ping. Any other status is
  a refusal / transport error — inspect the closed-set
  `dispatch_reason` token.

---

## 20. Stage 27.7b — how to verify no public routing

- `git ls-files PHX2/stage27 | grep -E 'public_router|subscriber_router|paid_tier_router|live_router|telegram|x_social|social_sidecar|tweet_ranking'`
  MUST return nothing. None of those basenames exist in Stage 27.
- `git ls-files PHX2/stage27 | grep -i 'enforcement'` MUST
  return nothing. Stage 29 owns enforcement, not Stage 27.
- The Stage 27.7b boundary tests assert no Stage 27.7b
  production .py module imports a network / messaging library.

---

## 21. Stage 27.7b — how to verify the one-ping bound

- `STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH` is locked to `1`. The
  dispatch refuses (`REFUSED_MULTIPLE_PAYLOADS`) any `payloads`
  sequence whose length is not exactly `1`.
- The injected transport's `call_count` MUST be exactly `1`
  after a successful `SENT` smoke. The Stage 27.7b
  `Stage27_7bFakeDiscordTransport.call_count` property reports
  this.
- A second consecutive dispatch is a NEW one-ping smoke; the
  Stage 27.7b dispatch surface does NOT batch, does NOT queue,
  and does NOT schedule background work.

---

## 22. Stage 27.7b — how to inspect artifacts after the smoke

- The Stage 27.7b dispatch returns one
  `Stage27_7bDispatchResultRecord` per call. Inspect:
  - `dispatch_status` — closed-set status token.
  - `dispatch_reason` — closed-set reason code.
  - `dispatch_mode` — `DRY_RUN` or `LIVE_SEND`.
  - `webhook_identity` — safe-to-display label (NEVER the URL).
  - `ping_id` / `run_id` / `session_id` — provenance IDs
    preserved from the Stage 27.5 payload + the operator's
    session identity.
  - `sent_at_utc` — ISO-8601 UTC stamp from the injected
    dispatch clock.
  - `transport_status_code` — numeric status when the transport
    was called; `None` on refusal / dry-run.
  - `redaction_status` — always `REDACTED` on the happy path.
  - `schema_version` — locked Stage 27.7b dispatch result
    schema version (`stage27_v0_private_discord_dispatch_result`).
  - `pair_quote_asset` / `render_status` — pair-class echo for
    audit.
- The Stage 27.5 dry-run artifacts (`ping_<id>_payload.json` and
  `ping_<id>_provenance.json`) are still produced upstream of
  Stage 27.7b dispatch and are still safe to inspect. The Stage
  27.7b dispatch result does NOT re-emit the payload body or
  provenance artifact; the payload is rendered once by Stage
  27.5 and consumed once by the sender.

---

## 23. Stage 27.7b — how to confirm the webhook URL did not leak

The Stage 27.7b sender / dispatch / models surface NEVER stores
the webhook URL on any returned record and NEVER includes the URL
in any raised exception message. The Stage 27.7b tests assert:

- `Stage27_7bDispatchResultRecord` has NO `webhook_url` /
  `discord_webhook_url` field;
  `is_forbidden_dispatch_result_field_name(...)` rejects any such
  substring.
- `repr()` and `str()` of every Stage 27.7b dispatch result
  contain only safe-to-display closed-set tokens and provenance
  IDs.
- The Stage 27.7b sender error type
  (`Stage27_7bSenderArgumentError`) carries only the argument
  NAME, a closed-set reason, and an optional length integer.
- The Stage 27.7b transport error
  (`Stage27_7bTransportError`) carries only a closed-set `kind`
  token and an optional numeric `status_code`.

A defensive post-smoke check:

- The smoke fixture in
  `PHX2/tests/stage27/test_stage_27_7b_private_discord_sender.py`
  uses a deliberately-distinctive fake webhook URL canary and
  asserts the canary substring never appears in the dispatch
  result `repr()`, the dispatch result `str()`, any raised
  exception message, or the dispatch result fields.

---

## 24. Stage 27.7b — how to abort before sending

The Stage 27.7b dispatch has multiple natural abort paths. To
abort a smoke before any transport call, choose whichever is
easiest:

- Leave `dispatch_mode` at the `DRY_RUN` default. The dispatch
  returns `DRY_RUN_NOT_SENT` and the transport is never called.
- Pass `operator_live_request=False`. The dispatch returns
  `REFUSED_UNAUTHORIZED_MODE` / `OPERATOR_LIVE_REQUEST_MISSING`.
- Pass `smoke_dispatch_request=False`. The dispatch returns
  `REFUSED_UNAUTHORIZED_MODE` / `SMOKE_DISPATCH_REQUEST_MISSING`.
- Pass `live_mode_authority="LIVE_REFUSED"` (or `"DRY_RUN"`).
  The dispatch returns `REFUSED_NOT_LIVE` /
  `LIVE_AUTHORITY_NOT_ALLOWED`.
- Pass an empty `payloads` sequence. The dispatch returns
  `REFUSED_MULTIPLE_PAYLOADS` / `NO_PAYLOAD_PROVIDED`.
- Pass `webhook_url=""` (or `webhook_identity=""`). The dispatch
  returns `REFUSED_MISSING_WEBHOOK`.

In every abort case the dispatch result still records the
verdict (with `sent_at_utc` stamped from the injected clock) so
the operator audit log captures the decision. There is no live
network side-effect on any abort path.

---

## 25. Stage 27.7b is not broad production

Stage 27.7b is a CONTROLLED FIRST private operator Discord smoke
ping. It is not:

- a production routing surface,
- a subscriber feed,
- a paid tier surface,
- a Telegram or X / social surface,
- a broad Discord community feed,
- an automated trading surface,
- a Stage 29 enforcement surface.

Stage 28 owns hardening (crash recovery, retries / backoff,
health checks, longer-running reliability). Stage 29 owns
approved enforcement and live gating. Stage 30+ owns X / social.
Stage 27.7b does NOT pre-authorize any of those surfaces.

Tag creation (`stage-27-7b-closed` or any other Stage 27 tag) is
an operator-only action and is not performed by Stage 27.7b
implementation.
