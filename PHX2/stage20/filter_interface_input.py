"""Stage 20.3 on-disk Stage 20.2 input validator.

Reads a Stage 20.2 run directory off disk, re-validates the
manifest shape and the published sibling-file SHA-256 hashes, and
returns an immutable Stage20TwoInputs NamedTuple that the rest of
Stage 20.3 consumes.

Every failure raises Stage20ValidationError(E2027) with a
distinguishing detail substring that the negative tests pin.

INFO-1 boundary discipline: this module inlines its own private
streaming sha256 helper rather than importing
compute_file_sha256 from PHX2.stage20.manifest_assembler. The
artifact-writer module ships a separate inlined copy for its own
use; the duplication is intentional and aligns with the
20.2-internal-import ban for Stage 20.3 production code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, NamedTuple

from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
    EligibilityErrorCode,
)
from PHX2.stage20.errors import Stage20ValidationError


# ---------------------------------------------------------------------------
# Locked Stage 20.2 input contract pins
# ---------------------------------------------------------------------------


STAGE20_2_REQUIRED_SIBLING_FILES: tuple[str, ...] = (
    "manifest.json",
    "preview_candidates.csv",
    "alert_eligibility_decisions.csv",
    "README.md",
    "stage20_run.log",
)

STAGE20_2_REQUIRED_MANIFEST_KEYS: frozenset[str] = frozenset({
    "alert_eligibility_decisions_csv_sha256",
    "alert_eligibility_decisions_row_count",
    "consumer_contract_version",
    "generated_at_utc",
    "input_hashes",
    "label_mapping",
    "mapping_version",
    "preview_candidates_csv_sha256",
    "preview_candidates_row_count",
    "preview_state_counts",
    "readme_md_sha256",
    "safe_for_live_dispatch",
    "stage18_run_id",
    "stage19_run_id",
    "stage20_run_id",
    "stage20_run_log_sha256",
    "stage20_version",
    "stage20_minor_version",
    "warnings",
})

# Maps the on-disk sibling filename to the manifest key that holds
# its expected SHA-256. Stage 20.3 recomputes the on-disk hash and
# cross-checks against this key.
_SIBLING_FILE_TO_MANIFEST_HASH_KEY: dict[str, str] = {
    "preview_candidates.csv": "preview_candidates_csv_sha256",
    "alert_eligibility_decisions.csv":
        "alert_eligibility_decisions_csv_sha256",
    "README.md": "readme_md_sha256",
    "stage20_run.log": "stage20_run_log_sha256",
}


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


class Stage20TwoInputs(NamedTuple):
    """Locked return shape of load_and_validate_stage20_2_run."""

    stage20_2_run_dir: Path
    stage20_run_id: str
    manifest: dict
    manifest_json_sha256: str
    preview_candidates_csv_sha256: str
    alert_eligibility_decisions_csv_sha256: str
    readme_md_sha256: str
    stage20_run_log_sha256: str
    label_mapping: dict


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_file_sha256_streaming(path: Path) -> str:
    """Streamed SHA-256 hex digest (64 KiB chunks; lowercase hex).

    INFO-1: this is a Stage 20.3-local copy of the hashing helper.
    Stage 20.3 must not import compute_file_sha256 from
    PHX2.stage20.manifest_assembler; an inlined duplicate keeps the
    20.3 boundary clean.
    """

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _raise_e2027(detail: str) -> None:
    raise Stage20ValidationError(EligibilityErrorCode.E2027, detail=detail)


def _validate_label_mapping(actual: Any) -> dict[str, str]:
    """Assert the manifest label_mapping equals the locked v0 mapping."""

    locked = {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}
    if not isinstance(actual, dict):
        _raise_e2027(
            "manifest.label_mapping is not a JSON object"
        )
    if actual.keys() != locked.keys():
        _raise_e2027(
            "manifest.label_mapping does not match locked v0 mapping: "
            f"key set differs (expected={sorted(locked.keys())} "
            f"actual={sorted(actual.keys())})"
        )
    for key, expected_value in locked.items():
        if actual[key] != expected_value:
            _raise_e2027(
                "manifest.label_mapping does not match locked v0 mapping: "
                f"key {key!r} value differs "
                f"(expected={expected_value!r} actual={actual[key]!r})"
            )
    return dict(actual)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def load_and_validate_stage20_2_run(
    stage20_2_run_dir: Path,
) -> Stage20TwoInputs:
    """Read and validate a Stage 20.2 on-disk run directory.

    Every failure raises Stage20ValidationError(E2027) with a
    distinguishing detail substring.

    Steps:
      1. stage20_2_run_dir exists and is a directory.
      2. All 5 required sibling files exist (regular files).
      3. manifest.json parses as JSON.
      4. Manifest carries all 19 required top-level keys.
      5. manifest.stage20_version == "stage20_v0_observe_only".
      6. manifest.stage20_minor_version == "20.2".
      7. manifest.consumer_contract_version == "stage20_to_stage21_v0".
      8. manifest.safe_for_live_dispatch is the Python literal False.
      9. manifest.label_mapping equals the locked v0 mapping.
      10. Recompute on-disk SHA-256 for the 4 non-manifest siblings;
          each must match the manifest's published hash.
      11. Compute manifest_json_sha256 from the bytes as read.
    """

    # 1) Run dir checks
    if not stage20_2_run_dir.exists():
        _raise_e2027(
            f"stage20_2_run_dir does not exist: {stage20_2_run_dir!s}"
        )
    if not stage20_2_run_dir.is_dir():
        _raise_e2027(
            f"stage20_2_run_dir is not a directory: {stage20_2_run_dir!s}"
        )

    # 2) Sibling file existence (files, not directories)
    for filename in STAGE20_2_REQUIRED_SIBLING_FILES:
        p = stage20_2_run_dir / filename
        if not p.is_file():
            _raise_e2027(
                f"required sibling file missing: {filename}"
            )

    # 3) Parse manifest.json
    manifest_path = stage20_2_run_dir / "manifest.json"
    raw_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _raise_e2027(
            f"manifest.json is not valid JSON: {exc}"
        )
    if not isinstance(manifest, dict):
        _raise_e2027(
            "manifest.json must be a JSON object at the top level"
        )

    # 4) Required key set
    missing_keys = STAGE20_2_REQUIRED_MANIFEST_KEYS - set(manifest.keys())
    if missing_keys:
        # Report the alphabetically-first missing key so the detail
        # is deterministic across runs; include the full set for
        # debuggability.
        first_missing = sorted(missing_keys)[0]
        _raise_e2027(
            "manifest missing required key: "
            f"{first_missing!r} (full missing set={sorted(missing_keys)})"
        )

    # 5/6/7) Version pins
    if manifest["stage20_version"] != STAGE20_VERSION:
        _raise_e2027(
            "manifest.stage20_version mismatch: "
            f"expected={STAGE20_VERSION!r} "
            f"actual={manifest['stage20_version']!r}"
        )
    if manifest["stage20_minor_version"] != STAGE20_MINOR_VERSION:
        _raise_e2027(
            "manifest.stage20_minor_version mismatch: "
            f"expected={STAGE20_MINOR_VERSION!r} "
            f"actual={manifest['stage20_minor_version']!r}"
        )
    if manifest["consumer_contract_version"] != CONSUMER_CONTRACT_VERSION:
        _raise_e2027(
            "manifest.consumer_contract_version mismatch: "
            f"expected={CONSUMER_CONTRACT_VERSION!r} "
            f"actual={manifest['consumer_contract_version']!r}"
        )

    # 8) safe_for_live_dispatch must be the Python literal False.
    if manifest["safe_for_live_dispatch"] is not False:
        _raise_e2027(
            "manifest.safe_for_live_dispatch must be the literal "
            f"False; got {manifest['safe_for_live_dispatch']!r}"
        )

    # 9) Label mapping matches the locked v0 mapping.
    label_mapping = _validate_label_mapping(manifest["label_mapping"])

    # 10) Recompute sibling hashes and compare to manifest claims.
    sibling_hashes: dict[str, str] = {}
    for filename, manifest_key in _SIBLING_FILE_TO_MANIFEST_HASH_KEY.items():
        on_disk = _compute_file_sha256_streaming(
            stage20_2_run_dir / filename
        )
        published = manifest[manifest_key]
        if on_disk != published:
            _raise_e2027(
                f"sibling file {filename} on-disk sha256 mismatch: "
                f"manifest={published!r} on_disk={on_disk!r}"
            )
        sibling_hashes[filename] = on_disk

    # 11) Manifest's own sha256 (from bytes as read).
    manifest_json_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    return Stage20TwoInputs(
        stage20_2_run_dir=stage20_2_run_dir,
        stage20_run_id=manifest["stage20_run_id"],
        manifest=manifest,
        manifest_json_sha256=manifest_json_sha256,
        preview_candidates_csv_sha256=sibling_hashes[
            "preview_candidates.csv"
        ],
        alert_eligibility_decisions_csv_sha256=sibling_hashes[
            "alert_eligibility_decisions.csv"
        ],
        readme_md_sha256=sibling_hashes["README.md"],
        stage20_run_log_sha256=sibling_hashes["stage20_run.log"],
        label_mapping=label_mapping,
    )


__all__ = [
    "STAGE20_2_REQUIRED_MANIFEST_KEYS",
    "STAGE20_2_REQUIRED_SIBLING_FILES",
    "Stage20TwoInputs",
    "_compute_file_sha256_streaming",
    "load_and_validate_stage20_2_run",
]
