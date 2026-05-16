"""Stage 20.2 ID derivation tests.

Covers determinism, per-input variation, the closed-set
prefix invariant ("stage20_", "cand_", "dec_"), the 16-hex-digest
length invariant, and the "|" separator rejection.

Per operator decision B2-c the minor-version axis
(``STAGE20_MINOR_VERSION`` = "20.2") participates in every
derivation alongside the major-version axis
(``STAGE20_VERSION`` = "stage20_v0_observe_only"). These tests
keep the version values as test-local constants so the tests do
not depend on future constants.py drift.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.ids import (
    derive_candidate_id,
    derive_decision_id,
    derive_stage20_run_id,
)


# Test-local version pair (independent of constants.py drift).
_MAJOR = "stage20_v0_observe_only"
_MINOR = "20.2"
_MAPPING = "v0"
_CONSUMER = "stage20_to_stage21_v0"


# ---------------------------------------------------------------------------
# Canonical input vectors
# ---------------------------------------------------------------------------


def _canonical_run_id_kwargs() -> dict:
    return dict(
        stage18_run_id="s18_aaa",
        stage18_manifest_sha256="a" * 64,
        stage18_review_matrix_sha256="b" * 64,
        stage19_run_id="s19_bbb",
        stage19_ledger_sha256="c" * 64,
        stage19_manifest_sha256="d" * 64,
        stage20_version=_MAJOR,
        stage20_minor_version=_MINOR,
        mapping_version=_MAPPING,
        consumer_contract_version=_CONSUMER,
        generated_at_utc="2026-05-15T00:00:00Z",
    )


def _canonical_candidate_kwargs() -> dict:
    return dict(
        stage19_run_id="s19_bbb",
        source_ledger_row_id="ledger_row_aaa",
        stage20_version=_MAJOR,
        stage20_minor_version=_MINOR,
    )


def _canonical_decision_kwargs() -> dict:
    return dict(
        candidate_id="cand_0123456789abcdef",
        decision_step_index=0,
        decision_step_name="slice_resolved",
        stage20_version=_MAJOR,
        stage20_minor_version=_MINOR,
    )


# ---------------------------------------------------------------------------
# Prefix + shape invariants
# ---------------------------------------------------------------------------


def test_stage20_run_id_prefix_and_length():
    rid = derive_stage20_run_id(**_canonical_run_id_kwargs())
    assert rid.startswith("stage20_")
    assert len(rid) == len("stage20_") + 16
    # Suffix is lowercase hex.
    suffix = rid.removeprefix("stage20_")
    assert all(c in "0123456789abcdef" for c in suffix)


def test_candidate_id_prefix_and_length():
    cid = derive_candidate_id(**_canonical_candidate_kwargs())
    assert cid.startswith("cand_")
    assert len(cid) == len("cand_") + 16
    suffix = cid.removeprefix("cand_")
    assert all(c in "0123456789abcdef" for c in suffix)


def test_decision_id_prefix_and_length():
    did = derive_decision_id(**_canonical_decision_kwargs())
    assert did.startswith("dec_")
    assert len(did) == len("dec_") + 16
    suffix = did.removeprefix("dec_")
    assert all(c in "0123456789abcdef" for c in suffix)


# ---------------------------------------------------------------------------
# Determinism (same inputs -> same id)
# ---------------------------------------------------------------------------


def test_stage20_run_id_is_deterministic():
    a = derive_stage20_run_id(**_canonical_run_id_kwargs())
    b = derive_stage20_run_id(**_canonical_run_id_kwargs())
    assert a == b


def test_candidate_id_is_deterministic():
    a = derive_candidate_id(**_canonical_candidate_kwargs())
    b = derive_candidate_id(**_canonical_candidate_kwargs())
    assert a == b


def test_decision_id_is_deterministic():
    a = derive_decision_id(**_canonical_decision_kwargs())
    b = derive_decision_id(**_canonical_decision_kwargs())
    assert a == b


# ---------------------------------------------------------------------------
# Variation -- one variation test per input field per function
# ---------------------------------------------------------------------------


def test_stage20_run_id_varies_when_generated_at_utc_changes():
    """Prompt-mandated test 8: generated_at_utc bump alters run id."""

    base = derive_stage20_run_id(**_canonical_run_id_kwargs())
    perturbed = _canonical_run_id_kwargs()
    perturbed["generated_at_utc"] = "2026-05-16T00:00:00Z"
    assert derive_stage20_run_id(**perturbed) != base


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("stage18_run_id", "s18_zzz"),
        ("stage18_manifest_sha256", "0" * 64),
        ("stage18_review_matrix_sha256", "0" * 64),
        ("stage19_run_id", "s19_zzz"),
        ("stage19_ledger_sha256", "0" * 64),
        ("stage19_manifest_sha256", "0" * 64),
        ("stage20_version", "stage20_v9_other"),
        ("stage20_minor_version", "99.99"),
        ("mapping_version", "v99"),
        ("consumer_contract_version", "stage20_to_stage21_v99"),
    ],
)
def test_stage20_run_id_varies_on_every_input(field: str, new_value: str):
    base = derive_stage20_run_id(**_canonical_run_id_kwargs())
    perturbed = _canonical_run_id_kwargs()
    perturbed[field] = new_value
    assert derive_stage20_run_id(**perturbed) != base


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("stage19_run_id", "s19_zzz"),
        ("source_ledger_row_id", "ledger_row_zzz"),
        ("stage20_version", "stage20_v9_other"),
        ("stage20_minor_version", "99.99"),
    ],
)
def test_candidate_id_varies_on_every_input(field: str, new_value: str):
    base = derive_candidate_id(**_canonical_candidate_kwargs())
    perturbed = _canonical_candidate_kwargs()
    perturbed[field] = new_value
    assert derive_candidate_id(**perturbed) != base


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("candidate_id", "cand_ffffffffffffffff"),
        ("decision_step_index", 1),
        ("decision_step_name", "terminal"),
        ("stage20_version", "stage20_v9_other"),
        ("stage20_minor_version", "99.99"),
    ],
)
def test_decision_id_varies_on_every_input(field: str, new_value):
    base = derive_decision_id(**_canonical_decision_kwargs())
    perturbed = _canonical_decision_kwargs()
    perturbed[field] = new_value
    assert derive_decision_id(**perturbed) != base


# ---------------------------------------------------------------------------
# "|" separator rejection (prompt-mandated test 9 -- 3 sub-tests)
# ---------------------------------------------------------------------------


def test_pipe_in_stage20_run_id_input_raises():
    kwargs = _canonical_run_id_kwargs()
    kwargs["stage18_run_id"] = "s18|injected"
    with pytest.raises(ValueError):
        derive_stage20_run_id(**kwargs)


def test_pipe_in_candidate_id_input_raises():
    kwargs = _canonical_candidate_kwargs()
    kwargs["source_ledger_row_id"] = "ledger|row|injected"
    with pytest.raises(ValueError):
        derive_candidate_id(**kwargs)


def test_pipe_in_decision_id_input_raises():
    kwargs = _canonical_decision_kwargs()
    kwargs["decision_step_name"] = "terminal|injected"
    with pytest.raises(ValueError):
        derive_decision_id(**kwargs)


# ---------------------------------------------------------------------------
# Minor-version axis sanity check (operator decision B2-c)
# ---------------------------------------------------------------------------


def test_stage20_run_id_changes_when_minor_version_bumps():
    base_kwargs = _canonical_run_id_kwargs()
    base = derive_stage20_run_id(**base_kwargs)

    bumped = dict(base_kwargs)
    bumped["stage20_minor_version"] = "20.3"
    assert derive_stage20_run_id(**bumped) != base


def test_candidate_id_changes_when_minor_version_bumps():
    base = derive_candidate_id(**_canonical_candidate_kwargs())
    bumped = dict(_canonical_candidate_kwargs())
    bumped["stage20_minor_version"] = "20.3"
    assert derive_candidate_id(**bumped) != base


def test_decision_id_changes_when_minor_version_bumps():
    base = derive_decision_id(**_canonical_decision_kwargs())
    bumped = dict(_canonical_decision_kwargs())
    bumped["stage20_minor_version"] = "20.3"
    assert derive_decision_id(**bumped) != base
