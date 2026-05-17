"""Stage 21.2 deterministic artifact writers.

This module owns the four Stage 21.2 file artifacts:

  * ``stage21_2_manifest.json``                -- run manifest
  * ``stage21_2_ping_ledger.jsonl``            -- one line per ping
  * ``stage21_2_fake_transport_capture.jsonl`` -- one line per capture
  * ``stage21_2_telemetry_summary.json``       -- aggregate summary

All writers:

  * accept an explicit target ``Path``;
  * validate the target path is safe (no empty path, no ``..``
    traversal, parent directory must exist, no recursive parent
    creation);
  * raise ``Stage21BoundaryError`` (E2106) on any unsafe path;
  * produce byte-identical output across re-runs with identical
    inputs;
  * serialize as UTF-8 with sorted keys and a trailing ``\\n``;
  * never echo any secret, webhook target, URL, credential, or
    public/paid/subscriber routing identifier into the artifact.

The writers do not create the output directory; they assume the
caller (the Stage 21.2 simulator) has already set it up. The
simulator may create exactly one directory level -- this
preserves the Stage 21.1 "writer never creates parent
directories" invariant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.constants import (
    FORBIDDEN_SUBSTRINGS,
    Stage21ErrorCode,
)
from PHX2.stage21.errors import Stage21BoundaryError, Stage21Error
from PHX2.stage21.fake_transport import FakeTransportCaptureRecord
from PHX2.stage21.ping_payloads import (
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
    PING_PAYLOAD_REQUIRED_MARKER_VALUES,
    PrivatePreviewPingPayload,
    STAGE21_2_STAGE_LABEL,
)


# ---------------------------------------------------------------------------
# Stage 21.2 remediation (R4) + R4-followup writer-boundary audit
# ---------------------------------------------------------------------------
#
# Each ``write_stage21_2_*`` function validates its input
# through the shared ``safe_content.validate_safe_payload_dict``
# predicate at entry, before any file is created or written.
# Unsafe input raises ``Stage21Error`` and leaves the filesystem
# untouched.
#
# The R4-followup audit closed two writer-boundary gaps where
# the R4 exemption mechanics let an attacker land an unsafe
# value on disk even though safe_content nominally passed:
#
#   * Manifest sanitized-copy strip: the original implementation
#     stripped the two locked-invariant ``run_metadata`` fields
#     from the validation copy by KEY NAME regardless of value.
#     A poisoned caller that bypassed
#     ``assemble_stage21_2_manifest`` and substituted a URL-
#     shaped string under ``stage21_2_stage_label`` or flipped
#     ``safe_for_public_dispatch`` to ``True`` / ``"false"``
#     would see the unsafe value stripped from the validation
#     copy and silently serialized into the artifact. The audit
#     fix (``_validate_manifest_locked_run_metadata_fields``)
#     asserts each locked invariant field carries EXACTLY the
#     locked Python constant value BEFORE the validation copy is
#     built; the strip is then legitimate only because the
#     locked literals have been confirmed.
#
#   * Ping/capture marker exemption: the ping ledger and capture
#     writers pass ``PING_PAYLOAD_REQUIRED_MARKER_KEYS`` as
#     ``exempt_keys`` so the safe_content predicate skips those
#     values. The R4 implementation relied on the ping builder
#     and the fake transport boundary to exact-equality enforce
#     the marker values upstream. The audit found that a
#     poisoned ``PrivatePreviewPingPayload`` (markers replaced
#     via ``_replace`` or a subclass override of
#     ``public_summary``) could bypass both upstream boundaries
#     and reach the writer with tampered markers. The audit fix
#     (``_validate_private_preview_marker_dict``) re-asserts each
#     marker's exact locked value on the row dict at writer
#     entry, BEFORE safe_content's exemption skips them.
#
# Manifest sanitized-copy pattern:
#   The Stage 21.2 manifest contains two locked Stage 21
#   invariant fields whose key/value shapes the safe_content
#   predicate would otherwise flag:
#
#     * ``run_metadata.stage21_2_stage_label`` -- value
#       ``"21.2"`` (locked ``STAGE21_2_STAGE_LABEL`` constant;
#       contains the literal ``.`` which fails the
#       SHORT_LABEL char-set ``[A-Za-z0-9_]``).
#     * ``run_metadata.safe_for_public_dispatch`` -- locked
#       boolean ``False`` value; the KEY contains the substring
#       ``public_dispatch`` (one of the
#       ``FORBIDDEN_SUBSTRINGS``) but is the Stage 21
#       dispatch-safety invariant name explicitly whitelisted in
#       ``STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS``.
#
#   The manifest writer flow is:
#     1. Assert each locked invariant field carries EXACTLY the
#        locked Python constant value
#        (``_validate_manifest_locked_run_metadata_fields``).
#     2. Construct a sanitized shallow copy of the manifest with
#        the two locked-invariant fields stripped from its
#        ``run_metadata`` block.
#     3. Run the safe_content predicate on the sanitized copy.
#     4. (On success) write the ORIGINAL unchanged manifest to
#        disk.
#
#   The sanitized copy is solely a validation artifact and
#   never reaches the file. The strip is legitimate only
#   because step 1 confirmed the locked literals.
#
# Marker-keys exemption + re-assertion:
#   The ping ledger and capture artifacts include the locked
#   Stage 21.2 private-preview marker fields (``stage`` /
#   ``visibility`` / ``operator_only`` / ``live_mode`` /
#   ``dispatch_target``) at the top level of each row. The
#   writer passes ``PING_PAYLOAD_REQUIRED_MARKER_KEYS`` as
#   ``exempt_keys`` so the safe_content predicate skips those
#   values. The exemption is legitimate ONLY when each marker
#   carries its locked value; re-asserting that invariant on
#   the row dict at writer entry
#   (``_validate_private_preview_marker_dict``) closes the gap
#   where a poisoned ping/capture row would otherwise reach the
#   file.
#
#   This pattern keeps the remediation scoped to
#   ``telemetry_writer.py`` and does not require modifying
#   safe_content's locked exempt set or its structural
#   exemption test.


MANIFEST_VALIDATION_STRIPPED_RUN_METADATA_KEYS: tuple[str, ...] = (
    "stage21_2_stage_label",
    "safe_for_public_dispatch",
)
MANIFEST_VALIDATION_STRIPPED_LOCKED_MARKER_KEYS: tuple[str, ...] = (
    PING_PAYLOAD_REQUIRED_MARKER_KEYS
)


# ---------------------------------------------------------------------------
# Stage 21.2 artifact filenames (locked)
# ---------------------------------------------------------------------------


STAGE21_2_MANIFEST_FILENAME: str = "stage21_2_manifest.json"
STAGE21_2_PING_LEDGER_FILENAME: str = "stage21_2_ping_ledger.jsonl"
STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME: str = (
    "stage21_2_fake_transport_capture.jsonl"
)
STAGE21_2_TELEMETRY_SUMMARY_FILENAME: str = "stage21_2_telemetry_summary.json"


STAGE21_2_ALL_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE21_2_MANIFEST_FILENAME,
    STAGE21_2_PING_LEDGER_FILENAME,
    STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME,
    STAGE21_2_TELEMETRY_SUMMARY_FILENAME,
)


# ---------------------------------------------------------------------------
# Path-safety helpers (mirrors PHX2/stage21/telemetry_writers.py)
# ---------------------------------------------------------------------------


def _validate_target_path(target: Path) -> None:
    """Reject unsafe target paths.

    Raises ``Stage21BoundaryError`` (E2106) when the target is
    empty / cwd / ``..``-traversing / parent-missing. The writer
    never creates parent directories itself.
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


