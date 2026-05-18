"""Stage 22.1 constants tests.

Pins every Stage 22 closed-set tuple, version axis, and
boundary-scanner input. Any drift in a token, an ordering, or
the size of a set fails here.
"""

from __future__ import annotations

from PHX2.stage22 import constants as c


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage22_version_is_locked():
    assert c.STAGE22_VERSION == "stage22_v0_ingest_hardening_foundation"


def test_stage22_minor_version_is_locked():
    assert c.STAGE22_MINOR_VERSION == "22.1"


def test_stage22_consumer_contract_version_is_locked():
    assert c.STAGE22_CONSUMER_CONTRACT_VERSION == "stage22_v0_ingest"


# ---------------------------------------------------------------------------
# PROVIDER_FAILURE_LABELS
# ---------------------------------------------------------------------------


def test_provider_failure_labels_match_locked_eight_token_set():
    assert c.PROVIDER_FAILURE_LABELS == (
        "provider_fetch_timeout",
        "provider_fetch_rate_limited",
        "provider_fetch_5xx",
        "provider_fetch_4xx",
        "provider_fetch_connection",
        "provider_fetch_auth",
        "provider_fetch_other",
        "provider_returned_malformed",
    )


def test_provider_returned_empty_is_not_a_failure_label():
    assert "provider_returned_empty" not in c.PROVIDER_FAILURE_LABELS


# ---------------------------------------------------------------------------
# STATUS_CLASSES
# ---------------------------------------------------------------------------


def test_status_classes_match_locked_nine_token_set():
    assert c.STATUS_CLASSES == (
        "success",
        "auth",
        "rate_limit",
        "client_error",
        "server_error",
        "timeout",
        "connection",
        "malformed",
        "unknown",
    )


# ---------------------------------------------------------------------------
# UPSTREAM_ERROR_TYPES
# ---------------------------------------------------------------------------


def test_upstream_error_types_match_locked_eleven_token_set():
    assert c.UPSTREAM_ERROR_TYPES == (
        "",
        "timeout",
        "connection_refused",
        "tls_error",
        "dns_error",
        "rate_limited",
        "auth_error",
        "server_error",
        "client_error",
        "malformed_response",
        "unknown_error",
    )


def test_upstream_error_type_none_is_empty_string():
    assert c.UPSTREAM_ERROR_TYPE_NONE == ""


# ---------------------------------------------------------------------------
# MALFORMED_EVENT_REASONS
# ---------------------------------------------------------------------------


def test_malformed_event_reasons_match_locked_six_token_set():
    assert c.MALFORMED_EVENT_REASONS == (
        "decode_shape_error",
        "decode_field_type_error",
        "decode_field_value_error",
        "decode_unsupported_instruction",
        "decode_suspicious_content",
        "decode_unexpected_error",
    )


# ---------------------------------------------------------------------------
# RETRY_DECISIONS
# ---------------------------------------------------------------------------


def test_retry_decisions_match_locked_three_token_set():
    assert c.RETRY_DECISIONS == (
        "retry",
        "skip",
        "abort",
    )


# ---------------------------------------------------------------------------
# DEDUPE_OUTCOMES
# ---------------------------------------------------------------------------


def test_dedupe_outcomes_match_locked_four_token_set():
    assert c.DEDUPE_OUTCOMES == (
        "new",
        "duplicate_already_dispatched",
        "duplicate_not_yet_dispatched",
        "ledger_unavailable",
    )


# ---------------------------------------------------------------------------
# INGEST_RUNNER_OUTCOMES
# ---------------------------------------------------------------------------


def test_ingest_runner_outcomes_match_locked_eight_token_set():
    assert c.INGEST_RUNNER_OUTCOMES == (
        "ok",
        "readiness_not_ready",
        "provider_failed",
        "provider_returned_zero",
        "all_malformed",
        "all_duplicates",
        "transport_refused",
        "max_attempts_exhausted",
    )


def test_all_malformed_outcome_is_present():
    # The 22.1 design-lock decision §11.2 added this token. Pin
    # its presence so a future drift surfaces here.
    assert "all_malformed" in c.INGEST_RUNNER_OUTCOMES


# ---------------------------------------------------------------------------
# Cross-set discipline
# ---------------------------------------------------------------------------


def test_every_closed_set_has_no_duplicates():
    for name, tokens in (
        ("PROVIDER_FAILURE_LABELS", c.PROVIDER_FAILURE_LABELS),
        ("STATUS_CLASSES", c.STATUS_CLASSES),
        ("UPSTREAM_ERROR_TYPES", c.UPSTREAM_ERROR_TYPES),
        ("MALFORMED_EVENT_REASONS", c.MALFORMED_EVENT_REASONS),
        ("RETRY_DECISIONS", c.RETRY_DECISIONS),
        ("DEDUPE_OUTCOMES", c.DEDUPE_OUTCOMES),
        ("INGEST_RUNNER_OUTCOMES", c.INGEST_RUNNER_OUTCOMES),
    ):
        assert len(tokens) == len(set(tokens)), (
            f"{name} contains duplicate tokens: {tokens!r}"
        )


