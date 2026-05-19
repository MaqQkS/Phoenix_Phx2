# Stage 23 closure audit

Stage: PHX2 Stage 23 — core on-chain filters (observe-only rebuild)
Audit sub-stage: 23.6
Posture: observe-only throughout
Closure decision target: local `stage-23-closed` tag after tests/audit
pass. **No push performed at audit time. No commit performed at audit
time.**

## 1. Stage 23 scope summary

Stage 23 is the first clean PHX2 filter rebuild stage after the
Stage 22 ingestion-hardening close-out. Its job is to take
Stage 22-shaped events (the `raw_capture.jsonl` / `dedupe.jsonl`
artifacts produced by Stage 22) and emit deterministic, redacted,
hashed filter evaluations to disk under three closed-set filter
families:

  * `HOLDER_CONCENTRATION`
  * `LAUNCH_STRUCTURE`
  * `WALLET_SOURCE_QUALITY`

Stage 23 is **observe-only**. It evaluates and labels Stage 22-shaped
events; it never blocks, gates, routes, dispatches, alerts, or
monetizes. The Stage 23 manifest carries the locked
`observe_only_mode = "observe_only"` posture marker; the
per-evaluation JSONL rows omit that field by design (the
observe-only posture is a run-level invariant, not a per-row
flag).

Stage 23 is also a clean rebuild: it deliberately does NOT import
Phoenix1 filters or any Stage 21 / Stage 22 production module. The
Stage 22 artifact shape is read by field-name only, through the
`PHX2.stage23.input_reader` projection layer.

## 2. Commit list

Six commits land Stage 23 on `master` after `stage-22-closed`:

  * `644a113` — phx2 stage 23.0: filter rebuild planning doc
    (planning artifact only, no Stage 23 production code).
  * `defd8ea` — phx2 stage 23.1: filter contracts and input reader
    scaffolding.
  * `aa5fe71` — phx2 stage 23.2: holder concentration observe-only
    filter.
  * `d1dab41` — phx2 stage 23.3: launch structure observe-only
    filter.
  * `a87ba11` — phx2 stage 23.4: wallet source quality observe-only
    surface.
  * `238f997` — phx2 stage 23.5: observe-only filter runner and
    artifacts.

The five short SHAs `defd8ea`, `aa5fe71`, `d1dab41`, `a87ba11`,
`238f997` cover the Stage 23 production-code surface. The closure
test pins these five SHAs verbatim against this document.

## 3. Final Stage 23 components

The Stage 23 production tree at closure (`PHX2/stage23/`) contains
exactly twelve Python source files plus two docs:

  * `__init__.py` — Stage 23 subtree marker and hard import-boundary
    policy doc.
  * `constants.py` — locked version strings, closed-set vocabularies
    (`LABELS`, `DATA_STATUSES`, `FILTER_FAMILIES`,
    `INPUT_KINDS`), the locally re-declared
    `STAGE23_FORBIDDEN_ROUTING_TOKENS` and
    `STAGE23_FORBIDDEN_VOCABULARY` boundary-scanner inputs, and the
    input-reader preserved-field allowlist / secret-leak
    substrings.
  * `errors.py` — `Stage23Error` hierarchy
    (`Stage23ContractError`, `Stage23InputError`,
    `Stage23ManifestError`, `Stage23BoundaryError`).
  * `models.py` — `Stage23FilterInput`, `Stage23FilterResult`,
    `Stage23FilterEvaluation` `NamedTuple` records, the
    deterministic canonical-JSON hash helpers (`canonical_json`,
    `stage23_hash`, `compute_input_hash`,
    `compute_evaluation_hash`), and the closed-set assertion
    helpers (`assert_label_in_closed_set`,
    `assert_data_status_in_closed_set`,
    `assert_filter_family_in_closed_set`) plus the
    `build_filter_result` / `build_filter_evaluation` constructors.
  * `input_reader.py` — `read_stage22_jsonl` reading Stage 22-shaped
    artifacts (`raw_capture.jsonl` / `dedupe.jsonl` / synthetic)
    from operator-supplied paths, with strict-by-default
    secret-leak detection and concept-level missing-field
    tracking.
  * `filter_contracts.py` — `Stage23Filter` `Protocol` plus the
    `Stage23FilterFamily` closed-set helper.
  * `stage23_manifest.py` — `Stage23ManifestFileEntry`,
    `Stage23InputManifest`, `Stage23ArtifactManifest`, deterministic
    builders/serializers, file SHA-256 helper, and the locked
    `REDACTION_CONFIRMED_TOKEN`.
  * `holder_concentration.py` — Stage 23.2 holder-concentration
    observe-only filter (`HOLDER_CONCENTRATION` family). Pure
    function plus class-shaped Protocol surface.
  * `launch_structure.py` — Stage 23.3 launch-structure observe-only
    filter (`LAUNCH_STRUCTURE` family). Pure function plus
    class-shaped Protocol surface.
  * `wallet_source_quality.py` — Stage 23.4 wallet / source-quality
    observe-only filter (`WALLET_SOURCE_QUALITY` family). Pure
    function plus class-shaped Protocol surface, with four
    independent unsupported-marker sub-families.
  * `runner.py` — Stage 23.5 offline observe-only runner.
    `run_stage23_filters` evaluates the default filter set across
    every supplied input, deterministically sorted, returning an
    immutable `Stage23RunnerResult` carrying aggregated counters.
  * `artifact_writer.py` — Stage 23.5 deterministic artifact writer.
    `write_stage23_artifacts` serializes a `Stage23RunnerResult`
    into the locked artifact filename set under an
    operator-supplied output directory, with a redaction sweep
    before write and byte-identical determinism via binary-mode
    writes.

