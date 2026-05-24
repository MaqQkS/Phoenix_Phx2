# Stage 28.11 Chainstack Yellowstone gRPC client runbook

Stage 28.11 is the first PHX2 substage that opens a real
Chainstack Yellowstone gRPC channel. Stage 28.11 satisfies the
Stage 28.10 `Stage28_10ChainstackYellowstoneClient` Protocol so
the existing Stage 28.10 event source / hint-aware candidate
assembler chain CAN later (in Stage 28.12, under separate
operator authorization) drain real provider-backed events
through the same Protocol the Stage 28.10 fake client already
satisfies.

**Stage 28.11 is NOT a Discord-send stage.** **Stage 28.11 does
NOT invoke the Stage 28.9 wrapper.** **Stage 28.11 is NOT Stage
29 enforcement.**

This runbook is a manual operator procedure. Nothing in this
document instructs a Python runtime to send anything live to
Discord; nothing in this document instructs a Python runtime to
ramp up to a Stage 28.9 dispatch loop. Every send that ever
happens past Stage 28.11 lives in a separately authorized
substage.

## 0. Scope marker

Stage 28.11 is **real gRPC client path; three modes; no
dispatch**.

The Stage 28.11 production tree ships:

* the redaction-safe private endpoint-secret record + the
  runtime-config record that pairs the Stage 28.10 safe
  boundary config with the private secret + Stage 28.11
  mode / timeout axes,
* the closed-set Stage 28.11 mode / probe-status / refusal-
  reason vocabularies,
* the Stage 28.11 readiness boundary (the SINGLE Stage 28.11
  surface that reads `os.environ`),
* the Stage 28.11 decoder (Yellowstone protobuf -> Stage 28.10
  payload),
* the Stage 28.11 real gRPC client that satisfies the Stage
  28.10 Protocol,
* the Stage 28.11 probe orchestrator that drives the three
  locked modes,
* this runbook + the Stage 28.11 manifest + the Stage-28.11-
  scoped dependency-pin file + the vendored proto sources +
  the generated Python stubs.

The Stage 28.11 production tree does NOT ship:

* a Stage 28.9 wrapper invocation, a dispatch loop, or a
  Discord send,
* Stage 29 enforcement / approval / activation semantics,
* public routing, subscriber routing, paid tier routing,
* Telegram, X / social,
* automated trading, wallet / private-key / signer logic,
  position sizing, trade execution,
* a dashboard / HTTP control server,
* a daemon / systemd / watchdog / autorestart service.

## 1. Pinned proto source

Stage 28.11 vendored the Yellowstone gRPC proto schema from
the upstream rpcpool / Triton One repository:

