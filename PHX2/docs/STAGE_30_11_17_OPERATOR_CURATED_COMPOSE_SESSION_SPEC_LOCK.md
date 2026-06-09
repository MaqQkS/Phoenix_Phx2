# Stage 30.11.17 — Operator-Curated Compose Session (SPEC LOCK)

**Stage label:** `phx2 stage 30.11.17: add operator-curated compose session`

**Status:** committed, offline / fakes-only, **no real send**. The controlled
live one-send ceremony remains a SEPARATE, explicitly operator-authorized step
that is **not** built or run by this stage.

---

## 1. Purpose

Create the smallest pure, bounded **session** wrapper over the already-proven
single-candidate no-send path:

```
operator-curated candidate list
  → Stage 30.11.13 revalidation request (one per entry)
  → compose_no_send_dispatch_deduped(...)           # committed Stage 30.11.15
  → ONE shared injected Stage 30.11.15 dedupe ledger
  → per-entry redaction-safe result
  → rolled-up redaction-safe session summary (counts + stop_reason)
```

Before Stage 30.11.17 every committed send-ready surface was single-candidate:
`compose_no_send_dispatch` / `compose_no_send_dispatch_deduped` take exactly one
`Stage30_11_13RevalidationRequest`, and the Stage 30.11.16 real-send guard
forwards exactly one deduped result. Stage 30.11.17 adds the missing committed
**bounded multi-candidate session** that runs an operator-curated list through the
deduped composer under hard caps, sharing one ledger so an in-run duplicate is
suppressed exactly as a cross-run duplicate is, and rolls up a redaction-safe
report. It is the curated counterpart of the deferred real harvest adapter
binding — the operator curates the list by hand; nothing is harvested live.

## 2. What this stage is NOT (hard exclusions)

- **No** real send. The only transport is the injected committed Stage 30.11.5
  recording **fake** client (a RECORDED would-send, never a real send).
- **No** call to / import of the Stage 30.11.16 real private transport guard.
- **No** real harvest adapter binding (Stage 30.11.6 `harvest_live_candidates`
  with a real assembler/flattener stays deferred to the out-of-repo ceremony).
- **No** live provider surfaces (Chainstack / Yellowstone gRPC, Stage 28 / Stage
  29 live provider sessions). No Stage 21–29 imports of any kind.
- **No** Discord / webhook call. No network, no env read, no wall-clock read
  (every clock is injected).
- **No** wallet / signing / trading. **No** public / subscriber / paid routing.
- **No** renderer polish, **no** `while`/daemon loop, **no** background service.
- **No** mutation of the operator ceremony ledger at
  `C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl`. The ledger is always
  caller-injected; committed tests use an in-memory ledger or a `tmp_path` JSONL
  ledger.
- **No** source edits outside the approved file list. **No** commit/tag/push
  until operator approval.

## 3. Files

### Added (production — `PHX2/stage30/`)
- `stage30_11_17_operator_curated_candidate_list_models.py` — pure leaf models +
  closed-set vocabularies + cap validator + default config (imports **no** PHX2).
- `stage30_11_17_operator_curated_compose_session.py` — the bounded session
  (single for-loop) + classifier + redaction self-scan.
- `stage30_11_17_fake_curated_session_proof.py` — thin offline driver.

### Added (docs)
- `PHX2/docs/STAGE_30_11_17_OPERATOR_CURATED_COMPOSE_SESSION_SPEC_LOCK.md` (this).

### Added (tests — `PHX2/tests/stage30/`)
- `test_stage_30_11_17_operator_curated_candidate_list_models.py`
- `test_stage_30_11_17_operator_curated_compose_session.py`
- `test_stage_30_11_17_fake_curated_session_proof.py`
- `test_stage_30_11_17_boundaries.py`
- `test_stage_30_11_17_manifest.py`

### Updated
- `PHX2/stage30/stage30_11_manifest.py` — Stage 30.11.17 manifest section +
  `__all__` exports only (constants mirrored BY VALUE).

### Reuse / import-only (NOT edited)
- `stage30_11_15_no_send_dedupe_guard.py` (`compose_no_send_dispatch_deduped`,
  `Stage30_11_15DedupedComposeResult`)
- `stage30_11_15_ping_dedupe_ledger.py` (`InMemoryPingDedupeLedger`,
  `JsonlPingDedupeLedger`, `PingDedupeLedger`)
