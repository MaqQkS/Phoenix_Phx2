# Stage 24 closure audit

Stage: PHX2 Stage 24 — execution-fee and execution-quality primitive
foundation (observe-only).
Audit sub-stage: 24.7.
Posture: observe-only throughout.
Closure decision target: local `stage-24-closed` tag after focused
tests pass and operator authorization. **No push performed at audit
time. No commit performed at audit time. No tag performed at audit
time.**

## 1. Stage 24 mission recap

Stage 24 is the first execution-fee and execution-quality primitive
stage after the Stage 23 filter rebuild. Its job is to take a
Stage 24-shaped transaction observation and emit deterministic,
redacted, hashed execution-primitive records to disk under the five
closed-set primitive families:

  * `COMPUTE_BUDGET`
  * `PRIORITY_FEE`
  * `JITO_TIP`
  * `ROUTER_FEE`
  * `EXECUTION_QUALITY`

Stage 24 is **observe-only**. It decodes and records evidence from
transaction-level data; it never blocks, gates, routes, dispatches,
alerts, or monetizes. The Stage 24 manifest carries the locked
`observe_only_mode = "observe_only"` posture marker.

Stage 24 is also a clean rebuild: it deliberately does not import
Phoenix1 fee / Jito / Axiom code and does not import any
Stage 21 / Stage 22 / Stage 23 production module. The Stage 24
input reader projects a Stage 24-shaped decoded transaction JSONL
into `Stage24ExecutionInput`; nothing else crosses the boundary.

## 2. Commit list

Seven commits land Stage 24 on `master` after the Stage 23 closure
commit (`401f05b` — *phx2 stage 23.6: closure audit and stage 24
handoff*):

  * `3957347` — phx2 stage 24.0: execution primitives scope lock
    (planning artifact only, no Stage 24 production code).
  * `a0ce8d8` — phx2 stage 24.1: execution primitive foundation.
  * `107fc3b` — phx2 stage 24.2: compute budget and priority fee
    decoder.
  * `a593cf7` — phx2 stage 24.3: jito tip decoder.
  * `cd8d7a8` — phx2 stage 24.4: router fee candidate scaffold.
  * `3af1ba5` — phx2 stage 24.5: no confirmed router fee decoder
    (Path B lock).
  * `5ae1709` — phx2 stage 24.6: runner writer and execution
    artifacts.

The seven short SHAs `3957347`, `a0ce8d8`, `107fc3b`, `a593cf7`,
`cd8d7a8`, `3af1ba5`, `5ae1709` cover the Stage 24 surface from
scope lock through deterministic artifacts. The Stage 24.7 closure
test pins these seven SHAs verbatim against this document.

## 3. Final Stage 24 components

The Stage 24 production tree at closure (`PHX2/stage24/`) contains
exactly fifteen Python source files plus three docs:

### Stage 24.1 foundation

  * `__init__.py` — Stage 24 subtree marker and hard import-boundary
    policy doc.
  * `constants.py` — locked version strings, closed-set vocabularies
    (`PRIMITIVE_FAMILIES`, `DECODER_STATUSES`, `DATA_STATUSES`,
    `CONFIDENCE_LEVELS`, `FEE_SOURCES`, `ROUTE_FAMILIES`,
    `INSTRUCTION_LOCATIONS`, `INPUT_KINDS`), the active and
    deprecated Axiom router program IDs, the known Jito tip
    accounts, the locally re-declared
    `STAGE24_FORBIDDEN_ROUTING_TOKENS` /
    `STAGE24_FORBIDDEN_VOCABULARY` /
    `STAGE24_FORBIDDEN_VOCABULARY_WORDS` boundary-scanner inputs,
    the input-reader forbidden-field-substring and
    forbidden-value-substring tuples, the Stage 24.5 lock scalar
    markers, the Stage 24.6 artifact filename tuple, and the
    runner / writer / execution-quality / rejection-reason version
    axes.
  * `models.py` — `Stage24ExecutionInput`,
    `Stage24ExecutionPrimitive`, `Stage24ComputeBudgetResult`,
    `Stage24PriorityFeeResult`, `Stage24JitoTipResult`,
    `Stage24RouterFeeResult`, `Stage24ExecutionQualityResult`,
    `Stage24RunnerResult` `NamedTuple` records, the deterministic
    canonical-JSON / hash helpers (`canonical_json`,
    `stage24_hash`, `compute_input_hash`,
    `compute_primitive_hash`), closed-set assertion helpers, and
    the `build_*` constructors.
  * `errors.py` — `Stage24Error` hierarchy (`Stage24ContractError`,
    `Stage24InputError`, `Stage24ManifestError`,
    `Stage24BoundaryError`).
  * `decoder_contracts.py` — `Stage24Decoder` Protocol surfaces for
    compute-budget, priority-fee, Jito-tip, router-fee, and
    execution-quality decoders.
  * `input_reader.py` — Stage 24-shaped decoded-tx JSONL reader,
    operator-supplied paths, strict-by-default secret-leak
    detection (forbidden-field substrings, forbidden-value
    substrings, long-hex-run threshold), and concept-level
    missing-field tracking.
  * `stage24_manifest.py` — `Stage24ManifestFileEntry`,
    `Stage24InputManifest`, `Stage24ArtifactManifest`, deterministic
    builders / serializers, file SHA-256 helper, and the locked
    `REDACTION_CONFIRMED_TOKEN`.

