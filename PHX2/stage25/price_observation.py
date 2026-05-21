"""Stage 25.3 price observation helpers.

Pure helpers operating on tuples of ``Stage25PriceObservation``
records produced by the Stage 25.1 input reader. The helpers are
deterministic and side-effect-free: they consume immutable
``NamedTuple`` records, return new immutable records / containers,
and never mutate caller-supplied inputs.

Functions:

  * ``normalize_price_observations``         -- canonicalize the order
                                               of an observation tuple
                                               so two equivalent input
                                               tuples produce
                                               byte-identical outputs.
  * ``group_price_observations_by_token``    -- group observations by
                                               ``token_mint`` with
                                               deterministic intra-
                                               group order.
  * ``group_price_observations_by_token_and_source``
                                            -- group observations by
                                               ``(token_mint,
                                               source_family)`` with
                                               deterministic intra-
                                               group order.
  * ``dedupe_price_observations``            -- collapse exact-duplicate
                                               observations sharing the
                                               same dedupe key.
  * ``classify_price_observation``           -- annotate an observation
                                               with diagnostic reason
                                               codes describing the
                                               classification (missing
                                               price, zero-price
                                               explicit, non-
                                               contributing source
                                               status).
  * ``price_observation_can_contribute_to_window``
                                            -- predicate that returns
                                               ``True`` only when the
                                               observation can later
                                               contribute to a measured
                                               price window.

Design notes:

  * The helpers are pure functions. They make no network calls, read
    no environment variables, open no sockets, write to no disk
    location, and import no Stage 21 / Stage 22 / Stage 23 / Stage 24
    production code.
  * Dedupe is EXACT and hash-bound. The dedupe key is the
    deterministic tuple
    ``(token_mint, source_family, observed_at_utc, _price_key(price),
    quote_denomination, source_status, observation_hash)``. The
    trailing ``observation_hash`` axis binds the full canonical
    observation body, so two observations that share token / source /
    timestamp / price / status but differ on any other field
    (``slot``, ``block_time``, ``provider_id``, ``reason_codes``,
    ``evidence``, ``input_missing_fields``) have distinct hashes and
    therefore DO NOT collapse. Only byte-identical observations
    collapse. This is deliberate: silently dropping a window-distinct
    observation (e.g. one whose ``block_time`` straddles the
    consolidated migration boundary) before window classification
    could corrupt migration-relative price windows downstream.
  * ``classify_price_observation`` rebuilds the observation through
    ``build_price_observation`` so the derived ``observation_hash``
    reflects the annotated ``reason_codes`` tuple. Callers that need
    to associate a classified observation with the original record
    can compare the original hash against the classified hash to
    detect the annotation.

This module imports only stdlib (``typing``) plus the Stage 25
constants / errors / models. It does NOT import Stage 21 /
Stage 22 / Stage 23 / Stage 24 production modules, does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage25.constants import (
    REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS,
    REASON_CODE_PRICE_OBSERVATION_NO_PRICE,
    REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25PriceObservation,
    build_price_observation,
)


# ---------------------------------------------------------------------------
# Source-status classification
# ---------------------------------------------------------------------------


_ContributingStatuses: frozenset[str] = frozenset(
    {
        SOURCE_STATUS_PRESENT,
        SOURCE_STATUS_PARTIAL,
    }
)


_NonContributingStatuses: frozenset[str] = frozenset(
    {
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_UNSUPPORTED,
        SOURCE_STATUS_AMBIGUOUS,
    }
)


# ---------------------------------------------------------------------------
# Dedupe / sort keys
# ---------------------------------------------------------------------------


def _price_key(price: Optional[int]) -> tuple[int, int]:
    """Return a deterministic tuple key for an ``Optional[int]`` price.

    ``None`` is encoded as ``(0, 0)``; a non-None ``int`` is encoded
    as ``(1, value)``. Using a fixed-shape tuple makes the dedupe
    key sortable / hashable without resorting to runtime ``Optional``
    coercion.
    """
    if price is None:
        return (0, 0)
    return (1, price)


def _dedupe_key(
    observation: Stage25PriceObservation,
) -> tuple[str, str, str, tuple[int, int], str, str, str]:
    """Return the deterministic dedupe tuple for ``observation``.

    Dedupe is EXACT and hash-bound: the tuple's trailing axis is the
    observation's deterministic ``observation_hash``, which binds the
    full canonical record body (including ``slot``, ``block_time``,
    ``provider_id``, ``reason_codes``, ``evidence``, and
    ``input_missing_fields``).

    Two observations sharing the same tuple are byte-identical
    duplicates and collapse to one record; observations that match on
    token / source / timestamp / price / status but differ on any
    other field have distinct ``observation_hash`` values and
    therefore remain as distinct rows. The leading axes are retained
    even though ``observation_hash`` alone would discriminate, so the
    dedupe key sorts and clusters by the natural observation identity
    before the hash tie-break.
    """
    return (
        observation.token_mint,
        observation.source_family,
        observation.observed_at_utc,
        _price_key(observation.price),
        observation.quote_denomination,
        observation.source_status,
        observation.observation_hash,
    )


def _sort_key(
    observation: Stage25PriceObservation,
) -> tuple[str, str, str, int, int, tuple[int, int], str, str, str]:
    """Return the deterministic sort tuple for ``observation``.

    Ordering: token, source_family, observed_at_utc, block_time,
    slot, price-key, quote_denomination, source_status, hash.
    The trailing ``observation_hash`` is the final disambiguator
    so two observations identical on every other axis still produce
    a stable deterministic order via their canonical-JSON hash.
    """
    return (
        observation.token_mint,
        observation.source_family,
        observation.observed_at_utc,
        observation.block_time,
        observation.slot,
        _price_key(observation.price),
        observation.quote_denomination,
        observation.source_status,
        observation.observation_hash,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalize_price_observations(
    observations: tuple[Stage25PriceObservation, ...],
) -> tuple[Stage25PriceObservation, ...]:
    """Return ``observations`` in deterministic canonical order.

    The original tuple is not mutated. The returned tuple has the
    same length as the input.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "normalize_price_observations: observations must be a tuple"
        )
    return tuple(sorted(observations, key=_sort_key))


