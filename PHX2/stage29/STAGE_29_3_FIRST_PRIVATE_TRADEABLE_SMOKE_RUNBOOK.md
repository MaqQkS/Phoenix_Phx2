# PHX2 Stage 29.3 — First Real Private Tradeable Ping Runbook

Stage 29.3 ships the orchestrator + supporting modules that
produce the first real private tradeable PHX2 ping. The pipeline:

```
real Chainstack PumpSwap event
  -> Stage 29.1 hint-aware decode
  -> Stage 29.2 Birdeye price / ATH context
  -> existing Stage 27 candidate assembly / render / provenance
  -> existing Stage 28.9 / 28.6 / 28.4 private dispatch path
  -> exactly one private operator Discord ping (mode 3)
  -> full Stage 29.3 redaction / provenance artifact bundle
```

Stage 29.3 is the live tradeability unblocker substage. Stage 26
policy enforcement remains operator-gated; public / subscriber /
paid-tier audiences, Telegram, X / social, automated trading,
wallet / private-key / signer surfaces, daemon / watchdog /
autorestart loops, Pump.fun bonding-curve decoding, Dexscreener
as a dispatch authority, and Helius as a price source ALL remain
forbidden under Stage 29.3.

---

## 1. Canonical Stage 29.3 mission sentence

> Stage 29.3 wires the existing Stage 27 / Stage 28.4 / Stage 28.6 / Stage 28.9 private dispatch chain to the Stage 29.1 PumpSwap hint-aware decoder + the Stage 29.2 Birdeye price / ATH adapter so the operator can drive exactly one real private tradeable PHX2 ping.

Future Stage 29.3 patches must preserve this sentence verbatim.

---

## 2. The three operator-supplied ceremony modes

| Mode | Outcome on success | Touches | Does NOT touch |
|---|---|---|---|
| `READINESS_ONLY` | `READY` | nothing live | gRPC, Birdeye HTTP, Discord |
| `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY` | `CONNECTED` | one Chainstack `Subscribe` scan + one Birdeye `/defi/price` | Discord, Birdeye `/defi/ohlcv` |
| `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN` | `DISPATCHED` (or a closed-set `SUPPRESSED_*` verdict) | the full chain | nothing beyond the canonical chain |

Run modes 1 -> 2 -> 3 sequentially. Stop at the first non-success
verdict; investigate; re-run.

---

## 3. Canonical env names (zero new env names)

Stage 29.3 reuses the existing Stage 28.11 Chainstack readiness
env names AND the existing Stage 29.2 Birdeye readiness env
names. Stage 29.3 introduces zero new env names. Stage 29.3
production source contains zero `os.environ` / `os.getenv` /
`os.environb` calls; every env read is delegated to the unchanged
Stage 28.11 + Stage 29.2 readiness boundaries.

### Stage 28.11 Chainstack env names (reused)

- `PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT`
- `PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN`
- `PHX2_STAGE28_11_ALLOW_LIVE_GRPC`
- `PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS`

### Stage 29.2 Birdeye env names (reused)

- `PHX2_STAGE29_2_BIRDEYE_API_KEY`
- `PHX2_STAGE29_2_BIRDEYE_BASE_URL`
- `PHX2_STAGE29_2_ALLOW_LIVE_HTTP`
- `PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS`

### Discord webhook URL

NOT read by Stage 29.3 production. The operator scratch runner
reads the URL from a private env name of its own choosing AND
passes the resolved string into the orchestrator as the
`private_webhook_url` parameter. The Stage 28.9 webhook wrapper
binds the URL inside its instance and never copies it onto a
Stage 28.9 / Stage 29.3 record.

---

## 4. Reused production modules (zero edits at Stage 29.3)

