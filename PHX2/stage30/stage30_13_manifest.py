"""Stage 30.13 bounded Helius WS auto-seeding manifest.

Constants-only manifest. Pins the Stage 30.13 inventory (the auto-seed models +
auto-seeder + the per-substage fake proofs + this manifest), the locked schema
version, the stdlib + PHX2 import allowlists, the EXPLICIT discovery-currency Stage
29.5 import allowlist (the documented Build #24 deviation -- Stage 30.13 IS the
discovery front-end, so it composes the committed Stage 29.5 record type + projection +
Helius WS adapter), the mirrored seed-decision / seed-reason / pump-suffix / seed-cap
vocabulary, the forbidden URL / secret / transport source-text needles the Stage 30.13
boundary scan checks the production source against, the forbidden-surface list, and the
real-read-only-WS-capture operator-auth note for the (separate) live-capture step.

Stage 30.13 is the committed bounded Helius WS AUTO-SEEDER: it turns bounded WS
discovery output into automatically seeded candidates for the existing supervised
monitor / watchlist path, proving fresh pump-suffix migrated mints can be discovered +
seeded WITHOUT a hand-fed input, BEFORE the existing recheck / fake-send runs. It
composes (never edits) the committed Stage 29.5 discovery currency and the committed
Stage 30.11.23 -> 30.11.22 chain. It is NOT wired into any real send path; wiring a
REAL read-only Helius WS socket transport behind the committed Stage 29.5 transport
Protocol (and running the controlled capped private send) is a SEPARATE, explicitly
operator-authorized step Stage 30.13 does not build.

The Stage 30.13 import allowlist DELIBERATELY DEVIATES from the leaf Stage 30.11.x /
30.12 "no Stage 21-29 import" rule: a discovery front-end MUST compose the committed
Stage 29.5 discovery currency. The deviation is SCOPED to exactly three committed Stage
29.5 modules (the migration models, the Stage 29.5.7 projection producer, and the Stage
29.5 Helius WS adapter); NO Birdeye / Stage 27 / Stage 28 / Stage 29.1-29.4 import is
admitted. Correspondingly the forbidden source-text needle set carries NO bare provider
name (so a module may import ``stage29_5_helius_ws_adapter`` by its real name and name
Helius in prose) -- the needle set is the punctuated URL / webhook / auth / key / RPC /
PEM family that should never appear as a literal in this slice's source.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * imports NO PHX2 module (the schema version + seed-decision / seed-reason / pump-
    suffix / cap strings are mirrored BY VALUE; a pin test cross-checks them against the
    Stage 30.13.0 models module),
  * reads no process environment variable,
  * opens no network connection,
  * writes no file, makes no git call, creates no tag,
  * contains no function / class definition,
  * contains no Call node (no implicit I/O at import time; the split-literal needle
    concatenations use ``+`` BinOps, never Calls),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple


# ---------------------------------------------------------------------------
# Stage id + minor version + schema version + purpose
# ---------------------------------------------------------------------------


STAGE30_13_STAGE_ID: str = "30.13"
STAGE30_13_MINOR_VERSION: str = "30.13"


# The Stage 30.13.0 auto-seed schema version (mirrored BY VALUE from the Stage 30.13.0
# models module; a pin test cross-checks it matches).
STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION: str = (
    "stage30_13_0_v0_ws_auto_seed"
)


STAGE30_13_PURPOSE: str = "bounded helius ws auto-seeding discovery"


# ---------------------------------------------------------------------------
# Locked basenames + dotted module paths
# ---------------------------------------------------------------------------


STAGE30_13_0_MODELS_BASENAME: str = (
    "stage30_13_0_ws_auto_seed_models.py"
)
STAGE30_13_0_AUTO_SEEDER_BASENAME: str = (
    "stage30_13_0_ws_auto_seeder.py"
)
STAGE30_13_1_SEED_ONLY_PROOF_BASENAME: str = (
    "stage30_13_1_fake_seed_only_proof.py"
)
STAGE30_13_2_END_TO_END_PROOF_BASENAME: str = (
    "stage30_13_2_fake_end_to_end_proof.py"
)
STAGE30_13_MANIFEST_BASENAME: str = "stage30_13_manifest.py"


STAGE30_13_0_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_13_0_ws_auto_seed_models"
)
STAGE30_13_0_AUTO_SEEDER_MODULE: str = (
    "PHX2.stage30.stage30_13_0_ws_auto_seeder"
)
STAGE30_13_1_SEED_ONLY_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_13_1_fake_seed_only_proof"
)
STAGE30_13_2_END_TO_END_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_13_2_fake_end_to_end_proof"
)


# ---------------------------------------------------------------------------
# Committed cross-stage modules Stage 30.13 composes (the documented deviation)
# ---------------------------------------------------------------------------
#
# The discovery currency (Stage 29.5): the migration record + PRESENT token + closed-set
# error live in the migration models; the PRESENT-evidence -> sanitized-summary
# projection lives in the Stage 29.5.7 producer; the Helius WS adapter (driven over a
# fake transport in the seed-only proof) lives in the Stage 29.5 adapter. These three --
# and ONLY these three -- are the admitted Stage 29 imports.


STAGE30_13_STAGE29_MIGRATION_MODELS_MODULE: str = (
    "PHX2.stage29.stage29_5_migration_models"
)
STAGE30_13_STAGE29_5_7_PRODUCER_MODULE: str = (
    "PHX2.stage29.stage29_5_7_live_migration_evidence_producer"
)
STAGE30_13_STAGE29_5_HELIUS_WS_ADAPTER_MODULE: str = (
    "PHX2.stage29.stage29_5_helius_ws_adapter"
)


# The committed Stage 30.11 chain the end-to-end proof feeds (the existing
# 30.11.23 -> 30.11.22 path; the seeded summaries are a drop-in front-end input).
STAGE30_13_STAGE30_11_23_BRIDGE_ADAPTER_MODULE: str = (
    "PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_adapter"
)
STAGE30_13_STAGE30_11_22_FAKE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof"
)


# The EXPLICIT discovery-currency Stage 29 import allowlist (the documented Build #24
# deviation). Exactly three committed Stage 29.5 modules; NO Birdeye / Stage 27 / Stage
# 28 / Stage 29.1-29.4 module is admitted.
STAGE30_13_ALLOWED_STAGE29_IMPORTS: Tuple[str, ...] = (
    STAGE30_13_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_13_STAGE29_5_7_PRODUCER_MODULE,
    STAGE30_13_STAGE29_5_HELIUS_WS_ADAPTER_MODULE,
)


# ---------------------------------------------------------------------------
# Inventory: own production files + scanned set + tests
# ---------------------------------------------------------------------------
#
# The NEW production files Stage 30.13 adds under ``PHX2/stage30/``. This GROWS per
# committed substage to reflect ONLY the files that exist at each commit: 30.13.0 adds
# the models + auto-seeder + this manifest; 30.13.1 adds the seed-only proof; 30.13.2
# adds the end-to-end proof; 30.13.3 is docs-only. (The import allowlists below are the
# stage's full intended ceiling and are declared upfront; the inventory + scanned sets
# grow as files land so the existence + scan tests stay green at every substage.)


STAGE30_13_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_13_0_MODELS_BASENAME,
    STAGE30_13_0_AUTO_SEEDER_BASENAME,
    STAGE30_13_1_SEED_ONLY_PROOF_BASENAME,
    STAGE30_13_MANIFEST_BASENAME,
)


# The production modules the Stage 30.13 boundary test scans for forbidden imports /
# text needles. The constants-only manifest is EXCLUDED (it documents the
# forbidden-surface family names + builds the forbidden-needle fragments, so scanning it
# against its own needles would self-collide); it is validated separately by the Stage
# 30.13 manifest test (import cleanliness + no transport-scheme literal + no top-level
# call). GROWS per committed substage as the proof modules land.
STAGE30_13_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_13_0_MODELS_BASENAME,
    STAGE30_13_0_AUTO_SEEDER_BASENAME,
    STAGE30_13_1_SEED_ONLY_PROOF_BASENAME,
)


STAGE30_13_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_13_0_ws_auto_seed_models.py",
    "test_stage_30_13_0_ws_auto_seeder.py",
    "test_stage_30_13_0_spec_lock.py",
    "test_stage_30_13_boundaries.py",
    "test_stage_30_13_manifest.py",
    "test_stage_30_13_1_fake_seed_only_proof.py",
    "test_stage_30_13_2_fake_end_to_end_proof.py",
    "test_stage_30_13_3_handoff_doc.py",
)


# The docs Stage 30.13 ships (spec-lock + per-substage runbooks + the deferred
# real-capture handoff). Not scanned as production .py modules; the handoff doc is
# validated by the Stage 30.13.3 doc-presence test.
STAGE30_13_DOC_BASENAMES: Tuple[str, ...] = (
    "STAGE_30_13_0_WS_AUTO_SEED_SPEC_LOCK.md",
    "STAGE_30_13_1_SEED_ONLY_RUNBOOK.md",
    "STAGE_30_13_2_END_TO_END_RUNBOOK.md",
    "STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md",
)


# ---------------------------------------------------------------------------
# Import allowlists
# ---------------------------------------------------------------------------
#
# Every non-PHX2 import in a Stage 30.13 production module must be in this stdlib
# allowlist (the models need ``dataclasses`` / ``typing``; the auto-seeder needs
# ``typing``; the proofs need ``dataclasses`` / ``typing``). It admits NO ``os`` (so NO
# env read), NO ``sqlite3``, NO compression, NO network module, NO clock module
# (``datetime`` / ``time``), NO ``decimal`` / ``re`` / ``json``.
STAGE30_13_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# Every PHX2 import in a Stage 30.13 production module must be one of these: the OWN
# Stage 30.13 siblings, the three discovery-currency Stage 29.5 modules (the documented
# deviation), and the committed Stage 30.11.23 bridge + Stage 30.11.22 fake-proof the
# end-to-end proof feeds. This positive allowlist proves, by construction, that NO
# Birdeye / Stage 27 / Stage 28 / Stage 29.1-29.4 / runtime orchestrator / transport /
# Discord / live-provider / durable-ledger module is imported.
STAGE30_13_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_13_0_MODELS_MODULE,
    STAGE30_13_0_AUTO_SEEDER_MODULE,
    STAGE30_13_1_SEED_ONLY_PROOF_MODULE,
    STAGE30_13_2_END_TO_END_PROOF_MODULE,
    STAGE30_13_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_13_STAGE29_5_7_PRODUCER_MODULE,
    STAGE30_13_STAGE29_5_HELIUS_WS_ADAPTER_MODULE,
    STAGE30_13_STAGE30_11_23_BRIDGE_ADAPTER_MODULE,
    STAGE30_13_STAGE30_11_22_FAKE_PROOF_MODULE,
)


# ---------------------------------------------------------------------------
# Mirrored seed vocabulary (BY VALUE; a pin test cross-checks vs the models)
# ---------------------------------------------------------------------------


STAGE30_13_PUMP_MINT_SUFFIX: str = "pump"
STAGE30_13_MAX_SEED_HARD_CAP: int = 10
STAGE30_13_DEFAULT_MAX_SEED: int = 10


STAGE30_13_SEED_DECISIONS: Tuple[str, ...] = (
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE",
    "ERROR",
)


STAGE30_13_SEED_REASONS: Tuple[str, ...] = (
    "SEEDED_FRESH_PUMP_MIGRATION",
    "NOT_PRESENT_MIGRATION",
    "NOT_PUMP_SUFFIX",
    "INCOMPLETE_EVIDENCE",
    "DUPLICATE_MINT",
    "WS_CAPTURE_FAILED",
    "NOT_A_RECORD",
)


STAGE30_13_REDACTION_STATUSES: Tuple[str, ...] = (
    "REDACTED",
    "REDACTION_VIOLATION",
)


# ---------------------------------------------------------------------------
# Forbidden source-text needles (already-lowercased; scan lowercases haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so this manifest
# source text itself does NOT carry the bare needle (and carries no contiguous
# transport-scheme separator). The Stage 30.13 boundary test scans every Stage 30.13
# scanned production module case-insensitively for these. The set is intentionally
# PUNCTUATED (URL / webhook / auth / API-key / RPC / PEM forms) -- the things that
# should never appear as a literal in this slice's source -- and carries NO bare
# provider name (so a module may import ``stage29_5_helius_ws_adapter`` by name and name
# Helius in prose without tripping the scan).


STAGE30_13_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# The surfaces the Stage 30.13 auto-seeder slice must not touch. Plain documentation
# words (family / feature names), NOT secret / host / transport needle forms.


STAGE30_13_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "real WebSocket / socket connection",
    "real Discord send",
    "live send",
    "approval token",
    "arm flip",
    "durable ledger read or mutation",
    "one-send ping_dedupe ledger",
    "webhook call",
    "live provider call",
    "Birdeye / provider call",
    "gRPC / Yellowstone",
    "env read",
    "wall-clock read",
    "filesystem write",
    "wallet / signing / trading",
    "public routing",
    "subscriber routing",
    "PHX2/main.py live flag edit",
    "Stage 27 production source edit",
    "Stage 28 production source edit",
    "Stage 29 production source edit",
    "Stage 30.11 runner / gate / transport edit",
    "commit",
    "tag",
    "push",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Deferred real read-only WS capture operator-auth note
# ---------------------------------------------------------------------------
#
# Stage 30.13 ships the OFFLINE auto-seeder + fakes-only proofs ONLY. Wiring a REAL
# read-only Helius WS socket transport behind the committed Stage 29.5 transport
# Protocol -- and running the controlled capped private send -- is a SEPARATE, explicitly
# operator-authorized step. The Stage 30.13.3 handoff doc specifies it; this slice does
# not build or run it.


STAGE30_13_REAL_WS_CAPTURE_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_13_REAL_WS_CAPTURE_NOTE: str = (
    "Stage 30.13 is the offline bounded WS auto-seeder + fakes-only proofs only; "
    "wiring a real read-only Helius WS socket transport behind the committed Stage "
    "29.5 transport Protocol is a separate, explicitly operator-authorized step that "
    "is not built here"
)


__all__ = (
    # Stage id + versions + purpose.
    "STAGE30_13_STAGE_ID",
    "STAGE30_13_MINOR_VERSION",
    "STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION",
    "STAGE30_13_PURPOSE",
    # Basenames.
    "STAGE30_13_0_MODELS_BASENAME",
    "STAGE30_13_0_AUTO_SEEDER_BASENAME",
    "STAGE30_13_1_SEED_ONLY_PROOF_BASENAME",
    "STAGE30_13_2_END_TO_END_PROOF_BASENAME",
    "STAGE30_13_MANIFEST_BASENAME",
    # Modules.
    "STAGE30_13_0_MODELS_MODULE",
    "STAGE30_13_0_AUTO_SEEDER_MODULE",
    "STAGE30_13_1_SEED_ONLY_PROOF_MODULE",
    "STAGE30_13_2_END_TO_END_PROOF_MODULE",
    # Cross-stage composed modules.
    "STAGE30_13_STAGE29_MIGRATION_MODELS_MODULE",
    "STAGE30_13_STAGE29_5_7_PRODUCER_MODULE",
    "STAGE30_13_STAGE29_5_HELIUS_WS_ADAPTER_MODULE",
    "STAGE30_13_STAGE30_11_23_BRIDGE_ADAPTER_MODULE",
    "STAGE30_13_STAGE30_11_22_FAKE_PROOF_MODULE",
    "STAGE30_13_ALLOWED_STAGE29_IMPORTS",
    # Inventory.
    "STAGE30_13_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_13_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_13_TEST_BASENAMES",
    "STAGE30_13_DOC_BASENAMES",
    # Import allowlists.
    "STAGE30_13_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_13_ALLOWED_PHX2_IMPORTS",
    # Mirrored vocabulary.
    "STAGE30_13_PUMP_MINT_SUFFIX",
    "STAGE30_13_MAX_SEED_HARD_CAP",
    "STAGE30_13_DEFAULT_MAX_SEED",
    "STAGE30_13_SEED_DECISIONS",
    "STAGE30_13_SEED_REASONS",
    "STAGE30_13_REDACTION_STATUSES",
    # Forbidden needles + surfaces.
    "STAGE30_13_FORBIDDEN_TEXT_NEEDLES",
    "STAGE30_13_FORBIDDEN_SURFACES",
    # Deferred real-capture operator-auth note.
    "STAGE30_13_REAL_WS_CAPTURE_REQUIRES_OPERATOR_AUTH",
    "STAGE30_13_REAL_WS_CAPTURE_NOTE",
)
