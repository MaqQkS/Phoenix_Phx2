"""Stage 28.11 Chainstack Yellowstone gRPC client models.

Stage 28.11 is the post-Stage-28-closure, post-Stage-28.10 narrow
amendment that adds the first REAL Chainstack Yellowstone gRPC
client behind the Stage 28.10 protocol / fake / models boundary.

This module ships the Stage 28.11-private model surface:

  * the immutable, redaction-safe private endpoint-secret record
    that carries the raw gRPC endpoint URL + raw x-token (the
    real credentials never leave this object's private slots),
  * the immutable runtime config record that pairs the Stage
    28.10 safe ``Stage28_10ChainstackYellowstoneConfig`` with
    the private endpoint secret + the Stage 28.11 mode /
    timeout / TLS axes,
  * the closed-set Stage 28.11 mode / probe-status / refusal
    vocabularies,
  * the immutable Stage 28.11 readiness report + probe result
    records,
  * the module-local Stage 28.11 exception hierarchy.

This module imports ONLY stdlib (``dataclasses`` / ``typing``)
plus the Stage 28.10 models module. It does NOT import:

  * ``grpc`` / ``grpcio`` / ``protobuf`` / generated ``*_pb2.py``
    / ``*_pb2_grpc.py`` (the runtime gRPC dependency is admitted
    in the Stage 28.11 client / decode / probe modules only),
  * Stage 21-27 production code,
  * any network / RPC / messaging / DB / scheduler / secrets-
    management library,
  * ``os`` / the process environment.

Discipline:

  * No env reads.
  * No network.
  * No sleep / no scheduling.
  * No top-level I/O at import time.
  * The raw endpoint URL and raw x-token are stored ONLY on the
    private ``Stage28_11ChainstackYellowstoneGrpcEndpointSecret``
    object's private slots; ``__repr__`` / ``__str__`` /
    ``to_safe_dict`` of that object emit only the Stage 28.11
    redaction token + safe length counters. The runtime config
    holds a reference to the secret subobject and never copies
    the raw fields onto its own attrs.
  * Direct constructors run ``__post_init__`` validation so the
    safe-shape contract cannot be bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstoneConfig,
    Stage28_10ChainstackYellowstonePayload,
    is_safe_provider_label,
)


# ---------------------------------------------------------------------------
# Stage 28.11 version axes
# ---------------------------------------------------------------------------


STAGE28_11_MINOR_VERSION: str = "28.11"
STAGE28_11_SCHEMA_VERSION: str = (
    "stage28_11_chainstack_yellowstone_grpc_v0"
)


# Distinctive Stage 28.11 redaction token; distinct from the
# Stage 27 / 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 / 28.6 /
# 28.7 / 28.9 / 28.10 redaction tokens so a leak-scan test for
# one cannot collide with another.
STAGE28_11_REDACTION_TOKEN: str = "<<STAGE28_11_REDACTED>>"


# ---------------------------------------------------------------------------
# Stage 28.11 closed-set: mode
# ---------------------------------------------------------------------------


MODE_READINESS_ONLY: str = "READINESS_ONLY"
MODE_PROVIDER_CONNECT_ONLY: str = "PROVIDER_CONNECT_ONLY"
MODE_ONE_EVENT_DECODE_DRY_RUN: str = "ONE_EVENT_DECODE_DRY_RUN"


MODE_VALUES: tuple[str, ...] = (
    MODE_READINESS_ONLY,
    MODE_PROVIDER_CONNECT_ONLY,
    MODE_ONE_EVENT_DECODE_DRY_RUN,
)


def is_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in MODE_VALUES


# ---------------------------------------------------------------------------
# Stage 28.11 closed-set: probe status
# ---------------------------------------------------------------------------


PROBE_STATUS_READY: str = "READY"
PROBE_STATUS_NOT_READY: str = "NOT_READY"
PROBE_STATUS_CONNECTED: str = "CONNECTED"
PROBE_STATUS_DECODED: str = "DECODED"
PROBE_STATUS_FAILED: str = "FAILED"
PROBE_STATUS_SKIPPED: str = "SKIPPED"


PROBE_STATUS_VALUES: tuple[str, ...] = (
    PROBE_STATUS_READY,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_DECODED,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_SKIPPED,
)


def is_probe_status_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in PROBE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 28.11 closed-set: refusal reason
# ---------------------------------------------------------------------------


REFUSAL_REASON_NONE: str = "NONE"
REFUSAL_REASON_ENDPOINT_MISSING: str = "ENDPOINT_MISSING"
REFUSAL_REASON_X_TOKEN_MISSING: str = "X_TOKEN_MISSING"
REFUSAL_REASON_ENDPOINT_UNSAFE: str = "ENDPOINT_UNSAFE"
REFUSAL_REASON_X_TOKEN_UNSAFE: str = "X_TOKEN_UNSAFE"
REFUSAL_REASON_TIMEOUT_INVALID: str = "TIMEOUT_INVALID"
REFUSAL_REASON_MODE_INVALID: str = "MODE_INVALID"
REFUSAL_REASON_LIVE_FLAG_NOT_SET: str = "LIVE_FLAG_NOT_SET"
REFUSAL_REASON_CONNECT_FAILED: str = "CONNECT_FAILED"
REFUSAL_REASON_DECODE_FAILED: str = "DECODE_FAILED"
REFUSAL_REASON_NO_EVENT_RECEIVED: str = "NO_EVENT_RECEIVED"


REFUSAL_REASON_VALUES: tuple[str, ...] = (
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_ENDPOINT_MISSING,
    REFUSAL_REASON_X_TOKEN_MISSING,
    REFUSAL_REASON_ENDPOINT_UNSAFE,
    REFUSAL_REASON_X_TOKEN_UNSAFE,
    REFUSAL_REASON_TIMEOUT_INVALID,
    REFUSAL_REASON_MODE_INVALID,
    REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    REFUSAL_REASON_CONNECT_FAILED,
    REFUSAL_REASON_DECODE_FAILED,
    REFUSAL_REASON_NO_EVENT_RECEIVED,
)


def is_refusal_reason_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 28.11 module-local exceptions
# ---------------------------------------------------------------------------


class Stage28_11GrpcError(Exception):
    """Base type for every Stage 28.11 model / readiness / decode /
    client / probe validation error. Module-local; not a subclass
    of any central PHX2 error registry. The constructor never
    carries a raw endpoint URL, raw x-token, or raw library
    traceback; callers redact at the call site.
    """


class Stage28_11InvalidEndpointSecretError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 endpoint-secret field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 invalid endpoint secret: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_11InvalidRuntimeConfigError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 runtime config field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 invalid runtime config: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_11InvalidReadinessReportError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 readiness-report field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 invalid readiness report: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_11InvalidProbeResultError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 probe-result field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 invalid probe result: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_11DecodeError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 decode step refuses an upstream
    Yellowstone message at the safe-shape boundary. Carries a
    closed-set reason token; never a raw protobuf field value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 decode error: reason={reason!r}"
        )


class Stage28_11ConnectError(Stage28_11GrpcError):
    """Raised when a Stage 28.11 connect step refuses an upstream
    Chainstack channel at the safe-shape boundary. Carries a
    closed-set reason token; never a raw gRPC error message
    (which can echo URLs / metadata).
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.11 connect error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Safe-shape validators (Stage 28.11 specific)
# ---------------------------------------------------------------------------


