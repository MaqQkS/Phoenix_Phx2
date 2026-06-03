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


# ---------------------------------------------------------------------------
# Stage 30.11.4 -- offline end-to-end proof (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.4 is the FOURTH (and final planned) Stage 30.11 production slice:
# the offline END-TO-END proof that COMPOSES the committed Stage 30.11.1 bridge +
# Stage 30.11.2 runtime gate seam + committed Stage 30.9.3 dip gate + Stage
# 30.11.3 private sink adapter behind an INJECTED in-memory recording FAKE
# private transport, proven with fakes / offline tests only. It adds two NEW
# production files -- the passive end-to-end proof models (the rolled-up
# end-to-end proof summary carrying the chain counters + the proof verdict, the
# end-to-end proof result carrying the verdict + summary + the recorded runtime
# outcomes + the safe-shape transport identities, and the closed-set proof
# decision / reason vocabularies, importing no PHX2 module) and the pure proof
# (which composes the committed Stage 30.11.2 default stream -> the committed
# runtime seam -> the committed dip gate -> the committed Stage 30.11.3 private
# sink wrapped for seam compatibility -> an INJECTED recording fake transport,
# folds the recorded private sink results via the committed Stage 30.11.3 fold,
# and judges the composed run against the author-verified baseline). It is the
# runtime counterpart of the Stage 30.10.3 fake artifact proof -- the FINAL fake
# / offline proof before the controlled live ceremony. It REIMPLEMENTS none of
# the composed slices (no new bridge / gate / runtime seam / sink adapter), ships
# NO real transport, NO real Discord / private send, NO dispatch reservation, NO
# live provider call, NO Discord send, NO env read, NO wall-clock read, NO daemon
# / background loop / while loop, and edits NO existing live runner / orchestrator
# / transport / Stage 28 suppression / Stage 29 live provider file. Unlike the
# offline-only Stage 30.9.x / 30.10.x slices, Stage 30.11.4 IS permitted to
# compose the committed live surfaces behind the dip gate (the permitted scope
# expansion): the proof composes the committed Stage 30.11.2 runtime seam + fake
# stream and the committed Stage 30.11.3 private sink adapter + fake proof, and
# the Stage 30.11.1 bridge + Stage 30.9.3 dip gate are exercised TRANSITIVELY
# through the committed seam; no Stage 21-29 / live runner / provider / real
# transport module is imported. NO Stage 30.11.5+ file ships at Stage 30.11.4.


STAGE30_11_4_MINOR_VERSION: str = "30.11.4"


# The Stage 30.11.4 offline end-to-end proof schema version (mirrored BY VALUE by
# the Stage 30.11.4 end-to-end proof models module; a pin test cross-checks it
# matches). Distinct from the Stage 30.11.3 private sink schema version, the
# Stage 30.11.2 runtime gate schema version, the Stage 30.11.1 bridge schema
# version, and the Stage 30.9.3 integration schema version.
STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION: str = (
    "stage30_11_4_v0_offline_e2e_proof"
)


# The two NEW production basenames + their dotted module paths.
STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME: str = (
    "stage30_11_4_offline_e2e_proof_models.py"
)
STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME: str = (
    "stage30_11_4_offline_e2e_proof.py"
)


STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_4_offline_e2e_proof_models"
)
STAGE30_11_4_OFFLINE_E2E_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_4_offline_e2e_proof"
)


# The ALREADY-COMMITTED sibling module paths the Stage 30.11.4 proof composes
# (re-declared here as literals; the manifest imports no PHX2 module). The proof
# composes the Stage 30.11.2 runtime seam + its deterministic fake stream / config
# / clock and the Stage 30.11.3 private sink adapter + fake proof (recording fake
# transport) + models (result type). The Stage 30.11.1 bridge + Stage 30.9.3 dip
# gate are composed TRANSITIVELY through the committed seam. These are the
# committed live-gate surfaces the Stage 30.11 wiring is explicitly permitted to
# compose behind the dip gate.
STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_seam"
)
STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
)
STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_models"
)
STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_adapter"
)
STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_3_fake_private_sink_proof"
)


# The two NEW production files Stage 30.11.4 adds under ``PHX2/stage30/`` on top
# of the already-allowed Stage 30.0..30.11.3 inventory. NO Stage 30.11.5+ file.
STAGE30_11_4_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME,
    STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME,
)


# The two production modules the Stage 30.11.4 boundary test scans for forbidden
# imports / text needles.
STAGE30_11_4_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME,
    STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME,
)


STAGE30_11_4_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_4_offline_e2e_proof_models.py",
    "test_stage_30_11_4_offline_e2e_proof.py",
    "test_stage_30_11_4_boundaries.py",
    "test_stage_30_11_4_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.4 production module must be in this
# stdlib allowlist (the models need ``dataclasses`` / ``typing``; the proof needs
# ``decimal`` / ``typing``). It admits NO ``os`` (so NO ``os.environ`` /
# ``os.getenv`` env read), NO ``sqlite3``, NO ``zstd`` / compression, NO network
# module, and NO ``time`` / ``datetime`` (every clock is injected, never read).
STAGE30_11_4_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.4 production module must be one of these
# siblings: the Stage 30.11.4 own end-to-end proof models sibling plus the
# committed Stage 30.11.2 runtime seam + fake proof siblings and the committed
# Stage 30.11.3 private sink models + adapter + fake proof siblings the proof
# composes. This positive allowlist proves, by construction, that NO Stage 21-29
# (incl. Stage 28 suppression / Stage 29.5 / Stage 29 live provider) / runtime
# orchestrator / renderer / real transport / Discord / live provider module is
# imported (the proof composes ONLY the committed Stage 30.11.2 + Stage 30.11.3
# offline surfaces; the Stage 30.11.1 bridge + Stage 30.9.3 gate are reached
# transitively through the committed seam).
STAGE30_11_4_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE,
    STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE,
)


# Closed-set proof decision tokens (mirrored BY VALUE from the Stage 30.11.4
# end-to-end proof models module). ``OFFLINE_E2E_PROOF_PASSED`` is the only
# decision on which the whole composed chain behaved as the baseline requires
# (the dip reached the fake transport ONLY).
STAGE30_11_4_PROOF_DECISIONS: Tuple[str, ...] = (
    "OFFLINE_E2E_PROOF_PASSED",
    "OFFLINE_E2E_PROOF_FAILED",
)


# The single decision on which the composed chain matched the baseline.
STAGE30_11_4_PROOF_PASS_DECISION: str = "OFFLINE_E2E_PROOF_PASSED"


# Closed-set proof reason tokens (mirrored BY VALUE from the Stage 30.11.4
# end-to-end proof models module). ``PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY`` names
# a RECORDED would-send for the dip ONLY, NEVER a real send.
STAGE30_11_4_PROOF_REASONS: Tuple[str, ...] = (
    "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY",
    "UNEXPECTED_E2E_COUNTS",
    "UNEXPECTED_TRANSPORT_ATTEMPT",
    "INVALID_PROOF_INPUT",
)


# The single reason that accompanies the only passed decision.
STAGE30_11_4_PROOF_PASS_REASON: str = "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY"


# The Stage 30.11.4 proof summary / result field names (mirrored BY VALUE from
# the Stage 30.11.4 end-to-end proof models module; a pin test cross-checks
# them). ``created_at_utc`` is caller-injected, never a wall-clock read; NONE is
# a secret, a raw payload, a host, or a transport destination.
STAGE30_11_4_PROOF_SUMMARY_FIELDS: Tuple[str, ...] = (
    "candidates_seen",
    "bridge_successes",
    "bridge_suppressed",
    "gate_passes",
    "gate_suppressed",
    "sink_attempts",
    "sink_accepts",
    "sink_failures",
    "transport_attempts",
    "transport_accepts",
    "runtime_stopped_by_candidate_cap",
    "runtime_stopped_by_dispatch_cap",
    "runtime_stopped_by_runtime_seconds",
    "proof_decision",
    "proof_reason",
    "created_at_utc",
)
STAGE30_11_4_PROOF_RESULT_FIELDS: Tuple[str, ...] = (
    "proof_decision",
    "proof_reason",
    "summary",
    "runtime_outcomes",
    "transport_candidate_ids",
    "transport_token_mints",
    "created_at_utc",
)


