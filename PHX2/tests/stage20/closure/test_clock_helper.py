"""Stage 20.4 closure clock helper tests.

Verify ``FrozenClock`` returns the injected value, ``SystemClock``
returns a tz-aware UTC datetime, ``format_utc_iso_z`` produces the
expected deterministic ISO-Z string, naive datetimes are rejected
at the helper boundary, and (boundary discipline) the closure
clock helper does NOT import from ``PHX2.stage20.clock`` or any
other ``PHX2.stage20.*`` module outside the closure subtree.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import clock_helper as ch


# ---------------------------------------------------------------------------
# Protocol structural conformance
# ---------------------------------------------------------------------------


def test_system_clock_has_now_method():
    sc = ch.SystemClock()
    assert callable(getattr(sc, "now"))


def test_frozen_clock_has_now_method():
    fc = ch.FrozenClock(
        datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert callable(getattr(fc, "now"))


# ---------------------------------------------------------------------------
# SystemClock
# ---------------------------------------------------------------------------


def test_system_clock_returns_tz_aware_utc():
    sc = ch.SystemClock()
    result = sc.now()
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


def test_default_clock_returns_system_clock_instance():
    assert isinstance(ch.default_clock(), ch.SystemClock)


# ---------------------------------------------------------------------------
# FrozenClock
# ---------------------------------------------------------------------------


def test_frozen_clock_returns_fixed_value():
    fixed = datetime(2026, 5, 16, 9, 30, 0, tzinfo=timezone.utc)
    fc = ch.FrozenClock(fixed)
    assert fc.now() == fixed


def test_frozen_clock_is_deterministic_across_calls():
    fixed = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    fc = ch.FrozenClock(fixed)
    samples = [fc.now() for _ in range(5)]
    assert all(s == fixed for s in samples)


def test_frozen_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        ch.FrozenClock(datetime(2026, 5, 16, 9, 30, 0))


# ---------------------------------------------------------------------------
# format_utc_iso_z
# ---------------------------------------------------------------------------


def test_format_utc_iso_z_locked_format():
    dt = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
    assert ch.format_utc_iso_z(dt) == "2026-05-16T12:34:56Z"


def test_format_utc_iso_z_pads_single_digit_components():
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert ch.format_utc_iso_z(dt) == "2026-01-02T03:04:05Z"


def test_format_utc_iso_z_rejects_naive_datetime():
    with pytest.raises(ValueError):
        ch.format_utc_iso_z(datetime(2026, 5, 16, 12, 0, 0))


def test_format_utc_iso_z_matches_stage_20_2_run_convention():
    """The closure helper's ISO-Z output must match the convention used
    by Stage 20.2's runner._format_iso_z and Stage 20.3's
    filter_interface_runner._format_iso_z: strftime("%Y-%m-%dT%H:%M:%SZ")
    on a tz-aware UTC datetime. This pin lives here (not via import) so
    the cross-stage hygiene policy is preserved."""
    dt = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
    expected = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert ch.format_utc_iso_z(dt) == expected


def test_format_utc_iso_z_is_deterministic_for_same_input():
    dt = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert ch.format_utc_iso_z(dt) == ch.format_utc_iso_z(dt)


def test_format_utc_iso_z_distinguishes_different_inputs():
    dt1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    assert ch.format_utc_iso_z(dt1) != ch.format_utc_iso_z(dt2)


# ---------------------------------------------------------------------------
# Boundary discipline: no wall-clock leakage outside SystemClock.now
# ---------------------------------------------------------------------------


def _count_datetime_now_calls(tree: ast.AST) -> int:
    """Count AST nodes that look like ``datetime.now(...)``.

    Matches ast.Call whose ``func`` is an ast.Attribute with
    attr="now" whose ``value`` is an ast.Name id="datetime".
    """

    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "now":
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "datetime":
            continue
        count += 1
    return count


def test_only_one_datetime_now_call_site_in_clock_helper():
    """SystemClock.now is the only call site for datetime.now() in the
    clock helper. Every other closure module derives timestamps via an
    injected Clock (so FrozenClock makes the run fully deterministic)."""
    source_path = Path(ch.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    assert _count_datetime_now_calls(tree) == 1


# ---------------------------------------------------------------------------
# Boundary discipline: closure clock_helper does not re-export upstream
# ---------------------------------------------------------------------------


def test_clock_helper_does_not_import_phx2_stage20_clock():
    """Stage 20.4 closure clock_helper must be a hand-duplicated local
    copy, NOT a thin re-export of PHX2.stage20.clock. Walk the module's
    AST and assert no import from PHX2.stage20.clock."""
    source_path = Path(ch.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "PHX2.stage20.clock", (
                f"clock_helper.py must not import from "
                f"PHX2.stage20.clock; found at line {node.lineno}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "PHX2.stage20.clock", (
                    f"clock_helper.py must not "
                    f"`import PHX2.stage20.clock`; "
                    f"found at line {node.lineno}"
                )


def test_clock_helper_imports_no_stage20_modules_outside_closure():
    """Boundary discipline: no imports from PHX2.stage20.* outside
    PHX2.stage20.closure.* . clock_helper currently imports zero
    PHX2.stage20.* modules; this test pins that invariant."""
    source_path = Path(ch.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("PHX2.stage20") and not mod.startswith(
                "PHX2.stage20.closure"
            ):
                pytest.fail(
                    f"clock_helper.py must not import from {mod!r} "
                    f"at line {node.lineno}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("PHX2.stage20") and not name.startswith(
                    "PHX2.stage20.closure"
                ):
                    pytest.fail(
                        f"clock_helper.py must not "
                        f"`import {name}` at line {node.lineno}"
                    )
