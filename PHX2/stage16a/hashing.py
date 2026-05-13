"""Stage 16A hashing helpers.

Two surfaces:

* Stage 15-style file-bytes / raw-bytes SHA-256, returning the
  ``"sha256:<hex>"`` prefixed string used throughout PHX2 lineage manifests.
  These functions are byte-identical to ``PHX2.stage15.hashing`` for the
  same input (verified by the Phase 2 parity test) — they are COPIED, not
  imported, so Stage 16A keeps a clean import surface (no Stage 15 runtime
  dependency).

* Compact canonical-JSON helpers (``canonical_json_dumps``,
  ``sha256_canonical_dict``, ``sha256_canonical_file``) used to compute
  the Stage 16A runtime artifact's ``policy_hash`` field over the body
  sans ``policy_hash`` itself. Stage 15 has no equivalent canonical
  helper (it always hashes pretty-printed file bytes), so this surface is
  a Stage 16A original — see Step 0 locked remediation #4.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_HASH_CHUNK_BYTES = 64 * 1024


# ---------------------------------------------------------------------------
# Compact canonical JSON
# ---------------------------------------------------------------------------


def canonical_json_dumps(value: Any) -> str:
    """Compact canonical JSON encoding for Stage 16A hashing.

    Rules:
      * ``sort_keys=True``
      * ``separators=(',', ':')`` (compact, no whitespace)
      * ``ensure_ascii=False``
      * no trailing newline

    These rules are NOT the rules Stage 15's writer uses (Stage 15
    pretty-prints with indent=2 and a trailing newline). Stage 16A's
    canonical form is its own — used only to derive
    ``policy_hash`` on the runtime body, never to serialize on-disk
    artifacts (the manifest and runtime policy file are pretty-printed
    just like Stage 15, for human readability).
    """

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Stage 15-style byte/file SHA-256 ("sha256:<hex>")
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """Return ``"sha256:<hex>"`` of ``data``.

    Byte-identical to ``PHX2.stage15.hashing.sha256_bytes`` (copied per
    Step 0 locked remediation #4; verified by Phase 2 parity test).
    """

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    """Return ``"sha256:<hex>"`` of the file at ``path`` (chunked read).

    Byte-identical to ``PHX2.stage15.hashing.sha256_file`` for the same
    file contents (verified by Phase 2 parity test).
    """

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


# ---------------------------------------------------------------------------
# Canonical-JSON SHA-256 ("sha256:<hex>") -- Stage 16A original surface
# ---------------------------------------------------------------------------


def sha256_canonical_dict(value: Any) -> str:
    """Return ``"sha256:<hex>"`` over ``canonical_json_dumps(value)``.

    Used to compute the Stage 16A runtime artifact's ``policy_hash`` over
    the body dict sans the ``policy_hash`` field itself.
    """

    encoded = canonical_json_dumps(value).encode("utf-8")
    return sha256_bytes(encoded)


def sha256_canonical_file(path: Path) -> str:
    """Re-parse the JSON file at ``path``, re-encode in canonical form,
    and return ``"sha256:<hex>"`` of the canonical bytes.

    Differs from ``sha256_file``: that hashes the on-disk bytes verbatim,
    while this re-canonicalizes so pretty-printed and compact encodings
    of the same body produce the same hash. Useful when verifying the
    runtime artifact's body hash independent of its on-disk formatting.
    """

    body = json.loads(Path(path).read_text(encoding="utf-8"))
    return sha256_canonical_dict(body)