Plus the two Stage 23.6 closure docs:

  * `STAGE_23_CLOSURE_AUDIT.md` — this document.
  * `STAGE_24_HANDOFF.md` — handoff scope for the next stage.

## 4. Final artifact outputs

The Stage 23.5 artifact writer emits exactly six artifact files
into an operator-supplied output directory:

  * `stage23_filter_evaluations.jsonl` — one JSONL row per
    (input, filter) evaluation, sorted deterministically by
    `(token_mint, event_id, captured_event_id, filter_name)`.
  * `stage23_filter_summary.csv` — counter rows for
    `(filter_family, filter_name, label, data_status)` over the
    run.
  * `stage23_reason_code_counts.csv` — counter rows for
    `(filter_family, filter_name, reason_code)` over the run.
  * `stage23_data_status_counts.csv` — counter rows for
    `(filter_family, filter_name, data_status)` over the run.
  * `stage23_label_counts.csv` — counter rows for
    `(filter_family, filter_name, label)` over the run.
  * `stage23_manifest.json` — canonical-JSON manifest carrying the
    stage / schema versions, the locked
    `redaction_confirmed = "stage23_redaction_confirmed"` token,
    per-filter `filter_versions` and `threshold_versions`, every
    artifact's SHA-256 and row count, and the aggregated label /
    data-status / reason-code counters.

All six filenames are locked in `PHX2/stage23/artifact_writer.py`
(`ARTIFACT_FILENAME_*` constants) and pinned by the Stage 23.5
boundary tests.

## 5. Observe-only guarantees

The Stage 23 production tree carries observe-only guarantees at
multiple levels:

  * Every Stage 23 manifest record carries the locked posture
    marker `OBSERVE_ONLY_MODE = "observe_only"`. The
    per-evaluation JSONL rows do not carry that marker (the
    posture is a manifest-level invariant; embedding it on every
    JSONL row would be redundant noise).
  * Every emitted `Stage23FilterResult` carries a
    `threshold_version` locked to
    `"thresholds_v0_observe_only"`. The threshold-version axis
    is deliberately distinct from `filter_version`, so a future
    calibration pass can re-tune thresholds without bumping the
    filter's implementation version axis.
  * No Stage 23 module enforces, gates, blocks, or routes any
    event. The runner produces one
    `Stage23FilterEvaluation` per (input, filter) pair
    unconditionally; a non-`NORMAL` label is evidence, not a
    block.
  * Stage 23 emits explicit `MISSING_INPUT` / `INSUFFICIENT_DATA`
    / `UNKNOWN` labels with explicit `MISSING` / `PARTIAL` /
    `UNSUPPORTED` data statuses when input primitives are
    absent. `NORMAL` is never the default for "we don't know".
  * Every filter is a pure function over its
    `Stage23FilterInput`. No filter reads the clock, the
    environment, the network, or disk.

## 6. Boundary guarantees

