# PHX2 Stage 29.5 — Helius WS Migration Evidence Adapter and Live Private Ping Context Join Spec Lock

Stage 29.5 is the Helius WebSocket migration evidence adapter
and live private ping context join substage for PHX2 private
tradeable pings. Stage 29.5 introduces a deferred Helius
WebSocket migration evidence boundary alongside a candidate-to-
migration join layer and a private ping migration context
projection that surfaces post-migration ATH verification
context for the existing Stage 28.9 private operator ping
render path. Stage 29.5 ships NO production enforcement, NO
public / subscriber / paid-tier routing, NO Telegram, NO X /
social, NO automated trading, NO wallet / private-key / signer
surface, NO daemon, NO new third-party runtime dependency, NO
PHX1 / Phoenix_Bot import path, NO direct PHX1 spaghetti copy,
NO Stage 26 enforcement activation, NO Discord dispatch
behavior change, and NO Stage 29.5.1+ implementation at Stage
29.5.0.

Stage 29.5 is split into:

- **Stage 29.5.0** — the spec-lock-only commit. Ships this
  spec-lock runbook + the Stage 29.5 spec-lock test + narrow
  test-files-only allowlist widenings in the Stage 28.8 /
  28.9 / 28.10 / 28.11 boundary tests and in the Stage 29.0
  spec-lock test. Stage 29.5.0 ships zero runtime production
  code. Stage 29.5.0 makes zero edits to Stage 27 / Stage 28 /
  Stage 29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 production
  source.
- **Stage 29.5.1** — the implementation commit (NOT shipped at
  Stage 29.5.0). May land the Stage 29.5 migration evidence
  models, the Helius WS adapter boundary or artifact reader,
  the candidate-to-migration join logic, the private ping
  migration context projection, and the Stage 29.5 manifest
  under operator authorization on a separate commit. Stage
  29.5.1 is reserved at Stage 29.5.0.

---

## 1. Canonical Stage 29.5 mission sentence

> Stage 29.5 is the Helius WebSocket migration evidence adapter and live private ping context join substage that lands a deferred Helius WS migration evidence boundary, a candidate-to-migration join layer, and a private ping migration context projection so that the existing Stage 28.9 private operator ping render path can surface post-migration ATH verification context without modifying any Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 production source at Stage 29.5.0.

Future Stage 29.5 patches must preserve this sentence
verbatim.

---

## 2. Stage 29.5 purpose

Stage 29.5 closes the migration evidence gap that prevents the
Stage 29.3 + Stage 29.4 private ping chain from confirming a
post-migration ATH on every dispatched private operator ping.
Today the Stage 27 + Stage 29.2 chain renders a private ping
when the Stage 29.1 PumpSwap hint quartet and the Stage 29.2
Birdeye price / ATH snapshot are both present, but the chain
carries no first-class signal that the observed pair has
migrated off the Pump.fun bonding curve onto PumpSwap. Stage
29.5 introduces that signal as a closed-set migration evidence
record, computes a candidate-to-migration join verdict, and
projects a private ping migration context object onto the
render path.

Stage 29.5 is observational only at Stage 29.5.1. The
migration evidence projection becomes a private ping rendering
input that the operator can audit. Stage 29.5 does NOT change
how Stage 28.9 dispatches, what audience receives the ping, or
what filter_enforcement_status the dispatch ledger records.
Stage 29.5 does NOT activate enforcement at any substage; the
locked `filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`
is preserved verbatim.

---

## 3. Stage 29.5.0 spec-lock-only scope

Stage 29.5.0 is a spec-lock-only pass. It ships:

- this spec-lock runbook (`STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md`)
- the Stage 29.5 spec-lock test
  (`test_stage_29_5_spec_lock.py`)
- narrow test-files-only allowlist widenings in the Stage
  28.8 / 28.9 / 28.10 / 28.11 boundary tests and in the Stage
  29.0 spec-lock test

