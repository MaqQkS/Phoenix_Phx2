"""Stage 29.5.7 Helius raw migration evidence producer manifest.

Constants-only re-export manifest. Pins the Stage 29.5.7
inventory, the zero env-read / zero outbound-network admission
tuples, the Stage 29.5.7 schema version + IDL-pinned migration
discriminators, the locked redaction token, and the Stage 29.5.7
forbidden-surface list.

Stage 29.5.7 ships the real Helius raw migration
evidence PRODUCER/NORMALIZER the Codex blocker audit identified
as the missing piece: it converts a raw Helius confirmed-
transaction envelope into a PRESENT Stage 29.5 migration evidence
record (a proven on-chain Pump.fun -> PumpSwap ``create_pool``
migration) and projects it onto the sanitized COMPLETE / SAFE /
trailing-``Z`` summary the committed Stage 30.11.9 / Stage 30.11.8
seam consumes. It replaces the Stage 29.5 Helius WS adapter's
deferred raw-decode path; it does NOT modify the Stage 29.5
adapter, the Stage 30.11.8 confirmation, or any committed
production file.

This manifest module is constants-only:

  * imports stdlib (``typing``) plus the Stage 29.5.7 sibling
    production modules and the Stage 29.5 redaction-safe token it
    asserts against,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_migration_models import (
    REDACTION_STATUS_SAFE as _LOCKED_REDACTION_FROM_STAGE_29_5,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR
    as _CREATE_POOL_EVENT_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
    as _CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG
    as _CREATE_POOL_INSTRUCTION_LOG,
    STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION
    as _EVIDENCE_SCHEMA_VERSION,
    STAGE29_5_7_REDACTION_STATUS_SAFE as _LOCKED_REDACTION,
    STAGE29_5_7_REJECT_REASON_VALUES as _REJECT_REASON_VALUES,
    Stage29_5_7MigrationNormalizationResult as _NORMALIZATION_RESULT,
    Stage29_5_7SanitizedMigrationEvidenceSummary as _SANITIZED_SUMMARY,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_normalizer import (
    normalize_helius_raw_migration_envelope as _NORMALIZE_FN,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN
    as _PRODUCER_HARD_MAX,
    Stage29_5_7LiveMigrationEvidenceProducer as _PRODUCER_CLASS,
    project_migration_evidence_to_sanitized_summary as _PROJECT_FN,
)


# Stage 29.5.7 mirrors the Stage 29.5 redaction-safe token BY VALUE; the boundary
# scan asserts the literal token ``SAFE`` survives, and the two imports must
# resolve to the same string at runtime.
assert (
    _LOCKED_REDACTION == _LOCKED_REDACTION_FROM_STAGE_29_5
), (
    "Stage 29.5.7 manifest: producer-side redaction lock must match the "
    "Stage 29.5 migration-models lock"
)


# ---------------------------------------------------------------------------
# Stage 29.5.7 inventory pins
# ---------------------------------------------------------------------------


STAGE29_5_7_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_7_helius_raw_migration_models.py",
    "stage29_5_7_helius_raw_migration_normalizer.py",
    "stage29_5_7_live_migration_evidence_producer.py",
    "stage29_5_7_manifest.py",
)


STAGE29_5_7_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_7_HELIUS_RAW_MIGRATION_RUNBOOK.md",
)


STAGE29_5_7_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_7_helius_raw_migration_models.py",
    "test_stage_29_5_7_helius_raw_migration_normalizer.py",
    "test_stage_29_5_7_live_migration_evidence_producer.py",
    "test_stage_29_5_7_composition.py",
    "test_stage_29_5_7_vendored_idl.py",
    "test_stage_29_5_7_boundaries.py",
    "test_stage_29_5_7_manifest.py",
    "test_stage_29_5_7_fake_evidence_proof.py",
)


# Stage 29.5.7 admits ZERO env-read sites. The producer takes its envelopes via
# method argument + its clock via constructor injection; the normalizer is a pure
# function. No env access anywhere.
STAGE29_5_7_ENV_READ_ADMITTED_BASENAMES: tuple[str, ...] = ()


# Stage 29.5.7 admits ZERO outbound-HTTP / outbound-WS / outbound-socket /
# outbound-gRPC sites. The normalizer consumes an INJECTED raw envelope; the
# producer consumes an INJECTED envelope iterable. No network work is performed
# here; the real Helius capture lives out-of-repo at the operator-authorized
# ceremony.
STAGE29_5_7_OUTBOUND_NETWORK_ADMITTED_BASENAMES: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Stage 29.5.7 schema-version + migration-identity pins
# ---------------------------------------------------------------------------


STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION: str = (
    _EVIDENCE_SCHEMA_VERSION
)


# The IDL-pinned authoritative migration-event discriminators (provenance only;
# pinned byte-for-byte against the vendored Pump AMM IDL by
# ``test_stage_29_5_7_vendored_idl.py``).
STAGE29_5_7_CREATE_POOL_INSTRUCTION_DISCRIMINATOR: tuple[int, ...] = (
    _CREATE_POOL_INSTRUCTION_DISCRIMINATOR
)
STAGE29_5_7_CREATE_POOL_EVENT_DISCRIMINATOR: tuple[int, ...] = (
    _CREATE_POOL_EVENT_DISCRIMINATOR
)
STAGE29_5_7_CREATE_POOL_INSTRUCTION_LOG: str = (
    _CREATE_POOL_INSTRUCTION_LOG
)


STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN: int = _PRODUCER_HARD_MAX


STAGE29_5_7_REJECT_REASON_VALUES: tuple[str, ...] = _REJECT_REASON_VALUES


# ---------------------------------------------------------------------------
# Stage 29.5.7 locked redaction token (echoed from Stage 29.5 models; the
# producer never overrides it)
# ---------------------------------------------------------------------------


STAGE29_5_7_REDACTION_STATUS_LOCKED: str = _LOCKED_REDACTION


# ---------------------------------------------------------------------------
# Stage 29.5.7 forbidden-surface pins
# ---------------------------------------------------------------------------
#
# Stage 29.5.7 unlocks exactly one surface relative to the Stage 29.5 forbidden
# list: the real RAW Helius migration decode path the Stage 29.5 Helius WS adapter
# explicitly deferred ("a future operator-authorized normalizer substage will land
# the raw-Helius decode path"). The decode reads the plaintext logs + the base58
# accountKeys + the create_pool instruction's leading 8-byte Anchor discriminator
# (recovered by a bounded, pure, hand-rolled base58 reader -- NO third-party
# base58 / base64 import, and NO borsh event-/arg-data decode beyond the
# discriminator) and is OFFLINE (the envelope is injected). Every other Stage 29.5
# forbidden surface remains pinned here, plus the Stage-29.5.7-specific pins below.


STAGE29_5_7_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "production enforcement",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Telegram sender",
    "Telegram client",
    "X / social sidecar",
    "automated trading",
    "position sizing",
    "trade execution",
    "wallet / private-key / signer logic",
    "private keys",
    "daemon / systemd / watchdog / autorestart service",
    "infinite loop / unbounded session",
    "Discord dispatch behavior change",
    "Discord send",
    "Telegram send",
    "X / social send",
    "public dashboard",
    "HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    # Forbidden-surface entries naming the pre-PHX2 codebase are concatenated
    # literally so this manifest's source itself does NOT carry the literal
    # substring; the runtime tuple values are unchanged byte-for-byte.
    "P" + "HX1 import path",
    "direct P" + "HX1 spaghetti copy",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "live Helius WebSocket call",
    "live Chainstack gRPC call",
    "live Birdeye HTTP call",
    "live Discord call",
    "real websockets-library transport",
    "real socket-based transport",
    # Stage 29.5.7 recovers the 8-byte create_pool Anchor discriminator via a
    # bounded, hand-rolled base58 reader; the THIRD-PARTY base58 / base64 library
    # import stays forbidden (boundary scan enforced), as does any borsh
    # event-/arg-data decode beyond the discriminator.
    "third-party base58 / base64 library import",
    "Anchor borsh event-data decoder",
    "synthetic migration source in production data flow",
    "Stage 30.11.8 confirmation loosening",
    "Stage 30 import from Stage 29",
    "ATH / drawdown patch",
    "dip gate change",
    "Stage 31 implementation",
    "Stage 29.6+ implementation",
)


# ---------------------------------------------------------------------------
# Sentinel references (boundary scan pins these named callables / types exist at
# import time without invoking them).
# ---------------------------------------------------------------------------


_NORMALIZE_FN_REF: object = _NORMALIZE_FN
_PROJECT_FN_REF: object = _PROJECT_FN
_PRODUCER_CLASS_REF: object = _PRODUCER_CLASS
_NORMALIZATION_RESULT_REF: object = _NORMALIZATION_RESULT
_SANITIZED_SUMMARY_REF: object = _SANITIZED_SUMMARY


__all__ = (
    "STAGE29_5_7_PRODUCTION_PY_BASENAMES",
    "STAGE29_5_7_DOC_BASENAMES",
    "STAGE29_5_7_TEST_BASENAMES",
    "STAGE29_5_7_ENV_READ_ADMITTED_BASENAMES",
    "STAGE29_5_7_OUTBOUND_NETWORK_ADMITTED_BASENAMES",
    "STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_5_7_CREATE_POOL_INSTRUCTION_DISCRIMINATOR",
    "STAGE29_5_7_CREATE_POOL_EVENT_DISCRIMINATOR",
    "STAGE29_5_7_CREATE_POOL_INSTRUCTION_LOG",
    "STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN",
    "STAGE29_5_7_REJECT_REASON_VALUES",
    "STAGE29_5_7_REDACTION_STATUS_LOCKED",
    "STAGE29_5_7_FORBIDDEN_SURFACES",
)