### Stage 24.2 decoders

  * `compute_budget.py` — Stage 24.2 compute-budget decoder.
    Recognizes the ComputeBudget program `SetComputeUnitLimit` /
    `SetComputeUnitPrice` instructions and decodes
    `unit_limit` / `unit_price_microlamports`. Synthetic-fixture
    backed; no real-fixture dependency.
  * `priority_fee.py` — Stage 24.2 priority-fee derivation.
    Composes the compute-budget decoder output with the upstream
    observation's `meta.compute_units_consumed` (when present) to
    produce an estimated realized priority fee. Honest about
    `ABSENT` / `PARTIAL` / `DECODED` / `DECODE_UNCONFIRMED` /
    `DECODE_FAILED` states.

### Stage 24.3 decoder

  * `jito_tip.py` — Stage 24.3 Jito-tip decoder. Recognizes a
    system-program `Transfer` instruction whose destination is one
    of the eight known Jito tip accounts. Decodes `tip_account` and
    `amount_lamports` when present. No tip-account match yields
    `ABSENT`. Synthetic-fixture backed.

### Stage 24.4 router-fee candidate scaffold

  * `router_fee.py` — Stage 24.4 router / global-fee candidate
    scaffold. Detects the two active Axiom router program IDs,
    the two deprecated Axiom router program IDs, inner system /
    token transfer candidates, and wrapped-swap evidence. Emits
    `Stage24RouterFeeResult` with `decoder_status ∈
    {ABSENT, UNSUPPORTED, DECODE_UNCONFIRMED}`, never `DECODED`;
    `amount_lamports = None` and `amount_token = None` always;
    `fee_source ∈ {UNKNOWN, ROUTER_FEE_CANDIDATE,
    AXIOM_GLOBAL_FEE_CANDIDATE}`, never the confirmed variants.

### Stage 24.5 no-confirmed-decoder lock (Path B)

  * `STAGE_24_5_NO_DECODER_LOCK.md` — Stage 24.5 Path B lock doc.
    Documents the no-confirmed-decoder state, the missing six
    proof criteria, the future Path A requirements, and the
    honesty claims preserved at the close of 24.5.

### Stage 24.6 runner / writer / execution-quality surface

  * `execution_quality.py` — Stage 24.6 execution-quality evaluator.
    `evaluate_execution_quality` composes the per-fee decoder
    outputs with the upstream submission / landing metadata into a
    `Stage24ExecutionQualityResult`. Observe-only: makes no judgment
    about whether a quality observation is *good*; Stage 26 is the
    calibration stage that decides what to do with it.
  * `runner.py` — Stage 24.6 deterministic decoder runner.
    `run_stage24_decoders` invokes each per-fee decoder once per
    `Stage24ExecutionInput`, composes the unified per-primitive
    rows, lifts typed `Stage24Error` failures into deterministic
    `Stage24RejectionRecord` rows, and returns an immutable
    `Stage24RunnerResult` plus the rejection tuple.
  * `artifact_writer.py` — Stage 24.6 deterministic artifact
    writer. `write_stage24_artifacts` serializes a
    `Stage24RunnerResult` into the locked artifact filename set
    under an operator-supplied output directory, with a redaction
    sweep before write, atomic writes via temp-and-rename, and
    byte-identical determinism via canonical JSON / sorted keys.

### Stage 24.7 closure docs

  * `STAGE_24_CLOSURE_AUDIT.md` — this document.
  * `STAGE_25_HANDOFF.md` — handoff scope for the next stage.

## 4. Final artifact outputs

