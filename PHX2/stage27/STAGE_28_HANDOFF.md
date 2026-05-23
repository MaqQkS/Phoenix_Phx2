# PHX2 Stage 28 Handoff

Stage 28 mission: private live runner hardening after Stage 27
closure.

Stage 27 proved the first private controlled live ping surface.
Stage 28 should make that private runner more reliable without
changing its routing model, audience, or enforcement posture.

## Stage 28 Must Include

Stage 28 owns reliability hardening for the private live runner:

- crash recovery
- retries/backoff
- health checks
- restart-safe dedupe
- provider failure handling
- monitoring/logging
- longer-running private sessions
- provider-neutral config cleanup for Chainstack/Helius naming
- optional Dexscreener fallback/cross-check design
- safe transition from scratch transport to audited tracked
  transport, if desired

These items should preserve Stage 27's private operator-only
delivery model and continue to keep secrets redacted from logs,
artifacts, exceptions, and dispatch results.

## Stage 28 Must Not Include

Stage 28 must not include:

- public routing
- paid tiers
- subscriber routing
- X/social
- Stage 29 enforcement
- automated trading

Stage 28 must not broaden Discord distribution, add Telegram,
introduce public or subscriber destinations, or turn Stage 26
policy candidates into runtime gates.

## Ownership Boundaries

Stage 29 owns approved enforcement/live gating. Any policy
candidate activation, live gate, allow/block decision, operator
approval semantics, or enforcement-derived routing belongs to
Stage 29 and requires its own explicit authorization.

Stage 30+ owns the X/social sidecar. Any X API, social scraping,
tweet ranking, social scoring, or public social distribution work
belongs there and must stay out of Stage 28.

Stage 28 may improve private runner reliability only. It should
not alter Stage 27.7b dispatch behavior, add public routing, add
subscriber routing, add paid tiers, add Telegram, add X/social,
add Stage 29 enforcement, or add automated trading.
