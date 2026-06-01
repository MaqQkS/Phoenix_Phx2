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


# ---------------------------------------------------------------------------
# Stage 30.9.2_RESUME -- dip-filtered live proof planning / fake-proof slice
# ---------------------------------------------------------------------------
#
# Stage 30.9.2 was PAUSED, not abandoned. With the completed Stage 30.10
# dip-gate stack (30.10.1 offline classifier -> 30.10.2 pre-dispatch gate ->
# 30.10.3 artifact projection) now proving dip-focused eligibility offline,
# Stage 30.9.2 is UNPAUSED -- but only as a dip-FILTERED live proof path, and
# only for PLANNING / fake proof in THIS slice. The slice adds three NEW
# leaf production modules -- the passive resume models (the dip-filtered
# resume plan + per-candidate proof record + resume proof summary, importing
# no PHX2 module), the pure plan builder (a planning-only plan that holds
# every live-affecting axis closed), and a fake / offline proof that composes
# the committed Stage 30.10.2 fake gate scenario -> the real gate -> the Stage
# 30.10.3 projector -> the Stage 30.9.2 resume records + summary. It ships
# ZERO live run, ZERO live provider call, ZERO Discord send, ZERO env read,
# ZERO real provider key use, ZERO real WebSocket / gRPC / HTTP provider
# session, ZERO dispatch reservation, ZERO filesystem write, ZERO
# transport-layer gate / PAYLOAD_REFUSED for a normal non-dip skip, ZERO
# database / SQLite / zstd / compression, ZERO default storage root, ZERO
# runtime orchestrator wiring, and edits NO Stage 28 suppression / Stage 30.3
# / Stage 30.4 runtime orchestrator. These constants pin the Stage 30.9.2
# inventory + import allowlists + the required dip-gate stack + the resume
# schema version + the resume plan / record / summary field names + the fake
# proof expected counts + the planning-only gating flags, and pin that the
# next allowed step is a CONTROLLED dip-filtered live ceremony that is
# explicitly operator-authorized (NOT an automatic live execution, NOT a
# Stage 30.10.4 -- there is no Stage 30.10.4). The Stage 30.9.0 family pointer
# STAGE30_9_NEXT_ALLOWED_STAGE stays pinned at 30.9.1; the 30.9.1-scoped
# pointer stays pinned at 30.9.2.


STAGE30_9_2_MINOR_VERSION: str = "30.9.2"


# The Stage 30.9.2_RESUME token (mirrors the Stage 30.10.3
# STAGE30_10_3_NEXT_ALLOWED_STAGE value BY VALUE; this manifest imports no
# Stage 30.10 manifest).
STAGE30_9_2_RESUME_ID: str = "30.9.2_RESUME"


# The prior stage this resume builds on: the final Stage 30.10 fake / offline
# proof.
STAGE30_9_2_PRIOR_STAGE: str = "30.10.3"


# The committed HEAD the Stage 30.9.2_RESUME plan is built against -- the
# Stage 30.10.3 fake gate artifact integration proof commit (mirrored BY VALUE
# from the resume plan module; a safe-shape hex id, never a secret).
STAGE30_9_2_REQUIRED_HEAD_SHA: str = (
    "e35e54b69668814d2ab8c096855f682c68ada8ab"
)


# The Stage 30.9.2 dip-filtered resume proof schema version (mirrored BY VALUE
# by the Stage 30.9.2 resume-models module; distinct from the Stage 30.8 /
# 30.9.1 / 30.10.3 schema versions).
STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION: str = (
    "stage30_9_2_v0_dip_filtered_resume_proof"
)


# The required dip-gate stack the resume plan names (mirrored BY VALUE by the
# Stage 30.9.2 resume-models module). The dip-filtered live proof may proceed
# only AFTER this committed Stage 30.10 stack has ruled each candidate.
STAGE30_9_2_GATE_STACK_REQUIRED: Tuple[str, ...] = (
    "30.10.1 offline tier-dip eligibility classifier",
    "30.10.2 optional pre-dispatch tier-dip gate",
    "30.10.3 gate artifact projection",
)