# The author-verified expected Stage 30.11.4 offline end-to-end proof counts over
# the committed Stage 30.11.2 deterministic five-candidate default stream run
# through the committed runtime seam with the committed Stage 30.11.3 private sink
# (wrapped for seam compatibility) injected and an INJECTED recording fake
# transport: at least four scenario kinds (dip / non-dip / bridge-skip / invalid)
# with five candidates seen, exactly two bridged, exactly one passed the
# committed dip gate, exactly one private sink attempt + accept, exactly one fake
# transport attempt + accept -- for the Tier 1 dip (``cand-tier1`` /
# ``mint-tier1``) ONLY. Every non-dip / bridge-skip / invalid candidate is
# suppressed cleanly BEFORE the sink and never reaches the transport, and no cap
# / wall-clock bound is tripped. No real dispatch reserved; no Discord sent.
STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN: int = 4
STAGE30_11_4_EXPECTED_CANDIDATES_SEEN: int = 5
STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES: int = 2
STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED: int = 3
STAGE30_11_4_EXPECTED_GATE_PASSES: int = 1
STAGE30_11_4_EXPECTED_GATE_SUPPRESSED: int = 1
STAGE30_11_4_EXPECTED_SINK_ATTEMPTS: int = 1
STAGE30_11_4_EXPECTED_SINK_ACCEPTS: int = 1
STAGE30_11_4_EXPECTED_SINK_FAILURES: int = 0
STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS: int = 1
STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID: str = "cand-tier1"
STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# After Stage 30.11.4 (the offline end-to-end proof) the WHOLE dip-gated private
# sink chain is proven offline / with fakes. The next allowed step is NOT a
# further Stage 30.11.<N> implementation slice: it is the controlled dip-filtered
# private compact live ceremony, which remains a SEPARATE, explicitly
# operator-authorized step (NOT run here, NOT in this stage). The Stage 30.11.0
# family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned at ``30.11.1``;
# this 30.11.4-scoped pointer names the operator-authorized ceremony as the next
# step. NO Stage 30.11.5+ file ships at Stage 30.11.4.
STAGE30_11_4_NEXT_ALLOWED_STAGE: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_11_4_NEXT_ALLOWED_STAGE_TITLE: str = (
    "controlled dip-filtered private compact live ceremony (a SEPARATE, "
    "explicitly operator-authorized step run against committed + green code; "
    "NOT run here -- the offline dip-gated private sink chain is now proven end "
    "to end with fakes)"
)


# The surfaces the Stage 30.11.4 offline end-to-end proof slice must not touch.
# Plain documentation words (family / feature names), NOT secret / host /
# transport needle forms. The slice ONLY composes the already-committed chain
# behind the dip gate and judges the result against the baseline; it must not
# reach any surface below, and it must NOT run the controlled live ceremony.
STAGE30_11_4_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "controlled live ceremony executed in this stage",
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
    "new runtime gate seam",
    "new private sink adapter",
    "new dip gate",
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
    "Stage 30.11.5+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.4 implements no part
# of it; it only proves -- with fakes -- that the whole committed dip-gated
# private sink chain composes end to end, with the fake transport reached ONLY
# for the dip).
STAGE30_11_4_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_4_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.4 is the offline end-to-end proof only; the controlled dip-"
    "filtered private compact live ceremony remains a separate, explicitly "
    "operator-authorized step that is not run here"
)


# ---------------------------------------------------------------------------
# Stage 30.11.5 -- controlled live ceremony wiring (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.5 is the FIFTH Stage 30.11 production slice: the narrowest
# controlled-live-ceremony WIRING the prior ceremony lacked between a real
# candidate source and the private operator transport boundary, proven with
# fakes / offline tests only. The prior controlled ceremony (after Stage 30.11.4)
# stopped safely BEFORE env / provider / Discord because the committed path had
# (a) NO committed source that produces a Stage 30.11.1
# ``Stage30_11LiveCandidateSnapshot`` and (b) NO committed transport adapter
# conforming to the Stage 30.11.3 sink transport protocol; the only full-chain
# proof used a fake stream + a fake transport, so a real ceremony would have
# required production edits and stopped. Stage 30.11.5 builds that missing wiring
# slice, fake / offline first. It adds five NEW production files -- the passive
# live wiring models (the live-candidate assembly result embedding the committed
# Stage 30.11.1 snapshot + the private operator payload + the low-level
# transport-client result + the bounded-run summary / result + the closed-set
# assembly-decision / assembly-reason / transport-status vocabularies + the hard
# bounded-run caps + the fake-wiring baseline), the live-candidate snapshot
# ASSEMBLER (which converts an existing flat safe-scalar candidate projection
# into a committed Stage 30.11.1 snapshot, failing closed on a missing / malformed
# pair / price / ATH / migration / drawdown / tier field, fabricating no dip, and
# never bypassing the committed bridge / dip gate -- the snapshot is their INPUT),
# the private TRANSPORT ADAPTER boundary (which conforms to the committed Stage
# 30.11.3 sink transport protocol by rendering a SAFE private operator payload
# from a sink request and handing it to an INJECTED low-level transport client --
# a FAKE in this slice -- never reading the private transport destination env var,
# never sending real Discord), the BOUNDED LIVE RUNNER (which composes the source
# -> the assembler -> the committed Stage 30.11.2 seam -> the committed Stage
# 30.11.3 private sink -> the injected transport adapter under HARD caps:
# max_dispatches <= 1, max_runtime_seconds <= 60, max_candidates <= 10, an
# injected clock, a single bounded for-loop, no daemon / while loop / autorestart
# / public routing), and the offline fake live wiring proof (which runs the
# bounded runner over a deterministic four-candidate fake source with an INJECTED
# recording fake transport client + an injected fake clock, proving the fake
# transport is reached for the dip ONLY). It is the missing live-wiring link the
# prior controlled live ceremony lacked. It ships NO real candidate source / real
# transport / real Discord / webhook send, NO dispatch reservation, NO live
# provider call, NO Discord send, NO env read, NO wall-clock read, NO daemon /
# background loop, and edits NO existing live runner / orchestrator / transport /
# Stage 28 suppression / Stage 29 live provider file. Unlike the offline-only
# Stage 30.9.x / 30.10.x slices, Stage 30.11.5 IS permitted to compose the
# committed live surfaces behind the dip gate (the permitted scope expansion): the
# models embed the Stage 30.11.1 snapshot, the assembler builds it, the transport
# adapter composes the Stage 30.11.3 request / result types, and the bounded
# runner composes the Stage 30.11.2 seam + the Stage 30.11.3 private sink; no
# Stage 21-29 (incl. the deeply-nested Stage 27 / 28 / 29 live candidate RECORD --
# the assembler reads a flat safe projection only) / live runner / provider / real
# transport module is imported. NO Stage 30.11.6+ file ships at Stage 30.11.5.


STAGE30_11_5_MINOR_VERSION: str = "30.11.5"


# The Stage 30.11.5 controlled live ceremony wiring schema version (mirrored BY
# VALUE by the Stage 30.11.5 live-wiring-models module; a pin test cross-checks it
# matches). Distinct from the Stage 30.11.4 end-to-end proof schema version, the
# Stage 30.11.3 private sink schema version, the Stage 30.11.2 runtime gate schema
# version, the Stage 30.11.1 bridge schema version, and the Stage 30.9.3
# integration schema version.
STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION: str = "stage30_11_5_v0_live_wiring"


# The safe-shape source-stage provenance token the transport adapter stamps onto
# every built private operator payload (mirrored BY VALUE by the Stage 30.11.5
# models module).
STAGE30_11_5_SOURCE_STAGE: str = "30.11.5"


# The five NEW production basenames + their dotted module paths.
STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME: str = (
    "stage30_11_5_live_wiring_models.py"
)
STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME: str = (
    "stage30_11_5_live_candidate_snapshot_assembler.py"
)
STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME: str = (
    "stage30_11_5_private_transport_adapter.py"
)
STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME: str = (
    "stage30_11_5_bounded_live_runner.py"
)
STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME: str = (
    "stage30_11_5_fake_live_wiring_proof.py"
)


STAGE30_11_5_LIVE_WIRING_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_5_live_wiring_models"
)
STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_MODULE: str = (
    "PHX2.stage30.stage30_11_5_live_candidate_snapshot_assembler"
)
STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_5_private_transport_adapter"
)
STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE: str = (
    "PHX2.stage30.stage30_11_5_bounded_live_runner"
)
STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_5_fake_live_wiring_proof"
)


# The ALREADY-COMMITTED sibling module paths the Stage 30.11.5 slice composes
# (re-declared here as literals; the manifest imports no PHX2 module). The models
# embed the Stage 30.11.1 snapshot; the assembler builds it; the transport adapter
# composes the Stage 30.11.3 request / result types; the bounded runner composes
# the Stage 30.11.2 runtime-gate-models + seam + the Stage 30.11.3 private sink
# adapter; the fake proof composes the Stage 30.11.2 fake proof (for the injected
# clock). These are the committed live-gate surfaces the Stage 30.11 wiring is
# explicitly permitted to compose behind the dip gate.
STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_1_live_candidate_bridge_models"
)
STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_models"
)
STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE: str = (
    "PHX2.stage30.stage30_11_2_runtime_gate_seam"
)
STAGE30_11_5_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
)
STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_models"
)
STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_3_private_sink_adapter"
)


# The five NEW production files Stage 30.11.5 adds under ``PHX2/stage30/`` on top
# of the already-allowed Stage 30.0..30.11.4 inventory. NO Stage 30.11.6+ file.
STAGE30_11_5_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
    STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME,
    STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
    STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME,
)


# The five production modules the Stage 30.11.5 boundary test scans for forbidden
# imports / text needles.
STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME,
    STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME,
    STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME,
    STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME,
)


STAGE30_11_5_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_5_live_wiring_models.py",
    "test_stage_30_11_5_live_candidate_snapshot_assembler.py",
    "test_stage_30_11_5_private_transport_adapter.py",
    "test_stage_30_11_5_bounded_live_runner.py",
    "test_stage_30_11_5_fake_live_wiring_proof.py",
    "test_stage_30_11_5_boundaries.py",
    "test_stage_30_11_5_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.5 production module must be in this stdlib
