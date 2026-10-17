"""Pure decode/scan of one confirmed-RPC block. No state, no I/O, no transport.

Why this module exists
----------------------
Confirmed-RPC recovery was measured applying ~1.600 produced blocks/second
against ~2.5 blocks/second of chain growth, with zero HTTP 429, zero RPC
errors and a request rate far below the provider ceiling: the deficit is CPU
work -- JSON decode of ~1,129-transaction blocks plus the per-transaction
program scan -- executed in the authoritative process under the GIL.

Everything in this module is deliberately PURE so it can be executed in a
worker process:

* it never opens a socket, a ledger, a checkpoint or a delivery transport;
* it never mutates census, tracker, cursor or recovery state;
* it returns plain picklable data, not live objects;
* the same functions are used by the serial reference path, so the parallel
  path cannot drift away from the semantics the serial path proves.

The authoritative parent keeps every decision that has durable consequences:
canonical slot ordering, duplicate suppression, checkpoint advancement,
cursor resolution and delivery eligibility.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: Bumped whenever the returned result schema changes in a way a parent from a
#: different build could misread. The parent refuses a foreign version.
BLOCK_SCAN_VERSION = 1

# -- result statuses (closed set) -------------------------------------------
BLOCK_SCAN_OK = "BLOCK_SCAN_OK"
BLOCK_SCAN_UNAVAILABLE = "BLOCK_SCAN_UNAVAILABLE"
BLOCK_SCAN_MALFORMED = "BLOCK_SCAN_MALFORMED"
BLOCK_SCAN_STATUSES = (
    BLOCK_SCAN_OK, BLOCK_SCAN_UNAVAILABLE, BLOCK_SCAN_MALFORMED)

# -- prefilter verdicts (closed set) ----------------------------------------
PREFILTER_DEFINITELY_IRRELEVANT = "DEFINITELY_IRRELEVANT"
PREFILTER_FULL_DECODE_REQUIRED = "FULL_DECODE_REQUIRED"

# -- per-transaction entry kinds (closed set) -------------------------------
#: Mentions a relevant program, canonically successful, projected: APPLY it.
ENTRY_APPLY = "APPLY"
#: Mentions a relevant program but the meta container is absent/failed.
ENTRY_REJECT_META = "REJECT_META"
#: Relevant, but no usable transaction signature.
ENTRY_REJECT_SIGNATURE = "REJECT_SIGNATURE"
#: Relevant, but the mechanical projection refused the transaction.
ENTRY_REJECT_PROJECTION = "REJECT_PROJECTION"
ENTRY_KINDS = (ENTRY_APPLY, ENTRY_REJECT_META, ENTRY_REJECT_SIGNATURE,
               ENTRY_REJECT_PROJECTION)

#: JSON-RPC codes proving the slot is skipped / not in ledger storage.
_RPC_SLOT_SKIPPED_CODES = (-32007, -32009)

_BASE58_RE = r"[1-9A-HJ-NP-Za-km-z]"
_RE_BLOCKHASH = re.compile(
    rb'(?<!previous)(?<!Previous)"blockhash":"(' + _BASE58_RE.encode() + rb'+)"')
_RE_PREVIOUS_BLOCKHASH = re.compile(
    rb'"previousBlockhash":"(' + _BASE58_RE.encode() + rb'+)"')
_RE_PARENT_SLOT = re.compile(rb'"parentSlot":(\d+)')

_TOKEN_TRANSACTIONS = b'"transactions":['
_TOKEN_SIGNATURES = b'"signatures":['
_TOKEN_META = b'"meta":{'
_TOKEN_ERROR = b'"error"'
_TOKEN_UNICODE_ESCAPE = b"\\u"


def _as_bytes(payload: object) -> Optional[bytes]:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    return None


def classify_block_payload(
    payload: object, program_ids: Sequence[str],
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Conservative raw-bytes relevance prefilter. NEVER a false negative.

    ``DEFINITELY_IRRELEVANT`` is returned only when ALL of the following hold,
    so that skipping the full decode cannot lose an event:

    1. no accepted program identifier occurs anywhere in the payload bytes.
       This is the soundness argument by itself: ``account_include``
       relevance is exactly "the identifier appears as an account key", which
       cannot be true unless those bytes are present somewhere in the block;
    2. the payload contains no ``\\u`` escape anywhere, so a base58 program
       identifier cannot be hiding from (1) in escaped form;
    3. the payload carries no ``"error"`` member, so it is a block response
       rather than a fault the parent must classify;
    4. the payload is the recognised compact ``getBlock``/``encoding=json``
       shape: exactly one ``"transactions":[`` member, a flat scalar-only
       header before it, and a flat scalar envelope tail after the array and
       its enclosing object close;
    5. every header field the authoritative parent needs (``blockhash``,
       ``previousBlockhash``, ``parentSlot``) is extractable from that header;
    6. the transaction count is corroborated by two independent per-
       transaction tokens that agree -- this, not the member ordering, is what
       makes the reported density trustworthy without a decode.

    Anything unknown, ambiguous, compressed, truncated or merely unexpected
    returns ``FULL_DECODE_REQUIRED``. There is no third answer.
    """

    raw = _as_bytes(payload)
    if raw is None or not raw:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    if not program_ids:
        # No accepted identifiers means relevance is undefined here, not
        # "nothing is relevant": refuse to skip.
        return PREFILTER_FULL_DECODE_REQUIRED, None
    if _TOKEN_ERROR in raw or _TOKEN_UNICODE_ESCAPE in raw:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    for program_id in program_ids:
        if not isinstance(program_id, str) or not program_id:
            return PREFILTER_FULL_DECODE_REQUIRED, None
        if program_id.encode("ascii", "ignore") in raw:
            return PREFILTER_FULL_DECODE_REQUIRED, None
    if raw.count(_TOKEN_TRANSACTIONS) != 1:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    closing = raw.rfind(b"]}")
    if closing < 0:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    tail = raw[closing + 2:].rstrip()
    # Everything after the last array-plus-object close must be a flat scalar
    # envelope tail (``,"id":1}``). A structured tail is an encoding this
    # filter does not claim to understand.
    if len(tail) > 64 or not tail.endswith(b"}") \
            or any(byte in tail for byte in (b"[", b"{", b"]", b"\\")):
        return PREFILTER_FULL_DECODE_REQUIRED, None
    head = raw[:raw.index(_TOKEN_TRANSACTIONS)]
    if head.count(b"[") or head.count(b"}") or head.count(b"{") != 2 \
            or b"\\" in head:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    blockhash = _RE_BLOCKHASH.search(head)
    previous_blockhash = _RE_PREVIOUS_BLOCKHASH.search(head)
    parent_slot = _RE_PARENT_SLOT.search(head)
    if blockhash is None or previous_blockhash is None or parent_slot is None:
        return PREFILTER_FULL_DECODE_REQUIRED, None
    signature_count = raw.count(_TOKEN_SIGNATURES)
    if signature_count != raw.count(_TOKEN_META):
        # Two independent per-transaction tokens disagree: the density this
        # filter would report is not trustworthy, so decode it properly.
        return PREFILTER_FULL_DECODE_REQUIRED, None
    header = {
        "blockhash": blockhash.group(1).decode("ascii"),
        "previous_blockhash": previous_blockhash.group(1).decode("ascii"),
        "parent_slot": int(parent_slot.group(1)),
        "transaction_count": int(signature_count),
    }
    return PREFILTER_DEFINITELY_IRRELEVANT, header


