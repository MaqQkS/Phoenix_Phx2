"""Stage 22.2 JsonlDedupeLedger tests.

Pins JSONL-specific semantics on top of the shared dedupe
contract:

  * File-format invariants: sorted keys, compact separators,
    newline-terminated, no timestamps, no secret-bearing fields,
    locked seven-field schema.
  * Replay reconstruction across construction boundaries.
  * Hard contract violations on every documented failure mode.
  * Path discipline: ``..`` rejected, missing parent rejected,
    non-Path argument rejected, non-file path rejected, no
    ``mkdir`` performed.
  * I/O failure behaviour: write failure during
    ``check_and_record`` returns ``ledger_unavailable`` and
    leaves state unchanged; write failure during
    ``mark_dispatched`` raises ``Stage22LedgerContractError``
    and leaves state unchanged.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
    DEDUPE_OUTCOME_NEW,
    LEDGER_RECORD_TYPE_DISPATCHED,
    LEDGER_RECORD_TYPE_SEEN,
    LEDGER_REQUIRED_RECORD_FIELDS,
    STAGE22_LEDGER_RECORD_SCHEMA_VERSION,
)
from PHX2.stage22.dedupe_ledger import JsonlDedupeLedger
from PHX2.stage22.errors import Stage22LedgerContractError
from PHX2.stage22.ingest_contracts import IngestEventKey


def _key(
    *,
    provider_id: str = "helius",
    chain: str = "solana_mainnet",
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
) -> IngestEventKey:
    return IngestEventKey(
        provider_id=provider_id,
        chain=chain,
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )


def _seen_record(*, key: IngestEventKey) -> dict[str, str]:
    return {
        "schema_version": STAGE22_LEDGER_RECORD_SCHEMA_VERSION,
        "record_type": LEDGER_RECORD_TYPE_SEEN,
        "provider_id": key.provider_id,
        "chain": key.chain,
        "event_id": key.event_id,
        "provider_event_id": key.provider_event_id,
        "raw_event_hash": key.raw_event_hash,
    }


def _dispatched_record(*, key: IngestEventKey) -> dict[str, str]:
    return dict(
        _seen_record(key=key),
        record_type=LEDGER_RECORD_TYPE_DISPATCHED,
    )


def _to_line(record: dict[str, str]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


# ---------------------------------------------------------------------------
# Core semantic behaviour
# ---------------------------------------------------------------------------


def test_first_check_and_record_returns_new(tmp_path: Path) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


def test_second_check_before_dispatch_returns_duplicate_not_yet_dispatched(
    tmp_path: Path,
) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    k = _key()
    ledger.check_and_record(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_check_after_dispatch_returns_duplicate_already_dispatched(
    tmp_path: Path,
) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_mark_dispatched_idempotent_on_already_dispatched(
    tmp_path: Path,
) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_mark_dispatched_unknown_logical_key_raises(tmp_path: Path) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    with pytest.raises(Stage22LedgerContractError):
        ledger.mark_dispatched(key=_key())


def test_audit_provider_event_id_drift_resolves_as_duplicate(
    tmp_path: Path,
) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    ledger.check_and_record(key=_key(provider_event_id="prov-1"))
    outcome = ledger.check_and_record(key=_key(provider_event_id="prov-2"))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_audit_raw_event_hash_drift_resolves_as_duplicate(
    tmp_path: Path,
) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    ledger.check_and_record(key=_key(raw_event_hash="0" * 64))
    outcome = ledger.check_and_record(key=_key(raw_event_hash="f" * 64))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


# ---------------------------------------------------------------------------
# Write counts: state transitions append, idempotent calls do not
# ---------------------------------------------------------------------------


def test_first_check_writes_exactly_one_seen_record(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["record_type"] == LEDGER_RECORD_TYPE_SEEN


def test_duplicate_check_appends_no_extra_record(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    ledger.check_and_record(key=_key())
    ledger.check_and_record(key=_key())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_mark_dispatched_writes_exactly_one_dispatched_record(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    ledger.mark_dispatched(key=_key())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    record = json.loads(lines[1])
    assert record["record_type"] == LEDGER_RECORD_TYPE_DISPATCHED


def test_idempotent_mark_dispatched_appends_no_extra_record(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    ledger.mark_dispatched(key=_key())
    ledger.mark_dispatched(key=_key())
    ledger.mark_dispatched(key=_key())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# File-format invariants
# ---------------------------------------------------------------------------


def test_emitted_record_has_sorted_keys_and_compact_separators(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    raw = p.read_text(encoding="utf-8")
    line = raw.splitlines()[0]
    record = json.loads(line)
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    assert line == canonical
    assert ": " not in raw
    assert ", " not in raw


def test_emitted_record_lines_are_newline_terminated(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    ledger.mark_dispatched(key=_key())
    raw = p.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.count("\n") == 2


def test_emitted_record_carries_locked_seven_field_schema(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert set(record.keys()) == set(LEDGER_REQUIRED_RECORD_FIELDS)


def test_emitted_record_uses_locked_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert record["schema_version"] == STAGE22_LEDGER_RECORD_SCHEMA_VERSION


def test_emitted_record_has_no_timestamp_field(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    ledger.mark_dispatched(key=_key())
    raw = p.read_text(encoding="utf-8")
    for record_line in raw.splitlines():
        record = json.loads(record_line)
        for forbidden in (
            "timestamp",
            "ts",
            "observed_at",
            "observed_at_utc",
            "received_at",
            "received_at_utc",
            "failed_at",
            "failed_at_utc",
            "at_utc",
            "time",
            "datetime",
            "epoch",
        ):
            assert forbidden not in record


def test_emitted_record_has_no_secret_bearing_field_names(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    forbidden_substrings = (
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
    for field in record.keys():
        lower = field.lower()
        for needle in forbidden_substrings:
            assert needle not in lower


def test_emitted_record_round_trips_back_into_an_ingest_event_key(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    original = _key()
    ledger.check_and_record(key=original)
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    rebuilt = IngestEventKey(
        provider_id=record["provider_id"],
        chain=record["chain"],
        event_id=record["event_id"],
        provider_event_id=record["provider_event_id"],
        raw_event_hash=record["raw_event_hash"],
    )
    assert rebuilt == original


# ---------------------------------------------------------------------------
# Replay behaviour
# ---------------------------------------------------------------------------


def test_replay_reconstructs_seen_only_state(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    first = JsonlDedupeLedger(path=p)
    k = _key()
    first.check_and_record(key=k)
    # Drop the first ledger; replay from disk.
    second = JsonlDedupeLedger(path=p)
    outcome = second.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_replay_reconstructs_seen_and_dispatched_state(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    first = JsonlDedupeLedger(path=p)
    k = _key()
    first.check_and_record(key=k)
    first.mark_dispatched(key=k)
    second = JsonlDedupeLedger(path=p)
    outcome = second.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_replay_reconstructs_multiple_interleaved_events(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    first = JsonlDedupeLedger(path=p)
    keys = [_key(event_id=f"evt_{i:024x}") for i in range(5)]
    for k in keys:
        first.check_and_record(key=k)
    first.mark_dispatched(key=keys[0])
    first.mark_dispatched(key=keys[2])
    first.mark_dispatched(key=keys[4])

    second = JsonlDedupeLedger(path=p)
    for i, k in enumerate(keys):
        outcome = second.check_and_record(key=k)
        if i in (0, 2, 4):
            assert (
                outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED
            )
        else:
            assert (
                outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED
            )


def test_replay_tolerates_duplicate_seen(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    line = _to_line(_seen_record(key=_key(event_id="evt_aaaa")))
    p.write_text(line + line, encoding="utf-8")
    ledger = JsonlDedupeLedger(path=p)
    outcome = ledger.check_and_record(key=_key(event_id="evt_aaaa"))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_replay_tolerates_duplicate_dispatched(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    seen_line = _to_line(_seen_record(key=_key(event_id="evt_bbbb")))
    disp_line = _to_line(_dispatched_record(key=_key(event_id="evt_bbbb")))
    p.write_text(seen_line + disp_line + disp_line, encoding="utf-8")
    ledger = JsonlDedupeLedger(path=p)
    outcome = ledger.check_and_record(key=_key(event_id="evt_bbbb"))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


# ---------------------------------------------------------------------------
# File-presence behaviour at construction
# ---------------------------------------------------------------------------


def test_missing_file_with_existing_parent_yields_empty_state(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    assert not p.exists()
    ledger = JsonlDedupeLedger(path=p)
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


def test_empty_file_yields_empty_state(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text("", encoding="utf-8")
    ledger = JsonlDedupeLedger(path=p)
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


def test_missing_parent_raises_at_construction(tmp_path: Path) -> None:
    p = tmp_path / "missing_dir" / "ledger.jsonl"
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_constructor_does_not_create_missing_parent(tmp_path: Path) -> None:
    p = tmp_path / "missing_dir" / "ledger.jsonl"
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)
    # mkdir invariant: parent must not exist after the failed
    # construction.
    assert not (tmp_path / "missing_dir").exists()


def test_path_traversal_with_dotdot_segment_rejected(tmp_path: Path) -> None:
    p = tmp_path / ".." / "ledger.jsonl"
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_non_pathlib_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=str(tmp_path / "ledger.jsonl"))  # type: ignore[arg-type]


def test_path_pointing_at_existing_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=tmp_path)


# ---------------------------------------------------------------------------
# Replay-time contract violations
# ---------------------------------------------------------------------------


def test_replay_rejects_malformed_json_line(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text("this is not json\n", encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_json_array_instead_of_object(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text("[1,2,3]\n", encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_unknown_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["schema_version"] = "stage22_v999_unknown"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_unknown_record_type(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["record_type"] = "delivered"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_missing_required_field(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    del bad["provider_id"]
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_non_string_field_value(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    raw = (
        '{"schema_version":"' + STAGE22_LEDGER_RECORD_SCHEMA_VERSION + '",'
        '"record_type":"seen","provider_id":"helius",'
        '"chain":"solana_mainnet",'
        '"event_id":42,'
        '"provider_event_id":"prov","raw_event_hash":"x"}\n'
    )
    p.write_text(raw, encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_empty_provider_id(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["provider_id"] = ""
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_empty_chain(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["chain"] = ""
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_empty_event_id(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["event_id"] = ""
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_empty_raw_event_hash(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _seen_record(key=_key())
    bad["raw_event_hash"] = ""
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_tolerates_empty_provider_event_id(tmp_path: Path) -> None:
    """``provider_event_id`` is audit-only and may be empty per the
    Stage 22.1 ``MalformedEventRecord`` convention.
    """
    p = tmp_path / "ledger.jsonl"
    rec = _seen_record(key=_key())
    rec["provider_event_id"] = ""
    p.write_text(_to_line(rec), encoding="utf-8")
    ledger = JsonlDedupeLedger(path=p)
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_replay_rejects_dispatched_for_unseen_logical_key(
    tmp_path: Path,
) -> None:
    p = tmp_path / "ledger.jsonl"
    bad = _dispatched_record(key=_key(event_id="evt_orphan_aaaaaaaaaaaa"))
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_blank_line(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text("\n", encoding="utf-8")
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


# ---------------------------------------------------------------------------
# Write-failure behaviour
# ---------------------------------------------------------------------------


def test_write_failure_during_check_and_record_returns_ledger_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_LEDGER_UNAVAILABLE


def test_write_failure_during_check_and_record_leaves_state_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)

    real_open = builtins.open

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    failed_outcome = ledger.check_and_record(key=_key())
    assert failed_outcome.outcome == DEDUPE_OUTCOME_LEDGER_UNAVAILABLE

    # Restore real open and verify state is still empty: the
    # second call must also return ``new``, proving no state
    # was mutated under failure.
    monkeypatch.setattr(builtins, "open", real_open)
    retry_outcome = ledger.check_and_record(key=_key())
    assert retry_outcome.outcome == DEDUPE_OUTCOME_NEW


def test_write_failure_during_mark_dispatched_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22LedgerContractError):
        ledger.mark_dispatched(key=_key())


def test_write_failure_during_mark_dispatched_leaves_state_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "ledger.jsonl"
    ledger = JsonlDedupeLedger(path=p)
    ledger.check_and_record(key=_key())

    real_open = builtins.open

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22LedgerContractError):
        ledger.mark_dispatched(key=_key())

    monkeypatch.setattr(builtins, "open", real_open)
    # State unchanged: subsequent check still reports
    # not-yet-dispatched rather than already-dispatched.
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


# ---------------------------------------------------------------------------
# Cross-ledger isolation
# ---------------------------------------------------------------------------


def test_two_ledgers_at_different_paths_have_independent_state(
    tmp_path: Path,
) -> None:
    a = JsonlDedupeLedger(path=tmp_path / "ledger_a.jsonl")
    b = JsonlDedupeLedger(path=tmp_path / "ledger_b.jsonl")
    a.check_and_record(key=_key())
    outcome = b.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


# ---------------------------------------------------------------------------
# Keyword-only signature discipline
# ---------------------------------------------------------------------------


def test_check_and_record_is_keyword_only(tmp_path: Path) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    with pytest.raises(TypeError):
        ledger.check_and_record(_key())  # type: ignore[misc]


def test_mark_dispatched_is_keyword_only(tmp_path: Path) -> None:
    ledger = JsonlDedupeLedger(path=tmp_path / "ledger.jsonl")
    ledger.check_and_record(key=_key())
    with pytest.raises(TypeError):
        ledger.mark_dispatched(_key())  # type: ignore[misc]


def test_constructor_is_keyword_only(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        JsonlDedupeLedger(tmp_path / "ledger.jsonl")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Extra-field rejection (exact seven-field schema enforcement)
# ---------------------------------------------------------------------------
#
# Per the Stage 22.2 audit fix, the JSONL replay decoder enforces
# exactly the locked ``LEDGER_REQUIRED_RECORD_FIELDS`` set. Any
# additional field -- even one whose presence might look harmless
# -- is a corrupt ledger and is rejected with
# ``Stage22LedgerContractError``. The cases below cover the
# realistic Stage 23+ field-shape leaks the runner could
# accidentally introduce.


def _line_with_extra_field(
    *,
    extra_field: str,
    extra_value: object,
) -> str:
    """Serialise a seen-record line that also contains
    ``extra_field``. The extra value is typed loosely so test
    cases can include strings or other JSON-serialisable values.
    """
    base: dict[str, object] = dict(_seen_record(key=_key()))
    base[extra_field] = extra_value
    return (
        json.dumps(base, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def test_replay_rejects_extra_field_timestamp(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="timestamp",
            extra_value="2026-05-18T00:00:00Z",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_cursor(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="cursor",
            extra_value="cursor-token-abc",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_raw_payload(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="raw_payload",
            extra_value="{\"would-be\":\"provider envelope\"}",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_transport_body(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="transport_body",
            extra_value="would-be transport request body",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_recipient(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="recipient",
            extra_value="would-be channel id",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_headers(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="headers",
            extra_value="would-be Authorization: Bearer ...",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


def test_replay_rejects_extra_field_webhook_url(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        _line_with_extra_field(
            extra_field="webhook_url",
            extra_value="would-be webhook target placeholder",
        ),
        encoding="utf-8",
    )
    with pytest.raises(Stage22LedgerContractError):
        JsonlDedupeLedger(path=p)


# ---------------------------------------------------------------------------
# Cross-reload no-duplicate-send proof
# ---------------------------------------------------------------------------


def test_no_duplicate_send_across_ledger_reload_with_audit_drift(
    tmp_path: Path,
) -> None:
    """End-to-end proof of cross-run duplicate-send prevention.

    Models the Stage 22.5 bounded runner's send-only-when-new
    discipline using the 22.2 ledger seam alone. The provider
    re-emits the same logical event after a restart with
    drifted ``provider_event_id`` and ``raw_event_hash``; the
    ledger's send-suppression identity is
    ``(provider_id, chain, event_id)``, so the runner must
    not re-send and the fake send counter must stay at 1.
    """
    p = tmp_path / "ledger.jsonl"
    send_counter: dict[str, int] = {"value": 0}

    def simulate_runner_pass(
        *,
        ledger: JsonlDedupeLedger,
        key: IngestEventKey,
    ) -> str:
        outcome = ledger.check_and_record(key=key)
        if outcome.outcome == DEDUPE_OUTCOME_NEW:
            send_counter["value"] += 1
            ledger.mark_dispatched(key=key)
        return outcome.outcome

    # First runner pass: ledger sees the event for the first
    # time; runner "sends"; ledger records dispatched on disk.
    first_ledger = JsonlDedupeLedger(path=p)
    first_key = _key(
        provider_event_id="prov-original",
        raw_event_hash="0" * 64,
    )
    first_outcome = simulate_runner_pass(
        ledger=first_ledger,
        key=first_key,
    )
    assert first_outcome == DEDUPE_OUTCOME_NEW
    assert send_counter["value"] == 1

    # Reload from disk; provider re-emits with drifted audit
    # fields (mutated envelope id and content hash).
    second_ledger = JsonlDedupeLedger(path=p)
    second_key = _key(
        provider_event_id="prov-drifted",
        raw_event_hash="f" * 64,
    )
    second_outcome = simulate_runner_pass(
        ledger=second_ledger,
        key=second_key,
    )
    assert second_outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED
    assert send_counter["value"] == 1