# allowlist (the models need ``dataclasses`` / ``decimal``; the assembler needs
# ``decimal``; the transport adapter needs ``typing``; the bounded runner needs
# ``decimal`` / ``typing``; the fake proof needs ``decimal`` / ``typing``). It
# admits NO ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO
# ``sqlite3``, NO ``zstd`` / compression, NO network module, and NO ``time`` /
# ``datetime`` (every clock is injected, never read).
STAGE30_11_5_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.5 production module must be one of these
# siblings: the Stage 30.11.5 own live-wiring-models + assembler + transport-
# adapter + bounded-runner siblings plus the committed Stage 30.11.1 bridge-models
# sibling (the snapshot type), the committed Stage 30.11.2 runtime-gate-models +
# seam + fake-proof siblings, and the committed Stage 30.11.3 private-sink-models +
# adapter siblings the slice composes. This positive allowlist proves, by
# construction, that NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live
# candidate record, Stage 28 suppression, Stage 29.5, Stage 29 live provider) /
# runtime orchestrator / renderer / real transport / Discord / live provider
# module is imported (the slice composes ONLY the committed Stage 30.11.1 +
# 30.11.2 + 30.11.3 offline surfaces).
STAGE30_11_5_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_5_LIVE_WIRING_MODELS_MODULE,
    STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_MODULE,
    STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_MODULE,
    STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE,
    STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE,
    STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_5_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
)


# Closed-set live-candidate assembly decision tokens (mirrored BY VALUE from the
# Stage 30.11.5 live-wiring-models module). ``ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT``
# is the only decision that carries a built Stage 30.11.1 snapshot; the two reject
# decisions carry ``None`` and never reach the committed bridge / gate / transport.
STAGE30_11_5_ASSEMBLY_DECISIONS: Tuple[str, ...] = (
    "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT",
    "REJECTED_MISSING_REQUIRED_FIELD",
    "REJECTED_INVALID_FIELD_SHAPE",
)


# The single decision that yields a built Stage 30.11.1 live candidate snapshot.
STAGE30_11_5_ASSEMBLY_PASS_DECISION: str = "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT"


# Closed-set live-candidate assembly reason tokens (mirrored BY VALUE from the
# Stage 30.11.5 live-wiring-models module). ``READY_FOR_BRIDGE`` names the built
# snapshot as the INPUT the committed Stage 30.11.1 bridge later consumes, NEVER a
# bypass of it.
STAGE30_11_5_ASSEMBLY_REASONS: Tuple[str, ...] = (
    "READY_FOR_BRIDGE",
    "MISSING_REQUIRED_CANDIDATE_FIELD",
    "INVALID_CANDIDATE_FIELD_SHAPE",
)


# The single reason that accompanies the only assembled decision.
STAGE30_11_5_ASSEMBLY_PASS_REASON: str = "READY_FOR_BRIDGE"


# Closed-set transport-client status tokens (mirrored BY VALUE from the Stage
# 30.11.5 live-wiring-models module). ``WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE``
# names a RECORDED would-deliver (the injected fake client recorded the payload),
# NEVER a real send.
STAGE30_11_5_TRANSPORT_STATUSES: Tuple[str, ...] = (
    "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE",
    "TRANSPORT_REJECTED",
)


# The single status on which the injected transport client accepted the payload.
STAGE30_11_5_TRANSPORT_ACCEPT_STATUS: str = (
    "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE"
)


# The Stage 30.11.5 candidate-projection field names (the flat safe-scalar shape
# the assembler reads FROM; mirrored BY VALUE from the models module). The
# projection field names equal the Stage 30.11.1 snapshot field names BY VALUE.
# ``created_at_utc`` is caller-injected, never a wall-clock read; NONE is a secret,
# a raw payload, a host, or a transport destination.
STAGE30_11_5_PROJECTION_FIELDS: Tuple[str, ...] = (
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
STAGE30_11_5_REQUIRED_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "created_at_utc",
)
STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# The Stage 30.11.5 assembly-result / payload / transport-client-result /
# bounded-run summary / result field names (mirrored BY VALUE from the models
# module; a pin test cross-checks them). NONE is a secret, a raw payload, a host,
# or a transport destination.
STAGE30_11_5_ASSEMBLY_RESULT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "assembly_decision",
    "assembly_reason",
    "rejected_field",
    "snapshot",
    "created_at_utc",
)
STAGE30_11_5_PRIVATE_OPERATOR_PAYLOAD_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "candidate_ref",
    "tier_token",
    "body",
    "source_stage",
    "created_at_utc",
)
STAGE30_11_5_TRANSPORT_CLIENT_RESULT_FIELDS: Tuple[str, ...] = (
    "accepted",
    "transport_status",
    "candidate_id",
    "token_mint",
    "created_at_utc",
)
STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS: Tuple[str, ...] = (
    "source_items_seen",
    "assembled",
    "assembly_rejected",
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
    "created_at_utc",
)
STAGE30_11_5_BOUNDED_RUN_RESULT_FIELDS: Tuple[str, ...] = (
    "assembly_outcomes",
    "runtime_outcomes",
    "summary",
    "created_at_utc",
)


# The HARD bounded-run caps the runner enforces (mirrored BY VALUE from the models
# module; the models express ``max_runtime_seconds`` as a ``Decimal`` magnitude --
# this manifest is constants-only and mirrors the bound BY VALUE as an ``int``).
# A config above any cap fails closed.
STAGE30_11_5_MAX_DISPATCHES_HARD_CAP: int = 1
STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP: int = 60
STAGE30_11_5_MAX_CANDIDATES_HARD_CAP: int = 10
STAGE30_11_5_DEFAULT_MAX_DISPATCHES: int = 1
STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS: int = 60
STAGE30_11_5_DEFAULT_MAX_CANDIDATES: int = 10


# The author-verified expected Stage 30.11.5 fake live wiring proof counts over
# the deterministic four-candidate default fake source run through the bounded
# runner with an INJECTED recording fake transport client + an injected constant
# clock: four source items seen, exactly three assembled (the assembler-rejected
# candidate -- a required ``current_market_cap_usd`` field absent -- never becomes
# a snapshot), exactly three reach the committed seam, exactly two bridge, exactly
# one passes the committed dip gate, exactly one dispatch attempt + accept, exactly
# one fake transport attempt + accept -- for the Tier 1 dip (``cand-tier1`` /
# ``mint-tier1``) ONLY. The non-dip is suppressed by the dip gate, the
# bridge-suppressed by the bridge, the rejected one by the assembler, so none
# reaches the transport; no cap / wall-clock bound is tripped. No real dispatch
# reserved; no Discord sent.
STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN: int = 4
STAGE30_11_5_EXPECTED_ASSEMBLED: int = 3
STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED: int = 1
STAGE30_11_5_EXPECTED_CANDIDATES_SEEN: int = 3
STAGE30_11_5_EXPECTED_BRIDGED: int = 2
STAGE30_11_5_EXPECTED_GATE_PASSED: int = 1
STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED: int = 1
STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED: int = 1
STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE: int = 1
STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE: int = 1
STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS: int = 1
STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID: str = "cand-tier1"
STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# After Stage 30.11.5 (the controlled live ceremony wiring) the WHOLE dip-gated
# private dispatch chain -- from an existing candidate projection through the
# private operator transport boundary -- is wired + proven offline / with fakes.
# The next allowed step is NOT a further Stage 30.11.<N> implementation slice: it
# is the controlled dip-filtered private compact live ceremony, which remains a
# SEPARATE, explicitly operator-authorized step (NOT run here, NOT in this stage).
# The Stage 30.11.0 family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned
# at ``30.11.1``; this 30.11.5-scoped pointer names the operator-authorized
# ceremony as the next step. NO Stage 30.11.6+ file ships at Stage 30.11.5.
STAGE30_11_5_NEXT_ALLOWED_STAGE: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_11_5_NEXT_ALLOWED_STAGE_TITLE: str = (
    "controlled dip-filtered private compact live ceremony (a SEPARATE, "
    "explicitly operator-authorized step run against committed + green code; "
    "NOT run here -- the live candidate source -> snapshot assembler and the "
    "private operator transport boundary are now wired + proven offline with "
    "fakes, so the next ceremony attempt composes committed + tested code)"
)


# The surfaces the Stage 30.11.5 controlled-live-ceremony-wiring slice must not
# touch. Plain documentation words (family / feature names), NOT secret / host /
# transport needle forms. The slice ONLY assembles a snapshot from a flat
# projection + renders a safe payload + composes the committed chain under hard
# caps with an INJECTED fake transport client; it must not reach any surface
# below, and it must NOT run the controlled live ceremony.
STAGE30_11_5_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "controlled live ceremony executed in this stage",
    "real candidate source",
    "real transport call",
    "real Discord send",
    "Discord send",
    "real private webhook send",
    "real dispatch reservation",
    "live run",
    "live provider call",
    "env read",
    "private transport destination env read",
    "wall-clock read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "new runtime gate seam",
    "new private sink adapter",
    "new dip gate",
    "max_dispatches above 1",
    "max_runtime_seconds above 60",
    "max_candidates above 10",
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
    "Stage 27 / 28 / 29 candidate-record import",
    "Stage 28 transport-internals edit",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.6+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.5 implements no part
