# PHX2 Stage 29.0 — Live Tradeability Unblocker Spec Lock

Stage 29.0 is a spec-lock-only pass. It ships no runtime code,
no Pump.fun / PumpSwap decoder, no Birdeye adapter, no Discord
send, no Stage 26 policy enforcement activation, no public /
subscriber / paid routing, no Telegram, no X / social, no
automated trading, and no wallet / private-key / signer logic.
Stage 29.0 ships only this document, the Stage 29 package
marker, the Stage 29 tests package marker, and the Stage 29.0
spec-lock tests.

---

## 1. Canonical Stage 29 scope sentence

Canonical sentence (future Stage 29 substages must preserve it
verbatim):

Stage 29 is the live tradeability unblocker for PHX2 private tradeable pings.

Stage 29 turns real Chainstack Yellowstone transaction /
instruction evidence into Stage 28.10 payloads with non-None
hint fields, attaches real Birdeye live price / ATH context to
those hint-bearing payloads, and lets the existing Stage 27
candidate chain finally produce real ASSEMBLED tradeable
private pings that flow through the existing Stage 28.4 audited
private Discord transport.

Stage 29 wraps and reuses Stage 27 + Stage 28 surfaces. Stage
29 does not rewrite Stage 27 classifier semantics, does not
broaden audience, does not broaden routing, does not activate
Stage 26 policy enforcement, and does not introduce trading
behavior.

---

## 2. Why Stage 28 stops here

Stage 28 is closed and tagged at `stage-28-closed`
(`a897bb0531259bbe065efb3e38703a7c3be156c7`). Stage 28.9 /
28.10 / 28.11 were post-closure narrow provider amendments:

- Stage 28.9 wired the existing Stage 27 / Stage 28.6 chain to
  a caller-supplied provider event source via the Stage 28.9
  adapter and the Stage 28.9 private webhook transport wrapper.
- Stage 28.10 defined the Chainstack Yellowstone provider
  boundary (protocol / fake / models surface) and the hint-
  aware candidate assembler.
- Stage 28.11 shipped the real Chainstack Yellowstone gRPC
  client behind the same Stage 28.10 protocol.

The Stage 28.11 live probe was performed and passed:

- mode 1 readiness-only: `READY`
- mode 2 provider-connect-only: `CONNECTED`
- mode 3 one-event decode dry run: `DECODED`,
  `handoff_ready=True`, `events_received=1`

The post-Stage-28-closure provider amendments are now finished.
Any further "Stage 28.12" / "Stage 28.13" amendments would
overload Stage 28's closed reliability charter with live-
tradeability work that does not belong inside it. Stage 28's
closure must hold.

---

## 3. Why diagnostic Discord smoke is rejected

A diagnostic Discord smoke that reports the suppression token
of a real Chainstack event suppressed via
`UNKNOWN_PAIR_SUPPRESSED` would prove only that the audited
transport can post text to a private channel. The post-Stage-
28.11 reality is that:

- the upstream Stage 28.11 decoder leaves every hint field as
  `None` by design (no SOL / USDC invention),
- the Stage 27 chain therefore classifies the candidate as
  `SUPPRESSED_UNKNOWN_PAIR`,
- the Stage 28.6 runner refuses to dispatch a tradeable ping,
- the audited transport, if invoked separately by an operator
  scratch script for diagnostic-only text, would send a
  message that is not a tradeable private ping.

PHX2 needs to replace PHX1. PHX1 emits real tradeable private
pings. A diagnostic-only smoke does not move PHX2 toward that
acceptance bar; it merely re-confirms a transport surface that
the Stage 28.4 / Stage 28.7 / Stage 28.9 tests have already
exercised offline. Stage 29.0 therefore rejects diagnostic
Discord smoke as insufficient evidence of live tradeability.

The Stage 28.7 controlled-live-smoke runbook continues to
document the operator-side scratch ceremony for the audited
transport in isolation; it is not the Stage 29 acceptance
event.

---

## 4. What blocks PHX2 from replacing PHX1 today

