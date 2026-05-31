"""Stage 30.9.0 bounded private live compact session bridge spec-lock
manifest.

Constants-only spec-lock manifest. Pins the Stage 30.9.0 inventory (the
spec-lock doc basename + path parts, this manifest basename, the test
basename), the Stage 30.9 stage id + spec version + next allowed substage,
the planned Stage 30.9.0 / 30.9.1 / 30.9.2 substage sequence, the existing
bounded private live compact engine reuse surfaces (by exact name), the
future Stage 30.9.1 artifact-bridge required surfaces, the gating
requirements, the dedupe stance, the Stage 30.8 compact ping artifact
identity fields, the forbidden surfaces the spec-lock slice must not
touch, and the forbidden runtime imports / text needles the spec-lock
files are scanned against.

Stage 30.9 is a bounded private live compact session bridge. The most
important planning finding is that the bounded private live compact-ping
chain ALREADY EXISTS and has already run live in earlier proof stages:
``run_stage30_4_2_compact_runtime_session`` ->
``run_stage30_3_compact_runtime_session`` ->
``run_stage28_9_live_provider_session`` ->
``Stage28_6BoundedPrivateSessionRunner`` ->
``Stage28_9PrivateWebhookTransport`` / the Stage 28.4 audited HTTP
transport, gated by ``evaluate_stage28_9_readiness`` over a
``Stage28_9LiveProviderSessionConfig``. Stage 30.9 does NOT build a new
live runner and does NOT reimplement readiness gates. The only missing
capability is persisting Stage 30.8-format compact session artifacts from
a live-shaped session and proving retained / duplicate / invalid over
them. Stage 30.9.0 LOCKS that design as prose + constants; it ships NO
runtime code, NO artifact bridge, NO capture transport, NO post-session
projector, NO live provider call, NO Discord send, and edits NO existing
live runner / orchestrator / transport / Stage 30.8 implementation file.

Stage 30.9.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this constants-only manifest.
  * ZERO runtime code, ZERO artifact bridge, ZERO capture transport, ZERO
    post-session projector, ZERO Stage 30.8 writer / reader / index
    invocation.
  * ZERO new live runner, ZERO new readiness gate, ZERO live provider
    call, ZERO Discord send, ZERO env read.
  * ZERO database / SQLite, ZERO zstd dependency / implementation, ZERO
    compression, ZERO default storage root, ZERO background daemon.
  * ZERO public / subscriber / paid routing, ZERO Telegram / X / social,
    ZERO trading / wallet / signing, ZERO enforcement, ZERO Stage 31.
  * ZERO edit to any existing live runner / orchestrator / transport file
    and ZERO edit to any Stage 30.8 implementation file (the Stage 30.0
    inventory allowlist widening excepted).

Stage 30.9.1+ scope (deferred, each separately operator-authorized):

  * 30.9.1 -- the artifact bridge with fakes / offline: capture transport
    + post-session projector + Stage 30.8 bundle write + Stage 30.8
    reader / index proof; fake provider / fake Discord tests only.
  * 30.9.2 -- the live proof doc / operator runbook / closure handoff:
    no new runtime unless explicitly authorized; an operator-driven
    bounded live proof out-of-repo; private Discord only.

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


STAGE30_9_STAGE_ID: str = "30.9"
STAGE30_9_0_MINOR_VERSION: str = "30.9.0"
STAGE30_9_0_SPEC_VERSION: str = "stage30_9_v0_bounded_private_live_compact"


# ---------------------------------------------------------------------------
# Locked basenames + path parts + inventory delta
# ---------------------------------------------------------------------------


STAGE30_9_SPEC_LOCK_FILENAME: str = (
    "STAGE_30_9_0_BOUNDED_PRIVATE_LIVE_COMPACT_SPEC_LOCK.md"
)
STAGE30_9_MANIFEST_BASENAME: str = "stage30_9_manifest.py"


# The repo-relative path parts of the spec-lock doc (so a pin test can
# join them without re-spelling the path).
STAGE30_9_SPEC_LOCK_PATH_PARTS: Tuple[str, ...] = (
    "PHX2",
    "stage30",
    STAGE30_9_SPEC_LOCK_FILENAME,
)


STAGE30_9_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_9_0_bounded_private_live_compact_spec_lock.py",
)


# The NEW files Stage 30.9.0 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.8.4 inventory: exactly the spec-lock
# markdown plus this constants-only manifest. NO production .py beyond the
# manifest at Stage 30.9.0; NO Stage 30.9.1+ bridge / capture / projector
# file.
STAGE30_9_ALLOWED_INITIAL_FILES: Tuple[str, ...] = (
    STAGE30_9_SPEC_LOCK_FILENAME,
    STAGE30_9_MANIFEST_BASENAME,
)


# The only NEW production .py Stage 30.9.0 adds is this constants-only
# manifest; the spec lock is markdown. The boundary scan checks this
# basename for forbidden imports / needles.
STAGE30_9_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_MANIFEST_BASENAME,
)


# Every non-PHX2 import in this manifest must be in this stdlib allowlist
# (the manifest is constants-only: it needs only ``__future__`` +
# ``typing``). The spec-lock slice has NO PHX2 production import at all.
STAGE30_9_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# ---------------------------------------------------------------------------
# Planned substage sequence + next allowed stage
# ---------------------------------------------------------------------------
#
# Stage 30.9 is sequenced fake / offline before live, smallest reversible
# slice first. Exactly three planned substages; each separately
# operator-authorized.


STAGE30_9_PLANNED_SUBSTAGES: Tuple[str, ...] = (
    "30.9.0",
    "30.9.1",
    "30.9.2",
)


STAGE30_9_NEXT_ALLOWED_STAGE: str = "30.9.1"
STAGE30_9_NEXT_ALLOWED_STAGE_TITLE: str = (
    "artifact bridge with fakes / offline (capture transport + "
    "post-session projector + Stage 30.8 bundle write + reader / index "
    "proof; fake provider / fake Discord tests only)"
)


# ---------------------------------------------------------------------------
# Existing engine reuse surfaces (by exact name)
# ---------------------------------------------------------------------------
#
# Stage 30.9 MUST reuse the existing bounded private live compact engine.
# It introduces NO new live loop. These are existing production
# function / class / family names (not secrets, not hosts, not transport
# destinations).


STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES: Tuple[str, ...] = (
    "run_stage30_4_2_compact_runtime_session",
    "run_stage30_3_compact_runtime_session",
    "run_stage28_9_live_provider_session",
    "evaluate_stage28_9_readiness",
    "Stage28_9LiveProviderSessionConfig",
    "Stage28_9PrivateWebhookTransport",
    "Stage 28.4 audited HTTP transport",
    "Stage28_6BoundedPrivateSessionRunner",
    "Stage 27.6 / Stage 28.2 runtime dedupe / dispatch ledger",
)


# ---------------------------------------------------------------------------
# Stage 30.9.1 artifact-bridge required surfaces (locked design)
# ---------------------------------------------------------------------------
#
# The Stage 30.9.1 artifact bridge is two pieces: a thin innermost capture
# transport and a post-session projector. These name the locked design
# surfaces; Stage 30.9.0 implements none of them. ``webhook_identity`` is
# the safe-shape identity the capture transport records (never the
# destination).


STAGE30_9_ARTIFACT_BRIDGE_REQUIRED_SURFACES: Tuple[str, ...] = (
    "thin innermost capture transport",
    "wraps inner_transport",
    "records webhook_identity",
    "records enriched payload content exactly as sent",
    "records sanitized transport result",
    "forwards the payload verbatim",
    "no payload mutation",
    "no filesystem I/O in capture transport",
    "no network except delegated inner_transport",
    "post-session projector",
    "joins capture records with Stage 28.9 / Stage 28.2 dispatch ledger",
    "obtains dedupe_key from runtime dispatch ledger",
    "emits Stage 30.8.1 model types",
    "write_compact_session_artifact_bundle",
    "read_compact_session_bundle",
    "build_compact_session_index",
    "post-session only writes",
    "no per-ping Stage 30.8 writer call",
    "Stage 30.8 index is post-run proof only",
)


# ---------------------------------------------------------------------------
# Gating requirements (reused, not redefined)
# ---------------------------------------------------------------------------
#
# Stage 30.9 reuses the existing readiness gate + bounded caps unchanged.
# The ``private_webhook_url`` gating field is named in its underscore code
# form (not a transport destination). ``max_runtime_seconds`` is NOT
# supported on this compact path unless an existing ``stop_signal`` path is
# driven externally; Stage 30.9 invents no wall-clock loop / daemon.


STAGE30_9_GATING_REQUIREMENTS: Tuple[str, ...] = (
    "live_env_ready must be explicit True",
    "live_operator_request must be explicit True",
    "private_webhook_url must be private / non-empty / shape-safe",
    "output_dir must be explicit and safe",
    "output_dir must remain outside repo when readiness requires it",
    "max_events > 0",
    "max_dispatches > 0",
    "max_ticks > 0 if used",
    "max_total_retries bounded",
    "DRY_RUN vs LIVE_PRIVATE separation via session_mode",
    "no default storage root",
    (
        "max_runtime_seconds NOT supported except external stop_signal "
        "path"
    ),
)


# The closed-set session-mode tokens carried by the existing config
# (mirrored by value; the manifest imports no Stage 28 module).
STAGE30_9_SESSION_MODE_VALUES: Tuple[str, ...] = (
    "DRY_RUN",
    "LIVE_PRIVATE",
)


# ---------------------------------------------------------------------------
# Dedupe stance (locked)
# ---------------------------------------------------------------------------
#
# Runtime dedupe remains Stage 27.6 + Stage 28.2. The Stage 30.8 dedupe
# index remains post-run proof only. The ``dedupe_key`` is carried into the
# Stage 30.8 compact ping artifacts (sourced from the runtime dispatch
# ledger). No new DB-backed dedupe; no cross-session runtime dedupe.


STAGE30_9_DEDUPE_STANCE: Tuple[str, ...] = (
    "runtime dedupe = Stage 27.6 + Stage 28.2",
    "Stage 30.8 dedupe index = post-run proof only",
    "dedupe_key carried into Stage 30.8 compact ping artifacts",
    "dedupe_key sourced from runtime dispatch ledger",
    "no new DB-backed dedupe",
    "no cross-session runtime dedupe in Stage 30.9",
)


# The post-session per-ping dedupe status closed set reused from Stage
# 30.8.3 (mirrored by value).
STAGE30_9_PING_DEDUPE_STATUS_VALUES: Tuple[str, ...] = (
    "RETAINED",
    "DUPLICATE_SUPPRESSED",
    "INVALID_SUPPRESSED",
)


# ---------------------------------------------------------------------------
# Stage 30.8 compact ping artifact identity fields (closed set)
# ---------------------------------------------------------------------------
#
# The stable identity every persisted Stage 30.8 compact ping artifact
# carries in a Stage 30.9 live-shaped session. Each is a safe-shape opaque
# id / closed-set token / ISO-8601 UTC timestamp. NONE is a secret, a raw
# payload, a host, or a transport destination.


STAGE30_9_ARTIFACT_IDENTITY_FIELDS: Tuple[str, ...] = (
    "run_id",
    "session_id",
    "ping_id",
    "candidate_id",
    "token_mint",
    "dedupe_key",
    "artifact_created_at_utc",
    "artifact_kind",
)


# The locked provenance / sourcing rules for the identity fields above
# (safe paraphrase labels).
STAGE30_9_ARTIFACT_FIELD_PROVENANCE: Tuple[str, ...] = (
    "dedupe_key from runtime dispatch ledger, not recomputed ad hoc",
    "session_id / run_id from Stage28_9LiveProviderSessionConfig",
    "ping_id / candidate_id from the live candidate / adapter path",
    "compact body captured from the enriched payload actually sent",
)


# ---------------------------------------------------------------------------
# Failure behavior (fail-closed, locked)
# ---------------------------------------------------------------------------


STAGE30_9_FAILURE_BEHAVIOR: Tuple[str, ...] = (
    "readiness failure => no provider call, no Discord send",
    "provider failure => bounded, no crash",
    "Discord failure => closed-set transport failure, no crash",
    "writer failure => artifact proof failure, sent pings unaffected",
    "reader / index failure => artifact proof failure",
    "missing dedupe_key => invalid artifact proof",
    "duplicate candidate => runtime suppressed before send",
    "invalid / unknown pair => runtime suppressed before send",
    "cap hit => clean bounded stop",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.9 family (and the Stage 30.9.0 spec-lock slice)
# must not touch. Plain documentation words (family / feature names), NOT
# secret / host / transport needle forms.


STAGE30_9_FORBIDDEN_SURFACES: Tuple[str, ...] = (
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
    "broad always-on daemon",
    "background service",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "default storage root",
    "inline per-ping Stage 30.8 writes",
    "new live runner",
    "new readiness gate",
    "live run",
    "provider call",
    "Discord send",
    "env read",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "Stage 30.8 implementation edit",
    "Stage 25/27/28/29 production import",
    "Stage 29.5 production import",
    "commit",
    "tag",
    "push",
    "Stage 31",
    "Stage 30.9.1+ implementation file",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.9.0 pin test walks the actual import lines of the Stage
# 30.9.0 Python files (this manifest + the pin test) and asserts none
# resolve to a module covered by this policy. The strings below are plain
# (the line-based scan never substring-matches them against source text).


STAGE30_9_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces the Stage 30.9.0 spec-lock files must not touch.
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
    # No zstd implementation / dependency at Stage 30.9.0 (docs + tests may
    # name the WORD ``zstd``; no module import is allowed).
    "import zstandard",
    "from zstandard",
    "import zstd",
    "from zstd",
    # Stage 21-29 production surfaces (incl. Stage 29.5).
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
# 30.9.0 pin test imports this tuple at runtime and scans every Stage
# 30.9.0 file (spec lock, manifest, test) case-insensitively for substring
# matches against the runtime-concatenated values. The spec doc paraphrases
# every secret / transport surface (for example "provider credential",
# "private transport destination", "transport scheme prefix") so it carries
# none of the bare needles.


STAGE30_9_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# Stage 30.9.1 artifact bridge inventory (capture transport + projector +
# bridge proof + passive models)
# ---------------------------------------------------------------------------
#
# Stage 30.9.1 is the FIRST Stage 30.9 production slice: the offline
# artifact bridge with fakes / offline tests only. It adds four NEW
# production files -- the passive bridge models, the thin innermost capture
# transport, the post-session projector, and the offline write -> read ->
# index proof helper. The bridge persists Stage 30.8-format compact session
# artifacts AFTER a bounded private live-shaped session, then proves
# retained / duplicate / invalid over them. It is NOT a live runner, NOT a
# new readiness gate, NOT a Discord send, NOT a live provider call; it adds
# NO database / SQLite / zstd / compression / default storage root and edits
# NO existing live runner / orchestrator / transport / Stage 30.8
# implementation file. The capture transport + projector + proof carry NO
# Stage 28 import (the dispatch context is a duck-typed / passive Stage
# 30.9.1 carrier). NO Stage 30.9.2+ file ships at Stage 30.9.1.


STAGE30_9_1_MINOR_VERSION: str = "30.9.1"


# Stage 30.9.1 bridge proof summary schema version (mirrored from the
# bridge models module; a pin test cross-checks it matches).
STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION: str = (
    "stage30_9_v0_compact_artifact_bridge_proof"
)


# The four NEW production basenames + their dotted module paths.
STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME: str = (
    "stage30_9_artifact_bridge_models.py"
)
STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME: str = (
    "stage30_9_capture_transport.py"
)
STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME: str = (
    "stage30_9_artifact_projector.py"
)
STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME: str = (
    "stage30_9_artifact_bridge_proof.py"
)


STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_artifact_bridge_models"
)
STAGE30_9_1_CAPTURE_TRANSPORT_MODULE: str = (
    "PHX2.stage30.stage30_9_capture_transport"
)
STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE: str = (
    "PHX2.stage30.stage30_9_artifact_projector"
)
STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_9_artifact_bridge_proof"
)


# The Stage 30.8 sibling module paths the Stage 30.9.1 projector + proof
# compose (re-declared here as literals; the manifest imports no PHX2
# module). These are the ALREADY-EXISTING Stage 30.8.1 / 30.8.2 / 30.8.3
# storage chain surfaces the bridge reuses.
STAGE30_9_1_STAGE30_8_ARTIFACT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_8_artifact_models"
)
STAGE30_9_1_STAGE30_8_TEMP_ARTIFACT_WRITER_MODULE: str = (
    "PHX2.stage30.stage30_8_temp_artifact_writer"
)
STAGE30_9_1_STAGE30_8_SESSION_BUNDLE_READER_MODULE: str = (
    "PHX2.stage30.stage30_8_session_bundle_reader"
)
STAGE30_9_1_STAGE30_8_SESSION_INDEX_BUILDER_MODULE: str = (
    "PHX2.stage30.stage30_8_session_index_builder"
)
STAGE30_9_1_STAGE30_8_SESSION_INDEX_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_8_session_index_models"
)


# The four NEW production files Stage 30.9.1 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.9.0 inventory. NO Stage 30.9.2+
# file.
STAGE30_9_1_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
    STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
    STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
    STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
)


# The four production modules the Stage 30.9.1 boundary test scans for
# forbidden imports / text needles.
STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME,
    STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME,
    STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME,
    STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME,
)


STAGE30_9_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_9_1_artifact_bridge_models.py",
    "test_stage_30_9_1_capture_transport.py",
    "test_stage_30_9_1_artifact_projector.py",
    "test_stage_30_9_1_artifact_bridge_proof.py",
    "test_stage_30_9_1_boundaries.py",
    "test_stage_30_9_1_manifest.py",
)


# Every non-PHX2 import in a Stage 30.9.1 production module must be in this
# stdlib allowlist (the models need ``dataclasses``; the capture transport /
# projector / proof need only ``typing`` -- the JSON / pathlib I/O all lives
# behind the composed Stage 30.8.2 writer + Stage 30.8.3 reader / builder).
# It admits NO ``os`` (so NO ``os.environ`` / ``os.getenv`` env read), NO
# ``sqlite3``, NO ``zstd`` / compression, and NO network module.
STAGE30_9_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# Every PHX2 import in a Stage 30.9.1 production module must be one of these
# siblings: the Stage 30.9.1 bridge-models + projector siblings plus the
# already-existing Stage 30.8.1 / 30.8.2 / 30.8.3 storage-chain siblings the
# bridge reuses. This positive allowlist proves, by construction, that NO
# Stage 21-29 (incl. Stage 28 / 29.5) / runtime / orchestrator / renderer /
# Discord / provider module is imported (the dispatch context is a passive
# Stage 30.9.1 carrier, not a Stage 28 import).
STAGE30_9_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE,
    STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE,
    STAGE30_9_1_STAGE30_8_ARTIFACT_MODELS_MODULE,
    STAGE30_9_1_STAGE30_8_TEMP_ARTIFACT_WRITER_MODULE,
    STAGE30_9_1_STAGE30_8_SESSION_BUNDLE_READER_MODULE,
    STAGE30_9_1_STAGE30_8_SESSION_INDEX_BUILDER_MODULE,
    STAGE30_9_1_STAGE30_8_SESSION_INDEX_MODELS_MODULE,
)


# Closed-set bridge status tokens (mirrored from the bridge models module).
STAGE30_9_1_BRIDGE_STATUS_VALUES: Tuple[str, ...] = (
    "CAPTURED",
    "PROJECTED",
    "WRITTEN_AND_INDEXED",
    "INVALID_INPUT",
    "PROJECT_FAILED",
    "WRITE_FAILED",
    "READ_FAILED",
    "INDEX_FAILED",
)


# Closed-set bridge reason tokens (mirrored from the bridge models module).
STAGE30_9_1_BRIDGE_REASON_VALUES: Tuple[str, ...] = (
    "NONE",
    "MISSING_RUN_ID",
    "MISSING_SESSION_ID",
    "MISSING_PING_ID",
    "MISSING_CANDIDATE_ID",
    "MISSING_TOKEN_MINT",
    "MISSING_DEDUPE_KEY",
    "MISSING_COMPACT_BODY",
    "MISSING_CAPTURE_INDEX",
    "COUNT_MISMATCH",
    "AMBIGUOUS_JOIN",
    "NON_PRIVATE_WEBHOOK",
    "WRITER_REJECTED",
    "READER_REJECTED",
    "INDEX_REJECTED",
)


# The safe private webhook identity label allowlist (mirrored from the
# bridge models module BY VALUE; mirrors the Stage 28.4 private-operator
# label without importing any Stage 28 module).
STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES: Tuple[str, ...] = (
    "PRIVATE_OPERATOR_WEBHOOK",
)


# The two deterministic fake bridge scenario names (mirrored from the
# bridge models module).
STAGE30_9_1_DEFAULT_SCENARIO_NAME: str = "stage30_9_1_default_dedupe_bridge"
STAGE30_9_1_MISMATCH_SCENARIO_NAME: str = (
    "stage30_9_1_mismatch_dedupe_bridge"
)


# The author-verified expected post-run index counts for the two scenarios
# (mirrored from the bridge models module; a pin test cross-checks them).
STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT: int = 3
STAGE30_9_1_DEFAULT_EXPECTED_RETAINED: int = 2
STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED: int = 1
STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED: int = 0

STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT: int = 4
STAGE30_9_1_MISMATCH_EXPECTED_RETAINED: int = 2
STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED: int = 1
STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED: int = 1


# ---------------------------------------------------------------------------
# Stage 30.9.1 forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.9.1 artifact-bridge slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host /
# transport needle forms. The bridge DOES write ONE Stage 30.8 bundle to a
# caller-provided temp dir (through the Stage 30.8.2 writer) and read /
# index it back (that is the slice); it must not reach any surface below.


STAGE30_9_1_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "live provider call",
    "real Discord send",
    "real bot artifact directory",
    "default storage root",
    "per-ping Stage 30.8 write",
    "new live runner",
    "new readiness gate",
    "wall-clock daemon",
    "background service",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
    "zstd dependency",
    "compression implementation",
    "env read",
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
    "Stage 30.8 implementation edit",
    "Stage 25/27/28/29 production import",
    "Stage 29.5 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.9.2+ implementation file",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Stage 30.9.1 next allowed stage
# ---------------------------------------------------------------------------
#
# After Stage 30.9.1 (the offline artifact bridge) the next allowed slice is
# Stage 30.9.2 (the live proof doc / operator runbook / closure handoff,
# separately operator-gated). The Stage 30.9.0 family pointer
# ``STAGE30_9_NEXT_ALLOWED_STAGE`` stays pinned at ``30.9.1``; this
# 30.9.1-scoped pointer names the slice that follows. NO Stage 30.9.2 file
# ships at Stage 30.9.1.


STAGE30_9_1_NEXT_ALLOWED_STAGE: str = "30.9.2"
STAGE30_9_1_NEXT_ALLOWED_STAGE_TITLE: str = (
    "live proof doc / operator runbook / closure handoff (operator-driven "
    "bounded live proof out-of-repo; private Discord only; no new runtime "
    "unless explicitly authorized)"
)


__all__ = (
    # Stage id + minor version + spec version.
    "STAGE30_9_STAGE_ID",
    "STAGE30_9_0_MINOR_VERSION",
    "STAGE30_9_0_SPEC_VERSION",
    # Locked basenames + path parts + inventory delta.
    "STAGE30_9_SPEC_LOCK_FILENAME",
    "STAGE30_9_MANIFEST_BASENAME",
    "STAGE30_9_SPEC_LOCK_PATH_PARTS",
    "STAGE30_9_0_TEST_BASENAMES",
    "STAGE30_9_ALLOWED_INITIAL_FILES",
    "STAGE30_9_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_9_ALLOWED_STDLIB_IMPORTS",
    # Planned substages + next allowed stage.
    "STAGE30_9_PLANNED_SUBSTAGES",
    "STAGE30_9_NEXT_ALLOWED_STAGE",
    "STAGE30_9_NEXT_ALLOWED_STAGE_TITLE",
    # Existing engine reuse + artifact-bridge surfaces.
    "STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES",
    "STAGE30_9_ARTIFACT_BRIDGE_REQUIRED_SURFACES",
    # Gating + session modes.
    "STAGE30_9_GATING_REQUIREMENTS",
    "STAGE30_9_SESSION_MODE_VALUES",
    # Dedupe stance + status tokens.
    "STAGE30_9_DEDUPE_STANCE",
    "STAGE30_9_PING_DEDUPE_STATUS_VALUES",
    # Artifact identity + provenance.
    "STAGE30_9_ARTIFACT_IDENTITY_FIELDS",
    "STAGE30_9_ARTIFACT_FIELD_PROVENANCE",
    # Failure behavior.
    "STAGE30_9_FAILURE_BEHAVIOR",
    # Forbidden surfaces.
    "STAGE30_9_FORBIDDEN_SURFACES",
    # Forbidden imports + needles.
    "STAGE30_9_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_9_FORBIDDEN_TEXT_NEEDLES",
    # Stage 30.9.1 artifact bridge inventory.
    "STAGE30_9_1_MINOR_VERSION",
    "STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION",
    "STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_BASENAME",
    "STAGE30_9_1_CAPTURE_TRANSPORT_BASENAME",
    "STAGE30_9_1_ARTIFACT_PROJECTOR_BASENAME",
    "STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_BASENAME",
    "STAGE30_9_1_ARTIFACT_BRIDGE_MODELS_MODULE",
    "STAGE30_9_1_CAPTURE_TRANSPORT_MODULE",
    "STAGE30_9_1_ARTIFACT_PROJECTOR_MODULE",
    "STAGE30_9_1_ARTIFACT_BRIDGE_PROOF_MODULE",
    "STAGE30_9_1_STAGE30_8_ARTIFACT_MODELS_MODULE",
    "STAGE30_9_1_STAGE30_8_TEMP_ARTIFACT_WRITER_MODULE",
    "STAGE30_9_1_STAGE30_8_SESSION_BUNDLE_READER_MODULE",
    "STAGE30_9_1_STAGE30_8_SESSION_INDEX_BUILDER_MODULE",
    "STAGE30_9_1_STAGE30_8_SESSION_INDEX_MODELS_MODULE",
    "STAGE30_9_1_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_9_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_9_1_TEST_BASENAMES",
    "STAGE30_9_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_9_1_ALLOWED_PHX2_IMPORTS",
    "STAGE30_9_1_BRIDGE_STATUS_VALUES",
    "STAGE30_9_1_BRIDGE_REASON_VALUES",
    "STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES",
    "STAGE30_9_1_DEFAULT_SCENARIO_NAME",
    "STAGE30_9_1_MISMATCH_SCENARIO_NAME",
    "STAGE30_9_1_DEFAULT_EXPECTED_PING_COUNT",
    "STAGE30_9_1_DEFAULT_EXPECTED_RETAINED",
    "STAGE30_9_1_DEFAULT_EXPECTED_DUPLICATE_SUPPRESSED",
    "STAGE30_9_1_DEFAULT_EXPECTED_INVALID_SUPPRESSED",
    "STAGE30_9_1_MISMATCH_EXPECTED_PING_COUNT",
    "STAGE30_9_1_MISMATCH_EXPECTED_RETAINED",
    "STAGE30_9_1_MISMATCH_EXPECTED_DUPLICATE_SUPPRESSED",
    "STAGE30_9_1_MISMATCH_EXPECTED_INVALID_SUPPRESSED",
    "STAGE30_9_1_FORBIDDEN_SURFACES",
    "STAGE30_9_1_NEXT_ALLOWED_STAGE",
    "STAGE30_9_1_NEXT_ALLOWED_STAGE_TITLE",
)
