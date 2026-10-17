"""Canonical Pump migration census and deterministic reserve 1.20x tracker.

The authenticated census is the dedupe authority shared by live Yellowstone
discovery and confirmed-RPC reconciliation.  A migration is identified by its
sealed canonical proof, not by observation time.  The tracker consumes only
canonical PumpSwap reserve artifacts and uses exact :class:`~decimal.Decimal`
arithmetic; token market-provider indexing is not part of the crossing fact.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer.durable_state import AuthenticatedSingletonStore
from PHX2.free_tier_producer.migration_admission import (
    MigrationProofSnapshot,
    validate_migration_proof,
)
from PHX2.free_tier_producer.pumpswap_reserves import effective_quote_reserves
from PHX2.free_tier_producer.phx1_structural_policy import (
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    policy_metadata_for_filter_results,
)


CHECKPOINT_KIND_MIGRATION_CENSUS = "PHX2_MIGRATION_CENSUS"
MIGRATION_CENSUS_SCHEMA_V1 = "phx2_migration_census_v1"
MIGRATION_CENSUS_RECORD_KIND = "PHX2_MIGRATION_CENSUS_STATE"
MIGRATION_CENSUS_CHECKPOINT_BASENAME = "migration_census_checkpoint.json"

MIGRATION_CENSUS_BASENAME = "migration_census.jsonl"
MIGRATION_120X_OUTCOMES_BASENAME = "migration_1_20x_outcomes.jsonl"
MIGRATION_120X_CROSSINGS_BASENAME = "migration_1_20x_crossings.jsonl"
MIGRATION_120X_SUMMARY_BASENAME = "migration_1_20x_summary.json"
PHX1_FILTER_RESULTS_BASENAME = "phx1_filter_results.jsonl"
PHX1_FILTER_SUMMARY_BASENAME = "phx1_filter_summary.json"

DISCOVERY_SOURCE_LIVE_GRPC = "LIVE_GRPC"
DISCOVERY_SOURCE_LIVE_HELIUS = "LIVE_HELIUS"
DISCOVERY_SOURCE_RPC_RECONCILIATION = "RPC_RECONCILIATION"
DISCOVERY_SOURCE_BOTH = "BOTH"
DISCOVERY_SOURCES = frozenset(
    {
        DISCOVERY_SOURCE_LIVE_GRPC,
        DISCOVERY_SOURCE_LIVE_HELIUS,
        DISCOVERY_SOURCE_RPC_RECONCILIATION,
        DISCOVERY_SOURCE_BOTH,
    }
)

OUTCOME_PENDING_WITH_DEADLINE = "PENDING_WITH_DEADLINE"
OUTCOME_REACHED_1_20X = "REACHED_1_20X"
OUTCOME_NEVER_REACHED_1_20X = "NEVER_REACHED_1_20X"
OUTCOME_STRUCTURAL_COLLAPSE = "STRUCTURAL_COLLAPSE"
OUTCOME_LIQUIDITY_LOST = "LIQUIDITY_LOST"
OUTCOME_EXPIRED = "EXPIRED"
OUTCOME_DATA_GAP_UNRESOLVED = "DATA_GAP_UNRESOLVED"
TRACKER_OUTCOMES = frozenset(
    {
        OUTCOME_PENDING_WITH_DEADLINE,
        OUTCOME_REACHED_1_20X,
        OUTCOME_NEVER_REACHED_1_20X,
        OUTCOME_STRUCTURAL_COLLAPSE,
        OUTCOME_LIQUIDITY_LOST,
        OUTCOME_EXPIRED,
        OUTCOME_DATA_GAP_UNRESOLVED,
    }
)
TRACKER_TERMINAL_OUTCOMES = TRACKER_OUTCOMES - {
    OUTCOME_PENDING_WITH_DEADLINE
}

ACTIVATION_MULTIPLIER = Decimal("1.20")
DEFAULT_WATCH_EXPIRY_SECONDS = 3600
WATCH_DEADLINE_SOURCE = (
    "PHX2.free_tier_producer.free_tier_session:"
    "--max-candidate-age-seconds(default=3600)"
)
CANONICAL_CROSSING_SOURCE = "PUMPSWAP_CANONICAL_EFFECTIVE_RESERVES"
CANONICAL_MARKET_CAP_UNIT = "QUOTE_TOKEN"


class MigrationCensusError(RuntimeError):
    """The census refused an inconsistent or non-durable mutation."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("DECIMAL_TEXT_REQUIRED")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DECIMAL_INVALID") from exc
    if not result.is_finite():
        raise ValueError("DECIMAL_NON_FINITE")
    return result


def _dtext(value: object) -> str:
    return format(_decimal(value), "f")


def _integer_amount(name: str, value: object) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise MigrationCensusError(f"{name}_INVALID")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value:
        negative = value.startswith("-")
        digits = value[1:] if negative else value
        if digits.isdigit() and (digits == "0" or not digits.startswith("0")):
            return int(value)
    raise MigrationCensusError(f"{name}_INVALID")

