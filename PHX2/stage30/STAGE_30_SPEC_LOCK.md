# PHX2 Stage 30 Spec Lock

Stage 30.0 is spec lock only. Stage 30.0 ships exactly four files
(this markdown, the Stage 30 package `__init__.py`, the Stage 30
tests package `__init__.py`, and the Stage 30.0 spec-lock pin
test). Stage 30.0 ships ZERO production .py file beyond the package
marker, ZERO renderer, ZERO tier model, ZERO runner, ZERO transport
wrapper, ZERO artifact writer, ZERO Discord send, ZERO live provider
call, and ZERO modification to any Stage 27 / Stage 28 / Stage 29
production source file. Every Stage 30.1+ substage requires
separately authorized scope before any production .py file lands.

## 1. Stage 30 stance pin

Stage 30 is the practical private runtime usability stage for PHX2.
Stage 30 is not abstract scaffolding. Stage 30 is not a refactor of
Stage 28. Stage 30 is not a precursor to Stage 31.

The Stage 30 goal is concrete:

- I can run a private bounded runtime session as the operator.
- I receive compact readable tier-dip private Discord pings during
  that session.
- The renderer displays a tier only when context is safe; otherwise
  it shows `Tier Unknown` or `Tier Not Applicable` instead of
  inventing a tier.
- Each ping comes with redaction-safe debug artifacts that explain
  why the renderer chose Tier 1 / Tier 2 / Tier 3 / Tier Unknown /
  Tier Not Applicable.
- The session is bounded by explicit operator-supplied caps and
  ends with a clean stop reason and a redaction-safe final summary.

Stage 30 does not exist to add new abstractions. Stage 30 exists to
make the already-proven Stage 29.6 private live path readable,
debuggable, and operator-usable for bounded private sessions.

## 2. Stage 30 substage map

- **Stage 30.0 — spec lock only (this commit).** Docs and pin tests
  only. Zero production code. Zero existing-file modifications. Four
  files total.
- **Stage 30.1 — tier decision model + tier snapshot artifact.**
  Pure projector that maps `drawdown_from_ath` (plus ATH /
  migration safety status) to a closed-set tier token. Emits a
  redaction-safe tier-decision snapshot per ping. No I/O beyond
  the snapshot writer. No live calls.
- **Stage 30.2 — compact private ping renderer + ping snapshot
  artifact.** Pure projector that turns a structured candidate
  record (price / ATH / drawdown / migration / tier) into the
  compact body text described in Section 4. Emits a redaction-safe
  compact-ping snapshot per dispatch. No I/O beyond the snapshot
  writer. No live calls.
- **Stage 30.3 — bounded private runtime session wiring.** Stage
  30 orchestrator that reuses the existing Stage 28.6 bounded
  private session runner, wraps the Stage 28.9 transport with a
  Stage 30 compact-body transport wrapper (REPLACES `content`
  rather than appending; the existing Stage 29.5.6 wrapper layered
  outside continues to append migration context as a side-channel),
  and wires the Stage 30.1 / 30.2 snapshot writers into the
  dispatch path. Live ceremony is separately authorized and
  performed from outside the repo, mirroring Stage 29.6 discipline.
- **Stage 30.4 — OPTIONAL MC / LP / volume adapter.** Deferred
  unless needed. Adds a market-cap / liquidity / volume source
  adapter (Birdeye `token_overview` or Dexscreener) so the
  renderer can populate the `MC` / `ATH MC` / `Mig MC` / `LP` /
  `Vol` fields with real values instead of `Unknown`. Stage 30.4
  is NOT a Stage 30 prerequisite; the Stage 30.1 tier model and
  the Stage 30.2 renderer ship usable output without it.

## 3. Hard forbidden scope

Stage 30 (every substage) MUST NOT:

- route to any public audience.
- route to any paid or subscriber tier audience.
- activate Stage 26 or Stage 29 enforcement.
- size, place, sign, route, or execute any trade.
- read, write, derive, or touch any wallet, private key, seed
  phrase, signer, or signing surface.
