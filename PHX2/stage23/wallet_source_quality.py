"""Stage 23.4 wallet / source-quality observe-only filter.

This is the third concrete Stage 23 filter, landing under the
``WALLET_SOURCE_QUALITY`` filter family. The filter is pure:
given a ``Stage23FilterInput`` it returns a
``Stage23FilterResult`` and never touches the network, the
clock, the environment, or disk. Stage 23 is observe-only: the
filter assigns a closed-set label and a closed-set
``data_status`` plus a deterministic tuple of reason codes; it
never blocks, routes, or alerts.

This module is mostly a *surface* for wallet / source-quality
primitives. PHX2 does not (yet) carry a full wallet graph
crawler, a funding-source database, or an authoritative
provenance reference. The filter is honest about that: when a
sub-family primitive (wallet age, funding graph, provenance) is
unsupported by the upstream artifact the filter emits
``UNKNOWN`` / ``UNSUPPORTED`` and the corresponding reason code
rather than pretending to have an answer. Future Stage 25+ work
can plug in real primitives without changing this contract.

Input shape:

  * Wallet / source-quality primitives are read out of
    ``filter_input.payload_summary`` by key. The Stage 23 input
    reader already enforces the payload-summary safety rules at
    ingest, so this filter consumes the projected mapping
    verbatim.
  * Recognized primitive keys (each optional):

      ``early_wallet_count``                    -- int
      ``fresh_wallet_count``                    -- int
      ``fresh_wallet_pct``                      -- float in [0.0, 1.0]
      ``repeated_source_wallet_count``          -- int
      ``repeated_source_wallet_pct``            -- float in [0.0, 1.0]
      ``common_funder_cluster_count``           -- int
      ``largest_common_funder_cluster_pct``     -- float in [0.0, 1.0]
      ``wallet_age_known_count``                -- int
      ``wallet_age_unknown_count``              -- int
      ``wallet_age_known_pct``                  -- float in [0.0, 1.0]
      ``young_wallet_pct``                      -- float in [0.0, 1.0]
      ``mature_wallet_pct``                     -- float in [0.0, 1.0]
      ``known_bad_source_count``                -- int
      ``known_bad_source_pct``                  -- float in [0.0, 1.0]
      ``known_good_source_count``               -- int
      ``known_good_source_pct``                 -- float in [0.0, 1.0]
      ``dev_wallet_age_days``                   -- int / float, non-negative
      ``creator_wallet_age_days``               -- int / float, non-negative
      ``source_quality_known_pct``              -- float in [0.0, 1.0]

  * Optional marker keys the upstream artifact may carry to
    signal that an entire sub-family is unsupported for this
    token. Each marker is independent; any one of them being
    ``"unsupported"`` causes the filter to emit
    ``label=UNKNOWN`` / ``data_status=UNSUPPORTED`` with the
    corresponding reason code:

      ``wallet_source_primitive_kind``          -- whole-surface
                                                   unsupported marker
      ``wallet_age_primitive_kind``             -- wallet-age
                                                   sub-family marker
      ``funding_graph_primitive_kind``          -- funding-graph
                                                   sub-family marker
      ``provenance_primitive_kind``             -- provenance
                                                   sub-family marker

Output shape:

  * ``filter_name``       -- ``"wallet_source_quality"``
  * ``filter_family``     -- ``"WALLET_SOURCE_QUALITY"``
  * ``filter_version``    -- ``"wallet_source_quality_v0"``
  * ``threshold_version`` -- ``"thresholds_v0_observe_only"``
  * ``label``             -- one of ``LABELS``
  * ``data_status``       -- one of ``DATA_STATUSES``
  * ``reason_codes``      -- tuple of closed-set codes in
                             canonical declaration order
  * ``numeric_features``  -- ``MappingProxyType`` view of the
                             projected primitives the filter
                             actually consumed
  * ``missing_features``  -- sorted tuple of recognized
                             primitive keys absent from the
                             input

Threshold guidance:

  Thresholds are conservative observe-only placeholders. They
  are NOT calibrated detection values. The
  ``threshold_version`` is locked to
  ``"thresholds_v0_observe_only"`` to make the placeholder
  posture explicit on every emitted record.

This module imports only stdlib (``math`` / ``types`` /
``typing``) plus the Stage 23 constants / models / errors. It
does NOT import Stage 21 or Stage 22 modules, does NOT import
any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, contains no
top-level I/O, and writes nothing to disk. It carries no
wallet-graph crawler, no funding-source client, and makes no
authoritative provenance claim.
"""

from __future__ import annotations

import math
from types import MappingProxyType
from typing import Mapping, NamedTuple

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    FILTER_FAMILY_WALLET_SOURCE_QUALITY,
    LABEL_ELEVATED,
    LABEL_INSUFFICIENT_DATA,
    LABEL_MISSING_INPUT,
    LABEL_NORMAL,
    LABEL_SCAM_LIKELY,
    LABEL_SUSPICIOUS,
    LABEL_UNKNOWN,
)
from PHX2.stage23.errors import Stage23ContractError
from PHX2.stage23.models import (
    Stage23FilterInput,
    Stage23FilterResult,
    build_filter_result,
)


# ---------------------------------------------------------------------------
# Filter identity (locked)
# ---------------------------------------------------------------------------


FILTER_NAME: str = "wallet_source_quality"
FILTER_VERSION: str = "wallet_source_quality_v0"
THRESHOLD_VERSION: str = "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# Wallet / source-quality primitive keys (closed set)
# ---------------------------------------------------------------------------


