"""Stage 30.11.6 candidate harvest adapter tests.

Proves the harvest seam: it drives an INJECTED assembler over a bounded event
source, captures each assembled record, flattens + projects it, and accumulates a
Stage 30.11.5-ready candidate source -- WITHOUT ever constructing a transport /
dispatch sink / runner. A raising assembler is a clean SKIPPED_ASSEMBLY_FAILED
(no candidate); a raising flattener / a projection-rejected record is a clean
SKIPPED_PROJECTION_REJECTED (no candidate); the run-scoped candidate ids are
stamped deterministically; the bounded harvest cap holds (fail-closed on an
out-of-bounds budget); and the injected assembler's dispatch tripwire is NEVER
called.

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from PHX2.stage30.stage30_11_6_candidate_harvest_adapter import (
    Stage30_11_6CandidateHarvestError,
    harvest_live_candidates,
    is_within_harvest_cap,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    HARVEST_DECISION_HARVESTED,
    HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
    STAGE30_11_6_NOT_PROJECTED,
    Stage30_11_6CandidateProjection,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fields(token_mint: str, *, omit_market_cap: bool = False) -> Dict[str, object]:
    fields: Dict[str, object] = {
        "token_mint": token_mint,
        "pair_type": "SOL",
        "tier_hint": "Tier 1",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "current_market_cap_usd": "12345.67",
        "post_migration_ath_verified": True,
        "source_ref": "ref",
        "created_at_utc": _CREATED_AT,
    }
    if omit_market_cap:
        del fields["current_market_cap_usd"]
    return fields


class _FakeRecord:
    """A captured record stand-in carrying the flat fields + scenario flags."""

    def __init__(self, candidate_id: str, fields: Dict[str, object]) -> None:
        self.candidate_id = candidate_id
        self.fields = dict(fields)


class _FakeAssembler:
    """Records assemble calls + exposes a dispatch tripwire the harvest never calls."""

    def __init__(self, scenario_for_mint: Optional[Dict[str, str]] = None) -> None:
        self.assemble_calls = 0
        self.seen_candidate_ids: List[str] = []
        self.dispatch_tripwire_calls = 0
        self._scenario = scenario_for_mint or {}

    def assemble(self, normalized_event: object, *, candidate_id: str) -> object:
        self.assemble_calls += 1
        self.seen_candidate_ids.append(candidate_id)
        token_mint = str(normalized_event)
        scenario = self._scenario.get(token_mint, "OK")
        if scenario == "RAISE":
            raise RuntimeError("fake assembler raising")
        if scenario == "NONE":
            return None
        return _FakeRecord(
            candidate_id,
            _fields(token_mint, omit_market_cap=(scenario == "OMIT_MC")),
        )

    def send_one_audited_post(self, *args: object, **kwargs: object) -> None:
        self.dispatch_tripwire_calls += 1


def _flatten(record: object) -> Dict[str, object]:
    assert isinstance(record, _FakeRecord)
    fields = dict(record.fields)
    fields["candidate_id"] = record.candidate_id
    return fields


def _raising_flatten(record: object) -> Dict[str, object]:
    raise ValueError("fake flattener raising")


# ---------------------------------------------------------------------------
# 1. Happy path: assembled candidates are harvested into a candidate source
# ---------------------------------------------------------------------------


def test_harvest_captures_and_projects() -> None:
    assembler = _FakeAssembler()
    result = harvest_live_candidates(
        ("mint-a", "mint-b"),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.events_seen == 2
    assert result.summary.harvested == 2
    assert result.summary.skipped_assembly_failed == 0
    assert result.summary.skipped_projection_rejected == 0
    assert len(result.candidate_source) == 2
    for projection in result.candidate_source:
        assert isinstance(projection, Stage30_11_6CandidateProjection)
    # Run-scoped candidate ids are stamped deterministically.
    assert [p.candidate_id for p in result.candidate_source] == [
        "stage30_11_6_cand_000000",
        "stage30_11_6_cand_000001",
    ]
    assert [p.token_mint for p in result.candidate_source] == [
        "mint-a",
        "mint-b",
    ]
    assert all(
        o.harvest_decision == HARVEST_DECISION_HARVESTED for o in result.outcomes
    )
    # The assembler was driven, but the dispatch tripwire was NEVER reached.
    assert assembler.assemble_calls == 2
    assert assembler.dispatch_tripwire_calls == 0


def test_candidate_id_prefix_is_configurable() -> None:
    assembler = _FakeAssembler()
    result = harvest_live_candidates(
        ("mint-a",),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
        candidate_id_prefix="run7_",
    )
    assert result.candidate_source[0].candidate_id == "run7_000000"


# ---------------------------------------------------------------------------
# 2. Failed assembly does NOT yield a candidate
# ---------------------------------------------------------------------------


def test_raising_assembler_is_skipped_assembly_failed() -> None:
    assembler = _FakeAssembler(scenario_for_mint={"mint-bad": "RAISE"})
    result = harvest_live_candidates(
        ("mint-a", "mint-bad", "mint-c"),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.harvested == 2
    assert result.summary.skipped_assembly_failed == 1
    assert [p.token_mint for p in result.candidate_source] == ["mint-a", "mint-c"]
    failed = [
        o
        for o in result.outcomes
        if o.harvest_decision == HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED
    ]
    assert len(failed) == 1
    assert failed[0].projection_decision == STAGE30_11_6_NOT_PROJECTED
    assert failed[0].candidate_id == ""
    # The assembler was still CALLED for the failing event (assembly attempted).
    assert assembler.assemble_calls == 3
    assert assembler.dispatch_tripwire_calls == 0


def test_none_record_is_skipped_assembly_failed() -> None:
    assembler = _FakeAssembler(scenario_for_mint={"mint-empty": "NONE"})
    result = harvest_live_candidates(
        ("mint-empty",),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.harvested == 0
    assert result.summary.skipped_assembly_failed == 1
    assert result.candidate_source == ()


# ---------------------------------------------------------------------------
# 3. Malformed candidate does NOT reach the runner (projection rejected)
# ---------------------------------------------------------------------------


def test_projection_rejected_record_is_skipped() -> None:
    assembler = _FakeAssembler(scenario_for_mint={"mint-bad": "OMIT_MC"})
    result = harvest_live_candidates(
        ("mint-a", "mint-bad"),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.harvested == 1
    assert result.summary.skipped_projection_rejected == 1
    skipped = [
        o
        for o in result.outcomes
        if o.harvest_decision == HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED
    ]
    assert len(skipped) == 1
    # The reject names the missing field (a safe field NAME only).
    assert skipped[0].rejected_field == "current_market_cap_usd"
    # Identity is still echoed (a record was captured).
    assert skipped[0].candidate_id == "stage30_11_6_cand_000001"
    assert skipped[0].token_mint == "mint-bad"


def test_raising_flattener_is_skipped_projection_rejected() -> None:
    assembler = _FakeAssembler()
    result = harvest_live_candidates(
        ("mint-a",),
        assembler=assembler,
        record_flattener=_raising_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.harvested == 0
    assert result.summary.skipped_projection_rejected == 1
    assert result.candidate_source == ()
    assert result.outcomes[0].harvest_decision == (
        HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED
    )
    # A flattener failure leaves no readable identity.
    assert result.outcomes[0].candidate_id == ""
    # The assembler WAS reached (a record was captured) but never dispatched.
    assert assembler.assemble_calls == 1
    assert assembler.dispatch_tripwire_calls == 0


# ---------------------------------------------------------------------------
# 4. Bounded harvest cap
# ---------------------------------------------------------------------------


def test_is_within_harvest_cap() -> None:
    assert is_within_harvest_cap(1)
    assert is_within_harvest_cap(STAGE30_11_6_MAX_HARVEST_HARD_CAP)
    assert not is_within_harvest_cap(0)
    assert not is_within_harvest_cap(-1)
    assert not is_within_harvest_cap(STAGE30_11_6_MAX_HARVEST_HARD_CAP + 1)
    assert not is_within_harvest_cap(True)
    assert not is_within_harvest_cap(1.0)
    assert not is_within_harvest_cap("3")


def test_max_harvest_caps_the_event_pull() -> None:
    assembler = _FakeAssembler()
    result = harvest_live_candidates(
        tuple(f"mint-{i}" for i in range(8)),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
        max_harvest=3,
    )
    # Only 3 events were pulled (a single bounded for-loop stops at the cap).
    assert result.summary.events_seen == 3
    assert result.summary.harvested == 3
    assert assembler.assemble_calls == 3


def test_out_of_bounds_max_harvest_fails_closed() -> None:
    assembler = _FakeAssembler()
    for bad in (0, -1, STAGE30_11_6_MAX_HARVEST_HARD_CAP + 1, True, 2.0):
        with pytest.raises(Stage30_11_6CandidateHarvestError):
            harvest_live_candidates(
                ("mint-a",),
                assembler=assembler,
                record_flattener=_flatten,
                created_at_utc=_CREATED_AT,
                max_harvest=bad,  # type: ignore[arg-type]
            )
    # Nothing was driven on the fail-closed path.
    assert assembler.assemble_calls == 0


def test_empty_source_harvests_nothing() -> None:
    assembler = _FakeAssembler()
    result = harvest_live_candidates(
        (),
        assembler=assembler,
        record_flattener=_flatten,
        created_at_utc=_CREATED_AT,
    )
    assert result.summary.events_seen == 0
    assert result.summary.harvested == 0
    assert result.candidate_source == ()
    assert assembler.assemble_calls == 0
