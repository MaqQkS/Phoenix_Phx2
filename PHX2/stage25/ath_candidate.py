"""Stage 25.4 ATH candidate builder.

Pure helpers that convert tuples of
``Stage25PriceWindowObservation`` records produced by the Stage
25.3 projector into tuples of ``Stage25ATHCandidate`` records,
one per (token_mint, source_family) group.

Stage 25.4 is candidate-only:

  * Stage 25.4 builds per-source candidates from already-windowed,
    source-labeled price observations.
  * Stage 25.4 does NOT compare sources, reconcile disagreement,
    or emit a consolidated ATH measurement.
  * Stage 25.4 does NOT construct ``Stage25ATHMeasurement``
    records; that is Stage 25.5+ work.
  * Stage 25.4 emits one ``Stage25ATHCandidate`` per
    (token, source) group, including an
    ``INSUFFICIENT_DATA`` candidate for groups that carry no
    eligible window observation.

Public entry points:

  * ``price_window_observation_is_ath_eligible``
                                            -- predicate that
                                               returns ``True`` only
                                               when the window
                                               observation can
                                               contribute to a peak.
  * ``group_price_window_observations_by_token_and_source``
                                            -- group observations by
                                               ``(token_mint,
                                               source_family)`` with
                                               deterministic intra-
                                               group order.
  * ``select_source_peak_window_observation``
                                            -- pick the deterministic
                                               source-local peak
                                               observation from a
                                               same-(token, source)
                                               group.
  * ``build_ath_candidate_for_token_source`` -- build a single
                                               candidate for one
                                               (token, source) group.
  * ``build_ath_candidates``                -- batch entry point that
                                               groups the input tuple
                                               by (token, source) and
                                               emits one candidate per
                                               group in deterministic
                                               order.

Eligibility rules (Stage 25.4 invariants):

  * Eligible window kinds: ``POST_MIGRATION_PRIMARY`` and
    ``POST_MIGRATION_EXTENDED``. ``PRE_MIGRATION_EXCLUDED`` and
    ``UNKNOWN_WINDOW`` are ineligible -- they NEVER produce a peak.
  * Eligible source statuses: ``PRESENT`` and ``PARTIAL``. ``ABSENT``
    / ``MALFORMED`` / ``DECODE_FAILED`` / ``UNSUPPORTED`` /
    ``AMBIGUOUS`` cannot contribute and are recorded as
    non-contributing on the resulting candidate's reason_codes.
  * ``price = None`` cannot produce a peak.
  * ``price = 0`` is only selected when it is the only eligible
    observation (negative tie-break ordering keeps positive prices
    above ``0``); when selected, the candidate preserves the upstream
    ``PRICE_OBSERVED_ZERO`` reason code so the record validator
    accepts the zero peak.

Peak selection:

  * Within an eligible group the peak is the observation with the
    highest ``price`` value.
  * Ties on price are broken first by earliest ``observed_at_utc``,
    then by ``source_family`` (lexicographic), then by the
    deterministic ``observation_hash``.
  * Source-family tie-break is identity-stable within a group (all
    observations in the group share one source_family) but is
    retained on the sort key so the tuple ordering is fully
    deterministic.

Candidate kinds:

  * ``ON_CHAIN_SWAP_REPLAY`` source -> ``SWAP_REPLAY_PEAK``.
  * ``BIRDEYE`` / ``DEXSCREENER`` / ``WEBSOCKET_CAPTURE`` /
    ``UNKNOWN_SOURCE`` source -> ``SOURCE_REPORTED_PEAK``.
  * Group with no eligible observation -> ``INSUFFICIENT_DATA`` with
    ``peak_price=None`` and ``peak_observed_at_utc=""``.

Confidence:

  * ``PRESENT`` source with an eligible price -> ``MEDIUM``.
  * ``PARTIAL`` source with an eligible price -> ``LOW`` (and the
    candidate carries ``ATH_CANDIDATE_PARTIAL_SOURCE_STATUS``).
  * No eligible observation -> ``NONE``.
  * ``HIGH`` is reserved for Stage 25.5+ cross-source reconciliation;
    Stage 25.4 never emits ``HIGH``.

First-class field promotion (Stage 25.4 audit remediation):

  * ``source_status`` and ``confidence_level`` are written directly
    onto the resulting ``Stage25ATHCandidate`` record so a Stage 25.5+
    source reconciler can read them as typed first-class fields rather
    than parsing the ``evidence`` mapping. The same values are NOT
    duplicated into ``evidence`` -- the record validator binds them
    into the canonical hash, and divergence between first-class and
    evidence views is therefore impossible by construction.

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
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_THRESHOLD_VERSION,
    PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    QUOTE_DENOMINATION_UNKNOWN_QUOTE,
    REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA,
    REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS,
    REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS,
    REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK,
    REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK,
    REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED,
    REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_ATH_CANDIDATE_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    Stage25PriceWindowObservation,
    build_ath_candidate_record,
)


# ---------------------------------------------------------------------------
# Internal sentinels / eligibility sets
# ---------------------------------------------------------------------------


_PEAK_SLOT_ABSENT_SENTINEL: int = -1
_PEAK_BLOCK_TIME_ABSENT_SENTINEL: int = -1


_ATH_ELIGIBLE_WINDOW_KINDS: frozenset[str] = frozenset(
    {
        PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
        PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    }
)


_ATH_ELIGIBLE_SOURCE_STATUSES: frozenset[str] = frozenset(
    {
        SOURCE_STATUS_PRESENT,
        SOURCE_STATUS_PARTIAL,
    }
)


# Priority order (worst -> least-worst) used to pick the first-class
# ``source_status`` on an ``INSUFFICIENT_DATA`` candidate. The priority
# names the status that most-informatively explains why the (token,
# source) group could not produce a peak: an ``AMBIGUOUS`` upstream
# observation outweighs a missing one, a corrupted one outweighs an
# unsupported one, and so on. ``PRESENT`` / ``PARTIAL`` come last
# because their presence on an ineligible group implies the gap is
# window-related rather than source-status-related, but the candidate
# still has to carry one closed-set status value.


_INSUFFICIENT_SOURCE_STATUS_PRIORITY: tuple[str, ...] = (
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_UNSUPPORTED,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
)


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def price_window_observation_is_ath_eligible(
    observation: Stage25PriceWindowObservation,
) -> bool:
    """Return ``True`` iff ``observation`` may contribute to an ATH peak.

    A contributing window observation has:

      * ``window_kind`` in {``POST_MIGRATION_PRIMARY``,
        ``POST_MIGRATION_EXTENDED``};
      * ``source_status`` in {``PRESENT``, ``PARTIAL``};
      * ``price`` is not ``None``.

    Pre-migration and unknown-window observations are ineligible -- a
    pre-migration price is by spec excluded from any ATH measurement,
    and an unknown-window observation cannot be assigned a measured
    peak honestly.
    """
    if not isinstance(observation, Stage25PriceWindowObservation):
        raise Stage25ContractError(
            "price_window_observation_is_ath_eligible: observation must "
            "be a Stage25PriceWindowObservation"
        )
    if observation.window_kind not in _ATH_ELIGIBLE_WINDOW_KINDS:
        return False
    if observation.source_status not in _ATH_ELIGIBLE_SOURCE_STATUSES:
        return False
    if observation.price is None:
        return False
    return True


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _intra_group_sort_key(
    observation: Stage25PriceWindowObservation,
) -> tuple[str, int, int, str]:
    """Deterministic sort key for ordering observations within a group.

    Ordering: observed_at_utc, block_time, slot, observation_hash.
    The trailing observation_hash is the final disambiguator.
    """
    return (
        observation.observed_at_utc,
        observation.block_time,
        observation.slot,
        observation.observation_hash,
    )


def group_price_window_observations_by_token_and_source(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> dict[tuple[str, str], tuple[Stage25PriceWindowObservation, ...]]:
    """Group ``observations`` by ``(token_mint, source_family)``.

    Returns a ``dict`` whose keys are ``(token_mint, source_family)``
    pairs sorted lexicographically and whose values are tuples of
    observations in a deterministic intra-group sort order
    (``observed_at_utc`` -> ``block_time`` -> ``slot`` ->
    ``observation_hash``). The caller-supplied tuple is not mutated.

    An empty input tuple returns an empty dict.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "group_price_window_observations_by_token_and_source: "
            "observations must be a tuple"
        )
    buckets: dict[
        tuple[str, str], list[Stage25PriceWindowObservation]
    ] = {}
    for observation in observations:
        if not isinstance(observation, Stage25PriceWindowObservation):
            raise Stage25ContractError(
                "group_price_window_observations_by_token_and_source: "
                "every entry must be a Stage25PriceWindowObservation"
            )
        key = (observation.token_mint, observation.source_family)
        buckets.setdefault(key, []).append(observation)
    grouped: dict[
        tuple[str, str], tuple[Stage25PriceWindowObservation, ...]
    ] = {}
    for key in sorted(buckets.keys()):
        grouped[key] = tuple(
            sorted(buckets[key], key=_intra_group_sort_key)
        )
    return grouped


