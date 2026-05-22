"""Stage 27.4 combined live measurement context.

The single Stage 27.4 entry point that combines a Stage 27.3
provider-ingest composition output with the Stage 27.4 price /
ATH / migration context records into one immutable
``LiveMeasurementContextRecord``.

Stage 27.4 deliberately does NOT:

  * open any provider connection,
  * call Helius / gRPC / Birdeye / Discord / Telegram / X-social,
  * read the process environment,
  * render a private ping,
  * send a private ping,
  * dedupe events,
  * run a runner,
  * enforce Stage 26 policy candidates,
  * route UNKNOWN / DISAGREE / USDC verdicts into the existing SOL
    calibration lane.

Closed-set vocabularies:

  * ``MEASUREMENT_STATUS``   -- ``COMPLETE`` / ``PARTIAL`` /
                                 ``MISSING_PRICE`` / ``MISSING_ATH`` /
                                 ``MISSING_MIGRATION`` /
                                 ``UNSUPPORTED_PAIR`` /
                                 ``SOURCE_ERROR``
  * ``MEASUREMENT_WARNINGS`` -- closed-set warning constants for
                                 downstream operator review.

Status policy:

  * ``UNSUPPORTED_PAIR`` -- the upstream Stage 27.3 composition
    skipped the event (unsupported event kind, missing token mint,
    UNKNOWN pair, DISAGREE pair, USDC pair on the SOL lane).
  * ``SOURCE_ERROR``     -- at least one Stage 27.4 source returned
    a ``SOURCE_ERROR`` record.
  * ``MISSING_*``        -- the corresponding context is missing
    (e.g. ``UNAVAILABLE`` price); other contexts may still be
    present.
  * ``PARTIAL``          -- at least one context is downgraded
    (``STALE`` price, ``MAY_INCLUDE_PRE_MIGRATION`` ATH,
    ``UNTRUSTED`` migration).
  * ``COMPLETE``         -- every context is ``PRESENT`` /
    ``POST_MIGRATION_ONLY`` and the pair is a SOL-lane
    ``CONFIRMED`` / ``PROVIDER_ONLY`` verdict.

This module imports only stdlib (``typing``) plus Stage 27.2,
Stage 27.3, and Stage 27.4 production modules. It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple

from PHX2.stage27.migration_context_models import (
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_SOURCE_ERROR,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_UNTRUSTED,
    MigrationContextRecord,
)
from PHX2.stage27.pair_detection_constants import (
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_NOT_APPLICABLE,
    ATH_STATUS_PRESENT,
    ATH_STATUS_SOURCE_ERROR,
    ATH_STATUS_STALE,
    ATH_STATUS_UNAVAILABLE,
    ATH_STATUS_UNSUPPORTED_PAIR,
    AthContextRecord,
    PRICE_STATUS_PRESENT,
    PRICE_STATUS_SOURCE_ERROR,
    PRICE_STATUS_STALE,
    PRICE_STATUS_UNAVAILABLE,
    PRICE_STATUS_UNSUPPORTED_PAIR,
    PriceContextRecord,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_ERROR,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    ProviderIngestOutputRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.4 combined measurement schema version
# ---------------------------------------------------------------------------


STAGE27_4_MEASUREMENT_SCHEMA_VERSION: str = (
    "stage27_v0_measurement_context"
)


# ---------------------------------------------------------------------------
# measurement_status closed set
# ---------------------------------------------------------------------------


MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
MEASUREMENT_STATUS_PARTIAL: str = "PARTIAL"
MEASUREMENT_STATUS_MISSING_PRICE: str = "MISSING_PRICE"
MEASUREMENT_STATUS_MISSING_ATH: str = "MISSING_ATH"
MEASUREMENT_STATUS_MISSING_MIGRATION: str = "MISSING_MIGRATION"
MEASUREMENT_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
MEASUREMENT_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"

MEASUREMENT_STATUS_VALUES: tuple[str, ...] = (
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_MISSING_PRICE,
    MEASUREMENT_STATUS_MISSING_ATH,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_UNSUPPORTED_PAIR,
    MEASUREMENT_STATUS_SOURCE_ERROR,
)


# ---------------------------------------------------------------------------
# measurement_warnings closed set
# ---------------------------------------------------------------------------


WARNING_USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION: str = (
    "USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION"
)
WARNING_UNKNOWN_PAIR_SUPPRESSED_IN_LIVE: str = (
    "UNKNOWN_PAIR_SUPPRESSED_IN_LIVE"
)
WARNING_DISAGREE_PAIR_SUPPRESSED_IN_LIVE: str = (
    "DISAGREE_PAIR_SUPPRESSED_IN_LIVE"
)
WARNING_PRICE_STALE: str = "PRICE_STALE"
WARNING_PRICE_UNAVAILABLE: str = "PRICE_UNAVAILABLE"
WARNING_ATH_UNAVAILABLE: str = "ATH_UNAVAILABLE"
WARNING_MIGRATION_MISSING: str = "MIGRATION_MISSING"
WARNING_MIGRATION_UNTRUSTED: str = "MIGRATION_UNTRUSTED"
WARNING_POST_MIGRATION_ATH_UNVERIFIED: str = (
    "POST_MIGRATION_ATH_UNVERIFIED"
)
WARNING_PRICE_SOURCE_ERROR: str = "PRICE_SOURCE_ERROR"
WARNING_ATH_SOURCE_ERROR: str = "ATH_SOURCE_ERROR"
WARNING_MIGRATION_SOURCE_ERROR: str = "MIGRATION_SOURCE_ERROR"
WARNING_COMPOSITION_SKIPPED_UNSUPPORTED_EVENT: str = (
    "COMPOSITION_SKIPPED_UNSUPPORTED_EVENT"
)
WARNING_COMPOSITION_SKIPPED_MISSING_TOKEN: str = (
    "COMPOSITION_SKIPPED_MISSING_TOKEN"
)
WARNING_COMPOSITION_ERROR: str = "COMPOSITION_ERROR"

MEASUREMENT_WARNING_VALUES: tuple[str, ...] = (
    WARNING_USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION,
    WARNING_UNKNOWN_PAIR_SUPPRESSED_IN_LIVE,
    WARNING_DISAGREE_PAIR_SUPPRESSED_IN_LIVE,
    WARNING_PRICE_STALE,
    WARNING_PRICE_UNAVAILABLE,
    WARNING_ATH_UNAVAILABLE,
    WARNING_MIGRATION_MISSING,
    WARNING_MIGRATION_UNTRUSTED,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    WARNING_PRICE_SOURCE_ERROR,
    WARNING_ATH_SOURCE_ERROR,
    WARNING_MIGRATION_SOURCE_ERROR,
    WARNING_COMPOSITION_SKIPPED_UNSUPPORTED_EVENT,
    WARNING_COMPOSITION_SKIPPED_MISSING_TOKEN,
    WARNING_COMPOSITION_ERROR,
)


# ---------------------------------------------------------------------------
# Immutable record: combined Stage 27.4 measurement context
# ---------------------------------------------------------------------------


class LiveMeasurementContextRecord(NamedTuple):
    """Immutable Stage 27.4 combined measurement context output.

    Fields:

      * ``provider_id``                       -- copied from the
                                                 Stage 27.3
                                                 composition output.
      * ``provider_event_id``                 -- copied.
      * ``normalized_event_id``               -- copied.
      * ``event_kind``                        -- copied.
      * ``observed_at_utc``                   -- copied from the
                                                 Stage 27.3 output
                                                 (event-observed time);
                                                 Stage 27.4 does NOT
                                                 overwrite this with
                                                 the clock.
      * ``token_mint``                        -- copied.
      * ``quote_mint``                        -- copied.
      * ``pair_quote_asset``                  -- Stage 27.2 closed-set
                                                 ``QUOTE_ASSET``
                                                 verdict (mirrored from
                                                 the Stage 27.3 output).
      * ``pair_pair_type``                    -- mirrored.
      * ``pair_bonding_curve_version``        -- mirrored.
      * ``pair_detection_status``             -- mirrored.
      * ``pair_detection_confidence``         -- mirrored.
      * ``pair_detection_reason``             -- mirrored.
      * ``pair_live_policy``                  -- mirrored.
      * ``pair_calibration_lane``             -- mirrored. USDC and
                                                 UNKNOWN NEVER reach
                                                 EXISTING_SOL_LANE.
      * ``composition_status``                -- mirrored.
      * ``composition_reason``                -- mirrored.
      * ``price_context``                     -- ``PriceContextRecord``.
      * ``ath_context``                       -- ``AthContextRecord``.
      * ``migration_context``                 -- ``MigrationContextRecord``.
      * ``measurement_status``                -- one of
                                                 ``MEASUREMENT_STATUS_VALUES``.
      * ``measurement_warnings``              -- tuple of closed-set
                                                 warning constants
                                                 (each from
                                                 ``MEASUREMENT_WARNING_VALUES``).
      * ``raw_capture_ref``                   -- mirrored from the
                                                 Stage 27.3 output.
      * ``source_summary``                    -- mirrored.
      * ``context_schema_version``            -- locked Stage 27.4
                                                 combined measurement
                                                 schema version
                                                 string.
    """

    provider_id: Optional[str]
    provider_event_id: Optional[str]
    normalized_event_id: Optional[str]
    event_kind: str
    observed_at_utc: Optional[str]
    token_mint: Optional[str]
    quote_mint: Optional[str]
    pair_quote_asset: str
    pair_pair_type: str
    pair_bonding_curve_version: str
    pair_detection_status: str
    pair_detection_confidence: str
    pair_detection_reason: str
    pair_live_policy: str
    pair_calibration_lane: str
    composition_status: str
    composition_reason: str
    price_context: PriceContextRecord
    ath_context: AthContextRecord
    migration_context: MigrationContextRecord
    measurement_status: str
    measurement_warnings: Tuple[str, ...]
    raw_capture_ref: Optional[str]
    source_summary: Optional[str]
    context_schema_version: str


# ---------------------------------------------------------------------------
# Status / warnings resolution helpers
# ---------------------------------------------------------------------------


def _pair_is_supported(
    ingest_output: ProviderIngestOutputRecord,
) -> bool:
    """Return ``True`` iff the Stage 27.3 verdict admits Stage 27.4
    context attachment.

    Stage 27.4 still attaches a context record for unsupported
    pairs, but the combined status is ``UNSUPPORTED_PAIR``.
    """
    if ingest_output.composition_status == COMPOSITION_STATUS_COMPOSED:
        return True
    return False


def _build_warnings(
    ingest_output: ProviderIngestOutputRecord,
    price_context: PriceContextRecord,
    ath_context: AthContextRecord,
    migration_context: MigrationContextRecord,
) -> Tuple[str, ...]:
    """Return the closed-set warning tuple for the combined record.

    Pure / deterministic; the order is stable so a test can pin the
    exact tuple membership.
    """
    warnings: list[str] = []

    # Composition-level skip warnings (preserved so the operator
    # review can see WHY no context was attached).
    if (
        ingest_output.composition_status
        == COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
    ):
        warnings.append(
            WARNING_COMPOSITION_SKIPPED_UNSUPPORTED_EVENT
        )
    elif (
        ingest_output.composition_status
        == COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
    ):
        warnings.append(
            WARNING_COMPOSITION_SKIPPED_MISSING_TOKEN
        )
    elif ingest_output.composition_status == COMPOSITION_STATUS_ERROR:
        warnings.append(WARNING_COMPOSITION_ERROR)

    # Pair-level LIVE-suppression warnings. DISAGREE must be
    # checked BEFORE the UNRESOLVED / UNKNOWN-quote-asset fallback
    # because Stage 27.2 emits DISAGREE pairs with
    # ``pair_quote_asset == UNKNOWN`` (the disagreement collapses
    # the closed-set tokens).
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        warnings.append(WARNING_DISAGREE_PAIR_SUPPRESSED_IN_LIVE)
    elif (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
        or ingest_output.pair_quote_asset == QUOTE_ASSET_UNKNOWN
    ):
        warnings.append(WARNING_UNKNOWN_PAIR_SUPPRESSED_IN_LIVE)
    elif ingest_output.pair_quote_asset == QUOTE_ASSET_USDC:
        warnings.append(
            WARNING_USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION
        )

    # Price-context warnings.
    if price_context.price_status == PRICE_STATUS_STALE:
        warnings.append(WARNING_PRICE_STALE)
    elif price_context.price_status == PRICE_STATUS_UNAVAILABLE:
        warnings.append(WARNING_PRICE_UNAVAILABLE)
    elif price_context.price_status == PRICE_STATUS_SOURCE_ERROR:
        warnings.append(WARNING_PRICE_SOURCE_ERROR)

    # ATH-context warnings.
    if ath_context.ath_status == ATH_STATUS_UNAVAILABLE:
        warnings.append(WARNING_ATH_UNAVAILABLE)
    elif ath_context.ath_status == ATH_STATUS_SOURCE_ERROR:
        warnings.append(WARNING_ATH_SOURCE_ERROR)
    elif (
        ath_context.ath_status == ATH_STATUS_PRESENT
        and ath_context.ath_since_migration_status
        == ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
    ):
        warnings.append(WARNING_POST_MIGRATION_ATH_UNVERIFIED)

    # Migration-context warnings.
    if (
        migration_context.migration_status
        == MIGRATION_STATUS_MISSING
    ):
        warnings.append(WARNING_MIGRATION_MISSING)
    elif (
        migration_context.migration_status
        == MIGRATION_STATUS_UNTRUSTED
    ):
        warnings.append(WARNING_MIGRATION_UNTRUSTED)
    elif (
        migration_context.migration_status
        == MIGRATION_STATUS_SOURCE_ERROR
    ):
        warnings.append(WARNING_MIGRATION_SOURCE_ERROR)

    return tuple(warnings)


def _resolve_status(
    ingest_output: ProviderIngestOutputRecord,
    price_context: PriceContextRecord,
    ath_context: AthContextRecord,
    migration_context: MigrationContextRecord,
) -> str:
    """Return the combined ``measurement_status`` token.

    Precedence (highest first):

      1. ``UNSUPPORTED_PAIR``  -- Stage 27.3 skip or non-SOL lane.
      2. ``SOURCE_ERROR``      -- any sub-context returned SOURCE_ERROR.
      3. ``MISSING_PRICE``     -- price is unavailable.
      4. ``MISSING_ATH``       -- ATH is unavailable.
      5. ``MISSING_MIGRATION`` -- migration is missing.
      6. ``PARTIAL``           -- any downgrade (stale price,
                                  may-include-pre-migration ATH,
                                  untrusted migration, USDC observe-
                                  only lane).
      7. ``COMPLETE``          -- everything present and trusted.
    """
    if not _pair_is_supported(ingest_output):
        return MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    if (
        price_context.price_status == PRICE_STATUS_UNSUPPORTED_PAIR
        or ath_context.ath_status == ATH_STATUS_UNSUPPORTED_PAIR
        or migration_context.migration_status
        == MIGRATION_STATUS_UNSUPPORTED_PAIR
    ):
        return MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    if (
        price_context.price_status == PRICE_STATUS_SOURCE_ERROR
        or ath_context.ath_status == ATH_STATUS_SOURCE_ERROR
        or migration_context.migration_status
        == MIGRATION_STATUS_SOURCE_ERROR
    ):
        return MEASUREMENT_STATUS_SOURCE_ERROR
    if price_context.price_status == PRICE_STATUS_UNAVAILABLE:
        return MEASUREMENT_STATUS_MISSING_PRICE
    if ath_context.ath_status == ATH_STATUS_UNAVAILABLE:
        return MEASUREMENT_STATUS_MISSING_ATH
    if migration_context.migration_status == MIGRATION_STATUS_MISSING:
        return MEASUREMENT_STATUS_MISSING_MIGRATION

    partial = False
    if price_context.price_status == PRICE_STATUS_STALE:
        partial = True
    if (
        ath_context.ath_status == ATH_STATUS_PRESENT
        and ath_context.ath_since_migration_status
        == ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
    ):
        partial = True
    if ath_context.ath_status in (
        ATH_STATUS_STALE,
        ATH_STATUS_NOT_APPLICABLE,
    ):
        partial = True
    if (
        migration_context.migration_status
        == MIGRATION_STATUS_UNTRUSTED
    ):
        partial = True
    if ingest_output.pair_quote_asset == QUOTE_ASSET_USDC:
        partial = True

    if partial:
        return MEASUREMENT_STATUS_PARTIAL

    if (
        price_context.price_status == PRICE_STATUS_PRESENT
        and ath_context.ath_status == ATH_STATUS_PRESENT
        and ath_context.ath_since_migration_status
        == ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        and migration_context.migration_status
        == MIGRATION_STATUS_PRESENT
        and ingest_output.pair_quote_asset == QUOTE_ASSET_SOL
        and ingest_output.pair_calibration_lane
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    ):
        return MEASUREMENT_STATUS_COMPLETE

    return MEASUREMENT_STATUS_PARTIAL


# ---------------------------------------------------------------------------
# Public assembler
# ---------------------------------------------------------------------------


def assemble_measurement_context(
    ingest_output: ProviderIngestOutputRecord,
    price_context: PriceContextRecord,
    ath_context: AthContextRecord,
    migration_context: MigrationContextRecord,
) -> LiveMeasurementContextRecord:
    """Assemble a Stage 27.4 combined measurement context record.

    The function is pure / deterministic. It NEVER reads the
    process environment, NEVER opens a network connection, NEVER
    rewrites the underlying records, and NEVER widens the closed-
    set vocabulary.

    The function does NOT enforce Stage 26 policies and does NOT
    decide whether the event should be sent live -- that is the
    responsibility of a later Stage 27 substage.
    """
    if not isinstance(ingest_output, ProviderIngestOutputRecord):
        raise TypeError(
            "assemble_measurement_context requires a "
            "ProviderIngestOutputRecord"
        )
    if not isinstance(price_context, PriceContextRecord):
        raise TypeError(
            "assemble_measurement_context requires a "
            "PriceContextRecord"
        )
    if not isinstance(ath_context, AthContextRecord):
        raise TypeError(
            "assemble_measurement_context requires an "
            "AthContextRecord"
        )
    if not isinstance(migration_context, MigrationContextRecord):
        raise TypeError(
            "assemble_measurement_context requires a "
            "MigrationContextRecord"
        )

    warnings = _build_warnings(
        ingest_output,
        price_context,
        ath_context,
        migration_context,
    )
    status = _resolve_status(
        ingest_output,
        price_context,
        ath_context,
        migration_context,
    )

    return LiveMeasurementContextRecord(
        provider_id=ingest_output.provider_id,
        provider_event_id=ingest_output.provider_event_id,
        normalized_event_id=ingest_output.normalized_event_id,
        event_kind=ingest_output.event_kind,
        observed_at_utc=ingest_output.observed_at_utc,
        token_mint=ingest_output.token_mint,
        quote_mint=ingest_output.quote_mint,
        pair_quote_asset=ingest_output.pair_quote_asset,
        pair_pair_type=ingest_output.pair_pair_type,
        pair_bonding_curve_version=(
            ingest_output.pair_bonding_curve_version
        ),
        pair_detection_status=ingest_output.pair_detection_status,
        pair_detection_confidence=(
            ingest_output.pair_detection_confidence
        ),
        pair_detection_reason=(
            ingest_output.pair_detection_reason
        ),
        pair_live_policy=ingest_output.pair_live_policy,
        pair_calibration_lane=ingest_output.pair_calibration_lane,
        composition_status=ingest_output.composition_status,
        composition_reason=ingest_output.composition_reason,
        price_context=price_context,
        ath_context=ath_context,
        migration_context=migration_context,
        measurement_status=status,
        measurement_warnings=warnings,
        raw_capture_ref=ingest_output.raw_capture_ref,
        source_summary=ingest_output.source_summary,
        context_schema_version=(
            STAGE27_4_MEASUREMENT_SCHEMA_VERSION
        ),
    )