def _dump_json(payload: object) -> str:
    """Serialize ``payload`` to UTF-8 JSON with sorted keys and indent."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def _dump_jsonl(payload: object) -> str:
    """Serialize ``payload`` to a single-line JSON with sorted keys."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ---------------------------------------------------------------------------
# Locked-literal + private-preview marker assertions (R4-followup audit)
# ---------------------------------------------------------------------------
#
# Both helpers below raise ``Stage21Error`` (telemetry family),
# not ``Stage21BoundaryError`` (E2106 is reserved for path-shape
# / target-type failures). Error codes:
#
#   * E2153 -- value is a string carrying a FORBIDDEN_SUBSTRINGS
#              hit (URL-shaped, webhook, public_dispatch, etc.).
#   * E2152 -- otherwise (wrong locked literal, wrong type,
#              missing marker key).


def _raise_locked_literal_violation(
    *,
    field_name: str,
    value: object,
    expected_literal: str,
) -> None:
    """Raise ``Stage21Error`` for an unsafe locked-literal field value.

    Picks the more-specific code: E2153 when the value is a
    string carrying any ``FORBIDDEN_SUBSTRINGS`` hit, E2152
    otherwise. The offending value itself is never echoed into
    the detail.
    """
    if isinstance(value, str):
        lower = value.lower()
        for sub in FORBIDDEN_SUBSTRINGS:
            if sub in lower:
                raise Stage21Error(
                    Stage21ErrorCode.E2153,
                    detail=(
                        f"field {field_name} kind LOCKED_LITERAL "
                        f"code E2153 matched {sub}"
                    ),
                )
    actual_type = type(value).__name__
    raise Stage21Error(
        Stage21ErrorCode.E2152,
        detail=(
            f"field {field_name} kind LOCKED_LITERAL "
            f"code E2152 actual_type {actual_type} "
            f"expected_literal {expected_literal}"
        ),
    )


