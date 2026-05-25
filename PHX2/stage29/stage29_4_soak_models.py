"""Stage 29.4 short-session private soak models.

Closed-set vocabularies + immutable frozen dataclasses for the
Stage 29.4 bounded short-session private tradeable soak around
the Stage 29.3 first private tradeable smoke.

Stage 29.4 composes the Stage 29.3 single-shot ceremony into a
bounded outer loop with cross-pass in-memory dedupe. Stage 29.4
ships NO daemon, NO infinite loop, NO public / subscriber /
paid-tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer surface, NO new env
names, NO new third-party dependencies, NO PHX1 / Phoenix_Bot
import path, NO Stage 26 enforcement activation, NO persistent
dedupe index.

This module ships only:

  * the locked Stage 29.4 version axes (minor / schema versions
    for the four artifact shapes / redaction token),
  * the closed-set probe-mode vocabulary (the three operator-
    supplied ceremony modes),
  * the closed-set Stage 29.4 soak-outcome vocabulary (the eight
    final soak summary tokens),
  * the closed-set Stage 29.4 dedupe-outcome vocabulary (the two
    cross-pass dedupe outcomes),
  * the closed-set redaction-status vocabulary,
  * the locked filter-enforcement-status marker,
  * the recommended bound ranges (documentation-only),
  * the immutable ``Stage29_4SoakBounds`` /
    ``Stage29_4SoakDedupeKey`` / ``Stage29_4PassRecord`` /
    ``Stage29_4SoakSummary`` / ``Stage29_4PassResult`` records,
  * the module-local Stage 29.4 exception hierarchy.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No Discord. No file I/O at
    import or call time.
  * No third-party dependency. Stdlib only (``dataclasses`` /
    ``typing``).
  * No raw secret value is ever carried on a Stage 29.4 record.
    Closed-set tokens / safe counters / safe identifiers only.
  * ``repr()`` / ``str()`` of any Stage 29.4 record is safe to log
    / print / persist.

Stage 29.4 ships NO public routing, NO subscriber routing, NO
paid tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO Stage 26 policy enforcement
activation, NO Pump.fun bonding-curve decoder, NO Dexscreener as
a dispatch authority, NO Helius as a price source, NO third or
fourth provider beyond Stage 28.11 (Chainstack) + Stage 29.2
(Birdeye), NO daemon / watchdog / autorestart loop, NO PHX1 /
Phoenix-1 import path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 29.4 version axes
# ---------------------------------------------------------------------------


STAGE29_4_MINOR_VERSION: str = "29.4"


STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION: str = (
    "stage29_4_soak_summary_v0"
)
STAGE29_4_HEARTBEAT_SCHEMA_VERSION: str = (
    "stage29_4_heartbeat_v0"
)
STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION: str = (
    "stage29_4_health_snapshot_v0"
)
STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION: str = (
    "stage29_4_redaction_scan_v0"
)


STAGE29_4_REDACTION_TOKEN: str = "<<STAGE29_4_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: probe mode (the three operator-supplied ceremony modes)
# ---------------------------------------------------------------------------


PROBE_MODE_READINESS_ONLY: str = "READINESS_ONLY"
PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY: str = (
    "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY"
)
PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN: str = (
    "SHORT_SESSION_PRIVATE_SOAK_DRY_RUN"
)


PROBE_MODE_VALUES: tuple[str, ...] = (
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN,
)


def is_probe_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in PROBE_MODE_VALUES


# ---------------------------------------------------------------------------
# Closed-set: soak outcome (the eight Stage 29.4 final-record outcomes)
# ---------------------------------------------------------------------------


SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP: str = (
    "COMPLETED_AT_DISPATCH_CAP"
)
SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK: str = (
    "COMPLETED_AT_WALL_CLOCK"
)
SOAK_OUTCOME_COMPLETED_AT_PASS_CAP: str = (
    "COMPLETED_AT_PASS_CAP"
)
SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT: str = (
    "BROKE_ON_SUPPRESSION_CIRCUIT"
)
SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS: str = (
    "BROKE_ON_REFUSED_READINESS"
)
SOAK_OUTCOME_BROKE_ON_FAILED_PASS: str = (
    "BROKE_ON_FAILED_PASS"
)
SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS: str = (
    "NO_DISPATCHES_NO_EVENTS"
)
SOAK_OUTCOME_REFUSED_INVALID_BOUNDS: str = (
    "REFUSED_INVALID_BOUNDS"
)


SOAK_OUTCOME_VALUES: tuple[str, ...] = (
    SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
    SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK,
    SOAK_OUTCOME_COMPLETED_AT_PASS_CAP,
    SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT,
    SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS,
    SOAK_OUTCOME_BROKE_ON_FAILED_PASS,
    SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS,
    SOAK_OUTCOME_REFUSED_INVALID_BOUNDS,
)


def is_soak_outcome_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in SOAK_OUTCOME_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: cross-pass dedupe outcome (NEW / DUPLICATE_SUPPRESSED_SOAK)
# ---------------------------------------------------------------------------


DEDUPE_OUTCOME_NEW: str = "NEW"
DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK: str = (
    "DUPLICATE_SUPPRESSED_SOAK"
)


DEDUPE_OUTCOME_VALUES: tuple[str, ...] = (
    DEDUPE_OUTCOME_NEW,
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
)


def is_dedupe_outcome_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in DEDUPE_OUTCOME_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction status (SAFE / REDACTED)
# ---------------------------------------------------------------------------


REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
)


def is_redaction_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Locked: filter-enforcement status marker
# ---------------------------------------------------------------------------


# Stage 29.4 explicitly does NOT activate Stage 26 / Stage 29
# policy enforcement. The locked marker pins this on every Stage
# 29.4 soak-summary record and on every per-pass record so a
# downstream reader can rely on the value to gate against
# enforcement-on assumptions.
FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING: str = (
    "NOT_ACTIVE_STAGE_29_PENDING"
)


# ---------------------------------------------------------------------------
# Recommended bound ranges (documentation; the orchestrator admits
# bounds outside these ranges but logs them on the soak summary)
# ---------------------------------------------------------------------------


# Inclusive recommended ranges per Stage 29.4 runbook Section 3.
RECOMMENDED_WALL_CLOCK_SECONDS_MIN: int = 600
RECOMMENDED_WALL_CLOCK_SECONDS_MAX: int = 1800
RECOMMENDED_MAX_DISPATCHES_MIN: int = 3
RECOMMENDED_MAX_DISPATCHES_MAX: int = 5
RECOMMENDED_MAX_PASSES_MIN: int = 3
RECOMMENDED_MAX_PASSES_MAX: int = 60
RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MIN: int = 3
RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MAX: int = 20
RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MIN: int = 10
RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MAX: int = 60


# Per-pass internal Stage 29.3 locks. Stage 29.4 inherits these
# verbatim; the soak orchestrator never adjusts them.
PER_PASS_MAX_EVENTS: int = 1
PER_PASS_MAX_DISPATCHES: int = 1
PER_PASS_MAX_TOTAL_RETRIES: int = 0


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage29_4SoakError(Exception):
    """Base type for every Stage 29.4 soak validation error.

    Module-local; not a subclass of any central PHX2 error registry.
    The constructor NEVER carries a raw upstream payload, a raw env
    value, a raw URL, or a raw secret; callers pass only closed-set
    tokens.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 29.4 soak error: reason={reason!r}"
        )


