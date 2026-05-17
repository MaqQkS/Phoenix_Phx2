"""Stage 21 core models tests."""

from __future__ import annotations

from PHX2.stage21.constants import (
    PRIVATE_PREVIEW_REQUIRED_TOKENS,
    SAFE_FOR_PUBLIC_DISPATCH,
    STAGE21_MINOR_VERSION,
    STAGE21_VERSION,
    ProviderModeName,
    SinkModeName,
)
from PHX2.stage21.models import (
    PrivatePreviewMarker,
    ProviderMode,
    SinkMode,
    Stage21RunId,
)


def test_stage21_run_id_of_factory_pins_version_axes():
    rid = Stage21RunId.of(
        run_id="abcd1234",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    assert rid.run_id == "abcd1234"
    assert rid.stage21_version == STAGE21_VERSION
    assert rid.stage21_minor_version == STAGE21_MINOR_VERSION
    assert rid.generated_at_utc_iso == "2026-05-17T12:00:00Z"


def test_provider_mode_fake_factory_returns_fake():
    pm = ProviderMode.fake()
    assert pm.name == ProviderModeName.FAKE


def test_sink_mode_fake_factory_returns_fake():
    sm = SinkMode.fake()
    assert sm.name == SinkModeName.FAKE


def test_private_preview_marker_locked_uses_constants():
    marker = PrivatePreviewMarker.locked()
    assert marker.banner_text == PRIVATE_PREVIEW_REQUIRED_TOKENS[0]
    assert marker.operator_only_text == PRIVATE_PREVIEW_REQUIRED_TOKENS[1]
    assert marker.do_not_forward_text == PRIVATE_PREVIEW_REQUIRED_TOKENS[2]
    assert marker.required_tokens == PRIVATE_PREVIEW_REQUIRED_TOKENS
    assert marker.safe_for_public_dispatch is False
    assert marker.safe_for_public_dispatch is SAFE_FOR_PUBLIC_DISPATCH


def test_private_preview_marker_required_tokens_includes_all_three_phrases():
    marker = PrivatePreviewMarker.locked()
    tokens = set(marker.required_tokens)
    assert "PHX2 PRIVATE PREVIEW" in tokens
    assert "OPERATOR ONLY" in tokens
    assert "DO NOT FORWARD AS PUBLIC SIGNAL" in tokens


def test_namedtuple_records_are_immutable():
    rid = Stage21RunId.of(
        run_id="abcd1234",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
    )
    # Replacing fields produces a new instance; the original is
    # unchanged.
    rid2 = rid._replace(run_id="other")
    assert rid.run_id == "abcd1234"
    assert rid2.run_id == "other"
