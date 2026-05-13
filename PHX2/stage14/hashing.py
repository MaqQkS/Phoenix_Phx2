"""Stage 14 hashing helpers.

Pure stdlib SHA-256 of file contents. Stage 14 hashes every consumed
Stage 13 and Stage 12 artifact and records the digest in its manifest
so a downstream reviewer (Stage 15) can audit exactly which input
bytes the shadow-policy replay was derived from.

Mirrors ``PHX2.stage13.hashing`` deliberately: Stage 14 keeps its own
copy so the module's import surface stays free of cross-stage runtime
dependencies (substrate-lock parity with how Stage 13 does not import
``PHX2.analysis`` runtime modules).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


_HASH_CHUNK_BYTES = 64 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of ``path`` as ``"sha256:<hex>"``.

    Reads the file in 64 KiB chunks so large CSVs do not balloon
    memory. Format matches Stage 13's ``"sha256:<hex>"`` convention so
    Stage 14's manifest hashes line up directly with the values Stage
    13 already records in its own manifest.

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

    Used by determinism tests that prefer in-memory digests over
    filesystem round-trips.
    """

    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"


def short_content_hash(canonical: str, *, length: int = 12) -> str:
    """Return the first ``length`` hex chars of SHA-256 of ``canonical``.

    Used by Stage 14 to mint content-stable rule IDs: the canonical
    input string is the pipe-joined identity tuple of a shadow rule, so
    two reruns over the same eligible Stage 13 row produce the same
    rule ID, while reordering rows or inserting new candidates does not
    shift the IDs of unchanged rules.
    """

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:length]
