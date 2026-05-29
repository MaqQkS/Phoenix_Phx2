# PHX2 Stage 30.5.0 — Migration Context Into Compact Pings Spec Lock

Stage 30.5.0 is spec lock and tests only. Stage 30.5.0 ships exactly
two new files (this markdown and the Stage 30.5.0 spec-lock pin
test) plus one narrow test-only allowlist widening on the Stage
30.0 inventory pin. Stage 30.5.0 ships ZERO production `.py` file,
ZERO renderer change, ZERO runtime wiring, ZERO source adapter,
ZERO bridge, ZERO live provider call, ZERO Discord send, ZERO
candidate scan, and ZERO modification to any Stage 27 / Stage 28 /
Stage 29 production source or to any Stage 30.1 / 30.2 / 30.3 / 30.4
runtime source. Every Stage 30.5.1+ substage requires separately
authorized scope before any production `.py` file lands.

This document is the spec-lock / handoff contract for wiring
migration context into the compact private ping. It is prose plus
closed-set token tables. It carries no provider credential, no
private transport destination, no provider host address, no raw
provider payload, and no request auth metadata (see Section 9).

## 1. Stage 30.5 scope

Stage 30.5 is migration context only. The single deliverable of the
whole Stage 30.5 family is moving the compact body `Mig` token from
the literal `Unknown` toward an honest, evidence-backed migration
status token.

Stage 30.5 is explicitly:

- migration context into compact private pings only.
- NO ATH. ATH context stays out of Stage 30.5 (see Section 8).
- NO Net. Net flow stays deferred (Stage 30.4 already pins it
  deferred and Unknown).
- NO live. No live run of any kind in any Stage 30.5 implementation
  substage.
- NO Discord. No Discord send in any Stage 30.5 implementation
  substage.
- NO provider calls. No live gRPC / HTTP / WebSocket provider call
  of any kind (no Chainstack, no Helius, no Birdeye, no
  Dexscreener, no other live source) during implementation.
- NO candidate scan. No live candidate scan.
- NO enforcement. Stage 26 / Stage 29 enforcement stays inactive.
- NO public or subscriber routing. The compact ping stays a single
  private operator surface.
- NO trading, NO wallet, NO signer surface.
- NO Telegram, NO X, NO social surface.

Stage 30.5.0 specifically is spec lock and tests only. Stage 30.5.0
is NOT live runtime implementation, is NOT Discord, is NOT ATH, and
is NOT a tag or a closure. Stage 30.5.0 makes no commit, no tag, and
no push by itself.

Stage 30.5 does NOT modify Stage 27 / Stage 28 / Stage 29 production
code. If a future Stage 30.5 bridge substage finds a strictly
required narrow read-only reuse of an existing Stage 29.5 evidence
module, that reuse is documented in that substage's own spec lock
under a narrow import allowlist (mirroring the Stage 30.4.3 Stage
29.2 reuse allowlist pattern) and stops short of any in-place
production edit. Stage 30.5 does NOT change Stage 30.1 / 30.2 / 30.3
compact runtime behavior in the first slice.

## 2. Starting point

The Stage 30.4.3E controlled private proof delivered the compact
body with this state line (MC and LP mapped from a real source;
ATH and Mig still Unknown):

```
• MC: $7.4k | ATH: Unknown | Mig: Unknown
```

Stage 30.5 only owns the `Mig` token on that line. The `MC` token,
the `ATH` token, the `Drop` / `Age` / `Net` line, the `LP` line, and
the `Basis` line are all out of Stage 30.5 scope. Stage 30.5 moves
the `Mig` token from `Unknown` toward `Known` (or another explicit
closed-set migration status token defined in Section 3).

Note on the current `Mig` slot. The Stage 30.2 renderer currently
fills the `Mig` token from the `migration_mc_text` display slot,
which was reserved for a future migration market-cap value. Stage
30.4 pins Migration MC as a deferred field with no source, so the
`Mig` token has only ever rendered `Unknown`. Stage 30.5 gives the
`Mig` slot a meaning by feeding it a migration **status** token. A
numeric migration market-cap value remains a separate deferred
field and is NOT introduced by Stage 30.5.

## 3. Target compact display options

### 3.1 Active closed set (Stage 30.5)

The `Mig` token is drawn from a closed set of three status tokens.
The renderer never invents a token outside this set; missing or
ambiguous evidence renders `Mig: Unknown`.

