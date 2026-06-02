"""Stage 30.11.0 dip-gated live dispatch wiring spec-lock manifest.

Constants-only spec-lock manifest. Pins the Stage 30.11.0 inventory (the
spec-lock doc basename + path parts, this manifest basename, the test
basename), the Stage 30.11 stage id + spec version + next allowed substage,
the planned Stage 30.11.0 / 30.11.1 / 30.11.2 / 30.11.3 / 30.11.4 substage
sequence, the why-now finding (the committed Stage 30.9.3 dip-filtered gate
seam is pure / offline and is NOT wired into the live candidate -> dispatch
path; the only committed live path is the ungated Stage 29.3 smoke, which
dispatches the first assembled tradeable candidate with no dip gate), the
gate-placement contract (the committed dip gate runs BEFORE dispatch
reservation / the private send; only a PASS candidate may reserve a dispatch
and drive the private send; a non-dip skip is a clean no-send, never a
transport-layer veto / PAYLOAD_REFUSED / dispatch failure), the only-PASS
real-send rule, the required wall-clock max_runtime_seconds bound (the gap the
Stage 30.9.2 readiness report named), the existing reuse surfaces (by exact
name), the permitted scope expansion (the Stage 30.11 RUNTIME wiring slices
MAY compose the committed live surfaces behind the dip gate -- unlike the
offline-only Stage 30.9.x / 30.10.x slices -- but never fork / reimplement
them and never widen routing), the dip-gate decision tokens + the live result
counter axes (mirrored BY VALUE from the committed Stage 30.9.3 seam), the
failure behavior, the Stage 30.9.2 / 30.9.3 relationship, the forbidden
surfaces the spec-lock slice (and the Stage 30.11 family) must not touch, and
the forbidden runtime imports / text needles the spec-lock files are scanned
against.

Stage 30.11 is the dip-gated live dispatch wiring. The most important
planning finding is that the dip-focused eligibility decision is ALREADY
proven offline -- the committed Stage 30.9.3 seam composes the Stage 30.10
dip-gate stack and lets ONLY a PASS candidate reserve a dispatch -- but
NOTHING wires that seam into the live candidate -> dispatch path, and the only
committed live path is the ungated Stage 29.3 smoke (which dispatches the
first assembled tradeable candidate with no dip gate). Stage 30.11 wires the
committed dip gate into the live path so a private compact ping is sent ONLY
for an eligible dip, against committed + tested code, with a bounded wall-clock
runtime. Stage 30.11.0 LOCKS that design as prose + constants; it ships NO
runtime code, NO assembly bridge, NO runtime gate seam, NO real dispatch sink,
NO live provider call, NO Discord send, and edits NO existing live runner /
orchestrator / transport / Stage 28 suppression file.

Stage 30.11.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this constants-only manifest.
  * ZERO assembly bridge, ZERO runtime gate seam, ZERO real dispatch sink,
    ZERO runtime wiring, ZERO artifact integration.
  * ZERO new live runner, ZERO new provider, ZERO new readiness gate,
    ZERO direct Stage 28 suppression-logic edit.
  * ZERO live provider call, ZERO Discord send, ZERO live run, ZERO env
    read.
  * ZERO database / SQLite, ZERO zstd dependency / implementation, ZERO
    compression, ZERO default storage root, ZERO broad always-on daemon.
  * ZERO public / subscriber / paid routing, ZERO Telegram / X / social,
    ZERO trading / wallet / signing, ZERO enforcement, ZERO Stage 31.

Stage 30.11.1+ scope (deferred, each separately operator-authorized):

  * 30.11.1 -- the fake / offline live-candidate -> dip-gate-input assembly
    bridge: a pure mapping that composes the existing tier / ATH / migration /
    market-context surfaces into the committed Stage 30.9.3 live gate input,
    proven with fakes only; no runtime wiring, no live, no Discord.
  * 30.11.2 -- the runtime gate seam with fakes only: run the committed dip
    gate over each live-assembled candidate inside the bounded session,
    reserve a dispatch ONLY for a PASS candidate, and enforce a wall-clock
    max_runtime_seconds bound; fake provider + fake transport only.
  * 30.11.3 -- the real dispatch sink adapter: compose the committed private
    ping + audited transport as the seam's dispatch sink, invoked ONLY for a
    PASS candidate; still proven with fakes (the live ceremony is a separate
    operator-authorized step).
  * 30.11.4 -- the offline end-to-end proof: fake provider -> assembly ->
    committed dip gate -> fake sink, proving only-PASS dispatches + the caps +
    the wall-clock bound (the runtime counterpart of the Stage 30.10.3 fake
    artifact proof).

After Stage 30.11 wires + proves the dip-gated live dispatch path (offline /
fakes only), the controlled dip-filtered private compact live ceremony may run
against committed + green code. That ceremony remains a SEPARATE, explicitly
operator-authorized step.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no function / class definition,
  * contains no Call node (no implicit I/O at import time; the
    split-literal needle concatenations use ``+`` BinOps, never Calls),
  * contains no runtime side effect,
  * imports no PHX2 module.
"""

from __future__ import annotations

from typing import Tuple


# ---------------------------------------------------------------------------
# Stage id + minor version + spec version
# ---------------------------------------------------------------------------


STAGE30_11_STAGE_ID: str = "30.11"
STAGE30_11_0_MINOR_VERSION: str = "30.11.0"
STAGE30_11_0_SPEC_VERSION: str = (
    "stage30_11_v0_dip_gated_live_dispatch_wiring"
)


# ---------------------------------------------------------------------------
# Locked basenames + path parts + inventory delta
# ---------------------------------------------------------------------------


STAGE30_11_SPEC_LOCK_FILENAME: str = (
    "STAGE_30_11_0_DIP_GATED_LIVE_DISPATCH_WIRING_SPEC_LOCK.md"
)
STAGE30_11_MANIFEST_BASENAME: str = "stage30_11_manifest.py"


# The repo-relative path parts of the spec-lock doc (so a pin test can
# join them without re-spelling the path).
STAGE30_11_SPEC_LOCK_PATH_PARTS: Tuple[str, ...] = (
    "PHX2",
    "stage30",
    STAGE30_11_SPEC_LOCK_FILENAME,
)


STAGE30_11_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py",
)


# The NEW files Stage 30.11.0 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.10.3 inventory: exactly the spec-lock
# markdown plus this constants-only manifest. NO production .py beyond the
# manifest at Stage 30.11.0; NO Stage 30.11.1+ bridge / seam / sink file.
STAGE30_11_ALLOWED_INITIAL_FILES: Tuple[str, ...] = (
    STAGE30_11_SPEC_LOCK_FILENAME,
    STAGE30_11_MANIFEST_BASENAME,
)


# The only NEW production .py Stage 30.11.0 adds is this constants-only
# manifest; the spec lock is markdown. The boundary scan checks this
# basename for forbidden imports / needles.
STAGE30_11_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_MANIFEST_BASENAME,
)


# Every non-PHX2 import in this manifest must be in this stdlib allowlist
# (the manifest is constants-only: it needs only ``__future__`` +
# ``typing``). The spec-lock slice has NO PHX2 production import at all.
STAGE30_11_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# ---------------------------------------------------------------------------
# Planned substage sequence + next allowed stage
# ---------------------------------------------------------------------------
#
# Stage 30.11 is sequenced fake / offline before live, smallest reversible
# slice first. Exactly five planned substages; each separately
# operator-authorized.


STAGE30_11_PLANNED_SUBSTAGES: Tuple[str, ...] = (
    "30.11.0",
    "30.11.1",
    "30.11.2",
    "30.11.3",
    "30.11.4",
)


