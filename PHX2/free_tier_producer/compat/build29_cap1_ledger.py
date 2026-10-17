"""Build #29 cap-1 — durable ledger baseline helpers (read-only digest + delta).

OUT-OF-REPO operator glue. Computes the operator's durable ping-ledger ``BaselineTriple``
(sha256 / size_bytes / line_count) WITHOUT mutating it, verifies it against an operator-asserted
``--require-baseline``, and computes the post-run line-count delta. The committed
``JsonlPingDedupeLedger`` is the only thing that ever WRITES to the ledger (one line per
reservation); this module only READS the file for the digest. The digest/counts are NOT secrets
(they are exactly what the committed launcher's ``BaselineTriple`` tracks).

Discipline: stdlib only (hashlib / os / pathlib / dataclasses). No env read, no network, no
ledger mutation, never prints a secret value.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class BaselineTriple:
    sha256: str
    size_bytes: int
    line_count: int

    def as_token(self) -> str:
        return f"{self.sha256}:{self.size_bytes}:{self.line_count}"


def compute_baseline(path: object) -> Optional[BaselineTriple]:
    """Return the durable ledger's current ``BaselineTriple``, or ``None`` if the file does
    not exist yet (a fresh ledger). READ-ONLY: never writes/creates the file."""
    p = Path(path)
    if not p.exists():
        return None
    if not p.is_file():
        return None
    data = p.read_bytes()
    return BaselineTriple(
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        line_count=data.count(b"\n"),
    )


def parse_require_baseline(value: object) -> Optional[BaselineTriple]:
    """Parse an operator-asserted ``<sha256>:<size_bytes>:<line_count>`` token, or ``None``."""
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    sha, size_s, lines_s = parts
    if not sha or any(c not in "0123456789abcdefABCDEF" for c in sha):
        return None
    try:
        size_bytes = int(size_s)
        line_count = int(lines_s)
    except ValueError:
        return None
    if size_bytes < 0 or line_count < 0:
        return None
    return BaselineTriple(sha256=sha, size_bytes=size_bytes, line_count=line_count)


def baseline_matches(actual: Optional[BaselineTriple], required: Optional[BaselineTriple]) -> bool:
    """``True`` iff a present actual baseline equals the operator-asserted required one
    (case-insensitive sha compare; exact size + line_count)."""
    if actual is None or required is None:
        return False
    return (
        actual.sha256.lower() == required.sha256.lower()
        and actual.size_bytes == required.size_bytes
        and actual.line_count == required.line_count
    )


def line_count_delta(
    before: Optional[BaselineTriple], after: Optional[BaselineTriple]
) -> Optional[int]:
    """``after.line_count - before.line_count`` (treating a missing file as 0 lines), or
    ``None`` if both are missing."""
    b = 0 if before is None else before.line_count
    a = 0 if after is None else after.line_count
    if before is None and after is None:
        return None
    return a - b


__all__ = (
    "BaselineTriple",
    "compute_baseline",
    "parse_require_baseline",
    "baseline_matches",
    "line_count_delta",
)
