"""Stage 29.5 Helius WebSocket migration evidence adapter
boundary.

Stage 29.5 admits a Helius WebSocket boundary as a migration
evidence source. At Stage 29.5.1 the boundary ships as a
Protocol-typed adapter that consumes an INJECTED WebSocket
transport. The Stage 29.5.1 commit ships NO real WebSocket
client class. The transport Protocol surface is what makes the
adapter testable against offline fake payloads.

A future operator-authorized substage may ship a concrete
``websockets``-library (or stdlib socket) transport behind the
Protocol; Stage 29.5.1 does not.

The adapter:

  * accepts one bounded scan call per invocation
    (``max_messages_to_read`` default 64, capped at 1024);
  * accepts one optional caller-supplied clock that returns an
    ISO-8601 UTC string for ``observed_at_utc`` stamping;
  * parses each received ``bytes`` / ``str`` message as JSON;
  * validates the JSON shape against the Stage 29.5 closed-set
    rules;
  * never fabricates a base_mint, pool_account, pool_program_id,
    quote_mint, migration_timestamp_utc, or migration_slot when
    the upstream payload did not supply one (the adapter emits
    ``migration_status=INVALID`` with the missing axes as
    ``None``);
  * never emits ``migration_source=SYNTHETIC_TEST_ONLY`` (the
    adapter is a production migration evidence source — only
    test fixtures emit ``SYNTHETIC_TEST_ONLY``);
  * returns a bounded tuple of
    :class:`Stage29_5MigrationEvidenceRecord` instances;
  * raises :class:`Stage29_5MigrationEvidenceError` with a
    closed-set ``refusal_reason`` when the transport itself
    fails or when the budget is exhausted before reading any
    message.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` /
    ``os.environb`` are never touched.
  * No real network. No ``websockets`` / ``websocket-client`` /
    ``aiohttp`` / ``socket`` import. No outbound TCP. No TLS
    handshake.
  * No third-party runtime dependency. The adapter imports
    only stdlib (``json`` / ``typing``) plus the Stage 29.5
    models module.
  * No top-level Call (no implicit I/O at import time).
  * No PHX1 import path. No legacy phoenix-1 import path.
"""

from __future__ import annotations

import json
from typing import (
    Callable,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_BUDGET_EXCEEDED,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_UNSUPPORTED_KIND,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
)


# ---------------------------------------------------------------------------
# Adapter bounds
# ---------------------------------------------------------------------------


STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ: int = 64
STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ: int = 1024


# Expected Stage 29.5 Helius WS migration message kind. The
# adapter only admits this kind; other kinds are refused with
# ``UNSUPPORTED_KIND``. The string lives here (not in a constants
# module) because Stage 29.5 has no separate constants module and
# the manifest re-exports this token.
STAGE29_5_HELIUS_WS_MIGRATION_KIND: str = "PUMP_AMM_MIGRATION"


# ---------------------------------------------------------------------------
# Injected WebSocket transport Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage29_5WebSocketTransport(Protocol):
    """Protocol shape for the injected Stage 29.5 WebSocket
    transport.

    Implementations may consume messages from a real Helius
    WebSocket (a future operator-authorized substage) or from a
    deterministic fake fixture (the Stage 29.5.1 test suite).
    Either way, the adapter only interacts with the transport
    through this Protocol.
    """

    def recv_one_message(
        self, timeout_seconds: float
    ) -> Optional[bytes]:
        """Return one upstream message as ``bytes``, or ``None``
        when the transport is exhausted within the supplied
        timeout. Implementations MUST NOT raise on a clean
        timeout; they may raise ``Stage29_5MigrationEvidenceError``
        with ``refusal_reason in {MALFORMED_PAYLOAD, SOURCE_INVALID}``
        when the underlying connection produced a non-message
        error.
        """
        ...

    def close(self) -> None:
        """Close the transport. Idempotent. Must not raise."""
        ...


# ---------------------------------------------------------------------------
# Message parser
# ---------------------------------------------------------------------------


def _decode_message_body(
    body: object,
) -> dict:
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_MALFORMED_PAYLOAD,
                "non-utf-8 message body",
            ) from exc
    elif isinstance(body, str):
        text = body
    else:
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "message body is not bytes or str",
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "message body is not valid JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "message body is not a JSON object",
        )
    return parsed


