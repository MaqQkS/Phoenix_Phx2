# PHX2 Stage 29.4 — Short-Session Private Tradeable Soak Runbook

Stage 29.4 is the bounded short-session private observation /
soak substage that composes the Stage 29.3 single-shot private
tradeable smoke into a bounded outer loop with cross-pass
in-memory dedupe, heartbeat / health-snapshot artifacts, and a
soak summary. Stage 29.4 ships NO daemon, NO infinite loop, NO
public / subscriber / paid-tier routing, NO Telegram, NO X /
social, NO automated trading, NO wallet / private-key / signer
surface, NO new env names, NO new third-party dependencies, NO
PHX1 / Phoenix_Bot import path, NO Stage 26 enforcement
activation, NO persistent dedupe index, and NO Stage 29.5+
implementation.

Stage 29.4 is split into:

- **Stage 29.4.0** — the spec-lock-only commit. Ships this
  runbook + the Stage 29.4 spec-lock test + narrow test
  allowlist widenings in the Stage 28.8 / 28.9 / 28.10 / 28.11
  boundary tests and in the Stage 29.0 spec-lock test. Stage
  29.4.0 ships zero runtime production code. Stage 29.4.0 makes
  no edits to Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 /
  Stage 29.3 production source.
- **Stage 29.4.1** — the implementation commit (NOT shipped at
  Stage 29.4.0). Will land the Stage 29.4 soak runner, dedupe
  index, soak artifact writer, soak models, and Stage 29.4
  manifest under operator authorization on a separate commit.
  Stage 29.4.1 is reserved at Stage 29.4.0.

---

## 1. Canonical Stage 29.4 mission sentence

> Stage 29.4 is the bounded short-session private tradeable soak around the Stage 29.3 first private tradeable smoke. It composes Stage 29.3 single-shot ceremonies into a bounded outer loop over a caller-supplied wall-clock window with caller-supplied caps on dispatches, suppressions, and passes, plus a cross-pass in-memory dedupe layer that prevents the same on-chain event from producing two private operator pings.

Future Stage 29.4 patches must preserve this sentence verbatim.

---

## 2. The three operator-supplied ceremony modes

Stage 29.4 reuses the Stage 29.3 mode 1 and mode 2 labels
verbatim. Stage 29.4 mode 3 is the new bounded outer-loop soak.

| Mode | Outcome on success | Touches |
|---|---|---|
| `READINESS_ONLY` | `READY` | nothing live |
| `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY` | `CONNECTED` | one Chainstack `Subscribe` scan + one Birdeye `/defi/price` |
| `SHORT_SESSION_PRIVATE_SOAK_DRY_RUN` | one of the closed-set Stage 29.4 outcomes | the full Stage 29.3 chain, looped up to the operator-supplied caps |

Modes 1 and 2 are aliases of the Stage 29.3 single-shot modes
and do NOT engage the soak loop. Mode 3 engages the bounded
outer loop and is the only Stage 29.4 mode that may dispatch
more than one private operator ping per ceremony.

Run modes 1 -> 2 -> 3 sequentially. Stop at the first
non-success verdict; investigate; re-run.

---

## 3. Operator-supplied soak bounds

Stage 29.4 mode 3 takes the following operator-supplied bounds.
Every bound is required; Stage 29.4 rejects unbounded calls.

| Bound | Recommended range | Hard requirement |
|---|---|---|
| `wall_clock_seconds` | 600 to 1800 (10 to 30 minutes) | finite, positive |
| `max_dispatches` | 3 to 5 | finite, positive, small |
| `max_passes` | 3 to 60 | finite, positive |
| `max_total_retries` | 0 per pass | exactly 0 (no Stage 28.3b transport retries) |
| `max_consecutive_suppressions` | 3 to 20 | finite, positive |
| `heartbeat_cadence_seconds` | 10 to 60 | finite, positive |

Stage 29.4 refuses any call where any bound is missing,
non-positive, or unbounded. Bounds outside the recommended
range are admitted but logged on the soak summary.

Stage 29.4 inherits the Stage 29.3 per-pass internal locks
verbatim: each pass invokes the Stage 29.3 entry point with
`max_events=1`, `max_dispatches=1`, `max_total_retries=0` on
the Stage 28.9 session config. The Stage 29.4 outer loop runs
multiple passes, not multiple dispatches per pass.

---

## 4. Closed-set Stage 29.4 soak outcomes

Stage 29.4 mode 3 emits exactly one closed-set outcome on the
final soak summary record. The vocabulary is locked:

- `COMPLETED_AT_DISPATCH_CAP` — the soak reached
  `max_dispatches` successful private dispatches before any
  other bound triggered. Normal success.
- `COMPLETED_AT_WALL_CLOCK` — the soak reached
  `wall_clock_seconds` before reaching the dispatch cap.
  Acceptable; the operator can re-run a longer soak.
- `COMPLETED_AT_PASS_CAP` — the soak reached `max_passes`
  before reaching the dispatch cap or the wall clock.
  Acceptable; the operator can re-run with a larger
  `max_passes`.
- `BROKE_ON_SUPPRESSION_CIRCUIT` — the soak reached
  `max_consecutive_suppressions` consecutive non-dispatch
  passes (any closed-set `SUPPRESSED_*` outcome from Stage
  29.3) before any dispatch. The circuit breaker stops the
  soak; the operator can investigate the upstream pair
  classification and re-run.
- `BROKE_ON_REFUSED_READINESS` — the soak's first pass
  returned the closed-set Stage 29.3 `REFUSED` outcome (one of
  the closed-set Stage 29.3 refusal reasons such as
  `CHAINSTACK_READINESS_FAILED`, `BIRDEYE_READINESS_FAILED`,
  `WEBHOOK_MISSING`, `LIVE_FLAG_NOT_SET`,
  `OPERATOR_REQUEST_NOT_SET`, `OUTPUT_DIR_UNSAFE`,
  `KNOWN_MINT_INVALID`, `CHANNEL_FACTORY_NOT_CALLABLE`).
  The soak does not start the loop body.
- `BROKE_ON_FAILED_PASS` — the soak observed the closed-set
  Stage 29.3 `FAILED` outcome on any pass (one of the closed-
  set Stage 29.3 failure reasons such as `SUBSCRIBE_FAILED`,
  `STREAM_ERROR`, `DECODE_FAILED`, `BIRDEYE_CONNECT_FAILED`,
  `SESSION_REFUSED`, `SESSION_FAILED`). The soak stops the
  loop and surfaces the failed pass.
- `NO_DISPATCHES_NO_EVENTS` — the soak completed without
  reaching the dispatch cap and without observing any
  hint-bearing PumpSwap event in any pass. Every pass returned
  the closed-set Stage 29.3 `NO_EVENT_RECEIVED` outcome.
  Legitimate non-error result on a quiet PumpSwap window.
- `REFUSED_INVALID_BOUNDS` — Stage 29.4 rejected the call
  before starting the loop because one or more
  operator-supplied bounds were missing, non-positive, or
  otherwise invalid.

The Stage 29.4 final soak summary record carries exactly one
of the eight tokens.

---

## 5. Cross-pass in-memory dedupe semantics

Stage 29.4 mode 3 maintains a cross-pass dedupe index in
process memory only. The index is NEVER persisted to disk,
NEVER serialized across processes, NEVER written into any
artifact under the operator-supplied output directory, and
NEVER survives the Stage 29.4 soak call.

The dedupe index keys on a canonical Stage 29.4 dedupe key
shape derived from the Stage 28.2 dispatch ledger's already-
populated dispatch identity axes (the exact key shape is
specified in Stage 29.4.1). The dedupe index supports exactly
one mutation operation that returns one of two closed-set
dedupe outcomes:

- `NEW` — the key was not present in the index at call time.
  The Stage 29.4 outer loop forwards the candidate to the
  Stage 28.4 audited private transport. The Stage 28.4
  transport may then accept or reject independently.
- `DUPLICATE_SUPPRESSED_SOAK` — the key was already present
  in the index at call time. The Stage 29.4 outer loop
  suppresses the duplicate; the Stage 28.4 audited private
  transport is NEVER invoked for this duplicate; the soak
  summary increments the `duplicate_suppressed_soak_count`
  counter and continues.

Stage 29.4 guarantees: no duplicate private operator ping is
ever sent within a single soak call. The dedupe layer is the
sole mechanism that enforces this guarantee; it is independent
of the Stage 28.2 dispatch ledger's per-session
restart-safety semantics.

Stage 29.4 dedupe semantics do NOT extend across separate soak
calls. Two separate soak ceremonies on the same operator
machine are independent; the in-memory index in the first
ceremony is garbage-collected at function return and does not
inform the second ceremony.

---

## 6. Stage 29.4 acceptance artifact bundle

Stage 29.4.1 will write the following four artifacts into the
operator-supplied output directory at the end of every Stage
29.4 mode-3 ceremony:

- `stage29_4_soak_summary.json` — the immutable Stage 29.4
  soak summary record. Carries the closed-set soak outcome
  token, the rolled-up counters across every pass
  (`dispatch_success_total`, `dispatch_failure_total`,
  `duplicate_suppressed_soak_count`, `events_seen_total`,
  every Stage 29.3 closed-set `SUPPRESSED_*` per-outcome
  count, `no_event_received_count`, `passes_attempted`,
  `consecutive_suppression_streak_max`), the locked
  `filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`
  axis, the soak's elapsed wall-clock seconds, the soak's
  start / end timestamps in UTC ISO-8601, and the operator-
  supplied bounds echoed back.
- `stage29_4_heartbeat.jsonl` — append-only JSONL of one
  heartbeat record per pass (and one final-tick heartbeat at
  soak stop). Each record carries a redaction-safe counter
  projection of soak state at that pass tick, a UTC ISO-8601
  timestamp, and the per-pass closed-set Stage 29.3 outcome
  token.
- `stage29_4_health_snapshot.json` — the rolling Stage 29.4
  health snapshot. Atomically overwritten on every pass; the
  final write carries the last pass's snapshot.
- `stage29_4_redaction_scan.json` — the Stage 28.7-style
  redaction scan over the three Stage 29.4 artifacts above
  plus every per-pass Stage 29.3 artifact bundle written
  during the soak. Closed-set verdict: `SAFE` (zero forbidden
  substring hits) or `REDACTED` (one or more hits).

Stage 29.4.0 ships none of these artifact files; they are
described here as the Stage 29.4.1 contract.

---

## 7. Reused production modules (no edits at Stage 29.4)

Stage 29.4 reuses the following surfaces unchanged. Stage
29.4.0 makes ZERO production-code edits to any of them; Stage
29.4.1 also makes ZERO production-code edits to any of them.

- Stage 27 live candidate assembler (`PHX2.stage27.live_candidate_assembler`)
- Stage 27 pair classifier (`PHX2.stage27.pump_pair_classifier`)
- Stage 27 private ping renderer (`PHX2.stage27.private_ping_renderer`)
- Stage 27.4 `PriceContextSource` / `AthContextSource` Protocols
- Stage 27.6 `Stage27_6Sources` bundle + run-local dedupe
- Stage 28.2 restart-safe dispatch ledger
- Stage 28.4 audited private operator-only Discord HTTP transport
- Stage 28.5 heartbeat / health snapshot / final summary writers
- Stage 28.6 bounded private session runner
- Stage 28.9 default candidate assembler + private webhook transport + orchestrator
- Stage 28.11 Chainstack Yellowstone readiness env-read boundary
- Stage 29.1 PumpSwap hint-aware decoder
- Stage 29.2 Birdeye readiness env-read boundary + price source + ATH source + HTTP transport
- Stage 29.3 single-shot first private tradeable smoke orchestrator entry point

Stage 29.4 wraps the Stage 29.3 entry point in an outer
bounded loop. It does NOT reimplement the Stage 29.3 chain.

---

## 8. Stage 29.4.0 file inventory (this commit ships only these)

Stage 29.4.0 ships exactly two new tracked files:

- `PHX2/stage29/STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md`
  (this document)
- `PHX2/tests/stage29/test_stage_29_4_spec_lock.py`

Plus narrow test-files-only allowlist widenings in:

- `PHX2/tests/stage28/test_stage_28_8_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_9_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_10_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_11_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py`

Stage 29.4.0 ships zero runtime production code. Stage 29.4.0
edits no production source under `PHX2/stage27/`, `PHX2/stage28/`,
`PHX2/stage29/` (other than the new runbook .md file).

---

## 9. Stage 29.4.1 planned production inventory (NOT shipped at 29.4.0)

Stage 29.4.1 will add these production .py files under
`PHX2/stage29/`. None of them ship at Stage 29.4.0:

- `stage29_4_soak_models.py` — closed-set vocabularies +
  immutable frozen dataclasses for soak bounds, pass records,
  soak summary, dedupe key, soak error.
- `stage29_4_dedupe_index.py` — pure in-memory dedupe index.
- `stage29_4_soak_orchestrator.py` — bounded outer-loop entry
  point that wraps the Stage 29.3 single-shot orchestrator.
- `stage29_4_soak_artifact_writer.py` — atomic / append-only
  writers for the four Stage 29.4 acceptance artifacts.
- `stage29_4_manifest.py` — constants-only re-export manifest.

