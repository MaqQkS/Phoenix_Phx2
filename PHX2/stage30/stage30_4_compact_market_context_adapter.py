"""Stage 30.4.1 offline compact market context adapter / projector.

Pure projector that turns a caller-supplied identifier bundle plus
a Stage 30.4.1 source-protocol-shaped object (or ``None``) into a
Stage 30.4.1 ``Stage30_4CompactMarketContextRecord``. The adapter
NEVER opens a network connection, NEVER reads the process
environment, NEVER calls ``datetime.now`` (the clock is caller-
supplied via ``created_at_utc``), NEVER mutates its inputs,
NEVER recomputes Stage 30.1 tier decisions, NEVER routes data
into Stage 30.3 runtime, NEVER triggers a Stage 30.3 transport
send, NEVER fabricates MC / LP / Net values (missing source =>
Unknown; invalid value => ERROR with display ``None``; stale
source => STALE with display ``None``).

Stage 30.4.1 hard-locks ``runtime_consumable=False`` on every
record this projector returns. A future Stage 30.4.2 / 30.4.3 may
flip the flag, but Stage 30.4.1 does not.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.4.1 sibling modules (``models`` / ``formatter`` /
    ``source_protocol``) imported read-only.
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No transport reference on source text.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import re
from typing import Optional

from PHX2.stage30.stage30_4_compact_market_context_formatter import (
    format_signed_usd_compact,
    format_usd_compact,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_UNKNOWN,
    NET_FLOW_BASIS_VALUES,
    SOURCE_REASON_MC_VALUE_INVALID,
    SOURCE_REASON_LP_VALUE_INVALID,
    SOURCE_REASON_NET_VALUE_INVALID,
    SOURCE_REASON_SOURCE_BASIS_INVALID,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_REASON_MALFORMED,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_VALUES,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION,
    STATUS_ERROR,
    STATUS_KNOWN,
    STATUS_STALE,
    STATUS_UNKNOWN,
    Stage30_4CompactMarketContextError,
    Stage30_4CompactMarketContextRecord,
)
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)


# ---------------------------------------------------------------------------
# Safe-shape gates
# ---------------------------------------------------------------------------


_ISO8601_UTC_PATTERN: re.Pattern[str] = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,9})?"
    r"(?:Z|\+00:00)\Z"
)


# Safe-shape opaque identifier: ASCII alphanumeric plus ``_``, ``-``,
# ``.``; length [1, 64].
_OPAQUE_ID_PATTERN: re.Pattern[str] = re.compile(
    r"\A[A-Za-z0-9_\-.]{1,64}\Z"
)


# Safe-shape token label: ASCII alphanumeric plus ``_``, ``-``, ``.``,
# the Unicode horizontal ellipsis ``...``; length [1, 32]. The
# adapter intentionally REFUSES to echo a raw full base58 mint here;
# callers should pass the short ``mint[:4] + "..." + mint[-4:]``
# form or a redacted hex-prefix hash. A 32+ char base58 string is
# longer than 32 so the gate cuts it off.
_TOKEN_LABEL_PATTERN: re.Pattern[str] = re.compile(
    r"\A[A-Za-z0-9_\-.…]{1,32}\Z"
)


# Safe-shape source label: ASCII alphanumeric plus ``_``, ``-``;
# length [1, 64].
_SOURCE_LABEL_PATTERN: re.Pattern[str] = re.compile(
    r"\A[A-Za-z0-9_\-]{1,64}\Z"
)


def _is_safe_iso8601_utc(value: object) -> bool:
    return isinstance(value, str) and (
        _ISO8601_UTC_PATTERN.fullmatch(value) is not None
    )


def _is_safe_opaque_id(value: object) -> bool:
    return isinstance(value, str) and (
        _OPAQUE_ID_PATTERN.fullmatch(value) is not None
    )


def _is_safe_token_label(value: object) -> bool:
    return isinstance(value, str) and (
        _TOKEN_LABEL_PATTERN.fullmatch(value) is not None
    )


def _is_safe_source_label(value: object) -> bool:
    return isinstance(value, str) and (
        _SOURCE_LABEL_PATTERN.fullmatch(value) is not None
    )


# ---------------------------------------------------------------------------
# Optional-identifier echo
# ---------------------------------------------------------------------------


def _echo_optional_id(value: object) -> Optional[str]:
    """Return ``value`` if it is a safe-shape opaque identifier;
    return ``None`` for ``None`` or any unsafe-shape input.
    """
    if value is None:
        return None
    if _is_safe_opaque_id(value):
        assert isinstance(value, str)  # narrows for downstream
        return value
    return None


def _echo_optional_token_label(value: object) -> Optional[str]:
    """Return ``value`` if it is a safe-shape token label;
    return ``None`` for ``None`` or any unsafe-shape input.
    """
    if value is None:
        return None
    if _is_safe_token_label(value):
        assert isinstance(value, str)
        return value
    return None


# ---------------------------------------------------------------------------
# Display rendering helpers
# ---------------------------------------------------------------------------


def _try_format_usd(value: object) -> Optional[str]:
    """Return ``format_usd_compact(value)`` on success; return
    ``None`` on any caller-shape failure. Used for MC and LP.
    """
    if not isinstance(value, str):
        return None
    try:
        return format_usd_compact(value)
    except ValueError:
        return None


def _try_format_signed_usd(value: object) -> Optional[str]:
    """Return ``format_signed_usd_compact(value)`` on success; return
    ``None`` on any caller-shape failure. Used for Net flow.
    """
    if not isinstance(value, str):
        return None
    try:
        return format_signed_usd_compact(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source-reading echo gates
# ---------------------------------------------------------------------------


def _echo_source_label(value: object) -> Optional[str]:
    if value is None:
        return None
    if _is_safe_source_label(value):
        assert isinstance(value, str)
        return value
    return None


def _echo_source_reason(value: object) -> Optional[str]:
    """Return ``value`` if it is on the closed-set
    ``SOURCE_REASON_VALUES`` tuple; return ``None`` otherwise.
    """
    if value is None:
        return None
    if isinstance(value, str) and value in SOURCE_REASON_VALUES:
        return value
    return None


def _echo_net_flow_basis(value: object) -> Optional[str]:
    """Return ``value`` if it is on the closed-set
    ``NET_FLOW_BASIS_VALUES`` tuple; return ``None`` otherwise.
    """
    if value is None:
        return None
    if isinstance(value, str) and value in NET_FLOW_BASIS_VALUES:
        return value
    return None


# ---------------------------------------------------------------------------
# Public: project_market_context
# ---------------------------------------------------------------------------


def project_market_context(
    *,
    session_id: Optional[str],
    run_id: Optional[str],
    candidate_id: Optional[str],
    token_mint: Optional[str],
    created_at_utc: str,
    source: object,
) -> Stage30_4CompactMarketContextRecord:
    """Project a Stage 30.4.1 compact market context record.

    Behavior:

      * ``source is None``                  => MC / LP / Net all
                                               ``UNKNOWN``, displays
                                               ``None``,
                                               ``source_status=UNAVAILABLE``,
                                               ``source_reason=SOURCE_NOT_CONFIGURED``,
                                               ``source_label=None``.
      * ``source`` present, returns ``None`` => same as the
                                               ``source is None`` path
                                               for the per-slot
                                               statuses, but
                                               ``source_status=UNAVAILABLE``
                                               and ``source_label`` is
                                               left ``None`` (because
                                               no reading was emitted).
      * ``source`` present, returns a
        ``Stage30_4MarketContextSourceReading`` with valid MC / LP
        / Net  decimal-text values =>        per-slot ``KNOWN`` with
                                             preformatted displays;
                                             ``source_status=PRESENT``,
                                             ``source_reason=SOURCE_PRESENT``
                                             (unless overridden by
                                             the reading's
                                             ``source_reason``).
      * reading flagged ``stale=True``       => per-slot ``STALE``
                                                for every slot that
                                                had a value; missing
                                                slots stay
                                                ``UNKNOWN``; displays
                                                ``None``;
                                                ``source_status=STALE``,
                                                ``source_reason=SOURCE_STALE``.
      * reading carries an invalid MC / LP
        / Net value =>                       per-slot ``ERROR`` with
                                             display ``None``;
                                             ``source_status=ERROR``;
                                             ``source_reason`` set to
                                             the most specific
                                             closed-set token (MC
                                             takes precedence over
                                             LP, which takes
                                             precedence over Net).
      * reading carries an unsafe-shape
        ``observed_at_utc`` =>               ``source_status=ERROR``,
                                             ``source_reason=SOURCE_OBSERVATION_TIMESTAMP_MALFORMED``;
                                             per-slot statuses still
                                             reflect the values that
                                             validated.
      * reading carries an off-closed-set
        ``net_flow_basis`` =>                ``net_flow_basis`` falls
                                             back to ``UNKNOWN``,
                                             ``source_status=ERROR``,
                                             ``source_reason=SOURCE_BASIS_INVALID``.

    Raises ``Stage30_4CompactMarketContextError`` on caller-shape
    failures only:

      * ``created_at_utc`` not a safe-shape ISO-8601 UTC string,
      * any caller-supplied identifier of the wrong type (a non-
        ``str`` non-``None`` is silently coerced to ``None`` via
        the echo gates, NOT raised).

    NEVER mutates ``source``, NEVER calls anything on ``source``
    other than ``source.read(token_mint)``, NEVER fetches network
    data, NEVER reads the process environment.
    """
    if not _is_safe_iso8601_utc(created_at_utc):
        raise Stage30_4CompactMarketContextError(
            "CREATED_AT_UTC_UNSAFE_SHAPE"
        )

    safe_session = _echo_optional_id(session_id)
    safe_run = _echo_optional_id(run_id)
    safe_candidate = _echo_optional_id(candidate_id)
    safe_token_label = _echo_optional_token_label(token_mint)

    # ----- Source is None: full Unknown path ------------------------------
    if source is None:
        return Stage30_4CompactMarketContextRecord(
            schema_version=(
                STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
            ),
            session_id=safe_session,
            run_id=safe_run,
            candidate_id=safe_candidate,
            token_label=safe_token_label,
            created_at_utc=created_at_utc,
            market_cap_usd_status=STATUS_UNKNOWN,
            market_cap_usd_value=None,
            market_cap_display=None,
            liquidity_usd_status=STATUS_UNKNOWN,
            liquidity_usd_value=None,
            liquidity_display=None,
            net_flow_status=STATUS_UNKNOWN,
            net_flow_usd_value=None,
            net_flow_display=None,
            net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
            source_label=None,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
            runtime_consumable=False,
        )

    # ----- Source present: ask for a reading ------------------------------
    reading = _safe_read(source, token_mint)
    if reading is None:
        return Stage30_4CompactMarketContextRecord(
            schema_version=(
                STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
            ),
            session_id=safe_session,
            run_id=safe_run,
            candidate_id=safe_candidate,
            token_label=safe_token_label,
            created_at_utc=created_at_utc,
            market_cap_usd_status=STATUS_UNKNOWN,
            market_cap_usd_value=None,
            market_cap_display=None,
            liquidity_usd_status=STATUS_UNKNOWN,
            liquidity_usd_value=None,
            liquidity_display=None,
            net_flow_status=STATUS_UNKNOWN,
            net_flow_usd_value=None,
            net_flow_display=None,
            net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
            source_label=None,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
            runtime_consumable=False,
        )

    # The reading is shape-checked here. Stage 30.4.1 does not assert
    # ``isinstance(reading, Stage30_4MarketContextSourceReading)``;
    # the protocol is duck-typed, and the gates below treat any
    # attribute access via ``getattr`` so a non-NamedTuple shaped
    # source can still satisfy the protocol.
    raw_mc = _safe_getattr(reading, "market_cap_usd_value")
    raw_lp = _safe_getattr(reading, "liquidity_usd_value")
    raw_net = _safe_getattr(reading, "net_flow_usd_value")
    raw_basis = _safe_getattr(reading, "net_flow_basis")
    raw_source_label = _safe_getattr(reading, "source_label")
    raw_observed = _safe_getattr(reading, "observed_at_utc")
    raw_stale = _safe_getattr(reading, "stale")
    raw_reason = _safe_getattr(reading, "source_reason")

    # Echo / validate source label + reason + basis.
    source_label_echo = _echo_source_label(raw_source_label)

    basis_echo = _echo_net_flow_basis(raw_basis)
    basis_invalid = basis_echo is None
    if basis_echo is None:
        basis_echo = NET_FLOW_BASIS_UNKNOWN

    observed_invalid = not _is_safe_iso8601_utc(raw_observed)

    reading_reason_echo = _echo_source_reason(raw_reason)
    reading_reason_malformed = (
        raw_reason is not None and reading_reason_echo is None
    )

    is_stale = raw_stale is True

    # ----- Per-slot canonical value validation ---------------------------
    mc_value, mc_invalid = _validate_unsigned_value(raw_mc)
    lp_value, lp_invalid = _validate_unsigned_value(raw_lp)
    net_value, net_invalid = _validate_signed_value(raw_net)

    # ----- Per-slot status + display ------------------------------------
    if mc_invalid:
        mc_status = STATUS_ERROR
        mc_display: Optional[str] = None
        mc_value_to_store: Optional[str] = None
    elif mc_value is None:
        mc_status = STATUS_UNKNOWN
        mc_display = None
        mc_value_to_store = None
    elif is_stale:
        mc_status = STATUS_STALE
        mc_display = None
        mc_value_to_store = mc_value
    else:
        mc_status = STATUS_KNOWN
        mc_display = _try_format_usd(mc_value)
        mc_value_to_store = mc_value if mc_display is not None else None
        if mc_display is None:
            mc_status = STATUS_ERROR

    if lp_invalid:
        lp_status = STATUS_ERROR
        lp_display: Optional[str] = None
        lp_value_to_store: Optional[str] = None
    elif lp_value is None:
        lp_status = STATUS_UNKNOWN
        lp_display = None
        lp_value_to_store = None
    elif is_stale:
        lp_status = STATUS_STALE
        lp_display = None
        lp_value_to_store = lp_value
    else:
        lp_status = STATUS_KNOWN
        lp_display = _try_format_usd(lp_value)
        lp_value_to_store = lp_value if lp_display is not None else None
        if lp_display is None:
            lp_status = STATUS_ERROR

    if net_invalid:
        net_status = STATUS_ERROR
        net_display: Optional[str] = None
        net_value_to_store: Optional[str] = None
    elif net_value is None:
        net_status = STATUS_UNKNOWN
        net_display = None
        net_value_to_store = None
    elif is_stale:
        net_status = STATUS_STALE
        net_display = None
        net_value_to_store = net_value
    else:
        net_status = STATUS_KNOWN
        net_display = _try_format_signed_usd(net_value)
        net_value_to_store = (
            net_value if net_display is not None else None
        )
        if net_display is None:
            net_status = STATUS_ERROR

    # ----- Aggregate source_status + source_reason ---------------------
    has_any_invalid = mc_invalid or lp_invalid or net_invalid

    source_status = SOURCE_STATUS_PRESENT
    if has_any_invalid or basis_invalid or observed_invalid or (
        reading_reason_malformed
    ):
        source_status = SOURCE_STATUS_ERROR
    elif is_stale:
        # If the reading flagged itself stale, the source_status is
        # STALE; per-slot STALE captures the value-bearing slots.
        source_status = SOURCE_STATUS_STALE

    # source_reason precedence:
    #   1. MC_VALUE_INVALID,
    #   2. LP_VALUE_INVALID,
    #   3. NET_VALUE_INVALID,
    #   4. SOURCE_BASIS_INVALID,
    #   5. SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
    #   6. SOURCE_REASON_MALFORMED,
    #   7. SOURCE_STALE,
    #   8. caller-supplied reading_reason_echo when on the closed set,
    #   9. SOURCE_PRESENT.
    if mc_invalid:
        source_reason = SOURCE_REASON_MC_VALUE_INVALID
    elif lp_invalid:
        source_reason = SOURCE_REASON_LP_VALUE_INVALID
    elif net_invalid:
        source_reason = SOURCE_REASON_NET_VALUE_INVALID
    elif basis_invalid:
        source_reason = SOURCE_REASON_SOURCE_BASIS_INVALID
    elif observed_invalid:
        source_reason = (
            SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED
        )
    elif reading_reason_malformed:
        source_reason = SOURCE_REASON_SOURCE_REASON_MALFORMED
    elif is_stale:
        source_reason = SOURCE_REASON_SOURCE_STALE
    elif reading_reason_echo is not None:
        source_reason = reading_reason_echo
    else:
        source_reason = SOURCE_REASON_SOURCE_PRESENT

    return Stage30_4CompactMarketContextRecord(
        schema_version=(
            STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
        ),
        session_id=safe_session,
        run_id=safe_run,
        candidate_id=safe_candidate,
        token_label=safe_token_label,
        created_at_utc=created_at_utc,
        market_cap_usd_status=mc_status,
        market_cap_usd_value=mc_value_to_store,
        market_cap_display=mc_display,
        liquidity_usd_status=lp_status,
        liquidity_usd_value=lp_value_to_store,
        liquidity_display=lp_display,
        net_flow_status=net_status,
        net_flow_usd_value=net_value_to_store,
        net_flow_display=net_display,
        net_flow_basis=basis_echo,
        source_label=source_label_echo,
        source_status=source_status,
        source_reason=source_reason,
        runtime_consumable=False,
    )


# ---------------------------------------------------------------------------
# Internal: safe read + safe getattr
# ---------------------------------------------------------------------------


def _safe_read(
    source: object, token_mint: object
) -> Optional[Stage30_4MarketContextSourceReading]:
    """Call ``source.read(token_mint)`` and return its value.

    The adapter does NOT swallow exceptions raised by the source;
    the caller decides whether to wrap. Stage 30.4.1 callers in
    practice run a fake source and never raise. This narrow surface
    exists so the adapter never touches any other attribute on the
    source object.
    """
    if not isinstance(token_mint, str):
        return None
    read_method = getattr(source, "read", None)
    if read_method is None:
        return None
    if not callable(read_method):
        return None
    return read_method(token_mint)


def _safe_getattr(reading: object, name: str) -> object:
    """Return ``getattr(reading, name, None)`` without falling
    through to ``hasattr`` shenanigans.
    """
    return getattr(reading, name, None)


# ---------------------------------------------------------------------------
# Internal: value validation
# ---------------------------------------------------------------------------


# Strict unsigned and signed canonical decimal-text patterns.
# Mirror the formatter's patterns. The adapter intentionally mirrors
# the regex rather than importing the formatter's private patterns,
# because the formatter raises ``ValueError`` for invalid input; the
# adapter needs to distinguish "value was None" (UNKNOWN) from
# "value was present but invalid" (ERROR) without raising.
_UNSIGNED_DECIMAL_PATTERN: re.Pattern[str] = re.compile(
    r"\A(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z"
)
_SIGNED_DECIMAL_PATTERN: re.Pattern[str] = re.compile(
    r"\A-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z"
)


def _validate_unsigned_value(value: object) -> tuple:
    """Validate ``value`` as a non-negative canonical decimal-text
    USD value.

    Returns ``(canonical_value_or_None, invalid_bool)``:

      * ``(None, False)``    if ``value is None``.
      * ``(value, False)``   if ``value`` is a string passing the
                             strict unsigned pattern AND not
                             ``"-0"``.
      * ``(None, True)``     if ``value`` is any other non-``None``
                             input.
    """
    if value is None:
        return None, False
    if not isinstance(value, str):
        return None, True
    if _UNSIGNED_DECIMAL_PATTERN.fullmatch(value) is None:
        return None, True
    return value, False


def _validate_signed_value(value: object) -> tuple:
    """Validate ``value`` as a canonical signed decimal-text USD
    value.

    Returns ``(canonical_value_or_None, invalid_bool)``:

      * ``(None, False)``    if ``value is None``.
      * ``(value, False)``   if ``value`` is a string passing the
                             strict signed pattern AND not ``"-0"``.
      * ``(None, True)``     if ``value`` is any other non-``None``
                             input.
    """
    if value is None:
        return None, False
    if not isinstance(value, str):
        return None, True
    if _SIGNED_DECIMAL_PATTERN.fullmatch(value) is None:
        return None, True
    if value == "-0":
        return None, True
    return value, False


__all__ = (
    "project_market_context",
)
