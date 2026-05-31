# PHX2 Stage 30.10.0 — Compact Tier-Dip Eligibility Gate Spec Lock

Stage 30.10.0 is spec lock and tests only. Stage 30.10.0 ships exactly
three new files (this markdown, `stage30_10_manifest.py`, and the Stage
30.10.0 spec-lock pin test) plus one narrow test-only allowlist widening on
the Stage 30.0 inventory pin and one narrow guard widening on the Stage
30.9.0 inventory pin (so the Stage 30.10.0 scaffold is admitted while Stage
30.10.1+ and Stage 31 stay forbidden). Stage 30.10.0 ships ZERO production
`.py` file beyond the constants-only manifest, ZERO eligibility classifier,
ZERO audit-record model, ZERO runtime wiring, ZERO artifact integration,
ZERO new live runner, ZERO new provider, ZERO new readiness gate, ZERO
direct Stage 28 suppression-logic edit, ZERO live provider call, ZERO
Discord send, ZERO live run, ZERO env read, ZERO database, ZERO SQLite,
ZERO zstd dependency or implementation, ZERO compression, ZERO default
storage root, ZERO broad always-on daemon, ZERO public / subscriber / paid
routing, ZERO Telegram / X / social, ZERO trading / wallet / signing, ZERO
enforcement, ZERO Stage 31, and ZERO edit to any existing live runner /
orchestrator / transport / Stage 28 suppression implementation file. Every
Stage 30.10.1+ substage requires separately authorized scope before any
production `.py` file lands.

This document is the spec-lock / handoff contract for adding the missing
compact tier-dip eligibility gate so private compact pings are dip-focused
instead of pinging every migrated / tradeable candidate. It is prose plus
closed-set token tables. It carries no provider credential, no private
transport destination, no provider host address, no transport scheme
prefix, no raw request / response payload field name, and no request
auth-metadata (see Section 13).

The single most important Stage 30.10 planning finding: the live compact
path can ALREADY render the tier / ATH / drawdown labels, but it does NOT
use them to decide whether to send. A tradeable Stage 27.6 candidate from a
provider hint event is dispatched whenever it is not malformed, not deduped,
and not otherwise suppressed — the displayed tier is never consulted. Stage
30.10 adds the missing gate so only a compact tier-dip eligible candidate is
sent. Stage 30.10 does NOT build a new live runner, does NOT build a new
provider, and does NOT reimplement readiness or suppression.

## 1. Purpose

Stage 30.10 is the compact tier-dip eligibility gate. Its purpose is to make
private compact pings dip-focused. The target behavior:

- only send a private compact ping when the candidate is an actual tier-dip
  opportunity;
- reuse the existing Stage 30.1 `decide_tier` / `TierDecisionRecord` tier
  projection and the existing ATH / migration / market context (no new tier
  model);
- turn the tier / ATH / drawdown signals into an active dispatch
  eligibility decision instead of a display-only label; and
- emit one eligibility audit record per evaluated candidate.

The bot must NOT ping every migrated token. The bot must NOT ping every
tradeable candidate. The bot must ping only compact tier-dip eligible
candidates.

Stage 30.10.0 specifically is spec lock and tests only. Stage 30.10.0 is NOT
an eligibility classifier, is NOT an audit-record model, is NOT a runtime
wiring, is NOT an artifact integration, is NOT a live run, is NOT a Discord
send, and is NOT a tag / push / closure. Stage 30.10.0 makes no commit, no
tag, and no push by itself.

## 2. Non-purpose

Stage 30.10 is explicitly NOT, and Stage 30.10.0 implements no part of, any
of the following. Stated as the closed non-purpose list (each is a hard
negative):

- NOT a new live runner;
- NOT a new provider;
- NOT a new readiness gate;
- NOT a direct edit of Stage 28 suppression logic;
- NOT a public bot;
- NOT subscriber routing;
- NOT paid / tier routing;
- NOT Telegram / X / social;
- NOT trading / wallet / signing;
- NOT enforcement activation;
- NOT a broad always-on daemon / background service;
- NOT a database / SQLite store;
- NOT a zstd / compression layer;
- NOT a default real storage root; and
- NOT Stage 31.

