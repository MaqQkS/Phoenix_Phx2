"""Stage 18 closed-set error codes (B01..B10) and exception type.

Mirrors Stage 17's error pattern: a flat closed set of B-codes,
each with a fixed message template, surfaced as a single
``Stage18Error`` exception. Callers (CLI exit-code dispatch,
tests) match on ``.code`` rather than parsing the formatted
message string.

Code table (locked):

  B01 -- input contract violation (missing file, bad header, bad
         column order, empty required file).
  B02 -- input manifest schema_version mismatch.
  B03 -- unknown Stage 17 ``descriptive_label`` (label not in the
         five-value accepted set).
  B04 -- output_dir already exists.
  B05 -- output_dir cannot be created or written to.
  B06 -- atomic-write failure for an output artifact.
  B07 -- input CSV row parse error (column-count mismatch).
  B08 -- input JSON parse error (malformed manifest).
  B09 -- ``git rev-parse`` failure. Non-fatal at the call site:
         the CLI downgrades to ``git_commit = "unknown"``.
  B10 -- internal invariant violation (Stage 18 bug).

Phase 18.1 exercises B01, B02, B07, B08; the rest are reserved for
later phases but are defined now so the closed set is fixed up
front.
"""

from __future__ import annotations

from typing import Mapping


B_CODES: tuple[str, ...] = (
    "B01",
    "B02",
    "B03",
    "B04",
    "B05",
    "B06",
    "B07",
    "B08",
    "B09",
    "B10",
)


ALL_CODES: frozenset[str] = frozenset(B_CODES)


MESSAGE_TEMPLATES: Mapping[str, str] = {
    "B01": "Stage 18 input contract violation",
    "B02": (
        "Stage 18 saw a Stage 17 manifest schema_version it does not accept"
    ),
    "B03": "Stage 18 saw an unknown Stage 17 descriptive_label",
    "B04": "Stage 18 output directory already exists",
    "B05": "Stage 18 could not provision the output directory",
    "B06": "Stage 18 could not write an output artifact atomically",
    "B07": "Stage 18 input CSV row failed to parse",
    "B08": "Stage 18 input JSON failed to parse",
    "B09": "Stage 18 could not capture git commit via git rev-parse",
    "B10": "Stage 18 internal invariant violated",
}


class Stage18Error(Exception):
    """Raised on any Stage 18 closed-set error condition.

    Carries a B01..B10 code; callers (CLI exit-code dispatcher,
    tests) match on ``.code`` rather than inspecting the formatted
    message string.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ALL_CODES:
            raise ValueError(
                f"Stage18Error code {code!r} is not in the closed set"
            )
        self.code = code
        self.detail = detail
        template = MESSAGE_TEMPLATES[code]
        if detail:
            message = f"[{code}] {template}: {detail}"
        else:
            message = f"[{code}] {template}"
        super().__init__(message)


__all__ = [
    "ALL_CODES",
    "B_CODES",
    "MESSAGE_TEMPLATES",
    "Stage18Error",
]