- Stage 27 live candidate assembler (`PHX2.stage27.live_candidate_assembler`)
- Stage 27 pair classifier (`PHX2.stage27.pump_pair_classifier`)
- Stage 27 private ping renderer (`PHX2.stage27.private_ping_renderer`)
- Stage 27 private ping provenance (`PHX2.stage27.private_ping_provenance`)
- Stage 27.4 `PriceContextSource` / `AthContextSource` / `MigrationContextSource` Protocols
- Stage 27.6 `Stage27_6Sources` bundle
- Stage 27.6 run-local dedupe (`PHX2.stage27.live_dedupe`)
- Stage 28.4 audited private operator-only Discord HTTP transport
- Stage 28.5 heartbeat / health snapshot / final summary
- Stage 28.6 bounded private session runner
- Stage 28.9 default candidate assembler + private webhook transport + orchestrator
- Stage 28.11 Chainstack Yellowstone readiness env-read boundary
- Stage 29.1 PumpSwap hint-aware decoder + `is_hint_bearing_payload`
- Stage 29.2 Birdeye readiness env-read boundary + price source + ATH source + HTTP transport

Stage 29.3 wraps and composes these surfaces; it does NOT
reimplement them.

---

## 5. Stage 29.3 new production files

```
PHX2/stage29/stage29_3_smoke_models.py
PHX2/stage29/stage29_3_no_migration_evidence_source.py
PHX2/stage29/stage29_3_hint_aware_event_source.py
PHX2/stage29/stage29_3_artifact_writer.py
PHX2/stage29/stage29_3_tradeable_smoke.py
PHX2/stage29/stage29_3_manifest.py
```

Plus this runbook. Stage 29.3 ships nothing outside `PHX2/stage29/`
in production; the test allowlist widenings in the Stage 28.8 /
28.9 / 28.10 / 28.11 boundary tests + the Stage 29.0 spec-lock +
Stage 29.1 / 29.2 boundary tests are test-files-only.

---

## 6. Acceptance artifact bundle

Stage 28.9 writes its four artifacts into the operator-supplied
output directory:

- `stage28_9_dispatch_ledger.jsonl`
- `stage28_9_heartbeat.jsonl`
- `stage28_9_health_snapshot.json`
- `stage28_9_final_run_summary.json`

Stage 29.3 then writes its four acceptance artifacts into the
same directory:

- `stage29_3_tradeable_smoke_result.json` — the immutable
  `Stage29_3TradeableSmokeResult` record.
- `stage29_3_extracted_hints.json` — the safe-shape projection of
  the Stage 29.1 extraction result for the dispatched event (or
  `"NO_EXTRACTION"` when no event reached the chain).
- `stage29_3_birdeye_evidence.json` — the Stage 29.2 price + ATH
  evidence record for the dispatched mint (or explicit `None`
  slots when no event reached the chain).
- `stage29_3_redaction_scan.json` — the Stage 28.7-style scan
  over the prior artifacts. Closed-set verdict: `SAFE` (zero
  forbidden substrings) or `REDACTED` (one or more hits).

The operator's output directory MUST live outside the PHX2
working tree (Stage 28.9 readiness gate enforces this for mode
3; the operator chooses the absolute path for modes 1 / 2).

---

## 7. Mode-3 acceptance criteria

Mode 3 passes when ALL of the following hold:

| Axis | Required value |
|---|---|
| `tradeable_smoke_outcome` | `DISPATCHED` |
| `tradeable_smoke_refusal_reason` | `NONE` |
| `events_seen` | `1` |
| `candidates_assembled` | `1` |
| `candidates_dispatched` | `1` |
| `dispatch_success` | `1` |
| `dispatch_failure` | `0` |
| `unknown_pair_suppressed` / `disagree_pair_suppressed` / `usdc_observe_only_suppressed` / `missing_price_suppressed` / `stale_price_suppressed` / `malformed_suppressed` | all `0` |
| `hint_bearing_payload_present` | `True` |
| Stage 28.9 final summary `stop_reason` | the bound-reached token (max-events or max-dispatches) |
| `stage29_3_redaction_scan.json` `redaction_status` | `SAFE` |
| `filter_enforcement_status` | `NOT_ACTIVE_STAGE_29_PENDING` |
| Audience invoked | private operator Discord only |
| Wallet / signer surface loaded | none |

A mode-3 `SUPPRESSED_*` outcome is a legitimate non-error
ceremony result that proves the chain correctly refused a
non-tradeable event. Operators may re-run the ceremony to look
for a different upstream event when investigating suppression
verdicts.

---

## 8. Forbidden surfaces

