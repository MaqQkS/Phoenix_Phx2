# PHX2 Stage 30.4 Spec Lock

Stage 30.4.0 is spec lock only. Stage 30.4.0 ships exactly three
new files (this markdown, `stage30_4_manifest.py`, and the
Stage 30.4.0 spec-lock pin test). Stage 30.4.0 ships ZERO
production .py file beyond the manifest, ZERO models, ZERO
formatter, ZERO source adapter, ZERO source protocol, ZERO
artifact writer, ZERO runtime orchestrator, ZERO Discord send,
ZERO live provider call, and ZERO modification to any Stage 21-29
or Stage 30.1 / 30.2 / 30.3 production source file. Every
Stage 30.4.1+ substage requires separately authorized scope
before any production .py file lands.

Stage 30.4 is the OPTIONAL compact market context enrichment
substage of Stage 30. It is pre-named in the parent Stage 30.0
spec lock §2.4 as the "MC / LP / volume adapter". Stage 30.4
normalizes that label drift onto the renderer-facing label `Net`
(see §1.1 below).

Stage 30.4.0 does not enable live provider calls. Stage 30.4.0
does not enable Discord sends.

## 1. Scope

Stage 30.4 adds compact market context enrichment for private
compact pings. Stage 30.4 is the substage that fills the
`current_mc_text`, `lp_text`, and (eventually) `net_flow_text`
display slots that the Stage 30.3 projection currently leaves at
`None`.

- Stage 30.4 adds compact market context enrichment for private
  compact pings.
- Target fields are current MC and LP first.
- Net remains a planned field, but real Net-flow source is
  deferred.
- Stage 30.4 is not a trading/enforcement/public-routing stage.

### 1.1 Label discipline

- The renderer-facing label is `Net` (matches the implemented
  Stage 30.2 `compact_ping_renderer.py` body label).
- Historical spec drift: parent Stage 30.0 spec lock §2.4 calls
  the field a "volume adapter"; §6 of the same lock calls it
  "net flow". The implemented Stage 30.2 renderer uses `Net`.
- Stage 30.4 renderer-facing label remains `Net`. Stage 30.4
  does NOT rename the field to `Vol`.

## 2. Why Stage 30.4 exists

- Stage 30.3C-B proved real compact private Discord delivery.
- The proof ping still showed `MC`, `LP`, and `Net` as
  `Unknown` because none of the three has a live source today.
- Stage 30.4 fills safe display slots when source data exists.
- Missing source data remains `Unknown`, never 0 or fabricated.

The Stage 30.3D proof record (`STAGE_30_3D_COMPACT_PRIVATE_LIVE_PROOF.md`
§6 "Known limitation" and §8 "Deferred") explicitly names Stage
30.4 as the next step for MC / LP / Net context; Stage 30.4 is
the spec-lock answer to that limitation.

## 3. Current inventory

Stage 30.3 currently has, at every `send_one_audited_post` call:

- the token / base mint (from `ingest_output.token_mint`),
- a Stage 27.4 price context record (carrying `price_value` and
  `price_status`),
- a Stage 27.4 ATH context record (its `ath_value` is price-unit
  decimal text, not market-cap-unit text),
- a Stage 27.4 migration context record (carrying
  `migration_timestamp_utc` and `migration_source`),
- a `price_status` echo,
- an integer `age_since_migration_seconds`.

The Stage 30.3 projection in
`stage30_3_compact_candidate_projection.build_compact_ping_input_record`
currently leaves `current_mc_text`, `ath_mc_text`,
`migration_mc_text`, `lp_text`, and `net_flow_text` as `None`.
Stage 30.2 renders `None` as `Unknown`. That is the precise
reason the Stage 30.3C-B live ping rendered every market field
as `Unknown`.

Existing Stage 27 / Stage 28 / Stage 29 path does not currently
expose honest MC, LP, or Net primitives. The Stage 29.2 Birdeye
adapter exposes only USD price (from `/defi/price`) and USD ATH
price (from `/defi/ohlcv`); it does not expose market cap,
liquidity, or net flow.

