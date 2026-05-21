"""Stage 26.6 deterministic operator review packet writer.

The writer emits Stage 26.6 review-only operator review packet
artifacts into a caller-supplied output directory and returns an
immutable ``Stage26ReviewArtifactSet`` recording each on-disk
artifact's basename, sha256, byte_count, and row_count.

Output artifacts (locked, review-only basenames):

  * ``stage26_operator_review_packet.json``     -- the packet body
                                                   (packet_id,
                                                   handoff
                                                   placeholders,
                                                   version axes,
                                                   safety locks).
  * ``stage26_operator_review_candidates.jsonl`` -- one canonical
                                                    JSON row per
                                                    ``Stage26ReviewCandidate``,
                                                    ordered
                                                    deterministically.
  * ``stage26_operator_review_summary.json``    -- the per-build
                                                   ``Stage26ReviewSummary``
                                                   serialized as
                                                   canonical JSON.
  * ``stage26_operator_review_manifest.json``   -- a Stage 26.6
                                                   manifest body
                                                   carrying every
                                                   artifact's
                                                   basename / sha256
                                                   / byte_count /
                                                   row_count plus
                                                   the manifest's
                                                   own self-entry
                                                   sentinel record.

Determinism / safety rules (Stage 26.6 invariants):

  * Output directory MUST exist before the writer runs; the writer
    never creates arbitrary parent directories.
  * Every JSONL row is canonical JSON (sorted keys, no whitespace,
    ASCII-safe). Identical input
    ``Stage26ReviewPacketBuildResult`` produces byte-identical
    artifacts.
  * Non-empty JSONL files end with a single trailing ``"\\n"``; an
    empty JSONL file is zero bytes (no trailing newline).
  * Packet / summary / manifest JSON files are canonical JSON
    without a trailing newline.
  * Before writing any artifact the writer runs a redaction sweep
    over every artifact's canonical text. The sweep refuses
    forbidden URL / webhook host / secret-shaped fragments and
    approval / runtime / enforcement leak markers; any failure
    raises ``Stage26ReviewPacketError`` and leaves the output
    directory untouched.
  * The writer refuses to emit any artifact under a runtime-policy /
    approval-decision / live-routing basename; the only locked
    basenames are the four review-only artifact basenames declared
    in ``PHX2.stage26.review_packet_constants``.
  * The writer NEVER writes outside the caller-supplied output
    directory.
  * The writer NEVER reads ``os.environ`` / ``os.getenv``, opens a
    network / DB / messaging connection, defines a CLI surface, or
    invokes a Stage 21 / 22 / 23 / 24 production module.

This module imports only stdlib (``hashlib`` / ``json`` /
``pathlib``) plus the Stage 26.6 constants / errors / models
surfaces. It does NOT import any Stage 25 module (Stage 26.6
vocabulary mirrors the Stage 25 self-entry sentinel convention
locally) and does NOT import Stage 26.1 / 26.2 / 26.3 / 26.4 /
26.5 production modules beyond the policy candidate + review
packet model surfaces it consumes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PHX2.stage26.errors import Stage26ReviewPacketError
from PHX2.stage26.review_packet_constants import (
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY,
    STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
    STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
    STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
    STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
    STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES,
    STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS,
    STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS,
    STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN,
    STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE,
    STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256,
    STAGE26_REVIEW_PACKET_VERSION,
    STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID,
    STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID,
    STG26_CAL_REVIEW_PACKET_REDACTION_FAILED,
    STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK,
)
from PHX2.stage26.review_packet_models import (
    Stage26ApprovalHandoff,
    Stage26ReviewArtifactReference,
    Stage26ReviewArtifactSet,
    Stage26ReviewCandidate,
    Stage26ReviewPacket,
    Stage26ReviewPacketBuildResult,
    Stage26ReviewSummary,
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
# Row / summary / handoff / packet serializers
# ---------------------------------------------------------------------------


def _handoff_to_dict(handoff: Stage26ApprovalHandoff) -> dict:
    return {
        "approval_actor": handoff.approval_actor,
        "approval_notes": handoff.approval_notes,
        "approval_required": handoff.approval_required,
        "approval_status": handoff.approval_status,
        "approval_timestamp_utc": handoff.approval_timestamp_utc,
        "enforcement_enabled": handoff.enforcement_enabled,
        "operator_approved": handoff.operator_approved,
        "runtime_consumable": handoff.runtime_consumable,
    }


def _review_candidate_to_row(
    candidate: Stage26ReviewCandidate,
) -> dict:
    """Serialize a ``Stage26ReviewCandidate`` into a canonical JSONL row.

    Field ordering is alphabetical (canonical JSON sorts keys
    anyway, so the row dict's iteration order is purely
    documentation). Tuples are emitted as JSON arrays. The
    embedded approval handoff record is emitted as a nested
    object.
    """
    return {
        "candidate_kind": candidate.candidate_kind,
        "candidate_only": candidate.candidate_only,
        "caveat_summary": candidate.caveat_summary,
        "cohort_key_dimensions": list(candidate.cohort_key_dimensions),
        "cohort_key_values": list(candidate.cohort_key_values),
        "enforcement_enabled": candidate.enforcement_enabled,
        "evidence_class": candidate.evidence_class,
        "handoff": _handoff_to_dict(candidate.handoff),
        "observe_only": candidate.observe_only,
        "observed_value": candidate.observed_value,
        "operator_approved": candidate.operator_approved,
        "policy_candidate_readiness": (
            candidate.policy_candidate_readiness
        ),
        "policy_candidate_status": candidate.policy_candidate_status,
        "review_candidate_id": candidate.review_candidate_id,
        "review_candidate_status": candidate.review_candidate_status,
        "review_only": candidate.review_only,
        "runtime_consumable": candidate.runtime_consumable,
        "source_policy_candidate_id": (
            candidate.source_policy_candidate_id
        ),
        "source_threshold_candidate_id": (
            candidate.source_threshold_candidate_id
        ),
        "stage25_manifest_hash": candidate.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            candidate.stage26_policy_candidate_version
        ),
        "stage26_review_packet_version": (
            candidate.stage26_review_packet_version
        ),
        "threshold_direction": candidate.threshold_direction,
        "threshold_value": candidate.threshold_value,
    }


def _summary_to_dict(
    summary: Stage26ReviewSummary,
    *,
    build_result: Stage26ReviewPacketBuildResult,
) -> dict:
    """Serialize the build's summary into a canonical JSON object."""
    return {
        "artifact_schema_version": summary.artifact_schema_version,
        "blocked_leak_count": summary.blocked_leak_count,
        "candidate_only_count": summary.candidate_only_count,
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
        "observe_only_count": summary.observe_only_count,
        "operator_approved_count": summary.operator_approved_count,
        "operator_approved_false_count": (
            summary.operator_approved_false_count
        ),
        "ready_for_operator_review_count": (
            summary.ready_for_operator_review_count
        ),
        "review_only_count": summary.review_only_count,
        "review_only_mode": STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE,
        "review_packet_version": summary.review_packet_version,
        "runtime_consumable_count": summary.runtime_consumable_count,
        "runtime_consumable_false_count": (
            summary.runtime_consumable_false_count
        ),
        "source_policy_candidate_count": (
            summary.source_policy_candidate_count
        ),
        "source_policy_ready_count": summary.source_policy_ready_count,
        "stage25_manifest_hash": summary.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            build_result.stage26_policy_candidate_version
        ),
        "stage26_review_packet_version": (
            STAGE26_REVIEW_PACKET_VERSION
        ),
        "stage26_threshold_generation_version": (
            build_result.stage26_threshold_generation_version
        ),
        "total_review_candidates": summary.total_review_candidates,
    }


