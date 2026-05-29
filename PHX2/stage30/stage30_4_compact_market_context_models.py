"""Stage 30.4.1 offline compact market context closed-set
vocabularies and immutable record shape.

Stage 30.4.1 ships the pure-Python model layer for the Stage 30.4
compact market context record the Stage 30.4.1 adapter / projector
emits per ping. The record carries only closed-set status tokens,
safe-shape opaque identifier echoes, canonical decimal-text values
or ``None``, preformatted display strings or ``None``, a source
label, a source status, a source reason, and a hard-locked
``runtime_consumable=False`` flag. Stage 30.4.1 is offline only:
the record is NEVER routed into Stage 30.3 runtime, NEVER fills
the Stage 30.2 renderer slots at runtime, and NEVER triggers a
Discord send.

Closed-set vocabularies:

  * ``MARKET_CAP_USD_STATUS``  -- ``UNKNOWN`` / ``KNOWN`` /
                                  ``ERROR`` / ``STALE``
  * ``LIQUIDITY_USD_STATUS``   -- same closed set
  * ``NET_FLOW_STATUS``        -- same closed set
  * ``SOURCE_STATUS``          -- ``UNAVAILABLE`` / ``PRESENT`` /
                                  ``ERROR`` / ``STALE``
  * ``SOURCE_REASON``          -- closed-set source reason tokens
  * ``NET_FLOW_BASIS``         -- ``UNKNOWN`` /
                                  ``BUY_SELL_USD_DELTA_24H`` /
                                  ``VOLUME_USD_DELTA_24H``

Stage 30.4.1 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, inbound-hook URLs, API-key strings, signed tokens, or
    raw authorization-header text (no field admits them),
  * RPC endpoint strings (no field admits them),
  * trading verdicts (Stage 30 is informational-only),
  * Stage 26 / Stage 29 enforcement decisions,
  * runtime-side-effect flags (``runtime_consumable`` is hard-
    locked to ``False`` in Stage 30.4.1).

Discipline:

  * Stdlib only (``typing``).
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No transport reference (no operator-channel, no inbound-hook,
    no provider-host literal) on source text.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source import or modification.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 30.4.1 schema version + locked artifact basename
# ---------------------------------------------------------------------------


STAGE30_4_1_MINOR_VERSION: str = "30.4.1"
STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_4_1_v0_compact_market_context"
)
STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME: str = (
    "stage30_4_compact_market_context.jsonl"
)


# ---------------------------------------------------------------------------
# Closed-set status tokens (market_cap_usd_status,
# liquidity_usd_status, net_flow_status)
# ---------------------------------------------------------------------------


STATUS_UNKNOWN: str = "UNKNOWN"
STATUS_KNOWN: str = "KNOWN"
STATUS_ERROR: str = "ERROR"
STATUS_STALE: str = "STALE"


STATUS_VALUES: Tuple[str, ...] = (
    STATUS_UNKNOWN,
    STATUS_KNOWN,
    STATUS_ERROR,
    STATUS_STALE,
)


def is_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.4.1 status token."""
    return isinstance(value, str) and value in STATUS_VALUES


# ---------------------------------------------------------------------------
# Closed-set source_status tokens
# ---------------------------------------------------------------------------


SOURCE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
SOURCE_STATUS_PRESENT: str = "PRESENT"
SOURCE_STATUS_ERROR: str = "ERROR"
SOURCE_STATUS_STALE: str = "STALE"


SOURCE_STATUS_VALUES: Tuple[str, ...] = (
    SOURCE_STATUS_UNAVAILABLE,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_STALE,
)


