# PHX2 Stage 30.8.0 — Compact Session Artifact / Storage Readiness Spec Lock

Stage 30.8.0 is spec lock and tests only. Stage 30.8.0 ships exactly
three new files (this markdown, `stage30_8_manifest.py`, and the Stage
30.8.0 spec-lock pin test) plus one narrow test-only allowlist widening on
the Stage 30.0 inventory pin. Stage 30.8.0 ships ZERO production `.py`
file beyond the manifest, ZERO storage writer, ZERO database, ZERO SQLite,
ZERO filesystem artifact writer, ZERO zstd dependency or implementation,
ZERO day-rolling implementation, ZERO live provider call, ZERO Discord
send, ZERO env read, ZERO enforcement, ZERO public routing, ZERO trading /
wallet / social, ZERO drawdown / tier recomputation, and ZERO edit to any
runtime orchestrator / compact renderer / compact model / Stage 30.7 file.
Every Stage 30.8.1+ substage requires separately authorized scope before
any production `.py` file lands.

This document is the spec-lock / handoff contract for safely collecting
compact private ping / session artifacts so the operator can eventually
leave the bot running and collect useful data for longer-running operation
/ eventual 24/7 collection. It is prose plus closed-set token tables. It
carries no provider credential, no private transport destination, no
provider host address, no transport scheme prefix, no raw request /
response payload field name, and no request auth-metadata (see Section
13).

## 1. Stage purpose

Stage 30.8 is the compact session artifact / storage-readiness family of
Stage 30. Stage 30.8 prepares compact private ping / session artifact
collection so the operator can eventually leave the bot running and
collect useful data safely, without:

- bloating the repo,
- losing dedupe / session identity,
- writing secrets,
- writing raw provider payloads,
- enabling enforcement / trading / public routing, or
- coupling storage to live provider code.

The compact `MC` / `ATH` / `Mig` / `LP` / `Net` display contract is now
offline-complete and proven (Stage 30.7 closed the compact `ATH` display;
Stage 30.4 / 30.5 closed `MC` / `LP` / `Mig`). The natural next problem is
durable, bounded session-artifact capture and storage readiness for
continuous collection. Stage 30.8.0 LOCKS that design; it implements no
part of it.

Stage 30.8.0 specifically is spec lock and tests only. Stage 30.8.0 is NOT
a storage implementation, is NOT a writer, is NOT a database, is NOT live
runtime, is NOT Discord, and is NOT a tag or a closure. Stage 30.8.0 makes
no commit, no tag, and no push by itself.

## 2. Non-goals

Stage 30.8.0 explicitly does NOT implement any of the following. Stated as
the closed non-goal list (each is a hard negative for this slice): no
writer, no database, no SQLite, no zstd (dependency or implementation), no
day rolling, no live run, no provider call, no Discord send, no
enforcement, no public routing, no trading or wallet logic, no drawdown /
tier recomputation.

Restated for the record, Stage 30.8.0 adds no writer of any kind, opens no
database, ships no SQLite access, adds no zstd dependency, performs no live
run, makes no provider call, performs no Discord send, reads no
environment variable, and edits no runtime orchestrator, no compact
renderer, no compact model, and no Stage 30.7 file.

## 3. Compact artifact types

Stage 30.8 pins the following closed set of compact artifact kinds. Stage
30.8.0 LOCKS the vocabulary only; it writes none of them.

1. `compact_session_summary` — one rolled-up summary per private soak
   session: safe counters (pings emitted, dispatch attempts, dedupe
   suppressed, errors), session id / run id, and the Stage 30.6-style
   per-run storage budget snapshot. Carries no raw provider payloads.
2. `compact_ping_artifact` — one durable record per terminal compact
   private ping: the already-rendered compact body text plus the
   operator-visible display fields (`MC` / `ATH` / `Mig` / `LP` / `Net`)
   plus the safe-shape opaque identifiers. This is the sanitized Stage
   30.2 `CompactPingSnapshotRecord` projection, never the input or raw
   provider data.
3. `compact_dispatch_attempt_artifact` — one record per dispatch / send
   attempt (including provider retry attempts): a sanitized transport
   status code and the attempt's dedupe key. Multiple attempt artifacts
   may exist for a single terminal ping (see Section 9).
4. `compact_error_artifact` — one record per closed-set error reason
   token encountered during capture (a reason code only; never a raw
   exception message, raw response body, or raw provider payload).
5. `compact_storage_budget_snapshot` — one record of the Stage 30.6
   per-run storage budget state (raw bytes written, durable rows written,
   archived / compressed bytes, dropped / pruned / sealed counts, dedupe
   suppressed count, disk usage percent before / after).

## 4. Required identity fields

Every persisted compact artifact carries the following stable identity
axes. Each is a safe-shape opaque id, a closed-set token, an ISO-8601 UTC
timestamp, or a version string. NONE is a secret, a raw payload, a host,
or a transport destination.

