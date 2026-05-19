"""Stage 23.1 manifest scaffolding tests.

Pins:

  * File SHA-256 hashing is stable.
  * Manifest serialization is deterministic (canonical JSON,
    sorted keys).
  * Row counts are preserved verbatim.
  * ``created_at_utc`` is caller-injected and stable in tests.
  * No secret-bearing or URL-shape substring may appear in
    manifest text.
  * Files in the manifest are sorted by basename for stable
    serialization regardless of caller-supplied order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage23.errors import Stage23ManifestError
from PHX2.stage23.stage23_manifest import (
    REDACTION_CONFIRMED_TOKEN,
    Stage23ArtifactManifest,
    Stage23InputManifest,
    Stage23ManifestFileEntry,
    build_artifact_manifest,
    build_input_manifest,
    build_manifest_file_entry,
    hash_file_sha256,
    serialize_artifact_manifest,
    serialize_input_manifest,
)


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
    with pytest.raises(Stage23ManifestError):
        hash_file_sha256(path=tmp_path / "nope.jsonl")


def test_hash_file_sha256_rejects_directory(tmp_path: Path):
    directory = tmp_path / "subdir"
    directory.mkdir()
    with pytest.raises(Stage23ManifestError):
        hash_file_sha256(path=directory)


# ---------------------------------------------------------------------------
# Manifest file entry builder
# ---------------------------------------------------------------------------


def test_build_manifest_file_entry_round_trips_safe_basename():
    entry = build_manifest_file_entry(
        file_basename="raw_capture.jsonl",
        sha256="a" * 64,
        row_count=3,
    )
    assert entry.file_basename == "raw_capture.jsonl"
    assert entry.sha256 == "a" * 64
    assert entry.row_count == 3


def test_build_manifest_file_entry_rejects_path_separator():
    with pytest.raises(Stage23ManifestError):
        build_manifest_file_entry(
            file_basename="folder/raw_capture.jsonl",
            sha256="a" * 64,
            row_count=0,
        )


def test_build_manifest_file_entry_rejects_secret_substring_in_basename():
    with pytest.raises(Stage23ManifestError):
        build_manifest_file_entry(
            file_basename="api_key_dump.jsonl",
            sha256="a" * 64,
            row_count=0,
        )


def test_build_manifest_file_entry_rejects_empty_sha256():
    with pytest.raises(Stage23ManifestError):
        build_manifest_file_entry(
            file_basename="raw.jsonl",
            sha256="",
            row_count=0,
        )


def test_build_manifest_file_entry_rejects_invalid_row_count():
    with pytest.raises(Stage23ManifestError):
        build_manifest_file_entry(
            file_basename="raw.jsonl",
            sha256="a" * 64,
            row_count=-2,
        )


# ---------------------------------------------------------------------------
# Manifest builders
# ---------------------------------------------------------------------------


def _entry(name: str, *, row_count: int = 0) -> Stage23ManifestFileEntry:
    return Stage23ManifestFileEntry(
        file_basename=name,
        sha256="a" * 64,
        row_count=row_count,
    )


def test_build_input_manifest_sorts_files_by_basename():
    manifest = build_input_manifest(
        files=(_entry("zeta.jsonl"), _entry("alpha.jsonl"), _entry("middle.jsonl")),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    names = [entry.file_basename for entry in manifest.files]
    assert names == ["alpha.jsonl", "middle.jsonl", "zeta.jsonl"]


def test_build_input_manifest_sets_locked_metadata():
    manifest = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert manifest.stage_name == "stage23"
    assert manifest.stage_version == "23.6"
    assert manifest.schema_version == "stage23_v0_manifest"
    assert manifest.observe_only_mode == "observe_only"


def test_build_input_manifest_accepts_redaction_confirmation_token():
    manifest = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2026-01-01T00:00:00Z",
        redaction_confirmed=REDACTION_CONFIRMED_TOKEN,
    )
    assert manifest.redaction_confirmed == REDACTION_CONFIRMED_TOKEN


def test_build_input_manifest_rejects_unknown_redaction_token():
    with pytest.raises(Stage23ManifestError):
        build_input_manifest(
            files=(_entry("a.jsonl"),),
            created_at_utc="2026-01-01T00:00:00Z",
            redaction_confirmed="something_else",
        )


def test_build_input_manifest_rejects_empty_created_at_utc():
    with pytest.raises(Stage23ManifestError):
        build_input_manifest(
            files=(_entry("a.jsonl"),),
            created_at_utc="",
        )


def test_build_input_manifest_rejects_non_tuple_files():
    with pytest.raises(Stage23ManifestError):
        build_input_manifest(
            files=[_entry("a.jsonl")],  # type: ignore[arg-type]
            created_at_utc="2026-01-01T00:00:00Z",
        )


def test_build_artifact_manifest_is_distinct_record_type():
    artifact = build_artifact_manifest(
        files=(_entry("art.jsonl"),),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert isinstance(artifact, Stage23ArtifactManifest)
    assert not isinstance(artifact, Stage23InputManifest)


# ---------------------------------------------------------------------------
# Row count preservation
# ---------------------------------------------------------------------------


def test_manifest_preserves_row_counts():
    manifest = build_input_manifest(
        files=(
            _entry("alpha.jsonl", row_count=7),
            _entry("beta.jsonl", row_count=42),
        ),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    by_name = {entry.file_basename: entry.row_count for entry in manifest.files}
    assert by_name == {"alpha.jsonl": 7, "beta.jsonl": 42}


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------


def test_serialize_input_manifest_is_byte_identical_across_calls():
    manifest = build_input_manifest(
        files=(_entry("alpha.jsonl"), _entry("beta.jsonl")),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    a = serialize_input_manifest(manifest)
    b = serialize_input_manifest(manifest)
    assert a == b


def test_serialize_input_manifest_is_byte_identical_regardless_of_input_order():
    a = build_input_manifest(
        files=(_entry("alpha.jsonl"), _entry("beta.jsonl")),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    b = build_input_manifest(
        files=(_entry("beta.jsonl"), _entry("alpha.jsonl")),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert serialize_input_manifest(a) == serialize_input_manifest(b)


def test_serialize_artifact_manifest_distinct_from_input_manifest_text():
    files = (_entry("x.jsonl"),)
    input_manifest = build_input_manifest(
        files=files,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    artifact_manifest = build_artifact_manifest(
        files=files,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert (
        serialize_input_manifest(input_manifest)
        != serialize_artifact_manifest(artifact_manifest)
    )


def test_serialized_manifest_carries_no_secret_substring():
    manifest = build_input_manifest(
        files=(_entry("alpha.jsonl"),),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    encoded = serialize_input_manifest(manifest)
    lower = encoded.lower()
    forbidden = [
        "api_key",
        "webhook_url",
        "rpc_url",
        "authorization",
        "password",
        "secret",
        "private_key",
    ]
    for needle in forbidden:
        assert needle not in lower


def test_serialized_manifest_carries_no_url_substring():
    manifest = build_input_manifest(
        files=(_entry("alpha.jsonl"),),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    encoded = serialize_input_manifest(manifest)
    lower = encoded.lower()
    colon_slash_slash = ":" + "//"
    forbidden = [
        "https" + colon_slash_slash,
        "http" + colon_slash_slash,
        "wss" + colon_slash_slash,
        "ws" + colon_slash_slash,
        "discord" + "." + "com",
    ]
    for needle in forbidden:
        assert needle not in lower


# ---------------------------------------------------------------------------
# created_at_utc injection / stability
# ---------------------------------------------------------------------------


def test_created_at_utc_is_carried_verbatim_in_manifest():
    manifest = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2026-02-15T12:34:56Z",
    )
    assert manifest.created_at_utc == "2026-02-15T12:34:56Z"


def test_created_at_utc_appears_in_serialized_output():
    manifest = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2026-02-15T12:34:56Z",
    )
    encoded = serialize_input_manifest(manifest)
    assert "2026-02-15T12:34:56Z" in encoded


def test_different_created_at_utc_changes_serialization():
    a = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2026-02-15T12:34:56Z",
    )
    b = build_input_manifest(
        files=(_entry("a.jsonl"),),
        created_at_utc="2027-09-09T00:00:00Z",
    )
    assert serialize_input_manifest(a) != serialize_input_manifest(b)