# The set of host chars a gRPC endpoint string may carry. Allows
# letters, digits, dot, hyphen, colon (host:port separator),
# slash (for ``dns:///host:port`` form), and ``:`` for ports.
# Deliberately does NOT admit ``@`` (which would carry
# user:pass), ``?`` / ``#`` / ``%`` (which would carry query
# string / fragment / percent-encoded bytes), or whitespace.
_SAFE_ENDPOINT_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789-._:/"
)
_SAFE_ENDPOINT_MIN_LENGTH: int = 4
_SAFE_ENDPOINT_MAX_LENGTH: int = 256


def is_safe_grpc_endpoint_url(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape gRPC endpoint
    string.

    A safe gRPC endpoint:

      * is a non-empty string,
      * has length in ``[4, 256]``,
      * contains only ``[A-Za-z0-9-._:/]`` characters,
      * does NOT carry ``@`` (no inline user:pass),
      * does NOT carry whitespace,
      * does NOT carry ``?`` / ``#`` / ``%`` (no query / fragment
        / percent-encoded bytes),
      * is NOT private-key-like (no WIF prefix, no long pure-hex,
        no JSON-array shape, no base64-padded shape).

    Pure / deterministic. No env access, no I/O.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_ENDPOINT_MIN_LENGTH:
        return False
    if len(value) > _SAFE_ENDPOINT_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_ENDPOINT_ALLOWED_CHARS:
            return False
    if _looks_private_key_like(value):
        return False
    return True


_SAFE_X_TOKEN_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789-_."
)
_SAFE_X_TOKEN_MIN_LENGTH: int = 8
_SAFE_X_TOKEN_MAX_LENGTH: int = 256


