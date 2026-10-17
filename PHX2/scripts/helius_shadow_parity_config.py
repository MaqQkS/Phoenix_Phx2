"""Canonical secret-safe configuration boundary for shadow parity only.

The Chainstack names are the production source's canonical Stage 28.11 names.
``HELIUS_GRPC_ENDPOINT`` is observed only as a legacy-presence fact: it is
never treated as a Helius endpoint and is never substituted for either
canonical Chainstack setting.  The older provider-neutral compatibility layer
continues to own any interpretation of that alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from PHX2.config.secret_env import (
    SecretEnvironment,
    load_secret_environment,
)
from PHX2.free_tier_producer.helius_source import (
    HELIUS_ENV_NAMES,
    HeliusSourceConfig,
    HeliusSourceConfigurationError,
    load_helius_source_config,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_PROVIDER_CONNECT_ONLY,
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
)
from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
    ENV_NAME_GRPC_ENDPOINT,
    ENV_NAME_GRPC_TIMEOUT_SECONDS,
    ENV_NAME_X_TOKEN,
    Stage28_11ReadinessEnvError,
    build_runtime_config_from_env,
)


LEGACY_CHAINSTACK_GRPC_ALIAS = "HELIUS_GRPC_ENDPOINT"
CHAINSTACK_SHADOW_ENV_NAMES = (
    ENV_NAME_GRPC_ENDPOINT,
    ENV_NAME_X_TOKEN,
    ENV_NAME_GRPC_TIMEOUT_SECONDS,
)
SHADOW_PARITY_ENV_NAMES = (
    *HELIUS_ENV_NAMES,
    LEGACY_CHAINSTACK_GRPC_ALIAS,
    *CHAINSTACK_SHADOW_ENV_NAMES,
)


class ShadowParityConfigurationError(ValueError):
    """A closed-set, value-free parity configuration refusal."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason)
        super().__init__(f"shadow parity configuration refused: {self.reason}")


@dataclass(frozen=True, repr=False)
class ShadowParityConfiguration:
    helius: HeliusSourceConfig
    chainstack: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig
    legacy_chainstack_alias_present: bool

    def __repr__(self) -> str:
        return (
            "ShadowParityConfiguration("
            "helius=<REDACTED_CONFIG>, "
            "chainstack=<REDACTED_CONFIG>, "
            "legacy_chainstack_alias_present="
            f"{self.legacy_chainstack_alias_present!r})"
        )

    def sanitized_presence(self) -> dict[str, str]:
        """Audit-only name-to-presence mapping; never emit to runtime logs."""

        return {
            "CHAINSTACK_ENDPOINT": "PRESENT",
            "CHAINSTACK_TOKEN": "PRESENT",
            "HELIUS_API_KEY": "PRESENT",
            "HELIUS_RPC_URL": "PRESENT",
            "HELIUS_WS_URL": "PRESENT",
            "HELIUS_GRPC_ENDPOINT": (
                "PRESENT_LEGACY_IGNORED"
                if self.legacy_chainstack_alias_present
                else "MISSING_LEGACY_IGNORED"
            ),
        }

    def sanitized_readiness(self) -> dict[str, str]:
        """Neutral, scanner-safe readiness fields for persisted/stdout use."""

        return {
            "SHADOW_AUTH_PRESENT": "true",
            "SHADOW_RPC_BASE_CONFIGURED": "true",
            "SHADOW_STREAM_BASE_CONFIGURED": "true",
            "CONTROL_SOURCE_CONFIGURED": "true",
            "CONTROL_AUTH_PRESENT": "true",
            "LEGACY_ALIAS_IGNORED": (
                "true" if self.legacy_chainstack_alias_present else "false"
            ),
        }


def _require_present(
    environment: SecretEnvironment, name: str, reason: str
) -> None:
    if environment.sanitized_presence((name,))[name] != "PRESENT":
        raise ShadowParityConfigurationError(reason)


def load_shadow_parity_configuration(
    *,
    env_path: Optional[Path],
    environ: Optional[Mapping[str, str]] = None,
    max_helius_raw_bytes: int,
) -> ShadowParityConfiguration:
    """Resolve and validate both sources before either may connect."""

    resolved = load_secret_environment(
        env_path=env_path,
        names=SHADOW_PARITY_ENV_NAMES,
        environ=environ,
    )
    _require_present(
        resolved, ENV_NAME_GRPC_ENDPOINT, "CHAINSTACK_ENDPOINT_MISSING"
    )
    _require_present(resolved, ENV_NAME_X_TOKEN, "CHAINSTACK_TOKEN_MISSING")
    for name in HELIUS_ENV_NAMES:
        _require_present(resolved, name, name + "_MISSING")

    helius_environment = resolved.select(HELIUS_ENV_NAMES)
    chainstack_environment = resolved.select(CHAINSTACK_SHADOW_ENV_NAMES)
    try:
        helius = load_helius_source_config(
            environ=helius_environment,
            max_total_raw_bytes=max_helius_raw_bytes,
        )
    except HeliusSourceConfigurationError:
        raise ShadowParityConfigurationError(
            "HELIUS_CONFIGURATION_UNSAFE"
        ) from None
    try:
        chainstack = build_runtime_config_from_env(
            mode=MODE_PROVIDER_CONNECT_ONLY,
            env=chainstack_environment,
            max_events=1,
        )
    except Stage28_11ReadinessEnvError as exc:
        raise ShadowParityConfigurationError(
            "CHAINSTACK_" + exc.refusal_reason
        ) from None
    return ShadowParityConfiguration(
        helius=helius,
        chainstack=chainstack,
        legacy_chainstack_alias_present=(
            resolved.sanitized_presence((LEGACY_CHAINSTACK_GRPC_ALIAS,))[
                LEGACY_CHAINSTACK_GRPC_ALIAS
            ]
            == "PRESENT"
        ),
    )


__all__ = (
    "CHAINSTACK_SHADOW_ENV_NAMES",
    "LEGACY_CHAINSTACK_GRPC_ALIAS",
    "SHADOW_PARITY_ENV_NAMES",
    "ShadowParityConfiguration",
    "ShadowParityConfigurationError",
    "load_shadow_parity_configuration",
)
