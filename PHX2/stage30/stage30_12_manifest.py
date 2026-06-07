"""Stage 30.12 PHOENIX private operator ping renderer manifest.

Constants-only manifest. Pins the Stage 30.12 inventory (the renderer models +
renderer + this manifest), the locked schema version, the stdlib + PHX2 import
allowlists, the mirrored tier-token + tier-band display vocabulary, the
forbidden URL / secret / transport source-text needles the Stage 30.12 boundary
scan checks the production source against, the forbidden-surface list, and the
operator-auth note for the (separate) live-wiring step.

Stage 30.12 is the committed PHOENIX private operator ping renderer: the
committed home for the rich operator body the first real private send
improvised out-of-repo (ceremony glue, NOT a committed renderer). It is a pure
LEAF -- the models import NO PHX2 module, the renderer imports ONLY the models
sibling, and NO existing Stage 27-29 / Stage 30.1 / Stage 30.2 / Stage 30.11
production file is edited. It is NOT wired into the Stage 30.11.5 bounded-runner
/ dip-gate / transport send path; wiring it into the live send path (and
carrying the rich price / LP / migration-timestamp / source-ref fields the
committed live chain does not yet supply at the body-builder boundary) is a
SEPARATE, explicitly operator-authorized step Stage 30.12 does not build.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * imports NO PHX2 module (the schema version + tier-token + tier-band display
    strings are mirrored BY VALUE; a pin test cross-checks them against the
    Stage 30.12 models module),
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no function / class definition,
  * contains no Call node (no implicit I/O at import time; the split-literal
    needle concatenations use ``+`` BinOps, never Calls),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple


# ---------------------------------------------------------------------------
# Stage id + minor version + schema version + purpose
# ---------------------------------------------------------------------------


STAGE30_12_STAGE_ID: str = "30.12"
STAGE30_12_MINOR_VERSION: str = "30.12"


# The Stage 30.12 renderer schema version (mirrored BY VALUE from the Stage
# 30.12 models module; a pin test cross-checks it matches).
STAGE30_12_RENDERER_SCHEMA_VERSION: str = (
    "stage30_12_v0_phoenix_operator_ping"
)


STAGE30_12_PURPOSE: str = "PHOENIX private operator ping renderer"


# ---------------------------------------------------------------------------
# Locked basenames + dotted module paths
# ---------------------------------------------------------------------------


STAGE30_12_MODELS_BASENAME: str = (
    "stage30_12_phoenix_operator_ping_models.py"
)
STAGE30_12_RENDERER_BASENAME: str = (
    "stage30_12_phoenix_operator_ping_renderer.py"
)
STAGE30_12_MANIFEST_BASENAME: str = "stage30_12_manifest.py"
# Stage 30.12.1 body-builder factory: the committed home for the body-builder
# glue that feeds the Stage 30.12 renderer through the EXISTING Stage 30.11.5
# ``compact_body_builder`` seam (no runner / sink / gate edit, no monkey-patch).
# A clean leaf -- it imports ONLY the two Stage 30.12 siblings below.
STAGE30_12_1_BODY_BUILDER_BASENAME: str = (
    "stage30_12_1_phoenix_operator_ping_body_builder.py"
)


STAGE30_12_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_12_phoenix_operator_ping_models"
)
STAGE30_12_RENDERER_MODULE: str = (
    "PHX2.stage30.stage30_12_phoenix_operator_ping_renderer"
)
STAGE30_12_1_BODY_BUILDER_MODULE: str = (
    "PHX2.stage30.stage30_12_1_phoenix_operator_ping_body_builder"
)


# The NEW production files Stage 30.12 + Stage 30.12.1 add under ``PHX2/stage30/``
# on top of the already-allowed Stage 30.0..30.11.10 inventory: the Stage 30.12
# models + renderer + constants-only manifest, plus the Stage 30.12.1 body-builder
# factory.
STAGE30_12_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_12_MODELS_BASENAME,
    STAGE30_12_RENDERER_BASENAME,
    STAGE30_12_MANIFEST_BASENAME,
    STAGE30_12_1_BODY_BUILDER_BASENAME,
)


# The production modules the Stage 30.12 boundary test scans for forbidden
# imports / text needles. The constants-only manifest is EXCLUDED from this set
# (it documents the forbidden-surface family names + builds the forbidden-needle
# fragments, so scanning it against its own needles would self-collide); the
# manifest is validated separately by the Stage 30.12 manifest test (import
# cleanliness + no transport-scheme literal + no top-level call). The Stage
# 30.12.1 body-builder factory IS scanned (it is a clean leaf and must stay one).
STAGE30_12_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_12_MODELS_BASENAME,
    STAGE30_12_RENDERER_BASENAME,
    STAGE30_12_1_BODY_BUILDER_BASENAME,
)


STAGE30_12_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_12_phoenix_operator_ping_models.py",
    "test_stage_30_12_phoenix_operator_ping_renderer.py",
    "test_stage_30_12_boundaries.py",
    "test_stage_30_12_manifest.py",
    "test_stage_30_12_1_phoenix_operator_ping_body_builder.py",
)


# ---------------------------------------------------------------------------
# Import allowlists
# ---------------------------------------------------------------------------
#
# Every non-PHX2 import in a Stage 30.12 production module must be in this
# stdlib allowlist (the models need only ``typing``; the renderer needs ``re`` /
# ``decimal`` / ``typing`` for safe-shape validation + clean price formatting;
# the manifest needs only ``typing``). It admits NO ``os`` (so NO env read), NO
# ``sqlite3``, NO compression, NO network module, NO clock module.
STAGE30_12_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "re",
    "decimal",
)


# Every PHX2 import in a Stage 30.12 production module must be one of these two
# OWN siblings: the renderer imports the models sibling; the models + manifest
# import no PHX2 module. This positive allowlist proves, by construction, that
# NO Stage 21-29 / Stage 30.1 / Stage 30.2 / Stage 30.11 / runtime orchestrator
# / transport / Discord / live-provider module is imported (the slice is a leaf).
STAGE30_12_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_12_MODELS_MODULE,
    STAGE30_12_RENDERER_MODULE,
)


# ---------------------------------------------------------------------------
# Mirrored tier-token + tier-band display vocabulary (BY VALUE)
# ---------------------------------------------------------------------------
#
# Mirrored BY VALUE from the Stage 30.12 models module (a pin test cross-checks
# the equality). The renderer maps a tier token to its DISPLAY band ONLY; it
# changes NO committed Stage 30.1 tier logic. The band separator is an en dash.


STAGE30_12_TIER_TOKEN_TIER_1: str = "Tier 1"
STAGE30_12_TIER_TOKEN_TIER_2: str = "Tier 2"
STAGE30_12_TIER_TOKEN_TIER_3: str = "Tier 3"
STAGE30_12_TIER_TOKEN_TIER_UNKNOWN: str = "Tier Unknown"
STAGE30_12_TIER_TOKEN_TIER_NOT_APPLICABLE: str = "Tier Not Applicable"


STAGE30_12_TIER_BAND_DISPLAY_TIER_1: str = "50%–60%"
STAGE30_12_TIER_BAND_DISPLAY_TIER_2: str = "62%–80%"
STAGE30_12_TIER_BAND_DISPLAY_TIER_3: str = "82%–95%"


# ---------------------------------------------------------------------------
# Body cap + display sentinel + footer (mirrored BY VALUE)
# ---------------------------------------------------------------------------


STAGE30_12_BODY_CHAR_HARD_CAP: int = 1900
STAGE30_12_DISPLAY_UNKNOWN: str = "Unknown"
STAGE30_12_OPERATOR_FOOTER: str = "PRIVATE OPERATOR ONLY · PHX2"


# ---------------------------------------------------------------------------
# Forbidden source-text needles (already-lowercased; scan lowercases haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so this
# manifest source text itself does NOT carry the bare needle (and carries no
# contiguous transport-scheme separator). The Stage 30.12 boundary test scans
# every Stage 30.12 production module (models, renderer, manifest)
# case-insensitively for these. The set is intentionally PUNCTUATED (URL /
# webhook / auth / API-key / RPC / PEM forms) -- the things that should never
# appear as a literal in a leaf renderer's source -- NOT bare English words
# (so the modules' own discipline docstrings may name "webhook" / provider
# families as prose without tripping the scan).


STAGE30_12_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
    ":" + "/" + "/",                  # transport scheme separator
    "/" + "web" + "hooks" + "/",      # webhooks path segment
    "discord" + ".com",               # discord host
    "discord" + "app.com",            # discord app host
    "x-" + "api-" + "key",            # api-key header name
    "api_" + "key",                   # api-key assignment form
    "-----" + "begin",                # PEM block header
    "rpc" + "_url",                   # rpc url env-var form
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.12 renderer slice must not touch. Plain
# documentation words (family / feature names), NOT secret / host / transport
# needle forms.


STAGE30_12_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "live Discord send",
    "webhook call",
    "live provider call",
    "env read",
    "filesystem write",
    "wallet / signing",
    "trading verdict emission",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "enforcement activation",
    "WSOL quote mint as CA",
    "Stage 27 production source edit",
    "Stage 28 production source edit",
    "Stage 29 production source edit",
    "Stage 30.1 tier logic edit",
    "Stage 30.2 compact renderer edit",
    "Stage 30.11 runner / gate / transport edit",
    "Stage 30.11.5 bounded-runner send-path wiring",
    "commit",
    "tag",
    "push",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Live-wiring operator-auth note
# ---------------------------------------------------------------------------
#
# Stage 30.12 ships the pure renderer ONLY. Wiring it into the live private send
# path -- and supplying the rich price / LP / migration-timestamp / source-ref
# fields the committed live chain does not yet carry at the body-builder
# boundary -- is a SEPARATE, explicitly operator-authorized step.


STAGE30_12_LIVE_WIRING_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_12_LIVE_WIRING_NOTE: str = (
    "Stage 30.12 is the pure PHOENIX operator ping renderer only; wiring it "
    "into the live private send path is a separate, explicitly "
    "operator-authorized step that is not built here"
)


__all__ = (
    # Stage id + versions + purpose.
    "STAGE30_12_STAGE_ID",
    "STAGE30_12_MINOR_VERSION",
    "STAGE30_12_RENDERER_SCHEMA_VERSION",
    "STAGE30_12_PURPOSE",
    # Basenames + modules.
    "STAGE30_12_MODELS_BASENAME",
    "STAGE30_12_RENDERER_BASENAME",
    "STAGE30_12_MANIFEST_BASENAME",
    "STAGE30_12_1_BODY_BUILDER_BASENAME",
    "STAGE30_12_MODELS_MODULE",
    "STAGE30_12_RENDERER_MODULE",
    "STAGE30_12_1_BODY_BUILDER_MODULE",
    "STAGE30_12_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_12_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_12_TEST_BASENAMES",
    # Import allowlists.
    "STAGE30_12_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_12_ALLOWED_PHX2_IMPORTS",
    # Mirrored vocabulary.
    "STAGE30_12_TIER_TOKEN_TIER_1",
    "STAGE30_12_TIER_TOKEN_TIER_2",
    "STAGE30_12_TIER_TOKEN_TIER_3",
    "STAGE30_12_TIER_TOKEN_TIER_UNKNOWN",
    "STAGE30_12_TIER_TOKEN_TIER_NOT_APPLICABLE",
    "STAGE30_12_TIER_BAND_DISPLAY_TIER_1",
    "STAGE30_12_TIER_BAND_DISPLAY_TIER_2",
    "STAGE30_12_TIER_BAND_DISPLAY_TIER_3",
    "STAGE30_12_BODY_CHAR_HARD_CAP",
    "STAGE30_12_DISPLAY_UNKNOWN",
    "STAGE30_12_OPERATOR_FOOTER",
    # Forbidden needles + surfaces.
    "STAGE30_12_FORBIDDEN_TEXT_NEEDLES",
    "STAGE30_12_FORBIDDEN_SURFACES",
    # Live-wiring operator-auth note.
    "STAGE30_12_LIVE_WIRING_REQUIRES_OPERATOR_AUTH",
    "STAGE30_12_LIVE_WIRING_NOTE",
)
