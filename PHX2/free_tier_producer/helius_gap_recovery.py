"""Bounded Helius HTTP recovery for an exact inclusive WSS slot gap.

The provider query is the proven ``getTransactionsForAddress`` shape over the
Pump program, succeeded transactions only, confirmed commitment, ascending
order, and exact ``gte`` / ``lte`` slot filters.  Pagination, rows, credits,
response bytes, and slot span all have hard ceilings.

Returned transactions are adapted into the existing PHX2 migration decoder.
Only full pagination exhaustion with a valid provider response proves coverage;
partial pages and even useful recovered migrations leave the gap unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

from PHX2.free_tier_producer.helius_source import (
    HELIUS_HTTP_SOURCE_IDENTITY,
    HeliusSourceConfig,
    project_admitted_helius_migration,
)
from PHX2.free_tier_producer.helius_byte_budget import (
    HeliusByteBudget,
    SOURCE_HTTP,
)
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    PUMPFUN_PROGRAM_ID,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.migration_journal import (
    APPEND_COMMITTED,
    APPEND_DUPLICATE,
    SOURCE_GAP_RECOVERY,
    build_journal_record,
)
from PHX2.free_tier_producer.source_continuity import (
    COVERAGE_COMPLETE,
    COVERAGE_FAILED,
    COVERAGE_PARTIAL,
    FAILURE_HTTP_CEILING,
    FAILURE_HTTP_PARTIAL,
    FAILURE_HTTP_PROVIDER,
    SourceContinuityTracker,
)
from PHX2.shadow_probes.helius_developer import (
    build_authenticated_url,
    build_slot_bounded_gtfa_request,
    gtfa_full_credits,
    helius_envelope_to_decoder_update,
)
from PHX2.stage28.chainstack_yellowstone_models import Stage28_10NormalizedEvent


RECOVERY_COMPLETE = "COMPLETE"
RECOVERY_PARTIAL = "PARTIAL"
RECOVERY_FAILED = "FAILED"

REASON_COMPLETE = "PAGINATION_EXHAUSTED"
REASON_PAGE_CEILING = "PAGE_CEILING"
REASON_RESULT_CEILING = "RESULT_CEILING"
REASON_CREDIT_CEILING = "CREDIT_CEILING"
REASON_SLOT_SPAN_CEILING = "SLOT_SPAN_CEILING"
REASON_PROVIDER_AUTH = "PROVIDER_AUTH_FAILURE"
REASON_PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMITED"
REASON_PROVIDER_ERROR = "PROVIDER_ERROR"
REASON_PROVIDER_PROTOCOL = "PROVIDER_PROTOCOL_INVALID"
REASON_PROVIDER_ROWS_REJECTED = "PROVIDER_ROWS_REJECTED"
REASON_LOCAL_DECODE_INCOMPLETE = "LOCAL_DECODE_INCOMPLETE"
REASON_PAGINATION_CYCLE = "PAGINATION_CYCLE"
REASON_ORDER_INVALID = "ORDER_INVALID"
REASON_BYTE_CEILING = "BYTE_CEILING"

DEFAULT_PAGE_SIZE = 25
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_RESULTS = 125
DEFAULT_MAX_CREDITS = 50
DEFAULT_MAX_SLOT_SPAN = 50_000
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class HeliusRecoveryConfigurationError(ValueError):
    """A recovery ceiling is absent or unsafe."""


class HeliusRecoveryProviderError(RuntimeError):
    """Provider failure carrying only a closed-set reason token."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class HeliusRecoveryConfig:
    page_size: int = DEFAULT_PAGE_SIZE
    max_pages: int = DEFAULT_MAX_PAGES
    max_results: int = DEFAULT_MAX_RESULTS
    max_credits: int = DEFAULT_MAX_CREDITS
    max_slot_span: int = DEFAULT_MAX_SLOT_SPAN
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        if not 1 <= int(self.page_size) <= 100:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery page size is out of range"
            )
        if not 1 <= int(self.max_pages) <= 20:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery page ceiling is out of range"
            )
        if not 1 <= int(self.max_results) <= 2000:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery result ceiling is out of range"
            )
        if not 10 <= int(self.max_credits) <= 1000:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery credit ceiling is out of range"
            )
        if not 1 <= int(self.max_slot_span) <= 100_000:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery slot ceiling is out of range"
            )
        if not 1 <= float(self.timeout_seconds) <= 60:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery timeout is out of range"
            )
        if not 1024 <= int(self.max_response_bytes) <= 64 * 1024 * 1024:
            raise HeliusRecoveryConfigurationError(
                "Helius recovery response ceiling is out of range"
            )


