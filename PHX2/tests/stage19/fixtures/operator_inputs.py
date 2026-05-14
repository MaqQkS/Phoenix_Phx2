"""Helpers that write operator-input CSVs used by Stage 19 tests.

The operator-input CSV (``operator_review_input.csv``) is the
human-supplied side of Stage 19's input contract: one row per
slice the operator reviewed, holding the slice key, the reviewer's
label, and free-text notes. ``operator_id`` is intentionally NOT
a CSV column -- it is a CLI scalar (``--operator-id``) passed
once per Stage 19 invocation.

These helpers build valid inputs and common invalid variants for
negative-path tests.

These helpers do **not** import ``PHX2.stage17`` or
``PHX2.stage18``. They also do not import
``PHX2.stage19.constants``: the operator-input column tuple,
review-label vocabulary, and length caps are duplicated locally so
a typo in ``PHX2.stage19.constants`` is caught by these tests
rather than silently mirrored. Test fixtures are an independent
source of truth for the operator-input contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Locked operator-input contract values (independently duplicated)
# ---------------------------------------------------------------------------


_OPERATOR_INPUT_COLUMNS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "review_label",
    "review_notes",
)


_LABELS: tuple[str, ...] = (
    "REVIEW_PROMISING_CONFIRMED",
    "REVIEW_HARMFUL_CONFIRMED",
    "REVIEW_REJECTED",
    "WATCHLIST",
    "NEEDS_MORE_DATA",
    "INCONCLUSIVE",
)


_DEFAULT_RUN_ID: str = "0123456789abcdef"
_DEFAULT_POLICY_HASH: str = "abc123def456"
_DEFAULT_RULE_ID: str = "rule_minimal"
_DEFAULT_WINDOW_SECONDS: str = "3600"
_DEFAULT_REVIEW_LABEL: str = "REVIEW_PROMISING_CONFIRMED"
_DEFAULT_NOTES: str = "Reviewed and concur with Stage 18 evidence."


_MAX_OPERATOR_ID_LENGTH: int = 64
_MAX_REVIEW_NOTES_LENGTH: int = 2000


# ---------------------------------------------------------------------------
# Public helpers -- valid inputs
# ---------------------------------------------------------------------------


def write_minimal_valid_operator_input(
    path: Path,
    *,
    rows: Sequence[Sequence[str]] = (),
) -> Path:
    """Write a minimal but contract-valid operator-input CSV.

    If ``rows`` is empty, writes a single default row matching the
    minimal Stage 18 packet produced by
    ``stage18_outputs.write_minimal_valid_stage18_output`` (same
    run id, slice key, default review_label
    ``REVIEW_PROMISING_CONFIRMED``). Otherwise writes the supplied
    rows verbatim under the locked 6-column header.
    """

    data_rows: Sequence[Sequence[str]] = (
        rows if rows else (make_operator_row(),)
    )
    _write_csv(path, _OPERATOR_INPUT_COLUMNS, data_rows)
    return path


def make_operator_row(
    *,
    stage18_run_id: str = _DEFAULT_RUN_ID,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    rule_id: str = _DEFAULT_RULE_ID,
    window_seconds: str = _DEFAULT_WINDOW_SECONDS,
    review_label: str = _DEFAULT_REVIEW_LABEL,
    review_notes: str = _DEFAULT_NOTES,
) -> tuple[str, ...]:
    """Build a single operator-input row matching the locked
    6-column schema. Defaults compose to a contract-valid row;
    tests override specific cells to trigger negative paths.

    Note: ``operator_id`` is NOT a CSV column -- it's a CLI scalar
    in production, so it does not appear in this row builder.
    """

    return (
        stage18_run_id,
        policy_hash,
        rule_id,
        window_seconds,
        review_label,
        review_notes,
    )


def write_header_only_operator_input(path: Path) -> Path:
    """Header present, no data rows. Per the read_operator_input
    contract this is VALID and yields an empty list of rows."""

    line = ",".join(_OPERATOR_INPUT_COLUMNS) + "\n"
    path.write_text(line, encoding="utf-8", newline="")
    return path


# ---------------------------------------------------------------------------
# Public helpers -- invalid variants (one helper per E-code family)
# ---------------------------------------------------------------------------


def write_empty_operator_input(path: Path) -> Path:
    """Zero-byte file -- no header, no rows. Triggers E07
    (header mismatch) since the file has no header at all."""

    path.write_text("", encoding="utf-8", newline="")
    return path


def write_operator_input_with_header(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[str]] = (),
) -> Path:
    """Write an operator-input CSV with a caller-supplied header
    (E07 trigger when the header diverges from the locked tuple).
    Use to simulate missing column, extra column, reordered, or
    renamed-column header negatives."""

    _write_csv(path, header, rows)
    return path


def write_operator_input_with_short_row(
    path: Path, short_row: Sequence[str]
) -> Path:
    """Write a CSV with a too-short data row (E08 trigger:
    column-count mismatch)."""

    parts = [",".join(_OPERATOR_INPUT_COLUMNS), ",".join(short_row)]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="")
    return path


def make_unknown_review_label() -> str:
    """Return a review_label string that is not in LABELS (E09
    trigger). The string is uppercase and label-shaped to match
    what a hand-edited operator-input CSV would plausibly
    contain."""

    candidate = "MAYBE_PROMISING"
    assert candidate not in _LABELS
    return candidate


def make_oversize_review_notes(
    *, length: int = _MAX_REVIEW_NOTES_LENGTH + 1
) -> str:
    """Produce a review_notes string that exceeds the 2000-char cap
    (E13 trigger). Default ``length`` is one over the cap."""

    return "x" * length


def make_control_char_review_notes(*, char: str = "\t") -> str:
    """Produce a review_notes string containing a control character
    (E13 trigger). Default is a tab; pass ``"\\n"``, ``"\\r"``,
    or ``"\\x00"`` (NUL) for the other negative variants. Space is
    explicitly NOT a control character per the E13 spec."""

    return f"a control char here: [{char}] -- triggers E13"


def make_oversize_operator_id(
    *, length: int = _MAX_OPERATOR_ID_LENGTH + 1
) -> str:
    """Produce an operator_id string that exceeds the 64-char cap
    (E14 trigger). Default ``length`` is one over the cap. Note
    that operator_id is a CLI scalar, not a CSV cell, so this
    helper returns a bare string for use in
    ``--operator-id`` argument tests."""

    return "a" * length


def make_duplicate_identity_rows() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return two rows that share the same
    (stage18_run_id, policy_hash, rule_id, window_seconds) tuple
    (E12 trigger when both reach the duplicate-detection step
    under the same operator_id)."""

    return (make_operator_row(), make_operator_row(review_label="WATCHLIST"))


def make_mismatched_run_id_row(
    *, wrong_run_id: str = "ffffffffffffffff"
) -> tuple[str, ...]:
    """Return a row whose stage18_run_id does NOT match the
    default Stage 18 manifest run_id (E10 trigger)."""

    return make_operator_row(stage18_run_id=wrong_run_id)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _write_csv(
    path: Path, columns: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    """Hand-write a CSV using LF newlines and a trailing newline."""

    parts = [",".join(columns)]
    for row in rows:
        parts.append(",".join(row))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


__all__ = [
    "make_control_char_review_notes",
    "make_duplicate_identity_rows",
    "make_mismatched_run_id_row",
    "make_operator_row",
    "make_oversize_operator_id",
    "make_oversize_review_notes",
    "make_unknown_review_label",
    "write_empty_operator_input",
    "write_header_only_operator_input",
    "write_minimal_valid_operator_input",
    "write_operator_input_with_header",
    "write_operator_input_with_short_row",
]