Stage 29.5.0 ships zero runtime production code. Stage 29.5.0
introduces no new production .py file under `PHX2/stage29/`.
Stage 29.5.0 makes zero edits to Stage 27 / Stage 28 / Stage
29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 production source.

Stage 29.5.0 must not create a `stage-29-5-0-closed` tag.
Stage 29.5.0 must not move or peel the existing
`stage-28-closed` tag. Stage 29.5.0 must not push to any
remote. Stage 29.5.0 ships no live network call, no live
gRPC, no live HTTP, no live WebSocket, no live Discord send.

Stage 29.5.0 closed-set vocabularies are NAMES ONLY. Stage
29.5.0 must not ship runtime models, enums, or constants for
these vocabularies; the spec lock pins the token names, and
the Stage 29.5.1 production .py files will materialize them as
immutable frozen dataclasses + closed-set string constants.

---

## 4. Stage 29.5.1 planned scope (NOT shipped at Stage 29.5.0)

Stage 29.5.1 may later add the following surfaces under
operator authorization on a separate commit:

- **migration evidence models** — closed-set vocabularies +
  immutable frozen `Stage29_5MigrationEvidenceRecord` /
  `Stage29_5MigrationJoinRecord` /
  `Stage29_5PrivatePingMigrationContext` /
  `Stage29_5MigrationEvidenceError` dataclasses pinning the
  Stage 29.5 closed-set status / source / join-status /
  measurement-status / warning-code tokens.
- **Helius WS adapter boundary or artifact reader** — either a
  bounded Helius WebSocket boundary that consumes Helius WS
  migration evidence messages or an artifact reader that
  consumes a pre-recorded Helius WS migration evidence
  artifact bundle. The substage may ship either option (not
  both at Stage 29.5.1) under explicit operator selection. The
  adapter boundary is the single Stage 29.5 outbound network
  site if the WS option ships; the artifact reader has zero
  outbound network if the artifact option ships.
- **candidate-to-migration join logic** — pure function that
  joins a Stage 29.3 hint-bearing candidate (Stage 29.1
  PumpSwap hint quartet + Stage 29.2 Birdeye price / ATH
  snapshot) against a Stage 29.5 migration evidence record on
  the (`base_mint`, `pool_account`, `pool_program_id`,
  `quote_mint`) axis with a caller-supplied time window. Emits
  one of the closed-set `migration_join_status` tokens.
- **private ping context projection** — a pure function that
  projects a `Stage29_5PrivatePingMigrationContext` object
  from the join verdict and the Stage 27 price / ATH context
  record. The projection becomes a private ping render input.
- **Stage 29.5 manifest** — constants-only re-export manifest
  pinning the inventory, closed-set vocabularies, and
  forbidden surfaces of the Stage 29.5.1 production tree.

Stage 29.5.1 will also add focused test files under
`PHX2/tests/stage29/` and may further widen the Stage 28 /
Stage 29 test allowlists; those widenings are NOT performed at
Stage 29.5.0.

Stage 29.5.1 is reserved at Stage 29.5.0.

---

## 5. PHX1 read-only design reference

PHX1 (the legacy `Phoenix_Bot` codebase) may be consulted as a
read-only design reference when designing the Stage 29.5
migration evidence shape. The operator may read PHX1 source
for migration evidence axes, post-migration ATH semantics, and
the Helius WS message shape that PHX1's migration evidence
path consumes.

Stage 29.5.0 and Stage 29.5.1 must NOT import any PHX1 module,
must NOT copy PHX1 source verbatim into the Stage 29.5 tree,
and must NOT carry a PHX1 / Phoenix_Bot path substring or
import reference in any Stage 29.5 production source or test
source. PHX1 is a read-only design reference only; the Stage
29.5 implementation must be written fresh against the Stage
27 + Stage 28 + Stage 29.1-29.4 contracts.