def _parse_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_migration_identity(proof: MigrationProofSnapshot) -> str:
    valid, reason = validate_migration_proof(proof)
    if not valid:
        raise ValueError(reason or "MIGRATION_PROOF_INVALID")
    return _sha256(
        {
            "identity_version": "phx2_canonical_migration_identity_v1",
            "mint": proof.candidate_mint,
            "pool": proof.pool,
            "migration_slot": int(proof.migration_slot),
            "migration_signature": proof.migration_signature,
            "outer_instruction_index": int(proof.outer_instruction_index),
            "inner_instruction_index": int(proof.inner_instruction_index),
            "flattened_instruction_index": int(
                proof.flattened_instruction_index
            ),
            "migration_version": proof.migration_instruction_version,
        }
    )


def _deadline(
    proof: MigrationProofSnapshot,
    *,
    migration_block_time: Optional[int],
    watch_expiry_seconds: int,
) -> Tuple[Optional[str], str]:
    anchor: Optional[datetime] = None
    if (
        isinstance(migration_block_time, int)
        and not isinstance(migration_block_time, bool)
        and migration_block_time >= 0
    ):
        anchor = datetime.fromtimestamp(
            migration_block_time, tz=timezone.utc
        )
    if anchor is None:
        anchor = _parse_utc(proof.observed_at_utc)
    if anchor is None:
        return None, WATCH_DEADLINE_SOURCE
    return (
        _utc_text(anchor + timedelta(seconds=int(watch_expiry_seconds))),
        WATCH_DEADLINE_SOURCE,
    )


def _source_union(existing: str, incoming: str) -> str:
    if incoming not in (
        DISCOVERY_SOURCE_LIVE_GRPC,
        DISCOVERY_SOURCE_LIVE_HELIUS,
        DISCOVERY_SOURCE_RPC_RECONCILIATION,
    ):
        raise ValueError("DISCOVERY_SOURCE_INVALID")
    if existing == incoming:
        return existing
    if existing in DISCOVERY_SOURCES:
        return DISCOVERY_SOURCE_BOTH
    return incoming


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    max_attempts = max(
        1, int(getattr(_cpe, "CHECKPOINT_WRITE_MAX_ATTEMPTS", 4))
    )
    for attempt in range(1, max_attempts + 1):
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            return
        except OSError:
            if attempt >= max_attempts:
                raise
            time.sleep(
                min(
                    float(getattr(
                        _cpe, "CHECKPOINT_WRITE_RETRY_MAX_SECONDS", 0.08
                    )),
                    float(getattr(
                        _cpe, "CHECKPOINT_WRITE_RETRY_BASE_SECONDS", 0.01
                    )) * float(attempt),
                )
            )

def _jsonl(records: Iterable[Mapping[str, Any]]) -> str:
    lines = [_canonical_json(dict(record)) for record in records]
    return ("\n".join(lines) + "\n") if lines else ""


def _base_census_record(
    proof: MigrationProofSnapshot,
    *,
    source: str,
    first_seen_utc: str,
    migration_block_time: Optional[int],
    reconciliation_range: Optional[Tuple[int, int]],
    watch_expiry_seconds: int,
) -> Dict[str, Any]:
    census_identity = canonical_migration_identity(proof)
    deadline_utc, deadline_source = _deadline(
        proof,
        migration_block_time=migration_block_time,
        watch_expiry_seconds=watch_expiry_seconds,
    )
    return {
        "record_kind": "PHX2_CANONICAL_MIGRATION",
        "census_identity": census_identity,
        "mint": proof.candidate_mint,
        "canonical_pool": proof.pool,
        "migration_slot": int(proof.migration_slot),
        "migration_block_time": migration_block_time,
        "migration_version": proof.migration_instruction_version,
        "canonical_migration_proof_digest": proof.proof_digest,
        "canonical_pda_result": bool(proof.canonical_pda_valid),
        "vault_derivation_result": bool(proof.vault_derivation_valid),
        "vault_ownership_result": bool(proof.vault_ownership_valid),
        "migration_signature_digest": hashlib.sha256(proof.migration_signature.encode("utf-8")).hexdigest(),
        "quote_mint": proof.quote_mint,
        "base_vault": proof.base_vault,
        "quote_vault": proof.quote_vault,
        "migration_market_cap_baseline": None,
        "migration_market_cap_unit": CANONICAL_MARKET_CAP_UNIT,
        "initial_canonical_reserves": None,
        "raw_quote_reserves": None,
        "virtual_quote_reserves": None,
        "effective_quote_reserves": None,
        "discovery_source": source,
        "first_seen_utc": first_seen_utc,
        "reconciliation_ranges": (
            []
            if reconciliation_range is None
            else [
                {
                    "start_slot": int(reconciliation_range[0]),
                    "end_slot": int(reconciliation_range[1]),
                }
            ]
        ),
        "current_1_20x_tracking_state": OUTCOME_PENDING_WITH_DEADLINE,
        "phx1_structural_filter_status": "PENDING_1_20X",
        "watch_deadline_utc": deadline_utc,
        "watch_deadline_seconds": int(watch_expiry_seconds),
        "watch_deadline_source": deadline_source,
    }


