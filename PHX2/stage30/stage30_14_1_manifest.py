"""Stage 30.14.1 evidence-artifact loader + replay-verifier manifest.

Constants-only manifest. Pins the Build 26.1C (Stage 30.14.1) inventory (the evidence
models leaf + the read-only evidence loader + the replay verifier + this manifest), the
locked Build 26.1 capture-evidence + verify schema versions, the locked Build 26.1C caps,
the TWO-TIER stdlib import allowlists (a STRICT tier for the models leaf + the verifier; a
RELAXED LOADER tier that additionally admits ``json`` + ``pathlib`` for the one
read-only-filesystem surface), the per-module PHX2 import allowlists, the EXPLICIT
discovery-currency Stage 29.5 import allowlist (the documented Build #26 deviation -- the
loader composes the committed Stage 29.5 migration models for the record type + closed-set
tokens + safe-shape validators), the mirrored cap / schema / redaction / required-field
vocabulary, the forbidden URL / secret / transport source-text needles, the forbidden
filesystem-WRITE surfaces, the allowed read-only filesystem surfaces, the forbidden-surface
list, the test + doc basenames, and the deferred real-evidence (Build 26.1B) operator-auth
note.

Stage 30.14.1 (Build 26.1C) is the committed, OFFLINE, SYNTHETIC-fixture loader + verifier
that loads a persisted ``build26_capture_evidence.jsonl`` artifact, validates the 15-field
Build 26.1 schema, reconstructs a ``Stage29_5MigrationEvidenceRecord`` without fabrication,
and replays it through the committed Stage 30.14.0 replay -> shadow-dispatch path to a FAKE
dispatch (never a real send). It composes (never edits) the committed Stage 30.14.0
orchestrator + replay source + the committed Stage 29.5 migration models. Pointing the same
committed loader at a real, evidence-bearing Build 26.1B artifact is a SEPARATE, explicitly
operator-authorized step, BLOCKED until such a capture exists -- and requires NO code change
(the loader validates a closed-set schema and special-cases no source).

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * imports NO PHX2 module (the schema versions + cap / redaction / required-field strings
    are mirrored BY VALUE; a pin test cross-checks them against the Stage 30.14.1 models
    module + the committed Stage 29.5 / 30.13.0 / 30.14.0 sources),
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
# Stage id + minor version + schema versions + purpose
# ---------------------------------------------------------------------------


STAGE30_14_1_STAGE_ID: str = "30.14.1"
STAGE30_14_1_MINOR_VERSION: str = "30.14.1"


# The locked Build 26.1 persisted capture-evidence artifact schema version + the Stage
# 30.14.1 verify-result schema version (both mirrored BY VALUE from the Stage 30.14.1 models
# module; a pin test cross-checks they match).
BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION: str = (
    "build26_1_v0_capture_evidence"
)
STAGE30_14_1_VERIFY_SCHEMA_VERSION: str = (
    "stage30_14_1_v0_evidence_load_replay_verify"
)


STAGE30_14_1_PURPOSE: str = (
    "offline evidence-artifact load + synthetic replay to shadow fake dispatch"
)


# ---------------------------------------------------------------------------
# Locked basenames + dotted module paths
# ---------------------------------------------------------------------------


STAGE30_14_1_MODELS_BASENAME: str = (
    "stage30_14_1_evidence_artifact_models.py"
)
STAGE30_14_1_LOADER_BASENAME: str = (
    "stage30_14_1_evidence_artifact_loader.py"
)
STAGE30_14_1_VERIFIER_BASENAME: str = (
    "stage30_14_1_replay_verifier.py"
)
STAGE30_14_1_MANIFEST_BASENAME: str = "stage30_14_1_manifest.py"


STAGE30_14_1_MODELS_MODULE: str = (
    "PHX2.stage30.stage30_14_1_evidence_artifact_models"
)
STAGE30_14_1_LOADER_MODULE: str = (
    "PHX2.stage30.stage30_14_1_evidence_artifact_loader"
)
STAGE30_14_1_VERIFIER_MODULE: str = (
    "PHX2.stage30.stage30_14_1_replay_verifier"
)


# ---------------------------------------------------------------------------
# Committed cross-stage modules Stage 30.14.1 composes (the documented deviation)
# ---------------------------------------------------------------------------
#
# The discovery currency (Stage 29.5): ONLY the migration models, for the record type +
# closed-set tokens + safe-shape validators the loader reconstructs against. NO Birdeye /
# Stage 27 / Stage 28 / Stage 29.1-29.4 import; the committed Stage 29.5.7 projection + WS
# adapter are reached TRANSITIVELY through the committed Stage 30.14.0 orchestrator (driven
# by the verifier), never imported by a Stage 30.14.1 file directly.


STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE: str = (
    "PHX2.stage29.stage29_5_migration_models"
)


# The committed Stage 30.14.0 shadow-dispatch orchestrator + replay source the verifier
# drives each reconstructed record through.
STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE: str = (
    "PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch"
)
STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE: str = (
    "PHX2.stage30.stage30_14_0_replay_discovery_source"
)


# The EXPLICIT discovery-currency Stage 29 import allowlist (the documented Build #26
# deviation). Exactly ONE committed Stage 29.5 module; NO Birdeye / Stage 27 / Stage 28 /
# Stage 29.1-29.4 module is admitted.
STAGE30_14_1_ALLOWED_STAGE29_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
)


# ---------------------------------------------------------------------------
# Inventory: own production files + scanned tiers + tests + docs
# ---------------------------------------------------------------------------


STAGE30_14_1_ALLOWED_STAGE30_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_BASENAME,
    STAGE30_14_1_LOADER_BASENAME,
    STAGE30_14_1_VERIFIER_BASENAME,
    STAGE30_14_1_MANIFEST_BASENAME,
)


# STRICT tier: stdlib-only (no filesystem / json / network / clock). The models leaf + the
# verifier are scanned against the strict stdlib allowlist.
STAGE30_14_1_STRICT_SCANNED_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_BASENAME,
    STAGE30_14_1_VERIFIER_BASENAME,
)


# LOADER tier: the strict allowlist PLUS ``json`` + ``pathlib`` (read-only filesystem). The
# loader is the ONLY Stage 30.14.1 production surface that touches the filesystem.
STAGE30_14_1_LOADER_SCANNED_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_1_LOADER_BASENAME,
)


# The full scanned production set (both tiers); the constants-only manifest is EXCLUDED (it
# documents the forbidden-needle / forbidden-surface family names + builds the
# forbidden-needle fragments, so scanning it against its own needles would self-collide); it
# is validated separately by the Stage 30.14.1 manifest test.
STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_BASENAME,
    STAGE30_14_1_LOADER_BASENAME,
    STAGE30_14_1_VERIFIER_BASENAME,
)


STAGE30_14_1_TEST_BASENAMES: Tuple[str, ...] = (
    "stage30_14_1_synthetic_evidence_fixtures.py",
    "test_stage_30_14_1_models.py",
    "test_stage_30_14_1_evidence_artifact_loader.py",
    "test_stage_30_14_1_replay_verifier.py",
    "test_stage_30_14_1_boundaries.py",
    "test_stage_30_14_1_manifest.py",
)


STAGE30_14_1_DOC_BASENAMES: Tuple[str, ...] = (
    "STAGE_30_14_1_EVIDENCE_ARTIFACT_LOADER_REPLAY_VERIFIER_SPEC_LOCK.md",
)


# ---------------------------------------------------------------------------
# Two-tier stdlib import allowlists
# ---------------------------------------------------------------------------
#
# STRICT: the models leaf + the verifier need ``__future__`` / ``typing`` / ``dataclasses``
# ONLY. It admits NO ``os`` (no env read), NO ``json``, NO ``pathlib``, NO clock module
# (``datetime`` / ``time``), NO ``sqlite3`` / compression / network module.


STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
)


# LOADER: the strict set PLUS ``json`` + ``pathlib`` (read-only filesystem). Still NO ``os``
# (no env read), NO clock, NO network / db / compression.
STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
    "dataclasses",
    "json",
    "pathlib",
)


# ---------------------------------------------------------------------------
# Per-module + combined PHX2 import allowlists
# ---------------------------------------------------------------------------
#
# The models leaf is a PURE leaf (no PHX2 import). The loader composes the models leaf + the
# one discovery-currency Stage 29.5 module. The verifier composes the models leaf + the
# committed Stage 30.14.0 orchestrator + the committed Stage 30.14.0 replay source. This
# positive allowlist proves, by construction, that NO Birdeye / Stage 27 / Stage 28 / Stage
# 29.1-29.4 / runtime orchestrator / transport / Discord / live-provider / durable-ledger /
# real-send-guard module is imported by any Stage 30.14.1 file.


STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = ()
STAGE30_14_1_LOADER_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_MODULE,
    STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
)
STAGE30_14_1_VERIFIER_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_MODULE,
    STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE,
    STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE,
)


STAGE30_14_1_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    STAGE30_14_1_MODELS_MODULE,
    STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE,
    STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE,
)


# ---------------------------------------------------------------------------
# Mirrored vocabulary (BY VALUE; a pin test cross-checks vs the models + committed sources)
# ---------------------------------------------------------------------------


STAGE30_14_1_DEFAULT_MAX_BYTES: int = 1_048_576
STAGE30_14_1_HARD_MAX_BYTES: int = 8_388_608
STAGE30_14_1_DEFAULT_MAX_LINES: int = 128
STAGE30_14_1_HARD_MAX_LINES: int = 4096
STAGE30_14_1_DEFAULT_MAX_ACCEPTED: int = 64
STAGE30_14_1_HARD_MAX_ACCEPTED: int = 256
STAGE30_14_1_DEFAULT_MAX_REPLAY: int = 8
STAGE30_14_1_HARD_MAX_REPLAY: int = 64


STAGE30_14_1_REDACTION_STATUSES: Tuple[str, ...] = (
    "REDACTED",
    "REDACTION_VIOLATION",
)


# The locked 15-field Build 26.1 capture-evidence schema (mirrored BY VALUE).
STAGE30_14_1_REQUIRED_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "token_mint",
    "migration_status",
    "migration_source",
    "pool_account",
    "pool_program_id",
    "quote_mint",
    "migration_event_time_utc",
    "migration_slot",
    "migration_signature",
    "source_ref",
    "observed_at_utc",
    "measurement_status",
    "redaction_status",
    "warnings",
)


# The required attestation token values (mirrored BY VALUE from the committed Stage 29.5 /
# 29.5.7 sources; a pin test cross-checks them).
STAGE30_14_1_MIGRATION_STATUS_PRESENT: str = "PRESENT"
STAGE30_14_1_MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
STAGE30_14_1_REDACTION_STATUS_SAFE: str = "SAFE"


# ---------------------------------------------------------------------------
# Forbidden source-text needles (already-lowercased; scan lowercases haystack)
# ---------------------------------------------------------------------------
#
# Every needle below is built with a split-literal concatenation so this manifest source
# text itself does NOT carry the bare needle (and carries no contiguous transport-scheme
# separator). The Stage 30.14.1 boundary test scans every scanned production module
# case-insensitively for these. The set is the URL / webhook / auth / API-key / RPC / PEM
# forms that must never appear as a literal in this slice's source; it carries NO bare
# provider name (the ``helius:sig:`` provenance form the models leaf builds is a public
# on-chain ref token, not a transport/secret needle).


STAGE30_14_1_FORBIDDEN_TEXT_NEEDLES: Tuple[str, ...] = (
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
# Filesystem surface gates (the loader tier is READ-ONLY)
# ---------------------------------------------------------------------------
#
# The loader may use ONLY the read-only filesystem surfaces below; every WRITE surface is
# forbidden in EVERY Stage 30.14.1 production module (the strict tier carries no filesystem
# surface at all).


STAGE30_14_1_ALLOWED_READONLY_FS_SURFACES: Tuple[str, ...] = (
    "Path",
    ".exists",
    ".is_file",
    ".stat",
    ".read_text",
)


STAGE30_14_1_FORBIDDEN_WRITE_SURFACES: Tuple[str, ...] = (
    ".write_text(",
    ".write_bytes(",
    ".mkdir(",
    "open(",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------


STAGE30_14_1_FORBIDDEN_SURFACES: Tuple[str, ...] = (
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
    "Stage 30.11 / 30.13 / 30.14.0 production source edit",
    "real Build 26.1B artifact copied into the repo",
    "tag",
    "push",
    "Stage 31",
)


# ---------------------------------------------------------------------------
# Deferred real-evidence (Build 26.1B) operator-auth note
# ---------------------------------------------------------------------------
#
# Stage 30.14.1 (Build 26.1C) ships the OFFLINE synthetic evidence-load + replay -> shadow
# dispatch proof ONLY. Pointing the committed loader at a real, evidence-bearing Build 26.1B
# artifact is a SEPARATE, explicitly operator-authorized step, BLOCKED until an
# evidence-preserving capture persists the redaction-safe 15-field schema -- and requires NO
# code change (the loader validates a closed-set schema and special-cases no source; a real
# HELIUS_WS-sourced artifact loads through the same path as a synthetic one). No real
# evidence is copied into the repo.


STAGE30_14_1_REAL_EVIDENCE_REPLAY_REQUIRES_OPERATOR_AUTH: bool = True
STAGE30_14_1_REAL_EVIDENCE_REPLAY_NOTE: str = (
    "Stage 30.14.1 (Build 26.1C) is the offline synthetic evidence-load + replay -> "
    "shadow-dispatch proof only; pointing the committed loader at a real evidence-bearing "
    "Build 26.1B artifact is a separate, explicitly operator-authorized step that is blocked "
    "until an evidence-preserving capture exists, and requires no code change because the "
    "loader validates a closed-set schema and special-cases no source"
)


__all__ = (
    # Stage id + versions + purpose.
    "STAGE30_14_1_STAGE_ID",
    "STAGE30_14_1_MINOR_VERSION",
    "BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION",
    "STAGE30_14_1_VERIFY_SCHEMA_VERSION",
    "STAGE30_14_1_PURPOSE",
    # Basenames.
    "STAGE30_14_1_MODELS_BASENAME",
    "STAGE30_14_1_LOADER_BASENAME",
    "STAGE30_14_1_VERIFIER_BASENAME",
    "STAGE30_14_1_MANIFEST_BASENAME",
    # Modules.
    "STAGE30_14_1_MODELS_MODULE",
    "STAGE30_14_1_LOADER_MODULE",
    "STAGE30_14_1_VERIFIER_MODULE",
    # Cross-stage composed modules.
    "STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE",
    "STAGE30_14_1_STAGE30_14_0_ORCHESTRATOR_MODULE",
    "STAGE30_14_1_STAGE30_14_0_REPLAY_SOURCE_MODULE",
    "STAGE30_14_1_ALLOWED_STAGE29_IMPORTS",
    # Inventory.
    "STAGE30_14_1_ALLOWED_STAGE30_BASENAMES",
    "STAGE30_14_1_STRICT_SCANNED_BASENAMES",
    "STAGE30_14_1_LOADER_SCANNED_BASENAMES",
    "STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_14_1_TEST_BASENAMES",
    "STAGE30_14_1_DOC_BASENAMES",
    # Import allowlists.
    "STAGE30_14_1_STRICT_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_14_1_LOADER_ALLOWED_STDLIB_IMPORTS",
    "STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS",
    "STAGE30_14_1_LOADER_ALLOWED_PHX2_IMPORTS",
    "STAGE30_14_1_VERIFIER_ALLOWED_PHX2_IMPORTS",
    "STAGE30_14_1_ALLOWED_PHX2_IMPORTS",
    # Mirrored vocabulary.
    "STAGE30_14_1_DEFAULT_MAX_BYTES",
    "STAGE30_14_1_HARD_MAX_BYTES",
    "STAGE30_14_1_DEFAULT_MAX_LINES",
    "STAGE30_14_1_HARD_MAX_LINES",
    "STAGE30_14_1_DEFAULT_MAX_ACCEPTED",
    "STAGE30_14_1_HARD_MAX_ACCEPTED",
    "STAGE30_14_1_DEFAULT_MAX_REPLAY",
    "STAGE30_14_1_HARD_MAX_REPLAY",
    "STAGE30_14_1_REDACTION_STATUSES",
    "STAGE30_14_1_REQUIRED_FIELDS",
    "STAGE30_14_1_MIGRATION_STATUS_PRESENT",
    "STAGE30_14_1_MEASUREMENT_STATUS_COMPLETE",
    "STAGE30_14_1_REDACTION_STATUS_SAFE",
    # Forbidden needles + fs surfaces + surfaces.
    "STAGE30_14_1_FORBIDDEN_TEXT_NEEDLES",
    "STAGE30_14_1_ALLOWED_READONLY_FS_SURFACES",
    "STAGE30_14_1_FORBIDDEN_WRITE_SURFACES",
    "STAGE30_14_1_FORBIDDEN_SURFACES",
    # Deferred real-evidence operator-auth note.
    "STAGE30_14_1_REAL_EVIDENCE_REPLAY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_14_1_REAL_EVIDENCE_REPLAY_NOTE",
)