- `Mig: Known`
- `Mig: Unverified`
- `Mig: Unknown`

Justification from existing Stage 29.5 evidence:

| Stage 29.5 evidence basis | `migration_basis` | `Mig` token |
|---|---|---|
| `COMPLETE` measurement + trusted on-chain source (`HELIUS_WS` / `STAGE29_MIGRATION_ARTIFACT`) + event time present (equivalently the Stage 27.4 `ON_CHAIN_MIGRATION_EVENT` snapshot the Stage 29.5.4 adapter already produces) | `ON_CHAIN_EVENT` | `Known` |
| `PARTIAL_MIGRATION_PRESENT`, or `COMPLETE` with a `SYNTHETIC_TEST_ONLY` / `UNKNOWN` source (evidence exists but is not promotable to trusted) | `EVIDENCE_PARTIAL` | `Unverified` |
| `MISSING_MIGRATION` / `INVALID_MIGRATION` / `CONFLICTING_MIGRATION` / no source / source error / ambiguous / absent | `NONE` | `Unknown` |

`Known` is the conservative trusted-migration signal already used by
the Stage 29.5.4 adapter and the Stage 29.5.5 source-trust matrix
(`SOURCE_TRUSTED_ON_CHAIN`). `Unverified` is the evidence-present-
but-not-trusted middle state the Stage 29.5.5 matrix already
distinguishes (`SOURCE_PARTIAL_*` / `SOURCE_UNTRUSTED_*`).
`Unknown` is the honest fallback for everything else.

When the bridge consumes only the coarse Stage 27.4
`MigrationSourceSnapshot` feed (which collapses to
`ON_CHAIN_MIGRATION_EVENT` vs `MIGRATION_SOURCE_UNKNOWN`), the
`Unverified` middle state collapses conservatively into `Unknown`.
`Unverified` is available only when the richer Stage 29.5 projection
feed (`measurement_status` + `migration_source`) is used.

### 3.2 Deferred display tokens

`Mig: Fresh` and `Mig: Stale` are deliberately NOT in the active
closed set at Stage 30.5.0. They are deferred. Existing Stage 29.5
evidence cannot justify them safely yet:

- Fresh / Stale require an age-vs-threshold freshness policy, and no
  such migration freshness threshold is pinned anywhere in Stage
  29.5.
- The migration event time and the age-since-migration already flow
  to the separate `Age` field on the compact body. Folding a
  freshness verdict into the `Mig` token would duplicate `Age` and
  would require its own basis decision.

Fresh / Stale may be revisited in a later Stage 30.5.x only after a
migration freshness basis is separately pinned. They are not part of
Stage 30.5.0.

## 4. Source contract

Stage 30 owns the compact display contract. Stage 30.5 defines a
small Stage-30-owned migration context record and a source protocol
that a later substage feeds from Stage 29.5 evidence. The contract
fields (defined here in prose; the dataclass / NamedTuple ships at
Stage 30.5.1):

- `token_mint` (or a normalized candidate identity) — the candidate
  the migration status describes. The record stores only a safe-
  shape redacted token label (the short `mint[:4] + ellipsis +
  mint[-4:]` form or a symbol-like label), never the full mint in
  the rendered `Mig` token. Mirrors the Stage 30.4.1 `token_label`
  discipline.
- `migration_status` — one of the closed set `KNOWN` / `UNVERIFIED`
  / `UNKNOWN` (Section 3). The renderer maps these to the `Mig:
  Known` / `Mig: Unverified` / `Mig: Unknown` display tokens.
- `migration_basis` — one of the closed set `ON_CHAIN_EVENT` /
  `EVIDENCE_PARTIAL` / `NONE` (Section 3). Records which evidence
  basis the status was derived from, analogous to the Stage 30.4.1
  `net_flow_basis` field.
- `migration_event_time` — the migration event UTC ISO-8601
  timestamp when available (sourced from the Stage 29.5
  `migration_timestamp_utc`), otherwise absent. Carried for
  provenance; it does NOT itself appear in the `Mig` token.
- `migration_age_seconds` — an optional non-negative integer age
  since migration, computed by the caller from an injected clock
  (never `datetime.now`). Carried for completeness and for the
  future Fresh / Stale decision; in the first slice it feeds the
  existing `Age` field, never the `Mig` token.
