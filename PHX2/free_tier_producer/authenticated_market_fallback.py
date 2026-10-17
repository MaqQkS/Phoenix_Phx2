"""Authenticated PumpSwap account snapshot fallback for fresh market state.

Birdeye remains the convenience source.  When its provider timestamp is stale,
this module reads the already-proven PumpSwap pool and both SPL vault accounts
through authenticated Helius JSON-RPC.  It reuses the sole reserve decoder and
pricing helpers; no alternate formula and no historical stream are introduced.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request
import uuid

from PHX2.free_tier_producer.liquidity_integrity import b58encode
from PHX2.free_tier_producer.market_budget import (
    ORIGIN_FALLBACK,
    MarketPhysicalRequestMeter,
)
from PHX2.free_tier_producer.migration_admission import (
    MigrationProofStore,
    validate_migration_proof,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveError,
    actual_pool_tvl_usd,
    decode_pool_account,
    reserve_market_cap_usd,
    reserve_price_usd,
)
from PHX2.shadow_probes.helius_developer import build_authenticated_url
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_IDS,
    USDC_MINT,
)


FRESH_FALLBACK_SOURCE = "HELIUS_AUTHENTICATED_PUMPSWAP_ACCOUNTS"
FRESH_FALLBACK_ENDPOINT = "helius:getMultipleAccounts"
FRESH_FALLBACK_SCHEMA_VERSION = "phx2_authenticated_market_fallback_v1"
FRESH_FALLBACK_ARTIFACT_BASENAME = "authenticated_market_fallback.jsonl"

FRESH_FALLBACK_ACCEPTED = "FRESH_FALLBACK_ACCEPTED"
FRESH_FALLBACK_CAPABILITY_UNAVAILABLE = "FRESH_FALLBACK_CAPABILITY_UNAVAILABLE"
FRESH_FALLBACK_PROOF_MISSING = "FRESH_FALLBACK_MIGRATION_PROOF_MISSING"
FRESH_FALLBACK_PROOF_INVALID = "FRESH_FALLBACK_MIGRATION_PROOF_INVALID"
FRESH_FALLBACK_SUPPLY_UNAVAILABLE = "FRESH_FALLBACK_AUTHORITATIVE_SUPPLY_UNAVAILABLE"
FRESH_FALLBACK_QUOTE_UNAVAILABLE = "FRESH_FALLBACK_QUOTE_PRICE_UNAVAILABLE"
FRESH_FALLBACK_TRANSPORT = "FRESH_FALLBACK_TRANSPORT_ERROR"
FRESH_FALLBACK_HTTP = "FRESH_FALLBACK_HTTP_ERROR"
FRESH_FALLBACK_RESPONSE_ID = "FRESH_FALLBACK_RESPONSE_ID_MISMATCH"
FRESH_FALLBACK_RPC = "FRESH_FALLBACK_RPC_ERROR"
FRESH_FALLBACK_RESPONSE_SHAPE = "FRESH_FALLBACK_RESPONSE_SHAPE_INVALID"
FRESH_FALLBACK_CONTEXT_SLOT = "FRESH_FALLBACK_CONTEXT_SLOT_INVALID"
FRESH_FALLBACK_ACCOUNT_MISSING = "FRESH_FALLBACK_REQUIRED_ACCOUNT_MISSING"
FRESH_FALLBACK_ACCOUNT_OWNER = "FRESH_FALLBACK_ACCOUNT_OWNER_INVALID"
FRESH_FALLBACK_ACCOUNT_DATA = "FRESH_FALLBACK_ACCOUNT_DATA_INVALID"
FRESH_FALLBACK_POOL_IDENTITY = "FRESH_FALLBACK_POOL_IDENTITY_INVALID"
FRESH_FALLBACK_WRONG_MINT = "FRESH_FALLBACK_WRONG_MINT"
FRESH_FALLBACK_VAULT_IDENTITY = "FRESH_FALLBACK_VAULT_IDENTITY_INVALID"
FRESH_FALLBACK_DECIMALS = "FRESH_FALLBACK_DECIMALS_INVALID"
FRESH_FALLBACK_COMPUTATION = "FRESH_FALLBACK_COMPUTATION_INVALID"


def _now_iso(now_fn: Callable[[], float]) -> str:
    return datetime.fromtimestamp(
        float(now_fn()), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _http_class(status: object) -> str:
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        return f"{status // 100}XX"
    return "UNKNOWN"


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _account_bytes(account: Mapping[str, Any]) -> Optional[bytes]:
    encoded = account.get("data")
    if not isinstance(encoded, (list, tuple)) or len(encoded) != 2 \
            or encoded[1] != "base64" or not isinstance(encoded[0], str):
        return None
    try:
        return base64.b64decode(encoded[0], validate=True)
    except (ValueError, TypeError):
        return None


def _spl_vault(data: bytes) -> Optional[Tuple[str, int]]:
    if not isinstance(data, bytes) or len(data) < 165:
        return None
    try:
        return b58encode(data[:32]), int.from_bytes(data[64:72], "little")
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FreshMarketFallbackOutcome:
    accepted: bool
    reason: str
    observation: Optional[Mapping[str, Any]] = None
    request_ticket_ids: Tuple[str, ...] = ()


class AuthenticatedPumpSwapMarketFallback:
    """One exact authenticated pool/vault snapshot, validated fail-closed."""

    def __init__(
        self,
        *,
        rpc_base_url: str,
        api_key: str,
        proof_store: MigrationProofStore,
        ath_store: Any,
        quote_price_fn: Optional[Callable[[str], Any]],
        physical_request_meter: Optional[MarketPhysicalRequestMeter] = None,
        post_fn: Optional[
            Callable[[str, Mapping[str, Any], float], Tuple[int, Any]]] = None,
        artifact_path: Optional[object] = None,
        now_fn: Callable[[], float] = time.time,
        max_concurrency: int = 4,
    ) -> None:
        self._url = build_authenticated_url(
            str(rpc_base_url), str(api_key), expected_scheme="https")
        self._proofs = proof_store
        self._ath = ath_store
        self._quote_price = quote_price_fn
        self._meter = physical_request_meter
        self._post = post_fn or self._default_post
        self._artifact = Path(artifact_path) if artifact_path is not None else None
        self._now = now_fn
        self._lock = threading.RLock()
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) \
                or not 1 <= max_concurrency <= 32:
            raise ValueError("fresh_market_fallback_max_concurrency_invalid")
        self._http_gate = threading.BoundedSemaphore(max_concurrency)
        self._stats: Dict[str, Any] = {
            "fresh_fallback_requests": 0,
            "fresh_fallback_successes": 0,
            "fresh_fallback_failure_reasons": {},
        }

    def __repr__(self) -> str:
        return ("AuthenticatedPumpSwapMarketFallback("
                "rpc_base_url=<REDACTED>, api_key=<REDACTED>)")

    @staticmethod
    def _default_post(
        url: str, payload: Mapping[str, Any], timeout: float,
    ) -> Tuple[int, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib_request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib_request.urlopen(
                    req, timeout=max(0.1, float(timeout))) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
        except urllib_error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, {}

    def _failure(
        self, reason: str, ticket_id: Optional[str] = None,
    ) -> FreshMarketFallbackOutcome:
        with self._lock:
            failures = self._stats["fresh_fallback_failure_reasons"]
            failures[reason] = int(failures.get(reason, 0)) + 1
        return FreshMarketFallbackOutcome(
            False, reason, None, (() if ticket_id is None else (ticket_id,)))

    def _write_artifact(self, observation: Mapping[str, Any]) -> None:
        if self._artifact is None:
            return
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(
                observation, sort_keys=True, separators=(",", ":")))
            stream.write("\n")

    def fetch(
        self, mint: str, *, timeout_seconds: float = 10.0,
    ) -> FreshMarketFallbackOutcome:
        proof = self._proofs.get(mint)
        if proof is None:
            return self._failure(FRESH_FALLBACK_PROOF_MISSING)
        valid, _reason = validate_migration_proof(proof)
        if not valid:
            return self._failure(FRESH_FALLBACK_PROOF_INVALID)
        if proof.candidate_mint != mint or proof.base_mint != mint:
            return self._failure(FRESH_FALLBACK_WRONG_MINT)

        epoch_id = getattr(self._ath, "active_live_epoch_id", None)
        get_supply = getattr(self._ath, "authoritative_supply_record", None)
        if not isinstance(epoch_id, str) or not epoch_id or not callable(get_supply):
            return self._failure(FRESH_FALLBACK_CAPABILITY_UNAVAILABLE)
        supply = get_supply(mint, live_epoch_id=epoch_id)
        if not isinstance(supply, Mapping):
            return self._failure(FRESH_FALLBACK_SUPPLY_UNAVAILABLE)
        raw_supply = supply.get("raw_amount")
        supply_decimals = supply.get("decimals")
        try:
            if not isinstance(raw_supply, str) or not raw_supply.isdigit():
                raise ValueError
            raw_supply_int = int(raw_supply)
            if raw_supply_int <= 0:
                raise ValueError
            if isinstance(supply_decimals, bool) or not isinstance(supply_decimals, int):
                raise ValueError
        except (TypeError, ValueError):
            return self._failure(FRESH_FALLBACK_SUPPLY_UNAVAILABLE)
        if proof.base_deposit_decimals not in (None, supply_decimals):
            return self._failure(FRESH_FALLBACK_DECIMALS)
        if isinstance(proof.quote_deposit_decimals, bool) \
                or not isinstance(proof.quote_deposit_decimals, int):
            return self._failure(FRESH_FALLBACK_DECIMALS)

        if proof.quote_mint == USDC_MINT:
            quote_record: Any = {
                "price_usd": "1", "observed_at_utc": _now_iso(self._now)}
        elif self._quote_price is None:
            return self._failure(FRESH_FALLBACK_CAPABILITY_UNAVAILABLE)
        else:
            try:
                quote_record = self._quote_price(proof.quote_mint)
            except Exception:
                quote_record = None
        if not isinstance(quote_record, Mapping):
            return self._failure(FRESH_FALLBACK_QUOTE_UNAVAILABLE)
        try:
            quote_usd = Decimal(str(quote_record.get("price_usd")))
            if not quote_usd.is_finite() or quote_usd <= 0:
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            return self._failure(FRESH_FALLBACK_QUOTE_UNAVAILABLE)

        rpc_id = f"fresh_market_{uuid.uuid4().hex}"
        addresses = (proof.pool, proof.base_vault, proof.quote_vault)
        payload = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "getMultipleAccounts",
            "params": [list(addresses), {
                "commitment": "confirmed", "encoding": "base64"}],
        }
        ticket_id: Optional[str] = None
        meter = self._meter
        try:
            with self._lock:
                self._stats["fresh_fallback_requests"] += 1
            with self._http_gate:
                if meter is not None:
                    with meter.ownership(
                        origin=ORIGIN_FALLBACK,
                        epoch_id=epoch_id,
                        mint=mint,
                        scheduler_owner="AUTHENTICATED_FRESH_MARKET_FALLBACK",
                        batch_size=3,
                    ):
                        ticket_id = meter.begin_physical(
                            FRESH_FALLBACK_ENDPOINT, retry_index=0)
                status, response = self._post(
                    self._url, payload, max(0.1, float(timeout_seconds)))
        except Exception:
            if meter is not None and ticket_id is not None:
                meter.complete_physical(
                    ticket_id, http_status_class="TRANSPORT",
                    provider_outcome=FRESH_FALLBACK_TRANSPORT,
                    observation_accepted=False,
                    rejection_reason=FRESH_FALLBACK_TRANSPORT)
            return self._failure(FRESH_FALLBACK_TRANSPORT, ticket_id)

        reason = FRESH_FALLBACK_ACCEPTED
        observation: Optional[Dict[str, Any]] = None
        if not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300:
            reason = FRESH_FALLBACK_HTTP
        elif not isinstance(response, Mapping):
            reason = FRESH_FALLBACK_RESPONSE_SHAPE
        elif response.get("id") != rpc_id:
            reason = FRESH_FALLBACK_RESPONSE_ID
        elif response.get("error") is not None:
            reason = FRESH_FALLBACK_RPC
        else:
            result = response.get("result")
            context = result.get("context") if isinstance(result, Mapping) else None
            accounts = result.get("value") if isinstance(result, Mapping) else None
            slot = context.get("slot") if isinstance(context, Mapping) else None
            if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
                reason = FRESH_FALLBACK_CONTEXT_SLOT
            elif not isinstance(accounts, list) or len(accounts) != 3:
                reason = FRESH_FALLBACK_RESPONSE_SHAPE
            elif any(not isinstance(account, Mapping) for account in accounts):
                reason = FRESH_FALLBACK_ACCOUNT_MISSING
            else:
                pool_account, base_account, quote_account = accounts
                assert isinstance(pool_account, Mapping)
                assert isinstance(base_account, Mapping)
                assert isinstance(quote_account, Mapping)
                if (pool_account.get("owner") != PUMPSWAP_PROGRAM_ID
                        or pool_account.get("executable") is not False
                        or base_account.get("owner") not in SPL_TOKEN_PROGRAM_IDS
                        or quote_account.get("owner") not in SPL_TOKEN_PROGRAM_IDS
                        or base_account.get("executable") is not False
                        or quote_account.get("executable") is not False):
                    reason = FRESH_FALLBACK_ACCOUNT_OWNER
                else:
                    pool_data = _account_bytes(pool_account)
                    base_data = _account_bytes(base_account)
                    quote_data = _account_bytes(quote_account)
                    base_vault = _spl_vault(base_data or b"")
                    quote_vault = _spl_vault(quote_data or b"")
                    if pool_data is None or base_vault is None or quote_vault is None:
                        reason = FRESH_FALLBACK_ACCOUNT_DATA
                    elif base_vault[0] != mint or quote_vault[0] != proof.quote_mint:
                        reason = FRESH_FALLBACK_WRONG_MINT
                    elif len(pool_data) < 203:
                        reason = FRESH_FALLBACK_ACCOUNT_DATA
                    else:
                        try:
                            embedded_base_vault = b58encode(pool_data[139:171])
                            embedded_quote_vault = b58encode(pool_data[171:203])
                        except (TypeError, ValueError):
                            reason = FRESH_FALLBACK_ACCOUNT_DATA
                        else:
                            if (embedded_base_vault != proof.base_vault
                                    or embedded_quote_vault != proof.quote_vault):
                                reason = FRESH_FALLBACK_VAULT_IDENTITY
                            else:
                                accepted_at = _now_iso(self._now)
                                try:
                                    artifact = decode_pool_account(
                                        pool_data,
                                        raw_quote_vault_balance=quote_vault[1],
                                        raw_base_vault_balance=base_vault[1],
                                        observation_timestamp=accepted_at,
                                        pool_address=proof.pool,
                                        base_decimals=supply_decimals,
                                        quote_decimals=proof.quote_deposit_decimals,
                                    )
                                    if artifact.base_mint != mint \
                                            or artifact.quote_mint != proof.quote_mint:
                                        reason = FRESH_FALLBACK_WRONG_MINT
                                    else:
                                        artifact = replace(
                                            artifact, base_supply=raw_supply_int)
                                        current_price = reserve_price_usd(
                                            artifact, quote_price_usd=quote_usd)
                                        market_cap = reserve_market_cap_usd(
                                            artifact, quote_price_usd=quote_usd)
                                        liquidity = actual_pool_tvl_usd(
                                            artifact,
                                            quote_price_usd=quote_usd,
                                            base_price_usd=current_price,
                                        )
                                except PumpSwapReserveError:
                                    reason = FRESH_FALLBACK_COMPUTATION
                                else:
                                    if reason == FRESH_FALLBACK_ACCEPTED:
                                        provenance = {
                                            "schema_version": FRESH_FALLBACK_SCHEMA_VERSION,
                                            "source": FRESH_FALLBACK_SOURCE,
                                            "mint": mint,
                                            "pool_address": proof.pool,
                                            "program_id": PUMPSWAP_PROGRAM_ID,
                                            "base_vault": proof.base_vault,
                                            "quote_vault": proof.quote_vault,
                                            "quote_mint": proof.quote_mint,
                                            "account_context_slot": slot,
                                            "account_slots": {
                                                address: slot for address in addresses},
                                            "raw_quote_reserves": str(
                                                artifact.raw_quote_reserves),
                                            "virtual_quote_reserves": str(
                                                artifact.virtual_quote_reserves),
                                            "effective_quote_reserves": str(
                                                artifact.effective_quote_reserves),
                                            "base_reserves": str(
                                                artifact.base_reserves),
                                            "base_decimals": supply_decimals,
                                            "quote_decimals": proof.quote_deposit_decimals,
                                            "authoritative_supply_record": dict(supply),
                                            "quote_price_usd": _decimal_text(quote_usd),
                                            "quote_price_observed_at_utc": quote_record.get(
                                                "observed_at_utc"),
                                            "current_price": _decimal_text(current_price),
                                            "current_market_cap_usd": _decimal_text(market_cap),
                                            "liquidity_usd": _decimal_text(liquidity),
                                            "liquidity_definition": (
                                                "REAL_QUOTE_VAULT_PLUS_REAL_BASE_VAULT_"
                                                "AT_RESERVE_DERIVED_CURRENT_PRICE"),
                                            "fetched_at_utc": accepted_at,
                                            "accepted_at_utc": accepted_at,
                                            "request_ticket_ids": (
                                                [] if ticket_id is None else [ticket_id]),
                                            "migration_proof_digest": proof.proof_digest,
                                            "validation_result": FRESH_FALLBACK_ACCEPTED,
                                        }
                                        observation = {
                                            "accepted": True,
                                            "reason": FRESH_FALLBACK_ACCEPTED,
                                            "mint": mint,
                                            "market_provider": FRESH_FALLBACK_SOURCE,
                                            # This is explicitly the confirmed
                                            # account-read acceptance instant,
                                            # not a substituted provider event
                                            # timestamp.
                                            "account_observed_at_utc": accepted_at,
                                            "accepted_at_utc": accepted_at,
                                            "fetched_at_utc": accepted_at,
                                            "current_price": _decimal_text(current_price),
                                            "current_market_cap_usd": _decimal_text(market_cap),
                                            "liquidity_usd": _decimal_text(liquidity),
                                            "pumpswap_reserve": provenance,
                                        }

        if meter is not None and ticket_id is not None:
            meter.complete_physical(
                ticket_id,
                http_status_class=_http_class(status),
                provider_outcome=reason,
                observation_accepted=observation is not None,
                rejection_reason=None if observation is not None else reason,
            )
        if observation is None:
            return self._failure(reason, ticket_id)
        with self._lock:
            self._stats["fresh_fallback_successes"] += 1
            self._write_artifact(observation)
        return FreshMarketFallbackOutcome(
            True, FRESH_FALLBACK_ACCEPTED, observation,
            (() if ticket_id is None else (ticket_id,)))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "fresh_fallback_failure_reasons": dict(
                    self._stats["fresh_fallback_failure_reasons"]),
                "fresh_fallback_capability_available": True,
            }


__all__ = [
    "AuthenticatedPumpSwapMarketFallback",
    "FreshMarketFallbackOutcome",
    "FRESH_FALLBACK_ACCEPTED",
    "FRESH_FALLBACK_ARTIFACT_BASENAME",
    "FRESH_FALLBACK_CAPABILITY_UNAVAILABLE",
    "FRESH_FALLBACK_COMPUTATION",
    "FRESH_FALLBACK_SOURCE",
    "FRESH_FALLBACK_WRONG_MINT",
]
