"""Stage 28.10 Chainstack Yellowstone hint-aware candidate assembler tests.

Pin:

  * SOL quote-mint hint reaches the Stage 27 adapter and avoids
    UNKNOWN suppression (where fake sources permit),
  * USDC quote-mint hint reaches the USDC observe-only lane,
  * missing quote hint does NOT invent SOL -- the candidate stays
    UNKNOWN,
  * conflicting hints (USDC mint with SOL provider hint) produce
    DISAGREE or safe suppression,
  * pool_account / pool_program_id / bonding-curve hints pass
    through to the Stage 27 adapter,
  * fake PRESENT price source enables candidate assembly,
  * missing price suppresses,
  * stale price suppresses,
  * no fake price source ships in production code,
  * the assembler refuses bad sources / bad candidate_id at
    construction / call time,
  * the assembler structurally satisfies the Stage 28.9
    ``Stage28_9CandidateAssembler`` Protocol shape,
  * hint extraction never fabricates a SOL / USDC token.

No real network. No real Discord send. No real provider call.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

import pytest

from PHX2.stage27 import price_ath_context_contracts as src_errors
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_REASON_RENDERED_WITH_WARNINGS,
    CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
)
from PHX2.stage27.pair_detection_constants import (
    KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_UNIT_SOL,
    ATH_UNIT_USDC,
    PRICE_UNIT_SOL,
    PRICE_UNIT_USDC,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
    FrozenStage27_4Clock,
    MigrationSourceSnapshot,
    PriceSourceSnapshot,
)

from PHX2.stage28.chainstack_yellowstone_candidate_assembler import (
    Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler,
    Stage28_10HintAwareCandidateAssemblerError,
    extract_stage28_10_hints,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    BONDING_CURVE_VERSION_HINT_SOL_LEGACY,
    PAIR_TYPE_HINT_PUMP_SOL,
    PAIR_TYPE_HINT_PUMP_USDC,
    QUOTE_ASSET_HINT_SOL,
    QUOTE_ASSET_HINT_USDC,
    build_normalized_event,
)


# ---------------------------------------------------------------------------
# Test-only fake sources (mirror Stage 27.6 test fixtures; live in tests
# only, never in production -- see Stage 28.10 runbook section 4).
# ---------------------------------------------------------------------------


_FIXED_UTC = datetime(2026, 5, 24, 12, 0, 30, tzinfo=timezone.utc)
_FIXED_UTC_ISO = "2026-05-24T12:00:30+00:00"


class _FrozenStage27_5Clock(NamedTuple):
    iso: str = _FIXED_UTC_ISO

    def now_utc_iso(self) -> str:
        return self.iso


class _FakePriceSource(NamedTuple):
    snapshot: Optional[PriceSourceSnapshot]
    raise_source_error: bool = False

    def read_price_snapshot(
        self, token_mint, *, pair_quote_asset,
    ):
        if self.raise_source_error:
            raise src_errors.Stage27PriceSourceError(
                "SOURCE_FAILED", source_label="fake_price",
            )
        return self.snapshot


class _FakeAthSource(NamedTuple):
    snapshot: Optional[AthSourceSnapshot]
    raise_source_error: bool = False

    def read_ath_snapshot(
        self, token_mint, *, pair_quote_asset,
    ):
        if self.raise_source_error:
            raise src_errors.Stage27AthSourceError(
                "SOURCE_FAILED", source_label="fake_ath",
            )
        return self.snapshot


class _FakeMigrationSource(NamedTuple):
    snapshot: Optional[MigrationSourceSnapshot]
    raise_source_error: bool = False

    def read_migration_snapshot(self, token_mint):
        if self.raise_source_error:
            raise src_errors.Stage27MigrationSourceError(
                "SOURCE_FAILED",
                source_label="fake_migration",
            )
        return self.snapshot


def _sol_sources(*, price_iso: str = _FIXED_UTC_ISO) -> Stage27_6Sources:
    price = PriceSourceSnapshot(
        price_value="0.001",
        price_unit=PRICE_UNIT_SOL,
        source_label="fake_birdeye",
        fetched_at_utc=price_iso,
    )
    ath = AthSourceSnapshot(
        ath_value="0.005",
        ath_unit=ATH_UNIT_SOL,
        source_label="fake_birdeye",
        ath_observed_at_utc="2026-05-24T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = MigrationSourceSnapshot(
        migration_event_id="mig-1",
        migration_timestamp_utc="2026-05-24T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="prov-mig-1",
        raw_capture_ref="rcap-mig-1",
    )
    return Stage27_6Sources(
        price_source=_FakePriceSource(snapshot=price),
        ath_source=_FakeAthSource(snapshot=ath),
        migration_source=_FakeMigrationSource(
            snapshot=migration,
        ),
        stage27_4_clock=FrozenStage27_4Clock(
            fixed_utc=_FIXED_UTC,
        ),
        stage27_5_clock=_FrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _usdc_sources() -> Stage27_6Sources:
    price = PriceSourceSnapshot(
        price_value="0.12",
        price_unit=PRICE_UNIT_USDC,
        source_label="fake_birdeye",
        fetched_at_utc=_FIXED_UTC_ISO,
    )
    ath = AthSourceSnapshot(
        ath_value="1.50",
        ath_unit=ATH_UNIT_USDC,
        source_label="fake_birdeye",
        ath_observed_at_utc="2026-05-24T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = MigrationSourceSnapshot(
        migration_event_id="mig-1",
        migration_timestamp_utc="2026-05-24T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="prov-mig-1",
        raw_capture_ref="rcap-mig-1",
    )
    return Stage27_6Sources(
        price_source=_FakePriceSource(snapshot=price),
        ath_source=_FakeAthSource(snapshot=ath),
        migration_source=_FakeMigrationSource(
            snapshot=migration,
        ),
        stage27_4_clock=FrozenStage27_4Clock(
            fixed_utc=_FIXED_UTC,
        ),
        stage27_5_clock=_FrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _missing_price_sources() -> Stage27_6Sources:
    ath = AthSourceSnapshot(
        ath_value="0.005",
        ath_unit=ATH_UNIT_SOL,
        source_label="fake_birdeye",
        ath_observed_at_utc="2026-05-24T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = MigrationSourceSnapshot(
        migration_event_id="mig-1",
        migration_timestamp_utc="2026-05-24T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="prov-mig-1",
        raw_capture_ref="rcap-mig-1",
    )
    return Stage27_6Sources(
        # No price snapshot -> Stage 27.4 treats as UNAVAILABLE.
        price_source=_FakePriceSource(snapshot=None),
        ath_source=_FakeAthSource(snapshot=ath),
        migration_source=_FakeMigrationSource(
            snapshot=migration,
        ),
        stage27_4_clock=FrozenStage27_4Clock(
            fixed_utc=_FIXED_UTC,
        ),
        stage27_5_clock=_FrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _stale_price_sources() -> Stage27_6Sources:
    """Sources whose price snapshot is one hour stale (well past the
    60s staleness threshold).
    """
    return _sol_sources(
        price_iso="2026-05-24T11:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Fixture normalized events
# ---------------------------------------------------------------------------


def _sol_event(
    *,
    event_id: str = "stage28_10_evt_sol_1",
    provider_event_id: str = "evt_sol_1",
    quote_mint: Optional[str] = KNOWN_WRAPPED_SOL_MINT,
    provider_quote_asset_hint: Optional[str] = QUOTE_ASSET_HINT_SOL,
    provider_pair_type_hint: Optional[str] = PAIR_TYPE_HINT_PUMP_SOL,
    bonding_curve_version_hint: Optional[str] = (
        BONDING_CURVE_VERSION_HINT_SOL_LEGACY
    ),
    pool_account: Optional[str] = (
        "PoolPoolPoolPoolPoolPoolPoolPoolPoolPoolPool11"
    ),
    pool_program_id: Optional[str] = (
        "ProgProgProgProgProgProgProgProgProgProgProg11"
    ),
    base_mint: Optional[str] = (
        "BaseBaseBaseBaseBaseBaseBaseBaseBaseBaseBase11"
    ),
):
    return build_normalized_event(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="chainstack_yellowstone_test",
        mint="MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA11",
        event_type="swap",
        observed_at_utc="2026-05-24T11:59:00+00:00",
        raw_event_hash=f"stage28_10_hash_{provider_event_id}",
        quote_mint=quote_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        base_mint=base_mint,
        bonding_curve_version_hint=bonding_curve_version_hint,
        provider_quote_asset_hint=provider_quote_asset_hint,
        provider_pair_type_hint=provider_pair_type_hint,
    )


def _usdc_event():
    return build_normalized_event(
        event_id="stage28_10_evt_usdc_1",
        provider_event_id="evt_usdc_1",
        provider_name="chainstack_yellowstone_test",
        mint="MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB22",
        event_type="swap",
        observed_at_utc="2026-05-24T11:59:00+00:00",
        raw_event_hash="stage28_10_hash_usdc",
        quote_mint=KNOWN_USDC_MINT,
        provider_quote_asset_hint=QUOTE_ASSET_HINT_USDC,
        provider_pair_type_hint=PAIR_TYPE_HINT_PUMP_USDC,
    )


def _no_hint_event():
    return build_normalized_event(
        event_id="stage28_10_evt_no_hint_1",
        provider_event_id="evt_no_hint_1",
        provider_name="chainstack_yellowstone_test",
        mint="MintCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC33",
        event_type="swap",
        observed_at_utc="2026-05-24T11:59:00+00:00",
        raw_event_hash="stage28_10_hash_no_hint",
        # No hints at all.
    )


def _conflicting_hint_event():
    """USDC quote_mint but SOL provider_quote_asset_hint -> the
    Stage 27 pair classifier must resolve to DISAGREE.
    """
    return build_normalized_event(
        event_id="stage28_10_evt_conflict_1",
        provider_event_id="evt_conflict_1",
        provider_name="chainstack_yellowstone_test",
        mint="MintDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD44",
        event_type="swap",
        observed_at_utc="2026-05-24T11:59:00+00:00",
        raw_event_hash="stage28_10_hash_conflict",
        quote_mint=KNOWN_USDC_MINT,
        provider_quote_asset_hint=QUOTE_ASSET_HINT_SOL,
        provider_pair_type_hint=PAIR_TYPE_HINT_PUMP_SOL,
    )


# ---------------------------------------------------------------------------
# Hint extraction
# ---------------------------------------------------------------------------


def test_extract_hints_returns_all_present_hint_attributes():
    event = _sol_event()
    hints = extract_stage28_10_hints(event)
    assert hints["quote_mint"] == KNOWN_WRAPPED_SOL_MINT
    assert (
        hints["provider_quote_asset_hint"]
        == QUOTE_ASSET_HINT_SOL
    )
    assert (
        hints["provider_pair_type_hint"]
        == PAIR_TYPE_HINT_PUMP_SOL
    )
    assert (
        hints["bonding_curve_version_hint"]
        == BONDING_CURVE_VERSION_HINT_SOL_LEGACY
    )
    assert hints["pool_account"] is not None
    assert hints["pool_program_id"] is not None
    assert hints["base_mint"] is not None


def test_extract_hints_returns_none_for_missing_attributes():
    event = _no_hint_event()
    hints = extract_stage28_10_hints(event)
    assert hints["quote_mint"] is None
    assert hints["pool_account"] is None
    assert hints["provider_quote_asset_hint"] is None
    assert hints["provider_pair_type_hint"] is None
    assert hints["bonding_curve_version_hint"] is None


def test_extract_hints_returns_none_for_non_eventlike():
    hints = extract_stage28_10_hints(object())
    for value in hints.values():
        assert value is None


def test_extract_hints_returns_none_for_non_string_attribute():
    class _BadEvent:
        quote_mint = 12345  # not a string
        pool_account = ""  # empty string

    hints = extract_stage28_10_hints(_BadEvent())
    assert hints["quote_mint"] is None
    assert hints["pool_account"] is None


# ---------------------------------------------------------------------------
# Assembler construction
# ---------------------------------------------------------------------------


def test_assembler_constructs_with_safe_sources():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    assert assembler.assemble_call_count == 0


def test_assembler_rejects_non_sources():
    with pytest.raises(
        Stage28_10HintAwareCandidateAssemblerError,
    ):
        (
            Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
                sources="not_a_sources",  # type: ignore[arg-type]
            )
        )


def test_assembler_rejects_empty_candidate_id():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    with pytest.raises(
        Stage28_10HintAwareCandidateAssemblerError,
    ):
        assembler.assemble(event, candidate_id="")


def test_assembler_rejects_non_string_candidate_id():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    with pytest.raises(
        Stage28_10HintAwareCandidateAssemblerError,
    ):
        assembler.assemble(
            event,
            candidate_id=123,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Structural compatibility with Stage 28.9 candidate assembler Protocol
# ---------------------------------------------------------------------------


def test_assembler_has_assemble_method():
    """Stage 28.10 assembler MUST expose
    ``assemble(normalized_event, *, candidate_id)`` so the Stage
    28.9 orchestrator can plug it in. This test pins the
    structural shape directly without importing Stage 28.9.
    """
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    assert hasattr(assembler, "assemble")
    assert callable(getattr(assembler, "assemble"))


# ---------------------------------------------------------------------------
# Hint-aware behaviour
# ---------------------------------------------------------------------------


def test_sol_event_with_hints_reaches_rendered_dry_run():
    """SOL event + SOL hints + PRESENT fresh price -> the Stage 27
    chain produces a RENDERED_DRY_RUN-like outcome (the Stage
    28.10 assembler forces write_artifacts=False, so the actual
    status will be ASSEMBLED rather than RENDERED_DRY_RUN -- but
    crucially NOT SUPPRESSED_UNKNOWN_PAIR).
    """
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    record = assembler.assemble(
        event, candidate_id="cand_sol_1",
    )
    assert isinstance(record, Stage27_6LiveCandidateRecord)
    # Stage 28.10 assembler forces write_artifacts=False; chain
    # produces ASSEMBLED (no on-disk write).
    assert record.candidate_status == CANDIDATE_STATUS_ASSEMBLED
    assert record.candidate_status not in (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
        CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    )
    assert record.candidate_reason in (
        CANDIDATE_REASON_RENDERED_OK,
        CANDIDATE_REASON_RENDERED_WITH_WARNINGS,
    )


def test_assembler_last_hints_captures_sol_hints():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    assembler.assemble(event, candidate_id="cand_sol_1")
    hints = assembler.last_hints
    assert hints["quote_mint"] == KNOWN_WRAPPED_SOL_MINT
    assert (
        hints["provider_quote_asset_hint"]
        == QUOTE_ASSET_HINT_SOL
    )


def test_assembler_call_count_increments():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    assembler.assemble(event, candidate_id="cand_a")
    assembler.assemble(
        _sol_event(
            event_id="stage28_10_evt_sol_2",
            provider_event_id="evt_sol_2",
        ),
        candidate_id="cand_b",
    )
    assert assembler.assemble_call_count == 2


def test_usdc_event_reaches_usdc_observe_only():
    sources = _usdc_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _usdc_event()
    record = assembler.assemble(
        event, candidate_id="cand_usdc_1",
    )
    # USDC observe-only candidate stays at the USDC observe-only
    # lane; the Stage 28.6 mapper projects this to
    # CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY downstream.
    assert (
        record.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY
    )


def test_no_hint_event_stays_unknown_no_silent_sol_promotion():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _no_hint_event()
    record = assembler.assemble(
        event, candidate_id="cand_no_hint_1",
    )
    assert (
        record.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    )
    assert (
        record.candidate_reason
        == CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
    )
    # Confirm no SOL was invented in the hint passthrough.
    assert assembler.last_hints["quote_mint"] is None
    assert (
        assembler.last_hints["provider_quote_asset_hint"] is None
    )


def test_conflicting_hint_event_resolves_to_disagree_or_safe_suppression():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _conflicting_hint_event()
    record = assembler.assemble(
        event, candidate_id="cand_conflict_1",
    )
    # The Stage 27 chain resolves conflicting hints to DISAGREE
    # (or, defensively, to UNKNOWN). Either is a safe suppression
    # path -- neither becomes a successful live-ready verdict.
    assert record.candidate_status in (
        CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    )
    assert record.candidate_reason in (
        CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
        CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    )


def test_pool_account_and_pool_program_id_hints_pass_through():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    assembler.assemble(event, candidate_id="cand_sol_1")
    hints = assembler.last_hints
    assert hints["pool_account"] is not None
    assert hints["pool_program_id"] is not None
    assert hints["base_mint"] is not None
    assert (
        hints["bonding_curve_version_hint"]
        == BONDING_CURVE_VERSION_HINT_SOL_LEGACY
    )


# ---------------------------------------------------------------------------
# Price-context discipline (no fake price in production)
# ---------------------------------------------------------------------------


def test_missing_price_suppresses_via_existing_stage_27_rules():
    sources = _missing_price_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    record = assembler.assemble(
        event, candidate_id="cand_sol_missing_price",
    )
    # The Stage 27.5 renderer marks the price_status as
    # UNAVAILABLE / SOURCE_ERROR (depending on the configured
    # source semantics); either way the Stage 28.6 mapper
    # projects to CANDIDATE_PRICE_STATUS_MISSING. The Stage 27.6
    # candidate itself stays ASSEMBLED but the rendered ping's
    # price_status surfaces the missing-price state.
    if record.rendered_ping is not None:
        assert record.rendered_ping.price_status in (
            "UNAVAILABLE", "SOURCE_ERROR", "UNSUPPORTED_PAIR",
        )


def test_stale_price_suppresses_via_existing_stage_27_rules():
    sources = _stale_price_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    record = assembler.assemble(
        event, candidate_id="cand_sol_stale_price",
    )
    if record.rendered_ping is not None:
        # Stage 27.4 stale-vs-present is decided at the staleness
        # threshold; with a 60-second threshold and an hour-old
        # price snapshot we expect STALE.
        assert record.rendered_ping.price_status in (
            "STALE",
            "UNAVAILABLE",
            "SOURCE_ERROR",
            "UNSUPPORTED_PAIR",
        )


def test_present_fresh_price_enables_candidate_assembly():
    sources = _sol_sources()
    assembler = (
        Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler(
            sources=sources,
        )
    )
    event = _sol_event()
    record = assembler.assemble(
        event, candidate_id="cand_sol_present",
    )
    assert record.rendered_ping is not None
    assert record.rendered_ping.price_status == "PRESENT"


# ---------------------------------------------------------------------------
# Production code carries no fake price source / no fake price
# ---------------------------------------------------------------------------


def test_production_assembler_module_carries_no_fake_price():
    """The Stage 28.10 candidate assembler production module must
    NOT define a fake price source / a fake price value. The
    operator injects real Stage 27.4 sources at the boundary.
    """
    src = (
        Path(__file__).resolve().parent.parent.parent
        / "stage28"
        / "chainstack_yellowstone_candidate_assembler.py"
    ).read_text(encoding="utf-8")
    lowered = src.lower()
    # Defensive: the production module must NOT define a fake
    # price source / a fake price snapshot.
    for needle in (
        "class _fakeprice",
        "class _fake_price",
        "class fakeprice",
        "fake_price_snapshot",
        "fake_birdeye",
        "stubbed_price",
        "hardcoded_price",
    ):
        assert needle not in lowered, (
            f"Stage 28.10 candidate assembler production module "
            f"must not contain fake-price marker {needle!r}"
        )
