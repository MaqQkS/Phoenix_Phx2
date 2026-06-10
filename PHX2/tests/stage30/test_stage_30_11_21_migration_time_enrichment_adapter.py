"""Stage 30.11.21 migration-time enrichment adapter Layer-0 tests.

Offline / pure only. Proves the committed adapter's Layer-0 enrichment: a CONFIRMED
Stage 30.11.8 resolution overwrites ONLY the three migration fields
(``migration_time_utc`` / ``migration_confirmed`` / ``migration_source``) on a COPY
of the base fact while carrying ``current_price`` + the Stage 30.11.19
market-context bundle + ``age_display`` + every other field UNCHANGED
(``ENRICHED``); a non-facts base, or an UNCONFIRMED migration (each of the committed
Stage 30.11.8 fail reasons), fails closed to the precise closed-set ``SKIPPED_*``
token (mirrored from the Stage 30.11.8 reason) with ``enriched_facts=None``; the
confirmed anchor is the committed Stage 30.11.8 verdict's (never a bare timestamp
copy); an unsafe ``source_ref`` is dropped to ``None``; and an out-of-caps session
config fails closed before any base fact is scanned (the evidence source is never
called).

No live call, no provider, no network, no env read, no send. The migration verdict
is the committed Stage 30.11.8 confirmation's; this test injects evidence and checks
the adapter maps the verdict, never re-deciding it.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    Stage30_11_8MigrationEvidence,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_models import (
    MIGRATION_ENRICHMENT_DECISION_ENRICHED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter import (
    Stage30_11_21MigrationTimeEnrichmentError,
    enrich_facts_with_migration_time,
    run_stage30_11_21_migration_time_enriched_session,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeEvidenceSource:
    """Duck-typed fake exposing the committed surface
    ``lookup_migration_evidence(token_mint)``. Returns the SAME preset evidence for
    every mint (so a mint-mismatch evidence can be injected directly, bypassing the
    Stage 30.11.9 mint-binding).
    """

    def __init__(self, evidence: Any) -> None:
        self._evidence = evidence
        self.calls: int = 0

    def lookup_migration_evidence(self, token_mint: object) -> Any:
        self.calls += 1
        return self._evidence


class _RaisingEvidenceSource:
    def lookup_migration_evidence(self, token_mint: object) -> Any:
        raise RuntimeError("boom")


class _NoMethodSource:
    # No lookup_migration_evidence surface at all.
    pass


_GOOD_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_OTHER_MINT: str = "So11111111111111111111111111111111111111112"
_GOOD_CID: str = "stage30_11_21_cand_dip"
_GOOD_CREATED: str = "2026-06-07T07:06:40Z"

# The strict trailing-Z migration anchor the committed Stage 30.11.8 confirmation
# binds on a CONFIRMED resolution. This is the value the enrichment writes onto
# migration_time_utc.
_CONFIRMED_ANCHOR: str = "2026-06-06T06:14:10Z"
_CONFIRMED_SOURCE_REF: str = "evt_abcdef0123"

# The placeholder the harvest ceremony carries BEFORE the migration seam fills it.
_MIGRATION_PLACEHOLDER: str = ""

# The price + market placeholders the committed Stage 30.11.20 / 30.11.19 (NOT this
# seam) later fill / a real harvest already carries -- this seam must leave them.
_PRICE_VALUE: str = "0.000003053202401565669"
_MC_PLACEHOLDER: str = "1"
_LP_PLACEHOLDER: str = "1"
_STATUS_PLACEHOLDER: str = "UNKNOWN"
_FETCHED_AT_PLACEHOLDER: str = "2020-01-01T00:00:00Z"


def _base_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    # migration_time_utc carries the EMPTY placeholder (the real harvest has no
    # migration anchor); migration_confirmed is set FALSE and migration_source None
    # so an ENRICHED result proves the adapter EARNED the confirmation (set both
    # from the committed Stage 30.11.8 verdict) rather than passing the base through.
    base = dict(
        token_mint=_GOOD_MINT,
        candidate_id=_GOOD_CID,
        migration_time_utc=_MIGRATION_PLACEHOLDER,
        current_price=_PRICE_VALUE,
        current_market_cap_usd=_MC_PLACEHOLDER,
        liquidity_usd=_LP_PLACEHOLDER,
        market_context_status=_STATUS_PLACEHOLDER,
        market_context_fetched_at_utc=_FETCHED_AT_PLACEHOLDER,
        created_at_utc=_GOOD_CREATED,
        symbol_or_name="PHX",
        migration_source=None,
        age_display="~24h",
        migration_confirmed=False,
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _evidence(**overrides) -> Stage30_11_8MigrationEvidence:
    # A bound, redaction-SAFE, on-chain COMPLETE, not-stale, valid trailing-Z
    # evidence -- the ONLY shape the committed Stage 30.11.8 confirmation confirms.
    fields = dict(
        token_mint=_GOOD_MINT,
        measurement_status="COMPLETE",
        migration_event_time_utc=_CONFIRMED_ANCHOR,
        warnings=(),
        redaction_status="SAFE",
        source_ref=_CONFIRMED_SOURCE_REF,
    )
    fields.update(overrides)
    return Stage30_11_8MigrationEvidence(**fields)


def _source(**evidence_overrides) -> _FakeEvidenceSource:
    return _FakeEvidenceSource(_evidence(**evidence_overrides))


# ---------------------------------------------------------------------------
# 1. ENRICHED overwrites ONLY the migration fields; everything else unchanged
# ---------------------------------------------------------------------------


def test_enriched_overwrites_only_the_migration_fields() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_source()
    )
    assert result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED
    enriched = result.enriched_facts
    assert isinstance(enriched, Stage30_11_18HarvestedCandidateFacts)
    # The three migration fields are filled FROM the committed confirmation verdict.
    assert enriched.migration_time_utc == _CONFIRMED_ANCHOR
    assert enriched.migration_confirmed is True
    assert enriched.migration_source == _CONFIRMED_SOURCE_REF
    # Price + the Stage 30.11.19 market-context bundle are NOT touched (later seams
    # / a real harvest own them).
    assert enriched.current_price == _PRICE_VALUE
    assert enriched.current_market_cap_usd == _MC_PLACEHOLDER
    assert enriched.liquidity_usd == _LP_PLACEHOLDER
    assert enriched.market_context_status == _STATUS_PLACEHOLDER
    assert enriched.market_context_fetched_at_utc == _FETCHED_AT_PLACEHOLDER
    # age_display is carried UNCHANGED -- it is NEVER derived here (no clock).
    assert enriched.age_display == "~24h"
    # Identity + the caller timestamp are carried unchanged.
    assert enriched.token_mint == _GOOD_MINT
    assert enriched.candidate_id == _GOOD_CID
    assert enriched.symbol_or_name == "PHX"
    assert enriched.created_at_utc == _GOOD_CREATED


def test_enriched_returns_a_copy_and_never_mutates_the_base() -> None:
    base = _base_facts()
    result = enrich_facts_with_migration_time(base, evidence_source=_source())
    assert result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED
    assert result.enriched_facts is not base
    # The frozen base fact still carries the placeholder + the un-earned flags.
    assert base.migration_time_utc == _MIGRATION_PLACEHOLDER
    assert base.migration_confirmed is False
    assert base.migration_source is None


def test_enriched_passes_the_fact_mint_to_the_evidence_source() -> None:
    class _MintRecordingSource:
        def __init__(self) -> None:
            self.mints: list = []

        def lookup_migration_evidence(self, token_mint: object) -> Any:
            self.mints.append(token_mint)
            return _evidence()

    source = _MintRecordingSource()
    enrich_facts_with_migration_time(_base_facts(), evidence_source=source)
    assert source.mints == [_GOOD_MINT]


def test_unsafe_source_ref_is_dropped_to_none_on_confirm() -> None:
    # The committed confirmation carries source_ref verbatim; this seam drops a
    # present-but-unsafe ref (a url / scheme) to None rather than write it onto the
    # facts. The confirmation still confirms (the anchor is valid).
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(source_ref="https://evil.example/leak"),
    )
    assert result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED
    assert result.enriched_facts.migration_source is None
    # The anchor still landed.
    assert result.enriched_facts.migration_time_utc == _CONFIRMED_ANCHOR


def test_missing_source_ref_yields_none_migration_source() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_source(source_ref=None)
    )
    assert result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED
    assert result.enriched_facts.migration_source is None


# ---------------------------------------------------------------------------
# 2. Every closed-set Layer-0 skip token (mirrors the Stage 30.11.8 fail reasons)
# ---------------------------------------------------------------------------


def test_skipped_not_base_facts() -> None:
    result = enrich_facts_with_migration_time(
        "not a facts record", evidence_source=_source()
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS
    )
    assert result.enriched_facts is None


def test_skipped_blank_candidate_mint() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(token_mint=""), evidence_source=_source()
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT
    )
    assert result.enriched_facts is None


def test_skipped_missing_migration_evidence_when_source_returns_none() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_FakeEvidenceSource(None)
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE
    )


def test_skipped_missing_evidence_when_source_raises_or_lacks_method() -> None:
    for source in (_RaisingEvidenceSource(), _NoMethodSource()):
        result = enrich_facts_with_migration_time(
            _base_facts(), evidence_source=source
        )
        assert result.decision == (
            MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE
        ), source


def test_skipped_evidence_mint_mismatch() -> None:
    # A directly-injected wrong-mint evidence (bypassing the Stage 30.11.9
    # mint-binding) is the only way the committed confirmation reaches
    # EVIDENCE_MINT_MISMATCH.
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_source(token_mint=_OTHER_MINT)
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH
    )


def test_skipped_redaction_unsafe() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_source(redaction_status="UNSAFE")
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE
    )


def test_skipped_unknown_migration_on_unrecognized_status() -> None:
    for weird in ("WAT", "complete", "", None):
        result = enrich_facts_with_migration_time(
            _base_facts(), evidence_source=_source(measurement_status=weird)
        )
        assert result.decision == (
            MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION
        ), weird


def test_skipped_partial_migration_unverified() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(measurement_status="PARTIAL_MIGRATION_PRESENT"),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED
    )


def test_skipped_evidence_reports_no_migration() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(measurement_status="MISSING_MIGRATION"),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION
    )


def test_skipped_contradictory_migration_evidence() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(measurement_status="CONFLICTING_MIGRATION"),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE
    )


def test_skipped_invalid_migration_evidence() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(measurement_status="INVALID_MIGRATION"),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE
    )


def test_skipped_stale_migration_evidence() -> None:
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(warnings=("MIGRATION_STALE",)),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE
    )


def test_skipped_invalid_migration_anchor() -> None:
    # A COMPLETE / SAFE / not-stale reading whose anchor is malformed or a non-UTC
    # offset form (the committed confirmation requires a strict trailing-Z calendar
    # instant) fails closed at the anchor check.
    for bad_anchor in (
        "not-a-timestamp",
        "2026-06-06T06:14:10+00:00",
        "2026-13-40T25:61:61Z",
        "",
        None,
    ):
        result = enrich_facts_with_migration_time(
            _base_facts(),
            evidence_source=_source(migration_event_time_utc=bad_anchor),
        )
        assert result.decision == (
            MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR
        ), bad_anchor
        assert result.enriched_facts is None


def test_status_precedence_beats_anchor_check() -> None:
    # A non-SAFE redaction that ALSO carries a usable anchor must skip on the
    # redaction (first failing check wins in the committed confirmation), never
    # enrich.
    result = enrich_facts_with_migration_time(
        _base_facts(),
        evidence_source=_source(
            redaction_status="UNSAFE", migration_event_time_utc="garbage"
        ),
    )
    assert result.decision == (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE
    )


# ---------------------------------------------------------------------------
# 3. The session fails closed before scanning on an out-of-caps config
# ---------------------------------------------------------------------------


def test_run_session_raises_on_invalid_config_without_calling_the_source() -> (
    None
):
    bad_config = Stage30_11_17SessionConfig(
        max_candidates=999,
        max_compositions=1,
        created_at_utc=_GOOD_CREATED,
    )
    source = _source()
    with pytest.raises(Stage30_11_21MigrationTimeEnrichmentError):
        run_stage30_11_21_migration_time_enriched_session(
            [_base_facts()],
            evidence_source=source,
            price_source=None,
            market_context_source=None,
            config=bad_config,
            ledger=None,
            ath_transport=None,
            ath_endpoint_secret=None,
            now_utc=None,
            transport_client=None,
            now_seconds=None,
        )
    # Fail-closed BEFORE scanning: the evidence source was never called.
    assert source.calls == 0