PHX1 has a known spaghetti-copy risk: large PHX1 surfaces
combine migration evidence, price / ATH lookup, audience
routing, Telegram dispatch, and trade-execution scaffolding in
the same module tree. The Stage 29.5 implementation must NOT
adopt PHX1's module shape; Stage 29.5 must restrict itself to
the four Stage 29.5.1 surface families above and must
introduce no audience-routing, no Telegram, no trade-execution,
and no wallet surface on the back of the migration evidence
shape.

---

## 6. Closed-set Stage 29.5 vocabularies

The Stage 29.5 spec lock pins the following closed-set
vocabularies. Stage 29.5.0 ships these as token names only;
Stage 29.5.1 materializes them as immutable frozen Python
constants on the Stage 29.5 models module.

### 6.1 `migration_status`

A Stage 29.5 migration evidence record carries exactly one of:

- `PRESENT` — Stage 29.5 holds a non-empty migration evidence
  record for this candidate; the source is one of the closed-
  set `migration_source` tokens (not `UNKNOWN`).
- `MISSING` — Stage 29.5 holds no migration evidence record
  for this candidate; the join verdict will be `NO_MATCH`.
- `CONFLICTING` — Stage 29.5 holds two or more migration
  evidence records for this candidate that disagree on the
  migration slot, the migration timestamp, the migration
  source, or the migration pair axes. The join verdict will
  be `MULTIPLE_MATCHES`.
- `INVALID` — Stage 29.5 holds a migration evidence record
  whose required axes (migration timestamp, migration slot,
  migration pair, migration source) failed validation. The
  join verdict will be `SOURCE_INVALID`.
- `STALE` — Stage 29.5 holds a migration evidence record
  whose freshness gate has expired against the caller-
  supplied time window. The join verdict will be
  `TIME_WINDOW_INVALID`.

### 6.2 `migration_source`

A Stage 29.5 migration evidence record carries exactly one of:

- `HELIUS_WS` — the migration evidence record was sourced from
  a Helius WebSocket migration evidence message via the Stage
  29.5.1 Helius WS adapter boundary.
- `STAGE29_MIGRATION_ARTIFACT` — the migration evidence record
  was sourced from a pre-recorded Stage 29.5 migration
  evidence artifact bundle on disk, via the Stage 29.5.1
  artifact reader.
- `SYNTHETIC_TEST_ONLY` — the migration evidence record was
  constructed by a Stage 29.5 offline fake fixture for
  test-suite purposes only. Production code paths must refuse
  this source on any non-test build.
- `UNKNOWN` — the migration evidence record carries no
  identifiable source. Pairs with `migration_status=MISSING`
  or `migration_status=INVALID` only.

### 6.3 `migration_join_status`

A Stage 29.5 candidate-to-migration join record carries
exactly one of:

- `JOINED` — the candidate and the migration evidence record
  matched on (`base_mint`, `pool_account`, `pool_program_id`,
  `quote_mint`) within the caller-supplied time window. The
  measurement projection will be `COMPLETE` (subject to the
  measurement-status rules below).
- `NO_MATCH` — Stage 29.5 found no migration evidence record
  matching the candidate's axes. The measurement projection
  will be `MISSING_MIGRATION`.
- `MULTIPLE_MATCHES` — Stage 29.5 found two or more migration
  evidence records that match the candidate's axes and that
  disagree on the migration slot, the migration timestamp,
  the migration source, or the migration pair axes. The
  measurement projection will be `CONFLICTING_MIGRATION`.
- `SOURCE_INVALID` — Stage 29.5 found a migration evidence
  record whose required axes failed validation. The
  measurement projection will be `INVALID_MIGRATION`.
- `TIME_WINDOW_INVALID` — Stage 29.5 found a migration
  evidence record whose timestamp falls outside the caller-
  supplied time window (post-migration only). The measurement
  projection will be `PARTIAL_MIGRATION_PRESENT` or
  `INVALID_MIGRATION` depending on which axis failed.
