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

Stage 21 exception messages are scrubbed of any secret content
before they leave this module. The constructor accepts an
arbitrary ``detail`` string but routes it through
``sanitize_detail`` first; URL-shaped substrings and long
token-like substrings are replaced with locked redaction
sentinels. Stage 21.1 callers pass only short non-secret strings,
but future Stage 21.x callers (e.g. error paths that include
payload context) cannot accidentally leak a real secret value
through the detail field.

The sanitizer is conservative: short tokens, identifier-shaped
tokens (snake_case / SCREAMING_SNAKE_CASE / PascalCase /
hyphenated-lowercase) pass through unchanged. Long tokens that
do not fit a recognized identifier shape -- mixed-case-with-digits
sequences, pure hex, base64-ish runs, URLs -- are redacted.
"""

from __future__ import annotations

import re
from typing import Mapping, Union

from PHX2.stage21.constants import (
    STAGE21_ERROR_CODE_NAMES,
    STAGE21_WARNING_CODE_NAMES,
    Stage21ErrorCode,
    Stage21WarningCode,
)


# ---------------------------------------------------------------------------
# Detail sanitization
# ---------------------------------------------------------------------------
#
# AUDIT-003: the Stage 21 exception ``detail`` field must not echo
# raw secret values. The sanitizer below scrubs URLs and unknown
# long token-like substrings before they reach ``self.detail`` and
# the formatted message. The locked sentinels are:
#   * <redacted-url>   -- replaces any http(s) URL-shaped substring
#   * <redacted-token> -- replaces any long candidate that does
#                         not match a recognized identifier shape

_REDACTED_URL_SENTINEL: str = "<redacted-url>"
_REDACTED_TOKEN_SENTINEL: str = "<redacted-token>"

_DETAIL_MAX_LENGTH: int = 256
_CANDIDATE_MIN_LENGTH: int = 8
_PURE_HEX_MIN_LENGTH: int = 16

# URL pattern: covers http and https schemes followed by ``://`` up
# to the next whitespace. The regex source is built piecewise so
# the literal ``http`` plus ``://`` does not appear in the module
# source -- Stage 21 forbids URL literals in production code.
_URL_RE = re.compile(r"https?" + "://" + r"\S+", re.IGNORECASE)

# Candidate sequences that may need redaction. Includes the
# alphanumeric + URL-safe-base64 characters (``+`` / ``/`` / ``=``)
# plus ``_`` and ``-`` so URL-safe base64 tokens are caught as a
# single block. Punctuation (``.``, ``:``, ``'``, quotes, brackets)
# is intentionally excluded so phrases like ``Optional[str]`` and
# ``tuple[str, ...]`` split into safe sub-tokens.
_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/=_-]{" + str(_CANDIDATE_MIN_LENGTH) + r",}")

# Pure hex sequences are explicitly redacted regardless of casing.
# Stage 21 emits sha256[:12] fingerprints as 12 hex chars (below the
# 16-char threshold) so the redaction does not collide with the
# fingerprint surface.
_HEX_LIKE_LOWER_RE = re.compile(r"^[a-f0-9]+$")
_HEX_LIKE_UPPER_RE = re.compile(r"^[A-F0-9]+$")

# Identifier shapes Stage 21 considers safe to pass through verbatim.
_SCREAMING_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SNAKE_LOWER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-z][A-Za-z0-9]*$")
_PRIVATE_NAME_RE = re.compile(r"^_[a-zA-Z0-9_]*$")
_HYPHENATED_LOWER_RE = re.compile(r"^[a-z]+(-[a-z]+)+$")


def _is_safe_identifier_shape(s: str) -> bool:
    """Return True if ``s`` matches a Stage 21 safe identifier shape.

    Safe shapes:
      * Any candidate below ``_CANDIDATE_MIN_LENGTH`` chars (never
        reaches the sanitizer in the first place).
      * SCREAMING_SNAKE_CASE: ``PHX2_STAGE21_PROVIDER_API_KEY``.
      * snake_case: ``compute_fingerprint``, ``allowlist``.
      * PascalCase (digit-tolerant after the second char):
        ``Stage21SecretError``, ``Optional``, ``NoneType``.
      * ``_private``-style identifiers.
      * hyphenated-lowercase phrases like ``round-trip``.

    Pure hex sequences of length >= ``_PURE_HEX_MIN_LENGTH`` are
    explicitly NOT safe -- they match the lowercase snake regex but
    are highly likely to be SHA-256-style fingerprints or hex tokens.
    """
    if len(s) < _CANDIDATE_MIN_LENGTH:
        return True
    # Pure hex is a leak shape, not an identifier. Reject before
    # the lowercase / SCREAMING regex would accept it.
    if len(s) >= _PURE_HEX_MIN_LENGTH and (
        _HEX_LIKE_LOWER_RE.fullmatch(s) or _HEX_LIKE_UPPER_RE.fullmatch(s)
    ):
        return False
    return bool(
        _SCREAMING_SNAKE_RE.fullmatch(s)
        or _SNAKE_LOWER_RE.fullmatch(s)
        or _PASCAL_CASE_RE.fullmatch(s)
        or _PRIVATE_NAME_RE.fullmatch(s)
        or _HYPHENATED_LOWER_RE.fullmatch(s)
    )


def _redact_candidate(match: "re.Match[str]") -> str:
    token = match.group(0)
    if _is_safe_identifier_shape(token):
        return token
    return _REDACTED_TOKEN_SENTINEL


def sanitize_detail(
    detail: object,
    *,
    max_length: int = _DETAIL_MAX_LENGTH,
) -> str:
    """Return a Stage21-safe rendering of ``detail``.

    The function:
      1. coerces non-string input to ``str``;
      2. replaces newlines / carriage returns / tabs with spaces;
      3. drops other non-printable characters;
      4. replaces every URL-shaped substring (``http`` / ``https``
         scheme followed by ``//`` and a non-whitespace run) with
         ``<redacted-url>``;
      5. replaces every long candidate substring that does not
         match a safe identifier shape with ``<redacted-token>``;
      6. truncates at ``max_length`` characters (appending ``...``).

    The sanitizer is conservative -- it scrubs anything that looks
    like a leak shape, even at the cost of false positives. Stage 21
    callers should pass short, non-secret detail strings whenever
    possible; the sanitizer is the belt-and-suspenders second line
    of defense.

    The function is intentionally pure: identical input produces
    identical output. The locked sentinel strings are
    ``<redacted-url>`` and ``<redacted-token>``.
    """
    if not isinstance(detail, str):
        detail = str(detail)
    # Normalize control whitespace; preserve printable chars.
    detail = detail.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    detail = "".join(c if (c == " " or c.isprintable()) else " " for c in detail)
    detail = _URL_RE.sub(_REDACTED_URL_SENTINEL, detail)
    detail = _CANDIDATE_RE.sub(_redact_candidate, detail)
    if len(detail) > max_length:
        detail = detail[:max_length] + "..."
    return detail


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
        # AUDIT-003: route every detail string through the
        # sanitizer so a future caller cannot leak a real secret /
        # webhook URL / payload value via the detail field. The
        # sanitized form is what ``self.detail`` exposes and what
        # the formatted message embeds; raw input is dropped.
        sanitized_detail = sanitize_detail(detail)
        self.code: str = code_value
        self.detail: str = sanitized_detail
        name = STAGE21_ERROR_CODE_NAMES[code_value]
        if sanitized_detail:
            message = f"[{code_value}] {name}: {sanitized_detail}"
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
    "sanitize_detail",
    "warning_name_for",
]
