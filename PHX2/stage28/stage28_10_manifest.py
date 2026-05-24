"""Stage 28.10 Chainstack Yellowstone provider boundary manifest.

Stage 28.10 is a post-Stage-28-closure, post-Stage-28.9 narrow
amendment that adds:

  * a sanitized payload + config model the future real Chainstack
    Yellowstone gRPC client must project upstream events into,
  * a Protocol contract + deterministic fake client for unit
    tests,
  * a Stage 28.9-compatible event source that maps payloads onto
    normalized events (carrying Stage 28.10 hint attributes),
  * a hint-aware candidate assembler that forwards pair / pool /
    bonding-curve hints to the Stage 27 adapter so the Stage 27
    chain does not lose hint evidence (avoiding the all-UNKNOWN
    suppression the Stage 28.9 default assembler hits when no
    hints are passed),
  * an operator runbook + this manifest.

Stage 28.10 ships NO real provider client, NO grpc / grpcio /
protobuf imports, NO generated ``*_pb2.py`` / ``*_pb2_grpc.py``
stubs, NO real network access, NO real Discord send, NO Stage 29
enforcement, NO public routing, NO subscriber routing, NO paid
tier routing, NO Telegram, NO X / social, NO automated trading,
NO wallet / private-key / signer logic, NO position sizing, and
NO trade execution.

This manifest module exposes the locked Stage 28.10 schema axes,
production-file / doc / test basename inventories, scope locks,
forbidden surfaces, closed-set vocabularies, and field-name
inventories so downstream substages (Stage 29+, when implemented)
can pin against them without re-deriving them from the model /
contract / event-source / assembler layers.

This module is constants-only:

  * imports only stdlib (``typing``) plus the Stage 28.10 models +
    contracts + event source + candidate assembler modules,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage28.chainstack_yellowstone_candidate_assembler import (
    Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler as _ASSEMBLER_TYPE,
)
from PHX2.stage28.chainstack_yellowstone_contracts import (
    Stage28_10ChainstackYellowstoneFakeClient as _CONTRACTS_FAKE_CLIENT_TYPE,
)
from PHX2.stage28.chainstack_yellowstone_event_source import (
    Stage28_10ChainstackYellowstoneEventSource as _EVENT_SOURCE_TYPE,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_VALUES as _MODELS_AUTH_MODE_VALUES,
    BONDING_CURVE_VERSION_HINT_VALUES as _MODELS_BONDING_CURVE_VERSION_HINT_VALUES,
    CHAIN_VALUES as _MODELS_CHAIN_VALUES,
    EVENT_TYPE_VALUES as _MODELS_EVENT_TYPE_VALUES,
    INSTRUCTION_KIND_VALUES as _MODELS_INSTRUCTION_KIND_VALUES,
    PAIR_TYPE_HINT_VALUES as _MODELS_PAIR_TYPE_HINT_VALUES,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE as _MODELS_PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    PROVIDER_KIND_VALUES as _MODELS_PROVIDER_KIND_VALUES,
    QUOTE_ASSET_HINT_VALUES as _MODELS_QUOTE_ASSET_HINT_VALUES,
    REDACTION_STATUS_VALUES as _MODELS_REDACTION_STATUS_VALUES,
    SOURCE_KIND_VALUES as _MODELS_SOURCE_KIND_VALUES,
    STAGE28_10_MINOR_VERSION as _MODELS_STAGE28_10_MINOR_VERSION,
    STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS as _MODELS_NORMALIZED_EVENT_HINT_FIELDS,
    STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS as _MODELS_NORMALIZED_EVENT_REQUIRED_FIELDS,
    STAGE28_10_PAYLOAD_FIELD_NAMES as _MODELS_PAYLOAD_FIELD_NAMES,
    STAGE28_10_REDACTION_TOKEN as _MODELS_STAGE28_10_REDACTION_TOKEN,
    STAGE28_10_SCHEMA_VERSION as _MODELS_STAGE28_10_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Re-exports of the locked Stage 28.10 schema axes
# ---------------------------------------------------------------------------


STAGE28_10_MINOR_VERSION: str = _MODELS_STAGE28_10_MINOR_VERSION
STAGE28_10_SCHEMA_VERSION: str = _MODELS_STAGE28_10_SCHEMA_VERSION
STAGE28_10_REDACTION_TOKEN: str = (
    _MODELS_STAGE28_10_REDACTION_TOKEN
)


# ---------------------------------------------------------------------------
# Locked Stage 28.10 source-file basename inventories
# ---------------------------------------------------------------------------


STAGE28_10_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_models.py",
    "chainstack_yellowstone_contracts.py",
    "chainstack_yellowstone_event_source.py",
    "chainstack_yellowstone_candidate_assembler.py",
    "stage28_10_manifest.py",
)


STAGE28_10_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_10_CHAINSTACK_YELLOWSTONE_RUNBOOK.md",
)


STAGE28_10_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_10_chainstack_yellowstone_models.py",
    "test_stage_28_10_chainstack_yellowstone_contracts.py",
    "test_stage_28_10_chainstack_yellowstone_event_source.py",
    "test_stage_28_10_chainstack_yellowstone_candidate_assembler.py",
    "test_stage_28_10_runbook.py",
    "test_stage_28_10_boundaries.py",
)


# Stage 28.10 admits Stage 21 / Stage 27 imports only in the hint-
# aware candidate assembler module. Every other Stage 28.10
# production module must NOT import Stage 21-27 production code.
STAGE28_10_STAGE_21_27_BRIDGE_BASENAME: str = (
    "chainstack_yellowstone_candidate_assembler.py"
)


# ---------------------------------------------------------------------------
# Locked Stage 28.10 closed-set vocabularies re-exported for pinning
# ---------------------------------------------------------------------------


STAGE28_10_PROVIDER_KIND_CHAINSTACK_YELLOWSTONE: str = (
    _MODELS_PROVIDER_KIND_CHAINSTACK_YELLOWSTONE
)
STAGE28_10_PROVIDER_KIND_VALUES: tuple[str, ...] = tuple(
    _MODELS_PROVIDER_KIND_VALUES
)
STAGE28_10_AUTH_MODE_VALUES: tuple[str, ...] = tuple(
    _MODELS_AUTH_MODE_VALUES
)
STAGE28_10_CHAIN_VALUES: tuple[str, ...] = tuple(
    _MODELS_CHAIN_VALUES
)
STAGE28_10_SOURCE_KIND_VALUES: tuple[str, ...] = tuple(
    _MODELS_SOURCE_KIND_VALUES
)
STAGE28_10_EVENT_TYPE_VALUES: tuple[str, ...] = tuple(
    _MODELS_EVENT_TYPE_VALUES
)
STAGE28_10_INSTRUCTION_KIND_VALUES: tuple[str, ...] = tuple(
    _MODELS_INSTRUCTION_KIND_VALUES
)
STAGE28_10_QUOTE_ASSET_HINT_VALUES: tuple[str, ...] = tuple(
    _MODELS_QUOTE_ASSET_HINT_VALUES
)
STAGE28_10_PAIR_TYPE_HINT_VALUES: tuple[str, ...] = tuple(
    _MODELS_PAIR_TYPE_HINT_VALUES
)
STAGE28_10_BONDING_CURVE_VERSION_HINT_VALUES: tuple[str, ...] = (
    tuple(_MODELS_BONDING_CURVE_VERSION_HINT_VALUES)
)
STAGE28_10_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _MODELS_REDACTION_STATUS_VALUES
)


# ---------------------------------------------------------------------------
# Field-name inventories re-exported
# ---------------------------------------------------------------------------


STAGE28_10_PAYLOAD_FIELD_NAMES: tuple[str, ...] = tuple(
    _MODELS_PAYLOAD_FIELD_NAMES
)
STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    tuple(_MODELS_NORMALIZED_EVENT_REQUIRED_FIELDS)
)
STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS: tuple[str, ...] = tuple(
    _MODELS_NORMALIZED_EVENT_HINT_FIELDS
)


# ---------------------------------------------------------------------------
# Stage 28.10 scope locks
# ---------------------------------------------------------------------------


STAGE28_10_SCOPE_LOCKS: tuple[str, ...] = (
    "Chainstack Yellowstone provider boundary scope",
    "protocol + fake + models surface only",
    "no real provider client in this stage",
    "no grpc / grpcio / protobuf imports",
    "no generated pb2 / pb2_grpc stubs",
    "no real Chainstack call",
    "no real Discord send",
    "no Stage 29 enforcement",
    "no enforcement gate",
    "no public routing",
    "no subscriber routing",
    "no paid tier routing",
    "no Telegram",
    "no X / social",
    "no automated trading",
    "no wallet / private-key / signer logic",
    "no position sizing",
    "no trade execution",
    "no dashboard / HTTP control server",
    "no daemon / systemd / watchdog / autorestart service",
    "no Stage 28 closure tag movement",
    "no env reads",
    "no sleep / no scheduling / no backoff execution",
    "fake / protocol tests only",
    "pair-hint-aware candidate assembly requirement",
    "Stage 21 / Stage 27 imports allowed in candidate assembler module only",
    "price must be injected via Stage 27.6 sources; never faked in production",
    "missing or stale price suppresses via existing Stage 27 / Stage 28.6 rules",
    (
        "UNKNOWN / DISAGREE / USDC observe-only suppressions remain "
        "via existing Stage 27 / Stage 28.6 rules"
    ),
    "redaction-safe records",
)


# ---------------------------------------------------------------------------
# Stage 28.10 forbidden surface re-declaration (defence in depth)
# ---------------------------------------------------------------------------


STAGE28_10_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "Stage 29 implementation",
    "enforcement",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "dashboard / HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
    "grpc / grpcio / protobuf imports",
    "generated pb2 / pb2_grpc stubs",
    "real provider network calls",
    "real Discord send",
)


# ---------------------------------------------------------------------------
# Stage 28.10 module-type pins
# ---------------------------------------------------------------------------


# The Stage 28.10 manifest deliberately re-binds the
# event-source / fake-client / hint-aware-assembler types so a
# downstream consumer can import the locked surface from the
# manifest module without reaching into the individual production
# modules.
STAGE28_10_EVENT_SOURCE_TYPE = _EVENT_SOURCE_TYPE
STAGE28_10_FAKE_CLIENT_TYPE = _CONTRACTS_FAKE_CLIENT_TYPE
STAGE28_10_HINT_AWARE_CANDIDATE_ASSEMBLER_TYPE = _ASSEMBLER_TYPE


__all__ = (
    # Version axes.
    "STAGE28_10_MINOR_VERSION",
    "STAGE28_10_SCHEMA_VERSION",
    "STAGE28_10_REDACTION_TOKEN",
    # Inventories.
    "STAGE28_10_PRODUCTION_PY_BASENAMES",
    "STAGE28_10_DOC_BASENAMES",
    "STAGE28_10_TEST_BASENAMES",
    "STAGE28_10_STAGE_21_27_BRIDGE_BASENAME",
    # Closed-set vocabularies.
    "STAGE28_10_PROVIDER_KIND_CHAINSTACK_YELLOWSTONE",
    "STAGE28_10_PROVIDER_KIND_VALUES",
    "STAGE28_10_AUTH_MODE_VALUES",
    "STAGE28_10_CHAIN_VALUES",
    "STAGE28_10_SOURCE_KIND_VALUES",
    "STAGE28_10_EVENT_TYPE_VALUES",
    "STAGE28_10_INSTRUCTION_KIND_VALUES",
    "STAGE28_10_QUOTE_ASSET_HINT_VALUES",
    "STAGE28_10_PAIR_TYPE_HINT_VALUES",
    "STAGE28_10_BONDING_CURVE_VERSION_HINT_VALUES",
    "STAGE28_10_REDACTION_STATUS_VALUES",
    # Field-name inventories.
    "STAGE28_10_PAYLOAD_FIELD_NAMES",
    "STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS",
    "STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS",
    # Scope locks + forbidden surfaces.
    "STAGE28_10_SCOPE_LOCKS",
    "STAGE28_10_FORBIDDEN_SURFACES",
    # Module-type pins.
    "STAGE28_10_EVENT_SOURCE_TYPE",
    "STAGE28_10_FAKE_CLIENT_TYPE",
    "STAGE28_10_HINT_AWARE_CANDIDATE_ASSEMBLER_TYPE",
)