STAGE30_11_NEXT_ALLOWED_STAGE: str = "30.11.1"
STAGE30_11_NEXT_ALLOWED_STAGE_TITLE: str = (
    "fake / offline live-candidate -> dip-gate-input assembly bridge (a pure "
    "mapping that composes the existing tier / ATH / migration / market-"
    "context surfaces into the committed Stage 30.9.3 live gate input, proven "
    "with fakes only; no runtime wiring, no live provider call, no Discord "
    "send)"
)


# The locked substage roadmap (safe paraphrase labels). The controlled
# dip-filtered live ceremony runs only AFTER Stage 30.11 wires + proves the
# dip-gated live dispatch path offline.
STAGE30_11_SUBSTAGE_ROADMAP: Tuple[str, ...] = (
    (
        "30.11.0 -- this spec lock only (spec doc + constants-only manifest "
        "+ pin test); no runtime, no bridge, no seam, no sink, no live"
    ),
    (
        "30.11.1 -- fake / offline live-candidate -> dip-gate-input assembly "
        "bridge"
    ),
    (
        "30.11.2 -- runtime gate seam with fakes only (run the committed dip "
        "gate over each live-assembled candidate; reserve a dispatch ONLY for "
        "a PASS candidate; enforce a wall-clock max_runtime_seconds bound)"
    ),
    (
        "30.11.3 -- real dispatch sink adapter (compose the committed private "
        "ping + audited transport, invoked ONLY for a PASS candidate; still "
        "proven with fakes)"
    ),
    (
        "30.11.4 -- offline end-to-end proof (fake provider -> assembly -> "
        "committed dip gate -> fake sink; proves only-PASS dispatches + caps "
        "+ the wall-clock bound)"
    ),
)


# ---------------------------------------------------------------------------
# One-line purpose
# ---------------------------------------------------------------------------


STAGE30_11_PURPOSE: str = "dip-gated live dispatch wiring"


# ---------------------------------------------------------------------------
# Locked why-now finding
# ---------------------------------------------------------------------------
#
# The dip-focused eligibility decision is already proven offline by the
# committed Stage 30.9.3 seam, but nothing wires it into the live path; the
# only committed live path is the ungated Stage 29.3 smoke. Each entry is a
# safe paraphrase / existing surface name (NOT a secret, host, or transport
# destination).


STAGE30_11_WHY_NOW_FINDINGS: Tuple[str, ...] = (
    (
        "the committed Stage 30.9.3 seam composes the Stage 30.10 dip-gate "
        "stack and lets ONLY a PASS candidate reserve a dispatch -- but it is "
        "pure / offline and consumes a pre-assembled live gate input"
    ),
    (
        "nothing committed assembles a live candidate into the Stage 30.9.3 "
        "live gate input"
    ),
    (
        "nothing committed wires the Stage 30.9.3 seam into the live "
        "candidate -> dispatch path"
    ),
    (
        "the only committed live path is the ungated Stage 29.3 smoke, which "
        "dispatches the first assembled tradeable candidate with no dip gate"
    ),
    (
        "running the live ceremony today would require hand-improvising a "
        "live dispatch path; Stage 30.11 builds + proves it first"
    ),
    (
        "the bounded session has count bounds + an external stop signal but "
        "no native wall-clock runtime bound"
    ),
)


# ---------------------------------------------------------------------------
# Gate placement contract (locked)
# ---------------------------------------------------------------------------
#
# The committed dip gate is evaluated BEFORE dispatch reservation and BEFORE
# the private send. ONLY a PASS candidate may reserve a dispatch and drive the
# private send. A normal non-dip skip is a clean no-send, NOT a dispatch
# failure: Stage 30.11 must NOT reuse the Stage 28.4 / Stage 30.3
# ``PAYLOAD_REFUSED`` transport-veto path for a normal non-dip skip.


STAGE30_11_GATE_PLACEMENT: Tuple[str, ...] = (
    "committed dip gate evaluated BEFORE dispatch reservation",
    "committed dip gate evaluated BEFORE the private Discord send",
    "only a PASS candidate may reserve a dispatch",
    "only a PASS candidate may drive the private send",
    "non-dip skip is a normal no-send, NOT a dispatch failure",
    "no transport-layer veto for a normal non-dip skip",
    "no PAYLOAD_REFUSED-style transport veto for a normal non-dip skip",
    "tier / ATH / drawdown stay dispatch eligibility, not display-only",
)


# ---------------------------------------------------------------------------
# Only-PASS real-send rule (locked)
# ---------------------------------------------------------------------------
#
# The real dispatch sink (the committed private ping + audited transport) may
# be invoked ONLY for a PASS candidate and ONLY within the dispatch /
# private-send caps. There is NO other call site for the real sink.


STAGE30_11_ONLY_PASS_SEND_RULE: Tuple[str, ...] = (
    "the real dispatch sink is invoked ONLY for a PASS candidate",
    "the real dispatch sink is invoked ONLY within the dispatch cap",
    "the real dispatch sink is invoked ONLY within the private-send cap",
    "a non-dip / invalid candidate can never reach the real sink",
    "the run stops after the dispatch / private-send cap is reached",
    "the real send is impossible without a PASS decision",
)


# ---------------------------------------------------------------------------
# Required wall-clock runtime bound (locked)
# ---------------------------------------------------------------------------
#
# Stage 30.11 adds the wall-clock ``max_runtime_seconds`` bound the bounded
# session lacks. The bound is an explicit cap; the wiring stops cleanly when
# it elapses. Stage 30.11 invents NO broad always-on daemon / background
# service / autorestart loop.


STAGE30_11_RUNTIME_BOUND: Tuple[str, ...] = (
    "max_runtime_seconds is an explicit wall-clock cap",
    "the wiring stops cleanly when max_runtime_seconds elapses",
    "the wall-clock bound composes with the existing count bounds",
    "the wall-clock bound composes with the existing external stop signal",
    "no broad always-on daemon",
    "no background service",
    "no autorestart loop",
)


# ---------------------------------------------------------------------------
# Existing reuse surfaces (by exact name)
# ---------------------------------------------------------------------------
#
# Stage 30.11 MUST reuse the committed dip-gate seam, the committed dip-gate
# stack, the existing tier / ATH / migration / market context, and the
# existing live session + transport + private ping. It builds NO new gate, NO
# new provider, NO new live runner, NO new transport. These are existing
# production surface names (not secrets, not hosts, not transport
# destinations).


STAGE30_11_EXISTING_REUSE_SURFACES: Tuple[str, ...] = (
    "run_dip_filtered_live_gate_integration",
    "evaluate_dip_filtered_live_gate",
    "Stage30_9_3LiveGateInput",
    "Stage30_9_3LiveGateDecision",
    "Stage30_9_3LiveGateIntegrationResult",
    "the Stage 30.10.1 / 30.10.2 / 30.10.3 dip-gate stack",
    "decide_tier",
    "TierDecisionRecord",
    "tier_token",
    "existing ATH context",
    "existing migration context",
    "existing MC / LP / current market context",
    "existing Stage 28 / 29 / 30 live session + gates",
    "existing audited transport + private ping + private webhook transport",
)


# ---------------------------------------------------------------------------
# Permitted scope expansion (locked, paraphrased)
# ---------------------------------------------------------------------------
#
# Unlike the offline-only Stage 30.9.x / 30.10.x slices (which forbid every
# Stage 21-29 production import), the Stage 30.11 RUNTIME wiring slices
# (30.11.1+) are EXPLICITLY permitted to compose the committed live surfaces
# BEHIND the dip gate. The permitted-import allowlists are pinned per-slice
# when each runtime slice lands; the Stage 30.11.0 spec-lock files themselves
# import nothing (this manifest is constants-only). The expansion is bounded:
# Stage 30.11 wires + composes; it never forks, never reimplements, never adds
# a new provider / runner / readiness gate, and never widens routing.


