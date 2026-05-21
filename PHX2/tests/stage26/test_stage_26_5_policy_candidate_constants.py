"""Stage 26.5 policy candidate closed-set / version-axis tests."""

from __future__ import annotations

import pytest

from PHX2.stage26 import policy_candidate_constants as c


_CLOSED_SETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("POLICY_CANDIDATE_KINDS", c.POLICY_CANDIDATE_KINDS),
    ("POLICY_CANDIDATE_STATUSES", c.POLICY_CANDIDATE_STATUSES),
    ("POLICY_CANDIDATE_READINESSES", c.POLICY_CANDIDATE_READINESSES),
    (
        "POLICY_CANDIDATE_ARTIFACT_KINDS",
        c.POLICY_CANDIDATE_ARTIFACT_KINDS,
    ),
    (
        "STAGE26_POLICY_CANDIDATE_ERROR_CODES",
        c.STAGE26_POLICY_CANDIDATE_ERROR_CODES,
    ),
    (
        "STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES",
        c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES,
    ),
    (
        "STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS",
        c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS,
    ),
    (
        "STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS",
        c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS,
    ),
)


@pytest.mark.parametrize("name,tup", _CLOSED_SETS)
def test_closed_set_is_tuple_and_non_empty(name, tup):
    assert isinstance(tup, tuple), f"{name} must be a tuple"
    assert len(tup) > 0, f"{name} must be non-empty"


@pytest.mark.parametrize("name,tup", _CLOSED_SETS)
def test_closed_set_has_no_duplicates(name, tup):
    assert len(set(tup)) == len(tup), f"{name} has duplicates"


_UPPERCASE_REQUIRED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("POLICY_CANDIDATE_KINDS", c.POLICY_CANDIDATE_KINDS),
    ("POLICY_CANDIDATE_STATUSES", c.POLICY_CANDIDATE_STATUSES),
    ("POLICY_CANDIDATE_READINESSES", c.POLICY_CANDIDATE_READINESSES),
    (
        "POLICY_CANDIDATE_ARTIFACT_KINDS",
        c.POLICY_CANDIDATE_ARTIFACT_KINDS,
    ),
    (
        "STAGE26_POLICY_CANDIDATE_ERROR_CODES",
        c.STAGE26_POLICY_CANDIDATE_ERROR_CODES,
    ),
)


@pytest.mark.parametrize("name,tup", _UPPERCASE_REQUIRED)
def test_closed_set_tokens_are_uppercase_ascii(name, tup):
    for token in tup:
        assert isinstance(token, str), f"{name}: non-string token {token!r}"
        assert token == token.upper(), (
            f"{name}: token {token!r} is not uppercase"
        )
        assert token.replace("_", "").isalnum(), (
            f"{name}: token {token!r} is not ASCII-alphanumeric"
        )


def test_policy_candidate_kinds_locked_set():
    assert set(c.POLICY_CANDIDATE_KINDS) == {
        "THRESHOLD_POLICY_CANDIDATE",
        "COVERAGE_CAVEAT_POLICY_CANDIDATE",
        "OBSERVABILITY_CAVEAT_POLICY_CANDIDATE",
        "REJECTION_CAVEAT_POLICY_CANDIDATE",
    }


def test_policy_candidate_statuses_locked_set():
    assert set(c.POLICY_CANDIDATE_STATUSES) == {
        "OBSERVE_ONLY_CANDIDATE",
        "BLOCKED_INSUFFICIENT_EVIDENCE",
        "BLOCKED_INVALID_THRESHOLD",
        "BLOCKED_POLICY_LEAK",
        "BLOCKED_RUNTIME_CONSUMABLE",
        "BLOCKED_APPROVAL_LEAK",
    }


