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
    assert c.STAGE22_MINOR_VERSION == "22.4"


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


# ---------------------------------------------------------------------------
# Stage 22.2 ledger record schema constants
# ---------------------------------------------------------------------------


def test_stage22_ledger_record_schema_version_is_locked():
    assert c.STAGE22_LEDGER_RECORD_SCHEMA_VERSION == "stage22_v0_ledger"


def test_ledger_record_type_seen_token_value():
    assert c.LEDGER_RECORD_TYPE_SEEN == "seen"


def test_ledger_record_type_dispatched_token_value():
    assert c.LEDGER_RECORD_TYPE_DISPATCHED == "dispatched"


def test_ledger_record_types_match_locked_two_token_tuple():
    assert c.LEDGER_RECORD_TYPES == (
        "seen",
        "dispatched",
    )


def test_ledger_record_types_has_no_duplicates():
    assert len(c.LEDGER_RECORD_TYPES) == len(set(c.LEDGER_RECORD_TYPES))


def test_ledger_record_types_tokens_are_shape_safe():
    for token in c.LEDGER_RECORD_TYPES:
        assert isinstance(token, str)
        assert token != ""
        assert token == token.strip()
        assert len(token) <= 64
        for ch in token:
            assert (
                ch.isdigit()
                or (ch.isalpha() and ch.islower() and ch.isascii())
                or ch == "_"
            ), f"LEDGER_RECORD_TYPES token {token!r} has bad char {ch!r}"


def test_ledger_required_record_fields_match_locked_tuple():
    assert c.LEDGER_REQUIRED_RECORD_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "chain",
        "event_id",
        "provider_event_id",
        "raw_event_hash",
    )


def test_ledger_required_non_empty_fields_match_locked_tuple():
    assert c.LEDGER_REQUIRED_NON_EMPTY_FIELDS == (
        "provider_id",
        "chain",
        "event_id",
        "raw_event_hash",
    )


def test_ledger_required_non_empty_fields_is_a_subset_of_required_record_fields():
    assert set(c.LEDGER_REQUIRED_NON_EMPTY_FIELDS) <= set(
        c.LEDGER_REQUIRED_RECORD_FIELDS
    )


def test_ledger_required_record_fields_carry_no_secret_bearing_substring():
    forbidden = (
        "api_key",
        "apikey",
        "webhook",
        "rpc_url",
        "raw_response",
        "response_body",
        "exception_message",
        "exception_repr",
        "exception_args",
        "authorization",
        "bearer",
        "password",
        "secret",
        "credential",
        "private_key",
    )
    for field in c.LEDGER_REQUIRED_RECORD_FIELDS:
        lower = field.lower()
        for bad in forbidden:
            assert bad not in lower, (
                f"LEDGER_REQUIRED_RECORD_FIELDS entry {field!r} contains "
                f"forbidden secret-bearing substring {bad!r}"
            )


# ---------------------------------------------------------------------------
# Stage 22.3 raw capture record schema constants
# ---------------------------------------------------------------------------


def test_stage22_capture_record_schema_version_is_locked():
    assert c.STAGE22_CAPTURE_RECORD_SCHEMA_VERSION == "stage22_v0_capture"


def test_capture_record_type_normalized_event_token_value():
    assert c.CAPTURE_RECORD_TYPE_NORMALIZED_EVENT == "normalized_event"


def test_capture_record_type_malformed_event_token_value():
    assert c.CAPTURE_RECORD_TYPE_MALFORMED_EVENT == "malformed_event"


def test_capture_record_type_provider_failure_token_value():
    assert c.CAPTURE_RECORD_TYPE_PROVIDER_FAILURE == "provider_failure"


def test_capture_record_types_match_locked_three_token_tuple():
    assert c.CAPTURE_RECORD_TYPES == (
        "normalized_event",
        "malformed_event",
        "provider_failure",
    )