@dataclass
class HeliusRecoveryMetrics:
    requests: int = 0
    pages: int = 0
    returned_rows: int = 0
    accepted_in_range_rows: int = 0
    duplicates: int = 0
    decoded_migrations: int = 0
    migrate: int = 0
    migrate_v2: int = 0
    non_migrations: int = 0
    decoder_rejections: int = 0
    rejected_rows: int = 0
    wrong_slot_rows: int = 0
    failed_rows: int = 0
    malformed_rows: int = 0
    estimated_credits: int = 0
    journal_records_committed: int = 0
    journal_duplicate_records: int = 0
    journal_failures: int = 0

    def snapshot(self) -> Dict[str, int]:
        return {
            "requests": self.requests,
            "pages": self.pages,
            "returned_rows": self.returned_rows,
            "accepted_in_range_rows": self.accepted_in_range_rows,
            "duplicates": self.duplicates,
            "decoded_migrations": self.decoded_migrations,
            "migrate": self.migrate,
            "migrate_v2": self.migrate_v2,
            "non_migrations": self.non_migrations,
            "decoder_rejections": self.decoder_rejections,
            "rejected_rows": self.rejected_rows,
            "wrong_slot_rows": self.wrong_slot_rows,
            "failed_rows": self.failed_rows,
            "malformed_rows": self.malformed_rows,
            "estimated_credits": self.estimated_credits,
            "journal_records_committed": self.journal_records_committed,
            "journal_duplicate_records": self.journal_duplicate_records,
            "journal_failures": self.journal_failures,
        }


@dataclass(frozen=True)
class HeliusRecoveryOutcome:
    gap_id: str
    gap_from_slot: int
    gap_to_slot: int
    coverage_status: str
    coverage_reason: str
    complete_range_proven: bool
    pagination_exhausted: bool
    empty_range: bool
    recovered_signatures: tuple[str, ...]
    recovered_slots: tuple[int, ...]
    metrics: Mapping[str, int]
    migration_types: tuple[str, ...]
    migrations: tuple[Stage28_10NormalizedEvent, ...] = field(
        repr=False,
        compare=False,
    )


def _provider_reason(status: Optional[int]) -> str:
    if status in (401, 403):
        return REASON_PROVIDER_AUTH
    if status == 429:
        return REASON_PROVIDER_RATE_LIMIT
    return REASON_PROVIDER_ERROR


