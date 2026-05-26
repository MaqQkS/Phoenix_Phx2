"""Stage 29.5 migration evidence artifact reader tests.

Offline tests only. Artifact files are written into pytest's
``tmp_path`` per test; the reader is exercised against those
temporary files.

Pins:

  * A single-object JSON file yields one PRESENT or INVALID
    record with ``migration_source=STAGE29_MIGRATION_ARTIFACT``.
  * A JSON-array file yields one record per object.
  * A ``.jsonl`` file yields one record per non-empty line.
  * A missing-required-axis record yields ``INVALID``, NEVER
    fabricates the missing axis.
  * Unsupported ``kind`` records are silently skipped.
  * Malformed JSON, non-object payloads, non-existing paths,
    non-file paths, and over-budget files raise the closed-set
    :class:`Stage29_5MigrationEvidenceError`.
  * A record declaring ``migration_source=SYNTHETIC_TEST_ONLY``
    raises ``REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED``.
  * The reader NEVER emits ``HELIUS_WS`` or ``SYNTHETIC_TEST_ONLY``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage29.stage29_5_migration_artifact_reader import (
    STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL,
    STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL,
    STAGE29_5_MIGRATION_ARTIFACT_KIND,
    Stage29_5MigrationArtifactReader,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_BUDGET_EXCEEDED,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
    REFUSAL_REASON_UNREADABLE_ARTIFACT,
    Stage29_5MigrationEvidenceError,
)


# ---------------------------------------------------------------------------
# Fake fixtures
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "A" * 44
_SAFE_MINT_B: str = "B" * 44
_SAFE_POOL_A: str = "P" * 44
_SAFE_POOL_PROGRAM: str = "G" * 44
_SAFE_QUOTE: str = "Q" * 44
_SAFE_TIMESTAMP_A: str = "2026-05-25T00:00:00+00:00"
_SAFE_TIMESTAMP_B: str = "2026-05-25T01:00:00+00:00"
_SAFE_OBSERVED_AT: str = "2026-05-25T02:00:00+00:00"


def _well_formed_object(
    *,
    base_mint: str = _SAFE_MINT_A,
    observed_at_utc: str = _SAFE_OBSERVED_AT,
) -> dict:
    return {
        "kind": STAGE29_5_MIGRATION_ARTIFACT_KIND,
        "base_mint": base_mint,
        "pool_account": _SAFE_POOL_A,
        "pool_program_id": _SAFE_POOL_PROGRAM,
        "quote_mint": _SAFE_QUOTE,
        "migration_timestamp_utc": _SAFE_TIMESTAMP_A,
        "migration_slot": 123456,
        "migration_signature": "synth-sig-A",
        "source_event_ref": "synth-ref-A",
        "observed_at_utc": observed_at_utc,
    }


# ---------------------------------------------------------------------------
# JSON single-object file
# ---------------------------------------------------------------------------


def test_single_object_json_yields_one_present_record(
    tmp_path: Path,
):
    path = tmp_path / "ev.json"
    path.write_text(
        json.dumps(_well_formed_object()), encoding="utf-8"
    )
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_PRESENT
    )
    assert (
        records[0].migration_source
        == MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
    )
    assert records[0].base_mint == _SAFE_MINT_A


def test_single_object_with_missing_axis_yields_invalid(
    tmp_path: Path,
):
    obj = _well_formed_object()
    del obj["pool_account"]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_INVALID
    )
    assert records[0].pool_account is None
    assert records[0].base_mint == _SAFE_MINT_A


def test_array_yields_one_record_per_object(tmp_path: Path):
    arr = [
        _well_formed_object(base_mint=_SAFE_MINT_A),
        _well_formed_object(base_mint=_SAFE_MINT_B),
    ]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(arr), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 2
    base_mints = {r.base_mint for r in records}
    assert base_mints == {_SAFE_MINT_A, _SAFE_MINT_B}


def test_empty_array_yields_no_records(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text("[]", encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert records == ()


# ---------------------------------------------------------------------------
# JSONL file
# ---------------------------------------------------------------------------


def test_jsonl_file_yields_one_record_per_line(
    tmp_path: Path,
):
    path = tmp_path / "ev.jsonl"
    lines = [
        json.dumps(
            _well_formed_object(base_mint=_SAFE_MINT_A)
        ),
        "",  # blank line should be skipped silently
        json.dumps(
            _well_formed_object(base_mint=_SAFE_MINT_B)
        ),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 2


def test_jsonl_malformed_line_raises(tmp_path: Path):
    path = tmp_path / "ev.jsonl"
    path.write_text("{not-json", encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


# ---------------------------------------------------------------------------
# Unsupported-kind handling
# ---------------------------------------------------------------------------


def test_unsupported_kind_is_silently_skipped(tmp_path: Path):
    arr = [
        {"kind": "NOT_A_MIGRATION"},
        _well_formed_object(),
    ]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(arr), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_PRESENT
    )


def test_only_unsupported_kinds_yields_empty_tuple(
    tmp_path: Path,
):
    arr = [
        {"kind": "NOT_A_MIGRATION"},
        {"kind": "ALSO_NOT"},
    ]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(arr), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert records == ()


# ---------------------------------------------------------------------------
# Synthetic-source rejection
# ---------------------------------------------------------------------------


def test_synthetic_test_only_source_record_is_rejected(
    tmp_path: Path,
):
    obj = _well_formed_object()
    obj["migration_source"] = (
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
    )
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED
    )


def test_reader_never_emits_synthetic_source(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text(
        json.dumps(_well_formed_object()), encoding="utf-8"
    )
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    for r in records:
        assert (
            r.migration_source
            != MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
        )


def test_reader_never_emits_helius_ws_source(tmp_path: Path):
    obj = _well_formed_object()
    # Even if the artifact illegally claims HELIUS_WS, the
    # reader stamps STAGE29_MIGRATION_ARTIFACT verbatim.
    obj["migration_source"] = MIGRATION_SOURCE_HELIUS_WS
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(path)
    assert len(records) == 1
    assert (
        records[0].migration_source
        == MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
    )


# ---------------------------------------------------------------------------
# Malformed payloads and unreadable paths
# ---------------------------------------------------------------------------


def test_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text("{not-json", encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_top_level_string_raises(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text('"just-a-string"', encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_nonexistent_path_raises_unreadable(tmp_path: Path):
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(
            tmp_path / "does-not-exist.json"
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_UNREADABLE_ARTIFACT
    )


def test_directory_path_raises_unreadable(tmp_path: Path):
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(tmp_path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_UNREADABLE_ARTIFACT
    )


def test_non_string_path_raises(tmp_path: Path):
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(12345)  # type: ignore[arg-type]
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_UNREADABLE_ARTIFACT
    )


def test_string_path_accepted(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text(
        json.dumps(_well_formed_object()), encoding="utf-8"
    )
    reader = Stage29_5MigrationArtifactReader()
    records = reader.read_evidence_from_path(str(path))
    assert len(records) == 1


def test_observed_at_utc_required(tmp_path: Path):
    obj = _well_formed_object()
    del obj["observed_at_utc"]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_observed_at_utc_must_be_utc_shaped(tmp_path: Path):
    obj = _well_formed_object(
        observed_at_utc="2026-05-25T00:00:00-05:00"
    )
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader()
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


def test_over_budget_array_raises(tmp_path: Path):
    arr = [
        _well_formed_object(base_mint=_SAFE_MINT_A)
        for _ in range(5)
    ]
    path = tmp_path / "ev.json"
    path.write_text(json.dumps(arr), encoding="utf-8")
    reader = Stage29_5MigrationArtifactReader(
        max_records_per_call=2
    )
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        reader.read_evidence_from_path(path)
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_BUDGET_EXCEEDED
    )


def test_zero_budget_rejected_at_construction():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        Stage29_5MigrationArtifactReader(
            max_records_per_call=0
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_BUDGET_EXCEEDED
    )


def test_over_hard_max_budget_rejected_at_construction():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        Stage29_5MigrationArtifactReader(
            max_records_per_call=(
                STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL
                + 1
            )
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_BUDGET_EXCEEDED
    )


def test_default_budget_constant_matches():
    reader = Stage29_5MigrationArtifactReader()
    assert (
        reader._max_records_per_call
        == STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_repeated_reads(tmp_path: Path):
    path = tmp_path / "ev.json"
    path.write_text(
        json.dumps(_well_formed_object()), encoding="utf-8"
    )
    reader = Stage29_5MigrationArtifactReader()
    a = reader.read_evidence_from_path(path)
    b = reader.read_evidence_from_path(path)
    assert a == b
