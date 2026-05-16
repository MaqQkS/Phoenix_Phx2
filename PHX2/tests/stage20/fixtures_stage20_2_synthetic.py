"""Synthetic Stage 20.2 run-directory builder (TEST-ONLY).

Used by Stage 20.3 Phases 2-6 tests to fabricate Stage 20.2-shaped
run directories in ``tmp_path``. The fixture must NOT import any
Stage 20.2-internal module (input_validators, builder,
artifact_writers, manifest_assembler, runner): the bytes are
written directly so the test surface stays independent of any
20.2 helper that we are not allowed to depend on from 20.3.

Layout produced under ``tmp_path``:

    <tmp_path>/stage20_runs/<synthetic_stage20_run_id>/
      manifest.json
      preview_candidates.csv
      alert_eligibility_decisions.csv
      README.md
      stage20_run.log

The manifest mirrors the 19 top-level keys produced by the real
Stage 20.2 ``assemble_manifest`` so that 20.3's input validator
treats the fixture as a valid 20.2 run. Override knobs allow
controlled corruption for negative tests (omit keys, mutate
values, scramble file hashes, etc.).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Optional

from PHX2.stage20.constants import (
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    CONSUMER_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PREVIEW_CANDIDATES_CSV_COLUMNS,
    PREVIEW_STATE_COUNT_KEYS,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
)


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------


_NO_OVERRIDE = object()
"""Default sentinel for safe_for_live_dispatch_override: do not override."""

OMIT_SAFE_FOR_LIVE_DISPATCH = object()
"""Pass as safe_for_live_dispatch_override to drop the key entirely."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _serialize_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Mirror the locked 20.2 manifest serialization.

    sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    trailing "\\n", UTF-8 no BOM.
    """

    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
    return canonical.encode("utf-8")


def _label_mapping_for_manifest() -> dict[str, str]:
    """Snapshot LABEL_TO_STATE_MAPPING_V0 with string values.

    The locked constant's values are PreviewEligibilityState
    str-Enum members. The manifest stores the .value strings so a
    downstream JSON consumer never has to depend on Stage 20's enum
    class.
    """

    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


def _write_csv_with_header(
    path: Path,
    columns: tuple[str, ...],
    row_count: int,
    row_prefix: str,
) -> bytes:
    """Write a header-plus-synthetic-rows CSV and return the bytes."""

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(list(columns))
    for i in range(row_count):
        cells = [f"{row_prefix}_{col}_{i:06d}" for col in columns]
        writer.writerow(cells)
    data = buf.getvalue().encode("utf-8")
    path.write_bytes(data)
    return data


def _write_readme(path: Path) -> bytes:
    text = (
        "PHX2 Stage 20.2 — synthetic test fixture run\n"
        "\n"
        "safe_for_live_dispatch: false. Synthetic fixture only; not a real run.\n"
        "\n"
        "Stage 20 boundary: Stage 21 owns live dispatch checks.\n"
    )
    data = text.encode("utf-8")
    path.write_bytes(data)
    return data


def _write_run_log(path: Path, stage20_run_id: str) -> bytes:
    """Write a synthetic JSON Lines log mirroring 20.2's format."""

    events = [
        {
            "event": "run_started",
            "ts_utc": "2026-05-15T00:00:00Z",
            "stage20_run_id": stage20_run_id,
            "detail": {},
        },
        {
            "event": "run_completed",
            "ts_utc": "2026-05-15T00:00:00Z",
            "stage20_run_id": stage20_run_id,
            "detail": {},
        },
    ]
    rendered = [
        json.dumps(
            ev,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for ev in events
    ]
    text = "\n".join(rendered) + "\n"
    data = text.encode("utf-8")
    path.write_bytes(data)
    return data


def _derive_synthetic_stage20_run_id(*parts: object) -> str:
    """Stable 16-hex-char id over the fixture parameters."""

    payload = "synthetic_stage20_2|" + "|".join(repr(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def build_synthetic_stage20_2_run(
    tmp_path: Path,
    *,
    candidate_count: int = 3,
    label_mapping_override: Optional[dict[str, str]] = None,
    safe_for_live_dispatch_override: Any = _NO_OVERRIDE,
    stage20_minor_version_override: Optional[str] = None,
    stage20_version_override: Optional[str] = None,
    consumer_contract_version_override: Optional[str] = None,
    omit_keys: tuple[str, ...] = (),
    malformed_json: bool = False,
    missing_file: Optional[str] = None,
    corrupt_file_hash: Optional[str] = None,
) -> Path:
    """Build a synthetic Stage 20.2 run directory.

    Returns the run directory path (a subdirectory of tmp_path).

    Override semantics:
      * label_mapping_override: replace the locked v0 mapping in the
        manifest's label_mapping key. None leaves the locked mapping
        intact.
      * safe_for_live_dispatch_override: bypass the locked False. Pass
        True / None / "false" to install a non-False value. Pass
        OMIT_SAFE_FOR_LIVE_DISPATCH to drop the key entirely.
      * stage20_minor_version_override / stage20_version_override /
        consumer_contract_version_override: replace those manifest
        scalars.
      * omit_keys: top-level manifest keys to remove before write.
      * malformed_json: truncate manifest bytes in the middle of a
        key so the validator's json.loads fails.
      * missing_file: name of a sibling file to skip writing.
      * corrupt_file_hash: name of a sibling file whose published
        sha256 the manifest publishes WRONG (the on-disk bytes are
        unchanged; the manifest just lies about them).
    """

    synth_run_id = _derive_synthetic_stage20_run_id(
        candidate_count,
        label_mapping_override,
        # The sentinel default and the OMIT sentinel both round-trip
        # through repr to a stable string per Python session.
        id(safe_for_live_dispatch_override)
        if safe_for_live_dispatch_override
        in (_NO_OVERRIDE, OMIT_SAFE_FOR_LIVE_DISPATCH)
        else safe_for_live_dispatch_override,
        stage20_minor_version_override,
        stage20_version_override,
        consumer_contract_version_override,
        omit_keys,
        malformed_json,
        missing_file,
        corrupt_file_hash,
    )

    run_dir = tmp_path / "stage20_runs" / synth_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    # 1) Write the 4 non-manifest sibling files (unless one is to
    # be omitted), then compute their byte sha256.
    sibling_bytes: dict[str, bytes] = {}

    if missing_file != "preview_candidates.csv":
        sibling_bytes["preview_candidates.csv"] = _write_csv_with_header(
            run_dir / "preview_candidates.csv",
            PREVIEW_CANDIDATES_CSV_COLUMNS,
            candidate_count,
            row_prefix="pc",
        )
    if missing_file != "alert_eligibility_decisions.csv":
        # 4 decision rows per candidate (the 4-step chain in 20.2).
        sibling_bytes["alert_eligibility_decisions.csv"] = (
            _write_csv_with_header(
                run_dir / "alert_eligibility_decisions.csv",
                ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
                candidate_count * 4,
                row_prefix="dec",
            )
        )
    if missing_file != "README.md":
        sibling_bytes["README.md"] = _write_readme(run_dir / "README.md")
    if missing_file != "stage20_run.log":
        sibling_bytes["stage20_run.log"] = _write_run_log(
            run_dir / "stage20_run.log", synth_run_id,
        )

    def _hash_or_corrupt(name: str) -> str:
        true_hash = (
            _sha256_bytes(sibling_bytes[name])
            if name in sibling_bytes
            else "0" * 64
        )
        if corrupt_file_hash == name:
            return "0" * 64
        return true_hash

    # 2) Build the manifest dict (mirror 20.2 assemble_manifest shape).
    preview_state_counts = {k: 0 for k in PREVIEW_STATE_COUNT_KEYS}
    # Distribute the synthetic candidates across the 4 states.
    for i in range(candidate_count):
        bucket = PREVIEW_STATE_COUNT_KEYS[i % len(PREVIEW_STATE_COUNT_KEYS)]
        preview_state_counts[bucket] += 1

    input_hashes = {
        "stage18_manifest_sha256": "1" * 64,
        "stage18_review_matrix_sha256": "2" * 64,
        "stage19_ledger_sha256": "3" * 64,
        "stage19_manifest_sha256": "4" * 64,
    }

    warnings_dict = {
        "W2001_run_median_staleness_exceeded": False,
        "W2002_preview_eligible_count_zero": False,
        "W2003_tier_hint_missing_count": 0,
        "W2004_multiple_operators_per_review_slice_count": 0,
        "W2005_stage18_evidence_missing_for_review_count": 0,
        "W2006_candidate_review_stale_count": 0,
        "W2007_eligibility_mapping_drift_detected": False,
    }

    label_mapping = (
        dict(label_mapping_override)
        if label_mapping_override is not None
        else _label_mapping_for_manifest()
    )

    manifest: dict[str, Any] = {
        "alert_eligibility_decisions_csv_sha256":
            _hash_or_corrupt("alert_eligibility_decisions.csv"),
        "alert_eligibility_decisions_row_count": candidate_count * 4,
        "consumer_contract_version": (
            consumer_contract_version_override
            if consumer_contract_version_override is not None
            else CONSUMER_CONTRACT_VERSION
        ),
        "generated_at_utc": "2026-05-15T00:00:00Z",
        "input_hashes": input_hashes,
        "label_mapping": label_mapping,
        "mapping_version": MAPPING_VERSION,
        "preview_candidates_csv_sha256":
            _hash_or_corrupt("preview_candidates.csv"),
        "preview_candidates_row_count": candidate_count,
        "preview_state_counts": preview_state_counts,
        "readme_md_sha256": _hash_or_corrupt("README.md"),
        "stage18_run_id": "stage18_synth_" + synth_run_id[:8],
        "stage19_run_id": "stage19_synth_" + synth_run_id[:8],
        "stage20_run_id": synth_run_id,
        "stage20_run_log_sha256": _hash_or_corrupt("stage20_run.log"),
        "stage20_version": (
            stage20_version_override
            if stage20_version_override is not None
            else STAGE20_VERSION
        ),
        "stage20_minor_version": (
            stage20_minor_version_override
            if stage20_minor_version_override is not None
            else STAGE20_MINOR_VERSION
        ),
        "warnings": warnings_dict,
    }

    # safe_for_live_dispatch override semantics
    if safe_for_live_dispatch_override is _NO_OVERRIDE:
        manifest["safe_for_live_dispatch"] = False
    elif safe_for_live_dispatch_override is OMIT_SAFE_FOR_LIVE_DISPATCH:
        # Drop the key entirely; the validator should reject for
        # missing required key.
        pass
    else:
        manifest["safe_for_live_dispatch"] = safe_for_live_dispatch_override

    # Apply any additional key omissions.
    for k in omit_keys:
        manifest.pop(k, None)

    # 3) Serialize manifest bytes (mirror 20.2 byte format).
    if missing_file != "manifest.json":
        manifest_bytes = _serialize_manifest_bytes(manifest)
        if malformed_json:
            # Truncate mid-key. Drop the last 5 bytes so json.loads fails.
            manifest_bytes = manifest_bytes[: max(0, len(manifest_bytes) - 5)]
        (run_dir / "manifest.json").write_bytes(manifest_bytes)

    return run_dir