## 3. Locked audit findings

The prior read-only audit found that the live compact path renders the
tier / ATH / drawdown labels but never uses them to decide whether to send.
These findings are LOCKED so Stage 30.10 corrects exactly this gap:

1. **Current ping trigger.** A tradeable Stage 27.6 candidate from a
   provider hint event.
2. **Final dispatch decision.** `map_stage27_candidate_to_stage28_6_event`
   sets `dispatch_allowed = not malformed`; the
   `Stage28_6BoundedPrivateSessionRunner` suppresses only malformed /
   unknown-pair / disagree-pair / USDC-observe-only / stale-price /
   missing-price / dedupe; the `Stage30_3CompactBodyTransportWrapper` only
   blocks render failure; no tier / dip / ATH gate exists on the dispatch
   path.
3. **ATH / drawdown.** `decide_tier` computes the drawdown and the tier
   bands, but its output is render / display only — not active as dispatch
   eligibility.
4. **Tier decision.** Stage 30.1 tier records exist and the `tier_token`
   appears in the compact body, but the `tier_token` is not used to decide
   whether to send.
5. **Migration.** Migration context is trigger / filter / display context,
   not a dip gate.
6. **If live proof ran today.** It would likely emit migrated / tradeable
   compact pings, many `Tier Unknown` / `Tier Not Applicable`, not true
   dip-filtered alerts.

Stage 30.10 exists to make the tier / ATH / drawdown signals become dispatch
eligibility, not display-only.

## 4. Gate placement

The eligibility gate MUST be evaluated BEFORE dispatch reservation and
BEFORE the private Discord send. The locked placement contract:

- the gate runs BEFORE the `Stage28_6BoundedPrivateSessionRunner` reserves
  dispatch intent;
- the gate runs BEFORE any private send;
- a normal non-dip skip is a clean no-send, NOT a dispatch failure; and
- the tier / ATH / drawdown signals become dispatch eligibility, not
  display-only.

Do NOT gate at the transport layer if that would count suppressed non-dips
as dispatch failures. Specifically, Stage 30.10 must NOT reuse the Stage
28.4 / Stage 30.3 `PAYLOAD_REFUSED` transport-veto path for a normal non-dip
skip: there is no transport-layer veto for a normal non-dip skip. A non-dip
candidate is simply not reserved and not sent; it never becomes a
`PAYLOAD_REFUSED`-style transport failure.

## 5. Existing logic reuse

Stage 30.10 MUST reuse the existing logic. It introduces NO new tier model
and NO new provider. The locked reuse surfaces, by exact name:

- `decide_tier` — the Stage 30.1 tier projector entry that classifies the
  drawdown into a tier band.
- `TierDecisionRecord` — the Stage 30.1 immutable tier decision record that
  carries the `tier_token`, the `tier_reason`, the echoed `drawdown_from_ath`
  / `drop_positive`, the `ath_status`, and the `migration_status`.
- the Stage 30.1 tier projection — the `tier_token` closed set (`Tier 1` /
  `Tier 2` / `Tier 3` / `Tier Unknown` / `Tier Not Applicable`).
- the existing ATH context — the ATH presence / drawdown evidence.
- the existing migration context — the migration presence / status.
- the existing MC / LP / current market context — the current market-cap /
  price availability.
- the existing Stage 30.9 compact / artifact lane — where the eligibility
  audit record will eventually be persisted.
- the existing Stage 28 / 29 / 30 live runner / gates — Stage 30.10 wraps
  and observes this path; it does NOT fork it and does NOT reimplement it.

## 6. Eligibility policy

The default operator policy is fail-closed: send ONLY a compact tier-dip
eligible candidate; suppress everything else. The locked default policy:

- SEND if `tier_token` is `Tier 1`, `Tier 2`, or `Tier 3`;
- SKIP if `Tier Unknown`;
- SKIP if `Tier Not Applicable`;
- SKIP if missing ATH;
- SKIP if missing migration;
- SKIP if missing drawdown;
- SKIP if invalid market context;
- SKIP if current MC / price unavailable; and
- fail closed, not fail open.

