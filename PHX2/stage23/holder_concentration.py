"""Stage 23.2 holder-concentration observe-only filter.

This is the first concrete Stage 23 filter, landing under the
``HOLDER_CONCENTRATION`` filter family. The filter is pure:
given a ``Stage23FilterInput`` it returns a
``Stage23FilterResult`` and never touches the network, the
clock, the environment, or disk. Stage 23 is observe-only:
the filter assigns a closed-set label and a closed-set
``data_status`` plus a deterministic tuple of reason codes;
it never blocks, routes, or alerts.

Input shape:

  * Holder snapshot primitives are read out of
    ``filter_input.payload_summary`` by key. The Stage 23
    input reader already enforces the payload-summary safety
    rules at ingest, so this filter consumes the projected
    mapping verbatim.
  * Recognized primitive keys (each optional):

      ``unique_holder_count``        -- int
      ``top_1_holder_pct``           -- float in [0.0, 1.0]
      ``top_5_holder_pct``           -- float in [0.0, 1.0]
      ``top_10_holder_pct``          -- float in [0.0, 1.0]
      ``top_20_holder_pct``          -- float in [0.0, 1.0]
      ``top_50_holder_pct``          -- float in [0.0, 1.0]
      ``creator_retained_pct``       -- float in [0.0, 1.0]
      ``dev_related_retained_pct``   -- float in [0.0, 1.0]
      ``pool_related_pct``           -- float in [0.0, 1.0]
      ``snapshot_age_seconds``       -- int / float, non-negative

  * Optional marker key ``holder_primitive_kind`` is recognized
    for ``"unsupported"`` -- the filter emits
    ``label=UNKNOWN`` / ``data_status=UNSUPPORTED`` with
    ``HOLDER_PRIMITIVE_UNSUPPORTED`` when the upstream
    primitive family is unsupported for this token.

Output shape:

  * ``filter_name``       -- ``"holder_concentration"``
  * ``filter_family``     -- ``"HOLDER_CONCENTRATION"``
  * ``filter_version``    -- ``"holder_concentration_v0"``
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
  are NOT calibrated enforcement values. The
  ``threshold_version`` is locked to
  ``"thresholds_v0_observe_only"`` to make the placeholder
  posture explicit on every emitted record.

This module imports only stdlib (``math`` / ``types`` /
``typing``) plus the Stage 23 constants / models / errors. It
does NOT import Stage 21 or Stage 22 modules, does NOT import
any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, contains no
top-level I/O, and writes nothing to disk.
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
    FILTER_FAMILY_HOLDER_CONCENTRATION,
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


FILTER_NAME: str = "holder_concentration"
FILTER_VERSION: str = "holder_concentration_v0"
THRESHOLD_VERSION: str = "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# Holder snapshot primitive keys (closed set)
# ---------------------------------------------------------------------------


PRIMITIVE_UNIQUE_HOLDER_COUNT: str = "unique_holder_count"
PRIMITIVE_TOP_1_HOLDER_PCT: str = "top_1_holder_pct"
PRIMITIVE_TOP_5_HOLDER_PCT: str = "top_5_holder_pct"
PRIMITIVE_TOP_10_HOLDER_PCT: str = "top_10_holder_pct"
PRIMITIVE_TOP_20_HOLDER_PCT: str = "top_20_holder_pct"
PRIMITIVE_TOP_50_HOLDER_PCT: str = "top_50_holder_pct"
PRIMITIVE_CREATOR_RETAINED_PCT: str = "creator_retained_pct"
PRIMITIVE_DEV_RELATED_RETAINED_PCT: str = "dev_related_retained_pct"
PRIMITIVE_POOL_RELATED_PCT: str = "pool_related_pct"
PRIMITIVE_SNAPSHOT_AGE_SECONDS: str = "snapshot_age_seconds"


HOLDER_PRIMITIVE_KEYS: tuple[str, ...] = (
    PRIMITIVE_UNIQUE_HOLDER_COUNT,
    PRIMITIVE_TOP_1_HOLDER_PCT,
    PRIMITIVE_TOP_5_HOLDER_PCT,
    PRIMITIVE_TOP_10_HOLDER_PCT,
    PRIMITIVE_TOP_20_HOLDER_PCT,
    PRIMITIVE_TOP_50_HOLDER_PCT,
    PRIMITIVE_CREATOR_RETAINED_PCT,
    PRIMITIVE_DEV_RELATED_RETAINED_PCT,
    PRIMITIVE_POOL_RELATED_PCT,
    PRIMITIVE_SNAPSHOT_AGE_SECONDS,
)


# Primitives whose presence is the minimum bar for a non-INSUFFICIENT
# verdict. The filter needs at least one of these concentration
# primitives to reason about the holder distribution at all.
_REQUIRED_CONCENTRATION_PRIMITIVES: tuple[str, ...] = (
    PRIMITIVE_TOP_10_HOLDER_PCT,
    PRIMITIVE_TOP_20_HOLDER_PCT,
)


# Optional marker key the upstream artifact may carry to signal the
# holder-primitive family is unsupported for this token. The locked
# token vocabulary mirrors the Stage 23 closed-set discipline.
PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND: str = "holder_primitive_kind"
HOLDER_PRIMITIVE_KIND_SUPPORTED: str = "supported"
HOLDER_PRIMITIVE_KIND_UNSUPPORTED: str = "unsupported"


HOLDER_PRIMITIVE_KIND_VALUES: tuple[str, ...] = (
    HOLDER_PRIMITIVE_KIND_SUPPORTED,
    HOLDER_PRIMITIVE_KIND_UNSUPPORTED,
)


# ---------------------------------------------------------------------------
# Reason codes (closed set, canonical declaration order)
# ---------------------------------------------------------------------------


REASON_HOLDER_CONCENTRATION_NORMAL: str = "HOLDER_CONCENTRATION_NORMAL"
REASON_TOP_1_CONCENTRATION_ELEVATED: str = "TOP_1_CONCENTRATION_ELEVATED"
REASON_TOP_10_CONCENTRATION_HIGH: str = "TOP_10_CONCENTRATION_HIGH"
REASON_TOP_20_CONCENTRATION_HIGH: str = "TOP_20_CONCENTRATION_HIGH"
REASON_TOP_50_CONCENTRATION_HIGH: str = "TOP_50_CONCENTRATION_HIGH"
REASON_LOW_HOLDER_BREADTH: str = "LOW_HOLDER_BREADTH"
REASON_CREATOR_RETAINED_HIGH: str = "CREATOR_RETAINED_HIGH"
REASON_DEV_RELATED_RETAINED_HIGH: str = "DEV_RELATED_RETAINED_HIGH"
REASON_POOL_RELATED_CONCENTRATION_HIGH: str = "POOL_RELATED_CONCENTRATION_HIGH"
REASON_HOLDER_SNAPSHOT_MISSING: str = "HOLDER_SNAPSHOT_MISSING"
REASON_HOLDER_SNAPSHOT_PARTIAL: str = "HOLDER_SNAPSHOT_PARTIAL"
REASON_HOLDER_SNAPSHOT_TOO_OLD: str = "HOLDER_SNAPSHOT_TOO_OLD"
REASON_HOLDER_PRIMITIVE_UNSUPPORTED: str = "HOLDER_PRIMITIVE_UNSUPPORTED"
REASON_INSUFFICIENT_HOLDER_COUNT: str = "INSUFFICIENT_HOLDER_COUNT"
REASON_REQUIRED_HOLDER_FEATURE_MISSING: str = (
    "REQUIRED_HOLDER_FEATURE_MISSING"
)


# Canonical declaration ORDER for reason codes. The filter always
# emits its reason_codes tuple in this order regardless of the
# order it discovered each condition; this keeps evaluation_hash
# stable across re-runs.
HOLDER_REASON_CODES: tuple[str, ...] = (
    REASON_HOLDER_CONCENTRATION_NORMAL,
    REASON_TOP_1_CONCENTRATION_ELEVATED,
    REASON_TOP_10_CONCENTRATION_HIGH,
    REASON_TOP_20_CONCENTRATION_HIGH,
    REASON_TOP_50_CONCENTRATION_HIGH,
    REASON_LOW_HOLDER_BREADTH,
    REASON_CREATOR_RETAINED_HIGH,
    REASON_DEV_RELATED_RETAINED_HIGH,
    REASON_POOL_RELATED_CONCENTRATION_HIGH,
    REASON_HOLDER_SNAPSHOT_MISSING,
    REASON_HOLDER_SNAPSHOT_PARTIAL,
    REASON_HOLDER_SNAPSHOT_TOO_OLD,
    REASON_HOLDER_PRIMITIVE_UNSUPPORTED,
    REASON_INSUFFICIENT_HOLDER_COUNT,
    REASON_REQUIRED_HOLDER_FEATURE_MISSING,
)


# Pre-computed rank map for the deterministic reason-code ordering.
_REASON_RANK: Mapping[str, int] = MappingProxyType(
    {code: index for index, code in enumerate(HOLDER_REASON_CODES)}
)


# ---------------------------------------------------------------------------
# Threshold placeholders (observe-only)
# ---------------------------------------------------------------------------
#
# These are NOT calibrated enforcement values. The
# ``threshold_version`` axis on every emitted result is locked to
# ``"thresholds_v0_observe_only"`` so downstream callers always see
# the placeholder posture.


TOP_1_ELEVATED_THRESHOLD: float = 0.15
TOP_1_SUSPICIOUS_THRESHOLD: float = 0.30
TOP_1_SCAM_LIKELY_THRESHOLD: float = 0.50

TOP_10_ELEVATED_THRESHOLD: float = 0.50
TOP_10_SUSPICIOUS_THRESHOLD: float = 0.80
TOP_10_SCAM_LIKELY_THRESHOLD: float = 0.95

TOP_20_ELEVATED_THRESHOLD: float = 0.60
TOP_20_SUSPICIOUS_THRESHOLD: float = 0.90

TOP_50_ELEVATED_THRESHOLD: float = 0.70

CREATOR_RETAINED_SUSPICIOUS_THRESHOLD: float = 0.25
CREATOR_RETAINED_SCAM_LIKELY_THRESHOLD: float = 0.50

DEV_RELATED_RETAINED_SUSPICIOUS_THRESHOLD: float = 0.25
DEV_RELATED_RETAINED_SCAM_LIKELY_THRESHOLD: float = 0.50

POOL_RELATED_SUSPICIOUS_THRESHOLD: float = 0.50

UNIQUE_HOLDER_MINIMUM: int = 5
LOW_HOLDER_BREADTH_THRESHOLD: int = 20

SNAPSHOT_AGE_TOO_OLD_SECONDS: int = 3600


# ---------------------------------------------------------------------------
# Internal projection helpers
# ---------------------------------------------------------------------------


class _HolderSnapshotProjection(NamedTuple):
    """Internal projection of holder primitives from a payload_summary.

    Each field is either a numeric value (float or int) or
    ``None`` when the upstream payload_summary did not carry the
    primitive. The projection is immutable so downstream
    reasoning can not mutate it.
    """

    unique_holder_count: int | None
    top_1_holder_pct: float | None
    top_5_holder_pct: float | None
    top_10_holder_pct: float | None
    top_20_holder_pct: float | None
    top_50_holder_pct: float | None
    creator_retained_pct: float | None
    dev_related_retained_pct: float | None
    pool_related_pct: float | None
    snapshot_age_seconds: float | None
    is_marked_unsupported: bool
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
                "holder primitive value is non-finite (NaN / Infinity)"
            )
        return value
    return None


def _read_int(value: object) -> int | None:
    """Coerce a payload_summary value to a non-negative ``int`` when safe.

    Floats that are integral and non-negative are accepted (an
    upstream provider that emits ``5.0`` for a count is treated
    as ``5``). Negative values are rejected with
    ``Stage23ContractError`` because a negative holder count is
    contractually impossible.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value < 0:
            raise Stage23ContractError(
                "holder primitive integer value is negative"
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage23ContractError(
                "holder primitive value is non-finite (NaN / Infinity)"
            )
        if value < 0.0:
            raise Stage23ContractError(
                "holder primitive numeric value is negative"
            )
        if value != int(value):
            return None
        return int(value)
    return None


def _project_holder_snapshot(
    *,
    payload: Mapping[str, object],
) -> _HolderSnapshotProjection:
    """Project the holder-snapshot primitives out of ``payload``."""
    unique_holder_count = _read_int(
        payload.get(PRIMITIVE_UNIQUE_HOLDER_COUNT)
    )
    top_1 = _read_float(payload.get(PRIMITIVE_TOP_1_HOLDER_PCT))
    top_5 = _read_float(payload.get(PRIMITIVE_TOP_5_HOLDER_PCT))
    top_10 = _read_float(payload.get(PRIMITIVE_TOP_10_HOLDER_PCT))
    top_20 = _read_float(payload.get(PRIMITIVE_TOP_20_HOLDER_PCT))
    top_50 = _read_float(payload.get(PRIMITIVE_TOP_50_HOLDER_PCT))
    creator_retained = _read_float(
        payload.get(PRIMITIVE_CREATOR_RETAINED_PCT)
    )
    dev_related_retained = _read_float(
        payload.get(PRIMITIVE_DEV_RELATED_RETAINED_PCT)
    )
    pool_related = _read_float(payload.get(PRIMITIVE_POOL_RELATED_PCT))
    snapshot_age = _read_float(
        payload.get(PRIMITIVE_SNAPSHOT_AGE_SECONDS)
    )

    marker_raw = payload.get(PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND)
    is_marked_unsupported = (
        isinstance(marker_raw, str)
        and marker_raw == HOLDER_PRIMITIVE_KIND_UNSUPPORTED
    )

    raw_values: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_UNIQUE_HOLDER_COUNT, unique_holder_count),
        (PRIMITIVE_TOP_1_HOLDER_PCT, top_1),
        (PRIMITIVE_TOP_5_HOLDER_PCT, top_5),
        (PRIMITIVE_TOP_10_HOLDER_PCT, top_10),
        (PRIMITIVE_TOP_20_HOLDER_PCT, top_20),
        (PRIMITIVE_TOP_50_HOLDER_PCT, top_50),
        (PRIMITIVE_CREATOR_RETAINED_PCT, creator_retained),
        (PRIMITIVE_DEV_RELATED_RETAINED_PCT, dev_related_retained),
        (PRIMITIVE_POOL_RELATED_PCT, pool_related),
        (PRIMITIVE_SNAPSHOT_AGE_SECONDS, snapshot_age),
    )
    missing_keys = tuple(
        sorted(key for key, val in raw_values if val is None)
    )

    return _HolderSnapshotProjection(
        unique_holder_count=unique_holder_count,
        top_1_holder_pct=top_1,
        top_5_holder_pct=top_5,
        top_10_holder_pct=top_10,
        top_20_holder_pct=top_20,
        top_50_holder_pct=top_50,
        creator_retained_pct=creator_retained,
        dev_related_retained_pct=dev_related_retained,
        pool_related_pct=pool_related,
        snapshot_age_seconds=snapshot_age,
        is_marked_unsupported=is_marked_unsupported,
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
    projection: _HolderSnapshotProjection,
) -> Mapping[str, object]:
    """Build the immutable numeric_features mapping the result carries."""
    out: dict[str, object] = {}
    pairs: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_UNIQUE_HOLDER_COUNT, projection.unique_holder_count),
        (PRIMITIVE_TOP_1_HOLDER_PCT, projection.top_1_holder_pct),
        (PRIMITIVE_TOP_5_HOLDER_PCT, projection.top_5_holder_pct),
        (PRIMITIVE_TOP_10_HOLDER_PCT, projection.top_10_holder_pct),
        (PRIMITIVE_TOP_20_HOLDER_PCT, projection.top_20_holder_pct),
        (PRIMITIVE_TOP_50_HOLDER_PCT, projection.top_50_holder_pct),
        (PRIMITIVE_CREATOR_RETAINED_PCT, projection.creator_retained_pct),
        (
            PRIMITIVE_DEV_RELATED_RETAINED_PCT,
            projection.dev_related_retained_pct,
        ),
        (PRIMITIVE_POOL_RELATED_PCT, projection.pool_related_pct),
        (PRIMITIVE_SNAPSHOT_AGE_SECONDS, projection.snapshot_age_seconds),
    )
    for key, value in pairs:
        if value is None:
            continue
        out[key] = value
    return MappingProxyType(out)