# of it; it only wires + proves -- with fakes -- the missing live candidate source
# -> snapshot assembler and the private operator transport boundary, so the next
# ceremony attempt composes committed + tested code).
STAGE30_11_5_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_5_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.5 is the offline controlled-live-ceremony wiring only; the "
    "controlled dip-filtered private compact live ceremony remains a separate, "
    "explicitly operator-authorized step that is not run here"
)


# ---------------------------------------------------------------------------
# Stage 30.11.6 -- real candidate source / harvest seam (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.6 is the SIXTH Stage 30.11 production slice: the real candidate
# source / harvest seam -- the narrowest remaining blocker before the controlled
# live ceremony can actually run. The Stage 30.11.5 bounded live runner needs a
# ``candidate_source`` of already-assembled flat projections, but the ONLY
# committed live assembly path (the Stage 28.9 / Stage 29.3 live provider session,
# ``run_stage28_9_live_provider_session``) FUSES candidate assembly with its OWN
# older ungated dispatch (the Stage 28.6 runner + transport) and returns only
# counters -- never the assembled candidate record. Stage 30.11.6 adds four NEW
# production files -- the passive candidate-source models (the closed-set harvest /
# projection decision + reason vocabularies, the Stage 30.11.5-shaped flat
# ``Stage30_11_6CandidateProjection``, the per-record projection result, the
# per-event harvest outcome, and the rolled-up harvest summary / result), the
# fail-closed projection adapter (which converts a HARVESTED candidate's flat
# safe-scalar fields into the Stage 30.11.5 projection shape, failing closed on a
# missing / malformed field and never fabricating a dip), the harvest adapter
# (which drives an INJECTED committed assembler boundary -- the
# ``Stage28_9CandidateAssembler.assemble`` protocol BY STRUCTURE -- over a bounded
# event source, CAPTURES each assembled record, flattens it via an INJECTED record
# flattener, and projects it, WITHOUT ever constructing a transport / dispatch sink
# / runner, so the old ungated dispatch is STRUCTURALLY impossible here), and the
# offline fake candidate source proof (which drives a deterministic five-event fake
# source through the harvest adapter and feeds the harvested ``candidate_source``
# through the committed Stage 30.11.5 fake live wiring proof). It ships NO real
# candidate source binding, NO real transport / Discord / webhook send, NO real
# dispatch reservation, NO live provider call, NO Discord send, NO env read, NO
# wall-clock read (every clock is injected), NO daemon / background loop, and edits
# NO existing Stage 27 / Stage 28 / Stage 29 / existing Stage 30 production file.
# Unlike the offline-only Stage 30.9.x / 30.10.x slices, Stage 30.11.6 IS permitted
# to compose the committed Stage 30.11.5 surfaces (the permitted scope expansion):
# the proof composes the committed Stage 30.11.5 fake live wiring proof; the harvest
# adapter is GENERIC (it drives an INJECTED assembler / flattener duck-typed as
# ``object``), so NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
# record, the Stage 28.9 live provider session adapter, Stage 28 suppression, Stage
# 29 live provider) module is imported. NO Stage 30.11.7+ file ships at Stage
# 30.11.6.


STAGE30_11_6_MINOR_VERSION: str = "30.11.6"


# The Stage 30.11.6 real candidate source / harvest seam schema version (mirrored
# BY VALUE by the Stage 30.11.6 candidate-source-models module; a pin test
# cross-checks it matches). Distinct from the Stage 30.11.5 live wiring schema
# version and every earlier Stage 30.11 schema version.
STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION: str = (
    "stage30_11_6_v0_candidate_source"
)


# The safe-shape source-stage provenance token the harvest seam stamps onto its
# results (provenance only; names the slice, never a secret / host / transport
# destination).
STAGE30_11_6_SOURCE_STAGE: str = "30.11.6"


# The four NEW production basenames + their dotted module paths.
STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME: str = (
    "stage30_11_6_candidate_source_models.py"
)
STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME: str = (
    "stage30_11_6_stage29_projection_adapter.py"
)
STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME: str = (
    "stage30_11_6_candidate_harvest_adapter.py"
)
STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME: str = (
    "stage30_11_6_fake_candidate_source_proof.py"
)


STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_6_candidate_source_models"
)
STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_6_stage29_projection_adapter"
)
STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_6_candidate_harvest_adapter"
)
STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_6_fake_candidate_source_proof"
)


# The ALREADY-COMMITTED Stage 30.11.5 sibling module path the Stage 30.11.6 fake
# proof composes (re-declared here as a literal; the manifest imports no PHX2
# module). The proof feeds the harvested candidate source through the committed
# Stage 30.11.5 fake live wiring proof (the committed bounded runner + the injected
# recording fake transport client + injected clock). This is the committed surface
# the Stage 30.11.6 slice is explicitly permitted to compose behind the dip gate.
STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_5_fake_live_wiring_proof"
)


# The four NEW production files Stage 30.11.6 adds under ``PHX2/stage30/`` on top
# of the already-allowed Stage 30.0..30.11.5 inventory. NO Stage 30.11.7+ file.
STAGE30_11_6_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME,
)


# The four production modules the Stage 30.11.6 boundary test scans for forbidden
# imports / text needles.
STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME,
)


STAGE30_11_6_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_6_candidate_source_models.py",
    "test_stage_30_11_6_stage29_projection_adapter.py",
    "test_stage_30_11_6_candidate_harvest_adapter.py",
    "test_stage_30_11_6_fake_candidate_source_proof.py",
    "test_stage_30_11_6_boundaries.py",
    "test_stage_30_11_6_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.6 production module must be in this stdlib
# allowlist (the models need ``dataclasses`` / ``decimal``; the projection adapter
# needs ``decimal``; the harvest adapter needs ``typing``; the fake proof needs
# ``dataclasses`` / ``typing``). It admits NO ``os`` (so NO ``os.environ`` /
# ``os.getenv`` env read), NO ``sqlite3``, NO ``zstd`` / compression, NO network
# module, and NO ``time`` / ``datetime`` (every clock is injected, never read).
STAGE30_11_6_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.6 production module must be one of these
# siblings: the Stage 30.11.6 own candidate-source-models + projection-adapter +
# harvest-adapter + fake-proof siblings plus the committed Stage 30.11.5
# fake-live-wiring-proof sibling the proof composes. This positive allowlist
# proves, by construction, that NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29
# live candidate record, the Stage 28.9 live provider session adapter, Stage 28
# suppression, Stage 29.5, Stage 29 live provider) / runtime orchestrator /
# renderer / real transport / Discord / live provider module is imported (the
# slice composes ONLY the committed Stage 30.11.5 offline surface; the assembler /
# record flattener are INJECTED, duck-typed as ``object``).
STAGE30_11_6_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE,
    STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE,
    STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE,
    STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE,
    STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE,
)


# Closed-set per-record projection decision tokens (mirrored BY VALUE from the
# Stage 30.11.6 candidate-source-models module). ``PROJECTED_LIVE_CANDIDATE`` is
# the only decision that carries a built ``Stage30_11_6CandidateProjection``; the
# two reject decisions carry ``None`` and never become a candidate the runner could
# dispatch.
STAGE30_11_6_PROJECTION_DECISIONS: Tuple[str, ...] = (
    "PROJECTED_LIVE_CANDIDATE",
    "REJECTED_MISSING_REQUIRED_FIELD",
    "REJECTED_INVALID_FIELD_SHAPE",
)
STAGE30_11_6_PROJECTION_PASS_DECISION: str = "PROJECTED_LIVE_CANDIDATE"


# Closed-set per-record projection reason tokens (mirrored BY VALUE from the
# models module). ``READY_FOR_LIVE_RUNNER`` names the projection as the INPUT the
# committed Stage 30.11.5 runner / assembler later consume, NEVER a bypass of the
# committed bridge / dip gate.
STAGE30_11_6_PROJECTION_REASONS: Tuple[str, ...] = (
    "READY_FOR_LIVE_RUNNER",
    "MISSING_REQUIRED_CANDIDATE_FIELD",
    "INVALID_CANDIDATE_FIELD_SHAPE",
)
STAGE30_11_6_PROJECTION_PASS_REASON: str = "READY_FOR_LIVE_RUNNER"


# Closed-set per-event harvest decision tokens (mirrored BY VALUE from the models
# module). ``HARVESTED_LIVE_CANDIDATE`` is the only decision that yields a
# ``candidate_source`` projection; the two skip decisions yield nothing (a failed
# assembly / a rejected projection never reaches the Stage 30.11.5 transport).
STAGE30_11_6_HARVEST_DECISIONS: Tuple[str, ...] = (
    "HARVESTED_LIVE_CANDIDATE",
    "SKIPPED_ASSEMBLY_FAILED",
    "SKIPPED_PROJECTION_REJECTED",
)
STAGE30_11_6_HARVEST_PASS_DECISION: str = "HARVESTED_LIVE_CANDIDATE"


