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

Stage 28.2 narrow amendment (authorized 2026-05-22): the
restart-safe dispatch ledger substage is authorized and adds the
following Stage 28.2 production .py inventory under
`PHX2/stage28/`:

- `dispatch_ledger_models.py`
- `dispatch_ledger.py`
- `stage28_2_manifest.py`

and the following Stage 28.2 test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_2_dispatch_ledger_models.py`
- `test_stage_28_2_dispatch_ledger.py`
- `test_stage_28_2_boundaries.py`

Stage 28.2 is the restart-safe private dispatch ledger only. It
is an append-only, replayable, redaction-safe ledger of dispatch
intent + pre-send provenance reference + terminal dispatch
result. It exists to prevent duplicate private Discord pings
across process restarts and to expose closed-set decisions for
duplicate-terminal and ambiguous-non-terminal replay outcomes.

Stage 28.2 ships no network calls, no HTTP, no gRPC, no Discord
dispatch, no provider connection, no retry / backoff logic, no
failure classification beyond a closed-set placeholder, no
audited HTTP transport, no heartbeat / health snapshot, no CLI
status line, no bounded private session runner, no longer-
session smoke harness, no live smoke, no Stage 29 enforcement,
no X / social, no Telegram, no public routing, no subscriber
routing, no paid tier routing, no automated trading, no wallet /
private-key / signer logic, no position sizing, no trade
execution, no dashboard / HTTP control server, and no daemon /
systemd / watchdog / autorestart service. Stage 28.2 reads no
process environment variables; the ledger path is always an
explicit caller-supplied path.

The Stage 28.2 dedupe key fields are closed-set and exclude
`run_id`, `session_id`, wall-clock timestamps as uniqueness
sources, webhook URLs, provider endpoints, API keys, raw secret
values, and recipient / channel / subscriber fields.

Any other `PHX2/stage28/*.py` file or other Stage 28.3+
production file is out of Stage 28.2 scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

- `failure_classification.py`
- `retry_policy.py`
- `audited_http_transport.py`
- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `bounded_private_session_runner.py`
- `longer_session_smoke_harness.py`
- `stage28_manifest.py`

Stage 28.3a narrow amendment (authorized 2026-05-23): the
failure-classification substage is authorized and adds the
following Stage 28.3a production .py inventory under
`PHX2/stage28/`:

- `failure_classification_models.py`
- `failure_classification.py`
- `stage28_3a_manifest.py`

and the following Stage 28.3a test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_3a_failure_classification_models.py`
- `test_stage_28_3a_failure_classification.py`
- `test_stage_28_3a_boundaries.py`

Stage 28.3a is the failure-classification layer only. It ships
pure, deterministic, redaction-safe closed-set primitives that
map an opaque failure description (failure kind hint + optional
domain / status / exception / state hints) to a stable
`Stage28_3aFailureClassification` record over the locked Stage
28.3a closed-set vocabularies (failure kinds, domains,
recommended actions, severities, dispatch-safety status,
session-continuation status, operator-visibility, safe reason
codes, redaction status). Stage 28.3a is NOT retry policy;
Stage 28.3a is the vocabulary + classifier layer that the Stage
28.3b retry policy will consume.

Stage 28.3a ships NO retry / backoff policy, NO audited Discord
HTTP transport, NO heartbeat / health snapshot, NO CLI status
line, NO bounded private session runner, NO longer-session smoke
harness, NO live smoke, NO Stage 29 enforcement, NO X / social,
NO Telegram, NO public routing, NO subscriber routing, NO paid
tier routing, NO automated trading, NO wallet / private-key /
signer logic, NO position sizing, NO trade execution, NO
dashboard / HTTP control server, and NO daemon / systemd /
watchdog / autorestart service. Stage 28.3a reads NO process
environment variables; all classifier inputs are caller-supplied
closed-set hints.

The Stage 28.3a classifier output surface is closed-set and
redaction-safe by construction: even when a caller supplies a
`raw_message` field (accepted for test fixtures), the classifier
NEVER copies it onto the output record. The output exposes only
closed-set tokens + a closed-set `safe_reason_code` snake_case
derivation of the failure-kind token.

Any other `PHX2/stage28/*.py` file or other Stage 28.3b+
production file is out of Stage 28.3a scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

- `retry_policy.py`
- `audited_http_transport.py`
- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `bounded_private_session_runner.py`
- `longer_session_smoke_harness.py`
- `stage28_manifest.py`

Stage 28.3b narrow amendment (authorized 2026-05-23): the
retry-policy substage is authorized and adds the following Stage
28.3b production .py inventory under `PHX2/stage28/`:

- `retry_policy_models.py`
- `retry_policy.py`
- `stage28_3b_manifest.py`

and the following Stage 28.3b test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_3b_retry_policy_models.py`
- `test_stage_28_3b_retry_policy.py`
- `test_stage_28_3b_boundaries.py`

Stage 28.3b is the retry-policy contracts layer only. It ships
pure, deterministic, redaction-safe closed-set primitives that
consume Stage 28.3a failure-classification outputs and produce
bounded retry decisions (closed-set retry outcomes / closed-set
retry profile names / closed-set terminal reasons) for future
Stage 28 runner / transport substages. Stage 28.3b never sleeps,
never schedules, never queues, never spawns threads / async
tasks / subprocesses; the decision record is the only output the
policy emits, and a future Stage 28 substage owns the retry
executor.

Stage 28.3b ships NO audited Discord HTTP transport, NO
heartbeat / health snapshot, NO CLI status line, NO bounded
private session runner, NO longer-session smoke harness, NO live
smoke, NO Stage 29 enforcement, NO X / social, NO Telegram, NO
public routing, NO subscriber routing, NO paid tier routing, NO
automated trading, NO wallet / private-key / signer logic, NO
position sizing, NO trade execution, NO dashboard / HTTP control
server, and NO daemon / systemd / watchdog / autorestart
service. Stage 28.3b reads NO process environment variables;
every policy input is a caller-supplied closed-set Stage 28.3a
classification record plus caller-supplied bounded attempt /
budget counters.

The Stage 28.3b retry-after handling is bounded: any caller-
supplied numeric retry-after hint is clamped to a locked cap of
30 seconds before the decision is emitted. Negative, NaN,
infinite, or non-numeric retry-after hints are refused (the
policy falls back to the profile's scheduled delay). Every
Stage 28.3b retry profile has a finite delay schedule; no
profile uses unbounded exponential backoff and no profile uses
jitter.

Any other `PHX2/stage28/*.py` file or other Stage 28.4+
production file is out of Stage 28.3b scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

- `audited_http_transport.py`
- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `bounded_private_session_runner.py`
- `longer_session_smoke_harness.py`
- `stage28_manifest.py`

Stage 28.4 narrow amendment (authorized 2026-05-23): the
audited private Discord HTTP transport substage is authorized
and adds the following Stage 28.4 production .py inventory under
`PHX2/stage28/`:

- `audited_http_transport_models.py`
- `audited_http_transport.py`
- `stage28_4_manifest.py`

and the following Stage 28.4 test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_4_audited_http_transport_models.py`
- `test_stage_28_4_audited_http_transport.py`
- `test_stage_28_4_boundaries.py`

Stage 28.4 is the audited private Discord HTTP transport layer
only. It ships an in-repo, redaction-safe, private-operator-only
HTTP transport primitive that future Stage 28 runner / smoke
substages will inject into the existing private Discord send
path. The Stage 28.4 transport sends exactly one HTTP POST per
send invocation to one private operator Discord webhook URL,
returns a closed-set redaction-safe transport result, and never
exposes the raw webhook URL on records, exceptions, repr / str,
public dicts, or audit outputs.

Stage 28.4 ships NO runner, NO retry execution, NO retry
scheduler, NO sleep / no scheduling / no backoff execution, NO
heartbeat / health snapshot, NO CLI status line, NO bounded
private session runner, NO longer-session smoke harness, NO live
smoke, NO Stage 29 enforcement, NO X / social, NO Telegram, NO
public routing, NO subscriber routing, NO paid tier routing, NO
automated trading, NO wallet / private-key / signer logic, NO
position sizing, NO trade execution, NO dashboard / HTTP control
server, and NO daemon / systemd / watchdog / autorestart service.
Stage 28.4 reads NO process environment variables; the webhook
URL is always a caller-supplied argument passed at the dispatch
boundary.

Stage 28.4 may import standard-library HTTP primitives
(`urllib.request`, `urllib.error`, `json`, `ssl`), but only in
`audited_http_transport.py`. The Stage 28.4 models / manifest
modules must remain network-library-free. Stage 28.4 must NOT
import `requests` / `httpx` / `aiohttp` / `urllib3` / `discord.py`
/ Telegram libraries / webhook libraries / `grpc` / async / queue
/ threading / subprocess libraries.

The Stage 28.4 transport closed-set status vocabulary covers
`SENT_OK`, `RATE_LIMITED`, `SERVER_ERROR`, `NETWORK_ERROR`,
`AUTH_OR_WEBHOOK_REFUSED`, `VALIDATION_FAILED`, and
`PAYLOAD_REFUSED`. Each transport call records a
`send_attempt_count` of `0` (rejected before send) or `1`
(exactly one POST attempted). The Stage 28.4 transport may
parse a `Retry-After` header into a clamped non-negative numeric
field (capped at the locked Stage 28.4 retry-after maximum of
`30` seconds), but it must never sleep, must never retry, and
must never call the Stage 28.3b retry policy itself; the future
Stage 28 runner substage owns that orchestration.

Any other `PHX2/stage28/*.py` file or other Stage 28.5+
production file is out of Stage 28.4 scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `bounded_private_session_runner.py`
- `longer_session_smoke_harness.py`
- `stage28_manifest.py`

Stage 28.5 narrow amendment (authorized 2026-05-23): the
heartbeat / health-snapshot / CLI-status substage is authorized
and adds the following Stage 28.5 production .py inventory under
`PHX2/stage28/`:

- `health_status_models.py`
- `heartbeat_writer.py`
- `health_snapshot_writer.py`
- `cli_status_line.py`
- `stage28_5_manifest.py`

and the following Stage 28.5 test inventory under
`PHX2/tests/stage28/`:

- `test_stage_28_5_health_status_models.py`
- `test_stage_28_5_heartbeat_writer.py`
- `test_stage_28_5_health_snapshot_writer.py`
- `test_stage_28_5_cli_status_line.py`
- `test_stage_28_5_boundaries.py`

Stage 28.5 is the operator-visibility primitives layer only. It
ships redaction-safe, deterministic, closed-set record models for
heartbeat lines, health-snapshot JSON, final-run-summary JSON,
and CLI status-line input, plus the matching append-only
heartbeat writer, atomic snapshot writer, atomic final-summary
writer, and pure CLI status-line formatter. Stage 28.5 records
expose only closed-set status tokens (provider / price /
dispatch / ledger / transport / artifact / health / stop reason /
last-event / last-ping / retry-budget / redaction), non-negative
integer counters, safe-shape run / session identifiers, and the
locked Stage 28.5 redaction-status verdict; no webhook URL, RPC
URL, API key, bearer token, auth header, wallet / signer field,
public-routing / subscriber / paid-tier / trade / enforcement
field ever reaches a Stage 28.5 record.

Stage 28.5 ships NO runner, NO retry execution, NO retry
scheduler, NO sleep / no scheduling / no backoff execution, NO
audited HTTP transport changes, NO bounded private session
runner, NO longer-session smoke harness, NO live smoke, NO Stage
29 enforcement, NO X / social, NO Telegram, NO public routing,
NO subscriber routing, NO paid tier routing, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO dashboard / HTTP control server,
and NO daemon / systemd / watchdog / autorestart service. Stage
28.5 reads NO process environment variables; every artifact path
is a caller-supplied `pathlib.Path`.

The Stage 28.5 writers perform local filesystem I/O ONLY against
caller-supplied paths. They never broadcast to any Discord
channel, never forward to any subscriber, never send to any
public router, never call into any provider client, never call
HTTP / gRPC / sockets. The CLI status formatter is pure: it
returns a single-line string and performs no I/O at all. The
heartbeat writer is append-only; the snapshot and final-summary
writers use a temp-write-then-replace pattern so the on-disk
artifact is never observed in a half-written state.

Any other `PHX2/stage28/*.py` file or other Stage 28.6+
production file is out of Stage 28.5 scope and must trip the
Stage 28 boundary scan. Examples of basenames the boundary scan
must continue to block until the matching substage is explicitly
authorized:

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
