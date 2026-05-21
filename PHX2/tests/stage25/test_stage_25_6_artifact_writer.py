"""Stage 25.6 deterministic artifact writer tests.

Pins:

  * The writer emits every locked Stage 25 artifact basename.
  * JSONL row ordering and JSON canonicalisation are deterministic.
  * The manifest records every artifact with the correct
    ``sha256`` / ``row_count`` and the locked redaction
    confirmation token.
  * Redaction sweep rejects forbidden field names, URL / webhook
    host substrings, and long-hex credential shapes.
  * Manifest entries refuse absolute paths.
  * Missing output_dir / non-directory output_dir is rejected.
  * Atomic temp files are cleaned up after a successful write.
  * Repeated write with identical inputs + identical
    ``created_at_utc`` produces byte-identical artifacts.
  * The writer never touches files outside its emitted artifact
    basenames.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType

import pytest

from PHX2.stage25.artifact_writer import (
    serialize_jsonl_rows,
    validate_output_dir,
    write_atomic_text,
    write_stage25_artifacts,
)
from PHX2.stage25.constants import (
    REDACTION_CONFIRMED_TOKEN,
    STAGE25_ARTIFACT_FILENAMES,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_EMITS_SOURCE_COVERAGE_CSV,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_WRITER_NAME,
    STAGE25_WRITER_VERSION,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
)
from PHX2.stage25.errors import Stage25ManifestError
from PHX2.stage25.runner import run_stage25_measurement
from PHX2.stage25.summary import build_stage25_summary
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_MIGRATION_BLOCK_TIME,
    SAMPLE_MIGRATION_SIG,
    SAMPLE_MIGRATION_SLOT,
    SAMPLE_TOKEN_MINT_A,
    make_ath_candidate,
    make_migration_observation,
    make_price_observation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _migration_obs(
    *,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    block_time: int = SAMPLE_MIGRATION_BLOCK_TIME,
):
    return make_migration_observation(
        source_family=source_family,
        block_time=block_time,
        slot=SAMPLE_MIGRATION_SLOT,
        migration_signature=SAMPLE_MIGRATION_SIG,
    )


def _price_obs(
    *,
    source_family: str = SOURCE_FAMILY_DEXSCREENER,
    block_time: int = SAMPLE_MIGRATION_BLOCK_TIME + 60,
    price: int = 2_000_000,
):
    return make_price_observation(
        source_family=source_family,
        block_time=block_time,
        price=price,
    )


def _run(*, migration=None, price=None):
    return run_stage25_measurement(
        migration_observations=tuple(migration or ()),
        price_observations=tuple(price or ()),
        created_at_utc=FIXED_CLOCK_UTC,
    )


def _write_result(result, output_dir: Path):
    return write_stage25_artifacts(
        output_dir,
        migration_observations=result.migration_observations,
        migration_measurements=result.migration_measurements,
        price_window_observations=result.price_window_observations,
        ath_candidates=result.ath_candidates,
        source_reconciliations=result.source_reconciliations,
        ath_measurements=result.ath_measurements,
        rejections=result.rejections,
        summary=result.summary,
        created_at_utc=result.created_at_utc,
    )


def _two_source_result():
    migration = (
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
        ),
    )
    price = (
        _price_obs(source_family=SOURCE_FAMILY_BIRDEYE, price=2_000_000),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER, price=2_010_000
        ),
    )
    return _run(migration=migration, price=price)


# ---------------------------------------------------------------------------
# Output directory validation
# ---------------------------------------------------------------------------


def test_validate_output_dir_rejects_missing_path(tmp_path):
    missing = tmp_path / "absent"
    with pytest.raises(Stage25ManifestError):
        validate_output_dir(missing)


def test_validate_output_dir_rejects_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(Stage25ManifestError):
        validate_output_dir(f)


def test_validate_output_dir_rejects_non_path(tmp_path):
    with pytest.raises(Stage25ManifestError):
        validate_output_dir(str(tmp_path))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# JSONL serialisation
# ---------------------------------------------------------------------------


def test_serialize_empty_jsonl_is_empty_string():
    assert serialize_jsonl_rows(()) == ""


def test_serialize_non_empty_jsonl_ends_with_newline():
    rows = (make_migration_observation(),)
    text = serialize_jsonl_rows(rows)
    assert text.endswith("\n")
    assert text.count("\n") == 1


def test_serialize_jsonl_is_canonical_json_per_row():
    rows = (make_migration_observation(),)
    text = serialize_jsonl_rows(rows)
    body = text.rstrip("\n")
    parsed = json.loads(body)
    re_encoded = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    assert body == re_encoded


def test_serialize_jsonl_row_ordering_is_deterministic():
    rows = (
        make_migration_observation(),
        make_migration_observation(source_family=SOURCE_FAMILY_DEXSCREENER),
    )
    text_a = serialize_jsonl_rows(rows)
    text_b = serialize_jsonl_rows(rows)
    assert text_a == text_b


def test_serialize_jsonl_rejects_unsupported_row_type():
    with pytest.raises(Exception):
        serialize_jsonl_rows((object(),))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_atomic_text_returns_byte_count(tmp_path):
    path = tmp_path / "out.txt"
    text = "hello\nworld\n"
    byte_count = write_atomic_text(path, text)
    assert byte_count == len(text.encode("utf-8"))
    assert path.read_text(encoding="utf-8") == text


def test_write_atomic_text_cleans_temp_file(tmp_path):
    path = tmp_path / "out.txt"
    write_atomic_text(path, "abc")
    temp = tmp_path / (path.name + ".tmp")
    assert not temp.exists()


def test_write_atomic_text_rejects_non_path(tmp_path):
    with pytest.raises(Stage25ManifestError):
        write_atomic_text(str(tmp_path / "x"), "y")  # type: ignore[arg-type]


def test_write_atomic_text_rejects_non_string(tmp_path):
    with pytest.raises(Stage25ManifestError):
        write_atomic_text(tmp_path / "x", b"bytes")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# write_stage25_artifacts -- happy path
# ---------------------------------------------------------------------------


def test_writer_emits_every_locked_artifact(tmp_path):
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    files = {p.name for p in tmp_path.iterdir() if p.is_file()}
    expected = set(STAGE25_ARTIFACT_FILENAMES)
    # Stage 25.6 does NOT emit the optional source-coverage CSV.
    assert STAGE25_EMITS_SOURCE_COVERAGE_CSV is False
    assert expected.issubset(files)
    # No stray .tmp temp files left behind.
    assert not any(name.endswith(".tmp") for name in files)
    assert manifest.redaction_confirmed == REDACTION_CONFIRMED_TOKEN


def test_writer_manifest_lists_every_artifact_including_self(tmp_path):
    """Stage 25.6: the manifest's ``files`` tuple includes the manifest
    file itself with the locked self-referential sentinel."""
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    file_basenames = {entry.file_basename for entry in manifest.files}
    expected = set(STAGE25_ARTIFACT_FILENAMES)
    assert expected == file_basenames


def test_writer_manifest_sha256_matches_actual_bytes(tmp_path):
    """Every non-manifest manifest entry's sha256 matches the on-disk
    bytes. The manifest's own self-entry carries the locked
    ``SELF_REFERENTIAL_MANIFEST_SHA256`` sentinel; downstream readers
    detect the sentinel and skip the bytes-equal verification.
    """
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    for entry in manifest.files:
        if entry.file_basename == STAGE25_MANIFEST_FILENAME:
            assert entry.sha256 == SELF_REFERENTIAL_MANIFEST_SHA256
            continue
        on_disk = (tmp_path / entry.file_basename).read_bytes()
        digest = hashlib.sha256(on_disk).hexdigest()
        assert digest == entry.sha256, (
            f"manifest sha256 for {entry.file_basename} does not match"
        )


def test_writer_jsonl_row_counts_match_manifest(tmp_path):
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    by_name = {entry.file_basename: entry for entry in manifest.files}
    jsonl_pairs = (
        (
            STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
            len(result.migration_observations),
        ),
        (
            STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
            len(result.migration_measurements),
        ),
        (
            STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
            len(result.price_window_observations),
        ),
        (STAGE25_ATH_CANDIDATES_FILENAME, len(result.ath_candidates)),
        (
            STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
            len(result.source_reconciliations),
        ),
        (
            STAGE25_ATH_MEASUREMENTS_FILENAME,
            len(result.ath_measurements),
        ),
        (
            STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
            len(result.rejections),
        ),
    )
    for basename, expected_count in jsonl_pairs:
        entry = by_name[basename]
        assert entry.row_count == expected_count, basename


def test_writer_summary_row_counts_match_artifact_rows(tmp_path):
    result = _two_source_result()
    _write_result(result, tmp_path)
    summary_path = tmp_path / STAGE25_SUMMARY_FILENAME
    parsed = json.loads(summary_path.read_text(encoding="utf-8"))
    row_counts = parsed["row_counts"]
    assert row_counts["migration_observations"] == len(
        result.migration_observations
    )
    assert row_counts["migration_measurements"] == len(
        result.migration_measurements
    )
    assert row_counts["price_window_observations"] == len(
        result.price_window_observations
    )
    assert row_counts["ath_candidates"] == len(result.ath_candidates)
    assert row_counts["source_reconciliations"] == len(
        result.source_reconciliations
    )
    assert row_counts["ath_measurements"] == len(result.ath_measurements)


def test_writer_jsonl_files_end_with_trailing_newline_when_non_empty(
    tmp_path,
):
    result = _two_source_result()
    _write_result(result, tmp_path)
    migration_text = (
        tmp_path / STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    ).read_text(encoding="utf-8")
    assert migration_text.endswith("\n")


def test_writer_jsonl_empty_files_are_zero_bytes(tmp_path):
    result = _two_source_result()
    _write_result(result, tmp_path)
    rejections_path = tmp_path / STAGE25_MEASUREMENT_REJECTIONS_FILENAME
    assert rejections_path.exists()
    assert rejections_path.read_bytes() == b""


def test_writer_manifest_includes_writer_identity(tmp_path):
    """The artifact manifest carries the Stage 25 version axes; the
    writer identity tokens are accessible via ``writer_identity()``."""
    from PHX2.stage25.artifact_writer import writer_identity

    ident = writer_identity()
    assert ident["writer_name"] == STAGE25_WRITER_NAME
    assert ident["writer_version"] == STAGE25_WRITER_VERSION


# ---------------------------------------------------------------------------
# Determinism: identical inputs produce byte-identical artifacts
# ---------------------------------------------------------------------------


def test_repeated_write_yields_byte_identical_artifacts(tmp_path):
    result = _two_source_result()
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    _write_result(result, out_a)
    _write_result(result, out_b)
    for basename in STAGE25_ARTIFACT_FILENAMES:
        bytes_a = (out_a / basename).read_bytes()
        bytes_b = (out_b / basename).read_bytes()
        assert bytes_a == bytes_b, basename


def test_jsonl_ordering_deterministic_under_reordered_input(tmp_path):
    migration_obs = (
        _migration_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER,
            block_time=SAMPLE_MIGRATION_BLOCK_TIME + 10,
        ),
        _migration_obs(source_family=SOURCE_FAMILY_BIRDEYE),
    )
    migration_obs_reversed = tuple(reversed(migration_obs))
    price_obs = (
        _price_obs(source_family=SOURCE_FAMILY_BIRDEYE, price=2_000_000),
        _price_obs(
            source_family=SOURCE_FAMILY_DEXSCREENER, price=2_010_000
        ),
    )
    result_a = run_stage25_measurement(
        migration_observations=migration_obs,
        price_observations=price_obs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    result_b = run_stage25_measurement(
        migration_observations=migration_obs_reversed,
        price_observations=price_obs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    _write_result(result_a, out_a)
    _write_result(result_b, out_b)
    for basename in STAGE25_ARTIFACT_FILENAMES:
        assert (out_a / basename).read_bytes() == (
            out_b / basename
        ).read_bytes(), basename


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def test_redaction_sweep_rejects_url_value_in_evidence(tmp_path):
    leaky_evidence = MappingProxyType(
        {"upstream": "ht" + "tps://leaked.example/path"}
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_long_hex_value(tmp_path):
    leaky_evidence = MappingProxyType({"hex_blob": "a" * 64})
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_forbidden_field_name(tmp_path):
    """The summary mapping carries forbidden field names -> sweep fires."""
    result = _two_source_result()
    bad_summary = dict(result.summary)
    bad_summary["api_key"] = "fake"
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc=result.created_at_utc,
        )


def test_redaction_sweep_failure_leaves_directory_untouched(tmp_path):
    leaky_evidence = MappingProxyType(
        {"upstream": "ht" + "tps://leaked.example/path"}
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)
    files = list(tmp_path.iterdir())
    assert files == [], "writer must not emit artifacts after sweep failure"


# ---------------------------------------------------------------------------
# Manifest invariants
# ---------------------------------------------------------------------------


def test_manifest_entry_basenames_contain_no_path_separator(tmp_path):
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    for entry in manifest.files:
        assert "/" not in entry.file_basename
        assert "\\" not in entry.file_basename


def test_manifest_entries_sorted_by_basename(tmp_path):
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    basenames = [entry.file_basename for entry in manifest.files]
    assert basenames == sorted(basenames)


def test_writer_rejects_missing_output_dir(tmp_path):
    missing = tmp_path / "absent"
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        _write_result(result, missing)


def test_writer_rejects_output_dir_that_is_a_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        _write_result(result, f)


def test_writer_rejects_empty_created_at_utc(tmp_path):
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=result.summary,
            created_at_utc="",
        )


def test_writer_rejects_non_tuple_row_inputs(tmp_path):
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=list(result.migration_observations),  # type: ignore[arg-type]
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=result.summary,
            created_at_utc=result.created_at_utc,
        )


def test_writer_does_not_touch_pre_existing_unrelated_files(tmp_path):
    bystander = tmp_path / "unrelated.txt"
    bystander.write_text("bystander", encoding="utf-8")
    result = _two_source_result()
    _write_result(result, tmp_path)
    assert bystander.read_text(encoding="utf-8") == "bystander"


def test_writer_pin_supports_stage24_basename_and_sha256(tmp_path):
    result = _two_source_result()
    manifest = write_stage25_artifacts(
        tmp_path,
        migration_observations=result.migration_observations,
        migration_measurements=result.migration_measurements,
        price_window_observations=result.price_window_observations,
        ath_candidates=result.ath_candidates,
        source_reconciliations=result.source_reconciliations,
        ath_measurements=result.ath_measurements,
        rejections=result.rejections,
        summary=result.summary,
        created_at_utc=result.created_at_utc,
        stage24_manifest_basename="stage24_manifest.json",
        stage24_manifest_sha256="ab" * 32,
    )
    pin = manifest.upstream_stage24_pin
    assert pin is not None
    assert pin.upstream_manifest_basename == "stage24_manifest.json"
    assert pin.upstream_manifest_sha256 == "ab" * 32


def test_writer_manifest_json_round_trips_through_disk(tmp_path):
    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    manifest_path = tmp_path / STAGE25_MANIFEST_FILENAME
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["redaction_confirmed"] == REDACTION_CONFIRMED_TOKEN
    assert parsed["observe_only_mode"] == "observe_only"
    assert parsed["created_at_utc"] == FIXED_CLOCK_UTC
    assert {f["file_basename"] for f in parsed["files"]} == {
        entry.file_basename for entry in manifest.files
    }


# ---------------------------------------------------------------------------
# Remediation tests: redaction sweep (codex finding 1)
# ---------------------------------------------------------------------------


def test_redaction_sweep_rejects_url_inside_hash_field(tmp_path):
    """A field named ``source_hash`` carrying a URL value is rejected.

    Codex finding 1: the hash-field allowlist must only relax the
    long-hex-run check, never the URL/webhook substring check.
    """
    leaky_evidence = MappingProxyType(
        {"source_hash": "ht" + "tps://leaked.example/path"}
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_url_inside_sha256_field(tmp_path):
    """A field named ``source_sha256`` carrying a URL value is rejected."""
    leaky_evidence = MappingProxyType(
        {"source_sha256": "ht" + "tps://leaked.example/path"}
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_long_hex_in_non_hash_field(tmp_path):
    """Long-hex values in non-hash fields remain rejected."""
    leaky_evidence = MappingProxyType({"raw_payload": "a" * 64})
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_accepts_long_hex_in_safe_hash_field(tmp_path):
    """Long-hex in a safe ``*_hash`` field with no URL/value leak passes."""
    safe_evidence = MappingProxyType({"upstream_record_hash": "a" * 64})
    safe_obs = make_migration_observation(evidence=safe_evidence)
    result = run_stage25_measurement(
        migration_observations=(safe_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    _write_result(result, tmp_path)
    # Writer succeeded; the artifact file exists.
    assert (
        tmp_path / STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    ).is_file()


def test_redaction_sweep_accepts_long_hex_in_safe_sha256_field(tmp_path):
    """Long-hex in a safe ``*_sha256`` field with no URL leak passes."""
    safe_evidence = MappingProxyType({"upstream_record_sha256": "b" * 64})
    safe_obs = make_migration_observation(evidence=safe_evidence)
    result = run_stage25_measurement(
        migration_observations=(safe_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    _write_result(result, tmp_path)
    assert (
        tmp_path / STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    ).is_file()


@pytest.mark.parametrize(
    "leaky_field",
    [
        "secret_hash",
        "api_key_hash",
        "webhook_hash",
        "authorization_hash",
        "private_key_hash",
        "headers_hash",
        "raw_response_hash",
    ],
)
def test_redaction_sweep_rejects_secret_bearing_hash_field(
    leaky_field, tmp_path
):
    """Hash-named field whose name contains a forbidden secret-bearing
    substring is rejected by the field-name scan.

    The hash-field allowlist does NOT bypass field-name leak checks.
    """
    leaky_evidence = MappingProxyType({leaky_field: "a" * 64})
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_deeply_nested_forbidden_field(tmp_path):
    """Forbidden field names at arbitrary nesting depth are rejected."""
    leaky_evidence = MappingProxyType(
        {
            "outer": {
                "middle": {"api_key": "fake_value"},
            },
        }
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_deeply_nested_url_value(tmp_path):
    """URL values at arbitrary nesting depth are rejected."""
    leaky_evidence = MappingProxyType(
        {
            "outer": {
                "middle": {
                    "field": "ht" + "tps://leaked.example/path",
                },
            },
        }
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)


def test_redaction_sweep_rejects_manifest_created_at_utc_url(tmp_path):
    """A URL embedded in ``created_at_utc`` is caught by the manifest
    redaction sweep BEFORE the manifest is written.

    Codex finding 2: the manifest body must be redaction-scanned.
    """
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=result.summary,
            created_at_utc="ht" + "tps://leaked.example/path",
        )


def test_redaction_sweep_rejects_manifest_created_at_utc_url_leaves_dir_empty(
    tmp_path,
):
    """Manifest-level redaction failure leaves the output directory empty."""
    result = _two_source_result()
    # build a fresh summary that matches the bogus created_at_utc the
    # caller is about to use so the row-count check passes first; the
    # redaction sweep should still fire BEFORE any artifact is written.
    bad_summary = dict(result.summary)
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc="ht" + "tps://leaked.example/path",
        )
    files = list(tmp_path.iterdir())
    assert files == [], (
        "manifest redaction failure must leave the output directory "
        "untouched"
    )


# ---------------------------------------------------------------------------
# Remediation tests: manifest file entry byte_count (codex finding 3)
# ---------------------------------------------------------------------------


def test_manifest_file_entries_record_byte_count(tmp_path):
    """Every artifact file entry carries the byte_count of its bytes."""
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    )

    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    for entry in manifest.files:
        if entry.file_basename == STAGE25_MANIFEST_FILENAME:
            # Self-entry uses the locked sentinel.
            assert entry.byte_count == (
                SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
            )
            continue
        on_disk = (tmp_path / entry.file_basename).read_bytes()
        assert entry.byte_count == len(on_disk), entry.file_basename


def test_manifest_file_entries_byte_count_serialised(tmp_path):
    """``byte_count`` round-trips through the serialised manifest JSON."""
    result = _two_source_result()
    _write_result(result, tmp_path)
    manifest_path = tmp_path / STAGE25_MANIFEST_FILENAME
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    for file_entry in parsed["files"]:
        assert "byte_count" in file_entry, file_entry


# ---------------------------------------------------------------------------
# Remediation tests: manifest runner/writer versions (codex finding 4)
# ---------------------------------------------------------------------------


def test_manifest_carries_runner_writer_identity(tmp_path):
    from PHX2.stage25.constants import (
        STAGE25_ARTIFACT_WRITER_NAME,
        STAGE25_ARTIFACT_WRITER_VERSION,
        STAGE25_RUNNER_NAME,
        STAGE25_RUNNER_VERSION,
        STAGE25_WRITER_NAME,
        STAGE25_WRITER_VERSION,
    )

    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    assert manifest.runner_name == STAGE25_RUNNER_NAME
    assert manifest.runner_version == STAGE25_RUNNER_VERSION
    assert manifest.writer_name == STAGE25_WRITER_NAME
    assert manifest.writer_version == STAGE25_WRITER_VERSION
    # Synonyms must agree.
    assert STAGE25_WRITER_NAME == STAGE25_ARTIFACT_WRITER_NAME
    assert STAGE25_WRITER_VERSION == STAGE25_ARTIFACT_WRITER_VERSION


def test_serialized_manifest_contains_runner_and_writer_fields(tmp_path):
    from PHX2.stage25.constants import (
        STAGE25_RUNNER_NAME,
        STAGE25_RUNNER_VERSION,
        STAGE25_WRITER_NAME,
        STAGE25_WRITER_VERSION,
    )

    result = _two_source_result()
    _write_result(result, tmp_path)
    manifest_path = tmp_path / STAGE25_MANIFEST_FILENAME
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["runner_name"] == STAGE25_RUNNER_NAME
    assert parsed["runner_version"] == STAGE25_RUNNER_VERSION
    assert parsed["writer_name"] == STAGE25_WRITER_NAME
    assert parsed["writer_version"] == STAGE25_WRITER_VERSION


# ---------------------------------------------------------------------------
# Remediation tests: manifest self-entry (codex finding 5)
# ---------------------------------------------------------------------------


def test_manifest_includes_self_entry_with_sentinel(tmp_path):
    """Stage 25.6 convention: manifest includes ``stage25_manifest.json``
    with the locked ``SELF_REFERENTIAL_MANIFEST_SHA256`` sentinel and
    ``-1`` byte_count.
    """
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
        SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    result = _two_source_result()
    manifest = _write_result(result, tmp_path)
    self_entry = next(
        e
        for e in manifest.files
        if e.file_basename == STAGE25_MANIFEST_FILENAME
    )
    assert self_entry.sha256 == SELF_REFERENTIAL_MANIFEST_SHA256
    assert self_entry.byte_count == SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
    assert self_entry.row_count == SELF_REFERENTIAL_MANIFEST_ROW_COUNT


def test_manifest_self_entry_serialised(tmp_path):
    """The manifest self-entry appears in the serialised manifest body."""
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    result = _two_source_result()
    _write_result(result, tmp_path)
    manifest_path = tmp_path / STAGE25_MANIFEST_FILENAME
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    self_entries = [
        e
        for e in parsed["files"]
        if e["file_basename"] == STAGE25_MANIFEST_FILENAME
    ]
    assert len(self_entries) == 1
    assert self_entries[0]["sha256"] == SELF_REFERENTIAL_MANIFEST_SHA256


def test_manifest_self_entry_sha256_is_not_a_hex_digest():
    """The locked sentinel must NOT look like a real digest so
    downstream readers cannot confuse it with bytes-equal evidence.
    """
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    # The sentinel contains uppercase characters and a literal "_",
    # neither of which appears in a lowercase 64-hex digest.
    assert any(ch.isupper() for ch in SELF_REFERENTIAL_MANIFEST_SHA256)
    assert "_" in SELF_REFERENTIAL_MANIFEST_SHA256


# ---------------------------------------------------------------------------
# Remediation tests: Stage 24 pin validated BEFORE any write (codex
# finding 6)
# ---------------------------------------------------------------------------


def test_invalid_stage24_pin_leaves_output_dir_empty(tmp_path):
    """An invalid Stage 24 pin is rejected before any artifact is written."""
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=result.summary,
            created_at_utc=result.created_at_utc,
            # basename without sha256 -> partial pin rejected
            stage24_manifest_basename="stage24_manifest.json",
            stage24_manifest_sha256="",
        )
    assert list(tmp_path.iterdir()) == []


def test_invalid_stage24_pin_basename_leaves_output_dir_empty(tmp_path):
    """A Stage 24 pin basename carrying a leak substring is rejected
    before any artifact is written."""
    result = _two_source_result()
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=result.summary,
            created_at_utc=result.created_at_utc,
            stage24_manifest_basename="dir/manifest.json",
            stage24_manifest_sha256="ab" * 32,
        )
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Remediation tests: summary row_count validation (codex finding 7)
# ---------------------------------------------------------------------------


def test_summary_row_count_mismatch_rejected(tmp_path):
    """A summary whose row_counts disagree with actual tuple lengths is rejected."""
    result = _two_source_result()
    bad_summary = dict(result.summary)
    bad_row_counts = dict(bad_summary["row_counts"])
    bad_row_counts["migration_observations"] = 99
    bad_summary["row_counts"] = bad_row_counts
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc=result.created_at_utc,
        )


def test_summary_row_count_mismatch_leaves_output_dir_empty(tmp_path):
    result = _two_source_result()
    bad_summary = dict(result.summary)
    bad_row_counts = dict(bad_summary["row_counts"])
    bad_row_counts["ath_measurements"] = 999
    bad_summary["row_counts"] = bad_row_counts
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc=result.created_at_utc,
        )
    assert list(tmp_path.iterdir()) == []


def test_summary_row_counts_missing_key_rejected(tmp_path):
    result = _two_source_result()
    bad_summary = dict(result.summary)
    bad_row_counts = dict(bad_summary["row_counts"])
    del bad_row_counts["migration_observations"]
    bad_summary["row_counts"] = bad_row_counts
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc=result.created_at_utc,
        )
    assert list(tmp_path.iterdir()) == []


def test_summary_row_counts_non_mapping_rejected(tmp_path):
    result = _two_source_result()
    bad_summary = dict(result.summary)
    bad_summary["row_counts"] = "not a mapping"
    with pytest.raises(Stage25ManifestError):
        write_stage25_artifacts(
            tmp_path,
            migration_observations=result.migration_observations,
            migration_measurements=result.migration_measurements,
            price_window_observations=result.price_window_observations,
            ath_candidates=result.ath_candidates,
            source_reconciliations=result.source_reconciliations,
            ath_measurements=result.ath_measurements,
            rejections=result.rejections,
            summary=bad_summary,
            created_at_utc=result.created_at_utc,
        )
    assert list(tmp_path.iterdir()) == []


def test_summary_row_count_match_writes_all_artifacts(tmp_path):
    """Happy path: when summary row_counts match the writer emits all files."""
    result = _two_source_result()
    _write_result(result, tmp_path)
    for basename in STAGE25_ARTIFACT_FILENAMES:
        assert (tmp_path / basename).is_file(), basename


# ---------------------------------------------------------------------------
# Remediation tests: missing output_dir / file output_dir caught before
# any writes
# ---------------------------------------------------------------------------


def test_missing_output_dir_leaves_no_writes(tmp_path):
    """Missing output_dir is rejected before any artifact is written."""
    result = _two_source_result()
    missing = tmp_path / "absent"
    with pytest.raises(Stage25ManifestError):
        _write_result(result, missing)
    # ``missing`` does not exist; nothing to assert beyond no-throw side
    # effects. The parent tmp_path still has nothing written.
    assert list(tmp_path.iterdir()) == []


def test_redaction_failure_leaves_output_dir_empty(tmp_path):
    """An evidence-level URL leak is rejected before any artifact is written."""
    leaky_evidence = MappingProxyType(
        {"upstream": "ht" + "tps://leaked.example/path"}
    )
    leaky_obs = make_migration_observation(evidence=leaky_evidence)
    result = run_stage25_measurement(
        migration_observations=(leaky_obs,),
        price_observations=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage25ManifestError):
        _write_result(result, tmp_path)
    assert list(tmp_path.iterdir()) == []
