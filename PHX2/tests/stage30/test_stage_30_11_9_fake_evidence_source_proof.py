"""Stage 30.11.9 fake evidence-source proof tests.

Proves the deterministic seven-mint probe set binds evidence for exactly the two
expected mints (one matching record + one value-identical duplicate) and fails closed
for the other five (absent / wrong-mint / conflicting / raising / blank).
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_9_fake_evidence_source_proof import (
    Stage30_11_9FakeRecordProvider,
    default_fake_probe_mints,
    default_fake_record_provider,
    run_stage30_11_9_fake_evidence_source,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED,
    STAGE30_11_9_EXPECTED_NO_EVIDENCE,
    STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
    STAGE30_11_9_EXPECTED_PROBES_SEEN,
)


def test_default_probe_set_has_seven_mints() -> None:
    mints = default_fake_probe_mints()
    assert len(mints) == STAGE30_11_9_EXPECTED_PROBES_SEEN
    assert mints[0] == STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT
    assert "" in mints  # the blank-mint probe


def test_default_provider_is_callable() -> None:
    provider = default_fake_record_provider()
    assert isinstance(provider, Stage30_11_9FakeRecordProvider)
    # The present mint yields exactly one record; an absent mint yields none.
    assert len(provider(STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT)) == 1
    assert provider("mint-absent") == ()


def test_baseline_run_counts() -> None:
    run = run_stage30_11_9_fake_evidence_source()
    s = run.summary
    assert s.probes_seen == STAGE30_11_9_EXPECTED_PROBES_SEEN
    assert s.evidence_returned == STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED
    assert s.no_evidence == STAGE30_11_9_EXPECTED_NO_EVIDENCE
    assert s.evidence_returned + s.no_evidence == s.probes_seen


def test_only_present_and_dup_bind_evidence() -> None:
    run = run_stage30_11_9_fake_evidence_source()
    present = {
        o.token_mint for o in run.outcomes if o.evidence_present
    }
    assert present == {STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT, "mint-dup"}


def test_created_at_is_caller_injected() -> None:
    run = run_stage30_11_9_fake_evidence_source(
        created_at_utc="2030-12-31T23:59:59Z"
    )
    assert run.created_at_utc == "2030-12-31T23:59:59Z"
    assert run.summary.created_at_utc == "2030-12-31T23:59:59Z"


def test_blank_mint_outcome_is_echoed_empty() -> None:
    run = run_stage30_11_9_fake_evidence_source()
    # The blank-mint probe records an empty echoed mint and no evidence.
    blanks = [o for o in run.outcomes if o.token_mint == ""]
    assert len(blanks) == 1
    assert blanks[0].evidence_present is False
