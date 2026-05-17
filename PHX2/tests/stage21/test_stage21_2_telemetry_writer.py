"""Stage 21.2 telemetry writer tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from PHX2.stage21.clock import FrozenClock
from PHX2.stage21.errors import Stage21BoundaryError, Stage21Error
from PHX2.stage21.fake_transport import FakePrivateTransport
from PHX2.stage21.normalized_events import normalize_fake_event
from PHX2.stage21.ping_builder import (
    build_candidate_from_normalized_event,
    build_private_preview_payload,
)
from PHX2.stage21.ping_payloads import (
    PrivatePreviewPingPayload,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
)
from PHX2.stage21.stage21_2_manifest import (
    Stage21_2SimulationCounts,
    assemble_stage21_2_manifest,
)
from PHX2.stage21.telemetry_writer import (
    STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME,
    STAGE21_2_MANIFEST_FILENAME,
    STAGE21_2_PING_LEDGER_FILENAME,
    STAGE21_2_TELEMETRY_SUMMARY_FILENAME,
    write_stage21_2_fake_transport_capture,
    write_stage21_2_manifest,
    write_stage21_2_ping_ledger,
    write_stage21_2_telemetry_summary,
)


def _payload(mint: str = "FAKE_MINT_AAAA"):
    norm = normalize_fake_event(
        provider_event_id=f"fake_pev_{mint}",
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind="stage21_fake_source",
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint=mint,
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=100,
        signature=f"fake_sig_{mint}",
        raw_payload={"fake_amount": 1000},
    )
    return build_private_preview_payload(
        build_candidate_from_normalized_event(norm)
    )


def _manifest_mapping():
    counts = Stage21_2SimulationCounts(
        fake_events_received=2,
        normalized_events_emitted=2,
        candidates_built=2,
        pings_built=2,
        captures_recorded=2,
        duplicates_skipped=0,
    )
    return assemble_stage21_2_manifest(
        run_id="stage21_2_test_run_id",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=counts,
    )


def _summary_mapping():
    return {
        "run_id": "stage21_2_test_run_id",
        "generated_at_utc_iso": "2026-05-17T12:00:00Z",
        "counts": {
            "fake_events_received": 2,
            "normalized_events_emitted": 2,
            "candidates_built": 2,
            "pings_built": 2,
            "captures_recorded": 2,
            "duplicates_skipped": 0,
        },
        "capture_payload_hashes_sorted": [],
    }


def _captures(tmp_path: Path):
    transport = FakePrivateTransport(
        clock=FrozenClock(
            datetime.fromisoformat("2026-05-17T12:00:00+00:00")
        )
    )
    transport.capture(_payload(mint="FAKE_MINT_A"))
    transport.capture(_payload(mint="FAKE_MINT_B"))
    return transport.captures()


# ---------------------------------------------------------------------------
# Locked filenames
# ---------------------------------------------------------------------------


def test_locked_filenames_have_expected_values():
    assert STAGE21_2_MANIFEST_FILENAME == "stage21_2_manifest.json"
    assert STAGE21_2_PING_LEDGER_FILENAME == "stage21_2_ping_ledger.jsonl"
    assert (
        STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
        == "stage21_2_fake_transport_capture.jsonl"
    )
    assert (
        STAGE21_2_TELEMETRY_SUMMARY_FILENAME
        == "stage21_2_telemetry_summary.json"
    )


# ---------------------------------------------------------------------------
# Manifest writer
# ---------------------------------------------------------------------------


def test_manifest_writer_writes_file(tmp_path: Path):
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    write_stage21_2_manifest(_manifest_mapping(), target)
    assert target.exists()


def test_manifest_writer_byte_deterministic(tmp_path: Path):
    target_a = tmp_path / "a.json"
    target_b = tmp_path / "b.json"
    write_stage21_2_manifest(_manifest_mapping(), target_a)
    write_stage21_2_manifest(_manifest_mapping(), target_b)
    assert target_a.read_bytes() == target_b.read_bytes()


def test_manifest_writer_sorted_keys_and_trailing_newline(tmp_path: Path):
    target = tmp_path / "out.json"
    write_stage21_2_manifest(_manifest_mapping(), target)
    encoded = target.read_text(encoding="utf-8")
    assert encoded.endswith("\n")
    payload = json.loads(encoded)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    ) + "\n"
    assert encoded == canonical


def test_manifest_writer_rejects_non_mapping_input(tmp_path: Path):
    target = tmp_path / "out.json"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_stage21_2_manifest("not a mapping", target)  # type: ignore[arg-type]
    assert excinfo.value.code == "E2106"


def test_manifest_writer_refuses_missing_parent(tmp_path: Path):
    target = tmp_path / "does-not-exist" / "out.json"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_stage21_2_manifest(_manifest_mapping(), target)
    assert excinfo.value.code == "E2106"


def test_manifest_writer_refuses_path_with_dotdot(tmp_path: Path):
    bad = tmp_path / ".." / "out.json"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_stage21_2_manifest(_manifest_mapping(), bad)
    assert excinfo.value.code == "E2106"


def test_manifest_writer_refuses_empty_path():
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_stage21_2_manifest(_manifest_mapping(), Path(""))
    assert excinfo.value.code == "E2106"


def test_manifest_writer_does_not_recursively_create_parents(tmp_path: Path):
    target = tmp_path / "level1" / "level2" / "out.json"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_manifest(_manifest_mapping(), target)
    # The writer must not have created any of the intermediate dirs.
    assert not (tmp_path / "level1").exists()


# ---------------------------------------------------------------------------
# Ping ledger writer
# ---------------------------------------------------------------------------


def test_ping_ledger_writes_one_line_per_payload(tmp_path: Path):
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    pings = [_payload(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")]
    write_stage21_2_ping_ledger(pings, target)
    encoded = target.read_text(encoding="utf-8")
    lines = [ln for ln in encoded.split("\n") if ln]
    assert len(lines) == 2
    # Each line must be valid JSON.
    for ln in lines:
        json.loads(ln)


def test_ping_ledger_empty_pings_writes_empty_artifact(tmp_path: Path):
    target = tmp_path / "out.jsonl"
    write_stage21_2_ping_ledger([], target)
    assert target.read_bytes() == b""


def test_ping_ledger_byte_deterministic(tmp_path: Path):
    pings = [_payload(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")]
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    write_stage21_2_ping_ledger(pings, a)
    write_stage21_2_ping_ledger(pings, b)
    assert a.read_bytes() == b.read_bytes()


def test_ping_ledger_rejects_non_payload_element(tmp_path: Path):
    target = tmp_path / "out.jsonl"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        write_stage21_2_ping_ledger(
            [_payload(), "not a payload"],  # type: ignore[list-item]
            target,
        )
    assert excinfo.value.code == "E2106"


def test_ping_ledger_refuses_missing_parent(tmp_path: Path):
    target = tmp_path / "missing" / "out.jsonl"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_ping_ledger([_payload()], target)


# ---------------------------------------------------------------------------
# Fake-transport capture writer
# ---------------------------------------------------------------------------


def test_capture_writer_writes_one_line_per_record(tmp_path: Path):
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    captures = _captures(tmp_path)
    write_stage21_2_fake_transport_capture(captures, target)
    encoded = target.read_text(encoding="utf-8")
    lines = [ln for ln in encoded.split("\n") if ln]
    assert len(lines) == 2


def test_capture_writer_byte_deterministic(tmp_path: Path):
    captures = _captures(tmp_path)
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    write_stage21_2_fake_transport_capture(captures, a)
    write_stage21_2_fake_transport_capture(captures, b)
    assert a.read_bytes() == b.read_bytes()


def test_capture_writer_rejects_non_capture_element(tmp_path: Path):
    target = tmp_path / "out.jsonl"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_fake_transport_capture(
            ["not a capture"],  # type: ignore[list-item]
            target,
        )


def test_capture_writer_refuses_missing_parent(tmp_path: Path):
    target = tmp_path / "missing" / "out.jsonl"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_fake_transport_capture(_captures(tmp_path), target)


# ---------------------------------------------------------------------------
# Telemetry summary writer
# ---------------------------------------------------------------------------


def test_summary_writer_writes_file(tmp_path: Path):
    target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    write_stage21_2_telemetry_summary(_summary_mapping(), target)
    assert target.exists()


def test_summary_writer_byte_deterministic(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_stage21_2_telemetry_summary(_summary_mapping(), a)
    write_stage21_2_telemetry_summary(_summary_mapping(), b)
    assert a.read_bytes() == b.read_bytes()


def test_summary_writer_rejects_non_mapping_input(tmp_path: Path):
    target = tmp_path / "out.json"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_telemetry_summary("not a mapping", target)  # type: ignore[arg-type]


def test_summary_writer_refuses_missing_parent(tmp_path: Path):
    target = tmp_path / "missing" / "out.json"
    with pytest.raises(Stage21BoundaryError):
        write_stage21_2_telemetry_summary(_summary_mapping(), target)


# ---------------------------------------------------------------------------
# Forbidden-content guards across all four artifacts
# ---------------------------------------------------------------------------


_FORBIDDEN_ARTIFACT_SUBSTRINGS: tuple[str, ...] = (
    "http" + "://",
    "https" + "://",
    "webhook",
    "api_key",
    "password",
    "credential",
    # Routing tokens forbidden in Stage 21.
    "public_dispatch",
    "paid_dispatch",
    "subscriber",
    "public_signal",
    "paid_signal",
)


# Stage 21.2 remediation R5: the artifact-content scan uses the
# JSON-aware ``cleaned_artifact_text_from_path`` helper. The
# helper parses each artifact, strips only the exact locked-
# invariant keypath ``run_metadata.safe_for_public_dispatch``
# (when its value is the Python boolean ``False``), and re-
# serializes the cleaned structure for substring scanning. The
# prior global ``.replace("safe_for_public_dispatch", "")``
# substring strip has been removed.
from PHX2.tests.stage21._artifact_scan_helpers import (  # noqa: E402
    cleaned_artifact_text_from_path,
)


def test_no_forbidden_strings_in_any_written_artifact(tmp_path: Path):
    manifest_target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    ledger_target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    capture_target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    summary_target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME

    write_stage21_2_manifest(_manifest_mapping(), manifest_target)
    write_stage21_2_ping_ledger(
        [_payload(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")],
        ledger_target,
    )
    write_stage21_2_fake_transport_capture(_captures(tmp_path), capture_target)
    write_stage21_2_telemetry_summary(_summary_mapping(), summary_target)

    for target in (
        manifest_target,
        ledger_target,
        capture_target,
        summary_target,
    ):
        cleaned = cleaned_artifact_text_from_path(target)
        for needle in _FORBIDDEN_ARTIFACT_SUBSTRINGS:
            assert needle not in cleaned, (
                f"{target.name} contains forbidden substring {needle!r}"
            )


# ---------------------------------------------------------------------------
# "token" and "secret" appear in artifacts only as schema-version substrings
# ---------------------------------------------------------------------------
#
# The locked schema versions for normalized events / ping payloads
# never include "token" or "secret"; this test asserts that
# behavior, so future changes that introduce those strings into
# the schema vocabulary fail this test instead of leaking into
# production artifacts.


def test_artifact_does_not_contain_word_secret_or_token(tmp_path: Path):
    manifest_target = tmp_path / "out_manifest.json"
    ledger_target = tmp_path / "out_ledger.jsonl"
    capture_target = tmp_path / "out_capture.jsonl"
    summary_target = tmp_path / "out_summary.json"

    write_stage21_2_manifest(_manifest_mapping(), manifest_target)
    write_stage21_2_ping_ledger([_payload()], ledger_target)
    write_stage21_2_fake_transport_capture(_captures(tmp_path), capture_target)
    write_stage21_2_telemetry_summary(_summary_mapping(), summary_target)

    for target in (
        manifest_target,
        ledger_target,
        capture_target,
        summary_target,
    ):
        encoded = target.read_text(encoding="utf-8").lower()
        assert "secret" not in encoded, (
            f"{target.name} contains 'secret' substring"
        )
        assert "token" not in encoded, (
            f"{target.name} contains 'token' substring"
        )


# ---------------------------------------------------------------------------
# Stage 21.2 remediation R4: writer-entry safe_content validation
# ---------------------------------------------------------------------------
#
# Each writer must reject unsafe input via safe_content BEFORE
# creating any artifact file. The tests below construct
# deliberately unsafe inputs that bypass earlier validation
# boundaries (e.g. by constructing a poisoned ping payload via
# ``_replace``) and verify the writer:
#
#   1. raises ``Stage21Error`` (or ``Stage21BoundaryError`` for
#      non-Mapping / non-record inputs), and
#   2. leaves the target file *uncreated* on the filesystem.


from PHX2.stage21.fake_transport import FakeTransportCaptureRecord  # noqa: E402
from PHX2.stage21.telemetry_writer import (  # noqa: E402
    MANIFEST_VALIDATION_STRIPPED_RUN_METADATA_KEYS,
)
from types import MappingProxyType  # noqa: E402


# ---------------------------------------------------------------------------
# Manifest writer R4 tests
# ---------------------------------------------------------------------------


def test_writer_entry_manifest_rejects_url_run_id_no_file(tmp_path: Path):
    """An unsafe run_id raises before any manifest file is written."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",  # construct with safe run_id
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )
    # Now poison the manifest's run_id in a place safe_content
    # will catch (it's a SHORT_IDENTIFIER value).
    poisoned = dict(poisoned)
    poisoned["run_metadata"] = dict(poisoned["run_metadata"])
    poisoned["run_metadata"]["run_id"] = (
        "https" + "://example.invalid/public_dispatch"
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists(), (
        "R4: unsafe manifest input must leave no file on disk"
    )


def test_writer_entry_manifest_rejects_forbidden_in_counts_no_file(
    tmp_path: Path,
):
    """An unsafe value injected into the counts sub-dict is rejected."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    # Build a poisoned manifest with a string in counts (counts
    # are normally ints; safe_content rejects a string with
    # forbidden substring as a value of a SHORT_LABEL-default
    # key).
    base = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )
    poisoned = dict(base)
    poisoned["counts"] = dict(base["counts"])
    poisoned["counts"]["unsafe_field"] = (
        "carries_webhook_in_value"
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_writer_entry_manifest_accepts_legitimate_input(tmp_path: Path):
    """Safe manifests still write successfully end-to-end."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    mf = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(2, 2, 2, 2, 2, 0),
    )
    write_stage21_2_manifest(mf, target)
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["run_metadata"]["run_id"] == "stage21_2_test_run"
    # Locked-invariant fields still present in the WRITTEN
    # output (not stripped from the disk artifact).
    assert payload["run_metadata"]["stage21_2_stage_label"] == "21.2"
    assert (
        payload["run_metadata"]["safe_for_public_dispatch"]
        is False
    )


