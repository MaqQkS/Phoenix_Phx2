"""Stage 19 validators: per-field rules and cross-field rules.

Surfaces five validators that each raise Stage19ValidationError
with a closed-set E-code on failure:

  * validate_operator_id           -- E14
  * validate_run_timestamp         -- E19
  * validate_output_dir            -- E15
  * validate_against_review_matrix -- E10, E11
  * validate_no_duplicates         -- E12

CLI scalars (``--operator-id``, ``--run-timestamp``,
``--output-dir``, ``--prior-ledger-dir``) flow through these
validators in Phase 19.3.

Row indices in error ``.detail`` strings are 1-based to match
operator-friendly debugging conventions (row 1 = first data row
after the header).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from PHX2.stage19.constants import MAX_OPERATOR_ID_LENGTH
from PHX2.stage19.errors import Stage19ValidationError
from PHX2.stage19.readers import OperatorInputRow, ReviewMatrixIndex


# Locked run-timestamp format (YYYY-MM-DDTHH:MM:SSZ).
_RUN_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"


# Characters explicitly forbidden inside operator_id, in addition
# to the general ASCII-printable rule. Listed verbatim here so a
# test can assert each one trips E14.
_OPERATOR_ID_FORBIDDEN_CHARS: frozenset[str] = frozenset({
    ",",
    "'",
    '"',
    "\n",
    "\r",
    "\t",
})


def validate_operator_id(operator_id: str) -> str:
    """Validate the ``--operator-id`` CLI scalar and return the
    canonical stripped form.

    Strips leading/trailing whitespace, then enforces:
      * non-empty after stripping
      * length <= MAX_OPERATOR_ID_LENGTH (64)
      * every character is ASCII printable (chr 32..126
        inclusive)
      * none of: comma, single quote, double quote, newline,
        carriage return, tab
      * no other control characters (everything below chr 32 or
        chr 127 is rejected)
    Internal spaces are allowed.

    Raises Stage19ValidationError with E14 on any failure.
    """

    if not isinstance(operator_id, str):
        raise Stage19ValidationError(
            "E14", detail=f"operator_id is not a string: {type(operator_id)!s}"
        )

    stripped = operator_id.strip()

    if not stripped:
        raise Stage19ValidationError(
            "E14", detail="operator_id is empty after stripping whitespace"
        )

    if len(stripped) > MAX_OPERATOR_ID_LENGTH:
        raise Stage19ValidationError(
            "E14",
            detail=(
                f"operator_id length {len(stripped)} > "
                f"{MAX_OPERATOR_ID_LENGTH}"
            ),
        )

    for ch in stripped:
        code_point = ord(ch)
        if ch in _OPERATOR_ID_FORBIDDEN_CHARS:
            raise Stage19ValidationError(
                "E14",
                detail=(
                    f"operator_id contains forbidden character "
                    f"ord={code_point}"
                ),
            )
        if code_point < 32 or code_point > 126:
            raise Stage19ValidationError(
                "E14",
                detail=(
                    f"operator_id contains non-ASCII-printable char "
                    f"ord={code_point}"
                ),
            )

    return stripped


def validate_run_timestamp(ts_string: str) -> str:
    """Validate the ``--run-timestamp`` CLI scalar.

    Accepts exactly ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, no fractional
    seconds, no timezone offset, T separator). Returns
    ``ts_string`` unchanged on success.

    Raises Stage19ValidationError with E19 for:
      * non-string input
      * empty string
      * missing trailing Z
      * fractional seconds (any '.' present)
      * timezone offset (e.g. +00:00, -05:00) -- caught by the
        no-trailing-Z check
      * space instead of T
      * malformed date / time / non-numeric values
    """

    if not isinstance(ts_string, str):
        raise Stage19ValidationError(
            "E19", detail=f"run-timestamp is not a string: {type(ts_string)!s}"
        )

    if not ts_string:
        raise Stage19ValidationError("E19", detail="run-timestamp is empty")

    if not ts_string.endswith("Z"):
        raise Stage19ValidationError(
            "E19", detail=f"run-timestamp {ts_string!r} missing trailing Z"
        )

    if "." in ts_string:
        raise Stage19ValidationError(
            "E19",
            detail=f"run-timestamp {ts_string!r} has fractional seconds",
        )

    try:
        datetime.strptime(ts_string, _RUN_TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise Stage19ValidationError(
            "E19",
            detail=(
                f"run-timestamp {ts_string!r} not in "
                f"YYYY-MM-DDTHH:MM:SSZ form: {exc}"
            ),
        ) from exc

    return ts_string


def validate_output_dir(path: Path) -> None:
    """Validate the ``--output-dir`` CLI scalar.

    Accepts:
      * a non-existent path (Phase 19.3 writers will create it)
      * an existing empty directory

    Does NOT create the directory.

    Raises Stage19ValidationError with E15 for:
      * path exists as a regular file (not a directory)
      * path exists as a directory and contains at least one
        entry
      * path exists as something other than file or directory
        (symlink to non-existent target, special file, etc.)
    """

    if not path.exists():
        return

    if path.is_file():
        raise Stage19ValidationError(
            "E15",
            detail=f"output_dir {path} exists as a file, not a directory",
        )

    if not path.is_dir():
        raise Stage19ValidationError(
            "E15",
            detail=(
                f"output_dir {path} exists but is not a regular file "
                f"or directory"
            ),
        )

    try:
        next(iter(path.iterdir()))
    except StopIteration:
        return  # empty directory: OK
    raise Stage19ValidationError(
        "E15", detail=f"output_dir {path} exists and is not empty"
    )


def validate_against_review_matrix(
    input_rows: Sequence[OperatorInputRow],
    review_matrix_index: ReviewMatrixIndex,
    stage18_run_id: str,
) -> None:
    """Validate that every operator-input row's stage18_run_id
    matches the Stage 18 manifest run_id, and its slice key
    ``(policy_hash, rule_id, window_seconds)`` appears in the
    review_matrix index.

    Validates rows in input order; raises on the FIRST failing
    row. The ``.detail`` string includes the 1-based row index
    for operator debugging.

    Raises Stage19ValidationError with:
      * E10 if any row's stage18_run_id != ``stage18_run_id``.
      * E11 if any row's slice key is not in
        ``review_matrix_index``.
    """

    for idx, row in enumerate(input_rows, start=1):
        if row.stage18_run_id != stage18_run_id:
            raise Stage19ValidationError(
                "E10",
                detail=(
                    f"row {idx} stage18_run_id={row.stage18_run_id!r} "
                    f"!= manifest run_id={stage18_run_id!r}"
                ),
            )
        key = (row.policy_hash, row.rule_id, row.window_seconds)
        if key not in review_matrix_index:
            raise Stage19ValidationError(
                "E11",
                detail=f"row {idx} identity {key!r} not in review_matrix",
            )


def validate_no_duplicates(
    input_rows: Sequence[OperatorInputRow],
    operator_id: str,
) -> None:
    """Verify no two input rows share
    ``(stage18_run_id, policy_hash, rule_id, window_seconds)``.

    Stage 19 takes one ``--operator-id`` per run, so all rows
    are attributed to the same operator; the parameter is
    accepted for explicitness and forward-compatibility (a
    multi-operator-per-run feature would key on operator_id
    too).

    Raises Stage19ValidationError with E12 on the FIRST
    duplicate discovered. The ``.detail`` string includes both
    1-based row indices.
    """

    seen: dict[tuple[str, str, str, int], int] = {}
    for idx, row in enumerate(input_rows, start=1):
        key = (
            row.stage18_run_id,
            row.policy_hash,
            row.rule_id,
            row.window_seconds,
        )
        if key in seen:
            raise Stage19ValidationError(
                "E12",
                detail=(
                    f"duplicate identity {key!r} at rows "
                    f"{seen[key]} and {idx} for operator_id={operator_id!r}"
                ),
            )
        seen[key] = idx


__all__ = [
    "validate_against_review_matrix",
    "validate_no_duplicates",
    "validate_operator_id",
    "validate_output_dir",
    "validate_run_timestamp",
]
