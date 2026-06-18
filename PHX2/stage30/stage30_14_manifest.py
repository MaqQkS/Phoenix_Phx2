"""Stage 30.14 real-discovery-replay -> shadow-dispatch manifest.

Constants-only manifest. Pins the Build #26 (Stage 30.14) inventory (the replay-discovery
models + replay source + the shadow-dispatch orchestrator + this manifest), the locked
schema version, the locked Build 26.0 caps, the stdlib + PHX2 import allowlists, the
EXPLICIT discovery-currency Stage 29.5 import allowlist (the documented Build #26 deviation
-- Stage 30.14 composes the committed Stage 29.5 migration-models closed-set capture error
so its replay source can fail closed exactly as a degraded real capture would), the
mirrored cap / schema / redaction vocabulary, the forbidden URL / secret / transport
source-text needles the Stage 30.14 boundary scan checks the production source against, the
forbidden-surface list, and the deferred real-evidence (Build 26.1) operator-auth note.

Stage 30.14 (Build 26.0) is the committed, OFFLINE, SYNTHETIC proof that an
already-discovered migration evidence record -- REPLAYED from memory, never a live capture
-- flows through the committed Stage 30.13.0 auto-seeder + the committed Stage 30.11.23 ->
30.11.22 recheck / fake-send chain to a RECORDED would-send (a FAKE dispatch), never a real
send. It composes (never edits) those committed modules. It is NOT wired into any real send
path; pointing the same committed replay seam at a real, evidence-bearing artifact (Build
26.1) is a SEPARATE step, BLOCKED until an evidence-preserving capture exists.

The Stage 30.14 import allowlist DELIBERATELY DEVIATES from the leaf "no Stage 21-29 import"
rule for exactly ONE committed Stage 29.5 module (the migration models -- for the
closed-set ``Stage29_5MigrationEvidenceError`` the replay source raises in its fail-closed
mode). NO Birdeye / Stage 27 / Stage 28 / Stage 29.1-29.4 import is admitted; the committed
Stage 29.5 record type + projection + WS adapter are reached TRANSITIVELY through the
committed Stage 30.13.0 auto-seeder, never imported by a Stage 30.14 file directly.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * imports NO PHX2 module (the schema version + cap / redaction strings are mirrored BY
    VALUE; a pin test cross-checks them against the Stage 30.14.0 models module),
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


STAGE30_14_STAGE_ID: str = "30.14"
STAGE30_14_MINOR_VERSION: str = "30.14"


# The Stage 30.14.0 shadow-dispatch schema version (mirrored BY VALUE from the Stage
# 30.14.0 models module; a pin test cross-checks it matches).
STAGE30_14_0_SCHEMA_VERSION: str = (
    "stage30_14_0_v0_real_discovery_replay_shadow_dispatch"
)


STAGE30_14_PURPOSE: str = (
    "synthetic real-discovery replay to shadow fake dispatch"
)


# ---------------------------------------------------------------------------
# Locked basenames + dotted module paths
# ---------------------------------------------------------------------------


STAGE30_14_0_MODELS_BASENAME: str = (
    "stage30_14_0_replay_discovery_models.py"
)
STAGE30_14_0_REPLAY_SOURCE_BASENAME: str = (
    "stage30_14_0_replay_discovery_source.py"
)
STAGE30_14_0_ORCHESTRATOR_BASENAME: str = (
    "stage30_14_0_real_discovery_to_shadow_dispatch.py"
)
STAGE30_14_MANIFEST_BASENAME: str = "stage30_14_manifest.py"


STAGE30_14_0_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_14_0_replay_discovery_models"
)
STAGE30_14_0_REPLAY_SOURCE_MODULE: str = (
    "PHX2.stage30.stage30_14_0_replay_discovery_source"
)
STAGE30_14_0_ORCHESTRATOR_MODULE: str = (
    "PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch"
)


# ---------------------------------------------------------------------------
# Committed cross-stage modules Stage 30.14 composes (the documented deviation)
# ---------------------------------------------------------------------------
#
# The discovery currency (Stage 29.5): ONLY the migration models, for the closed-set
# ``Stage29_5MigrationEvidenceError`` the replay source raises in fail-closed mode. The
# committed Stage 29.5 record type + Stage 29.5.7 projection + Helius WS adapter are reached
# TRANSITIVELY through the committed Stage 30.13.0 auto-seeder; no Stage 30.14 file imports
# them directly.


STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE: str = (
    "PHX2.stage29.stage29_5_migration_models"
)


# The committed Stage 30.13.0 auto-seeder the orchestrator drives over the replay source.
STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE: str = (
    "PHX2.stage30.stage30_13_0_ws_auto_seeder"
)


# The committed Stage 30.11.23 fake real-fed dry-run proof the orchestrator feeds the
# seeded summaries: it bridges them (the committed Stage 30.11.23 bridge) and runs the
# committed Stage 30.11.22 dry-run chain to a recording FAKE dispatch.
STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE: str = (
    "PHX2.stage30.stage30_11_23_fake_migration_evidence_candidate_bridge_proof"
)


# The EXPLICIT discovery-currency Stage 29 import allowlist (the documented Build #26
# deviation). Exactly ONE committed Stage 29.5 module; NO Birdeye / Stage 27 / Stage 28 /
# Stage 29.1-29.4 module is admitted.
STAGE30_14_ALLOWED_STAGE29_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
)


# ---------------------------------------------------------------------------
# Inventory: own production files + scanned set + tests + docs
# ---------------------------------------------------------------------------


STAGE30_14_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_0_MODELS_BASENAME,
    STAGE30_14_0_REPLAY_SOURCE_BASENAME,
    STAGE30_14_0_ORCHESTRATOR_BASENAME,
    STAGE30_14_MANIFEST_BASENAME,
)


# The production modules the Stage 30.14 boundary test scans for forbidden imports / text
# needles. The constants-only manifest is EXCLUDED (it documents the forbidden-surface
# family names + builds the forbidden-needle fragments, so scanning it against its own
# needles would self-collide); it is validated separately by the Stage 30.14 manifest test
# (import cleanliness + no transport-scheme literal + no top-level call).
STAGE30_14_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_0_MODELS_BASENAME,
    STAGE30_14_0_REPLAY_SOURCE_BASENAME,
    STAGE30_14_0_ORCHESTRATOR_BASENAME,
)


STAGE30_14_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_14_0_replay_discovery_models.py",
    "test_stage_30_14_0_replay_discovery_source.py",
    "test_stage_30_14_0_real_discovery_to_shadow_dispatch.py",
    "test_stage_30_14_boundaries.py",
    "test_stage_30_14_manifest.py",
)


STAGE30_14_DOC_BASENAMES: Tuple[str, ...] = (
    "STAGE_30_14_0_REAL_DISCOVERY_REPLAY_SHADOW_DISPATCH_SPEC_LOCK.md",
)


# ---------------------------------------------------------------------------
# Import allowlists
# ---------------------------------------------------------------------------
#
# Every non-PHX2 import in a Stage 30.14 production module must be in this stdlib allowlist
# (the models need ``dataclasses`` / ``typing``; the replay source needs ``typing``; the
# orchestrator needs ``typing``). It admits NO ``os`` (so NO env read), NO ``sqlite3``, NO
# compression, NO network module, NO clock module (``datetime`` / ``time``), NO ``decimal``
# / ``re`` / ``json``.
STAGE30_14_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# Every PHX2 import in a Stage 30.14 production module must be one of these: the OWN Stage
# 30.14 siblings, the one discovery-currency Stage 29.5 module (the documented deviation),
# the committed Stage 30.13.0 auto-seeder, and the committed Stage 30.11.23 fake proof. This
# positive allowlist proves, by construction, that NO Birdeye / Stage 27 / Stage 28 / Stage
# 29.1-29.4 / runtime orchestrator / transport / Discord / live-provider / durable-ledger /
# real-send-guard module is imported.
STAGE30_14_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_0_MODELS_MODULE,
    STAGE30_14_0_REPLAY_SOURCE_MODULE,
    STAGE30_14_0_ORCHESTRATOR_MODULE,
    STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE,
    STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE,
)


# ---------------------------------------------------------------------------
# Mirrored vocabulary (BY VALUE; a pin test cross-checks vs the models)
# ---------------------------------------------------------------------------


STAGE30_14_MAX_SEED: int = 1
STAGE30_14_MAX_RECHECKS: int = 1
STAGE30_14_MAX_FAKE_DISPATCHES: int = 1


STAGE30_14_REDACTION_STATUSES: Tuple[str, ...] = (
    "REDACTED",
    "REDACTION_VIOLATION",
)


# ---------------------------------------------------------------------------
# Forbidden source-text needles (already-lowercased; scan lowercases haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so this manifest source
# text itself does NOT carry the bare needle (and carries no contiguous transport-scheme
# separator). The Stage 30.14 boundary test scans every Stage 30.14 scanned production
# module case-insensitively for these. The set is intentionally PUNCTUATED (URL / webhook /
# auth / API-key / RPC / PEM forms) -- the things that should never appear as a literal in
# this slice's source -- and carries NO bare provider name.


STAGE30_14_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# The surfaces the Stage 30.14 slice must not touch. Plain documentation words (family /
# feature names), NOT secret / host / transport needle forms.


STAGE30_14_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "real WebSocket / socket connection",
    "real capture",
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
    "Stage 30.11 / 30.13 production source edit",
    "real Build #25 artifact copied into the repo",
    "commit",
    "tag",
    "push",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Deferred real-evidence (Build 26.1) operator-auth note
# ---------------------------------------------------------------------------
#
# Stage 30.14 (Build 26.0) ships the OFFLINE synthetic replay -> shadow-dispatch proof
# ONLY. Pointing the same committed replay seam at a real, evidence-bearing artifact (Build
# 26.1) is a SEPARATE, explicitly operator-authorized step, BLOCKED until an
# evidence-preserving capture exists: Build #25 persisted only the discovery decision ledger
# (the accepted mint + four counts), NOT the migration evidence (migration_event_time_utc /
# source_ref / slot / signature / quartet) the recheck chain requires. Build 26.0 fabricates
# none of those; it replays only what a caller injects.


STAGE30_14_REAL_EVIDENCE_REPLAY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_14_REAL_EVIDENCE_REPLAY_NOTE: str = (
    "Stage 30.14 (Build 26.0) is the offline synthetic replay -> shadow-dispatch proof "
    "only; pointing the committed replay seam at a real evidence-bearing artifact (Build "
    "26.1) is a separate, explicitly operator-authorized step that is blocked until an "
    "evidence-preserving capture exists and is not built here"
)


__all__ = (
    # Stage id + versions + purpose.
    "STAGE30_14_STAGE_ID",
    "STAGE30_14_MINOR_VERSION",
    "STAGE30_14_0_SCHEMA_VERSION",
    "STAGE30_14_PURPOSE",
    # Basenames.
    "STAGE30_14_0_MODELS_BASENAME",
    "STAGE30_14_0_REPLAY_SOURCE_BASENAME",
    "STAGE30_14_0_ORCHESTRATOR_BASENAME",
    "STAGE30_14_MANIFEST_BASENAME",
    # Modules.
    "STAGE30_14_0_MODELS_MODULE",
    "STAGE30_14_0_REPLAY_SOURCE_MODULE",
    "STAGE30_14_0_ORCHESTRATOR_MODULE",
    # Cross-stage composed modules.
    "STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE",
    "STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE",
    "STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE",
    "STAGE30_14_ALLOWED_STAGE29_IMPORTS",
    # Inventory.
    "STAGE30_14_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_14_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_14_TEST_BASENAMES",
    "STAGE30_14_DOC_BASENAMES",
    # Import allowlists.
    "STAGE30_14_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_14_ALLOWED_PHX2_IMPORTS",
    # Mirrored vocabulary.
    "STAGE30_14_MAX_SEED",
    "STAGE30_14_MAX_RECHECKS",
    "STAGE30_14_MAX_FAKE_DISPATCHES",
    "STAGE30_14_REDACTION_STATUSES",
    # Forbidden needles + surfaces.
    "STAGE30_14_FORBIDDEN_TEXT_NEEDLES",
    "STAGE30_14_FORBIDDEN_SURFACES",
    # Deferred real-evidence operator-auth note.
    "STAGE30_14_REAL_EVIDENCE_REPLAY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_14_REAL_EVIDENCE_REPLAY_NOTE",
)