def _base_tracker_record(census: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "record_kind": "PHX2_MIGRATION_1_20X_OUTCOME",
        "census_identity": census["census_identity"],
        "mint": census["mint"],
        "canonical_pool": census["canonical_pool"],
        "migration_slot": int(census["migration_slot"]),
        "migration_baseline": None,
        "market_cap_unit": CANONICAL_MARKET_CAP_UNIT,
        "activation_multiplier": _dtext(ACTIVATION_MULTIPLIER),
        "activation_target_market_cap": None,
        "baseline_slot": None,
        "baseline_timestamp": None,
        "baseline_reserves": None,
        "first_crossing_slot": None,
        "first_crossing_timestamp": None,
        "crossing_reserves": None,
        "crossing_market_cap": None,
        "crossing_source": None,
        "crossing_proof": None,
        "highest_canonical_market_cap": None,
        "highest_canonical_market_cap_slot": None,
        "outcome": OUTCOME_PENDING_WITH_DEADLINE,
        "watch_deadline_utc": census.get("watch_deadline_utc"),
        "watch_deadline_seconds": census.get("watch_deadline_seconds"),
        "watch_deadline_source": census.get("watch_deadline_source"),
        "observations": 0,
        "last_observation_slot": None,
        "last_observation_timestamp": None,
        "last_observation_evidence_digest": None,
        "data_gap_reason": None,
    }