STAGE30_11_PERMITTED_SCOPE_NOTE: Tuple[str, ...] = (
    (
        "Stage 30.11 runtime slices MAY compose the committed live surfaces "
        "behind the dip gate"
    ),
    (
        "the Stage 30.11.0 spec-lock files import nothing (this manifest is "
        "constants-only)"
    ),
    "per-slice permitted-import allowlists are pinned when each slice lands",
    "Stage 30.11 wires + composes; it never forks or reimplements",
    "Stage 30.11 adds no new provider, no new runner, no new readiness gate",
    "Stage 30.11 never widens routing beyond the private operator route",
)


# ---------------------------------------------------------------------------
# Dip-gate decision tokens (mirrored BY VALUE from the committed Stage 30.9.3
# seam; this manifest imports no Stage 30.9 / 30.10 module)
# ---------------------------------------------------------------------------
#
# Exactly one gate decision per evaluated live candidate. ``PASS_TO_DISPATCH``
# is the only decision that reserves a dispatch / drives the private send;
# ``SKIP_BEFORE_DISPATCH`` cleanly suppresses a non-dip BEFORE reservation
# (NOT a dispatch failure, NOT a transport veto); ``INVALID_INPUT`` fails
# closed on a malformed candidate.


STAGE30_11_GATE_DECISIONS: Tuple[str, ...] = (
    "PASS_TO_DISPATCH",
    "SKIP_BEFORE_DISPATCH",
    "INVALID_INPUT",
)


# The single decision that reserves a dispatch / drives the private send.
STAGE30_11_GATE_PASS_DECISION: str = "PASS_TO_DISPATCH"


# ---------------------------------------------------------------------------
# Live result counter axes (mirrored BY VALUE from the committed Stage 30.9.3
# integration result; the live wiring tallies these over a bounded run)
# ---------------------------------------------------------------------------
#
# ``dispatch_failures_recorded`` / ``transport_veto_count`` /
# ``payload_refused_count`` are ALWAYS 0 for a dip-gated skip (a non-dip is
# suppressed BEFORE reservation; it is never a dispatch failure / transport
# veto / PAYLOAD_REFUSED). ``created_at_utc`` is caller-injected on the
# offline proof; the live wiring stamps a bounded-run timestamp. NONE is a
# secret, a raw payload, a host, or a transport destination.


STAGE30_11_RESULT_COUNTER_AXES: Tuple[str, ...] = (
    "candidates_seen",
    "candidates_evaluated",
    "candidates_passed_gate",
    "candidates_skipped_before_dispatch",
    "invalid_inputs",
    "dispatch_attempts_reserved",
    "dispatch_failures_recorded",
    "transport_veto_count",
    "payload_refused_count",
    "private_discord_sends",
    "created_at_utc",
)


# The counter axes that are ALWAYS 0 for a dip-gated pre-dispatch skip.
STAGE30_11_ALWAYS_ZERO_AXES: Tuple[str, ...] = (
    "dispatch_failures_recorded",
    "transport_veto_count",
    "payload_refused_count",
)


# ---------------------------------------------------------------------------
# Failure behavior (fail-closed, locked)
# ---------------------------------------------------------------------------


STAGE30_11_FAILURE_BEHAVIOR: Tuple[str, ...] = (
    "readiness failure => no provider call, no Discord send",
    "non-PASS candidate => suppressed BEFORE reservation, no send",
    "invalid candidate => INVALID_INPUT, no reservation, no send",
    "provider failure => bounded, no crash",
    "Discord failure => closed-set transport failure, no crash",
    "dispatch / private-send cap reached => clean bounded stop",
    "max_runtime_seconds elapsed => clean bounded stop",
    "non-dip skip is never a dispatch failure / transport veto / PAYLOAD_REFUSED",
    "fail closed on any unknown / missing input, never fail open",
)


# ---------------------------------------------------------------------------
# Stage 30.9.2 / 30.9.3 relationship (locked)
# ---------------------------------------------------------------------------


STAGE30_11_STAGE_30_9_RELATIONSHIP: str = (
    "Stage 30.9.3 committed the pure / offline dip-gate seam; Stage 30.11 "
    "wires it into the live path and proves it offline before the controlled "
    "live ceremony resumes"
)
STAGE30_11_STAGE_30_9_2_STATUS: str = "paused, not abandoned"


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.11 family (and the Stage 30.11.0 spec-lock slice)
# must not touch. Plain documentation words (family / feature names), NOT
# secret / host / transport needle forms.


STAGE30_11_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "new live runner",
    "new provider",
    "new readiness gate",
    "direct Stage 28 suppression-logic edit",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "ungated Stage 29.3 send path reused directly",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / signing",
    "enforcement activation",
    "auto-buy",
    "strategy execution",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "default storage root",
    "broad always-on daemon",
    "background service",
    "autorestart loop",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "commit",
    "tag",
    "push",
    "Stage 30.11.1+ implementation file",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.11.0 pin test walks the actual import lines of the Stage
# 30.11.0 Python files (this manifest + the pin test) and asserts none
# resolve to a module covered by this policy. The strings below are plain
# (the line-based scan never substring-matches them against source text).
# This forbidden-import policy applies to the Stage 30.11.0 SPEC-LOCK files
# only; the future Stage 30.11.1+ runtime slices carry their own per-slice
# permitted-import allowlists (the permitted scope expansion above).


STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces the Stage 30.11.0 spec-lock files must not touch.
    "import os",
    "from os.",
    "os.environ",
    "os.getenv",
    "os.environb",
    "import dotenv",
    "from dotenv",
    "import keyring",
    "from keyring",
    "import requests",
    "from requests",
    "import httpx",
    "from httpx",
    "import aiohttp",
    "from aiohttp",
    "import urllib",
    "from urllib",
    "import socket",
    "from socket",
    "import grpc",
    "from grpc",
    "import http",
    "from http",
    "import websocket",
    "import websockets",
    "import sqlite3",
    "from sqlite3",
    # No zstd implementation / dependency at Stage 30.11.0 (docs + tests may
    # name the WORD ``zstd``; no module import is allowed).
    "import zstandard",
    "from zstandard",
    "import zstd",
    "from zstd",
    # Stage 21-29 production surfaces (incl. Stage 29.5). The spec-lock files
    # import none of these; the future runtime slices carry their own
    # per-slice allowlists.
    "from PHX2.stage21",
    "from PHX2.stage22",
    "from PHX2.stage23",
    "from PHX2.stage24",
    "from PHX2.stage25",
    "from PHX2.stage26",
    "from PHX2.stage27",
    "from PHX2.stage28",
    "from PHX2.stage29",
    "import PHX2.stage21",
    "import PHX2.stage22",
    "import PHX2.stage23",
    "import PHX2.stage24",
    "import PHX2.stage25",
    "import PHX2.stage26",
    "import PHX2.stage27",
    "import PHX2.stage28",
    "import PHX2.stage29",
    # PHX1 / legacy.
    "from PHX1",
    "import PHX1",
)


# ---------------------------------------------------------------------------
# Forbidden text needles (already-lowercased; scan must lowercase the
# haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so this
# manifest source text itself does NOT carry the bare needle. The Stage
# 30.11.0 pin test imports this tuple at runtime and scans every Stage
# 30.11.0 file (spec lock, manifest, test) case-insensitively for substring
# matches against the runtime-concatenated values. The spec doc paraphrases
# every secret / transport surface (for example "provider credential",
# "private transport destination", "transport scheme prefix") so it carries
# none of the bare needles.


