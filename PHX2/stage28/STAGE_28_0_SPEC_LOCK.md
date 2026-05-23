# PHX2 Stage 28.0 — Spec Lock / Reliability Charter

Stage 28.0 is the scaffold-only spec-lock pass. It ships no
runtime reliability code, no provider-neutral config wrapper, no
dedupe ledger, no retry policy, no audited Discord transport, no
heartbeat / health snapshot, no longer-session runner, and no
longer-session smoke harness. Stage 28.0 ships only this
document, the Stage 28 package marker, the Stage 28 tests
package marker, and the Stage 28.0 spec-lock tests.

---

## 1. Mission

> Stage 28 is private live runner reliability hardening.

That sentence is the canonical Stage 28 scope. Future Stage 28
substages must preserve it verbatim.

Stage 28 hardens the Stage 27 private live tradeable ping
runner so it can be run longer, restart cleaner, fail louder,
retry safely, dedupe across restarts, and expose operator-
visible health/status, while preserving private-only dispatch.

Stage 28 wraps and reuses Stage 27 surfaces. Stage 28 does not
rewrite Stage 27, does not broaden audience, does not broaden
routing, does not activate enforcement, and does not introduce
trading behavior.

---

## 2. Stage 27 reuse rules

Stage 28 must reuse and wrap the Stage 27 surfaces below. Stage
28 must not reimplement them.

Reuse, do not duplicate:

- `live_operator_config`
- `live_secrets_readiness`
- `live_run_identity`
- pump pair classifier / pair detection contracts
- provider ingest composition
- price / ATH context reader
- live measurement context
- live candidate assembler
- private ping renderer
- private ping provenance / artifact writer
- bounded dry-run runner
- live smoke dispatch seven-gate chokepoint
- private Discord sender / models
- Stage 27 pair suppression rules (UNKNOWN / DISAGREE / USDC
  observe-only)

Do not reimplement:

- the pair classifier
- the seven dispatch gates
- live authorization checks
- the private ping renderer schema
- Stage 25 / Stage 26 measurement / calibration logic
- Stage 21 / 22 / 23 / 24 legacy internals as runtime
  dependencies, unless an explicitly authorized future substage
  reopens that

Stage 28 may add thin reliability wrappers around these
surfaces (config aggregator, dedupe ledger, retry wrapper,
audited transport, heartbeat writer, longer-session loop), but
the Stage 27 surfaces remain the authoritative implementations.

---

## 3. Substage plan

The planned Stage 28 substage sequence is:

- 28.0 spec lock / reliability charter (this document)
- 28.1 provider-neutral config wrapper
- 28.2 restart-safe dispatch ledger
- 28.3a failure classification
- 28.3b retry policy
- 28.4 audited private HTTP Discord transport
- 28.5 heartbeat / health snapshot / CLI status
- 28.6 longer-session bounded private runner with graceful
  shutdown
- 28.7 longer-session smoke harness + controlled live smoke
- 28.8 closure audit + Stage 29 handoff

Every substage past 28.0 requires explicit operator
authorization before any edit lands. No substage past 28.0 is
authorized by this document. Stage 28.0 only locks the plan.

---

## 4. Reliability surfaces Stage 28 may own

Stage 28 may own reliability surfaces in the following list and
nowhere else:

- crash recovery story
- restart-safe dedupe
- ambiguous send handling
- bounded retry / backoff
- provider disconnect / reconnect handling
- Discord 429 / 5xx handling
- price API timeout handling
- stale price suppression
- artifact write fail-closed behavior
- malformed event capture / suppression
- graceful shutdown
- heartbeat / health snapshots
- final run summary
- operator-visible CLI status
- provider-neutral Chainstack / Helius naming cleanup
- safe transition from scratch transport to tracked audited
  private transport
- continued redaction of secrets

Anything outside this list is out of Stage 28 scope and
requires a separately authorized stage.

---

## 5. Dedupe principles to lock

Stage 28 must include restart-safe dedupe before longer
private live sessions are trusted.

The Stage 28 dedupe principles are:

