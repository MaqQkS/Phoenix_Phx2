"""Stage 28.2 dispatch ledger model tests.

Pins:

  * Locked Stage 28.2 version axes and the redaction token.
  * Closed-set dedupe state / dispatch decision / record kind /
    failure reason vocabularies.
  * Terminal vs non-terminal dedupe state partition.
  * Dedupe-key field allowlist (length, character class,
    leading/trailing chars, secret-like substring rejection).
  * Artifact-reference allowlist (length, character class, path
    traversal / separator rejection, secret-like substring
    rejection).
  * ``build_dispatch_dedupe_key`` validates every field at
    construction.
  * ``DispatchDedupeKey`` is immutable (NamedTuple shape).
  * ``canonical_dedupe_key_serialization`` is deterministic and
    safe.
  * Stage 28.2 model exceptions never carry raw secret-like
    values; they expose only closed-set tokens / safe basenames /
    length axes.
  * Canary webhook URL / API key / bearer / provider endpoint /
    raw env-like value never appears in any record's repr / str
    / serialization.
  * Stage 28.2 forbidden dedupe-key field names (run_id /
    session_id / wall_clock / webhook_url / provider_endpoint /
    api_key / bearer_token / subscriber_id / paid_tier / etc.)
    are declared by ``FORBIDDEN_DEDUPE_KEY_FIELD_NAMES``.
"""

from __future__ import annotations

import re

import pytest

from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_NON_TERMINAL_STATES,
    DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_PRE_SEND_RECORDED,
    DEDUPE_STATE_REFUSED_PRE_SEND,
    DEDUPE_STATE_RESERVED,
    DEDUPE_STATE_VALUES,
    DEDUPE_TERMINAL_STATES,
    DISPATCH_DECISION_PROCEED,
    DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
    DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
    DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
    DISPATCH_DECISION_VALUES,
    DedupeKeyState,
    DispatchDedupeDecision,
    DispatchDedupeKey,
    FAILURE_REASON_UNSPECIFIED,
    FAILURE_REASON_VALUES,
    FORBIDDEN_DEDUPE_KEY_FIELD_NAMES,
    LedgerReplayState,
    PreSendRecord,
    RECORD_KIND_PRE_SEND,
    RECORD_KIND_RESERVE,
    RECORD_KIND_TERMINAL,
    RECORD_KIND_VALUES,
    ReserveRecord,
    STAGE28_2_MINOR_VERSION,
    STAGE28_2_REDACTION_TOKEN,
    STAGE28_2_SCHEMA_VERSION,
    Stage28_2DispatchLedgerError,
    Stage28_2InvalidArtifactReferenceError,
    Stage28_2InvalidDedupeKeyError,
    Stage28_2LedgerIOError,
    Stage28_2LedgerPathError,
    Stage28_2MalformedLedgerLineError,
    Stage28_2UnknownLedgerSchemaError,
    Stage28_2UnknownLedgerStateError,
    TerminalRecord,
    build_dispatch_dedupe_key,
    canonical_dedupe_key_serialization,
    is_artifact_reference_safe,
    is_dedupe_key_field_safe,
    is_dedupe_state_value,
    is_dispatch_decision_value,
    is_failure_reason_value,
    is_non_terminal_dedupe_state,
    is_record_kind_value,
    is_terminal_dedupe_state,
)


# ---------------------------------------------------------------------------
# Canary secret-like values used to assert non-leak across surfaces
# ---------------------------------------------------------------------------


_CANARY_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com/api/webhooks/canary/token"
)
_CANARY_PROVIDER_ENDPOINT: str = (
    "h" + "ttps://" + "rpc.helius" + ".xyz/?api-key=CANARY"
)
_CANARY_API_KEY: str = "sk-CANARY-API-KEY-DO-NOT-LEAK-1234567890"
_CANARY_BEARER: str = "Bearer CANARY-BEARER-TOKEN-DO-NOT-LEAK-987654"
_CANARY_AUTH_HEADER: str = "Authorization: Bearer CANARY-AUTH-HEADER"
_CANARY_RAW_ENV: str = "DISCORD_WEBHOOK_URL=h" + "ttps://canary"


