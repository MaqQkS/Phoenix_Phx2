"""Stage 18 manifest assembly + atomic write + run_id derivation.

The manifest is the only run-level summary written by Stage 18
that captures enough state to reproduce the run later: it pins
the upstream Stage 17 manifest verbatim, the gate threshold set,
input and output row counts, classification counts, and the git
commit.

Determinism contract: two runs against the same Stage 17 output
directory produce identical Stage 18 manifests AFTER zeroing the
run-specific fields:

  * ``run_id``
  * ``run_started_utc``
  * ``run_finished_utc``
  * ``stage17_input_dir``
  * ``output_dir``

``run_id`` is in this list for symmetry with Stage 17's pattern;
by construction it IS deterministic from the canonical input set
when both runs see the same Stage 17 output, so the
byte-comparison still works whether you zero it or not.

run_id derivation (locked):

    sha256(canonical_json({
        "stage17_run_id":         <from upstream manifest>,
        "stage17_input_basename": <basename of input dir>,
        "stage18_version":        STAGE18_VERSION,
        "gates":                  <five constants verbatim>,
        "input_row_counts":       <four CSV files -> row count>,
        "policy_hash_filter":     <sorted, deduplicated list of
                                   --policy-hash values; empty
                                   list when no filter is active>
    }))[:16]

``policy_hash_filter`` participates in the canonical input set so
two runs against the same Stage 17 directory with different
``--policy-hash`` arguments produce distinct run ids (the emitted
artifact scope differs). The list is sorted and deduplicated, so
``--policy-hash A --policy-hash B`` and
``--policy-hash B --policy-hash A`` yield the same id.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from PHX2.stage18.constants import (
    MANIFEST_SCHEMA_VERSION,
    MAX_INCOMPLETE_OUTCOME_RATIO,
    MAX_UNEVALUABLE_RATE,
    MIN_EVALUABLE_COUNT,
    MIN_RULE_NEGATIVE_COUNT,
    MIN_RULE_POSITIVE_COUNT,
    STAGE18_VERSION,
)
from PHX2.stage18.errors import Stage18Error


# Five-element gate snapshot embedded in the manifest and used as
# part of the run_id input set. Defined here as a module-level
# constant so the run_id derivation and the manifest body see the
# same dict (no drift between the two).
GATES_SNAPSHOT: Mapping[str, Any] = {
    "min_evaluable_count": MIN_EVALUABLE_COUNT,
    "min_rule_positive_count": MIN_RULE_POSITIVE_COUNT,
    "min_rule_negative_count": MIN_RULE_NEGATIVE_COUNT,
    "max_unevaluable_rate": MAX_UNEVALUABLE_RATE,
    "max_incomplete_outcome_ratio": MAX_INCOMPLETE_OUTCOME_RATIO,
}


def compute_run_id(
    *,
    stage17_run_id: str,
    stage17_input_basename: str,
    input_row_counts: Mapping[str, int],
    policy_hash_filter: Sequence[str] = (),
) -> str:
    """Derive the 16-hex-char Stage 18 run id from the canonical
    input set. Pure function of its arguments.

    ``policy_hash_filter`` is sorted and deduplicated before
    being folded into the canonical JSON, so call-order does not
    affect the derived id. An unfiltered run passes an empty
    sequence (the default).
    """

    canonical = json.dumps(
        {
            "stage17_run_id": stage17_run_id,
            "stage17_input_basename": stage17_input_basename,
            "stage18_version": STAGE18_VERSION,
            "gates": dict(GATES_SNAPSHOT),
            "input_row_counts": dict(input_row_counts),
            "policy_hash_filter": sorted(set(policy_hash_filter)),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def build_manifest(
    *,
    run_id: str,
    run_started_utc: str,
    run_finished_utc: str,
    stage17_input_dir: str,
    output_dir: str,
    stage17_manifest: Mapping[str, Any],
    input_row_counts: Mapping[str, int],
    output_row_counts: Mapping[str, int],
    classification_counts: Mapping[str, int],
    git_commit: str,
    policy_hash_filter: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble the Stage 18 manifest dict (does not write it).

    ``policy_hash_filter`` is sorted and deduplicated before
    being embedded, mirroring the convention used by
    ``compute_run_id``. The field is always present in the
    manifest: an unfiltered run records an empty list, a filtered
    run records the sorted set of filter values.
    """

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "stage18_version": STAGE18_VERSION,
        "run_id": run_id,
        "run_started_utc": run_started_utc,
        "run_finished_utc": run_finished_utc,
        "stage17_input_dir": stage17_input_dir,
        "output_dir": output_dir,
        "gates": dict(GATES_SNAPSHOT),
        "stage17_manifest": dict(stage17_manifest),
        "input_row_counts": dict(input_row_counts),
        "output_row_counts": dict(output_row_counts),
        "classification_counts": dict(classification_counts),
        "policy_hash_filter": sorted(set(policy_hash_filter)),
        "git_commit": git_commit,
    }


def write_manifest(manifest: Mapping[str, Any], output_path: Path) -> None:
    """Atomically write the Stage 18 manifest JSON.

    Serialization: ``sort_keys=True``, compact separators, UTF-8
    without ASCII escaping -- so the byte sequence is independent
    of dict insertion order. The atomic-write pattern mirrors the
    CSV / log writers (``.tmp`` sibling + ``os.replace``).
    """

    payload = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    tmp = output_path.with_name(output_path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8", newline="")
        os.replace(tmp, output_path)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise Stage18Error("B06", f"{output_path.name}: {exc}") from exc


__all__ = [
    "GATES_SNAPSHOT",
    "build_manifest",
    "compute_run_id",
    "write_manifest",
]
