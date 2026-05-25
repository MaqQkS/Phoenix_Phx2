# PHX2 Stage 29.2 — Birdeye live price / ATH adapter — operator runbook

Stage 29.2 wires a real Birdeye-backed implementation of the
existing Stage 27.4 `PriceContextSource` / `AthContextSource`
Protocols + a Stage-29.2-pinned live probe that turns a known
Stage 29.1 `base_mint` into a (price, ATH, drawdown, freshness)
evidence record consumable by Stage 29.3.

Stage 29.2 ships NO Discord send, NO Telegram, NO X / social, NO
trading, NO wallet / signer, NO public / subscriber / paid
routing, NO Stage 26 enforcement activation, NO Pump.fun
bonding-curve decoder, NO Dexscreener fallback, NO Helius, NO
Stage 29.3 tradeable smoke.

---

## 1. Stage 29.2 inventory pins

Production source (under `PHX2/stage29/`):

- `birdeye_constants.py` — endpoint paths, header names, OHLCV
  resolution closed set, default lookback / timeout, safe-shape
  validators.
- `stage29_2_birdeye_models.py` — closed-set vocabularies, the
  Stage 29.2 snapshot + evidence dataclasses, module-local
  `Stage29_2BirdeyeError`.
- `stage29_2_birdeye_readiness.py` — the SOLE Stage 29.2
  env-read site. Reads exactly four locked env names.
- `stage29_2_birdeye_http_transport.py` — the SOLE Stage 29.2
  outbound-HTTP site (stdlib `urllib.request` only).
- `stage29_2_birdeye_price_source.py` — the Stage 27.4
  `PriceContextSource` Protocol implementation backed by
  Birdeye `GET /defi/price`.
- `stage29_2_birdeye_ath_source.py` — the Stage 27.4
  `AthContextSource` Protocol implementation backed by Birdeye
  `GET /defi/ohlcv` (ATH from `max(items[].h)` candle highs).
- `stage29_2_birdeye_probe_models.py` — closed-set probe
  mode / status sets + `Stage29_2BirdeyeHintProbeResult`.
- `stage29_2_birdeye_probe.py` — the SOLE Stage 29.2 live
  probe orchestrator.
- `stage29_2_manifest.py` — constants-only re-export + pinned
  inventories + forbidden-surfaces tuple.

Documentation:

- `STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md` (this document).

Tests live at `PHX2/tests/stage29/test_stage_29_2_*.py`.

---

## 2. Canonical Stage 29.2 env names

Stage 29.2 reads exactly four env names through the readiness
boundary at `stage29_2_birdeye_readiness.py`:

| Env name | Purpose |
|---|---|
| `PHX2_STAGE29_2_BIRDEYE_API_KEY` | Birdeye `X-API-KEY` header value. Safe-shape ASCII; length-bound `[16, 256]`; alphanumeric + `_` + `-` only. |
| `PHX2_STAGE29_2_BIRDEYE_BASE_URL` | Birdeye HTTPS base URL. MUST start `https://`, no trailing slash, length-bound `[12, 256]`, alphanumeric + `.` `-` `_` `:` `/` only. |
| `PHX2_STAGE29_2_ALLOW_LIVE_HTTP` | Locked truthy marker `"1"`. Without exactly this string, Stage 29.2's probe refuses every mode past `READINESS_ONLY`. |
| `PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS` | Bounded int in `[1, 600]`. Defaults to `30` when unset. `INVALID` when present-but-unsafe. |

The raw values NEVER appear on `__repr__`, `dataclasses.asdict`,
`pickle.dumps`, `json.dumps`, exception messages, log lines, or
persisted artifacts. The Stage 29.2 redaction discipline is the
same as Stage 28.11's.

Stage 29.2 does NOT fall back to a generic `BIRDEYE_API_KEY` /
`BIRDEYE_BASE_URL` name. Operators with an existing PHX1 / out-
of-tree convention should copy the value into the Stage-29.2
pinned name.

---

## 3. Endpoint set + headers

Stage 29.2 calls exactly two Birdeye endpoints:

| Purpose | Method | Path | Required query params | Response shape consumed |
|---|---|---|---|---|
| Current price | `GET` | `/defi/price` | `address=<base_mint>` | `data.value` |
| ATH (from candle highs) | `GET` | `/defi/ohlcv` | `address=<base_mint>`, `type=<resolution>`, `time_from=<unix>`, `time_to=<unix>` | `max(data.items[].h)` + corresponding `data.items[].unixTime` |