def _validate_manifest_locked_run_metadata_fields(
    manifest: Mapping[str, object],
) -> None:
    """Assert manifest ``run_metadata`` locked invariant fields exactly match.

    The two locked invariant fields are exempt from the
    manifest's safe_content scan via the sanitized validation
    copy. The exemption is legitimate ONLY when the values are
    exactly the locked Python constants. Any other value -- a
    URL-shaped string, a ``True`` boolean, a ``"false"`` string,
    a different label -- is rejected here so the unsafe value
    is never serialized.

    Required exact values:
      * ``run_metadata.stage21_2_stage_label`` ==
        ``STAGE21_2_STAGE_LABEL`` (``"21.2"``).
      * ``run_metadata.safe_for_public_dispatch`` is exactly
        the Python boolean ``False`` (identity check; truthy /
        falsy non-False values are rejected).

    Does nothing when ``run_metadata`` is missing or non-Mapping
    (the safe_content scan flags that separately) or when the
    locked keys are absent from ``run_metadata`` (the scan
    accepts a manifest without them; the validation-copy strip
    is then a no-op).
    """
    run_metadata = manifest.get("run_metadata")
    if not isinstance(run_metadata, Mapping):
        return
    if "stage21_2_stage_label" in run_metadata:
        value = run_metadata["stage21_2_stage_label"]
        if value != STAGE21_2_STAGE_LABEL:
            _raise_locked_literal_violation(
                field_name="run_metadata.stage21_2_stage_label",
                value=value,
                expected_literal=STAGE21_2_STAGE_LABEL,
            )
    if "safe_for_public_dispatch" in run_metadata:
        value = run_metadata["safe_for_public_dispatch"]
        # Identity check on the locked Python ``False`` literal
        # so ``True`` / ``"false"`` / ``0`` / ``None`` all fail.
        if value is not False:
            _raise_locked_literal_violation(
                field_name="run_metadata.safe_for_public_dispatch",
                value=value,
                expected_literal="False",
            )


def _validate_manifest_locked_markers(manifest: Mapping[str, object]) -> None:
    """Assert manifest ``locked_markers`` carries exact private-preview values."""
    locked_markers = manifest.get("locked_markers")
    if not isinstance(locked_markers, Mapping):
        raise Stage21Error(
            Stage21ErrorCode.E2152,
            detail=(
                "field manifest.locked_markers kind MARKER "
                "code E2152 missing_or_invalid_locked_markers"
            ),
        )
    _validate_private_preview_marker_dict(
        locked_markers,
        context="manifest.locked_markers",
    )


def _raise_marker_violation(
    *,
    field_name: str,
    value: object,
) -> None:
    """Raise ``Stage21Error`` for a wrong-marker-value violation."""
    if isinstance(value, str):
        lower = value.lower()
        for sub in FORBIDDEN_SUBSTRINGS:
            if sub in lower:
                raise Stage21Error(
                    Stage21ErrorCode.E2153,
                    detail=(
                        f"field {field_name} kind MARKER "
                        f"code E2153 matched {sub}"
                    ),
                )
    raise Stage21Error(
        Stage21ErrorCode.E2152,
        detail=(
            f"field {field_name} kind MARKER "
            f"code E2152 wrong_marker_literal"
        ),
    )