In short: allow only `Tier 1` / `Tier 2` / `Tier 3`; suppress
`Tier Unknown`, `Tier Not Applicable`, missing ATH, missing migration, and
missing market context.

The bot should NOT ping every migrated token, should NOT ping every
tradeable candidate, and should ping only compact tier-dip eligible
candidates.

## 7. Policy config

The policy is an EXPLICIT policy object / config, never a hidden env read.
The locked config fields and their default values:

- `allowed_tiers = ("TIER_1", "TIER_2", "TIER_3")` — the allowed tier band
  codes (mapping to the `tier_token` display values `Tier 1` / `Tier 2` /
  `Tier 3`).
- `require_post_migration_ath = True` — require a post-migration ATH;
  suppress missing ATH.
- `require_migration_present = True` — require migration context; suppress
  missing migration.
- `require_current_market_context = True` — require current MC / price;
  suppress missing / invalid market context.
- `fail_closed_on_unknown = True` — suppress `Tier Unknown` /
  `Tier Not Applicable` and any degraded / missing input.

There is NO hidden env read: the policy is passed explicitly. There is no
default real storage root and no implicit configuration source.

## 8. Eligibility decisions and audit record

Stage 30.10 emits exactly one eligibility decision per evaluated candidate,
drawn from this closed set:

- `ELIGIBLE_DIP` — a compact tier-dip eligible candidate (the only
  send-allowed decision);
- `SKIPPED_NOT_DIP` — an in-band tier excluded by the active policy;
- `SKIPPED_TIER_UNKNOWN` — `Tier Unknown`;
- `SKIPPED_TIER_NOT_APPLICABLE` — `Tier Not Applicable`;
- `SKIPPED_MISSING_ATH` — missing / unusable ATH;
- `SKIPPED_MISSING_MIGRATION` — missing migration;
- `SKIPPED_MISSING_MARKET_CONTEXT` — missing / invalid market context or
  unavailable current MC / price; and
- `INVALID_INPUT` — malformed / unusable evaluation input.

`ELIGIBLE_DIP` is the only decision that allows a downstream send; every
other token is a no-send.

Stage 30.10 emits one eligibility audit record per evaluated candidate. The
locked audit-record fields:

- `candidate_id` — the safe-shape candidate identifier.
- `token_mint` — the safe-shape token mint.
- `tier_token` — the echoed Stage 30.1 tier token.
- `drawdown_from_ath` — the echoed canonical decimal-text drawdown, when
  available.
- `drop_positive` — the echoed canonical decimal-text positive drop, when
  available.
- `migration_status` — the echoed migration status.
- `ath_status` — the echoed ATH status.
- `decision` — one of the eligibility-decision closed set above.
- `reason` — a closed-set reason token explaining the decision.
- `created_at_utc` — an ISO-8601 UTC timestamp that is explicit /
  caller-injected; never read from a wall clock (no `datetime.now`).

The drawdown / drop fields are OPTIONAL (present only when available). No
field is a secret, a raw payload, a host, or a transport destination.

## 9. Failure behavior

Stage 30.10 is fail-closed end-to-end. The locked failure contract:

- invalid input ⇒ `INVALID_INPUT`, no send;
- `Tier Unknown` ⇒ `SKIPPED_TIER_UNKNOWN`, no send;
- `Tier Not Applicable` ⇒ `SKIPPED_TIER_NOT_APPLICABLE`, no send;
- missing ATH ⇒ `SKIPPED_MISSING_ATH`, no send;
- missing migration ⇒ `SKIPPED_MISSING_MIGRATION`, no send;
- missing / invalid market context ⇒ `SKIPPED_MISSING_MARKET_CONTEXT`, no
  send;
- in-band tier but policy-excluded ⇒ `SKIPPED_NOT_DIP`, no send;
- eligible dip ⇒ `ELIGIBLE_DIP`, send allowed downstream; and
- fail closed on any unknown / missing input, never fail open.

A skip NEVER becomes a transport failure: a non-dip candidate is simply not
reserved and not sent.

## 10. Future slices

