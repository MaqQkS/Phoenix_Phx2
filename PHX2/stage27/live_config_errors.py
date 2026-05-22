"""Stage 27.1 module-local exception hierarchy.

Stage 27.1 follows the Stage 25 / Stage 26 discipline: module-local
exception types rooted at plain ``Exception``, NOT at a central
PHX2 error registry.

Hierarchy:

    Stage27ConfigError(Exception)
    ├── Stage27LiveModeFailedClosedError
    ├── Stage27MissingRequiredLiveSecretError
    ├── Stage27MalformedLiveSecretError
    └── Stage27RedactionLeakError

Every Stage 27 config error type is engineered so that ``str()``
and ``repr()`` of an instance NEVER include a raw secret value, a
raw webhook URL, a raw RPC / gRPC endpoint, or a raw API-key
substring. Error messages may only reference:

  * the env / config variable NAME
  * a closed-set reason code
  * a closed-set malformed-secret reason
  * a redaction token (a short literal marker like ``<<REDACTED>>``)

The error types do NOT accept a raw secret value as a constructor
argument; the caller must redact at the call site before raising.
"""

from __future__ import annotations

from typing import Optional


class Stage27ConfigError(Exception):
    """Base type for every Stage 27.1 config / readiness violation.

    Module-local; intentionally not a subclass of any central PHX2
    error registry so the prior-stage closed code registries stay
    out of Stage 27.1's surface.
    """


class Stage27LiveModeFailedClosedError(Stage27ConfigError):
    """Raised when LIVE mode was requested but fails closed.

    Raised only by callers that explicitly want a hard failure when
    LIVE mode is requested but cannot be allowed (either factor
    missing, or required live secrets missing / malformed). The
    Stage 27.1 operator config resolver does NOT raise this by
    default -- it instead returns a ``LIVE_REFUSED`` authority.
    Callers (later substages or operator scripts) may raise this
    when they want LIVE-refused to be a hard error.
    """

    def __init__(
        self,
        reason_code: str,
        *,
        missing_secret_names: tuple[str, ...] = (),
        malformed_secret_names: tuple[str, ...] = (),
    ) -> None:
        self.reason_code: str = reason_code
        self.missing_secret_names: tuple[str, ...] = tuple(missing_secret_names)
        self.malformed_secret_names: tuple[str, ...] = tuple(malformed_secret_names)
        parts: list[str] = [f"LIVE mode fails closed: reason={reason_code}"]
        if self.missing_secret_names:
            parts.append(f"missing={list(self.missing_secret_names)!r}")
        if self.malformed_secret_names:
            parts.append(f"malformed={list(self.malformed_secret_names)!r}")
        super().__init__("; ".join(parts))


class Stage27MissingRequiredLiveSecretError(Stage27ConfigError):
    """Raised when a required LIVE secret name is missing.

    Carries only the secret NAME; never the value.
    """

    def __init__(self, secret_name: str) -> None:
        self.secret_name: str = secret_name
        super().__init__(
            f"required LIVE secret is missing: name={secret_name!r}"
        )


class Stage27MalformedLiveSecretError(Stage27ConfigError):
    """Raised when a required LIVE secret value fails format check.

    Carries only the secret NAME and a closed-set malformed-reason
    code. The raw secret value is NEVER carried.
    """

    def __init__(self, secret_name: str, malformed_reason: str) -> None:
        self.secret_name: str = secret_name
        self.malformed_reason: str = malformed_reason
        super().__init__(
            f"required LIVE secret is malformed: "
            f"name={secret_name!r} reason={malformed_reason!r}"
        )


class Stage27RedactionLeakError(Stage27ConfigError):
    """Raised when a redaction-protected surface would have emitted a raw secret.

    Stage 27.1 producers (readiness summary builder, operator
    config builder) raise this when an internal invariant detects
    that a raw secret value would have been included in a printable
    surface. The error carries only the secret NAME and a closed-
    set leak-context token; the offending value is NEVER carried.
    """

    def __init__(
        self,
        secret_name: str,
        leak_context: str,
        *,
        secret_value_length: Optional[int] = None,
    ) -> None:
        self.secret_name: str = secret_name
        self.leak_context: str = leak_context
        self.secret_value_length: Optional[int] = secret_value_length
        msg = (
            f"Stage 27 redaction leak: name={secret_name!r} "
            f"context={leak_context!r}"
        )
        if secret_value_length is not None:
            msg += f" length={secret_value_length}"
        super().__init__(msg)
