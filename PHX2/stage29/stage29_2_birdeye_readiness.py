"""Stage 29.2 Birdeye readiness boundary.

This module is the SINGLE Stage 29.2 surface that reads the
process environment for Stage 29.2-specific env names. Every
other Stage 29.2 module (models / http transport / sources /
probe-models / probe / manifest) receives an explicit
``Mapping[str, str]`` projection through this boundary or runs
against an explicitly-constructed runtime-config record.

The Stage 29.2 boundary scan asserts ``os.environ`` /
``os.getenv`` / ``os.environb`` appear only here in the Stage
29.2 production tree.

This module:

  * reads exactly four locked env names
    (``PHX2_STAGE29_2_BIRDEYE_API_KEY``,
    ``PHX2_STAGE29_2_BIRDEYE_BASE_URL``,
    ``PHX2_STAGE29_2_ALLOW_LIVE_HTTP``,
    ``PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS``),
  * projects the env into a safe public projection record AND a
    private endpoint-secret record (when the env is well-formed),
  * emits a closed-set readiness report carrying only safe
    length counters + closed-set status / refusal tokens,
  * NEVER echoes the raw API key, raw base URL, raw live-gate
    string, or raw timeout-override string to any log, repr,
    dict, exception, or persisted record.

The module mirrors the Stage 28.11 readiness pattern exactly.

This module imports stdlib (``os`` / ``dataclasses`` / ``typing``)
plus the Stage 29.2 constants + models modules. It does NOT
import:

  * Stage 21-28 production code,
  * any network / RPC / messaging / DB / scheduler / secrets /
    wallet / trading / Discord / Telegram / X / dotenv / keyring
    library,
  * any PHX1 / legacy Phoenix-1 source tree module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from PHX2.stage29.birdeye_constants import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION,
    STAGE29_2_REDACTION_TOKEN,
    is_safe_api_key,
    is_safe_base_url,
    is_safe_timeout_seconds,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_API_KEY_MISSING,
    BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE,
    BIRDEYE_REFUSAL_REASON_NONE,
    BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID,
    Stage29_2BirdeyeError,
    is_birdeye_refusal_reason_value,
)


# ---------------------------------------------------------------------------
# Locked Stage 29.2 env-name surface
# ---------------------------------------------------------------------------


ENV_NAME_BIRDEYE_API_KEY: str = "PHX2_STAGE29_2_BIRDEYE_API_KEY"
ENV_NAME_BIRDEYE_BASE_URL: str = "PHX2_STAGE29_2_BIRDEYE_BASE_URL"
ENV_NAME_ALLOW_LIVE_HTTP: str = "PHX2_STAGE29_2_ALLOW_LIVE_HTTP"
ENV_NAME_HTTP_TIMEOUT_SECONDS: str = (
    "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS"
)


STAGE29_2_READ_ENV_NAMES: tuple[str, ...] = (
    ENV_NAME_BIRDEYE_API_KEY,
    ENV_NAME_BIRDEYE_BASE_URL,
    ENV_NAME_ALLOW_LIVE_HTTP,
    ENV_NAME_HTTP_TIMEOUT_SECONDS,
)


# ---------------------------------------------------------------------------
# Probe-status closed set (READY / NOT_READY only at the readiness layer)
# ---------------------------------------------------------------------------


READINESS_STATUS_READY: str = "READY"
READINESS_STATUS_NOT_READY: str = "NOT_READY"


READINESS_STATUS_VALUES: tuple[str, ...] = (
    READINESS_STATUS_READY,
    READINESS_STATUS_NOT_READY,
)


def is_readiness_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in READINESS_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Timeout-override status (matches Stage 28.11 pattern)
# ---------------------------------------------------------------------------


TIMEOUT_STATUS_DEFAULT: str = "DEFAULT"
TIMEOUT_STATUS_OVERRIDE: str = "OVERRIDE"
TIMEOUT_STATUS_INVALID: str = "INVALID"


TIMEOUT_STATUS_VALUES: tuple[str, ...] = (
    TIMEOUT_STATUS_DEFAULT,
    TIMEOUT_STATUS_OVERRIDE,
    TIMEOUT_STATUS_INVALID,
)


# ---------------------------------------------------------------------------
# Env-read helpers
# ---------------------------------------------------------------------------


def _read_env_value(
    name: str,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return the env value for ``name``, or ``None`` if not set.

    When ``env`` is provided the projection runs against the
    caller-supplied mapping (testing path). When ``env`` is
    ``None``, the projection reads ``os.environ`` -- this is the
    ONLY production env-read site in the Stage 29.2 tree.
    """
    if env is not None:
        value = env.get(name)
    else:
        value = os.environ.get(name)
    if value is None:
        return None
    return value


