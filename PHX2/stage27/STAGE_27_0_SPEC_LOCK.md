# PHX2 Stage 27.0 — Spec Lock / Architecture Charter

Stage 27.0 is the scaffold-only spec-lock pass. It ships no live
runner, no secrets reader, no provider client, no Helius / gRPC
client, no Birdeye / API client, no pair classifier, no Discord
sender, no ping renderer, no dedupe path, and no enforcement
surface. Stage 27.0 ships only this document, the package marker,
the tests package marker, and the Stage 27.0 spec-lock tests.

---

## 1. Mission

> Stage 27 turns PHX2 into a private live PHX1-parity tradeable ping runner, with pair-aware SOL/USDC handling, while keeping enforcement and public routing out of scope.

That sentence is the canonical Stage 27 mission. Future Stage 27
work must preserve it verbatim.

---

## 2. PHX1-parity definition

For Stage 27, **PHX1-parity** means and only means:

- private operator Discord webhook delivery
- usable live ping field-set
- bounded operator-controlled runner lifecycle
- dedupe / no-spam behavior
- provenance / run / ping IDs
- enough context for manual trading

PHX1-parity does **NOT** mean any of the following, and Stage 27
must not be measured against them:

- public production
- paid routing
- broad Discord distribution
- latency guarantees
- signal-quality guarantees
- automated trading
- Stage 29 enforcement

If any future substage tries to redefine PHX1-parity to include a
forbidden item above, the substage is out of Stage 27 scope.

---

## 3. Tradeable definition

For Stage 27, **tradeable** means and only means:

- the operator can manually act on the ping
- the mint is present and copy-pasteable
- the pair type is known and displayed
- the quote asset is displayed
- price / freshness / source are displayed when available
- migration context is displayed when available
- the run_id and ping_id / provenance are available

Tradeable does **NOT** mean any of the following:

- the signal is guaranteed good
- the bot auto-approves the trade
- the bot auto-executes
- Stage 26 policy candidates are enforced

Tradeable in Stage 27 is an operator capability, not a quality
claim and not an automation claim.

---

## 4. Stage 27 is NOT X/social

Stage 27 is not the X/social stage. X/social work is deferred to
Stage 30+.

Stage 27 must not:

- implement an X API / Twitter API integration
- implement tweet ranking
- implement social scraping
- implement a social sidecar
- implement social scoring
- import or scaffold any X/social module

The Stage 26.7 handoff already pinned this. Stage 27.0 re-pins it.

---

## 5. Stage 27 is private only

Stage 27 is private routing only. The runtime addressable
destination set is exactly one private operator Discord webhook.

Stage 27 must not:

- implement public Discord routing
- implement subscriber routing
- implement paid tiers
- implement broad community distribution
- implement Telegram unless explicitly scoped later in a separate
  authorization

The two-factor LIVE authority (Section 8) gates the only path
that reaches the private webhook at all.

---

## 6. Pair-awareness is mandatory

Stage 27 must classify every candidate event before it is
considered for a private tradeable ping.

The pair-awareness contract Stage 27 must eventually expose:

- `quote_asset` — closed set: `SOL` | `USDC` | `UNKNOWN`
- `pair_type` — closed set: `PUMP_SOL` | `PUMP_USDC` | `UNKNOWN`
- `bonding_curve_version` — closed set: `SOL_LEGACY` |
  `USDC_FIXED` | `UNKNOWN`
- `quote_mint`
- `pair_detection_status`
- `pair_detection_confidence`
- `pair_detection_reason`
- `pair_detection_source` (or `detection_sources`)

Rules:

- SOL-pair and USDC-pair measurement / calibration universes must
  stay separate. Stage 27 must not silently mix them.
- USDC-pair pings must be labeled OBSERVE_ONLY until PHX2 has
  accumulated enough first-party USDC-pair data to justify
  changing the label.
- `UNKNOWN` must never default to `SOL`. An UNKNOWN classification
  is its own state, not an alias.
- UNKNOWN pair events must be suppressed in LIVE mode for
  Stage 27 and surfaced only in dry-run / artifacts, unless a
  later explicitly authorized stage changes this policy.