- `source_label` — a short safe-shape source-family label (for
  example `stage29_5_migration_evidence`). Never a host address,
  never a credential.
- `source_status` — one of the closed set `UNAVAILABLE` / `PRESENT`
  / `ERROR` / `STALE` (mirrors the Stage 30.4.1 source-status set).
- `source_reason` — a closed-set source-reason token (for example
  `SOURCE_NOT_CONFIGURED` / `SOURCE_PRESENT` / `EVIDENCE_INVALID` /
  `EVIDENCE_PARTIAL` / `SOURCE_STALE`). The exact closed set is
  pinned at Stage 30.5.1.
- `runtime_consumable` — false / true semantics identical to Stage
  30.4.1: hard-locked `False` for the offline-only Stage 30.5.1
  record so an offline record can NEVER route into runtime; a later
  opt-in runtime substage (Stage 30.5.2) may set it `True` only
  under the orchestrator boundary.

Redaction expectations. The record carries only closed-set tokens,
safe-shape opaque identifier echoes, safe-shape ISO-8601 timestamps,
and a short safe-shape source label. It carries no full mint in the
display token, no migration signature, no migration event id, no
source event ref, no raw provider payload, no provider credential,
no provider host address, and no private transport destination. A
forbidden-field-name guard (mirroring the Stage 30.2 and Stage
30.4.1 guards) rejects any future refactor that tries to widen the
record with a secret-class or raw-payload-class field name.

## 5. Rendering rule

The compact body keeps the exact same compact line shape. Stage 30.5
replaces only the `Mig` token:

```
• MC: <mc> | ATH: <ath> | Mig: <mig>
```

- Keep the same compact line shape. The `MC` and `ATH` tokens, the
  separators, and every other body line are untouched.
- Replace only the `Mig` token with one of `Known` / `Unverified` /
  `Unknown`.
- Do not expand into a verbose block. The `Mig` token is a single
  short word, never a paragraph, never a multi-line section.
- No action verbs. No trading instruction language. The `Mig` token
  and the contract carry none of the closed-set trading-verdict /
  action substrings already pinned forbidden by the Stage 30 spec
  lock Section 4 and enforced by the Stage 30.2 renderer.
- No raw IDs unless public and safe. No full mint, no signature, no
  event id appears in the `Mig` token.
- If the source is missing or ambiguous, render `Mig: Unknown`.

First-slice implementation approach (no renderer change). To honor
the no-change-to-Stage-30.2 constraint, the first slice feeds the
migration status display word (`Known` / `Unverified` / a `None`
that renders `Unknown`) through the existing `migration_mc_text`
display slot that the Stage 30.2 renderer already maps to the `Mig`
token. The Stage 30.2 renderer is NOT modified in Stage 30.5.1 /
30.5.2; it renders whatever short safe string occupies that slot and
falls back to `Unknown` when the slot is `None`. This is the same
slot-reuse pattern Stage 30.4.2 used to fill `MC` / `LP` through
`current_mc_text` / `lp_text` without touching the renderer. The
field is named for a market-cap value for historical reasons; the
`Mig` body label is generic enough to carry either a value or a
status token. Whether to later rename or split that slot is a
separate decision deferred past the first slice.

## 6. Stage 29.5 handoff

Stage 30.5 should not duplicate migration evidence logic. Stage 29.5
remains the migration evidence / source side; Stage 30 owns only the
compact display contract. The eventual evidence feed for the
Stage-30-owned record is:

- the Stage 29.5.4 migration context source adapter
  (`stage29_5_4_migration_context_source_adapter`), which already
  projects Stage 29.5 evidence onto a Stage 27.4
  `MigrationSourceSnapshot` (`ON_CHAIN_MIGRATION_EVENT` vs
  `MIGRATION_SOURCE_UNKNOWN`) via a conservative closed-set matrix;
  and / or
- the Stage 29.5 `Stage29_5PrivatePingMigrationContext` projection
  (`measurement_status` + `migration_source` +
  `migration_timestamp_utc`), which carries the richer evidence
  needed to distinguish `Unverified`.

