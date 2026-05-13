"""Phase 2: closed-set L01-L22 / R01-R08 / B01 error codes carry non-empty messages."""

from __future__ import annotations

import pytest

from PHX2.stage16a.errors import (
    ALL_CODES,
    B_CODES,
    L_CODES,
    MESSAGE_TEMPLATES,
    R_CODES,
    Stage16AError,
)


def test_every_l_code_has_a_non_empty_message() -> None:
    for code in L_CODES:
        assert code in MESSAGE_TEMPLATES, f"L code {code} missing template"
        assert MESSAGE_TEMPLATES[code].strip(), (
            f"L code {code} has empty message template"
        )


def test_every_r_code_has_a_non_empty_message() -> None:
    for code in R_CODES:
        assert code in MESSAGE_TEMPLATES, f"R code {code} missing template"
        assert MESSAGE_TEMPLATES[code].strip(), (
            f"R code {code} has empty message template"
        )


def test_every_b_code_has_a_non_empty_message() -> None:
    for code in B_CODES:
        assert code in MESSAGE_TEMPLATES, f"B code {code} missing template"
        assert MESSAGE_TEMPLATES[code].strip(), (
            f"B code {code} has empty message template"
        )


def test_l15_and_l16_are_intentionally_dropped() -> None:
    """Step 0 locked remediation #2: Stage 15 predicate has 5 keys, not 7.
    L15 (predicate.direction) and L16 (predicate.policy_surface) have
    nothing to verify and must not appear in the closed set."""

    assert "L15" not in L_CODES
    assert "L16" not in L_CODES
    assert "L15" not in MESSAGE_TEMPLATES
    assert "L16" not in MESSAGE_TEMPLATES


def test_all_codes_union() -> None:
    assert ALL_CODES == frozenset(L_CODES) | frozenset(R_CODES) | frozenset(B_CODES)


def test_stage16a_error_carries_code_and_detail() -> None:
    exc = Stage16AError("L01", "missing path /tmp/foo")
    assert exc.code == "L01"
    assert exc.detail == "missing path /tmp/foo"
    rendered = str(exc)
    assert "L01" in rendered
    assert "missing path /tmp/foo" in rendered


def test_stage16a_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError):
        Stage16AError("L99")


def test_stage16a_error_without_detail() -> None:
    exc = Stage16AError("R01")
    assert exc.code == "R01"
    assert exc.detail == ""
    assert "R01" in str(exc)
