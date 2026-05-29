# PHX2 Stage 30.7 — ATH Context Bridge Handoff

This handoff explains how a future caller supplies sanitized ATH
evidence to the Stage 30.7 ATH context bridge, exactly which inputs
produce a displayed `$Y` value versus `Unknown`, and how the value
reaches the compact private-ping body. It is the companion to
`STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md`.

This document carries no provider credential, no private transport
destination, no provider host address, no transport scheme prefix, no
raw provider payload, and no request auth metadata. The pseudo example
below is illustrative, not executable live code.

## 1. How a future caller supplies sanitized ATH evidence

The Stage 30.7.3 bridge consumes a **sanitized** scalar summary of
upstream ATH evidence. The caller is responsible for reducing whatever
upstream ATH context it has (a Stage 25 ATH candidate, a Stage 27.4 ATH
context record, a Stage 29.2 Birdeye ATH snapshot) down to safe scalar
fields BEFORE handing it to the bridge. The bridge then maps those
scalars onto the Stage 30 closed sets.

The bridge accepts the sanitized evidence in any of three shapes:

- a plain `dict` (fields read by key),
- any attribute-bearing object (fields read by attribute), or
- the Stage-30-owned `Stage30_7_3SanitizedUpstreamAthEvidence`
  dataclass.

The bridge imports NO Stage 25 / 27 / 28 / 29 module. It never reads a
raw provider payload, a raw transaction signature, an event log, a
source event ref, a provider URL / host, a secret, an inbound-hook URL,
or a Discord destination — the evidence carrier it builds has no field
for any of those. A nested `dict` / `list` / `tuple` / `set` /
`bytes` value in the value slot is rejected (treated as missing), so a
raw nested provider object can never flow through.

## 2. Accepted sanitized aliases

Each logical field is read from the first present alias (an explicit
`None` counts as present; only a truly absent field falls through to the
next alias):

- value — `ath_value`
- unit — `ath_unit`
- source status — `source_status` or `ath_status`
- basis — `basis` or `drawdown_basis`
- redaction-safe — `redaction_safe`
- source label — `source_label` or `ath_source`
- observed clock — `observed_at_utc` or `ath_observed_at_utc`

The `source_label` and `observed_at_utc` fields are inert provenance:
they are carried but NEVER echoed into the compact `ATH` token (the
compact token is only a `$Y` value or the literal `Unknown`, never a
label or a timestamp).

## 3. Required safe display conditions

The bridge emits a `$Y` value (an `ATH_KNOWN` projection) ONLY when ALL
of the following hold on the normalized evidence:

- source PRESENT — the source status maps to `PRESENT`.
- unit USD — the unit maps to `USD` and matches the market-context unit
  (default `USD`).
- basis `ATH_MARKET_CAP_OBSERVED` — the upstream basis is
  `ATH_MARKET_CAP_OBSERVED` or `MARKET_CAP_OBSERVED` (both map to the
  observed-market-cap basis).
- redaction_safe exactly True — the upstream `redaction_safe` is exactly
  `True`.
- a positive finite scalar value — `ath_value` is a positive, finite
  number or strict decimal-text string.

When all five hold, the compact `ATH` token renders the truncating
`$Y` magnitude form (for example `$120k`).

## 4. Expected Unknown cases

Every other shape fails closed to the literal `Unknown`. The expected
`Unknown` cases:

- missing redaction_safe — no `redaction_safe` present, or any value
  other than exactly `True`.
- price-derived — a `PRICE_DERIVED` / `ATH_PRICE_DERIVED` basis is at
  most `ATH_UNVERIFIED` and never displays in this slice.
- USDC — a `USDC` unit maps to `UNKNOWN` (never silently treated as
  USD).
- SOL with USD context — a `SOL` unit against a `USD` market context is
  unit-incompatible.
- stale / error / conflicting / unavailable — any non-`PRESENT` source
  status (including `NOT_APPLICABLE` / `UNSUPPORTED_PAIR` / `UNKNOWN`,
  which fail closed to `UNAVAILABLE`).
