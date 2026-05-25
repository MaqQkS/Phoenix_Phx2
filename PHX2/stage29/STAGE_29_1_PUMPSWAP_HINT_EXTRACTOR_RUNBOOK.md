# PHX2 Stage 29.1 — PumpSwap Hint Extractor Operator Runbook

Stage 29.1 ships the post-migration PumpSwap-only hint
extractor authorized under Option A of the Stage 29.1 plan. It
turns real Chainstack Yellowstone PumpSwap transaction evidence
into Stage 28.10 payloads with non-None hint fields so the
existing Stage 27 candidate chain can produce ASSEMBLED
candidates instead of suppressing them as UNKNOWN_PAIR.

Stage 29.1 ships NO Discord send, NO diagnostic Discord smoke,
NO Birdeye adapter, NO Dexscreener, NO Helius, NO Telegram, NO
X / social, NO automated trading, NO wallet / private-key /
signer logic, NO position sizing, NO trade execution, NO public
/ subscriber / paid-tier routing, NO Stage 26 enforcement
activation, NO Stage 28.9 wrapper invocation, NO Stage 28.6
bounded runner invocation, NO Stage 28.4 audited transport
invocation, NO Pump.fun bonding-curve decoder, and NO Pump.fun
bonding-curve program id constant. Pump.fun bonding-curve
coverage is deferred to a future explicitly-authorized substage
that lands the bonding-curve Anchor IDL first.

---

## 1. Stage 29.1 scope sentence

Stage 29.1 is the PumpSwap hint extractor for PHX2. Real
Chainstack Yellowstone PumpSwap transaction evidence in,
non-None `base_mint` / `pool_account` / `quote_mint` /
`pool_program_id` / `provider_pair_type_hint` /
`provider_quote_asset_hint` hints on the Stage 28.10 payload
record out, closed-set `no_evidence_reason` token when the
evidence is insufficient, and never an invented hint.

---

## 2. Canonical Stage 28.11 env names (Stage 29.1 reuses these)

Stage 29.1 introduces NO new env-read site. The unchanged
Stage 28.11 readiness boundary
(`PHX2/stage28/chainstack_yellowstone_grpc_readiness.py`)
remains the single env-read surface for the Stage 28.11 +
Stage 29.1 chain. The four canonical env names are:

| Name | Purpose |
|---|---|
| `PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT` | Raw gRPC endpoint (host:port; TLS required). Lives only on the private endpoint-secret subobject. |
| `PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN` | Raw Chainstack x-token. Lives only on the private endpoint-secret subobject. |
| `PHX2_STAGE28_11_ALLOW_LIVE_GRPC` | Must be exactly `"1"` to enable the Stage 29.1 live probe. |
| `PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS` | Optional; integer in `[1, 600]`. Defaults to `30`. |

The following env names are NOT used at any point in Stage 29.1
(or anywhere in the PHX2 tree) and are flagged for the
operator's awareness:

- `PHX2_STAGE28_11_GRPC_LIVE_ALLOW` (wrong; the correct name is
  `PHX2_STAGE28_11_ALLOW_LIVE_GRPC`).
- `PHX2_STAGE28_11_GRPC_ENDPOINT` (wrong; the correct name is
  `PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT`).
- `PHX2_STAGE28_11_GRPC_X_TOKEN` (wrong; the correct name is
  `PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN`).

---

## 3. Stage 29.1 file inventory

Production files under `PHX2/stage29/`:

- `pumpswap_program_constants.py` — PumpSwap program id, known
  quote mints, SPL Token / Token-2022 program ids, PumpSwap
  Anchor BuyEvent / SellEvent event discriminators, vendored
  IDL provenance pins.
- `pumpswap_hint_models.py` — closed-set
  `hint_extraction_outcome` / `no_evidence_reason` /
  `pool_account_evidence_source` /
  `quote_mint_evidence_source` vocabularies + the immutable
  `Stage29_1PumpSwapHintExtractionResult` record + the
  `Stage29_1PumpSwapHintExtractorError` exception.
- `pumpswap_hint_extractor.py` — pure function
  `extract_pumpswap_hints(update)` implementing the
  token-balance owner-grouping rule.
- `pumpswap_hint_aware_decoder.py` — thin composition layer
  that calls the unchanged Stage 28.11 baseline decoder + the
  Stage 29.1 extractor and rebuilds a hint-populated Stage
  28.10 payload.
- `stage29_1_hint_probe_models.py` — closed-set probe mode /
  status / refusal-reason vocabularies + the immutable
  `Stage29_1HintProbeResult` record + the
  `Stage29_1HintProbeError` exception.
- `stage29_1_pumpswap_hint_probe.py` — the live probe
  orchestrator (the single Stage 29.1 production file allowed
  to import `grpc` and the generated Yellowstone protobuf
  stubs).
- `stage29_1_manifest.py` — constants-only re-export manifest
  for boundary tests.