def _has_any_concentration_primitive(
    projection: _HolderSnapshotProjection,
) -> bool:
    return any(
        getattr(projection, attr) is not None
        for attr in (
            "top_1_holder_pct",
            "top_5_holder_pct",
            "top_10_holder_pct",
            "top_20_holder_pct",
            "top_50_holder_pct",
            "creator_retained_pct",
            "dev_related_retained_pct",
            "pool_related_pct",
        )
    )


def _has_required_concentration_primitive(
    projection: _HolderSnapshotProjection,
) -> bool:
    return any(
        getattr(projection, key) is not None
        for key in _REQUIRED_CONCENTRATION_PRIMITIVES
    )


# ---------------------------------------------------------------------------
# Severity verdict
# ---------------------------------------------------------------------------


def _classify_severity(
    projection: _HolderSnapshotProjection,
) -> tuple[str, tuple[str, ...]]:
    """Compute the severity label + reason codes for a snapshot.

    Caller has already ensured at least one of the required
    concentration primitives is present.
    """
    label = LABEL_NORMAL
    reasons: list[str] = []

    top_1 = projection.top_1_holder_pct
    if top_1 is not None:
        if top_1 >= TOP_1_SCAM_LIKELY_THRESHOLD:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_TOP_1_CONCENTRATION_ELEVATED)
        elif top_1 >= TOP_1_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_TOP_1_CONCENTRATION_ELEVATED)
        elif top_1 >= TOP_1_ELEVATED_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_TOP_1_CONCENTRATION_ELEVATED)

    top_10 = projection.top_10_holder_pct
    if top_10 is not None:
        if top_10 >= TOP_10_SCAM_LIKELY_THRESHOLD:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_TOP_10_CONCENTRATION_HIGH)
        elif top_10 >= TOP_10_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_TOP_10_CONCENTRATION_HIGH)
        elif top_10 >= TOP_10_ELEVATED_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_TOP_10_CONCENTRATION_HIGH)

    top_20 = projection.top_20_holder_pct
    if top_20 is not None:
        if top_20 >= TOP_20_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_TOP_20_CONCENTRATION_HIGH)
        elif top_20 >= TOP_20_ELEVATED_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_TOP_20_CONCENTRATION_HIGH)

    top_50 = projection.top_50_holder_pct
    if top_50 is not None:
        if top_50 >= TOP_50_ELEVATED_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_TOP_50_CONCENTRATION_HIGH)

    creator = projection.creator_retained_pct
    if creator is not None:
        if creator >= CREATOR_RETAINED_SCAM_LIKELY_THRESHOLD:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_CREATOR_RETAINED_HIGH)
        elif creator >= CREATOR_RETAINED_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_CREATOR_RETAINED_HIGH)

    dev_related = projection.dev_related_retained_pct
    if dev_related is not None:
        if dev_related >= DEV_RELATED_RETAINED_SCAM_LIKELY_THRESHOLD:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_DEV_RELATED_RETAINED_HIGH)
        elif dev_related >= DEV_RELATED_RETAINED_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_DEV_RELATED_RETAINED_HIGH)

    pool_related = projection.pool_related_pct
    if pool_related is not None:
        if pool_related >= POOL_RELATED_SUSPICIOUS_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_POOL_RELATED_CONCENTRATION_HIGH)

    unique_count = projection.unique_holder_count
    if unique_count is not None and unique_count < LOW_HOLDER_BREADTH_THRESHOLD:
        reasons.append(REASON_LOW_HOLDER_BREADTH)
        # Low breadth alone does not push past ELEVATED -- it is a
        # contributing signal, not a verdict.
        label = _escalate(label, LABEL_ELEVATED)

    if not reasons:
        reasons.append(REASON_HOLDER_CONCENTRATION_NORMAL)

    return label, tuple(reasons)


