"""Stage 20.4 artifact validator.

Verifies a Stage 20.2 + Stage 20.3 run pair by:

  * Confirming every required artifact filename exists and is a
    regular file in the respective run directory.
  * Hashing each present artifact (SHA-256, byte count) for the
    closure lineage record.
  * Parsing each manifest as JSON and asserting the locked safety
    flag values (Stage 20.2 ``safe_for_live_dispatch is False``;
    Stage 20.3 ``live_dispatch_ready is False`` and, if present,
    ``safe_for_live_dispatch is False``).
  * Asserting Stage 20.3's ``filter_interface_registry.csv`` and
    ``filter_interface_results.csv`` are each exactly one
    non-empty header row with zero data rows (E2047 / E2048;
    empty files are NOT passing).
  * Cross-checking every Stage 20.2 artifact hash recorded inside
    Stage 20.3's ``stage20_2_lineage`` block against the actual
    SHA-256 computed by Stage 20.4 itself (E2036 on any mismatch
    or missing-file-with-recorded-hash).

Two failure surfaces:

  * ``ArtifactValidationError`` records carry an E20xx code +
    detail string. The orchestrator (Phase 6) consumes the tuple
    to decide ``closure_status`` and to fill the closure manifest's
    ``errors`` block.
  * ``ArtifactValidationWarning`` records carry a W20xx code +
    detail string. Non-blocking; surfaces in the closure manifest
    and the checklist as warning rows.

What this module does NOT do:

  * Does NOT mutate Stage 20.2 or Stage 20.3 artifacts. Every
    ``open()`` on those run dirs uses ``"r"`` or ``"rb"``.
  * Does NOT create directories or write any artifact.
  * Does NOT invoke git, subprocess, or sqlite3.
  * Does NOT read environment variables.
  * Does NOT recompute Stage 20.2 / Stage 20.3 outputs; verify only.
  * Does NOT validate Stage 20.2's self-reported output hashes
    (Phase 0 decision: lineage crosscheck via Stage 20.3 is the
    contract; Stage 20.4 v0 does not duplicate it).

Phoenix1 departure note: this module imports no Phoenix1 code.

Boundary discipline: imports only stdlib + the closure subtree.

Known limitations (v0):

  * Files with non-UTF-8 bytes in their JSON manifest fail E2032 /
    E2033 with the UnicodeDecodeError carried into the detail.
  * The lineage crosscheck iterates the locked field set in
    ``STAGE20_2_LINEAGE_HASH_FIELDS``. Extra fields inside
    ``stage20_2_lineage`` are ignored. Missing fields fire
    E2036.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import NamedTuple

from PHX2.stage20.closure.constants import (
    STAGE20_2_LINEAGE_HASH_FIELDS,
    STAGE20_2_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH,
    STAGE20_2_MANIFEST_FILENAME,
    STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES,
    STAGE20_2_README_FILENAME,
    STAGE20_2_REQUIRED_ARTIFACT_FILENAMES,
    STAGE20_3_FILTER_INTERFACE_REGISTRY_CSV_FILENAME,
    STAGE20_3_FILTER_INTERFACE_RESULTS_CSV_FILENAME,
    STAGE20_3_MANIFEST_FIELD_LIVE_DISPATCH_READY,
    STAGE20_3_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH,
    STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE,
    STAGE20_3_MANIFEST_FILENAME,
    STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES,
    STAGE20_3_README_FILENAME,
    STAGE20_3_REQUIRED_ARTIFACT_FILENAMES,
)
from PHX2.stage20.closure.models import (
    ArtifactHash,
    ArtifactValidationResult,
)


# ---------------------------------------------------------------------------
# Public result + error/warning shapes
# ---------------------------------------------------------------------------


class ArtifactValidationError(NamedTuple):
    """One accumulated E20xx artifact validation error."""

    code: str
    detail: str


class ArtifactValidationWarning(NamedTuple):
    """One accumulated W20xx artifact validation warning (non-blocking)."""

    code: str
    detail: str


class ArtifactValidationOutcome(NamedTuple):
    """Return shape of ``validate_artifacts``.

    ``result``   -- the locked ``ArtifactValidationResult`` NamedTuple
                    (filename presence map, computed hashes, boolean
                    sub-states, top-level ``passed``).
    ``errors``   -- tuple of ``ArtifactValidationError`` records.
    ``warnings`` -- tuple of ``ArtifactValidationWarning`` records.
    """

    result: ArtifactValidationResult
    errors: tuple
    warnings: tuple


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def compute_file_sha256(path: Path) -> tuple[str, int]:
    """Streamed SHA-256 hex digest + byte count.

    Opens ``path`` in read-binary mode only. Stage 20.4's
    read-only contract for prior-stage run dirs is enforced here.
    """

    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def check_csv_header_only(path: Path) -> tuple[bool, str]:
    """Return (is_header_only, detail).

    Header-only means ALL of:
      * file exists and is a regular file
      * file is non-empty (size > 0 bytes)
      * the first non-empty row has at least one non-empty cell
      * exactly one non-empty row total

    An entirely empty file is NOT passing. A file with the
    header row plus extra trailing newline(s) is OK (csv module
    yields one or more rows, but only one is non-empty).
    """

    if not path.exists() or not path.is_file():
        return False, f"file does not exist or is not a regular file: {path}"
    if path.stat().st_size == 0:
        return False, f"file is empty (0 bytes): {path}"

    with path.open("r", encoding="utf-8", newline="") as f:
        try:
            rows = list(csv.reader(f))
        except UnicodeDecodeError as exc:
            return False, f"file is not valid UTF-8: {path}: {exc}"
        except csv.Error as exc:
            return False, f"file is not valid CSV: {path}: {exc}"

    non_empty_rows = [
        r for r in rows
        if r and any(cell.strip() for cell in r)
    ]
    if not non_empty_rows:
        return False, f"no non-empty rows in file: {path}"
    if len(non_empty_rows) > 1:
        return (
            False,
            f"file has {len(non_empty_rows) - 1} data row(s); "
            f"expected exactly one header row and zero data rows: {path}",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Internal per-stage results
# ---------------------------------------------------------------------------


class _Stage20_2Result(NamedTuple):
    artifacts_present: dict
    artifact_hashes: tuple
    manifest_valid: bool
    safe_for_live_dispatch_false: bool
    errors: tuple
    warnings: tuple


class _Stage20_3Result(NamedTuple):
    artifacts_present: dict
    artifact_hashes: tuple
    manifest_valid: bool
    manifest_data: dict | None
    safe_for_live_dispatch_false: bool
    live_dispatch_ready_false: bool
    filter_registry_empty: bool
    filter_results_empty: bool
    errors: tuple
    warnings: tuple


class _LineageCrosscheckResult(NamedTuple):
    passed: bool
    errors: tuple


# ---------------------------------------------------------------------------
# Stage 20.2 validation
# ---------------------------------------------------------------------------


def validate_stage20_2(run_dir: Path) -> _Stage20_2Result:
    """Validate Stage 20.2 artifacts in ``run_dir``.

    Read-only access. Emits E2032 / E2034 / E2041 errors and
    W2021 warnings.
    """

    errors: list[ArtifactValidationError] = []
    warnings_out: list[ArtifactValidationWarning] = []
    artifact_hashes: list[ArtifactHash] = []
    artifacts_present: dict = {}

    # Required artifacts: existence + hash.
    for filename in STAGE20_2_REQUIRED_ARTIFACT_FILENAMES:
        path = run_dir / filename
        present = path.exists() and path.is_file()
        artifacts_present[filename] = present
        if not present:
            errors.append(ArtifactValidationError(
                code="E2034",
                detail=(
                    f"Stage 20.2 required artifact missing: {filename} "
                    f"(expected at {path})"
                ),
            ))
            continue
        sha, byts = compute_file_sha256(path)
        artifact_hashes.append(ArtifactHash(
            relative_path=filename, sha256=sha, bytes=byts,
        ))

    # Optional README -> W2021 if missing.
    for filename in STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES:
        path = run_dir / filename
        present = path.exists() and path.is_file()
        artifacts_present[filename] = present
        if not present:
            if filename == STAGE20_2_README_FILENAME:
                warnings_out.append(ArtifactValidationWarning(
                    code="W2021",
                    detail=(
                        f"Stage 20.2 README.md missing in run dir: {run_dir}"
                    ),
                ))
            continue
        sha, byts = compute_file_sha256(path)
        artifact_hashes.append(ArtifactHash(
            relative_path=filename, sha256=sha, bytes=byts,
        ))

    # Parse manifest.
    manifest_valid = False
    manifest_data: dict | None = None
    manifest_path = run_dir / STAGE20_2_MANIFEST_FILENAME
    if artifacts_present.get(STAGE20_2_MANIFEST_FILENAME):
        try:
            raw = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(ArtifactValidationError(
                code="E2032",
                detail=(
                    f"Stage 20.2 manifest is not readable as UTF-8: "
                    f"{manifest_path}: {exc}"
                ),
            ))
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(ArtifactValidationError(
                    code="E2032",
                    detail=(
                        f"Stage 20.2 manifest is not valid JSON: "
                        f"{manifest_path}: {exc.msg} "
                        f"(line {exc.lineno} col {exc.colno})"
                    ),
                ))
            else:
                if not isinstance(parsed, dict):
                    errors.append(ArtifactValidationError(
                        code="E2032",
                        detail=(
                            f"Stage 20.2 manifest root must be a JSON object; "
                            f"got {type(parsed).__name__}"
                        ),
                    ))
                else:
                    manifest_data = parsed
                    manifest_valid = True

    # Check safe_for_live_dispatch field (E2041).
    safe_for_live_dispatch_false = False
    if manifest_valid and manifest_data is not None:
        field = STAGE20_2_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH
        if field not in manifest_data:
            errors.append(ArtifactValidationError(
                code="E2041",
                detail=(
                    f"Stage 20.2 manifest is missing required field "
                    f"{field!r}"
                ),
            ))
        else:
            val = manifest_data[field]
            if val is False:
                safe_for_live_dispatch_false = True
            else:
                errors.append(ArtifactValidationError(
                    code="E2041",
                    detail=(
                        f"Stage 20.2 manifest {field}={val!r}, "
                        f"expected literal False"
                    ),
                ))

    return _Stage20_2Result(
        artifacts_present=artifacts_present,
        artifact_hashes=tuple(artifact_hashes),
        manifest_valid=manifest_valid,
        safe_for_live_dispatch_false=safe_for_live_dispatch_false,
        errors=tuple(errors),
        warnings=tuple(warnings_out),
    )


# ---------------------------------------------------------------------------
# Stage 20.3 validation
# ---------------------------------------------------------------------------


def validate_stage20_3(run_dir: Path) -> _Stage20_3Result:
    """Validate Stage 20.3 artifacts in ``run_dir``.

    Read-only access. Emits E2033 / E2035 / E2041 / E2042 / E2047 /
    E2048 errors and W2022 warnings. Returns the parsed Stage 20.3
    manifest dict (or None on parse failure) so the lineage
    crosscheck can consume it.
    """

    errors: list[ArtifactValidationError] = []
    warnings_out: list[ArtifactValidationWarning] = []
    artifact_hashes: list[ArtifactHash] = []
    artifacts_present: dict = {}

    for filename in STAGE20_3_REQUIRED_ARTIFACT_FILENAMES:
        path = run_dir / filename
        present = path.exists() and path.is_file()
        artifacts_present[filename] = present
        if not present:
            errors.append(ArtifactValidationError(
                code="E2035",
                detail=(
                    f"Stage 20.3 required artifact missing: {filename} "
                    f"(expected at {path})"
                ),
            ))
            continue
        sha, byts = compute_file_sha256(path)
        artifact_hashes.append(ArtifactHash(
            relative_path=filename, sha256=sha, bytes=byts,
        ))

    for filename in STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES:
        path = run_dir / filename
        present = path.exists() and path.is_file()
        artifacts_present[filename] = present
        if not present:
            if filename == STAGE20_3_README_FILENAME:
                warnings_out.append(ArtifactValidationWarning(
                    code="W2022",
                    detail=(
                        f"Stage 20.3 README.md missing in run dir: {run_dir}"
                    ),
                ))
            continue
        sha, byts = compute_file_sha256(path)
        artifact_hashes.append(ArtifactHash(
            relative_path=filename, sha256=sha, bytes=byts,
        ))

    # Parse manifest.
    manifest_valid = False
    manifest_data: dict | None = None
    manifest_path = run_dir / STAGE20_3_MANIFEST_FILENAME
    if artifacts_present.get(STAGE20_3_MANIFEST_FILENAME):
        try:
            raw = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(ArtifactValidationError(
                code="E2033",
                detail=(
                    f"Stage 20.3 manifest is not readable as UTF-8: "
                    f"{manifest_path}: {exc}"
                ),
            ))
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(ArtifactValidationError(
                    code="E2033",
                    detail=(
                        f"Stage 20.3 manifest is not valid JSON: "
                        f"{manifest_path}: {exc.msg} "
                        f"(line {exc.lineno} col {exc.colno})"
                    ),
                ))
            else:
                if not isinstance(parsed, dict):
                    errors.append(ArtifactValidationError(
                        code="E2033",
                        detail=(
                            f"Stage 20.3 manifest root must be a JSON object; "
                            f"got {type(parsed).__name__}"
                        ),
                    ))
                else:
                    manifest_data = parsed
                    manifest_valid = True

    # live_dispatch_ready must exist and be False (E2042).
    live_dispatch_ready_false = False
    if manifest_valid and manifest_data is not None:
        field = STAGE20_3_MANIFEST_FIELD_LIVE_DISPATCH_READY
        if field not in manifest_data:
            errors.append(ArtifactValidationError(
                code="E2042",
                detail=(
                    f"Stage 20.3 manifest is missing required field "
                    f"{field!r}"
                ),
            ))
        else:
            val = manifest_data[field]
            if val is False:
                live_dispatch_ready_false = True
            else:
                errors.append(ArtifactValidationError(
                    code="E2042",
                    detail=(
                        f"Stage 20.3 manifest {field}={val!r}, "
                        f"expected literal False"
                    ),
                ))

    # safe_for_live_dispatch: if present, must be False (E2041, same
    # code as Stage 20.2's unsafe-flag check; detail differentiates).
    # If absent, treated as vacuously OK (the locked Stage 20.3
    # manifest schema currently emits this field but the operator
    # decision is "if present").
    safe_for_live_dispatch_false = False
    if manifest_valid and manifest_data is not None:
        field = STAGE20_3_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH
        if field in manifest_data:
            val = manifest_data[field]
            if val is False:
                safe_for_live_dispatch_false = True
            else:
                errors.append(ArtifactValidationError(
                    code="E2041",
                    detail=(
                        f"Stage 20.3 manifest {field}={val!r}, "
                        f"expected literal False"
                    ),
                ))
        else:
            # Field absent. Per locked behavior, "if present, must be
            # False" -- absence is acceptable. Mark the boolean True
            # so the closure manifest does not record a missing field
            # as a violation.
            safe_for_live_dispatch_false = True

    # filter_interface_registry.csv header-only check (E2047).
    filter_registry_empty = False
    registry_filename = STAGE20_3_FILTER_INTERFACE_REGISTRY_CSV_FILENAME
    if artifacts_present.get(registry_filename):
        ok, detail = check_csv_header_only(run_dir / registry_filename)
        if ok:
            filter_registry_empty = True
        else:
            errors.append(ArtifactValidationError(
                code="E2047",
                detail=(
                    f"Stage 20.3 filter_interface_registry.csv is not "
                    f"header-only: {detail}"
                ),
            ))

    # filter_interface_results.csv header-only check (E2048).
    filter_results_empty = False
    results_filename = STAGE20_3_FILTER_INTERFACE_RESULTS_CSV_FILENAME
    if artifacts_present.get(results_filename):
        ok, detail = check_csv_header_only(run_dir / results_filename)
        if ok:
            filter_results_empty = True
        else:
            errors.append(ArtifactValidationError(
                code="E2048",
                detail=(
                    f"Stage 20.3 filter_interface_results.csv is not "
                    f"header-only: {detail}"
                ),
            ))

    return _Stage20_3Result(
        artifacts_present=artifacts_present,
        artifact_hashes=tuple(artifact_hashes),
        manifest_valid=manifest_valid,
        manifest_data=manifest_data,
        safe_for_live_dispatch_false=safe_for_live_dispatch_false,
        live_dispatch_ready_false=live_dispatch_ready_false,
        filter_registry_empty=filter_registry_empty,
        filter_results_empty=filter_results_empty,
        errors=tuple(errors),
        warnings=tuple(warnings_out),
    )


# ---------------------------------------------------------------------------
# Lineage crosscheck
# ---------------------------------------------------------------------------


def crosscheck_stage20_2_lineage(
    stage20_3_manifest_data: dict | None,
    stage20_2_run_dir: Path,
) -> _LineageCrosscheckResult:
    """Compare every Stage 20.2 artifact hash recorded inside
    ``stage20_2_lineage`` against the actual SHA-256 computed by
    Stage 20.4 for the corresponding file in ``stage20_2_run_dir``.

    Emits E2036 for any:
      * missing or malformed ``stage20_2_lineage`` block
      * missing hash field inside the lineage block
      * recorded hash that does not match the actual file hash
      * recorded hash for an artifact whose file is missing from
        ``stage20_2_run_dir`` (lineage describes a file that no
        longer exists -> closure boundary violation)
    """

    errors: list[ArtifactValidationError] = []

    if not isinstance(stage20_3_manifest_data, dict):
        # Stage 20.3 manifest was unreadable; E2033 already fired.
        # The crosscheck cannot run; treat as failed.
        return _LineageCrosscheckResult(passed=False, errors=())

    lineage = stage20_3_manifest_data.get(
        STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE,
    )
    if not isinstance(lineage, dict):
        errors.append(ArtifactValidationError(
            code="E2036",
            detail=(
                f"Stage 20.3 manifest is missing or malformed "
                f"{STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE!r} block "
                f"(got {type(lineage).__name__})"
            ),
        ))
        return _LineageCrosscheckResult(passed=False, errors=tuple(errors))

    all_matched = True
    for field_name, artifact_filename in STAGE20_2_LINEAGE_HASH_FIELDS.items():
        if field_name not in lineage:
            errors.append(ArtifactValidationError(
                code="E2036",
                detail=(
                    f"Stage 20.3 stage20_2_lineage is missing field "
                    f"{field_name!r} (expected for artifact "
                    f"{artifact_filename!r})"
                ),
            ))
            all_matched = False
            continue
        recorded_hash = lineage[field_name]

        actual_path = stage20_2_run_dir / artifact_filename
        if not actual_path.exists() or not actual_path.is_file():
            errors.append(ArtifactValidationError(
                code="E2036",
                detail=(
                    f"Stage 20.3 lineage records hash for "
                    f"{artifact_filename!r} but the actual Stage 20.2 "
                    f"file is missing at {actual_path}"
                ),
            ))
            all_matched = False
            continue

        actual_hash, _ = compute_file_sha256(actual_path)
        if actual_hash != recorded_hash:
            errors.append(ArtifactValidationError(
                code="E2036",
                detail=(
                    f"Stage 20.3 lineage hash mismatch for "
                    f"{artifact_filename!r}: "
                    f"recorded={recorded_hash!r} actual={actual_hash!r}"
                ),
            ))
            all_matched = False

    return _LineageCrosscheckResult(
        passed=all_matched,
        errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def validate_artifacts(
    stage20_2_run_dir: Path,
    stage20_3_run_dir: Path,
) -> ArtifactValidationOutcome:
    """Run the full Phase 4 artifact validation pipeline.

    Order:
      1. Validate Stage 20.2 artifacts (presence, hashes, manifest,
         safety flag).
      2. Validate Stage 20.3 artifacts (presence, hashes, manifest,
         safety flags, header-only CSVs).
      3. Cross-check Stage 20.3's ``stage20_2_lineage`` against the
         actual Stage 20.2 file hashes.
      4. Materialize the locked ``ArtifactValidationResult``
         NamedTuple and surface accumulated errors / warnings.

    ``passed`` is True iff every sub-state is verified positive
    AND the lineage crosscheck succeeds. Warnings do not affect
    ``passed``.
    """

    s2 = validate_stage20_2(stage20_2_run_dir)
    s3 = validate_stage20_3(stage20_3_run_dir)
    lineage = crosscheck_stage20_2_lineage(
        s3.manifest_data, stage20_2_run_dir,
    )

    errors = s2.errors + s3.errors + lineage.errors
    warnings_out = s2.warnings + s3.warnings

    s2_all_required_present = all(
        s2.artifacts_present.get(f, False)
        for f in STAGE20_2_REQUIRED_ARTIFACT_FILENAMES
    )
    s3_all_required_present = all(
        s3.artifacts_present.get(f, False)
        for f in STAGE20_3_REQUIRED_ARTIFACT_FILENAMES
    )

    passed = (
        s2.manifest_valid
        and s2.safe_for_live_dispatch_false
        and s2_all_required_present
        and s3.manifest_valid
        and s3.safe_for_live_dispatch_false
        and s3.live_dispatch_ready_false
        and s3_all_required_present
        and s3.filter_registry_empty
        and s3.filter_results_empty
        and lineage.passed
    )

    result = ArtifactValidationResult(
        stage20_2_manifest_valid=s2.manifest_valid,
        stage20_2_artifacts_present=dict(s2.artifacts_present),
        stage20_2_artifact_hashes=s2.artifact_hashes,
        stage20_2_safe_for_live_dispatch_false=(
            s2.safe_for_live_dispatch_false
        ),
        stage20_3_manifest_valid=s3.manifest_valid,
        stage20_3_artifacts_present=dict(s3.artifacts_present),
        stage20_3_artifact_hashes=s3.artifact_hashes,
        stage20_3_safe_for_live_dispatch_false=(
            s3.safe_for_live_dispatch_false
        ),
        stage20_3_live_dispatch_ready_false=s3.live_dispatch_ready_false,
        stage20_3_filter_registry_empty=s3.filter_registry_empty,
        stage20_3_filter_results_empty=s3.filter_results_empty,
        lineage_crosscheck_passed=lineage.passed,
        passed=passed,
    )

    return ArtifactValidationOutcome(
        result=result,
        errors=errors,
        warnings=warnings_out,
    )


__all__ = [
    "ArtifactValidationError",
    "ArtifactValidationOutcome",
    "ArtifactValidationWarning",
    "check_csv_header_only",
    "compute_file_sha256",
    "crosscheck_stage20_2_lineage",
    "validate_artifacts",
    "validate_stage20_2",
    "validate_stage20_3",
]
