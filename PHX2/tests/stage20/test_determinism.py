"""Stage 20.2 determinism harness (Phase D).

E2020 coverage:
  * Positive: two runs over identical synthetic inputs with the
    same FrozenClock produce byte-identical artifacts for all 5
    output files (preview_candidates.csv,
    alert_eligibility_decisions.csv, README.md, stage20_run.log,
    manifest.json).
  * Negative (input drift): a one-cell tamper on the ledger CSV
    between two runs alters at least one output file.
  * Negative (clock drift): a different FrozenClock instant
    alters the stage20_run_id and at least manifest.json.

These tests are deliberately strict: any byte-level divergence in
the locked artifact set is a failure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.manifest_assembler import verify_run_determinism
from PHX2.stage20.runner import run_stage20_2
from PHX2.tests.stage20.fixtures.synthetic_stage18_19 import (
    make_minimal_valid_inputs,
)


_FROZEN_NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


def _frozen_clock_a() -> FrozenClock:
    return FrozenClock(_FROZEN_NOW)


def _frozen_clock_b() -> FrozenClock:
    # Distinct instant so generated_at_utc differs by exactly 1 day.
    return FrozenClock(_FROZEN_NOW + timedelta(days=1))


_OUTPUT_FILENAMES: tuple[str, ...] = (
    "preview_candidates.csv",
    "alert_eligibility_decisions.csv",
    "README.md",
    "stage20_run.log",
    "manifest.json",
)


def _run_and_collect_bytes(
    tmp_base: Path,
    label: str,
    *,
    clock: FrozenClock,
    mutate_ledger_row: bool = False,
) -> dict[str, bytes]:
    """Build a fresh fixture under ``tmp_base / label``, run the
    runner, and return ``{filename: bytes}`` for every locked
    output file."""

    inputs = make_minimal_valid_inputs(tmp_base / f"in_{label}")
    if mutate_ledger_row:
        # Tamper one byte: rewrite the ledger CSV with a different
        # operator_id on the single data row. Stage 19 manifest
        # records hashes of Stage 18 only, so this change does
        # NOT trip E2003; validate_inputs accepts it cleanly and
        # downstream artifacts differ.
        ledger_path = inputs["stage19_ledger_path"]
        text = ledger_path.read_text(encoding="utf-8")
        tampered = text.replace(",op_a,", ",op_b,")
        assert tampered != text, (
            "expected the synthetic fixture to contain ',op_a,' "
            "for the tamper test"
        )
        ledger_path.write_bytes(tampered.encode("utf-8"))

    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_base / f"out_{label}",
        clock=clock,
    )
    return {
        name: (result.run_dir / name).read_bytes()
        for name in _OUTPUT_FILENAMES
    }


# ---------------------------------------------------------------------------
# Positive determinism: identical inputs + identical clock -> byte-identical
# ---------------------------------------------------------------------------


def _run_and_return_dir(
    tmp_base: Path,
    label: str,
    *,
    clock: FrozenClock,
) -> Path:
    inputs = make_minimal_valid_inputs(tmp_base / f"in_{label}")
    result = run_stage20_2(
        inputs["stage18_manifest_path"],
        inputs["stage18_review_matrix_path"],
        inputs["stage19_manifest_path"],
        inputs["stage19_ledger_path"],
        tmp_base / f"out_{label}",
        clock=clock,
    )
    return result.run_dir


def test_two_runs_identical_inputs_identical_clock_yield_byte_identical_outputs(
    tmp_path,
):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    for name in _OUTPUT_FILENAMES:
        assert bytes_a[name] == bytes_b[name], (
            f"E2020: artifact {name} differs across two clean runs "
            f"over identical inputs"
        )


def test_verify_run_determinism_passes_on_byte_identical_runs(tmp_path):
    """Codex remediation: production-side E2020 detector path.

    ``verify_run_determinism`` is now the locked entry point for
    cross-run determinism. The twice-run harness invokes it
    explicitly so the test surface mirrors how a real audit
    pipeline would consume the function.
    """

    dir_a = _run_and_return_dir(tmp_path, "a", clock=_frozen_clock_a())
    dir_b = _run_and_return_dir(tmp_path, "b", clock=_frozen_clock_a())
    # Must not raise.
    verify_run_determinism(dir_a, dir_b)


def test_two_runs_produce_byte_identical_preview_candidates_csv(tmp_path):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    assert bytes_a["preview_candidates.csv"] == bytes_b["preview_candidates.csv"]


def test_two_runs_produce_byte_identical_decisions_csv(tmp_path):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    assert (
        bytes_a["alert_eligibility_decisions.csv"]
        == bytes_b["alert_eligibility_decisions.csv"]
    )


def test_two_runs_produce_byte_identical_readme(tmp_path):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    assert bytes_a["README.md"] == bytes_b["README.md"]


def test_two_runs_produce_byte_identical_run_log(tmp_path):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    assert bytes_a["stage20_run.log"] == bytes_b["stage20_run.log"]


def test_two_runs_produce_byte_identical_manifest_json(tmp_path):
    bytes_a = _run_and_collect_bytes(tmp_path, "a", clock=_frozen_clock_a())
    bytes_b = _run_and_collect_bytes(tmp_path, "b", clock=_frozen_clock_a())
    assert bytes_a["manifest.json"] == bytes_b["manifest.json"]


# ---------------------------------------------------------------------------
# Negative determinism: input tamper alters at least one output
# ---------------------------------------------------------------------------


def test_ledger_tamper_changes_at_least_one_output(tmp_path):
    baseline = _run_and_collect_bytes(
        tmp_path, "baseline", clock=_frozen_clock_a(),
    )
    tampered = _run_and_collect_bytes(
        tmp_path,
        "tampered",
        clock=_frozen_clock_a(),
        mutate_ledger_row=True,
    )
    diffs = [
        name for name in _OUTPUT_FILENAMES
        if baseline[name] != tampered[name]
    ]
    assert diffs, (
        "tampering the ledger CSV must alter at least one output "
        "(otherwise the harness cannot detect drift)"
    )


# ---------------------------------------------------------------------------
# Negative determinism: clock-shift alters stage20_run_id and manifest.json
# ---------------------------------------------------------------------------


def test_different_frozen_clock_changes_stage20_run_id_and_manifest(tmp_path):
    inputs_a = make_minimal_valid_inputs(tmp_path / "in_a")
    inputs_b = make_minimal_valid_inputs(tmp_path / "in_b")
    res_a = run_stage20_2(
        inputs_a["stage18_manifest_path"],
        inputs_a["stage18_review_matrix_path"],
        inputs_a["stage19_manifest_path"],
        inputs_a["stage19_ledger_path"],
        tmp_path / "out_a",
        clock=_frozen_clock_a(),
    )
    res_b = run_stage20_2(
        inputs_b["stage18_manifest_path"],
        inputs_b["stage18_review_matrix_path"],
        inputs_b["stage19_manifest_path"],
        inputs_b["stage19_ledger_path"],
        tmp_path / "out_b",
        clock=_frozen_clock_b(),
    )
    assert res_a.stage20_run_id != res_b.stage20_run_id

    manifest_a = (res_a.run_dir / "manifest.json").read_bytes()
    manifest_b = (res_b.run_dir / "manifest.json").read_bytes()
    assert manifest_a != manifest_b


# ---------------------------------------------------------------------------
# Codex remediation: E2020 negative coverage via verify_run_determinism
# ---------------------------------------------------------------------------


def test_verify_run_determinism_raises_e2020_on_byte_mismatch(tmp_path):
    """Tamper one artifact in run_dir_b after a successful run and
    confirm verify_run_determinism raises E2020 with the offending
    filename in the detail.
    """

    dir_a = _run_and_return_dir(tmp_path, "a", clock=_frozen_clock_a())
    dir_b = _run_and_return_dir(tmp_path, "b", clock=_frozen_clock_a())

    # Sanity: the two run dirs are byte-identical at start.
    verify_run_determinism(dir_a, dir_b)

    # Tamper a single byte of preview_candidates.csv in dir_b. Any
    # byte change cascades into the SHA, so the verifier must raise.
    tampered_file = dir_b / "preview_candidates.csv"
    raw = tampered_file.read_bytes()
    tampered_file.write_bytes(raw + b"\n")  # extra trailing newline

    with pytest.raises(Stage20ValidationError) as exc:
        verify_run_determinism(dir_a, dir_b)
    assert exc.value.code == "E2020"
    assert "preview_candidates.csv" in str(exc.value)


def test_verify_run_determinism_raises_e2020_on_missing_artifact(tmp_path):
    """A missing artifact in one of the run dirs also trips E2020."""

    dir_a = _run_and_return_dir(tmp_path, "a", clock=_frozen_clock_a())
    dir_b = _run_and_return_dir(tmp_path, "b", clock=_frozen_clock_a())

    # Remove README.md from dir_b.
    (dir_b / "README.md").unlink()

    with pytest.raises(Stage20ValidationError) as exc:
        verify_run_determinism(dir_a, dir_b)
    assert exc.value.code == "E2020"
    assert "README.md" in str(exc.value)
    assert "run_dir_b" in str(exc.value)