# ---------------------------------------------------------------------------
# Public filter surface
# ---------------------------------------------------------------------------


def evaluate(
    *,
    filter_input: Stage23FilterInput,
) -> Stage23FilterResult:
    """Evaluate the holder-concentration filter for one input.

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

    projection = _project_holder_snapshot(payload=payload)
    numeric_features = _build_numeric_features(projection)

    if projection.is_marked_unsupported:
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_UNKNOWN,
            data_status=DATA_STATUS_UNSUPPORTED,
            reason_codes=(REASON_HOLDER_PRIMITIVE_UNSUPPORTED,),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    has_any_primitive = (
        projection.unique_holder_count is not None
        or _has_any_concentration_primitive(projection)
        or projection.snapshot_age_seconds is not None
    )

    if not has_any_primitive:
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_MISSING_INPUT,
            data_status=DATA_STATUS_MISSING,
            reason_codes=(REASON_HOLDER_SNAPSHOT_MISSING,),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    snapshot_age = projection.snapshot_age_seconds
    snapshot_too_old = (
        snapshot_age is not None
        and snapshot_age > SNAPSHOT_AGE_TOO_OLD_SECONDS
    )

    unique_count = projection.unique_holder_count
    insufficient_count = (
        unique_count is not None and unique_count < UNIQUE_HOLDER_MINIMUM
    )

    if insufficient_count:
        reasons = [REASON_INSUFFICIENT_HOLDER_COUNT]
        if snapshot_too_old:
            reasons.append(REASON_HOLDER_SNAPSHOT_TOO_OLD)
        if projection.missing_primitive_keys:
            reasons.append(REASON_HOLDER_SNAPSHOT_PARTIAL)
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
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

    if not _has_required_concentration_primitive(projection):
        reasons = [
            REASON_REQUIRED_HOLDER_FEATURE_MISSING,
            REASON_HOLDER_SNAPSHOT_PARTIAL,
        ]
        if snapshot_too_old:
            reasons.append(REASON_HOLDER_SNAPSHOT_TOO_OLD)
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
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
        reasons_accum.append(REASON_HOLDER_SNAPSHOT_PARTIAL)
    if snapshot_too_old:
        reasons_accum.append(REASON_HOLDER_SNAPSHOT_TOO_OLD)

    data_status = (
        DATA_STATUS_PARTIAL
        if projection.missing_primitive_keys
        else DATA_STATUS_COMPLETE
    )

    return build_filter_result(
        filter_name=FILTER_NAME,
        filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
        filter_version=FILTER_VERSION,
        threshold_version=THRESHOLD_VERSION,
        label=label,
        data_status=data_status,
        reason_codes=_sort_reason_codes(tuple(reasons_accum)),
        numeric_features=numeric_features,
        missing_features=projection.missing_primitive_keys,
    )


class HolderConcentrationFilter:
    """Class-shaped surface satisfying the ``Stage23Filter`` Protocol.

    The class wraps the pure ``evaluate`` function so callers
    that prefer a Protocol-shaped instance (Stage 23.5 runners
    in particular) can construct one without losing the pure
    function's testability.
    """

    filter_name: str = FILTER_NAME
    filter_family: str = FILTER_FAMILY_HOLDER_CONCENTRATION
    filter_version: str = FILTER_VERSION
    threshold_version: str = THRESHOLD_VERSION

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult:
        return evaluate(filter_input=filter_input)


__all__ = [
    "FILTER_NAME",
    "FILTER_VERSION",
    "HOLDER_PRIMITIVE_KEYS",
    "HOLDER_PRIMITIVE_KIND_SUPPORTED",
    "HOLDER_PRIMITIVE_KIND_UNSUPPORTED",
    "HOLDER_PRIMITIVE_KIND_VALUES",
    "HOLDER_REASON_CODES",
    "HolderConcentrationFilter",
    "PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND",
    "PRIMITIVE_CREATOR_RETAINED_PCT",
    "PRIMITIVE_DEV_RELATED_RETAINED_PCT",
    "PRIMITIVE_POOL_RELATED_PCT",
    "PRIMITIVE_SNAPSHOT_AGE_SECONDS",
    "PRIMITIVE_TOP_1_HOLDER_PCT",
    "PRIMITIVE_TOP_10_HOLDER_PCT",
    "PRIMITIVE_TOP_20_HOLDER_PCT",
    "PRIMITIVE_TOP_5_HOLDER_PCT",
    "PRIMITIVE_TOP_50_HOLDER_PCT",
    "PRIMITIVE_UNIQUE_HOLDER_COUNT",
    "REASON_CREATOR_RETAINED_HIGH",
    "REASON_DEV_RELATED_RETAINED_HIGH",
    "REASON_HOLDER_CONCENTRATION_NORMAL",
    "REASON_HOLDER_PRIMITIVE_UNSUPPORTED",
    "REASON_HOLDER_SNAPSHOT_MISSING",
    "REASON_HOLDER_SNAPSHOT_PARTIAL",
    "REASON_HOLDER_SNAPSHOT_TOO_OLD",
    "REASON_INSUFFICIENT_HOLDER_COUNT",
    "REASON_LOW_HOLDER_BREADTH",
    "REASON_POOL_RELATED_CONCENTRATION_HIGH",
    "REASON_REQUIRED_HOLDER_FEATURE_MISSING",
    "REASON_TOP_1_CONCENTRATION_ELEVATED",
    "REASON_TOP_10_CONCENTRATION_HIGH",
    "REASON_TOP_20_CONCENTRATION_HIGH",
    "REASON_TOP_50_CONCENTRATION_HIGH",
    "THRESHOLD_VERSION",
    "evaluate",
]