* Source repo: `rpcpool/yellowstone-grpc`
  (<https://github.com/rpcpool/yellowstone-grpc>)
* Pinned tag: `v13.1.0+solana.4.0.0`
* Pinned commit SHA:
  `62893fb7644b1ceafd2f8d840f8e3997f44a483f`
* Pinned proto files (vendored verbatim under
  `PHX2/proto/stage28_11/source/`):
  * `geyser.proto`
  * `solana-storage.proto`

Stage 28.11 does NOT re-derive a proto schema from any other
source. The vendored copies under
`PHX2/proto/stage28_11/source/` are the locked Stage 28.11
schema. Re-vendoring requires a separately authorized substage
that pins the new tag + commit SHA in this runbook.

## 2. Pinned runtime dependencies

Stage 28.11 pins exactly three Python runtime dependencies in
`PHX2/stage28/stage28_11_requirements.txt`:

```
grpcio==1.66.2
grpcio-tools==1.66.2
protobuf==5.28.3
```

Stage 28.11 does NOT auto-upgrade these pins. Stage 28.11 does
NOT silently float versions. The rest of the PHX2 tree (Stage
21 .. Stage 28.10) remains stdlib-only by design; Stage 28.11
is the first PHX2 substage to introduce third-party
dependencies.

The pins are deliberately conservative: `grpcio==1.66.2` was
the Stage 28.10 runbook's nominated minor; `grpcio-tools` and
`protobuf` are pinned to compatible minors that ship the same
generated-stub `runtime_version` envelope.

Install into the local venv via:

```
.venv/Scripts/python.exe -m pip install --no-cache-dir \
  -r PHX2/stage28/stage28_11_requirements.txt
```

(Adjust the venv path on non-Windows hosts.)

## 3. Pinned proto generation command

The vendored generated Python stubs under
`PHX2/proto/stage28_11/_generated/` were produced by exactly:

```
.venv/Scripts/python.exe -m grpc_tools.protoc \
  -I=PHX2/proto/stage28_11/source \
  --python_out=PHX2/proto/stage28_11/_generated \
  --grpc_python_out=PHX2/proto/stage28_11/_generated \
  PHX2/proto/stage28_11/source/geyser.proto \
  PHX2/proto/stage28_11/source/solana-storage.proto
```

The generator emits sibling imports (`import solana_storage_pb2
as ...`); the Stage 28.11 vendor step rewrites those to
absolute package imports (`from PHX2.proto.stage28_11._generated
import solana_storage_pb2 as ...`) so the stubs work as a
proper Python package without `sys.path` manipulation.

Re-generation is NOT part of any test run. The generated stubs
are tracked in git so test runs are deterministic and so a
downstream reader can audit the exact emitted code without
having to install `grpcio-tools`.

If the operator ever needs to re-generate the stubs:

1. Re-run the command above.
2. Re-apply the import rewrite (the three lines below in the
   generated `geyser_pb2.py` / `geyser_pb2_grpc.py`):
   * `import solana_storage_pb2 as solana__storage__pb2`
     ->
     `from PHX2.proto.stage28_11._generated import solana_storage_pb2 as solana__storage__pb2`
   * `from solana_storage_pb2 import *`
     ->
     `from PHX2.proto.stage28_11._generated.solana_storage_pb2 import *`
   * `import geyser_pb2 as geyser__pb2`
     ->
     `from PHX2.proto.stage28_11._generated import geyser_pb2 as geyser__pb2`
3. Confirm the regenerated stubs import cleanly:
   * `python -c "from PHX2.proto.stage28_11._generated import
     geyser_pb2, geyser_pb2_grpc, solana_storage_pb2"`
4. Re-run the Stage 28.11 tests.
5. Update this runbook's section 1 pin if the upstream tag /
   commit SHA changed.

## 4. Env-name surface

Stage 28.11 reads exactly four env names through the Stage
28.11 readiness boundary
(`PHX2/stage28/chainstack_yellowstone_grpc_readiness.py`):

| Env name | Purpose |
|---|---|
| `PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT` | Raw gRPC endpoint (host:port; TLS required). Lives only on the private endpoint-secret subobject. |
| `PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN` | Raw Chainstack x-token. Lives only on the private endpoint-secret subobject. |
| `PHX2_STAGE28_11_ALLOW_LIVE_GRPC` | Must be exactly `"1"` to enable the connect-only / one-event-decode modes and the live integration test. |
| `PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS` | Optional; integer in `[1, 600]`. Defaults to `30`. |

Stage 28.11 does NOT broaden the Stage 28.1 provider-neutral
readiness env-name list. The Stage 28.11 names are a parallel
narrow surface.

The raw endpoint URL and raw x-token NEVER appear on any
public record, `__repr__`, exception, log line, or persisted
artifact. The Stage 28.11 model module's
`Stage28_11ChainstackYellowstoneGrpcEndpointSecret` carries
them on private slots and returns a redacted form from
`__repr__` / `__str__` / `to_safe_dict`. The Stage 28.11
boundary test pins this redaction.

## 5. Live order

Stage 28.11 mandates the following live order. The operator
runs each step in turn and only proceeds when the prior step's
probe result reports the closed-set success status / no
refusal.

1. **Readiness-only.** No network. No subscribe. No decode.
   * `run_stage28_11_probe_from_env(mode=MODE_READINESS_ONLY)`.
   * Expected: `status=READY`, `refusal_reason=NONE`,
     `ready=True`, `connected=False`, `decoded=False`,
     `handoff_ready=False`.
   * Failure modes: `ENDPOINT_MISSING` /
     `ENDPOINT_UNSAFE` / `X_TOKEN_MISSING` /
     `X_TOKEN_UNSAFE` / `TIMEOUT_INVALID`. None of these
     trigger a network connect.
2. **Provider-connect-only.** Opens TLS gRPC channel, calls
   `Ping()`, tears the channel down.
   * Requires `PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1`.
   * `run_stage28_11_probe_from_env(mode=MODE_PROVIDER_CONNECT_ONLY)`.
   * Expected: `status=CONNECTED`, `refusal_reason=NONE`,
     `ready=True`, `connected=True`, `decoded=False`,
     `handoff_ready=False`.
   * Failure modes: `LIVE_FLAG_NOT_SET` (the env flag is
     missing) or `CONNECT_FAILED` (the gRPC channel
     refused).
   * No event decode. No subscribe. No Discord.
3. **One-event decode dry run.** Opens TLS gRPC channel,
   subscribes with a minimal non-vote transaction filter,
   reads at most ONE upstream `SubscribeUpdate`, decodes it
   into the Stage 28.10 safe payload, tears the channel down.
   * Requires `PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1`.
   * `run_stage28_11_probe_from_env(mode=MODE_ONE_EVENT_DECODE_DRY_RUN)`.
   * Expected: `status=DECODED`, `refusal_reason=NONE`,
     `ready=True`, `connected=True`, `decoded=True`,
     `decoded_payload=<Stage28_10ChainstackYellowstonePayload>`,
     `handoff_ready=True`, `events_received=1`.
   * Failure modes: `LIVE_FLAG_NOT_SET` /
     `CONNECT_FAILED` / `NO_EVENT_RECEIVED` (the deadline
     expired before any transaction update arrived) /
     `DECODE_FAILED` (the upstream message failed the Stage
     28.10 safe-shape contract; the operator inspects the
     closed-set reason token).
   * **No Discord.** **No dispatch.** **No Stage 28.9
     wrapper.** **No Stage 29 enforcement.** **No public /
     subscriber / paid tier routing.** **No Telegram / X /
     social.** **No automated trading / wallet / private-
     key logic.** **No position sizing / trade execution.**
4. **Stage 28.12 wrapper with tight caps.** ONLY after step
   3 above succeeds AND the operator separately authorizes
   the next substage:
   * Stage 28.12 wires this Stage 28.11 client into the
     Stage 28.9 `run_stage28_9_live_provider_session` call
     with `max_events=1`, `max_dispatches=1`, an out-of-repo
     artifact directory, the Stage 28.10 hint-aware candidate
     assembler, and the operator's explicit
     `live_env_ready=True` / `live_operator_request=True`
     decisions.
   * The first private Discord ping past Stage 28.10 may flow
     ONLY at Stage 28.12, under explicit operator
     authorization, and only to the operator-private
     webhook.

## 6. Real pings still require fresh price context

The Stage 28.11 decoder leaves the `quote_mint` / `pool_account`
/ `pool_program_id` / `base_mint` / `provider_quote_asset_hint`
/ `provider_pair_type_hint` /
`provider_bonding_curve_version_hint` /
`bonding_curve_version_hint` hint fields as `None`. **Stage
28.11 NEVER invents a SOL hint.** **Stage 28.11 NEVER invents a
USDC hint.** The Stage 27 chain owns the actual pair / pool /
bonding-curve classification; Stage 28.11 hands off a
hint-empty payload to the Stage 28.10 candidate assembler when
the operator escalates to Stage 28.12.

The Stage 28.10 hint-aware candidate assembler then runs the
existing Stage 27 candidate chain (`assemble_live_candidate`).
The Stage 27 chain refuses to render a tradeable private ping
when:

* the injected Stage 27.4 price source returns `UNAVAILABLE`
  / `SOURCE_ERROR` (rendered ping carries `price_status =
  UNAVAILABLE` / `SOURCE_ERROR`, mapped to
  `CANDIDATE_PRICE_STATUS_MISSING`, suppressed via
  `PRICE_MISSING`),
* the injected price snapshot's `fetched_at_utc` lies outside
  the configured staleness threshold (rendered ping carries
  `price_status = STALE`, mapped to
  `CANDIDATE_PRICE_STATUS_STALE`, suppressed via
  `PRICE_STALE`).

**A missing price suppresses.** **A stale price suppresses.**

Stage 28.11 production code NEVER fakes a price; the operator
supplies the price source at the Stage 27.6 `Stage27_6Sources`
boundary in the eventual Stage 28.12 wrapper invocation.

## 7. UNKNOWN / DISAGREE / USDC observe-only suppressions remain

Because the Stage 28.11 decoder leaves every hint field as
`None`, every Stage 28.11-produced Stage 28.10 payload starts
in the UNKNOWN pair lane. The Stage 27 / Stage 28.6 chain
therefore suppresses the candidate via the existing
`UNKNOWN_PAIR_SUPPRESSED` rule when Stage 28.12 eventually
runs the dispatch loop. **Stage 28.11 does NOT promote UNKNOWN
to SOL.** **Stage 28.11 does NOT promote DISAGREE to a
successful live-ready verdict.** **Stage 28.11 does NOT flip
the USDC observe-only lane to allow-only.**

The eventual Stage 28.12 substage MAY add Pump.fun instruction
decoding to derive hint evidence; that is a separately
authorized step. Stage 28.11 itself stays hint-empty by
construction.

## 8. Stage 29 enforcement pending

Stage 29 owns the approved / activated filter enforcement
gate. Stage 28.11 does NOT add an enforcement gate; Stage
28.11 does NOT activate any Stage 26 policy candidate; Stage
28.11 does NOT flip any Stage 27 suppression rule from
observe-only to allow-only.

Every Stage 28.10 candidate that eventually reaches the Stage
28.9 mapper in the future Stage 28.12 step carries the Stage
28.9 marker `Filter enforcement:
NOT_ACTIVE_STAGE_29_PENDING` on its rendered Discord payload.
Stage 28.11 inherits the marker via the Stage 28.10 boundary;
Stage 28.11 does NOT add a new marker of its own.

## 9. No public / subscriber routing in Stage 28.11

Stage 28.11 is private-operator only by construction. The
Stage 28.10 boundary already refuses public routing /
subscriber routing / paid tier routing surfaces; Stage 28.11
inherits those refusals and does NOT introduce any of:

* public router,
* subscriber router,
* paid tier router,
* approval gate, approval status, enforcement result,
* Telegram sender / Telegram client,
* X / social sidecar / tweet ranking / social scoring,
* auto-trade / position sizer / trade executor / wallet
  signer / private-key loader,
* dashboard, HTTP control server, watchdog, autorestart,
  daemon, systemd unit.

The Stage 28.11 boundary scan pins these prohibitions.

## 10. No Telegram / X / social in Stage 28.11

Stage 28.11 imports no Telegram client, no X / Twitter client,
no Discord client beyond the Stage 28.4 audited HTTP
transport's documented private-operator webhook (which Stage
28.11 itself does NOT invoke). The Stage 28.11 boundary scan
pins the forbidden import patterns.

