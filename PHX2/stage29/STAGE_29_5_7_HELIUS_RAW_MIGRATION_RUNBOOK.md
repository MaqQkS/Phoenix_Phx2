# Stage 29.5.7 — Helius raw migration evidence producer/normalizer

## Why this stage exists

The Codex blocker audit found that PHX2 had **safe routers and a correct
confirmation but no real live migration evidence producer**. Every committed
migration source was a stub or a placeholder:

- the Stage 29.5 Helius WS adapter only parses **pre-normalized**
  `PUMP_AMM_MIGRATION` messages and explicitly **refuses** raw Helius JSON-RPC
  (it deferred "the raw-Helius decode path" to "a future operator-authorized
  normalizer substage");
- `Stage29_3NoMigrationEvidenceSource` returns `MIGRATION_SOURCE_UNKNOWN` for
  every mint;
- the Stage 29.3 Chainstack stream is real but extracts PumpSwap **swap** hints,
  not migration evidence;
- `integrations/helius_client.py` is a `pass` placeholder.

So a harvested live candidate could only ever die at
`MISSING_MIGRATION_EVIDENCE`. Stage 29.5.7 is the **smallest real migration
evidence producer/normalizer** that closes exactly that gap. It is the
raw-Helius decode path the Stage 29.5 WS adapter deferred.

It does **not** build another Stage 30.11 router, a dashboard, storage, a
daemon, public routing, or Stage 31; it does **not** patch ATH/drawdown; it does
**not** loosen the Stage 30.11.8 confirmation; it does **not** use fake migration
evidence in the production path.

## What proves a migration

A Pump.fun token graduates by creating its **PumpSwap (Pump AMM)** pool. The
migration-proving on-chain event is the PumpSwap **`create_pool`** instruction,
which emits the **`CreatePoolEvent`**:

| identity | value | provenance |
|---|---|---|
| PumpSwap program id | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | `pumpswap_program_constants` (vendored-IDL pinned) |
| `create_pool` instruction discriminator | `(233,146,209,142,207,104,64,188)` | vendored IDL, pinned by `test_stage_29_5_7_vendored_idl.py` |
| `CreatePoolEvent` discriminator | `(177,49,12,210,160,118,167,116)` | vendored IDL, pinned by `test_stage_29_5_7_vendored_idl.py` |
| `create_pool` account layout | `pool`=0, `base_mint`=3, `quote_mint`=4 | vendored IDL, pinned by `test_stage_29_5_7_vendored_idl.py` |

Ordinary post-migration trading is `Buy` / `Sell` (different discriminators,
different log markers) and is **rejected**.

## What the producer consumes and emits

**Input** — a raw Helius confirmed-transaction envelope (the standard Solana
JSON-RPC `getTransaction` / `transactionSubscribe` / enhanced-webhook object,
`encoding=json`), as a parsed `dict` or as raw `bytes`/`str` JSON. The fields it
reads: `slot`, `blockTime`, `signature` / `transaction.signatures[0]`,
`transaction.message.accountKeys` + `instructions`, `meta.err` /
`logMessages` / `innerInstructions` / `loadedAddresses`.

**Detection is bound to the create_pool instruction discriminator.** It reads the
plaintext log strings, the ready-made base58 `accountKeys` strings, the integer
instruction account indices, **and** the leading 8-byte Anchor discriminator of
each PumpSwap instruction's `data` — recovered by a bounded, hand-rolled,
stdlib-only big-integer base58 reader. There is **no** third-party `base58` /
`base64` import (the boundary scan forbids `base58` / `base64` / `construct`
imports) and **no** borsh event-/arg-data decode beyond the discriminator. A
migration is proven iff:

1. the envelope is a successful (non-failed), non-vote transaction with `meta`;
2. the PumpSwap program was **invoked** (`Program <id> invoke` log);
3. the Anchor **`Instruction: CreatePool`** program-log marker is present — a
   **coarse precondition only**: it is a tx-level string, not bound to any one
   instruction, so it can no longer prove a migration on its own (an ordinary swap
   carrying a stray `CreatePool` log fails at step 4);
4. **exactly one distinct** `(pool_account, base_mint, quote_mint)` resolves
   across the PumpSwap instructions **whose own `data` discriminator is the
   IDL-pinned `create_pool` discriminator** `(233, 146, 209, 142, 207, 104, 64,
   188)`, with the account layout (`pool`@0, `base_mint`@3, known `quote_mint`@4 —
   wrapped-SOL / USDC) read from that **same** instruction (top-level **and**
   inner/CPI — a Pump.fun migration calls `create_pool` via CPI). An ordinary
   `Buy` / `Sell` shares this **exact** layout, so the layout **alone** is never
   migration evidence; only the discriminator on that instruction distinguishes a
   migration from a swap. Value-identical quartets collapse to one, two distinct
   quartets fail closed;
5. a non-blank signature, a non-negative int slot, and a non-negative int
   `blockTime` are all present.

Why the instruction account layout and not token-balance owner-grouping: a
`create_pool` migration debits the creator's base+quote token accounts into the
new pool vaults, so **both** the creator and the pool PDA own a `{base, quote}`
pair — owner-grouping would be ambiguous. The `create_pool` instruction's own
account list names pool/base/quote at fixed IDL positions and is unambiguous; on
the Helius JSON shape those positions are already base58 strings, and the
instruction is identified by its own decoded Anchor discriminator, so the
pool/base/quote read is bound to the genuine `create_pool` migration instruction
and never to a look-alike `Buy` / `Sell`.

**Output** — a Stage 29.5 `Stage29_5MigrationEvidenceRecord` with
`migration_status=PRESENT`, `migration_source=HELIUS_WS`, the resolved quartet
(`pool_program_id` = PumpSwap), the `blockTime`-derived **strict trailing-`Z`**
anchor (`epoch_seconds_to_trailing_z_utc`, pure integer arithmetic — never
`+00:00`), the slot, the signature, and a `helius:sig:<sig>:slot:<slot>`
`source_event_ref`.

The producer's projection (`project_migration_evidence_to_sanitized_summary`)
maps a PRESENT record onto a sanitized summary whose field names equal the Stage
30.11.9 / 30.11.8 evidence fields **by value**:

- `base_mint` → `token_mint`
- `measurement_status` = `COMPLETE` (a proven on-chain `create_pool` migration is
  a complete migration measurement — **ATH is judged separately and later** by
  Stage 30.11.7, so `COMPLETE` here means "on-chain migration complete", not
  "post-migration ATH verified")
- `migration_timestamp_utc` → `migration_event_time_utc` (carried **verbatim** —
  never reformatted, so a non-`Z` anchor stays exactly as recorded and the Stage
  30.11.8 confirmation rejects it)
- `warnings` = explicit `()`
- `redaction_status` = `SAFE` (only public chain data)
- `source_event_ref` → `source_ref`

A summary is emitted **only** when every required evidence field exists; any
incomplete / non-PRESENT record fails closed to `None`.

## The chain it feeds (proved offline in `test_stage_29_5_7_composition.py`)

```
raw Helius migration envelope
  → normalize_helius_raw_migration_envelope         (Stage 29.5.7)
  → PRESENT Stage29_5MigrationEvidenceRecord
  → project_migration_evidence_to_sanitized_summary (Stage 29.5.7)
  → build_evidence_record_from_sanitized_projection (Stage 30.11.9, in the test)
  → Stage30_11_9MigrationEvidenceSourceAdapter.lookup_migration_evidence(token_mint)
  → resolve_candidate_migration / build_migration_resolver (Stage 30.11.8) → confirmed=True
  → enrich_harvested_candidate (Stage 30.11.7): MIGRATION cleared
      · with a green ATH resolver  → ENRICHED (ready for live runner)
      · with a missing ATH resolver → REJECTED at the ATH dimension (no transport)
```

The Stage-30 wiring lives only in the test; the Stage 29.5.7 production slice
imports **no** Stage 30 module (Stage 30 mirrors Stage 29 by value; the reverse
import is forbidden).

## Boundaries (pinned by `test_stage_29_5_7_boundaries.py`)

Zero env reads. Zero outbound network (HTTP / WS / gRPC / socket). No third-party
`base58` / `base64` / `solders` / `solana` / `helius` / Discord / Telegram /
wallet / trading import (the create_pool discriminator is recovered by a
hand-rolled, stdlib-only base58 reader — no imported decoder). No `datetime` /
`time` (the anchor is pure integer arithmetic; the clock is caller-injected). No Stage 30 import, no Stage 21-28
import, no Stage 29.3 / 29.4 import. No module-body Call except `@dataclass`. No
PHX1 path, no Pump.fun bonding-curve program-id literal, no URL host, no raw
secret. The Stage 30.11.8 confirmation is **not** modified or loosened.

## Operator notes

- Stage 29.5.7 is **offline-only**: the envelopes are injected. The real live
  Helius capture (a WebSocket / RPC subscription) lives **out-of-repo** at the
  separately, explicitly operator-authorized ceremony, which feeds harvested raw
  envelopes into `Stage29_5_7LiveMigrationEvidenceProducer.produce_migration_evidence`.
- Test fakes are confined to fixtures; the production path
  (`normalize_*` / `project_*` / the producer) calls no fake-proof module.
- Next blocker after this passes: the **ATH / drawdown** dimension (Stage
  30.11.7's ATH resolver) — migration has now cleared, so ATH is the next gate
  before transport. Do not patch it here.