def test_writer_entry_manifest_validation_strip_keys_are_locked():
    """R4 audit trail: the sanitized-copy strip set is locked at 2 keys."""
    assert set(MANIFEST_VALIDATION_STRIPPED_RUN_METADATA_KEYS) == {
        "stage21_2_stage_label",
        "safe_for_public_dispatch",
    }


# ---------------------------------------------------------------------------
# Ping ledger writer R4 tests
# ---------------------------------------------------------------------------


def _poisoned_ping(*, mint: str = "FAKE_MINT_AAAA"):
    """Build a ping with a poisoned non-marker field via _replace.

    Direct constructor poisoning of an otherwise-locked
    PrivatePreviewPingPayload lets the test drive the writer's
    safe_content check without going through the ping builder
    (which would otherwise reject the input upstream).
    """
    base = _payload(mint=mint)
    return base._replace(
        # Poison the `reason` field via the structured_payload
        # equivalent isn't a top-level ping payload field;
        # `summary_text` is exempt; `body_text` is exempt. The
        # only top-level non-marker non-exempt string field we
        # can poison and still keep the markers valid is...
        # actually `schema_version` — a SHORT_LABEL-routed value.
        schema_version="carries_webhook_v0",
    )


def test_writer_entry_ping_ledger_rejects_unsafe_ping_no_file(
    tmp_path: Path,
):
    """An unsafe ping payload raises before any ledger file is written."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    pings = [_payload(mint="FAKE_MINT_A"), _poisoned_ping(mint="FAKE_MINT_B")]
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_ping_ledger(pings, target)
    assert exc.value.code == "E2153"
    assert not target.exists(), (
        "R4: unsafe ping ledger input must leave no file on disk"
    )


def test_writer_entry_ping_ledger_rejects_unsafe_first_ping_no_file(
    tmp_path: Path,
):
    """Unsafe element at index 0 is rejected; no file created."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    pings = [_poisoned_ping(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")]
    with pytest.raises(Stage21Error):
        write_stage21_2_ping_ledger(pings, target)
    assert not target.exists()