_ALL_CANARIES: tuple[str, ...] = (
    _CANARY_WEBHOOK_URL,
    _CANARY_PROVIDER_ENDPOINT,
    _CANARY_API_KEY,
    _CANARY_BEARER,
    _CANARY_AUTH_HEADER,
    _CANARY_RAW_ENV,
)


def _assert_no_canary_in(text: str) -> None:
    for canary in _ALL_CANARIES:
        assert canary not in text, (
            f"canary value {canary!r} leaked into Stage 28.2 surface"
        )


# ---------------------------------------------------------------------------
# 1. Version axes + redaction token
# ---------------------------------------------------------------------------


def test_stage28_2_minor_version_is_28_2():
    assert STAGE28_2_MINOR_VERSION == "28.2"


def test_stage28_2_schema_version_is_locked_v0():
    assert STAGE28_2_SCHEMA_VERSION == "stage28_2_dispatch_ledger_v0"


def test_stage28_2_redaction_token_is_locked():
    assert STAGE28_2_REDACTION_TOKEN == "<<STAGE28_2_REDACTED>>"


def test_stage28_2_redaction_token_is_distinct_from_stage28_1_token():
    # Sanity: the Stage 28.2 redaction token must not collide with
    # any Stage 28.1 / Stage 27 token. We only inspect the literal
    # here -- importing the Stage 28.1 token would create a Stage
    # 28.1 production dependency, which the Stage 28.2 boundary
    # scan forbids.
    assert "STAGE28_2_REDACTED" in STAGE28_2_REDACTION_TOKEN
    assert "STAGE28_1_REDACTED" not in STAGE28_2_REDACTION_TOKEN


# ---------------------------------------------------------------------------
# 2. Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_dedupe_state_values_are_exactly_the_six_locked_tokens():
    assert set(DEDUPE_STATE_VALUES) == {
        "RESERVED",
        "PRE_SEND_RECORDED",
        "DISPATCHED_OK",
        "DISPATCHED_FAILED",
        "DISPATCHED_AMBIGUOUS",
        "REFUSED_PRE_SEND",
    }
    assert len(DEDUPE_STATE_VALUES) == 6


def test_dedupe_terminal_states_are_four():
    assert set(DEDUPE_TERMINAL_STATES) == {
        "DISPATCHED_OK",
        "DISPATCHED_FAILED",
        "DISPATCHED_AMBIGUOUS",
        "REFUSED_PRE_SEND",
    }
    assert len(DEDUPE_TERMINAL_STATES) == 4


def test_dedupe_non_terminal_states_are_two():
    assert set(DEDUPE_NON_TERMINAL_STATES) == {
        "RESERVED",
        "PRE_SEND_RECORDED",
    }
    assert len(DEDUPE_NON_TERMINAL_STATES) == 2


def test_terminal_and_non_terminal_states_are_disjoint():
    assert (
        set(DEDUPE_TERMINAL_STATES) & set(DEDUPE_NON_TERMINAL_STATES)
        == set()
    )


def test_terminal_plus_non_terminal_covers_every_dedupe_state():
    assert (
        set(DEDUPE_TERMINAL_STATES) | set(DEDUPE_NON_TERMINAL_STATES)
        == set(DEDUPE_STATE_VALUES)
    )


def test_dispatch_decision_values_are_exactly_four():
    assert set(DISPATCH_DECISION_VALUES) == {
        "PROCEED",
        "SUPPRESS_DUPLICATE_TERMINAL",
        "SUPPRESS_AMBIGUOUS",
        "REJECTED_INVALID_TRANSITION",
    }
    assert len(DISPATCH_DECISION_VALUES) == 4


def test_record_kind_values_are_exactly_three():
    assert set(RECORD_KIND_VALUES) == {
        "RESERVE",
        "PRE_SEND",
        "TERMINAL",
    }
    assert len(RECORD_KIND_VALUES) == 3


