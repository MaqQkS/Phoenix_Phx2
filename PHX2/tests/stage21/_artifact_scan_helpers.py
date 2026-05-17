"""Stage 21.2 remediation R5: JSON-aware artifact-scan whitelist.

Stage 21.2's pre-R5 artifact scans used a global ``.replace(...)``
substring strip to remove the literal text
``safe_for_public_dispatch`` from each artifact before scanning
for forbidden substrings (otherwise the bare ``public_dispatch``
forbidden token would trip on the locked Stage 21 dispatch-
safety invariant key name). That substring strip was overly
broad: it removed the literal text everywhere it appeared, not
just at the exact JSON keypath where the locked invariant is
emitted.

R5 replaces the substring strip with a JSON/JSONL-aware
whitelist:

  * ``KNOWN_SAFE_KEYPATHS`` is an exact tuple of keypath tuples
    that the whitelist removes. Per the Stage 21.2 STEP 0
    inventory, only one keypath qualifies:
    ``("run_metadata", "safe_for_public_dispatch")``.
  * ``strip_known_safe_keys`` walks a parsed JSON object, removes
    only the locked keypaths, and only when the value is the
    exact Python boolean ``False`` (identity check ``is False``).
    The function deep-copies the input; the caller's parsed
    object is never mutated.
  * ``cleaned_artifact_text`` / ``cleaned_artifact_text_from_path``
    return a re-serialized form of a JSON or JSONL artifact
    suitable for the existing forbidden-substring scans.

This module is test-only. It does not import any production
Stage 21 module; it has no side effects at import time; it does
no network / disk / DB access.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Locked safe-keypaths
# ---------------------------------------------------------------------------
#
# Each keypath is a tuple of string keys traversed from the
# JSON root. The set is intentionally narrow -- STEP 0 of the
# Stage 21.2 remediation confirmed only one Stage 21 invariant
# keypath exists across all Stage 21.2 artifacts.
#
# Adding to this tuple is a test-only change that broadens the
# whitelist; it should require an explicit audit acknowledgement.
# The ``test_known_safe_keypaths_is_exactly_locked`` test pins
# the set so any addition surfaces in review.


KNOWN_SAFE_KEYPATHS: tuple[tuple[str, ...], ...] = (
    ("run_metadata", "safe_for_public_dispatch"),
)


# ---------------------------------------------------------------------------
# Whitelist primitive
# ---------------------------------------------------------------------------


def _strip_one_keypath(node: Any, keypath: tuple[str, ...]) -> None:
    """In-place strip of ``keypath`` from ``node`` if the leaf value is False.

    Used INTERNALLY by ``strip_known_safe_keys`` on the deep-
    copied node so the caller's object is never mutated.

    The leaf removal is conditional on an identity check
    ``val is False``. This rejects:
      * ``True``                  (boolean True)
      * the integer ``0``         (CPython interning means
                                   ``0 is False`` evaluates
                                   ``False``)
      * the string ``"false"``    (clearly not the locked
                                   boolean value)
      * ``None``                  (different type)
      * any other shape
    """
    if not isinstance(node, dict):
        return
    if not keypath:
        return
    if len(keypath) == 1:
        leaf = keypath[0]
        if leaf in node and node[leaf] is False:
            del node[leaf]
        return
    head = keypath[0]
    rest = keypath[1:]
    child = node.get(head)
    if isinstance(child, dict):
        _strip_one_keypath(child, rest)


def strip_known_safe_keys(parsed: Any) -> Any:
    """Return a deep copy of ``parsed`` with the locked safe-keypaths removed.

    Locked behavior:
      * The caller's ``parsed`` object is NEVER mutated; the
        function returns a deep copy.
      * Only the exact keypaths in ``KNOWN_SAFE_KEYPATHS`` are
        considered.
      * A keypath is removed only when its leaf value is
        ``True is False``-style identity-equal to the Python
        ``False`` literal.
      * If the keypath does not exist in the input, the
        function does nothing for that keypath.
      * If the leaf value is anything other than literal
        ``False`` (e.g. ``True``, ``"false"``, ``0``,
        ``None``, a dict, a list), the function does NOT
        remove the keypath.
      * No substring matching anywhere. Keys at the wrong
        keypath (e.g. top-level ``safe_for_public_dispatch``,
        not under ``run_metadata``) are NOT stripped.
      * A different key that contains the locked key as a
        substring (e.g. ``unsafe_for_public_dispatch``) is NOT
        stripped.
    """
    cleaned = copy.deepcopy(parsed)
    for keypath in KNOWN_SAFE_KEYPATHS:
        _strip_one_keypath(cleaned, keypath)
    return cleaned


# ---------------------------------------------------------------------------
# Artifact-scan convenience helpers
# ---------------------------------------------------------------------------


def cleaned_artifact_text(raw: str, *, is_jsonl: bool) -> str:
    """Return a re-serialized cleaned form of an artifact's raw text.

    For ``is_jsonl=False`` (``.json`` artifacts):
      * Parse the whole text as JSON.
      * Apply ``strip_known_safe_keys``.
      * Re-serialize via ``json.dumps(..., sort_keys=True)``.

    For ``is_jsonl=True`` (``.jsonl`` artifacts):
      * Split on ``\\n``.
      * For each non-empty line, parse as JSON, strip known-safe
        keys, re-serialize via ``json.dumps(..., sort_keys=True)``.
      * Re-join with ``\\n`` preserving the original line count
        (so trailing empty lines survive).

    The returned text is intended for substring scanning. It is
    NOT byte-equivalent to the original artifact (because the
    serializer re-orders keys and uses no whitespace), but it
    preserves all artifact content other than the
    locked-keypath strips.

    Empty / whitespace-only input is returned unchanged.
    """
    if not raw or not raw.strip():
        return raw
    if not is_jsonl:
        parsed = json.loads(raw)
        cleaned = strip_known_safe_keys(parsed)
        return json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    # JSONL: parse line-by-line.
    lines = raw.split("\n")
    out_lines: list[str] = []
    for line in lines:
        if line == "":
            out_lines.append("")
            continue
        parsed = json.loads(line)
        cleaned = strip_known_safe_keys(parsed)
        out_lines.append(
            json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
        )
    return "\n".join(out_lines)


def cleaned_artifact_text_from_path(path: Path) -> str:
    """Read ``path`` and return its cleaned text via ``cleaned_artifact_text``.

    Convenience for the existing artifact-scan tests. Infers
    JSON vs JSONL from the file suffix: ``.jsonl`` -> line-by-line,
    anything else -> whole-file JSON parse.
    """
    raw = path.read_text(encoding="utf-8")
    is_jsonl = path.suffix == ".jsonl"
    return cleaned_artifact_text(raw, is_jsonl=is_jsonl)


__all__ = [
    "KNOWN_SAFE_KEYPATHS",
    "cleaned_artifact_text",
    "cleaned_artifact_text_from_path",
    "strip_known_safe_keys",
]
