"""Stage 28.2 dispatch ledger operation tests.

Pins:

  * Replay of a non-existent ledger returns an empty replay state.
  * Replay of an empty file returns an empty replay state.
  * ``reserve_dispatch_intent`` writes exactly one JSONL line.
  * Reserve -> replay reconstructs RESERVED.
  * Reserve -> pre-send -> replay reconstructs PRE_SEND_RECORDED.
  * Reserve -> pre-send -> terminal-OK -> replay reconstructs
    DISPATCHED_OK.
  * Reserve -> pre-send -> terminal-FAILED reconstructs
    DISPATCHED_FAILED.
  * Reserve -> REFUSED_PRE_SEND terminal is allowed (refused pre-
    send is itself a terminal outcome).
  * Duplicate terminal reserve attempt -> SUPPRESS_DUPLICATE_TERMINAL,
    no second line written.
  * Duplicate non-terminal reserve attempt -> SUPPRESS_AMBIGUOUS,
    no second line written.
  * Pre-send before reserve -> REJECTED_INVALID_TRANSITION, no
    line written.
  * Malformed JSONL line -> Stage28_2MalformedLedgerLineError.
  * Unknown schema_version -> Stage28_2UnknownLedgerSchemaError.
  * Unknown record_kind / terminal_status / failure_reason ->
    Stage28_2UnknownLedgerStateError.
  * Missing dedupe_key field set -> Stage28_2MalformedLedgerLineError.
  * Unsafe dedupe-key field (URL / bearer / token=) is rejected
    by replay validation.
  * Unsafe artifact reference is rejected by replay validation +
    by ``record_pre_send``.
  * OSError on write/read is wrapped as Stage28_2LedgerIOError.
  * Ledger path is a directory -> Stage28_2LedgerPathError.
  * Ledger path with secret-like substring -> Stage28_2LedgerPathError.
  * Ledger path with missing parent directory ->
    Stage28_2LedgerPathError (no autocreation).
  * Append-only: writes don't truncate; reserve never rewrites an
    existing reserve.
  * Deterministic JSON: ``sort_keys=True`` keeps record bytes
    identical across runs.
  * No canary webhook / API key / bearer / provider endpoint /
    auth header leaks into the ledger file, public decision,
    repr/str, or exceptions.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from PHX2.stage28.dispatch_ledger import (
    classify_replay_state,
    lookup_state,
    record_pre_send,
    record_terminal,
    replay_ledger,
    reserve_dispatch_intent,
)
from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_PRE_SEND_RECORDED,
    DEDUPE_STATE_REFUSED_PRE_SEND,
    DEDUPE_STATE_RESERVED,
    DISPATCH_DECISION_PROCEED,
    DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
    DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
    DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
    DispatchDedupeKey,
    FAILURE_REASON_UNSPECIFIED,
    LedgerReplayState,
    STAGE28_2_SCHEMA_VERSION,
    Stage28_2InvalidArtifactReferenceError,
    Stage28_2InvalidDedupeKeyError,
    Stage28_2LedgerIOError,
    Stage28_2LedgerPathError,
    Stage28_2MalformedLedgerLineError,
    Stage28_2UnknownLedgerSchemaError,
    Stage28_2UnknownLedgerStateError,
    build_dispatch_dedupe_key,
    canonical_dedupe_key_serialization,
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
# Test fixtures
# ---------------------------------------------------------------------------


def _make_safe_key(
    *,
    pair_quote_asset: str = "SOL",
    normalized_event_id: str = "evt-abc-001",
    event_kind: str = "migration",
) -> DispatchDedupeKey:
    return build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset=pair_quote_asset,
        event_kind=event_kind,
        ping_type="tradeable_private_ping",
        normalized_event_id=normalized_event_id,
    )


# Stage 28.2 ledger tests need a writable temp directory.
# pytest's built-in ``tmp_path`` would normally fit, but on this
# host the sandboxed pytest cache lacks list-access to the global
# ``pytest-of-*`` root. A project-local self-managed temp directory
# sidesteps that and keeps the test deterministic (matching the
# Stage 27.5 ``stage27_5_tmp_path`` convention).
@pytest.fixture
def stage28_2_tmp_path():
    base = Path(__file__).resolve().parent / "_stage_28_2_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="stage28_2_", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        # Best-effort cleanup of the parent if it became empty.
        try:
            base.rmdir()
        except OSError:
            pass


@pytest.fixture
def ledger_path(stage28_2_tmp_path: Path) -> Path:
    return stage28_2_tmp_path / "stage28_dispatch_ledger.jsonl"


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if raw == "":
        return []
    out: list[str] = []
    for line in raw.split("\n"):
        out.append(line)
    if out and out[-1] == "":
        out.pop()
    return out


# ---------------------------------------------------------------------------
# 1. Empty / missing ledger replay
# ---------------------------------------------------------------------------


def test_replay_of_missing_ledger_returns_empty(ledger_path: Path):
    assert not ledger_path.exists()
    state = replay_ledger(ledger_path)
    assert state.record_count == 0
    assert dict(state.states_by_key) == {}


def test_replay_of_empty_file_returns_empty(ledger_path: Path):
    ledger_path.write_bytes(b"")
    state = replay_ledger(ledger_path)
    assert state.record_count == 0
    assert dict(state.states_by_key) == {}


# ---------------------------------------------------------------------------
# 2. Reserve writes exactly one JSONL record
# ---------------------------------------------------------------------------


def test_reserve_writes_one_jsonl_record(ledger_path: Path):
    key = _make_safe_key()
    empty = replay_ledger(ledger_path)
    decision = reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=empty,
    )
    assert decision.decision == DISPATCH_DECISION_PROCEED
    assert decision.current_state == DEDUPE_STATE_RESERVED
    lines = _read_lines(ledger_path)
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["schema_version"] == STAGE28_2_SCHEMA_VERSION
    assert parsed["record_kind"] == "RESERVE"
    assert parsed["dedupe_key"]["token_mint"] == key.token_mint
    assert parsed["dedupe_key"]["pair_quote_asset"] == "SOL"


def test_reserve_then_replay_reconstructs_reserved(ledger_path: Path):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    state = replay_ledger(ledger_path)
    assert state.record_count == 1
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.current_state == DEDUPE_STATE_RESERVED
    assert reconstructed.reserve_seen is True
    assert reconstructed.pre_send_seen is False
    assert reconstructed.terminal_seen is False
    assert reconstructed.terminal_status is None
    assert reconstructed.artifact_reference is None


# ---------------------------------------------------------------------------
# 3. Pre-send and terminal lifecycle
# ---------------------------------------------------------------------------


def test_pre_send_after_reserve_reconstructs_pre_send_recorded(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    decision = record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_private_ping_payload.json",
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_PROCEED
    assert decision.current_state == DEDUPE_STATE_PRE_SEND_RECORDED

    state = replay_ledger(ledger_path)
    assert state.record_count == 2
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.current_state == DEDUPE_STATE_PRE_SEND_RECORDED
    assert reconstructed.reserve_seen is True
    assert reconstructed.pre_send_seen is True
    assert reconstructed.terminal_seen is False
    assert reconstructed.artifact_reference == (
        "stage27_private_ping_payload.json"
    )


def test_terminal_ok_after_pre_send_reconstructs_dispatched_ok(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_artifact.json",
        replay=replay_ledger(ledger_path),
    )
    decision = record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_PROCEED
    assert decision.current_state == DEDUPE_STATE_DISPATCHED_OK

    state = replay_ledger(ledger_path)
    assert state.record_count == 3
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.current_state == DEDUPE_STATE_DISPATCHED_OK
    assert reconstructed.terminal_seen is True
    assert reconstructed.terminal_status == DEDUPE_STATE_DISPATCHED_OK
    assert reconstructed.failure_reason is None
    assert reconstructed.artifact_reference == (
        "stage27_artifact.json"
    )


def test_terminal_failed_reconstructs_dispatched_failed(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_artifact.json",
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
        replay=replay_ledger(ledger_path),
        failure_reason=FAILURE_REASON_UNSPECIFIED,
    )
    state = replay_ledger(ledger_path)
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.current_state == DEDUPE_STATE_DISPATCHED_FAILED
    assert reconstructed.terminal_status == DEDUPE_STATE_DISPATCHED_FAILED
    assert reconstructed.failure_reason == FAILURE_REASON_UNSPECIFIED


def test_terminal_refused_pre_send_after_reserve_only_is_allowed(
    ledger_path: Path,
):
    # REFUSED_PRE_SEND is itself a terminal outcome: the runner
    # refused to attempt the send because pre-send artifact write
    # failed. Stage 28.2 does not enforce a pre-send-before-
    # terminal transition.
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    decision = record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_REFUSED_PRE_SEND,
        replay=replay_ledger(ledger_path),
        failure_reason=FAILURE_REASON_UNSPECIFIED,
    )
    assert decision.decision == DISPATCH_DECISION_PROCEED
    assert decision.current_state == DEDUPE_STATE_REFUSED_PRE_SEND
    state = replay_ledger(ledger_path)
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.terminal_seen is True
    assert reconstructed.pre_send_seen is False
    assert reconstructed.current_state == DEDUPE_STATE_REFUSED_PRE_SEND


def test_terminal_dispatched_ambiguous_reconstructs(ledger_path: Path):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_artifact.json",
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
        replay=replay_ledger(ledger_path),
        failure_reason=FAILURE_REASON_UNSPECIFIED,
    )
    state = replay_ledger(ledger_path)
    reconstructed = lookup_state(state, key)
    assert reconstructed is not None
    assert reconstructed.current_state == DEDUPE_STATE_DISPATCHED_AMBIGUOUS


# ---------------------------------------------------------------------------
# 4. Duplicate suppression: terminal + ambiguous
# ---------------------------------------------------------------------------


def test_duplicate_terminal_reserve_suppresses(ledger_path: Path):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_artifact.json",
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    lines_before = _read_lines(ledger_path)
    assert len(lines_before) == 3

    # A second reserve against the same key must suppress and NOT
    # write a new record.
    decision = reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL
    assert decision.current_state == DEDUPE_STATE_DISPATCHED_OK

    lines_after = _read_lines(ledger_path)
    assert lines_after == lines_before


def test_duplicate_non_terminal_reserve_suppresses_ambiguously(
    ledger_path: Path,
):
    key = _make_safe_key()
    # First reserve writes RESERVED. Then simulate a crash before
    # any pre-send / terminal record was written by reading the
    # current replay state and trying a second reserve.
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    lines_before = _read_lines(ledger_path)
    assert len(lines_before) == 1

    decision = reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_AMBIGUOUS
    assert decision.current_state == DEDUPE_STATE_RESERVED

    lines_after = _read_lines(ledger_path)
    assert lines_after == lines_before


def test_duplicate_pre_send_after_pre_send_recorded_suppresses_ambiguously(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="artifact_a.json",
        replay=replay_ledger(ledger_path),
    )
    lines_before = _read_lines(ledger_path)

    decision = record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="artifact_b.json",
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_AMBIGUOUS
    assert decision.current_state == DEDUPE_STATE_PRE_SEND_RECORDED
    lines_after = _read_lines(ledger_path)
    assert lines_after == lines_before


def test_pre_send_before_reserve_rejects_invalid_transition(
    ledger_path: Path,
):
    key = _make_safe_key()
    decision = record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_artifact.json",
        replay=replay_ledger(ledger_path),
    )
    assert (
        decision.decision == DISPATCH_DECISION_REJECTED_INVALID_TRANSITION
    )
    assert decision.current_state is None
    assert not ledger_path.exists() or _read_lines(ledger_path) == []


def test_terminal_after_terminal_suppresses_duplicate_terminal(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    lines_before = _read_lines(ledger_path)

    decision = record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
        replay=replay_ledger(ledger_path),
    )
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL
    assert decision.current_state == DEDUPE_STATE_DISPATCHED_OK
    assert _read_lines(ledger_path) == lines_before


# ---------------------------------------------------------------------------
# 5. classify_replay_state (pure helper)
# ---------------------------------------------------------------------------


def test_classify_replay_state_returns_proceed_for_unseen_key(
    ledger_path: Path,
):
    key = _make_safe_key()
    state = replay_ledger(ledger_path)
    decision = classify_replay_state(state, key)
    assert decision.decision == DISPATCH_DECISION_PROCEED
    assert decision.current_state is None


def test_classify_replay_state_returns_suppress_ambiguous_for_reserved_key(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    state = replay_ledger(ledger_path)
    decision = classify_replay_state(state, key)
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_AMBIGUOUS
    assert decision.current_state == DEDUPE_STATE_RESERVED


def test_classify_replay_state_returns_suppress_terminal_for_dispatched_key(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    state = replay_ledger(ledger_path)
    decision = classify_replay_state(state, key)
    assert decision.decision == DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL
    assert decision.current_state == DEDUPE_STATE_DISPATCHED_OK


# ---------------------------------------------------------------------------
# 6. Multiple keys + interleaving
# ---------------------------------------------------------------------------


def test_two_distinct_keys_get_independent_states(ledger_path: Path):
    key_a = _make_safe_key(normalized_event_id="evt-a")
    key_b = _make_safe_key(normalized_event_id="evt-b")

    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_a,
        replay=replay_ledger(ledger_path),
    )
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_b,
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key_a,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )

    state = replay_ledger(ledger_path)
    a_state = lookup_state(state, key_a)
    b_state = lookup_state(state, key_b)
    assert a_state is not None
    assert b_state is not None
    assert a_state.current_state == DEDUPE_STATE_DISPATCHED_OK
    assert b_state.current_state == DEDUPE_STATE_RESERVED


def test_different_quote_assets_produce_distinct_keys(
    ledger_path: Path,
):
    key_sol = _make_safe_key(pair_quote_asset="SOL")
    key_usdc = _make_safe_key(pair_quote_asset="USDC")
    assert (
        canonical_dedupe_key_serialization(key_sol)
        != canonical_dedupe_key_serialization(key_usdc)
    )
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_sol,
        replay=replay_ledger(ledger_path),
    )
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_usdc,
        replay=replay_ledger(ledger_path),
    )
    state = replay_ledger(ledger_path)
    assert len(state.states_by_key) == 2


# ---------------------------------------------------------------------------
# 7. Malformed JSONL handling
# ---------------------------------------------------------------------------


def test_replay_raises_on_invalid_json_line(ledger_path: Path):
    ledger_path.write_text(
        "this is not json\n", encoding="utf-8"
    )
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.line_index == 1
    assert exc_info.value.reason == "INVALID_JSON"


def test_replay_raises_on_empty_line(ledger_path: Path):
    ledger_path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "EMPTY_LINE"


def test_replay_raises_on_json_array_line(ledger_path: Path):
    ledger_path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "NOT_A_JSON_OBJECT"


def test_replay_raises_on_missing_schema_version(ledger_path: Path):
    ledger_path.write_text(
        json.dumps(
            {
                "record_kind": "RESERVE",
                "dedupe_key": {
                    "token_mint": "x" * 10,
                    "pair_quote_asset": "SOL",
                    "event_kind": "migration",
                    "ping_type": "tradeable_private_ping",
                    "normalized_event_id": "evt-a",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "MISSING_SCHEMA_VERSION"


def test_replay_raises_on_unknown_schema_version(ledger_path: Path):
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": "stage99_unknown_schema",
                "record_kind": "RESERVE",
                "dedupe_key": {
                    "token_mint": "x" * 10,
                    "pair_quote_asset": "SOL",
                    "event_kind": "migration",
                    "ping_type": "tradeable_private_ping",
                    "normalized_event_id": "evt-a",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage28_2UnknownLedgerSchemaError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.line_index == 1


def test_replay_raises_on_unknown_record_kind(ledger_path: Path):
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": STAGE28_2_SCHEMA_VERSION,
                "record_kind": "BOGUS",
                "dedupe_key": {
                    "token_mint": "x" * 10,
                    "pair_quote_asset": "SOL",
                    "event_kind": "migration",
                    "ping_type": "tradeable_private_ping",
                    "normalized_event_id": "evt-a",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage28_2UnknownLedgerStateError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.field_name == "record_kind"


def test_replay_raises_on_unknown_terminal_status(ledger_path: Path):
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": STAGE28_2_SCHEMA_VERSION,
                "record_kind": "TERMINAL",
                "dedupe_key": {
                    "token_mint": "x" * 10,
                    "pair_quote_asset": "SOL",
                    "event_kind": "migration",
                    "ping_type": "tradeable_private_ping",
                    "normalized_event_id": "evt-a",
                },
                "terminal_status": "BOGUS_TERMINAL",
                "failure_reason": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage28_2UnknownLedgerStateError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.field_name == "terminal_status"


def test_replay_raises_on_unknown_failure_reason(ledger_path: Path):
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": STAGE28_2_SCHEMA_VERSION,
                "record_kind": "TERMINAL",
                "dedupe_key": {
                    "token_mint": "x" * 10,
                    "pair_quote_asset": "SOL",
                    "event_kind": "migration",
                    "ping_type": "tradeable_private_ping",
                    "normalized_event_id": "evt-a",
                },
                "terminal_status": DEDUPE_STATE_DISPATCHED_FAILED,
                "failure_reason": "BOGUS_FAILURE",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage28_2UnknownLedgerStateError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.field_name == "failure_reason"


def test_replay_raises_on_dedupe_key_field_set_mismatch(
    ledger_path: Path,
):
    bad = {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": "RESERVE",
        "dedupe_key": {
            "token_mint": "x" * 10,
            "pair_quote_asset": "SOL",
            # missing event_kind, ping_type, normalized_event_id
        },
    }
    ledger_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "DEDUPE_KEY_FIELD_SET_MISMATCH"


def test_replay_raises_on_dedupe_key_field_carrying_url(ledger_path: Path):
    bad = {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": "RESERVE",
        "dedupe_key": {
            # token_mint carrying a ``bearer`` substring: the
            # Stage 28.2 dedupe-key allowlist rejects secret-like
            # substrings even when the character class passes.
            "token_mint": "bearer_token_value_unsafe",
            "pair_quote_asset": "SOL",
            "event_kind": "migration",
            "ping_type": "tradeable_private_ping",
            "normalized_event_id": "evt-a",
        },
    }
    ledger_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "DEDUPE_KEY_FIELD_UNSAFE"


def test_replay_raises_on_reserve_with_extra_field(ledger_path: Path):
    bad = {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": "RESERVE",
        "dedupe_key": {
            "token_mint": "x" * 10,
            "pair_quote_asset": "SOL",
            "event_kind": "migration",
            "ping_type": "tradeable_private_ping",
            "normalized_event_id": "evt-a",
        },
        "extra": "should-not-be-here",
    }
    ledger_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "RESERVE_RECORD_HAS_EXTRA_FIELDS"


def test_replay_raises_on_pre_send_with_unsafe_artifact_reference(
    ledger_path: Path,
):
    bad = {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": "PRE_SEND",
        "dedupe_key": {
            "token_mint": "x" * 10,
            "pair_quote_asset": "SOL",
            "event_kind": "migration",
            "ping_type": "tradeable_private_ping",
            "normalized_event_id": "evt-a",
        },
        "artifact_reference": "../parent.json",
    }
    ledger_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_2MalformedLedgerLineError) as exc_info:
        replay_ledger(ledger_path)
    assert exc_info.value.reason == "ARTIFACT_REFERENCE_UNSAFE"


# ---------------------------------------------------------------------------
# 8. record_pre_send validates artifact reference
# ---------------------------------------------------------------------------


def test_record_pre_send_rejects_unsafe_artifact_reference(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    with pytest.raises(Stage28_2InvalidArtifactReferenceError):
        record_pre_send(
            ledger_path=ledger_path,
            dedupe_key=key,
            artifact_reference=_CANARY_WEBHOOK_URL,
            replay=replay_ledger(ledger_path),
        )


def test_record_pre_send_rejects_path_traversal_artifact_reference(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    with pytest.raises(Stage28_2InvalidArtifactReferenceError):
        record_pre_send(
            ledger_path=ledger_path,
            dedupe_key=key,
            artifact_reference="../../etc/passwd",
            replay=replay_ledger(ledger_path),
        )


# ---------------------------------------------------------------------------
# 9. Terminal status / failure reason closed-set enforcement
# ---------------------------------------------------------------------------


def test_record_terminal_rejects_unknown_terminal_status(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    with pytest.raises(Stage28_2UnknownLedgerStateError) as exc_info:
        record_terminal(
            ledger_path=ledger_path,
            dedupe_key=key,
            terminal_status="BOGUS",
            replay=replay_ledger(ledger_path),
        )
    assert exc_info.value.field_name == "terminal_status"


def test_record_terminal_rejects_non_terminal_state_token(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    # ``RESERVED`` is a valid dedupe state but NOT a terminal one;
    # record_terminal must reject it.
    with pytest.raises(Stage28_2UnknownLedgerStateError):
        record_terminal(
            ledger_path=ledger_path,
            dedupe_key=key,
            terminal_status=DEDUPE_STATE_RESERVED,
            replay=replay_ledger(ledger_path),
        )


def test_record_terminal_rejects_unknown_failure_reason(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    with pytest.raises(Stage28_2UnknownLedgerStateError) as exc_info:
        record_terminal(
            ledger_path=ledger_path,
            dedupe_key=key,
            terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
            replay=replay_ledger(ledger_path),
            failure_reason="bogus_reason_token",
        )
    assert exc_info.value.field_name == "failure_reason"


# ---------------------------------------------------------------------------
# 10. Reserve validates dedupe key defensively
# ---------------------------------------------------------------------------


def test_reserve_dispatch_intent_rejects_unsafe_dedupe_key(
    ledger_path: Path,
):
    # Construct an unsafe DispatchDedupeKey directly via NamedTuple
    # ctor, bypassing build_dispatch_dedupe_key. The token_mint
    # value carries the literal ``bearer`` substring, which the
    # Stage 28.2 dedupe-key allowlist rejects even though the
    # underlying characters pass the [A-Za-z0-9_-] check.
    unsafe = DispatchDedupeKey(
        token_mint="bearer_token_value_unsafe",
        pair_quote_asset="SOL",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt-a",
    )
    with pytest.raises(Stage28_2InvalidDedupeKeyError):
        reserve_dispatch_intent(
            ledger_path=ledger_path,
            dedupe_key=unsafe,
            replay=replay_ledger(ledger_path),
        )
    assert not ledger_path.exists() or _read_lines(ledger_path) == []


# ---------------------------------------------------------------------------
# 11. Path safety
# ---------------------------------------------------------------------------


def test_replay_rejects_directory_as_ledger_path(
    stage28_2_tmp_path: Path,
):
    dir_path = stage28_2_tmp_path / "as_directory"
    dir_path.mkdir()
    with pytest.raises(Stage28_2LedgerPathError) as exc_info:
        replay_ledger(dir_path)
    assert exc_info.value.reason == "LEDGER_PATH_IS_DIRECTORY"


def test_reserve_rejects_directory_as_ledger_path(
    stage28_2_tmp_path: Path,
):
    dir_path = stage28_2_tmp_path / "as_directory"
    dir_path.mkdir()
    key = _make_safe_key()
    with pytest.raises(Stage28_2LedgerPathError):
        reserve_dispatch_intent(
            ledger_path=dir_path,
            dedupe_key=key,
            replay=LedgerReplayState(
                states_by_key={}, record_count=0
            ),
        )


def test_reserve_rejects_secret_like_path(stage28_2_tmp_path: Path):
    # The filename carries the literal ``bearer`` substring, which
    # the Stage 28.2 ledger-path validator must reject regardless
    # of which other path components are present.
    bad_path = stage28_2_tmp_path / "bearer_ledger.jsonl"
    key = _make_safe_key()
    with pytest.raises(Stage28_2LedgerPathError) as exc_info:
        reserve_dispatch_intent(
            ledger_path=bad_path,
            dedupe_key=key,
            replay=LedgerReplayState(
                states_by_key={}, record_count=0
            ),
        )
    assert exc_info.value.reason == "LEDGER_PATH_SECRET_LIKE"


def test_replay_rejects_path_with_missing_parent(
    stage28_2_tmp_path: Path,
):
    missing = stage28_2_tmp_path / "nope" / "sub" / "ledger.jsonl"
    with pytest.raises(Stage28_2LedgerPathError) as exc_info:
        replay_ledger(missing)
    assert exc_info.value.reason == "LEDGER_PARENT_DIRECTORY_MISSING"


def test_reserve_does_not_autocreate_parent_directories(
    stage28_2_tmp_path: Path,
):
    missing = (
        stage28_2_tmp_path / "deeply" / "nested" / "ledger.jsonl"
    )
    key = _make_safe_key()
    with pytest.raises(Stage28_2LedgerPathError):
        reserve_dispatch_intent(
            ledger_path=missing,
            dedupe_key=key,
            replay=LedgerReplayState(
                states_by_key={}, record_count=0
            ),
        )
    # The deeply / nested parents must not have been created.
    assert not (stage28_2_tmp_path / "deeply").exists()


def test_replay_rejects_non_pathlib_path():
    with pytest.raises(Stage28_2LedgerPathError) as exc_info:
        replay_ledger("/tmp/ledger.jsonl")  # type: ignore[arg-type]
    assert exc_info.value.reason == "LEDGER_PATH_NOT_A_PATHLIB_PATH"


# ---------------------------------------------------------------------------
# 12. OSError wrapping
# ---------------------------------------------------------------------------


def test_replay_wraps_oserror_on_read(ledger_path: Path):
    ledger_path.write_text("{}\n", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated read failure")

    with mock.patch.object(Path, "read_bytes", _boom):
        with pytest.raises(Stage28_2LedgerIOError) as exc_info:
            replay_ledger(ledger_path)
    assert exc_info.value.operation == "LEDGER_READ"


def test_reserve_wraps_oserror_on_append(ledger_path: Path):
    key = _make_safe_key()

    original_open = Path.open

    def _boom(self, mode="r", *args, **kwargs):  # noqa: ANN001
        if "a" in mode:
            raise OSError("simulated append failure")
        return original_open(self, mode, *args, **kwargs)

    with mock.patch.object(Path, "open", _boom):
        with pytest.raises(Stage28_2LedgerIOError) as exc_info:
            reserve_dispatch_intent(
                ledger_path=ledger_path,
                dedupe_key=key,
                replay=replay_ledger(ledger_path),
            )
    assert exc_info.value.operation == "LEDGER_APPEND"


# ---------------------------------------------------------------------------
# 13. Append-only behavior
# ---------------------------------------------------------------------------


def test_ledger_writes_are_append_only(ledger_path: Path):
    key_a = _make_safe_key(normalized_event_id="evt-a")
    key_b = _make_safe_key(normalized_event_id="evt-b")
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_a,
        replay=replay_ledger(ledger_path),
    )
    bytes_after_a = ledger_path.read_bytes()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key_b,
        replay=replay_ledger(ledger_path),
    )
    bytes_after_b = ledger_path.read_bytes()
    # The first write's bytes must remain a prefix of the second
    # write's bytes (append-only contract).
    assert bytes_after_b.startswith(bytes_after_a)
    assert len(bytes_after_b) > len(bytes_after_a)


def test_duplicate_reserve_never_rewrites_existing_record(
    ledger_path: Path,
):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    bytes_before = ledger_path.read_bytes()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    bytes_after = ledger_path.read_bytes()
    assert bytes_before == bytes_after


# ---------------------------------------------------------------------------
# 14. Deterministic JSON serialization
# ---------------------------------------------------------------------------


def test_reserve_serializes_record_with_sorted_keys(ledger_path: Path):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    line = ledger_path.read_text(encoding="utf-8").rstrip("\n")
    parsed = json.loads(line)
    # Compute deterministic expected encoding.
    expected = json.dumps(
        parsed, sort_keys=True, separators=(",", ":")
    )
    assert line == expected


def test_two_runs_emit_byte_identical_records(
    stage28_2_tmp_path: Path,
):
    path_a = stage28_2_tmp_path / "a.jsonl"
    path_b = stage28_2_tmp_path / "b.jsonl"
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=path_a,
        dedupe_key=key,
        replay=replay_ledger(path_a),
    )
    reserve_dispatch_intent(
        ledger_path=path_b,
        dedupe_key=key,
        replay=replay_ledger(path_b),
    )
    assert path_a.read_bytes() == path_b.read_bytes()


# ---------------------------------------------------------------------------
# 15. Redaction tests: canaries never reach ledger / decision / repr
# ---------------------------------------------------------------------------


def test_full_lifecycle_does_not_leak_canaries_into_ledger_file(
    ledger_path: Path,
):
    # The canaries are passed nowhere -- but assert defensively
    # that the ledger file never carries any of them after a full
    # lifecycle.
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    record_pre_send(
        ledger_path=ledger_path,
        dedupe_key=key,
        artifact_reference="stage27_private_ping_payload.json",
        replay=replay_ledger(ledger_path),
    )
    record_terminal(
        ledger_path=ledger_path,
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay_ledger(ledger_path),
    )
    content = ledger_path.read_text(encoding="utf-8")
    _assert_no_canary_in(content)


def test_decision_repr_carries_no_canaries(ledger_path: Path):
    key = _make_safe_key()
    decision = reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    _assert_no_canary_in(repr(decision))
    _assert_no_canary_in(str(decision))


def test_replay_state_repr_carries_no_canaries(ledger_path: Path):
    key = _make_safe_key()
    reserve_dispatch_intent(
        ledger_path=ledger_path,
        dedupe_key=key,
        replay=replay_ledger(ledger_path),
    )
    state = replay_ledger(ledger_path)
    _assert_no_canary_in(repr(state))
    _assert_no_canary_in(str(state))


def test_path_error_for_secret_like_path_does_not_echo_path(
    stage28_2_tmp_path: Path,
):
    # Use a filename containing the literal ``bearer`` substring so
    # the Stage 28.2 path validator rejects the path. The
    # resulting exception must NOT echo the raw path -- only the
    # closed-set reason token.
    bad_path = stage28_2_tmp_path / "bearer_secret_ledger.jsonl"
    try:
        replay_ledger(bad_path)
    except Stage28_2LedgerPathError as exc:
        text = str(exc)
        assert "bearer_secret_ledger" not in text
        assert exc.reason == "LEDGER_PATH_SECRET_LIKE"
    else:
        pytest.fail("expected Stage28_2LedgerPathError")