Stage 29.4.1 will also add focused test files under
`PHX2/tests/stage29/` and may further widen the Stage 28 / 29
test allowlists; those widenings are NOT performed at Stage
29.4.0.

---

## 10. Offline Stage 29.4.0 acceptance criteria

Stage 29.4.0 acceptance holds iff every one of the following
is true:

- The Stage 29.4 spec-lock test passes against this runbook.
- The full Stage 29 test suite passes.
- The four touched Stage 28 boundary tests pass with their
  widened allowlist unions.
- The Stage 29.0 spec-lock test passes with its widened
  allowlist unions.
- No Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage
  29.3 production .py file is modified at Stage 29.4.0.
- No live Chainstack gRPC call is performed during the Stage
  29.4.0 work.
- No live Birdeye HTTP call is performed during the Stage
  29.4.0 work.
- No private operator Discord send is performed during the
  Stage 29.4.0 work.
- No commit / tag / push is performed by the automated agent;
  the commit step is reserved for the operator on a separate
  turn.

---

## 11. Future Stage 29.4 live acceptance criteria

The Stage 29.4 live soak ceremony is operator-gated and runs
only after Stage 29.4.1 lands. The future live ceremony passes
when ALL of the following hold:

- At least one Stage 29.4 mode-3 pass reaches the closed-set
  Stage 29.3 `DISPATCHED` outcome (i.e. at least one real
  private tradeable ping is sent during the soak).
- `dispatch_failure_total` is `0`.
- `redaction_status` is `SAFE` over the full Stage 29.4
  artifact bundle and over every per-pass Stage 29.3 artifact
  bundle written during the soak.
- `filter_enforcement_status` is `NOT_ACTIVE_STAGE_29_PENDING`
  on every dispatched ping ledger record.
- No duplicate private operator ping is sent during the soak;
  every duplicate event is counted in
  `duplicate_suppressed_soak_count` with the Stage 28.4
  audited transport NEVER invoked for that duplicate.
- Each successful dispatched ping carries the canonical Stage
  28.2 dispatch ledger triple `RESERVE -> PRE_SEND ->
  TERMINAL` with terminal status `DISPATCHED_OK` and
  `ping_type=PRIVATE_OPERATOR_OBSERVE`.
- Audience invoked is the private operator only.
- No public routing, subscriber routing, paid-tier routing,
  Telegram send, X / social send, automated trading, or
  wallet / private-key / signer surface is invoked.

A Stage 29.4 mode-3 ceremony that completes the wall clock
without any dispatched ping (final outcome
`COMPLETED_AT_WALL_CLOCK`, `COMPLETED_AT_PASS_CAP`,
`NO_DISPATCHES_NO_EVENTS`, or `BROKE_ON_SUPPRESSION_CIRCUIT`)
is a legitimate non-error soak result that proves the bounded
session behavior, the heartbeat / health-snapshot artifacts,
the redaction discipline, and the dedupe layer all held
without surfacing a dispatchable event. Operators may re-run
the ceremony on a busier PumpSwap window.

---

## 12. Forbidden surfaces under Stage 29.4

Stage 29.4 must NOT include or import any of:

- daemon / systemd / watchdog / autorestart service
- infinite loop / unbounded session
- Stage 26 policy enforcement activation
- public routing
- subscriber routing
- paid-tier routing
- Telegram sender / Telegram client
- X / social sidecar
- automated trading / position sizing / trade execution
- wallet / private-key / signer logic
- public dashboard / HTTP control server
- new env name (Stage 29.4 reads zero env vars directly and
  introduces no new env name; it relies on the existing
  Stage 28.11 + Stage 29.2 readiness boundaries that Stage
  29.3 already invokes)
- new third-party runtime dependency
- PHX1 / Phoenix_Bot import path
- Pump.fun bonding-curve decoder
- Dexscreener as a dispatch authority
- Helius as a price source
- third or fourth provider beyond Stage 28.11 (Chainstack) +
  Stage 29.2 (Birdeye)
- persistent dedupe index (cross-pass dedupe is in-memory
  only and never serialized to disk)
- Stage 29.5+ implementation

Stage 29.4 production source under `PHX2/stage29/` must
contain zero `os.environ` / `os.getenv` / `os.environb`
calls. Stage 29.4 must not introduce any `time.sleep(`-driven
scheduling, any `threading.Thread`, any `asyncio` event loop,
any `subprocess`, any `multiprocessing`, or any
`signal.SIGTERM` / `signal.SIGINT` handler that bypasses the
bounded-cap exit path.

