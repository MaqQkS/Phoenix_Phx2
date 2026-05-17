"""Stage 21 deterministic artifact writers.

Stage 21.1 ships a single writer:
  * ``write_foundation_manifest`` -- serializes a
    ``Stage21FoundationManifest`` to a JSON file with sorted keys
    and a trailing newline. The output is byte-identical across
    re-runs when the inputs (including the clock-derived
    ``generated_at_utc_iso`` field) are identical.

No existing PHX2 table is mutated. The writer accepts a target
file path and refuses to write outside a directory the caller
controls; the boundary check rejects:
  * empty paths,
  * paths that traverse via ``..``,
  * paths whose parent directory does not already exist.

The Stage 21 writer is artifact-based to mirror the Stage 17 /
18 / 19 / 20 convention. Stage 21.1 does not introduce a DB
migration; the foundation manifest lives entirely on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.credential_attestation import (
    CredentialAttestation,
    serialize_attestation_bundle,
)
from PHX2.stage21.errors import Stage21BoundaryError
from PHX2.stage21.telemetry_models import Stage21FoundationManifest


def manifest_to_dict(
    manifest: Stage21FoundationManifest,
) -> Mapping[str, object]:
    """Serialize a foundation manifest to a manifest-safe dict.

    The returned mapping is JSON-friendly: every value is a
    primitive, a list, or a dict; no secret value appears
    anywhere. The function is deterministic -- ordering follows
    the manifest record's field order, attestations are emitted
    in their pre-sorted order, and the recipients tuple is
    converted to a list verbatim (the parser already sorts).
    """
    if not isinstance(manifest, Stage21FoundationManifest):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "manifest_to_dict expected Stage21FoundationManifest; "
                f"got {type(manifest).__name__}"
            ),
        )
    return {
        "run_metadata": manifest.run_metadata.public_summary(),
        "credential_attestations": serialize_attestation_bundle(
            manifest.credential_attestations
        ),
        "allowlist_summary": {
            "recipients": list(manifest.allowlist_summary.recipients),
            "count": manifest.allowlist_summary.count,
            "fail_closed": manifest.allowlist_summary.fail_closed,
        },
        # Stage 21.1 emits a zero-length list; the field is
        # reserved for 21.2+. The placeholder records carry no
        # secret-class values.
        "pings": [
            {
                "ping_id": p.ping_id,
                "candidate_id": p.candidate_id,
                "safe_for_public_dispatch": p.safe_for_public_dispatch,
                "private_preview_marker_present":
                    p.private_preview_marker_present,
            }
            for p in manifest.pings
        ],
    }


def _validate_target_path(target: Path) -> None:
    """Reject unsafe target paths.

    Raises ``Stage21BoundaryError`` (E2106) when:
      * ``target`` is empty, has no file-name part, or resolves to
        the current directory (``Path("")`` -> ``Path('.')`` on
        most platforms),
      * any path component is ``..``,
      * the parent directory does not exist.

    The writer never creates parent directories itself; the
    caller is responsible for setting up the run directory. This
    avoids the writer silently materializing arbitrary paths.
    """
    if not isinstance(target, Path):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "target must be a pathlib.Path instance; got "
                f"{type(target).__name__}"
            ),
        )
    rendered = str(target).strip()
    if rendered == "" or rendered == ".":
        # ``Path("")`` constructs a path equal to ``Path(".")`` on
        # CPython; both forms are unsafe as a write target because
        # they resolve to the current working directory.
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail="target path is empty or refers to the cwd",
        )
    if target.name == "":
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail="target path has no file-name part",
        )
    if ".." in target.parts:
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail="target path traverses via '..'",
        )
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "target path's parent directory does not exist or is "
                "not a directory"
            ),
        )


def write_foundation_manifest(
    manifest: Stage21FoundationManifest,
    target: Path,
) -> None:
    """Write the Stage 21 foundation manifest to ``target``.

    The writer emits JSON with ``sort_keys=True`` and a trailing
    newline so byte-identical inputs produce byte-identical
    output. The file is opened in text mode with UTF-8 encoding
    and an explicit ``\\n`` newline -- no BOM, no platform-native
    newline.

    Raises ``Stage21BoundaryError`` (E2106) when the target path
    is unsafe. The writer never mutates any existing PHX2 table
    and never touches a path outside ``target``.
    """
    _validate_target_path(target)
    payload = manifest_to_dict(manifest)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    ) + "\n"
    # Open in binary mode and write encoded UTF-8 so a trailing
    # newline is always \n on every platform. The Stage 17 / 18 /
    # 19 / 20 writers follow the same pattern.
    target.write_bytes(encoded.encode("utf-8"))


def serialize_attestations(
    attestations: tuple[CredentialAttestation, ...],
) -> list[Mapping[str, object]]:
    """Convenience re-export of the attestation serializer.

    Stage 21.1 tests call this helper directly to verify the
    attestation serialization is deterministic and free of any
    secret value. The helper is kept here (rather than only on
    ``credential_attestation``) so callers that only depend on
    the writer module have a single import surface.
    """
    return serialize_attestation_bundle(attestations)


__all__ = [
    "manifest_to_dict",
    "serialize_attestations",
    "write_foundation_manifest",
]
