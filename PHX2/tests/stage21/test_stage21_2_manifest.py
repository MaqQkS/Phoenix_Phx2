"""Stage 21.2 manifest assembler tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.constants import STAGE21_VERSION
from PHX2.stage21.ping_payloads import (
    FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
    LIVE_MODE_MARKER,
    NORMALIZED_EVENT_SCHEMA_VERSION,
    OPERATOR_ONLY_MARKER,
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
    PING_PAYLOAD_REQUIRED_MARKER_VALUES,
    PING_PAYLOAD_SCHEMA_VERSION,
    PRIVATE_PREVIEW_VISIBILITY,
    PrivatePreviewCandidate,
    PrivatePreviewPingPayload,
    STAGE21_2_STAGE_LABEL,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
    STAGE21_FAKE_SOURCE_KIND,
)
from PHX2.stage21.errors import Stage21Error
from PHX2.stage21.stage21_2_manifest import (
    Stage21_2SimulationCounts,
    assemble_stage21_2_manifest,
)


def _counts() -> Stage21_2SimulationCounts:
    return Stage21_2SimulationCounts(
        fake_events_received=3,
        normalized_events_emitted=3,
        candidates_built=3,
        pings_built=3,
        captures_recorded=3,
        duplicates_skipped=0,
    )


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


def test_stage21_2_stage_label_is_locked():
    assert STAGE21_2_STAGE_LABEL == "21.2"


def test_private_preview_visibility_is_locked():
    assert PRIVATE_PREVIEW_VISIBILITY == "private_preview"


def test_operator_only_marker_is_python_true():
    assert OPERATOR_ONLY_MARKER is True


def test_live_mode_marker_is_python_false():
    assert LIVE_MODE_MARKER is False


def test_fake_private_transport_dispatch_target_is_locked():
    assert FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET == "fake_private_transport"


def test_schema_versions_are_locked():
    assert NORMALIZED_EVENT_SCHEMA_VERSION == "stage21_2_normalized_event_v0"
    assert PING_PAYLOAD_SCHEMA_VERSION == "stage21_2_ping_payload_v0"


def test_required_marker_keys_match_marker_values_keys():
    assert (
        set(PING_PAYLOAD_REQUIRED_MARKER_KEYS)
        == set(PING_PAYLOAD_REQUIRED_MARKER_VALUES.keys())
    )


def test_required_marker_values_are_locked_at_known_constants():
    assert PING_PAYLOAD_REQUIRED_MARKER_VALUES["stage"] == STAGE21_2_STAGE_LABEL
    assert (
        PING_PAYLOAD_REQUIRED_MARKER_VALUES["visibility"]
        == PRIVATE_PREVIEW_VISIBILITY
    )
    assert (
        PING_PAYLOAD_REQUIRED_MARKER_VALUES["operator_only"]
        is OPERATOR_ONLY_MARKER
    )
    assert PING_PAYLOAD_REQUIRED_MARKER_VALUES["live_mode"] is LIVE_MODE_MARKER
    assert (
        PING_PAYLOAD_REQUIRED_MARKER_VALUES["dispatch_target"]
        == FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET
    )


def test_fake_provider_name_chain_and_source_kind_are_locked():
    assert STAGE21_FAKE_PROVIDER_NAME == "stage21_fake_provider"
    assert STAGE21_FAKE_CHAIN_NAME == "stage21_fake_chain"
    assert STAGE21_FAKE_SOURCE_KIND == "stage21_fake_source"


# ---------------------------------------------------------------------------
# Record shape tests
# ---------------------------------------------------------------------------


def test_candidate_namedtuple_has_required_fields():
    expected = {
        "candidate_id",
        "normalized_event_id",
        "mint",
        "event_type",
        "observed_at_utc",
        "reason",
        "source",
    }
    assert set(PrivatePreviewCandidate._fields) == expected


def test_ping_payload_namedtuple_carries_required_marker_fields():
    fields = set(PrivatePreviewPingPayload._fields)
    for marker in PING_PAYLOAD_REQUIRED_MARKER_KEYS:
        assert marker in fields
    # Spec-required minimum payload fields.
    required = {
        "ping_id",
        "stage",
        "visibility",
        "operator_only",
        "live_mode",
        "dispatch_target",
        "candidate_id",
        "normalized_event_id",
        "mint",
        "event_type",
        "observed_at_utc",
        "summary_text",
        "body_text",
        "structured_payload",
        "payload_hash",
    }
    assert required.issubset(fields)


# ---------------------------------------------------------------------------
# Manifest assembler
# ---------------------------------------------------------------------------


def test_assemble_returns_mapping_with_required_top_level_keys():
    out = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    assert isinstance(out, dict)
    required = {
        "run_metadata",
        "locked_markers",
        "fake_provider",
        "schema_versions",
        "counts",
    }
    assert required.issubset(set(out.keys()))


def test_assemble_carries_locked_safe_for_public_dispatch_false():
    out = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    assert out["run_metadata"]["safe_for_public_dispatch"] is False


def test_assemble_carries_stage21_version():
    out = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    assert out["run_metadata"]["stage21_version"] == STAGE21_VERSION


def test_assemble_carries_locked_markers_block():
    out = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    markers = out["locked_markers"]
    assert markers["stage"] == "21.2"
    assert markers["visibility"] == "private_preview"
    assert markers["operator_only"] is True
    assert markers["live_mode"] is False
    assert markers["dispatch_target"] == "fake_private_transport"


def test_assemble_is_pure_function():
    a = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    b = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    assert a == b


def test_assemble_rejects_empty_run_id():
    with pytest.raises(ValueError):
        assemble_stage21_2_manifest(
            run_id="",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            counts=_counts(),
        )


def test_assemble_rejects_empty_generated_at_utc_iso():
    with pytest.raises(ValueError):
        assemble_stage21_2_manifest(
            run_id="rid",
            generated_at_utc_iso="",
            counts=_counts(),
        )


def test_assemble_rejects_non_counts_input():
    with pytest.raises(ValueError):
        assemble_stage21_2_manifest(
            run_id="rid",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            counts={"fake_events_received": 0},  # type: ignore[arg-type]
        )


def test_assemble_counts_block_carries_all_six_fields():
    out = assemble_stage21_2_manifest(
        run_id="rid",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    required = {
        "fake_events_received",
        "normalized_events_emitted",
        "candidates_built",
        "pings_built",
        "captures_recorded",
        "duplicates_skipped",
    }
    assert set(out["counts"].keys()) == required


# ---------------------------------------------------------------------------
# Stage 21.2 remediation: Codex PoC #1 reproduction
# ---------------------------------------------------------------------------


def test_codex_poc_1_run_id_with_url_rejected_at_manifest():
    """Codex PoC #1: assemble_stage21_2_manifest rejects URL-laced run_id.

    The Stage 21.2 Codex audit produced a manifest artifact
    containing a URL value with a routing token in its path. The
    remediation wires the shared safe_content predicate into the
    manifest assembler at R11f so a URL-shaped run_id raises
    ``Stage21Error`` ``E2153`` before any manifest dict is
    constructed.
    """
    poisoned_run_id = "https" + "://example.invalid/public_dispatch"
    with pytest.raises(Stage21Error) as exc:
        assemble_stage21_2_manifest(
            run_id=poisoned_run_id,
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            counts=_counts(),
        )
    assert exc.value.code == "E2153", (
        f"Codex PoC #1 expected E2153 (forbidden_substring); "
        f"got {exc.value.code}"
    )


def test_assemble_rejects_url_generated_at_utc_iso():
    """Defense-in-depth: a URL-shaped timestamp is rejected too."""
    bad_ts = "https" + "://attacker.example/leak"
    with pytest.raises(Stage21Error) as exc:
        assemble_stage21_2_manifest(
            run_id="stage21_2_test_run",
            generated_at_utc_iso=bad_ts,
            counts=_counts(),
        )
    # The timestamp handler runs the forbidden-substring scan
    # alongside the RFC3339 regex; either path is fail-closed.
    assert exc.value.code in ("E2152", "E2153")


def test_assemble_rejects_run_id_with_disallowed_chars():
    """SHORT_IDENTIFIER rejects disallowed chars (E2152)."""
    with pytest.raises(Stage21Error) as exc:
        assemble_stage21_2_manifest(
            run_id="has space",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            counts=_counts(),
        )
    assert exc.value.code == "E2152"


def test_assemble_accepts_legitimate_inputs_unchanged():
    """Sanity: standard valid inputs still succeed."""
    out = assemble_stage21_2_manifest(
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        counts=_counts(),
    )
    assert out["run_metadata"]["run_id"] == "stage21_2_test_run"
