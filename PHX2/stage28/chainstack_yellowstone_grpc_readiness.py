"""Stage 28.11 Chainstack Yellowstone gRPC readiness boundary.

This module is the SINGLE Stage 28.11 surface that reads the
process environment for Stage 28.11-specific env names. Every
other Stage 28.11 module (models / decode / client / probe /
manifest) receives an explicit ``Mapping[str, str]`` projection
through this boundary or runs against an explicitly-constructed
runtime-config record.

The Stage 28.11 boundary scan asserts ``os.environ`` /
``os.getenv`` / ``os.environb`` appear only here in the Stage
28.11 production tree.

This module:

  * reads exactly four locked env names,
  * projects the env into a safe Stage 28.10 boundary config +
    a private Stage 28.11 endpoint-secret record (when the env
    is well-formed),
  * emits a closed-set readiness report carrying only safe
    length counters + closed-set status / refusal tokens,
  * never echoes the raw endpoint URL or raw x-token to any
    log, repr, dict, exception, or persisted record.

This module imports stdlib (``os`` / ``typing``) plus the Stage
28.11 models module + the Stage 28.10 models module. It does
NOT import:

  * Stage 21-27 production code,
  * ``grpc`` / ``grpcio`` / ``protobuf`` / generated stubs,
  * any network / RPC / messaging / DB / scheduler library,
  * the Stage 28.1 ``provider_neutral_readiness`` module (the
    operator decided in Q7 not to broaden Stage 28.1's locked
    env-name list for Stage 28.11; the Stage 28.11 surface is a
    parallel narrow boundary).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_READINESS_ONLY,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_READY,
    REFUSAL_REASON_ENDPOINT_MISSING,
    REFUSAL_REASON_ENDPOINT_UNSAFE,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_TIMEOUT_INVALID,
    REFUSAL_REASON_X_TOKEN_MISSING,
    REFUSAL_REASON_X_TOKEN_UNSAFE,
    STAGE28_11_REDACTION_TOKEN,
    Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    Stage28_11GrpcError,
    Stage28_11GrpcReadinessReport,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
    build_grpc_readiness_report,
    is_safe_grpc_endpoint_url,
    is_safe_grpc_x_token,
    is_safe_timeout_seconds,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    Stage28_10ChainstackYellowstoneConfig,
    build_chainstack_yellowstone_config,
)


# ---------------------------------------------------------------------------
# Locked Stage 28.11 env-name surface
# ---------------------------------------------------------------------------


ENV_NAME_GRPC_ENDPOINT: str = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT"
)
ENV_NAME_X_TOKEN: str = (
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN"
)
ENV_NAME_ALLOW_LIVE_GRPC: str = (
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC"
)
ENV_NAME_GRPC_TIMEOUT_SECONDS: str = (
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS"
)


STAGE28_11_READ_ENV_NAMES: tuple[str, ...] = (
    ENV_NAME_GRPC_ENDPOINT,
    ENV_NAME_X_TOKEN,
    ENV_NAME_ALLOW_LIVE_GRPC,
    ENV_NAME_GRPC_TIMEOUT_SECONDS,
)


# Default gRPC timeout in seconds when the env-supplied override
# is absent. Stage 28.11 mandates a bounded deadline; 30 s is
# enough for the connect-only ``Ping()`` round-trip on the
# Chainstack edge and well below the upstream Yellowstone idle
# stream timeout.
DEFAULT_GRPC_TIMEOUT_SECONDS: int = 30


# Default safe provider id label echoed when readiness reports a
# valid endpoint shape. The label MUST pass Stage 28.10
# ``is_safe_provider_label``; the operator can override at
# runtime via the Stage 28.10 builder.
DEFAULT_PROVIDER_ID_SAFE_LABEL: str = (
    "chainstack_yellowstone_grpc"
)
DEFAULT_ENDPOINT_SAFE_LABEL: str = (
    "chainstack_yellowstone_endpoint"
)
DEFAULT_MAX_EVENTS_FOR_READINESS_CONFIG: int = 1


# ---------------------------------------------------------------------------
# Env projection
# ---------------------------------------------------------------------------


def _read_env_value(
    name: str,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return the env value for ``name``, or ``None`` if not set.

    When ``env`` is provided, the projection runs against the
    caller-supplied mapping (the testing path). When ``env`` is
    ``None``, the projection reads ``os.environ`` -- this is the
    ONLY production env-read site in the Stage 28.11 tree.
    """
    if env is not None:
        value = env.get(name)
    else:
        value = os.environ.get(name)
    if value is None:
        return None
    return value