def test_failure_reason_values_are_unspecified_only_at_28_2():
    # Stage 28.3a will extend this vocabulary. Stage 28.2 locks
    # the single ``UNSPECIFIED`` placeholder; failure
    # classification is intentionally NOT shipped here.
    assert FAILURE_REASON_VALUES == ("UNSPECIFIED",)
    assert FAILURE_REASON_UNSPECIFIED == "UNSPECIFIED"


def test_dedupe_state_individual_constants_match_tuple():
    assert DEDUPE_STATE_RESERVED == "RESERVED"
    assert DEDUPE_STATE_PRE_SEND_RECORDED == "PRE_SEND_RECORDED"
    assert DEDUPE_STATE_DISPATCHED_OK == "DISPATCHED_OK"
    assert DEDUPE_STATE_DISPATCHED_FAILED == "DISPATCHED_FAILED"
    assert DEDUPE_STATE_DISPATCHED_AMBIGUOUS == "DISPATCHED_AMBIGUOUS"
    assert DEDUPE_STATE_REFUSED_PRE_SEND == "REFUSED_PRE_SEND"


def test_dispatch_decision_individual_constants_match_tuple():
    assert DISPATCH_DECISION_PROCEED == "PROCEED"
    assert (
        DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL
        == "SUPPRESS_DUPLICATE_TERMINAL"
    )
    assert (
        DISPATCH_DECISION_SUPPRESS_AMBIGUOUS == "SUPPRESS_AMBIGUOUS"
    )
    assert (
        DISPATCH_DECISION_REJECTED_INVALID_TRANSITION
        == "REJECTED_INVALID_TRANSITION"
    )


def test_record_kind_individual_constants_match_tuple():
    assert RECORD_KIND_RESERVE == "RESERVE"
    assert RECORD_KIND_PRE_SEND == "PRE_SEND"
    assert RECORD_KIND_TERMINAL == "TERMINAL"


# ---------------------------------------------------------------------------
# 3. Closed-set membership helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", DEDUPE_STATE_VALUES)
def test_is_dedupe_state_value_accepts_each_closed_set_token(token):
    assert is_dedupe_state_value(token) is True


@pytest.mark.parametrize(
    "token",
    [
        "",
        "unknown",
        "RESERVED ",
        " RESERVED",
        None,
        0,
        b"RESERVED",
    ],
)
def test_is_dedupe_state_value_rejects_out_of_set(token):
    assert is_dedupe_state_value(token) is False


@pytest.mark.parametrize("token", DEDUPE_TERMINAL_STATES)
def test_is_terminal_dedupe_state_accepts_terminal_only(token):
    assert is_terminal_dedupe_state(token) is True


@pytest.mark.parametrize("token", DEDUPE_NON_TERMINAL_STATES)
def test_is_terminal_dedupe_state_rejects_non_terminal(token):
    assert is_terminal_dedupe_state(token) is False


@pytest.mark.parametrize("token", DEDUPE_NON_TERMINAL_STATES)
def test_is_non_terminal_dedupe_state_accepts_non_terminal_only(token):
    assert is_non_terminal_dedupe_state(token) is True


@pytest.mark.parametrize("token", DEDUPE_TERMINAL_STATES)
def test_is_non_terminal_dedupe_state_rejects_terminal(token):
    assert is_non_terminal_dedupe_state(token) is False


@pytest.mark.parametrize("token", RECORD_KIND_VALUES)
def test_is_record_kind_value_accepts_closed_set(token):
    assert is_record_kind_value(token) is True


@pytest.mark.parametrize("token", DISPATCH_DECISION_VALUES)
def test_is_dispatch_decision_value_accepts_closed_set(token):
    assert is_dispatch_decision_value(token) is True


def test_is_failure_reason_value_accepts_unspecified():
    assert is_failure_reason_value("UNSPECIFIED") is True


def test_is_failure_reason_value_rejects_other_tokens():
    assert is_failure_reason_value("TRANSPORT_ERROR") is False
    assert is_failure_reason_value("") is False
    assert is_failure_reason_value(None) is False