PRIMITIVE_EARLY_WALLET_COUNT: str = "early_wallet_count"
PRIMITIVE_FRESH_WALLET_COUNT: str = "fresh_wallet_count"
PRIMITIVE_FRESH_WALLET_PCT: str = "fresh_wallet_pct"
PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT: str = "repeated_source_wallet_count"
PRIMITIVE_REPEATED_SOURCE_WALLET_PCT: str = "repeated_source_wallet_pct"
PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT: str = "common_funder_cluster_count"
PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT: str = (
    "largest_common_funder_cluster_pct"
)
PRIMITIVE_WALLET_AGE_KNOWN_COUNT: str = "wallet_age_known_count"
PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT: str = "wallet_age_unknown_count"
PRIMITIVE_WALLET_AGE_KNOWN_PCT: str = "wallet_age_known_pct"
PRIMITIVE_YOUNG_WALLET_PCT: str = "young_wallet_pct"
PRIMITIVE_MATURE_WALLET_PCT: str = "mature_wallet_pct"
PRIMITIVE_KNOWN_BAD_SOURCE_COUNT: str = "known_bad_source_count"
PRIMITIVE_KNOWN_BAD_SOURCE_PCT: str = "known_bad_source_pct"
PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT: str = "known_good_source_count"
PRIMITIVE_KNOWN_GOOD_SOURCE_PCT: str = "known_good_source_pct"
PRIMITIVE_DEV_WALLET_AGE_DAYS: str = "dev_wallet_age_days"
PRIMITIVE_CREATOR_WALLET_AGE_DAYS: str = "creator_wallet_age_days"
PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT: str = "source_quality_known_pct"


WALLET_SOURCE_PRIMITIVE_KEYS: tuple[str, ...] = (
    PRIMITIVE_EARLY_WALLET_COUNT,
    PRIMITIVE_FRESH_WALLET_COUNT,
    PRIMITIVE_FRESH_WALLET_PCT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_PCT,
    PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT,
    PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT,
    PRIMITIVE_WALLET_AGE_KNOWN_COUNT,
    PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT,
    PRIMITIVE_WALLET_AGE_KNOWN_PCT,
    PRIMITIVE_YOUNG_WALLET_PCT,
    PRIMITIVE_MATURE_WALLET_PCT,
    PRIMITIVE_KNOWN_BAD_SOURCE_COUNT,
    PRIMITIVE_KNOWN_BAD_SOURCE_PCT,
    PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT,
    PRIMITIVE_KNOWN_GOOD_SOURCE_PCT,
    PRIMITIVE_DEV_WALLET_AGE_DAYS,
    PRIMITIVE_CREATOR_WALLET_AGE_DAYS,
    PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT,
)


# Primitives whose presence is the minimum bar for a non-INSUFFICIENT
# verdict. The filter needs at least one of these source-quality
# primitives to reason about the wallet-source surface at all.
_REQUIRED_WALLET_SOURCE_PRIMITIVES: tuple[str, ...] = (
    PRIMITIVE_FRESH_WALLET_PCT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_PCT,
    PRIMITIVE_KNOWN_BAD_SOURCE_COUNT,
    PRIMITIVE_KNOWN_BAD_SOURCE_PCT,
    PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT,
    PRIMITIVE_MATURE_WALLET_PCT,
)


# Optional marker keys the upstream artifact may carry to signal
# that an entire sub-family is unsupported for this token. The
# locked token vocabulary mirrors the Stage 23 closed-set
# discipline.
PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND: str = (
    "wallet_source_primitive_kind"
)
PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND: str = (
    "wallet_age_primitive_kind"
)
PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND: str = (
    "funding_graph_primitive_kind"
)
PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND: str = (
    "provenance_primitive_kind"
)


WALLET_SOURCE_PRIMITIVE_KIND_SUPPORTED: str = "supported"
WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED: str = "unsupported"


WALLET_SOURCE_PRIMITIVE_KIND_VALUES: tuple[str, ...] = (
    WALLET_SOURCE_PRIMITIVE_KIND_SUPPORTED,
    WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED,
)


WALLET_SOURCE_PRIMITIVE_KIND_MARKERS: tuple[str, ...] = (
    PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND,
    PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND,
    PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND,
    PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND,
)


# ---------------------------------------------------------------------------
# Reason codes (closed set, canonical declaration order)
# ---------------------------------------------------------------------------


REASON_WALLET_SOURCE_QUALITY_NORMAL: str = "WALLET_SOURCE_QUALITY_NORMAL"
REASON_FRESH_WALLET_DENSITY_ELEVATED: str = "FRESH_WALLET_DENSITY_ELEVATED"
REASON_FRESH_WALLET_DENSITY_HIGH: str = "FRESH_WALLET_DENSITY_HIGH"
REASON_REPEATED_SOURCE_WALLETS: str = "REPEATED_SOURCE_WALLETS"
REASON_COMMON_FUNDER_CLUSTER_HIGH: str = "COMMON_FUNDER_CLUSTER_HIGH"
REASON_LARGEST_FUNDER_CLUSTER_HIGH: str = "LARGEST_FUNDER_CLUSTER_HIGH"
REASON_WALLET_AGE_COVERAGE_LOW: str = "WALLET_AGE_COVERAGE_LOW"
REASON_YOUNG_WALLET_SHARE_HIGH: str = "YOUNG_WALLET_SHARE_HIGH"
REASON_KNOWN_BAD_SOURCE_PRESENT: str = "KNOWN_BAD_SOURCE_PRESENT"
REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH: str = (
    "KNOWN_BAD_SOURCE_DENSITY_HIGH"
)
REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW: str = (
    "KNOWN_GOOD_SOURCE_DENSITY_LOW"
)
REASON_DEV_WALLET_TOO_FRESH: str = "DEV_WALLET_TOO_FRESH"
REASON_CREATOR_WALLET_TOO_FRESH: str = "CREATOR_WALLET_TOO_FRESH"
REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED: str = (
    "SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED"
)
REASON_FUNDING_GRAPH_UNSUPPORTED: str = "FUNDING_GRAPH_UNSUPPORTED"
REASON_WALLET_AGE_UNSUPPORTED: str = "WALLET_AGE_UNSUPPORTED"
REASON_PROVENANCE_UNSUPPORTED: str = "PROVENANCE_UNSUPPORTED"
REASON_WALLET_SOURCE_INPUT_MISSING: str = "WALLET_SOURCE_INPUT_MISSING"
REASON_WALLET_SOURCE_INPUT_PARTIAL: str = "WALLET_SOURCE_INPUT_PARTIAL"
REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING: str = (
    "REQUIRED_WALLET_SOURCE_FEATURE_MISSING"
)
REASON_INSUFFICIENT_WALLET_SAMPLE: str = "INSUFFICIENT_WALLET_SAMPLE"


