# Stage 29.5.2 — Offline integration proof runbook

## Canonical Stage 29.5.2 mission sentence

Stage 29.5.2 is the offline integration proof substage that
composes the existing Stage 29.5 candidate-to-migration join
layer and the Stage 29.5 private ping migration context
projection over a Stage 29.3-shaped candidate axes record plus a
Stage 27.4 ATH context record, using purely synthetic migration
evidence and a deterministic clock, so that the Stage 29.5 join +
projection are proven to compose cleanly without opening any live
WebSocket / gRPC / HTTP transport and without wiring the
composition into the Stage 29.3 mode-3 orchestrator or the Stage
29.4 short-session private soak orchestrator.

## What Stage 29.5.2 ships

Production:

* `PHX2/stage29/stage29_5_2_offline_integration.py` — the pure
  composition function `run_stage29_5_2_offline_integration` and
  the immutable result record
  `Stage29_5_2OfflineIntegrationResult`.
* `PHX2/stage29/stage29_5_2_synthetic_evidence_fixtures.py` —
  pure builders that emit PRESENT / MISSING / INVALID /
  CONFLICTING / STALE synthetic
  `Stage29_5MigrationEvidenceRecord` instances. This is the
  sole authorized site for the closed-set
  `MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY` Stage 29.5 token.
* `PHX2/stage29/stage29_5_2_manifest.py` — constants-only
  manifest pinning the Stage 29.5.2 production / doc / test
  inventories and the zero-env-read + zero-outbound-network
  admissions.

Doc:

* `PHX2/stage29/STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md`
  (this file).

Tests:

* `PHX2/tests/stage29/test_stage_29_5_2_offline_integration.py`
* `PHX2/tests/stage29/test_stage_29_5_2_boundaries.py`
* `PHX2/tests/stage29/test_stage_29_5_2_no_integration_into_stage_29_3.py`
* `PHX2/tests/stage29/test_stage_29_5_2_manifest.py`
* `PHX2/tests/stage29/test_stage_29_5_2_spec_lock.py`

## What Stage 29.5.2 does NOT ship

Stage 29.5.2 ships NO live network call, NO live Helius
WebSocket, NO live Chainstack Yellowstone gRPC, NO live Birdeye
HTTP, NO real `websockets` / `websocket-client` / `aiohttp` /
`socket` / `grpc` import, NO outbound HTTP, NO outbound gRPC, NO
Discord send, NO Telegram, NO X / social, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO public / subscriber / paid-tier routing, NO
Stage 26 enforcement activation, NO Stage 28.9 wrapper
invocation, NO Stage 28.6 bounded runner invocation, NO Stage
28.4 audited transport invocation, NO Pump.fun bonding-curve
decoder, NO Dexscreener, NO Helius as a price source, NO PHX1
import path, NO new env name, NO new third-party runtime
dependency, NO Stage 29.6+ implementation.

Stage 29.5.2 also explicitly defers:

* a Stage 29.4 pass-entrypoint wrapper that drives the
  composition per soak pass and writes a side-channel artifact —
  deferred to Stage 29.5.3.
* a runtime wiring of the Stage 29.5 projection into the Stage
  29.3 mode-3 orchestrator — the existing Stage 29.5 boundary
  test pin
  `test_stage29_3_mode3_uses_stage29_5_projection_or_explicitly_marks_not_integrated`
  remains green at Stage 29.5.2; the Stage 29.3 orchestrator
  continues to inject `Stage29_3NoMigrationEvidenceSource` and
  does NOT consume the Stage 29.5 projection at runtime.

## Composition data flow