def test_every_token_in_every_closed_set_is_shape_safe():
    """Every token (except the locked empty string in UPSTREAM_ERROR_TYPES)
    is a non-empty, ASCII lowercase + digit + underscore string <= 64 chars.
    """
    sets = (
        ("PROVIDER_FAILURE_LABELS", c.PROVIDER_FAILURE_LABELS),
        ("STATUS_CLASSES", c.STATUS_CLASSES),
        ("UPSTREAM_ERROR_TYPES", c.UPSTREAM_ERROR_TYPES),
        ("MALFORMED_EVENT_REASONS", c.MALFORMED_EVENT_REASONS),
        ("RETRY_DECISIONS", c.RETRY_DECISIONS),
        ("DEDUPE_OUTCOMES", c.DEDUPE_OUTCOMES),
        ("INGEST_RUNNER_OUTCOMES", c.INGEST_RUNNER_OUTCOMES),
    )
    for name, tokens in sets:
        for token in tokens:
            assert isinstance(token, str), (
                f"{name}: non-string token {token!r}"
            )
            # The only allowed empty string is UPSTREAM_ERROR_TYPE_NONE.
            if token == "":
                assert name == "UPSTREAM_ERROR_TYPES", (
                    f"{name}: empty token is only allowed in "
                    "UPSTREAM_ERROR_TYPES"
                )
                continue
            assert token == token.strip(), (
                f"{name}: token {token!r} has whitespace"
            )
            assert len(token) <= 64, (
                f"{name}: token {token!r} exceeds 64 chars"
            )
            # All characters must be lowercase ASCII letter, digit, or underscore.
            for ch in token:
                assert (
                    ch.isdigit()
                    or (ch.isalpha() and ch.islower() and ch.isascii())
                    or ch == "_"
                ), f"{name}: token {token!r} has disallowed char {ch!r}"


# ---------------------------------------------------------------------------
# Default retry cap
# ---------------------------------------------------------------------------


def test_default_retry_max_attempts_is_locked_positive_int():
    assert isinstance(c.DEFAULT_RETRY_MAX_ATTEMPTS, int)
    assert not isinstance(c.DEFAULT_RETRY_MAX_ATTEMPTS, bool)
    assert c.DEFAULT_RETRY_MAX_ATTEMPTS >= 1
    # 22.1 locks the cap at 3. Future sub-stages may revise.
    assert c.DEFAULT_RETRY_MAX_ATTEMPTS == 3


# ---------------------------------------------------------------------------
# Stage 22 forbidden routing tokens / explicit-allow identifiers
# ---------------------------------------------------------------------------


def test_stage22_forbidden_routing_tokens_match_locked_set():
    assert c.STAGE22_FORBIDDEN_ROUTING_TOKENS == (
        "subscriber",
        "subscribers",
        "subscriber_channel",
        "public_channel",
        "public_signal",
        "public_dispatch",
        "paid_signal",
        "paid_signals",
        "paid_channel",
        "paid_dispatch",
    )


def test_stage22_forbidden_routing_tokens_mirror_stage21_set():
    """The Stage 22 forbidden-routing tuple must match the Stage 21 set
    exactly. The Stage 22 invariant is inherited; any drift would be
    a Stage 22 design decision that must be paired with a Stage 21
    review.
    """
    from PHX2.stage21.constants import STAGE21_FORBIDDEN_ROUTING_TOKENS

    assert (
        c.STAGE22_FORBIDDEN_ROUTING_TOKENS
        == STAGE21_FORBIDDEN_ROUTING_TOKENS
    )


def test_stage22_explicit_allow_identifiers_match_locked_pair():
    assert c.STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS == (
        "safe_for_public_dispatch",
        "SAFE_FOR_PUBLIC_DISPATCH",
    )


# ---------------------------------------------------------------------------
# Stage 22 forbidden vocabulary (boundary scanner input)
# ---------------------------------------------------------------------------


def test_stage22_forbidden_vocabulary_includes_late_stage_concerns():
    forbidden = set(c.STAGE22_FORBIDDEN_VOCABULARY)
    assert {
        "scheduler",
        "daemon",
        "orchestrator",
        "run_loop",
        "worker",
        "telegram",
        "axiom",
        "jito",
        "eligibility",
    } <= forbidden


def test_stage22_forbidden_vocabulary_omits_legitimate_22_vocabulary():
    """Stage 22 is the home of retry / dedupe / capture / classify /
    ingest / failure / ledger / archive / quarantine -- those substrings
    must NOT appear in the forbidden set.
    """
    forbidden = set(c.STAGE22_FORBIDDEN_VOCABULARY)
    legitimate = {
        "retry",
        "dedupe",
        "capture",
        "classify",
        "ingest",
        "failure",
        "ledger",
        "archive",
        "quarantine",
    }
    overlap = forbidden & legitimate
    assert not overlap, (
        f"Stage 22 forbidden vocabulary illegally includes legitimate "
        f"Stage 22 vocabulary: {sorted(overlap)}"
    )