def test_writer_entry_ping_ledger_accepts_legitimate_input(tmp_path: Path):
    """Safe ping ledger writes successfully."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    write_stage21_2_ping_ledger(
        [_payload(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")],
        target,
    )
    assert target.exists()


# ---------------------------------------------------------------------------
# Fake-transport capture writer R4 tests
# ---------------------------------------------------------------------------


def _capture_with_poisoned_field(tmp_path: Path):
    """Build a FakeTransportCaptureRecord whose top-level field carries an unsafe value.

    The transport's own capture() flow validates the ping (so we
    can't smuggle an unsafe ping through). Instead we capture a
    safe ping and then NamedTuple-replace the captured record's
    schema-free top-level string field with an unsafe value.

    Actually FakeTransportCaptureRecord doesn't have a schema_version
    field. We poison `capture_id` directly via _replace.
    """
    transport = FakePrivateTransport(
        clock=FrozenClock(
            datetime.fromisoformat("2026-05-17T12:00:00+00:00")
        )
    )
    transport.capture(_payload(mint="FAKE_MINT_A"))
    record = transport.captures()[0]
    return record._replace(capture_id="carries_webhook_capture")


def test_writer_entry_capture_rejects_unsafe_record_no_file(tmp_path: Path):
    """Unsafe capture record raises before any capture file is written."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    poisoned = _capture_with_poisoned_field(tmp_path)
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_fake_transport_capture([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_writer_entry_capture_rejects_first_element_no_file(tmp_path: Path):
    """Unsafe element at index 0 is rejected; no file created."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    poisoned = _capture_with_poisoned_field(tmp_path)
    safe = FakePrivateTransport(
        clock=FrozenClock(
            datetime.fromisoformat("2026-05-17T12:00:00+00:00")
        )
    )
    safe.capture(_payload(mint="FAKE_MINT_B"))
    with pytest.raises(Stage21Error):
        write_stage21_2_fake_transport_capture(
            [poisoned, safe.captures()[0]],
            target,
        )
    assert not target.exists()


def test_writer_entry_capture_accepts_legitimate_input(tmp_path: Path):
    """Safe capture sequence writes successfully."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    write_stage21_2_fake_transport_capture(_captures(tmp_path), target)
    assert target.exists()


# ---------------------------------------------------------------------------
# Telemetry summary writer R4 tests
# ---------------------------------------------------------------------------


def test_writer_entry_summary_rejects_url_run_id_no_file(tmp_path: Path):
    """Unsafe run_id in telemetry summary raises before file write."""
    target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    summary = dict(_summary_mapping())
    summary["run_id"] = "https" + "://attacker.example/leak"
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_telemetry_summary(summary, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_writer_entry_summary_rejects_unsafe_field_no_file(tmp_path: Path):
    """Unsafe arbitrary field in summary raises before file write."""
    target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    summary = dict(_summary_mapping())
    summary["operator_note"] = "carries_webhook_in_note"
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_telemetry_summary(summary, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_writer_entry_summary_rejects_unsafe_timestamp_no_file(
    tmp_path: Path,
):
    """Unsafe generated_at_utc_iso in summary raises before file write."""
    target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    summary = dict(_summary_mapping())
    summary["generated_at_utc_iso"] = "not-a-timestamp"
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_telemetry_summary(summary, target)
    # TIMESTAMP regex miss yields E2152; either E2152 or E2153
    # (substring) is fail-closed evidence.
    assert exc.value.code in ("E2152", "E2153")
    assert not target.exists()


def test_writer_entry_summary_accepts_legitimate_input(tmp_path: Path):
    """Safe summary writes successfully."""
    target = tmp_path / STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    write_stage21_2_telemetry_summary(_summary_mapping(), target)
    assert target.exists()


# ---------------------------------------------------------------------------
# Validation precedes path safety (R4: no file work on unsafe input)
# ---------------------------------------------------------------------------


def test_writer_entry_manifest_validation_runs_before_file_write(
    tmp_path: Path,
):
    """Validation must succeed before any write attempt.

    With both unsafe input AND a valid target path, the writer
    must raise via safe_content; the target file must not exist
    afterward. This pins the "validate-then-write" ordering.
    """
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    base = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )
    poisoned = dict(base)
    poisoned["counts"] = dict(base["counts"])
    poisoned["counts"]["leak"] = "carries_webhook_in_counts"
    with pytest.raises(Stage21Error):
        write_stage21_2_manifest(poisoned, target)
    assert not target.exists()


# ---------------------------------------------------------------------------
# Path-safety behavior preserved (existing R4 invariant)
# ---------------------------------------------------------------------------


def test_path_safety_still_rejects_missing_parent_after_r4(tmp_path: Path):
    """R4 wiring must not weaken the existing missing-parent rejection."""
    target = tmp_path / "does-not-exist" / "out.json"
    mf = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )
    with pytest.raises(Stage21BoundaryError) as exc:
        write_stage21_2_manifest(mf, target)
    assert exc.value.code == "E2106"


def test_path_safety_still_rejects_dotdot_after_r4(tmp_path: Path):
    """R4 wiring must not weaken the existing '..' rejection."""
    bad = tmp_path / ".." / "out.json"
    mf = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )
    with pytest.raises(Stage21BoundaryError) as exc:
        write_stage21_2_manifest(mf, bad)
    assert exc.value.code == "E2106"


def test_path_safety_still_rejects_non_mapping_manifest_after_r4(
    tmp_path: Path,
):
    """R4: non-Mapping input still raises Stage21BoundaryError E2106."""
    target = tmp_path / "out.json"
    with pytest.raises(Stage21BoundaryError) as exc:
        write_stage21_2_manifest("not a mapping", target)  # type: ignore[arg-type]
    assert exc.value.code == "E2106"


# ---------------------------------------------------------------------------
# Marker handling not weakened by R4
# ---------------------------------------------------------------------------


def test_r4_does_not_weaken_marker_keys_in_capture_writer(tmp_path: Path):
    """Captured records still carry locked private-preview markers."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    write_stage21_2_fake_transport_capture(_captures(tmp_path), target)
    assert target.exists()
    encoded = target.read_text(encoding="utf-8")
    for line in encoded.splitlines():
        if not line:
            continue
        record = json.loads(line)
        assert record["stage"] == "21.2"
        assert record["visibility"] == "private_preview"
        assert record["operator_only"] is True
        assert record["live_mode"] is False
        assert record["dispatch_target"] == "fake_private_transport"


def test_r4_does_not_weaken_marker_keys_in_ping_ledger(tmp_path: Path):
    """Ping ledger lines still carry the locked private-preview markers."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    write_stage21_2_ping_ledger(
        [_payload(mint="FAKE_MINT_A"), _payload(mint="FAKE_MINT_B")],
        target,
    )
    assert target.exists()
    encoded = target.read_text(encoding="utf-8")
    for line in encoded.splitlines():
        if not line:
            continue
        record = json.loads(line)
        assert record["stage"] == "21.2"
        assert record["visibility"] == "private_preview"
        assert record["operator_only"] is True
        assert record["live_mode"] is False
        assert record["dispatch_target"] == "fake_private_transport"


