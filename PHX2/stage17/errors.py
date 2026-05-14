"""Stage 17 closed-set error codes (A01..A10) and exception type.

The A-codes form a closed set; the CLI maps them onto its locked
exit-code class (0/2/3/4/5). All Stage 17 surfaces (readers, writers,
manifest, log) raise ``Stage17Error(code, detail)`` rather than ad-hoc
exception types so the CLI dispatch table stays a flat mapping.
"""

from __future__ import annotations

from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 17 closed-set A codes
# ---------------------------------------------------------------------------
#
# Exit-code class mapping:
#
#   exit 3 (DB connectivity / required table missing / read failure):
#     A01 -- DB file is not readable
#     A02 -- a required source table is missing
#     A03 -- a SELECT query failed
#
#   exit 4 (runtime error during analysis OR output-dir collision):
#     A04 -- output directory could not be provisioned (existed,
#            mkdir failed, or unwritable)
#     A05 -- manifest write failed
#     A06 -- one of the CSV writes failed
#     A07 -- README write failed
#     A08 -- run-log write failed
#
#   non-fatal at the call site (CLI records "unknown" and continues):
#     A09 -- ``git rev-parse HEAD`` failed
#
#   exit 5 (unexpected programmer error not classified above):
#     A10 -- unexpected runtime error

A_CODES: tuple[str, ...] = (
    "A01",
    "A02",
    "A03",
    "A04",
    "A05",
    "A06",
    "A07",
    "A08",
    "A09",
    "A10",
)


ALL_CODES: frozenset[str] = frozenset(A_CODES)


MESSAGE_TEMPLATES: Mapping[str, str] = {
    "A01": "Stage 17 could not open the PHX2 SQLite database in read-only mode",
    "A02": "Stage 17 requires a source table that is not present in the database",
    "A03": "Stage 17 SELECT query failed against the PHX2 database",
    "A04": "Stage 17 could not provision the output directory",
    "A05": "Stage 17 could not write the run manifest",
    "A06": "Stage 17 could not write a CSV report file",
    "A07": "Stage 17 could not write the README report",
    "A08": "Stage 17 could not write the run log",
    "A09": "Stage 17 could not capture git commit via git rev-parse",
    "A10": "Stage 17 hit an unexpected runtime error",
}


class Stage17Error(Exception):
    """Raised on any Stage 17 closed-set error condition.

    Carries an A01..A10 code; callers (CLI exit-code dispatcher, tests)
    match on ``.code`` rather than inspecting the formatted message.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ALL_CODES:
            raise ValueError(
                f"Stage17Error code {code!r} is not in the closed set"
            )
        self.code = code
        self.detail = detail
        template = MESSAGE_TEMPLATES[code]
        if detail:
            message = f"[{code}] {template}: {detail}"
        else:
            message = f"[{code}] {template}"
        super().__init__(message)