- nested / raw-like payloads — a nested container in the value slot is
  rejected as a missing value.

## 5. How it reaches the compact ping

The display value flows through the existing Stage 30 seam — no renderer
change, no compact-model change:

```
sanitized bridge -> Stage30_7_2AthDisplayResolver -> ath_context_resolver seam -> ath_mc_text
```

The bridge's `build_stage30_ath_resolver_from_sanitized_evidence(...)`
returns a `Stage30_7_2AthDisplayResolver` — the drop-in object the Stage
30.4.2 orchestrator's opt-in `ath_context_resolver` seam (added at Stage
30.7.2) already consumes. Per ping, the orchestrator calls the resolver's
`resolve_display_text(...)` and, when the result is a safe non-`None`
string, fills the existing Stage 30.2 `ath_mc_text` slot. The renderer
then renders that slot into the compact body `ATH` token. When no
resolver is wired, the slot stays untouched and the body keeps
`ATH: Unknown`.

## 6. Pseudo example (illustrative, not executable live code)

```python
from PHX2.stage30.stage30_7_sanitized_ath_bridge import (
    build_stage30_ath_resolver_from_sanitized_evidence,
)

# A future caller assembles a SANITIZED scalar summary of upstream ATH
# evidence. This is NOT a raw provider payload — it is the safe scalar
# reduction the caller is responsible for producing.
sanitized = {
    "ath_value": 120000,                  # positive finite scalar
    "ath_unit": "USD",                    # matches the USD market context
    "source_status": "PRESENT",           # source dominance: PRESENT
    "basis": "ATH_MARKET_CAP_OBSERVED",   # observed market cap, not price
    "redaction_safe": True,               # exactly True, else fails closed
    "source_label": "sanitized_upstream_ath_evidence",  # inert provenance
    "observed_at_utc": "2026-05-29T00:00:00Z",          # inert provenance
}

resolver = build_stage30_ath_resolver_from_sanitized_evidence(
    raw_evidence=sanitized,
)

# The Stage 30.4.2 orchestrator's opt-in ath_context_resolver seam then
# calls resolver.resolve_display_text(...) per ping, which returns "$120k"
# for the evidence above and fills the existing ath_mc_text slot. The
# rendered compact body becomes:
#   • MC: $83k | ATH: $120k | Mig: Known
#
# Change basis to "ATH_PRICE_DERIVED", drop redaction_safe, switch the
# unit to "USDC" or "SOL", or use any non-PRESENT source status, and the
# resolver returns "Unknown" instead (the body keeps ATH: Unknown).
```

## 7. Future integration warnings

- Do NOT import provider modules into Stage 30. The bridge deliberately
  imports no Stage 25 / 27 / 28 / 29 module and no provider client; keep
  it that way. The upstream ATH evidence is consumed as a sanitized
  duck-typed shape, never imported.
- Do NOT pass raw provider payloads. The caller must reduce upstream
  context to safe scalars first; the evidence carrier has no field for a
  raw payload, signature, event ref, URL, host, secret, or Discord
  destination, and a nested container in the value slot is dropped.
- Do NOT use `runtime_consumable` as a live permission. Stage 30.7 hard-
  locks `runtime_consumable=False` on every projection; the adapter never
  flips or trusts it as a live-send authorization. It is not a routing
  gate and it is not a Discord-send flag.
- Do NOT mix ATH display with tier recomputation yet. A displayed ATH is
  trusted for a FUTURE drawdown / tier anchor
  (`should_trust_for_drawdown=True` only for `ATH_KNOWN`), but Stage 30.7
  recomputes no drawdown and no tier. Drawdown-from-ATH and tier dip
  remain deferred to a separately authorized later stage.

---

_Stage 30.7 owns only the compact `ATH` display contract. Live ATH
sourcing, storage / session persistence, drawdown / tier recomputation,
enforcement, and public routing all remain out of scope and gated behind
a separate audit._
