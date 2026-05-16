"""Stage 20.2 manifest assembler.

Pure functions only -- no clocks, no run state. The runner
orchestrates the order in which these are called against an
on-disk run directory.

Public surface (Phase C spec):

  * ``compute_file_sha256(path)``                -- streamed
    SHA-256 hex digest (64 KiB chunks). Used for both input and
    output hash computation.

  * ``recompute_input_hashes(...)``              -- 4 required
    keys; the 5th (``stage19_summary_sha256``) is included only
    when a summary path is provided.

  * ``extract_stage18_run_id_from_stage19_manifest(path)``
    -- per operator decision B1-a. Reads
    ``STAGE19_MANIFEST_KEY_STAGE18_RUN_ID`` ("stage18_run_id")
    from Stage 19's manifest JSON. Stage 18's own manifest uses
    the un-namespaced key ``"run_id"``; Stage 20 reads via Stage
    19 because Stage 19's manifest schema is the locked record
    of the stage18_run_id Stage 19 actually consumed.

  * ``extract_stage19_run_id(path)``             -- reads
    ``STAGE19_MANIFEST_KEY_STAGE19_RUN_ID`` from Stage 19's
    manifest.

  * ``assemble_manifest(...)``                   -- builds the
    19-key manifest dict (locked count: 18 base keys + 1 added
    by operator B2-c for ``stage20_minor_version``). The
    optional ``stage19_summary_sha256`` key sits inside
    ``input_hashes`` only when summary was provided.

  * ``validate_manifest_shape(manifest)``        -- raises
    E2021 / E2024 / E2022 on shape violations. The E2022 branch
    asserts ``safe_for_live_dispatch is False`` (per the Phase C
    spec: "Asserts safe_for_live_dispatch is exactly False").

  * ``write_manifest_json(path, manifest)``      -- serializes
    with sort_keys=True, compact separators, UTF-8 no BOM,
    trailing "\\n".
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional

from PHX2.stage20.constants import (
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    CONSUMER_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    MANIFEST_REQUIRED_INPUT_HASH_KEYS,
    MANIFEST_REQUIRED_OUTPUT_HASH_KEYS,
    MAPPING_VERSION,
    PREVIEW_CANDIDATES_CSV_COLUMNS,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE19_MANIFEST_KEY_STAGE18_RUN_ID,
    STAGE19_MANIFEST_KEY_STAGE19_RUN_ID,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
    EligibilityErrorCode,
)
from PHX2.stage20.errors import Stage20ValidationError


# The locked set of artifact filenames Stage 20.2 emits per run.
# ``verify_run_determinism`` compares all five between two run
# directories byte-for-byte (E2020).
_DETERMINISTIC_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "preview_candidates.csv",
    "alert_eligibility_decisions.csv",
    "README.md",
    "stage20_run.log",
    "manifest.json",
)


_HASH_CHUNK_SIZE: int = 65536


def compute_file_sha256(path: Path) -> str:
    """Streamed SHA-256 hex digest of the file at ``path``.

    Reads in 64 KiB chunks. Matches the chunk size used by
    Stage 19 and the 20.1 verifier so hash computation stays
    byte-stable across pipeline stages.
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
# Input hash recomputation (the four required + the one optional)
# ---------------------------------------------------------------------------


def recompute_input_hashes(
    stage18_manifest_path: Path,
    stage18_review_matrix_path: Path,
    stage19_manifest_path: Path,
    stage19_ledger_path: Path,
    stage19_summary_path: Optional[Path] = None,
) -> dict[str, str]:
    """Compute the SHA-256 hex digest of every Stage 18/19 input.

    Required keys (4): stage18_manifest_sha256,
    stage18_review_matrix_sha256, stage19_manifest_sha256,
    stage19_ledger_sha256.

    Optional key (1) present iff ``stage19_summary_path`` is
    provided: stage19_summary_sha256.

    Raises:
        FileNotFoundError: if any required path does not exist.
    """

    hashes: dict[str, str] = {
        "stage18_manifest_sha256":
            compute_file_sha256(stage18_manifest_path),
        "stage18_review_matrix_sha256":
            compute_file_sha256(stage18_review_matrix_path),
        "stage19_ledger_sha256":
            compute_file_sha256(stage19_ledger_path),
        "stage19_manifest_sha256":
            compute_file_sha256(stage19_manifest_path),
    }
    if stage19_summary_path is not None:
        hashes["stage19_summary_sha256"] = compute_file_sha256(
            stage19_summary_path
        )
    return hashes