# The three NEW Stage 30.9.2 production modules + their import paths.
STAGE30_9_2_RESUME_MODELS_BASENAME: str = (
    "stage30_9_2_resume_dip_filtered_live_models.py"
)
STAGE30_9_2_RESUME_PLAN_BASENAME: str = (
    "stage30_9_2_resume_dip_filtered_live_plan.py"
)
STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME: str = (
    "stage30_9_2_resume_fake_proof.py"
)
STAGE30_9_2_RESUME_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models"
)
STAGE30_9_2_RESUME_PLAN_MODULE: str = (
    "PHX2.stage30.stage30_9_2_resume_dip_filtered_live_plan"
)
STAGE30_9_2_RESUME_FAKE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_9_2_resume_fake_proof"
)


# The ALREADY-EXISTING Stage 30.10.3 sibling module paths the Stage 30.9.2
# fake proof composes (re-declared here as literals; the manifest imports no
# PHX2 module). These are the committed gate-stack surfaces the resume reuses.
STAGE30_9_2_STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_10_3_fake_artifact_proof"
)
STAGE30_9_2_STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_3_gate_artifact_models"
)


# The three NEW production files Stage 30.9.2 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.10.3 inventory. NO Stage 30.9.3+
# file; NO Stage 30.10.4 file.
STAGE30_9_2_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_2_RESUME_MODELS_BASENAME,
    STAGE30_9_2_RESUME_PLAN_BASENAME,
    STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME,
)
STAGE30_9_2_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_2_RESUME_MODELS_BASENAME,
    STAGE30_9_2_RESUME_PLAN_BASENAME,
    STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME,
)


# The Stage 30.9.2 test inventory.
STAGE30_9_2_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_9_2_resume_dip_filtered_live_models.py",
    "test_stage_30_9_2_resume_dip_filtered_live_plan.py",
    "test_stage_30_9_2_resume_fake_proof.py",
    "test_stage_30_9_2_resume_boundaries.py",
    "test_stage_30_9_2_resume_manifest.py",
)


# The positive stdlib import allowlist for the Stage 30.9.2 production modules
# (the resume models need ``dataclasses`` / ``typing``; the plan needs
# ``typing``; the fake proof needs ``typing``). NO ``os`` / no network / no
# database / no compression / no ``decimal`` module is allowlisted (the fake
# proof reuses the already-built Stage 30.10 scenario, so it constructs no
# ``Decimal`` of its own).
STAGE30_9_2_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# The positive PHX2 import allowlist: the resume models import NO PHX2 module;
# the plan imports the Stage 30.9.2 resume-models sibling; the fake proof
# imports the Stage 30.9.2 resume-models + resume-plan siblings + the Stage
# 30.10.3 fake-artifact-proof + gate-artifact-models siblings. No Stage 21-29 /
# Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live runner /
# provider / transport module is allowlisted.
STAGE30_9_2_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_9_2_RESUME_MODELS_MODULE,
    STAGE30_9_2_RESUME_PLAN_MODULE,
    STAGE30_9_2_STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE,
    STAGE30_9_2_STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE,
)


# The Stage 30.9.2 resume plan / candidate proof record / resume proof summary
# field names (mirrored BY VALUE by the Stage 30.9.2 resume-models module;
# ``created_at_utc`` is caller-injected, never a wall-clock read; NONE is a
# secret, a raw payload, a host, or a transport destination).
STAGE30_9_2_RESUME_PLAN_FIELDS: Tuple[str, ...] = (
    "resume_id",
    "required_head_sha",
    "prior_stage",
    "gate_stack_required",
    "live_allowed",
    "dispatch_allowed",
    "env_read_allowed",
    "provider_call_allowed",
    "discord_send_allowed",
    "created_at_utc",
)
STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "eligibility_decision",
    "eligibility_reason",
    "gate_decision",
    "gate_reason",
    "artifact_schema_version",
    "dispatch_reservation_would_be_attempted",
    "suppressed_before_dispatch_reservation",
    "dispatch_failure_recorded",
    "transport_veto_used",
    "payload_refused_used",
    "created_at_utc",
)
STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS: Tuple[str, ...] = (
    "resume_id",
    "candidates_seen",
    "candidates_passed",
    "candidates_skipped",
    "invalid_inputs",
    "dispatch_attempts_reserved",
    "dispatch_attempts_suppressed_before_reservation",
    "dispatch_failures_recorded",
    "transport_veto_count",
    "payload_refused_count",
    "live_allowed",
    "provider_call_allowed",
    "discord_send_allowed",
    "created_at_utc",
)