STAGE30_11_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "endpoint" + " url",
    "endpoint" + "_secret",
    "raw" + "_body",
    "response" + "_body",
    "head" + "ers",
    "author" + "ization",
    "b" + "earer",
    "api" + " key",
    "api_" + "key",
    "x-api-" + "key",
    "x-" + "token",
    "public-api.birdeye" + ".so",
    "dex" + "screener.com",
    "chain" + "stack",
    "hel" + "ius",
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
)


# ---------------------------------------------------------------------------
# Stage 30.11.1 -- offline live-candidate -> Stage30_9_3LiveGateInput assembly
# bridge (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.1 is the FIRST Stage 30.11 production slice: the offline
# live-candidate assembly bridge with fakes / offline tests only. It adds three
# NEW production files -- the passive bridge models (the Stage 30.11-owned
# already-assembled live candidate snapshot + the per-candidate bridge result
# carrying the committed Stage 30.9.3 live gate input + the rolled-up proof
# summary), the pure bridge (which maps an already-assembled snapshot's
# present fields ONE-TO-ONE onto a committed Stage 30.9.3
# ``Stage30_9_3LiveGateInput``, failing closed on a blank id / missing
# context), and the offline fake bridge proof (which tallies the bridge over a
# deterministic five-candidate stream and OPTIONALLY feeds the bridged inputs
# into the committed Stage 30.9.3 gate to prove compatibility WITHOUT
# dispatching). It is the missing assembly link the prior controlled live
# ceremony lacked. It ships NO runtime wiring, NO runtime gate seam, NO real
# dispatch sink, NO dispatch reservation, NO live provider call, NO Discord
# send, NO env read, and edits NO existing live runner / orchestrator /
# transport / Stage 28 suppression / Stage 29 live provider file. Unlike the
# offline-only Stage 30.9.x / 30.10.x slices, Stage 30.11.1 IS permitted to
# compose the committed Stage 30.9.3 surfaces (the permitted scope expansion):
# the bridge models embed the Stage 30.9.3 live gate input, and the fake proof
# composes the Stage 30.9.3 dip-gate adapter; no Stage 21-29 / live runner /
# provider / transport module is imported. NO Stage 30.11.2+ file ships at
# Stage 30.11.1.


STAGE30_11_1_MINOR_VERSION: str = "30.11.1"


# The Stage 30.11.1 live-candidate assembly bridge schema version (mirrored BY
# VALUE by the Stage 30.11.1 bridge-models module; a pin test cross-checks it
# matches). Distinct from the Stage 30.9.3 integration schema version and the
# Stage 30.10.3 artifact schema version.
STAGE30_11_1_BRIDGE_SCHEMA_VERSION: str = (
    "stage30_11_1_v0_live_candidate_bridge"
)


# The three NEW production basenames + their dotted module paths.
STAGE30_11_1_BRIDGE_MODELS_BASENAME: str = (
    "stage30_11_1_live_candidate_bridge_models.py"
)
STAGE30_11_1_BRIDGE_BASENAME: str = "stage30_11_1_live_candidate_bridge.py"
STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME: str = (
    "stage30_11_1_fake_bridge_proof.py"
)


STAGE30_11_1_BRIDGE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
)
STAGE30_11_1_BRIDGE_MODULE: str = (
    "PHX2.stage30.stage30_11_1_live_candidate_bridge"
)
STAGE30_11_1_FAKE_BRIDGE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_1_fake_bridge_proof"
)


# The ALREADY-COMMITTED Stage 30.9.3 sibling module paths the Stage 30.11.1
# bridge composes (re-declared here as literals; the manifest imports no PHX2
# module). The bridge models embed the gate-input model; the fake proof
# composes the dip-gate adapter. These are the committed live-gate surfaces the
# Stage 30.11 wiring is explicitly permitted to compose behind the dip gate.
STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
)
STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
)


# The three NEW production files Stage 30.11.1 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.11.0 inventory. NO Stage 30.11.2+
# file.
STAGE30_11_1_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_1_BRIDGE_MODELS_BASENAME,
    STAGE30_11_1_BRIDGE_BASENAME,
    STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
)


# The three production modules the Stage 30.11.1 boundary test scans for
# forbidden imports / text needles.
STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_1_BRIDGE_MODELS_BASENAME,
    STAGE30_11_1_BRIDGE_BASENAME,
    STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME,
)


STAGE30_11_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_1_live_candidate_bridge_models.py",
    "test_stage_30_11_1_live_candidate_bridge.py",
    "test_stage_30_11_1_fake_bridge_proof.py",
    "test_stage_30_11_1_boundaries.py",
    "test_stage_30_11_1_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.1 production module must be in this
# stdlib allowlist (the models need ``dataclasses`` / ``decimal``; the bridge
# needs ``typing``; the fake proof needs ``decimal`` / ``typing``). It admits
# NO ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO ``sqlite3``, NO
# ``zstd`` / compression, and NO network module.
STAGE30_11_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.1 production module must be one of these
# siblings: the Stage 30.11.1 bridge-models + bridge siblings plus the
# committed Stage 30.9.3 integration-models + dip-gate-adapter siblings the
# bridge composes. This positive allowlist proves, by construction, that NO
# Stage 21-29 (incl. Stage 28 suppression / Stage 29.5) / runtime orchestrator
# / renderer / transport / Discord / live provider module is imported (the
# bridge composes ONLY the committed Stage 30.9.3 offline surfaces).
STAGE30_11_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_1_BRIDGE_MODULE,
    STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE,
)


# Closed-set bridge decision tokens (mirrored BY VALUE from the Stage 30.11.1
# bridge-models module). ``BRIDGED_TO_LIVE_GATE_INPUT`` is the only decision
# that carries a built Stage 30.9.3 live gate input; the other two carry
# ``None``.
STAGE30_11_1_BRIDGE_DECISIONS: Tuple[str, ...] = (
    "BRIDGED_TO_LIVE_GATE_INPUT",
    "SKIPPED_MISSING_REQUIRED_CONTEXT",
    "INVALID_BRIDGE_INPUT",
)


# The single decision that yields a built Stage 30.9.3 live gate input.
STAGE30_11_1_BRIDGE_PASS_DECISION: str = "BRIDGED_TO_LIVE_GATE_INPUT"


# Closed-set bridge reason tokens (mirrored BY VALUE from the Stage 30.11.1
# bridge-models module).
STAGE30_11_1_BRIDGE_REASONS: Tuple[str, ...] = (
    "READY_FOR_DIP_GATE",
    "MISSING_REQUIRED_CONTEXT",
    "INVALID_FIELD_SHAPE",
)


# The Stage 30.11.1 candidate snapshot / bridge result / bridge proof summary
# field names (mirrored BY VALUE from the Stage 30.11.1 bridge-models module;
# a pin test cross-checks them). ``created_at_utc`` is caller-injected, never a
# wall-clock read; NONE is a secret, a raw payload, a host, or a transport
# destination.
STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "post_migration_ath_verified",
    "source_ref",
    "created_at_utc",
)
STAGE30_11_1_BRIDGE_RESULT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "bridge_decision",
    "bridge_reason",
    "live_gate_input",
    "created_at_utc",
)
STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS: Tuple[str, ...] = (
    "candidates_seen",
    "bridged",
    "skipped_missing_context",
    "invalid_inputs",
    "created_at_utc",
)


# The author-verified expected Stage 30.11.1 fake bridge proof counts over the
# deterministic five-candidate default stream: five candidates seen, exactly
# two bridged into a committed Stage 30.9.3 live gate input (a Tier 1 dip-
# context candidate + a Tier Unknown non-dip-context candidate -- the non-dip
# decision is the GATE's, made LATER, not the bridge's), exactly two skipped
# for missing required context (missing ATH + missing migration), and exactly
# one invalid (a blank candidate id). The bridge reserves NO dispatch and
# sends NO Discord.
STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN: int = 5
STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED: int = 2
STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT: int = 2
STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS: int = 1


