"""Stage 30.8.0 compact session artifact / storage readiness spec-lock
manifest.

Constants-only spec-lock manifest. Pins the Stage 30.8.0 inventory (the
spec-lock doc basename, this manifest basename, the test basename), the
Stage 30.8 stage id + next recommended substage, the closed-set compact
artifact kinds, the required artifact identity fields, the safe compact
content fields, the forbidden artifact fields (safe paraphrase labels),
the forbidden surfaces the spec-lock slice must not touch, the Stage 30.6
storage-budget handoff references (soft / hard disk caps), the Stage 30.7
proof handoff references (the closure-audit / handoff doc basenames and
the final compact proof line), the redaction substitution tokens, the
future Stage 30.8.1+ substage sequence, and the forbidden runtime imports
/ text needles the spec-lock files are scanned against.

Stage 30.8 is the compact session artifact / storage-readiness family of
Stage 30. Before PHX2 can be safely left running for long private soaks /
eventual 24/7 collection, the compact private-ping / session artifact
collection design has to be locked so durable capture does NOT bloat the
repo, lose dedupe / session identity, write secrets, write raw provider
payloads, enable enforcement / trading / public routing, or couple
storage to live provider code. Stage 30.8.0 LOCKS that design as prose +
constants; it ships NO storage writer, NO database, NO SQLite, NO
filesystem artifact writer, NO zstd dependency, NO day-rolling, NO live
run, NO provider call, NO Discord send, and edits NO runtime orchestrator
/ renderer / compact model / Stage 30.7 file.

Stage 30.8.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this manifest.
  * ZERO storage writer, ZERO database / SQLite / filesystem artifact
    writer, ZERO zstd dependency / implementation, ZERO day-rolling
    implementation.
  * ZERO runtime orchestrator / compact renderer / compact model edit,
    ZERO Stage 30.7 file edit.
  * ZERO live provider call. ZERO Discord send. ZERO env read. ZERO
    enforcement. ZERO public routing. ZERO trading / wallet / social.
    ZERO drawdown / tier recomputation.

Stage 30.8.1+ scope (deferred, each separately operator-authorized):

  * 30.8.1 -- pure compact artifact models + validators, NO writer.
  * 30.8.2 -- temp-dir artifact writer with fake / offline tests only.
  * 30.8.3 -- dedupe / session index integration, offline.
  * 30.8.4 -- controlled compact session artifact proof.

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
# Stage id + minor version
# ---------------------------------------------------------------------------


STAGE30_8_STAGE_ID: str = "30.8"
STAGE30_8_0_MINOR_VERSION: str = "30.8.0"


# ---------------------------------------------------------------------------
# Locked basenames + inventory delta
# ---------------------------------------------------------------------------


STAGE30_8_0_SPEC_LOCK_BASENAME: str = (
    "STAGE_30_8_0_COMPACT_SESSION_STORAGE_SPEC_LOCK.md"
)
STAGE30_8_MANIFEST_BASENAME: str = "stage30_8_manifest.py"


STAGE30_8_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_8_0_storage_spec_lock.py",
)


# The NEW files Stage 30.8.0 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.7.4 inventory: exactly the spec-lock
# markdown plus this constants-only manifest. NO production .py beyond the
# manifest at Stage 30.8.0; NO Stage 30.8.1+ models / writer / index file.
STAGE30_8_ALLOWED_INITIAL_FILES: Tuple[str, ...] = (
    STAGE30_8_0_SPEC_LOCK_BASENAME,
    STAGE30_8_MANIFEST_BASENAME,
)


# The only NEW production .py Stage 30.8.0 adds is this constants-only
# manifest; the spec lock is markdown. The boundary scan checks this
# basename for forbidden imports / needles.
STAGE30_8_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_8_MANIFEST_BASENAME,
)


# Every non-PHX2 import in this manifest must be in this stdlib allowlist
# (the manifest is constants-only: it needs only ``__future__`` +
# ``typing``). The spec-lock slice has NO PHX2 production import at all.
STAGE30_8_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# ---------------------------------------------------------------------------
# Compact artifact kinds (closed set)
# ---------------------------------------------------------------------------
#
# The closed set of compact artifact kinds Stage 30.8 will eventually
# persist. Stage 30.8.0 LOCKS the vocabulary only; it writes none of them.


STAGE30_8_ARTIFACT_KIND_COMPACT_SESSION_SUMMARY: str = (
    "compact_session_summary"
)
STAGE30_8_ARTIFACT_KIND_COMPACT_PING_ARTIFACT: str = (
    "compact_ping_artifact"
)
STAGE30_8_ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT: str = (
    "compact_dispatch_attempt_artifact"
)
STAGE30_8_ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT: str = (
    "compact_error_artifact"
)
STAGE30_8_ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT: str = (
    "compact_storage_budget_snapshot"
)


STAGE30_8_ARTIFACT_KINDS: Tuple[str, ...] = (
    STAGE30_8_ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    STAGE30_8_ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    STAGE30_8_ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    STAGE30_8_ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    STAGE30_8_ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
)


# ---------------------------------------------------------------------------
# Required artifact identity fields (closed set)
# ---------------------------------------------------------------------------
#
# Stable identity axes every persisted compact artifact carries. Each is a
# safe-shape opaque id / closed-set token / ISO-8601 UTC timestamp /
# version string. NONE is a secret, a raw payload, a host, or a transport
# destination. ``token_mint`` / ``candidate_id`` / ``normalized_event_id``
# are written only when already present on the sanitized snapshot.


STAGE30_8_IDENTITY_FIELDS: Tuple[str, ...] = (
    "stage_id",
    "run_id",
    "session_id",
    "ping_id",
    "candidate_id",
    "token_mint",
    "normalized_event_id",
    "observed_at_utc",
    "artifact_created_at_utc",
    "artifact_schema_version",
    "artifact_kind",
    "dedupe_key",
    "compact_ping_schema_version",
)


# ---------------------------------------------------------------------------
# Safe compact content fields (closed set)
# ---------------------------------------------------------------------------
#
# The already-rendered, redaction-safe compact display strings + closed-set
# status codes Stage 30.8 may persist. These mirror the Stage 30.2
# ``CompactPingSnapshotRecord`` display fields (MC / ATH / Mig / LP / Net)
# plus the eligibility / warning / outcome / transport status tokens. They
# are persisted ONLY after the Stage 30.2 / private send-safe redaction
# guard, never as raw provider data.


STAGE30_8_SAFE_COMPACT_CONTENT_FIELDS: Tuple[str, ...] = (
    "compact_body_text",
    "mc_display",
    "lp_display",
    "net_display",
    "ath_display",
    "migration_display",
    "eligibility_status",
    "warning_reason_codes",
    "terminal_outcome_code",
    "transport_status",
)


# ---------------------------------------------------------------------------
# Forbidden artifact fields (safe paraphrase labels)
# ---------------------------------------------------------------------------
#
# The field classes a Stage 30.8 artifact must NEVER carry. These are plain
# paraphrase labels (deliberately NOT the bare secret / transport / URL
# needle forms) so this manifest source itself carries none of the
# sanitized-away substrings. A future writer (Stage 30.8.2+) must fail
# closed when it sees any of these.


STAGE30_8_FORBIDDEN_ARTIFACT_FIELDS: Tuple[str, ...] = (
    "private webhook destination",
    "provider API-key",
    "request auth-metadata",
    "signed-token credential",
    "environment variable value",
    "raw provider payload",
    "raw transaction or log payload",
    "full Discord response body",
    "wallet private key",
    "signing material",
    "user secret",
    "unredacted URL",
    "arbitrary nested raw dict or list payload",
    "binary blob",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.8.0 spec-lock slice must not touch. These are
# plain documentation words (family / feature names), NOT secret / host /
# transport needle forms.


STAGE30_8_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "writer implementation",
    "database implementation",
    "SQLite implementation",
    "filesystem artifact writer implementation",
    "zstd implementation",
    "zstd dependency",
    "day rolling implementation",
    "live run",
    "provider call",
    "Discord send",
    "env read",
    "compact renderer edit",
    "compact models edit",
    "runtime orchestrator edit",
    "Stage 30.7 file edit",
    "enforcement",
    "public routing",
    "trading",
    "wallet",
    "social",
    "drawdown recomputation",
    "tier recomputation",
    "Stage 25/27/28/29 production import",
    "Stage 29.5 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.8.1+ implementation file",
)


# ---------------------------------------------------------------------------
# Stage 30.6 storage-budget handoff references (reused, not redefined)
# ---------------------------------------------------------------------------
#
# Stage 30.8 storage budgeting is GOVERNED BY the Stage 30.6 storage-budget
# policy (the soft / hard disk caps + the storage budget models /
# evaluator). Stage 30.8.0 references those constants by value; it does NOT
# import the Stage 30.6 manifest (the manifest stays PHX2-import-free) and
# it re-implements no budget logic.


STAGE30_8_STAGE30_6_BUDGET_HANDOFF_SUBSTAGE: str = "30.6"
STAGE30_8_DISK_SOFT_ALARM_PERCENT: int = 65
STAGE30_8_DISK_HARD_STOP_PERCENT: int = 90


# ---------------------------------------------------------------------------
# Stage 30.7 proof handoff references (reused, not redefined)
# ---------------------------------------------------------------------------
#
# Stage 30.8 builds directly on the closed Stage 30.7 ATH context family.
# The references below pin the Stage 30.7 closure-audit / handoff doc
# basenames and the final offline compact proof line that motivates durable
# capture. Stage 30.8.0 edits NO Stage 30.7 file.


STAGE30_8_STAGE30_7_CLOSURE_AUDIT_BASENAME: str = (
    "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md"
)
STAGE30_8_STAGE30_7_HANDOFF_BASENAME: str = (
    "STAGE_30_7_ATH_CONTEXT_HANDOFF.md"
)
STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE: str = (
    "• MC: $83k | ATH: $120k | Mig: Known"
)


# ---------------------------------------------------------------------------
# Redaction substitution tokens (closed set)
# ---------------------------------------------------------------------------
#
# Every persisted string must pass a redaction scan or be substituted with
# one of these closed-set safe tokens. A future writer fails closed (drops
# the artifact, never the field) on any unsafe field.


STAGE30_8_REDACTION_SUBSTITUTION_TOKENS: Tuple[str, ...] = (
    "SAFE",
    "REDACTED",
    "Unknown",
)


# ---------------------------------------------------------------------------
# Future substage sequence + next recommended stage
# ---------------------------------------------------------------------------


STAGE30_8_FUTURE_SUBSTAGE_SEQUENCE: Tuple[str, ...] = (
    "30.8.0",
    "30.8.1",
    "30.8.2",
    "30.8.3",
    "30.8.4",
)


STAGE30_8_NEXT_RECOMMENDED_STAGE: str = "30.8.1"
STAGE30_8_NEXT_RECOMMENDED_STAGE_TITLE: str = (
    "pure compact artifact models + validators (no writer)"
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.8.0 pin test walks the actual import lines of the Stage
# 30.8.0 Python files (this manifest + the pin test) and asserts none
# resolve to a module covered by this policy. The strings below are plain
# (the line-based scan never substring-matches them against source text).


STAGE30_8_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces the Stage 30.8.0 spec-lock files must not touch.
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
    # No zstd implementation / dependency at Stage 30.8.0 (docs + tests may
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
# 30.8.0 pin test imports this tuple at runtime and scans every Stage
# 30.8.0 file (spec lock, manifest, test) case-insensitively for substring
# matches against the runtime-concatenated values. The spec doc paraphrases
# every secret / transport surface (for example "provider credential",
# "private transport destination", "transport scheme prefix") so it carries
# none of the bare needles.


STAGE30_8_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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


__all__ = (
    # Stage id + minor version.
    "STAGE30_8_STAGE_ID",
    "STAGE30_8_0_MINOR_VERSION",
    # Locked basenames + inventory delta.
    "STAGE30_8_0_SPEC_LOCK_BASENAME",
    "STAGE30_8_MANIFEST_BASENAME",
    "STAGE30_8_0_TEST_BASENAMES",
    "STAGE30_8_ALLOWED_INITIAL_FILES",
    "STAGE30_8_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_8_ALLOWED_STDLIB_IMPORTS",
    # Compact artifact kinds.
    "STAGE30_8_ARTIFACT_KIND_COMPACT_SESSION_SUMMARY",
    "STAGE30_8_ARTIFACT_KIND_COMPACT_PING_ARTIFACT",
    "STAGE30_8_ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT",
    "STAGE30_8_ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT",
    "STAGE30_8_ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT",
    "STAGE30_8_ARTIFACT_KINDS",
    # Identity + content + forbidden fields.
    "STAGE30_8_IDENTITY_FIELDS",
    "STAGE30_8_SAFE_COMPACT_CONTENT_FIELDS",
    "STAGE30_8_FORBIDDEN_ARTIFACT_FIELDS",
    # Forbidden surfaces.
    "STAGE30_8_FORBIDDEN_SURFACES",
    # Stage 30.6 budget handoff.
    "STAGE30_8_STAGE30_6_BUDGET_HANDOFF_SUBSTAGE",
    "STAGE30_8_DISK_SOFT_ALARM_PERCENT",
    "STAGE30_8_DISK_HARD_STOP_PERCENT",
    # Stage 30.7 proof handoff.
    "STAGE30_8_STAGE30_7_CLOSURE_AUDIT_BASENAME",
    "STAGE30_8_STAGE30_7_HANDOFF_BASENAME",
    "STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE",
    # Redaction substitution tokens.
    "STAGE30_8_REDACTION_SUBSTITUTION_TOKENS",
    # Future substages + next stage.
    "STAGE30_8_FUTURE_SUBSTAGE_SEQUENCE",
    "STAGE30_8_NEXT_RECOMMENDED_STAGE",
    "STAGE30_8_NEXT_RECOMMENDED_STAGE_TITLE",
    # Forbidden imports + needles.
    "STAGE30_8_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_8_FORBIDDEN_TEXT_NEEDLES",
)
