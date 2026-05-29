# PHX2 Stage 30.7.0 — ATH Context Bridge Spec Lock

Stage 30.7.0 is spec lock and tests only. Stage 30.7.0 ships exactly
two new files (this markdown and the Stage 30.7.0 spec-lock pin test)
plus one constants-only manifest module, plus one narrow test-only
allowlist widening on the Stage 30.0 inventory pin. Stage 30.7.0 ships
ZERO production `.py` file beyond the manifest, ZERO ATH bridge code,
ZERO renderer change, ZERO runtime wiring, ZERO source adapter, ZERO
live provider call, ZERO Discord send, ZERO candidate scan, and ZERO
modification to any Stage 25 / Stage 27 / Stage 28 / Stage 29
production source or to any Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 /
30.6 runtime source. Every Stage 30.7.1+ substage requires separately
authorized scope before any ATH bridge production `.py` file lands.

This document is the spec-lock / handoff contract for bridging
all-time-high (ATH) context into the compact private ping. It is prose
plus closed-set token tables. It carries no provider credential, no
private transport destination, no provider host address, no transport
scheme prefix, no raw provider payload, and no request auth metadata
(see Section 13).

## 1. Stage 30.7 scope and stance

Stage 30.7 is ATH context only. The single deliverable of the whole
Stage 30.7 family is moving the compact body `ATH` token from the
literal `Unknown` toward an honest, evidence-backed ATH display value,
and eventually supporting accurate drawdown / tier context derived
from that ATH.

The purpose of ATH context, pinned:

- Provide compact ATH display context for private operator pings.
- Preserve the existing `MC` / `LP` and `Mig` behavior exactly. Stage
  30.7 owns only the `ATH` token.
- Support later, accurate drawdown / tier context once the ATH source
  and unit are valid.
- Treat ATH as evidence-backed, not guessed. ATH is a measurement and
  evidence problem, never an estimate.

Stage 30.7 is explicitly:

- ATH context into compact private pings only.
- NO live. No live run of any kind in any Stage 30.7 implementation
  substage.
- NO Discord. No Discord send in any Stage 30.7 implementation
  substage.
- NO provider calls. No live gRPC / HTTP / WebSocket provider call of
  any kind (no Birdeye, no Dexscreener, no Chainstack, no Helius, no
  other live source) during implementation.
- NO candidate scan. No live candidate scan.
- NO enforcement. Stage 26 / Stage 29 enforcement stays inactive.
- NO filters. Filters stay observe-only unless separately promoted.
- NO storage writer, NO dedupe engine, NO database migration, NO
  filesystem writer, NO compression / archive implementation. Stage
  30.6 owns storage and dedupe; Stage 30.7 adds none of it.
- NO public or subscriber routing. The compact ping stays a single
  private operator surface.
- NO trading, NO wallet, NO signer surface.
- NO Telegram, NO X, NO social surface.

Stage 30.7.0 specifically is spec lock and tests only. Stage 30.7.0 is
NOT the ATH bridge implementation, is NOT live runtime, is NOT
Discord, and is NOT a tag or a closure. Stage 30.7.0 makes no commit,
no tag, and no push by itself.

ATH is a measurement / evidence problem. Stage 30.7.0 must not jam
live Birdeye calls, runtime sending, or tier enforcement into this
stage. The honest ATH market-cap basis is hard precisely because an
ATH market cap requires the circulating supply at the historical peak,
which no current source ships directly; Stage 30.7 therefore locks the
contract first and defers every live or wiring decision to a later,
separately authorized slice.

## 2. Starting point

The Stage 30.5 migration slices moved the `Mig` token from `Unknown`
toward an evidence-backed status word, and the Stage 30.4 market
context slices mapped `MC` / `LP` from a real source. The compact body
state line today reads, in sanitized form:

```
• MC: $X | ATH: Unknown | Mig: Known
```