# After Stage 30.11.1 (the offline assembly bridge) the next allowed slice is
# Stage 30.11.2 (the runtime gate seam with fakes only, separately operator-
# gated). The Stage 30.11.0 family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE``
# stays pinned at ``30.11.1``; this 30.11.1-scoped pointer names the slice that
# follows. NO Stage 30.11.2 file ships at Stage 30.11.1.
STAGE30_11_1_NEXT_ALLOWED_STAGE: str = "30.11.2"
STAGE30_11_1_NEXT_ALLOWED_STAGE_TITLE: str = (
    "runtime gate seam with fakes only (run the committed dip gate over each "
    "live-assembled candidate inside the bounded session; reserve a dispatch "
    "ONLY for a PASS candidate; enforce a wall-clock max_runtime_seconds "
    "bound; fake provider + fake transport only)"
)


# The surfaces the Stage 30.11.1 assembly-bridge slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host / transport
# needle forms. The bridge ONLY assembles a gate input; it must not reach any
# surface below.
STAGE30_11_1_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "runtime gate seam",
    "run the dip gate inside the bridge",
    "real dispatch sink",
    "dispatch reservation",
    "dispatch sink call",
    "runtime session loop",
    "live run",
    "live provider call",
    "Discord send",
    "env read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "ungated Stage 29.3 send path reused directly",
    "filesystem write",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "default storage root",
    "broad always-on daemon",
    "background service",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / signing",
    "enforcement activation",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.2+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.1 implements no
# part of it; it only assembles the gate input the ceremony will later gate).
STAGE30_11_1_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_1_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.1 is the offline assembly bridge only; the controlled dip-"
    "filtered private compact live ceremony remains a separate, explicitly "
    "operator-authorized step that is not run here"
)


# ---------------------------------------------------------------------------
# Stage 30.11.2 -- offline runtime gate seam + max_runtime_seconds (fakes /
# offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.2 is the SECOND Stage 30.11 production slice: the offline runtime
# gate seam with fakes / offline tests only. It adds three NEW production files
# -- the passive runtime models (the bounded-runtime config + the per-candidate
# runtime outcome + the rolled-up runtime summary + the fake dispatch
# acknowledgement result + the closed-set runtime decision / reason
# vocabularies), the pure runtime seam (which, per already-assembled candidate,
# composes the committed Stage 30.11.1 bridge -> the committed Stage 30.9.3 dip
# gate -> an INJECTED fake dispatch sink that is reachable ONLY behind a gate
# PASS, while enforcing the wall-clock max_runtime_seconds bound via an injected
# clock plus the max_candidates / max_dispatches count bounds), and the offline
# fake runtime gate proof (which runs the seam over a deterministic five-
# candidate stream with an in-memory recording sink + an injected fake clock).
# It adds the wall-clock runtime bound the bounded session lacked and proves --
# with fakes only -- that the dispatch sink is unreachable without a committed
# dip-gate PASS. It ships NO real dispatch sink, NO real Discord / webhook /
# transport wiring, NO dispatch reservation, NO live provider call, NO Discord
# send, NO env read, NO wall-clock read (the runtime clock is injected), NO
# daemon / background loop, and edits NO existing live runner / orchestrator /
# transport / Stage 28 suppression / Stage 29 live provider file. Unlike the
# offline-only Stage 30.9.x / 30.10.x slices, Stage 30.11.2 IS permitted to
# compose the committed live surfaces behind the dip gate (the permitted scope
# expansion): the seam composes the Stage 30.11.1 bridge + the Stage 30.9.3 dip
# gate; no Stage 21-29 / live runner / provider / transport module is imported.
# NO Stage 30.11.3+ file ships at Stage 30.11.2.


STAGE30_11_2_MINOR_VERSION: str = "30.11.2"


# The Stage 30.11.2 runtime gate seam schema version (mirrored BY VALUE by the
# Stage 30.11.2 runtime-gate-models module; a pin test cross-checks it matches).
# Distinct from the Stage 30.11.1 bridge schema version, the Stage 30.9.3
# integration schema version, and the Stage 30.10.3 artifact schema version.
STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION: str = (
    "stage30_11_2_v0_runtime_gate_seam"
)


# The three NEW production basenames + their dotted module paths.
STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME: str = (
    "stage30_11_2_runtime_gate_models.py"
)
STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME: str = (
    "stage30_11_2_runtime_gate_seam.py"
)
STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME: str = (
    "stage30_11_2_fake_runtime_gate_proof.py"
)


STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_models"
)
STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_seam"
)
STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
)


# The ALREADY-COMMITTED sibling module paths the Stage 30.11.2 seam composes
# (re-declared here as literals; the manifest imports no PHX2 module). The seam
# composes the Stage 30.11.1 bridge + bridge models, the Stage 30.9.3 dip-gate
# adapter + gate models, and the Stage 30.10.2 gate-decision token. These are the
# committed live-gate surfaces the Stage 30.11 wiring is explicitly permitted to
# compose behind the dip gate.
STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE: str = (
    "PHX2.stage30.stage30_11_1_live_candidate_bridge"
)
STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
)
STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
)
STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
)
STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models"
)


# The three NEW production files Stage 30.11.2 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.11.1 inventory. NO Stage 30.11.3+
# file.
STAGE30_11_2_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME,
    STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME,
    STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME,
)


# The three production modules the Stage 30.11.2 boundary test scans for
# forbidden imports / text needles.
STAGE30_11_2_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME,
    STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME,
    STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME,
)


STAGE30_11_2_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_2_runtime_gate_models.py",
    "test_stage_30_11_2_runtime_gate_seam.py",
    "test_stage_30_11_2_fake_runtime_gate_proof.py",
    "test_stage_30_11_2_boundaries.py",
    "test_stage_30_11_2_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.2 production module must be in this
# stdlib allowlist (the models need ``dataclasses`` / ``decimal``; the seam needs
# ``decimal`` / ``typing``; the fake proof needs ``decimal`` / ``typing``). It
# admits NO ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO
# ``sqlite3``, NO ``zstd`` / compression, NO network module, and NO ``time`` /
# ``datetime`` (the runtime clock is injected, never read).
STAGE30_11_2_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.2 production module must be one of these
# siblings: the Stage 30.11.2 own runtime-gate-models + seam siblings plus the
# committed Stage 30.11.1 bridge / bridge-models siblings, the committed Stage
# 30.9.3 dip-gate adapter / gate-models siblings, and the committed Stage 30.10.2
# gate-decision-token sibling the seam composes. This positive allowlist proves,
# by construction, that NO Stage 21-29 (incl. Stage 28 suppression / Stage 29.5 /
# Stage 29 live provider) / runtime orchestrator / renderer / transport / Discord
# / live provider module is imported (the seam composes ONLY the committed Stage
# 30.9.3 + Stage 30.10.2 + Stage 30.11.1 offline surfaces).
STAGE30_11_2_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE,
    STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE,
)


# Closed-set runtime decision tokens (mirrored BY VALUE from the Stage 30.11.2
# runtime-gate-models module). ``DISPATCHED_AFTER_DIP_GATE_PASS`` is the only
# decision on which the injected fake dispatch sink was called.
STAGE30_11_2_RUNTIME_DECISIONS: Tuple[str, ...] = (
    "DISPATCHED_AFTER_DIP_GATE_PASS",
    "SUPPRESSED_BY_BRIDGE",
    "SUPPRESSED_BY_DIP_GATE",
    "STOPPED_BY_CANDIDATE_CAP",
    "STOPPED_BY_DISPATCH_CAP",
    "STOPPED_BY_RUNTIME_SECONDS",
    "INVALID_RUNTIME_INPUT",
)