# The planning-only gating flags the Stage 30.9.2 resume plan / proof hold
# closed in THIS slice (the actual live ceremony is a separate,
# operator-authorized step).
STAGE30_9_2_PLANNING_LIVE_ALLOWED: bool = False
STAGE30_9_2_PLANNING_DISPATCH_ALLOWED: bool = False
STAGE30_9_2_PLANNING_ENV_READ_ALLOWED: bool = False
STAGE30_9_2_PLANNING_PROVIDER_CALL_ALLOWED: bool = False
STAGE30_9_2_PLANNING_DISCORD_SEND_ALLOWED: bool = False


# The author-verified expected Stage 30.9.2 resume fake proof counts over the
# SAME deterministic nine-candidate scenario as the Stage 30.10.2 / 30.10.3
# fake proofs: nine candidate proof records, three that would proceed toward
# the private compact dispatch, six suppressed BEFORE reservation, and zero
# dispatch failures / transport vetoes / ``PAYLOAD_REFUSED`` uses -- with the
# live / provider / Discord gating flags all held closed.
STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN: int = 9
STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED: int = 3
STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED: int = 5
STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS: int = 1
STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED: int = 3
STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_SUPPRESSED_BEFORE_RESERVATION: int = (
    6
)
STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED: int = 0
STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT: int = 0
STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT: int = 0
STAGE30_9_2_FAKE_PROOF_EXPECTED_LIVE_ALLOWED: bool = False
STAGE30_9_2_FAKE_PROOF_EXPECTED_PROVIDER_CALL_ALLOWED: bool = False
STAGE30_9_2_FAKE_PROOF_EXPECTED_DISCORD_SEND_ALLOWED: bool = False


# The Stage 30.9.2 resume status (unpaused for planning / fake proof only).
STAGE30_9_2_RESUME_STATUS: str = (
    "unpaused for dip-filtered planning / fake proof only"
)


# The actual Stage 30.9.2 dip-filtered live ceremony remains a SEPARATE,
# explicitly operator-authorized step (this slice implements no part of it).
STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_9_2_RESUME_NOTE: str = (
    "Stage 30.10.3 remains the final Stage 30.10 fake / offline proof before "
    "the Stage 30.9.2 resume; Stage 30.9.2 is now unpaused for dip-filtered "
    "planning / fake proof only, and its actual dip-filtered private compact "
    "live ceremony remains a separate, explicitly operator-authorized step"
)


# After this planning / fake-proof slice, the next allowed step is a
# CONTROLLED dip-filtered private compact live ceremony that is explicitly
# operator-authorized -- NOT an automatic live execution and NOT a Stage
# 30.10.4 (there is no Stage 30.10.4).
STAGE30_9_2_NEXT_ALLOWED_STEP: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE: str = (
    "controlled dip-filtered private compact live ceremony -- a separate, "
    "explicitly operator-authorized step; never an automatic live execution "
    "and never a Stage 30.10.4"
)


# The surfaces the Stage 30.9.2 resume planning / fake-proof slice must not
# touch. Plain documentation words (family / feature names), NOT secret /
# host / transport needle forms.
STAGE30_9_2_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "live run",
    "live provider call",
    "Discord send",
    "env read",
    "real provider key use",
    "real WebSocket / gRPC / HTTP provider session",
    "dispatch reservation",
    "filesystem write",
    "transport-layer gate",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "runtime orchestrator wiring",
    "Stage 28 suppression-logic edit",
    "Stage 30.3 compact orchestrator edit",
    "Stage 30.4 compact orchestrator edit",
    "new live runner",
    "new provider",
    "new readiness gate",
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
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "automatic live execution",
    "Stage 30.10.4+ implementation file",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Stage 30.9.3 -- dip-filtered live dispatch integration seam