def is_safe_grpc_x_token(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape Chainstack
    x-token string.

    A safe x-token:

      * is a non-empty string,
      * has length in ``[8, 256]``,
      * contains only ``[A-Za-z0-9-_.]`` characters,
      * is NOT private-key-like (no WIF prefix, no long pure-hex,
        no JSON-array shape, no base64-padded shape).

    Pure / deterministic. No env access, no I/O.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_X_TOKEN_MIN_LENGTH:
        return False
    if len(value) > _SAFE_X_TOKEN_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_X_TOKEN_ALLOWED_CHARS:
            return False
    if _looks_private_key_like(value):
        return False
    return True


_TIMEOUT_SECONDS_MIN: int = 1
_TIMEOUT_SECONDS_MAX: int = 600


def is_safe_timeout_seconds(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape gRPC timeout
    in whole seconds, ``[1, 600]``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    if value < _TIMEOUT_SECONDS_MIN:
        return False
    if value > _TIMEOUT_SECONDS_MAX:
        return False
    return True


# Bitcoin WIF (wallet-import-format) base58 private-key prefixes.
# Mirrors the Stage 28.10 detector. Stage 28.11 endpoint URLs and
# x-tokens that start with these prefixes are conservatively
# refused.
_PRIVATE_KEY_LIKE_WIF_PREFIXES: tuple[str, ...] = (
    "5K", "5J", "5H", "5L",
)
_PRIVATE_KEY_LIKE_HEX_MIN_LENGTH: int = 64
_PRIVATE_KEY_LIKE_BASE64_PADDED_MIN_LENGTH: int = 44


_HEX_ALPHABET: frozenset[str] = frozenset(
    "0123456789abcdefABCDEF"
)


def _looks_private_key_like(value: object) -> bool:
    """Return ``True`` iff ``value`` resembles raw private-key /
    raw-secret material. Mirrors the Stage 28.10
    ``_looks_private_key_like`` discipline so the Stage 28.11
    endpoint / x-token validators reject the same shapes."""
    if not isinstance(value, str) or value == "":
        return False
    if (
        len(value) >= 2
        and value[:2] in _PRIVATE_KEY_LIKE_WIF_PREFIXES
    ):
        return True
    if value.startswith("["):
        return True
    if len(value) >= _PRIVATE_KEY_LIKE_HEX_MIN_LENGTH:
        if all(ch in _HEX_ALPHABET for ch in value):
            return True
    if (
        len(value) >= _PRIVATE_KEY_LIKE_BASE64_PADDED_MIN_LENGTH
        and value.endswith("=")
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Stage 28.11 private endpoint secret
# ---------------------------------------------------------------------------


class Stage28_11ChainstackYellowstoneGrpcEndpointSecret:
    """Immutable, redaction-safe private record carrying the real
    Chainstack Yellowstone gRPC endpoint URL + x-token.

    Implemented as a regular class (NOT a ``@dataclass``) so the
    raw fields live on private ``__slots__`` and never become
    visible via ``dataclasses.asdict`` / default ``__repr__`` /
    default ``__eq__``. The two access methods used by the Stage
    28.11 client are explicit and named to discourage casual
    callers.

    Discipline:

      * The raw endpoint URL is stored in ``self.__endpoint_url``;
        access only via ``get_endpoint_url_for_internal_use()``.
      * The raw x-token is stored in ``self.__x_token``; access
        only via ``get_x_token_for_internal_use()``.
      * ``__repr__`` / ``__str__`` / ``to_safe_dict`` emit only
        the Stage 28.11 redaction token + safe length counters
        + the locked ``auth_mode = "XTOKEN"`` label.
      * ``__eq__`` / ``__hash__`` compare by safe lengths so two
        distinct secret records carrying different real values
        are distinguishable in a set without leaking the values
        themselves.
    """

    __slots__ = (
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__endpoint_url",
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__x_token",
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__auth_mode",
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__endpoint_length",
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__x_token_length",
        "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__tls",
    )

    def __init__(
        self,
        *,
        endpoint_url: object,
        x_token: object,
        tls: object = True,
    ) -> None:
        if not isinstance(endpoint_url, str):
            raise Stage28_11InvalidEndpointSecretError(
                field_name="endpoint_url",
                reason="ENDPOINT_NOT_STRING",
            )
        if not is_safe_grpc_endpoint_url(endpoint_url):
            raise Stage28_11InvalidEndpointSecretError(
                field_name="endpoint_url",
                reason="ENDPOINT_UNSAFE",
            )
        if not isinstance(x_token, str):
            raise Stage28_11InvalidEndpointSecretError(
                field_name="x_token",
                reason="X_TOKEN_NOT_STRING",
            )
        if not is_safe_grpc_x_token(x_token):
            raise Stage28_11InvalidEndpointSecretError(
                field_name="x_token",
                reason="X_TOKEN_UNSAFE",
            )
        if not isinstance(tls, bool):
            raise Stage28_11InvalidEndpointSecretError(
                field_name="tls",
                reason="TLS_NOT_BOOL",
            )
        if not tls:
            # Stage 28.11 mandates TLS. Plaintext gRPC is refused
            # at construction; a future substage may admit
            # plaintext under explicit operator authorization.
            raise Stage28_11InvalidEndpointSecretError(
                field_name="tls",
                reason="TLS_REQUIRED",
            )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__endpoint_url",
            endpoint_url,
        )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__x_token",
            x_token,
        )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__auth_mode",
            "XTOKEN",
        )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__endpoint_length",
            len(endpoint_url),
        )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__x_token_length",
            len(x_token),
        )
        object.__setattr__(
            self,
            "_Stage28_11ChainstackYellowstoneGrpcEndpointSecret__tls",
            True,
        )

    def __setattr__(self, name: str, value: object) -> None:
        # Frozen: refuse any attribute rebinding after __init__.
        raise Stage28_11InvalidEndpointSecretError(
            field_name=name, reason="FIELD_IS_FROZEN",
        )

    def __delattr__(self, name: str) -> None:
        raise Stage28_11InvalidEndpointSecretError(
            field_name=name, reason="FIELD_IS_FROZEN",
        )

    def __repr__(self) -> str:
        return (
            "Stage28_11ChainstackYellowstoneGrpcEndpointSecret("
            f"endpoint_url={STAGE28_11_REDACTION_TOKEN!r}, "
            f"x_token={STAGE28_11_REDACTION_TOKEN!r}, "
            f"auth_mode={self.__auth_mode!r}, "
            f"endpoint_length={self.__endpoint_length!r}, "
            f"x_token_length={self.__x_token_length!r}, "
            f"tls={self.__tls!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(
            other,
            Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
        ):
            return NotImplemented
        return (
            self.__endpoint_length == other.__endpoint_length
            and self.__x_token_length == other.__x_token_length
            and self.__auth_mode == other.__auth_mode
            and self.__tls == other.__tls
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.__endpoint_length,
                self.__x_token_length,
                self.__auth_mode,
                self.__tls,
            )
        )

    @property
    def auth_mode(self) -> str:
        return self.__auth_mode

    @property
    def endpoint_length(self) -> int:
        return self.__endpoint_length

    @property
    def x_token_length(self) -> int:
        return self.__x_token_length

    @property
    def tls(self) -> bool:
        return self.__tls

    def get_endpoint_url_for_internal_use(self) -> str:
        """Return the raw gRPC endpoint URL.

        The name is deliberately long and explicit so casual
        callers (printers, loggers, serializers) cannot reach the
        raw value by mistake; only the Stage 28.11 gRPC client
        opens the secret at channel-create time.
        """
        return self.__endpoint_url

    def get_x_token_for_internal_use(self) -> str:
        """Return the raw Chainstack x-token.

        The name is deliberately long and explicit so casual
        callers cannot reach the raw value by mistake; only the
        Stage 28.11 gRPC client opens the secret at metadata-
        attach time.
        """
        return self.__x_token

    def to_safe_dict(self) -> dict:
        """Return a deterministic-order, redaction-safe dict
        projection.

        Used by the Stage 28.11 probe and runbook tests to pin
        the secret never echoes the raw URL / token. Carries the
        Stage 28.11 redaction token + the safe length counters +
        the locked auth-mode + TLS axis only.
        """
        return {
            "endpoint_url": STAGE28_11_REDACTION_TOKEN,
            "x_token": STAGE28_11_REDACTION_TOKEN,
            "auth_mode": self.__auth_mode,
            "endpoint_length": self.__endpoint_length,
            "x_token_length": self.__x_token_length,
            "tls": self.__tls,
            "redaction_token": STAGE28_11_REDACTION_TOKEN,
        }


