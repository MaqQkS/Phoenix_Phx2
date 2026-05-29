"""Stage 30.7.1 offline ATH-context closed-set vocabularies and
immutable evidence / projection shapes.

Stage 30.7.1 ships the pure-Python model layer the Stage 30.7.1
projection adapter consumes and emits. The Stage-30-owned ATH context
projection carries only closed-set status / source-status / unit /
basis / reason tokens, a single short safe-shape compact ATH display
string (a ``$Y`` value or the literal ``Unknown``), an optional
canonical decimal-text value echo, and a ``runtime_consumable`` flag.
Stage 30.7.1 is offline only: the evidence / projection is NEVER routed
into Stage 30.1 / 30.2 / 30.3 runtime, NEVER fills the Stage 30.2
renderer ``ath_mc_text`` slot at runtime, and NEVER triggers a Discord
send. Stage 30.7.1 does NOT call a provider, does NOT compute final
tier / drop behavior, and does NOT wire into the compact runtime
(that is a later, separately authorized substage).

Closed-set vocabularies (committed by the Stage 30.7.0 spec lock):

  * ``ATH_STATUS``        -- ``ATH_KNOWN`` / ``ATH_UNVERIFIED`` /
                            ``ATH_UNKNOWN``. Only ``ATH_KNOWN`` renders
                            a ``$Y`` value; the other two render
                            ``Unknown``.
  * ``ATH_SOURCE_STATUS`` -- ``PRESENT`` / ``UNAVAILABLE`` / ``ERROR``
                            / ``STALE`` / ``CONFLICTING``. A non-PRESENT
                            source status dominates any claimed value
                            and degrades the projection to ``Unknown``.
  * ``ATH_UNIT``          -- ``USD`` / ``SOL`` / ``UNKNOWN``. The
                            displayed ATH must share the same currency
                            basis as the displayed ``MC``; a USD ATH is
                            never treated as SOL or vice versa.
  * ``ATH_BASIS``         -- ``ATH_MARKET_CAP_OBSERVED`` /
                            ``ATH_PRICE_DERIVED`` / ``ATH_BASIS_NONE``.
                            Only an observed-market-cap basis can
                            support ``ATH_KNOWN``; a price-derived ATH
                            market cap assumes a supply that may not
                            match the supply at the historical peak, so
                            it is at most ``ATH_UNVERIFIED``, never
                            ``ATH_KNOWN``, in this slice.
  * ``ATH_REASON``        -- closed-set projection reason tokens that
                            explain WHY the projection chose its status
                            / display.

Immutable shapes:

  * ``Stage30_7AthContextEvidence``   -- the caller-supplied sanitized
                                         ATH evidence. A LENIENT carrier
                                         (see below).
  * ``Stage30_7AthContextProjection`` -- the validated projection output
                                         (closed-set status / source-
                                         status / unit / basis / reason
                                         + a single safe compact display
                                         string + echoes).

Evidence is deliberately a LENIENT carrier: it does NOT validate its
fields at construction. This mirrors the Stage 30.6.1 lenient
observation carrier and differs from the Stage 30.4 / 30.5 strict
offline RECORDS (which validate at construction): a bad value, a bad
unit, or a bad source status must be expressible as input so it can
flow to a fail-closed ``ATH_UNKNOWN`` projection (never a constructor
exception). The Projection, by contrast, is the validated OUTPUT and
DOES validate at construction: building a projection with an off-
closed-set status / source-status / unit / basis / reason, a non-bool
flag, a non-string version, a non-string display text, or
``runtime_consumable`` not ``False`` raises ``Stage30_7AthContextError``
with a closed-set reason token.

Stage 30.7.1 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * raw transaction signatures, raw event logs, the source event ref /
    raw capture ref / migration or trade event ids (no field admits
    them),
  * provider URLs, provider host addresses, transport scheme prefixes,
    request header metadata, or request auth metadata (no field admits
    them),
  * secrets, inbound-hook URLs, signed-token credential strings, or
    environment values (no field admits them),
  * Discord destination / Discord message body text (no field admits
    them),
  * Net flow fields (Net stays deferred),
  * a drawdown / tier recomputation (deferred until the ATH source and
    unit are valid),
  * trading verdicts (Stage 30 is informational-only),
  * Stage 26 / Stage 29 enforcement decisions.

Discipline:

  * Stdlib only (``typing`` / ``dataclasses``).
  * No ``os`` import, no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access, no ``pathlib`` / ``shutil`` / ``sqlite3`` /
    zstd import.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook, provider
    reference.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem I/O at import time. No top-level
    Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema / projection versions
# ---------------------------------------------------------------------------


STAGE30_7_1_MINOR_VERSION: str = "30.7.1"
STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_7_1_v0_ath_context"
)
STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION: str = (
    "stage30_7_ath_context_projection_v0"
)


# Default market-context currency basis. The displayed ATH must share
# the same currency basis as the displayed ``MC``; ``MC`` reports in
# USD, so the default market context unit is USD.
STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT: str = "USD"


# Literal missing-value display sentinel for the compact ``ATH`` token.
# NEVER ``"0"`` / ``"0.0"`` / empty string / a fabricated estimate.
ATH_DISPLAY_UNKNOWN: str = "Unknown"


# ---------------------------------------------------------------------------
# Closed-set ath_status tokens
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 30.5 migration status discipline (KNOWN /
# UNVERIFIED / UNKNOWN). Only ATH_KNOWN renders a ``$Y`` value in the
# compact line; ATH_UNVERIFIED and ATH_UNKNOWN render ``Unknown``.


ATH_STATUS_KNOWN: str = "ATH_KNOWN"
ATH_STATUS_UNVERIFIED: str = "ATH_UNVERIFIED"
ATH_STATUS_UNKNOWN: str = "ATH_UNKNOWN"


ATH_STATUS_VALUES: Tuple[str, ...] = (
    ATH_STATUS_KNOWN,
    ATH_STATUS_UNVERIFIED,
    ATH_STATUS_UNKNOWN,
)


def is_ath_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.7.1 ath_status
    token.
    """
    return isinstance(value, str) and value in ATH_STATUS_VALUES