After Stage 28.11 the operator-observed blockers are:

- The Stage 28.11 decoder produces Stage 28.10 payloads with
  every hint field at `None`: `quote_mint=None`,
  `pool_account=None`, `pool_program_id=None`,
  `base_mint=None`, `provider_quote_asset_hint=None`,
  `provider_pair_type_hint=None`,
  `provider_bonding_curve_version_hint=None`,
  `bonding_curve_version_hint=None`.
- The Stage 27 candidate chain therefore classifies the
  upstream event as `SUPPRESSED_UNKNOWN_PAIR` and refuses to
  render a tradeable private ping.
- Even if the hints were present, the existing Stage 27.4
  price-context source is a deterministic test fake; there is
  no real Birdeye-backed price / ATH adapter wired in. A real
  tradeable private ping requires both axes.

Stage 29.1 must solve the hint-extraction blocker. Stage 29.2
must solve the live price / ATH blocker. Stage 29.3 must prove
the end-to-end real-event-to-real-private-ping path. Until
Stage 29.3 passes, PHX2 cannot replace PHX1.

---

## 5. Stage 29 substage plan (29.0 to 29.3)

The disciplined Stage 29 substage sequence is:

- **29.0** spec lock / live tradeability unblocker charter
  (this document)
- **29.1** Pump.fun / PumpSwap hint extractor from real
  Chainstack Yellowstone transaction / log / instruction data
- **29.2** Birdeye live price / ATH adapter for known mint
  context
- **29.3** first real private tradeable Discord smoke with
  `max_events=1` / `max_dispatches=1`

Every substage past 29.0 requires explicit operator
authorization before any edit lands. No substage past 29.0 is
authorized by this document. Stage 29.0 only locks the plan.

Stage 29.4+ is reserved. If any post-29.3 hardening is needed
(enforcement activation, additional providers, additional
dispatch surfaces) it requires a separately authorized substage
that ships its own spec lock first.

---

## 6. Stage 29.1 evidence contract (Pump.fun / PumpSwap hint extractor)

Stage 29.1 must extract hints **only from explicit decoded
evidence** present in the upstream Yellowstone `SubscribeUpdate`
message. The evidence sources are:

- `transaction.transaction.transaction.message.account_keys`
  (the resolved account-key list, including address-table-
  lookup-resolved keys),
- `transaction.transaction.transaction.message.instructions`
  (the top-level instruction list),
- `transaction.transaction.meta.inner_instructions` (inner
  SPL Token / System Program transfers / ATA initializations),
- `transaction.transaction.meta.log_messages` (Pump.fun /
  PumpSwap program log lines, when present),
- `transaction.transaction.meta.pre_token_balances` and
  `post_token_balances` (resolved mint references on the
  pre / post token balance side).

Stage 29.1 must extract these fields **per-event, from this
evidence only**:

- `token_mint` / `base_mint` — the base token mint being
  observed. Populated only when the mint string appears in the
  resolved account-keys list at the program-pinned account
  position for a known Pump.fun / PumpSwap instruction
  discriminator, or in the pre / post token-balance side of
  the instruction. Otherwise `None`.
- `pool_account` — the on-chain pool / bonding-curve account.
  Populated only when the account string appears in the
  account-keys list at the program-pinned position for the
  matched instruction discriminator. Otherwise `None`.
- `quote_mint` — the on-chain quote-side mint. Populated only
  when the mint string is directly referenced in the
  account-keys list at the program-pinned quote position OR
  in a matched inner-instruction SPL Token transfer that
  pairs against the base-token side. Otherwise `None`.
  No SOL invention. No USDC invention.
- `pool_program_id` — the program id that owns the matched
  instruction. Populated from the resolved instruction's
  `program_id_index` lookup against the account-keys list.
  Otherwise `None`.
- `provider_pair_type_hint` — closed-set
  `PUMP_SOL` / `PUMP_USDC` / `UNKNOWN`. Populated only when
  the matched program id and the extracted quote-side mint
  together uniquely identify a pair type. No fabrication from
  a program-id match alone.
