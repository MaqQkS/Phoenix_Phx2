"""Stage 23.3 launch-structure observe-only filter.

This is the second concrete Stage 23 filter, landing under the
``LAUNCH_STRUCTURE`` filter family. The filter is pure: given a
``Stage23FilterInput`` it returns a ``Stage23FilterResult`` and
never touches the network, the clock, the environment, or
disk. Stage 23 is observe-only: the filter assigns a closed-set
label and a closed-set ``data_status`` plus a deterministic
tuple of reason codes; it never blocks, routes, or alerts.

This module is PHX2-native. It is NOT a reproduction of any
external launch-structure / bundle classifier and makes no
exact-parity claim against any prior implementation. The
filter emits bundle-like labels from deterministic synthetic
primitives carried on ``Stage23FilterInput.payload_summary``;
future calibration against ground truth is out of scope for
Stage 23.3.

Input shape:

  * Launch-window primitives are read out of
    ``filter_input.payload_summary`` by key. The Stage 23 input
    reader already enforces the payload-summary safety rules at
    ingest, so this filter consumes the projected mapping
    verbatim.
  * Recognized primitive keys (each optional):

      ``first_n_buyers_count``              -- int
      ``first_n_unique_buyers``             -- int
      ``first_n_unique_funders``            -- int
      ``same_slot_buyer_count``             -- int
      ``near_slot_buyer_count``             -- int
      ``buyer_source_cluster_count``        -- int
      ``largest_buyer_cluster_pct``         -- float in [0.0, 1.0]
      ``largest_funder_cluster_pct``        -- float in [0.0, 1.0]
      ``first_n_holder_concentration_pct``  -- float in [0.0, 1.0]
      ``repeated_source_wallet_count``      -- int
      ``repeated_buyer_wallet_count``       -- int
      ``launch_window_seconds``             -- int / float, non-negative
      ``launch_slot``                       -- int, non-negative
      ``observed_slot_span``                -- int, non-negative
      ``first_n_events_observed``           -- int, non-negative

  * Optional marker key ``launch_primitive_kind`` is recognized
    for ``"unsupported"`` -- the filter emits
    ``label=UNKNOWN`` / ``data_status=UNSUPPORTED`` with
    ``LAUNCH_PRIMITIVE_UNSUPPORTED`` when the upstream
    primitive family is unsupported for this token.

Output shape:

  * ``filter_name``       -- ``"launch_structure"``
  * ``filter_family``     -- ``"LAUNCH_STRUCTURE"``
  * ``filter_version``    -- ``"launch_structure_v0"``
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
    FILTER_FAMILY_LAUNCH_STRUCTURE,
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


FILTER_NAME: str = "launch_structure"
FILTER_VERSION: str = "launch_structure_v0"
THRESHOLD_VERSION: str = "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# Launch-window primitive keys (closed set)
# ---------------------------------------------------------------------------


PRIMITIVE_FIRST_N_BUYERS_COUNT: str = "first_n_buyers_count"
PRIMITIVE_FIRST_N_UNIQUE_BUYERS: str = "first_n_unique_buyers"
PRIMITIVE_FIRST_N_UNIQUE_FUNDERS: str = "first_n_unique_funders"
PRIMITIVE_SAME_SLOT_BUYER_COUNT: str = "same_slot_buyer_count"
PRIMITIVE_NEAR_SLOT_BUYER_COUNT: str = "near_slot_buyer_count"
PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT: str = "buyer_source_cluster_count"
PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT: str = "largest_buyer_cluster_pct"
PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT: str = "largest_funder_cluster_pct"
PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT: str = (
    "first_n_holder_concentration_pct"
)
PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT: str = "repeated_source_wallet_count"
PRIMITIVE_REPEATED_BUYER_WALLET_COUNT: str = "repeated_buyer_wallet_count"
PRIMITIVE_LAUNCH_WINDOW_SECONDS: str = "launch_window_seconds"
PRIMITIVE_LAUNCH_SLOT: str = "launch_slot"
PRIMITIVE_OBSERVED_SLOT_SPAN: str = "observed_slot_span"
PRIMITIVE_FIRST_N_EVENTS_OBSERVED: str = "first_n_events_observed"


LAUNCH_PRIMITIVE_KEYS: tuple[str, ...] = (
    PRIMITIVE_FIRST_N_BUYERS_COUNT,
    PRIMITIVE_FIRST_N_UNIQUE_BUYERS,
    PRIMITIVE_FIRST_N_UNIQUE_FUNDERS,
    PRIMITIVE_SAME_SLOT_BUYER_COUNT,
    PRIMITIVE_NEAR_SLOT_BUYER_COUNT,
    PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT,
    PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
    PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT,
    PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
    PRIMITIVE_REPEATED_BUYER_WALLET_COUNT,
    PRIMITIVE_LAUNCH_WINDOW_SECONDS,
    PRIMITIVE_LAUNCH_SLOT,
    PRIMITIVE_OBSERVED_SLOT_SPAN,
    PRIMITIVE_FIRST_N_EVENTS_OBSERVED,
)


# Primitives whose presence is the minimum bar for a non-INSUFFICIENT
# verdict. The filter needs at least one of these structural
# primitives to reason about the launch shape at all.
_REQUIRED_LAUNCH_PRIMITIVES: tuple[str, ...] = (
    PRIMITIVE_SAME_SLOT_BUYER_COUNT,
    PRIMITIVE_NEAR_SLOT_BUYER_COUNT,
    PRIMITIVE_FIRST_N_UNIQUE_BUYERS,
    PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
)


# Optional marker key the upstream artifact may carry to signal
# the launch-primitive family is unsupported for this token. The
# locked token vocabulary mirrors the Stage 23 closed-set
# discipline.
PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND: str = "launch_primitive_kind"
LAUNCH_PRIMITIVE_KIND_SUPPORTED: str = "supported"
LAUNCH_PRIMITIVE_KIND_UNSUPPORTED: str = "unsupported"


LAUNCH_PRIMITIVE_KIND_VALUES: tuple[str, ...] = (
    LAUNCH_PRIMITIVE_KIND_SUPPORTED,
    LAUNCH_PRIMITIVE_KIND_UNSUPPORTED,
)


# ---------------------------------------------------------------------------
# Reason codes (closed set, canonical declaration order)
# ---------------------------------------------------------------------------


REASON_LAUNCH_STRUCTURE_NORMAL: str = "LAUNCH_STRUCTURE_NORMAL"
REASON_SAME_SLOT_BUYER_CLUSTER: str = "SAME_SLOT_BUYER_CLUSTER"
REASON_NEAR_SLOT_BUYER_CLUSTER: str = "NEAR_SLOT_BUYER_CLUSTER"
REASON_LOW_UNIQUE_BUYER_COUNT: str = "LOW_UNIQUE_BUYER_COUNT"
REASON_LOW_UNIQUE_FUNDER_COUNT: str = "LOW_UNIQUE_FUNDER_COUNT"
REASON_BUYER_CLUSTER_CONCENTRATION_HIGH: str = (
    "BUYER_CLUSTER_CONCENTRATION_HIGH"
)
REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH: str = (
    "FUNDER_CLUSTER_CONCENTRATION_HIGH"
)
REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH: str = (
    "FIRST_N_HOLDER_CONCENTRATION_HIGH"
)
REASON_REPEATED_SOURCE_WALLETS: str = "REPEATED_SOURCE_WALLETS"
REASON_REPEATED_BUYER_WALLETS: str = "REPEATED_BUYER_WALLETS"
REASON_BUNDLE_LIKE_LAUNCH_PATTERN: str = "BUNDLE_LIKE_LAUNCH_PATTERN"
REASON_LAUNCH_WINDOW_MISSING: str = "LAUNCH_WINDOW_MISSING"
REASON_LAUNCH_WINDOW_PARTIAL: str = "LAUNCH_WINDOW_PARTIAL"
REASON_LAUNCH_WINDOW_TOO_SMALL: str = "LAUNCH_WINDOW_TOO_SMALL"
REASON_LAUNCH_PRIMITIVE_UNSUPPORTED: str = "LAUNCH_PRIMITIVE_UNSUPPORTED"
REASON_REQUIRED_LAUNCH_FEATURE_MISSING: str = (
    "REQUIRED_LAUNCH_FEATURE_MISSING"
)
REASON_INSUFFICIENT_LAUNCH_EVENTS: str = "INSUFFICIENT_LAUNCH_EVENTS"


# Canonical declaration ORDER for reason codes. The filter always
# emits its reason_codes tuple in this order regardless of the
# order it discovered each condition; this keeps evaluation_hash
# stable across re-runs.
LAUNCH_REASON_CODES: tuple[str, ...] = (
    REASON_LAUNCH_STRUCTURE_NORMAL,
    REASON_SAME_SLOT_BUYER_CLUSTER,
    REASON_NEAR_SLOT_BUYER_CLUSTER,
    REASON_LOW_UNIQUE_BUYER_COUNT,
    REASON_LOW_UNIQUE_FUNDER_COUNT,
    REASON_BUYER_CLUSTER_CONCENTRATION_HIGH,
    REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH,
    REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH,
    REASON_REPEATED_SOURCE_WALLETS,
    REASON_REPEATED_BUYER_WALLETS,
    REASON_BUNDLE_LIKE_LAUNCH_PATTERN,
    REASON_LAUNCH_WINDOW_MISSING,
    REASON_LAUNCH_WINDOW_PARTIAL,
    REASON_LAUNCH_WINDOW_TOO_SMALL,
    REASON_LAUNCH_PRIMITIVE_UNSUPPORTED,
    REASON_REQUIRED_LAUNCH_FEATURE_MISSING,
    REASON_INSUFFICIENT_LAUNCH_EVENTS,
)


# Pre-computed rank map for the deterministic reason-code ordering.
_REASON_RANK: Mapping[str, int] = MappingProxyType(
    {code: index for index, code in enumerate(LAUNCH_REASON_CODES)}
)


# ---------------------------------------------------------------------------
# Threshold placeholders (observe-only)
# ---------------------------------------------------------------------------
#
# These are NOT calibrated detection values. The
# ``threshold_version`` axis on every emitted result is locked to
# ``"thresholds_v0_observe_only"`` so downstream callers always see
# the placeholder posture.


SAME_SLOT_BUYER_ELEVATED_COUNT: int = 2
SAME_SLOT_BUYER_SUSPICIOUS_COUNT: int = 4
SAME_SLOT_BUYER_SCAM_LIKELY_COUNT: int = 6

NEAR_SLOT_BUYER_ELEVATED_COUNT: int = 4
NEAR_SLOT_BUYER_SUSPICIOUS_COUNT: int = 8

LOW_UNIQUE_BUYER_COUNT_THRESHOLD: int = 5
VERY_LOW_UNIQUE_BUYER_COUNT_THRESHOLD: int = 3

LOW_UNIQUE_FUNDER_COUNT_THRESHOLD: int = 5
VERY_LOW_UNIQUE_FUNDER_COUNT_THRESHOLD: int = 3

LARGEST_BUYER_CLUSTER_SUSPICIOUS_PCT: float = 0.40
LARGEST_BUYER_CLUSTER_SCAM_LIKELY_PCT: float = 0.70

LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT: float = 0.40
LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT: float = 0.70

FIRST_N_HOLDER_CONCENTRATION_SUSPICIOUS_PCT: float = 0.60
FIRST_N_HOLDER_CONCENTRATION_SCAM_LIKELY_PCT: float = 0.85

REPEATED_SOURCE_WALLET_THRESHOLD: int = 2
REPEATED_BUYER_WALLET_THRESHOLD: int = 2

LAUNCH_WINDOW_TOO_SMALL_SECONDS: float = 30.0
INSUFFICIENT_LAUNCH_EVENTS_THRESHOLD: int = 3

# Combined "bundle-like" signature: repeated source wallets +
# elevated largest-buyer-cluster percentage. Triggers the
# BUNDLE_LIKE_LAUNCH_PATTERN reason and escalates the verdict
# to at least SUSPICIOUS.
BUNDLE_LIKE_BUYER_CLUSTER_PCT: float = 0.30


# ---------------------------------------------------------------------------
# Internal projection helpers
# ---------------------------------------------------------------------------


class _LaunchStructureProjection(NamedTuple):
    """Internal projection of launch-window primitives from a payload_summary.

    Each field is either a numeric value (float or int) or
    ``None`` when the upstream payload_summary did not carry the
    primitive. The projection is immutable so downstream
    reasoning can not mutate it.
    """

    first_n_buyers_count: int | None
    first_n_unique_buyers: int | None
    first_n_unique_funders: int | None
    same_slot_buyer_count: int | None
    near_slot_buyer_count: int | None
    buyer_source_cluster_count: int | None
    largest_buyer_cluster_pct: float | None
    largest_funder_cluster_pct: float | None
    first_n_holder_concentration_pct: float | None
    repeated_source_wallet_count: int | None
    repeated_buyer_wallet_count: int | None
    launch_window_seconds: float | None
    launch_slot: int | None
    observed_slot_span: int | None
    first_n_events_observed: int | None
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
                "launch primitive value is non-finite (NaN / Infinity)"
            )
        return value
    return None


def _read_int(value: object) -> int | None:
    """Coerce a payload_summary value to a non-negative ``int`` when safe.

    Floats that are integral and non-negative are accepted (an
    upstream provider that emits ``5.0`` for a count is treated
    as ``5``). Negative values are rejected with
    ``Stage23ContractError`` because a negative launch-window
    count is contractually impossible.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value < 0:
            raise Stage23ContractError(
                "launch primitive integer value is negative"
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage23ContractError(
                "launch primitive value is non-finite (NaN / Infinity)"
            )
        if value < 0.0:
            raise Stage23ContractError(
                "launch primitive numeric value is negative"
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
            "launch primitive float value is negative"
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
            "launch percentage primitive is below 0.0"
        )
    if coerced > 1.0:
        raise Stage23ContractError(
            "launch percentage primitive is above 1.0"
        )
    return coerced


def _project_launch_structure(
    *,
    payload: Mapping[str, object],
) -> _LaunchStructureProjection:
    """Project the launch-structure primitives out of ``payload``."""
    first_n_buyers_count = _read_int(
        payload.get(PRIMITIVE_FIRST_N_BUYERS_COUNT)
    )
    first_n_unique_buyers = _read_int(
        payload.get(PRIMITIVE_FIRST_N_UNIQUE_BUYERS)
    )
    first_n_unique_funders = _read_int(
        payload.get(PRIMITIVE_FIRST_N_UNIQUE_FUNDERS)
    )
    same_slot_buyer_count = _read_int(
        payload.get(PRIMITIVE_SAME_SLOT_BUYER_COUNT)
    )
    near_slot_buyer_count = _read_int(
        payload.get(PRIMITIVE_NEAR_SLOT_BUYER_COUNT)
    )
    buyer_source_cluster_count = _read_int(
        payload.get(PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT)
    )
    largest_buyer_cluster_pct = _read_pct(
        payload.get(PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT)
    )
    largest_funder_cluster_pct = _read_pct(
        payload.get(PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT)
    )
    first_n_holder_concentration_pct = _read_pct(
        payload.get(PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT)
    )
    repeated_source_wallet_count = _read_int(
        payload.get(PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT)
    )
    repeated_buyer_wallet_count = _read_int(
        payload.get(PRIMITIVE_REPEATED_BUYER_WALLET_COUNT)
    )
    launch_window_seconds = _read_non_negative_float(
        payload.get(PRIMITIVE_LAUNCH_WINDOW_SECONDS)
    )
    launch_slot = _read_int(payload.get(PRIMITIVE_LAUNCH_SLOT))
    observed_slot_span = _read_int(payload.get(PRIMITIVE_OBSERVED_SLOT_SPAN))
    first_n_events_observed = _read_int(
        payload.get(PRIMITIVE_FIRST_N_EVENTS_OBSERVED)
    )

    marker_raw = payload.get(PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND)
    if marker_raw is not None and marker_raw not in LAUNCH_PRIMITIVE_KIND_VALUES:
        raise Stage23ContractError(
            "launch_primitive_kind marker carries a non-closed-set value"
        )
    is_marked_unsupported = (
        isinstance(marker_raw, str)
        and marker_raw == LAUNCH_PRIMITIVE_KIND_UNSUPPORTED
    )

    raw_values: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_FIRST_N_BUYERS_COUNT, first_n_buyers_count),
        (PRIMITIVE_FIRST_N_UNIQUE_BUYERS, first_n_unique_buyers),
        (PRIMITIVE_FIRST_N_UNIQUE_FUNDERS, first_n_unique_funders),
        (PRIMITIVE_SAME_SLOT_BUYER_COUNT, same_slot_buyer_count),
        (PRIMITIVE_NEAR_SLOT_BUYER_COUNT, near_slot_buyer_count),
        (PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT, buyer_source_cluster_count),
        (PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT, largest_buyer_cluster_pct),
        (PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT, largest_funder_cluster_pct),
        (
            PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
            first_n_holder_concentration_pct,
        ),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
            repeated_source_wallet_count,
        ),
        (PRIMITIVE_REPEATED_BUYER_WALLET_COUNT, repeated_buyer_wallet_count),
        (PRIMITIVE_LAUNCH_WINDOW_SECONDS, launch_window_seconds),
        (PRIMITIVE_LAUNCH_SLOT, launch_slot),
        (PRIMITIVE_OBSERVED_SLOT_SPAN, observed_slot_span),
        (PRIMITIVE_FIRST_N_EVENTS_OBSERVED, first_n_events_observed),
    )
    missing_keys = tuple(
        sorted(key for key, val in raw_values if val is None)
    )

    return _LaunchStructureProjection(
        first_n_buyers_count=first_n_buyers_count,
        first_n_unique_buyers=first_n_unique_buyers,
        first_n_unique_funders=first_n_unique_funders,
        same_slot_buyer_count=same_slot_buyer_count,
        near_slot_buyer_count=near_slot_buyer_count,
        buyer_source_cluster_count=buyer_source_cluster_count,
        largest_buyer_cluster_pct=largest_buyer_cluster_pct,
        largest_funder_cluster_pct=largest_funder_cluster_pct,
        first_n_holder_concentration_pct=first_n_holder_concentration_pct,
        repeated_source_wallet_count=repeated_source_wallet_count,
        repeated_buyer_wallet_count=repeated_buyer_wallet_count,
        launch_window_seconds=launch_window_seconds,
        launch_slot=launch_slot,
        observed_slot_span=observed_slot_span,
        first_n_events_observed=first_n_events_observed,
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
    projection: _LaunchStructureProjection,
) -> Mapping[str, object]:
    """Build the immutable numeric_features mapping the result carries."""
    out: dict[str, object] = {}
    pairs: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_FIRST_N_BUYERS_COUNT, projection.first_n_buyers_count),
        (PRIMITIVE_FIRST_N_UNIQUE_BUYERS, projection.first_n_unique_buyers),
        (
            PRIMITIVE_FIRST_N_UNIQUE_FUNDERS,
            projection.first_n_unique_funders,
        ),
        (PRIMITIVE_SAME_SLOT_BUYER_COUNT, projection.same_slot_buyer_count),
        (PRIMITIVE_NEAR_SLOT_BUYER_COUNT, projection.near_slot_buyer_count),
        (
            PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT,
            projection.buyer_source_cluster_count,
        ),
        (
            PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
            projection.largest_buyer_cluster_pct,
        ),
        (
            PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT,
            projection.largest_funder_cluster_pct,
        ),
        (
            PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
            projection.first_n_holder_concentration_pct,
        ),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
            projection.repeated_source_wallet_count,
        ),
        (
            PRIMITIVE_REPEATED_BUYER_WALLET_COUNT,
            projection.repeated_buyer_wallet_count,
        ),
        (PRIMITIVE_LAUNCH_WINDOW_SECONDS, projection.launch_window_seconds),
        (PRIMITIVE_LAUNCH_SLOT, projection.launch_slot),
        (PRIMITIVE_OBSERVED_SLOT_SPAN, projection.observed_slot_span),
        (
            PRIMITIVE_FIRST_N_EVENTS_OBSERVED,
            projection.first_n_events_observed,
        ),
    )
    for key, value in pairs:
        if value is None:
            continue
        out[key] = value
    return MappingProxyType(out)


