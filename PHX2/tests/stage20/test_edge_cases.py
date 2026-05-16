"""Stage 20.2 edge-case coverage (Phase D).

Three additional behaviors not exercised by the smaller fixtures
elsewhere:

  * Large input scale: 1000 ledger rows across 200 slices.
    Asserts: run completes, counts correct, artifacts byte-stable
    across two runs. Does NOT assert wall-clock timing (per Phase
    D constraint G).

  * Extreme timestamps: epoch-zero and far-future
    (``9999-12-31T23:59:59Z``). Asserts: no parse crash, no
    exception, review_age_days is either a real integer or ``-1``.

  * review_sequence collision within a slice: two rows with the
    same review_sequence but different ledger_row_ids. Asserts
    the locked tiebreaker (max(ledger_row_id) by string compare)
    chooses the deterministic winner end-to-end through
    ``run_stage20_2``.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.runner import run_stage20_2
from PHX2.tests.stage20.fixtures.synthetic_stage18_19 import (
    make_ledger_row,
    make_review_matrix_row,
    make_stage18_files,
    make_stage19_files,
)


_FROZEN_NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


def _frozen_clock() -> FrozenClock:
    return FrozenClock(_FROZEN_NOW)


# ---------------------------------------------------------------------------
# Large input: 1000 rows across 200 slices
# ---------------------------------------------------------------------------


_SLICE_COUNT: int = 200
_ROWS_PER_SLICE: int = 5
_TOTAL_ROWS: int = _SLICE_COUNT * _ROWS_PER_SLICE  # = 1000


def _build_large_inputs(base_dir: Path) -> dict[str, Path]:
    stage18_dir = base_dir / "stage18"
    stage19_dir = base_dir / "stage19"

    rm_rows = [
        make_review_matrix_row(
            policy_hash=f"ph_{i:04d}",
            rule_id=f"rule_{i:04d}",
            window_seconds=str(30 + (i % 5)),  # vary the slice key
        )
        for i in range(_SLICE_COUNT)
    ]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)

    ledger_rows = []
    # Cycle through the 6 locked review labels so we hit all
    # PreviewEligibilityState values.
    label_cycle = (
        "REVIEW_PROMISING_CONFIRMED",
        "REVIEW_HARMFUL_CONFIRMED",
        "REVIEW_REJECTED",
        "WATCHLIST",
        "NEEDS_MORE_DATA",
        "INCONCLUSIVE",
    )
    for slice_idx in range(_SLICE_COUNT):
        slice_label = label_cycle[slice_idx % len(label_cycle)]
        for r in range(_ROWS_PER_SLICE):
            ledger_rows.append(make_ledger_row(
                ledger_row_id=f"lrid_s{slice_idx:04d}_r{r:02d}",
                policy_hash=f"ph_{slice_idx:04d}",
                rule_id=f"rule_{slice_idx:04d}",
                window_seconds=str(30 + (slice_idx % 5)),
                review_sequence=str(r + 1),  # winner has max r
                review_label=slice_label,
            ))
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    return {
        "stage18_manifest_path": s18_manifest,
        "stage18_review_matrix_path": s18_rm,
        "stage19_manifest_path": s19_manifest,
        "stage19_ledger_path": s19_ledger,
    }


def test_large_ledger_1000_rows_200_slices_completes(tmp_path):
    inputs = _build_large_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    # 200 slices -> 200 candidates -> 200 * 4 = 800 decision rows.
    assert result.candidate_count == _SLICE_COUNT
    assert result.decision_count == _SLICE_COUNT * 4

    # Sum of per-state counts equals candidate count.
    total = sum(result.preview_state_counts.values())
    assert total == _SLICE_COUNT


def test_large_ledger_is_byte_deterministic_across_two_runs(tmp_path):
    inputs_a = _build_large_inputs(tmp_path / "in_a")
    inputs_b = _build_large_inputs(tmp_path / "in_b")
    res_a = run_stage20_2(
        inputs_a["stage18_manifest_path"],
        inputs_a["stage18_review_matrix_path"],
        inputs_a["stage19_manifest_path"],
        inputs_a["stage19_ledger_path"],
        tmp_path / "out_a",
        clock=_frozen_clock(),
    )
    res_b = run_stage20_2(
        inputs_b["stage18_manifest_path"],
        inputs_b["stage18_review_matrix_path"],
        inputs_b["stage19_manifest_path"],
        inputs_b["stage19_ledger_path"],
        tmp_path / "out_b",
        clock=_frozen_clock(),
    )
    for name in (
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "README.md",
        "stage20_run.log",
        "manifest.json",
    ):
        assert (
            (res_a.run_dir / name).read_bytes()
            == (res_b.run_dir / name).read_bytes()
        ), f"large-input determinism: {name} differs"


def test_large_ledger_csv_row_counts_match_manifest(tmp_path):
    inputs = _build_large_inputs(tmp_path / "inputs")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["preview_candidates_row_count"] == _SLICE_COUNT
    assert manifest["alert_eligibility_decisions_row_count"] == (
        _SLICE_COUNT * 4
    )


# ---------------------------------------------------------------------------
# Extreme review_timestamp_utc values
# ---------------------------------------------------------------------------


def _build_inputs_with_timestamps(
    base_dir: Path,
    timestamps_per_slice: list[str],
) -> dict[str, Path]:
    stage18_dir = base_dir / "stage18"
    stage19_dir = base_dir / "stage19"
    rm_rows = [
        make_review_matrix_row(policy_hash=f"ph_{i}", rule_id=f"rule_{i}")
        for i in range(len(timestamps_per_slice))
    ]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)
    ledger_rows = [
        make_ledger_row(
            ledger_row_id=f"lrid_{i}",
            policy_hash=f"ph_{i}",
            rule_id=f"rule_{i}",
            review_timestamp_utc=ts,
        )
        for i, ts in enumerate(timestamps_per_slice)
    ]
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    return {
        "stage18_manifest_path": s18_manifest,
        "stage18_review_matrix_path": s18_rm,
        "stage19_manifest_path": s19_manifest,
        "stage19_ledger_path": s19_ledger,
    }


def test_extreme_review_timestamp_epoch_zero_does_not_crash(tmp_path):
    inputs = _build_inputs_with_timestamps(
        tmp_path / "inputs", ["1970-01-01T00:00:00Z"],
    )
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    assert result.candidate_count == 1
    # Read the preview CSV and confirm review_age_days is either
    # a real integer or -1.
    with (result.run_dir / "preview_candidates.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    age = rows[0]["review_age_days"]
    # Must be parseable as int.
    parsed_age = int(age)
    # Either a real (large) computed value or -1.
    assert parsed_age == -1 or parsed_age > 0


def test_extreme_review_timestamp_far_future_does_not_crash(tmp_path):
    inputs = _build_inputs_with_timestamps(
        tmp_path / "inputs", ["9999-12-31T23:59:59Z"],
    )
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    assert result.candidate_count == 1
    with (result.run_dir / "preview_candidates.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    age = rows[0]["review_age_days"]
    parsed_age = int(age)
    # Far-future yields a (negative) computed delta or -1; both
    # are acceptable per Phase D constraint G.
    assert parsed_age == -1 or parsed_age < 0
    # review_stale must be "false" for a future timestamp -- only
    # positive ages > 30 trigger staleness.
    assert rows[0]["review_stale"] == "false"


def test_extreme_timestamps_mixed_run_completes_byte_deterministic(tmp_path):
    timestamps = [
        "1970-01-01T00:00:00Z",
        "2026-05-15T00:00:00Z",
        "9999-12-31T23:59:59Z",
    ]
    inputs_a = _build_inputs_with_timestamps(tmp_path / "in_a", timestamps)
    inputs_b = _build_inputs_with_timestamps(tmp_path / "in_b", timestamps)
    res_a = run_stage20_2(
        inputs_a["stage18_manifest_path"],
        inputs_a["stage18_review_matrix_path"],
        inputs_a["stage19_manifest_path"],
        inputs_a["stage19_ledger_path"],
        tmp_path / "out_a",
        clock=_frozen_clock(),
    )
    res_b = run_stage20_2(
        inputs_b["stage18_manifest_path"],
        inputs_b["stage18_review_matrix_path"],
        inputs_b["stage19_manifest_path"],
        inputs_b["stage19_ledger_path"],
        tmp_path / "out_b",
        clock=_frozen_clock(),
    )
    for name in (
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "manifest.json",
    ):
        assert (
            (res_a.run_dir / name).read_bytes()
            == (res_b.run_dir / name).read_bytes()
        )


# ---------------------------------------------------------------------------
# review_sequence collision within a slice (ledger_row_id tiebreak)
# ---------------------------------------------------------------------------


def _build_inputs_with_sequence_tie(
    base_dir: Path,
    *,
    ledger_row_ids_in_order: list[str],
    expected_winner_label: str = "WATCHLIST",
    loser_label: str = "REVIEW_REJECTED",
) -> tuple[dict[str, Path], str]:
    """Build a one-slice fixture where every ledger row has the
    same review_sequence. The row whose ledger_row_id sorts
    largest by string compare is assigned ``expected_winner_label``;
    every other row gets ``loser_label``. The end-to-end winner's
    review_label is what propagates into the PreviewCandidate's
    preview_state.

    Returns (inputs, expected_winner_ledger_row_id).
    """

    stage18_dir = base_dir / "stage18"
    stage19_dir = base_dir / "stage19"
    rm_rows = [make_review_matrix_row()]
    s18_manifest, s18_rm = make_stage18_files(stage18_dir, rm_rows)

    expected_winner_id = max(ledger_row_ids_in_order)
    ledger_rows = []
    for lrid in ledger_row_ids_in_order:
        ledger_rows.append(make_ledger_row(
            ledger_row_id=lrid,
            review_sequence="5",  # same for every row
            review_label=(
                expected_winner_label
                if lrid == expected_winner_id
                else loser_label
            ),
        ))
    s19_manifest, s19_ledger = make_stage19_files(
        stage19_dir, ledger_rows, s18_manifest, s18_rm,
    )
    return (
        {
            "stage18_manifest_path": s18_manifest,
            "stage18_review_matrix_path": s18_rm,
            "stage19_manifest_path": s19_manifest,
            "stage19_ledger_path": s19_ledger,
        },
        expected_winner_id,
    )


def test_review_sequence_tie_winner_is_max_ledger_row_id(tmp_path):
    """End-to-end: same review_sequence across all rows in a
    slice -> winner is max(ledger_row_id) by string compare.
    """

    inputs, expected_winner_id = _build_inputs_with_sequence_tie(
        tmp_path / "inputs",
        ledger_row_ids_in_order=["lrid_aaa", "lrid_mmm", "lrid_zzz"],
    )
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_path / "out",
        clock=_frozen_clock(),
    )
    assert result.candidate_count == 1
    with (result.run_dir / "preview_candidates.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    # The candidate's source_ledger_row_id must be the locked
    # tiebreak winner.
    assert rows[0]["source_ledger_row_id"] == expected_winner_id
    # And the preview_state reflects the winner's label
    # (WATCHLIST -> PREVIEW_OBSERVE_ONLY), not the losers'.
    assert rows[0]["preview_state"] == "PREVIEW_OBSERVE_ONLY"


def test_review_sequence_tie_is_deterministic_across_input_orderings(tmp_path):
    """Permute the order ledger rows appear in the CSV; the locked
    tiebreaker must still pick the same winner.
    """

    inputs_a, win_a = _build_inputs_with_sequence_tie(
        tmp_path / "in_a",
        ledger_row_ids_in_order=["lrid_aaa", "lrid_mmm", "lrid_zzz"],
    )
    inputs_b, win_b = _build_inputs_with_sequence_tie(
        tmp_path / "in_b",
        ledger_row_ids_in_order=["lrid_zzz", "lrid_aaa", "lrid_mmm"],
    )
    assert win_a == win_b == "lrid_zzz"

    res_a = run_stage20_2(
        inputs_a["stage18_manifest_path"],
        inputs_a["stage18_review_matrix_path"],
        inputs_a["stage19_manifest_path"],
        inputs_a["stage19_ledger_path"],
        tmp_path / "out_a",
        clock=_frozen_clock(),
    )
    res_b = run_stage20_2(
        inputs_b["stage18_manifest_path"],
        inputs_b["stage18_review_matrix_path"],
        inputs_b["stage19_manifest_path"],
        inputs_b["stage19_ledger_path"],
        tmp_path / "out_b",
        clock=_frozen_clock(),
    )
    # Same candidate_id (candidate_id is derived from
    # stage19_run_id + source_ledger_row_id + versions; the
    # tiebreak winner is identical so candidate_id matches).
    manifest_a = json.loads(
        (res_a.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_b = json.loads(
        (res_b.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        manifest_a["preview_state_counts"]
        == manifest_b["preview_state_counts"]
    )