class Stage29_4InvalidBoundsError(Stage29_4SoakError):
    """Raised when ``Stage29_4SoakBounds`` validation fails.

    Carries only the closed-set field name + reason token; never
    the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"INVALID_SOAK_BOUNDS_FIELD::{field_name}::{reason}"
        )
        self.field_name: str = field_name
        self.reason: str = reason


class Stage29_4InvalidDedupeKeyError(Stage29_4SoakError):
    """Raised when a ``Stage29_4SoakDedupeKey`` field fails the
    locked validation contract.

    Carries only the closed-set field name + reason token; never
    the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"INVALID_SOAK_DEDUPE_KEY_FIELD::"
            f"{field_name}::{reason}"
        )
        self.field_name: str = field_name
        self.reason: str = reason


class Stage29_4InvalidPassRecordError(Stage29_4SoakError):
    """Raised when a ``Stage29_4PassRecord`` field fails the locked
    validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"INVALID_PASS_RECORD_FIELD::"
            f"{field_name}::{reason}"
        )
        self.field_name: str = field_name
        self.reason: str = reason


class Stage29_4InvalidSoakSummaryError(Stage29_4SoakError):
    """Raised when a ``Stage29_4SoakSummary`` field fails the locked
    validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"INVALID_SOAK_SUMMARY_FIELD::"
            f"{field_name}::{reason}"
        )
        self.field_name: str = field_name
        self.reason: str = reason


# ---------------------------------------------------------------------------
# Safe-counter helper (matches Stage 28.5 / Stage 29.3 discipline)
# ---------------------------------------------------------------------------


