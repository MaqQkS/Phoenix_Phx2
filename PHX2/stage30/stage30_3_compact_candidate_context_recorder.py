"""Stage 30.3 compact candidate context recorder.

Pure / deterministic wrapper around a Stage 28.9-shaped inner
candidate assembler. The recorder forwards every ``assemble``
call to the inner assembler verbatim, captures a duck-typed
projection of the returned record onto a Stage 30.3
``Stage30_3RecordedCandidateContext`` entry, appends the entry
onto an internal tuple of recorded entries, and returns the
inner record byte-for-byte.

The Stage 30.3 wrapper consumes the most recent recorded entry
to produce a Stage 30.1 tier decision plus a Stage 30.2 compact
ping snapshot at each ``send_one_audited_post`` call. The
recorder itself NEVER opens a network connection, NEVER reads
the process environment, NEVER calls ``datetime.now`` (the clock
is caller-supplied), NEVER mutates its inputs.

Duck-typing discipline:

  * The inner assembler is validated for the presence of a
    callable ``assemble`` attribute. The recorder does NOT
    import any Stage 27 / Stage 28 / Stage 29 module.
  * The injected clock is validated for the presence of a
    callable ``now_utc_iso`` attribute. The Stage 30.3 wrapper
    re-reads the clock at every ``send_one_audited_post`` call
    via the same injection slot.
  * The returned record is duck-typed via ``getattr`` for the
    ``ingest_output.token_mint`` mint string, the
    ``measurement_context.ath_context`` / ``.migration_context``
    pair, and the ``rendered_ping.price_status`` echo. Stage
    30.1's projector is the validation boundary for the actual
    Stage 27.4 record types.

Age semantics:

  * The recorder reads the migration record's absolute UTC
    timestamp field ``migration_timestamp_utc`` and computes the
    integer seconds between the recorder clock's now-time and the
    migration timestamp. Negative ages floor to zero. Missing /
    unparseable timestamps produce ``None``. Any internal
    exception during the parse / arithmetic also produces
    ``None``.

Discipline:

  * Stdlib only (``datetime`` / ``typing``).
  * No Stage 27 / Stage 28 / Stage 29 import.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from PHX2.stage30.stage30_3_compact_runtime_models import (
    Stage30_3CompactRuntimeError,
    Stage30_3RecordedCandidateContext,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_iso_utc_to_aware(value: object) -> Optional[datetime]:
    """Parse an ISO-8601 UTC string into a timezone-aware
    ``datetime`` in UTC, or return ``None`` on any failure.

    Accepts the common ``...Z`` suffix and the explicit
    ``...+00:00`` form. Returns ``None`` for non-string / empty /
    unparseable / non-UTC-offset inputs.
    """
    if not isinstance(value, str):
        return None
    if value == "":
        return None
    try:
        normalized = value
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _derive_age_seconds(
    migration_record: object,
    clock_now_utc: str,
) -> Optional[int]:
    """Derive integer seconds since migration from the duck-typed
    migration record's absolute UTC timestamp and the recorder
    clock's now-time string.

    Returns ``None`` when the migration record is missing, when the
    timestamp field is missing / unparseable, or when any internal
    exception fires during the parse / arithmetic. Floors negative
    ages at zero so a wall-clock skew between the upstream
    migration timestamp and the recorder clock cannot produce a
    negative age value.
    """
    if migration_record is None:
        return None
    try:
        migration_ts = getattr(
            migration_record, "migration_timestamp_utc", None
        )
        migration_dt = _parse_iso_utc_to_aware(migration_ts)
        if migration_dt is None:
            return None
        clock_dt = _parse_iso_utc_to_aware(clock_now_utc)
        if clock_dt is None:
            return None
        delta_seconds = int(
            (clock_dt - migration_dt).total_seconds()
        )
        if delta_seconds < 0:
            return 0
        return delta_seconds
    except Exception:
        return None


def _safe_str_or_none(value: object) -> Optional[str]:
    """Return ``value`` if it is a string, else ``None``.

    Does NOT shape-check; Stage 30.1 / Stage 30.2 downstream
    sanitize the actual shape (base58 / safe-identifier / closed-
    set token).
    """
    if isinstance(value, str):
        return value
    return None


def _project_to_recorded(
    record: object,
    *,
    candidate_id: str,
    recorded_at_utc: str,
) -> Stage30_3RecordedCandidateContext:
    """Project ``record`` onto a Stage 30.3 recorded entry via
    duck-typing.

    The projection reads exactly four slots off the inner record:

      * ``ingest_output.token_mint``                  -- the Solana
                                                         base58 mint.
      * ``measurement_context.ath_context``           -- the Stage
                                                         27.4 ATH
                                                         record.
      * ``measurement_context.migration_context``     -- the Stage
                                                         27.4
                                                         migration
                                                         record.
      * ``rendered_ping.price_status``                -- the Stage
                                                         27.4
                                                         PRICE_STATUS
                                                         echo.

    Missing attributes resolve to ``None``. The Stage 30.1
    projector validates the actual Stage 27.4 record types
    downstream; the recorder never raises on a duck-type miss.
    """
    ingest_output = getattr(record, "ingest_output", None)
    mint_value = getattr(ingest_output, "token_mint", None)
    mint = _safe_str_or_none(mint_value)

    measurement_context = getattr(record, "measurement_context", None)
    if measurement_context is not None:
        ath_record: Optional[object] = getattr(
            measurement_context, "ath_context", None
        )
        migration_record: Optional[object] = getattr(
            measurement_context, "migration_context", None
        )
    else:
        ath_record = None
        migration_record = None

    rendered_ping = getattr(record, "rendered_ping", None)
    if rendered_ping is not None:
        price_status_value = getattr(
            rendered_ping, "price_status", None
        )
        price_status = _safe_str_or_none(price_status_value)
    else:
        price_status = None

    age_seconds = _derive_age_seconds(
        migration_record, recorded_at_utc
    )

    return Stage30_3RecordedCandidateContext(
        candidate_id=candidate_id,
        mint=mint,
        ath_record=ath_record,
        migration_record=migration_record,
        price_status=price_status,
        age_since_migration_seconds=age_seconds,
        recorded_at_utc=recorded_at_utc,
    )


# ---------------------------------------------------------------------------
# Public recorder
# ---------------------------------------------------------------------------


class Stage30_3CompactCandidateContextRecorder:
    """Stage 30.3 compact candidate context recorder.

    Wraps a Stage 28.9-shaped inner candidate assembler. Each
    ``assemble`` call forwards verbatim to the inner assembler,
    captures a duck-typed projection of the returned record onto
    a Stage 30.3 ``Stage30_3RecordedCandidateContext`` entry,
    appends the entry onto an internal tuple of recorded entries,
    and returns the inner record byte-for-byte.

    The Stage 30.3 wrapper consumes the most recent recorded
    entry to produce a Stage 30.1 tier decision plus a Stage
    30.2 compact ping snapshot at each ``send_one_audited_post``
    call.

    The recorder NEVER opens a network connection, NEVER reads
    the process environment, NEVER calls ``datetime.now`` (the
    clock is caller-supplied), NEVER mutates its inputs, NEVER
    swallows inner-assembler exceptions (they propagate verbatim
    so the Stage 28.6 runner's outer try/except still fires).
    """

    __slots__ = (
        "_inner_assembler",
        "_clock",
        "_recorded_entries",
    )

    def __init__(
        self,
        *,
        inner_assembler: object,
        clock: object,
    ) -> None:
        if not callable(getattr(inner_assembler, "assemble", None)):
            raise Stage30_3CompactRuntimeError(
                "INNER_ASSEMBLER_INVALID"
            )
        if not callable(getattr(clock, "now_utc_iso", None)):
            raise Stage30_3CompactRuntimeError("CLOCK_INVALID")
        self._inner_assembler: object = inner_assembler
        self._clock: object = clock
        self._recorded_entries: Tuple[
            Stage30_3RecordedCandidateContext, ...
        ] = ()

    @property
    def recorded_entries(
        self,
    ) -> Tuple[Stage30_3RecordedCandidateContext, ...]:
        """Return the immutable tuple of recorded entries in
        insertion order.
        """
        return self._recorded_entries

    def assemble(
        self,
        normalized_event: object,
        *,
        candidate_id: str,
    ) -> object:
        """Forward one ``assemble`` call to the inner assembler,
        capture a Stage 30.3 recorded entry, and return the inner
        record verbatim.

        Inner-assembler exceptions propagate verbatim. The
        recorder does NOT swallow them; the Stage 28.6 runner's
        outer try/except handles the per-event failure.

        The recorder clock's ``now_utc_iso()`` is invoked once per
        call, immediately AFTER a successful inner-assembler
        return, so the recorded ``recorded_at_utc`` strictly
        post-dates the inner assembler's wall-clock observation
        time.
        """
        record = self._inner_assembler.assemble(
            normalized_event, candidate_id=candidate_id
        )
        recorded_at_utc = self._clock.now_utc_iso()
        entry = _project_to_recorded(
            record,
            candidate_id=candidate_id,
            recorded_at_utc=recorded_at_utc,
        )
        self._recorded_entries = self._recorded_entries + (entry,)
        return record


__all__ = (
    "Stage30_3CompactCandidateContextRecorder",
)
