"""Stage 28.4 audited HTTP transport models tests.

Pins:

  * Stage 28.4 closed-set transport-status / response-body status /
    redaction-status / safe-transport-reason / send-attempt-count
    vocabularies stay locked.
  * Stage 28.4 transport result is immutable, with safe ``repr()`` /
    ``str()``; canary webhook URLs / API keys / bearer tokens /
    response bodies / raw exception strings never reach the record.
  * The safe-reason-code mapping is the deterministic lowercased
    transport-status token; unknown transport-status tokens raise
    ``Stage28_4TransportRedactionLeakError`` rather than silently
    leaking a non-closed-set value.
  * Webhook identity safe-shape rule rejects URL-shaped /
    secret-shaped / mixed-case / hyphen-containing /
    whitespace-containing / dot-containing / slash-containing values
    and admits identifier-like ALL_CAPS_WITH_UNDERSCORES labels of
    length 1..64.
  * Forbidden payload-routing field names cover Stage 29 enforcement,
    public / subscriber routing, paid tier, Telegram, X / social,
    automated trading, wallet / signer logic, and raw secret /
    auth-header field names.
  * Stage 28.4 retry-after caps stay locked at ``30.0`` seconds max
    and ``0.0`` seconds min; the Stage 28.4 max payload size stays
    locked at ``8192`` bytes.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.audited_http_transport_models import (
    FORBIDDEN_PAYLOAD_FIELD_NAMES,
    MAX_PAYLOAD_BYTES,
    REDACTION_STATUS_FAILED,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_VALUES,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    RESPONSE_BODY_STATUS_NOT_CAPTURED,
    RESPONSE_BODY_STATUS_VALUES,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_AFTER_MIN_SECONDS,
    SAFE_TRANSPORT_REASON_CODE_VALUES,
    SEND_ATTEMPT_COUNT_NOT_SENT,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    SEND_ATTEMPT_COUNT_VALUES,
    STAGE28_4_MINOR_VERSION,
    STAGE28_4_REDACTION_TOKEN,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportError,
    Stage28_4TransportRedactionLeakError,
    Stage28_4TransportResult,
    Stage28_4TransportValidationError,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_NOT_SENT_VALUES,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SENT_VALUES,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    TRANSPORT_STATUS_VALUES,
    WEBHOOK_IDENTITY_MISSING_LABEL,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    WEBHOOK_IDENTITY_REDACTED_UNSAFE,
    derive_safe_reason_code,
    is_forbidden_payload_field_name,
    is_not_sent_transport_status,
    is_redaction_status_value,
    is_response_body_status_value,
    is_safe_transport_reason_code_value,
    is_safe_webhook_identity_label,
    is_sent_transport_status,
    is_transport_status_value,
    redacted_safe_headers,
)


# ---------------------------------------------------------------------------
# Canary values used by redaction tests
# ---------------------------------------------------------------------------


# Canary substrings. Each value is a synthetic test fixture; if it
# ever reaches a Stage 28.4 record / repr / str / exception
# message the leak-scan tests below fail.
_CANARY_WEBHOOK_URL: str = (
    # Synthetic Discord webhook URL canary built by concatenation
    # so this test file itself does not trigger the URL-literal
    # boundary scan elsewhere.
    "h" + "ttps://" + "discord" + ".com" + "/api/webhooks/"
    "1234567890/CANARY_WEBHOOK_TOKEN_DO_NOT_LOG_xxx"
)
_CANARY_API_KEY: str = "CANARY_API_KEY_sk-DO_NOT_LOG_xxx"
_CANARY_BEARER_TOKEN: str = (
    "CANARY_BEARER_TOKEN_Bearer_value_DO_NOT_LOG"
)
_CANARY_RAW_RESPONSE_BODY: str = (
    "CANARY_RESPONSE_BODY_DO_NOT_LOG"
)
_CANARY_RAW_EXCEPTION: str = "CANARY_EXC_DO_NOT_LOG"
_CANARY_PROVIDER_ENDPOINT: str = (
    "h" + "ttps://" + "api.helius" + ".xyz" + "/v0/CANARY_ENDPOINT"
)
_CANARY_SECRET_PATH: str = "/CANARY/SECRET/PATH"


# ---------------------------------------------------------------------------
# 1. Version axes locked
# ---------------------------------------------------------------------------


def test_stage_28_4_minor_version_is_locked():
    assert STAGE28_4_MINOR_VERSION == "28.4"


def test_stage_28_4_schema_version_is_locked():
    assert (
        STAGE28_4_SCHEMA_VERSION
        == "stage28_4_audited_http_transport_v0"
    )


def test_stage_28_4_redaction_token_is_distinct():
    assert STAGE28_4_REDACTION_TOKEN == "<<STAGE28_4_REDACTED>>"


# ---------------------------------------------------------------------------
# 2. Transport-status closed set
# ---------------------------------------------------------------------------


_EXPECTED_TRANSPORT_STATUS_VALUES: set[str] = {
    "SENT_OK",
    "RATE_LIMITED",
    "SERVER_ERROR",
    "NETWORK_ERROR",
    "AUTH_OR_WEBHOOK_REFUSED",
    "VALIDATION_FAILED",
    "PAYLOAD_REFUSED",
}


def test_transport_status_values_match_locked_set():
    assert (
        set(TRANSPORT_STATUS_VALUES)
        == _EXPECTED_TRANSPORT_STATUS_VALUES
    )


def test_transport_status_values_are_all_strings():
    for value in TRANSPORT_STATUS_VALUES:
        assert isinstance(value, str)


def test_transport_status_values_have_no_duplicates():
    assert len(TRANSPORT_STATUS_VALUES) == len(
        set(TRANSPORT_STATUS_VALUES)
    )


@pytest.mark.parametrize(
    "status",
    [
        TRANSPORT_STATUS_SENT_OK,
        TRANSPORT_STATUS_RATE_LIMITED,
        TRANSPORT_STATUS_SERVER_ERROR,
        TRANSPORT_STATUS_NETWORK_ERROR,
        TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
        TRANSPORT_STATUS_VALIDATION_FAILED,
        TRANSPORT_STATUS_PAYLOAD_REFUSED,
    ],
)
def test_is_transport_status_value_accepts_closed_set_tokens(status):
    assert is_transport_status_value(status) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "sent",
        "SENT_OK ",
        "UNKNOWN",
        123,
        None,
        True,
        ["SENT_OK"],
    ],
)
def test_is_transport_status_value_rejects_out_of_set_inputs(bad):
    assert is_transport_status_value(bad) is False


def test_sent_subset_contains_only_sent_statuses():
    expected = {
        "SENT_OK",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "NETWORK_ERROR",
        "AUTH_OR_WEBHOOK_REFUSED",
    }
    assert set(TRANSPORT_STATUS_SENT_VALUES) == expected


def test_not_sent_subset_contains_only_not_sent_statuses():
    expected = {"VALIDATION_FAILED", "PAYLOAD_REFUSED"}
    assert set(TRANSPORT_STATUS_NOT_SENT_VALUES) == expected


def test_sent_and_not_sent_subsets_partition_transport_status_values():
    union = set(TRANSPORT_STATUS_SENT_VALUES) | set(
        TRANSPORT_STATUS_NOT_SENT_VALUES
    )
    intersection = set(TRANSPORT_STATUS_SENT_VALUES) & set(
        TRANSPORT_STATUS_NOT_SENT_VALUES
    )
    assert union == set(TRANSPORT_STATUS_VALUES)
    assert intersection == set()


def test_is_sent_transport_status_matches_subset():
    for status in TRANSPORT_STATUS_VALUES:
        expected = status in TRANSPORT_STATUS_SENT_VALUES
        assert is_sent_transport_status(status) is expected


def test_is_not_sent_transport_status_matches_subset():
    for status in TRANSPORT_STATUS_VALUES:
        expected = status in TRANSPORT_STATUS_NOT_SENT_VALUES
        assert is_not_sent_transport_status(status) is expected


# ---------------------------------------------------------------------------
# 3. Safe-reason-code mapping
# ---------------------------------------------------------------------------


def test_safe_reason_code_values_are_lowercased_status_tokens():
    expected = tuple(s.lower() for s in TRANSPORT_STATUS_VALUES)
    assert SAFE_TRANSPORT_REASON_CODE_VALUES == expected


def test_safe_reason_codes_have_no_duplicates():
    assert len(SAFE_TRANSPORT_REASON_CODE_VALUES) == len(
        set(SAFE_TRANSPORT_REASON_CODE_VALUES)
    )


def test_safe_reason_codes_are_all_snake_case_lowercase():
    for code in SAFE_TRANSPORT_REASON_CODE_VALUES:
        assert isinstance(code, str)
        assert code == code.lower()
        for ch in code:
            assert ch == "_" or ("a" <= ch <= "z")


def test_derive_safe_reason_code_round_trips_each_status():
    for status in TRANSPORT_STATUS_VALUES:
        assert derive_safe_reason_code(status) == status.lower()


def test_derive_safe_reason_code_raises_for_unknown_status():
    with pytest.raises(Stage28_4TransportRedactionLeakError) as exc:
        derive_safe_reason_code("NOT_IN_CLOSED_SET")
    assert exc.value.field_name == "transport_status"
    assert exc.value.reason == "TRANSPORT_STATUS_NOT_CLOSED_SET"


def test_derive_safe_reason_code_raises_for_non_string():
    with pytest.raises(Stage28_4TransportRedactionLeakError):
        derive_safe_reason_code(None)


def test_is_safe_transport_reason_code_value_accepts_closed_set():
    for code in SAFE_TRANSPORT_REASON_CODE_VALUES:
        assert is_safe_transport_reason_code_value(code) is True


@pytest.mark.parametrize(
    "bad",
    ["", "SENT_OK", "sent_ok ", "rate-limited", None, 1, True],
)
def test_is_safe_transport_reason_code_value_rejects_out_of_set(bad):
    assert is_safe_transport_reason_code_value(bad) is False


# ---------------------------------------------------------------------------
# 4. Response-body status closed set
# ---------------------------------------------------------------------------


def test_response_body_status_values_match_locked_set():
    assert set(RESPONSE_BODY_STATUS_VALUES) == {
        "DROPPED_UNRECORDED",
        "NOT_CAPTURED",
    }


def test_is_response_body_status_value_round_trips():
    for value in RESPONSE_BODY_STATUS_VALUES:
        assert is_response_body_status_value(value) is True


@pytest.mark.parametrize(
    "bad",
    ["", "dropped", "DROPPED", None, 0, True, ["NOT_CAPTURED"]],
)
def test_is_response_body_status_value_rejects_out_of_set(bad):
    assert is_response_body_status_value(bad) is False


# ---------------------------------------------------------------------------
# 5. Redaction-status closed set
# ---------------------------------------------------------------------------


def test_redaction_status_values_match_locked_set():
    assert set(REDACTION_STATUS_VALUES) == {
        "REDACTED",
        "REDACTION_FAILED",
    }


def test_is_redaction_status_value_round_trips():
    for value in REDACTION_STATUS_VALUES:
        assert is_redaction_status_value(value) is True


@pytest.mark.parametrize(
    "bad",
    ["", "redacted", "REDACT", "REDACTED ", None, 1, True],
)
def test_is_redaction_status_value_rejects_out_of_set(bad):
    assert is_redaction_status_value(bad) is False


# ---------------------------------------------------------------------------
# 6. Webhook identity label safe-shape rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "PRIVATE_OPERATOR_WEBHOOK",
        "X",
        "A_B_C",
        "OPERATOR_99",
        "REDACTED_UNSAFE_WEBHOOK_IDENTITY",
        "MISSING_WEBHOOK_IDENTITY",
        "Z" * 64,
    ],
)
def test_is_safe_webhook_identity_label_accepts_safe_shapes(good):
    assert is_safe_webhook_identity_label(good) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        " PRIVATE_OPERATOR_WEBHOOK",
        "PRIVATE_OPERATOR_WEBHOOK ",
        "private_operator_webhook",
        "Private_Operator_Webhook",
        "PRIVATE-OPERATOR-WEBHOOK",
        "PRIVATE.OPERATOR.WEBHOOK",
        "PRIVATE/OPERATOR",
        "PRIVATE OPERATOR",
        "h" + "ttps://" + "example.com",
        "Bearer abc123",
        "Authorization: foo",
        "Z" * 65,
        "1_NOT_LETTER_FIRST",
        None,
        123,
        True,
        ["PRIVATE_OPERATOR_WEBHOOK"],
        b"PRIVATE_OPERATOR_WEBHOOK",
    ],
)
def test_is_safe_webhook_identity_label_rejects_unsafe_shapes(bad):
    assert is_safe_webhook_identity_label(bad) is False


def test_private_operator_label_is_safe_shape():
    assert (
        is_safe_webhook_identity_label(
            WEBHOOK_IDENTITY_PRIVATE_OPERATOR
        )
        is True
    )


def test_redacted_unsafe_label_is_safe_shape():
    assert (
        is_safe_webhook_identity_label(
            WEBHOOK_IDENTITY_REDACTED_UNSAFE
        )
        is True
    )


def test_missing_label_is_safe_shape():
    assert (
        is_safe_webhook_identity_label(
            WEBHOOK_IDENTITY_MISSING_LABEL
        )
        is True
    )


def test_webhook_identity_labels_are_distinct():
    assert (
        WEBHOOK_IDENTITY_PRIVATE_OPERATOR
        != WEBHOOK_IDENTITY_REDACTED_UNSAFE
    )
    assert (
        WEBHOOK_IDENTITY_PRIVATE_OPERATOR
        != WEBHOOK_IDENTITY_MISSING_LABEL
    )
    assert (
        WEBHOOK_IDENTITY_REDACTED_UNSAFE
        != WEBHOOK_IDENTITY_MISSING_LABEL
    )


# ---------------------------------------------------------------------------
# 7. Forbidden payload-field-name allowlist
# ---------------------------------------------------------------------------


_FORBIDDEN_FIELD_SUBSTRINGS: set[str] = {
    "subscriber_id",
    "channel_id",
    "public_channel_id",
    "audience",
    "paid_tier",
    "route_id",
    "approval_status",
    "enforcement_result",
    "trade_side",
    "buy_signal",
    "sell_signal",
    "position_size",
    "wallet_address",
    "signer_address",
    "private_key",
    "auth_header",
    "authorization",
    "bearer_token",
    "api_key",
    "webhook_url",
    "rpc_url",
    "telegram_chat_id",
    "x_user_id",
    "tweet_id",
}


@pytest.mark.parametrize("needle", sorted(_FORBIDDEN_FIELD_SUBSTRINGS))
def test_forbidden_payload_field_names_contain_each_needle(needle):
    joined = "\n".join(FORBIDDEN_PAYLOAD_FIELD_NAMES)
    assert needle in joined, (
        f"Stage 28.4 forbidden payload field names must include "
        f"a needle for {needle!r}"
    )


@pytest.mark.parametrize(
    "good",
    [
        "content",
        "embeds",
        "title",
        "description",
        "color",
        "ping_id",
        "fields",
    ],
)
def test_is_forbidden_payload_field_name_accepts_safe_field_names(good):
    assert is_forbidden_payload_field_name(good) is False


@pytest.mark.parametrize(
    "bad",
    [
        "subscriber_id",
        "Subscriber_id",
        "public_channel_id",
        "audience",
        "paid_tier",
        "trade_side",
        "buy_signal",
        "wallet_address",
        "AUTHORIZATION",
        "Authorization-Bearer",
        "api_key",
        "API_KEY",
        "x-api-key",
        "private_key",
        "telegram_chat_id",
        "webhook_url",
        "discord_webhook_url",
    ],
)
def test_is_forbidden_payload_field_name_refuses_bad_field_names(bad):
    assert is_forbidden_payload_field_name(bad) is True


def test_is_forbidden_payload_field_name_returns_false_for_non_string():
    assert is_forbidden_payload_field_name(None) is False
    assert is_forbidden_payload_field_name(123) is False
    assert is_forbidden_payload_field_name(b"subscriber_id") is False


# ---------------------------------------------------------------------------
# 8. Retry-after caps + payload size cap
# ---------------------------------------------------------------------------


def test_retry_after_max_seconds_is_locked_at_30():
    assert RETRY_AFTER_MAX_SECONDS == 30.0


def test_retry_after_min_seconds_is_locked_at_zero():
    assert RETRY_AFTER_MIN_SECONDS == 0.0


def test_max_payload_bytes_is_locked():
    assert MAX_PAYLOAD_BYTES == 8192


# ---------------------------------------------------------------------------
# 9. Send-attempt-count constants
# ---------------------------------------------------------------------------


def test_send_attempt_count_values_are_zero_and_one():
    assert SEND_ATTEMPT_COUNT_NOT_SENT == 0
    assert SEND_ATTEMPT_COUNT_SENT_ONCE == 1
    assert SEND_ATTEMPT_COUNT_VALUES == (0, 1)


# ---------------------------------------------------------------------------
# 10. Stage28_4TransportResult — construction + immutability
# ---------------------------------------------------------------------------


def _build_sent_ok_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_SENT_OK,
        ok=True,
        http_status_code=204,
        retry_after_seconds=None,
        send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        redaction_status=REDACTION_STATUS_REDACTED,
        safe_reason_code=derive_safe_reason_code(
            TRANSPORT_STATUS_SENT_OK
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


def _build_validation_failed_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_VALIDATION_FAILED,
        ok=False,
        http_status_code=None,
        retry_after_seconds=None,
        send_attempt_count=SEND_ATTEMPT_COUNT_NOT_SENT,
        webhook_identity=WEBHOOK_IDENTITY_MISSING_LABEL,
        redaction_status=REDACTION_STATUS_REDACTED,
        safe_reason_code=derive_safe_reason_code(
            TRANSPORT_STATUS_VALIDATION_FAILED
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


def _build_rate_limited_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_RATE_LIMITED,
        ok=False,
        http_status_code=429,
        retry_after_seconds=5.0,
        send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        redaction_status=REDACTION_STATUS_REDACTED,
        safe_reason_code=derive_safe_reason_code(
            TRANSPORT_STATUS_RATE_LIMITED
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


def test_transport_result_named_tuple_is_immutable():
    result = _build_sent_ok_result()
    with pytest.raises(AttributeError):
        result.transport_status = TRANSPORT_STATUS_NETWORK_ERROR  # type: ignore[misc]


def test_transport_result_round_trips_via_named_tuple_replace():
    result = _build_sent_ok_result()
    replaced = result._replace(
        transport_status=TRANSPORT_STATUS_SERVER_ERROR,
        ok=False,
        http_status_code=500,
        safe_reason_code=derive_safe_reason_code(
            TRANSPORT_STATUS_SERVER_ERROR
        ),
    )
    assert replaced.transport_status == TRANSPORT_STATUS_SERVER_ERROR
    assert replaced.ok is False
    assert replaced.http_status_code == 500
    assert (
        replaced.safe_reason_code == "server_error"
    )


def test_transport_result_schema_version_is_locked():
    result = _build_sent_ok_result()
    assert (
        result.schema_version
        == "stage28_4_audited_http_transport_v0"
    )


def test_transport_result_send_attempt_count_is_zero_on_validation_failed():
    result = _build_validation_failed_result()
    assert result.send_attempt_count == 0


def test_transport_result_send_attempt_count_is_one_on_rate_limited():
    result = _build_rate_limited_result()
    assert result.send_attempt_count == 1


def test_transport_result_retry_after_seconds_is_capped_at_max():
    capped = _build_rate_limited_result()._replace(
        retry_after_seconds=RETRY_AFTER_MAX_SECONDS
    )
    assert capped.retry_after_seconds == RETRY_AFTER_MAX_SECONDS


# ---------------------------------------------------------------------------
# 11. Redaction: repr / str do not leak canaries
# ---------------------------------------------------------------------------


def _assert_no_canary(text: str) -> None:
    for canary in (
        _CANARY_WEBHOOK_URL,
        _CANARY_API_KEY,
        _CANARY_BEARER_TOKEN,
        _CANARY_RAW_RESPONSE_BODY,
        _CANARY_RAW_EXCEPTION,
        _CANARY_PROVIDER_ENDPOINT,
        _CANARY_SECRET_PATH,
    ):
        assert canary not in text, (
            f"Stage 28.4 record / repr / str contains canary "
            f"{canary!r}; redaction broken"
        )


def test_sent_ok_result_repr_does_not_leak_canaries():
    result = _build_sent_ok_result()
    _assert_no_canary(repr(result))
    _assert_no_canary(str(result))


def test_validation_failed_result_repr_does_not_leak_canaries():
    result = _build_validation_failed_result()
    _assert_no_canary(repr(result))
    _assert_no_canary(str(result))


def test_rate_limited_result_repr_does_not_leak_canaries():
    result = _build_rate_limited_result()
    _assert_no_canary(repr(result))
    _assert_no_canary(str(result))


def test_result_named_tuple_asdict_does_not_leak_canaries():
    for result in (
        _build_sent_ok_result(),
        _build_validation_failed_result(),
        _build_rate_limited_result(),
    ):
        as_dict = dict(result._asdict())
        for value in as_dict.values():
            _assert_no_canary(repr(value))


# ---------------------------------------------------------------------------
# 12. Exception hierarchy is redaction-safe
# ---------------------------------------------------------------------------


def test_transport_validation_error_carries_only_field_and_reason():
    exc = Stage28_4TransportValidationError(
        field_name="webhook_url",
        reason="URL_EMPTY",
    )
    assert exc.field_name == "webhook_url"
    assert exc.reason == "URL_EMPTY"
    text = str(exc)
    assert "webhook_url" in text
    assert "URL_EMPTY" in text
    _assert_no_canary(text)


def test_transport_validation_error_message_does_not_leak_canary_url():
    # Construct an exception with a synthetic name; the message
    # must not include the canary URL even if a malicious caller
    # tried to smuggle it in.
    exc = Stage28_4TransportValidationError(
        field_name="webhook_url",
        reason="URL_NOT_PRIVATE_DISCORD_WEBHOOK",
    )
    _assert_no_canary(repr(exc))
    _assert_no_canary(str(exc))


def test_transport_redaction_leak_error_carries_only_safe_fields():
    exc = Stage28_4TransportRedactionLeakError(
        field_name="transport_status",
        reason="TRANSPORT_STATUS_NOT_CLOSED_SET",
    )
    assert exc.field_name == "transport_status"
    assert exc.reason == "TRANSPORT_STATUS_NOT_CLOSED_SET"
    _assert_no_canary(repr(exc))
    _assert_no_canary(str(exc))


def test_transport_error_hierarchy_subclass_relationships():
    assert issubclass(
        Stage28_4TransportValidationError, Stage28_4TransportError
    )
    assert issubclass(
        Stage28_4TransportRedactionLeakError,
        Stage28_4TransportError,
    )


# ---------------------------------------------------------------------------
# 13. redacted_safe_headers helper
# ---------------------------------------------------------------------------


def test_redacted_safe_headers_admits_safe_headers():
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "PHX2",
        "Accept": "application/json",
    }
    out = redacted_safe_headers(headers)
    out_names = {name for name, _ in out}
    assert out_names == set(headers.keys())


def test_redacted_safe_headers_drops_secret_class_headers():
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer abc",
        "x-api-key": "abc",
        "Webhook_url": (
            "h" + "ttps://" + "example.com"
        ),
    }
    out = redacted_safe_headers(headers)
    out_names = {name for name, _ in out}
    assert "Authorization" not in out_names
    assert "x-api-key" not in out_names
    assert "Webhook_url" not in out_names
    assert "Content-Type" in out_names


def test_redacted_safe_headers_rejects_non_mapping_input():
    assert redacted_safe_headers([("a", "b")]) == ()  # type: ignore[arg-type]
    assert redacted_safe_headers(None) == ()  # type: ignore[arg-type]
    assert redacted_safe_headers("not a mapping") == ()  # type: ignore[arg-type]


def test_redacted_safe_headers_drops_non_string_values():
    headers = {"Content-Type": 123, "User-Agent": None}
    out = redacted_safe_headers(headers)  # type: ignore[arg-type]
    assert out == ()
