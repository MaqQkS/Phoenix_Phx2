"""Stage 13 hashing helpers.

Pure stdlib SHA-256 of file contents. Stage 13 hashes every consumed
Stage 12 artifact and records the digest in its manifest under
``stage12_input_hashes`` (per spec L11) so a downstream reviewer can
audit which Stage 12 outputs the recommendation set was derived from.

Hashing is the only filesystem read this module performs. The file is
read in fixed-size chunks so large CSVs do not balloon memory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


_HASH_CHUNK_BYTES = 64 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of ``path`` as ``"sha256:<hex>"``.

    Reads the file in 64 KiB chunks. The output format matches the
    manifest convention used in Stage 13's ``stage12_input_hashes`` and
    ``stage12_manifest_hash`` fields.

    Raises ``FileNotFoundError`` if the path does not exist.
    """

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of a byte string, returned in the same ``"sha256:<hex>"``
    format used by ``sha256_file``.

    Used by ``compute_recommendation_set_version`` (spec §FILE LIST) and
    by tests that prefer in-memory digests over filesystem round-trips.
    """

    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"