Stage 30.7 only owns the `ATH` token on that line. The `MC` token, the
`Mig` token, the separators, the `Drop` / `Age` / `Net` line, the `LP`
line, and the `Basis` line are all out of Stage 30.7 scope. Stage 30.7
moves the `ATH` token from `Unknown` toward an honest displayed value:

```
• MC: $X | ATH: $Y | Mig: Known
```

Note on the current `ATH` slot. The Stage 30.2 renderer already fills
the `ATH` token from the existing `ath_mc_text` display slot, which was
reserved for a future ATH market-cap value. No source has ever
populated it, so the `ATH` token has only ever rendered `Unknown`.
Stage 30.7 gives that slot a trustworthy value by feeding it an
evidence-backed ATH display string. This is the same slot-reuse
pattern Stage 30.4.2 used to fill `MC` / `LP` through `current_mc_text`
/ `lp_text`, and Stage 30.5.2 used to fill `Mig` through
`migration_mc_text`, all without touching the renderer.

## 3. Stage 30-owned ATH contract

Stage 30 owns the compact ATH projection contract. Stage 30.7 defines
a small Stage-30-owned ATH context record and a projection adapter (in
a later substage; the dataclass / NamedTuple ships at Stage 30.7.1)
that turns evidence into a single safe compact `ATH` display string.

A potential future bridge may consume sanitized upstream ATH evidence
from Stage 25 / Stage 27 / Stage 29, but the Stage 30 compact runtime
must not directly depend on messy or live provider code. The boundary
is identical to the Stage 30.5 migration bridge boundary: Stage 30
reads a sanitized, duck-typed evidence shape and maps it onto Stage
30's own closed sets; it does not import a live provider client into
the compact runtime path. The upstream evidence side (Stage 25 ATH
candidates, the Stage 27.4 ATH context record, the Stage 29.2 Birdeye
ATH source) stays on the evidence side; Stage 30 owns only the compact
display contract.

The Stage-30-owned ATH context contract fields (defined here in prose;
the exact record ships at Stage 30.7.1):

- `token_label` — a short safe-shape redacted token label (the short
  `mint[:4] + ellipsis + mint[-4:]` form or a symbol-like label),
  never the full mint in the rendered `ATH` token. Mirrors the Stage
  30.4.1 / 30.5.1 `token_label` discipline.
- `ath_status` — one of the closed set `ATH_KNOWN` / `ATH_UNVERIFIED`
  / `ATH_UNKNOWN` (Section 5).
- `ath_display_value` — the already-formatted compact ATH display
  string (for example `$Y`) when, and only when, the evidence is
  trusted enough; otherwise absent so the renderer falls back to
  `Unknown`.
- `ath_unit` — one of the closed set `USD` / `SOL` / `UNKNOWN`
  (Section 6). The displayed ATH must share the same currency basis as
  the displayed `MC`, else the projection degrades to `Unknown`.
- `ath_basis` — one of the closed set `ATH_MARKET_CAP_OBSERVED` /
  `ATH_PRICE_DERIVED` / `ATH_BASIS_NONE` (Section 5). Records which
  evidence basis the ATH was derived from, analogous to the Stage
  30.5.1 `migration_basis` field.
- `source_label` — a short safe-shape source-family label. Never a
  host address, never a credential.
- `source_status` — one of the closed set `PRESENT` / `UNAVAILABLE` /
  `ERROR` / `STALE` / `CONFLICTING` (Section 7).
- `source_reason` — a closed-set source-reason token. The exact
  closed set is pinned at Stage 30.7.1, mirroring how Stage 30.5.0
  deferred the exact `source_reason` set to Stage 30.5.1.
- `runtime_consumable` — false / true semantics identical to Stage
  30.4.1 / 30.5.1: hard-locked `False` for the offline-only first
  record so an offline record can NEVER route into runtime; a later
  opt-in runtime substage may relax it only under the orchestrator
  boundary.

## 4. Display vocabulary and rendering

The compact ping `ATH` field stays simple. It has exactly two display
outcomes:

- `Unknown` — when the ATH is missing, untrusted, errored, stale,
  conflicting, non-finite, zero or negative, redaction-unsafe, or of
  an incompatible unit.
