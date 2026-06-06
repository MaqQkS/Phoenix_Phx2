"""Stage 30.11.10 offline fake ATH-resolver proof tests.

Proves the deterministic nine-base fake scenario drives the Stage 30.11.10 ATH resolver
to exactly ONE resolved ATH (``mint-resolved``) and EIGHT fail-closed readings on eight
DISTINCT reasons -- with the committed drawdown carried VERBATIM, strict mint binding,
and no resolution reaching any send surface. Pure / offline; no live call, no provider,
no private send, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_10_EXPECTED_BASES_SEEN,
    STAGE30_11_10_EXPECTED_RESOLVED,
    STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT,
    STAGE30_11_10_EXPECTED_UNRESOLVED,
)
from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    ATH_DECISION_RESOLVED,
    ATH_DECISION_UNRESOLVED,
    ATH_REASON_ATH_MINT_MISMATCH,
    ATH_REASON_ATH_NOT_PRESENT,
    ATH_REASON_ATH_SOURCE_ERROR,
    ATH_REASON_ATH_SOURCE_UNAVAILABLE,
    ATH_REASON_BLANK_CANDIDATE_MINT,
    ATH_REASON_MISSING_DRAWDOWN,
    ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
)
from PHX2.stage30.stage30_11_10_fake_ath_resolver_proof import (
    run_stage30_11_10_fake_ath_resolver,
)


def test_default_run_counts_match_the_baseline() -> None:
    run = run_stage30_11_10_fake_ath_resolver()
    s = run.summary
    assert s.bases_seen == STAGE30_11_10_EXPECTED_BASES_SEEN == 9
    assert s.resolved == STAGE30_11_10_EXPECTED_RESOLVED == 1
    assert s.unresolved == STAGE30_11_10_EXPECTED_UNRESOLVED == 8
    assert len(run.outcomes) == 9
    assert s.created_at_utc == "2026-01-01T00:00:00Z"


def test_exactly_one_resolved_and_it_is_the_expected_mint() -> None:
    run = run_stage30_11_10_fake_ath_resolver()
    resolved = [
        o for o in run.outcomes if o.decision == ATH_DECISION_RESOLVED
    ]
    assert len(resolved) == 1
    only = resolved[0]
    assert only.token_mint == STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT
    assert only.reason == ATH_REASON_RESOLVED_POST_MIGRATION_ATH
    assert only.present is True
    assert only.fresh is True
    assert only.post_migration_ath_verified is True
    # The committed drawdown is carried VERBATIM.
    assert only.drawdown_from_ath == "0.55"


def test_eight_fail_closed_reasons_are_all_distinct() -> None:
    run = run_stage30_11_10_fake_ath_resolver()
    fail_reasons = [
        o.reason for o in run.outcomes if o.decision == ATH_DECISION_UNRESOLVED
    ]
    assert len(fail_reasons) == 8
    assert set(fail_reasons) == {
        ATH_REASON_BLANK_CANDIDATE_MINT,
        ATH_REASON_MISSING_MIGRATION_ANCHOR,
        ATH_REASON_ATH_SOURCE_UNAVAILABLE,
        ATH_REASON_ATH_SOURCE_ERROR,
        ATH_REASON_ATH_MINT_MISMATCH,
        ATH_REASON_ATH_NOT_PRESENT,
        ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
        ATH_REASON_MISSING_DRAWDOWN,
    }


def test_every_outcome_is_a_closed_set_decision_and_reason() -> None:
    run = run_stage30_11_10_fake_ath_resolver()
    for o in run.outcomes:
        assert o.decision in (ATH_DECISION_RESOLVED, ATH_DECISION_UNRESOLVED)
        if o.decision == ATH_DECISION_RESOLVED:
            assert o.reason == ATH_REASON_RESOLVED_POST_MIGRATION_ATH
        else:
            assert o.reason != ATH_REASON_RESOLVED_POST_MIGRATION_ATH


def test_run_is_deterministic() -> None:
    a = run_stage30_11_10_fake_ath_resolver()
    b = run_stage30_11_10_fake_ath_resolver()
    assert a.summary == b.summary
    assert [(o.token_mint, o.decision, o.reason) for o in a.outcomes] == [
        (o.token_mint, o.decision, o.reason) for o in b.outcomes
    ]


def test_injected_created_at_is_carried_not_read_from_clock() -> None:
    run = run_stage30_11_10_fake_ath_resolver(
        created_at_utc="2030-12-31T23:59:59Z"
    )
    assert run.created_at_utc == "2030-12-31T23:59:59Z"
    assert run.summary.created_at_utc == "2030-12-31T23:59:59Z"