# The single runtime decision on which the injected fake dispatch sink was
# called.
STAGE30_11_2_RUNTIME_DISPATCH_DECISION: str = "DISPATCHED_AFTER_DIP_GATE_PASS"


# Closed-set runtime reason tokens (mirrored BY VALUE from the Stage 30.11.2
# runtime-gate-models module).
STAGE30_11_2_RUNTIME_REASONS: Tuple[str, ...] = (
    "PASS_TO_FAKE_DISPATCH",
    "BRIDGE_SKIPPED_OR_INVALID",
    "DIP_GATE_SKIPPED",
    "CANDIDATE_CAP_REACHED",
    "DISPATCH_CAP_REACHED",
    "RUNTIME_SECONDS_REACHED",
    "INVALID_CONFIG_OR_INPUT",
)


# The single runtime reason that accompanies the only dispatch decision.
STAGE30_11_2_RUNTIME_DISPATCH_REASON: str = "PASS_TO_FAKE_DISPATCH"


# The runtime-local not-evaluated sentinel for an outcome's bridge / gate
# decision axis where the bridge / gate was not run (a cap / runtime stop or a
# non-conforming stream item). NOT a Stage 30.11.1 bridge decision nor a Stage
# 30.9.3 / 30.10.2 gate decision.
STAGE30_11_2_NOT_EVALUATED: str = "NOT_EVALUATED"


# The Stage 30.11.2 config / outcome / summary / fake-result field names
# (mirrored BY VALUE from the Stage 30.11.2 runtime-gate-models module; a pin
# test cross-checks them). ``created_at_utc`` is caller-injected, never a
# wall-clock read; NONE is a secret, a raw payload, a host, or a transport
# destination.
STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS: Tuple[str, ...] = (
    "max_runtime_seconds",
    "max_candidates",
    "max_dispatches",
    "created_at_utc",
)
STAGE30_11_2_RUNTIME_OUTCOME_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "bridge_decision",
    "gate_decision",
    "runtime_decision",
    "runtime_reason",
    "dispatch_attempted",
    "dispatch_accepted",
    "created_at_utc",
)
STAGE30_11_2_RUNTIME_SUMMARY_FIELDS: Tuple[str, ...] = (
    "candidates_seen",
    "bridged",
    "gate_passed",
    "dispatch_attempted",
    "dispatch_accepted",
    "suppressed_by_bridge",
    "suppressed_by_gate",
    "stopped_by_candidate_cap",
    "stopped_by_dispatch_cap",
    "stopped_by_runtime_seconds",
    "invalid_inputs",
    "created_at_utc",
)
STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS: Tuple[str, ...] = (
    "accepted",
    "candidate_id",
    "token_mint",
    "created_at_utc",
)


# The author-verified expected Stage 30.11.2 fake runtime gate proof counts over
# the deterministic five-candidate default stream run with the permissive
# baseline config (so no cap / runtime bound is tripped): five candidates seen,
# exactly two bridged (the Tier 1 dip-context + the Tier Unknown non-dip-context
# candidate), exactly one passed the committed dip gate (the Tier 1 dip), exactly
# one fake dispatch attempted + accepted (the dip; the ONLY candidate the sink is
# called for), exactly three suppressed by the bridge (missing ATH + missing
# migration + invalid id), exactly one suppressed by the gate (the non-dip), and
# exactly one invalid input (the invalid id, which is also a bridge suppression).
# No real dispatch reserved; no Discord sent.
STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN: int = 5
STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED: int = 2
STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED: int = 1
STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED: int = 1
STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED: int = 1
STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE: int = 3
STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE: int = 1
STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS: int = 1


# After Stage 30.11.2 (the runtime gate seam) the next allowed slice is Stage
# 30.11.3 (the real dispatch sink adapter, separately operator-gated). The Stage
# 30.11.0 family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned at
# ``30.11.1``; this 30.11.2-scoped pointer names the slice that follows. NO Stage
# 30.11.3 file ships at Stage 30.11.2.
STAGE30_11_2_NEXT_ALLOWED_STAGE: str = "30.11.3"
STAGE30_11_2_NEXT_ALLOWED_STAGE_TITLE: str = (
    "real dispatch sink adapter (compose the committed private ping + audited "
    "transport as the seam's dispatch sink, invoked ONLY for a PASS candidate; "
    "still proven with fakes -- the live ceremony is a separate operator-"
    "authorized step)"
)


# The surfaces the Stage 30.11.2 runtime-gate-seam slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host / transport
# needle forms. The seam ONLY composes the committed bridge + dip gate + an
# injected fake sink; it must not reach any surface below.
STAGE30_11_2_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "real dispatch sink",
    "real dispatch sink wiring",
    "dispatch reservation",
    "real Discord send",
    "Discord send",
    "live run",
    "live provider call",
    "env read",
    "wall-clock read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "ungated Stage 29.3 send path reused directly",
    "daemon",
    "background service",
    "autorestart loop",
    "unbounded loop",
    "filesystem write",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "default storage root",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / signing",
    "enforcement activation",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.3+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.2 implements no part
# of it; it only proves the bounded runtime seam composes the committed bridge +
# dip gate behind an injected fake sink).
STAGE30_11_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_2_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.2 is the offline runtime gate seam only; the controlled dip-"
    "filtered private compact live ceremony remains a separate, explicitly "
    "operator-authorized step that is not run here"
)


# ---------------------------------------------------------------------------
# Stage 30.11.3 -- private sink adapter (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.3 is the THIRD Stage 30.11 production slice: the private sink
# adapter boundary the Stage 30.11.2 runtime seam reaches ONLY behind a committed
# dip-gate PASS, proven with fakes / offline tests only. It adds three NEW
# production files -- the passive private sink models (the adapter-side private
# sink request derived from a committed Stage 30.9.3 live gate input + the
# per-call private sink result + the rolled-up private sink proof summary + the
# closed-set sink decision / reason vocabularies), the pure private sink adapter
# (which validates a PASS gate input, builds a SAFE compact operator body via an
# injected builder, builds a private sink request, and hands it to an INJECTED
# transport that is reachable ONLY for a well-shaped input -- plus a thin
# seam-compatibility wrapper that maps the rich private sink result onto the
# committed Stage 30.11.2 fake-dispatch-result type so the committed seam stays
# untouched), and the offline fake private sink proof (a direct three-call sink
# proof + a runtime seam integration proof, both driven by an in-memory recording
# FAKE transport). It proves -- with fakes only -- that the private sink boundary
# is reachable ONLY for a PASS candidate and that the recording fake transport is
# attempted ONLY for the dip. It ships NO real transport, NO real Discord /
# webhook send, NO dispatch reservation, NO live provider call, NO Discord send,
# NO env read, NO wall-clock read, NO daemon / background loop, and edits NO
# existing live runner / orchestrator / transport / Stage 28 suppression / Stage
# 29 live provider file. Unlike the offline-only Stage 30.9.x / 30.10.x slices,
# Stage 30.11.3 IS permitted to compose the committed live surfaces behind the dip
# gate (the permitted scope expansion): the adapter composes the Stage 30.9.3
# gate-input type + the Stage 30.11.2 fake-dispatch-result type, and the fake
# proof composes the Stage 30.11.2 runtime seam + its deterministic fake stream;
# no Stage 21-29 / live runner / provider / real transport module is imported. NO
# Stage 30.11.4+ file ships at Stage 30.11.3.


STAGE30_11_3_MINOR_VERSION: str = "30.11.3"