# ---------------------------------------------------------------------------
# Run-id extraction from Stage 19's manifest
# ---------------------------------------------------------------------------


def _extract_required_manifest_key(
    manifest_path: Path, key: str,
) -> str:
    raw = manifest_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"manifest at {manifest_path!s} is not a JSON object"
        )
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"manifest at {manifest_path!s} missing or empty "
            f"key {key!r}"
        )
    return value


def extract_stage18_run_id_from_stage19_manifest(
    stage19_manifest_path: Path,
) -> str:
    """Read stage18_run_id from Stage 19's manifest.

    Per operator decision B1-a: Stage 18's own manifest uses the
    un-namespaced key ``"run_id"``, while Stage 19's manifest
    records the consumed stage18 id under the namespaced key
    ``"stage18_run_id"``. Stage 20 reads from Stage 19 so the
    value is the one Stage 19 validated upstream.
    """

    return _extract_required_manifest_key(
        stage19_manifest_path, STAGE19_MANIFEST_KEY_STAGE18_RUN_ID,
    )


def extract_stage19_run_id(stage19_manifest_path: Path) -> str:
    """Read stage19_run_id from Stage 19's manifest."""

    return _extract_required_manifest_key(
        stage19_manifest_path, STAGE19_MANIFEST_KEY_STAGE19_RUN_ID,
    )


# ---------------------------------------------------------------------------
# Manifest dict assembly
# ---------------------------------------------------------------------------


def _label_mapping_for_manifest() -> dict[str, str]:
    """Snapshot LABEL_TO_STATE_MAPPING_V0 with string values.

    The locked constant's values are PreviewEligibilityState
    str-Enum members. The manifest stores the .value strings so
    a downstream consumer can parse the JSON without depending
    on Stage 20's enum.
    """

    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


def assemble_manifest(
    *,
    stage20_run_id: str,
    stage18_run_id: str,
    stage19_run_id: str,
    generated_at_utc: str,
    input_hashes: Mapping[str, str],
    output_hashes: Mapping[str, str],
    preview_state_counts: Mapping[str, int],
    preview_candidates_row_count: int,
    alert_eligibility_decisions_row_count: int,
    warnings_dict: Mapping[str, object],
) -> dict[str, object]:
    """Assemble the 19-key Stage 20.2 manifest dict.

    Key count: 18 spec-required keys + 1 from operator decision
    B2-c (``stage20_minor_version``). Optional
    ``stage19_summary_sha256`` is conditional inside
    ``input_hashes`` only (not at top level).

    The dict is returned in arbitrary key order; the serializer
    applies sort_keys=True for byte-stable output.
    """

    return {
        "alert_eligibility_decisions_csv_sha256":
            output_hashes["alert_eligibility_decisions_csv_sha256"],
        "alert_eligibility_decisions_row_count":
            alert_eligibility_decisions_row_count,
        "consumer_contract_version": CONSUMER_CONTRACT_VERSION,
        "generated_at_utc": generated_at_utc,
        "input_hashes": dict(input_hashes),
        "label_mapping": _label_mapping_for_manifest(),
        "mapping_version": MAPPING_VERSION,
        "preview_candidates_csv_sha256":
            output_hashes["preview_candidates_csv_sha256"],
        "preview_candidates_row_count":
            preview_candidates_row_count,
        "preview_state_counts": dict(preview_state_counts),
        "readme_md_sha256": output_hashes["readme_md_sha256"],
        "safe_for_live_dispatch": SAFE_FOR_LIVE_DISPATCH,
        "stage18_run_id": stage18_run_id,
        "stage19_run_id": stage19_run_id,
        "stage20_run_id": stage20_run_id,
        "stage20_run_log_sha256":
            output_hashes["stage20_run_log_sha256"],
        "stage20_version": STAGE20_VERSION,
        "stage20_minor_version": STAGE20_MINOR_VERSION,
        "warnings": dict(warnings_dict),
    }


