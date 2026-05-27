"""Stage 29.5.4 migration context source adapter behavior matrix.

Pins:

  * Constructor validates caller-shape (callable providers +
    callable clock + str-or-None windowing kwargs).
  * ``read_migration_snapshot`` returns a Stage 27.4
    ``MigrationSourceSnapshot`` for every input -- NEVER raises.
  * COMPLETE + HELIUS_WS / STAGE29_MIGRATION_ARTIFACT + non-None
    timestamp -> populated snapshot with
    ``migration_source = ON_CHAIN_MIGRATION_EVENT``.
  * COMPLETE + SYNTHETIC_TEST_ONLY -> ``MIGRATION_SOURCE_UNKNOWN``
    snapshot (no spurious authority promotion).
  * COMPLETE + UNKNOWN -> ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
  * PARTIAL / MISSING / INVALID / CONFLICTING ->
    ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
  * Deterministic: identical inputs produce identical snapshots.
  * Per-mint isolation: different ``token_mint`` calls produce
    independent results.
  * Provider exceptions degrade to UNKNOWN snapshot.
  * Clock returning malformed string degrades to UNKNOWN snapshot.
  * Unsafe ``token_mint`` shape degrades to UNKNOWN snapshot.
  * ``migration_event_id`` + ``source_event_ref`` echoed from
    first matched evidence (deterministic order).
  * ``raw_capture_ref`` is always None.

All tests use synthetic in-memory fixtures only. No live network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional, Sequence

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_SOURCE_UNKNOWN,
)
from PHX2.stage27.pair_detection_constants import (
    PAIR_TYPE_PUMP_SOL,
    QUOTE_ASSET_SOL,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_UNIT_SOL,
    AthContextRecord,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_5_4_migration_context_source_adapter import (
    STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION,
    Stage29_5_4MigrationContextSourceAdapter,
)
from PHX2.stage29.stage29_5_migration_models import (
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Test fixtures (synthetic, safe-shape)
# ---------------------------------------------------------------------------


_BASE_MINT: str = "BaseMintAAAA" + "A" * 32  # length 44 safe-shape
_BASE_MINT_OTHER: str = (
    "OtherMintBBB" + "B" * 32
)  # length 44 safe-shape
_POOL_ACCOUNT: str = "PoolAccountCC" + "C" * 31
_POOL_PROGRAM_ID: str = "PoolProgramDDD" + "D" * 30
_QUOTE_MINT: str = "QuoteMintEEEE" + "E" * 31
_TS_MIGRATION: str = "2026-01-01T00:00:00+00:00"
_TS_OBSERVED: str = "2026-01-01T00:00:01+00:00"
_TS_ATH: str = "2026-01-02T00:00:00+00:00"  # strictly post-migration
_TS_CLOCK: str = "2026-01-02T00:00:01+00:00"
_MIGRATION_SLOT: int = 12345
_MIGRATION_SIGNATURE: str = "sig_abcdef_1234567890"
_SOURCE_EVENT_REF: str = "evt_ref_safe"


def _ath_context(
    *,
    token_mint: str = _BASE_MINT,
) -> AthContextRecord:
    """Synthetic Stage 27.4 ATH context record that satisfies
    every Stage 29.5 projection COMPLETE-gate predicate:

      * ath_status == PRESENT,
      * ath_value non-None,
      * token_mint matches the candidate base_mint,
      * ath_since_migration_status == POST_MIGRATION_ONLY,
      * ath_observed_at_utc is strictly after _TS_MIGRATION.
    """
    return AthContextRecord(
        token_mint=token_mint,
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        ath_value="0.000054",
        ath_unit=ATH_UNIT_SOL,
        ath_source="stage29_5_4_test_fixture",
        ath_observed_at_utc=_TS_ATH,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_from_ath="0.3333333333",
        drawdown_unit=ATH_UNIT_SOL,
        drawdown_basis=(
            DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
        ),
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _present_evidence(
    *,
    base_mint: str = _BASE_MINT,
    migration_source: str = MIGRATION_SOURCE_HELIUS_WS,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=migration_source,
        base_mint=base_mint,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_TS_MIGRATION,
        migration_slot=_MIGRATION_SLOT,
        migration_signature=_MIGRATION_SIGNATURE,
        observed_at_utc=_TS_OBSERVED,
        source_event_ref=_SOURCE_EVENT_REF,
    )


def _missing_evidence() -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_TS_OBSERVED,
        source_event_ref=None,
    )


def _empty_evidence_provider(
    token_mint: str,
) -> Sequence[Stage29_5MigrationEvidenceRecord]:
    return ()


def _no_ath_provider(token_mint: str):
    return None


def _fixed_clock() -> str:
    return _TS_CLOCK


def _build_adapter(
    *,
    evidence,
    ath_provider=None,
    time_window_start_utc: Optional[str] = None,
    time_window_end_utc: Optional[str] = None,
) -> Stage29_5_4MigrationContextSourceAdapter:
    return Stage29_5_4MigrationContextSourceAdapter(
        evidence_provider=evidence,
        ath_context_provider=(
            ath_provider
            if ath_provider is not None
            else _no_ath_provider
        ),
        clock=_fixed_clock,
        time_window_start_utc=time_window_start_utc,
        time_window_end_utc=time_window_end_utc,
    )


# ---------------------------------------------------------------------------
# Constructor caller-shape validation
# ---------------------------------------------------------------------------


def test_constructor_rejects_non_callable_evidence_provider() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider="not_callable",  # type: ignore[arg-type]
            ath_context_provider=_no_ath_provider,
            clock=_fixed_clock,
        )


def test_constructor_rejects_non_callable_ath_provider() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider=_empty_evidence_provider,
            ath_context_provider="not_callable",  # type: ignore[arg-type]
            clock=_fixed_clock,
        )


def test_constructor_rejects_non_callable_clock() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider=_empty_evidence_provider,
            ath_context_provider=_no_ath_provider,
            clock="not_callable",  # type: ignore[arg-type]
        )


def test_constructor_rejects_non_str_time_window_start_utc() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider=_empty_evidence_provider,
            ath_context_provider=_no_ath_provider,
            clock=_fixed_clock,
            time_window_start_utc=42,  # type: ignore[arg-type]
        )


def test_constructor_rejects_non_str_time_window_end_utc() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider=_empty_evidence_provider,
            ath_context_provider=_no_ath_provider,
            clock=_fixed_clock,
            time_window_end_utc=42,  # type: ignore[arg-type]
        )


def test_constructor_rejects_non_str_expected_pool_program_id() -> None:
    with pytest.raises(TypeError):
        Stage29_5_4MigrationContextSourceAdapter(
            evidence_provider=_empty_evidence_provider,
            ath_context_provider=_no_ath_provider,
            clock=_fixed_clock,
            expected_pool_program_id=42,  # type: ignore[arg-type]
        )


def test_constructor_accepts_minimal_valid_args() -> None:
    adapter = _build_adapter(
        evidence=_empty_evidence_provider,
    )
    assert isinstance(
        adapter, Stage29_5_4MigrationContextSourceAdapter
    )


# ---------------------------------------------------------------------------
# read_migration_snapshot always returns a MigrationSourceSnapshot
# ---------------------------------------------------------------------------


def test_read_migration_snapshot_returns_snapshot_type() -> None:
    adapter = _build_adapter(
        evidence=_empty_evidence_provider,
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert isinstance(snapshot, MigrationSourceSnapshot)


# ---------------------------------------------------------------------------
# COMPLETE branch: HELIUS_WS evidence -> populated snapshot
# ---------------------------------------------------------------------------


def test_complete_with_helius_ws_evidence_produces_populated_snapshot() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
            ),
        ],
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
    )
    assert snapshot.migration_timestamp_utc == _TS_MIGRATION
    assert snapshot.migration_event_id == _MIGRATION_SIGNATURE
    assert snapshot.source_event_ref == _SOURCE_EVENT_REF
    assert snapshot.raw_capture_ref is None


def test_complete_with_stage29_migration_artifact_evidence_produces_populated_snapshot() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=(
                    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
                ),
            ),
        ],
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
    )
    assert snapshot.migration_timestamp_utc == _TS_MIGRATION
    assert snapshot.migration_event_id == _MIGRATION_SIGNATURE
    assert snapshot.source_event_ref == _SOURCE_EVENT_REF
    assert snapshot.raw_capture_ref is None


# ---------------------------------------------------------------------------
# COMPLETE branch with NOT-trusted source -> UNKNOWN
# ---------------------------------------------------------------------------


def test_complete_with_synthetic_test_only_degrades_to_unknown() -> None:
    """Stage 29.5.2 synthetic fixtures emit
    migration_source=SYNTHETIC_TEST_ONLY. Even when the
    Stage 29.5 projection emits COMPLETE on a synthetic input
    (all 8 COMPLETE-gate predicates satisfied including ATH
    context wired post-migration), the adapter MUST NOT surface
    a populated authoritative snapshot -- the synthetic source
    has no on-chain provenance.
    """
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=(
                    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
                ),
            ),
        ],
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None


# ---------------------------------------------------------------------------
# Missing / partial / invalid / conflicting -> UNKNOWN
# ---------------------------------------------------------------------------


def test_missing_evidence_degrades_to_unknown() -> None:
    """When the evidence sequence projects to MISSING_MIGRATION
    (no matching evidence record), the adapter returns the
    canonical UNKNOWN snapshot.
    """
    adapter = _build_adapter(
        evidence=_empty_evidence_provider,
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None


def test_no_match_for_base_mint_degrades_to_unknown() -> None:
    """When the evidence sequence is non-empty but contains no
    record matching the queried base_mint, the join layer emits
    NO_MATCH and the projection emits MISSING_MIGRATION -- the
    adapter degrades to UNKNOWN.
    """
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                base_mint=_BASE_MINT_OTHER,
            ),
        ],
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Deterministic
# ---------------------------------------------------------------------------


def test_adapter_is_deterministic() -> None:
    """Identical inputs (same provider results, same clock)
    produce identical snapshots across repeated calls.
    """
    evidence_list = [
        _present_evidence(
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
        ),
    ]
    adapter = _build_adapter(
        evidence=lambda token_mint: list(evidence_list),
    )
    s1 = adapter.read_migration_snapshot(_BASE_MINT)
    s2 = adapter.read_migration_snapshot(_BASE_MINT)
    s3 = adapter.read_migration_snapshot(_BASE_MINT)
    assert s1 == s2 == s3


# ---------------------------------------------------------------------------
# Per-mint isolation
# ---------------------------------------------------------------------------


def test_different_mints_produce_independent_results() -> None:
    """The adapter must call the evidence provider with each
    distinct token_mint and use that mint's record set to drive
    the projection. Two different mints yield independent
    snapshots.
    """

    def evidence_for(token_mint):
        if token_mint == _BASE_MINT:
            return [
                _present_evidence(
                    base_mint=_BASE_MINT,
                    migration_source=(
                        MIGRATION_SOURCE_HELIUS_WS
                    ),
                ),
            ]
        return []

    adapter = _build_adapter(
        evidence=evidence_for,
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot_present = adapter.read_migration_snapshot(
        _BASE_MINT,
    )
    snapshot_missing = adapter.read_migration_snapshot(
        _BASE_MINT_OTHER,
    )
    assert (
        snapshot_present.migration_source
        == MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
    )
    assert (
        snapshot_missing.migration_source
        == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Exception swallowing -> UNKNOWN
# ---------------------------------------------------------------------------


def test_evidence_provider_raises_degrades_to_unknown() -> None:
    def raising_provider(token_mint):
        raise RuntimeError(
            "synthetic provider failure"
        )

    adapter = _build_adapter(evidence=raising_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_timestamp_utc is None


def test_ath_provider_raises_degrades_to_unknown() -> None:
    def raising_ath_provider(token_mint):
        raise RuntimeError(
            "synthetic ATH provider failure"
        )

    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
            ),
        ],
        ath_provider=raising_ath_provider,
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_clock_returning_malformed_string_degrades_to_unknown() -> None:
    def malformed_clock() -> str:
        return "this is not a valid UTC ISO-8601 string"

    adapter = Stage29_5_4MigrationContextSourceAdapter(
        evidence_provider=lambda token_mint: [
            _present_evidence(
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
            ),
        ],
        ath_context_provider=_no_ath_provider,
        clock=malformed_clock,
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Unsafe / non-str token_mint -> UNKNOWN
# ---------------------------------------------------------------------------


def test_unsafe_short_token_mint_degrades_to_unknown() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(),
        ],
    )
    snapshot = adapter.read_migration_snapshot(
        "shortMint",
    )
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_empty_string_token_mint_degrades_to_unknown() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(),
        ],
    )
    snapshot = adapter.read_migration_snapshot("")
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_non_string_token_mint_degrades_to_unknown() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(),
        ],
    )
    snapshot = adapter.read_migration_snapshot(42)  # type: ignore[arg-type]
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_whitespace_in_token_mint_degrades_to_unknown() -> None:
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(),
        ],
    )
    # 44-char string but with whitespace inside -> rejected by
    # the Stage 29.5 safe-shape check.
    mint_with_space = (
        "AAA AAAAAAAA" + "A" * 32  # space inside
    )
    snapshot = adapter.read_migration_snapshot(
        mint_with_space,
    )
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Evidence provider receives the queried mint
# ---------------------------------------------------------------------------


def test_evidence_provider_receives_token_mint() -> None:
    seen_mints: list[str] = []

    def recording_provider(token_mint):
        seen_mints.append(token_mint)
        return ()

    adapter = _build_adapter(evidence=recording_provider)
    adapter.read_migration_snapshot(_BASE_MINT)
    adapter.read_migration_snapshot(_BASE_MINT_OTHER)
    assert seen_mints == [_BASE_MINT, _BASE_MINT_OTHER]


# ---------------------------------------------------------------------------
# raw_capture_ref always None
# ---------------------------------------------------------------------------


def test_raw_capture_ref_is_always_none() -> None:
    """The adapter never carries a raw payload reference -- the
    Stage 27.4 contract for ``raw_capture_ref`` admits a short
    safe-to-display reference, but Stage 29.5.4 deliberately
    omits it to keep the redaction discipline tight.
    """
    # COMPLETE path: ATH context wired, populated snapshot.
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
            ),
        ],
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert snapshot.raw_capture_ref is None
    assert (
        snapshot.migration_source
        == MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
    )

    # Also for the UNKNOWN path
    adapter2 = _build_adapter(evidence=_empty_evidence_provider)
    snapshot2 = adapter2.read_migration_snapshot(_BASE_MINT)
    assert snapshot2.raw_capture_ref is None


# ---------------------------------------------------------------------------
# Schema version constant matches manifest
# ---------------------------------------------------------------------------


def test_schema_version_constant_pinned() -> None:
    assert (
        STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION
        == "stage29_5_4_v0_migration_context_source_adapter"
    )


# ---------------------------------------------------------------------------
# UNKNOWN snapshot shape pin (defense in depth)
# ---------------------------------------------------------------------------


def test_unknown_snapshot_has_canonical_shape() -> None:
    """Every UNKNOWN-degraded snapshot must carry the canonical
    shape: all 5 optional slots None except ``migration_source =
    MIGRATION_SOURCE_UNKNOWN``.
    """
    adapter = _build_adapter(evidence=_empty_evidence_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None


# ---------------------------------------------------------------------------
# Non-raising contract under provider sequence corruption
# ---------------------------------------------------------------------------


def test_provider_returning_non_iterable_degrades_to_unknown() -> None:
    def bad_provider(token_mint):
        return 42  # not iterable

    adapter = _build_adapter(evidence=bad_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_provider_returning_non_record_entry_degrades_to_unknown() -> None:
    def bad_provider(token_mint):
        return ["not a real Stage29_5MigrationEvidenceRecord"]

    adapter = _build_adapter(evidence=bad_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Provider exception types beyond RuntimeError
# ---------------------------------------------------------------------------


def test_provider_value_error_degrades_to_unknown() -> None:
    def raising_provider(token_mint):
        raise ValueError("synthetic value error")

    adapter = _build_adapter(evidence=raising_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


def test_provider_key_error_degrades_to_unknown() -> None:
    def raising_provider(token_mint):
        raise KeyError("synthetic key error")

    adapter = _build_adapter(evidence=raising_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Adapter satisfies the Stage 27.4 MigrationContextSource Protocol
# ---------------------------------------------------------------------------


def test_adapter_satisfies_migration_context_source_protocol_shape() -> None:
    """Duck-type check: the adapter exposes
    ``read_migration_snapshot(token_mint) -> MigrationSourceSnapshot``.
    """
    adapter = _build_adapter(evidence=_empty_evidence_provider)
    method = getattr(adapter, "read_migration_snapshot", None)
    assert method is not None and callable(method)
    snapshot = method(_BASE_MINT)
    assert isinstance(snapshot, MigrationSourceSnapshot)


# ---------------------------------------------------------------------------
# Multiple matched evidence records -> first match drives the
# migration_event_id / source_event_ref echo
# ---------------------------------------------------------------------------


def test_first_matched_evidence_drives_event_id_and_source_event_ref() -> None:
    """When the Stage 29.5 join layer produces a JOINED record
    with >= 1 matched evidence entries (deterministic order), the
    adapter echoes the FIRST matched record's
    ``migration_signature`` -> snapshot.migration_event_id and
    the FIRST matched record's ``source_event_ref`` ->
    snapshot.source_event_ref.
    """
    first = _present_evidence(
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
    )
    adapter = _build_adapter(
        evidence=lambda token_mint: [first],
        ath_provider=lambda token_mint: _ath_context(
            token_mint=token_mint,
        ),
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_event_id == first.migration_signature
    assert snapshot.source_event_ref == first.source_event_ref


# ---------------------------------------------------------------------------
# Window kwargs propagate to the underlying integration
# ---------------------------------------------------------------------------


def test_window_kwargs_constrain_match() -> None:
    """A time_window that EXCLUDES the evidence record's
    timestamp must cause the join to emit TIME_WINDOW_INVALID
    and the adapter to degrade to UNKNOWN.
    """
    # Window AFTER the migration timestamp -> excluded.
    adapter = _build_adapter(
        evidence=lambda token_mint: [
            _present_evidence(
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
            ),
        ],
        time_window_start_utc="2026-06-01T00:00:00+00:00",
        time_window_end_utc="2026-06-02T00:00:00+00:00",
    )
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Codex hardening (Stage 29.5.4 PASS audit follow-up)
#
# These tests bypass the real Stage 29.5.2 offline integration by
# monkeypatching the adapter module's ``run_stage29_5_2_offline_integration``
# symbol with a fake that returns a deliberately-constructed result.
# The Stage 29.5 projection layer never legitimately produces these
# field combinations (e.g. COMPLETE + UNKNOWN source, COMPLETE +
# trusted source but None timestamp); these tests pin the Stage
# 29.5.4 adapter's defense-in-depth branches that degrade to
# ``MIGRATION_SOURCE_UNKNOWN`` regardless.
#
# Test-only fakes use ``types.SimpleNamespace`` for the inner
# objects; the adapter accesses attributes without isinstance-
# checking, so duck-typed namespaces suffice.
# ---------------------------------------------------------------------------


_ADAPTER_MODULE_PATH: str = (
    "PHX2.stage29.stage29_5_4_migration_context_source_adapter"
    ".run_stage29_5_2_offline_integration"
)


def _fake_result(
    *,
    measurement_status: str,
    migration_source: str,
    migration_timestamp_utc: Optional[str],
) -> SimpleNamespace:
    """Build a duck-typed fake Stage29_5_2OfflineIntegrationResult
    carrying only the attributes the Stage 29.5.4 adapter reads:
    ``private_ping_context`` (with ``measurement_status``,
    ``migration_source``, ``migration_timestamp_utc``) and
    ``join_record`` (with ``matched_evidence``).

    The ``matched_evidence`` tuple carries one duck-typed evidence
    namespace populated with a trusted-looking
    ``migration_signature`` + ``source_event_ref`` so the adapter
    has visibly authoritative fields available to leak if its
    defense-in-depth branches fail.
    """
    fake_projection = SimpleNamespace(
        measurement_status=measurement_status,
        migration_source=migration_source,
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=_MIGRATION_SLOT,
    )
    fake_evidence = SimpleNamespace(
        migration_signature=_MIGRATION_SIGNATURE,
        source_event_ref=_SOURCE_EVENT_REF,
    )
    fake_join = SimpleNamespace(
        matched_evidence=(fake_evidence,),
    )
    return SimpleNamespace(
        private_ping_context=fake_projection,
        join_record=fake_join,
    )


@pytest.mark.parametrize(
    "non_complete_status",
    [
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    ],
)
def test_non_complete_projection_statuses_degrade_to_unknown_even_with_trusted_timestamp(
    monkeypatch, non_complete_status: str,
) -> None:
    """Even when the upstream Stage 29.5 projection emits a
    non-COMPLETE ``measurement_status``, the Stage 29.5.4 adapter
    MUST degrade to ``MIGRATION_SOURCE_UNKNOWN`` regardless of how
    trusted-looking the supporting fields are (HELIUS_WS source,
    populated migration_event_id via matched evidence, populated
    migration_timestamp_utc). The Stage 29.5 projection layer never
    legitimately produces these combinations, but the adapter's
    projection-to-snapshot branch must NOT trust them either.
    """
    fake = _fake_result(
        measurement_status=non_complete_status,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        migration_timestamp_utc=_TS_MIGRATION,
    )

    def fake_run_integration(**kwargs) -> SimpleNamespace:
        return fake

    monkeypatch.setattr(
        _ADAPTER_MODULE_PATH, fake_run_integration,
    )

    adapter = _build_adapter(evidence=_empty_evidence_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)

    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None


def test_complete_with_unknown_projection_source_degrades_to_unknown(
    monkeypatch,
) -> None:
    """When the upstream Stage 29.5 projection emits
    ``measurement_status=COMPLETE`` with
    ``migration_source=UNKNOWN``, the Stage 29.5.4 adapter MUST
    degrade to ``MIGRATION_SOURCE_UNKNOWN`` even when the
    supporting fields (event_id, timestamp) look populated. The
    UNKNOWN source token is never in the trusted set; an UNKNOWN
    projection never anchors an authoritative snapshot.
    """
    fake = _fake_result(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        migration_timestamp_utc=_TS_MIGRATION,
    )

    def fake_run_integration(**kwargs) -> SimpleNamespace:
        return fake

    monkeypatch.setattr(
        _ADAPTER_MODULE_PATH, fake_run_integration,
    )

    adapter = _build_adapter(evidence=_empty_evidence_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)

    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None


def test_complete_with_trusted_source_but_missing_timestamp_degrades_to_unknown(
    monkeypatch,
) -> None:
    """When the upstream Stage 29.5 projection emits
    ``measurement_status=COMPLETE`` with a trusted
    ``migration_source`` (HELIUS_WS or
    STAGE29_MIGRATION_ARTIFACT) but a ``None`` timestamp, the
    Stage 29.5.4 adapter MUST degrade to
    ``MIGRATION_SOURCE_UNKNOWN``. Half-valid COMPLETE data NEVER
    anchors an authoritative snapshot; the
    ``migration_event_id`` and ``source_event_ref`` available on
    the matched evidence MUST NOT leak through.
    """
    fake = _fake_result(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        migration_timestamp_utc=None,
    )

    def fake_run_integration(**kwargs) -> SimpleNamespace:
        return fake

    monkeypatch.setattr(
        _ADAPTER_MODULE_PATH, fake_run_integration,
    )

    adapter = _build_adapter(evidence=_empty_evidence_provider)
    snapshot = adapter.read_migration_snapshot(_BASE_MINT)

    assert (
        snapshot.migration_source == MIGRATION_SOURCE_UNKNOWN
    )
    assert snapshot.migration_event_id is None
    assert snapshot.migration_timestamp_utc is None
    assert snapshot.source_event_ref is None
    assert snapshot.raw_capture_ref is None
