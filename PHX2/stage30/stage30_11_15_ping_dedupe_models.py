"""Stage 30.11.15 private operator ping dedupe models.

Stage 30.11.15 ships the passive, pure, stdlib-only MODEL layer for the
committed cross-run private operator ping dedupe layer: the frozen dedupe KEY
derived from a committed Stage 30.11.13 composed snapshot, the per-check dedupe
OUTCOME (verdict + reason) the ledger and the guard return, the closed-set
verdict / reason vocabularies they share, the JSONL ledger record schema
identity + field set, and the pure safe-shape / banding helpers the ledger and
the guard compose.

The dedupe key is mint-anchored + state-classed so the SAME mint in the SAME
operator state is suppressed across runs while a MEANINGFUL state change
(a new tier, a crossed drawdown band, an ATH-verification flip, a policy bump)
yields a NEW key that is allowed to ping again. It deliberately carries NO
``candidate_id`` (per-run / per-candidate), NO exact drawdown, NO current market
cap, NO ATH price, and NO ``created_at_utc`` -- every one of those moves run to
run and would defeat suppression. The exact drawdown + ATH price are read ONLY
to COMPUTE the rounded ``drawdown_band`` bucket, then discarded.

This module is the MODEL layer ONLY. It implements NO ledger (that is
``stage30_11_15_ping_dedupe_ledger``), NO guard / orchestrator (that is
``stage30_11_15_no_send_dedupe_guard``), reads NO process environment, opens NO
network connection, opens NO database, writes NO file, reads NO wall clock
(``created_at_utc`` / ``reserved_at_utc`` are caller-injected and PARSED only by
the ledger), reserves NO dispatch, sends NO Discord message, and edits NO Stage
21-29 / Stage 30.12 / tier-band production file. Stage 30.11.15 is fake /
offline only: the real private compact dispatch / Discord send remains a
SEPARATE, explicitly operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.11.3 / 30.11.1 model modules);
    the records carry only safe scalars / closed-set tokens, not embedded Stage
    30.11.13 snapshot types.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected and parsed
    only by the ledger.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + dedupe schema identity
# ---------------------------------------------------------------------------


STAGE30_11_15_MINOR_VERSION: str = "30.11.15"


# The Stage 30.11.15 ping dedupe schema version. Names the key / outcome shape;
# distinct from the ledger record schema version. Mirrored BY VALUE by the Stage
# 30.11 manifest section; this module imports no Stage 30.11 manifest.
STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION: str = "stage30_11_15_v0_ping_dedupe"


# The Stage 30.11.15 append-only JSONL ledger record schema version. Names the
# persisted per-reservation record shape; a replay rejects any other value.
STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION: str = (
    "stage30_11_15_v0_ping_dedupe_ledger"
)


# The safe-shape source-stage provenance token (names the slice; never a secret
# / host / transport destination).
STAGE30_11_15_SOURCE_STAGE: str = "30.11.15"


# ---------------------------------------------------------------------------
# Key policy defaults (closed-set, operator-configurable in tests)
# ---------------------------------------------------------------------------
#
# The operator-signal-kind + policy-version axes let a NEW ping type or a policy
# bump intentionally re-alert without defeating in-state suppression (Stage 30.6
# dedupe-contract Section 4). The default TTL bounds re-alert for an UNCHANGED
# state; the default drawdown bucket is the band width in percent.


STAGE30_11_15_OPERATOR_SIGNAL_KIND: str = "PHOENIX_OPERATOR_DIP_PING"
STAGE30_11_15_POLICY_VERSION: str = "stage30_11_15_v0"

# Default re-alert TTL for an UNCHANGED key: 6 hours. Configurable in tests.
STAGE30_11_15_DEFAULT_TTL_SECONDS: int = 21600

# Default drawdown band width in percent (10% buckets).
STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT: int = 10

# The drawdown-band token prefix (a display / key token only).
STAGE30_11_15_DRAWDOWN_BAND_PREFIX: str = "DD_BAND_"


# ---------------------------------------------------------------------------
# Closed-set: dedupe verdict
# ---------------------------------------------------------------------------
#
# Exactly one verdict per check. ``DEDUPE_ALLOWED`` is the only verdict on which
# the composer proceeds to dispatch; the other two fail closed (no runner call,
# no body, transport_attempts 0). Mirrored BY VALUE by the Stage 30.11 manifest.


DEDUPE_VERDICT_ALLOWED: str = "DEDUPE_ALLOWED"
DEDUPE_VERDICT_SUPPRESSED_DUPLICATE: str = "DEDUPE_SUPPRESSED_DUPLICATE"
DEDUPE_VERDICT_UNAVAILABLE: str = "DEDUPE_UNAVAILABLE"


STAGE30_11_15_DEDUPE_VERDICTS: Tuple[str, ...] = (
    DEDUPE_VERDICT_ALLOWED,
    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
    DEDUPE_VERDICT_UNAVAILABLE,
)


def is_ping_dedupe_verdict(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set dedupe verdict.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_15_DEDUPE_VERDICTS


# ---------------------------------------------------------------------------
# Closed-set: dedupe reason
# ---------------------------------------------------------------------------
#
# Exactly one reason per verdict. ``NEW_KEY`` / ``TTL_EXPIRED`` accompany an
# allow (a genuinely new state class, or an unchanged state past its TTL); a key
# whose ANY field differs -- a new tier / mint / drawdown band / policy version /
# ATH-verification flip -- is simply not present and so is allowed with
# ``NEW_KEY``. ``DUPLICATE_WITHIN_TTL`` is the only suppress reason. The
# ``LEDGER_*`` + ``MALFORMED_KEY`` reasons accompany the fail-closed unavailable
# verdict. Mirrored BY VALUE by the Stage 30.11 manifest.


DEDUPE_REASON_NEW_KEY: str = "DEDUPE_REASON_NEW_KEY"
DEDUPE_REASON_TTL_EXPIRED: str = "DEDUPE_REASON_TTL_EXPIRED"
DEDUPE_REASON_DUPLICATE_WITHIN_TTL: str = "DEDUPE_REASON_DUPLICATE_WITHIN_TTL"
DEDUPE_REASON_LEDGER_UNAVAILABLE: str = "DEDUPE_REASON_LEDGER_UNAVAILABLE"
DEDUPE_REASON_LEDGER_CORRUPT: str = "DEDUPE_REASON_LEDGER_CORRUPT"
DEDUPE_REASON_LEDGER_WRITE_FAILED: str = "DEDUPE_REASON_LEDGER_WRITE_FAILED"
DEDUPE_REASON_MALFORMED_KEY: str = "DEDUPE_REASON_MALFORMED_KEY"


STAGE30_11_15_DEDUPE_REASONS: Tuple[str, ...] = (
    DEDUPE_REASON_NEW_KEY,
    DEDUPE_REASON_TTL_EXPIRED,
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_LEDGER_CORRUPT,
    DEDUPE_REASON_LEDGER_WRITE_FAILED,
    DEDUPE_REASON_MALFORMED_KEY,
)


def is_ping_dedupe_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set dedupe reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_15_DEDUPE_REASONS


# ---------------------------------------------------------------------------
# Pure safe-shape + decimal helpers
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.3 / 30.11.1 non-blank id
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def _coerce_finite_decimal(value: object) -> Optional[Decimal]:
    """Coerce safe decimal text / int / Decimal to a finite (>= 0) ``Decimal``;
    else ``None``. Never raises. Mirrors the committed Stage 30.11.13 helper BY
    VALUE so the band math matches the snapshot's drawdown handling.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _coerce_positive_decimal(value: object) -> Optional[Decimal]:
    """Coerce safe decimal text / int / Decimal to a finite, strictly-positive
    ``Decimal``; else ``None``. Never raises. Mirrors the committed Stage
    30.11.13 helper BY VALUE.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def drawdown_band_token(
    drawdown: object,
    ath_price: object,
    *,
    bucket_pct: int = STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
) -> Optional[str]:
    """Return the rounded drawdown-band token for an absolute ``drawdown`` and an
    ``ath_price``, or ``None`` (fail closed) on any malformed / non-positive
    input.

    ``pct = (drawdown / ath_price) * 100``; the band floors ``pct`` to a multiple
    of ``bucket_pct`` and renders ``DD_BAND_<index>``. A tiny move inside a
    bucket keeps the SAME token (suppress); a move that crosses a bucket yields a
    DIFFERENT token (a new key -> allow). Pure / total; never raises. The exact
    drawdown + ATH price are consumed here and are NEVER part of the dedupe key.
    """
    if not isinstance(bucket_pct, int) or isinstance(bucket_pct, bool):
        return None
    if bucket_pct <= 0:
        return None
    dd = _coerce_finite_decimal(drawdown)
    ath = _coerce_positive_decimal(ath_price)
    if dd is None or ath is None:
        return None
    try:
        pct = (dd / ath) * Decimal(100)
        band_index = int(pct // Decimal(bucket_pct)) * bucket_pct
    except (InvalidOperation, ZeroDivisionError):
        return None
    if band_index < 0:
        return None
    return f"{STAGE30_11_15_DRAWDOWN_BAND_PREFIX}{band_index}"


# ---------------------------------------------------------------------------
# Immutable model: the dedupe key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_15PingDedupeKey:
    """Immutable mint-anchored, state-classed private operator ping dedupe key.

    Carries ONLY the state-class axes that should suppress a repeat ping for the
    same mint, and re-alert on a meaningful change:

      * ``token_mint``                  -- identity (NEVER ``candidate_id``).
      * ``operator_signal_kind``        -- closed-set ping-type tag.
      * ``tier_token``                  -- the Stage 30.1 tier (a new tier
                                           re-alerts).
      * ``drawdown_band``               -- the rounded drawdown bucket token (a
                                           crossed band re-alerts; the EXACT
                                           drawdown is never carried).
      * ``post_migration_ath_verified`` -- the ATH-verification state (a flip
                                           re-alerts).
      * ``ath_source_stage``            -- the ATH provenance stage (guards
                                           against a source-stage drift forging a
                                           re-alert).
      * ``policy_version``              -- the dedupe policy axis (a bump
                                           intentionally re-alerts).

    No secret, no raw payload, no host, no transport destination, no env value,
    no exact drawdown / MC / ATH price / timestamp.
    """

    token_mint: str
    operator_signal_kind: str
    tier_token: str
    drawdown_band: str
    post_migration_ath_verified: bool
    ath_source_stage: str
    policy_version: str


def is_ping_dedupe_key(value: object) -> bool:
    """Return ``True`` iff ``value`` is a well-shaped ``Stage30_11_15PingDedupeKey``
    (the right type, non-blank string axes, a real ``bool`` verified flag).

    Pure / total; never raises.
    """
    if not isinstance(value, Stage30_11_15PingDedupeKey):
        return False
    if not isinstance(value.post_migration_ath_verified, bool):
        return False
    for text in (
        value.token_mint,
        value.operator_signal_kind,
        value.tier_token,
        value.drawdown_band,
        value.ath_source_stage,
        value.policy_version,
    ):
        if not is_nonblank_str(text):
            return False
    return True


def canonical_ping_dedupe_key_tuple(
    key: Stage30_11_15PingDedupeKey,
) -> Tuple[str, str, str, str, bool, str, str]:
    """Project ``key`` to its canonical hashable identity tuple (the lookup key
    both ledger implementations store). Pure; no I/O, no clock.
    """
    return (
        key.token_mint,
        key.operator_signal_kind,
        key.tier_token,
        key.drawdown_band,
        key.post_migration_ath_verified,
        key.ath_source_stage,
        key.policy_version,
    )


# ---------------------------------------------------------------------------
# Immutable model: per-check dedupe outcome (verdict + reason)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_15PingDedupeOutcome:
    """Immutable per-check dedupe outcome.

    The ledger's ``check_and_reserve`` and the guard both return one of these.
    Carries a closed-set ``verdict`` + ``reason``; the ``allowed`` /
    ``suppressed`` / ``unavailable`` properties are the duck-typed view the
    committed Stage 30.11.13 composer's ``pre_dispatch_guard`` hook reads (the
    composer imports no Stage 30.11.15 type). Carries no secret / payload / host.
    """

    verdict: str
    reason: str

    @property
    def allowed(self) -> bool:
        """``True`` iff the verdict is ``DEDUPE_ALLOWED``."""
        return self.verdict == DEDUPE_VERDICT_ALLOWED

    @property
    def suppressed(self) -> bool:
        """``True`` iff the verdict is ``DEDUPE_SUPPRESSED_DUPLICATE``."""
        return self.verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE

    @property
    def unavailable(self) -> bool:
        """``True`` iff the verdict is ``DEDUPE_UNAVAILABLE`` (fail closed)."""
        return self.verdict == DEDUPE_VERDICT_UNAVAILABLE


def allowed_outcome(reason: str) -> Stage30_11_15PingDedupeOutcome:
    """Build an ``DEDUPE_ALLOWED`` outcome with ``reason``. Pure."""
    return Stage30_11_15PingDedupeOutcome(
        verdict=DEDUPE_VERDICT_ALLOWED, reason=reason
    )


def suppressed_outcome(reason: str) -> Stage30_11_15PingDedupeOutcome:
    """Build a ``DEDUPE_SUPPRESSED_DUPLICATE`` outcome with ``reason``. Pure."""
    return Stage30_11_15PingDedupeOutcome(
        verdict=DEDUPE_VERDICT_SUPPRESSED_DUPLICATE, reason=reason
    )


def unavailable_outcome(reason: str) -> Stage30_11_15PingDedupeOutcome:
    """Build a ``DEDUPE_UNAVAILABLE`` (fail-closed) outcome with ``reason``. Pure."""
    return Stage30_11_15PingDedupeOutcome(
        verdict=DEDUPE_VERDICT_UNAVAILABLE, reason=reason
    )


# ---------------------------------------------------------------------------
# JSONL ledger record field set (the persisted per-reservation shape)
# ---------------------------------------------------------------------------
#
# The append-only JSONL ledger persists exactly these fields per reservation:
# the schema version, the seven key axes, and the caller-injected
# ``reserved_at_utc`` timestamp (the ONLY non-key field; it drives TTL re-alert).
# A replay rejects any other field set.


STAGE30_11_15_LEDGER_RESERVED_AT_FIELD: str = "reserved_at_utc"
STAGE30_11_15_LEDGER_SCHEMA_FIELD: str = "schema_version"

STAGE30_11_15_LEDGER_RECORD_FIELDS: Tuple[str, ...] = (
    STAGE30_11_15_LEDGER_SCHEMA_FIELD,
    "token_mint",
    "operator_signal_kind",
    "tier_token",
    "drawdown_band",
    "post_migration_ath_verified",
    "ath_source_stage",
    "policy_version",
    STAGE30_11_15_LEDGER_RESERVED_AT_FIELD,
)

# The string-typed ledger record fields that must be present + non-empty.
STAGE30_11_15_LEDGER_REQUIRED_NON_EMPTY_FIELDS: Tuple[str, ...] = (
    STAGE30_11_15_LEDGER_SCHEMA_FIELD,
    "token_mint",
    "operator_signal_kind",
    "tier_token",
    "drawdown_band",
    "ath_source_stage",
    "policy_version",
    STAGE30_11_15_LEDGER_RESERVED_AT_FIELD,
)


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def ping_dedupe_key_field_names() -> Tuple[str, ...]:
    """Return the dedupe key field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_15PingDedupeKey))


