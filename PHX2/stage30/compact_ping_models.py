"""Stage 30.2 compact private ping closed-set vocabularies and
immutable record shapes.

Stage 30.2 ships the pure-Python model layer for two records:

  * ``CompactPingInputRecord``    -- the caller-supplied input the
                                     Stage 30.2 renderer consumes.
                                     Carries a Stage 30.1
                                     ``TierDecisionRecord`` plus
                                     safe display fields (already-
                                     formatted MC / ATH / Mig / LP
                                     / net-flow display text,
                                     integer age, optional symbol,
                                     opaque session / ping /
                                     candidate ids, optional Stage
                                     27.4 ``PRICE_STATUS`` echo,
                                     caller-injected ISO-8601 UTC
                                     clock).
  * ``CompactPingSnapshotRecord`` -- the Stage 30.2 artifact
                                     record. Carries the rendered
                                     compact body text plus every
                                     operator-visible display field
                                     plus the warning lines plus
                                     the safe-shape opaque
                                     identifier echoes.

Closed-set surface:

  * ``DISPLAY_UNKNOWN``              -- the literal ``"Unknown"``
                                       sentinel the renderer emits
                                       for every missing /
                                       degraded display field.
                                       NEVER ``"0"`` / ``"0.0"`` /
                                       empty string / fabricated
                                       value.
  * ``FORBIDDEN_RECORD_FIELD_NAMES`` -- defensive sentinel
                                       vocabulary. Inherits the
                                       Stage 30.1 forbidden-name
                                       surface plus a small set of
                                       Stage 30.2-relevant names.

Stage 30.2 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, webhook URLs, API keys, bearer tokens, authorization
    headers (no field admits them),
  * trading verdicts (the Stage 30 spec forbids any trading-verdict
    substring on rendered output; the renderer scans every caller-
    supplied display field for the closed-set forbidden trading-
    verdict / URL / auth / secret substrings before assembling the
    body),
  * Stage 26 / Stage 29 enforcement decisions (Stage 30 is
    informational-only).

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.1 ``TierDecisionRecord`` imported read-only (no Stage
    30.1 file is modified).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack,
    Birdeye, Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source modification.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple

from PHX2.stage30.tier_decision_models import TierDecisionRecord


# ---------------------------------------------------------------------------
# Stage 30.2 schema version + locked artifact basename + cap constants
# ---------------------------------------------------------------------------


STAGE30_2_MINOR_VERSION: str = "30.2"
STAGE30_2_COMPACT_PING_SCHEMA_VERSION: str = (
    "stage30_2_v0_compact_ping"
)
STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME: str = (
    "stage30_2_compact_pings.jsonl"
)


# Target body length for the typical in-band rendered ping. The Stage
# 30.0 spec lock pins this at <= 800 chars. The renderer asserts
# this for in-band cases via the Stage 30.2 test suite, not at
# runtime, because warning lines can legitimately push the body
# slightly above 800 in degraded cases.
STAGE30_2_BODY_CHAR_TARGET: int = 800


# Hard cap on body length. The renderer raises if it would ever
# emit a body above this length. The cap echoes the Stage 28.9
# Discord content cap (``STAGE28_9_CONTENT_MAX_CHARS = 1900``); the
# Stage 30.2 renderer pins the value verbatim WITHOUT importing
# Stage 28.
STAGE30_2_BODY_CHAR_HARD_CAP: int = 1900


# Literal missing-value sentinel for every display field. NEVER use
# ``"0"`` / ``"0.0"`` / empty string / a fabricated estimate.
DISPLAY_UNKNOWN: str = "Unknown"


# ---------------------------------------------------------------------------
# Immutable record: compact ping input
# ---------------------------------------------------------------------------


class CompactPingInputRecord(NamedTuple):
    """Immutable Stage 30.2 compact ping input record.

    Caller-supplied input to the Stage 30.2 renderer. Carries a
    Stage 30.1 ``TierDecisionRecord`` (the renderer NEVER recomputes
    tier bands; it echoes ``tier_token`` / ``tier_reason`` / ``basis``
    / ``drawdown_from_ath_raw`` / ``drop_positive`` /
    ``ath_status`` / ``ath_since_migration_status`` /
    ``migration_status`` verbatim), plus already-formatted display
    text fields for ``MC`` / ``ATH MC`` / ``migration MC`` / ``LP``
    / ``net flow``, plus an integer ``age_since_migration_seconds``
    field, plus an optional ``symbol`` label, plus opaque
    identifier echoes, plus an optional Stage 27.4 ``PRICE_STATUS``
    echo for the price-degradation warning, plus a caller-injected
    ISO-8601 UTC ``created_at_utc``.

    Fields:

      * ``tier_decision``                -- Stage 30.1
                                            ``TierDecisionRecord``;
                                            REQUIRED.
      * ``mint``                         -- safe-shape Solana base58
                                            mint or ``None``.
      * ``symbol``                       -- short safe-shape symbol
                                            label (printable ASCII
                                            alphanumeric + ``_-.``,
                                            length [1, 16]) or
                                            ``None``.
      * ``current_mc_text``              -- already-formatted display
                                            text (e.g. ``"$83k"``) or
                                            ``None``. ``None`` /
                                            empty renders as
                                            ``DISPLAY_UNKNOWN``.
      * ``ath_mc_text``                  -- same shape as
                                            ``current_mc_text``.
      * ``migration_mc_text``            -- same.
      * ``lp_text``                      -- same.
      * ``net_flow_text``                -- same. Eventually
                                            populated with operator-
                                            readable net buy / sell
                                            flow (e.g.
                                            ``"+$12k buys"``); until
                                            a net-flow source ships,
                                            callers pass ``None``
                                            and the renderer emits
                                            ``DISPLAY_UNKNOWN``.
      * ``age_since_migration_seconds``  -- non-negative integer
                                            seconds since migration,
                                            or ``None``. Negative
                                            input raises.
      * ``price_status``                 -- Stage 27.4
                                            ``PRICE_STATUS`` echo
                                            (e.g. ``"PRESENT"``,
                                            ``"STALE"``,
                                            ``"SOURCE_ERROR"``,
                                            ``"UNAVAILABLE"``,
                                            ``"UNSUPPORTED_PAIR"``)
                                            or ``None``.
      * ``session_id``                   -- safe-shape opaque session
                                            identifier or ``None``.
      * ``ping_id``                      -- safe-shape opaque ping
                                            identifier or ``None``.
      * ``candidate_id``                 -- safe-shape opaque
                                            candidate identifier or
                                            ``None``.
      * ``created_at_utc``               -- ISO-8601 UTC timestamp
                                            passed in by the caller
                                            (the injected clock).
    """

    tier_decision: TierDecisionRecord
    mint: Optional[str]
    symbol: Optional[str]
    current_mc_text: Optional[str]
    ath_mc_text: Optional[str]
    migration_mc_text: Optional[str]
    lp_text: Optional[str]
    net_flow_text: Optional[str]
    age_since_migration_seconds: Optional[int]
    price_status: Optional[str]
    session_id: Optional[str]
    ping_id: Optional[str]
    candidate_id: Optional[str]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable record: compact ping snapshot
# ---------------------------------------------------------------------------


class CompactPingSnapshotRecord(NamedTuple):
    """Immutable Stage 30.2 compact ping snapshot record.

    Carries only closed-set tokens, safe-shape opaque identifier
    echoes, already-rendered display strings, the rendered compact
    body text, the warning lines (0..2), and an ISO-8601 UTC
    timestamp. No raw provider payload blob, no secret value, no
    webhook URL, no API key, no bearer token, no authorization
    header is ever populated on this record by the renderer. The
    Stage 30.2 forbidden-field-name guard rejects any future
    refactor that tries to widen the field set with a secret-class
    or raw-payload-class name.

    Fields:

      * ``schema_version``                  -- locked Stage 30.2
                                               compact ping schema
                                               version string.
      * ``session_id``                      -- safe-shape opaque
                                               session identifier or
                                               ``None``.
      * ``ping_id``                         -- safe-shape opaque ping
                                               identifier or ``None``.
      * ``candidate_id``                    -- safe-shape opaque
                                               candidate identifier
                                               or ``None``.
      * ``mint``                            -- safe-shape Solana
                                               base58 mint or
                                               ``None``.
      * ``symbol``                          -- safe-shape short
                                               symbol label or
                                               ``None``.
      * ``tier_token``                      -- echo of
                                               ``tier_decision.tier_token``.
      * ``tier_reason``                     -- echo of
                                               ``tier_decision.tier_reason``.
      * ``basis``                           -- echo of
                                               ``tier_decision.basis``.
      * ``drawdown_from_ath_raw``           -- echo of
                                               ``tier_decision.drawdown_from_ath_raw``.
      * ``drop_positive``                   -- echo of
                                               ``tier_decision.drop_positive``.
      * ``ath_status``                      -- echo of
                                               ``tier_decision.ath_status``.
      * ``ath_since_migration_status``      -- echo of
                                               ``tier_decision.ath_since_migration_status``.
      * ``migration_status``                -- echo of
                                               ``tier_decision.migration_status``.
      * ``price_status``                    -- echo of input
                                               ``price_status`` or
                                               ``None``.
      * ``current_mc_display``              -- rendered display
                                               string (input text or
                                               ``DISPLAY_UNKNOWN``).
      * ``ath_mc_display``                  -- same.
      * ``migration_mc_display``            -- same.
      * ``drop_percent_display``            -- rendered drawdown
                                               from ATH (e.g.
                                               ``"-82%"``) or
                                               ``DISPLAY_UNKNOWN``.
                                               The visible body
                                               label is ``Drop``
                                               (NOT ``Floor`` --
                                               ``Floor`` would imply
                                               an observed minimum-
                                               drawdown tracker
                                               which does not yet
                                               exist).
      * ``age_display``                     -- rendered age (e.g.
                                               ``"16.6h"``) or
                                               ``DISPLAY_UNKNOWN``.
      * ``lp_display``                      -- same shape as
                                               ``current_mc_display``.
      * ``net_flow_display``                -- rendered net buy /
                                               sell flow display
                                               text (e.g.
                                               ``"+$12k buys"``) or
                                               ``DISPLAY_UNKNOWN``.
                                               The visible body
                                               label is ``Net``
                                               (NOT ``Vol`` --
                                               ``Vol`` would imply
                                               a raw volume / cooling
                                               source that has not
                                               yet been adopted in
                                               Stage 30).
      * ``warnings``                        -- tuple of rendered
                                               warning lines (0..2).
      * ``body_text``                       -- the rendered compact
                                               body, a single string
                                               with LF-separated
                                               lines.
      * ``body_length_chars``               -- ``len(body_text)``
                                               (Python str length,
                                               characters not bytes).
      * ``created_at_utc``                  -- ISO-8601 UTC timestamp
                                               echoed from the input.
    """

    schema_version: str
    session_id: Optional[str]
    ping_id: Optional[str]
    candidate_id: Optional[str]
    mint: Optional[str]
    symbol: Optional[str]
    tier_token: str
    tier_reason: str
    basis: str
    drawdown_from_ath_raw: Optional[str]
    drop_positive: Optional[str]
    ath_status: str
    ath_since_migration_status: str
    migration_status: str
    price_status: Optional[str]
    current_mc_display: str
    ath_mc_display: str
    migration_mc_display: str
    drop_percent_display: str
    age_display: str
    lp_display: str
    net_flow_display: str
    warnings: Tuple[str, ...]
    body_text: str
    body_length_chars: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.2 must never accept a field named anything secret-class or
# raw-payload-class on either record. The current
# ``CompactPingInputRecord._fields`` /
# ``CompactPingSnapshotRecord._fields`` sets have no such name, but
# this helper is kept so a future refactor cannot silently widen the
# admitted field set.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    "webhook",
    "webhook_url",
    "webhooks",
    "webhook_token",
    "api_key",
    "apikey",
    "bearer",
    "bearer_token",
    "authorization",
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
    "migration_event_id",
    "raw_capture_ref",
    "source_event_ref",
    "rpc_url",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.2 uses this guard to reject any
    future refactor that tries to widen either record with a
    secret-class or raw-payload-class field name.
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


class Stage30_2CompactPingError(Exception):
    """Closed-set Stage 30.2 compact ping error.

    Carries only a closed-set reason token on the exception message.
    Stage 30.2 callers should never embed a raw OSError message, a
    raw provider payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.2 compact ping error: reason={reason!r}"
        )


__all__ = (
    # Version + locked artifact basename + caps + sentinel.
    "STAGE30_2_MINOR_VERSION",
    "STAGE30_2_COMPACT_PING_SCHEMA_VERSION",
    "STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME",
    "STAGE30_2_BODY_CHAR_TARGET",
    "STAGE30_2_BODY_CHAR_HARD_CAP",
    "DISPLAY_UNKNOWN",
    # Records.
    "CompactPingInputRecord",
    "CompactPingSnapshotRecord",
    # Forbidden-field-name guard.
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    # Error.
    "Stage30_2CompactPingError",
)