# Canonical declaration ORDER for reason codes. The filter always
# emits its reason_codes tuple in this order regardless of the
# order it discovered each condition; this keeps evaluation_hash
# stable across re-runs.
WALLET_SOURCE_REASON_CODES: tuple[str, ...] = (
    REASON_WALLET_SOURCE_QUALITY_NORMAL,
    REASON_FRESH_WALLET_DENSITY_ELEVATED,
    REASON_FRESH_WALLET_DENSITY_HIGH,
    REASON_REPEATED_SOURCE_WALLETS,
    REASON_COMMON_FUNDER_CLUSTER_HIGH,
    REASON_LARGEST_FUNDER_CLUSTER_HIGH,
    REASON_WALLET_AGE_COVERAGE_LOW,
    REASON_YOUNG_WALLET_SHARE_HIGH,
    REASON_KNOWN_BAD_SOURCE_PRESENT,
    REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH,
    REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW,
    REASON_DEV_WALLET_TOO_FRESH,
    REASON_CREATOR_WALLET_TOO_FRESH,
    REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED,
    REASON_FUNDING_GRAPH_UNSUPPORTED,
    REASON_WALLET_AGE_UNSUPPORTED,
    REASON_PROVENANCE_UNSUPPORTED,
    REASON_WALLET_SOURCE_INPUT_MISSING,
    REASON_WALLET_SOURCE_INPUT_PARTIAL,
    REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING,
    REASON_INSUFFICIENT_WALLET_SAMPLE,
)


# Pre-computed rank map for the deterministic reason-code ordering.
_REASON_RANK: Mapping[str, int] = MappingProxyType(
    {code: index for index, code in enumerate(WALLET_SOURCE_REASON_CODES)}
)


# ---------------------------------------------------------------------------
# Threshold placeholders (observe-only)
# ---------------------------------------------------------------------------
#
# These are NOT calibrated detection values. The
# ``threshold_version`` axis on every emitted result is locked to
# ``"thresholds_v0_observe_only"`` so downstream callers always see
# the placeholder posture.


FRESH_WALLET_PCT_ELEVATED: float = 0.40
FRESH_WALLET_PCT_SUSPICIOUS: float = 0.70

REPEATED_SOURCE_WALLET_PCT_ELEVATED: float = 0.20
REPEATED_SOURCE_WALLET_PCT_SUSPICIOUS: float = 0.50
REPEATED_SOURCE_WALLET_COUNT_ELEVATED: int = 2

COMMON_FUNDER_CLUSTER_HIGH_COUNT: int = 3

LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT: float = 0.40
LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT: float = 0.70

WALLET_AGE_COVERAGE_LOW_PCT: float = 0.30
YOUNG_WALLET_SHARE_HIGH_PCT: float = 0.50

KNOWN_BAD_SOURCE_COUNT_PRESENT: int = 1
KNOWN_BAD_SOURCE_DENSITY_HIGH_PCT: float = 0.20
KNOWN_BAD_SOURCE_DENSITY_SCAM_LIKELY_PCT: float = 0.50

KNOWN_GOOD_SOURCE_DENSITY_LOW_PCT: float = 0.10

DEV_WALLET_TOO_FRESH_DAYS: float = 7.0
DEV_WALLET_VERY_FRESH_DAYS: float = 1.0
CREATOR_WALLET_TOO_FRESH_DAYS: float = 7.0
CREATOR_WALLET_VERY_FRESH_DAYS: float = 1.0

INSUFFICIENT_WALLET_SAMPLE_THRESHOLD: int = 5


# ---------------------------------------------------------------------------
# Internal projection helpers
# ---------------------------------------------------------------------------


class _WalletSourceProjection(NamedTuple):
    """Internal projection of wallet / source-quality primitives.

    Each field is either a numeric value (float or int) or
    ``None`` when the upstream payload_summary did not carry the
    primitive. The projection is immutable so downstream
    reasoning can not mutate it.
    """

    early_wallet_count: int | None
    fresh_wallet_count: int | None
    fresh_wallet_pct: float | None
    repeated_source_wallet_count: int | None
    repeated_source_wallet_pct: float | None
    common_funder_cluster_count: int | None
    largest_common_funder_cluster_pct: float | None
    wallet_age_known_count: int | None
    wallet_age_unknown_count: int | None
    wallet_age_known_pct: float | None
    young_wallet_pct: float | None
    mature_wallet_pct: float | None
    known_bad_source_count: int | None
    known_bad_source_pct: float | None
    known_good_source_count: int | None
    known_good_source_pct: float | None
    dev_wallet_age_days: float | None
    creator_wallet_age_days: float | None
    source_quality_known_pct: float | None
    is_overall_unsupported: bool
    is_wallet_age_unsupported: bool
    is_funding_graph_unsupported: bool
    is_provenance_unsupported: bool
    missing_primitive_keys: tuple[str, ...]