Default OHLCV resolution: `15m`. The closed-set allowed
resolutions are `1m / 3m / 5m / 15m / 30m / 1H / 2H / 4H / 6H /
8H / 12H / 1D / 3D / 1W / 1M`.

HTTP headers sent on every request:

- `X-API-KEY: <operator's PHX2_STAGE29_2_BIRDEYE_API_KEY value>`
- `x-chain: solana` — hardcoded constant; Stage 29.2 is
  Solana-only by construction. There is no `chain` env var.
- `accept: application/json`
- `User-Agent: phx2-stage29-2/1`

Stage 29.2 sends NO request body (read-only). The transport
follows NO redirects to a host outside the operator-supplied
base URL. Stage 29.2 does NOT retry on failure.

---

## 4. Probe modes

The Stage 29.2 live probe accepts three modes via
`run_stage29_2_birdeye_probe(mode=...)`:

### 4.1 `READINESS_ONLY`

No outbound network. Asserts the env-read boundary projects
cleanly + the readiness verdict is `READY`. Returns the
readiness axes (api_key_length, base_url_length, live_flag_set,
timeout_seconds) + `handoff_ready`.

Expected PASS:

```
mode=READINESS_ONLY
status=READY
refusal_reason=NONE
handoff_ready=True
```

### 4.2 `HTTP_CONNECT_ONLY`

Exactly one outbound `GET /defi/price?address=<WRAPPED_SOL_MINT>`
to prove credentials are accepted. Uses the Stage 29.1 manifest
re-export of the WSOL constant; the operator's target mint is
NOT revealed by this mode.

Expected PASS:

```
mode=HTTP_CONNECT_ONLY
status=CONNECTED
refusal_reason=NONE
http_status_code=200
handoff_ready=True
```

### 4.3 `ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN`

Takes the operator-supplied `base_mint` (from the Stage 29.1
PumpSwap probe), makes at most two outbound requests (one
`/defi/price` + one `/defi/ohlcv`), builds a Stage 29.2
evidence record (with locally-computed drawdown ratio for
telemetry), and runs the no-invention audit.

Bounded budget:

- max outbound requests: 2 (one `/defi/price` + one
  `/defi/ohlcv`).
- no retries.
- no looping.

Expected PASS:

```
mode=ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN
status=FETCHED_WITH_PRICE_AND_ATH
refusal_reason=NONE
base_mint=<Stage 29.1 extracted base_mint>
price_status=PRESENT
ath_status=PRESENT
window_starts_post_migration=<true|false>
drawdown_ratio=<canonical decimal text or None>
freshness_status=FRESH
handoff_ready=True
no_invention_audit=PASSED
```

---

## 5. Operator scratch ceremony

Stage 29.2's probe writes NO artifact on its own. The operator
captures the probe result via a scratch caller that lives
OUTSIDE the PHX2 working tree. The scratch caller MUST:

1. set the four env names listed in §2,
2. confirm `git rev-parse stage-28-closed^{}` still peels to
   `a897bb0531259bbe065efb3e38703a7c3be156c7`,
3. confirm the Stage 28.11 + Stage 29.1 live probes both
   previously passed in the same operator environment,
4. invoke `run_stage29_2_birdeye_probe(...)` once per mode,
5. serialize the returned `Stage29_2BirdeyeHintProbeResult` to
   an operator-supplied artifact directory,
6. run a Stage 28.7-style redaction scan over the artifact
   directory and confirm `SAFE`.

The Stage 29.2 result object's `__repr__` / `asdict` emit only
the Stage 29.2 closed-set tokens + safe length counters; the
raw API key, raw base URL, raw response body, and raw HTTP
traceback are NEVER carried on the result.

---

## 6. Closed-set vocabularies

### 6.1 `birdeye_price_status`

`PRESENT` / `MISSING` / `STALE` / `SOURCE_ERROR`

### 6.2 `birdeye_ath_status`

`PRESENT` / `MISSING` / `STALE` / `SOURCE_ERROR`

### 6.3 `birdeye_freshness_status`

`FRESH` / `STALE` / `UNKNOWN`

### 6.4 `birdeye_refusal_reason`