def _validate_private_preview_marker_dict(
    row: Mapping[str, object],
    *,
    context: str,
) -> None:
    """Assert ``row`` carries each locked Stage 21.2 marker exactly.

    Each writer that exempts the marker keys from the
    safe_content scan MUST first prove the row carries exactly
    the locked values. Missing keys or any non-exact value
    raises ``Stage21Error`` so the unsafe row never reaches the
    file.

    Required exact values (sourced from
    ``PING_PAYLOAD_REQUIRED_MARKER_VALUES``):
      * ``stage`` == ``"21.2"``
      * ``visibility`` == ``"private_preview"``
      * ``operator_only`` is ``True``   (identity, not equality)
      * ``live_mode`` is ``False``       (identity, not equality)
      * ``dispatch_target`` == ``"fake_private_transport"``

    Codes:
      * E2152 -- missing key, wrong literal, or wrong type.
      * E2153 -- value is a string carrying a
        ``FORBIDDEN_SUBSTRINGS`` hit.
    """
    for key, expected in PING_PAYLOAD_REQUIRED_MARKER_VALUES.items():
        if key not in row:
            raise Stage21Error(
                Stage21ErrorCode.E2152,
                detail=(
                    f"field {context}.{key} kind MARKER "
                    f"code E2152 missing_marker_key"
                ),
            )
        actual = row[key]
        if isinstance(expected, bool):
            # Boolean markers: identity check so truthy-but-not-
            # True values (1 / "yes") do NOT pass.
            if actual is not expected:
                _raise_marker_violation(
                    field_name=f"{context}.{key}",
                    value=actual,
                )
            continue
        if actual == expected:
            continue
        _raise_marker_violation(
            field_name=f"{context}.{key}",
            value=actual,
        )


# ---------------------------------------------------------------------------
# Manifest writer
# ---------------------------------------------------------------------------


def _build_manifest_validation_copy(
    manifest: Mapping[str, object],
) -> Mapping[str, object]:
    """Return a shallow copy of ``manifest`` for the safe_content scan.

    Removes only locked manifest fields whose exact values have
    already been asserted by writer-entry guards. The original
    manifest is never mutated; the returned copy is the input fed
    to ``validate_safe_payload_dict`` only.
    """
    copy: dict[str, object] = dict(manifest)
    run_metadata = copy.get("run_metadata")
    if isinstance(run_metadata, Mapping):
        rm_copy = dict(run_metadata)
        for key in MANIFEST_VALIDATION_STRIPPED_RUN_METADATA_KEYS:
            rm_copy.pop(key, None)
        copy["run_metadata"] = rm_copy
    locked_markers = copy.get("locked_markers")
    if isinstance(locked_markers, Mapping):
        lm_copy = dict(locked_markers)
        for key in MANIFEST_VALIDATION_STRIPPED_LOCKED_MARKER_KEYS:
            lm_copy.pop(key, None)
        copy["locked_markers"] = lm_copy
    return copy