- `stage_id` — the producing stage id (for example `30.8`).
- `run_id` — the runtime-context run identifier.
- `session_id` — the private-soak session identifier.
- `ping_id` — the compact ping identifier.
- `candidate_id` — the candidate identifier, when available.
- `token_mint` — the candidate / token mint (safe-shape base58), when
  available.
- `normalized_event_id` — the `provider_event_id` / `normalized_event_id`,
  when available (a sanitized opaque id only).
- `observed_at_utc` — the observation timestamp (ISO-8601 UTC).
- `artifact_created_at_utc` — the artifact creation timestamp (ISO-8601
  UTC, from the caller-injected clock).
- `artifact_schema_version` — the Stage 30.8 artifact schema version
  string.
- `artifact_kind` — one of the closed-set artifact kinds in Section 3.
- `dedupe_key` — the dedupe key / `dedupe_fingerprint` (see Section 9).
- `compact_ping_schema_version` — the renderer / compact ping schema
  version echo (for example the Stage 30.2 `compact_ping` schema version),
  when available.

## 5. Required compact content fields

Stage 30.8 may persist the following already-rendered, redaction-safe
compact content fields. These mirror the Stage 30.2 compact display fields
and the closed-set status codes; they are persisted ONLY after the private
send-safe redaction guard (Section 10), never as raw provider data.

- `compact_body_text` — the rendered compact private-ping body string.
- `mc_display` — the `MC` display string (for example `$83k` or
  `Unknown`).
- `lp_display` — the `LP` display string.
- `net_display` — the `Net` display string.
- `ath_display` — the `ATH` display string (for example `$120k` or
  `Unknown`).
- `migration_display` — the `Mig` display string (`Known` / `Unverified`
  / `Unknown`).
- `eligibility_status` — the decision / eligibility status, when already
  present (a closed-set status token).
- `warning_reason_codes` — the closed-set warning / reason codes.
- `terminal_outcome_code` — the terminal outcome code.
- `transport_status` — the sanitized transport status code, when present.

The proven offline compact state line these fields reconstruct is, for
the record:

```
• MC: $83k | ATH: $120k | Mig: Known
```

## 6. Forbidden fields

A Stage 30.8 artifact must NEVER carry any of the following. A future
writer (Stage 30.8.2+) must fail closed (drop the artifact) on any of
them:

- a private webhook destination,
- a provider API-key,
- a request auth-metadata field,
- a signed-token credential,
- an environment variable value,
- a raw provider payload,
- a raw transaction or log payload,
- a full Discord response body (it may contain a secret),
- a wallet private key,
- signing material,
- a user secret,
- an unredacted URL,
- an arbitrary nested raw dict or list payload,
- a binary blob.

The artifact field set is a closed set of safe scalars (opaque ids,
closed-set tokens, already-rendered display strings, timestamps, version
strings, integer counters). No field on any artifact admits a secret, a
raw provider payload, or an unredacted transport destination.

## 7. Storage location policy

- The default artifact storage root MUST default to a location OUTSIDE the
  repository working tree, unless the operator explicitly configures an
  in-tree path for a short controlled test.
- The repo path MUST NOT be used for long-running artifact collection;
  long-running artifacts belong outside the repository.
- Test fixtures MUST use temporary directories only (a `tmp_path` style
  temp dir), never the repo and never a real operator collection root.
- Stage 30.8.0 adds NO writer: there is no filesystem artifact writer, no
  database, and no SQLite in this slice. The storage location policy is a
  design lock only.

## 8. Retention and rolling policy

The intended future retention behavior (locked here, implemented later):

- day-partitioned artifacts (one partition per UTC day);
- compact JSONL or small JSON records (append-only, one artifact per
  line); never a single giant forever-growing file;
- optional future compression with zstd ONLY after zstd is separately
  authorized; Stage 30.8.0 adds no compression implementation and no zstd
  dependency;
- retention bounded by the Stage 30.6 storage budget policy: the soft cap
  and hard cap references in Section 12 gate writes, and a per-run storage
  budget snapshot records usage.

## 9. Dedupe policy

Stage 30.8 reuses the Stage 30.6 dedupe identity (mint + alert / tier /
state class + policy-version / session-scope axis). The compact-artifact
dedupe rules:

- the dedupe identity for a `compact_ping_artifact` is its `dedupe_key`
  (the Stage 30.6 dedupe key / `dedupe_fingerprint`);
- the same run / session / ping MUST NOT create duplicate final ping
  artifacts — there is exactly one terminal `compact_ping_artifact` per
  (session, ping) dedupe identity;
- provider retry attempts are recorded as separate
  `compact_dispatch_attempt_artifact` records, but they collapse to only
  one terminal ping artifact;