def _empty_result(*, slot: int, status: str, prefilter: str) -> Dict[str, Any]:
    return {
        "scan_version": BLOCK_SCAN_VERSION,
        "slot": int(slot),
        "status": str(status),
        "prefilter": str(prefilter),
        "blockhash": None,
        "previous_blockhash": None,
        "parent_slot": None,
        "block_time": None,
        "transaction_count": 0,
        "entries": [],
        "payload_bytes": 0,
    }


def scan_block_result(
    *, slot: int, result: Mapping[str, Any], program_ids: Sequence[str],
    payload_bytes: int = 0,
    prefilter: str = PREFILTER_FULL_DECODE_REQUIRED,
) -> Dict[str, Any]:
    """Scan one decoded ``getBlock`` result into a deterministic block result.

    Structural acceptance is IDENTICAL to ``SolanaRpcBackfillAdapter``'s: the
    same four header fields, the same types, the same ``parentSlot < slot``
    refusal.  The per-transaction walk is identical to the serial application
    loop, entry for entry, so the parent can reproduce its counters exactly.
    """

    from PHX2.free_tier_producer.rpc_gap_recovery import (
        build_subscribe_update_from_rpc_transaction,
        rpc_transaction_mentions_program,
    )

    if not isinstance(result, Mapping):
        return _empty_result(
            slot=slot, status=BLOCK_SCAN_MALFORMED, prefilter=prefilter)
    parent_slot = result.get("parentSlot")
    blockhash = result.get("blockhash")
    previous_blockhash = result.get("previousBlockhash")
    transactions = result.get("transactions")
    if (isinstance(parent_slot, bool) or not isinstance(parent_slot, int)
            or parent_slot < 0
            or not isinstance(blockhash, str) or not blockhash
            or not isinstance(previous_blockhash, str)
            or not previous_blockhash
            or not isinstance(transactions, list)):
        return _empty_result(
            slot=slot, status=BLOCK_SCAN_MALFORMED, prefilter=prefilter)
    if parent_slot >= int(slot):
        return _empty_result(
            slot=slot, status=BLOCK_SCAN_MALFORMED, prefilter=prefilter)

    block_time = result.get("blockTime")
    if isinstance(block_time, bool) or not isinstance(block_time, int):
        block_time = None
    entries: List[Dict[str, Any]] = []
    for tx_index, tx_json in enumerate(transactions):
        mentions = False
        for program_id in program_ids:
            if rpc_transaction_mentions_program(tx_json, program_id):
                mentions = True
                break
        if not mentions:
            continue
        meta_json = tx_json.get("meta") if isinstance(tx_json, Mapping) else None
        if not isinstance(meta_json, Mapping) \
                or meta_json.get("err") is not None:
            entries.append({"index": tx_index, "kind": ENTRY_REJECT_META,
                            "signature": None, "update": None})
            continue
        tx_body = tx_json.get("transaction")
        signatures = tx_body.get("signatures") if isinstance(
            tx_body, Mapping) else None
        signature = (signatures[0] if isinstance(signatures, list)
                     and signatures and isinstance(signatures[0], str)
                     else None)
        if signature is None:
            entries.append({"index": tx_index, "kind": ENTRY_REJECT_SIGNATURE,
                            "signature": None, "update": None})
            continue
        update = build_subscribe_update_from_rpc_transaction(
            slot=int(slot), block_time=block_time,
            transaction_index=tx_index, tx_json=tx_json)
        if update is None:
            entries.append({"index": tx_index, "kind": ENTRY_REJECT_PROJECTION,
                            "signature": signature, "update": None})
            continue
        entries.append({
            "index": tx_index, "kind": ENTRY_APPLY, "signature": signature,
            # Serialized so the result stays picklable and cheap to move
            # across a process boundary. The parent re-parses it into the very
            # same message type the live gRPC path hands to the decoders.
            "update": update.SerializeToString(),
        })
    return {
        "scan_version": BLOCK_SCAN_VERSION,
        "slot": int(slot),
        "status": BLOCK_SCAN_OK,
        "prefilter": str(prefilter),
        "blockhash": str(blockhash),
        "previous_blockhash": str(previous_blockhash),
        "parent_slot": int(parent_slot),
        "block_time": block_time,
        "transaction_count": len(transactions),
        "entries": entries,
        "payload_bytes": int(payload_bytes),
    }