# The Stage 30.11.3 private sink adapter schema version (mirrored BY VALUE by the
# Stage 30.11.3 private-sink-models module; a pin test cross-checks it matches).
# Distinct from the Stage 30.11.2 runtime gate schema version, the Stage 30.11.1
# bridge schema version, and the Stage 30.9.3 integration schema version.
STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION: str = (
    "stage30_11_3_v0_private_sink_adapter"
)


# The safe-shape source-stage provenance token stamped onto every built private
# sink request (mirrored BY VALUE by the Stage 30.11.3 models module).
STAGE30_11_3_SOURCE_STAGE: str = "30.11.3"


# The three NEW production basenames + their dotted module paths.
STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME: str = (
    "stage30_11_3_private_sink_models.py"
)
STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME: str = (
    "stage30_11_3_private_sink_adapter.py"
)
STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME: str = (
    "stage30_11_3_fake_private_sink_proof.py"
)


STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_models"
)
STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_adapter"
)
STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_3_fake_private_sink_proof"
)


# The ALREADY-COMMITTED sibling module paths the Stage 30.11.3 slice composes
# (re-declared here as literals; the manifest imports no PHX2 module). The
# adapter composes the Stage 30.9.3 gate-input model + the Stage 30.11.2
# fake-dispatch-result model; the fake proof additionally composes the Stage
# 30.11.2 runtime seam + its deterministic fake stream / clock / config. These
# are the committed live-gate surfaces the Stage 30.11 wiring is explicitly
# permitted to compose behind the dip gate.
STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
)
STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_models"
)
STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_seam"
)
STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
)


# The three NEW production files Stage 30.11.3 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.11.2 inventory. NO Stage 30.11.4+
# file.
STAGE30_11_3_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
    STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
)


# The three production modules the Stage 30.11.3 boundary test scans for
# forbidden imports / text needles.
STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
    STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
)


STAGE30_11_3_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_3_private_sink_models.py",
    "test_stage_30_11_3_private_sink_adapter.py",
    "test_stage_30_11_3_fake_private_sink_proof.py",
    "test_stage_30_11_3_boundaries.py",
    "test_stage_30_11_3_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.3 production module must be in this
# stdlib allowlist (the models need ``dataclasses`` / ``typing``; the adapter
# needs ``typing``; the fake proof needs ``decimal`` / ``typing``). It admits NO
# ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO ``sqlite3``, NO
# ``zstd`` / compression, NO network module, and NO ``time`` / ``datetime`` (the
# runtime clock is injected, never read).
STAGE30_11_3_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.3 production module must be one of these
# siblings: the Stage 30.11.3 own private-sink-models + adapter siblings plus the
# committed Stage 30.9.3 gate-models sibling and the committed Stage 30.11.2
# runtime-gate-models + seam + fake-proof siblings the slice composes. This
# positive allowlist proves, by construction, that NO Stage 21-29 (incl. Stage 28
# suppression / Stage 29.5 / Stage 29 live provider) / runtime orchestrator /
# renderer / real transport / Discord / live provider module is imported (the
# slice composes ONLY the committed Stage 30.9.3 + Stage 30.11.2 offline
# surfaces).
STAGE30_11_3_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
)


# Closed-set private sink decision tokens (mirrored BY VALUE from the Stage
# 30.11.3 private-sink-models module). ``PRIVATE_SINK_ACCEPTED`` is the only
# decision on which the injected fake transport accepted a built request.
STAGE30_11_3_PRIVATE_SINK_DECISIONS: Tuple[str, ...] = (
    "PRIVATE_SINK_ACCEPTED",
    "PRIVATE_SINK_REJECTED_INVALID_INPUT",
    "PRIVATE_SINK_TRANSPORT_FAILED",
)


# The single decision on which the injected fake transport accepted a built
# request (a recorded would-send).
STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION: str = "PRIVATE_SINK_ACCEPTED"


# Closed-set private sink reason tokens (mirrored BY VALUE from the Stage 30.11.3
# private-sink-models module). ``WOULD_SEND_PRIVATE_OPERATOR_MESSAGE`` names a
# RECORDED would-send (the fake transport recorded the request), NEVER a real
# send.
STAGE30_11_3_PRIVATE_SINK_REASONS: Tuple[str, ...] = (
    "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE",
    "INVALID_SINK_INPUT",
    "FAKE_TRANSPORT_REJECTED",
)


# The single reason that accompanies the only accept decision.
STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON: str = (
    "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE"
)


# The Stage 30.11.3 request / result / summary field names (mirrored BY VALUE
# from the Stage 30.11.3 private-sink-models module; a pin test cross-checks
# them). ``created_at_utc`` is caller-injected, never a wall-clock read; NONE is
# a secret, a raw payload, a host, or a transport destination.
STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "candidate_ref",
    "tier_token",
    "compact_body",
    "created_at_utc",
    "source_stage",
)
STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "sink_decision",
    "sink_reason",
    "transport_attempted",
    "transport_accepted",
    "created_at_utc",
)
STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS: Tuple[str, ...] = (
    "requests_seen",
    "accepted",
    "rejected_invalid",
    "transport_failed",
    "transport_attempted",
    "transport_accepted",
    "created_at_utc",
)


# The author-verified expected Stage 30.11.3 fake private sink proof counts. The
# direct three-call sink proof drives one valid-accept, one blank-id invalid, and
# one valid-reject input through the private sink: three requests seen, exactly
# one accepted (the valid accept), exactly one rejected-invalid (the blank id,
# which never reaches the transport), exactly one transport-failed (the valid
# reject), exactly two transport attempts (the two valid inputs), and exactly one
# transport accept. The runtime seam integration proof runs the committed Stage
# 30.11.2 seam over the first three default candidates (a dip, a non-dip, a
# bridge-skip) with the Stage 30.11.3 private sink injected, and the recording
# fake transport records exactly one attempt -- for the dip only. No real
# dispatch reserved; no Discord sent.
STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN: int = 3
STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED: int = 1
STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID: int = 1
STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED: int = 1
STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED: int = 2
STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED: int = 1
STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS: int = 1


# After Stage 30.11.3 (the private sink adapter) the next allowed slice is Stage
# 30.11.4 (the offline end-to-end proof, separately operator-gated). The Stage
# 30.11.0 family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned at
# ``30.11.1``; this 30.11.3-scoped pointer names the slice that follows. NO Stage
# 30.11.4 file ships at Stage 30.11.3.
STAGE30_11_3_NEXT_ALLOWED_STAGE: str = "30.11.4"
STAGE30_11_3_NEXT_ALLOWED_STAGE_TITLE: str = (
    "offline end-to-end proof (fake provider -> assembly -> committed dip gate "
    "-> fake sink; proves only-PASS dispatches + the caps + the wall-clock "
    "bound -- the runtime counterpart of the Stage 30.10.3 fake artifact proof)"
)


# The surfaces the Stage 30.11.3 private-sink-adapter slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host / transport
# needle forms. The slice ONLY translates a PASS gate input into a private sink
# request and hands it to an INJECTED fake transport; it must not reach any
# surface below.
STAGE30_11_3_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "real transport call",
    "real Discord send",
    "Discord send",
    "real private webhook send",
    "real dispatch reservation",
    "live run",
    "live provider call",
    "env read",
    "wall-clock read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "ungated Stage 29.3 send path reused directly",
    "daemon",
    "background service",
    "autorestart loop",
    "unbounded loop",
    "filesystem write",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "default storage root",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / signing",
    "enforcement activation",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "Stage 28 transport-internals edit",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.4+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.3 implements no part
# of it; it only proves the private sink boundary the runtime seam reaches behind
# the committed dip gate, with an injected fake transport).
STAGE30_11_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_3_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.3 is the offline private sink adapter only; the controlled dip-"
    "filtered private compact live ceremony remains a separate, explicitly "
    "operator-authorized step that is not run here"
)


