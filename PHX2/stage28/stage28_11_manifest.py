"""Stage 28.11 Chainstack Yellowstone gRPC client manifest.

Stage 28.11 is a post-Stage-28-closure, post-Stage-28.10 narrow
amendment that ships the FIRST Stage 28 production class which
opens a real Chainstack Yellowstone gRPC channel. Stage 28.11
satisfies the Stage 28.10
``Stage28_10ChainstackYellowstoneClient`` Protocol so the
existing Stage 28.10 event source / hint-aware candidate
assembler chain CAN later (in Stage 28.12, under separate
operator authorization) drain real provider-backed events
through the same Protocol the Stage 28.10 fake client already
satisfies.

Stage 28.11 ships:

  * the redaction-safe private endpoint-secret record + the
    runtime-config record that pairs the Stage 28.10 safe
    boundary config with the secret + Stage 28.11 mode /
    timeout axes,
  * the closed-set Stage 28.11 mode / probe-status / refusal-
    reason vocabularies,
  * the Stage 28.11 readiness boundary (the SINGLE Stage
    28.11 surface that reads ``os.environ``),
  * the Stage 28.11 decoder (Yellowstone protobuf ->
    Stage 28.10 payload),
  * the Stage 28.11 real gRPC client that satisfies the
    Stage 28.10 Protocol,
  * the Stage 28.11 probe orchestrator that drives the three
    locked modes (readiness-only, provider-connect-only,
    one-event decode dry run),
  * the operator runbook, this manifest, the Stage-28.11-scoped
    dependency-pin file, and the vendored proto sources + the
    generated Python stubs.

Stage 28.11 ships NO real Discord send, NO Stage 28.9 wrapper
invocation, NO dispatch, NO Stage 29 enforcement, NO public
routing, NO subscriber routing, NO paid tier routing, NO
Telegram, NO X / social, NO automated trading, NO wallet /
private-key / signer logic, NO position sizing, NO trade
execution, NO dashboard / HTTP control server, NO daemon /
systemd / watchdog / autorestart service.

This manifest module is constants-only:

  * imports only stdlib (``typing``) plus the Stage 28.11
    models + readiness + decode + client + probe modules,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from PHX2.stage28.chainstack_yellowstone_grpc_client import (
    GRPC_METADATA_KEY_X_TOKEN as _CLIENT_METADATA_KEY_X_TOKEN,
    Stage28_11ChainstackYellowstoneGrpcClient as _CLIENT_TYPE,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    STAGE28_11_DEFAULT_EVENT_TYPE as _DECODE_DEFAULT_EVENT_TYPE,
    STAGE28_11_DEFAULT_INSTRUCTION_KIND as _DECODE_DEFAULT_INSTRUCTION_KIND,
    STAGE28_11_PLACEHOLDER_MINT as _DECODE_PLACEHOLDER_MINT,
    STAGE28_11_PROVIDER_EVENT_ID_PREFIX as _DECODE_PROVIDER_EVENT_ID_PREFIX,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN as _MODELS_MODE_DRY_RUN,
    MODE_PROVIDER_CONNECT_ONLY as _MODELS_MODE_CONNECT_ONLY,
    MODE_READINESS_ONLY as _MODELS_MODE_READINESS_ONLY,
    MODE_VALUES as _MODELS_MODE_VALUES,
    PROBE_STATUS_VALUES as _MODELS_PROBE_STATUS_VALUES,
    REFUSAL_REASON_VALUES as _MODELS_REFUSAL_REASON_VALUES,
    STAGE28_11_MINOR_VERSION as _MODELS_MINOR_VERSION,
    STAGE28_11_REDACTION_TOKEN as _MODELS_REDACTION_TOKEN,
    STAGE28_11_SCHEMA_VERSION as _MODELS_SCHEMA_VERSION,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    ENV_NAME_ALLOW_LIVE_GRPC as _READINESS_ENV_NAME_LIVE,
    ENV_NAME_GRPC_ENDPOINT as _READINESS_ENV_NAME_ENDPOINT,
    ENV_NAME_GRPC_TIMEOUT_SECONDS as _READINESS_ENV_NAME_TIMEOUT,
    ENV_NAME_X_TOKEN as _READINESS_ENV_NAME_X_TOKEN,
    STAGE28_11_READ_ENV_NAMES as _READINESS_READ_ENV_NAMES,
)


# ---------------------------------------------------------------------------
# Stage 28.11 version axes
# ---------------------------------------------------------------------------


STAGE28_11_MINOR_VERSION: str = _MODELS_MINOR_VERSION
STAGE28_11_SCHEMA_VERSION: str = _MODELS_SCHEMA_VERSION
STAGE28_11_REDACTION_TOKEN: str = _MODELS_REDACTION_TOKEN


# ---------------------------------------------------------------------------
# Locked Stage 28.11 source-file basename inventory
# ---------------------------------------------------------------------------


STAGE28_11_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_grpc_models.py",
    "chainstack_yellowstone_grpc_readiness.py",
    "chainstack_yellowstone_grpc_decode.py",
    "chainstack_yellowstone_grpc_client.py",
    "chainstack_yellowstone_grpc_probe.py",
    "stage28_11_manifest.py",
)


STAGE28_11_DEPENDENCY_BASENAMES: tuple[str, ...] = (
    "stage28_11_requirements.txt",
)


STAGE28_11_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_11_CHAINSTACK_GRPC_RUNBOOK.md",
)


STAGE28_11_TEST_BASENAMES: tuple[str, ...] = (
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_models.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_readiness.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_decode.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_client.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_probe.py"
    ),
    "test_stage_28_11_runbook.py",
    "test_stage_28_11_boundaries.py",
)


# Stage 28.11 admits the generated Yellowstone protobuf imports
# (``grpc`` / generated stubs) ONLY in the client / decode /
# probe modules. The models / readiness modules must remain
# stdlib + Stage 28.10/Stage 28.11 sibling imports only. The
# Stage 28.11 boundary scan pins this list.
STAGE28_11_GRPC_IMPORT_ADMITTED_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_grpc_client.py",
    "chainstack_yellowstone_grpc_decode.py",
)


# Stage 28.11 admits ``os.environ`` reads ONLY in the readiness
# module. Every other Stage 28.11 production module must NOT
# read the env directly.
STAGE28_11_ENV_READ_ADMITTED_BASENAME: str = (
    "chainstack_yellowstone_grpc_readiness.py"
)


# Locked vendored-proto source path and generated-stub path.
# Tests pin these strings so a downstream consumer can locate
# the proto + stub surface from this manifest.
STAGE28_11_VENDORED_PROTO_SOURCE_PATH: str = (
    "PHX2/proto/stage28_11/source"
)
STAGE28_11_GENERATED_STUB_PATH: str = (
    "PHX2/proto/stage28_11/_generated"
)


# Locked vendored proto source pin. Stage 28.11 vendored
# exactly these two proto files from the upstream rpcpool /
# Triton One Yellowstone gRPC repository at the tag below.
STAGE28_11_VENDORED_PROTO_REPO: str = (
    "rpcpool/yellowstone-grpc"
)
STAGE28_11_VENDORED_PROTO_TAG: str = "v13.1.0+solana.4.0.0"
STAGE28_11_VENDORED_PROTO_COMMIT_SHA: str = (
    "62893fb7644b1ceafd2f8d840f8e3997f44a483f"
)
STAGE28_11_VENDORED_PROTO_FILES: tuple[str, ...] = (
    "geyser.proto",
    "solana-storage.proto",
)


# Locked pinned dependency versions for the Stage 28.11 gRPC
# client path. These pins live in
# ``PHX2/stage28/stage28_11_requirements.txt`` (Stage-28.11-
# scoped); the rest of the PHX2 tree remains stdlib-only.
STAGE28_11_PINNED_DEPENDENCIES: tuple[
    tuple[str, str], ...
] = (
    ("grpcio", "1.66.2"),
    ("grpcio-tools", "1.66.2"),
    ("protobuf", "5.28.3"),
)


# ---------------------------------------------------------------------------
# Locked Stage 28.11 closed-set vocabularies re-exported for
# pinning
# ---------------------------------------------------------------------------


STAGE28_11_MODE_READINESS_ONLY: str = (
    _MODELS_MODE_READINESS_ONLY
)
STAGE28_11_MODE_PROVIDER_CONNECT_ONLY: str = (
    _MODELS_MODE_CONNECT_ONLY
)
STAGE28_11_MODE_ONE_EVENT_DECODE_DRY_RUN: str = (
    _MODELS_MODE_DRY_RUN
)
STAGE28_11_MODE_VALUES: tuple[str, ...] = tuple(
    _MODELS_MODE_VALUES
)
STAGE28_11_PROBE_STATUS_VALUES: tuple[str, ...] = tuple(
    _MODELS_PROBE_STATUS_VALUES
)
STAGE28_11_REFUSAL_REASON_VALUES: tuple[str, ...] = tuple(
    _MODELS_REFUSAL_REASON_VALUES
)


STAGE28_11_ENV_NAME_GRPC_ENDPOINT: str = (
    _READINESS_ENV_NAME_ENDPOINT
)
STAGE28_11_ENV_NAME_X_TOKEN: str = (
    _READINESS_ENV_NAME_X_TOKEN
)
STAGE28_11_ENV_NAME_ALLOW_LIVE_GRPC: str = (
    _READINESS_ENV_NAME_LIVE
)
STAGE28_11_ENV_NAME_GRPC_TIMEOUT_SECONDS: str = (
    _READINESS_ENV_NAME_TIMEOUT
)
STAGE28_11_READ_ENV_NAMES: tuple[str, ...] = tuple(
    _READINESS_READ_ENV_NAMES
)


STAGE28_11_GRPC_METADATA_KEY_X_TOKEN: str = (
    _CLIENT_METADATA_KEY_X_TOKEN
)


STAGE28_11_DECODE_PLACEHOLDER_MINT: str = (
    _DECODE_PLACEHOLDER_MINT
)
STAGE28_11_DECODE_PROVIDER_EVENT_ID_PREFIX: str = (
    _DECODE_PROVIDER_EVENT_ID_PREFIX
)
STAGE28_11_DECODE_DEFAULT_EVENT_TYPE: str = (
    _DECODE_DEFAULT_EVENT_TYPE
)
STAGE28_11_DECODE_DEFAULT_INSTRUCTION_KIND: str = (
    _DECODE_DEFAULT_INSTRUCTION_KIND
)


# ---------------------------------------------------------------------------
# Stage 28.11 scope locks
# ---------------------------------------------------------------------------


STAGE28_11_SCOPE_LOCKS: tuple[str, ...] = (
    "Chainstack Yellowstone real gRPC client scope",
    "first PHX2 substage that opens a real provider connection",
    "satisfies the Stage 28.10 client Protocol",
    "three explicit modes only: readiness-only, connect-only, one-event decode dry run",
    "no Stage 28.9 wrapper invocation",
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
    "env reads admitted in chainstack_yellowstone_grpc_readiness.py only",
    "grpc / protobuf imports admitted in client + decode modules only",
    "no sleep / no scheduling / no backoff execution",
    "TLS mandatory; plaintext gRPC refused at construction",
    "x-token auth only; username/password refused in this substage",
    "every gRPC call carries a finite deadline",
    "raw endpoint URL / x-token NEVER appear on any public record / repr / log / artifact",
    "live live-flag env required for non-readiness modes",
    "live tests skipped by default; opt-in via PHX2_STAGE28_11_ALLOW_LIVE_GRPC=1",
    "real pings still require fresh price context (Stage 27.4)",
    "missing or stale price suppresses via existing Stage 27 / Stage 28.6 rules",
    "UNKNOWN / DISAGREE / USDC observe-only suppressions remain",
    "redaction-safe records",
)


# ---------------------------------------------------------------------------
# Stage 28.11 forbidden surface re-declaration (defence in depth)
# ---------------------------------------------------------------------------


STAGE28_11_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "Stage 28.9 wrapper invocation in Stage 28.11",
    "real Discord send in Stage 28.11",
)


# ---------------------------------------------------------------------------
# Stage 28.11 module-type pins
# ---------------------------------------------------------------------------


STAGE28_11_CLIENT_TYPE = _CLIENT_TYPE


__all__ = (
    # Version axes.
    "STAGE28_11_MINOR_VERSION",
    "STAGE28_11_SCHEMA_VERSION",
    "STAGE28_11_REDACTION_TOKEN",
    # Inventories.
    "STAGE28_11_PRODUCTION_PY_BASENAMES",
    "STAGE28_11_DEPENDENCY_BASENAMES",
    "STAGE28_11_DOC_BASENAMES",
    "STAGE28_11_TEST_BASENAMES",
    "STAGE28_11_GRPC_IMPORT_ADMITTED_BASENAMES",
    "STAGE28_11_ENV_READ_ADMITTED_BASENAME",
    # Vendored proto pins.
    "STAGE28_11_VENDORED_PROTO_REPO",
    "STAGE28_11_VENDORED_PROTO_TAG",
    "STAGE28_11_VENDORED_PROTO_COMMIT_SHA",
    "STAGE28_11_VENDORED_PROTO_FILES",
    "STAGE28_11_VENDORED_PROTO_SOURCE_PATH",
    "STAGE28_11_GENERATED_STUB_PATH",
    "STAGE28_11_PINNED_DEPENDENCIES",
    # Mode + status + refusal vocabularies.
    "STAGE28_11_MODE_READINESS_ONLY",
    "STAGE28_11_MODE_PROVIDER_CONNECT_ONLY",
    "STAGE28_11_MODE_ONE_EVENT_DECODE_DRY_RUN",
    "STAGE28_11_MODE_VALUES",
    "STAGE28_11_PROBE_STATUS_VALUES",
    "STAGE28_11_REFUSAL_REASON_VALUES",
    # Env-name surface.
    "STAGE28_11_ENV_NAME_GRPC_ENDPOINT",
    "STAGE28_11_ENV_NAME_X_TOKEN",
    "STAGE28_11_ENV_NAME_ALLOW_LIVE_GRPC",
    "STAGE28_11_ENV_NAME_GRPC_TIMEOUT_SECONDS",
    "STAGE28_11_READ_ENV_NAMES",
    # gRPC metadata key.
    "STAGE28_11_GRPC_METADATA_KEY_X_TOKEN",
    # Decode pins.
    "STAGE28_11_DECODE_PLACEHOLDER_MINT",
    "STAGE28_11_DECODE_PROVIDER_EVENT_ID_PREFIX",
    "STAGE28_11_DECODE_DEFAULT_EVENT_TYPE",
    "STAGE28_11_DECODE_DEFAULT_INSTRUCTION_KIND",
    # Scope locks + forbidden surfaces.
    "STAGE28_11_SCOPE_LOCKS",
    "STAGE28_11_FORBIDDEN_SURFACES",
    # Module-type pins.
    "STAGE28_11_CLIENT_TYPE",
)