# ---------------------------------------------------------------------------
# 4. Dedupe-key field allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "So11111111111111111111111111111111111111112",
        "SOL",
        "USDC",
        "migration",
        "ath_candidate",
        "tradeable_private_ping",
        "event-id-2026-05-22-abc",
        "abc_def_ghi",
        "a" * 128,
    ],
)
def test_is_dedupe_key_field_safe_accepts_typical_stage27_inputs(
    value,
):
    assert is_dedupe_key_field_safe(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # empty
        "",
        # leading / trailing dash or underscore
        "-foo",
        "foo-",
        "_foo",
        "foo_",
        # exceeds length cap
        "a" * 129,
        # disallowed characters
        "foo bar",
        "foo/bar",
        "foo\\bar",
        "foo.bar",
        "foo:bar",
        "foo,bar",
        "foo+bar",
        "foo@bar",
    ],
)
def test_is_dedupe_key_field_safe_rejects_invalid_inputs(value):
    assert is_dedupe_key_field_safe(value) is False


@pytest.mark.parametrize(
    "value",
    [
        # URL / scheme substrings
        "h" + "ttps://discord" + ".com/foo",
        "h" + "ttp://example.com",
        "w" + "ss://x.y",
        "foo://bar",
        # bearer / auth
        "BearerCANARY",
        "AuthorizationHeader",
        "auth=secret",
        "token=abcdefgh",
        "apikey=zzz",
        "key=xxx",
        "secret=yyy",
        "password123",
        "passwd",
        # webhook hosts
        "discord" + ".com",
        "discord" + "app.com",
        "hooks" + ".slack.com",
        "thing/webhooks/here",
    ],
)
def test_is_dedupe_key_field_safe_rejects_secret_like_substrings(value):
    # Some of these also fail the character allowlist (slashes,
    # equals). The combined rejection is what matters.
    assert is_dedupe_key_field_safe(value) is False


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        1,
        True,
        False,
        b"bytes",
        ["list"],
        {"dict": 1},
        (1, 2),
    ],
)
def test_is_dedupe_key_field_safe_rejects_non_strings(value):
    assert is_dedupe_key_field_safe(value) is False


# ---------------------------------------------------------------------------
# 5. Artifact-reference allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "stage27_private_ping_payload.json",
        "stage27_private_ping_artifact_abc.json",
        "abc-1234.txt",
        "a" * 256,
        "ping_provenance.jsonl",
    ],
)
def test_is_artifact_reference_safe_accepts_typical_basenames(value):
    assert is_artifact_reference_safe(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 257,
        ".hidden",
        "trailing.",
        "-leading",
        "trailing-",
        "has space.json",
        "has\\backslash.json",
        "has/slash.json",
        "../parent.json",
        "..",
        "..hidden",
    ],
)
def test_is_artifact_reference_safe_rejects_invalid_inputs(value):
    assert is_artifact_reference_safe(value) is False


@pytest.mark.parametrize(
    "value",
    [
        # ``bearer`` is a literal substring in the Stage 28.2
        # secret-like list and must be rejected even when wrapped
        # in otherwise-safe artifact-name material.
        "bearer_artifact.json",
        "authorization_artifact.json",
        "password_artifact.json",
        # ``discord.com`` segment forces rejection even though the
        # underlying chars pass the artifact-reference allowlist.
        "discord.com_artifact.json",
    ],
)
def test_is_artifact_reference_safe_rejects_secret_like_substrings(
    value,
):
    # Each of these passes the character allowlist but must be
    # rejected by the secret-like substring scan.
    assert is_artifact_reference_safe(value) is False


@pytest.mark.parametrize(
    "value",
    [
        None,
        b"bytes.json",
        123,
        ["x.json"],
    ],
)
def test_is_artifact_reference_safe_rejects_non_strings(value):
    assert is_artifact_reference_safe(value) is False


