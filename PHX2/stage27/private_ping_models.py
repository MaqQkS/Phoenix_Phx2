"""Stage 27.5 private ping model layer.

Stage 27.5 ships the in-memory model layer for the Stage 27 private
PHX1-parity dry-run ping payload + the offline provenance artifact
that records the existence (and redacted summary) of that payload.

Stage 27.5 deliberately does NOT:

  * call Discord / Telegram / X-social / any webhook,
  * import any network / RPC / messaging library,
  * read the process environment,
  * route an event to a live destination,
  * dedupe a stream of events,
  * run a bounded continuous runner,
  * enforce Stage 26 candidate policies,
  * decide trading verdicts.

Closed-set vocabularies:

  * ``RENDER_STATUS``       -- ``RENDERED`` /
                               ``RENDERED_WITH_WARNINGS`` /
                               ``RENDERED_SUPPRESSED`` /
                               ``RENDERED_OBSERVE_ONLY`` /
                               ``RENDERED_UNSUPPORTED``
  * ``ARTIFACT_KIND``       -- ``PRIVATE_PING_DRY_RUN``
  * ``REDACTION_STATUS``    -- ``REDACTED`` / ``REDACTION_FAILED``

The payload record carries only closed-set tokens, safe-to-display
canonical fields, and the deterministic plain-text body the dry-run
artifact writer will persist. No field on either record ever takes a
raw provider payload blob, a secret, a webhook URL, an RPC URL, or
any Stage 26 enforcement decision.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 27.5 version axes
# ---------------------------------------------------------------------------


STAGE27_5_MINOR_VERSION: str = "27.5"
STAGE27_5_PING_SCHEMA_VERSION: str = "stage27_v0_private_ping"
STAGE27_5_PROVENANCE_SCHEMA_VERSION: str = (
    "stage27_v0_ping_provenance"
)


# ---------------------------------------------------------------------------
# render_status closed set
# ---------------------------------------------------------------------------
#
# RENDERED              -- pair is SOL on the existing-SOL lane, every
#                          measurement context is PRESENT / trusted,
#                          measurement_status is COMPLETE.
# RENDERED_WITH_WARNINGS -- pair is SOL on the existing-SOL lane but
#                          at least one measurement axis is degraded
#                          (STALE price, MAY_INCLUDE_PRE_MIGRATION
#                          ATH, UNTRUSTED migration, etc.).
# RENDERED_SUPPRESSED   -- pair is UNKNOWN or DISAGREE: the dry-run
#                          payload still exists for operator review
#                          but the Stage 27 live-policy verdict is
#                          LIVE_SUPPRESS_UNKNOWN /
#                          LIVE_SUPPRESS_DISAGREE.
# RENDERED_OBSERVE_ONLY -- pair is USDC: the dry-run payload exists
#                          but the SOL calibration lane does not apply.
# RENDERED_UNSUPPORTED  -- composition upstream was SKIPPED_*
#                          (missing token, unsupported event kind) or
#                          a sub-context returned UNSUPPORTED_PAIR.


RENDER_STATUS_RENDERED: str = "RENDERED"
RENDER_STATUS_RENDERED_WITH_WARNINGS: str = "RENDERED_WITH_WARNINGS"
RENDER_STATUS_RENDERED_SUPPRESSED: str = "RENDERED_SUPPRESSED"
RENDER_STATUS_RENDERED_OBSERVE_ONLY: str = "RENDERED_OBSERVE_ONLY"
RENDER_STATUS_RENDERED_UNSUPPORTED: str = "RENDERED_UNSUPPORTED"

RENDER_STATUS_VALUES: tuple[str, ...] = (
    RENDER_STATUS_RENDERED,
    RENDER_STATUS_RENDERED_WITH_WARNINGS,
    RENDER_STATUS_RENDERED_SUPPRESSED,
    RENDER_STATUS_RENDERED_OBSERVE_ONLY,
    RENDER_STATUS_RENDERED_UNSUPPORTED,
)


# ---------------------------------------------------------------------------
# artifact_kind closed set
# ---------------------------------------------------------------------------


ARTIFACT_KIND_PRIVATE_PING_DRY_RUN: str = "PRIVATE_PING_DRY_RUN"

ARTIFACT_KIND_VALUES: tuple[str, ...] = (
    ARTIFACT_KIND_PRIVATE_PING_DRY_RUN,
)


# ---------------------------------------------------------------------------
# redaction_status closed set
# ---------------------------------------------------------------------------


REDACTION_STATUS_REDACTED: str = "REDACTED"
REDACTION_STATUS_FAILED: str = "REDACTION_FAILED"

REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_FAILED,
)


# ---------------------------------------------------------------------------
# Display sentinels for missing / unavailable context fields
# ---------------------------------------------------------------------------
#
# Stage 27.5 NEVER displays ``0`` / ``0.0`` for a missing price or ATH;
# instead the rendered field carries one of these explicit sentinel
# strings. The provenance artifact / dry-run writer both honor these
# canonical placeholders.


DISPLAY_UNAVAILABLE: str = "UNAVAILABLE"
DISPLAY_STALE: str = "STALE"
DISPLAY_MISSING: str = "MISSING"
DISPLAY_UNTRUSTED: str = "UNTRUSTED"
DISPLAY_SOURCE_ERROR: str = "SOURCE_ERROR"
DISPLAY_NOT_APPLICABLE: str = "NOT_APPLICABLE"
DISPLAY_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
DISPLAY_NONE: str = "NONE"


DISPLAY_SENTINEL_VALUES: tuple[str, ...] = (
    DISPLAY_UNAVAILABLE,
    DISPLAY_STALE,
    DISPLAY_MISSING,
    DISPLAY_UNTRUSTED,
    DISPLAY_SOURCE_ERROR,
    DISPLAY_NOT_APPLICABLE,
    DISPLAY_UNSUPPORTED_PAIR,
    DISPLAY_NONE,
)


# ---------------------------------------------------------------------------
# Immutable record: private ping payload
# ---------------------------------------------------------------------------


class PrivatePingPayloadRecord(NamedTuple):
    """Immutable Stage 27.5 private ping payload.

    Carries only closed-set tokens, safe-to-display canonical fields,
    and the deterministic plain-text body the dry-run artifact writer
    persists. No raw provider payload blob, no secret value, no
    webhook URL is ever populated on this record.

    Fields:

      * ``ping_id``                       -- caller-supplied stable
                                             ping identifier.
      * ``run_id``                        -- caller-supplied run
                                             identifier; ``None`` when
                                             not attached yet.
      * ``session_id``                    -- caller-supplied session
                                             identifier; ``None`` when
                                             not attached yet.
      * ``ping_schema_version``           -- locked Stage 27.5 ping
                                             schema version string.
      * ``provider_id``                   -- copied from the Stage
                                             27.4 measurement context.
      * ``provider_event_id``             -- copied.
      * ``normalized_event_id``           -- copied.
      * ``raw_capture_ref``               -- copied. NEVER a payload
                                             blob.
      * ``token_mint``                    -- copied.
      * ``quote_mint``                    -- copied.
      * ``pair_type``                     -- copied closed-set token.
      * ``quote_asset``                   -- copied closed-set token.
      * ``bonding_curve_version``         -- copied closed-set token.
      * ``pair_detection_status``         -- copied closed-set token.
      * ``pair_detection_confidence``     -- copied closed-set token.
      * ``pair_detection_reason``         -- copied closed-set token.
      * ``pair_live_policy``              -- copied closed-set token.
                                             Stage 27.5 does NOT send
                                             anything live, but the
                                             token is preserved for
                                             operator review.
      * ``calibration_lane``              -- copied closed-set token.
                                             USDC / UNKNOWN / DISAGREE
                                             NEVER ``EXISTING_SOL_LANE``.
      * ``measurement_status``            -- copied closed-set token.
      * ``measurement_warnings``          -- copied tuple of closed-set
                                             warning constants.
      * ``price_status``                  -- copied closed-set token.
      * ``price_value_display``           -- the canonical decimal-text
                                             price value when present,
                                             otherwise one of the
                                             ``DISPLAY_*`` sentinel
                                             tokens. NEVER ``"0"`` /
                                             ``"0.0"`` as a missing
                                             sentinel.
      * ``price_unit_display``            -- copied closed-set
                                             ``PRICE_UNIT`` token or a
                                             ``DISPLAY_*`` sentinel.
      * ``price_source_display``          -- safe-to-display source
                                             label or a ``DISPLAY_*``
                                             sentinel.
      * ``price_staleness_seconds_display`` -- canonical decimal
                                             integer string for the
                                             staleness seconds, or a
                                             ``DISPLAY_*`` sentinel.
      * ``ath_status``                    -- copied closed-set token.
      * ``ath_value_display``             -- as above; explicit
                                             ``DISPLAY_*`` sentinel
                                             when missing / not-
                                             applicable.
      * ``ath_unit_display``              -- as above.
      * ``ath_since_migration_status_display`` -- copied closed-set
                                             token or sentinel.
      * ``drawdown_display``              -- as above.
      * ``drawdown_basis_display``        -- copied closed-set token or
                                             sentinel.
      * ``migration_status``              -- copied closed-set token.
      * ``migration_timestamp_display``   -- safe-to-display ISO-8601
                                             UTC string or sentinel.
      * ``migration_age_seconds_display`` -- canonical decimal integer
                                             string or sentinel.
      * ``migration_source_display``      -- copied closed-set token.
      * ``render_status``                 -- Stage 27.5 closed-set
                                             render verdict.
      * ``render_note``                   -- short safe-to-display
                                             rendering note (e.g.
                                             ``"LIVE_SUPPRESSED"``,
                                             ``"OBSERVE_ONLY"``).
      * ``body_text``                     -- deterministic plain-text
                                             body the dry-run writer
                                             persists. Carries no raw
                                             secret canary, no webhook
                                             URL, no raw provider
                                             payload blob, no BUY /
                                             SELL / APPROVED / GATE /
                                             enforcement / execute /
                                             position-size / auto-
                                             trade verdict language.
    """

    ping_id: str
    run_id: Optional[str]
    session_id: Optional[str]
    ping_schema_version: str

    provider_id: Optional[str]
    provider_event_id: Optional[str]
    normalized_event_id: Optional[str]
    raw_capture_ref: Optional[str]

    token_mint: Optional[str]
    quote_mint: Optional[str]

    pair_type: str
    quote_asset: str
    bonding_curve_version: str
    pair_detection_status: str
    pair_detection_confidence: str
    pair_detection_reason: str
    pair_live_policy: str
    calibration_lane: str

    measurement_status: str
    measurement_warnings: Tuple[str, ...]

    price_status: str
    price_value_display: str
    price_unit_display: str
    price_source_display: str
    price_staleness_seconds_display: str

    ath_status: str
    ath_value_display: str
    ath_unit_display: str
    ath_since_migration_status_display: str
    drawdown_display: str
    drawdown_basis_display: str

    migration_status: str
    migration_timestamp_display: str
    migration_age_seconds_display: str
    migration_source_display: str

    render_status: str
    render_note: str
    body_text: str


# ---------------------------------------------------------------------------
# Immutable record: dry-run provenance artifact
# ---------------------------------------------------------------------------


class PingProvenanceArtifactRecord(NamedTuple):
    """Immutable Stage 27.5 dry-run ping provenance artifact.

    A redacted summary record describing that a Stage 27.5 dry-run
    private ping was produced. Carries only closed-set tokens,
    safe-to-display canonical fields, the upstream provenance IDs,
    and a deterministic content hash of the rendered payload.

    Fields:

      * ``artifact_kind``               -- closed-set Stage 27.5
                                           artifact kind token.
      * ``artifact_schema_version``     -- locked Stage 27.5
                                           provenance schema version.
      * ``artifact_created_at_utc``     -- ISO-8601 UTC wall time
                                           supplied by the injected
                                           Stage 27.5 clock.
      * ``ping_id``                     -- ping identifier the artifact
                                           refers to.
      * ``ping_schema_version``         -- locked Stage 27.5 ping
                                           schema version string.
      * ``run_id``                      -- caller-supplied; ``None``
                                           when not attached.
      * ``session_id``                  -- caller-supplied; ``None``
                                           when not attached.
      * ``provider_id``                 -- copied.
      * ``provider_event_id``           -- copied.
      * ``normalized_event_id``         -- copied.
      * ``raw_capture_ref``             -- copied. NEVER a payload
                                           blob.
      * ``token_mint``                  -- copied.
      * ``pair_quote_asset``            -- copied closed-set token.
      * ``pair_type``                   -- copied closed-set token.
      * ``pair_detection_status``       -- copied closed-set token.
      * ``pair_detection_confidence``   -- copied closed-set token.
      * ``pair_live_policy``            -- copied closed-set token.
      * ``calibration_lane``            -- copied closed-set token.
                                           NEVER ``EXISTING_SOL_LANE``
                                           for USDC / UNKNOWN /
                                           DISAGREE pairs.
      * ``measurement_status``          -- copied closed-set token.
      * ``measurement_warnings``        -- copied tuple of closed-set
                                           warning constants.
      * ``render_status``               -- Stage 27.5 closed-set
                                           render verdict.
      * ``redaction_status``            -- closed-set redaction
                                           verdict; ``REDACTED`` on the
                                           happy path.
      * ``payload_content_hash``        -- deterministic hex digest of
                                           a canonical JSON encoding
                                           of the payload (every byte
                                           that ends up in the dry-run
                                           artifact). Stage 27.5 uses
                                           SHA-256.
    """

    artifact_kind: str
    artifact_schema_version: str
    artifact_created_at_utc: str
    ping_id: str
    ping_schema_version: str
    run_id: Optional[str]
    session_id: Optional[str]
    provider_id: Optional[str]
    provider_event_id: Optional[str]
    normalized_event_id: Optional[str]
    raw_capture_ref: Optional[str]
    token_mint: Optional[str]
    pair_quote_asset: str
    pair_type: str
    pair_detection_status: str
    pair_detection_confidence: str
    pair_live_policy: str
    calibration_lane: str
    measurement_status: str
    measurement_warnings: Tuple[str, ...]
    render_status: str
    redaction_status: str
    payload_content_hash: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 27.5 must never accept a field named anything secret-class or
# raw-payload-class on its payload or artifact records. The
# ``NamedTuple`` schemas above already exclude such fields; this
# helper is kept so a future refactor cannot silently widen the
# admitted field set.


FORBIDDEN_PAYLOAD_FIELD_NAMES: tuple[str, ...] = (
    "raw_payload",
    "raw_payload_blob",
    "payload_blob",
    "secret",
    "api_key",
    "apikey",
    "token_secret",
    "webhook",
    "webhook_url",
    "discord_webhook",
    "rpc_url",
    "private_key",
    "credentials",
    "bearer_token",
)


def is_forbidden_payload_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden payload field name.

    Pure / deterministic. Stage 27.5 uses this to reject any caller
    who tries to smuggle a raw payload blob into the ping payload or
    the provenance artifact.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_PAYLOAD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False
