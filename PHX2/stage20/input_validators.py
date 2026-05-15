"""Stage 20 input validators.

Reads Stage 18 + Stage 19 run directories and surfaces the locked
set of E2001..E2010 errors and W2001/W2004/W2005 warnings. Codes
that 20.1 actively emits vs. defines-but-defers are listed in
``PHX2.stage20.constants.CODES_ACTIVE_IN_STAGE_20_1`` and
``CODES_DEFERRED_IN_STAGE_20_1``.

20.1 sub-phases populate this module incrementally:
  * 20.1.B -- run-dir locators + hash verifier (E2001, E2002, E2003)
  * 20.1.C -- column / label / taxonomy / SAFE_FOR_LIVE_DISPATCH
              defensive checks (E2005..E2010, E2022)
  * 20.1.D -- aggregate ``validate_inputs`` + warning detectors
              (W2001, W2004, W2005)

Behavior contracts:

  * The locators (``locate_stage18_run`` and ``locate_stage19_run``)
    raise ``Stage20ValidationError`` on missing manifests so the
    aggregate orchestrator can record a clean ``halted_at`` and
    skip downstream validation.
  * Every other validator returns ``list[EligibilityErrorCode]``
    or ``list[EligibilityWarningCode]`` so the aggregate
    orchestrator can accumulate multiple findings per run.

Path handling: ``pathlib.Path`` exclusively; no string
concatenation; Windows-safe.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional, Sequence

from PHX2.stage20.clock import Clock, default_clock
from PHX2.stage20.constants import (
    EligibilityErrorCode,
    EligibilityWarningCode,
    LABEL_TO_STATE_MAPPING_V0,
    STAGE18_MANIFEST_FILENAME,
    STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
    STAGE18_REVIEW_MATRIX_FILENAME,
    STAGE19_LEDGER_EXPECTED_COLUMNS,
    STAGE19_LEDGER_FILENAME,
    STAGE19_LEDGER_TIMESTAMP_FORMAT,
    STAGE19_MANIFEST_FILENAME,
    STAGE19_MANIFEST_KEY_STAGE18_MANIFEST_HASH,
    STAGE19_MANIFEST_KEY_STAGE18_REVIEW_MATRIX_HASH,
    STAGE19_REVIEW_LABELS,
    STALENESS_THRESHOLD_DAYS,
)
from PHX2.stage20.errors import Stage20ValidationError


# 64 KiB streaming reads for SHA-256 (matches PHX2/stage19/manifest.py).
_HASH_CHUNK_SIZE: int = 65536


class Stage18RunFiles(NamedTuple):
    """Typed handle to the required files inside a Stage 18 run dir."""

    run_dir: Path
    manifest_path: Path
    review_matrix_path: Path


class Stage19RunFiles(NamedTuple):
    """Typed handle to the required files inside a Stage 19 run dir."""

    run_dir: Path
    manifest_path: Path
    ledger_path: Path


def _compute_file_sha256(path: Path) -> str:
    """Return the 64-hex lowercase SHA-256 digest of ``path``.

    Streams the file in 64 KiB chunks rather than loading the
    whole file into memory. Matches the hash computation in
    PHX2/stage19/manifest.py compute_file_sha256.
    """

    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 20.1.B -- run-dir locators
# ---------------------------------------------------------------------------


def locate_stage18_run(run_dir: Path) -> Stage18RunFiles:
    """Locate the required files inside a Stage 18 run directory.

    Returns a Stage18RunFiles tuple. The presence of ``manifest.json``
    is enforced here (E2001); the presence of ``review_matrix.csv``
    is enforced later by ``validate_stage18_review_matrix_columns``
    so a missing review_matrix surfaces as an E2008 schema error.

    Raises:
        Stage20ValidationError(E2001): when ``manifest.json`` is
            absent from ``run_dir``.
    """

    manifest_path = run_dir / STAGE18_MANIFEST_FILENAME
    review_matrix_path = run_dir / STAGE18_REVIEW_MATRIX_FILENAME

    if not manifest_path.is_file():
        raise Stage20ValidationError(
            EligibilityErrorCode.E2001,
            detail=str(manifest_path),
        )

    return Stage18RunFiles(
        run_dir=run_dir,
        manifest_path=manifest_path,
        review_matrix_path=review_matrix_path,
    )


def locate_stage19_run(run_dir: Path) -> Stage19RunFiles:
    """Locate the required files inside a Stage 19 run directory.

    Returns a Stage19RunFiles tuple. The presence of ``manifest.json``
    is enforced here (E2002); the presence of the ledger is
    enforced later by ``validate_stage19_ledger_columns`` so a
    missing ledger surfaces as an E2009 schema error.

    Raises:
        Stage20ValidationError(E2002): when ``manifest.json`` is
            absent from ``run_dir``.
    """

    manifest_path = run_dir / STAGE19_MANIFEST_FILENAME
    ledger_path = run_dir / STAGE19_LEDGER_FILENAME

    if not manifest_path.is_file():
        raise Stage20ValidationError(
            EligibilityErrorCode.E2002,
            detail=str(manifest_path),
        )

    return Stage19RunFiles(
        run_dir=run_dir,
        manifest_path=manifest_path,
        ledger_path=ledger_path,
    )


# ---------------------------------------------------------------------------
# 20.1.B -- hash verifier (E2003 active, E2004 defined-but-deferred)
# ---------------------------------------------------------------------------


def verify_input_hashes(
    stage18_files: Stage18RunFiles,
    stage19_files: Stage19RunFiles,
) -> list[EligibilityErrorCode]:
    """Verify Stage 18 input file hashes against the SHA-256 values
    recorded in Stage 19's manifest.

    E2003 (active in 20.1):
        Compares the recomputed SHA-256 of the Stage 18 manifest.json
        and review_matrix.csv against the values recorded in
        Stage 19's manifest under the keys
        ``stage18_manifest_sha256`` and
        ``stage18_review_matrix_sha256``. Any mismatch emits
        ``EligibilityErrorCode.E2003`` once per failing file.

    E2004 (deferred in 20.1):
        There is no source-of-truth SHA-256 for the Stage 19 ledger
        anywhere in the current pipeline (Stage 19's own manifest
        only records hashes of the upstream inputs Stage 19
        consumed, not its own ledger output). E2004 remains in
        ``EligibilityErrorCode`` and ``ERROR_MESSAGE_TEMPLATES``
        but is never emitted by this function in 20.1. A baseline
        sidecar or post-write hash record could activate E2004 in
        a later phase.

    Behavior when Stage 19's manifest is unreadable / malformed:
        ``verify_input_hashes`` returns ``[]`` (no errors). Stage 19
        manifest schema correctness is out of scope for the hash
        verifier; a separate Stage 20 validator (slated for 20.2)
        will catch a malformed manifest. This keeps
        ``verify_input_hashes`` idempotent and a pure hash
        comparator.

    Behavior when a hash field is absent from Stage 19's manifest:
        That specific file's hash check is skipped. A missing hash
        key in the manifest is silent here; presence-but-mismatch
        is the only path that emits E2003.

    Returns:
        A list of EligibilityErrorCode values. Empty if every
        comparable hash matched (or no hashes were comparable).
    """

    errors: list[EligibilityErrorCode] = []

    try:
        raw = stage19_files.manifest_path.read_text(encoding="utf-8")
        s19_manifest = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return errors

    if not isinstance(s19_manifest, dict):
        return errors

    expected_s18_manifest_hash = s19_manifest.get(
        STAGE19_MANIFEST_KEY_STAGE18_MANIFEST_HASH
    )
    if (
        isinstance(expected_s18_manifest_hash, str)
        and expected_s18_manifest_hash
        and stage18_files.manifest_path.is_file()
    ):
        actual = _compute_file_sha256(stage18_files.manifest_path)
        if actual != expected_s18_manifest_hash:
            errors.append(EligibilityErrorCode.E2003)

    expected_s18_rm_hash = s19_manifest.get(
        STAGE19_MANIFEST_KEY_STAGE18_REVIEW_MATRIX_HASH
    )
    if (
        isinstance(expected_s18_rm_hash, str)
        and expected_s18_rm_hash
        and stage18_files.review_matrix_path.is_file()
    ):
        actual = _compute_file_sha256(stage18_files.review_matrix_path)
        if actual != expected_s18_rm_hash:
            errors.append(EligibilityErrorCode.E2003)

    return errors


# ---------------------------------------------------------------------------
# 20.1.C -- schema column validators
# ---------------------------------------------------------------------------


def _read_csv_header(path: Path) -> list[str] | None:
    """Return the header row of a CSV at ``path``, or None if the file
    is missing, empty, or unreadable.
    """

    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                return next(reader)
            except StopIteration:
                return None
    except OSError:
        return None


def validate_stage18_review_matrix_columns(
    review_matrix_path: Path,
) -> list[EligibilityErrorCode]:
    """Verify the Stage 18 review_matrix.csv header contains every
    locked column in STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS.

    Returns:
        ``[EligibilityErrorCode.E2008]`` if the file is missing,
        empty, has no header, or is missing any required column.
        Empty list on success.

    20.1.C does not enforce column ORDER or absence of EXTRA columns;
    only the required-column subset is checked. Stage 20.2 may
    tighten this if downstream consumers need order guarantees.
    """

    header = _read_csv_header(review_matrix_path)
    if header is None:
        return [EligibilityErrorCode.E2008]
    if not set(STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS).issubset(set(header)):
        return [EligibilityErrorCode.E2008]
    return []


def validate_stage19_ledger_columns(
    ledger_path: Path,
) -> list[EligibilityErrorCode]:
    """Verify the Stage 19 ledger CSV header contains every locked
    column in STAGE19_LEDGER_EXPECTED_COLUMNS.

    Returns:
        ``[EligibilityErrorCode.E2009]`` if the file is missing,
        empty, has no header, or is missing any required column.
        Empty list on success.
    """

    header = _read_csv_header(ledger_path)
    if header is None:
        return [EligibilityErrorCode.E2009]
    if not set(STAGE19_LEDGER_EXPECTED_COLUMNS).issubset(set(header)):
        return [EligibilityErrorCode.E2009]
    return []


def read_stage19_ledger_rows(ledger_path: Path) -> list[dict[str, str]]:
    """Read all rows of the Stage 19 ledger as dicts.

    Returns an empty list if the file is missing, has only a header,
    or is unreadable. Does no schema validation -- caller is
    responsible for running ``validate_stage19_ledger_columns``
    first if they require schema completeness.
    """

    if not ledger_path.is_file():
        return []
    try:
        with ledger_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except OSError:
        return []


def validate_stage19_operator_labels(
    ledger_rows: Sequence[dict[str, str]],
) -> list[EligibilityErrorCode]:
    """Check each ledger row's operator review label.

    For each row:
      * empty / missing review_label -> emit E2007 (once total).
      * non-empty label not in LABEL_TO_STATE_MAPPING_V0 -> emit
        E2005 (once total).

    Defense-in-depth rationale: Stage 19's own readers enforce label
    validity on input. Stage 20 re-checks because the ledger CSV
    on disk could have been tampered with or could carry an
    operator label from a future Stage 19 schema bump.

    Returns:
        A list containing at most one E2007 and at most one E2005.
    """

    errors: list[EligibilityErrorCode] = []
    seen_missing = False
    seen_unknown = False

    for row in ledger_rows:
        label = row.get("review_label", "")
        if not label:
            if not seen_missing:
                errors.append(EligibilityErrorCode.E2007)
                seen_missing = True
            continue
        if label not in LABEL_TO_STATE_MAPPING_V0:
            if not seen_unknown:
                errors.append(EligibilityErrorCode.E2005)
                seen_unknown = True

    return errors


def validate_stage19_ledger_row_id_uniqueness(
    ledger_rows: Sequence[dict[str, str]],
) -> list[EligibilityErrorCode]:
    """Verify that ledger_row_id values are unique across all rows.

    Stage 19's ledger_row_id is a deterministic 16-hex SHA-256
    prefix over the canonical identity fields. Duplicates indicate
    either a determinism failure inside Stage 19 or post-hoc
    tampering of the ledger CSV.

    Renamed from "duplicate_review_id" per the STEP 0 operator
    decision: Stage 19 has no review_id column; ledger_row_id is
    the deterministic per-row identifier Stage 19 produces.

    Returns:
        ``[EligibilityErrorCode.E2006]`` on the first duplicate.
        Empty list otherwise. Rows whose ledger_row_id is empty
        are skipped (presence enforced by E2009).
    """

    seen: set[str] = set()
    for row in ledger_rows:
        rid = row.get("ledger_row_id", "")
        if not rid:
            continue
        if rid in seen:
            return [EligibilityErrorCode.E2006]
        seen.add(rid)
    return []


def verify_eligibility_taxonomy_completeness() -> list[EligibilityErrorCode]:
    """Internal self-check that LABEL_TO_STATE_MAPPING_V0 covers
    exactly the locked Stage 19 LABELS set.

    Emits E2010 if the mapping's key set diverges from the Stage 19
    label set in either direction (missing keys -> mapping cannot
    map every observed label; extra keys -> mapping has drifted
    beyond the locked Stage 19 vocabulary).
    """

    if set(LABEL_TO_STATE_MAPPING_V0.keys()) != set(STAGE19_REVIEW_LABELS):
        return [EligibilityErrorCode.E2010]
    return []


def defensive_check_safe_for_live_dispatch() -> list[EligibilityErrorCode]:
    """Defense-in-depth check that SAFE_FOR_LIVE_DISPATCH is False.

    Reads the current value from PHX2.stage20.constants at call
    time so tests can monkeypatch the attribute and exercise
    E2022. Stage 20 must refuse to run if any future edit flips
    this constant to True.

    Returns:
        ``[EligibilityErrorCode.E2022]`` if the constant is not
        False. Empty list otherwise.
    """

    # Re-read from the constants module at call time so the test
    # monkeypatch in test_safe_dispatch can flip the value without
    # also rebinding the symbol imported into this module.
    from PHX2.stage20 import constants as _constants

    if _constants.SAFE_FOR_LIVE_DISPATCH is not False:
        return [EligibilityErrorCode.E2022]
    return []


# ---------------------------------------------------------------------------
# 20.1.D -- warning detectors
# ---------------------------------------------------------------------------


def _parse_ledger_timestamp(ts: str) -> Optional[datetime]:
    """Parse a Stage 19 ledger timestamp string (``YYYY-MM-DDTHH:MM:SSZ``).

    Returns a tz-aware UTC datetime on success, or None if the
    string cannot be parsed. Parse failure is silent here because
    a malformed timestamp is a Stage 19 contract violation; Stage
    20 surfaces that as part of its column / read validators in
    20.1.C and downstream phases.
    """

    try:
        parsed = datetime.strptime(ts, STAGE19_LEDGER_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _median(values: Sequence[float]) -> float:
    """Return the median of a non-empty sorted-or-unsorted sequence."""

    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def detect_staleness_overall(
    ledger_rows: Sequence[dict[str, str]],
    clock: Clock,
) -> list[EligibilityWarningCode]:
    """Emit W2001 if the median ledger-row age exceeds
    STALENESS_THRESHOLD_DAYS.

    Operator decision (STEP 0): median is computed OVER ROWS, not
    over distinct Stage 19 runs. Every ledger row carries a
    review_timestamp_utc that equals the run-level timestamp of
    the Stage 19 invocation that produced it -- per-row median
    will cluster by run, which is the intended behavior.

    Returns:
        ``[EligibilityWarningCode.W2001]`` if the median age is
        strictly greater than ``STALENESS_THRESHOLD_DAYS``. Empty
        list otherwise (including the case where no row carries a
        parseable timestamp).
    """

    if not ledger_rows:
        return []

    now = clock.now()
    ages_in_days: list[float] = []
    for row in ledger_rows:
        parsed = _parse_ledger_timestamp(row.get("review_timestamp_utc", ""))
        if parsed is None:
            continue
        delta = now - parsed
        ages_in_days.append(delta.total_seconds() / 86400.0)

    if not ages_in_days:
        return []

    if _median(ages_in_days) > STALENESS_THRESHOLD_DAYS:
        return [EligibilityWarningCode.W2001]
    return []


def detect_multiple_operators_per_review_slice(
    ledger_rows: Sequence[dict[str, str]],
) -> list[EligibilityWarningCode]:
    """Emit W2004 if any review slice has been reviewed by 2+
    distinct operator_ids.

    Renamed from "multiple_reviews_for_same_token" per the STEP 0
    operator decision: Stage 18/19 have no token concept and
    Stage 19 explicitly supports same-slice revisits via
    review_sequence. Same-slice revisits by a single operator
    are EXPECTED, not a warning; W2004 fires only when distinct
    operators reviewed the same slice (a genuinely orthogonal
    signal).

    A review slice is the tuple
    ``(stage18_run_id, policy_hash, rule_id, window_seconds)``.

    Returns:
        ``[EligibilityWarningCode.W2004]`` if any slice has been
        reviewed by 2+ distinct operators. Empty list otherwise.
    """

    slice_operators: dict[tuple[str, str, str, str], set[str]] = {}
    for row in ledger_rows:
        key = (
            row.get("stage18_run_id", ""),
            row.get("policy_hash", ""),
            row.get("rule_id", ""),
            row.get("window_seconds", ""),
        )
        op = row.get("operator_id", "")
        if not op:
            continue
        slice_operators.setdefault(key, set()).add(op)

    for operators in slice_operators.values():
        if len(operators) >= 2:
            return [EligibilityWarningCode.W2004]
    return []


def detect_stage18_evidence_gaps(
    stage18_review_matrix_path: Path,
    ledger_rows: Sequence[dict[str, str]],
) -> list[EligibilityWarningCode]:
    """Emit W2005 if any Stage 19 ledger row references a slice key
    not present in the Stage 18 review_matrix.

    The slice key is ``(policy_hash, rule_id, window_seconds)`` --
    matching the index key Stage 19's readers use to join ledger
    rows back to the review_matrix.

    20.1 reports the warning only. Stage 20.2 will use the gap to
    skip candidate construction; in 20.1 there is no candidate
    construction, so this is reporting only.

    Returns:
        ``[EligibilityWarningCode.W2005]`` if any ledger row's
        slice key is missing from the review_matrix. Empty list
        if the review_matrix is unreadable (the schema validator
        already emitted E2008 in that case).
    """

    if not stage18_review_matrix_path.is_file():
        return []

    review_matrix_keys: set[tuple[str, str, str]] = set()
    try:
        with stage18_review_matrix_path.open(
            "r", encoding="utf-8", newline=""
        ) as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (
                    row.get("policy_hash", "") or "",
                    row.get("rule_id", "") or "",
                    row.get("window_seconds", "") or "",
                )
                review_matrix_keys.add(key)
    except OSError:
        return []

    for row in ledger_rows:
        key = (
            row.get("policy_hash", ""),
            row.get("rule_id", ""),
            row.get("window_seconds", ""),
        )
        if key not in review_matrix_keys:
            return [EligibilityWarningCode.W2005]
    return []


# ---------------------------------------------------------------------------
# 20.1.D -- aggregate validate_inputs orchestrator
# ---------------------------------------------------------------------------


class ValidationResult(NamedTuple):
    """Public return type from ``validate_inputs``.

    Fields:
      * ok        -- True iff ``errors`` is empty.
      * errors    -- tuple of EligibilityErrorCode VALUES (strings)
                     in the order they were accumulated. May be
                     empty.
      * warnings  -- tuple of EligibilityWarningCode VALUES
                     (strings) in order. May be empty.
      * summary   -- dict of run-level metadata that 20.2 can
                     promote into its emitted manifest. Always
                     present; partial when a locator halts.
    """

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: dict[str, object]


def validate_inputs(
    stage18_dir: Path,
    stage19_dir: Path,
    *,
    clock: Optional[Clock] = None,
) -> ValidationResult:
    """Run every Stage 20.1 validator and accumulate findings.

    Order of operations:
      1. locate_stage18_run         -> may raise E2001 (caught,
                                       returns partial summary).
      2. locate_stage19_run         -> may raise E2002 (same).
      3. verify_input_hashes        -> E2003 (active).
      4. validate_stage18_review_matrix_columns -> E2008.
      5. validate_stage19_ledger_columns        -> E2009.
      6. read ledger rows.
      7. validate_stage19_operator_labels       -> E2005, E2007.
      8. validate_stage19_ledger_row_id_uniqueness -> E2006.
      9. verify_eligibility_taxonomy_completeness -> E2010.
     10. defensive_check_safe_for_live_dispatch -> E2022.
     11. detect_staleness_overall              -> W2001.
     12. detect_multiple_operators_per_review_slice -> W2004.
     13. detect_stage18_evidence_gaps         -> W2005.

    Args:
        stage18_dir: Path to a closed Stage 18 run directory.
        stage19_dir: Path to a closed Stage 19 run directory.
        clock: Optional injectable Clock. Defaults to SystemClock.
            Tests inject a FrozenClock for determinism.

    Returns:
        A ValidationResult with ``ok = not errors``, frozen
        ordered tuples of error/warning code values, and a
        summary dict carrying basic run-level metadata. Same
        inputs + same injected clock yield equal results across
        repeated calls.
    """

    if clock is None:
        clock = default_clock()

    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, object] = {
        "stage18_dir": str(stage18_dir),
        "stage19_dir": str(stage19_dir),
        "halted_at": None,
        "ledger_row_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }

    # 1. Locate Stage 18
    try:
        s18_files = locate_stage18_run(stage18_dir)
    except Stage20ValidationError as exc:
        errors.append(exc.code)
        summary["halted_at"] = "locate_stage18"
        summary["error_count"] = len(errors)
        return ValidationResult(
            ok=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
            summary=summary,
        )

    # 2. Locate Stage 19
    try:
        s19_files = locate_stage19_run(stage19_dir)
    except Stage20ValidationError as exc:
        errors.append(exc.code)
        summary["halted_at"] = "locate_stage19"
        summary["error_count"] = len(errors)
        return ValidationResult(
            ok=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
            summary=summary,
        )

    # 3. Verify input hashes (E2003 active; E2004 deferred)
    for err in verify_input_hashes(s18_files, s19_files):
        errors.append(err.value)

    # 4. Stage 18 review_matrix column schema (E2008)
    for err in validate_stage18_review_matrix_columns(
        s18_files.review_matrix_path
    ):
        errors.append(err.value)

    # 5. Stage 19 ledger column schema (E2009)
    for err in validate_stage19_ledger_columns(s19_files.ledger_path):
        errors.append(err.value)

    # 6. Read ledger rows (best-effort; DictReader handles missing
    #    columns gracefully and downstream validators are
    #    null-safe).
    ledger_rows = read_stage19_ledger_rows(s19_files.ledger_path)
    summary["ledger_row_count"] = len(ledger_rows)

    # 7. Operator label checks (E2005, E2007)
    for err in validate_stage19_operator_labels(ledger_rows):
        errors.append(err.value)

    # 8. Ledger row id uniqueness (E2006)
    for err in validate_stage19_ledger_row_id_uniqueness(ledger_rows):
        errors.append(err.value)

    # 9. Taxonomy completeness self-check (E2010)
    for err in verify_eligibility_taxonomy_completeness():
        errors.append(err.value)

    # 10. SAFE_FOR_LIVE_DISPATCH defensive check (E2022)
    for err in defensive_check_safe_for_live_dispatch():
        errors.append(err.value)

    # 11-13. Warnings
    for warn in detect_staleness_overall(ledger_rows, clock):
        warnings.append(warn.value)
    for warn in detect_multiple_operators_per_review_slice(ledger_rows):
        warnings.append(warn.value)
    for warn in detect_stage18_evidence_gaps(
        s18_files.review_matrix_path, ledger_rows
    ):
        warnings.append(warn.value)

    summary["error_count"] = len(errors)
    summary["warning_count"] = len(warnings)

    return ValidationResult(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        summary=summary,
    )


__all__ = [
    "Stage18RunFiles",
    "Stage19RunFiles",
    "ValidationResult",
    "defensive_check_safe_for_live_dispatch",
    "detect_multiple_operators_per_review_slice",
    "detect_stage18_evidence_gaps",
    "detect_staleness_overall",
    "locate_stage18_run",
    "locate_stage19_run",
    "read_stage19_ledger_rows",
    "validate_inputs",
    "validate_stage18_review_matrix_columns",
    "validate_stage19_ledger_columns",
    "validate_stage19_ledger_row_id_uniqueness",
    "validate_stage19_operator_labels",
    "verify_eligibility_taxonomy_completeness",
    "verify_input_hashes",
]