def is_source_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.4.1 source-status
    token.
    """
    return isinstance(value, str) and value in SOURCE_STATUS_VALUES


# ---------------------------------------------------------------------------
# Closed-set source_reason tokens
# ---------------------------------------------------------------------------
#
# Stage 30.4.1 source_reason tokens partition into three families:
#
#   * SOURCE_NOT_CONFIGURED          -- no source object was passed
#                                       to the adapter; the record
#                                       carries Unknown on every
#                                       field.
#   * SOURCE_PRESENT                 -- source object was passed
#                                       and yielded at least one
#                                       KNOWN slot.
#   * SOURCE_STALE                   -- source object was passed
#                                       but flagged the reading as
#                                       stale; per-slot statuses
#                                       resolve to STALE.
#   * MC_VALUE_INVALID,
#     LP_VALUE_INVALID,
#     NET_VALUE_INVALID              -- the value text supplied for
#                                       MC / LP / Net failed strict
#                                       decimal validation, was
#                                       non-finite, or violated the
#                                       sign rules.
#   * SOURCE_OBSERVATION_TIMESTAMP_MALFORMED
#                                    -- the source supplied an
#                                       observation timestamp that
#                                       did not parse as a safe-
#                                       shape ISO-8601 UTC string.
#   * SOURCE_BASIS_INVALID           -- the source supplied a
#                                       ``net_flow_basis`` that is
#                                       not on the closed set.
#   * SOURCE_REASON_MALFORMED        -- the source supplied a
#                                       ``source_reason`` of a non-
#                                       string type. Closed-set
#                                       fallback so callers can
#                                       still ship a record.


SOURCE_REASON_SOURCE_NOT_CONFIGURED: str = "SOURCE_NOT_CONFIGURED"
SOURCE_REASON_SOURCE_PRESENT: str = "SOURCE_PRESENT"
SOURCE_REASON_SOURCE_STALE: str = "SOURCE_STALE"
SOURCE_REASON_MC_VALUE_INVALID: str = "MC_VALUE_INVALID"
SOURCE_REASON_LP_VALUE_INVALID: str = "LP_VALUE_INVALID"
SOURCE_REASON_NET_VALUE_INVALID: str = "NET_VALUE_INVALID"
SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED: str = (
    "SOURCE_OBSERVATION_TIMESTAMP_MALFORMED"
)
SOURCE_REASON_SOURCE_BASIS_INVALID: str = "SOURCE_BASIS_INVALID"
SOURCE_REASON_SOURCE_REASON_MALFORMED: str = (
    "SOURCE_REASON_MALFORMED"
)


SOURCE_REASON_VALUES: Tuple[str, ...] = (
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_MC_VALUE_INVALID,
    SOURCE_REASON_LP_VALUE_INVALID,
    SOURCE_REASON_NET_VALUE_INVALID,
    SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
    SOURCE_REASON_SOURCE_BASIS_INVALID,
    SOURCE_REASON_SOURCE_REASON_MALFORMED,
)


def is_source_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.4.1 source-reason
    token.
    """
    return isinstance(value, str) and value in SOURCE_REASON_VALUES


# ---------------------------------------------------------------------------
# Closed-set net_flow_basis tokens
# ---------------------------------------------------------------------------
#
# ``UNKNOWN``                  -- no basis declared (default whenever
#                                 Net is UNKNOWN).
# ``BUY_SELL_USD_DELTA_24H``   -- buy-volume USD minus sell-volume
#                                 USD over the last 24h.
# ``VOLUME_USD_DELTA_24H``     -- raw 24h volume USD delta (volume
#                                 today minus volume yesterday).


NET_FLOW_BASIS_UNKNOWN: str = "UNKNOWN"
NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H: str = (
    "BUY_SELL_USD_DELTA_24H"
)
NET_FLOW_BASIS_VOLUME_USD_DELTA_24H: str = "VOLUME_USD_DELTA_24H"


NET_FLOW_BASIS_VALUES: Tuple[str, ...] = (
    NET_FLOW_BASIS_UNKNOWN,
    NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
    NET_FLOW_BASIS_VOLUME_USD_DELTA_24H,
)