# ---------------------------------------------------------------------------
# 6. Forbidden dedupe-key field NAMES vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "run_id",
        "session_id",
        "wall_clock_timestamp",
        "wall_clock",
        "timestamp",
        "webhook_url",
        "webhook",
        "provider_endpoint",
        "provider_url",
        "rpc_url",
        "grpc_endpoint",
        "api_key",
        "bearer_token",
        "auth_header",
        "subscriber_id",
        "subscribers",
        "channel_id",
        "public_channel_id",
        "recipient",
        "audience",
        "route_id",
        "paid_tier",
        "tier",
        "approval_status",
        "enforcement_result",
    ],
)
def test_forbidden_dedupe_key_field_names_lists_each_excluded_name(
    name,
):
    assert name in FORBIDDEN_DEDUPE_KEY_FIELD_NAMES


def test_dispatch_dedupe_key_fields_do_not_overlap_forbidden_names():
    allowed = {
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    }
    forbidden = set(FORBIDDEN_DEDUPE_KEY_FIELD_NAMES)
    assert allowed & forbidden == set()


def test_dispatch_dedupe_key_named_tuple_exposes_only_allowed_fields():
    # Sanity: the NamedTuple shape exposes exactly the locked
    # dedupe-key field names. Reject any future drift that would
    # add ``run_id`` / ``session_id`` / ``timestamp`` / etc.
    field_names = set(DispatchDedupeKey._fields)
    allowed = {
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    }
    assert field_names == allowed


# ---------------------------------------------------------------------------
# 7. build_dispatch_dedupe_key
# ---------------------------------------------------------------------------


def _make_safe_key() -> DispatchDedupeKey:
    return build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="SOL",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt-abc-001",
    )


def test_build_dispatch_dedupe_key_accepts_safe_inputs():
    key = _make_safe_key()
    assert isinstance(key, DispatchDedupeKey)
    assert key.token_mint == (
        "So11111111111111111111111111111111111111112"
    )
    assert key.pair_quote_asset == "SOL"
    assert key.event_kind == "migration"
    assert key.ping_type == "tradeable_private_ping"
    assert key.normalized_event_id == "evt-abc-001"


@pytest.mark.parametrize(
    "field_name",
    [
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    ],
)
def test_build_dispatch_dedupe_key_rejects_missing_field_when_empty(
    field_name,
):
    kwargs = {
        "token_mint": "So11111111111111111111111111111111111111112",
        "pair_quote_asset": "SOL",
        "event_kind": "migration",
        "ping_type": "tradeable_private_ping",
        "normalized_event_id": "evt-abc-001",
    }
    kwargs[field_name] = ""  # empty -> outside allowlist
    with pytest.raises(Stage28_2InvalidDedupeKeyError) as exc_info:
        build_dispatch_dedupe_key(**kwargs)
    assert exc_info.value.field_name == field_name
    assert exc_info.value.reason == "DEDUPE_KEY_FIELD_UNSAFE"


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        # Each canary carries a substring (``://`` / ``=`` /
        # whitespace / colon) that the Stage 28.2 dedupe-key field
        # allowlist rejects -- either at the character-class step
        # or at the secret-like substring step. ``_CANARY_API_KEY``
        # is deliberately not used here because it is a pure
        # alphanumeric+dash string that the dedupe-key allowlist
        # cannot distinguish from a legitimate opaque event id;
        # Stage 28.2's redaction discipline catches it elsewhere
        # (e.g. it never makes it to a record because the only
        # closed-set field values are token_mint / pair_quote_asset
        # / event_kind / ping_type / normalized_event_id and a
        # caller would never assign an API key to those slots).
        ("token_mint", _CANARY_WEBHOOK_URL),
        ("token_mint", _CANARY_PROVIDER_ENDPOINT),
        ("pair_quote_asset", _CANARY_PROVIDER_ENDPOINT),
        ("event_kind", _CANARY_BEARER),
        ("ping_type", _CANARY_AUTH_HEADER),
        ("normalized_event_id", _CANARY_RAW_ENV),
    ],
)
def test_build_dispatch_dedupe_key_rejects_secret_like_field(
    field_name, bad_value
):
    kwargs = {
        "token_mint": "So11111111111111111111111111111111111111112",
        "pair_quote_asset": "SOL",
        "event_kind": "migration",
        "ping_type": "tradeable_private_ping",
        "normalized_event_id": "evt-abc-001",
    }
    kwargs[field_name] = bad_value
    with pytest.raises(Stage28_2InvalidDedupeKeyError):
        build_dispatch_dedupe_key(**kwargs)