class HeliusEnhancedHttpClient:
    """One bounded authenticated JSON-RPC caller with redacted failures."""

    def __init__(
        self,
        config: HeliusSourceConfig,
        *,
        byte_budget: Optional[HeliusByteBudget] = None,
    ) -> None:
        self._config = config
        self._byte_budget = byte_budget

    def call(
        self,
        payload: Mapping[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> Mapping[str, object]:
        url = build_authenticated_url(
            self._config.rpc_base_url.reveal(),
            self._config.api_key.reveal(),
            expected_scheme="https",
        )
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib_request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib_request.urlopen(
                request, timeout=timeout_seconds
            ) as response:
                raw = response.read(max_response_bytes + 1)
        except urllib_error.HTTPError as exc:
            raise HeliusRecoveryProviderError(
                _provider_reason(int(exc.code))
            ) from None
        except (urllib_error.URLError, TimeoutError, OSError):
            raise HeliusRecoveryProviderError(REASON_PROVIDER_ERROR) from None
        finally:
            url = ""
        if len(raw) > max_response_bytes:
            raise HeliusRecoveryProviderError(REASON_PROVIDER_PROTOCOL)
        if self._byte_budget is not None and not self._byte_budget.consume(
            len(raw), source=SOURCE_HTTP
        ):
            raise HeliusRecoveryProviderError(REASON_BYTE_CEILING)
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HeliusRecoveryProviderError(
                REASON_PROVIDER_PROTOCOL
            ) from None
        if not isinstance(parsed, Mapping):
            raise HeliusRecoveryProviderError(REASON_PROVIDER_PROTOCOL)
        return parsed


def _entry_signature(entry: Mapping[str, object]) -> Optional[str]:
    direct = entry.get("signature")
    if isinstance(direct, str) and direct:
        return direct
    transaction = entry.get("transaction")
    if isinstance(transaction, Mapping):
        # gTFA may wrap the Solana transaction alongside meta.
        inner = transaction.get("transaction")
        if isinstance(inner, Mapping):
            transaction = inner
        signatures = transaction.get("signatures")
        if (
            isinstance(signatures, list)
            and signatures
            and isinstance(signatures[0], str)
            and signatures[0]
        ):
            return signatures[0]
    return None


def _entry_meta(entry: Mapping[str, object]) -> Optional[Mapping[str, object]]:
    meta = entry.get("meta")
    if isinstance(meta, Mapping):
        return meta
    transaction = entry.get("transaction")
    if isinstance(transaction, Mapping) and isinstance(
        transaction.get("meta"), Mapping
    ):
        return transaction["meta"]
    return None


def _transaction_index(entry: Mapping[str, object]) -> Optional[int]:
    value = entry.get("transactionIndex")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return None


class HeliusSlotGapRecoverer:
    """Recover one exact WSS gap without broad history or startup crawling."""

    def __init__(
        self,
        *,
        source_config: HeliusSourceConfig,
        recovery_config: Optional[HeliusRecoveryConfig] = None,
        continuity: Optional[SourceContinuityTracker] = None,
        http_call: Optional[Callable[..., Mapping[str, object]]] = None,
        byte_budget: Optional[HeliusByteBudget] = None,
        proof_store: Any = None,
        census_sink: Optional[Callable[[object], None]] = None,
        journal: Any = None,
        candidate_commit_fn: Optional[Callable[..., bool]] = None,
        now_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        self._source_config = source_config
        self.config = recovery_config or HeliusRecoveryConfig()
        self._continuity = continuity
        self._client = HeliusEnhancedHttpClient(
            source_config,
            byte_budget=byte_budget,
        )
        self._byte_budget = byte_budget
        self._http_call = http_call
        self._proof_store = proof_store
        self._census_sink = census_sink
        self._journal = journal
        self._candidate_commit_fn = candidate_commit_fn
        self.admission_commit_failed = False
        self._now = now_fn or self._utc_now

    @staticmethod
    def _utc_now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def build_request(
        self,
        *,
        request_id: int,
        gap_from_slot: int,
        gap_to_slot: int,
        limit: int,
        pagination_token: Optional[str],
    ) -> Dict[str, object]:
        return build_slot_bounded_gtfa_request(
            request_id=request_id,
            address=PUMPFUN_PROGRAM_ID,
            slot_gte=gap_from_slot,
            slot_lte=gap_to_slot,
            limit=limit,
            pagination_token=pagination_token,
        )

    def _call(self, request: Mapping[str, object]) -> Mapping[str, object]:
        if self._http_call is not None:
            return self._http_call(
                request,
                timeout_seconds=self.config.timeout_seconds,
                max_response_bytes=self.config.max_response_bytes,
            )
        return self._client.call(
            request,
            timeout_seconds=self.config.timeout_seconds,
            max_response_bytes=self.config.max_response_bytes,
        )

    def _finalize_continuity(
        self,
        *,
        gap_id: str,
        gap_from_slot: int,
        gap_to_slot: int,
        status: str,
        reason: str,
        signatures: Sequence[str],
        slots: Sequence[int],
    ) -> None:
        tracker = self._continuity
        if tracker is None:
            return
        coverage = (
            COVERAGE_COMPLETE
            if status == RECOVERY_COMPLETE
            else COVERAGE_PARTIAL
            if status == RECOVERY_PARTIAL
            else COVERAGE_FAILED
        )
        tracker.record_recovery_evidence(
            gap_id=gap_id,
            signatures=signatures,
            slots=slots,
            coverage_status=coverage,
        )
        if status == RECOVERY_COMPLETE:
            tracker.apply_recovered_range(gap_from_slot, gap_to_slot)
            return
        ceiling_reasons = {
            REASON_PAGE_CEILING,
            REASON_RESULT_CEILING,
            REASON_CREDIT_CEILING,
            REASON_SLOT_SPAN_CEILING,
            REASON_BYTE_CEILING,
        }
        failure = (
            FAILURE_HTTP_CEILING
            if reason in ceiling_reasons
            else FAILURE_HTTP_PROVIDER
            if reason.startswith("PROVIDER_")
            else FAILURE_HTTP_PARTIAL
        )
        tracker.mark_recovery_failed(gap_id, reason=failure)

    def _outcome(
        self,
        *,
        gap_id: str,
        gap_from_slot: int,
        gap_to_slot: int,
        status: str,
        reason: str,
        exhausted: bool,
        signatures: Sequence[str],
        slots: Sequence[int],
        metrics: HeliusRecoveryMetrics,
        migration_types: Sequence[str],
        migrations: Sequence[Stage28_10NormalizedEvent],
    ) -> HeliusRecoveryOutcome:
        self._finalize_continuity(
            gap_id=gap_id,
            gap_from_slot=gap_from_slot,
            gap_to_slot=gap_to_slot,
            status=status,
            reason=reason,
            signatures=signatures,
            slots=slots,
        )
        return HeliusRecoveryOutcome(
            gap_id=gap_id,
            gap_from_slot=gap_from_slot,
            gap_to_slot=gap_to_slot,
            coverage_status=status,
            coverage_reason=reason,
            complete_range_proven=(
                status == RECOVERY_COMPLETE and exhausted
            ),
            pagination_exhausted=exhausted,
            empty_range=bool(exhausted and not signatures),
            recovered_signatures=tuple(signatures),
            recovered_slots=tuple(slots),
            metrics=metrics.snapshot(),
            migration_types=tuple(migration_types),
            migrations=tuple(migrations),
        )

    def _journal_recovered(
        self,
        *,
        decision: Any,
        signature: str,
        slot: int,
        metrics: HeliusRecoveryMetrics,
    ) -> None:
        """Persist one recovered proof idempotently.

        A signature the live socket already journalled comes back DUPLICATE and
        writes nothing: exact-range recovery deliberately re-requests ground
        that may overlap live delivery, and the journal is what makes that
        overlap harmless.
        """

        journal = self._journal
        if journal is None:
            return
        proof = getattr(decision, "proof", None)
        record = build_journal_record(
            mint=getattr(decision, "candidate_mint", None),
            signature=signature,
            migration_slot=slot,
            migration_kind=getattr(decision, "migration_version", None),
            migration_proof_digest=getattr(proof, "proof_digest", None),
            block_time_utc=getattr(decision, "block_time_utc", None),
            source=SOURCE_GAP_RECOVERY,
        )
        if record is None:
            metrics.journal_failures += 1
            return
        try:
            result = journal.append(record)
        except Exception:
            metrics.journal_failures += 1
            return
        outcome = getattr(result, "outcome", None)
        if outcome == APPEND_COMMITTED:
            metrics.journal_records_committed += 1
            try:
                journal.commit_cursor(slot)
            except Exception:
                metrics.journal_failures += 1
        elif outcome == APPEND_DUPLICATE:
            metrics.journal_duplicate_records += 1
        else:
            metrics.journal_failures += 1

    def recover(
        self,
        *,
        gap_id: str,
        gap_from_slot: int,
        gap_to_slot: int,
    ) -> HeliusRecoveryOutcome:
        if (
            not isinstance(gap_id, str)
            or not gap_id
            or isinstance(gap_from_slot, bool)
            or isinstance(gap_to_slot, bool)
            or not isinstance(gap_from_slot, int)
            or not isinstance(gap_to_slot, int)
            or gap_from_slot < 0
            or gap_to_slot < gap_from_slot
        ):
            raise ValueError("Helius recovery gap identity is invalid")
        metrics = HeliusRecoveryMetrics()
        span = gap_to_slot - gap_from_slot + 1
        if span > self.config.max_slot_span:
            return self._outcome(
                gap_id=gap_id,
                gap_from_slot=gap_from_slot,
                gap_to_slot=gap_to_slot,
                status=RECOVERY_FAILED,
                reason=REASON_SLOT_SPAN_CEILING,
                exhausted=False,
                signatures=(),
                slots=(),
                metrics=metrics,
                migration_types=(),
                migrations=(),
            )
        if self._continuity is not None:
            self._continuity.mark_recovery_requested(gap_id, gap_from_slot)

        accepted: List[Mapping[str, object]] = []
        signatures: List[str] = []
        slots: List[int] = []
        migrations: List[Stage28_10NormalizedEvent] = []
        migration_types: List[str] = []
        seen_signatures: set[str] = set()
        seen_tokens: set[str] = set()
        token: Optional[str] = None
        exhausted = False
        terminal_reason: Optional[str] = None
        previous_slot: Optional[int] = None
        previous_index: Optional[int] = None

        for page_index in range(self.config.max_pages):
            remaining_results = self.config.max_results - metrics.returned_rows
            if remaining_results <= 0:
                terminal_reason = REASON_RESULT_CEILING
                break
            page_limit = min(self.config.page_size, remaining_results)
            page_credit_ceiling = gtfa_full_credits(page_limit)
            if (
                metrics.estimated_credits + page_credit_ceiling
                > self.config.max_credits
            ):
                terminal_reason = REASON_CREDIT_CEILING
                break
            request_id = 9000 + page_index
            request = self.build_request(
                request_id=request_id,
                gap_from_slot=gap_from_slot,
                gap_to_slot=gap_to_slot,
                limit=page_limit,
                pagination_token=token,
            )
            metrics.requests += 1
            try:
                response = self._call(request)
            except HeliusRecoveryProviderError as exc:
                terminal_reason = exc.reason
                break
            except Exception:
                terminal_reason = REASON_PROVIDER_ERROR
                break
            if (
                response.get("jsonrpc") != "2.0"
                or response.get("id") != request_id
                or "error" in response
            ):
                terminal_reason = REASON_PROVIDER_PROTOCOL
                break
            result = response.get("result")
            if not isinstance(result, Mapping) or not isinstance(
                result.get("data"), list
            ):
                terminal_reason = REASON_PROVIDER_PROTOCOL
                break
            rows = result["data"]
            assert isinstance(rows, list)
            if len(rows) > page_limit:
                terminal_reason = REASON_PROVIDER_PROTOCOL
                break
            metrics.pages += 1
            metrics.returned_rows += len(rows)
            page_credits = gtfa_full_credits(len(rows))
            metrics.estimated_credits += page_credits
            if self._byte_budget is not None:
                self._byte_budget.record_estimated_credits(
                    page_credits,
                    source=SOURCE_HTTP,
                )
            order_invalid = False
            for entry in rows:
                if not isinstance(entry, Mapping):
                    metrics.malformed_rows += 1
                    metrics.rejected_rows += 1
                    continue
                slot = entry.get("slot")
                signature = _entry_signature(entry)
                meta = _entry_meta(entry)
                if (
                    isinstance(slot, bool)
                    or not isinstance(slot, int)
                    or signature is None
                    or meta is None
                ):
                    metrics.malformed_rows += 1
                    metrics.rejected_rows += 1
                    continue
                if not gap_from_slot <= slot <= gap_to_slot:
                    metrics.wrong_slot_rows += 1
                    metrics.rejected_rows += 1
                    continue
                if meta.get("err") is not None:
                    metrics.failed_rows += 1
                    metrics.rejected_rows += 1
                    continue
                index = _transaction_index(entry)
                if previous_slot is not None:
                    if slot < previous_slot:
                        order_invalid = True
                    elif (
                        slot == previous_slot
                        and index is not None
                        and previous_index is not None
                        and index < previous_index
                    ):
                        order_invalid = True
                previous_slot = slot
                previous_index = index
                if signature in seen_signatures:
                    metrics.duplicates += 1
                    continue
                seen_signatures.add(signature)
                accepted.append(entry)
                signatures.append(signature)
                slots.append(slot)
                metrics.accepted_in_range_rows += 1
            if order_invalid:
                terminal_reason = REASON_ORDER_INVALID
                break
            next_token = result.get("paginationToken")
            if next_token is None:
                exhausted = True
                break
            if not isinstance(next_token, str) or not next_token:
                terminal_reason = REASON_PROVIDER_PROTOCOL
                break
            if next_token in seen_tokens:
                terminal_reason = REASON_PAGINATION_CYCLE
                break
            seen_tokens.add(next_token)
            token = next_token
        if not exhausted and terminal_reason is None:
            terminal_reason = REASON_PAGE_CEILING

        for entry, signature, slot in zip(accepted, signatures, slots):
            try:
                update = helius_envelope_to_decoder_update(entry)
                decision = evaluate_migration_admission(
                    update, observed_at_utc=self._now()
                )
            except Exception:
                metrics.decoder_rejections += 1
                continue
            if decision is None:
                metrics.non_migrations += 1
                continue
            raw_hash = hashlib.sha256(
                json.dumps(
                    entry,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest()
            event = project_admitted_helius_migration(
                decision=decision,
                signature=signature,
                slot=slot,
                observed_at_utc=self._now(),
                raw_event_hash=raw_hash,
                source_identity=HELIUS_HTTP_SOURCE_IDENTITY,
            )
            if event is None:
                metrics.decoder_rejections += 1
                continue
            proof = getattr(decision, "proof", None)
            if proof is not None and self._proof_store is not None:
                try:
                    self._proof_store.seal_and_store(proof)
                except Exception:
                    metrics.decoder_rejections += 1
                    continue
            if proof is not None and self._census_sink is not None:
                try:
                    if self._census_sink(proof) is False:
                        raise OSError("MIGRATION_CENSUS_COMMIT_FAILED")
                except Exception:
                    metrics.decoder_rejections += 1
                    continue
            if self._candidate_commit_fn is not None:
                try:
                    if self._candidate_commit_fn(event, migration_proof=proof,
                            migration_signature=signature, event_slot=slot,
                            replayed=True) is not True:
                        raise RuntimeError("ADMISSION_INBOX_COMMIT_FAILED")
                except Exception:
                    # Do not credit complete coverage for an unowned migration.
                    self.admission_commit_failed = True
                    metrics.decoder_rejections += 1
                    continue
            self._journal_recovered(
                decision=decision,
                signature=signature,
                slot=slot,
                metrics=metrics,
            )
            migrations.append(event)
            migration_types.append(str(decision.migration_version))
            metrics.decoded_migrations += 1
            if decision.migration_version == MIGRATION_VERSION_V1:
                metrics.migrate += 1
            elif decision.migration_version == MIGRATION_VERSION_V2:
                metrics.migrate_v2 += 1

        if (
            exhausted
            and metrics.rejected_rows == 0
            and metrics.decoder_rejections == 0
        ):
            status = RECOVERY_COMPLETE
            reason = REASON_COMPLETE
        elif terminal_reason in (
            REASON_PROVIDER_AUTH,
            REASON_PROVIDER_RATE_LIMIT,
            REASON_PROVIDER_ERROR,
            REASON_PROVIDER_PROTOCOL,
            REASON_SLOT_SPAN_CEILING,
            REASON_BYTE_CEILING,
        ) and not accepted:
            status = RECOVERY_FAILED
            reason = terminal_reason
        else:
            status = RECOVERY_PARTIAL
            reason = (
                REASON_PROVIDER_ROWS_REJECTED
                if exhausted and metrics.rejected_rows
                else REASON_LOCAL_DECODE_INCOMPLETE
                if exhausted and metrics.decoder_rejections
                else terminal_reason or REASON_PROVIDER_PROTOCOL
            )
        return self._outcome(
            gap_id=gap_id,
            gap_from_slot=gap_from_slot,
            gap_to_slot=gap_to_slot,
            status=status,
            reason=reason,
            exhausted=exhausted,
            signatures=signatures,
            slots=slots,
            metrics=metrics,
            migration_types=migration_types,
            migrations=migrations,
        )


__all__ = (
    "DEFAULT_MAX_CREDITS",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MAX_SLOT_SPAN",
    "DEFAULT_PAGE_SIZE",
    "HeliusEnhancedHttpClient",
    "HeliusRecoveryConfig",
    "HeliusRecoveryConfigurationError",
    "HeliusRecoveryMetrics",
    "HeliusRecoveryOutcome",
    "HeliusRecoveryProviderError",
    "HeliusSlotGapRecoverer",
    "RECOVERY_COMPLETE",
    "RECOVERY_FAILED",
    "RECOVERY_PARTIAL",
    "REASON_BYTE_CEILING",
    "REASON_COMPLETE",
    "REASON_CREDIT_CEILING",
    "REASON_LOCAL_DECODE_INCOMPLETE",
    "REASON_ORDER_INVALID",
    "REASON_PAGE_CEILING",
    "REASON_PAGINATION_CYCLE",
    "REASON_PROVIDER_AUTH",
    "REASON_PROVIDER_ERROR",
    "REASON_PROVIDER_PROTOCOL",
    "REASON_PROVIDER_RATE_LIMIT",
    "REASON_PROVIDER_ROWS_REJECTED",
    "REASON_RESULT_CEILING",
    "REASON_SLOT_SPAN_CEILING",
)