def _has_any_launch_primitive(
    projection: _LaunchStructureProjection,
) -> bool:
    return any(
        getattr(projection, attr) is not None
        for attr in (
            "first_n_buyers_count",
            "first_n_unique_buyers",
            "first_n_unique_funders",
            "same_slot_buyer_count",
            "near_slot_buyer_count",
            "buyer_source_cluster_count",
            "largest_buyer_cluster_pct",
            "largest_funder_cluster_pct",
            "first_n_holder_concentration_pct",
            "repeated_source_wallet_count",
            "repeated_buyer_wallet_count",
            "launch_window_seconds",
            "launch_slot",
            "observed_slot_span",
            "first_n_events_observed",
        )
    )


def _has_required_launch_primitive(
    projection: _LaunchStructureProjection,
) -> bool:
    name_attr_map = {
        PRIMITIVE_SAME_SLOT_BUYER_COUNT: "same_slot_buyer_count",
        PRIMITIVE_NEAR_SLOT_BUYER_COUNT: "near_slot_buyer_count",
        PRIMITIVE_FIRST_N_UNIQUE_BUYERS: "first_n_unique_buyers",
        PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT: "largest_buyer_cluster_pct",
    }
    return any(
        getattr(projection, name_attr_map[key]) is not None
        for key in _REQUIRED_LAUNCH_PRIMITIVES
    )


