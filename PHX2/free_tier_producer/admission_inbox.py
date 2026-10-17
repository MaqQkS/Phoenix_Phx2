"""Bounded durable ownership of public migration candidates awaiting a watch.

Digests detect corruption, not hostile modification by a writer with access to
the runtime directory. Only the canonical source admission boundary creates
receipts; replay revalidates the sealed proof and its original epoch boundary.
No credentials, provider envelopes, or arbitrary candidate extensions persist.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from PHX2.free_tier_producer.migration_admission import (
    candidate_migration_is_admitted, candidate_migration_proof,
)
from PHX2.models.discovery_provenance import LIVE_DISCOVERY_PROVENANCES

SCHEMA = "phx2_pending_admission_v1"
MAX_PENDING = 4096
MAX_RECEIPT_BYTES = 16384
_FIELDS = frozenset((
    "token_mint", "candidate_id", "migration_time_utc", "local_observed_at_utc",
    "migration_time_source", "migration_time_authoritative", "provider_event_id",
    "discovery_provider", "discovery_provenance", "discovery_utc", "live_epoch_id",
    "migration_slot", "migration_signature", "migration_proof",
    "migration_evidence_class", "pair_address", "pool_dex_identity",
    "migration_mc_source", "ath_source", "liquidity_source", "current_data_source",
    "source_confidence", "dedupe_identity", "migration_market_cap_usd",
    "migration_market_cap_price", "migration_supply_at_observation",
    "migration_market_cap_observed_at_utc", "migration_market_cap_source",
))
_BINDING = ("token_mint", "candidate_id", "pair_address", "migration_signature", "migration_slot",
            "live_epoch_id", "discovery_provenance", "migration_proof")


class AdmissionInboxError(OSError):
    """Closed-set local persistence/admission failure; contains no raw input."""


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _public_candidate(candidate: Mapping[str, Any]) -> dict:
    proof = candidate_migration_proof(candidate.get("migration_proof"))
    if proof is None or not candidate_migration_is_admitted(candidate):
        raise AdmissionInboxError("ADMISSION_PROOF_INVALID")
    public = {key: candidate[key] for key in _FIELDS if key in candidate}
    public["migration_proof"] = proof.to_dict()
    # A provider raw_ref may contain a URL. Use the exact public signature as
    # the stable source reference instead; never retain arbitrary raw refs.
    public["source_ref"] = proof.migration_signature
    for key, value in public.items():
        if key == "migration_proof":
            continue
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise AdmissionInboxError("ADMISSION_PUBLIC_FIELD_INVALID")
        if isinstance(value, str) and (len(value) > 256 or "://" in value
                                      or "@" in value or "\n" in value):
            raise AdmissionInboxError("ADMISSION_PUBLIC_FIELD_INVALID")
    return public


def validate_admission_receipt(value: object, candidate: object = None) -> bool:
    """Validate persisted ownership and, optionally, an exact watch identity."""
    try:
        if not isinstance(value, Mapping) or set(value) != {
                "schema", "candidate", "first_eligible_slot", "receipt_id"}:
            return False
        if value["schema"] != SCHEMA or len(_bytes(value)) > MAX_RECEIPT_BYTES:
            return False
        saved = value["candidate"]
        if not isinstance(saved, dict) or _public_candidate(saved) != saved:
            return False
        epoch = saved.get("live_epoch_id")
        boundary, slot = value["first_eligible_slot"], saved.get("migration_slot")
        if (not isinstance(epoch, str) or not epoch or
                saved.get("discovery_provenance") not in LIVE_DISCOVERY_PROVENANCES or
                type(boundary) is not int or boundary <= 0 or
                type(slot) is not int or slot < boundary):
            return False
        observed = saved.get("local_observed_at_utc") or saved.get("discovery_utc")
        if not isinstance(observed, str) or datetime.fromisoformat(
                observed.replace("Z", "+00:00")).tzinfo is None:
            return False
        if value["receipt_id"] != _digest({k: v for k, v in value.items()
                                           if k != "receipt_id"}):
            return False
        if candidate is not None:
            if not isinstance(candidate, Mapping):
                return False
            if any(candidate.get(k) != saved.get(k) for k in _BINDING):
                return False
        return True
    except (TypeError, ValueError, OverflowError, AdmissionInboxError):
        return False


class DurableAdmissionInbox:
    """One process owner, bounded records/bytes, fail-closed restart loading."""

    def __init__(self, path: object, *, max_pending: int = 256) -> None:
        if type(max_pending) is not int or not 1 <= max_pending <= MAX_PENDING:
            raise ValueError("ADMISSION_CAPACITY_INVALID")
        self.path = Path(path)
        self.max_pending = max_pending
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}
        self._generation = 0
        self._poisoned = False
        self._load()

    def _ensure_healthy(self) -> None:
        if self._poisoned:
            raise AdmissionInboxError("ADMISSION_INBOX_RELOAD_REQUIRED")

    def _read(self) -> dict:
        with self.path.open("rb") as handle:
            raw = handle.read(self.max_pending * MAX_RECEIPT_BYTES + 4097)
        if len(raw) > self.max_pending * MAX_RECEIPT_BYTES + 4096:
            raise AdmissionInboxError("ADMISSION_INBOX_TOO_LARGE")
        data = json.loads(raw)
        if (not isinstance(data, dict) or set(data) != {
                "schema", "generation", "pending", "digest"} or
                data.get("schema") != SCHEMA or
                type(data.get("generation")) is not int or data["generation"] < 1 or
                data["digest"] != _digest({k: v for k, v in data.items() if k != "digest"}) or
                not isinstance(data["pending"], list) or
                len(data["pending"]) > self.max_pending):
            raise AdmissionInboxError("ADMISSION_INBOX_INVALID")
        identities = set()
        for record in data["pending"]:
            if not validate_admission_receipt(record):
                raise AdmissionInboxError("ADMISSION_RECEIPT_INVALID")
            mint = record["candidate"]["token_mint"]
            if mint in identities:
                raise AdmissionInboxError("ADMISSION_DUPLICATE_IDENTITY")
            identities.add(mint)
        return data

    def _load(self) -> None:
        try:
            data = self._read()
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise AdmissionInboxError("ADMISSION_INBOX_LOAD_FAILED") from exc
        self._generation = data["generation"]
        self._pending = {r["receipt_id"]: r for r in data["pending"]}

    def _commit(self, records: dict[str, dict]) -> None:
        self._ensure_healthy()
        data = {"schema": SCHEMA, "generation": self._generation + 1,
                "pending": list(records.values())}
        data["digest"] = _digest(data)
        payload = _bytes(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # A failed replace/readback can have an uncertain disk outcome.
            # Never let the watch thread overwrite a newer canonical receipt
            # using stale in-memory state; only a fresh validated load recovers.
            self._poisoned = True
            os.replace(temporary, self.path)
            if self._read() != data:
                raise AdmissionInboxError("ADMISSION_INBOX_VERIFY_FAILED")
        except (OSError, ValueError, TypeError) as exc:
            raise AdmissionInboxError("ADMISSION_INBOX_COMMIT_FAILED") from exc
        self._pending = records
        self._generation = data["generation"]
        self._poisoned = False

    def pending(self) -> tuple[dict, ...]:
        with self._lock:
            self._ensure_healthy()
            return tuple(json.loads(_bytes(r)) for r in self._pending.values())

    def receipt_for(self, candidate: Mapping[str, Any]) -> dict | None:
        with self._lock:
            self._ensure_healthy()
            for record in self._pending.values():
                if validate_admission_receipt(record, candidate):
                    return json.loads(_bytes(record))
        return None

    def put(self, candidate: Mapping[str, Any], *, first_eligible_slot: int) -> dict:
        public = _public_candidate(candidate)
        record = {"schema": SCHEMA, "candidate": public,
                  "first_eligible_slot": first_eligible_slot}
        record["receipt_id"] = _digest(record)
        if not validate_admission_receipt(record):
            raise AdmissionInboxError("ADMISSION_RECEIPT_INVALID")
        with self._lock:
            self._ensure_healthy()
            prior = self.receipt_for(candidate)
            if prior is not None:
                return prior
            if any(r["candidate"]["token_mint"] == public["token_mint"]
                   for r in self._pending.values()):
                raise AdmissionInboxError("ADMISSION_IDENTITY_CONFLICT")
            if len(self._pending) >= self.max_pending:
                raise AdmissionInboxError("ADMISSION_INBOX_FULL")
            self._commit({**self._pending, record["receipt_id"]: record})
            return json.loads(_bytes(record))

    def acknowledge_checkpoint(self, receipts: list[dict]) -> None:
        """Called only after a watch checkpoint write has been verified."""
        with self._lock:
            self._ensure_healthy()
            records = dict(self._pending)
            for receipt in receipts:
                if (validate_admission_receipt(receipt) and
                        records.get(receipt["receipt_id"]) == receipt):
                    records.pop(receipt["receipt_id"])
            if records != self._pending:
                self._commit(records)

    def snapshot(self) -> dict:
        with self._lock:
            return {"pending": len(self._pending), "capacity": self.max_pending,
                    "generation": self._generation, "reload_required": self._poisoned}