def write_stage21_2_manifest(
    manifest: Mapping[str, object],
    target: Path,
) -> None:
    """Write the Stage 21.2 manifest as a deterministic JSON artifact.

    ``manifest`` is the pre-assembled mapping returned by
    ``PHX2.stage21.stage21_2_manifest.assemble_stage21_2_manifest``.
    The writer:

      1. Asserts ``manifest`` is a ``Mapping``.
      2. Asserts each locked invariant ``run_metadata`` field
         carries EXACTLY the locked Python constant value
         (``_validate_manifest_locked_run_metadata_fields``).
         This closes the R4-followup audit gap where the
         validation-copy strip removed the keys regardless of
         value.
      3. Asserts each ``locked_markers`` field carries EXACTLY
         the private-preview marker value
         (``_validate_manifest_locked_markers``).
      4. Runs the shared ``safe_content`` predicate on a
         sanitized validation copy of ``manifest`` (see
         ``_build_manifest_validation_copy`` for the
         locked-invariant exemption rationale).
      5. Validates the target path.
      6. Writes the ORIGINAL manifest dict to disk.

    Raises ``Stage21BoundaryError`` (E2106) on unsafe paths or
    non-Mapping input. Raises ``Stage21Error`` (E2150..E2158) on
    safe-content violation or locked-literal mismatch. No file
    is created on any failure.
    """
    if not isinstance(manifest, Mapping):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "write_stage21_2_manifest expected Mapping; got "
                f"{type(manifest).__name__}"
            ),
        )
    # R4-followup audit: assert locked invariants exactly before
    # the validation copy strips them. A poisoned value (URL-
    # shaped stage_label, True / "false" safe_for_public_dispatch,
    # etc.) fails closed here.
    _validate_manifest_locked_run_metadata_fields(manifest)
    # Final writer-boundary patch: assert manifest locked_markers
    # exactly before the validation copy strips them. The manifest
    # safe_content call below deliberately uses no broad recursive
    # marker exemptions, so unrelated nested marker-key names are
    # still scanned.
    _validate_manifest_locked_markers(manifest)
    # R4: safe_content predicate on the sanitized copy.
    validation_copy = _build_manifest_validation_copy(manifest)
    _sc.validate_safe_payload_dict(
        validation_copy,
        field_name="manifest",
    )
    _validate_target_path(target)
    target.write_bytes(_dump_json(dict(manifest)).encode("utf-8"))


# ---------------------------------------------------------------------------
# Ping ledger writer
# ---------------------------------------------------------------------------


def write_stage21_2_ping_ledger(
    pings: Sequence[PrivatePreviewPingPayload],
    target: Path,
) -> None:
    """Write the Stage 21.2 ping ledger as JSONL.

    One line per ping payload, in the order supplied by the
    caller (which is the simulator's stable per-event order).
    Each line is the JSON form of the ping payload's
    ``public_summary`` dict.

    R4 + R4-followup audit flow:

      1. Per-element type check.
      2. Per-element marker re-assertion on the row dict
         (``_validate_private_preview_marker_dict``). This
         closes the R4-followup audit gap where a poisoned ping
         (marker replaced via ``_replace`` or a subclass
         override of ``public_summary``) would otherwise bypass
         the safe_content marker-key exemption and reach the
         file.
      3. Per-element safe_content predicate on each ping
         payload's ``public_summary``. Marker keys are exempted
         via ``exempt_keys``; their values were exact-equality
         enforced in step 2.
      4. Target path safety check.
      5. Write the JSONL artifact.

    Raises ``Stage21BoundaryError`` (E2106) on unsafe paths or
    non-payload elements. Raises ``Stage21Error`` (E2150..E2158)
    on safe-content violation or marker mismatch. No file is
    created on any failure.
    """
    # R4 + R4-followup audit: per-element type + marker assert
    # + safe_content validation BEFORE path check and BEFORE any
    # file work.
    marker_exempt = frozenset(PING_PAYLOAD_REQUIRED_MARKER_KEYS)
    for index, ping in enumerate(pings):
        if not isinstance(ping, PrivatePreviewPingPayload):
            raise Stage21BoundaryError(
                Stage21ErrorCode.E2106,
                detail=(
                    f"write_stage21_2_ping_ledger element at index {index} "
                    "is not a PrivatePreviewPingPayload"
                ),
            )
        row = dict(ping.public_summary())
        _validate_private_preview_marker_dict(
            row,
            context=f"ping_ledger[{index}]",
        )
        _sc.validate_safe_payload_dict(
            row,
            field_name=f"ping_ledger[{index}]",
            exempt_keys=marker_exempt,
        )
    _validate_target_path(target)
    lines: list[str] = []
    for ping in pings:
        lines.append(_dump_jsonl(dict(ping.public_summary())))
    encoded = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    target.write_bytes(encoded)


# ---------------------------------------------------------------------------
# Fake transport capture writer
# ---------------------------------------------------------------------------


