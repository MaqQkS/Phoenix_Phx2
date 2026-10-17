"""Watch-checkpoint canonical merge, safe diagnostics and durability.

The 2026-07-29 acceptance run recorded 63 checkpoint write attempts, 2
successes and 61 permanent ``STRUCTURAL_CHECKPOINT_FAILURE`` results. Only the
closed-set category was persisted, so the failing record set was unrecoverable.
These tests pin both halves of the repair: same-mint records are canonicalized
before serialization, and any structural refusal now carries a safe, precise
reason.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as CPE
from PHX2.free_tier_producer.compat import build30_watchlist as W

MINT_A = "9jFMtdTtREkwnimNwagzr8fhM8R3e2cpVXK2m9eNpump"
MINT_B = "7fqbk1iad3JpHXnRacjQ4ddQoBoSUZmZ5GJwqHkKpump"


def _record(mint=MINT_A, candidate_id="cand_a", **kw):
    base = dict(
        token_mint=mint, candidate_id=candidate_id,
        migration_time_utc="2026-07-29T05:41:04Z", source_ref="ref",
        seeded_at_utc="2026-07-29T06:13:00Z")
    base.update(kw)
    entry = W.WatchEntry(**base)
    payload = asdict(entry)
    payload["record_digest"] = CPE.build_record_digest(
        CPE.CHECKPOINT_KIND_WATCH, payload)
    return payload


def _write(tmp_path, records, generation=1, previous=None):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    header = CPE.build_envelope_header(
        checkpoint_kind=CPE.CHECKPOINT_KIND_WATCH,
        schema_version=W.WATCH_CHECKPOINT_SCHEMA_VERSION,
        payload_encoding=CPE.PAYLOAD_ENCODING_JSONL,
        generation=generation,
        record_digests=[str(r["record_digest"]) for r in records],
        created_at_utc="2026-07-29T06:13:00Z",
        updated_at_utc=CPE.utc_now_iso(),
        previous_generation_digest=previous,
        source_id=primary.name, migration_history=())
    CPE.write_checkpoint_generation(
        primary_path=primary, backup_path=backup, header=header,
        records=records, classify=W.classify_watch_checkpoint_file)
    return primary, backup, header


# ---------------------------------------------------------------------------
# canonical merge
# ---------------------------------------------------------------------------


def test_duplicate_mint_different_candidate_id_is_canonicalized():
    rows = [_record(candidate_id="live_1"),
            _record(candidate_id="dex_restart_1")]
    canonical, conflicts = W.canonicalize_watch_checkpoint_records(rows)
    assert conflicts == []
    assert len(canonical) == 1
    assert canonical[0]["token_mint"] == MINT_A


def test_duplicate_mint_previously_broke_the_write(tmp_path):
    """The exact pre-fix failure signature, pinned as a regression."""

    rows = [_record(candidate_id="live_1"),
            _record(candidate_id="dex_restart_1")]
    with pytest.raises(CPE.CheckpointWriteError) as excinfo:
        _write(tmp_path, rows)
    assert "CHECKPOINT_DUPLICATE_RECORD" in str(excinfo.value)
    assert CPE.classify_checkpoint_write_error(excinfo.value) == \
        CPE.CHECKPOINT_FAILURE_STRUCTURAL

    canonical, _ = W.canonicalize_watch_checkpoint_records(rows)
    _write(tmp_path, canonical)  # canonicalized set writes cleanly


def test_distinct_mints_are_never_merged():
    rows = [_record(mint=MINT_A, candidate_id="a"),
            _record(mint=MINT_B, candidate_id="b")]
    canonical, conflicts = W.canonicalize_watch_checkpoint_records(rows)
    assert conflicts == []
    assert {r["token_mint"] for r in canonical} == {MINT_A, MINT_B}


def test_merge_preserves_monotonic_high_water_values():
    left = _record(candidate_id="a", recheck_count=7, market_attempt_count=2)
    right = _record(candidate_id="b", recheck_count=3, market_attempt_count=9)
    merged, reason = W.merge_canonical_watch_records(left, right)
    assert reason == ""
    assert merged["recheck_count"] == 7
    assert merged["market_attempt_count"] == 9


def test_merge_fills_holes_but_dominant_wins_contested_fields():
    left = _record(candidate_id="a", token_name="PHILOSOPHY")
    right = _record(candidate_id="b", token_name="OTHER", symbol_or_name="PHILO")
    merged, _ = W.merge_canonical_watch_records(left, right)
    assert merged["token_name"] == "PHILOSOPHY"   # dominant kept
    assert merged["symbol_or_name"] == "PHILO"    # genuine hole filled


def test_partial_provenance_is_never_upgraded_to_complete():
    dex = _record(candidate_id="dex_1",
                  discovery_provenance=W.DISCOVERY_PROVENANCE_DEX)
    other = _record(candidate_id="dex_2",
                    discovery_provenance=W.DISCOVERY_PROVENANCE_DEX)
    merged, _ = W.merge_canonical_watch_records(dex, other)
    assert merged["discovery_provenance"] == W.DISCOVERY_PROVENANCE_DEX


def test_live_provenance_dominates_backfill():
    live = _record(candidate_id="live_1",
                   discovery_provenance=W.DISCOVERY_PROVENANCE_LIVE,
                   migration_slot=435898700)
    dex = _record(candidate_id="dex_1",
                  discovery_provenance=W.DISCOVERY_PROVENANCE_DEX)
    merged, _ = W.merge_canonical_watch_records(dex, live)
    assert merged["discovery_provenance"] == W.DISCOVERY_PROVENANCE_LIVE
    assert merged["migration_slot"] == 435898700


@pytest.mark.parametrize("field_name,left,right,expected", [
    ("migration_baseline_digest", "a" * 64, "b" * 64,
     W.CONFLICT_BASELINE_MISMATCH),
    ("delivery_ledger_key", "key-1", "key-2", W.CONFLICT_DELIVERY_MISMATCH),
    ("activation_proof_digest", "c" * 64, "d" * 64,
     W.CONFLICT_ACTIVATION_MISMATCH),
])
def test_conflicting_duplicates_fail_closed(field_name, left, right, expected):
    a = _record(candidate_id="a", **{field_name: left})
    b = _record(candidate_id="b", **{field_name: right})
    merged, reason = W.merge_canonical_watch_records(a, b)
    assert merged is None
    assert reason == expected

    canonical, conflicts = W.canonicalize_watch_checkpoint_records([a, b])
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == expected
    assert conflicts[0]["duplicate_identity_type"] == W.DUPLICATE_IDENTITY_MINT


# ---------------------------------------------------------------------------
# safe diagnostics
# ---------------------------------------------------------------------------


def test_clean_record_set_reports_no_diagnostic():
    detail = W.describe_checkpoint_records(
        [_record(mint=MINT_A, candidate_id="a"),
         _record(mint=MINT_B, candidate_id="b")])
    assert detail is None


def test_duplicate_diagnostic_is_precise_and_safe():
    rows = [_record(candidate_id="live_1"), _record(candidate_id="dex_1")]
    detail = W.describe_checkpoint_records(rows)
    assert detail is not None
    assert detail["failure_category"] == CPE.CHECKPOINT_FAILURE_STRUCTURAL
    assert detail["reason"] == CPE.QUARANTINE_DUPLICATE_RECORD
    assert detail["record_index"] == 1
    assert detail["first_record_index"] == 0
    assert detail["field_path"] == "identity.mint"
    assert detail["duplicate_identity_type"] == W.DUPLICATE_IDENTITY_MINT
    assert detail["schema_version"] == W.WATCH_CHECKPOINT_SCHEMA_VERSION
    assert detail["candidate_count"] == 2
    assert len(detail["record_identity_digest"]) == 64


def test_diagnostic_never_leaks_candidate_contents():
    rows = [_record(candidate_id="live_1", token_name="LEAKCANARY"),
            _record(candidate_id="dex_1", token_name="LEAKCANARY")]
    detail = W.describe_checkpoint_records(rows)
    assert "LEAKCANARY" not in str(detail)
    assert MINT_A not in str(detail)


@pytest.mark.parametrize("value,expected_path", [
    ({"a": Decimal("1.5")}, "a"),
    ({"a": {"b": Decimal("1")}}, "a.b"),
    ({"a": [1, 2, Decimal("3")]}, "a[2]"),
    ({"a": 1.5}, "a"),
    ({"a": {"b": [{"c": Decimal("9")}]}}, "a.b[0].c"),
])
def test_unserializable_field_path_is_exact(value, expected_path):
    assert W._unserializable_field_path(value) == expected_path


def test_json_safe_values_report_no_path():
    payload = {"a": "s", "b": 1, "c": True, "d": None, "e": [1, "x"],
               "f": {"g": None}}
    assert W._unserializable_field_path(payload) is None


@pytest.mark.parametrize("bad", [
    {"global_fees": {"global_fees_paid_sol": Decimal("0.9")}},
    {"global_fee_support": {"fee_support_per_10k_sol": Decimal("0.37")}},
    {"market": {"volume_5m_usd": 1234.5}},
])
def test_new_observation_shapes_are_caught_by_path_not_coerced(bad):
    """Decimal/float payloads must be located, never silently str()-coerced."""

    path = W._unserializable_field_path(bad)
    assert path is not None and "." in path


# ---------------------------------------------------------------------------
# durability behaviour
# ---------------------------------------------------------------------------


def test_repeated_valid_writes_all_succeed(tmp_path):
    """63 consecutive writes over valid canonical state must all succeed.

    The failed run managed 2. Under canonical state there is no mechanism left
    that degrades with generation count.
    """

    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    previous = None
    for generation in range(1, 64):
        rows, _ = W.canonicalize_watch_checkpoint_records(
            [_record(mint=MINT_A, candidate_id="a", recheck_count=generation),
             _record(mint=MINT_B, candidate_id="b")])
        header = CPE.build_envelope_header(
            checkpoint_kind=CPE.CHECKPOINT_KIND_WATCH,
            schema_version=W.WATCH_CHECKPOINT_SCHEMA_VERSION,
            payload_encoding=CPE.PAYLOAD_ENCODING_JSONL,
            generation=generation,
            record_digests=[str(r["record_digest"]) for r in rows],
            created_at_utc="2026-07-29T06:13:00Z",
            updated_at_utc=CPE.utc_now_iso(),
            previous_generation_digest=previous,
            source_id=primary.name, migration_history=())
        CPE.write_checkpoint_generation(
            primary_path=primary, backup_path=backup, header=header,
            records=rows, classify=W.classify_watch_checkpoint_file)
        previous = header["envelope_digest"]
    assert W.classify_watch_checkpoint_file(primary).state == \
        CPE.FILE_VALID_CURRENT


def test_prior_valid_generation_is_preserved_on_structural_failure(tmp_path):
    good = [_record(mint=MINT_A, candidate_id="a")]
    primary, backup, header = _write(tmp_path, good)
    before = primary.read_bytes()

    bad = [_record(candidate_id="live_1"), _record(candidate_id="dex_1")]
    with pytest.raises(CPE.CheckpointWriteError):
        _write(tmp_path, bad, generation=2,
               previous=header["envelope_digest"])
    assert primary.read_bytes() == before
    assert W.classify_watch_checkpoint_file(primary).state == \
        CPE.FILE_VALID_CURRENT


def test_restore_reproduces_canonical_state_exactly(tmp_path):
    rows, _ = W.canonicalize_watch_checkpoint_records(
        [_record(mint=MINT_A, candidate_id="a", recheck_count=4),
         _record(mint=MINT_B, candidate_id="b", recheck_count=9)])
    primary, _, _ = _write(tmp_path, rows)
    state = W.classify_watch_checkpoint_file(primary)
    assert state.state == CPE.FILE_VALID_CURRENT
    restored = {r["token_mint"]: r for r in state.records}
    assert restored[MINT_A]["recheck_count"] == 4
    assert restored[MINT_B]["recheck_count"] == 9


def test_structural_error_classification_is_never_retried():
    exc = CPE.CheckpointWriteError(
        "CHECKPOINT_WRITE_READBACK_INVALID:CHECKPOINT_DUPLICATE_RECORD")
    assert CPE.classify_checkpoint_write_error(exc) == \
        CPE.CHECKPOINT_FAILURE_STRUCTURAL
    assert CPE.is_transient_checkpoint_write_error(exc) is False


def test_transient_error_classification_is_retryable():
    exc = CPE.CheckpointWriteError("CHECKPOINT_WRITE_FAILED:PermissionError")
    assert CPE.classify_checkpoint_write_error(exc) == \
        CPE.CHECKPOINT_FAILURE_TRANSIENT
    assert CPE.is_transient_checkpoint_write_error(exc) is True


def test_no_credential_bearing_values_in_diagnostics():
    rows = [_record(candidate_id="a", delivery_ledger_key="tok_CANARY"),
            _record(candidate_id="b", delivery_ledger_key="tok_OTHER")]
    _, conflicts = W.canonicalize_watch_checkpoint_records(rows)
    assert conflicts
    assert "CANARY" not in str(conflicts)
    assert "tok_" not in str(conflicts)