def _is_safe_counter(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    if value < 0:
        return False
    return True


def _is_safe_nonneg_float(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if not isinstance(value, float):
        return False
    if value != value:  # NaN
        return False
    if value < 0:
        return False
    # Reject inf as well.
    if value == float("inf") or value == float("-inf"):
        return False
    return True


# ---------------------------------------------------------------------------
# Safe-shape ISO-8601 UTC timestamp validation
# ---------------------------------------------------------------------------


_UTC_ISO_ALLOWED_CHARS: frozenset[str] = frozenset(
    "0123456789-:.T+Z"
)
_UTC_ISO_MIN_LENGTH: int = 18
_UTC_ISO_MAX_LENGTH: int = 40


def _is_safe_utc_iso(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < _UTC_ISO_MIN_LENGTH:
        return False
    if len(value) > _UTC_ISO_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _UTC_ISO_ALLOWED_CHARS:
            return False
    return True


# ---------------------------------------------------------------------------
# Stage 29.4 dedupe key
# ---------------------------------------------------------------------------


# Stage 29.4 dedupe-key field allowlist character class. Matches
# the Stage 28.2 ``DispatchDedupeKey`` field shape (mints / pair
# quote tokens / event-kind tags / ping-type tags / normalized
# event ids). The allowlist keeps a key field to letters, digits,
# underscore, and dash, with strict length caps. URL / bearer /
# secret material cannot pass this allowlist.
_SOAK_DEDUPE_KEY_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_SOAK_DEDUPE_KEY_FIELD_MIN_LENGTH: int = 1
_SOAK_DEDUPE_KEY_FIELD_MAX_LENGTH: int = 128


_SOAK_DEDUPE_KEY_FIELD_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    "password",
    "passwd",
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
)


def _is_safe_soak_dedupe_key_field(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < _SOAK_DEDUPE_KEY_FIELD_MIN_LENGTH:
        return False
    if len(value) > _SOAK_DEDUPE_KEY_FIELD_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _SOAK_DEDUPE_KEY_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _SOAK_DEDUPE_KEY_FIELD_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


SOAK_DEDUPE_KEY_FIELD_NAMES: tuple[str, ...] = (
    "token_mint",
    "pair_quote_asset",
    "event_kind",
    "ping_type",
    "normalized_event_id",
)


@dataclass(frozen=True)
class Stage29_4SoakDedupeKey:
    """Immutable Stage 29.4 cross-pass soak dedupe key.

    Mirrors the Stage 28.2 ``DispatchDedupeKey`` field shape. The
    key carries only closed-set / opaque identifiers; webhook URLs,
    run / session ids, wall-clock timestamps, RPC endpoints, API
    keys, bearer tokens, auth headers, recipient / subscriber
    fields, paid-tier markers are NEVER carried.

    Fields:

      * ``token_mint`` -- Solana base58 mint or opaque mint
        identifier (Stage 28.2 / Stage 27 mint axis).
      * ``pair_quote_asset`` -- closed-set Stage 27 pair-classifier
        quote token (e.g. ``SOL`` / ``USDC`` / ``UNKNOWN``).
      * ``event_kind`` -- closed-set Stage 27 event-kind tag.
      * ``ping_type`` -- closed-set Stage 27 ping-type tag (e.g.
        ``tradeable_private_ping``).
      * ``normalized_event_id`` -- deterministic Stage 27 event id
        that survives restart and is stable across passes.

    The frozen-dataclass shape gives the record built-in
    immutability, structural equality, and a safe ``repr()`` that
    exposes only the closed-set field values.
    """

    token_mint: str
    pair_quote_asset: str
    event_kind: str
    ping_type: str
    normalized_event_id: str

    def __post_init__(self) -> None:
        for name in SOAK_DEDUPE_KEY_FIELD_NAMES:
            value = getattr(self, name)
            if not _is_safe_soak_dedupe_key_field(value):
                raise Stage29_4InvalidDedupeKeyError(
                    field_name=name,
                    reason="DEDUPE_KEY_FIELD_NOT_SAFE",
                )


def build_soak_dedupe_key(
    *,
    token_mint: str,
    pair_quote_asset: str,
    event_kind: str,
    ping_type: str,
    normalized_event_id: str,
) -> Stage29_4SoakDedupeKey:
    """Construct an immutable ``Stage29_4SoakDedupeKey`` with full
    validation. Raises ``Stage29_4InvalidDedupeKeyError`` for any
    field that fails the locked allowlist.
    """
    return Stage29_4SoakDedupeKey(
        token_mint=token_mint,
        pair_quote_asset=pair_quote_asset,
        event_kind=event_kind,
        ping_type=ping_type,
        normalized_event_id=normalized_event_id,
    )


def canonical_soak_dedupe_key_tuple(
    key: Stage29_4SoakDedupeKey,
) -> Tuple[str, str, str, str, str]:
    """Project a ``Stage29_4SoakDedupeKey`` into a deterministic
    tuple suitable for use as a Python ``dict`` / ``set`` key.

    Pure / deterministic. Stable across processes.
    """
    if not isinstance(key, Stage29_4SoakDedupeKey):
        raise Stage29_4InvalidDedupeKeyError(
            field_name="key",
            reason="NOT_A_SOAK_DEDUPE_KEY",
        )
    return (
        key.token_mint,
        key.pair_quote_asset,
        key.event_kind,
        key.ping_type,
        key.normalized_event_id,
    )


# ---------------------------------------------------------------------------
# Stage 29.4 soak bounds
# ---------------------------------------------------------------------------


SOAK_BOUNDS_FIELD_NAMES: tuple[str, ...] = (
    "wall_clock_seconds",
    "max_dispatches",
    "max_passes",
    "max_total_retries",
    "max_consecutive_suppressions",
    "heartbeat_cadence_seconds",
)


@dataclass(frozen=True)
class Stage29_4SoakBounds:
    """Immutable Stage 29.4 soak bounds.

    Every bound is required, finite, and positive (except
    ``max_total_retries`` which is locked at exactly 0). The
    orchestrator rejects bounds outside these rules with the
    closed-set ``REFUSED_INVALID_BOUNDS`` soak outcome.

    Fields:

      * ``wall_clock_seconds`` -- the soak's overall wall-clock cap.
      * ``max_dispatches`` -- the soak's overall dispatch cap; the
        soak completes with ``COMPLETED_AT_DISPATCH_CAP`` when this
        many private dispatches succeed.
      * ``max_passes`` -- the soak's overall outer-loop iteration
        cap.
      * ``max_total_retries`` -- locked at ``0``; the soak does not
        invoke Stage 28.3b transport retries.
      * ``max_consecutive_suppressions`` -- the soak's suppression
        circuit-breaker; the soak completes with
        ``BROKE_ON_SUPPRESSION_CIRCUIT`` when this many consecutive
        Stage 29.3 ``SUPPRESSED_*`` outcomes appear before any
        dispatch.
      * ``heartbeat_cadence_seconds`` -- the documented heartbeat
        cadence; the soak emits one heartbeat per pass.
    """

    wall_clock_seconds: int
    max_dispatches: int
    max_passes: int
    max_total_retries: int
    max_consecutive_suppressions: int
    heartbeat_cadence_seconds: int

    def __post_init__(self) -> None:
        _validate_soak_bounds(self)


def _validate_soak_bounds(bounds: "Stage29_4SoakBounds") -> None:
    if not _is_safe_counter(bounds.wall_clock_seconds) or (
        bounds.wall_clock_seconds <= 0
    ):
        raise Stage29_4InvalidBoundsError(
            field_name="wall_clock_seconds",
            reason="WALL_CLOCK_SECONDS_NOT_POSITIVE_INT",
        )
    if not _is_safe_counter(bounds.max_dispatches) or (
        bounds.max_dispatches <= 0
    ):
        raise Stage29_4InvalidBoundsError(
            field_name="max_dispatches",
            reason="MAX_DISPATCHES_NOT_POSITIVE_INT",
        )
    if not _is_safe_counter(bounds.max_passes) or (
        bounds.max_passes <= 0
    ):
        raise Stage29_4InvalidBoundsError(
            field_name="max_passes",
            reason="MAX_PASSES_NOT_POSITIVE_INT",
        )
    if not _is_safe_counter(bounds.max_total_retries):
        raise Stage29_4InvalidBoundsError(
            field_name="max_total_retries",
            reason="MAX_TOTAL_RETRIES_NOT_NONNEG_INT",
        )
    if bounds.max_total_retries != PER_PASS_MAX_TOTAL_RETRIES:
        raise Stage29_4InvalidBoundsError(
            field_name="max_total_retries",
            reason="MAX_TOTAL_RETRIES_NOT_EXACTLY_ZERO",
        )
    if not _is_safe_counter(
        bounds.max_consecutive_suppressions,
    ) or bounds.max_consecutive_suppressions <= 0:
        raise Stage29_4InvalidBoundsError(
            field_name="max_consecutive_suppressions",
            reason=(
                "MAX_CONSECUTIVE_SUPPRESSIONS_NOT_POSITIVE_INT"
            ),
        )
    if not _is_safe_counter(
        bounds.heartbeat_cadence_seconds,
    ) or bounds.heartbeat_cadence_seconds <= 0:
        raise Stage29_4InvalidBoundsError(
            field_name="heartbeat_cadence_seconds",
            reason="HEARTBEAT_CADENCE_SECONDS_NOT_POSITIVE_INT",
        )


def build_soak_bounds(
    *,
    wall_clock_seconds: int,
    max_dispatches: int,
    max_passes: int,
    max_consecutive_suppressions: int,
    heartbeat_cadence_seconds: int,
    max_total_retries: int = PER_PASS_MAX_TOTAL_RETRIES,
) -> Stage29_4SoakBounds:
    """Construct a ``Stage29_4SoakBounds`` record with full
    validation. Raises ``Stage29_4InvalidBoundsError`` for any
    field that fails the locked allowlist.
    """
    return Stage29_4SoakBounds(
        wall_clock_seconds=wall_clock_seconds,
        max_dispatches=max_dispatches,
        max_passes=max_passes,
        max_total_retries=max_total_retries,
        max_consecutive_suppressions=(
            max_consecutive_suppressions
        ),
        heartbeat_cadence_seconds=heartbeat_cadence_seconds,
    )


def soak_bounds_to_dict(bounds: Stage29_4SoakBounds) -> dict:
    """Project a ``Stage29_4SoakBounds`` into a deterministic-order
    dict suitable for canonical JSON encoding.
    """
    if not isinstance(bounds, Stage29_4SoakBounds):
        raise Stage29_4InvalidBoundsError(
            field_name="bounds",
            reason="NOT_A_SOAK_BOUNDS",
        )
    return {
        name: getattr(bounds, name)
        for name in SOAK_BOUNDS_FIELD_NAMES
    }


def bounds_within_recommended_ranges(
    bounds: Stage29_4SoakBounds,
) -> bool:
    """Return ``True`` iff every bound is within the recommended
    range from Stage 29.4 runbook Section 3.

    Used by the soak orchestrator as documentation-only metadata
    on the soak summary; bounds outside the recommended ranges are
    admitted but flagged on the summary.
    """
    if not (
        RECOMMENDED_WALL_CLOCK_SECONDS_MIN
        <= bounds.wall_clock_seconds
        <= RECOMMENDED_WALL_CLOCK_SECONDS_MAX
    ):
        return False
    if not (
        RECOMMENDED_MAX_DISPATCHES_MIN
        <= bounds.max_dispatches
        <= RECOMMENDED_MAX_DISPATCHES_MAX
    ):
        return False
    if not (
        RECOMMENDED_MAX_PASSES_MIN
        <= bounds.max_passes
        <= RECOMMENDED_MAX_PASSES_MAX
    ):
        return False
    if not (
        RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MIN
        <= bounds.max_consecutive_suppressions
        <= RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MAX
    ):
        return False
    if not (
        RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MIN
        <= bounds.heartbeat_cadence_seconds
        <= RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MAX
    ):
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 29.4 per-pass record
# ---------------------------------------------------------------------------


# Safe-shape stage29_3_outcome / refusal_reason character class.
# Closed-set tokens from Stage 29.3; we allow these axis values
# through as-is and validate basic shape.
_SAFE_OUTCOME_TOKEN_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_SAFE_OUTCOME_TOKEN_MIN_LENGTH: int = 1
_SAFE_OUTCOME_TOKEN_MAX_LENGTH: int = 64


def _is_safe_outcome_token(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_OUTCOME_TOKEN_MIN_LENGTH:
        return False
    if len(value) > _SAFE_OUTCOME_TOKEN_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_OUTCOME_TOKEN_ALLOWED_CHARS:
            return False
    return True


PASS_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "pass_index",
    "stage29_3_outcome",
    "stage29_3_refusal_reason",
    "dedupe_outcome",
    "events_seen",
    "candidates_dispatched",
    "candidates_suppressed",
    "dispatch_success",
    "dispatch_failure",
    "consecutive_suppression_streak",
    "dispatch_success_total_at_tick",
    "duplicate_suppressed_soak_count_at_tick",
    "elapsed_at_tick_seconds",
    "utc_iso_timestamp",
    "filter_enforcement_status",
    "redaction_status",
)


@dataclass(frozen=True)
class Stage29_4PassRecord:
    """Immutable Stage 29.4 per-pass record.

    Captures the per-pass projection the soak orchestrator emits
    into the Stage 29.4 heartbeat JSONL artifact. The record
    carries only closed-set tokens, safe counters, and safe-shape
    ISO-8601 timestamps; no webhook URL, RPC endpoint, API key,
    bearer token, auth header, raw provider payload, or raw
    exception string is ever carried.

    Fields:

      * ``pass_index`` -- 1-based pass index within the soak.
      * ``stage29_3_outcome`` -- closed-set Stage 29.3 outcome
        token observed on this pass.
      * ``stage29_3_refusal_reason`` -- closed-set Stage 29.3
        refusal-reason token; ``NONE`` iff the outcome is
        non-error.
      * ``dedupe_outcome`` -- closed-set Stage 29.4 dedupe outcome
        (``NEW`` / ``DUPLICATE_SUPPRESSED_SOAK``) or ``None`` when
        no dispatch candidate was deduped on this pass.
      * ``events_seen`` / ``candidates_dispatched`` /
        ``candidates_suppressed`` / ``dispatch_success`` /
        ``dispatch_failure`` -- per-pass safe counters mirrored
        from the Stage 29.3 smoke result.
      * ``consecutive_suppression_streak`` -- streak count at the
        end of this pass (reset to 0 on every non-SUPPRESSED_*
        outcome).
      * ``dispatch_success_total_at_tick`` -- soak-level
        cumulative dispatch success count at the end of this
        pass (NEW dedupe outcomes only).
      * ``duplicate_suppressed_soak_count_at_tick`` -- soak-level
        cumulative duplicate-suppressed count at the end of this
        pass.
      * ``elapsed_at_tick_seconds`` -- non-negative wall-clock
        seconds elapsed since the soak start.
      * ``utc_iso_timestamp`` -- safe-shape ISO-8601 UTC timestamp
        captured at the end of this pass.
      * ``filter_enforcement_status`` -- locked
        ``NOT_ACTIVE_STAGE_29_PENDING``.
      * ``redaction_status`` -- locked
        ``REDACTION_STATUS_SAFE`` on every well-formed record.
      * ``schema_version`` -- locked
        ``STAGE29_4_HEARTBEAT_SCHEMA_VERSION``.
    """

    pass_index: int
    stage29_3_outcome: str
    stage29_3_refusal_reason: str
    dedupe_outcome: Optional[str]
    events_seen: int
    candidates_dispatched: int
    candidates_suppressed: int
    dispatch_success: int
    dispatch_failure: int
    consecutive_suppression_streak: int
    dispatch_success_total_at_tick: int
    duplicate_suppressed_soak_count_at_tick: int
    elapsed_at_tick_seconds: float
    utc_iso_timestamp: str
    filter_enforcement_status: str = (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    redaction_status: str = REDACTION_STATUS_SAFE
    schema_version: str = STAGE29_4_HEARTBEAT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_pass_record_fields(self)


def _validate_pass_record_fields(
    record: "Stage29_4PassRecord",
) -> None:
    if (
        record.schema_version
        != STAGE29_4_HEARTBEAT_SCHEMA_VERSION
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="schema_version",
            reason="SCHEMA_VERSION_NOT_LOCKED",
        )
    if not _is_safe_counter(record.pass_index) or (
        record.pass_index <= 0
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="pass_index",
            reason="PASS_INDEX_NOT_POSITIVE_INT",
        )
    if not _is_safe_outcome_token(record.stage29_3_outcome):
        raise Stage29_4InvalidPassRecordError(
            field_name="stage29_3_outcome",
            reason="STAGE29_3_OUTCOME_NOT_SAFE_TOKEN",
        )
    if not _is_safe_outcome_token(
        record.stage29_3_refusal_reason,
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="stage29_3_refusal_reason",
            reason="STAGE29_3_REFUSAL_REASON_NOT_SAFE_TOKEN",
        )
    if record.dedupe_outcome is not None and (
        not is_dedupe_outcome_value(record.dedupe_outcome)
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="dedupe_outcome",
            reason="DEDUPE_OUTCOME_NOT_CLOSED_SET",
        )
    for name in (
        "events_seen",
        "candidates_dispatched",
        "candidates_suppressed",
        "dispatch_success",
        "dispatch_failure",
        "consecutive_suppression_streak",
        "dispatch_success_total_at_tick",
        "duplicate_suppressed_soak_count_at_tick",
    ):
        value = getattr(record, name)
        if not _is_safe_counter(value):
            raise Stage29_4InvalidPassRecordError(
                field_name=name,
                reason="COUNTER_NOT_NONNEG_INT",
            )
    if not _is_safe_nonneg_float(
        record.elapsed_at_tick_seconds,
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="elapsed_at_tick_seconds",
            reason="ELAPSED_AT_TICK_SECONDS_NOT_NONNEG_FLOAT",
        )
    if not _is_safe_utc_iso(record.utc_iso_timestamp):
        raise Stage29_4InvalidPassRecordError(
            field_name="utc_iso_timestamp",
            reason="UTC_ISO_TIMESTAMP_NOT_SAFE_SHAPE",
        )
    if (
        record.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        raise Stage29_4InvalidPassRecordError(
            field_name="filter_enforcement_status",
            reason="FILTER_ENFORCEMENT_STATUS_NOT_LOCKED",
        )
    if not is_redaction_status_value(record.redaction_status):
        raise Stage29_4InvalidPassRecordError(
            field_name="redaction_status",
            reason="REDACTION_STATUS_NOT_CLOSED_SET",
        )


def build_pass_record(
    *,
    pass_index: int,
    stage29_3_outcome: str,
    stage29_3_refusal_reason: str,
    dedupe_outcome: Optional[str],
    events_seen: int,
    candidates_dispatched: int,
    candidates_suppressed: int,
    dispatch_success: int,
    dispatch_failure: int,
    consecutive_suppression_streak: int,
    dispatch_success_total_at_tick: int,
    duplicate_suppressed_soak_count_at_tick: int,
    elapsed_at_tick_seconds: float,
    utc_iso_timestamp: str,
) -> Stage29_4PassRecord:
    """Construct an immutable ``Stage29_4PassRecord`` with full
    validation.
    """
    return Stage29_4PassRecord(
        pass_index=pass_index,
        stage29_3_outcome=stage29_3_outcome,
        stage29_3_refusal_reason=stage29_3_refusal_reason,
        dedupe_outcome=dedupe_outcome,
        events_seen=events_seen,
        candidates_dispatched=candidates_dispatched,
        candidates_suppressed=candidates_suppressed,
        dispatch_success=dispatch_success,
        dispatch_failure=dispatch_failure,
        consecutive_suppression_streak=(
            consecutive_suppression_streak
        ),
        dispatch_success_total_at_tick=(
            dispatch_success_total_at_tick
        ),
        duplicate_suppressed_soak_count_at_tick=(
            duplicate_suppressed_soak_count_at_tick
        ),
        elapsed_at_tick_seconds=elapsed_at_tick_seconds,
        utc_iso_timestamp=utc_iso_timestamp,
    )


def pass_record_to_dict(record: Stage29_4PassRecord) -> dict:
    """Project a ``Stage29_4PassRecord`` into a deterministic-order
    dict suitable for canonical JSON encoding.
    """
    if not isinstance(record, Stage29_4PassRecord):
        raise Stage29_4InvalidPassRecordError(
            field_name="record",
            reason="NOT_A_PASS_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in PASS_RECORD_FIELD_NAMES
    }


# ---------------------------------------------------------------------------
# Stage 29.4 pass-result envelope (used by the orchestrator's DI seam)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_4PassResult:
    """Envelope returned by a Stage 29.4 pass entrypoint.

    Carries the per-pass Stage 29.3 single-shot smoke result plus
    the optional Stage 29.4 cross-pass dedupe key candidate that
    the entrypoint identified for the dispatched candidate (or
    ``None`` when no dispatchable candidate was observed). The
    soak orchestrator consults the Stage 29.4 in-memory dedupe
    index against ``dedupe_key`` when one is present, and counts
    the resulting ``dedupe_outcome`` on the rolled-up soak
    counters.

    The ``smoke_result`` field is typed loosely as ``object`` here
    so this module does NOT need to import the Stage 29.3 smoke
    models surface; the orchestrator validates the record's shape
    at call time via duck-typing on the closed-set fields it reads.

    Fields:

      * ``smoke_result`` -- the Stage 29.3 single-shot smoke
        result returned by the per-pass entrypoint.
      * ``dedupe_key`` -- the cross-pass dedupe key the entrypoint
        derived for the candidate it processed, or ``None`` when
        no dispatchable candidate was observed.
    """

    smoke_result: object
    dedupe_key: Optional[Stage29_4SoakDedupeKey] = None


def build_pass_result(
    *,
    smoke_result: object,
    dedupe_key: Optional[Stage29_4SoakDedupeKey] = None,
) -> Stage29_4PassResult:
    """Construct an immutable ``Stage29_4PassResult`` envelope."""
    if dedupe_key is not None and not isinstance(
        dedupe_key, Stage29_4SoakDedupeKey,
    ):
        raise Stage29_4SoakError(
            "PASS_RESULT_DEDUPE_KEY_TYPE_INVALID",
        )
    return Stage29_4PassResult(
        smoke_result=smoke_result,
        dedupe_key=dedupe_key,
    )


# ---------------------------------------------------------------------------
# Stage 29.4 soak summary
# ---------------------------------------------------------------------------


SUPPRESSED_PER_OUTCOME_COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "suppressed_unknown_pair_count",
    "suppressed_disagree_pair_count",
    "suppressed_usdc_observe_only_count",
    "suppressed_missing_price_count",
    "suppressed_stale_price_count",
    "suppressed_malformed_count",
)


SOAK_SUMMARY_COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "passes_attempted",
    "dispatch_success_total",
    "dispatch_failure_total",
    "duplicate_suppressed_soak_count",
    "events_seen_total",
    "no_event_received_count",
    "consecutive_suppression_streak_max",
) + SUPPRESSED_PER_OUTCOME_COUNTER_FIELD_NAMES


SOAK_SUMMARY_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "soak_outcome",
    "passes_attempted",
    "dispatch_success_total",
    "dispatch_failure_total",
    "duplicate_suppressed_soak_count",
    "events_seen_total",
    "suppressed_unknown_pair_count",
    "suppressed_disagree_pair_count",
    "suppressed_usdc_observe_only_count",
    "suppressed_missing_price_count",
    "suppressed_stale_price_count",
    "suppressed_malformed_count",
    "no_event_received_count",
    "consecutive_suppression_streak_max",
    "elapsed_wall_clock_seconds",
    "start_utc_iso",
    "end_utc_iso",
    "bounds",
    "bounds_within_recommended_ranges",
    "filter_enforcement_status",
    "redaction_status",
)


@dataclass(frozen=True)
class Stage29_4SoakSummary:
    """Immutable Stage 29.4 soak summary record.

    Carries the closed-set soak outcome token, the rolled-up
    counters across every pass, the locked
    ``filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`` axis,
    the soak's elapsed wall-clock seconds, the soak's start / end
    timestamps in UTC ISO-8601, and the operator-supplied bounds
    echoed back. The record carries only closed-set tokens, safe
    counters, and safe-shape ISO-8601 strings; no webhook URL,
    RPC endpoint, API key, bearer token, auth header, raw
    provider payload, or raw exception string is ever carried.
    """

    soak_outcome: str
    passes_attempted: int
    dispatch_success_total: int
    dispatch_failure_total: int
    duplicate_suppressed_soak_count: int
    events_seen_total: int
    suppressed_unknown_pair_count: int
    suppressed_disagree_pair_count: int
    suppressed_usdc_observe_only_count: int
    suppressed_missing_price_count: int
    suppressed_stale_price_count: int
    suppressed_malformed_count: int
    no_event_received_count: int
    consecutive_suppression_streak_max: int
    elapsed_wall_clock_seconds: float
    start_utc_iso: str
    end_utc_iso: str
    bounds: Stage29_4SoakBounds
    bounds_within_recommended_ranges: bool = True
    filter_enforcement_status: str = (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    redaction_status: str = REDACTION_STATUS_SAFE
    schema_version: str = (
        STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _validate_soak_summary_fields(self)


def _validate_soak_summary_fields(
    record: "Stage29_4SoakSummary",
) -> None:
    if (
        record.schema_version
        != STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION
    ):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="schema_version",
            reason="SCHEMA_VERSION_NOT_LOCKED",
        )
    if not is_soak_outcome_value(record.soak_outcome):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="soak_outcome",
            reason="SOAK_OUTCOME_NOT_CLOSED_SET",
        )
    for name in SOAK_SUMMARY_COUNTER_FIELD_NAMES:
        value = getattr(record, name)
        if not _is_safe_counter(value):
            raise Stage29_4InvalidSoakSummaryError(
                field_name=name,
                reason="COUNTER_NOT_NONNEG_INT",
            )
    if not _is_safe_nonneg_float(
        record.elapsed_wall_clock_seconds,
    ):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="elapsed_wall_clock_seconds",
            reason="ELAPSED_NOT_NONNEG_FLOAT",
        )
    if not _is_safe_utc_iso(record.start_utc_iso):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="start_utc_iso",
            reason="START_UTC_ISO_NOT_SAFE_SHAPE",
        )
    if not _is_safe_utc_iso(record.end_utc_iso):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="end_utc_iso",
            reason="END_UTC_ISO_NOT_SAFE_SHAPE",
        )
    if not isinstance(record.bounds, Stage29_4SoakBounds):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="bounds",
            reason="BOUNDS_NOT_A_SOAK_BOUNDS",
        )
    if not isinstance(
        record.bounds_within_recommended_ranges, bool,
    ):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="bounds_within_recommended_ranges",
            reason="BOUNDS_WITHIN_RECOMMENDED_RANGES_NOT_BOOL",
        )
    if (
        record.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="filter_enforcement_status",
            reason="FILTER_ENFORCEMENT_STATUS_NOT_LOCKED",
        )
    if not is_redaction_status_value(record.redaction_status):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="redaction_status",
            reason="REDACTION_STATUS_NOT_CLOSED_SET",
        )