---

## 13. Stage 29.3 artifact-projection caveat (carried forward as deferred)

Stage 29.3 mode-3 ceremonies currently emit per-event Stage
29.3 artifact files (`stage29_3_extracted_hints.json` and
`stage29_3_birdeye_evidence.json`) that show the safe-shape
default projection (`NO_EXTRACTION` / `MISSING`) because the
mode-3 orchestrator passes `extraction=None` /
`price_snapshot=None` / `ath_snapshot=None` to the artifact
writer. This caveat is documented as a deferred cleanup item
in Section 12.6 of the Stage 29.3 runbook.

Stage 29.4 acceptance does NOT depend on this projection
being cleaned up. The authoritative proof axes for every
Stage 29.4 dispatched ping remain:

- the Stage 28.9 health-snapshot counters
  (`event_count`, `unknown_pair_suppressed_count`,
  `missing_price_count`, `last_event_status`,
  `last_ping_status`, `dispatch_success_count`,
  `redaction_status`), and
- the Stage 28.2 dispatch ledger terminal record
  (`terminal_status=DISPATCHED_OK`,
  `ping_type=PRIVATE_OPERATOR_OBSERVE`,
  `failure_reason=null`).

Threading the live extraction + Birdeye price / ATH evidence
back onto the per-event mode-3 artifact files is reserved for
a separate operator-gated substage (Stage 29.3E or a peer)
and is explicitly NOT part of Stage 29.4.

If the operator runs Stage 29.4.1 mode 3 and inspects the
per-pass Stage 29.3 artifact bundle directly, the
`NO_EXTRACTION` / `MISSING` safe-shape entries should be
read against the Stage 28.9 + dispatch ledger axes above
rather than as evidence of pipeline failure.

---

## 14. Operator preconditions for any future Stage 29.4 ceremony

When Stage 29.4.1 lands and a Stage 29.4 mode-3 soak ceremony
is run, the operator MUST confirm every Stage 29.3 operator
precondition (Section 9 of the Stage 29.3 runbook) AND:

- The Stage 29.3 mode-3 controlled live smoke proof recorded
  in Section 12 of the Stage 29.3 runbook holds in the
  operator environment (i.e. a single Stage 29.3 mode-3
  ceremony reached `DISPATCHED` with `redaction_status=SAFE`
  in the same operator environment).
- The Stage 29.4 offline test suite passes against the
  shipped Stage 29.4.1 code.
- The Stage 29.4 operator-supplied bounds fall within the
  recommended ranges in Section 3 of this runbook.
- The operator has typed an explicit per-ceremony Stage 29.4
  soak authorization phrase into the operator audit log.

Stage 29.4 documents these preconditions; it does not enforce
them in runtime code beyond the readiness gates Stage 29.3
already enforces.

---

## 15. Stage 29.4 closed-set vocabularies (summary)

### Probe mode

- `READINESS_ONLY`
- `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY`
- `SHORT_SESSION_PRIVATE_SOAK_DRY_RUN`

### Soak outcome

- `COMPLETED_AT_DISPATCH_CAP`
- `COMPLETED_AT_WALL_CLOCK`
- `COMPLETED_AT_PASS_CAP`
- `BROKE_ON_SUPPRESSION_CIRCUIT`
- `BROKE_ON_REFUSED_READINESS`
- `BROKE_ON_FAILED_PASS`
- `NO_DISPATCHES_NO_EVENTS`
- `REFUSED_INVALID_BOUNDS`

### Dedupe outcome

- `NEW`
- `DUPLICATE_SUPPRESSED_SOAK`

### Redaction status

- `SAFE`
- `REDACTED`

### Filter enforcement status (locked)

- `NOT_ACTIVE_STAGE_29_PENDING`

### Per-pass underlying Stage 29.3 closed-set outcomes (reused unchanged)

The Stage 29.4 outer loop observes the Stage 29.3 closed-set
outcomes verbatim and aggregates them onto the Stage 29.4
soak summary. The Stage 29.3 outcome vocabulary is the
canonical source; Stage 29.4 does not redefine it.

---

## 16. Sanitization discipline

This runbook contains zero URL literals, zero raw API-key
literals, zero webhook host literals, zero raw operator
secrets, zero env-name-paired-with-value entries, and zero
on-chain mint addresses. Every operator-side concrete value
lives in the operator audit log outside the repository.

The Stage 29.4 spec-lock test asserts the absence of URL
literals, secret-shape literals, and raw env-assignment
substrings in this runbook.