# ---------------------------------------------------------------------------
# Stage 21.2 R4-followup audit: writer-boundary marker enforcement
# ---------------------------------------------------------------------------
#
# The re-audit found two writer-boundary gaps left by R4:
#
#   * Manifest sanitized-copy strip removed the two locked
#     ``run_metadata`` invariant fields by KEY NAME regardless
#     of value. A poisoned caller that bypassed
#     ``assemble_stage21_2_manifest`` and substituted a URL-
#     shaped string under ``stage21_2_stage_label`` or flipped
#     ``safe_for_public_dispatch`` to ``True`` / ``"false"``
#     would see the unsafe value stripped from the validation
#     copy and silently serialized.
#   * Ping/capture writers passed the marker keys as safe_content
#     exemptions but did not re-assert the marker values. A
#     poisoned ``PrivatePreviewPingPayload`` / capture record
#     (markers replaced via ``_replace`` or a subclass override
#     of ``public_summary``) would slip past both upstream
#     boundaries and serialize an unsafe marker value.
#
# Both gaps are closed by ``telemetry_writer`` local helpers
# (``_validate_manifest_locked_run_metadata_fields`` /
# ``_validate_private_preview_marker_dict``). The tests below
# pin the fix: each unsafe direct writer input raises
# ``Stage21Error`` BEFORE any file is created on disk, and each
# legitimate input still round-trips with the locked values
# preserved.


