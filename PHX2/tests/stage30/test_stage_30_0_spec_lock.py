"""Stage 30.0 spec-lock pins.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.0
contract via direct filesystem inspection of the four-file
inventory and substring / regex matches against the spec-lock
markdown.

Pinned contract:

  * ``PHX2/stage30/`` and ``PHX2/tests/stage30/`` package dirs
    exist and carry the expected package markers.
  * ``PHX2/stage30/STAGE_30_SPEC_LOCK.md`` exists.
  * The Stage 30.0 inventory under ``PHX2/stage30/`` is exactly
    ``__init__.py`` + ``STAGE_30_SPEC_LOCK.md`` (no production
    ``.py``, no extra markdown).
  * The Stage 30.0 inventory under ``PHX2/tests/stage30/`` is
    exactly ``__init__.py`` + ``test_stage_30_0_spec_lock.py``.
  * The spec-lock markdown contains the ten required section
    headings.
  * The spec-lock markdown declares the exact tier bands
    (0.50-0.60 / 0.62-0.80 / 0.82-0.95) with the intentional
    gaps.
  * The spec-lock markdown declares the preferred drawdown
    formula ``drawdown_from_ath = (current_mc - ath_mc) / ath_mc``.
  * The spec-lock markdown explicitly says Stage 30 NEVER
    fabricates MC, supply, ATH MC, or current MC.
  * The spec-lock markdown explicitly says missing MC / LP / Vol
    values render as the literal ``Unknown`` (not ``0``).
  * The spec-lock markdown declares the hard forbidden scope
    (no public routing, no paid/subscriber routing, no
    enforcement, no automated trading, no wallet/signing, no
    Telegram, no X/social, no Stage 31).
  * The spec-lock markdown pins that Stage 30.0 is spec lock
    only.
  * The spec-lock markdown pins that live Discord / provider
    calls require separate explicit operator authorization.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / "STAGE_30_SPEC_LOCK.md"


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 30 package + tests package + spec lock file exist
# ---------------------------------------------------------------------------


def test_stage30_package_dir_exists() -> None:
    assert STAGE30_ROOT.is_dir(), (
        f"Stage 30.0 requires the package dir {STAGE30_ROOT}"
    )


def test_stage30_tests_package_dir_exists() -> None:
    assert TESTS_STAGE30_ROOT.is_dir(), (
        f"Stage 30.0 requires the tests package dir "
        f"{TESTS_STAGE30_ROOT}"
    )


def test_stage30_package_init_exists() -> None:
    init_path = STAGE30_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 30.0 requires the package marker {init_path}"
    )


def test_stage30_tests_package_init_exists() -> None:
    init_path = TESTS_STAGE30_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 30.0 requires the tests package marker "
        f"{init_path}"
    )


def test_stage30_spec_lock_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Stage 30.0 inventory is exactly four files (no production .py beyond
#    the package marker, no extra markdown, no orphaned test).
# ---------------------------------------------------------------------------


_STAGE30_ALLOWED_BASENAMES: frozenset = frozenset(
    {
        "__init__.py",
        "STAGE_30_SPEC_LOCK.md",
        # Stage 30.1 production additions.
        "tier_decision_models.py",
        "tier_decision_projector.py",
        "tier_decision_artifact_writer.py",
        "stage30_1_manifest.py",
        # Stage 30.2 production additions.
        "compact_ping_models.py",
        "compact_ping_renderer.py",
        "compact_ping_artifact_writer.py",
        "stage30_2_manifest.py",
        # Stage 30.3A production additions.
        "stage30_3_compact_runtime_models.py",
        "stage30_3_compact_candidate_projection.py",
        "stage30_3_compact_candidate_context_recorder.py",
        "stage30_3_compact_body_transport_wrapper.py",
        "stage30_3_runtime_wiring_artifact_writer.py",
        "stage30_3_manifest.py",
        # Stage 30.3B production additions.
        "stage30_3_compact_runtime_session_orchestrator.py",
        # Stage 30.3D proof record (sanitized documentation only).
        "STAGE_30_3D_COMPACT_PRIVATE_LIVE_PROOF.md",
        # Stage 30.4.0 spec lock + manifest (spec-lock only; no
        # production code beyond the manifest at Stage 30.4.0).
        "STAGE_30_4_SPEC_LOCK.md",
        "stage30_4_manifest.py",
        # Stage 30.4.1 offline production additions: models,
        # formatter, source protocol, adapter, artifact writer.
        "stage30_4_compact_market_context_models.py",
        "stage30_4_compact_market_context_formatter.py",
        "stage30_4_compact_market_context_source_protocol.py",
        "stage30_4_compact_market_context_adapter.py",
        "stage30_4_compact_market_context_artifact_writer.py",
        # Stage 30.4.2 opt-in parallel compact runtime session
        # orchestrator (offline / fake-source only; no live Birdeye
        # token_overview adapter ships in Stage 30.4.2).
        "stage30_4_compact_runtime_session_orchestrator.py",
        # Stage 30.4.3 offline Birdeye token-overview market-context
        # source bridge (maps a Stage 29.2 snapshot onto a Stage
        # 30.4.1 reading; offline / fake-transport in tests).
        "stage30_4_3_market_context_birdeye_source.py",
        # Stage 30.4.4 sanitized private-live proof record
        # (documentation only; records the out-of-repo Stage
        # 30.4.3C / 30.4.3D / 30.4.3E proofs).
        "STAGE_30_4_4_MC_LP_PRIVATE_LIVE_PROOF.md",
        # Stage 30.5.0 migration-context spec lock (spec-lock /
        # handoff doc only; zero production code at Stage 30.5.0).
        "STAGE_30_5_0_MIGRATION_CONTEXT_SPEC_LOCK.md",
        # Stage 30.5.1 offline migration-context production additions:
        # models, source protocol, adapter, manifest (fakes only; no
        # renderer / runtime / bridge / live / Discord change).
        "stage30_5_migration_context_models.py",
        "stage30_5_migration_context_source_protocol.py",
        "stage30_5_migration_context_adapter.py",
        "stage30_5_manifest.py",
        # Stage 30.5.2 opt-in offline compact migration runtime adapter:
        # the duck-typed resolver that wires the Stage 30.5.1 migration
        # projection into the existing Stage 30.4.2 compact runtime
        # replacement path (no renderer change; the Stage 30.4.2
        # orchestrator gains one optional duck-typed resolver param).
        "stage30_5_compact_migration_runtime_adapter.py",
        # Stage 30.5.3 offline Stage 29.5 migration-evidence bridge:
        # converts a sanitized Stage 29.5 migration-evidence summary into
        # the Stage 30.5 record / projection / resolver contract (imports
        # no Stage 29 module; reuses the Stage 30.5.1 models + Stage 30.5.2
        # resolver; no renderer / orchestrator edit; no ATH / Net / live).
        "stage30_5_stage29_migration_bridge.py",
        # Stage 30.6.0 storage + dedupe spec lock + manifest
        # (spec-lock only; the spec doc plus a constants-only
        # manifest. ZERO storage writer, ZERO dedupe engine, ZERO
        # budget evaluator, ZERO lifecycle-seal aggregate, ZERO
        # database migration, ZERO filesystem writer, ZERO zstd
        # dependency, ZERO live / Discord / ATH; no Stage 30.6.1+
        # implementation file ships at Stage 30.6.0).
        "STAGE_30_6_0_STORAGE_DEDUPE_SPEC_LOCK.md",
        "stage30_6_manifest.py",
        # Stage 30.6.1 storage budget models + pure policy evaluator
        # (offline policy brain only; no storage writer / dedupe
        # ledger / WAL writer / database migration / zstd / live /
        # Discord / ATH; reads no actual disk).
        "stage30_6_storage_budget_models.py",
        "stage30_6_storage_budget_evaluator.py",
        # Stage 30.7.0 ATH context bridge spec lock + manifest
        # (spec-lock only; the spec doc plus a constants-only
        # manifest. ZERO ATH bridge code, ZERO ATH models, ZERO
        # projection adapter, ZERO source bridge, ZERO renderer /
        # runtime change, ZERO live / Discord / provider / DB /
        # filesystem writer / compression / filters / enforcement;
        # no Stage 30.7.1+ implementation file ships at Stage 30.7.0).
        "STAGE_30_7_0_ATH_CONTEXT_SPEC_LOCK.md",
        "stage30_7_manifest.py",
        # Stage 30.7.1 offline ATH context production additions: models
        # + pure projection adapter (fakes only; no renderer / runtime /
        # source bridge / live / Discord / provider change, no drawdown /
        # tier recomputation). No Stage 30.7.3+ implementation file.
        "stage30_7_ath_context_models.py",
        "stage30_7_ath_context_projection.py",
        # Stage 30.7.2 opt-in offline compact ATH runtime adapter: the
        # duck-typed resolver + projection-to-text converter that wires
        # the Stage 30.7.1 ATH projection into the existing Stage 30.4.2
        # compact runtime replacement path through the existing
        # ``ath_mc_text`` slot (no renderer / models change; the Stage
        # 30.4.2 orchestrator gains one optional duck-typed resolver
        # param; no live / Discord / provider / DB / filesystem writer /
        # compression / drawdown / tier / ATH source bridge change).
        "stage30_7_compact_ath_runtime_adapter.py",
        # Stage 30.7.3 offline sanitized upstream ATH-evidence bridge:
        # normalizes a sanitized Stage 25 / 27.4 / 29.2-style scalar ATH
        # shape into the Stage 30.7.1 evidence carrier and reuses the
        # Stage 30.7.1 projection + Stage 30.7.2 compact adapter / resolver
        # to produce the compact ``ATH`` text (imports no Stage 25/27/28/29
        # module; reuses the Stage 30.7.2 ``ath_context_resolver`` seam with
        # no orchestrator edit; no renderer / models change; no live /
        # Discord / provider / DB / filesystem writer / compression /
        # drawdown / tier change).
        "stage30_7_sanitized_ath_bridge.py",
        # Stage 30.7.4 ATH context bridge closure audit + handoff
        # (closure docs + a constants-only manifest only; ZERO runtime
        # production code, ZERO renderer / compact models / orchestrator
        # edit, ZERO live / provider / Discord / env / DB / filesystem
        # writer / zstd / drawdown / tier / enforcement change; no Stage
        # 30.7.5+ file).
        "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md",
        "STAGE_30_7_ATH_CONTEXT_HANDOFF.md",
        "stage30_7_4_manifest.py",
        # Stage 30.8.0 compact session artifact / storage-readiness spec
        # lock + manifest (spec-lock only; the spec doc plus a
        # constants-only manifest. ZERO storage writer, ZERO database,
        # ZERO SQLite, ZERO filesystem artifact writer, ZERO zstd
        # dependency, ZERO day-rolling, ZERO live / Discord / provider /
        # env, ZERO enforcement / public routing / trading / wallet /
        # social, ZERO drawdown / tier recomputation, ZERO renderer /
        # compact models / orchestrator / Stage 30.7 file edit; no Stage
        # 30.8.1+ implementation file ships at Stage 30.8.0).
        "STAGE_30_8_0_COMPACT_SESSION_STORAGE_SPEC_LOCK.md",
        "stage30_8_manifest.py",
        # Stage 30.8.1 pure compact artifact models + validators
        # (passive frozen records + deterministic validators only; NO
        # writer, NO database / SQLite / filesystem artifact writer, NO
        # zstd / compression, NO dedupe / session index, NO live /
        # Discord / provider / env, NO renderer / compact models /
        # orchestrator / Stage 30.7 file edit; the models import no PHX2
        # module and the validators import only the models sibling; no
        # Stage 30.8.2+ implementation file ships at Stage 30.8.1).
        "stage30_8_artifact_models.py",
        "stage30_8_artifact_validators.py",
        # Stage 30.8.2 temp-dir compact session artifact writer (a small,
        # fail-closed, stdlib-only writer that persists a caller-assembled
        # bundle of validated Stage 30.8.1 artifacts to a caller-PROVIDED
        # output dir, used against temp dirs only in tests; NO database,
        # NO SQLite, NO zstd / compression, NO dedupe / session index, NO
        # append-only log, NO live / Discord / provider / env, NO real bot
        # artifact directory, NO renderer / compact models / orchestrator /
        # Stage 30.7 edit; it imports only stdlib plus the Stage 30.8.1
        # models + validators siblings; no Stage 30.8.3+ file ships at
        # Stage 30.8.2).
        "stage30_8_temp_artifact_writer.py",
        # Stage 30.8.2 temp-dir artifact writer closure audit (closure /
        # handoff doc only; ZERO production code, ZERO manifest change,
        # ZERO writer behavior change, ZERO renderer / compact models /
        # orchestrator / Stage 30.7 edit; no Stage 30.8.3 file).
        "STAGE_30_8_2_TEMP_ARTIFACT_WRITER_CLOSURE_AUDIT.md",
        # Stage 30.8.3 offline compact session index / dedupe slice
        # (passive index models + a fail-closed manifest-backed bundle
        # reader + a pure in-memory index / dedupe builder, proven against
        # temp dirs only; NO database, NO SQLite, NO zstd / compression, NO
        # index artifact write, NO live / Discord / provider / env, NO real
        # bot artifact directory, NO default storage root, NO renderer /
        # compact models / orchestrator / Stage 30.7 edit; the models +
        # reader import no PHX2 module and the builder imports only the
        # Stage 30.8.3 reader + index-models siblings plus the Stage 30.8.1
        # artifact-models sibling; no Stage 30.8.4+ file ships at Stage
        # 30.8.3).
        "stage30_8_session_index_models.py",
        "stage30_8_session_bundle_reader.py",
        "stage30_8_session_index_builder.py",
        # Stage 30.8.4 controlled compact session artifact proof slice
        # (a passive proof models module -- scenario + summary records +
        # closed-set tokens, imports no PHX2 module -- plus a fail-closed
        # proof runner that COMPOSES the Stage 30.8.1 models + Stage 30.8.2
        # writer + Stage 30.8.3 reader / index builder over caller-provided
        # temp dirs only; NO runtime integration, NO live provider run, NO
        # Discord send, NO real bot storage root, NO default storage /
        # proof-summary path, NO database / SQLite / zstd / compression, NO
        # env read, NO renderer / compact models / orchestrator / Stage
        # 30.7 / Stage 30.8.1-3 production edit; the runner writes nothing
        # of its own and the summary is in-memory; no Stage 30.8.5+ / Stage
        # 30.9 file ships at Stage 30.8.4).
        "stage30_8_controlled_artifact_proof_models.py",
        "stage30_8_controlled_artifact_proof.py",
        # Stage 30.9.0 bounded private live compact session bridge spec
        # lock + manifest (spec-lock only; the spec doc plus a
        # constants-only manifest. ZERO runtime code, ZERO artifact
        # bridge, ZERO capture transport, ZERO post-session projector,
        # ZERO Stage 30.8 writer / reader / index invocation, ZERO new
        # live runner / readiness gate, ZERO live / Discord / provider /
        # env, ZERO database / SQLite / zstd / compression, ZERO default
        # storage root / background daemon, ZERO public / subscriber /
        # paid routing, ZERO Telegram / X / social, ZERO trading / wallet /
        # signing, ZERO enforcement, ZERO Stage 31, ZERO edit to any
        # existing live runner / orchestrator / transport / Stage 30.8
        # implementation file; no Stage 30.9.1+ implementation file ships
        # at Stage 30.9.0).
        "STAGE_30_9_0_BOUNDED_PRIVATE_LIVE_COMPACT_SPEC_LOCK.md",
        "stage30_9_manifest.py",
        # Stage 30.9.1 offline artifact bridge production additions: the
        # passive bridge models, the thin innermost capture transport, the
        # post-session projector, and the offline write -> read -> index
        # proof helper. Fakes / offline only; NO live runner, NO new
        # readiness gate, NO live provider call, NO Discord send, NO env
        # read, NO database / SQLite / zstd / compression, NO default
        # storage root, NO per-ping write, NO edit to any existing live
        # runner / orchestrator / transport / Stage 30.8 implementation
        # file. The capture transport / projector / proof carry NO Stage 28
        # import (the dispatch context is a passive Stage 30.9.1 carrier);
        # the projector / proof reuse the Stage 30.8.1 models + Stage 30.8.2
        # writer + Stage 30.8.3 reader / index builder. No Stage 30.9.2+
        # file ships at Stage 30.9.1.
        "stage30_9_artifact_bridge_models.py",
        "stage30_9_capture_transport.py",
        "stage30_9_artifact_projector.py",
        "stage30_9_artifact_bridge_proof.py",
        # Stage 30.10.0 compact tier-dip eligibility gate spec lock +
        # manifest (spec-lock only; the spec doc plus a constants-only
        # manifest. ZERO runtime code, ZERO eligibility classifier, ZERO
        # audit-record model, ZERO runtime wiring, ZERO artifact
        # integration, ZERO new live runner / provider / readiness gate,
        # ZERO direct Stage 28 suppression-logic edit, ZERO live / Discord /
        # provider / env, ZERO database / SQLite / zstd / compression, ZERO
        # default storage root / background daemon, ZERO public / subscriber
        # / paid routing, ZERO Telegram / X / social, ZERO trading / wallet /
        # signing, ZERO enforcement, ZERO Stage 31; no Stage 30.10.1+
        # implementation file ships at Stage 30.10.0).
        "STAGE_30_10_0_COMPACT_TIER_DIP_ELIGIBILITY_SPEC_LOCK.md",
        "stage30_10_manifest.py",
        # Stage 30.10.1 fake / offline eligibility model + classifier
        # production additions (a pure tier-dip classifier + per-candidate
        # audit-record model, proven with fakes only; ZERO runtime wiring,
        # ZERO live provider call, ZERO Discord send, ZERO env read, ZERO
        # database / SQLite / zstd / compression, ZERO default storage root,
        # ZERO Stage 28 suppression / Stage 30.3 / Stage 30.4 orchestrator
        # edit; no Stage 30.10.2+ implementation file ships at Stage 30.10.1).
        "stage30_10_1_tier_dip_eligibility_models.py",
        "stage30_10_1_tier_dip_eligibility_classifier.py",
        # Stage 30.10.2 optional fake / offline pre-dispatch tier-dip gate
        # production additions (the gate models, the gate that wraps the
        # Stage 30.10.1 classifier and is evaluated BEFORE dispatch
        # reservation, and the offline fake-gate proof; ZERO runtime wiring,
        # ZERO live provider call, ZERO Discord send, ZERO env read, ZERO
        # transport-layer veto / PAYLOAD_REFUSED for a normal non-dip skip,
        # ZERO database / SQLite / zstd / compression, ZERO default storage
        # root, ZERO Stage 28 suppression / Stage 30.3 / Stage 30.4
        # orchestrator edit; no Stage 30.10.3+ implementation file ships at
        # Stage 30.10.2).
        "stage30_10_2_pre_dispatch_gate_models.py",
        "stage30_10_2_pre_dispatch_gate.py",
        "stage30_10_2_fake_gate_proof.py",
        # Stage 30.10.3 offline gate artifact integration proof production
        # additions (the passive gate artifact models -- per-candidate record
        # + rolled-up batch + in-memory sink result, importing no PHX2 module
        # -- the pure projector that maps a Stage 30.10.2 gate record onto an
        # artifact record / batch, and the fake / offline proof that composes
        # the Stage 30.10.2 fake gate scenario -> the real gate -> the
        # projector -> an explicitly in-memory artifact sink; ZERO runtime
        # wiring, ZERO live provider call, ZERO Discord send, ZERO env read,
        # ZERO filesystem write, ZERO transport-layer gate / PAYLOAD_REFUSED
        # for a normal non-dip skip, ZERO database / SQLite / zstd /
        # compression, ZERO default storage root, ZERO Stage 28 suppression /
        # Stage 30.3 / Stage 30.4 orchestrator edit; no Stage 30.10.4+
        # implementation file ships at Stage 30.10.3).
        "stage30_10_3_gate_artifact_models.py",
        "stage30_10_3_gate_artifact_projector.py",
        "stage30_10_3_fake_artifact_proof.py",
        # Stage 30.9.2_RESUME dip-filtered live proof planning / fake-proof
        # production additions (the passive resume models -- dip-filtered
        # resume plan + per-candidate proof record + resume proof summary,
        # importing no PHX2 module -- the pure plan builder that holds every
        # live-affecting axis closed, and the fake / offline proof that
        # composes the committed Stage 30.10.2 fake gate scenario -> the real
        # gate -> the Stage 30.10.3 projector -> the Stage 30.9.2 resume
        # records + summary; ZERO live run, ZERO live provider call, ZERO
        # Discord send, ZERO env read, ZERO real provider key use, ZERO real
        # provider session, ZERO dispatch reservation, ZERO filesystem write,
        # ZERO transport-layer gate / PAYLOAD_REFUSED for a normal non-dip
        # skip, ZERO database / SQLite / zstd / compression, ZERO default
        # storage root, ZERO runtime orchestrator wiring, ZERO Stage 28
        # suppression / Stage 30.3 / Stage 30.4 orchestrator edit; the actual
        # dip-filtered live ceremony remains a separate, explicitly
        # operator-authorized step and no Stage 30.9.3+ / Stage 30.10.4 file
        # ships at Stage 30.9.2).
        "stage30_9_2_resume_dip_filtered_live_models.py",
        "stage30_9_2_resume_dip_filtered_live_plan.py",
        "stage30_9_2_resume_fake_proof.py",
        # Stage 30.9.3 dip-filtered live dispatch integration seam production
        # additions (the passive integration models -- assembled live-candidate
        # input + per-candidate live gate decision + rolled-up integration
        # result, importing no PHX2 module -- the pure adapter that builds the
        # Stage 30.10.1 eligibility input from existing live context fields and
        # runs the committed Stage 30.10 gate stack, the bounded orchestrator
        # that drives the adapter over a candidate stream with an injected
        # dispatch sink + caps, and a fake / offline integration proof with
        # deterministic fake streams + an in-memory recording sink; the REAL
        # seam the later operator-authorized live ceremony reuses, but ZERO
        # live run / provider call / Discord send / env read / real transport
        # dispatch reservation ships here; no Stage 30.9.4 / Stage 30.10.4
        # file).
        "stage30_9_3_dip_filtered_live_gate_models.py",
        "stage30_9_3_dip_filtered_live_gate_adapter.py",
        "stage30_9_3_dip_filtered_live_gate_orchestrator.py",
        "stage30_9_3_fake_live_gate_integration_proof.py",
        # Stage 30.11.0 dip-gated live dispatch wiring spec-lock additions
        # (the spec-lock markdown + the constants-only manifest). Spec lock /
        # tests only; ZERO runtime / assembly bridge / runtime gate seam /
        # real dispatch sink / live run / Discord send / env read; no Stage
        # 30.11.1+ file ships at Stage 30.11.0.
        "STAGE_30_11_0_DIP_GATED_LIVE_DISPATCH_WIRING_SPEC_LOCK.md",
        "stage30_11_manifest.py",
        # Stage 30.11.1 offline live-candidate -> Stage30_9_3LiveGateInput
        # assembly bridge production additions (the passive bridge models --
        # the Stage 30.11-owned already-assembled live candidate snapshot + the
        # per-candidate bridge result carrying the committed Stage 30.9.3 live
        # gate input + the rolled-up proof summary, embedding only that ONE
        # committed Stage 30.9.3 model -- the pure bridge that maps an already-
        # assembled snapshot's present fields one-to-one onto a committed Stage
        # 30.9.3 Stage30_9_3LiveGateInput, and the fake / offline bridge proof
        # that tallies the bridge over a deterministic five-candidate stream and
        # OPTIONALLY feeds the bridged inputs into the committed Stage 30.9.3
        # gate to prove compatibility; the missing assembly link the prior
        # controlled live ceremony lacked, but ZERO runtime wiring / runtime
        # gate seam / real dispatch sink / dispatch reservation / live run /
        # provider call / Discord send / env read ships here, and NO Stage 28 /
        # 29 / existing Stage 30 production file is edited; no Stage 30.11.2+
        # file ships at Stage 30.11.1.
        "stage30_11_1_live_candidate_bridge_models.py",
        "stage30_11_1_live_candidate_bridge.py",
        "stage30_11_1_fake_bridge_proof.py",
        # Stage 30.11.2 offline runtime gate seam production additions (the
        # passive runtime models -- bounded-runtime config + per-candidate
        # runtime outcome + rolled-up runtime summary + fake dispatch
        # acknowledgement result + closed-set runtime decision / reason
        # vocabularies, importing no PHX2 module -- the pure runtime seam that
        # composes the committed Stage 30.11.1 bridge -> the committed Stage
        # 30.9.3 dip gate -> an INJECTED fake dispatch sink reachable ONLY behind
        # a gate PASS, enforcing the wall-clock max_runtime_seconds bound via an
        # injected clock plus the max_candidates / max_dispatches count bounds,
        # and the offline fake runtime gate proof composing the seam over a
        # deterministic five-candidate stream with an in-memory recording sink +
        # an injected fake clock; the runtime counterpart of the Stage 30.11.1
        # bridge proof, but ZERO real dispatch sink / real Discord / transport
        # wiring / dispatch reservation / live run / provider call / Discord
        # send / env read / wall-clock read / daemon ships here, and NO Stage 28
        # / 29 / existing Stage 30 production file is edited; no Stage 30.11.3+
        # file ships at Stage 30.11.2.
        "stage30_11_2_runtime_gate_models.py",
        "stage30_11_2_runtime_gate_seam.py",
        "stage30_11_2_fake_runtime_gate_proof.py",
        # Stage 30.11.3 private sink adapter production additions (private sink
        # models, private sink adapter, fake private sink proof): the
        # adapter-side private sink request / result / proof-summary models, the
        # pure adapter that translates a committed PASS gate input into a private
        # sink request and hands it to an INJECTED fake transport (plus a thin
        # Stage 30.11.2 seam-compatibility wrapper), and the offline fake private
        # sink proof (a direct three-call sink proof + a runtime seam integration
        # proof driven by an in-memory recording FAKE transport). ZERO real
        # transport / real Discord / webhook send / dispatch reservation / live
        # run / provider call / Discord send / env read / wall-clock read /
        # daemon ships here, and NO Stage 28 / 29 / existing Stage 30 production
        # file is edited; no Stage 30.11.4+ file ships at Stage 30.11.3.
        "stage30_11_3_private_sink_models.py",
        "stage30_11_3_private_sink_adapter.py",
        "stage30_11_3_fake_private_sink_proof.py",
        # Stage 30.11.4 offline end-to-end proof production additions (end-to-end
        # proof models, end-to-end proof): the passive proof summary / result
        # models (importing no PHX2 module) and the pure proof that COMPOSES the
        # committed Stage 30.11.2 runtime seam + the committed Stage 30.11.3
        # private sink behind the dip gate over the committed default stream with
        # an INJECTED recording FAKE transport, and judges the composed run
        # against the author-verified baseline. ZERO real transport / real Discord
        # / webhook send / dispatch reservation / live run / provider call /
        # Discord send / env read / wall-clock read / daemon ships here, and NO
        # Stage 28 / 29 / existing Stage 30 production file is edited; no Stage
        # 30.11.5+ file ships at Stage 30.11.4.
        "stage30_11_4_offline_e2e_proof_models.py",
        "stage30_11_4_offline_e2e_proof.py",
        # Stage 30.11.5 controlled live ceremony wiring production additions
        # (live wiring models, live-candidate snapshot assembler, private
        # transport adapter, bounded live runner, fake live wiring proof): the
        # passive models (the live-candidate assembly result embedding the
        # committed Stage 30.11.1 snapshot + the private operator payload + the
        # low-level transport-client result + the bounded-run summary / result),
        # the assembler that converts an existing flat safe-scalar candidate
        # projection into a committed Stage 30.11.1 snapshot (failing closed on a
        # missing / malformed required field; never fabricating a dip; never
        # bypassing the committed bridge / dip gate), the transport adapter that
        # conforms to the committed Stage 30.11.3 sink transport protocol by
        # rendering a SAFE operator payload and handing it to an INJECTED fake
        # transport client, the bounded live runner that composes the source ->
        # assembler -> committed Stage 30.11.2 seam -> committed Stage 30.11.3
        # private sink -> injected transport adapter under HARD caps
        # (max_dispatches <= 1 / max_runtime_seconds <= 60 / max_candidates <=
        # 10, injected clock, single bounded for-loop, no daemon / while loop),
        # and the offline fake live wiring proof. ZERO real candidate source /
        # real transport / real Discord / webhook send / dispatch reservation /
        # live run / provider call / Discord send / env read / wall-clock read /
        # daemon ships here, and NO Stage 28 / 29 / existing Stage 30 production
        # file is edited; no Stage 30.11.6+ file ships at Stage 30.11.5.
        "stage30_11_5_live_wiring_models.py",
        "stage30_11_5_live_candidate_snapshot_assembler.py",
        "stage30_11_5_private_transport_adapter.py",
        "stage30_11_5_bounded_live_runner.py",
        "stage30_11_5_fake_live_wiring_proof.py",
        # Stage 30.11.6 real candidate source / harvest seam additions (candidate
        # source models, harvested-candidate -> Stage 30.11.5 projection adapter,
        # candidate harvest adapter, fake candidate source proof). The harvest
        # adapter drives an INJECTED committed assembler boundary, captures the
        # assembled record, and projects it into the Stage 30.11.5 shape WITHOUT
        # ever constructing a transport / dispatch sink / runner (the old ungated
        # dispatch is structurally impossible). Fakes / offline only.
        "stage30_11_6_candidate_source_models.py",
        "stage30_11_6_stage29_projection_adapter.py",
        "stage30_11_6_candidate_harvest_adapter.py",
        "stage30_11_6_fake_candidate_source_proof.py",
        # Stage 30.11.7 candidate dip-enrichment bridge additions (enrichment
        # models, fail-closed enrichment adapter, fake enrichment proof). The
        # adapter fills the missing Stage 30 dip fields onto a harvested candidate
        # from four INJECTED resolvers, failing closed on every missing /
        # unconfirmed / stale / malformed dimension and never fabricating a dip.
        # A clean leaf: imports only its own three siblings. Fakes / offline only.
        "stage30_11_7_candidate_enrichment_models.py",
        "stage30_11_7_candidate_enrichment_adapter.py",
        "stage30_11_7_fake_enrichment_proof.py",
        # Stage 30.11.8 narrow migration-confirmation bridge additions (confirmation
        # models, fail-closed confirmation adapter, fake confirmation proof). The
        # adapter maps an injected per-mint migration evidence onto a confirmed
        # verdict ONLY for a bound, redaction-safe, on-chain COMPLETE, fresh,
        # valid-anchor reading, failing closed (with a precise reason) otherwise and
        # never fabricating evidence. A clean leaf: imports only its own three
        # siblings. Fakes / offline only.
        "stage30_11_8_migration_confirmation_models.py",
        "stage30_11_8_migration_confirmation_adapter.py",
        "stage30_11_8_fake_confirmation_proof.py",
        # Stage 30.11.9 mint-keyed migration evidence-source adapter slice (the
        # per-mint source the Stage 30.11.8 confirmation seam was missing). A
        # clean leaf: imports only its own three siblings; routes a sanitized
        # record by mint, never fabricating evidence. Fakes / offline only.
        "stage30_11_9_migration_evidence_source_models.py",
        "stage30_11_9_migration_evidence_source_adapter.py",
        "stage30_11_9_fake_evidence_source_proof.py",
        # Stage 30.11.10 real ATH-resolver bridge slice (the real ATH resolver the
        # Stage 30.11.7 ATH dimension was missing). A clean leaf: imports only its
        # own three siblings; maps a committed Stage 27.4 AthContextRecord-shaped
        # reading onto the Stage 30.11.7 ATH resolver contract, carrying the
        # committed drawdown VERBATIM and never recomputing it, failing closed on a
        # missing / stale / pre-migration / drawdownless / wrong-mint reading.
        # Fakes / offline only.
        "stage30_11_10_ath_resolver_models.py",
        "stage30_11_10_ath_resolver_adapter.py",
        "stage30_11_10_fake_ath_resolver_proof.py",
        # Stage 30.12 PHOENIX private operator ping renderer slice (the rich
        # committed operator-body renderer the first real private send improvised
        # out-of-repo). A pure LEAF: the models import no PHX2 module, the
        # renderer imports only the models sibling, and the manifest is
        # constants-only. NOT wired into the Stage 30.11.5 send path; wiring it
        # live is a separate operator-authorized step.
        "stage30_12_phoenix_operator_ping_models.py",
        "stage30_12_phoenix_operator_ping_renderer.py",
        "stage30_12_manifest.py",
        # Stage 30.12.1 body-builder factory (the committed home for the
        # body-builder glue that feeds the Stage 30.12 renderer through the
        # EXISTING Stage 30.11.5 ``compact_body_builder`` seam, with NO runner /
        # sink / gate edit and no monkey-patch). A clean leaf: imports only the
        # two Stage 30.12 siblings (models + renderer) and renders at
        # construction so a fail-closed surfaces before the runner. Offline only.
        "stage30_12_1_phoenix_operator_ping_body_builder.py",
        # Stage 30.11.11 migration-anchored ATH source slice (the committed real
        # ATH context source; the ATH-correctness fix anchoring the OHLCV window
        # at the migration moment so a live post-migration ATH cannot clip the
        # first peak). Imports the committed Stage 27.4 reader + Stage 29.2
        # sources DIRECTLY (the audited Stage 30.11.11 import expansion);
        # transport + secret + now-clock injected; fail-closed; offline-testable.
        "stage30_11_11_migration_anchored_ath_source.py",
        # Stage 30.11.13 committed end-to-end no-send composer slice (the
        # integration capstone binding the gate decision + the PHOENIX body to
        # ONE immutable revalidation snapshot; hard-wires the Stage 30.11.11
        # anchored ATH source, computes the ATH market cap in committed code,
        # and dispatches only through the Stage 30.11.5 recording FAKE
        # transport). Integration module + offline fake proof; no real send.
        "stage30_11_13_committed_no_send_composer.py",
        "stage30_11_13_fake_composer_proof.py",
        # Stage 30.11.15 committed cross-run private operator ping dedupe slice
        # (the dedupe key + outcome models, the append-only JSONL ledger + its
        # in-memory twin, the total no-send guard + deduped orchestrator, and the
        # offline fake dedupe proof). The ledger is the sole filesystem-
        # persistence surface (an injected base path only); no real send.
        "stage30_11_15_ping_dedupe_models.py",
        "stage30_11_15_ping_dedupe_ledger.py",
        "stage30_11_15_no_send_dedupe_guard.py",
        "stage30_11_15_fake_dedupe_proof.py",
        # Stage 30.11.16 no-send-by-default real private transport guard slice
        # (the real-send authorization / target / result models, the one-shot
        # burn-on-attempt guard, and the offline fake real-send proof + recording
        # fake transport). Consumes the Stage 30.11.15 deduped result; imports no
        # Stage 28 (the audited transport is injected duck-typed); no real send.
        "stage30_11_16_real_send_models.py",
        "stage30_11_16_real_private_transport_guard.py",
        "stage30_11_16_fake_real_send_proof.py",
        # Stage 30.11.17 operator-curated compose session slice (three production
        # modules). No real send; composes the committed Stage 30.11.15 deduped
        # orchestrator; imports no Stage 28/29, no Stage 30.11.16 guard.
        "stage30_11_17_operator_curated_candidate_list_models.py",
        "stage30_11_17_operator_curated_compose_session.py",
        "stage30_11_17_fake_curated_session_proof.py",
        # Stage 30.11.18 harvested-facts -> curated compose session adapter slice
        # (three production modules). Offline; maps a flat harvested-candidate
        # FACTS carrier into the Stage 30.11.17 curated session input, runs the
        # bounded no-send session, and rolls up a redacted report. Imports no
        # Stage 28/29, no Stage 30.11.16 guard, no Stage 30.11.6 harvest adapter;
        # the real harvest source is ceremony-injected.
        "stage30_11_18_harvested_facts_models.py",
        "stage30_11_18_harvest_to_curated_adapter.py",
        "stage30_11_18_fake_harvest_session_proof.py",
        # Stage 30.11.19 market-context enrichment adapter slice (three production
        # modules). Offline; reuses the committed Stage 30.4.3 token-overview
        # market-context source (injected, duck-typed) to fill the MC/LP/fetched-at
        # bundle on harvested facts, then runs the committed Stage 30.11.18
        # session. No new fetcher, no Stage 28/29 import, no real transport
        # construction; the live read is ceremony-injected.
        "stage30_11_19_market_context_enrichment_models.py",
        "stage30_11_19_market_context_enrichment_adapter.py",
        "stage30_11_19_fake_market_context_enrichment_proof.py",
    }
)


_TESTS_STAGE30_ALLOWED_BASENAMES: frozenset = frozenset(
    {
        "__init__.py",
        "test_stage_30_0_spec_lock.py",
        # Stage 30.1 test additions.
        "test_stage_30_1_tier_decision_models.py",
        "test_stage_30_1_tier_decision_projector.py",
        "test_stage_30_1_tier_decision_artifact_writer.py",
        # Stage 30.1 tier-band fractional-drawdown regression suite (committed
        # at HEAD e32b8ce; registered here to close a pre-existing inventory
        # gap -- the HEAD commit added the file without listing it).
        "test_stage_30_1_tier_units_regression.py",
        # Stage 30.2 test additions.
        "test_stage_30_2_compact_ping_models.py",
        "test_stage_30_2_compact_ping_renderer.py",
        "test_stage_30_2_compact_ping_artifact_writer.py",
        # Stage 30.3A test additions.
        "test_stage_30_3_compact_runtime_models.py",
        "test_stage_30_3_compact_candidate_projection.py",
        "test_stage_30_3_compact_candidate_context_recorder.py",
        "test_stage_30_3_compact_body_transport_wrapper.py",
        "test_stage_30_3_compact_body_transport_wrapper_composes_with_stage29_5_6.py",
        "test_stage_30_3_runtime_wiring_artifact_writer.py",
        "test_stage_30_3_spec_lock.py",
        # Stage 30.3B test additions.
        "test_stage_30_3_compact_runtime_session_orchestrator.py",
        "test_stage_30_3_compact_runtime_session_orchestrator_redaction_safe.py",
        # Stage 30.3D proof-doc guard.
        "test_stage_30_3d_live_proof_doc.py",
        # Stage 30.4.0 spec-lock pin test.
        "test_stage_30_4_0_spec_lock.py",
        # Stage 30.4.1 offline test additions.
        "test_stage_30_4_1_models.py",
        "test_stage_30_4_1_formatter.py",
        "test_stage_30_4_1_adapter_unknown_path.py",
        "test_stage_30_4_1_adapter_present_path_with_fake_source.py",
        "test_stage_30_4_1_adapter_error_stale_paths.py",
        "test_stage_30_4_1_artifact_writer.py",
        "test_stage_30_4_1_boundaries.py",
        # Stage 30.4.2 opt-in parallel compact runtime session
        # orchestrator test additions (integration + boundaries).
        "test_stage_30_4_2_compact_runtime_integration.py",
        "test_stage_30_4_2_boundaries.py",
        # Stage 30.4.3 offline Birdeye token-overview source bridge
        # test additions (unknown paths, present path + end-to-end
        # render, partial / bad values, boundaries, manifest).
        "test_stage_30_4_3_birdeye_source_unknown_paths.py",
        "test_stage_30_4_3_birdeye_source_present_path.py",
        "test_stage_30_4_3_birdeye_source_partial_and_bad_values.py",
        "test_stage_30_4_3_boundaries.py",
        "test_stage_30_4_3_manifest.py",
        # Stage 30.4.4 proof-doc guard.
        "test_stage_30_4_4_mc_lp_private_live_proof_doc.py",
        # Stage 30.5.0 migration-context spec-lock pin test.
        "test_stage_30_5_0_migration_context_spec_lock.py",
        # Stage 30.5.1 offline migration-context test additions
        # (models, source protocol, adapter, boundaries, manifest).
        "test_stage_30_5_1_migration_context_models.py",
        "test_stage_30_5_1_migration_context_source_protocol.py",
        "test_stage_30_5_1_migration_context_adapter.py",
        "test_stage_30_5_1_boundaries.py",
        "test_stage_30_5_1_manifest.py",
        # Stage 30.5.2 opt-in compact migration runtime adapter test
        # additions (adapter unit, runtime integration, boundaries,
        # manifest).
        "test_stage_30_5_2_compact_migration_runtime_adapter.py",
        "test_stage_30_5_2_runtime_integration.py",
        "test_stage_30_5_2_boundaries.py",
        "test_stage_30_5_2_manifest.py",
        # Stage 30.5.3 offline Stage 29.5 migration-evidence bridge test
        # additions (bridge unit, runtime integration, boundaries,
        # manifest).
        "test_stage_30_5_3_stage29_migration_bridge.py",
        "test_stage_30_5_3_runtime_integration.py",
        "test_stage_30_5_3_boundaries.py",
        "test_stage_30_5_3_manifest.py",
        # Stage 30.6.0 storage + dedupe spec-lock pin test.
        "test_stage_30_6_0_storage_dedupe_spec_lock.py",
        # Stage 30.6.1 storage budget models + evaluator test additions
        # (models, evaluator, boundaries, manifest).
        "test_stage_30_6_1_storage_budget_models.py",
        "test_stage_30_6_1_storage_budget_evaluator.py",
        "test_stage_30_6_1_boundaries.py",
        "test_stage_30_6_1_manifest.py",
        # Stage 30.7.0 ATH context bridge spec-lock pin test.
        "test_stage_30_7_0_ath_context_spec_lock.py",
        # Stage 30.7.1 offline ATH context test additions (models,
        # projection, boundaries, manifest).
        "test_stage_30_7_1_ath_context_models.py",
        "test_stage_30_7_1_ath_context_projection.py",
        "test_stage_30_7_1_boundaries.py",
        "test_stage_30_7_1_manifest.py",
        # Stage 30.7.2 opt-in compact ATH runtime adapter test additions
        # (adapter unit, runtime integration, boundaries, manifest).
        "test_stage_30_7_2_compact_ath_runtime_adapter.py",
        "test_stage_30_7_2_runtime_integration.py",
        "test_stage_30_7_2_boundaries.py",
        "test_stage_30_7_2_manifest.py",
        # Stage 30.7.3 sanitized upstream ATH-evidence bridge test additions
        # (bridge unit, runtime integration, boundaries, manifest).
        "test_stage_30_7_3_sanitized_ath_bridge.py",
        "test_stage_30_7_3_runtime_integration.py",
        "test_stage_30_7_3_boundaries.py",
        "test_stage_30_7_3_manifest.py",
        # Stage 30.7.4 ATH context bridge closure audit + handoff test
        # additions (closure-audit doc, handoff doc, boundaries,
        # manifest).
        "test_stage_30_7_4_closure_audit.py",
        "test_stage_30_7_4_handoff.py",
        "test_stage_30_7_4_boundaries.py",
        "test_stage_30_7_4_manifest.py",
        # Stage 30.8.0 compact session artifact / storage-readiness
        # spec-lock pin test.
        "test_stage_30_8_0_storage_spec_lock.py",
        # Stage 30.8.1 pure compact artifact models + validators test
        # additions (models, validators, boundaries, manifest).
        "test_stage_30_8_1_artifact_models.py",
        "test_stage_30_8_1_artifact_validators.py",
        "test_stage_30_8_1_boundaries.py",
        "test_stage_30_8_1_manifest.py",
        # Stage 30.8.2 temp-dir compact session artifact writer test
        # additions (writer, boundaries, manifest).
        "test_stage_30_8_2_temp_artifact_writer.py",
        "test_stage_30_8_2_boundaries.py",
        "test_stage_30_8_2_manifest.py",
        # Stage 30.8.2 temp-dir artifact writer closure-audit test
        # (closure / handoff doc guard only; no production / manifest
        # change; no Stage 30.8.3 file).
        "test_stage_30_8_2_closure_audit.py",
        # Stage 30.8.3 offline compact session index / dedupe test
        # additions (index models, bundle reader, index builder,
        # boundaries, manifest).
        "test_stage_30_8_3_session_index_models.py",
        "test_stage_30_8_3_session_bundle_reader.py",
        "test_stage_30_8_3_session_index_builder.py",
        "test_stage_30_8_3_boundaries.py",
        "test_stage_30_8_3_manifest.py",
        # Stage 30.8.4 controlled compact session artifact proof test
        # additions (controlled proof runner, boundaries, manifest).
        "test_stage_30_8_4_controlled_artifact_proof.py",
        "test_stage_30_8_4_boundaries.py",
        "test_stage_30_8_4_manifest.py",
        # Stage 30.9.0 bounded private live compact session bridge
        # spec-lock pin test (spec-lock only; no runtime, no bridge, no
        # live).
        "test_stage_30_9_0_bounded_private_live_compact_spec_lock.py",
        # Stage 30.9.1 offline artifact bridge test additions (bridge
        # models, capture transport, projector, bridge proof, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_9_1_artifact_bridge_models.py",
        "test_stage_30_9_1_capture_transport.py",
        "test_stage_30_9_1_artifact_projector.py",
        "test_stage_30_9_1_artifact_bridge_proof.py",
        "test_stage_30_9_1_boundaries.py",
        "test_stage_30_9_1_manifest.py",
        # Stage 30.10.0 compact tier-dip eligibility gate spec-lock pin
        # test (spec-lock only; no runtime, no classifier, no live).
        "test_stage_30_10_0_compact_tier_dip_eligibility_spec_lock.py",
        # Stage 30.10.1 fake / offline eligibility model + classifier test
        # additions (models, classifier, boundaries, manifest). Fakes /
        # offline only.
        "test_stage_30_10_1_tier_dip_eligibility_models.py",
        "test_stage_30_10_1_tier_dip_eligibility_classifier.py",
        "test_stage_30_10_1_boundaries.py",
        "test_stage_30_10_1_manifest.py",
        # Stage 30.10.2 optional fake / offline pre-dispatch tier-dip gate
        # test additions (gate models, gate, fake-gate proof, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_10_2_pre_dispatch_gate_models.py",
        "test_stage_30_10_2_pre_dispatch_gate.py",
        "test_stage_30_10_2_fake_gate_proof.py",
        "test_stage_30_10_2_boundaries.py",
        "test_stage_30_10_2_manifest.py",
        # Stage 30.10.3 offline gate artifact integration proof test
        # additions (artifact models, projector, fake artifact proof,
        # boundaries, manifest). Fakes / offline only.
        "test_stage_30_10_3_gate_artifact_models.py",
        "test_stage_30_10_3_gate_artifact_projector.py",
        "test_stage_30_10_3_fake_artifact_proof.py",
        "test_stage_30_10_3_boundaries.py",
        "test_stage_30_10_3_manifest.py",
        # Stage 30.9.2_RESUME dip-filtered live proof planning / fake-proof
        # test additions (resume models, resume plan, resume fake proof,
        # boundaries, manifest). Fakes / offline only.
        "test_stage_30_9_2_resume_dip_filtered_live_models.py",
        "test_stage_30_9_2_resume_dip_filtered_live_plan.py",
        "test_stage_30_9_2_resume_fake_proof.py",
        "test_stage_30_9_2_resume_boundaries.py",
        "test_stage_30_9_2_resume_manifest.py",
        # Stage 30.9.3 dip-filtered live dispatch integration seam test
        # additions (models, adapter, orchestrator, fake integration proof,
        # boundaries, manifest). Fakes / offline only.
        "test_stage_30_9_3_dip_filtered_live_gate_models.py",
        "test_stage_30_9_3_dip_filtered_live_gate_adapter.py",
        "test_stage_30_9_3_dip_filtered_live_gate_orchestrator.py",
        "test_stage_30_9_3_fake_live_gate_integration_proof.py",
        "test_stage_30_9_3_boundaries.py",
        "test_stage_30_9_3_manifest.py",
        # Stage 30.11.0 dip-gated live dispatch wiring spec-lock pin test.
        "test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py",
        # Stage 30.11.1 offline live-candidate assembly bridge test additions
        # (bridge models, bridge, fake bridge proof, boundaries, manifest).
        # Fakes / offline only.
        "test_stage_30_11_1_live_candidate_bridge_models.py",
        "test_stage_30_11_1_live_candidate_bridge.py",
        "test_stage_30_11_1_fake_bridge_proof.py",
        "test_stage_30_11_1_boundaries.py",
        "test_stage_30_11_1_manifest.py",
        # Stage 30.11.2 offline runtime gate seam test additions (runtime gate
        # models, runtime gate seam, fake runtime gate proof, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_11_2_runtime_gate_models.py",
        "test_stage_30_11_2_runtime_gate_seam.py",
        "test_stage_30_11_2_fake_runtime_gate_proof.py",
        "test_stage_30_11_2_boundaries.py",
        "test_stage_30_11_2_manifest.py",
        # Stage 30.11.3 private sink adapter test additions (private sink
        # models, private sink adapter, fake private sink proof, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_11_3_private_sink_models.py",
        "test_stage_30_11_3_private_sink_adapter.py",
        "test_stage_30_11_3_fake_private_sink_proof.py",
        "test_stage_30_11_3_boundaries.py",
        "test_stage_30_11_3_manifest.py",
        # Stage 30.11.4 offline end-to-end proof test additions (end-to-end proof
        # models, end-to-end proof, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_4_offline_e2e_proof_models.py",
        "test_stage_30_11_4_offline_e2e_proof.py",
        "test_stage_30_11_4_boundaries.py",
        "test_stage_30_11_4_manifest.py",
        # Stage 30.11.5 controlled live ceremony wiring test additions (live
        # wiring models, live-candidate snapshot assembler, private transport
        # adapter, bounded live runner, fake live wiring proof, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_11_5_live_wiring_models.py",
        "test_stage_30_11_5_live_candidate_snapshot_assembler.py",
        "test_stage_30_11_5_private_transport_adapter.py",
        "test_stage_30_11_5_bounded_live_runner.py",
        "test_stage_30_11_5_fake_live_wiring_proof.py",
        "test_stage_30_11_5_boundaries.py",
        "test_stage_30_11_5_manifest.py",
        # Stage 30.11.6 real candidate source / harvest seam test additions
        # (candidate source models, projection adapter, harvest adapter, fake
        # candidate source proof, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_6_candidate_source_models.py",
        "test_stage_30_11_6_stage29_projection_adapter.py",
        "test_stage_30_11_6_candidate_harvest_adapter.py",
        "test_stage_30_11_6_fake_candidate_source_proof.py",
        "test_stage_30_11_6_boundaries.py",
        "test_stage_30_11_6_manifest.py",
        # Stage 30.11.7 candidate dip-enrichment bridge test additions (enrichment
        # models, enrichment adapter, fake enrichment proof + end-to-end runner
        # composition, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_7_candidate_enrichment_models.py",
        "test_stage_30_11_7_candidate_enrichment_adapter.py",
        "test_stage_30_11_7_fake_enrichment_proof.py",
        "test_stage_30_11_7_boundaries.py",
        "test_stage_30_11_7_manifest.py",
        # Stage 30.11.8 narrow migration-confirmation bridge test additions
        # (confirmation models, confirmation adapter + Stage 30.11.7 composition,
        # fake confirmation proof, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_8_migration_confirmation_models.py",
        "test_stage_30_11_8_migration_confirmation_adapter.py",
        "test_stage_30_11_8_fake_confirmation_proof.py",
        "test_stage_30_11_8_boundaries.py",
        "test_stage_30_11_8_manifest.py",
        # Stage 30.11.9 mint-keyed migration evidence-source test additions
        # (source models, source adapter + mapper, fake source proof, composition
        # with the committed Stage 30.11.8 + 30.11.7 adapters, boundaries,
        # manifest). Fakes / offline only.
        "test_stage_30_11_9_migration_evidence_source_models.py",
        "test_stage_30_11_9_migration_evidence_source_adapter.py",
        "test_stage_30_11_9_fake_evidence_source_proof.py",
        "test_stage_30_11_9_composition.py",
        "test_stage_30_11_9_boundaries.py",
        "test_stage_30_11_9_manifest.py",
        # Stage 30.11.10 real ATH-resolver bridge test additions (ATH-resolver
        # models, ATH-resolver adapter, fake ATH-resolver proof, composition with
        # the committed Stage 30.11.7 / 30.11.8 / 30.11.9 adapters + the committed
        # Stage 27.4 read_ath_context, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_10_ath_resolver_models.py",
        "test_stage_30_11_10_ath_resolver_adapter.py",
        "test_stage_30_11_10_fake_ath_resolver_proof.py",
        "test_stage_30_11_10_composition.py",
        "test_stage_30_11_10_boundaries.py",
        "test_stage_30_11_10_manifest.py",
        # Stage 30.12 PHOENIX private operator ping renderer test additions
        # (models, renderer, boundaries, manifest). Pure / offline only.
        "test_stage_30_12_phoenix_operator_ping_models.py",
        "test_stage_30_12_phoenix_operator_ping_renderer.py",
        "test_stage_30_12_boundaries.py",
        "test_stage_30_12_manifest.py",
        # Stage 30.12.1 body-builder factory test additions (factory unit +
        # render-at-construction + fail-closed + mint-mismatch + committed-runner
        # end-to-end + leaf boundaries). Fakes / offline only.
        "test_stage_30_12_1_phoenix_operator_ping_body_builder.py",
        # Stage 30.11.11 migration-anchored ATH source test additions (source
        # behavior + anchored window + interval selection + fail-closed +
        # Stage 27.4 compat + tier correction, boundaries, manifest). Fakes /
        # offline only.
        "test_stage_30_11_11_migration_anchored_ath_source.py",
        "test_stage_30_11_11_boundaries.py",
        "test_stage_30_11_11_manifest.py",
        # Stage 30.11.13 committed end-to-end no-send composer tests.
        "test_stage_30_11_13_committed_no_send_composer.py",
        # Stage 30.11.15 committed cross-run ping dedupe tests (ledger replay +
        # TTL + fail-closed, guard key derivation, composer hook, deduped
        # orchestrator, boundaries, manifest). Fakes / offline only.
        "test_stage_30_11_15_ping_dedupe_ledger.py",
        "test_stage_30_11_15_no_send_dedupe_guard.py",
        "test_stage_30_11_15_boundaries.py",
        "test_stage_30_11_15_manifest.py",
        "test_stage_30_11_15_fake_dedupe_proof.py",
        # Stage 30.11.16 real private transport guard tests (models, guard,
        # fake proof, boundaries, manifest). Fakes / no-send only.
        "test_stage_30_11_16_real_send_models.py",
        "test_stage_30_11_16_real_private_transport_guard.py",
        "test_stage_30_11_16_fake_real_send_proof.py",
        "test_stage_30_11_16_boundaries.py",
        "test_stage_30_11_16_manifest.py",
        # Stage 30.11.17 operator-curated compose session tests (models, session,
        # fake proof, boundaries, manifest). Fakes / no-send only.
        "test_stage_30_11_17_operator_curated_candidate_list_models.py",
        "test_stage_30_11_17_operator_curated_compose_session.py",
        "test_stage_30_11_17_fake_curated_session_proof.py",
        "test_stage_30_11_17_boundaries.py",
        "test_stage_30_11_17_manifest.py",
        # Stage 30.11.18 harvested-facts -> curated compose session adapter tests
        # (adapter, fake proof, boundaries, manifest). Fakes / offline / no-send.
        "test_stage_30_11_18_harvest_to_curated_adapter.py",
        "test_stage_30_11_18_fake_harvest_session_proof.py",
        "test_stage_30_11_18_boundaries.py",
        "test_stage_30_11_18_manifest.py",
        # Stage 30.11.19 market-context enrichment adapter tests (adapter, fake
        # proof, boundaries, manifest). Fakes / offline / no-send.
        "test_stage_30_11_19_market_context_enrichment_adapter.py",
        "test_stage_30_11_19_fake_market_context_enrichment_proof.py",
        "test_stage_30_11_19_boundaries.py",
        "test_stage_30_11_19_manifest.py",
    }
)


def _basenames_of(path: Path) -> frozenset:
    return frozenset(
        entry.name
        for entry in path.iterdir()
        if entry.name != "__pycache__"
    )


def test_stage30_package_dir_inventory_is_minimal() -> None:
    observed = _basenames_of(STAGE30_ROOT)
    extras = observed - _STAGE30_ALLOWED_BASENAMES
    assert not extras, (
        "Stage 30.0 package dir must contain only the "
        "allowed inventory; unexpected entries: "
        f"{sorted(extras)}"
    )
    missing = _STAGE30_ALLOWED_BASENAMES - observed
    assert not missing, (
        "Stage 30.0 package dir is missing required entries: "
        f"{sorted(missing)}"
    )


def test_stage30_tests_package_dir_inventory_is_minimal() -> None:
    observed = _basenames_of(TESTS_STAGE30_ROOT)
    extras = observed - _TESTS_STAGE30_ALLOWED_BASENAMES
    assert not extras, (
        "Stage 30.0 tests package dir must contain only the "
        "allowed inventory; unexpected entries: "
        f"{sorted(extras)}"
    )
    missing = _TESTS_STAGE30_ALLOWED_BASENAMES - observed
    assert not missing, (
        "Stage 30.0 tests package dir is missing required "
        f"entries: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# 3. Spec-lock markdown contains the ten required section headings.
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: tuple = (
    "## 1. Stage 30 stance pin",
    "## 2. Stage 30 substage map",
    "## 3. Hard forbidden scope",
    "## 4. Compact private ping target",
    "## 5. Tier semantics",
    "## 6. Required operator-readable fields",
    "## 7. Bounded private runtime semantics",
    "## 8. Required artifacts",
    "## 9. Ceremony discipline",
    "## 10. Acceptance criteria for Stage 30 overall",
)


def test_spec_lock_contains_all_required_section_headings() -> None:
    text = _spec_lock_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30 spec lock missing required section "
            f"heading: {heading!r}"
        )


def test_spec_lock_section_headings_appear_in_order() -> None:
    text = _spec_lock_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 4. Spec-lock markdown declares the exact tier bands with the
#    intentional gaps.
# ---------------------------------------------------------------------------


_REQUIRED_TIER_BAND_LINES: tuple = (
    "**TIER_1**: `0.50 <= drop <= 0.60`",
    "**TIER_2**: `0.62 <= drop <= 0.80`",
    "**TIER_3**: `0.82 <= drop <= 0.95`",
)


def test_spec_lock_declares_exact_tier_bands() -> None:
    text = _spec_lock_text()
    for band_line in _REQUIRED_TIER_BAND_LINES:
        assert band_line in text, (
            f"Stage 30 spec lock missing tier band line: "
            f"{band_line!r}"
        )


def test_spec_lock_preserves_intentional_tier_gaps() -> None:
    """Stage 30 must not silently force in-gap drops into a tier;
    the spec lock must explicitly name the gap discipline.
    """
    normalized = _normalized_whitespace(_spec_lock_text())
    required_gap_phrases = (
        # 0.60-0.62 gap pin
        "0.60-0.62",
        # 0.80-0.82 gap pin
        "0.80-0.82",
        # > 0.95 graveyard pin
        "> 0.95",
        # < 0.50 pre-tier pin
        "< 0.50",
        # no internal rounding pin
        "NEVER rounds `drop` before tier comparison",
    )
    for phrase in required_gap_phrases:
        assert phrase in normalized, (
            f"Stage 30 spec lock must explicitly name the "
            f"tier-band gap discipline: missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 5. Spec-lock markdown declares the preferred drawdown formula.
# ---------------------------------------------------------------------------


def test_spec_lock_declares_preferred_drawdown_formula() -> None:
    text = _spec_lock_text()
    formula = "drawdown_from_ath = (current_mc - ath_mc) / ath_mc"
    assert formula in text, (
        "Stage 30 spec lock must declare the preferred drawdown "
        f"formula verbatim: missing {formula!r}"
    )


def test_spec_lock_declares_equivalent_drop_formula() -> None:
    text = _spec_lock_text()
    formula = "drop = (ath_mc - current_mc) / ath_mc"
    assert formula in text, (
        "Stage 30 spec lock must declare the equivalent positive "
        f"drop formula verbatim: missing {formula!r}"
    )


def test_spec_lock_declares_abs_drop_relation() -> None:
    text = _spec_lock_text()
    relation = "drop = abs(drawdown_from_ath)"
    assert relation in text, (
        "Stage 30 spec lock must declare the abs() relation "
        f"between drop and drawdown_from_ath: missing {relation!r}"
    )


# ---------------------------------------------------------------------------
# 6. Spec-lock markdown explicitly forbids fabricating MC / supply.
# ---------------------------------------------------------------------------


def test_spec_lock_forbids_fabricating_mc_or_supply() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        # Tier model NEVER fabricates MC inputs.
        "NEVER fabricates",
        # Specifically names the three forbidden fabrications.
        "ath_mc",
        "current_mc",
        "circulating supply",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must explicitly forbid "
            f"fabricating MC/supply inputs; missing {phrase!r}"
        )


def test_spec_lock_forbids_fabricating_mc_supply_in_basis_section() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "Stage 30 NEVER fabricates MC, supply, ATH MC, or "
        "current MC."
    )
    assert required in normalized, (
        "Stage 30 spec lock must pin the no-fabrication "
        f"discipline verbatim in the basis section: missing "
        f"{required!r}"
    )


# ---------------------------------------------------------------------------
# 7. Spec-lock markdown says missing MC/LP/Net values render as Unknown.
# ---------------------------------------------------------------------------


def test_spec_lock_says_missing_values_render_as_unknown() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "Missing `MC`, `LP`, or `Net` values render as the "
        "literal string `Unknown`"
    )
    assert required in normalized, (
        "Stage 30 spec lock must pin the missing-as-Unknown "
        f"rendering rule verbatim: missing {required!r}"
    )


def test_spec_lock_forbids_zero_as_missing_sentinel() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "never `0`",
        "never `0.0`",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must forbid 0 / 0.0 as a "
            f"missing-value sentinel: missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. Spec-lock markdown declares the hard forbidden scope.
# ---------------------------------------------------------------------------


_REQUIRED_FORBIDDEN_SCOPE_PHRASES: tuple = (
    "route to any public audience",
    "paid or subscriber",
    "Stage 26 or Stage 29 enforcement",
    "sign, route, or execute any trade",
    "wallet, private key, seed",
    "Telegram",
    "X / Twitter / social",
    "Stage 31",
)


def test_spec_lock_declares_hard_forbidden_scope() -> None:
    text = _spec_lock_text()
    for phrase in _REQUIRED_FORBIDDEN_SCOPE_PHRASES:
        assert phrase in text, (
            "Stage 30 spec lock must declare the hard forbidden "
            f"scope; missing {phrase!r}"
        )


def test_spec_lock_forbids_raw_provider_blobs_in_artifacts() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = "raw provider blob"
    assert required in normalized, (
        "Stage 30 spec lock must forbid raw provider blobs in "
        f"artifacts: missing {required!r}"
    )


def test_spec_lock_forbids_printing_live_secrets() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "live secret",
        "API key",
        "webhook URL",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must forbid printing live "
            f"secrets; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 9. Spec-lock markdown says Stage 30.0 is spec lock only.
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage_30_0_is_spec_lock_only() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = "Stage 30.0 is spec lock only"
    assert required in normalized, (
        "Stage 30 spec lock must pin that Stage 30.0 is spec "
        f"lock only: missing {required!r}"
    )


def test_spec_lock_pins_stage_30_0_zero_production_code() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "ZERO production .py file beyond the package marker",
        "ZERO renderer",
        "ZERO tier model",
        "ZERO runner",
        "ZERO transport wrapper",
        "ZERO artifact writer",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must pin the Stage 30.0 "
            f"zero-production-code stance: missing {phrase!r}"
        )


def test_spec_lock_lists_substage_map_30_0_through_30_4() -> None:
    text = _spec_lock_text()
    required_substages = (
        "Stage 30.0",
        "Stage 30.1",
        "Stage 30.2",
        "Stage 30.3",
        "Stage 30.4",
    )
    for substage in required_substages:
        assert substage in text, (
            "Stage 30 spec lock must list the full substage "
            f"map 30.0..30.4: missing {substage!r}"
        )


# ---------------------------------------------------------------------------
# 10. Spec-lock markdown says live Discord / provider calls require
#     separate explicit operator authorization.
# ---------------------------------------------------------------------------


def test_spec_lock_requires_explicit_authorization_for_live_calls() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        # Implementation substages must not send live Discord.
        "MUST NOT send live Discord during implementation",
        # Implementation substages must not call live providers.
        "MUST NOT call live gRPC / HTTP / WebSocket providers",
        # Live ceremony requires separate explicit authorization.
        "separate explicit operator authorization",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must require separate explicit "
            f"authorization for live calls: missing {phrase!r}"
        )


def test_spec_lock_requires_explicit_authorization_for_tag_push_close() -> (
    None
):
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "MUST NOT tag, push, or close Stage 29 or Stage 30 "
        "without separate explicit operator authorization"
    )
    assert required in normalized, (
        "Stage 30 spec lock must require separate explicit "
        f"authorization for tag / push / close: missing "
        f"{required!r}"
    )


# ---------------------------------------------------------------------------
# 11. Defensive pins: spec lock carries no URL host, no webhook host
#     literal, no bearer / API-key prefix, and no Phoenix_Bot legacy
#     reference.
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_PATTERNS: tuple = (
    r"https?://",
    r"discord\.com/api/webhooks",
    r"discordapp\.com",
    r"api\.birdeye\.so",
    r"helius-rpc\.com",
    r"chainstack\.com",
    r"Bearer\s+[A-Za-z0-9]",
    r"Phoenix_Bot",
)


def test_spec_lock_carries_no_url_or_secret_literal() -> None:
    text = _spec_lock_text()
    for pattern in _FORBIDDEN_URL_PATTERNS:
        match = re.search(pattern, text)
        assert match is None, (
            "Stage 30 spec lock must not carry URL / host / "
            f"bearer / legacy literal matching {pattern!r}; "
            f"found: {match.group(0) if match else None!r}"
        )


# ---------------------------------------------------------------------------
# 12. Defensive pin: spec lock pins the example compact ping shape.
# ---------------------------------------------------------------------------


def test_spec_lock_contains_compact_ping_header_marker() -> None:
    text = _spec_lock_text()
    required_substrings = (
        "PHOENIX",
        "[Tier 3]",
        "\U0001f9e0 State",
        "MC: $",
        "ATH: $",
        "Mig: $",
        "Drop: -",
        "Age:",
        "Net:",
        "LP: $",
    )
    for substring in required_substrings:
        assert substring in text, (
            "Stage 30 spec lock must carry the compact ping "
            f"example shape; missing {substring!r}"
        )