- a `$Y` formatted ATH value — only when the evidence is trusted
  enough (an `ATH_KNOWN` status with a valid value and unit).

Rendering rules, pinned:

- No verbose ATH debug text in the compact line. The `ATH` token is a
  single short string, never a paragraph, never a multi-line section.
- No raw provider IDs, signatures, or URLs in the display. No full
  mint, no signature, no event id, no provider host appears in the
  `ATH` token.
- No action verbs and no trading instruction language. The `ATH` token
  and the contract carry none of the closed-set trading-verdict /
  action substrings already pinned forbidden by the Stage 30 spec lock
  and enforced by the Stage 30.2 renderer.
- Preserve the line shape. The compact body keeps the exact same
  compact line shape; Stage 30.7 replaces only the `ATH` token:

```
• MC: <mc> | ATH: <ath> | Mig: <mig>
```

First-slice implementation approach (no renderer change). To honor the
no-change-to-Stage-30.2 constraint, the first wiring slice feeds the
ATH display string (a `$Y` value, or a `None` that renders `Unknown`)
through the existing `ath_mc_text` display slot that the Stage 30.2
renderer already maps to the `ATH` token. The Stage 30.2 renderer and
the Stage 30.2 models are NOT modified anywhere in the Stage 30.7
family; the renderer renders whatever short safe string occupies that
slot and falls back to `Unknown` when the slot is `None`.

## 5. Evidence confidence

Stage 30.7 locks an ATH confidence status closed set and an ATH basis
closed set.

ATH confidence status (`ath_status`):

| `ath_status` | meaning | compact `ATH` token |
|---|---|---|
| `ATH_KNOWN` | positive finite ATH value from a trusted, unit-compatible, observed-market-cap basis with no conflict and no redaction failure | the `$Y` value |
| `ATH_UNVERIFIED` | evidence exists but is not promotable to trusted (for example a price-derived basis, or a partial / untrusted source) | `Unknown` |
| `ATH_UNKNOWN` | the honest fallback for everything else | `Unknown` |

Only `ATH_KNOWN` renders a `$Y` value in the compact line. The
`ATH_UNVERIFIED` middle state is retained on the contract for
provenance and for the future drawdown / tier work, but it renders
`Unknown` in the compact line in the first slice because an unverified
ATH has no trustworthy value to display.

ATH basis (`ath_basis`):

| `ath_basis` | meaning |
|---|---|
| `ATH_MARKET_CAP_OBSERVED` | a directly observed / sourced ATH market-cap value; the only basis that can support `ATH_KNOWN` |
| `ATH_PRICE_DERIVED` | an ATH derived from an ATH price times a supply assumption; honesty-limited and at most `ATH_UNVERIFIED`, never `ATH_KNOWN`, in the first slice |
| `ATH_BASIS_NONE` | no basis |

A price-derived ATH market cap that assumes current supply is NEVER
promoted to `ATH_KNOWN`, because the circulating supply at the
historical peak is not guaranteed to match current supply. This echoes
the Stage 30 no-fabrication rule.

Known ATH requirements. An `ATH_KNOWN` status (and therefore a
displayed `$Y` value) requires ALL of:

- a positive finite ATH value,
- a trusted source status (`PRESENT`),
- a compatible price / market context (same currency basis as the
  displayed `MC`),
- an observed-market-cap basis (`ATH_MARKET_CAP_OBSERVED`),
- no redaction or safety failure,
- no conflicting evidence.

Unknown dominates. The `ATH` token renders `Unknown` whenever any of:

- source missing,
- source error,
- source stale,
- conflicting evidence,
- a non-finite value,
- a zero or negative value,
- redaction unsafe,
- an incompatible unit or an ambiguous currency.

## 6. Unit and currency safety

ATH must not mix incompatible units. The spec distinguishes:

- USD-denominated ATH context.
- SOL-denominated ATH context, if supported later.
- `Unknown` if the unit is unsupported or ambiguous.

