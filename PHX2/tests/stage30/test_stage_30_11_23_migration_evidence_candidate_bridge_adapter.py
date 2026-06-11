"""Stage 30.11.23 discovered migration-evidence bridge adapter tests.

Offline / pure only. Exercises every closed-set bridge decision, the mint-keyed
evidence-source wiring, the duck-typed summary read (dict + attribute object), the
first-wins duplicate-mint policy, the source_ref redaction discipline, the inert
candidate-projection placeholders (proven to project cleanly through the committed
Stage 30.11.6 projection gate), and the bounded-scan + caller-shape fail-closed.

No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import pytest

from PHX2.stage30.stage30_11_6_candidate_source_models import (
    PROJECTION_DECISION_PROJECTED,
)
from PHX2.stage30.stage30_11_6_stage29_projection_adapter import (
    project_harvested_candidate,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED,
    BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT,
    BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS,
    BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME,
    BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY,
    BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT,
    BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION,
    STAGE30_11_23_REDACTED_UNSAFE_ID,
    STAGE30_11_23_REDACTION_STATUS_REDACTED,
    Stage30_11_23DiscoveredCandidate,
    Stage30_11_23RealFedInputs,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_adapter import (
    Stage30_11_23BridgeError,
    Stage30_11_23DiscoveredCandidateAssembler,
    Stage30_11_23DiscoveredCandidateFlattener,
    build_real_fed_inputs_from_migration_evidence,
    is_within_summaries_cap,
)


_CREATED_AT: str = "2026-06-10T00:00:00Z"
_MINT: str = "MintAAA111BBB222CCC333"
_ANCHOR: str = "2026-06-06T06:00:00Z"
_SOURCE_REF: str = "ref:sig:aaa:slot:1"


@dataclass(frozen=True)
class _Summary:
    """A fake Stage 29.5.7 sanitized migration-evidence summary (the bridge reads it
    duck-typed; the real Stage 29 type is never imported).
    """

    token_mint: Optional[object] = _MINT
    measurement_status: Optional[object] = "COMPLETE"
    migration_event_time_utc: Optional[object] = _ANCHOR
    warnings: object = ()
    redaction_status: Optional[object] = "SAFE"
    source_ref: Optional[object] = _SOURCE_REF


def _build(*summaries, **kwargs):
    return build_real_fed_inputs_from_migration_evidence(
        list(summaries), created_at_utc=_CREATED_AT, **kwargs
    )


def _decide(summary):
    inputs = _build(summary)
    assert len(inputs.report.bridge_events) == 1
    return inputs.report.bridge_events[0].decision, inputs


# ---------------------------------------------------------------------------
# 1. Happy path: one summary -> one candidate + one bound evidence record
# ---------------------------------------------------------------------------


def test_good_summary_bridges_candidate_and_evidence() -> None:
    inputs = _build(_Summary())
    assert isinstance(inputs, Stage30_11_23RealFedInputs)
    r = inputs.report
    assert r.summaries_seen == 1
    assert r.bridged == 1
    assert r.skipped == 0
    assert r.redaction_status == STAGE30_11_23_REDACTION_STATUS_REDACTED
    assert len(r.bridge_events) == 1
    ev = r.bridge_events[0]
    assert ev.index == 0
    assert ev.decision == BRIDGE_DECISION_BRIDGED
    assert ev.token_mint == _MINT
    assert ev.created_at_utc == _CREATED_AT

    assert len(inputs.events) == 1
    assert isinstance(inputs.events[0], Stage30_11_23DiscoveredCandidate)
    assert inputs.events[0].token_mint == _MINT


def test_evidence_source_returns_bound_record_for_the_discovered_mint() -> None:
    inputs = _build(_Summary())
    rec = inputs.evidence_source.lookup_migration_evidence(_MINT)
    assert rec is not None
    # The candidate token_mint AND the evidence token_mint are the SAME string.
    assert rec.token_mint == _MINT
    assert inputs.events[0].token_mint == rec.token_mint
    assert rec.measurement_status == "COMPLETE"
    assert rec.migration_event_time_utc == _ANCHOR
    assert rec.warnings == ()
    assert rec.redaction_status == "SAFE"
    assert rec.source_ref == _SOURCE_REF


def test_evidence_source_returns_none_for_unknown_mint() -> None:
    inputs = _build(_Summary())
    assert inputs.evidence_source.lookup_migration_evidence("UnknownMint") is None
    assert inputs.evidence_source.lookup_migration_evidence(None) is None


# ---------------------------------------------------------------------------
# 2. Redaction: source_ref is evidence-side only; never echoed in a bridge event
# ---------------------------------------------------------------------------


def test_source_ref_never_echoed_in_bridge_events() -> None:
    inputs = _build(_Summary())
    for ev in inputs.report.bridge_events:
        assert _SOURCE_REF not in ev.decision
        assert _SOURCE_REF not in ev.token_mint
        assert _SOURCE_REF not in ev.created_at_utc


def test_candidate_side_source_ref_is_none_and_projects_cleanly() -> None:
    inputs = _build(_Summary())
    assembler = inputs.assembler
    assert isinstance(assembler, Stage30_11_23DiscoveredCandidateAssembler)
    assert isinstance(
        inputs.record_flattener, Stage30_11_23DiscoveredCandidateFlattener
    )
    record = assembler.assemble(
        inputs.events[0], candidate_id="stage30_11_6_cand_000000"
    )
    assert record.token_mint == _MINT
    assert record.candidate_id == "stage30_11_6_cand_000000"
    flat = inputs.record_flattener(record)
    assert flat["token_mint"] == _MINT
    assert flat["candidate_id"] == "stage30_11_6_cand_000000"
    # The discovered source_ref lives ONLY on the evidence record, never the candidate.
    assert flat["source_ref"] is None
    # The inert placeholders satisfy the committed Stage 30.11.6 projection contract.
    result = project_harvested_candidate(flat, created_at_utc=_CREATED_AT)
    assert result.projection_decision == PROJECTION_DECISION_PROJECTED
    assert result.projection is not None
    assert result.projection.token_mint == _MINT
    assert result.projection.source_ref is None


# ---------------------------------------------------------------------------
# 3. Every SKIPPED decision
# ---------------------------------------------------------------------------


def test_skipped_not_a_summary() -> None:
    for bad in (None, 123, "MintLooksLikeAStringButIsScalar", 4.5, True, b"bytes"):
        decision, inputs = _decide(bad)
        assert decision == BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY
        assert inputs.report.bridged == 0
        assert inputs.events == ()
        assert inputs.evidence_source.lookup_migration_evidence(_MINT) is None


def test_skipped_missing_token_mint() -> None:
    assert _decide(_Summary(token_mint=None))[0] == (
        BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT
    )
    assert _decide(_Summary(token_mint="   "))[0] == (
        BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT
    )
    assert _decide(_Summary(token_mint=42))[0] == (
        BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT
    )


def test_skipped_invalid_token_mint_is_redacted_in_event() -> None:
    decision, inputs = _decide(_Summary(token_mint="bad/mint:x"))
    assert decision == BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT
    ev = inputs.report.bridge_events[0]
    # The raw unsafe mint is NEVER echoed -- it is replaced by REDACTED_UNSAFE_ID.
    assert ev.token_mint == STAGE30_11_23_REDACTED_UNSAFE_ID
    assert "bad/mint" not in ev.token_mint
    assert inputs.report.redaction_status == STAGE30_11_23_REDACTION_STATUS_REDACTED
    assert inputs.events == ()


def test_skipped_missing_migration_time() -> None:
    assert _decide(_Summary(migration_event_time_utc=None))[0] == (
        BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME
    )
    assert _decide(_Summary(migration_event_time_utc="  "))[0] == (
        BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME
    )


def test_skipped_not_complete_measurement() -> None:
    assert _decide(_Summary(measurement_status="PARTIAL"))[0] == (
        BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT
    )
    assert _decide(_Summary(measurement_status=None))[0] == (
        BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT
    )


def test_skipped_unsafe_redaction() -> None:
    assert _decide(_Summary(redaction_status="UNSAFE"))[0] == (
        BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION
    )
    assert _decide(_Summary(redaction_status=None))[0] == (
        BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION
    )


def test_skipped_malformed_warnings() -> None:
    for bad_warn in (None, "MIGRATION_STALE", 5, {"a": 1}, ("ok", 3), {"set"}):
        assert _decide(_Summary(warnings=bad_warn))[0] == (
            BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS
        ), f"warnings={bad_warn!r} must be SKIPPED_MALFORMED_WARNINGS"


def test_well_formed_stale_warnings_still_bridges() -> None:
    # A well-formed warnings CARRYING MIGRATION_STALE is bridged -- the bridge does NOT
    # decide staleness (the committed Stage 30.11.8 confirmation blocks it downstream).
    decision, inputs = _decide(_Summary(warnings=("MIGRATION_STALE",)))
    assert decision == BRIDGE_DECISION_BRIDGED
    rec = inputs.evidence_source.lookup_migration_evidence(_MINT)
    assert rec is not None
    assert rec.warnings == ("MIGRATION_STALE",)


# ---------------------------------------------------------------------------
# 4. First-wins duplicate-mint policy
# ---------------------------------------------------------------------------


def test_duplicate_mint_first_wins() -> None:
    first = _Summary()
    second = replace(first, migration_event_time_utc="2026-06-06T09:00:00Z")
    inputs = _build(first, second)
    assert inputs.report.summaries_seen == 2
    assert inputs.report.bridged == 1
    assert inputs.report.skipped == 1
    assert inputs.report.bridge_events[0].decision == BRIDGE_DECISION_BRIDGED
    assert inputs.report.bridge_events[1].decision == (
        BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT
    )
    assert len(inputs.events) == 1
    # First-wins: the single bound record carries the FIRST summary's anchor.
    rec = inputs.evidence_source.lookup_migration_evidence(_MINT)
    assert rec is not None
    assert rec.migration_event_time_utc == _ANCHOR


# ---------------------------------------------------------------------------
# 5. Duck-typed dict summary
# ---------------------------------------------------------------------------


def test_dict_summary_is_read_duck_typed() -> None:
    d = {
        "token_mint": "MintDictAAA111",
        "measurement_status": "COMPLETE",
        "migration_event_time_utc": _ANCHOR,
        "warnings": (),
        "redaction_status": "SAFE",
        "source_ref": "ref",
    }
    decision, inputs = _decide(d)
    assert decision == BRIDGE_DECISION_BRIDGED
    assert inputs.events[0].token_mint == "MintDictAAA111"
    assert (
        inputs.evidence_source.lookup_migration_evidence("MintDictAAA111")
        is not None
    )


# ---------------------------------------------------------------------------
# 6. Bounded scan + caller-shape fail-closed
# ---------------------------------------------------------------------------


def test_empty_summaries_yields_empty_consistent_bundle() -> None:
    inputs = _build()
    assert inputs.report.summaries_seen == 0
    assert inputs.report.bridged == 0
    assert inputs.report.skipped == 0
    assert inputs.events == ()
    assert inputs.report.redaction_status == STAGE30_11_23_REDACTION_STATUS_REDACTED


def test_bounded_scan_stops_at_max_summaries() -> None:
    summaries = [_Summary(token_mint=f"Mint{i:04d}AAA") for i in range(12)]
    inputs = build_real_fed_inputs_from_migration_evidence(
        summaries, created_at_utc=_CREATED_AT
    )
    assert inputs.report.summaries_seen == 10
    assert inputs.report.bridged == 10
    assert len(inputs.events) == 10


def test_is_within_summaries_cap() -> None:
    assert is_within_summaries_cap(1)
    assert is_within_summaries_cap(10)
    assert not is_within_summaries_cap(0)
    assert not is_within_summaries_cap(-1)
    assert not is_within_summaries_cap(11)
    assert not is_within_summaries_cap(True)
    assert not is_within_summaries_cap(1.0)
    assert not is_within_summaries_cap("5")


def test_out_of_cap_max_summaries_raises() -> None:
    for bad in (0, -1, 11, True, 1.5, "5"):
        with pytest.raises(Stage30_11_23BridgeError):
            build_real_fed_inputs_from_migration_evidence(
                [_Summary()], created_at_utc=_CREATED_AT, max_summaries=bad
            )