- the dedupe record MUST NOT include any secret, any raw provider payload,
  or any transport destination — it carries only the safe dedupe key and
  the safe identity fields.

## 10. Redaction policy

- all persisted strings MUST pass a redaction scan or be substituted with
  a closed-set safe token (`SAFE` / `REDACTED` / `Unknown`);
- the `compact_body_text` is persisted ONLY after the same private
  send-safe redaction guard the compact ping already passes;
- the future artifact writer MUST fail closed on any unsafe field: on a
  redaction-scan hit it drops the artifact and records a
  `compact_error_artifact` reason code, rather than persisting the unsafe
  value;
- the redaction guard runs before any artifact is written and again before
  any archive proof is considered safe (mirroring the Stage 30.6
  pre-archive redaction scan).

## 11. Future implementation stages

Stage 30.8 is sequenced fake / offline before live, smallest reversible
slice first:

- Stage 30.8.0 — compact session artifact / storage-readiness spec lock +
  manifest + pin test only (this slice). No production `.py` beyond the
  manifest; no writer.
- Stage 30.8.1 — pure compact artifact models + validators. No writer, no
  database, no filesystem access; closed-set models + a deterministic
  validator only.
- Stage 30.8.2 — temp-dir artifact writer with fake / offline tests only.
  A bounded writer proven entirely against temporary directories; no live
  run, no real collection root.
- Stage 30.8.3 — dedupe / session index integration, offline. Wires the
  Stage 30.6 restart-safe dedupe / session seen-state into the artifact
  index using fakes only.
- Stage 30.8.4 — controlled compact session artifact proof. A single
  controlled, separately operator-authorized capture proof; gated behind
  the earlier offline slices.

A later closure / handoff slice may follow Stage 30.8.4 to record the
family closure, mirroring the Stage 30.7.4 pattern. Numbering may be
adjusted if the project style suggests a better split; each substage
remains separately authorized.

## 12. Prior context and proof handoff

Stage 30.8 builds directly on two already-closed Stage 30 families.

### 12.1 Stage 30.7 closure / proof handoff

Stage 30.8 builds on the closed Stage 30.7 ATH context family. The Stage
30.7 closure record is `STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md` and the
caller handoff is `STAGE_30_7_ATH_CONTEXT_HANDOFF.md`. Stage 30.7 produced,
fully offline (no Discord send, no live provider call), the final compact
proof line:

```
• MC: $83k | ATH: $120k | Mig: Known
```

This is the exact compact state line a `compact_ping_artifact` durably
captures. Stage 30.8.0 edits NO Stage 30.7 file.

### 12.2 Stage 30.6 storage budget handoff

Stage 30.8 storage budgeting is GOVERNED BY the Stage 30.6 storage budget
policy (`STAGE_30_6_0_STORAGE_DEDUPE_SPEC_LOCK.md` plus the Stage 30.6
storage budget models / evaluator). The soft cap (a soft disk alarm around
65% disk used) fires a private operator warning; the hard cap (a hard stop
around 90% disk used) refuses new writes and fails closed. The Stage 30.8
`compact_storage_budget_snapshot` records the Stage 30.6 per-run storage
summary fields. Stage 30.8.0 references those constants by value; it
imports no Stage 30.6 module and re-implements no budget logic.

## 13. Forbidden terms and secret hygiene

This document is held to the same redaction hygiene as the Stage 30.6.0 /
30.7.4 records. It carries no provider credential strings, no private
transport destination strings, no provider host address strings, no
transport scheme prefixes, no raw request-payload or response-payload
field names, and no request auth-metadata strings. It records only
closed-set tokens, field names, thresholds, prose, and safe design labels.

The Stage 30.8.0 pin test enforces this by scanning this document, the
manifest, and the test, case-insensitively, against a split-literal
forbidden-substring vocabulary, so none of the three files can carry any
of the sanitized-away substrings even inside a negative claim.

---

_Stage 30.8.0 is spec lock and tests only._

Ceremony discipline, restated plainly for the record:

- There is no live provider call during Stage 30.8.0 implementation.
- There is no Discord send during Stage 30.8.0 implementation.
- There is no storage writer, no database, no SQLite, and no filesystem
  artifact writer at Stage 30.8.0.
- There is no zstd dependency and no zstd implementation added at Stage
  30.8.0.
- There is no day-rolling implementation at Stage 30.8.0.
- There is no runtime orchestrator change, no compact renderer change, no
  compact model change, and no Stage 30.7 file change at Stage 30.8.0.
- There is no enforcement, no public routing, and no trading / wallet /
  social surface at Stage 30.8.0.
- There is no drawdown / tier recomputation at Stage 30.8.0.
- There is no Stage 25 / 27 / 28 / 29 (or Stage 29.5) production import at
  Stage 30.8.0.
- There is no commit, no tag, and no push performed by Stage 30.8.0
  implementation. Commit gating is a separate operator decision after
  audit.
