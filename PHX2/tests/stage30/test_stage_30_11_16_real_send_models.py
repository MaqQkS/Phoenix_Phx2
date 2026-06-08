"""Stage 30.11.16 real-send guard model tests.

Offline only. Pins the closed-set decision / reason vocabularies, the dataclass
field tuples, and the pure safe-shape predicates: the authorization sentinel
validator (valid passes; missing / wrong confirm token / ``authorized`` not
``True`` / wrong type / blank tokens fail), the locked private-operator target
identity / visibility, and the minimal ``{"content": ...}`` payload allowlist.

No real send, no network, no env read, no wallet, no trading.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_16_real_send_models import (
    REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
    REAL_SEND_DECISION_REFUSED,
    REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT,
    REAL_SEND_REASON_CAP_EXHAUSTED,
    REAL_SEND_REASON_TRANSPORT_EXCEPTION,
    STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN,
    STAGE30_11_16_MAX_DISPATCHES,
    STAGE30_11_16_PAYLOAD_CONTENT_KEY,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
    STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    STAGE30_11_16_REAL_SEND_DECISIONS,
    STAGE30_11_16_REAL_SEND_REASONS,
    STAGE30_11_16_REQUIRED_COMPOSE_DECISION,
    Stage30_11_16RealSendAuthorization,
    Stage30_11_16RealSendResult,
    Stage30_11_16TransportTarget,
    is_minimal_content_payload,
    is_private_operator_identity,
    is_real_send_authorization,
    is_real_send_decision,
    is_real_send_reason,
    is_safe_operator_token,
    is_valid_transport_target,
    real_send_authorization_field_names,
    real_send_result_field_names,
    transport_target_field_names,
)


def _valid_auth(**overrides) -> Stage30_11_16RealSendAuthorization:
    base = dict(
        authorized=True,
        confirm_token=STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN,
        operator_label="OPERATOR_CONTROLLED_CEREMONY",
        authorization_reason="STAGE_30_11_16_CONTROLLED_ONE_SEND",
        created_at_utc="2026-06-07T07:06:40Z",
    )
    base.update(overrides)
    return Stage30_11_16RealSendAuthorization(**base)


# ---------------------------------------------------------------------------
# 1. Closed-set decision / reason vocab
# ---------------------------------------------------------------------------


def test_decisions_pinned() -> None:
    assert STAGE30_11_16_REAL_SEND_DECISIONS == (
        "WOULD_SEND_NO_TRANSPORT",
        "FORWARDED_TO_TRANSPORT",
        "REFUSED",
    )


def test_reasons_pinned() -> None:
    assert STAGE30_11_16_REAL_SEND_REASONS == (
        "WOULD_SEND_RECORDED_NO_TRANSPORT",
        "FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE",
        "NOT_AUTHORIZED",
        "INVALID_AUTHORIZATION_TYPE",
        "INVALID_COMPOSE_RESULT",
        "COMPOSE_NOT_DISPATCHED",
        "DEDUPE_NOT_ALLOWED",
        "SNAPSHOT_MISSING",
        "INVALID_SNAPSHOT_PROVENANCE",
        "BODY_MISSING",
        "INVALID_TARGET_IDENTITY",
        "FORBIDDEN_PAYLOAD_FIELD",
        "CAP_EXHAUSTED",
        "TRANSPORT_EXCEPTION",
    )


def test_decision_and_reason_predicates() -> None:
    for d in STAGE30_11_16_REAL_SEND_DECISIONS:
        assert is_real_send_decision(d)
    for r in STAGE30_11_16_REAL_SEND_REASONS:
        assert is_real_send_reason(r)
    assert not is_real_send_decision("NOPE")
    assert not is_real_send_decision(7)
    assert not is_real_send_reason("NOPE")


def test_locked_constants_pinned() -> None:
    assert STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY == "PRIVATE_OPERATOR_WEBHOOK"
    assert STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY == "PRIVATE_OPERATOR_ONLY"
    assert STAGE30_11_16_PAYLOAD_CONTENT_KEY == "content"
    assert STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN == (
        "I_AUTHORIZE_ONE_REAL_PRIVATE_OPERATOR_SEND"
    )
    assert STAGE30_11_16_REQUIRED_COMPOSE_DECISION == "NO_SEND_DISPATCHED"
    assert STAGE30_11_16_MAX_DISPATCHES == 1


# ---------------------------------------------------------------------------
# 2. Field tuples pinned
# ---------------------------------------------------------------------------


def test_authorization_fields_pinned() -> None:
    assert real_send_authorization_field_names() == (
        "authorized",
        "confirm_token",
        "operator_label",
        "authorization_reason",
        "created_at_utc",
    )


def test_transport_target_fields_pinned() -> None:
    assert transport_target_field_names() == ("webhook_identity", "visibility")


def test_real_send_result_fields_pinned() -> None:
    assert real_send_result_field_names() == (
        "decision",
        "reason",
        "token_mint",
        "candidate_id",
        "dispatch_forwarded",
        "transport_attempted",
        "transport_status",
        "transport_ok",
        "webhook_identity",
        "cap_consumed",
        "redaction_status",
        "created_at_utc",
    )


def test_result_carries_no_body_url_or_secret_field_names() -> None:
    for name in real_send_result_field_names():
        lower = name.lower()
        for forbidden in ("body", "url", "secret", "webhook_url", "content"):
            assert forbidden not in lower, (
                f"result field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 3. Authorization sentinel validation
# ---------------------------------------------------------------------------


def test_valid_authorization_passes() -> None:
    assert is_real_send_authorization(_valid_auth())


def test_missing_or_wrong_confirm_token_fails() -> None:
    assert not is_real_send_authorization(_valid_auth(confirm_token="nope"))
    assert not is_real_send_authorization(_valid_auth(confirm_token=""))
    # A near-miss token must not pass.
    assert not is_real_send_authorization(
        _valid_auth(confirm_token="I_AUTHORIZE_ONE_REAL_PRIVATE_OPERATOR_SENT")
    )


def test_authorized_not_true_fails() -> None:
    assert not is_real_send_authorization(_valid_auth(authorized=False))
    # A truthy-but-not-True value must not pass (identity check, not truthiness).
    assert not is_real_send_authorization(_valid_auth(authorized=1))


def test_wrong_authorization_type_fails() -> None:
    assert not is_real_send_authorization(None)
    assert not is_real_send_authorization("not-a-sentinel")
    assert not is_real_send_authorization(object())


def test_blank_or_unsafe_labels_fail() -> None:
    assert not is_real_send_authorization(_valid_auth(operator_label=""))
    assert not is_real_send_authorization(_valid_auth(operator_label="lower"))
    assert not is_real_send_authorization(
        _valid_auth(authorization_reason="")
    )
    assert not is_real_send_authorization(_valid_auth(created_at_utc=""))
    assert not is_real_send_authorization(_valid_auth(created_at_utc="   "))


# ---------------------------------------------------------------------------
# 4. Safe operator token + private-operator identity
# ---------------------------------------------------------------------------


def test_safe_operator_token_shape() -> None:
    assert is_safe_operator_token("PRIVATE_OPERATOR_WEBHOOK")
    assert is_safe_operator_token("A")
    assert not is_safe_operator_token("")
    assert not is_safe_operator_token("lowerstart")
    assert not is_safe_operator_token("1LEADING_DIGIT")
    assert not is_safe_operator_token("HAS SPACE")
    assert not is_safe_operator_token("HAS/SLASH")
    assert not is_safe_operator_token("HAS.DOT")
    assert not is_safe_operator_token("X" * 65)
    assert not is_safe_operator_token(7)


def test_private_operator_identity_is_locked() -> None:
    assert is_private_operator_identity("PRIVATE_OPERATOR_WEBHOOK")
    # A safe-shape but different identity is rejected (private-only).
    assert not is_private_operator_identity("PUBLIC_BROADCAST_WEBHOOK")
    assert not is_private_operator_identity("SUBSCRIBER_WEBHOOK")
    assert not is_private_operator_identity("")


# ---------------------------------------------------------------------------
# 5. Transport target validation
# ---------------------------------------------------------------------------


def test_valid_transport_target() -> None:
    target = Stage30_11_16TransportTarget(
        webhook_identity=STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
        visibility=STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    )
    assert is_valid_transport_target(target)


def test_invalid_transport_target_identity_or_visibility() -> None:
    assert not is_valid_transport_target(
        Stage30_11_16TransportTarget(
            webhook_identity="WRONG_IDENTITY",
            visibility=STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
        )
    )
    assert not is_valid_transport_target(
        Stage30_11_16TransportTarget(
            webhook_identity=STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
            visibility="PUBLIC",
        )
    )
    assert not is_valid_transport_target(None)
    assert not is_valid_transport_target("not-a-target")
    # No url / env field on the target (it carries exactly two fields).
    assert transport_target_field_names() == ("webhook_identity", "visibility")


# ---------------------------------------------------------------------------
# 6. Minimal {"content": body} payload allowlist
# ---------------------------------------------------------------------------


def test_minimal_content_payload_allowlist() -> None:
    assert is_minimal_content_payload({"content": "hello"})
    # Any extra key (a routing / subscriber / audience field) fails closed.
    assert not is_minimal_content_payload(
        {"content": "hello", "channel_id": "123"}
    )
    assert not is_minimal_content_payload(
        {"content": "hello", "subscriber_id": "x"}
    )
    assert not is_minimal_content_payload({"audience": "all", "content": "x"})
    # Wrong / missing / non-string content fails closed.
    assert not is_minimal_content_payload({"content": ""})
    assert not is_minimal_content_payload({"content": "   "})
    assert not is_minimal_content_payload({"content": 7})
    assert not is_minimal_content_payload({"text": "hello"})
    assert not is_minimal_content_payload({})
    assert not is_minimal_content_payload("not-a-dict")


# ---------------------------------------------------------------------------
# 7. Result record is constructible + carries only safe scalars
# ---------------------------------------------------------------------------


def test_result_record_is_frozen_and_safe() -> None:
    result = Stage30_11_16RealSendResult(
        decision=REAL_SEND_DECISION_REFUSED,
        reason=REAL_SEND_REASON_CAP_EXHAUSTED,
        token_mint="mint",
        candidate_id="cand",
        dispatch_forwarded=False,
        transport_attempted=False,
        transport_status=None,
        transport_ok=None,
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        cap_consumed=True,
        redaction_status="REDACTED",
        created_at_utc="2026-06-07T07:06:40Z",
    )
    assert is_real_send_decision(result.decision)
    assert is_real_send_reason(result.reason)
    # The decision / reason values used above are members of the closed sets.
    assert REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT in (
        STAGE30_11_16_REAL_SEND_DECISIONS
    )
    assert REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT in (
        STAGE30_11_16_REAL_SEND_DECISIONS
    )
    assert REAL_SEND_REASON_TRANSPORT_EXCEPTION in STAGE30_11_16_REAL_SEND_REASONS
