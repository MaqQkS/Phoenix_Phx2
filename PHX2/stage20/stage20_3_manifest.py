"""Stage 20.3 manifest assembly + run-id derivation.

Pure functions only -- no clocks, no file I/O. The runner is
responsible for capturing generated_at_utc from the injected clock
and for serializing the returned dict to bytes via the writer
module.

Locked surfaces:
  * derive_stage20_3_run_id(stage20_run_id,
        stage20_2_manifest_json_sha256) -> 16-hex-char id.
    Content-deterministic; generated_at_utc is intentionally not
    part of the hash so two clocks against the same Stage 20.2
    inputs produce the same id.
  * assemble_stage20_3_manifest(...) -> dict. Mirrors Stage 20.2's
    byte-stable serialization contract (caller serializes with
    json.dumps(sort_keys=True, separators=(",", ":"),
    ensure_ascii=False) + "\\n").

Naming discipline (D2/D3):
  * Module filename: stage20_3_manifest.py.
  * Assemble function: assemble_stage20_3_manifest (does NOT
    collide with Stage 20.2's assemble_manifest).
  * The literal substring formed from "filter_" + "interface_" +
    "manifest" must not appear in this module's source.
"""

from __future__ import annotations

import hashlib
from typing import Any

from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    FILTER_INTERFACE_VERSION,
    FILTER_MODE_VALUES_V0,
    FILTER_REGISTRY_CONTRACT_VERSION,
    FILTER_RESULT_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    STAGE20_3_MINOR_VERSION,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
)
from PHX2.stage20.filter_interface_input import Stage20TwoInputs


STAGE20_3_MANIFEST_ARTIFACT_FILENAME: str = "stage20_3_manifest.json"
"""Filename of the on-disk Stage 20.3 manifest artifact."""

STAGE20_3_RUN_ID_PAYLOAD_VERSION_TAG: str = "20.3"
"""Fixed version tag baked into the run-id derivation payload."""

V0_NOTE: str = (
    "v0 interface is intentionally empty; zero filters registered"
    " by design."
)


def derive_stage20_3_run_id(
    stage20_run_id: str,
    stage20_2_manifest_json_sha256: str,
) -> str:
    """Content-deterministic 16-hex-char Stage 20.3 run id.

    Payload (joined with "\\n"):
        stage20_run_id
        "20.3"
        FILTER_INTERFACE_VERSION
        FILTER_REGISTRY_CONTRACT_VERSION
        FILTER_RESULT_CONTRACT_VERSION
        stage20_2_manifest_json_sha256

    Returns hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].
    generated_at_utc is intentionally absent from the payload so
    two clocks against the same Stage 20.2 inputs produce the same
    Stage 20.3 run id.
    """

    payload = "\n".join([
        stage20_run_id,
        STAGE20_3_RUN_ID_PAYLOAD_VERSION_TAG,
        FILTER_INTERFACE_VERSION,
        FILTER_REGISTRY_CONTRACT_VERSION,
        FILTER_RESULT_CONTRACT_VERSION,
        stage20_2_manifest_json_sha256,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _label_mapping_for_lineage() -> dict[str, str]:
    """Snapshot LABEL_TO_STATE_MAPPING_V0 with string values."""

    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


def assemble_stage20_3_manifest(
    inputs: Stage20TwoInputs,
    stage20_3_run_id: str,
    generated_at_utc: str,
    filter_interface_registry_csv_sha256: str,
    filter_interface_results_csv_sha256: str,
    stage20_3_run_log_sha256: str,
    readme_md_sha256: str,
) -> dict[str, Any]:
    """Build the Stage 20.3 manifest dict.

    Pure function. Caller serializes the returned dict with
    json.dumps(sort_keys=True, separators=(",", ":"),
    ensure_ascii=False) + "\\n" for byte-stable output.

    Every literal-False / zero / explicit-bool field is a hardcoded
    Python value -- nothing flows from the Stage 20.2 inputs that
    could promote the run to anything other than the empty v0
    interface state.
    """

    lineage = {
        "stage20_run_id": inputs.stage20_run_id,
        "stage20_minor_version": STAGE20_MINOR_VERSION,
        "stage20_version": STAGE20_VERSION,
        "consumer_contract_version": CONSUMER_CONTRACT_VERSION,
        "manifest_json_sha256": inputs.manifest_json_sha256,
        "preview_candidates_csv_sha256":
            inputs.preview_candidates_csv_sha256,
        "alert_eligibility_decisions_csv_sha256":
            inputs.alert_eligibility_decisions_csv_sha256,
        "readme_md_sha256": inputs.readme_md_sha256,
        "stage20_run_log_sha256": inputs.stage20_run_log_sha256,
        "safe_for_live_dispatch": False,
        "label_mapping": _label_mapping_for_lineage(),
    }

    return {
        # Identity
        "stage20_version": STAGE20_VERSION,
        "stage20_3_minor_version": STAGE20_3_MINOR_VERSION,
        "stage20_3_run_id": stage20_3_run_id,
        "generated_at_utc": generated_at_utc,

        # Filter interface schema versions
        "filter_interface_version": FILTER_INTERFACE_VERSION,
        "filter_registry_contract_version": FILTER_REGISTRY_CONTRACT_VERSION,
        "filter_result_contract_version": FILTER_RESULT_CONTRACT_VERSION,
        "filter_mode_enum_v0": sorted(list(FILTER_MODE_VALUES_V0)),

        # Explicit zero / false anti-confusion fields
        "interface_initialized": True,
        "registered_filter_count": 0,
        "evaluated_filter_count": 0,
        "candidate_mutation_count": 0,
        "blocking_filter_count": 0,
        "enforcement_enabled": False,
        "v0_interface_intentionally_empty": True,
        "safe_for_live_dispatch": False,
        "live_dispatch_ready": False,

        # Stage 20.2 lineage (nested)
        "stage20_2_lineage": lineage,

        # Stage 20.3 artifact filename + self-hashes
        "stage20_3_manifest_artifact_filename":
            STAGE20_3_MANIFEST_ARTIFACT_FILENAME,
        "filter_interface_registry_csv_sha256":
            filter_interface_registry_csv_sha256,
        "filter_interface_results_csv_sha256":
            filter_interface_results_csv_sha256,
        "stage20_3_run_log_sha256": stage20_3_run_log_sha256,
        "readme_md_sha256": readme_md_sha256,

        # Diagnostics
        "errors": [],
        "warnings": [],
        "notes": [V0_NOTE],
    }


__all__ = [
    "STAGE20_3_MANIFEST_ARTIFACT_FILENAME",
    "STAGE20_3_RUN_ID_PAYLOAD_VERSION_TAG",
    "V0_NOTE",
    "assemble_stage20_3_manifest",
    "derive_stage20_3_run_id",
]
