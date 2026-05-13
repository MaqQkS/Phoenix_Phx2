"""Stage 15 hashing helpers.

Pure stdlib SHA-256 of file contents. Returns ``"sha256:<hex>"`` to
match Stage 14's hash format so source-hash lineage lines up byte-for-
byte with Stage 14's manifest values.

Stage 15 keeps its own copy of this helper rather than importing
Stage 14's module so the Stage 15 import surface stays clean of any
prior-stage runtime dependency.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


_HASH_CHUNK_BYTES = 64 * 1024


def sha256_file(path: Path) -> str:
    """Return SHA-256 of the file at ``path`` as ``"sha256:<hex>"``."""

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 of ``data`` as ``"sha256:<hex>"``."""

    return f"sha256:{hashlib.sha256(data).hexdigest()}"