The Stage 23 production tree honors hard boundary guarantees that
are pinned by the existing Stage 23 boundary tests
(`test_stage_23_*_boundaries.py`) and re-pinned by the Stage 23.6
closure test:

  * **No enforcement/blocking.** No identifier in the Stage 23
    production source contains `enforce`, `block_token`, `block`,
    `blocking`, `gate_token`, or `gate`. The Stage 23 boundary
    scanner's `STAGE23_FORBIDDEN_VOCABULARY` list explicitly
    forbids `enforce`, `gate`, `block`, and `blocking` as
    identifier substrings; the Stage 23.5 runner/writer
    file-scoped scanner re-pins the same set (plus the legacy
    `block_token` / `gate_token` patterns) at the AST identifier
    level so a future drift toward `block_event` /
    `blocking_filter` / `gate_event` slipping past the more
    specific tokens still fails the boundary suite.
  * **No alert dispatch.** No Stage 23 module imports Discord,
    Telegram, or any messaging library. No identifier carries
    `dispatch`, `alert`, `send_to_discord`, or
    `send_to_telegram`.
  * **No public/subscriber routing.** No identifier carries any
    member of `STAGE23_FORBIDDEN_ROUTING_TOKENS`
    (`subscriber`, `subscriber_channel`, `public_channel`,
    `public_signal`, `public_dispatch`, `paid_signal`,
    `paid_signals`, `paid_channel`, `paid_dispatch`).
  * **No DB writes/repos.** No Stage 23 module imports `sqlite3`
    / `sqlalchemy` or any other persistence library. No
    identifier carries `db`, `repository`, or `bot.db`.
  * **No env reads.** No Stage 23 module imports `os` for
    `os.environ` / `os.getenv` use; the env-read detector in
    `test_stage_23_1_boundaries.py` pins this AST-shape level.
  * **No network/live provider calls.** No Stage 23 module
    imports `requests`, `httpx`, `aiohttp`, `urllib3`,
    `websockets`, `grpc`, `helius`, `birdeye`, `dexscreener`,
    `jupiter`, `jito`, `axiom`, or any other provider client.
    No URL literal (`https://`, `http://`, `ws://`, `wss://`,
    `discord.com`, `discordapp.com`, `hooks.slack.com`) appears
    in any Stage 23 production source.
  * **No Stage 21/22 edits.** `git diff stage-22-closed^{commit}..HEAD --
    PHX2/stage21 PHX2/stage22 PHX2/tests/stage21
    PHX2/tests/stage22` is empty at closure-audit time.
  * **No ATH/Birdeye/Dexscreener.** No Stage 23 production source
    defines identifiers containing `birdeye`, `dexscreener`,
    `ath`, or `migration`. These belong to Stage 25.
  * **No Axiom/Jito/priority fee/global fee.** No Stage 23
    production source defines identifiers containing `axiom`,
    `jito`, `priority_fee`, `compute_budget`, or
    `execution_quality`. These belong to Stage 24.
  * **No X/social.** No Stage 23 production source defines
    identifiers containing `x_api` or `social`. These belong to
    Stage 27+.
  * **No Phoenix1 imports.** No Stage 23 production module
    imports a `phoenix1.*` target; the
    `test_no_phoenix1_imports` boundary test pins this at the
    AST import-target level.

## 7. Known caveat

Stage 22's `STAGE_22_CLOSURE_AUDIT.md` suite carries a stale
post-tag boundary test that expected no `stage-22-*` tag to
exist. The `stage-22-closed` tag now exists (annotated,
dereferences to commit
`9647f8eb94204203d2d8ef1da035e3bc5ed28b5d`), so that single
Stage 22 test is permanently expected to fail until its assertion
is inverted in a future hygiene pass. The user has explicitly
deferred that fix: **Stage 23 does not modify the Stage 22 test
suite to address this caveat. Stage 22 closure cannot be
re-opened from Stage 23.**

## 8. Closure decision

Stage 23 is ready for a local `stage-23-closed` tag once the
Stage 23.6 closure tests pass alongside the full Stage 23 test
suite. The tag is intentionally a local-only annotation at this
point — **no push is performed at audit time. No commit is
performed at audit time.**

Stage 24 is the next stage; see
[STAGE_24_HANDOFF.md](STAGE_24_HANDOFF.md) for its scope.
