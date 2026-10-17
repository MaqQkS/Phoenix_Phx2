"""Create-pool-bound Yellowstone source for the paid PHX2 producer.

The server subscription is PumpSwap-program filtered. This client-side boundary
enforces the full migration-proof admission: the exact IDL-pinned
``create_pool`` Anchor discriminator must occur as an INNER instruction whose
CPI ancestry is the official pump.fun ``migrate`` frame, on a successful
transaction, with the canonical pool PDA, exact vault derivations/ownership,
coherent mint binding, an approved quote mint, and a quote-vault deposit at or
above the configured Decimal floor.  Ordinary Buy/Sell instructions, direct
signer-created pools, and migration-shaped dust pools all fail closed.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

import grpc

from PHX2.proto.stage28_11._generated import geyser_pb2, geyser_pb2_grpc
from PHX2.stage28.chainstack_yellowstone_event_source import (
    project_payload_to_normalized_event,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    Stage28_11DecodeError,
    decode_subscribe_update_to_payload,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    INSTRUCTION_KIND_PUMP_SWAP,
    Stage28_10ChainstackYellowstoneError,
    build_chainstack_yellowstone_payload,
)
from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT,
    PUMPSWAP_PROGRAM_ID,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    _build_metadata,
    _open_channel,
    build_pumpswap_subscribe_request,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    CREATE_POOL_ACCOUNT_INDEX_BASE_MINT,
    CREATE_POOL_ACCOUNT_INDEX_POOL,
    CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT,
    CREATE_POOL_MIN_ACCOUNT_COUNT,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveIndex,
    ingest_reserve_events_from_update,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    FeeEvidenceIndex,
    ingest_fee_events_from_update,
)
from PHX2.free_tier_producer.liquidity_integrity import (
    LiquidityIntegrityIndex,
    MigrationLiquidityIdentity,
)
from PHX2.free_tier_producer.migration_admission import (
    MigrationAdmissionConfig,
    MigrationAdmissionCounters,
    MigrationAdmissionDecision,
    MigrationProofStore,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer import stream_cursor as _cursor_mod
from PHX2.free_tier_producer.stream_cursor import (
    build_stream_event_identity,
    evaluate_replay_retention,
)


REFUSAL_NONE = "NONE"
REFUSAL_SUBSCRIBE_FAILED = "SUBSCRIBE_FAILED"
REFUSAL_STREAM_ERROR = "STREAM_ERROR"
REFUSAL_NO_CREATE_POOL = "NO_CREATE_POOL_RECEIVED"
REFUSAL_DECODE_FAILED = "DECODE_FAILED"
REFUSAL_CURSOR_HELD = "CURSOR_HELD_DOWNSTREAM_NOT_DURABLE"
REFUSAL_TRANSPORT_WATERMARK_COMMIT_FAILED = (
    "TRANSPORT_WATERMARK_COMMIT_FAILED")
REFUSAL_MIGRATION_CENSUS_COMMIT_FAILED = "MIGRATION_CENSUS_COMMIT_FAILED"

# Provider statuses that mean "the requested replay position is no longer
# available", as distinct from an ordinary transport failure. A too-old
# resume position must never be silently retried from the live head.
REPLAY_REJECTION_CODES = frozenset({"INVALID_ARGUMENT", "OUT_OF_RANGE", "NOT_FOUND"})

# Where an event's ORIGINAL time came from. A replayed migration must not
# appear newly migrated merely because it was decoded now, so the provider's
# own event stamp is preserved and the local receipt time is kept separate.
EVENT_TIME_SOURCE_PROVIDER_CREATED_AT = "PROVIDER_CREATED_AT"
EVENT_TIME_SOURCE_UNKNOWN = "UNKNOWN"
EVENT_TIME_SOURCES = (
    EVENT_TIME_SOURCE_PROVIDER_CREATED_AT, EVENT_TIME_SOURCE_UNKNOWN)

ITERATOR_END_NOT_STARTED = "NOT_STARTED"
ITERATOR_END_GRPC_ERROR = "GRPC_ERROR"
ITERATOR_END_LOCAL_ERROR = "LOCAL_ERROR"
ITERATOR_END_CLEAN_EOF = "CLEAN_EOF"
ITERATOR_END_MAX_EVENTS = "MAX_EVENTS_REACHED"
ITERATOR_END_CANCELLED = "CANCELLED"

_KNOWN_GRPC_CODES = frozenset({
    "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED",
    "NOT_FOUND", "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED",
    "FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED",
    "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED",
})

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _grpc_code(err: object) -> str:
    try:
        code = err.code()
        name = getattr(code, "name", None)
        return name if isinstance(name, str) and name in _KNOWN_GRPC_CODES else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _safe_exception_class(err: object) -> str:
    name = getattr(type(err), "__name__", "")
    if (isinstance(name, str) and 0 < len(name) <= 64
            and all(char.isalnum() or char == "_" for char in name)):
        return name
    return "UNSAFE_EXCEPTION_CLASS"


def _safe_grpc_detail(err: object, code: str) -> Tuple[str, str]:
    """Project unrestricted gRPC details onto fixed redaction-safe categories."""
    try:
        raw = err.details()
    except Exception:
        raw = ""
    detail = raw.lower() if isinstance(raw, str) else ""
    connection_terms = ("connection", "concurrent", "subscriber", "subscription", "stream")
    if code == "RESOURCE_EXHAUSTED":
        if ((("too many" in detail or "maximum" in detail or "max " in detail)
                and any(term in detail for term in connection_terms))
                or "connection limit" in detail or "subscription limit" in detail):
            return (
                "PROVIDER_CONCURRENT_STREAM_LIMIT",
                "Provider rejected the stream because its concurrent subscription limit was reached.",
            )
        if any(term in detail for term in ("rate limit", "quota", "requests per")):
            return (
                "PROVIDER_QUOTA_OR_RATE_LIMIT",
                "Provider reported a resource or request quota limit.",
            )
        return (
            "RESOURCE_EXHAUSTED_UNSPECIFIED",
            "Provider reported resource exhaustion without a safely classifiable detail.",
        )
    if code in ("UNAVAILABLE", "INTERNAL"):
        if "goaway" in detail:
            return "HTTP2_GOAWAY", "The HTTP/2 peer sent GOAWAY."
        if "too many pings" in detail or "keepalive" in detail:
            return "KEEPALIVE_POLICY_REJECTION", "The HTTP/2 peer rejected the keepalive policy."
        if "rst_stream" in detail or "stream reset" in detail:
            return "HTTP2_STREAM_RESET", "The HTTP/2 peer reset the stream."
        if any(term in detail for term in ("name resolution", "dns", "resolver")):
            return "NAME_RESOLUTION_FAILURE", "The transport reported name resolution failure."
        if "connection refused" in detail:
            return "CONNECTION_REFUSED", "The remote connection was refused."
        if (("tls" in detail or "ssl" in detail or "certificate" in detail)
                and "handshake" in detail):
            return "TLS_HANDSHAKE_FAILURE", "The TLS handshake failed."
        if ("failed to connect to all addresses" in detail
                or "connect failed" in detail or "failed to connect" in detail):
            return "NETWORK_CONNECT_FAILURE", "The transport could not establish a connection."
        if "timed out" in detail or "timeout" in detail:
            return "NETWORK_CONNECT_TIMEOUT", "The transport connection attempt timed out."
        if any(term in detail for term in (
                "connection reset", "transport is closing", "transport closed", "socket closed")):
            return "HTTP2_TRANSPORT_CLOSED", "The HTTP/2 transport closed unexpectedly."
        return f"GRPC_{code}", f"The provider returned gRPC status {code}."
    if code == "CANCELLED":
        return "RPC_CANCELLED", "The streaming RPC was cancelled."
    if code == "DEADLINE_EXCEEDED":
        return "RPC_DEADLINE_EXCEEDED", "The streaming RPC deadline was exceeded."
    if code in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
        return "AUTHENTICATION_OR_PERMISSION_FAILURE", "The provider rejected authentication or permission."
    return f"GRPC_{code}", f"The provider returned gRPC status {code}."


def _base58_encode(raw: object) -> str:
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return ""
    data = bytes(raw)
    zeros = 0
    for value in data:
        if value != 0:
            break
        zeros += 1
    number = int.from_bytes(data, "big")
    chars = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[rem])
    return "1" * zeros + "".join(reversed(chars))


def _base58_decode(text: object) -> Optional[bytes]:
    if not isinstance(text, str) or not text:
        return None
    number = 0
    for char in text:
        digit = _BASE58_ALPHABET.find(char)
        if digit < 0:
            return None
        number = number * 58 + digit
    zeros = len(text) - len(text.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * zeros + body


def _resolve_key(keys: list[bytes], index: int) -> Optional[str]:
    if isinstance(index, bool) or not isinstance(index, int) or not (0 <= index < len(keys)):
        return None
    value = _base58_encode(keys[index])
    return value or None


def extract_create_pool_quartet(update: object) -> Optional[Tuple[str, str, str]]:
    """Return exactly one discriminator-bound ``(pool, base, quote)`` quartet."""
    try:
        wrapper = update.transaction
        tx_info = wrapper.transaction
        transaction = tx_info.transaction
        message = transaction.message
        meta = tx_info.meta
    except Exception:
        return None
    logs = list(getattr(meta, "log_messages", ()) or ())
    if PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG not in logs:
        return None
    keys = [bytes(value) for value in list(getattr(message, "account_keys", ()) or ())]
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_writable_addresses", ()) or ()))
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_readonly_addresses", ()) or ()))
    instructions = list(getattr(message, "instructions", ()) or ())
    for group in list(getattr(meta, "inner_instructions", ()) or ()):
        instructions.extend(list(getattr(group, "instructions", ()) or ()))
    discriminator = bytes(PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR)
    matches = set()
    known_quotes = set(KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
    for instruction in instructions:
        try:
            program = _resolve_key(keys, int(instruction.program_id_index))
            data = bytes(instruction.data)
            accounts = list(bytes(instruction.accounts))
        except Exception:
            continue
        if program != PUMPSWAP_PROGRAM_ID or not data.startswith(discriminator):
            continue
        if len(accounts) < CREATE_POOL_MIN_ACCOUNT_COUNT:
            continue
        try:
            pool = _resolve_key(keys, accounts[CREATE_POOL_ACCOUNT_INDEX_POOL])
            mint_a = _resolve_key(keys, accounts[CREATE_POOL_ACCOUNT_INDEX_BASE_MINT])
            mint_b = _resolve_key(keys, accounts[CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT])
        except (IndexError, TypeError):
            continue
        if not pool or not mint_a or not mint_b or len({pool, mint_a, mint_b}) != 3:
            continue
        quote_a = mint_a in known_quotes
        quote_b = mint_b in known_quotes
        if quote_a == quote_b:
            continue
        base, quote = (mint_b, mint_a) if quote_a else (mint_a, mint_b)
        matches.add((pool, base, quote))
    return next(iter(matches)) if len(matches) == 1 else None


def _admission_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_provider_event_time(update: object) -> Tuple[Optional[str], str]:
    """Return ``(provider_event_time_utc, source_token)`` for one update.

    ``SubscribeUpdate.created_at`` (field 11, ``google.protobuf.Timestamp``) is
    the provider's own stamp for the event and is the only original-time signal
    this transaction-filtered subscription carries -- the transaction variant
    exposes no block time, and no ``blocks_meta`` subscription is opened.

    Returns ``(None, UNKNOWN)`` when the stamp is absent or unusable.  It never
    substitutes the current wall clock: a fabricated age is worse than an
    admitted absence, because downstream age-sensitive authorization can fail
    closed on an absence but cannot detect a plausible lie.
    """

    try:
        if not update.HasField("created_at"):
            return None, EVENT_TIME_SOURCE_UNKNOWN
        stamp = update.created_at
        seconds = int(stamp.seconds)
        nanos = int(stamp.nanos)
    except Exception:
        return None, EVENT_TIME_SOURCE_UNKNOWN
    if seconds <= 0 or not (0 <= nanos < 1_000_000_000):
        return None, EVENT_TIME_SOURCE_UNKNOWN
    try:
        moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None, EVENT_TIME_SOURCE_UNKNOWN
    return (moment.isoformat().replace("+00:00", "Z"),
            EVENT_TIME_SOURCE_PROVIDER_CREATED_AT)


def query_replay_first_available(stub: object) -> Optional[int]:
    """Ask the provider for the oldest slot it can still replay.

    Uses the generated ``Geyser.SubscribeReplayInfo`` unary RPC, which already
    exists in the pinned stub.  No new endpoint, no second subscription and no
    fabricated field: ``SubscribeReplayInfoRequest`` is empty and the response
    carries exactly one ``first_available`` value.

    Returns ``None`` when the RPC is unsupported, fails, or answers with
    something unusable -- which the caller must treat as *unproven coverage*,
    never as proof of availability.
    """

    call = getattr(stub, "SubscribeReplayInfo", None)
    if not callable(call):
        return None
    try:
        response = call(geyser_pb2.SubscribeReplayInfoRequest())
        if not response.HasField("first_available"):
            return None
        value = int(response.first_available)
    except Exception:
        return None
    return value if value >= 0 else None


def extract_stream_position(update: object) -> Optional[Tuple[int, str, Optional[int]]]:
    """Return ``(slot, signature_base58, transaction_index)`` for one update.

    This is the pre-decode identity of a transaction-variant ``SubscribeUpdate``
    and therefore the replay-skip key: it is computable before any admission,
    reserve or fee side effect runs, so a replayed update can be recognised and
    skipped without repeating work that was already made durable.

    Returns ``None`` when the provider shape is not a usable transaction
    update; such a message can never advance the cursor.
    """

    try:
        wrapper = update.transaction
        slot_raw = wrapper.slot
        signature_raw = wrapper.transaction.signature
    except Exception:
        return None
    if isinstance(slot_raw, bool) or not isinstance(slot_raw, int) or slot_raw < 0:
        return None
    signature = _base58_encode(bytes(signature_raw)) if signature_raw else ""
    if not signature:
        return None
    index_raw = getattr(wrapper.transaction, "index", None)
    if isinstance(index_raw, bool) or not isinstance(index_raw, int) or index_raw < 0:
        index = None
    else:
        index = index_raw
    return int(slot_raw), signature, index


def build_transaction_skip_identity(
    slot: int, signature: str, transaction_index: Optional[int]
) -> str:
    """The deterministic transaction-scoped replay-skip key."""

    return build_stream_event_identity(
        slot=slot, signature=signature, transaction_index=transaction_index)


def build_admitted_event_identity(
    decision: object, *, slot: int, signature: str,
    transaction_index: Optional[int] = None,
) -> str:
    """The finer instruction-site identity of one admitted migration.

    Carries the outer / inner / flattened instruction indices and the pinned
    migration version, so two create-pool sites in one transaction and one
    slot remain individually distinguishable.
    """

    proof = getattr(decision, "proof", None)
    return build_stream_event_identity(
        slot=slot,
        signature=signature,
        transaction_index=transaction_index,
        outer_instruction_index=getattr(proof, "outer_instruction_index", None),
        inner_instruction_index=getattr(proof, "inner_instruction_index", None),
        flattened_instruction_index=getattr(
            proof, "flattened_instruction_index", None),
        migration_version=getattr(decision, "migration_version", None),
        mint=getattr(decision, "candidate_mint", None),
        pool=getattr(decision, "pool", None),
    )


def decode_create_pool_update(
    update: object,
    *,
    provider_name: str,
    admission_config: Optional[MigrationAdmissionConfig] = None,
    admission_observer: Optional[Callable[[MigrationAdmissionDecision], None]] = None,
) -> Optional[Any]:
    """Admit ONLY proven pump.fun bonding-curve migrations.

    The full admission proof (pump.fun migrate CPI ancestry, tx success,
    canonical PDA, vault derivations/ownership, mint binding, approved quote,
    Decimal deposit floor) runs first; the observer receives every admitted or
    rejected decision for counters and redaction-safe diagnostics.  An
    unexpected admission exception fails CLOSED (no candidate)."""
    try:
        decision = evaluate_migration_admission(
            update, config=admission_config, observed_at_utc=_admission_now_iso())
    except Exception:
        return None
    if decision is None:
        return None
    if admission_observer is not None:
        try:
            admission_observer(decision)
        except Exception:
            pass
    if not decision.admitted or decision.proof is None:
        return None
    quartet = extract_create_pool_quartet(update)
    if quartet is None:
        return None
    pool, base, quote = quartet
    if (pool, base, quote) != (decision.pool, decision.candidate_mint, decision.quote_mint):
        # The admission proof and the legacy extractor must bind the exact
        # same pool/base/quote or the event is not representable.
        return None
    try:
        baseline = decode_subscribe_update_to_payload(update, provider_name=provider_name)
        payload = build_chainstack_yellowstone_payload(
            provider_event_id=baseline.provider_event_id,
            provider_name=baseline.provider_name,
            source_kind=baseline.source_kind,
            mint=base,
            event_type=baseline.event_type,
            observed_at_utc=baseline.observed_at_utc,
            slot=baseline.slot,
            signature=baseline.signature,
            instruction_kind=INSTRUCTION_KIND_PUMP_SWAP,
            # The sealed proof itself (including its digest) travels via the
            # proof store keyed by mint; only the closed-set marker is safe
            # for the Stage 28 payload's strict decoded_fields validator.
            decoded_fields={**dict(baseline.decoded_fields),
                            "migration_proof": "PUMPFUN_MIGRATE_CPI_CANONICAL_POOL"},
            chain=baseline.chain,
            quote_mint=quote,
            pool_account=pool,
            pool_program_id=PUMPSWAP_PROGRAM_ID,
            base_mint=base,
            bonding_curve_version_hint=None,
            provider_quote_asset_hint=(
                KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT.get(quote)),
            provider_pair_type_hint=(
                KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT.get(quote)),
            provider_bonding_curve_version_hint=None,
        )
        return project_payload_to_normalized_event(payload)
    except (Stage28_11DecodeError, Stage28_10ChainstackYellowstoneError):
        return None


class PaidCreatePoolYellowstoneSource:
    """Iterator over one PumpSwap-filtered subscription.

    Tests and independent probes may retain a finite message bound.  The paid
    production owner passes ``None`` so an otherwise healthy subscription is
    not discarded merely because ``create_pool`` is rarer than ordinary
    PumpSwap traffic.  ``close`` cancels the active response iterator so the
    owner can still stop promptly without waiting for another migration.
    """

    def __init__(self, *, runtime_config: Stage28_11ChainstackYellowstoneGrpcRuntimeConfig,
                  max_messages_to_scan: Optional[int] = 64,
                  channel_factory: Any = None,
                  reserve_index: Optional[PumpSwapReserveIndex] = None,
                  fee_index: Optional[FeeEvidenceIndex] = None,
                  liquidity_index: Optional[LiquidityIntegrityIndex] = None,
                  admission_config: Optional[MigrationAdmissionConfig] = None,
                  admission_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
                  proof_store: Optional[MigrationProofStore] = None,
                  from_slot: Optional[int] = None,
                  cursor: Any = None,
                  downstream_durable_fn: Optional[Callable[[], bool]] = None,
                  stream_generation: int = 0,
                  recovery_generation: Optional[int] = None,
                  transaction_observer: Optional[
                      Callable[[int, str, Optional[int], str], None]] = None,
                  transport_slot_observer: Optional[
                      Callable[[int, str], bool]] = None,
                  census_sink: Optional[Callable[[Any], bool]] = None,
                  ) -> None:
        self._runtime_config = runtime_config
        self._max_messages = (None if max_messages_to_scan is None
                              else max(1, int(max_messages_to_scan)))
        self._channel_factory = channel_factory
        self._reserve_index = reserve_index
        self._fee_index = fee_index
        self._liquidity_index = liquidity_index
        self._admission_config = admission_config
        self._admission_sink = admission_sink
        self._proof_store = proof_store
        self.admission_commit_failed = False
        # PHX2-E2E-008: the resume position this subscription must replay
        # from. ``None`` means "start at the provider's live head", which is
        # correct ONLY for a genuinely new subscription.
        if from_slot is not None and (
                isinstance(from_slot, bool) or not isinstance(from_slot, int)
                or from_slot < 0):
            raise ValueError("from_slot must be a non-negative int or None")
        self._from_slot = from_slot
        self._cursor = cursor
        self._downstream_durable_fn = downstream_durable_fn
        # Recovery-quarantine tap: sees every transaction-shaped update's
        # pre-decode identity. Never affects stream health; exceptions are
        # swallowed. ``None`` (the default and every certified caller) keeps
        # behaviour byte-identical.
        self._transaction_observer = transaction_observer
        self._transport_slot_observer = transport_slot_observer
        self._census_sink = census_sink
        self.admission_counters = MigrationAdmissionCounters()
        self._close_event = threading.Event()
        self._response_lock = threading.Lock()
        self._response_iter: Any = None
        self.last_refusal_reason = REFUSAL_NONE
        self.events_scanned = 0
        self.transactions_scanned = 0
        self.create_pool_yielded = 0
        self.reserve_events_decoded = 0
        self.fee_events_decoded = 0
        self.last_update_epoch: Optional[float] = None
        self.first_update_epoch: Optional[float] = None
        self.last_decoded_event_epoch: Optional[float] = None
        self.stream_started_epoch: Optional[float] = None
        self.stream_ended_epoch: Optional[float] = None
        self.stream_phase = "NOT_STARTED"
        self.iterator_end_kind = ITERATOR_END_NOT_STARTED
        self.error_class: Optional[str] = None
        self.grpc_status_code: Optional[str] = None
        self.sanitized_error_category: Optional[str] = None
        self.sanitized_details: Optional[str] = None
        self.cancellation_requested = False
        # --- reconnect-recovery observability (all redaction-safe) ---
        self.stream_generation = int(stream_generation)
        self.replay_requested = from_slot is not None
        self.replay_from_slot = from_slot
        self.replay_position_rejected = False
        # Provider retention floor, when the replay-info RPC answered.
        self.replay_first_available: Optional[int] = None
        self.replay_retention_reason: str = _cursor_mod.REASON_NONE
        self.replayed_events = 0
        self.replay_duplicates_suppressed = 0
        self.cursor_commits = 0
        self.cursor_commit_failures = 0
        self.cursor_holds = 0
        self.first_slot_observed: Optional[int] = None
        self.last_slot_observed: Optional[int] = None
        self.highest_slot_observed: Optional[int] = None
        self.overlap_observed = False
        # The exact position this attempt asked to be proven, and the slot that
        # actually proved it. Kept distinct so an overlap can be checked
        # against the boundary it claims to prove rather than against itself.
        self.expected_overlap_slot = from_slot
        self.overlap_proof_slot: Optional[int] = None
        self.overlap_proof_accepted = False
        # The recovery episode this attempt belongs to. A proof recorded under
        # a superseded generation is refused by the cursor.
        if recovery_generation is None:
            recovery_generation = self._read_cursor_recovery_generation()
        self.recovery_generation = int(recovery_generation or 0)
        # Per-event provider time side-channel. The normalized event is a
        # frozen dataclass, so the owner reads these immediately after the
        # yield returns -- synchronously, on the one owned stream.
        self.last_event_provider_time_utc: Optional[str] = None
        self.last_event_time_source: str = EVENT_TIME_SOURCE_UNKNOWN
        self.last_event_replayed = False
        # Per-event transaction slot side-channel. The frozen normalized event
        # carries no slot field, and the live-epoch admission gate fails
        # CLOSED on a missing slot -- which silently rejected EVERY live
        # migration from the candidate path (EPOCH_EVENT_PRE_ARM_REJECTED
        # with migration_slot null, 38/38 on 2026-07-27) while census/proof
        # consumers read the slot from the raw update directly.
        self.last_event_slot: Optional[int] = None
        # Same-connection confirmed slots form a transport/head watermark.
        # They are never transaction event positions and never mutate cursor.
        self.confirmed_slot_updates = 0
        self.first_confirmed_slot: Optional[int] = None
        self.latest_confirmed_slot: Optional[int] = None
        self.migration_census_reserve_failure_reason: Optional[str] = None

    def _read_cursor_recovery_generation(self) -> int:
        if self._cursor is None:
            return 0
        try:
            return int(self._cursor.state.recovery_generation)
        except Exception:
            return 0

    def _record_overlap_proof(self, slot: int) -> None:
        """Bind positive replay proof to the episode boundary it must prove.

        Called only once the boundary event's identity processing is complete,
        so ``mark_overlap_proven`` cannot close an episode on an event that has
        not yet been deduped.

        The proof is refused by the cursor unless the requested position IS the
        pinned episode boundary.  That is what stops the pre-repair loop in
        which overlap proved only that the provider honoured whatever position
        the cursor happened to hold -- never that the position still owed
        coverage.
        """

        self.overlap_observed = True
        if self.overlap_proof_slot is None:
            self.overlap_proof_slot = slot
        if self._cursor is None or self.overlap_proof_accepted:
            return
        prove = getattr(self._cursor, "mark_overlap_proven", None)
        if not callable(prove):
            return
        try:
            self.overlap_proof_accepted = bool(prove(
                requested_from_slot=self._from_slot,
                proven_boundary_slot=slot,
                recovery_generation=self.recovery_generation))
        except Exception:
            self.overlap_proof_accepted = False

    def close(self) -> None:
        """Cancel the sole active subscription without exposing its config."""
        self.cancellation_requested = True
        self._close_event.set()
        with self._response_lock:
            response_iter = self._response_iter
        if response_iter is not None:
            try:
                response_iter.cancel()
            except Exception:
                pass

    def diagnostic_snapshot(self) -> Dict[str, Any]:
        """Return only closed-set/fixed-text diagnostics; never raw exception text."""
        return {
            "error_class": self.error_class,
            "grpc_status_code": self.grpc_status_code,
            "sanitized_error_category": self.sanitized_error_category,
            "sanitized_details": self.sanitized_details,
            "stream_phase": self.stream_phase,
            "iterator_end_kind": self.iterator_end_kind,
            "cancellation_requested": bool(self.cancellation_requested),
        }

    def recovery_snapshot(self) -> Dict[str, Any]:
        """Replay/coverage evidence for one subscription attempt.

        Kept separate from ``diagnostic_snapshot`` so the existing diagnostic
        contract (and its exact-equality tests) stays byte-identical.
        """

        return {
            "stream_generation": int(self.stream_generation),
            "replay_requested": bool(self.replay_requested),
            "replay_from_slot": self.replay_from_slot,
            "replay_position_rejected": bool(self.replay_position_rejected),
            "replayed_events": int(self.replayed_events),
            "replay_duplicates_suppressed": int(self.replay_duplicates_suppressed),
            "overlap_observed": bool(self.overlap_observed),
            "overlap_expected_slot": self.expected_overlap_slot,
            "overlap_proof_slot": self.overlap_proof_slot,
            "overlap_proof_accepted": bool(self.overlap_proof_accepted),
            "recovery_generation": int(self.recovery_generation),
            "replay_first_available": self.replay_first_available,
            "replay_retention_reason": self.replay_retention_reason,
            "first_slot_observed": self.first_slot_observed,
            "last_slot_observed": self.last_slot_observed,
            "highest_slot_observed": self.highest_slot_observed,
            "cursor_commits": int(self.cursor_commits),
            "cursor_commit_failures": int(self.cursor_commit_failures),
            "cursor_holds": int(self.cursor_holds),
            "confirmed_slot_updates": int(self.confirmed_slot_updates),
            "first_confirmed_slot": self.first_confirmed_slot,
            "latest_confirmed_slot": self.latest_confirmed_slot,
            "migration_census_reserve_failure_reason": (
                self.migration_census_reserve_failure_reason
            ),
        }

    def _record_grpc_error(self, err: object, *, phase: str) -> None:
        code = _grpc_code(err)
        category, detail = _safe_grpc_detail(err, code)
        self.stream_phase = phase
        self.iterator_end_kind = ITERATOR_END_GRPC_ERROR
        self.error_class = _safe_exception_class(err)
        self.grpc_status_code = code
        self.sanitized_error_category = category
        self.sanitized_details = detail
        if self.replay_requested and code in REPLAY_REJECTION_CODES:
            # The provider refused the requested resume position (retention
            # exceeded or otherwise unavailable). This must never degrade into
            # a silent restart at the live head.
            self.replay_position_rejected = True

    def _downstream_handoff_is_durable(self) -> bool:
        """Did the owner make this candidate's handoff durable?

        Defaults to ``True`` when no owner predicate is supplied so probes and
        independent iteration keep their existing behaviour; the production
        owner supplies a real predicate bound to its handoff artifact.
        """

        if self._downstream_durable_fn is None:
            return True
        try:
            return bool(self._downstream_durable_fn())
        except Exception:
            # An unreadable durability signal must not be optimistic.
            return False

    def _commit_cursor(self, *, slot: int, identity: str,
                       signature: Optional[str], replayed: bool,
                       detail_identity: Optional[str] = None) -> None:
        """Advance the durable position for one authoritatively handled event.

        A persistence failure never advances the position and never reports
        health: the event replays on the next connection and exact-identity
        dedupe absorbs whatever was already durable downstream.
        """

        if self._cursor is None:
            return
        try:
            self._cursor.commit_event(
                slot=slot, identity=identity, signature=signature,
                replayed=replayed, detail_identity=detail_identity)
            self.cursor_commits += 1
        except Exception:
            self.cursor_commit_failures += 1

    def _record_local_error(self, err: object, *, phase: str) -> None:
        self.stream_phase = phase
        self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
        self.error_class = _safe_exception_class(err)
        self.grpc_status_code = None
        self.sanitized_error_category = "LOCAL_SOURCE_EXCEPTION"
        self.sanitized_details = "A local exception escaped the source phase; raw text was withheld."

    def iter_events(self, *, max_events: int) -> Iterator[Any]:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events <= 0:
            self.last_refusal_reason = REFUSAL_DECODE_FAILED
            return
        cfg = self._runtime_config
        response_iter = None
        self.stream_phase = "CHANNEL_OPEN"
        try:
            with _open_channel(cfg, self._channel_factory) as channel:
                stub = geyser_pb2_grpc.GeyserStub(channel)
                self.stream_started_epoch = time.time()
                # ---- replay retention pre-check ---------------------------
                # Ask, before subscribing, whether the required boundary is
                # still inside the provider's replay window. Discovering this
                # reactively instead produced a tight reconnect loop against a
                # position that could never be served.
                if self._from_slot is not None:
                    self.stream_phase = "REPLAY_INFO"
                    self.replay_first_available = query_replay_first_available(stub)
                    verdict = evaluate_replay_retention(
                        safe_resume_slot=self._from_slot,
                        first_available_slot=self.replay_first_available)
                    self.replay_retention_reason = verdict.reason
                    if verdict.retention_exceeded:
                        # Terminal: never silently start at the live head and
                        # never delete the cursor. The owner stops here.
                        self.replay_position_rejected = True
                        self.stream_phase = "REPLAY_RETENTION_EXCEEDED"
                        self.iterator_end_kind = ITERATOR_END_GRPC_ERROR
                        self.sanitized_error_category = (
                            "REPLAY_RETENTION_EXCEEDED")
                        self.sanitized_details = (
                            "The requested resume position is older than the "
                            "provider's replay retention window.")
                        self.last_refusal_reason = (
                            f"{REFUSAL_STREAM_ERROR}:REPLAY_RETENTION_EXCEEDED")
                        return
                # Subscribe is a long-lived server stream.  The runtime timeout remains
                # available to connection readiness and unary Ping code, but is not a
                # total lifetime deadline on this RPC.
                self.stream_phase = "SUBSCRIBE_CALL"
                # PHX2-E2E-008: a reconnect carries the durable resume
                # position so the provider replays from the last proven-safe
                # slot instead of restarting at the current live head.
                response_iter = stub.Subscribe(
                    iter([build_pumpswap_subscribe_request(
                        from_slot=self._from_slot)]),
                    metadata=_build_metadata(cfg),
                )
                self.stream_phase = "ITERATE"
                with self._response_lock:
                    self._response_iter = response_iter
                yielded = 0
                scanned = 0
                while (not self._close_event.is_set()
                       and (self._max_messages is None or scanned < self._max_messages)):
                    try:
                        update = next(response_iter)
                    except StopIteration:
                        self.stream_phase = "ITERATOR_ENDED"
                        self.iterator_end_kind = ITERATOR_END_CLEAN_EOF
                        break
                    except grpc.RpcError as err:
                        if self._close_event.is_set():
                            self.stream_phase = "ITERATE"
                            self.iterator_end_kind = ITERATOR_END_CANCELLED
                            return
                        self._record_grpc_error(err, phase="ITERATE")
                        self.last_refusal_reason = f"{REFUSAL_STREAM_ERROR}:{_grpc_code(err)}"
                        return
                    scanned += 1
                    self.events_scanned += 1
                    self.last_update_epoch = time.time()
                    if self.first_update_epoch is None:
                        self.first_update_epoch = self.last_update_epoch
                    self.stream_phase = "DECODE"
                    if not isinstance(update, geyser_pb2.SubscribeUpdate):
                        self.stream_phase = "ITERATE"
                        continue
                    try:
                        if update.HasField("slot"):
                            confirmed_slot = int(update.slot.slot)
                            if int(update.slot.status) == int(geyser_pb2.SLOT_CONFIRMED):
                                persisted = self._transport_slot_observer is None
                                if self._transport_slot_observer is not None:
                                    try:
                                        persisted = bool(self._transport_slot_observer(
                                            confirmed_slot, _admission_now_iso()))
                                    except Exception:
                                        persisted = False
                                if not persisted:
                                    self.last_refusal_reason = (
                                        REFUSAL_TRANSPORT_WATERMARK_COMMIT_FAILED)
                                    self.stream_phase = "TRANSPORT_WATERMARK_COMMIT"
                                    self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
                                    return
                                self.confirmed_slot_updates += 1
                                if self.first_confirmed_slot is None:
                                    self.first_confirmed_slot = confirmed_slot
                                self.latest_confirmed_slot = max(
                                    confirmed_slot,
                                    self.latest_confirmed_slot
                                    if self.latest_confirmed_slot is not None
                                    else confirmed_slot)
                            self.stream_phase = "ITERATE"
                            continue
                        if not update.HasField("transaction"):
                            self.stream_phase = "ITERATE"
                            continue
                    except (TypeError, ValueError):
                        self.stream_phase = "ITERATE"
                        continue
                    self.transactions_scanned += 1
                    # ---- PHX2-E2E-008 replay boundary -------------------
                    # The pre-decode transaction identity is computed BEFORE
                    # any side effect, so a replayed update is recognised and
                    # skipped without repeating reserve/fee accumulation,
                    # admission, sealing or handoff.
                    position = extract_stream_position(update)
                    slot: Optional[int] = None
                    signature: Optional[str] = None
                    tx_index: Optional[int] = None
                    skip_identity: Optional[str] = None
                    is_replayed = False
                    proves_overlap = False
                    if position is not None:
                        slot, signature, tx_index = position
                        if self.first_slot_observed is None:
                            self.first_slot_observed = slot
                        self.last_slot_observed = slot
                        self.highest_slot_observed = (
                            slot if self.highest_slot_observed is None
                            else max(self.highest_slot_observed, slot))
                        if self._from_slot is not None and slot <= self._from_slot:
                            # Receiving the boundary slot back is positive
                            # proof the provider honoured the requested
                            # resume position. The proof is RECORDED below,
                            # after this event's identity processing, not here.
                            proves_overlap = True
                            is_replayed = True
                            self.replayed_events += 1
                        skip_identity = build_transaction_skip_identity(
                            slot, signature, tx_index)
                        if self._transaction_observer is not None:
                            try:
                                self._transaction_observer(
                                    slot, signature, tx_index, skip_identity)
                            except Exception:
                                # Observation is telemetry for the recovery
                                # coordinator; it must never affect the stream.
                                pass
                    # A position that cannot be extracted is still processed
                    # exactly as before; it simply cannot advance the durable
                    # position, so it will replay after a reconnect.
                    already_processed = False
                    if self._cursor is not None and skip_identity is not None:
                        try:
                            already_processed = bool(
                                self._cursor.is_duplicate(skip_identity))
                        except Exception:
                            already_processed = False
                    if proves_overlap and slot is not None:
                        # Identity resolution for the boundary event is now
                        # complete, so the proof may be bound to the episode.
                        self._record_overlap_proof(slot)
                    if already_processed:
                        # Exact duplicate replay: counted, never admitted,
                        # seeded, sealed, scheduled, composed or delivered
                        # a second time.
                        self.replay_duplicates_suppressed += 1
                        try:
                            self._cursor.record_duplicate_replay()
                        except Exception:
                            pass
                        self.stream_phase = "ITERATE"
                        continue
                    if self._reserve_index is not None:
                        # Reuse the sole transaction stream.  This opens no
                        # account subscription and performs no extra RPC.
                        self.reserve_events_decoded += ingest_reserve_events_from_update(
                            update, reserve_index=self._reserve_index)
                        consume_failure = getattr(
                            self._reserve_index,
                            "consume_required_observer_failure", None)
                        if callable(consume_failure) and consume_failure():
                            failure_reason = getattr(
                                self._reserve_index,
                                "last_required_observer_failure_reason",
                                lambda: None,
                            )()
                            self.migration_census_reserve_failure_reason = (
                                failure_reason
                            )
                            self.last_refusal_reason = (
                                REFUSAL_MIGRATION_CENSUS_COMMIT_FAILED)
                            self.stream_phase = "MIGRATION_CENSUS_RESERVE_COMMIT"
                            self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
                            return
                    if self._fee_index is not None:
                        # PHX1 Fee Gate accumulation reuses this primary stream.
                        # No third subscription and no verifier swap processing.
                        self.fee_events_decoded += ingest_fee_events_from_update(
                            update, fee_index=self._fee_index)
                    decision_holder: Dict[str, Any] = {}

                    def _observe_admission(decision: MigrationAdmissionDecision,
                                           _holder: Dict[str, Any] = decision_holder) -> None:
                        _holder["decision"] = decision
                        self.admission_counters.record(decision)
                        if not decision.admitted and self._admission_sink is not None:
                            try:
                                self._admission_sink(decision.diagnostic_record())
                            except Exception:
                                # Diagnostics must never affect stream health.
                                pass

                    event = decode_create_pool_update(
                        update, provider_name=cfg.safe_config.provider_id,
                        admission_config=self._admission_config,
                        admission_observer=_observe_admission)
                    if event is None:
                        # Deterministic rejection: the update travelled the
                        # complete admission boundary and produced no
                        # candidate. There is no downstream state owing, so
                        # the position may advance immediately -- and must,
                        # or a rejection-only range would replay forever.
                        if slot is not None and skip_identity is not None:
                            self._commit_cursor(
                                slot=slot, identity=skip_identity,
                                signature=signature, replayed=is_replayed)
                        self.stream_phase = "ITERATE"
                        continue
                    admitted_decision = decision_holder.get("decision")
                    sealed_proof = getattr(admitted_decision, "proof", None)
                    if sealed_proof is not None:
                        # Census persistence is a required effect. If it cannot
                        # be made durable, hold the transaction cursor so replay
                        # can retry this exact migration.
                        if self._census_sink is not None:
                            try:
                                census_persisted = bool(
                                    self._census_sink(sealed_proof))
                            except Exception:
                                census_persisted = False
                            if not census_persisted:
                                self.admission_commit_failed = True
                                self.last_refusal_reason = (
                                    REFUSAL_MIGRATION_CENSUS_COMMIT_FAILED)
                                self.stream_phase = "MIGRATION_CENSUS_COMMIT"
                                self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
                                return
                        # Immutable, restart-safe migration proof: sealed once
                        # here, then cross-checked by every downstream consumer.
                        if self._proof_store is not None:
                            try:
                                self._proof_store.seal_and_store(sealed_proof)
                            except Exception:
                                self.admission_commit_failed = True
                                self.last_refusal_reason = "MIGRATION_PROOF_COMMIT_FAILED"
                                self.stream_phase = "MIGRATION_PROOF_COMMIT"
                                self.iterator_end_kind = ITERATOR_END_LOCAL_ERROR
                                return
                        if self._liquidity_index is not None:
                            try:
                                self._liquidity_index.register_migration_proof(sealed_proof)
                            except Exception:
                                pass
                    self.last_decoded_event_epoch = time.time()
                    if self._reserve_index is not None:
                        self._reserve_index.register_pool(
                            pool_address=getattr(event, "pool_account", None),
                            base_mint=getattr(event, "base_mint", None),
                            quote_mint=getattr(event, "quote_mint", None),
                            creation_timestamp=getattr(event, "observed_at_utc", None),
                        )
                    if self._liquidity_index is not None:
                        try:
                            self._liquidity_index.register_migration(
                                MigrationLiquidityIdentity(
                                    candidate_mint=str(getattr(event, "base_mint")),
                                    pool=str(getattr(event, "pool_account")),
                                    quote_mint=str(getattr(event, "quote_mint")),
                                    migration_signature=_base58_encode(bytes(
                                        update.transaction.transaction.signature)),
                                    migration_slot=int(update.transaction.slot),
                                    migration_timestamp_utc=str(
                                        getattr(event, "observed_at_utc")),
                                    provider_pool=str(getattr(event, "pool_account")),
                                ))
                        except Exception:
                            # Identity failure never fabricates a canonical pool;
                            # the verifier will remain UNKNOWN and block delivery.
                            pass
                    yielded += 1
                    self.create_pool_yielded += 1
                    self.last_refusal_reason = REFUSAL_NONE
                    # Publish this event's ORIGINAL provider time before the
                    # yield. The normalized event is a frozen dataclass, so the
                    # owner reads these synchronously on the one owned stream
                    # while handling exactly this event.
                    (self.last_event_provider_time_utc,
                     self.last_event_time_source) = extract_provider_event_time(
                        update)
                    self.last_event_replayed = is_replayed
                    self.last_event_slot = (
                        int(slot) if isinstance(slot, int)
                        and not isinstance(slot, bool) else None)
                    # Synchronous side-channel, exactly like slot/time: the
                    # owner carries this SAME transaction's proof into durable
                    # candidates rather than trusting a suffix/provenance label.
                    self.last_event_migration_proof = sealed_proof
                    self.last_event_signature = signature
                    yield event
                    # Control only returns here once the owner has finished
                    # handling this candidate, so the cursor advances AFTER
                    # the authoritative downstream handoff -- never before.
                    # The reverse ordering (cursor committed, handoff lost) is
                    # therefore impossible by construction.
                    if slot is None or skip_identity is None:
                        # No extractable position: nothing to commit.
                        pass
                    elif self._downstream_handoff_is_durable():
                        self._commit_cursor(
                            slot=slot, identity=skip_identity,
                            signature=signature, replayed=is_replayed,
                            detail_identity=build_admitted_event_identity(
                                admitted_decision, slot=slot,
                                signature=signature,
                                transaction_index=tx_index))
                    else:
                        # The handoff was not made durable: hold the position
                        # so a reconnect or restart replays this exact event.
                        # Anything already durable is suppressed by identity.
                        self.cursor_holds += 1
                        self.last_refusal_reason = REFUSAL_CURSOR_HELD
                    if yielded >= max_events:
                        self.stream_phase = "ITERATOR_ENDED"
                        self.iterator_end_kind = ITERATOR_END_MAX_EVENTS
                        return
                    self.stream_phase = "ITERATE"
                if self._close_event.is_set() and self.iterator_end_kind == ITERATOR_END_NOT_STARTED:
                    self.stream_phase = "ITERATE"
                    self.iterator_end_kind = ITERATOR_END_CANCELLED
                if yielded == 0 and not self._close_event.is_set():
                    self.last_refusal_reason = REFUSAL_NO_CREATE_POOL
        except grpc.RpcError as err:
            if self._close_event.is_set():
                self.iterator_end_kind = ITERATOR_END_CANCELLED
                return
            self._record_grpc_error(err, phase=self.stream_phase)
            self.last_refusal_reason = f"{REFUSAL_SUBSCRIBE_FAILED}:{_grpc_code(err)}"
        except Exception as err:
            if self._close_event.is_set():
                self.iterator_end_kind = ITERATOR_END_CANCELLED
                return
            self._record_local_error(err, phase=self.stream_phase)
            self.last_refusal_reason = REFUSAL_SUBSCRIBE_FAILED
        finally:
            self.stream_ended_epoch = time.time()
            with self._response_lock:
                if self._response_iter is response_iter:
                    self._response_iter = None
            if response_iter is not None:
                try:
                    response_iter.cancel()
                except Exception:
                    pass


__all__ = (
    "PaidCreatePoolYellowstoneSource",
    "decode_create_pool_update",
    "extract_create_pool_quartet",
    "extract_stream_position",
    "build_transaction_skip_identity",
    "build_admitted_event_identity",
    "extract_provider_event_time",
    "query_replay_first_available",
    "EVENT_TIME_SOURCE_PROVIDER_CREATED_AT",
    "EVENT_TIME_SOURCE_UNKNOWN",
    "EVENT_TIME_SOURCES",
    "REPLAY_REJECTION_CODES",
    "REFUSAL_CURSOR_HELD",
    "REFUSAL_TRANSPORT_WATERMARK_COMMIT_FAILED",
    "REFUSAL_MIGRATION_CENSUS_COMMIT_FAILED",
)
