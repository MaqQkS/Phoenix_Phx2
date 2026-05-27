# Stage 29.5.6 Private Ping Migration Context Body Injection Runbook

## 1. Canonical Stage 29.5.6 mission sentence

Stage 29.5.6 is the private ping body migration context injection substage that adds a deterministic redaction-safe transport-wrapper injector which first tries to append the full already-rendered Stage 29.5.5 migration context block to the operator-visible private Discord ping body, falls back to a deterministic compact migration-context block built from already-revalidated closed-set / display fields on the rendered block when the full append would exceed the local 1900-character combined-body cap, appends the compact block when the compact append fits the cap, skips the append entirely only when the compact append would also overflow (never truncates the rendered block, never appends a partial / invented block, never appends raw JSON), threads one optional `private_discord_body_injector` kwarg into `run_stage29_3_first_private_tradeable_smoke`, gates the injection mode-3-only and opt-in, validates the wrapped transport candidate via `callable(getattr(candidate, "send_one_audited_post", None))` before replacing the original Stage 28.9 transport and falls back to the unwrapped transport on any wrap-time exception or non-conforming candidate, mutates a copied payload only, re-validates the rendered block via the Stage 29.5.5 closed-set safety validator immediately before each append, and modifies no Stage 27, Stage 28, Stage 29.4, Stage 29.5, Stage 29.5.2, Stage 29.5.3, Stage 29.5.4, or Stage 29.5.5 production source.

## 2. Scope

Stage 29.5.6 ships:

- a Stage 29.5.6 transport-wrapper injector class (`Stage29_5_6PrivateDiscordBodyInjector`) that consumes a duck-typed Stage 29.5.5 recorder reference via its constructor and exposes a single `wrap_transport(inner_transport) -> object` method returning a thin wrapper transport;
- the wrapper transport (`_Stage29_5_6WrappedTransport`, module-private) that implements the Stage 28.6 / Stage 28.9 `send_one_audited_post(*, webhook_identity, payload)` shape, intercepts the payload immediately before forwarding to the inner Stage 28.9 transport, optionally appends the most recently recorded Stage 29.5.5 rendered block's `body_text` to a copy of `payload["content"]`, and forwards the resulting payload copy verbatim through the inner transport;
- a constants-only Stage 29.5.6 manifest (`stage29_5_6_manifest.py`) re-exporting the locked enforcement / redaction tokens, the locked schema versions, and the Stage 29.5.6 forbidden-surface tuple;
- this runbook and a dedicated Stage 29.5.6 test surface;
- one tiny edit to `stage29_3_tradeable_smoke.py`: a new keyword-only `private_discord_body_injector: Optional[object] = None` kwarg on `run_stage29_3_first_private_tradeable_smoke` threaded one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`. The mode-3 dispatch path, after constructing the Stage 28.9 `Stage28_9PrivateWebhookTransport` and before calling `run_stage28_9_live_provider_session(...)`, conditionally wraps the transport via `private_discord_body_injector.wrap_transport(transport)` inside a `try` / `except Exception: pass` guard AND a conformance gate: the candidate returned by `wrap_transport` replaces the original `transport` only when `callable(getattr(candidate, "send_one_audited_post", None))` is `True`. A non-conforming candidate (a `None` return, a bare object without `send_one_audited_post`, or an object whose `send_one_audited_post` attribute is not callable) preserves the original transport. Any wrap-time exception likewise preserves the original transport. The kwarg is annotated `Optional[object]` so the Stage 29.3 production source carries ZERO `stage29_5*` imports (mirroring the Stage 29.5.4 + Stage 29.5.5 typing discipline). Modes 1 and 2 never construct the Stage 28.9 transport stack and the injector is therefore never invoked on those modes.

Stage 29.5.6 ships ZERO live Chainstack gRPC call, ZERO live Birdeye HTTP call, ZERO live Helius WebSocket call, ZERO live Discord send during implementation or tests, ZERO Telegram / X / social sender, ZERO automated trading / wallet / private-key / signer surface, ZERO public / subscriber / paid-tier routing, ZERO Stage 26 enforcement activation, ZERO new env names, ZERO new third-party runtime dependency, ZERO Pump.fun bonding-curve decoder, ZERO Dexscreener / Helius-as-price-source, ZERO legacy (pre-PHX2) import path, ZERO Stage 29.4 runtime wiring change, ZERO Stage 29.5 manifest inventory change, ZERO Stage 29.5.2 manifest inventory change, ZERO Stage 29.5.3 manifest inventory change, ZERO Stage 29.5.4 manifest inventory change, ZERO Stage 29.5.5 manifest inventory change, ZERO modification to the Stage 27.5 private ping renderer, ZERO modification to the Stage 28.4 audited HTTP transport, ZERO modification to the Stage 28.9 dispatch wrapper, ZERO modification to the Stage 28.2 / 28.6 dispatch ledger record shape, ZERO change to the Stage 28.9 dispatch counter axes, ZERO change to the Stage 29.3 mode-1 + mode-2 dispatch paths, ZERO change to the live dispatched audience routing, ZERO change to the Stage 29.5.5 renderer / recorder / side-channel artifact writer source, and ZERO change to the Stage 29.3 default behavior when the injector kwarg is omitted.

## 3. Why a separate Stage 29.5.6 substage

Stage 29.5.5 wired the Stage 29.5 private migration context projection through a pure deterministic renderer plus a Stage 27.4 `MigrationContextSource` Protocol recording adapter and a Stage 29.5.5 side-channel artifact writer. The Stage 29.5.5 runbook deliberately deferred "injecting the Stage 29.5.5 rendered block into the live dispatched Discord body" — its Section 9 noted the deferral as a separately spec-locked decision. Stage 29.5.5 captured rendered blocks ONLY in a side-channel artifact file under the Stage 29.3 mode-3 `output_dir`; the live dispatched body remained the unchanged Stage 27.5 plain-text rendering plus the Stage 28.9 header.

Stage 29.5.6 unlocks exactly that one surface. The Stage 29.5.6 design preserves every other Stage 29.5.5 lock: the Stage 27.5 private ping renderer is unchanged, the Stage 28.4 audited HTTP transport is unchanged, the Stage 28.9 dispatch wrapper is unchanged, the Stage 28.2 / 28.6 dispatch ledger record shape is unchanged, the dispatched audience routing is unchanged, the Stage 28.9 dispatch counter axes are unchanged, the Stage 29.5.5 production source is unchanged byte-for-byte, the Stage 29.5.5 side-channel artifact write still happens exactly as before when a writer is wired as `migration_context_renderer`, and the Stage 29.3 default behavior (no `private_discord_body_injector` kwarg) is BYTE-EQUIVALENT to the Stage 29.5.5 default. The injector is consumed BY Stage 29.3 mode-3 at the operator's option only.

## 4. Data flow

```
operator builds a Stage 29.5.5 recorder with a renderer wired:
    recorder = Stage29_5_5MigrationContextRecorder(
        evidence_provider=...,
        ath_context_provider=...,
        clock=...,
        renderer=render_private_discord_migration_context_block,
    )

operator builds the Stage 29.5.6 injector with the recorder reference:
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

operator passes the recorder as migration_source AND the injector
as private_discord_body_injector to
    run_stage29_3_first_private_tradeable_smoke.

# ---- Stage 29.3 mode-3 path (per ceremony) ----

per Stage 27.6 candidate assembly (one call per assembled
candidate, max_dispatches=1):

    snapshot = recorder.read_migration_snapshot(token_mint)
    # Stage 29.5.5 recorder Phase 1 + Phase 2 unchanged at Stage 29.5.6;
    # Phase 2 (when renderer wired) appends one
    # Stage29_5_5RecordedRenderEntry to recorder._recorded_entries.

# After Stage 28.9 transport is constructed, before the Stage 28.9
# session runs, Stage 29.3 mode-3 conditionally wraps the transport
# (the wrap call is gated by both a try/except AND a conformance
# check on the returned candidate):

    if private_discord_body_injector is not None:
        try:
            candidate = private_discord_body_injector.wrap_transport(
                transport,
            )
            if callable(
                getattr(candidate, "send_one_audited_post", None),
            ):
                transport = candidate
            # Non-conforming candidate (None, bare object, or
            # object whose send_one_audited_post attribute is not
            # callable): keep the original Stage 28.9 transport.
        except Exception:
            # Wrap-time failure: fall back to the unwrapped Stage
            # 28.9 transport. The dispatched body is the unchanged
            # Stage 28.9 rendered body.
            pass