- `PAIR_MISMATCH` — Stage 29.5 found a migration evidence
  record whose pair axes (e.g. `pool_program_id` or
  `quote_mint`) disagree with the candidate's pair axes. The
  measurement projection will be `INVALID_MIGRATION`.

### 6.4 `measurement_status`

A Stage 29.5 private ping migration context projection carries
exactly one of:

- `MISSING_MIGRATION` — no migration evidence record was
  joined to the candidate. Post-migration ATH is not
  verified; the private ping continues to render against the
  Stage 29.2 Birdeye snapshot alone.
- `PARTIAL_MIGRATION_PRESENT` — a migration evidence record
  was joined to the candidate but at least one required axis
  is unavailable (e.g. `MIGRATION_SLOT_MISSING`). The private
  ping continues to render; the projection surfaces the
  partial verification as a closed-set warning.
- `COMPLETE` — a migration evidence record was joined to the
  candidate, the migration timestamp and slot pass
  validation, and the Stage 29.2 Birdeye ATH window
  observably starts after the migration timestamp. Post-
  migration ATH is verified.
- `INVALID_MIGRATION` — a migration evidence record was found
  but failed validation. The private ping continues to render
  against the Stage 29.2 Birdeye snapshot alone; the
  projection surfaces the invalid migration as a closed-set
  warning.
- `CONFLICTING_MIGRATION` — two or more migration evidence
  records disagree. The private ping continues to render
  against the Stage 29.2 Birdeye snapshot alone; the
  projection surfaces the conflict as a closed-set warning.

### 6.5 Warning codes

The Stage 29.5 private ping migration context projection may
carry zero or more closed-set warning codes from the following
set. The set is locked; Stage 29.5.1 must not emit any token
outside this list:

- `MIGRATION_MISSING`
- `POST_MIGRATION_ATH_UNVERIFIED`
- `MIGRATION_SOURCE_UNKNOWN`
- `MIGRATION_CONFLICT`
- `MIGRATION_STALE`
- `MIGRATION_TIMESTAMP_INVALID`
- `MIGRATION_PAIR_MISMATCH`
- `MIGRATION_SLOT_MISSING`

The warning codes are observational only. Stage 29.5 must not
gate dispatch on any warning code; the private ping is
dispatched per the existing Stage 28.9 + Stage 28.4 + Stage
28.2 chain regardless of which warning codes are present, and
the warning codes ride on the private ping render output for
operator audit.

### 6.6 Filter enforcement status (locked)

- `NOT_ACTIVE_STAGE_29_PENDING` — Stage 29.5 must preserve
  this token verbatim on every dispatch ledger record.

---

## 7. Reused production modules (no edits at Stage 29.5.0)

Stage 29.5 reuses the following surfaces unchanged. Stage
29.5.0 makes ZERO production-code edits to any of them.

- Stage 27 live candidate assembler
- Stage 27 pair classifier
- Stage 27 private ping renderer
- Stage 27.4 `PriceContextSource` and `AthContextSource`
  Protocols
- Stage 27.6 `Stage27_6Sources` bundle and run-local dedupe
- Stage 28.2 restart-safe dispatch ledger
- Stage 28.4 audited private operator-only Discord HTTP
  transport
- Stage 28.5 heartbeat and health snapshot and final summary
  writers
- Stage 28.6 bounded private session runner
- Stage 28.9 default candidate assembler and private webhook
  transport and orchestrator
- Stage 28.11 Chainstack Yellowstone readiness env-read
  boundary
- Stage 29.1 PumpSwap hint-aware decoder
- Stage 29.2 Birdeye readiness env-read boundary and price
  source and ATH source and HTTP transport
- Stage 29.3 single-shot first private tradeable smoke
  orchestrator entry point
