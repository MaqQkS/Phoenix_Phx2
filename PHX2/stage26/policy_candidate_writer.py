"""Stage 26.5 deterministic observe-only policy candidate writer.

The writer emits Stage 26.5 observe-only policy candidate artifacts
into a caller-supplied output directory and returns an immutable
``Stage26PolicyCandidateArtifactSet`` recording each on-disk
artifact's basename, sha256, byte_count, and row_count.

Output artifacts (locked, observe-only basenames):

  * ``stage26_policy_candidates.jsonl``      -- one canonical JSON
                                                row per
                                                ``Stage26PolicyCandidate``,
                                                ordered deterministically.
  * ``stage26_policy_candidate_summary.json`` -- the per-build
                                                 ``Stage26PolicyCandidateSummary``
                                                 serialized as
                                                 canonical JSON.
  * ``stage26_policy_candidate_manifest.json`` -- a Stage 26.5
                                                  manifest body
                                                  carrying every
                                                  artifact's
                                                  basename / sha256
                                                  / byte_count /
                                                  row_count plus
                                                  the manifest's own
                                                  self-entry sentinel
                                                  record.

Determinism / safety rules (Stage 26.5 invariants):

  * Output directory MUST exist before the writer runs; the writer
    never creates arbitrary parent directories.
  * Every JSONL row is canonical JSON (sorted keys, no whitespace,
    ASCII-safe). Identical input
    ``Stage26PolicyCandidateBuildResult`` produces byte-identical
    artifacts.
  * Non-empty JSONL files end with a single trailing ``"\\n"``; an
    empty JSONL file is zero bytes (no trailing newline).
  * Summary + manifest JSON files are canonical JSON without a
    trailing newline.
  * Before writing any artifact the writer runs a redaction sweep
    over every row's / summary's / manifest's canonical text. The
    sweep refuses forbidden URL / webhook host / secret-shaped
    fragments and approval / runtime leak markers; any failure
    raises ``Stage26PolicyCandidateError`` and leaves the output
    directory untouched.
  * The writer refuses to emit any artifact under a runtime-policy
    basename; the only locked basenames are the three observe-only
    artifact basenames declared in
    ``PHX2.stage26.policy_candidate_constants``.
  * The writer NEVER writes outside the caller-supplied output
    directory.
  * The writer NEVER reads ``os.environ`` / ``os.getenv``, opens a
    network / DB / messaging connection, defines a CLI surface, or
    invokes a Stage 21 / 22 / 23 / 24 production module.

This module imports only stdlib (``hashlib`` / ``json`` /
``pathlib``) plus the Stage 26.5 constants / errors / models
surfaces. It does NOT import any Stage 25 module (Stage 26.5
vocabulary mirrors the Stage 25 self-entry sentinel convention
locally) and does NOT import Stage 26.1 / 26.2 / 26.3 / 26.4
production modules beyond the threshold + policy candidate model
surfaces it consumes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PHX2.stage26.errors import Stage26PolicyCandidateError
from PHX2.stage26.policy_candidate_constants import (
    POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST,
    POLICY_CANDIDATE_ARTIFACT_KIND_ROWS,
    POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY,
    STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES,
    STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS,
    STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS,
    STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
    STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE,
    STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN,
    STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
    STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256,
    STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
    STAGE26_POLICY_CANDIDATE_VERSION,
    STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID,
    STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID,
    STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED,
    STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK,
)
from PHX2.stage26.policy_candidate_models import (
    Stage26PolicyCandidate,
    Stage26PolicyCandidateArtifactReference,
    Stage26PolicyCandidateArtifactSet,
    Stage26PolicyCandidateBuildResult,
    Stage26PolicyCandidateSummary,
)


# ---------------------------------------------------------------------------
# Canonical JSON helpers
# ---------------------------------------------------------------------------


def _canonical_json_text(obj: object) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _canonical_json_bytes(obj: object) -> bytes:
    return _canonical_json_text(obj).encode("utf-8")


def _canonical_jsonl_bytes(rows: tuple[dict, ...]) -> bytes:
    if rows == ():
        return b""
    pieces = [_canonical_json_text(row) for row in rows]
    return ("\n".join(pieces) + "\n").encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _count_non_blank_lines(data: bytes) -> int:
    if data == b"":
        return 0
    return sum(
        1
        for line in data.decode("utf-8").split("\n")
        if line.strip() != ""
    )


# ---------------------------------------------------------------------------
# Row / summary serializers
# ---------------------------------------------------------------------------


def _policy_candidate_to_row(
    candidate: Stage26PolicyCandidate,
) -> dict:
    """Serialize a ``Stage26PolicyCandidate`` into a canonical JSONL row.

    Field ordering is alphabetical (canonical JSON sorts keys
    anyway, so the row dict's iteration order is purely
    documentation). Tuples are emitted as JSON arrays. Floats are
    emitted as numbers; the upstream Stage 26.4 rates are already
    deterministic safe-zero-denominator floats so no extra rounding
    or coercion happens here.
    """
    return {
        "ambiguous_rate": candidate.ambiguous_rate,
        "candidate_kind": candidate.candidate_kind,
        "candidate_only": candidate.candidate_only,
        "candidate_status": candidate.candidate_status,
        "cohort_key_dimensions": list(candidate.cohort_key_dimensions),
        "cohort_key_values": list(candidate.cohort_key_values),
        "coverage_gap_rate": candidate.coverage_gap_rate,
        "enforcement_enabled": candidate.enforcement_enabled,
        "evidence_class": candidate.evidence_class,
        "observability_rate": candidate.observability_rate,
        "observe_only": candidate.observe_only,
        "observed_value": candidate.observed_value,
        "operator_approved": candidate.operator_approved,
        "policy_candidate_id": candidate.policy_candidate_id,
        "primary_measured_denominator_count": (
            candidate.primary_measured_denominator_count
        ),
        "readiness": candidate.readiness,
        "reason": candidate.reason,
        "rejection_rate": candidate.rejection_rate,
        "row_count": candidate.row_count,
        "runtime_consumable": candidate.runtime_consumable,
        "scope_gap_rate": candidate.scope_gap_rate,
        "source_conflict_rate": candidate.source_conflict_rate,
        "source_threshold_candidate_id": (
            candidate.source_threshold_candidate_id
        ),
        "source_threshold_candidate_kind": (
            candidate.source_threshold_candidate_kind
        ),
        "source_threshold_candidate_status": (
            candidate.source_threshold_candidate_status
        ),
        "source_threshold_review_readiness": (
            candidate.source_threshold_review_readiness
        ),
        "stage25_manifest_hash": candidate.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            candidate.stage26_policy_candidate_version
        ),
        "stage26_threshold_generation_version": (
            candidate.stage26_threshold_generation_version
        ),
        "threshold_calibration_eligible_count": (
            candidate.threshold_calibration_eligible_count
        ),
        "threshold_direction": candidate.threshold_direction,
        "threshold_value": candidate.threshold_value,
    }


def _summary_to_dict(
    summary: Stage26PolicyCandidateSummary,
    *,
    build_result: Stage26PolicyCandidateBuildResult,
) -> dict:
    """Serialize the build's summary into a canonical JSON object.

    The summary body is the per-build ``Stage26PolicyCandidateSummary``
    record's fields plus the locked Stage 26.5 observe-only mode
    marker and version axes. The mode marker is a literal string
    that downstream consumers can grep for to confirm the artifact
    is not a runtime policy artifact.
    """
    return {
        "artifact_schema_version": summary.artifact_schema_version,
        "blocked_approval_leak_count": (
            summary.blocked_approval_leak_count
        ),
        "blocked_insufficient_evidence_count": (
            summary.blocked_insufficient_evidence_count
        ),
        "blocked_invalid_threshold_count": (
            summary.blocked_invalid_threshold_count
        ),
        "blocked_policy_leak_count": summary.blocked_policy_leak_count,
        "blocked_runtime_consumable_count": (
            summary.blocked_runtime_consumable_count
        ),
        "candidate_generation_version": (
            summary.candidate_generation_version
        ),
        "candidate_only_true_count": summary.candidate_only_true_count,
        "coverage_caveat_policy_candidate_kind_count": (
            summary.coverage_caveat_policy_candidate_kind_count
        ),
        "deterministic_ordering_version": (
            summary.deterministic_ordering_version
        ),
        "enforcement_enabled_count": summary.enforcement_enabled_count,
        "enforcement_enabled_false_count": (
            summary.enforcement_enabled_false_count
        ),
        "invalid_for_operator_review_count": (
            summary.invalid_for_operator_review_count
        ),
        "needs_better_coverage_count": (
            summary.needs_better_coverage_count
        ),
        "needs_more_measured_rows_count": (
            summary.needs_more_measured_rows_count
        ),
        "needs_rejection_review_count": (
            summary.needs_rejection_review_count
        ),
        "needs_scope_review_count": summary.needs_scope_review_count,
        "observability_caveat_policy_candidate_kind_count": (
            summary.observability_caveat_policy_candidate_kind_count
        ),
        "observe_only_candidate_count": (
            summary.observe_only_candidate_count
        ),
        "observe_only_mode": (
            STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE
        ),
        "observe_only_true_count": summary.observe_only_true_count,
        "operator_approved_count": summary.operator_approved_count,
        "operator_approved_false_count": (
            summary.operator_approved_false_count
        ),
        "ready_for_operator_review_count": (
            summary.ready_for_operator_review_count
        ),
        "rejection_caveat_policy_candidate_kind_count": (
            summary.rejection_caveat_policy_candidate_kind_count
        ),
        "runtime_consumable_count": summary.runtime_consumable_count,
        "runtime_consumable_false_count": (
            summary.runtime_consumable_false_count
        ),
        "source_threshold_candidate_count": (
            summary.source_threshold_candidate_count
        ),
        "source_threshold_ready_count": (
            summary.source_threshold_ready_count
        ),
        "stage25_manifest_hash": summary.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
        "stage26_threshold_generation_version": (
            build_result.stage26_threshold_generation_version
        ),
        "threshold_policy_candidate_kind_count": (
            summary.threshold_policy_candidate_kind_count
        ),
        "total_policy_candidates": summary.total_policy_candidates,
    }


def _manifest_file_entry(
    *,
    artifact_kind: str,
    basename: str,
    sha256: str,
    byte_count: int,
    row_count: int,
) -> dict:
    return {
        "artifact_kind": artifact_kind,
        "basename": basename,
        "byte_count": byte_count,
        "row_count": row_count,
        "sha256": sha256,
    }


def _build_manifest_body(
    *,
    rows_bytes: bytes,
    summary_bytes: bytes,
    build_result: Stage26PolicyCandidateBuildResult,
    rows_row_count: int,
) -> dict:
    """Assemble the Stage 26.5 manifest body (without the manifest's own bytes).

    The body lists every artifact entry (sorted ascending by
    basename) including the manifest's own self-entry sentinel
    record. The sentinel record carries the locked
    ``STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_*`` values so the
    manifest's serialized bytes do not depend on its own sha256 (a
    self-referential dependency Stage 25 also breaks via the same
    sentinel convention).
    """
    rows_entry = _manifest_file_entry(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_ROWS,
        basename=STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
        sha256=_sha256_hex(rows_bytes),
        byte_count=len(rows_bytes),
        row_count=rows_row_count,
    )
    summary_entry = _manifest_file_entry(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY,
        basename=STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
        sha256=_sha256_hex(summary_bytes),
        byte_count=len(summary_bytes),
        row_count=-1,
    )
    manifest_self_entry = _manifest_file_entry(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST,
        basename=STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
        sha256=(
            STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256
        ),
        byte_count=(
            STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
        ),
        row_count=(
            STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_ROW_COUNT
        ),
    )
    entries = sorted(
        (rows_entry, summary_entry, manifest_self_entry),
        key=lambda entry: entry["basename"],
    )
    return {
        "artifact_schema_version": (
            build_result.artifact_schema_version
        ),
        "candidate_generation_version": (
            build_result.candidate_generation_version
        ),
        "deterministic_ordering_version": (
            build_result.deterministic_ordering_version
        ),
        "files": entries,
        "manifest_kind": "stage26_policy_candidate_manifest",
        "observe_only_mode": (
            STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE
        ),
        "redaction_confirmed": (
            STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN
        ),
        "stage25_manifest_hash": build_result.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
        "stage26_threshold_deterministic_ordering_version": (
            build_result.stage26_threshold_deterministic_ordering_version
        ),
        "stage26_threshold_generation_version": (
            build_result.stage26_threshold_generation_version
        ),
        "stage26_threshold_version": (
            build_result.stage26_threshold_version
        ),
    }


# ---------------------------------------------------------------------------
# Redaction sweep + runtime-filename guard
# ---------------------------------------------------------------------------


def _redaction_scan(payload: bytes, *, basename: str) -> None:
    """Refuse forbidden substrings in a Stage 26.5 output payload."""
    text = payload.decode("utf-8")
    lower = text.lower()
    for fragment in STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS:
        if fragment.lower() in lower:
            raise Stage26PolicyCandidateError(
                (
                    f"Stage 26.5 writer redaction sweep refused "
                    f"artifact {basename!r}: forbidden fragment "
                    f"{fragment!r} appears in the canonical payload"
                ),
                error_code=STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED,
            )


def _validate_basename_not_runtime_policy(basename: str) -> None:
    """Refuse an output basename carrying a runtime-policy fragment."""
    lower = basename.lower()
    for fragment in (
        STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
    ):
        if fragment in lower:
            raise Stage26PolicyCandidateError(
                (
                    f"Stage 26.5 writer refused output basename "
                    f"{basename!r}: forbidden runtime-policy fragment "
                    f"{fragment!r} detected"
                ),
                error_code=STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK,
            )


def _validate_locked_basenames() -> None:
    """Defensive validation that the locked output basenames match the spec.

    The check runs at writer entry so a future refactor that
    introduces a stray basename (or drops one) fails immediately
    rather than silently emitting a non-conforming artifact set.
    """
    expected = frozenset(
        (
            STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
            STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
            STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
        )
    )
    actual = frozenset(STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES)
    if expected != actual:
        raise Stage26PolicyCandidateError(
            (
                "Stage 26.5 locked artifact basenames disagree: "
                f"expected {sorted(expected)!r}, got {sorted(actual)!r}"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID,
        )
    for basename in expected:
        _validate_basename_not_runtime_policy(basename)


# ---------------------------------------------------------------------------
# Output-dir validation
# ---------------------------------------------------------------------------


def _validate_output_dir(output_dir: Path) -> None:
    if not isinstance(output_dir, Path):
        raise Stage26PolicyCandidateError(
            (
                "Stage 26.5 writer requires a pathlib.Path output "
                f"directory; got {type(output_dir).__name__}"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID,
        )
    if not output_dir.exists():
        raise Stage26PolicyCandidateError(
            (
                f"Stage 26.5 writer output directory {str(output_dir)!r} "
                "does not exist; Stage 26.5 refuses to create arbitrary "
                "parent directories"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID,
        )
    if not output_dir.is_dir():
        raise Stage26PolicyCandidateError(
            (
                f"Stage 26.5 writer output directory {str(output_dir)!r} "
                "is not a directory"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID,
        )


# ---------------------------------------------------------------------------
# Public writer entrypoint
# ---------------------------------------------------------------------------


def write_policy_candidate_artifacts(
    build_result: Stage26PolicyCandidateBuildResult,
    output_dir: Path,
) -> Stage26PolicyCandidateArtifactSet:
    """Write the Stage 26.5 observe-only artifact set into ``output_dir``.

    The writer:

      1. Validates ``output_dir`` exists and is a directory.
      2. Validates the locked Stage 26.5 basenames are the only
         basenames it will emit (defensive against refactor drift).
      3. Serializes the rows JSONL + summary JSON payloads.
      4. Runs the Stage 26.5 redaction sweep over both payloads
         BEFORE writing any bytes to disk.
      5. Assembles the manifest body using the locked self-entry
         sentinel.
      6. Serializes the manifest JSON payload and re-runs the
         redaction sweep on it.
      7. Writes each artifact to ``output_dir`` via
         ``Path.write_bytes`` (no temp-file dance because Stage
         26.5 does not promise atomicity; the writer's safety net
         is the upstream redaction sweep, not crash-resilience).
      8. Returns an immutable ``Stage26PolicyCandidateArtifactSet``
         recording each artifact's reference.

    Raises ``Stage26PolicyCandidateError`` on any invariant
    violation. On error the writer leaves the output directory in
    whatever state the last successful step achieved -- callers
    should treat any non-empty error as an unsafe-to-trust output
    set.
    """
    _validate_output_dir(output_dir)
    _validate_locked_basenames()

    rows_payload = tuple(
        _policy_candidate_to_row(candidate)
        for candidate in build_result.policy_candidates
    )
    rows_bytes = _canonical_jsonl_bytes(rows_payload)
    rows_row_count = _count_non_blank_lines(rows_bytes)

    summary_obj = _summary_to_dict(
        build_result.summary, build_result=build_result
    )
    summary_bytes = _canonical_json_bytes(summary_obj)

    _redaction_scan(
        rows_bytes,
        basename=STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
    )
    _redaction_scan(
        summary_bytes,
        basename=STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
    )

    manifest_body = _build_manifest_body(
        rows_bytes=rows_bytes,
        summary_bytes=summary_bytes,
        build_result=build_result,
        rows_row_count=rows_row_count,
    )
    manifest_bytes = _canonical_json_bytes(manifest_body)
    _redaction_scan(
        manifest_bytes,
        basename=STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
    )

    rows_path = output_dir / STAGE26_POLICY_CANDIDATE_ROWS_FILENAME
    summary_path = (
        output_dir / STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME
    )
    manifest_path = (
        output_dir / STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME
    )

    rows_path.write_bytes(rows_bytes)
    summary_path.write_bytes(summary_bytes)
    manifest_path.write_bytes(manifest_bytes)

    rows_ref = Stage26PolicyCandidateArtifactReference(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_ROWS,
        basename=STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
        sha256=_sha256_hex(rows_bytes),
        byte_count=len(rows_bytes),
        row_count=rows_row_count,
        redaction_confirmed=True,
    )
    summary_ref = Stage26PolicyCandidateArtifactReference(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY,
        basename=STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
        sha256=_sha256_hex(summary_bytes),
        byte_count=len(summary_bytes),
        row_count=-1,
        redaction_confirmed=True,
    )
    manifest_ref = Stage26PolicyCandidateArtifactReference(
        artifact_kind=POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST,
        basename=STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
        sha256=_sha256_hex(manifest_bytes),
        byte_count=len(manifest_bytes),
        row_count=-1,
        redaction_confirmed=True,
    )
    references = tuple(
        sorted(
            (rows_ref, summary_ref, manifest_ref),
            key=lambda entry: entry.basename,
        )
    )
    return Stage26PolicyCandidateArtifactSet(
        output_dir=str(output_dir),
        rows_path=str(rows_path),
        summary_path=str(summary_path),
        manifest_path=str(manifest_path),
        artifact_references=references,
        manifest_hash=_sha256_hex(manifest_bytes),
        redaction_confirmed=all(
            ref.redaction_confirmed for ref in references
        ),
    )


__all__ = [
    "write_policy_candidate_artifacts",
]