# ---- Stage 28.9 session runs ----

# Per dispatched candidate (max_dispatches=1):

    transport.send_one_audited_post(
        webhook_identity=..., payload={"content": <stage28_9_body>}
    )
    # Wrapper internals (try/except Exception: pass throughout):
    #   - duck-type recorder.recorded_entries
    #   - if empty / missing -> forward payload unchanged
    #   - else read last entry's rendered_block
    #   - re-validate via
    #     stage29_5_5_rendered_block_is_safe_for_serialization
    #   - if unsafe -> forward payload unchanged
    #   - Attempt 1 (full): compute
    #         full_combined_len = (
    #             len(payload["content"]) + 2
    #             + len(rendered_block.body_text)
    #         )
    #     - if full_combined_len <= STAGE29_5_6_CONTENT_MAX_CHARS
    #       (1900) -> build payload_copy = dict(payload);
    #       payload_copy["content"] = (
    #           payload["content"] + "\n\n"
    #           + rendered_block.body_text
    #       );
    #       inner_transport.send_one_audited_post(
    #           webhook_identity=..., payload=payload_copy
    #       )
    #   - Attempt 2 (compact fallback): build deterministic
    #     compact migration-context block from already-revalidated
    #     closed-set / display fields on the rendered block:
    #         [MIGRATION CONTEXT]
    #         status: <migration_evidence_status_display>
    #         evidence: <migration_evidence_source_trust_display>
    #         ath_context: <post_migration_ath_verified_display>
    #         filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING
    #         informational_only: true
    #         not_a_trading_verdict: true
    #     compact_combined_len = (
    #         len(payload["content"]) + 2 + len(compact_text)
    #     )
    #     - if compact_combined_len <= STAGE29_5_6_CONTENT_MAX_CHARS
    #       -> build payload_copy = dict(payload);
    #       payload_copy["content"] = (
    #           payload["content"] + "\n\n" + compact_text
    #       );
    #       inner_transport.send_one_audited_post(
    #           webhook_identity=..., payload=payload_copy
    #       )
    #   - Skip: else forward the original payload unchanged
    #     through the inner transport (NEVER truncate the
    #     rendered block, NEVER append a partial / invented
    #     block, NEVER append raw JSON)
    # On ANY failure on any of the steps above:
    #   - forward the ORIGINAL payload through the inner transport
    #   - never raise

# ---- end of Stage 28.9 session ----

# When migration_context_renderer is ALSO wired (Stage 29.5.5
# side-channel writer), Stage 29.3 mode-3 ALSO writes the Stage
# 29.5.5 side-channel artifact post-session (unchanged from Stage
# 29.5.5).

# ---- end of Stage 29.3 mode-3 ----

