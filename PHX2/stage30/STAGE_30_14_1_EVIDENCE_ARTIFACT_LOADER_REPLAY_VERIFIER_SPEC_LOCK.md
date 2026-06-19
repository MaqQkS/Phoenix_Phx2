# Stage 30.14.1 — Evidence Artifact Loader + Replay Verifier (SPEC LOCK)

Build #26, substage 30.14.1 (Build 26.1C). Committed, OFFLINE, SYNTHETIC-fixture only,
no-send. This document is the locked contract for the Stage 30.14.1 evidence models leaf +
evidence artifact loader + replay verifier + manifest. It composes (never edits) the
committed Stage 30.14.0 replay → shadow-dispatch path and the committed Stage 29.5 migration
models.

## Build numbering

- **Build #24** — committed offline WS auto-seeder (Stage 30.13.0–30.13.4).
- **Build #25** — the real **read-only** Helius WS capture executed out-of-repo; it
  persisted only the discovery **decision** ledger (the accepted mint + four counts), **not**
  the underlying migration evidence.
- **Build #26 (Stage 30.14.x)** — take a discovered migration evidence record and run it
  through the committed recheck → fake-dispatch chain.
  - **Build 26.0 (Stage 30.14.0)** — committed, offline, **synthetic** plumbing proof: an
    in-memory replay source feeds a hand-built record through the committed auto-seeder +
    recheck/fake-send chain.
  - **Build 26.1C (this slice, Stage 30.14.1)** — the committed, offline loader that turns a
    *persisted* `build26_capture_evidence.jsonl` artifact into validated, reconstructed
    records and replays them through the committed Stage 30.14.0 path. SYNTHETIC JSONL
    fixtures only.
  - **Build 26.1B (deferred, blocked)** — producing a *real* evidence-bearing artifact and
    pointing the committed loader at it. Out-of-repo; operator-authorized; needs **no code
    change** (see Handoff).

## Purpose

Prove, with SYNTHETIC `build26_capture_evidence.jsonl` fixtures only, that a persisted
evidence artifact can be loaded offline, validated field-by-field against the locked 15-field
Build 26.1 schema, reconstructed into a `Stage29_5MigrationEvidenceRecord` **without
fabrication**, and replayed through the committed Stage 30.14.0 path to a **fake dispatch
decision** — with the dispatched mint tracing back to the discovered mint, the committed
chain's re-derived summary equal to the persisted attestation, and **no real send**, no
durable ledger, and no provider/network/secret surface.

## Locked composition (top-down)

```
build26_capture_evidence.jsonl  (SYNTHETIC fixtures only; never a real Build 26.1B artifact)
  → Stage30_14_1EvidenceArtifactLoader.load_evidence_from_path(path, created_at_utc=...)
      [LOADER tier: read-only json + pathlib]
      byte cap (pre-read stat) → utf-8 read → line cap → per-line json object
      → structural schema_version gate (== build26_1_v0_capture_evidence)
      → per-line 14-field validation (first failing check wins)
      → source_ref == helius:sig:<migration_signature>:slot:<migration_slot>
      → dedupe by token_mint + migration_signature (first-wins)
      → reconstruct Stage29_5MigrationEvidenceRecord  (token_mint→base_mint /
            migration_event_time_utc→migration_timestamp_utc / source_ref→source_event_ref;
            no fabrication; committed validator backstop)
      = Stage30_14_1EvidenceLoadResult(outcomes, accepted_records, accepted_attestations,
            summary, redaction_status)
  → run_stage30_14_1_replay_verify(load_result, price/market/ath fakes + clocks, ...)
      [VERIFIER tier: strict stdlib] one committed pass PER accepted record (≤ max_replay)
      → Stage30_14ReplayDiscoverySource((record,))                  (committed)
      → run_stage30_14_0_real_discovery_to_shadow_dispatch(...)     (committed; locked 1/1/1)
      → round-trip: committed seeded_summaries[0] == persisted attestation
      = Stage30_14_1ReplayVerifyResult(outcomes, shadow_results, aggregate flags)
```

## Locked 15-field Build 26.1 capture-evidence schema → reconstruction

| JSONL field | validation | → reconstructed record field |
|---|---|---|
| `schema_version` | `== build26_1_v0_capture_evidence` (structural raise on mismatch) | (record uses its dataclass default) |
| `token_mint` | safe mint/pool string **and** base58 pump-suffix | `base_mint` |
| `migration_status` | `== PRESENT` | `migration_status` |
| `migration_source` | closed-set, `!= UNKNOWN` | `migration_source` |
| `pool_account` | safe mint/pool string | `pool_account` |
| `pool_program_id` | safe mint/pool string | `pool_program_id` |
| `quote_mint` | safe mint/pool string | `quote_mint` |
| `migration_event_time_utc` | UTC ISO-8601 | `migration_timestamp_utc` |
| `migration_slot` | non-negative int (not bool) | `migration_slot` |
| `migration_signature` | non-blank str | `migration_signature` |
| `source_ref` | `== helius:sig:<sig>:slot:<slot>` | `source_event_ref` |
| `observed_at_utc` | UTC ISO-8601 | `observed_at_utc` |
| `measurement_status` | `== COMPLETE` | (attestation; round-trip cross-checked) |
| `redaction_status` | `== SAFE` | (attestation; round-trip cross-checked) |
| `warnings` | empty list `[]` | (attestation; round-trip cross-checked) |

## Locked discipline (every Stage 30.14.1 production module)

- **Two tiers.** The models leaf + the verifier are STRICT (`__future__` / `typing` /
  `dataclasses` only; the leaf imports **no** PHX2 module). The loader is the one read-only
  filesystem surface and additionally admits `json` + `pathlib`.