# Closed-set per-event harvest reason tokens (mirrored BY VALUE from the models
# module).
STAGE30_11_6_HARVEST_REASONS: Tuple[str, ...] = (
    "HARVESTED_READY_FOR_LIVE_RUNNER",
    "ASSEMBLY_RAISED_OR_EMPTY",
    "PROJECTION_FAILED_CLOSED",
)
STAGE30_11_6_HARVEST_PASS_REASON: str = "HARVESTED_READY_FOR_LIVE_RUNNER"


# The projection sentinel stamped on a harvest outcome whose assembler RAISED (so
# no record was captured and the projection adapter was never reached); NOT a
# member of the projection decision / reason vocabularies.
STAGE30_11_6_NOT_PROJECTED: str = "NOT_PROJECTED"


# The Stage 30.11.6 flat projection field names (the Stage 30.11.5-shaped flat
# safe-scalar projection the harvest seam emits; mirrored BY VALUE from the models
# module AND equal to the committed Stage 30.11.5 projection field names BY VALUE,
# a pin test cross-checks both). ``created_at_utc`` is caller-injected, never a
# wall-clock read; NONE is a secret, a raw payload, a host, or a transport
# destination.
STAGE30_11_6_PROJECTION_FIELDS: Tuple[str, ...] = (
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
STAGE30_11_6_REQUIRED_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "created_at_utc",
)
STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# The Stage 30.11.6 projection / projection-result / harvest-outcome / harvest-
# summary / harvest-result field names (mirrored BY VALUE from the models module;
# a pin test cross-checks them). NONE is a secret, a raw payload, a host, or a
# transport destination.
STAGE30_11_6_CANDIDATE_PROJECTION_FIELDS: Tuple[str, ...] = (
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
STAGE30_11_6_PROJECTION_RESULT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "projection_decision",
    "projection_reason",
    "rejected_field",
    "projection",
    "created_at_utc",
)
STAGE30_11_6_HARVEST_OUTCOME_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "harvest_decision",
    "harvest_reason",
    "projection_decision",
    "projection_reason",
    "rejected_field",
    "created_at_utc",
)
STAGE30_11_6_HARVEST_SUMMARY_FIELDS: Tuple[str, ...] = (
    "events_seen",
    "harvested",
    "skipped_assembly_failed",
    "skipped_projection_rejected",
    "created_at_utc",
)
STAGE30_11_6_HARVEST_RESULT_FIELDS: Tuple[str, ...] = (
    "outcomes",
    "candidate_source",
    "summary",
    "created_at_utc",
)


# The HARD harvest cap the harvest adapter enforces + the default + the run-scoped
# candidate-id prefix (mirrored BY VALUE from the models module). The cap mirrors
# the Stage 30.11.5 ``max_candidates <= 10`` ceiling; a ``max_harvest`` above the
# cap fails closed BEFORE harvesting.
STAGE30_11_6_MAX_HARVEST_HARD_CAP: int = 10
STAGE30_11_6_DEFAULT_MAX_HARVEST: int = 10
STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX: str = "stage30_11_6_cand_"


# The author-verified expected Stage 30.11.6 fake candidate source proof counts
# over the deterministic five-event default fake source: five events seen, exactly
# three harvested (one non-dip + one bridge-suppressed + one Tier 1 dip), exactly
# one skipped for a failed assembly (the injected assembler raised), exactly one
# skipped for a rejected projection (a required field absent). The committed Stage
# 30.11.5 runner over the three harvested projections: three candidates seen, two
# bridged, one dip-gate PASS, exactly one dispatch attempt + accept, exactly one
# fake transport attempt + accept -- for the Tier 1 dip
# (``stage30_11_6_cand_000002`` / ``mint-tier1``) ONLY. The old ungated dispatch
# path is never invoked (the fake assembler's dispatch tripwire records zero
# calls). No real dispatch reserved; no Discord sent.
STAGE30_11_6_EXPECTED_EVENTS_SEEN: int = 5
STAGE30_11_6_EXPECTED_HARVESTED: int = 3
STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED: int = 1
STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN: int = 3
STAGE30_11_6_EXPECTED_RUNNER_BRIDGED: int = 2
STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED: int = 1
STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS: int = 1
STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID: str = "stage30_11_6_cand_000002"
STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# After Stage 30.11.6 (the real candidate source / harvest seam) the WHOLE
# dip-gated private dispatch chain -- from harvesting a real-shaped assembled
# candidate (WITHOUT the old ungated dispatch) through the committed Stage 30.11.5
# bounded runner to the private operator transport boundary -- is wired + proven
# offline / with fakes. The next allowed step is NOT a further Stage 30.11.<N>
# implementation slice: it is the controlled dip-filtered private compact live
# ceremony, which remains a SEPARATE, explicitly operator-authorized step (NOT run
# here, NOT in this stage). The Stage 30.11.0 family pointer
# ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned at ``30.11.1``; this 30.11.6-
# scoped pointer names the operator-authorized ceremony as the next step. NO Stage
# 30.11.7+ file ships at Stage 30.11.6.
STAGE30_11_6_NEXT_ALLOWED_STAGE: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_11_6_NEXT_ALLOWED_STAGE_TITLE: str = (
    "controlled dip-filtered private compact live ceremony (a SEPARATE, "
    "explicitly operator-authorized step run against committed + green code; "
    "NOT run here -- the real candidate source / harvest seam now harvests an "
    "assembled candidate WITHOUT the old ungated dispatch and feeds it through "
    "the committed Stage 30.11.5 bounded runner, all proven offline with fakes, "
    "so the next ceremony attempt composes committed + tested code for the "
    "candidate source as well)"
)


# The surfaces the Stage 30.11.6 real-candidate-source / harvest-seam slice must
# not touch. Plain documentation words (family / feature names), NOT secret / host
# / transport needle forms. The slice ONLY harvests an assembled candidate (via an
# INJECTED assembler / flattener) + projects it + feeds the committed Stage 30.11.5
# runner; it must not reach any surface below, and it must NOT run the controlled
# live ceremony.
STAGE30_11_6_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "controlled live ceremony executed in this stage",
    "real candidate source binding",
    "real transport call",
    "real Discord send",
    "Discord send",
    "real private webhook send",
    "real dispatch reservation",
    "old ungated dispatch invoked",
    "Stage 28.9 live provider session call",
    "ungated Stage 29.3 send path reused directly",
    "live run",
    "live provider call",
    "env read",
    "wall-clock read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "new runtime gate seam",
    "new private sink adapter",
    "new dip gate",
    "new broad live runner",
    "bypass Stage 30.11.5 bounded runner",
    "bypass Stage 30.9.3 dip gate",
    "max_harvest above 10",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
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
    "Stage 27 / 28 / 29 candidate-record import",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.7+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.6 implements no part
# of it; it only harvests + projects -- with fakes -- the missing real candidate
# source, so the next ceremony attempt composes committed + tested code).
STAGE30_11_6_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_6_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.6 is the offline real-candidate-source / harvest seam only; the "
    "controlled dip-filtered private compact live ceremony remains a separate, "
    "explicitly operator-authorized step that is not run here"
)


# ---------------------------------------------------------------------------
# Stage 30.11.7 -- candidate dip-enrichment bridge (fakes / offline only)
# ---------------------------------------------------------------------------
#
# Stage 30.11.7 is the SEVENTH Stage 30.11 production slice: the narrow candidate
# dip-enrichment bridge -- the blocker the controlled live ceremony retry surfaced.
# The committed Stage 30.11.6 harvest seam captures + projects a real assembled
# candidate's flat fields, but the committed live chain produces only candidate
# IDENTITY; it does NOT produce the Stage 30 dip / enrichment fields (a
# ``tier_hint``, a ``current_market_cap_usd``, real migration evidence, an ATH /
# drawdown), so the fail-closed Stage 30.11.6 projection correctly rejected the
# harvested candidate with ``MISSING_REQUIRED_FIELD`` (rejected field
# ``tier_hint``) -- and that safety behavior MUST remain. Stage 30.11.7 adds three
# NEW production files -- the passive enrichment models (the closed-set enrichment
# decision / reason / dimension vocabularies, the four INJECTED resolver-result
# carriers, the Stage 30.11.5-shaped flat ``Stage30_11_7EnrichedCandidate``, the
# per-candidate enrichment result, and the rolled-up enrichment summary / run
# result), the fail-closed enrichment adapter (which fills the missing dip fields
# from four INJECTED resolvers, mapping a CONFIRMED verdict to the gate's
# ``PRESENT`` token + a finite -- cap strictly positive -- ``Decimal`` magnitude,
# carrying the tier token VERBATIM, and failing closed on the FIRST missing /
# unavailable / unconfirmed / stale / pre-migration / malformed dimension, never
# fabricating a dip), and the offline fake enrichment proof (which drives a
# deterministic six-base fake source through the enrichment bridge with injected
# fake resolvers). It ships NO real resolver binding, NO real transport / Discord /
# webhook send, NO real dispatch reservation, NO live provider call, NO Discord
# send, NO env read, NO wall-clock read (every clock is injected), NO daemon /
# background loop, and edits NO existing Stage 27 / Stage 28 / Stage 29 / existing
# Stage 30 production file. Unlike the Stage 30.11.6 slice, the Stage 30.11.7
# PRODUCTION slice is a clean LEAF: it imports ONLY its own three siblings (no
# Stage 30.11.5 / Stage 30.11.6 import), so the committed Stage 30.11.5 /
# Stage 30.11.6 leaf boundary tests stay green untouched; the committed Stage
# 30.11.5 bounded runner is composed -- and the "exactly one PASS dip reaches the
# fake transport" end-to-end assertion proven -- by the Stage 30.11.7 TEST (which
# feeds the enriched ``candidate_source`` through the committed Stage 30.11.5 fake
# live wiring proof; a test file is not boundary-scanned). The real Stage 30.4
# market context / Stage 30.5 migration / Stage 30.7 ATH adapters plug in at the
# INJECTED resolver seam via out-of-repo, operator-authorized wrappers, exactly as
# the Stage 30.11.6 record flattener wraps the real flattener at the ceremony
# boundary; NO Stage 21-29 module is imported. NO Stage 30.11.8+ file ships at
# Stage 30.11.7.