def _packet_to_dict(
    packet: Stage26ReviewPacket,
    *,
    build_result: Stage26ReviewPacketBuildResult,
) -> dict:
    """Serialize the packet body (without rows / summary duplication)."""
    return {
        "approval_handoff": _handoff_to_dict(packet.approval_handoff),
        "approval_handoff_status": packet.approval_handoff_status,
        "candidate_rows_basename": (
            STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME
        ),
        "deterministic_ordering_version": (
            packet.deterministic_ordering_version
        ),
        "enforcement_enabled": packet.enforcement_enabled,
        "manifest_basename": STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
        "operator_approved": packet.operator_approved,
        "packet_id": packet.packet_id,
        "packet_status": packet.packet_status,
        "review_only": packet.review_only,
        "review_only_mode": STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE,
        "review_packet_version": packet.review_packet_version,
        "runtime_consumable": packet.runtime_consumable,
        "source_policy_candidate_build_hash": (
            packet.source_policy_candidate_build_hash
        ),
        "source_policy_candidate_set_size": (
            build_result.source_policy_candidate_set_size
        ),
        "stage25_manifest_hash": packet.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            build_result.stage26_policy_candidate_version
        ),
        "stage26_review_packet_version": (
            STAGE26_REVIEW_PACKET_VERSION
        ),
        "stage26_threshold_generation_version": (
            build_result.stage26_threshold_generation_version
        ),
        "summary_basename": STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
        "total_review_candidates": len(packet.review_candidates),
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
    packet_bytes: bytes,
    candidate_rows_bytes: bytes,
    summary_bytes: bytes,
    build_result: Stage26ReviewPacketBuildResult,
    candidate_rows_row_count: int,
) -> dict:
    """Assemble the Stage 26.6 manifest body (without the manifest's own bytes).

    The body lists every artifact entry (sorted ascending by
    basename) including the manifest's own self-entry sentinel
    record. The sentinel record carries the locked Stage 26.6
    sentinel values so the manifest's serialized bytes do not
    depend on its own sha256.
    """
    packet_entry = _manifest_file_entry(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET,
        basename=STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
        sha256=_sha256_hex(packet_bytes),
        byte_count=len(packet_bytes),
        row_count=-1,
    )
    candidate_rows_entry = _manifest_file_entry(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS,
        basename=STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
        sha256=_sha256_hex(candidate_rows_bytes),
        byte_count=len(candidate_rows_bytes),
        row_count=candidate_rows_row_count,
    )
    summary_entry = _manifest_file_entry(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY,
        basename=STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
        sha256=_sha256_hex(summary_bytes),
        byte_count=len(summary_bytes),
        row_count=-1,
    )
    manifest_self_entry = _manifest_file_entry(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST,
        basename=STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
        sha256=(
            STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256
        ),
        byte_count=(
            STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
        ),
        row_count=(
            STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_ROW_COUNT
        ),
    )
    entries = sorted(
        (
            packet_entry,
            candidate_rows_entry,
            summary_entry,
            manifest_self_entry,
        ),
        key=lambda entry: entry["basename"],
    )
    return {
        "artifact_schema_version": (
            build_result.artifact_schema_version
        ),
        "deterministic_ordering_version": (
            build_result.deterministic_ordering_version
        ),
        "files": entries,
        "manifest_kind": "stage26_review_packet_manifest",
        "redaction_confirmed": (
            STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN
        ),
        "review_only_mode": STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE,
        "review_packet_version": build_result.review_packet_version,
        "stage25_manifest_hash": build_result.stage25_manifest_hash,
        "stage26_policy_candidate_version": (
            build_result.stage26_policy_candidate_version
        ),
        "stage26_review_packet_version": (
            STAGE26_REVIEW_PACKET_VERSION
        ),
        "stage26_threshold_generation_version": (
            build_result.stage26_threshold_generation_version
        ),
    }


