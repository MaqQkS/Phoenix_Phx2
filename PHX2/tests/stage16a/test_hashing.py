"""Phase 2: deterministic Stage 16A hashing helpers plus Stage 15 byte parity.

Per Step 0 locked remediation #4, the "byte-identical canonical JSON with
Stage 15" claim is softened: Stage 15 hashes pretty-printed file bytes, not
canonical dicts, so the parity tests verify equality at the raw-bytes and
raw-file-bytes layer only. Stage 16A's compact canonical JSON is its own
surface, used solely for the runtime artifact's policy_hash; it is NOT
expected to match any Stage 15 hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from PHX2.stage15.hashing import sha256_bytes as stage15_sha256_bytes
from PHX2.stage15.hashing import sha256_file as stage15_sha256_file
from PHX2.stage16a.hashing import (
    canonical_json_dumps,
    sha256_bytes,
    sha256_canonical_dict,
    sha256_canonical_file,
    sha256_file,
)


# ---------------------------------------------------------------------------
# canonical_json_dumps
# ---------------------------------------------------------------------------


def test_canonical_json_dumps_is_compact_and_sorted() -> None:
    d = {"b": 1, "a": [3, 2]}
    out = canonical_json_dumps(d)
    assert out == '{"a":[3,2],"b":1}'
    assert "\n" not in out


def test_canonical_json_dumps_ensure_ascii_false() -> None:
    d = {"x": "café"}
    out = canonical_json_dumps(d)
    assert "café" in out  # raw, not \u-escaped


def test_canonical_json_dumps_order_independent() -> None:
    assert canonical_json_dumps({"a": 1, "b": 2}) == canonical_json_dumps({"b": 2, "a": 1})


# ---------------------------------------------------------------------------
# sha256_canonical_dict / sha256_canonical_file
# ---------------------------------------------------------------------------


def test_sha256_canonical_dict_deterministic() -> None:
    d = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
    h1 = sha256_canonical_dict(d)
    h2 = sha256_canonical_dict(d)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_sha256_canonical_dict_order_independent() -> None:
    h1 = sha256_canonical_dict({"a": 1, "b": 2})
    h2 = sha256_canonical_dict({"b": 2, "a": 1})
    assert h1 == h2


def test_sha256_canonical_dict_value_sensitive() -> None:
    h1 = sha256_canonical_dict({"a": 1})
    h2 = sha256_canonical_dict({"a": 2})
    assert h1 != h2


def test_sha256_canonical_file_matches_dict_for_pretty_printed_source(
    tmp_path: Path,
) -> None:
    """A pretty-printed file and its parsed dict hash to the same canonical
    value -- this is the whole point of sha256_canonical_file."""

    d = {"a": 1, "b": [2, 3], "c": {"deep": True}}
    path = tmp_path / "x.json"
    path.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    assert sha256_canonical_file(path) == sha256_canonical_dict(d)


def test_sha256_canonical_file_matches_dict_for_compact_source(
    tmp_path: Path,
) -> None:
    d = {"a": 1, "b": 2}
    path = tmp_path / "x.json"
    path.write_text(canonical_json_dumps(d), encoding="utf-8")
    assert sha256_canonical_file(path) == sha256_canonical_dict(d)


# ---------------------------------------------------------------------------
# sha256_bytes / sha256_file value correctness
# ---------------------------------------------------------------------------


def test_sha256_bytes_prefix_and_value() -> None:
    h = sha256_bytes(b"hello")
    assert h == f"sha256:{hashlib.sha256(b'hello').hexdigest()}"


def test_sha256_file_prefix_and_value(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    payload = b"some file contents\n"
    path.write_bytes(payload)
    assert sha256_file(path) == f"sha256:{hashlib.sha256(payload).hexdigest()}"


def test_sha256_file_chunked_read_for_large_input(tmp_path: Path) -> None:
    """Stage 15-style chunked file reader must handle inputs larger than
    one chunk (64 KiB) without dropping bytes."""

    path = tmp_path / "big.bin"
    payload = b"X" * (128 * 1024 + 7)
    path.write_bytes(payload)
    assert sha256_file(path) == f"sha256:{hashlib.sha256(payload).hexdigest()}"


# ---------------------------------------------------------------------------
# Stage 15 byte/file parity (the only Stage 15 hashing comparison)
# ---------------------------------------------------------------------------


def test_sha256_bytes_byte_parity_with_stage15() -> None:
    data = b"the quick brown fox jumps over the lazy dog"
    assert sha256_bytes(data) == stage15_sha256_bytes(data)


def test_sha256_file_byte_parity_with_stage15(tmp_path: Path) -> None:
    path = tmp_path / "parity.bin"
    path.write_bytes(b"parity test payload\n")
    assert sha256_file(path) == stage15_sha256_file(path)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00",
        b"\xff" * 1024,
        "café".encode("utf-8"),
    ],
)
def test_sha256_bytes_parity_with_stage15_for_edge_payloads(data: bytes) -> None:
    assert sha256_bytes(data) == stage15_sha256_bytes(data)
