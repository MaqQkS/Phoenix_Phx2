"""Stage 30.5.2 compact migration runtime adapter unit tests.

Pins the Stage 30.5.2 offline runtime seam
(``stage30_5_compact_migration_runtime_adapter``):

  * ``resolve_migration_display_text(source, token_mint,
    observed_at_utc)`` returns the single safe closed-set ``Mig``
    display word (``Known`` / ``Unverified`` / ``Unknown``) for every
    source outcome, with source-availability dominance preserved from
    the Stage 30.5.1 projector (a non-PRESENT source_status degrades a
    ``KNOWN`` record to ``Unknown``; there is no ``Mig: Stale`` word).
  * ``Stage30_5_2MigrationDisplayResolver`` bundles a source and
    exposes ``resolve_display_text`` returning the same closed-set
    word.
  * The resolver / helper output vocabulary never leaves the three
    closed-set display words.

Fake / offline only. No live provider call, no Discord send, no
network, no env read, no filesystem write. Stdlib + pytest only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    STAGE30_5_2_MINOR_VERSION,
    Stage30_5_2MigrationDisplayResolver,
    resolve_migration_display_text,
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
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextRecord,
)


# ---------------------------------------------------------------------------
# Locked constants + fakes
# ---------------------------------------------------------------------------


_OBS_TS: str = "2026-05-29T00:00:00Z"
_TOKEN_MINT: str = "FakeMintPhx2NotWso1ForStage305_2Base58222222"


def _record(
    *,
    status: str,
    basis: str,
    source_status: str,
    source_reason: str,
    source_label: Optional[str] = "stage30_5_2_fake_migration",
) -> Stage30_5MigrationContextRecord:
    return Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label=None,
        migration_status=status,
        migration_basis=basis,
        migration_event_time_utc=None,
        migration_age_seconds=None,
        source_label=source_label,
        source_status=source_status,
        source_reason=source_reason,
        runtime_consumable=False,
        observed_at_utc=_OBS_TS,
    )


class _FakeMigrationSource:
    """Stage 30.5.1 source-protocol-compatible fake.

    Returns a caller-supplied record (or ``None``) on each
    ``read(token_mint, observed_at_utc)`` call, or raises when
    ``raises=True``.
    """

    def __init__(
        self,
        *,
        record: Optional[Stage30_5MigrationContextRecord] = None,
        raises: bool = False,
    ) -> None:
        self._record = record
        self._raises = raises
        self.call_count: int = 0
        self.last_token_mint: object = None
        self.last_observed_at_utc: object = None

    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        self.call_count += 1
        self.last_token_mint = token_mint
        self.last_observed_at_utc = observed_at_utc
        if self._raises:
            raise RuntimeError("fake migration source failure")
        return self._record


# ---------------------------------------------------------------------------
# 0. Version pin
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_5_2_MINOR_VERSION == "30.5.2"


# ---------------------------------------------------------------------------
# 1. PRESENT records project the status display word
# ---------------------------------------------------------------------------


def test_known_present_resolves_to_known() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_KNOWN
    assert result == "Known"
    assert source.call_count == 1
    assert source.last_token_mint == _TOKEN_MINT
    assert source.last_observed_at_utc == _OBS_TS


def test_unverified_present_resolves_to_unverified() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_UNVERIFIED,
            basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNVERIFIED
    assert result == "Unverified"


def test_unknown_unavailable_resolves_to_unknown() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_UNKNOWN,
            basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN
    assert result == "Unknown"


# ---------------------------------------------------------------------------
# 2. Source-availability dominance: a non-PRESENT source_status degrades
#    a KNOWN record to Unknown (no Mig: Stale display word)
# ---------------------------------------------------------------------------


def test_known_but_source_error_degrades_to_unknown() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_SOURCE_ERROR,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN
    assert result == "Unknown"


def test_known_but_source_stale_degrades_to_unknown_no_stale_word() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_STALE,
            source_reason=SOURCE_REASON_SOURCE_STALE,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN
    assert result == "Unknown"
    # There is no Mig: Stale display token.
    assert result != "Stale"
    assert "Stale" not in result


# ---------------------------------------------------------------------------
# 3. Source failures all degrade to Unknown
# ---------------------------------------------------------------------------


def test_source_returns_none_resolves_to_unknown() -> None:
    source = _FakeMigrationSource(record=None)
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN
    assert source.call_count == 1


def test_source_raises_resolves_to_unknown() -> None:
    source = _FakeMigrationSource(raises=True)
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN


def test_source_object_is_none_resolves_to_unknown() -> None:
    result = resolve_migration_display_text(None, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN


def test_source_missing_read_resolves_to_unknown() -> None:
    bogus_source = SimpleNamespace(not_read="nope")
    result = resolve_migration_display_text(
        bogus_source, _TOKEN_MINT, _OBS_TS
    )
    assert result == MIGRATION_DISPLAY_UNKNOWN


def test_off_closed_set_record_resolves_to_unknown() -> None:
    """A source that returns an object whose evidence fields are not all
    on the Stage 30.5.1 closed sets degrades to Unknown.
    """
    bogus_record = SimpleNamespace(
        migration_status="DEFINITELY_MIGRATED",
        migration_basis="TOTALLY_TRUSTED",
        source_status="SUPER_PRESENT",
        source_reason="ALL_GOOD",
        source_label="stage30_5_2_bogus",
    )
    source = _FakeMigrationSource(record=bogus_record)  # type: ignore[arg-type]
    result = resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN


def test_token_mint_not_str_resolves_to_unknown() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        ),
    )
    result = resolve_migration_display_text(source, 12345, _OBS_TS)
    assert result == MIGRATION_DISPLAY_UNKNOWN


def test_observed_at_utc_defaults_to_none() -> None:
    """``observed_at_utc`` is optional; omitting it still resolves."""
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        ),
    )
    result = resolve_migration_display_text(source, _TOKEN_MINT)
    assert result == MIGRATION_DISPLAY_KNOWN
    assert source.last_observed_at_utc is None


# ---------------------------------------------------------------------------
# 4. Stage30_5_2MigrationDisplayResolver wraps a source
# ---------------------------------------------------------------------------


def test_resolver_exposes_source() -> None:
    source = _FakeMigrationSource(record=None)
    resolver = Stage30_5_2MigrationDisplayResolver(source=source)
    assert resolver.source is source


def test_resolver_resolve_display_text_present_known() -> None:
    source = _FakeMigrationSource(
        record=_record(
            status=MIGRATION_STATUS_KNOWN,
            basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        ),
    )
    resolver = Stage30_5_2MigrationDisplayResolver(source=source)
    result = resolver.resolve_display_text(
        token_mint=_TOKEN_MINT,
        observed_at_utc=_OBS_TS,
    )
    assert result == "Known"
    assert source.call_count == 1
    assert source.last_token_mint == _TOKEN_MINT


def test_resolver_with_none_source_resolves_to_unknown() -> None:
    resolver = Stage30_5_2MigrationDisplayResolver(source=None)
    result = resolver.resolve_display_text(
        token_mint=_TOKEN_MINT,
        observed_at_utc=_OBS_TS,
    )
    assert result == "Unknown"


def test_resolver_raising_source_resolves_to_unknown() -> None:
    resolver = Stage30_5_2MigrationDisplayResolver(
        source=_FakeMigrationSource(raises=True),
    )
    result = resolver.resolve_display_text(
        token_mint=_TOKEN_MINT,
        observed_at_utc=_OBS_TS,
    )
    assert result == "Unknown"


# ---------------------------------------------------------------------------
# 5. Display vocabulary never leaves the three closed-set words
# ---------------------------------------------------------------------------


def test_display_vocabulary_is_closed_set_across_matrix() -> None:
    """Every source outcome resolves to one of exactly three closed-set
    display words; the runtime adapter never invents a Fresh / Stale /
    ATH / Net word.
    """
    matrix = [
        _FakeMigrationSource(
            record=_record(
                status=MIGRATION_STATUS_KNOWN,
                basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
                source_status=SOURCE_STATUS_PRESENT,
                source_reason=SOURCE_REASON_SOURCE_PRESENT,
            ),
        ),
        _FakeMigrationSource(
            record=_record(
                status=MIGRATION_STATUS_UNVERIFIED,
                basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
                source_status=SOURCE_STATUS_PRESENT,
                source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
            ),
        ),
        _FakeMigrationSource(
            record=_record(
                status=MIGRATION_STATUS_KNOWN,
                basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
                source_status=SOURCE_STATUS_ERROR,
                source_reason=SOURCE_REASON_SOURCE_ERROR,
            ),
        ),
        _FakeMigrationSource(
            record=_record(
                status=MIGRATION_STATUS_KNOWN,
                basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
                source_status=SOURCE_STATUS_STALE,
                source_reason=SOURCE_REASON_SOURCE_STALE,
            ),
        ),
        _FakeMigrationSource(record=None),
        _FakeMigrationSource(raises=True),
    ]
    observed = set()
    for source in matrix:
        observed.add(
            resolve_migration_display_text(source, _TOKEN_MINT, _OBS_TS)
        )
    observed.add(resolve_migration_display_text(None, _TOKEN_MINT, _OBS_TS))
    assert observed <= set(MIGRATION_DISPLAY_VALUES)
    assert observed <= {"Known", "Unverified", "Unknown"}
    # The forbidden Fresh / Stale words never appear.
    assert "Fresh" not in observed
    assert "Stale" not in observed
