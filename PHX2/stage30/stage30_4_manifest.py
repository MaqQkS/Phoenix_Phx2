"""Stage 30.4.0 compact market context spec-lock manifest.

Constants-only spec-lock manifest. Pins the Stage 30.4.0
inventory (spec basename, manifest basename, test basenames),
the Stage 30.4.0 contract surface (substage sequence, operator
decisions, forbidden runtime imports, forbidden text needles).

Stage 30.4 is the OPTIONAL compact market context enrichment
substage of Stage 30, pre-named in the parent Stage 30.0 spec
lock section 2 substage map. Stage 30.4 normalizes the parent
label drift ("volume" / "net flow") onto the renderer-facing
label "Net" (matches the implemented Stage 30.2 renderer body
label).

Stage 30.4.0 scope (this turn):

  * Spec lock + manifest + pin tests only.
  * ZERO production .py file beyond the manifest.
  * ZERO models, formatter, source protocol, adapter, artifact
    writer, runtime orchestrator.
  * ZERO modification to Stage 21-29 or Stage 30.1 / 30.2 / 30.3
    source.
  * ZERO Discord send. ZERO live provider call. ZERO env read.

Stage 30.4.1 scope (deferred, operator-authorized):

  * Offline-only models + formatter + source protocol + adapter
    + artifact writer.
  * Fake / offline tests only.

Stage 30.4.2 scope (deferred, operator-authorized):

  * Opt-in parallel compact runtime orchestrator that imports
    Stage 30.3 read-only and fills Stage 30.2 display slots from
    a fake / offline source.

Stage 30.4.3 scope (deferred, operator-authorized):

  * OPTIONAL controlled private proof, only after a real source
    adapter is separately authorized.

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
# Minor version + locked basenames
# ---------------------------------------------------------------------------


STAGE30_4_MINOR_VERSION: str = "30.4"


STAGE30_4_SPEC_BASENAME: str = "STAGE_30_4_SPEC_LOCK.md"
STAGE30_4_MANIFEST_BASENAME: str = "stage30_4_manifest.py"


# ---------------------------------------------------------------------------
# Stage 30.4.0 test inventory (pin test only)
# ---------------------------------------------------------------------------


STAGE30_4_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_4_0_spec_lock.py",
)


# ---------------------------------------------------------------------------
# Stage 30.4.0 production-inventory delta
# ---------------------------------------------------------------------------
#
# The new files Stage 30.4.0 adds under ``PHX2/stage30/`` on top of
# the already-allowed Stage 30.0..30.3 inventory. Exactly the spec
# lock markdown plus the manifest module; no production .py beyond
# the manifest at Stage 30.4.0.


STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0: Tuple[str, ...] = (
    STAGE30_4_SPEC_BASENAME,
    STAGE30_4_MANIFEST_BASENAME,
)


# ---------------------------------------------------------------------------
# Stage 30.4.1 production-inventory delta
# ---------------------------------------------------------------------------
#
# The new files Stage 30.4.1 adds under ``PHX2/stage30/`` on top of
# the Stage 30.4.0 inventory delta. Exactly the offline models +
# formatter + source protocol + adapter + artifact writer. NO
# Stage 30.4.2 orchestrator file. The 30.4.0 pin test allowlist
# (``STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0``) remains
# unchanged because it pins the 30.4.0 delta, not the 30.4.1 delta.


STAGE30_4_1_COMPACT_MARKET_CONTEXT_MODELS_BASENAME: str = (
    "stage30_4_compact_market_context_models.py"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_FORMATTER_BASENAME: str = (
    "stage30_4_compact_market_context_formatter.py"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_SOURCE_PROTOCOL_BASENAME: str = (
    "stage30_4_compact_market_context_source_protocol.py"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_ADAPTER_BASENAME: str = (
    "stage30_4_compact_market_context_adapter.py"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_WRITER_BASENAME: str = (
    "stage30_4_compact_market_context_artifact_writer.py"
)


STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1: Tuple[str, ...] = (
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_MODELS_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_FORMATTER_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SOURCE_PROTOCOL_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ADAPTER_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_WRITER_BASENAME,
)


# ---------------------------------------------------------------------------
# Stage 30.4.1 test inventory
# ---------------------------------------------------------------------------


STAGE30_4_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_4_1_models.py",
    "test_stage_30_4_1_formatter.py",
    "test_stage_30_4_1_adapter_unknown_path.py",
    "test_stage_30_4_1_adapter_present_path_with_fake_source.py",
    "test_stage_30_4_1_adapter_error_stale_paths.py",
    "test_stage_30_4_1_artifact_writer.py",
    "test_stage_30_4_1_boundaries.py",
)


# ---------------------------------------------------------------------------
# Stage 30.4.1 schema version + locked artifact basename
# ---------------------------------------------------------------------------


STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_4_1_v0_compact_market_context"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME: str = (
    "stage30_4_compact_market_context.jsonl"
)


# ---------------------------------------------------------------------------
# Stage 30.4 substage sequence (pinned)
# ---------------------------------------------------------------------------


STAGE30_4_SUBSTAGE_SEQUENCE: Tuple[str, ...] = (
    "30.4.0",
    "30.4.1",
    "30.4.2",
    "30.4.3",
)


# ---------------------------------------------------------------------------
# Operator decisions pinned at Stage 30.4.0
# ---------------------------------------------------------------------------


STAGE30_4_OPERATOR_DECISION_LABEL_NET: str = "Net"


STAGE30_4_OPERATOR_DECISION_FIRST_FIELDS: Tuple[str, ...] = (
    "MC",
    "LP",
)


STAGE30_4_OPERATOR_DECISION_DEFERRED_FIELDS: Tuple[str, ...] = (
    "Net",
    "ATH MC",
    "Migration MC",
)


STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL: str = (
    "birdeye_token_overview"
)


# Deferred source labels. Split-literal concatenations are used
# below so this manifest source text does NOT itself carry the
# bare provider-domain substrings that appear on the Stage 30.4.0
# forbidden text-needle list.


STAGE30_4_OPERATOR_DECISION_DEFERRED_SOURCES: Tuple[str, ...] = (
    "on-chain_supply_times_price",
    "dex" + "screener_cross_check",
    "birdeye_trade_data",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports
# ---------------------------------------------------------------------------
#
# Documentation tuple. The Stage 30.4.0 pin test parses 30.4.0
# Python files line-by-line and asserts that no ``import X`` /
# ``from X import Y`` statement resolves to a module covered by
# this policy. The strings below are kept in plain form because
# the pin test never uses them in a substring scan; the line-
# based parser cannot false-positive on a string literal inside
# a tuple.


STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces Stage 30.4 must not touch.
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
    # Stage 21-29 production surfaces (the Stage 30.4.0 pin test
    # walks the actual import lines, not these literal strings;
    # see ``test_no_stage21_29_imports_in_30_4_0_files``).
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
# Forbidden text needles (already-lowercased; scan must lowercase
# the haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so
# the manifest source text itself does NOT carry the bare needle.
# The Stage 30.4.0 pin test imports this tuple at runtime and scans
# every Stage 30.4.0 file (spec lock, manifest, test) case-
# insensitively for substring matches against the runtime-
# concatenated values.


STAGE30_4_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "b" + "earer",
    "author" + "ization:",
    "api_" + "key",
    "x-api-" + "key",
    "x-" + "token",
    "public-api.birdeye" + ".so",
    "dex" + "screener.com",
    "chain" + "stack",
    "hel" + "ius",
)


__all__ = (
    "STAGE30_4_MINOR_VERSION",
    "STAGE30_4_SPEC_BASENAME",
    "STAGE30_4_MANIFEST_BASENAME",
    "STAGE30_4_TEST_BASENAMES",
    "STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_MODELS_BASENAME",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_FORMATTER_BASENAME",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_SOURCE_PROTOCOL_BASENAME",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_ADAPTER_BASENAME",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_WRITER_BASENAME",
    "STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1",
    "STAGE30_4_1_TEST_BASENAMES",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME",
    "STAGE30_4_SUBSTAGE_SEQUENCE",
    "STAGE30_4_OPERATOR_DECISION_LABEL_NET",
    "STAGE30_4_OPERATOR_DECISION_FIRST_FIELDS",
    "STAGE30_4_OPERATOR_DECISION_DEFERRED_FIELDS",
    "STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL",
    "STAGE30_4_OPERATOR_DECISION_DEFERRED_SOURCES",
    "STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_4_FORBIDDEN_TEXT_NEEDLES",
)