```
        synthetic Stage29_5MigrationEvidenceRecord[*]
                       (test fixtures only; source=SYNTHETIC_TEST_ONLY
                        or source=UNKNOWN for the MISSING variant)
                                  |
        Stage29_5CandidateAxes
            (base_mint required; pool_account / pool_program_id /
             quote_mint optional and wildcarded when None)
                                  |
                                  v
        join_candidate_to_migration_evidence(
            candidate_axes, evidence, clock, window_start?,
            window_end?, expected_pool_program_id?)
                                  |
                                  v  Stage29_5MigrationJoinRecord
                                  |  (closed-set migration_join_status:
                                  |   JOINED / NO_MATCH /
                                  |   MULTIPLE_MATCHES / SOURCE_INVALID /
                                  |   TIME_WINDOW_INVALID / PAIR_MISMATCH)
                                  |
        AthContextRecord
            (synthetic Stage 27.4 NamedTuple; same-token or
             wrong-token; PRESENT / MISSING / UNKNOWN)
                                  |
                                  v
        project_private_ping_migration_context(
            join_record, ath_context, clock)
                                  |
                                  v  Stage29_5PrivatePingMigrationContext
                                  |  (closed-set measurement_status:
                                  |   COMPLETE / PARTIAL_MIGRATION_PRESENT /
                                  |   MISSING_MIGRATION /
                                  |   INVALID_MIGRATION /
                                  |   CONFLICTING_MIGRATION;
                                  |   filter_enforcement_status locked
                                  |   to NOT_ACTIVE_STAGE_29_PENDING)
                                  v
        Stage29_5_2OfflineIntegrationResult(
            candidate_axes_echoed,
            join_record,
            private_ping_context,
            filter_enforcement_status="NOT_ACTIVE_STAGE_29_PENDING",
            redaction_status="SAFE",
            schema_version="stage29_5_2_v0_offline_integration")
```

The composition is **pure** — same inputs => same output. The
Stage 29.5 join is itself pure (no env, no network, no file
I/O); the Stage 29.5 projection is itself pure; the Stage
29.5.2 composition layer is a thin wrapper that re-emits the
join verdict and the projection alongside an audit echo of the
candidate axes.

## Why a separate Stage 29.5.2 inventory

Three hard constraints make a separate inventory the only safe
option at Stage 29.5.2:

1. The Stage 29.5 boundary scan (PHX2/tests/stage29/test_stage_29_5_boundaries.py)
   pins the Stage 29.5 production inventory at exactly six
   files. Adding the composition to that tuple would also
   require relaxing the Stage 29.5 sibling-import guard, which
   forbids any Stage 29.5 production file from importing any
   sibling Stage 29 surface.
2. The Stage 29.5 boundary scan pins that the Stage 29.3 mode-3
   orchestrator file `stage29_3_tradeable_smoke.py` neither
   imports any Stage 29.5 module nor references any Stage 29.5
   identifier; that pin is what marks the "deferred runtime
   integration" state, and it must survive Stage 29.5.2 without
   modification.
3. The locked Stage 29.5 manifest tuples
   (`STAGE29_5_PRODUCTION_PY_BASENAMES`,
   `STAGE29_5_DOC_BASENAMES`, `STAGE29_5_TEST_BASENAMES`,
   `STAGE29_5_ENV_READ_ADMITTED_BASENAMES`,
   `STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES`) are pinned
   by a dedicated manifest test
   (`test_stage_29_5_manifest.py`). Those pins must survive
   Stage 29.5.2.

## Stage 29.5.2 acceptance criteria

A. Stage 29.5.2 production / doc / test inventories exist on
   disk and match the
   `STAGE29_5_2_PRODUCTION_PY_BASENAMES` /
   `STAGE29_5_2_DOC_BASENAMES` /
   `STAGE29_5_2_TEST_BASENAMES` tuples in
   `stage29_5_2_manifest.py`.

B. Stage 29.5.2 admits ZERO env-read sites
   (`STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES == ()`).

C. Stage 29.5.2 admits ZERO outbound-network sites
   (`STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()`).

D. Stage 29.5.2 production imports zero Stage 21..26 module,
   zero PHX1 / Phoenix_Bot module, zero Stage 28 module, zero
   Stage 29.1 / 29.2 / 29.3 / 29.4 module, and zero forbidden
   runtime library (`solders` / `solana` / `construct` /
   `base58` / `helius` / `jupiter` / `discord` / `telegram` /
   `telethon` / `webhook_client` / `apscheduler` / `celery` /
   `schedule` / `crontab` / `sqlalchemy` / `sqlite3` /
   `dotenv` / `keyring` / `tweepy` / `twitter` / `threading` /
   `multiprocessing` / `subprocess` / `queue` / `sched` /
   `dexscreener` / `signal`).

E. Stage 29.5.2 production source carries NO URL host literal,
   NO raw-secret-looking literal, NO Pump.fun bonding-curve
   program id literal.

F. The bare string literal `"SYNTHETIC_TEST_ONLY"` (or its
   single-quoted equivalent) appears in
   `stage29_5_2_synthetic_evidence_fixtures.py` only as a
   *symbolic* reference (via the imported Stage 29.5 constant
   `MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY`); the composition
   module and the manifest must not carry the bare literal.