def validate_migration_census_state(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    if record.get("record_kind") != MIGRATION_CENSUS_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    census = record.get("census_records")
    tracker = record.get("tracker_records")
    filters = record.get("filter_results")
    if not isinstance(census, list) or not isinstance(tracker, list):
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    if not isinstance(filters, list):
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    identities: set[str] = set()
    mints: set[str] = set()
    for item in census:
        if not isinstance(item, Mapping):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        identity = item.get("census_identity")
        mint = item.get("mint")
        if (
            not _cpe.is_sha256_digest(identity)
            or not isinstance(mint, str)
            or not mint
            or identity in identities
            or mint in mints
            or item.get("discovery_source") not in DISCOVERY_SOURCES
        ):
            return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
        identities.add(identity)
        mints.add(mint)
    tracker_ids: set[str] = set()
    for item in tracker:
        if not isinstance(item, Mapping):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        identity = item.get("census_identity")
        if (
            identity not in identities
            or identity in tracker_ids
            or item.get("outcome") not in TRACKER_OUTCOMES
        ):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        tracker_ids.add(identity)
    if tracker_ids != identities:
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    for name in (
        "duplicate_migrations_suppressed",
        "duplicate_candidate_applications_suppressed",
        "census_insertions",
        "source_upgrades",
    ):
        value = record.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if not _cpe.record_digest_is_valid(
        CHECKPOINT_KIND_MIGRATION_CENSUS, record
    ):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    return True, ""


def migration_census_state_identity(
    record: Mapping[str, Any],
) -> Tuple[str]:
    if record.get("record_kind") != MIGRATION_CENSUS_RECORD_KIND:
        raise ValueError("MIGRATION_CENSUS_RECORD_KIND_INVALID")
    return (MIGRATION_CENSUS_RECORD_KIND,)


class MigrationCensusStore(AuthenticatedSingletonStore):
    """Authenticated union census plus one explicit tracker state per item."""

    checkpoint_kind = CHECKPOINT_KIND_MIGRATION_CENSUS
    schema_version = MIGRATION_CENSUS_SCHEMA_V1
    record_kind = MIGRATION_CENSUS_RECORD_KIND

    def __init__(
        self,
        *,
        state_dir: object,
        artifact_dir: Optional[object] = None,
        watch_expiry_seconds: int = DEFAULT_WATCH_EXPIRY_SECONDS,
        basename: str = MIGRATION_CENSUS_CHECKPOINT_BASENAME,
    ) -> None:
        if (
            isinstance(watch_expiry_seconds, bool)
            or not isinstance(watch_expiry_seconds, int)
            or watch_expiry_seconds <= 0
        ):
            raise ValueError("WATCH_EXPIRY_SECONDS_INVALID")
        super().__init__(primary_path=Path(state_dir) / basename)
        self._artifact_dir = (
            Path(artifact_dir) if artifact_dir is not None else None
        )
        self._watch_expiry_seconds = int(watch_expiry_seconds)
        self._census: Dict[str, Dict[str, Any]] = {}
        self._mint_to_identity: Dict[str, str] = {}
        self._tracker: Dict[str, Dict[str, Any]] = {}
        self._filter_results: Dict[str, Dict[str, Any]] = {}
        self._duplicate_migrations_suppressed = 0
        self._duplicate_candidate_applications_suppressed = 0
        self._census_insertions = 0
        self._source_upgrades = 0
        self._mutation_lock = threading.RLock()

    def classify(self, path: object) -> _cpe.FileClassification:
        return _cpe.classify_checkpoint_file(
            path,
            kind=self.checkpoint_kind,
            supported_schema_versions=(self.schema_version,),
            record_validator=validate_migration_census_state,
            identity_fn=migration_census_state_identity,
        )

    def restore_record(self, record: Mapping[str, Any]) -> None:
        self._census = {
            str(item["census_identity"]): dict(item)
            for item in record.get("census_records") or []
        }
        self._mint_to_identity = {
            str(item["mint"]): str(item["census_identity"])
            for item in self._census.values()
        }
        self._tracker = {
            str(item["census_identity"]): dict(item)
            for item in record.get("tracker_records") or []
        }
        self._filter_results = {
            str(item["census_identity"]): dict(item)
            for item in record.get("filter_results") or []
        }
        self._duplicate_migrations_suppressed = int(
            record.get("duplicate_migrations_suppressed") or 0
        )
        self._duplicate_candidate_applications_suppressed = int(
            record.get("duplicate_candidate_applications_suppressed") or 0
        )
        self._census_insertions = int(
            record.get("census_insertions") or 0
        )
        self._source_upgrades = int(record.get("source_upgrades") or 0)

    def current_record(self) -> Dict[str, Any]:
        return {
            "record_kind": MIGRATION_CENSUS_RECORD_KIND,
            "census_records": sorted(
                (dict(item) for item in self._census.values()),
                key=lambda item: (
                    int(item["migration_slot"]),
                    str(item["census_identity"]),
                ),
            ),
            "tracker_records": sorted(
                (dict(item) for item in self._tracker.values()),
                key=lambda item: (
                    int(item["migration_slot"]),
                    str(item["census_identity"]),
                ),
            ),
            "filter_results": sorted(
                (dict(item) for item in self._filter_results.values()),
                key=lambda item: str(item["census_identity"]),
            ),
            "duplicate_migrations_suppressed": int(
                self._duplicate_migrations_suppressed
            ),
            "duplicate_candidate_applications_suppressed": int(
                self._duplicate_candidate_applications_suppressed
            ),
            "census_insertions": int(self._census_insertions),
            "source_upgrades": int(self._source_upgrades),
        }

    def _persist_all_locked(self) -> None:
        self._persist_record_locked(self.current_record())
        self._write_artifacts_locked()

    def register_migration(
        self,
        proof: MigrationProofSnapshot,
        *,
        discovery_source: str,
        migration_block_time: Optional[int] = None,
        reconciliation_range: Optional[Tuple[int, int]] = None,
        first_seen_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        valid, reason = validate_migration_proof(proof)
        if not valid:
            raise MigrationCensusError(reason or "MIGRATION_PROOF_INVALID")
        if discovery_source not in (
            DISCOVERY_SOURCE_LIVE_GRPC,
            DISCOVERY_SOURCE_LIVE_HELIUS,
            DISCOVERY_SOURCE_RPC_RECONCILIATION,
        ):
            raise MigrationCensusError("DISCOVERY_SOURCE_INVALID")
        identity = canonical_migration_identity(proof)
        with self._mutation_lock, self._lock:
            existing_mint_identity = self._mint_to_identity.get(
                proof.candidate_mint
            )
            if (
                existing_mint_identity is not None
                and existing_mint_identity != identity
            ):
                raise MigrationCensusError(
                    "CANONICAL_MIGRATION_IDENTITY_CONFLICT"
                )
            existing = self._census.get(identity)
            if existing is not None:
                self._duplicate_migrations_suppressed += 1
                updated = dict(existing)
                union = _source_union(
                    str(existing["discovery_source"]), discovery_source
                )
                source_upgraded = union != existing["discovery_source"]
                updated["discovery_source"] = union
                if reconciliation_range is not None:
                    row = {
                        "start_slot": int(reconciliation_range[0]),
                        "end_slot": int(reconciliation_range[1]),
                    }
                    ranges = list(updated.get("reconciliation_ranges") or [])
                    if row not in ranges:
                        ranges.append(row)
                    updated["reconciliation_ranges"] = ranges
                if source_upgraded:
                    self._source_upgrades += 1
                self._census[identity] = updated
                self._persist_all_locked()
                return {
                    "inserted": False,
                    "source_upgraded": source_upgraded,
                    "census_identity": identity,
                    "discovery_source": union,
                }
            now = first_seen_utc or _cpe.utc_now_iso()
            census = _base_census_record(
                proof,
                source=discovery_source,
                first_seen_utc=now,
                migration_block_time=migration_block_time,
                reconciliation_range=reconciliation_range,
                watch_expiry_seconds=self._watch_expiry_seconds,
            )
            self._census[identity] = census
            self._mint_to_identity[proof.candidate_mint] = identity
            self._tracker[identity] = _base_tracker_record(census)
            self._census_insertions += 1
            try:
                self._persist_all_locked()
            except Exception:
                self._census.pop(identity, None)
                self._mint_to_identity.pop(proof.candidate_mint, None)
                self._tracker.pop(identity, None)
                self._census_insertions -= 1
                raise
            return {
                "inserted": True,
                "source_upgraded": False,
                "census_identity": identity,
                "discovery_source": discovery_source,
            }

    def note_duplicate_candidate_application(self) -> None:
        with self._mutation_lock, self._lock:
            self._duplicate_candidate_applications_suppressed += 1
            self._persist_all_locked()

    def observe_canonical_reserve(
        self,
        *,
        mint: str,
        pool: str,
        slot: int,
        observed_at_utc: str,
        raw_quote_reserves: object,
        virtual_quote_reserves: object,
        effective_quote_reserves_value: object,
        base_reserves: object,
        base_supply: object,
        base_decimals: int,
        quote_decimals: int,
        source_evidence_digest: str,
        quote_price_usd: Optional[object] = None,
    ) -> Dict[str, Any]:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise MigrationCensusError("RESERVE_SLOT_INVALID")
        identity = self._mint_to_identity.get(str(mint))
        if identity is None:
            return {"accepted": False, "reason": "CENSUS_MINT_UNKNOWN"}
        raw_quote = _integer_amount(
            "RAW_QUOTE_RESERVES", raw_quote_reserves
        )
        virtual_quote = _integer_amount(
            "VIRTUAL_QUOTE_RESERVES", virtual_quote_reserves
        )
        supplied_effective = _integer_amount(
            "EFFECTIVE_QUOTE_RESERVES",
            effective_quote_reserves_value,
        )
        expected_effective = effective_quote_reserves(
            raw_quote, virtual_quote
        )
        if supplied_effective != expected_effective:
            raise MigrationCensusError("EFFECTIVE_QUOTE_RESERVE_MISMATCH")
        if (
            isinstance(base_decimals, bool)
            or not isinstance(base_decimals, int)
            or base_decimals < 0
            or isinstance(quote_decimals, bool)
            or not isinstance(quote_decimals, int)
            or quote_decimals < 0
        ):
            raise MigrationCensusError("RESERVE_DECIMALS_INVALID")
        base = _integer_amount("BASE_RESERVES", base_reserves)
        supply = _integer_amount("BASE_SUPPLY", base_supply)
        if base <= 0 or supply <= 0:
            raise MigrationCensusError("RESERVE_BASE_OR_SUPPLY_INVALID")
        price_quote = (
            Decimal(expected_effective) / (Decimal(10) ** quote_decimals)
        ) / (Decimal(base) / (Decimal(10) ** base_decimals))
        whole_supply = Decimal(supply) / (Decimal(10) ** base_decimals)
        market_cap_quote = price_quote * whole_supply
        market_cap_usd: Optional[Decimal] = None
        if quote_price_usd is not None:
            market_cap_usd = market_cap_quote * _decimal(quote_price_usd)
        reserves = {
            "raw_quote_reserves": str(raw_quote),
            "virtual_quote_reserves": str(virtual_quote),
            "effective_quote_reserves": str(supplied_effective),
            "base_reserves": str(base),
            "base_supply": str(supply),
            "base_decimals": int(base_decimals),
            "quote_decimals": int(quote_decimals),
        }
        with self._mutation_lock, self._lock:
            census = dict(self._census[identity])
            tracker = dict(self._tracker[identity])
            if census["canonical_pool"] != pool:
                raise MigrationCensusError("NONCANONICAL_POOL_RESERVE")
            if slot < int(census["migration_slot"]):
                raise MigrationCensusError("PRE_MIGRATION_RESERVE")
            observed_time = _parse_utc(observed_at_utc)
            deadline_time = _parse_utc(tracker.get("watch_deadline_utc"))
            if (
                observed_time is None
                or (deadline_time is not None and observed_time > deadline_time)
            ):
                return {
                    "accepted": False,
                    "reason": (
                        "RESERVE_TIMESTAMP_INVALID"
                        if observed_time is None
                        else "AFTER_WATCH_DEADLINE"
                    ),
                    "outcome": tracker["outcome"],
                }
            if tracker["outcome"] in TRACKER_TERMINAL_OUTCOMES:
                return {
                    "accepted": False,
                    "reason": "TRACKER_TERMINAL",
                    "outcome": tracker["outcome"],
                }
            if (
                tracker.get("last_observation_evidence_digest")
                == source_evidence_digest
            ):
                # A required write may have succeeded while the enclosing
                # transaction cursor was still held. Replaying that exact
                # reserve event heals every durable projection without
                # counting the observation or crossing twice.
                self._persist_all_locked()
                return {
                    "accepted": False,
                    "reason": "DUPLICATE_RESERVE_OBSERVATION",
                    "outcome": tracker["outcome"],
                }
            tracker["observations"] = int(tracker["observations"]) + 1
            tracker["last_observation_slot"] = int(slot)
            tracker["last_observation_timestamp"] = observed_at_utc
            tracker["last_observation_evidence_digest"] = (
                source_evidence_digest
            )
            baseline_created = tracker["migration_baseline"] is None
            if baseline_created:
                tracker["migration_baseline"] = _dtext(market_cap_quote)
                tracker["activation_target_market_cap"] = _dtext(
                    market_cap_quote * ACTIVATION_MULTIPLIER
                )
                tracker["baseline_slot"] = int(slot)
                tracker["baseline_timestamp"] = observed_at_utc
                tracker["baseline_reserves"] = reserves
                census["migration_market_cap_baseline"] = _dtext(
                    market_cap_quote
                )
                census["initial_canonical_reserves"] = reserves
                census["raw_quote_reserves"] = reserves[
                    "raw_quote_reserves"
                ]
                census["virtual_quote_reserves"] = reserves[
                    "virtual_quote_reserves"
                ]
                census["effective_quote_reserves"] = reserves[
                    "effective_quote_reserves"
                ]
            highest = tracker.get("highest_canonical_market_cap")
            if highest is None or market_cap_quote > _decimal(highest):
                tracker["highest_canonical_market_cap"] = _dtext(
                    market_cap_quote
                )
                tracker["highest_canonical_market_cap_slot"] = int(slot)
            crossed = False
            if not baseline_created:
                target = _decimal(tracker["activation_target_market_cap"])
                if market_cap_quote >= target:
                    crossed = True
                    proof_payload = {
                        "proof_version": "phx2_migration_1_20x_crossing_v1",
                        "census_identity": identity,
                        "mint": mint,
                        "pool": pool,
                        "slot": int(slot),
                        "observed_at_utc": observed_at_utc,
                        "market_cap_quote": _dtext(market_cap_quote),
                        "market_cap_usd": (
                            None
                            if market_cap_usd is None
                            else _dtext(market_cap_usd)
                        ),
                        "target_market_cap_quote": tracker[
                            "activation_target_market_cap"
                        ],
                        "reserves": reserves,
                        "source": CANONICAL_CROSSING_SOURCE,
                        "source_evidence_digest": source_evidence_digest,
                    }
                    tracker["first_crossing_slot"] = int(slot)
                    tracker["first_crossing_timestamp"] = observed_at_utc
                    tracker["crossing_reserves"] = reserves
                    tracker["crossing_market_cap"] = _dtext(market_cap_quote)
                    tracker["crossing_source"] = CANONICAL_CROSSING_SOURCE
                    tracker["crossing_proof"] = {
                        **proof_payload,
                        "proof_digest": _sha256(proof_payload),
                    }
                    tracker["outcome"] = OUTCOME_REACHED_1_20X
                    census[
                        "current_1_20x_tracking_state"
                    ] = OUTCOME_REACHED_1_20X
                    census[
                        "phx1_structural_filter_status"
                    ] = "PENDING_EVALUATION"
            self._census[identity] = census
            self._tracker[identity] = tracker
            self._persist_all_locked()
            return {
                "accepted": True,
                "baseline_created": baseline_created,
                "crossed": crossed,
                "outcome": tracker["outcome"],
                "census_identity": identity,
                "market_cap_quote": _dtext(market_cap_quote),
                "market_cap_usd": (
                    None
                    if market_cap_usd is None
                    else _dtext(market_cap_usd)
                ),
            }

    def mark_outcome(
        self,
        *,
        census_identity: str,
        outcome: str,
        reason: Optional[str] = None,
    ) -> None:
        if outcome not in TRACKER_OUTCOMES:
            raise ValueError("TRACKER_OUTCOME_INVALID")
        with self._mutation_lock, self._lock:
            tracker = dict(self._tracker[census_identity])
            census = dict(self._census[census_identity])
            if tracker["outcome"] == OUTCOME_REACHED_1_20X:
                return
            tracker["outcome"] = outcome
            if outcome == OUTCOME_DATA_GAP_UNRESOLVED:
                tracker["data_gap_reason"] = reason
            census["current_1_20x_tracking_state"] = outcome
            self._tracker[census_identity] = tracker
            self._census[census_identity] = census
            self._persist_all_locked()

    def expire_due(self, *, now_utc: str) -> int:
        now = _parse_utc(now_utc)
        if now is None:
            raise ValueError("NOW_UTC_INVALID")
        changed = 0
        with self._mutation_lock, self._lock:
            for identity, current in list(self._tracker.items()):
                if current["outcome"] != OUTCOME_PENDING_WITH_DEADLINE:
                    continue
                deadline = _parse_utc(current.get("watch_deadline_utc"))
                if deadline is None or now < deadline:
                    continue
                tracker = dict(current)
                census = dict(self._census[identity])
                # The exact observation horizon ended with complete reserve
                # evidence and no crossing. EXPIRED is the explicit canonical
                # state; NEVER_REACHED is reserved for downstream reporting
                # that can additionally prove the entire horizon.
                tracker["outcome"] = OUTCOME_EXPIRED
                census["current_1_20x_tracking_state"] = OUTCOME_EXPIRED
                self._tracker[identity] = tracker
                self._census[identity] = census
                changed += 1
            if changed:
                self._persist_all_locked()
        return changed

    def finalize_complete_horizons(
        self, *, coverage_through_utc: str
    ) -> int:
        """Close only horizons proven completely observed through their deadline.

        Wall-clock passage alone is not coverage. The caller must supply the
        timestamp of the last fully reconciled produced block. A horizon with
        no canonical reserve observation is an explicit data gap; an observed
        horizon with no crossing becomes NEVER_REACHED_1_20X.
        """

        coverage = _parse_utc(coverage_through_utc)
        if coverage is None:
            raise ValueError("COVERAGE_THROUGH_UTC_INVALID")
        changed = 0
        with self._mutation_lock, self._lock:
            for identity, current in list(self._tracker.items()):
                if current["outcome"] != OUTCOME_PENDING_WITH_DEADLINE:
                    continue
                deadline = _parse_utc(current.get("watch_deadline_utc"))
                if deadline is None or coverage < deadline:
                    continue
                tracker = dict(current)
                census = dict(self._census[identity])
                if int(tracker.get("observations") or 0) > 0:
                    outcome = OUTCOME_NEVER_REACHED_1_20X
                else:
                    outcome = OUTCOME_DATA_GAP_UNRESOLVED
                    tracker["data_gap_reason"] = (
                        "NO_CANONICAL_RESERVE_OBSERVATION_IN_COMPLETE_HORIZON"
                    )
                tracker["outcome"] = outcome
                census["current_1_20x_tracking_state"] = outcome
                self._tracker[identity] = tracker
                self._census[identity] = census
                changed += 1
            if changed:
                self._persist_all_locked()
        return changed

    def record_filter_results(
        self,
        *,
        census_identity: str,
        results: List[Mapping[str, Any]],
        final_verdict: str,
        evaluated_at_utc: Optional[str] = None,
        phx1_structural_policy: str = PHX1_STRUCTURAL_POLICY_ENFORCE,
    ) -> None:
        with self._mutation_lock, self._lock:
            if census_identity not in self._census:
                raise KeyError(census_identity)
            policy_metadata = policy_metadata_for_filter_results(
                results, policy_mode=phx1_structural_policy)
            record = {
                "record_kind": "PHX2_PHX1_STRUCTURAL_FILTER_RESULT_SET",
                "census_identity": census_identity,
                "mint": self._census[census_identity]["mint"],
                "evaluated_at_utc": (
                    evaluated_at_utc or _cpe.utc_now_iso()
                ),
                "results": [dict(item) for item in results],
                "original_filter_results": [dict(item) for item in results],
                "final_verdict": final_verdict,
                **policy_metadata,
            }
            record["result_set_digest"] = _sha256(record)
            self._filter_results[census_identity] = record
            census = dict(self._census[census_identity])
            census["phx1_structural_filter_status"] = final_verdict
            self._census[census_identity] = census
            self._persist_all_locked()

    def get_by_mint(self, mint: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            identity = self._mint_to_identity.get(str(mint))
            return (
                None
                if identity is None
                else dict(self._census[identity])
            )

    def get_tracker_by_mint(self, mint: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            identity = self._mint_to_identity.get(str(mint))
            return (
                None
                if identity is None
                else dict(self._tracker[identity])
            )

    def records(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(
                dict(item)
                for item in sorted(
                    self._census.values(),
                    key=lambda item: (
                        int(item["migration_slot"]),
                        str(item["census_identity"]),
                    ),
                )
            )

    def tracker_records(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(
                dict(item)
                for item in sorted(
                    self._tracker.values(),
                    key=lambda item: (
                        int(item["migration_slot"]),
                        str(item["census_identity"]),
                    ),
                )
            )

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            outcomes: Dict[str, int] = {
                outcome: 0 for outcome in sorted(TRACKER_OUTCOMES)
            }
            for item in self._tracker.values():
                outcomes[str(item["outcome"])] += 1
            sources = {source: 0 for source in sorted(DISCOVERY_SOURCES)}
            for item in self._census.values():
                sources[str(item["discovery_source"])] += 1
            filter_verdicts: Dict[str, int] = {}
            for item in self._filter_results.values():
                verdict = str(item.get("final_verdict") or "UNKNOWN")
                filter_verdicts[verdict] = filter_verdicts.get(verdict, 0) + 1
            crossing_ids = {
                str(item["census_identity"])
                for item in self._tracker.values()
                if item["outcome"] == OUTCOME_REACHED_1_20X
            }
            return {
                "census_records": len(self._census),
                "tracker_records": len(self._tracker),
                "outcomes": outcomes,
                "discovery_sources": sources,
                "duplicate_migrations_suppressed": (
                    self._duplicate_migrations_suppressed
                ),
                "duplicate_candidate_applications_suppressed": (
                    self._duplicate_candidate_applications_suppressed
                ),
                "census_insertions": self._census_insertions,
                "source_upgrades": self._source_upgrades,
                "structural_filter_result_sets": len(self._filter_results),
                "structural_filter_verdicts": filter_verdicts,
                "crossing_candidates_pending_filter_evaluation": len(
                    crossing_ids - set(self._filter_results)
                ),
                "checkpoint_generation": self.generation,
                "checkpoint_quarantined": self.quarantined,
            }

    def _write_artifacts_locked(self) -> None:
        if self._artifact_dir is None:
            return
        census = sorted(
            self._census.values(),
            key=lambda item: (
                int(item["migration_slot"]),
                str(item["census_identity"]),
            ),
        )
        tracker = sorted(
            self._tracker.values(),
            key=lambda item: (
                int(item["migration_slot"]),
                str(item["census_identity"]),
            ),
        )
        crossings = [
            item
            for item in tracker
            if item["outcome"] == OUTCOME_REACHED_1_20X
        ]
        _atomic_text(
            self._artifact_dir / MIGRATION_CENSUS_BASENAME,
            _jsonl(census),
        )
        _atomic_text(
            self._artifact_dir / MIGRATION_120X_OUTCOMES_BASENAME,
            _jsonl(tracker),
        )
        _atomic_text(
            self._artifact_dir / MIGRATION_120X_CROSSINGS_BASENAME,
            _jsonl(crossings),
        )
        _atomic_text(
            self._artifact_dir / MIGRATION_120X_SUMMARY_BASENAME,
            _canonical_json(self.summary()) + "\n",
        )
        filter_results = sorted(
            self._filter_results.values(),
            key=lambda item: str(item["census_identity"]),
        )
        filter_verdicts: Dict[str, int] = {}
        effective_policy_verdicts: Dict[str, int] = {}
        policy_modes: Dict[str, int] = {}
        for item in filter_results:
            verdict = str(item.get("final_verdict") or "UNKNOWN")
            filter_verdicts[verdict] = filter_verdicts.get(verdict, 0) + 1
            effective = str(item.get("effective_phx1_policy_verdict") or "UNKNOWN")
            effective_policy_verdicts[effective] = (
                effective_policy_verdicts.get(effective, 0) + 1)
            policy_mode = str(item.get("policy_mode") or "UNKNOWN")
            policy_modes[policy_mode] = policy_modes.get(policy_mode, 0) + 1
        crossing_ids = {
            str(item["census_identity"])
            for item in tracker
            if item["outcome"] == OUTCOME_REACHED_1_20X
        }
        _atomic_text(
            self._artifact_dir / PHX1_FILTER_RESULTS_BASENAME,
            _jsonl(filter_results),
        )
        _atomic_text(
            self._artifact_dir / PHX1_FILTER_SUMMARY_BASENAME,
            _canonical_json({
                "kind": "PHX2_CENSUS_PHX1_FILTER_SUMMARY",
                "crossing_candidates": len(crossing_ids),
                "evaluated_result_sets": len(filter_results),
                "pending_crossing_evaluations": len(
                    crossing_ids - set(self._filter_results)
                ),
                "final_verdicts": filter_verdicts,
                "effective_phx1_policy_verdicts": effective_policy_verdicts,
                "phx1_structural_policy_modes": policy_modes,
            }) + "\n",
        )


__all__ = (
    "CHECKPOINT_KIND_MIGRATION_CENSUS",
    "MIGRATION_CENSUS_SCHEMA_V1",
    "MIGRATION_CENSUS_RECORD_KIND",
    "MIGRATION_CENSUS_CHECKPOINT_BASENAME",
    "MIGRATION_CENSUS_BASENAME",
    "MIGRATION_120X_OUTCOMES_BASENAME",
    "MIGRATION_120X_CROSSINGS_BASENAME",
    "MIGRATION_120X_SUMMARY_BASENAME",
    "PHX1_FILTER_RESULTS_BASENAME",
    "PHX1_FILTER_SUMMARY_BASENAME",
    "DISCOVERY_SOURCE_LIVE_GRPC",
    "DISCOVERY_SOURCE_LIVE_HELIUS",
    "DISCOVERY_SOURCE_RPC_RECONCILIATION",
    "DISCOVERY_SOURCE_BOTH",
    "OUTCOME_PENDING_WITH_DEADLINE",
    "OUTCOME_REACHED_1_20X",
    "OUTCOME_NEVER_REACHED_1_20X",
    "OUTCOME_STRUCTURAL_COLLAPSE",
    "OUTCOME_LIQUIDITY_LOST",
    "OUTCOME_EXPIRED",
    "OUTCOME_DATA_GAP_UNRESOLVED",
    "TRACKER_OUTCOMES",
    "ACTIVATION_MULTIPLIER",
    "DEFAULT_WATCH_EXPIRY_SECONDS",
    "WATCH_DEADLINE_SOURCE",
    "CANONICAL_CROSSING_SOURCE",
    "MigrationCensusError",
    "canonical_migration_identity",
    "MigrationCensusStore",
    "validate_migration_census_state",
)