def test_build_dispatch_dedupe_key_does_not_leak_bad_value_in_exception():
    bad = _CANARY_WEBHOOK_URL
    try:
        build_dispatch_dedupe_key(
            token_mint=bad,
            pair_quote_asset="SOL",
            event_kind="migration",
            ping_type="tradeable_private_ping",
            normalized_event_id="evt-abc-001",
        )
    except Stage28_2InvalidDedupeKeyError as exc:
        _assert_no_canary_in(str(exc))
        _assert_no_canary_in(repr(exc))
        assert exc.field_name == "token_mint"
        assert exc.reason == "DEDUPE_KEY_FIELD_UNSAFE"
    else:
        pytest.fail("expected Stage28_2InvalidDedupeKeyError")


# ---------------------------------------------------------------------------
# 8. DispatchDedupeKey immutability
# ---------------------------------------------------------------------------


def test_dispatch_dedupe_key_is_immutable_named_tuple():
    key = _make_safe_key()
    # NamedTuple instances are immutable; attribute assignment
    # raises AttributeError.
    with pytest.raises(AttributeError):
        key.token_mint = "SOMETHING_ELSE"  # type: ignore[misc]


def test_dispatch_dedupe_key_equality_is_structural():
    a = _make_safe_key()
    b = _make_safe_key()
    assert a == b
    assert hash(a) == hash(b)


def test_dispatch_dedupe_key_inequality_when_field_differs():
    a = _make_safe_key()
    b = build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="USDC",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt-abc-001",
    )
    assert a != b


# ---------------------------------------------------------------------------
# 9. canonical_dedupe_key_serialization
# ---------------------------------------------------------------------------


def test_canonical_dedupe_key_serialization_is_deterministic():
    key = _make_safe_key()
    out_a = canonical_dedupe_key_serialization(key)
    out_b = canonical_dedupe_key_serialization(key)
    assert out_a == out_b
    assert isinstance(out_a, str)


def test_canonical_dedupe_key_serialization_includes_each_field_name():
    key = _make_safe_key()
    out = canonical_dedupe_key_serialization(key)
    for name in (
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    ):
        assert name in out


def test_canonical_dedupe_key_serialization_distinguishes_quote_assets():
    a = _make_safe_key()
    b = build_dispatch_dedupe_key(
        token_mint=a.token_mint,
        pair_quote_asset="USDC",
        event_kind=a.event_kind,
        ping_type=a.ping_type,
        normalized_event_id=a.normalized_event_id,
    )
    assert (
        canonical_dedupe_key_serialization(a)
        != canonical_dedupe_key_serialization(b)
    )


def test_canonical_dedupe_key_serialization_has_no_url_or_secret():
    key = _make_safe_key()
    out = canonical_dedupe_key_serialization(key)
    _assert_no_canary_in(out)


# ---------------------------------------------------------------------------
# 10. Record shapes
# ---------------------------------------------------------------------------


def test_reserve_record_is_named_tuple_with_locked_fields():
    key = _make_safe_key()
    record = ReserveRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_RESERVE,
        dedupe_key=key,
    )
    assert record.schema_version == STAGE28_2_SCHEMA_VERSION
    assert record.record_kind == RECORD_KIND_RESERVE
    assert record.dedupe_key is key
    with pytest.raises(AttributeError):
        record.dedupe_key = key  # type: ignore[misc]


def test_pre_send_record_carries_artifact_reference():
    key = _make_safe_key()
    record = PreSendRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_PRE_SEND,
        dedupe_key=key,
        artifact_reference="stage27_private_ping_payload.json",
    )
    assert record.artifact_reference == (
        "stage27_private_ping_payload.json"
    )