STAGE30_11_7_MINOR_VERSION: str = "30.11.7"


# The Stage 30.11.7 candidate dip-enrichment bridge schema version (mirrored BY
# VALUE by the Stage 30.11.7 enrichment-models module; a pin test cross-checks it
# matches). Distinct from the Stage 30.11.6 candidate-source schema version and
# every earlier Stage 30.11 schema version.
STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION: str = (
    "stage30_11_7_v0_candidate_enrichment"
)


# The safe-shape source-stage provenance token the enrichment bridge stamps onto
# its results (provenance only; names the slice, never a secret / host / transport
# destination).
STAGE30_11_7_SOURCE_STAGE: str = "30.11.7"


# The three NEW production basenames + their dotted module paths.
STAGE30_11_7_ENRICHMENT_MODELS_BASENAME: str = (
    "stage30_11_7_candidate_enrichment_models.py"
)
STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME: str = (
    "stage30_11_7_candidate_enrichment_adapter.py"
)
STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME: str = (
    "stage30_11_7_fake_enrichment_proof.py"
)


STAGE30_11_7_ENRICHMENT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_11_7_candidate_enrichment_models"
)
STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_7_candidate_enrichment_adapter"
)
STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_7_fake_enrichment_proof"
)


# The three NEW production files Stage 30.11.7 adds under ``PHX2/stage30/`` on top
# of the already-allowed Stage 30.0..30.11.6 inventory. NO Stage 30.11.8+ file.
STAGE30_11_7_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_7_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME,
)


# The three production modules the Stage 30.11.7 boundary test scans for forbidden
# imports / text needles.
STAGE30_11_7_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_11_7_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME,
)


STAGE30_11_7_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_11_7_candidate_enrichment_models.py",
    "test_stage_30_11_7_candidate_enrichment_adapter.py",
    "test_stage_30_11_7_fake_enrichment_proof.py",
    "test_stage_30_11_7_boundaries.py",
    "test_stage_30_11_7_manifest.py",
)


# Every non-PHX2 import in a Stage 30.11.7 production module must be in this stdlib
# allowlist (the models need ``dataclasses`` / ``decimal``; the adapter needs
# ``decimal`` / ``typing``; the fake proof needs ``dataclasses`` / ``typing``). It
# admits NO ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO ``sqlite3``,
# NO ``zstd`` / compression, NO network module, and NO ``time`` / ``datetime``
# (every clock is injected, never read).
STAGE30_11_7_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# Every PHX2 import in a Stage 30.11.7 production module must be one of these
# siblings: the Stage 30.11.7 own enrichment-models + enrichment-adapter +
# fake-proof siblings. This positive allowlist proves, by construction, that the
# Stage 30.11.7 PRODUCTION slice is a clean LEAF -- it imports NO Stage 30.11.5 /
# Stage 30.11.6 module (so the committed Stage 30.11.5 / Stage 30.11.6 leaf
# boundary tests stay green), NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29
# live candidate record, Stage 28 suppression, Stage 29 live provider) / runtime
# orchestrator / renderer / real transport / Discord / live provider module. The
# four resolvers are INJECTED, duck-typed; the committed Stage 30.11.5 runner is
# composed by the Stage 30.11.7 TEST, never by a Stage 30.11.7 production module.
STAGE30_11_7_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_11_7_ENRICHMENT_MODELS_MODULE,
    STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE,
)


# The committed Stage 30.11.5 fake-live-wiring-proof module the Stage 30.11.7 TEST
# (NOT a Stage 30.11.7 production module) composes to prove the enriched
# ``candidate_source`` reaches the committed bounded runner and dip gate. Declared
# here as a literal (the manifest imports no PHX2 module); it is NOT in the Stage
# 30.11.7 production PHX2 import allowlist -- the production slice is a leaf.
STAGE30_11_7_TEST_COMPOSES_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_5_fake_live_wiring_proof"
)


# Closed-set per-candidate enrichment decision tokens (mirrored BY VALUE from the
# Stage 30.11.7 enrichment-models module). ``ENRICHED_DIP_CANDIDATE`` is the only
# decision that carries a built ``Stage30_11_7EnrichedCandidate``; the reject
# decision carries ``None`` and never becomes a candidate the runner could
# dispatch.
STAGE30_11_7_ENRICHMENT_DECISIONS: Tuple[str, ...] = (
    "ENRICHED_DIP_CANDIDATE",
    "REJECTED_ENRICHMENT",
)
STAGE30_11_7_ENRICHMENT_PASS_DECISION: str = "ENRICHED_DIP_CANDIDATE"


# Closed-set per-candidate enrichment reason tokens (mirrored BY VALUE from the
# models module). ``READY_FOR_LIVE_RUNNER`` names the enriched candidate as the
# INPUT the committed Stage 30.11.5 runner / dip gate later consume; every other
# reason names the FIRST failing dimension's fail-closed cause (an UNKNOWN
# migration, a missing / stale market context or ATH, a malformed magnitude can
# never become eligible).
STAGE30_11_7_ENRICHMENT_REASONS: Tuple[str, ...] = (
    "READY_FOR_LIVE_RUNNER",
    "MISSING_MARKET_CONTEXT",
    "INVALID_MARKET_CAP",
    "MISSING_TIER",
    "MISSING_MIGRATION_EVIDENCE",
    "UNCONFIRMED_MIGRATION",
    "MISSING_ATH",
    "STALE_ATH",
    "PRE_MIGRATION_ATH_NOT_VERIFIED",
    "INVALID_DRAWDOWN",
)
STAGE30_11_7_ENRICHMENT_PASS_REASON: str = "READY_FOR_LIVE_RUNNER"


# Closed-set rejected enrichment dimension tokens (mirrored BY VALUE from the
# models module); the empty ``""`` enriched sentinel is NOT a dimension.
STAGE30_11_7_ENRICHMENT_DIMENSIONS: Tuple[str, ...] = (
    "MARKET_CONTEXT",
    "TIER",
    "MIGRATION",
    "ATH",
)


# The Stage 30.11.7 enriched-candidate field names (the Stage 30.11.5-shaped flat
# safe-scalar enriched candidate the enrichment bridge emits; mirrored BY VALUE
# from the models module AND equal to the committed Stage 30.11.6 projection field
# names BY VALUE, a pin test cross-checks both). ``created_at_utc`` is
# caller-injected, never a wall-clock read; NONE is a secret, a raw payload, a
# host, or a transport destination.
STAGE30_11_7_ENRICHED_FIELDS: Tuple[str, ...] = (
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
STAGE30_11_7_REQUIRED_ENRICHED_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "created_at_utc",
)
STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# The Stage 30.11.7 enrichment result / summary / run-result + resolver-result
# field names (mirrored BY VALUE from the models module; a pin test cross-checks
# them). NONE is a secret, a raw payload, a host, or a transport destination.
STAGE30_11_7_ENRICHMENT_RESULT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "enrichment_decision",
    "enrichment_reason",
    "rejected_dimension",
    "enriched_candidate",
    "created_at_utc",
)
STAGE30_11_7_ENRICHMENT_SUMMARY_FIELDS: Tuple[str, ...] = (
    "bases_seen",
    "enriched",
    "rejected_market_context",
    "rejected_tier",
    "rejected_migration",
    "rejected_ath",
    "created_at_utc",
)
STAGE30_11_7_ENRICHMENT_RUN_RESULT_FIELDS: Tuple[str, ...] = (
    "outcomes",
    "candidate_source",
    "summary",
    "created_at_utc",
)
STAGE30_11_7_MARKET_CONTEXT_RESOLUTION_FIELDS: Tuple[str, ...] = (
    "present",
    "current_market_cap_usd",
    "source_ref",
)
STAGE30_11_7_TIER_RESOLUTION_FIELDS: Tuple[str, ...] = ("tier_hint",)
STAGE30_11_7_MIGRATION_RESOLUTION_FIELDS: Tuple[str, ...] = (
    "confirmed",
    "source_ref",
)
STAGE30_11_7_ATH_RESOLUTION_FIELDS: Tuple[str, ...] = (
    "present",
    "fresh",
    "post_migration_ath_verified",
    "drawdown_from_ath",
    "source_ref",
)


