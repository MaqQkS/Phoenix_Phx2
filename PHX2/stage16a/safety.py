"""Stage 16A safety-surface constants: the single source of truth for what a
valid Stage 15 input and Stage 16A runtime artifact look like.

Two match styles, per Step 0 locked remediation #6:

* Stage 15 input (manifest + draft): SUBSET match. Stage 15 may carry
  additional top-level fields (e.g. ``runtime_consumable_scope``) that
  Stage 16A does not enumerate. The named safety keys must be present
  with the expected values; extras are ignored.

* Stage 16A runtime artifact: EXACT match. No extras allowed; no missing
  keys allowed. The runtime artifact's safety_surface block must match
  ``EXPECTED_RUNTIME_SAFETY_SURFACE`` verbatim.

Tuples are used inside the constants for immutability at the Python level.
JSON lists are normalized to tuples during comparison so a list-from-JSON
compares equal to a tuple-in-constant.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from PHX2.stage16a.errors import Stage16AError


# ---------------------------------------------------------------------------
# Allowed value sets (used by load-time predicate validation)
# ---------------------------------------------------------------------------

ALLOWED_TIER_SCOPES: frozenset[str] = frozenset({"T1", "T2", "T3"})

ALLOWED_FILTER_LABELS: frozenset[str] = frozenset({
    "NORMAL",
    "ELEVATED",
    "SUSPICIOUS",
    "SCAM_LIKELY",
    "UNKNOWN",
})


# ---------------------------------------------------------------------------
# Predicate-key sets (per locked Step 0 remediation: 5 keys, no direction /
# policy_surface). Stage 15 already trims its draft predicate to these 5
# keys; Stage 16A's runtime predicate carries the same 5 keys.
# ---------------------------------------------------------------------------

REQUIRED_PREDICATE_KEYS_STAGE15: frozenset[str] = frozenset({
    "tier_scope",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
})

REQUIRED_PREDICATE_KEYS_RUNTIME: frozenset[str] = REQUIRED_PREDICATE_KEYS_STAGE15


# ---------------------------------------------------------------------------
# Stage 15 manifest top-level safety surface (subset-matched)
# ---------------------------------------------------------------------------

EXPECTED_STAGE15_SAFETY_SURFACE: Mapping[str, Any] = MappingProxyType({
    "hard_block_allowed": False,
    "safe_for_live_enforcement": False,
    "safe_for_hard_blocking": False,
    "runtime_consumable": False,
    "observe_only_runtime_consumable": False,
    "safe_for_observe_only_wiring": True,
    "enforcement_mode": "NONE",
})


# ---------------------------------------------------------------------------
# Stage 15 draft top-level safety surface (subset-matched)
# ---------------------------------------------------------------------------

EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE: Mapping[str, Any] = MappingProxyType({
    **EXPECTED_STAGE15_SAFETY_SURFACE,
    "intended_action_set": ("LOG_WOULD_BLOCK",),
    "approval_status": "OPERATOR_APPROVED_DRAFT",
})


# ---------------------------------------------------------------------------
# Stage 16A runtime artifact safety surface (EXACT-matched)
# ---------------------------------------------------------------------------

EXPECTED_RUNTIME_SAFETY_SURFACE: Mapping[str, Any] = MappingProxyType({
    "enforcement_mode": "OBSERVE_ONLY",
    "hard_block_allowed": False,
    "safe_for_live_enforcement": False,
    "safe_for_hard_blocking": False,
    "runtime_consumable": True,
    "observe_only_runtime_consumable": True,
    "allowed_action_set": ("LOG_WOULD_BLOCK",),
})


# ---------------------------------------------------------------------------
# Match helpers
# ---------------------------------------------------------------------------


def _normalize(value: Any) -> Any:
    """Normalize a value for safety-surface comparison.

    Recursively converts lists to tuples so a JSON-loaded list compares
    equal to a tuple constant in the Stage 16A safety dicts. Dicts are
    walked into; scalars pass through unchanged.
    """

    if isinstance(value, (list, tuple)):
        return tuple(_normalize(v) for v in value)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def assert_subset_match(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    code: str,
    context: str = "",
) -> None:
    """Assert every key in ``expected`` is present in ``actual`` with the
    expected value. Extra keys in ``actual`` are permitted (subset match).

    Used for Stage 15 manifest and draft safety-surface validation.
    Raises ``Stage16AError(code)`` on the first divergence; the detail
    string names the offending field.
    """

    for key, want in expected.items():
        if key not in actual:
            detail = (
                f"{context}: missing key {key!r}"
                if context
                else f"missing key {key!r}"
            )
            raise Stage16AError(code, detail)
        got = actual[key]
        if _normalize(want) != _normalize(got):
            detail = (
                f"{context}: field {key!r} expected {want!r}, got {got!r}"
                if context
                else f"field {key!r} expected {want!r}, got {got!r}"
            )
            raise Stage16AError(code, detail)


def assert_exact_match(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    code: str,
    context: str = "",
) -> None:
    """Assert ``actual`` has exactly the same keys and values as ``expected``.

    Used for Stage 16A runtime artifact safety-surface validation. Raises
    ``Stage16AError(code)`` on extra keys, missing keys, or value
    mismatches.
    """

    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    extra = actual_keys - expected_keys
    if extra:
        detail = (
            f"{context}: unexpected keys {sorted(extra)!r}"
            if context
            else f"unexpected keys {sorted(extra)!r}"
        )
        raise Stage16AError(code, detail)
    assert_subset_match(expected, actual, code=code, context=context)
