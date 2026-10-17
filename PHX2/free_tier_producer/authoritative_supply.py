"""Authenticated on-chain token-supply proof for central ATH resolution.

The Solana ``getTokenSupply`` response is bound to one request id, one mint,
one live epoch, and one immutable physical-request ticket.  The module never
accepts a floating-point supply and never substitutes a conventional token
supply when RPC evidence is missing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib import request as urllib_request
from urllib import error as urllib_error
import uuid

from PHX2.free_tier_producer.market_budget import (
    ORIGIN_AUTHORITATIVE_SUPPLY,
    MarketPhysicalRequestMeter,
)
from PHX2.shadow_probes.helius_developer import build_authenticated_url


SOURCE_HELIUS_GET_TOKEN_SUPPLY = "HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY"
SUPPLY_RPC_ENDPOINT = "helius:getTokenSupply"
SUPPLY_RECORD_SCHEMA_VERSION = "phx2_authoritative_supply_v1"
SUPPLY_ARTIFACT_BASENAME = "authoritative_supply.jsonl"

SUPPLY_VALID = "SUPPLY_VALID"
SUPPLY_PENDING_NOT_ELIGIBLE = "SUPPLY_PENDING_NOT_ELIGIBLE"
SUPPLY_PENDING_EPOCH_MISMATCH = "SUPPLY_PENDING_EPOCH_MISMATCH"
SUPPLY_PENDING_PRE_BOUNDARY = "SUPPLY_PENDING_PRE_BOUNDARY"
SUPPLY_PENDING_TRANSPORT = "SUPPLY_PENDING_TRANSPORT"
SUPPLY_PENDING_HTTP = "SUPPLY_PENDING_HTTP"
SUPPLY_PENDING_RESPONSE_ID = "SUPPLY_PENDING_RESPONSE_ID"
SUPPLY_PENDING_RPC_ERROR = "SUPPLY_PENDING_RPC_ERROR"
SUPPLY_PENDING_RESPONSE_SHAPE = "SUPPLY_PENDING_RESPONSE_SHAPE"
SUPPLY_PENDING_MINT_MISMATCH = "SUPPLY_PENDING_MINT_MISMATCH"
SUPPLY_PENDING_AMOUNT_INVALID = "SUPPLY_PENDING_AMOUNT_INVALID"
SUPPLY_PENDING_DECIMALS_INVALID = "SUPPLY_PENDING_DECIMALS_INVALID"
SUPPLY_PENDING_NORMALIZATION_INVALID = "SUPPLY_PENDING_NORMALIZATION_INVALID"
SUPPLY_PENDING_CONTEXT_SLOT_INVALID = "SUPPLY_PENDING_CONTEXT_SLOT_INVALID"
SUPPLY_PENDING_AUTHENTICATION = "SUPPLY_PENDING_AUTHENTICATION"
SUPPLY_PENDING_EPOCH_INVALID = "SUPPLY_PENDING_EPOCH_INVALID"
SUPPLY_PENDING_CENTRAL_REJECTED = "SUPPLY_PENDING_CENTRAL_REJECTED"

SUPPLY_PENDING_REASONS = (
    SUPPLY_PENDING_NOT_ELIGIBLE,
    SUPPLY_PENDING_EPOCH_MISMATCH,
    SUPPLY_PENDING_PRE_BOUNDARY,
    SUPPLY_PENDING_TRANSPORT,
    SUPPLY_PENDING_HTTP,
    SUPPLY_PENDING_RESPONSE_ID,
    SUPPLY_PENDING_RPC_ERROR,
    SUPPLY_PENDING_RESPONSE_SHAPE,
    SUPPLY_PENDING_MINT_MISMATCH,
    SUPPLY_PENDING_AMOUNT_INVALID,
    SUPPLY_PENDING_DECIMALS_INVALID,
    SUPPLY_PENDING_NORMALIZATION_INVALID,
    SUPPLY_PENDING_CONTEXT_SLOT_INVALID,
    SUPPLY_PENDING_AUTHENTICATION,
    SUPPLY_PENDING_EPOCH_INVALID,
    SUPPLY_PENDING_CENTRAL_REJECTED,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_mint(value: object) -> Optional[str]:
    from PHX2.free_tier_producer.migration_admission import is_supported_mint_identity
    return value if is_supported_mint_identity(value) else None


def _http_class(status: object) -> str:
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        return f"{status // 100}XX"
    return "UNKNOWN"


@dataclass(frozen=True)
class AuthoritativeSupplyRecord:
    schema_version: str
    mint: str
    raw_amount: str
    decimals: int
    normalized_supply: str
    rpc_context_slot: int
    fetched_at_utc: str
    source: str
    live_epoch_id: str
    request_ticket_id: str
    validation_result: str
    cache_hit: bool = False

    def to_record(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupplyFetchOutcome:
    record: Optional[AuthoritativeSupplyRecord]
    reason: str
    retryable: bool
    request_ticket_id: Optional[str]

    @property
    def accepted(self) -> bool:
        return self.record is not None and self.reason == SUPPLY_VALID


class HeliusTokenSupplyClient:
    """One authenticated JSON-RPC call per cache miss, validated fail-closed."""

    def __init__(
        self,
        *,
        rpc_base_url: str,
        api_key: str,
        physical_request_meter: Optional[MarketPhysicalRequestMeter] = None,
        post_fn: Optional[Callable[[str, Mapping[str, Any], float], Tuple[int, Any]]] = None,
        cache_ttl_seconds: float = 3600.0,
        artifact_path: Optional[object] = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        # Build once to validate the secret-bearing configuration, but retain
        # only private fields and never expose the authenticated URL in repr or
        # exception text.
        self._url = build_authenticated_url(
            str(rpc_base_url), str(api_key), expected_scheme="https")
        self._meter = physical_request_meter
        self._post_fn = post_fn or self._default_post
        self._cache_ttl = max(0.0, float(cache_ttl_seconds))
        self._artifact = Path(artifact_path) if artifact_path is not None else None
        self._monotonic = monotonic_fn
        self._lock = threading.RLock()
        self._cache: Dict[str, Tuple[float, AuthoritativeSupplyRecord]] = {}
        self._stats: Dict[str, Any] = {
            "supply_requests": 0,
            "supply_successes": 0,
            "supply_cache_hits": 0,
            "supply_failure_reasons": {},
        }

    def __repr__(self) -> str:
        return "HeliusTokenSupplyClient(rpc_base_url=<REDACTED>, api_key=<REDACTED>)"

    @staticmethod
    def _default_post(
        url: str, payload: Mapping[str, Any], timeout: float,
    ) -> Tuple[int, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib_request.urlopen(
                    req, timeout=max(0.1, float(timeout))) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
        except urllib_error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = {}
        return status, decoded

    def _failure(
        self, reason: str, ticket_id: Optional[str], *, retryable: bool = True,
    ) -> SupplyFetchOutcome:
        with self._lock:
            failures = self._stats["supply_failure_reasons"]
            failures[reason] = int(failures.get(reason, 0)) + 1
        return SupplyFetchOutcome(None, reason, retryable, ticket_id)

    def _write_artifact(self, record: AuthoritativeSupplyRecord) -> None:
        if self._artifact is None:
            return
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(
                record.to_record(), sort_keys=True, separators=(",", ":")))
            stream.write("\n")

    def fetch(
        self,
        *,
        mint: object,
        live_epoch_id: object,
        timeout_seconds: float = 10.0,
        retry_index: int = 0,
    ) -> SupplyFetchOutcome:
        token = _canonical_mint(mint)
        epoch_id = live_epoch_id if isinstance(live_epoch_id, str) and live_epoch_id else None
        if token is None:
            return self._failure(SUPPLY_PENDING_MINT_MISMATCH, None, retryable=False)
        if epoch_id is None:
            return self._failure(SUPPLY_PENDING_EPOCH_INVALID, None, retryable=False)

        now = self._monotonic()
        with self._lock:
            cached = self._cache.get(token)
            if cached is not None and cached[1].live_epoch_id == epoch_id \
                    and now - cached[0] <= self._cache_ttl:
                self._stats["supply_cache_hits"] += 1
                return SupplyFetchOutcome(
                    replace(cached[1], cache_hit=True), SUPPLY_VALID, False,
                    cached[1].request_ticket_id)

        rpc_id = f"supply_{uuid.uuid4().hex}"
        payload = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "getTokenSupply",
            "params": [token, {"commitment": "confirmed"}],
        }
        ticket_id: Optional[str] = None
        meter = self._meter
        try:
            if meter is not None:
                with meter.ownership(
                    origin=ORIGIN_AUTHORITATIVE_SUPPLY,
                    epoch_id=epoch_id,
                    mint=token,
                    scheduler_owner="AUTHORITATIVE_SUPPLY",
                    batch_size=1,
                ):
                    ticket_id = meter.begin_physical(
                        SUPPLY_RPC_ENDPOINT, retry_index=retry_index)
            with self._lock:
                self._stats["supply_requests"] += 1
            status, response = self._post_fn(
                self._url, payload, max(0.1, float(timeout_seconds)))
        except Exception:
            if meter is not None and ticket_id is not None:
                meter.complete_physical(
                    ticket_id,
                    http_status_class="TRANSPORT",
                    provider_outcome=SUPPLY_PENDING_TRANSPORT,
                    observation_accepted=False,
                    rejection_reason=SUPPLY_PENDING_TRANSPORT,
                )
            return self._failure(SUPPLY_PENDING_TRANSPORT, ticket_id)

        reason = SUPPLY_VALID
        record: Optional[AuthoritativeSupplyRecord] = None
        if not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300:
            reason = SUPPLY_PENDING_HTTP
        elif not isinstance(response, Mapping):
            reason = SUPPLY_PENDING_RESPONSE_SHAPE
        elif response.get("id") != rpc_id:
            reason = SUPPLY_PENDING_RESPONSE_ID
        elif response.get("error") is not None:
            reason = SUPPLY_PENDING_RPC_ERROR
        else:
            result = response.get("result")
            context = result.get("context") if isinstance(result, Mapping) else None
            value = result.get("value") if isinstance(result, Mapping) else None
            response_mint = None
            if isinstance(result, Mapping):
                response_mint = result.get("mint") or result.get("requestedMint")
            if isinstance(value, Mapping):
                response_mint = value.get("mint") or value.get("requestedMint") or response_mint
            if not isinstance(result, Mapping) or not isinstance(context, Mapping) \
                    or not isinstance(value, Mapping):
                reason = SUPPLY_PENDING_RESPONSE_SHAPE
            elif response_mint is not None and response_mint != token:
                reason = SUPPLY_PENDING_MINT_MISMATCH
            else:
                raw_text = value.get("amount")
                decimals_value = value.get("decimals")
                slot_value = context.get("slot")
                try:
                    if not isinstance(raw_text, str) or not raw_text.isdigit():
                        raise ValueError
                    raw = int(raw_text)
                except (TypeError, ValueError):
                    reason = SUPPLY_PENDING_AMOUNT_INVALID
                else:
                    if isinstance(decimals_value, bool) or not isinstance(decimals_value, int) \
                            or not 0 <= decimals_value <= 255:
                        reason = SUPPLY_PENDING_DECIMALS_INVALID
                    elif isinstance(slot_value, bool) or not isinstance(slot_value, int) \
                            or slot_value < 0:
                        reason = SUPPLY_PENDING_CONTEXT_SLOT_INVALID
                    else:
                        try:
                            with localcontext() as ctx:
                                ctx.prec = max(80, len(raw_text) + decimals_value + 2)
                                normalized = Decimal(raw) / (Decimal(10) ** decimals_value)
                            ui_text = value.get("uiAmountString")
                            if ui_text is not None:
                                ui_value = Decimal(str(ui_text))
                                if not ui_value.is_finite() or ui_value != normalized:
                                    raise InvalidOperation
                        except (InvalidOperation, TypeError, ValueError):
                            reason = SUPPLY_PENDING_NORMALIZATION_INVALID
                        else:
                            record = AuthoritativeSupplyRecord(
                                schema_version=SUPPLY_RECORD_SCHEMA_VERSION,
                                mint=token,
                                raw_amount=str(raw),
                                decimals=decimals_value,
                                normalized_supply=format(normalized, "f"),
                                rpc_context_slot=slot_value,
                                fetched_at_utc=_now_iso(),
                                source=SOURCE_HELIUS_GET_TOKEN_SUPPLY,
                                live_epoch_id=epoch_id,
                                request_ticket_id=ticket_id or f"unmetered_{rpc_id}",
                                validation_result=SUPPLY_VALID,
                            )

        if meter is not None and ticket_id is not None:
            meter.complete_physical(
                ticket_id,
                http_status_class=_http_class(status),
                provider_outcome=reason,
                observation_accepted=record is not None,
                rejection_reason=None if record is not None else reason,
            )
        if record is None:
            return self._failure(reason, ticket_id)
        with self._lock:
            self._cache[token] = (now, record)
            self._stats["supply_successes"] += 1
            self._write_artifact(record)
        return SupplyFetchOutcome(record, SUPPLY_VALID, False, record.request_ticket_id)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "supply_failure_reasons": dict(self._stats["supply_failure_reasons"]),
                "supply_cache_entries": len(self._cache),
            }


@dataclass
class _PendingMint:
    first_pending_monotonic: float
    next_attempt_monotonic: float
    attempts: int = 0
    retries: int = 0
    last_reason: str = SUPPLY_PENDING_NOT_ELIGIBLE
    resolved: bool = False


class AuthoritativeSupplyBridge:
    """Live-epoch eligibility, bounded retry, and central-ATH handoff."""

    def __init__(
        self,
        *,
        client: HeliusTokenSupplyClient,
        ath_store: Any,
        backoff_base_seconds: float = 5.0,
        backoff_max_seconds: float = 300.0,
        systemic_pending_seconds: float = 900.0,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._ath_store = ath_store
        self._backoff_base = max(0.0, float(backoff_base_seconds))
        self._backoff_max = max(self._backoff_base, float(backoff_max_seconds))
        self._systemic_pending_seconds = max(1.0, float(systemic_pending_seconds))
        self._monotonic = monotonic_fn
        self._lock = threading.RLock()
        self._mints: Dict[str, _PendingMint] = {}
        self._central_observations = 0

    def _pending(self, mint: str, now: float) -> _PendingMint:
        return self._mints.setdefault(mint, _PendingMint(now, now))

    def observe_entry(
        self,
        entry: object,
        *,
        current_epoch_id: object,
        first_eligible_slot: object,
        timeout_seconds: float = 10.0,
    ) -> str:
        mint = _canonical_mint(getattr(entry, "token_mint", None))
        if mint is None:
            return SUPPLY_PENDING_MINT_MISMATCH
        now = self._monotonic()
        with self._lock:
            pending = self._pending(mint, now)
            if pending.resolved:
                return SUPPLY_VALID
            entry_epoch = getattr(entry, "live_epoch_id", None)
            migration_slot = getattr(entry, "migration_slot", None)
            if not isinstance(current_epoch_id, str) or not current_epoch_id:
                pending.last_reason = SUPPLY_PENDING_EPOCH_INVALID
                return pending.last_reason
            if entry_epoch != current_epoch_id:
                pending.last_reason = SUPPLY_PENDING_EPOCH_MISMATCH
                return pending.last_reason
            if isinstance(first_eligible_slot, bool) or not isinstance(first_eligible_slot, int) \
                    or first_eligible_slot <= 0:
                pending.last_reason = SUPPLY_PENDING_NOT_ELIGIBLE
                return pending.last_reason
            if isinstance(migration_slot, bool) or not isinstance(migration_slot, int) \
                    or migration_slot < first_eligible_slot:
                pending.last_reason = SUPPLY_PENDING_PRE_BOUNDARY
                return pending.last_reason
            if now < pending.next_attempt_monotonic:
                return pending.last_reason
            retry_index = pending.retries
            pending.attempts += 1

        outcome = self._client.fetch(
            mint=mint,
            live_epoch_id=current_epoch_id,
            timeout_seconds=timeout_seconds,
            retry_index=retry_index,
        )
        with self._lock:
            pending = self._pending(mint, now)
            if not outcome.accepted or outcome.record is None:
                pending.last_reason = outcome.reason
                pending.retries += 1
                delay = min(
                    self._backoff_max,
                    self._backoff_base * (2 ** min(pending.retries - 1, 30)),
                )
                pending.next_attempt_monotonic = now + delay
                return pending.last_reason

            record = outcome.record
            accepted = self._ath_store.observe_authoritative_supply(
                mint=record.mint,
                raw_amount=record.raw_amount,
                decimals=record.decimals,
                normalized_supply=record.normalized_supply,
                rpc_context_slot=record.rpc_context_slot,
                fetched_at_utc=record.fetched_at_utc,
                source=record.source,
                live_epoch_id=record.live_epoch_id,
                request_ticket_id=record.request_ticket_id,
                validation_result=record.validation_result,
            )
            if not accepted:
                pending.last_reason = SUPPLY_PENDING_CENTRAL_REJECTED
                pending.retries += 1
                pending.next_attempt_monotonic = now + min(
                    self._backoff_max,
                    self._backoff_base * (2 ** min(pending.retries - 1, 30)),
                )
                return pending.last_reason
            pending.resolved = True
            pending.last_reason = SUPPLY_VALID
            self._central_observations += 1
            return SUPPLY_VALID

    def due(self, mint: object) -> bool:
        """Whether a sweep slot can perform useful work for this mint now."""

        token = _canonical_mint(mint)
        if token is None:
            return False
        now = self._monotonic()
        with self._lock:
            pending = self._mints.get(token)
            return pending is None or (
                not pending.resolved and now >= pending.next_attempt_monotonic)

    def stats(self) -> Dict[str, Any]:
        now = self._monotonic()
        try:
            ath_stats = self._ath_store.stats()
        except Exception:
            ath_stats = {}
        with self._lock:
            unresolved = [item for item in self._mints.values() if not item.resolved]
            oldest = max(
                (max(0.0, now - item.first_pending_monotonic) for item in unresolved),
                default=0.0,
            )
            reasons: Dict[str, int] = {}
            for item in unresolved:
                reasons[item.last_reason] = reasons.get(item.last_reason, 0) + 1
            attempts = sum(item.attempts for item in self._mints.values())
            retries = sum(item.retries for item in self._mints.values())
            return {
                **self._client.stats(),
                "supply_bridge_attempts": attempts,
                "supply_retries": retries,
                "supply_central_observations": self._central_observations,
                "supply_resolved_tuples": int(
                    ath_stats.get("ath_resolved_tuples") or 0),
                "supply_pending": len(unresolved),
                "supply_pending_reasons": reasons,
                "supply_oldest_pending_age_seconds": oldest,
                "supply_systemic_pending_seconds": self._systemic_pending_seconds,
                "supply_systemic_failure": bool(
                    unresolved and oldest >= self._systemic_pending_seconds),
            }


__all__ = [
    "AuthoritativeSupplyBridge",
    "AuthoritativeSupplyRecord",
    "HeliusTokenSupplyClient",
    "SOURCE_HELIUS_GET_TOKEN_SUPPLY",
    "SUPPLY_ARTIFACT_BASENAME",
    "SUPPLY_PENDING_REASONS",
    "SUPPLY_VALID",
    "SupplyFetchOutcome",
]