Hard boundary: Stage 30.5 must NOT import the Stage 29.5.5 private
Discord side-channel renderer
(`stage29_5_5_private_discord_migration_context_renderer`), the
Stage 29.5.5 recorder
(`stage29_5_5_migration_context_recorder`), or the Stage 29.5.5
side-channel artifact writer
(`stage29_5_5_side_channel_artifact_writer`). Those are the side-
channel rendering surface and must stay on the Stage 29.5 side. The
Stage 30 compact renderer must not depend on Discord-rendering side-
channel code.

The following Stage 29.5 surfaces are side-channel / audit only and
must NOT be rendered into the compact body:

- the Stage 29.5.5 verbose multi-line `body_text` block;
- the Stage 29.5.5 closed-set display vocabulary
  (`MIGRATION_EVIDENCE_COMPLETE`, `SOURCE_TRUSTED_ON_CHAIN`, etc.) —
  Stage 30 owns its own short closed set instead;
- the audit identifiers `migration_event_id` / `source_event_ref` /
  `raw_capture_ref` and the evidence `migration_signature`;
- `migration_slot`, `join_status_echoed`, `warnings`,
  `post_migration_ath_verified`, `redaction_status`,
  `filter_enforcement_status`, `observed_at_utc`, and the schema
  version provenance fields.

## 7. Proposed substage sequence

The Stage 30.5 family follows the established Stage 30.4 discipline:
fake / offline before live, smallest reversible slice first.

- Stage 30.5.0 — spec lock and tests only (this commit). No
  production `.py`.
- Stage 30.5.1 — Stage-30-owned migration context models + source
  protocol + adapter, with fakes only. No Stage 29 import. Mirrors
  Stage 30.4.1.
- Stage 30.5.2 — compact renderer / runtime dry-run with a fake
  migration context, filling the `Mig` slot via the existing
  display slot. Opt-in parallel orchestrator; Stage 30.1 / 30.2 /
  30.3 runtime stays unchanged. Mirrors Stage 30.4.2.
- Stage 30.5.3 — Stage 29.5 evidence to Stage-30 record bridge,
  fake tests only, under a narrow Stage 29 import allowlist (the
  Stage 29.5.4 adapter / the Stage 29.5 projection / the Stage 27.4
  snapshot shape, and NOT the Stage 29.5.5 side-channel surface).
  Mirrors Stage 30.4.3.
- Stage 30.5.4 — controlled private dry-run with real existing
  evidence if available, NO Discord. Mirrors Stage 30.4.3D.
- Stage 30.5.5 — controlled private Discord proof with `Mig` filled,
  only if separately operator-authorized. Mirrors Stage 30.4.3E.

The sequence may be refined by a later audit, but the principle is
fixed: every offline / fake slice lands and is proven before any
live or Discord slice is even authorized.

## 8. Handoff to ATH

ATH is not part of Stage 30.5.

- ATH context remains Stage 30.6 (or a later Stage 30.5.x only after
  migration context is clean and closed).
- Stage 30.5.0 does not wire ATH. No ATH mapping, no ATH basis, no
  ATH display change ships in any Stage 30.5 migration slice.
- ATH needs its own separate evidence and basis mapping (an honest
  ATH market-cap basis requires historical supply that no current
  source ships), so it is a separate spec-locked decision and must
  not be mixed into Stage 30.5.

Do not mix ATH into Stage 30.5.0. The `ATH` token on the compact
body stays `Unknown` through the entire Stage 30.5 family.

## 9. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage
30.4.4 proof record. It carries no provider credential strings, no
private transport destination strings, no provider host address
strings, no transport scheme prefixes, no raw request-payload or
response-payload field names, and no request auth-metadata strings.
It records only closed-set status tokens, closed-set basis tokens,
field names, prose, and the single sanitized starting body line.

The Stage 30.5.0 pin test enforces this by scanning this document,
case-insensitively, against a split-literal forbidden-substring
vocabulary, so the document's own source cannot carry any of the
sanitized-away substrings even inside a negative claim.

---

_Stage 30.5.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.5.0
  implementation.
- There is no Discord send during Stage 30.5.0 implementation.
- There is no candidate scan during Stage 30.5.0 implementation.
- There is no runtime logic change and no Stage 27 / 28 / 29
  production change at Stage 30.5.0.
- There is no Stage 30.1 / 30.2 / 30.3 runtime change at Stage
  30.5.0.
- There is no ATH implementation at Stage 30.5.0.
- There is no commit, no tag, and no push performed by Stage 30.5.0
  implementation. Commit gating is a separate operator decision
  after audit.
