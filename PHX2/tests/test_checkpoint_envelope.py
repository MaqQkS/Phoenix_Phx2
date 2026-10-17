"""PHX2-E2E-005 — authenticated checkpoint envelope + load decision matrix.

Deterministic offline proofs that corrupt, tampered, truncated, duplicated,
mis-typed, mis-bound or unsupported checkpoint content NEVER silently loads
as an empty healthy state, and that the exact primary/backup decision matrix
(cases A-I) selects only chain-consistent authenticated generations.

Temporary checkpoint directories only. No live run, no provider/transport
connection, no real ledger.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.compat.build30_watchlist import (
    SEED_OUTCOME_CHECKPOINT_QUARANTINED,
    WATCH_CHECKPOINT_SCHEMA_VERSION,
    Watchlist,
    classify_watch_checkpoint_file,
)

NOW = "2026-07-15T12:00:00Z"
LATER = "2026-07-15T13:00:00Z"


def _mint(index: int) -> str:
    return f"EnvFixture{index:04d}" + "0" * 26 + "pump"


def _seed(watch: Watchlist, count: int) -> None:
    for index in range(count):
        entry, outcome = watch.seed_with_outcome(
            {"token_mint": _mint(index), "candidate_id": f"env{index}"},
            seeded_at_utc=NOW)
        assert entry is not None and outcome in ("ADMITTED", "EXISTING")


def _watchlist(tmp_path: Path, count: int = 2) -> Path:
    state = tmp_path / "watch_state.jsonl"
    watch = Watchlist(max_size=256,
                      terminal_history_path=tmp_path / "history.jsonl")
    _seed(watch, count)
    watch.persist(state)
    return state


def _load(tmp_path: Path, state: Path, **kwargs) -> Watchlist:
    return Watchlist.load(
        state, max_size=256,
        terminal_history_path=tmp_path / f"history_{len(list(tmp_path.iterdir()))}.jsonl",
        **kwargs)


def _read_doc(state: Path):
    lines = [line for line in state.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    header = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:]]
    return header, records


def _resign(header, records):
    """Recompute the full digest chain after a semantic mutation, so the test
    isolates the SEMANTIC validator (not merely a digest mismatch)."""

    for record in records:
        record.pop("record_digest", None)
        record["record_digest"] = cpe.build_record_digest(
            header["checkpoint_kind"], record)
    header["record_count"] = len(records)
    header["payload_digest"] = cpe.build_payload_digest(
        header["checkpoint_kind"], header["schema_version"],
        [record["record_digest"] for record in records])
    header.pop("envelope_digest", None)
    header["envelope_digest"] = cpe.build_envelope_digest(header)
    return header, records


def _write_doc(state: Path, header, records) -> None:
    lines = [json.dumps(header, sort_keys=True, separators=(",", ":"))]
    lines.extend(json.dumps(record, sort_keys=True, separators=(",", ":"))
                 for record in records)
    state.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Load decision matrix (required tests 1-9)
# ---------------------------------------------------------------------------

def test_01_missing_primary_and_backup_is_checkpoint_not_found(tmp_path):
    watch = _load(tmp_path, tmp_path / "watch_state.jsonl")
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_NOT_FOUND
    assert not watch.checkpoint.checkpoint_files_found
    assert not watch.checkpoint_quarantined


def test_02_valid_primary_restores(tmp_path):
    state = _watchlist(tmp_path)
    watch = _load(tmp_path, state)
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_PRIMARY_OK
    assert len(watch.all_entries()) == 2


def test_03_valid_primary_and_backup_select_newest_generation(tmp_path):
    state = _watchlist(tmp_path)
    watch = _load(tmp_path, state)
    _seed(watch, 3)  # entry 2 is new
    watch.persist(state)   # generation 2; backup = generation 1
    restored = _load(tmp_path, state)
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK
    assert restored.checkpoint.checkpoint_generation == 2
    assert len(restored.all_entries()) == 3


def test_04_invalid_primary_with_valid_backup_restores_backup(tmp_path):
    state = _watchlist(tmp_path)
    watch = _load(tmp_path, state)
    watch.persist(state)  # establishes a valid backup
    state.write_text("{corrupt", encoding="utf-8")
    restored = _load(tmp_path, state)
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
    assert restored.checkpoint.checkpoint_recovered_from_backup
    assert len(restored.all_entries()) == 2


def test_05_missing_primary_with_valid_backup_restores_backup(tmp_path):
    state = _watchlist(tmp_path)
    watch = _load(tmp_path, state)
    watch.persist(state)
    state.unlink()
    restored = _load(tmp_path, state)
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
    assert len(restored.all_entries()) == 2


def test_06_valid_primary_with_invalid_backup_warns_and_keeps_primary(tmp_path):
    state = _watchlist(tmp_path)
    backup = Path(str(state) + ".bak")
    backup.write_text("{corrupt", encoding="utf-8")
    restored = _load(tmp_path, state)
    assert restored.checkpoint.checkpoint_status == cpe.CHECKPOINT_BACKUP_INVALID
    assert restored.checkpoint.checkpoint_backup_invalid_reason
    assert len(restored.all_entries()) == 2
    # the primary is NOT replaced by the invalid backup
    assert classify_watch_checkpoint_file(state).state == cpe.FILE_VALID_CURRENT


def test_07_and_10_corrupt_primary_and_backup_quarantine_not_empty(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    state.write_text("{corrupt json\n", encoding="utf-8")
    Path(str(state) + ".bak").write_text("also not json\n", encoding="utf-8")
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_QUARANTINED
    assert watch.checkpoint.checkpoint_quarantine_reason \
        in cpe.QUARANTINE_REASONS
    assert watch.all_entries() == []          # no state, but NOT healthy-empty
    assert watch.summary()["checkpoint_quarantined"] is True
    blocked, outcome = watch.seed_with_outcome(
        {"token_mint": _mint(9), "candidate_id": "x"}, seeded_at_utc=NOW)
    assert blocked is None and outcome == SEED_OUTCOME_CHECKPOINT_QUARANTINED
    # evidence preserved unchanged; persistence refused
    watch.persist(state)
    assert state.read_text(encoding="utf-8") == "{corrupt json\n"
    assert watch.summary()["checkpoint_persist_refused"] == 1


def test_08_unsupported_schema_version_quarantines(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    header["schema_version"] = "phx2_watch_checkpoint_v99"
    _write_doc(state, *_resign(header, records))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_SCHEMA_UNSUPPORTED


def test_09_divergent_generations_without_chain_quarantine(tmp_path):
    # same generation, different payloads
    state = _watchlist(tmp_path)
    backup = Path(str(state) + ".bak")
    header, records = _read_doc(state)
    _write_doc(backup, *_resign(
        {**header}, [dict(records[0])]))   # same generation, 1 record
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_GENERATION_CONFLICT
    assert watch.checkpoint.checkpoint_generation_conflict_total == 1
    # broken previous-generation chain (gap without linkage)
    header2, records2 = _read_doc(state)
    header2["generation"] = int(header2["generation"]) + 5
    _write_doc(state, *_resign(header2, records2))
    watch2 = _load(tmp_path, state)
    assert watch2.checkpoint_quarantined
    assert watch2.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_GENERATION_CONFLICT


# ---------------------------------------------------------------------------
# Structural corruption (required tests 10-18)
# ---------------------------------------------------------------------------

def test_11_truncated_envelope_does_not_load_empty(tmp_path):
    state = _watchlist(tmp_path)
    text = state.read_text(encoding="utf-8")
    state.write_text(text[: len(text) // 2], encoding="utf-8")
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason in (
        cpe.QUARANTINE_TRUNCATED, cpe.QUARANTINE_RECORD_COUNT_MISMATCH)


def test_12_empty_existing_file_is_not_missing(tmp_path):
    # Watch: zero bytes was the valid legacy empty encoding -> migrates to an
    # explicit EMPTY current checkpoint; never CHECKPOINT_NOT_FOUND.
    state = tmp_path / "watch_state.jsonl"
    state.write_text("", encoding="utf-8")
    watch = _load(tmp_path, state)
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    assert watch.checkpoint.checkpoint_files_found
    assert watch.all_entries() == []
    # ATH: an empty file was never valid -> quarantine, never "not found".
    from PHX2.free_tier_producer.ath_state import CentralAthStateStore
    ath_dir = tmp_path / "ath"
    ath_dir.mkdir()
    (ath_dir / "ath_state_checkpoint.json").write_text("", encoding="utf-8")
    store = CentralAthStateStore(ath_dir)
    assert store.checkpoint.checkpoint_status == cpe.CHECKPOINT_QUARANTINED
    assert store.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_TRUNCATED


def test_13_record_count_mismatch_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    # fewer record lines than record_count: truncation
    _write_doc(state, header, records[:-1])
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_RECORD_COUNT_MISMATCH


def test_14_payload_digest_mismatch_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    _write_doc(state, header, list(reversed(records)))  # order is bound
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_PAYLOAD_DIGEST_INVALID
    assert watch.checkpoint.checkpoint_digest_failure_total >= 1


def test_15_envelope_digest_mismatch_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    header["generation"] = 7   # header field changed without re-signing
    _write_doc(state, header, records)
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_ENVELOPE_DIGEST_INVALID


def test_16_record_digest_mismatch_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    records[0]["recheck_count"] = 999   # tampered without re-signing
    _write_doc(state, header, records)
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_RECORD_DIGEST_INVALID


def test_17_zero_digest_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    records[0]["record_digest"] = "0" * 64
    header["payload_digest"] = cpe.build_payload_digest(
        header["checkpoint_kind"], header["schema_version"],
        [record["record_digest"] for record in records])
    header.pop("envelope_digest", None)
    header["envelope_digest"] = cpe.build_envelope_digest(header)
    _write_doc(state, header, records)
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_RECORD_DIGEST_INVALID
    assert not cpe.is_sha256_digest("0" * 64)


def test_18_wrong_checkpoint_kind_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    header["checkpoint_kind"] = cpe.CHECKPOINT_KIND_ATH
    for record in records:
        record.pop("record_digest", None)
        record["record_digest"] = cpe.build_record_digest(
            cpe.CHECKPOINT_KIND_ATH, record)
    header["payload_digest"] = cpe.build_payload_digest(
        cpe.CHECKPOINT_KIND_ATH, header["schema_version"],
        [record["record_digest"] for record in records])
    header.pop("envelope_digest", None)
    header["envelope_digest"] = cpe.build_envelope_digest(header)
    _write_doc(state, header, records)
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_KIND_INVALID


# ---------------------------------------------------------------------------
# Record binding + typed-value rejection (required tests 19-25)
# ---------------------------------------------------------------------------

def test_19_duplicate_candidate_id_fails(tmp_path):
    state = _watchlist(tmp_path, count=2)
    header, records = _read_doc(state)
    records[1]["candidate_id"] = records[0]["candidate_id"]
    _write_doc(state, *_resign(header, records))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_DUPLICATE_RECORD


def test_20_conflicting_mint_binding_fails(tmp_path):
    state = _watchlist(tmp_path, count=2)
    header, records = _read_doc(state)
    records[1]["token_mint"] = records[0]["token_mint"]
    _write_doc(state, *_resign(header, records))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_DUPLICATE_RECORD


def test_21_invalid_timestamp_fails(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    records[0]["seeded_at_utc"] = "not-a-timestamp"
    _write_doc(state, *_resign(header, records))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_TIMESTAMP_INVALID


@pytest.mark.parametrize("bad_value, expected_reason", [
    ("definitely-not-decimal", cpe.QUARANTINE_NUMERIC_INVALID),   # 22
    ("NaN", cpe.QUARANTINE_NUMERIC_INVALID),                      # 23
    ("Infinity", cpe.QUARANTINE_NUMERIC_INVALID),                 # 24
    ("-5", cpe.QUARANTINE_NUMERIC_INVALID),                       # negative
])
def test_22_23_24_invalid_decimal_nan_infinity_fail(
        tmp_path, bad_value, expected_reason):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    records[0]["migration_market_cap_usd"] = bad_value
    _write_doc(state, *_resign(header, records))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason == expected_reason


def test_22b_float_typed_economic_value_cannot_even_be_signed(tmp_path):
    # A float where the contract requires an exact Decimal string can never
    # carry a valid canonical record digest: the digest layer refuses floats
    # entirely, so a float-typed record always fails closed.
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    records[0]["migration_market_cap_usd"] = 1000.5
    with pytest.raises(ValueError):
        cpe.build_record_digest(header["checkpoint_kind"], records[0])
    _write_doc(state, header, records)   # stale digest over float content
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_RECORD_DIGEST_INVALID


def test_23b_raw_json_nan_infinity_tokens_are_rejected_at_parse():
    with pytest.raises(ValueError):
        cpe.strict_json_loads('{"value": NaN}')
    with pytest.raises(ValueError):
        cpe.strict_json_loads('{"value": Infinity}')
    with pytest.raises(ValueError):
        cpe.strict_json_loads('{"a": 1, "a": 2}')   # duplicate JSON keys


def test_25_negative_ath_fails(tmp_path):
    from PHX2.free_tier_producer.ath_state import CentralAthStateStore
    ath_dir = tmp_path / "ath"
    ath_dir.mkdir()
    (ath_dir / "ath_state_checkpoint.json").write_text(json.dumps({
        "schema_version": "phx2_central_ath_v1",
        "artifact_kind": "CENTRAL_ATH_RESTART_CHECKPOINT",
        "updated_at": NOW,
        "mints": {("Neg" + "0" * 37 + "pump"): {
            "ath_price": "-1", "ath_market_cap": "-50000",
            "ath_timestamp": NOW, "ath_provider": "PAID_CURRENT_PRICE",
            "ath_observation_type": "PAID_CURRENT_PRICE",
            "ath_status": "CONFIRMED",
        }},
    }), encoding="utf-8")
    store = CentralAthStateStore(ath_dir)
    assert store.checkpoint_quarantined
    assert store.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_NUMERIC_INVALID


# ---------------------------------------------------------------------------
# Write-path safety (required tests 57-58)
# ---------------------------------------------------------------------------

def test_57_failed_readback_validation_does_not_install(tmp_path):
    state = _watchlist(tmp_path)
    original = state.read_bytes()
    header, records = _read_doc(state)

    def rejecting_classifier(path):
        classification = classify_watch_checkpoint_file(path)
        if Path(path).name.endswith(".next.tmp"):
            classification.state = cpe.FILE_INVALID
            classification.reason = cpe.QUARANTINE_JSON_INVALID
        return classification

    with pytest.raises(cpe.CheckpointWriteError):
        cpe.write_checkpoint_generation(
            primary_path=state,
            backup_path=Path(str(state) + ".bak"),
            header=header,
            records=records,
            classify=rejecting_classifier,
        )
    assert state.read_bytes() == original     # previous generation survives


def test_58_backup_recovery_does_not_overwrite_only_valid_generation(tmp_path):
    state = _watchlist(tmp_path)
    watch = _load(tmp_path, state)
    watch.persist(state)                       # generation 2 + backup gen 1
    backup = Path(str(state) + ".bak")
    backup_bytes = backup.read_bytes()
    state.write_text("{corrupt", encoding="utf-8")
    restored = _load(tmp_path, state)
    assert restored.checkpoint.checkpoint_recovered_from_backup
    # the only valid generation was never touched by recovery
    assert backup.read_bytes() == backup_bytes
    # the corrupt primary evidence was preserved before the controlled rewrite
    assert any(p.name.startswith("watch_state.jsonl.invalid_evidence_")
               for p in tmp_path.iterdir())
    assert classify_watch_checkpoint_file(state).state == cpe.FILE_VALID_CURRENT


# ---------------------------------------------------------------------------
# Hostile / boundary inputs
# ---------------------------------------------------------------------------

def test_hostile_invalid_utf8_fails_closed(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    state.write_bytes(b"\xff\xfe{not utf8}\n")
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_JSON_INVALID


def test_hostile_truncated_final_newline_still_validates(tmp_path):
    state = _watchlist(tmp_path)
    text = state.read_text(encoding="utf-8")
    state.write_text(text.rstrip("\n"), encoding="utf-8")
    watch = _load(tmp_path, state)
    assert not watch.checkpoint_quarantined
    assert len(watch.all_entries()) == 2


def test_hostile_very_large_decimal_strings_round_trip(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    watch = Watchlist(max_size=8, terminal_history_path=tmp_path / "h.jsonl")
    entry, _ = watch.seed_with_outcome(
        {"token_mint": _mint(0), "candidate_id": "big"}, seeded_at_utc=NOW)
    big = "9" * 60 + "." + "1" * 40
    entry.migration_market_cap_usd = big
    watch.persist(state)
    restored = _load(tmp_path, state)
    assert restored.get(_mint(0)).migration_market_cap_usd == big


def test_hostile_backup_newer_than_primary_needs_chain_proof(tmp_path):
    state = _watchlist(tmp_path)
    backup = Path(str(state) + ".bak")
    watch = _load(tmp_path, state)
    watch.persist(state)                 # primary gen2, backup gen1
    # swap the files: backup now NEWER than primary
    primary_bytes = state.read_bytes()
    backup_bytes = backup.read_bytes()
    state.write_bytes(backup_bytes)
    backup.write_bytes(primary_bytes)
    restored = _load(tmp_path, state)
    # gen2 backup chains to gen1 primary: newest consistent generation wins
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
    assert restored.checkpoint.checkpoint_generation == 2


def test_hostile_clock_skew_policy(tmp_path):
    state = _watchlist(tmp_path)
    header, records = _read_doc(state)
    # beyond tolerance: quarantine
    future = "2030-01-01T00:00:00Z"
    header_future = dict(header)
    header_future["updated_at_utc"] = future
    _write_doc(state, *_resign(header_future, list(records)))
    watch = _load(tmp_path, state)
    assert watch.checkpoint_quarantined
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_TIMESTAMP_INVALID
    # within tolerance: restores (validation_now_utc anchors the clock)
    _write_doc(state, *_resign(dict(header), list(records)))
    within = _load(tmp_path, state,
                   validation_now_utc=header["updated_at_utc"])
    assert not within.checkpoint_quarantined


def test_hostile_zero_one_and_128_record_checkpoints(tmp_path):
    for count in (0, 1, 128):
        sub = tmp_path / f"n{count}"
        sub.mkdir()
        state = sub / "watch_state.jsonl"
        watch = Watchlist(max_size=256,
                          terminal_history_path=sub / "history.jsonl")
        _seed(watch, count)
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=256, terminal_history_path=sub / "history2.jsonl")
        assert not restored.checkpoint_quarantined
        assert len(restored.all_entries()) == count
        assert restored.checkpoint.checkpoint_records_validated == count


def test_seed_outcome_token_is_closed_set():
    assert SEED_OUTCOME_CHECKPOINT_QUARANTINED == "CHECKPOINT_QUARANTINED"
    assert WATCH_CHECKPOINT_SCHEMA_VERSION == "phx2_watch_checkpoint_v2"
    for reason in cpe.QUARANTINE_REASONS:
        assert reason.startswith("CHECKPOINT_")