# ---------------------------------------------------------------------------
# Manifest writer R4-followup tests (Codex tests 1..6)
# ---------------------------------------------------------------------------


def _safe_base_manifest():
    """Return a freshly-assembled, safe Stage 21.2 manifest."""
    return assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=Stage21_2SimulationCounts(0, 0, 0, 0, 0, 0),
    )


def _poison_run_metadata(base, key: str, value):
    """Return a shallow-copy manifest with ``run_metadata[key] = value``."""
    poisoned = dict(base)
    poisoned["run_metadata"] = dict(base["run_metadata"])
    poisoned["run_metadata"][key] = value
    return poisoned


def _poison_locked_marker(base, key: str, value):
    """Return a shallow-copy manifest with ``locked_markers[key] = value``."""
    poisoned = dict(base)
    poisoned["locked_markers"] = dict(base["locked_markers"])
    poisoned["locked_markers"][key] = value
    return poisoned


def _drop_locked_marker(base, key: str):
    """Return a shallow-copy manifest with one locked marker removed."""
    poisoned = dict(base)
    poisoned["locked_markers"] = dict(base["locked_markers"])
    poisoned["locked_markers"].pop(key, None)
    return poisoned


def test_r4_followup_manifest_rejects_url_stage_label_no_file(tmp_path: Path):
    """Codex test 1: URL-shaped stage_label is rejected before file write."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_run_metadata(
        _safe_base_manifest(),
        "stage21_2_stage_label",
        "https" + "://example.invalid/public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists(), (
        "R4-followup: unsafe stage_label must leave no file on disk"
    )


def test_r4_followup_manifest_rejects_bad_stage_label_no_file(tmp_path: Path):
    """Codex test 2: a non-locked stage_label literal is rejected."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_run_metadata(
        _safe_base_manifest(),
        "stage21_2_stage_label",
        "bad_stage",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_r4_followup_manifest_rejects_url_safe_for_public_dispatch_no_file(
    tmp_path: Path,
):
    """Codex test 3: URL-shaped safe_for_public_dispatch is rejected."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_run_metadata(
        _safe_base_manifest(),
        "safe_for_public_dispatch",
        "https" + "://example.invalid/public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_r4_followup_manifest_rejects_true_safe_for_public_dispatch_no_file(
    tmp_path: Path,
):
    """Codex test 4: True safe_for_public_dispatch is rejected by identity."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_run_metadata(
        _safe_base_manifest(),
        "safe_for_public_dispatch",
        True,
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_r4_followup_manifest_rejects_string_false_safe_for_public_dispatch_no_file(
    tmp_path: Path,
):
    """Codex test 5: the string ``"false"`` is rejected; only ``False`` passes."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_run_metadata(
        _safe_base_manifest(),
        "safe_for_public_dispatch",
        "false",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_r4_followup_manifest_valid_preserves_locked_invariants(tmp_path: Path):
    """Codex test 6: a valid manifest still writes the locked values unchanged."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    write_stage21_2_manifest(_safe_base_manifest(), target)
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["run_metadata"]["stage21_2_stage_label"] == "21.2"
    assert payload["run_metadata"]["safe_for_public_dispatch"] is False