- Stage 29.4 short-session private soak orchestrator entry
  point

Stage 29.5 does NOT reimplement any of these surfaces. Stage
29.5.1 wraps the Stage 28.9 candidate assembler input axes
with the migration context projection; it does not modify the
assembler itself.

---

## 8. Stage 29.5.0 file inventory (this commit ships only these)

Stage 29.5.0 ships exactly two new tracked files:

- `PHX2/stage29/STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md`
  (this document)
- `PHX2/tests/stage29/test_stage_29_5_spec_lock.py`

Plus narrow test-files-only allowlist widenings in:

- `PHX2/tests/stage28/test_stage_28_8_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_9_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_10_boundaries.py`
- `PHX2/tests/stage28/test_stage_28_11_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py`

Stage 29.5.0 ships zero runtime production code. Stage 29.5.0
edits no production source under `PHX2/stage27/`,
`PHX2/stage28/`, `PHX2/stage29/` (other than the new spec-lock
runbook .md file).

---

## 9. Stage 29.5.1 planned production inventory (NOT shipped at Stage 29.5.0)

Stage 29.5.1 may later add these production .py files under
`PHX2/stage29/`. None of them ship at Stage 29.5.0:

- `stage29_5_migration_models.py` — closed-set vocabularies
  and immutable frozen dataclasses for the Stage 29.5
  migration evidence record, the migration join record, the
  private ping migration context projection, and the Stage
  29.5 error type.
- `stage29_5_helius_ws_adapter.py` — bounded Helius
  WebSocket adapter boundary (OR a paired artifact reader,
  not both; see Section 4). Single Stage 29.5 outbound
  network site if the WS option ships.
- `stage29_5_migration_artifact_reader.py` — pure file
  reader that consumes a pre-recorded Stage 29.5 migration
  evidence artifact bundle on disk.
- `stage29_5_candidate_to_migration_join.py` — pure join
  function over the (`base_mint`, `pool_account`,
  `pool_program_id`, `quote_mint`) axes with a caller-
  supplied time window. Emits one of the closed-set
  `migration_join_status` tokens.
- `stage29_5_private_ping_context_projection.py` — pure
  projection function that builds the
  `Stage29_5PrivatePingMigrationContext` from the join
  verdict and the Stage 27 price / ATH context record.
- `stage29_5_manifest.py` — constants-only re-export
  manifest.

Each of the above production basenames is pinned ABSENT at
Stage 29.5.0. The Stage 29.5 spec-lock test asserts that none
of them exist under `PHX2/stage29/` until Stage 29.5.1
materializes them under a separately authorized commit.

---

## 10. Stage 29.5.1 testing discipline

Stage 29.5.1 follows the established Stage 29.1-29.4 testing
discipline:

- **Fake / offline tests first.** Every Stage 29.5.1
  production .py file must ship with focused offline test
  coverage using fake adapters, synthetic migration evidence
  fixtures, and the existing Stage 29 offline test patterns.
  Stage 29.5.1 must not introduce a live-network test in its
  initial commit.
- **Closed-set discipline.** Every Stage 29.5.1 dataclass
  validator must enforce the closed-set vocabulary tokens
  from Section 6; arbitrary string values are rejected.
- **No invention discipline.** Stage 29.5.1 must never
  fabricate a migration timestamp, a migration slot, a
  migration source, or a migration pair axis. If the Helius
  WS adapter or artifact reader observes incomplete data, the
  Stage 29.5 migration evidence record carries
  `migration_status=MISSING` or `migration_status=INVALID`
  with the relevant axes set to None.
- **Boundary-test parity.** Stage 29.5.1 must include focused
  boundary tests on the Stage 29.5 production tree, pinning
  the single outbound network site (if the WS option ships),
  zero PHX1 / Phoenix_Bot import, zero forbidden third-party
  library, and zero raw secret-shape literal.