# The gate-facing PRESENT token the enrichment maps a confirmed verdict onto
# (mirrored BY VALUE from the committed Stage 30.10.1 / Stage 30.11.1 PRESENT
# tokens). The HARD enrichment cap the bounded helper enforces + the default
# (mirrored BY VALUE from the models module). The cap mirrors the Stage 30.11.5
# ``max_candidates <= 10`` ceiling; a ``max_enrich`` above the cap fails closed
# BEFORE enriching.
STAGE30_11_7_CONTEXT_STATUS_PRESENT: str = "PRESENT"
STAGE30_11_7_MAX_ENRICH_HARD_CAP: int = 10
STAGE30_11_7_DEFAULT_MAX_ENRICH: int = 10


# The author-verified expected Stage 30.11.7 fake enrichment proof counts over the
# deterministic six-base default fake source: six bases seen, exactly two enriched
# (one Tier 1 dip + one Tier Unknown non-dip), exactly one rejected per dimension
# (a missing market context + a missing tier + an unconfirmed UNKNOWN migration + a
# stale ATH). The committed Stage 30.11.5 runner over the two enriched candidates
# (composed by the Stage 30.11.7 TEST): two candidates seen, two bridged, one
# dip-gate PASS, exactly one fake transport attempt + accept -- for the Tier 1 dip
# (``stage30_11_7_cand_dip`` / ``mint-dip``) ONLY. The old ungated dispatch path is
# never invoked. No real dispatch reserved; no Discord sent.
STAGE30_11_7_EXPECTED_BASES_SEEN: int = 6
STAGE30_11_7_EXPECTED_ENRICHED: int = 2
STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT: int = 1
STAGE30_11_7_EXPECTED_REJECTED_TIER: int = 1
STAGE30_11_7_EXPECTED_REJECTED_MIGRATION: int = 1
STAGE30_11_7_EXPECTED_REJECTED_ATH: int = 1
STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN: int = 2
STAGE30_11_7_EXPECTED_RUNNER_BRIDGED: int = 2
STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED: int = 1
STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS: int = 1
STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID: str = "stage30_11_7_cand_dip"
STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT: str = "mint-dip"


# After Stage 30.11.7 (the candidate dip-enrichment bridge) the WHOLE dip-gated
# private dispatch chain -- from harvesting a real-shaped assembled candidate
# (Stage 30.11.6) through ENRICHING its missing Stage 30 dip fields (Stage 30.11.7)
# through the committed Stage 30.11.5 bounded runner to the private operator
# transport boundary -- is wired + proven offline / with fakes. The next allowed
# step is NOT a further Stage 30.11.<N> implementation slice: it is the controlled
# dip-filtered private compact live ceremony retry, which remains a SEPARATE,
# explicitly operator-authorized step (NOT run here, NOT in this stage). The Stage
# 30.11.0 family pointer ``STAGE30_11_NEXT_ALLOWED_STAGE`` stays pinned at
# ``30.11.1``; the Stage 30.11.6 scoped pointer stays pinned at the ceremony; this
# 30.11.7-scoped pointer names the operator-authorized ceremony retry as the next
# step. NO Stage 30.11.8+ file ships at Stage 30.11.7.
STAGE30_11_7_NEXT_ALLOWED_STAGE: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_11_7_NEXT_ALLOWED_STAGE_TITLE: str = (
    "controlled dip-filtered private compact live ceremony retry (a SEPARATE, "
    "explicitly operator-authorized step run against committed + green code; NOT "
    "run here -- the enrichment bridge now fills the missing Stage 30 dip fields "
    "the prior ceremony lacked (the MISSING_REQUIRED_FIELD -> tier_hint gap) onto "
    "a harvested candidate, failing closed on every missing / unconfirmed / stale "
    "/ malformed dimension, so the next ceremony attempt composes committed + "
    "tested code for the enrichment as well)"
)


# The surfaces the Stage 30.11.7 candidate-dip-enrichment slice must not touch.
# Plain documentation words (family / feature names), NOT secret / host / transport
# needle forms. The slice ONLY enriches a harvested candidate (via INJECTED
# resolvers) into a flat enriched candidate the committed runner consumes; it must
# not reach any surface below, must NOT fabricate a missing dip field, and must NOT
# run the controlled live ceremony.
STAGE30_11_7_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "controlled live ceremony executed in this stage",
    "real resolver binding",
    "real market context provider call",
    "real migration provider call",
    "real ATH provider call",
    "real transport call",
    "real Discord send",
    "Discord send",
    "real private webhook send",
    "real dispatch reservation",
    "old ungated dispatch invoked",
    "ungated Stage 29.3 send path reused directly",
    "live run",
    "live provider call",
    "env read",
    "wall-clock read",
    "WebSocket / gRPC / HTTP session",
    "new live runner",
    "new provider",
    "new readiness gate",
    "new runtime gate seam",
    "new private sink adapter",
    "new dip gate",
    "parallel tier model",
    "fabricate missing dip field",
    "treat UNKNOWN migration as eligible",
    "treat missing or stale market context as eligible",
    "treat missing or stale ATH as eligible",
    "bypass Stage 30.11.5 bounded runner",
    "bypass Stage 30.11.6 harvest projection",
    "bypass Stage 30.9.3 dip gate",
    "max_enrich above 10",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
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
    "Stage 27 / 28 / 29 candidate-record import",
    "Stage 28 suppression-logic edit",
    "Stage 29 live provider / session edit",
    "Stage 25/27/28/29 production import",
    "Stage 30.11.5 / Stage 30.11.6 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.11.8+ implementation file",
    "Stage 31",
)