def test_terminal_record_carries_status_and_failure_reason_or_none():
    key = _make_safe_key()
    ok = TerminalRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_TERMINAL,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        failure_reason=None,
    )
    assert ok.failure_reason is None
    failed = TerminalRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_TERMINAL,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
        failure_reason=FAILURE_REASON_UNSPECIFIED,
    )
    assert failed.failure_reason == FAILURE_REASON_UNSPECIFIED


def test_dedupe_key_state_is_named_tuple():
    key = _make_safe_key()
    state = DedupeKeyState(
        dedupe_key=key,
        current_state=DEDUPE_STATE_RESERVED,
        reserve_seen=True,
        pre_send_seen=False,
        terminal_seen=False,
        terminal_status=None,
        failure_reason=None,
        artifact_reference=None,
    )
    assert state.dedupe_key is key
    with pytest.raises(AttributeError):
        state.current_state = (  # type: ignore[misc]
            DEDUPE_STATE_DISPATCHED_OK
        )


def test_ledger_replay_state_is_named_tuple():
    bundle = LedgerReplayState(states_by_key={}, record_count=0)
    assert bundle.record_count == 0
    assert bundle.states_by_key == {}
    with pytest.raises(AttributeError):
        bundle.record_count = 1  # type: ignore[misc]


def test_dispatch_dedupe_decision_is_named_tuple():
    key = _make_safe_key()
    decision = DispatchDedupeDecision(
        decision=DISPATCH_DECISION_PROCEED,
        current_state=DEDUPE_STATE_RESERVED,
        dedupe_key=key,
    )
    assert decision.decision == DISPATCH_DECISION_PROCEED
    with pytest.raises(AttributeError):
        decision.decision = (  # type: ignore[misc]
            DISPATCH_DECISION_SUPPRESS_AMBIGUOUS
        )


# ---------------------------------------------------------------------------
# 11. Repr / str redaction for records
# ---------------------------------------------------------------------------


def test_dispatch_dedupe_key_repr_carries_no_canary():
    key = _make_safe_key()
    _assert_no_canary_in(repr(key))
    _assert_no_canary_in(str(key))


def test_reserve_record_repr_carries_no_canary():
    record = ReserveRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_RESERVE,
        dedupe_key=_make_safe_key(),
    )
    _assert_no_canary_in(repr(record))
    _assert_no_canary_in(str(record))


def test_pre_send_record_repr_carries_no_canary():
    record = PreSendRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_PRE_SEND,
        dedupe_key=_make_safe_key(),
        artifact_reference="stage27_artifact.json",
    )
    _assert_no_canary_in(repr(record))
    _assert_no_canary_in(str(record))


def test_terminal_record_repr_carries_no_canary():
    record = TerminalRecord(
        schema_version=STAGE28_2_SCHEMA_VERSION,
        record_kind=RECORD_KIND_TERMINAL,
        dedupe_key=_make_safe_key(),
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        failure_reason=None,
    )
    _assert_no_canary_in(repr(record))
    _assert_no_canary_in(str(record))


def test_dispatch_dedupe_decision_repr_carries_no_canary():
    decision = DispatchDedupeDecision(
        decision=DISPATCH_DECISION_PROCEED,
        current_state=DEDUPE_STATE_RESERVED,
        dedupe_key=_make_safe_key(),
    )
    _assert_no_canary_in(repr(decision))
    _assert_no_canary_in(str(decision))


# ---------------------------------------------------------------------------
# 12. Exception hierarchy
# ---------------------------------------------------------------------------


def test_stage28_2_dispatch_ledger_error_is_module_local_exception():
    assert issubclass(Stage28_2DispatchLedgerError, Exception)