Drop and Age were Unknown in the live proof only because
migration evidence was intentionally disabled (the Stage 30.3C-B
ceremony ran with `Stage29_3NoMigrationEvidenceSource`, which
forces `Tier Not Applicable / NA_MIGRATION_MISSING` and yields
`drop_positive=None` / `age_since_migration_seconds=None`).
Stage 30.4 does not fix Drop/Age. Drop/Age are not Stage 30.4
scope.

## 4. Source decisions

- First planned MC/LP source: Birdeye token_overview.
- Current MC may come from the token_overview market-cap-like
  field if present and valid.
- LP may come from the token_overview liquidity-like field if
  present and valid.
- ATH MC and Migration MC are deferred. Honest computation
  requires historical supply, which no current source ships.
- Net flow is deferred. It requires a separate trade-data /
  net buy / sell source.
- Dexscreener cross-check is deferred.
- On-chain supply x Birdeye price is deferred.

The "first source" decision pins Birdeye token_overview as the
planned source family for Stage 30.4.1 / 30.4.2 fakes. A real
Birdeye token_overview HTTP adapter is NOT shipped by Stage
30.4.0 / 30.4.1 / 30.4.2; it requires separately authorized
scope.

## 5. Architecture

Stage 30.4 is a small projector/adapter layer that fills already-
existing Stage 30.2 input slots. Stage 30.4 does NOT add new
renderer slots, does NOT change the renderer body shape, and
does NOT modify Stage 30.1 / 30.2 / 30.3 runtime code.

- Stage 30.4.1 will introduce offline-only models, formatter,
  source protocol, adapter / projector, and artifact writer.
- Stage 30.4.2 may introduce a parallel compact runtime
  orchestrator that imports Stage 30.3 read-only and fills
  Stage 30.2 display slots.
- Stage 30.4 must not modify Stage 30.1 / Stage 30.2 / Stage 30.3
  runtime code in 30.4.0 or 30.4.1.
- Stage 30.4.2 integration must be opt-in and offline / fake-
  source tested first.
- Any real Birdeye token_overview source or live proof requires
  a later explicit operator authorization.

## 6. Unknown policy

Stage 30.4 inherits the Stage 30.0 / 30.2 missing-value discipline
verbatim and tightens it for the source bundle:

- Missing source => Unknown.
- Missing value => Unknown.
- Invalid value => ERROR status in artifact, display remains
  Unknown.
- Stale value => STALE status in artifact, display policy must
  be explicit (pinned by Stage 30.4.1).
- Non-finite numbers rejected.
- Negative MC/LP rejected.
- Empty strings rejected.
- Unknown is never rendered as 0.
- Unknown is never silently converted to "0.0".
- Unknown does not produce fake compact values.

## 7. Display policy

Stage 30.4 owns the preformatted display strings for
`current_mc_text` and `lp_text` (and, when a Net-flow source
later ships, `net_flow_text`).

Example display forms:

- `"$83k"`
- `"$1.2M"`
- `"$27k"`

Discipline:

- Stage 30.4 must store both canonical decimal-text values and
  display text in its artifact.
- The compact renderer remains the final body renderer. Stage
  30.4 produces only display-text inputs to the renderer.
- Stage 30.4 does not recompute tier decisions. Stage 30.4 does
  not change price-basis tier classification.
- Tier basis remains price-basis until both current MC and ATH
  MC are honestly available in a later stage.

## 8. Non-goals

- No public routing.
- No paid tiers.
- No Telegram.
- No X/social.
- No enforcement.
- No wallet/signer/trading.
- No Axiom/global-fee hard gates.
- No Discord transport changes.
- No Stage 28.4 audited HTTP transport changes.
- No Stage 30.1 / 30.2 / 30.3 closed-set weakening.
- No fake MC / LP / Net values.
- No live provider calls in 30.4.0 / 30.4.1.
- No live Discord sends in 30.4.0 / 30.4.1 / 30.4.2.
- No Stage 29.5.6 migration-context append in Stage 30.4.0.
- No Drop/Age fix in Stage 30.4.
- No Net real source in first slice.
- No ATH MC / Migration MC in first slice.
- No Dexscreener in first slice.
- No on-chain supply path in first slice.