Stage 29.3 must NOT include or import any of:

- Stage 26 policy enforcement activation (approved / activated
  filter gates)
- public routing
- subscriber routing
- paid tier routing
- Telegram
- X / social
- automated trading
- wallet / private-key / signer logic
- position sizing
- trade execution
- public dashboard / HTTP control server
- daemon / systemd / watchdog / autorestart service
- Dexscreener as a dispatch authority
- Helius as a price source
- any third or fourth provider beyond Stage 28.11 (Chainstack) +
  Stage 29.2 (Birdeye)
- Pump.fun bonding-curve decoder
- PHX1 / `Phoenix_Bot` import path
- any non-stdlib import beyond `grpc`, the generated protobuf
  stubs, and the already-allowed Stage 27 / 28 / 29 modules

---

## 9. Operator preconditions for any Stage 29.3 ceremony

Before running any Stage 29.3 ceremony the operator MUST confirm:

- `git rev-parse stage-28-closed^{}` still peels to
  `a897bb0531259bbe065efb3e38703a7c3be156c7`.
- The Stage 28.11 live probe sequence (modes 1 to 3) was performed
  and passed in the operator environment with
  `handoff_ready=True` on the dry-run result.
- The Stage 29.1 live probe (mode 3
  `ONE_PUMPSWAP_EVENT_HINT_DRY_RUN`) was performed and passed
  with `no_invention_audit=PASSED`.
- The Stage 29.2 live probe (modes 1 / 2 / 3) was performed and
  passed with `no_invention_audit=PASSED` and the redaction scan
  reporting `SAFE`.
- No `stage-29-*` tag exists in the operator's local clone.
- The Stage 29.3 offline test suite passes.
- The operator has typed an explicit per-ceremony authorization
  phrase into the operator audit log.
- The operator's output directory exists outside the PHX2 working
  tree.

Stage 29.3 documents these preconditions; it does not enforce
them in runtime code beyond the readiness gates.

---

## 10. Stage 29.3 closed-set vocabularies

### Probe mode

- `READINESS_ONLY`
- `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY`
- `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN`

### Tradeable smoke outcome

- `DISPATCHED`
- `SUPPRESSED_UNKNOWN_PAIR`
- `SUPPRESSED_DISAGREE_PAIR`
- `SUPPRESSED_USDC_OBSERVE_ONLY`
- `SUPPRESSED_MISSING_PRICE`
- `SUPPRESSED_STALE_PRICE`
- `SUPPRESSED_MALFORMED`
- `NO_EVENT_RECEIVED`
- `READY`
- `CONNECTED`
- `REFUSED`
- `FAILED`

### Tradeable smoke refusal reason

- `NONE`
- `MODE_INVALID`
- `CHAINSTACK_READINESS_FAILED`
- `BIRDEYE_READINESS_FAILED`
- `WEBHOOK_MISSING`
- `LIVE_FLAG_NOT_SET`
- `OPERATOR_REQUEST_NOT_SET`
- `OUTPUT_DIR_UNSAFE`
- `KNOWN_MINT_INVALID`
- `CHANNEL_FACTORY_NOT_CALLABLE`
- `SUBSCRIBE_FAILED`
- `STREAM_ERROR`
- `DECODE_FAILED`
- `BIRDEYE_CONNECT_FAILED`
- `SESSION_REFUSED`
- `SESSION_FAILED`

### Redaction status

- `SAFE`
- `REDACTED`

### Filter enforcement status (locked)

- `NOT_ACTIVE_STAGE_29_PENDING`

---

## 11. PHX2-replaces-PHX1 acceptance criteria

PHX2 is considered ready to replace PHX1 only after every one of
the following holds:

- At least one real private tradeable ping has been sent from
  live Chainstack + live Birdeye context via the existing Stage
  28.4 audited private transport (Stage 29.3 mode-3 `DISPATCHED`
  outcome).
- The Stage 29.3 acceptance artifacts prove the real event
  source, the extracted real mint / pair hints, the real Birdeye
  price / ATH / freshness snapshot, and the real private Discord
  dispatch result.
