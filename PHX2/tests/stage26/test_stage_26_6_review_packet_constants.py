"""Stage 26.6 review packet constants closed-set tests.

Pins the closed-set vocabularies, version axes, artifact basenames,
manifest self-entry sentinels, redaction-confirmed token, forbidden
runtime-basename and forbidden output-content substrings, and
typed-error code tokens declared in
``PHX2.stage26.review_packet_constants``.
"""

from __future__ import annotations

import pytest

from PHX2.stage26 import review_packet_constants as c


# ---------------------------------------------------------------------------
# Closed-set shape
# ---------------------------------------------------------------------------


_CLOSED_SET_NAMES: tuple[str, ...] = (
    "APPROVAL_HANDOFF_STATUSES",
    "REVIEW_CANDIDATE_STATUSES",
    "REVIEW_PACKET_ARTIFACT_KINDS",
    "REVIEW_PACKET_KINDS",
    "REVIEW_PACKET_STATUSES",
    "STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES",
    "STAGE26_REVIEW_PACKET_ERROR_CODES",
    "STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS",
    "STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS",
)


@pytest.mark.parametrize("name", _CLOSED_SET_NAMES)
def test_closed_set_is_non_empty_tuple_of_str(name):
    value = getattr(c, name)
    assert isinstance(value, tuple), (
        f"{name} must be a tuple; got {type(value).__name__}"
    )
    assert value != (), f"{name} must be non-empty"
    for item in value:
        assert isinstance(item, str), (
            f"{name} contains non-str entry {item!r}"
        )
        assert item != "", f"{name} contains empty string entry"


@pytest.mark.parametrize("name", _CLOSED_SET_NAMES)
def test_closed_set_has_no_duplicates(name):
    value = getattr(c, name)
    assert len(set(value)) == len(value), (
        f"{name} contains duplicate entries: {value!r}"
    )


_UPPERCASE_CLOSED_SET_NAMES: tuple[str, ...] = (
    "APPROVAL_HANDOFF_STATUSES",
    "REVIEW_CANDIDATE_STATUSES",
    "REVIEW_PACKET_ARTIFACT_KINDS",
    "REVIEW_PACKET_KINDS",
    "REVIEW_PACKET_STATUSES",
    "STAGE26_REVIEW_PACKET_ERROR_CODES",
)


@pytest.mark.parametrize("name", _UPPERCASE_CLOSED_SET_NAMES)
def test_token_closed_set_is_all_uppercase(name):
    value = getattr(c, name)
    for item in value:
        assert item == item.upper(), (
            f"{name} token {item!r} is not all-uppercase"
        )


# ---------------------------------------------------------------------------
# Locked closed-set contents
# ---------------------------------------------------------------------------


def test_review_packet_kinds_locked():
    assert c.REVIEW_PACKET_KINDS == (
        "OPERATOR_REVIEW_PACKET",
        "OPERATOR_REVIEW_CANDIDATE_ROWS",
        "OPERATOR_REVIEW_SUMMARY",
        "OPERATOR_REVIEW_MANIFEST",
    )


def test_review_packet_statuses_locked():
    assert c.REVIEW_PACKET_STATUSES == (
        "REVIEW_ONLY_PACKET",
        "BLOCKED_APPROVAL_LEAK",
        "BLOCKED_RUNTIME_LEAK",
        "BLOCKED_ENFORCEMENT_LEAK",
        "BLOCKED_REDACTION_FAILED",
        "BLOCKED_INVALID_INPUT",
    )


def test_review_candidate_statuses_locked():
    assert c.REVIEW_CANDIDATE_STATUSES == (
        "READY_FOR_OPERATOR_REVIEW",
        "NEEDS_MORE_MEASURED_ROWS",
        "NEEDS_BETTER_COVERAGE",
        "NEEDS_SCOPE_REVIEW",
        "NEEDS_REJECTION_REVIEW",
        "INVALID_FOR_OPERATOR_REVIEW",
        "BLOCKED_POLICY_CANDIDATE_LEAK",
    )


def test_approval_handoff_statuses_locked():
    assert c.APPROVAL_HANDOFF_STATUSES == (
        "PENDING_OPERATOR_REVIEW",
        "NOT_APPROVED",
        "APPROVAL_NOT_IN_STAGE_SCOPE",
    )


def test_review_packet_artifact_kinds_locked():
    assert c.REVIEW_PACKET_ARTIFACT_KINDS == (
        "REVIEW_PACKET",
        "REVIEW_CANDIDATE_ROWS",
        "REVIEW_SUMMARY",
        "REVIEW_MANIFEST",
    )


def test_approval_handoff_statuses_do_not_contain_approved_tokens():
    """Stage 26.6 NEVER exposes an APPROVED / AUTO_APPROVED token."""
    forbidden = {"APPROVED", "AUTO_APPROVED"}
    assert not (set(c.APPROVAL_HANDOFF_STATUSES) & forbidden)


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_review_packet_version_is_pinned_string():
    assert isinstance(c.STAGE26_REVIEW_PACKET_VERSION, str)
    assert c.STAGE26_REVIEW_PACKET_VERSION == "stage26_review_packet_v0"