def scan_block_payload(
    *, slot: int, payload: object, program_ids: Sequence[str],
) -> Dict[str, Any]:
    """Prefilter, decode and scan one UNDECODED JSON-RPC ``getBlock`` body."""

    raw = _as_bytes(payload)
    if raw is None:
        return _empty_result(slot=slot, status=BLOCK_SCAN_MALFORMED,
                             prefilter=PREFILTER_FULL_DECODE_REQUIRED)
    verdict, header = classify_block_payload(raw, program_ids)
    if verdict == PREFILTER_DEFINITELY_IRRELEVANT and header is not None:
        if int(header["parent_slot"]) >= int(slot):
            return _empty_result(slot=slot, status=BLOCK_SCAN_MALFORMED,
                                 prefilter=verdict)
        return {
            "scan_version": BLOCK_SCAN_VERSION,
            "slot": int(slot),
            "status": BLOCK_SCAN_OK,
            "prefilter": verdict,
            "blockhash": header["blockhash"],
            "previous_blockhash": header["previous_blockhash"],
            "parent_slot": int(header["parent_slot"]),
            "block_time": None,
            "transaction_count": int(header["transaction_count"]),
            "entries": [],
            "payload_bytes": len(raw),
        }
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _empty_result(slot=slot, status=BLOCK_SCAN_MALFORMED,
                             prefilter=verdict)
    if not isinstance(body, dict):
        return _empty_result(slot=slot, status=BLOCK_SCAN_MALFORMED,
                             prefilter=verdict)
    error = body.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        status = (BLOCK_SCAN_UNAVAILABLE if code in _RPC_SLOT_SKIPPED_CODES
                  else BLOCK_SCAN_MALFORMED)
        return _empty_result(slot=slot, status=status, prefilter=verdict)
    result = body.get("result")
    if result is None:
        return _empty_result(slot=slot, status=BLOCK_SCAN_UNAVAILABLE,
                             prefilter=verdict)
    if not isinstance(result, Mapping):
        return _empty_result(slot=slot, status=BLOCK_SCAN_MALFORMED,
                             prefilter=verdict)
    return scan_block_result(
        slot=slot, result=result, program_ids=program_ids,
        payload_bytes=len(raw), prefilter=verdict)