Vendored sources under `PHX2/proto/stage29_1/source/`:

- `PHX2/proto/stage29_1/source/pump_amm.json` — vendored copy
  of the public Pump AMM Anchor IDL (program address
  `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`). Provenance:
  this is the public Anchor IDL the program publishes on
  mainnet; it is not a PHX1 artifact (PHX1 happens to vendor
  the same public IDL). The file SHA-256 is pinned in
  `pumpswap_program_constants.VENDORED_PUMP_AMM_IDL_SHA256`
  and `test_stage_29_1_vendored_idl.py` pins it.

Operator runbook + this doc:

- `STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md` (this
  file).

Test files under `PHX2/tests/stage29/`:

- `test_stage_29_1_pumpswap_program_constants.py`
- `test_stage_29_1_pumpswap_hint_models.py`
- `test_stage_29_1_pumpswap_hint_extractor.py`
- `test_stage_29_1_pumpswap_hint_aware_decoder.py`
- `test_stage_29_1_hint_probe_models.py`
- `test_stage_29_1_pumpswap_hint_probe.py`
- `test_stage_29_1_runbook.py`
- `test_stage_29_1_boundaries.py`
- `test_stage_29_1_vendored_idl.py`

---

## 4. Token-balance owner-grouping extraction rule

The Stage 29.1 hint extractor implements a single deterministic
rule:

1. The upstream `SubscribeUpdate` must carry a `transaction`
   oneof. Non-transaction variants (ping / pong / slot / block
   / block_meta / entry / account / transaction_status) yield
   `NO_EVIDENCE_REASON_UPDATE_NOT_TRANSACTION`.
2. Vote transactions yield
   `NO_EVIDENCE_REASON_TRANSACTION_IS_VOTE_SKIPPED`.
3. The transaction's `meta` field must be present; missing
   yields `NO_EVIDENCE_REASON_META_MISSING`.
4. Failed transactions (`meta.err` set) yield
   `NO_EVIDENCE_REASON_TRANSACTION_FAILED_PER_META_ERR` — the
   extractor refuses to mine hints from a failed swap.
5. The extractor walks `meta.pre_token_balances +
   meta.post_token_balances`, filters to entries whose
   `program_id` is the SPL Token or SPL Token-2022 program
   (the only two SPL token programs Stage 29.1 considers), and
   groups by the `owner` string.
6. For each owner the extractor computes:
   - the subset of known quote mints the owner holds (closed
     set: `So111...112` for SOL, `EPjF...t1v` for USDC),
   - the subset of non-quote mints the owner holds.
7. An owner is a pool candidate iff it holds exactly ONE
   known quote mint AND exactly ONE non-quote mint. Owners
   holding multiple non-quote mints are recorded for the
   `NO_EVIDENCE_REASON_POOL_OWNER_HAS_MULTIPLE_NON_QUOTE_MINTS`
   refusal path.
8. If exactly one pool candidate exists, the extractor
   populates the four-axis hint quartet (`base_mint` = the
   non-quote mint, `pool_account` = the owner, `quote_mint` =
   the known quote mint, `pool_program_id` = the PumpSwap
   program id) plus `provider_pair_type_hint` /
   `provider_quote_asset_hint` derived from the quote mint via
   the closed-set lookup. Outcome:
   `HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED`.
9. If zero pool candidates exist after step 7, the extractor
   returns
   `NO_EVIDENCE_REASON_NO_POOL_OWNER_WITH_BOTH_QUOTE_AND_BASE`
   (or the multi-non-quote variant when applicable).
10. If two or more pool candidates exist, the extractor
    returns
    `NO_EVIDENCE_REASON_POOL_OWNER_AMBIGUOUS_MULTIPLE_MATCHES`.

The rule consumes only protobuf fields the Stage 28.11
generated stubs expose at type `string` (`TokenBalance.mint`,
`TokenBalance.owner`, `TokenBalance.program_id`). It does NOT
base58-encode raw account-key bytes, does NOT parse Anchor
instruction data, does NOT decode Anchor event logs, and does
NOT consult any Anchor IDL at runtime.

The `bonding_curve_version_hint` slot stays `None` at Stage
29.1 because PumpSwap is the post-migration AMM; bonding-curve
version is a pre-migration axis owned by the deferred Pump.fun
bonding-curve substage.

---

## 5. Stage 29.1 live probe — offline-tested entry point

```python
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    build_runtime_config_from_env,
)
from PHX2.stage29.stage29_1_hint_probe_models import (
    PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
)
from PHX2.stage29.stage29_1_pumpswap_hint_probe import (
    run_stage29_1_pumpswap_hint_probe,
)

runtime_config = build_runtime_config_from_env(
    mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
)

result = run_stage29_1_pumpswap_hint_probe(
    runtime_config=runtime_config,
    mode=PROBE_MODE_ONE_PUMPSWAP_EVENT_HINT_DRY_RUN,
    live_flag_set=True,
    max_messages_to_scan=64,
    channel_factory=None,
)
```