def test_final_manifest_rejects_locked_markers_url_stage_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers.stage cannot hide behind marker exemption."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_locked_marker(
        _safe_base_manifest(),
        "stage",
        "https" + "://example.invalid/public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_final_manifest_rejects_locked_markers_url_dispatch_target_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers.dispatch_target is exact-value checked."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_locked_marker(
        _safe_base_manifest(),
        "dispatch_target",
        "https" + "://example.invalid/webhook",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_final_manifest_rejects_locked_markers_public_visibility_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers.visibility must remain private_preview."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_locked_marker(
        _safe_base_manifest(),
        "visibility",
        "public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_final_manifest_rejects_locked_markers_missing_dispatch_target_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers must carry every required marker key."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _drop_locked_marker(_safe_base_manifest(), "dispatch_target")
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_final_manifest_rejects_locked_markers_operator_only_false_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers.operator_only must be exactly True."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_locked_marker(
        _safe_base_manifest(),
        "operator_only",
        False,
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_final_manifest_rejects_locked_markers_live_mode_true_no_file(
    tmp_path: Path,
):
    """Manifest locked_markers.live_mode must be exactly False."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = _poison_locked_marker(
        _safe_base_manifest(),
        "live_mode",
        True,
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_final_manifest_valid_preserves_locked_markers(tmp_path: Path):
    """A valid manifest writes locked_markers unchanged."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    write_stage21_2_manifest(_safe_base_manifest(), target)
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    markers = payload["locked_markers"]
    assert markers["stage"] == "21.2"
    assert markers["visibility"] == "private_preview"
    assert markers["operator_only"] is True
    assert markers["live_mode"] is False
    assert markers["dispatch_target"] == "fake_private_transport"


def test_final_manifest_rejects_recursive_marker_key_bypass_no_file(
    tmp_path: Path,
):
    """Unrelated nested marker-key names are still scanned, not exempted."""
    target = tmp_path / STAGE21_2_MANIFEST_FILENAME
    poisoned = dict(_safe_base_manifest())
    poisoned["counts"] = dict(poisoned["counts"])
    poisoned["counts"]["nested"] = {
        "stage": "https" + "://example.invalid/public_dispatch",
    }
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_manifest(poisoned, target)
    assert exc.value.code == "E2153"
    assert not target.exists()


# ---------------------------------------------------------------------------
# Ping ledger writer R4-followup tests (Codex tests 7..11)
# ---------------------------------------------------------------------------
#
# Test 10 requires a payload whose ``public_summary()`` dict
# OMITS one of the marker keys. Since ``PrivatePreviewPingPayload``
# is a NamedTuple and always carries every marker attribute, the
# only way to construct such a row is via a subclass override of
# ``public_summary``. The subclass keeps ``isinstance(ping,
# PrivatePreviewPingPayload)`` True so the writer's first guard
# does not short-circuit.


class _PingMissingDispatchTargetMarker(PrivatePreviewPingPayload):
    """Test-only subclass: ``public_summary`` omits ``dispatch_target``."""

    def public_summary(self):
        d = dict(PrivatePreviewPingPayload.public_summary(self))
        d.pop("dispatch_target", None)
        return d


def test_r4_followup_ping_ledger_rejects_url_stage_marker_no_file(
    tmp_path: Path,
):
    """Codex test 7: ping with URL-shaped stage marker is rejected."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    poisoned = _payload(mint="FAKE_MINT_A")._replace(
        stage="https" + "://example.invalid/public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_ping_ledger([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists(), (
        "R4-followup: unsafe ping marker must leave no file on disk"
    )


def test_r4_followup_ping_ledger_rejects_url_dispatch_target_marker_no_file(
    tmp_path: Path,
):
    """Codex test 8: ping with URL-shaped dispatch_target marker is rejected."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    poisoned = _payload(mint="FAKE_MINT_A")._replace(
        dispatch_target="https" + "://example.invalid/webhook",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_ping_ledger([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_r4_followup_ping_ledger_rejects_public_dispatch_visibility_marker_no_file(
    tmp_path: Path,
):
    """Codex test 9: ping with public_dispatch visibility marker is rejected."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    poisoned = _payload(mint="FAKE_MINT_A")._replace(
        visibility="public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_ping_ledger([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_r4_followup_ping_ledger_rejects_missing_marker_no_file(tmp_path: Path):
    """Codex test 10: ping row missing one required marker is rejected."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    base = _payload(mint="FAKE_MINT_A")
    missing = _PingMissingDispatchTargetMarker(*base)
    assert isinstance(missing, PrivatePreviewPingPayload)
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_ping_ledger([missing], target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_r4_followup_ping_ledger_valid_preserves_marker_values(tmp_path: Path):
    """Codex test 11: a valid ping ledger writes the locked markers unchanged."""
    target = tmp_path / STAGE21_2_PING_LEDGER_FILENAME
    write_stage21_2_ping_ledger([_payload(mint="FAKE_MINT_A")], target)
    assert target.exists()
    line = target.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["stage"] == "21.2"
    assert record["visibility"] == "private_preview"
    assert record["operator_only"] is True
    assert record["live_mode"] is False
    assert record["dispatch_target"] == "fake_private_transport"


# ---------------------------------------------------------------------------
# Capture writer R4-followup tests (Codex tests 12..16)
# ---------------------------------------------------------------------------


class _CaptureMissingDispatchTargetMarker(FakeTransportCaptureRecord):
    """Test-only subclass: ``public_summary`` omits ``dispatch_target``."""

    def public_summary(self):
        d = dict(FakeTransportCaptureRecord.public_summary(self))
        d.pop("dispatch_target", None)
        return d


def _safe_first_capture(tmp_path: Path) -> FakeTransportCaptureRecord:
    """Return the first record from a fresh capture sequence."""
    return _captures(tmp_path)[0]


def test_r4_followup_capture_rejects_url_stage_marker_no_file(tmp_path: Path):
    """Codex test 12: capture with URL-shaped stage marker is rejected."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    poisoned = _safe_first_capture(tmp_path)._replace(
        stage="https" + "://example.invalid/public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_fake_transport_capture([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists(), (
        "R4-followup: unsafe capture marker must leave no file on disk"
    )


def test_r4_followup_capture_rejects_url_dispatch_target_marker_no_file(
    tmp_path: Path,
):
    """Codex test 13: capture with URL-shaped dispatch_target is rejected."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    poisoned = _safe_first_capture(tmp_path)._replace(
        dispatch_target="https" + "://example.invalid/webhook",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_fake_transport_capture([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_r4_followup_capture_rejects_public_dispatch_visibility_marker_no_file(
    tmp_path: Path,
):
    """Codex test 14: capture with public_dispatch visibility is rejected."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    poisoned = _safe_first_capture(tmp_path)._replace(
        visibility="public_dispatch",
    )
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_fake_transport_capture([poisoned], target)
    assert exc.value.code == "E2153"
    assert not target.exists()


def test_r4_followup_capture_rejects_missing_marker_no_file(tmp_path: Path):
    """Codex test 15: capture row missing one required marker is rejected."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    base = _safe_first_capture(tmp_path)
    missing = _CaptureMissingDispatchTargetMarker(*base)
    assert isinstance(missing, FakeTransportCaptureRecord)
    with pytest.raises(Stage21Error) as exc:
        write_stage21_2_fake_transport_capture([missing], target)
    assert exc.value.code == "E2152"
    assert not target.exists()


def test_r4_followup_capture_valid_preserves_marker_values(tmp_path: Path):
    """Codex test 16: a valid capture writes the locked markers unchanged."""
    target = tmp_path / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    write_stage21_2_fake_transport_capture(_captures(tmp_path), target)
    assert target.exists()
    encoded = target.read_text(encoding="utf-8")
    for line in encoded.splitlines():
        if not line:
            continue
        record = json.loads(line)
        assert record["stage"] == "21.2"
        assert record["visibility"] == "private_preview"
        assert record["operator_only"] is True
        assert record["live_mode"] is False
        assert record["dispatch_target"] == "fake_private_transport"