G. Every emitted
   `Stage29_5_2OfflineIntegrationResult.filter_enforcement_status`
   equals the locked Stage 29.5 token
   `NOT_ACTIVE_STAGE_29_PENDING`.

H. Stage 29.5.2 production contains NO top-level Call (no
   implicit I/O at import time).

I. The Stage 29.3 mode-3 orchestrator file
   `stage29_3_tradeable_smoke.py` continues to inject
   `Stage29_3NoMigrationEvidenceSource` and imports no
   `stage29_5*` module (including `stage29_5_2*`); the Stage
   29.4 soak orchestrator file `stage29_4_soak_orchestrator.py`
   imports no `stage29_5*` module (including `stage29_5_2*`).

J. The Stage 29.5 manifest production inventory remains
   exactly the six-file tuple
   (`stage29_5_migration_models.py`,
   `stage29_5_helius_ws_adapter.py`,
   `stage29_5_migration_artifact_reader.py`,
   `stage29_5_candidate_to_migration_join.py`,
   `stage29_5_private_ping_context_projection.py`,
   `stage29_5_manifest.py`).

## Stage 29.5.2 behavior test matrix (offline only)

| Branch | Inputs | Expected verdict |
|---|---|---|
| Happy path COMPLETE projection | 1 synthetic PRESENT evidence with quartet + slot present + source SYNTHETIC_TEST_ONLY; ATH context PRESENT same-token POST_MIGRATION_ONLY observed strictly after migration timestamp | join=JOINED, measurement=COMPLETE, post_migration_ath_verified=True, warnings=() |
| Missing migration evidence | empty evidence sequence | join=NO_MATCH, measurement=MISSING_MIGRATION, warnings include MIGRATION_MISSING + POST_MIGRATION_ATH_UNVERIFIED, verified=None |
| Invalid migration evidence | 1 synthetic INVALID evidence matching candidate axes | join=SOURCE_INVALID, measurement=INVALID_MIGRATION, warnings include MIGRATION_TIMESTAMP_INVALID + POST_MIGRATION_ATH_UNVERIFIED |
| Conflicting migration evidence | 2 synthetic PRESENT evidence with quartet but disagreeing on `migration_timestamp_utc` | join=MULTIPLE_MATCHES, measurement=CONFLICTING_MIGRATION, warnings include MIGRATION_CONFLICT + POST_MIGRATION_ATH_UNVERIFIED |
| Stale / out-of-window migration evidence | 1 synthetic STALE evidence (status=STALE) matching candidate | join=TIME_WINDOW_INVALID, measurement=PARTIAL_MIGRATION_PRESENT, warnings include MIGRATION_STALE + POST_MIGRATION_ATH_UNVERIFIED, verified=None |
| Wrong-token ATH stays PARTIAL with verified=None | 1 PRESENT evidence for token A; ATH context PRESENT but token_mint=B | join=JOINED, measurement=PARTIAL_MIGRATION_PRESENT, verified=None (NOT False), warnings include POST_MIGRATION_ATH_UNVERIFIED |
| Pair mismatch via expected_pool_program_id | 1 PRESENT evidence with `pool_program_id=X`; caller supplies `expected_pool_program_id=Y` | join=PAIR_MISMATCH, measurement=INVALID_MIGRATION, warnings include MIGRATION_PAIR_MISMATCH + POST_MIGRATION_ATH_UNVERIFIED |
| Slot missing blocks COMPLETE | 1 PRESENT evidence with `migration_slot=None`; same-token POST_MIGRATION_ONLY ATH | join=JOINED, measurement=PARTIAL_MIGRATION_PRESENT, warnings include MIGRATION_SLOT_MISSING + POST_MIGRATION_ATH_UNVERIFIED, verified=None |

## Stage 29.5.3 (deferred)

Stage 29.5.3 will introduce a Stage 29.4 pass-entrypoint wrapper
that runs the Stage 29.5.2 composition over the per-pass
candidate axes and writes a side-channel artifact, without
modifying the Stage 29.4 pass-result envelope and without
changing dispatch semantics. That work is explicitly out of
scope for Stage 29.5.2.

A subsequent substage (separately authorized) will introduce
the runtime wiring of the Stage 29.5 projection into the Stage
29.3 mode-3 orchestrator. Flipping the Stage 29.5 boundary test
pin
`test_stage29_3_mode3_uses_stage29_5_projection_or_explicitly_marks_not_integrated`
from the "not yet integrated" branch to the "imports the
projection" branch is reserved for that substage; Stage 29.5.2
does not touch the pin.