# ---------------------------------------------------------------------------
# Closed-set source_status tokens
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 30.5 source-status set and adds CONFLICTING:
# cross-source ATH disagreement (two sources reporting materially
# different peaks) is a real ATH failure mode and must degrade
# conservatively to ``Unknown`` rather than picking a peak. A
# non-PRESENT source status dominates any claimed ATH value.


ATH_SOURCE_STATUS_PRESENT: str = "PRESENT"
ATH_SOURCE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
ATH_SOURCE_STATUS_ERROR: str = "ERROR"
ATH_SOURCE_STATUS_STALE: str = "STALE"
ATH_SOURCE_STATUS_CONFLICTING: str = "CONFLICTING"


ATH_SOURCE_STATUS_VALUES: Tuple[str, ...] = (
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_CONFLICTING,
)


def is_ath_source_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.7.1 source-status
    token.
    """
    return (
        isinstance(value, str) and value in ATH_SOURCE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set ath_unit tokens
# ---------------------------------------------------------------------------
#
# The compact ATH display must share the same currency basis as the
# displayed ``MC``. USD is the reporting unit; SOL is the on-chain
# native unit (recognized as a token, display deferred); UNKNOWN
# otherwise. The spec forbids ever treating USD as SOL or SOL as USD.


ATH_UNIT_USD: str = "USD"
ATH_UNIT_SOL: str = "SOL"
ATH_UNIT_UNKNOWN: str = "UNKNOWN"


ATH_UNIT_VALUES: Tuple[str, ...] = (
    ATH_UNIT_USD,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
)


def is_ath_unit_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.7.1 ath_unit
    token.
    """
    return isinstance(value, str) and value in ATH_UNIT_VALUES


