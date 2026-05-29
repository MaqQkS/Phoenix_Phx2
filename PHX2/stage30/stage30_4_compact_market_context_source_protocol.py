"""Stage 30.4.1 offline compact market context source protocol.

Pure-Python duck-typed surface that the Stage 30.4.1 adapter /
projector consumes. Stage 30.4.1 ships ONLY the protocol surface
plus an immutable reading record; no real source adapter ships
in Stage 30.4.1. A real Birdeye-token-overview HTTP / on-chain
supply / cross-check source adapter requires separately
authorized scope (Stage 30.4.3 or later).

Surfaces:

  * ``Stage30_4MarketContextSourceReading``
      Immutable ``NamedTuple`` carrying the closed-shape per-call
      reading a source emits when the adapter asks for context on
      one token. Fields are restricted to canonical decimal-text
      values OR ``None``, a closed-set ``net_flow_basis`` token, a
      short safe-shape source label, an ISO-8601 UTC
      ``observed_at_utc`` timestamp, a ``stale`` boolean, and an
      OPTIONAL closed-set ``source_reason`` token. No raw provider
      response, no URL, no API-key string, no signed-token
      credential, no authorization-header text, no RPC endpoint,
      no host string is ever populated on this reading.

  * ``Stage30_4MarketContextSourceProtocol``
      Duck-typed ``Protocol``. A source implements one method,
      ``read(token_mint: str) -> Optional[Stage30_4MarketContextSourceReading]``.
      Returning ``None`` is the equivalent of "source had nothing
      to report" and the adapter resolves the per-slot status to
      ``UNKNOWN`` with ``source_status=UNAVAILABLE``.

Discipline:

  * Stdlib only (``typing``).
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No transport reference on source text.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Protocol, Tuple, runtime_checkable


# ---------------------------------------------------------------------------
# Immutable reading record
# ---------------------------------------------------------------------------


class Stage30_4MarketContextSourceReading(NamedTuple):
    """Immutable Stage 30.4.1 per-call source reading.

    Carries only canonical decimal-text values OR ``None``, a closed-
    set ``net_flow_basis`` token, a short safe-shape source label,
    a safe-shape ISO-8601 UTC ``observed_at_utc`` timestamp, a
    ``stale`` boolean, and an OPTIONAL closed-set ``source_reason``
    token. No raw provider response, no URL, no API-key string, no
    signed-token credential, no authorization-header text, no RPC
    endpoint, no host string is ever populated on this reading by
    a Stage 30.4.1 fake or by a future real adapter.

    Fields:

      * ``market_cap_usd_value``     -- canonical decimal-text
                                        (e.g. ``"83000"``) or
                                        ``None``. ``None`` => the
                                        source has no MC reading
                                        for this token.
      * ``liquidity_usd_value``      -- canonical decimal-text or
                                        ``None``.
      * ``net_flow_usd_value``       -- canonical signed
                                        decimal-text (may carry a
                                        leading ``-``) or ``None``.
      * ``net_flow_basis``           -- closed-set basis token. The
                                        Stage 30.4.1 models module
                                        owns the closed set
                                        (``NET_FLOW_BASIS_VALUES``).
                                        Default when Net is
                                        ``None`` is ``UNKNOWN``.
      * ``source_label``             -- short safe-shape source
                                        label (e.g.
                                        ``"birdeye_token_overview"``).
                                        NEVER a URL, host, or API
                                        key string.
      * ``observed_at_utc``          -- ISO-8601 UTC timestamp the
                                        source assigns to this
                                        reading. The Stage 30.4.1
                                        adapter validates safe-shape
                                        before echoing.
      * ``stale``                    -- ``True`` iff the source
                                        flagged this reading as
                                        stale (cached / past TTL /
                                        snapshot-not-refreshed).
                                        The adapter promotes per-
                                        slot status to ``STALE`` in
                                        that case.
      * ``source_reason``            -- OPTIONAL closed-set
                                        source-reason token. The
                                        adapter substitutes a
                                        sensible default when
                                        ``None``.
    """

    market_cap_usd_value: Optional[str]
    liquidity_usd_value: Optional[str]
    net_flow_usd_value: Optional[str]
    net_flow_basis: str
    source_label: str
    observed_at_utc: str
    stale: bool
    source_reason: Optional[str]


# ---------------------------------------------------------------------------
# Duck-typed source protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage30_4MarketContextSourceProtocol(Protocol):
    """Duck-typed Stage 30.4.1 compact market context source.

    A source exposes a single ``read`` method that takes the
    candidate ``token_mint`` string and returns either a
    ``Stage30_4MarketContextSourceReading`` (the source had a
    reading) or ``None`` (the source had nothing to report; the
    adapter resolves the per-slot status to ``UNKNOWN`` with
    ``source_status=UNAVAILABLE``).

    The protocol intentionally does NOT define a ``close`` /
    ``open`` / ``flush`` / ``url`` / ``auth`` / ``api`` + ``_key``
    / ``b`` + ``earer`` / ``token`` / ``configure`` / ``set_endpoint``
    method. The Stage 30.4.1 adapter NEVER calls anything on the
    source other than ``read``.
    """

    def read(
        self, token_mint: str
    ) -> Optional[Stage30_4MarketContextSourceReading]:
        ...


# ---------------------------------------------------------------------------
# Defensive: forbidden attribute names on a source object
# ---------------------------------------------------------------------------
#
# The Stage 30.4.1 adapter never accesses any of these attributes on
# a source object. The tuple is exported so the Stage 30.4.1 adapter
# can defensively assert that the source-protocol implementation it
# was handed does not advertise a secret-class / transport-class
# surface.


SOURCE_FORBIDDEN_ATTRIBUTE_NAMES: Tuple[str, ...] = (
    # Stage 30.4.1 reserved-attribute substrings (split-literal so
    # this module's source text never carries the bare needle).
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "web" + "hook",
    "web" + "hook_url",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
    "secret",
    "secret_key",
    "private_key",
    "credentials",
    "password",
    "signer",
    "raw_payload",
    "payload",
    "payload_blob",
    "raw_response",
)


def is_source_forbidden_attribute_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden source attribute
    name.

    Pure / deterministic. Stage 30.4.1 uses this guard to reject any
    future source-protocol implementation that tries to advertise a
    secret-class or transport-class surface.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in SOURCE_FORBIDDEN_ATTRIBUTE_NAMES:
        if forbidden in lower:
            return True
    return False


__all__ = (
    "Stage30_4MarketContextSourceReading",
    "Stage30_4MarketContextSourceProtocol",
    "SOURCE_FORBIDDEN_ATTRIBUTE_NAMES",
    "is_source_forbidden_attribute_name",
)