def test_policy_candidate_readinesses_locked_set():
    assert set(c.POLICY_CANDIDATE_READINESSES) == {
        "READY_FOR_OPERATOR_REVIEW",
        "NEEDS_MORE_MEASURED_ROWS",
        "NEEDS_BETTER_COVERAGE",
        "NEEDS_SCOPE_REVIEW",
        "NEEDS_REJECTION_REVIEW",
        "INVALID_FOR_OPERATOR_REVIEW",
    }


def test_policy_candidate_artifact_kinds_locked_set():
    assert set(c.POLICY_CANDIDATE_ARTIFACT_KINDS) == {
        "POLICY_CANDIDATE_ROWS",
        "POLICY_CANDIDATE_SUMMARY",
        "POLICY_CANDIDATE_MANIFEST",
    }


def test_error_codes_locked_set_prefix():
    for code in c.STAGE26_POLICY_CANDIDATE_ERROR_CODES:
        assert code.startswith("STG26_CAL_POLICY_CANDIDATE_"), (
            f"error code {code!r} does not carry the Stage 26.5 prefix"
        )


def test_required_error_codes_present():
    required = {
        "STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD",
        "STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK",
        "STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK",
        "STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK",
        "STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS",
        "STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH",
        "STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID",
        "STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED",
    }
    assert required.issubset(set(c.STAGE26_POLICY_CANDIDATE_ERROR_CODES))


def test_artifact_filenames_locked_set():
    assert set(c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES) == {
        "stage26_policy_candidates.jsonl",
        "stage26_policy_candidate_summary.json",
        "stage26_policy_candidate_manifest.json",
    }


def test_artifact_filenames_have_no_runtime_policy_fragments():
    for name in c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES:
        lower = name.lower()
        for fragment in (
            c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
        ):
            assert fragment not in lower, (
                f"artifact filename {name!r} contains forbidden runtime "
                f"fragment {fragment!r}"
            )


def test_self_referential_manifest_sentinels_are_locked():
    assert isinstance(
        c.STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256, str
    )
    assert (
        c.STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
        == -1
    )
    assert (
        c.STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_ROW_COUNT
        == -1
    )


def test_self_entry_sentinel_does_not_look_like_sha256():
    sentinel = c.STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256
    is_64_hex = (
        len(sentinel) == 64
        and all(ch in "0123456789abcdef" for ch in sentinel)
    )
    assert not is_64_hex, (
        "self-entry sentinel must not look like a 64-char hex digest"
    )


def test_version_axes_are_locked_strings():
    assert c.STAGE26_POLICY_CANDIDATE_VERSION == (
        "stage26_policy_candidate_v0"
    )
    assert c.STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION == (
        "stage26_policy_candidate_ordering_v0"
    )
    assert c.STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION == (
        "stage26_policy_candidate_artifact_v0"
    )


def test_observe_only_mode_marker_is_observe_only():
    assert "observe_only" in (
        c.STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE
    )


def test_redaction_confirmed_token_documents_redaction():
    assert "redaction_confirmed" in (
        c.STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN
    )


def test_forbidden_output_substrings_include_url_and_secret_fragments():
    fragments_lower = tuple(
        fragment.lower()
        for fragment in c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS
    )
    expected_fragments = {
        "https://",
        "api_key",
        "webhook_url",
        "secret_key",
        "operator_approved=true",
        "runtime_consumable=true",
        "enforcement_enabled=true",
    }
    for needle in expected_fragments:
        assert needle in fragments_lower, (
            f"forbidden-output substrings missing required fragment "
            f"{needle!r}"
        )


def test_forbidden_runtime_basename_substrings_include_known_fragments():
    fragments = set(
        c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
    )
    required = {
        "runtime_policy",
        "approved_policy",
        "enforcement_policy",
        "live_policy",
        "operator_review_packet",
    }
    assert required.issubset(fragments)


def test_default_config_values_are_observe_only():
    assert c.DEFAULT_MIN_READY_THRESHOLD_CANDIDATES == 0
    assert c.DEFAULT_INCLUDE_NON_READY_CANDIDATES is True