- Stage 27 must not mix SOL ATH / migration behavior with USDC
  ATH / migration behavior.

Stage 27.0 only documents this contract. Stage 27.2 ships the
classifier skeleton (no live calls). No Stage 27.0 module
implements classification.

---

## 7. Pair detection source hierarchy

When Stage 27 ships its classifier, the intended source hierarchy
(strongest evidence first) is:

1. on-chain pool quote mint / pool account
2. bonding-curve metadata / account layout / program ID
3. migration event fields
4. provider-enriched payload
5. known quote-mint fallback
6. UNKNOWN

If sources disagree:

- the on-chain quote mint is treated as strongest evidence
- disagreement must lower the recorded confidence
- a conflicted or UNKNOWN classification must fail closed in LIVE
  mode (no private ping is sent)
- all source disagreement must be recorded in artifacts later,
  not silently flattened

This hierarchy is documentation only at Stage 27.0. No Stage 27.0
module implements detection.

---

## 8. LIVE mode authority

Stage 27 must eventually require two independent live-mode
authorizations before a single private Discord ping is sent:

1. a local env / config flag indicating that LIVE mode is allowed
   at all for this checkout
2. an explicit CLI / operator argument indicating that *this*
   run is a LIVE run

Either alone must fail closed (LIVE refuses to start). Both
together is the only path that produces real private pings.

Stage 27.0 only documents this requirement. The two-factor LIVE
authority is implemented in Stage 27.1 (operator config + mode
authority) and exercised in Stage 27.7b (first single private
ping smoke).

---

## 9. Runner scope

The Stage 27 future runner must be:

- bounded (by both `--max-duration` and `--max-pings`; refuses to
  start without at least one bound set)
- private (single operator webhook only)
- foreground / operator-controlled (no daemonization)
- safe to start / stop (SIGINT drains; SIGTERM stops hard)
- dedupe-aware (no spam)
- redacted (no webhook URL, no secret, no raw provider payload
  in logs or artifacts)
- capable of one controlled private tradeable ping smoke

The Stage 27 runner must not be:

- a public production daemon
- an auto-restarting service
- a subscriber router
- a paid-tier system
- an enforcement engine
- an X/social sidecar

Stage 28 will harden (and is the correct home for) the following
items, which Stage 27 must not pre-implement:

- crash recovery
- retries / backoff beyond the bounded minimum
- health checks
- restart-safe dedupe
- richer provider failure handling
- monitoring
- longer-running reliability

---

## 10. Stage 26 relationship

Stage 26 outputs are evidence / review-only.

Stage 27 may display Stage 26 context inside the private ping as
review-only / observe-only label text.

Stage 27 must not enforce Stage 26 candidate policies. Stage 27
must not auto-approve a ping using Stage 26 policy candidates.
Stage 27 must not auto-block a ping using Stage 26 policy
candidates.

Stage 29 is the correct home for approved enforcement and live
gating. Stage 27.x must not preempt it.

---

## 11. Prior stage reuse

Stage 27 must reuse the Stage 21 / Stage 22 live-ingest, private
transport, raw capture, and dedupe boundaries where applicable.

Stage 27 must not duplicate:

- provider connection management
- decoder logic
- private transport logic
- dedupe logic

unless a narrow seam genuinely requires an adapter, in which case
the adapter is small and explicit.

Stage 27 must avoid the PHX1-spaghetti shape:

- no single mega-runner that does ingest + classify + price +
  render + send
- no scattered env reads (env is read by exactly one module,
  shipped in Stage 27.1)
- no global mutable LIVE-mode state
- no copied provider parsing
- no renderer doing business logic

Stage 21 / 22 already own their own boundaries. Stage 27 composes
on top of those boundaries; it does not rewrite them.

---

## 12. Substage plan

The intended Stage 27 substage breakdown is:

- **27.0** spec lock / architecture charter *(this document)*
- **27.1** secrets / .env readiness + operator config + mode
  authority + run / session ID
- **27.2** pair classification contracts + classifier skeleton,
  no live calls