def _coerce_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _coerce_optional_nonneg_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def parse_helius_ws_migration_message(
    body: object,
    observed_at_utc: str,
) -> Stage29_5MigrationEvidenceRecord:
    """Pure function — parse one Helius WS migration message
    into a :class:`Stage29_5MigrationEvidenceRecord`.

    Behavior:

      * Refuses non-JSON / non-object bodies with
        ``Stage29_5MigrationEvidenceError(REFUSAL_REASON_MALFORMED_PAYLOAD)``.
      * Refuses an unexpected ``kind`` field with
        ``Stage29_5MigrationEvidenceError(REFUSAL_REASON_UNSUPPORTED_KIND)``.
      * Emits ``migration_status=PRESENT`` +
        ``migration_source=HELIUS_WS`` when the four required
        axes + ``migration_timestamp_utc`` are all populated
        with safe-shape values.
      * Emits ``migration_status=INVALID`` +
        ``migration_source=HELIUS_WS`` when the ``kind`` matches
        but at least one required axis is missing or
        unsafe-shaped.
      * NEVER emits ``migration_source=SYNTHETIC_TEST_ONLY``.
      * NEVER fabricates an axis value the upstream payload did
        not supply.
    """
    if not is_safe_iso8601_utc_string(observed_at_utc):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "observed_at_utc must be a UTC-shaped ISO-8601 "
            "string",
        )
    parsed = _decode_message_body(body)
    kind_value = parsed.get("kind")
    if (
        not isinstance(kind_value, str)
        or kind_value
        != STAGE29_5_HELIUS_WS_MIGRATION_KIND
    ):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNSUPPORTED_KIND,
            f"expected kind={STAGE29_5_HELIUS_WS_MIGRATION_KIND}; "
            f"got kind={kind_value!r}",
        )
    base_mint_raw = _coerce_optional_string(
        parsed.get("base_mint")
    )
    pool_account_raw = _coerce_optional_string(
        parsed.get("pool_account")
    )
    pool_program_id_raw = _coerce_optional_string(
        parsed.get("pool_program_id")
    )
    quote_mint_raw = _coerce_optional_string(
        parsed.get("quote_mint")
    )
    migration_timestamp_raw = _coerce_optional_string(
        parsed.get("migration_timestamp_utc")
    )
    migration_slot_raw = _coerce_optional_nonneg_int(
        parsed.get("migration_slot")
    )
    migration_signature_raw = _coerce_optional_string(
        parsed.get("migration_signature")
    )
    source_event_ref_raw = _coerce_optional_string(
        parsed.get("source_event_ref")
    )
    safe_quartet_axes = (
        base_mint_raw
        if (
            base_mint_raw is not None
            and is_safe_mint_or_pool_string(base_mint_raw)
        )
        else None,
        pool_account_raw
        if (
            pool_account_raw is not None
            and is_safe_mint_or_pool_string(pool_account_raw)
        )
        else None,
        pool_program_id_raw
        if (
            pool_program_id_raw is not None
            and is_safe_mint_or_pool_string(
                pool_program_id_raw
            )
        )
        else None,
        quote_mint_raw
        if (
            quote_mint_raw is not None
            and is_safe_mint_or_pool_string(quote_mint_raw)
        )
        else None,
    )
    safe_timestamp = (
        migration_timestamp_raw
        if (
            migration_timestamp_raw is not None
            and is_safe_iso8601_utc_string(
                migration_timestamp_raw
            )
        )
        else None
    )
    quartet_complete = all(
        axis is not None for axis in safe_quartet_axes
    )
    if quartet_complete and safe_timestamp is not None:
        return Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=safe_quartet_axes[0],
            pool_account=safe_quartet_axes[1],
            pool_program_id=safe_quartet_axes[2],
            quote_mint=safe_quartet_axes[3],
            migration_timestamp_utc=safe_timestamp,
            migration_slot=migration_slot_raw,
            migration_signature=migration_signature_raw,
            observed_at_utc=observed_at_utc,
            source_event_ref=source_event_ref_raw,
        )
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=safe_quartet_axes[0],
        pool_account=safe_quartet_axes[1],
        pool_program_id=safe_quartet_axes[2],
        quote_mint=safe_quartet_axes[3],
        migration_timestamp_utc=safe_timestamp,
        migration_slot=migration_slot_raw,
        migration_signature=migration_signature_raw,
        observed_at_utc=observed_at_utc,
        source_event_ref=source_event_ref_raw,
    )