__all__ = (
    # Stage id + minor version + spec version.
    "STAGE30_11_STAGE_ID",
    "STAGE30_11_0_MINOR_VERSION",
    "STAGE30_11_0_SPEC_VERSION",
    # Locked basenames + path parts + inventory delta.
    "STAGE30_11_SPEC_LOCK_FILENAME",
    "STAGE30_11_MANIFEST_BASENAME",
    "STAGE30_11_SPEC_LOCK_PATH_PARTS",
    "STAGE30_11_0_TEST_BASENAMES",
    "STAGE30_11_ALLOWED_INITIAL_FILES",
    "STAGE30_11_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_ALLOWED_STDLIB_IMPORTS",
    # Planned substages + next allowed stage + roadmap.
    "STAGE30_11_PLANNED_SUBSTAGES",
    "STAGE30_11_NEXT_ALLOWED_STAGE",
    "STAGE30_11_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_SUBSTAGE_ROADMAP",
    # Purpose.
    "STAGE30_11_PURPOSE",
    # Why-now finding.
    "STAGE30_11_WHY_NOW_FINDINGS",
    # Gate placement.
    "STAGE30_11_GATE_PLACEMENT",
    # Only-PASS real-send rule.
    "STAGE30_11_ONLY_PASS_SEND_RULE",
    # Required wall-clock runtime bound.
    "STAGE30_11_RUNTIME_BOUND",
    # Existing reuse surfaces.
    "STAGE30_11_EXISTING_REUSE_SURFACES",
    # Permitted scope expansion.
    "STAGE30_11_PERMITTED_SCOPE_NOTE",
    # Dip-gate decision tokens + pass token.
    "STAGE30_11_GATE_DECISIONS",
    "STAGE30_11_GATE_PASS_DECISION",
    # Live result counter axes + always-zero axes.
    "STAGE30_11_RESULT_COUNTER_AXES",
    "STAGE30_11_ALWAYS_ZERO_AXES",
    # Failure behavior.
    "STAGE30_11_FAILURE_BEHAVIOR",
    # Stage 30.9.2 / 30.9.3 relationship.
    "STAGE30_11_STAGE_30_9_RELATIONSHIP",
    "STAGE30_11_STAGE_30_9_2_STATUS",
    # Forbidden surfaces.
    "STAGE30_11_FORBIDDEN_SURFACES",
    # Forbidden imports + needles.
    "STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    # ---- Stage 30.11.1 assembly bridge ----
    # Minor version + bridge schema identity.
    "STAGE30_11_1_MINOR_VERSION",
    "STAGE30_11_1_BRIDGE_SCHEMA_VERSION",
    # Basenames + module paths.
    "STAGE30_11_1_BRIDGE_MODELS_BASENAME",
    "STAGE30_11_1_BRIDGE_BASENAME",
    "STAGE30_11_1_FAKE_BRIDGE_PROOF_BASENAME",
    "STAGE30_11_1_BRIDGE_MODELS_MODULE",
    "STAGE30_11_1_BRIDGE_MODULE",
    "STAGE30_11_1_FAKE_BRIDGE_PROOF_MODULE",
    "STAGE30_11_1_STAGE30_9_3_GATE_MODELS_MODULE",
    "STAGE30_11_1_STAGE30_9_3_GATE_ADAPTER_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_1_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_1_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_1_ALLOWED_PHX2_IMPORTS",
    # Bridge decisions + reasons.
    "STAGE30_11_1_BRIDGE_DECISIONS",
    "STAGE30_11_1_BRIDGE_PASS_DECISION",
    "STAGE30_11_1_BRIDGE_REASONS",
    # Model field tuples.
    "STAGE30_11_1_CANDIDATE_SNAPSHOT_FIELDS",
    "STAGE30_11_1_BRIDGE_RESULT_FIELDS",
    "STAGE30_11_1_BRIDGE_PROOF_SUMMARY_FIELDS",
    # Fake proof expected counts.
    "STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED",
    "STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT",
    "STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
    # Next allowed stage + forbidden surfaces + live ceremony note.
    "STAGE30_11_1_NEXT_ALLOWED_STAGE",
    "STAGE30_11_1_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_1_FORBIDDEN_SURFACES",
    "STAGE30_11_1_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_1_LIVE_CEREMONY_NOTE",
    # ---- Stage 30.11.2 runtime gate seam ----
    # Minor version + runtime gate schema identity.
    "STAGE30_11_2_MINOR_VERSION",
    "STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION",
    # Basenames + module paths.
    "STAGE30_11_2_RUNTIME_GATE_MODELS_BASENAME",
    "STAGE30_11_2_RUNTIME_GATE_SEAM_BASENAME",
    "STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_BASENAME",
    "STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE",
    "STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
    "STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
    "STAGE30_11_2_STAGE30_11_1_BRIDGE_MODULE",
    "STAGE30_11_2_STAGE30_11_1_BRIDGE_MODELS_MODULE",
    "STAGE30_11_2_STAGE30_9_3_GATE_ADAPTER_MODULE",
    "STAGE30_11_2_STAGE30_9_3_GATE_MODELS_MODULE",
    "STAGE30_11_2_STAGE30_10_2_GATE_MODELS_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_2_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_2_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_2_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_2_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_2_ALLOWED_PHX2_IMPORTS",
    # Runtime decisions + reasons + sentinel.
    "STAGE30_11_2_RUNTIME_DECISIONS",
    "STAGE30_11_2_RUNTIME_DISPATCH_DECISION",
    "STAGE30_11_2_RUNTIME_REASONS",
    "STAGE30_11_2_RUNTIME_DISPATCH_REASON",
    "STAGE30_11_2_NOT_EVALUATED",
    # Model field tuples.
    "STAGE30_11_2_RUNTIME_GATE_CONFIG_FIELDS",
    "STAGE30_11_2_RUNTIME_OUTCOME_FIELDS",
    "STAGE30_11_2_RUNTIME_SUMMARY_FIELDS",
    "STAGE30_11_2_FAKE_DISPATCH_RESULT_FIELDS",
    # Fake proof expected counts.
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE",
    "STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
    # Next allowed stage + forbidden surfaces + live ceremony note.
    "STAGE30_11_2_NEXT_ALLOWED_STAGE",
    "STAGE30_11_2_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_2_FORBIDDEN_SURFACES",
    "STAGE30_11_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_2_LIVE_CEREMONY_NOTE",
    # ---- Stage 30.11.3 private sink adapter ----
    # Minor version + private sink schema identity.
    "STAGE30_11_3_MINOR_VERSION",
    "STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION",
    "STAGE30_11_3_SOURCE_STAGE",
    # Basenames + module paths.
    "STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME",
    "STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME",
    "STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME",
    "STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE",
    "STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE",
    "STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE",
    "STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE",
    "STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE",
    "STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
    "STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_3_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_3_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_3_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_3_ALLOWED_PHX2_IMPORTS",
    # Sink decisions + reasons.
    "STAGE30_11_3_PRIVATE_SINK_DECISIONS",
    "STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION",
    "STAGE30_11_3_PRIVATE_SINK_REASONS",
    "STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON",
    # Model field tuples.
    "STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS",
    "STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS",
    "STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS",
    # Fake proof expected counts.
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED",
    "STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS",
    # Next allowed stage + forbidden surfaces + live ceremony note.
    "STAGE30_11_3_NEXT_ALLOWED_STAGE",
    "STAGE30_11_3_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_3_FORBIDDEN_SURFACES",
    "STAGE30_11_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_3_LIVE_CEREMONY_NOTE",
)