# default behavior (operator omits private_discord_body_injector
# kwarg):
#   - run_stage29_3_first_private_tradeable_smoke(...,
#       private_discord_body_injector=None)
#   - _run_mode_one_real_private_tradeable_ping_dry_run sees
#     private_discord_body_injector is None and skips the wrap
#     entirely. The Stage 29.3 mode-3 dispatched body is
#     BYTE-EQUIVALENT to the pre-Stage-29.5.6 code path.
```

The Stage 29.5.6 injector mutates only a copy of the operator-supplied payload dict; the original payload dict passed to the wrapper is never mutated. No raw JSON blob, no raw URL, no raw secret, no Discord-side webhook reference, no wallet / private-key field, no audience-routing field, and no trading verdict (BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE / POSITION-SIZE / AUTO-TRADE language) is ever added to the dispatched body by Stage 29.5.6; the Stage 29.5.5 closed-set forbidden-substring validator guards the rendered block at construction time and the Stage 29.5.6 injector re-runs the same validator immediately before every append as defense in depth.

## 5. Injector behavior matrix (closed-set)

### 5.1 No injector wired (default)

| `private_discord_body_injector` | `migration_source` | dispatched body |
|---|---|---|
| `None` (default) | any | unchanged Stage 28.9 body (BYTE-EQUIVALENT to pre-Stage-29.5.6) |

### 5.2 Injector wired, mode-3, recorder with at least one safe entry

The injector tries the full rendered `body_text` first; on overflow it falls back to a deterministic compact migration-context block built from already-revalidated closed-set / display fields on the rendered block. The append is skipped only when BOTH the full body_text AND the compact block would overflow the 1900-char combined cap. The injector never truncates a rendered field.

| `private_discord_body_injector` | `migration_source.recorded_entries` | combined budget | dispatched body |
|---|---|---|---|
| Stage 29.5.6 injector | non-empty + latest safe | full append ≤ 1900 chars | Stage 28.9 body + `\n\n` + full Stage 29.5.5 rendered `body_text` |
| Stage 29.5.6 injector | non-empty + latest safe | full > 1900 chars AND compact append ≤ 1900 chars | Stage 28.9 body + `\n\n` + compact migration-context block |
| Stage 29.5.6 injector | non-empty + latest safe | full > 1900 chars AND compact > 1900 chars | unchanged Stage 28.9 body (skip — never truncate) |
| Stage 29.5.6 injector | non-empty + latest UNSAFE (validator rejects) | n/a | unchanged Stage 28.9 body (skip) |
| Stage 29.5.6 injector | empty | n/a | unchanged Stage 28.9 body |
| Stage 29.5.6 injector | duck-type miss (no `recorded_entries` attr) | n/a | unchanged Stage 28.9 body |

### 5.3 Injector wired, non-mode-3

| Stage 29.3 mode | `private_discord_body_injector` | dispatched body |
|---|---|---|
| `READINESS_ONLY` (mode 1) | any | injector never invoked (mode 1 never builds the Stage 28.9 transport stack) |
| `CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY` (mode 2) | any | injector never invoked (mode 2 never builds the Stage 28.9 transport stack) |
| `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN` (mode 3) | non-None | wrap attempted per section 5.2 |

### 5.4 Failure paths

| Failure | Effect |
|---|---|
| Injector `wrap_transport` raises | Stage 29.3 catches; original Stage 28.9 transport used unchanged |
| Injector `wrap_transport` returns a non-conforming candidate (`None`, a bare object, or an object whose `send_one_audited_post` attribute is not callable) | Stage 29.3 rejects the candidate via the `callable(getattr(candidate, "send_one_audited_post", None))` gate; original Stage 28.9 transport used unchanged |
| Wrapper construction raises | Stage 29.3 catches; original Stage 28.9 transport used unchanged |
| Wrapper `send_one_audited_post` internal step raises (recorder read / validator / build copy / etc.) | Wrapper forwards original payload unchanged through inner transport |
| Inner transport raises | Exception propagates as on the unwrapped path (wrapper does NOT swallow inner-transport exceptions) |

## 6. Acceptance criteria

**A.** The injector module is pure / deterministic: same inputs always produce the same wrapped transport behavior; no env reads, no network, no file I/O at import or runtime.

**B.** `Stage29_5_6PrivateDiscordBodyInjector` accepts exactly one constructor argument (`migration_source: object`) and exposes exactly one method (`wrap_transport(inner_transport: object) -> object`) returning a wrapper that exposes `send_one_audited_post(*, webhook_identity, payload)`.

**C.** With `private_discord_body_injector=None` (default), the Stage 29.3 mode-3 dispatched payload bytes are BYTE-EQUIVALENT to the pre-Stage-29.5.6 code path. The Stage 28.9 counter axes and the smoke result outcome are unchanged.

**D.** With an injector wired AND a Stage 29.5.5 recorder carrying at least one safe recorded entry AND combined body within budget, the dispatched payload's `content` contains the unchanged Stage 28.9 body followed by exactly `"\n\n"` plus the latest rendered block's `body_text`. The Stage 28.9 dispatch counter axes are unchanged; the dispatched-Discord count is exactly one.

**E.** The injector re-validates the latest rendered block via `stage29_5_5_rendered_block_is_safe_for_serialization` immediately before each append. A block that fails the closed-set / pinned-value / forbidden-substring validator is dropped silently and the dispatched body is unchanged.

**F.** The combined body length is capped at `STAGE29_5_6_CONTENT_MAX_CHARS = 1900`. The injector attempts the full rendered `body_text` first; when the projected full-combined length exceeds the cap, the injector builds a deterministic compact migration-context block from already-revalidated closed-set / display fields on the rendered block (`migration_evidence_status_display`, `migration_evidence_source_trust_display`, `post_migration_ath_verified_display`, plus the pinned `filter_enforcement_status` / `informational_only` / `not_a_trading_verdict` safety tokens) and attempts to append the compact block; when the projected compact-combined length also exceeds the cap, the injector skips the append entirely. The injector NEVER truncates a rendered field, NEVER appends a partial / invented block, and NEVER appends raw JSON.

**G.** The injector mutates a COPY of the operator-supplied payload dict only. The original payload dict reference passed into `send_one_audited_post` is never mutated.

**H.** The injector swallows every internal exception (recorder read, validator, copy build, body assembly). On any internal failure the original payload is forwarded through the inner transport unchanged. The wrapper does NOT swallow exceptions raised by the inner transport itself.

**I.** Modes 1 (`READINESS_ONLY`) and 2 (`CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY`) never invoke the injector — neither mode constructs the Stage 28.9 transport stack.

**J.** Stage 29.3 production source carries NO `stage29_5*` import. The new kwarg's static type is `Optional[object]`. The Stage 29.3 mode-3 path performs the `wrap_transport(...)` call via duck typing only.

**K.** Stage 29.4 production source is untouched at Stage 29.5.6; the Stage 29.4 soak orchestrator continues to import zero `stage29_5*` modules.

**L.** Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 / Stage 29.5.4 / Stage 29.5.5 production source is untouched at Stage 29.5.6; every Stage 29.5.x manifest production-inventory tuple is unchanged byte-for-byte.

**M.** Stage 27 + Stage 28 production source is untouched at Stage 29.5.6; the Stage 27.5 private ping renderer, the Stage 28.4 audited HTTP transport, the Stage 28.6 bounded runner, the Stage 28.9 dispatch wrapper, and the Stage 28.2 dispatch ledger are unchanged.

**N.** The Stage 29.5.6 production source reads zero env names. The Stage 29.5.6 production source imports zero outbound-network libraries (no `urllib`, no `requests`, no `httpx`, no `aiohttp`, no `websockets`, no `websocket`, no `http.client`, no `socket`, no `grpc`, no `asyncio`). The Stage 29.5.6 boundary scan pins the admission tuple at empty.

**O.** No public / subscriber / paid-tier routing. No Stage 26 enforcement activation. No Telegram / X / social sender. No automated trading / position sizing / trade execution. No wallet / private-key / signer surface. No live Helius WS / Chainstack gRPC / Birdeye HTTP / Discord call from Stage 29.5.6 production or test source.

**P.** No duplicate dispatch occurs: with `max_dispatches=1`, the Stage 29.3 mode-3 ceremony makes at most one Discord call regardless of whether the Stage 29.5.6 injector is wired. The Stage 28.9 dispatch ledger semantics are unchanged. The dispatched body's `content` is the only field the injector touches; the injector adds no other top-level payload key and removes no existing top-level payload key.

**Q.** The dispatched body content carries NO raw URL host literal, NO raw API-key shape, NO raw webhook URL, NO bearer-token-shaped or authorization-header-shaped substring, NO raw Helius / Chainstack / Birdeye payload, NO wallet / private-key / signer field, NO pre-PHX2 / legacy import reference, NO trading verdict language (BUY / SELL / APPROVED / GATE / BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE / AUTO-TRADE), and NO raw JSON blob in the appended migration context block. The Stage 29.5.5 rendered-block forbidden-substring scan covers every string field that reaches the dispatched body via the injector.

**R.** Stage 29.5.6 ships the canonical mission sentence verbatim in Section 1 and pins every acceptance criterion letter A–R in this runbook. The Stage 29.5.6 boundary scan pins the canonical mission sentence and the locked schema version verbatim.

## 7. Forbidden surfaces (Stage 29.5.6)

Stage 29.5.6 unlocks exactly one Stage 29.5.5 forbidden surface: **"injecting rendered block into live dispatched Discord body"** (the unlocked surface is the Stage 29.5.6 transport-wrapper injector path, gated mode-3-only and opt-in only).

Every other Stage 29.5.5 forbidden surface remains pinned at Stage 29.5.6. The Stage 29.5.6 manifest tuple `STAGE29_5_6_FORBIDDEN_SURFACES` is the canonical list; the Stage 29.5.6 manifest test asserts the tuple shape verbatim. Additional Stage 29.5.6 forbidden-surface pins:

- **Stage 27.5 private ping renderer modification** — Stage 29.5.6 ships ZERO change to the Stage 27 plain-text rendered ping.
- **Stage 28.4 audited HTTP transport modification** — Stage 29.5.6 ships ZERO change to the Stage 28.4 transport; the injector wraps but never replaces the audited transport.
- **Stage 28.6 bounded runner modification** — Stage 29.5.6 ships ZERO change to the Stage 28.6 candidate-stream runner.
- **Stage 28.9 dispatch wrapper modification** — Stage 29.5.6 ships ZERO change to the Stage 28.9 `Stage28_9PrivateWebhookTransport`; the injector wraps it externally from the Stage 29.3 mode-3 path.
- **Stage 28.9 dispatch ledger record shape change** — the dispatched-Discord ledger record continues to carry the unchanged Stage 28.9 dispatch counter axes.
- **Stage 28.9 dispatch counter axes change** — the injector mutates only the dispatched payload `content` field, never the Stage 28.9 outcome / counters / refusal reason.
- **live dispatched audience change** — the dispatched audience routing is unchanged (PRIVATE_OPERATOR only).
- **raw JSON blob in dispatched body** — only the Stage 29.5.5 closed-set rendered `body_text` is appended; never the projection_summary / snapshot_summary JSON.
- **raw payload bytes in dispatched body** — the injector never copies upstream provider bytes onto the dispatched body.
- **raw URL host / raw API key / raw webhook URL in dispatched body** — the Stage 29.5.5 forbidden-substring scanner gates every appended string.
- **Stage 29.5.5 renderer source modification** — the Stage 29.5.5 pure renderer is consumed read-only.
- **Stage 29.5.5 recorder source modification** — the Stage 29.5.5 recorder is consumed read-only via the duck-typed `recorded_entries` property.
- **Stage 29.5.5 side-channel writer source modification** — the Stage 29.5.5 writer is unchanged; Stage 29.5.6 ships a separate injector class and never edits the writer.
- **Stage 29.5.5 manifest inventory change** — the Stage 29.5.5 manifest production-inventory tuple is locked at Stage 29.5.5 and survives Stage 29.5.6 byte-for-byte.
- **Stage 29.3 default behavior change** — when `private_discord_body_injector` is omitted (or explicitly None), Stage 29.3 mode-3 dispatched bytes are BYTE-EQUIVALENT to the pre-Stage-29.5.6 code path.
- **Stage 29.6+ implementation** — Stage 29.6 and beyond remain blocked until separately spec-locked.

## 8. Files added at Stage 29.5.6

**Production (new):**

- `PHX2/stage29/stage29_5_6_private_ping_migration_context_injector.py`
- `PHX2/stage29/stage29_5_6_manifest.py`

**Doc (new):**

- `PHX2/stage29/STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md` (this file)

**Production (edited):**

- `PHX2/stage29/stage29_3_tradeable_smoke.py` — adds optional `private_discord_body_injector: Optional[object] = None` kwarg on `run_stage29_3_first_private_tradeable_smoke` (keyword-only); threads one layer into `_run_mode_one_real_private_tradeable_ping_dry_run`; after `Stage28_9PrivateWebhookTransport` is built and before `run_stage28_9_live_provider_session` is called, conditionally wraps the transport via `private_discord_body_injector.wrap_transport(transport)` inside a `try` / `except Exception: pass` guard AND a `callable(getattr(candidate, "send_one_audited_post", None))` conformance gate. The candidate replaces the original transport only when both the call did not raise AND the candidate exposes a callable `send_one_audited_post` attribute; a non-conforming candidate preserves the original transport. Default behavior (`private_discord_body_injector=None`) is byte-equivalent to the pre-Stage-29.5.6 code path. No other change to Stage 29.3 production source.

**Tests (new):**

- `PHX2/tests/stage29/test_stage_29_5_6_private_ping_migration_context.py`
- `PHX2/tests/stage29/test_stage_29_5_6_boundaries.py`
- `PHX2/tests/stage29/test_stage_29_5_6_manifest.py`
- `PHX2/tests/stage29/test_stage_29_5_6_spec_lock.py`

**Tests (narrow allowlist widenings, test-files-only):**

- `PHX2/tests/stage29/test_stage_29_0_spec_lock.py` — add Stage 29.5.6 production + test allowlist frozensets; union into the existing cumulative production + test unions; extend the `test_no_python_module_under_stage29_beyond_init` allowed-py union.

## 9. Deferred after Stage 29.5.6

- **Stage 29.6+ implementation** — pinned absent in the Stage 29.5.6 forbidden-surface tuple. Stage 29.6 (bounded private live/soak proof with migration context visible in the private ping body) requires separate operator authorization.
- **Public / subscriber / paid-tier injection of the migration context** — permanently forbidden under the Stage 29.5 spec lock's no-public-routing / no-subscriber-routing / no-paid-tier-routing pins.
- **Trading verdict language in the dispatched body** — permanently forbidden.
- **Live Helius WebSocket migration-evidence ingestion** — deferred (the Stage 29.5 Helius WS adapter is the upstream layer the operator wires into the Stage 29.5.5 recorder's `evidence_provider` callable; today operators may pass an in-memory list or a Stage 29.5 artifact reader's output).
- **Stage 29.3 default flip from `NoMigrationEvidence` to a real source** — deferred indefinitely. The `migration_source` kwarg + the `migration_context_renderer` kwarg + the new `private_discord_body_injector` kwarg all stay default-`None` forever; flipping any default is a separately spec-locked decision.
- **Stage 29.4 soak orchestrator auto-wires the Stage 29.5.6 injector** — deferred. The soak orchestrator's pass-entrypoint contract is unchanged at Stage 29.5.6; operators may pass the Stage 29.5.6 injector into the Stage 29.5.3 wrapper's inner-pass-entrypoint closure or directly into `run_stage29_3_first_private_tradeable_smoke`.
- **Pump.fun bonding-curve decoder, Dexscreener-as-dispatch-authority, Helius-as-price-source, additional providers** — all deferred.
- **Legacy / pre-PHX2 import path** — permanently forbidden.

## 10. Operator runbook (minimal)

To exercise the Stage 29.5.6 opt-in injector in a controlled offline test:

```
from PHX2.stage29.stage29_3_tradeable_smoke import (
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    Stage29_5_6PrivateDiscordBodyInjector,
)