def _empty_missing_record(
    observed_at_utc: str,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class Stage29_5HeliusWebSocketAdapter:
    """Stage 29.5 Helius WebSocket migration evidence adapter.

    Composition over an injected
    :class:`Stage29_5WebSocketTransport`. The transport is the
    sole source of bytes; the adapter never opens its own
    socket.

    Construction takes:

      * the injected transport
      * a clock callable returning a UTC-shaped ISO-8601 string
      * an optional ``max_messages_to_read`` budget (default 64,
        capped at 1024)
      * an optional ``per_message_timeout_seconds`` (default
        5.0, capped at 30.0)
      * an optional ``include_missing_when_empty`` flag (default
        False) controlling whether a fully-empty scan returns an
        empty tuple (default) or a single
        ``migration_status=MISSING`` placeholder record.

    No env reads. No outbound network. No subscriber surface.
    """

    def __init__(
        self,
        transport: Stage29_5WebSocketTransport,
        clock: Callable[[], str],
        max_messages_to_read: int = (
            STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ
        ),
        per_message_timeout_seconds: float = 5.0,
        include_missing_when_empty: bool = False,
    ) -> None:
        if not isinstance(
            max_messages_to_read, int
        ) or isinstance(max_messages_to_read, bool):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_messages_to_read must be an int",
            )
        if max_messages_to_read < 1:
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_messages_to_read must be >= 1",
            )
        if (
            max_messages_to_read
            > STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ
        ):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_messages_to_read must be <= "
                f"{STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ}",
            )
        if not (
            isinstance(per_message_timeout_seconds, (int, float))
            and not isinstance(
                per_message_timeout_seconds, bool
            )
            and per_message_timeout_seconds > 0.0
            and per_message_timeout_seconds <= 30.0
        ):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "per_message_timeout_seconds must be a positive "
                "number <= 30.0",
            )
        if not callable(clock):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_MALFORMED_PAYLOAD,
                "clock must be callable",
            )
        if not isinstance(transport, Stage29_5WebSocketTransport):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_MALFORMED_PAYLOAD,
                "transport must implement "
                "Stage29_5WebSocketTransport",
            )
        if not isinstance(include_missing_when_empty, bool):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_MALFORMED_PAYLOAD,
                "include_missing_when_empty must be bool",
            )
        self._transport: Stage29_5WebSocketTransport = transport
        self._clock: Callable[[], str] = clock
        self._max_messages_to_read: int = max_messages_to_read
        self._per_message_timeout_seconds: float = float(
            per_message_timeout_seconds
        )
        self._include_missing_when_empty: bool = (
            include_missing_when_empty
        )

    def read_migration_evidence_batch(
        self,
    ) -> Tuple[Stage29_5MigrationEvidenceRecord, ...]:
        """Read up to ``max_messages_to_read`` messages from the
        injected transport and parse them into migration
        evidence records.

        Behavior:

          * One transport timeout ends the batch (treated as end
            of stream).
          * One malformed JSON payload raises a closed-set
            :class:`Stage29_5MigrationEvidenceError`. The caller
            decides whether to retry; this adapter never silently
            swallows a parse failure.
          * One ``UNSUPPORTED_KIND`` payload is silently
            skipped — it is a valid non-migration message on the
            Helius stream and must not blow up the batch.
          * Returns a frozen tuple of evidence records;
            ``include_missing_when_empty=True`` injects one
            ``migration_status=MISSING`` record when the batch
            saw zero migration messages.
        """
        out: list = []
        read_count = 0
        while read_count < self._max_messages_to_read:
            message = self._transport.recv_one_message(
                self._per_message_timeout_seconds
            )
            if message is None:
                break
            read_count += 1
            observed_at_utc = self._clock()
            if not is_safe_iso8601_utc_string(
                observed_at_utc
            ):
                raise Stage29_5MigrationEvidenceError(
                    REFUSAL_REASON_MALFORMED_PAYLOAD,
                    "clock returned non-UTC-shaped string",
                )
            try:
                record = parse_helius_ws_migration_message(
                    message, observed_at_utc
                )
            except Stage29_5MigrationEvidenceError as exc:
                if (
                    exc.refusal_reason
                    == REFUSAL_REASON_UNSUPPORTED_KIND
                ):
                    continue
                raise
            out.append(record)
        if not out and self._include_missing_when_empty:
            observed_at_utc = self._clock()
            if not is_safe_iso8601_utc_string(
                observed_at_utc
            ):
                raise Stage29_5MigrationEvidenceError(
                    REFUSAL_REASON_MALFORMED_PAYLOAD,
                    "clock returned non-UTC-shaped string",
                )
            out.append(
                _empty_missing_record(observed_at_utc)
            )
        return tuple(out)

    def close(self) -> None:
        """Close the injected transport."""
        self._transport.close()


__all__ = (
    "STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ",
    "STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ",
    "STAGE29_5_HELIUS_WS_MIGRATION_KIND",
    "Stage29_5WebSocketTransport",
    "Stage29_5HeliusWebSocketAdapter",
    "parse_helius_ws_migration_message",
)