# ---------------------------------------------------------------------------
#
# Stage 30.9.3 builds the committed, tested integration SEAM that lets the live
# candidate -> dispatch path enforce the completed Stage 30.10 dip-gate stack
# (30.10.1 classifier -> 30.10.2 pre-dispatch gate -> 30.10.3 artifact
# projection) so ONLY a PASS_TO_DISPATCH candidate may reserve a dispatch /
# drive the private compact send; every SKIP_BEFORE_DISPATCH / INVALID_INPUT
# candidate is suppressed BEFORE dispatch reservation, is never a dispatch
# failure, and never reuses PAYLOAD_REFUSED. It adds four NEW leaf production
# modules -- the passive integration models (the assembled live-candidate input
# + per-candidate live gate decision + rolled-up integration result, importing
# no PHX2 module), the pure adapter (builds the Stage 30.10.1 eligibility input
# from existing live context fields, runs the gate stack, projects a decision),
# the bounded orchestrator (drives the adapter over a candidate stream with an
# injected dispatch sink + max_candidates_evaluated / max_dispatches /
# max_private_discord_sends caps), and a fake / offline integration proof
# (deterministic fake streams + an in-memory recording sink). This is the REAL
# seam the later controlled live ceremony will reuse, but THIS slice ships ZERO
# live run, ZERO live provider call, ZERO Discord send, ZERO env read, ZERO real
# transport dispatch reservation, ZERO filesystem write, ZERO transport-layer
# gate / PAYLOAD_REFUSED for a normal non-dip skip, ZERO database / SQLite /
# zstd / compression, ZERO default storage root, and edits NO Stage 28
# suppression / Stage 30.3 / Stage 30.4 runtime orchestrator -- the slice is a
# leaf (nothing existing imports it). The actual dip-filtered live ceremony
# remains a separate, explicitly operator-authorized step. The Stage 30.9.0
# family pointer STAGE30_9_NEXT_ALLOWED_STAGE stays pinned at 30.9.1 and the
# planned-substage tuple is unchanged (the seam is an additively admitted
# slice).


STAGE30_9_3_MINOR_VERSION: str = "30.9.3"


# The prior stage this integration seam builds on: the Stage 30.9.2 dip-filtered
# resume planning slice (and, by composition, the committed Stage 30.10 dip-gate
# stack it reuses).
STAGE30_9_3_PRIOR_STAGE: str = "30.9.2"


# The Stage 30.9.3 integration schema version (mirrored BY VALUE by the Stage
# 30.9.3 models module; distinct from the Stage 30.9.2 resume proof schema
# version and the Stage 30.10.3 artifact schema version).
STAGE30_9_3_INTEGRATION_SCHEMA_VERSION: str = (
    "stage30_9_3_v0_dip_filtered_live_gate"
)


# The required dip-gate stack the Stage 30.9.3 seam composes (mirrors the Stage
# 30.9.2 STAGE30_9_2_GATE_STACK_REQUIRED value BY VALUE). The seam runs each
# live candidate through exactly this committed Stage 30.10 stack.
STAGE30_9_3_GATE_STACK_REQUIRED: Tuple[str, ...] = (
    "30.10.1 offline tier-dip eligibility classifier",
    "30.10.2 optional pre-dispatch tier-dip gate",
    "30.10.3 gate artifact projection",
)


# The closed-set gate decisions the Stage 30.9.3 decision echoes from the Stage
# 30.10.2 gate (mirrored BY VALUE; this manifest imports no Stage 30.10 module).
# Only PASS_TO_DISPATCH may reserve a dispatch / drive the private compact send.
STAGE30_9_3_GATE_DECISIONS: Tuple[str, ...] = (
    "PASS_TO_DISPATCH",
    "SKIP_BEFORE_DISPATCH",
    "INVALID_INPUT",
)
STAGE30_9_3_DISPATCH_ALLOWED_GATE_DECISION: str = "PASS_TO_DISPATCH"