def test_deterministic_ordering_version_is_pinned_string():
    assert isinstance(
        c.STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION, str
    )
    assert (
        c.STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION
        == "stage26_review_packet_ordering_v0"
    )


def test_artifact_schema_version_is_pinned_string():
    assert isinstance(
        c.STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION, str
    )
    assert (
        c.STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION
        == "stage26_review_packet_artifact_v0"
    )


# ---------------------------------------------------------------------------
# Artifact basenames + manifest sentinels
# ---------------------------------------------------------------------------


def test_locked_artifact_filenames_are_review_only_basenames():
    assert c.STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES == (
        "stage26_operator_review_packet.json",
        "stage26_operator_review_candidates.jsonl",
        "stage26_operator_review_summary.json",
        "stage26_operator_review_manifest.json",
    )


def test_artifact_basename_individual_constants():
    assert (
        c.STAGE26_OPERATOR_REVIEW_PACKET_FILENAME
        == "stage26_operator_review_packet.json"
    )
    assert (
        c.STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME
        == "stage26_operator_review_candidates.jsonl"
    )
    assert (
        c.STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME
        == "stage26_operator_review_summary.json"
    )
    assert (
        c.STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME
        == "stage26_operator_review_manifest.json"
    )


def test_self_referential_manifest_sentinels_are_not_64_char_hex():
    """The sha256 sentinel must not look like a 64-char lowercase hex
    digest so a reader cannot mistake it for a real sha256.
    """
    sentinel = c.STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256
    is_64_lowercase_hex = (
        len(sentinel) == 64
        and all(ch in "0123456789abcdef" for ch in sentinel)
    )
    assert not is_64_lowercase_hex


def test_self_referential_manifest_byte_count_is_minus_one():
    assert (
        c.STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
        == -1
    )


def test_self_referential_manifest_row_count_is_minus_one():
    assert (
        c.STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_ROW_COUNT
        == -1
    )


def test_review_only_mode_marker_is_pinned():
    assert (
        c.STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE
        == "stage26_operator_review_only"
    )


def test_redaction_confirmed_token_is_pinned():
    assert (
        c.STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN
        == "stage26_review_packet_redaction_confirmed"
    )


# ---------------------------------------------------------------------------
# Forbidden runtime / output substrings
# ---------------------------------------------------------------------------


def test_forbidden_runtime_basename_substrings_include_key_fragments():
    forbidden = c.STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
    expected_fragments = (
        "runtime_policy",
        "approved_policy",
        "enforcement_policy",
        "approval_decision",
        "live_router",
        "subscriber_router",
    )
    for fragment in expected_fragments:
        assert fragment in forbidden


def test_forbidden_output_substrings_include_url_and_secret_fragments():
    forbidden = c.STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS
    must_be_present = (
        "h" + "ttps://",
        "h" + "ttp://",
        "discord" + ".com",
        "api_key",
        "webhook_url",
        "operator_approved=true",
        "runtime_consumable=true",
        "enforcement_enabled=true",
    )
    for fragment in must_be_present:
        assert fragment in forbidden, (
            f"forbidden output substring {fragment!r} missing"
        )


def test_forbidden_output_substrings_include_approval_state_leak():
    forbidden = c.STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS
    # The double-quoted "APPROVED" / "AUTO_APPROVED" literals only
    # match a JSON string value that equals "APPROVED" / "AUTO_APPROVED"
    # exactly; they do NOT match field names like "operator_approved".
    assert "\"AUTO_APPROVED\"" in forbidden
    assert "\"APPROVED\"" in forbidden


# ---------------------------------------------------------------------------
# Error code tokens
# ---------------------------------------------------------------------------


def test_error_code_tuple_contains_locked_tokens():
    expected = {
        "STG26_CAL_REVIEW_PACKET_INVALID_INPUT",
        "STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK",
        "STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK",
        "STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK",
        "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED",
        "STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID",
        "STG26_CAL_REVIEW_PACKET_HASH_MISMATCH",
        "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID",
        "STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK",
        "STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH",
        "STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND",
        "STG26_CAL_REVIEW_PACKET_INVALID_STATUS",
    }
    assert set(c.STAGE26_REVIEW_PACKET_ERROR_CODES) == expected


@pytest.mark.parametrize(
    "code", list(_CLOSED_SET_NAMES)
)
def test_error_codes_use_stg26_cal_review_packet_prefix(code):
    if code != "STAGE26_REVIEW_PACKET_ERROR_CODES":
        return
    for token in c.STAGE26_REVIEW_PACKET_ERROR_CODES:
        assert token.startswith("STG26_CAL_REVIEW_PACKET_"), (
            f"Error-code token {token!r} missing required "
            "STG26_CAL_REVIEW_PACKET_ prefix"
        )


# ---------------------------------------------------------------------------
# Default config knob
# ---------------------------------------------------------------------------


def test_default_include_blocked_candidates_is_true():
    assert c.DEFAULT_INCLUDE_BLOCKED_CANDIDATES is True
