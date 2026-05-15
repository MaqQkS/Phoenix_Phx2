"""Stage 20 closed-set validation exception.

Mirrors the Stage 18 (B01..B08) and Stage 19 (E01..E21) pattern:
a single ``Stage20ValidationError`` exception whose ``.code``
attribute carries an EligibilityErrorCode value and whose
``.detail`` carries an optional context string. Callers and
tests match on ``.code`` rather than parsing the formatted
message text.

The exception is intentionally flat (no per-code subclasses) so
the exception surface stays small as Stage 20 phases land
additional codes. Codes outside ``EligibilityErrorCode`` are
rejected at construction time.
"""

from __future__ import annotations

from typing import Mapping, Union

from PHX2.stage20.constants import EligibilityErrorCode


ERROR_MESSAGE_TEMPLATES: Mapping[str, str] = {
    "E2001": (
        "Stage 18 manifest.json missing in stage18 input directory"
    ),
    "E2002": (
        "Stage 19 manifest.json missing in stage19 input directory"
    ),
    "E2003": (
        "Stage 18 review_matrix.csv or manifest.json SHA-256 does "
        "not match the hash recorded in Stage 19's manifest"
    ),
    "E2004": (
        "Stage 19 ledger SHA-256 does not match the expected hash "
        "(deferred in Stage 20.1: no source-of-truth hash for the "
        "ledger exists anywhere in the current pipeline)"
    ),
    "E2005": (
        "Stage 19 ledger row carries an operator review label "
        "outside the locked v0 taxonomy"
    ),
    "E2006": (
        "Stage 19 ledger contains duplicate ledger_row_id values"
    ),
    "E2007": (
        "Stage 19 ledger row missing operator review label"
    ),
    "E2008": (
        "Stage 18 review_matrix.csv missing one or more required "
        "columns"
    ),
    "E2009": (
        "Stage 19 operator_review_ledger.csv missing one or more "
        "required columns"
    ),
    "E2010": (
        "Stage 20 eligibility taxonomy mapping does not cover the "
        "locked Stage 19 label set"
    ),
    "E2011": "Preview candidate id collision",
    "E2012": "Filter interface schema violation",
    "E2013": "Filter mode is not OBSERVE_ONLY in v0",
    "E2014": "Filter ordering index collision",
    "E2015": "Decision step index collision",
    "E2016": "Multiple or zero terminating decision steps",
    "E2017": "Decision state inconsistency",
    "E2020": "Preview candidates output is nondeterministic across reruns",
    "E2021": "Manifest input hashes are missing",
    "E2022": "SAFE_FOR_LIVE_DISPATCH is not False",
    "E2023": "Output row count does not match expected",
    "E2024": "Manifest output hashes are missing",
    "E2025": "Output CSV missing required column",
}


_ALL_CODE_VALUES: frozenset[str] = frozenset(
    member.value for member in EligibilityErrorCode
)


class Stage20ValidationError(Exception):
    """Raised on any Stage 20 closed-set validation failure.

    Carries an EligibilityErrorCode value in ``.code`` (always a
    string) and an optional context string in ``.detail``.
    Callers and tests match on ``.code`` rather than inspecting
    the formatted message.

    Subclassing per code is intentionally avoided -- the
    exception surface stays flat across all 23 Stage 20 codes.
    """

    def __init__(
        self,
        code: Union[EligibilityErrorCode, str],
        detail: str = "",
    ) -> None:
        if isinstance(code, EligibilityErrorCode):
            code_value = code.value
        else:
            code_value = code
            if code_value not in _ALL_CODE_VALUES:
                raise ValueError(
                    f"Stage20ValidationError code {code_value!r} is "
                    f"not in the closed set"
                )
        self.code: str = code_value
        self.detail: str = detail
        template = ERROR_MESSAGE_TEMPLATES[code_value]
        if detail:
            message = f"[{code_value}] {template}: {detail}"
        else:
            message = f"[{code_value}] {template}"
        super().__init__(message)


__all__ = [
    "ERROR_MESSAGE_TEMPLATES",
    "Stage20ValidationError",
]