# The four NEW Stage 30.9.3 production modules + their import paths.
STAGE30_9_3_GATE_MODELS_BASENAME: str = (
    "stage30_9_3_dip_filtered_live_gate_models.py"
)
STAGE30_9_3_GATE_ADAPTER_BASENAME: str = (
    "stage30_9_3_dip_filtered_live_gate_adapter.py"
)
STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME: str = (
    "stage30_9_3_dip_filtered_live_gate_orchestrator.py"
)
STAGE30_9_3_FAKE_PROOF_BASENAME: str = (
    "stage30_9_3_fake_live_gate_integration_proof.py"
)
STAGE30_9_3_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
)
STAGE30_9_3_GATE_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter"
)
STAGE30_9_3_GATE_ORCHESTRATOR_MODULE: str = (
    "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator"
)
STAGE30_9_3_FAKE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_9_3_fake_live_gate_integration_proof"
)


# The ALREADY-EXISTING Stage 30.10 sibling module paths the Stage 30.9.3 adapter
# / orchestrator compose (re-declared here as literals; the manifest imports no
# PHX2 module). These are the committed dip-gate stack surfaces the seam reuses.
STAGE30_9_3_STAGE30_10_1_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_1_tier_dip_eligibility_models"
)
STAGE30_9_3_STAGE30_10_2_GATE_MODULE: str = (
    "PHX2.stage30.stage30_10_2_pre_dispatch_gate"
)
STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_2_pre_dispatch_gate_models"
)
STAGE30_9_3_STAGE30_10_3_PROJECTOR_MODULE: str = (
    "PHX2.stage30.stage30_10_3_gate_artifact_projector"
)
STAGE30_9_3_STAGE30_10_3_ARTIFACT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_3_gate_artifact_models"
)


# The four NEW production files Stage 30.9.3 adds under PHX2/stage30/ on top of
# the already-allowed Stage 30.0..30.9.2 / 30.10.3 inventory. NO Stage 30.9.4+
# file; NO Stage 30.10.4 file.
STAGE30_9_3_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_3_GATE_MODELS_BASENAME,
    STAGE30_9_3_GATE_ADAPTER_BASENAME,
    STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
    STAGE30_9_3_FAKE_PROOF_BASENAME,
)
STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_9_3_GATE_MODELS_BASENAME,
    STAGE30_9_3_GATE_ADAPTER_BASENAME,
    STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME,
    STAGE30_9_3_FAKE_PROOF_BASENAME,
)


# The Stage 30.9.3 test inventory.
STAGE30_9_3_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_9_3_dip_filtered_live_gate_models.py",
    "test_stage_30_9_3_dip_filtered_live_gate_adapter.py",
    "test_stage_30_9_3_dip_filtered_live_gate_orchestrator.py",
    "test_stage_30_9_3_fake_live_gate_integration_proof.py",
    "test_stage_30_9_3_boundaries.py",
    "test_stage_30_9_3_manifest.py",
)


# The positive stdlib import allowlist for the Stage 30.9.3 production modules
# (the models need dataclasses / decimal / typing; the adapter + orchestrator
# need typing; the fake proof needs decimal / typing). NO os / no network / no
# database / no compression module is allowlisted.
STAGE30_9_3_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
)


# The positive PHX2 import allowlist: the Stage 30.9.3 own models + adapter +
# orchestrator modules plus the committed Stage 30.10 dip-gate stack modules the
# adapter / orchestrator compose. The fake-proof module is a leaf entry point
# (nothing imports it), so its module path is NOT in this import allowlist. No
# Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression /
# live runner / provider / transport module is allowlisted.
STAGE30_9_3_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_9_3_GATE_ADAPTER_MODULE,
    STAGE30_9_3_GATE_ORCHESTRATOR_MODULE,
    STAGE30_9_3_STAGE30_10_1_MODELS_MODULE,
    STAGE30_9_3_STAGE30_10_2_GATE_MODULE,
    STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE,
    STAGE30_9_3_STAGE30_10_3_PROJECTOR_MODULE,
    STAGE30_9_3_STAGE30_10_3_ARTIFACT_MODELS_MODULE,
)