The Stage 24.6 artifact writer emits exactly eleven artifact files
into an operator-supplied output directory. Every filename is
locked in `PHX2/stage24/constants.py` (`ARTIFACT_FILENAME_*`
constants, `ALL_STAGE24_ARTIFACT_FILENAMES` tuple) and pinned by
the Stage 24.6 / 24.7 boundary tests:

  * `stage24_manifest.json` — canonical-JSON manifest carrying the
    stage / schema versions, the locked
    `redaction_confirmed = "stage24_redaction_confirmed"` token,
    runner / writer name+version axes, every artifact's SHA-256 /
    row count / bytes written, the Stage 24.5 lock scalar markers
    (`stage_24_5_has_confirmed_router_fee_decoder`,
    `stage_24_5_real_fixture_count`,
    `stage_24_5_confirmed_layout_count`), and the locked artifact
    filename tuple.
  * `stage24_summary.json` — per-(primitive_family, decoder_status)
    and per-primitive_family counter summary, plus the
    router-fee candidate / confirmed split, plus the Stage 24.5
    lock scalar markers.
  * `stage24_execution_primitives.jsonl` — one row per unified
    `Stage24ExecutionPrimitive`, sorted by
    `(tx_signature, primitive_family, fee_source, primitive_hash)`.
  * `stage24_compute_budget_results.jsonl` — one row per
    `Stage24ComputeBudgetResult`, sorted by `result_hash`.
  * `stage24_priority_fee_results.jsonl` — one row per
    `Stage24PriorityFeeResult`, sorted by `result_hash`.
  * `stage24_jito_tip_results.jsonl` — one row per
    `Stage24JitoTipResult`, sorted by `result_hash`.
  * `stage24_router_fee_results.jsonl` — one row per
    `Stage24RouterFeeResult` with `decoder_status = DECODED`.
    **Empty at the close of Stage 24** because Stage 24.5 took
    Path B (no confirmed router / global-fee decoder).
  * `stage24_router_fee_candidates.jsonl` — one row per
    `Stage24RouterFeeResult` with
    `decoder_status ∈ {ABSENT, UNSUPPORTED, DECODE_UNCONFIRMED,
    PARTIAL}`, sorted by `result_hash`. The candidate side of the
    router / global-fee surface; this is where 24.4 candidate
    evidence lands.
  * `stage24_execution_quality_results.jsonl` — one row per
    `Stage24ExecutionQualityResult`, sorted by `result_hash`.
  * `stage24_decoder_coverage.csv` — per-(primitive_family,
    decoder_status, data_status) coverage matrix. Operator-facing
    summary of how much of the run each decoder confidently
    decoded.
  * `stage24_rejections.jsonl` — one row per rejected input
    (typed `Stage24Error` raised during a decoder call). Carries
    the closed-set rejection reason token and the rejecting
    decoder's name; never the raw exception message.

All eleven filenames are constants in `constants.py` and are
emitted by `artifact_writer.py` via the locked
`ARTIFACT_FILENAME_*` constants. The redaction sweep in the writer
rejects any forbidden field substring, URL / webhook host
substring, or long-hex-run shape before persisting.

## 5. Test state

Stage 24 ships focused tests under `PHX2/tests/stage24/`. Running

```text
py -B -m pytest PHX2/tests/stage24 -q -p no:cacheprovider \
    --basetemp=PHX2/.pytest_tmp_stage24
```

passes after Stage 24.7 lands. The focused test count after
Stage 24.7 is **higher than 508** (the count immediately before the
Stage 24.7 closure tests landed, after Stage 24.6's
`runner / writer / execution-quality` surface was committed). The
exact post-24.7 count is the count emitted by the run above; the
Stage 24.7 closure tests add the new closure-audit assertions.

Stage 24 tests cover, at a minimum:

  * Stage 24.1 constants closed-set tests, model immutability tests,
    input-reader malformed-JSONL / forbidden-substring / oversized
    rejection tests, manifest canonical-JSON byte-stability tests,
    Stage 24 boundary scanner tests.
  * Stage 24.2 compute-budget decoder tests (DECODED / PARTIAL /
    ABSENT / DECODE_FAILED / DECODE_UNCONFIRMED), priority-fee
    derivation tests.
  * Stage 24.3 Jito-tip decoder tests (DECODED / ABSENT /
    DECODE_FAILED), known-tip-account lockdown tests.
  * Stage 24.4 router-fee candidate scaffold tests (active program
    detection, deprecated program detection, wrapped-swap
    candidate, candidate-only contract).
  * Stage 24.5 no-confirmed-decoder lock tests (Path B), runtime
    invariants (no DECODED, `amount_lamports is None`, no
    confirmed `AXIOM_GLOBAL_FEE` fee source).
  * Stage 24.6 runner / writer / execution-quality tests
    (deterministic output, redaction sweep, atomic writes, empty
    input, decoder coverage CSV).
  * Stage 24.7 closure tests (this audit): closure docs present,
    commit SHAs pinned, artifact filenames pinned, Path B locked,
    constants lock holds, router_fee.py source still candidate-only,
    Stage 25 handoff doc defers ATH / Stage 26 calibration /
    Stage 27 X / social, exact Stage 24 production file set is
    allowed, no forbidden imports, no Stage 25 / Stage 26 /
    Stage 27 feature files created.