# ---------------------------------------------------------------------------
# Manifest shape validator (E2021 / E2024 / E2022)
# ---------------------------------------------------------------------------


def validate_manifest_shape(manifest: Mapping[str, object]) -> None:
    """Validate manifest shape just before write.

    Raises:
      * Stage20ValidationError(E2021): a required key is absent
        from ``input_hashes``.
      * Stage20ValidationError(E2024): a required output hash
        key is absent from manifest top level.
      * Stage20ValidationError(E2022): ``safe_for_live_dispatch``
        is anything other than the literal Python False.

    The E2022 branch implements the locked Phase C spec line
    "Asserts safe_for_live_dispatch is exactly False" -- it is
    NOT a separate validator built for the negative test; it is
    a required behavior of this shape validator.
    """

    ih = manifest.get("input_hashes")
    if not isinstance(ih, dict):
        raise Stage20ValidationError(
            EligibilityErrorCode.E2021,
            detail="manifest missing 'input_hashes' object",
        )
    for key in MANIFEST_REQUIRED_INPUT_HASH_KEYS:
        if key not in ih:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2021,
                detail=f"input_hashes missing required key: {key!r}",
            )

    for key in MANIFEST_REQUIRED_OUTPUT_HASH_KEYS:
        if key not in manifest:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2024,
                detail=f"manifest missing required output hash: {key!r}",
            )

    # E2022 -- safe_for_live_dispatch must be the literal False.
    # ``is`` (identity) check rather than ``== False`` so that
    # ``0`` or ``""`` or other falsy-but-non-False values flag.
    if manifest.get("safe_for_live_dispatch") is not False:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2022,
            detail=(
                "manifest.safe_for_live_dispatch must be the literal "
                "Python False; got "
                f"{manifest.get('safe_for_live_dispatch')!r}"
            ),
        )


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------


def write_manifest_json(
    path: Path, manifest: Mapping[str, object],
) -> None:
    """Write the manifest JSON byte-stably.

    Serialization: ``json.dumps(manifest, sort_keys=True,
    separators=(",", ":"), ensure_ascii=False)`` followed by a
    single trailing newline. UTF-8 encoded, no BOM.
    """

    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    path.write_bytes(canonical.encode("utf-8"))


# ---------------------------------------------------------------------------
# Post-write reconciliation (E2023 row count + E2025 missing column)
# ---------------------------------------------------------------------------


def _count_csv_data_rows(path: Path) -> int:
    """Count CSV data rows (excluding header) in ``path``.

    Returns 0 for an empty file or a header-only file. A missing
    file raises FileNotFoundError -- callers that reach this
    function have already written the artifact; the missing-file
    case is unexpected and we surface it as a hard error rather
    than silently treating it as zero rows.
    """

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _read_csv_header(path: Path) -> list[str]:
    """Return the first (header) row of a CSV, or [] on empty file."""

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            return list(next(reader))
        except StopIteration:
            return []