Locked rules:

- Never treat USD as SOL or SOL as USD. A USD-denominated ATH must
  never be compared against, or displayed alongside, a SOL-denominated
  `MC`, and vice versa.
- The displayed ATH must share the same currency basis as the
  displayed `MC`. When the bases disagree, the `ATH` token renders
  `Unknown` rather than silently mixing units.
- Display must make unit assumptions explicit. Future Stage 30.7.x
  tests must assert the unit assumption for every displayed ATH value
  so a USD-vs-SOL confusion is caught at test time.

## 7. Source dominance

Like the Stage 30.5 migration context, the ATH source status dominates
any claimed ATH value.

- A bad source status dominates the claimed ATH value. A non-`PRESENT`
  source status (`UNAVAILABLE` / `ERROR` / `STALE` / `CONFLICTING`)
  degrades the projection to `Unknown` regardless of any value the
  evidence carries.
- A `PRESENT` source status can display a known ATH only when the
  value and the unit are valid (positive, finite, unit-compatible,
  observed-market-cap basis, no conflict).
- `ERROR`, `UNAVAILABLE`, `STALE`, and `CONFLICTING` all render
  `Unknown`.

The ATH source status closed set adds `CONFLICTING` beyond the Stage
30.5 migration source-status set, because cross-source ATH
disagreement (two sources reporting materially different peaks) is a
real ATH failure mode and must degrade conservatively to `Unknown`
rather than picking a peak.

## 8. Drawdown and tier dependency

- Stage 30.7.0 does not implement drawdown or tier recomputation. The
  existing `Drop` and tier display behavior is unchanged by Stage
  30.7.0.
- A future Stage 30.7.x may project ATH into the compact ping and,
  separately, into a more accurate drawdown / tier context.
- The tier decision and the drop display must only become trusted
  after the ATH source and unit are valid. An ATH that is not
  `ATH_KNOWN` cannot anchor a trusted drawdown.
- If the ATH is unknown, the drop and tier display may remain the
  existing placeholder or stay conservative. Stage 30.7 never forces a
  drawdown from an untrusted ATH.

## 9. Sanitization and no raw leakage

The Stage 30 compact ATH contract carries only closed-set tokens, a
single short safe-shape ATH display string (a `$Y` value or
`Unknown`), a short safe-shape source-family label, and safe-shape
ISO-8601 timestamps. The contract stores and renders NONE of the
following:

- raw transaction signatures,
- raw event logs,
- the `source_event_ref` / `raw_capture_ref` / migration or trade
  event ids,
- raw provider payloads,
- provider URLs or provider host addresses,
- transport scheme prefixes,
- HTTP header metadata or request auth metadata,
- a private transport destination,
- Discord message body text,
- any secret, signed-token credential, or environment value.

A forbidden-field-name guard (mirroring the Stage 30.2, Stage 30.4.1,
and Stage 30.5.1 guards) will reject any future refactor that tries to
widen the ATH record with a secret-class or raw-payload-class field
name.

## 10. Prior art and reuse

Stage 30.7 should not duplicate ATH measurement logic. The existing
ATH evidence shapes on the evidence side are:

- the Stage 25 ATH candidate builder, which selects a deterministic
  per-source post-migration peak and carries a confidence level
  (`NONE` / `LOW` / `MEDIUM`) and an `INSUFFICIENT_DATA` placeholder
  for groups with no eligible window. Stage 25 already excludes
  pre-migration data from any peak.
- the Stage 27.4 ATH context record, which carries a canonical
  decimal-text `ath_value`, an `ath_unit` (`SOL` / `USDC` / `USD` /
  `UNKNOWN`), an `ath_status` (`PRESENT` / `STALE` / `UNAVAILABLE` /
  `NOT_APPLICABLE` / `UNSUPPORTED_PAIR` / `SOURCE_ERROR`), an
  `ath_since_migration_status` (`POST_MIGRATION_ONLY` /
  `MAY_INCLUDE_PRE_MIGRATION` / `UNKNOWN` / `NOT_APPLICABLE`), and a
  `drawdown_basis`. Stage 27.4 already refuses to claim
  `POST_MIGRATION_ONLY` without an explicit upstream promise.
