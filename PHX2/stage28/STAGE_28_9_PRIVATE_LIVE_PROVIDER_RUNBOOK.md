# Stage 28.9 private live provider session runbook

Stage 28.9 is the post-Stage-28-closure operational bridge that
lets the already-closed Stage 28.6 bounded private session
runner consume real provider-backed candidate events from the
existing Stage 21 / Stage 27 chain so the operator can see real
private operator-only Discord coin pings.

Stage 28.9 ships NO Stage 29 enforcement, NO approval /
activation semantics, NO public routing, NO subscriber routing,
NO paid tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO dashboard / HTTP control server,
NO daemon / systemd / watchdog / autorestart service.

This runbook is a manual operator procedure. Nothing in this
document instructs a Python runtime to send anything; every send
that happens during a Stage 28.9 session is driven by the
caller-injected Stage 28.4 audited transport wrapped by the
Stage 28.9 private webhook transport, and the operator is
responsible for the wrap-and-go ceremony described below.

## 0. Scope marker

Stage 28.9 pings are real provider-backed candidates.

Full Axiom / Ante / wallet / holder filter enforcement is NOT
active yet. Stage 29 owns the approved gates / enforcement.
Early Stage 28.9 stream may be noisy: the operator MUST manually
interpret each ping. Every ping payload carries the locked
marker `Filter enforcement: NOT_ACTIVE_STAGE_29_PENDING` and a
policy mode of `PRIVATE_OPERATOR_ONLY_OBSERVE_MANUAL` so the
operator's eye is reminded on every line.

## 1. Required preconditions

Before a Stage 28.9 private live provider session is started the
operator MUST confirm each of the following:

1. **Explicit operator authorization.** The operator has typed
   the explicit "go" decision in their own console / log. The
   adapter refuses to start when `live_operator_request` is
   anything other than the literal Python `True`.
2. **Private Discord channel only.** The webhook URL points at
   a private operator-only Discord channel. No public, no
   subscriber, no paid tier, no other audience. The operator
   verifies the channel identity out-of-band; the adapter only
   echoes a safe `PRIVATE_OPERATOR_WEBHOOK` identity label on
   the result.
3. **Env readiness check.** The operator confirms the live
   environment readiness state without printing any secret. The
   readiness check is operator-side and out of scope of the
   adapter; the adapter only consumes the resulting boolean.
4. **Provider readiness check without printing secrets.** The
   operator confirms the provider client is up and responsive,
   without echoing any API key, bearer token, or RPC URL.
5. **Short bounded first run.** The operator sets a tight
   bounded first-session window: 5 to 15 minutes of wall time
   OR a tight `max_events` / `max_dispatches` cap (recommended
   defaults: `max_events <= 32`, `max_dispatches <= 16`).
6. **Out-of-repo artifact directory.** The operator supplies an
   explicit absolute path to a pre-existing directory that
   lives OUTSIDE the PHX2 working tree. The adapter never
   creates the directory, never echoes the path on any record,
   and refuses to start when the directory is missing or
   carries a URL-shaped substring in its path string.
7. **Max sends cap.** The Stage 28.6 runner config carries the
   hard cap; the operator has reviewed it.
8. **Redaction scan.** The operator runs the Stage 28.7-style
   redaction scan against the produced artifacts before sharing
   them with anyone (the scan looks for URL / secret / wallet /
   raw-response substrings and refuses to whitelist any
   artifact that contains them).
9. **Final report.** The operator captures the Stage 28.9
   session result record + the Stage 28.5-shaped final summary
   artifact for review.
10. **Rollback / stop.** The operator can request a stop via
    the Stage 28.6 `Stage28_6StopSignal` injected primitive
    (the adapter forwards the signal). The adapter has no
    daemon, no watchdog, no autorestart; on stop the bounded
    runner emits a final summary and the orchestrator returns.

## 2. Operator ceremony

The Stage 28.9 entry point is the `run_stage28_9_live_provider_session`
function in `live_provider_session_adapter.py`. The function
takes the following operator-supplied inputs:

* `config` -- the `Stage28_9LiveProviderSessionConfig` built via
  `build_live_provider_session_config(...)` with the locked
  per-session safe identifiers, provider id / kind labels,
  `max_events` / `max_dispatches` / `max_ticks` /
  `max_total_retries` / `heartbeat_every_n_events`, and the
  safe `output_dir_safe_label`.
* `provider_event_source` -- an object satisfying the
  `Stage28_9ProviderEventSource` Protocol. The operator
  supplies the real provider client (or a controlled fake);
  the adapter does NOT instantiate one.
* `candidate_assembler` -- an object satisfying the
  `Stage28_9CandidateAssembler` Protocol. The default real
  path is `Stage28_9DefaultCandidateAssembler(sources=...)`
  with the operator-supplied Stage 27.4 sources bundle (price
  context source, ATH source, migration source, Stage 27.4
  clock, Stage 27.5 clock, staleness threshold). Tests use a
  fake assembler that returns hand-crafted Stage 27.6 records.
* `transport` -- the Stage 28.6-shape transport. The operator
  wraps the real Stage 28.4 `Stage28_4AuditedHttpTransport`
  inside the Stage 28.9 `Stage28_9PrivateWebhookTransport`
  with the bound private webhook URL. The Stage 28.6 runner
  protocol sees only the wrapper; the URL never reaches the
  runner.