## 9. Substage map

- 30.4.0: spec lock + manifest + pin tests only.
- 30.4.1: offline models + formatter + source protocol + adapter
  + artifact writer, fake tests only.
- 30.4.2: opt-in parallel runtime integration with fake/offline
  source, no live Discord.
- 30.4.3 or later: optional controlled private proof only after
  real source adapter is separately authorized.

## 10. Forbidden imports and boundaries

Stage 30.4.0 files must not import:

- `os` (including `os.environ` / `os.getenv` / `os.environb`)
- `dotenv`
- `keyring`
- `requests`
- `httpx`
- `aiohttp`
- `urllib`
- `socket`
- `grpc`
- Discord and webhook transports
- Stage 21 / 22 / 23 / 24 / 25 / 26 / 27 / 28 / 29 production
  modules
- PHX1 / legacy phoenix-1 modules

Stage 30.4.0 source text must not contain raw endpoint / secret /
webhook strings. The Stage 30.4.0 manifest pins the closed-set
forbidden-text-needle vocabulary in split-literal form. The
Stage 30.4.0 spec-lock pin test scans every Stage 30.4.0 file
case-insensitively for those needles.

If a future doc needs to refer to a provider domain, it must use
safe split literals in tests or phrase the reference as a
provider label (for example `birdeye_token_overview` or
`Dexscreener`) only, not a raw URL or domain.

## 11. Manifest requirements

`stage30_4_manifest.py` is constants-only. It exposes:

- `STAGE30_4_SPEC_BASENAME`
- `STAGE30_4_MANIFEST_BASENAME`
- `STAGE30_4_TEST_BASENAMES`
- `STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0`
- `STAGE30_4_SUBSTAGE_SEQUENCE`
- `STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS`
- `STAGE30_4_FORBIDDEN_TEXT_NEEDLES`

The manifest:

- imports stdlib only (`typing`),
- reads no process environment variable,
- opens no network connection,
- writes no file,
- makes no git call,
- creates no tag,
- contains no top-level Call (no implicit I/O at import time),
- contains no runtime side effect.

## 12. Tests

`PHX2/tests/stage30/test_stage_30_4_0_spec_lock.py` pins the
Stage 30.4.0 contract. It asserts that:

- the spec doc exists;
- the manifest exists;
- the spec contains required scope / non-goal / source-decision
  tokens;
- operator decisions are pinned: `Net` label not `Vol`; MC + LP
  first; Net deferred; Birdeye token_overview first; on-chain
  supply deferred; Dexscreener deferred;
- the substage map is pinned;
- no Stage 30.4 runtime source files exist beyond the spec lock
  and the manifest;
- no Stage 30.4.1+ files exist yet;
- no forbidden imports appear in 30.4.0 files;
- no forbidden raw endpoint / secret / webhook needles appear in
  30.4.0 files;
- no Stage 21-29 production imports appear in 30.4.0 files;
- no Stage 30.1 / 30.2 / 30.3 runtime files are modified by this
  stage;
- Stage 30.4.0 does not enable live provider calls or Discord
  sends;
- the Unknown policy is pinned;
- no fake MC / LP / Net values are allowed;
- Drop / Age are explicitly out of Stage 30.4 scope.

---

_Stage 30.4.0 is spec lock only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.4.0
  implementation.
- There is no live Discord send during Stage 30.4.0
  implementation.
- There is no env / secret read during Stage 30.4.0
  implementation.
- There is no Stage 30.4.1+ production .py file at
  Stage 30.4.0 closure.
- There is no commit / tag / push performed by Stage 30.4.0
  implementation. Commit gating is a separate operator decision
  after audit.