def group_price_observations_by_token(
    observations: tuple[Stage25PriceObservation, ...],
) -> dict[str, tuple[Stage25PriceObservation, ...]]:
    """Group ``observations`` by ``token_mint`` with deterministic order.

    Returns a ``dict`` whose keys are token mints sorted lexicographically
    and whose values are tuples of observations in the deterministic
    sort order. The caller-supplied tuple is not mutated.

    An empty input tuple returns an empty dict.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "group_price_observations_by_token: observations must be a tuple"
        )
    buckets: dict[str, list[Stage25PriceObservation]] = {}
    for observation in observations:
        buckets.setdefault(observation.token_mint, []).append(observation)
    grouped: dict[str, tuple[Stage25PriceObservation, ...]] = {}
    for token in sorted(buckets.keys()):
        grouped[token] = tuple(sorted(buckets[token], key=_sort_key))
    return grouped


def group_price_observations_by_token_and_source(
    observations: tuple[Stage25PriceObservation, ...],
) -> dict[tuple[str, str], tuple[Stage25PriceObservation, ...]]:
    """Group ``observations`` by ``(token_mint, source_family)``.

    Returns a ``dict`` whose keys are ``(token_mint, source_family)``
    pairs sorted lexicographically and whose values are tuples of
    observations in the deterministic sort order. The caller-supplied
    tuple is not mutated.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "group_price_observations_by_token_and_source: observations "
            "must be a tuple"
        )
    buckets: dict[tuple[str, str], list[Stage25PriceObservation]] = {}
    for observation in observations:
        key = (observation.token_mint, observation.source_family)
        buckets.setdefault(key, []).append(observation)
    grouped: dict[
        tuple[str, str], tuple[Stage25PriceObservation, ...]
    ] = {}
    for key in sorted(buckets.keys()):
        grouped[key] = tuple(sorted(buckets[key], key=_sort_key))
    return grouped


