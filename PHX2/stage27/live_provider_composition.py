"""Stage 27.3 provider-ingest composition pipeline.

The single Stage 27.3 entry point that runs the deterministic
pipeline:

  1. Stage 27.3 ingest input (or normalized-event-like) is
     validated.
  2. The Stage 27.3 adapter projects the input into the Stage
     27.2 pair-detection input shape.
  3. The Stage 27.2 ``classify_pair`` classifier runs over the
     pair-detection input.
  4. Stage 27.3 emits one immutable
     ``ProviderIngestOutputRecord`` carrying the closed-set
     composition status, the closed-set composition reason, the
     full Stage 27.2 pair-classification verdict, and the safe
     provenance fields.

Stage 27.3 deliberately does NOT:

  * open any provider connection,
  * call Helius / gRPC / Birdeye / Discord / Telegram / X-social,
  * read the process environment,
  * render a private ping,
  * send a private ping,
  * dedupe events,
  * run a runner,
  * enforce Stage 26 policy candidates,
  * map UNKNOWN / DISAGREE / USDC results into the existing SOL
    lane (those lanes are preserved exactly as Stage 27.2 emits
    them).

Composition policy:

  * Unsupported event kinds (``EVENT_KIND_UNKNOWN`` or any value
    outside ``SUPPORTED_EVENT_KINDS``) yield
    ``SKIPPED_UNSUPPORTED_EVENT`` /
    ``UNSUPPORTED_EVENT_KIND``. The pair fields fall back to the
    Stage 27.2 UNKNOWN / UNRESOLVED defaults so no caller can
    accidentally trade on a skipped event.
  * Supported kinds with a missing token mint yield
    ``SKIPPED_MISSING_TOKEN`` / ``MISSING_TOKEN_MINT``. Again the
    pair fields fall back to UNKNOWN / UNRESOLVED defaults.
  * Supported kinds with a token mint are classified through
    Stage 27.2:
      - ``UNRESOLVED`` -> ``CLASSIFIED_UNKNOWN`` /
        ``PAIR_UNRESOLVED``
      - ``DISAGREE``   -> ``CLASSIFIED_DISAGREE`` /
        ``PAIR_DISAGREE``
      - ``CONFIRMED`` / ``PROVIDER_ONLY`` -> ``COMPOSED`` / ``OK``

This module imports only stdlib (``typing``) plus Stage 27.2 and
Stage 27.3 production modules. It does NOT import Stage 21-26
production code, does NOT import Stage 27.1 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_UNKNOWN,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    PAIR_DETECTION_CONFIDENCE_NONE,
    PAIR_DETECTION_REASON_NO_EVIDENCE,
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    PAIR_TYPE_UNKNOWN,
    QUOTE_ASSET_UNKNOWN,
)
from PHX2.stage27.pair_detection_models import (
    PairDetectionOutputRecord,
)
from PHX2.stage27.provider_event_adapter import (
    NormalizedEventLike,
    adapt_ingest_input_to_pair_input,
    adapt_normalized_event_to_ingest_input,
)
from PHX2.stage27.provider_ingest_contracts import (
    Stage27ProviderIngestError,
    Stage27ProviderIngestInvalidEventError,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_INVALID_INPUT_SHAPE,
    COMPOSITION_REASON_MISSING_TOKEN_MINT,
    COMPOSITION_REASON_OK,
    COMPOSITION_REASON_PAIR_DISAGREE,
    COMPOSITION_REASON_PAIR_UNRESOLVED,
    COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND,
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_ERROR,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    EVENT_KIND_UNKNOWN,
    ProviderIngestInputRecord,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
    SUPPORTED_EVENT_KINDS,
)
from PHX2.stage27.pump_pair_classifier import classify_pair


# ---------------------------------------------------------------------------
# Helpers: skipped / error outputs
# ---------------------------------------------------------------------------


def _unresolved_pair_verdict_fields() -> dict:
    """Return the locked Stage 27.2 UNRESOLVED / UNKNOWN verdict
    field set used when Stage 27.3 skips an event before running
    the classifier.

    Returning these fields verbatim means USDC / UNKNOWN / DISAGREE
    cases never accidentally route into ``EXISTING_SOL_LANE`` --
    the lane is the locked ``UNKNOWN_PAIR_OBSERVE_ONLY``.
    """
    return {
        "pair_quote_asset": QUOTE_ASSET_UNKNOWN,
        "pair_pair_type": PAIR_TYPE_UNKNOWN,
        "pair_bonding_curve_version": BONDING_CURVE_VERSION_UNKNOWN,
        "pair_detection_status": PAIR_DETECTION_STATUS_UNRESOLVED,
        "pair_detection_confidence": PAIR_DETECTION_CONFIDENCE_NONE,
        "pair_detection_reason": PAIR_DETECTION_REASON_NO_EVIDENCE,
        "pair_live_policy": LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        "pair_calibration_lane": (
            CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
        ),
    }


def _build_output(
    record: ProviderIngestInputRecord,
    *,
    composition_status: str,
    composition_reason: str,
    pair_fields: Mapping[str, str],
) -> ProviderIngestOutputRecord:
    """Construct a ``ProviderIngestOutputRecord`` from the input
    provenance and a Stage 27.2 pair-verdict field mapping.

    Pure / deterministic.
    """
    return ProviderIngestOutputRecord(
        provider_id=record.provider_id,
        provider_event_id=record.provider_event_id,
        normalized_event_id=record.normalized_event_id,
        event_kind=record.event_kind,
        observed_at_utc=record.observed_at_utc,
        token_mint=record.token_mint,
        quote_mint=record.quote_mint,
        pair_quote_asset=pair_fields["pair_quote_asset"],
        pair_pair_type=pair_fields["pair_pair_type"],
        pair_bonding_curve_version=(
            pair_fields["pair_bonding_curve_version"]
        ),
        pair_detection_status=(
            pair_fields["pair_detection_status"]
        ),
        pair_detection_confidence=(
            pair_fields["pair_detection_confidence"]
        ),
        pair_detection_reason=(
            pair_fields["pair_detection_reason"]
        ),
        pair_live_policy=pair_fields["pair_live_policy"],
        pair_calibration_lane=(
            pair_fields["pair_calibration_lane"]
        ),
        raw_capture_ref=record.raw_capture_ref,
        source_summary=record.source_summary,
        composition_status=composition_status,
        composition_reason=composition_reason,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _pair_fields_from_classifier_output(
    output: PairDetectionOutputRecord,
) -> dict:
    """Project a Stage 27.2 ``PairDetectionOutputRecord`` into the
    Stage 27.3 ``pair_*`` field mapping used by the output record.
    """
    return {
        "pair_quote_asset": output.quote_asset,
        "pair_pair_type": output.pair_type,
        "pair_bonding_curve_version": output.bonding_curve_version,
        "pair_detection_status": output.pair_detection_status,
        "pair_detection_confidence": (
            output.pair_detection_confidence
        ),
        "pair_detection_reason": output.pair_detection_reason,
        "pair_live_policy": output.live_policy,
        "pair_calibration_lane": output.calibration_lane,
    }


# ---------------------------------------------------------------------------
# Public composer
# ---------------------------------------------------------------------------


def compose_provider_ingest_event(
    record: ProviderIngestInputRecord,
) -> ProviderIngestOutputRecord:
    """Compose a single Stage 27.3 provider-ingest input record.

    Returns one immutable ``ProviderIngestOutputRecord``. The
    Stage 27.2 ``classify_pair`` classifier is the sole pair-
    classification authority -- Stage 27.3 never duplicates pair-
    classification logic. Stage 27.3 only routes the verdict into
    a composition-status / composition-reason pair.

    Raises ``Stage27ProviderIngestInvalidEventError`` only when
    ``record`` is not a ``ProviderIngestInputRecord`` (the only
    structural shape error Stage 27.3 raises). All other shape
    issues -- missing token mint, unsupported event kind, UNKNOWN /
    DISAGREE pair verdict -- resolve to typed composition statuses
    rather than raising.

    Pure / deterministic; never reads the process environment,
    never opens a network connection, never sends anything live.
    """
    if not isinstance(record, ProviderIngestInputRecord):
        raise Stage27ProviderIngestInvalidEventError(
            "record must be a ProviderIngestInputRecord",
            offending_type_name=type(record).__name__,
        )

    event_kind = record.event_kind
    if (
        event_kind == EVENT_KIND_UNKNOWN
        or event_kind not in SUPPORTED_EVENT_KINDS
    ):
        return _build_output(
            record,
            composition_status=(
                COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
            ),
            composition_reason=(
                COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND
            ),
            pair_fields=_unresolved_pair_verdict_fields(),
        )

    if not isinstance(record.token_mint, str) or record.token_mint == "":
        return _build_output(
            record,
            composition_status=(
                COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
            ),
            composition_reason=(
                COMPOSITION_REASON_MISSING_TOKEN_MINT
            ),
            pair_fields=_unresolved_pair_verdict_fields(),
        )

    pair_input = adapt_ingest_input_to_pair_input(record)
    pair_output = classify_pair(pair_input)
    pair_fields = _pair_fields_from_classifier_output(pair_output)

    status = pair_output.pair_detection_status
    if status == PAIR_DETECTION_STATUS_DISAGREE:
        return _build_output(
            record,
            composition_status=(
                COMPOSITION_STATUS_CLASSIFIED_DISAGREE
            ),
            composition_reason=COMPOSITION_REASON_PAIR_DISAGREE,
            pair_fields=pair_fields,
        )
    if status == PAIR_DETECTION_STATUS_UNRESOLVED:
        return _build_output(
            record,
            composition_status=(
                COMPOSITION_STATUS_CLASSIFIED_UNKNOWN
            ),
            composition_reason=COMPOSITION_REASON_PAIR_UNRESOLVED,
            pair_fields=pair_fields,
        )
    if status in (
        PAIR_DETECTION_STATUS_CONFIRMED,
        PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    ):
        return _build_output(
            record,
            composition_status=COMPOSITION_STATUS_COMPOSED,
            composition_reason=COMPOSITION_REASON_OK,
            pair_fields=pair_fields,
        )

    # Defensive default: an unrecognized pair_detection_status is
    # treated as an error rather than silently composed.
    return _build_output(
        record,
        composition_status=COMPOSITION_STATUS_ERROR,
        composition_reason=COMPOSITION_REASON_INVALID_INPUT_SHAPE,
        pair_fields=pair_fields,
    )


def compose_provider_ingest_from_normalized_event(
    event_like: NormalizedEventLike,
    *,
    provider_id: Optional[str] = None,
    pool_account: Optional[str] = None,
    pool_program_id: Optional[str] = None,
    base_mint: Optional[str] = None,
    quote_mint: Optional[str] = None,
    bonding_curve_program_id: Optional[str] = None,
    bonding_curve_version_hint: Optional[str] = None,
    migration_event_quote_asset_hint: Optional[str] = None,
    provider_quote_asset_hint: Optional[str] = None,
    provider_pair_type_hint: Optional[str] = None,
    provider_bonding_curve_version_hint: Optional[str] = None,
    source_summary: Optional[str] = None,
    extra_fields: Optional[Mapping[str, object]] = None,
) -> ProviderIngestOutputRecord:
    """Convenience composer: ``event_like`` -> Stage 27.3 output.

    Runs the Stage 27.3 adapter first (which validates the event
    shape, rejects raw-payload-class extras, and projects the
    upstream normalized event into a
    ``ProviderIngestInputRecord``), then composes the ingest
    output. Pure / deterministic.

    Any Stage 27.3 typed error raised by the adapter (invalid
    event shape, rejected raw-payload-class key) propagates to the
    caller. A non-Stage-27.3 ``Exception`` is converted into an
    ``ERROR`` composition output so the composer never silently
    swallows an unknown failure: the safer behaviour for a
    deterministic pipeline is to surface the ERROR record (with
    UNKNOWN pair fields) rather than to crash the per-event loop.
    """
    try:
        record = adapt_normalized_event_to_ingest_input(
            event_like,
            provider_id=provider_id,
            pool_account=pool_account,
            pool_program_id=pool_program_id,
            base_mint=base_mint,
            quote_mint=quote_mint,
            bonding_curve_program_id=bonding_curve_program_id,
            bonding_curve_version_hint=bonding_curve_version_hint,
            migration_event_quote_asset_hint=(
                migration_event_quote_asset_hint
            ),
            provider_quote_asset_hint=provider_quote_asset_hint,
            provider_pair_type_hint=provider_pair_type_hint,
            provider_bonding_curve_version_hint=(
                provider_bonding_curve_version_hint
            ),
            source_summary=source_summary,
            extra_fields=extra_fields,
        )
    except Stage27ProviderIngestError:
        # Stage 27.3 typed errors are the contract; re-raise so the
        # caller can inspect ``.reason`` / ``.field_name``.
        raise
    return compose_provider_ingest_event(record)
