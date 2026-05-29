"""Stage 30.5.1 migration-context adapter / projector tests.

A fake source drives every adapter path: a valid KNOWN / UNVERIFIED
/ UNKNOWN record, a ``None`` source, a ``None`` read, a raising
source, a malformed-evidence object, and an unusable token. No live
network, no env, no Discord, no provider call.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from PHX2.stage30.stage30_5_migration_context_adapter import (
    project_migration_context,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_DISPLAY_KNOWN,
    MIGRATION_DISPLAY_UNKNOWN,
    MIGRATION_DISPLAY_UNVERIFIED,
    MIGRATION_DISPLAY_VALUES,
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNKNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextProjection,
    Stage30_5MigrationContextRecord,
)


_VALID_TS: str = "2026-05-29T00:02:00Z"
_EVENT_TS: str = "2026-05-29T00:00:00Z"
_MINT: str = "So11111111111111111111111111111111111111112"


# ---------------------------------------------------------------------------
# Record builders + fake sources
# ---------------------------------------------------------------------------


def _record(
    *,
    migration_status: str,
    migration_basis: str,
    source_status: str,
    source_reason: str,
    source_label: Optional[str] = "stage29_5_migration_evidence",
    migration_event_time_utc: Optional[str] = _EVENT_TS,
    migration_age_seconds: Optional[int] = 120,
) -> Stage30_5MigrationContextRecord:
    return Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label="ABcd...WXyz",
        migration_status=migration_status,
        migration_basis=migration_basis,
        migration_event_time_utc=migration_event_time_utc,
        migration_age_seconds=migration_age_seconds,
        source_label=source_label,
        source_status=source_status,
        source_reason=source_reason,
        runtime_consumable=False,
        observed_at_utc=_VALID_TS,
    )


class _FakeRecordSource:
    def __init__(
        self, record: Optional[Stage30_5MigrationContextRecord]
    ) -> None:
        self._record = record
        self.reads: list = []

    def read(
        self, token_mint: str, observed_at_utc: Optional[str] = None
    ) -> Optional[Stage30_5MigrationContextRecord]:
        self.reads.append((token_mint, observed_at_utc))
        return self._record


class _RaisingSource:
    def read(
        self, token_mint: str, observed_at_utc: Optional[str] = None
    ) -> Optional[Stage30_5MigrationContextRecord]:
        raise RuntimeError(
            "LEAKSENTINELRAWPROVIDERERROR_with_secret_value"
        )


class _BogusEvidence:
    """A duck-typed object carrying off-closed-set evidence."""

    migration_status = "BOGUS"
    migration_basis = "WHATEVER"
    source_status = "MISSING"
    source_reason = "AMBIGUOUS_EVIDENCE"
    source_label = "stage29_5_migration_evidence"


class _BogusSource:
    def read(
        self, token_mint: str, observed_at_utc: Optional[str] = None
    ) -> object:
        return _BogusEvidence()


class _NoReadSource:
    pass


# ---------------------------------------------------------------------------
# KNOWN / UNVERIFIED / UNKNOWN -> display words
# ---------------------------------------------------------------------------


def test_known_record_renders_known() -> None:
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )
    )
    proj = project_migration_context(source, _MINT, _VALID_TS)
    assert proj.migration_display_text == MIGRATION_DISPLAY_KNOWN
    assert proj.migration_status == MIGRATION_STATUS_KNOWN
    assert proj.migration_basis == MIGRATION_BASIS_ON_CHAIN_EVENT
    assert proj.source_status == SOURCE_STATUS_PRESENT
    assert proj.source_reason == SOURCE_REASON_SOURCE_PRESENT
    assert proj.source_label == "stage29_5_migration_evidence"
    assert proj.runtime_consumable is False
    # observed_at_utc is forwarded to the source read.
    assert source.reads == [(_MINT, _VALID_TS)]


def test_unverified_record_renders_unverified() -> None:
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_UNVERIFIED,
            migration_basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNVERIFIED
    assert proj.migration_status == MIGRATION_STATUS_UNVERIFIED
    assert proj.migration_basis == MIGRATION_BASIS_EVIDENCE_PARTIAL


def test_unknown_record_renders_unknown() -> None:
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
            source_label=None,
            migration_event_time_utc=None,
            migration_age_seconds=None,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE


# ---------------------------------------------------------------------------
# Degraded paths -> Unknown
# ---------------------------------------------------------------------------


def test_none_source_renders_unknown_not_configured() -> None:
    proj = project_migration_context(None, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE
    assert proj.source_status == SOURCE_STATUS_UNAVAILABLE
    assert proj.source_reason == SOURCE_REASON_SOURCE_NOT_CONFIGURED
    assert proj.source_label is None
    assert proj.runtime_consumable is False


def test_none_read_renders_unknown_unavailable() -> None:
    source = _FakeRecordSource(None)
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_UNAVAILABLE
    assert proj.source_reason == SOURCE_REASON_SOURCE_UNAVAILABLE


def test_raising_source_renders_unknown_error_without_leak() -> None:
    proj = project_migration_context(_RaisingSource(), _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_ERROR
    assert proj.source_reason == SOURCE_REASON_SOURCE_ERROR
    # The raw exception text must NEVER reach the projection.
    rep = repr(proj)
    assert "LEAKSENTINELRAWPROVIDERERROR" not in rep
    for value in dataclasses.astuple(proj):
        if isinstance(value, str):
            assert "LEAKSENTINELRAWPROVIDERERROR" not in value


def test_bogus_evidence_renders_unknown_evidence_invalid() -> None:
    proj = project_migration_context(_BogusSource(), _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE
    assert proj.source_status == SOURCE_STATUS_ERROR
    assert proj.source_reason == SOURCE_REASON_EVIDENCE_INVALID
    # A safe source label is still preserved through the invalid path.
    assert proj.source_label == "stage29_5_migration_evidence"


def test_stale_record_renders_unknown_with_stale_provenance() -> None:
    """A STALE source_status conservatively projects to Mig: Unknown
    even when the underlying migration_status was KNOWN. There is no
    Mig: Stale display token; the stale provenance is preserved on
    source_status / source_reason only.
    """
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_STALE,
            source_reason=SOURCE_REASON_SOURCE_STALE,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE
    assert proj.source_status == SOURCE_STATUS_STALE
    assert proj.source_reason == SOURCE_REASON_SOURCE_STALE
    # A safe source label is preserved through the stale path.
    assert proj.source_label == "stage29_5_migration_evidence"
    assert proj.runtime_consumable is False
    # No Mig: Stale display token is ever emitted.
    assert proj.migration_display_text != "Stale"
    assert proj.migration_display_text in MIGRATION_DISPLAY_VALUES


def test_stale_record_with_unverified_status_also_unknown() -> None:
    """Stale degradation does not depend on the underlying status:
    a STALE reading whose migration_status was UNVERIFIED also
    projects to Unknown.
    """
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_UNVERIFIED,
            migration_basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_STALE,
            source_reason=SOURCE_REASON_SOURCE_STALE,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_STALE
    assert proj.source_reason == SOURCE_REASON_SOURCE_STALE


# ---------------------------------------------------------------------------
# Source-availability dominance: only PRESENT may project a status word
# ---------------------------------------------------------------------------


def test_error_source_with_known_status_renders_unknown() -> None:
    """source_status=ERROR dominates a KNOWN migration_status and
    degrades the projection to Mig: Unknown (Codex finding).
    """
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_EVIDENCE_INVALID,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE
    # Original source provenance preserved.
    assert proj.source_status == SOURCE_STATUS_ERROR
    assert proj.source_reason == SOURCE_REASON_EVIDENCE_INVALID
    assert proj.runtime_consumable is False


def test_unavailable_source_with_known_status_renders_unknown() -> None:
    """source_status=UNAVAILABLE dominates a KNOWN migration_status
    and degrades the projection to Mig: Unknown (Codex finding).
    """
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.migration_basis == MIGRATION_BASIS_NONE
    assert proj.source_status == SOURCE_STATUS_UNAVAILABLE
    assert proj.source_reason == SOURCE_REASON_SOURCE_UNAVAILABLE
    assert proj.runtime_consumable is False


def test_present_source_unknown_status_renders_unknown() -> None:
    """PRESENT + UNKNOWN -> Unknown (via the PRESENT echo path)."""
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )
    )
    proj = project_migration_context(source, _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.migration_status == MIGRATION_STATUS_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_PRESENT


def test_every_projection_runtime_consumable_false() -> None:
    """Every projection the adapter emits is runtime_consumable False,
    across PRESENT, degraded, and no-record paths.
    """
    present = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )
    )
    for proj in (
        project_migration_context(None, _MINT),
        project_migration_context(_FakeRecordSource(None), _MINT),
        project_migration_context(_RaisingSource(), _MINT),
        project_migration_context(_BogusSource(), _MINT),
        project_migration_context(present, _MINT),
    ):
        assert proj.runtime_consumable is False


def test_non_str_token_renders_unknown() -> None:
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )
    )
    proj = project_migration_context(source, 12345)  # type: ignore[arg-type]
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_UNAVAILABLE
    assert proj.source_reason == SOURCE_REASON_SOURCE_UNAVAILABLE
    # The source's read must NOT have been called for an unusable token.
    assert source.reads == []


def test_source_without_read_renders_unknown_error() -> None:
    proj = project_migration_context(_NoReadSource(), _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_UNKNOWN
    assert proj.source_status == SOURCE_STATUS_ERROR
    assert proj.source_reason == SOURCE_REASON_SOURCE_ERROR


# ---------------------------------------------------------------------------
# Source label preservation
# ---------------------------------------------------------------------------


def test_safe_source_label_preserved_unsafe_coerced_none() -> None:
    safe = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
            source_label="stage29_5_migration_evidence",
        )
    )
    assert (
        project_migration_context(safe, _MINT).source_label
        == "stage29_5_migration_evidence"
    )

    # A duck-typed object whose evidence is valid but whose source
    # label is unsafe-shape: the adapter coerces the label to None.
    class _UnsafeLabelEvidence:
        migration_status = MIGRATION_STATUS_KNOWN
        migration_basis = MIGRATION_BASIS_ON_CHAIN_EVENT
        source_status = SOURCE_STATUS_PRESENT
        source_reason = SOURCE_REASON_SOURCE_PRESENT
        source_label = "has space and / slash"

    class _UnsafeLabelSource:
        def read(self, token_mint, observed_at_utc=None):
            return _UnsafeLabelEvidence()

    proj = project_migration_context(_UnsafeLabelSource(), _MINT)
    assert proj.migration_display_text == MIGRATION_DISPLAY_KNOWN
    assert proj.source_label is None


# ---------------------------------------------------------------------------
# Projection invariants: type, no Fresh/Stale, no age/time/ATH/Net,
# runtime_consumable always False
# ---------------------------------------------------------------------------


def test_projection_type_and_display_closed_set() -> None:
    for record in (
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        ),
        _record(
            migration_status=MIGRATION_STATUS_UNVERIFIED,
            migration_basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
        ),
        _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
            source_label=None,
            migration_event_time_utc=None,
            migration_age_seconds=None,
        ),
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_STALE,
            source_reason=SOURCE_REASON_SOURCE_STALE,
        ),
    ):
        proj = project_migration_context(
            _FakeRecordSource(record), _MINT
        )
        assert isinstance(proj, Stage30_5MigrationContextProjection)
        # Only the three closed-set display words ever appear.
        assert proj.migration_display_text in MIGRATION_DISPLAY_VALUES
        # No Fresh / Stale anywhere.
        assert proj.migration_display_text not in ("Fresh", "Stale")
        assert proj.runtime_consumable is False


def test_projection_has_no_age_time_ath_or_net_fields() -> None:
    field_names = {
        f.name
        for f in dataclasses.fields(Stage30_5MigrationContextProjection)
    }
    joined = " ".join(field_names).lower()
    assert "age" not in joined
    assert "event_time" not in joined  # bare "time" would collide with runtime_consumable
    assert "ath" not in joined
    assert "net" not in joined
    # Migration age / time are carried on the record (provenance) but
    # never projected into the compact Mig token.
    assert "migration_age_seconds" not in field_names
    assert "migration_event_time_utc" not in field_names


def test_age_and_event_time_not_displayed() -> None:
    """A record with a populated age / event time must not surface
    either value anywhere on the projection.
    """
    source = _FakeRecordSource(
        _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
            migration_event_time_utc=_EVENT_TS,
            migration_age_seconds=987654,
        )
    )
    proj = project_migration_context(source, _MINT)
    rep = repr(proj)
    assert "987654" not in rep
    assert _EVENT_TS not in rep