def build_chainstack_yellowstone_grpc_endpoint_secret(
    *,
    endpoint_url: object,
    x_token: object,
    tls: object = True,
) -> Stage28_11ChainstackYellowstoneGrpcEndpointSecret:
    """Construct a redaction-safe Stage 28.11 endpoint-secret
    record.

    Thin factory over the constructor (which runs full validation
    via ``__init__``). Raises
    ``Stage28_11InvalidEndpointSecretError`` on the first failing
    field; the error carries only the closed-set field name +
    reason token, never the raw unsafe value.
    """
    return Stage28_11ChainstackYellowstoneGrpcEndpointSecret(
        endpoint_url=endpoint_url,
        x_token=x_token,
        tls=tls,
    )


# ---------------------------------------------------------------------------
# Stage 28.11 runtime config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage28_11ChainstackYellowstoneGrpcRuntimeConfig:
    """Immutable Stage 28.11 runtime config record.

    Pairs the Stage 28.10 safe ``Stage28_10ChainstackYellowstoneConfig``
    (which carries only safe labels + closed-set tokens) with a
    private ``Stage28_11ChainstackYellowstoneGrpcEndpointSecret``
    (which carries the raw endpoint + x-token on private slots)
    plus the Stage 28.11 mode / timeout / TLS axes.

    The dataclass holds a *reference* to the secret subobject;
    ``dataclasses.asdict`` on this record exposes the subobject
    reference, NOT the raw secret values (the subobject's
    ``__repr__`` and ``to_safe_dict`` redact the raw fields). For
    a fully redacted dict projection callers use
    ``runtime_config_to_dict``.

    Fields:

      * ``safe_config`` -- Stage 28.10 safe boundary config.
      * ``endpoint_secret`` -- private endpoint-secret record.
      * ``mode`` -- closed-set Stage 28.11 mode token.
      * ``timeout_seconds`` -- positive int gRPC deadline.
    """

    safe_config: Stage28_10ChainstackYellowstoneConfig
    endpoint_secret: (
        Stage28_11ChainstackYellowstoneGrpcEndpointSecret
    )
    mode: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        _validate_runtime_config_fields(self)

    def __repr__(self) -> str:
        # Redacted repr — never echoes the secret subobject's
        # raw fields. The subobject's own ``__repr__`` is already
        # redaction-safe; we just call it.
        return (
            "Stage28_11ChainstackYellowstoneGrpcRuntimeConfig("
            f"safe_config={self.safe_config!r}, "
            f"endpoint_secret={self.endpoint_secret!r}, "
            f"mode={self.mode!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )


def _validate_runtime_config_fields(
    record: "Stage28_11ChainstackYellowstoneGrpcRuntimeConfig",
) -> None:
    """Validate every field of a runtime-config record.

    Pure / deterministic. Runs on every direct construction (via
    ``__post_init__``) AND on every builder call. Raises
    ``Stage28_11InvalidRuntimeConfigError`` on the first failing
    field; the error carries only the closed-set field name +
    reason token.
    """
    if not isinstance(
        record.safe_config,
        Stage28_10ChainstackYellowstoneConfig,
    ):
        raise Stage28_11InvalidRuntimeConfigError(
            field_name="safe_config",
            reason="NOT_A_STAGE_28_10_CONFIG",
        )
    if not isinstance(
        record.endpoint_secret,
        Stage28_11ChainstackYellowstoneGrpcEndpointSecret,
    ):
        raise Stage28_11InvalidRuntimeConfigError(
            field_name="endpoint_secret",
            reason="NOT_AN_ENDPOINT_SECRET",
        )
    if not is_mode_value(record.mode):
        raise Stage28_11InvalidRuntimeConfigError(
            field_name="mode",
            reason="MODE_NOT_CLOSED_SET",
        )
    if not is_safe_timeout_seconds(record.timeout_seconds):
        raise Stage28_11InvalidRuntimeConfigError(
            field_name="timeout_seconds",
            reason="TIMEOUT_UNSAFE",
        )


def build_chainstack_yellowstone_grpc_runtime_config(
    *,
    safe_config: object,
    endpoint_secret: object,
    mode: object,
    timeout_seconds: object,
) -> Stage28_11ChainstackYellowstoneGrpcRuntimeConfig:
    """Construct an immutable Stage 28.11 runtime-config record
    with full validation.
    """
    return Stage28_11ChainstackYellowstoneGrpcRuntimeConfig(
        safe_config=safe_config,  # type: ignore[arg-type]
        endpoint_secret=endpoint_secret,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
    )


def runtime_config_to_safe_dict(
    record: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
) -> dict:
    """Project a runtime-config record into a deterministic-order
    fully redacted dict suitable for tests and runbook
    inspection.

    The returned dict carries:

      * the Stage 28.10 safe config (already redaction-safe),
      * the endpoint secret's safe dict (no raw URL / token),
      * the closed-set mode token,
      * the safe timeout int,
      * the Stage 28.11 redaction token.

    Pure / deterministic.
    """
    if not isinstance(
        record,
        Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
    ):
        raise Stage28_11InvalidRuntimeConfigError(
            field_name="record",
            reason="NOT_A_RUNTIME_CONFIG",
        )
    from PHX2.stage28.chainstack_yellowstone_models import (
        config_to_dict as _safe_config_to_dict,
    )
    return {
        "safe_config": _safe_config_to_dict(record.safe_config),
        "endpoint_secret": (
            record.endpoint_secret.to_safe_dict()
        ),
        "mode": record.mode,
        "timeout_seconds": record.timeout_seconds,
        "redaction_token": STAGE28_11_REDACTION_TOKEN,
    }


# ---------------------------------------------------------------------------
# Stage 28.11 readiness report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage28_11GrpcReadinessReport:
    """Immutable Stage 28.11 readiness report.

    Carries only closed-set status + closed-set refusal-reason
    tokens + safe length counters + the safe Stage 28.10
    ``endpoint_safe_label``. NEVER carries the raw endpoint URL
    or raw x-token; the readiness step computes from the env
    projection and the result keeps only the projection's safe
    shape.

    Fields:

      * ``status`` -- closed-set ``PROBE_STATUS_READY`` /
                       ``PROBE_STATUS_NOT_READY``.
      * ``refusal_reason`` -- closed-set
                               ``REFUSAL_REASON_*`` token.
      * ``endpoint_safe_label`` -- Stage 28.10 safe label echoed
                                    when readiness reports the
                                    endpoint shape is valid.
      * ``endpoint_length`` -- safe length counter (0 when
                                missing).
      * ``x_token_length`` -- safe length counter (0 when
                               missing).
      * ``live_flag_set`` -- whether the live-gate env flag is
                              set; readiness exposes the bool
                              only, never the env name's raw
                              value.
      * ``timeout_seconds`` -- effective gRPC deadline used by
                                later modes when readiness
                                completes; positive int.
    """

    status: str
    refusal_reason: str
    endpoint_safe_label: Optional[str]
    endpoint_length: int
    x_token_length: int
    live_flag_set: bool
    timeout_seconds: int

    def __post_init__(self) -> None:
        _validate_readiness_report_fields(self)


def _validate_readiness_report_fields(
    record: "Stage28_11GrpcReadinessReport",
) -> None:
    if not is_probe_status_value(record.status):
        raise Stage28_11InvalidReadinessReportError(
            field_name="status",
            reason="STATUS_NOT_CLOSED_SET",
        )
    if record.status not in (
        PROBE_STATUS_READY,
        PROBE_STATUS_NOT_READY,
    ):
        raise Stage28_11InvalidReadinessReportError(
            field_name="status",
            reason="STATUS_NOT_READINESS_VALUE",
        )
    if not is_refusal_reason_value(record.refusal_reason):
        raise Stage28_11InvalidReadinessReportError(
            field_name="refusal_reason",
            reason="REFUSAL_REASON_NOT_CLOSED_SET",
        )
    if record.endpoint_safe_label is not None:
        if not is_safe_provider_label(record.endpoint_safe_label):
            raise Stage28_11InvalidReadinessReportError(
                field_name="endpoint_safe_label",
                reason="LABEL_UNSAFE",
            )
    if (
        isinstance(record.endpoint_length, bool)
        or not isinstance(record.endpoint_length, int)
    ):
        raise Stage28_11InvalidReadinessReportError(
            field_name="endpoint_length",
            reason="LENGTH_NOT_INT",
        )
    if record.endpoint_length < 0:
        raise Stage28_11InvalidReadinessReportError(
            field_name="endpoint_length",
            reason="LENGTH_NEGATIVE",
        )
    if (
        isinstance(record.x_token_length, bool)
        or not isinstance(record.x_token_length, int)
    ):
        raise Stage28_11InvalidReadinessReportError(
            field_name="x_token_length",
            reason="LENGTH_NOT_INT",
        )
    if record.x_token_length < 0:
        raise Stage28_11InvalidReadinessReportError(
            field_name="x_token_length",
            reason="LENGTH_NEGATIVE",
        )
    if not isinstance(record.live_flag_set, bool):
        raise Stage28_11InvalidReadinessReportError(
            field_name="live_flag_set",
            reason="LIVE_FLAG_NOT_BOOL",
        )
    if not is_safe_timeout_seconds(record.timeout_seconds):
        raise Stage28_11InvalidReadinessReportError(
            field_name="timeout_seconds",
            reason="TIMEOUT_UNSAFE",
        )


def build_grpc_readiness_report(
    *,
    status: object,
    refusal_reason: object,
    endpoint_safe_label: object = None,
    endpoint_length: object = 0,
    x_token_length: object = 0,
    live_flag_set: object = False,
    timeout_seconds: object = 30,
) -> Stage28_11GrpcReadinessReport:
    return Stage28_11GrpcReadinessReport(
        status=status,  # type: ignore[arg-type]
        refusal_reason=refusal_reason,  # type: ignore[arg-type]
        endpoint_safe_label=(
            endpoint_safe_label  # type: ignore[arg-type]
        ),
        endpoint_length=endpoint_length,  # type: ignore[arg-type]
        x_token_length=x_token_length,  # type: ignore[arg-type]
        live_flag_set=live_flag_set,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
    )


def readiness_report_to_safe_dict(
    record: Stage28_11GrpcReadinessReport,
) -> dict:
    if not isinstance(record, Stage28_11GrpcReadinessReport):
        raise Stage28_11InvalidReadinessReportError(
            field_name="record",
            reason="NOT_A_READINESS_REPORT",
        )
    return {
        "status": record.status,
        "refusal_reason": record.refusal_reason,
        "endpoint_safe_label": record.endpoint_safe_label,
        "endpoint_length": record.endpoint_length,
        "x_token_length": record.x_token_length,
        "live_flag_set": record.live_flag_set,
        "timeout_seconds": record.timeout_seconds,
        "redaction_token": STAGE28_11_REDACTION_TOKEN,
    }


# ---------------------------------------------------------------------------
# Stage 28.11 probe result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage28_11GrpcProbeResult:
    """Immutable Stage 28.11 probe result.

    Carries only closed-set status / refusal-reason tokens, an
    optional Stage 28.10 ``Stage28_10ChainstackYellowstonePayload``
    when the one-event decode mode emitted one, and the boolean
    ``handoff_ready`` axis that signals to the operator whether
    Stage 28.12 (the Stage 28.9 wrapper with
    ``max_events=1`` / ``max_dispatches=1``) MAY be attempted
    next under separate authorization.

    Fields:

      * ``mode`` -- closed-set Stage 28.11 mode token executed.
      * ``status`` -- closed-set probe-status token.
      * ``refusal_reason`` -- closed-set refusal-reason token
                              (``NONE`` when the probe succeeded).
      * ``ready`` -- True iff the readiness sub-step passed.
      * ``connected`` -- True iff the connect-only sub-step
                         passed.
      * ``decoded`` -- True iff the one-event decode sub-step
                       emitted one Stage 28.10 payload.
      * ``decoded_payload`` -- the one Stage 28.10 payload (or
                                ``None`` when no decode).
      * ``handoff_ready`` -- True iff all three sub-steps that
                             the mode targeted passed.
      * ``events_received`` -- safe int counter (0 in
                                readiness-only / connect-only
                                modes; 0 or 1 in dry-run mode).
      * ``schema_version`` -- locked Stage 28.11 schema string.
    """

    mode: str
    status: str
    refusal_reason: str
    ready: bool
    connected: bool
    decoded: bool
    decoded_payload: Optional[
        Stage28_10ChainstackYellowstonePayload
    ]
    handoff_ready: bool
    events_received: int
    schema_version: str = STAGE28_11_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_probe_result_fields(self)


def _validate_probe_result_fields(
    record: "Stage28_11GrpcProbeResult",
) -> None:
    if record.schema_version != STAGE28_11_SCHEMA_VERSION:
        raise Stage28_11InvalidProbeResultError(
            field_name="schema_version",
            reason="SCHEMA_VERSION_NOT_LOCKED",
        )
    if not is_mode_value(record.mode):
        raise Stage28_11InvalidProbeResultError(
            field_name="mode",
            reason="MODE_NOT_CLOSED_SET",
        )
    if not is_probe_status_value(record.status):
        raise Stage28_11InvalidProbeResultError(
            field_name="status",
            reason="STATUS_NOT_CLOSED_SET",
        )
    if not is_refusal_reason_value(record.refusal_reason):
        raise Stage28_11InvalidProbeResultError(
            field_name="refusal_reason",
            reason="REFUSAL_REASON_NOT_CLOSED_SET",
        )
    if not isinstance(record.ready, bool):
        raise Stage28_11InvalidProbeResultError(
            field_name="ready",
            reason="READY_NOT_BOOL",
        )
    if not isinstance(record.connected, bool):
        raise Stage28_11InvalidProbeResultError(
            field_name="connected",
            reason="CONNECTED_NOT_BOOL",
        )
    if not isinstance(record.decoded, bool):
        raise Stage28_11InvalidProbeResultError(
            field_name="decoded",
            reason="DECODED_NOT_BOOL",
        )
    if record.decoded_payload is not None:
        if not isinstance(
            record.decoded_payload,
            Stage28_10ChainstackYellowstonePayload,
        ):
            raise Stage28_11InvalidProbeResultError(
                field_name="decoded_payload",
                reason="PAYLOAD_NOT_STAGE_28_10",
            )
    if not isinstance(record.handoff_ready, bool):
        raise Stage28_11InvalidProbeResultError(
            field_name="handoff_ready",
            reason="HANDOFF_READY_NOT_BOOL",
        )
    if (
        isinstance(record.events_received, bool)
        or not isinstance(record.events_received, int)
    ):
        raise Stage28_11InvalidProbeResultError(
            field_name="events_received",
            reason="EVENTS_RECEIVED_NOT_INT",
        )
    if record.events_received < 0:
        raise Stage28_11InvalidProbeResultError(
            field_name="events_received",
            reason="EVENTS_RECEIVED_NEGATIVE",
        )
    if record.events_received > 1:
        # Stage 28.11 dry-run is bounded to at most one event
        # per probe; counters above 1 indicate a bound was
        # broken.
        raise Stage28_11InvalidProbeResultError(
            field_name="events_received",
            reason="EVENTS_RECEIVED_EXCEEDS_DRY_RUN_BOUND",
        )


def build_grpc_probe_result(
    *,
    mode: object,
    status: object,
    refusal_reason: object,
    ready: object,
    connected: object,
    decoded: object,
    decoded_payload: object = None,
    handoff_ready: object = False,
    events_received: object = 0,
) -> Stage28_11GrpcProbeResult:
    return Stage28_11GrpcProbeResult(
        mode=mode,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        refusal_reason=refusal_reason,  # type: ignore[arg-type]
        ready=ready,  # type: ignore[arg-type]
        connected=connected,  # type: ignore[arg-type]
        decoded=decoded,  # type: ignore[arg-type]
        decoded_payload=(
            decoded_payload  # type: ignore[arg-type]
        ),
        handoff_ready=handoff_ready,  # type: ignore[arg-type]
        events_received=(
            events_received  # type: ignore[arg-type]
        ),
        schema_version=STAGE28_11_SCHEMA_VERSION,
    )


def probe_result_to_safe_dict(
    record: Stage28_11GrpcProbeResult,
) -> dict:
    if not isinstance(record, Stage28_11GrpcProbeResult):
        raise Stage28_11InvalidProbeResultError(
            field_name="record",
            reason="NOT_A_PROBE_RESULT",
        )
    from PHX2.stage28.chainstack_yellowstone_models import (
        payload_to_dict as _safe_payload_to_dict,
    )
    decoded_dict = None
    if record.decoded_payload is not None:
        decoded_dict = _safe_payload_to_dict(
            record.decoded_payload,
        )
    return {
        "mode": record.mode,
        "status": record.status,
        "refusal_reason": record.refusal_reason,
        "ready": record.ready,
        "connected": record.connected,
        "decoded": record.decoded,
        "decoded_payload": decoded_dict,
        "handoff_ready": record.handoff_ready,
        "events_received": record.events_received,
        "schema_version": record.schema_version,
        "redaction_token": STAGE28_11_REDACTION_TOKEN,
    }


__all__ = (
    # Version axes.
    "STAGE28_11_MINOR_VERSION",
    "STAGE28_11_SCHEMA_VERSION",
    "STAGE28_11_REDACTION_TOKEN",
    # Mode vocabulary.
    "MODE_READINESS_ONLY",
    "MODE_PROVIDER_CONNECT_ONLY",
    "MODE_ONE_EVENT_DECODE_DRY_RUN",
    "MODE_VALUES",
    "is_mode_value",
    # Probe-status vocabulary.
    "PROBE_STATUS_READY",
    "PROBE_STATUS_NOT_READY",
    "PROBE_STATUS_CONNECTED",
    "PROBE_STATUS_DECODED",
    "PROBE_STATUS_FAILED",
    "PROBE_STATUS_SKIPPED",
    "PROBE_STATUS_VALUES",
    "is_probe_status_value",
    # Refusal-reason vocabulary.
    "REFUSAL_REASON_NONE",
    "REFUSAL_REASON_ENDPOINT_MISSING",
    "REFUSAL_REASON_X_TOKEN_MISSING",
    "REFUSAL_REASON_ENDPOINT_UNSAFE",
    "REFUSAL_REASON_X_TOKEN_UNSAFE",
    "REFUSAL_REASON_TIMEOUT_INVALID",
    "REFUSAL_REASON_MODE_INVALID",
    "REFUSAL_REASON_LIVE_FLAG_NOT_SET",
    "REFUSAL_REASON_CONNECT_FAILED",
    "REFUSAL_REASON_DECODE_FAILED",
    "REFUSAL_REASON_NO_EVENT_RECEIVED",
    "REFUSAL_REASON_VALUES",
    "is_refusal_reason_value",
    # Safe-shape validators.
    "is_safe_grpc_endpoint_url",
    "is_safe_grpc_x_token",
    "is_safe_timeout_seconds",
    # Records + builders.
    "Stage28_11ChainstackYellowstoneGrpcEndpointSecret",
    "build_chainstack_yellowstone_grpc_endpoint_secret",
    "Stage28_11ChainstackYellowstoneGrpcRuntimeConfig",
    "build_chainstack_yellowstone_grpc_runtime_config",
    "runtime_config_to_safe_dict",
    "Stage28_11GrpcReadinessReport",
    "build_grpc_readiness_report",
    "readiness_report_to_safe_dict",
    "Stage28_11GrpcProbeResult",
    "build_grpc_probe_result",
    "probe_result_to_safe_dict",
    # Exceptions.
    "Stage28_11GrpcError",
    "Stage28_11InvalidEndpointSecretError",
    "Stage28_11InvalidRuntimeConfigError",
    "Stage28_11InvalidReadinessReportError",
    "Stage28_11InvalidProbeResultError",
    "Stage28_11DecodeError",
    "Stage28_11ConnectError",
)