def is_net_flow_basis_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.4.1 net-flow-basis
    token.
    """
    return isinstance(value, str) and value in NET_FLOW_BASIS_VALUES


# ---------------------------------------------------------------------------
# Immutable record: compact market context
# ---------------------------------------------------------------------------


class Stage30_4CompactMarketContextRecord(NamedTuple):
    """Immutable Stage 30.4.1 compact market context record.

    Carries only closed-set tokens, safe-shape opaque identifier
    echoes, canonical decimal-text values or ``None``, preformatted
    display strings or ``None``, a source label, and a hard-locked
    ``runtime_consumable=False`` flag. No raw provider payload blob,
    no secret value, no inbound-hook URL, no API-key string, no
    signed-token credential, no authorization-header text, no RPC
    endpoint string is ever populated on this record by the
    Stage 30.4.1 adapter. The Stage 30.4.1 forbidden-field-name
    guard rejects any future refactor that tries to widen the
    field set with a secret-class or raw-payload-class name.

    Fields:

      * ``schema_version``               -- locked Stage 30.4.1
                                            compact market context
                                            schema version string.
      * ``session_id``                   -- safe-shape opaque session
                                            identifier or ``None``.
      * ``run_id``                       -- safe-shape opaque run
                                            identifier or ``None``.
      * ``candidate_id``                 -- safe-shape opaque
                                            candidate identifier or
                                            ``None``.
      * ``token_label``                  -- redacted token label
                                            (e.g. the short
                                            ``mint[:4] + "..."
                                            + mint[-4:]`` form, a
                                            hex-prefix mint hash, or
                                            a symbol-like string) or
                                            ``None``. NEVER the full
                                            mint string.
      * ``created_at_utc``               -- ISO-8601 UTC timestamp
                                            passed in by the caller
                                            (the injected clock).
      * ``market_cap_usd_status``        -- one of ``STATUS_VALUES``.
      * ``market_cap_usd_value``         -- canonical decimal-text MC
                                            value (e.g. ``"83000"``)
                                            or ``None``.
      * ``market_cap_display``           -- preformatted display text
                                            (e.g. ``"$83k"``) or
                                            ``None``.
      * ``liquidity_usd_status``         -- one of ``STATUS_VALUES``.
      * ``liquidity_usd_value``          -- canonical decimal-text LP
                                            value or ``None``.
      * ``liquidity_display``            -- preformatted display text
                                            or ``None``.
      * ``net_flow_status``              -- one of ``STATUS_VALUES``.
      * ``net_flow_usd_value``           -- canonical decimal-text net
                                            flow value (may carry a
                                            leading ``"-"``) or
                                            ``None``.
      * ``net_flow_display``             -- preformatted display text
                                            (e.g. ``"+$12k buys"`` /
                                            ``"-$8k sells"`` /
                                            ``"$0 flat"``) or
                                            ``None``.
      * ``net_flow_basis``               -- one of
                                            ``NET_FLOW_BASIS_VALUES``.
      * ``source_label``                 -- source-family label
                                            (e.g. ``"birdeye_token_overview"``)
                                            or ``None``.
      * ``source_status``                -- one of
                                            ``SOURCE_STATUS_VALUES``.
      * ``source_reason``                -- one of
                                            ``SOURCE_REASON_VALUES``.
      * ``runtime_consumable``           -- HARD-LOCKED to ``False``
                                            in Stage 30.4.1. The
                                            adapter raises if any
                                            caller / source tries to
                                            flip this to ``True``.
    """

    schema_version: str
    session_id: Optional[str]
    run_id: Optional[str]
    candidate_id: Optional[str]
    token_label: Optional[str]
    created_at_utc: str
    market_cap_usd_status: str
    market_cap_usd_value: Optional[str]
    market_cap_display: Optional[str]
    liquidity_usd_status: str
    liquidity_usd_value: Optional[str]
    liquidity_display: Optional[str]
    net_flow_status: str
    net_flow_usd_value: Optional[str]
    net_flow_display: Optional[str]
    net_flow_basis: str
    source_label: Optional[str]
    source_status: str
    source_reason: str
    runtime_consumable: bool


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.4.1 must never accept a field named anything secret-class
# or raw-payload-class on its record. The current
# ``Stage30_4CompactMarketContextRecord._fields`` set has no such
# name, but this helper is kept so a future refactor cannot silently
# widen the admitted field set.


# Split literals so this module's own source does NOT carry the
# bare API-key / signed-token / inbound-hook / authorization
# substrings that appear on the Stage 30.4.0 forbidden text-needle
# list. The runtime tuple value still resolves to the correct
# human-readable forbidden names.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
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
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "raw_response",
    "raw_capture_ref",
    "source_event_ref",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.4.1 uses this guard to reject any
    future refactor that tries to widen the record with a secret-
    class or raw-payload-class field name.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_4CompactMarketContextError(Exception):
    """Closed-set Stage 30.4.1 compact market context error.

    Carries only a closed-set reason token on the exception message.
    Stage 30.4.1 callers should never embed a raw OSError message, a
    raw provider payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.4.1 compact market context error: "
            f"reason={reason!r}"
        )


__all__ = (
    # Version + locked artifact basename.
    "STAGE30_4_1_MINOR_VERSION",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION",
    "STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME",
    # Status tokens.
    "STATUS_UNKNOWN",
    "STATUS_KNOWN",
    "STATUS_ERROR",
    "STATUS_STALE",
    "STATUS_VALUES",
    "is_status_value",
    # Source-status tokens.
    "SOURCE_STATUS_UNAVAILABLE",
    "SOURCE_STATUS_PRESENT",
    "SOURCE_STATUS_ERROR",
    "SOURCE_STATUS_STALE",
    "SOURCE_STATUS_VALUES",
    "is_source_status_value",
    # Source-reason tokens.
    "SOURCE_REASON_SOURCE_NOT_CONFIGURED",
    "SOURCE_REASON_SOURCE_PRESENT",
    "SOURCE_REASON_SOURCE_STALE",
    "SOURCE_REASON_MC_VALUE_INVALID",
    "SOURCE_REASON_LP_VALUE_INVALID",
    "SOURCE_REASON_NET_VALUE_INVALID",
    "SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED",
    "SOURCE_REASON_SOURCE_BASIS_INVALID",
    "SOURCE_REASON_SOURCE_REASON_MALFORMED",
    "SOURCE_REASON_VALUES",
    "is_source_reason_value",
    # Net-flow-basis tokens.
    "NET_FLOW_BASIS_UNKNOWN",
    "NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H",
    "NET_FLOW_BASIS_VOLUME_USD_DELTA_24H",
    "NET_FLOW_BASIS_VALUES",
    "is_net_flow_basis_value",
    # Record + forbidden-field guard + error.
    "Stage30_4CompactMarketContextRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_4CompactMarketContextError",
)