- `stage30_11_13_committed_no_send_composer.py` (closed-set compose decision /
  reason tokens; `Stage30_11_13RevalidationRequest` is used by tests only)
- `stage30_11_5_fake_live_wiring_proof.py` (`Stage30_11_5RecordingFakeTransportClient`)
- `stage30_11_manifest.py` (constants)

## 4. Model / API shape

- `Stage30_11_17OperatorCuratedCandidate{ request: Any, curated_label: Optional[str] }`
- `Stage30_11_17SessionConfig{ max_candidates: int, max_compositions: int, created_at_utc: str }`
- `Stage30_11_17SessionEvent{ index, candidate_id, token_mint, curated_label,
  outcome, compose_decision, compose_reason, dedupe_verdict, dedupe_reason,
  transport_attempts, body_present, created_at_utc }`
- `Stage30_11_17SessionResult{ events, candidates_seen, compositions_attempted,
  dispatched, rejected, dedupe_blocked, errors, would_send_recorded, stop_reason,
  redaction_status, created_at_utc }`
- `run_stage30_11_17_operator_curated_compose_session(candidates, *, config,
  ledger, ath_transport, ath_endpoint_secret, now_utc, transport_client,
  now_seconds, ath_timeout_seconds=10, market_context_max_age_seconds=None,
  ttl_seconds=None) -> Stage30_11_17SessionResult`

## 5. Bounds + defaults

- Dry / no-send only (fake recording client).
- `max_candidates <= 10` (hard cap, mirrors committed Stage 30.11.5).
- `1 <= max_compositions <= max_candidates`.
- ONE shared injected ledger across all entries (in-memory / temp in tests).
- Single bounded `for` loop; no `while`; no daemon.
- Redaction-safe report only (`redaction_status` self-attested; no body / url /
  secret ever carried — only closed-set tokens + safe-echo ids).

## 6. Per-entry outcome taxonomy (closed set)

| outcome | when |
| --- | --- |
| `DISPATCHED` | compose decision `NO_SEND_DISPATCHED` (recorded would-send via fake client) |
| `DEDUPE_BLOCKED` | compose reason `DEDUPE_SUPPRESSED_DUPLICATE` (shared-ledger duplicate within TTL) |
| `REJECTED` | any other fail-closed composer rejection (stale/missing market context, ineligible tier, invalid request, …) |
| `ERROR` | dedupe-unavailable (`DEDUPE_UNAVAILABLE`), a missing compose result, or an unexpected exception (caught; the session never raises mid-list) |

## 7. Stop reasons (closed set)

`COMPLETED_ALL_CANDIDATES` · `STOPPED_BY_CANDIDATE_CAP` ·
`STOPPED_BY_COMPOSITION_CAP`.

## 8. Test obligations (proven)

- list length cap enforced; composition cap enforced; out-of-cap config raises.
- no live / webhook / Discord / real transport call possible (only the fake
  recording client is reached; `would_send_recorded` counts recorded would-sends).
- no Stage 28/29 imports; no Stage 30.11.16 guard import/call; no Stage 30.11.6
  harvest import (AST boundary scan over the three production modules).
- `compose_no_send_dispatch_deduped` called once per eligible curated entry until
  a cap.
- ONE shared ledger blocks an in-session duplicate; the caller-injected ledger is
  used; the operator ceremony `ping_dedupe.jsonl` is never referenced anywhere.
- per-entry outcomes include `DISPATCHED` / `REJECTED` / `DEDUPE_BLOCKED` /
  `ERROR`; the rolled-up summary carries `stop_reason` + counts that reconcile.
- report redacts secrets (`redaction_status == REDACTED`; an unsafe id / label is
  redacted to `REDACTED_UNSAFE_ID`, never echoed raw).
- boundary tests forbid public / subscriber / wallet / trading / live-provider
  imports; manifest mirrors all constants BY VALUE.

## 9. Next allowed step

`operator-authorized controlled live ceremony (separate step)`. Stage 30.11.17
ships no part of it. A real one-send would compose the curated session's
`DISPATCHED` result through the SEPARATE Stage 30.11.16 real-send guard with a
real audited transport + a valid operator-auth sentinel — an explicit,
separately-authorized ceremony, not this stage.
