"""Fee Gate lifecycle: freshness, maturity, and durable-lock separation.

The PHX1 scoring rubric in :mod:`PHX2.free_tier_producer.phx1_fee_gate` is
untouched.  This module corrects the lifecycle defects proven by the 2026-07-17
live investigation by separating four concepts the old path conflated:

A. evidence availability/freshness   -> ``TEMPORARILY_STALE`` is recoverable;
B. provisional classification        -> immature evidence never locks;
C. durable confirmed scam lock       -> only fresh, mature, structurally
                                        reasoned scam evidence confirmed across
                                        distinct evidence versions (or a severe
                                        structural proof the existing composite
                                        policy already recognizes);
D. send eligibility                  -> only ``FRESH_CONFIRMED`` evidence with
                                        an acceptable verdict may authorize
                                        compose/reserve/send, re-checked at the
                                        pre-reserve boundary.

Fail-closed behavior at compose time is preserved: a stale, immature,
provisional, invalid or locked lifecycle always yields a block reason that the
composite policy and the pre-reserve send gate enforce.  What changed is that
stale/immature outcomes no longer poison a candidate permanently: the candidate
stays tracked, the last fresh verdict is preserved, and fresh evidence recovers
the mint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_DATA_STALE,
    BLOCK_SCAM_LIKELY,
    DEFAULT_FEE_PROOF_MAX_AGE_SECONDS,
    FEE_GATE_LABELS,
    FEE_GATE_UNKNOWN,
    PHX1_FEE_GATE_SCAM_LIKELY,
    REASON_BRIBES_LOW,
    REASON_BRIBES_STARVED,
    REASON_CREATOR_DOMINANCE,
    REASON_STICKY_LOCK,
    REASON_THIN_SAMPLE,
    FeeGateSnapshot,
    seal_fee_snapshot,
)


FEE_GATE_LIFECYCLE_VERSION = "PHX2_FEE_GATE_LIFECYCLE_V1"

LIFECYCLE_IMMATURE = "IMMATURE"
LIFECYCLE_FRESH_PROVISIONAL = "FRESH_PROVISIONAL"
LIFECYCLE_FRESH_CONFIRMED = "FRESH_CONFIRMED"
LIFECYCLE_TEMPORARILY_STALE = "TEMPORARILY_STALE"
LIFECYCLE_DURABLE_SCAM_LOCKED = "DURABLE_SCAM_LOCKED"
LIFECYCLE_STATES = frozenset({
    LIFECYCLE_IMMATURE,
    LIFECYCLE_FRESH_PROVISIONAL,
    LIFECYCLE_FRESH_CONFIRMED,
    LIFECYCLE_TEMPORARILY_STALE,
    LIFECYCLE_DURABLE_SCAM_LOCKED,
})

MATURITY_IMMATURE = "IMMATURE"
MATURITY_PROVISIONAL = "PROVISIONAL"
MATURITY_CONFIRMED = "CONFIRMED"
MATURITY_RESULTS = frozenset({
    MATURITY_IMMATURE, MATURITY_PROVISIONAL, MATURITY_CONFIRMED,
})

# Closed-set lifecycle block tokens (redaction-safe; never carry raw values).
LIFECYCLE_BLOCK_IMMATURE = "PHX2_FEE_LIFECYCLE_IMMATURE"
LIFECYCLE_BLOCK_PROVISIONAL = "PHX2_FEE_LIFECYCLE_PROVISIONAL"
LIFECYCLE_BLOCK_STALE = "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE"
LIFECYCLE_BLOCK_DURABLE_LOCK = "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK"
LIFECYCLE_BLOCK_STATE_INVALID = "PHX2_FEE_LIFECYCLE_STATE_INVALID"
LIFECYCLE_BLOCK_EVIDENCE_UNBOUND = "PHX2_FEE_LIFECYCLE_EVIDENCE_UNBOUND"

# The one single-snapshot severe structural proof the historical two-stream
# composite recognized: a fresh mature SCAM_LIKELY fee verdict co-occurring
# with a proven post-migration liquidity removal (LP_INTEGRITY_FAIL).  The
# caller proves it via ``severe_structural_proof=True``; this module never
# recomputes LP evidence itself.  Single-stream production has no verifier,
# never passes True, and a HISTORICAL lock justified only by this proof is
# ignored on restore (see ``_load``) with an observable marker.
SEVERE_PROOF_LP_REMOVAL_COMPOSITE = "LP_AND_FEE_COMPOSITE_BLOCK"

# Observable restore marker: legacy LP-only durable locks are not enforced in
# single-stream production.  Keep the literal in sync with
# ``PHX2.free_tier_producer.scam_policy.LEGACY_LP_STATE_IGNORED_SINGLE_STREAM``
# (importing it here would invert the policy layering).
LEGACY_LP_STATE_IGNORED_SINGLE_STREAM = "LEGACY_LP_STATE_IGNORED_SINGLE_STREAM"

_COUNTER_FIELDS = (
    "fee_gate_immature",
    "fee_gate_fresh_provisional",
    "fee_gate_fresh_confirmed",
    "fee_gate_temporarily_stale",
    "fee_gate_durable_scam_locked",
    "fee_gate_recovered_from_stale",
    "fee_gate_provisional_scam_recovered",
    "fee_gate_send_time_stale_blocks",
    "fee_gate_send_time_immature_blocks",
    "fee_gate_send_time_scam_blocks",
)

_ENV_INT_FIELDS = {
    "PHX2_FEE_LIFECYCLE_PROVISIONAL_MIN_TRANSACTIONS": "provisional_min_transaction_count",
    "PHX2_FEE_LIFECYCLE_PROVISIONAL_MIN_EVENTS": "provisional_min_event_count",
    "PHX2_FEE_LIFECYCLE_PROVISIONAL_MIN_SPAN_SECONDS": "provisional_min_evidence_span_seconds",
    "PHX2_FEE_LIFECYCLE_CONFIRMED_MIN_TRANSACTIONS": "confirmed_min_transaction_count",
    "PHX2_FEE_LIFECYCLE_CONFIRMED_MIN_EVENTS": "confirmed_min_event_count",
    "PHX2_FEE_LIFECYCLE_CONFIRMED_MIN_SPAN_SECONDS": "confirmed_min_evidence_span_seconds",
    "PHX2_FEE_LIFECYCLE_SCAM_CONFIRMATIONS": "scam_confirmations_required",
}


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"fee_lifecycle_config_invalid:{field}")
    return value


@dataclass(frozen=True)
class FeeGateLifecycleConfig:
    """Deterministic maturity + confirmation policy (integers/Decimal only).

    The confirmed floors are grounded in the existing evidence windows: a full
    PHX1 last-20 ante window of distinct transactions observed across at least
    one full 300-second recent window.  ``thin_sample`` keeps its PHX1 meaning
    (transaction_count < 500) and stays visible; maturity is a separate,
    stricter-purpose measurement and never rewrites the PHX1 score.
    """

    provisional_min_transaction_count: int = 5
    provisional_min_event_count: int = 5
    provisional_min_evidence_span_seconds: int = 60
    confirmed_min_transaction_count: int = 20
    confirmed_min_event_count: int = 20
    confirmed_min_evidence_span_seconds: int = 300
    freshness_max_age_seconds: Decimal = DEFAULT_FEE_PROOF_MAX_AGE_SECONDS
    scam_confirmations_required: int = 2
    structural_scam_reasons: Tuple[str, ...] = (
        REASON_BRIBES_STARVED, REASON_CREATOR_DOMINANCE)
    severe_single_snapshot_reasons: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "provisional_min_transaction_count", "provisional_min_event_count",
            "provisional_min_evidence_span_seconds",
            "confirmed_min_transaction_count", "confirmed_min_event_count",
            "confirmed_min_evidence_span_seconds",
        ):
            _positive_int(getattr(self, field), field)
        for provisional, confirmed in (
            ("provisional_min_transaction_count", "confirmed_min_transaction_count"),
            ("provisional_min_event_count", "confirmed_min_event_count"),
            ("provisional_min_evidence_span_seconds", "confirmed_min_evidence_span_seconds"),
        ):
            if getattr(self, provisional) > getattr(self, confirmed):
                raise ValueError(f"fee_lifecycle_config_invalid:{confirmed}")
        if (isinstance(self.scam_confirmations_required, bool)
                or not isinstance(self.scam_confirmations_required, int)
                or self.scam_confirmations_required < 2):
            # "At least two consecutive fresh mature snapshots" is a hard
            # policy floor; single-observation locks go through the severe
            # structural proof path only.
            raise ValueError("fee_lifecycle_config_invalid:scam_confirmations_required")
        if (not isinstance(self.freshness_max_age_seconds, Decimal)
                or not self.freshness_max_age_seconds.is_finite()
                or self.freshness_max_age_seconds <= 0):
            raise ValueError("fee_lifecycle_config_invalid:freshness_max_age_seconds")
        structural = tuple(self.structural_scam_reasons)
        if not structural or any(not isinstance(reason, str) for reason in structural):
            raise ValueError("fee_lifecycle_config_invalid:structural_scam_reasons")
        if {REASON_THIN_SAMPLE, REASON_BRIBES_LOW} & set(structural):
            # Sample scarcity and the soft bribes flag are never durable
            # structural scam reasons.
            raise ValueError("fee_lifecycle_config_invalid:structural_scam_reasons")
        if not set(self.severe_single_snapshot_reasons) <= set(structural):
            raise ValueError("fee_lifecycle_config_invalid:severe_single_snapshot_reasons")

    def to_safe_dict(self) -> Dict[str, Any]:
        """Plain policy numbers/tokens only — safe for startup/status output."""

        payload = asdict(self)
        payload["freshness_max_age_seconds"] = format(self.freshness_max_age_seconds, "f")
        payload["structural_scam_reasons"] = list(self.structural_scam_reasons)
        payload["severe_single_snapshot_reasons"] = list(self.severe_single_snapshot_reasons)
        payload["lifecycle_version"] = FEE_GATE_LIFECYCLE_VERSION
        return payload


def build_fee_gate_lifecycle_config(
    env: Mapping[str, str],
    *,
    freshness_max_age_seconds: object = None,
) -> FeeGateLifecycleConfig:
    """Build the lifecycle config with optional integer env overrides.

    A malformed override raises ``ValueError`` so the session REFUSES the run
    instead of silently weakening the policy (same posture as migration
    admission).  The structural/severe reason sets are code-level policy and
    deliberately have no env override.
    """

    overrides: Dict[str, Any] = {}
    for env_key, field in _ENV_INT_FIELDS.items():
        raw = env.get(env_key)
        if raw is None or not str(raw).strip():
            continue
        text = str(raw).strip()
        if not (text.isascii() and text.isdigit()):
            raise ValueError(f"fee_lifecycle_config_invalid:{env_key}")
        overrides[field] = int(text)
    if freshness_max_age_seconds is not None:
        try:
            freshness = Decimal(str(freshness_max_age_seconds))
        except (InvalidOperation, ValueError):
            raise ValueError("fee_lifecycle_config_invalid:freshness_max_age_seconds")
        overrides["freshness_max_age_seconds"] = freshness
    return FeeGateLifecycleConfig(**overrides)


def _parse_utc_epoch(value: object) -> Optional[int]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return int(parsed.timestamp())


def evidence_identity_digest(snapshot: FeeGateSnapshot) -> str:
    """Digest of the underlying EVIDENCE only (evaluation-time fields excluded).

    Two evaluations of the exact same frozen evidence produce the same identity
    even though their sealed proof digests differ (the sealed digest covers the
    evaluation instant).  Confirmation counting dedupes on this identity, so a
    repeated evaluation of one frozen snapshot can never satisfy the
    confirmation count.
    """

    payload = {
        "candidate_mint": snapshot.candidate_mint,
        "quote_mint": snapshot.quote_mint,
        "unit": snapshot.unit,
        "total_fees": snapshot.total_fees,
        "lp_fees": snapshot.lp_fees,
        "protocol_fees": snapshot.protocol_fees,
        "creator_fees": snapshot.creator_fees,
        "base_fees": snapshot.base_fees,
        "priority_fees": snapshot.priority_fees,
        "jito_tips": snapshot.jito_tips,
        "transaction_count": snapshot.transaction_count,
        "event_count": snapshot.event_count,
        "first_observed_at_utc": snapshot.first_observed_at_utc,
        "last_observed_at_utc": snapshot.last_observed_at_utc,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaturityResult:
    maturity: str
    transaction_count: int
    event_count: int
    evidence_span_seconds: Optional[int]


def evaluate_maturity(
    snapshot: FeeGateSnapshot, *, config: FeeGateLifecycleConfig, now_epoch: int,
) -> MaturityResult:
    """Deterministic maturity from counts + age since first valid event.

    Never wall-clock age alone: the confirmed tier requires the transaction and
    event floors AND the observed span.  An unparseable first-observation
    timestamp fails closed to IMMATURE.
    """

    transaction_count = int(snapshot.transaction_count)
    event_count = int(snapshot.event_count)
    first_epoch = _parse_utc_epoch(snapshot.first_observed_at_utc)
    span = None if first_epoch is None else int(now_epoch) - first_epoch
    if span is not None and span < 0:
        span = None
    if (span is not None
            and transaction_count >= config.confirmed_min_transaction_count
            and event_count >= config.confirmed_min_event_count
            and span >= config.confirmed_min_evidence_span_seconds):
        maturity = MATURITY_CONFIRMED
    elif (span is not None
            and transaction_count >= config.provisional_min_transaction_count
            and event_count >= config.provisional_min_event_count
            and span >= config.provisional_min_evidence_span_seconds):
        maturity = MATURITY_PROVISIONAL
    else:
        maturity = MATURITY_IMMATURE
    return MaturityResult(
        maturity=maturity,
        transaction_count=transaction_count,
        event_count=event_count,
        evidence_span_seconds=span,
    )


def stamp_durable_scam_lock(
    snapshot: FeeGateSnapshot, *, locked_score: int,
) -> FeeGateSnapshot:
    """Reseal a fresh snapshot as the durable hard block.

    Mirrors the legacy sticky presentation (``sticky_lock`` reason, SCAM label,
    ineligible, hard block) so ``validate_fee_snapshot``'s sticky seam, the
    composite policy and the composer display keep working unchanged — but it
    is now applied ONLY from a confirmed durable lock, never from a raw
    worst-score memory.
    """

    reasons = tuple(dict.fromkeys((*snapshot.fee_gate_reasons, REASON_STICKY_LOCK)))
    current = snapshot.fee_gate_score if isinstance(snapshot.fee_gate_score, int) else 0
    return seal_fee_snapshot(replace(
        snapshot,
        fee_gate_score=max(int(current), int(locked_score)),
        fee_gate_label=PHX1_FEE_GATE_SCAM_LIKELY,
        fee_gate_reasons=reasons,
        fee_gate_eligible=False,
        hard_block=True,
        proof_digest="",
    ))


_RECORD_TUPLE_FIELDS = (
    "last_fresh_reasons",
    "confirmation_identities",
    "confirmation_proof_digests",
    "confirmation_last_event_at_utc",
    "confirmation_structural_reasons",
    "durable_lock_reasons",
)


@dataclass(frozen=True)
class FeeGateLifecycleRecord:
    """Restart-persisted lifecycle state for one mint (sealed with a digest)."""

    lifecycle_version: str
    candidate_mint: str
    lifecycle_state: str
    last_fresh_verdict: Optional[str]
    last_fresh_score: Optional[int]
    last_fresh_reasons: Tuple[str, ...]
    last_fresh_maturity: Optional[str]
    last_fresh_proof_digest: Optional[str]
    last_fresh_evidence_identity: Optional[str]
    last_fresh_last_event_at_utc: Optional[str]
    last_fresh_evaluated_at_epoch: Optional[int]
    last_fresh_transaction_count: int
    last_fresh_event_count: int
    provisional_scam_count: int
    confirmation_identities: Tuple[str, ...]
    confirmation_proof_digests: Tuple[str, ...]
    confirmation_last_event_at_utc: Tuple[str, ...]
    confirmation_structural_reasons: Tuple[str, ...]
    durable_scam_locked: bool
    durable_lock_reasons: Tuple[str, ...]
    durable_lock_created_at_epoch: Optional[int]
    durable_lock_score: Optional[int]
    stale_since_epoch: Optional[int]
    record_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for field in _RECORD_TUPLE_FIELDS:
            payload[field] = list(payload[field])
        return payload


def _record_digest(record: FeeGateLifecycleRecord) -> str:
    payload = record.to_dict()
    payload.pop("record_digest", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_lifecycle_record(record: FeeGateLifecycleRecord) -> FeeGateLifecycleRecord:
    return replace(record, record_digest=_record_digest(replace(record, record_digest="")))


def validate_lifecycle_record(record: object) -> Tuple[bool, Optional[str]]:
    if not isinstance(record, FeeGateLifecycleRecord):
        return False, "record_missing"
    if record.lifecycle_version != FEE_GATE_LIFECYCLE_VERSION:
        return False, "lifecycle_version_mismatch"
    if not record.record_digest or record.record_digest != _record_digest(record):
        return False, "record_digest_mismatch"
    if not isinstance(record.candidate_mint, str) or not record.candidate_mint:
        return False, "mint_invalid"
    if record.lifecycle_state not in LIFECYCLE_STATES:
        return False, "state_invalid"
    if record.last_fresh_verdict is not None and (
            record.last_fresh_verdict not in FEE_GATE_LABELS
            or record.last_fresh_verdict == FEE_GATE_UNKNOWN):
        return False, "last_fresh_verdict_invalid"
    for field in ("last_fresh_transaction_count", "last_fresh_event_count",
                  "provisional_scam_count"):
        value = getattr(record, field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, f"{field}_invalid"
    for field in _RECORD_TUPLE_FIELDS:
        values = getattr(record, field)
        if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item for item in values):
            return False, f"{field}_invalid"
    if record.provisional_scam_count != len(record.confirmation_identities):
        return False, "confirmation_count_mismatch"
    if len(set(record.confirmation_identities)) != len(record.confirmation_identities):
        return False, "confirmation_identities_duplicated"
    if record.durable_scam_locked:
        if record.lifecycle_state != LIFECYCLE_DURABLE_SCAM_LOCKED:
            return False, "durable_lock_state_mismatch"
        if LIFECYCLE_BLOCK_DURABLE_LOCK not in record.durable_lock_reasons:
            return False, "durable_lock_reasons_invalid"
        if (isinstance(record.durable_lock_score, bool)
                or not isinstance(record.durable_lock_score, int)
                or record.durable_lock_score < 0):
            return False, "durable_lock_score_invalid"
    else:
        if record.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED:
            return False, "durable_lock_state_mismatch"
        if record.durable_lock_reasons:
            return False, "durable_lock_reasons_invalid"
    return True, None


@dataclass(frozen=True)
class FeeGateLifecycleView:
    """One observation outcome bound to the exact evidence it evaluated."""

    candidate_mint: str
    lifecycle_state: str
    maturity: str
    current_verdict: str
    send_block_reasons: Tuple[str, ...]
    effective_snapshot: FeeGateSnapshot
    evidence_proof_digest: str
    evidence_identity: Optional[str]
    artifact: Dict[str, Any]


class FeeGateLifecycleIndex:
    """Thread-safe per-mint lifecycle owner with restart persistence.

    Replaces the removed in-index worst-score sticky memory: recovery is the
    default for provisional/stale outcomes, and only the confirmation policy
    creates a durable lock.  Only tracked candidates are ever observed here —
    migration admission already rejected fake dust and direct pools upstream,
    so they never enter the lifecycle.
    """

    def __init__(
        self,
        *,
        config: Optional[FeeGateLifecycleConfig] = None,
        path: Optional[Any] = None,
    ) -> None:
        self._config = config if config is not None else FeeGateLifecycleConfig()
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._by_mint: Dict[str, Dict[str, Any]] = {}
        self._tainted: set = set()
        self._counters = {name: 0 for name in _COUNTER_FIELDS}
        self._persist_errors = 0
        self._load_dropped = 0
        self._restored_records = 0
        self._restored_locks = 0
        self._legacy_lp_locks_ignored = 0
        self._legacy_lp_ignored_mints: set = set()
        if self._path is not None and self._path.exists():
            self._load()

    @property
    def config(self) -> FeeGateLifecycleConfig:
        return self._config

    # ---- persistence ----

    def _load(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            mint_hint = None
            try:
                payload = json.loads(line)
                mint_hint = payload.get("candidate_mint")
                for field in _RECORD_TUPLE_FIELDS:
                    payload[field] = tuple(payload.get(field) or ())
                record = FeeGateLifecycleRecord(**payload)
            except (ValueError, TypeError):
                self._load_dropped += 1
                if isinstance(mint_hint, str) and mint_hint:
                    # Fail closed: a malformed persisted line for a known mint
                    # permanently blocks that mint's send authorization for
                    # this session.  Valid durable locks from other lines are
                    # still honored (locks only ever block).
                    self._tainted.add(mint_hint)
                continue
            valid, _ = validate_lifecycle_record(record)
            if not valid:
                self._load_dropped += 1
                if isinstance(mint_hint, str) and mint_hint:
                    self._tainted.add(mint_hint)
                continue
            self._restored_records += 1
            # Latest valid record per mint wins; runtime-only fields reset.
            state = self._state_from_record(record)
            self._filter_legacy_lp_lock(record.candidate_mint, state)
            if state["durable_scam_locked"]:
                self._restored_locks += 1
            self._by_mint[record.candidate_mint] = state

    def _filter_legacy_lp_lock(self, mint: str, state: Dict[str, Any]) -> None:
        """Single-stream restore rule: an LP-removal composite is no longer a
        recognized lock justification.  A restored durable lock that fresh
        mature structural fee evidence justifies on its own (enough distinct
        confirmations, or a severe single-snapshot FEE reason) survives with
        the LP token stripped from its reasons; a lock justified ONLY by the
        historical LP severe proof is observably ignored instead of blocking a
        new single-stream run."""
        if not state["durable_scam_locked"]:
            return
        reasons = tuple(state["durable_lock_reasons"])
        if SEVERE_PROOF_LP_REMOVAL_COMPOSITE not in reasons:
            return
        fee_justified = (
            int(state["provisional_scam_count"] or 0)
            >= self._config.scam_confirmations_required
            or any(reason in self._config.severe_single_snapshot_reasons
                   for reason in state["confirmation_structural_reasons"]))
        if fee_justified:
            state["durable_lock_reasons"] = tuple(
                reason for reason in reasons
                if reason != SEVERE_PROOF_LP_REMOVAL_COMPOSITE)
            return
        state["durable_scam_locked"] = False
        state["durable_lock_reasons"] = ()
        state["durable_lock_created_at_epoch"] = None
        state["durable_lock_score"] = None
        if state["lifecycle_state"] == LIFECYCLE_DURABLE_SCAM_LOCKED:
            state["lifecycle_state"] = LIFECYCLE_TEMPORARILY_STALE
        self._legacy_lp_locks_ignored += 1
        self._legacy_lp_ignored_mints.add(str(mint))

    @staticmethod
    def _state_from_record(record: FeeGateLifecycleRecord) -> Dict[str, Any]:
        return {
            "lifecycle_state": record.lifecycle_state,
            "last_fresh_verdict": record.last_fresh_verdict,
            "last_fresh_score": record.last_fresh_score,
            "last_fresh_reasons": tuple(record.last_fresh_reasons),
            "last_fresh_maturity": record.last_fresh_maturity,
            "last_fresh_proof_digest": record.last_fresh_proof_digest,
            "last_fresh_evidence_identity": record.last_fresh_evidence_identity,
            "last_fresh_last_event_at_utc": record.last_fresh_last_event_at_utc,
            "last_fresh_evaluated_at_epoch": record.last_fresh_evaluated_at_epoch,
            "last_fresh_transaction_count": record.last_fresh_transaction_count,
            "last_fresh_event_count": record.last_fresh_event_count,
            "provisional_scam_count": record.provisional_scam_count,
            "confirmation_identities": tuple(record.confirmation_identities),
            "confirmation_proof_digests": tuple(record.confirmation_proof_digests),
            "confirmation_last_event_at_utc": tuple(record.confirmation_last_event_at_utc),
            "confirmation_structural_reasons": tuple(record.confirmation_structural_reasons),
            "durable_scam_locked": bool(record.durable_scam_locked),
            "durable_lock_reasons": tuple(record.durable_lock_reasons),
            "durable_lock_created_at_epoch": record.durable_lock_created_at_epoch,
            "durable_lock_score": record.durable_lock_score,
            "stale_since_epoch": record.stale_since_epoch,
            "last_artifact": None,
        }

    @staticmethod
    def _new_state() -> Dict[str, Any]:
        return {
            "lifecycle_state": None,
            "last_fresh_verdict": None,
            "last_fresh_score": None,
            "last_fresh_reasons": (),
            "last_fresh_maturity": None,
            "last_fresh_proof_digest": None,
            "last_fresh_evidence_identity": None,
            "last_fresh_last_event_at_utc": None,
            "last_fresh_evaluated_at_epoch": None,
            "last_fresh_transaction_count": 0,
            "last_fresh_event_count": 0,
            "provisional_scam_count": 0,
            "confirmation_identities": (),
            "confirmation_proof_digests": (),
            "confirmation_last_event_at_utc": (),
            "confirmation_structural_reasons": (),
            "durable_scam_locked": False,
            "durable_lock_reasons": (),
            "durable_lock_created_at_epoch": None,
            "durable_lock_score": None,
            "stale_since_epoch": None,
            "last_artifact": None,
        }

    def _record_from_state(self, mint: str, state: Mapping[str, Any]) -> FeeGateLifecycleRecord:
        return seal_lifecycle_record(FeeGateLifecycleRecord(
            lifecycle_version=FEE_GATE_LIFECYCLE_VERSION,
            candidate_mint=mint,
            lifecycle_state=str(state["lifecycle_state"]),
            last_fresh_verdict=state["last_fresh_verdict"],
            last_fresh_score=state["last_fresh_score"],
            last_fresh_reasons=tuple(state["last_fresh_reasons"]),
            last_fresh_maturity=state["last_fresh_maturity"],
            last_fresh_proof_digest=state["last_fresh_proof_digest"],
            last_fresh_evidence_identity=state["last_fresh_evidence_identity"],
            last_fresh_last_event_at_utc=state["last_fresh_last_event_at_utc"],
            last_fresh_evaluated_at_epoch=state["last_fresh_evaluated_at_epoch"],
            last_fresh_transaction_count=int(state["last_fresh_transaction_count"]),
            last_fresh_event_count=int(state["last_fresh_event_count"]),
            provisional_scam_count=int(state["provisional_scam_count"]),
            confirmation_identities=tuple(state["confirmation_identities"]),
            confirmation_proof_digests=tuple(state["confirmation_proof_digests"]),
            confirmation_last_event_at_utc=tuple(state["confirmation_last_event_at_utc"]),
            confirmation_structural_reasons=tuple(state["confirmation_structural_reasons"]),
            durable_scam_locked=bool(state["durable_scam_locked"]),
            durable_lock_reasons=tuple(state["durable_lock_reasons"]),
            durable_lock_created_at_epoch=state["durable_lock_created_at_epoch"],
            durable_lock_score=state["durable_lock_score"],
            stale_since_epoch=state["stale_since_epoch"],
        ))

    def _persist(self, mint: str, state: Mapping[str, Any]) -> None:
        if self._path is None:
            return
        try:
            record = self._record_from_state(mint, state)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(
                    record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        except (OSError, ValueError, TypeError):
            self._persist_errors += 1

    # ---- observation ----

    def observe(
        self,
        snapshot: FeeGateSnapshot,
        *,
        now_epoch: int,
        severe_structural_proof: bool = False,
    ) -> FeeGateLifecycleView:
        """Fold one sealed fee snapshot into the mint's lifecycle.

        ``severe_structural_proof`` is the caller-proven LP-removal composite
        (the one single-snapshot severe proof the existing policy recognizes);
        it never weakens anything — it can only accelerate a lock that fresh
        mature structural scam evidence already justifies.
        """

        if not isinstance(snapshot, FeeGateSnapshot):
            raise ValueError("fee_lifecycle_snapshot_required")
        mint = str(snapshot.candidate_mint)
        with self._lock:
            state = self._by_mint.get(mint)
            if state is None:
                state = self._new_state()
                self._by_mint[mint] = state
            material_before = self._material_tuple(state)

            fresh_scored = (
                snapshot.fee_gate_label != FEE_GATE_UNKNOWN
                and snapshot.fee_gate_score is not None
            )
            stale_tick = (
                snapshot.fee_gate_label == FEE_GATE_UNKNOWN
                and (BLOCK_DATA_STALE in snapshot.fee_gate_reasons
                     or bool(snapshot.stale_data_reasons))
            )
            maturity_result: Optional[MaturityResult] = None
            identity: Optional[str] = None

            if fresh_scored:
                maturity_result = evaluate_maturity(
                    snapshot, config=self._config, now_epoch=now_epoch)
                identity = evidence_identity_digest(snapshot)
                if (state["lifecycle_state"] == LIFECYCLE_TEMPORARILY_STALE
                        and not state["durable_scam_locked"]):
                    self._counters["fee_gate_recovered_from_stale"] += 1
                state["stale_since_epoch"] = None
                state["last_fresh_verdict"] = snapshot.fee_gate_label
                state["last_fresh_score"] = int(snapshot.fee_gate_score)
                state["last_fresh_reasons"] = tuple(snapshot.fee_gate_reasons)
                state["last_fresh_maturity"] = maturity_result.maturity
                state["last_fresh_proof_digest"] = snapshot.proof_digest
                state["last_fresh_evidence_identity"] = identity
                state["last_fresh_last_event_at_utc"] = snapshot.last_observed_at_utc
                state["last_fresh_evaluated_at_epoch"] = int(now_epoch)
                state["last_fresh_transaction_count"] = int(snapshot.transaction_count)
                state["last_fresh_event_count"] = int(snapshot.event_count)

                if snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY:
                    structural = tuple(
                        reason for reason in snapshot.fee_gate_reasons
                        if reason in self._config.structural_scam_reasons)
                    if (maturity_result.maturity == MATURITY_CONFIRMED
                            and structural
                            and not state["durable_scam_locked"]):
                        if identity not in state["confirmation_identities"]:
                            state["confirmation_identities"] = (
                                *state["confirmation_identities"], identity)
                            state["confirmation_proof_digests"] = (
                                *state["confirmation_proof_digests"],
                                snapshot.proof_digest)
                            state["confirmation_last_event_at_utc"] = (
                                *state["confirmation_last_event_at_utc"],
                                str(snapshot.last_observed_at_utc))
                            state["confirmation_structural_reasons"] = tuple(
                                dict.fromkeys((
                                    *state["confirmation_structural_reasons"],
                                    *structural)))
                            state["provisional_scam_count"] = len(
                                state["confirmation_identities"])
                        severe_hit = bool(severe_structural_proof) or any(
                            reason in self._config.severe_single_snapshot_reasons
                            for reason in structural)
                        if (severe_hit or state["provisional_scam_count"]
                                >= self._config.scam_confirmations_required):
                            lock_reasons = [
                                LIFECYCLE_BLOCK_DURABLE_LOCK, BLOCK_SCAM_LIKELY,
                                *state["confirmation_structural_reasons"],
                            ]
                            if severe_structural_proof:
                                lock_reasons.append(SEVERE_PROOF_LP_REMOVAL_COMPOSITE)
                            state["durable_scam_locked"] = True
                            state["durable_lock_reasons"] = tuple(
                                dict.fromkeys(lock_reasons))
                            state["durable_lock_created_at_epoch"] = int(now_epoch)
                            state["durable_lock_score"] = int(snapshot.fee_gate_score)
                    # Immature/provisional SCAM or a non-structural score stays
                    # provisional-only: visible, blocking today, never durable.
                else:
                    if (state["provisional_scam_count"] > 0
                            and not state["durable_scam_locked"]):
                        self._counters["fee_gate_provisional_scam_recovered"] += 1
                    # A fresh non-scam evaluation breaks the consecutive chain.
                    state["provisional_scam_count"] = 0
                    state["confirmation_identities"] = ()
                    state["confirmation_proof_digests"] = ()
                    state["confirmation_last_event_at_utc"] = ()
                    state["confirmation_structural_reasons"] = ()

                if state["durable_scam_locked"]:
                    lifecycle_state = LIFECYCLE_DURABLE_SCAM_LOCKED
                elif maturity_result.maturity == MATURITY_CONFIRMED:
                    lifecycle_state = LIFECYCLE_FRESH_CONFIRMED
                elif maturity_result.maturity == MATURITY_PROVISIONAL:
                    lifecycle_state = LIFECYCLE_FRESH_PROVISIONAL
                else:
                    lifecycle_state = LIFECYCLE_IMMATURE
            elif stale_tick:
                # Stale never overwrites the last fresh verdict, never counts
                # toward confirmation, and never strengthens a lock.
                if state["durable_scam_locked"]:
                    lifecycle_state = LIFECYCLE_DURABLE_SCAM_LOCKED
                else:
                    lifecycle_state = LIFECYCLE_TEMPORARILY_STALE
                    if state["stale_since_epoch"] is None:
                        state["stale_since_epoch"] = int(now_epoch)
            else:
                # Missing proof / insufficient sample / uncalibrated pair /
                # malformed: evidence is absent rather than aged out.  Warmup
                # states never lock and never count.
                if state["durable_scam_locked"]:
                    lifecycle_state = LIFECYCLE_DURABLE_SCAM_LOCKED
                else:
                    lifecycle_state = LIFECYCLE_IMMATURE

            state["lifecycle_state"] = lifecycle_state
            self._counters[self._state_counter(lifecycle_state)] += 1

            effective = snapshot
            if state["durable_scam_locked"] and fresh_scored:
                effective = stamp_durable_scam_lock(
                    snapshot, locked_score=int(state["durable_lock_score"] or 0))

            send_block_reasons = self._send_block_reasons(mint, state, lifecycle_state)
            maturity_token = (
                maturity_result.maturity if maturity_result is not None
                else MATURITY_IMMATURE)
            artifact = self._artifact(
                mint=mint, state=state, snapshot=snapshot,
                lifecycle_state=lifecycle_state, maturity=maturity_token,
                maturity_result=maturity_result, identity=identity,
                send_block_reasons=send_block_reasons)
            state["last_artifact"] = artifact
            if material_before != self._material_tuple(state):
                self._persist(mint, state)
            return FeeGateLifecycleView(
                candidate_mint=mint,
                lifecycle_state=lifecycle_state,
                maturity=maturity_token,
                current_verdict=snapshot.fee_gate_label,
                send_block_reasons=send_block_reasons,
                effective_snapshot=effective,
                evidence_proof_digest=snapshot.proof_digest,
                evidence_identity=identity,
                artifact=artifact,
            )

    @staticmethod
    def _material_tuple(state: Mapping[str, Any]) -> Tuple[Any, ...]:
        return (
            state["lifecycle_state"],
            state["last_fresh_verdict"],
            state["last_fresh_maturity"],
            state["provisional_scam_count"],
            state["confirmation_identities"],
            state["durable_scam_locked"],
            state["durable_lock_reasons"],
        )

    @staticmethod
    def _state_counter(lifecycle_state: str) -> str:
        return {
            LIFECYCLE_IMMATURE: "fee_gate_immature",
            LIFECYCLE_FRESH_PROVISIONAL: "fee_gate_fresh_provisional",
            LIFECYCLE_FRESH_CONFIRMED: "fee_gate_fresh_confirmed",
            LIFECYCLE_TEMPORARILY_STALE: "fee_gate_temporarily_stale",
            LIFECYCLE_DURABLE_SCAM_LOCKED: "fee_gate_durable_scam_locked",
        }[lifecycle_state]

    def _send_block_reasons(
        self, mint: str, state: Mapping[str, Any], lifecycle_state: str,
    ) -> Tuple[str, ...]:
        if mint in self._tainted:
            return (LIFECYCLE_BLOCK_STATE_INVALID,)
        if state["durable_scam_locked"]:
            return (LIFECYCLE_BLOCK_DURABLE_LOCK,)
        if lifecycle_state == LIFECYCLE_TEMPORARILY_STALE:
            return (LIFECYCLE_BLOCK_STALE,)
        if lifecycle_state == LIFECYCLE_IMMATURE:
            return (LIFECYCLE_BLOCK_IMMATURE,)
        if lifecycle_state == LIFECYCLE_FRESH_PROVISIONAL:
            return (LIFECYCLE_BLOCK_PROVISIONAL,)
        return ()

    def _artifact(
        self,
        *,
        mint: str,
        state: Mapping[str, Any],
        snapshot: FeeGateSnapshot,
        lifecycle_state: str,
        maturity: str,
        maturity_result: Optional[MaturityResult],
        identity: Optional[str],
        send_block_reasons: Tuple[str, ...],
    ) -> Dict[str, Any]:
        return {
            "kind": "PHX2_FEE_GATE_LIFECYCLE",
            "lifecycle_version": FEE_GATE_LIFECYCLE_VERSION,
            "token_mint": mint,
            "lifecycle_state": lifecycle_state,
            "current_verdict": snapshot.fee_gate_label,
            "current_reasons": list(snapshot.fee_gate_reasons),
            "maturity": maturity,
            "evidence_span_seconds": (
                maturity_result.evidence_span_seconds
                if maturity_result is not None else None),
            "sample_count": int(snapshot.sample_count),
            "transaction_count": int(snapshot.transaction_count),
            "event_count": int(snapshot.event_count),
            "evidence_freshness_seconds": snapshot.evidence_freshness_seconds,
            "evidence_proof_digest": snapshot.proof_digest,
            "evidence_identity_digest": identity,
            "last_fresh_verdict": state["last_fresh_verdict"],
            "last_fresh_score": state["last_fresh_score"],
            "last_fresh_reasons": list(state["last_fresh_reasons"]),
            "last_fresh_maturity": state["last_fresh_maturity"],
            "last_fresh_proof_digest": state["last_fresh_proof_digest"],
            "last_fresh_last_event_at_utc": state["last_fresh_last_event_at_utc"],
            "provisional_scam_count": int(state["provisional_scam_count"]),
            "durable_scam_locked": bool(state["durable_scam_locked"]),
            "durable_lock_reasons": list(state["durable_lock_reasons"]),
            "stale_since_epoch": state["stale_since_epoch"],
            "state_invalid": mint in self._tainted,
            "send_block_reasons": list(send_block_reasons),
            "legacy_lp_state": (
                LEGACY_LP_STATE_IGNORED_SINGLE_STREAM
                if mint in self._legacy_lp_ignored_mints else None),
        }

    # ---- read-only accessors ----

    def artifact_for(self, mint: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._by_mint.get(str(mint))
            if state is None or state.get("last_artifact") is None:
                return None
            return dict(state["last_artifact"])

    def is_durably_locked(self, mint: str) -> bool:
        with self._lock:
            state = self._by_mint.get(str(mint))
            return bool(state and state["durable_scam_locked"])

    def send_time_block_reason(
        self,
        *,
        view: FeeGateLifecycleView,
        bound_decision: Any,
        now_epoch: int,
    ) -> Optional[str]:
        """Fail-closed check at the pre-reserve boundary.

        ``view`` is the lifecycle observation taken at THIS instant;
        ``bound_decision`` is the sealed composite decision the composer will
        render (already digest-validated upstream).  Blocks — without reserving,
        mutating the ledger, or attempting transport — when current evidence is
        stale/immature/provisional/locked, when the current verdict is
        SCAM_LIKELY, when no decision is bound to this exact mint, or when the
        bound evidence itself has aged past the freshness window while the
        candidate waited between activation and compose.
        """

        for reason in view.send_block_reasons:
            with self._lock:
                if reason == LIFECYCLE_BLOCK_STALE:
                    self._counters["fee_gate_send_time_stale_blocks"] += 1
                elif reason in (LIFECYCLE_BLOCK_IMMATURE, LIFECYCLE_BLOCK_PROVISIONAL):
                    self._counters["fee_gate_send_time_immature_blocks"] += 1
                elif reason in (LIFECYCLE_BLOCK_DURABLE_LOCK, LIFECYCLE_BLOCK_STATE_INVALID):
                    self._counters["fee_gate_send_time_scam_blocks"] += 1
            return reason
        if view.current_verdict == PHX1_FEE_GATE_SCAM_LIKELY:
            with self._lock:
                self._counters["fee_gate_send_time_scam_blocks"] += 1
            return BLOCK_SCAM_LIKELY
        bound_fee = getattr(bound_decision, "fee_snapshot", None)
        if bound_fee is None or str(getattr(bound_fee, "candidate_mint", "")) \
                != view.candidate_mint:
            return LIFECYCLE_BLOCK_EVIDENCE_UNBOUND
        if getattr(bound_fee, "fee_gate_label", None) == PHX1_FEE_GATE_SCAM_LIKELY:
            with self._lock:
                self._counters["fee_gate_send_time_scam_blocks"] += 1
            return BLOCK_SCAM_LIKELY
        bound_last_epoch = _parse_utc_epoch(
            getattr(bound_fee, "last_observed_at_utc", None))
        if bound_last_epoch is None:
            return LIFECYCLE_BLOCK_EVIDENCE_UNBOUND
        bound_age = Decimal(int(now_epoch) - bound_last_epoch)
        if bound_age < 0 or bound_age > self._config.freshness_max_age_seconds:
            with self._lock:
                self._counters["fee_gate_send_time_stale_blocks"] += 1
            return LIFECYCLE_BLOCK_STALE
        return None

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            by_state: Dict[str, int] = {name: 0 for name in sorted(LIFECYCLE_STATES)}
            for state in self._by_mint.values():
                token = state.get("lifecycle_state")
                if token in by_state:
                    by_state[token] += 1
            return {
                "lifecycle_version": FEE_GATE_LIFECYCLE_VERSION,
                **dict(self._counters),
                "fee_lifecycle_mints_tracked": len(self._by_mint),
                "fee_lifecycle_mints_by_state": by_state,
                "fee_lifecycle_state_invalid_mints": len(self._tainted),
                "fee_lifecycle_restored_records": self._restored_records,
                "fee_lifecycle_restored_locks": self._restored_locks,
                "fee_lifecycle_legacy_lp_locks_ignored": self._legacy_lp_locks_ignored,
                "fee_lifecycle_load_dropped": self._load_dropped,
                "fee_lifecycle_persist_errors": self._persist_errors,
            }


def make_fee_gate_send_time_gate(
    *,
    fee_index: Any,
    lifecycle_index: FeeGateLifecycleIndex,
    security_index: Any,
    max_age_seconds: object,
    now_epoch_fn: Callable[[], int],
    phx1_structural_policy: str = "ENFORCE",
    policy_counters: Any = None,
) -> Callable[[str], Optional[str]]:
    """Build the production pre-reserve send-time gate.

    Runs at the compose boundary (after market context, before any dedupe
    reserve / ledger mutation / transport): re-snapshots CURRENT evidence, folds
    it into the lifecycle (the identity digest dedupe means re-observing frozen
    evidence never double-counts), and fails closed unless the lifecycle is
    FRESH_CONFIRMED with an acceptable verdict and the bound decision's evidence
    is still fresh for this exact mint.
    """

    max_age = Decimal(str(max_age_seconds))

    def fee_gate_send_time_gate(mint: str) -> Optional[str]:
        now_epoch = int(now_epoch_fn())
        snapshot = fee_index.snapshot(
            str(mint), now_epoch=now_epoch, max_age_seconds=max_age)
        view = lifecycle_index.observe(snapshot, now_epoch=now_epoch)
        bound_decision = security_index.get(str(mint))
        raw_reason = lifecycle_index.send_time_block_reason(
            view=view,
            bound_decision=bound_decision,
            now_epoch=now_epoch,
        )
        # Preserve the accepted ENFORCE boundary byte-for-byte: it returns the
        # same first raw lifecycle reason and does not replace the tick-bound
        # decision.  SHADOW re-routes only that exact reason, then binds the
        # refreshed sealed decision so composer/artifact consumers cannot lose
        # the original evidence.
        from PHX2.free_tier_producer.phx1_structural_policy import (
            PHX1_STRUCTURAL_POLICY_ENFORCE,
            normalize_phx1_structural_policy,
        )
        policy_mode = normalize_phx1_structural_policy(
            phx1_structural_policy)
        if policy_mode == PHX1_STRUCTURAL_POLICY_ENFORCE or raw_reason is None:
            return raw_reason
        from PHX2.free_tier_producer.scam_policy import (
            delivery_block_reason,
            evaluate_delivery_safety,
            validate_delivery_decision,
        )
        bound_original_reasons = tuple(
            getattr(bound_decision, "original_hard_block_reason_tokens", ())
            or ()
        )
        original_reasons = tuple(dict.fromkeys((
            *bound_original_reasons,
            *view.send_block_reasons,
            raw_reason,
        )))
        refreshed = evaluate_delivery_safety(
            fee_snapshot=view.effective_snapshot,
            existing_block_reasons=original_reasons,
            phx1_structural_policy=policy_mode,
        )
        valid, invalid_reason = validate_delivery_decision(refreshed)
        if not valid:
            return invalid_reason or raw_reason
        security_index.bind(refreshed)
        effective_reason = delivery_block_reason(refreshed)
        if effective_reason is None and policy_counters is not None:
            # An original hard block was carried forward as a visible
            # manual-review warning rather than enforced.  Counted, never
            # rendered as blocked.
            try:
                policy_counters.increment("fee_lifecycle_shadow_warnings")
            except Exception:
                pass
        return effective_reason

    return fee_gate_send_time_gate


__all__ = (
    "FEE_GATE_LIFECYCLE_VERSION",
    "LIFECYCLE_IMMATURE", "LIFECYCLE_FRESH_PROVISIONAL",
    "LIFECYCLE_FRESH_CONFIRMED", "LIFECYCLE_TEMPORARILY_STALE",
    "LIFECYCLE_DURABLE_SCAM_LOCKED", "LIFECYCLE_STATES",
    "MATURITY_IMMATURE", "MATURITY_PROVISIONAL", "MATURITY_CONFIRMED",
    "LIFECYCLE_BLOCK_IMMATURE", "LIFECYCLE_BLOCK_PROVISIONAL",
    "LIFECYCLE_BLOCK_STALE", "LIFECYCLE_BLOCK_DURABLE_LOCK",
    "LIFECYCLE_BLOCK_STATE_INVALID", "LIFECYCLE_BLOCK_EVIDENCE_UNBOUND",
    "SEVERE_PROOF_LP_REMOVAL_COMPOSITE",
    "LEGACY_LP_STATE_IGNORED_SINGLE_STREAM",
    "FeeGateLifecycleConfig", "build_fee_gate_lifecycle_config",
    "MaturityResult", "evaluate_maturity", "evidence_identity_digest",
    "stamp_durable_scam_lock",
    "FeeGateLifecycleRecord", "seal_lifecycle_record", "validate_lifecycle_record",
    "FeeGateLifecycleView", "FeeGateLifecycleIndex",
    "make_fee_gate_send_time_gate",
)
