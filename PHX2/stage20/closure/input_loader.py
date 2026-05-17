"""Stage 20.4 input config loader.

Loads + validates the JSON config file supplied to the
orchestrator CLI and returns a typed ``ClosureInputConfig``
together with a tuple of accumulated E20xx validation errors.

Two failure modes are distinguished:

  * ``InputFormatError`` -- raised for pre-validation config
    failures: file missing/unreadable, malformed JSON, missing
    top-level required keys, operator_test_results not a JSON
    object, output_root not a string / not existing / not a
    directory / not writable. These are PRE-RUN-DIR failures
    in the orchestrator (exit code 2; no closure run directory
    is created).

  * ``InputValidationError`` -- a NamedTuple record (code,
    detail). The loader ACCUMULATES these instead of
    short-circuiting. Each entry maps to one of the Stage 20.4
    E20xx codes (E2030, E2031, E2043, E2044, E2045). The
    orchestrator inspects the returned tuple and either
    proceeds (when empty) or writes a ``closure_blocked``
    packet (when non-empty).

What this module does NOT do (Phase 2 boundary):

  * Does NOT read Stage 20.2 / Stage 20.3 manifests.
  * Does NOT parse CSVs or compute artifact hashes.
  * Does NOT create directories or write artifacts.
  * Does NOT run the codebase auditor.
  * Does NOT emit warnings (W20xx).
  * Does NOT enforce / check Stage 20.3 being nested inside
    Stage 20.2 (operator-level concern; lineage crosscheck in
    Phase 4 catches genuinely-mismatched pairs).

Phoenix1 departure note: this module imports no Phoenix1 code.

Boundary discipline: imports only from stdlib + the closure
subtree. Does not import ``PHX2.stage20.*`` outside of
``PHX2.stage20.closure.*``.

Known limitations (v0):

  * test_command is validated as a non-empty string after
    ``str.strip()`` only; the command is not parsed or executed.
  * Path resolution: absolute paths are taken as-is;
    relative paths are resolved against ``repo_root`` for the
    Stage 20.2 / Stage 20.3 run dirs, and against the CWD for
    ``output_root`` / ``repo_root``. The locked spec describes
    ``output_root`` and ``repo_root`` as absolute paths in
    practice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import NamedTuple

from PHX2.stage20.closure.clock_helper import Clock, format_utc_iso_z
from PHX2.stage20.closure.constants import (
    COMMIT_SHA_REGEX,
    RUN_ID_CONFIG_SHA_LENGTH,
)
from PHX2.stage20.closure.models import (
    ClosureInputConfig,
    OperatorTestResults,
)


# ---------------------------------------------------------------------------
# Public types / exceptions
# ---------------------------------------------------------------------------


class InputFormatError(Exception):
    """Raised for pre-validation config failures.

    Categories (mapped to exit code 2 in the orchestrator):
      * config file not found / not a regular file / not readable
      * config file is not valid JSON
      * config root is not a JSON object
      * missing required top-level key
      * operator_test_results is not a JSON object
      * output_root is not a string / does not exist / is not a
        directory / is not writable

    None of these conditions are recorded as E20xx codes;
    output_root is operator infrastructure, not a Stage 20
    artifact / lineage concern.
    """


class InputValidationError(NamedTuple):
    """One accumulated E20xx validation error.

    ``code``   -- one of E2030 / E2031 / E2043 / E2044 / E2045.
    ``detail`` -- short, single-line human-readable string.
    """

    code: str
    detail: str


class LoadedInputs(NamedTuple):
    """Return shape of ``load_input_config``.

    ``config``            -- always materialized, even when
                             ``validation_errors`` is non-empty
                             (the orchestrator uses it when
                             writing a ``closure_blocked``
                             manifest). Fields whose raw values
                             were missing / wrong type get safe
                             default substitutes; the validation
                             error tuple records what was wrong.

    ``validation_errors`` -- tuple of ``InputValidationError``.
                             Empty tuple means input passed every
                             E20xx check (closure may proceed).
    """

    config: ClosureInputConfig
    validation_errors: tuple


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "stage20_1_commit_sha",
    "stage20_2_commit_sha",
    "stage20_3_commit_sha",
    "stage20_2_run_dir",
    "stage20_3_run_dir",
    "repo_root",
    "output_root",
    "operator_test_results",
)


REQUIRED_OPERATOR_FIELDS: tuple[str, ...] = (
    "test_command",
    "run1_passed",
    "run1_failed",
    "run1_errors",
    "run2_passed",
    "run2_failed",
    "run2_errors",
)


_NUMERIC_OPERATOR_FIELDS: tuple[str, ...] = (
    "run1_passed",
    "run1_failed",
    "run1_errors",
    "run2_passed",
    "run2_failed",
    "run2_errors",
)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def load_input_config(
    config_path: Path,
    *,
    clock: Clock,
) -> LoadedInputs:
    """Load + validate the closure JSON config.

    Raises:
        InputFormatError: for pre-validation failures (file,
            JSON, top-level structure, output_root precondition).

    Returns:
        ``LoadedInputs`` whose ``validation_errors`` tuple is
        empty when every E20xx check passed. The ``config``
        field is always materialized.

    The injected ``clock`` is used exactly once to populate the
    ``generated_at_utc`` field on the resulting
    ``ClosureInputConfig`` via ``format_utc_iso_z(clock.now())``.
    No other wall-clock reads happen in this function.
    """

    # -- Step 1: file existence + regular file -----------------
    if not config_path.exists():
        raise InputFormatError(
            f"config file not found: {config_path}"
        )
    if not config_path.is_file():
        raise InputFormatError(
            f"config path is not a regular file: {config_path}"
        )

    # -- Step 2: read + parse JSON -----------------------------
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputFormatError(
            f"config file not readable: {config_path}: {exc}"
        ) from exc
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InputFormatError(
            f"config file is not valid JSON: {config_path}: "
            f"{exc.msg} (line {exc.lineno} col {exc.colno})"
        ) from exc

    # -- Step 3: top-level must be a JSON object ---------------
    if not isinstance(data, dict):
        raise InputFormatError(
            f"config file root must be a JSON object; got "
            f"{type(data).__name__}"
        )

    # -- Step 4: required top-level keys -----------------------
    missing_top = [k for k in REQUIRED_TOP_LEVEL_KEYS if k not in data]
    if missing_top:
        raise InputFormatError(
            f"config missing required top-level key(s): "
            f"{missing_top}"
        )

    # -- Step 5: operator_test_results must be a JSON object ---
    op_block = data["operator_test_results"]
    if not isinstance(op_block, dict):
        raise InputFormatError(
            f"operator_test_results must be a JSON object; got "
            f"{type(op_block).__name__}"
        )

    # -- Step 6: output_root precondition (InputFormatError) ---
    output_root = _validate_output_root_precondition(
        data["output_root"],
    )

    # =========================================================
    # PAST THIS POINT: only E20xx validation errors accumulated.
    # No InputFormatError raised below.
    # =========================================================

    errors: list[InputValidationError] = []

    # -- Step 7: commit SHAs (E2044, each independently) -------
    sha_pattern = re.compile(COMMIT_SHA_REGEX)
    for field_name in (
        "stage20_1_commit_sha",
        "stage20_2_commit_sha",
        "stage20_3_commit_sha",
    ):
        val = data[field_name]
        if not isinstance(val, str) or not sha_pattern.fullmatch(val):
            errors.append(InputValidationError(
                code="E2044",
                detail=(
                    f"{field_name}={val!r} is not a 40-char "
                    f"lowercase hex commit SHA"
                ),
            ))

    # -- Step 8: resolve repo_root + validate (E2045) ----------
    repo_root_raw = data["repo_root"]
    if isinstance(repo_root_raw, str):
        repo_root = Path(repo_root_raw).resolve()
        if (
            not repo_root.exists()
            or not repo_root.is_dir()
            or not (repo_root / "PHX2").is_dir()
        ):
            errors.append(InputValidationError(
                code="E2045",
                detail=(
                    f"repo_root is not a valid PHX2 repo root "
                    f"(missing or PHX2/ subdir absent): "
                    f"{repo_root}"
                ),
            ))
    else:
        repo_root = Path(".").resolve()
        errors.append(InputValidationError(
            code="E2045",
            detail=(
                f"repo_root must be a string path; got "
                f"{type(repo_root_raw).__name__}"
            ),
        ))

    # -- Step 9: stage20_2_run_dir (E2030) ---------------------
    stage20_2_run_dir = _resolve_with_repo_base(
        data["stage20_2_run_dir"],
        repo_root,
    )
    if not _is_existing_directory(data["stage20_2_run_dir"], stage20_2_run_dir):
        errors.append(InputValidationError(
            code="E2030",
            detail=(
                f"stage20_2_run_dir does not exist or is not a "
                f"directory: raw={data['stage20_2_run_dir']!r} "
                f"resolved={stage20_2_run_dir}"
            ),
        ))

    # -- Step 10: stage20_3_run_dir (E2031) --------------------
    stage20_3_run_dir = _resolve_with_repo_base(
        data["stage20_3_run_dir"],
        repo_root,
    )
    if not _is_existing_directory(data["stage20_3_run_dir"], stage20_3_run_dir):
        errors.append(InputValidationError(
            code="E2031",
            detail=(
                f"stage20_3_run_dir does not exist or is not a "
                f"directory: raw={data['stage20_3_run_dir']!r} "
                f"resolved={stage20_3_run_dir}"
            ),
        ))

    # -- Step 11: operator_test_results (E2043; accumulate) ----
    errors.extend(_validate_operator_test_results(op_block))

    # -- Step 12: derived OperatorTestResults ------------------
    op_results = _build_operator_test_results(op_block)

    # -- Step 13: generated_at_utc from injected clock ---------
    generated_at_utc = format_utc_iso_z(clock.now())

    # -- Step 14: build ClosureInputConfig ---------------------
    config = ClosureInputConfig(
        stage20_1_commit_sha=_safe_str(data["stage20_1_commit_sha"]),
        stage20_2_commit_sha=_safe_str(data["stage20_2_commit_sha"]),
        stage20_3_commit_sha=_safe_str(data["stage20_3_commit_sha"]),
        stage20_2_run_dir=stage20_2_run_dir,
        stage20_3_run_dir=stage20_3_run_dir,
        repo_root=repo_root,
        output_root=output_root,
        operator_test_results=op_results,
        generated_at_utc=generated_at_utc,
    )

    return LoadedInputs(
        config=config,
        validation_errors=tuple(errors),
    )


def compute_config_sha8(config: ClosureInputConfig) -> str:
    """Return the first 8 hex chars of sha256(canonical_json(config)).

    Canonical form:
      * Path fields serialized as their resolved absolute string
        (matches what ``load_input_config`` stored on the config).
      * operator_test_results uses only the 7 raw fields
        (test_command + 6 numeric); the derived ``both_runs_match``
        and ``all_green`` are EXCLUDED because they are pure
        functions of the raw fields and including them adds noise
        without changing the digest's discriminative power.
      * ``generated_at_utc`` is EXCLUDED so the digest is
        content-deterministic across different clock values for
        the same input.
      * ``json.dumps(..., sort_keys=True, separators=(",", ":"),
        ensure_ascii=False)`` is applied recursively (all dicts
        at every nesting level are key-sorted).

    The full 64-char hex digest is then truncated to the first
    ``RUN_ID_CONFIG_SHA_LENGTH`` (= 8) characters; lowercase hex
    is the natural output of ``hashlib.sha256().hexdigest()``.
    """

    canonical = {
        "stage20_1_commit_sha": config.stage20_1_commit_sha,
        "stage20_2_commit_sha": config.stage20_2_commit_sha,
        "stage20_3_commit_sha": config.stage20_3_commit_sha,
        "stage20_2_run_dir": str(config.stage20_2_run_dir),
        "stage20_3_run_dir": str(config.stage20_3_run_dir),
        "repo_root": str(config.repo_root),
        "output_root": str(config.output_root),
        "operator_test_results": {
            "test_command": config.operator_test_results.test_command,
            "run1_passed": config.operator_test_results.run1_passed,
            "run1_failed": config.operator_test_results.run1_failed,
            "run1_errors": config.operator_test_results.run1_errors,
            "run2_passed": config.operator_test_results.run2_passed,
            "run2_failed": config.operator_test_results.run2_failed,
            "run2_errors": config.operator_test_results.run2_errors,
        },
    }
    blob = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return digest[:RUN_ID_CONFIG_SHA_LENGTH]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_output_root_precondition(raw_value) -> Path:
    """Resolve + validate output_root. Raises InputFormatError on failure.

    output_root failures are infrastructure preconditions: if it
    is invalid there is nowhere safe to write a closure manifest.
    See operator decision on E2049 / no E2050 allocation.
    """

    if not isinstance(raw_value, str):
        raise InputFormatError(
            f"output_root must be a string path; got "
            f"{type(raw_value).__name__}"
        )
    try:
        resolved = Path(raw_value).resolve()
    except OSError as exc:
        raise InputFormatError(
            f"output_root path could not be resolved: "
            f"{raw_value!r}: {exc}"
        ) from exc
    if not resolved.exists():
        raise InputFormatError(
            f"output_root does not exist: {resolved}"
        )
    if not resolved.is_dir():
        raise InputFormatError(
            f"output_root is not a directory: {resolved}"
        )
    if not os.access(resolved, os.W_OK):
        raise InputFormatError(
            f"output_root is not writable: {resolved}"
        )
    return resolved


def _resolve_with_repo_base(raw_value, repo_root: Path) -> Path:
    """Resolve a config path. Absolute -> .resolve(); relative ->
    relative to ``repo_root``. Non-string input returns a placeholder
    (the caller records an E20xx error separately)."""

    if not isinstance(raw_value, str):
        return Path(".").resolve()
    p = Path(raw_value)
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def _is_existing_directory(raw_value, resolved: Path) -> bool:
    """True iff the raw value parsed as a string AND the resolved
    path exists AND is a directory."""

    if not isinstance(raw_value, str):
        return False
    return resolved.exists() and resolved.is_dir()


def _safe_str(v) -> str:
    """Return v if it is a string; otherwise return ""."""

    if isinstance(v, str):
        return v
    return ""


def _validate_operator_test_results(
    block: dict,
) -> list[InputValidationError]:
    """Run the C.7 consistency rules; return accumulated E2043 entries.

    Rules (every violation records its own E2043 entry):
      1. Every required field present.
      2. test_command is a non-empty string after strip().
      3. Each numeric field is a non-negative int (bool rejected).
      4. run1_failed + run1_errors == 0.
      5. run2_failed + run2_errors == 0.
      6. run1_passed == run2_passed.
      7. Not the case that run1_passed == 0 AND run2_passed == 0.

    Cross-field checks (4-7) only fire for fields that are
    present AND well-typed; otherwise the type errors recorded
    in rule 3 are the actionable signal.
    """

    errors: list[InputValidationError] = []

    # 1. Missing fields (one summary entry).
    missing = [f for f in REQUIRED_OPERATOR_FIELDS if f not in block]
    if missing:
        errors.append(InputValidationError(
            code="E2043",
            detail=(
                f"operator_test_results missing required field(s): "
                f"{missing}"
            ),
        ))

    # 2. test_command must be a non-empty string after strip().
    if "test_command" in block:
        tc = block["test_command"]
        if not isinstance(tc, str) or not tc.strip():
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    "operator_test_results.test_command must be a "
                    "non-empty string after strip()"
                ),
            ))

    # 3. Numeric fields are non-negative ints (reject bool subclass).
    type_errors: set[str] = set()
    for fname in _NUMERIC_OPERATOR_FIELDS:
        if fname not in block:
            continue
        v = block[fname]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    f"operator_test_results.{fname}={v!r} must be a "
                    f"non-negative integer"
                ),
            ))
            type_errors.add(fname)

    def _valid(fn: str) -> bool:
        return fn in block and fn not in type_errors

    # 4. run1 must be green.
    if _valid("run1_failed") and _valid("run1_errors"):
        if block["run1_failed"] + block["run1_errors"] != 0:
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    f"operator_test_results.run1 is not green: "
                    f"failed={block['run1_failed']} "
                    f"errors={block['run1_errors']}"
                ),
            ))

    # 5. run2 must be green.
    if _valid("run2_failed") and _valid("run2_errors"):
        if block["run2_failed"] + block["run2_errors"] != 0:
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    f"operator_test_results.run2 is not green: "
                    f"failed={block['run2_failed']} "
                    f"errors={block['run2_errors']}"
                ),
            ))

    # 6. run1_passed == run2_passed.
    if _valid("run1_passed") and _valid("run2_passed"):
        if block["run1_passed"] != block["run2_passed"]:
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    f"operator_test_results passed-count mismatch: "
                    f"run1_passed={block['run1_passed']} "
                    f"run2_passed={block['run2_passed']}"
                ),
            ))

    # 7. Not both runs zero.
    if _valid("run1_passed") and _valid("run2_passed"):
        if block["run1_passed"] == 0 and block["run2_passed"] == 0:
            errors.append(InputValidationError(
                code="E2043",
                detail=(
                    "operator_test_results recorded zero passed "
                    "tests in both runs"
                ),
            ))

    return errors


def _build_operator_test_results(block: dict) -> OperatorTestResults:
    """Materialize OperatorTestResults from a possibly-invalid block.

    Missing or non-int numeric fields default to 0; test_command
    defaults to ``""`` when missing or non-string. Derived
    ``both_runs_match`` and ``all_green`` are computed from the
    resulting (possibly default) values. The validation pass
    captures what the operator actually supplied.
    """

    def _safe_int(v) -> int:
        if isinstance(v, bool):
            return 0
        if isinstance(v, int) and v >= 0:
            return v
        return 0

    tc = block.get("test_command", "")
    if not isinstance(tc, str):
        tc = ""

    r1p = _safe_int(block.get("run1_passed", 0))
    r1f = _safe_int(block.get("run1_failed", 0))
    r1e = _safe_int(block.get("run1_errors", 0))
    r2p = _safe_int(block.get("run2_passed", 0))
    r2f = _safe_int(block.get("run2_failed", 0))
    r2e = _safe_int(block.get("run2_errors", 0))

    both_runs_match = (
        r1p == r2p and r1f == r2f and r1e == r2e
    )
    all_green = (
        r1f + r1e + r2f + r2e == 0 and r1p > 0
    )

    return OperatorTestResults(
        test_command=tc,
        run1_passed=r1p,
        run1_failed=r1f,
        run1_errors=r1e,
        run2_passed=r2p,
        run2_failed=r2f,
        run2_errors=r2e,
        both_runs_match=both_runs_match,
        all_green=all_green,
    )


__all__ = [
    "InputFormatError",
    "InputValidationError",
    "LoadedInputs",
    "REQUIRED_OPERATOR_FIELDS",
    "REQUIRED_TOP_LEVEL_KEYS",
    "compute_config_sha8",
    "load_input_config",
]
