"""Tests for Stage 20 errors module (20.1.A).

Covers Stage20ValidationError construction, code validation,
and message-template coverage. Mirrors the Stage 19 errors-test
pattern.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.constants import EligibilityErrorCode
from PHX2.stage20.errors import ERROR_MESSAGE_TEMPLATES, Stage20ValidationError


def test_constructor_accepts_enum_code():
    err = Stage20ValidationError(EligibilityErrorCode.E2001)
    assert err.code == "E2001"
    assert err.detail == ""
    assert "[E2001]" in str(err)


def test_constructor_accepts_string_code_with_detail():
    err = Stage20ValidationError("E2005", detail="row 3 label=BANANA")
    assert err.code == "E2005"
    assert err.detail == "row 3 label=BANANA"
    assert "BANANA" in str(err)


def test_constructor_rejects_unknown_code():
    with pytest.raises(ValueError):
        Stage20ValidationError("E9999")


def test_every_locked_code_has_a_message_template():
    for member in EligibilityErrorCode:
        assert member.value in ERROR_MESSAGE_TEMPLATES, (
            f"{member.value} missing from ERROR_MESSAGE_TEMPLATES"
        )