Live Helius WS or live migration artifact ceremonies are
operator-gated and run only after Stage 29.5.1 lands; they
are NOT part of Stage 29.5.0.

---

## 11. Offline Stage 29.5.0 acceptance criteria

Stage 29.5.0 acceptance holds iff every one of the following
is true:

- The Stage 29.5 spec-lock test passes against this runbook.
- The full Stage 29 test suite passes.
- The four touched Stage 28 boundary tests pass with their
  widened allowlist unions.
- The Stage 29.0 spec-lock test passes with its widened
  allowlist unions.
- No Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage
  29.3 / Stage 29.4 production .py file is modified at Stage
  29.5.0.
- No live Chainstack gRPC call is performed during the Stage
  29.5.0 work.
- No live Birdeye HTTP call is performed during the Stage
  29.5.0 work.
- No live Helius WebSocket call is performed during the
  Stage 29.5.0 work.
- No private operator Discord send is performed during the
  Stage 29.5.0 work.
- No tag is created and no push is performed by the
  automated agent; the commit step is reserved for the
  operator on a separate turn.

---

## 12. Forbidden surfaces under Stage 29.5

Stage 29.5 must NOT include or import any of:

- production enforcement (no Stage 26 policy enforcement
  activation; no Stage 29.5 enforcement gate at any
  substage)
- public routing
- subscriber routing
- paid-tier routing
- Telegram sender / Telegram client
- X / social sidecar
- automated trading / position sizing / trade execution
- wallet / private-key / signer logic
- private keys (no Stage 29.5 surface loads, validates, or
  references a private-key shape)
- daemon / systemd / watchdog / autorestart service
- infinite loop / unbounded session
- Discord dispatch behavior change (Stage 29.5 must not
  modify how Stage 28.4 dispatches, what audience receives
  the ping, or what the dispatch ledger records)
- public dashboard / HTTP control server
- new env name (Stage 29.5 reads zero env vars directly at
  Stage 29.5.0; Stage 29.5.1 may introduce at most ONE
  Stage-29.5-pinned env-read boundary if the Helius WS
  adapter option ships, mirroring the Stage 29.2 single-env-
  boundary pattern)
- new third-party runtime dependency
- PHX1 / Phoenix_Bot import path
- direct PHX1 spaghetti copy
- Pump.fun bonding-curve decoder
- Dexscreener as a dispatch authority
- Helius as a price source (Helius is admitted at Stage
  29.5 only as a migration evidence source via the Stage
  29.5.1 WebSocket adapter or artifact reader; Helius MUST
  NOT become a price / ATH provider)
- third or fourth provider beyond Stage 28.11 (Chainstack) +
  Stage 29.2 (Birdeye) + Stage 29.5 (Helius migration
  evidence only)
- persistent dedupe index
- tag (Stage 29.5.0 must not create `stage-29-5-0-closed`)
- push (Stage 29.5.0 must not push to any remote)
- Stage 29.6+ implementation

Stage 29.5 production source under `PHX2/stage29/` must
preserve the locked
`filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING` on
every dispatch ledger record. Stage 29.5.0 production source
contains zero `os.environ` / `os.getenv` / `os.environb`
calls (since Stage 29.5.0 ships zero production code). Stage
29.5 must not introduce any `time.sleep(`-driven scheduling,
any `threading.Thread`, any `asyncio` event loop (except
where Helius WS protocol semantics require a bounded async
client whose lifetime is fully scoped under the Stage
29.5.1 adapter boundary), any `subprocess`, any
`multiprocessing`, or any `signal.SIGTERM` / `signal.SIGINT`
handler that bypasses the bounded-cap exit path.

---

## 13. Stage 29.3 / Stage 29.4 artifact-projection caveats (carried forward as deferred)