- **27.3** provider ingest composition using Stage 21 / 22
  boundaries
- **27.4** price / migration / ATH context integration
- **27.5** private ping renderer + provenance writer, dry-run
  only
- **27.6** bounded runner + dedupe, still dry-run
- **27.7a** operator runbook + full dry-run smoke, no Discord
  call
- **27.7b** live-mode gating + first single private Discord ping
  smoke
- **27.8** closure audit + Stage 28 handoff

Each substage is gated by an explicit operator authorization in
its own turn. Stage 27.0 does not pre-authorize any later
substage.

---

## 13. Explicit non-goals

Stage 27 explicitly excludes the following surfaces. These are
forbidden in every Stage 27 substage and are not relaxable inside
Stage 27:

- X/social (deferred to Stage 30+)
- public routing
- subscriber routing
- paid tiers
- broad Discord community distribution
- Telegram unless explicitly scoped later
- Stage 29 approved enforcement / live gating
- automatic enforcement derived from Stage 26 candidate policies
- Axiom reopening
- global-fee reopening
- Stage 24 reopening
- Stage 25 artifact mutation
- Stage 26 artifact mutation
- bypassing Stage 21 / 22 live-ingest boundaries
- public routing logic
- paid alert logic

If a future Stage 27.x prompt asks for any of these, the spec
lock has been violated and the substage must be rejected before
implementation.

---

## 14. Stage 28 / Stage 29 / Stage 30+ handoff

- **Stage 28** is the hardening stage. Crash recovery, retries /
  backoff, health checks, restart-safe dedupe, richer provider
  failure handling, monitoring, and longer-running reliability
  belong there, not in Stage 27.
- **Stage 29** is where approved enforcement and live gating
  live. Stage 26 candidate policies become enforcement only
  through Stage 29's explicit authorization gate.
- **Stage 30+** is where the X/social sidecar lives. Stage 27
  must not preempt any X/social work.

---

## 15. Stage 27.0 scaffold inventory

Stage 27.0 ships exactly these files under `PHX2/stage27/`:

- `__init__.py` (package marker)
- `STAGE_27_0_SPEC_LOCK.md` *(this document)*

Stage 27.0 ships exactly these files under `PHX2/tests/stage27/`:

- `__init__.py` (tests package marker)
- `test_stage_27_0_spec_lock.py` (spec-lock pins)

Stage 27.0 does **not** ship any of the following implementation
files (each is reserved for a later substage and must not exist
under `PHX2/stage27/` at Stage 27.0 closure):

- `live_operator_config.py` (reserved for 27.1)
- `live_secrets_readiness.py` (reserved for 27.1)
- `pair_detection_contracts.py` (reserved for 27.2)
- `pump_pair_classifier.py` (reserved for 27.2)
- `live_provider_composition.py` (reserved for 27.3)
- `price_ath_context_reader.py` (reserved for 27.4)
- `private_ping_renderer.py` (reserved for 27.5)
- `private_discord_sender.py` (reserved for 27.5 / 27.7b)
- `live_candidate_assembler.py` (reserved for 27.5 / 27.6)
- `bounded_tradeable_ping_runner.py` (reserved for 27.6)
- `live_dedupe.py` (reserved for 27.6)

The spec-lock tests enforce this allowlist. Any later substage
that adds an implementation file must extend the allowlist
narrowly inside its own prompt, never silently.

---

## 16. Stage 27.0 closure conditions

Stage 27.0 is closed when:

- this document exists and contains the canonical mission
  sentence verbatim
- the Stage 27.0 spec-lock tests pass
- the Stage 25.7 and Stage 26.7 closure-audit tests still pass
  under the narrow Stage 27.0 amendment
- `PHX2/stage27/` contains only the Stage 27.0 scaffold set
- no Stage 27 implementation file (Section 15) has been
  introduced
- no commit, tag, or push is performed by the implementation
  pass itself

Tag creation (`stage-27-0-closed` or any subsequent Stage 27
tag) is an operator-only action and is not performed by Stage
27.0 implementation.