Stage 30.10 is sequenced fake / offline before live, smallest reversible
slice first:

- Stage 30.10.0 — this spec lock only (spec doc + constants-only manifest +
  pin test). No runtime, no classifier, no live.
- Stage 30.10.1 — the fake / offline eligibility model + classifier tests: a
  pure tier-dip classifier + per-candidate audit-record model, proven with
  fakes only. No runtime wiring, no live provider call, no Discord send.
- Stage 30.10.2 — wire the OPTIONAL gate into the compact runtime path with
  fakes only: the gate is evaluated BEFORE dispatch reservation / private
  send; a non-dip skip is a normal no-send, never a transport failure.
- Stage 30.10.3 — prove artifact integration: persist the eligibility audit
  record alongside the existing Stage 30.9 compact / artifact lane, offline
  only.

Numbering may be adjusted if the project style suggests a better split; each
substage remains separately operator-authorized.

## 11. Stage 30.9.2 relationship

Stage 30.9.2 is paused, not abandoned. Stage 30.9.2 is the bounded private
live compact proof doc / operator handoff. It is paused because a read-only
audit found the current live compact path would mostly ping migrated /
tradeable candidates rather than true dips. Stage 30.9.2 should resume only
after Stage 30.10 proves dip-focused eligibility. Until then, no live proof
is run.

## 12. Forbidden surfaces

Stage 30.10 must NEVER touch any of the following. Explicitly listed as the
closed forbidden-surface set:

- a new live runner;
- a new provider;
- a new readiness gate;
- a direct Stage 28 suppression-logic edit;
- a transport-layer veto for a non-dip skip;
- public routing;
- subscriber routing;
- paid tiers;
- Telegram;
- X / social;
- automated trading;
- wallet / signing;
- enforcement activation;
- auto-buy;
- strategy execution;
- a broad always-on daemon;
- a database / SQLite store;
- zstd / compression;
- a default storage root;
- a background service; and
- Stage 31.

In addition, Stage 30.10 edits NO existing live runner / orchestrator /
transport file, NO Stage 28 suppression implementation file, and NO Stage
25 / 27 / 28 / 29 production file.

## 13. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage 30.6.0 /
30.7.4 / 30.8.0 / 30.9.0 records. It carries no provider credential strings,
no private transport destination strings, no provider host address strings,
no transport scheme prefixes, no raw request-payload or response-payload
field names, and no request auth-metadata strings. It records only
closed-set tokens, field names, thresholds, prose, and safe design labels.

The Stage 30.10.0 pin test enforces this by scanning this document, the
manifest, and the test, case-insensitively, against a split-literal
forbidden-substring vocabulary, so none of the three files can carry any of
the sanitized-away substrings even inside a negative claim.

---

_Stage 30.10.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.10.0 implementation.
- There is no Discord send during Stage 30.10.0 implementation.
- There is no eligibility classifier, no audit-record model, no runtime
  wiring, and no artifact integration at Stage 30.10.0.
- There is no new live runner, no new provider, and no new readiness gate at
  Stage 30.10.0.
- There is no direct edit of Stage 28 suppression logic at Stage 30.10.0.
- There is no database, no SQLite, no zstd dependency, no zstd
  implementation, and no compression at Stage 30.10.0.
- There is no default storage root and no background daemon at Stage
  30.10.0.
- There is no env read at Stage 30.10.0.
- There is no edit to any existing live runner / orchestrator / transport
  file (the Stage 30.0 inventory allowlist widening and the Stage 30.9.0
  inventory guard widening excepted) at Stage 30.10.0.
- There is no public routing, no subscriber routing, no paid routing, no
  Telegram, no X / social, no trading / wallet / signing, and no enforcement
  at Stage 30.10.0.
- There is no Stage 25 / 27 / 28 / 29 (or Stage 29.5) production import at
  Stage 30.10.0.
- There is no Stage 30.10.1+ implementation file at Stage 30.10.0.
- There is no Stage 31 surface at Stage 30.10.0.
- There is no commit, no tag, and no push performed by Stage 30.10.0
  implementation. Commit gating is a separate operator decision after audit.