def build_soak_summary(
    *,
    soak_outcome: str,
    bounds: Stage29_4SoakBounds,
    passes_attempted: int = 0,
    dispatch_success_total: int = 0,
    dispatch_failure_total: int = 0,
    duplicate_suppressed_soak_count: int = 0,
    events_seen_total: int = 0,
    suppressed_unknown_pair_count: int = 0,
    suppressed_disagree_pair_count: int = 0,
    suppressed_usdc_observe_only_count: int = 0,
    suppressed_missing_price_count: int = 0,
    suppressed_stale_price_count: int = 0,
    suppressed_malformed_count: int = 0,
    no_event_received_count: int = 0,
    consecutive_suppression_streak_max: int = 0,
    elapsed_wall_clock_seconds: float = 0.0,
    start_utc_iso: str = "",
    end_utc_iso: str = "",
    bounds_within_recommended_ranges: bool = True,
) -> Stage29_4SoakSummary:
    """Construct an immutable ``Stage29_4SoakSummary`` with full
    validation.
    """
    return Stage29_4SoakSummary(
        soak_outcome=soak_outcome,
        passes_attempted=passes_attempted,
        dispatch_success_total=dispatch_success_total,
        dispatch_failure_total=dispatch_failure_total,
        duplicate_suppressed_soak_count=(
            duplicate_suppressed_soak_count
        ),
        events_seen_total=events_seen_total,
        suppressed_unknown_pair_count=(
            suppressed_unknown_pair_count
        ),
        suppressed_disagree_pair_count=(
            suppressed_disagree_pair_count
        ),
        suppressed_usdc_observe_only_count=(
            suppressed_usdc_observe_only_count
        ),
        suppressed_missing_price_count=(
            suppressed_missing_price_count
        ),
        suppressed_stale_price_count=(
            suppressed_stale_price_count
        ),
        suppressed_malformed_count=(
            suppressed_malformed_count
        ),
        no_event_received_count=no_event_received_count,
        consecutive_suppression_streak_max=(
            consecutive_suppression_streak_max
        ),
        elapsed_wall_clock_seconds=(
            elapsed_wall_clock_seconds
        ),
        start_utc_iso=start_utc_iso,
        end_utc_iso=end_utc_iso,
        bounds=bounds,
        bounds_within_recommended_ranges=(
            bounds_within_recommended_ranges
        ),
    )