# The Stage 30.9.3 live gate input / live gate decision / integration result
# field names (mirrored BY VALUE by the Stage 30.9.3 models module;
# ``created_at_utc`` is caller-injected, never a wall-clock read; NONE is a
# secret, a raw payload, a host, or a transport destination).
STAGE30_9_3_LIVE_GATE_INPUT_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "tier_token",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "post_migration_ath_verified",
    "candidate_ref",
    "created_at_utc",
)
STAGE30_9_3_LIVE_GATE_DECISION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "eligibility_decision",
    "eligibility_reason",
    "gate_decision",
    "gate_reason",
    "artifact_schema_version",
    "dispatch_reservation_allowed",
    "suppressed_before_dispatch_reservation",
    "dispatch_failure_recorded",
    "transport_veto_used",
    "payload_refused_used",
    "created_at_utc",
)
STAGE30_9_3_INTEGRATION_RESULT_FIELDS: Tuple[str, ...] = (
    "candidates_seen",
    "candidates_evaluated",
    "candidates_passed_gate",
    "candidates_skipped_before_dispatch",
    "invalid_inputs",
    "dispatch_attempts_reserved",
    "dispatch_failures_recorded",
    "transport_veto_count",
    "payload_refused_count",
    "would_send_private_discord_count",
    "created_at_utc",
)


# The author-verified expected Stage 30.9.3 fake integration proof counts.
# FULL classification (caps high enough to evaluate all nine candidates): three
# eligible dips PASS (three sink calls), five non-dips suppressed BEFORE
# reservation, one invalid suppressed -- zero dispatch failures / transport
# vetoes / PAYLOAD_REFUSED uses.
STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN: int = 9
STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_PASSED: int = 3
STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SKIPPED: int = 5
STAGE30_9_3_FAKE_PROOF_FULL_INVALID_INPUTS: int = 1
STAGE30_9_3_FAKE_PROOF_FULL_DISPATCH_ATTEMPTS_RESERVED: int = 3
STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD: int = 3
# CONTROLLED dip-present (max_dispatches=1): exactly one reserved dispatch / one
# sink call (the DISPATCHED_OK shape; the run stops after the first dip).
STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES: int = 1
# CONTROLLED no-dip (max_dispatches=1): zero reserved dispatches / zero sink
# calls; five non-dips + one invalid suppressed (the NO_DIP_FOUND_BUT_SAFE
# shape).
STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES: int = 0
STAGE30_9_3_FAKE_PROOF_NO_DIP_CANDIDATES_SKIPPED: int = 5
STAGE30_9_3_FAKE_PROOF_NO_DIP_INVALID_INPUTS: int = 1
# The three transport-safety negatives are ALWAYS zero across every scenario.
STAGE30_9_3_FAKE_PROOF_DISPATCH_FAILURES_RECORDED: int = 0
STAGE30_9_3_FAKE_PROOF_TRANSPORT_VETO_COUNT: int = 0
STAGE30_9_3_FAKE_PROOF_PAYLOAD_REFUSED_COUNT: int = 0


# Stage 30.9.3 holds the live ceremony behind an explicit operator-authorized
# step; the seam is offline-only in this slice.
STAGE30_9_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_9_3_INTEGRATION_NOTE: str = (
    "Stage 30.9.3 provides the committed, tested seam that wires the Stage "
    "30.10 dip gate into the live candidate -> dispatch path; the actual "
    "dip-filtered live ceremony remains a separate, explicitly operator-"
    "authorized step that this slice does not perform"
)


