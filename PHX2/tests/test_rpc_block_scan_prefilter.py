"""Pure block decode/scan: prefilter soundness, worker purity, determinism.

The prefilter may only ever be WRONG in the safe direction. Every test here
that classifies a block ``DEFINITELY_IRRELEVANT`` also proves, against the full
serial decode, that the block really did carry zero relevant events; every
unknown, ambiguous, escaped or unexpected payload must fall back to a full
decode instead of being skipped.

Worker purity is tested as a capability question, not a style question: the
worker entrypoint runs with the filesystem, sockets and HTTP stack rigged to
explode, and it still returns a correct result.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from PHX2.free_tier_producer import rpc_block_scan as rbs
from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer.rpc_block_pool import (
    RPC_APPLY_BATCH_SIZE_MAX,
    RPC_APPLY_PROCESSES_MAX,
    BlockScanPoolError,
    BoundedBlockScanPool,
    default_apply_processes,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID

PROGRAM_IDS = (PUMPSWAP_PROGRAM_ID,)
BLOCK_TIME = 1_753_142_400

#: Base58 excludes 0, O, I and l. Synthetic signatures and blockhashes must
#: stay inside the alphabet or the production decoder refuses them for the
#: wrong reason and the test proves nothing about the scan.
_B58_DIGITS = "ABCDEFGHJK"


def b58_slot_hash(slot: int) -> str:
    return "Hb" + "".join(_B58_DIGITS[int(digit)] for digit in str(slot))


def make_tx(signature: str, *, relevant: bool = True,
            failed: bool = False) -> Dict[str, Any]:
    keys = ["FeePayer1111111111111111111111111111111111"]
    if relevant:
        keys.append(PUMPSWAP_PROGRAM_ID)
    return {
        "meta": {
            "err": ({"InstructionError": [0, "Custom"]} if failed else None),
            "logMessages": [],
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
        "transaction": {
            "message": {"accountKeys": keys, "instructions": []},
            "signatures": [signature],
        },
    }


def make_result(slot: int, txs: List[Dict[str, Any]], *,
                parent_slot: Optional[int] = None) -> Dict[str, Any]:
    # Key order matters to the prefilter: the header is flat and scalar, and
    # ``transactions`` is the last member. That is the shape the provider emits.
    return {
        "blockHeight": slot - 10,
        "blockTime": BLOCK_TIME,
        "blockhash": b58_slot_hash(slot),
        "parentSlot": (slot - 1) if parent_slot is None else parent_slot,
        "previousBlockhash": b58_slot_hash(slot - 1),
        "transactions": txs,
    }


def envelope_bytes(result: Dict[str, Any]) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "result": result, "id": 1},
                      separators=(",", ":")).encode("utf-8")


IRRELEVANT = make_result(500, [make_tx(f"S1gSkip{i + 1}", relevant=False)
                               for i in range(6)])
RELEVANT = make_result(501, [make_tx("S1gSkipA", relevant=False),
                             make_tx("S1gKeep1", relevant=True),
                             make_tx("S1gKeep2", relevant=True)])


class TestPrefilter:
    def test_recognised_irrelevant_block_safely_skips_full_decode(self) -> None:
        verdict, header = rbs.classify_block_payload(
            envelope_bytes(IRRELEVANT), PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_DEFINITELY_IRRELEVANT
        assert header["blockhash"] == b58_slot_hash(500)
        assert header["previous_blockhash"] == b58_slot_hash(499)
        assert header["parent_slot"] == 499
        assert header["transaction_count"] == 6
        # The safety claim itself: the full serial decode finds nothing.
        full = rbs.scan_block_result(
            slot=500, result=IRRELEVANT, program_ids=PROGRAM_IDS)
        assert full["entries"] == []
        assert full["transaction_count"] == header["transaction_count"]

    def test_relevant_block_is_never_prefilter_skipped(self) -> None:
        verdict, header = rbs.classify_block_payload(
            envelope_bytes(RELEVANT), PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED
        assert header is None
        scan = rbs.scan_block_payload(
            slot=501, payload=envelope_bytes(RELEVANT),
            program_ids=PROGRAM_IDS)
        assert scan["prefilter"] == rbs.PREFILTER_FULL_DECODE_REQUIRED
        assert len(scan["entries"]) == 2

    @pytest.mark.parametrize("payload", [
        b"",
        b"\x1f\x8b\x08\x00compressed",          # gzip magic, not JSON
        b"not json at all",
        b'{"jsonrpc":"2.0","result":"base64-encoded-block","id":1}',
    ])
    def test_unknown_encoding_forces_full_decode(self, payload: bytes) -> None:
        verdict, header = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED
        assert header is None

    def test_unicode_escape_anywhere_forces_full_decode(self) -> None:
        result = make_result(502, [make_tx("S1gEsc", relevant=False)])
        result["transactions"][0]["meta"]["logMessages"] = ["café"]
        payload = json.dumps({"jsonrpc": "2.0", "result": result, "id": 1},
                             separators=(",", ":")).encode("utf-8")
        assert b"\\u" in payload
        verdict, _ = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_extra_scalar_member_after_transactions_stays_sound(self) -> None:
        """A trailing member changes neither the header nor the density."""

        result = dict(IRRELEVANT)
        result["rewards"] = []
        verdict, header = rbs.classify_block_payload(
            envelope_bytes(result), PROGRAM_IDS)
        full = rbs.scan_block_result(
            slot=500, result=result, program_ids=PROGRAM_IDS)
        assert full["entries"] == []
        if verdict == rbs.PREFILTER_DEFINITELY_IRRELEVANT:
            assert header["transaction_count"] == full["transaction_count"]
            assert header["blockhash"] == full["blockhash"]
            assert header["parent_slot"] == full["parent_slot"]

    def test_structured_envelope_tail_forces_full_decode(self) -> None:
        payload = envelope_bytes(IRRELEVANT).replace(
            b'"id":1}', b'"id":1,"context":{"apiVersion":"x"}}')
        verdict, _ = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_uncorroborated_transaction_count_forces_full_decode(self) -> None:
        payload = envelope_bytes(IRRELEVANT).replace(
            b'"signatures":[', b'"signatures2":[', 1)
        verdict, _ = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_nested_header_member_forces_full_decode(self) -> None:
        result = {"extra": {"nested": 1}, **IRRELEVANT}
        verdict, _ = rbs.classify_block_payload(
            envelope_bytes(result), PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_disagreeing_per_transaction_tokens_force_full_decode(self) -> None:
        result = make_result(503, [make_tx("S1gA", relevant=False),
                                   make_tx("S1gB", relevant=False)])
        payload = envelope_bytes(result).replace(b'"meta":{', b'"meta2":{', 1)
        verdict, _ = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_error_envelope_forces_full_decode(self) -> None:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32007, "message": "skipped"}}).encode("utf-8")
        verdict, _ = rbs.classify_block_payload(payload, PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_empty_program_id_set_never_skips(self) -> None:
        verdict, _ = rbs.classify_block_payload(
            envelope_bytes(IRRELEVANT), ())
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED

    def test_program_id_only_in_loaded_addresses_is_not_skipped(self) -> None:
        tx = make_tx("S1gLoaded", relevant=False)
        tx["meta"]["loadedAddresses"] = {
            "writable": [PUMPSWAP_PROGRAM_ID], "readonly": []}
        result = make_result(504, [tx])
        verdict, _ = rbs.classify_block_payload(
            envelope_bytes(result), PROGRAM_IDS)
        assert verdict == rbs.PREFILTER_FULL_DECODE_REQUIRED
        scan = rbs.scan_block_result(
            slot=504, result=result, program_ids=PROGRAM_IDS)
        assert len(scan["entries"]) == 1


class TestScanEquivalenceAndDeterminism:
    def test_serial_and_worker_decode_match(self) -> None:
        payload = envelope_bytes(RELEVANT)
        serial = rbs.scan_block_result(
            slot=501, result=RELEVANT, program_ids=PROGRAM_IDS)
        worker = rbs.scan_block_task({
            "slot": 501, "payload": payload, "program_ids": PROGRAM_IDS})
        for key in ("slot", "status", "blockhash", "previous_blockhash",
                    "parent_slot", "block_time", "transaction_count"):
            assert serial[key] == worker[key]
        assert serial["entries"] == worker["entries"]

    def test_worker_output_is_deterministic(self) -> None:
        task = {"slot": 501, "payload": envelope_bytes(RELEVANT),
                "program_ids": PROGRAM_IDS}
        first = rbs.scan_block_task(dict(task))
        for _ in range(4):
            assert rbs.scan_block_task(dict(task)) == first

    def test_every_rejection_classification_is_reproduced(self) -> None:
        txs = [
            make_tx("S1gAdmit", relevant=True),
            make_tx("S1gErred", relevant=True, failed=True),
            make_tx("S1gSkipped", relevant=False),
        ]
        no_signature = make_tx("S1gNoSig", relevant=True)
        no_signature["transaction"]["signatures"] = []
        txs.append(no_signature)
        unprojectable = make_tx("S1gBadKey", relevant=True)
        unprojectable["transaction"]["message"]["accountKeys"] = [
            "not-base58-0OIl", PUMPSWAP_PROGRAM_ID]
        txs.append(unprojectable)
        result = make_result(505, txs)
        scan = rbs.scan_block_result(
            slot=505, result=result, program_ids=PROGRAM_IDS)
        assert [(e["index"], e["kind"]) for e in scan["entries"]] == [
            (0, rbs.ENTRY_APPLY),
            (1, rbs.ENTRY_REJECT_META),
            (3, rbs.ENTRY_REJECT_SIGNATURE),
            (4, rbs.ENTRY_REJECT_PROJECTION),
        ]

    def test_apply_entry_round_trips_into_the_live_message_type(self) -> None:
        scan = rbs.scan_block_result(
            slot=501, result=RELEVANT, program_ids=PROGRAM_IDS)
        entry = scan["entries"][0]
        update = rbs.parse_scan_entry_update(entry)
        assert update is not None
        assert int(update.transaction.slot) == 501
        assert update.SerializeToString() == entry["update"]

    @pytest.mark.parametrize("result,status", [
        ({"jsonrpc": "2.0", "result": None, "id": 1},
         rbs.BLOCK_SCAN_UNAVAILABLE),
        ({"jsonrpc": "2.0", "id": 1,
          "error": {"code": -32007, "message": "skipped"}},
         rbs.BLOCK_SCAN_UNAVAILABLE),
        ({"jsonrpc": "2.0", "id": 1,
          "error": {"code": -32602, "message": "bad"}},
         rbs.BLOCK_SCAN_MALFORMED),
        ({"jsonrpc": "2.0", "result": {"blockhash": "x"}, "id": 1},
         rbs.BLOCK_SCAN_MALFORMED),
    ])
    def test_failure_envelopes_map_to_closed_set_statuses(
            self, result: Dict[str, Any], status: str) -> None:
        scan = rbs.scan_block_payload(
            slot=600, payload=json.dumps(result).encode("utf-8"),
            program_ids=PROGRAM_IDS)
        assert scan["status"] == status
        assert scan["entries"] == []

    def test_parent_slot_at_or_after_slot_is_malformed(self) -> None:
        result = make_result(700, [], parent_slot=700)
        assert rbs.scan_block_result(
            slot=700, result=result,
            program_ids=PROGRAM_IDS)["status"] == rbs.BLOCK_SCAN_MALFORMED
        assert rbs.scan_block_payload(
            slot=700, payload=envelope_bytes(result),
            program_ids=PROGRAM_IDS)["status"] == rbs.BLOCK_SCAN_MALFORMED


class TestWorkerPurity:
    """A worker must not be ABLE to reach durable or delivery machinery."""

    def test_worker_scans_correctly_with_io_disabled(self, monkeypatch) -> None:
        import builtins
        import socket
        import urllib.request

        def _refuse(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("WORKER_PERFORMED_IO")

        monkeypatch.setattr(builtins, "open", _refuse)
        monkeypatch.setattr(socket, "socket", _refuse)
        monkeypatch.setattr(urllib.request, "urlopen", _refuse)
        scan = rbs.scan_block_task({
            "slot": 501, "payload": envelope_bytes(RELEVANT),
            "program_ids": PROGRAM_IDS})
        assert scan["status"] == rbs.BLOCK_SCAN_OK
        assert len(scan["entries"]) == 2

    def test_worker_cannot_mutate_cursor_or_recovery_state(
            self, monkeypatch, tmp_path) -> None:
        from PHX2.free_tier_producer import stream_cursor as sc

        for owner, name in ((sc.GrpcStreamCursorStore, "commit_event"),
                            (sc.GrpcStreamCursorStore, "mark_disconnect"),
                            (rgr.RpcGapRecoveryStore, "update"),
                            (rgr.RpcGapRecoveryStore, "persist"),
                            (rgr.QuarantinedLiveBuffer, "append")):
            monkeypatch.setattr(
                owner, name,
                lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("WORKER_TOUCHED_DURABLE_STATE")))
        assert rbs.scan_block_task({
            "slot": 501, "payload": envelope_bytes(RELEVANT),
            "program_ids": PROGRAM_IDS})["status"] == rbs.BLOCK_SCAN_OK

    def test_worker_cannot_mutate_census_or_tracker_state(
            self, monkeypatch) -> None:
        from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
        from PHX2.free_tier_producer.pumpswap_reserves import (
            PumpSwapReserveIndex,
        )

        def _refuse(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("WORKER_TOUCHED_CENSUS_OR_TRACKER")

        monkeypatch.setattr(PumpSwapReserveIndex, "record", _refuse)
        monkeypatch.setattr(PumpSwapReserveIndex, "register_pool", _refuse)
        monkeypatch.setattr(FeeEvidenceIndex, "record", _refuse)
        assert rbs.scan_block_task({
            "slot": 501, "payload": envelope_bytes(RELEVANT),
            "program_ids": PROGRAM_IDS})["status"] == rbs.BLOCK_SCAN_OK

    def test_worker_modules_reference_no_delivery_or_ledger_surface(
            self) -> None:
        """CODE, not prose: docstrings that DENY a capability are not uses."""

        import ast
        import inspect

        from PHX2.free_tier_producer import rpc_block_pool as pool_module

        banned = ("telegram", "discord", "webhook", "ping_dedupe", "ledger",
                  "urlopen", "sendmessage", "socket")
        for module in (rbs, pool_module):
            tree = ast.parse(inspect.getsource(module))
            names: List[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                elif isinstance(node, ast.Import):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                    names.extend(alias.name for alias in node.names)
            joined = "|".join(names).lower()
            for token in banned:
                assert token not in joined, (module.__name__, token)

    def test_worker_returns_malformed_instead_of_raising(self) -> None:
        for payload in (None, 12345, b"\xff\xfe not utf8"):
            scan = rbs.scan_block_task({
                "slot": 42, "payload": payload, "program_ids": PROGRAM_IDS})
            assert scan["status"] == rbs.BLOCK_SCAN_MALFORMED
            assert scan["entries"] == []

    def test_invalid_slot_never_produces_an_applicable_result(self) -> None:
        for slot in (None, -1, True, "500"):
            scan = rbs.scan_block_task({
                "slot": slot, "payload": envelope_bytes(RELEVANT),
                "program_ids": PROGRAM_IDS})
            assert scan["status"] == rbs.BLOCK_SCAN_MALFORMED


class TestResultValidation:
    def _ok(self) -> Dict[str, Any]:
        return rbs.scan_block_result(
            slot=501, result=RELEVANT, program_ids=PROGRAM_IDS)

    def test_valid_result_is_accepted(self) -> None:
        assert rbs.validate_scan_result(
            self._ok(), expected_slot=501) == (True, "SCAN_RESULT_OK")

    def test_wrong_slot_result_fails_closed(self) -> None:
        ok, token = rbs.validate_scan_result(self._ok(), expected_slot=999)
        assert not ok and token == "SCAN_RESULT_SLOT_MISMATCH"

    def test_foreign_schema_version_fails_closed(self) -> None:
        result = self._ok()
        result["scan_version"] = rbs.BLOCK_SCAN_VERSION + 1
        ok, token = rbs.validate_scan_result(result, expected_slot=501)
        assert not ok and token == "SCAN_RESULT_VERSION_MISMATCH"

    @pytest.mark.parametrize("mutate,token", [
        (lambda r: r.update(blockhash=""), "SCAN_RESULT_BLOCK_IDENTITY_INVALID"),
        (lambda r: r.update(previous_blockhash=None),
         "SCAN_RESULT_BLOCK_IDENTITY_INVALID"),
        (lambda r: r.update(parent_slot=501), "SCAN_RESULT_PARENT_SLOT_INVALID"),
        (lambda r: r.update(transaction_count=-1),
         "SCAN_RESULT_TRANSACTION_COUNT_INVALID"),
        (lambda r: r.update(status="WHATEVER"), "SCAN_RESULT_STATUS_INVALID"),
        (lambda r: r.update(prefilter="MAYBE"), "SCAN_RESULT_PREFILTER_INVALID"),
    ])
    def test_wrong_block_identity_or_shape_fails_closed(
            self, mutate: Any, token: str) -> None:
        result = self._ok()
        mutate(result)
        ok, detail = rbs.validate_scan_result(result, expected_slot=501)
        assert not ok and detail == token

    def test_out_of_order_or_duplicate_entries_fail_closed(self) -> None:
        result = self._ok()
        result["entries"] = list(reversed(result["entries"]))
        ok, token = rbs.validate_scan_result(result, expected_slot=501)
        assert not ok and token == "SCAN_RESULT_ENTRY_ORDER_INVALID"
        duplicated = self._ok()
        duplicated["entries"] = [duplicated["entries"][0],
                                 dict(duplicated["entries"][0])]
        ok, token = rbs.validate_scan_result(duplicated, expected_slot=501)
        assert not ok and token == "SCAN_RESULT_ENTRY_ORDER_INVALID"

    def test_entry_index_beyond_transaction_count_fails_closed(self) -> None:
        result = self._ok()
        result["transaction_count"] = 1
        ok, token = rbs.validate_scan_result(result, expected_slot=501)
        assert not ok and token == "SCAN_RESULT_ENTRY_INDEX_INVALID"

    def test_failed_status_may_not_carry_entries(self) -> None:
        result = self._ok()
        result["status"] = rbs.BLOCK_SCAN_UNAVAILABLE
        ok, token = rbs.validate_scan_result(result, expected_slot=501)
        assert not ok and token == "SCAN_RESULT_ENTRIES_ON_FAILURE"


class TestPoolBounds:
    @pytest.mark.parametrize("kwargs", [
        {"processes": 0}, {"processes": -1}, {"processes": True},
        {"processes": RPC_APPLY_PROCESSES_MAX + 1},
        {"queue_bound": 0}, {"queue_bound": 10_000},
        {"batch_size": 0}, {"batch_size": RPC_APPLY_BATCH_SIZE_MAX + 1},
        {"worker_timeout_seconds": 0}, {"worker_timeout_seconds": -1.0},
        {"worker_timeout_seconds": 10_000.0},
    ])
    def test_invalid_pool_settings_fail_closed(
            self, kwargs: Dict[str, Any]) -> None:
        base = dict(processes=2, queue_bound=4, batch_size=2,
                    worker_timeout_seconds=30.0, program_ids=PROGRAM_IDS)
        base.update(kwargs)
        with pytest.raises(BlockScanPoolError):
            BoundedBlockScanPool(**base)

    @pytest.mark.parametrize("kwargs,token", [
        ({"rpc_apply_processes": 0}, "RPC_APPLY_PROCESSES"),
        ({"rpc_apply_processes": RPC_APPLY_PROCESSES_MAX + 1},
         "RPC_APPLY_PROCESSES"),
        ({"rpc_apply_queue_bound": 0}, "RPC_APPLY_QUEUE_BOUND"),
        ({"rpc_apply_batch_size": 0}, "RPC_APPLY_BATCH_SIZE"),
        ({"rpc_worker_timeout_seconds": 0.0}, "RPC_WORKER_TIMEOUT_SECONDS"),
        ({"rpc_worker_timeout_seconds": 100_000.0},
         "RPC_WORKER_TIMEOUT_SECONDS"),
    ])
    def test_invalid_pool_configuration_is_refused_not_clamped(
            self, kwargs: Dict[str, Any], token: str) -> None:
        config = rgr.RpcGapRecoveryConfig(
            mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="confirmed", **kwargs)
        refusals = rgr.validate_rpc_gap_recovery_config(config)
        assert f"{rgr.CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:{token}" in refusals

    def test_default_worker_count_is_conservative(self) -> None:
        assert default_apply_processes(1) == 2
        assert default_apply_processes(4) == 2
        assert default_apply_processes(12) == 8
        assert default_apply_processes(64) == 8
        assert 2 <= default_apply_processes() <= 8

    def test_defaults_are_valid_and_serial_by_default(self) -> None:
        config = rgr.RpcGapRecoveryConfig(
            mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="confirmed")
        assert rgr.validate_rpc_gap_recovery_config(config) == []
        assert config.rpc_apply_processes == 1
        snapshot = config.snapshot()
        assert snapshot["rpc_apply_processes"] == 1
        assert snapshot["rpc_apply_queue_bound"] == 8


class TestWindowsSpawnPool:
    """The real pool, on the real spawn context, end to end."""

    def test_spawned_workers_return_results_matching_the_serial_scan(
            self) -> None:
        payloads = [(500 + index,
                     envelope_bytes(make_result(
                         500 + index,
                         [make_tx(f"S1gA{index}", relevant=True),
                          make_tx(f"S1gB{index}", relevant=False)])))
                    for index in range(6)]
        expected = {
            slot: rbs.scan_block_payload(
                slot=slot, payload=payload, program_ids=PROGRAM_IDS)
            for slot, payload in payloads}
        pool = BoundedBlockScanPool(
            processes=2, queue_bound=4, batch_size=2,
            worker_timeout_seconds=60.0, program_ids=PROGRAM_IDS)
        collected: Dict[int, Dict[str, Any]] = {}
        try:
            index = 0
            while len(collected) < len(payloads):
                if index < len(payloads) and pool.outstanding_batches < 4:
                    if pool.try_submit(payloads[index:index + 2]):
                        index += 2
                for result in pool.poll(timeout=1.0):
                    collected[int(result["slot"])] = result
        finally:
            pool.close()
        assert collected == expected
        assert pool.worker_failures == 0
        assert pool.restarts == 0

    def test_close_is_idempotent_and_deterministic(self) -> None:
        pool = BoundedBlockScanPool(
            processes=2, queue_bound=2, batch_size=1,
            worker_timeout_seconds=30.0, program_ids=PROGRAM_IDS)
        pool.close()
        pool.close()
        assert pool.outstanding_batches == 0
