"""Stage 30.10.0 compact tier-dip eligibility gate spec-lock manifest.

Constants-only spec-lock manifest. Pins the Stage 30.10.0 inventory (the
spec-lock doc basename + path parts, this manifest basename, the test
basename), the Stage 30.10 stage id + spec version + next allowed substage,
the planned Stage 30.10.0 / 30.10.1 / 30.10.2 / 30.10.3 substage sequence,
the read-only audit findings the gate is built to correct, the gate
placement contract (BEFORE dispatch reservation / private send, never a
transport-layer veto for a normal non-dip skip), the existing reuse
surfaces (by exact name), the default fail-closed eligibility policy + its
explicit config fields, the eligibility-decision closed set + per-candidate
audit-record fields, the Stage 30.9.2 paused-not-abandoned relationship, the
forbidden surfaces the spec-lock slice (and the Stage 30.10 family) must not
touch, and the forbidden runtime imports / text needles the spec-lock files
are scanned against.

Stage 30.10 is the compact tier-dip eligibility gate. The most important
planning finding is that the live compact path can ALREADY render the
tier / ATH / drawdown labels but does NOT use them to decide whether to
send: a tradeable Stage 27.6 candidate from a provider hint event is
dispatched whenever it is not malformed / not deduped / not an
unknown-pair / not stale-price / not missing-price, so a live proof today
would emit migrated / tradeable compact pings (many ``Tier Unknown`` /
``Tier Not Applicable``), not true dip-filtered alerts. Stage 30.10 adds
the missing tier-dip eligibility gate so private compact pings are
dip-focused. Stage 30.10.0 LOCKS that design as prose + constants; it ships
NO runtime code, NO eligibility classifier, NO audit-record model, NO
runtime wiring, NO live provider call, NO Discord send, and edits NO
existing live runner / orchestrator / transport / Stage 28 suppression
file.

Stage 30.10.0 scope (this slice):

  * Spec lock + manifest + pin test only.
  * ZERO production .py file beyond this constants-only manifest.
  * ZERO eligibility classifier, ZERO audit-record model, ZERO runtime
    wiring, ZERO artifact integration.
  * ZERO new live runner, ZERO new provider, ZERO new readiness gate,
    ZERO direct Stage 28 suppression-logic edit.
  * ZERO live provider call, ZERO Discord send, ZERO live run, ZERO env
    read.
  * ZERO database / SQLite, ZERO zstd dependency / implementation, ZERO
    compression, ZERO default storage root, ZERO broad always-on daemon.
  * ZERO public / subscriber / paid routing, ZERO Telegram / X / social,
    ZERO trading / wallet / signing, ZERO enforcement, ZERO Stage 31.

Stage 30.10.1+ scope (deferred, each separately operator-authorized):

  * 30.10.1 -- the fake / offline eligibility model + classifier tests:
    a pure tier-dip classifier + per-candidate audit-record model, proven
    with fakes only; no runtime wiring, no live, no Discord.
  * 30.10.2 -- wire the OPTIONAL gate into the compact runtime path with
    fakes only: the gate is evaluated BEFORE dispatch reservation /
    private send; a non-dip skip is a normal no-send, never a transport
    failure.
  * 30.10.3 -- prove artifact integration: persist the eligibility audit
    record alongside the existing Stage 30.9 compact / artifact lane,
    offline only.

After Stage 30.10 proves dip-focused eligibility, the PAUSED Stage 30.9.2
live proof / operator handoff may resume. Stage 30.9.2 is paused, NOT
abandoned.

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


STAGE30_10_STAGE_ID: str = "30.10"
STAGE30_10_0_MINOR_VERSION: str = "30.10.0"
STAGE30_10_0_SPEC_VERSION: str = (
    "stage30_10_v0_compact_tier_dip_eligibility"
)


# ---------------------------------------------------------------------------
# Locked basenames + path parts + inventory delta
# ---------------------------------------------------------------------------


STAGE30_10_SPEC_LOCK_FILENAME: str = (
    "STAGE_30_10_0_COMPACT_TIER_DIP_ELIGIBILITY_SPEC_LOCK.md"
)
STAGE30_10_MANIFEST_BASENAME: str = "stage30_10_manifest.py"


# The repo-relative path parts of the spec-lock doc (so a pin test can
# join them without re-spelling the path).
STAGE30_10_SPEC_LOCK_PATH_PARTS: Tuple[str, ...] = (
    "PHX2",
    "stage30",
    STAGE30_10_SPEC_LOCK_FILENAME,
)


STAGE30_10_0_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_10_0_compact_tier_dip_eligibility_spec_lock.py",
)


# The NEW files Stage 30.10.0 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.9.1 inventory: exactly the spec-lock
# markdown plus this constants-only manifest. NO production .py beyond the
# manifest at Stage 30.10.0; NO Stage 30.10.1+ classifier / model / runtime
# file.
STAGE30_10_ALLOWED_INITIAL_FILES: Tuple[str, ...] = (
    STAGE30_10_SPEC_LOCK_FILENAME,
    STAGE30_10_MANIFEST_BASENAME,
)


# The only NEW production .py Stage 30.10.0 adds is this constants-only
# manifest; the spec lock is markdown. The boundary scan checks this
# basename for forbidden imports / needles.
STAGE30_10_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_10_MANIFEST_BASENAME,
)


# Every non-PHX2 import in this manifest must be in this stdlib allowlist
# (the manifest is constants-only: it needs only ``__future__`` +
# ``typing``). The spec-lock slice has NO PHX2 production import at all.
STAGE30_10_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# ---------------------------------------------------------------------------
# Planned substage sequence + next allowed stage
# ---------------------------------------------------------------------------
#
# Stage 30.10 is sequenced fake / offline before live, smallest reversible
# slice first. Exactly four planned substages; each separately
# operator-authorized.


STAGE30_10_PLANNED_SUBSTAGES: Tuple[str, ...] = (
    "30.10.0",
    "30.10.1",
    "30.10.2",
    "30.10.3",
)


STAGE30_10_NEXT_ALLOWED_STAGE: str = "30.10.1"
STAGE30_10_NEXT_ALLOWED_STAGE_TITLE: str = (
    "fake / offline eligibility model + classifier tests (a pure tier-dip "
    "classifier + per-candidate audit-record model, proven with fakes "
    "only; no runtime wiring, no live provider call, no Discord send)"
)


# The locked substage roadmap (safe paraphrase labels). Stage 30.9.2 (the
# paused live proof) resumes only AFTER Stage 30.10 proves dip-focused
# eligibility.
STAGE30_10_SUBSTAGE_ROADMAP: Tuple[str, ...] = (
    (
        "30.10.0 -- this spec lock only (spec doc + constants-only "
        "manifest + pin test); no runtime, no classifier, no live"
    ),
    "30.10.1 -- fake / offline eligibility model + classifier tests",
    (
        "30.10.2 -- wire the OPTIONAL gate into the compact runtime path "
        "with fakes only (gate BEFORE dispatch reservation / private send)"
    ),
    "30.10.3 -- prove artifact integration, offline only",
)


# ---------------------------------------------------------------------------
# One-line purpose
# ---------------------------------------------------------------------------


STAGE30_10_PURPOSE: str = "compact tier-dip eligibility gate"


# ---------------------------------------------------------------------------
# Locked read-only audit findings
# ---------------------------------------------------------------------------
#
# The prior read-only audit found that the live compact path renders
# tier / ATH / drawdown labels but never uses them to decide whether to
# send. These findings are LOCKED so Stage 30.10 corrects exactly this gap.
# Each is a safe paraphrase / existing surface name (NOT a secret, host, or
# transport destination).


STAGE30_10_LOCKED_AUDIT_FINDINGS: Tuple[str, ...] = (
    (
        "current ping trigger is a tradeable Stage 27.6 candidate from a "
        "provider hint event"
    ),
    "map_stage27_candidate_to_stage28_6_event sets dispatch_allowed = not malformed",
    (
        "Stage28_6BoundedPrivateSessionRunner suppresses only malformed / "
        "unknown-pair / disagree-pair / USDC-observe-only / stale-price / "
        "missing-price / dedupe"
    ),
    "Stage30_3CompactBodyTransportWrapper only blocks render failure",
    "no tier / dip / ATH gate exists on the dispatch path",
    "decide_tier computes drawdown + tier bands but its output is render / display only",
    "tier_token appears in the compact body but is not used to decide whether to send",
    "migration context is trigger / filter / display context, not a dip gate",
    (
        "a live proof today would emit migrated / tradeable compact pings, "
        "many Tier Unknown / Tier Not Applicable, not true dip-filtered "
        "alerts"
    ),
    "the bot must not ping every migrated token",
    "the bot must not ping every tradeable candidate",
)


# ---------------------------------------------------------------------------
# Gate placement contract (locked)
# ---------------------------------------------------------------------------
#
# The eligibility gate is evaluated BEFORE dispatch reservation and BEFORE
# the private send. A normal non-dip skip is a clean no-send, NOT a dispatch
# failure: Stage 30.10 must NOT reuse the Stage 28.4 / Stage 30.3
# ``PAYLOAD_REFUSED`` transport-veto path for a normal non-dip skip (that
# would count suppressed non-dips as dispatch failures).


STAGE30_10_GATE_PLACEMENT: Tuple[str, ...] = (
    "gate evaluated BEFORE dispatch reservation",
    "gate evaluated BEFORE the private Discord send",
    "non-dip skip is a normal no-send, NOT a dispatch failure",
    "no transport-layer veto for a normal non-dip skip",
    "no PAYLOAD_REFUSED-style transport veto for a normal non-dip skip",
    "tier / ATH / drawdown become dispatch eligibility, not display-only",
)


# ---------------------------------------------------------------------------
# Existing reuse surfaces (by exact name)
# ---------------------------------------------------------------------------
#
# Stage 30.10 MUST reuse the existing tier / ATH / migration / market
# context and the existing Stage 28 / 29 / 30 live runner + gates. It builds
# NO new tier model, NO new provider, NO new live runner. These are existing
# production surface names (not secrets, not hosts, not transport
# destinations).


STAGE30_10_EXISTING_REUSE_SURFACES: Tuple[str, ...] = (
    "decide_tier",
    "TierDecisionRecord",
    "tier_token",
    "Stage 30.1 tier projection",
    "existing ATH context",
    "existing migration context",
    "existing MC / LP / current market context",
    "Stage 30.9 compact / artifact lane",
    "existing Stage 28 / 29 / 30 live runner / gates",
)


# ---------------------------------------------------------------------------
# Default eligibility policy stance + explicit config fields
# ---------------------------------------------------------------------------
#
# The default operator policy is fail-closed: send ONLY a compact tier-dip
# eligible candidate; suppress everything else. The policy is an EXPLICIT
# config object, never a hidden env read.


STAGE30_10_DEFAULT_POLICY_STANCE: Tuple[str, ...] = (
    "SEND if tier_token in Tier 1 / Tier 2 / Tier 3",
    "SKIP if Tier Unknown",
    "SKIP if Tier Not Applicable",
    "SKIP if missing ATH",
    "SKIP if missing migration",
    "SKIP if missing drawdown",
    "SKIP if invalid market context",
    "SKIP if current MC / price unavailable",
    "fail closed, not fail open",
)


# The explicit policy config field names (an explicit policy object, never a
# hidden env read).
STAGE30_10_POLICY_FIELDS: Tuple[str, ...] = (
    "allowed_tiers",
    "require_post_migration_ath",
    "require_migration_present",
    "require_current_market_context",
    "fail_closed_on_unknown",
)


# The locked DEFAULT policy values.
STAGE30_10_DEFAULT_ALLOWED_TIERS: Tuple[str, ...] = (
    "TIER_1",
    "TIER_2",
    "TIER_3",
)
STAGE30_10_DEFAULT_REQUIRE_POST_MIGRATION_ATH: bool = True
STAGE30_10_DEFAULT_REQUIRE_MIGRATION_PRESENT: bool = True
STAGE30_10_DEFAULT_REQUIRE_CURRENT_MARKET_CONTEXT: bool = True
STAGE30_10_DEFAULT_FAIL_CLOSED_ON_UNKNOWN: bool = True


# The Stage 30.1 ``tier_token`` display values the default policy ALLOWS
# (mirrored by value; the manifest imports no Stage 30.1 module). The
# ``allowed_tiers`` config above uses the band-name codes (``TIER_1`` /
# ``TIER_2`` / ``TIER_3``) that map to these display tokens.
STAGE30_10_ALLOWED_TIER_TOKENS: Tuple[str, ...] = (
    "Tier 1",
    "Tier 2",
    "Tier 3",
)


# The Stage 30.1 ``tier_token`` display values the default policy SUPPRESSES
# (mirrored by value).
STAGE30_10_SUPPRESSED_TIER_TOKENS: Tuple[str, ...] = (
    "Tier Unknown",
    "Tier Not Applicable",
)


# ---------------------------------------------------------------------------
# Eligibility-decision closed set
# ---------------------------------------------------------------------------
#
# Exactly one decision token per evaluated candidate. ``ELIGIBLE_DIP`` is the
# only send-allowed decision; every other token is a no-send.


STAGE30_10_ELIGIBILITY_DECISIONS: Tuple[str, ...] = (
    "ELIGIBLE_DIP",
    "SKIPPED_NOT_DIP",
    "SKIPPED_TIER_UNKNOWN",
    "SKIPPED_TIER_NOT_APPLICABLE",
    "SKIPPED_MISSING_ATH",
    "SKIPPED_MISSING_MIGRATION",
    "SKIPPED_MISSING_MARKET_CONTEXT",
    "INVALID_INPUT",
)


# The single send-allowed decision token.
STAGE30_10_SEND_ALLOWED_DECISION: str = "ELIGIBLE_DIP"


# ---------------------------------------------------------------------------
# Per-candidate eligibility audit-record fields
# ---------------------------------------------------------------------------
#
# Stage 30.10 emits one eligibility audit record per evaluated candidate.
# Each field is a safe-shape opaque id, a closed-set token, a canonical
# decimal-text value, or an ISO-8601 UTC timestamp. ``created_at_utc`` is
# explicit / caller-injected; never a wall-clock read. ``drawdown_from_ath``
# / ``drop_positive`` are OPTIONAL (present only when available). NONE is a
# secret, a raw payload, a host, or a transport destination.


STAGE30_10_AUDIT_RECORD_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "tier_token",
    "drawdown_from_ath",
    "drop_positive",
    "migration_status",
    "ath_status",
    "decision",
    "reason",
    "created_at_utc",
)


# ---------------------------------------------------------------------------
# Stage 30.9.2 relationship (paused, not abandoned)
# ---------------------------------------------------------------------------


STAGE30_10_STAGE_30_9_2_STATUS: str = "paused, not abandoned"
STAGE30_10_STAGE_30_9_2_RESUME_CONDITION: str = (
    "resume only after Stage 30.10 proves dip-focused eligibility"
)


# ---------------------------------------------------------------------------
# Failure behavior (fail-closed, locked)
# ---------------------------------------------------------------------------


STAGE30_10_FAILURE_BEHAVIOR: Tuple[str, ...] = (
    "invalid input => INVALID_INPUT, no send",
    "Tier Unknown => SKIPPED_TIER_UNKNOWN, no send",
    "Tier Not Applicable => SKIPPED_TIER_NOT_APPLICABLE, no send",
    "missing ATH => SKIPPED_MISSING_ATH, no send",
    "missing migration => SKIPPED_MISSING_MIGRATION, no send",
    "missing / invalid market context => SKIPPED_MISSING_MARKET_CONTEXT, no send",
    "in-band tier but policy-excluded => SKIPPED_NOT_DIP, no send",
    "eligible dip => ELIGIBLE_DIP, send allowed downstream",
    "fail closed on any unknown / missing input, never fail open",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.10 family (and the Stage 30.10.0 spec-lock
# slice) must not touch. Plain documentation words (family / feature names),
# NOT secret / host / transport needle forms.


STAGE30_10_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "new live runner",
    "new provider",
    "new readiness gate",
    "direct Stage 28 suppression-logic edit",
    "transport-layer veto for non-dip skip",
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
    "live run",
    "provider call",
    "Discord send",
    "env read",
    "existing live runner edit",
    "existing orchestrator edit",
    "existing transport edit",
    "Stage 25/27/28/29 production import",
    "commit",
    "tag",
    "push",
    "Stage 30.10.1+ implementation file",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Forbidden runtime imports (documentation tuple)
# ---------------------------------------------------------------------------
#
# The Stage 30.10.0 pin test walks the actual import lines of the Stage
# 30.10.0 Python files (this manifest + the pin test) and asserts none
# resolve to a module covered by this policy. The strings below are plain
# (the line-based scan never substring-matches them against source text).


STAGE30_10_FORBIDDEN_RUNTIME_IMPORTS: Tuple[str, ...] = (
    # Stdlib surfaces the Stage 30.10.0 spec-lock files must not touch.
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
    # No zstd implementation / dependency at Stage 30.10.0 (docs + tests may
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
# 30.10.0 pin test imports this tuple at runtime and scans every Stage
# 30.10.0 file (spec lock, manifest, test) case-insensitively for substring
# matches against the runtime-concatenated values. The spec doc paraphrases
# every secret / transport surface (for example "provider credential",
# "private transport destination", "transport scheme prefix") so it carries
# none of the bare needles.


STAGE30_10_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# Stage 30.10.1 -- fake / offline eligibility model + classifier slice
# ---------------------------------------------------------------------------
#
# Stage 30.10.1 lands the fake / offline eligibility model + classifier
# (proven with fakes only): a pure tier-dip classifier + per-candidate audit-
# record model. It ships ZERO runtime wiring, ZERO live provider call, ZERO
# Discord send, ZERO env read, ZERO database / SQLite, ZERO zstd /
# compression, ZERO default storage root, and edits NO Stage 28 suppression /
# Stage 30.3 / Stage 30.4 runtime orchestrator. These constants pin the
# Stage 30.10.1 inventory + import allowlists + the eligibility reason closed
# set (the decision closed set is the family ``STAGE30_10_ELIGIBILITY_DECISIONS``
# above; the Stage 30.10.1 models mirror both BY VALUE) and advance the
# slice-scoped next-allowed pointer to Stage 30.10.2. The family
# ``STAGE30_10_NEXT_ALLOWED_STAGE`` stays pinned at 30.10.1 (the slice this
# manifest's spec lock backs).


STAGE30_10_1_MINOR_VERSION: str = "30.10.1"


# The two NEW Stage 30.10.1 production modules + their import paths.
STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME: str = (
    "stage30_10_1_tier_dip_eligibility_models.py"
)
STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME: str = (
    "stage30_10_1_tier_dip_eligibility_classifier.py"
)
STAGE30_10_1_ELIGIBILITY_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_10_1_tier_dip_eligibility_models"
)
STAGE30_10_1_ELIGIBILITY_CLASSIFIER_MODULE: str = (
    "PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier"
)


# The Stage 30.10.1 production inventory (exactly the two modules above; the
# boundary scan walks these basenames).
STAGE30_10_1_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
    STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
)
STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME,
    STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME,
)


# The Stage 30.10.1 test inventory.
STAGE30_10_1_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_10_1_tier_dip_eligibility_models.py",
    "test_stage_30_10_1_tier_dip_eligibility_classifier.py",
    "test_stage_30_10_1_boundaries.py",
    "test_stage_30_10_1_manifest.py",
)


# The positive stdlib import allowlist for the Stage 30.10.1 production
# modules (the models module needs ``dataclasses`` / ``decimal`` / ``re``;
# the classifier needs ``decimal`` + the models sibling). NO ``os`` / no
# network / no database / no compression module is allowlisted.
STAGE30_10_1_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "decimal",
    "re",
)


# The positive PHX2 import allowlist: the models module imports NO PHX2
# module; the classifier imports ONLY the models sibling. No Stage 21-29 /
# Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression module is
# allowlisted.
STAGE30_10_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_10_1_ELIGIBILITY_MODELS_MODULE,
)


# The eligibility-reason closed set (mirrored BY VALUE by the Stage 30.10.1
# models module). Exactly one reason per decision; ``TIER_ALLOWED`` is the
# only reason that accompanies the send-allowed ``ELIGIBLE_DIP`` decision.
STAGE30_10_1_ELIGIBILITY_REASONS: Tuple[str, ...] = (
    "TIER_ALLOWED",
    "TIER_NOT_ALLOWED",
    "TIER_UNKNOWN",
    "TIER_NOT_APPLICABLE",
    "MISSING_ATH",
    "MISSING_MIGRATION",
    "MISSING_DRAWDOWN",
    "MISSING_MARKET_CONTEXT",
    "MISSING_CURRENT_MARKET_CAP",
    "PRE_MIGRATION_ATH_NOT_ALLOWED",
    "INVALID_CANDIDATE_ID",
    "INVALID_TOKEN_MINT",
    "INVALID_CREATED_AT_UTC",
    "INVALID_POLICY",
)


# The single send-allowed reason token (mirrors the models module BY VALUE).
STAGE30_10_1_SEND_ALLOWED_REASON: str = "TIER_ALLOWED"


# After Stage 30.10.1 lands, the next operator-authorized slice is Stage
# 30.10.2 (the OPTIONAL runtime wiring, fakes only).
STAGE30_10_1_NEXT_ALLOWED_STAGE: str = "30.10.2"
STAGE30_10_1_NEXT_ALLOWED_STAGE_TITLE: str = (
    "wire the OPTIONAL gate into the compact runtime path with fakes only "
    "(the gate is evaluated BEFORE dispatch reservation / the private send; "
    "a non-dip skip is a normal no-send, never a transport failure)"
)


# The surfaces the Stage 30.10.1 slice must not touch. Plain documentation
# words (family / feature names), NOT secret / host / transport needle forms.
STAGE30_10_1_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "live runtime wiring",
    "Stage 28 suppression-logic edit",
    "Stage 30.3 compact orchestrator edit",
    "Stage 30.4 compact orchestrator edit",
    "new live runner",
    "new provider",
    "new readiness gate",
    "transport-layer veto for non-dip skip",
    "live run",
    "live provider call",
    "Discord send",
    "env read",
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
    "Stage 30.10.2+ implementation file",
    "Stage 31",
)


__all__ = (
    # Stage id + minor version + spec version.
    "STAGE30_10_STAGE_ID",
    "STAGE30_10_0_MINOR_VERSION",
    "STAGE30_10_0_SPEC_VERSION",
    # Locked basenames + path parts + inventory delta.
    "STAGE30_10_SPEC_LOCK_FILENAME",
    "STAGE30_10_MANIFEST_BASENAME",
    "STAGE30_10_SPEC_LOCK_PATH_PARTS",
    "STAGE30_10_0_TEST_BASENAMES",
    "STAGE30_10_ALLOWED_INITIAL_FILES",
    "STAGE30_10_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_10_ALLOWED_STDLIB_IMPORTS",
    # Planned substages + next allowed stage + roadmap.
    "STAGE30_10_PLANNED_SUBSTAGES",
    "STAGE30_10_NEXT_ALLOWED_STAGE",
    "STAGE30_10_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_10_SUBSTAGE_ROADMAP",
    # Purpose.
    "STAGE30_10_PURPOSE",
    # Locked audit findings.
    "STAGE30_10_LOCKED_AUDIT_FINDINGS",
    # Gate placement.
    "STAGE30_10_GATE_PLACEMENT",
    # Existing reuse surfaces.
    "STAGE30_10_EXISTING_REUSE_SURFACES",
    # Default policy stance + explicit config fields + defaults.
    "STAGE30_10_DEFAULT_POLICY_STANCE",
    "STAGE30_10_POLICY_FIELDS",
    "STAGE30_10_DEFAULT_ALLOWED_TIERS",
    "STAGE30_10_DEFAULT_REQUIRE_POST_MIGRATION_ATH",
    "STAGE30_10_DEFAULT_REQUIRE_MIGRATION_PRESENT",
    "STAGE30_10_DEFAULT_REQUIRE_CURRENT_MARKET_CONTEXT",
    "STAGE30_10_DEFAULT_FAIL_CLOSED_ON_UNKNOWN",
    "STAGE30_10_ALLOWED_TIER_TOKENS",
    "STAGE30_10_SUPPRESSED_TIER_TOKENS",
    # Eligibility decisions + send-allowed token.
    "STAGE30_10_ELIGIBILITY_DECISIONS",
    "STAGE30_10_SEND_ALLOWED_DECISION",
    # Per-candidate audit-record fields.
    "STAGE30_10_AUDIT_RECORD_FIELDS",
    # Stage 30.9.2 relationship.
    "STAGE30_10_STAGE_30_9_2_STATUS",
    "STAGE30_10_STAGE_30_9_2_RESUME_CONDITION",
    # Failure behavior.
    "STAGE30_10_FAILURE_BEHAVIOR",
    # Forbidden surfaces.
    "STAGE30_10_FORBIDDEN_SURFACES",
    # Forbidden imports + needles.
    "STAGE30_10_FORBIDDEN_RUNTIME_IMPORTS",
    "STAGE30_10_FORBIDDEN_TEXT_NEEDLES",
    # Stage 30.10.1 fake / offline eligibility model + classifier slice.
    "STAGE30_10_1_MINOR_VERSION",
    "STAGE30_10_1_ELIGIBILITY_MODELS_BASENAME",
    "STAGE30_10_1_ELIGIBILITY_CLASSIFIER_BASENAME",
    "STAGE30_10_1_ELIGIBILITY_MODELS_MODULE",
    "STAGE30_10_1_ELIGIBILITY_CLASSIFIER_MODULE",
    "STAGE30_10_1_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_10_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_10_1_TEST_BASENAMES",
    "STAGE30_10_1_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_10_1_ALLOWED_PHX2_IMPORTS",
    "STAGE30_10_1_ELIGIBILITY_REASONS",
    "STAGE30_10_1_SEND_ALLOWED_REASON",
    "STAGE30_10_1_NEXT_ALLOWED_STAGE",
    "STAGE30_10_1_NEXT_ALLOWED_STAGE_TITLE",
    "STAGE30_10_1_FORBIDDEN_SURFACES",
)
