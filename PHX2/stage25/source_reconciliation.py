"""Stage 25.5 source reconciliation + confidence labeling.

Pure reconciler that consumes tuples of per-source
``Stage25ATHCandidate`` records produced by the Stage 25.4 builder
and emits, per token, one ``Stage25SourceReconciliation`` plus one
``Stage25ATHMeasurement`` record.

Stage 25.5 is consolidation-only:

  * Stage 25.5 compares per-source ATH candidate rows across
    ``source_family`` for each token and labels their agreement
    honestly (AGREED / SINGLE_SOURCE / DISAGREED_MINOR /
    DISAGREED_MAJOR / AMBIGUOUS / NO_SOURCES).
  * Stage 25.5 NEVER silently picks a winner when sources
    materially conflict.
  * Stage 25.5 NEVER emits a ``MEASURED`` ATH measurement unless at
    least two contributing source families agree within the
    Stage 25-locked price / time tolerances.
  * Stage 25.5 produces the reconciliation and consolidated
    measurement records consumed by a future Stage 25.6 runner /
    artifact writer; Stage 25.5 itself ships NO runner, NO writer,
    and performs NO file I/O.

Public entry points:

  * ``group_ath_candidates_by_token`` -- bucket candidates by
                                         ``token_mint`` in a
                                         deterministic
                                         lexicographic order.
  * ``candidate_can_contribute_to_reconciled_ath``
                                      -- predicate that returns
                                         ``True`` only when a
                                         candidate may contribute
                                         evidence to a reconciled
                                         peak.
  * ``classify_candidate_set_reconciliation_status``
                                      -- map a candidate-set to one
                                         of ``RECONCILIATION_STATUSES``
                                         given the Stage 25-locked
                                         price / time tolerances.
  * ``build_source_reconciliation_for_token`` -- build one
                                                 ``Stage25SourceReconciliation``
                                                 record for a token.
  * ``build_ath_measurement_for_token`` -- build the consolidated
                                           ``Stage25ATHMeasurement``
                                           for a token given a prior
                                           reconciliation.
  * ``reconcile_ath_candidates``     -- batch entry point that
                                         groups candidates by token
                                         and emits the
                                         (reconciliation,
                                         measurement) tuples in
                                         deterministic order.

Eligibility rules (Stage 25.5 invariants -- see Stage 25
docstring):

  * A candidate can contribute to a reconciled ATH iff:
      - ``candidate_kind != INSUFFICIENT_DATA``;
      - ``peak_price`` is not ``None``;
      - ``peak_observed_at_utc`` is non-empty;
      - ``source_status`` in {``PRESENT``, ``PARTIAL``};
      - ``confidence_level`` in {``MEDIUM``, ``LOW``};
      - ``source_family`` is a known source family (not
        ``UNKNOWN_SOURCE``).
  * Non-contributing inputs are preserved in the reconciliation
    record as ``source_families`` membership and reason-code
    diagnostics; they never silently drop out of the audit trail.

Reconciliation outcomes (Stage 25.5 invariants):

  * No candidates -> ``NO_SOURCES`` / ``MISSING`` / confidence
    ``NONE`` / no reconciled peak.
  * Only non-contributing candidates ->
      - ``NO_SOURCES`` (or ``AMBIGUOUS`` if an upstream AMBIGUOUS
        source_status appears) / ``MISSING`` /
        ``UNSUPPORTED`` / ``AMBIGUOUS`` measurement /
        confidence ``NONE`` / no reconciled peak.
  * One contributing candidate -> ``SINGLE_SOURCE`` / ``PARTIAL``
    measurement / confidence ``LOW`` / no reconciled peak (Stage
    25.5 v0 refuses to promote a single source to ``MEASURED``).
  * Two-or-more contributing candidates within
    ``PRICE_DISAGREEMENT_TOLERANCE_PPM`` /
    ``PEAK_TIME_TOLERANCE_SECONDS`` -> ``AGREED`` / ``MEASURED`` /
    confidence ``HIGH`` (or ``MEDIUM`` when any contributor is
    PARTIAL/LOW) / reconciled peak selected deterministically.
  * Two-or-more contributing candidates outside the minor
    tolerance but within
    ``PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM`` /
    ``PEAK_TIME_MAJOR_TOLERANCE_SECONDS`` -> ``DISAGREED_MINOR``
    / ``PARTIAL`` measurement / confidence ``LOW`` / no reconciled
    peak.
  * Two-or-more contributing candidates exceeding the major
    threshold -> ``DISAGREED_MAJOR`` / ``SOURCE_CONFLICT``
    measurement / confidence ``NONE`` / no reconciled peak.
  * Any non-positive peak price among contributing candidates
    short-circuits to ``AMBIGUOUS`` (the parts-per-million metric
    cannot be computed safely against a ``min_price <= 0``).
  * Any candidate carrying source_status ``AMBIGUOUS`` and no
    contributors at all -> ``AMBIGUOUS`` reconciliation /
    ``AMBIGUOUS`` measurement.

Deterministic peak selection (AGREED outcomes):

  * Among contributors agreeing within tolerance, pick the
    observation with the highest ``peak_price``.
  * Ties on price -> earliest ``peak_observed_at_utc``.
  * Ties remaining -> lexicographic ``source_family``.
  * Final disambiguator -> the candidate's ``candidate_hash``.

Confidence:

  * ``HIGH`` -- AGREED with every contributor PRESENT/MEDIUM.
  * ``MEDIUM`` -- AGREED with at least one contributor
    PARTIAL/LOW.
  * ``LOW`` -- SINGLE_SOURCE or DISAGREED_MINOR.
  * ``NONE`` -- NO_SOURCES, AMBIGUOUS, or DISAGREED_MAJOR.

This module imports only stdlib (``types``, ``typing``) plus the
Stage 25 constants / errors / models. It does NOT import Stage 21
/ Stage 22 / Stage 23 / Stage 24 production modules, does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    MEASUREMENT_STATUS_UNSUPPORTED,
    PEAK_TIME_MAJOR_TOLERANCE_SECONDS,
    PEAK_TIME_TOLERANCE_SECONDS,
    PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM,
    PRICE_DISAGREEMENT_TOLERANCE_PPM,
    REASON_CODE_ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION,
    REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_MISSING_NO_SOURCES,
    REASON_CODE_ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR,
    REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE,
    REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT,
    REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED,
    REASON_CODE_ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES,
    REASON_CODE_SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE,
    REASON_CODE_SOURCE_RECONCILIATION_INSUFFICIENT_DATA,
    REASON_CODE_SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES,
    REASON_CODE_SOURCE_RECONCILIATION_NULL_PEAK_TIME,
    REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT,
    REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR,
    REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR,
    REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT,
    REASON_CODE_SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED,
    QUOTE_DENOMINATION_UNKNOWN_QUOTE,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_DISAGREED_MINOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    SOURCE_FAMILY_UNKNOWN_SOURCE,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_ATH_MEASUREMENT_VERSION,
    STAGE25_ATH_MEASURER_NAME,
    STAGE25_SOURCE_RECONCILIATION_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    Stage25ATHMeasurement,
    Stage25SourceReconciliation,
    build_ath_measurement_record,
    build_source_reconciliation_record,
)


# ---------------------------------------------------------------------------
# Internal sentinels / eligibility sets
# ---------------------------------------------------------------------------


_PEAK_SLOT_ABSENT_SENTINEL: int = -1
_PEAK_BLOCK_TIME_ABSENT_SENTINEL: int = -1


_CONTRIBUTING_SOURCE_STATUSES: frozenset[str] = frozenset(
    {SOURCE_STATUS_PRESENT, SOURCE_STATUS_PARTIAL}
)


_CONTRIBUTING_CONFIDENCE_LEVELS: frozenset[str] = frozenset(
    {CONFIDENCE_LEVEL_MEDIUM, CONFIDENCE_LEVEL_LOW}
)


_PARTIAL_LIKE_CONTRIBUTOR_STATUSES: frozenset[str] = frozenset(
    {SOURCE_STATUS_PARTIAL}
)


_PARTIAL_LIKE_CONTRIBUTOR_CONFIDENCES: frozenset[str] = frozenset(
    {CONFIDENCE_LEVEL_LOW}
)


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def candidate_can_contribute_to_reconciled_ath(
    candidate: Stage25ATHCandidate,
) -> bool:
    """Return ``True`` iff ``candidate`` may contribute to a reconciled ATH.

    Stage 25.5 contribution rules:

      * ``candidate_kind`` != ``INSUFFICIENT_DATA``;
      * ``peak_price`` is not ``None``;
      * ``peak_observed_at_utc`` is non-empty;
      * ``source_status`` is ``PRESENT`` or ``PARTIAL``;
      * ``confidence_level`` is ``MEDIUM`` or ``LOW``;
      * ``source_family`` is a known source family (not the
        ``UNKNOWN_SOURCE`` placeholder).

    The predicate is intentionally STRICTER than the per-source ATH
    candidate eligibility predicate in
    ``ath_candidate.price_window_observation_is_ath_eligible`` --
    Stage 25.5 only considers candidates with a non-NULL peak and a
    contributing first-class source_status / confidence pair.
    """
    if not isinstance(candidate, Stage25ATHCandidate):
        raise Stage25ContractError(
            "candidate_can_contribute_to_reconciled_ath: candidate "
            "must be a Stage25ATHCandidate"
        )
    if candidate.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA:
        return False
    if candidate.peak_price is None:
        return False
    if candidate.peak_observed_at_utc == "":
        return False
    if candidate.source_status not in _CONTRIBUTING_SOURCE_STATUSES:
        return False
    if candidate.confidence_level not in _CONTRIBUTING_CONFIDENCE_LEVELS:
        return False
    if candidate.source_family == SOURCE_FAMILY_UNKNOWN_SOURCE:
        return False
    return True


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _intra_group_sort_key(
    candidate: Stage25ATHCandidate,
) -> tuple[str, str]:
    """Deterministic sort key inside one token bucket.

    Ordering: source_family, candidate_hash. The trailing
    candidate_hash is the final disambiguator.
    """
    return (candidate.source_family, candidate.candidate_hash)


def group_ath_candidates_by_token(
    candidates: tuple[Stage25ATHCandidate, ...],
) -> dict[str, tuple[Stage25ATHCandidate, ...]]:
    """Group ``candidates`` by ``token_mint``.

    Returns a ``dict`` whose keys are ``token_mint`` strings sorted
    lexicographically and whose values are tuples of candidates in a
    deterministic intra-group sort order
    (``source_family`` -> ``candidate_hash``). The caller-supplied
    tuple is not mutated.
    """
    if not isinstance(candidates, tuple):
        raise Stage25ContractError(
            "group_ath_candidates_by_token: candidates must be a tuple"
        )
    buckets: dict[str, list[Stage25ATHCandidate]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Stage25ATHCandidate):
            raise Stage25ContractError(
                "group_ath_candidates_by_token: every entry must be a "
                "Stage25ATHCandidate"
            )
        buckets.setdefault(candidate.token_mint, []).append(candidate)
    grouped: dict[str, tuple[Stage25ATHCandidate, ...]] = {}
    for token in sorted(buckets.keys()):
        grouped[token] = tuple(
            sorted(buckets[token], key=_intra_group_sort_key)
        )
    return grouped


# ---------------------------------------------------------------------------
# Disagreement metrics
# ---------------------------------------------------------------------------


def _compute_price_disagreement_ppm(
    contributors: tuple[Stage25ATHCandidate, ...],
) -> Optional[int]:
    """Return integer parts-per-million spread across contributing peaks.

    Returns ``None`` when any contributor's ``peak_price`` is
    non-positive (``<= 0``) -- the parts-per-million metric is not
    well-defined and the caller treats this as an ambiguous result.
    """
    if not contributors:
        return 0
    prices: list[int] = []
    for candidate in contributors:
        price = candidate.peak_price
        if price is None or price <= 0:
            return None
        prices.append(price)
    min_price = min(prices)
    max_price = max(prices)
    return ((max_price - min_price) * 1_000_000) // min_price


def _compute_peak_time_disagreement_seconds(
    contributors: tuple[Stage25ATHCandidate, ...],
) -> Optional[int]:
    """Return integer second-spread across contributing peak block times.

    Returns ``None`` when any contributor's ``peak_block_time`` is
    the absent sentinel (``-1``) -- the time-disagreement metric is
    not well-defined and the caller treats this as an ambiguous
    result.
    """
    if not contributors:
        return 0
    block_times: list[int] = []
    for candidate in contributors:
        if candidate.peak_block_time < 0:
            return None
        block_times.append(candidate.peak_block_time)
    return max(block_times) - min(block_times)


# ---------------------------------------------------------------------------
# Reconciliation status classification
# ---------------------------------------------------------------------------


def _has_ambiguous_candidate(
    candidates: tuple[Stage25ATHCandidate, ...],
) -> bool:
    """Return ``True`` iff any candidate carries ambiguous evidence.

    Stage 25.5 honesty invariant: an ``AMBIGUOUS`` source_status on
    even a single candidate POISONS the entire token-level
    reconciliation. The reconciler may NOT silently ignore an
    ambiguous candidate just because other sources happen to agree
    -- ambiguity on one source is itself evidence the token's ATH
    cannot be measured honestly.

    Ambiguity is detected via the ``SOURCE_STATUS_AMBIGUOUS`` token
    on any candidate (contributing or not), regardless of
    candidate_kind.
    """
    return any(
        c.source_status == SOURCE_STATUS_AMBIGUOUS for c in candidates
    )


def _select_per_source_best_contributor(
    candidates: tuple[Stage25ATHCandidate, ...],
) -> tuple[Stage25ATHCandidate, ...]:
    """Reduce ``candidates`` to one deterministic contributor per source.

    Filters to candidates that pass
    ``candidate_can_contribute_to_reconciled_ath`` and then collapses
    multiple rows from the same ``source_family`` to a single
    deterministic best candidate. Selection within one source uses:

      1. highest ``peak_price``;
      2. earliest ``peak_observed_at_utc``;
      3. ``candidate_hash`` (final disambiguator).

    The result is sorted by ``source_family`` so the cross-source
    reconciliation is deterministic across input orderings. Two
    candidates from the same source family therefore NEVER produce
    a multi-source AGREED -- the cross-source view sees at most one
    contributor per source family.
    """
    by_source: dict[str, list[Stage25ATHCandidate]] = {}
    for candidate in candidates:
        if not candidate_can_contribute_to_reconciled_ath(candidate):
            continue
        by_source.setdefault(candidate.source_family, []).append(candidate)
    chosen: list[Stage25ATHCandidate] = []
    for source_family in sorted(by_source.keys()):
        bucket = by_source[source_family]
        chosen.append(min(bucket, key=_peak_select_key))
    return tuple(chosen)


def classify_candidate_set_reconciliation_status(
    candidates: tuple[Stage25ATHCandidate, ...],
    *,
    price_disagreement_tolerance_ppm: int = PRICE_DISAGREEMENT_TOLERANCE_PPM,
    peak_time_tolerance_seconds: int = PEAK_TIME_TOLERANCE_SECONDS,
    price_disagreement_major_tolerance_ppm: int = (
        PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM
    ),
    peak_time_major_tolerance_seconds: int = (
        PEAK_TIME_MAJOR_TOLERANCE_SECONDS
    ),
) -> str:
    """Return the ``RECONCILIATION_STATUSES`` token for ``candidates``.

    Stage 25.5 invariants enforced here:

      * Empty input -> ``NO_SOURCES``.
      * ANY candidate with ``source_status == AMBIGUOUS`` poisons
        the reconciliation -> ``AMBIGUOUS``. This applies even when
        other contributors agree; ambiguity on one source is
        evidence the token's ATH cannot be measured honestly.
      * No distinct contributing source families -> ``NO_SOURCES``.
      * One distinct contributing source family -> ``SINGLE_SOURCE``
        (even when two candidate rows from the same source are
        present; cross-source reconciliation is based on DISTINCT
        source families, not candidate rows).
      * Two-or-more distinct contributing source families:
          - any non-positive ``peak_price`` -> ``AMBIGUOUS``.
          - any absent ``peak_block_time`` -> ``AMBIGUOUS``.
          - price ppm or time spread above the MAJOR threshold ->
            ``DISAGREED_MAJOR``.
          - price ppm or time spread above the MINOR tolerance ->
            ``DISAGREED_MINOR``.
          - otherwise -> ``AGREED``.
    """
    if not candidates:
        return RECONCILIATION_STATUS_NO_SOURCES
    if _has_ambiguous_candidate(candidates):
        return RECONCILIATION_STATUS_AMBIGUOUS
    contributors = _select_per_source_best_contributor(candidates)
    if not contributors:
        return RECONCILIATION_STATUS_NO_SOURCES
    if len(contributors) == 1:
        return RECONCILIATION_STATUS_SINGLE_SOURCE
    price_ppm = _compute_price_disagreement_ppm(contributors)
    if price_ppm is None:
        return RECONCILIATION_STATUS_AMBIGUOUS
    time_spread = _compute_peak_time_disagreement_seconds(contributors)
    if time_spread is None:
        return RECONCILIATION_STATUS_AMBIGUOUS
    if (
        price_ppm > price_disagreement_major_tolerance_ppm
        or time_spread > peak_time_major_tolerance_seconds
    ):
        return RECONCILIATION_STATUS_DISAGREED_MAJOR
    if (
        price_ppm > price_disagreement_tolerance_ppm
        or time_spread > peak_time_tolerance_seconds
    ):
        return RECONCILIATION_STATUS_DISAGREED_MINOR
    return RECONCILIATION_STATUS_AGREED


# ---------------------------------------------------------------------------
# Deterministic peak selection
# ---------------------------------------------------------------------------


def _peak_select_key(
    candidate: Stage25ATHCandidate,
) -> tuple[int, str, str, str]:
    """Return the deterministic peak-selection key.

    Sort key: ``(-peak_price, peak_observed_at_utc, source_family,
    candidate_hash)``. The negated price ensures the maximum price
    sorts first under ``min``; ties on price prefer earliest
    ``peak_observed_at_utc`` then ``source_family`` lexicographically
    then the deterministic ``candidate_hash``.

    Callers MUST filter to contributors before invoking this key --
    the helper raises if invoked with a ``None`` peak_price so a
    missing-peak candidate can never win.
    """
    price = candidate.peak_price
    if price is None:
        raise Stage25ContractError(
            "_peak_select_key: refusing to derive a peak key for a "
            "candidate with peak_price=None"
        )
    return (
        -price,
        candidate.peak_observed_at_utc,
        candidate.source_family,
        candidate.candidate_hash,
    )


def _select_peak_candidate(
    contributors: tuple[Stage25ATHCandidate, ...],
) -> Stage25ATHCandidate:
    """Pick the deterministic peak contributor.

    Caller guarantees ``contributors`` is non-empty and every entry
    has a non-``None`` ``peak_price``.
    """
    return min(contributors, key=_peak_select_key)


# ---------------------------------------------------------------------------
# Confidence resolution
# ---------------------------------------------------------------------------


def _confidence_for_reconciliation(
    reconciliation_status: str,
    contributors: tuple[Stage25ATHCandidate, ...],
) -> str:
    """Return the ``CONFIDENCE_LEVELS`` token for a reconciliation outcome.

    Mirrors the Stage 25.5 confidence table:

      * AGREED -> HIGH if every contributor is PRESENT/MEDIUM,
                  MEDIUM if any contributor is PARTIAL/LOW.
      * SINGLE_SOURCE -> LOW.
      * DISAGREED_MINOR -> LOW.
      * DISAGREED_MAJOR / AMBIGUOUS / NO_SOURCES -> NONE.
    """
    if reconciliation_status == RECONCILIATION_STATUS_AGREED:
        for candidate in contributors:
            if (
                candidate.source_status in _PARTIAL_LIKE_CONTRIBUTOR_STATUSES
                or candidate.confidence_level
                in _PARTIAL_LIKE_CONTRIBUTOR_CONFIDENCES
            ):
                return CONFIDENCE_LEVEL_MEDIUM
        return CONFIDENCE_LEVEL_HIGH
    if reconciliation_status == RECONCILIATION_STATUS_SINGLE_SOURCE:
        return CONFIDENCE_LEVEL_LOW
    if reconciliation_status == RECONCILIATION_STATUS_DISAGREED_MINOR:
        return CONFIDENCE_LEVEL_LOW
    return CONFIDENCE_LEVEL_NONE


# ---------------------------------------------------------------------------
# Disagreement-metric mapping assembly
# ---------------------------------------------------------------------------


def _disagreement_metric_mapping(
    contributors: tuple[Stage25ATHCandidate, ...],
) -> Mapping[str, object]:
    """Build the canonical ``disagreement_metric`` mapping.

    Keys:

      * ``price_disagreement_ppm`` -- integer parts-per-million spread
        across contributing peak prices, or ``-1`` when undefined.
      * ``peak_time_disagreement_seconds`` -- integer second-spread
        across contributing peak block times, or ``-1`` when undefined.
      * ``contributor_count`` -- number of contributing candidates.

    A value of ``-1`` for either spread is the deterministic
    "undefined" sentinel; callers consume the same sentinel when
    interpreting the metric.
    """
    price_ppm = _compute_price_disagreement_ppm(contributors)
    time_spread = _compute_peak_time_disagreement_seconds(contributors)
    return _frozen_mapping(
        {
            "price_disagreement_ppm": (
                price_ppm if price_ppm is not None else -1
            ),
            "peak_time_disagreement_seconds": (
                time_spread if time_spread is not None else -1
            ),
            "contributor_count": len(contributors),
        }
    )


# ---------------------------------------------------------------------------
# Reason-code assembly
# ---------------------------------------------------------------------------


def _reconciliation_reason_codes(
    reconciliation_status: str,
    candidates: tuple[Stage25ATHCandidate, ...],
    contributors: tuple[Stage25ATHCandidate, ...],
    *,
    token_mismatch_observed: bool,
) -> tuple[str, ...]:
    """Assemble the reason-codes tuple for a reconciliation record."""
    codes: list[str] = []
    if reconciliation_status == RECONCILIATION_STATUS_NO_SOURCES:
        if not candidates:
            _append_unique(
                codes, REASON_CODE_SOURCE_RECONCILIATION_NO_CANDIDATES
            )
        else:
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_NO_CONTRIBUTING_CANDIDATES,
            )
    elif reconciliation_status == RECONCILIATION_STATUS_AMBIGUOUS:
        if any(
            c.source_status == SOURCE_STATUS_AMBIGUOUS for c in candidates
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_AMBIGUOUS_CANDIDATE,
            )
        if any(
            c.peak_price is not None and c.peak_price <= 0
            for c in contributors
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_NON_POSITIVE_PEAK_PRICE,
            )
        if any(c.peak_block_time < 0 for c in contributors):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_NULL_PEAK_TIME,
            )
    elif reconciliation_status == RECONCILIATION_STATUS_SINGLE_SOURCE:
        _append_unique(
            codes, REASON_CODE_SOURCE_RECONCILIATION_SINGLE_SOURCE_PARTIAL
        )
    elif reconciliation_status == RECONCILIATION_STATUS_AGREED:
        _append_unique(
            codes, REASON_CODE_SOURCE_RECONCILIATION_SOURCES_AGREED
        )
    elif reconciliation_status == RECONCILIATION_STATUS_DISAGREED_MINOR:
        _append_unique(
            codes,
            REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MINOR,
        )
        price_ppm = _compute_price_disagreement_ppm(contributors)
        time_spread = _compute_peak_time_disagreement_seconds(contributors)
        if price_ppm is not None and (
            price_ppm > PRICE_DISAGREEMENT_TOLERANCE_PPM
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT,
            )
        if time_spread is not None and (
            time_spread > PEAK_TIME_TOLERANCE_SECONDS
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT,
            )
    elif reconciliation_status == RECONCILIATION_STATUS_DISAGREED_MAJOR:
        _append_unique(
            codes,
            REASON_CODE_SOURCE_RECONCILIATION_SOURCES_DISAGREED_MAJOR,
        )
        price_ppm = _compute_price_disagreement_ppm(contributors)
        time_spread = _compute_peak_time_disagreement_seconds(contributors)
        if price_ppm is not None and (
            price_ppm > PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_PRICE_DISAGREEMENT,
            )
        if time_spread is not None and (
            time_spread > PEAK_TIME_MAJOR_TOLERANCE_SECONDS
        ):
            _append_unique(
                codes,
                REASON_CODE_SOURCE_RECONCILIATION_TIME_DISAGREEMENT,
            )

    if any(
        c.candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
        for c in candidates
    ):
        _append_unique(
            codes, REASON_CODE_SOURCE_RECONCILIATION_INSUFFICIENT_DATA
        )
    if any(
        c.source_family == SOURCE_FAMILY_UNKNOWN_SOURCE for c in candidates
    ):
        _append_unique(
            codes,
            REASON_CODE_SOURCE_RECONCILIATION_UNKNOWN_SOURCE_EXCLUDED,
        )
    if token_mismatch_observed:
        _append_unique(
            codes, REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED
        )
    return tuple(codes)


def _ath_measurement_reason_codes(
    measurement_status: str,
    reconciliation: Stage25SourceReconciliation,
    *,
    token_mismatch_observed: bool,
) -> tuple[str, ...]:
    """Assemble the reason-codes tuple for the consolidated measurement."""
    codes: list[str] = []
    if measurement_status == MEASUREMENT_STATUS_MEASURED:
        _append_unique(
            codes,
            REASON_CODE_ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES,
        )
    elif measurement_status == MEASUREMENT_STATUS_PARTIAL:
        if (
            reconciliation.reconciliation_status
            == RECONCILIATION_STATUS_DISAGREED_MINOR
        ):
            _append_unique(
                codes,
                REASON_CODE_ATH_MEASUREMENT_PARTIAL_DISAGREED_MINOR,
            )
        else:
            _append_unique(
                codes, REASON_CODE_ATH_MEASUREMENT_PARTIAL_SINGLE_SOURCE
            )
    elif measurement_status == MEASUREMENT_STATUS_SOURCE_CONFLICT:
        _append_unique(codes, REASON_CODE_ATH_MEASUREMENT_SOURCE_CONFLICT)
    elif measurement_status == MEASUREMENT_STATUS_MISSING:
        _append_unique(
            codes, REASON_CODE_ATH_MEASUREMENT_MISSING_NO_SOURCES
        )
    elif measurement_status == MEASUREMENT_STATUS_UNSUPPORTED:
        _append_unique(
            codes, REASON_CODE_ATH_MEASUREMENT_UNSUPPORTED_NO_SOURCES
        )
    elif measurement_status == MEASUREMENT_STATUS_AMBIGUOUS:
        _append_unique(
            codes,
            REASON_CODE_ATH_MEASUREMENT_AMBIGUOUS_RECONCILIATION,
        )

    if measurement_status != MEASUREMENT_STATUS_MEASURED:
        _append_unique(
            codes,
            REASON_CODE_ATH_MEASUREMENT_NOT_MEASURED_RECONCILIATION,
        )
    if token_mismatch_observed:
        _append_unique(
            codes, REASON_CODE_ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED
        )
    return tuple(codes)


# ---------------------------------------------------------------------------
# Disagreeing-source-count derivation
# ---------------------------------------------------------------------------


def _disagreeing_source_count(
    reconciliation_status: str,
    contributors: tuple[Stage25ATHCandidate, ...],
) -> int:
    """Return the count of contributing source families recorded as
    disagreeing on the reconciliation record.

    For AGREED outcomes every contributor is by definition in
    agreement, so the count is 0. For DISAGREED_MINOR /
    DISAGREED_MAJOR / AMBIGUOUS the count is the number of
    distinct contributing source families that participated in the
    disagreement (i.e. all contributors). For SINGLE_SOURCE /
    NO_SOURCES the count is 0.
    """
    if reconciliation_status in (
        RECONCILIATION_STATUS_AGREED,
        RECONCILIATION_STATUS_SINGLE_SOURCE,
        RECONCILIATION_STATUS_NO_SOURCES,
    ):
        return 0
    return len({c.source_family for c in contributors})


# ---------------------------------------------------------------------------
# Public per-token entry points
# ---------------------------------------------------------------------------


def _validate_token_inputs(
    token: str,
    candidates: tuple[Stage25ATHCandidate, ...],
) -> tuple[tuple[Stage25ATHCandidate, ...], bool]:
    """Validate ``token`` and ``candidates`` and drop token-mismatches.

    Returns ``(relevant_candidates, token_mismatch_observed)``.
    Candidates whose ``token_mint`` does not match ``token`` are
    excluded from the reconciliation; their presence is signaled via
    the ``token_mismatch_observed`` flag so the caller can attach the
    ``ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED`` reason code.
    """
    if not isinstance(token, str) or token == "":
        raise Stage25ContractError(
            "token must be a non-empty string"
        )
    if not isinstance(candidates, tuple):
        raise Stage25ContractError(
            "candidates must be a tuple"
        )
    for candidate in candidates:
        if not isinstance(candidate, Stage25ATHCandidate):
            raise Stage25ContractError(
                "every candidate must be a Stage25ATHCandidate"
            )
    mismatch = any(c.token_mint != token for c in candidates)
    relevant = tuple(c for c in candidates if c.token_mint == token)
    return relevant, mismatch


def _select_quote_denomination(
    candidates: tuple[Stage25ATHCandidate, ...],
) -> str:
    """Return the canonical quote denomination for ``candidates``.

    All candidates for one token are expected to share one quote
    denomination (the upstream pipeline enforces this). The helper
    tolerates an empty input by returning ``UNKNOWN_QUOTE`` so an
    empty token bucket still produces a valid record.
    """
    if not candidates:
        return QUOTE_DENOMINATION_UNKNOWN_QUOTE
    return candidates[0].quote_denomination


def build_source_reconciliation_for_token(
    token: str,
    candidates: tuple[Stage25ATHCandidate, ...],
    *,
    reconciliation_version: str = STAGE25_SOURCE_RECONCILIATION_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    price_disagreement_tolerance_ppm: int = PRICE_DISAGREEMENT_TOLERANCE_PPM,
    peak_time_tolerance_seconds: int = PEAK_TIME_TOLERANCE_SECONDS,
    price_disagreement_major_tolerance_ppm: int = (
        PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM
    ),
    peak_time_major_tolerance_seconds: int = (
        PEAK_TIME_MAJOR_TOLERANCE_SECONDS
    ),
) -> Stage25SourceReconciliation:
    """Build a single ``Stage25SourceReconciliation`` record for ``token``.

    Candidates whose ``token_mint`` does not match ``token`` are
    rejected from the reconciliation; the resulting record carries
    the ``ATH_MEASUREMENT_TOKEN_MISMATCH_REJECTED`` reason code when
    any mismatch is observed.

    The returned record is fully validated via
    ``build_source_reconciliation_record`` and carries a
    deterministic ``reconciliation_hash``.
    """
    relevant, mismatch = _validate_token_inputs(token, candidates)
    contributors = _select_per_source_best_contributor(relevant)
    status = classify_candidate_set_reconciliation_status(
        relevant,
        price_disagreement_tolerance_ppm=price_disagreement_tolerance_ppm,
        peak_time_tolerance_seconds=peak_time_tolerance_seconds,
        price_disagreement_major_tolerance_ppm=(
            price_disagreement_major_tolerance_ppm
        ),
        peak_time_major_tolerance_seconds=peak_time_major_tolerance_seconds,
    )
    confidence = _confidence_for_reconciliation(status, contributors)
    disagreement_metric = _disagreement_metric_mapping(contributors)
    source_families = tuple(sorted({c.source_family for c in relevant}))
    contributing_source_count = len(contributors)
    disagreeing_source_count = _disagreeing_source_count(status, contributors)
    reason_codes = _reconciliation_reason_codes(
        status,
        relevant,
        contributors,
        token_mismatch_observed=mismatch,
    )
    evidence = _frozen_mapping(
        {
            "reconciliation_version": reconciliation_version,
            "threshold_version": threshold_version,
            "candidate_count": len(relevant),
            "contributor_count": len(contributors),
            "candidate_hashes": sorted(c.candidate_hash for c in relevant),
            "contributor_candidate_hashes": sorted(
                c.candidate_hash for c in contributors
            ),
            "quote_denomination": _select_quote_denomination(relevant),
            "price_disagreement_tolerance_ppm": (
                price_disagreement_tolerance_ppm
            ),
            "peak_time_tolerance_seconds": peak_time_tolerance_seconds,
            "price_disagreement_major_tolerance_ppm": (
                price_disagreement_major_tolerance_ppm
            ),
            "peak_time_major_tolerance_seconds": (
                peak_time_major_tolerance_seconds
            ),
        }
    )
    return build_source_reconciliation_record(
        measurement_family=MEASUREMENT_FAMILY_ATH,
        reconciliation_status=status,
        confidence_level=confidence,
        token_mint=token,
        source_families=source_families,
        contributing_source_count=contributing_source_count,
        disagreeing_source_count=disagreeing_source_count,
        disagreement_metric=disagreement_metric,
        reason_codes=reason_codes,
        evidence=evidence,
    )


def _resolve_unmeasured_status(
    reconciliation_status: str,
    candidates: tuple[Stage25ATHCandidate, ...],
) -> str:
    """Return the ``MEASUREMENT_STATUSES`` token for an unmeasured outcome.

    Precedence:

      * AMBIGUOUS reconciliation -> ``AMBIGUOUS`` measurement.
      * DISAGREED_MAJOR -> ``SOURCE_CONFLICT``.
      * DISAGREED_MINOR -> ``PARTIAL``.
      * SINGLE_SOURCE -> ``PARTIAL``.
      * NO_SOURCES with any ``UNSUPPORTED`` source_status ->
        ``UNSUPPORTED``.
      * NO_SOURCES otherwise -> ``MISSING``.
    """
    if reconciliation_status == RECONCILIATION_STATUS_AMBIGUOUS:
        return MEASUREMENT_STATUS_AMBIGUOUS
    if reconciliation_status == RECONCILIATION_STATUS_DISAGREED_MAJOR:
        return MEASUREMENT_STATUS_SOURCE_CONFLICT
    if reconciliation_status == RECONCILIATION_STATUS_DISAGREED_MINOR:
        return MEASUREMENT_STATUS_PARTIAL
    if reconciliation_status == RECONCILIATION_STATUS_SINGLE_SOURCE:
        return MEASUREMENT_STATUS_PARTIAL
    # NO_SOURCES
    if any(c.source_status == SOURCE_STATUS_UNSUPPORTED for c in candidates):
        return MEASUREMENT_STATUS_UNSUPPORTED
    return MEASUREMENT_STATUS_MISSING


def build_ath_measurement_for_token(
    token: str,
    candidates: tuple[Stage25ATHCandidate, ...],
    reconciliation: Stage25SourceReconciliation,
    *,
    measurement_version: str = STAGE25_ATH_MEASUREMENT_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    measurer_name: str = STAGE25_ATH_MEASURER_NAME,
) -> Stage25ATHMeasurement:
    """Build the consolidated ``Stage25ATHMeasurement`` for ``token``.

    The supplied ``reconciliation`` MUST be the reconciliation record
    produced for the same token; a token mismatch raises
    ``Stage25ContractError``.

    Stage 25.5 ``MEASURED`` invariants enforced here:

      * Only ``reconciliation.reconciliation_status == AGREED``
        produces a ``MEASURED`` measurement.
      * Every other reconciliation status maps to an unmeasured
        measurement (``PARTIAL`` / ``SOURCE_CONFLICT`` /
        ``AMBIGUOUS`` / ``MISSING`` / ``UNSUPPORTED``).
    """
    if not isinstance(reconciliation, Stage25SourceReconciliation):
        raise Stage25ContractError(
            "build_ath_measurement_for_token: reconciliation must be a "
            "Stage25SourceReconciliation"
        )
    if reconciliation.token_mint != token:
        raise Stage25ContractError(
            "build_ath_measurement_for_token: reconciliation token_mint "
            "does not match the requested token"
        )
    relevant, mismatch = _validate_token_inputs(token, candidates)
    contributors = _select_per_source_best_contributor(relevant)
    status = reconciliation.reconciliation_status

    numeric_features = _frozen_mapping(
        {
            "candidate_count": len(relevant),
            "contributor_count": len(contributors),
            "contributing_source_count": (
                reconciliation.contributing_source_count
            ),
            "disagreeing_source_count": (
                reconciliation.disagreeing_source_count
            ),
        }
    )
    evidence = _frozen_mapping(
        {
            "measurement_version": measurement_version,
            "threshold_version": threshold_version,
            "reconciliation_hash": reconciliation.reconciliation_hash,
            "candidate_hashes": sorted(c.candidate_hash for c in relevant),
            "contributor_candidate_hashes": sorted(
                c.candidate_hash for c in contributors
            ),
            "quote_denomination": _select_quote_denomination(relevant),
        }
    )

    if status == RECONCILIATION_STATUS_AGREED:
        peak = _select_peak_candidate(contributors)
        measurement_status = MEASUREMENT_STATUS_MEASURED
        confidence = _confidence_for_reconciliation(status, contributors)
        reason_codes = _ath_measurement_reason_codes(
            measurement_status,
            reconciliation,
            token_mismatch_observed=mismatch,
        )
        return build_ath_measurement_record(
            measurement_status=measurement_status,
            confidence_level=confidence,
            reconciliation_status=status,
            token_mint=token,
            schema_version=schema_version,
            threshold_version=threshold_version,
            measurer_name=measurer_name,
            measurer_version=measurement_version,
            consolidated_peak_slot=peak.peak_slot,
            consolidated_peak_block_time=peak.peak_block_time,
            consolidated_peak_price=peak.peak_price,
            quote_denomination=peak.quote_denomination,
            peak_source_family=peak.source_family,
            reconciled_peak_observed_at_utc=peak.peak_observed_at_utc,
            time_to_peak_seconds=None,
            contributing_source_count=(
                reconciliation.contributing_source_count
            ),
            reason_codes=reason_codes,
            numeric_features=numeric_features,
            evidence=evidence,
            input_missing_fields=(),
        )

    measurement_status = _resolve_unmeasured_status(status, relevant)
    confidence = _confidence_for_reconciliation(status, contributors)
    reason_codes = _ath_measurement_reason_codes(
        measurement_status,
        reconciliation,
        token_mismatch_observed=mismatch,
    )
    return build_ath_measurement_record(
        measurement_status=measurement_status,
        confidence_level=confidence,
        reconciliation_status=status,
        token_mint=token,
        schema_version=schema_version,
        threshold_version=threshold_version,
        measurer_name=measurer_name,
        measurer_version=measurement_version,
        consolidated_peak_slot=_PEAK_SLOT_ABSENT_SENTINEL,
        consolidated_peak_block_time=_PEAK_BLOCK_TIME_ABSENT_SENTINEL,
        consolidated_peak_price=None,
        quote_denomination=_select_quote_denomination(relevant),
        peak_source_family="",
        reconciled_peak_observed_at_utc="",
        time_to_peak_seconds=None,
        contributing_source_count=reconciliation.contributing_source_count,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=(),
    )


# ---------------------------------------------------------------------------
# Top-level batch reconciler
# ---------------------------------------------------------------------------


def reconcile_ath_candidates(
    candidates: tuple[Stage25ATHCandidate, ...],
    *,
    reconciliation_version: str = STAGE25_SOURCE_RECONCILIATION_VERSION,
    measurement_version: str = STAGE25_ATH_MEASUREMENT_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    measurer_name: str = STAGE25_ATH_MEASURER_NAME,
    price_disagreement_tolerance_ppm: int = PRICE_DISAGREEMENT_TOLERANCE_PPM,
    peak_time_tolerance_seconds: int = PEAK_TIME_TOLERANCE_SECONDS,
    price_disagreement_major_tolerance_ppm: int = (
        PRICE_DISAGREEMENT_MAJOR_TOLERANCE_PPM
    ),
    peak_time_major_tolerance_seconds: int = (
        PEAK_TIME_MAJOR_TOLERANCE_SECONDS
    ),
) -> tuple[
    tuple[Stage25SourceReconciliation, ...],
    tuple[Stage25ATHMeasurement, ...],
]:
    """Group candidates by token and emit (reconciliation, measurement) pairs.

    Output ordering is deterministic: token mints sorted
    lexicographically. The caller-supplied tuple is not mutated.

    Empty input returns ``((), ())``.
    """
    if not isinstance(candidates, tuple):
        raise Stage25ContractError(
            "reconcile_ath_candidates: candidates must be a tuple"
        )
    grouped = group_ath_candidates_by_token(candidates)
    reconciliations: list[Stage25SourceReconciliation] = []
    measurements: list[Stage25ATHMeasurement] = []
    for token in sorted(grouped.keys()):
        bucket = grouped[token]
        reconciliation = build_source_reconciliation_for_token(
            token,
            bucket,
            reconciliation_version=reconciliation_version,
            threshold_version=threshold_version,
            price_disagreement_tolerance_ppm=(
                price_disagreement_tolerance_ppm
            ),
            peak_time_tolerance_seconds=peak_time_tolerance_seconds,
            price_disagreement_major_tolerance_ppm=(
                price_disagreement_major_tolerance_ppm
            ),
            peak_time_major_tolerance_seconds=(
                peak_time_major_tolerance_seconds
            ),
        )
        measurement = build_ath_measurement_for_token(
            token,
            bucket,
            reconciliation,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )
        reconciliations.append(reconciliation)
        measurements.append(measurement)
    return tuple(reconciliations), tuple(measurements)


__all__ = [
    "build_ath_measurement_for_token",
    "build_source_reconciliation_for_token",
    "candidate_can_contribute_to_reconciled_ath",
    "classify_candidate_set_reconciliation_status",
    "group_ath_candidates_by_token",
    "reconcile_ath_candidates",
]