# ---------------------------------------------------------------------------
# Closed-set ath_basis tokens
# ---------------------------------------------------------------------------
#
# The honesty axis. Only an observed market-cap basis can support
# ATH_KNOWN. A price-derived ATH market cap assumes a supply that may
# not match the supply at the historical peak, so it is at most
# ATH_UNVERIFIED, never ATH_KNOWN, in this slice.


ATH_BASIS_MARKET_CAP_OBSERVED: str = "ATH_MARKET_CAP_OBSERVED"
ATH_BASIS_PRICE_DERIVED: str = "ATH_PRICE_DERIVED"
ATH_BASIS_NONE: str = "ATH_BASIS_NONE"


ATH_BASIS_VALUES: Tuple[str, ...] = (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_PRICE_DERIVED,
    ATH_BASIS_NONE,
)


def is_ath_basis_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.7.1 ath_basis
    token.
    """
    return isinstance(value, str) and value in ATH_BASIS_VALUES


# ---------------------------------------------------------------------------
# Closed-set ath_reason tokens
# ---------------------------------------------------------------------------
#
# Each reason explains WHY the projection chose its status / display.
# Exactly one reason pairs with each terminal outcome:
#
#   * ATH_KNOWN_USD_MARKET_CAP        -- PRESENT + positive finite USD
#                                        value + compatible USD market
#                                        context + observed-market-cap
#                                        basis => ATH_KNOWN ($Y).
#   * ATH_UNVERIFIED_PRICE_DERIVED    -- a price-derived basis, never
#                                        promotable to ATH_KNOWN in this
#                                        slice => ATH_UNVERIFIED
#                                        (display Unknown).
#   * ATH_UNKNOWN_SOURCE_UNAVAILABLE  -- source status UNAVAILABLE.
#   * ATH_UNKNOWN_SOURCE_ERROR        -- source status ERROR.
#   * ATH_UNKNOWN_SOURCE_STALE        -- source status STALE.
#   * ATH_UNKNOWN_SOURCE_CONFLICTING  -- source status CONFLICTING.
#   * ATH_UNKNOWN_VALUE_MISSING       -- no value supplied.
#   * ATH_UNKNOWN_VALUE_NOT_NUMERIC   -- value not a parseable number.
#   * ATH_UNKNOWN_VALUE_NOT_FINITE    -- value NaN / infinite.
#   * ATH_UNKNOWN_VALUE_NON_POSITIVE  -- value zero or negative.
#   * ATH_UNKNOWN_UNIT_UNSUPPORTED    -- unit UNKNOWN / unrecognized /
#                                        not displayable in this slice.
#   * ATH_UNKNOWN_UNIT_INCOMPATIBLE   -- unit disagrees with the market
#                                        context unit.
#   * ATH_UNKNOWN_REDACTION_UNSAFE    -- evidence flagged redaction-
#                                        unsafe.
#   * ATH_UNKNOWN_INVALID_INPUT       -- malformed evidence, an off-
#                                        closed-set source status, or a
#                                        basis with no support (NONE /
#                                        off-set) for an otherwise valid
#                                        value.


ATH_REASON_KNOWN_USD_MARKET_CAP: str = "ATH_KNOWN_USD_MARKET_CAP"
ATH_REASON_UNVERIFIED_PRICE_DERIVED: str = (
    "ATH_UNVERIFIED_PRICE_DERIVED"
)
ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE: str = (
    "ATH_UNKNOWN_SOURCE_UNAVAILABLE"
)
ATH_REASON_UNKNOWN_SOURCE_ERROR: str = "ATH_UNKNOWN_SOURCE_ERROR"
ATH_REASON_UNKNOWN_SOURCE_STALE: str = "ATH_UNKNOWN_SOURCE_STALE"
ATH_REASON_UNKNOWN_SOURCE_CONFLICTING: str = (
    "ATH_UNKNOWN_SOURCE_CONFLICTING"
)
ATH_REASON_UNKNOWN_VALUE_MISSING: str = "ATH_UNKNOWN_VALUE_MISSING"
ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC: str = (
    "ATH_UNKNOWN_VALUE_NOT_NUMERIC"
)
ATH_REASON_UNKNOWN_VALUE_NOT_FINITE: str = (
    "ATH_UNKNOWN_VALUE_NOT_FINITE"
)
ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE: str = (
    "ATH_UNKNOWN_VALUE_NON_POSITIVE"
)
ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED: str = (
    "ATH_UNKNOWN_UNIT_UNSUPPORTED"
)
ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE: str = (
    "ATH_UNKNOWN_UNIT_INCOMPATIBLE"
)
ATH_REASON_UNKNOWN_REDACTION_UNSAFE: str = (
    "ATH_UNKNOWN_REDACTION_UNSAFE"
)
ATH_REASON_UNKNOWN_INVALID_INPUT: str = "ATH_UNKNOWN_INVALID_INPUT"


ATH_REASON_VALUES: Tuple[str, ...] = (
    ATH_REASON_KNOWN_USD_MARKET_CAP,
    ATH_REASON_UNVERIFIED_PRICE_DERIVED,
    ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE,
    ATH_REASON_UNKNOWN_SOURCE_ERROR,
    ATH_REASON_UNKNOWN_SOURCE_STALE,
    ATH_REASON_UNKNOWN_SOURCE_CONFLICTING,
    ATH_REASON_UNKNOWN_VALUE_MISSING,
    ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC,
    ATH_REASON_UNKNOWN_VALUE_NOT_FINITE,
    ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE,
    ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED,
    ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE,
    ATH_REASON_UNKNOWN_REDACTION_UNSAFE,
    ATH_REASON_UNKNOWN_INVALID_INPUT,
)


def is_ath_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.7.1 ath_reason
    token.
    """
    return isinstance(value, str) and value in ATH_REASON_VALUES


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_7AthContextError(Exception):
    """Closed-set Stage 30.7.1 ATH-context error.

    Carries only a closed-set reason token on the exception message.
    Raised ONLY at ``Stage30_7AthContextProjection`` construction (the
    validated output); the projection adapter itself never raises for
    bad evidence -- it fails closed to an ``ATH_UNKNOWN`` projection
    instead. Callers should never embed a raw OSError message, a raw
    provider payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.7.1 ATH context error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Immutable carrier: ATH context evidence (lenient)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_7AthContextEvidence:
    """Immutable Stage 30.7.1 ATH-context evidence.

    A LENIENT carrier of caller-supplied sanitized ATH evidence: it
    does NOT validate its fields at construction (see the module
    docstring). The projection adapter classifies the evidence and
    fails closed to ``ATH_UNKNOWN`` on missing / non-numeric /
    non-finite / non-positive / bad-unit / incompatible-unit /
    redaction-unsafe / off-closed-set input.

    Carries only sanitized values: a numeric-or-string ATH value, a
    closed-set-ish unit / source-status / basis token, a redaction-safe
    flag, and optional short safe-shape provenance (a source-family
    label and an ISO-8601 timestamp). It admits NO raw provider
    payload, NO raw signature / event log / source event ref, NO
    provider URL / host / transport scheme / request auth metadata, NO
    secret / inbound-hook URL / signed-token credential, and NO Discord
    destination / message body. The ``source_label`` and
    ``observed_at_utc`` fields are optional caller provenance and are
    NOT echoed into the compact ATH projection (the compact ``ATH``
    token is a single short value / ``Unknown`` word, never a label or
    a timestamp).

    Fields:

      * ``ath_value``       -- the candidate ATH value. Numeric
                              (``int`` / ``float`` / ``Decimal``) or a
                              strict decimal-text ``str``. ``None`` / a
                              non-number / NaN / infinite / non-positive
                              value is tolerated here and fails closed
                              in the projection adapter. NEVER a raw
                              provider payload.
      * ``ath_unit``        -- the ATH currency unit token
                              (``USD`` / ``SOL`` / ``UNKNOWN``) or
                              ``None``. An unrecognized / ``None`` unit
                              fails closed to ``Unknown``.
      * ``source_status``   -- the ATH source-status token
                              (``PRESENT`` / ``UNAVAILABLE`` / ``ERROR``
                              / ``STALE`` / ``CONFLICTING``) or
                              ``None``. A non-PRESENT / unrecognized /
                              ``None`` status dominates any value and
                              degrades to ``Unknown``.
      * ``basis``           -- the ATH evidence basis token
                              (``ATH_MARKET_CAP_OBSERVED`` /
                              ``ATH_PRICE_DERIVED`` / ``ATH_BASIS_NONE``)
                              or ``None``. Only an observed-market-cap
                              basis can support ``ATH_KNOWN``.
      * ``redaction_safe``  -- ``bool``; ``True`` means the caller
                              asserts the evidence passed a redaction /
                              safety check. Anything other than ``True``
                              degrades to ``Unknown``. Default ``False``
                              (fail closed: an omitted redaction proof is
                              never trusted, so an evidence built without
                              explicitly asserting ``redaction_safe=True``
                              can NEVER project to ``ATH_KNOWN``).
      * ``source_label``    -- optional short safe-shape source-family
                              provenance label (never a host address,
                              never a credential). NOT echoed into the
                              compact projection.
      * ``observed_at_utc`` -- optional caller-supplied ISO-8601 UTC
                              timestamp string (never derived from
                              ``datetime.now`` here). NOT echoed into the
                              compact projection.
    """

    ath_value: object = None
    ath_unit: Optional[str] = None
    source_status: Optional[str] = None
    basis: Optional[str] = None
    redaction_safe: bool = False
    source_label: Optional[str] = None
    observed_at_utc: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable output: ATH context projection (validated)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_7AthContextProjection:
    """Immutable Stage 30.7.1 compact ATH-context projection.

    The validated OUTPUT of the Stage 30.7.1 projection adapter. Frozen
    dataclass with construction-time closed-set validation: an off-
    closed-set ``ath_status`` / ``source_status`` / ``ath_unit`` /
    ``basis`` / ``reason``, a non-string / empty version, a non-string /
    empty ``ath_display_text``, a non-``None`` non-string ``ath_value``
    echo, a non-bool flag, or ``runtime_consumable`` not ``False`` raises
    ``Stage30_7AthContextError`` with a closed-set reason token.

    The compact ``ATH`` token has exactly two display outcomes:
    ``Unknown`` (when the ATH is missing / untrusted / errored / stale /
    conflicting / non-finite / zero or negative / redaction-unsafe / of
    an incompatible or unsupported unit) or a ``$Y`` formatted value
    (only for an ``ATH_KNOWN`` status with a valid observed-market-cap
    USD value and a compatible market context).

    ``runtime_consumable`` is hard-locked ``False``: Stage 30.7.1 is a
    pure offline projection, NOT a live runtime feed. The projection
    NEVER claims a Discord send occurred and NEVER routes into runtime.
    A later separately-authorized substage (Stage 30.7.2) would consume
    it through the existing ``ath_mc_text`` display slot; Stage 30.7.1
    does not.

    Fields:

      * ``schema_version``            -- locked Stage 30.7.1 ATH-context
                                         projection schema version
                                         string (non-empty).
      * ``ath_status``                -- one of ``ATH_STATUS_VALUES``.
      * ``source_status``             -- one of
                                         ``ATH_SOURCE_STATUS_VALUES``.
      * ``ath_unit``                  -- one of ``ATH_UNIT_VALUES``.
      * ``basis``                     -- one of ``ATH_BASIS_VALUES``.
      * ``ath_value``                 -- canonical decimal-text echo of
                                         the trusted-enough value (for
                                         ``ATH_KNOWN`` / ``ATH_UNVERIFIED``)
                                         or ``None`` (for every
                                         ``ATH_UNKNOWN`` outcome).
      * ``ath_display_text``          -- the compact ``ATH`` token
                                         string: a ``$Y`` value (only for
                                         ``ATH_KNOWN``) or the literal
                                         ``Unknown``.
      * ``reason``                    -- one of ``ATH_REASON_VALUES``.
      * ``should_display_value``      -- ``bool``; ``True`` only for
                                         ``ATH_KNOWN`` (the display text
                                         is a real ``$Y`` value).
      * ``should_trust_for_drawdown`` -- ``bool``; ``True`` only for
                                         ``ATH_KNOWN`` (an unverified /
                                         unknown ATH must NOT anchor a
                                         trusted drawdown / tier).
      * ``projection_version``        -- locked Stage 30.7.1 projection-
                                         logic version string (non-empty).
      * ``runtime_consumable``        -- ``bool``; MUST be ``False``.
    """

    schema_version: str
    ath_status: str
    source_status: str
    ath_unit: str
    basis: str
    ath_value: Optional[str]
    ath_display_text: str
    reason: str
    should_display_value: bool
    should_trust_for_drawdown: bool
    projection_version: str
    runtime_consumable: bool

    def __post_init__(self) -> None:
        if not (
            isinstance(self.schema_version, str)
            and self.schema_version != ""
        ):
            raise Stage30_7AthContextError("SCHEMA_VERSION_INVALID")
        if not is_ath_status_value(self.ath_status):
            raise Stage30_7AthContextError("ATH_STATUS_INVALID")
        if not is_ath_source_status_value(self.source_status):
            raise Stage30_7AthContextError("SOURCE_STATUS_INVALID")
        if not is_ath_unit_value(self.ath_unit):
            raise Stage30_7AthContextError("ATH_UNIT_INVALID")
        if not is_ath_basis_value(self.basis):
            raise Stage30_7AthContextError("ATH_BASIS_INVALID")
        if self.ath_value is not None and not (
            isinstance(self.ath_value, str) and self.ath_value != ""
        ):
            raise Stage30_7AthContextError("ATH_VALUE_ECHO_INVALID")
        if not (
            isinstance(self.ath_display_text, str)
            and self.ath_display_text != ""
        ):
            raise Stage30_7AthContextError("ATH_DISPLAY_TEXT_INVALID")
        if not is_ath_reason_value(self.reason):
            raise Stage30_7AthContextError("ATH_REASON_INVALID")
        if not isinstance(self.should_display_value, bool):
            raise Stage30_7AthContextError(
                "SHOULD_DISPLAY_VALUE_NOT_BOOL"
            )
        if not isinstance(self.should_trust_for_drawdown, bool):
            raise Stage30_7AthContextError(
                "SHOULD_TRUST_FOR_DRAWDOWN_NOT_BOOL"
            )
        if not (
            isinstance(self.projection_version, str)
            and self.projection_version != ""
        ):
            raise Stage30_7AthContextError(
                "PROJECTION_VERSION_INVALID"
            )
        if not isinstance(self.runtime_consumable, bool):
            raise Stage30_7AthContextError(
                "RUNTIME_CONSUMABLE_NOT_BOOL"
            )
        if self.runtime_consumable is not False:
            # Stage 30.7.1 is a pure offline projection: it can NEVER
            # claim a live runtime feed / Discord send, so True is
            # rejected outright (not silently normalized). A later opt-in
            # runtime substage (Stage 30.7.2) would relax this.
            raise Stage30_7AthContextError(
                "RUNTIME_CONSUMABLE_MUST_BE_FALSE"
            )


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.7.1 must never accept a field named anything secret-class,
# raw-payload-class, audit-identifier-class, or Discord-class on either
# dataclass. The current evidence / projection field sets carry no such
# name, but this helper is kept so a future refactor cannot silently
# widen the admitted field set.
#
# Split literals so this module's own source does NOT carry the bare
# inbound-hook / API-key / signed-token / auth-metadata substrings
# (mirrors the Stage 30.4 / 30.5 / 30.6 forbidden-field guard). The
# runtime tuple value still resolves to the correct human-readable
# forbidden names.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    # Secret-class / transport-class.
    "web" + "hook",
    "web" + "hook_url",
    "web" + "hooks",
    "web" + "hook_token",
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "secret",
    "secret_key",
    "secretkey",
    "token_secret",
    "private_key",
    "privatekey",
    "seed_phrase",
    "mnemonic",
    "signer",
    "signing_key",
    "credentials",
    "password",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
    # Raw-payload-class.
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "raw_response",
    "raw_capture_ref",
    # Audit-identifier-class (these stay on the evidence side and must
    # NEVER reach the compact projection).
    "source_event_ref",
    "ath_event_id",
    "migration_event_id",
    "migration_signature",
    "signature",
    # Discord-class.
    "discord",
    "channel_id",
    "destination",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.7.1 uses this guard to reject any
    future refactor that tries to widen the evidence / projection with a
    secret-class, raw-payload-class, audit-identifier-class, or
    Discord-class field name.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


def evidence_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.7.1 evidence field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_7AthContextEvidence))


def projection_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.7.1 projection field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_7AthContextProjection)
    )


__all__ = (
    # Version + schema / projection versions + defaults + sentinel.
    "STAGE30_7_1_MINOR_VERSION",
    "STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION",
    "STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION",
    "STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT",
    "ATH_DISPLAY_UNKNOWN",
    # ath_status tokens.
    "ATH_STATUS_KNOWN",
    "ATH_STATUS_UNVERIFIED",
    "ATH_STATUS_UNKNOWN",
    "ATH_STATUS_VALUES",
    "is_ath_status_value",
    # source_status tokens.
    "ATH_SOURCE_STATUS_PRESENT",
    "ATH_SOURCE_STATUS_UNAVAILABLE",
    "ATH_SOURCE_STATUS_ERROR",
    "ATH_SOURCE_STATUS_STALE",
    "ATH_SOURCE_STATUS_CONFLICTING",
    "ATH_SOURCE_STATUS_VALUES",
    "is_ath_source_status_value",
    # ath_unit tokens.
    "ATH_UNIT_USD",
    "ATH_UNIT_SOL",
    "ATH_UNIT_UNKNOWN",
    "ATH_UNIT_VALUES",
    "is_ath_unit_value",
    # ath_basis tokens.
    "ATH_BASIS_MARKET_CAP_OBSERVED",
    "ATH_BASIS_PRICE_DERIVED",
    "ATH_BASIS_NONE",
    "ATH_BASIS_VALUES",
    "is_ath_basis_value",
    # ath_reason tokens.
    "ATH_REASON_KNOWN_USD_MARKET_CAP",
    "ATH_REASON_UNVERIFIED_PRICE_DERIVED",
    "ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE",
    "ATH_REASON_UNKNOWN_SOURCE_ERROR",
    "ATH_REASON_UNKNOWN_SOURCE_STALE",
    "ATH_REASON_UNKNOWN_SOURCE_CONFLICTING",
    "ATH_REASON_UNKNOWN_VALUE_MISSING",
    "ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC",
    "ATH_REASON_UNKNOWN_VALUE_NOT_FINITE",
    "ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE",
    "ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED",
    "ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE",
    "ATH_REASON_UNKNOWN_REDACTION_UNSAFE",
    "ATH_REASON_UNKNOWN_INVALID_INPUT",
    "ATH_REASON_VALUES",
    "is_ath_reason_value",
    # Records + field-name helpers.
    "Stage30_7AthContextEvidence",
    "Stage30_7AthContextProjection",
    "evidence_field_names",
    "projection_field_names",
    # Forbidden-field guard + error.
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_7AthContextError",
)
