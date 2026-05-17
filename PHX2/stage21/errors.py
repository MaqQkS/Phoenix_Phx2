"""Stage 21 closed-set exception hierarchy (foundation only at 21.1).

Stage 21 follows the Stage 20 pattern: a small set of stage-scoped
exception types, each carrying a closed ``code`` from
``Stage21ErrorCode`` / ``Stage21WarningCode``. Callers and tests
match on ``.code`` rather than parsing the formatted message.

Stage 21 also splits the exception surface into a handful of
sub-classes -- config, secret, boundary, telemetry, provider
contract, transport contract -- so misuse at a specific seam
surfaces as a specific exception type while still carrying a closed
code. Each sub-class is intentionally narrow; the registry test
asserts every declared code maps to exactly one expected family.

Stage 21.1 exception messages are scrubbed of any secret content
before they leave this module. The constructor never accepts a raw
secret value; callers pass code + detail strings only, and the
detail string is required by contract to be non-secret.
"""

from __future__ import annotations

from typing import Mapping, Union

from PHX2.stage21.constants import (
    STAGE21_ERROR_CODE_NAMES,
    STAGE21_WARNING_CODE_NAMES,
    Stage21ErrorCode,
    Stage21WarningCode,
)


_ALL_ERROR_CODE_VALUES: frozenset[str] = frozenset(
    member.value for member in Stage21ErrorCode
)

_ALL_WARNING_CODE_VALUES: frozenset[str] = frozenset(
    member.value for member in Stage21WarningCode
)


# ---------------------------------------------------------------------------
# Locked error-code -> family mapping
# ---------------------------------------------------------------------------
#
# Each Stage 21 code is owned by exactly one Stage 21 exception
# family. The registry test asserts:
#   * every Stage21ErrorCode value appears in this mapping;
#   * no code appears in two families.


_CODE_TO_FAMILY: Mapping[str, str] = {
    # config codes
    # E2105 (allowlist_parser_invalid_token) is a config-family
    # concern: the allowlist tokens themselves are non-secret
    # operator identifiers; only the env-var *value* surface is
    # secret-class.
    "E2100": "config",
    "E2101": "config",
    "E2102": "config",
    "E2105": "config",
    # secret-handling codes
    "E2103": "secret",
    "E2104": "secret",
    # boundary codes (manifest-writer path / artifact path violations)
    "E2106": "boundary",
    # reserved (not actively raised in 21.1; mapped for the
    # registry test so a future sub-stage cannot accidentally raise
    # a duplicate code in a different family)
    "E2110": "telemetry",
    "E2111": "telemetry",
    "E2112": "telemetry",
    "E2113": "telemetry",
    "E2120": "provider_contract",
    "E2121": "provider_contract",
    "E2122": "provider_contract",
    "E2130": "transport_contract",
    "E2131": "transport_contract",
    "E2132": "transport_contract",
    "E2140": "telemetry",
    "E2141": "telemetry",
}


# ---------------------------------------------------------------------------
# Exception base + sub-classes
# ---------------------------------------------------------------------------


class Stage21Error(Exception):
    """Base type for every Stage 21 closed-set exception.

    Carries a Stage 21 error code in ``.code`` (always a string) and
    a non-secret detail string in ``.detail``. The code must be a
    member of ``Stage21ErrorCode``; the constructor rejects any
    out-of-range string with a ``ValueError`` so the surface stays
    closed.

    Sub-classes (``Stage21ConfigError`` / ``Stage21SecretError`` /
    ...) constrain the accepted code subset to their family.
    """

    _ALLOWED_FAMILIES: tuple[str, ...] = ()
    # When a sub-class declares ``_ALLOWED_FAMILIES``, the
    # constructor restricts ``code`` to codes whose family appears
    # in that tuple. The base class leaves the tuple empty, which
    # means "any code in Stage21ErrorCode is allowed".

    def __init__(
        self,
        code: Union[Stage21ErrorCode, str],
        detail: str = "",
    ) -> None:
        if isinstance(code, Stage21ErrorCode):
            code_value = code.value
        else:
            code_value = code
            if code_value not in _ALL_ERROR_CODE_VALUES:
                raise ValueError(
                    f"Stage21 error code {code_value!r} is not in the "
                    f"closed set"
                )
        family = _CODE_TO_FAMILY[code_value]
        if self._ALLOWED_FAMILIES and family not in self._ALLOWED_FAMILIES:
            raise ValueError(
                f"Stage21 code {code_value!r} belongs to family "
                f"{family!r}; {type(self).__name__} only accepts "
                f"{self._ALLOWED_FAMILIES!r}"
            )
        self.code: str = code_value
        self.detail: str = detail
        name = STAGE21_ERROR_CODE_NAMES[code_value]
        if detail:
            message = f"[{code_value}] {name}: {detail}"
        else:
            message = f"[{code_value}] {name}"
        super().__init__(message)