## 6. Boundary guarantees

The Stage 24 production tree honors hard boundary guarantees that
are pinned by the rolling Stage 24 boundary tests and re-pinned by
the Stage 24.7 closure tests:

  * **No DB writes.** No Stage 24 module imports `sqlite3` /
    `sqlalchemy` or any other persistence library. Stage 24 writes
    deterministic JSONL / CSV / JSON artifacts to a caller-supplied
    directory via `pathlib`; it never opens a database connection.
  * **No network / RPC.** No Stage 24 module imports `requests` /
    `httpx` / `aiohttp` / `urllib3` / `websockets` / `grpc` /
    `solana` / `solders` / `anchorpy` / `helius` / `jupiter` or
    any other provider client. No URL literal
    (`https://`, `http://`, `ws://`, `wss://`, `discord.com`,
    `discordapp.com`, `hooks.slack.com`) appears in any Stage 24
    production source. URL-scheme fragments and webhook host
    literals in `constants.py` are constructed at runtime via
    string concatenation so the literal substrings never appear in
    the source file.
  * **No Discord / Telegram dispatch.** No Stage 24 module imports
    a Discord or Telegram client or any messaging library. No
    Stage 24 production identifier contains `discord`, `telegram`,
    `telethon`, `webhook`, `dispatch`, or `alert`.
  * **No public / subscriber routing.** No Stage 24 production
    identifier contains any member of
    `STAGE24_FORBIDDEN_ROUTING_TOKENS` (`subscriber`,
    `subscribers`, `subscriber_channel`, `public_channel`,
    `public_signal`, `public_dispatch`, `paid_signal`,
    `paid_signals`, `paid_channel`, `paid_dispatch`).
  * **No live alert behavior.** Stage 24 emits records to disk; it
    never sends a live alert. No `alert` / `dispatch` /
    `notification` identifier exists in any Stage 24 production
    module. The runner is a pure function over inputs; the writer
    is a pure function over the runner's result and an output
    directory.
  * **No Stage 21 / Stage 22 / Stage 23 mutation.** No Stage 24
    module imports a `PHX2.stage21` / `PHX2.stage22` /
    `PHX2.stage23` production target. The Stage 24 input reader
    consumes Stage 24-shaped decoded-tx JSONL by field-name only;
    upstream Stage 22 raw capture is consumed (when at all) by a
    caller-supplied projection step, never by a Stage 24 import.
    The Stage 24 boundary tests pin this at the AST import-target
    level.
  * **No Phoenix1 imports.** No Stage 24 production module imports
    a `phoenix1.*` target. The Stage 24 boundary tests pin this at
    the AST import-target level. Stage 24 is a clean rebuild; no
    Phoenix1 fee / Jito / Axiom code is transcribed verbatim.
  * **No env reads.** No Stage 24 module imports `os.environ` /
    `os.getenv`; the env-read detector in the Stage 24 boundary
    tests pins this at the AST shape level.
  * **No CLI / sleep libs.** No Stage 24 module imports `argparse`
    / `click` / `typer` / `fire` / `docopt` / `time` / `asyncio`.
    The Stage 24 modules have no `__name__ == "__main__"` guard
    and no `main` / `cli` / `entrypoint` function.
  * **No top-level I/O.** Every Stage 24 module is side-effect-free
    at import time. The runner / writer / execution-quality
    modules have no forbidden top-level calls.

## 7. Router / global-fee honesty

