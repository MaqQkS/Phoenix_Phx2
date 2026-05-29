"""Stage 30.6.0 storage + dedupe spec-lock manifest.

Constants-only spec-lock manifest. Pins the Stage 30.6.0 inventory
(spec basename, manifest basename, test basenames), the Stage 30.6
substage sequence, the closed-set storage lifecycle tier names, the
closed-set dedupe re-alert state-change triggers, the dedupe-key
component names, the disk-budget thresholds, the per-run storage
summary field names, the ATH handoff substage, the forbidden runtime
imports, and the forbidden text needles.

Stage 30.6 is the 24/7-readiness storage + dedupe family of Stage 30.
Before PHX2 is left running for long private soaks, the storage and
dedupe architecture has to prevent repeated same-token pings, same-
tier spam, unbounded raw-event / database / file bloat, the legacy
PHX1-style giant DB / log accumulation, and out-of-disk crashes.
Stage 30.6.0 LOCKS that architecture as prose + constants; it ships
NO storage writer, NO dedupe engine, NO database migration, NO
filesystem writer, NO zstd dependency, NO live run, NO Discord send,
and NO ATH.

Stage 30.6.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this manifest.
  * ZERO storage writer, ZERO dedupe engine, ZERO budget evaluator,
    ZERO lifecycle-seal aggregate, ZERO database migration, ZERO
    filesystem writer, ZERO zstd implementation / dependency.
  * ZERO modification to Stage 21-29 or Stage 30.1 / 30.2 / 30.3 /
    30.4 / 30.5 runtime source.
  * ZERO live provider call. ZERO Discord send. ZERO env read. ZERO
    candidate scan. ZERO ATH. ZERO Net. ZERO filters. ZERO
    enforcement.

Stage 30.6.1+ scope (deferred, each separately operator-authorized):

  * 30.6.1 -- storage budget models + pure policy evaluator.
  * 30.6.2 -- rotating WAL / day-rolled artifact writer scaffold.
  * 30.6.3 -- dedupe / session ledger scaffold.
  * 30.6.4 -- lifecycle seal aggregate contract.
  * 30.6.5 -- storage / dedupe offline integration proof.
  * 30.7   -- ATH context bridge, only after the storage / dedupe
              spec is locked.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple


# ---------------------------------------------------------------------------
# Minor versions + locked basenames
# ---------------------------------------------------------------------------


STAGE30_6_MINOR_VERSION: str = "30.6"
STAGE30_6_0_MINOR_VERSION: str = "30.6.0"


STAGE30_6_SPEC_BASENAME: str = (
    "STAGE_30_6_0_STORAGE_DEDUPE_SPEC_LOCK.md"
)
STAGE30_6_MANIFEST_BASENAME: str = "stage30_6_manifest.py"


# ---------------------------------------------------------------------------
# Stage 30.6.0 test inventory (pin test only)
# ---------------------------------------------------------------------------


STAGE30_6_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_6_0_storage_dedupe_spec_lock.py",
)


# ---------------------------------------------------------------------------
# Stage 30.6.0 production-inventory delta
# ---------------------------------------------------------------------------
#
# The new files Stage 30.6.0 adds under ``PHX2/stage30/`` on top of
# the already-allowed Stage 30.0..30.5 inventory. Exactly the spec
# lock markdown plus this manifest module; NO production .py beyond
# the manifest at Stage 30.6.0. No Stage 30.6.1+ storage writer /
# dedupe ledger / budget evaluator / seal aggregate file.


STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0: Tuple[str, ...] = (
    STAGE30_6_SPEC_BASENAME,
    STAGE30_6_MANIFEST_BASENAME,
)


# ---------------------------------------------------------------------------
# Stage 30.6 substage sequence (pinned) + ATH handoff
# ---------------------------------------------------------------------------


STAGE30_6_SUBSTAGE_SEQUENCE: Tuple[str, ...] = (
    "30.6.0",
    "30.6.1",
    "30.6.2",
    "30.6.3",
    "30.6.4",
    "30.6.5",
)


# ATH context is the explicit follow-on AFTER the storage / dedupe
# spec is locked. It is NOT a Stage 30.6 substage; it is Stage 30.7.
STAGE30_6_ATH_HANDOFF_SUBSTAGE: str = "30.7"


# ---------------------------------------------------------------------------
# Storage lifecycle tiers (closed set of four)
# ---------------------------------------------------------------------------
#
# Stage 30.6 pins a four-tier lifecycle storage model, NOT a simple
# time-only retention model:
#
#   * Tier 0 / WAL buffer            -- short-lived rotating raw
#                                       buffer, safe to delete.
#   * Tier 1 / Hot raw               -- short-lived raw per-event /
#                                       per-sample evidence, ~24-48h.
#   * Tier 2 / Durable token summary -- one evolving compact aggregate
#                                       per mint / session.
#   * Tier 3 / Sealed archive        -- immutable compact summary +
#                                       optional zstd evidence bundle.


STAGE30_6_STORAGE_TIER_0_WAL_BUFFER: str = "TIER_0_WAL_BUFFER"
STAGE30_6_STORAGE_TIER_1_HOT_RAW: str = "TIER_1_HOT_RAW"
STAGE30_6_STORAGE_TIER_2_DURABLE_TOKEN_SUMMARY: str = (
    "TIER_2_DURABLE_TOKEN_SUMMARY"
)
STAGE30_6_STORAGE_TIER_3_SEALED_ARCHIVE: str = (
    "TIER_3_SEALED_ARCHIVE"
)


STAGE30_6_STORAGE_TIER_NAMES: Tuple[str, ...] = (
    STAGE30_6_STORAGE_TIER_0_WAL_BUFFER,
    STAGE30_6_STORAGE_TIER_1_HOT_RAW,
    STAGE30_6_STORAGE_TIER_2_DURABLE_TOKEN_SUMMARY,
    STAGE30_6_STORAGE_TIER_3_SEALED_ARCHIVE,
)


# Human-readable tier labels (as they appear in the spec lock
# section headings). Documentation tuple; the pin test asserts each
# label appears verbatim in the spec doc.
STAGE30_6_STORAGE_TIER_LABELS: Tuple[str, ...] = (
    "Tier 0 / WAL buffer",
    "Tier 1 / Hot raw",
    "Tier 2 / Durable token summary",
    "Tier 3 / Sealed archive",
)


# ---------------------------------------------------------------------------
# Dedupe re-alert state-change triggers (closed set)
# ---------------------------------------------------------------------------
#
# After the first ping for a mint, Stage 30.6 only re-pings on a
# meaningful state change drawn from this closed set. Same mint +
# same tier + same state is suppressed.


STAGE30_6_REALERT_TRIGGER_NEW_TIER: str = "NEW_TIER"
STAGE30_6_REALERT_TRIGGER_MIG_UNKNOWN_TO_KNOWN: str = (
    "MIG_UNKNOWN_TO_KNOWN_OR_UNVERIFIED"
)
STAGE30_6_REALERT_TRIGGER_ATH_UNKNOWN_TO_KNOWN: str = (
    "ATH_UNKNOWN_TO_KNOWN"
)
STAGE30_6_REALERT_TRIGGER_MATERIAL_DRAWDOWN: str = (
    "MATERIAL_DRAWDOWN_OR_TIER_TRANSITION"
)
STAGE30_6_REALERT_TRIGGER_OPERATOR_APPROVED: str = (
    "OPERATOR_APPROVED_REALERT"
)


STAGE30_6_REALERT_TRIGGER_NAMES: Tuple[str, ...] = (
    STAGE30_6_REALERT_TRIGGER_NEW_TIER,
    STAGE30_6_REALERT_TRIGGER_MIG_UNKNOWN_TO_KNOWN,
    STAGE30_6_REALERT_TRIGGER_ATH_UNKNOWN_TO_KNOWN,
    STAGE30_6_REALERT_TRIGGER_MATERIAL_DRAWDOWN,
    STAGE30_6_REALERT_TRIGGER_OPERATOR_APPROVED,
)


# Dedupe-key component names (the dedupe key must include mint + an
# alert / tier / state class + a policy-version / session-scope axis
# as appropriate). Documentation tuple; the spec doc carries the same
# component list.
STAGE30_6_DEDUPE_KEY_COMPONENTS: Tuple[str, ...] = (
    "mint",
    "alert_or_tier_state_class",
    "policy_version",
    "session_scope",
)


# ---------------------------------------------------------------------------
# Disk budget thresholds (percent of disk used)
# ---------------------------------------------------------------------------
#
# Soft alarm fires a private operator warning; hard stop refuses new
# writes (fail closed) so a full disk never produces a weird crash.
# Prune is NOT the first line of defense.


STAGE30_6_DISK_SOFT_ALARM_PERCENT: int = 65
STAGE30_6_DISK_HARD_STOP_PERCENT: int = 90


# ---------------------------------------------------------------------------
# Per-run storage summary field names (closed set)
# ---------------------------------------------------------------------------
#
# Every long soak emits a per-run storage summary carrying these
# observability axes. Counters / byte counts / percentages only; no
# raw payload, no provider credential, no private transport
# destination.


STAGE30_6_STORAGE_SUMMARY_FIELD_NAMES: Tuple[str, ...] = (
    "raw_bytes_written",
    "durable_rows_written",
    "archived_compressed_bytes",
    "dropped_count",
    "pruned_count",
    "sealed_count",
    "dedupe_suppressed_count",
    "disk_usage_percent_before",
    "disk_usage_percent_after",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.6.0 pin test walks the actual import lines of the
# Stage 30.6.0 Python files (this manifest + the pin test) and
# asserts none resolve to a module covered by this policy. The
# strings below are plain (the line-based scan never substring-
# matches them against source text).


STAGE30_6_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces Stage 30.6.0 spec-lock files must not touch.
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
    # No zstd implementation / dependency at Stage 30.6.0 (docs +
    # tests may name the WORD ``zstd``; no module import is allowed).
    "import zstandard",
    "from zstandard",
    "import zstd",
    "from zstd",
    # Stage 21-29 production surfaces.
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
# Every needle below is built with a split-literal concatenation so
# this manifest source text itself does NOT carry the bare needle.
# The Stage 30.6.0 pin test imports this tuple at runtime and scans
# every Stage 30.6.0 file (spec lock, manifest, test) case-
# insensitively for substring matches against the runtime-
# concatenated values. The spec doc paraphrases every secret /
# transport surface (for example "provider credential", "private
# transport destination", "transport scheme prefix") so it carries
# none of the bare needles.


STAGE30_6_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# Stage 30.6.1 storage budget models + pure policy evaluator inventory
# ---------------------------------------------------------------------------
#
# Stage 30.6.1 is the FIRST Stage 30.6 production slice: a pure offline
# storage-budget policy brain (closed-set models + a deterministic
# evaluator). It is NOT a storage writer, NOT a dedupe ledger, NOT a
# WAL / day-rolled writer, NOT a lifecycle-seal aggregate, and NOT a
# live runtime. It reads NO actual disk: the caller supplies the
# observed disk-used percentage. The two NEW production files are the
# models module + the evaluator module. NO database migration, NO
# filesystem writer, NO zstd dependency, NO live / Discord / provider,
# NO ATH, NO Net, NO filters, NO enforcement, NO dedupe / WAL writer.


STAGE30_6_1_MINOR_VERSION: str = "30.6.1"


STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION: str = (
    "stage30_6_1_v0_storage_budget"
)
STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION: str = (
    "stage30_6_storage_budget_policy_v0"
)


STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME: str = (
    "stage30_6_storage_budget_models.py"
)
STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME: str = (
    "stage30_6_storage_budget_evaluator.py"
)


STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_6_storage_budget_models"
)
STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_MODULE: str = (
    "PHX2.stage30.stage30_6_storage_budget_evaluator"
)


# The NEW production files Stage 30.6.1 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.5 + 30.6.0 inventory:
# exactly the storage budget models + evaluator. NO Stage 30.6.2+ file.
STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1: Tuple[str, ...] = (
    STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME,
    STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME,
)


# The two production modules the Stage 30.6.1 boundary test scans for
# forbidden imports / text needles.
STAGE30_6_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME,
    STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME,
)


STAGE30_6_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_6_1_storage_budget_models.py",
    "test_stage_30_6_1_storage_budget_evaluator.py",
    "test_stage_30_6_1_boundaries.py",
    "test_stage_30_6_1_manifest.py",
)


# Every non-PHX2 import in a Stage 30.6.1 production module must be in
# this stdlib allowlist; every PHX2 import must be the Stage 30.6.1
# models sibling. This positive allowlist proves, by construction, that
# NO os / pathlib / shutil / sqlite3 / zstd / network / Discord /
# provider / Stage 21-29 module is imported (so NO actual disk is
# read).
STAGE30_6_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "math",
)


STAGE30_6_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE,
)


# Closed-set storage-budget status / action tokens (mirrored from the
# Stage 30.6.1 models module; the manifest test cross-checks they match
# ``stage30_6_storage_budget_models``). Documentation + drift guard.
STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES: Tuple[str, ...] = (
    "STORAGE_BUDGET_OK",
    "STORAGE_BUDGET_SOFT_ALARM",
    "STORAGE_BUDGET_HARD_STOP",
    "STORAGE_BUDGET_INVALID_INPUT",
)


STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES: Tuple[str, ...] = (
    "ALLOW_WRITES",
    "ALLOW_WRITES_WITH_WARNING",
    "REFUSE_NEW_WRITES",
    "INVALID_INPUT_REFUSE_WRITES",
)


# Float forms of the Stage 30.6.0 soft 65 / hard 90 disk guardrails
# (the integer forms are pinned above as
# STAGE30_6_DISK_SOFT_ALARM_PERCENT / STAGE30_6_DISK_HARD_STOP_PERCENT).
# The Stage 30.6.1 models module carries the canonical defaults; the
# manifest test cross-checks these match.
STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT: float = 65.0
STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT: float = 90.0


__all__ = (
    # Version axes + basenames.
    "STAGE30_6_MINOR_VERSION",
    "STAGE30_6_0_MINOR_VERSION",
    "STAGE30_6_SPEC_BASENAME",
    "STAGE30_6_MANIFEST_BASENAME",
    "STAGE30_6_0_TEST_BASENAMES",
    "STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0",
    # Substage sequence + ATH handoff.
    "STAGE30_6_SUBSTAGE_SEQUENCE",
    "STAGE30_6_ATH_HANDOFF_SUBSTAGE",
    # Storage lifecycle tiers.
    "STAGE30_6_STORAGE_TIER_0_WAL_BUFFER",
    "STAGE30_6_STORAGE_TIER_1_HOT_RAW",
    "STAGE30_6_STORAGE_TIER_2_DURABLE_TOKEN_SUMMARY",
    "STAGE30_6_STORAGE_TIER_3_SEALED_ARCHIVE",
    "STAGE30_6_STORAGE_TIER_NAMES",
    "STAGE30_6_STORAGE_TIER_LABELS",
    # Dedupe re-alert triggers + key components.
    "STAGE30_6_REALERT_TRIGGER_NEW_TIER",
    "STAGE30_6_REALERT_TRIGGER_MIG_UNKNOWN_TO_KNOWN",
    "STAGE30_6_REALERT_TRIGGER_ATH_UNKNOWN_TO_KNOWN",
    "STAGE30_6_REALERT_TRIGGER_MATERIAL_DRAWDOWN",
    "STAGE30_6_REALERT_TRIGGER_OPERATOR_APPROVED",
    "STAGE30_6_REALERT_TRIGGER_NAMES",
    "STAGE30_6_DEDUPE_KEY_COMPONENTS",
    # Disk budget thresholds.
    "STAGE30_6_DISK_SOFT_ALARM_PERCENT",
    "STAGE30_6_DISK_HARD_STOP_PERCENT",
    # Observability.
    "STAGE30_6_STORAGE_SUMMARY_FIELD_NAMES",
    # Forbidden surfaces.
    "STAGE30_6_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_6_FORBIDDEN_TEXT_NEEDLES",
    # Stage 30.6.1 storage budget models + evaluator inventory.
    "STAGE30_6_1_MINOR_VERSION",
    "STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION",
    "STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION",
    "STAGE30_6_1_STORAGE_BUDGET_MODELS_BASENAME",
    "STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_BASENAME",
    "STAGE30_6_1_STORAGE_BUDGET_MODELS_MODULE",
    "STAGE30_6_1_STORAGE_BUDGET_EVALUATOR_MODULE",
    "STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_1",
    "STAGE30_6_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_6_1_TEST_BASENAMES",
    "STAGE30_6_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_6_1_ALLOWED_PHX2_IMPORTS",
    "STAGE30_6_1_STORAGE_BUDGET_STATUS_VALUES",
    "STAGE30_6_1_STORAGE_BUDGET_ACTION_VALUES",
    "STAGE30_6_1_DEFAULT_SOFT_ALARM_USED_PCT",
    "STAGE30_6_1_DEFAULT_HARD_STOP_USED_PCT",
)