# The actual controlled dip-filtered private compact live ceremony retry remains a
# SEPARATE, explicitly operator-authorized step (Stage 30.11.7 implements no part
# of it; it only enriches -- with fakes -- the missing dip fields, so the next
# ceremony attempt composes committed + tested code).
STAGE30_11_7_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_11_7_LIVE_CEREMONY_NOTE: str = (
    "Stage 30.11.7 is the offline candidate dip-enrichment bridge only; the "
    "controlled dip-filtered private compact live ceremony retry remains a "
    "separate, explicitly operator-authorized step that is not run here"
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
    # ---- Stage 30.11.4 offline end-to-end proof ----
    # Minor version + end-to-end proof schema identity.
    "STAGE30_11_4_MINOR_VERSION",
    "STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION",
    # Basenames + module paths.
    "STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_BASENAME",
    "STAGE30_11_4_OFFLINE_E2E_PROOF_BASENAME",
    "STAGE30_11_4_OFFLINE_E2E_PROOF_MODELS_MODULE",
    "STAGE30_11_4_OFFLINE_E2E_PROOF_MODULE",
    "STAGE30_11_4_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
    "STAGE30_11_4_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
    "STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE",
    "STAGE30_11_4_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE",
    "STAGE30_11_4_STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_4_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_4_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_4_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_4_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_4_ALLOWED_PHX2_IMPORTS",
    # Proof decisions + reasons.
    "STAGE30_11_4_PROOF_DECISIONS",
    "STAGE30_11_4_PROOF_PASS_DECISION",
    "STAGE30_11_4_PROOF_REASONS",
    "STAGE30_11_4_PROOF_PASS_REASON",
    # Model field tuples.
    "STAGE30_11_4_PROOF_SUMMARY_FIELDS",
    "STAGE30_11_4_PROOF_RESULT_FIELDS",
    # Expected proof counts.
    "STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_4_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES",
    "STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED",
    "STAGE30_11_4_EXPECTED_GATE_PASSES",
    "STAGE30_11_4_EXPECTED_GATE_SUPPRESSED",
    "STAGE30_11_4_EXPECTED_SINK_ATTEMPTS",
    "STAGE30_11_4_EXPECTED_SINK_ACCEPTS",
    "STAGE30_11_4_EXPECTED_SINK_FAILURES",
    "STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT",
    # Next allowed stage + forbidden surfaces + live ceremony note.
    "STAGE30_11_4_NEXT_ALLOWED_STAGE",
    "STAGE30_11_4_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_4_FORBIDDEN_SURFACES",
    "STAGE30_11_4_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_4_LIVE_CEREMONY_NOTE",
    # ---- Stage 30.11.5 controlled live ceremony wiring ----
    # Minor version + live wiring schema identity.
    "STAGE30_11_5_MINOR_VERSION",
    "STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION",
    "STAGE30_11_5_SOURCE_STAGE",
    # Basenames + module paths.
    "STAGE30_11_5_LIVE_WIRING_MODELS_BASENAME",
    "STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_BASENAME",
    "STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_BASENAME",
    "STAGE30_11_5_BOUNDED_LIVE_RUNNER_BASENAME",
    "STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_BASENAME",
    "STAGE30_11_5_LIVE_WIRING_MODELS_MODULE",
    "STAGE30_11_5_LIVE_CANDIDATE_SNAPSHOT_ASSEMBLER_MODULE",
    "STAGE30_11_5_PRIVATE_TRANSPORT_ADAPTER_MODULE",
    "STAGE30_11_5_BOUNDED_LIVE_RUNNER_MODULE",
    "STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE",
    "STAGE30_11_5_STAGE30_11_1_BRIDGE_MODELS_MODULE",
    "STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE",
    "STAGE30_11_5_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
    "STAGE30_11_5_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
    "STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE",
    "STAGE30_11_5_STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_5_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_5_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_5_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_5_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_5_ALLOWED_PHX2_IMPORTS",
    # Assembly decisions + reasons.
    "STAGE30_11_5_ASSEMBLY_DECISIONS",
    "STAGE30_11_5_ASSEMBLY_PASS_DECISION",
    "STAGE30_11_5_ASSEMBLY_REASONS",
    "STAGE30_11_5_ASSEMBLY_PASS_REASON",
    # Transport-client statuses.
    "STAGE30_11_5_TRANSPORT_STATUSES",
    "STAGE30_11_5_TRANSPORT_ACCEPT_STATUS",
    # Projection + model field tuples.
    "STAGE30_11_5_PROJECTION_FIELDS",
    "STAGE30_11_5_REQUIRED_PROJECTION_FIELDS",
    "STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS",
    "STAGE30_11_5_ASSEMBLY_RESULT_FIELDS",
    "STAGE30_11_5_PRIVATE_OPERATOR_PAYLOAD_FIELDS",
    "STAGE30_11_5_TRANSPORT_CLIENT_RESULT_FIELDS",
    "STAGE30_11_5_BOUNDED_RUN_SUMMARY_FIELDS",
    "STAGE30_11_5_BOUNDED_RUN_RESULT_FIELDS",
    # Hard caps + defaults.
    "STAGE30_11_5_MAX_DISPATCHES_HARD_CAP",
    "STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP",
    "STAGE30_11_5_MAX_CANDIDATES_HARD_CAP",
    "STAGE30_11_5_DEFAULT_MAX_DISPATCHES",
    "STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS",
    "STAGE30_11_5_DEFAULT_MAX_CANDIDATES",
    # Expected proof counts.
    "STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN",
    "STAGE30_11_5_EXPECTED_ASSEMBLED",
    "STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED",
    "STAGE30_11_5_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_5_EXPECTED_BRIDGED",
    "STAGE30_11_5_EXPECTED_GATE_PASSED",
    "STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED",
    "STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED",
    "STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE",
    "STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE",
    "STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT",
    # Next allowed stage + forbidden surfaces + live ceremony note.
    "STAGE30_11_5_NEXT_ALLOWED_STAGE",
    "STAGE30_11_5_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_5_FORBIDDEN_SURFACES",
    "STAGE30_11_5_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_5_LIVE_CEREMONY_NOTE",
    # ---- Stage 30.11.6 real candidate source / harvest seam ----
    # Minor version + candidate-source schema identity.
    "STAGE30_11_6_MINOR_VERSION",
    "STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION",
    "STAGE30_11_6_SOURCE_STAGE",
    # Basenames + module paths.
    "STAGE30_11_6_CANDIDATE_SOURCE_MODELS_BASENAME",
    "STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_BASENAME",
    "STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_BASENAME",
    "STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_BASENAME",
    "STAGE30_11_6_CANDIDATE_SOURCE_MODELS_MODULE",
    "STAGE30_11_6_STAGE29_PROJECTION_ADAPTER_MODULE",
    "STAGE30_11_6_CANDIDATE_HARVEST_ADAPTER_MODULE",
    "STAGE30_11_6_FAKE_CANDIDATE_SOURCE_PROOF_MODULE",
    "STAGE30_11_6_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_6_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_6_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_6_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_11_6_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_6_ALLOWED_PHX2_IMPORTS",
    # Projection decisions + reasons.
    "STAGE30_11_6_PROJECTION_DECISIONS",
    "STAGE30_11_6_PROJECTION_PASS_DECISION",
    "STAGE30_11_6_PROJECTION_REASONS",
    "STAGE30_11_6_PROJECTION_PASS_REASON",
    # Harvest decisions + reasons + sentinel.
    "STAGE30_11_6_HARVEST_DECISIONS",
    "STAGE30_11_6_HARVEST_PASS_DECISION",
    "STAGE30_11_6_HARVEST_REASONS",
    "STAGE30_11_6_HARVEST_PASS_REASON",
    "STAGE30_11_6_NOT_PROJECTED",
    # Projection + model field tuples.
    "STAGE30_11_6_PROJECTION_FIELDS",
    "STAGE30_11_6_REQUIRED_PROJECTION_FIELDS",
    "STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS",
    "STAGE30_11_6_CANDIDATE_PROJECTION_FIELDS",
    "STAGE30_11_6_PROJECTION_RESULT_FIELDS",
    "STAGE30_11_6_HARVEST_OUTCOME_FIELDS",
    "STAGE30_11_6_HARVEST_SUMMARY_FIELDS",
    "STAGE30_11_6_HARVEST_RESULT_FIELDS",
    # Hard cap + default + candidate-id prefix.
    "STAGE30_11_6_MAX_HARVEST_HARD_CAP",
    "STAGE30_11_6_DEFAULT_MAX_HARVEST",
    "STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX",
    # Expected proof counts.
    "STAGE30_11_6_EXPECTED_EVENTS_SEEN",
    "STAGE30_11_6_EXPECTED_HARVESTED",
    "STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED",
    "STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED",
    "STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN",
    "STAGE30_11_6_EXPECTED_RUNNER_BRIDGED",
    "STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED",
    "STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED",
    "STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED",
    "STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT",
    # Next allowed step + forbidden surfaces + live ceremony note.
    "STAGE30_11_6_NEXT_ALLOWED_STAGE",
    "STAGE30_11_6_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_6_FORBIDDEN_SURFACES",
    "STAGE30_11_6_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_6_LIVE_CEREMONY_NOTE",
    # ---- Stage 30.11.7 candidate dip-enrichment bridge ----
    # Minor version + enrichment schema identity.
    "STAGE30_11_7_MINOR_VERSION",
    "STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION",
    "STAGE30_11_7_SOURCE_STAGE",
    # Basenames + module paths.
    "STAGE30_11_7_ENRICHMENT_MODELS_BASENAME",
    "STAGE30_11_7_ENRICHMENT_ADAPTER_BASENAME",
    "STAGE30_11_7_FAKE_ENRICHMENT_PROOF_BASENAME",
    "STAGE30_11_7_ENRICHMENT_MODELS_MODULE",
    "STAGE30_11_7_ENRICHMENT_ADAPTER_MODULE",
    "STAGE30_11_7_FAKE_ENRICHMENT_PROOF_MODULE",
    # Inventory + scanned + test basenames.
    "STAGE30_11_7_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_11_7_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_11_7_TEST_BASENAMES",
    # Import allowlists + the test-composed committed runner module.
    "STAGE30_11_7_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_11_7_ALLOWED_PHX2_IMPORTS",
    "STAGE30_11_7_TEST_COMPOSES_STAGE30_11_5_FAKE_LIVE_WIRING_PROOF_MODULE",
    # Enrichment decisions + reasons + dimensions.
    "STAGE30_11_7_ENRICHMENT_DECISIONS",
    "STAGE30_11_7_ENRICHMENT_PASS_DECISION",
    "STAGE30_11_7_ENRICHMENT_REASONS",
    "STAGE30_11_7_ENRICHMENT_PASS_REASON",
    "STAGE30_11_7_ENRICHMENT_DIMENSIONS",
    # Enriched + model + resolver field tuples.
    "STAGE30_11_7_ENRICHED_FIELDS",
    "STAGE30_11_7_REQUIRED_ENRICHED_FIELDS",
    "STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS",
    "STAGE30_11_7_ENRICHMENT_RESULT_FIELDS",
    "STAGE30_11_7_ENRICHMENT_SUMMARY_FIELDS",
    "STAGE30_11_7_ENRICHMENT_RUN_RESULT_FIELDS",
    "STAGE30_11_7_MARKET_CONTEXT_RESOLUTION_FIELDS",
    "STAGE30_11_7_TIER_RESOLUTION_FIELDS",
    "STAGE30_11_7_MIGRATION_RESOLUTION_FIELDS",
    "STAGE30_11_7_ATH_RESOLUTION_FIELDS",
    # PRESENT token + hard cap + default.
    "STAGE30_11_7_CONTEXT_STATUS_PRESENT",
    "STAGE30_11_7_MAX_ENRICH_HARD_CAP",
    "STAGE30_11_7_DEFAULT_MAX_ENRICH",
    # Expected proof counts.
    "STAGE30_11_7_EXPECTED_BASES_SEEN",
    "STAGE30_11_7_EXPECTED_ENRICHED",
    "STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT",
    "STAGE30_11_7_EXPECTED_REJECTED_TIER",
    "STAGE30_11_7_EXPECTED_REJECTED_MIGRATION",
    "STAGE30_11_7_EXPECTED_REJECTED_ATH",
    "STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN",
    "STAGE30_11_7_EXPECTED_RUNNER_BRIDGED",
    "STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED",
    "STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT",
    # Next allowed step + forbidden surfaces + live ceremony note.
    "STAGE30_11_7_NEXT_ALLOWED_STAGE",
    "STAGE30_11_7_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_11_7_FORBIDDEN_SURFACES",
    "STAGE30_11_7_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_11_7_LIVE_CEREMONY_NOTE",
)
