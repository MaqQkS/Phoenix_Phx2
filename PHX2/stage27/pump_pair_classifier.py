"""Stage 27.2 deterministic Pump pair classifier skeleton.

The classifier is a pure function over a single
``PairDetectionInputRecord``. It gathers evidence from the input,
applies a deterministic source-strength hierarchy, and returns a
single immutable ``PairDetectionOutputRecord``.

Stage 27.2 does NOT:

  * read the process environment,
  * call any provider (no Helius / gRPC / Birdeye client),
  * import any network / RPC / messaging / DB / scheduler library,
  * import Stage 21-26 production code,
  * send anything to Discord / Telegram / X-social,
  * implement provider ingest, price / migration / ATH context,
    ping rendering, candidate assembly, bounded runner, dedupe,
    enforcement, public routing, or X / social.

Source-strength hierarchy (strongest first):

  1. ``POOL_QUOTE_MINT``         (strong)
  2. ``BONDING_CURVE_METADATA``  (strong)
  3. ``MIGRATION_EVENT``         (middle)
  4. ``PROVIDER_PAYLOAD``        (weak)
  5. ``KNOWN_MINT_FALLBACK``     (weak)

Resolution rules (deterministic):

  * If two or more strong sources disagree -> ``DISAGREE`` / ``LOW``
    / ``LIVE_SUPPRESS_DISAGREE`` / ``DISAGREE_PAIR_OBSERVE_ONLY``.
    quote_asset / pair_type / bonding_curve_version all fall back
    to ``UNKNOWN``.
  * If a strong source agrees with itself AND any middle / weak
    source contradicts it -> ``DISAGREE`` / ``LOW`` /
    ``LIVE_SUPPRESS_DISAGREE``.
  * If a strong source agrees with itself AND every middle / weak
    source agrees (or stays silent) -> ``CONFIRMED`` / ``HIGH``.
  * If no strong source fires but middle / weak sources agree ->
    ``PROVIDER_ONLY`` / ``MEDIUM``.
  * If middle / weak sources disagree -> ``DISAGREE`` / ``LOW``.
  * If no source fires (or every source returned ``UNKNOWN``) ->
    ``UNRESOLVED`` / ``NONE`` / ``UNKNOWN`` /
    ``LIVE_SUPPRESS_UNKNOWN`` / ``UNKNOWN_PAIR_OBSERVE_ONLY``.

LIVE-policy / calibration-lane rules:

  * SOL ``CONFIRMED`` / ``PROVIDER_ONLY`` -> ``LIVE_ALLOWED`` /
    ``EXISTING_SOL_LANE`` (classification policy only -- Stage 27.2
    does NOT actually send anything).
  * USDC ``CONFIRMED`` / ``PROVIDER_ONLY`` -> ``DRY_RUN_ONLY`` /
    ``USDC_OBSERVE_ONLY``. USDC MUST NOT use the SOL lane.
  * UNKNOWN -> ``LIVE_SUPPRESS_UNKNOWN`` /
    ``UNKNOWN_PAIR_OBSERVE_ONLY``. UNKNOWN MUST NOT use the SOL
    lane.
  * DISAGREE -> ``LIVE_SUPPRESS_DISAGREE`` /
    ``DISAGREE_PAIR_OBSERVE_ONLY``.

This module imports only stdlib (``typing``) plus other Stage 27.2
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_SOL_LEGACY,
    BONDING_CURVE_VERSION_UNKNOWN,
    BONDING_CURVE_VERSION_USDC_FIXED,
    BONDING_CURVE_VERSION_VALUES,
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    LIVE_POLICY_DRY_RUN_ONLY,
    LIVE_POLICY_LIVE_ALLOWED,
    LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    PAIR_DETECTION_CONFIDENCE_HIGH,
    PAIR_DETECTION_CONFIDENCE_LOW,
    PAIR_DETECTION_CONFIDENCE_MEDIUM,
    PAIR_DETECTION_CONFIDENCE_NONE,
    PAIR_DETECTION_REASON_BONDING_CURVE_VS_QUOTE_MINT_DISAGREE,
    PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
    PAIR_DETECTION_REASON_MALFORMED_QUOTE_MINT,
    PAIR_DETECTION_REASON_MIGRATION_HINT_ONLY,
    PAIR_DETECTION_REASON_NO_EVIDENCE,
    PAIR_DETECTION_REASON_PROVIDER_INTERNAL_INCONSISTENT,
    PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE,
    PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE,
    PAIR_DETECTION_REASON_SINGLE_STRONG_SOURCE,
    PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE,
    PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
    PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
    PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
    PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
    PAIR_DETECTION_SOURCES_STRONG,
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    PAIR_TYPE_PUMP_SOL,
    PAIR_TYPE_PUMP_USDC,
    PAIR_TYPE_UNKNOWN,
    PAIR_TYPE_VALUES,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
    QUOTE_ASSET_VALUES,
    bonding_curve_version_for_quote_asset,
    classify_known_quote_mint,
    pair_type_for_quote_asset,
)
from PHX2.stage27.pair_detection_contracts import (
    Stage27InvalidPairInputError,
)
from PHX2.stage27.pair_detection_models import (
    PairDetectionEvidenceRecord,
    PairDetectionInputRecord,
    PairDetectionOutputRecord,
)


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _is_meaningful_string(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _gather_pool_quote_mint_evidence(
    quote_mint: Optional[str],
) -> Optional[PairDetectionEvidenceRecord]:
    """Build the POOL_QUOTE_MINT evidence record, or ``None`` when
    the input did not carry a quote-mint string.
    """
    if not _is_meaningful_string(quote_mint):
        return None
    assert quote_mint is not None  # for type narrowing
    asset = classify_known_quote_mint(quote_mint)
    if asset == QUOTE_ASSET_UNKNOWN:
        # An unrecognized quote-mint string MUST NOT silently
        # promote to SOL. Record an UNKNOWN verdict with LOW
        # confidence so the downstream classifier treats it as
        # weak / non-evidence.
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
            quote_asset_verdict=QUOTE_ASSET_UNKNOWN,
            pair_type_verdict=PAIR_TYPE_UNKNOWN,
            bonding_curve_version_verdict=BONDING_CURVE_VERSION_UNKNOWN,
            confidence=PAIR_DETECTION_CONFIDENCE_LOW,
            reason=PAIR_DETECTION_REASON_MALFORMED_QUOTE_MINT,
        )
    return PairDetectionEvidenceRecord(
        source=PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
        quote_asset_verdict=asset,
        pair_type_verdict=pair_type_for_quote_asset(asset),
        bonding_curve_version_verdict=(
            bonding_curve_version_for_quote_asset(asset)
        ),
        confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        reason=None,
    )


def _gather_bonding_curve_metadata_evidence(
    bcv_hint: Optional[str],
) -> Optional[PairDetectionEvidenceRecord]:
    """Build the BONDING_CURVE_METADATA evidence record, or ``None``
    when the input did not carry a bonding-curve-version hint.
    """
    if not _is_meaningful_string(bcv_hint):
        return None
    if bcv_hint == BONDING_CURVE_VERSION_SOL_LEGACY:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
            quote_asset_verdict=QUOTE_ASSET_SOL,
            pair_type_verdict=PAIR_TYPE_PUMP_SOL,
            bonding_curve_version_verdict=(
                BONDING_CURVE_VERSION_SOL_LEGACY
            ),
            confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
            reason=None,
        )
    if bcv_hint == BONDING_CURVE_VERSION_USDC_FIXED:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
            quote_asset_verdict=QUOTE_ASSET_USDC,
            pair_type_verdict=PAIR_TYPE_PUMP_USDC,
            bonding_curve_version_verdict=(
                BONDING_CURVE_VERSION_USDC_FIXED
            ),
            confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
            reason=None,
        )
    # Unknown / unrecognized hint -> UNKNOWN verdict.
    return PairDetectionEvidenceRecord(
        source=PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
        quote_asset_verdict=QUOTE_ASSET_UNKNOWN,
        pair_type_verdict=PAIR_TYPE_UNKNOWN,
        bonding_curve_version_verdict=BONDING_CURVE_VERSION_UNKNOWN,
        confidence=PAIR_DETECTION_CONFIDENCE_LOW,
        reason=None,
    )


def _gather_migration_event_evidence(
    migration_hint: Optional[str],
) -> Optional[PairDetectionEvidenceRecord]:
    """Build the MIGRATION_EVENT evidence record, or ``None`` when
    the input did not carry a migration hint.
    """
    if not _is_meaningful_string(migration_hint):
        return None
    if migration_hint == QUOTE_ASSET_SOL:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
            quote_asset_verdict=QUOTE_ASSET_SOL,
            pair_type_verdict=PAIR_TYPE_PUMP_SOL,
            bonding_curve_version_verdict=None,
            confidence=PAIR_DETECTION_CONFIDENCE_MEDIUM,
            reason=None,
        )
    if migration_hint == QUOTE_ASSET_USDC:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
            quote_asset_verdict=QUOTE_ASSET_USDC,
            pair_type_verdict=PAIR_TYPE_PUMP_USDC,
            bonding_curve_version_verdict=None,
            confidence=PAIR_DETECTION_CONFIDENCE_MEDIUM,
            reason=None,
        )
    return PairDetectionEvidenceRecord(
        source=PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
        quote_asset_verdict=QUOTE_ASSET_UNKNOWN,
        pair_type_verdict=PAIR_TYPE_UNKNOWN,
        bonding_curve_version_verdict=None,
        confidence=PAIR_DETECTION_CONFIDENCE_LOW,
        reason=None,
    )


def _provider_asset_verdict(
    provider_quote_asset_hint: Optional[str],
    provider_pair_type_hint: Optional[str],
) -> tuple[str, str, Optional[str]]:
    """Reconcile the provider quote-asset and pair-type hints into a
    single (quote_asset, pair_type, reason) tuple.

    The returned reason is ``None`` for an internally consistent
    provider hint, or
    ``PAIR_DETECTION_REASON_PROVIDER_INTERNAL_INCONSISTENT`` when
    the two hints contradict each other.
    """
    qa_norm: Optional[str] = (
        provider_quote_asset_hint
        if provider_quote_asset_hint in QUOTE_ASSET_VALUES
        else None
    )
    pt_norm: Optional[str] = (
        provider_pair_type_hint
        if provider_pair_type_hint in PAIR_TYPE_VALUES
        else None
    )

    # Both fields missing or unrecognized -> UNKNOWN verdict.
    if (qa_norm is None or qa_norm == QUOTE_ASSET_UNKNOWN) and (
        pt_norm is None or pt_norm == PAIR_TYPE_UNKNOWN
    ):
        return QUOTE_ASSET_UNKNOWN, PAIR_TYPE_UNKNOWN, None

    # Derive a candidate (asset, pair_type) from each hint and
    # reconcile them.
    candidate_asset: Optional[str] = None
    candidate_pair_type: Optional[str] = None
    if qa_norm == QUOTE_ASSET_SOL:
        candidate_asset = QUOTE_ASSET_SOL
        candidate_pair_type = PAIR_TYPE_PUMP_SOL
    elif qa_norm == QUOTE_ASSET_USDC:
        candidate_asset = QUOTE_ASSET_USDC
        candidate_pair_type = PAIR_TYPE_PUMP_USDC

    pair_asset: Optional[str] = None
    if pt_norm == PAIR_TYPE_PUMP_SOL:
        pair_asset = QUOTE_ASSET_SOL
    elif pt_norm == PAIR_TYPE_PUMP_USDC:
        pair_asset = QUOTE_ASSET_USDC

    if candidate_asset is not None and pair_asset is not None:
        if candidate_asset != pair_asset:
            return (
                QUOTE_ASSET_UNKNOWN,
                PAIR_TYPE_UNKNOWN,
                PAIR_DETECTION_REASON_PROVIDER_INTERNAL_INCONSISTENT,
            )
        return candidate_asset, candidate_pair_type or PAIR_TYPE_UNKNOWN, None

    if candidate_asset is not None:
        return candidate_asset, candidate_pair_type or PAIR_TYPE_UNKNOWN, None

    if pair_asset is not None:
        return (
            pair_asset,
            PAIR_TYPE_PUMP_SOL
            if pair_asset == QUOTE_ASSET_SOL
            else PAIR_TYPE_PUMP_USDC,
            None,
        )

    return QUOTE_ASSET_UNKNOWN, PAIR_TYPE_UNKNOWN, None


def _gather_provider_payload_evidence(
    provider_quote_asset_hint: Optional[str],
    provider_pair_type_hint: Optional[str],
    provider_bonding_curve_version_hint: Optional[str],
) -> Optional[PairDetectionEvidenceRecord]:
    """Build the PROVIDER_PAYLOAD evidence record, or ``None`` when
    the input did not carry any provider hint at all.
    """
    if (
        not _is_meaningful_string(provider_quote_asset_hint)
        and not _is_meaningful_string(provider_pair_type_hint)
        and not _is_meaningful_string(
            provider_bonding_curve_version_hint
        )
    ):
        return None

    asset, pair_type, conflict_reason = _provider_asset_verdict(
        provider_quote_asset_hint=provider_quote_asset_hint,
        provider_pair_type_hint=provider_pair_type_hint,
    )

    bcv_verdict: Optional[str] = None
    if provider_bonding_curve_version_hint in BONDING_CURVE_VERSION_VALUES:
        bcv_verdict = provider_bonding_curve_version_hint

    if conflict_reason is not None:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
            quote_asset_verdict=QUOTE_ASSET_UNKNOWN,
            pair_type_verdict=PAIR_TYPE_UNKNOWN,
            bonding_curve_version_verdict=bcv_verdict,
            confidence=PAIR_DETECTION_CONFIDENCE_LOW,
            reason=conflict_reason,
        )

    if asset == QUOTE_ASSET_UNKNOWN:
        return PairDetectionEvidenceRecord(
            source=PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
            quote_asset_verdict=QUOTE_ASSET_UNKNOWN,
            pair_type_verdict=PAIR_TYPE_UNKNOWN,
            bonding_curve_version_verdict=bcv_verdict,
            confidence=PAIR_DETECTION_CONFIDENCE_LOW,
            reason=None,
        )

    return PairDetectionEvidenceRecord(
        source=PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
        quote_asset_verdict=asset,
        pair_type_verdict=pair_type,
        bonding_curve_version_verdict=bcv_verdict,
        confidence=PAIR_DETECTION_CONFIDENCE_MEDIUM,
        reason=None,
    )


def gather_evidence(
    input_record: PairDetectionInputRecord,
) -> tuple[PairDetectionEvidenceRecord, ...]:
    """Project an input record into the immutable evidence tuple.

    Public helper exposed for downstream tests / future Stage 27.3+
    composers. Pure / deterministic; never reads the process
    environment, never opens a network connection.
    """
    if not isinstance(input_record, PairDetectionInputRecord):
        raise Stage27InvalidPairInputError(
            "input must be a PairDetectionInputRecord",
            offending_type_name=type(input_record).__name__,
        )
    evidence: list[PairDetectionEvidenceRecord] = []
    pool_evidence = _gather_pool_quote_mint_evidence(
        input_record.quote_mint
    )
    if pool_evidence is not None:
        evidence.append(pool_evidence)
    bcv_evidence = _gather_bonding_curve_metadata_evidence(
        input_record.bonding_curve_version_hint
    )
    if bcv_evidence is not None:
        evidence.append(bcv_evidence)
    migration_evidence = _gather_migration_event_evidence(
        input_record.migration_event_quote_asset_hint
    )
    if migration_evidence is not None:
        evidence.append(migration_evidence)
    provider_evidence = _gather_provider_payload_evidence(
        provider_quote_asset_hint=(
            input_record.provider_quote_asset_hint
        ),
        provider_pair_type_hint=(
            input_record.provider_pair_type_hint
        ),
        provider_bonding_curve_version_hint=(
            input_record.provider_bonding_curve_version_hint
        ),
    )
    if provider_evidence is not None:
        evidence.append(provider_evidence)
    return tuple(evidence)


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _meaningful_asset_verdicts(
    evidence: tuple[PairDetectionEvidenceRecord, ...],
    sources: tuple[str, ...],
) -> set[str]:
    """Return the set of non-UNKNOWN quote-asset verdicts emitted by
    evidence records whose source is in ``sources``.
    """
    verdicts: set[str] = set()
    for record in evidence:
        if record.source not in sources:
            continue
        if (
            record.quote_asset_verdict is None
            or record.quote_asset_verdict == QUOTE_ASSET_UNKNOWN
        ):
            continue
        verdicts.add(record.quote_asset_verdict)
    return verdicts


def _all_distinct_asset_verdicts(
    evidence: tuple[PairDetectionEvidenceRecord, ...],
) -> set[str]:
    verdicts: set[str] = set()
    for record in evidence:
        if (
            record.quote_asset_verdict is None
            or record.quote_asset_verdict == QUOTE_ASSET_UNKNOWN
        ):
            continue
        verdicts.add(record.quote_asset_verdict)
    return verdicts


def _live_policy_and_lane_for_resolved_asset(
    asset: str,
    status: str,
) -> tuple[str, str]:
    """Return ``(live_policy, calibration_lane)`` for a resolved asset.

    Stage 27.2 policy:

      * SOL ``CONFIRMED`` / ``PROVIDER_ONLY`` ->
        ``LIVE_ALLOWED`` + ``EXISTING_SOL_LANE``.
      * USDC ``CONFIRMED`` / ``PROVIDER_ONLY`` ->
        ``DRY_RUN_ONLY`` + ``USDC_OBSERVE_ONLY``. USDC MUST NOT
        use the SOL lane.
      * Anything else -> caller is responsible for using the
        DISAGREE / UNRESOLVED helpers below; we hard-fail here so
        the caller cannot accidentally map UNKNOWN to SOL.
    """
    if asset == QUOTE_ASSET_SOL:
        return (
            LIVE_POLICY_LIVE_ALLOWED,
            CALIBRATION_LANE_EXISTING_SOL_LANE,
        )
    if asset == QUOTE_ASSET_USDC:
        return (
            LIVE_POLICY_DRY_RUN_ONLY,
            CALIBRATION_LANE_USDC_OBSERVE_ONLY,
        )
    raise Stage27InvalidPairInputError(
        f"_live_policy_and_lane_for_resolved_asset: invalid asset "
        f"{asset!r}; only SOL / USDC are resolvable lanes"
    )


def _unresolved_output(
    quote_mint: Optional[str],
    evidence_count: int,
    disagreement_count: int,
    reason: str,
) -> PairDetectionOutputRecord:
    """Return the canonical UNRESOLVED / UNKNOWN output."""
    return PairDetectionOutputRecord(
        quote_asset=QUOTE_ASSET_UNKNOWN,
        quote_mint=quote_mint,
        pair_type=PAIR_TYPE_UNKNOWN,
        bonding_curve_version=BONDING_CURVE_VERSION_UNKNOWN,
        pair_detection_status=PAIR_DETECTION_STATUS_UNRESOLVED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_NONE,
        pair_detection_reason=reason,
        evidence_count=evidence_count,
        disagreement_count=disagreement_count,
        live_policy=LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        calibration_lane=CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    )


def _disagree_output(
    quote_mint: Optional[str],
    evidence_count: int,
    disagreement_count: int,
    reason: str,
) -> PairDetectionOutputRecord:
    """Return the canonical DISAGREE output.

    DISAGREE collapses every directional field to UNKNOWN so a
    downstream consumer cannot accidentally trade on a disputed
    pair. The lane is ``DISAGREE_PAIR_OBSERVE_ONLY`` (NOT the SOL
    lane).
    """
    return PairDetectionOutputRecord(
        quote_asset=QUOTE_ASSET_UNKNOWN,
        quote_mint=quote_mint,
        pair_type=PAIR_TYPE_UNKNOWN,
        bonding_curve_version=BONDING_CURVE_VERSION_UNKNOWN,
        pair_detection_status=PAIR_DETECTION_STATUS_DISAGREE,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_LOW,
        pair_detection_reason=reason,
        evidence_count=evidence_count,
        disagreement_count=disagreement_count,
        live_policy=LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
        calibration_lane=CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    )


def _resolved_output(
    asset: str,
    status: str,
    confidence: str,
    reason: str,
    quote_mint: Optional[str],
    evidence_count: int,
    disagreement_count: int,
) -> PairDetectionOutputRecord:
    live_policy, calibration_lane = (
        _live_policy_and_lane_for_resolved_asset(asset, status)
    )
    return PairDetectionOutputRecord(
        quote_asset=asset,
        quote_mint=quote_mint,
        pair_type=pair_type_for_quote_asset(asset),
        bonding_curve_version=(
            bonding_curve_version_for_quote_asset(asset)
        ),
        pair_detection_status=status,
        pair_detection_confidence=confidence,
        pair_detection_reason=reason,
        evidence_count=evidence_count,
        disagreement_count=disagreement_count,
        live_policy=live_policy,
        calibration_lane=calibration_lane,
    )


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------


def classify_pair(
    input_record: PairDetectionInputRecord,
) -> PairDetectionOutputRecord:
    """Deterministic pair classifier over a single input record.

    Returns one immutable ``PairDetectionOutputRecord``. Never reads
    the process environment, never opens a network connection,
    never calls a provider. Raises
    ``Stage27InvalidPairInputError`` only if ``input_record`` is
    not a ``PairDetectionInputRecord`` instance (a structurally
    invalid call); every other shape -- including missing /
    malformed optional fields -- resolves to an UNRESOLVED or
    UNKNOWN classification rather than raising.
    """
    if not isinstance(input_record, PairDetectionInputRecord):
        raise Stage27InvalidPairInputError(
            "input must be a PairDetectionInputRecord",
            offending_type_name=type(input_record).__name__,
        )

    evidence = gather_evidence(input_record)
    evidence_count = len(evidence)
    quote_mint = (
        input_record.quote_mint
        if isinstance(input_record.quote_mint, str)
        else None
    )

    all_distinct = _all_distinct_asset_verdicts(evidence)
    disagreement_count = max(0, len(all_distinct) - 1)

    strong_verdicts = _meaningful_asset_verdicts(
        evidence, PAIR_DETECTION_SOURCES_STRONG
    )

    # Case A: strong sources disagree among themselves -> DISAGREE.
    if len(strong_verdicts) >= 2:
        return _disagree_output(
            quote_mint=quote_mint,
            evidence_count=evidence_count,
            disagreement_count=disagreement_count,
            reason=(
                PAIR_DETECTION_REASON_BONDING_CURVE_VS_QUOTE_MINT_DISAGREE
                if _strong_sources_split(evidence)
                else PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE
            ),
        )

    # Case B: exactly one strong asset verdict.
    if len(strong_verdicts) == 1:
        chosen = next(iter(strong_verdicts))
        # Any non-UNKNOWN provider / middle verdict that disagrees
        # is a strong-vs-weak disagreement.
        other_verdicts = _all_distinct_asset_verdicts(
            tuple(
                r
                for r in evidence
                if r.source not in PAIR_DETECTION_SOURCES_STRONG
            )
        )
        if other_verdicts and chosen not in other_verdicts:
            return _disagree_output(
                quote_mint=quote_mint,
                evidence_count=evidence_count,
                disagreement_count=disagreement_count,
                reason=(
                    PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE
                ),
            )
        # Determine whether multiple strong sources agree (boosts
        # the reason to CONFIRMED_AGREEMENT) or only one strong
        # source spoke (SINGLE_STRONG_SOURCE). Confidence remains
        # HIGH in both cases because a strong source is canonical.
        strong_record_count = sum(
            1
            for r in evidence
            if r.source in PAIR_DETECTION_SOURCES_STRONG
            and r.quote_asset_verdict not in (
                None,
                QUOTE_ASSET_UNKNOWN,
            )
        )
        reason = (
            PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT
            if strong_record_count >= 2
            else PAIR_DETECTION_REASON_SINGLE_STRONG_SOURCE
        )
        return _resolved_output(
            asset=chosen,
            status=PAIR_DETECTION_STATUS_CONFIRMED,
            confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
            reason=reason,
            quote_mint=quote_mint,
            evidence_count=evidence_count,
            disagreement_count=disagreement_count,
        )

    # Case C: no strong evidence. Fall back to middle + weak.
    weak_and_middle = tuple(
        r
        for r in evidence
        if r.source not in PAIR_DETECTION_SOURCES_STRONG
    )
    other_verdicts = _all_distinct_asset_verdicts(weak_and_middle)

    if len(other_verdicts) >= 2:
        return _disagree_output(
            quote_mint=quote_mint,
            evidence_count=evidence_count,
            disagreement_count=disagreement_count,
            reason=(
                PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE
            ),
        )

    if len(other_verdicts) == 1:
        chosen = next(iter(other_verdicts))
        only_middle = all(
            r.source == PAIR_DETECTION_SOURCE_MIGRATION_EVENT
            for r in weak_and_middle
            if r.quote_asset_verdict not in (
                None,
                QUOTE_ASSET_UNKNOWN,
            )
        )
        reason = (
            PAIR_DETECTION_REASON_MIGRATION_HINT_ONLY
            if only_middle
            else PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE
        )
        return _resolved_output(
            asset=chosen,
            status=PAIR_DETECTION_STATUS_PROVIDER_ONLY,
            confidence=PAIR_DETECTION_CONFIDENCE_MEDIUM,
            reason=reason,
            quote_mint=quote_mint,
            evidence_count=evidence_count,
            disagreement_count=disagreement_count,
        )

    # Case D: no usable evidence at all.
    return _unresolved_output(
        quote_mint=quote_mint,
        evidence_count=evidence_count,
        disagreement_count=disagreement_count,
        reason=PAIR_DETECTION_REASON_NO_EVIDENCE,
    )


def _strong_sources_split(
    evidence: tuple[PairDetectionEvidenceRecord, ...],
) -> bool:
    """Return ``True`` when at least one POOL_QUOTE_MINT and at least
    one BONDING_CURVE_METADATA evidence record disagree on the
    quote-asset verdict.
    """
    pool_assets: set[str] = set()
    bcv_assets: set[str] = set()
    for record in evidence:
        if (
            record.quote_asset_verdict is None
            or record.quote_asset_verdict == QUOTE_ASSET_UNKNOWN
        ):
            continue
        if record.source == PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT:
            pool_assets.add(record.quote_asset_verdict)
        elif (
            record.source
            == PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA
        ):
            bcv_assets.add(record.quote_asset_verdict)
    if not pool_assets or not bcv_assets:
        return False
    return pool_assets.isdisjoint(bcv_assets)