def ping_dedupe_outcome_field_names() -> Tuple[str, ...]:
    """Return the dedupe outcome field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_15PingDedupeOutcome))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_15_MINOR_VERSION",
    "STAGE30_11_15_PING_DEDUPE_SCHEMA_VERSION",
    "STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION",
    "STAGE30_11_15_SOURCE_STAGE",
    # Key policy defaults.
    "STAGE30_11_15_OPERATOR_SIGNAL_KIND",
    "STAGE30_11_15_POLICY_VERSION",
    "STAGE30_11_15_DEFAULT_TTL_SECONDS",
    "STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT",
    "STAGE30_11_15_DRAWDOWN_BAND_PREFIX",
    # Verdicts.
    "DEDUPE_VERDICT_ALLOWED",
    "DEDUPE_VERDICT_SUPPRESSED_DUPLICATE",
    "DEDUPE_VERDICT_UNAVAILABLE",
    "STAGE30_11_15_DEDUPE_VERDICTS",
    "is_ping_dedupe_verdict",
    # Reasons.
    "DEDUPE_REASON_NEW_KEY",
    "DEDUPE_REASON_TTL_EXPIRED",
    "DEDUPE_REASON_DUPLICATE_WITHIN_TTL",
    "DEDUPE_REASON_LEDGER_UNAVAILABLE",
    "DEDUPE_REASON_LEDGER_CORRUPT",
    "DEDUPE_REASON_LEDGER_WRITE_FAILED",
    "DEDUPE_REASON_MALFORMED_KEY",
    "STAGE30_11_15_DEDUPE_REASONS",
    "is_ping_dedupe_reason",
    # Safe-shape + banding helpers.
    "is_nonblank_str",
    "drawdown_band_token",
    # Models.
    "Stage30_11_15PingDedupeKey",
    "is_ping_dedupe_key",
    "canonical_ping_dedupe_key_tuple",
    "Stage30_11_15PingDedupeOutcome",
    "allowed_outcome",
    "suppressed_outcome",
    "unavailable_outcome",
    # Ledger record schema.
    "STAGE30_11_15_LEDGER_RESERVED_AT_FIELD",
    "STAGE30_11_15_LEDGER_SCHEMA_FIELD",
    "STAGE30_11_15_LEDGER_RECORD_FIELDS",
    "STAGE30_11_15_LEDGER_REQUIRED_NON_EMPTY_FIELDS",
    # Field-name helpers.
    "ping_dedupe_key_field_names",
    "ping_dedupe_outcome_field_names",
)