- `bonding_curve_version_hint` — closed-set
  `SOL_LEGACY` / `USDC_FIXED` / `UNKNOWN`. Populated only when
  the matched instruction discriminator + the extracted pool
  layout together uniquely identify a bonding-curve version.
  Otherwise `None`.

Stage 29.1 must classify the `instruction_kind` axis on the
existing Stage 28.10 closed set (`PUMP_SWAP`,
`PUMP_MIGRATION`, `PUMP_CREATE`, `UNKNOWN`). The classification
is allowed to surface only when the discriminator match is
unambiguous; ambiguous discriminators map to `UNKNOWN`.

Stage 29.1 must never invent a SOL hint. Stage 29.1 must never invent a USDC hint. Stage 29.1 must never invent a mint, a pool, a program id, or a pair type from the absence of evidence. If the evidence is insufficient, the field stays `None` and the Stage 27 chain continues to suppress `UNKNOWN_PAIR`. Stage 29.1 must not modify Stage 27 classifier semantics; the existing pair-classification chain remains authoritative for the eventual ASSEMBLED / SUPPRESSED verdict.

Stage 29.1 must own a Stage-29.1-pinned table of Pump.fun /
PumpSwap program ids and per-discriminator account layouts.
The table is internal to Stage 29.1 and is the only source of
account-position evidence; the table is not extended at
runtime, never read from the environment, and never reaches
across the Stage 27 / Stage 28 boundary.

---

## 7. Stage 29.2 evidence contract (Birdeye live price / ATH adapter)

Stage 29.2 must provide a real Birdeye-backed implementation of
the existing Stage 27.4 `PriceContextSource` Protocol and the
Stage 27.4 `AthContextSource` Protocol so the existing Stage
27.6 `Stage27_6Sources` bundle can carry real live context
into the existing Stage 27.6 candidate chain.

Stage 29.2 must surface the following evidence per known mint:

- **current price** — the most recent Birdeye price snapshot
  for the mint, in the safe-shape number the Stage 27.4 price
  contract expects.
- **ATH since migration** — the all-time-high price observed
  since the Pump.fun bonding-curve migration event (when the
  mint has migrated), or since first-observed otherwise. The
  ATH must be derived from a Birdeye historical query bounded
  by the Stage 29.1-extracted migration evidence (when
  available) and must never be invented when the historical
  series is unavailable.
- **drawdown** — the current price expressed as a closed-set
  drawdown ratio against the ATH (e.g. `-0.42`). Computed
  locally from the two values above; never invented.
- **freshness timestamp / status** — the upstream Birdeye
  response timestamp projected to an ISO-8601 UTC string, plus
  a closed-set freshness status (`PRESENT` / `STALE` /
  `UNAVAILABLE` / `SOURCE_ERROR`) that the existing Stage 27.5
  rendered ping already maps to the Stage 28.6
  `CANDIDATE_PRICE_STATUS_*` closed set.

Stage 29.2 must run through a single Stage-29.2-pinned env-read
boundary (mirroring the Stage 28.11 readiness pattern). The
raw Birdeye API key is never echoed on any public record,
`__repr__`, exception, log line, or persisted artifact.

Stage 29.2 must never invent a price, an ATH, a drawdown, a
freshness timestamp, or a freshness status. A missing or
errored upstream response maps to `UNAVAILABLE` or
`SOURCE_ERROR`; the existing Stage 27 chain will suppress
`PRICE_MISSING` / `PRICE_STALE` accordingly.

Stage 29.2 must not introduce Dexscreener as a dispatch
authority. Stage 29.2 must not introduce Helius as a price
source. Stage 29.2 must not introduce any other provider beyond
Birdeye at Stage 29.2.

---

## 8. Stage 29.3 acceptance contract (first real private tradeable ping)

Stage 29.3 must prove the following end-to-end path on a real
operator-supplied Chainstack endpoint and a real operator-
supplied Birdeye key, under tight bounds:

- a real Chainstack Yellowstone event is received,
- Stage 29.1 extracts non-None hint fields from the event
  (token mint / pool / quote mint / pair type where evidence
  is present),
- Stage 29.2 returns a real Birdeye price + ATH + freshness
  status for the extracted mint,
- the existing Stage 27 candidate chain produces an
  `ASSEMBLED` candidate (not `SUPPRESSED_UNKNOWN_PAIR`),
- the Stage 28.9 wrapper drives the Stage 28.6 bounded runner,
- the Stage 28.4 audited private operator-only Discord
  transport sends exactly one private tradeable ping,
- `max_events=1`, `max_dispatches=1`, operator live flags are
  explicit, and the artifact directory is operator-supplied
  and lives outside the PHX2 working tree.

The Stage 29.3 acceptance artifacts must record: the real
provider event id and slot, the extracted hint fields, the
Birdeye price / ATH / freshness snapshot, the Stage 28.6 final
summary with `candidates_dispatched=1` / `dispatch_success=1`,
the Stage 28.4 transport result with `transport_status` in the
locked success set, and the Stage 28.7-style redaction scan
confirming no URL / secret / wallet / raw-response substring
leaked into any artifact.

Stage 29.3 must not retry. Stage 29.3 must not loop. Stage
29.3 must not run unattended.

---

## 9. What remains forbidden until after Stage 29.3

Until Stage 29.3 demonstrably passes on a real operator
environment, the following surfaces remain out of Stage 29:

- Stage 26 policy enforcement activation (approved / activated
  filter gates)
- public routing
- subscriber routing
- paid tier routing
- Telegram
- X / social
- automated trading
- wallet / private-key / signer logic
- position sizing
- trade execution
- public dashboard / HTTP control server
- daemon / systemd / watchdog / autorestart service
- Dexscreener as a dispatch authority
- Helius as a primary provider
- any third or fourth provider beyond Stage 28.11 (Chainstack)
  + Stage 29.2 (Birdeye)

Resuming any of the above requires a separately authorized
Stage 29.4+ substage that ships its own spec lock first. The
old Stage 28.8-era Stage 29 handoff doc that proposed Stage
29 as enforcement charter is superseded by this Stage 29.0
spec lock; enforcement activation moves to a later authorized
substage and is **not** Stage 29.1 / 29.2 / 29.3.

---

## 10. Acceptance criteria for PHX2 replacing PHX1

PHX2 is considered ready to replace PHX1 only after every one
of the following holds:

- at least one real private tradeable ping has been sent from
  live Chainstack + live Birdeye context via the existing
  Stage 28.4 audited private transport,
- the Stage 29.3 acceptance artifacts prove the real event
  source, the extracted real mint / pair hints, the real
  Birdeye price / ATH / freshness snapshot, and the real
  private Discord dispatch result,
- no public routing was invoked,
- no subscriber routing was invoked,
- no paid tier routing was invoked,
- no Telegram send was invoked,
- no X / social send was invoked,
- no automated trading was invoked,
- no wallet / private-key / signer surface was loaded,
- no Stage 26 policy enforcement gate was activated unless
  separately authorized after Stage 29.3,
- the Stage 28.7-style redaction scan over the acceptance
  artifact directory reports `SAFE`,
- the operator records the per-event audit trail in their own
  log.

PHX2 replacing PHX1 does not imply Stage 29 enforcement
activation. Enforcement activation remains separately
authorized.

---

## 11. Stage 29.0 scope locks

Stage 29.0 ships only:

- this `STAGE_29_0_SPEC_LOCK.md` document
- `PHX2/stage29/__init__.py` (package marker)
- `PHX2/tests/stage29/__init__.py` (tests package marker)
- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py` (spec-lock
  tests)

Stage 29.0 must not include any of:

- Pump.fun / PumpSwap decoder implementation
- Birdeye adapter implementation
- Discord send
- diagnostic Discord smoke
- scratch sender of any kind
- public routing
- subscriber routing
- paid tier routing
- Telegram
- X / social
- automated trading
- wallet / private-key / signer logic
- position sizing
- trade execution
- Stage 26 policy enforcement activation
- fake SOL / USDC hint values
- invented mint / pool values
- Dexscreener
- Helius
- second env-read site (Stage 28.11 readiness remains the
  Stage 28.11 env-read boundary; Stage 29.2 will own its own
  Stage 29.2-pinned env-read boundary when it lands)
- runtime model / enum / constant for the Stage 29.1 hint
  vocabulary (Stage 29.0 names them, Stage 29.1 ships them)
- tagging / pushing / committing the spec lock from inside the
  Stage 29.0 implementation (the operator handles those steps
  explicitly)

Stage 29.0 must not create a `stage-29-0-closed` tag. Stage
29.0 must not move or peel the existing `stage-28-closed` tag.

---

## 12. Reuse rules

Stage 29 must reuse and wrap the surfaces below. Stage 29 must
not reimplement them:

- Stage 27 live candidate assembler
- Stage 27 pair classifier (UNKNOWN / DISAGREE / USDC observe-
  only suppression rules)
- Stage 27 private ping renderer
- Stage 27.4 `PriceContextSource` and `AthContextSource`
  Protocols
- Stage 27.6 `Stage27_6Sources` bundle
- Stage 28.2 restart-safe dispatch ledger
- Stage 28.3a failure classification
- Stage 28.3b bounded retry policy
- Stage 28.4 audited private operator-only Discord HTTP
  transport
- Stage 28.5 heartbeat / health snapshot / final summary
  artifacts
- Stage 28.6 bounded private session runner
- Stage 28.9 private live provider session adapter and
  private webhook transport wrapper
- Stage 28.10 Chainstack Yellowstone provider boundary
  (protocol / models / event source / hint-aware candidate
  assembler)
- Stage 28.11 real Chainstack Yellowstone gRPC client + the
  Stage 28.11 readiness env-read boundary

Stage 29 must not reimplement the Stage 27 pair classifier,
the Stage 28.4 audited transport, the Stage 28.6 bounded
runner, or the Stage 28.11 gRPC client. Stage 29.1 owns only
the hint extractor; Stage 29.2 owns only the Birdeye adapter;
Stage 29.3 owns only the operator-side wiring of the existing
Stage 28.9 entry point under explicit operator authorization.

---

## 13. Closed-set vocabulary placeholders (names only at 29.0)

Stage 29.1 will own these closed-set vocabularies (names only
at Stage 29.0; Stage 29.0 must not ship runtime models, enums,
or constants for these vocabularies):

- `hint_evidence_kind`
- `pump_program_match`
- `pumpswap_program_match`
- `instruction_discriminator_match`
- `account_position_match`
- `hint_extraction_outcome`
- `quote_mint_evidence_source`
- `pool_account_evidence_source`

Stage 29.2 will own these closed-set vocabularies (names only
at Stage 29.0):

- `birdeye_price_status`
- `birdeye_ath_status`
- `birdeye_freshness_status`
- `birdeye_refusal_reason`

Stage 29.3 will own these closed-set vocabularies (names only
at Stage 29.0):

- `tradeable_smoke_outcome`
- `tradeable_smoke_refusal_reason`

Stage 29.0 must not ship runtime models, enums, or constants
for these vocabularies.

---

## 14. Operator preconditions for any Stage 29.1+ work

Before any Stage 29.1+ edit lands the operator must confirm:

- `git rev-parse stage-28-closed^{}` still peels to
  `a897bb0531259bbe065efb3e38703a7c3be156c7`.
- The Stage 28.11 live probe sequence (modes 1 to 3) was
  performed and passed in the operator environment within
  the same session, with `handoff_ready=True` on the dry-run
  result.
- No `stage-29-*` tag exists.
- The Stage 29.0 spec-lock tests pass.
- The operator has typed an explicit per-substage
  authorization phrase into the operator audit log.

Stage 29.0 documents these preconditions; it does not enforce
them in runtime code (Stage 29.0 ships no runtime code).