def dedupe_price_observations(
    observations: tuple[Stage25PriceObservation, ...],
) -> tuple[Stage25PriceObservation, ...]:
    """Collapse exact-duplicate observations sharing the dedupe key.

    Dedupe is EXACT and hash-bound. The dedupe key is the tuple
    ``(token_mint, source_family, observed_at_utc, _price_key(price),
    quote_denomination, source_status, observation_hash)``. The
    trailing ``observation_hash`` axis binds the full canonical
    observation body, so:

      * byte-identical observations collapse to one record;
      * observations that share token / source / timestamp / price /
        status but differ on ``slot``, ``block_time``, ``provider_id``,
        ``reason_codes``, ``evidence``, or ``input_missing_fields``
        have distinct ``observation_hash`` values and DO NOT collapse.

    This is deliberate: a same-timestamp / same-price pair whose
    ``block_time`` straddles the consolidated migration boundary
    must remain distinct so window classification stays honest. The
    helper intentionally does NOT implement fuzzy price dedupe or
    source-only collapse.

    The caller-supplied tuple is not mutated. Output ordering is the
    deterministic canonical sort order so two equivalent input tuples
    produce byte-identical outputs.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "dedupe_price_observations: observations must be a tuple"
        )
    seen: set[tuple[str, str, str, tuple[int, int], str, str, str]] = set()
    keepers: list[Stage25PriceObservation] = []
    for observation in sorted(observations, key=_sort_key):
        key = _dedupe_key(observation)
        if key in seen:
            continue
        seen.add(key)
        keepers.append(observation)
    return tuple(keepers)


def classify_price_observation(
    observation: Stage25PriceObservation,
) -> Stage25PriceObservation:
    """Annotate ``observation`` with diagnostic reason codes.

    Returns a NEW ``Stage25PriceObservation`` whose ``reason_codes``
    tuple carries diagnostic markers for any of:

      * source_status is one of ``ABSENT`` / ``MALFORMED`` /
        ``DECODE_FAILED`` / ``UNSUPPORTED`` / ``AMBIGUOUS`` --
        annotated with ``PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS``.
      * ``price`` is ``None`` -- annotated with
        ``PRICE_OBSERVATION_NO_PRICE``.
      * ``price`` is ``0`` and the original record already carries
        the explicit ``PRICE_OBSERVED_ZERO`` reason -- annotated with
        ``PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT``.

    Codes already present on the input observation are not duplicated.
    When no diagnostic codes apply, the original observation is
    returned unchanged.

    The input observation is never mutated. The returned record is
    rebuilt through ``build_price_observation`` so its
    ``observation_hash`` reflects the annotated ``reason_codes`` tuple.
    """
    extra_codes: list[str] = []
    if observation.source_status in _NonContributingStatuses:
        extra_codes.append(
            REASON_CODE_PRICE_OBSERVATION_NON_CONTRIBUTING_STATUS
        )
    if observation.price is None:
        extra_codes.append(REASON_CODE_PRICE_OBSERVATION_NO_PRICE)
    if (
        observation.price == 0
        and REASON_CODE_PRICE_OBSERVED_ZERO in observation.reason_codes
    ):
        extra_codes.append(
            REASON_CODE_PRICE_OBSERVATION_ZERO_PRICE_EXPLICIT
        )

    if not extra_codes:
        return observation

    existing = list(observation.reason_codes)
    seen: set[str] = set(existing)
    for code in extra_codes:
        if code in seen:
            continue
        seen.add(code)
        existing.append(code)

    if tuple(existing) == observation.reason_codes:
        return observation

    return build_price_observation(
        token_mint=observation.token_mint,
        source_family=observation.source_family,
        source_status=observation.source_status,
        observed_at_utc=observation.observed_at_utc,
        slot=observation.slot,
        block_time=observation.block_time,
        price=observation.price,
        quote_denomination=observation.quote_denomination,
        provider_id=observation.provider_id,
        reason_codes=tuple(existing),
        evidence=observation.evidence,
        input_missing_fields=observation.input_missing_fields,
    )


# ---------------------------------------------------------------------------
# Contribution predicate
# ---------------------------------------------------------------------------


def price_observation_can_contribute_to_window(
    observation: Stage25PriceObservation,
) -> bool:
    """Return ``True`` iff ``observation`` can contribute to a price window.

    A contributing observation has:

      * ``source_status`` in {``PRESENT``, ``PARTIAL``}, AND
      * ``price`` is not ``None``.

    A ``PRESENT`` observation with a non-None ``price`` is the
    canonical contributor. A ``PARTIAL`` observation with a non-None
    ``price`` is permitted to contribute (callers preserve the
    ``PARTIAL`` source_status verbatim on any window observation so
    downstream readers can detect the partial origin).

    Any ``ABSENT`` / ``MALFORMED`` / ``DECODE_FAILED`` /
    ``UNSUPPORTED`` / ``AMBIGUOUS`` observation cannot contribute;
    likewise any observation with ``price=None``.
    """
    if observation.source_status not in _ContributingStatuses:
        return False
    if observation.price is None:
        return False
    return True


def price_observation_source_status_is_non_contributing(
    observation: Stage25PriceObservation,
) -> bool:
    """Return ``True`` iff ``observation``'s source_status cannot
    contribute to a price window.
    """
    return observation.source_status in _NonContributingStatuses


__all__ = [
    "classify_price_observation",
    "dedupe_price_observations",
    "group_price_observations_by_token",
    "group_price_observations_by_token_and_source",
    "normalize_price_observations",
    "price_observation_can_contribute_to_window",
    "price_observation_source_status_is_non_contributing",
]
