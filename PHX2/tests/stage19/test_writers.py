"""Stage 19 writers tests.

Covers each of the four writers: header order, deterministic
output for identical input, empty-rows handling, atomic-write
behavior on simulated failure, and the README's required content
including the no-action reminder.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from PHX2.stage19 import writers as W
from PHX2.stage19.constants import (
    LABELS,
    LEDGER_COLUMNS,
    SUMMARY_COLUMNS,
)
from PHX2.stage19.ledger import LedgerRow, SummaryRow


def _ledger_row(
    *,
    stage19_run_id: str = "stage19_aaaa",
    ledger_row_id: str = "0123456789abcdef",
    stage18_run_id: str = "0123456789abcdef",
    policy_hash: str = "abc123def456",
    rule_id: str = "rule_minimal",
    window_seconds: int = 3600,
    operator_id: str = "alice",
    review_sequence: int = 1,
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "ok",
    review_timestamp_utc: str = "2026-05-14T05:00:00Z",
    stage18_classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
) -> LedgerRow:
    return LedgerRow(
        stage19_run_id=stage19_run_id,
        ledger_row_id=ledger_row_id,
        stage18_run_id=stage18_run_id,
        policy_hash=policy_hash,
        rule_id=rule_id,
        window_seconds=window_seconds,
        operator_id=operator_id,
        review_sequence=review_sequence,
        review_label=review_label,
        review_notes=review_notes,
        review_timestamp_utc=review_timestamp_utc,
        stage18_classification=stage18_classification,
        stage17_label_preserved=stage17_label_preserved,
    )


def _summary_row(
    *,
    stage18_run_id: str = "0123456789abcdef",
    policy_hash: str = "abc123def456",
    rule_id: str = "rule_minimal",
    window_seconds: int = 3600,
    operator_id: str = "alice",
    current_review_sequence: int = 1,
    current_review_label: str = "REVIEW_PROMISING_CONFIRMED",
    current_review_notes: str = "ok",
    current_review_timestamp_utc: str = "2026-05-14T05:00:00Z",
    stage18_classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
) -> SummaryRow:
    return SummaryRow(
        stage18_run_id=stage18_run_id,
        policy_hash=policy_hash,
        rule_id=rule_id,
        window_seconds=window_seconds,
        operator_id=operator_id,
        current_review_sequence=current_review_sequence,
        current_review_label=current_review_label,
        current_review_notes=current_review_notes,
        current_review_timestamp_utc=current_review_timestamp_utc,
        stage18_classification=stage18_classification,
        stage17_label_preserved=stage17_label_preserved,
    )


def _base_manifest() -> dict:
    return {
        "stage19_schema_version": "stage19_ledger_v1",
        "stage19_version": "0.1.0",
        "stage19_run_id": "aaaaaaaaaaaaaaaa",
        "run_timestamp_utc": "2026-05-14T05:00:00Z",
        "operator_id": "alice",
        "stage18_input_dir": "/tmp/stage18_run_x",
        "stage18_input_basename": "stage18_run_x",
        "stage18_run_id": "0123456789abcdef",
        "stage18_manifest_sha256": "0" * 64,
        "stage18_review_matrix_sha256": "1" * 64,
        "operator_input_path": "/tmp/op.csv",
        "operator_input_sha256": "2" * 64,
        "prior_ledger_dir": None,
        "prior_ledger_sha256": None,
        "prior_ledger_schema_version": None,
        "new_row_count": 3,
        "prior_row_count": 0,
        "total_ledger_row_count": 3,
        "label_counts": {label: 0 for label in LABELS},
        "git_commit": "0" * 40,
    }


# ===========================================================================
# write_ledger_csv
# ===========================================================================


class TestWriteLedgerCsv:
    def test_emits_header_in_LEDGER_COLUMNS_order(self, tmp_path: Path) -> None:
        out = tmp_path / "ledger.csv"
        W.write_ledger_csv(out, [_ledger_row()])
        with out.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert tuple(header) == LEDGER_COLUMNS

    def test_writes_integer_fields_as_decimal_strings(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "ledger.csv"
        W.write_ledger_csv(
            out, [_ledger_row(window_seconds=86400, review_sequence=42)]
        )
        with out.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader)  # header
            row = next(reader)
        # window_seconds is column 5 (0-indexed), review_sequence is 7
        assert row[5] == "86400"
        assert row[7] == "42"

    def test_empty_rows_produces_header_only(self, tmp_path: Path) -> None:
        out = tmp_path / "ledger.csv"
        W.write_ledger_csv(out, [])
        text = out.read_text(encoding="utf-8")
        assert text == ",".join(LEDGER_COLUMNS) + "\n"

    def test_deterministic_for_identical_input(self, tmp_path: Path) -> None:
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        rows = [_ledger_row(rule_id=f"rule_{i}") for i in range(3)]
        W.write_ledger_csv(a, rows)
        W.write_ledger_csv(b, rows)
        assert a.read_bytes() == b.read_bytes()

    def test_writer_preserves_caller_row_order(self, tmp_path: Path) -> None:
        out = tmp_path / "ledger.csv"
        rows = [
            _ledger_row(rule_id="z"),
            _ledger_row(rule_id="a"),
            _ledger_row(rule_id="m"),
        ]
        W.write_ledger_csv(out, rows)
        with out.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader)
            data_rows = list(reader)
        # rule_id is column 4
        assert [r[4] for r in data_rows] == ["z", "a", "m"]

    def test_atomic_no_partial_file_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "ledger.csv"

        def boom(src, dst):  # noqa: ARG001
            raise OSError("simulated rename")

        monkeypatch.setattr("PHX2.stage19.writers.os.replace", boom)
        with pytest.raises(OSError, match="simulated"):
            W.write_ledger_csv(out, [_ledger_row()])
        assert not out.exists()
        assert not (tmp_path / "ledger.csv.tmp").exists()


# ===========================================================================
# write_summary_csv
# ===========================================================================


class TestWriteSummaryCsv:
    def test_emits_header_in_SUMMARY_COLUMNS_order(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "summary.csv"
        W.write_summary_csv(out, [_summary_row()])
        with out.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert tuple(header) == SUMMARY_COLUMNS

    def test_empty_rows_produces_header_only(self, tmp_path: Path) -> None:
        out = tmp_path / "summary.csv"
        W.write_summary_csv(out, [])
        text = out.read_text(encoding="utf-8")
        assert text == ",".join(SUMMARY_COLUMNS) + "\n"

    def test_deterministic_for_identical_input(self, tmp_path: Path) -> None:
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        rows = [_summary_row(rule_id=f"rule_{i}") for i in range(3)]
        W.write_summary_csv(a, rows)
        W.write_summary_csv(b, rows)
        assert a.read_bytes() == b.read_bytes()

    def test_atomic_no_partial_file_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "summary.csv"

        def boom(src, dst):  # noqa: ARG001
            raise OSError("simulated")

        monkeypatch.setattr("PHX2.stage19.writers.os.replace", boom)
        with pytest.raises(OSError):
            W.write_summary_csv(out, [_summary_row()])
        assert not out.exists()
        assert not (tmp_path / "summary.csv.tmp").exists()


# ===========================================================================
# write_readme_md
# ===========================================================================


class TestWriteReadmeMd:
    def test_includes_label_counts_section_with_all_labels(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "README.md"
        manifest = _base_manifest()
        manifest["label_counts"] = {
            label: i + 1 for i, label in enumerate(LABELS)
        }
        W.write_readme_md(out, manifest)
        text = out.read_text(encoding="utf-8")
        for label in LABELS:
            assert label in text

    def test_includes_schema_versions(self, tmp_path: Path) -> None:
        out = tmp_path / "README.md"
        W.write_readme_md(out, _base_manifest())
        text = out.read_text(encoding="utf-8")
        assert "stage19_schema_version" in text
        assert "stage19_ledger_v1" in text
        assert "stage19_version" in text
        assert "0.1.0" in text

    def test_includes_judgments_not_activation_reminder(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "README.md"
        W.write_readme_md(out, _base_manifest())
        text = out.read_text(encoding="utf-8")
        assert "review judgments" in text
        assert "not activation commands" in text

    def test_deterministic_for_identical_input(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        manifest = _base_manifest()
        W.write_readme_md(a, manifest)
        W.write_readme_md(b, manifest)
        assert a.read_bytes() == b.read_bytes()

    def test_run_timestamp_sourced_from_manifest(self, tmp_path: Path) -> None:
        out = tmp_path / "README.md"
        manifest = _base_manifest()
        manifest["run_timestamp_utc"] = "2099-12-31T23:59:59Z"
        W.write_readme_md(out, manifest)
        text = out.read_text(encoding="utf-8")
        assert "2099-12-31T23:59:59Z" in text

    def test_no_wall_clock_dates_outside_manifest(
        self, tmp_path: Path
    ) -> None:
        """The README must not contain any date-like string other
        than ones derived from the manifest (run_timestamp_utc).
        We sample a couple of frozen run_timestamp_utc values and
        confirm the README contains those and no other ISO-shaped
        dates."""

        import re as _re

        out = tmp_path / "README.md"
        manifest = _base_manifest()
        manifest["run_timestamp_utc"] = "2026-05-14T05:00:00Z"
        W.write_readme_md(out, manifest)
        text = out.read_text(encoding="utf-8")
        date_like = _re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text)
        assert date_like == ["2026-05-14T05:00:00Z"]

    def test_prior_ledger_dir_none_renders_as_none(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "README.md"
        W.write_readme_md(out, _base_manifest())
        text = out.read_text(encoding="utf-8")
        assert "`none`" in text

    def test_prior_ledger_schema_shown_when_present(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "README.md"
        manifest = _base_manifest()
        manifest["prior_ledger_dir"] = "/tmp/prior_run"
        manifest["prior_ledger_sha256"] = "f" * 64
        manifest["prior_ledger_schema_version"] = "stage19_ledger_v1"
        W.write_readme_md(out, manifest)
        text = out.read_text(encoding="utf-8")
        assert "prior_ledger_schema_version" in text

    def test_atomic_no_partial_file_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "README.md"

        def boom(src, dst):  # noqa: ARG001
            raise OSError("simulated")

        monkeypatch.setattr("PHX2.stage19.writers.os.replace", boom)
        with pytest.raises(OSError):
            W.write_readme_md(out, _base_manifest())
        assert not out.exists()
        assert not (tmp_path / "README.md.tmp").exists()


# ===========================================================================
# write_run_log
# ===========================================================================


class TestWriteRunLog:
    def test_lines_in_order(self, tmp_path: Path) -> None:
        out = tmp_path / "run.log"
        entries = ["a=1", "b=2", "c=3"]
        W.write_run_log(out, entries)
        text = out.read_text(encoding="utf-8")
        assert text == "a=1\nb=2\nc=3\n"

    def test_deterministic_for_identical_input(self, tmp_path: Path) -> None:
        a = tmp_path / "a.log"
        b = tmp_path / "b.log"
        entries = ["e1", "e2", "e3"]
        W.write_run_log(a, entries)
        W.write_run_log(b, entries)
        assert a.read_bytes() == b.read_bytes()

    def test_empty_entries_produces_empty_file(self, tmp_path: Path) -> None:
        out = tmp_path / "run.log"
        W.write_run_log(out, [])
        assert out.read_text(encoding="utf-8") == ""

    def test_atomic_no_partial_file_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "run.log"

        def boom(src, dst):  # noqa: ARG001
            raise OSError("simulated")

        monkeypatch.setattr("PHX2.stage19.writers.os.replace", boom)
        with pytest.raises(OSError):
            W.write_run_log(out, ["a=1"])
        assert not out.exists()
        assert not (tmp_path / "run.log.tmp").exists()
