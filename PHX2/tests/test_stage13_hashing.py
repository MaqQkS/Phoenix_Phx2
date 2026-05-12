"""Stage 13 hashing helper unit tests.

Verifies that ``sha256_file`` is deterministic on identical contents,
differs when contents differ, and matches an in-memory SHA-256 digest
for byte-equal payloads.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from PHX2.stage13.hashing import sha256_bytes, sha256_file


def _write_bytes(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_sha256_file_deterministic_on_identical_input(tmp_path: Path) -> None:
    a = _write_bytes(tmp_path / "a.bin", b"hello world\n")
    b = _write_bytes(tmp_path / "b.bin", b"hello world\n")
    assert sha256_file(a) == sha256_file(b)


def test_sha256_file_differs_for_modified_input(tmp_path: Path) -> None:
    a = _write_bytes(tmp_path / "a.bin", b"hello world\n")
    b = _write_bytes(tmp_path / "b.bin", b"hello world!\n")
    assert sha256_file(a) != sha256_file(b)


def test_sha256_file_matches_stdlib_digest_format(tmp_path: Path) -> None:
    payload = b"some bytes here\nwith a newline"
    path = _write_bytes(tmp_path / "f.bin", payload)
    expected = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert sha256_file(path) == expected


def test_sha256_bytes_matches_stdlib() -> None:
    payload = b"x" * 1024
    expected = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert sha256_bytes(payload) == expected


def test_sha256_file_handles_empty_file(tmp_path: Path) -> None:
    path = _write_bytes(tmp_path / "empty.bin", b"")
    expected = f"sha256:{hashlib.sha256(b'').hexdigest()}"
    assert sha256_file(path) == expected


def test_sha256_file_raises_for_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "does_not_exist.bin")


def test_sha256_file_handles_large_chunked_read(tmp_path: Path) -> None:
    # Force multi-chunk read path: 200 KiB > 64 KiB chunk size.
    payload = b"a" * (200 * 1024)
    path = _write_bytes(tmp_path / "big.bin", payload)
    assert sha256_file(path) == sha256_bytes(payload)
