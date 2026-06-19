"""Stage 30.14.1 evidence-artifact loader tests.

Covers: a full valid synthetic artifact loads + reconstructs without fabrication; every
missing / malformed / unsafe field fails closed with the EXACT closed-set reason; bad
source_ref / non-pump / unsafe redaction / non-empty warnings / incomplete measurement /
non-present / invalid source rejected; duplicate mint + signature deterministically deduped;
structural faults (unreadable / oversized / too-many-lines / too-many-records /
malformed-jsonl / wrong-schema / invalid-cap) raise; ``strict`` mode raises on a content
fault; redaction clean.

Offline only; the loader reads a pytest ``tmp_path`` JSONL file (read-only) and reads no env,
no clock, no network.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_STATUS_PRESENT,
    STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_loader import (
    Stage30_14_1EvidenceArtifactLoader,
    Stage30_14_1EvidenceLoadError,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_models import (
    BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION,
    LOAD_DECISION_ACCEPTED,
    LOAD_DECISION_REJECTED,
    LOAD_ERROR_FILE_TOO_LARGE,
    LOAD_ERROR_INVALID_CAP,
    LOAD_ERROR_MALFORMED_JSONL_LINE,
    LOAD_ERROR_TOO_MANY_LINES,
    LOAD_ERROR_TOO_MANY_RECORDS,
    LOAD_ERROR_UNREADABLE_ARTIFACT,
    LOAD_ERROR_WRONG_SCHEMA_VERSION,
    LOAD_REASON_ACCEPTED_FRESH_EVIDENCE,
    LOAD_REASON_BAD_SOURCE_REF,
    LOAD_REASON_DUPLICATE_MINT,
    LOAD_REASON_DUPLICATE_SIGNATURE,
    LOAD_REASON_INCOMPLETE_MEASUREMENT,
    LOAD_REASON_INVALID_SOURCE,
    LOAD_REASON_MALFORMED_TIMESTAMP,
    LOAD_REASON_MISSING_REQUIRED_FIELD,
    LOAD_REASON_NONEMPTY_WARNINGS,
    LOAD_REASON_NON_PRESENT_STATUS,
    LOAD_REASON_NOT_PUMP_SUFFIX,
    LOAD_REASON_UNSAFE_AXIS_SHAPE,
    LOAD_REASON_UNSAFE_REDACTION,
    STAGE30_14_1_REDACTION_STATUS_REDACTED,
    build_expected_source_ref,
)
from PHX2.tests.stage30.stage30_14_1_synthetic_evidence_fixtures import (
    SYNTH_MIGRATION_EVENT_TIME_UTC,
    SYNTH_MIGRATION_SIGNATURE,
    SYNTH_MIGRATION_SLOT,
    SYNTH_NON_PUMP_MINT,
    SYNTH_OBSERVED_AT_UTC,
    SYNTH_POOL_ACCOUNT,
    SYNTH_PUMP_MINT,
    SYNTH_QUOTE_MINT,
    SYNTH_SOURCE_SYNTHETIC_TEST_ONLY,
    build_second_valid_evidence_obj,
    build_valid_evidence_obj,
    write_jsonl,
    write_raw_lines,
)


_CREATED_AT: str = "2026-06-07T07:06:40Z"


def _load_objs(tmp_path, objs, **loader_kwargs):
    path = write_jsonl(tmp_path / "build26_capture_evidence.jsonl", objs)
    loader = Stage30_14_1EvidenceArtifactLoader(**loader_kwargs)
    return loader.load_evidence_from_path(path, created_at_utc=_CREATED_AT)


def _load_one(tmp_path, obj, **loader_kwargs):
    return _load_objs(tmp_path, [obj], **loader_kwargs)


def _reason_of_single(result) -> str:
    assert len(result.outcomes) == 1
    return result.outcomes[0].load_reason


# ---------------------------------------------------------------------------
# 1. Full valid artifact loads + reconstructs without fabrication
# ---------------------------------------------------------------------------


def test_full_valid_artifact_loads(tmp_path) -> None:
    result = _load_objs(
        tmp_path,
        [build_valid_evidence_obj(), build_second_valid_evidence_obj()],
    )
    assert result.summary.lines_seen == 2
    assert result.summary.accepted == 2
    assert result.summary.rejected == 0
    assert result.summary.duplicate == 0
    assert len(result.accepted_records) == 2
    assert len(result.accepted_attestations) == 2
    assert result.redaction_status == STAGE30_14_1_REDACTION_STATUS_REDACTED
    assert all(
        o.load_decision == LOAD_DECISION_ACCEPTED for o in result.outcomes
    )
    assert all(
        o.load_reason == LOAD_REASON_ACCEPTED_FRESH_EVIDENCE
        for o in result.outcomes
    )


def test_reconstruction_maps_fields_without_fabrication(tmp_path) -> None:
    result = _load_one(tmp_path, build_valid_evidence_obj())
    record = result.accepted_records[0]
    assert isinstance(record, Stage29_5MigrationEvidenceRecord)
    # Field renames reversed from the committed projection.
    assert record.base_mint == SYNTH_PUMP_MINT
    assert record.migration_timestamp_utc == SYNTH_MIGRATION_EVENT_TIME_UTC
    assert record.source_event_ref == build_expected_source_ref(
        SYNTH_MIGRATION_SIGNATURE, SYNTH_MIGRATION_SLOT
    )
    # Direct axes.
    assert record.migration_status == MIGRATION_STATUS_PRESENT
    assert record.pool_account == SYNTH_POOL_ACCOUNT
    assert record.quote_mint == SYNTH_QUOTE_MINT
    assert record.migration_slot == SYNTH_MIGRATION_SLOT
    assert record.migration_signature == SYNTH_MIGRATION_SIGNATURE
    assert record.observed_at_utc == SYNTH_OBSERVED_AT_UTC
    # schema_version is the record's own default -- never sourced from the artifact field.
    assert record.schema_version == STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
    # Persisted attestation captured for the verifier round-trip.
    att = result.accepted_attestations[0]
    assert att.token_mint == SYNTH_PUMP_MINT
    assert att.measurement_status == "COMPLETE"
    assert att.redaction_status == "SAFE"
    assert att.warnings == ()
    assert att.source_ref == record.source_event_ref


def test_synthetic_test_only_source_is_accepted(tmp_path) -> None:
    # The loader special-cases no source: a SYNTHETIC_TEST_ONLY-sourced line loads the same
    # way a HELIUS_WS one does (so a real HELIUS_WS artifact will load with no code change).
    result = _load_one(
        tmp_path,
        build_valid_evidence_obj(
            migration_source=SYNTH_SOURCE_SYNTHETIC_TEST_ONLY
        ),
    )
    assert result.summary.accepted == 1
    assert result.accepted_records[0].migration_source == (
        SYNTH_SOURCE_SYNTHETIC_TEST_ONLY
    )


# ---------------------------------------------------------------------------
# 2. Per-line content faults fail closed with the exact reason
# ---------------------------------------------------------------------------


def test_missing_field_rejected(tmp_path) -> None:
    obj = build_valid_evidence_obj()
    del obj["pool_account"]
    result = _load_one(tmp_path, obj)
    assert result.summary.accepted == 0
    assert _reason_of_single(result) == LOAD_REASON_MISSING_REQUIRED_FIELD
    assert result.outcomes[0].load_decision == LOAD_DECISION_REJECTED


def test_non_present_status_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"migration_status": "MISSING"}
    )
    assert _reason_of_single(result) == LOAD_REASON_NON_PRESENT_STATUS


def test_invalid_source_rejected(tmp_path) -> None:
    for bad in ("UNKNOWN", "NOT_A_SOURCE"):
        result = _load_one(
            tmp_path, build_valid_evidence_obj() | {"migration_source": bad}
        )
        assert _reason_of_single(result) == LOAD_REASON_INVALID_SOURCE


def test_non_pump_mint_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path, build_valid_evidence_obj(token_mint=SYNTH_NON_PUMP_MINT)
    )
    assert _reason_of_single(result) == LOAD_REASON_NOT_PUMP_SUFFIX


def test_unsafe_axis_shape_rejected(tmp_path) -> None:
    # too-short pool string
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"pool_account": "tooShort"}
    )
    assert _reason_of_single(result) == LOAD_REASON_UNSAFE_AXIS_SHAPE
    # negative slot
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"migration_slot": -1}
    )
    assert _reason_of_single(result) == LOAD_REASON_UNSAFE_AXIS_SHAPE
    # bool slot (must not coerce to 1/0)
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"migration_slot": True}
    )
    assert _reason_of_single(result) == LOAD_REASON_UNSAFE_AXIS_SHAPE
    # blank signature
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"migration_signature": "  "}
    )
    assert _reason_of_single(result) in (
        LOAD_REASON_UNSAFE_AXIS_SHAPE,
        LOAD_REASON_BAD_SOURCE_REF,
    )


def test_malformed_timestamp_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path,
        build_valid_evidence_obj()
        | {"migration_event_time_utc": "not-a-timestamp"},
    )
    assert _reason_of_single(result) == LOAD_REASON_MALFORMED_TIMESTAMP
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"observed_at_utc": "2026-13-40T99:99:99Z"}
    )
    assert _reason_of_single(result) == LOAD_REASON_MALFORMED_TIMESTAMP


def test_bad_source_ref_rejected(tmp_path) -> None:
    # Wrong form.
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"source_ref": "not-a-ref"}
    )
    assert _reason_of_single(result) == LOAD_REASON_BAD_SOURCE_REF
    # Right form but slot disagrees with the explicit migration_slot.
    mismatched = build_expected_source_ref(SYNTH_MIGRATION_SIGNATURE, 999)
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"source_ref": mismatched}
    )
    assert _reason_of_single(result) == LOAD_REASON_BAD_SOURCE_REF


def test_incomplete_measurement_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path,
        build_valid_evidence_obj()
        | {"measurement_status": "PARTIAL_MIGRATION_PRESENT"},
    )
    assert _reason_of_single(result) == LOAD_REASON_INCOMPLETE_MEASUREMENT


def test_unsafe_redaction_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"redaction_status": "REDACTED"}
    )
    assert _reason_of_single(result) == LOAD_REASON_UNSAFE_REDACTION


def test_nonempty_warnings_rejected(tmp_path) -> None:
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"warnings": ["MIGRATION_STALE"]}
    )
    assert _reason_of_single(result) == LOAD_REASON_NONEMPTY_WARNINGS
    # Non-list warnings is also rejected (not the required empty list).
    result = _load_one(
        tmp_path, build_valid_evidence_obj() | {"warnings": None}
    )
    assert _reason_of_single(result) == LOAD_REASON_NONEMPTY_WARNINGS


# ---------------------------------------------------------------------------
# 3. Duplicate handling (deterministic, first-wins)
# ---------------------------------------------------------------------------


def test_duplicate_mint_deduped(tmp_path) -> None:
    obj = build_valid_evidence_obj()
    result = _load_objs(tmp_path, [obj, dict(obj)])
    assert result.summary.accepted == 1
    assert result.summary.duplicate == 1
    assert result.summary.rejected == 0
    assert result.outcomes[0].load_decision == LOAD_DECISION_ACCEPTED
    assert result.outcomes[1].load_reason == LOAD_REASON_DUPLICATE_MINT


def test_duplicate_signature_deduped(tmp_path) -> None:
    first = build_valid_evidence_obj()
    # Distinct mint, SAME signature + slot -> same source_ref -> duplicate signature.
    second = build_second_valid_evidence_obj(
        migration_signature=SYNTH_MIGRATION_SIGNATURE
    )
    result = _load_objs(tmp_path, [first, second])
    assert result.summary.accepted == 1
    assert result.summary.duplicate == 1
    assert result.outcomes[1].load_reason == LOAD_REASON_DUPLICATE_SIGNATURE


# ---------------------------------------------------------------------------
# 4. Structural faults raise
# ---------------------------------------------------------------------------


def test_unreadable_artifact_raises(tmp_path) -> None:
    loader = Stage30_14_1EvidenceArtifactLoader()
    missing = tmp_path / "does_not_exist.jsonl"
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        loader.load_evidence_from_path(missing, created_at_utc=_CREATED_AT)
    assert exc.value.reason == LOAD_ERROR_UNREADABLE_ARTIFACT


def test_non_path_argument_raises(tmp_path) -> None:
    loader = Stage30_14_1EvidenceArtifactLoader()
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        loader.load_evidence_from_path(1234, created_at_utc=_CREATED_AT)
    assert exc.value.reason == LOAD_ERROR_UNREADABLE_ARTIFACT


def test_oversized_file_raises(tmp_path) -> None:
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_objs(tmp_path, [build_valid_evidence_obj()], max_bytes=10)
    assert exc.value.reason == LOAD_ERROR_FILE_TOO_LARGE


def test_too_many_lines_raises(tmp_path) -> None:
    objs = [
        build_valid_evidence_obj(),
        build_second_valid_evidence_obj(),
        build_valid_evidence_obj(
            token_mint="Synth26Evidence" + ("C" * 25) + "pump",
            migration_signature="sig-c",
        ),
    ]
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_objs(tmp_path, objs, max_lines=2)
    assert exc.value.reason == LOAD_ERROR_TOO_MANY_LINES


def test_too_many_records_raises(tmp_path) -> None:
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_objs(
            tmp_path,
            [build_valid_evidence_obj(), build_second_valid_evidence_obj()],
            max_accepted=1,
        )
    assert exc.value.reason == LOAD_ERROR_TOO_MANY_RECORDS


def test_malformed_jsonl_line_raises(tmp_path) -> None:
    path = write_raw_lines(
        tmp_path / "bad.jsonl", ['{"unterminated": true']
    )
    loader = Stage30_14_1EvidenceArtifactLoader()
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        loader.load_evidence_from_path(path, created_at_utc=_CREATED_AT)
    assert exc.value.reason == LOAD_ERROR_MALFORMED_JSONL_LINE


def test_non_object_jsonl_line_raises(tmp_path) -> None:
    path = write_raw_lines(tmp_path / "arr.jsonl", ["[1, 2, 3]"])
    loader = Stage30_14_1EvidenceArtifactLoader()
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        loader.load_evidence_from_path(path, created_at_utc=_CREATED_AT)
    assert exc.value.reason == LOAD_ERROR_MALFORMED_JSONL_LINE


def test_wrong_schema_version_raises(tmp_path) -> None:
    result_obj = build_valid_evidence_obj() | {"schema_version": "wrong_v9"}
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_one(tmp_path, result_obj)
    assert exc.value.reason == LOAD_ERROR_WRONG_SCHEMA_VERSION


def test_missing_schema_version_raises(tmp_path) -> None:
    obj = build_valid_evidence_obj()
    del obj["schema_version"]
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_one(tmp_path, obj)
    assert exc.value.reason == LOAD_ERROR_WRONG_SCHEMA_VERSION


def test_invalid_cap_raises() -> None:
    for kwargs in (
        {"max_bytes": 0},
        {"max_lines": 0},
        {"max_accepted": 0},
        {"max_bytes": 9_999_999_999},
    ):
        with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
            Stage30_14_1EvidenceArtifactLoader(**kwargs)
        assert exc.value.reason == LOAD_ERROR_INVALID_CAP


# ---------------------------------------------------------------------------
# 5. Strict mode raises on a content fault
# ---------------------------------------------------------------------------


def test_strict_mode_raises_on_content_fault(tmp_path) -> None:
    obj = build_valid_evidence_obj(token_mint=SYNTH_NON_PUMP_MINT)
    with pytest.raises(Stage30_14_1EvidenceLoadError) as exc:
        _load_one(tmp_path, obj, strict=True)
    assert exc.value.reason == LOAD_REASON_NOT_PUMP_SUFFIX


def test_strict_mode_accepts_valid(tmp_path) -> None:
    result = _load_one(tmp_path, build_valid_evidence_obj(), strict=True)
    assert result.summary.accepted == 1


# ---------------------------------------------------------------------------
# 6. Empty artifact loads cleanly (no records, no raise)
# ---------------------------------------------------------------------------


def test_empty_artifact_loads_empty(tmp_path) -> None:
    path = write_raw_lines(tmp_path / "empty.jsonl", ["", "   "])
    loader = Stage30_14_1EvidenceArtifactLoader()
    result = loader.load_evidence_from_path(path, created_at_utc=_CREATED_AT)
    assert result.summary.lines_seen == 0
    assert result.accepted_records == ()
    assert result.redaction_status == STAGE30_14_1_REDACTION_STATUS_REDACTED
