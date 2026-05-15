"""Tests for the aggregate ``validate_inputs`` orchestrator (20.1.D).

Covers:
  * Clean fixture passes (ok=True, no errors, no warnings).
  * Missing Stage 18 surfaces E2001 + halted_at.
  * Missing Stage 19 surfaces E2002 + halted_at.
  * W2001 fires when the median row age exceeds the threshold
    (under an injected FrozenClock).
  * W2004 fires when two operators reviewed the same slice.
  * W2005 fires when a ledger row references an unmapped slice.
  * Determinism: same inputs + same clock = equal ValidationResult.
"""

from __future__ import annotations

from datetime import datetime, timezone

from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.input_validators import (
    ValidationResult,
    validate_inputs,
)
from PHX2.tests.stage20.fixtures.stage18_outputs import (
    write_minimal_stage18_dir,
)
from PHX2.tests.stage20.fixtures.stage19_outputs import (
    make_ledger_row,
    write_ledger,
    write_minimal_stage19_dir,
    write_stage19_manifest,
)


def _clock_at(year, month, day) -> FrozenClock:
    return FrozenClock(datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc))


def test_clean_fixture_returns_ok(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    # Same day as the fixture's review_timestamp_utc (2026-05-13Z)
    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))

    assert isinstance(result, ValidationResult)
    assert result.ok
    assert result.errors == ()
    assert result.warnings == ()
    assert result.summary["halted_at"] is None
    assert result.summary["ledger_row_count"] == 1


def test_missing_stage18_returns_e2001_and_halts(tmp_path):
    s18 = tmp_path / "stage18_empty"
    s18.mkdir()  # exists but no manifest
    # We still need a valid Stage 19 dir for the orchestrator to
    # reach step 2; build one against a SECOND Stage 18 fixture
    # because Stage 19's manifest pins upstream hashes against
    # whatever Stage 18 it was built from.
    s18_for_s19 = tmp_path / "stage18_for_s19"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18_for_s19)
    write_minimal_stage19_dir(s19, stage18_dir=s18_for_s19)

    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))

    assert not result.ok
    assert "E2001" in result.errors
    assert result.summary["halted_at"] == "locate_stage18"


def test_missing_stage19_returns_e2002_and_halts(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19_empty"
    write_minimal_stage18_dir(s18)
    s19.mkdir()  # no manifest

    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))

    assert not result.ok
    assert "E2002" in result.errors
    assert result.summary["halted_at"] == "locate_stage19"


def test_stale_ledger_emits_w2001(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    # Default fixture timestamp is 2026-05-13Z. Fast-forward clock
    # 60 days; median row age = 60 > 30.
    result = validate_inputs(s18, s19, clock=_clock_at(2026, 7, 13))

    assert result.ok  # warnings do not fail validation
    assert "W2001" in result.warnings


def test_multiple_operators_per_slice_emits_w2004(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)

    s19.mkdir()
    rows = [
        make_ledger_row(
            ledger_row_id="aaaa000000000001",
            operator_id="operator_alice",
        ),
        make_ledger_row(
            ledger_row_id="bbbb000000000002",
            operator_id="operator_bob",  # different operator, same slice
        ),
    ]
    write_ledger(s19 / "operator_review_ledger.csv", rows=rows)
    write_stage19_manifest(
        s19 / "manifest.json",
        stage18_input_dir=str(s18.resolve()),
    )

    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))
    assert "W2004" in result.warnings


def test_stage18_evidence_gap_emits_w2005(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)  # has only the default slice

    s19.mkdir()
    orphan_row = make_ledger_row(
        ledger_row_id="cccc000000000003",
        policy_hash="orphan_policy_hash",
        rule_id="orphan_rule",
        window_seconds="7200",
    )
    write_ledger(s19 / "operator_review_ledger.csv", rows=[orphan_row])
    write_stage19_manifest(
        s19 / "manifest.json",
        stage18_input_dir=str(s18.resolve()),
    )

    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))
    assert "W2005" in result.warnings


def test_validate_inputs_is_deterministic_under_same_inputs(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    clock = _clock_at(2026, 5, 13)
    a = validate_inputs(s18, s19, clock=clock)
    b = validate_inputs(s18, s19, clock=clock)

    assert a == b


def test_validate_inputs_summary_carries_halted_at_on_locator_failure(tmp_path):
    s18 = tmp_path / "stage18_missing"
    s19 = tmp_path / "stage19_missing"
    s18.mkdir()
    s19.mkdir()

    result = validate_inputs(s18, s19, clock=_clock_at(2026, 5, 13))

    assert result.summary["halted_at"] is not None
    assert result.summary["ledger_row_count"] == 0
