"""Stage 30.5.1 migration-context manifest.

Constants-only manifest. Pins the Stage 30.5.1 inventory (production
basenames, manifest basename, test basenames), the Stage 30.5.1
schema version, the Stage 30.5.1 import allowlists (stdlib + PHX2),
the forbidden runtime imports, the forbidden text needles, and the
Stage 29.5.5 private side-channel modules the Stage 30.5 production
code must NEVER import.

Stage 30.5 is the migration-context enrichment family of Stage 30,
pre-named in the parent Stage 30.0 spec lock substage map and
contracted by the committed Stage 30.5.0 spec lock. Stage 30.5 owns
ONLY the compact body ``Mig`` token: it moves the token from the
literal ``Unknown`` toward an honest, evidence-backed migration
status word drawn from a closed set.

Stage 30.5.1 scope (this slice):

  * Stage-30-owned migration context models + source protocol +
    adapter, with fakes only. Mirrors Stage 30.4.1.
  * ZERO live provider call. ZERO Discord send. ZERO candidate scan.
  * ZERO ATH. ZERO Net.
  * ZERO Stage 27 / 28 / 29 production-source modification.
  * ZERO Stage 29.5 production-source modification.
  * ZERO Stage 30.1 / 30.2 / 30.3 runtime change. The compact
    renderer and the compact runtime orchestrator are untouched (the
    first slice fills the ``Mig`` slot through the existing display
    slot only at a later substage).
  * ZERO Stage 29.5.5 private side-channel renderer / recorder /
    artifact writer import.

Closed sets committed by the Stage 30.5.0 spec lock and implemented
in Stage 30.5.1:

  * migration_status -- ``KNOWN`` / ``UNVERIFIED`` / ``UNKNOWN``
  * migration_basis  -- ``ON_CHAIN_EVENT`` / ``EVIDENCE_PARTIAL`` /
                        ``NONE``
  * source_status    -- ``UNAVAILABLE`` / ``PRESENT`` / ``ERROR`` /
                        ``STALE``

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
# Minor versions + schema version
# ---------------------------------------------------------------------------


STAGE30_5_MINOR_VERSION: str = "30.5"
STAGE30_5_1_MINOR_VERSION: str = "30.5.1"


STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_5_1_v0_migration_context"
)


# ---------------------------------------------------------------------------
# Locked basenames
# ---------------------------------------------------------------------------


STAGE30_5_MANIFEST_BASENAME: str = "stage30_5_manifest.py"


STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME: str = (
    "stage30_5_migration_context_models.py"
)
STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME: str = (
    "stage30_5_migration_context_source_protocol.py"
)
STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME: str = (
    "stage30_5_migration_context_adapter.py"
)


# ---------------------------------------------------------------------------
# Stage 30.5.1 production-inventory delta
# ---------------------------------------------------------------------------
#
# The new files Stage 30.5.1 adds under ``PHX2/stage30/`` on top of
# the already-allowed Stage 30.0..30.4 + 30.5.0 inventory. Exactly the
# offline models + source protocol + adapter plus this manifest (the
# Stage 30.5.0 commit shipped the spec-lock doc only, no manifest, so
# the manifest lands here at Stage 30.5.1). NO renderer change, NO
# runtime orchestrator change, NO artifact writer, NO bridge.


STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1: Tuple[str, ...] = (
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME,
    STAGE30_5_MANIFEST_BASENAME,
)


# The three production modules the Stage 30.5.1 boundary test scans
# for forbidden imports / text needles (the manifest itself is
# constants-only and is pinned by the manifest test instead).


STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME,
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME,
)


# ---------------------------------------------------------------------------
# Stage 30.5.1 test inventory
# ---------------------------------------------------------------------------


STAGE30_5_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_5_1_migration_context_models.py",
    "test_stage_30_5_1_migration_context_source_protocol.py",
    "test_stage_30_5_1_migration_context_adapter.py",
    "test_stage_30_5_1_boundaries.py",
    "test_stage_30_5_1_manifest.py",
)


# ---------------------------------------------------------------------------
# Stage 30.5.1 import allowlists
# ---------------------------------------------------------------------------
#
# Every non-PHX2 import in a Stage 30.5.1 production module must be in
# the stdlib allowlist; every PHX2 import must be one of the three
# Stage 30.5.1 sibling modules. This positive allowlist is what proves
# (by construction) that NO Stage 29 / Stage 28 / Stage 30.1-30.4 /
# Discord / provider / network module is imported.


STAGE30_5_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "re",
)


STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_5_migration_context_models"
)
STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE: str = (
    "PHX2.stage30.stage30_5_migration_context_source_protocol"
)
STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_5_migration_context_adapter"
)


STAGE30_5_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
)


# ---------------------------------------------------------------------------
# Stage 30.5.2 opt-in compact migration runtime adapter inventory
# ---------------------------------------------------------------------------
#
# Stage 30.5.2 wires the Stage 30.5.1 migration-context projection into
# the existing Stage 30.4.2 compact runtime replacement path via a duck-
# typed resolver. The only NEW Stage 30.5.2-owned production file is the
# offline compact migration runtime adapter (the resolver). The Stage
# 30.4.2 orchestrator gains one optional duck-typed
# ``migration_context_resolver`` parameter, but that file is a Stage 30.4
# file already in the parent Stage 30.0 inventory and is NOT re-listed
# here. NO renderer change, NO new artifact writer, NO live / Discord /
# provider / bridge change, NO ATH, NO Net.


STAGE30_5_2_MINOR_VERSION: str = "30.5.2"


STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME: str = (
    "stage30_5_compact_migration_runtime_adapter.py"
)


STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_5_compact_migration_runtime_adapter"
)


# The new production files Stage 30.5.2 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.5.1 inventory: exactly the
# offline compact migration runtime adapter. (The Stage 30.4.2
# orchestrator edit reuses an existing inventory file.)
STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2: Tuple[str, ...] = (
    STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
)


# The single production module the Stage 30.5.2 boundary test scans for
# forbidden imports / text needles.
STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME,
)


STAGE30_5_2_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_5_2_compact_migration_runtime_adapter.py",
    "test_stage_30_5_2_runtime_integration.py",
    "test_stage_30_5_2_boundaries.py",
    "test_stage_30_5_2_manifest.py",
)


# Every non-PHX2 import in the Stage 30.5.2 runtime adapter must be in
# this stdlib allowlist (the adapter is a thin projector seam: it needs
# only ``__future__`` + ``typing``).
STAGE30_5_2_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# Every PHX2 import in the Stage 30.5.2 runtime adapter must be one of
# the two Stage 30.5.1 sibling modules (the projector + the closed-set
# display vocabulary). This positive allowlist proves, by construction,
# that the Stage 30.5.2 adapter imports NO Stage 29 / Stage 28 / Stage
# 30.1-30.4 / Discord / provider / network module, and reaches NO ATH /
# Net market-context model.
STAGE30_5_2_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE,
    STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE,
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 private side-channel modules the Stage 30.5 production
# code must NEVER import
# ---------------------------------------------------------------------------
#
# Stage 30.5.0 spec lock §6 hard boundary: Stage 30.5 must NOT import
# the Stage 29.5.5 private side-channel renderer, the Stage 29.5.5
# recorder, or the Stage 29.5.5 side-channel artifact writer. Those
# are the Discord-rendering side-channel surface and must stay on the
# Stage 29.5 side.
#
# The renderer basename carries a provider-platform substring; it is
# assembled here from word-split literals so this manifest's own
# source text does NOT carry the bare needle (mirrors the Stage 30.4
# split-literal discipline). The boundary test reconstructs the full
# module path and asserts no Stage 30.5.1 production module imports it.
# (Asserting "no PHX2.stage29 import at all" is the stronger superset
# check the boundary test actually enforces; these names document the
# specific must-not-import surface.)


STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES: Tuple[str, ...] = (
    (
        "PHX2.stage29.stage29_5_5_private_"
        + "dis"
        + "cord"
        + "_migration_context_renderer"
    ),
    "PHX2.stage29.stage29_5_5_migration_context_recorder",
    "PHX2.stage29.stage29_5_5_side_channel_artifact_writer",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.5.1 boundary test walks the actual import lines of the
# production modules and asserts none resolve to a module covered by
# this policy. The strings below are plain (the line-based scan never
# substring-matches them against source text).


STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
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
    "from PHX2.stage21",
    "from PHX2.stage22",
    "from PHX2.stage23",
    "from PHX2.stage24",
    "from PHX2.stage25",
    "from PHX2.stage26",
    "from PHX2.stage27",
    "from PHX2.stage28",
    "from PHX2.stage29",
    "import PHX2.stage29",
    "from PHX1",
    "import PHX1",
)


# ---------------------------------------------------------------------------
# Forbidden text needles (already-lowercased; scan must lowercase the
# haystack)
# ---------------------------------------------------------------------------
#
# Every needle is built with a split-literal concatenation so this
# manifest source text itself does NOT carry the bare needle. The
# Stage 30.5.1 boundary test imports this tuple at runtime and scans
# every Stage 30.5.1 scanned production module case-insensitively for
# substring matches against the runtime-concatenated values.


STAGE30_5_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "b" + "earer ",
    "author" + "ization:",
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
    "STAGE30_5_MINOR_VERSION",
    "STAGE30_5_1_MINOR_VERSION",
    "STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION",
    "STAGE30_5_MANIFEST_BASENAME",
    "STAGE30_5_1_MIGRATION_CONTEXT_MODELS_BASENAME",
    "STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_BASENAME",
    "STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_BASENAME",
    "STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_1",
    "STAGE30_5_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_5_1_TEST_BASENAMES",
    "STAGE30_5_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_5_1_MIGRATION_CONTEXT_MODELS_MODULE",
    "STAGE30_5_1_MIGRATION_CONTEXT_SOURCE_PROTOCOL_MODULE",
    "STAGE30_5_1_MIGRATION_CONTEXT_ADAPTER_MODULE",
    "STAGE30_5_1_ALLOWED_PHX2_IMPORTS",
    # Stage 30.5.2 opt-in compact migration runtime adapter inventory.
    "STAGE30_5_2_MINOR_VERSION",
    "STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_BASENAME",
    "STAGE30_5_2_COMPACT_MIGRATION_RUNTIME_ADAPTER_MODULE",
    "STAGE30_5_ALLOWED_STAGE30_BASENAMES_FOR_30_5_2",
    "STAGE30_5_2_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_5_2_TEST_BASENAMES",
    "STAGE30_5_2_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_5_2_ALLOWED_PHX2_IMPORTS",
    "STAGE30_5_FORBIDDEN_STAGE29_5_5_MODULES",
    "STAGE30_5_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_5_FORBIDDEN_TEXT_NEEDLES",
)