def validate_scan_result(
    result: object, *, expected_slot: int,
) -> Tuple[bool, str]:
    """Parent-side schema/identity acceptance for one worker result.

    A worker is untrusted structural input: nothing it returns is applied
    before this passes.
    """

    if not isinstance(result, Mapping):
        return False, "SCAN_RESULT_NOT_MAPPING"
    if result.get("scan_version") != BLOCK_SCAN_VERSION:
        return False, "SCAN_RESULT_VERSION_MISMATCH"
    slot = result.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int):
        return False, "SCAN_RESULT_SLOT_INVALID"
    if int(slot) != int(expected_slot):
        return False, "SCAN_RESULT_SLOT_MISMATCH"
    status = result.get("status")
    if status not in BLOCK_SCAN_STATUSES:
        return False, "SCAN_RESULT_STATUS_INVALID"
    if result.get("prefilter") not in (
            PREFILTER_DEFINITELY_IRRELEVANT, PREFILTER_FULL_DECODE_REQUIRED):
        return False, "SCAN_RESULT_PREFILTER_INVALID"
    entries = result.get("entries")
    if not isinstance(entries, list):
        return False, "SCAN_RESULT_ENTRIES_INVALID"
    if status != BLOCK_SCAN_OK:
        if entries:
            return False, "SCAN_RESULT_ENTRIES_ON_FAILURE"
        return True, "SCAN_RESULT_OK"
    count = result.get("transaction_count")
    parent_slot = result.get("parent_slot")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return False, "SCAN_RESULT_TRANSACTION_COUNT_INVALID"
    if isinstance(parent_slot, bool) or not isinstance(parent_slot, int) \
            or parent_slot < 0 or parent_slot >= int(slot):
        return False, "SCAN_RESULT_PARENT_SLOT_INVALID"
    for name in ("blockhash", "previous_blockhash"):
        value = result.get(name)
        if not isinstance(value, str) or not value:
            return False, "SCAN_RESULT_BLOCK_IDENTITY_INVALID"
    previous_index = -1
    for entry in entries:
        if not isinstance(entry, Mapping):
            return False, "SCAN_RESULT_ENTRY_NOT_MAPPING"
        index = entry.get("index")
        kind = entry.get("kind")
        if isinstance(index, bool) or not isinstance(index, int) \
                or index < 0 or index >= count:
            return False, "SCAN_RESULT_ENTRY_INDEX_INVALID"
        if index <= previous_index:
            return False, "SCAN_RESULT_ENTRY_ORDER_INVALID"
        previous_index = index
        if kind not in ENTRY_KINDS:
            return False, "SCAN_RESULT_ENTRY_KIND_INVALID"
        if kind == ENTRY_APPLY:
            if not isinstance(entry.get("signature"), str) \
                    or not entry.get("signature"):
                return False, "SCAN_RESULT_ENTRY_SIGNATURE_INVALID"
            if not isinstance(entry.get("update"), (bytes, bytearray)) \
                    or not entry.get("update"):
                return False, "SCAN_RESULT_ENTRY_UPDATE_INVALID"
    return True, "SCAN_RESULT_OK"