def test_capture_record_types_has_no_duplicates():
    assert len(c.CAPTURE_RECORD_TYPES) == len(set(c.CAPTURE_RECORD_TYPES))


def test_capture_record_types_tokens_are_shape_safe():
    for token in c.CAPTURE_RECORD_TYPES:
        assert isinstance(token, str)
        assert token != ""
        assert token == token.strip()
        assert len(token) <= 64
        for ch in token:
            assert (
                ch.isdigit()
                or (ch.isalpha() and ch.islower() and ch.isascii())
                or ch == "_"
            ), f"CAPTURE_RECORD_TYPES token {token!r} has bad char {ch!r}"


# ---------------------------------------------------------------------------
# Per-record-type required-field tuples
# ---------------------------------------------------------------------------


def test_capture_normalized_event_required_fields_match_locked_tuple():
    assert c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "chain",
        "event_id",
        "provider_event_id",
        "raw_event_hash",
        "received_at_utc",
        "provider_attempt_index",
        "event_type",
        "source_kind",
        "mint",
        "slot",
        "signature",
        "payload_summary",
    )


def test_capture_malformed_event_required_fields_match_locked_tuple():
    assert c.CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "provider_event_id",
        "reason",
        "failed_at_utc",
        "raw_event_hash",
    )


def test_capture_provider_failure_required_fields_match_locked_tuple():
    assert c.CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "failure_label",
        "status_class",
        "upstream_error_type",
        "provider_attempt_index",
        "observed_at_utc",
    )


def test_capture_required_field_tuples_have_no_duplicates_within_tuple():
    for name, fields in (
        (
            "CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS",
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
        ),
        (
            "CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS",
            c.CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS,
        ),
        (
            "CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS",
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
        ),
    ):
        assert len(fields) == len(set(fields)), (
            f"{name} contains duplicate field names"
        )


def test_capture_normalized_event_required_fields_drops_instruction_kind():
    """Stage 22.3 deliberately does NOT capture ``instruction_kind`` --
    the field does not exist on ``NormalizedLiveEvent``; it is a
    Stage 23+ on-chain-filter vocabulary item.
    """
    assert "instruction_kind" not in c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS


def test_capture_normalized_event_required_fields_drops_normalized_schema_version():
    """Stage 22.3 does not duplicate the Stage 21 event-side
    schema_version into the capture record; the capture record
    has its own ``schema_version`` axis.
    """
    assert (
        "normalized_schema_version"
        not in c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS
    )


def test_capture_required_tuples_carry_no_secret_bearing_substring():
    forbidden = (
        "api_key",
        "apikey",
        "webhook",
        "rpc_url",
        "raw_response",
        "response_body",
        "exception_message",
        "exception_repr",
        "exception_args",
        "authorization",
        "bearer",
        "password",
        "credential",
        "private_key",
    )
    for fields in (
        c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
        c.CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS,
        c.CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
    ):
        for field in fields:
            lower = field.lower()
            for bad in forbidden:
                assert bad not in lower, (
                    f"capture required field {field!r} contains "
                    f"forbidden secret-bearing substring {bad!r}"
                )


# ---------------------------------------------------------------------------
# Per-record-type required non-empty-string and int field tuples
# ---------------------------------------------------------------------------


def test_capture_normalized_event_required_non_empty_string_fields_match_locked_tuple():
    assert c.CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "chain",
        "event_id",
        "raw_event_hash",
        "received_at_utc",
        "event_type",
        "source_kind",
        "mint",
        "signature",
    )


def test_capture_malformed_event_required_non_empty_string_fields_match_locked_tuple():
    assert c.CAPTURE_MALFORMED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "reason",
        "failed_at_utc",
        "raw_event_hash",
    )


def test_capture_provider_failure_required_non_empty_string_fields_match_locked_tuple():
    assert c.CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS == (
        "schema_version",
        "record_type",
        "provider_id",
        "failure_label",
        "status_class",
        "upstream_error_type",
        "observed_at_utc",
    )