def _read_float(value: object) -> float | None:
    """Coerce a payload_summary value to ``float`` when safe.

    Bool is rejected (``isinstance(True, int)`` is True in
    Python; we treat bool as a separate type). Non-finite floats
    raise ``Stage23ContractError`` -- the Stage 22 / Stage 23
    sanitisers should never have admitted them in the first
    place; surfacing here means an upstream invariant broke.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage23ContractError(
                "wallet-source primitive value is non-finite "
                "(NaN / Infinity)"
            )
        return value
    return None


def _read_int(value: object) -> int | None:
    """Coerce a payload_summary value to a non-negative ``int`` when safe.

    Floats that are integral and non-negative are accepted (an
    upstream provider that emits ``5.0`` for a count is treated
    as ``5``). Negative values are rejected with
    ``Stage23ContractError`` because a negative wallet-source
    count is contractually impossible.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value < 0:
            raise Stage23ContractError(
                "wallet-source primitive integer value is negative"
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage23ContractError(
                "wallet-source primitive value is non-finite "
                "(NaN / Infinity)"
            )
        if value < 0.0:
            raise Stage23ContractError(
                "wallet-source primitive numeric value is negative"
            )
        if value != int(value):
            return None
        return int(value)
    return None


def _read_non_negative_float(value: object) -> float | None:
    """Coerce a payload_summary value to a non-negative ``float`` when safe."""
    result = _read_float(value)
    if result is None:
        return None
    if result < 0.0:
        raise Stage23ContractError(
            "wallet-source primitive float value is negative"
        )
    return result


def _read_pct(value: object) -> float | None:
    """Coerce a payload_summary value to a bounded ``[0.0, 1.0]`` float.

    Returns ``None`` when the payload_summary did not carry the
    primitive at all. Raises ``Stage23ContractError`` when the
    value is present but outside the closed ``[0.0, 1.0]`` band
    or is non-finite. Stage 23 percentage primitives are
    contractually a fraction; an out-of-band value is a hard
    contract violation, not data the filter should silently round
    or clamp into NORMAL.
    """
    coerced = _read_float(value)
    if coerced is None:
        return None
    if coerced < 0.0:
        raise Stage23ContractError(
            "wallet-source percentage primitive is below 0.0"
        )
    if coerced > 1.0:
        raise Stage23ContractError(
            "wallet-source percentage primitive is above 1.0"
        )
    return coerced


def _marker_is_unsupported(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED
    )


def _validate_marker_value(*, marker_name: str, value: object) -> None:
    """Raise ``Stage23ContractError`` if a marker carries a non-closed-set value.

    ``None`` (the marker was absent from the payload_summary) is
    accepted unconditionally. A present marker value must be one
    of the closed-set ``WALLET_SOURCE_PRIMITIVE_KIND_VALUES``
    tokens; any other value is a contract violation rather than a
    silently-ignored payload.
    """
    if value is None:
        return
    if value in WALLET_SOURCE_PRIMITIVE_KIND_VALUES:
        return
    raise Stage23ContractError(
        f"{marker_name} marker carries a non-closed-set value"
    )


def _project_wallet_source(
    *,
    payload: Mapping[str, object],
) -> _WalletSourceProjection:
    """Project the wallet / source-quality primitives out of ``payload``."""
    early_wallet_count = _read_int(payload.get(PRIMITIVE_EARLY_WALLET_COUNT))
    fresh_wallet_count = _read_int(payload.get(PRIMITIVE_FRESH_WALLET_COUNT))
    fresh_wallet_pct = _read_pct(payload.get(PRIMITIVE_FRESH_WALLET_PCT))
    repeated_source_wallet_count = _read_int(
        payload.get(PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT)
    )
    repeated_source_wallet_pct = _read_pct(
        payload.get(PRIMITIVE_REPEATED_SOURCE_WALLET_PCT)
    )
    common_funder_cluster_count = _read_int(
        payload.get(PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT)
    )
    largest_common_funder_cluster_pct = _read_pct(
        payload.get(PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT)
    )
    wallet_age_known_count = _read_int(
        payload.get(PRIMITIVE_WALLET_AGE_KNOWN_COUNT)
    )
    wallet_age_unknown_count = _read_int(
        payload.get(PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT)
    )
    wallet_age_known_pct = _read_pct(
        payload.get(PRIMITIVE_WALLET_AGE_KNOWN_PCT)
    )
    young_wallet_pct = _read_pct(payload.get(PRIMITIVE_YOUNG_WALLET_PCT))
    mature_wallet_pct = _read_pct(
        payload.get(PRIMITIVE_MATURE_WALLET_PCT)
    )
    known_bad_source_count = _read_int(
        payload.get(PRIMITIVE_KNOWN_BAD_SOURCE_COUNT)
    )
    known_bad_source_pct = _read_pct(
        payload.get(PRIMITIVE_KNOWN_BAD_SOURCE_PCT)
    )
    known_good_source_count = _read_int(
        payload.get(PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT)
    )
    known_good_source_pct = _read_pct(
        payload.get(PRIMITIVE_KNOWN_GOOD_SOURCE_PCT)
    )
    dev_wallet_age_days = _read_non_negative_float(
        payload.get(PRIMITIVE_DEV_WALLET_AGE_DAYS)
    )
    creator_wallet_age_days = _read_non_negative_float(
        payload.get(PRIMITIVE_CREATOR_WALLET_AGE_DAYS)
    )
    source_quality_known_pct = _read_pct(
        payload.get(PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT)
    )

    raw_overall_marker = payload.get(PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND)
    raw_wallet_age_marker = payload.get(PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND)
    raw_funding_graph_marker = payload.get(
        PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND
    )
    raw_provenance_marker = payload.get(PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND)

    _validate_marker_value(
        marker_name=PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND,
        value=raw_overall_marker,
    )
    _validate_marker_value(
        marker_name=PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND,
        value=raw_wallet_age_marker,
    )
    _validate_marker_value(
        marker_name=PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND,
        value=raw_funding_graph_marker,
    )
    _validate_marker_value(
        marker_name=PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND,
        value=raw_provenance_marker,
    )

    is_overall_unsupported = _marker_is_unsupported(raw_overall_marker)
    is_wallet_age_unsupported = _marker_is_unsupported(raw_wallet_age_marker)
    is_funding_graph_unsupported = _marker_is_unsupported(
        raw_funding_graph_marker
    )
    is_provenance_unsupported = _marker_is_unsupported(raw_provenance_marker)

    raw_values: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_EARLY_WALLET_COUNT, early_wallet_count),
        (PRIMITIVE_FRESH_WALLET_COUNT, fresh_wallet_count),
        (PRIMITIVE_FRESH_WALLET_PCT, fresh_wallet_pct),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
            repeated_source_wallet_count,
        ),
        (PRIMITIVE_REPEATED_SOURCE_WALLET_PCT, repeated_source_wallet_pct),
        (
            PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT,
            common_funder_cluster_count,
        ),
        (
            PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT,
            largest_common_funder_cluster_pct,
        ),
        (PRIMITIVE_WALLET_AGE_KNOWN_COUNT, wallet_age_known_count),
        (PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT, wallet_age_unknown_count),
        (PRIMITIVE_WALLET_AGE_KNOWN_PCT, wallet_age_known_pct),
        (PRIMITIVE_YOUNG_WALLET_PCT, young_wallet_pct),
        (PRIMITIVE_MATURE_WALLET_PCT, mature_wallet_pct),
        (PRIMITIVE_KNOWN_BAD_SOURCE_COUNT, known_bad_source_count),
        (PRIMITIVE_KNOWN_BAD_SOURCE_PCT, known_bad_source_pct),
        (PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT, known_good_source_count),
        (PRIMITIVE_KNOWN_GOOD_SOURCE_PCT, known_good_source_pct),
        (PRIMITIVE_DEV_WALLET_AGE_DAYS, dev_wallet_age_days),
        (PRIMITIVE_CREATOR_WALLET_AGE_DAYS, creator_wallet_age_days),
        (PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT, source_quality_known_pct),
    )
    missing_keys = tuple(
        sorted(key for key, val in raw_values if val is None)
    )

    return _WalletSourceProjection(
        early_wallet_count=early_wallet_count,
        fresh_wallet_count=fresh_wallet_count,
        fresh_wallet_pct=fresh_wallet_pct,
        repeated_source_wallet_count=repeated_source_wallet_count,
        repeated_source_wallet_pct=repeated_source_wallet_pct,
        common_funder_cluster_count=common_funder_cluster_count,
        largest_common_funder_cluster_pct=largest_common_funder_cluster_pct,
        wallet_age_known_count=wallet_age_known_count,
        wallet_age_unknown_count=wallet_age_unknown_count,
        wallet_age_known_pct=wallet_age_known_pct,
        young_wallet_pct=young_wallet_pct,
        mature_wallet_pct=mature_wallet_pct,
        known_bad_source_count=known_bad_source_count,
        known_bad_source_pct=known_bad_source_pct,
        known_good_source_count=known_good_source_count,
        known_good_source_pct=known_good_source_pct,
        dev_wallet_age_days=dev_wallet_age_days,
        creator_wallet_age_days=creator_wallet_age_days,
        source_quality_known_pct=source_quality_known_pct,
        is_overall_unsupported=is_overall_unsupported,
        is_wallet_age_unsupported=is_wallet_age_unsupported,
        is_funding_graph_unsupported=is_funding_graph_unsupported,
        is_provenance_unsupported=is_provenance_unsupported,
        missing_primitive_keys=missing_keys,
    )