class Stage21ConfigError(Stage21Error):
    """Raised when Stage 21 config / env loading fails closed.

    Accepts codes whose family is ``config``: E2100, E2101,
    E2102, E2105. E2105 (allowlist token validation) is a config
    concern because allowlist tokens are non-secret operator
    identifiers; only env-var *values* are secret-class.
    """

    _ALLOWED_FAMILIES = ("config",)


class Stage21SecretError(Stage21Error):
    """Raised when a Stage 21 secret-handling invariant is violated.

    Accepts codes whose family is ``secret``: E2103, E2104. The
    constructor's ``detail`` field must be non-secret -- callers
    pass only the name of the offending field, never the value.
    """

    _ALLOWED_FAMILIES = ("secret",)


class Stage21BoundaryError(Stage21Error):
    """Raised when a Stage 21 boundary invariant is violated.

    Accepts codes whose family is ``boundary``: E2106. Used by the
    manifest / artifact writer skeletons to reject unsafe target
    paths.
    """

    _ALLOWED_FAMILIES = ("boundary",)


class Stage21TelemetryError(Stage21Error):
    """Raised when a Stage 21 telemetry contract is violated.

    Accepts codes whose family is ``telemetry``: E2110..E2113,
    E2140, E2141. 21.1 itself does not raise any telemetry code;
    the family is declared here so the registry test can lock the
    code -> family mapping ahead of 21.2.
    """

    _ALLOWED_FAMILIES = ("telemetry",)


class Stage21ProviderContractError(Stage21Error):
    """Raised when a provider contract invariant is violated.

    Accepts codes whose family is ``provider_contract``: E2120,
    E2121, E2122. 21.1 ships only the contract types and a fake
    test implementation; the family is reserved for the Stage 21.3
    live adapter.
    """

    _ALLOWED_FAMILIES = ("provider_contract",)


class Stage21TransportContractError(Stage21Error):
    """Raised when a transport contract invariant is violated.

    Accepts codes whose family is ``transport_contract``: E2130,
    E2131, E2132. 21.1 ships only the contract types and a fake
    test implementation; the family is reserved for the Stage 21.4
    private-preview transport.
    """

    _ALLOWED_FAMILIES = ("transport_contract",)


# ---------------------------------------------------------------------------
# Warning helpers
# ---------------------------------------------------------------------------


def warning_name_for(code: Union[Stage21WarningCode, str]) -> str:
    """Resolve a Stage 21 warning code to its snake_case name.

    The Stage 21 telemetry writers emit warnings as ``(code, name)``
    pairs; this helper is the single canonical lookup.
    """

    if isinstance(code, Stage21WarningCode):
        value = code.value
    else:
        value = code
        if value not in _ALL_WARNING_CODE_VALUES:
            raise ValueError(
                f"Stage21 warning code {value!r} is not in the "
                f"closed set"
            )
    return STAGE21_WARNING_CODE_NAMES[value]


__all__ = [
    "Stage21BoundaryError",
    "Stage21ConfigError",
    "Stage21Error",
    "Stage21ProviderContractError",
    "Stage21SecretError",
    "Stage21TelemetryError",
    "Stage21TransportContractError",
    "warning_name_for",
]