def write_stage21_2_fake_transport_capture(
    captures: Sequence[FakeTransportCaptureRecord],
    target: Path,
) -> None:
    """Write the Stage 21.2 fake-transport capture artifact as JSONL.

    One line per ``FakeTransportCaptureRecord`` in the order
    supplied by the caller.

    R4 + R4-followup audit flow:

      1. Per-element type check.
      2. Per-element marker re-assertion on the row dict
         (``_validate_private_preview_marker_dict``). This
         closes the R4-followup audit gap where a poisoned
         capture record (marker replaced via ``_replace`` or a
         subclass override of ``public_summary``) would
         otherwise bypass the safe_content marker-key exemption
         and reach the file.
      3. Per-element safe_content predicate on each capture
         record's ``public_summary``. Marker keys are exempted
         via ``exempt_keys``; their values were exact-equality
         enforced in step 2.
      4. Target path safety check.
      5. Write the JSONL artifact.

    Raises ``Stage21BoundaryError`` (E2106) on unsafe paths or
    non-record elements. Raises ``Stage21Error`` (E2150..E2158)
    on safe-content violation or marker mismatch. No file is
    created on any failure.
    """
    # R4 + R4-followup audit: per-element type + marker assert
    # + safe_content validation BEFORE path check and BEFORE any
    # file work.
    marker_exempt = frozenset(PING_PAYLOAD_REQUIRED_MARKER_KEYS)
    for index, record in enumerate(captures):
        if not isinstance(record, FakeTransportCaptureRecord):
            raise Stage21BoundaryError(
                Stage21ErrorCode.E2106,
                detail=(
                    f"write_stage21_2_fake_transport_capture element at "
                    f"index {index} is not a FakeTransportCaptureRecord"
                ),
            )
        row = record.public_summary()
        _validate_private_preview_marker_dict(
            row,
            context=f"capture[{index}]",
        )
        _sc.validate_safe_payload_dict(
            row,
            field_name=f"capture[{index}]",
            exempt_keys=marker_exempt,
        )
    _validate_target_path(target)
    lines: list[str] = []
    for record in captures:
        lines.append(_dump_jsonl(record.public_summary()))
    encoded = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    target.write_bytes(encoded)


# ---------------------------------------------------------------------------
# Telemetry summary writer
# ---------------------------------------------------------------------------


def write_stage21_2_telemetry_summary(
    summary: Mapping[str, object],
    target: Path,
) -> None:
    """Write the Stage 21.2 telemetry summary as deterministic JSON.

    ``summary`` is a Mapping the simulator assembles; the writer
    serializes it with sorted keys and a trailing newline.

    R4 flow:

      1. Type check the summary mapping.
      2. safe_content predicate on the summary. The summary has
         no private-preview marker keys so ``exempt_keys`` is
         the default (empty).
      3. Target path safety check.
      4. Write the JSON artifact.

    Raises ``Stage21BoundaryError`` (E2106) on unsafe paths or
    non-Mapping input. Raises ``Stage21Error`` (E2150..E2158) on
    safe-content violation. No file is created on either
    failure.
    """
    if not isinstance(summary, Mapping):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "write_stage21_2_telemetry_summary expected Mapping; got "
                f"{type(summary).__name__}"
            ),
        )
    # R4: safe_content predicate before path check / file work.
    # No marker keys present in the telemetry summary shape;
    # exempt_keys defaults to MARKER_EXEMPT_KEYS_DEFAULT (empty).
    _sc.validate_safe_payload_dict(
        summary,
        field_name="telemetry_summary",
    )
    _validate_target_path(target)
    target.write_bytes(_dump_json(dict(summary)).encode("utf-8"))


__all__ = [
    "MANIFEST_VALIDATION_STRIPPED_RUN_METADATA_KEYS",
    "MANIFEST_VALIDATION_STRIPPED_LOCKED_MARKER_KEYS",
    "STAGE21_2_ALL_ARTIFACT_FILENAMES",
    "STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME",
    "STAGE21_2_MANIFEST_FILENAME",
    "STAGE21_2_PING_LEDGER_FILENAME",
    "STAGE21_2_TELEMETRY_SUMMARY_FILENAME",
    "write_stage21_2_fake_transport_capture",
    "write_stage21_2_manifest",
    "write_stage21_2_ping_ledger",
    "write_stage21_2_telemetry_summary",
]