## 11. No automated trading / wallet / private-key logic in Stage 28.11

Stage 28.11 imports no Solana SDK, no `solders`, no `solana`,
no `base58` library (the Stage 28.11 decoder ships a tiny
pure-Python base58 helper local to the decode module). Stage
28.11 does NOT load a wallet seed, does NOT sign a transaction,
does NOT size a position, does NOT execute a trade. The Stage
28.11 boundary scan pins these prohibitions.

## 12. Operator checklist

Before running any Stage 28.11 probe:

* [ ] Confirm `git rev-parse stage-28-closed^{}` still peels to
      the Stage 28.8 closure commit
      (`a897bb0531259bbe065efb3e38703a7c3be156c7`).
* [ ] Confirm `PHX2/stage29/` and `PHX2/tests/stage29/` do
      not exist.
* [ ] Confirm
      `PHX2/proto/stage28_11/source/geyser.proto` and
      `PHX2/proto/stage28_11/source/solana-storage.proto`
      match the upstream rpcpool/yellowstone-grpc tag
      `v13.1.0+solana.4.0.0` (commit SHA
      `62893fb7644b1ceafd2f8d840f8e3997f44a483f`).
* [ ] Confirm `pip install -r
      PHX2/stage28/stage28_11_requirements.txt` reports
      `grpcio==1.66.2`, `grpcio-tools==1.66.2`,
      `protobuf==5.28.3`.