# ---------------------------------------------------------------------------
# Severity verdict
# ---------------------------------------------------------------------------


def _classify_severity(
    projection: _LaunchStructureProjection,
) -> tuple[str, tuple[str, ...]]:
    """Compute the severity label + reason codes for a launch snapshot.

    Caller has already ensured at least one of the required
    launch primitives is present.
    """
    label = LABEL_NORMAL
    reasons: list[str] = []

    same_slot = projection.same_slot_buyer_count
    if same_slot is not None:
        if same_slot >= SAME_SLOT_BUYER_SCAM_LIKELY_COUNT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_SAME_SLOT_BUYER_CLUSTER)
        elif same_slot >= SAME_SLOT_BUYER_SUSPICIOUS_COUNT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_SAME_SLOT_BUYER_CLUSTER)
        elif same_slot >= SAME_SLOT_BUYER_ELEVATED_COUNT:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_SAME_SLOT_BUYER_CLUSTER)

    near_slot = projection.near_slot_buyer_count
    if near_slot is not None:
        if near_slot >= NEAR_SLOT_BUYER_SUSPICIOUS_COUNT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_NEAR_SLOT_BUYER_CLUSTER)
        elif near_slot >= NEAR_SLOT_BUYER_ELEVATED_COUNT:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_NEAR_SLOT_BUYER_CLUSTER)

    unique_buyers = projection.first_n_unique_buyers
    if unique_buyers is not None:
        if unique_buyers <= VERY_LOW_UNIQUE_BUYER_COUNT_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_LOW_UNIQUE_BUYER_COUNT)
        elif unique_buyers < LOW_UNIQUE_BUYER_COUNT_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_LOW_UNIQUE_BUYER_COUNT)

    unique_funders = projection.first_n_unique_funders
    if unique_funders is not None:
        if unique_funders <= VERY_LOW_UNIQUE_FUNDER_COUNT_THRESHOLD:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_LOW_UNIQUE_FUNDER_COUNT)
        elif unique_funders < LOW_UNIQUE_FUNDER_COUNT_THRESHOLD:
            label = _escalate(label, LABEL_ELEVATED)
            reasons.append(REASON_LOW_UNIQUE_FUNDER_COUNT)

    largest_buyer = projection.largest_buyer_cluster_pct
    if largest_buyer is not None:
        if largest_buyer >= LARGEST_BUYER_CLUSTER_SCAM_LIKELY_PCT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_BUYER_CLUSTER_CONCENTRATION_HIGH)
        elif largest_buyer >= LARGEST_BUYER_CLUSTER_SUSPICIOUS_PCT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_BUYER_CLUSTER_CONCENTRATION_HIGH)

    largest_funder = projection.largest_funder_cluster_pct
    if largest_funder is not None:
        if largest_funder >= LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH)
        elif largest_funder >= LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH)

    first_n_concentration = projection.first_n_holder_concentration_pct
    if first_n_concentration is not None:
        if first_n_concentration >= FIRST_N_HOLDER_CONCENTRATION_SCAM_LIKELY_PCT:
            label = _escalate(label, LABEL_SCAM_LIKELY)
            reasons.append(REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH)
        elif first_n_concentration >= FIRST_N_HOLDER_CONCENTRATION_SUSPICIOUS_PCT:
            label = _escalate(label, LABEL_SUSPICIOUS)
            reasons.append(REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH)

    repeated_sources = projection.repeated_source_wallet_count
    if (
        repeated_sources is not None
        and repeated_sources >= REPEATED_SOURCE_WALLET_THRESHOLD
    ):
        label = _escalate(label, LABEL_SUSPICIOUS)
        reasons.append(REASON_REPEATED_SOURCE_WALLETS)

    repeated_buyers = projection.repeated_buyer_wallet_count
    if (
        repeated_buyers is not None
        and repeated_buyers >= REPEATED_BUYER_WALLET_THRESHOLD
    ):
        label = _escalate(label, LABEL_ELEVATED)
        reasons.append(REASON_REPEATED_BUYER_WALLETS)

    # Bundle-like detection: repeated source wallets paired with
    # an elevated largest-buyer-cluster percentage. This is the
    # composite signature; a single contributing primitive does
    # NOT trigger the bundle-like reason on its own.
    bundle_like_repeated_sources = (
        repeated_sources is not None
        and repeated_sources >= REPEATED_SOURCE_WALLET_THRESHOLD
    )
    bundle_like_cluster = (
        largest_buyer is not None
        and largest_buyer >= BUNDLE_LIKE_BUYER_CLUSTER_PCT
    )
    if bundle_like_repeated_sources and bundle_like_cluster:
        label = _escalate(label, LABEL_SUSPICIOUS)
        reasons.append(REASON_BUNDLE_LIKE_LAUNCH_PATTERN)

    # Extreme combination escalation: same-slot clustering paired
    # with repeated source wallets paired with very high first-N
    # holder concentration. This is the most severe composite
    # signature; it escalates to SCAM_LIKELY.
    extreme_same_slot = (
        same_slot is not None
        and same_slot >= SAME_SLOT_BUYER_SUSPICIOUS_COUNT
    )
    extreme_first_n_concentration = (
        first_n_concentration is not None
        and first_n_concentration
        >= FIRST_N_HOLDER_CONCENTRATION_SCAM_LIKELY_PCT
    )
    if (
        extreme_same_slot
        and bundle_like_repeated_sources
        and extreme_first_n_concentration
    ):
        label = _escalate(label, LABEL_SCAM_LIKELY)
        if REASON_BUNDLE_LIKE_LAUNCH_PATTERN not in reasons:
            reasons.append(REASON_BUNDLE_LIKE_LAUNCH_PATTERN)

    if not reasons:
        reasons.append(REASON_LAUNCH_STRUCTURE_NORMAL)

    return label, tuple(reasons)