def evidence_provider(token_mint):
    return [...]  # Stage 29.5 migration evidence records

def ath_context_provider(token_mint):
    return ...   # optional Stage 27.4 AthContextRecord or None

recorder = Stage29_5_5MigrationContextRecorder(
    evidence_provider=evidence_provider,
    ath_context_provider=ath_context_provider,
    clock=lambda: "2026-01-01T00:00:00+00:00",
    renderer=render_private_discord_migration_context_block,
)

injector = Stage29_5_6PrivateDiscordBodyInjector(
    migration_source=recorder,
)

result = run_stage29_3_first_private_tradeable_smoke(
    mode=...,
    runtime_configs=...,
    private_webhook_url=...,
    output_dir=...,
    live_env_ready=...,
    live_operator_request=...,
    migration_source=recorder,
    private_discord_body_injector=injector,  # <-- Stage 29.5.6 opt-in
)
```

Omitting the `private_discord_body_injector` kwarg restores the default behavior byte-equivalently (no migration context appended to the dispatched body). Passing an injector without wiring a Stage 29.5.5 recorder as `migration_source` causes the injector to silently no-op (no `recorded_entries` to read) and the dispatched body is unchanged.

## 11. Stage 29.5.6 schema versions

`stage29_5_6_v0_private_discord_body_injector` — the Stage 29.5.6 injector module's schema version pin. Re-exported through the Stage 29.5.6 manifest module for cross-checks.