The operator sets the four canonical Stage 28.11 env names
listed in §2 BEFORE invoking the probe. The probe NEVER reads
`os.environ` itself; the Stage 28.11 readiness layer is the
single env-read site.

Expected success shape on a healthy mainnet PumpSwap stream:

```
mode = "ONE_PUMPSWAP_EVENT_HINT_DRY_RUN"
status = "DECODED_WITH_HINTS"
refusal_reason = "NONE"
hint_bearing_payload.base_mint = <base58 string>
hint_bearing_payload.pool_account = <base58 string>
hint_bearing_payload.quote_mint = "So11...112" or "EPjF...t1v"
hint_bearing_payload.pool_program_id =
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
hint_bearing_payload.provider_pair_type_hint =
    "PUMP_SOL" or "PUMP_USDC"
hint_bearing_payload.provider_quote_asset_hint =
    "SOL" or "USDC"
hint_bearing_payload.bonding_curve_version_hint = None
extraction_result.outcome = "HINTS_EXTRACTED"
extraction_result.no_evidence_reason = "NONE"
handoff_ready = True
events_scanned ≤ 64
```

---

## 6. Stage 29.1 must-not surfaces (operator audit)

- NO Discord send (audited or otherwise).
- NO diagnostic Discord smoke.
- NO Birdeye adapter implementation.
- NO Dexscreener integration.
- NO Helius integration.
- NO Telegram send.
- NO X / social send.
- NO automated trading.
- NO wallet / private-key / signer logic.
- NO position sizing.
- NO trade execution.
- NO public routing.
- NO subscriber routing.
- NO paid tier routing.
- NO Stage 26 enforcement activation.
- NO Stage 28.9 wrapper invocation in Stage 29.1.
- NO Stage 28.6 bounded runner invocation in Stage 29.1.
- NO Stage 28.4 audited transport invocation in Stage 29.1.
- NO Pump.fun bonding-curve decoder.
- NO Pump.fun bonding-curve program id constant.
- NO Stage 29.2 Birdeye adapter implementation.
- NO Stage 29.3 tradeable Discord smoke.
- NO PHX1 import path. The token-balance owner-grouping rule
  is independently re-implemented from the Stage 29.1 spec;
  PHX1 served only as design evidence that the rule is
  well-bounded.

---

## 7. Stage 29.1 closure preconditions

Before any operator considers Stage 29.1 closed:

- The Stage 28.11 closure tag `stage-28-closed` still peels
  to `a897bb0531259bbe065efb3e38703a7c3be156c7`.
- All Stage 29.1 offline tests pass via:
  ```
  .\.venv\Scripts\python.exe -B -m pytest PHX2/tests/stage29 -q
      -p no:cacheprovider --basetemp=PHX2/.pytest_tmp
  ```
- The unchanged Stage 28.11 + Stage 28.10 test suites pass:
  ```
  .\.venv\Scripts\python.exe -B -m pytest
      PHX2/tests/stage28/test_stage_28_11_*.py
      -q -p no:cacheprovider --basetemp=PHX2/.pytest_tmp
  .\.venv\Scripts\python.exe -B -m pytest
      PHX2/tests/stage28/test_stage_28_10_*.py
      -q -p no:cacheprovider --basetemp=PHX2/.pytest_tmp
  ```
- The Stage 29.1 live probe sequence is operator-eligible
  (operator decision; not part of Stage 29.1 offline
  closure). Live probe is not required for Stage 29.1
  offline-test pass.
- The operator does the commit / tag / push manually after
  closure-audit review. Stage 29.1 implementation itself does
  not commit, tag, or push.

---

## 8. What remains for Stage 29.2 and beyond

- **Stage 29.2** — real Birdeye live price / ATH adapter for
  known mints. Stage 29.2 will own its own Stage-29.2-pinned
  env-read boundary (`PHX2_STAGE29_2_BIRDEYE_*`) and
  implement the Stage 27.4 `PriceContextSource` /
  `AthContextSource` Protocols. NOT shipped at Stage 29.1.
- **Stage 29.3** — first real private tradeable Discord smoke
  with `max_events=1` / `max_dispatches=1` against the
  unchanged Stage 28.4 audited private transport. NOT shipped
  at Stage 29.1.
- **Pump.fun bonding-curve substage** — separately authorized
  Stage 29.1 follow-up that lands the Pump.fun bonding-curve
  Anchor IDL into `PHX2/proto/stage29_1/source/` (or a
  Stage-29.1-bonding-curve-pinned directory) and adds
  `instruction_kind = PUMP_CREATE` / `PUMP_MIGRATION` /
  bonding-curve account-position extraction. NOT shipped at
  Stage 29.1.