def parse_scan_entry_update(entry: Mapping[str, Any]) -> Optional[Any]:
    """Re-materialise one ``APPLY`` entry as the live-path message type."""

    from PHX2.proto.stage28_11._generated import geyser_pb2

    payload = entry.get("update")
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        return None
    update = geyser_pb2.SubscribeUpdate()
    try:
        update.ParseFromString(bytes(payload))
    except Exception:
        return None
    return update


def scan_block_task(task: Mapping[str, Any]) -> Dict[str, Any]:
    """Top-level, pickle-safe worker entrypoint. Windows-spawn compatible.

    Accepts and returns only plain data.  It holds no reference to any store,
    index, transport, ledger or delivery object, and cannot acquire one: the
    task carries bytes, a slot and immutable program identifiers.
    """

    slot = task.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        return _empty_result(slot=0, status=BLOCK_SCAN_MALFORMED,
                             prefilter=PREFILTER_FULL_DECODE_REQUIRED)
    program_ids = tuple(task.get("program_ids") or ())
    try:
        return scan_block_payload(
            slot=int(slot), payload=task.get("payload"),
            program_ids=program_ids)
    except Exception:
        # A worker NEVER decides an outcome by crashing: a structurally
        # unusable payload is reported as malformed and the parent applies its
        # own closed-set classification.
        return _empty_result(slot=int(slot), status=BLOCK_SCAN_MALFORMED,
                             prefilter=PREFILTER_FULL_DECODE_REQUIRED)


__all__ = (
    "BLOCK_SCAN_VERSION", "BLOCK_SCAN_OK", "BLOCK_SCAN_UNAVAILABLE",
    "BLOCK_SCAN_MALFORMED", "BLOCK_SCAN_STATUSES",
    "PREFILTER_DEFINITELY_IRRELEVANT", "PREFILTER_FULL_DECODE_REQUIRED",
    "ENTRY_APPLY", "ENTRY_REJECT_META", "ENTRY_REJECT_SIGNATURE",
    "ENTRY_REJECT_PROJECTION", "ENTRY_KINDS",
    "classify_block_payload", "scan_block_result", "scan_block_payload",
    "validate_scan_result", "parse_scan_entry_update", "scan_block_task",
)