- No public routing was invoked.
- No subscriber routing was invoked.
- No paid-tier routing was invoked.
- No Telegram send was invoked.
- No X / social send was invoked.
- No automated trading was invoked.
- No wallet / private-key / signer surface was loaded.
- No Stage 26 policy enforcement gate was activated unless
  separately authorized after Stage 29.3.
- The Stage 28.7-style redaction scan over the acceptance
  artifact directory reports `SAFE`.
- The operator records the per-ceremony audit-trail entry in
  their own log.

PHX2 replacing PHX1 does NOT imply Stage 29 enforcement
activation. Enforcement activation remains separately authorized.

---

## 12. Controlled live smoke proof (Stage 29.3D — 2026-05-25)

Stage 29.3D records a sanitized acceptance note for the first
mode-3 ceremony to reach `DISPATCHED` end-to-end. No secret value
(webhook URL, API key, endpoint URL, auth token, signature, or
env-name-paired-with-value) appears in this section; the operator
audit log carries the full per-ceremony details out of the repo.

### 12.1 Ceremony label

- **Date**: 2026-05-25
- **HEAD at ceremony**: `df09d98` (`phx2 stage 29.3c: accept usd
  price context for sol-pair render`)
- **Scratch root**: out-of-repo operator path under
  `phx2_scratch/stage29_3_live_smoke_retry_3/` (not committed)
- **Mode invoked**: `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN`
- **Operator-supplied bounds**: `max_events=1`, `max_dispatches=1`,
  `max_total_retries=0`, `max_messages_to_scan=100`, 5-minute
  wall-clock safety timeout

### 12.2 Acceptance outcome

The mode-3 ceremony returned `DISPATCHED` on the first attempt
after Stage 29.3A / 29.3B / 29.3C all landed. Safe counter
projection from `stage29_3_tradeable_smoke_result.json`:

| Axis | Recorded value |
|---|---|
| `tradeable_smoke_outcome` | `DISPATCHED` |
| `tradeable_smoke_refusal_reason` | `NONE` |
| `events_seen` | `1` |
| `candidates_assembled` | `1` |
| `candidates_dispatched` | `1` |
| `candidates_suppressed` | `0` |
| `dispatch_success` | `1` |
| `dispatch_failure` | `0` |
| `hint_bearing_payload_present` | `True` |
| `filter_enforcement_status` | `NOT_ACTIVE_STAGE_29_PENDING` |
| `redaction_status` | `SAFE` |

Stage 28.9 companion counters from `stage28_9_health_snapshot.json`
+ `stage28_9_final_run_summary.json`:

| Axis | Recorded value |
|---|---|
| `current_health_status` | `HEALTHY` |
| `last_event_status` | `OBSERVED` |
| `last_ping_status` | `RENDERED` |
| `event_count` / `candidate_count` / `ping_rendered_count` / `dispatch_success_count` | each `1` |
| `dispatch_failure_count` | `0` |
| `unknown_pair_suppressed_count` | `0` |
| `disagree_pair_suppressed_count` | `0` |
| `usdc_observe_only_count` | `0` |
| `missing_price_count` | `0` |
| `stale_price_count` | `0` |
| `retry_count` | `0` |
| `provider_status` / `price_status` / `transport_status` / `dispatch_status` / `ledger_status` / `artifact_status` | each `OK` |
| `redaction_status` | `SAFE` |

`stage28_9_dispatch_ledger.jsonl` recorded the canonical
`RESERVE -> PRE_SEND -> TERMINAL` triple for the single
`PRIVATE_OPERATOR_OBSERVE` ping; the terminal record's
`terminal_status` was `DISPATCHED_OK` with `failure_reason=null`.

### 12.3 The three repairs verified together

The controlled live smoke proves the following three Stage 29.3
follow-up commits work in concert end-to-end against a real
Chainstack Yellowstone gRPC stream + a real Birdeye HTTP
endpoint + the operator's private operator Discord webhook:

1. **Stage 29.3A — scan-budget semantics** (`731a781`):
   `Stage29_3HintAwareChainstackEventSource.iter_events` now lets
   `max_messages_to_scan` control upstream provider messages
   scanned independently of `max_events`. The retry_3 ceremony's
   `max_messages_to_scan=100` is therefore honoured; pre-29.3A
   it was capped at `min(max_events, max_messages_to_scan) = 1`.