- Dedupe must survive process restart.
- Dedupe must be append-only and replayable.
- Reserve / write dedupe intent before attempting send.
- Write / render pre-send provenance before attempting send.
- Mark the terminal send result after send.
- If a crash leaves a reserved / non-terminal send state, the
  resumed runner must treat that state as ambiguous and
  suppress re-send by default.
- Duplicate replay must never generate another private Discord
  ping.
- Dedupe protects private dispatch safety only. Dedupe is not
  enforcement, is not policy approval, and is not trade gating.

Stage 28 must lock an ambiguous-send suppression principle:
ambiguous dedupe state suppresses re-send by default.

---

## 6. Retry / backoff principles to lock

The Stage 28 retry / backoff principles are:

- Every retry must be bounded.
- No infinite retry loops.
- No unbounded retry queues.
- No silent drops.
- No retry storms.
- No auto-restart daemon, watchdog, or autorestart service.
- Every exhausted retry path must produce a closed-set failure
  reason.
- Artifact write failures must fail closed before dispatch.
- UNKNOWN / DISAGREE pair cases are not retryable.
- Stale price is not retryable beyond a bounded refresh
  attempt.
- Discord 429 should respect retry-after if available, within
  caps.

Stage 28 must lock the bounded-retry-no-infinite-retry
principle.

---

## 7. Health / status principles to lock

The Stage 28 health / status principles are:

- Stage 28 should expose operator-visible status for longer
  private sessions.
- CLI status lines are allowed.
- Heartbeat / health / final summary artifacts are allowed.
- No public dashboard.
- No HTTP control server.
- No Discord operational-status spam path.
- No Prometheus / OpenTelemetry / exporter scope in Stage 28.0
  unless explicitly authorized later.

Stage 28 health / status is operator-visible only and must not
broaden audience.

---

## 8. Provider-neutral config cleanup principles

Stage 28 should clean up provider naming so the runner is not
visibly Helius-only or Chainstack-only.

Locked direction:

- Introduce provider-neutral names in Stage 28, for example
  `PHX2_PROVIDER_GRPC_ENDPOINT` and similar.
- Preserve Stage 27-era names such as `HELIUS_GRPC_ENDPOINT`
  as legacy aliases if needed for backwards compatibility.
- Prefer the new provider-neutral name when present.
- If the new and legacy names are both set and disagree, the
  runner must refuse to start.
- Never log raw provider endpoints, API keys, webhook
  identifiers, auth headers, bearer tokens, or any secret-like
  values.
- Safe non-secret labels such as a provider id or provider
  kind (for example a literal `chainstack` or `helius` label)
  may be logged when they are explicitly non-secret.

Stage 28 must lock the provider-neutral-config alias principle.

---

## 9. Dexscreener decision

Stage 28.0 locks the Dexscreener stance as:

- Dexscreener is design-only or provenance-only at most in
  Stage 28.
- Dexscreener must not become a dispatch authority in Stage 28.
- Dexscreener must not bypass Stage 25 measurement contracts.
- Birdeye / Stage 25-style authoritative measurement remains
  the live dispatch authority unless a future explicitly
  authorized stage changes that.
- Price API failure must suppress tradeable private pings
  rather than silently substituting a non-authoritative source.

Stage 28 must lock the Dexscreener-is-not-dispatch-authority
principle.

---

## 10. Audited transport principles

Stage 28 may add an in-repo audited private Discord HTTP
transport in a later substage. The audited transport
principles are:

- The audited transport must remain private-operator only.
- It must not add channel routing, subscriber routing, public
  routing, or paid-tier routing.
- It must not leak the private webhook identifier or any
  secret values in records, exceptions, logs, artifacts, or
  metrics.
- The transport send call must preserve exactly-one-send
  semantics per send intent.
- A retry wrapper, if added later, must treat each retry as
  an attempt within one send intent and must record those
  attempts.
- The transport must continue Stage 27's secret-redaction
  discipline.

Stage 28 must lock the audited-transport privacy and
redaction principle.

---

## 11. Boundary locks — forbidden Stage 28 surfaces

Stage 28 must not include, and Stage 28.0 tests must continue
to block, the following surfaces:

- public routing
- subscriber routing
- paid tier routing
- broad Discord distribution
- Telegram
- X / social
- Stage 29 enforcement
- approval semantics
- activation semantics
- runtime allow / block gates from Stage 26 policy candidates
- automated trading
- wallet / private-key / signer logic
- position sizing
- trade execution
- public dashboard / control panel
- HTTP control server
- daemon / systemd / watchdog / autorestart service

Stage 28.0 scaffold admits only:

- `PHX2/stage28/__init__.py`
- `PHX2/stage28/STAGE_28_0_SPEC_LOCK.md`

and tests package files:

- `PHX2/tests/stage28/__init__.py`
- `PHX2/tests/stage28/test_stage_28_0_spec_lock.py`

Stage 28.1 narrow amendment (authorized 2026-05-22): the
provider-neutral config wrapper substage is authorized and adds
the following Stage 28.1 production .py inventory under
`PHX2/stage28/`:

- `provider_neutral_models.py`
- `provider_neutral_config.py`
- `provider_neutral_readiness.py`
- `stage28_1_manifest.py`

and the following Stage 28.1 test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_1_provider_neutral_models.py`
- `test_stage_28_1_provider_neutral_config.py`
- `test_stage_28_1_provider_neutral_readiness.py`
- `test_stage_28_1_boundaries.py`

Stage 28.1 is the provider-neutral config / secrets-readiness
cleanup layer only. It ships no network calls, no Discord
dispatch, no provider connection, no dispatch ledger, no retry /
backoff, no failure classification, no audited HTTP transport,
no heartbeat / health snapshot, no CLI status line, no bounded
private session runner, no longer-session smoke harness, no
Stage 29 enforcement, no X / social, no Telegram, no public
routing, no subscriber routing, no paid tier routing, no
automated trading, no wallet / private-key / signer logic, no
position sizing, no trade execution, no dashboard / HTTP control
server, and no daemon / systemd / watchdog / autorestart service.

Any other `PHX2/stage28/*.py` file or other Stage 28.2+
production file is out of Stage 28.1 scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

- `dispatch_ledger.py`
- `dispatch_ledger_models.py`
- `failure_classification.py`
- `retry_policy.py`
- `audited_http_transport.py`
- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `bounded_private_session_runner.py`
- `longer_session_smoke_harness.py`
- `stage28_manifest.py`

---

## 12. Closed-set vocabulary placeholders

Stage 28 will need several closed-set vocabularies before any
of the listed substages can land runtime code. Stage 28.0
names these placeholders and locks that the values are
defined in a later substage, not here:

- `run_mode`
- `stop_reason`
- `dedupe_state`
- `dispatch_terminal_state`
- `retry_outcome`
- `failure_kind`
- `provider_status`
- `price_status`
- `artifact_status`
- `heartbeat_status`
- `redaction_status`

Stage 28.0 must not ship runtime models, enums, or constants
for these vocabularies. They appear in this document as
names only, so that later substages can land them under a
known list.

---

## 13. Ownership boundaries / deferred ownership

Stage 28 owns private runner reliability hardening only.

- **Stage 29 owns approved enforcement / live gating.** Any
  policy candidate activation, live gate, allow / block
  decision, operator approval semantics, or enforcement-
  derived routing belongs to Stage 29 and requires its own
  explicit authorization.
- **Stage 30+ owns the X / social sidecar.** Any X API,
  social scraping, tweet ranking, social scoring, or public
  social distribution work belongs to Stage 30+ and must
  stay out of Stage 28.

Portfolio / thesis journal / dashboard work is also separate
and is not Stage 28.

---

## 14. Scope finalization

Stage 28 must not:

- alter Stage 27.7b dispatch behavior
- add public routing
- add subscriber routing
- add paid tiers
- add Telegram
- add X / social
- add Stage 29 enforcement
- add automated trading
- broaden Discord distribution

Stage 28 may improve private runner reliability only, under
the substage plan in Section 3, with explicit operator
authorization required for each substage past 28.0.

This document is the Stage 28 spec lock. Stage 28.1+ substages
must reference it.
