"""Stage 30.11.8 offline fake migration-confirmation proof tests.

Proves the deterministic fake confirmation proof: eleven bases seen, exactly ONE
confirmed (``mint-confirmed``), exactly TEN unconfirmed on TEN DISTINCT fail-closed
reasons (so a contradictory / invalid reading is never collapsed into a silent
unknown), the confirmed resolution carries the bound anchor + provenance, and the
ten fail-closed resolutions carry neither.

Pure / offline. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_8_fake_confirmation_proof import (
    default_fake_confirmation_bases,
    default_fake_evidence_source,
    run_stage30_11_8_fake_confirmation,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_DECISION_CONFIRMED,
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    STAGE30_11_8_EXPECTED_BASES_SEEN,
    STAGE30_11_8_EXPECTED_CONFIRMED,
    STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT,
    STAGE30_11_8_EXPECTED_UNCONFIRMED,
    STAGE30_11_8_FAIL_CLOSED_REASONS,
)


def test_proof_tally_matches_pinned_counts() -> None:
    run = run_stage30_11_8_fake_confirmation()
    s = run.summary
    assert s.bases_seen == STAGE30_11_8_EXPECTED_BASES_SEEN
    assert s.confirmed == STAGE30_11_8_EXPECTED_CONFIRMED
    assert s.unconfirmed == STAGE30_11_8_EXPECTED_UNCONFIRMED
    assert s.confirmed + s.unconfirmed == s.bases_seen
    assert len(run.outcomes) == STAGE30_11_8_EXPECTED_BASES_SEEN


def test_exactly_one_confirmed_and_it_is_the_expected_mint() -> None:
    run = run_stage30_11_8_fake_confirmation()
    confirmed = [o for o in run.outcomes if o.confirmed is True]
    assert len(confirmed) == 1
    only = confirmed[0]
    assert only.token_mint == STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT
    assert only.decision == CONFIRM_DECISION_CONFIRMED
    assert only.reason == CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT
    # The confirmed resolution carries the bound anchor + provenance.
    assert only.migration_event_time_utc is not None
    assert only.source_ref is not None


def test_ten_unconfirmed_on_ten_distinct_reasons() -> None:
    run = run_stage30_11_8_fake_confirmation()
    unconfirmed = [o for o in run.outcomes if o.confirmed is False]
    assert len(unconfirmed) == 10
    reasons = [o.reason for o in unconfirmed]
    # All ten are distinct (never collapsed) and every one is a fail-closed reason.
    assert len(set(reasons)) == 10
    assert set(reasons) == set(STAGE30_11_8_FAIL_CLOSED_REASONS) - {
        "BLANK_CANDIDATE_MINT"
    }
    # A fail-closed resolution carries NO anchor / provenance.
    for o in unconfirmed:
        assert o.migration_event_time_utc is None
        assert o.source_ref is None


def test_default_source_and_bases_are_deterministic() -> None:
    bases_a = default_fake_confirmation_bases()
    bases_b = default_fake_confirmation_bases()
    assert tuple(b.token_mint for b in bases_a) == (
        tuple(b.token_mint for b in bases_b)
    )
    assert bases_a[0].token_mint == STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT
    # ``mint-missing`` is deliberately absent from the source map.
    source = default_fake_evidence_source()
    assert source.lookup_migration_evidence("mint-missing") is None
    assert source.lookup_migration_evidence(
        STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT
    ) is not None


def test_proof_run_is_repeatable() -> None:
    run_a = run_stage30_11_8_fake_confirmation()
    run_b = run_stage30_11_8_fake_confirmation()
    assert [(o.token_mint, o.reason) for o in run_a.outcomes] == (
        [(o.token_mint, o.reason) for o in run_b.outcomes]
    )