def soak_summary_to_dict(
    record: Stage29_4SoakSummary,
) -> dict:
    """Project a ``Stage29_4SoakSummary`` into a deterministic-
    order dict suitable for canonical JSON encoding. The ``bounds``
    field is projected into its dict form so the resulting
    structure is stdlib-JSON serializable.
    """
    if not isinstance(record, Stage29_4SoakSummary):
        raise Stage29_4InvalidSoakSummaryError(
            field_name="record",
            reason="NOT_A_SOAK_SUMMARY",
        )
    projected: dict = {}
    for name in SOAK_SUMMARY_FIELD_NAMES:
        if name == "bounds":
            projected[name] = soak_bounds_to_dict(record.bounds)
        else:
            projected[name] = getattr(record, name)
    return projected


__all__ = (
    # Version axes.
    "STAGE29_4_MINOR_VERSION",
    "STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION",
    "STAGE29_4_HEARTBEAT_SCHEMA_VERSION",
    "STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION",
    "STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION",
    "STAGE29_4_REDACTION_TOKEN",
    # Probe-mode vocabulary.
    "PROBE_MODE_READINESS_ONLY",
    "PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
    "PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN",
    "PROBE_MODE_VALUES",
    "is_probe_mode_value",
    # Soak-outcome vocabulary.
    "SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP",
    "SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK",
    "SOAK_OUTCOME_COMPLETED_AT_PASS_CAP",
    "SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT",
    "SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS",
    "SOAK_OUTCOME_BROKE_ON_FAILED_PASS",
    "SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS",
    "SOAK_OUTCOME_REFUSED_INVALID_BOUNDS",
    "SOAK_OUTCOME_VALUES",
    "is_soak_outcome_value",
    # Dedupe-outcome vocabulary.
    "DEDUPE_OUTCOME_NEW",
    "DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK",
    "DEDUPE_OUTCOME_VALUES",
    "is_dedupe_outcome_value",
    # Redaction vocabulary.
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_VALUES",
    "is_redaction_status_value",
    # Filter enforcement vocabulary.
    "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING",
    # Recommended ranges + per-pass locks.
    "RECOMMENDED_WALL_CLOCK_SECONDS_MIN",
    "RECOMMENDED_WALL_CLOCK_SECONDS_MAX",
    "RECOMMENDED_MAX_DISPATCHES_MIN",
    "RECOMMENDED_MAX_DISPATCHES_MAX",
    "RECOMMENDED_MAX_PASSES_MIN",
    "RECOMMENDED_MAX_PASSES_MAX",
    "RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MIN",
    "RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MAX",
    "RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MIN",
    "RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MAX",
    "PER_PASS_MAX_EVENTS",
    "PER_PASS_MAX_DISPATCHES",
    "PER_PASS_MAX_TOTAL_RETRIES",
    # Records.
    "Stage29_4SoakDedupeKey",
    "SOAK_DEDUPE_KEY_FIELD_NAMES",
    "Stage29_4SoakBounds",
    "SOAK_BOUNDS_FIELD_NAMES",
    "Stage29_4PassRecord",
    "PASS_RECORD_FIELD_NAMES",
    "Stage29_4PassResult",
    "Stage29_4SoakSummary",
    "SOAK_SUMMARY_FIELD_NAMES",
    "SOAK_SUMMARY_COUNTER_FIELD_NAMES",
    "SUPPRESSED_PER_OUTCOME_COUNTER_FIELD_NAMES",
    # Builders.
    "build_soak_dedupe_key",
    "canonical_soak_dedupe_key_tuple",
    "build_soak_bounds",
    "soak_bounds_to_dict",
    "bounds_within_recommended_ranges",
    "build_pass_record",
    "pass_record_to_dict",
    "build_pass_result",
    "build_soak_summary",
    "soak_summary_to_dict",
    # Exceptions.
    "Stage29_4SoakError",
    "Stage29_4InvalidBoundsError",
    "Stage29_4InvalidDedupeKeyError",
    "Stage29_4InvalidPassRecordError",
    "Stage29_4InvalidSoakSummaryError",
)