# ---------------------------------------------------------------------------
# Peak selection
# ---------------------------------------------------------------------------


def _peak_select_key(
    observation: Stage25PriceWindowObservation,
) -> tuple[int, str, str, str]:
    """Return the deterministic peak-selection key.

    Sort key: ``(-price, observed_at_utc, source_family,
    observation_hash)``. The negated price ensures the maximum
    price sorts first under ``min``; ties on price prefer earliest
    ``observed_at_utc`` then ``source_family`` lexicographically
    then the deterministic ``observation_hash``.

    Callers MUST filter out ``price is None`` before invoking this
    key -- the helper deliberately raises if it observes ``None``
    so a missing-price observation can never become a peak.
    """
    price = observation.price
    if price is None:
        raise Stage25ContractError(
            "_peak_select_key: refusing to derive a peak key for an "
            "observation with price=None"
        )
    return (
        -price,
        observation.observed_at_utc,
        observation.source_family,
        observation.observation_hash,
    )


def select_source_peak_window_observation(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> Optional[Stage25PriceWindowObservation]:
    """Return the deterministic source-local peak observation, or ``None``.

    Filters ``observations`` to the eligible subset
    (post-migration window kind, contributing source status,
    non-``None`` price) and selects the entry with the highest
    price under the deterministic
    ``_peak_select_key`` ordering. Returns ``None`` when no
    eligible observation remains.

    The caller-supplied tuple is not mutated.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "select_source_peak_window_observation: observations must "
            "be a tuple"
        )
    eligible = tuple(
        observation
        for observation in observations
        if price_window_observation_is_ath_eligible(observation)
    )
    if not eligible:
        return None
    return min(eligible, key=_peak_select_key)


# ---------------------------------------------------------------------------
# Helpers for diagnostic reason-code assembly
# ---------------------------------------------------------------------------


def _count_eligible(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> int:
    return sum(
        1
        for observation in observations
        if price_window_observation_is_ath_eligible(observation)
    )


def _has_window_kind(
    observations: tuple[Stage25PriceWindowObservation, ...],
    window_kind: str,
) -> bool:
    return any(
        observation.window_kind == window_kind
        for observation in observations
    )


def _has_null_price(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> bool:
    return any(observation.price is None for observation in observations)


def _has_non_contributing_status(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> bool:
    return any(
        observation.source_status not in _ATH_ELIGIBLE_SOURCE_STATUSES
        for observation in observations
    )


def _eligible_has_tie_on_price(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> bool:
    """Return ``True`` iff two or more eligible observations share the
    maximum eligible price (so the deterministic tie-break logic is
    load-bearing for the chosen peak).
    """
    eligible_prices: list[int] = []
    for observation in observations:
        if not price_window_observation_is_ath_eligible(observation):
            continue
        price = observation.price
        if price is None:
            continue
        eligible_prices.append(price)
    if len(eligible_prices) < 2:
        return False
    maximum = max(eligible_prices)
    return eligible_prices.count(maximum) > 1


def _candidate_kind_for_source(source_family: str) -> str:
    if source_family == SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY:
        return ATH_CANDIDATE_KIND_SWAP_REPLAY_PEAK
    return ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK


def _selected_peak_reason_code(source_family: str) -> str:
    if source_family == SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY:
        return REASON_CODE_ATH_CANDIDATE_SELECTED_SWAP_REPLAY_PEAK
    return REASON_CODE_ATH_CANDIDATE_SELECTED_SOURCE_PEAK


def _confidence_for_peak(peak: Stage25PriceWindowObservation) -> str:
    if peak.source_status == SOURCE_STATUS_PARTIAL:
        return CONFIDENCE_LEVEL_LOW
    return CONFIDENCE_LEVEL_MEDIUM


def _group_quote_denomination(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> str:
    """Return the quote denomination for the group.

    All observations in one group share a single source_family. The
    Stage 25 input pipeline guarantees a source carries a single
    quote denomination, but the helper tolerates a group with no
    observations by returning ``UNKNOWN_QUOTE`` so an empty input
    still produces a valid record.
    """
    if not observations:
        return QUOTE_DENOMINATION_UNKNOWN_QUOTE
    return observations[0].quote_denomination


def _observation_hashes_list(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> list[str]:
    return [observation.observation_hash for observation in observations]


def _resolve_insufficient_source_status(
    observations: tuple[Stage25PriceWindowObservation, ...],
) -> str:
    """Pick the most-relevant source_status for an INSUFFICIENT candidate.

    Returns ``ABSENT`` when ``observations`` is empty. Otherwise walks
    the priority order in ``_INSUFFICIENT_SOURCE_STATUS_PRIORITY`` and
    returns the first status that appears in the group; the resulting
    value names the closed-set status that most-informatively explains
    why no peak could be selected.
    """
    if not observations:
        return SOURCE_STATUS_ABSENT
    statuses = {observation.source_status for observation in observations}
    for candidate_status in _INSUFFICIENT_SOURCE_STATUS_PRIORITY:
        if candidate_status in statuses:
            return candidate_status
    # The priority tuple already enumerates every closed-set value,
    # so this fallback is defensive only.
    return observations[0].source_status


# ---------------------------------------------------------------------------
# Candidate builders (private)
# ---------------------------------------------------------------------------


def _build_insufficient_candidate(
    *,
    token: str,
    source_family: str,
    observations: tuple[Stage25PriceWindowObservation, ...],
    candidate_version: str,
    threshold_version: str,
) -> Stage25ATHCandidate:
    """Build the ``INSUFFICIENT_DATA`` candidate for a no-eligible group.

    ``source_status`` is resolved via
    ``_resolve_insufficient_source_status`` so the first-class field
    names the most-relevant closed-set status explaining the gap.
    ``confidence_level`` is locked to ``NONE``.
    """
    reason_codes: list[str] = []
    _append_unique(
        reason_codes, REASON_CODE_ATH_CANDIDATE_INSUFFICIENT_DATA
    )
    _append_unique(
        reason_codes, REASON_CODE_ATH_CANDIDATE_NO_ELIGIBLE_WINDOWS
    )
    if _has_window_kind(
        observations, PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    ):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED,
        )
    if _has_window_kind(
        observations, PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    ):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED,
        )
    if _has_null_price(observations):
        _append_unique(
            reason_codes, REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED
        )
    if _has_non_contributing_status(observations):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS,
        )
    evidence = _frozen_mapping(
        {
            "candidate_version": candidate_version,
            "threshold_version": threshold_version,
            "selected_window_kind": "",
            "selected_observation_hash": "",
            "observation_count": len(observations),
            "eligible_observation_count": 0,
            "window_observation_hashes": _observation_hashes_list(
                observations
            ),
        }
    )
    return build_ath_candidate_record(
        token_mint=token,
        source_family=source_family,
        source_status=_resolve_insufficient_source_status(observations),
        candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        peak_observed_at_utc="",
        peak_slot=_PEAK_SLOT_ABSENT_SENTINEL,
        peak_block_time=_PEAK_BLOCK_TIME_ABSENT_SENTINEL,
        peak_price=None,
        quote_denomination=_group_quote_denomination(observations),
        reason_codes=tuple(reason_codes),
        evidence=evidence,
        input_missing_fields=(),
    )


def _build_peak_candidate(
    *,
    token: str,
    source_family: str,
    peak: Stage25PriceWindowObservation,
    observations: tuple[Stage25PriceWindowObservation, ...],
    candidate_version: str,
    threshold_version: str,
) -> Stage25ATHCandidate:
    """Build a candidate carrying the deterministic source-local peak."""
    candidate_kind = _candidate_kind_for_source(source_family)
    confidence_level = _confidence_for_peak(peak)

    reason_codes: list[str] = []
    _append_unique(reason_codes, _selected_peak_reason_code(source_family))
    if peak.source_status == SOURCE_STATUS_PARTIAL:
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_PARTIAL_SOURCE_STATUS,
        )
    if _eligible_has_tie_on_price(observations):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_TIE_BREAK_EARLIEST_OBSERVED,
        )
    if _has_non_contributing_status(observations):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_NON_CONTRIBUTING_SOURCE_STATUS,
        )
    if _has_null_price(observations):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_NULL_PRICE_EXCLUDED,
        )
    if _has_window_kind(
        observations, PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    ):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_PRE_MIGRATION_EXCLUDED,
        )
    if _has_window_kind(
        observations, PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    ):
        _append_unique(
            reason_codes,
            REASON_CODE_ATH_CANDIDATE_UNKNOWN_WINDOW_EXCLUDED,
        )
    if (
        peak.price == 0
        and REASON_CODE_PRICE_OBSERVED_ZERO in peak.reason_codes
    ):
        # Preserve the upstream observed-zero invariant so the record
        # validator accepts a zero-price peak.
        _append_unique(reason_codes, REASON_CODE_PRICE_OBSERVED_ZERO)

    evidence = _frozen_mapping(
        {
            "candidate_version": candidate_version,
            "threshold_version": threshold_version,
            "selected_window_kind": peak.window_kind,
            "selected_observation_hash": peak.observation_hash,
            "observation_count": len(observations),
            "eligible_observation_count": _count_eligible(observations),
            "window_observation_hashes": _observation_hashes_list(
                observations
            ),
        }
    )
    return build_ath_candidate_record(
        token_mint=token,
        source_family=source_family,
        source_status=peak.source_status,
        candidate_kind=candidate_kind,
        confidence_level=confidence_level,
        peak_observed_at_utc=peak.observed_at_utc,
        peak_slot=peak.slot,
        peak_block_time=peak.block_time,
        peak_price=peak.price,
        quote_denomination=peak.quote_denomination,
        reason_codes=tuple(reason_codes),
        evidence=evidence,
        input_missing_fields=(),
    )


# ---------------------------------------------------------------------------
# Public per-group / batch entry points
# ---------------------------------------------------------------------------


def build_ath_candidate_for_token_source(
    token: str,
    source_family: str,
    observations: tuple[Stage25PriceWindowObservation, ...],
    *,
    candidate_version: str = STAGE25_ATH_CANDIDATE_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
) -> Stage25ATHCandidate:
    """Build a single ``Stage25ATHCandidate`` for one (token, source) group.

    All entries of ``observations`` must satisfy
    ``observation.token_mint == token`` and
    ``observation.source_family == source_family``. A mismatch
    raises ``Stage25ContractError`` -- the caller is expected to
    group by (token, source) before invoking this routine.

    Behavior:

      * When at least one observation is ATH-eligible
        (POST_MIGRATION_PRIMARY / POST_MIGRATION_EXTENDED with
        PRESENT / PARTIAL status and non-``None`` price), the
        returned candidate carries the deterministic source-local
        peak.
      * When no observation is eligible (empty group, all
        pre-migration / unknown-window, all null-price, or all
        non-contributing-status), the returned candidate is an
        ``INSUFFICIENT_DATA`` placeholder with
        ``peak_price=None`` and reason codes naming the missing
        evidence.

    Stage 25.4 NEVER produces a ``COMBINED_PEAK`` here. Combined
    peaks are reserved for Stage 25.5+ cross-source reconciliation.
    """
    if not isinstance(token, str) or token == "":
        raise Stage25ContractError(
            "build_ath_candidate_for_token_source: token must be a "
            "non-empty string"
        )
    if not isinstance(source_family, str) or source_family == "":
        raise Stage25ContractError(
            "build_ath_candidate_for_token_source: source_family must "
            "be a non-empty string"
        )
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "build_ath_candidate_for_token_source: observations must "
            "be a tuple"
        )
    for observation in observations:
        if not isinstance(observation, Stage25PriceWindowObservation):
            raise Stage25ContractError(
                "build_ath_candidate_for_token_source: every entry "
                "must be a Stage25PriceWindowObservation"
            )
        if observation.token_mint != token:
            raise Stage25ContractError(
                "build_ath_candidate_for_token_source: an observation "
                "token_mint does not match the requested token"
            )
        if observation.source_family != source_family:
            raise Stage25ContractError(
                "build_ath_candidate_for_token_source: an observation "
                "source_family does not match the requested "
                "source_family"
            )

    canonical_group = tuple(
        sorted(observations, key=_intra_group_sort_key)
    )
    peak = select_source_peak_window_observation(canonical_group)
    if peak is None:
        return _build_insufficient_candidate(
            token=token,
            source_family=source_family,
            observations=canonical_group,
            candidate_version=candidate_version,
            threshold_version=threshold_version,
        )
    return _build_peak_candidate(
        token=token,
        source_family=source_family,
        peak=peak,
        observations=canonical_group,
        candidate_version=candidate_version,
        threshold_version=threshold_version,
    )


def build_ath_candidates(
    observations: tuple[Stage25PriceWindowObservation, ...],
    *,
    candidate_version: str = STAGE25_ATH_CANDIDATE_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
) -> tuple[Stage25ATHCandidate, ...]:
    """Group ``observations`` by (token, source) and emit one candidate per group.

    Output ordering is deterministic: groups are sorted
    lexicographically by ``(token_mint, source_family)``. The
    caller-supplied tuple is never mutated.

    Empty input returns an empty tuple. A group whose observations
    are all ineligible produces an ``INSUFFICIENT_DATA`` candidate
    rather than being silently dropped, so downstream readers can
    detect the gap.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "build_ath_candidates: observations must be a tuple"
        )
    grouped = group_price_window_observations_by_token_and_source(
        observations
    )
    out: list[Stage25ATHCandidate] = []
    for (token, source_family) in sorted(grouped.keys()):
        out.append(
            build_ath_candidate_for_token_source(
                token,
                source_family,
                grouped[(token, source_family)],
                candidate_version=candidate_version,
                threshold_version=threshold_version,
            )
        )
    return tuple(out)


__all__ = [
    "build_ath_candidate_for_token_source",
    "build_ath_candidates",
    "group_price_window_observations_by_token_and_source",
    "price_window_observation_is_ath_eligible",
    "select_source_peak_window_observation",
]