# ---------------------------------------------------------------------------
# Public filter surface
# ---------------------------------------------------------------------------


def evaluate(
    *,
    filter_input: Stage23FilterInput,
) -> Stage23FilterResult:
    """Evaluate the launch-structure filter for one input.

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

    projection = _project_launch_structure(payload=payload)
    numeric_features = _build_numeric_features(projection)

    if projection.is_marked_unsupported:
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_LAUNCH_STRUCTURE,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_UNKNOWN,
            data_status=DATA_STATUS_UNSUPPORTED,
            reason_codes=(REASON_LAUNCH_PRIMITIVE_UNSUPPORTED,),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    if not _has_any_launch_primitive(projection):
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_LAUNCH_STRUCTURE,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=LABEL_MISSING_INPUT,
            data_status=DATA_STATUS_MISSING,
            reason_codes=(REASON_LAUNCH_WINDOW_MISSING,),
            numeric_features=numeric_features,
            missing_features=projection.missing_primitive_keys,
        )

    launch_window_seconds = projection.launch_window_seconds
    launch_window_too_small = (
        launch_window_seconds is not None
        and launch_window_seconds < LAUNCH_WINDOW_TOO_SMALL_SECONDS
    )

    first_n_events_observed = projection.first_n_events_observed
    insufficient_events = (
        first_n_events_observed is not None
        and first_n_events_observed < INSUFFICIENT_LAUNCH_EVENTS_THRESHOLD
    )

    if insufficient_events:
        reasons = [REASON_INSUFFICIENT_LAUNCH_EVENTS]
        if launch_window_too_small:
            reasons.append(REASON_LAUNCH_WINDOW_TOO_SMALL)
        if projection.missing_primitive_keys:
            reasons.append(REASON_LAUNCH_WINDOW_PARTIAL)
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_LAUNCH_STRUCTURE,
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

    if not _has_required_launch_primitive(projection):
        reasons = [
            REASON_REQUIRED_LAUNCH_FEATURE_MISSING,
            REASON_LAUNCH_WINDOW_PARTIAL,
        ]
        if launch_window_too_small:
            reasons.append(REASON_LAUNCH_WINDOW_TOO_SMALL)
        return build_filter_result(
            filter_name=FILTER_NAME,
            filter_family=FILTER_FAMILY_LAUNCH_STRUCTURE,
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
        reasons_accum.append(REASON_LAUNCH_WINDOW_PARTIAL)
    if launch_window_too_small:
        reasons_accum.append(REASON_LAUNCH_WINDOW_TOO_SMALL)
        # A too-small launch window is a contributing signal --
        # it nudges the label off NORMAL but does not push past
        # ELEVATED on its own.
        label = _escalate(label, LABEL_ELEVATED)
        # If the severity classifier had nothing to say, replace
        # the placeholder NORMAL reason with the window signal so
        # the reason set stays meaningful.
        if (
            label == LABEL_ELEVATED
            and reasons_accum
            and reasons_accum[0] == REASON_LAUNCH_STRUCTURE_NORMAL
        ):
            reasons_accum = [
                code
                for code in reasons_accum
                if code != REASON_LAUNCH_STRUCTURE_NORMAL
            ]

    data_status = (
        DATA_STATUS_PARTIAL
        if projection.missing_primitive_keys
        else DATA_STATUS_COMPLETE
    )

    return build_filter_result(
        filter_name=FILTER_NAME,
        filter_family=FILTER_FAMILY_LAUNCH_STRUCTURE,
        filter_version=FILTER_VERSION,
        threshold_version=THRESHOLD_VERSION,
        label=label,
        data_status=data_status,
        reason_codes=_sort_reason_codes(tuple(reasons_accum)),
        numeric_features=numeric_features,
        missing_features=projection.missing_primitive_keys,
    )


class LaunchStructureFilter:
    """Class-shaped surface satisfying the ``Stage23Filter`` Protocol.

    The class wraps the pure ``evaluate`` function so callers
    that prefer a Protocol-shaped instance (Stage 23.5 runners
    in particular) can construct one without losing the pure
    function's testability.
    """

    filter_name: str = FILTER_NAME
    filter_family: str = FILTER_FAMILY_LAUNCH_STRUCTURE
    filter_version: str = FILTER_VERSION
    threshold_version: str = THRESHOLD_VERSION

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult:
        return evaluate(filter_input=filter_input)


__all__ = [
    "BUNDLE_LIKE_BUYER_CLUSTER_PCT",
    "FILTER_NAME",
    "FILTER_VERSION",
    "FIRST_N_HOLDER_CONCENTRATION_SCAM_LIKELY_PCT",
    "FIRST_N_HOLDER_CONCENTRATION_SUSPICIOUS_PCT",
    "INSUFFICIENT_LAUNCH_EVENTS_THRESHOLD",
    "LARGEST_BUYER_CLUSTER_SCAM_LIKELY_PCT",
    "LARGEST_BUYER_CLUSTER_SUSPICIOUS_PCT",
    "LARGEST_FUNDER_CLUSTER_SCAM_LIKELY_PCT",
    "LARGEST_FUNDER_CLUSTER_SUSPICIOUS_PCT",
    "LAUNCH_PRIMITIVE_KEYS",
    "LAUNCH_PRIMITIVE_KIND_SUPPORTED",
    "LAUNCH_PRIMITIVE_KIND_UNSUPPORTED",
    "LAUNCH_PRIMITIVE_KIND_VALUES",
    "LAUNCH_REASON_CODES",
    "LAUNCH_WINDOW_TOO_SMALL_SECONDS",
    "LaunchStructureFilter",
    "LOW_UNIQUE_BUYER_COUNT_THRESHOLD",
    "LOW_UNIQUE_FUNDER_COUNT_THRESHOLD",
    "NEAR_SLOT_BUYER_ELEVATED_COUNT",
    "NEAR_SLOT_BUYER_SUSPICIOUS_COUNT",
    "PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND",
    "PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT",
    "PRIMITIVE_FIRST_N_BUYERS_COUNT",
    "PRIMITIVE_FIRST_N_EVENTS_OBSERVED",
    "PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT",
    "PRIMITIVE_FIRST_N_UNIQUE_BUYERS",
    "PRIMITIVE_FIRST_N_UNIQUE_FUNDERS",
    "PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT",
    "PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT",
    "PRIMITIVE_LAUNCH_SLOT",
    "PRIMITIVE_LAUNCH_WINDOW_SECONDS",
    "PRIMITIVE_NEAR_SLOT_BUYER_COUNT",
    "PRIMITIVE_OBSERVED_SLOT_SPAN",
    "PRIMITIVE_REPEATED_BUYER_WALLET_COUNT",
    "PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT",
    "PRIMITIVE_SAME_SLOT_BUYER_COUNT",
    "REASON_BUNDLE_LIKE_LAUNCH_PATTERN",
    "REASON_BUYER_CLUSTER_CONCENTRATION_HIGH",
    "REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH",
    "REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH",
    "REASON_INSUFFICIENT_LAUNCH_EVENTS",
    "REASON_LAUNCH_PRIMITIVE_UNSUPPORTED",
    "REASON_LAUNCH_STRUCTURE_NORMAL",
    "REASON_LAUNCH_WINDOW_MISSING",
    "REASON_LAUNCH_WINDOW_PARTIAL",
    "REASON_LAUNCH_WINDOW_TOO_SMALL",
    "REASON_LOW_UNIQUE_BUYER_COUNT",
    "REASON_LOW_UNIQUE_FUNDER_COUNT",
    "REASON_NEAR_SLOT_BUYER_CLUSTER",
    "REASON_REPEATED_BUYER_WALLETS",
    "REASON_REPEATED_SOURCE_WALLETS",
    "REASON_REQUIRED_LAUNCH_FEATURE_MISSING",
    "REASON_SAME_SLOT_BUYER_CLUSTER",
    "REPEATED_BUYER_WALLET_THRESHOLD",
    "REPEATED_SOURCE_WALLET_THRESHOLD",
    "SAME_SLOT_BUYER_ELEVATED_COUNT",
    "SAME_SLOT_BUYER_SCAM_LIKELY_COUNT",
    "SAME_SLOT_BUYER_SUSPICIOUS_COUNT",
    "THRESHOLD_VERSION",
    "VERY_LOW_UNIQUE_BUYER_COUNT_THRESHOLD",
    "VERY_LOW_UNIQUE_FUNDER_COUNT_THRESHOLD",
    "evaluate",
]