`NONE` / `ENDPOINT_MISSING` / `ENDPOINT_UNSAFE` /
`API_KEY_MISSING` / `API_KEY_UNSAFE` / `LIVE_FLAG_NOT_SET` /
`TIMEOUT_INVALID` / `HTTP_FAILED` / `HTTP_TIMEOUT` /
`HTTP_STATUS_REJECTED` / `HTTP_SUCCESS_FALSE` /
`BODY_MALFORMED` / `PRICE_MISSING_IN_BODY` /
`ATH_SERIES_EMPTY` / `MINT_REJECTED_SAFE_SHAPE` /
`BASE_URL_REJECTED` / `LOOKBACK_INVALID` /
`OHLCV_TYPE_INVALID` / `MODE_INVALID` /
`TRANSPORT_FACTORY_NOT_CALLABLE`

### 6.5 `probe_mode`

`READINESS_ONLY` / `HTTP_CONNECT_ONLY` /
`ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN`

### 6.6 `probe_status`

`READY` / `NOT_READY` / `CONNECTED` /
`FETCHED_WITH_PRICE_AND_ATH` / `FETCHED_PRICE_ONLY` /
`FETCHED_NO_ATH_EVIDENCE` / `FAILED` / `SKIPPED`

### 6.7 `no_invention_audit`

`PASSED` / `FAILED`

---

## 7. Forbidden surfaces (Stage 29.2 scope)

The following surfaces are forbidden anywhere in Stage 29.2
production source. Boundary tests at
`PHX2/tests/stage29/test_stage_29_2_boundaries.py` police them.

- Discord send / diagnostic Discord smoke
- Telegram / X / social sender
- automated trading / position sizing / trade execution
- wallet / private-key / signer surface
- public / subscriber / paid-tier routing
- Stage 26 policy enforcement gate activation
- Stage 28.4 audited transport invocation in Stage 29.2
- Stage 28.6 bounded runner invocation in Stage 29.2
- Stage 28.9 wrapper invocation in Stage 29.2
- Pump.fun bonding-curve decoder / program id constant
- Stage 29.3 tradeable Discord smoke harness
- Dexscreener as a dispatch authority OR price fallback
- Helius as a price source
- any third or fourth provider beyond Birdeye at Stage 29.2
- PHX1 import path / `Phoenix_Bot` path string / `phx1`
  substring (case-insensitive)
- raw API-key-shaped literal in production source
- raw Birdeye URL host literal in production source (the host
  comes from `PHX2_STAGE29_2_BIRDEYE_BASE_URL` only)
- top-level Call / top-level filesystem-write at module import
  time
- `os.environ` / `os.getenv` / `os.environb` reads outside
  `stage29_2_birdeye_readiness.py`
- `urllib.request` / `requests` / `httpx` / `aiohttp` /
  `solana` / `solders` / `discord` / `telegram` / `dotenv` /
  `keyring` / `sqlalchemy` / `asyncio` / `threading` /
  `subprocess` imports outside
  `stage29_2_birdeye_http_transport.py`

---

## 8. Acceptance criteria — Stage 29.2

Stage 29.2 is considered closed only after every one of the
following holds:

- all nine production .py files exist at the locked paths;
- this runbook exists at the locked path;
- all ten test files exist at the locked paths and pass
  offline;
- the Stage 29.0 + Stage 29.1 + Stage 28.8 / 28.9 / 28.10 /
  28.11 boundary tests have been widened (test files only;
  production unchanged) to admit Stage 29.2 inventory while
  continuing to block Stage 29.3 implementation files,
  Pump.fun bonding-curve files, and the other forbidden
  surfaces;
- the operator has performed the three probe modes on a real
  operator environment and recorded:
  - mode 1 `READINESS_ONLY` → `status=READY`,
    `refusal_reason=NONE`;
  - mode 2 `HTTP_CONNECT_ONLY` → `status=CONNECTED`,
    `refusal_reason=NONE`, HTTP 200;
  - mode 3
    `ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN` →
    `status=FETCHED_WITH_PRICE_AND_ATH`,
    `refusal_reason=NONE`,
    `price_status=PRESENT`,
    `ath_status=PRESENT`,
    `handoff_ready=True`,
    `no_invention_audit=PASSED`;
- a Stage 28.7-style redaction scan over the artifact
  directory reports `SAFE`;
- the operator has confirmed:
  - no Discord send was invoked,
  - no Stage 29.3 tradeable smoke was invoked,
  - no Stage 26 enforcement was activated,
  - no PHX1 import path was loaded.

Stage 29.3 acceptance authorization remains separately
required; Stage 29.2 only lands the snapshot side.