Stage 29.3 mode-3 ceremonies and Stage 29.4 mode-3 ceremonies
emit per-event artifact files that show the safe-shape default
projection (`NO_EXTRACTION` / `MISSING`) because the
respective orchestrators pass `extraction=None` /
`price_snapshot=None` / `ath_snapshot=None` to their artifact
writers. These caveats are documented as deferred cleanup
items in Section 12.6 of the Stage 29.3 runbook and Section 13
of the Stage 29.4 runbook.

Stage 29.5 acceptance does NOT depend on those projections
being cleaned up. The authoritative proof axes for every Stage
29.5 dispatched ping remain the Stage 28.9 health-snapshot
counters and the Stage 28.2 dispatch ledger terminal record.
Threading the live extraction and Birdeye price / ATH evidence
and Stage 29.5 migration evidence projection back onto the
per-event mode-3 artifact files is reserved for a separate
operator-gated substage and is explicitly NOT part of Stage
29.5.

---

## 14. Stage 29.5 closed-set vocabularies (summary)

### Migration status

- `PRESENT`
- `MISSING`
- `CONFLICTING`
- `INVALID`
- `STALE`

### Migration source

- `HELIUS_WS`
- `STAGE29_MIGRATION_ARTIFACT`
- `SYNTHETIC_TEST_ONLY`
- `UNKNOWN`

### Migration join status

- `JOINED`
- `NO_MATCH`
- `MULTIPLE_MATCHES`
- `SOURCE_INVALID`
- `TIME_WINDOW_INVALID`
- `PAIR_MISMATCH`

### Measurement status

- `MISSING_MIGRATION`
- `PARTIAL_MIGRATION_PRESENT`
- `COMPLETE`
- `INVALID_MIGRATION`
- `CONFLICTING_MIGRATION`

### Warning codes

- `MIGRATION_MISSING`
- `POST_MIGRATION_ATH_UNVERIFIED`
- `MIGRATION_SOURCE_UNKNOWN`
- `MIGRATION_CONFLICT`
- `MIGRATION_STALE`
- `MIGRATION_TIMESTAMP_INVALID`
- `MIGRATION_PAIR_MISMATCH`
- `MIGRATION_SLOT_MISSING`

### Redaction status

- `SAFE`
- `REDACTED`

### Filter enforcement status (locked)

- `NOT_ACTIVE_STAGE_29_PENDING`

---

## 15. Sanitization discipline

This runbook contains zero URL literals, zero raw API-key
literals, zero webhook host literals, zero raw operator
secrets, zero env-name-paired-with-value entries, and zero
on-chain mint addresses. Every operator-side concrete value
lives in the operator audit log outside the repository.

The Stage 29.5 spec-lock test asserts the absence of URL
literals, secret-shape literals, and raw env-assignment
substrings in this runbook.

---

## 16. Stage 29.5.0 spec-only scope locks

Stage 29.5.0 must not include:

- any production .py file under `PHX2/stage29/` named
  `stage29_5_*.py`
- migration evidence models in runtime form
- Helius WebSocket adapter boundary in runtime form
- migration artifact reader in runtime form
- candidate-to-migration join logic in runtime form
- private ping migration context projection in runtime form
- Stage 29.5 manifest in runtime form
- diagnostic Discord smoke
- scratch sender of any kind
- public routing
- subscriber routing
- paid-tier routing
- Telegram
- X / social
- automated trading
- wallet / private-key / signer logic
- position sizing
- trade execution
- Stage 26 policy enforcement activation
- fake migration timestamps or invented migration slot values
- Dexscreener
- Helius as a price source
- second env-read site (Stage 29.5.0 ships zero env-read
  sites; Stage 29.5.1 admits at most one if the Helius WS
  option ships)

Stage 29.5.0 closed-set vocabularies are names only; Stage
29.5.0 must not ship runtime models, enums, or constants for
these vocabularies.

Stage 29.5.0 explicitly defers Stage 29.5.1 to a separately
authorized operator commit and explicitly defers Stage 29.6+
to future operator authorization.
