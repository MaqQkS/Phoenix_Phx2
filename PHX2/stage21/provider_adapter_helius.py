"""Stage 21.3B Helius provider adapter (boundary-only).

This module is the Stage 21.3B concrete provider adapter
boundary. It defines:

  * ``HeliusClientProtocol`` -- the duck-typed contract for an
    injected client. The client is responsible for any actual
    network / RPC / gRPC work; the adapter never imports a
    network library and never calls one directly.
  * ``HeliusProviderAdapter`` -- the thin adapter that consumes
    client responses and produces either:

      - raw 11-key Stage 21.3A payload mappings via
        ``fetch_raw_payloads`` (the input shape that
        ``decode_provider_event`` accepts), or
      - ``NormalizedLiveEvent`` records via
        ``fetch_normalized_events`` (the same payload mapped
        through ``decode_provider_event``).

The adapter is intentionally minimal. It enriches each client
response with the adapter-locked constants
(``HELIUS_PROVIDER_NAME``, ``HELIUS_CHAIN_NAME``,
``HELIUS_SOURCE_KIND``,
``HELIUS_INSTRUCTION_KIND_PLACEHOLDER``) and validates that the
remaining caller-supplied fields satisfy the
``decode_provider_event`` contract.

Stage 21.3B scope notes:

  * The adapter keeps ``instruction_kind`` at the Stage 21.3A
    placeholder ``"reserved_for_21_3b"``. The real PumpSwap /
    Pump.fun instruction-kind vocabulary lands in Stage 21.4+
    with the live runner; the decoder is NOT widened here.
  * The adapter is gRPC-compatible by design: the client
    contract is a single ``fetch_raw_responses`` method
    returning a ``Sequence`` of mappings, which a Yellowstone /
    Geyser / Helius enhanced-webhook client can all satisfy.
  * The adapter does NOT own credentials. Credential material
    lives in the injected client (which the future Stage 21.4
    runner will construct from a ``SecretRef`` snapshot).
  * The adapter does NOT read ``os.environ`` / ``os.getenv``.
    The Stage 21 env-read boundary stays at
    ``PHX2/stage21/config.py`` alone.
  * The adapter does NOT import any network / RPC / messaging /
    transport / DB / secrets-management library.
  * The adapter does NOT import ``fake_provider``,
    ``fake_transport``, ``live_path_simulator``, Phoenix1, any
    PHX2 runtime layer, or any Stage 17..20 module.
  * The adapter has NO retry / backoff / dedupe / archive /
    Discord-send / orchestrator / runner behaviour. Those land
    in Stage 21.3C, 21.4, and Stage 22 respectively.

The adapter is side-effect-free on import: only module-level
constant assignments and class / function definitions appear
at top level.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.provider_event_decoder import decode_provider_event


# ---------------------------------------------------------------------------
# Locked Stage 21.3B adapter constants
# ---------------------------------------------------------------------------
#
# These are the four adapter-locked enrichment values that the
# adapter applies to every payload it builds. Callers cannot
# override them: the adapter is the single authority on the
# ``provider_name`` / ``chain`` / ``source_kind`` /
# ``instruction_kind`` fields of the payload. This prevents a
# malicious or malformed client from forging a different
# provider_name back through the boundary.


# Adapter-emitted ``provider_name``. The Stage 21.3A decoder
# accepts any non-empty string here; the adapter pins it to the
# real Helius label so downstream consumers can distinguish
# real-provider events from fake-provider events at the
# field-value level.
HELIUS_PROVIDER_NAME: str = "helius"


# Adapter-emitted ``chain``. Stage 21.3B is Solana mainnet only;
# devnet / testnet / multi-chain support is out of scope for
# this sub-stage and would land in a future adapter constructor
# parameter or sibling adapter module.
HELIUS_CHAIN_NAME: str = "solana_mainnet"


# Adapter-emitted ``source_kind``. The label is intentionally
# generic so it covers both Helius enhanced-webhook and Helius
# gRPC-compatible (Yellowstone / Geyser) flavours without
# locking us into the HTTP polling shape.
HELIUS_SOURCE_KIND: str = "helius_grpc_compatible"


# Adapter-emitted ``instruction_kind``. Stage 21.3B keeps this
# at the Stage 21.3A placeholder. The real PumpSwap / Pump.fun
# instruction-kind vocabulary lands in Stage 21.4+ with an
# explicit operator decision and a paired decoder update.
HELIUS_INSTRUCTION_KIND_PLACEHOLDER: str = "reserved_for_21_3b"


# Frozen tuple of the four adapter-locked enrichment values.
# Tests pin this set so a future drift requires an explicit
# operator decision.
HELIUS_ADAPTER_LOCKED_VALUES: tuple[str, ...] = (
    HELIUS_PROVIDER_NAME,
    HELIUS_CHAIN_NAME,
    HELIUS_SOURCE_KIND,
    HELIUS_INSTRUCTION_KIND_PLACEHOLDER,
)


# ---------------------------------------------------------------------------
# Required client-response keys
# ---------------------------------------------------------------------------
#
# The client is responsible for delivering each event as a
# ``Mapping`` with these seven keys. The adapter validates the
# shape, then enriches with the four adapter-locked values
# above to produce the 11-key Stage 21.3A
# ``RawProviderPayload`` shape that
# ``decode_provider_event`` accepts.


REQUIRED_CLIENT_RESPONSE_KEYS: tuple[str, ...] = (
    "provider_event_id",
    "signature",
    "slot",
    "observed_at_utc",
    "event_type",
    "mint",
    "decoded_fields",
)


# ---------------------------------------------------------------------------
# Module-local error hierarchy
# ---------------------------------------------------------------------------
#
# The hierarchy is module-local and rooted at plain ``Exception``,
# mirroring the Stage 21.3A decoder's Q3 decision. The Stage 21
# central ``Stage21Error`` registry is NOT extended here: the
# closed-set E2120..E2122 codes remain reserved for a future
# adapter contract surface (Stage 21.3C / 21.4) if needed.


class HeliusAdapterError(Exception):
    """Base error for Stage 21.3B Helius adapter contract violations."""


class HeliusClientResponseShapeError(HeliusAdapterError):
    """Raised when the client returned a non-Sequence, or a response that is
    not a Mapping, or a response missing one of the required keys."""


class HeliusClientResponseFieldTypeError(HeliusAdapterError):
    """Raised when a required client-response field has the wrong Python type."""


class HeliusClientResponseFieldValueError(HeliusAdapterError):
    """Raised when a required client-response field has an invalid value
    (empty string, negative slot, etc.)."""


class HeliusClientFetchError(HeliusAdapterError):
    """Raised when the injected client itself raised an exception during
    ``fetch_raw_responses``.

    The adapter wraps any client-side exception in this
    adapter-local error and sanitizes the message: only the
    client exception's TYPE name is exposed. The original
    exception's ``str`` / ``repr`` / ``args`` / raw response
    body / URL / token / secret / API key / RPC URL is never
    surfaced.

    The wrapping uses ``raise ... from None`` so Python's
    exception chaining (``__cause__`` / ``__context__``) does
    not expose the original exception's repr in tracebacks.
    """


# ---------------------------------------------------------------------------
# Injected-client Protocol
# ---------------------------------------------------------------------------


class HeliusClientProtocol(Protocol):
    """Duck-typed contract for an injected Helius (or gRPC-compatible) client.

    The adapter calls a single method on the client. The client
    is responsible for any actual RPC / gRPC / HTTP work and
    for any pre-decoding required to fill the seven
    ``REQUIRED_CLIENT_RESPONSE_KEYS`` of each response mapping.

    The adapter does not construct the client and does not
    inspect any other client state -- the client is treated as
    an opaque collaborator. The future Stage 21.4 runner is the
    expected operational caller that constructs a real client
    from a ``SecretRef`` snapshot and passes it in here.
    """

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[Mapping[str, object]]: ...


# ---------------------------------------------------------------------------
# Helius provider adapter
# ---------------------------------------------------------------------------


class HeliusProviderAdapter:
    """Stage 21.3B Helius provider adapter (boundary-only).

    Construct with an injected client implementing
    ``HeliusClientProtocol``. The adapter does NOT own
    credentials, does NOT read the environment, and does NOT
    call any network library.

    Two public surfaces:

      * ``fetch_raw_payloads(cursor, max_results)`` -- returns
        an immutable tuple of the 11-key Stage 21.3A
        ``RawProviderPayload`` mappings. Each mapping is the
        adapter's enrichment of one client response.
      * ``fetch_normalized_events(cursor, max_results)`` --
        returns an immutable tuple of ``NormalizedLiveEvent``
        records by running each raw payload through
        ``decode_provider_event``.

    The adapter never retries, never deduplicates, never
    archives, never sends, never persists. Those concerns live
    in Stage 21.3C (private Discord transport), Stage 21.4 (live
    runner / orchestrator), and Stage 22 (retries / dedupe /
    raw archival / quarantine).

    ``__repr__`` does NOT echo the client's repr -- the client
    may hold credential material. Only the adapter class name
    and the client's type name appear.
    """

    HELIUS_PROVIDER_NAME: str = HELIUS_PROVIDER_NAME
    HELIUS_CHAIN_NAME: str = HELIUS_CHAIN_NAME
    HELIUS_SOURCE_KIND: str = HELIUS_SOURCE_KIND
    HELIUS_INSTRUCTION_KIND_PLACEHOLDER: str = (
        HELIUS_INSTRUCTION_KIND_PLACEHOLDER
    )

    def __init__(self, client: HeliusClientProtocol) -> None:
        if client is None:
            raise HeliusClientResponseShapeError(
                "HeliusProviderAdapter requires a non-None client"
            )
        self._client = client

    def __repr__(self) -> str:
        return (
            "HeliusProviderAdapter(client_type="
            f"{type(self._client).__name__!r})"
        )

    def fetch_raw_payloads(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> tuple[Mapping[str, object], ...]:
        """Return an immutable tuple of 11-key Stage 21.3A payload mappings.

        Calls ``self._client.fetch_raw_responses(...)`` and
        converts each response into the
        ``REQUIRED_TOP_LEVEL_KEYS`` shape that
        ``decode_provider_event`` accepts. The four
        adapter-locked enrichment values
        (``provider_name`` / ``chain`` / ``source_kind`` /
        ``instruction_kind``) are added by the adapter -- the
        client cannot influence them.

        Raises ``HeliusClientFetchError`` if the injected
        client itself raised; the raw client exception
        ``str`` / ``repr`` / ``args`` are NOT surfaced -- only
        the client exception's TYPE name is exposed. Raises
        ``HeliusClientResponseShapeError`` if the client
        returned a non-Sequence, or any response is not a
        Mapping, or a required key is missing. Raises
        ``HeliusClientResponseFieldTypeError`` /
        ``HeliusClientResponseFieldValueError`` for per-field
        violations. Exception messages name the offending field
        and (where helpful) the offending Python type -- they
        never echo the raw response value.
        """
        # Audit-21.3B Major remediation: the injected client may
        # raise an arbitrary Exception whose ``str`` / ``repr``
        # / ``args`` could carry a raw response body, URL, token,
        # API key, or RPC URL. The adapter wraps the call and
        # surfaces only the client exception's TYPE name through
        # ``HeliusClientFetchError``. ``raise ... from None``
        # suppresses Python's exception-chaining display so the
        # original exception's repr never reaches the traceback.
        try:
            responses = self._client.fetch_raw_responses(
                cursor=cursor,
                max_results=max_results,
            )
        except Exception as exc:
            raise HeliusClientFetchError(
                f"helius client fetch failed: {type(exc).__name__}"
            ) from None
        # Reject str / bytes outright -- both satisfy Sequence
        # but neither carries response mappings; treating them
        # as iterables of characters / bytes is never what the
        # contract intends.
        if isinstance(responses, (str, bytes)):
            raise HeliusClientResponseShapeError(
                "client.fetch_raw_responses must return a Sequence of "
                "Mappings; got a "
                f"{type(responses).__name__}"
            )
        if not isinstance(responses, Sequence):
            raise HeliusClientResponseShapeError(
                "client.fetch_raw_responses must return a Sequence of "
                "Mappings; got "
                f"{type(responses).__name__}"
            )
        return tuple(
            self._build_payload(response, index=index)
            for index, response in enumerate(responses)
        )

    def fetch_normalized_events(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> tuple[NormalizedLiveEvent, ...]:
        """Return an immutable tuple of ``NormalizedLiveEvent`` records.

        Composes ``fetch_raw_payloads`` with
        ``decode_provider_event``. Raises the adapter errors
        listed on ``fetch_raw_payloads`` for client-side
        violations, and the
        ``provider_event_decoder.ProviderPayloadError``
        subclasses for decoder-level violations (shape /
        type / value / unsupported instruction kind /
        suspicious content).
        """
        payloads = self.fetch_raw_payloads(
            cursor=cursor,
            max_results=max_results,
        )
        return tuple(decode_provider_event(payload) for payload in payloads)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        response: object,
        *,
        index: int,
    ) -> Mapping[str, object]:
        """Convert one client response into the 11-key payload.

        The function validates the response shape, extracts
        each required field with the correct Python type, then
        adds the four adapter-locked enrichment values.
        Exception messages name the field and (where helpful)
        the offending Python type -- they never echo the raw
        value.
        """
        if not isinstance(response, Mapping):
            raise HeliusClientResponseShapeError(
                f"client response at index {index} must be a Mapping; "
                f"got {type(response).__name__}"
            )
        for key in REQUIRED_CLIENT_RESPONSE_KEYS:
            if key not in response:
                raise HeliusClientResponseShapeError(
                    f"client response at index {index} missing required key "
                    f"{key!r}"
                )

        provider_event_id = self._require_str(response, "provider_event_id", index=index)
        signature = self._require_str(response, "signature", index=index)
        slot = self._require_int(response, "slot", index=index)
        observed_at_utc = self._require_str(response, "observed_at_utc", index=index)
        event_type = self._require_str(response, "event_type", index=index)
        mint = self._require_str(response, "mint", index=index)
        decoded_fields = self._require_mapping(response, "decoded_fields", index=index)

        return {
            "provider_event_id": provider_event_id,
            "provider_name": HELIUS_PROVIDER_NAME,
            "source_kind": HELIUS_SOURCE_KIND,
            "chain": HELIUS_CHAIN_NAME,
            "mint": mint,
            "event_type": event_type,
            "observed_at_utc": observed_at_utc,
            "slot": slot,
            "signature": signature,
            "instruction_kind": HELIUS_INSTRUCTION_KIND_PLACEHOLDER,
            "decoded_fields": decoded_fields,
        }

    @staticmethod
    def _require_str(
        response: Mapping[str, object],
        key: str,
        *,
        index: int,
    ) -> str:
        value = response[key]
        if not isinstance(value, str):
            raise HeliusClientResponseFieldTypeError(
                f"client response at index {index} field {key!r} must be "
                f"str; got {type(value).__name__}"
            )
        if value == "":
            raise HeliusClientResponseFieldValueError(
                f"client response at index {index} field {key!r} must be "
                "a non-empty string"
            )
        return value

    @staticmethod
    def _require_int(
        response: Mapping[str, object],
        key: str,
        *,
        index: int,
    ) -> int:
        value = response[key]
        # bool is a subclass of int in Python; reject it
        # explicitly so a stray True / False slot does not
        # silently coerce to 1 / 0.
        if isinstance(value, bool) or not isinstance(value, int):
            raise HeliusClientResponseFieldTypeError(
                f"client response at index {index} field {key!r} must be "
                f"int; got {type(value).__name__}"
            )
        if value < 0:
            raise HeliusClientResponseFieldValueError(
                f"client response at index {index} field {key!r} must be "
                "non-negative"
            )
        return value

    @staticmethod
    def _require_mapping(
        response: Mapping[str, object],
        key: str,
        *,
        index: int,
    ) -> Mapping[str, object]:
        value = response[key]
        if not isinstance(value, Mapping):
            raise HeliusClientResponseFieldTypeError(
                f"client response at index {index} field {key!r} must be "
                f"Mapping; got {type(value).__name__}"
            )
        return value


__all__ = [
    "HELIUS_ADAPTER_LOCKED_VALUES",
    "HELIUS_CHAIN_NAME",
    "HELIUS_INSTRUCTION_KIND_PLACEHOLDER",
    "HELIUS_PROVIDER_NAME",
    "HELIUS_SOURCE_KIND",
    "HeliusAdapterError",
    "HeliusClientFetchError",
    "HeliusClientProtocol",
    "HeliusClientResponseFieldTypeError",
    "HeliusClientResponseFieldValueError",
    "HeliusClientResponseShapeError",
    "HeliusProviderAdapter",
    "REQUIRED_CLIENT_RESPONSE_KEYS",
]