# After this integration seam slice, the next allowed step is the CONTROLLED
# dip-filtered private compact live ceremony -- now UNBLOCKED by the seam, but
# still a separate, explicitly operator-authorized step (NOT an automatic live
# execution, NOT a Stage 30.9.4, NOT a Stage 30.10.4).
STAGE30_9_3_NEXT_ALLOWED_STEP: str = (
    "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
)
STAGE30_9_3_NEXT_ALLOWED_STEP_TITLE: str = (
    "controlled dip-filtered private compact live ceremony -- now unblocked by "
    "the Stage 30.9.3 integration seam; a separate, explicitly operator-"
    "authorized step; never an automatic live execution and never a Stage "
    "30.9.4 / Stage 30.10.4"
)


# The surfaces the Stage 30.9.3 integration-seam slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host / transport
# needle forms. (The seam DOES reserve fake dispatch attempts + call an
# injected fake sink offline -- that is the slice; it must not reach any real
# transport / live surface below.)
STAGE30_9_3_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "live run",
    "live provider call",
    "real Discord send",
    "env read",
    "real provider key use",
    "real WebSocket / gRPC / HTTP provider session",
    "real transport dispatch reservation",
    "filesystem write",
    "transport-layer gate",
    "transport-layer veto for non-dip skip",
    "PAYLOAD_REFUSED for normal non-dip skip",
    "non-dip counted as dispatch failure",
    "dispatch sink call without PASS_TO_DISPATCH",
    "runtime orchestrator wiring",
    "Stage 28 suppression-logic edit",
    "Stage 30.3 compact orchestrator edit",
    "Stage 30.4 compact orchestrator edit",
    "existing live runner edit",
    "new provider",
    "new readiness gate",
    "database implementation",
    "SQLite implementation",
    "zstd implementation",
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
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "automatic live execution",
    "Stage 30.9.4+ implementation file",
    "Stage 30.10.4+ implementation file",
    "Stage 31",
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
    # Stage 30.9.2_RESUME dip-filtered live proof planning / fake-proof slice.
    "STAGE30_9_2_MINOR_VERSION",
    "STAGE30_9_2_RESUME_ID",
    "STAGE30_9_2_PRIOR_STAGE",
    "STAGE30_9_2_REQUIRED_HEAD_SHA",
    "STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION",
    "STAGE30_9_2_GATE_STACK_REQUIRED",
    "STAGE30_9_2_RESUME_MODELS_BASENAME",
    "STAGE30_9_2_RESUME_PLAN_BASENAME",
    "STAGE30_9_2_RESUME_FAKE_PROOF_BASENAME",
    "STAGE30_9_2_RESUME_MODELS_MODULE",
    "STAGE30_9_2_RESUME_PLAN_MODULE",
    "STAGE30_9_2_RESUME_FAKE_PROOF_MODULE",
    "STAGE30_9_2_STAGE30_10_3_FAKE_ARTIFACT_PROOF_MODULE",
    "STAGE30_9_2_STAGE30_10_3_GATE_ARTIFACT_MODELS_MODULE",
    "STAGE30_9_2_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_9_2_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_9_2_TEST_BASENAMES",
    "STAGE30_9_2_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_9_2_ALLOWED_PHX2_IMPORTS",
    "STAGE30_9_2_RESUME_PLAN_FIELDS",
    "STAGE30_9_2_CANDIDATE_PROOF_RECORD_FIELDS",
    "STAGE30_9_2_RESUME_PROOF_SUMMARY_FIELDS",
    "STAGE30_9_2_PLANNING_LIVE_ALLOWED",
    "STAGE30_9_2_PLANNING_DISPATCH_ALLOWED",
    "STAGE30_9_2_PLANNING_ENV_READ_ALLOWED",
    "STAGE30_9_2_PLANNING_PROVIDER_CALL_ALLOWED",
    "STAGE30_9_2_PLANNING_DISCORD_SEND_ALLOWED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_PASSED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_CANDIDATES_SKIPPED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_RESERVED",
    (
        "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTS_"
        "SUPPRESSED_BEFORE_RESERVATION"
    ),
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISPATCH_FAILURES_RECORDED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_TRANSPORT_VETO_COUNT",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_PAYLOAD_REFUSED_COUNT",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_LIVE_ALLOWED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_PROVIDER_CALL_ALLOWED",
    "STAGE30_9_2_FAKE_PROOF_EXPECTED_DISCORD_SEND_ALLOWED",
    "STAGE30_9_2_RESUME_STATUS",
    "STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_9_2_RESUME_NOTE",
    "STAGE30_9_2_NEXT_ALLOWED_STEP",
    "STAGE30_9_2_NEXT_ALLOWED_STEP_TITLE",
    "STAGE30_9_2_FORBIDDEN_SURFACES",
    # Stage 30.9.3 dip-filtered live dispatch integration seam.
    "STAGE30_9_3_MINOR_VERSION",
    "STAGE30_9_3_PRIOR_STAGE",
    "STAGE30_9_3_INTEGRATION_SCHEMA_VERSION",
    "STAGE30_9_3_GATE_STACK_REQUIRED",
    "STAGE30_9_3_GATE_DECISIONS",
    "STAGE30_9_3_DISPATCH_ALLOWED_GATE_DECISION",
    "STAGE30_9_3_GATE_MODELS_BASENAME",
    "STAGE30_9_3_GATE_ADAPTER_BASENAME",
    "STAGE30_9_3_GATE_ORCHESTRATOR_BASENAME",
    "STAGE30_9_3_FAKE_PROOF_BASENAME",
    "STAGE30_9_3_GATE_MODELS_MODULE",
    "STAGE30_9_3_GATE_ADAPTER_MODULE",
    "STAGE30_9_3_GATE_ORCHESTRATOR_MODULE",
    "STAGE30_9_3_FAKE_PROOF_MODULE",
    "STAGE30_9_3_STAGE30_10_1_MODELS_MODULE",
    "STAGE30_9_3_STAGE30_10_2_GATE_MODULE",
    "STAGE30_9_3_STAGE30_10_2_GATE_MODELS_MODULE",
    "STAGE30_9_3_STAGE30_10_3_PROJECTOR_MODULE",
    "STAGE30_9_3_STAGE30_10_3_ARTIFACT_MODELS_MODULE",
    "STAGE30_9_3_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_9_3_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_9_3_TEST_BASENAMES",
    "STAGE30_9_3_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_9_3_ALLOWED_PHX2_IMPORTS",
    "STAGE30_9_3_LIVE_GATE_INPUT_FIELDS",
    "STAGE30_9_3_LIVE_GATE_DECISION_FIELDS",
    "STAGE30_9_3_INTEGRATION_RESULT_FIELDS",
    "STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SEEN",
    "STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_PASSED",
    "STAGE30_9_3_FAKE_PROOF_FULL_CANDIDATES_SKIPPED",
    "STAGE30_9_3_FAKE_PROOF_FULL_INVALID_INPUTS",
    "STAGE30_9_3_FAKE_PROOF_FULL_DISPATCH_ATTEMPTS_RESERVED",
    "STAGE30_9_3_FAKE_PROOF_FULL_WOULD_SEND_PRIVATE_DISCORD",
    "STAGE30_9_3_FAKE_PROOF_DIP_PRESENT_DISPATCHES",
    "STAGE30_9_3_FAKE_PROOF_NO_DIP_DISPATCHES",
    "STAGE30_9_3_FAKE_PROOF_NO_DIP_CANDIDATES_SKIPPED",
    "STAGE30_9_3_FAKE_PROOF_NO_DIP_INVALID_INPUTS",
    "STAGE30_9_3_FAKE_PROOF_DISPATCH_FAILURES_RECORDED",
    "STAGE30_9_3_FAKE_PROOF_TRANSPORT_VETO_COUNT",
    "STAGE30_9_3_FAKE_PROOF_PAYLOAD_REFUSED_COUNT",
    "STAGE30_9_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_9_3_INTEGRATION_NOTE",
    "STAGE30_9_3_NEXT_ALLOWED_STEP",
    "STAGE30_9_3_NEXT_ALLOWED_STEP_TITLE",
    "STAGE30_9_3_FORBIDDEN_SURFACES",
)