* `output_dir` -- the explicit absolute `Path` to the
  pre-existing operator-owned scratch directory (out of repo).
* `private_webhook_url` -- the private operator Discord
  webhook URL string. The adapter forwards the URL into the
  readiness check + the transport wrapper; it is NEVER echoed
  on any record.
* `live_env_ready` -- exactly `True` after the operator's
  out-of-band env readiness check passes.
* `live_operator_request` -- exactly `True` after the operator
  decides to go.

The adapter:

1. evaluates the Stage 28.9 readiness gate (no provider call
   yet);
2. on refusal returns a closed-set REFUSED result with a
   closed-set refusal reason;
3. on ready drains up to `max_events` normalized events from
   the provider source;
4. assembles each into a Stage 27.6 live candidate record via
   the injected assembler;
5. maps each Stage 27.6 candidate into a Stage 28.6 candidate
   event via the locked deterministic projection;
6. drives the Stage 28.6 bounded private session runner with
   the wrapped transport, emitting Stage 28.5-shape
   heartbeat / health snapshot / final summary artifacts under
   `output_dir`;
7. returns a Stage 28.9 session result with closed-set
   counters and the Stage 29-pending filter-enforcement
   marker.

## 3. Stage 27 safety suppressions preserved

The Stage 28.9 mapper preserves the existing Stage 27 / Stage
28.6 / Stage 28.2 / Stage 28.3a safety suppressions exactly:

* **UNKNOWN pair** -- Stage 27 `SUPPRESSED_UNKNOWN_PAIR`
  candidates project to the Stage 28.6 `CANDIDATE_PAIR_STATUS_UNKNOWN`
  pair status; the Stage 28.6 runner refuses the dispatch via
  the Stage 28.3a `UNKNOWN_PAIR_SUPPRESSED` classification.
* **DISAGREE pair** -- Stage 27 `SUPPRESSED_DISAGREE_PAIR`
  candidates project to Stage 28.6 `CANDIDATE_PAIR_STATUS_DISAGREE`;
  Stage 28.6 refuses via `DISAGREE_PAIR_SUPPRESSED`.
* **USDC observe-only** -- Stage 27 candidates with the
  `USDC_OBSERVE_ONLY` reason project to Stage 28.6
  `CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY`; Stage 28.6
  refuses via `USDC_OBSERVE_ONLY`.
* **STALE price** -- Stage 27 rendered ping with `price_status
  == STALE` projects to Stage 28.6 `CANDIDATE_PRICE_STATUS_STALE`;
  Stage 28.6 refuses via `PRICE_STALE`.
* **MISSING price** -- Stage 27 rendered ping with
  `price_status` in `(UNAVAILABLE, SOURCE_ERROR)` projects to
  Stage 28.6 `CANDIDATE_PRICE_STATUS_MISSING`; Stage 28.6
  refuses via `PRICE_MISSING`.
* **Malformed / skipped / error** -- Stage 27 candidates with
  `candidate_status` in `(ERROR, ARTIFACT_WRITE_FAILED,
  SKIPPED_UNSUPPORTED_EVENT, SKIPPED_MISSING_TOKEN,
  SKIPPED_DUPLICATE)` are marked `malformed=True` and refused
  by Stage 28.6.
* **Duplicate terminal** -- Stage 28.6 + Stage 28.2 continue
  to suppress duplicate terminal dispatches via the
  restart-safe dispatch ledger; nothing the Stage 28.9
  adapter does weakens that.
* **Ambiguous ledger** -- Stage 28.6 + Stage 28.2 continue to
  suppress ambiguous ledger states; nothing the Stage 28.9
  adapter does weakens that.

## 4. Rollback / stop

To stop a Stage 28.9 session in flight:

* request the injected Stage 28.6 `Stage28_6StopSignal` to
  stop (`signal.request_stop()`),
* the Stage 28.6 runner observes the request between
  candidates, emits the final summary artifact, and returns;
* the Stage 28.9 orchestrator returns the resulting Stage 28.9
  session result with the Stage 28.5 `OPERATOR_STOP` or
  `SIGINT` stop reason.

To roll back a Stage 28.9 session:

* the adapter writes only into the operator-supplied output
  directory; remove the directory (or its Stage 28.9-named
  artifacts) at the operator's discretion;
* there is no Stage 28.9 daemon, no autorestart, no scheduled
  job; nothing else to clean up.

## 5. Scope locks (re-stated)

Stage 28.9 explicitly does NOT add:

* Stage 29 enforcement,
* public routing,
* subscriber routing,
* paid tiers,
* Telegram,
* X / social,
* automated trading,
* wallet / private-key / signer logic,
* position sizing,
* trade execution,
* dashboard / HTTP control server,
* daemon / systemd / watchdog / autorestart service.

The full set is pinned in `stage28_9_manifest.py`
(`STAGE28_9_FORBIDDEN_SURFACES`).

## 6. Operator interpretation reminder

Every Stage 28.9 ping is a real provider-backed candidate. The
Stage 29 approved / activated filter enforcement gate is NOT
active. Operator MUST manually interpret each ping; no
automated decision flows from a Stage 28.9 ping. The marker
`Filter enforcement: NOT_ACTIVE_STAGE_29_PENDING` is stamped on
every payload header.