def test_capture_normalized_event_required_int_fields_match_locked_tuple():
    assert c.CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS == (
        "provider_attempt_index",
        "slot",
    )


def test_capture_provider_failure_required_int_fields_match_locked_tuple():
    assert c.CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS == (
        "provider_attempt_index",
    )


def test_capture_required_non_empty_string_fields_are_subset_of_required_fields():
    pairs = (
        (
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS,
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
        ),
        (
            c.CAPTURE_MALFORMED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS,
            c.CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS,
        ),
        (
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS,
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
        ),
    )
    for non_empty, all_fields in pairs:
        assert set(non_empty) <= set(all_fields)


def test_capture_required_int_fields_are_subset_of_required_fields():
    pairs = (
        (
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS,
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
        ),
        (
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS,
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
        ),
    )
    for int_fields, all_fields in pairs:
        assert set(int_fields) <= set(all_fields)


def test_capture_required_non_empty_string_fields_and_int_fields_are_disjoint():
    pairs = (
        (
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS,
            c.CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS,
        ),
        (
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS,
            c.CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS,
        ),
    )
    for non_empty, int_fields in pairs:
        assert set(non_empty).isdisjoint(set(int_fields))


# ---------------------------------------------------------------------------
# Sanitiser caps
# ---------------------------------------------------------------------------


def test_capture_payload_summary_max_keys_is_locked():
    assert c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS == 16
    assert isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS, int)
    assert not isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS, bool)


def test_capture_payload_summary_max_key_len_is_locked():
    assert c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN == 64
    assert isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN, int)
    assert not isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN, bool)


def test_capture_payload_summary_max_string_len_is_locked():
    assert c.CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN == 512
    assert isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN, int)
    assert not isinstance(c.CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN, bool)


def test_capture_long_hex_run_min_len_is_locked():
    assert c.CAPTURE_LONG_HEX_RUN_MIN_LEN == 40
    assert isinstance(c.CAPTURE_LONG_HEX_RUN_MIN_LEN, int)
    assert not isinstance(c.CAPTURE_LONG_HEX_RUN_MIN_LEN, bool)


def test_capture_long_tokenish_min_len_is_locked():
    assert c.CAPTURE_LONG_TOKENISH_MIN_LEN == 32
    assert isinstance(c.CAPTURE_LONG_TOKENISH_MIN_LEN, int)
    assert not isinstance(c.CAPTURE_LONG_TOKENISH_MIN_LEN, bool)


# ---------------------------------------------------------------------------
# Forbidden URL / secret-key sanitiser inputs
# ---------------------------------------------------------------------------


def test_capture_forbidden_url_substrings_match_locked_assembled_values():
    expected = (
        "http" + ":" + "//",
        "https" + ":" + "//",
        "ws" + ":" + "//",
        "wss" + ":" + "//",
        ":" + "//",
        "discord" + "." + "com",
        "discordapp" + "." + "com",
        "hooks" + ".slack" + "." + "com",
    )
    assert c.CAPTURE_FORBIDDEN_URL_SUBSTRINGS == expected


def test_capture_forbidden_url_substrings_has_no_duplicates():
    assert len(c.CAPTURE_FORBIDDEN_URL_SUBSTRINGS) == len(
        set(c.CAPTURE_FORBIDDEN_URL_SUBSTRINGS)
    )


def test_capture_forbidden_secret_key_substrings_match_locked_set():
    assert c.CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS == (
        "api_key",
        "apikey",
        "webhook_url",
        "webhook",
        "rpc_url",
        "raw_response_body",
        "raw_response",
        "response_body",
        "exception_message",
        "exception_repr",
        "exception_args",
        "headers",
        "authorization",
        "bearer",
        "password",
        "secret",
        "credential",
        "credentials",
        "private_key",
        "privatekey",
    )


def test_capture_forbidden_secret_key_substrings_has_no_duplicates():
    assert len(c.CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS) == len(
        set(c.CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS)
    )
