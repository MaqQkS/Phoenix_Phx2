"""Phase 6: dense R03 / R04 coverage on the safety surface and tampered body."""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.observe_only_policy_loader import ObserveOnlyPolicyLoader
from PHX2.tests.stage16a.fixtures.builders import make_runtime_artifact_path


def _load_and_expect(path: Path, code: str) -> None:
    with pytest.raises(Stage16AError) as info:
        ObserveOnlyPolicyLoader().load(path)
    assert info.value.code == code, (
        f"expected {code}, got {info.value.code}: {info.value}"
    )


CLEAN_SURFACE = {
    "enforcement_mode": "OBSERVE_ONLY",
    "hard_block_allowed": False,
    "safe_for_live_enforcement": False,
    "safe_for_hard_blocking": False,
    "runtime_consumable": True,
    "observe_only_runtime_consumable": True,
    "allowed_action_set": ["LOG_WOULD_BLOCK"],
}


def _surface(**override):
    out = dict(CLEAN_SURFACE)
    out.update(override)
    return out


# ---------------------------------------------------------------------------
# R03: any deviation from the runtime safety surface is rejected
# ---------------------------------------------------------------------------


def test_R03_hard_block_allowed_true(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(hard_block_allowed=True)
    )
    _load_and_expect(path, "R03")


def test_R03_safe_for_live_enforcement_true(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(safe_for_live_enforcement=True)
    )
    _load_and_expect(path, "R03")


def test_R03_safe_for_hard_blocking_true(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(safe_for_hard_blocking=True)
    )
    _load_and_expect(path, "R03")


@pytest.mark.parametrize("mode", ["BLOCK", "ENFORCE", "NONE", "DRY_RUN", ""])
def test_R03_enforcement_mode_anything_but_observe_only(
    tmp_path: Path, mode: str
) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(enforcement_mode=mode)
    )
    _load_and_expect(path, "R03")


def test_R03_allowed_action_set_includes_hard_block(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path,
        safety_surface_override=_surface(
            allowed_action_set=["LOG_WOULD_BLOCK", "HARD_BLOCK"]
        ),
    )
    _load_and_expect(path, "R03")


def test_R03_allowed_action_set_empty(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(allowed_action_set=[])
    )
    _load_and_expect(path, "R03")


def test_R03_allowed_action_set_single_block(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(allowed_action_set=["BLOCK"])
    )
    _load_and_expect(path, "R03")


def test_R03_runtime_consumable_false(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, safety_surface_override=_surface(runtime_consumable=False)
    )
    _load_and_expect(path, "R03")


def test_R03_observe_only_runtime_consumable_false(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path,
        safety_surface_override=_surface(observe_only_runtime_consumable=False),
    )
    _load_and_expect(path, "R03")


def test_R03_extra_safety_key_rejected_under_exact_match(tmp_path: Path) -> None:
    """Stage 16A runtime safety_surface is EXACT-matched; unknown extras
    must be rejected (in contrast to Stage 15's subset-match for the
    input surface)."""

    path = make_runtime_artifact_path(
        tmp_path,
        safety_surface_override={**CLEAN_SURFACE, "future_field": "drift"},
    )
    _load_and_expect(path, "R03")


# ---------------------------------------------------------------------------
# R04: single-byte tamper on the body must invalidate the hash
# ---------------------------------------------------------------------------


def test_R04_single_byte_tamper_in_serialized_body(tmp_path: Path) -> None:
    """Write a clean artifact, flip one byte in the rendered JSON, and
    verify R04 fires (not R01 / R02)."""

    path = make_runtime_artifact_path(tmp_path)
    raw = path.read_bytes()
    # Find a byte we can flip without breaking JSON structure. Flip a
    # digit inside the generated_at_utc ISO string.
    flipped = raw.replace(b'"2026-05-13T12:00:00', b'"2027-05-13T12:00:00')
    assert flipped != raw, "test fixture must contain the target substring"
    path.write_bytes(flipped)
    _load_and_expect(path, "R04")