# ---------------------------------------------------------------------------
# Reasoning helpers
# ---------------------------------------------------------------------------


def _label_priority(label: str) -> int:
    """Return a severity rank for a label so the filter can fold the
    per-primitive verdicts into a single overall label.
    """
    ranks = {
        LABEL_NORMAL: 0,
        LABEL_ELEVATED: 1,
        LABEL_SUSPICIOUS: 2,
        LABEL_SCAM_LIKELY: 3,
    }
    return ranks.get(label, -1)


def _escalate(current: str, candidate: str) -> str:
    """Return the more severe of two labels by priority.

    Both labels must belong to the severity ladder
    (``NORMAL`` / ``ELEVATED`` / ``SUSPICIOUS`` / ``SCAM_LIKELY``).
    The non-severity labels (``UNKNOWN`` / ``INSUFFICIENT_DATA`` /
    ``MISSING_INPUT``) are handled outside this helper.
    """
    if _label_priority(candidate) > _label_priority(current):
        return candidate
    return current


def _sort_reason_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Return ``codes`` re-ordered into the canonical reason-code order."""
    return tuple(
        sorted(codes, key=lambda code: _REASON_RANK.get(code, 1 << 30))
    )


def _build_numeric_features(
    projection: _WalletSourceProjection,
) -> Mapping[str, object]:
    """Build the immutable numeric_features mapping the result carries."""
    out: dict[str, object] = {}
    pairs: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_EARLY_WALLET_COUNT, projection.early_wallet_count),
        (PRIMITIVE_FRESH_WALLET_COUNT, projection.fresh_wallet_count),
        (PRIMITIVE_FRESH_WALLET_PCT, projection.fresh_wallet_pct),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
            projection.repeated_source_wallet_count,
        ),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_PCT,
            projection.repeated_source_wallet_pct,
        ),
        (
            PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT,
            projection.common_funder_cluster_count,
        ),
        (
            PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT,
            projection.largest_common_funder_cluster_pct,
        ),
        (
            PRIMITIVE_WALLET_AGE_KNOWN_COUNT,
            projection.wallet_age_known_count,
        ),
        (
            PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT,
            projection.wallet_age_unknown_count,
        ),
        (PRIMITIVE_WALLET_AGE_KNOWN_PCT, projection.wallet_age_known_pct),
        (PRIMITIVE_YOUNG_WALLET_PCT, projection.young_wallet_pct),
        (PRIMITIVE_MATURE_WALLET_PCT, projection.mature_wallet_pct),
        (
            PRIMITIVE_KNOWN_BAD_SOURCE_COUNT,
            projection.known_bad_source_count,
        ),
        (PRIMITIVE_KNOWN_BAD_SOURCE_PCT, projection.known_bad_source_pct),
        (
            PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT,
            projection.known_good_source_count,
        ),
        (PRIMITIVE_KNOWN_GOOD_SOURCE_PCT, projection.known_good_source_pct),
        (PRIMITIVE_DEV_WALLET_AGE_DAYS, projection.dev_wallet_age_days),
        (
            PRIMITIVE_CREATOR_WALLET_AGE_DAYS,
            projection.creator_wallet_age_days,
        ),
        (
            PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT,
            projection.source_quality_known_pct,
        ),
    )
    for key, value in pairs:
        if value is None:
            continue
        out[key] = value
    return MappingProxyType(out)


def _has_any_wallet_source_primitive(
    projection: _WalletSourceProjection,
) -> bool:
    return any(
        getattr(projection, attr) is not None
        for attr in (
            "early_wallet_count",
            "fresh_wallet_count",
            "fresh_wallet_pct",
            "repeated_source_wallet_count",
            "repeated_source_wallet_pct",
            "common_funder_cluster_count",
            "largest_common_funder_cluster_pct",
            "wallet_age_known_count",
            "wallet_age_unknown_count",
            "wallet_age_known_pct",
            "young_wallet_pct",
            "mature_wallet_pct",
            "known_bad_source_count",
            "known_bad_source_pct",
            "known_good_source_count",
            "known_good_source_pct",
            "dev_wallet_age_days",
            "creator_wallet_age_days",
            "source_quality_known_pct",
        )
    )


_REQUIRED_PRIMITIVE_ATTR_NAMES: Mapping[str, str] = MappingProxyType(
    {
        PRIMITIVE_FRESH_WALLET_PCT: "fresh_wallet_pct",
        PRIMITIVE_REPEATED_SOURCE_WALLET_PCT: "repeated_source_wallet_pct",
        PRIMITIVE_KNOWN_BAD_SOURCE_COUNT: "known_bad_source_count",
        PRIMITIVE_KNOWN_BAD_SOURCE_PCT: "known_bad_source_pct",
        PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT: (
            "largest_common_funder_cluster_pct"
        ),
        PRIMITIVE_MATURE_WALLET_PCT: "mature_wallet_pct",
    }
)


def _has_required_wallet_source_primitive(
    projection: _WalletSourceProjection,
) -> bool:
    return any(
        getattr(projection, _REQUIRED_PRIMITIVE_ATTR_NAMES[key]) is not None
        for key in _REQUIRED_WALLET_SOURCE_PRIMITIVES
    )


# ---------------------------------------------------------------------------
# Severity verdict
# ---------------------------------------------------------------------------


def _classify_severity(
    projection: _WalletSourceProjection,
) -> tuple[str, tuple[str, ...]]:
    """Compute the severity label + reason codes for a wallet-source snapshot.

    Caller has already ensured at least one of the required
    wallet-source primitives is present.
    """
    label = LABEL_NORMAL
    reasons: list[str] = []

    fresh_pct = projection.fresh_wallet_pct
    if fresh_pct is not None:
        if fresh_pct >= FRESH_WALLET_PCT_SUSPICIOUS:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_FRESH_WALLET_DENSITY_HIGH)
        elif fresh_pct >= FRESH_WALLET_PCT_ELEVATED:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_FRESH_WALLET_DENSITY_ELEVATED)

    repeated_pct = projection.repeated_source_wallet_pct
    repeated_count = projection.repeated_source_wallet_count
    if repeated_pct is not None:
        if repeated_pct >= REPEATED_SOURCE_WALLET_PCT_SUSPICIOUS:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_REPEATED_SOURCE_WALLETS)
        elif repeated_pct >= REPEATED_SOURCE_WALLET_PCT_ELEVATED:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_REPEATED_SOURCE_WALLETS)
    elif (
        repeated_count is not None
        and repeated_count >= REPEATED_SOURCE_WALLET_COUNT_ELEVATED
    ):
        label = _escalate(label, LABEL_ELEVATED)
        reasons.append(REASON_REPEATED_SOURCE_WALLETS)

    cluster_count = projection.common_funder_cluster_count
    if (
        cluster_count is not None
        and cluster_count >= COMMON_FUNDER_CLUSTER_HIGH_COUNT
    ):
        label = _escalate(label, LABEL_SUSPICIOUS)
        reasons.append(REASON_COMMON_FUNDER_CLUSTER_HIGH)

    largest_funder_pct = projection.largest_common_funder_cluster_pct
    if largest_funder_pct is not None:
        if largest_funder_pct >= LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_LARGEST_FUNDER_CLUSTER_HIGH)
        elif largest_funder_pct >= LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_LARGEST_FUNDER_CLUSTER_HIGH)

    wallet_age_known_pct = projection.wallet_age_known_pct
    if (
        wallet_age_known_pct is not None
        and wallet_age_known_pct < WALLET_AGE_COVERAGE_LOW_PCT
    ):
        reasons.append(REASON_WALLET_AGE_COVERAGE_LOW)
        # Low age coverage is a contributing signal, not a verdict
        # on its own; it nudges the label off NORMAL but never past
        # ELEVATED.
        label = _escalate(label, LABEL_ELEVATED)

    young_pct = projection.young_wallet_pct
    if (
        young_pct is not None
        and young_pct >= YOUNG_WALLET_SHARE_HIGH_PCT
    ):
        label = _escalate(label, LABEL_ELEVATED)
        reasons.append(REASON_YOUNG_WALLET_SHARE_HIGH)

    known_bad_count = projection.known_bad_source_count
    if (
        known_bad_count is not None
        and known_bad_count >= KNOWN_BAD_SOURCE_COUNT_PRESENT
    ):
        label = _escalate(label, LABEL_SUSPICIOUS)
        reasons.append(REASON_KNOWN_BAD_SOURCE_PRESENT)

    known_bad_pct = projection.known_bad_source_pct
    if known_bad_pct is not None:
        if known_bad_pct >= KNOWN_BAD_SOURCE_DENSITY_SCAM_LIKELY_PCT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH)
        elif known_bad_pct >= KNOWN_BAD_SOURCE_DENSITY_HIGH_PCT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH)

    known_good_pct = projection.known_good_source_pct
    if (
        known_good_pct is not None
        and known_good_pct < KNOWN_GOOD_SOURCE_DENSITY_LOW_PCT
    ):
        # Low good-source density is a contributing signal; it
        # nudges the label off NORMAL but never past ELEVATED.
        label = _escalate(label, LABEL_ELEVATED)
        reasons.append(REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW)

    dev_age = projection.dev_wallet_age_days
    if dev_age is not None:
        if dev_age < DEV_WALLET_VERY_FRESH_DAYS:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_DEV_WALLET_TOO_FRESH)
        elif dev_age < DEV_WALLET_TOO_FRESH_DAYS:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_DEV_WALLET_TOO_FRESH)

    creator_age = projection.creator_wallet_age_days
    if creator_age is not None:
        if creator_age < CREATOR_WALLET_VERY_FRESH_DAYS:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_CREATOR_WALLET_TOO_FRESH)
        elif creator_age < CREATOR_WALLET_TOO_FRESH_DAYS:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_CREATOR_WALLET_TOO_FRESH)

    if not reasons:
        reasons.append(REASON_WALLET_SOURCE_QUALITY_NORMAL)

    return label, tuple(reasons)


# ---------------------------------------------------------------------------
# Public filter surface
# ---------------------------------------------------------------------------


def _collect_unsupported_reasons(
    projection: _WalletSourceProjection,
) -> tuple[str, ...]:
    """Return the unsupported-reason tuple for an unsupported-marker payload.

    Returns an empty tuple when no unsupported marker is set on
    the payload.
    """
    reasons: list[str] = []
    if projection.is_overall_unsupported:
        reasons.append(REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED)
    if projection.is_funding_graph_unsupported:
        reasons.append(REASON_FUNDING_GRAPH_UNSUPPORTED)
    if projection.is_wallet_age_unsupported:
        reasons.append(REASON_WALLET_AGE_UNSUPPORTED)
    if projection.is_provenance_unsupported:
        reasons.append(REASON_PROVENANCE_UNSUPPORTED)
    return tuple(reasons)


def evaluate(
    *,
    filter_input: Stage23FilterInput,
) -> Stage23FilterResult:
    """Evaluate the wallet / source-quality filter for one input.

    Pure function: no env reads, no clock reads, no network,
    no disk writes. The returned ``Stage23FilterResult`` carries
    the filter's verdict and is the input to
    ``compute_evaluation_hash`` downstream.
    """
    payload = filter_input.payload_summary
    if not isinstance(payload, Mapping):
        raise Stage23ContractError(
            "filter_input.payload_summary must be a Mapping"
        )

    projection = _project_wallet_source(payload=payload)
    numeric_features = _build_numeric_features(projection)

    unsupported_reasons = _collect_unsupported_reasons(projection)
    if unsupported_reasons:
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_WALLET_SOURCE_QUALITY,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_UNKNOWN,
            data_status=DATA_STATUS_UNSUPPORTED,
            reason_codes=_sort_reason_codes(unsupported_reasons),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    if not _has_any_wallet_source_primitive(projection):
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_WALLET_SOURCE_QUALITY,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_MISSING_INPUT,
            data_status=DATA_STATUS_MISSING,
            reason_codes=(REASON_WALLET_SOURCE_INPUT_MISSING,),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    early_wallet_count = projection.early_wallet_count
    insufficient_sample = (
        early_wallet_count is not None
        and early_wallet_count < INSUFFICIENT_WALLET_SAMPLE_THRESHOLD
    )

    if insufficient_sample:
        reasons = [REASON_INSUFFICIENT_WALLET_SAMPLE]
        if projection.missing_primitive_keys:
            reasons.append(REASON_WALLET_SOURCE_INPUT_PARTIAL)
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_WALLET_SOURCE_QUALITY,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_INSUFFICIENT_DATA,
            data_status=(
                DATA_STATUS_PARTIAL
                if projection.missing_primitive_keys
                else DATA_STATUS_COMPLETE
            ),
            reason_codes=_sort_reason_codes(tuple(reasons)),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    if not _has_required_wallet_source_primitive(projection):
        reasons = [
            REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING,
            REASON_WALLET_SOURCE_INPUT_PARTIAL,
        ]
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_WALLET_SOURCE_QUALITY,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_INSUFFICIENT_DATA,
            data_status=DATA_STATUS_PARTIAL,
            reason_codes=_sort_reason_codes(tuple(reasons)),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    label, severity_reasons = _classify_severity(projection)
    reasons_accum: list[str] = list(severity_reasons)
    if projection.missing_primitive_keys:
        reasons_accum.append(REASON_WALLET_SOURCE_INPUT_PARTIAL)

    data_status = (
        DATA_STATUS_PARTIAL
        if projection.missing_primitive_keys
        else DATA_STATUS_COMPLETE
    )

    return build_filter_result(
        filter_name=FILTER_NAME,
        filter_family=FILTER_FAMILY_WALLET_SOURCE_QUALITY,
        filter_version=FILTER_VERSION,
        threshold_version=THRESHOLD_VERSION,
        label=label,
        data_status=data_status,
        reason_codes=_sort_reason_codes(tuple(reasons_accum)),
        numeric_features=numeric_features,
        missing_features=projection.missing_primitive_keys,
    )


class WalletSourceQualityFilter:
    """Class-shaped surface satisfying the ``Stage23Filter`` Protocol.

    The class wraps the pure ``evaluate`` function so callers
    that prefer a Protocol-shaped instance (Stage 23.5 runners
    in particular) can construct one without losing the pure
    function's testability.
    """

    filter_name: str = FILTER_NAME
    filter_family: str = FILTER_FAMILY_WALLET_SOURCE_QUALITY
    filter_version: str = FILTER_VERSION
    threshold_version: str = THRESHOLD_VERSION

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult:
        return evaluate(filter_input=filter_input)


__all__ = [
    "COMMON_FUNDER_CLUSTER_HIGH_COUNT",
    "CREATOR_WALLET_TOO_FRESH_DAYS",
    "CREATOR_WALLET_VERY_FRESH_DAYS",
    "DEV_WALLET_TOO_FRESH_DAYS",
    "DEV_WALLET_VERY_FRESH_DAYS",
    "FILTER_NAME",
    "FILTER_VERSION",
    "FRESH_WALLET_PCT_ELEVATED",
    "FRESH_WALLET_PCT_SUSPICIOUS",
    "INSUFFICIENT_WALLET_SAMPLE_THRESHOLD",
    "KNOWN_BAD_SOURCE_COUNT_PRESENT",
    "KNOWN_BAD_SOURCE_DENSITY_HIGH_PCT",
    "KNOWN_BAD_SOURCE_DENSITY_SCAM_LIKELY_PCT",
    "KNOWN_GOOD_SOURCE_DENSITY_LOW_PCT",
    "LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT",
    "LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT",
    "PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND",
    "PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND",
    "PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND",
    "PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND",
    "PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT",
    "PRIMITIVE_CREATOR_WALLET_AGE_DAYS",
    "PRIMITIVE_DEV_WALLET_AGE_DAYS",
    "PRIMITIVE_EARLY_WALLET_COUNT",
    "PRIMITIVE_FRESH_WALLET_COUNT",
    "PRIMITIVE_FRESH_WALLET_PCT",
    "PRIMITIVE_KNOWN_BAD_SOURCE_COUNT",
    "PRIMITIVE_KNOWN_BAD_SOURCE_PCT",
    "PRIMITIVE_KNOWN_GOOD_SOURCE_COUNT",
    "PRIMITIVE_KNOWN_GOOD_SOURCE_PCT",
    "PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT",
    "PRIMITIVE_MATURE_WALLET_PCT",
    "PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT",
    "PRIMITIVE_REPEATED_SOURCE_WALLET_PCT",
    "PRIMITIVE_SOURCE_QUALITY_KNOWN_PCT",
    "PRIMITIVE_WALLET_AGE_KNOWN_COUNT",
    "PRIMITIVE_WALLET_AGE_KNOWN_PCT",
    "PRIMITIVE_WALLET_AGE_UNKNOWN_COUNT",
    "PRIMITIVE_YOUNG_WALLET_PCT",
    "REASON_COMMON_FUNDER_CLUSTER_HIGH",
    "REASON_CREATOR_WALLET_TOO_FRESH",
    "REASON_DEV_WALLET_TOO_FRESH",
    "REASON_FRESH_WALLET_DENSITY_ELEVATED",
    "REASON_FRESH_WALLET_DENSITY_HIGH",
    "REASON_FUNDING_GRAPH_UNSUPPORTED",
    "REASON_INSUFFICIENT_WALLET_SAMPLE",
    "REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH",
    "REASON_KNOWN_BAD_SOURCE_PRESENT",
    "REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW",
    "REASON_LARGEST_FUNDER_CLUSTER_HIGH",
    "REASON_PROVENANCE_UNSUPPORTED",
    "REASON_REPEATED_SOURCE_WALLETS",
    "REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING",
    "REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED",
    "REASON_WALLET_AGE_COVERAGE_LOW",
    "REASON_WALLET_AGE_UNSUPPORTED",
    "REASON_WALLET_SOURCE_INPUT_MISSING",
    "REASON_WALLET_SOURCE_INPUT_PARTIAL",
    "REASON_WALLET_SOURCE_QUALITY_NORMAL",
    "REASON_YOUNG_WALLET_SHARE_HIGH",
    "REPEATED_SOURCE_WALLET_COUNT_ELEVATED",
    "REPEATED_SOURCE_WALLET_PCT_ELEVATED",
    "REPEATED_SOURCE_WALLET_PCT_SUSPICIOUS",
    "THRESHOLD_VERSION",
    "WALLET_AGE_COVERAGE_LOW_PCT",
    "WALLET_SOURCE_PRIMITIVE_KEYS",
    "WALLET_SOURCE_PRIMITIVE_KIND_MARKERS",
    "WALLET_SOURCE_PRIMITIVE_KIND_SUPPORTED",
    "WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED",
    "WALLET_SOURCE_PRIMITIVE_KIND_VALUES",
    "WALLET_SOURCE_REASON_CODES",
    "WalletSourceQualityFilter",
    "YOUNG_WALLET_SHARE_HIGH_PCT",
    "evaluate",
]
