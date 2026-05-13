"""Stage 15 safety gate.

Centralizes the safety invariants every Stage 15 artifact must carry.
These flags are written defensively into every output and asserted
before any artifact is emitted, so a regression in writer.py or a
future caller can't accidentally produce an artifact that claims to
be runtime-consumable.

The reconciler's A01-A04 gating is per-row and lives in reconciler.py.
This module is the single source of truth for the *artifact-level*
safety surface (runtime_consumable=false, hard_block_allowed=false,
intended_action_set=["LOG_WOULD_BLOCK"], etc.).
"""

from __future__ import annotations

from typing import Any


# Artifact-level safety surface. Identical for clean and validation-
# failed runs at the top-level invariants; only safe_for_observe_only_wiring
# flips based on whether a draft was actually written.
SAFETY_SURFACE: dict[str, Any] = {
    "runtime_consumable": False,
    "observe_only_runtime_consumable": False,
    "hard_block_allowed": False,
    "safe_for_live_enforcement": False,
    "safe_for_hard_blocking": False,
    "enforcement_mode": "NONE",
    "intended_action_set": ("LOG_WOULD_BLOCK",),
}

# Per-rule safety constants.
RULE_INTENDED_ACTION = "LOG_WOULD_BLOCK"
RULE_HARD_BLOCK_ALLOWED = False

# Approval-draft schema constants.
DRAFT_SCHEMA_VERSION = "stage15_approval_draft_v0"
MANIFEST_SCHEMA_VERSION = "stage15_manifest_v0"
DRAFT_APPROVAL_STATUS = "OPERATOR_APPROVED_DRAFT"

# Manifest approval_status values (closed set).
MANIFEST_APPROVED = "APPROVED_DRAFT_WRITTEN"
MANIFEST_VALIDATION_FAILED = "VALIDATION_FAILED"
MANIFEST_STATUS_VALUES: frozenset[str] = frozenset({
    MANIFEST_APPROVED,
    MANIFEST_VALIDATION_FAILED,
})


def assert_draft_safety_invariants(draft: dict[str, Any]) -> None:
    """Defensive pre-write check on approved_observe_only_policy_draft.json.

    Raises AssertionError if any safety invariant is violated. The
    writer calls this immediately before emitting the JSON; any
    violation is a programmer error in Stage 15 itself (the spec says
    no Stage 15 output may ever contain a true safety flag), so an
    AssertionError surfaces it loudly during testing rather than
    silently emitting an unsafe artifact.
    """

    if draft.get("runtime_consumable") is not False:
        raise AssertionError("draft.runtime_consumable must be False")
    if draft.get("observe_only_runtime_consumable") is not False:
        raise AssertionError(
            "draft.observe_only_runtime_consumable must be False"
        )
    if draft.get("hard_block_allowed") is not False:
        raise AssertionError("draft.hard_block_allowed must be False")
    if draft.get("safe_for_live_enforcement") is not False:
        raise AssertionError("draft.safe_for_live_enforcement must be False")
    if draft.get("safe_for_hard_blocking") is not False:
        raise AssertionError("draft.safe_for_hard_blocking must be False")
    if draft.get("safe_for_observe_only_wiring") is not True:
        raise AssertionError(
            "draft.safe_for_observe_only_wiring must be True when a draft is written"
        )
    if draft.get("enforcement_mode") != "NONE":
        raise AssertionError("draft.enforcement_mode must be 'NONE'")
    intended = draft.get("intended_action_set")
    if intended != ["LOG_WOULD_BLOCK"]:
        raise AssertionError(
            f"draft.intended_action_set must be ['LOG_WOULD_BLOCK']; "
            f"got {intended!r}"
        )

    for rule in draft.get("rules", []):
        if rule.get("hard_block_allowed") is not False:
            raise AssertionError(
                f"draft rule {rule.get('rule_id')!r} hard_block_allowed must "
                f"be False"
            )
        if rule.get("intended_action_if_wired") != RULE_INTENDED_ACTION:
            raise AssertionError(
                f"draft rule {rule.get('rule_id')!r} intended_action_if_wired "
                f"must be {RULE_INTENDED_ACTION!r}"
            )
        if rule.get("operator_decision") != "APPROVE_OBSERVE_ONLY":
            raise AssertionError(
                f"draft rule {rule.get('rule_id')!r} operator_decision must "
                f"be 'APPROVE_OBSERVE_ONLY' (writer should have excluded "
                f"any other state)"
            )