- The loader imports ONLY the 30.14.1 models leaf + the committed Stage 29.5 migration models
  (the scoped discovery-currency deviation). The verifier imports ONLY the 30.14.1 models
  leaf + the committed Stage 30.14.0 orchestrator + the committed Stage 30.14.0 replay
  source. No Birdeye / Stage 27 / Stage 28 / Stage 29.1–29.4 import; the committed Stage
  29.5.7 projection / WS adapter are reached **transitively** through the committed
  orchestrator.
- No `os.environ` / `os.getenv` (no env read). No `time` / `datetime` (no wall-clock read;
  every timestamp/clock is caller-injected). No network / socket / HTTP / gRPC / WebSocket.
  No database / compression. **No filesystem WRITE** (`.write_text` / `.write_bytes` /
  `.mkdir` / bare `open(`); the loader uses read-only `Path` / `.exists` / `.is_file` /
  `.stat` / `.read_text` only. No durable ledger read/mutation. No module-level Call (no
  implicit I/O at import time). No `while` loop / daemon.
- The pump-suffix predicate + the `source_ref` builder are mirrored BY VALUE in the models
  leaf (pin-tested against the committed Stage 30.13.0 + Stage 29.5.7 sources). Redaction
  self-scan over every emitted outcome string field; an unsafe mint is echoed as
  `REDACTED_UNSAFE_ID`, never raw. No `://` literal, no URL / webhook / auth / key / RPC /
  PEM needle in source.

## Locked caps (Build 26.1C; all fail closed, never truncate)

- `max_bytes` default `1_048_576` / hard `8_388_608` — checked against file size **before
  read**.
- `max_lines` default `128` / hard `4096`.
- `max_accepted` default `64` / hard `256`.
- `max_replay` default `8` / hard `64` — bounds committed passes per verify call.
- The committed Stage 30.14.0 path remains internally locked to `max_seed = max_rechecks =
  max_fake_dispatches = 1`.

## Locked failure behavior

- **Structural (raise `Stage30_14_1EvidenceLoadError`):** `UNREADABLE_ARTIFACT`,
  `FILE_TOO_LARGE`, `TOO_MANY_LINES`, `TOO_MANY_RECORDS`, `MALFORMED_JSONL_LINE`,
  `WRONG_SCHEMA_VERSION`, `INVALID_CAP`.
- **Per-line content (REJECTED outcome; or raise under `strict=True`):**
  `MISSING_REQUIRED_FIELD`, `NON_PRESENT_STATUS`, `INVALID_SOURCE`, `UNSAFE_AXIS_SHAPE`,
  `NOT_PUMP_SUFFIX`, `MALFORMED_TIMESTAMP`, `BAD_SOURCE_REF`, `INCOMPLETE_MEASUREMENT`,
  `UNSAFE_REDACTION`, `NONEMPTY_WARNINGS`, `DUPLICATE_MINT`, `DUPLICATE_SIGNATURE`.
- **Verify (raise `Stage30_14_1ReplayVerifyError`):** `NOT_A_LOAD_RESULT`,
  `INVALID_MAX_REPLAY`, `TOO_MANY_REPLAY_RECORDS`. A non-fake provider source / out-of-bounds
  locked cap surfaces the committed `Stage30_14ShadowDispatchError`.

## Required proof (asserted by the focused tests)

- a full valid synthetic artifact loads (N accepted, reconstructed fields correct);
- every invalid/missing/unsafe field fails closed with the exact closed-set reason;
- `source_ref` form/mismatch rejected; non-pump rejected; unsafe redaction rejected;
  non-empty warnings rejected; duplicate mint/signature deterministically deduped;
- oversized / too-many-lines / too-many-records / out-of-bounds cap fail closed;
- full replay reaches `dispatched == 1` per record; the dispatched mint traces to the
  discovered mint (`mint_traces_through is True`); `real_send_performed == False`;
  `real_send_guard_invoked == False`; the persisted attestation round-trips against the
  committed re-derived summary;
- no durable ledger path/import/reference; no Discord/webhook/send/approval/arm surface; no
  Stage 28 / gRPC / Yellowstone surface;
- redaction clean (load + verify `redaction_status == REDACTED`);
- the two-tier import allowlist + manifest pins hold.

## Non-goals (NOT built in Stage 30.14.1)

- No real capture / socket / RPC; no real Discord; no live send; no approval token; no arm
  flip; no durable `ping_dedupe` ledger access; no wallet / signing / trading; no public /
  subscriber routing; no Stage 28 / gRPC / Yellowstone; no `PHX2/main.py` live-flag edit; no
  edit of any committed Stage 27 / 28 / 29 / 30.11 / 30.13 / 30.14.0 production file; no
  copying of a real Build 26.1B artifact (or any out-of-repo capture) into the repo; no tag;
  no push.

## Handoff (Build 26.1B — deferred and blocked)

Pointing the committed Stage 30.14.1 loader at a **real, evidence-bearing artifact** (so the
dispatched mint traces to a real `*pump` discovery) is a SEPARATE, explicitly
**operator-authorized** step. It is **blocked** until an evidence-preserving capture persists
the redaction-safe 15-field schema (`token_mint` + `migration_event_time_utc` + `source_ref`
in the `helius:sig:<sig>:slot:<n>` form + `migration_slot` + `migration_signature` + the
quartet + `warnings=[]` + `COMPLETE` + `SAFE`). It requires **no code change**: the loader
validates a closed-set schema and special-cases no source, so a real `HELIUS_WS`-sourced
artifact loads through the same path as a synthetic one. Build 26.1C fabricates none of those
fields; it reconstructs only what the artifact supplies. No real evidence is copied into the
repo.