* [ ] Confirm
      `python -c "from PHX2.proto.stage28_11._generated import
      geyser_pb2, geyser_pb2_grpc, solana_storage_pb2"` imports
      cleanly.
* [ ] Run the Stage 28.11 unit tests; confirm every Stage
      28.11 test passes with the live env flag UNSET (the
      live test is skipped by default).
* [ ] Set `PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT`,
      `PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN`, and
      `PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1` in the operator
      shell only (never persist these values in any tracked
      file).
* [ ] Run mode 1 (readiness-only). Confirm
      `status=READY`.
* [ ] Run mode 2 (provider-connect-only). Confirm
      `status=CONNECTED`.
* [ ] Run mode 3 (one-event decode dry run). Confirm
      `status=DECODED` and `handoff_ready=True`.
* [ ] Stop. Do NOT proceed to Stage 28.12 without separate
      explicit operator authorization.

## 13. Stage 28.11 closure

Stage 28.11 is closed when:

* the Stage 28.11 production / doc / test inventory matches
  the locked `stage28_11_manifest.py` lists,
* every Stage 28.11 test passes offline,
* the live probe order (modes 1 -> 2 -> 3 above) succeeds end
  to end in the operator's environment,
* no Stage 29 / public / subscriber / paid / Telegram / X /
  social / trade / wallet / dashboard / daemon surface was
  introduced,
* no `stage-28-closed` tag was created, moved, or peeled,
* no Stage 28 commit was pushed by Stage 28.11
  implementation.

Stage 28.11 does NOT introduce a `stage-28-11-closed` tag.
Tagging Stage 28.11 (if appropriate) requires separate
explicit operator authorization.