def _read_stage29_2_env_raw(
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Private: read the Stage 29.2 env-name surface into a plain
    dict containing the RAW values.

    This helper is module-private and is NEVER exported via
    ``__all__``. The raw values it returns flow only into:

      * the internal readiness validator (which projects them
        onto closed-set status / refusal-reason tokens + safe
        length counters; never echoes the raw values),
      * the private endpoint-secret constructor (which carries
        them on the secret's private slots and redacts every
        public surface).
    """
    projected: dict[str, str] = {}
    for name in STAGE29_2_READ_ENV_NAMES:
        value = _read_env_value(name, env=env)
        if value is None:
            continue
        projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Public, redaction-safe env projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2SafeEnvProjection:
    """Immutable, redaction-safe public projection of the Stage
    29.2 env-name surface.

    Carries ONLY:

      * presence booleans for each of the four Stage 29.2 env
        names,
      * safe length counters (raw env-string lengths; never the
        characters of the values themselves),
      * the locked truthy boolean for the live-gate flag,
      * the closed-set timeout-status token.

    NEVER carries any raw API key, raw base URL, raw live-gate
    string, or raw timeout-override string. Safe to log,
    persist, repr, asdict, or include in a redacted public
    artifact.
    """

    api_key_present: bool
    base_url_present: bool
    live_flag_present: bool
    timeout_present: bool
    api_key_length: int
    base_url_length: int
    live_flag_value_is_allow: bool
    timeout_status: str


def _is_truthy_env_flag(value: object) -> bool:
    """Return ``True`` iff ``value`` is the locked truthy Stage
    29.2 live-gate marker ``"1"`` (case-sensitive, deliberately
    narrow). Other truthy-looking strings (``"true"`` / ``"yes"``
    / ``"on"`` / ``"True"``) are rejected to keep the live gate
    explicit; the operator must set exactly ``1``.
    """
    return value == "1"


def _parse_timeout_seconds(value: object) -> Optional[int]:
    """Return the safe int timeout seconds, or ``None`` when the
    env-supplied value is unsafe.

    Returns ``DEFAULT_HTTP_TIMEOUT_SECONDS`` when the env value
    is ``None`` (the override is opt-in). Returns ``None`` when
    the env value is present but cannot be parsed as a safe int
    in the Stage 29.2 bounded range -- the caller maps that to
    ``BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID``.
    """
    if value is None:
        return DEFAULT_HTTP_TIMEOUT_SECONDS
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


def project_stage29_2_env_safe(
    env: Optional[Mapping[str, str]] = None,
) -> Stage29_2SafeEnvProjection:
    """Public, redaction-safe projection of the Stage 29.2 env
    surface. Returns a ``Stage29_2SafeEnvProjection`` carrying
    only presence booleans + safe length counters + the locked
    truthy boolean + the closed-set timeout-status token. NEVER
    echoes a raw API key, raw base URL, raw live-gate string, or
    raw timeout-override string.
    """
    raw = _read_stage29_2_env_raw(env=env)
    api_key_raw = raw.get(ENV_NAME_BIRDEYE_API_KEY)
    base_url_raw = raw.get(ENV_NAME_BIRDEYE_BASE_URL)
    live_flag_raw = raw.get(ENV_NAME_ALLOW_LIVE_HTTP)
    timeout_raw = raw.get(ENV_NAME_HTTP_TIMEOUT_SECONDS)
    if timeout_raw is None:
        timeout_status = TIMEOUT_STATUS_DEFAULT
    elif _parse_timeout_seconds(timeout_raw) is None:
        timeout_status = TIMEOUT_STATUS_INVALID
    else:
        timeout_status = TIMEOUT_STATUS_OVERRIDE
    return Stage29_2SafeEnvProjection(
        api_key_present=(
            isinstance(api_key_raw, str) and api_key_raw != ""
        ),
        base_url_present=(
            isinstance(base_url_raw, str) and base_url_raw != ""
        ),
        live_flag_present=live_flag_raw is not None,
        timeout_present=timeout_raw is not None,
        api_key_length=(
            len(api_key_raw)
            if isinstance(api_key_raw, str)
            else 0
        ),
        base_url_length=(
            len(base_url_raw)
            if isinstance(base_url_raw, str)
            else 0
        ),
        live_flag_value_is_allow=_is_truthy_env_flag(
            live_flag_raw,
        ),
        timeout_status=timeout_status,
    )


# ---------------------------------------------------------------------------
# Readiness report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeReadinessReport:
    """Immutable, redaction-safe Stage 29.2 readiness report.

    Carries ONLY closed-set status / refusal tokens + safe
    length counters + the locked truthy boolean + the resolved
    int timeout. NEVER carries any raw env value.
    """

    status: str
    refusal_reason: str
    api_key_length: int
    base_url_length: int
    live_flag_set: bool
    timeout_seconds: int
    schema_version: str

    def __post_init__(self) -> None:
        _validate_readiness_report(self)


def _validate_readiness_report(
    record: "Stage29_2BirdeyeReadinessReport",
) -> None:
    if not is_readiness_status_value(record.status):
        raise Stage29_2BirdeyeError(
            "READINESS_STATUS_NOT_CLOSED_SET"
        )
    if not is_birdeye_refusal_reason_value(
        record.refusal_reason
    ):
        raise Stage29_2BirdeyeError(
            "REFUSAL_REASON_NOT_CLOSED_SET"
        )
    if (
        isinstance(record.api_key_length, bool)
        or not isinstance(record.api_key_length, int)
        or record.api_key_length < 0
    ):
        raise Stage29_2BirdeyeError(
            "API_KEY_LENGTH_UNSAFE"
        )
    if (
        isinstance(record.base_url_length, bool)
        or not isinstance(record.base_url_length, int)
        or record.base_url_length < 0
    ):
        raise Stage29_2BirdeyeError(
            "BASE_URL_LENGTH_UNSAFE"
        )
    if not isinstance(record.live_flag_set, bool):
        raise Stage29_2BirdeyeError(
            "LIVE_FLAG_SET_NOT_BOOL"
        )
    if not is_safe_timeout_seconds(record.timeout_seconds):
        raise Stage29_2BirdeyeError(
            "TIMEOUT_SECONDS_UNSAFE"
        )


def build_readiness_report(
    *,
    status: str,
    refusal_reason: str,
    api_key_length: int,
    base_url_length: int,
    live_flag_set: bool,
    timeout_seconds: int,
) -> Stage29_2BirdeyeReadinessReport:
    """Construct a validated readiness report."""
    return Stage29_2BirdeyeReadinessReport(
        status=status,
        refusal_reason=refusal_reason,
        api_key_length=api_key_length,
        base_url_length=base_url_length,
        live_flag_set=live_flag_set,
        timeout_seconds=timeout_seconds,
        schema_version=(
            STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION
        ),
    )


def detect_stage29_2_birdeye_readiness(
    env: Optional[Mapping[str, str]] = None,
) -> Stage29_2BirdeyeReadinessReport:
    """Top-level Stage 29.2 readiness entry point.

    Projects the Stage 29.2 env-name surface through the env-read
    boundary and assesses readiness. Returns a
    ``Stage29_2BirdeyeReadinessReport`` whose ``status`` is
    ``READINESS_STATUS_READY`` iff:

      * ``PHX2_STAGE29_2_BIRDEYE_API_KEY`` is a safe-shape API key,
      * ``PHX2_STAGE29_2_BIRDEYE_BASE_URL`` is a safe-shape base URL,
      * the optional ``PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS`` is
        either unset (defaults applied) OR a safe int.

    The live-gate env (``PHX2_STAGE29_2_ALLOW_LIVE_HTTP``) is
    NOT required for ``READY`` -- readiness alone is offline.
    The live-gate flag is surfaced on the report as
    ``live_flag_set`` so the probe / live-test layers can gate
    themselves.

    Pure with respect to a caller-supplied ``env``.
    """
    projected = _read_stage29_2_env_raw(env=env)
    api_key_raw = projected.get(ENV_NAME_BIRDEYE_API_KEY)
    base_url_raw = projected.get(ENV_NAME_BIRDEYE_BASE_URL)
    live_flag_raw = projected.get(ENV_NAME_ALLOW_LIVE_HTTP)
    timeout_raw = projected.get(ENV_NAME_HTTP_TIMEOUT_SECONDS)

    api_key_length = (
        len(api_key_raw) if isinstance(api_key_raw, str) else 0
    )
    base_url_length = (
        len(base_url_raw)
        if isinstance(base_url_raw, str)
        else 0
    )
    live_flag_set = _is_truthy_env_flag(live_flag_raw)

    timeout_seconds = _parse_timeout_seconds(timeout_raw)
    if timeout_seconds is None:
        return build_readiness_report(
            status=READINESS_STATUS_NOT_READY,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID
            ),
            api_key_length=api_key_length,
            base_url_length=base_url_length,
            live_flag_set=live_flag_set,
            timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

    if base_url_raw is None or base_url_raw == "":
        return build_readiness_report(
            status=READINESS_STATUS_NOT_READY,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING
            ),
            api_key_length=api_key_length,
            base_url_length=base_url_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if not is_safe_base_url(base_url_raw):
        return build_readiness_report(
            status=READINESS_STATUS_NOT_READY,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE
            ),
            api_key_length=api_key_length,
            base_url_length=base_url_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if api_key_raw is None or api_key_raw == "":
        return build_readiness_report(
            status=READINESS_STATUS_NOT_READY,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_API_KEY_MISSING
            ),
            api_key_length=api_key_length,
            base_url_length=base_url_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )
    if not is_safe_api_key(api_key_raw):
        return build_readiness_report(
            status=READINESS_STATUS_NOT_READY,
            refusal_reason=(
                BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE
            ),
            api_key_length=api_key_length,
            base_url_length=base_url_length,
            live_flag_set=live_flag_set,
            timeout_seconds=timeout_seconds,
        )

    return build_readiness_report(
        status=READINESS_STATUS_READY,
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        api_key_length=api_key_length,
        base_url_length=base_url_length,
        live_flag_set=live_flag_set,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Private endpoint-secret + runtime-config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeEndpointSecret:
    """Private record carrying the raw Birdeye API key + raw
    base URL.

    Stage 29.2 NEVER exposes the raw values on any public
    surface. ``__repr__`` / ``__str__`` emit only the Stage 29.2
    redaction token + safe length counters. The HTTP transport
    reads ``_api_key`` and ``_base_url`` only at request-build
    time and never copies them onto any returned record.
    """

    _api_key: str
    _base_url: str

    def __post_init__(self) -> None:
        if not is_safe_api_key(self._api_key):
            raise Stage29_2BirdeyeError(
                "API_KEY_UNSAFE_AT_SECRET_BUILD"
            )
        if not is_safe_base_url(self._base_url):
            raise Stage29_2BirdeyeError(
                "BASE_URL_UNSAFE_AT_SECRET_BUILD"
            )

    def __repr__(self) -> str:
        return (
            f"Stage29_2BirdeyeEndpointSecret("
            f"api_key={STAGE29_2_REDACTION_TOKEN!r} "
            f"api_key_length={len(self._api_key)} "
            f"base_url={STAGE29_2_REDACTION_TOKEN!r} "
            f"base_url_length={len(self._base_url)})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def safe_summary(self) -> dict[str, object]:
        """Return a redaction-safe dict for artifact persistence."""
        return {
            "api_key": STAGE29_2_REDACTION_TOKEN,
            "api_key_length": len(self._api_key),
            "base_url": STAGE29_2_REDACTION_TOKEN,
            "base_url_length": len(self._base_url),
        }

    def reveal_api_key(self) -> str:
        """Return the raw API key. ONLY the HTTP transport may
        call this; production code MUST NOT log / persist / repr
        the returned string.
        """
        return self._api_key

    def reveal_base_url(self) -> str:
        """Return the raw base URL. ONLY the HTTP transport may
        call this; production code MUST NOT log / persist / repr
        the returned string.
        """
        return self._base_url


@dataclass(frozen=True)
class Stage29_2BirdeyeRuntimeConfig:
    """Immutable Stage 29.2 runtime config.

    Pairs the private endpoint-secret subobject with the resolved
    int timeout + the closed-set live-flag boolean. ``__repr__``
    is redaction-safe: it never copies the raw API key / base URL
    onto its own attrs; it only references the secret subobject's
    own redacted repr.
    """

    endpoint_secret: Stage29_2BirdeyeEndpointSecret
    timeout_seconds: int
    live_flag_set: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.endpoint_secret,
            Stage29_2BirdeyeEndpointSecret,
        ):
            raise Stage29_2BirdeyeError(
                "ENDPOINT_SECRET_TYPE_INVALID"
            )
        if not is_safe_timeout_seconds(self.timeout_seconds):
            raise Stage29_2BirdeyeError(
                "TIMEOUT_SECONDS_UNSAFE"
            )
        if not isinstance(self.live_flag_set, bool):
            raise Stage29_2BirdeyeError(
                "LIVE_FLAG_SET_NOT_BOOL"
            )


class Stage29_2ReadinessEnvError(Stage29_2BirdeyeError):
    """Raised when the env-driven secret / runtime-config build
    refuses because the env did not pass readiness.

    Carries the closed-set ``BIRDEYE_REFUSAL_REASON_*`` token
    from the readiness report; NEVER the raw API key or raw
    base URL.
    """

    def __init__(self, refusal_reason: str) -> None:
        self.refusal_reason: str = refusal_reason
        super().__init__(refusal_reason)


def build_endpoint_secret_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> Stage29_2BirdeyeEndpointSecret:
    """Read the Stage 29.2 env names and construct a private
    endpoint-secret record.

    Raises ``Stage29_2ReadinessEnvError`` (carrying the
    closed-set refusal-reason token) when the env did not pass
    readiness. The raw values never appear on the exception
    object's attributes.
    """
    report = detect_stage29_2_birdeye_readiness(env=env)
    if report.status != READINESS_STATUS_READY:
        raise Stage29_2ReadinessEnvError(
            refusal_reason=report.refusal_reason,
        )
    projected = _read_stage29_2_env_raw(env=env)
    api_key_raw = projected.get(ENV_NAME_BIRDEYE_API_KEY)
    base_url_raw = projected.get(ENV_NAME_BIRDEYE_BASE_URL)
    # ``detect_stage29_2_birdeye_readiness`` guarantees both
    # values are present + safe-shape; we wrap immediately.
    return Stage29_2BirdeyeEndpointSecret(
        _api_key=api_key_raw,
        _base_url=base_url_raw,
    )


def build_runtime_config_from_env(
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Stage29_2BirdeyeRuntimeConfig:
    """Read the Stage 29.2 env names and construct a runtime
    config record paired with the private secret subobject.
    """
    secret = build_endpoint_secret_from_env(env=env)
    report = detect_stage29_2_birdeye_readiness(env=env)
    return Stage29_2BirdeyeRuntimeConfig(
        endpoint_secret=secret,
        timeout_seconds=report.timeout_seconds,
        live_flag_set=report.live_flag_set,
    )


__all__ = (
    "ENV_NAME_BIRDEYE_API_KEY",
    "ENV_NAME_BIRDEYE_BASE_URL",
    "ENV_NAME_ALLOW_LIVE_HTTP",
    "ENV_NAME_HTTP_TIMEOUT_SECONDS",
    "STAGE29_2_READ_ENV_NAMES",
    "READINESS_STATUS_READY",
    "READINESS_STATUS_NOT_READY",
    "READINESS_STATUS_VALUES",
    "is_readiness_status_value",
    "TIMEOUT_STATUS_DEFAULT",
    "TIMEOUT_STATUS_OVERRIDE",
    "TIMEOUT_STATUS_INVALID",
    "TIMEOUT_STATUS_VALUES",
    "Stage29_2SafeEnvProjection",
    "project_stage29_2_env_safe",
    "Stage29_2BirdeyeReadinessReport",
    "build_readiness_report",
    "detect_stage29_2_birdeye_readiness",
    "Stage29_2BirdeyeEndpointSecret",
    "Stage29_2BirdeyeRuntimeConfig",
    "Stage29_2ReadinessEnvError",
    "build_endpoint_secret_from_env",
    "build_runtime_config_from_env",
)
