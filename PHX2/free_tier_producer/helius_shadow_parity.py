"""Sanitized Chainstack-versus-Helius parity records.

This module compares already-decoded observations and writes JSONL evidence.
It never constructs either provider, never admits a delivery, and never opens
the production ping ledger. Runtime authority remains entirely with the caller.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from PHX2.free_tier_producer.launcher_contract import (
    PAID_PRIMARY_RUNTIME_ROOT,
)


# Persisted labels are deliberately neutral: the runtime/status manifest
# records which provider owns each role, while parity rows avoid provider-name
# secret-scanner needles as well as every endpoint or credential.
PROVIDER_CHAINSTACK = "PROVIDER_A"
PROVIDER_HELIUS_WSS = "PROVIDER_B_WSS"
PROVIDER_HELIUS_HTTP = "PROVIDER_B_HTTP"
PARITY_PROVIDERS = (
    PROVIDER_CHAINSTACK,
    PROVIDER_HELIUS_WSS,
    PROVIDER_HELIUS_HTTP,
)

MATCH = "MATCH"
HELIUS_ONLY = "HELIUS_ONLY"
CHAINSTACK_ONLY = "CHAINSTACK_ONLY"
SLOT_MISMATCH = "SLOT_MISMATCH"
DECODE_MISMATCH = "DECODE_MISMATCH"
LATE_MATCH = "LATE_MATCH"
RECOVERED_BY_HELIUS_HTTP = "RECOVERED_BY_HELIUS_HTTP"
UNRESOLVED = "UNRESOLVED"
MATCH_STATUSES = (
    MATCH,
    HELIUS_ONLY,
    CHAINSTACK_ONLY,
    SLOT_MISMATCH,
    DECODE_MISMATCH,
    LATE_MATCH,
    RECOVERED_BY_HELIUS_HTTP,
    UNRESOLVED,
)

VERDICT_ADMITTED = "ADMITTED"
VERDICT_REJECTED = "REJECTED"
VERDICT_MALFORMED = "MALFORMED"
DECODER_VERDICTS = (
    VERDICT_ADMITTED,
    VERDICT_REJECTED,
    VERDICT_MALFORMED,
)

DEFAULT_LATE_MATCH_SECONDS = 5.0


class HeliusParityRecordError(ValueError):
    """A parity observation or artifact record is unsafe."""


def _parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError("timestamp must include an offset")
    return moment


def _safe_text(value: object, *, allow_none: bool = False) -> bool:
    if value is None:
        return allow_none
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        return False
    lowered = value.lower()
    return not any(
        token in lowered
        for token in (
            "http://",
            "https://",
            "ws://",
            "wss://",
            "api-key",
            "authorization",
            "bearer ",
        )
    )


@dataclass(frozen=True)
class ParityObservation:
    provider_label: str
    signature_or_hash: str
    slot: int
    receive_timestamp: str
    migration_type: Optional[str]
    mint: Optional[str]
    pool: Optional[str]
    local_decoder_verdict: str
    rejection_reason: Optional[str]
    bytes: int
    estimated_credits: float
    reconnect_count: int = 0
    gap_state: str = "NO_GAP"
    recovery_state: str = "NOT_REQUESTED"

    def __post_init__(self) -> None:
        if self.provider_label not in PARITY_PROVIDERS:
            raise HeliusParityRecordError("provider label is invalid")
        if not _safe_text(self.signature_or_hash):
            raise HeliusParityRecordError("signature identity is unsafe")
        if (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or self.slot < 0
        ):
            raise HeliusParityRecordError("slot is invalid")
        try:
            _parse_utc(self.receive_timestamp)
        except (TypeError, ValueError):
            raise HeliusParityRecordError("receive timestamp is invalid") from None
        if self.local_decoder_verdict not in DECODER_VERDICTS:
            raise HeliusParityRecordError("decoder verdict is invalid")
        for value in (
            self.migration_type,
            self.mint,
            self.pool,
            self.rejection_reason,
            self.gap_state,
            self.recovery_state,
        ):
            if not _safe_text(value, allow_none=True):
                raise HeliusParityRecordError("observation text is unsafe")
        if (
            isinstance(self.bytes, bool)
            or not isinstance(self.bytes, int)
            or self.bytes < 0
            or not isinstance(self.estimated_credits, (int, float))
            or isinstance(self.estimated_credits, bool)
            or self.estimated_credits < 0
            or isinstance(self.reconnect_count, bool)
            or not isinstance(self.reconnect_count, int)
            or self.reconnect_count < 0
        ):
            raise HeliusParityRecordError("observation metric is invalid")


@dataclass(frozen=True)
class ParityRecord:
    provider_label: str
    signature_or_hash: str
    slot: int
    control_slot: Optional[int]
    shadow_slot: Optional[int]
    receive_timestamp: str
    migration_type: Optional[str]
    mint: Optional[str]
    pool: Optional[str]
    local_decoder_verdict: str
    rejection_reason: Optional[str]
    first_seen_provider: str
    latency_difference_seconds: Optional[float]
    match_status: str
    bytes: int
    estimated_credits: float
    reconnect_count: int
    gap_state: str
    recovery_state: str

    def __post_init__(self) -> None:
        if self.match_status not in MATCH_STATUSES:
            raise HeliusParityRecordError("match status is invalid")
        if self.first_seen_provider not in PARITY_PROVIDERS:
            raise HeliusParityRecordError("first-seen provider is invalid")
        if not _safe_text(self.provider_label):
            raise HeliusParityRecordError("provider label is unsafe")
        # Reuse the observation validator for all shared fields and metrics.
        ParityObservation(
            provider_label=self.first_seen_provider,
            signature_or_hash=self.signature_or_hash,
            slot=self.slot,
            receive_timestamp=self.receive_timestamp,
            migration_type=self.migration_type,
            mint=self.mint,
            pool=self.pool,
            local_decoder_verdict=self.local_decoder_verdict,
            rejection_reason=self.rejection_reason,
            bytes=self.bytes,
            estimated_credits=self.estimated_credits,
            reconnect_count=self.reconnect_count,
            gap_state=self.gap_state,
            recovery_state=self.recovery_state,
        )

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _helius_observation(
    values: Mapping[str, ParityObservation],
) -> Optional[ParityObservation]:
    return values.get(PROVIDER_HELIUS_WSS) or values.get(
        PROVIDER_HELIUS_HTTP
    )


class HeliusShadowParityAccumulator:
    """Pair observations by authoritative signature/hash identity."""

    def __init__(
        self, *, late_match_seconds: float = DEFAULT_LATE_MATCH_SECONDS
    ) -> None:
        if not 0 <= float(late_match_seconds) <= 3600:
            raise ValueError("late_match_seconds is out of range")
        self._late_seconds = float(late_match_seconds)
        self._pending: Dict[str, Dict[str, ParityObservation]] = {}
        self._unmatched_emitted: set[str] = set()

    def observe(self, observation: ParityObservation) -> Optional[ParityRecord]:
        values = self._pending.setdefault(observation.signature_or_hash, {})
        values[observation.provider_label] = observation
        chainstack = values.get(PROVIDER_CHAINSTACK)
        helius = _helius_observation(values)
        if chainstack is None or helius is None:
            return None
        record = self._pair_record(
            chainstack,
            helius,
            previously_unmatched=(
                observation.signature_or_hash in self._unmatched_emitted
            ),
        )
        self._pending.pop(observation.signature_or_hash, None)
        self._unmatched_emitted.discard(observation.signature_or_hash)
        return record

    def _pair_record(
        self,
        chainstack: ParityObservation,
        helius: ParityObservation,
        *,
        previously_unmatched: bool,
    ) -> ParityRecord:
        chain_time = _parse_utc(chainstack.receive_timestamp)
        helius_time = _parse_utc(helius.receive_timestamp)
        latency = (helius_time - chain_time).total_seconds()
        first = (
            chainstack
            if chain_time <= helius_time
            else helius
        )
        if helius.provider_label == PROVIDER_HELIUS_HTTP:
            status = RECOVERED_BY_HELIUS_HTTP
        elif chainstack.slot != helius.slot:
            status = SLOT_MISMATCH
        elif (
            chainstack.local_decoder_verdict
            != helius.local_decoder_verdict
            or chainstack.migration_type != helius.migration_type
            or chainstack.mint != helius.mint
            or chainstack.pool != helius.pool
            or chainstack.rejection_reason != helius.rejection_reason
        ):
            status = DECODE_MISMATCH
        elif previously_unmatched or abs(latency) > self._late_seconds:
            status = LATE_MATCH
        else:
            status = MATCH
        verdict = (
            chainstack.local_decoder_verdict
            if chainstack.local_decoder_verdict
            == helius.local_decoder_verdict
            else VERDICT_REJECTED
        )
        rejection = chainstack.rejection_reason or helius.rejection_reason
        return ParityRecord(
            provider_label=(
                PROVIDER_CHAINSTACK + "|" + helius.provider_label
            ),
            signature_or_hash=chainstack.signature_or_hash,
            slot=first.slot,
            control_slot=chainstack.slot,
            shadow_slot=helius.slot,
            receive_timestamp=first.receive_timestamp,
            migration_type=chainstack.migration_type or helius.migration_type,
            mint=chainstack.mint or helius.mint,
            pool=chainstack.pool or helius.pool,
            local_decoder_verdict=verdict,
            rejection_reason=rejection,
            first_seen_provider=first.provider_label,
            latency_difference_seconds=latency,
            match_status=status,
            bytes=chainstack.bytes + helius.bytes,
            estimated_credits=(
                chainstack.estimated_credits + helius.estimated_credits
            ),
            reconnect_count=helius.reconnect_count,
            gap_state=helius.gap_state,
            recovery_state=helius.recovery_state,
        )

    def _finalize_identities(
        self,
        identities: List[str],
    ) -> tuple[ParityRecord, ...]:
        records: List[ParityRecord] = []
        for identity in sorted(identities):
            if identity in self._unmatched_emitted:
                continue
            values = self._pending[identity]
            chainstack = values.get(PROVIDER_CHAINSTACK)
            helius = _helius_observation(values)
            observation = chainstack or helius
            if observation is None:
                continue
            unresolved = (
                observation.gap_state != "NO_GAP"
                or observation.recovery_state in (
                    "PARTIAL",
                    "FAILED",
                    "UNRESOLVED",
                )
            )
            status = (
                UNRESOLVED
                if unresolved
                else CHAINSTACK_ONLY
                if chainstack is not None
                else HELIUS_ONLY
            )
            records.append(
                ParityRecord(
                    provider_label=observation.provider_label,
                    signature_or_hash=observation.signature_or_hash,
                    slot=observation.slot,
                    control_slot=(
                        chainstack.slot if chainstack is not None else None
                    ),
                    shadow_slot=(
                        helius.slot if helius is not None else None
                    ),
                    receive_timestamp=observation.receive_timestamp,
                    migration_type=observation.migration_type,
                    mint=observation.mint,
                    pool=observation.pool,
                    local_decoder_verdict=(
                        observation.local_decoder_verdict
                    ),
                    rejection_reason=observation.rejection_reason,
                    first_seen_provider=observation.provider_label,
                    latency_difference_seconds=None,
                    match_status=status,
                    bytes=observation.bytes,
                    estimated_credits=observation.estimated_credits,
                    reconnect_count=observation.reconnect_count,
                    gap_state=observation.gap_state,
                    recovery_state=observation.recovery_state,
                )
            )
            self._unmatched_emitted.add(identity)
        return tuple(records)

    def finalize_expired(
        self,
        *,
        now_timestamp: str,
    ) -> tuple[ParityRecord, ...]:
        """Emit unmatched rows only after the bounded late-match grace."""

        now = _parse_utc(now_timestamp)
        expired: List[str] = []
        for identity, values in self._pending.items():
            observations = list(values.values())
            if not observations:
                continue
            first = min(
                _parse_utc(item.receive_timestamp)
                for item in observations
            )
            if (now - first).total_seconds() >= self._late_seconds:
                expired.append(identity)
        return self._finalize_identities(expired)

    def finalize_unmatched(self) -> tuple[ParityRecord, ...]:
        return self._finalize_identities(list(self._pending))


def _is_under(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        parent = root.resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved == parent or parent in resolved.parents


class HeliusParityArtifactWriter:
    """Append-only, fsync'd sanitized JSONL writer outside production state."""

    def __init__(self, path: Path, *, allowed_root: Path) -> None:
        self.path = path.resolve()
        self.allowed_root = allowed_root.resolve()
        if not _is_under(self.path, self.allowed_root):
            raise HeliusParityRecordError(
                "parity artifact path is outside the allowed root"
            )
        if _is_under(self.path, Path(PAID_PRIMARY_RUNTIME_ROOT)):
            raise HeliusParityRecordError(
                "parity artifact path overlaps production runtime"
            )

    def initialize(self) -> None:
        """Create one fresh artifact even when the run observes no migration."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.flush()
            os.fsync(handle.fileno())

    def write(self, record: ParityRecord) -> None:
        payload = record.to_dict()
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        lowered = serialized.lower()
        if any(
            token in lowered
            for token in (
                "http://",
                "https://",
                "ws://",
                "wss://",
                "api-key",
                "authorization",
                "bearer ",
            )
        ):
            raise HeliusParityRecordError(
                "parity artifact contains forbidden secret shape"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())


__all__ = (
    "CHAINSTACK_ONLY",
    "DECODE_MISMATCH",
    "DECODER_VERDICTS",
    "HELIUS_ONLY",
    "HeliusParityArtifactWriter",
    "HeliusParityRecordError",
    "HeliusShadowParityAccumulator",
    "LATE_MATCH",
    "MATCH",
    "MATCH_STATUSES",
    "PROVIDER_CHAINSTACK",
    "PROVIDER_HELIUS_HTTP",
    "PROVIDER_HELIUS_WSS",
    "ParityObservation",
    "ParityRecord",
    "RECOVERED_BY_HELIUS_HTTP",
    "SLOT_MISMATCH",
    "UNRESOLVED",
    "VERDICT_ADMITTED",
    "VERDICT_MALFORMED",
    "VERDICT_REJECTED",
)