- the Stage 29.2 Birdeye ATH source, which implements the Stage 27.4
  ATH source protocol over a live transport and reports in USD. This
  is the live, messy provider source; the Stage 30 compact runtime
  must NOT depend on it directly.

A future Stage 30.7.3 bridge consumes a sanitized, duck-typed copy of
this evidence and maps it onto the Stage 30 closed sets, mirroring the
Stage 30.5.3 migration bridge. The no-evidence fallback mirrors the
Stage 29.3 no-evidence source: when no ATH evidence is available, the
projection is `ATH_UNKNOWN` with an `UNAVAILABLE` source status, never
a fabricated peak.

## 11. Non-goals

Stage 30.7.0 explicitly does NOT:

- implement the ATH bridge,
- call Birdeye, call Dexscreener, or call any provider,
- change the renderer or the runtime,
- write a database or files,
- compress archives,
- implement a dedupe or storage writer,
- implement filters or enforcement,
- route public or subscriber pings,
- trade or sign transactions.

## 12. Future slices

The Stage 30.7 family follows the established Stage 30.4 / Stage 30.5
discipline: fake / offline before live, smallest reversible slice
first.

- Stage 30.7.0 — ATH context bridge spec lock and tests only (this
  commit). No ATH bridge production `.py`.
- Stage 30.7.1 — ATH context models + pure projection adapter, with
  fakes only. No live, no provider. Mirrors Stage 30.5.1.
- Stage 30.7.2 — fake-wire the ATH projection into the compact ping
  using the existing `ath_mc_text` slot, opt-in parallel orchestrator;
  the Stage 30.1 / 30.2 / 30.3 runtime stays unchanged. Mirrors Stage
  30.5.2.
- Stage 30.7.3 — bridge sanitized Stage 25 / 27 / 29 ATH evidence into
  the Stage 30 ATH resolver, fake tests only, under a narrow import
  allowlist. Mirrors Stage 30.5.3.
- Stage 30.7.4 — offline runtime proof with `MC` + `Mig` + `ATH`
  together, NO Discord. Mirrors Stage 30.5.4 / Stage 30.4.3D.
- Stage 30.7.5 — controlled live ATH probe / dry-run only, and only
  after a separate audit and only if separately operator-authorized.
  Mirrors Stage 30.4.3C / 30.4.3E.

The sequence may be refined by a later audit, but the principle is
fixed: every offline / fake slice lands and is proven before any live
or Discord slice is even authorized.

## 13. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage 30.5.0
and Stage 30.6.0 spec locks. It carries no provider credential
strings, no private transport destination strings, no provider host
address strings, no transport scheme prefixes, no raw request-payload
or response-payload field names, and no request auth-metadata strings.
It records only closed-set status tokens, closed-set basis tokens,
field names, prose, and the sanitized starting and target body lines.

The Stage 30.7.0 pin test enforces this by scanning this document, the
manifest, and the pin test itself, case-insensitively, against a
split-literal forbidden-substring vocabulary, so the document's own
source cannot carry any of the sanitized-away substrings even inside a
negative claim.

---

_Stage 30.7.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.7.0 implementation.
- There is no Discord send during Stage 30.7.0 implementation.
- There is no candidate scan during Stage 30.7.0 implementation.
- There is no runtime logic change and no Stage 25 / 27 / 28 / 29
  production change at Stage 30.7.0.
- There is no Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 / 30.6 runtime
  change at Stage 30.7.0.
- There is no ATH bridge implementation at Stage 30.7.0.
- There is no database migration and no filesystem writer at Stage
  30.7.0.
- There is no compression and no archive implementation at Stage
  30.7.0.
- There is no filter and no enforcement at Stage 30.7.0.
- There is no commit, no tag, and no push performed by Stage 30.7.0
  implementation. Commit gating is a separate operator decision after
  audit.