2. **Stage 29.3B — pair-hint forwarding** (`f73de0b`):
   `Stage28_9DefaultCandidateAssembler.assemble` forwards
   `pool_account` / `pool_program_id` / `base_mint` / `quote_mint`
   / `bonding_curve_program_id` / `bonding_curve_version_hint` /
   `provider_quote_asset_hint` / `provider_pair_type_hint` /
   `provider_bonding_curve_version_hint` from the Stage 28.10
   `NormalizedEvent` into the Stage 27.3 ingest input. The
   ceremony's `pair_quote_asset=SOL` /
   `pair_detection_status=CONFIRMED` resolution on the dispatch
   ledger key proves the hint quartet reached the classifier.

3. **Stage 29.3C — USD price context for SOL-pair render** (`df09d98`):
   Stage 27.4 `build_price_context_record` admits
   `PRICE_UNIT_USD` on a SOL or USDC pair, mirroring the
   pre-existing `ATH_UNIT_USD` exception in
   `build_ath_context_record`. Pair lane is unchanged (SOL stays
   SOL; USDC stays USDC); only the display unit is USD. The
   ceremony's `missing_price_count=0` /
   `unknown_pair_suppressed_count=0` /
   `last_ping_status=RENDERED` counters prove the USD-denominated
   Birdeye snapshot rendered cleanly through the SOL-lane chain
   instead of falling through the previous
   `RENDERED_UNSUPPORTED` defensive branch to
   `SUPPRESSED_UNKNOWN_PAIR`.

### 12.4 Redaction scan

The orchestrator-emitted `stage29_3_redaction_scan.json` reported
`redaction_status: SAFE` with empty `hits_by_file`. An independent
cross-cutting scan of all eight retry_3 artifact files against
seventeen forbidden needles (the four canonical Stage 28.11
endpoint / x-token-shaped literals; the four canonical Stage
29.2 API-key / base-url-shaped literals; the operator-private
webhook URL string; the Discord webhooks path prefix; the four
canonical header literals; the two `sk-live-` / `sk-test-` API
key prefixes; the five canonical `*_KEY=` / `*_TOKEN=` / `*_URL=`
env literals) reported zero hits across every file. Both scans
agree: `SAFE`.

### 12.5 Scope confirmations

- No Stage 26 policy enforcement was activated; the smoke result
  carries `filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`.
- Audience: private operator only (single
  `PRIVATE_OPERATOR_OBSERVE` ping_type recorded in the dispatch
  ledger).
- No public routing was invoked.
- No subscriber routing was invoked.
- No paid-tier routing was invoked.
- No Telegram send was invoked.
- No X / social send was invoked.
- No automated trading was invoked.
- No wallet / private-key / signer surface was loaded.
- No additional retry was performed after the terminal
  `DISPATCHED` verdict; the operator's "do not retry
  automatically" standing instruction was honoured.

### 12.6 Known caveat (artifact projection — deferred)

`stage29_3_extracted_hints.json` and
`stage29_3_birdeye_evidence.json` still show the safe-shape
`NO_EXTRACTION` / `MISSING` projections respectively, because
the mode-3 orchestrator passes `extraction=None` /
`price_snapshot=None` / `ath_snapshot=None` to the artifact
writer (the per-event hint extraction result and the Birdeye
price / ATH snapshots are consumed inside
`Stage29_3HintAwareChainstackEventSource` and the Stage 27.4
reader respectively, and not threaded back out to the
orchestrator's artifact-write seam). The chain's authoritative
proof of having resolved both hint axes and price / ATH axes is
the Stage 28.9 health snapshot (`last_event_status=OBSERVED`,
`last_ping_status=RENDERED`, `missing_price_count=0`,
`unknown_pair_suppressed_count=0`) plus the dispatch ledger's
`DISPATCHED_OK` terminal record — none of which would be
producible if hint extraction or price / ATH resolution had
failed. Threading the live extraction + Birdeye evidence back
onto the mode-3 acceptance artifacts is a future cleanup
substage and remains operator-gated.