def reconcile_output_artifacts(
    manifest: Mapping[str, object],
    run_dir: Path,
) -> None:
    """Step 21 post-write reconciliation of the locked Stage 20.2 CSVs.

    Reads ``preview_candidates.csv`` and ``alert_eligibility_decisions.csv``
    from ``run_dir`` and asserts:

      * E2023 -- the data-row count in each CSV matches the
        corresponding manifest field
        (``preview_candidates_row_count`` /
        ``alert_eligibility_decisions_row_count``).
      * E2025 -- the header in each CSV contains every locked
        required column. Extra columns are tolerated.

    Raises ``Stage20ValidationError`` on the first violation
    encountered.
    """

    preview_csv = run_dir / "preview_candidates.csv"
    decisions_csv = run_dir / "alert_eligibility_decisions.csv"

    # E2023 -- preview row count
    actual_preview = _count_csv_data_rows(preview_csv)
    expected_preview = manifest["preview_candidates_row_count"]
    if actual_preview != expected_preview:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2023,
            detail=(
                "preview_candidates_row_count mismatch: "
                f"manifest={expected_preview} actual={actual_preview}"
            ),
        )

    # E2023 -- decision row count
    actual_decisions = _count_csv_data_rows(decisions_csv)
    expected_decisions = manifest["alert_eligibility_decisions_row_count"]
    if actual_decisions != expected_decisions:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2023,
            detail=(
                "alert_eligibility_decisions_row_count mismatch: "
                f"manifest={expected_decisions} "
                f"actual={actual_decisions}"
            ),
        )

    # E2025 -- preview required columns
    preview_header = _read_csv_header(preview_csv)
    missing_preview = (
        set(PREVIEW_CANDIDATES_CSV_COLUMNS) - set(preview_header)
    )
    if missing_preview:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2025,
            detail=(
                "preview_candidates.csv missing columns: "
                f"{sorted(missing_preview)}"
            ),
        )

    # E2025 -- decisions required columns
    decisions_header = _read_csv_header(decisions_csv)
    missing_decisions = (
        set(ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS)
        - set(decisions_header)
    )
    if missing_decisions:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2025,
            detail=(
                "alert_eligibility_decisions.csv missing columns: "
                f"{sorted(missing_decisions)}"
            ),
        )


# ---------------------------------------------------------------------------
# Cross-run determinism verification (E2020)
# ---------------------------------------------------------------------------


def verify_run_determinism(
    run_dir_a: Path, run_dir_b: Path,
) -> None:
    """Byte-compare the 5 Stage 20.2 output artifacts in two run dirs.

    Production-side determinism check that backs the E2020 promise:
    given two run directories produced from the same inputs and the
    same injected clock, every output file must be byte-identical.
    Streamed SHA-256 is used so this scales to multi-megabyte
    artifacts without loading either file fully into memory.

    Args:
        run_dir_a: first run directory (any candidate run dir).
        run_dir_b: second run directory (any candidate run dir).

    Raises:
        Stage20ValidationError(E2020):
          * if any of the 5 locked artifacts is absent from either
            run directory; or
          * if the SHA-256 of any artifact differs between the two
            run directories.

    The function is symmetric: ``verify_run_determinism(a, b)`` and
    ``verify_run_determinism(b, a)`` produce identical raise/no-raise
    behavior modulo the ``detail`` text (which always identifies
    the offending filename and the two computed hashes).
    """

    for name in _DETERMINISTIC_ARTIFACT_FILENAMES:
        path_a = run_dir_a / name
        path_b = run_dir_b / name
        if not path_a.is_file():
            raise Stage20ValidationError(
                EligibilityErrorCode.E2020,
                detail=(
                    "missing artifact in run_dir_a: "
                    f"{name} (path={path_a!s})"
                ),
            )
        if not path_b.is_file():
            raise Stage20ValidationError(
                EligibilityErrorCode.E2020,
                detail=(
                    "missing artifact in run_dir_b: "
                    f"{name} (path={path_b!s})"
                ),
            )
        sha_a = compute_file_sha256(path_a)
        sha_b = compute_file_sha256(path_b)
        if sha_a != sha_b:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2020,
                detail=(
                    f"artifact byte mismatch: {name} "
                    f"sha_a={sha_a} sha_b={sha_b}"
                ),
            )


__all__ = [
    "assemble_manifest",
    "compute_file_sha256",
    "extract_stage18_run_id_from_stage19_manifest",
    "extract_stage19_run_id",
    "reconcile_output_artifacts",
    "recompute_input_hashes",
    "validate_manifest_shape",
    "verify_run_determinism",
    "write_manifest_json",
]
