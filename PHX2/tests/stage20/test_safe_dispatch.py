"""Tests for SAFE_FOR_LIVE_DISPATCH defensive check (20.1.C).

E2022 fires if the constant is ever flipped to True. The
defensive check is invoked by validate_inputs in 20.1.D as a
runtime guard.
"""

from __future__ import annotations

from PHX2.stage20 import constants
from PHX2.stage20.constants import EligibilityErrorCode
from PHX2.stage20.input_validators import (
    defensive_check_safe_for_live_dispatch,
)


def test_safe_for_live_dispatch_false_passes():
    errors = defensive_check_safe_for_live_dispatch()
    assert errors == []


def test_safe_for_live_dispatch_true_triggers_e2022(monkeypatch):
    monkeypatch.setattr(constants, "SAFE_FOR_LIVE_DISPATCH", True)
    errors = defensive_check_safe_for_live_dispatch()
    assert EligibilityErrorCode.E2022 in errors