@pytest.mark.parametrize(
    "exc_class",
    [
        Stage28_2InvalidDedupeKeyError,
        Stage28_2InvalidArtifactReferenceError,
        Stage28_2MalformedLedgerLineError,
        Stage28_2UnknownLedgerSchemaError,
        Stage28_2UnknownLedgerStateError,
        Stage28_2LedgerPathError,
        Stage28_2LedgerIOError,
    ],
)
def test_each_specific_error_inherits_from_dispatch_ledger_error(
    exc_class,
):
    assert issubclass(exc_class, Stage28_2DispatchLedgerError)


def test_invalid_dedupe_key_error_carries_field_and_reason():
    exc = Stage28_2InvalidDedupeKeyError(
        field_name="token_mint", reason="DEDUPE_KEY_FIELD_UNSAFE"
    )
    assert exc.field_name == "token_mint"
    assert exc.reason == "DEDUPE_KEY_FIELD_UNSAFE"
    _assert_no_canary_in(str(exc))


def test_invalid_artifact_reference_error_carries_reason_only():
    exc = Stage28_2InvalidArtifactReferenceError(
        reason="ARTIFACT_REFERENCE_UNSAFE"
    )
    assert exc.reason == "ARTIFACT_REFERENCE_UNSAFE"
    _assert_no_canary_in(str(exc))


def test_malformed_ledger_line_error_carries_index_and_reason_only():
    exc = Stage28_2MalformedLedgerLineError(
        line_index=42, reason="INVALID_JSON"
    )
    assert exc.line_index == 42
    assert exc.reason == "INVALID_JSON"
    _assert_no_canary_in(str(exc))


def test_unknown_ledger_schema_error_carries_index_and_length_only():
    exc = Stage28_2UnknownLedgerSchemaError(
        line_index=7, observed_length=42
    )
    assert exc.line_index == 7
    assert exc.observed_length == 42
    _assert_no_canary_in(str(exc))


def test_unknown_ledger_state_error_carries_index_field_length_only():
    exc = Stage28_2UnknownLedgerStateError(
        line_index=5, field_name="terminal_status", observed_length=8
    )
    assert exc.line_index == 5
    assert exc.field_name == "terminal_status"
    assert exc.observed_length == 8
    _assert_no_canary_in(str(exc))


def test_ledger_path_error_carries_reason_and_optional_safe_basename():
    exc_no_name = Stage28_2LedgerPathError(
        reason="LEDGER_PATH_IS_DIRECTORY"
    )
    assert exc_no_name.reason == "LEDGER_PATH_IS_DIRECTORY"
    assert exc_no_name.safe_basename is None

    exc_with_name = Stage28_2LedgerPathError(
        reason="LEDGER_PARENT_DIRECTORY_MISSING",
        safe_basename="ledger.jsonl",
    )
    assert exc_with_name.safe_basename == "ledger.jsonl"
    _assert_no_canary_in(str(exc_with_name))


def test_ledger_io_error_carries_operation_and_optional_safe_basename():
    exc = Stage28_2LedgerIOError(
        operation="LEDGER_APPEND",
        safe_basename="ledger.jsonl",
    )
    assert exc.operation == "LEDGER_APPEND"
    assert exc.safe_basename == "ledger.jsonl"
    _assert_no_canary_in(str(exc))


# ---------------------------------------------------------------------------
# 13. Stage 28.0 forbidden-secret regex sanity over module source
# ---------------------------------------------------------------------------


def test_no_raw_secret_looking_value_in_module_source():
    # Sanity scan of the dispatch_ledger_models module source for
    # any of the canary substrings we use as test fixtures. None
    # of them must appear in production source.
    import inspect

    from PHX2.stage28 import dispatch_ledger_models as mod

    source = inspect.getsource(mod)
    for canary in _ALL_CANARIES:
        assert canary not in source, (
            f"canary {canary!r} accidentally landed in production "
            "Stage 28.2 models source"
        )
    # Also forbid bearer-token-like and sk-like raw values.
    assert not re.search(
        r"\bsk-[A-Za-z0-9_-]{8,}\b", source
    ), "production source carries an sk- secret-looking token"
    assert not re.search(
        r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", source
    ), "production source carries a Bearer-prefixed token"