def _read_stage28_11_env_raw(
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Private: read the Stage 28.11 env-name surface into a plain
    dict containing the RAW values.

    This helper is module-private and is NEVER exported via
    ``__all__``. The raw values it returns flow only into:

      * the internal readiness validator (which projects them
        onto closed-set status / refusal-reason tokens + safe
        length counters; never echoes the raw values),
      * the private endpoint-secret constructor (which carries
        them on the secret's private slots and redacts every
        public surface).

    The Stage 28.11 redaction contract requires that no raw env
    value ever appear on a public dict, public readiness report
    field, ``repr()``, ``dataclasses.asdict()`` result, exception
    message, log line, or persisted artifact. Callers that need
    to surface env-presence information publicly MUST use the
    redaction-safe ``project_stage28_11_env_safe`` helper
    instead.
    """
    projected: dict[str, str] = {}
    for name in STAGE28_11_READ_ENV_NAMES:
        value = _read_env_value(name, env=env)
        if value is None:
            continue
        projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Redaction-safe public env projection
# ---------------------------------------------------------------------------


TIMEOUT_STATUS_DEFAULT: str = "DEFAULT"
TIMEOUT_STATUS_OVERRIDE: str = "OVERRIDE"
TIMEOUT_STATUS_INVALID: str = "INVALID"


TIMEOUT_STATUS_VALUES: tuple[str, ...] = (
    TIMEOUT_STATUS_DEFAULT,
    TIMEOUT_STATUS_OVERRIDE,
    TIMEOUT_STATUS_INVALID,
)


@dataclass(frozen=True)
class Stage28_11SafeEnvProjection:
    """Immutable, redaction-safe public projection of the Stage
    28.11 env-name surface.

    Carries ONLY:

      * presence booleans for each of the four Stage 28.11 env
        names,
      * safe length counters (raw env-string lengths, capped at
        the Stage 28.11 safe-shape allowlist length; never
        characters of the values themselves),
      * the locked truthy boolean for the live-gate flag,
      * the closed-set timeout-status token.

    NEVER carries any raw endpoint URL, raw x-token, raw
    live-gate string, or raw timeout-override string. Safe to
    log, persist, repr, asdict, or include in a redacted public
    artifact.
    """

    endpoint_present: bool
    x_token_present: bool
    live_flag_present: bool
    timeout_present: bool
    endpoint_length: int
    x_token_length: int
    live_flag_value_is_allow: bool
    timeout_status: str


def project_stage28_11_env_safe(
    env: Optional[Mapping[str, str]] = None,
) -> Stage28_11SafeEnvProjection:
    """Public, redaction-safe projection of the Stage 28.11 env
    surface.

    Returns a ``Stage28_11SafeEnvProjection`` carrying only
    presence booleans + safe length counters + the locked
    truthy bool for the live-gate flag + the closed-set
    timeout-status token. NEVER echoes a raw endpoint URL, raw
    x-token, raw live-gate string, or raw timeout-override
    string.

    Pure with respect to a caller-supplied ``env``: when ``env``
    is supplied, only that mapping is consulted. When ``env`` is
    ``None``, the function reads ``os.environ`` (the production
    path).
    """
    raw = _read_stage28_11_env_raw(env=env)
    endpoint_raw = raw.get(ENV_NAME_GRPC_ENDPOINT)
    x_token_raw = raw.get(ENV_NAME_X_TOKEN)
    live_flag_raw = raw.get(ENV_NAME_ALLOW_LIVE_GRPC)
    timeout_raw = raw.get(ENV_NAME_GRPC_TIMEOUT_SECONDS)
    if timeout_raw is None:
        timeout_status = TIMEOUT_STATUS_DEFAULT
    elif _parse_timeout_seconds(timeout_raw) is None:
        timeout_status = TIMEOUT_STATUS_INVALID
    else:
        timeout_status = TIMEOUT_STATUS_OVERRIDE
    return Stage28_11SafeEnvProjection(
        endpoint_present=(
            isinstance(endpoint_raw, str) and endpoint_raw != ""
        ),
        x_token_present=(
            isinstance(x_token_raw, str) and x_token_raw != ""
        ),
        live_flag_present=live_flag_raw is not None,
        timeout_present=timeout_raw is not None,
        endpoint_length=(
            len(endpoint_raw)
            if isinstance(endpoint_raw, str)
            else 0
        ),
        x_token_length=(
            len(x_token_raw)
            if isinstance(x_token_raw, str)
            else 0
        ),
        live_flag_value_is_allow=_is_truthy_env_flag(
            live_flag_raw,
        ),
        timeout_status=timeout_status,
    )


# ---------------------------------------------------------------------------
# Readiness assessment
# ---------------------------------------------------------------------------


def _is_truthy_env_flag(value: object) -> bool:
    """Return ``True`` iff ``value`` looks like the locked truthy
    Stage 28.11 live-gate marker ``"1"`` (case-sensitive,
    deliberately narrow).

    Other truthy-looking strings (``"true"``, ``"yes"``,
    ``"on"``, ``"True"``) are rejected to keep the live gate
    explicit; the operator must set exactly ``1``.
    """
    return value == "1"


def _parse_timeout_seconds(value: object) -> Optional[int]:
    """Return the safe int timeout seconds, or ``None`` when the
    env-supplied value is unsafe.

    Returns ``DEFAULT_GRPC_TIMEOUT_SECONDS`` when the env value
    is ``None`` (the override is opt-in). Returns ``None`` when
    the env value is present but cannot be parsed as a safe int
    in ``[1, 600]`` -- the caller maps that to
    ``REFUSAL_REASON_TIMEOUT_INVALID``.
    """
    if value is None:
        return DEFAULT_GRPC_TIMEOUT_SECONDS
    if not isinstance(value, str):
        return None
    if value == "":
        return None
    if value.startswith("-") or value.startswith("+"):
        return None
    for ch in value:
        if ch not in "0123456789":
            return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if not is_safe_timeout_seconds(parsed):
        return None
    return parsed


def detect_stage28_11_grpc_readiness(
    env: Optional[Mapping[str, str]] = None,
) -> Stage28_11GrpcReadinessReport:
    """Top-level Stage 28.11 readiness entry point.

    Projects the Stage 28.11 env-name surface through the env-
    read boundary and assesses readiness. Returns a
    ``Stage28_11GrpcReadinessReport`` whose ``status`` is
    ``PROBE_STATUS_READY`` iff:

      * ``PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT`` is set to
        a safe-shape gRPC endpoint string,
      * ``PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN`` is set to a
        safe-shape Chainstack x-token string,
      * the optional ``PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS`` is
        either unset (defaults applied) OR a safe int.

    The live-gate env (``PHX2_STAGE28_11_ALLOW_LIVE_GRPC``) is
    NOT required for ``READY`` -- readiness alone is offline. The
    live-gate flag is surfaced on the report as ``live_flag_set``
    so the probe / live-test layers can gate themselves.

    Pure with respect to a caller-supplied ``env``: tests pass an
    explicit ``env`` mapping to keep the readiness layer
    deterministic. When ``env`` is ``None``, ``os.environ`` is
    consulted (the production path).
    """
    projected = _read_stage28_11_env_raw(env=env)
    endpoint_raw = projected.get(ENV_NAME_GRPC_ENDPOINT)
    x_token_raw = projected.get(ENV_NAME_X_TOKEN)
    live_flag_raw = projected.get(ENV_NAME_ALLOW_LIVE_GRPC)
    timeout_raw = projected.get(ENV_NAME_GRPC_TIMEOUT_SECONDS)

    endpoint_length = (
        len(endpoint_raw) if isinstance(endpoint_raw, str) else 0
    )
    x_token_length = (
        len(x_token_raw) if isinstance(x_token_raw, str) else 0
    )
    live_flag_set = _is_truthy_env_flag(live_flag_raw)

    timeout_seconds = _parse_timeout_seconds(timeout_raw)
    if timeout_seconds is None:
        return build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_TIMEOUT_INVALID,
            endpoint_safe_label=None,
            endpoint_length=endpoint_length,
            x_token_length=x_token_length,
            live_flag_set=live_flag_set,
            timeout_seconds=DEFAULT_GRPC_TIMEOUT_SECONDS,
        )

    if endpoint_raw is None or endpoint_raw == "":
        return build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_ENDPOINT_MISSING,
            endpoint_safe_label=None,
            endpoint_length=endpoint_length,
            x_token_length=x_token_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if not is_safe_grpc_endpoint_url(endpoint_raw):
        return build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_ENDPOINT_UNSAFE,
            endpoint_safe_label=None,
            endpoint_length=endpoint_length,
            x_token_length=x_token_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if x_token_raw is None or x_token_raw == "":
        return build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_X_TOKEN_MISSING,
            endpoint_safe_label=None,
            endpoint_length=endpoint_length,
            x_token_length=x_token_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if not is_safe_grpc_x_token(x_token_raw):
        return build_grpc_readiness_report(
            status=PROBE_STATUS_NOT_READY,
            refusal_reason=REFUSAL_REASON_X_TOKEN_UNSAFE,
            endpoint_safe_label=None,
            endpoint_length=endpoint_length,
            x_token_length=x_token_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )

    return build_grpc_readiness_report(
        status=PROBE_STATUS_READY,
        refusal_reason=REFUSAL_REASON_NONE,
        endpoint_safe_label=DEFAULT_ENDPOINT_SAFE_LABEL,
        endpoint_length=endpoint_length,
        x_token_length=x_token_length,
        live_flag_set=live_flag_set,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Endpoint-secret / runtime-config construction from env
# ---------------------------------------------------------------------------


class Stage28_11ReadinessEnvError(Stage28_11GrpcError):
    """Raised when the env-driven secret / runtime-config build
    refuses because the env did not pass readiness.

    The constructor carries the closed-set
    ``REFUSAL_REASON_*`` token from the readiness report; never
    the raw endpoint URL or raw x-token.
    """

    def __init__(self, refusal_reason: str) -> None:
        self.refusal_reason: str = refusal_reason
        super().__init__(
            f"Stage 28.11 readiness refused secret build: "
            f"refusal_reason={refusal_reason!r}"
        )


def build_endpoint_secret_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> Stage28_11ChainstackYellowstoneGrpcEndpointSecret:
    """Read the Stage 28.11 env names and construct a private
    endpoint-secret record.

    Raises ``Stage28_11ReadinessEnvError`` (carrying the
    closed-set refusal-reason token) when the env did not pass
    readiness. The raw endpoint URL and raw x-token never appear
    on the exception object's attributes.

    When ``env`` is ``None`` the function reads ``os.environ``
    (the production path); tests pass an explicit ``env`` to
    keep the helper deterministic.
    """
    report = detect_stage28_11_grpc_readiness(env=env)
    if report.status != PROBE_STATUS_READY:
        raise Stage28_11ReadinessEnvError(
            refusal_reason=report.refusal_reason,
        )
    projected = _read_stage28_11_env_raw(env=env)
    endpoint_raw = projected.get(ENV_NAME_GRPC_ENDPOINT)
    x_token_raw = projected.get(ENV_NAME_X_TOKEN)
    # The readiness check above ensures both values are present
    # and safe-shape; the strings are kept local to this function
    # and immediately wrapped in the private secret record.
    return build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=endpoint_raw,
        x_token=x_token_raw,
        tls=True,
    )


def build_runtime_config_from_env(
    *,
    mode: str,
    env: Optional[Mapping[str, str]] = None,
    provider_id: str = DEFAULT_PROVIDER_ID_SAFE_LABEL,
    endpoint_safe_label: str = DEFAULT_ENDPOINT_SAFE_LABEL,
    max_events: int = DEFAULT_MAX_EVENTS_FOR_READINESS_CONFIG,
) -> Stage28_11ChainstackYellowstoneGrpcRuntimeConfig:
    """Read the Stage 28.11 env names and construct a runtime-
    config record paired with the Stage 28.10 safe boundary
    config.

    Raises ``Stage28_11ReadinessEnvError`` (carrying the closed-
    set refusal-reason token) when the env did not pass
    readiness.

    The returned record is safe to log via its redacted
    ``__repr__`` -- the raw endpoint URL and raw x-token live
    only on the private secret subobject.
    """
    secret = build_endpoint_secret_from_env(env=env)
    report = detect_stage28_11_grpc_readiness(env=env)
    safe_config: Stage28_10ChainstackYellowstoneConfig = (
        build_chainstack_yellowstone_config(
            provider_id=provider_id,
            endpoint_safe_label=endpoint_safe_label,
            auth_mode=AUTH_MODE_XTOKEN,
            max_events=max_events,
            provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
            chain=CHAIN_SOLANA,
        )
    )
    return build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=safe_config,
        endpoint_secret=secret,
        mode=mode,
        timeout_seconds=report.timeout_seconds,
    )


__all__ = (
    "ENV_NAME_GRPC_ENDPOINT",
    "ENV_NAME_X_TOKEN",
    "ENV_NAME_ALLOW_LIVE_GRPC",
    "ENV_NAME_GRPC_TIMEOUT_SECONDS",
    "STAGE28_11_READ_ENV_NAMES",
    "DEFAULT_GRPC_TIMEOUT_SECONDS",
    "DEFAULT_PROVIDER_ID_SAFE_LABEL",
    "DEFAULT_ENDPOINT_SAFE_LABEL",
    "DEFAULT_MAX_EVENTS_FOR_READINESS_CONFIG",
    "TIMEOUT_STATUS_DEFAULT",
    "TIMEOUT_STATUS_OVERRIDE",
    "TIMEOUT_STATUS_INVALID",
    "TIMEOUT_STATUS_VALUES",
    "Stage28_11SafeEnvProjection",
    "project_stage28_11_env_safe",
    "detect_stage28_11_grpc_readiness",
    "build_endpoint_secret_from_env",
    "build_runtime_config_from_env",
    "Stage28_11ReadinessEnvError",
)
