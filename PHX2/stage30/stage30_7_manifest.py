"""Stage 30.7.0 ATH context bridge spec-lock manifest.

Constants-only spec-lock manifest. Pins the Stage 30.7.0 inventory
(spec basename, manifest basename, test basenames), the Stage 30.7
substage sequence, the closed-set ATH confidence-status tokens, the
closed-set ATH source-status tokens, the closed-set ATH unit tokens,
the closed-set ATH basis tokens, the reused compact display slot, the
preserved compact line shape, the forbidden runtime imports, and the
forbidden text needles.

Stage 30.7 is the ATH context family of Stage 30. It moves the compact
body ``ATH`` token from the literal ``Unknown`` toward an honest,
evidence-backed ATH display value, and eventually supports accurate
drawdown / tier context. ATH is a measurement / evidence problem: an
honest ATH market cap requires the circulating supply at the
historical peak, which no current source ships directly. Stage 30.7.0
LOCKS the architecture as prose + constants; it ships NO ATH bridge
code, NO renderer change, NO runtime wiring, NO source adapter, NO live
run, NO Discord send, NO provider call, and NO candidate scan.

Stage 30.7.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this manifest.
  * ZERO ATH bridge, ZERO ATH models, ZERO projection adapter, ZERO
    source bridge, ZERO renderer change, ZERO runtime wiring.
  * ZERO modification to Stage 25 / 27 / 28 / 29 or Stage 30.1 / 30.2 /
    30.3 / 30.4 / 30.5 / 30.6 runtime source.
  * ZERO live provider call. ZERO Discord send. ZERO env read. ZERO
    candidate scan. ZERO database migration. ZERO filesystem writer.
    ZERO compression. ZERO filters. ZERO enforcement.

Stage 30.7.1+ scope (deferred, each separately operator-authorized):

  * 30.7.1 -- ATH context models + pure projection adapter (fakes).
  * 30.7.2 -- fake-wire the ATH projection into the compact ping using
              the existing ``ath_mc_text`` slot (opt-in orchestrator).
  * 30.7.3 -- bridge sanitized Stage 25 / 27 / 29 ATH evidence into the
              Stage 30 ATH resolver (fake tests, narrow allowlist).
  * 30.7.4 -- offline runtime proof with MC + Mig + ATH (no Discord).
  * 30.7.5 -- controlled live ATH probe / dry-run only, after a
              separate audit and only if separately operator-authorized.

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


STAGE30_7_MINOR_VERSION: str = "30.7"
STAGE30_7_0_MINOR_VERSION: str = "30.7.0"


STAGE30_7_SPEC_BASENAME: str = (
    "STAGE_30_7_0_ATH_CONTEXT_SPEC_LOCK.md"
)
STAGE30_7_MANIFEST_BASENAME: str = "stage30_7_manifest.py"


# ---------------------------------------------------------------------------
# Stage 30.7.0 test inventory (pin test only)
# ---------------------------------------------------------------------------


STAGE30_7_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_7_0_ath_context_spec_lock.py",
)


# ---------------------------------------------------------------------------
# Stage 30.7.0 production-inventory delta
# ---------------------------------------------------------------------------
#
# The new files Stage 30.7.0 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.6 inventory. Exactly the spec lock
# markdown plus this manifest module; NO production .py beyond the
# manifest at Stage 30.7.0. No Stage 30.7.1+ ATH models / projection
# adapter / source bridge file.


STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0: Tuple[str, ...] = (
    STAGE30_7_SPEC_BASENAME,
    STAGE30_7_MANIFEST_BASENAME,
)


# ---------------------------------------------------------------------------
# Stage 30.7 substage sequence (pinned)
# ---------------------------------------------------------------------------


STAGE30_7_SUBSTAGE_SEQUENCE: Tuple[str, ...] = (
    "30.7.0",
    "30.7.1",
    "30.7.2",
    "30.7.3",
    "30.7.4",
    "30.7.5",
)


# ---------------------------------------------------------------------------
# ATH confidence status (closed set of three)
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 30.5 migration status discipline (KNOWN /
# UNVERIFIED / UNKNOWN). Only ATH_KNOWN renders a ``$Y`` value in the
# compact line; ATH_UNVERIFIED and ATH_UNKNOWN render ``Unknown``.


STAGE30_7_ATH_STATUS_KNOWN: str = "ATH_KNOWN"
STAGE30_7_ATH_STATUS_UNVERIFIED: str = "ATH_UNVERIFIED"
STAGE30_7_ATH_STATUS_UNKNOWN: str = "ATH_UNKNOWN"


STAGE30_7_ATH_STATUS_VALUES: Tuple[str, ...] = (
    STAGE30_7_ATH_STATUS_KNOWN,
    STAGE30_7_ATH_STATUS_UNVERIFIED,
    STAGE30_7_ATH_STATUS_UNKNOWN,
)


# ---------------------------------------------------------------------------
# ATH source status (closed set of five)
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 30.5 source-status set and adds CONFLICTING:
# cross-source ATH disagreement is a real ATH failure mode and must
# degrade conservatively to ``Unknown`` rather than picking a peak.
# A non-PRESENT source status dominates any claimed ATH value.


STAGE30_7_ATH_SOURCE_STATUS_PRESENT: str = "PRESENT"
STAGE30_7_ATH_SOURCE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
STAGE30_7_ATH_SOURCE_STATUS_ERROR: str = "ERROR"
STAGE30_7_ATH_SOURCE_STATUS_STALE: str = "STALE"
STAGE30_7_ATH_SOURCE_STATUS_CONFLICTING: str = "CONFLICTING"


STAGE30_7_ATH_SOURCE_STATUS_VALUES: Tuple[str, ...] = (
    STAGE30_7_ATH_SOURCE_STATUS_PRESENT,
    STAGE30_7_ATH_SOURCE_STATUS_UNAVAILABLE,
    STAGE30_7_ATH_SOURCE_STATUS_ERROR,
    STAGE30_7_ATH_SOURCE_STATUS_STALE,
    STAGE30_7_ATH_SOURCE_STATUS_CONFLICTING,
)


# ---------------------------------------------------------------------------
# ATH unit (closed set of three)
# ---------------------------------------------------------------------------
#
# The compact ATH display must share the same currency basis as the
# displayed ``MC``. USD is the Birdeye reporting unit; SOL is the
# on-chain native unit (supported later); UNKNOWN otherwise. The spec
# forbids ever treating USD as SOL or SOL as USD.


STAGE30_7_ATH_UNIT_USD: str = "USD"
STAGE30_7_ATH_UNIT_SOL: str = "SOL"
STAGE30_7_ATH_UNIT_UNKNOWN: str = "UNKNOWN"


STAGE30_7_ATH_UNIT_VALUES: Tuple[str, ...] = (
    STAGE30_7_ATH_UNIT_USD,
    STAGE30_7_ATH_UNIT_SOL,
    STAGE30_7_ATH_UNIT_UNKNOWN,
)


# ---------------------------------------------------------------------------
# ATH basis (closed set of three)
# ---------------------------------------------------------------------------
#
# The honesty axis. Only an observed market-cap basis can support
# ATH_KNOWN. A price-derived ATH market cap assumes a supply that may
# not match the supply at the historical peak, so it is at most
# ATH_UNVERIFIED, never ATH_KNOWN, in the first slice.


STAGE30_7_ATH_BASIS_MARKET_CAP_OBSERVED: str = (
    "ATH_MARKET_CAP_OBSERVED"
)
STAGE30_7_ATH_BASIS_PRICE_DERIVED: str = "ATH_PRICE_DERIVED"
STAGE30_7_ATH_BASIS_NONE: str = "ATH_BASIS_NONE"


STAGE30_7_ATH_BASIS_VALUES: Tuple[str, ...] = (
    STAGE30_7_ATH_BASIS_MARKET_CAP_OBSERVED,
    STAGE30_7_ATH_BASIS_PRICE_DERIVED,
    STAGE30_7_ATH_BASIS_NONE,
)


# ---------------------------------------------------------------------------
# Compact display reuse (no renderer change)
# ---------------------------------------------------------------------------
#
# The first wiring slice (Stage 30.7.2) feeds the ATH display string
# through the EXISTING Stage 30.2 ``ath_mc_text`` display slot the
# renderer already maps to the ``ATH`` token, exactly as Stage 30.4.2
# reused ``current_mc_text`` / ``lp_text`` and Stage 30.5.2 reused
# ``migration_mc_text``. The Stage 30.2 renderer / models are NOT
# modified anywhere in the Stage 30.7 family.


STAGE30_7_REUSED_COMPACT_SLOT_FIELD: str = "ath_mc_text"
STAGE30_7_COMPACT_DISPLAY_UNKNOWN: str = "Unknown"
STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE: str = (
    "• MC: <mc> | ATH: <ath> | Mig: <mig>"
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.7.0 pin test walks the actual import lines of the Stage
# 30.7.0 Python files (this manifest + the pin test) and asserts none
# resolve to a module covered by this policy. The strings below are
# plain (the line-based scan never substring-matches them against
# source text).


STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces Stage 30.7.0 spec-lock files must not touch.
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
    # No compression dependency / implementation at Stage 30.7.0.
    "import zstandard",
    "from zstandard",
    "import zstd",
    "from zstd",
    # Stage 25-29 production surfaces (the ATH evidence side stays on
    # the evidence side; the Stage 30 compact runtime must not import
    # a live provider client).
    "from PHX2.stage21",
    "from PHX2.stage22",
    "from PHX2.stage23",
    "from PHX2.stage24",
    "from PHX2.stage25",
    "from PHX2.stage26",
    "from PHX2.stage27",
    "from PHX2.stage28",
    "from PHX2.stage29",
    "import PHX2.stage25",
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
# this manifest source text itself does NOT carry the bare needle. The
# Stage 30.7.0 pin test imports this tuple at runtime and scans every
# Stage 30.7.0 file (spec lock, manifest, test) case-insensitively for
# substring matches against the runtime-concatenated values. The spec
# doc paraphrases every secret / transport surface (for example
# "provider credential", "private transport destination", "transport
# scheme prefix", "request auth metadata", "HTTP header metadata") so
# it carries none of the bare needles, while still being free to name
# the provider families (Birdeye / Dexscreener / Chainstack / Helius)
# in the prose "do not call" lists -- those bare family names are NOT
# needles; only their host / scheme / secret forms are.


STAGE30_7_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    "api" + " key",
    "api_" + "key",
    "x-api-" + "key",
    "x-" + "token",
    "web" + "hook url",
    "discord web" + "hook url",
    "endpoint" + " url",
    "endpoint" + "_secret",
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "raw" + "_body",
    "response" + "_body",
    "request" + "_body",
    "head" + "ers",
    "author" + "ization",
    "b" + "earer",
    "public-api.birdeye" + ".so",
    "dex" + "screener.com",
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
)


# ---------------------------------------------------------------------------
# Stage 30.7.1 ATH context models + pure projection adapter inventory
# ---------------------------------------------------------------------------
#
# Stage 30.7.1 is the FIRST Stage 30.7 production slice: a pure offline
# ATH-context projection brain (closed-set models + a deterministic
# projection adapter). It is NOT a renderer change, NOT a runtime
# wiring, NOT a source bridge, NOT a live provider call, and NOT a
# drawdown / tier recomputation. The two NEW production files are the
# models module + the projection adapter module. NO renderer / model /
# orchestrator edit, NO Stage 25 / 27 / 28 / 29 import, NO live /
# Discord / provider / DB / filesystem writer / compression, NO Net, NO
# filters, NO enforcement, NO Stage 30.7.2+ file.


STAGE30_7_1_MINOR_VERSION: str = "30.7.1"


STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_7_1_v0_ath_context"
)
STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION: str = (
    "stage30_7_ath_context_projection_v0"
)


# The displayed ATH must share the displayed ``MC`` currency basis; USD
# is the default market-context unit.
STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT: str = "USD"


STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME: str = (
    "stage30_7_ath_context_models.py"
)
STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME: str = (
    "stage30_7_ath_context_projection.py"
)


STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_7_ath_context_models"
)
STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE: str = (
    "PHX2.stage30.stage30_7_ath_context_projection"
)


# The NEW production files Stage 30.7.1 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.6 + 30.7.0 inventory:
# exactly the ATH context models + projection adapter. NO Stage 30.7.2+
# file. (The Stage 30.7.0 manifest is already in the parent inventory.)
STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1: Tuple[str, ...] = (
    STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
)


# The two production modules the Stage 30.7.1 boundary test scans for
# forbidden imports / text needles.
STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME,
)


STAGE30_7_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_7_1_ath_context_models.py",
    "test_stage_30_7_1_ath_context_projection.py",
    "test_stage_30_7_1_boundaries.py",
    "test_stage_30_7_1_manifest.py",
)


# Every non-PHX2 import in a Stage 30.7.1 production module must be in
# this stdlib allowlist; every PHX2 import must be the Stage 30.7.1
# models sibling. This positive allowlist proves, by construction, that
# NO os / pathlib / shutil / sqlite3 / zstd / network / Discord /
# provider / compact-renderer / orchestrator / Stage 21-29 module is
# imported.
STAGE30_7_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
    "math",
    "re",
)


STAGE30_7_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
)


# Closed-set ATH status / source-status / unit / basis / reason tokens
# (mirrored from the Stage 30.7.1 models module; the manifest test
# cross-checks they match ``stage30_7_ath_context_models``).
# Documentation + drift guard.
STAGE30_7_1_ATH_STATUS_VALUES: Tuple[str, ...] = (
    "ATH_KNOWN",
    "ATH_UNVERIFIED",
    "ATH_UNKNOWN",
)


STAGE30_7_1_ATH_SOURCE_STATUS_VALUES: Tuple[str, ...] = (
    "PRESENT",
    "UNAVAILABLE",
    "ERROR",
    "STALE",
    "CONFLICTING",
)


STAGE30_7_1_ATH_UNIT_VALUES: Tuple[str, ...] = (
    "USD",
    "SOL",
    "UNKNOWN",
)


STAGE30_7_1_ATH_BASIS_VALUES: Tuple[str, ...] = (
    "ATH_MARKET_CAP_OBSERVED",
    "ATH_PRICE_DERIVED",
    "ATH_BASIS_NONE",
)


STAGE30_7_1_ATH_REASON_VALUES: Tuple[str, ...] = (
    "ATH_KNOWN_USD_MARKET_CAP",
    "ATH_UNVERIFIED_PRICE_DERIVED",
    "ATH_UNKNOWN_SOURCE_UNAVAILABLE",
    "ATH_UNKNOWN_SOURCE_ERROR",
    "ATH_UNKNOWN_SOURCE_STALE",
    "ATH_UNKNOWN_SOURCE_CONFLICTING",
    "ATH_UNKNOWN_VALUE_MISSING",
    "ATH_UNKNOWN_VALUE_NOT_NUMERIC",
    "ATH_UNKNOWN_VALUE_NOT_FINITE",
    "ATH_UNKNOWN_VALUE_NON_POSITIVE",
    "ATH_UNKNOWN_UNIT_UNSUPPORTED",
    "ATH_UNKNOWN_UNIT_INCOMPATIBLE",
    "ATH_UNKNOWN_REDACTION_UNSAFE",
    "ATH_UNKNOWN_INVALID_INPUT",
)


# ---------------------------------------------------------------------------
# Stage 30.7.2 opt-in compact ATH runtime adapter inventory
# ---------------------------------------------------------------------------
#
# Stage 30.7.2 wires the Stage 30.7.1 ATH-context projection into the
# existing Stage 30.4.2 compact runtime replacement path via a duck-typed
# resolver, so the compact body ``ATH`` token can carry a trusted ``$Y``
# value through the EXISTING Stage 30.2 ``ath_mc_text`` display slot
# instead of the literal ``Unknown`` (exactly as Stage 30.5.2 reused the
# ``migration_mc_text`` slot for the ``Mig`` token). The only NEW Stage
# 30.7.2-owned production file is the offline compact ATH runtime adapter
# (the projection-to-text converter + the duck-typed resolver). The Stage
# 30.4.2 orchestrator gains one optional duck-typed ``ath_context_resolver``
# parameter, but that file is a Stage 30.4 file already in the parent Stage
# 30.0 inventory and is NOT re-listed here. NO renderer / models change,
# NO new artifact writer, NO live / Discord / provider / DB / filesystem
# writer / compression change, NO drawdown / tier recomputation, NO ATH
# source bridge, NO Net, NO filters, NO enforcement.
#
# Future slice: Stage 30.7.3 bridges sanitized upstream Stage 25 / 27 / 29
# ATH evidence into the Stage 30 ATH resolver (fake tests, narrow
# allowlist); it is NOT admitted by the Stage 30.7.2 inventory.


STAGE30_7_2_MINOR_VERSION: str = "30.7.2"


STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_BASENAME: str = (
    "stage30_7_compact_ath_runtime_adapter.py"
)


STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_7_compact_ath_runtime_adapter"
)


# The new production files Stage 30.7.2 adds under ``PHX2/stage30/`` on
# top of the already-allowed Stage 30.0..30.7.1 inventory: exactly the
# offline compact ATH runtime adapter. (The Stage 30.4.2 orchestrator
# edit reuses an existing inventory file.)
STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_2: Tuple[str, ...] = (
    STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_BASENAME,
)


# The single production module the Stage 30.7.2 boundary test scans for
# forbidden imports / text needles.
STAGE30_7_2_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_BASENAME,
)


STAGE30_7_2_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_7_2_compact_ath_runtime_adapter.py",
    "test_stage_30_7_2_runtime_integration.py",
    "test_stage_30_7_2_boundaries.py",
    "test_stage_30_7_2_manifest.py",
)


# Every non-PHX2 import in the Stage 30.7.2 runtime adapter must be in
# this stdlib allowlist (the adapter is a thin projector seam: it needs
# only ``__future__`` + ``typing``).
STAGE30_7_2_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# Every PHX2 import in the Stage 30.7.2 runtime adapter must be one of the
# two Stage 30.7.1 sibling modules (the closed-set models + the pure
# projection adapter). This positive allowlist proves, by construction,
# that the Stage 30.7.2 adapter imports NO Stage 21-29 / Stage 28 / Stage
# 30.1-30.6 runtime / Discord / provider / network / disk module (so the
# compact renderer / models / orchestrator and the tier-decision modules
# are unreachable, and NO drawdown / tier recomputation is wired).
STAGE30_7_2_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE,
)


# ---------------------------------------------------------------------------
# Stage 30.7.3 sanitized upstream ATH-evidence bridge inventory
# ---------------------------------------------------------------------------
#
# Stage 30.7.3 ships the Stage-30-owned offline bridge that normalizes a
# sanitized upstream ATH-evidence shape (the safe scalar summary a Stage 25
# ATH candidate, a Stage 27.4 ATH context record, or a Stage 29.2 Birdeye
# ATH snapshot reduces to) into the Stage 30.7.1 ATH-context evidence
# carrier, then reuses the EXISTING Stage 30.7.1 projection + Stage 30.7.2
# compact adapter to produce the compact ``ATH`` display string. The single
# NEW Stage 30.7.3-owned production file is the sanitized ATH bridge. The
# bridge imports NO Stage 25 / 27 / 28 / 29 module: it consumes a sanitized
# duck-typed / dict-like scalar input and reuses only the two Stage 30.7
# sibling modules (the closed-set models + the Stage 30.7.2 compact ATH
# runtime adapter, which wraps the Stage 30.7.1 pure projection). The
# broader "sanitized" name (not "stage29") is used precisely because the
# bridge is generic over the Stage 25 / 27.4 / 29.2 upstream ATH shape and
# is NOT bound to a single Stage 29 module. NO renderer / models change, NO
# orchestrator edit (the Stage 30.7.2 ``ath_context_resolver`` seam is
# reused), NO live / Discord / provider / DB / filesystem writer /
# compression change, NO drawdown / tier recomputation, NO live ATH probe,
# NO Net, NO filters, NO enforcement.
#
# Future slice: Stage 30.7.4 is the offline runtime proof with MC + Mig +
# ATH (no Discord); it is NOT admitted by the Stage 30.7.3 inventory.


STAGE30_7_3_MINOR_VERSION: str = "30.7.3"


STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME: str = (
    "stage30_7_sanitized_ath_bridge.py"
)


STAGE30_7_3_SANITIZED_ATH_BRIDGE_MODULE: str = (
    "PHX2.stage30.stage30_7_sanitized_ath_bridge"
)


# The new production files Stage 30.7.3 adds under ``PHX2/stage30/`` on top
# of the already-allowed Stage 30.0..30.7.2 inventory: exactly the offline
# sanitized upstream ATH-evidence bridge. (The Stage 30.7.2
# ``ath_context_resolver`` seam is reused with no orchestrator edit.)
STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3: Tuple[str, ...] = (
    STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
)


# The single production module the Stage 30.7.3 boundary test scans for
# forbidden imports / text needles.
STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME,
)


STAGE30_7_3_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_7_3_sanitized_ath_bridge.py",
    "test_stage_30_7_3_runtime_integration.py",
    "test_stage_30_7_3_boundaries.py",
    "test_stage_30_7_3_manifest.py",
)


# Every non-PHX2 import in the Stage 30.7.3 bridge must be in this stdlib
# allowlist (the bridge needs ``__future__`` + ``typing`` + ``dataclasses``
# for the sanitized-evidence dataclass).
STAGE30_7_3_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# Every PHX2 import in the Stage 30.7.3 bridge must be one of these two
# Stage 30.7 sibling modules: the Stage 30.7.1 closed-set models (the
# evidence carrier + tokens) and the Stage 30.7.2 compact ATH runtime
# adapter (the projection-to-text converter + duck-typed resolver, which
# itself wraps the Stage 30.7.1 pure projection). This positive allowlist
# proves, by construction, that the Stage 30.7.3 bridge imports NO Stage 25
# / 27 / 28 / 29 / Stage 30.1-30.6 runtime / Discord / provider / network /
# disk module (so the compact renderer / models / orchestrator and the
# tier-decision modules are unreachable, and NO drawdown / tier
# recomputation is wired).
STAGE30_7_3_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE,
    STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE,
)


__all__ = (
    # Version axes + basenames.
    "STAGE30_7_MINOR_VERSION",
    "STAGE30_7_0_MINOR_VERSION",
    "STAGE30_7_SPEC_BASENAME",
    "STAGE30_7_MANIFEST_BASENAME",
    "STAGE30_7_0_TEST_BASENAMES",
    "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0",
    # Substage sequence.
    "STAGE30_7_SUBSTAGE_SEQUENCE",
    # ATH confidence status closed set.
    "STAGE30_7_ATH_STATUS_KNOWN",
    "STAGE30_7_ATH_STATUS_UNVERIFIED",
    "STAGE30_7_ATH_STATUS_UNKNOWN",
    "STAGE30_7_ATH_STATUS_VALUES",
    # ATH source status closed set.
    "STAGE30_7_ATH_SOURCE_STATUS_PRESENT",
    "STAGE30_7_ATH_SOURCE_STATUS_UNAVAILABLE",
    "STAGE30_7_ATH_SOURCE_STATUS_ERROR",
    "STAGE30_7_ATH_SOURCE_STATUS_STALE",
    "STAGE30_7_ATH_SOURCE_STATUS_CONFLICTING",
    "STAGE30_7_ATH_SOURCE_STATUS_VALUES",
    # ATH unit closed set.
    "STAGE30_7_ATH_UNIT_USD",
    "STAGE30_7_ATH_UNIT_SOL",
    "STAGE30_7_ATH_UNIT_UNKNOWN",
    "STAGE30_7_ATH_UNIT_VALUES",
    # ATH basis closed set.
    "STAGE30_7_ATH_BASIS_MARKET_CAP_OBSERVED",
    "STAGE30_7_ATH_BASIS_PRICE_DERIVED",
    "STAGE30_7_ATH_BASIS_NONE",
    "STAGE30_7_ATH_BASIS_VALUES",
    # Compact display reuse.
    "STAGE30_7_REUSED_COMPACT_SLOT_FIELD",
    "STAGE30_7_COMPACT_DISPLAY_UNKNOWN",
    "STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE",
    # Forbidden surfaces.
    "STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_7_FORBIDDEN_TEXT_NEEDLES",
    # Stage 30.7.1 ATH context models + projection adapter inventory.
    "STAGE30_7_1_MINOR_VERSION",
    "STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION",
    "STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION",
    "STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT",
    "STAGE30_7_1_ATH_CONTEXT_MODELS_BASENAME",
    "STAGE30_7_1_ATH_CONTEXT_PROJECTION_BASENAME",
    "STAGE30_7_1_ATH_CONTEXT_MODELS_MODULE",
    "STAGE30_7_1_ATH_CONTEXT_PROJECTION_MODULE",
    "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_1",
    "STAGE30_7_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_7_1_TEST_BASENAMES",
    "STAGE30_7_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_7_1_ALLOWED_PHX2_IMPORTS",
    "STAGE30_7_1_ATH_STATUS_VALUES",
    "STAGE30_7_1_ATH_SOURCE_STATUS_VALUES",
    "STAGE30_7_1_ATH_UNIT_VALUES",
    "STAGE30_7_1_ATH_BASIS_VALUES",
    "STAGE30_7_1_ATH_REASON_VALUES",
    # Stage 30.7.2 opt-in compact ATH runtime adapter inventory.
    "STAGE30_7_2_MINOR_VERSION",
    "STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_BASENAME",
    "STAGE30_7_2_COMPACT_ATH_RUNTIME_ADAPTER_MODULE",
    "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_2",
    "STAGE30_7_2_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_7_2_TEST_BASENAMES",
    "STAGE30_7_2_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_7_2_ALLOWED_PHX2_IMPORTS",
    # Stage 30.7.3 sanitized upstream ATH-evidence bridge inventory.
    "STAGE30_7_3_MINOR_VERSION",
    "STAGE30_7_3_SANITIZED_ATH_BRIDGE_BASENAME",
    "STAGE30_7_3_SANITIZED_ATH_BRIDGE_MODULE",
    "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_3",
    "STAGE30_7_3_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_7_3_TEST_BASENAMES",
    "STAGE30_7_3_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_7_3_ALLOWED_PHX2_IMPORTS",
)