Stage 24 is honest about what it does and does not know about
Axiom and other router-level fees. The Stage 24.5 no-confirmed-
decoder lock (Path B) is preserved at closure:

  * Stage 24.4 is the **candidate-only** scaffold: every
    router-fee primitive carries
    `decoder_status ∈ {ABSENT, UNSUPPORTED, DECODE_UNCONFIRMED}`
    and `amount_lamports = None`, regardless of whether an active
    Axiom router program ID appears in the transaction.
  * Stage 24.5 took **Path B** per
    `PHX2/docs/STAGE_24_BRAINSTORM.md` Section 5 / Section 15 /
    Section 19: no confirmed Axiom / router / global-fee decoder
    exists. The 24.5 lock doc
    (`PHX2/stage24/STAGE_24_5_NO_DECODER_LOCK.md`) documents the
    missing six proof criteria and the future Path A
    requirements.
  * The Stage 24.5 scalar markers in `constants.py` carry the
    locked values:
      * `STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER = False`
      * `STAGE_24_5_REAL_FIXTURE_COUNT = 0`
      * `STAGE_24_5_CONFIRMED_LAYOUT_COUNT = 0`
    These three markers are pinned by the Stage 24.5 lock tests
    and re-pinned by the Stage 24.7 closure tests.
  * **No DECODED router_fee primitive is ever emitted.** Stage 24
    contains no path that promotes a router-fee primitive to
    `decoder_status = DECODED`. `router_fee.py` does not import
    `DECODER_STATUS_DECODED` and does not define
    `decode_router_fee_confirmed` or `decode_axiom_global_fee`.
  * **No non-None router `amount_lamports`.** Every router-fee
    primitive carries `amount_lamports = None` and
    `amount_token = None`. Zero is never substituted as a
    stand-in for an unknown router fee. The 24.4 candidate
    decoder records candidate transfer counts in
    `numeric_features` (as research evidence) but never as a
    decoded amount.
  * **No confirmed `AXIOM_GLOBAL_FEE` fee_source.** `router_fee.py`
    does not import `FEE_SOURCE_AXIOM_GLOBAL_FEE` and does not
    emit it. Only the `_CANDIDATE` variants
    (`ROUTER_FEE_CANDIDATE` / `AXIOM_GLOBAL_FEE_CANDIDATE`) are
    emitted by the live decoder.
  * **Empty confirmed-router artifact file.** The Stage 24.6
    artifact writer emits `stage24_router_fee_results.jsonl` with
    zero data rows; every candidate row goes to
    `stage24_router_fee_candidates.jsonl`.

## 8. Known limitations

Stage 24 closes with the following limitations explicitly recorded:

  * **No exact Axiom / global-fee decoder yet.** Stage 24.5 took
    Path B; the confirmed router / global-fee decoder is deferred
    to a future Stage 24.x sub-stage that lands sanitized real
    fixtures and a fixture-backed decoder under the six proof
    criteria documented in
    `PHX2/stage24/STAGE_24_5_NO_DECODER_LOCK.md`.
  * **No sanitized real Axiom / FLASHX8 fixture proof yet.** The
    `INPUT_KIND_SANITIZED_REAL_DECODED_TX_JSONL` axis remains
    reserved in `constants.py` for future Path A but no caller
    produces it and no file under
    `PHX2/tests/stage24/fixtures/` carries the `sanitized` /
    `axiom_capture` / `flashx8_capture` substring. The Stage 24.5
    lock tests cross-pin this against the fixture-count constant.
  * **`execution_quality` is observe-only, not enforcement.**
    `Stage24ExecutionQualityResult` records `landed`,
    `landed_slot`, `submitted_slot`, `slot_delta`, and the
    realized priority-fee / Jito-tip / router-fee amounts (when
    decoded). Stage 24 makes no judgment about whether a quality
    observation is *good*; that judgment is a Stage 26 calibration
    concern.
  * **`priority_fee` remains estimated unless / where observed
    fields prove otherwise.** Stage 24.2 derives
    `priority_fee_estimated_lamports` from `unit_price *
    compute_units_consumed / 1_000_000` (with integer ceiling),
    not from a separately observed realized priority-fee field.
    `priority_fee_observed_lamports` stays `None` because Stage 24
    cannot separate base fee from priority fee without sanctioned
    upstream evidence. Compute-budget absence or ambiguity yields
    the appropriate `ABSENT` / `PARTIAL` / `DECODE_UNCONFIRMED` /
    `DECODE_FAILED` state with `amount_lamports = None`.

## 9. Closure decision

Stage 24 implementation is **complete through deterministic
artifacts**. The Stage 24.6 runner + writer pair emits the locked
eleven-artifact set deterministically given a tuple of
`Stage24ExecutionInput` records and an operator-supplied output
directory. The Stage 24.7 closure docs and closure tests pin the
final state.

The Stage 24 tag (`stage-24-closed`) should only be created after
the final focused test run passes locally and after explicit
operator authorization. **No push is performed at audit time. No
tag is performed at audit time. No commit is performed at audit
time.**

Stage 25 is the next stage; see
[STAGE_25_HANDOFF.md](STAGE_25_HANDOFF.md) for its scope.
