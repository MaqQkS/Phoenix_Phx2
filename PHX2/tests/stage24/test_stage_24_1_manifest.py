"""Stage 24.1 manifest scaffolding tests.

Pins:

  * File SHA-256 hashing is stable.
  * Manifest serialization is deterministic (canonical JSON,
    sorted keys, byte-stable).
  * Row counts are preserved verbatim.
  * ``created_at_utc`` is caller-injected and stable in tests.
  * Files in the manifest are sorted by basename for stable
    serialization regardless of caller-supplied order.
  * Basename safety: secret-bearing / URL-shape substrings
    raise; path separators raise.
  * Redaction-confirmation token vocabulary: only the locked
    token or the empty string is accepted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage24.errors import Stage24ManifestError
from PHX2.stage24.stage24_manifest import (
    REDACTION_CONFIRMED_TOKEN,
    Stage24ArtifactManifest,
    Stage24InputManifest,
    Stage24ManifestFileEntry,
    build_artifact_manifest,
    build_input_manifest,
    build_manifest_file_entry,
    hash_file_sha256,
    serialize_artifact_manifest,
    serialize_input_manifest,
)


FIXED_CLOCK_UTC: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# File hash stability
# ---------------------------------------------------------------------------


def test_hash_file_sha256_is_stable_across_calls(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text("hello\nworld\n", encoding="utf-8")
    a = hash_file_sha256(path=path)
    b = hash_file_sha256(path=path)
    assert a == b


def test_hash_file_sha256_differs_for_different_bytes(tmp_path: Path):
    a_path = tmp_path / "a.jsonl"
    b_path = tmp_path / "b.jsonl"
    a_path.write_text("aaa", encoding="utf-8")
    b_path.write_text("bbb", encoding="utf-8")
    assert hash_file_sha256(path=a_path) != hash_file_sha256(path=b_path)


def test_hash_file_sha256_rejects_missing_path(tmp_path: Path):
    with pytest.raises(Stage24ManifestError):
        hash_file_sha256(path=tmp_path / "nope.jsonl")


def test_hash_file_sha256_rejects_directory(tmp_path: Path):
    directory = tmp_path / "subdir"
    directory.mkdir()
    with pytest.raises(Stage24ManifestError):
        hash_file_sha256(path=directory)


def test_hash_file_sha256_length_is_64_hex_chars(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text("data", encoding="utf-8")
    digest = hash_file_sha256(path=path)
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


# ---------------------------------------------------------------------------
# Manifest file entry builder
# ---------------------------------------------------------------------------


def test_build_manifest_file_entry_round_trips_safe_basename():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=3,
    )
    assert isinstance(entry, Stage24ManifestFileEntry)
    assert entry.file_basename == "decoded_tx.jsonl"
    assert entry.sha256 == "a" * 64
    assert entry.row_count == 3


def test_build_manifest_file_entry_rejects_empty_basename():
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename="", sha256="a" * 64, row_count=0
        )


def test_build_manifest_file_entry_rejects_path_separator():
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename="dir/decoded_tx.jsonl",
            sha256="a" * 64,
            row_count=0,
        )
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename="dir\\decoded_tx.jsonl",
            sha256="a" * 64,
            row_count=0,
        )


def test_build_manifest_file_entry_rejects_secret_basename():
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename="api_key_leak.jsonl",
            sha256="a" * 64,
            row_count=0,
        )


def test_build_manifest_file_entry_rejects_url_shape_basename():
    bad = "h" + "ttps://evil.example/leak.jsonl"
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename=bad, sha256="a" * 64, row_count=0
        )


def test_build_manifest_file_entry_rejects_invalid_row_count():
    with pytest.raises(Stage24ManifestError):
        build_manifest_file_entry(
            file_basename="decoded_tx.jsonl",
            sha256="a" * 64,
            row_count=-2,
        )


def test_build_manifest_file_entry_accepts_minus_one_row_count():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=-1,
    )
    assert entry.row_count == -1


# ---------------------------------------------------------------------------
# Redaction confirmation token
# ---------------------------------------------------------------------------


def test_redaction_confirmed_token_is_locked():
    assert REDACTION_CONFIRMED_TOKEN == "stage24_redaction_confirmed"


def test_build_input_manifest_accepts_locked_redaction_token():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    manifest = build_input_manifest(
        files=(entry,),
        created_at_utc=FIXED_CLOCK_UTC,
        redaction_confirmed=REDACTION_CONFIRMED_TOKEN,
    )
    assert manifest.redaction_confirmed == REDACTION_CONFIRMED_TOKEN


def test_build_input_manifest_rejects_unknown_redaction_token():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    with pytest.raises(Stage24ManifestError):
        build_input_manifest(
            files=(entry,),
            created_at_utc=FIXED_CLOCK_UTC,
            redaction_confirmed="not_the_locked_token",
        )


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def test_build_input_manifest_sorts_files_by_basename():
    a = build_manifest_file_entry(
        file_basename="zzz.jsonl", sha256="a" * 64, row_count=2
    )
    b = build_manifest_file_entry(
        file_basename="aaa.jsonl", sha256="b" * 64, row_count=1
    )
    manifest = build_input_manifest(
        files=(a, b),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert isinstance(manifest, Stage24InputManifest)
    assert [f.file_basename for f in manifest.files] == [
        "aaa.jsonl",
        "zzz.jsonl",
    ]


def test_build_artifact_manifest_sorts_files_by_basename():
    a = build_manifest_file_entry(
        file_basename="zzz_artifact.jsonl",
        sha256="a" * 64,
        row_count=2,
    )
    b = build_manifest_file_entry(
        file_basename="aaa_artifact.jsonl",
        sha256="b" * 64,
        row_count=1,
    )
    manifest = build_artifact_manifest(
        files=(a, b),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert isinstance(manifest, Stage24ArtifactManifest)
    assert [f.file_basename for f in manifest.files] == [
        "aaa_artifact.jsonl",
        "zzz_artifact.jsonl",
    ]


def test_build_input_manifest_rejects_empty_created_at_utc():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    with pytest.raises(Stage24ManifestError):
        build_input_manifest(files=(entry,), created_at_utc="")


def test_build_input_manifest_rejects_non_tuple_files():
    with pytest.raises(Stage24ManifestError):
        build_input_manifest(
            files=[],  # type: ignore[arg-type]
            created_at_utc=FIXED_CLOCK_UTC,
        )


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------


def test_serialize_input_manifest_is_deterministic():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=2,
    )
    a_manifest = build_input_manifest(
        files=(entry,), created_at_utc=FIXED_CLOCK_UTC
    )
    b_manifest = build_input_manifest(
        files=(entry,), created_at_utc=FIXED_CLOCK_UTC
    )
    assert serialize_input_manifest(a_manifest) == serialize_input_manifest(
        b_manifest
    )


def test_serialize_input_manifest_is_byte_stable_under_file_reorder():
    a = build_manifest_file_entry(
        file_basename="aaa.jsonl", sha256="a" * 64, row_count=1
    )
    b = build_manifest_file_entry(
        file_basename="bbb.jsonl", sha256="b" * 64, row_count=2
    )
    forward = build_input_manifest(
        files=(a, b), created_at_utc=FIXED_CLOCK_UTC
    )
    reverse = build_input_manifest(
        files=(b, a), created_at_utc=FIXED_CLOCK_UTC
    )
    assert serialize_input_manifest(forward) == serialize_input_manifest(
        reverse
    )


def test_serialize_artifact_manifest_distinct_from_input_manifest():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    input_manifest = build_input_manifest(
        files=(entry,), created_at_utc=FIXED_CLOCK_UTC
    )
    artifact_manifest = build_artifact_manifest(
        files=(entry,), created_at_utc=FIXED_CLOCK_UTC
    )
    assert serialize_input_manifest(input_manifest) != serialize_artifact_manifest(
        artifact_manifest
    )


def test_serialize_input_manifest_carries_locked_stage_metadata():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    manifest = build_input_manifest(
        files=(entry,),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    serialized = serialize_input_manifest(manifest)
    assert '"stage_name":"stage24"' in serialized
    assert '"stage_version":"24.1"' in serialized
    assert '"observe_only_mode":"observe_only"' in serialized
    assert '"manifest_kind":"input"' in serialized


def test_serialize_artifact_manifest_carries_artifact_kind_marker():
    entry = build_manifest_file_entry(
        file_basename="decoded_tx.jsonl",
        sha256="a" * 64,
        row_count=1,
    )
    manifest = build_artifact_manifest(
        files=(entry,),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    serialized = serialize_artifact_manifest(manifest)
    assert '"manifest_kind":"artifact"' in serialized