- import, wrap, or call any Telegram surface.
- import, wrap, or call any X / Twitter / social surface.
- start, scope, scaffold, or anticipate Stage 31.
- close, tag, or push Stage 29 unless separately and explicitly
  authorized by the operator.
- print, log, or expose any live secret, API key, bearer token,
  webhook URL, or RPC URL.
- write any raw provider payload blob to any artifact, ledger, or
  snapshot.
- introduce any daemon, watchdog, autorestart loop, dashboard, or
  HTTP control-server module.
- introduce any Pump.fun bonding-curve decoder.
- modify the Stage 27 / Stage 28 / Stage 29 production source
  tree at Stage 30.0; subsequent Stage 30.1+ substages MUST
  document any narrow Stage 27 / 28 / 29 production touch in
  their own spec lock and prefer wrapper / parallel orchestrator
  patterns over in-place modification.

## 4. Compact private ping target

The Stage 30.2 renderer produces a compact, operator-readable
private Discord ping body. Target body shape (example):

```
🔥 PHOENIX — <SYMBOL-OR-MINT> [Tier 3]
<mint>

🧠 State
• MC: $83k | ATH: $460k | Mig: $36k
• Drop: -82% | Age: 16.6h | Net: Unknown
• LP: $27k (Tradable)
```

Rendering rules:

- The header carries the tier token verbatim
  (`[Tier 1]` / `[Tier 2]` / `[Tier 3]` / `[Tier Unknown]` /
  `[Tier Not Applicable]`).
- The mint line carries the full token / base mint address; the
  symbol slot may show `<mint short>` when no symbol is known. The
  renderer NEVER substitutes the quote mint (WSOL / USDC) for the
  token / base mint.
- The `🧠 State` section shows: `MC`, `ATH`, `Mig`, `Drop`, `Age`,
  `Net`, `LP`.
- `Drop` is the CURRENT drawdown from ATH at ping time (derived
  from the Stage 30.1 ``drop_positive`` value). It is NOT a
  historical floor / minimum-drawdown tracker; calling it `Floor`
  would mis-promise that.
- `Net` is operator-readable net buy / sell flow. Until a net-flow
  source ships in a later substage, callers pass no net-flow text
  and the renderer emits `Unknown`.
- Missing `MC`, `LP`, or `Net` values render as the literal string
  `Unknown` — never `0`, never `0.0`, never an empty value, never
  a fabricated estimate.
- Warnings render only when needed (degraded price staleness,
  `MAY_INCLUDE_PRE_MIGRATION` ATH, `UNTRUSTED` migration source,
  etc.). The renderer does not stack a warning when nothing is
  wrong.
- The compact body MUST target `<= 800` characters.
- The compact body MUST fit comfortably under the existing Stage
  28.9 Discord content cap (currently `STAGE28_9_CONTENT_MAX_CHARS
  = 1900`).
- The compact body MUST NOT contain any trading-verdict substring
  (case-insensitive): `BUY`, `SELL`, `APPROVED`, `GATE`, `BLOCK`,
  `ENFORCEMENT`, `EXECUTE`, `POSITION`, `AUTO-TRADE`.
- The standalone word `SAFE` is intentionally NOT on the forbidden
  list. Stage 30 artifacts and the Stage 30 redaction scan use
  `SAFE` as a closed-set status token (e.g. the redaction scan
  reports `SAFE` for every committed session), and the renderer
  must not collide with that usage. A compound trading-verdict
  phrase such as `SAFE BUY` or `SAFE SELL` is still rejected
  because `BUY` / `SELL` remain forbidden substrings; the `SAFE`
  carve-out applies only when `SAFE` appears WITHOUT a paired
  forbidden trading-verdict substring.

## 5. Tier semantics

Stage 30 adopts the historical Phoenix tier bands. The bands are
INCLUSIVE on both ends and carry intentional gaps:

- **TIER_1**: `0.50 <= drop <= 0.60`
- **TIER_2**: `0.62 <= drop <= 0.80`
- **TIER_3**: `0.82 <= drop <= 0.95`

Where:

```
drop = abs(drawdown_from_ath)
```

Preferred market-cap drawdown formula:

```
drawdown_from_ath = (current_mc - ath_mc) / ath_mc
```

Equivalent positive drop expressed in market-cap terms:

```
drop = (ath_mc - current_mc) / ath_mc
```

### Tier discipline (pinned)

- The gaps between bands are intentional and MUST be preserved.
  A `drop` in the `0.60-0.62` gap is NOT in any tier and MUST
  render `Tier Unknown`. A `drop` in the `0.80-0.82` gap is NOT
  in any tier and MUST render `Tier Unknown`. A `drop` of
  `> 0.95` is NOT a
  Tier 3 and MUST render `Tier Unknown` (graveyard band).
- A `drop` of `< 0.50` is below Tier 1 and MUST render
  `Tier Unknown` (pre-tier band; not yet a tier-dip candidate).
- The tier model NEVER rounds `drop` before tier comparison.
- The tier model NEVER squeezes an in-gap drop into the closer
  band.
- The tier model NEVER fabricates `ATH MC`, `current MC`, or
  `circulating supply`. When any of these is missing or the
  source is degraded, the tier model returns `Tier Unknown`.
- The tier model returns `Tier Not Applicable` when the ATH
  context carries `MAY_INCLUDE_PRE_MIGRATION` and the renderer
  cannot promise the drawdown is referenced against a
  post-migration ATH, or when migration evidence reports
  `MISSING` / `INVALID` / `CONFLICTING` / `SOURCE_ERROR`. The
  rationale: a drawdown computed against a pre-migration peak
  is misleading for tier display.

### Basis discipline (pinned)

- The preferred basis is `mc-basis` (uses `ath_mc` /
  `current_mc`). Stage 30 uses `mc-basis` whenever a real MC
  source is available.
- Until a Stage 30.4 MC source ships, Stage 30 MAY use the
  existing `AthContextRecord.drawdown_from_ath` price-basis
  value. With fixed/locked token supply (the norm post-
  migration), `mc-basis` and `price-basis` produce the same
  drop value.
- The Stage 30.2 renderer MUST expose the basis used
  (`price-basis` vs `mc-basis`) so the operator can see which
  one fired for any given ping.
- Stage 30 NEVER fabricates MC, supply, ATH MC, or current MC.
  Missing source values render as `Unknown` and downgrade the
  tier to `Tier Unknown` when the missing value is required
  for the basis in use.

## 6. Required operator-readable fields

Every Stage 30 compact ping MUST surface the following operator-
readable fields, in this order, with explicit `Unknown` for any
field whose source is missing or degraded:

- `token` / `mint` (token / base mint; NEVER the quote mint)
- `current MC` (if available)
- `ATH MC` (if available)
- `migration MC` (if available)
- `drawdown` / `drop %` (current drawdown from ATH at ping time;
  NOT a historical floor)
- `tier`: `Tier 1` / `Tier 2` / `Tier 3` / `Tier Unknown` /
  `Tier Not Applicable`
- `age since migration`
- `LP` (if available)
- `net flow` (net buy / sell pressure; if available)
- `warnings`: rendered ONLY when needed (degraded price
  staleness, untrusted migration source, pre-migration ATH risk,
  etc.).

## 7. Bounded private runtime semantics

The Stage 30.3 bounded private runtime session MUST:

- be private-operator-only (single private webhook identity, no
  fan-out).
- accept and honor an explicit operator-supplied `max_events`
  bound.
- accept and honor an explicit operator-supplied `max_candidates`
  bound when applicable.
- accept and honor an explicit operator-supplied `max_dispatches`
  bound.
- accept and honor an explicit operator-supplied
  `max_wall_seconds` bound.
- end with a clean closed-set `stop_reason`
  (`MAX_EVENTS` / `MAX_DISPATCHES` / `MAX_WALL_SECONDS` /
  `OPERATOR_STOP` / `RETRY_BUDGET_EXHAUSTED` / `ERROR`).
- write a redaction-safe final run summary at session end.

Implementation discipline:

- Stage 30.3 MUST reuse the existing
  `Stage28_6BoundedPrivateSessionRunner` (the Stage 28.6
  bounded private session runner) for the candidate loop, the
  dispatch ledger reservation, the bounded retry executor, the
  heartbeat emission, the health snapshot, and the final
  summary write. Stage 30 does NOT reimplement Stage 28.6.
- Stage 30.3 MAY ship a thin Stage 30 orchestrator that
  parallels Stage 29.3 mode-3 (rather than modifying it) so
  the Stage 29.3 production surface is untouched.

## 8. Required artifacts

Every Stage 30 bounded private session MUST emit the following
artifact families. Every artifact MUST be redaction-safe.

- **compact ping body snapshot** — one record per rendered
  compact ping, carrying the rendered body text, the operator-
  visible fields surfaced in the body, the basis used
  (`price-basis` / `mc-basis`), and the tier token. No webhook
  URL, no API key, no raw provider blob.
- **tier decision snapshot** — one record per tier decision,
  carrying the `drop` value, the `basis` used, the input
  `ath_status` / `migration_status` /
  `ath_since_migration_status`, the chosen tier token, and the
  closed-set tier reason.
- **price / ATH / migration context snapshot** — one record per
  dispatched candidate, carrying the Stage 27.4 context tokens
  (price_status / ath_status / migration_status) and the
  safe-to-display canonical fields used by the renderer. No raw
  provider blob.
- **dispatch ledger** — the existing Stage 28.2 dispatch ledger
  reused verbatim.
- **redaction scan** — a Stage 30 redaction scan over every
  Stage 30 artifact written during the session. The scan MUST
  report `SAFE` for every committed session.
- **final run summary** — the existing Stage 28.5 final run
  summary reused verbatim, augmented with Stage 30 counters
  (compact pings rendered, tiers emitted by token).

## 9. Ceremony discipline

- Stage 30 implementation substages (30.0 / 30.1 / 30.2 / 30.3
  / 30.4) MUST NOT send live Discord during implementation.
- Stage 30 implementation substages MUST NOT call live
  gRPC / HTTP / WebSocket providers during implementation
  (including but not limited to Chainstack Yellowstone,
  Birdeye, Helius, Dexscreener, or any other live data source).
- Stage 30 implementation substages MUST NOT read live secrets
  during implementation. Stage 30 implementation substages MAY
  reuse the unchanged Stage 28.11 / Stage 29.2 readiness
  boundaries through their existing optional
  `build_runtime_configs_from_env` helpers, but only at live
  ceremony time and only under separate explicit operator
  authorization.
- Any Stage 30.3 live ceremony requires separate explicit
  operator authorization before any live gRPC / HTTP / WS call
  or live Discord send. The live ceremony is run from outside
  the repo against the operator's own scratch workspace,
  mirroring the Stage 29.6 ceremony discipline.
- Stage 30 implementation substages MUST NOT tag, push, or
  close Stage 29 or Stage 30 without separate explicit operator
  authorization.

## 10. Acceptance criteria for Stage 30 overall

Stage 30 succeeds when:

- I can run a private bounded session on demand.
- I receive compact readable private Discord pings during that
  session.
- The renderer displays a tier only when context is safe; missing
  or degraded context renders `Tier Unknown` or
  `Tier Not Applicable` instead of inventing a tier.
- Missing values are visible (`Unknown`) instead of fabricated.
- The artifacts explain WHY each ping was Tier 1 / Tier 2 /
  Tier 3 / Tier Unknown / Tier Not Applicable.
- The Stage 30 redaction scan reports `SAFE` on every session.
- Zero public routing, zero paid / subscriber routing, zero
  enforcement, zero automated trading, zero wallet / signing
  surface, zero Telegram, zero X / social surface exists in
  Stage 30 at any substage.

Stage 30.0 acceptance is narrower:

- The four-file Stage 30.0 inventory ships, nothing else.
- `PHX2/tests/stage30/test_stage_30_0_spec_lock.py` passes.
- Existing Stage 27 / Stage 28 / Stage 29 tests pass unchanged.
- No commit, no tag, no push performed at Stage 30.0
  implementation time. Commit gating is a separate operator
  decision after audit.