# ---------------------------------------------------------------------------
# Redaction sweep + runtime-filename guard
# ---------------------------------------------------------------------------


def _redaction_scan(payload: bytes, *, basename: str) -> None:
    """Refuse forbidden substrings in a Stage 26.6 output payload."""
    text = payload.decode("utf-8")
    lower = text.lower()
    for fragment in STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS:
        if fragment.lower() in lower:
            raise Stage26ReviewPacketError(
                (
                    f"Stage 26.6 writer redaction sweep refused "
                    f"artifact {basename!r}: forbidden fragment "
                    f"{fragment!r} appears in the canonical payload"
                ),
                error_code=STG26_CAL_REVIEW_PACKET_REDACTION_FAILED,
            )


def _validate_basename_not_runtime_policy(basename: str) -> None:
    """Refuse an output basename carrying a runtime / approval fragment."""
    lower = basename.lower()
    for fragment in (
        STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
    ):
        if fragment in lower:
            raise Stage26ReviewPacketError(
                (
                    f"Stage 26.6 writer refused output basename "
                    f"{basename!r}: forbidden runtime / approval / "
                    f"live-routing fragment {fragment!r} detected"
                ),
                error_code=STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK,
            )


def _validate_locked_basenames() -> None:
    """Defensive validation that the locked output basenames match the spec.

    The check runs at writer entry so a future refactor that
    introduces a stray basename (or drops one) fails immediately
    rather than silently emitting a non-conforming artifact set.
    """
    expected = frozenset(
        (
            STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
            STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
            STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
            STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
        )
    )
    actual = frozenset(STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES)
    if expected != actual:
        raise Stage26ReviewPacketError(
            (
                "Stage 26.6 locked artifact basenames disagree: "
                f"expected {sorted(expected)!r}, got {sorted(actual)!r}"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID,
        )
    for basename in expected:
        _validate_basename_not_runtime_policy(basename)


# ---------------------------------------------------------------------------
# Output-dir validation
# ---------------------------------------------------------------------------


def _validate_output_dir(output_dir: Path) -> None:
    if not isinstance(output_dir, Path):
        raise Stage26ReviewPacketError(
            (
                "Stage 26.6 writer requires a pathlib.Path output "
                f"directory; got {type(output_dir).__name__}"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID,
        )
    if not output_dir.exists():
        raise Stage26ReviewPacketError(
            (
                f"Stage 26.6 writer output directory {str(output_dir)!r} "
                "does not exist; Stage 26.6 refuses to create arbitrary "
                "parent directories"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID,
        )
    if not output_dir.is_dir():
        raise Stage26ReviewPacketError(
            (
                f"Stage 26.6 writer output directory {str(output_dir)!r} "
                "is not a directory"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID,
        )


# ---------------------------------------------------------------------------
# Public writer entrypoint
# ---------------------------------------------------------------------------


def write_review_packet_artifacts(
    build_result: Stage26ReviewPacketBuildResult,
    output_dir: Path,
) -> Stage26ReviewArtifactSet:
    """Write the Stage 26.6 review-only artifact set into ``output_dir``.

    The writer:

      1. Validates ``output_dir`` exists and is a directory.
      2. Validates the locked Stage 26.6 basenames are the only
         basenames it will emit (defensive against refactor drift).
      3. Serializes the candidate rows JSONL + summary JSON +
         packet JSON payloads.
      4. Runs the Stage 26.6 redaction sweep over each payload
         BEFORE writing any bytes to disk.
      5. Assembles the manifest body using the locked self-entry
         sentinel.
      6. Serializes the manifest JSON payload and re-runs the
         redaction sweep on it.
      7. Writes each artifact to ``output_dir`` via
         ``Path.write_bytes``.
      8. Returns an immutable ``Stage26ReviewArtifactSet`` recording
         each artifact's reference.

    Raises ``Stage26ReviewPacketError`` on any invariant violation.
    """
    _validate_output_dir(output_dir)
    _validate_locked_basenames()

    packet = build_result.review_packet
    candidate_rows_payload = tuple(
        _review_candidate_to_row(candidate)
        for candidate in packet.review_candidates
    )
    candidate_rows_bytes = _canonical_jsonl_bytes(candidate_rows_payload)
    candidate_rows_row_count = _count_non_blank_lines(
        candidate_rows_bytes
    )

    summary_obj = _summary_to_dict(
        packet.review_summary, build_result=build_result
    )
    summary_bytes = _canonical_json_bytes(summary_obj)

    packet_obj = _packet_to_dict(packet, build_result=build_result)
    packet_bytes = _canonical_json_bytes(packet_obj)

    _redaction_scan(
        candidate_rows_bytes,
        basename=STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
    )
    _redaction_scan(
        summary_bytes,
        basename=STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
    )
    _redaction_scan(
        packet_bytes,
        basename=STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
    )

    manifest_body = _build_manifest_body(
        packet_bytes=packet_bytes,
        candidate_rows_bytes=candidate_rows_bytes,
        summary_bytes=summary_bytes,
        build_result=build_result,
        candidate_rows_row_count=candidate_rows_row_count,
    )
    manifest_bytes = _canonical_json_bytes(manifest_body)
    _redaction_scan(
        manifest_bytes,
        basename=STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
    )

    packet_path = output_dir / STAGE26_OPERATOR_REVIEW_PACKET_FILENAME
    candidate_rows_path = (
        output_dir / STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME
    )
    summary_path = (
        output_dir / STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME
    )
    manifest_path = (
        output_dir / STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME
    )

    packet_path.write_bytes(packet_bytes)
    candidate_rows_path.write_bytes(candidate_rows_bytes)
    summary_path.write_bytes(summary_bytes)
    manifest_path.write_bytes(manifest_bytes)

    packet_ref = Stage26ReviewArtifactReference(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET,
        basename=STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
        sha256=_sha256_hex(packet_bytes),
        byte_count=len(packet_bytes),
        row_count=-1,
        redaction_confirmed=True,
    )
    candidate_rows_ref = Stage26ReviewArtifactReference(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS,
        basename=STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
        sha256=_sha256_hex(candidate_rows_bytes),
        byte_count=len(candidate_rows_bytes),
        row_count=candidate_rows_row_count,
        redaction_confirmed=True,
    )
    summary_ref = Stage26ReviewArtifactReference(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY,
        basename=STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
        sha256=_sha256_hex(summary_bytes),
        byte_count=len(summary_bytes),
        row_count=-1,
        redaction_confirmed=True,
    )
    manifest_ref = Stage26ReviewArtifactReference(
        artifact_kind=REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST,
        basename=STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
        sha256=_sha256_hex(manifest_bytes),
        byte_count=len(manifest_bytes),
        row_count=-1,
        redaction_confirmed=True,
    )
    references = tuple(
        sorted(
            (
                packet_ref,
                candidate_rows_ref,
                summary_ref,
                manifest_ref,
            ),
            key=lambda entry: entry.basename,
        )
    )
    return Stage26ReviewArtifactSet(
        output_dir=str(output_dir),
        packet_path=str(packet_path),
        candidate_rows_path=str(candidate_rows_path),
        summary_path=str(summary_path),
        manifest_path=str(manifest_path),
        artifact_references=references,
        manifest_hash=_sha256_hex(manifest_bytes),
        redaction_confirmed=all(
            ref.redaction_confirmed for ref in references
        ),
    )


__all__ = [
    "write_review_packet_artifacts",
]
